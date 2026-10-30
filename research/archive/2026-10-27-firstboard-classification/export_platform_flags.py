import csv,json,hashlib
from pathlib import Path
import duckdb
p=Path(__file__).parent
frozen=list(csv.DictReader((p/'shape-selection-paths.csv').open(encoding='utf-8')))
codes=['000810.SZ','002687.SZ','600785.SH','002354.SZ'];old={(x['symbol'],x['date']):x for x in frozen if x['symbol'] in codes}
c=duckdb.connect();q="SELECT symbol,date,open,high,low,close,consecutive_limit_ups FROM read_parquet('D:/TSP/data/kline_daily_enriched/date=*/*.parquet',hive_partitioning=true) WHERE date BETWEEN DATE '2025-01-01' AND DATE '2026-10-23' AND symbol IN ('000810.SZ','002687.SZ','600785.SH','002354.SZ') ORDER BY symbol,date"
result=c.execute(q);cols=[x[0] for x in result.description];new=[dict(zip(cols,r)) for r in result.fetchall()]
assert len(new)==len(old)
for r in new:
 r['date']=str(r['date']);o=old[(r['symbol'],r['date'])]
 for k in ['open','high','low','close']:assert float(o[k])==r[k],('SNAPSHOT_PRICE_MISMATCH',r['symbol'],r['date'],k)
file=p/'platform-firstboard-flags.csv'
with file.open('w',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(new)
manifest={'source':'D:/TSP/data/kline_daily_enriched','query':q,'rule':'consecutive_limit_ups == 1; platform candidates, not certified historical identities','price_alignment':'all four OHLC fields exactly equal to frozen chart inputs, all matching symbol/date rows','rows':len(new),'flags_csv_sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'chart_csv_sha256':hashlib.sha256((p/'shape-selection-paths.csv').read_bytes()).hexdigest(),'cutoff':'2026-10-23','source_flag_version':'read at export time; earlier flag snapshot not available'}
(p/'platform-firstboard-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS:',len(new),'rows aligned to frozen OHLC; platform flags exported')
