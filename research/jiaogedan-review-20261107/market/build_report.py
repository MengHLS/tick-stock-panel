# -*- coding: utf-8 -*-
import pandas as pd, numpy as np, os
B = r"C:\work\sourcecode\tick-stock-panel\research\jiaogedan-review-20261107"
M = os.path.join(B,"market")
out=[]
def p(s=""): out.append(str(s))
F={"买入笔数":"{:.0f}","买入金额万元":"{:,.1f}","均笔金额":"{:,.0f}","回合数":"{:.0f}","胜率":"{:.1f}%",
   "合计盈亏":"{:,.0f}","平均单笔盈亏":"{:.0f}","平均收益率":"{:+.2f}%","次数占比%":"{:.1f}%","金额占比%":"{:.1f}%",
   "交易日数":"{:.0f}","交易日占比%":"{:.1f}%","回合占比%":"{:.1f}%","平均持有交易日":"{:.2f}"}
def md(df,fmt=None,title=None):
    d=df.copy()
    if title: p("**"+title+"**"); p()
    cols=list(d.columns)
    p("| "+" | ".join(map(str,cols))+" |"); p("|"+"|".join(["---"]*len(cols))+"|")
    for _,r in d.iterrows():
        cells=[]
        for c in cols:
            v=r[c]
            if isinstance(v,(float,np.floating)):
                if pd.isna(v): cells.append("—")
                else: cells.append(fmt[c].format(v) if fmt and c in fmt else f"{v:,.2f}")
            else: cells.append(str(v))
        p("| "+" | ".join(cells)+" |")
    p()
feat=pd.read_csv(os.path.join(M,"feat.csv")); buys=pd.read_csv(os.path.join(M,"buys.csv")); daily=pd.read_csv(os.path.join(M,"daily.csv"))
eq=pd.read_csv(os.path.join(B,"risk","equity_corrected.csv"))
for d in (feat,buys,daily,eq):
    for c in d.columns:
        if c in ("buy_date","sell_date","date"): d[c]=pd.to_datetime(d[c])
daily=daily.sort_values("date").reset_index(drop=True); eq=eq.sort_values("date").reset_index(drop=True)
daily["breadth"]=daily.up_count/(daily.up_count+daily.down_count)
sgn=np.sign(daily.psh.fillna(0)); st=[];cur=0
for s in sgn:
    cur=(cur+1 if cur>0 else 1) if s>0 else ((cur-1 if cur<0 else -1) if s<0 else 0); st.append(cur)
daily["streak"]=st
smap=dict(zip(daily.date,daily.streak))
for d in (feat,buys): d["streak"]=d.buy_date.map(smap)
for d in (feat,buys,daily): d["breadth"]=d.up_count/(d.up_count+d.down_count)
W0,W1=pd.Timestamp("2025-03-21"),pd.Timestamp("2026-11-06")
dm=daily[(daily.date>=W0)&(daily.date<=W1)].copy()
lab3=["前5","6-10","11-30","不在名单"]
def bucket(x,cuts,labels):
    if pd.isna(x): return labels[-1]
    for c,l in zip(cuts,labels):
        if x<=c: return l
    return labels[-1]
stk=feat[feat.pkind=="股票"].copy()
stk["gn_b"]=stk.gn_rank.apply(lambda x:bucket(x,[5,10,30],lab3)); stk["ind_b"]=stk.ind_rank.apply(lambda x:bucket(x,[5,10,30],lab3))
T={}
def prof(key,label,order=None,bins=None,labels=None):
    K=key+"_b" if bins is not None else key
    if bins is not None:
        for d in (feat,buys,dm): d[K]=pd.cut(d[key],bins=bins,labels=labels)
    g=buys.groupby(K,dropna=False).agg(买入笔数=("amt","size"),买入金额万元=("amt",lambda s:s.sum()/1e4),均笔金额=("amt","mean")).reset_index()
    a=feat.groupby(K,dropna=False).agg(回合数=("pnl","size"),胜率=("pnl",lambda s:(s>0).mean()*100),合计盈亏=("pnl","sum"),平均单笔盈亏=("pnl","mean"),平均收益率=("ret_pct","mean")).reset_index()
    g=g.merge(a,on=K,how="outer")
    g["次数占比%"]=g.买入笔数/g.买入笔数.sum()*100; g["金额占比%"]=g.买入金额万元/g.买入金额万元.sum()*100
    ds=dm.groupby(K).size().rename("交易日数").reset_index(); g=g.merge(ds,on=K,how="left")
    g["交易日占比%"]=g.交易日数/g.交易日数.sum()*100
    if order is not None:
        for o in order:
            if o not in set(g[K].astype(str)): g=pd.concat([g,pd.DataFrame([{K:o}])],ignore_index=True)
        g[K]=g[K].astype(object); g["_o"]=g[K].astype(str).map({v:i for i,v in enumerate(map(str,order))}); g=g.sort_values("_o").drop(columns="_o")
    g=g.rename(columns={K:label})
    return g
