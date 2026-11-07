"""研究基线因子包 (B0) 的 Provider 注册。

为什么走 Provider 而不是 `POST /api/factors/custom`:
- 自定义因子存储 (app/factors/store.py#CUSTOM_ID_PATTERN) 强制 id 形如 `uf_*` / `cf_*`,
  而研究侧策略表达式引用的是 `ma20` / `prior_high_20` 这类原名 (docs/factors/
  FACTOR_ENTRY_RULE_20261107.md §2.1 R1 引用闭合)。改名成 `uf_ma20` 会让策略提交物
  与研究规格对不上, 所以只能走「任意 id + 元数据」的 Provider 入口。
- Provider 是既有扩展点 (app/extensions/factors.py#ensure_factor_providers 自动发现
  app/custom/*/factor_provider.py), 注册不动内核: 不碰 registry/dsl/store。

计算不在这里重写: 每个因子只持有一条 DSL 公式 (factor_specs.py), 物化时用同一个
compile_formula_cached + frame_transform 原语 (与 app/strategy/scoring.py
materialize_scoring_columns 的 pending 分支完全一致), 因此与因子检验/评分/回测共用
一条计算路径, 不存在第二套实现。

矩阵回测 (app/backtest/matrix.py#matrix_feature) 目前只认识 ma*/boll_* 这类内置特征;
sd20 / prior_* / vol60 / prior_amount_20 的矩阵侧实现是缺能力项 (需架构契约), 本包
不在此处偷偷补一套 numpy 实现 —— 详见交付文档 limitations。
"""
from __future__ import annotations

import polars as pl

from app.custom.research_factor_pack.factor_specs import (
    RESEARCH_BASELINE_FACTOR_IDS,
    RESEARCH_BASELINE_FACTOR_SPECS,
    SPEC_BY_ID,
)
from app.extensions.factors import FactorProvider, FactorProviderContext
from app.factors.dsl import FACTOR_COLUMN, compile_formula_cached


def _sorted_by_symbol_date(frame: pl.DataFrame) -> bool:
    if frame.height < 2:
        return True
    return bool(frame.select(pl.struct(["symbol", "date"]).is_sorted()).item())


class ResearchFactorPackProvider(FactorProvider):
    """把研究侧口径注册成可引用因子; 数值由既有 DSL 计算。"""

    provider_id = "official.research-factor-pack-b0"
    version = 1
    kind = "frame"
    factor_ids = RESEARCH_BASELINE_FACTOR_IDS
    factor_specs = RESEARCH_BASELINE_FACTOR_SPECS

    def dependencies(self, factor_id: str) -> frozenset[str]:
        return SPEC_BY_ID[factor_id].dependencies

    def warmup_bars(self, factor_id: str) -> int:
        return SPEC_BY_ID[factor_id].warmup_bars

    def materialize_frame(
        self,
        frame: pl.DataFrame,
        names: frozenset[str],
        context: FactorProviderContext,
    ) -> pl.DataFrame:
        del context
        requested = [name for name in sorted(names) if name in RESEARCH_BASELINE_FACTOR_IDS]
        pending = [name for name in requested if name not in frame.columns]
        if frame.is_empty() or not pending:
            return frame
        if "symbol" not in frame.columns or "date" not in frame.columns:
            raise ValueError("研究基线因子需要 symbol/date 列 (fail-closed)")

        # 滚动窗口按 symbol 分组, 行序必须按 (symbol, date) 升序; 调用方给的帧
        # 若无序则先排序计算、再按原行序还原 (列位置语义保持不变)。
        restore_order = not _sorted_by_symbol_date(frame)
        work = frame.with_row_index("__rfp_row") if restore_order else frame
        if restore_order:
            work = work.sort(["symbol", "date"])

        for name in pending:
            spec = SPEC_BY_ID[name]
            compiled = compile_formula_cached(spec.formula_text)
            if not compiled.ok:
                first = compiled.errors[0]
                raise ValueError(
                    f"研究基线因子公式无效 {name} [{first.code}]: {first.message}"
                )
            transformed = compiled.frame_transform(work) if compiled.frame_transform else None
            if transformed is None:
                raise ValueError(
                    f"研究基线因子 {name} 缺少依赖列: {sorted(spec.dependencies)}"
                )
            column = transformed.get_column(FACTOR_COLUMN).alias(name)
            staged_temps = [
                c for c in transformed.columns
                if c not in work.columns and c != FACTOR_COLUMN
            ]
            work = transformed.drop([FACTOR_COLUMN, *staged_temps]).with_columns(column)

        if restore_order:
            work = work.sort("__rfp_row").drop("__rfp_row")
        return work


FACTOR_PROVIDERS = (ResearchFactorPackProvider(),)
