# -*- coding: utf-8 -*-
"""重建日频持仓市值面板：股数(daily_positions) x 通达信日线收盘价 -> 单票市值/权重。"""
import csv, os, struct, bisect

BASE = r"C:\work\sourcecode\tick-stock-panel\research\jiaogedan-review-20261107"
DATA = os.path.join(BASE, "data")
OUT = os.path.join(BASE, "risk")
TDX = r"D:\tdx\vipdoc"
os.makedirs(OUT, exist_ok=True)


def price_scale(code):
    """通达信 .day 收盘价整数缩放：股票 x100，ETF/LOF x1000，可转债 x10000。"""
    if code.startswith(('110', '111', '113', '118', '123', '127', '128')):
        return 10000.0
    if code.startswith(('15', '16', '50', '51', '56', '58')):
        return 1000.0
    return 100.0


def load_day(path, scale=100.0):
    out = []
    try:
        raw = open(path, "rb").read()
    except OSError:
        return out
    n = len(raw) // 32
    for i in range(n):
        d, o, h, l, c, amt, vol, _ = struct.unpack("IIIIIfII", raw[i * 32:(i + 1) * 32])
        out.append((d, c / scale))
    return out


def mkt_dir(code):
    if code[0] == '6' or code.startswith(('5', '11', '9', '72', '71')):
        return 'sh'
    if code.startswith(('4', '8')):
        return 'bj'
    return 'sz'


def day_path(code):
    mk = mkt_dir(code)
    p = os.path.join(TDX, mk, 'lday', f'{mk}{code}.day')
    if os.path.exists(p):
        return p
    other = 'sz' if mk != 'sz' else 'sh'
    p2 = os.path.join(TDX, other, 'lday', f'{other}{code}.day')
    return p2 if os.path.exists(p2) else p


with open(os.path.join(DATA, 'daily_positions.csv'), encoding='utf-8-sig') as f:
    rd = csv.reader(f)
    header = next(rd)
    rows = [r for r in rd]
codes = header[1:]

price, missing = {}, []
for code in codes:
    s = load_day(day_path(code), price_scale(code))
    if not s:
        missing.append(code)
    else:
        price[code] = s

name_map = {}
for path in [os.path.join(DATA, 'trades_clean.csv'), os.path.join(DATA, 'roundtrips.csv')]:
    with open(path, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            c = str(r.get('code') or '').zfill(6)
            if c and r.get('name'):
                name_map.setdefault(c, r['name'])

tdxhy = {}
hy_path = r"D:\tdx\T0002\hq_cache\tdxhy.cfg"
if os.path.exists(hy_path):
    for line in open(hy_path, 'rb').read().decode('gbk', 'ignore').splitlines():
        parts = line.split('|')
        if len(parts) >= 3 and parts[1]:
            tdxhy[parts[1].strip()] = (parts[2].strip(), parts[5].strip() if len(parts) > 5 else '')

hy_name, sw_name, cur_sec = {}, {}, None
inc = r"D:\tdx\incon.dat"
if os.path.exists(inc):
    for line in open(inc, 'rb').read().decode('gbk', 'ignore').splitlines():
        if line.startswith('######'):
            cur_sec = None
            continue
        if line.startswith('#'):
            cur_sec = line.strip('#').strip()
            continue
        if '|' not in line:
            continue
        k, v = line.split('|', 1)
        if cur_sec == 'TDXNHY':
            hy_name[k] = v
        elif cur_sec == 'SWHY':
            sw_name[k] = v

def kind_str(c):
    if c.startswith(("110", "111", "113", "118", "123", "127", "128")):
        return '转债'
    return 'other'


out_rows, diag = [], []
for r in rows:
    date = r[0]
    di = int(date.replace('-', ''))
    tot, per = 0.0, []
    for code, val in zip(codes, r[1:]):
        try:
            sh = float(val) if val not in ('', 'nan') else 0.0
        except ValueError:
            sh = 0.0
        if sh <= 0:
            continue
        s = price.get(code)
        if not s:
            per.append((code, sh, None, None, 0.0))
            continue
        lo, hi = 0, len(s)
        while lo < hi:
            mid = (lo + hi) // 2
            if s[mid][0] <= di:
                lo = mid + 1
            else:
                hi = mid
        lo -= 1
        if lo < 0:
            per.append((code, sh, None, None, 0.0))
            continue
        pdate, px = s[lo]
        if pdate < int(date.replace('-', '')) - 7:
            src = 'stale'
        else:
            src = 'close'
        mv = sh * px
        tot += mv
        per.append((code, sh, px, pdate, mv))
    for i, (code, sh, px, pdate, mv) in enumerate(per):
        if px is None and kind_str(code) == '转债':
            # 新债上市前无行情，按面值 100 元/张入账
            px, pdate, mv = 100.0, int(date.replace('-', '')) + 100000, sh * 100.0
            tot += mv
            per[i] = (code, sh, px, pdate, mv)
    diag.append((date, round(tot, 2)))
    for code, sh, px, pdate, mv in per:
        out_rows.append({
            'date': date, 'code': code, 'name': name_map.get(code, ''),
            'shares': sh, 'price': px if px is not None else '',
            'price_date': pdate if pdate else '',
            'price_source': ('par' if pdate and pdate > 30000000 else
                             ('stale' if pdate and int(date.replace('-', '')) - pdate > 7 else 'close')),
            'mv': round(mv, 2),
            'weight_in_mv': round(mv / tot, 6) if tot > 0 else '',
            'hy': hy_name.get(tdxhy.get(code, ('', ''))[0], ''),
            'hy_code': tdxhy.get(code, ('', ''))[0],
            'sw': sw_name.get(tdxhy.get(code, ('', ''))[1], ''),
        })

with open(os.path.join(OUT, 'positions_mv.csv'), 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
    w.writeheader()
    w.writerows(out_rows)

with open(os.path.join(OUT, 'mv_check.csv'), 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.writer(f)
    w.writerow(['date', 'mv_from_positions_x_close'])
    w.writerows(diag)

print('rows', len(out_rows), 'missing', missing)
