"""数据状态统计不得在 /status 热路径上做全表扫描。

回归 (2026-10-30 用户反馈): 分钟/指数数据量增长后数据页加载不出来。
实测 /api/data/status 冷调用 17.3s, 其中 index_daily 4.75s、index_enriched
4.60s、adj_factor 9.58s —— 三者都在对百万级行/数万 parquet 文件做
count/min/max 全表聚合。数据页 30s 轮询反复触发, 叠加写盘竞争后超过前端
30s 超时。修复: 日期维度改读 date= 分区目录名, 标的数读维表小表;
adj_factor 的日 K 覆盖区间同样取自分区目录名, 不再扫描 kline_daily 视图。
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.api import data as data_api


class _Repo:
    """记录 SQL 的仓库替身; 未登记的查询直接失败, 防止意外全表扫描。"""

    def __init__(self, data_dir: Path, *, rows: dict[str, tuple] | None = None) -> None:
        self.store = SimpleNamespace(data_dir=Path(data_dir))
        self.rows = rows or {}
        self.sql: list[str] = []

    def execute_one(self, sql: str, params: list | None = None):
        self.sql.append(sql)
        for marker, row in self.rows.items():
            if marker in sql:
                return row
        raise AssertionError(f"unexpected query: {sql}")


def _touch_dates(root: Path, table: str, dates: list[str]) -> Path:
    table_dir = root / table
    for d in dates:
        (table_dir / f"date={d}").mkdir(parents=True)
    # 非分区目录不得计入
    (table_dir / "tmp").mkdir(parents=True)
    return table_dir


def _write_parquet(path: Path, columns: int) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    pq.write_table(pa.table({f"c{i}": [1] for i in range(columns)}), path)


# ---------- 指数日K / enriched ----------

def test_index_daily_stats_read_partitions_not_parquet(tmp_path):
    _touch_dates(tmp_path, "kline_index_daily", ["2026-10-28", "2026-10-29", "2026-10-30"])
    repo = _Repo(tmp_path, rows={"FROM instruments_index": (599,)})

    stats = data_api._safe_aggregate_index_daily(repo)

    assert stats == {
        "rows": 0,
        "earliest_date": "2026-10-28",
        "latest_date": "2026-10-30",
        "symbols_covered": 599,
        "trading_days": 3,
    }
    assert repo.sql == ["SELECT count(DISTINCT symbol) FROM instruments_index"]
    assert not any("kline_index_daily" in sql for sql in repo.sql)


def test_index_enriched_stats_read_partitions_not_parquet(tmp_path):
    table_dir = _touch_dates(tmp_path, "kline_index_enriched", ["2026-10-29", "2026-10-30"])
    _write_parquet(table_dir / "date=2026-10-30" / "part.parquet", 15)
    repo = _Repo(tmp_path, rows={"FROM instruments_index": (599, 598, 10)})

    stats = data_api._safe_aggregate_index_enriched(repo)

    assert stats["fields"] == 15
    assert stats["earliest_date"] == "2026-10-29"
    assert stats["trading_days"] == 2
    assert not any("FROM kline_index_enriched" in sql for sql in repo.sql)


def test_index_stats_none_without_partitions(tmp_path):
    (tmp_path / "kline_index_daily").mkdir()
    repo = _Repo(tmp_path)
    assert data_api._safe_aggregate_index_daily(repo) is None
    assert repo.sql == []


# ---------- adj_factor ----------

def test_adj_factor_range_from_partitions_not_daily_view(tmp_path):
    _touch_dates(tmp_path, "kline_daily", ["2026-10-28", "2026-10-29", "2026-10-30"])
    repo = _Repo(tmp_path, rows={"FROM adj_factor": (32856, 5183, 300)})

    stats = data_api._safe_aggregate_adj_factor(repo)

    assert stats == {
        "rows": 32856,
        "symbols_covered": 5183,
        "earliest_date": "2026-10-28",
        "latest_date": "2026-10-30",
        "trading_days": 300,
    }
    # 只允许查 adj_factor 小表; 日 K 区间必须来自分区目录名
    assert len(repo.sql) == 1
    assert "FROM adj_factor" in repo.sql[0]
    assert "FROM kline_daily" not in repo.sql[0]


def test_adj_factor_none_without_daily_partitions(tmp_path):
    (tmp_path / "kline_daily").mkdir()
    repo = _Repo(tmp_path)
    assert data_api._safe_aggregate_adj_factor(repo) is None
    assert repo.sql == []


# ---------- 其余统计保持轻量 ----------

def test_daily_and_enriched_do_not_scan_parquet(tmp_path):
    _touch_dates(tmp_path, "kline_daily", ["2026-10-29", "2026-10-30"])
    _touch_dates(tmp_path, "kline_daily_enriched", ["2026-10-29", "2026-10-30"])
    repo = _Repo(tmp_path, rows={"FROM instruments": (5890,)})

    daily = data_api._safe_aggregate_daily(repo)
    enriched = data_api._safe_aggregate_enriched(repo)

    assert daily["latest_date"] == "2026-10-30" and daily["trading_days"] == 2
    assert enriched["latest_date"] == "2026-10-30" and enriched["fields"] == 0
    assert not any("FROM kline_daily" in sql for sql in repo.sql)


# ---------- ETF 旧存储回退 ----------

def test_etf_daily_skips_legacy_scan_without_etf_instruments(tmp_path):
    """指数维表没有 etf 标的时, 旧存储回退必然为空, 不得扫描百万行指数数据。"""
    repo = _Repo(tmp_path, rows={"FROM instruments_index WHERE asset_type": (0,)})

    assert data_api._safe_aggregate_etf_daily(repo) is None
    assert len(repo.sql) == 1
    assert "kline_index_daily" not in repo.sql[0]


def test_etf_daily_reads_partitions_when_present(tmp_path):
    _touch_dates(tmp_path, "kline_etf_daily", ["2026-10-29", "2026-10-30"])
    repo = _Repo(tmp_path, rows={"FROM instruments_etf": (1769,)})

    stats = data_api._safe_aggregate_etf_daily(repo)

    assert stats == {
        "rows": 0,
        "earliest_date": "2026-10-29",
        "latest_date": "2026-10-30",
        "symbols_covered": 1769,
        "trading_days": 2,
    }
    assert not any("kline_index_daily" in sql for sql in repo.sql)


def test_etf_enriched_reads_partitions_and_one_schema(tmp_path):
    table_dir = _touch_dates(tmp_path, "kline_etf_enriched", ["2026-10-29", "2026-10-30"])
    _write_parquet(table_dir / "date=2026-10-30" / "part.parquet", 18)
    repo = _Repo(tmp_path, rows={"FROM instruments_etf": (1769,)})

    stats = data_api._safe_aggregate_etf_enriched(repo)

    assert stats == {
        "rows": 0,
        "fields": 18,
        "earliest_date": "2026-10-29",
        "latest_date": "2026-10-30",
        "symbols_covered": 1769,
        "trading_days": 2,
    }
    assert repo.sql == ["SELECT count(DISTINCT symbol) FROM instruments_etf"]


def test_etf_enriched_empty_skips_database(tmp_path):
    repo = _Repo(tmp_path)
    assert data_api._safe_aggregate_etf_enriched(repo) is None
    assert repo.sql == []


# ---------- null 统计的缓存 ----------

def test_computed_null_stats_cached_until_invalidated():
    data_api.invalidate_data_cache("etf_daily")
    calls: list[int] = []

    def fetch():
        calls.append(1)
        return None

    assert data_api._get_table_stats("etf_daily", fetch) is None
    assert data_api._get_table_stats("etf_daily", fetch) is None
    assert len(calls) == 1  # 空表探测结果在 TTL 内复用, 不再每轮重算

    data_api.invalidate_data_cache("etf_daily")
    assert data_api._get_table_stats("etf_daily", fetch) is None
    assert len(calls) == 2  # 写入后失效, 立即重算
    data_api.invalidate_data_cache(None)
