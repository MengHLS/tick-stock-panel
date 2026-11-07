"""F-A11b 读法裁定：v0.7:1501 原文 '逐列 rel = max|p−m| / max(|p|, 1e-12)' 究竟一义吗？
两种可辩护读法在同一正确核上给相反判决 → 判据不可机械判定。"""
from __future__ import annotations
import json, sys
from datetime import date
from pathlib import Path
PROJECT = Path(r"C:\work\sourcecode\tick-stock-panel")
sys.path.insert(0, str(PROJECT / "backend"))
import numpy as np, polars as pl
OUT = {}
BASE = ["symbol","date","open","high","low","close","volume","amount"]
EPS23, EPS24 = 2.0**-23, 2.0**-24
from app.backtest.matrix import build_market_data_matrix, matrix_feature
from app.config import settings
from app.extensions.adapters import FileMarketData
from app.strategy.scoring import materialize_scoring_columns

ids = ["ma20","boll_lower","boll_upper"]
sym = ["600000.SH","000001.SZ","600519.SH","000002.SZ","600036.SH","000651.SZ","600276.SH","002415.SZ"]
f = FileMarketData(settings.data_dir).get_daily_batch(sym, date(2023,1,3), date(2026,6,30), BASE).sort(["symbol","date"])
market = build_market_data_matrix(f)
panel = materialize_scoring_columns(f.select(BASE), ids)
syms = list(market.symbols); dates=[str(x)[:10] for x in market.timestamp_labels]

res={}
for fid in ids:
    piv = panel.select(["date","symbol",fid]).pivot(on="symbol",index="date",values=fid)
    piv = piv.with_columns(pl.col("date").cast(pl.Utf8).str.slice(0,10))
    daymap={d:i for i,d in enumerate(piv["date"].to_list())}
    cols={c:piv[c].to_list() for c in piv.columns if c!="date"}
    mat=np.asarray(matrix_feature(market,fid),dtype=np.float64)
    P=[];M=[]
    for i,dl in enumerate(dates):
        if dl not in daymap: continue
        r=daymap[dl]
        for j,s in enumerate(syms):
            if s not in cols: continue
            pv=cols[s][r]; mv=mat[i,j] if i<mat.shape[0] and j<mat.shape[1] else np.nan
            if pv is None or not np.isfinite(pv) or not np.isfinite(mv): continue
            P.append(pv);M.append(mv)
    P=np.asarray(P);M=np.asarray(M); d=np.abs(P-M); aP=np.abs(P)
    # 读法1（逐元素 rel，v0.7 括号里的 1e-12 只有这样才有意义）
    rel_elem = d/np.maximum(aP,1e-12); k=int(np.argmax(rel_elem))
    r1=float(rel_elem.max()); ok1=r1<=EPS23
    # 读法2（列级：分子列最大绝对差 / 列最大 |p|）
    colmax=float(aP.max()); r2=float(d.max()/max(colmax,1e-12)); ok2=r2<=EPS23
    # 越线点是否落在近零值（判断 rel_elem 是否退化）
    res[fid]=dict(n=int(P.size),read1_elem=dict(max_rel=r1,pass_=bool(ok1)),
        read2_col=dict(max_rel=r2,pass_=bool(ok2)),
        verdict_differs=(ok1!=ok2),
        worst_elem=dict(p=float(P[k]),m=float(M[k]),absdiff=float(d[k]),rel=float(rel_elem[k]),
            p_abs=float(aP[k]), is_near_zero=bool(aP[k]<1.0)))
    print(f"{fid:11s} r1_elem={r1:.4e} ({'PASS' if ok1 else 'FAIL'})  r2_col={r2:.4e} ({'PASS' if ok2 else 'FAIL'})  differs={ok1!=ok2}")
    print(f"            worst elem: |p|={aP[k]:.6g} absdiff={d[k]:.3e} near_zero={aP[k]<1.0}")
OUT["fa11b_readings"]=res
OUT["note"]="v0.7:1501 同一句含两个断言；读法1(逐元素,1e-12 才有意义)与读法2(列级)在正确核上判决相反"
Path(__file__).with_suffix(".json").write_text(json.dumps(OUT,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
print("[done]")
