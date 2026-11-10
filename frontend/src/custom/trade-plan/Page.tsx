import { useDeferredValue, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ChevronRight,
  ClipboardList,
  Plus,
  RefreshCw,
  Sparkles,
  Target,
} from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { EmptyState } from '@/components/EmptyState'
import { toast } from '@/components/Toast'
import { cn } from '@/lib/cn'
import { cnToday } from '@/lib/kline'
import { PlanForm } from './PlanForm'
import { PlanDetail } from './PlanDetail'
import { Analytics } from './Analytics'
import { AiReview } from './AiReview'
import { tradePlanApi, tradePlanKeys, type PlanFilters } from './client'
import {
  MOOD_LABEL,
  SETUP_LABEL,
  STATUS_CLASS,
  STATUS_LABEL,
  type PlanStatus,
  type SetupType,
  type TradePlan,
  type TradePlanPayload,
  type TradeStats,
} from './types'

type Tab = 'plans' | 'analytics' | 'ai'
type RangePreset = 'today' | '7d' | '30d' | 'all'

function addDays(day: string, delta: number): string {
  const date = new Date(`${day}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() + delta)
  return date.toISOString().slice(0, 10)
}

function rangeOf(preset: RangePreset): { start?: string; end?: string } {
  if (preset === 'all') return {}
  const today = cnToday()
  if (preset === 'today') return { start: today, end: today }
  return { start: addDays(today, preset === '7d' ? -6 : -29), end: today }
}

function pctPoint(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  return `${v > 0 ? '+' : ''}${v.toFixed(2)}%`
}

function rText(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  return `${v > 0 ? '+' : ''}${v.toFixed(2)}R`
}

function payloadOf(plan: TradePlan): TradePlanPayload {
  return {
    plan_date: plan.plan_date,
    symbol: plan.symbol,
    name: plan.name,
    setup: plan.setup,
    market_mood: plan.market_mood,
    confidence: plan.confidence,
    planned_hold: plan.planned_hold,
    thesis: plan.thesis,
    trigger: plan.trigger,
    invalidation: plan.invalidation,
    planned_entry_low: plan.planned_entry_low,
    planned_entry_high: plan.planned_entry_high,
    stop_loss: plan.stop_loss,
    target_price: plan.target_price,
    planned_position_pct: plan.planned_position_pct,
    status: plan.status,
    actual_entry_price: plan.actual_entry_price,
    entry_at: plan.entry_at,
    actual_position_pct: plan.actual_position_pct,
    actual_exit_price: plan.actual_exit_price,
    exit_at: plan.exit_at,
    exit_reason: plan.exit_reason,
    review: plan.review,
    tags: plan.tags,
  }
}

function StatCard({ label, value, sub, tone }: {
  label: string
  value: string
  sub?: string
  tone?: string
}) {
  return (
    <div className="rounded-card border border-border bg-surface px-3.5 py-2.5">
      <div className="text-[10px] text-muted">{label}</div>
      <div className={cn('mt-0.5 font-mono text-lg font-semibold', tone ?? 'text-foreground')}>{value}</div>
      {sub && <div className="mt-0.5 text-[9px] text-muted">{sub}</div>}
    </div>
  )
}

function StatsStrip({ stats }: { stats: TradeStats }) {
  return (
    <div className="grid grid-cols-2 gap-2 px-4 pt-3 md:grid-cols-5">
      <StatCard
        label="计划 / 执行率"
        value={String(stats.total)}
        sub={stats.execution_rate == null ? '无执行样本' : `执行率 ${stats.execution_rate.toFixed(0)}%`}
      />
      <StatCard
        label="胜率"
        value={stats.win_rate == null ? '—' : `${stats.win_rate.toFixed(0)}%`}
        sub={`${stats.closed} 笔已结束`}
      />
      <StatCard
        label="平均单笔"
        value={pctPoint(stats.avg_pnl_pct)}
        sub={`累计 ${pctPoint(stats.total_pnl_pct)}`}
        tone={(stats.avg_pnl_pct ?? 0) > 0 ? 'text-bull' : (stats.avg_pnl_pct ?? 0) < 0 ? 'text-bear' : undefined}
      />
      <StatCard
        label="平均 R"
        value={stats.avg_r == null ? '—' : stats.avg_r.toFixed(2)}
        sub={stats.total_r == null ? '无 R 样本' : `累计 ${stats.total_r.toFixed(2)}R`}
        tone={(stats.avg_r ?? 0) > 0 ? 'text-bull' : (stats.avg_r ?? 0) < 0 ? 'text-bear' : undefined}
      />
      <StatCard
        label="纪律分"
        value={stats.discipline_score == null ? '—' : stats.discipline_score.toFixed(0)}
        sub={`追高 ${stats.chase_count} · 破止损 ${stats.stop_breach_count}`}
        tone={
          stats.discipline_score == null ? undefined
            : stats.discipline_score >= 80 ? 'text-success'
              : stats.discipline_score >= 50 ? 'text-warning' : 'text-danger'
        }
      />
    </div>
  )
}

function PlanRow({ plan, onOpen, onMiss }: {
  plan: TradePlan
  onOpen: () => void
  onMiss: () => void
}) {
  const m = plan.metrics
  const flags = plan.flags.slice(0, 2)
  return (
    <div
      onClick={onOpen}
      className="group grid cursor-pointer grid-cols-[104px_minmax(140px,1.2fr)_minmax(170px,1.5fr)_minmax(130px,1.2fr)_88px_84px_78px] items-center gap-2 border-b border-border/50 px-3 py-2 transition-colors hover:bg-elevated/35"
    >
      <div>
        <div className="font-mono text-[10px] text-secondary">{plan.plan_date.slice(5)}</div>
        <div className="mt-0.5 truncate text-[9px] text-muted">
          {SETUP_LABEL[plan.setup]} · {MOOD_LABEL[plan.market_mood]}
        </div>
      </div>
      <div className="min-w-0">
        <div className="truncate text-[12px] font-medium text-foreground">{plan.name || plan.symbol}</div>
        <div className="mt-0.5 flex items-center gap-1.5">
          <span className="font-mono text-[9px] text-muted">{plan.symbol}</span>
          {plan.tags.slice(0, 1).map(tag => (
            <span key={tag} className="truncate rounded-full bg-elevated px-1.5 py-px text-[8px] text-muted">{tag}</span>
          ))}
        </div>
      </div>
      <div className="font-mono text-[10px] text-secondary">
        <div>
          {plan.planned_entry_low?.toFixed(2) ?? '—'}–{plan.planned_entry_high?.toFixed(2) ?? '—'}
        </div>
        <div className="mt-0.5 text-[9px] text-muted">
          损 {plan.stop_loss?.toFixed(2) ?? '—'} · 标 {plan.target_price?.toFixed(2) ?? '—'}
        </div>
      </div>
      <div className="font-mono text-[10px] text-secondary">
        <div>
          {plan.actual_entry_price?.toFixed(2) ?? '—'} → {plan.actual_exit_price?.toFixed(2) ?? '—'}
        </div>
        <div className={cn('mt-0.5 text-[9px]', (m.entry_deviation_pct ?? 0) > 0 ? 'text-warning' : 'text-muted')}>
          偏离 {pctPoint(m.entry_deviation_pct)}
        </div>
      </div>
      <div className="text-right">
        <div className={cn('font-mono text-[12px] font-semibold', (m.pnl_pct ?? 0) > 0 ? 'text-bull' : (m.pnl_pct ?? 0) < 0 ? 'text-bear' : 'text-muted')}>
          {pctPoint(m.pnl_pct)}
        </div>
        <div className="mt-0.5 font-mono text-[9px] text-muted">{rText(m.r_multiple)}</div>
      </div>
      <div className="flex flex-wrap justify-end gap-1">
        {flags.length === 0 && plan.status === 'exited' && (
          <span className="rounded-full bg-success/10 px-1.5 py-0.5 text-[8px] text-success">无偏差</span>
        )}
        {flags.map(flag => (
          <span
            key={flag.code}
            className={cn(
              'rounded-full px-1.5 py-0.5 text-[8px]',
              flag.tone === 'danger' && 'bg-danger/10 text-danger',
              flag.tone === 'warn' && 'bg-warning/10 text-warning',
              flag.tone === 'info' && 'bg-accent/10 text-accent',
              flag.tone === 'muted' && 'bg-elevated text-muted',
            )}
          >
            {flag.label}
          </span>
        ))}
      </div>
      <div className="flex items-center justify-end gap-1">
        {plan.status === 'planned' && (
          <button
            onClick={event => {
              event.stopPropagation()
              onMiss()
            }}
            className="rounded px-1.5 py-0.5 text-[9px] text-muted opacity-0 transition-opacity hover:bg-warning/10 hover:text-warning group-hover:opacity-100"
          >
            未执行
          </button>
        )}
        <span className={cn('rounded-full border px-1.5 py-0.5 text-[9px]', STATUS_CLASS[plan.status])}>
          {STATUS_LABEL[plan.status]}
        </span>
        <ChevronRight className="h-3 w-3 text-muted/50" />
      </div>
    </div>
  )
}

function PlanList({ plans, onOpen, onMiss }: {
  plans: TradePlan[]
  onOpen: (plan: TradePlan) => void
  onMiss: (plan: TradePlan) => void
}) {
  const groups = useMemo(() => {
    const map = new Map<string, TradePlan[]>()
    for (const plan of plans) {
      const list = map.get(plan.plan_date) ?? []
      list.push(plan)
      map.set(plan.plan_date, list)
    }
    return [...map.entries()]
  }, [plans])

  return (
    <div className="overflow-x-auto">
      <div className="min-w-[880px]">
        <div className="grid grid-cols-[104px_minmax(140px,1.2fr)_minmax(170px,1.5fr)_minmax(130px,1.2fr)_88px_84px_78px] gap-2 border-b border-border bg-elevated/20 px-3 py-1.5 text-[9px] text-muted">
          <span>日期 / 模式</span><span>标的</span><span>计划区间</span><span>实际</span>
          <span className="text-right">收益</span><span className="text-right">偏差</span><span className="text-right">状态</span>
        </div>
        {groups.map(([date, items]) => (
          <div key={date}>
            <div className="flex items-center justify-between border-b border-border/60 bg-base/40 px-3 py-1.5">
              <span className="font-mono text-[10px] text-secondary">{date}</span>
              <span className="text-[9px] text-muted">{items.length} 条计划</span>
            </div>
            {items.map(plan => (
              <PlanRow
                key={plan.id}
                plan={plan}
                onOpen={() => onOpen(plan)}
                onMiss={() => onMiss(plan)}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}

export function TradePlanPage() {
  const qc = useQueryClient()
  const [tab, setTab] = useState<Tab>('plans')
  const [preset, setPreset] = useState<RangePreset>('30d')
  const [setup, setSetup] = useState<SetupType | ''>('')
  const [status, setStatus] = useState<PlanStatus | ''>('')
  const [search, setSearch] = useState('')
  const query = useDeferredValue(search)
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<TradePlan | null>(null)
  const [detail, setDetail] = useState<TradePlan | null>(null)

  const range = rangeOf(preset)
  const filters: PlanFilters = { ...range, setup, status, q: query }
  const plansQ = useQuery({
    queryKey: tradePlanKeys.list(filters),
    queryFn: () => tradePlanApi.list(filters),
    placeholderData: previous => previous,
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: ['custom', 'trade-plan'] })

  const missMut = useMutation({
    mutationFn: (plan: TradePlan) => tradePlanApi.update(plan.id, { ...payloadOf(plan), status: 'missed' }),
    onSuccess: () => {
      invalidate()
      toast('已标记未执行', 'success')
    },
    onError: (error: any) => toast(error?.message || '操作失败', 'error'),
  })

  const deleteMut = useMutation({
    mutationFn: (planId: string) => tradePlanApi.remove(planId),
    onSuccess: () => {
      setDetail(null)
      invalidate()
      toast('计划已删除', 'success')
    },
    onError: (error: any) => toast(error?.message || '删除失败', 'error'),
  })

  const stats = plansQ.data?.stats
  const plans = plansQ.data?.plans ?? []

  return (
    <div className="flex h-full min-h-0 flex-col">
      <PageHeader
        title="交易计划"
        titleExtra={<span className="rounded-full border border-accent/25 bg-accent/10 px-2 py-0.5 text-[9px] text-accent">超短</span>}
        right={(
          <div className="flex items-center gap-1.5">
            <button
              onClick={() => { setEditing(null); setFormOpen(true) }}
              className="inline-flex h-7 items-center gap-1.5 rounded-btn bg-accent px-3 text-[11px] font-medium text-white hover:bg-accent/90"
            >
              <Plus className="h-3.5 w-3.5" /> 新建计划
            </button>
            <button
              onClick={() => plansQ.refetch()}
              className="rounded-btn border border-border p-1.5 text-muted hover:bg-elevated hover:text-foreground"
              title="刷新"
            >
              <RefreshCw className={cn('h-3.5 w-3.5', plansQ.isFetching && 'animate-spin')} />
            </button>
          </div>
        )}
      />

      <div className="flex items-center gap-1 border-b border-border px-4 py-2">
        {([
          ['plans', '计划', ClipboardList],
          ['analytics', '执行分析', Target],
          ['ai', 'AI 复盘', Sparkles],
        ] as const).map(([key, label, Icon]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-btn px-2.5 py-1 text-[11px] transition-colors',
              tab === key ? 'bg-accent/10 text-accent' : 'text-secondary hover:bg-elevated hover:text-foreground',
            )}
          >
            <Icon className="h-3.5 w-3.5" /> {label}
          </button>
        ))}
      </div>

      {stats && <StatsStrip stats={stats} />}

      <div className="flex flex-wrap items-center gap-2 px-4 py-2">
        <div className="flex rounded-btn border border-border p-0.5">
          {([
            ['today', '今日'],
            ['7d', '近 7 日'],
            ['30d', '近 30 日'],
            ['all', '全部'],
          ] as const).map(([key, label]) => (
            <button
              key={key}
              onClick={() => setPreset(key)}
              className={cn(
                'rounded px-2 py-1 text-[10px] transition-colors',
                preset === key ? 'bg-elevated text-foreground' : 'text-muted hover:text-foreground',
              )}
            >
              {label}
            </button>
          ))}
        </div>
        <select
          value={setup}
          onChange={event => setSetup(event.target.value as SetupType | '')}
          className="h-7 rounded-btn border border-border bg-base px-2 text-[10px] text-secondary outline-none focus:border-accent/60"
        >
          <option value="">全部模式</option>
          {Object.entries(SETUP_LABEL).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
        </select>
        <select
          value={status}
          onChange={event => setStatus(event.target.value as PlanStatus | '')}
          className="h-7 rounded-btn border border-border bg-base px-2 text-[10px] text-secondary outline-none focus:border-accent/60"
        >
          <option value="">全部状态</option>
          {Object.entries(STATUS_LABEL).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
        </select>
        <input
          value={search}
          onChange={event => setSearch(event.target.value)}
          placeholder="代码 / 名称 / 逻辑"
          className="h-7 min-w-40 flex-1 rounded-btn border border-border bg-base px-2.5 text-[11px] text-foreground outline-none focus:border-accent/60 sm:max-w-64"
        />
        <div className="ml-auto flex items-center gap-2 text-[9px] text-muted">
          {range.start && <span className="font-mono">{range.start} ~ {range.end}</span>}
          <span>{plans.length} 条</span>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-5">
        {plansQ.isLoading && (
          <div className="grid h-48 place-items-center text-[11px] text-muted">加载中…</div>
        )}
        {plansQ.isError && (
          <div className="mx-auto mt-10 max-w-md rounded-card border border-danger/30 bg-danger/5 p-4 text-center text-[11px] text-danger">
            {(plansQ.error as any)?.message || '加载失败'}
          </div>
        )}
        {!plansQ.isLoading && !plansQ.isError && (
          tab === 'plans' ? (
            plans.length > 0 ? (
              <div className="rounded-card border border-border bg-surface">
                <PlanList
                  plans={plans}
                  onOpen={setDetail}
                  onMiss={plan => missMut.mutate(plan)}
                />
              </div>
            ) : (
              <EmptyState
                icon={ClipboardList}
                title="还没有交易计划"
                hint="先记录一条盘前计划，再在执行后补上成交与离场。"
              />
            )
          ) : tab === 'analytics' ? (
            stats ? <Analytics stats={stats} /> : null
          ) : (
            <AiReview start={range.start} end={range.end} />
          )
        )}
      </div>

      {formOpen && (
        <PlanForm
          plan={editing}
          onClose={() => { setFormOpen(false); setEditing(null) }}
          onSaved={() => {
            invalidate()
            setFormOpen(false)
            setEditing(null)
          }}
        />
      )}

      {detail && (
        <PlanDetail
          plan={detail}
          onClose={() => setDetail(null)}
          onEdit={() => {
            setEditing(detail)
            setDetail(null)
            setFormOpen(true)
          }}
          onDelete={() => {
            if (window.confirm(`删除 ${detail.name || detail.symbol} 的计划？`)) {
              deleteMut.mutate(detail.id)
            }
          }}
        />
      )}
    </div>
  )
}
