"""把 2026-11-07 复算复核的修正写回 E3_DATA_AVAILABILITY_20261107.md。

只做定点替换，每处都断言「原文出现且仅出现一次」，避免误改。
"""
from __future__ import annotations

from pathlib import Path

DOC = Path(r"C:\work\sourcecode\tick-stock-panel\docs\factors\evidence\E3_DATA_AVAILABILITY_20261107.md")
V = Path(r"C:\work\sourcecode\tick-stock-panel\research\e3-data-availability-20261107\verify")

NEW_B2 = '''# C2 as-of 合并到全部 K 线格 → 三态与逐年分布（duckdb ASOF 版；polars 版跑不通，原因见 §10）
cd /c/work/sourcecode/tick-stock-panel && backend/.venv/Scripts/python.exe - <<'PY'
import duckdb
con = duckdb.connect(); con.execute("SET threads=8")
con.execute("CREATE VIEW k AS SELECT symbol, CAST(date AS DATE) d FROM read_parquet('D:/TSP/data/kline_daily/date=*/*.parquet', hive_partitioning=true, union_by_name=true)")
con.execute("CREATE VIEW st AS SELECT symbol, CAST(flag_date AS DATE) fd, st_flag FROM read_parquet('D:/TSP/data/st_history/part.parquet')")
con.execute("CREATE TABLE sj AS SELECT k.symbol, k.d, s.st_flag FROM k ASOF LEFT JOIN st s ON k.symbol = s.symbol AND k.d >= s.fd")
print(con.execute("SELECT count(*), count(*) FILTER (WHERE st_flag IS NULL), count(*) FILTER (WHERE st_flag) FROM sj").fetchone())
print(con.execute("SELECT year(d), count(*), count(*) FILTER (WHERE st_flag IS NULL), count(*) FILTER (WHERE st_flag) FROM sj GROUP BY 1 ORDER BY 1").fetchall())
PY
# 实测输出: (9780842, 755763, 276079)
# [(2018, 755758, 755758, 0), (2019, 848337, 0, 20553), (2020, 949498, 0, 42391), (2021, 1072678, 0, 45152),
#  (2022, 1170796, 0, 36264), (2023, 1258250, 0, 29179), (2024, 1293409, 0, 29047), (2025, 1313507, 0, 37400),
#  (2026, 1118609, 5, 36093)]
'''

NEW_B6 = '''# 缺口段长分布（未清洗，权威口径；duckdb 版，复用上一段的 cal/grid/miss）
cd /c/work/sourcecode/tick-stock-panel && backend/.venv/Scripts/python.exe - <<'PY'
import duckdb
con = duckdb.connect(); con.execute("SET threads=8")
con.execute("CREATE VIEW k AS SELECT symbol, CAST(date AS DATE) d FROM read_parquet('D:/TSP/data/kline_daily/date=*/*.parquet', hive_partitioning=true, union_by_name=true)")
con.execute("CREATE TABLE cal AS SELECT d, row_number() OVER (ORDER BY d) di FROM (SELECT DISTINCT d FROM k)")
con.execute("CREATE TABLE ps AS SELECT symbol, min(d) fb, max(d) lb FROM k GROUP BY 1")
con.execute("CREATE TABLE grid AS SELECT p.symbol, c.d, c.di FROM ps p JOIN cal c ON c.d BETWEEN p.fb AND p.lb")
con.execute("CREATE TABLE miss AS SELECT g.* FROM grid g ANTI JOIN (SELECT DISTINCT symbol, d FROM k) x USING(symbol, d)")
con.execute("""CREATE TABLE runs AS
  WITH m AS (SELECT symbol, di, di - row_number() OVER (PARTITION BY symbol ORDER BY di) g FROM miss)
  SELECT symbol, count(*) "len", min(di) a, max(di) b FROM m GROUP BY symbol, g""")
print(con.execute('SELECT count(*), count(DISTINCT symbol), max("len") FROM runs').fetchone())
print(con.execute("""SELECT CASE WHEN "len"=1 THEN '1' WHEN "len"=2 THEN '2' WHEN "len"=3 THEN '3'
 WHEN "len"<=5 THEN '4-5' WHEN "len"<=10 THEN '6-10' WHEN "len"<=20 THEN '11-20'
 WHEN "len"<=60 THEN '21-60' WHEN "len"<=250 THEN '61-250' ELSE '>250' END b, count(*), sum("len")
 FROM runs GROUP BY 1 ORDER BY min("len")""").fetchall())
PY
# 实测输出: (4549, 2083, 589)
# [('1',2013,2013),('2',204,408),('3',170,510),('4-5',668,3233),('6-10',992,9157),
#  ('11-20',114,1794),('21-60',222,8243),('61-250',158,15403),('>250',8,2742)]
'''

NEW_B7 = None  # 由 b7.sh 改写标签生成

