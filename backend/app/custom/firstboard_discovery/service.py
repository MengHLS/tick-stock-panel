"""Read-only first-board discovery orchestration and bounded snapshot cache."""
from __future__ import annotations

import copy
import math
import threading
import time
from bisect import bisect_right
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
from app.custom.firstboard_discovery.negative import (
    MAIN_COLUMN,
    MAIN_THRESHOLD,
    build_negative_research,
    predict_negative_risk,
    prepare_research_cohorts,
)
from app.custom.firstboard_discovery.outcomes import build_event_samples
from app.custom.firstboard_discovery.storage import FirstboardDiscoveryStore
from app.enriched_generation import EnrichedGenerationUnavailableError
from app.extensions.adapters import repository_read_adapters
from app.factors.registry import all_factors, get_factor

ALGORITHM_VERSION = "firstboard-discovery-v6"
_EXCLUDED_DEPS = {
    "turnover_rate", "float_shares", "total_shares",
    "pb_latest", "roe_latest", "gross_margin_latest", "net_margin_latest",
    "revenue_yoy_latest", "net_income_yoy_latest", "debt_ratio_latest",
}
_EXCLUDED_FACTOR_IDS = {"vwap_bias"}
_ALLOWED_EXTENSION_FACTOR_IDS = (
    "ext_limit_board_events_first_seal_minute",
    "ext_limit_board_events_observed_open",
    "ext_limit_board_events_limit_up_pool_open_times",
)
_CANDIDATE_POLICY = {
    "allowed_kinds": ["base", "virtual"],
    "allowed_languages": ["dsl"],
    "require_scale_free": True,
    "require_stable": True,
    "excluded_factor_ids": sorted(_EXCLUDED_FACTOR_IDS),
    "allowed_extension_factor_ids": list(_ALLOWED_EXTENSION_FACTOR_IDS),
}
WARNINGS = [
    "平台口径首板，历史 ST/板块制度未认证；事件数为候选数量。",
    "最高收益是价格机会，不是可兑现收益；T+1 开盘仅为研究基准，未模拟成交、费用或 T+1 卖出约束。",
    "最大不利波动不是持有期最大回撤；-8% 低点触及不等于实际止损成交。",
    "因子、方向和阈值只在训练期选择；验证期证据不足时不会替换训练规则。",
    "同日事件和重叠收益窗口并非独立样本；q 值为探索性诊断，不构成有效性认证。",
    "确认性候选含内置 DSL 无量纲稳定因子，以及首次封板、是否开板、涨停池开板次数；自定义/复合、原始价位、VWAP乖离、实验因子、炸板池次数和最后封板时间不参与。",
    "早损定义为 T+1 开盘后前 5 个交易日低点触及 -8%，不等于实际亏损或可成交止损；预测风险与观察标签分别报告。",
    "按所选事件日期与当前数据库计算；行情数据截至日仅说明来源。风险阈值只在训练内校准段选择。",
]


@dataclass(frozen=True)
class DiscoveryParams:
    start: date
    end: date
    horizon: int = 20
    strong_threshold: float = 0.20
    snapshot_mode: Literal["D_minus_1", "D_close", "both"] = "both"
    train_end: date | None = None

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise ValueError("开始日期不能晚于结束日期")
        if self.horizon != 20:
            raise ValueError("首版仅支持 20 个交易日")
        if not math.isfinite(self.strong_threshold) or self.strong_threshold != 0.20:
            raise ValueError("首版强首板阈值固定为 20%")
        if self.snapshot_mode not in ("D_minus_1", "D_close", "both"):
            raise ValueError("未知特征时点")
        if self.train_end is not None and not self.start < self.train_end < self.end:
            raise ValueError("预注册训练截止日必须位于事件区间内部")


@dataclass(frozen=True)
class _Snapshot:
    report: dict
    events: list[dict]


