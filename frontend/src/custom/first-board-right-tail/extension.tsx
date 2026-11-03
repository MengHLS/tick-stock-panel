import { lazy, Suspense, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  ArrowUpRight,
  BellRing,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleDollarSign,
  Clock3,
  Gauge,
  Import,
  LineChart,
  Loader2,
  Play,
  RefreshCw,
  RotateCcw,
  ShieldAlert,
  Target,
  Trash2,
  TrendingUp,
  X,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { Modal } from '@/components/Modal'
import { PageHeader } from '@/components/PageHeader'
import { toast } from '@/components/Toast'
import type { FrontendExtension } from '@/extensions/types'
import { toNavItems, type NavItem } from '@/lib/listNav'

const StockDailyKChart = lazy(() =>
  import('@/components/StockDailyKChart').then(module => ({ default: module.StockDailyKChart })),
)
const StockMultiDayIntradayChart = lazy(() =>
  import('@/components/StockMultiDayIntradayChart').then(module => ({
    default: module.StockMultiDayIntradayChart,
  })),
)

type EventStatus = 'WATCH' | 'BUY_PENDING' | 'FILLED' | 'DROPPED'
type Filter = 'active' | 'all' | EventStatus

interface WatchEvent {
  event_id: string
  symbol: string
  name: string | null
  event_date: string
  t_close_raw: number
  t_close_adj: number
  t_high_raw: number
  t_high_adj: number
  limit_up_price: number
  status: EventStatus
  watch_day: number
  trigger_rule: string | null
  triggered_rules: string[]
  blocked_rules: string[]
  pending: {
    rule: string
    signal_time: string
    order_time: string
    signal_price_adj: number
    reason: string
  } | null
  entry_price_raw: number | null
  entry_price_adj: number | null
  fill_time: string | null
  drop_reason: string | null
  last_price_raw: number | null
  last_price_adj: number | null
  change_pct: number | null
  last_observed_at: string | null
  data_status: string | null
  capacity_warning: boolean | null
}

interface Overview {
  as_of: string | null
  algorithm_version: string
  summary: {
    total: number
    watching: number
    pending: number
    filled: number
    dropped: number
  }
  events: WatchEvent[]
  runtime: {
    last_evaluation?: string
    minute_status?: string
    minute_last_time?: string
    active_symbols?: number
    auction_symbols?: number
    d_available?: boolean
    realtime_enabled?: boolean
    quote_interval?: number
  }
  rules: Record<string, string>
  simple_rule_ids: string[]
}

interface PreviewTarget {
  symbol: string
  name?: string
}

const KLINE_RANGES = [
  { key: 3, label: '3月' },
  { key: 6, label: '6月' },
  { key: 12, label: '1年' },
] as const
const INTRADAY_RANGES = [1, 3, 5, 10] as const

type KlineView = 'daily' | 'intraday'

function rangeForMonths(months: number) {
  const end = new Date()
  const start = new Date(end)
  start.setMonth(start.getMonth() - months)
  return {
    start: start.toISOString().slice(0, 10),
    end: end.toISOString().slice(0, 10),
  }
}

const BASE = '/api/custom/first-board-right-tail'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    signal: AbortSignal.timeout(30_000),
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(typeof payload.detail === 'string' ? payload.detail : `请求失败（${response.status}）`)
  }
  return payload as T
}

const client = {
  overview: () => request<Overview>('/overview'),
  importLatest: () => request<{ imported: number; total: number; event_date: string | null }>(
    '/import-latest',
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' },
  ),
  evaluate: () => request<{ ok: boolean; count: number; events: Array<{ message: string }> }>(
    '/evaluate',
    { method: 'POST' },
  ),
  seedSimple: () => request<{ ok: boolean; rules: unknown[] }>(
    '/simple-monitor-rules',
    { method: 'POST' },
  ),
  reset: (eventId: string) => request<{ ok: boolean }>(
    `/events/${encodeURIComponent(eventId)}/reset`,
    { method: 'POST' },
  ),
  remove: (eventId: string) => request<{ ok: boolean }>(
    `/events/${encodeURIComponent(eventId)}`,
    { method: 'DELETE' },
  ),
  key: ['first-board-right-tail', 'overview'] as const,
}

