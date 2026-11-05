"""Theme analysis computed from the stable market-data read contract."""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any

import polars as pl

from app.extensions.contracts import MarketDataRead

from .store import SYMBOL_RE, normalize_symbols

BENCH_PREF: dict[str, tuple[str, ...]] = {
    "SH": ("000002.SH", "000001.SH"),
    "STAR": ("000688.SH", "000002.SH"),
    "SZ": ("399107.SZ", "399001.SZ"),
    "GEM": ("399102.SZ", "399107.SZ"),
    "BJ": ("899050.BJ", "000001.SH"),
}
BENCH_SYMBOLS = {symbol for values in BENCH_PREF.values() for symbol in values}
INDEX_SERIES_SYMBOL = "000001.SH"
DEFAULT_WINDOW_TRADING_DAYS = 60
LOOKBACK_CALENDAR_DAYS = 120
MINUTE_SAMPLE_LIMIT = 12
EVENT_COLUMNS = [
    "trade_date",
    "symbol",
    "name",
    "in_limit_up_pool",
    "in_limit_break_pool",
    "continue_day_cnt",
    "limit_up_reason",
    "limit_up_time",
    "first_seal_time",
    "last_seal_time",
    "limit_up_pool_open_times",
    "break_pool_open_times",
    "seal_money",
]


def benchmark_key(symbol: str) -> str:
    code = symbol.split(".", 1)[0]
    if symbol.endswith(".BJ") or code[:2] in {"43", "83", "87", "92"}:
        return "BJ"
    if symbol.endswith(".SH"):
        return "STAR" if code.startswith("68") else "SH"
    if symbol.endswith(".SZ"):
        return "GEM" if code.startswith("30") else "SZ"
    return "SH"


def _ratio(value: float | None) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(float(value), 6)


def _pct(value: float | None) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(float(value) * 100.0, 2)


def _round(value: float | None, digits: int = 2) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(float(value), digits)


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and len(value) >= 10:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _frame_rows_by_symbol(frame: pl.DataFrame) -> dict[str, list[dict[str, Any]]]:
    if frame.is_empty() or "symbol" not in frame.columns:
        return {}
    result: dict[str, list[dict[str, Any]]] = {}
    for row in frame.sort(["symbol", "date"]).iter_rows(named=True):
        result.setdefault(str(row["symbol"]), []).append(row)
    return result


def _dataframe_from_rows(rows: list[dict[str, Any]]) -> pl.DataFrame:
    return pl.DataFrame(rows) if rows else pl.DataFrame()


