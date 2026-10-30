import json,hashlib,copy
from pathlib import Path
p=Path(__file__).parent;src=p/'event-replay-v01';dst=p/'event-replay-v011-schema';dst.mkdir(exist_ok=True)
oldhash={x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in src.iterdir() if x.is_file()}
f=src/'candidate-classifications.json';original=json.loads(f.read_text(encoding='utf-8'));updated=copy.deepcopy(original);changes=[];rows=set();nodes=0
reason={'no_first_decline':'NO_FIRST_DECLINE_BEFORE_D','no_post_anchor_high':'POST_ANCHOR_HIGH_REQUIREMENT_FAILED','no_setup':'NO_PREBREAK_SETUP_LOW'}
for i,r in enumerate(updated):
 c=r['classification'];pairs=[]
 if c['selected'] is not None:pairs.append(('selected',c['selected']))
 pairs.extend((f'trace[{j}]',v) for j,v in enumerate(c['trace']))
 for scope,v in pairs:
  absent=[k for k in ['depth','recovery_raw','recovery_applicable'] if k not in v]
  if not absent:continue
  nodes+=1;rows.add(i);why=reason.get(v['path_state'],'CALCULATION_UNAVAILABLE')
  v['null_reason_codes']={}
  for key in absent:
   v[key]=None;v['null_reason_codes'][key]=why
   changes.append({'row_index':i,'event_id':r['event_id'],'rule':r['rule'],'path':'classification.'+scope+'.'+key,'before':'KEY_ABSENT','after':None,'reason_code':why})
# Remove only additions and prove exact semantic identity to previous file.
restored=copy.deepcopy(updated)
for i,r in enumerate(restored):
 c=r['classification'];pairs=[]
 if c['selected'] is not None:pairs.append(('selected',c['selected']))
 pairs.extend((f'trace[{j}]',v) for j,v in enumerate(c['trace']))
 for scope,v in pairs:
  oldnode=original[i]['classification']['selected'] if scope=='selected' else original[i]['classification']['trace'][int(scope[6:-1])]
  if 'null_reason_codes' in v:
   for k in list(v['null_reason_codes']):assert k not in oldnode and v[k] is None;del v[k]
   del v['null_reason_codes']
assert restored==original
out=dst/'candidate-classifications.json';out.write_text(json.dumps(updated,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(dst/'schema-differences.json').write_text(json.dumps(changes,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
assert oldhash=={x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in src.iterdir() if x.is_file()}
manifest={'schema_version':'v0.1.1-schema','calculation_version':'replay-v01-discussion-20261028 unchanged','scope':'27 events / 432 event-rule rows; schema-only candidate sidecar','source':str(f),'source_sha256':oldhash[f.name],'output_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'affected_candidate_rows':len(rows),'affected_serialized_nodes':nodes,'added_null_fields':len(changes),'selected_null_fields':sum('.selected.' in x['path'] for x in changes),'trace_null_fields':sum('.trace[' in x['path'] for x in changes),'old_directory_sha256':oldhash,'verification':'Remove only added null fields and reason maps => deep equality with v01; all old directory hashes unchanged','audit_count_note':'Verifier reported 170 missing-field checks; this file reports actual JSON paths including duplicated selected/trace representations. Counting scopes differ and are not forced to match.','limitations':'No recomputation; prior independent rule-value review pertains to unchanged old values. Future-isolation, outcomes, followups, factor and identity audits not implied.'}
(dst/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:manifest[k] for k in ['affected_candidate_rows','affected_serialized_nodes','added_null_fields','selected_null_fields','trace_null_fields']},ensure_ascii=False))
print('PASS: schema-only additions reversed to exact v01 equality; every v01 file hash unchanged')
