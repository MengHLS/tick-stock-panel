"""异动边缘统计 — 按交易所异动规则口径实时计算个股接近度。

规则 (近似口径, 与交易所《交易规则》的异常波动/严重异常波动披露阈值对齐;
主板/科创板条款号指上交所《交易规则(2026年修订)》, 2026-07-06 施行):
- 主板:     连续3日收盘价涨跌幅偏离值累计 ±20% (5.4.2)
- 创业板/科创板: 3日 ±30% (科创板 6.10)
- 北交所:   3日 ±40%
- 严重异常波动 (5.4.3/6.11): 10日累计偏离 +100%(-50%), 30日 +200%(-70%) —
  负向阈值显著严于正向 (跌方向更早触发), 各板块相同。
  「10日内4次同向异常波动」情形 (科创板3次) 需事件计数, 暂未实现。
- 风险警示 (ST/*ST): 2026-07-06 起主板风险警示股票涨跌幅限制调整为 10%,
  异常波动特别规定 (原 3日±15% / 10日+50% / 30日+100%) 同步废止,
  与主板普通股票适用同一套标准 (见 price_limits.MAIN_BOARD_ST_LIMIT_CHANGE_DATE)。

偏离值 = 个股从本轮启动点到当前的涨幅 - 对应指数同期涨幅。3 日窗口固定；
10/30 日窗口上限分别为 10/30 个交易日，正向取窗口内最低收盘、负向取最高
收盘，因此实际窗口可能短于上限 (enriched 的 deviate_Nd 仍保留固定 N 日口径)。
「接近度」= |实时偏离| / 该方向阈值: ≥1 已触发, ≥0.7 边缘, ≥0.5 观察。
盘中实时叠加: 历史偏离 (已完成交易日) + 今日实时涨跌 - 基准指数今日涨跌。
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import polars as pl

from app.indicators.pipeline import (
    BENCH_KEYS,
    DEVIATION_WINDOWS,
    bench_rt_pct_for,
    load_benchmark_momentum,
)
from app.market_time import cn_today
from app.services import trading_day


def _is_closed_session() -> bool:
    """工作日休市 (国庆等): 探针确定休市才视为无「今日涨跌」可叠加。未知保持叠加。"""
    return trading_day.is_trading_day() is False

# ── 规则表 ────────────────────────────────────────────────

@dataclass(frozen=True)
class AbnormalRule:
    board: str
    st: bool
    # 各窗口阈值 (小数): {窗口: (正向, 负向)} — 严重异动负向阈值更严 (见模块 docstring)
    thresholds: dict[int, tuple[float, float]]


# 3日异常波动阈值各板块对称; 10/30日严重异动各板块一致且不对称 (+100%/-50%, +200%/-70%)
_MAIN = {3: (0.20, 0.20), 10: (1.00, 0.50), 30: (2.00, 0.70)}
_GEM_STAR = {3: (0.30, 0.30), 10: (1.00, 0.50), 30: (2.00, 0.70)}
_BSE = {3: (0.40, 0.40), 10: (1.00, 0.50), 30: (2.00, 0.70)}

RULES_META: list[dict[str, Any]] = [
    {"board": "主板", "st": False, "thresholds": {f"{k}d": {"up": u, "down": d} for k, (u, d) in _MAIN.items()},
     "note": "3日±20% 异常波动; 严重异常波动 10日+100%(-50%) / 30日+200%(-70%), "
             "负向更严; 2026-07-06 起风险警示(ST)股票同口径 (原±15%特别规定已废止)"},
    {"board": "创业板/科创板", "st": False, "thresholds": {f"{k}d": {"up": u, "down": d} for k, (u, d) in _GEM_STAR.items()},
     "note": "20%涨跌幅板块, 3日±30%"},
    {"board": "北交所", "st": False, "thresholds": {f"{k}d": {"up": u, "down": d} for k, (u, d) in _BSE.items()},
     "note": "30%涨跌幅板块, 3日±40%"},
]

_BENCH_RT_CANDIDATES = ["000002.SH", "000001.SH", "399107.SZ", "399001.SZ", "899050.BJ"]


def _bench_key_of(symbol: str) -> str:
    """symbol → 板块基准键, 与 pipeline._bench_key_expr 同口径 (SH/STAR/SZ/GEM/BJ)。"""
    code = symbol.split(".")[0]
    if symbol.endswith(".BJ"):
        return "BJ"
    if symbol.endswith(".SH"):
        return "STAR" if code.startswith("68") else "SH"
    if symbol.endswith(".SZ"):
        return "GEM" if code.startswith("30") else "SZ"
    return ""


def board_of(symbol: str) -> str:
    """按代码前缀判定板块。"""
    code = symbol.split(".")[0]
    if symbol.endswith(".BJ") or code[:2] in {"43", "83", "87", "92"}:
        return "北交所"
    if code.startswith("68"):
        return "科创板"
    if code.startswith(("30", "301")):
        return "创业板"
    return "主板"


def is_st_name(name: str | None) -> bool:
    return bool(name) and "ST" in str(name).upper()


def rule_for(symbol: str, name: str | None) -> AbnormalRule:
    board = board_of(symbol)
    st = is_st_name(name)
    # 主板风险警示股票 2026-07-06 起与普通股票同标准 (涨跌幅 10%,
    # 异常波动特别规定废止); st 仅为展示标记。创业板/科创板/北交所本就不区分。
    if board == "北交所":
        return AbnormalRule(board, st, _BSE)
    if board in ("创业板", "科创板"):
        return AbnormalRule(board, st, _GEM_STAR)
    return AbnormalRule(board, st, _MAIN)


# ── 快照计算 ──────────────────────────────────────────────

_hist_cache_lock = threading.Lock()
_hist_cache: dict[tuple[int, ...], Any] = {}
_HIST_CACHE_TTL = 60.0
_HIST_CACHE_TTL_ADAPTIVE_MISSING = 10.0

_STATUS_TRIGGERED = "triggered"
_STATUS_EDGE = "edge"
_STATUS_WATCH = "watch"
_ADAPTIVE_WINDOWS = (10, 30)


def _normalize_window(window: str | None) -> int | None:
    """'10d' → 10；None/未知值返回 None。"""
    if window is None:
        return None
    for n in DEVIATION_WINDOWS:
        if window == f"{n}d":
            return n
    return None


def _status_of(closeness: float) -> str:
    if closeness >= 1.0:
        return _STATUS_TRIGGERED
    if closeness >= 0.7:
        return _STATUS_EDGE
    return _STATUS_WATCH


def _hist_snapshot(
    repo: Any,
    windows: tuple[int, ...] | None = None,
) -> dict[str, Any]:
    """enriched 最新日的偏离列快照 (按所需窗口分别缓存 60s)。

    页面选中单一窗口时只读取该窗口的 deviate 列并只重算该窗口的
    自适应启动点；未指定窗口的监控规则仍使用全部窗口。
    """
    requested = tuple(
        n for n in (windows if windows is not None else DEVIATION_WINDOWS)
        if n in DEVIATION_WINDOWS
    )
    if not requested:
        requested = DEVIATION_WINDOWS
    now = time.monotonic()
    with _hist_cache_lock:
        cached = _hist_cache.get(requested)
        if cached is not None:
            ttl = _HIST_CACHE_TTL if cached.get("adaptive_ready") else _HIST_CACHE_TTL_ADAPTIVE_MISSING
            if now - cached["_ts"] < ttl:
                return cached

    df, cache_date = repo.get_enriched_latest()
    rows: dict[str, dict[str, Any]] = {}
    if not df.is_empty() and "symbol" in df.columns:
        deviate_cols = [f"deviate_{n}d" for n in requested]
        cols = [
            c for c in ("symbol", "name", "close", "change_pct", *deviate_cols)
            if c in df.columns
        ]
        df = df.select(cols)
        name_map = repo.get_name_map(df["symbol"].to_list())
        for r in df.iter_rows(named=True):
            symbol = str(r["symbol"])
            row = {
                "name": name_map.get(symbol) or r.get("name"),
                "close": r.get("close"),
                "rt_pct": r.get("change_pct"),
            }
            for n in requested:
                col = f"deviate_{n}d"
                if col in df.columns:
                    row[col] = r.get(col)
            rows[symbol] = row
    adaptive = _load_adaptive_deviation_map(repo, cache_date, rows, requested)
    for symbol, row in rows.items():
        row["adaptive"] = adaptive.get(symbol, {})
    adaptive_required = tuple(n for n in requested if n in _ADAPTIVE_WINDOWS)
    payload = {
        "_ts": now,
        "rows": rows,
        "cache_date": cache_date.isoformat() if cache_date else None,
        "adaptive_ready": bool(adaptive) if adaptive_required else True,
    }
    with _hist_cache_lock:
        _hist_cache[requested] = payload
    return payload


def _finite_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _bench_close_on_date(
    bench_by_key: dict[str, dict[date, float]],
    bench_key: str,
    target: date,
) -> float | None:
    """取基准日精确对应的收盘点位；缺行时 fail closed。"""
    return (bench_by_key.get(bench_key) or {}).get(target)


def _load_adaptive_deviation_map(
    repo: Any,
    cache_date: date | None,
    rows: dict[str, dict[str, Any]],
    windows: tuple[int, ...] | None = None,
) -> dict[str, dict[str, dict[str, Any]]]:
    """按本轮上涨启动点重算偏离，供异动页和压制弹窗使用。

    固定交易所口径从 T-N 取基准；这里改为在 T-N..T-1 的实际收盘中找
    正向最低点（负向最高点），实际窗口可短于 N 日。它只影响异动展示和
    压制位，不改 enriched 的全局 deviate_* 因子口径。
    """
    adaptive_windows = tuple(
        n for n in (windows if windows is not None else _ADAPTIVE_WINDOWS)
        if n in _ADAPTIVE_WINDOWS
    )
    if cache_date is None or not rows or not adaptive_windows:
        return {}
    data_dir = getattr(getattr(repo, "store", None), "data_dir", None)
    get_history = getattr(repo, "get_enriched_history", None)
    if data_dir is None or not callable(get_history):
        return {}

    history_end = cache_date
    get_span = getattr(repo, "get_enriched_history_span", None)
    if callable(get_span):
        try:
            span = get_span()
        except Exception:  # noqa: BLE001
            span = None
        if span is not None and span[1] < history_end:
            # 盘中实时缓存只更新 _enriched_cache，历史缓存可能仍停在昨收；
            # 本轮启动点只需截至昨收的历史，今天现价由快照 close 提供。
            history_end = span[1]

    lookback_days = max(adaptive_windows) + 1
    try:
        history = get_history(history_end, lookback_days)
    except Exception:  # noqa: BLE001 - 历史缓存不可用时保留固定口径
        return {}
    if history is None:
        # 实时 flush 只更新 _enriched_cache，历史缓存可能仍停在最近收盘；
        # 向前退几个自然日找到可用历史末行，今天现价仍由快照 close 提供。
        for back in range(1, 15):
            try:
                history = get_history(
                    history_end - timedelta(days=back),
                    lookback_days,
                )
            except Exception:  # noqa: BLE001
                break
            if history is not None:
                break
    if (
        history is None
        or history.is_empty()
        or not {"symbol", "date", "close"}.issubset(history.columns)
    ):
        return {}
    history_max = history["date"].max()
    if not isinstance(history_max, date) or (cache_date - history_max).days > 21:
        return {}

    bench = load_benchmark_momentum(data_dir)
    if bench is None or bench.is_empty():
        return {}

    bench_by_key: dict[str, dict[date, float]] = {}
    for item in bench.iter_rows(named=True):
        bench_key = item.get("bench_key")
        trade_date = item.get("date")
        close = _finite_float(item.get("bench_close"))
        if not bench_key or not isinstance(trade_date, date) or close is None or close <= 0:
            continue
        bench_by_key.setdefault(bench_key, {})[trade_date] = close

    series: dict[str, list[tuple[date, float]]] = {}
    selected = history.select(["symbol", "date", "close"]).drop_nulls().unique(
        subset=["symbol", "date"], keep="last"
    ).sort(["symbol", "date"])
    for item in selected.iter_rows(named=True):
        symbol = str(item["symbol"])
        trade_date = item["date"]
        close = _finite_float(item["close"])
        if not isinstance(trade_date, date) or close is None or close <= 0:
            continue
        series.setdefault(symbol, []).append((trade_date, close))

    adaptive: dict[str, dict[str, dict[str, Any]]] = {}
    for symbol, base in rows.items():
        current_close = _finite_float(base.get("close"))
        bench_key = _bench_key_of(symbol)
        points = series.get(symbol)
        if current_close is None or current_close <= 0 or not bench_key or not points:
            continue
        prior = [(day, close) for day, close in points if day < cache_date]
        if not prior:
            continue
        bench_now = _bench_close_on_date(bench_by_key, bench_key, cache_date)
        if bench_now is None:
            continue

        for n in adaptive_windows:
            window = prior[-n:]
            if not window:
                continue
            official = _finite_float(base.get(f"deviate_{n}d"))
            positive = official >= 0 if official is not None else current_close >= window[-1][1]
            best_index = 0
            for index in range(1, len(window)):
                if positive:
                    if window[index][1] < window[best_index][1]:
                        best_index = index
                elif window[index][1] > window[best_index][1]:
                    best_index = index

            base_date, base_close = window[best_index]
            bench_base = _bench_close_on_date(bench_by_key, bench_key, base_date)
            if (
                bench_base is None
                or bench_base <= 0
                or base_close <= 0
            ):
                continue
            stock_return = current_close / base_close - 1.0
            bench_return = bench_now / bench_base - 1.0
            value = stock_return - bench_return
            direction = "up" if value >= 0 else "down"
            effective_days = len(window) - best_index
            adaptive.setdefault(symbol, {})[f"{n}d"] = {
                "value": value,
                "direction": direction,
                "effective_days": effective_days,
                "base_date": base_date.isoformat(),
                "base_close": base_close,
                "bench_base": bench_base,
                "bench_now": bench_now,
            }
    return adaptive


def _bench_rt_pct(quote_service: Any) -> float:
    """基准指数今日实时涨跌 (各候选均值, 小数制, 缺数据时 0)。

    quote_service.get_index_quotes() 返回指数展示缓存, change_pct/pct/pct_change
    为百分数口径 (CONTRIBUTING §3.1), 消费前显式 /100, 与 enriched 侧小数制
    change_pct 对齐 (#232); close/prev_close 兜底路径本身是小数, 不转换。
    """
    try:
        df = quote_service.get_index_quotes()
    except Exception:
        return 0.0
    if df is None or df.is_empty():
        return 0.0
    df = df.filter(pl.col("symbol").is_in(_BENCH_RT_CANDIDATES))
    if df.is_empty():
        return 0.0
    for col in ("change_pct", "pct", "pct_change"):
        if col in df.columns:
            vals = df[col].drop_nulls()
            if vals.len() > 0:
                return float(vals.mean()) / 100.0
    if {"close", "prev_close"} <= set(df.columns):
        sub = df.select(["close", "prev_close"]).drop_nulls()
        if sub.height > 0:
            return float((sub["close"] / sub["prev_close"] - 1).mean())
    return 0.0


def build_overview(
    repo: Any,
    quote_service: Any = None,
    *,
    min_closeness: float = 0.5,
    limit: int = 200,
    window: str | None = None,
    direction: str = "both",
    board: str | None = None,
    boards: set[str] | None = None,
    exclude_st: bool = False,
    symbols: set[str] | None = None,
    query: str | None = None,
) -> dict[str, Any]:
    """返回异动边缘总览: 规则表 + 按接近度排序的个股列表。

    筛选必须在 ``limit`` 截断之前完成。调用方 (页面/监控规则) 会按窗口、
    方向、板块等继续过滤; 若先截断再过滤, 接近度靠前但板块/窗口不匹配的
    标的会占满结果, 让其余筛选项看起来“没有数据”。
    """
    window_number = _normalize_window(window)
    window_key = f"{window_number}d" if window_number is not None else None
    requested_windows = (window_number,) if window_number is not None else DEVIATION_WINDOWS
    hist = _hist_snapshot(repo, requested_windows)
    cache_date = hist.get("cache_date")
    hist_rows: dict[str, dict[str, Any]] = hist["rows"]

    bench_rt = _bench_rt_pct(quote_service) if quote_service is not None else 0.0
    # 实时叠加按板块基准: 科创板减科创50、创业板减创业板综指, 不再全市场混均值
    bench_by_key: dict[str, float] = {}
    if quote_service is not None:
        try:
            index_quotes = quote_service.get_index_quotes()
        except Exception:
            index_quotes = None
        for k in BENCH_KEYS:
            bench_by_key[k] = bench_rt_pct_for(index_quotes, k)
    # 快照的 change_pct 属于 cache_date 当日涨跌, 已经含在 deviate_* 里。
    # 只有缓存日早于北京今天、且今天仍是交易日时, 才叠加「今日」涨跌;
    # 周末/节假日没有新的今日涨跌, 再叠一次就是把最近交易日涨跌算两遍。
    today = cn_today()
    includes_today = cache_date is not None and cache_date >= today.isoformat()
    if not includes_today and (today.weekday() >= 5 or _is_closed_session()):
        includes_today = True

    direction_key = direction if direction in ("up", "down") else "both"
    query_key = (query or "").strip().lower()
    board_filter = boards if boards else ({board} if board else None)
    out_rows: list[dict[str, Any]] = []
    for symbol, base in hist_rows.items():
        rule = rule_for(symbol, base.get("name"))
        if board_filter is not None and rule.board not in board_filter:
            continue
        if exclude_st and rule.st:
            continue
        if symbols is not None and symbol not in symbols:
            continue
        if query_key and query_key not in f"{symbol} {base.get('name') or ''}".lower():
            continue
        rt_pct = base.get("rt_pct")
        rt_delta = 0.0 if includes_today else (
            (rt_pct or 0.0) - bench_by_key.get(_bench_key_of(symbol), 0.0)
        )

        windows: dict[str, dict[str, Any]] = {}
        max_closeness = 0.0
        adaptive = base.get("adaptive") or {}
        for n in requested_windows:
            window_key_n = f"{n}d"
            adaptive_item = adaptive.get(window_key_n) if isinstance(adaptive, dict) else None
            if adaptive_item is not None:
                hist_dev = _finite_float(adaptive_item.get("value"))
                window_days = adaptive_item.get("effective_days")
                base_date = adaptive_item.get("base_date")
            else:
                hist_dev = base.get(f"deviate_{n}d")
                window_days = None
                base_date = None
            if hist_dev is None:
                continue
            live = hist_dev + rt_delta
            up_t, down_t = rule.thresholds[n]
            threshold = up_t if live >= 0 else down_t
            closeness = abs(live) / threshold if threshold > 0 else 0.0
            windows[window_key_n] = {
                "value": round(live, 4),
                "threshold": threshold,
                "closeness": round(closeness, 4),
                "window_days": int(window_days) if window_days is not None else n,
                "base_date": base_date,
            }
            max_closeness = max(max_closeness, closeness)
        if not windows or max_closeness < min_closeness:
            continue
        focus_closeness = max_closeness
        if window_key is not None:
            selected = windows.get(window_key)
            if selected is None or selected["closeness"] < min_closeness:
                continue
            focus_closeness = selected["closeness"]
        if direction_key != "both":
            focus = windows.get(window_key) if window_key else max(
                windows.values(), key=lambda w: w["closeness"]
            )
            if (direction_key == "up" and focus["value"] <= 0) or (
                direction_key == "down" and focus["value"] >= 0
            ):
                continue
        out_rows.append({
            "symbol": symbol,
            "name": base.get("name"),
            "board": rule.board,
            "st": rule.st,
            "close": base.get("close"),
            "rt_pct": rt_pct,
            "windows": windows,
            "max_closeness": round(max_closeness, 4),
            "focus_closeness": round(focus_closeness, 4),
            "status": _status_of(focus_closeness),
        })

    out_rows.sort(key=lambda r: r["focus_closeness"], reverse=True)
    total = len(out_rows)
    counts = {
        _STATUS_TRIGGERED: sum(1 for r in out_rows if r["status"] == _STATUS_TRIGGERED),
        _STATUS_EDGE: sum(1 for r in out_rows if r["status"] == _STATUS_EDGE),
        _STATUS_WATCH: sum(1 for r in out_rows if r["status"] == _STATUS_WATCH),
    }
    return {
        "asof": time.time(),
        "cache_date": cache_date,
        "bench_rt_pct": round(bench_rt, 4),
        "includes_today": includes_today,
        "rules": RULES_META,
        "counts": counts,
        "total": total,
        "rows": out_rows[:limit],
    }


# ================================================================
# 异动阈值价格压制 (弹窗「后续上涨空间」)
#
# 交易所异动阈值是偏离值上限。把阈值反解成收盘价, 就是当前窗口的
# 「压制价」; 窗口每个交易日向前滚动, 因此明日/后日的压制价要按新的
# N 日基准重算, 不能把今天的压制价当成固定值。
#
# 推导 (小数口径; P_base / B_base 为本轮启动点):
#   deviate_N = P_now / P_base - 1 - (B_now / B_base - 1)
#             = P_now / P_base - B_now / B_base
#   P_cap = P_base * (threshold + B_now / B_base)
#         = P_now + P_base * (threshold - deviate_N)
#
# 对第 k 个未来交易日, 基准日向前滚动 k 个交易日, B_now 假设保持当前
# 指数点位。只使用已经发生的历史基准日, 不引入未来个股价格。
# ================================================================

_SUPPRESSION_MAX_FORWARD_DAYS = 10


def _as_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _suppression_sort_key(window: dict[str, Any]) -> tuple[int, float]:
    """最临近的压制窗口: 已越过阈值优先, 其次按剩余空间由近到远。"""
    today = (window.get("days") or [{}])[0]
    room = float(today.get("room_pct") or 0.0)
    if window.get("direction") == "down":
        return (0 if room > 0 else 1, -room)
    return (0 if room < 0 else 1, room)


def _adaptive_base_index(
    closes: list[float],
    last_index: int,
    window: int,
    direction: str,
    offset: int,
) -> int | None:
    """未来第 offset 个交易日对应的本轮启动低/高点索引。

    未来价格未知时沿用已有历史：上涨方向假定未来价格不低于当前低点，
    因此低点只有滚出窗口后才会切换。这样今日/明日仍使用同一个启动点。
    """
    end = last_index + offset
    low = max(0, end - window)
    high = min(last_index, end - 1)
    if high < low:
        return None
    best = low
    for index in range(low + 1, high + 1):
        if direction == "up":
            if closes[index] < closes[best]:
                best = index
        elif closes[index] > closes[best]:
            best = index
    return best


def build_suppression_schedule(
    repo: Any,
    *,
    symbol: str,
    forward_days: int = 5,
    window: str | None = None,
) -> dict[str, Any]:
    """返回各偏离窗口的收盘价压制位与后续交易日剩余空间。

    参数:
        symbol: 个股代码。
        forward_days: 向后测算的交易日数 (0=仅今日), 上限 10。
        window: 仅测算指定偏离窗口; 省略时保留全部窗口 (监控兼容路径)。

    返回 ``windows`` 中每个窗口包含 ``threshold`` / ``direction`` /
    ``current_deviation`` / ``days``; ``days[0]`` 为今日, ``days[k]`` 为
    第 k 个未来交易日。``room_pct`` 为相对现价的百分比空间:
      - direction=up: 正数=距上方压制价还剩多少, 负数=已越过压制价;
      - direction=down: 负数=距下方压制价还剩多少, 正数=已跌破压制价。
    """
    symbol = symbol.strip().upper()
    forward_days = max(0, min(int(forward_days), _SUPPRESSION_MAX_FORWARD_DAYS))
    window_number = _normalize_window(window)
    requested_windows = (window_number,) if window_number is not None else DEVIATION_WINDOWS
    hist = _hist_snapshot(repo, requested_windows)
    cache_date = hist.get("cache_date")
    base = (hist.get("rows") or {}).get(symbol)
    if not base:
        return {"symbol": symbol, "windows": {}, "reason": "no_snapshot"}

    name = base.get("name")
    close = base.get("close")
    if close is None or not math.isfinite(float(close)) or float(close) <= 0:
        return {"symbol": symbol, "name": name, "windows": {}, "reason": "no_close"}

    rule = rule_for(symbol, name)
    bench_key = _bench_key_of(symbol)
    data_dir = getattr(getattr(repo, "store", None), "data_dir", None)
    if not bench_key or data_dir is None:
        return {"symbol": symbol, "name": name, "windows": {}, "reason": "no_benchmark"}

    bench = load_benchmark_momentum(data_dir)
    if bench is None or bench.is_empty():
        return {"symbol": symbol, "name": name, "windows": {}, "reason": "no_benchmark"}
    bench = bench.filter(pl.col("bench_key") == bench_key).sort("date")
    bench_by_date = {
        row["date"]: float(row["bench_close"])
        for row in bench.iter_rows(named=True)
        if row.get("date") is not None and row.get("bench_close") is not None
    }
    if not bench_by_date:
        return {"symbol": symbol, "name": name, "windows": {}, "reason": "no_benchmark"}

    end = _as_date(cache_date) or cn_today()
    start = end - timedelta(days=180)
    try:
        stock = repo.get_daily(symbol, start, end)
    except Exception:  # noqa: BLE001 - 数据不可用时降级为空, 弹窗不阻塞
        stock = pl.DataFrame()
    if stock.is_empty() or not {"date", "close"}.issubset(stock.columns):
        return {"symbol": symbol, "name": name, "windows": {}, "reason": "no_history"}

    stock = (
        stock.select(["date", "close"])
        .drop_nulls()
        .unique(subset=["date"], keep="last")
        .sort("date")
    )
    stock = stock.with_columns(pl.col("date").cast(pl.Date))
    stock = stock.filter(pl.col("date") <= end)
    # 最新快照可能含今日实时行; 以快照 close 为准, 避免日线末行与弹窗现价不一致。
    stock = stock.filter(pl.col("date") != end)
    if stock.is_empty():
        return {"symbol": symbol, "name": name, "windows": {}, "reason": "no_history"}
    stock = pl.concat(
        [
            stock,
            pl.DataFrame({"date": [end], "close": [float(close)]}, schema_overrides={
                "date": pl.Date,
                "close": pl.Float64,
            }),
        ],
        how="vertical_relaxed",
    ).sort("date")

    dates = stock["date"].to_list()
    closes = [float(value) for value in stock["close"].to_list()]
    last_index = len(dates) - 1
    if last_index < min(requested_windows):
        return {"symbol": symbol, "name": name, "windows": {}, "reason": "insufficient_history"}

    windows: dict[str, dict[str, Any]] = {}
    missing_history = False
    adaptive_by_window = base.get("adaptive") or {}
    if not isinstance(adaptive_by_window, dict):
        adaptive_by_window = {}
    for n in requested_windows:
        up_threshold, down_threshold = rule.thresholds[n]
        adaptive_item = adaptive_by_window.get(f"{n}d")
        adaptive_used = False
        if isinstance(adaptive_item, dict):
            deviate = _finite_float(adaptive_item.get("value"))
            direction = adaptive_item.get("direction")
            p_base = _finite_float(adaptive_item.get("base_close"))
            b_base = _finite_float(adaptive_item.get("bench_base"))
            b_now = _finite_float(adaptive_item.get("bench_now"))
            if (
                deviate is not None
                and direction in ("up", "down")
                and p_base is not None
                and p_base > 0
                and b_base is not None
                and b_base > 0
                and b_now is not None
                and b_now > 0
            ):
                adaptive_used = True
                threshold = up_threshold if direction == "up" else down_threshold
                signed_threshold = threshold if direction == "up" else -threshold
                effective_days = int(adaptive_item.get("effective_days") or n)
            else:
                adaptive_used = False

        if not adaptive_used:
            deviate = base.get(f"deviate_{n}d")
            if deviate is None:
                continue
            deviate = float(deviate)
            if not math.isfinite(deviate):
                continue
            direction = "up" if deviate >= 0 else "down"
            threshold = up_threshold if direction == "up" else down_threshold
            signed_threshold = threshold if direction == "up" else -threshold
            effective_days = n

            base_index = last_index - n
            if base_index < 0:
                missing_history = True
                continue
            p_base = closes[base_index]
            b_base = bench_by_date.get(dates[base_index])
            if (
                not math.isfinite(p_base)
                or p_base <= 0
                or b_base is None
                or not math.isfinite(b_base)
                or b_base <= 0
            ):
                missing_history = True
                continue

            # B_now / B_base 由当前偏离反解: deviate = P_now / P_base - B_now / B_base
            bench_ratio_now = close / p_base - deviate
            if not math.isfinite(bench_ratio_now) or bench_ratio_now <= 0:
                missing_history = True
                continue
            b_now = b_base * bench_ratio_now
        else:
            base_index = None

        days: list[dict[str, Any]] = []
        max_offset = min(forward_days, n)
        for offset in range(max_offset + 1):
            if adaptive_used:
                index = _adaptive_base_index(
                    closes, last_index, n, direction, offset,
                )
            else:
                index = base_index + offset
            if index is None or index < 0:
                continue
            p_window_base = closes[index]
            b_window_base = bench_by_date.get(dates[index])
            if (
                not math.isfinite(p_window_base)
                or p_window_base <= 0
                or b_window_base is None
                or not math.isfinite(b_window_base)
                or b_window_base <= 0
            ):
                continue
            cap = p_window_base * (signed_threshold + b_now / b_window_base)
            if not math.isfinite(cap) or cap <= 0:
                continue
            days.append({
                "offset": offset,
                "base_date": dates[index].isoformat(),
                "cap": round(cap, 3),
                "room_pct": round(cap / close - 1.0, 4),
            })
        if not days:
            missing_history = True
            continue
        windows[f"{n}d"] = {
            "threshold": threshold,
            "direction": direction,
            "current_deviation": round(deviate, 4),
            "effective_days": effective_days,
            "days": days,
        }

    if not windows:
        return {
            "symbol": symbol,
            "name": name,
            "windows": {},
            "reason": "insufficient_history" if missing_history else "no_deviation",
        }

    nearest_key = min(windows, key=lambda key: _suppression_sort_key(windows[key]))
    nearest_day = windows[nearest_key]["days"][0]
    return {
        "symbol": symbol,
        "name": name,
        "asof": cache_date,
        "close": round(float(close), 3),
        "bench_key": bench_key,
        "windows": windows,
        "nearest": {
            "window": nearest_key,
            "direction": windows[nearest_key]["direction"],
            "room_pct": nearest_day["room_pct"],
        },
    }


# ================================================================
# 盘中异动 (量价信号聚合, 异动监控「盘中」tab)
#
# 数据源: enriched 最新快照的当日消息号列 (零新增采集):
# 涨停/跌停/跌停翘板/炸板/放量(量比≥2)/创60日新高/新低。
# 行序 = 信号优先级 (涨停 > 炸板 > 翘板 > 跌停 > 新高 > 新低 > 放量),
# 同级按 |今日涨跌| 降序; counts 供前端筛选 chips 展示各类型数量。
# ================================================================

_INTRADAY_SIGNALS: tuple[tuple[str, str], ...] = (
    ("signal_limit_up", "limit_up"),
    ("signal_broken_limit_up", "broken"),
    ("signal_limit_down_recovery", "recovery"),
    ("signal_limit_down", "limit_down"),
    ("signal_n_day_high", "new_high"),
    ("signal_n_day_low", "new_low"),
    ("signal_volume_surge", "volume_surge"),
)
_INTRADAY_PRIORITY = {key: i for i, (_, key) in enumerate(_INTRADAY_SIGNALS)}
_INTRADAY_COLS = ("symbol", "name", "close", "change_pct", "amplitude",
                  "vol_ratio_5d", "turnover_rate", "consecutive_limit_ups")


def build_intraday(repo: Any, limit: int = 500) -> dict[str, Any]:
    """enriched 最新快照 → 当日异动信号命中行 (含各类型计数)。"""
    df, cache_date = repo.get_enriched_latest()
    empty = {"cache_date": cache_date.isoformat() if cache_date else None,
             "counts": {}, "rows": []}
    if df.is_empty() or "symbol" not in df.columns:
        return empty
    present = [(c, k) for c, k in _INTRADAY_SIGNALS if c in df.columns]
    if not present:
        return empty

    hits = df.filter(pl.any_horizontal([pl.col(c).fill_null(False) for c, _ in present]))
    if hits.is_empty():
        return empty
    counts = {k: int(hits[c].fill_null(False).sum()) for c, k in present}

    sig_cols = {k: hits[c].fill_null(False).to_list() for c, k in present}
    base_cols = [c for c in _INTRADAY_COLS if c in hits.columns]
    base = hits.select(base_cols).to_dicts()
    name_map = repo.get_name_map([str(r["symbol"]) for r in base])
    rows: list[dict[str, Any]] = []
    for i, r in enumerate(base):
        signals = [k for k, flags in sig_cols.items() if flags[i]]
        symbol = str(r["symbol"])
        rows.append({
            **{c: r.get(c) for c in base_cols},
            "name": name_map.get(symbol) or r.get("name"),
            "signals": signals,
            "_prio": min((_INTRADAY_PRIORITY[s] for s in signals), default=99),
        })
    rows.sort(key=lambda r: (r["_prio"], -abs(r.get("change_pct") or 0.0)))
    for r in rows:
        r.pop("_prio", None)
    return {"cache_date": cache_date.isoformat() if cache_date else None,
            "counts": counts, "rows": rows[:limit]}
