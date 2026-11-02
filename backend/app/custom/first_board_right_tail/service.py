"""Live observation service for first-board right-tail candidates."""
from __future__ import annotations

import math
import threading
from collections.abc import Iterable
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl

from app.custom.first_board_right_tail.screening import screen_first_boards
from app.custom.first_board_right_tail.storage import FirstBoardRightTailStore
from app.custom.first_board_right_tail.triggers import (
    aggregate_five_minutes,
    evaluate_intraday_rules,
)
from app.extensions.adapters import repository_read_adapters
from app.market_time import CN_TZ

ALGORITHM_VERSION = "first-board-right-tail-live-v1"
SOURCE = "first_board_right_tail"
WATCHING_STATUSES = {"WATCH", "BUY_PENDING", "FILLED"}

RULE_DESCRIPTIONS = {
    "A": "1分钟收盘突破T日最高，成交量大于前20分钟均量2倍；下一分钟开盘确认。",
    "B": "连续2根5分钟收盘站上当日VWAP，且VWAP高于上一根；下一分钟确认。",
    "C": "5分钟收盘重新站上5分钟MA5，且未跌破T日收盘-6%。",
    "D": "T+1竞价缺口0%-4%、竞价量比>1，首根5分钟均价不低于竞价均价；09:36确认。",
}


