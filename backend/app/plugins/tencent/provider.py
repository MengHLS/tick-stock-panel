"""Tencent public 1-minute K-line provider."""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import polars as pl

logger = logging.getLogger(__name__)

_BASE_URL = "https://ifzq.gtimg.cn/appstock/app/kline/mkline"
_MAX_BARS = 800
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
class TencentConfig:
    datasets: dict[str, object] = field(default_factory=lambda: {"minute": {}})


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


def _beijing_wallclock(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(_CN_TZ).replace(tzinfo=None)


def _in_session(value: datetime) -> bool:
    minute = value.hour * 60 + value.minute
    return 570 <= minute <= 690 or 780 <= minute <= 900


def _bar(row: object) -> dict | None:
    if not isinstance(row, (list, tuple)) or len(row) < 6:
        return None
    try:
        stamp = datetime.strptime(str(row[0]), "%Y%m%d%H%M")
        open_, close, high, low, volume = (
            float(row[index]) for index in (1, 2, 3, 4, 5)
        )
    except (TypeError, ValueError):
        return None
    values = (open_, close, high, low, volume)
    if not all(math.isfinite(value) for value in values):
        return None
    if min(open_, close, high, low) <= 0 or volume < 0 or not _in_session(stamp):
        return None
    if high < max(open_, close, low) or low > min(open_, close, high):
        return None
    return {
        "datetime": stamp,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "amount": None,
    }


class TencentProvider:
    """Minute-only provider backed by Tencent's public chart endpoint."""

    name = "tencent"
    minute_history_days = 3

    def __init__(self) -> None:
        self.config = TencentConfig()
        self._client: httpx.Client | None = None

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=20.0,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Referer": "https://gu.qq.com/",
                },
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def _request(self, request_code: str) -> list:
        response = self._get_client().get(
            _BASE_URL,
            params={"param": f"{request_code},m1,,{_MAX_BARS}"},
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") not in (None, 0, "0"):
            raise ValueError(f"Tencent response code={payload.get('code')}")
        item = (payload.get("data") or {}).get(request_code) or {}
        rows = item.get("m1")
        return rows if isinstance(rows, list) else []

    def get_minute(
        self,
        symbols: list[str],
        start_time: datetime | None,
        end_time: datetime | None,
        asset_type: str = "stock",
        freq: str = "1m",
        on_chunk_done: Callable[[int, int], None] | None = None,
    ) -> pl.DataFrame:
        if not symbols or freq != "1m" or asset_type not in {"stock", "etf", "index"}:
            return pl.DataFrame(schema=_MINUTE_SCHEMA)
        start = _beijing_wallclock(start_time)
        end = _beijing_wallclock(end_time)
        frames: list[pl.DataFrame] = []
        for index, symbol in enumerate(symbols, start=1):
            request_code = _request_code(symbol)
            if request_code is not None:
                try:
                    raw_rows = self._request(request_code)
                except Exception as exc:  # noqa: BLE001 - isolate one symbol
                    logger.warning("Tencent minute %s failed: %s", symbol, exc)
                    raw_rows = []
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
                if rows:
                    frames.append(pl.DataFrame(rows, schema=_MINUTE_SCHEMA))
            if on_chunk_done is not None:
                on_chunk_done(index, len(symbols))
        if not frames:
            return pl.DataFrame(schema=_MINUTE_SCHEMA)
        return (
            pl.concat(frames, how="vertical_relaxed")
            .unique(subset=["symbol", "datetime"], keep="last")
            .sort("symbol", "datetime")
        )

    def test_dataset(self, dataset: str, symbols: list[str] | None = None) -> dict:
        if dataset != "minute":
            return {
                "provider": self.name,
                "dataset": dataset,
                "rows": 0,
                "error": "Tencent plugin only provides minute data",
            }
        selected = (symbols or ["600519.SH"])[:3]
        try:
            frame = self.get_minute(selected, None, None)
        except Exception as exc:  # noqa: BLE001 - settings test response
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