GIT_STATUS = '''```
 M research/strategy-search-20261107/REPORT.md
 M research/strategy-search-20261107/results/registry.json
?? backend/app/custom/research_factor_pack/
?? docs/architecture/
?? docs/factors/
?? docs/research/caliber-decisions-20261107.md
?? docs/research/factor-audit-20261107/
?? research/e3-data-availability-20261107/
?? research/factor-registration-20261107/
?? research/independent-review-20261107/
?? research/jiaogedan-review-20261107/
?? research/strategy-search-20261107/FACTOR_MAP_v1.md
?? research/strategy-search-20261107/RULE-CHANGE-20261107.md
?? research/strategy-search-20261107/factor_map_v1.json
?? research/strategy-search-20261107/scripts/factor_map_build.py
?? research/trade-ledger-20261107/
```'''


def rep(text: str, old: str, new: str, tag: str) -> str:
    n = text.count(old)
    assert n == 1, f"{tag}: 期望 1 处，实际 {n} 处"
    return text.replace(old, new)


def main() -> None:
    s = DOC.read_text(encoding="utf-8").replace("\r\n", "\n")
    b2 = (V / "b2.sh").read_text(encoding="utf-8").replace("\r\n", "\n")
    b6 = (V / "b6.sh").read_text(encoding="utf-8").replace("\r\n", "\n")
    b7 = (V / "b7.sh").read_text(encoding="utf-8").replace("\r\n", "\n")

    # --- 头部：补复算复核记录 ---
    s = rep(
        s,
        "- 写作口径：**确证**＝本次实测复现的数字；",
        "- 复算复核：2026-11-07 15:00–15:25，本文件每条「可复算命令」都在本机逐条执行，退出码全 0；"
        "其中两条 polars 命令已改为 duckdb 等价实现（原因见 §10）。\n"
        "- 写作口径：**确证**＝本次实测复现的数字；",
        "header",
    )

    # --- 事实修正 1：ST 基线 True 只数 11 → 9 ---
    s = rep(
        s,
        "其中 True **11** 只 |",
        "其中 True **9** 只（复算 `count(*) filter (where st_flag)` = 9、`count(distinct symbol)` = 9；初稿写 11 是笔误） |",
        "baseline",
    )

    # --- 事实修正 2：<60 日的 11 只 ST 分布 1/10 → 3/8 ---
    s = rep(
        s,
        "<60 日的 11 只中 True 1 只、False 10 只",
        "<60 日的 11 只中 True **3** 只、False **8** 只",
        "lt60",
    )

    # --- 命令修正 1：C1 的 `rows` 是 duckdb 保留字 ---
    s = rep(s, "SELECT count(*) rows,", "SELECT count(*) n_rows,", "c1")

    # --- 命令修正 2/3：两条 polars 命令换成 duckdb ---
    s = rep(s, b2, NEW_B2, "b2")
    s = rep(s, b6, NEW_B6, "b6")

    # --- 命令修正 4：§5.6 中文标签在 GBK 控制台乱码，改 ASCII ---
    b7new = (b7.replace('print("消失:"', 'print("gone:"')
               .replace('print("按缺口交易日分桶:"', 'print("buckets_by_missing_days:"')
               .replace('print("维表有/无 K 线:"', 'print("instruments_without_bar:"')
               .replace('print("现名含退:"', 'print("name_contains_tui:"'))
    s = rep(s, b7, b7new, "b7")

    # --- §0 退市一行：补「≥250 日≠退市」的反证 ---
    s = rep(
        s,
        "≥250 个交易日无行情的 209 只可视为已退市，但 <60 个交易日的 11 只无法区分停牌与退市",
        "「最后一根 K 线」在 T 日不可知；≥250 个交易日无行情的 209 只只能做事后近似，"
        "且库内存在 **8 段 ≥250 个交易日的中途缺口后来复牌**（最长 589 日），故 ≥250 日不能单独证明退市；"
        "<60 个交易日的 11 只完全无法区分停牌与退市",
        "sec0_delist",
    )

    # --- §5.4 追加反证段 ---
    s = rep(
        s,
        "补充一条**反向证据**，说明「现名含退」不能当日判据：",
        "**第二条反证（对「≥250 日＝退市」这条近似本身的证伪）**：全库有 **8 段 >250 个交易日的中途缺口后来复牌**——"
        "`000670.SZ` 589 个交易日（2020-03-20..2022-08-19）、`000995.SZ` 399（2019-04-26..2020-12-15）、"
        "`600610.SH` 316（2019-04-30..2020-08-14）、`002323.SZ` 314、`000792.SZ` 311 等。"
        "也就是说「长时间没有 bar」既可能是退市，也可能是跨年的长期停牌（重组/重大事项）。"
        "209 只只是在「到数据末端仍未回归」这个意义上可作 **事后** 近似陈述，"
        "不能反推成「该标的在 T 日已退市」，更不能当天进入池判据。\n\n"
        "补充一条**反向证据**，说明「现名含退」不能当日判据：",
        "sec5_counter",
    )

    # --- §5.5 结论补一句 ---
    s = rep(
        s,
        "能可靠给出的只有「该标的已连续 ≥250 个交易日无行情」（209 只）这一事后陈述。",
        "能可靠给出的只有「该标的已连续 ≥250 个交易日无行情、且到数据末端未回归」（209 只）这一事后陈述；"
        "而这条陈述本身也被 8 段 >250 日又复牌的缺口证伪了「无行情即退市」的充分性（§5.4）。",
        "sec5_5",
    )

    # --- §9 git 状态刷新 ---
    old_git = s[s.index("```\n?? docs/architecture/"):s.index("本文件是本轮唯一新增")]
    s = s.replace(old_git, GIT_STATUS + "\n\n", 1)
    s = rep(
        s,
        "本文件是本轮唯一新增；以上未提交改动一律未触碰。",
        "本文件与本目录下的取证/复核脚本是本轮唯一新增（`research/e3-data-availability-20261107/`）；"
        "以上未提交改动一律未触碰。",
        "sec9_tail",
    )

    # --- 附录：脚本位置 ---
    s = rep(
        s,
        "取证脚本落在仓库外的临时目录 `C:\\Users\\A\\AppData\\Local\\Temp\\e3probe\\`（`s1.py`..`s18.py`、`q1.py`..`q14.py`），"
        "**未写入仓库**；文中每条结论下方已给出可直接粘贴运行的等价命令。",
        "取证脚本（均在 `research/e3-data-availability-20261107/`，只读数据）：\n\n"
        "| 脚本 | 覆盖 |\n"
        "| --- | --- |\n"
        "| `e3_probe.py` | A 面 + F1 停牌 + F2 限价 + F3 退市 + F4 上市 + F5 ST，共 50 个具名查询，输出 `e3_raw.json` |\n"
        "| `verify/b1.sh`..`b8.sh` | 本文件 §2.7/§3.6/§4.6/§5.6 的命令原文，逐条抽出后直接执行 |\n"
        "| `verify/verify_gaps_st.py` | §4.2 缺口段长分布 + §2.2 ST 三态逐年（替代两条 polars 命令） |\n"
        "| `verify/verify_st_detail.py` | §2.2 全部 ST 细节 + §1 布局数字 |\n"
        "| `verify/verify_st_lastbar.py` | §5.2「消失时是否 ST」与最后 bar 年份 |\n"
        "| `verify/verify_shells.py` | §5.2 维表壳（78 只）、现名含退（155/140）、近 12 个月消失 |\n\n"
        "文中每条结论下方已给出可直接粘贴运行的等价命令（不复用脚本即可复现）。",
        "appendix_scripts",
    )

    # --- 附录：补索引行 ---
    s = rep(
        s,
        "| C11 | §5.6 | `241 / 分桶 / 78 / (155,140)` |",
        "| C11 | §5.6 | `241 / 分桶 / 78 / (155,140)` |\n"
        "| C12 | §2.2 | 2019-01-01 基线 True **9** 只（初稿 11 为笔误） |\n"
        "| C13 | §2.2 | 曾经 ST 712 / 5,817；切换次数中位数 1、最大 9 |\n"
        "| C14 | §5.2 | ≥250 日 209 只：最后 bar 上 ST True 70 / False 139；<60 日 11 只：True 3 / False 8 |\n"
        "| C15 | §5.4 | >250 日缺口 8 段且全部复牌：589/399/316/314/311…（`verify/verify_gaps_st.py`） |",
        "appendix_index",
    )

    # --- 新增 §10 ---
    s = rep(
        s,
        "---\n\n## 附录：数字索引（便于抽查）",
        "---\n\n## 10. 复算时踩到的三个坑（命令层面，已在本文件内修正）\n\n"
        "| # | 现象 | 处理 |\n"
        "| --- | --- | --- |\n"
        "| 1 | duckdb 1.5.3 里 `rows`、`days`、`len` 不能直接当列别名（`Parser Error: syntax error at or near \"rows\"`） | C1 改用 `n_rows`；段长用 `\"len\"`、`n_days` |\n"
        "| 2 | polars 3.0.3 的 `read_parquet()` **不接受** `extra_columns`（那是 `scan_parquet` 的参数），且 `date=*/*.parquet` 的多 schema 通配直接读会失败 | C2 与「缺口段长分布」两段已换成 duckdb 的 `ASOF LEFT JOIN` / 窗口函数等价实现，输出与原数字逐位一致 |\n"
        "| 3 | Windows 控制台默认 GBK，带中文标签的 `print` 会乱码（**数字不受影响**） | 复算前 `set PYTHONIOENCODING=utf-8`（bash: `PYTHONIOENCODING=utf-8 ...`）；§5.6 的标签已改成 ASCII |\n\n"
        "---\n\n## 附录：数字索引（便于抽查）",
        "sec10",
    )

    DOC.write_text(s, encoding="utf-8", newline="\n")
    print("ok", len(s), s.count("\n") + 1, "lines")


if __name__ == "__main__":
    main()
