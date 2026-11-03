/**
 * 首板回放页的纯数据模型与文案生成。
 *
 * 约束: 只用冻结材料里的字段, 不计算任何综合评分/收益; 后续结果只做描述性展示。
 */

export interface FbBar {
  date: string
  open: number
  high: number
  low: number
  close: number
  rawClose: number | null
  firstBoard: boolean
}

export interface FbRuleResult {
  anchor: string | null
  P: number | null
  P_date: string | null
  P_known_at: string | null
  L_setup: number | null
  L_setup_date: string | null
  first_break: string | null
  path_state: string | null
  skip: boolean | null
  new_high_after_anchor: boolean | null
  depth: number | null
  nearest_anchor: string | null
  examined: number | null
  stop: string | null
  reason: string | null
  trace: Array<{
    anchor: string | null
    P: number | null
    P_date: string | null
    P_known_at: string | null
    L_setup: number | null
    L_setup_date: string | null
    first_break: string | null
    skip: boolean | null
    new_high_after_anchor: boolean | null
    depth: number | null
    path_state: string | null
  }>
}

export interface FbOutcome {
  horizon: number | null
  available: number | null
  complete: boolean
  horizon_end: string | null
  close_return: number | null
  max_high_return: number | null
  min_low_return: number | null
  reason: string | null
}

export interface FbFactors {
  asof: string
  amount: number | null
  volume: number | null
  turnover_rate: number | null
  turnover_reason?: string | null
  return_5: number | null
  return_20: number | null
  return_60: number | null
  return_120: number | null
  return_250: number | null
  position_250: number | null
  position_240: number | null
  ma_bias_20: number | null
  daily_return_std_20: number | null
  volume_ratio_vs_prior5: number | null
  coverage_250: number | null
}

export type FbScaleState = 'CROSS_SCALE_VERIFIED' | 'CROSS_SCALE_FACTOR_RECORD' | 'CROSS_SCALE_UNVERIFIED' | 'NO_GAP_DETECTED'

export interface FbScaleGap {
  date: string
  close: number | null
  raw_close: number | null
  prev_raw_close: number | null
  adj_ratio_prev: number | null
  adj_ratio: number | null
  raw_change: number | null
  kind: 'ADJ_RATIO_STEP' | 'RAW_PRICE_STEP'
}

/** 本地 adj_factor 只读核对到的窗口内因子事件；不是公告原件，也不代表完整覆盖。 */
export interface FbFactorEvent {
  date: string
  ex_factor: number | null
  dividend: number | null
  bonus: number | null
  prev_close: number | null
  source: string
  announcement_status: 'PENDING_ORIGINAL_ANNOUNCEMENT'
  /** 是否落在 90 日回放窗口内；false 表示仅在锚点区间内。 */
  in_short_window: boolean
}

/** 冻结材料内的价格尺度/公司行动核对结果；UNKNOWN 明确表示没有原始证据。 */
export interface FbScaleCheck {
  state: FbScaleState
  judgment: 'INVALID_PENDING_REBUILD' | 'UNVERIFIED'
  window_start: string
  short_window_start: string
  anchor_window_start: string
  structure_window_start: string
  window_end: string
  gap_dates: string[]
  gaps: FbScaleGap[]
  reported_note: string | null
  evidence: string[]
  verification: 'VERIFIED_FROM_FROZEN_CSV' | 'LOCAL_FACTOR_RECORD_ONLY' | 'UNKNOWN'
  /** 价格台阶只能证明尺度异常；公司行动类型需公告/因子来源。 */
  cause_status: 'PRICE_SCALE_ONLY_PENDING_ANNOUNCEMENT' | 'LOCAL_FACTOR_RECORD_COVERAGE_UNVERIFIED' | 'UNKNOWN'
  factor_events?: FbFactorEvent[]
}

export interface FbEvent {
  event_id: string
  code: string
  date: string
  version: string
  raw_open: number
  raw_high: number
  raw_low: number
  raw_close: number
  previous_observed_raw_close: number | null
  raw_change_vs_previous_observed_close: number | null
  board_identity_certification: string
  shape_certification: string
  coverage_reason: string
  structural_price_basis: string
  preclose_reason: string
  factors_D_minus_1: FbFactors
  factors_D_close: FbFactors
  rules: Record<string, FbRuleResult>
  outcomes: FbOutcome[]
  tracking: Array<{ asof: string; step: number | null; relation: string | null; label: string | null; return_since_D: number | null; frozen_D_P: number | null }>
  scale_check?: FbScaleCheck
}

export interface FbSymbol {
  code: string
  name: string
  board: string
  listing_date: string
  firstboard_identity: string
  first_boards: string[]
  bars: Array<[string, number | null, number | null, number | null, number | null, number | null, number | null]>
}

export interface FbClassificationProvenance {
  schema_version: string
  calculation_version: string
  source_version: string
  source_path: string
  source_sha256: string
  output_path: string
  output_sha256: string
  added_null_keys: number
  validation: string
  legacy_v01: { path: string; sha256: string }
  legacy_output?: { path: string; sha256: string | null }
}