const STATUS_META: Record<EventStatus, { label: string; className: string; dot: string }> = {
  WATCH: { label: '观察中', className: 'border-sky-400/30 bg-sky-400/10 text-sky-300', dot: 'bg-sky-400' },
  BUY_PENDING: { label: '待成交确认', className: 'border-amber-400/35 bg-amber-400/10 text-amber-300', dot: 'bg-amber-400' },
  FILLED: { label: '已确认买点', className: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300', dot: 'bg-emerald-400' },
  DROPPED: { label: '已放弃', className: 'border-rose-400/25 bg-rose-400/10 text-rose-300', dot: 'bg-rose-400' },
}

const RULE_META = [
  { id: 'A', title: '突破确认', tone: 'from-cyan-400/20', accent: 'text-cyan-300' },
  { id: 'B', title: '站稳 VWAP', tone: 'from-sky-400/20', accent: 'text-sky-300' },
  { id: 'C', title: '回踩 MA5', tone: 'from-emerald-400/20', accent: 'text-emerald-300' },
  { id: 'D', title: '竞价确认', tone: 'from-amber-400/20', accent: 'text-amber-300' },
]

const FILTERS: Array<{ key: Filter; label: string }> = [
  { key: 'active', label: '活动池' },
  { key: 'all', label: '全部' },
  { key: 'WATCH', label: '观察中' },
  { key: 'BUY_PENDING', label: '待确认' },
  { key: 'FILLED', label: '已触发' },
  { key: 'DROPPED', label: '已放弃' },
]

function pct(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(2)}%`
}

function price(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return '—'
  return value.toFixed(2)
}

function shortTime(value: string | null | undefined) {
  if (!value) return '—'
  const parsed = new Date(/[zZ]|[+-]\d{2}:\d{2}$/.test(value) ? value : `${value}+08:00`)
  if (Number.isNaN(parsed.getTime())) return value.replace('T', ' ')
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(parsed)
}

function distanceFrom(value: number | null, reference: number | null) {
  if (value == null || reference == null || reference <= 0) return null
  return value / reference - 1
}

function statusMatches(event: WatchEvent, filter: Filter) {
  if (filter === 'all') return true
  if (filter === 'active') return event.status === 'WATCH' || event.status === 'BUY_PENDING'
  return event.status === filter
}

function StatCard({
  label,
  value,
  hint,
  icon: Icon,
}: {
  label: string
  value: number
  hint: string
  icon: typeof Target
}) {
  return (
    <div className="relative overflow-hidden rounded-xl border border-border/80 bg-surface px-4 py-3.5">
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/15 to-transparent" />
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[10px] font-medium uppercase tracking-[0.16em] text-muted">{label}</div>
          <div className="mt-1.5 font-mono text-2xl font-semibold tabular-nums text-foreground">{value}</div>
          <div className="mt-0.5 text-[11px] text-muted">{hint}</div>
        </div>
        <Icon size={18} className="mt-0.5 text-accent/80" />
      </div>
    </div>
  )
}

function StatusBadge({ status }: { status: EventStatus }) {
  const meta = STATUS_META[status] ?? STATUS_META.WATCH
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[10px] font-medium ${meta.className}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} />
      {meta.label}
    </span>
  )
}

function RuleStrip({ rules, runtime }: { rules: Record<string, string>; runtime: Overview['runtime'] }) {
  return (
    <section className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-4">
      {RULE_META.map(rule => {
        const unavailable = rule.id === 'D' && runtime.d_available === false
        return (
          <div
            key={rule.id}
            className={`relative overflow-hidden rounded-xl border border-border/80 bg-gradient-to-br ${rule.tone} to-transparent p-3.5`}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className={`font-mono text-lg font-semibold ${rule.accent}`}>{rule.id}</span>
                <span className="text-xs font-medium text-foreground">{rule.title}</span>
              </div>
              <span className={`text-[10px] ${unavailable ? 'text-rose-300' : 'text-muted'}`}>
                {unavailable ? '数据未就绪' : '动态触发'}
              </span>
            </div>
            <p className="mt-2 text-[11px] leading-5 text-secondary">{rules[rule.id] ?? '规则说明未加载'}</p>
          </div>
        )
      })}
    </section>
  )
}

function EventDetail({
  event,
  onPreview,
  onReset,
  onRemove,
  busy,
}: {
  event: WatchEvent
  onPreview: (event: WatchEvent) => void
  onReset: (id: string) => void
  onRemove: (id: string) => void
  busy: boolean
}) {
  const stale = event.data_status && event.data_status !== 'ok'
  return (
    <div className="grid grid-cols-1 gap-3 border-t border-border/70 bg-base/30 px-4 py-4 text-xs md:grid-cols-3">
      <div className="space-y-1.5">
        <div className="text-[10px] uppercase tracking-[0.12em] text-muted">决策路径</div>
        <div className="text-secondary">T 日：{event.event_date} · 观察第 {event.watch_day}/5 日</div>
        <div className="text-secondary">
          T 高 {price(event.t_high_raw)} · T 收 {price(event.t_close_raw)} · 放弃线 {price(event.t_close_raw * 0.94)}
        </div>
        <div className="text-secondary">
          已触发：{event.triggered_rules.length ? event.triggered_rules.join(' / ') : '尚未触发'}
        </div>
      </div>
      <div className="space-y-1.5">
        <div className="text-[10px] uppercase tracking-[0.12em] text-muted">执行口径</div>
        <div className="text-secondary">
          信号：{event.pending ? `${event.pending.rule} 组 @ ${shortTime(event.pending.signal_time)}` : '—'}
        </div>
        <div className="text-secondary">
          下一分钟：{event.pending ? shortTime(event.pending.order_time) : event.fill_time ? shortTime(event.fill_time) : '—'}
        </div>
        <div className="text-secondary">
          参考入场：{price(event.entry_price_raw)}
          {event.capacity_warning ? ' · 容量历史不足' : ''}
        </div>
      </div>
      <div className="space-y-1.5">
        <div className="text-[10px] uppercase tracking-[0.12em] text-muted">状态说明</div>
        <div className={stale ? 'text-rose-300' : 'text-secondary'}>
          {event.drop_reason || event.pending?.reason || (event.status === 'FILLED' ? '同一事件不会重复入场；继续跟踪 -6% 风险线。' : '等待完成 K 线触发。')}
        </div>
        {event.blocked_rules.length > 0 && (
          <div className="text-amber-300">不可成交后已冻结规则：{event.blocked_rules.join(' / ')}</div>
        )}
        <div className="flex flex-wrap gap-2 pt-1">
          <button
            type="button"
            onClick={() => onPreview(event)}
            className="inline-flex items-center gap-1.5 rounded-btn border border-cyan-400/25 bg-cyan-400/5 px-2.5 py-1.5 text-[11px] text-cyan-300 hover:bg-cyan-400/10"
          >
            <LineChart size={12} /> 查看 K 线
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => onReset(event.event_id)}
            className="inline-flex items-center gap-1.5 rounded-btn border border-border bg-elevated px-2.5 py-1.5 text-[11px] text-secondary hover:text-foreground disabled:opacity-50"
          >
            <RotateCcw size={12} /> 重置状态
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => onRemove(event.event_id)}
            className="inline-flex items-center gap-1.5 rounded-btn border border-rose-400/20 bg-rose-400/5 px-2.5 py-1.5 text-[11px] text-rose-300 hover:bg-rose-400/10 disabled:opacity-50"
          >
            <Trash2 size={12} /> 移出观察池
          </button>
        </div>
      </div>
    </div>
  )
}

function DesktopTable({
  events,
  selected,
  onSelect,
  onPreview,
  onReset,
  onRemove,
  busy,
}: {
  events: WatchEvent[]
  selected: string
  onSelect: (id: string) => void
  onPreview: (event: WatchEvent) => void
  onReset: (id: string) => void
  onRemove: (id: string) => void
  busy: boolean
}) {
  return (
    <div className="hidden overflow-hidden rounded-xl border border-border bg-surface lg:block">
      <table className="w-full text-xs">
        <thead className="border-b border-border bg-elevated/45 text-[10px] uppercase tracking-[0.1em] text-muted">
          <tr>
            <th className="px-4 py-2.5 text-left">标的</th>
            <th className="px-3 py-2.5 text-left">状态</th>
            <th className="px-3 py-2.5 text-right">观察日</th>
            <th className="px-3 py-2.5 text-right">最新价</th>
            <th className="px-3 py-2.5 text-right">距 T 高</th>
            <th className="px-3 py-2.5 text-right">距放弃线</th>
            <th className="px-3 py-2.5 text-left">规则 / 最近动作</th>
            <th className="px-3 py-2.5 text-right">更新</th>
          </tr>
        </thead>
        <tbody>
          {events.map(event => {
            const open = selected === event.event_id
            return (
              <tr key={event.event_id} className="group border-b border-border/65 last:border-0">
                <td colSpan={8} className="p-0">
                  <button
                    type="button"
                    onClick={() => onSelect(event.event_id)}
                    className="grid w-full grid-cols-[minmax(130px,1.15fr)_100px_64px_80px_80px_92px_minmax(190px,1.6fr)_96px] items-center text-left hover:bg-elevated/25"
                  >
                    <span className="px-4 py-3">
                      <span className="block font-medium text-foreground">{event.name || event.symbol}</span>
                      <span className="font-mono text-[10px] text-muted">{event.symbol}</span>
                    </span>
                    <span className="px-3 py-3"><StatusBadge status={event.status} /></span>
                    <span className="px-3 py-3 text-right font-mono tabular-nums text-secondary">{event.watch_day || '—'}/5</span>
                    <span className="px-3 py-3 text-right font-mono tabular-nums text-foreground">{price(event.last_price_raw)}</span>
                    <span className={`px-3 py-3 text-right font-mono tabular-nums ${
                      (distanceFrom(event.last_price_raw, event.t_high_raw) ?? 0) >= 0 ? 'text-emerald-300' : 'text-secondary'
                    }`}>
                      {pct(distanceFrom(event.last_price_raw, event.t_high_raw))}
                    </span>
                    <span className="px-3 py-3 text-right font-mono tabular-nums text-amber-300">
                      {pct(distanceFrom(event.last_price_raw, event.t_close_raw * 0.94))}
                    </span>
                    <span className="min-w-0 px-3 py-3">
                      <span className="flex items-center gap-1.5 text-foreground">
                        {event.trigger_rule ? `${event.trigger_rule} 组` : '等待触发'}
                        {event.status === 'BUY_PENDING' && <Clock3 size={12} className="text-amber-300" />}
                        {event.status === 'FILLED' && <CheckCircle2 size={12} className="text-emerald-300" />}
                        {event.drop_reason && <ShieldAlert size={12} className="text-rose-300" />}
                      </span>
                      <span className="mt-0.5 block truncate text-[10px] text-muted">
                        {event.drop_reason || event.pending?.reason || (event.fill_time ? `成交确认 ${shortTime(event.fill_time)}` : 'A/B/C/D 任一完成 K 触发')}
                      </span>
                    </span>
                    <span className="flex items-center justify-end gap-2 px-3 py-3 text-[10px] text-muted">
                      {shortTime(event.last_observed_at)}
                      <ChevronDown size={13} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
                    </span>
                  </button>
                  {open && <EventDetail event={event} onPreview={onPreview} onReset={onReset} onRemove={onRemove} busy={busy} />}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function MobileCards({
  events,
  selected,
  onSelect,
  onPreview,
  onReset,
  onRemove,
  busy,
}: {
  events: WatchEvent[]
  selected: string
  onSelect: (id: string) => void
  onPreview: (event: WatchEvent) => void
  onReset: (id: string) => void
  onRemove: (id: string) => void
  busy: boolean
}) {
  return (
    <div className="space-y-2 lg:hidden">
      {events.map(event => {
        const open = selected === event.event_id
        return (
          <article key={event.event_id} className="overflow-hidden rounded-xl border border-border bg-surface">
            <button type="button" onClick={() => onSelect(event.event_id)} className="w-full p-3.5 text-left">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="font-medium text-foreground">{event.name || event.symbol}</div>
                  <div className="font-mono text-[10px] text-muted">{event.symbol} · T {event.event_date}</div>
                </div>
                <StatusBadge status={event.status} />
              </div>
              <div className="mt-3 grid grid-cols-3 gap-2">
                <div className="rounded-lg bg-elevated/45 p-2">
                  <div className="text-[9px] text-muted">最新价</div>
                  <div className="mt-1 font-mono text-sm text-foreground">{price(event.last_price_raw)}</div>
                </div>
                <div className="rounded-lg bg-elevated/45 p-2">
                  <div className="text-[9px] text-muted">距 T 高</div>
                  <div className="mt-1 font-mono text-sm text-secondary">{pct(distanceFrom(event.last_price_raw, event.t_high_raw))}</div>
                </div>
                <div className="rounded-lg bg-elevated/45 p-2">
                  <div className="text-[9px] text-muted">观察日</div>
                  <div className="mt-1 font-mono text-sm text-secondary">{event.watch_day || '—'}/5</div>
                </div>
              </div>
              <div className="mt-2.5 flex items-center justify-between gap-2 text-[10px] text-muted">
                <span>{event.trigger_rule ? `${event.trigger_rule} 组 · ${event.pending?.reason || event.drop_reason || '已记录'}` : '等待 A/B/C/D 触发'}</span>
                <ChevronDown size={13} className={`shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
              </div>
            </button>
            {open && <EventDetail event={event} onPreview={onPreview} onReset={onReset} onRemove={onRemove} busy={busy} />}
          </article>
        )
      })}
    </div>
  )
}

