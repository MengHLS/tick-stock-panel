# -*- coding: utf-8 -*-
"""v0.13 举证脚本（只读；不改任何文件）。用法：python research/arch-build-20261107/verify_v013.py

A. v0.13 全 CRLF；footer 固定点自洽（正文前缀 sha256 / 字节数 == footer 自述）。
B. §7.1 八行块：v0.13 与 v0.12 逐字节相等，两组常量 == 台账 v5.11 [4] 登记值。
C. F-A47-4 期望键集 == gate.py _detail("FS09", …) 实产键集（逐键、按序）；FS04 / FS01 变体各 8 键。
D. 规范性文本（§13 之前）「6 键 / 六键」= 0 命中；§13 内命中全部是引述。
E. F-A1–F-A42 判据行逐行相等；未新增判据号。
F. v0.12 本体未被改动（正文 sha256 仍 d97f657b…，269,092 B）。
"""
import hashlib
import json
import re
import subprocess
import sys

V12 = 'docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.12.md'
V13 = 'docs/architecture/FACTOR_ENGINE_CONTRACTS_20261108_v0.13.md'
CR = chr(13)
LF = chr(10)
CRLF = CR + LF

ok = True


def check(name, cond, detail=''):
    global ok
    ok = ok and bool(cond)
    print(('PASS ' if cond else 'FAIL ') + name + (' — ' + detail if detail else ''))


b12 = open(V12, 'rb').read()
b13 = open(V13, 'rb').read()
t12 = b12.decode('utf-8')
t13 = b13.decode('utf-8')

# ---------- F ----------
i12 = b12.rfind('本文件正文 sha256'.encode())
h12 = hashlib.sha256(b12[:i12]).hexdigest()
check('F v0.12 未被改动', h12.startswith('d97f657b61b85376') and len(b12) == 269092,
      str(len(b12)) + ' B / ' + h12[:16])

# ---------- A ----------
check('A1 v0.13 全 CRLF', b13.count(CRLF.encode()) == b13.count(LF.encode()),
      'crlf=' + str(b13.count(CRLF.encode())) + ' lf=' + str(b13.count(LF.encode())))
i13 = b13.rfind('本文件正文 sha256'.encode())
body13 = b13[:i13]
footer13 = b13[i13:].decode('utf-8')
h13 = hashlib.sha256(body13).hexdigest()
check('A2 正文 = 全文去掉最后一行 footer', body13.endswith(('---' + CRLF + CRLF).encode()),
      '正文 ' + str(len(body13)) + ' B')
check('A3 footer 自述 sha == 复算', h13 in footer13, h13)
m = re.search('head -c ([0-9]+) "', footer13)
check('A4 footer 自述字节 == 复算', bool(m) and int(m.group(1)) == len(body13),
      'footer 写 ' + (m.group(1) if m else '?') + ' / 复算 ' + str(len(body13)))
m2 = re.search('全文 `([0-9]+)` 行', footer13)
check('A5 footer 自述行数 == 复算',
      bool(m2) and int(m2.group(1)) == b13.count(LF.encode()),
      'footer 写 ' + (m2.group(1) if m2 else '?') + ' / 复算 ' + str(b13.count(LF.encode())))

# ---------- B ----------
def blk(t):
    i = t.index('### 7.1')
    j = t.index('### 7.2', i)
    return t[i:j]

k12, k13 = blk(t12), blk(t13)
check('B1 §7.1 块 v0.12 == v0.13 逐字节相等', k12 == k13, str(len(k12)) + ' chars')
check('B2 CRLF 口径 == 2,541 / a8e88134f60b504c',
      len(k13) == 2541 and hashlib.sha256(k13.encode()).hexdigest()[:16] == 'a8e88134f60b504c',
      str(len(k13)) + ' / ' + hashlib.sha256(k13.encode()).hexdigest()[:16])
lf = k13.replace(CRLF, LF)
check('B3 LF 口径 == 2,514 / 6d3db0139a45f54c',
      len(lf) == 2514 and hashlib.sha256(lf.encode()).hexdigest()[:16] == '6d3db0139a45f54c',
      str(len(lf)) + ' / ' + hashlib.sha256(lf.encode()).hexdigest()[:16])

