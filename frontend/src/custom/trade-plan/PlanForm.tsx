import { useEffect, useState } from 'react'
import { X } from 'lucide-react'
import { Modal } from '@/components/Modal'
import { toast } from '@/components/Toast'
import { cn } from '@/lib/cn'
import { cnToday } from '@/lib/kline'
import { tradePlanApi } from './client'
import { InstrumentSearch } from './InstrumentSearch'
import {
  EXIT_REASON_OPTIONS,
  HOLD_LABEL,
  MOOD_LABEL,
  SETUP_LABEL,
  STATUS_LABEL,
  type HoldingPlan,
  type MarketMood,
  type PlanStatus,
  type SetupType,
  type TradePlan,
  type TradePlanPayload,
} from './types'

const inputCls =
  'h-8 w-full rounded-btn border border-border bg-base px-2.5 text-[12px] text-foreground outline-none transition-colors focus:border-accent/60'
const textareaCls =
  'w-full rounded-btn border border-border bg-base px-2.5 py-2 text-[12px] leading-relaxed text-foreground outline-none transition-colors focus:border-accent/60 resize-y'

function numText(value: number | null | undefined): string {
  return value == null ? '' : String(value)
}

function numOrNull(value: string): number | null {
  const text = value.trim()
  if (!text) return null
  const number = Number(text)
  return Number.isFinite(number) ? number : null
}

function dateTimeText(value: string | null | undefined): string {
  return value ? value.slice(0, 16) : ''
}

function emptyForm(): TradePlanPayload {
  return {
    plan_date: cnToday(),
    symbol: '',
    name: '',
    setup: 'first_board',
    market_mood: 'skip',
    confidence: 3,
    planned_hold: 'overnight',
    thesis: '',
    trigger: '',
    invalidation: '',
    planned_entry_low: null,
    planned_entry_high: null,
    stop_loss: null,
    target_price: null,
    planned_position_pct: null,
    status: 'planned',
    actual_entry_price: null,
    entry_at: null,
    actual_position_pct: null,
    actual_exit_price: null,
    exit_at: null,
    exit_reason: null,
    review: '',
    tags: [],
  }
}

type NumericKey =
  | 'planned_entry_low'
  | 'planned_entry_high'
  | 'stop_loss'
  | 'target_price'
  | 'planned_position_pct'
  | 'actual_entry_price'
  | 'actual_position_pct'
  | 'actual_exit_price'

function fromPlan(plan: TradePlan): TradePlanPayload {
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
    tags: plan.tags ?? [],
  }
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="flex items-center justify-between gap-2 text-[10px] text-muted">
        <span>{label}</span>
        {hint && <span className="text-muted/70">{hint}</span>}
      </span>
      {children}
    </label>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <h3 className="text-[11px] font-medium tracking-wide text-secondary">{title}</h3>
      {children}
    </section>
  )
}

