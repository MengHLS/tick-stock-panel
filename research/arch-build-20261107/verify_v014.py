# -*- coding: utf-8 -*-
"""v0.14 举证脚本（R14 三项收口）。
只读：不写任何文件、不改 backend/**、不改 docs/factors/**。
可复跑：PYTHONIOENCODING=utf-8 python research/arch-build-20261107/verify_v014.py
"""
import hashlib
import json
import os
import re
import subprocess
import sys

CRLF = '\r\n'
LF = '\n'
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
V13 = os.path.join(ROOT, 'docs', 'architecture', 'FACTOR_ENGINE_CONTRACTS_20261108_v0.13.md')
V14 = os.path.join(ROOT, 'docs', 'architecture', 'FACTOR_ENGINE_CONTRACTS_20261108_v0.14.md')

ok = True


def check(name, cond, detail=''):
    global ok
    ok = ok and bool(cond)
    print(('PASS  ' if cond else 'FAIL  ') + name + ('  [' + detail + ']' if detail else ''))


b13 = open(V13, 'rb').read()
b14 = open(V14, 'rb').read()
t13 = b13.decode('utf-8')
t14 = b14.decode('utf-8')

# ---------- A 四元组与自洽 ----------
print('== A 四元组 / footer 自洽 ==')
i14 = b14.rfind('本文件正文 sha256'.encode())
body14 = b14[:i14]
footer14 = b14[i14:].decode('utf-8')
h14 = hashlib.sha256(body14).hexdigest()
check('A1 v0.14 全 CRLF', b14.count(CRLF.encode()) == b14.count(LF.encode()),
      'crlf=' + str(b14.count(CRLF.encode())) + ' lf=' + str(b14.count(LF.encode())))
check('A2 正文 = 全文去掉最后一行 footer', body14.endswith(('---' + CRLF + CRLF).encode()),
      '正文 ' + str(len(body14)) + ' B')
check('A3 footer 自述 sha == 复算', h14 in footer14, h14)
m = re.search('head -c ([0-9]+) "', footer14)
check('A4 footer 自述字节 == 复算', bool(m) and int(m.group(1)) == len(body14),
      'footer 写 ' + (m.group(1) if m else '?') + ' / 复算 ' + str(len(body14)))
m2 = re.search('全文 `([0-9]+)` 行', footer14)
check('A5 footer 自述行数 == 复算', bool(m2) and int(m2.group(1)) == b14.count(LF.encode()),
      'footer 写 ' + (m2.group(1) if m2 else '?') + ' / 复算 ' + str(b14.count(LF.encode())))
print('   四元组: ' + str(len(b14)) + ' B / ' + str(b14.count(LF.encode())) + ' 行 / 正文 '
      + str(len(body14)) + ' B 前缀 sha256 ' + h14[:16] + ' / 全文 sha256 '
      + hashlib.sha256(b14).hexdigest()[:16])

# ---------- B §7.1 块 ----------
print('== B §7.1 八行公式（台账 v5.11 [4] 绑定锚）==')


def blk(t):
    i = t.index('### 7.1')
    j = t.index('### 7.2', i)
    return t[i:j]


k13, k14 = blk(t13), blk(t14)
check('B1 §7.1 块 v0.13 == v0.14 逐字节相等', k13 == k14, str(len(k13)) + ' chars')
check('B2 CRLF 口径 == 2,541 / a8e88134f60b504c',
      len(k14) == 2541 and hashlib.sha256(k14.encode()).hexdigest()[:16] == 'a8e88134f60b504c',
      str(len(k14)) + ' / ' + hashlib.sha256(k14.encode()).hexdigest()[:16])
lf14 = k14.replace(CRLF, LF)
check('B3 LF 口径 == 2,514 / 6d3db0139a45f54c',
      len(lf14) == 2514 and hashlib.sha256(lf14.encode()).hexdigest()[:16] == '6d3db0139a45f54c',
      str(len(lf14)) + ' / ' + hashlib.sha256(lf14.encode()).hexdigest()[:16])

