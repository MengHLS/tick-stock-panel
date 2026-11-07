"""落库层：重复导入幂等、批次留痕。"""
import sqlite3

from tsp_ledger import store
from tsp_ledger.parse import read_jiaogedan


def _import(con, path):
    res = read_jiaogedan(path)
    return store.import_events(con, res.events, path, res.encoding, res.total_rows, res.skipped_rows)


def test_import_is_idempotent(tmp_path, sample_csv):
    db = tmp_path / "ledger.sqlite"
    con = store.connect(db)

    first = _import(con, sample_csv)
    assert first["rows_new"] == 1055
    assert first["rows_dup"] == 0
    assert first["encoding"] == "gb18030"
    assert (first["date_min"], first["date_max"]) == ("2025-03-21", "2026-11-06")

    second = _import(con, sample_csv)
    assert second["rows_new"] == 0
    assert second["rows_dup"] == 1055

    assert con.execute("SELECT COUNT(*) FROM event").fetchone()[0] == 1055
    assert con.execute("SELECT COUNT(*) FROM import_batch").fetchone()[0] == 2
    # 两次导入的文件哈希一致，可反查"这份文件导过没"
    hashes = [r[0] for r in con.execute("SELECT file_sha256 FROM import_batch")]
    assert len(set(hashes)) == 1


def test_tables_created_and_derived_replaceable(tmp_path, sample_csv):
    con = store.connect(tmp_path / "ledger.sqlite")
    info = _import(con, sample_csv)
    names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"meta", "import_batch", "event", "roundtrip", "daily_equity",
            "daily_position", "exposure"} <= names

    batch = store.latest_batch(con)
    assert batch == info["batch_id"]

    # 空重建两次不应报错，也不应留下残行
    store.replace_derived(con, batch, [], [], [], exposure_rows=[])
    store.replace_derived(con, batch, [], [], [], exposure_rows=[])
    assert con.execute("SELECT COUNT(*) FROM roundtrip").fetchone()[0] == 0


def test_load_events_roundtrip(tmp_path, sample_csv):
    con = store.connect(tmp_path / "ledger.sqlite")
    _import(con, sample_csv)
    events = store.load_events(con)
    assert len(events) == 1055
    assert round(sum(e.cash for e in events), 2) == 44.34
    assert events[0].trade_date <= events[-1].trade_date
