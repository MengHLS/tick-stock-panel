"""Normalize Fuyao's limit-up and limit-break pools as positive evidence."""

from __future__ import annotations

import math
import re
from datetime import date, datetime, time

from app.market_time import CN_TZ
from app.plugins.fuyao.client import FuyaoClient
from app.plugins.fuyao.provider import _ms_of_date

_SYMBOL = re.compile(r"^\d{6}\.(SH|SZ|BJ)$")
_TIME = re.compile(r"^\d{2}:\d{2}$")
_MAX_PAGES = 20


def _number(value, *, integer: bool = False):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("Boolean received for a numeric pool field")
    try:
        parsed = float(value)
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid numeric pool field") from exc
    if not math.isfinite(parsed) or parsed < 0 or (integer and not parsed.is_integer()):
        raise ValueError("Invalid nonnegative pool field")
    return int(parsed) if integer else parsed


def _clock(value) -> tuple[str | None, int | None]:
    if value is None or value == "":
        return None, None
    if not isinstance(value, str) or not _TIME.fullmatch(value):
        raise ValueError("Invalid pool time; expected Beijing HH:MM")
    clock = time.fromisoformat(value)
    if not (time(9, 25) <= clock <= time(11, 30) or time(13) <= clock <= time(15)):
        raise ValueError("Pool time outside A-share trading sessions")
    return value, clock.hour * 60 + clock.minute


def _ready_at(value, day: date) -> str:
    stamp = _number(value, integer=True)
    if not stamp:
        raise ValueError("Pool ready timestamp is missing")
    ready = datetime.fromtimestamp(stamp / 1000, CN_TZ)
    if ready < datetime.combine(day, time(15), CN_TZ):
        raise ValueError("Pool is not ready for the requested completed trading day")
    return ready.isoformat()


def _fetch_pool(
    client: FuyaoClient,
    kind: str,
    day: date,
    page_size: int,
) -> tuple[list[dict], str]:
    collected: list[dict] = []
    total = pages = None
    ready = None
    for page in range(1, _MAX_PAGES + 1):
        data = client._get(
            f"/api/a-share/special-data/{kind}",
            {"date_ms": _ms_of_date(day), "page": page, "size": page_size},
        )
        pagination = data.get("pagination")
        rows = data.get("item")
        if not isinstance(pagination, dict) or not isinstance(rows, list):
            raise ValueError("Pool response missing pagination/item")
        metadata = [pagination.get(key) for key in ("total", "pages", "page", "size")]
        if any(type(value) is not int for value in metadata):
            raise ValueError("Invalid pool pagination")
        count, page_count, echoed_page, size = metadata
        if (
            count < 0
            or not 0 <= page_count <= _MAX_PAGES
            or echoed_page != page
            or size != page_size
        ):
            raise ValueError("Pool pagination inconsistent or exceeds safety limit")
        expected_pages = math.ceil(count / page_size)
        if (count and page_count != expected_pages) or (not count and page_count not in (0, 1)):
            raise ValueError("Pool pagination total/pages mismatch")
        if total is not None and (count != total or page_count != pages):
            raise ValueError("Pool changed during pagination; retry the completed day")
        total, pages = count, page_count
        expected_rows = min(page_size, max(0, count - (page - 1) * page_size))
        if len(rows) != expected_rows or any(not isinstance(row, dict) for row in rows):
            raise ValueError("Incomplete pool page")
        page_ready = _ready_at(data.get("timestamp"), day)
        ready = ready or page_ready
        collected.extend(rows)
        if page >= page_count:
            break
    if total is None or pages is None or ready is None or len(collected) != total:
        raise ValueError("Incomplete pool response")

    symbols: list[str] = []
    for row in collected:
        symbol = row.get("thscode")
        if not isinstance(symbol, str) or not _SYMBOL.fullmatch(symbol):
            raise ValueError("Invalid pool symbol")
        symbols.append(symbol)
        if row.get("date") is not None and str(row["date"])[:10] != day.isoformat():
            raise ValueError("Pool row date differs from requested trading day")
        if row.get("date_ms") is not None:
            try:
                row_day = datetime.fromtimestamp(int(row["date_ms"]) / 1000, CN_TZ).date()
            except (TypeError, ValueError, OSError) as exc:
                raise ValueError("Invalid pool row date_ms") from exc
            if row_day != day:
                raise ValueError("Pool row date_ms differs from requested trading day")
    if len(set(symbols)) != len(symbols):
        raise ValueError("Duplicate symbols in pool response")
    return collected, ready


def fetch_limit_board_events(
    client: FuyaoClient,
    day: date,
    *,
    page_size: int = 200,
) -> list[dict]:
    """Return one normalized row per symbol after both complete pools succeed.

    Membership is positive evidence (1) or unknown (None). A missing row in
    the break pool is not evidence of zero intraday opens.
    """
    if not 1 <= page_size <= 200:
        raise ValueError("page_size must be in 1..200")

    up_rows, up_ready = _fetch_pool(client, "limit-up-pool", day, page_size)
    break_rows, break_ready = _fetch_pool(client, "limit-break-pool", day, page_size)
    up = {row["thscode"]: row for row in up_rows}
    broken = {row["thscode"]: row for row in break_rows}
    retrieved_at = datetime.now(CN_TZ).isoformat()

    result = []
    for symbol in sorted(up.keys() | broken.keys()):
        up_row = up.get(symbol, {})
        break_row = broken.get(symbol, {})
        up_count = _number(up_row.get("open_times"), integer=True)
        break_count = _number(break_row.get("open_times"), integer=True)
        limit_time, limit_minute = _clock(up_row.get("limit_up_time"))
        first_time, first_minute = _clock(break_row.get("first_seal_time"))
        last_time, last_minute = _clock(break_row.get("last_seal_time"))
        if first_minute is not None and last_minute is not None and first_minute > last_minute:
            raise ValueError("First seal time is after last seal time")
        result.append(
            {
                "trade_date": day.isoformat(),
                "symbol": symbol,
                "name": up_row.get("name") or break_row.get("name"),
                "in_limit_up_pool": 1 if up_row else None,
                "in_limit_break_pool": 1 if break_row else None,
                "observed_open": (
                    1
                    if break_row or (up_count is not None and up_count > 0)
                    else 0
                    if up_count == 0
                    else None
                ),
                "continue_day_cnt": _number(up_row.get("continue_day_cnt"), integer=True),
                "limit_up_reason": up_row.get("limit_up_reason") or None,
                "limit_up_time": limit_time,
                "limit_up_minute": limit_minute,
                "first_seal_time": first_time,
                "first_seal_minute": first_minute,
                "last_seal_time": last_time,
                "last_seal_minute": last_minute,
                "limit_up_pool_open_times": up_count,
                "break_pool_open_times": break_count,
                "seal_money": _number(up_row.get("seal_money")),
                "max_seal_money": _number(up_row.get("max_seal_money")),
                "turnover": _number(break_row.get("turnover")),
                "turnover_ratio_pct": _number(break_row.get("turnover_ratio_pct")),
                "up_source_ready_at": up_ready if up_row else None,
                "break_source_ready_at": break_ready if break_row else None,
                "retrieved_at": retrieved_at,
            }
        )
    return result
