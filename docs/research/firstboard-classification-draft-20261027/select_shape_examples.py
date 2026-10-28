import csv,json,hashlib,math
from pathlib import Path
import duckdb
p=Path(__file__).parent
src=Path('C:/work/sourcecode/stock-limit-up-analyzer/docs/research/FIRSTBOARD-20261023-RECURSIVE-2019-V1-20261026/target-chain-summary.csv')
old=list(csv.DictReader(src.open(encoding='utf-8-sig')));codes=[x['stockCode'] for x in old]
c=duckdb.connect();q="SELECT symbol,date,open,high,low,close,volume,raw_close FROM read_parquet('D:/TSP/data/kline_daily_enriched/date=*/*.parquet',hive_partitioning=true) WHERE date BETWEEN DATE '2025-01-01' AND DATE '2026-10-23' AND symbol IN ("+','.join("'"+x+"'" for x in codes)+") ORDER BY symbol,date"
r=c.execute(q);names=[x[0] for x in r.description];rows=[dict(zip(names,x)) for x in r.fetchall()]
for x in rows:x['date']=str(x['date'])
f=p/'shape-selection-paths.csv'
with f.open('w',newline='',encoding='utf-8') as o:w=csv.DictWriter(o,fieldnames=names);w.writeheader();w.writerows(rows)
metrics=[]
for item in old:
 rs=[x for x in rows if x['symbol']==item['stockCode']];before=rs[:-1]
 if len(before)<250:continue
 def ret(n):return before[-1]['close']/before[-1-n]['close']-1
 def pos(n):
  rr=before[-n:];lo=min(x['low'] for x in rr);hi=max(x['high'] for x in rr);return (before[-1]['close']-lo)/(hi-lo)
 def width(n):
  rr=before[-n:];return max(x['high'] for x in rr)/min(x['low'] for x in rr)-1
 m={'code':item['stockCode'],'name':item['stockName'],'r20':ret(20),'r60':ret(60),'r120':ret(120),'pos250':pos(250),'pos60':pos(60),'w20':width(20),'w60':width(60),'dd20':before[-1]['close']/max(x['high'] for x in before[-20:])-1}
 metrics.append(m)
(p/'shape-selection-metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding='utf-8')
(p/'shape-selection-manifest.json').write_text(json.dumps({'target':'2026-10-23','background_asof':'2026-10-22','source':'D:/TSP/data/kline_daily_enriched','query':q,'csv_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'rows':len(rows),'scope':'53旧目标候选中的形态选样，不是策略筛选或身份认证；当前读取快照与前次快照未断言一致','adjustment_basis':'本次读取的enriched存储快照；具体因子末日未另认证；每张图内部同一尺度','future_rows_used':False},ensure_ascii=False,indent=2),encoding='utf-8')
for label,score in [('低位窄幅',lambda x:x['pos250']+x['w60']+abs(x['r60'])),('上涨后震荡',lambda x:-x['r120']+abs(x['r20'])+x['w20']),('下跌反弹',lambda x:x['r120']-x['r20']),('上涨回调',lambda x:-x['r120']+x['r20'])]:
 print(label)
 for x in sorted(metrics,key=score)[:5]:print(json.dumps(x,ensure_ascii=False))
