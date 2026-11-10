import { Pencil, Trash2, X } from 'lucide-react'
import { Modal } from '@/components/Modal'
import { cn } from '@/lib/cn'
import { fmtPrice, priceColorClass } from '@/lib/format'
import {
  EXIT_REASON_LABEL,
  HOLD_LABEL,
  MOOD_LABEL,
  SETUP_LABEL,
  STATUS_CLASS,
  STATUS_LABEL,
  type TradePlan,
} from './types'

function pct(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  return `${v > 0 ? '+' : ''}${v.toFixed(2)}%`
}

function rMultiple(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  return `${v > 0 ? '+' : ''}${v.toFixed(2)}R`
}

function holdText(minutes: number | null | undefined): string {
  if (minutes == null) return '—'
  if (minutes < 60) return `${minutes} 分钟`
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  return rest ? `${hours} 小时 ${rest} 分` : `${hours} 小时`
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-btn border border-border bg-base/60 px-3 py-2">
      <div className="text-[9px] text-muted">{label}</div>
      <div className={cn('mt-0.5 font-mono text-[13px] font-semibold text-foreground', tone)}>{value}</div>
    </div>
  )
}

function PriceLadder({ plan }: { plan: TradePlan }) {
  const values = [
    plan.planned_entry_low,
    plan.planned_entry_high,
    plan.metrics.planned_entry_mid,
    plan.stop_loss,
    plan.target_price,
    plan.actual_entry_price,
    plan.actual_exit_price,
  ].filter((value): value is number => value != null && Number.isFinite(value))
  if (values.length === 0) return null

  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || max * 0.02 || 1
  const left = min - span * 0.08
  const right = max + span * 0.08
  const pos = (value: number) => ((value - left) / (right - left)) * 100
  const low = plan.planned_entry_low
  const high = plan.planned_entry_high

  return (
    <div className="rounded-btn border border-border bg-base/60 px-4 pb-8 pt-4">
      <div className="relative h-7">
        <div className="absolute left-0 right-0 top-3 h-px bg-border" />
        {low != null && high != null && (
          <div
            className="absolute top-1 h-4 rounded-sm border border-accent/45 bg-accent/15"
            style={{ left: `${pos(low)}%`, width: `${Math.max(pos(high) - pos(low), 0.8)}%` }}
          />
        )}
        {plan.stop_loss != null && (
          <div className="absolute top-0.5 h-6 w-px bg-bear" style={{ left: `${pos(plan.stop_loss)}%` }} />
        )}
        {plan.target_price != null && (
          <div className="absolute top-0.5 h-6 w-px bg-bull" style={{ left: `${pos(plan.target_price)}%` }} />
        )}
        {plan.actual_entry_price != null && (
          <div className="absolute top-1.5 h-4 w-1.5 -translate-x-1/2 rounded-sm bg-accent"
            style={{ left: `${pos(plan.actual_entry_price)}%` }} />
        )}
        {plan.actual_exit_price != null && (
          <div className="absolute top-1.5 h-4 w-1.5 -translate-x-1/2 rounded-sm bg-foreground"
            style={{ left: `${pos(plan.actual_exit_price)}%` }} />
        )}
      </div>
      <div className="relative mt-1 h-4 text-[9px] text-muted">
        {plan.stop_loss != null && (
          <span className="absolute -translate-x-1/2 text-bear" style={{ left: `${pos(plan.stop_loss)}%` }}>
            止损 {fmtPrice(plan.stop_loss)}
          </span>
        )}
        {plan.target_price != null && (
          <span className="absolute -translate-x-1/2 text-bull" style={{ left: `${pos(plan.target_price)}%` }}>
            目标 {fmtPrice(plan.target_price)}
          </span>
        )}
        {plan.actual_entry_price != null && (
          <span className="absolute -translate-x-1/2 text-accent" style={{ left: `${pos(plan.actual_entry_price)}%` }}>
            买 {fmtPrice(plan.actual_entry_price)}
          </span>
        )}
        {plan.actual_exit_price != null && (
          <span className="absolute -translate-x-1/2 text-foreground" style={{ left: `${pos(plan.actual_exit_price)}%` }}>
            卖 {fmtPrice(plan.actual_exit_price)}
          </span>
        )}
      </div>
    </div>
  )
}

function TextBlock({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] text-muted">{label}</div>
      <p className="mt-1 whitespace-pre-wrap text-[12px] leading-relaxed text-secondary">
        {value || '—'}
      </p>
    </div>
  )
}