# ---------- E F-A1..F-A42 ----------
print('== E F-A1–F-A42 判据行 ==')
pat = re.compile(r'^\|\s*\**`?(F-A([0-9]+)(-[0-9]+)?)`?\**\s*\|')


def rows_of(t):
    d = {}
    for l in t.split(CRLF):
        mm = pat.match(l)
        if mm:
            d[mm.group(1)] = l
    return d


r13, r14 = rows_of(t13), rows_of(t14)
old = dict((k, v) for k, v in r13.items() if int(re.match('F-A([0-9]+)', k).group(1)) <= 42)
diff = [k for k, v in old.items() if r14.get(k) != v]
check('E1 F-A1–F-A42 判据行逐行相等', len(diff) == 0,
      str(len(old)) + ' 行 / 不等 ' + str(len(diff)) + ' ' + str(diff))
new_ids = sorted(set(r14) - set(r13))
check('E2 未新增判据号', len(new_ids) == 0, str(new_ids))
lost = sorted(set(r13) - set(r14))
check('E3 未丢失判据号', len(lost) == 0, str(lost))

# ---------- R14-1 F-A45-2 可机械判 ----------
print('== R14-1 F-A45-2 判定强度 ==')
row_f452 = [l for l in t14.split(CRLF) if l.startswith('| `F-A45-2`')]
check('R1-1 F-A45-2 判据行唯一', len(row_f452) == 1, str(len(row_f452)) + ' 行')
j = row_f452[0]
for token in ('删除的断言行 == 0', '条数', 'skip', 'xfail', '>=', '逐条列出'):
    check('R1-2 含可机械判要素「' + token + '」', token in j)
check('R1-3 F-A45-2 行内不再以「一个字不改」作判据',
      '一个字不改' not in j or '取代' in j)
row_sec = [l for l in t14.split(CRLF) if l.startswith('- **位置参数顺序')]
check('R1-4 §7.17.2 签名条已注明测试文件不是零改动对象',
      len(row_sec) == 1 and '测试文件不是「零改动」对象' in row_sec[0])

# ---------- R14-2 FS04 载体唯一读法 ----------
print('== R14-2 FS04 载体（裁定 (a)）==')
i_sec13_14 = t14.index('## 13. 本版改动说明')
norm = t14[:i_sec13_14]
check('R2-1 §7.8.4 载体段存在', '**`FS04` 的载体（v0.14 裁定 (a)：全文唯一读法）**' in norm)
check('R2-2 §7.16.4 载体条存在', '**`dual_ids` 只在 `GateError.detail` 上（v0.14 裁定 (a)）**' in norm)
check('R2-3 §7.16.6 表已改「不标 dual_id」',
      '允许；**不标 `dual_id`**（`GateReport` 无槽位' in norm)
check('R2-4 §7.8.4 矩阵已改「不产生 dual_id 标记」',
      '允许；**不产生 `dual_id` 标记**' in norm)
# 规范性文本里不得再出现 dual_id=true / 「标双 id」式允许
bad = [l for l in norm.split(CRLF) if ('dual_id=true' in l or '标 `dual_id=true`' in l)]
check('R2-5 规范性文本 0 处 dual_id=true', len(bad) == 0, str(len(bad)))
# GateReport 不得出现第七字段的添加式句子
check('R2-6 明文否决 (b)（不加第七字段）', '本版否决 (b)' in norm)
# §7.8.4 与 §7.16 两处同步判据：同一句「无槽位」两处都在
check('R2-7 §7.8.4 与 §7.16 对「无槽位」表述一致',
      norm.count('`GateReport` 六字段') >= 2 and '不加字段' in norm)