def _naive_cn(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(CN_TZ).replace(tzinfo=None)


def _limit_price(previous_raw: float | None) -> float | None:
    if previous_raw is None or previous_raw <= 0:
        return None
    cents = math.floor(previous_raw * 100.0 + 0.5)
    return math.floor((cents * 110 + 50) / 100) / 100.0


def build_simple_monitor_rules(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build the two rules supported by the existing monitor center."""
    from app.strategy import monitor_rules

    symbols = sorted({str(event.get("symbol")) for event in events if event.get("symbol")})
    if not symbols:
        return []
    base = {
        "type": "signal",
        "scope": "symbols",
        "symbols": symbols,
        "logic": "or",
        "cooldown_seconds": 3600,
        "severity": "info",
        "enabled": True,
    }
    rules = [
        monitor_rules.normalize(
            {
                **base,
                "id": "frt_simple_cross_prev_close",
                "name": "首板观察 · 价格上穿昨收",
                "conditions": [
                    {"field": "signal_intraday_zero_cross_up", "op": "truth"},
                ],
            }
        ),
        monitor_rules.normalize(
            {
                **base,
                "id": "frt_simple_cross_vwap",
                "name": "首板观察 · 价格上穿VWAP",
                "conditions": [
                    {"field": "signal_intraday_avg_cross_up", "op": "truth"},
                ],
            }
        ),
    ]
    for rule in rules:
        monitor_rules.validate(rule)
    return rules


class FirstBoardRightTailService:
    def __init__(
        self,
        repository: Any | None,
        data_dir: Path,
        *,
        store: FirstBoardRightTailStore | None = None,
        market_data: Any | None = None,
        enriched_panel: Any | None = None,
    ) -> None:
        fallback_market, fallback_enriched = repository_read_adapters(repository) if repository is not None else (None, None)
        self.market_data = market_data or fallback_market
        self.enriched_panel = enriched_panel or fallback_enriched
        if self.market_data is None or self.enriched_panel is None:
            raise TypeError("market_data and enriched_panel are required")
        self.repository = self.market_data
        self.data_dir = data_dir
        self.store = store or FirstBoardRightTailStore(data_dir)
        self._lock = threading.RLock()
        self._state = self.store.load()
        self._last_bucket: str | None = None
        self._screen_cache: tuple[float, date, dict[str, Any]] | None = None

    def load_state(self) -> dict[str, Any]:
        with self._lock:
            self._state = self.store.load()
            return deepcopy(self._state)

    def _save(self) -> None:
        self.store.save(self._state)

    def screen_latest(self, as_of: date | None = None) -> dict[str, Any]:
        target = as_of or self.enriched_panel.latest_date("stock")
        if target is None:
            target = self.market_data.latest_daily_date()
        if target is None:
            raise ValueError("本地没有可用日线日期")
        with self._lock:
            if self._screen_cache is not None:
                cached_at, cached_date, result = self._screen_cache
                if cached_date == target and datetime.now().timestamp() - cached_at < 60:
                    return deepcopy(result)
        instruments = self.market_data.get_instruments("stock")
        if instruments.is_empty() or "symbol" not in instruments.columns:
            raise ValueError("股票维表不可用")
        symbols = [
            str(symbol)
            for symbol in instruments["symbol"].to_list()
            if symbol and str(symbol).startswith(("60", "00"))
        ]
        daily = self.market_data.get_daily_batch(
            symbols,
            target - timedelta(days=120),
            target,
            columns=[
                "symbol",
                "date",
                "close",
                "high",
                "low",
                "raw_close",
                "raw_high",
                "raw_low",
                "volume",
                "amount",
                "consecutive_limit_ups",
            ],
        )
        result = screen_first_boards(
            daily,
            instruments,
            self.market_data.get_st_history(),
            as_of=target,
        )
        result["algorithm_version"] = ALGORITHM_VERSION
        with self._lock:
            self._screen_cache = (datetime.now().timestamp(), target, deepcopy(result))
        return result

    def import_latest(self, as_of: date | None = None) -> dict[str, Any]:
        screened = self.screen_latest(as_of)
        with self._lock:
            existing = {
                str(event["event_id"]): event
                for event in self._state.get("events", [])
            }
            imported = 0
            for candidate in screened["candidates"]:
                event_id = str(candidate["event_id"])
                if event_id in existing:
                    continue
                existing[event_id] = {
                    **candidate,
                    "status": "WATCH",
                    "watch_day": 0,
                    "triggered_rules": [],
                    "blocked_rules": [],
                    "blocked_rule_signal_times": {},
                    "one_word_locked_dates": [],
                    "pending": None,
                    "entry_price_raw": None,
                    "entry_price_adj": None,
                    "entry_time": None,
                    "fill_time": None,
                    "trigger_rule": None,
                    "drop_reason": None,
                    "risk_alerted": False,
                    "created_at": datetime.now(CN_TZ).isoformat(),
                    "updated_at": datetime.now(CN_TZ).isoformat(),
                }
                imported += 1
            self._state["events"] = list(existing.values())
            self._state["data_as_of"] = screened["as_of"]
            self._save()
            return {
                "imported": imported,
                "total": len(self._state["events"]),
                "event_date": screened.get("event_date"),
                "excluded": screened.get("excluded", {}),
            }

    def remove_event(self, event_id: str) -> bool:
        with self._lock:
            before = len(self._state.get("events", []))
            self._state["events"] = [
                event for event in self._state.get("events", [])
                if str(event.get("event_id")) != event_id
            ]
            changed = len(self._state["events"]) != before
            if changed:
                self._save()
            return changed

    def reset_event(self, event_id: str) -> bool:
        with self._lock:
            for event in self._state.get("events", []):
                if str(event.get("event_id")) != event_id:
                    continue
                event.update(
                    {
                        "status": "WATCH",
                        "watch_day": 0,
                        "triggered_rules": [],
                        "blocked_rules": [],
                        "blocked_rule_signal_times": {},
                        "one_word_locked_dates": [],
                        "pending": None,
                        "entry_price_raw": None,
                        "entry_price_adj": None,
                        "entry_time": None,
                        "fill_time": None,
                        "trigger_rule": None,
                        "drop_reason": None,
                        "risk_alerted": False,
                        "updated_at": datetime.now(CN_TZ).isoformat(),
                    }
                )
                self._save()
                return True
        return False

    def watched_symbols(self) -> frozenset[str]:
        with self._lock:
            return frozenset(
                str(event["symbol"])
                for event in self._state.get("events", [])
                if event.get("status") in WATCHING_STATUSES and event.get("symbol")
            )

    def overview(self) -> dict[str, Any]:
        state = self.load_state()
        events = state.get("events", [])
        from app.services import preferences

        runtime = dict(state.get("runtime", {}))
        runtime["realtime_enabled"] = preferences.get_realtime_quotes_enabled()
        runtime["quote_interval"] = preferences.get_realtime_quote_interval()
        summary = {
            "total": len(events),
            "watching": sum(event.get("status") == "WATCH" for event in events),
            "pending": sum(event.get("status") == "BUY_PENDING" for event in events),
            "filled": sum(event.get("status") == "FILLED" for event in events),
            "dropped": sum(event.get("status") == "DROPPED" for event in events),
        }
        return {
            "as_of": state.get("data_as_of"),
            "algorithm_version": ALGORITHM_VERSION,
            "summary": summary,
            "events": events,
            "runtime": runtime,
            "rules": RULE_DESCRIPTIONS,
            "simple_rule_ids": [
                "frt_simple_cross_prev_close",
                "frt_simple_cross_vwap",
            ],
        }

    def evaluate_now(self) -> list[dict[str, Any]]:
        frame, _ = self.enriched_panel.latest("stock")
        if frame.is_empty():
            return []
        fields = [
            column
            for column in ("symbol", "name", "close", "raw_close", "change_pct")
            if column in frame.columns
        ]
        quotes = frame.select(fields).iter_rows(named=True)
        return self.on_quote_update(datetime.now(CN_TZ), quotes, force=True)

    def on_quote_update(
        self,
        observed_at: datetime,
        quotes: Iterable[dict[str, Any]],
        *,
        force: bool = False,
    ) -> list[dict[str, Any]]:
        observed = _naive_cn(observed_at)
        bucket = observed.strftime("%Y%m%d%H%M")
        with self._lock:
            if not force and self._last_bucket == bucket:
                return []
            self._last_bucket = bucket
            state = deepcopy(self._state)
            active = [
                event for event in state.get("events", [])
                if event.get("status") in WATCHING_STATUSES
            ]
            if not active:
                return []
        quote_map = {
            str(row.get("symbol")): dict(row)
            for row in quotes
            if row.get("symbol")
        }
        symbols = sorted({str(event["symbol"]) for event in active})
        minute = self.market_data.get_minute_batch(symbols, observed.date())
        event_days = [
            date.fromisoformat(str(event["event_date"]))
            for event in active
        ]
        range_start = min(event_days) + timedelta(days=1)
        minute_dates = self.market_data.list_minute_dates(range_start, observed.date())
        events: list[dict[str, Any]] = []
        if minute.is_empty():
            state.setdefault("runtime", {}).update(
                {
                    "last_evaluation": observed.isoformat(),
                    "minute_status": "unavailable",
                    "minute_last_time": None,
                    "active_symbols": len(symbols),
                }
            )
            with self._lock:
                self._state = state
                self._save()
            return []

        auction_by_symbol = self._load_auction(observed.date())
        by_symbol = {
            str(part["symbol"][0]): part.sort("datetime")
            for part in minute.partition_by("symbol", maintain_order=True)
        }
        for event in active:
            symbol = str(event["symbol"])
            bars = by_symbol.get(symbol)
            quote = quote_map.get(symbol, {})
            if bars is None or bars.is_empty():
                event["data_status"] = "minute_missing"
                continue
            event_day = date.fromisoformat(str(event["event_date"]))
            watch_dates = [
                day for day in minute_dates
                if event_day < day <= observed.date()
            ]
            if observed.date() not in watch_dates and observed.date() > event_day:
                watch_dates.append(observed.date())
            event["watch_day"] = len(watch_dates)
            event["last_observed_at"] = observed.isoformat()
            event["last_price_raw"] = quote.get("raw_close") or quote.get("close")
            event["last_price_adj"] = quote.get("close")
            event["change_pct"] = quote.get("change_pct")
            event["data_status"] = "ok"

            if event["watch_day"] > 5 and event.get("status") != "FILLED":
                event["status"] = "DROPPED"
                event["drop_reason"] = "观察超过5个交易日"
                events.append(self._alert(event, "drop", event["drop_reason"], observed))
                continue

            five = aggregate_five_minutes(bars)
            locked = self._one_word_locked(bars, quote)
            locked_dates = event["one_word_locked_dates"]
            if locked and observed.date().isoformat() not in locked_dates:
                locked_dates.append(observed.date().isoformat())
            previous_watch_date = watch_dates[-2] if len(watch_dates) >= 2 else None
            consecutive_lock = (
                locked
                and previous_watch_date is not None
                and previous_watch_date.isoformat() in locked_dates
                and observed.date().isoformat() in locked_dates
            )
            if consecutive_lock and event.get("status") != "FILLED":
                event["status"] = "DROPPED"
                event["drop_reason"] = "连续一字板且无可成交开板"
                events.append(self._alert(event, "drop", event["drop_reason"], observed))
                continue
            if not locked:
                locked_dates.clear()

            if event.get("status") != "FILLED":
                abandon = (
                    not five.is_empty()
                    and float(five["close"][-1]) <= float(event["t_close_adj"]) * 0.94
                )
                if abandon:
                    event["status"] = "DROPPED"
                    event["drop_reason"] = "自T日收盘回撤达到6%"
                    event["pending"] = None
                    events.append(self._alert(event, "drop", event["drop_reason"], observed))
                    continue

            if event.get("status") == "BUY_PENDING":
                fill_event = self._try_fill(event, bars, quote)
                if fill_event is not None:
                    events.append(fill_event)

            if event.get("status") == "WATCH":
                candidates = evaluate_intraday_rules(
                    event,
                    bars,
                    auction=auction_by_symbol.get(symbol),
                    decision_day=int(event["watch_day"]),
                )
                for candidate in candidates:
                    if candidate.rule in event["triggered_rules"]:
                        continue
                    blocked_at = event.get("blocked_rule_signal_times", {}).get(candidate.rule)
                    if blocked_at and candidate.signal_time.isoformat() <= blocked_at:
                        continue
                    event["triggered_rules"].append(candidate.rule)
                    event["status"] = "BUY_PENDING"
                    event["trigger_rule"] = candidate.rule
                    event["pending"] = {
                        "rule": candidate.rule,
                        "signal_time": candidate.signal_time.isoformat(),
                        "order_time": candidate.order_time.isoformat(),
                        "signal_price_adj": candidate.price_adj,
                        "reason": candidate.reason,
                    }
                    events.append(
                        self._alert(
                            event,
                            "buy_trigger",
                            f"{candidate.rule}组触发：{candidate.reason}；等待下一分钟开盘确认，不是当前价成交",
                            observed,
                        )
                    )
                    fill_event = self._try_fill(event, bars, quote)
                    if fill_event is not None:
                        events.append(fill_event)
                    break

            if event.get("status") == "FILLED" and not event.get("risk_alerted"):
                entry = event.get("entry_price_raw")
                current = quote.get("raw_close") or quote.get("close")
                if entry and current and float(current) <= float(entry) * 0.94:
                    event["risk_alerted"] = True
                    events.append(
                        self._alert(
                            event,
                            "risk_stop",
                            "价格已到-6%风险线；若跳空则按下一可成交价处理，禁止按理想止损价假设成交",
                            observed,
                            severity="critical",
                        )
                    )

        state.setdefault("runtime", {}).update(
            {
                "last_evaluation": observed.isoformat(),
                "minute_status": "ok",
                "minute_last_time": minute["datetime"].max().isoformat(),
                "active_symbols": len(symbols),
                "auction_symbols": len(auction_by_symbol),
                "d_available": bool(auction_by_symbol),
            }
        )
        with self._lock:
            self._state = state
            self._save()
        return events

    def _try_fill(
        self,
        event: dict[str, Any],
        bars: pl.DataFrame,
        quote: dict[str, Any],
    ) -> dict[str, Any] | None:
        pending = event.get("pending") or {}
        order_time = pending.get("order_time")
        if not order_time:
            return None
        target_time = datetime.fromisoformat(str(order_time))
        fill_rows = bars.filter(pl.col("datetime") >= target_time)
        if fill_rows.is_empty():
            return None
        bar = fill_rows.row(0, named=True)
        if float(bar.get("volume") or 0) <= 0:
            event["status"] = "WATCH"
            event["pending"] = None
            self._block_rule_attempt(event)
            return self._alert(
                event,
                "fill_blocked",
                "下一分钟无成交，触发作废，等待新的触发边沿",
                target_time,
            )
        if self._one_word_locked(bars, quote):
            event["status"] = "WATCH"
            event["pending"] = None
            self._block_rule_attempt(event)
            return self._alert(
                event,
                "fill_blocked",
                "涨停锁死，下一分钟开盘不可成交；等待开板后的新触发",
                target_time,
            )
        close = quote.get("close")
        raw_close = quote.get("raw_close")
        factor = (
            float(close) / float(raw_close)
            if close and raw_close and float(raw_close) > 0
            else 1.0
        )
        fill_open_adj = float(bar["open"])
        history = bars.filter(pl.col("datetime") < target_time).tail(20)
        capacity_warning = history.height < 20
        if not capacity_warning:
            average_amount = float(history["amount"].mean() or 0.0)
            if average_amount * 0.01 < 18_000.0:
                event["status"] = "WATCH"
                event["pending"] = None
                self._block_rule_attempt(event)
                return self._alert(
                    event,
                    "fill_blocked",
                    "订单金额超过前20分钟平均成交额的1%，不记为可成交",
                    target_time,
                )
        event["status"] = "FILLED"
        event["entry_price_adj"] = fill_open_adj
        event["entry_price_raw"] = fill_open_adj / factor
        event["entry_time"] = target_time.isoformat()
        event["fill_time"] = bar["datetime"].isoformat()
        event["pending"] = None
        event["capacity_warning"] = capacity_warning
        return self._alert(
            event,
            "buy_fill",
            f"{event.get('trigger_rule')}组信号已按下一分钟开盘确认；参考成交价 {event['entry_price_raw']:.3f}元",
            bar["datetime"],
        )

    @staticmethod
    def _block_rule_attempt(event: dict[str, Any]) -> None:
        rule = str(event.get("trigger_rule") or "")
        if not rule:
            return
        if rule not in event["blocked_rules"]:
            event["blocked_rules"].append(rule)
        pending = event.get("pending") or {}
        signal_time = pending.get("signal_time")
        if signal_time:
            event.setdefault("blocked_rule_signal_times", {})[rule] = signal_time
        if rule in event["triggered_rules"]:
            event["triggered_rules"].remove(rule)

    def _one_word_locked(self, bars: pl.DataFrame, quote: dict[str, Any]) -> bool:
        if bars.is_empty():
            return False
        if bars.filter(
            (pl.col("high") - pl.col("low")).abs() > 1e-8
        ).height:
            return False
        close = quote.get("raw_close") or quote.get("close")
        change_pct = quote.get("change_pct")
        if close is None or change_pct is None or float(change_pct) <= -1:
            return False
        previous = float(close) / (1.0 + float(change_pct))
        limit = _limit_price(previous)
        return limit is not None and float(bars["close"][-1]) >= limit - 0.005

    def _load_auction(self, trade_date: date) -> dict[str, dict[str, float]]:
        live_root = self.data_dir / "ext_data" / "auction_result_live" / "timeseries"
        legacy_root = self.data_dir / "ext_data" / "auction_result" / "timeseries"
        required = {"symbol", "auction_open", "opening_gap", "volume_shares", "has_result"}
        current = None
        for root in (live_root, legacy_root):
            path = root / f"date={trade_date.isoformat()}" / "part.parquet"
            if not path.exists():
                continue
            try:
                frame = pl.read_parquet(path)
            except Exception:  # noqa: BLE001
                continue
            if not required.issubset(frame.columns):
                continue
            frame = frame.filter(pl.col("has_result") == 1)
            if not frame.is_empty():
                current = frame
                break
        if current is None:
            return {}

        # 新实时表从启用日开始积累；已有归档表是同口径历史，可立即补齐
        # D 规则所需的 5 日竞价量基准。同日优先实时表。
        history_by_date: dict[date, Path] = {}
        for root in (legacy_root, live_root):
            for path in root.glob("date=*/part.parquet"):
                try:
                    day = date.fromisoformat(path.parent.name.removeprefix("date="))
                except ValueError:
                    continue
                if day < trade_date:
                    history_by_date[day] = path
        history_paths = [
            history_by_date[day] for day in sorted(history_by_date)[-5:]
        ]
        if len(history_paths) < 5 or current.is_empty():
            return {}
        frames: list[pl.DataFrame] = []
        for path in history_paths:
            try:
                frames.append(pl.read_parquet(path, columns=["symbol", "volume_shares"]))
            except Exception:  # noqa: BLE001
                continue
        if len(frames) < 5:
            return {}
        history = pl.concat(frames, how="vertical")
        averages = history.group_by("symbol").agg(
            pl.col("volume_shares").mean().alias("_average_volume")
        )
        current = current.join(averages, on="symbol", how="left").with_columns(
            pl.when(pl.col("_average_volume") > 0)
            .then(pl.col("volume_shares") / pl.col("_average_volume"))
            .otherwise(None)
            .alias("_volume_ratio")
        )
        return {
            str(row["symbol"]): {
                "auction_price": float(row["auction_open"]),
                "opening_gap": float(row["opening_gap"]),
                "volume_ratio": float(row["_volume_ratio"]),
            }
            for row in current.iter_rows(named=True)
            if row.get("_volume_ratio") is not None
        }

    @staticmethod
    def _alert(
        event: dict[str, Any],
        alert_type: str,
        message: str,
        observed: datetime,
        *,
        severity: str = "warn",
    ) -> dict[str, Any]:
        return {
            "ts": int(observed.timestamp() * 1000),
            "rule_id": f"frt_{event['event_id']}",
            "source": SOURCE,
            "type": alert_type,
            "symbol": event["symbol"],
            "name": event.get("name"),
            "message": message,
            "price": event.get("last_price_raw"),
            "change_pct": event.get("change_pct"),
            "signals": [event["trigger_rule"]] if event.get("trigger_rule") else [],
            "severity": severity,
            "conditions": [],
            "logic": "and",
        }