class ThemeAnalyzerService:
    def __init__(self, market_data: MarketDataRead) -> None:
        self.market_data = market_data
        self._instrument_cache: pl.DataFrame | None = None

    def _instruments(self) -> pl.DataFrame:
        if self._instrument_cache is None:
            try:
                self._instrument_cache = self.market_data.get_instruments("stock")
            except Exception:  # noqa: BLE001 - caller degrades to symbol labels
                self._instrument_cache = pl.DataFrame()
        return self._instrument_cache

    def names(self, symbols: list[str]) -> dict[str, str]:
        frame = self._instruments()
        if frame.is_empty() or "symbol" not in frame.columns or "name" not in frame.columns:
            return {symbol: symbol for symbol in symbols}
        wanted = set(symbols)
        result: dict[str, str] = {}
        for row in frame.select(
            pl.col("symbol").cast(pl.Utf8),
            pl.col("name").cast(pl.Utf8),
        ).iter_rows(named=True):
            symbol = str(row["symbol"])
            if symbol in wanted:
                result[symbol] = str(row["name"])
        return {symbol: result.get(symbol, symbol) for symbol in symbols}

    def validate_symbols(self, symbols: list[str]) -> list[str]:
        malformed = [
            str(raw).strip()
            for raw in symbols
            if not SYMBOL_RE.fullmatch(str(raw or "").strip().upper())
        ]
        if malformed:
            shown = "、".join(malformed[:5])
            suffix = " 等" if len(malformed) > 5 else ""
            raise ValueError(f"标的代码格式无效: {shown}{suffix}")
        normalized = normalize_symbols(symbols)
        if not normalized:
            return []
        frame = self._instruments()
        if frame.is_empty() or "symbol" not in frame.columns:
            return normalized
        universe = set(frame["symbol"].cast(pl.Utf8).to_list())
        missing = [symbol for symbol in normalized if symbol not in universe]
        if missing:
            shown = "、".join(missing[:5])
            suffix = " 等" if len(missing) > 5 else ""
            raise ValueError(f"以下标的不在股票维表中: {shown}{suffix}")
        return normalized

    def analyze(
        self,
        theme: dict[str, Any],
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> dict[str, Any]:
        symbols = normalize_symbols(theme.get("symbols") or [])
        names = self.names(symbols)
        latest_daily = self._latest_daily_date()
        resolved_end = min(end, latest_daily) if end and latest_daily else (end or latest_daily)
        if resolved_end is None:
            return self._empty_payload(theme, symbols, names, start, end)

        trading_dates: list[date] = []
        try:
            trading_dates = self.market_data.list_trading_dates(
                resolved_end - timedelta(days=LOOKBACK_CALENDAR_DAYS * 2),
                resolved_end,
            )
        except Exception:  # noqa: BLE001 - daily frame dates are the fallback
            trading_dates = []
        resolved_start = start
        if resolved_start is None:
            if len(trading_dates) > DEFAULT_WINDOW_TRADING_DAYS:
                resolved_start = trading_dates[-DEFAULT_WINDOW_TRADING_DAYS]
            elif trading_dates:
                resolved_start = trading_dates[0]
            else:
                resolved_start = resolved_end - timedelta(days=90)
        if resolved_start > resolved_end:
            resolved_start, resolved_end = resolved_end, resolved_start
        if not symbols:
            return self._empty_payload(theme, symbols, names, resolved_start, resolved_end)

        load_start = resolved_start - timedelta(days=LOOKBACK_CALENDAR_DAYS)
        daily = self._load_daily(
            symbols,
            load_start,
            resolved_end,
            columns=["symbol", "date", "open", "high", "low", "close", "volume", "amount"],
        )
        if daily.is_empty():
            return self._empty_payload(
                theme,
                symbols,
                names,
                resolved_start,
                resolved_end,
                latest_daily=resolved_end,
            )

        daily = daily.with_columns(
            pl.col("symbol").cast(pl.Utf8),
            pl.col("date").cast(pl.Date),
        ).sort(["symbol", "date"])
        available_dates = sorted(set(daily["date"].to_list()))
        window_dates = [day for day in available_dates if resolved_start <= day <= resolved_end]
        if not window_dates:
            return self._empty_payload(
                theme,
                symbols,
                names,
                resolved_start,
                resolved_end,
                latest_daily=resolved_end,
            )

        index_daily = self._load_index_daily(load_start, resolved_end)
        bench_map = self._benchmark_map(index_daily)
        window_start_index = available_dates.index(window_dates[0])
        route_context_start = available_dates[max(0, window_start_index - 30)]
        route_events = self._load_events(route_context_start, resolved_end)
        if not route_events.is_empty() and "symbol" in route_events.columns:
            if route_events.schema.get("trade_date") == pl.String:
                route_events = route_events.with_columns(
                    pl.col("trade_date").str.to_date(),
                )
            route_events = route_events.filter(pl.col("symbol").is_in(symbols))
        window_events = (
            route_events.filter(
                pl.col("trade_date").is_between(resolved_start, resolved_end),
            )
            if not route_events.is_empty()
            else route_events
        )
        event_map = self._event_markers(window_events)
        active_symbols = (
            sorted(set(window_events["symbol"].cast(pl.Utf8).to_list()))
            if not window_events.is_empty()
            else []
        )
        active_set = set(active_symbols)
        rows_by_symbol = _frame_rows_by_symbol(daily)

        leaders: list[dict[str, Any]] = []
        heat_rows: list[dict[str, Any]] = []
        for symbol in symbols:
            symbol_rows = rows_by_symbol.get(symbol, [])
            if not symbol_rows:
                continue
            summary, heat = self._summarize_symbol(
                symbol,
                names.get(symbol, symbol),
                symbol_rows,
                window_dates,
                bench_map,
                event_map,
                active_set,
            )
            leaders.append(summary)
            heat_rows.append(heat)

        leaders.sort(
            key=lambda row: (
                row.get("max_ret_30") is None,
                -(row.get("max_ret_30") or 0.0),
                row.get("max_ret_10") is None,
                -(row.get("max_ret_10") or 0.0),
                -(row.get("max_ret_3") or 0.0),
            )
        )
        heat_order = {row["symbol"]: index for index, row in enumerate(leaders)}
        heat_rows.sort(key=lambda row: heat_order.get(row["symbol"], 10_000))

        index_payload = self._equal_weight_index(
            rows_by_symbol,
            window_dates,
            all_dates=available_dates,
            active_symbols=active_set,
        )
        index_payload["sh"] = self._benchmark_series(index_daily, INDEX_SERIES_SYMBOL, window_dates)
        breadth = self._breadth(window_events, window_dates)
        latest_event_date = self._latest_event_date(resolved_end)
        latest_limit = self._latest_limit_payload(
            symbols,
            names,
            window_events,
            latest_event_date,
            resolved_end,
        )
        minute_dates = self._minute_dates(resolved_start, resolved_end)
        limit_route = self._limit_route(
            route_events,
            leaders,
            names,
            window_dates,
            minute_dates,
            available_dates,
        )
        sh_return = _ratio(
            (index_payload["sh"][-1] / 100.0 - 1) if index_payload["sh"] and index_payload["sh"][-1] is not None else None
        )
        pool_last = index_payload["pool"][-1] if index_payload["pool"] else None
        active_last = index_payload["active"][-1] if index_payload["active"] else None

        return {
            "theme_id": theme["id"],
            "theme_name": theme["name"],
            "as_of": resolved_end.isoformat(),
            "window_start": resolved_start.isoformat(),
            "window_end": resolved_end.isoformat(),
            "default_window_days": DEFAULT_WINDOW_TRADING_DAYS,
            "pool_count": len(symbols),
            "quoted_count": len(leaders),
            "active_count": len(active_set),
            "active_return": _ratio(active_last / 100.0 - 1) if active_last is not None else None,
            "pool_return": _ratio(pool_last / 100.0 - 1) if pool_last is not None else None,
            "sh_return": sh_return,
            "latest_minute_date": minute_dates[-1].isoformat() if minute_dates else None,
            "minute_dates": [day.isoformat() for day in minute_dates],
            "leaders": leaders,
            "index": index_payload,
            "heatmap": {
                "dates": [day.isoformat() for day in window_dates],
                "rows": heat_rows,
            },
            "breadth": breadth,
            "seal": latest_limit,
            "limit_route": limit_route,
        }

    def minute_overlay(
        self,
        theme: dict[str, Any],
        trade_date: date,
        symbols: list[str] | None = None,
    ) -> dict[str, Any]:
        theme_symbols = normalize_symbols(theme.get("symbols") or [])
        selected = normalize_symbols(symbols or [])[:MINUTE_SAMPLE_LIMIT]
        if not selected:
            selected = theme_symbols[:MINUTE_SAMPLE_LIMIT]
        if not selected:
            return {
                "theme_id": theme["id"],
                "date": trade_date.isoformat(),
                "status": "empty",
                "stocks": [],
                "times": [],
                "series": {},
                "table": {"times": [], "series": {}},
                "features": {},
                "missing": [],
            }
        names = self.names(selected)
        try:
            minute_dates = self.market_data.list_minute_dates(trade_date, trade_date)
        except Exception:  # noqa: BLE001 - empty response below
            minute_dates = []
        if trade_date not in minute_dates:
            return {
                "theme_id": theme["id"],
                "date": trade_date.isoformat(),
                "status": "no_data",
                "stocks": [
                    {"symbol": symbol, "name": names.get(symbol, symbol)}
                    for symbol in selected
                ],
                "times": [],
                "series": {},
                "table": {"times": [], "series": {}},
                "features": {},
                "missing": selected,
            }

        try:
            minute = self.market_data.get_minute_batch(selected, trade_date)
        except Exception:  # noqa: BLE001 - empty response below
            minute = pl.DataFrame()
        if minute.is_empty():
            return {
                "theme_id": theme["id"],
                "date": trade_date.isoformat(),
                "status": "no_data",
                "stocks": [
                    {"symbol": symbol, "name": names.get(symbol, symbol)}
                    for symbol in selected
                ],
                "times": [],
                "series": {},
                "table": {"times": [], "series": {}},
                "features": {},
                "missing": selected,
            }

        minute = minute.with_columns(pl.col("symbol").cast(pl.Utf8))
        daily = self._load_daily(
            selected,
            trade_date - timedelta(days=45),
            trade_date - timedelta(days=1),
            columns=["symbol", "date", "close"],
        )
        prev_close: dict[str, float] = {}
        if not daily.is_empty():
            for symbol, group in daily.sort(["symbol", "date"]).group_by("symbol", maintain_order=True):
                symbol_key = symbol[0] if isinstance(symbol, tuple) else symbol
                values = group["close"].drop_nulls().to_list()
                if values:
                    prev_close[str(symbol_key)] = float(values[-1])

        all_times = sorted({
            _minute_time(value)
            for value in minute["datetime"].to_list()
            if _minute_time(value) is not None
        })
        series: dict[str, list[float | None]] = {}
        table_series: dict[str, list[float | None]] = {}
        features: dict[str, dict[str, Any]] = {}
        missing: list[str] = []
        table_times = _table_times(all_times)

        by_symbol: dict[str, pl.DataFrame] = {}
        for symbol, group in minute.group_by("symbol", maintain_order=True):
            symbol_key = symbol[0] if isinstance(symbol, tuple) else symbol
            by_symbol[str(symbol_key)] = group.sort("datetime")
        for symbol in selected:
            group = by_symbol.get(symbol)
            base = prev_close.get(symbol)
            if group is None or group.is_empty() or not base:
                missing.append(symbol)
                series[symbol] = [None for _ in all_times]
                table_series[symbol] = [None for _ in table_times]
                continue
            time_price: dict[str, float] = {}
            for row in group.iter_rows(named=True):
                time_key = _minute_time(row.get("datetime"))
                close = row.get("close")
                if time_key is not None and close is not None:
                    time_price[time_key] = float(close)
            series[symbol] = [
                _round((time_price[time_key] / base - 1.0) * 100.0, 2)
                if time_key in time_price else None
                for time_key in all_times
            ]
            table_series[symbol] = [
                _round((time_price[time_key] / base - 1.0) * 100.0, 2)
                if time_key in time_price else None
                for time_key in table_times
            ]
            features[symbol] = self._minute_features(group, base)

        return {
            "theme_id": theme["id"],
            "date": trade_date.isoformat(),
            "status": "ok" if any(value is not None for value in features) else "no_data",
            "stocks": [
                {
                    "symbol": symbol,
                    "name": names.get(symbol, symbol),
                    "prev_close": _round(prev_close.get(symbol), 3),
                    "has_data": symbol not in missing,
                }
                for symbol in selected
            ],
            "times": all_times,
            "series": series,
            "table": {"times": table_times, "series": table_series},
            "features": features,
            "missing": missing,
        }

    def _load_index_daily(self, start: date, end: date) -> pl.DataFrame:
        frames: list[pl.DataFrame] = []
        try:
            dates = self.market_data.dataset_partition_dates("kline_index_daily", start, end)
        except Exception:  # noqa: BLE001 - optional benchmark
            return pl.DataFrame()
        for day in dates:
            try:
                frame = self.market_data.read_dataset_partition(
                    "kline_index_daily",
                    day,
                    ["symbol", "date", "close"],
                )
            except Exception:  # noqa: BLE001 - skip one bad partition
                continue
            if frame.is_empty() or "symbol" not in frame.columns:
                continue
            frames.append(frame.filter(pl.col("symbol").is_in(list(BENCH_SYMBOLS))))
        if not frames:
            return pl.DataFrame()
        return pl.concat(frames, how="diagonal_relaxed").with_columns(
            pl.col("symbol").cast(pl.Utf8),
            pl.col("date").cast(pl.Date),
        ).sort(["symbol", "date"])

    def _load_daily(
        self,
        symbols: list[str],
        start: date,
        end: date,
        *,
        columns: list[str],
    ) -> pl.DataFrame:
        """Read only the requested symbols from daily enriched partitions.

        ``get_daily_batch`` may synchronously build the core's 300-day enriched
        cache on a cold process. Analysis does not need that cache, so use the
        stable partition reader first and keep the batch API as a compatibility
        fallback for providers that do not expose daily partitions.
        """

        try:
            dates = self.market_data.dataset_partition_dates(
                "kline_daily_enriched",
                start,
                end,
            )
        except Exception:  # noqa: BLE001 - fallback below
            dates = []
        frames: list[pl.DataFrame] = []
        for day in dates:
            try:
                frame = self.market_data.read_dataset_partition(
                    "kline_daily_enriched",
                    day,
                    columns,
                )
            except Exception:  # noqa: BLE001 - try the full schema once
                try:
                    frame = self.market_data.read_dataset_partition(
                        "kline_daily_enriched",
                        day,
                    )
                except Exception:  # noqa: BLE001 - skip one bad partition
                    continue
                existing = [column for column in columns if column in frame.columns]
                frame = frame.select(existing) if existing else pl.DataFrame()
            if frame.is_empty() or "symbol" not in frame.columns:
                continue
            frames.append(frame.filter(pl.col("symbol").is_in(symbols)))
        if frames:
            result = pl.concat(frames, how="diagonal_relaxed")
            if not result.is_empty():
                return result.with_columns(
                    pl.col("symbol").cast(pl.Utf8),
                    pl.col("date").cast(pl.Date),
                ).sort(["symbol", "date"])
        try:
            return self.market_data.get_daily_batch(
                symbols,
                start,
                end,
                columns=columns,
            )
        except Exception:  # noqa: BLE001 - caller returns an explicit empty state
            return pl.DataFrame()

    def _latest_daily_date(self) -> date | None:
        """Use partition names first; DuckDB max(date) is slow on a cold process."""

        try:
            dates = self.market_data.dataset_partition_dates(
                "kline_daily_enriched",
                date(2000, 1, 1),
                date.today() + timedelta(days=1),
            )
            if dates:
                return dates[-1]
        except Exception:  # noqa: BLE001 - compatibility fallback below
            pass
        try:
            return self.market_data.latest_daily_date()
        except Exception:  # noqa: BLE001 - no daily data available
            return None

    def _load_events(self, start: date, end: date) -> pl.DataFrame:
        try:
            dates = self.market_data.dataset_partition_dates(
                "ext_data/limit_board_events/timeseries",
                start,
                end,
            )
        except Exception:  # noqa: BLE001 - optional event overlay
            return pl.DataFrame()
        frames: list[pl.DataFrame] = []
        for day in dates:
            try:
                frame = self.market_data.read_dataset_partition(
                    "ext_data/limit_board_events/timeseries",
                    day,
                )
            except Exception:  # noqa: BLE001 - skip one bad partition
                continue
            if frame.is_empty() or "symbol" not in frame.columns:
                continue
            columns = [column for column in EVENT_COLUMNS if column in frame.columns]
            if not {"trade_date", "symbol"}.issubset(columns):
                continue
            frames.append(frame.select(columns))
        if not frames:
            return pl.DataFrame()
        return pl.concat(frames, how="diagonal_relaxed").with_columns(
            pl.col("symbol").cast(pl.Utf8),
        )

    def _benchmark_map(
        self,
        index_daily: pl.DataFrame,
    ) -> dict[str, dict[date, float]]:
        result: dict[str, dict[date, float]] = {}
        if index_daily.is_empty():
            return result
        for symbol, group in index_daily.group_by("symbol", maintain_order=True):
            symbol_key = symbol[0] if isinstance(symbol, tuple) else symbol
            series: dict[date, float] = {}
            for row in group.iter_rows(named=True):
                day = _as_date(row.get("date"))
                close = row.get("close")
                if day is not None and close is not None:
                    series[day] = float(close)
            result[str(symbol_key)] = series
        return result

    def _benchmark_for(
        self,
        symbol: str,
        bench_map: dict[str, dict[date, float]],
    ) -> dict[date, float]:
        for candidate in BENCH_PREF[benchmark_key(symbol)]:
            series = bench_map.get(candidate)
            if series:
                return series
        return {}

    def _summarize_symbol(
        self,
        symbol: str,
        name: str,
        rows: list[dict[str, Any]],
        window_dates: list[date],
        bench_map: dict[str, dict[date, float]],
        event_map: dict[tuple[str, date], str],
        active_set: set[str],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        dates = [_as_date(row.get("date")) for row in rows]
        closes = [float(row["close"]) if row.get("close") is not None else None for row in rows]
        highs = [float(row["high"]) if row.get("high") is not None else None for row in rows]
        lows = [float(row["low"]) if row.get("low") is not None else None for row in rows]
        trading_positions = {day: index for index, day in enumerate(window_dates)}
        date_index = {day: index for index, day in enumerate(dates) if day is not None}
        benchmark = self._benchmark_for(symbol, bench_map)
        summary: dict[str, Any] = {
            "symbol": symbol,
            "name": name,
            "active": symbol in active_set,
            "last_date": dates[-1].isoformat() if dates and dates[-1] is not None else None,
            "last_close": _round(closes[-1], 3) if closes and closes[-1] is not None else None,
        }

        for window in (3, 10, 30):
            best: float | None = None
            best_date: date | None = None
            best_high: float | None = None
            best_high_date: date | None = None
            for index, day in enumerate(dates):
                if day is None or day < window_dates[0] or day > window_dates[-1]:
                    continue
                trading_index = trading_positions.get(day)
                if trading_index is None or trading_index < window:
                    continue
                base_index = date_index.get(window_dates[trading_index - window])
                if base_index is None or base_index >= index:
                    continue
                base = closes[base_index]
                close = closes[index]
                high = highs[index]
                if not base or close is None:
                    continue
                ret = close / base - 1.0
                if best is None or ret > best:
                    best, best_date = ret, day
                if high is not None:
                    high_ret = high / base - 1.0
                    if best_high is None or high_ret > best_high:
                        best_high, best_high_date = high_ret, day
            latest_index = date_index.get(window_dates[-1])
            latest_trading_index = trading_positions.get(window_dates[-1])
            latest_base_index = (
                date_index.get(window_dates[latest_trading_index - window])
                if latest_trading_index is not None and latest_trading_index >= window
                else None
            )
            latest_ret = (
                closes[latest_index] / closes[latest_base_index] - 1.0
                if latest_index is not None
                and latest_base_index is not None
                and closes[latest_index] is not None
                and closes[latest_base_index]
                else None
            )
            summary[f"max_ret_{window}"] = _ratio(best)
            summary[f"max_ret_{window}_date"] = best_date.isoformat() if best_date else None
            summary[f"max_high_ret_{window}"] = _ratio(best_high)
            summary[f"max_high_ret_{window}_date"] = (
                best_high_date.isoformat() if best_high_date else None
            )
            summary[f"latest_ret_{window}"] = _ratio(latest_ret)

        heat_values: list[float | None] = []
        active_values: list[float] = []
        close_positions: list[float] = []
        for day in window_dates:
            index = date_index.get(day)
            if index is None or index == 0 or closes[index] is None or closes[index - 1] is None:
                heat_values.append(None)
                continue
            stock_ret = closes[index] / closes[index - 1] - 1.0
            previous_day = dates[index - 1]
            bench_ret = None
            if previous_day is not None and day in benchmark and previous_day in benchmark:
                bench_ret = benchmark[day] / benchmark[previous_day] - 1.0
            deviation = stock_ret - bench_ret if bench_ret is not None else None
            heat_values.append(_ratio(deviation))
            if deviation is not None:
                active_values.append(deviation)
            high = highs[index]
            low = lows[index]
            close = closes[index]
            if high is not None and low is not None and close is not None and high > low:
                close_positions.append((close - low) / (high - low))

        summary["active_gt2"] = sum(1 for value in active_values if value > 0.02)
        summary["avg_deviate"] = (
            _ratio(sum(active_values) / len(active_values)) if active_values else None
        )
        summary["max_deviate"] = _ratio(max(active_values)) if active_values else None
        summary["avg_close_pos"] = (
            _ratio(sum(close_positions) / len(close_positions))
            if close_positions
            else None
        )
        summary["active_days"] = len(active_values)
        summary["event_count"] = sum(
            1 for day in window_dates if (symbol, day) in event_map
        )
        heat = {
            "symbol": symbol,
            "name": name,
            "active": symbol in active_set,
            "values": heat_values,
            "markers": [
                event_map.get((symbol, day), "") for day in window_dates
            ],
        }
        return summary, heat

    def _event_markers(self, events: pl.DataFrame) -> dict[tuple[str, date], str]:
        result: dict[tuple[str, date], str] = {}
        if events.is_empty():
            return result
        for row in events.iter_rows(named=True):
            day = _as_date(row.get("trade_date"))
            symbol = str(row.get("symbol") or "")
            if day is None or not symbol:
                continue
            if int(row.get("in_limit_up_pool") or 0) == 1:
                result[(symbol, day)] = "seal"
            elif int(row.get("in_limit_break_pool") or 0) == 1:
                result[(symbol, day)] = "broken"
        return result

    def _equal_weight_index(
        self,
        rows_by_symbol: dict[str, list[dict[str, Any]]],
        window_dates: list[date],
        *,
        all_dates: list[date],
        active_symbols: set[str],
    ) -> dict[str, Any]:
        if not window_dates:
            return {"dates": [], "active": [], "pool": []}
        close_maps: dict[str, dict[date, float]] = {}
        for symbol, rows in rows_by_symbol.items():
            series: dict[date, float] = {}
            for row in rows:
                day = _as_date(row.get("date"))
                close = row.get("close")
                if day is not None and close is not None:
                    series[day] = float(close)
            close_maps[symbol] = series
        all_dates_set = set(all_dates)
        ordered_dates = sorted(day for day in all_dates_set if day <= window_dates[-1])
        previous_by_day: dict[date, date | None] = {}
        previous: date | None = None
        for day in ordered_dates:
            previous_by_day[day] = previous
            previous = day

        def curve(symbols: set[str]) -> list[float | None]:
            if not symbols:
                return []
            values: list[float | None] = []
            level = 100.0
            for day in window_dates:
                previous_day = previous_by_day.get(day)
                returns = []
                for symbol in symbols:
                    series = close_maps.get(symbol)
                    if not series or previous_day is None:
                        continue
                    current_close = series.get(day)
                    previous_close = series.get(previous_day)
                    if current_close and previous_close:
                        returns.append(current_close / previous_close - 1.0)
                if returns:
                    level *= 1.0 + sum(returns) / len(returns)
                values.append(round(level, 2))
            return values

        active = curve(active_symbols)
        pool = curve(set(rows_by_symbol))
        return {
            "dates": [day.isoformat() for day in window_dates],
            "active": active,
            "pool": pool,
        }

    def _benchmark_series(
        self,
        index_daily: pl.DataFrame,
        symbol: str,
        window_dates: list[date],
    ) -> list[float | None]:
        if index_daily.is_empty() or not window_dates:
            return []
        frame = index_daily.filter(pl.col("symbol") == symbol).sort("date")
        if frame.is_empty():
            return []
        close_by_day: dict[date, float] = {}
        for row in frame.iter_rows(named=True):
            day = _as_date(row.get("date"))
            close = row.get("close")
            if day is not None and close is not None:
                close_by_day[day] = float(close)
        base = close_by_day.get(window_dates[0])
        if not base:
            return []
        return [
            round(close_by_day[day] / base * 100.0, 2)
            if day in close_by_day
            else None
            for day in window_dates
        ]

    def _breadth(self, events: pl.DataFrame, window_dates: list[date]) -> list[dict[str, Any]]:
        if events.is_empty():
            return []
        by_day: dict[date, dict[str, set[str] | int]] = {}
        for row in events.iter_rows(named=True):
            day = _as_date(row.get("trade_date"))
            symbol = str(row.get("symbol") or "")
            if day is None or not symbol or day < window_dates[0] or day > window_dates[-1]:
                continue
            bucket = by_day.setdefault(day, {"touched": set(), "sealed": 0, "broken": 0})
            touched = bucket["touched"]
            if isinstance(touched, set):
                touched.add(symbol)
            if int(row.get("in_limit_up_pool") or 0) == 1:
                bucket["sealed"] = int(bucket["sealed"]) + 1
            elif int(row.get("in_limit_break_pool") or 0) == 1:
                bucket["broken"] = int(bucket["broken"]) + 1
        return [
            {
                "date": day.isoformat(),
                "touched": len(bucket["touched"]),
                "sealed": bucket["sealed"],
                "broken": bucket["broken"],
            }
            for day, bucket in sorted(by_day.items())
        ]

    def _limit_route(
        self,
        events: pl.DataFrame,
        leaders: list[dict[str, Any]],
        names: dict[str, str],
        window_dates: list[date],
        minute_dates: list[date],
        available_dates: list[date] | None = None,
    ) -> dict[str, Any]:
        """Build the limit-up relay route used by the route chart and switch days."""

        empty = {
            "dates": [day.isoformat() for day in window_dates],
            "rows": [],
            "daily_leaders": [],
            "leader_phases": [],
            "switch_days": [],
            "event_count": 0,
            "seal_count": 0,
            "space_leader_symbol": None,
            "space_leader_name": None,
            "space_leader_peak_date": None,
        }
        if events.is_empty() or not window_dates:
            return empty
        first_day, last_day = window_dates[0], window_dates[-1]
        leader_by_symbol = {
            str(row.get("symbol")): row
            for row in leaders
            if row.get("symbol")
        }
        minute_date_set = set(minute_dates)
        calendar_dates = sorted(set(available_dates or window_dates))
        calendar_index = {day: index for index, day in enumerate(calendar_dates)}

        by_symbol: dict[str, list[dict[str, Any]]] = {}
        first_dates: dict[str, date] = {}
        first_seal_dates: dict[str, date] = {}
        first_times: dict[str, str] = {}
        first_seal_times: dict[str, str] = {}
        total_lu: dict[str, int] = {}
        max_consec: dict[str, int] = {}
        event_by_key: set[tuple[str, date, str]] = set()
        seen_seal: set[str] = set()
        seal_previous_index: dict[str, int | None] = {}
        seal_streak: dict[str, int] = {}

        event_rows = list(events.iter_rows(named=True))
        event_rows.sort(key=lambda row: (
            _as_date(row.get("trade_date")) or date.min,
            str(row.get("first_seal_time") or row.get("limit_up_time") or ""),
        ))
        for row in event_rows:
            day = _as_date(row.get("trade_date"))
            symbol = str(row.get("symbol") or "")
            if day is None or not symbol or day > last_day:
                continue
            sealed = int(row.get("in_limit_up_pool") or 0) == 1
            broken = int(row.get("in_limit_break_pool") or 0) == 1
            event_type = "seal" if sealed else "broken" if broken else ""
            if not event_type:
                continue
            key = (symbol, day, event_type)
            if key in event_by_key:
                continue
            event_by_key.add(key)
            first_time = (
                row.get("first_seal_time")
                or row.get("limit_up_time")
                or "—"
            )
            last_time = row.get("last_seal_time") or "—"
            opens = (
                row.get("limit_up_pool_open_times")
                if event_type == "seal"
                else row.get("break_pool_open_times")
            )
            raw_consec = int(row.get("continue_day_cnt") or 0)
            day_index = calendar_index.get(day)
            if event_type == "seal":
                previous_index = seal_previous_index.get(symbol)
                derived_consec = (
                    seal_streak.get(symbol, 0) + 1
                    if previous_index is not None
                    and day_index is not None
                    and day_index == previous_index + 1
                    else 1
                )
                # Source board height is only used to seed a streak that began
                # before the loaded route context. Later days are recomputed from
                # the trading calendar so stale source counters cannot leak.
                consec = (
                    raw_consec
                    if symbol not in seen_seal and raw_consec > 0
                    else derived_consec
                )
                seen_seal.add(symbol)
                seal_previous_index[symbol] = day_index
                seal_streak[symbol] = consec
            else:
                consec = 0
                seal_previous_index[symbol] = None
                seal_streak[symbol] = 0
            if day < first_day:
                continue
            reason = str(row.get("limit_up_reason") or "").split("+")[0]
            event = {
                "date": day.isoformat(),
                "type": event_type,
                "first_time": str(first_time),
                "last_time": str(last_time),
                "opens": int(opens) if opens is not None else None,
                "consec": consec,
                "money": _round(
                    float(row["seal_money"]) if row.get("seal_money") is not None else None,
                    0,
                ),
                "reason": reason,
                "catch_up": False,
                "relay": False,
            }
            by_symbol.setdefault(symbol, []).append(event)
            if (
                symbol not in first_dates
                or day < first_dates[symbol]
                or (
                    day == first_dates[symbol]
                    and str(first_time) < first_times.get(symbol, "99:99")
                )
            ):
                first_times[symbol] = str(first_time)
            first_dates[symbol] = min(first_dates.get(symbol, day), day)
            if event_type == "seal":
                if (
                    symbol not in first_seal_dates
                    or day < first_seal_dates[symbol]
                    or (
                        day == first_seal_dates[symbol]
                        and str(first_time) < first_seal_times.get(symbol, "99:99")
                    )
                ):
                    first_seal_times[symbol] = str(first_time)
                first_seal_dates[symbol] = min(first_seal_dates.get(symbol, day), day)
                total_lu[symbol] = total_lu.get(symbol, 0) + 1
                max_consec[symbol] = max(max_consec.get(symbol, 0), consec)

        space_leader = next(
            (
                row
                for row in leaders
                if row.get("symbol") in total_lu
                and row.get("max_ret_30") is not None
            ),
            None,
        )
        space_symbol = str(space_leader["symbol"]) if space_leader else None
        space_peak = _as_date(space_leader.get("max_ret_30_date")) if space_leader else None

        route_rows: list[dict[str, Any]] = []
        for symbol, symbol_events in by_symbol.items():
            summary = leader_by_symbol.get(symbol)
            if summary is None or total_lu.get(symbol, 0) == 0:
                continue
            symbol_events.sort(key=lambda item: (item["date"], item["first_time"]))
            first_date = first_dates.get(symbol)
            first_seal = first_seal_dates.get(symbol)
            route_rows.append({
                "symbol": symbol,
                "name": names.get(symbol, summary.get("name") or symbol),
                "active": bool(summary.get("active")),
                "first_date": first_date.isoformat() if first_date else None,
                "first_seal_date": first_seal.isoformat() if first_seal else None,
                "first_time": first_seal_times.get(symbol) or first_times.get(symbol) or "—",
                "last_date": symbol_events[-1]["date"],
                "total_lu": total_lu.get(symbol, 0),
                "max_consec": max_consec.get(symbol, 0),
                "max_ret_30": summary.get("max_ret_30"),
                "max_ret_30_date": summary.get("max_ret_30_date"),
                "is_space_leader": symbol == space_symbol,
                "events": symbol_events,
            })
        route_rows.sort(
            key=lambda row: (
                row["first_seal_date"] or "9999-99-99",
                row["first_time"] or "99:99",
                -(row["max_ret_30"] or 0),
                row["name"],
            )
        )
        if not route_rows:
            return empty
        for rank, row in enumerate(route_rows, start=1):
            row["start_rank"] = rank
            first_seal_day = _as_date(row["first_seal_date"])
            for event in row["events"]:
                event_day = _as_date(event["date"])
                after_peak = bool(
                    space_peak
                    and event["type"] == "seal"
                    and row["symbol"] != space_symbol
                    and event_day is not None
                    and event_day > space_peak
                )
                is_new_starter = bool(
                    first_seal_day is not None
                    and space_peak is not None
                    and first_seal_day > space_peak
                )
                event["catch_up"] = after_peak and is_new_starter
                event["relay"] = after_peak and not is_new_starter

        events_by_date: dict[date, list[dict[str, Any]]] = {}
        for symbol, symbol_events in by_symbol.items():
            for event in symbol_events:
                day = _as_date(event["date"])
                if day is None:
                    continue
                events_by_date.setdefault(day, []).append({
                    **event,
                    "symbol": symbol,
                    "name": names.get(symbol, symbol),
                    "total_lu": total_lu.get(symbol, 0),
                })

        daily_leaders: list[dict[str, Any]] = []
        previous_leader: str | None = None
        for day in sorted(events_by_date):
            sealed_today = [
                event for event in events_by_date[day]
                if event["type"] == "seal"
            ]
            if not sealed_today:
                continue
            leader = sorted(
                sealed_today,
                key=lambda event: (
                    -int(event.get("consec") or 0),
                    str(event.get("first_time") or "99:99"),
                    -float(event.get("money") or 0),
                ),
            )[0]
            leader_symbol = str(leader["symbol"])
            daily_leaders.append({
                "date": day.isoformat(),
                "symbol": leader_symbol,
                "name": leader["name"],
                "consec": int(leader.get("consec") or 0),
                "total_lu": int(leader.get("total_lu") or 1),
                "first_time": leader.get("first_time") or "—",
                "switch": previous_leader is not None and previous_leader != leader_symbol,
            })
            previous_leader = leader_symbol

        leader_phases: list[dict[str, Any]] = []
        for item in daily_leaders:
            if (
                not leader_phases
                or leader_phases[-1]["symbol"] != item["symbol"]
            ):
                leader_phases.append({
                    "symbol": item["symbol"],
                    "name": item["name"],
                    "start": item["date"],
                    "end": item["date"],
                    "days": 1,
                })
            else:
                phase = leader_phases[-1]
                phase["end"] = item["date"]
                phase["days"] = int(phase["days"]) + 1

        switch_days: list[dict[str, Any]] = []
        previous_daily_leader: str | None = None
        first_event_day = min(events_by_date)
        for day in sorted(events_by_date):
            day_events = events_by_date[day]
            sealed = sorted(
                [event for event in day_events if event["type"] == "seal"],
                key=lambda event: (event["first_time"], event["symbol"]),
            )
            broken = sorted(
                [event for event in day_events if event["type"] == "broken"],
                key=lambda event: (event["first_time"], event["symbol"]),
            )
            catch_up_events = [event for event in sealed if event.get("catch_up")]
            relay_events = [event for event in sealed if event.get("relay")]
            daily_leader = next(
                (item for item in daily_leaders if item["date"] == day.isoformat()),
                None,
            )
            new_starters = [
                row for row in route_rows
                if row["first_seal_date"] == day.isoformat()
            ]
            leader_changed = bool(
                daily_leader
                and previous_daily_leader
                and daily_leader["symbol"] != previous_daily_leader
            )
            labels: list[str] = []
            reasons: list[str] = []
            if day == first_event_day:
                labels.append("启动")
                reasons.append("窗口内最早出现涨停/炸板事件")
            if leader_changed:
                labels.append("领涨切换")
                reasons.append(
                    f"{names.get(previous_daily_leader, previous_daily_leader)}"
                    f" → {daily_leader['name']}（按连板高度、首封时间）"
                )
            if len(new_starters) >= 2:
                labels.append(f"扩散 +{len(new_starters)}")
                reasons.append("、".join(row["name"] for row in new_starters[:3]))
            if len(sealed) >= 5:
                labels.append(f"封板潮 {len(sealed)}")
            elif len(broken) > len(sealed) and len(broken) >= 2:
                labels.append("分歧")
                reasons.append(f"炸板 {len(broken)} / 封板 {len(sealed)}")
            if catch_up_events:
                labels.append(f"补涨 +{len(catch_up_events)}")
                new_starter_symbols = {row["symbol"] for row in new_starters}
                catch_up_names = [
                    str(event["name"])
                    for event in catch_up_events
                    if event["symbol"] not in new_starter_symbols
                ]
                if catch_up_names:
                    reasons.append(
                        "、".join(catch_up_names[:3])
                        + " 在龙头 30 日峰值后首次封板"
                    )
            if len(relay_events) >= 3:
                labels.append(f"接力 {len(relay_events)}")
                reasons.append(
                    "、".join(str(event["name"]) for event in relay_events[:3])
                    + " 峰值后继续封板（非首次）"
                )
            if not labels and new_starters:
                labels.append("新人首封")

            if labels:
                ordered_symbols: list[str] = []
                if daily_leader:
                    ordered_symbols.append(str(daily_leader["symbol"]))
                if previous_daily_leader:
                    ordered_symbols.append(previous_daily_leader)
                if space_symbol:
                    ordered_symbols.append(space_symbol)
                for event in broken:
                    ordered_symbols.append(str(event["symbol"]))
                for event in sealed:
                    ordered_symbols.append(str(event["symbol"]))
                for row in new_starters:
                    ordered_symbols.append(str(row["symbol"]))
                switch_days.append({
                    "date": day.isoformat(),
                    "label": " / ".join(dict.fromkeys(labels)),
                    "reason": "；".join(dict.fromkeys(reasons)),
                    "symbols": list(dict.fromkeys(ordered_symbols))[:12],
                    "minute_symbols": list(dict.fromkeys(ordered_symbols))[:8],
                    "sealed": [
                        {
                            "symbol": str(event["symbol"]),
                            "name": event["name"],
                            "consec": int(event.get("consec") or 0),
                            "first_time": event.get("first_time") or "—",
                            "catch_up": bool(event.get("catch_up")),
                            "relay": bool(event.get("relay")),
                        }
                        for event in sealed
                    ],
                    "broken": [
                        {
                            "symbol": str(event["symbol"]),
                            "name": event["name"],
                            "first_time": event.get("first_time") or "—",
                        }
                        for event in broken
                    ],
                    "new_starters": [
                        {"symbol": row["symbol"], "name": row["name"]}
                        for row in new_starters
                    ],
                    "daily_leader": daily_leader["symbol"] if daily_leader else None,
                    "leader_name": daily_leader["name"] if daily_leader else None,
                    "previous_leader": previous_daily_leader,
                    "previous_leader_name": names.get(previous_daily_leader) if previous_daily_leader else None,
                    "has_minute": day in minute_date_set,
                })
            if daily_leader:
                previous_daily_leader = str(daily_leader["symbol"])

        if space_peak is not None and first_day <= space_peak <= last_day:
            peak_switch = next(
                (item for item in switch_days if item["date"] == space_peak.isoformat()),
                None,
            )
            peak_reason = f"{space_leader['name']} 30日峰值日"
            if peak_switch is None:
                switch_days.append({
                    "date": space_peak.isoformat(),
                    "label": "龙头涨幅峰值",
                    "reason": peak_reason,
                    "symbols": [space_symbol] if space_symbol else [],
                    "minute_symbols": [space_symbol] if space_symbol else [],
                    "sealed": [],
                    "broken": [],
                    "new_starters": [],
                    "daily_leader": space_symbol,
                    "leader_name": space_leader["name"],
                    "previous_leader": None,
                    "previous_leader_name": None,
                    "has_minute": space_peak in minute_date_set,
                })
            else:
                if "龙头涨幅峰值" not in peak_switch["label"]:
                    peak_switch["label"] = f"{peak_switch['label']} / 龙头涨幅峰值"
                    peak_switch["reason"] = "；".join(
                        item for item in (peak_switch["reason"], peak_reason) if item
                    )
                if space_symbol:
                    peak_switch["minute_symbols"] = list(dict.fromkeys([
                        space_symbol,
                        *peak_switch["minute_symbols"],
                    ]))[:8]
                peak_switch["has_minute"] = (
                    bool(peak_switch["has_minute"])
                    or space_peak in minute_date_set
                )
        switch_days.sort(key=lambda item: item["date"])

        return {
            "dates": [day.isoformat() for day in window_dates],
            "rows": route_rows,
            "daily_leaders": daily_leaders,
            "leader_phases": leader_phases,
            "switch_days": switch_days,
            "event_count": sum(len(events) for events in by_symbol.values()),
            "seal_count": sum(total_lu.values()),
            "space_leader_symbol": space_symbol,
            "space_leader_name": space_leader["name"] if space_leader else None,
            "space_leader_peak_date": space_peak.isoformat() if space_peak else None,
        }

    def _latest_event_date(self, end: date) -> date | None:
        try:
            dates = self.market_data.dataset_partition_dates(
                "ext_data/limit_board_events/timeseries",
                end - timedelta(days=30),
                end,
            )
        except Exception:  # noqa: BLE001 - optional event overlay
            return None
        return dates[-1] if dates else None

    def _latest_limit_payload(
        self,
        symbols: list[str],
        names: dict[str, str],
        window_events: pl.DataFrame,
        event_date: date | None,
        fallback_date: date,
    ) -> dict[str, Any]:
        if event_date is None:
            return {
                "date": fallback_date.isoformat(),
                "sealed": [],
                "broken": [],
                "sealed_count": 0,
                "broken_count": 0,
                "touched": 0,
                "seal_rate": None,
                "share": None,
            }
        try:
            latest_all = self.market_data.read_dataset_partition(
                "ext_data/limit_board_events/timeseries",
                event_date,
            )
        except Exception:  # noqa: BLE001 - empty latest structure
            latest_all = pl.DataFrame()
        if latest_all.is_empty() or "symbol" not in latest_all.columns:
            return {
                "date": event_date.isoformat(),
                "sealed": [],
                "broken": [],
                "sealed_count": 0,
                "broken_count": 0,
                "touched": 0,
                "seal_rate": None,
                "share": None,
            }
        latest_all = latest_all.with_columns(pl.col("symbol").cast(pl.Utf8))
        theme_latest = latest_all.filter(pl.col("symbol").is_in(symbols))
        sealed = theme_latest.filter(pl.col("in_limit_up_pool") == 1) if "in_limit_up_pool" in theme_latest.columns else pl.DataFrame()
        broken = theme_latest.filter(pl.col("in_limit_break_pool") == 1) if "in_limit_break_pool" in theme_latest.columns else pl.DataFrame()
        market_sealed = (
            latest_all.filter(pl.col("in_limit_up_pool") == 1).height
            if "in_limit_up_pool" in latest_all.columns
            else 0
        )
        stat_map: dict[str, dict[str, Any]] = {}
        if not window_events.is_empty() and "symbol" in window_events.columns:
            for symbol, group in window_events.filter(pl.col("in_limit_up_pool") == 1).group_by("symbol"):
                symbol_key = symbol[0] if isinstance(symbol, tuple) else symbol
                stat_map[str(symbol_key)] = {
                    "total_lu": group.height,
                }

        def sealed_row(row: dict[str, Any]) -> dict[str, Any]:
            symbol = str(row.get("symbol") or "")
            stat = stat_map.get(symbol, {})
            first = row.get("first_seal_time") or row.get("limit_up_time") or "—"
            last = row.get("last_seal_time")
            if not last and row.get("limit_up_pool_open_times") in (None, 0):
                last = row.get("limit_up_time")
            return {
                "symbol": symbol,
                "name": names.get(symbol, row.get("name") or symbol),
                "total_lu": int(stat.get("total_lu") or 1),
                "consec": max(1, int(row.get("continue_day_cnt") or 1)),
                "first": first,
                "last": last or "—",
                "opens": row.get("limit_up_pool_open_times"),
                "money": row.get("seal_money"),
                "reason": str(row.get("limit_up_reason") or "").split("+")[0],
            }

        def broken_row(row: dict[str, Any]) -> dict[str, Any]:
            symbol = str(row.get("symbol") or "")
            return {
                "symbol": symbol,
                "name": names.get(symbol, row.get("name") or symbol),
                "first": row.get("first_seal_time") or row.get("limit_up_time") or "—",
                "last": row.get("last_seal_time") or "—",
                "opens": row.get("break_pool_open_times"),
                "reason": str(row.get("limit_up_reason") or "").split("+")[0],
            }

        sealed_rows = sorted(
            [sealed_row(row) for row in sealed.iter_rows(named=True)],
            key=lambda row: str(row["first"]),
        )
        broken_rows = sorted(
            [broken_row(row) for row in broken.iter_rows(named=True)],
            key=lambda row: str(row["first"]),
        )
        touched = int(theme_latest.height) if "symbol" in theme_latest.columns else 0
        return {
            "date": event_date.isoformat(),
            "sealed": sealed_rows,
            "broken": broken_rows,
            "sealed_count": len(sealed_rows),
            "broken_count": len(broken_rows),
            "touched": touched,
            "seal_rate": _ratio(len(sealed_rows) / touched) if touched else None,
            "share": _ratio(len(sealed_rows) / market_sealed) if market_sealed else None,
        }

    def _minute_dates(self, start: date, end: date) -> list[date]:
        try:
            return self.market_data.list_minute_dates(start, end)
        except Exception:  # noqa: BLE001 - optional minute lab
            return []

    def _minute_features(self, group: pl.DataFrame, prev_close: float) -> dict[str, Any]:
        rows = group.sort("datetime").iter_rows(named=True)
        times: list[str] = []
        closes: list[float] = []
        volumes: list[float] = []
        amounts: list[float | None] = []
        for row in rows:
            time_key = _minute_time(row.get("datetime"))
            close = row.get("close")
            if time_key is None or close is None:
                continue
            times.append(time_key)
            closes.append(float(close))
            volumes.append(float(row.get("volume") or 0.0))
            amount = row.get("amount")
            amounts.append(float(amount) if amount is not None else None)
        if not closes:
            return {
                "sample": 0,
                "complete": False,
                "day": None,
                "open30": None,
                "am": None,
                "pm": None,
                "tail30": None,
                "max_dd": None,
                "vwap_dev": None,
                "up_ratio": None,
            }

        def at_time(target: str) -> float:
            for index, value in enumerate(times):
                if value >= target:
                    return closes[index]
            return closes[-1]

        last = closes[-1]
        base = at_time("13:00")
        peak = closes[0]
        max_drawdown = 0.0
        up_volume = 0.0
        down_volume = 0.0
        cumulative_amount = 0.0
        cumulative_volume = 0.0
        for index, close in enumerate(closes):
            peak = max(peak, close)
            if peak:
                max_drawdown = min(max_drawdown, close / peak - 1.0)
            if index:
                move = close - closes[index - 1]
                if move > 0:
                    up_volume += volumes[index]
                elif move < 0:
                    down_volume += volumes[index]
            volume = volumes[index]
            cumulative_volume += volume
            amount = amounts[index]
            cumulative_amount += amount if amount is not None else close * volume * 100.0
        vwap = cumulative_amount / (cumulative_volume * 100.0) if cumulative_volume else None
        return {
            "sample": len(closes),
            "complete": len(closes) >= 100,
            "day": _pct(last / prev_close - 1.0),
            "open30": _pct(at_time("10:00") / prev_close - 1.0),
            "am": _pct(at_time("11:30") / prev_close - 1.0),
            "pm": _pct(last / base - 1.0) if base else None,
            "tail30": _pct(last / at_time("14:30") - 1.0) if at_time("14:30") else None,
            "max_dd": _pct(max_drawdown),
            "vwap_dev": _pct(last / vwap - 1.0) if vwap else None,
            "up_ratio": _pct(up_volume / (up_volume + down_volume)) if up_volume + down_volume else None,
        }

    def _empty_payload(
        self,
        theme: dict[str, Any],
        symbols: list[str],
        names: dict[str, str],
        start: date | None,
        end: date | None,
        *,
        latest_daily: date | None = None,
    ) -> dict[str, Any]:
        today = date.today()
        resolved_end = end or latest_daily or today
        resolved_start = start or (resolved_end - timedelta(days=90))
        return {
            "theme_id": theme["id"],
            "theme_name": theme["name"],
            "as_of": latest_daily.isoformat() if latest_daily else None,
            "window_start": resolved_start.isoformat(),
            "window_end": resolved_end.isoformat(),
            "default_window_days": DEFAULT_WINDOW_TRADING_DAYS,
            "pool_count": len(symbols),
            "quoted_count": 0,
            "active_count": 0,
            "active_return": None,
            "pool_return": None,
            "sh_return": None,
            "latest_minute_date": None,
            "minute_dates": [],
            "leaders": [
                {
                    "symbol": symbol,
                    "name": names.get(symbol, symbol),
                    "active": False,
                    "last_date": None,
                    "last_close": None,
                    "max_ret_3": None,
                    "max_ret_10": None,
                    "max_ret_30": None,
                    "latest_ret_3": None,
                    "active_gt2": 0,
                    "avg_deviate": None,
                    "max_deviate": None,
                    "avg_close_pos": None,
                    "active_days": 0,
                    "event_count": 0,
                }
                for symbol in symbols
            ],
            "index": {"dates": [], "active": [], "pool": [], "sh": []},
            "heatmap": {"dates": [], "rows": []},
            "breadth": [],
            "seal": {
                "date": resolved_end.isoformat(),
                "sealed": [],
                "broken": [],
                "sealed_count": 0,
                "broken_count": 0,
                "touched": 0,
                "seal_rate": None,
                "share": None,
            },
            "limit_route": {
                "dates": [],
                "rows": [],
                "daily_leaders": [],
                "leader_phases": [],
                "switch_days": [],
                "event_count": 0,
                "seal_count": 0,
                "space_leader_symbol": None,
                "space_leader_name": None,
                "space_leader_peak_date": None,
            },
        }


def _minute_time(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.strftime("%H:%M")
    if isinstance(value, str):
        text = value.strip()
        if "T" in text:
            text = text.split("T", 1)[1]
        elif " " in text:
            text = text.split(" ", 1)[1]
        return text[:5] if len(text) >= 5 else None
    return None


def _table_times(times: list[str]) -> list[str]:
    result: list[str] = []
    keep = {"09:31", "11:30", "13:01", "15:00"}
    for time_key in times:
        try:
            minute = int(time_key.split(":", 1)[1])
        except (ValueError, IndexError):
            continue
        if minute % 5 == 0 or time_key in keep:
            result.append(time_key)
    return result

