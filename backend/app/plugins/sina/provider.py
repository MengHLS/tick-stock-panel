"""Sina public 1-minute K-line provider."""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import polars as pl

from app.data_providers.base import ProviderRequestError

logger = logging.getLogger(__name__)

_BASE_URL = "https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData"
_MAX_BARS = 1500
_REQUEST_INTERVAL_S = 0.05
_INTRADAY_WORKERS = 32
_INTRADAY_BARS = 300
_CN_TZ = ZoneInfo("Asia/Shanghai")
_MINUTE_SCHEMA = {
    "symbol": pl.Utf8,
    "datetime": pl.Datetime("us"),
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "volume": pl.Float64,
    "amount": pl.Float64,
}


@dataclass
class SinaConfig:
    datasets: dict[str, object] = field(
        default_factory=lambda: {"minute": {}, "full_minute": {}}
    )


def availability() -> tuple[bool, str]:
    return True, "ok"


def _request_code(symbol: str) -> str | None:
    if "." not in symbol:
        return None
    code, exchange = symbol.rsplit(".", 1)
    prefix = {"SH": "sh", "SZ": "sz"}.get(exchange.upper())
    if prefix is None or len(code) != 6 or not code.isdigit():
        return None
    return f"{prefix}{code}"


def _is_main_board(symbol: str) -> bool:
    request_code = _request_code(symbol)
    return request_code is not None and request_code.startswith(("sh60", "sz00"))


def _beijing_wallclock(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(_CN_TZ).replace(tzinfo=None)


def _in_session(value: datetime) -> bool:
    minute = value.hour * 60 + value.minute
    return 570 <= minute <= 690 or 780 <= minute <= 900


def _bar(row: object) -> dict | None:
    if not isinstance(row, dict):
        return None
    try:
        stamp = datetime.strptime(str(row["day"]), "%Y-%m-%d %H:%M:%S")
        open_ = float(row["open"])
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])
        volume = float(row["volume"])
        amount = float(row["amount"])
    except (KeyError, TypeError, ValueError):
        return None
    values = (open_, high, low, close, volume, amount)
    if not all(math.isfinite(value) for value in values):
        return None
    if min(open_, high, low, close) <= 0 or volume < 0 or amount < 0:
        return None
    if high < max(open_, close, low) or low > min(open_, close, high):
        return None
    if not _in_session(stamp):
        return None
    return {
        "datetime": stamp,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume / 100.0,
        "amount": amount,
    }