p("# 交割单复盘 · 市场环境部分（市场状态画像 / 主线匹配 / 基准与风格 / 反事实）")
p()
p(f"窗口 {W0.date()} ~ {W1.date()}，交易日 {len(dm)} 天。买入事件 {len(buys)} 笔（side=B：证券买入 377 + 配售缴款 6），买入金额合计 {buys.amt.sum():,.0f} 元；盈亏与胜率用 FIFO 回合 {len(feat)} 个，按开仓日归到当日市场状态（一个回合可含多笔买入，故笔数≠回合数）。")
p("数据源：regime_history（phase/涨跌停/宽度/成交额）、mainline_history（板块排名）、kline_index_daily（指数日线）、ext_gn_ths 与 ext_hy_ths_pit（个股概念/行业截面）、roundtrip_tags_attribution（回合盈亏）、risk/equity_corrected.csv（日盈亏修正序列）。")
p()
p("## 核心结论（每条给出可被推翻的条件）")
p("1. **他并不是在情绪最高潮时加大买入**：涨停家数三分位下每交易日买入笔数 0.95~0.98 笔、笔均金额 1.8~2.0 万，基本无差别；但高潮日的钱明显更差——高位日 140 个回合合计 −49,806 元、胜率 37.1%，低位日 159 个回合 −7,683 元、胜率 46.5%。（推翻条件：按金额加权或剔除最差 5 个回合后，高、低位差距消失）")
p("2. **失血集中在「涨停 80~119 家」的中高热度区**：77 个回合 −57,382 元、胜率 36.4%、笔均 −745 元，是全部亏损里最大的一块（占 −75,825 的 76%）。（推翻条件：该档亏损由 1~2 个极端回合贡献超过一半）")
p("3. **买在概念主线前 5 反而最差**：110 个回合 −35,071 元、胜率 35.5%、笔均 −319 元；表现最好的是「在名单内但排 11~30」的 −84 元/回合。他抓的是最热板块里的跟风尾部，不是龙头——只有 5 个回合买在当日榜单的板块龙头，5 战全胜 +4,892 元。（推翻条件：概念归属换成当期时点数据后，前 5 档盈亏显著转正）")
p("4. **这段行情不难，是他的方法在亏**：上证 +9.66%、等权全A代理 +13.28%、日均涨停 64 家、日均成交 2.1 万亿；若只买指数、同样的钱约 +1,100~+5,500 元，实际 −75,825 元，日收益均值 −0.53%/日，与指数相关性仅 0.30~0.34、beta 0.93~1.61（放大波动却拿不到方向）。（推翻条件：若换用含分红的全收益指数，指数收益显著不同）")
p()
p("## 0. 这段行情本身（事实）")
lu=dm.limit_up; br=dm.breadth; am=dm.above_ma20_pct
p(f"- 涨停家数：均值 {lu.mean():.1f} / 中位 {lu.median():.0f} / 区间 {lu.min():.0f}~{lu.max():.0f}")
p(f"- 上涨家数占比（重算 up/(up+down)；regime 自带 up_ratio 有 18.29、640 等异常值，不用）：均值 {br.mean():.3f} / 中位 {br.median():.3f} / 区间 {br.min():.2f}~{br.max():.2f}")
p(f"- 站上 MA20 比例：均值 {am.mean():.3f} / 中位 {am.median():.3f} / 区间 {am.min():.2f}~{am.max():.2f}")
p(f"- 日均成交额 {dm.total_amount.mean()/1e12:.2f} 万亿元（{dm.total_amount.min()/1e12:.2f}~{dm.total_amount.max()/1e12:.2f}）")
ph=dm.groupby("phase").agg(交易日=("date","size"),涨停均值=("limit_up","mean"),宽度均值=("breadth","mean"),MA20均值=("above_ma20_pct","mean"),上证日均pct=("psh","mean"),成交万亿=("total_amount","mean")).reset_index()
ph["成交万亿"]=ph.成交万亿/1e12; T["t0_phase"]=ph
md(ph,{"交易日":"{:.0f}","涨停均值":"{:.1f}","宽度均值":"{:.3f}","MA20均值":"{:.3f}","上证日均pct":"{:+.4f}","成交万亿":"{:.2f}"},"表0.1 regime 阶段（窗口内天数）")
p("## 1. 买入日的市场状态画像")
p()
t=prof("phase","regime阶段")
t=t.sort_values("买入笔数",ascending=False); t["regime阶段"]=t["regime阶段"].astype(object).fillna("缺数据(2026-11-06)")
T["t1_1_phase"]=t; md(t,F,"表1.1 按 regime phase（含窗口内交易日占比对照）")
t=prof("limit_up","涨停家数",bins=[-1,40,80,120,1000],labels=["<40","40~79","80~119",">=120"]); T["t1_2_limitup"]=t; md(t,F,"表1.2 按买入日涨停家数")
t=prof("breadth","上涨家数占比",bins=[-0.01,0.40,0.55,0.70,1.01],labels=["<0.40","0.40~0.55","0.55~0.70",">=0.70"]); T["t1_3_breadth"]=t; md(t,F,"表1.3 按买入日市场宽度")
t=prof("index_pct","当日指数涨跌",bins=[-1,-0.01,-0.0001,0.0001,0.01,1],labels=["<-1%","-1%~0","≈0","0~1%",">1%"]); T["t1_4_indexpct"]=t; md(t,F,"表1.4 按买入日 regime.index_pct")
order=["连涨>=3天","连涨2天","连涨1天","平","跌1天","跌2天","连跌>=3天"]
def sm(x): return "连涨>=3天" if x>=3 else "连涨2天" if x==2 else "连涨1天" if x==1 else "平" if x==0 else "跌1天" if x==-1 else "跌2天" if x==-2 else "连跌>=3天"
for d in (feat,buys,dm): d["stg"]=d.streak.apply(sm)
t=prof("stg","上证连涨/连跌",order=order); T["t1_5_streak"]=t; md(t,F,"表1.5 按买入日上证连续涨跌天数")
t=prof("above_ma20_pct","站上MA20比例",bins=[-0.01,0.30,0.50,0.70,1.01],labels=["<0.30","0.30~0.50","0.50~0.70",">=0.70"]); T["t1_6_ma20"]=t; md(t,F,"表1.6 按买入日站上 MA20 比例")
q1,q2=dm.limit_up.quantile([1/3,2/3])
def terc(x): return "低位(<=%d)"%int(q1) if x<=q1 else ("中位" if x<=q2 else "高位(>%d)"%int(q2))
for d in (dm,buys,feat): d["lu_t"]=d.limit_up.apply(terc)
a=dm.groupby("lu_t").size().rename("交易日数"); b=buys.groupby("lu_t").size().rename("买入笔数"); c=buys.groupby("lu_t").amt.sum().rename("买入金额")
e=feat.groupby("lu_t").agg(回合数=("pnl","size"),胜率=("pnl",lambda s:(s>0).mean()*100),合计盈亏=("pnl","sum"),平均单笔盈亏=("pnl","mean"))
t=pd.concat([a,b,c,e],axis=1).reindex(["低位(<=%d)"%int(q1),"中位","高位(>%d)"%int(q2)]).reset_index().rename(columns={"lu_t":"涨停家数三分位"})
t["交易日占比%"]=t.交易日数/t.交易日数.sum()*100; t["买入笔数占比%"]=t.买入笔数/t.买入笔数.sum()*100; t["每交易日笔数"]=t.买入笔数/t.交易日数
T["t1_7_tercile"]=t
md(t,{"交易日数":"{:.0f}","买入笔数":"{:.0f}","买入金额":"{:,.0f}","回合数":"{:.0f}","胜率":"{:.1f}%","合计盈亏":"{:,.0f}","平均单笔盈亏":"{:.0f}","交易日占比%":"{:.1f}%","买入笔数占比%":"{:.1f}%","每交易日笔数":"{:.2f}"},"表1.7 情绪温度三分位：买入频率与结果")
p()
p("## 2. 主线匹配")
p("口径：mainline_history 每日给 concept 30 个排名板块、industry 最多 30 个；个股→概念用 ext_gn_ths 截面快照（非时点，概念归属会漂移，平均每只股票挂 ~13 个概念，故「进名单」门槛偏松）；个股→行业用 ext_hy_ths_pit（库内仅 2026-11-01~06 六日，按其最新行业回溯，行业归属变动少）。个股所属任一概念/行业出现在当日名单即算匹配，取最小 rank。仅股票回合（剔除 ETF）。")
p()
for key,label,ttl,fn in [("gn_b","概念主线档位","表2.1 概念主线（concept）","t2_1_concept"),("ind_b","行业主线档位","表2.2 行业主线（industry）","t2_2_industry")]:
    t=stk.groupby(key).agg(回合数=("pnl","size"),胜率=("pnl",lambda s:(s>0).mean()*100),合计盈亏=("pnl","sum"),平均单笔盈亏=("pnl","mean"),平均收益率=("ret_pct","mean"),平均持有交易日=("hold_td","mean")).reindex(lab3).reset_index().rename(columns={key:label})
    t["回合占比%"]=t.回合数/t.回合数.fillna(0).sum()*100; T[fn]=t; md(t,F,ttl)
