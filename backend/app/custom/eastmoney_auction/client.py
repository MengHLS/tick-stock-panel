"""Eastmoney public endpoints used by the live opening-auction collector."""

from __future__ import annotations

import logging
import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from app.market_time import CN_TZ, cn_now

logger = logging.getLogger(__name__)

_ULIST_URL = "https://push2.eastmoney.com/api/qt/ulist.np/get"
_STOCK_URL = "https://push2.eastmoney.com/api/qt/stock/get"
_BATCH_SIZE = 100
_SESSION_INDEX = "1.000001"
_MARKET_FIELDS = "f2,f5,f6,f12,f13,f14,f17,f18"
_FINAL_FIELDS = "f43,f47,f48,f57,f58,f60,f86"


class EastmoneyError(RuntimeError):
    """An Eastmoney response cannot be used as a complete market observation."""


@dataclass(frozen=True)
class MarketRow:
    symbol: str
    name: str | None
    reference_price: float | None
    cumulative_volume_lots: float | None
    cumulative_amount: float | None
    auction_open: float | None
    prev_close: float | None


@dataclass(frozen=True)
class MarketSnapshot:
    rows: list[MarketRow]
    total: int
    observed_at: datetime


@dataclass(frozen=True)
class AuctionFinal:
    symbol: str
    auction_open: float
    prev_close: float
    volume_lots: float
    amount: float
    source_timestamp: str


def _number(value: Any) -> float | None:
    if value in (None, "", "-"):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _market_symbol(row: dict) -> str:
    code = str(row.get("f12") or "").strip()
    market = row.get("f13")
    if not code.isdigit():
        raise EastmoneyError(f"invalid Eastmoney code: {code!r}")
    suffix = {"0": "SZ", "1": "SH"}.get(str(market))
    if suffix is None:
        raise EastmoneyError(f"unsupported Eastmoney market id: {market!r}")
    return f"{code.zfill(6)}.{suffix}"


def _market_row(row: dict) -> MarketRow:
    return MarketRow(
        symbol=_market_symbol(row),
        name=str(row["f14"]) if row.get("f14") not in (None, "-") else None,
        reference_price=_number(row.get("f2")),
        cumulative_volume_lots=_number(row.get("f5")),
        cumulative_amount=_number(row.get("f6")),
        auction_open=_number(row.get("f17")),
        prev_close=_number(row.get("f18")),
    )


def _secid(symbol: str) -> str:
    if "." not in symbol:
        raise EastmoneyError(f"invalid symbol: {symbol}")
    code, exchange = symbol.rsplit(".", 1)
    market = {"SH": "1", "SZ": "0"}.get(exchange.upper())
    if market is None or len(code) != 6 or not code.isdigit():
        raise EastmoneyError(f"unsupported symbol: {symbol}")
    return f"{market}.{code}"


