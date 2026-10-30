import csv
from pathlib import Path
from PIL import Image,ImageDraw
p=Path(__file__).parent;rows=list(csv.DictReader((p/'shape-selection-paths.csv').open(encoding='utf-8')))
codes=['000810.SZ','603901.SH','002687.SZ','600785.SH','603286.SH','002354.SZ','603466.SH','002747.SZ']
im=Image.new('RGB',(1400,1600),'white');d=ImageDraw.Draw(im)
for j,code in enumerate(codes):
 rs=[r for r in rows if r['symbol']==code][-251:];ox=(j%2)*700;oy=(j//2)*400
 d.text((ox+20,oy+10),code,fill='black');lo=min(float(r['low']) for r in rs);hi=max(float(r['high']) for r in rs)
 def y(v):return oy+360-(float(v)-lo)/(hi-lo)*310
 for i,r in enumerate(rs):
  x=ox+35+i*2.5;co='red' if float(r['close'])>=float(r['open']) else 'green'
  d.line((x,y(r['high']),x,y(r['low'])),fill=co);d.line((x,y(r['open']),x,y(r['close'])),fill=co,width=2)
 d.text((ox+20,oy+375),rs[0]['date']+' -- '+rs[-1]['date'],fill='black')
im.save(p/'shape-selection-review.png')
