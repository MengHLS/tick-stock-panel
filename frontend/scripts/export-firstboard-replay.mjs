#!/usr/bin/env node
/**
 * 只读导出：把 docs/research 下冻结的首板回放材料整理成前端可 fetch 的紧凑 JSON。
 *
 * - 只读取冻结材料，不写研究目录、不重算收益、不访问数据仓库。
 * - 输出固定写 frontend/public/research/firstboard/replay.json（Vite 会原样拷进 dist）。
 * - 记录每个源文件的 SHA256，便于页面展示来源并在材料变化时发现漂移。
 *
 * 用法: node scripts/export-firstboard-replay.mjs
 */
import { createHash } from 'node:crypto'
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const repo = resolve(here, '..', '..')
const research = join(repo, 'docs', 'research', 'firstboard-classification-draft-20261027')
const v01 = join(research, 'event-replay-v01')
const outDir = join(here, '..', 'public', 'research', 'firstboard')
const outFile = join(outDir, 'replay.json')

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
  classifications: join(v01, 'candidate-classifications.json'),
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
const classifications = JSON.parse(readFileSync(sources.classifications, 'utf8'))
const outcomes = parseCsv(readFileSync(sources.outcomes, 'utf8'))
const tracking = JSON.parse(readFileSync(sources.tracking, 'utf8'))
const factorRows = parseCsv(readFileSync(sources.factors, 'utf8'))

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
const symbols = Object.entries(manifest.per_symbol).map(([code, meta]) => {
  const rows = (bySymbol.get(code) ?? []).sort((a, b) => a.date.localeCompare(b.date))
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

const eventList = events.map(ev => ({
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
  rules: ruleIndex.get(ev.event_id) ?? {},
  outcomes: outcomesByEvent.get(ev.event_id) ?? [],
  tracking: trackingByEvent.get(ev.event_id) ?? [],
}))

const payload = {
  schema: 'firstboard-replay-web-1',
  generated_at: new Date().toISOString(),
  rule_version: events[0]?.version ?? 'replay-v01',
  default_rule: DEFAULT_RULE,
  rules: RULES,
  research_root: relative(repo, research).replaceAll('\\', '/'),
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
console.log(`symbols=${symbols.length} events=${eventList.length} rules=${RULES.length}`)
