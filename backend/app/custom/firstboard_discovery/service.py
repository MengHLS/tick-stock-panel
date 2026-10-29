"""Read-only first-board discovery orchestration and bounded snapshot cache."""
from __future__ import annotations

import copy
import math
import threading
import time
from collections import OrderedDict
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Any, Literal

import polars as pl

from app.custom.firstboard_discovery.discovery import (
    FactorScore,
    _candidate_mask,
    _factor_scores,
    score_factor,
    search_rules,
)
from app.custom.firstboard_discovery.outcomes import build_event_samples
from app.custom.firstboard_discovery.storage import FirstboardDiscoveryStore
from app.enriched_generation import EnrichedGenerationUnavailableError
from app.factors.registry import all_factors, get_factor

ALGORITHM_VERSION = "firstboard-discovery-v2"
_EXCLUDED_DEPS = {
    "turnover_rate", "float_shares", "total_shares",
    "pb_latest", "roe_latest", "gross_margin_latest", "net_margin_latest",
    "revenue_yoy_latest", "net_income_yoy_latest", "debt_ratio_latest",
}
WARNINGS = [
    "平台口径首板，历史 ST/板块制度未认证；事件数为候选数量。",
    "最高收益是价格机会，不是可兑现收益；T+1 开盘仅为研究基准，未模拟成交、费用或 T+1 卖出约束。",
    "最大不利波动不是持有期最大回撤；-8% 低点触及不等于实际止损成交。",
    "因子、方向和阈值只在训练期选择；验证期证据不足时不会替换训练规则。",
    "同日事件和重叠收益窗口并非独立样本；q 值为探索性诊断，不构成有效性认证。",
]


@dataclass(frozen=True)
class DiscoveryParams:
    start: date
    end: date
    horizon: int = 20
    strong_threshold: float = 0.20
    snapshot_mode: Literal["D_minus_1", "D_close", "both"] = "both"

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise ValueError("开始日期不能晚于结束日期")
        if self.horizon != 20:
            raise ValueError("首版仅支持 20 个交易日")
        if not math.isfinite(self.strong_threshold) or self.strong_threshold != 0.20:
            raise ValueError("首版强首板阈值固定为 20%")
        if self.snapshot_mode not in ("D_minus_1", "D_close", "both"):
            raise ValueError("未知特征时点")


@dataclass(frozen=True)
class _Snapshot:
    report: dict
    events: list[dict]