# ---------- C ----------
rows = [l for l in t13.split(CRLF) if l.startswith('| `F-A47-4`')]
check('C0 F-A47-4 判据行唯一', len(rows) == 1, str(len(rows)) + ' 行')
row = rows[0]
seg = row.split('逐键等于 §7.16.4 的固定 7 键**（', 1)[1].split('，不多不少', 1)[0]
expect = re.findall('`([a-z_]+)`', seg)
print('   F-A47-4 期望键集 :', expect)

PY = 'backend/.venv/Scripts/python.exe'
code = ("import sys, json; sys.path.insert(0,'backend'); from app.factors import gate;"
        "print(json.dumps(list(gate._detail('FS09','production','namespace',None,None,None,'x').keys()), ensure_ascii=False))")
r = subprocess.run([PY, '-c', code], capture_output=True)
actual = json.loads(r.stdout.decode('utf-8').strip())
print('   gate._detail FS09:', actual)
check('C1 期望键集 == 实产键集（逐键）', expect == actual, str(len(expect)) + ' vs ' + str(len(actual)))
check('C2 键数 == 7', len(actual) == 7, str(len(actual)))

code2 = ("import sys, json; sys.path.insert(0,'backend'); from app.factors import gate;"
         "d=gate._detail('FS04','production','vol60','uf_vol60',None,None,'x'); d['dual_ids']=['vol60','uf_vol60'];"
         "e=gate._detail('FS01','production','ma20',None,None,'draft','x');"
         "print(json.dumps([list(d.keys()), list(e.keys())]))")
r2 = subprocess.run([PY, '-c', code2], capture_output=True)
fs04, fs01 = json.loads(r2.stdout.decode('utf-8').strip())
check('C3 FS04 = 7 键 + dual_ids（8）', fs04 == expect + ['dual_ids'], str(fs04))
check('C4 FS01 = 7 键 + status（8）', fs01 == expect + ['status'], str(fs01))
print('   gate.py 锚点行（_detail dict 字面量）:')
src = open('backend/app/factors/gate.py', encoding='utf-8').read().split(LF)
for n in range(531, 540):
    print('    ' + str(n + 1) + ': ' + src[n].strip()[:70])

# ---------- D ----------
i_sec13 = t13.index('## 13. 本版改动说明')
hits = [(m.start(), m.group()) for m in re.finditer('6\\s*键|六键', t13)]
outside = [h for h in hits if h[0] < i_sec13]
check('D1 §13 之前（规范性文本）0 命中', len(outside) == 0, str(len(outside)) + ' 处')
lines_with = []
for pos, _g in hits:
    ls = t13.rfind(LF, 0, pos) + 1
    le = t13.find(CRLF, pos)
    lines_with.append(t13[ls:le])
allq = True
for l in lines_with:
    isq = (l.startswith('| R13-') or '引述' in l or '「形状按' in l or '六键」' in l)
    allq = allq and isq
    print('    ' + ('[引述] ' if isq else '[!!非引述] ') + l[:100])
check('D2 §13 内命中全部是引述', allq, str(len(lines_with)) + ' 处')

# ---------- E ----------
pat = re.compile('^\\|\\s*\\**`?(F-A([0-9]+)(-[0-9]+)?)`?\\**\\s*\\|')


def rows_of(t):
    d = {}
    for l in t.split(CRLF):
        m = pat.match(l)
        if m:
            d[m.group(1)] = l
    return d


r12, r13 = rows_of(t12), rows_of(t13)
old = dict((k, v) for k, v in r12.items() if int(re.match('F-A([0-9]+)', k).group(1)) <= 42)
diff = [k for k, v in old.items() if r13.get(k) != v]
check('E1 F-A1–F-A42 判据行逐行相等', len(diff) == 0, str(len(old)) + ' 行 / 不等 ' + str(len(diff)) + ' ' + str(diff))
new_ids = sorted(set(r13) - set(r12))
check('E2 未新增判据号', len(new_ids) == 0, str(new_ids))

print()
print('SUMMARY', 'ALL PASS' if ok else 'HAS FAIL')
print('v0.13:', len(b13), 'B /', b13.count(LF.encode()), '行 / 正文', len(body13), 'B / 正文 sha256', h13)
print('全文 sha256:', hashlib.sha256(b13).hexdigest())
sys.exit(0 if ok else 1)