export interface FbReplayData {
  schema: string
  generated_at: string
  rule_version: string
  default_rule: string
  rules: string[]
  research_root: string
  classification?: FbClassificationProvenance
  sources: Record<string, { path: string; sha256: string }>
  limitations: string[]
  symbols: FbSymbol[]
  events: FbEvent[]
  factor_meta: Record<string, { unit: string; formula: string; window: number | null; role: string }>
}

export function toBars(symbol: FbSymbol): FbBar[] {
  return symbol.bars.map(([date, open, high, low, close, rawClose, flag]) => ({
    date,
    open: Number(open),
    high: Number(high),
    low: Number(low),
    close: Number(close),
    rawClose: rawClose == null ? null : Number(rawClose),
    firstBoard: Number(flag) === 1,
  }))
}

/** D 日截断: 历史图永远不含 D 之后的数据 */
export function barsUpToD(bars: FbBar[], d: string): FbBar[] {
  return bars.filter(bar => bar.date <= d)
}

/** 短周期回放窗口: D 之前最近 n 根, 仍不含 D 之后 */
export function replayWindow(bars: FbBar[], d: string, n = 90): FbBar[] {
  return barsUpToD(bars, d).slice(-n)
}

/** 后续走势: 只在用户主动展开时使用, 与历史图分开渲染; 首根严格晚于 D */
export function futureWindow(bars: FbBar[], d: string, n = 20): FbBar[] {
  return bars.filter(bar => bar.date > d).slice(0, n)
}

export function positionBucket(position: number | null): string {
  if (position == null || !Number.isFinite(position)) return '位置数据缺失'
  if (position >= 2 / 3) return '位于近250日区间上部'
  if (position >= 1 / 3) return '位于近250日区间中部'
  return '位于近250日区间下部'
}