function LocalKlineDialog({
  target,
  navList,
  onNavigate,
  onClose,
}: {
  target: PreviewTarget | null
  navList: NavItem[]
  onNavigate: (target: PreviewTarget) => void
  onClose: () => void
}) {
  const [months, setMonths] = useState(6)
  const [view, setView] = useState<KlineView>('daily')
  const [intradayDays, setIntradayDays] = useState<number>(INTRADAY_RANGES[0])
  const dateRange = useMemo(() => rangeForMonths(months), [months])
  if (!target) return null

  const index = navList.findIndex(item => item.symbol === target.symbol)
  const move = (offset: number) => {
    if (navList.length === 0 || index < 0) return
    const next = navList[(index + offset + navList.length) % navList.length]
    onNavigate({ symbol: next.symbol, name: next.name })
  }

  return (
    <Modal
      onClose={onClose}
      labelledBy="first-board-right-tail-kline-title"
      panelClassName="flex max-h-[92vh] w-[94vw] max-w-6xl flex-col overflow-hidden rounded-card border border-border bg-surface shadow-2xl"
    >
      <div className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-2 border-b border-border px-4 py-3">
        <div className="flex min-w-0 items-center gap-2">
          <span id="first-board-right-tail-kline-title" className="truncate text-sm font-semibold text-foreground">
            {target.name ? `${target.name} · ${target.symbol}` : target.symbol}
          </span>
          <span className="rounded-full border border-emerald-400/25 bg-emerald-400/10 px-2 py-0.5 text-[10px] text-emerald-300">
            {view === 'daily' ? '本地日线优先' : '分时按需加载'}
          </span>
        </div>
        <div className="flex w-full flex-wrap items-center gap-1.5 sm:ml-auto sm:w-auto sm:justify-end">
          <button
            type="button"
            onClick={() => move(-1)}
            disabled={navList.length < 2}
            aria-label="上一只"
            className="shrink-0 rounded-btn border border-border bg-elevated p-1.5 text-secondary hover:text-foreground disabled:opacity-35"
          >
            <ChevronLeft size={15} />
          </button>
          <span className="min-w-10 text-center font-mono text-[10px] text-muted">
            {index >= 0 ? index + 1 : '—'} / {navList.length}
          </span>
          <button
            type="button"
            onClick={() => move(1)}
            disabled={navList.length < 2}
            aria-label="下一只"
            className="shrink-0 rounded-btn border border-border bg-elevated p-1.5 text-secondary hover:text-foreground disabled:opacity-35"
          >
            <ChevronRight size={15} />
          </button>
          <span className="mx-1 h-4 w-px bg-border" />
          <div className="inline-flex shrink-0 items-center rounded-btn border border-border bg-base/60 p-0.5">
            <button
              type="button"
              onClick={() => setView('daily')}
              className={`inline-flex items-center gap-1 whitespace-nowrap rounded px-2.5 py-1 text-[11px] ${
                view === 'daily' ? 'bg-accent/20 text-accent' : 'text-muted hover:text-foreground'
              }`}
            >
              <LineChart size={12} /> 日 K
            </button>
            <button
              type="button"
              onClick={() => setView('intraday')}
              className={`inline-flex items-center gap-1 whitespace-nowrap rounded px-2.5 py-1 text-[11px] ${
                view === 'intraday' ? 'bg-accent/20 text-accent' : 'text-muted hover:text-foreground'
              }`}
            >
              <Clock3 size={12} /> 分时
            </button>
          </div>
          {view === 'daily'
            ? KLINE_RANGES.map(range => (
                <button
                  key={range.key}
                  type="button"
                  onClick={() => setMonths(range.key)}
                  className={`whitespace-nowrap rounded-btn px-2.5 py-1.5 text-[11px] ${
                    months === range.key ? 'bg-accent text-white' : 'bg-elevated/55 text-secondary hover:text-foreground'
                  }`}
                >
                  {range.label}
                </button>
              ))
            : INTRADAY_RANGES.map(days => (
                <button
                  key={days}
                  type="button"
                  onClick={() => setIntradayDays(days)}
                  className={`whitespace-nowrap rounded-btn px-2.5 py-1.5 text-[11px] ${
                    intradayDays === days ? 'bg-accent text-white' : 'bg-elevated/55 text-secondary hover:text-foreground'
                  }`}
                >
                  {days}日
                </button>
              ))}
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭 K 线"
            className="ml-1 rounded-btn p-1.5 text-secondary hover:bg-elevated hover:text-foreground"
          >
            <X size={16} />
          </button>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-3">
        {view === 'daily' ? (
          <Suspense
            fallback={
              <div className="flex min-h-96 items-center justify-center gap-2 text-xs text-secondary">
                <Loader2 size={15} className="animate-spin text-accent" /> 正在加载本地日线…
              </div>
            }
          >
            <StockDailyKChart
              symbol={target.symbol}
              dateRange={dateRange}
              height={520}
              visibleBars={80}
              showIndicatorControls
              showLimitMarkers
              showMarkerToggle={false}
            />
          </Suspense>
        ) : (
          <Suspense
            fallback={
              <div className="flex min-h-96 items-center justify-center gap-2 text-xs text-secondary">
                <Loader2 size={15} className="animate-spin text-accent" /> 正在加载分时组件…
              </div>
            }
          >
            <StockMultiDayIntradayChart
              symbol={target.symbol}
              days={intradayDays}
              height={520}
            />
          </Suspense>
        )}
        <p className="px-1 pt-2 text-[10px] leading-4 text-muted">
          {view === 'daily'
            ? '日 K 默认读取本地 enriched 数据，本地存在时不会请求远端行情。'
            : '分时只在切换到当前页后读取；切换标的时再取新标的，不提前预取相邻股票。'}
        </p>
      </div>
    </Modal>
  )
}

