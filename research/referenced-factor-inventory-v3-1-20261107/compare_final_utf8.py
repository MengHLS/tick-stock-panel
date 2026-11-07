import json, sys, collections
sys.stdout.reconfigure(encoding='utf-8')
A=json.load(open('docs/architecture/evidence/referenced_factor_inventory.json',encoding='utf-8'))
E=json.load(open('docs/factors/evidence/referenced_factor_inventory_expected_20261107.json',encoding='utf-8'))
CONTRACT=['source_kind','source_path','source_id','source_sha256','source_enabled','path_scope','ref_raw','ref_name','ref_namespace','resolved_id','class','verifiable','gate_mode','verdict','code','evidence','both_collision','path_divergence','side','side_key','record_kind','path_base']
KEY=lambda r:(r.get('source_path'),r.get('evidence'),r.get('side'),r.get('ref_raw'),r.get('record_kind'))
G=lambda r,f: r.get(f)   # missing and null both -> None
exp_recs=list(E['records'])+list(E.get('companion_records',[]))
exp_map={KEY(r):r for r in exp_recs}
exp_paths=set(r.get('source_path') for r in exp_recs)
art_live=[r for r in A['records'] if r.get('source_path') in exp_paths]
art_map={KEY(r):r for r in art_live}
print('== 多重集（键 = source_path+evidence+side+ref_raw+record_kind）')
print('  artifact live', len(art_live), '/ expected', len(exp_recs))
print('  artifact_only', len(set(art_map)-set(exp_map)), ' expected_only', len(set(exp_map)-set(art_map)))
print()
print('== 契约 §7.10.2 表内 22 字段（%d 对配对）' % len(set(exp_map)&set(art_map)))
incontract=collections.Counter(); outside=collections.Counter(); ex={}; exo={}
for k in set(exp_map)&set(art_map):
    er, ar = exp_map[k], art_map[k]
    for f in CONTRACT:
        if G(ar,f)!=G(er,f):
            incontract[f]+=1; ex.setdefault(f,(k,G(er,f),G(ar,f)))
    for f in set(er)|set(ar):
        if f in CONTRACT: continue
        if G(ar,f)!=G(er,f):
            outside[f]+=1; exo.setdefault(f,(k,G(er,f),G(ar,f)))
print('  表内差异字段:', dict(incontract) or 'NONE（0）')
print('  其中 side_key 差异:', incontract.get('side_key',0), '/', len(set(exp_map)&set(art_map)))
for f,(k,ev,av) in ex.items(): print('   ---',f,k,'expected=',ev,'artifact=',av)
print()
print('== 表外字段差异')
print('  表外差异字段:', dict(outside) or 'NONE')
for f,(k,ev,av) in exo.items():
    print('   ---',f,'共',outside[f],'条，例 key=',k)
    print('      expected:',str(ev)[:120])
    print('      artifact:',str(av)[:120])
print()
sk=collections.Counter(r.get('side_key') for r in art_live)
print('== side_key（93 条活配置）')
print('  null:', sk.get(None,0), '  distinct:', len(sk))
for v,c in sorted(sk.items(), key=lambda x:(-x[1],str(x[0]))): print('  %3d  %s'%(c,v))
eks=collections.Counter(r.get('side_key') for r in exp_recs)
print('  与期望表 side_key 逐条相等:', all(G(art_map[k],'side_key')==G(exp_map[k],'side_key') for k in exp_map))