export function PlanDetail({ plan, onClose, onEdit, onDelete }: {
  plan: TradePlan
  onClose: () => void
  onEdit: () => void
  onDelete: () => void
}) {
  const m = plan.metrics
  return (
    <Modal
      onClose={onClose}
      labelledBy="trade-plan-detail-title"
      panelClassName="w-[94vw] max-w-3xl max-h-[90vh] overflow-hidden rounded-card border border-border bg-surface shadow-2xl"
    >
      <div className="flex items-start justify-between border-b border-border px-5 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h2 id="trade-plan-detail-title" className="truncate text-[15px] font-semibold text-foreground">
              {plan.name || plan.symbol}
            </h2>
            <span className={cn('rounded-full border px-2 py-0.5 text-[9px]', STATUS_CLASS[plan.status])}>
              {STATUS_LABEL[plan.status]}
            </span>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px] text-muted">
            <span className="font-mono">{plan.symbol}</span>
            <span>{plan.plan_date}</span>
            <span>{SETUP_LABEL[plan.setup]}</span>
            <span>情绪 {MOOD_LABEL[plan.market_mood]}</span>
            <span>{HOLD_LABEL[plan.planned_hold]}</span>
            <span>信心 {plan.confidence}/5</span>
          </div>
        </div>
        <button onClick={onClose} className="rounded-btn p-1.5 text-muted hover:bg-elevated hover:text-foreground">
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="max-h-[calc(90vh-125px)] overflow-y-auto px-5 py-4">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
          <Metric label="单笔收益" value={pct(m.pnl_pct)} tone={priceColorClass(m.pnl_pct)} />
          <Metric label="R 倍数" value={rMultiple(m.r_multiple)} tone={priceColorClass(m.r_multiple)} />
          <Metric label="入场偏离" value={pct(m.entry_deviation_pct)} />
          <Metric label="纪律分" value={m.discipline_score == null ? '—' : String(m.discipline_score)}
            tone={m.discipline_score == null ? undefined : m.discipline_score >= 80 ? 'text-success' : m.discipline_score >= 50 ? 'text-warning' : 'text-danger'} />
          <Metric label="持有" value={holdText(m.hold_minutes)} />
        </div>

        <div className="mt-4">
          <PriceLadder plan={plan} />
        </div>

        {plan.flags.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-1.5">
            {plan.flags.map(flag => (
              <span key={flag.code}
                className={cn(
                  'rounded-full border px-2 py-0.5 text-[9px]',
                  flag.tone === 'danger' && 'border-danger/30 bg-danger/10 text-danger',
                  flag.tone === 'warn' && 'border-warning/30 bg-warning/10 text-warning',
                  flag.tone === 'info' && 'border-accent/30 bg-accent/10 text-accent',
                  flag.tone === 'muted' && 'border-border bg-elevated text-muted',
                )}>
                {flag.label}
              </span>
            ))}
          </div>
        )}

        <div className="mt-5 grid gap-5 sm:grid-cols-2">
          <section className="space-y-3">
            <h3 className="text-[11px] font-medium text-secondary">计划</h3>
            <div className="grid grid-cols-2 gap-2 text-[11px]">
              <div className="text-muted">买入区间</div>
              <div className="font-mono text-foreground">
                {fmtPrice(plan.planned_entry_low)} - {fmtPrice(plan.planned_entry_high)}
              </div>
              <div className="text-muted">止损 / 目标</div>
              <div className="font-mono text-foreground">
                {fmtPrice(plan.stop_loss)} / {fmtPrice(plan.target_price)}
              </div>
              <div className="text-muted">计划仓位</div>
              <div className="font-mono text-foreground">
                {plan.planned_position_pct == null ? '—' : `${plan.planned_position_pct}%`}
              </div>
              <div className="text-muted">风险 / 盈亏比</div>
              <div className="font-mono text-foreground">
                {pct(m.planned_risk_pct)} / {m.planned_rr == null ? '—' : m.planned_rr.toFixed(2)}
              </div>
            </div>
            <TextBlock label="核心逻辑" value={plan.thesis} />
            <TextBlock label="触发条件" value={plan.trigger} />
            <TextBlock label="失效条件" value={plan.invalidation} />
          </section>

          <section className="space-y-3">
            <h3 className="text-[11px] font-medium text-secondary">执行</h3>
            <div className="grid grid-cols-2 gap-2 text-[11px]">
              <div className="text-muted">买入</div>
              <div className="font-mono text-foreground">
                {fmtPrice(plan.actual_entry_price)} {plan.entry_at ? `· ${plan.entry_at.slice(5, 16).replace('T', ' ')}` : ''}
              </div>
              <div className="text-muted">卖出</div>
              <div className="font-mono text-foreground">
                {fmtPrice(plan.actual_exit_price)} {plan.exit_at ? `· ${plan.exit_at.slice(5, 16).replace('T', ' ')}` : ''}
              </div>
              <div className="text-muted">实际仓位</div>
              <div className="font-mono text-foreground">
                {plan.actual_position_pct == null ? '—' : `${plan.actual_position_pct}%`}
              </div>
              <div className="text-muted">离场原因</div>
              <div className="text-foreground">
                {plan.exit_reason ? EXIT_REASON_LABEL[plan.exit_reason] ?? plan.exit_reason : '—'}
              </div>
            </div>
            <TextBlock label="执行复盘" value={plan.review} />
            {plan.tags.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {plan.tags.map(tag => (
                  <span key={tag} className="rounded-full bg-elevated px-2 py-0.5 text-[9px] text-muted">{tag}</span>
                ))}
              </div>
            )}
          </section>
        </div>
      </div>

      <div className="flex items-center justify-between border-t border-border px-5 py-3">
        <button onClick={onDelete}
          className="inline-flex items-center gap-1.5 rounded-btn border border-danger/30 px-3 py-1.5 text-[11px] text-danger hover:bg-danger/10">
          <Trash2 className="h-3.5 w-3.5" /> 删除
        </button>
        <button onClick={onEdit}
          className="inline-flex items-center gap-1.5 rounded-btn bg-accent px-4 py-1.5 text-[11px] font-medium text-white hover:bg-accent/90">
          <Pencil className="h-3.5 w-3.5" /> 编辑
        </button>
      </div>
    </Modal>
  )
}