for key,label,ttl,fn in [("gn_b","概念","表2.3 概念：主线内(前10) vs 名单外","t2_3_concept_grp"),("ind_b","行业","表2.4 行业：主线内(前10) vs 名单外","t2_4_industry_grp")]:
    stk["grp"]=np.where(stk[key].isin(["前5","6-10"]),"主线内(前10)",np.where(stk[key]=="11-30","名单内11-30","不在主线"))
    t=stk.groupby("grp").agg(回合数=("pnl","size"),胜率=("pnl",lambda s:(s>0).mean()*100),合计盈亏=("pnl","sum"),平均单笔盈亏=("pnl","mean"),平均收益率=("ret_pct","mean")).reindex(["主线内(前10)","名单内11-30","不在主线"]).reset_index().rename(columns={"grp":label+"主线分组"})
    t["回合占比%"]=t.回合数/t.回合数.fillna(0).sum()*100; T[fn]=t; md(t,F,ttl)
stk["ld"]=stk.leader_rank.apply(lambda x:"当日某板块龙头(rank<=10)" if pd.notna(x) and x<=10 else "非龙头")
t=stk.groupby("ld").agg(回合数=("pnl","size"),胜率=("pnl",lambda s:(s>0).mean()*100),合计盈亏=("pnl","sum"),平均单笔盈亏=("pnl","mean"),平均收益率=("ret_pct","mean")).reset_index().rename(columns={"ld":"是否当日板块龙头"})
T["t2_5_leader"]=t; md(t,F,"表2.5 是否买在当日主线板块的龙头股")
p("差距读数：概念口径下「在主线里(前10)」比「不在主线」每回合多亏 66 元（−250 vs −184），比「名单内 11~30」多亏 166 元（−250 vs −84）；行业口径下「在主线里(前10)」每回合 +94 元，比不在主线的 −202 元好 296 元/回合，但只有 28 个回合，样本薄。")
p()
p("## 3. 基准与风格")
p()
def idxret(col):
    s=dm[["date",col]].dropna()
    return (s.date.iloc[0],s.date.iloc[-1],s[col].iloc[-1]/s[col].iloc[0]-1) if len(s)>1 else None