class FirstboardDiscoveryService:
    def __init__(
        self,
        repository: Any,
        engine: Any | None = None,
        storage: FirstboardDiscoveryStore | None = None,
    ) -> None:
        if engine is None:
            from app.backtest.engine import BacktestEngine

            engine = BacktestEngine(repository)
        self.repository = repository
        self.engine = engine
        self.storage = storage
        self._lock = threading.Lock()
        self._cache: OrderedDict[tuple, _Snapshot] = OrderedDict()

    def report(self, params: DiscoveryParams) -> dict:
        return copy.deepcopy(self._snapshot(params).report)

    def events(
        self,
        params: DiscoveryParams,
        *,
        rule_id: str | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> dict:
        if page < 1 or not 1 <= page_size <= 200:
            raise ValueError("分页参数超出范围")
        snapshot = self._snapshot(params)
        return self._events_payload(
            snapshot, rule_id=rule_id, page=page, page_size=page_size,
        )

    def list_runs(self) -> list[dict]:
        return self.storage.list_runs() if self.storage is not None else []

    def saved_report(self, run_id: str) -> dict:
        if self.storage is None:
            raise FileNotFoundError(run_id)
        return self.storage.load_report(run_id)

    def saved_events(
        self,
        run_id: str,
        *,
        rule_id: str | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> dict:
        if self.storage is None:
            raise FileNotFoundError(run_id)
        if page < 1 or not 1 <= page_size <= 200:
            raise ValueError("分页参数超出范围")
        report = self.storage.load_report(run_id)
        self._assert_rule(report, rule_id)
        total, rows = self.storage.load_event_page(
            run_id, rule_id=rule_id, page=page, page_size=page_size,
        )
        return {
            "generation": report["generation"],
            "total": total,
            "page": page,
            "page_size": page_size,
            "rows": rows,
        }

    def _events_payload(
        self,
        snapshot: _Snapshot,
        *,
        rule_id: str | None,
        page: int,
        page_size: int,
    ) -> dict:
        self._assert_rule(snapshot.report, rule_id)
        rows = [
            row for row in snapshot.events
            if not rule_id or rule_id in row["rule_ids"]
        ]
        offset = (page - 1) * page_size
        return {
            "generation": snapshot.report["generation"],
            "total": len(rows),
            "page": page,
            "page_size": page_size,
            "rows": copy.deepcopy(rows[offset:offset + page_size]),
        }

    @staticmethod
    def _assert_rule(report: dict, rule_id: str | None) -> None:
        if rule_id and rule_id not in {r["id"] for r in report["rules"]}:
            raise ValueError("规则不存在，请重新加载报告")

    def _candidate_factor_columns(self, snapshot_mode: str) -> list[tuple[str, str]]:
        specs = {spec.id: spec for spec in all_factors(asset_type="stock")}

        def safe(name: str, seen: frozenset[str] = frozenset()) -> bool:
            if name.startswith("ext_") or name in _EXCLUDED_DEPS or name in seen:
                return False
            spec = specs.get(name)
            if spec is None:
                return True
            if spec.pit or spec.group in ("财务", "规模"):
                return False
            return all(safe(dep, seen | {name}) for dep in spec.dependencies)

        snapshots = (
            ["D_minus_1", "D_close"]
            if snapshot_mode == "both" else [snapshot_mode]
        )
        return [
            (spec.id, snapshot)
            for spec in specs.values()
            if safe(spec.id) and spec.stability != "deprecated"
            for snapshot in snapshots
            if not (snapshot == "D_close" and spec.id == "change_pct")
        ]

    def _snapshot(self, params: DiscoveryParams) -> _Snapshot:
        columns = self._candidate_factor_columns(params.snapshot_mode)
        generation = self.engine.data_generation("stock")
        versions = tuple(
            (s.id, s.version, s.formula_text, s.components)
            for s in all_factors(asset_type="stock")
        )
        key = (generation, params, tuple(columns), versions, ALGORITHM_VERSION)
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                self._cache.move_to_end(key)
        if cached is not None:
            self._assert_generation(generation)
            return cached
        snapshot = self._build(params, columns, generation)
        self._assert_generation(generation)
        if self.storage is not None:
            run_id, saved_at = self.storage.save(snapshot.report, snapshot.events)
            snapshot = _Snapshot(
                report={**snapshot.report, "run_id": run_id, "saved_at": saved_at},
                events=snapshot.events,
            )
        with self._lock:
            self._cache[key] = snapshot
            self._cache.move_to_end(key)
            while len(self._cache) > 4:
                self._cache.popitem(last=False)
        return snapshot

    def _assert_generation(self, generation: str | None) -> None:
        if self.engine.data_generation("stock") != generation:
            raise EnrichedGenerationUnavailableError("行情数据版本已变化，请重新发现")

    def _attach_limit_prices(self, panel: pl.DataFrame) -> pl.DataFrame:
        from app.indicators.pipeline import compute_limit_signals

        instruments = self.repository.get_instruments_asset("stock")
        if instruments.is_empty():
            raise ValueError("缺少股票维表，无法检查 T+1 开盘涨停价格")
        result = compute_limit_signals(
            panel,
            instruments,
            needed={"limit_up_price"},
            historical_shares=self.repository.get_historical_shares(),
        )
        if "name" not in result.columns and "name" in instruments.columns:
            result = result.join(
                instruments.select("symbol", "name").unique("symbol"),
                on="symbol", how="left",
            )
        return result

    def _materialize_factors(self, panel: pl.DataFrame, factor_ids: set[str]) -> pl.DataFrame:
        from app.backtest.factor import FactorBacktestService

        return FactorBacktestService._compute_missing_factors(
            panel, factor_ids - set(panel.columns),
        )

    def _build(self, params: DiscoveryParams, columns: list[tuple[str, str]], generation) -> _Snapshot:
        started = time.perf_counter()
        latest = getattr(self.repository, "latest_enriched_date", lambda _: params.end)("stock")
        load_end = latest or params.end
        # Calendar padding is only an IO bound. Actual windows use observed bars;
        # finite feature coverage is checked after materialization.
        physical = [
            "symbol", "date", "open", "high", "low", "close", "volume", "amount",
            "raw_close", "raw_high", "raw_low", "consecutive_limit_ups",
        ]
        panel = self.engine.load_panel(
            None, params.start - timedelta(days=550), load_end,
            columns=physical, asset_type="stock", expected_generation=generation,
        )
        if panel.is_empty():
            return self._empty(params, generation, started)
        panel = panel.sort(["symbol", "date"])
        keys = panel.select(
            pl.struct("symbol", "date").n_unique(),
        ).item()
        if keys != panel.height or panel["symbol"].null_count() or panel["date"].null_count():
            raise ValueError("行情日期或股票键缺失/重复，无法构造事件快照")
        # Enriched stores adjusted open and raw close; derive raw open on the
        # identical row scale instead of mixing adjusted and raw prices.
        panel = panel.with_columns(
            (pl.col("open") * pl.col("raw_close") / pl.col("close")).alias("raw_open"),
        )
        panel = self._attach_limit_prices(panel).sort(["symbol", "date"])
        samples = build_event_samples(
            panel, horizon=params.horizon, strong_threshold=params.strong_threshold,
        ).filter(pl.col("date").is_between(params.start, params.end))
        if samples.is_empty():
            return self._empty(params, generation, started)
        # Future rows belong solely to outcomes, never to factor transforms.
        feature_panel = panel.filter(pl.col("date") <= params.end)
        feature_panel = self._materialize_factors(feature_panel, {c[0] for c in columns})
        feature_panel = feature_panel.sort(["symbol", "date"])
        available = [(fid, snap) for fid, snap in columns if fid in feature_panel.columns]
        expressions = []
        for factor_id, snapshot in available:
            value = pl.col(factor_id).cast(pl.Float64, strict=False)
            if snapshot == "D_minus_1":
                value = value.shift(1).over("symbol")
            expressions.append(value.alias(f"{snapshot}__{factor_id}"))
        values = feature_panel.select("symbol", "date", *expressions)
        samples = samples.join(values, on=["symbol", "date"], how="left")
        self._assert_generation(generation)
        return self._summarize(params, samples, available, generation, started)

    def _summarize(self, params, samples, columns, generation, started) -> _Snapshot:
        eligible = samples.filter(pl.col("strong").is_not_null())
        dates = sorted(eligible["date"].unique().to_list())
        split_index = min(max(1, int(len(dates) * 0.7)), max(len(dates) - 1, 1))
        train_end = dates[split_index - 1] if dates else None
        validation_start = dates[split_index] if len(dates) > split_index else None
        train = eligible.filter(pl.col("date") <= train_end) if train_end else eligible.head(0)
        validation = eligible.filter(pl.col("date") >= validation_start) if validation_start else eligible.head(0)
        unpurged_count = train.height
        if validation_start is not None:
            train = train.filter(pl.col("outcome_end") < validation_start)
        purged_count = unpurged_count - train.height
        training_ids = set(train["event_id"].to_list())
        research_events = pl.concat([train, validation])
        scores = _factor_scores(train, columns) if train.height else []
        base_rate = float(train["strong"].mean() or 0.0)
        sufficient = (
            train.height >= 120 and validation.height >= 60
            and min(int(train["strong"].sum() or 0), train.height - int(train["strong"].sum() or 0)) >= 10
            and min(int(validation["strong"].sum() or 0), validation.height - int(validation["strong"].sum() or 0)) >= 10
        )
        # Sparse data still has diagnostic factor scores, but no auto rules.
        rules = (
            search_rules(research_events, columns, train_end=train_end, base_rate=base_rate)
            if sufficient else []
        )
        factor_rows = [self._factor_row(s, validation) for s in scores]
        factor_rows.sort(key=lambda row: -abs((row["auc"] if row["auc"] is not None else .5) - .5))
        event_rows = samples.sort(["date", "symbol"], descending=[True, False]).to_dicts()
        hits: dict[str, list[str]] = {row["event_id"]: [] for row in event_rows}
        for rule in rules:
            uses = [_condition_use(condition) for condition in rule["conditions"]]
            for event_id in _candidate_mask(samples, uses)["event_id"].to_list():
                hits[event_id].append(rule["id"])
        for row in event_rows:
            row["rule_ids"] = hits[row["event_id"]]
            row["split"] = (
                "excluded" if row["strong"] is None
                else "train" if row["event_id"] in training_ids
                else "purged" if train_end and row["date"] <= train_end
                else "validation"
            )
            row.pop("row_index", None)
            for field, value in row.items():
                if isinstance(value, float) and not math.isfinite(value):
                    row[field] = None
        exclusions = {
            name: int(samples[name].sum() or 0)
            for name in (
                "right_censored", "entry_unavailable", "entry_limit_locked",
                "outcome_unavailable", "scale_break_suspected",
            )
        }
        report = {
            "algorithm_version": ALGORITHM_VERSION,
            "generation": generation,
            "params": asdict(params),
            "data_as_of": max(samples["entry_date"].drop_nulls().to_list(), default=None),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
            "sample": {
                "status": "ok" if sufficient else "insufficient_sample",
                "total_events": samples.height,
                "eligible_events": eligible.height,
                "excluded_events": samples.height - eligible.height,
                "excluded": exclusions,
                "base_strong_rate": float(eligible["strong"].mean()) if eligible.height else None,
            },
            "split": {
                "train_start": dates[0] if dates else None,
                "train_end": train_end,
                "validation_start": validation_start,
                "validation_end": dates[-1] if validation_start else None,
                "train_count": train.height,
                "purged_count": purged_count,
                "validation_count": validation.height,
                "train_base_rate": base_rate,
                "validation_base_rate": float(validation["strong"].mean()) if validation.height else None,
            },
            "factors": factor_rows,
            "rules": rules,
            "warnings": WARNINGS,
        }
        return _Snapshot(report=report, events=event_rows)

    @staticmethod
    def _factor_row(score: FactorScore, validation: pl.DataFrame) -> dict:
        column = f"{score.snapshot}__{score.factor_id}"
        valid_score = score_factor(
            score.factor_id, score.snapshot,
            validation[column].to_list() if column in validation.columns else [],
            validation["strong"].to_list() if column in validation.columns else [],
        )
        return {
            **asdict(score),
            "label": (spec.label if (spec := get_factor(score.factor_id)) else score.factor_id),
            "validation_auc": valid_score.auc,
            "validation_coverage": valid_score.coverage,
            "validation_count": valid_score.train_count,
        }

    @staticmethod
    def _empty(params, generation, started) -> _Snapshot:
        return _Snapshot({
            "algorithm_version": ALGORITHM_VERSION,
            "generation": generation,
            "params": asdict(params),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
            "sample": {
                "status": "no_data", "total_events": 0, "eligible_events": 0,
                "excluded_events": 0, "excluded": {}, "base_strong_rate": None,
            },
            "split": {
                "train_start": None, "train_end": None, "validation_start": None,
                "validation_end": None, "train_count": 0, "validation_count": 0,
                "train_base_rate": None, "validation_base_rate": None,
            },
            "factors": [], "rules": [], "warnings": WARNINGS,
        }, [])


def _condition_use(condition: dict) -> tuple:
    column = f"{condition['snapshot']}__{condition['factor_id']}"
    if condition["operator"] != "between":
        return (column, condition["operator"], condition["threshold"])
    # Explicit bounds preserve the same disjoint buckets used for selection.
    return (column, "range", (condition.get("lower"), condition.get("upper")))
