#!/usr/bin/env node
/**
 * 只读导出：把 docs/research 下冻结的首板回放材料整理成前端可 fetch 的紧凑 JSON。
 *
 * - 分类源使用 v0.1.2 补键版本（schema-only；计算值与 v0.1 相同）。
 * - 只读取冻结材料，不写研究目录、不重算收益、不访问数据仓库。
 * - 输出 frontend/public/research/firstboard/replay-v012.json；
 *   旧 replay.json 保留为 v0.1 输出，不覆盖。
 * - 记录每个源文件的 SHA256，并校验 v0.1.2 manifest 的 source/output 指纹。
 *
 * 用法: node scripts/export-firstboard-replay.mjs
 */
import { createHash } from 'node:crypto'
import { existsSync, readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const repo = resolve(here, '..', '..')
const research = join(repo, 'docs', 'research', 'firstboard-classification-draft-20261027')
const v01 = join(research, 'event-replay-v01')
const v011 = join(research, 'event-replay-v011-schema')
const v012 = join(research, 'event-replay-v012-schema')
const outDir = join(here, '..', 'public', 'research', 'firstboard')
const outFile = join(outDir, 'replay-v012.json')
const legacyOutFile = join(outDir, 'replay.json')

const RULES = []
for (const p of ['A', 'B']) {
  for (const q of ['0.03', '0.05']) {
    for (const g of ['0', '1']) {
      for (const r of ['0', '1']) RULES.push(`P${p}_q${q}_G${g}_R${r}`)
    }
  }
}
const DEFAULT_RULE = 'PB_q0.05_G0_R0'

const sources = {
  paths: join(research, 'four-case-paths.csv'),
  manifest: join(research, 'four-case-manifest.json'),
  events: join(v01, 'historical-events.json'),
  classifications: join(v012, 'candidate-classifications.json'),
  classifications_v011: join(v011, 'candidate-classifications.json'),
  classifications_v01: join(v01, 'candidate-classifications.json'),
  classifications_manifest: join(v012, 'manifest.json'),
  classifications_v011_manifest: join(v011, 'manifest.json'),
  outcomes: join(v01, 'forward-outcomes.csv'),
  tracking: join(v01, 'forward-tracking.json'),
  factors: join(v01, 'factor-snapshots-long.csv'),
}

function sha256(path) {
  return createHash('sha256').update(readFileSync(path)).digest('hex')
}

/** 极简 CSV 解析（支持引号内逗号/换行/双引号转义） */
function parseCsv(text) {
  const rows = []
  let row = []
  let field = ''
  let quoted = false
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i]
    if (quoted) {
      if (ch === '"') {
        if (text[i + 1] === '"') { field += '"'; i += 1 } else quoted = false
      } else field += ch
      continue
    }
    if (ch === '"') quoted = true
    else if (ch === ',') { row.push(field); field = '' }
    else if (ch === '\n') { row.push(field); field = ''; rows.push(row); row = [] }
    else if (ch !== '\r') field += ch
  }
  if (field !== '' || row.length > 0) { row.push(field); rows.push(row) }
  const [header, ...body] = rows.filter(r => r.length > 1 || (r.length === 1 && r[0] !== ''))
  return body.map(r => Object.fromEntries(header.map((h, i) => [h, r[i] ?? ''])))
}