ew=(1+dm.avg_pct.fillna(0)).cumprod()
rows=[]
for col,name,pcol in [("c300","沪深300 000300.SH","p300"),("c1000","中证1000 000852.SH","p1000"),("cgz2000","国证2000 399303.SZ","pgz2000"),("csh","上证综指 000001.SH","psh")]:
    r=idxret(col); rows.append({"基准":name,"起":str(r[0].date()),"止":str(r[1].date()),"区间涨跌幅%":r[2]*100,"日均涨跌幅%":dm[pcol].dropna().mean()*100})
rows.append({"基准":"等权全A代理（regime.avg_pct 日再平衡连乘）","起":str(dm.date.iloc[0].date()),"止":str(dm.date.iloc[-1].date()),"区间涨跌幅%":(ew.iloc[-1]-1)*100,"日均涨跌幅%":dm.avg_pct.mean()*100})
t3=pd.DataFrame(rows); T["t3_1_bench"]=t3
md(t3,{"区间涨跌幅%":"{:+.2f}%","日均涨跌幅%":"{:+.4f}"},"表3.1 同期基准（各自可得区间的首末收盘）")
p("注：000300/000852/399303 在本库止于 2026-10-28（末 7 个交易日缺），上证与等权到 2026-11-05，终点不完全一致；均为价格指数，不含分红。")
p()
eqw=eq[(eq.date>=W0)&(eq.date<=W1)].copy(); eqw["prev"]=eqw.equity_corr.shift(1); eqw["r"]=eqw.d_pnl/eqw.prev
eqw=eqw[(eqw.prev>0)&eqw.r.notna()]; eqw=eqw[eqw.r.abs()<0.5]
d3=eqw.merge(dm[["date","psh","p300","p1000","pgz2000","avg_pct","index_pct","breadth","npos"]],on="date",how="left")
p(f"策略日收益（修正口径 d_pnl / 前一日权益，剔除 |r|>50% 的入金跳变日）：样本 {len(d3)} 天，均值 {d3.r.mean()*100:+.3f}%/日，日波动 {d3.r.std()*100:.2f}%，累计 {eq.pnl_corr.iloc[-1]:,.2f} 元（核定口径 {eq.pnl_stated.iloc[-1]:,.2f} 元）。")
p(f"资金：累计入金 {eq.cumdep.max():,.0f} 元，历史最高权益 {eq.equity.max():,.0f} 元，有仓日平均持仓市值 {dm.loc[dm.npos>0,'mv'].mean():,.0f} 元；买入总额 {buys.amt.sum():,.0f} 元 ÷ 有仓日平均市值 ≈ {buys.amt.sum()/dm.loc[dm.npos>0,'mv'].mean():.0f} 倍周转。")
p()
rows=[]
for col,name in [("psh","上证综指"),("p300","沪深300"),("p1000","中证1000"),("pgz2000","国证2000"),("avg_pct","等权全A(avg_pct)"),("index_pct","regime.index_pct")]:
    x=d3[["r",col]].dropna()
    if len(x)<20: continue
    beta=np.cov(x.r,x[col])[0,1]/np.var(x[col],ddof=1)
    rows.append({"基准":name,"样本日":len(x),"相关系数":x.r.corr(x[col]),"beta":beta,"策略日均%":x.r.mean()*100,"基准日均%":x[col].mean()*100})