class EastmoneyAuctionClient:
    """Bounded, fail-closed client for auction snapshots and final verification."""

    def __init__(
        self,
        *,
        http_client: httpx.Client | None = None,
        clock: Callable[[], datetime] = cn_now,
        retries: int = 2,
    ) -> None:
        self._client = http_client or httpx.Client(
            timeout=20.0,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://quote.eastmoney.com/",
            },
        )
        self._owns_client = http_client is None
        self._clock = clock
        self._retries = max(0, retries)
        self._cancel_lock = threading.Lock()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _request_json(self, url: str, params: dict[str, Any]) -> dict:
        last: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                response = self._client.get(url, params=params)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise EastmoneyError("response is not an object")
                return payload
            except Exception as exc:  # noqa: BLE001 - normalized and retried
                last = exc
                if attempt < self._retries:
                    time.sleep(1.0 * (attempt + 1))
        raise EastmoneyError(str(last) if last is not None else "request failed")

    @staticmethod
    def _check_cancel(cancel_event: threading.Event | None) -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise EastmoneyError("request cancelled")

    def fetch_market_snapshot(
        self,
        *,
        symbols: list[str],
        cancel_event: threading.Event | None = None,
    ) -> MarketSnapshot:
        """Fetch a complete local stock universe through bounded ulist batches."""
        requested = list(dict.fromkeys(symbols))
        if not requested:
            raise EastmoneyError("empty stock universe")
        for symbol in requested:
            _secid(symbol)

        raw_rows: list[MarketRow] = []
        for offset in range(0, len(requested), _BATCH_SIZE):
            self._check_cancel(cancel_event)
            chunk = requested[offset : offset + _BATCH_SIZE]
            payload = self._request_json(
                _ULIST_URL,
                {
                    "fltt": 2,
                    "invt": 2,
                    "fields": _MARKET_FIELDS,
                    "secids": ",".join(_secid(symbol) for symbol in chunk),
                },
            )
            data = payload.get("data")
            if not isinstance(data, dict):
                raise EastmoneyError("ulist response has no data")
            rows = data.get("diff") or []
            if isinstance(rows, dict):
                rows = list(rows.values())
            if not isinstance(rows, list):
                raise EastmoneyError("ulist response has invalid rows")
            parsed: list[MarketRow] = []
            seen: set[str] = set()
            for raw in rows:
                if not isinstance(raw, dict):
                    raise EastmoneyError("ulist response contains a non-object row")
                row = _market_row(raw)
                if row.symbol in seen:
                    raise EastmoneyError(f"duplicate symbol in ulist batch: {row.symbol}")
                seen.add(row.symbol)
                parsed.append(row)
            expected = set(chunk)
            if seen != expected:
                missing = sorted(expected - seen)
                extra = sorted(seen - expected)
                raise EastmoneyError(
                    "incomplete ulist batch: "
                    f"missing={missing[:5]}, extra={extra[:5]}"
                )
            raw_rows.extend(parsed)
            if offset + _BATCH_SIZE < len(requested):
                time.sleep(0.15)
        observed_at = self._clock()
        if observed_at.tzinfo is None:
            raise EastmoneyError("clock must return a timezone-aware datetime")
        return MarketSnapshot(
            rows=raw_rows,
            total=len(raw_rows),
            observed_at=observed_at.astimezone(CN_TZ),
        )

    def _stock_payload(self, secid: str) -> dict:
        payload = self._request_json(
            _STOCK_URL,
            {
                "fltt": 2,
                "invt": 2,
                "fields": _FINAL_FIELDS,
                "secid": secid,
            },
        )
        data = payload.get("data")
        if not isinstance(data, dict):
            raise EastmoneyError("stock/get response has no data")
        return data

    def verify_session(self, expected_date) -> bool:
        """The index quote timestamp must belong to the requested date."""
        data = self._stock_payload(_SESSION_INDEX)
        try:
            stamp = int(data["f86"])
        except (KeyError, TypeError, ValueError) as exc:
            raise EastmoneyError("stock/get timestamp is missing") from exc
        observed = datetime.fromtimestamp(stamp, tz=CN_TZ).date()
        return observed == expected_date

    def fetch_auction_final(self, symbol: str, expected_date) -> AuctionFinal:
        """Cross-check one batch row against the single-symbol stock endpoint."""
        data = self._stock_payload(_secid(symbol))
        try:
            price = float(data["f43"])
            volume = float(data["f47"])
            amount = float(data["f48"])
            prev_close = float(data["f60"])
            stamp = int(data["f86"])
        except (KeyError, TypeError, ValueError) as exc:
            raise EastmoneyError(f"invalid final auction fields for {symbol}") from exc
        if not all(math.isfinite(v) for v in (price, volume, amount, prev_close)):
            raise EastmoneyError(f"non-finite final auction fields for {symbol}")
        if price <= 0 or prev_close <= 0 or volume < 0 or amount <= 0:
            raise EastmoneyError(f"unconfirmed final auction for {symbol}")
        observed = datetime.fromtimestamp(stamp, tz=CN_TZ)
        if observed.date() != expected_date:
            raise EastmoneyError(f"final auction timestamp mismatch for {symbol}")
        return AuctionFinal(
            symbol=symbol,
            auction_open=price,
            prev_close=prev_close,
            volume_lots=volume,
            amount=amount,
            source_timestamp=observed.isoformat(timespec="seconds"),
        )