const num = value => {
  if (value === '' || value == null) return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

const manifest = JSON.parse(readFileSync(sources.manifest, 'utf8'))
const paths = parseCsv(readFileSync(sources.paths, 'utf8'))
const events = JSON.parse(readFileSync(sources.events, 'utf8'))
const v012Manifest = JSON.parse(readFileSync(sources.classifications_manifest, 'utf8'))
const v011Manifest = JSON.parse(readFileSync(sources.classifications_v011_manifest, 'utf8'))
const classifications = JSON.parse(readFileSync(sources.classifications, 'utf8'))
const outcomes = parseCsv(readFileSync(sources.outcomes, 'utf8'))
const tracking = JSON.parse(readFileSync(sources.tracking, 'utf8'))
const factorRows = parseCsv(readFileSync(sources.factors, 'utf8'))

// ── 版本指纹：v0.1 -> v0.1.1 -> v0.1.2 只补键，不重算 ─────────────────
const v012Hash = sha256(sources.classifications)
const v011Hash = sha256(sources.classifications_v011)
const v01Hash = sha256(sources.classifications_v01)
if (v012Manifest.schema_version !== 'v0.1.2') {
  throw new Error(`unexpected v0.1.2 schema version: ${v012Manifest.schema_version}`)
}
if (v012Manifest.calculation_version !== 'v0.1 unchanged') {
  throw new Error(`v0.1.2 calculation changed: ${v012Manifest.calculation_version}`)
}
if (v012Hash !== v012Manifest.output_sha256) {
  throw new Error('v0.1.2 output sha256 does not match manifest')
}
if (v011Hash !== v012Manifest.source_sha256) {
  throw new Error('v0.1.1 source sha256 does not match v0.1.2 manifest source_sha256')
}
if (v01Hash !== v011Manifest.old_directory_sha256['candidate-classifications.json']) {
  throw new Error('v0.1 source sha256 does not match v0.1.1 manifest old_directory_sha256')
}

// ── 因子字典：单位/公式/窗口（只取定义，不重复 756 行数值）────────────
const factorMeta = {}
for (const row of factorRows) {
  if (!factorMeta[row.factor]) {
    factorMeta[row.factor] = {
      unit: row.unit,
      formula: row.formula,
      window: num(row.window),
      role: row.classification_usage,
    }
  }
}

// ── 个股日K（前复权 OHLC + 原始收盘 + 平台首板标记）────────────────────
const bySymbol = new Map()
for (const row of paths) {
  if (!bySymbol.has(row.symbol)) bySymbol.set(row.symbol, [])
  bySymbol.get(row.symbol).push(row)
}
const orderedRows = code => (bySymbol.get(code) ?? []).slice().sort((a, b) => a.date.localeCompare(b.date))

const symbols = Object.entries(manifest.per_symbol).map(([code, meta]) => {
  const rows = orderedRows(code)
  const bars = rows.map(r => [
    r.date,
    num(r.open), num(r.high), num(r.low), num(r.close),
    num(r.raw_close),
    num(r.consecutive_limit_ups),
  ])
  return {
    code,
    name: meta.name_now,
    board: meta.board,
    listing_date: meta.listing_date,
    firstboard_identity: meta.firstboard_identity,
    first_boards: rows.filter(r => num(r.consecutive_limit_ups) === 1).map(r => r.date),
    bars,
  }
})

// ── 27 个冻结事件 + 16 规则分类 + 后续结果 ────────────────────────────
const ruleIndex = new Map()
for (const row of classifications) {
  const key = row.event_id
  if (!ruleIndex.has(key)) ruleIndex.set(key, {})
  const sel = row.classification.selected ?? null
  ruleIndex.get(key)[row.rule] = {
    anchor: sel?.anchor ?? null,
    P: sel?.P ?? null,
    P_date: sel?.P_date ?? null,
    P_known_at: sel?.P_known_at ?? null,
    L_setup: sel?.L_setup ?? null,
    L_setup_date: sel?.L_setup_date ?? null,
    first_break: sel?.first_break ?? null,
    path_state: sel?.path_state ?? null,
    skip: sel?.skip ?? null,
    new_high_after_anchor: sel?.new_high_after_anchor ?? null,
    depth: sel?.depth ?? null,
    nearest_anchor: row.classification.nearest_anchor ?? null,
    examined: row.classification.examined ?? null,
    stop: row.classification.stop ?? null,
    reason: row.classification.reason ?? null,
    trace: (row.classification.trace ?? []).map(t => ({
      anchor: t.anchor ?? null, P: t.P ?? null, P_date: t.P_date ?? null, P_known_at: t.P_known_at ?? null,
      L_setup: t.L_setup ?? null, L_setup_date: t.L_setup_date ?? null, first_break: t.first_break ?? null,
      skip: t.skip ?? null, new_high_after_anchor: t.new_high_after_anchor ?? null, depth: t.depth ?? null,
      path_state: t.path_state ?? null,
    })),
  }
}

const outcomesByEvent = new Map()
for (const row of outcomes) {
  if (!outcomesByEvent.has(row.event_id)) outcomesByEvent.set(row.event_id, [])
  outcomesByEvent.get(row.event_id).push({
    horizon: num(row.horizon_observed_sessions),
    available: num(row.available_sessions),
    complete: row.complete === 'True',
    horizon_end: row.horizon_end || null,
    close_return: num(row.close_return),
    max_high_return: num(row.max_high_return),
    min_low_return: num(row.min_low_return),
    reason: row.reason || null,
  })
}
const trackingByEvent = new Map()
for (const row of tracking) {
  if (!trackingByEvent.has(row.event_id)) trackingByEvent.set(row.event_id, [])
  trackingByEvent.get(row.event_id).push({
    asof: row.asof,
    step: num(row.step_observed_sessions),
    relation: row.current_relation_to_frozen_P,
    label: row.tracking_label,
    return_since_D: num(row.return_since_D),
    frozen_D_P: num(row.frozen_D_P),
  })
}

// ── 复权/价格尺度核对 ─────────────────────────────────────────────────
// 冻结 enriched 在 2020-05-08 之后未再前复权，公司行动只表现为原始价台阶；
// 这里用冻结 CSV 的 adj_ratio 跳变或超过板块涨跌幅容差的原始价变动做提示。
// 以下三行由本地 adj_factor/all.parquet 只读核对（sha256 5a957525e43a9c07…，32,845 行 /
// 5,183 标的 / 2018-01-11 ~ 2026-10-28）；不是公告原件，也不代表完整覆盖（COMPLETE）。
const factorEvent = (date, ex_factor, dividend, bonus, prev_close) => ({
  date,
  ex_factor,
  dividend,
  bonus,
  prev_close,
  source: 'adj_factor/all.parquet · 本地只读 · sha256 5a957525e43a9c07…',
  announcement_status: 'PENDING_ORIGINAL_ANNOUNCEMENT',
})

const FACTOR_EVENTS = {
  '600785.SH@2026-07-15': [factorEvent('2026-06-25', 1.409434, 0.1, 0.4, 14.94)],
  '000810.SZ@2026-07-10': [factorEvent('2026-06-16', 1.00739, 0.08, 0, 10.9)],
  '600785.SH@2026-01-14': [
    factorEvent('2025-11-21', 1.00745, 0.1, 0, 13.52),
    factorEvent('2025-06-20', 1.02228, 0.25, 0, 11.47),
  ],
}

const REPORTED_ADJUSTMENT_EVENTS = {
  '000810.SZ@2026-07-10': {
    note: '本地 adj_factor 记录显示窗口内 2026-06-16 有 dividend 0.08、ex_factor=1.00739（非 D 日）；冻结 CSV 未见可识别原始价台阶。该记录不是公告原件，也不代表完整覆盖（COMPLETE），跨尺度影响仍待认证，不把转述当认证。',
  },
  '600785.SH@2026-01-14': {
    note: '本地 adj_factor 记录显示窗口内 2025-11-21 有 dividend 0.1、ex_factor=1.00745（非 D 日）；冻结 CSV 未见可识别原始价台阶。该记录不是公告原件，也不代表完整覆盖（COMPLETE），跨尺度影响仍待认证，不把转述当认证。',
  },
  '600785.SH@2026-07-15': {
    note: '外部报告称窗口跨 2026-06-25 转增；外部只读因子核对为 ex_factor=1.409434、bonus=0.4、prev_close=14.94；冻结 CSV 当日 close=10.31、raw_close=10.31、prev_raw=14.94、change_pct_raw=-30.99%、adj_ratio=1.0，台阶未消除。冻结序列为未复权/跨尺度，不能当已连续复权；跨该日的收益、动量、P-L、位置指标均跨尺度，正确复权需另用因子链重算并独立认证。原始价台阶也不能单独证明转增/除权原因，公告来源与公司行动类型仍待核对。',
  },
}

function rawStepLimit(board) {
  if (board === 'GEM' || board === 'STAR') return 0.21
  if (board === 'BSE') return 0.31
  return 0.11
}

function detectScaleGaps(rows, start, end, limit) {
  const gaps = []
  for (let i = 1; i < rows.length; i += 1) {
    const cur = rows[i]
    const prev = rows[i - 1]
    if (cur.date < start || cur.date > end) continue
    const prevRatio = num(prev.adj_ratio)
    const curRatio = num(cur.adj_ratio)
    const rawChange = num(cur.change_pct_raw)
    const ratioStep = prevRatio != null && curRatio != null && Math.abs(curRatio - prevRatio) > 0.0001
    const rawStep = rawChange != null && Math.abs(rawChange) > limit
    if (!ratioStep && !rawStep) continue
    gaps.push({
      date: cur.date,
      close: num(cur.close),
      raw_close: num(cur.raw_close),
      prev_raw_close: num(prev.raw_close),
      adj_ratio_prev: prevRatio,
      adj_ratio: curRatio,
      raw_change: rawChange,
      kind: ratioStep ? 'ADJ_RATIO_STEP' : 'RAW_PRICE_STEP',
    })
  }
  return gaps
}

function buildScaleCheck(event, rules, meta) {
  const d = event.date
  const rows = orderedRows(event.code)
  const barsUpToD = rows.filter(r => r.date <= d)
  const last90Start = barsUpToD.slice(-90)[0]?.date ?? d
  const anchorDates = []
  for (const rule of Object.values(rules)) {
    for (const key of ['P_date', 'L_setup_date', 'first_break']) {
      if (rule[key]) anchorDates.push(rule[key])
    }
  }
  const firstDate = rows[0]?.date ?? d
  const anchorStart = anchorDates.length ? anchorDates.slice().sort()[0] : d
  const anchorWindowStart = anchorStart < firstDate ? firstDate : anchorStart
  const candidateStart = [last90Start, anchorWindowStart].filter(Boolean).sort()[0] ?? d
  const start = candidateStart < firstDate ? firstDate : candidateStart
  const gaps = detectScaleGaps(rows, start, d, rawStepLimit(meta.board))
  const reported = REPORTED_ADJUSTMENT_EVENTS[event.event_id] ?? null
  const factorEvents = (FACTOR_EVENTS[event.event_id] ?? []).map(item => ({
    ...item,
    in_short_window: item.date >= last90Start,
  }))
  // 只有台阶落在结构锚点区间内，才作废旧结构判断；台阶仅在 90 日图表窗口内时只提示图表/指标跨尺度。
  const structureStart = anchorWindowStart
  const structureAffected = gaps.some(g => g.date >= structureStart && g.date <= d)
  const evidence = gaps.map(g => {
    const pct = g.raw_change == null ? '—' : `${(g.raw_change * 100).toFixed(2)}%`
    return `${g.date} ${g.kind === 'ADJ_RATIO_STEP' ? '复权比跳变' : '原始价台阶'}：前原始收盘 ${g.prev_raw_close ?? '—'} → ${g.raw_close ?? '—'}（${pct}），close/raw ${g.close ?? '—'}/${g.raw_close ?? '—'}，adj_ratio ${g.adj_ratio_prev ?? '—'} → ${g.adj_ratio ?? '—'}`
  })

  if (gaps.length > 0) {
    return {
      state: 'CROSS_SCALE_VERIFIED',
      judgment: structureAffected ? 'INVALID_PENDING_REBUILD' : 'UNVERIFIED',
      window_start: start,
      short_window_start: last90Start,
      anchor_window_start: anchorWindowStart,
      structure_window_start: structureStart,
      window_end: d,
      gap_dates: gaps.map(g => g.date),
      gaps,
      reported_note: reported?.note ?? null,
      evidence,
      verification: 'VERIFIED_FROM_FROZEN_CSV',
      cause_status: 'PRICE_SCALE_ONLY_PENDING_ANNOUNCEMENT',
      factor_events: factorEvents,
    }
  }

  if (factorEvents.length > 0) {
    return {
      state: 'CROSS_SCALE_FACTOR_RECORD',
      judgment: 'UNVERIFIED',
      window_start: start,
      short_window_start: last90Start,
      anchor_window_start: anchorWindowStart,
      structure_window_start: anchorWindowStart,
      window_end: d,
      gap_dates: [],
      gaps: [],
      reported_note: reported?.note ?? null,
      evidence: ['冻结 CSV 的 adj_ratio 在本区间恒为 1，未出现可识别的复权比跳变或超过板块容差的原始价台阶；本地 adj_factor 有窗口内因子记录，但非公告原件、非完整覆盖（COMPLETE），价格尺度影响仍待认证。'],
      verification: 'LOCAL_FACTOR_RECORD_ONLY',
      cause_status: 'LOCAL_FACTOR_RECORD_COVERAGE_UNVERIFIED',
      factor_events: factorEvents,
    }
  }

  if (reported) {
    return {
      state: 'CROSS_SCALE_UNVERIFIED',
      judgment: 'UNVERIFIED',
      window_start: start,
      short_window_start: last90Start,
      anchor_window_start: anchorWindowStart,
      structure_window_start: anchorWindowStart,
      window_end: d,
      gap_dates: [],
      gaps: [],
      reported_note: reported.note,
      evidence: ['外部报告称窗口跨除权日，但本地记录未匹配到因子行；冻结 CSV 未见可识别原始价台阶，跨尺度影响仍待核实。已检索范围未发现可信覆盖来源，代码签名完整性不等于上游覆盖真实性。'],
      verification: 'UNKNOWN',
      cause_status: 'UNKNOWN',
      factor_events: [],
    }
  }

  return {
    state: 'NO_GAP_DETECTED',
    judgment: 'UNVERIFIED',
    window_start: start,
    short_window_start: last90Start,
    anchor_window_start: anchorWindowStart,
    structure_window_start: anchorWindowStart,
    window_end: d,
    gap_dates: [],
    gaps: [],
    reported_note: null,
    evidence: ['冻结 CSV 未出现可识别的复权比跳变或超过板块容差的原始价台阶；这不等于无除权。'],
    verification: 'UNKNOWN',
    cause_status: 'UNKNOWN',
    factor_events: [],
  }
}

const eventList = events.map(ev => {
  const rules = ruleIndex.get(ev.event_id) ?? {}
  const meta = manifest.per_symbol[ev.code]
  return {
    event_id: ev.event_id,
    code: ev.code,
    date: ev.date,
    version: ev.version,
    raw_open: ev.raw_open,
    raw_high: ev.raw_high,
    raw_low: ev.raw_low,
    raw_close: ev.raw_close,
    previous_observed_raw_close: ev.previous_observed_raw_close,
    raw_change_vs_previous_observed_close: ev.raw_change_vs_previous_observed_close,
    board_identity_certification: ev.board_identity_certification,
    shape_certification: ev.shape_certification,
    coverage_reason: ev.coverage_reason,
    structural_price_basis: ev.structural_price_basis,
    preclose_reason: ev.preclose_reason,
    factors_D_minus_1: ev.factors_D_minus_1,
    factors_D_close: ev.factors_D_close,
    rules,
    outcomes: outcomesByEvent.get(ev.event_id) ?? [],
    tracking: trackingByEvent.get(ev.event_id) ?? [],
    scale_check: buildScaleCheck(ev, rules, meta),
  }
})

const payload = {
  schema: 'firstboard-replay-web-2',
  generated_at: new Date().toISOString(),
  rule_version: events[0]?.version ?? 'replay-v01',
  default_rule: DEFAULT_RULE,
  rules: RULES,
  research_root: relative(repo, research).replaceAll('\\', '/'),
  classification: {
    schema_version: v012Manifest.schema_version,
    calculation_version: v012Manifest.calculation_version,
    source_version: v011Manifest.schema_version,
    source_path: relative(repo, sources.classifications_v011).replaceAll('\\', '/'),
    source_sha256: v011Hash,
    output_path: relative(repo, sources.classifications).replaceAll('\\', '/'),
    output_sha256: v012Hash,
    added_null_keys: v012Manifest.added_nulls,
    validation: v012Manifest.validation,
    legacy_v01: {
      path: relative(repo, sources.classifications_v01).replaceAll('\\', '/'),
      sha256: v01Hash,
    },
    legacy_output: {
      path: relative(repo, legacyOutFile).replaceAll('\\', '/'),
      sha256: existsSync(legacyOutFile) ? sha256(legacyOutFile) : null,
    },
  },
  sources: Object.fromEntries(Object.entries(sources).map(([k, p]) => [
    k,
    { path: relative(repo, p).replaceAll('\\', '/'), sha256: sha256(p) },
  ])),
  limitations: manifest.limitations,
  symbols,
  events: eventList,
  factor_meta: factorMeta,
}

mkdirSync(outDir, { recursive: true })
writeFileSync(outFile, JSON.stringify(payload), 'utf8')
const kb = (Buffer.byteLength(JSON.stringify(payload)) / 1024).toFixed(1)
console.log(`wrote ${outFile} (${kb} KB)`)
console.log(`classification=${v012Manifest.schema_version} source=${v011Manifest.schema_version} calculation=${v012Manifest.calculation_version}`)
console.log(`symbols=${symbols.length} events=${eventList.length} rules=${RULES.length}`)