function pct(value: number | null | undefined, digits = 1): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${(value * 100).toFixed(digits)}%`
}

export interface EventNarrative {
  background: string
  recent: string
  local: string
  board: string
}

export function describeEvent(event: FbEvent): EventNarrative {
  const bg = event.factors_D_minus_1
  const d = event.factors_D_close
  const trend20 = d.return_20
  const trendDir = trend20 == null ? '近期走势数据缺失' : trend20 >= 0 ? `近20日上涨 ${pct(trend20)}` : `近20日下跌 ${pct(-trend20)}`
  const vol = d.daily_return_std_20
  const background = [
    `截至 ${bg.asof} 收盘，${positionBucket(d.position_250 ?? bg.position_250)}，${trendDir}。`,
    vol == null ? '' : `近20日波动（日收益标准差）约 ${(vol * 100).toFixed(1)}%。`,
  ].filter(Boolean).join('')
  const recent = [
    `首板前一日成交量 ${bg.volume == null ? '—' : Math.round(bg.volume).toLocaleString()} 手级单位，量比 ${bg.volume_ratio_vs_prior5 == null ? '—' : bg.volume_ratio_vs_prior5.toFixed(2)}（当日量 / 前5日均量）。`,
    `近60日 ${pct(bg.return_60)}、近120日 ${pct(bg.return_120)}，用于看这段回调发生在什么位置。`,
  ].join('')
  const local = [
    `D 日开 ${event.raw_open}、高 ${event.raw_high}、低 ${event.raw_low}、收 ${event.raw_close}（原始价，两位小数）。`,
    `相对上一可观测原始收盘 ${event.previous_observed_raw_close ?? '—'} 变化 ${pct(event.raw_change_vs_previous_observed_close)}；`,
    '交易所除权昨收缺失，这不是官方涨幅。',
  ].join('')
  const board = '首板身份按平台 consecutive_limit_ups==1 口径，历史 ST/早期板块制度未认证；本批 4 只股票是已挑选的开发样本，只能验证方法，不是独立证据。'
  return { background, recent, local, board }
}

export interface RuleLine {
  key: string
  label: string
  value: string
}

/** 规则判定的中文解释（不含数字报表味道的堆砌） */
export function describeRule(rule: FbRuleResult | null | undefined): { text: string; dates: string[] } {
  if (!rule || rule.P == null) {
    return { text: '该规则在此事件上没有选出可用的锚点/结构低点（可能历史窗口不足或路径提前突破）。', dates: [] }
  }
  const parts: string[] = []
  parts.push(`最近锚点 ${rule.anchor ?? '—'} 的高点 P=${rule.P}`)
  if (rule.L_setup != null) parts.push(`此前回踩的结构低点 L=${rule.L_setup}`)
  const dates: string[] = []
  if (rule.P_date) dates.push(`P 形成于 ${rule.P_date}`)
  if (rule.P_known_at) dates.push(`最早可知 ${rule.P_known_at}`)
  if (rule.L_setup != null) dates.push(`结构低点 L=${rule.L_setup}${rule.L_setup_date ? `（${rule.L_setup_date}）` : ''}`)
  if (rule.first_break) dates.push(`首次收盘突破 ${rule.first_break}`)
  if (rule.skip) parts.push('该锚点因已有突破/未形成回踩等被跳过')
  if (rule.new_high_after_anchor) parts.push('锚点后又创出新高')
  if (rule.depth != null) parts.push(`回调深度 ${(rule.depth * 100).toFixed(1)}%`)
  if (rule.path_state) parts.push(`路径状态 ${rule.path_state}`)
  if (rule.examined != null) parts.push(`共检查 ${rule.examined} 个锚点`)
  return { text: `${parts.join('；')}。`, dates }
}

export interface ScaleCheckDescription {
  tone: 'danger' | 'warn' | 'muted'
  title: string
  summary: string
  details: string[]
  causeText: string
  invalidatesJudgment: boolean
}

/** 把尺度核对翻译成页面文案；UNKNOWN 不能写成“已验证无除权”。 */
export function describeScaleCheck(check: FbScaleCheck | null | undefined): ScaleCheckDescription {
  if (!check) {
    return {
      tone: 'muted',
      title: '未提供尺度核对状态',
      summary: '该事件没有价格尺度/除权连续性状态，不能据此推断已认证。',
      details: [],
      causeText: '未提供',
      invalidatesJudgment: false,
    }
  }
  const dates = check.gap_dates.join('、')
  if (check.state === 'CROSS_SCALE_VERIFIED') {
    if (check.judgment === 'INVALID_PENDING_REBUILD') {
      return {
        tone: 'danger',
        title: '结构判断作废/待重算：窗口跨价格台阶',
        summary: `锚点区间 ${check.window_start} ~ ${check.window_end} 跨 ${dates} 的价格台阶，P/L 不在同一价格尺度；旧结构判断不能作为有效结论。价格台阶只证明尺度异常；本地因子记录日期与台阶日一致，但公告原件/公司行动类型仍待核对（UNKNOWN）。`,
        details: [check.reported_note, ...check.evidence].filter((item): item is string => Boolean(item)),
        causeText: '价格台阶已证实；公告原件/公司行动类型待核对',
        invalidatesJudgment: true,
      }
    }
    return {
      tone: 'warn',
      title: '窗口跨价格台阶：图表/指标跨尺度',
      summary: `90日窗口 ${check.short_window_start} ~ ${check.window_end} 跨 ${dates} 的价格台阶；结构锚点均在 ${check.structure_window_start} 之后，结构判断不直接作废，但图表、收益、动量、位置指标仍跨尺度，需复核。`,
      details: [check.reported_note, ...check.evidence].filter((item): item is string => Boolean(item)),
      causeText: '价格台阶已证实；结构锚点在台阶后，公告原件/公司行动类型待核对',
      invalidatesJudgment: false,
    }
  }
  if (check.state === 'CROSS_SCALE_FACTOR_RECORD') {
    const events = check.factor_events ?? []
    const factorDate = events[0]?.date ?? '—'
    const eventText = events.length > 1 ? `${events.length} 个因子事件（最近 ${factorDate}）` : `因子事件 ${factorDate}`
    return {
      tone: 'warn',
      title: '跨尺度（本地因子记录，未认证覆盖）',
      summary: `窗口 ${check.short_window_start} ~ ${check.window_end} 含 ${eventText}（非 D 日）；冻结 CSV 未见原始价台阶。该记录仅为本地 adj_factor，非公告权威、非完整覆盖（COMPLETE），跨尺度影响与结构判断仍待认证，不把转述当认证。`,
      details: [check.reported_note, ...check.evidence].filter((item): item is string => Boolean(item)),
      causeText: '本地因子记录；公告原件/完整覆盖未认证',
      invalidatesJudgment: false,
    }
  }
  if (check.state === 'CROSS_SCALE_UNVERIFIED') {
    return {
      tone: 'warn',
      title: '跨尺度待核实（UNKNOWN）',
      summary: '外部报告称该事件窗口跨除权日，但本地记录未匹配到因子行；冻结 CSV 未见可识别原始价台阶，跨尺度影响仍待核实（UNKNOWN），不把口述当已验证。',
      details: [check.reported_note, ...check.evidence].filter((item): item is string => Boolean(item)),
      causeText: '未匹配到本地因子记录；跨尺度影响待核实（UNKNOWN）',
      invalidatesJudgment: false,
    }
  }
  return {
    tone: 'muted',
    title: '未发现可识别除权台阶',
    summary: '仅表示冻结 CSV 中没有可识别的复权比跳变或超限原始价台阶，不等于无除权。',
    details: check.evidence,
    causeText: '未核对（UNKNOWN）',
    invalidatesJudgment: false,
  }
}

export function scaleStateLabel(state: FbScaleState | undefined, judgment?: FbScaleCheck['judgment']): string | null {
  if (state === 'CROSS_SCALE_VERIFIED') {
    return judgment === 'INVALID_PENDING_REBUILD' ? '跨尺度·作废' : '跨尺度·窗口'
  }
  if (state === 'CROSS_SCALE_FACTOR_RECORD') return '跨尺度·因子记录'
  if (state === 'CROSS_SCALE_UNVERIFIED') return '跨尺度·待核实'
  return null
}

export function pctText(value: number | null | undefined, digits = 1): string {
  return pct(value, digits)
}
