#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
R8 digest 口径变更（recipe 1 -> recipe 2）独立判定脚本。
自写：只读产物 JSON，不 import 被审方任何模块、不调用 build_referenced_factor_inventory.py。
输出：research/independent-review-20261107/artifacts/r8_digest_recipe_audit.json
退出码：0 = 全部断言成立；1 = 有断言不成立（逐条写在 results 里）。
"""
import json, hashlib, copy, os, sys, io, random, subprocess

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
ART = os.path.join(ROOT, 'docs', 'architecture', 'evidence', 'referenced_factor_inventory.json')
SIDE = ART + '.sha256'
OUT = os.path.join(ROOT, 'research', 'independent-review-20261107', 'artifacts',
                   'r8_digest_recipe_audit.json')

R = []          # 断言结果
def add(name, ok, detail):
    R.append({'name': name, 'ok': bool(ok), 'detail': detail})

def rk(x):
    return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(',', ':'))

# ---------- recipe 1：§7.12.4 原文（剔 4 键黑名单） ----------
DROP1 = {'generated_at', 'repo_head', 'data_root', 'canonical_digest'}
def digest_recipe1(d):
    q = {k: v for k, v in d.items() if k not in DROP1}
    q['records'] = sorted(q.get('records', []), key=rk)
    blob = json.dumps(q, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(blob.encode('utf-8')).hexdigest()

# ---------- recipe 2：§10.3 载荷白名单 ----------
KEEP2 = ('schema_version', 'scanned_sources', 'records')
def digest_recipe2(d):
    payload = {k: d[k] for k in KEEP2 if k in d}
    payload['records'] = sorted(payload.get('records', []), key=rk)
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(blob.encode('utf-8')).hexdigest()

def sha256_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()

def main():
    raw = open(ART, 'rb').read()
    d = json.loads(raw.decode('utf-8'))
    st = os.stat(ART)

    top = sorted(d.keys())
    recs = d.get('records', [])
    notes = d.get('notes')
    ondisk = d.get('canonical_digest')
    ondish_recipe = d.get('canonical_digest_recipe', '<ABSENT>')

    r1 = digest_recipe1(d)
    r2 = digest_recipe2(d)

    # --- 0 产物与环境事实 ---
    add('A0_artifact_sha256', True, {
        'path': ART, 'bytes': len(raw), 'mtime': st.st_mtime_ns,
        'full_sha256': sha256_file(ART), 'sidecar': open(SIDE).read().strip(),
        'sidecar_matches_file': sha256_file(ART) in open(SIDE).read(),
        'top_keys': top, 'n_records': len(recs),
        'schema_version': d.get('schema_version'),
        'scanned_sources': d.get('scanned_sources'),
        'generated_at': d.get('generated_at'),
        'repo_head': d.get('repo_head'), 'data_root': d.get('data_root'),
        'notes_type': type(notes).__name__,
        'notes_len': (len(notes) if isinstance(notes, (list, str)) else None),
        'notes_bytes': len(json.dumps(notes, ensure_ascii=False).encode('utf-8')),
        'canonical_digest_ondisk': ondisk,
        'canonical_digest_recipe_ondisk': ondish_recipe,
    })

    # --- 1 recipe 1 是否复现落盘值 ---
    add('A1_recipe1_reproduces_ondisk', r1 == ondisk,
        {'computed': r1, 'ondisk': ondisk, 'equal': r1 == ondisk})

    # --- 2 recipe 2 自算（非权威参照） ---
    add('A2_recipe2_computed', True, {'computed': r2, 'differs_from_recipe1': r2 != r1})

    # --- 3 载荷边界：哪些顶层键进了各 recipe 的载荷 ---
    q1 = {k for k in d if k not in DROP1}
    q2 = {k for k in d if k in KEEP2}
    add('A3_payload_sets', True, {
        'recipe1_payload_keys': sorted(q1),
        'recipe1_n_keys': len(q1),
        'recipe2_payload_keys': sorted(q2),
        'recipe2_n_keys': len(q2),
        'outside_recipe2': sorted(set(d) - q2),
        'outside_recipe1': sorted(set(d) - q1),
    })

    # --- 4 扰动矩阵（逐项比 r1/r2 是否变） ---
    def perturb(fn, label):
        e = copy.deepcopy(d)
        fn(e)
        return {'case': label, 'r1': digest_recipe1(e), 'r2': digest_recipe2(e),
                'r1_changed': digest_recipe1(e) != r1, 'r2_changed': digest_recipe2(e) != r2}

    def _notes_tail_space(e):
        n = e.get('notes')
        if isinstance(n, list):
            e['notes'] = [str(x) + ' ' for x in n]
        elif isinstance(n, str):
            e['notes'] = n + ' '
        else:
            raise RuntimeError('notes type')

    def _notes_word(e):
        # 必须用必然改变字节的扰动：产物 note[0] 里不含某些汉字，replace 会静默失配（本脚本初版踩过一次）
        n = e.get('notes')
        if isinstance(n, list) and n:
            e['notes'] = [str(n[0]) + 'X'] + list(n[1:])
        elif isinstance(n, str):
            e['notes'] = n + 'X'
        else:
            raise RuntimeError('notes empty')

    def _notes_drop_all(e):
        e['notes'] = []

    def _summary_num(e):
        e.setdefault('summary', {}).setdefault('live_config', {})['records'] = 999

    def _summary_drop(e):
        e.pop('summary', None)

    def _stale(e):
        e['stale_count'] = int(e.get('stale_count', 0)) + 1

    def _gen_at(e):
        e['generated_at'] = '1999-01-01T00:00:00+08:00'

    def _repo_head(e):
        e['repo_head'] = 'deadbeef' * 5

    def _data_root(e):
        e['data_root'] = 'X:/other'

    def _rev(e):
        e['records'] = list(reversed(e['records']))

    def _shuffle(e):
        rnd = random.Random(7)
        r = list(e['records']); rnd.shuffle(r); e['records'] = r

    def _verdict(e):
        for r in e['records']:
            if r.get('verdict') == 'allow':
                r['verdict'] = 'block'; break
        else:
            e['records'][0]['verdict'] = 'block'

    def _add_top(e):
        e['a_new_top_level_field'] = {'x': 1}

    def _version_str(e):
        e['generator_version'] = 'vX.Y.Z-injected'

    def _schema(e):
        # 产物落盘值为 "2"，扰动必须朝另一个取值，否则是空操作（本脚本初版此处写错过一次）
        assert d.get('schema_version') == '2'
        e['schema_version'] = '1'

    def _scanned(e):
        e['scanned_sources'] = int(e['scanned_sources']) + 1

    perturb_cases = [
        (_notes_tail_space, 'notes_each_tail_space'),
        (_notes_word, 'notes_first_char_append_X'),
        (_notes_drop_all, 'notes_emptied'),
        (_summary_num, 'summary.live_config.records_93_to_999'),
        (_summary_drop, 'summary_removed'),
        (_stale, 'stale_count_plus1'),
        (_gen_at, 'generated_at_changed'),
        (_repo_head, 'repo_head_changed'),
        (_data_root, 'data_root_changed'),
        (_rev, 'records_reversed'),
        (_shuffle, 'records_shuffle_seed7'),
        (_verdict, 'one_verdict_allow_to_block'),
        (_add_top, 'new_top_level_key_added'),
        (_version_str, 'generator_version_string'),
        (_schema, 'schema_version_1_to_2'),
        (_scanned, 'scanned_sources_plus1'),
    ]
    matrix = []
    for fn, label in perturb_cases:
        try:
            matrix.append(perturb(fn, label))
        except Exception as ex:
            matrix.append({'case': label, 'error': repr(ex)})
    add('A4_perturbation_matrix', True, matrix)

    # --- 5 契约自述的扰动值 vs 我实测（报告值 vs 实测比对） ---
    claims = {
        'notes_each_tail_space': {'r1': 'ba414786', 'r2': None, 'r1_changed': True, 'r2_changed': False},
        'summary.live_config.records_93_to_999': {'r1': '6c33d2db', 'r1_changed': True, 'r2_changed': False},
        'records_shuffle_seed7': {'r1': None, 'r1_changed': False, 'r2_changed': False},
        'one_verdict_allow_to_block': {'r1': '3b4e85e7', 'r2': '6e6d6cde', 'r1_changed': True, 'r2_changed': True},
    }
    claim_check = []
    for case, c in claims.items():
        row = next((x for x in matrix if x.get('case') == case), None)
        if row is None or 'error' in row:
            claim_check.append({'case': case, 'status': 'MISSING'}); continue
        item = {'case': case,
                'r1_prefix_measured': row['r1'][:8], 'r1_prefix_claimed': c.get('r1'),
                'r2_prefix_measured': row['r2'][:8], 'r2_prefix_claimed': c.get('r2'),
                'r1_changed_measured': row['r1_changed'], 'r1_changed_claimed': c.get('r1_changed'),
                'r2_changed_measured': row['r2_changed'], 'r2_changed_claimed': c.get('r2_changed')}
        bad = []
        if c.get('r1') and row['r1'][:8] != c['r1']: bad.append('r1_value')
        if c.get('r2') and row['r2'][:8] != c['r2']: bad.append('r2_value')
        if c.get('r1_changed') is not None and row['r1_changed'] != c['r1_changed']: bad.append('r1_changed')
        if c.get('r2_changed') is not None and row['r2_changed'] != c['r2_changed']: bad.append('r2_changed')
        item['mismatch'] = bad
        claim_check.append(item)
    add('A5_contract_claim_vs_measured', all(not x.get('mismatch') for x in claim_check), claim_check)

    # --- 6 白名单的"自动收纳新字段"性质：新增顶层键是否落在载荷外 ---
    newkey_row = next(x for x in matrix if x['case'] == 'new_top_level_key_added')
    add('A6_whitelist_auto_excludes_new_keys',
        (not newkey_row['r2_changed']) and newkey_row['r1_changed'],
        {'new_top_level_key_changes_recipe1': newkey_row['r1_changed'],
         'new_top_level_key_changes_recipe2': newkey_row['r2_changed'],
         'note': 'recipe1（黑名单）会把任何新增顶层键纳入签认；recipe2 不会'})

    # --- 7 recipe 2 的载荷是否仍能区分 schema_version / scanned_sources ---
    s1 = next(x for x in matrix if x['case'] == 'schema_version_1_to_2')
    s2 = next(x for x in matrix if x['case'] == 'scanned_sources_plus1')
    add('A7_payload_discriminates_schema_and_sources',
        s1['r2_changed'] and s2['r2_changed'],
        {'schema_version_change_r2': s1['r2_changed'],
         'scanned_sources_change_r2': s2['r2_changed']})

    # --- 8 notes 语义损失面：recipe2 下 notes 全空与原文同 digest ---
    nd = next(x for x in matrix if x['case'] == 'notes_emptied')
    add('A8_notes_fully_outside_signature',
        (not nd['r2_changed']) and nd['r1_changed'],
        {'notes_emptied_r1_changed': nd['r1_changed'],
         'notes_emptied_r2_changed': nd['r2_changed'],
         'notes_char_len_total': (sum(len(str(x)) for x in notes) if isinstance(notes, list) else len(str(notes))),
         'notes_share_of_payload_bytes': None})

    # --- 9 summary/stale_count 一致性在 recipe2 下不再被 digest 兜底 ---
    sm = next(x for x in matrix if x['case'] == 'summary.live_config.records_93_to_999')
    dr = next(x for x in matrix if x['case'] == 'summary_removed')
    stc = next(x for x in matrix if x['case'] == 'stale_count_plus1')
    add('A9_derived_fields_outside_signature',
        (not sm['r2_changed']) and (not dr['r2_changed']) and (not stc['r2_changed']),
        {'summary_tamper_r2_changed': sm['r2_changed'],
         'summary_removed_r2_changed': dr['r2_changed'],
         'stale_count_r2_changed': stc['r2_changed'],
         'summary_removed_still_digest_ok_recipe1': dr['r1_changed']})

    # --- 10 三份历史 digest 的可复验性：盘上是否有原文件 ---
    hist = {'184e4728': '17:27 产物', '9d34fef7': '17:10 产物', 'aefdf528': '19:23:55 产物'}
    found = {k: [] for k in hist}
    scan_roots = [os.path.join(ROOT, 'docs'), os.path.join(ROOT, 'research'),
                  os.path.join(ROOT, 'backend')]
    n_json = 0
    for sr in scan_roots:
        for dp, dns, fns in os.walk(sr):
            dns[:] = [x for x in dns if x not in ('node_modules', '.git', '__pycache__')]
            for f in fns:
                if not f.endswith('.json'):
                    continue
                fp = os.path.join(dp, f)
                try:
                    if os.path.getsize(fp) > 40_000_000:
                        continue
                    b = open(fp, 'rb').read()
                except OSError:
                    continue
                n_json += 1
                if b'"canonical_digest"' not in b:
                    continue
                try:
                    o = json.loads(b.decode('utf-8'))
                except Exception:
                    continue
                if not isinstance(o, dict):
                    continue
                cd = str(o.get('canonical_digest', ''))
                for k in hist:
                    if cd.startswith(k):
                        found[k].append({'path': os.path.relpath(fp, ROOT),
                                         'bytes': len(b),
                                         'generated_at': o.get('generated_at'),
                                         'digest': cd,
                                         'recipe_field': o.get('canonical_digest_recipe', '<ABSENT>'),
                                         'n_records': len(o.get('records', [])),
                                         'recompute_r1': digest_recipe1(o),
                                         'recompute_r1_matches': digest_recipe1(o) == cd})
    add('A10_historical_digests_on_disk', True,
        {'scanned_json_files': n_json, 'claims': hist, 'found': found})

    # --- 11 生成侧是否已实现 recipe 2 ---
    bld = os.path.join(ROOT, 'backend', 'scripts', 'build_referenced_factor_inventory.py')
    bsrc = open(bld, encoding='utf-8').read()
    gen_facts = {
        'builder_path': os.path.relpath(bld, ROOT),
        'builder_bytes': len(bsrc.encode('utf-8')),
        'mentions_canonical_digest_recipe': 'canonical_digest_recipe' in bsrc,
        'canonical_drop_literal': 'CANONICAL_DROP = ("generated_at", "repo_head", "data_root", "canonical_digest")' in bsrc,
        'n_payload_keep_tuples': bsrc.count('KEEP'),
        'writes_notes_into_payload': '"notes": NOTES' in bsrc,
    }
    add('A11_generator_implements_recipe2', gen_facts['mentions_canonical_digest_recipe'], gen_facts)

    # --- 12 消费侧：仓内是否有任何代码在读 canonical_digest_recipe ---
    cons = []
    for sr in [os.path.join(ROOT, 'backend'), os.path.join(ROOT, 'frontend')]:
        if not os.path.isdir(sr):
            continue
        for dp, dns, fns in os.walk(sr):
            dns[:] = [x for x in dns if x not in ('node_modules', '.git', '__pycache__', 'dist')]
            for f in fns:
                if not f.endswith(('.py', '.ts', '.tsx', '.js')):
                    continue
                fp = os.path.join(dp, f)
                try:
                    t = open(fp, encoding='utf-8', errors='replace').read()
                except OSError:
                    continue
                if 'canonical_digest' in t:
                    cons.append({'path': os.path.relpath(fp, ROOT),
                                 'n_canonical_digest': t.count('canonical_digest'),
                                 'has_recipe': 'canonical_digest_recipe' in t})
    add('A12_consumers_reading_recipe', any(c['has_recipe'] for c in cons),
        {'files_touching_canonical_digest': cons})

    # --- 13 契约可执行性：§7.12.4 / §10.3 复算片段能否逐字运行 ---
    contract = os.path.join(ROOT, 'docs', 'architecture',
                            'FACTOR_ENGINE_CONTRACTS_20261107_v0.9.md')
    ctext = open(contract, encoding='utf-8').read()
    i1 = ctext.find('rk(x) = json.dumps')
    i2 = ctext.find('载荷 = `{schema_version, scanned_sources, records[]}`')
    add('A13_contract_snippet_present', i1 > 0 and ('sort_keys=True' in ctext),
        {'found_rk_def': i1 > 0,
         'has_sort_keys_kw': 'sort_keys=True' in ctext,
         'n_recipe_word': ctext.count('recipe'),
         'has_recipe_field_name': 'canonical_digest_recipe' in ctext})

    # --- 14 契约是否写了 recipe 2 的"落盘字段必填"与缺省读法 ---
    add('A14_default_read_rule', '缺省按 `"1"` 读' in ctext or '缺省按 "1" 读' in ctext,
        {'default_is_1': ('缺省按 `"1"` 读' in ctext or '缺省按 "1" 读' in ctext),
         'l2_requires_2': ('L2 起产物必须 `"2"`' in ctext or 'L2 起产物必须 "2"' in ctext)})

    # --- 15b 选择子自身是否进载荷（两 recipe 的分歧） ---
    label_rows = []
    for lab in ('1', '2', '3', ''):
        e = copy.deepcopy(d)
        e['canonical_digest_recipe'] = lab
        label_rows.append({'label': lab, 'r1': digest_recipe1(e), 'r2': digest_recipe2(e),
                           'r1_changed': digest_recipe1(e) != r1,
                           'r2_changed': digest_recipe2(e) != r2})
    add('A15b_selector_inside_recipe1_outside_recipe2',
        all(x['r1_changed'] for x in label_rows) and not any(x['r2_changed'] for x in label_rows),
        label_rows)

    # --- 15c F-A36 度量文本 vs §10.3 强制 recipe 2：是否互斥 ---
    fa36 = [l for l in ctext.splitlines() if l.startswith('| F-A36')]
    fa36 = fa36[0] if fa36 else ''
    add('A15c_F_A36_text_still_mandates_7_12_4',
        ('按 §7.12.4 代码复算' in fa36) and ('recipe' not in fa36),
        {'F_A36_row': fa36[:300],
         'mandates_7_12_4': '按 §7.12.4 代码复算' in fa36,
         'mentions_recipe': 'recipe' in fa36,
         's10_3_mandates_recipe2_for_new': '本版起新产物必须用它' in ctext})

    # --- 15d §7.12.4 原文是否真的未动（v0.6-v0.9 逐字节） ---
    def sect(p, start, end):
        t = open(p, encoding='utf-8').read()
        i = t.find(start)
        if i < 0:
            return None
        j = t.find(end, i)
        return t[i:j if j > 0 else len(t)]
    secs = {}
    for tag in ('_v0.6', '_v0.7', '_v0.8', '_v0.9'):
        p = os.path.join(ROOT, 'docs', 'architecture',
                         f'FACTOR_ENGINE_CONTRACTS_20261107{tag}.md')
        if not os.path.exists(p):
            continue
        b = sect(p, '#### 7.12.4', '#### 7.12.5')
        if b is None:
            secs[tag] = '<ABSENT>'
            continue
        secs[tag] = {'chars': len(b),
                     'lf_sha16': hashlib.sha256(b.replace('\r\n', '\n').encode()).hexdigest()[:16],
                     'raw_sha16': hashlib.sha256(b.encode()).hexdigest()[:16]}
    vals = [v for v in secs.values() if v != '<ABSENT>']
    add('A15d_7_12_4_body_unchanged_v06_v09',
        len({v['raw_sha16'] for v in vals}) == 1 and len(vals) >= 3, secs)

    # --- 15 跨 recipe 规则原文（用于定性漏判通道） ---
    j = ctext.find('不同报「**不可比**」')
    add('A15_cross_recipe_rule_text', j > 0,
        {'snippet': ctext[max(0, j - 160):j + 120] if j > 0 else None})

    # ---------- 汇总 ----------
    summary = {
        'n_assertions': len(R),
        'n_fail': sum(1 for x in R if not x['ok']),
        'failed': [x['name'] for x in R if not x['ok']],
        'digest_recipe1_measured': r1,
        'digest_recipe2_measured': r2,
        'digest_ondisk': ondisk,
        'recipe1_matches_ondisk': r1 == ondisk,
        'artifact_bytes': len(raw),
        'artifact_full_sha256': sha256_file(ART),
        'n_records': len(recs),
    }
    out = {'summary': summary, 'results': R}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with io.open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary['n_fail'] == 0 else 1

if __name__ == '__main__':
    sys.exit(main())