export function FirstBoardRightTail() {
  const queryClient = useQueryClient()
  const [filter, setFilter] = useState<Filter>('active')
  const [selected, setSelected] = useState('')
  const [preview, setPreview] = useState<PreviewTarget | null>(null)
  const overview = useQuery({
    queryKey: client.key,
    queryFn: client.overview,
    refetchInterval: 10_000,
    refetchIntervalInBackground: false,
    staleTime: 4_000,
  })
  const refresh = () => queryClient.invalidateQueries({ queryKey: client.key })
  const importMut = useMutation({
    mutationFn: client.importLatest,
    onSuccess: data => {
      toast(`已导入 ${data.imported} 只首板，观察池共 ${data.total} 只`, 'success')
      void refresh()
    },
    onError: error => toast(error.message),
  })
  const evaluateMut = useMutation({
    mutationFn: client.evaluate,
    onSuccess: data => {
      toast(data.count ? `本次产生 ${data.count} 条状态变化` : '本次没有新的触发', 'success')
      void refresh()
    },
    onError: error => toast(error.message),
  })
  const simpleRuleMut = useMutation({
    mutationFn: client.seedSimple,
    onSuccess: () => {
      toast('已同步到监控中心，可在监控页继续维护', 'success')
      void queryClient.invalidateQueries({ queryKey: ['monitor-rules'] })
    },
    onError: error => toast(error.message),
  })
  const resetMut = useMutation({
    mutationFn: client.reset,
    onSuccess: () => {
      setSelected('')
      toast('事件状态已重置', 'success')
      void refresh()
    },
    onError: error => toast(error.message),
  })
  const removeMut = useMutation({
    mutationFn: client.remove,
    onSuccess: () => {
      setSelected('')
      toast('已移出观察池', 'success')
      void refresh()
    },
    onError: error => toast(error.message),
  })

  const data = overview.data
  const events = useMemo(
    () => [...(data?.events ?? [])]
      .filter(event => statusMatches(event, filter))
      .sort((a, b) => {
        const rank: Record<EventStatus, number> = { BUY_PENDING: 0, WATCH: 1, FILLED: 2, DROPPED: 3 }
        return rank[a.status] - rank[b.status] || String(b.last_observed_at ?? '').localeCompare(String(a.last_observed_at ?? ''))
      }),
    [data?.events, filter],
  )
  const busy = importMut.isPending || evaluateMut.isPending || simpleRuleMut.isPending || resetMut.isPending || removeMut.isPending
  const activeCount = (data?.summary.watching ?? 0) + (data?.summary.pending ?? 0)
  const previewNavList = useMemo<NavItem[]>(() => toNavItems(events), [events])

  return (
    <div className="min-h-full bg-base">
      <PageHeader title="首板右尾观察池" subtitle="T+1 至 T+5 动态触发 · 信号后下一分钟确认 · 不自动下单" />
      <main className="mx-auto max-w-[1560px] space-y-4 p-3 lg:p-5">
        <section className="relative overflow-hidden rounded-2xl border border-border bg-surface">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_12%_20%,rgba(34,211,238,0.16),transparent_34%),radial-gradient(circle_at_82%_90%,rgba(245,158,11,0.12),transparent_34%)]" />
          <div className="relative grid gap-5 p-4 lg:grid-cols-[1.35fr_0.65fr] lg:p-5">
            <div>
              <div className="flex items-center gap-2 text-[10px] font-medium uppercase tracking-[0.18em] text-cyan-300">
                <Target size={14} /> Board Breakout Watch
              </div>
              <h1 className="mt-2 max-w-3xl text-2xl font-semibold leading-tight text-foreground lg:text-3xl">
                不猜买入时间，只等条件出现。
              </h1>
              <p className="mt-2 max-w-3xl text-xs leading-6 text-secondary">
                首板确认后进入观察池，A/B/C/D 在连续竞价期间独立触发。信号只代表“下一分钟观察可成交性”，
                一字板、涨停锁死、无量或超过容量时不会把理想价记成成交。
              </p>
              <div className="mt-3 flex flex-wrap gap-2 text-[10px]">
                <span className="rounded-full border border-cyan-400/20 bg-cyan-400/5 px-2.5 py-1 text-cyan-300">首板重算，不信任旧连板列</span>
                <span className="rounded-full border border-amber-400/20 bg-amber-400/5 px-2.5 py-1 text-amber-300">-6% 放弃线</span>
                <span className="rounded-full border border-border bg-elevated/50 px-2.5 py-1 text-muted">{data?.algorithm_version ?? '加载中'}</span>
              </div>
            </div>
            <div className="rounded-xl border border-border/80 bg-base/55 p-3.5 backdrop-blur-sm">
              <div className="flex items-center justify-between text-[10px] uppercase tracking-[0.14em] text-muted">
                <span>运行状态</span>
                <span className={(data?.runtime.minute_status === 'ok') ? 'text-emerald-300' : 'text-amber-300'}>
                  {data?.runtime.minute_status === 'ok' ? '分钟数据正常' : '等待分钟数据'}
                </span>
              </div>
              <div className="mt-3 space-y-2 text-xs">
                <div className="flex justify-between gap-3"><span className="text-muted">数据截至</span><span className="font-mono text-foreground">{data?.as_of ?? '—'}</span></div>
                <div className="flex justify-between gap-3"><span className="text-muted">最近检查</span><span className="font-mono text-secondary">{shortTime(data?.runtime.last_evaluation)}</span></div>
                <div className="flex justify-between gap-3"><span className="text-muted">活动标的</span><span className="font-mono text-secondary">{data?.runtime.active_symbols ?? activeCount}</span></div>
                <div className="flex justify-between gap-3"><span className="text-muted">实时行情</span><span className={data?.runtime.realtime_enabled ? 'text-emerald-300' : 'text-rose-300'}>{data?.runtime.realtime_enabled ? `已开启 · ${data?.runtime.quote_interval ?? '—'}s` : '未开启'}</span></div>
                <div className="flex justify-between gap-3"><span className="text-muted">竞价表</span><span className={data?.runtime.d_available ? 'text-emerald-300' : 'text-amber-300'}>{data?.runtime.d_available ? 'D 可用' : 'D 缺历史或当日数据'}</span></div>
              </div>
            </div>
          </div>
        </section>

        {data && data.runtime.realtime_enabled === false && (
          <section className="flex flex-col gap-2 rounded-xl border border-rose-400/30 bg-rose-400/5 px-4 py-3 text-xs text-secondary sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-2">
              <AlertTriangle size={15} className="mt-0.5 shrink-0 text-rose-300" />
              <span>实时行情当前关闭。观察池会保留状态，但后台不会收到新行情，也不会产生新的买卖点告警。</span>
            </div>
            <Link to="/settings" className="shrink-0 text-rose-300 hover:underline">去设置开启实时行情</Link>
          </section>
        )}

        <section className="grid grid-cols-2 gap-2 lg:grid-cols-4">
          <StatCard label="观察中" value={data?.summary.watching ?? 0} hint="等待任一规则首次成立" icon={Gauge} />
          <StatCard label="待成交确认" value={data?.summary.pending ?? 0} hint="信号已完成，等待下一分钟" icon={Clock3} />
          <StatCard label="已确认买点" value={data?.summary.filled ?? 0} hint="同一事件不再重复入场" icon={CircleDollarSign} />
          <StatCard label="已放弃" value={data?.summary.dropped ?? 0} hint="-6% / 超时 / 连续一字" icon={ShieldAlert} />
        </section>

        <RuleStrip rules={data?.rules ?? {}} runtime={data?.runtime ?? {}} />

        <section className="rounded-xl border border-border bg-surface">
          <div className="flex flex-col gap-3 border-b border-border p-3.5 xl:flex-row xl:items-center xl:justify-between">
            <div className="flex flex-wrap items-center gap-1.5">
              {FILTERS.map(item => (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => setFilter(item.key)}
                  className={`rounded-btn px-2.5 py-1.5 text-[11px] transition-colors ${
                    filter === item.key ? 'bg-accent text-white' : 'bg-elevated/45 text-secondary hover:text-foreground'
                  }`}
                >
                  {item.label}
                </button>
              ))}
              <span className="ml-1 font-mono text-[10px] text-muted">{events.length} / {data?.summary.total ?? 0}</span>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => importMut.mutate()}
                disabled={busy}
                className="inline-flex h-8 items-center gap-1.5 rounded-btn bg-accent px-3 text-[11px] font-medium text-white disabled:opacity-50"
              >
                {importMut.isPending ? <Loader2 size={13} className="animate-spin" /> : <Import size={13} />}
                导入最新首板
              </button>
              <button
                type="button"
                onClick={() => evaluateMut.mutate()}
                disabled={busy || activeCount === 0}
                className="inline-flex h-8 items-center gap-1.5 rounded-btn border border-border bg-elevated px-3 text-[11px] text-secondary hover:text-foreground disabled:opacity-50"
              >
                {evaluateMut.isPending ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />}
                立即检查
              </button>
              <button
                type="button"
                onClick={() => simpleRuleMut.mutate()}
                disabled={busy || activeCount === 0}
                className="inline-flex h-8 items-center gap-1.5 rounded-btn border border-cyan-400/25 bg-cyan-400/5 px-3 text-[11px] text-cyan-300 disabled:opacity-50"
              >
                {simpleRuleMut.isPending ? <Loader2 size={13} className="animate-spin" /> : <BellRing size={13} />}
                同步简化告警
              </button>
              <Link
                to="/monitor"
                className="inline-flex h-8 items-center gap-1.5 rounded-btn border border-border bg-elevated px-3 text-[11px] text-secondary hover:text-foreground"
              >
                监控中心 <ArrowUpRight size={13} />
              </Link>
              <button
                type="button"
                onClick={() => void overview.refetch()}
                disabled={overview.isFetching}
                aria-label="刷新观察池"
                className="inline-flex h-8 w-8 items-center justify-center rounded-btn border border-border bg-elevated text-secondary hover:text-foreground disabled:opacity-50"
              >
                <RefreshCw size={13} className={overview.isFetching ? 'animate-spin' : ''} />
              </button>
            </div>
          </div>

          {overview.isLoading ? (
            <div className="flex min-h-56 items-center justify-center gap-3 text-sm text-secondary">
              <Loader2 size={18} className="animate-spin text-accent" /> 正在读取观察池…
            </div>
          ) : overview.isError ? (
            <div className="flex min-h-56 flex-col items-center justify-center gap-3 px-5 text-center">
              <AlertTriangle size={22} className="text-rose-300" />
              <div className="text-sm text-foreground">观察服务读取失败</div>
              <div className="max-w-xl text-xs text-muted">{overview.error.message}</div>
              <button type="button" onClick={() => void overview.refetch()} className="rounded-btn bg-elevated px-3 py-1.5 text-xs text-secondary">重试</button>
            </div>
          ) : events.length === 0 ? (
            <div className="flex min-h-56 flex-col items-center justify-center gap-3 px-5 text-center">
              <div className="rounded-full border border-cyan-400/20 bg-cyan-400/5 p-3 text-cyan-300"><TrendingUp size={22} /></div>
              <div className="text-sm font-medium text-foreground">{data?.summary.total ? '当前筛选没有事件' : '观察池还是空的'}</div>
              <div className="max-w-lg text-xs leading-5 text-muted">
                {data?.summary.total
                  ? '切换上方状态筛选查看其他事件。'
                  : '先按最新日线重算首板。识别不使用旧 consecutive_limit_ups 列。'}
              </div>
              {!data?.summary.total && (
                <button type="button" onClick={() => importMut.mutate()} disabled={busy} className="inline-flex items-center gap-2 rounded-btn bg-accent px-3 py-2 text-xs text-white disabled:opacity-50">
                  <Import size={14} /> 识别并导入最新首板
                </button>
              )}
            </div>
          ) : (
            <>
              <DesktopTable
                events={events}
                selected={selected}
                onSelect={id => setSelected(value => value === id ? '' : id)}
                onPreview={event => setPreview({ symbol: event.symbol, name: event.name ?? undefined })}
                onReset={resetMut.mutate}
                onRemove={removeMut.mutate}
                busy={busy}
              />
              <div className="p-2.5 lg:hidden">
                <MobileCards
                  events={events}
                  selected={selected}
                  onSelect={id => setSelected(value => value === id ? '' : id)}
                  onPreview={event => setPreview({ symbol: event.symbol, name: event.name ?? undefined })}
                  onReset={resetMut.mutate}
                  onRemove={removeMut.mutate}
                  busy={busy}
                />
              </div>
            </>
          )}
        </section>

        <section className="grid gap-3 lg:grid-cols-[1.2fr_0.8fr]">
          <div className="rounded-xl border border-amber-400/25 bg-amber-400/5 p-4 text-xs leading-6 text-secondary">
            <div className="flex items-center gap-2 font-medium text-amber-300"><AlertTriangle size={15} />这里显示的是研究观察状态</div>
            <p className="mt-1.5">
              “已确认买点”只表示信号后下一分钟存在有效开盘价且未被一字板锁死，不代表真实账户已成交，也不包含排队和完整冲击成本。
              回测、标签和组合验收仍未完成，本页不构成收益结论。
            </p>
          </div>
          <div className="rounded-xl border border-border bg-surface p-4 text-xs leading-6 text-secondary">
            <div className="flex items-center gap-2 font-medium text-foreground"><CheckCircle2 size={15} className="text-emerald-300" />简化告警做什么</div>
            <p className="mt-1.5">
              同步后在现有监控中心生成两条显式标的规则：价格上穿昨收、价格上穿 VWAP。
              它们只做早期提示；完整的 T+1～T+5、-6% 放弃线、A/B/C/D 和一次成交约束以本页状态为准。
            </p>
          </div>
        </section>
      </main>
      <LocalKlineDialog
        target={preview}
        navList={previewNavList}
        onNavigate={setPreview}
        onClose={() => setPreview(null)}
      />
    </div>
  )
}

const extension: FrontendExtension = {
  id: 'official.first-board-right-tail',
  apiVersion: 1,
  routes: [
    { id: 'first-board-right-tail', path: '/first-board-right-tail', component: FirstBoardRightTail },
  ],
  navigation: [
    {
      id: 'first-board-right-tail',
      routeId: 'first-board-right-tail',
      label: '首板右尾',
      icon: Target,
      order: 460,
    },
  ],
}

export default extension
