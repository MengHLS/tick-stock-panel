-- 交割单复盘·市场环境部分：明细表重建脚本（DuckDB）
-- 依赖：D:\TSP\data（regime_history / mainline_history / kline_index_daily / instruments / ext_data）
--       C:\work\sourcecode\tick-stock-panel\research\jiaogedan-review-20261107\data（trades_clean.csv / roundtrips.csv /
--       roundtrip_tags_attribution.csv / daily_equity.csv）
-- 产出：daily.csv / feat.csv / buys.csv（market/ 目录），再交给 mkt_report3.py 生成 REPORT_market.md

CREATE OR REPLACE TABLE regime AS
SELECT * FROM read_parquet('D:/TSP/data/regime_history/part.parquet');

CREATE OR REPLACE TABLE mainline AS
SELECT * FROM read_parquet('D:/TSP/data/mainline_history/part.parquet');

CREATE OR REPLACE TABLE idx AS
SELECT * FROM read_parquet('D:/TSP/data/kline_index_daily/*/*.parquet', union_by_name=true);

CREATE OR REPLACE TABLE inst AS
SELECT * FROM read_parquet('D:/TSP/data/instruments/instruments.parquet');

-- 个股行业：仅 2026-11-01~06 六个快照，按最新日回溯使用
CREATE OR REPLACE TABLE ind_pit AS
SELECT CAST(date AS DATE) AS date, code, symbol, "所属同花顺行业" AS ths_ind
FROM read_parquet('D:/TSP/data/ext_data/ext_hy_ths_pit/timeseries/date=*/part.parquet');

CREATE OR REPLACE TABLE gn AS
SELECT symbol, code, unnest(string_split("所属概念", ';')) AS concept
FROM read_parquet('D:/TSP/data/ext_data/ext_gn_ths/part.parquet');

CREATE OR REPLACE TABLE tw AS SELECT * FROM read_csv_auto('.../data/trades_clean.csv', header=true);
CREATE OR REPLACE TABLE rta AS SELECT * FROM read_csv_auto('.../data/roundtrip_tags_attribution.csv', header=true);
CREATE OR REPLACE TABLE deq AS SELECT * FROM read_csv_auto('.../data/daily_equity.csv', header=true);

CREATE OR REPLACE TABLE idxp AS
SELECT symbol, date, close,
       close / lag(close) OVER (PARTITION BY symbol ORDER BY date) - 1 AS pct
FROM idx
WHERE symbol IN ('000300.SH','000852.SH','399303.SZ','000001.SH','000905.SH')
  AND date BETWEEN DATE '2024-12-01' AND DATE '2026-11-07';

CREATE OR REPLACE TABLE daily AS
WITH p AS (
  SELECT date,
    max(CASE WHEN symbol='000300.SH' THEN close END) c300, max(CASE WHEN symbol='000300.SH' THEN pct END) p300,
    max(CASE WHEN symbol='000852.SH' THEN close END) c1000, max(CASE WHEN symbol='000852.SH' THEN pct END) p1000,
    max(CASE WHEN symbol='399303.SZ' THEN close END) cgz2000, max(CASE WHEN symbol='399303.SZ' THEN pct END) pgz2000,
    max(CASE WHEN symbol='000001.SH' THEN close END) csh, max(CASE WHEN symbol='000001.SH' THEN pct END) psh
  FROM idxp GROUP BY 1
)
SELECT g.date, g.phase, g.state, g.score, g.limit_up, g.limit_down, g.broken_limit, g.seal_rate,
       g.up_count, g.down_count, g.up_ratio, g.index_pct, g.above_ma20_pct, g.avg_pct, g.median_pct,
       g.total_amount, g.strong_up_pct, g.strong_down_pct,
       p.c300, p.p300, p.c1000, p.p1000, p.cgz2000, p.pgz2000, p.csh, p.psh,
       d.equity, d.mv, d.cash, d.dep, d.pnl, d.npos
FROM regime g
LEFT JOIN p ON p.date = g.date
LEFT JOIN deq d ON d.date = g.date
WHERE g.date BETWEEN DATE '2025-03-20' AND DATE '2026-11-07'
ORDER BY g.date;

CREATE OR REPLACE TABLE feat AS
WITH si AS (SELECT code, min(ths_ind) AS ths_ind FROM ind_pit WHERE date = DATE '2026-11-05' GROUP BY 1),
     sym AS (SELECT code, min(symbol) AS symbol FROM ind_pit GROUP BY 1),
     ml AS (SELECT date, kind, member, rank, leader_symbol FROM mainline
            WHERE date BETWEEN DATE '2025-03-20' AND DATE '2026-11-06'),
     b AS (SELECT r.*, printf('%06d', r."代码") AS code6 FROM rta r),
     ir AS (SELECT s.code, ml.date, min(ml.rank) AS rk FROM si s
            JOIN ml ON ml.kind='industry' AND ml.member IN (s.ths_ind, split_part(s.ths_ind,'-',1)) GROUP BY 1,2),
     gr AS (SELECT g.code, ml.date, min(ml.rank) AS rk FROM gn g
            JOIN ml ON ml.kind='concept' AND ml.member=g.concept GROUP BY 1,2),
     lr AS (SELECT i.symbol, ml.date, min(ml.rank) AS rk FROM inst i
            JOIN ml ON ml.leader_symbol=i.symbol GROUP BY 1,2)
SELECT b."代码" AS code, b.code6, b."名称" AS name, b."品种" AS pkind, b."买入日" AS buy_date, b."卖出日" AS sell_date,
       b."持有交易日" AS hold_td, b."买入成本" AS cost, b."盈亏" AS pnl, b."收益率pct" AS ret_pct,
       b."市场beta" AS beta_pnl, b."选股alpha" AS alpha_pnl, b."主标签" AS tag,
       si.ths_ind, ir.rk AS ind_rank, gr.rk AS gn_rank, lr.rk AS leader_rank,
       dd.phase, dd.state, dd.limit_up, dd.limit_down, dd.broken_limit, dd.up_count, dd.down_count,
       dd.up_ratio, dd.index_pct, dd.above_ma20_pct, dd.avg_pct, dd.median_pct, dd.total_amount,
       dd.p300, dd.p1000, dd.pgz2000, dd.psh, dd.npos
FROM b
LEFT JOIN si ON si.code = b.code6
LEFT JOIN sym ON sym.code = b.code6
LEFT JOIN ir ON ir.code = b.code6 AND ir.date = b.buy_date
LEFT JOIN gr ON gr.code = b.code6 AND gr.date = b.buy_date
LEFT JOIN lr ON lr.symbol = sym.symbol AND lr.date = b.buy_date
LEFT JOIN daily dd ON dd.date = b.buy_date
ORDER BY b."买入日";

CREATE OR REPLACE TABLE buys AS
SELECT t.date AS buy_date, t.code, t.name, t.type, t.amt, t.qty,
       d.phase, d.state, d.limit_up, d.limit_down, d.broken_limit, d.up_count, d.down_count,
       d.up_ratio, d.index_pct, d.above_ma20_pct, d.avg_pct, d.median_pct, d.p300, d.p1000, d.pgz2000, d.psh
FROM tw t LEFT JOIN daily d ON d.date = t.date
WHERE t.side = 'B'
ORDER BY t.date, t.time;

-- 导出：COPY (SELECT * FROM feat) TO 'market/feat.csv' (HEADER, DELIMITER ',');
--       COPY (SELECT * FROM buys) TO 'market/buys.csv' (HEADER, DELIMITER ',');
--       COPY (SELECT * FROM daily) TO 'market/daily.csv' (HEADER, DELIMITER ',');
