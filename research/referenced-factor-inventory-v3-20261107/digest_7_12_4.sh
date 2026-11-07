python - <<'PY'
import json, hashlib
p = 'docs/architecture/evidence/referenced_factor_inventory.json'
DROP = {'generated_at', 'repo_head', 'data_root', 'canonical_digest'}
rk = lambda x: json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
d = json.load(open(p, encoding='utf-8'))
q = {k: v for k, v in d.items() if k not in DROP}
q['records'] = sorted(q.get('records', []), key=rk)
blob = json.dumps(q, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
print(hashlib.sha256(blob.encode('utf-8')).hexdigest())
PY