t32=pd.DataFrame(rows); T["t3_2_beta"]=t32
md(t32,{"样本日":"{:.0f}","相关系数":"{:.3f}","beta":"{:.3f}","策略日均%":"{:+.3f}","基准日均%":"{:+.3f}"},"表3.2 策略日收益 vs 各指数（相关与 beta）")
x=d3.dropna(subset=["p300","pgz2000"])
p(f"风格：同期国证2000 − 沪深300 日均超额 {(x.pgz2000-x.p300).mean()*100:+.3f}%，小盘略强；策略对小盘指数 beta {np.cov(x.r,x.pgz2000)[0,1]/np.var(x.pgz2000,ddof=1):.2f}、对沪深300 beta {np.cov(x.r,x.p300)[0,1]/np.var(x.p300,ddof=1):.2f}，与指数相关性只有 0.30 左右，说明盈亏主要不来自市场方向而是选股/时点，且这部分是负的。")
p()
p("## 4. 一句话结论：如果他只买指数")
mv=dm.loc[dm.npos>0,"mv"].mean(); rows=[]
for col,name in [("c300","沪深300"),("c1000","中证1000"),("cgz2000","国证2000"),("csh","上证综指")]:
    r=idxret(col); rows.append({"方案":f"全程持有{name}","区间收益%":r[2]*100,"折算盈亏(元)":r[2]*mv})
rows.append({"方案":"等权全A代理","区间收益%":(ew.iloc[-1]-1)*100,"折算盈亏(元)":(ew.iloc[-1]-1)*mv})
t41=pd.DataFrame(rows); T["t4_1_counterfactual"]=t41
md(t41,{"区间收益%":"{:+.2f}%","折算盈亏(元)":"{:,.0f}"},"表4.1 反事实：同样的钱只买指数")
p(f"假设：一次性投入「有仓日平均持仓市值」{mv:,.0f} 元、不择时、不复利、不计费用、不含分红；实际 −75,824.59 元。若按累计入金 {eq.cumdep.max():,.0f} 元作基数，同样指数的绝对收益约 {eq.cumdep.max()*0.0432:,.0f}~{eq.cumdep.max()*0.1328:,.0f} 元。")
p()
txt="\n".join(out)
open(os.path.join(M,"REPORT_market.md"),"w",encoding="utf-8").write(txt)
for k,v in T.items(): v.to_csv(os.path.join(M,"tab_"+k+".csv"),index=False,encoding="utf-8-sig")
print(txt)
