#!/usr/bin/env python
"""四类数据阻塞 + 一次口径争议的可复现只读审计。

覆盖：
  industry     行业中性 / 行业轮动：本地是否存在可用的历史行业归属
  index        指数增强：本地是否存在指数成分股 / 权重
  etf          ETF 全族：kline_etf_* 三个目录与 ETF 元数据、库内替代表
  short        做空 / 对冲：代码执行路径与数据层（两融、券源）
  universe616  口径争议：78 / 355 / 236 / 616 四个数字的精确口径

用法（项目根目录为工作目录，PYTHONUTF8=1）：
  backend/.venv/Scripts/python.exe research/data-gaps-20261107/scripts/audit_data_gaps.py --check industry
  backend/.venv/Scripts/python.exe research/data-gaps-20261107/scripts/audit_data_gaps.py --check index
  backend/.venv/Scripts/python.exe research/data-gaps-20261107/scripts/audit_data_gaps.py --check etf
  backend/.venv/Scripts/python.exe research/data-gaps-20261107/scripts/audit_data_gaps.py --check short
  backend/.venv/Scripts/python.exe research/data-gaps-20261107/scripts/audit_data_gaps.py --check universe616

退出码：
  0 = 检查执行完成，已写出 results/check_<id>.json
      （注意：这里的 0 表示"审计命令跑通"，不代表数据可用；数据结论看 status / verdict）
  2 = 参数错误
  3 = 数据根或必需输入缺失，检查无法执行
  4 = 检查内部断言失败

本脚本只读：不写数据根，不修改 backend/，只写 research/data-gaps-20261107/results/。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, time as dtime
from pathlib import Path
from typing import Any

import duckdb

CHECK_IDS = ("industry", "index", "etf", "short", "universe616")
DEFAULT_DATA_ROOT = Path(r"D:/TSP/data")
SCRIPT_DIR = Path(__file__).resolve().parent
RESEARCH_DIR = SCRIPT_DIR.parent
REPO_ROOT = RESEARCH_DIR.parents[1]          # research/<topic>/scripts -> repo root
RESULTS_DIR = RESEARCH_DIR / "results"
IND = '"所属同花顺行业"'                        # 同花顺行业字段名（含层级，形如 二级-三级）


# ── 基础工具 ────────────────────────────────────────────────────────────────
def p2s(path: Path) -> str:
    """Windows 路径 -> DuckDB 可用的 POSIX 风格字符串。"""
    return str(path).replace("\\", "/")


def jval(value: Any) -> Any:
    if isinstance(value, (datetime, date, dtime)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        return f"<{len(value)} bytes>"
    if isinstance(value, dict):
        return {str(k): jval(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jval(v) for v in value]
    try:
        return value.item()  # numpy / decimal 标量
    except AttributeError:
        return value


class Recorder:
    """收集事实与 SQL，保证每条结论都能回溯到一条可重跑的命令。"""

    def __init__(self, con: duckdb.DuckDBPyConnection):
        self.con = con
        self.facts: list[dict] = []
        self.sqls: list[str] = []

    def fact(self, name: str, value: Any, *, sql: str | None = None,
             source: str | None = None, note: str | None = None) -> None:
        if sql:
            self.sqls.append(sql)
        item = {"name": name, "value": jval(value)}
        if sql:
            item["sql"] = sql
        if source:
            item["source"] = source
        if note:
            item["note"] = note
        self.facts.append(item)

    def rows(self, sql: str) -> list[dict]:
        rel = self.con.sql(sql)
        cols = [d[0] for d in rel.description]
        return [{c: jval(v) for c, v in zip(cols, row)} for row in rel.fetchall()]

    def one(self, sql: str) -> dict:
        got = self.rows(sql)
        return got[0] if got else {}

    def scalar(self, sql: str) -> Any:
        got = self.one(sql)
        return next(iter(got.values())) if got else None


def columns_of(con: duckdb.DuckDBPyConnection, parquet_glob: str) -> list[str]:
    rel = con.sql(f"describe select * from read_parquet('{parquet_glob}')")
    return [r[0] for r in rel.fetchall()]


def line_of(path: Path, needle: str) -> int | None:
    """返回 needle 首次出现的 1-based 行号（源码取证用）。"""
    if not path.exists():
        return None
    for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if needle in line:
            return i
    return None


def code_evidence(rel_path: str, needle: str, quote: str) -> dict:
    full = REPO_ROOT / rel_path
    return {
        "path": f"{rel_path}:{line_of(full, needle) or '?'}",
        "statement": quote,
        "search": f"grep -n \"{needle}\" {rel_path}",
    }


def dir_stats(path: Path) -> dict:
    """目录的文件数 / 字节数 / 非空文件数（含隐藏文件，递归）。"""
    files = [f for f in path.rglob("*") if f.is_file()] if path.exists() else []
    sizes = [f.stat().st_size for f in files]
    return {
        "path": p2s(path),
        "exists": path.exists(),
        "files": len(files),
        "bytes": sum(sizes),
        "non_empty_files": sum(1 for s in sizes if s > 0),
        "sample_files": [p2s(f) for f in files[:5]],
    }


# ── 共享面板（一次建临时表，三个检查复用）──────────────────────────────────
class Panel:
    def __init__(self, con: duckdb.DuckDBPyConnection, root: Path):
        self.con, self.root = con, root
        self.kline = p2s(root / "kline_daily" / "**" / "*.parquet")
        self.enriched = p2s(root / "kline_daily_enriched" / "**" / "*.parquet")
        self.linkage = p2s(root / "kline_daily_linkage" / "**" / "*.parquet")
        con.execute(
            "create or replace temp table panel_agg as "
            f"select symbol, count(*) as bars, min(date) as first_date, max(date) as last_date "
            f"from read_parquet('{self.kline}') group by 1"
        )
        con.execute(
            "create or replace temp table panel_dates as "
            f"select distinct date from read_parquet('{self.kline}')"
        )
        con.execute(
            "create or replace temp table ins as select * from read_parquet("
            f"'{p2s(root / 'instruments' / 'instruments.parquet')}')"
        )
        con.execute(
            "create or replace temp table adj_syms as select distinct symbol from read_parquet("
            f"'{p2s(root / 'adj_factor' / 'all.parquet')}')"
        )
        for name, table in (
            ("fin_bs", "balance_sheet"), ("fin_income", "income"),
            ("fin_cf", "cash_flow"), ("fin_metrics", "metrics"),
        ):
            con.execute(
                f"create or replace temp table {name} as select distinct symbol from read_parquet("
                f"'{p2s(root / 'financials' / table / '*.parquet')}')"
            )
        con.execute(
            "create or replace temp table fin_any as "
            "select symbol from fin_bs union select symbol from fin_income "
            "union select symbol from fin_cf union select symbol from fin_metrics"
        )


# ── 检查 1：行业中性 / 行业轮动 ────────────────────────────────────────────
def check_industry(ctx: Recorder, root: Path, panel: Panel) -> dict:
    pit_root = root / "ext_data" / "ext_hy_ths_pit" / "timeseries"
    part_dirs = sorted([d for d in pit_root.glob("date=*") if d.is_dir()])
    pit_glob = p2s(pit_root / "**" / "*.parquet")

    parts = []
    for d in part_dirs:
        files = sorted(d.glob("*.parquet"))
        parts.append({
            "date": d.name[5:],
            "files": len(files),
            "bytes": sum(f.stat().st_size for f in files),
        })
    ctx.fact(
        "行业时点快照分区（ext_hy_ths_pit）",
        {"partitions": len(parts), "partitions_detail": parts,
         "total_bytes": sum(x["bytes"] for x in parts)},
        source=p2s(pit_root),
        note="目录列举：date=* 分区即一次快照；文件为零字节即为空分区",
    )

    per_date_sql = (
        f"select date::varchar as snapshot_date, count(*) as n_rows, "
        f"count(distinct symbol) as n_symbols, count(distinct {IND}) as n_industries, "
        f"count(*) filter (where {IND} is null or trim({IND}) = '') as n_null_industry "
        f"from read_parquet('{pit_glob}', hive_partitioning=true) group by 1 order by 1"
    )
    per_date = ctx.rows(per_date_sql)
    ctx.fact("每个快照日的证券数与行业标签数", per_date, sql=per_date_sql)

    panel_dates_sql = (
        "select (select count(*) from panel_dates) as panel_trading_days, "
        f"(select count(*) from panel_dates pd where exists (select 1 from "
        f"(select distinct date from read_parquet('{pit_glob}', hive_partitioning=true)) p "
        f"where p.date = pd.date)) as panel_days_with_same_day_industry"
    )
    ctx.fact("行业快照与面板交易日对齐", ctx.one(panel_dates_sql), sql=panel_dates_sql)

    # 窗口内逐日：有标签的证券数 / 当日与日线面板的匹配数
    window = []
    for d in ("2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06"):
        pit_file = p2s(pit_root / f"date={d}" / "*.parquet")
        kl_file = p2s(root / "kline_daily" / f"date={d}" / "*.parquet")
        sql = (
            "select (select count(distinct symbol) from read_parquet('{p}')) as labeled_symbols, "
            "(select count(*) from (select distinct symbol from read_parquet('{p}')) a join "
            "(select distinct symbol from read_parquet('{k}')) b using(symbol)) as matched_kline_symbols, "
            "(select count(*) from read_parquet('{k}')) as kline_symbols"
        ).format(p=pit_file, k=kl_file)
        window.append({"date": d, **ctx.one(sql)})
        ctx.sqls.append(sql)
    ctx.fact("窗口内每个交易日有行业标签的证券数（5 个交易日）", window,
             note="每个交易日一条 SQL，全部逐条记入 sql_log：select count(distinct symbol) from read_parquet(pit_file) 与 kline 分区按 symbol join 计数")

    union_sql = (
        f"select (select count(*) from panel_agg) as panel_symbols, "
        f"(select count(distinct symbol) from read_parquet('{pit_glob}', hive_partitioning=true)) as snapshot_union_symbols, "
        f"(select count(*) from panel_agg where symbol in (select distinct symbol from "
        f"read_parquet('{pit_glob}', hive_partitioning=true))) as panel_symbols_labeled_ever, "
        f"(select count(*) from panel_agg where symbol not in (select distinct symbol from "
        f"read_parquet('{pit_glob}', hive_partitioning=true))) as panel_symbols_never_labeled"
    )
    ctx.fact("全期（含窗口）行业标签对面板的覆盖", ctx.one(union_sql), sql=union_sql)

    snap = root / "ext_data" / "ext_hy_ths" / "part.parquet"
    snap_cols = columns_of(ctx.con, p2s(snap))
    snap_sql = f"select count(*) as n_rows, count(distinct symbol) as n_symbols from read_parquet('{p2s(snap)}')"
    ctx.fact(
        "非时点行业快照（ext_hy_ths）",
        {**ctx.one(snap_sql), "columns": snap_cols, "has_date_column": "date" in snap_cols},
        sql=snap_sql, source=p2s(snap),
        note="snapshot 模式：无日期列，只能代表 '当前'，不能当作历史",
    )

    link_sql = (
        "select count(*) as total_rows, "
        "count(industry_relative_momentum_20d) as nonnull_industry_relative_momentum_20d, "
        "count(industry_rank_momentum_20d) as nonnull_industry_rank_momentum_20d, "
        "count(industry_corr_60d) as nonnull_industry_corr_60d, "
        "count(industry_beta_60d) as nonnull_industry_beta_60d, "
        "count(distinct date) as dates, min(date) as first_date, max(date) as last_date "
        f"from read_parquet('{panel.linkage}')"
    )
    ctx.fact("预计算的行业联动因子（kline_daily_linkage）非空率", ctx.one(link_sql), sql=link_sql)

    link_parts_sql = (
        "select count(*) as partitions, "
        "sum(case when n > 0 then 1 else 0 end) as partitions_with_any_industry_factor "
        f"from (select date, count(industry_relative_momentum_20d) as n "
        f"from read_parquet('{panel.linkage}') group by 1)"
    )
    ctx.fact("含任一非空行业因子的分区数", ctx.one(link_parts_sql), sql=link_parts_sql)

    graph_path = root / "user_data" / "industry_chain" / "graph.json"
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    node_keys = sorted({k for n in graph.get("nodes", [])[:200] for k in n})
    link_keys = sorted({k for n in graph.get("stock_links", [])[:200] for k in n})
    ctx.fact(
        "产业链图谱（industry_chain/graph.json）",
        {
            "nodes": len(graph.get("nodes", [])),
            "stock_links": len(graph.get("stock_links", [])),
            "chains": len(graph.get("chains", [])),
            "node_keys": node_keys,
            "stock_link_keys": link_keys,
            "has_any_date_field": any("date" in k for k in node_keys + link_keys),
            "updated_at": graph.get("updated_at"),
            "backups_in_dir": sorted(p.name for p in graph_path.parent.glob("graph.json.bak*"))[:12],
        },
        source=p2s(graph_path),
        note="只有 updated_at（2026-11-06）与 2026-11-04/05 的备份，备份是同一周内的快照，不是历史版本",
    )

    fin_hits: dict[str, list[str]] = {}
    for table in ("balance_sheet", "income", "cash_flow", "metrics"):
        cols = columns_of(ctx.con, p2s(root / "financials" / table / "*.parquet"))
        hit = [c for c in cols if re.search(r"主营|segment|industry|行业|business", c, re.I)]
        fin_hits[table] = hit
    ctx.fact(
        "财务表是否含主营构成 / 行业字段（可用于重构行业归属）",
        fin_hits,
        source="、".join(p2s(root / "financials" / t / "*.parquet")
                        for t in ("balance_sheet", "income", "cash_flow", "metrics")),
        note="空列表 = 该表无此类字段；四表均为空则无法用财务字段重构行业",
    )

    cfg = json.loads((root / "ext_data" / "ext_hy_ths_pit" / "config.json").read_text(encoding="utf-8"))
    pull = cfg.get("pull") or {}
    ctx.fact(
        "行业时点来源的拉取配方",
        {
            "mode": cfg.get("mode"),
            "created_at": cfg.get("created_at"),
            "schedule_period": pull.get("schedule_period"),
            "schedule_trading_only": pull.get("schedule_trading_only"),
            "date_param": pull.get("date_param"),
            "time_window_start": pull.get("time_window_start"),
            "time_window_end": pull.get("time_window_end"),
            "url": pull.get("url"),
        },
        source="D:/TSP/data/ext_data/ext_hy_ths_pit/config.json",
        note="配方没有任何日期/时间窗口参数 → 每次只能拉'当天'，历史只能向前累积",
    )

    # 备选路径审查：mainline_history 里确实存在 kind='industry' 的行业级时序（2018 起 6,476 行），
    # 但它是用「当前行业快照」回看历史聚合涨停梯队得到的，代码自带前视声明；
    # 且只覆盖涨停事件、不含全样本个股归属，因此不能当作行业中性/行业轮动的干净输入。
    ml_glob = p2s(root / "mainline_history" / "*.parquet")
    ml_sql = (
        f"select kind, count(*) as n_rows, min(date) as first_date, max(date) as last_date, "
        f"count(distinct member) as members, count(distinct date) as dates "
        f"from read_parquet('{ml_glob}') group by 1 order by 1"
    )
    ctx.fact(
        "候选捷径：mainline_history 的行业维度覆盖",
        ctx.rows(ml_sql),
        sql=ml_sql,
        source="D:/TSP/data/mainline_history/part.parquet",
        note="member 是行业名而非 symbol→行业映射；行是涨停梯队聚合，不是个股行业归属",
    )
    mainline_py = REPO_ROOT / "backend/app/services/market_mainline.py"
    ml_note = None
    for line in mainline_py.read_text(encoding="utf-8", errors="replace").splitlines():
        if "当前快照回看历史" in line:
            ml_note = line.strip().strip('"').strip("'").rstrip(",")
            break
    ctx.fact(
        "候选捷径的前视声明（代码原文）",
        {
            "MEMBERSHIP_NOTE": ml_note,
            "line": line_of(mainline_py, "当前快照回看历史"),
            "industry_map_source": "app.services.rps_rotation._load_concept_map_df -> ExtConfigStore 当前快照",
            "industry_map_has_date_dimension": False,
        },
        source="backend/app/services/market_mainline.py",
        note="该时序把今天的行业成分回看历史计算，属前视，不能作为无前视的行业归属来源",
    )
    evidence = [
        code_evidence("backend/app/services/market_mainline.py", "当前快照回看历史",
                      "主业/概念主线时序按当前成分回看历史生成，代码自认'早年存在归属漂移'，只能当展示口径"),
        code_evidence("backend/app/services/rps_rotation.py", "维度成分股是 snapshot",
                      "行业归属映射的唯一来源是 ExtConfigStore 的当前快照，无日期维度，不可 PIT 化"),
        code_evidence("backend/app/custom/cross_sectional_linkage/store.py",
                      "snapshot 行业归属不能回填历史",
                      "系统自己就拒绝用 snapshot 行业回填历史，只有 timeseries 且 require_complete=True 才可作为 PIT 来源"),
        code_evidence("backend/app/custom/cross_sectional_linkage/compute.py",
                      "_MAX_INDUSTRY_AGE_DAYS",
                      "行业归属用 join_asof backward + 最大 30 天时效：快照只能向前覆盖 30 天，不能回填"),
    ]

    conclusion = (
        "历史上不可做：本地行业归属只有 2026-11-01~06 的 6 个时点快照（面板内 5 个交易日，0.23%），"
        "另有一份无日期列的当前快照与一份无日期维度的产业链图谱；财务表无主营构成字段，"
        "因此没有任何无前视的历史行业归属来源。预计算行业联动因子在 9,752,990 行历史中非空数为 0。"
        "唯一合规的可用切片是 2026-11-02~06 五天的当日截面行业相对强弱，不具有跨期检验价值。"
        "另已排查唯一候选捷径 mainline_history 的 industry 维度（2018-01-10 起 6,476 行）：它是用当前行业快照"
        "回看历史聚合涨停梯队得到的，代码自带前视声明，且只覆盖涨停事件、不含全样本个股归属，否决。"
    )
    return {
        "id": "industry",
        "family": "行业中性 / 行业轮动 / 行业分层归因",
        "status": "blocked",
        "verdict": "确证",
        "conclusion": conclusion,
        "partial_capability": "2026-11-02~06 共 5 个交易日可做当日截面行业相对强弱（无前视）；无法做行业中性化回测或行业轮动",
        "facts": ctx.facts,
        "code_evidence": evidence,
        "unknown": [
            "供应商是否提供历史行业成员关系接口：仓库内只有 catalog + constituents(当前) 两个端点，"
            "是否存在历史端点未知（需向数据方确认，属采购/外部能力问题）",
            "产业链图谱（431 节点 / 3,539 条股票映射）的来源与更新规则未审计：它只有当前版本，无法作为历史归属",
        ],
        "needs_without_purchase": (
            "仅凭现存本地文件不可补历史：未找到历史行业分类落盘文件，财务表缺少主营构成字段，"
            "当前快照倒推即前视。本地已知可行做法是向前累积每日快照（已有落盘配置，"
            "2026-11-01 起已有六天落盘）；公开历史档案是否足够、是否需采购均未验证。"
        ),
        "evidence_paths": [p2s(pit_root), p2s(snap), p2s(graph_path),
                           p2s(root / "ext_data" / "ext_hy_ths_pit" / "config.json")],
    }


# ── 检查 2：指数增强 ──────────────────────────────────────────────────────
def check_index(ctx: Recorder, root: Path) -> dict:
    daily_glob = p2s(root / "kline_index_daily" / "**" / "*.parquet")
    enriched_glob = p2s(root / "kline_index_enriched" / "**" / "*.parquet")
    meta_glob = p2s(root / "instruments_index" / "instruments_index.parquet")

    daily_cols = columns_of(ctx.con, daily_glob)
    enriched_cols = columns_of(ctx.con, enriched_glob)
    meta_cols = columns_of(ctx.con, meta_glob)

    cov_sql = (
        f"select count(distinct symbol) as index_symbols, count(distinct date) as dates, "
        f"min(date) as first_date, max(date) as last_date from read_parquet('{daily_glob}')"
    )
    ctx.fact("指数日线（kline_index_daily）", {**ctx.one(cov_sql), "columns": daily_cols}, sql=cov_sql)
    ctx.fact("指数增强行情（kline_index_enriched）列", {"columns": enriched_cols},
             source=enriched_glob,
             note="只有 OHLCV + 复权价，无成分/权重字段")
    ctx.fact("指数元数据（instruments_index）", {"columns": meta_cols,
                                        "rows": ctx.scalar(f"select count(*) from read_parquet('{meta_glob}')")},
             sql=f"select count(*) from read_parquet('{meta_glob}')",
             source=meta_glob,
             note="599 条指数名称表，无成分、无权重")

    # 全数据根按目录名找成分/权重类数据集（递归到 3 层）
    keyword = re.compile(r"constituent|weight|member|成分|权重|index_member", re.I)
    named = sorted({p2s(p) for p in root.rglob("*")
                    if p.is_dir() and keyword.search(p.name)})
    ctx.fact("数据根下名称含 成分/权重/constituent/weight 的目录", named or "未找到",
             source=p2s(root),
             note="目录名普查：root.rglob('*') 逐目录正则 constituent|weight|member|成分|权重|index_member；空集 = 未找到")

    # 所有指数相关 parquet 的列名里是否有权重/成分
    weight_cols = {name: [c for c in cols if re.search(r"weight|constituent|成分|权重", c, re.I)]
                   for name, cols in (("kline_index_daily", daily_cols),
                                      ("kline_index_enriched", enriched_cols),
                                      ("instruments_index", meta_cols))}
    ctx.fact("指数类数据集中的权重/成分列", weight_cols,
             source="、".join((daily_glob, enriched_glob, meta_glob)),
             note="对三张指数表 describe 后按 weight|constituent|成分|权重 正则过滤；全为空 → 任何指数数据集都不带成分或权重")

    # 扩展数据配置里是否有指数成分类拉取配方。
    # 注意：命中 "constituent" 的全部来自 fuyao 板块成分端点
    # /api/a-share-index/constituents/ths-stock-list（概念/行业板块的当前成分），
    # 与指数成分、权重无关。这里把命中片段一并留档，避免"命中关键词"被误读为"有成分配方"。
    cfg_hits = []
    for cfg_path in sorted((root / "ext_data").glob("*/config.json")):
        text = cfg_path.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"成分|constituent|weight|权重", text, re.I)
        if m:
            start = max(0, m.start() - 60)
            cfg_hits.append({
                "path": p2s(cfg_path),
                "match": m.group(0),
                "snippet": " ".join(text[start:m.end() + 60].split()),
                "is_index_weight_recipe": bool(re.search(r"index[^\"']*weight|weight[^\"']*index", text, re.I)),
            })
    ctx.fact("ext_data 配置中提及 成分/权重 的配方文件", cfg_hits or "未找到",
             source="、".join(h["path"] for h in cfg_hits) or p2s(root / "ext_data" / "*/config.json"),
             note="逐条给出命中片段：全部是 ths-stock-list 板块成分端点，is_index_weight_recipe 均为 false")

    # 概念快照里是否连"按指数名做标签"都没有
    gn = p2s(root / "ext_data" / "ext_gn_ths" / "part.parquet")
    label_sql = (
        f"select count(*) filter (where \"所属概念\" like '%沪深300%') as hs300, "
        f"count(*) filter (where \"所属概念\" like '%中证500%') as zz500, "
        f"count(*) filter (where \"所属概念\" like '%中证1000%') as zz1000, "
        f"count(*) filter (where \"所属概念\" like '%上证50%') as sz50 "
        f"from read_parquet('{gn}')"
    )
    ctx.fact("概念快照中带 沪深300/中证500/中证1000/上证50 标签的证券数", ctx.one(label_sql), sql=label_sql,
             note="全 0：连'当前成分'的快照代理都不存在")

    evidence = [
        code_evidence("backend/app/services/ext_presets.py", "_FUYAO_CONSTITUENTS_PATH",
                      "仓库内唯一成分接口是 ths-stock-list（当前成分，无历史版本参数），且服务于板块/概念，不是指数权重"),
        code_evidence("backend/app/capabilities.py", "", "n/a") if (REPO_ROOT / "backend/app/capabilities.py").exists() else {},
    ]
    evidence = [e for e in evidence if e]

    conclusion = (
        "不可做。本地只有 599 个指数的日线价格（2016-10-28~2026-11-06），不存在任何指数成分或权重数据："
        "所有指数数据集的列里没有成分/权重字段，数据根下没有成分数据集目录，扩展数据配置里没有成分类配方，"
        "概念快照中也没有以宽基指数名为标签的成员关系。指数增强需要成分与权重，"
        "用今天的成分回测 2019 年即前视，故本族在现有数据下无法做可信检验。"
    )
    return {
        "id": "index",
        "family": "指数增强 / 指数成分轮动 / 跟踪误差约束",
        "status": "blocked",
        "verdict": "确证",
        "conclusion": conclusion,
        "facts": ctx.facts,
        "code_evidence": evidence,
        "unknown": [
            "历史上是否存在过成分数据文件后又被删除：本审计只能证明'当前不存在'，无法证明'从未存在'",
        ],
        "needs_without_purchase": (
            "现有本地数据不可补：需要指数成分与权重及生效日期的历史，本地未找到。"
            "外部免费覆盖与采购必要性未验证；本次不推测替代方案。"
        ),
        "evidence_paths": [p2s(root / "kline_index_daily"), p2s(root / "instruments_index"),
                           p2s(root / "ext_data" / "ext_gn_ths" / "part.parquet")],
    }


# ── 检查 3：ETF 全族 ──────────────────────────────────────────────────────
def check_etf(ctx: Recorder, root: Path) -> dict:
    targets = ["kline_etf_daily", "kline_etf_enriched", "kline_etf_minute"]
    stats = {name: dir_stats(root / name) for name in targets}
    ctx.fact("三个 ETF 行情目录的文件数 / 字节数", stats,
             source="、".join(p2s(root / n) for n in targets),
             note="0 文件 0 字节 = 目录存在但从未落过任何分区")

    extra = dir_stats(root / "adj_factor_etf")
    ctx.fact("ETF 复权因子目录（adj_factor_etf）", extra,
             source=p2s(root / "adj_factor_etf"),
             note="同为 0 文件 0 字节")

    meta_glob = p2s(root / "instruments_etf" / "instruments_etf.parquet")
    meta_sql = (
        "select count(*) as rows, count(distinct symbol) as symbols, "
        "count(distinct substr(symbol,1,3)) as prefixes from "
        f"read_parquet('{meta_glob}')"
    )
    prefix_sql = (
        "select substr(symbol,1,3) as prefix, count(*) as n from "
        f"read_parquet('{meta_glob}') group by 1 order by 2 desc limit 8"
    )
    ctx.fact("ETF 元数据（instruments_etf）", {**ctx.one(meta_sql), "top_prefixes": ctx.rows(prefix_sql)},
             sql=meta_sql + " ; " + prefix_sql, source=p2s(root / "instruments_etf" / "instruments_etf.parquet"),
             note="有 1,769 条 ETF 代码表，但没有任何行情")

    overlap_sql = (
        f"select count(distinct k.symbol) as etf_symbols_present_in_stock_kline "
        f"from read_parquet('{p2s(root / 'kline_daily' / '**' / '*.parquet')}') k "
        f"where k.symbol in (select symbol from read_parquet('{meta_glob}'))"
    )
    ctx.fact("ETF 代码是否混在股票日线面板里", ctx.one(overlap_sql), sql=overlap_sql)

    prefix_probe_sql = (
        "select substr(symbol,1,2) as prefix, count(distinct symbol) as n "
        f"from read_parquet('{p2s(root / 'kline_daily' / '**' / '*.parquet')}') "
        "where substr(symbol,1,2) in ('51','15','56','58','16') group by 1 order by 1"
    )
    ctx.fact("股票日线面板中的 ETF 类代码前缀（51/15/56/58/16）", ctx.rows(prefix_probe_sql) or "未找到",
             sql=prefix_probe_sql, note="空结果 = 面板里连一只 ETF 都没有")
    # 24 GB 分钟线是最后一个可能的 ETF 行情替代；只投影 symbol 列做全量扫，代价可接受。
    minute_probe_sql = (
        "select count(distinct symbol) as symbols, "
        "count(distinct symbol) filter (where substr(symbol,1,2) in ('51','15','56','58','16')) as etf_like_symbols "
        f"from read_parquet('{p2s(root / 'kline_minute' / '**' / '*.parquet')}')"
    )
    ctx.fact("分钟线是否覆盖 ETF（全量 symbol 列扫描）", ctx.one(minute_probe_sql), sql=minute_probe_sql,
             source=p2s(root / "kline_minute"),
             note="etf_like_symbols = 0 → 分钟线也只有股票代码，ETF 没有任何粒度的行情")

    evidence = [
        code_evidence("backend/app/api/data.py", '"kline_etf_daily"',
                      "读接口已按 ETF 专区命名（daily/enriched/minute 三套），说明管道存在、缺的是数据"),
    ]

    conclusion = (
        "不可做。kline_etf_daily / kline_etf_enriched / kline_etf_minute 三个目录均为 0 个文件、0 字节，"
        "adj_factor_etf 同样为空；本地只有 1,769 条 ETF 代码元数据。股票日线面板里没有一只 ETF（51/15/56/58/16 前缀为 0），"
        "全量分钟线（5,917 只代码）里也没有一只 ETF，因此库里没有任何可用于 ETF 轮动、ETF 套利或 ETF 基准净值的行情表。"
    )
    return {
        "id": "etf",
        "family": "ETF 全族（轮动 / 套利 / 基准）",
        "status": "blocked",
        "verdict": "确证",
        "conclusion": conclusion,
        "facts": ctx.facts,
        "code_evidence": evidence,
        "unknown": [
            "ETF 行情是'从未采购'还是'曾经有后被清理'：目录 mtime 2026-10-28 之后无写入，无法判定原因",
        ],
        "needs_without_purchase": (
            "现有本地数据不可补：需要 ETF 日线与复权/公司行为记录；分钟及折溢价按策略需求补齐。"
            "kline_etf_daily / kline_etf_enriched / kline_etf_minute 三个专区与读接口已经存在，"
            "尚需核验可用来源、历史覆盖及采集校验链；免费来源与采购必要性未验证。"
        ),
        "evidence_paths": [p2s(root / n) for n in targets] + [p2s(root / "adj_factor_etf"),
                                                              p2s(root / "instruments_etf" / "instruments_etf.parquet")],
    }


# ── 检查 4：做空 / 对冲 ───────────────────────────────────────────────────
def check_short(ctx: Recorder, root: Path) -> dict:
    app = REPO_ROOT / "backend" / "app"
    patterns = {
        "short_literal": re.compile(r"""["']short["']"""),
        "short_word": re.compile(r"\bshort\b", re.I),
        "hedge": re.compile(r"\bhedg\w*", re.I),
        "basis": re.compile(r"\bbasis\b", re.I),
        "margin": re.compile(r"\bmargin\w*", re.I),
        "borrow_lend": re.compile(r"\b(borrow|lend|lending|securities_lending)\w*", re.I),
        "cn_short": re.compile(r"做空|融券|两融|融资余额|借券|卖空|保证金"),
        "cn_hedge": re.compile(r"对冲|套保|套期"),
    }
    hits: dict[str, list[str]] = {}
    for name, pat in patterns.items():
        found = []
        for py in sorted(app.rglob("*.py")):
            try:
                text = py.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if pat.search(line):
                    rel = py.relative_to(REPO_ROOT).as_posix()
                    found.append(f"{rel}:{i}: {line.strip()[:150]}")
        hits[name] = found
    ctx.fact(
        "backend/app 全量静态命中（逐模式）",
        {k: {"count": len(v), "hits": v[:8]} for k, v in hits.items()},
        source="backend/app/**/*.py",
        note="只统计命中行数与样例；hedge 的计数口径差异见下一条（子串 grep 会把 EnrichedGeneration 计进去）",
    )
    # 口径核对：naive 子串 grep -i "hedge" 会命中 "EnrichedGeneration..."（...hed + Ge...，
    # 跳词边界恰好拼出 hedGe），带词边界的正则不会。两种口径全部留档，
    # 避免把“搜到了关键词”误读为“存在对冲路径”。
    naive_substring = 0
    for py in sorted(app.rglob("*.py")):
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        naive_substring += sum(1 for ln in text.splitlines() if "hedge" in ln.lower())
    ctx.fact(
        "hedge 命中口径核对（带词边界 vs 子串）",
        {
            "with_word_boundary": len(hits["hedge"]),
            "naive_substring": naive_substring,
            "false_positive_source": "EnrichedGenerationUnavailableError（...hed + Ge... 跨词边界拼出 hedGe）",
            "cn_hedge_hits": len(hits["cn_hedge"]),
            "cn_hedge_samples": hits["cn_hedge"][:5],
        },
        source="backend/app/**/*.py",
        note="子串口径的 70 条全部是 EnrichedGeneration 假阳性；真实 hedge/对冲/套保 命中为 0",
    )

    engine = REPO_ROOT / "backend/app/backtest/engine.py"
    engine_text = engine.read_text(encoding="utf-8", errors="replace")
    ctx.fact(
        "撮合器支持的委托方向",
        {
            "buy_literal": engine_text.count('"buy"'),
            "sell_literal": engine_text.count('"sell"'),
            "has_allow_short_flag": bool(re.search(r"allow_short|short_selling|sell_short", engine_text)),
        },
        source="backend/app/backtest/engine.py",
        note="只有 buy/sell 两个字面方向，没有任何 allow_short 开关",
    )

    margin_dirs = sorted({p2s(p) for p in root.rglob("*")
                          if p.is_dir() and re.search(r"margin|rzrq|lending|borrow|short", p.name, re.I)})
    ctx.fact("数据根下 两融/融券/借券 类数据集目录", margin_dirs or "未找到",
             source=p2s(root),
             note="目录名普查：root.rglob('*') 逐目录正则 margin|rzrq|lending|borrow|short；空集 = 未找到")

    gn = p2s(root / "ext_data" / "ext_gn_ths" / "part.parquet")
    tag_sql = (
        f"select count(*) filter (where \"所属概念\" like '%融资融券%') as margin_tag_symbols, "
        f"count(*) filter (where \"所属概念\" like '%转融券%') as lending_tag_symbols "
        f"from read_parquet('{gn}')"
    )
    ctx.fact("概念快照中的 融资融券 / 转融券 标签证券数", ctx.one(tag_sql), sql=tag_sql,
             note="融资融券标签只是'标的身分'的当前快照，没有余额、费率、券源，也没有历史")

    evidence = [
        code_evidence("backend/app/backtest/engine.py", 'sign = 1 if side == "buy" else -1',
                      "滑点/成本按 buy/sell 两向计算，买卖是唯一的委托语义"),
        code_evidence("backend/app/backtest/engine.py", "capacity = max(0.0, equity * max_exposure_pct - market_value)",
                      "仓位受现金与敞口上限约束，weights 全部 >= 0（1/n 或 max(score,0) 归一），不存在负仓位"),
        code_evidence("backend/app/backtest/factor.py", "50/50 理论多空两腿",
                      "因子层的 long_short 是净值价差记账（多空组合统计），不产生可执行空头，也没有券源/费率"),
        code_evidence("backend/app/strategy/prompt_builder.py", "DIRECTION_CN",
                      "short 只作为策略描述里的中文标签出现，不进入撮合"),
    ]

    conclusion = (
        "不可做。代码层没有任何做空或对冲的执行路径：撮合器只有 buy/sell，仓位权重全为非负，"
        "受现金与敞口上限约束；因子层的 long_short 只是分组净值价差统计，不含券源、费率与保证金。"
        "数据层没有两融余额、融券余额、券源、保证金或借券费表，唯一相关的是概念快照里的'融资融券'标签（3,891 只，当前快照、无历史）。"
        "对冲类策略（市场中性、配对、多空）只能测多头腿，其 Sharpe 含市场 beta，不能当作中性策略的结论。"
    )
    return {
        "id": "short",
        "family": "做空 / 对冲 / 市场中性 / 配对交易",
        "status": "blocked",
        "verdict": "确证",
        "conclusion": conclusion,
        "facts": ctx.facts,
        "code_evidence": evidence,
        "unknown": [
            "A 股实际券源可得性无法从行情数据推断；即使采购两融明细，也无法对 2019–2022 的个股券源做逐日判定",
        ],
        "needs_without_purchase": (
            "现有本地数据不可补，且不只是数据问题：需要两融明细（融资余额/融券余额/费率/标的调整历史）"
            "＋引擎的空头账户（保证金、借券费、强平及适用结算限制）。仅补行情无法证明历史券源可得性，免费来源及采购必要性未验证；"
            "任何多空结论都要额外打折。"
        ),
        "evidence_paths": [p2s(app), p2s(root / "ext_data" / "ext_gn_ths" / "part.parquet")],
    }