export function PlanForm({ plan, initialSymbol, initialName, symbolOptions, onClose, onSaved }: {
  plan: TradePlan | null
  initialSymbol?: string
  initialName?: string
  symbolOptions?: Array<{ symbol: string; name: string }>
  onClose: () => void
  onSaved: (plan: TradePlan) => void
}) {
  const initialForm = () => {
    if (plan) return fromPlan(plan)
    return {
      ...emptyForm(),
      symbol: initialSymbol ?? '',
      name: initialName ?? '',
    }
  }
  const [form, setForm] = useState<TradePlanPayload>(initialForm)
  const [tagsText, setTagsText] = useState((plan?.tags ?? []).join('，'))
  // 数字输入保留原始文本，允许用户输入 "12." 等中间态；提交前再转 number。
  const [numberDrafts, setNumberDrafts] = useState<Partial<Record<NumericKey, string>>>({})
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setForm(plan ? fromPlan(plan) : {
      ...emptyForm(),
      symbol: initialSymbol ?? '',
      name: initialName ?? '',
    })
    setTagsText((plan?.tags ?? []).join('，'))
    setNumberDrafts({})
    // initialName 可能由异步名称查询稍后到达，单独在下方补空值，避免重置用户已填内容。
  }, [plan, initialSymbol])

  useEffect(() => {
    if (plan || !initialName || form.symbol !== initialSymbol) return
    setForm(prev => (prev.name ? prev : { ...prev, name: initialName }))
  }, [initialName, initialSymbol, plan, form.symbol])

  const set = <K extends keyof TradePlanPayload>(key: K, value: TradePlanPayload[K]) => {
    setForm(prev => ({ ...prev, [key]: value }))
  }

  const setNumber = (key: NumericKey, text: string) => {
    setNumberDrafts(prev => ({ ...prev, [key]: text }))
    setForm(prev => ({ ...prev, [key]: numOrNull(text) }))
  }

  const numberProps = (key: NumericKey) => ({
    value: numberDrafts[key] ?? numText(form[key]),
    onChange: (event: React.ChangeEvent<HTMLInputElement>) => setNumber(key, event.target.value),
    onBlur: () => setNumberDrafts(prev => {
      const next = { ...prev }
      delete next[key]
      return next
    }),
  })

  const submit = async () => {
    if (!form.symbol.trim()) {
      toast('请填写证券代码', 'error')
      return
    }
    if (form.status === 'exited' && !form.exit_at) {
      toast('已结束计划需填写卖出时间', 'error')
      return
    }
    setSaving(true)
    try {
      const payload: TradePlanPayload = {
        ...form,
        symbol: form.symbol.trim().toUpperCase(),
        name: form.name.trim(),
        tags: Array.from(new Set(
          tagsText
            .split(/[,，、\s]+/)
            .map(tag => tag.trim())
            .filter(Boolean),
        )).slice(0, 10),
      }
      const result = plan
        ? await tradePlanApi.update(plan.id, payload)
        : await tradePlanApi.create(payload)
      toast(plan ? '计划已更新' : '计划已创建', 'success')
      onSaved(result.plan)
      onClose()
    } catch (error: any) {
      toast(error?.message || '保存失败', 'error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      onClose={onClose}
      labelledBy="trade-plan-form-title"
      panelClassName="w-[94vw] max-w-4xl max-h-[90vh] overflow-hidden rounded-card border border-border bg-surface shadow-2xl"
    >
      <div className="flex items-center justify-between border-b border-border px-5 py-3">
        <div>
          <h2 id="trade-plan-form-title" className="text-[15px] font-semibold text-foreground">
            {plan ? '编辑交易计划' : '新建交易计划'}
          </h2>
        </div>
        <button onClick={onClose} className="rounded-btn p-1.5 text-muted hover:bg-elevated hover:text-foreground">
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="max-h-[calc(90vh-105px)] overflow-y-auto px-5 py-4">
        <div className="space-y-6">
          <Section title="标的与模式">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div className="col-span-2">
                <Field label="搜索标的" hint="代码 / 名称">
                  <InstrumentSearch onSelect={(symbol, name) => {
                    set('symbol', symbol)
                    set('name', name)
                  }} />
                </Field>
              </div>
              {symbolOptions && symbolOptions.length > 1 && (
                <div className="col-span-2">
                  <Field label="从当前自选选择" hint={`${symbolOptions.length} 只`}>
                    <select
                      className={inputCls}
                      value={symbolOptions.some(item => item.symbol === form.symbol) ? form.symbol : ''}
                      onChange={event => {
                        const item = symbolOptions.find(option => option.symbol === event.target.value)
                        if (!item) return
                        set('symbol', item.symbol)
                        set('name', item.name)
                      }}
                    >
                      <option value="">选择标的</option>
                      {symbolOptions.map(item => (
                        <option key={item.symbol} value={item.symbol}>
                          {item.symbol}{item.name ? ` ${item.name}` : ''}
                        </option>
                      ))}
                    </select>
                  </Field>
                </div>
              )}
              <Field label="证券代码">
                <input className={inputCls} placeholder="600000.SH" value={form.symbol}
                  onChange={e => set('symbol', e.target.value)} />
              </Field>
              <Field label="名称">
                <input className={inputCls} placeholder="可选" value={form.name}
                  onChange={e => set('name', e.target.value)} />
              </Field>
              <Field label="计划日">
                <input type="date" className={inputCls} value={form.plan_date}
                  onChange={e => set('plan_date', e.target.value)} />
              </Field>
              <Field label="模式">
                <select className={inputCls} value={form.setup}
                  onChange={e => set('setup', e.target.value as SetupType)}>
                  {Object.entries(SETUP_LABEL).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </Field>
              <Field label="市场情绪">
                <select className={inputCls} value={form.market_mood}
                  onChange={e => set('market_mood', e.target.value as MarketMood)}>
                  {Object.entries(MOOD_LABEL).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </Field>
              <Field label="预期持有">
                <select className={inputCls} value={form.planned_hold}
                  onChange={e => set('planned_hold', e.target.value as HoldingPlan)}>
                  {Object.entries(HOLD_LABEL).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </Field>
              <Field label="信心">
                <select className={inputCls} value={form.confidence}
                  onChange={e => set('confidence', Number(e.target.value))}>
                  {[1, 2, 3, 4, 5].map(value => (
                    <option key={value} value={value}>{value} / 5</option>
                  ))}
                </select>
              </Field>
              <Field label="执行状态">
                <select className={inputCls} value={form.status}
                  onChange={e => set('status', e.target.value as PlanStatus)}>
                  {Object.entries(STATUS_LABEL).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </Field>
            </div>
            <Field label="标签" hint="逗号分隔">
              <input className={inputCls} placeholder="首板，科技，弱转强" value={tagsText}
                onChange={e => setTagsText(e.target.value)} />
            </Field>
          </Section>

          <Section title="计划价格与仓位">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
              <Field label="买入下限">
                <input type="number" step="0.01" className={inputCls} {...numberProps('planned_entry_low')} />
              </Field>
              <Field label="买入上限">
                <input type="number" step="0.01" className={inputCls} {...numberProps('planned_entry_high')} />
              </Field>
              <Field label="止损">
                <input type="number" step="0.01" className={inputCls} {...numberProps('stop_loss')} />
              </Field>
              <Field label="目标">
                <input type="number" step="0.01" className={inputCls} {...numberProps('target_price')} />
              </Field>
              <Field label="计划仓位 %">
                <input type="number" step="1" min="0" max="100" className={inputCls}
                  {...numberProps('planned_position_pct')} />
              </Field>
            </div>
          </Section>

          <Section title="计划逻辑">
            <div className="grid gap-3 lg:grid-cols-3">
              <Field label="核心逻辑">
                <textarea rows={3} className={textareaCls} value={form.thesis}
                  onChange={e => set('thesis', e.target.value)} />
              </Field>
              <Field label="触发条件">
                <textarea rows={3} className={textareaCls} value={form.trigger}
                  onChange={e => set('trigger', e.target.value)} />
              </Field>
              <Field label="失效条件">
                <textarea rows={3} className={textareaCls} value={form.invalidation}
                  onChange={e => set('invalidation', e.target.value)} />
              </Field>
            </div>
          </Section>

          <Section title="实际执行">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Field label="实际买入价">
                <input type="number" step="0.01" className={inputCls} {...numberProps('actual_entry_price')} />
              </Field>
              <Field label="买入时间">
                <input type="datetime-local" className={inputCls} value={dateTimeText(form.entry_at)}
                  onChange={e => set('entry_at', e.target.value || null)} />
              </Field>
              <Field label="实际仓位 %">
                <input type="number" step="1" min="0" max="100" className={inputCls}
                  {...numberProps('actual_position_pct')} />
              </Field>
              <Field label="离场原因">
                <select className={inputCls} value={form.exit_reason ?? ''}
                  onChange={e => set('exit_reason', e.target.value || null)}>
                  <option value="">未填写</option>
                  {EXIT_REASON_OPTIONS.map(item => (
                    <option key={item.value} value={item.value}>{item.label}</option>
                  ))}
                </select>
              </Field>
              <Field label="实际卖出价">
                <input type="number" step="0.01" className={inputCls} {...numberProps('actual_exit_price')} />
              </Field>
              <Field label="卖出时间">
                <input type="datetime-local" className={inputCls} value={dateTimeText(form.exit_at)}
                  onChange={e => set('exit_at', e.target.value || null)} />
              </Field>
            </div>
            <Field label="执行复盘">
              <textarea rows={3} className={textareaCls} value={form.review}
                onChange={e => set('review', e.target.value)} />
            </Field>
          </Section>
        </div>
      </div>

      <div className="flex items-center justify-end gap-2 border-t border-border px-5 py-3">
        <button onClick={onClose}
          className="rounded-btn border border-border px-3 py-1.5 text-[12px] text-secondary hover:bg-elevated">
          取消
        </button>
        <button onClick={submit} disabled={saving}
          className={cn(
            'rounded-btn bg-accent px-4 py-1.5 text-[12px] font-medium text-white hover:bg-accent/90',
            saving && 'cursor-wait opacity-60',
          )}>
          {saving ? '保存中…' : '保存'}
        </button>
      </div>
    </Modal>
  )
}
