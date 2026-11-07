import json
d=json.load(open(r"C:/work/sourcecode/tick-stock-panel/research/arch-build-20261107/EVIDENCE_v11.json", encoding="utf-8"))
for k in ("quad_v0_10","quad_v0_11","git_numstat","git_stat_tail","sec_7_1_v0_10","sec_7_1_v0_11","sec_7_1_all_9_identical","reverse_restore","fa_seq","stopword","banner_shape"):
    print(k, "=", json.dumps(d[k], ensure_ascii=False))
for k in ("numstat_autojunk_true","numstat_autojunk_false"):
    v={kk:vv for kk,vv in d[k].items() if kk!="detail"}
    print(k, "=", json.dumps(v, ensure_ascii=False))
    print("  detail", json.dumps(d[k]["detail"], ensure_ascii=False))