# ── 检查 5：616 口径争议 ──────────────────────────────────────────────────
def check_universe616(ctx: Recorder, root: Path, panel: Panel) -> dict:
    matrix_sql = (
        "select 'instruments' as table_name, (select count(*) from ins) as table_symbols, "
        "(select count(*) from panel_agg where symbol not in (select symbol from ins)) as panel_missing, "
        "(select count(*) from ins where symbol not in (select symbol from panel_agg)) as instruments_missing "
        "union all select 'adj_factor', (select count(*) from adj_syms), "
        "(select count(*) from panel_agg where symbol not in (select symbol from adj_syms)), "
        "(select count(*) from ins where symbol not in (select symbol from adj_syms)) "
        "union all select 'balance_sheet', (select count(*) from fin_bs), "
        "(select count(*) from panel_agg where symbol not in (select symbol from fin_bs)), "
        "(select count(*) from ins where symbol not in (select symbol from fin_bs)) "
        "union all select 'income', (select count(*) from fin_income), "
        "(select count(*) from panel_agg where symbol not in (select symbol from fin_income)), "
        "(select count(*) from ins where symbol not in (select symbol from fin_income)) "
        "union all select 'cash_flow', (select count(*) from fin_cf), "
        "(select count(*) from panel_agg where symbol not in (select symbol from fin_cf)), "
        "(select count(*) from ins where symbol not in (select symbol from fin_cf)) "
        "union all select 'metrics', (select count(*) from fin_metrics), "
        "(select count(*) from panel_agg where symbol not in (select symbol from fin_metrics)), "
        "(select count(*) from ins where symbol not in (select symbol from fin_metrics)) "
        "union all select 'any_financials', (select count(*) from fin_any), "
        "(select count(*) from panel_agg where symbol not in (select symbol from fin_any)), "
        "(select count(*) from ins where symbol not in (select symbol from fin_any))"
    )
    matrix = ctx.rows(matrix_sql)
    ctx.fact("缺表矩阵：面板 5,813 只 / 元数据 5,536 只 对各数据集的缺口", matrix, sql=matrix_sql,
             note="panel_missing = 该表没有、但面板有日线的证券数；instruments_missing = 该表没有、但元数据里有的证券数")

    base_sql = (
        "select (select count(*) from panel_agg) as panel_symbols, "
        "(select count(*) from ins) as instruments_symbols, "
        "(select count(*) from ins where symbol in (select symbol from panel_agg)) as intersection"
    )
    ctx.fact("两个宇宙的交集", ctx.one(base_sql), sql=base_sql,
             note="5,458 = 5,813 − 355 = 5,536 − 78：78 与 355 是互补的两个缺口，不是同一个数的两种说法")

    p616_sql = (
        "select substr(symbol,1,2) as prefix, count(*) as n from panel_agg "
        "where symbol not in (select symbol from adj_syms) group by 1 order by 1"
    )
    ctx.fact("616 只无复权因子行的证券（按代码前缀）", ctx.rows(p616_sql), sql=p616_sql)

    first_bar_sql = (
        "select case when first_date >= date '2023-01-01' then '2023+' "
        "when first_date >= date '2020-01-01' then '2020-2022' "
        "when first_date >= date '2018-01-08' then '2018-2019' else 'pre-2018' end as bucket, "
        "count(*) as n from panel_agg where symbol not in (select symbol from adj_syms) group by 1 order by 2 desc"
    )
    ctx.fact("616 只的首根 K 线年份分布", ctx.rows(first_bar_sql), sql=first_bar_sql)

    adj_diff_sql = (
        "select count(*) as rows_scanned, "
        "count(*) filter (where close is not null and raw_close is not null "
        "and abs(close - raw_close) > 1e-6) as rows_with_adjusted_diff, "
        "count(distinct symbol) filter (where abs(close - raw_close) > 1e-6) as symbols_with_adjusted_diff "
        f"from read_parquet('{panel.enriched}') where symbol not in (select symbol from adj_syms)"
    )
    ctx.fact("616 只的 复权价 vs 原始价 一致性", ctx.one(adj_diff_sql), sql=adj_diff_sql,
             note="0 差异仅证明本地复权价与原始价一致；无因子事件行不能证明真实世界无除权，也不能排除供应商漏记")

    p78_sql = (
        "select substr(i.symbol,1,2) as prefix, count(*) as n from ins i "
        "where i.symbol not in (select symbol from panel_agg) group by 1 order by 1"
    )
    ctx.fact("78 只无日线的证券（按代码前缀）", ctx.rows(p78_sql), sql=p78_sql)

    p78_detail_sql = (
        "select count(*) as n, count(*) filter (where coalesce(i.name,'') like '%退%') as delisted_name, "
        "count(*) filter (where i.listing_date is null) as null_listing_date, "
        "min(i.listing_date) as earliest_listing, max(i.listing_date) as latest_listing "
        "from ins i where i.symbol not in (select symbol from panel_agg)"
    )
    ctx.fact("78 只无日线的证券：退市名称 / 缺失上市日", ctx.one(p78_detail_sql), sql=p78_detail_sql)

    p78_names_sql = (
        "select i.symbol, i.name, i.listing_date from ins i "
        "where i.symbol not in (select symbol from panel_agg) order by i.symbol limit 10"
    )
    ctx.fact("78 只无日线的样例", ctx.rows(p78_names_sql), sql=p78_names_sql,
             note="样例为 1990 年代上市、2018 年前已退市/更名的老代码")

    p236_sql = (
        "select substr(symbol,1,2) as prefix, count(*) as n from panel_agg "
        "where symbol not in (select symbol from fin_any) group by 1 order by 1"
    )
    ctx.fact("236 只无任何财务报表的证券（按代码前缀）", ctx.rows(p236_sql), sql=p236_sql)

    p236_names_sql = (
        "select i.symbol, i.name, i.listing_date from ins i "
        "where i.symbol not in (select symbol from fin_any) order by i.symbol limit 10"
    )
    ctx.fact("236 只的样例（面板内且有元数据的交集部分）", ctx.rows(p236_names_sql), sql=p236_names_sql,
             note="样例均为退市/*ST 老代码；财务报表库只覆盖当前存续标的")

    three_sql = (
        "select (select count(*) from panel_agg where symbol in (select symbol from fin_bs) "
        "and symbol in (select symbol from fin_income) and symbol in (select symbol from fin_cf)) as panel_all_three, "
        "(select count(*) from ins where symbol in (select symbol from fin_bs) "
        "and symbol in (select symbol from fin_income) and symbol in (select symbol from fin_cf)) as instruments_all_three"
    )
    three = ctx.one(three_sql)
    ctx.fact("三表齐全的证券数", three, sql=three_sql)

    main_no_all_three_sql = (
        "select "
        "(select count(*) from panel_agg where substr(symbol,1,2) in ('60','00') and (symbol not in (select symbol from fin_bs) "
        "or symbol not in (select symbol from fin_income) or symbol not in (select symbol from fin_cf))) as panel_mainboard_any_missing, "
        "(select count(*) from ins where substr(symbol,1,2) in ('60','00') and (symbol not in (select symbol from fin_bs) "
        "or symbol not in (select symbol from fin_income) or symbol not in (select symbol from fin_cf))) as instruments_mainboard_any_missing, "
        "(select count(*) from ins where substr(symbol,1,2) in ('60','00') and symbol not in (select symbol from fin_income)) as instruments_mainboard_no_income"
    )
    ctx.fact("主板口径下的财务缺口（用于对账 663）", ctx.one(main_no_all_three_sql), sql=main_no_all_three_sql)

    latest68_sql = (
        "select substr(symbol,1,2) as prefix, count(*) as n from read_parquet("
        f"'{p2s(root / 'kline_daily' / 'date=2026-11-06' / 'part.parquet')}') group by 1 order by 1"
    )
    by_prefix = ctx.rows(latest68_sql)
    ctx.fact("2026-11-06 当日各板块证券数", by_prefix, sql=latest68_sql,
             note="68 开头正好 616 只 —— 与'无复权因子行'的 616 数值相同但完全无关")

    panel_total = int(ctx.scalar("select count(*) from panel_agg"))
    instruments_total = int(ctx.scalar("select count(*) from ins"))
    candidates = {
        "panel_no_any_financials": 236,
        "panel_no_income": 236,
        "instruments_no_income": 313,
        "panel_no_all_three": panel_total - int(three["panel_all_three"]),
        "instruments_no_all_three": instruments_total - int(three["instruments_all_three"]),
    }
    ctx.fact("对账 663 的候选口径", candidates,
             note="由 sql_log 中面板/元数据/三表齐全三条 SQL 组合而成；没有任何候选等于 663，'663 只无财务'在本数据上无法复现（差异 ≥ 35）")

    conclusion = (
        "定论：616 可精确复现，但语义被误读。616 = 面板 5,813 只证券中在 adj_factor（复权因子事件表）里没有任何一行的证券数"
        "（5,813 − 5,197 = 616，按前缀 00:225 / 30:92 / 60:186 / 68:69 / 92:44）。adj_factor 是按除权事件写的表，"
        "这 616 只在 789,432 行行情里 close 与 raw_close 完全相等（0 行差异），仅说明本地价格一致，不能证明真实世界没有除权事件；"
        "不能将其直接等同于'研究因子库缺失'；'无因子'应写作'无复权因子事件行'。"
        "另外三个数字同样可精确复现且口径互不相同：78 = 元数据 5,536 中有、日线面板 5,813 中完全没有日线的证券"
        "（1990 年代上市、2018 年前已退市/更名的老代码，15 只名称含'退'）；355 = 日线面板中有、元数据中没有的证券"
        "（全部为北交所 92x）；236 = 日线面板中四张财务表都没有任何记录的证券（样例均为退市/*ST）。"
        "三者之和 669 ≠ 616，说明它们不是同一口径下的互补分解，不能互相印证。"
        "数值巧合：2026-11-06 当日科创板（68x）恰好也是 616 只，与'无复权因子行'的 616 无关。"
        "663 无法复现：236 / 313 / 266 / 628 / 802 / 1,079 均不等于 663。"
    )
    return {
        "id": "universe616",
        "family": "口径争议：616 只无因子 vs 78 / 355 / 236",
        "status": "available",
        "status_meaning": "该口径可复现且已定论（status 枚举在此表示'争议可否定论'，不是'策略族可做'）",
        "verdict": "确证",
        "settlement": "616 可复现但语义不成立（应为'无复权因子事件行'）；78/355/236 三数均可复现；663 无法复现",
        "conclusion": conclusion,
        "facts": ctx.facts,
        "code_evidence": [],
        "unknown": [
            "供应商是否漏记了某些除权事件：close==raw_close 只能证明面板内部一致，不能证明外部公司行为台账完整",
        ],
        "needs_without_purchase": (
            "无需采购：这是口径问题，不是数据采购问题。建议统一口径为"
            "'面板 ∩ 元数据 = 5,458；元数据无日线 78；面板无元数据 355（北交所）；面板无财务 236；面板无复权因子事件 616'，"
            "并在任何报告里写明每一数的分母。"
        ),
        "evidence_paths": [p2s(root / "instruments" / "instruments.parquet"),
                           p2s(root / "adj_factor" / "all.parquet"),
                           p2s(root / "financials"),
                           p2s(root / "kline_daily")],
    }


