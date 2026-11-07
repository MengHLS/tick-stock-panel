import json, sys, hashlib

p = r'C:\work\sourcecode\tick-stock-panel\research\b2-engine-20261107\EVIDENCE_20261107.json'
raw = open(p, 'rb').read()
print('bytes', len(raw), 'sha256', hashlib.sha256(raw).hexdigest())
d = json.loads(raw.decode('utf-8'))

def show(key, cap=7000):
    print('\n' + '=' * 72)
    print('##', key)
    v = d.get(key)
    print(json.dumps(v, ensure_ascii=False, indent=1)[:cap])

for k in sys.argv[1:] or ['batch', 'generated_for', 'git_head', 'contract', 'paths', 'summary']:
    show(k)