class SinaProvider:
    """Minute-only provider backed by Sina's public chart endpoint."""

    name = "sina"
    minute_history_days = 6

    def __init__(self) -> None:
        self.config = SinaConfig()
        self._client: httpx.Client | None = None

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=20.0,
                limits=httpx.Limits(
                    max_connections=64,
                    max_keepalive_connections=_INTRADAY_WORKERS,
                    keepalive_expiry=30,
                ),
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Referer": "https://finance.sina.com.cn/",
                },
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def _request(self, request_code: str, *, datalen: int = _MAX_BARS) -> list:
        try:
            response = self._get_client().get(
                _BASE_URL,
                params={
                    "symbol": request_code,
                    "scale": "1",
                    "ma": "no",
                    "datalen": str(datalen),
                },
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderRequestError(f"Sina minute {request_code} request failed: {exc}") from exc
        if not isinstance(payload, list):
            raise ProviderRequestError(f"Sina minute {request_code} returned unexpected payload")
        return payload

    def get_minute(
        self,
        symbols: list[str],
        start_time: datetime | None,
        end_time: datetime | None,
        asset_type: str = "stock",
        freq: str = "1m",
        on_chunk_done: Callable[[int, int], None] | None = None,
    ) -> pl.DataFrame:
        if freq != "1m":
            raise ProviderRequestError("Sina plugin only provides 1m minute data")
        if asset_type != "stock":
            raise ProviderRequestError("Sina minute plugin currently supports stock only")
        if not symbols:
            return pl.DataFrame(schema=_MINUTE_SCHEMA)
        request_codes = []
        for symbol in symbols:
            request_code = _request_code(symbol)
            if request_code is None:
                raise ProviderRequestError(f"Sina minute plugin does not support symbol: {symbol}")
            request_codes.append((symbol, request_code))

        start = _beijing_wallclock(start_time)
        end = _beijing_wallclock(end_time)
        frames: list[pl.DataFrame] = []
        total = len(request_codes)
        for index, (symbol, request_code) in enumerate(request_codes, start=1):
            raw_rows = self._request(request_code)
            rows = []
            for raw in raw_rows:
                parsed = _bar(raw)
                if parsed is None:
                    continue
                stamp = parsed["datetime"]
                if start is not None and stamp < start:
                    continue
                if end is not None and stamp > end:
                    continue
                rows.append({"symbol": symbol, **parsed})
            if raw_rows and not rows:
                logger.warning("Sina minute %s returned %d rows but none parsed", symbol, len(raw_rows))
            if rows:
                frames.append(pl.DataFrame(rows, schema=_MINUTE_SCHEMA))
            if on_chunk_done is not None:
                on_chunk_done(index, total)
            time.sleep(_REQUEST_INTERVAL_S)
        if not frames:
            return pl.DataFrame(schema=_MINUTE_SCHEMA)
        return (
            pl.concat(frames, how="vertical_relaxed")
            .unique(subset=["symbol", "datetime"], keep="last")
            .sort("symbol", "datetime")
        )

    def get_intraday_batch(
        self,
        symbols: list[str],
        count: int = 300,
        asset_type: str = "stock",
    ) -> pl.DataFrame:
        """Main-board-only full-market repair round for the intraday service."""
        if asset_type != "stock":
            raise ProviderRequestError("Sina full_minute plugin currently supports stock only")
        supported = [symbol for symbol in symbols if _is_main_board(symbol)]
        if not supported:
            return pl.DataFrame(schema=_MINUTE_SCHEMA)
        try:
            datalen = max(250, min(int(count), _MAX_BARS))
        except (TypeError, ValueError):
            datalen = _INTRADAY_BARS
        today = datetime.now(_CN_TZ).date()

        def fetch(symbol: str) -> tuple[str, list[dict], str | None]:
            request_code = _request_code(symbol)
            try:
                raw_rows = self._request(request_code, datalen=datalen)
            except ProviderRequestError as exc:
                return symbol, [], str(exc)
            rows = []
            for raw in raw_rows:
                parsed = _bar(raw)
                if parsed is None or parsed["datetime"].date() != today:
                    continue
                rows.append({"symbol": symbol, **parsed})
            return symbol, rows, None

        frames: list[pl.DataFrame] = []
        failures: list[tuple[str, str]] = []
        with ThreadPoolExecutor(
            max_workers=_INTRADAY_WORKERS,
            thread_name_prefix="sina-intraday",
        ) as executor:
            for symbol, rows, error in executor.map(fetch, supported):
                if error is not None:
                    failures.append((symbol, error))
                    continue
                if rows:
                    frames.append(pl.DataFrame(rows, schema=_MINUTE_SCHEMA))
        if failures:
            if not frames:
                raise ProviderRequestError(
                    f"Sina intraday batch failed for all {len(failures)} symbols: {failures[0][1]}"
                )
            logger.warning(
                "Sina intraday batch skipped %d/%d failed symbols; first error: %s",
                len(failures), len(supported), failures[0][1],
            )
        if not frames:
            return pl.DataFrame(schema=_MINUTE_SCHEMA)
        return (
            pl.concat(frames, how="vertical_relaxed")
            .unique(subset=["symbol", "datetime"], keep="last")
            .sort("symbol", "datetime")
        )

    def test_dataset(self, dataset: str, symbols: list[str] | None = None) -> dict:
        if dataset not in {"minute", "full_minute"}:
            return {
                "provider": self.name,
                "dataset": dataset,
                "rows": 0,
                "error": "Sina plugin only provides minute and full_minute data",
            }
        selected = (symbols or ["600519.SH"])[:3]
        try:
            frame = (
                self.get_intraday_batch(selected)
                if dataset == "full_minute"
                else self.get_minute(selected, None, None)
            )
        except ProviderRequestError as exc:
            return {
                "provider": self.name,
                "dataset": dataset,
                "rows": 0,
                "error": str(exc),
            }
        preview = frame.head(5).to_dicts()
        for row in preview:
            if isinstance(row.get("datetime"), datetime):
                row["datetime"] = row["datetime"].isoformat()
        return {
            "provider": self.name,
            "dataset": dataset,
            "rows": frame.height,
            "columns": frame.columns,
            "preview": preview,
        }