# ---------- R14-3 F-A47-1/3 标接线后生效 ----------
print('== R14-3 F-A47-1 / F-A47-3 生效时点 ==')
lf_lines = t14.split(CRLF)
r1 = [l for l in lf_lines if l.startswith('| `F-A47-1`')]
r3 = [l for l in lf_lines if l.startswith('| `F-A47-3`')]
check('R3-1 F-A47-1 唯一且标「接线后生效」',
      len(r1) == 1 and '接线后生效' in r1[0], str(len(r1)) + ' 行')
check('R3-2 F-A47-3 唯一且标「接线后生效」',
      len(r3) == 1 and '接线后生效' in r3[0], str(len(r3)) + ' 行')
check('R3-3 §7.17.8 新增节存在', '#### 7.17.8' in t14)
r1a = [l for l in lf_lines if l.startswith('| `F-A47-1a`')]
r3a = [l for l in lf_lines if l.startswith('| `F-A47-3a`')]
check('R3-4 F-A47-1a / F-A47-3a 各唯一', len(r1a) == 1 and len(r3a) == 1,
      str(len(r1a)) + '/' + str(len(r3a)))
check('R3-5 不重复计分规则已写', '不得**把母条记为「部分不可验」' in t14.replace('**不得**', '不得**'))
check('R3-6 接线前事实锚（调用方 0 / except GateError 0）已写',
      '调用方 0' in t14 and '`except GateError` 0' in t14)

# ---------- C 闸门层实测（F-A47-1a / F-A47-3a 的替代判据） ----------
print('== C 闸门层实测（backend/.venv）==')
PY = os.path.join(ROOT, 'backend', '.venv', 'Scripts', 'python.exe')
runner = (
    "import sys, json; sys.path.insert(0,'backend');\n"
    "from app.factors import gate\n"
    "class F:\n"
    "    def __init__(s, **k): s.__dict__.update(k)\n"
    "class Facts:\n"
    "    def __init__(s): pass\n"
    "    def facts(s, fid):\n"
    "        if fid=='vol60': return F(factor_id='vol60', registered=True, kind='custom', status='active', alias_of='uf_vol60', lang='dsl', strategy_usable=False)\n"
    "        if fid=='uf_vol60': return F(factor_id='uf_vol60', registered=True, kind='custom', status='active', alias_of=None, lang='dsl', strategy_usable=True)\n"
    "        return None\n"
    "out={}\n"
    "for mode in ('production','research','diagnostic'):\n"
    "    try:\n"
    "        r=gate.assert_factors_usable(['vol60','uf_vol60'], mode, facts=Facts())\n"
    "        out[mode]={'raised':None,'report':list(r.__dict__.keys()) if hasattr(r,'__dict__') else str(type(r))}\n"
    "    except Exception as e:\n"
    "        out[mode]={'raised':type(e).__name__,'code':getattr(e,'code',None),'detail_keys':list(e.detail.keys()) if getattr(e,'detail',None) else None,'dual_ids':(e.detail or {}).get('dual_ids'),'table_row':(e.detail or {}).get('table_row')}\n"
    "print(json.dumps(out, ensure_ascii=False))\n"
)
r = subprocess.run([PY, '-c', runner], capture_output=True, cwd=ROOT)
try:
    got = json.loads(r.stdout.decode('utf-8').strip().splitlines()[-1])
except Exception:
    got = None
    print('   stderr:', r.stderr.decode('utf-8', 'replace')[:500])
print('   ' + json.dumps(got, ensure_ascii=False))
if got:
    for mode in ('production', 'research'):
        g = got.get(mode, {})
        check('C1 ' + mode + ' → GateError FS04', g.get('raised') == 'GateError' and g.get('code') == 'FS04',
              str(g.get('raised')) + '/' + str(g.get('code')))
        check('C2 ' + mode + ' detail 8 键且第 8 键为 dual_ids',
              g.get('detail_keys') is not None and len(g.get('detail_keys')) == 8
              and g['detail_keys'][-1] == 'dual_ids', str(g.get('detail_keys')))
        check('C3 ' + mode + ' dual_ids == ["vol60","uf_vol60"]',
              g.get('dual_ids') == ['vol60', 'uf_vol60'], str(g.get('dual_ids')))
        check('C4 ' + mode + ' table_row is None', g.get('table_row') is None, str(g.get('table_row')))
    gd = got.get('diagnostic', {})
    check('C5 diagnostic 不抛 GateError（无 dual_id 标记）', gd.get('raised') is None, str(gd.get('raised')))

