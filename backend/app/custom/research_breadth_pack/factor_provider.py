"""`market_breadth` 的 Provider 注册 (台账 §16.4 门票)。

物化顺序无关: `materialize_factor_columns` 按 provider 分组迭代, `market_breadth` 若
排在 `in_universe` 之前被求值, `breadth.compute_market_breadth` 会自行物化
`ma60` 与 `in_universe`(同一口径, 见该模块 docstring), 不依赖调用方的顺序。

矩阵路径 (`materialize_matrix_field`) 保持基类默认 `None` = 缺能力项: 与 `in_universe`
一致, 矩阵侧不是本批范围。
"""
from __future__ import annotations

from pathlib import Path

import polars as pl

from app.custom.research_breadth_pack.breadth import (
    MARKET_BREADTH_ID,
    MARKET_BREADTH_SPEC,
    compute_market_breadth,
)
from app.extensions.factors import FactorProvider, FactorProviderContext
from app.tickflow.security_status import read_st_history


class ResearchBreadthProvider(FactorProvider):
    provider_id = "official.research-breadth-pack-e5"
    version = 1
    kind = "frame"
    factor_ids = frozenset({MARKET_BREADTH_ID})
    factor_specs = (MARKET_BREADTH_SPEC,)

    def dependencies(self, factor_id: str) -> frozenset[str]:
        del factor_id
        return MARKET_BREADTH_SPEC.dependencies

    def warmup_bars(self, factor_id: str) -> int:
        del factor_id
        return MARKET_BREADTH_SPEC.warmup_bars

    def params(self, factor_id: str):
        del factor_id
        return {"formula": MARKET_BREADTH_SPEC.formula_text}

    def materialize_frame(
        self,
        frame: pl.DataFrame,
        names: frozenset[str],
        context: FactorProviderContext,
    ) -> pl.DataFrame:
        if MARKET_BREADTH_ID not in names or MARKET_BREADTH_ID in frame.columns:
            return frame
        if frame.is_empty():
            return frame.with_columns(
                pl.lit(None, dtype=pl.Float64).alias(MARKET_BREADTH_ID)
            )
        return compute_market_breadth(frame, st_history=self._st_history(context))

    @staticmethod
    def _st_history(context: FactorProviderContext) -> pl.DataFrame:
        """按 `context.data_dir` 读 st_history; 无 data_dir 时回落到 settings, 仍拿不到就抛。

        口径与 `in_universe` 同源 (契约 §2.3): 拿不到历史 ST 就不能把「未知」当「非 ST」。
        """
        data_dir = context.data_dir
        if data_dir is None:
            from app.config import settings

            data_dir = settings.data_dir
        assert isinstance(data_dir, Path)
        history = read_st_history(data_dir)
        if history.is_empty():
            raise ValueError(
                "market_breadth 需要 in_universe, 而 in_universe 需要 st_history; "
                f"未在数据目录找到 ({data_dir / 'st_history'})"
            )
        return history


FACTOR_PROVIDERS = (ResearchBreadthProvider(),)
