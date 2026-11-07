import json, sys

p = r'C:\work\sourcecode\tick-stock-panel\research\b2-engine-20261107\EVIDENCE_20261107.json'
d = json.load(open(p, encoding='utf-8'))
path = sys.argv[1].split('.')
v = d
for k in path:
    v = v[int(k)] if isinstance(v, list) else v[k]
print(json.dumps(v, ensure_ascii=False, indent=1))
