export type PlanStatus = 'planned' | 'entered' | 'exited' | 'missed' | 'cancelled'

export type SetupType =
  | 'first_board'
  | 'relay'
  | 'dip'
  | 'halfway'
  | 'reversal'
  | 'leader_first_yin'
  | 'other'

export type MarketMood = 'ice' | 'repair' | 'ferment' | 'climax' | 'ebb' | 'skip'

export type HoldingPlan = 'intraday' | 'overnight' | 'one_two_days' | 'three_days_plus'

export interface TradePlanPayload {
  plan_date: string
  symbol: string
  name: string
  setup: SetupType
  market_mood: MarketMood
  confidence: number
  planned_hold: HoldingPlan
  thesis: string
  trigger: string
  invalidation: string
  planned_entry_low: number | null
  planned_entry_high: number | null
  stop_loss: number | null
  target_price: number | null
  planned_position_pct: number | null
  status: PlanStatus
  actual_entry_price: number | null
  entry_at: string | null
  actual_position_pct: number | null
  actual_exit_price: number | null
  exit_at: string | null
  exit_reason: string | null
  review: string
  tags: string[]
}

export interface PlanMetrics {
  planned_entry_mid: number | null
  planned_risk_pct: number | null
  actual_risk_pct: number | null
  planned_rr: number | null
  entry_deviation_pct: number | null
  chase_pct: number | null
  pnl_pct: number | null
  r_multiple: number | null
  entry_in_plan: boolean | null
  position_in_plan: boolean | null
  stop_respected: boolean | null
  discipline_score: number | null
  hold_minutes: number | null
}

export interface PlanFlag {
  code: string
  label: string
  tone: 'danger' | 'warn' | 'info' | 'muted'
}

export interface TradePlan extends TradePlanPayload {
  id: string
  created_at: string
  updated_at: string
  version: number
  metrics: PlanMetrics
  flags: PlanFlag[]
}

export interface GroupStats {
  key: string
  count: number
  closed: number
  win_rate: number | null
  avg_pnl_pct: number | null
  avg_r: number | null
}

export interface EquityPoint {
  date: string
  symbol: string
  pnl_pct: number
  cum_pct: number
}

export interface FlagCount {
  code: string
  label: string
  tone: string
  count: number
}

export interface TradeStats {
  total: number
  planned: number
  entered: number
  exited: number
  missed: number
  cancelled: number
  executed: number
  execution_rate: number | null
  closed: number
  win_rate: number | null
  avg_pnl_pct: number | null
  total_pnl_pct: number | null
  avg_r: number | null
  total_r: number | null
  avg_win_pct: number | null
  avg_loss_pct: number | null
  profit_factor: number | null
  discipline_score: number | null
  chase_count: number
  stop_breach_count: number
  flag_counts: FlagCount[]
  by_setup: GroupStats[]
  by_mood: GroupStats[]
  equity_curve: EquityPoint[]
}

export interface AiPlanReport {
  id: string
  created_at: string
  start: string | null
  end: string | null
  focus: string
  content: string
  summary: string
  stats: Partial<TradeStats>
}

export interface AnalyzeMeta {
  plan_count: number
  closed_count: number
  execution_rate: number | null
  win_rate: number | null
  avg_pnl_pct: number | null
  avg_r: number | null
  discipline_score: number | null
}

export const STATUS_LABEL: Record<PlanStatus, string> = {
  planned: '待执行',
  entered: '持仓中',
  exited: '已结束',
  missed: '未执行',
  cancelled: '已取消',
}

export const STATUS_CLASS: Record<PlanStatus, string> = {
  planned: 'border-border bg-elevated text-secondary',
  entered: 'border-accent/30 bg-accent/10 text-accent',
  exited: 'border-border bg-surface text-foreground',
  missed: 'border-warning/30 bg-warning/10 text-warning',
  cancelled: 'border-border bg-surface text-muted',
}

export const SETUP_LABEL: Record<SetupType, string> = {
  first_board: '首板打板',
  relay: '连板接力',
  dip: '低吸',
  halfway: '半路',
  reversal: '反包',
  leader_first_yin: '龙头首阴',
  other: '其他',
}

export const MOOD_LABEL: Record<MarketMood, string> = {
  ice: '冰点',
  repair: '修复',
  ferment: '发酵',
  climax: '高潮',
  ebb: '退潮',
  skip: '不参与',
}

export const HOLD_LABEL: Record<HoldingPlan, string> = {
  intraday: '日内',
  overnight: '隔日',
  one_two_days: '1-2日',
  three_days_plus: '3日+',
}

export const EXIT_REASON_OPTIONS = [
  { value: 'target', label: '止盈' },
  { value: 'stop', label: '止损' },
  { value: 'time', label: '时间止损' },
  { value: 'mood', label: '情绪走弱' },
  { value: 'manual', label: '主观离场' },
  { value: 'other', label: '其他' },
] as const

export const EXIT_REASON_LABEL: Record<string, string> = Object.fromEntries(
  EXIT_REASON_OPTIONS.map(item => [item.value, item.label]),
)