# F-A47-3a: 不洗错
runner3 = (
    "import sys, json; sys.path.insert(0,'backend');\n"
    "from app.factors import gate\n"
    "class Boom:\n"
    "    def facts(s, fid): raise RuntimeError('boom')\n"
    "try:\n"
    "    gate.assert_factors_usable(['x'], 'production', facts=Boom())\n"
    "    print(json.dumps({'raised':None}))\n"
    "except Exception as e:\n"
    "    print(json.dumps({'raised':type(e).__name__}))\n"
)
r3 = subprocess.run([PY, '-c', runner3], capture_output=True, cwd=ROOT)
try:
    g3 = json.loads(r3.stdout.decode('utf-8').strip().splitlines()[-1])
except Exception:
    g3 = None
    print('   stderr3:', r3.stderr.decode('utf-8', 'replace')[:300])
print('   F-A47-3a inject:', json.dumps(g3, ensure_ascii=False))
check('C6 注入 RuntimeError 原样逃出（不被洗成 GateError）',
      bool(g3) and g3.get('raised') == 'RuntimeError', str(g3 and g3.get('raised')))

src = open(os.path.join(ROOT, 'backend', 'app', 'factors', 'gate.py'), encoding='utf-8').read()
check('C7 gate.py 无 except Exception/BaseException（不洗错）',
      len(re.findall(r'except\s+(Exception|BaseException)', src)) == 0,
      str(len(re.findall(r'except\s+(Exception|BaseException)', src))))
n_ni = src.count('raise NotImplementedError')
print('   gate.py `raise NotImplementedError` 计数 =', n_ni)
check('C8 F-A47-2 口径：gate.py `raise NotImplementedError` 计数（契约正文已不写时点盘面数）',
      True, '实测 ' + str(n_ni) + ' —— 漂移提示，见本轮回复')

# 接线前事实锚
appdir = os.path.join(ROOT, 'backend', 'app')
calls = 0
for root, _dirs, files in os.walk(appdir):
    for fn in files:
        if not fn.endswith('.py'):
            continue
        p = os.path.join(root, fn)
        txt = open(p, encoding='utf-8', errors='replace').read()
        for ln, line in enumerate(txt.split(LF), 1):
            if 'assert_factors_usable' in line and not line.strip().startswith('#'):
                rel = os.path.relpath(p, ROOT)
                if rel.replace('\\', '/') == 'backend/app/factors/gate.py':
                    continue
                calls += 1
                print('   调用候选:', rel + ':' + str(ln), line.strip()[:80])
check('C9 backend/app/** 下 assert_factors_usable 调用方 == 0', calls == 0, str(calls))

exc_gate = 0
for root, _dirs, files in os.walk(appdir):
    for fn in files:
        if not fn.endswith('.py'):
            continue
        txt = open(os.path.join(root, fn), encoding='utf-8', errors='replace').read()
        exc_gate += len(re.findall(r'except\s+GateError', txt))
check('C10 backend/app/** 下 except GateError == 0', exc_gate == 0, str(exc_gate))

print()
print('SUMMARY', 'ALL PASS' if ok else 'HAS FAIL')
print('v0.14:', len(b14), 'B /', b14.count(LF.encode()), '行 / 正文', len(body14),
      'B / 正文 sha256', h14)
print('全文 sha256:', hashlib.sha256(b14).hexdigest())
sys.exit(0 if ok else 1)
