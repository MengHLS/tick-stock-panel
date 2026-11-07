# -*- coding: utf-8 -*-
"""§10.3 banner 三行切片哈希（可复跑口径，2026-11-08）。

口径（写死，R12 §5.7 引用此脚本）：
  1) 起点 = 文件中 '### 10.3' 标题行之后的第一个非空行；
  2) 从该行起，取连续的、以 '> ' 开头的行，直到第一行不以 '>' 开头为止（本口径下恰 3 行）；
  3) CRLF 保留口径 = 这 3 行原文（含各自行尾 CRLF）拼成的字节串；
     LF 归一 口径 = 同一串把 CRLF 换成 LF；
  4) 两种口径各取 sha256，报前 16 位。
用法：python research/arch-build-20261107/slice_hashes_20261108.py [文件…]
"""
import hashlib
import sys

CR = chr(13)
LF = chr(10)
CRLF = CR + LF

DEFAULT = [
    'docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.11.md',
    'docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.12.md',
]


def banner_block(path):
    t = open(path, 'rb').read().decode('utf-8')
    i = t.index('### 10.3')
    seg = t[i:].split(CRLF)
    k = 1
    while k < len(seg) and seg[k].strip() == '':
        k += 1
    out = []
    while k < len(seg) and seg[k].startswith('>'):
        out.append(seg[k])
        k += 1
    raw = CRLF.join(out) + CRLF
    return out, raw


for p in (sys.argv[1:] or DEFAULT):
    lines, raw = banner_block(p)
    lf = raw.replace(CRLF, LF)
    print(p.split('/')[-1] if '/' in p else p)
    print('  行数        :', len(lines))
    print('  CRLF 口径   :', len(raw), 'chars /', hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16])
    print('  LF 归一口径 :', len(lf), 'chars /', hashlib.sha256(lf.encode('utf-8')).hexdigest()[:16])