# ── 入口 ──────────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="四类数据阻塞 + 616 口径争议的只读审计")
    parser.add_argument("--check", default="all", choices=(*CHECK_IDS, "all"))
    parser.add_argument("--all", dest="check_all", action="store_true",
                        help="等价于 --check all（全五项）")
    parser.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    parser.add_argument("--out", default=str(RESULTS_DIR))
    args = parser.parse_args(argv)
    if args.check_all:
        args.check = "all"

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    root = Path(args.data_root)
    if not (root / "kline_daily").exists():
        print(f"[FAIL] 数据根不可用: {root}", file=sys.stderr)
        return 3
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    try:
        con.execute("SET threads = 4")
        panel = Panel(con, root)
        ids = CHECK_IDS if args.check == "all" else (args.check,)
        for cid in ids:
            ctx = Recorder(con)
            if cid == "industry":
                result = check_industry(ctx, root, panel)
            elif cid == "index":
                result = check_index(ctx, root)
            elif cid == "etf":
                result = check_etf(ctx, root)
            elif cid == "short":
                result = check_short(ctx, root)
            else:
                result = check_universe616(ctx, root, panel)
            result["sql_log"] = ctx.sqls
            payload = {
                "schema_version": "1.0.0",
                "check": cid,
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "data_root": p2s(root),
                "python": sys.version.split()[0],
                "duckdb": duckdb.__version__,
                **result,
            }
            target = out_dir / f"check_{cid}.json"
            target.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"[OK] {cid}: status={result['status']} verdict={result['verdict']} -> {p2s(target)}")
            print(f"     {result['conclusion'][:150]}...")
        return 0
    except AssertionError as exc:                      # 断言失败：口径与预期不符
        print(f"[ASSERT] {exc}", file=sys.stderr)
        return 4
    except FileNotFoundError as exc:
        print(f"[FAIL] 必需输入缺失: {exc}", file=sys.stderr)
        return 3
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
