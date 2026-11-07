import sys, glob, re
sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd, numpy as np, polars as pl

# ---------- 1. daily bars + features ----------
files = sorted(glob.glob('D:/TSP/data/kline_daily_enriched/date=*'))
files = [f for f in files if f[-10:] >= '2024-11-01']
print('partitions', len(files), flush=True)
df = pl.read_parquet(files, columns=['symbol','date','open','high','low','close','raw_close','consecutive_limit_ups','amount'])
df = df.with_columns(pl.col('date').cast(pl.Date)).sort(['symbol','date'])
df = df.with_columns([
    pl.col('raw_close').shift(1).over('symbol').alias('prev_raw'),
])
df = df.with_columns([(pl.col('raw_close')/pl.col('prev_raw')-1).alias('pct')])
df = df.with_columns([
    (pl.col('close')/pl.col('close').shift(1).over('symbol')-1).alias('pct_adj'),
])
for n in (20,60):
    df = df.with_columns((pl.col('close')/pl.col('close').shift(n).over('symbol')-1).alias(f'ret{n}'))
df = df.with_columns(pl.col('close').rolling_mean(20).over('symbol').alias('ma20'))
df = df.with_columns((pl.col('consecutive_limit_ups')>0).cast(pl.Int8).alias('lu'))
df = df.with_columns(pl.col('lu').rolling_sum(20).over('symbol').alias('lu20'))
df = df.with_columns(pl.col('lu').rolling_sum(60).over('symbol').alias('lu60'))
bars = df.select(['symbol','date','open','high','low','close','raw_close','pct','ret20','ret60','ma20','consecutive_limit_ups','lu20','lu60','amount']).to_pandas()
bars['code'] = bars['symbol'].str[:6]
bars['date'] = pd.to_datetime(bars['date'])
print('bars', bars.shape, flush=True)
bars.to_parquet('C:/work/sourcecode/tick-stock-panel/research/trade-ledger-20261107/pattern_review/bars_feat.parquet')

# ---------- 2. trades ----------
raw = pd.read_csv('D:/TSP/data/user_data/trade_ledger/inbox/jiaogedan_full_20261107.csv', encoding='gbk', dtype=str)
raw.columns = [c.strip() for c in raw.columns]
def clean_code(x):
    m = re.search(r'(\d{6})', str(x))
    return m.group(1) if m else None
raw['code'] = raw['证券代码'].map(clean_code)
raw['name'] = raw['证券名称'].str.strip()
raw['date'] = pd.to_datetime(raw['发生日期'], errors='coerce')
for c in ['成交数量','成交均价','成交金额','发生金额','佣金','其他费用','印花税','过户费']:
    raw[c] = pd.to_numeric(raw[c], errors='coerce')
raw['time'] = raw['发生时间'].str.strip()
buys = raw[raw['交易类别'].str.contains('买入') & raw['code'].notna()].copy()
buys = buys.rename(columns={'成交均价':'px','成交数量':'qty','成交金额':'amt'})
print('buys', len(buys), flush=True)

# ---------- 3. listing date ----------
inst = pd.read_parquet('D:/TSP/data/instruments/instruments.parquet')
print('inst cols', list(inst.columns), flush=True)
inst.to_csv('C:/work/sourcecode/tick-stock-panel/research/trade-ledger-20261107/pattern_review/_inst_head.csv', index=False)
