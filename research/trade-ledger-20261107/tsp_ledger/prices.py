"""行情读取：从系统行情库取不复权收盘价，构造 PriceBook。

只读，不写行情库；不涉及复权、行情新鲜度、回测与信号逻辑。

价格源优先级
------------
1. ``data/kline_daily``（原始日线，不复权 —— 复盘估值口径以此为准）
2. ``data/kline_daily_enriched``（日线富化表，前复权；仅当原始日线缺该日分区时兜底。
   本单 2026-10-26 原始日线整个分区缺失，只有富化表有数据，且该股当日无除权，
   补出来的价格与原始口径一致）
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .derive import PriceBook, TradingCalendar

PRICE_ROOTS = (
    Path(r"D:\TSP\data\kline_daily"),
    Path(r"D:\TSP\data\kline_daily_enriched"),
)
DEFAULT_PRICE_ROOT = PRICE_ROOTS[0]


def _days_of(root: Path) -> list[str]:
    root = Path(root)
    if not root.exists():
        return []
    out = []
    for p in root.glob("date=*"):
        d = p.name.split("=", 1)[1]
        if len(d) == 10 and d[4] == "-":
            out.append(d)
    return out


def available_days(roots: Iterable[Path] = PRICE_ROOTS) -> list[str]:
    days: set[str] = set()
    for r in roots:
        days.update(_days_of(Path(r)))
    return sorted(days)


def load_calendar(roots: Iterable[Path] = PRICE_ROOTS) -> TradingCalendar:
    return TradingCalendar(available_days(roots))


def load_prices(
    codes: Iterable[str],
    start: str,
    end: str,
    roots: Iterable[Path] = PRICE_ROOTS,
) -> PriceBook:
    """读取 [start, end] 内指定代码的收盘价。

    依赖 polars（随系统后端环境提供）。缺 polars 或缺行情库时返回空 PriceBook，
    调用方可退化到 last_trade 口径，不会抛错。
    """
    try:
        import polars as pl
    except Exception:  # pragma: no cover - 环境缺依赖
        return PriceBook({})

    wanted = {
        f"{c}.SH" if c.startswith(("6", "9", "5")) else f"{c}.SZ" for c in codes
    }
    closes: dict[str, dict[str, float]] = {}
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        for day in _days_of(root):
            if day < start or day > end:
                continue
            f = root / f"date={day}" / "part.parquet"
            if not f.exists():
                continue
            try:
                df = pl.read_parquet(f, columns=["symbol", "close"]).filter(
                    pl.col("symbol").is_in(wanted)
                )
            except Exception:
                continue
            if not df.height:
                continue
            for sym, close in df.iter_rows():
                if close is None:
                    continue
                code = sym.split(".")[0]
                # 先写入的源优先：原始日线在前，富化表只补缺日缺码
                closes.setdefault(code, {}).setdefault(day, float(close))
    return PriceBook(closes)
