"""E3 `in_universe` 的 Provider 注册 (契约 v0.7 §2, 落到 frame 路径)。

为什么是独立 Provider 而不是纯 DSL 因子:
- `in_universe` 需要**有状态输入** (as-of 的 `st_history` + 覆盖期末端), DSL 只能表达
  逐行表达式, 无法访问外部数据集; Provider 是既有扩展点, 提供 `context.data_dir`。
- 计算本身只调用 `app/custom/research_universe_pack/universe.py`, 不重写口径。

矩阵路径 (`materialize_matrix_field`) 保持基类默认 `None` = 缺能力项: 契约 §7.13/§7.14
把矩阵侧 `in_universe` 列为 B0b 另批, 本批不动矩阵路径。
"""
from __future__ import annotations

from pathlib import Path

import polars as pl

from app.custom.research_universe_pack.universe import (
    FACTOR_COLUMN_IN_UNIVERSE,
    UniverseParams,
    compute_in_universe,
)
from app.extensions.factors import FactorProvider, FactorProviderContext
from app.factors.registry import FactorSpec
from app.tickflow.security_status import read_st_history

IN_UNIVERSE_ID = FACTOR_COLUMN_IN_UNIVERSE

# 依赖列 = 契约 §2.2 输入表 + 内部派生 prior_amount20 所需的 amount。
# 不含 st_flag: 它来自 st_history 数据集 (as-of), 不是面板列 (面板列 st_flag 是
# 当前名称推断的近似值, 契约 §2.5-3 明令禁止用它判历史)。
IN_UNIVERSE_DEPENDENCIES = frozenset(
    {"symbol", "date", "volume", "amount", "raw_close"}
)

_SPEC = FactorSpec(
    id=IN_UNIVERSE_ID,
    label="公共股票池掩码",
    group="研究补充",
    formula_text=(
        "(observed_bars >= 120) & (st_flag == False as-of) & (raw_close >= 3.0)"
        " & (prior_amount20 >= 1e8) & (volume > 0)"
    ),
    kind="custom",
    lang="dsl",
    version=1,
    dependencies=IN_UNIVERSE_DEPENDENCIES,
    # warmup = 契约 §2.2 的 121 (observed_bars 需 120 根 + prior_amount20 需 21 根,
    # 取 max=120 后再 +1 覆盖「第 120 根之前不可判」)。台账必须登记 120 而非 60。
    warmup_bars=120,
    unit="none",
    direction="none",  # 掩码无方向 (契约 §7.2)
    # 值域 {1.0, 0.0, null} —— 供 xs_rank_pool / xs_mean / xs_rank_pct 的第 2 参数
    # 通过 dsl.py#MASK_FACTOR_TAG 静态识破「这是掩码」。
    tags=("mask", "研究基线", "E3"),
    stability="stable",
    null_policy="keep",
    scale_free=True,
)


class ResearchUniverseProvider(FactorProvider):
    provider_id = "official.research-universe-pack-e3"
    version = 1
    kind = "frame"
    factor_ids = frozenset({IN_UNIVERSE_ID})
    factor_specs = (_SPEC,)

    def dependencies(self, factor_id: str) -> frozenset[str]:
        del factor_id
        return IN_UNIVERSE_DEPENDENCIES

    def warmup_bars(self, factor_id: str) -> int:
        del factor_id
        return _SPEC.warmup_bars

    def params(self, factor_id: str):
        del factor_id
        params = UniverseParams()
        return {
            "min_observed_bars": params.min_observed_bars,
            "min_price_raw": params.min_price_raw,
            "min_prior_amount20": params.min_prior_amount20,
            "require_volume_gt0": params.require_volume_gt0,
            "symbol_prefixes": params.symbol_prefixes,
            "exclude_st": params.exclude_st,
            "st_flag_missing_policy": params.st_flag_missing_policy,
            "st_unknown_windows": params.st_unknown_windows,
            "universe_version": params.universe_version,
        }

    def materialize_frame(
        self,
        frame: pl.DataFrame,
        names: frozenset[str],
        context: FactorProviderContext,
    ) -> pl.DataFrame:
        if IN_UNIVERSE_ID not in names or IN_UNIVERSE_ID in frame.columns:
            return frame
        if frame.is_empty():
            return frame.with_columns(
                pl.lit(None, dtype=pl.Float64).alias(IN_UNIVERSE_ID)
            )
        history = self._st_history(context)
        return compute_in_universe(frame, st_history=history)

    @staticmethod
    def _st_history(context: FactorProviderContext) -> pl.DataFrame:
        """按 `context.data_dir` 读 st_history; 无 data_dir 时 fail-closed。

        契约 §2.3: 拿不到历史 ST 就不能把「未知」当「非 ST」, 故宁可抛错。
        """
        data_dir = context.data_dir
        if data_dir is None:
            # 反向推导: 与 app.config.Settings.data_dir 同一来源, 不新增配置项。
            from app.config import settings

            data_dir = settings.data_dir
        assert isinstance(data_dir, Path)
        history = read_st_history(data_dir)
        if history.is_empty():
            raise ValueError(
                "in_universe 需要 st_history 数据集, 但未在数据目录找到 "
                f"({data_dir / 'st_history'}); 不能用当前名称或默认值代替"
            )
        return history


FACTOR_PROVIDERS = (ResearchUniverseProvider(),)