class FirstboardDiscoveryService:
    def __init__(
        self,
        repository: Any | None = None,
        engine: Any | None = None,
        storage: FirstboardDiscoveryStore | None = None,
        *,
        market_data: Any | None = None,
        enriched_panel: Any | None = None,
        data_dir: Any | None = None,
    ) -> None:
        fallback_market, fallback_enriched = repository_read_adapters(repository) if repository is not None else (None, None)
        self.market_data = market_data or fallback_market
        self.enriched_panel = enriched_panel or fallback_enriched
        if self.market_data is None or self.enriched_panel is None:
            raise TypeError("market_data and enriched_panel are required")
        if engine is None:
            from app.backtest.read import BacktestReadAdapter

            if repository is None:
                raise TypeError("repository or engine is required")
            engine = BacktestReadAdapter(repository)
        self.backtest_read = engine
        self.repository = self.market_data
        self.engine = self.backtest_read
        self.data_dir = data_dir
        if self.data_dir is None:
            self.data_dir = getattr(getattr(repository, "store", None), "data_dir", None)
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

        def safe(
            spec,
            seen: frozenset[str] = frozenset(),
            *,
            root: bool = True,
        ) -> bool:
            if spec.id in seen:
                return False
            allowed_extension = spec.id in _ALLOWED_EXTENSION_FACTOR_IDS
            if (
                (spec.id.startswith("ext_") and not allowed_extension)
                or spec.id in _EXCLUDED_DEPS
                or spec.id in _EXCLUDED_FACTOR_IDS
                or spec.kind not in _CANDIDATE_POLICY["allowed_kinds"]
                or getattr(spec, "lang", "dsl") not in _CANDIDATE_POLICY["allowed_languages"]
                or (root and not spec.scale_free and not allowed_extension)
                or spec.stability != "stable"
            ):
                return False
            if spec.pit or spec.group in ("财务", "规模"):
                return False
            for dependency in spec.dependencies:
                if (
                    (dependency.startswith("ext_") and not allowed_extension)
                    or dependency in _EXCLUDED_DEPS
                    or dependency in _EXCLUDED_FACTOR_IDS
                ):
                    return False
                dependency_spec = specs.get(dependency)
                if dependency_spec is not None and not safe(
                    dependency_spec, seen | {spec.id}, root=False,
                ):
                    return False
            return True

        snapshots = (
            ["D_minus_1", "D_close"]
            if snapshot_mode == "both" else [snapshot_mode]
        )
        return [
            (spec.id, snapshot)
            for spec in specs.values()
            if safe(spec)
            for snapshot in snapshots
            if not (snapshot == "D_close" and spec.id == "change_pct")
            and not (
                snapshot == "D_minus_1"
                and spec.id in _ALLOWED_EXTENSION_FACTOR_IDS
            )
        ]

    def _snapshot(self, params: DiscoveryParams) -> _Snapshot:
        for attempt in range(3):
            try:
                return self._current_snapshot(params)
            except EnrichedGenerationUnavailableError:
                if attempt == 2:
                    raise EnrichedGenerationUnavailableError(
                        "行情正在更新，自动重试后仍未就绪，请稍后重试",
                    ) from None
                time.sleep(0.2)
        raise AssertionError("unreachable")

    def _current_snapshot(self, params: DiscoveryParams) -> _Snapshot:
        columns = self._candidate_factor_columns(params.snapshot_mode)
        wait_for_generation = getattr(
            self.backtest_read,
            "data_generation_await",
            None,
        )
        generation = (
            wait_for_generation("stock", timeout_s=10.0)
            if callable(wait_for_generation)
            else self.backtest_read.data_generation("stock")
        )
        versions = tuple(
            (s.id, s.version, s.formula_text, s.components)
            for s in all_factors(asset_type="stock")
        )
        extension_signature = self._extension_signature({column[0] for column in columns})
        key = (
            generation, params, tuple(columns), versions, ALGORITHM_VERSION,
            extension_signature,
        )
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                self._cache.move_to_end(key)
        if cached is not None:
            self._assert_generation(generation)
            return cached
        snapshot = self._build(params, columns, generation)
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
        if self.backtest_read.data_generation("stock") != generation:
            raise EnrichedGenerationUnavailableError("行情数据版本已变化，请重新发现")

    def _attach_limit_prices(self, panel: pl.DataFrame) -> pl.DataFrame:
        from app.indicators.pipeline import compute_limit_signals

        instruments = self.market_data.get_instruments("stock")
        if instruments.is_empty():
            raise ValueError("缺少股票维表，无法检查 T+1 开盘涨停价格")
        result = compute_limit_signals(
            panel,
            instruments,
            needed={"limit_up_price"},
            historical_shares=self.market_data.get_historical_shares(),
        )
        if "name" not in result.columns and "name" in instruments.columns:
            result = result.join(
                instruments.select("symbol", "name").unique("symbol"),
                on="symbol", how="left",
            )
        return result

    def _materialize_factors(self, panel: pl.DataFrame, factor_ids: set[str]) -> pl.DataFrame:
        from app.backtest.factor import compute_missing_factor_columns

        return compute_missing_factor_columns(
            panel, factor_ids - set(panel.columns),
        )

    def _attach_extension_factors(self, panel: pl.DataFrame, factor_ids: set[str]) -> pl.DataFrame:
        requested = factor_ids & set(_ALLOWED_EXTENSION_FACTOR_IDS)
        if not requested:
            return panel
        from app.factors import ext_factors

        data_dir = self._data_dir()
        if data_dir is None:
            raise ValueError("缺少数据目录，无法加载封板炸板扩展因子")
        config = next(
            (cfg for cfg in ext_factors.load_extension_configs(data_dir)
             if cfg.id == "limit_board_events"),
            None,
        )
        if config is None:
            raise ValueError("缺少涨停封板与炸板扩展表，无法进行本次因子研究")
        field_by_column = {
            ext_factors.ext_column_name(config.id, field.name): field
            for field in config.fields
        }
        missing_config = sorted(requested - set(field_by_column))
        if missing_config:
            raise ValueError(f"涨停封板与炸板扩展配置缺少字段: {missing_config}")
        fields = [field_by_column[name] for name in requested]
        ext = ext_factors.timeseries_frame(data_dir, config, fields)
        if ext.is_empty():
            raise ValueError("涨停封板与炸板扩展表暂无数据，无法进行本次因子研究")
        missing = requested - set(ext.columns)
        if missing:
            raise ValueError(f"涨停封板与炸板扩展表缺少字段: {sorted(missing)}")
        value_columns = sorted(requested - set(panel.columns))
        ext = (
            ext.select("symbol", "_ext_date", *value_columns)
            .rename({"_ext_date": "date"})
            .with_columns(pl.col("date").str.to_date())
        )
        return panel.join(ext, on=["symbol", "date"], how="left")

    def _data_dir(self):
        return self.data_dir

    def _extension_signature(self, factor_ids: set[str]) -> tuple | None:
        if not factor_ids & set(_ALLOWED_EXTENSION_FACTOR_IDS):
            return None
        data_dir = self._data_dir()
        if data_dir is None:
            return None
        from app.factors import ext_factors

        config_path = data_dir / "ext_data" / "limit_board_events" / "config.json"
        try:
            stat = config_path.stat()
            config_signature = (stat.st_mtime_ns, stat.st_size)
        except FileNotFoundError:
            config_signature = None
        except OSError:
            config_signature = None
        return (
            config_signature,
            ext_factors.timeseries_signature(
                data_dir / "ext_data" / "limit_board_events" / "timeseries",
            ),
        )

    def _build(self, params: DiscoveryParams, columns: list[tuple[str, str]], generation) -> _Snapshot:
        started = time.perf_counter()
        latest = self.enriched_panel.latest_date("stock")
        load_end = latest or params.end
        # Calendar padding is only an IO bound. Actual windows use observed bars;
        # finite feature coverage is checked after materialization.
        physical = [
            "symbol", "date", "open", "high", "low", "close", "volume", "amount",
            "raw_close", "raw_high", "raw_low", "consecutive_limit_ups",
        ]
        panel = self.backtest_read.load_panel(
            None, params.start - timedelta(days=550), load_end,
            columns=physical, asset_type="stock", expected_generation=generation,
        )
        if panel.is_empty():
            self._assert_generation(generation)
            return self._empty(params, generation, started)
        data_as_of = panel["date"].max()
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
        market_sessions = self._market_sessions(panel)
        # All database inputs are now in memory. Later publications do not
        # invalidate a calculation using this internally consistent read.
        self._assert_generation(generation)
        samples = build_event_samples(
            panel, horizon=params.horizon, strong_threshold=params.strong_threshold,
            sessions=market_sessions,
        ).filter(pl.col("date").is_between(params.start, params.end))
        if samples.is_empty():
            return self._empty(params, generation, started, data_as_of=data_as_of)
        # Future rows belong solely to outcomes, never to factor transforms.
        feature_panel = panel.filter(pl.col("date") <= params.end)
        feature_panel = self._attach_extension_factors(
            feature_panel, {c[0] for c in columns},
        )
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
        return self._summarize(
            params, samples, available, generation, started, data_as_of=data_as_of,
        )

    def _market_sessions(self, panel: pl.DataFrame) -> list[date]:
        start = panel["date"].min()
        end = panel["date"].max()
        sessions = self.market_data.list_trading_dates(start, end, "stock")
        if not sessions:
            raise ValueError("缺少全市场 enriched 交易日分区，无法构造 T+1 标签")
        return sessions

    def _summarize(
        self, params, samples, columns, generation, started, *, data_as_of=None,
    ) -> _Snapshot:
        eligible = samples.filter(pl.col("strong").is_not_null())
        dates = sorted(eligible["date"].unique().to_list())
        if params.train_end is not None:
            split_index = bisect_right(dates, params.train_end)
            if split_index == 0 or split_index >= len(dates):
                raise ValueError("预注册训练截止日两侧均需存在可评估事件")
            train_end = params.train_end
            validation_start = dates[split_index]
        else:
            split_index = min(max(1, int(len(dates) * 0.7)), max(len(dates) - 1, 1))
            train_end = dates[split_index - 1] if dates else None
            validation_start = dates[split_index] if len(dates) > split_index else None
        if train_end is None:
            train = eligible.head(0)
            validation = eligible.head(0)
            purged_count = 0
        elif validation_start is None:
            # A single eligible date has no future cohort to purge against.
            train = eligible.filter(pl.col("date") <= train_end)
            validation = eligible.head(0)
            purged_count = 0
        else:
            cohorts = prepare_research_cohorts(
                samples,
                train_end=train_end,
                validation_start=validation_start,
            )
            train = cohorts.train
            validation = cohorts.validation
            purged_count = cohorts.purged_count
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
        negative = (
            build_negative_research(
                train,
                validation,
                columns, train_end=train_end,
            ) if train_end is not None else
            {"status": "insufficient_sample", "groups": [], "model": {"status": "insufficient_sample"}}
        )
        negative["evaluation_cutoff"] = params.end
        negative["lockbox_excluded_count"] = 0
        risks = predict_negative_risk(samples, negative["model"])
        risk_by_id = dict(zip(samples["event_id"].to_list(), risks, strict=True))
        threshold = negative["model"].get("decision_threshold")
        event_rows = samples.sort(["date", "symbol"], descending=[True, False]).to_dicts()
        hits: dict[str, list[str]] = {row["event_id"]: [] for row in event_rows}
        for rule in rules:
            uses = [_condition_use(condition) for condition in rule["conditions"]]
            for event_id in _candidate_mask(samples, uses)["event_id"].to_list():
                hits[event_id].append(rule["id"])
        for row in event_rows:
            row["rule_ids"] = hits[row["event_id"]]
            probability = risk_by_id[row["event_id"]]
            row["early_fail_probability"] = float(probability) if math.isfinite(probability) else None
            row["negative_veto"] = (
                bool(probability >= threshold)
                if math.isfinite(probability) and threshold is not None else None
            )
            main_value = row.get(MAIN_COLUMN)
            row["frozen_main_hit"] = (
                bool(main_value >= MAIN_THRESHOLD)
                if main_value is not None and math.isfinite(main_value) else None
            )
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
            "data_as_of": data_as_of,
            "research_cutoff": params.end,
            "lockbox_excluded_count": 0,
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
            "negative_research": negative,
            "candidate_policy": {
                **_CANDIDATE_POLICY,
                "factor_count": len(columns),
            },
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
    def _empty(
        params,
        generation,
        started,
        *,
        data_as_of: date | None = None,
    ) -> _Snapshot:
        return _Snapshot({
            "algorithm_version": ALGORITHM_VERSION,
            "generation": generation,
            "params": asdict(params),
            "data_as_of": data_as_of,
            "research_cutoff": params.end,
            "lockbox_excluded_count": 0,
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
            "factors": [], "rules": [],
            "negative_research": {"status": "no_data", "groups": []},
            "candidate_policy": {**_CANDIDATE_POLICY, "factor_count": 0},
            "warnings": WARNINGS,
        }, [])


def _condition_use(condition: dict) -> tuple:
    column = f"{condition['snapshot']}__{condition['factor_id']}"
    if condition["operator"] != "between":
        return (column, condition["operator"], condition["threshold"])
    # Explicit bounds preserve the same disjoint buckets used for selection.
    return (column, "range", (condition.get("lower"), condition.get("upper")))
