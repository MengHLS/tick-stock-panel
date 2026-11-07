"""落库层：SQLite 台账，重复导入幂等。

库位置默认 ``<data_root>/user_data/trade_ledger/ledger.sqlite``，
与系统既有 user_data 规范一致（data_root 默认 D:\\TSP\\data）。

表
--
* ``import_batch``  每次导入的批次（文件哈希、编码、行数、去重结果）
* ``event``         事件级明细，主键 event_uid，重复导入只增不重
* ``roundtrip``     FIFO 回合（可重建）
* ``daily_equity``  日频权益（可重建）
* ``daily_position``日终持仓明细（可重建）
* ``exposure``      单票/行业暴露（可重建）
* ``meta``          口径版本号等
"""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

from .parse import Event

PARSER_VERSION = "1.0.0"
DEFAULT_DATA_ROOT = Path(r"D:\TSP\data")
LEDGER_SUBDIR = Path("user_data") / "trade_ledger"

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS import_batch (
    batch_id TEXT PRIMARY KEY,
    source_file TEXT NOT NULL,
    file_sha256 TEXT NOT NULL,
    encoding TEXT NOT NULL,
    bytes INTEGER NOT NULL,
    rows_total INTEGER NOT NULL,
    rows_skipped INTEGER NOT NULL,
    rows_new INTEGER NOT NULL,
    rows_dup INTEGER NOT NULL,
    date_min TEXT,
    date_max TEXT,
    imported_at TEXT NOT NULL,
    parser_version TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS event (
    event_uid TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    settle_date TEXT,
    trade_time TEXT,
    code TEXT,
    name TEXT,
    raw_type TEXT NOT NULL,
    category TEXT NOT NULL,
    qty INTEGER NOT NULL DEFAULT 0,
    price REAL NOT NULL DEFAULT 0,
    amount REAL NOT NULL DEFAULT 0,
    cash REAL NOT NULL DEFAULT 0,
    comm REAL NOT NULL DEFAULT 0,
    other_fee REAL NOT NULL DEFAULT 0,
    stamp REAL NOT NULL DEFAULT 0,
    transfer_fee REAL NOT NULL DEFAULT 0,
    shares_after INTEGER NOT NULL DEFAULT 0,
    cash_after REAL NOT NULL DEFAULT 0,
    deal_no TEXT,
    holder TEXT,
    serial TEXT,
    market TEXT,
    ccy TEXT,
    kind TEXT,
    side TEXT,
    net_px REAL NOT NULL DEFAULT 0,
    row_no INTEGER,
    source_file TEXT,
    date_from_settle INTEGER NOT NULL DEFAULT 0,
    imported_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_event_date ON event(trade_date);
CREATE INDEX IF NOT EXISTS idx_event_code ON event(code, trade_date);
CREATE TABLE IF NOT EXISTS roundtrip (
    batch_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    code TEXT,
    name TEXT,
    kind TEXT,
    open_time TEXT,
    close_time TEXT,
    qty INTEGER,
    buy_px REAL,
    sell_px REAL,
    cost REAL,
    pnl REAL,
    ret REAL,
    hold_days REAL,
    hold_td REAL,
    unmatched_qty INTEGER DEFAULT 0,
    pnl_adj REAL,
    flags TEXT,
    sell_event_uid TEXT,
    PRIMARY KEY (batch_id, seq)
);
CREATE TABLE IF NOT EXISTS daily_equity (
    batch_id TEXT NOT NULL,
    date TEXT NOT NULL,
    equity REAL, mv REAL, cash REAL, dep REAL, cumdep REAL, pnl REAL, npos INTEGER,
    PRIMARY KEY (batch_id, date)
);
CREATE TABLE IF NOT EXISTS daily_position (
    batch_id TEXT NOT NULL,
    date TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT,
    kind TEXT,
    qty INTEGER,
    cost REAL,
    price REAL,
    price_src TEXT,
    mv REAL,
    upnl REAL,
    PRIMARY KEY (batch_id, date, code)
);
CREATE TABLE IF NOT EXISTS exposure (
    batch_id TEXT NOT NULL,
    date TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT,
    weight REAL,
    mv REAL,
    equity REAL,
    PRIMARY KEY (batch_id, date, code)
);
"""


def ledger_path(data_root: Path | str = DEFAULT_DATA_ROOT) -> Path:
    return Path(data_root) / LEDGER_SUBDIR / "ledger.sqlite"


def connect(db_path: Path | str) -> sqlite3.Connection:
    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    return con


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


EVENT_COLUMNS = [
    "event_uid", "batch_id", "trade_date", "settle_date", "trade_time", "code", "name",
    "raw_type", "category", "qty", "price", "amount", "cash", "comm", "other_fee",
    "stamp", "transfer_fee", "shares_after", "cash_after", "deal_no", "holder",
    "serial", "market", "ccy", "kind", "side", "net_px", "row_no", "source_file",
    "date_from_settle", "imported_at",
]


def import_events(
    con: sqlite3.Connection,
    events: Sequence[Event],
    source_file: Path,
    encoding: str,
    rows_total: int,
    rows_skipped: int,
) -> dict:
    """写入一个批次，返回 {batch_id, rows_new, rows_dup, ...}。幂等。"""
    src = Path(source_file)
    raw = src.read_bytes()
    file_hash = hashlib.sha256(raw).hexdigest()
    imported_at = datetime.now().astimezone().isoformat(timespec="seconds")
    # 微秒级时间戳：同一秒内连续导入两次不会撞主键（否则第二次会覆盖第一批次的留痕）
    batch_id = f"{datetime.now():%Y%m%dT%H%M%S%f}-{file_hash[:8]}"

    dates = sorted({e.trade_date for e in events if e.trade_date})
    cur = con.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO import_batch (batch_id, source_file, file_sha256, encoding,"
        " bytes, rows_total, rows_skipped, rows_new, rows_dup, date_min, date_max,"
        " imported_at, parser_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (batch_id, str(src), file_hash, encoding, len(raw), rows_total, rows_skipped,
         0, 0, dates[0] if dates else None, dates[-1] if dates else None, imported_at,
         PARSER_VERSION),
    )
    before = con.execute("SELECT COUNT(*) FROM event").fetchone()[0]
    payload = []
    for e in events:
        row = e.as_row()
        row["batch_id"] = batch_id
        row["imported_at"] = imported_at
        row["date_from_settle"] = int(row["date_from_settle"])
        payload.append(tuple(row.get(c) for c in EVENT_COLUMNS))
    cur.executemany(
        f"INSERT OR IGNORE INTO event ({','.join(EVENT_COLUMNS)}) VALUES ({','.join('?'*len(EVENT_COLUMNS))})",
        payload,
    )
    after = con.execute("SELECT COUNT(*) FROM event").fetchone()[0]
    rows_new = after - before
    rows_dup = len(events) - rows_new
    cur.execute(
        "UPDATE import_batch SET rows_new=?, rows_dup=? WHERE batch_id=?",
        (rows_new, rows_dup, batch_id),
    )
    con.commit()
    return {
        "batch_id": batch_id,
        "file_sha256": file_hash,
        "rows_total": rows_total,
        "rows_skipped": rows_skipped,
        "rows_new": rows_new,
        "rows_dup": rows_dup,
        "date_min": dates[0] if dates else None,
        "date_max": dates[-1] if dates else None,
        "imported_at": imported_at,
        "encoding": encoding,
    }


def load_events(con: sqlite3.Connection) -> list[Event]:
    """从库中还原事件对象（供派生层复用，保证与落库口径一致）。"""
    rows = con.execute("SELECT * FROM event ORDER BY trade_date, trade_time, deal_no").fetchall()
    out: list[Event] = []
    for r in rows:
        out.append(
            Event(
                event_uid=r["event_uid"], trade_date=r["trade_date"], settle_date=r["settle_date"] or "",
                trade_time=r["trade_time"] or "", code=r["code"] or "", name=r["name"] or "",
                raw_type=r["raw_type"], category=r["category"], qty=r["qty"], price=r["price"],
                amount=r["amount"], cash=r["cash"], comm=r["comm"], other_fee=r["other_fee"],
                stamp=r["stamp"], transfer_fee=r["transfer_fee"], shares_after=r["shares_after"],
                cash_after=r["cash_after"], deal_no=r["deal_no"] or "", holder=r["holder"] or "",
                serial=r["serial"] or "", market=r["market"] or "", ccy=r["ccy"] or "",
                kind=r["kind"] or "", side=r["side"] or "", net_px=r["net_px"], row_no=r["row_no"] or 0,
                date_from_settle=bool(r["date_from_settle"]), source_file=r["source_file"] or "",
            )
        )
    return out


def latest_batch(con: sqlite3.Connection) -> str:
    row = con.execute(
        "SELECT batch_id FROM import_batch ORDER BY imported_at DESC, batch_id DESC LIMIT 1"
    ).fetchone()
    if not row:
        raise RuntimeError("台账为空：请先执行 import 导入交割单")
    return row["batch_id"]


def replace_derived(
    con: sqlite3.Connection,
    batch_id: str,
    roundtrips: Iterable,
    daily_rows: Iterable,
    detail_rows: Iterable,
    exposure_rows: Iterable | None = None,
) -> dict:
    """用最新口径重建派生表（同一 batch 全量覆盖）。"""
    roundtrips = list(roundtrips)
    daily_rows = list(daily_rows)
    detail_rows = list(detail_rows)
    exposure_rows = list(exposure_rows or [])
    cur = con.cursor()
    cur.execute("DELETE FROM roundtrip WHERE batch_id=?", (batch_id,))
    cur.execute("DELETE FROM daily_equity WHERE batch_id=?", (batch_id,))
    cur.execute("DELETE FROM daily_position WHERE batch_id=?", (batch_id,))
    cur.execute("DELETE FROM exposure WHERE batch_id=?", (batch_id,))

    rt_payload = []
    for i, r in enumerate(roundtrips):
        rt_payload.append((
            batch_id, i, r.code, r.name, r.kind, r.open_time, r.close_time, r.qty,
            r.buy_px, r.sell_px, r.cost, r.pnl, r.ret, r.hold_days, r.hold_td,
            r.unmatched_qty, r.pnl_adj, r.flags, r.sell_event_uid,
        ))
    cur.executemany(
        "INSERT INTO roundtrip (batch_id,seq,code,name,kind,open_time,close_time,qty,buy_px,"
        "sell_px,cost,pnl,ret,hold_days,hold_td,unmatched_qty,pnl_adj,flags,sell_event_uid)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rt_payload)

    cur.executemany(
        "INSERT INTO daily_equity (batch_id,date,equity,mv,cash,dep,cumdep,pnl,npos)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        [(batch_id, d.date, d.equity, d.mv, d.cash, d.dep, d.cumdep, d.pnl, d.npos) for d in daily_rows],
    )
    cur.executemany(
        "INSERT INTO daily_position (batch_id,date,code,name,kind,qty,cost,price,price_src,mv,upnl)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [(batch_id, r["date"], r["code"], r["name"], r["kind"], r["qty"], r["cost"], r["price"],
          r["price_src"], r["mv"], r["upnl"]) for r in detail_rows],
    )
    if exposure_rows:
        cur.executemany(
            "INSERT INTO exposure (batch_id,date,code,name,weight,mv,equity) VALUES (?,?,?,?,?,?,?)",
            [(batch_id, r["date"], r["code"], r["name"], r["weight"], r["mv"], r["equity"])
             for r in exposure_rows],
        )
    con.commit()
    return {
        "roundtrips": len(roundtrips),
        "daily_days": len(daily_rows),
        "positions": len(detail_rows),
        "exposure": len(exposure_rows),
    }
