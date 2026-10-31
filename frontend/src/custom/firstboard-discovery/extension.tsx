import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, ArrowRight, History, Loader2, Search, SlidersHorizontal } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { fmtPct } from '@/lib/format'
import type { FrontendExtension } from '@/extensions/types'
import { NegativeResearch, type NegativeResearchReport } from './NegativeResearch'

type SnapshotMode = 'D_minus_1' | 'D_close' | 'both'
type OutcomeHorizon = 5 | 10 | 20
interface Params { start: string; end: string; snapshot_mode: SnapshotMode; train_end?: string | null }
interface Condition {
  factor_id: string
  snapshot: string
  operator: string
  threshold?: number
  lower?: number | null
  upper?: number | null
}
interface FactorRow {
  factor_id: string; label?: string; snapshot: string; direction: string | null
  auc: number | null; q_value: number | null; coverage: number
  validation_auc: number | null; validation_count: number
}
interface Rule {
  id: string; conditions: Condition[]; dimension: number
  train_hits: number; validation_hits: number; validation_eligible: boolean
  train_strong_rate: number; validation_strong_rate: number | null
  lift: number | null; validation_lift: number | null
  mean_mfe_5d: number | null; mean_close_return_5d: number | null; mean_mae_5d: number | null
  mean_mfe_10d: number | null; mean_close_return_10d: number | null; mean_mae_10d: number | null
  mean_mfe_20d: number | null; mean_close_return_20d: number | null; mean_mae_20d: number | null
}
interface Report {
  run_id?: string; saved_at?: string
  data_as_of?: string | null
  generation: string; algorithm_version: string; elapsed_ms: number
  sample: {
    status: string; total_events: number; eligible_events: number; excluded_events: number
    excluded: Record<string, number>; base_strong_rate: number | null
  }
  split: {
    train_start: string | null; train_end: string | null; train_count: number
    validation_start: string | null; validation_end: string | null; validation_count: number
    train_base_rate: number | null; validation_base_rate: number | null; purged_count?: number
  }
  factors: FactorRow[]; rules: Rule[]; warnings: string[]
  negative_research?: NegativeResearchReport
  candidate_policy?: {
    factor_count: number; allowed_kinds: string[]; allowed_languages: string[]
    require_scale_free: boolean; require_stable: boolean; excluded_factor_ids: string[]
    allowed_extension_factor_ids?: string[]
  }
}
interface EventRow {
  event_id: string; symbol: string; name: string | null; date: string
  entry_date: string | null
  mfe_5d: number | null; close_return_5d: number | null; mae_5d: number | null
  mfe_10d: number | null; close_return_10d: number | null; mae_10d: number | null
  mfe_20d: number | null; close_return_20d: number | null; mae_20d: number | null
  strong: boolean | null; split: string; rule_ids: string[]
  early_fail_5d?: boolean | null; early_fail_probability?: number | null
  negative_veto?: boolean | null; frozen_main_hit?: boolean | null
  right_censored?: boolean; entry_unavailable?: boolean; entry_limit_locked?: boolean
  outcome_unavailable?: boolean; scale_break_suspected?: boolean; feature_unavailable?: boolean
}
interface Events { generation: string; rows: EventRow[]; total: number; page_size: number }
interface RunSummary {
  run_id: string; saved_at: string; algorithm_version: string; generation: string
  params: Params; sample_status: string; total_events: number
  eligible_events: number | null; event_count: number; factor_count: number; rule_count: number
  train_count: number | null; validation_count: number | null; elapsed_ms: number
}
interface Runs { items: RunSummary[] }

// Extension-specific API and cache namespace. All callers share this contract.
const client = {
  async get<T>(path: string, params?: Params | Record<string, string>): Promise<T> {
    const entries = params
      ? Object.entries(params).filter(([, value]) => value != null && value !== '')
      : []
    const query = entries.length ? `?${new URLSearchParams(entries as [string, string][])}` : ''
    const response = await fetch(`/api/custom/firstboard-discovery/${path}${query}`, {
      signal: AbortSignal.timeout(300_000),
    })
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}))
      throw new Error(typeof payload.detail === 'string' ? payload.detail : `读取失败（${response.status}）`)
    }
    return response.json() as Promise<T>
  },
  report: (params: Params) => client.get<Report>('report', params),
  events: (params: Params, extra: Record<string, string>) =>
    client.get<Events>('events', { ...params, ...extra }),
  runs: () => client.get<Runs>('runs'),
  savedReport: (runId: string) => client.get<Report>(`runs/${encodeURIComponent(runId)}/report`),
  savedEvents: (runId: string, extra: Record<string, string>) =>
    client.get<Events>(`runs/${encodeURIComponent(runId)}/events`, extra),
  reportKey: (params: Params | null, runId: string, revision: number) =>
    ['firstboard-discovery', 'report', params, runId, revision] as const,
  eventsKey: (params: Params | null, runId: string, generation: string | undefined, rule: string, page: number, revision: number) =>
    ['firstboard-discovery', 'events', params, runId, generation, rule, page, revision] as const,
  runsKey: ['firstboard-discovery', 'runs'] as const,
}

function cnToday() {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(new Date())
  const pick = (type: string) => parts.find(p => p.type === type)?.value ?? ''
  return `${pick('year')}-${pick('month')}-${pick('day')}`
}
const SNAPSHOT: Record<string, string> = { D_minus_1: 'T-1 收盘', D_close: 'T 日收盘' }
const EXCLUSIONS: Record<string, string> = {
  right_censored: '20日未走完', entry_unavailable: '价格或交易日缺失',
  entry_limit_locked: '次日开盘涨停', outcome_unavailable: '收益窗口价格缺失',
  scale_break_suspected: '价格尺度待核查',
  feature_unavailable: '特征预热不足',
}
export function qualityFlags(row: Partial<EventRow>): string[] {
  return Object.entries(EXCLUSIONS)
    .filter(([field]) => row[field as keyof EventRow] === true)
    .map(([, label]) => label)
}
export function ruleText(conditions: Condition[], labels: Record<string, string>): string {
  return conditions.map(c => {
    const label = `${SNAPSHOT[c.snapshot] ?? c.snapshot} · ${labels[c.factor_id] ?? c.factor_id}`
    if (c.operator !== 'between') return `${label} ${c.operator} ${c.threshold?.toPrecision(4)}`
    return `${label} ${c.lower == null ? '' : `≥ ${c.lower.toPrecision(4)}`} ${c.upper == null ? '' : `< ${c.upper.toPrecision(4)}`}`.trim()
  }).join(' 且 ')
}
export function formatRatio(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${(value * 100).toFixed(digits)}%`
}
export function formatQValue(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—'
  if (value < .001) return '<0.001'
  if (value > .999) return '>0.999'
  return value.toFixed(3)
}
const number = (value: number | null | undefined, digits = 3) =>
  value == null ? '—' : value.toFixed(digits)
const inputClass = 'h-9 rounded-input border border-border bg-base px-2 text-xs text-foreground'
const numericCell = 'whitespace-nowrap px-4 py-2 text-right font-mono tabular-nums'
const HORIZONS: OutcomeHorizon[] = [5, 10, 20]

function outcomeValue(
  row: EventRow | Rule,
  horizon: OutcomeHorizon,
  metric: 'mfe' | 'close_return' | 'mae',
): number | null {
  return (row as unknown as Record<string, number | null>)[`${metric}_${horizon}d`] ?? null
}

function ruleOutcomeValue(
  rule: Rule,
  horizon: OutcomeHorizon,
  metric: 'mfe' | 'close_return' | 'mae',
): number | null {
  return rule[`mean_${metric}_${horizon}d`] ?? null
}

function formatSavedAt(value: string | undefined): string {
  if (!value) return '尚未保存'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(parsed)
}

export function FirstboardDiscovery() {
  const today = cnToday()
  const queryClient = useQueryClient()
  const syncedRun = useRef('')
  const [draft, setDraft] = useState<Params>({
    start: `${Number(today.slice(0, 4)) - 3}${today.slice(4)}`,
    end: today, snapshot_mode: 'both', train_end: '',
  })
  const [active, setActive] = useState<Params | null>(null)
  const [selectedRunId, setSelectedRunId] = useState('')
  const [revision, setRevision] = useState(0)
  const [ruleId, setRuleId] = useState('')
  const [page, setPage] = useState(1)
  const [outcomeHorizon, setOutcomeHorizon] = useState<OutcomeHorizon>(20)
  const [sort, setSort] = useState<'auc' | 'validation_auc' | 'coverage'>('auc')
  const report = useQuery({
    queryKey: client.reportKey(active, selectedRunId, revision),
    queryFn: () => selectedRunId ? client.savedReport(selectedRunId) : client.report(active!),
    enabled: !!active, retry: false, staleTime: Infinity, refetchOnWindowFocus: false,
  })
  const runs = useQuery({
    queryKey: client.runsKey,
    queryFn: client.runs,
    enabled: !!report.data, retry: false, staleTime: 0, refetchOnWindowFocus: false,
  })
  const eventsRunId = selectedRunId || report.data?.run_id || ''
  const events = useQuery({
    queryKey: client.eventsKey(active, eventsRunId, report.data?.generation, ruleId, page, revision),
    queryFn: () => {
      const extra = { page: String(page), page_size: '50', ...(ruleId ? { rule_id: ruleId } : {}) }
      return eventsRunId ? client.savedEvents(eventsRunId, extra) : client.events(active!, extra)
    },
    enabled: !!active && !!report.data && !report.isFetching,
    retry: false, staleTime: Infinity, refetchOnWindowFocus: false,
  })
  const data = report.data
  useEffect(() => {
    if (!data?.run_id || selectedRunId || syncedRun.current === data.run_id) return
    syncedRun.current = data.run_id
    void queryClient.invalidateQueries({ queryKey: client.runsKey })
  }, [data?.run_id, queryClient, selectedRunId])
  const labels = useMemo(() => Object.fromEntries((report.data?.factors ?? []).map(f => [
    f.factor_id, f.label ?? f.factor_id,
  ])), [report.data])
  const factors = useMemo(() => [...(report.data?.factors ?? [])].sort((a, b) => {
    if (sort === 'coverage') return b.coverage - a.coverage
    return Math.abs((b[sort] ?? .5) - .5) - Math.abs((a[sort] ?? .5) - .5)
  }), [report.data, sort])
  const run = () => {
    setRuleId(''); setPage(1); setSelectedRunId(''); setOutcomeHorizon(20)
    setActive({ ...draft }); setRevision(r => r + 1)
  }
  const chooseRun = (runId: string) => {
    setSelectedRunId(runId)
    setRuleId(''); setPage(1); setOutcomeHorizon(20)
    const selected = runs.data?.items.find(item => item.run_id === runId)
    if (selected) {
      setDraft({ ...selected.params, train_end: selected.params.train_end ?? '' })
      setActive(selected.params)
    }
  }
  const selectedRule = data?.rules.find(r => r.id === ruleId)
  const busy = report.isFetching

  return <div className="min-h-full bg-base">
    <PageHeader title="首板因子区分" subtitle="T 日及以前的特征 → 次日开盘后的 5 / 10 / 20 日价格机会" />
    <main className="mx-auto max-w-[1600px] space-y-4 p-3 lg:p-5">
      <aside className="rounded-card border border-amber-400/40 bg-amber-400/5 px-4 py-3 text-xs leading-6 text-secondary">
        <div className="flex items-center gap-2 font-medium text-amber-500"><AlertTriangle size={14} />按当前数据库进行研究</div>
        <p>按所选事件日期使用当前数据库计算，数据更新后可直接重新计算。行情数据截至日仅用于说明数据来源。早损研究用于比较风险与机会保留，结果属于回顾性研究。</p>
      </aside>
      <section className="rounded-card border border-border bg-surface p-4">
        <div className="flex items-center gap-2 text-sm font-medium"><SlidersHorizontal size={16} className="text-accent" />自动发现研究</div>
        <p className="mt-2 text-xs leading-5 text-secondary">
          主标签：T+1 开盘至后续 20 个交易日最高价上涨 ≥20%。同时观察 5、10、20 日窗口的最高收益、期末收益与最大不利波动。
          每次先在较早日期训练，再用较晚日期验证。
        </p>
        <div className="mt-3 grid grid-cols-1 items-end gap-3 sm:flex sm:flex-wrap">
          <label className="w-full space-y-1 text-xs text-secondary sm:w-auto"><span className="block">事件开始</span>
            <input aria-label="事件开始" className={inputClass} type="date" value={draft.start} onChange={e => setDraft({ ...draft, start: e.target.value })} />
          </label>
          <label className="w-full space-y-1 text-xs text-secondary sm:w-auto"><span className="block">事件截止</span>
            <input aria-label="事件截止" className={inputClass} type="date" max={today} value={draft.end} onChange={e => setDraft({ ...draft, end: e.target.value })} />
          </label>
          <label className="w-full space-y-1 text-xs text-secondary sm:w-auto"><span className="block">特征时点</span>
            <select aria-label="特征时点" className={inputClass} value={draft.snapshot_mode} onChange={e => setDraft({ ...draft, snapshot_mode: e.target.value as SnapshotMode })}>
              <option value="both">T-1 与 T 收盘分别筛选</option><option value="D_minus_1">T-1 收盘</option><option value="D_close">T 日收盘</option>
            </select>
          </label>
          <label className="w-full space-y-1 text-xs text-secondary sm:w-auto"><span className="block">预注册训练截止</span>
            <input aria-label="预注册训练截止" className={inputClass} type="date" value={draft.train_end ?? ''}
              min={draft.start} max={draft.end} onChange={e => setDraft({ ...draft, train_end: e.target.value })} />
          </label>
          <button type="button" disabled={busy || !draft.start || !draft.end || draft.start > draft.end || draft.end > today
            || (!!draft.train_end && (draft.train_end <= draft.start || draft.train_end >= draft.end))}
            onClick={run} className="inline-flex h-9 w-full items-center justify-center gap-2 rounded-btn bg-accent px-4 text-xs font-medium text-white disabled:opacity-50 sm:w-auto">
            {busy ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />}
            {busy ? '正在计算…' : '开始自动发现'}
          </button>
        </div>
        <p className="mt-2 text-[11px] leading-5 text-muted">按需计算，可能需要数分钟。填写训练截止日后，训练/验证边界将固定，便于预注册复验；留空则使用探索性的 70/30 时间切分。</p>
      </section>

      {!active && <div className="rounded-card border border-dashed border-border py-14 text-center text-sm text-muted">
        选择首板事件区间，开始自动发现区分因子
      </div>}
      {busy && <div role="status" className="flex items-center justify-center gap-3 rounded-card border border-border bg-surface py-12 text-sm text-secondary">
        <Loader2 size={18} className="animate-spin text-accent" />加载行情、计算因子与训练规则中…
      </div>}
      {report.isError && <ErrorBox error={report.error} retry={() => void report.refetch()} />}
      {data && !busy && <>
        <section className="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
          {[
            ['候选首板', data.sample.total_events.toLocaleString()],
            ['可评估事件', data.sample.eligible_events.toLocaleString()],
            ['≥20% 基准率', formatRatio(data.sample.base_strong_rate)],
            ['训练 / 验证', `${data.split.train_count} / ${data.split.validation_count}`],
            ['已排除事件', String(data.sample.excluded_events)],
          ].map(([label, value]) => <div key={label} className="rounded-card border border-border bg-surface p-3">
            <div className="text-[11px] text-muted">{label}</div><div className="mt-1 font-mono text-xl text-foreground">{value}</div>
          </div>)}
        </section>
        <section className="flex flex-wrap items-end justify-between gap-3 rounded-card border border-border bg-surface p-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-sm font-medium"><History size={15} className="text-accent" />已保存结果</div>
            <p className="mt-1 text-[11px] leading-5 text-muted">
              每次计算会保存报告和事件供历史查看；开始自动发现始终按当前数据库计算。
            </p>
          </div>
          <label className="min-w-[240px] flex-1 space-y-1 text-[11px] text-muted sm:max-w-xl">
            <span className="block">打开训练记录</span>
            <select aria-label="已保存结果" className={`${inputClass} w-full`} value={selectedRunId}
              onChange={e => chooseRun(e.target.value)}>
              <option value="">本次计算结果</option>
              {(runs.data?.items ?? []).map(item => <option key={item.run_id} value={item.run_id}>
                {formatSavedAt(item.saved_at)} · {item.params.start}～{item.params.end} · {item.eligible_events?.toLocaleString() ?? '—'} 可评估
              </option>)}
            </select>
          </label>
          <div className="w-full text-[10px] text-muted">
            {data.run_id ? `记录 ${data.run_id.slice(0, 24)} · 保存于 ${formatSavedAt(data.saved_at)}` : '当前记录尚未生成保存标识'}
            {runs.isError ? ' · 历史记录读取失败' : ''}
          </div>
        </section>
        <div className="rounded-card border border-border bg-surface p-3 text-xs leading-6 text-secondary">
          <div>训练 {data.split.train_start ?? '—'} ～ {data.split.train_end ?? '—'} <ArrowRight size={12} className="mx-1 inline" />
            验证 {data.split.validation_start ?? '—'} ～ {data.split.validation_end ?? '—'}
            {data.split.purged_count ? ` · 边界隔离 ${data.split.purged_count} 个事件` : ''}</div>
          <div>排除原因可重叠：{Object.entries(data.sample.excluded).map(([k, v]) => `${EXCLUSIONS[k] ?? k} ${v}`).join(' · ') || '无'}</div>
          <div>行情数据截至 {data.data_as_of ?? '—'}</div>
          <div className="text-[10px] text-muted">
            {data.algorithm_version} · 候选 {data.candidate_policy?.factor_count ?? '—'} 个
            {data.candidate_policy?.require_scale_free
              ? ` · ${data.candidate_policy.allowed_extension_factor_ids?.length
                ? '内置无量纲稳定因子 · 封板炸板白名单仅 T 日收盘'
                : '仅无量纲稳定因子'}`
              : ''}
            {' · '}数据版本 {data.generation?.slice(0, 12)} · 耗时 {(data.elapsed_ms / 1000).toFixed(1)}s
          </div>
        </div>
        {data.sample.status !== 'ok' && <div role="status" className="rounded-card border border-amber-400/40 bg-amber-400/5 p-3 text-xs leading-6 text-amber-500">
          {data.sample.status === 'no_data' ? '所选区间没有可用首板事件。' : '样本不足，暂不生成自动规则。需训练 ≥120、验证 ≥60，且两侧强弱样本均 ≥10。可扩大事件日期区间。'}
        </div>}

        <NegativeResearch report={data.negative_research} labels={labels} />

        <section className="overflow-hidden rounded-card border border-border bg-surface">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border p-3">
            <h2 className="text-sm font-medium">因子区分能力</h2>
            <select aria-label="因子排序" className={inputClass} value={sort} onChange={e => setSort(e.target.value as typeof sort)}>
              <option value="auc">训练 AUC 偏离 0.5</option><option value="validation_auc">验证 AUC 偏离 0.5</option><option value="coverage">覆盖率</option>
            </select>
          </div>
          <p className="px-3 py-2 text-[11px] leading-5 text-muted">AUC=0.5 表示未体现区分；高于 0.5 表示高值对应更多强首板，低于 0.5 表示低值对应更多。q 值越小越值得复核，低于 0.001 按显示精度单列。</p>
          <p className="border-t border-border px-3 py-2 text-[11px] text-muted sm:hidden">左右滑动查看 AUC、验证样本与 q 值；因子列会保持可见。</p>
          <div className="max-h-[28rem] overflow-auto overscroll-x-contain">
            <table className="w-full min-w-[760px] text-left text-xs">
              <thead className="sticky top-0 bg-elevated text-muted"><tr>
                <th className="sticky left-0 z-20 min-w-[210px] bg-elevated px-4 py-2 font-normal">因子 / 时点</th>
                <th className="px-3 py-2 font-normal">方向</th>
                <th className="px-4 py-2 text-right font-normal">覆盖</th>
                <th className="px-4 py-2 text-right font-normal">训练 AUC</th>
                <th className="px-4 py-2 text-right font-normal">验证 AUC</th>
                <th className="px-4 py-2 text-right font-normal">验证样本</th>
                <th className="px-4 py-2 text-right font-normal">训练 q</th>
              </tr></thead>
              <tbody>{!factors.length && <tr><td colSpan={7} className="p-6 text-center text-muted">暂无可展示的因子</td></tr>}{factors.map(f => <tr key={`${f.factor_id}-${f.snapshot}`} className="border-t border-border">
                <td className="sticky left-0 z-10 min-w-[210px] bg-surface px-4 py-2.5"><div className="font-medium">{labels[f.factor_id]}</div><div className="mt-0.5 text-[10px] text-muted">{SNAPSHOT[f.snapshot]}</div></td>
                <td className="whitespace-nowrap px-3 py-2.5">{f.direction === 'high' ? '高值' : f.direction === 'low' ? '低值' : '未区分'}</td>
                <td className={numericCell}>{formatRatio(f.coverage)}</td>
                <td className={numericCell}>{number(f.auc)}</td>
                <td className={numericCell}>{number(f.validation_auc)}</td>
                <td className={`${numericCell} text-secondary`}>{f.validation_count.toLocaleString()}</td>
                <td className={numericCell}>{formatQValue(f.q_value)}</td>
              </tr>)}</tbody>
            </table>
          </div>
        </section>

        <section className="rounded-card border border-border bg-surface">
          <h2 className="border-b border-border p-3 text-sm font-medium">自动选择的规则 <span className="text-xs font-normal text-muted">20 日标签训练期排名 · 验证期独立评估</span></h2>
          <p className="border-b border-border px-3 py-2 text-[11px] leading-5 text-muted">因子和规则仍以 20 日最高收益 ≥20% 为分类标签；下方同时列出命中事件在 5、10、20 日窗口的验证期表现。</p>
          {!data.rules.length && <p className="p-6 text-center text-xs text-muted">暂无满足训练支持度的规则</p>}
          <div className="divide-y divide-border">{data.rules.map((r, index) => <button key={r.id} type="button"
            aria-pressed={ruleId === r.id}
            onClick={() => { setRuleId(ruleId === r.id ? '' : r.id); setPage(1) }}
            className={`w-full p-3 text-left transition-colors hover:bg-elevated/50 ${ruleId === r.id ? 'bg-accent/10' : ''}`}>
            <div className="flex gap-2 text-xs leading-6"><span className="font-mono text-accent">{index + 1}</span><span>{ruleText(r.conditions, labels)}</span></div>
            <div className="mt-1 flex flex-wrap gap-x-5 gap-y-1 text-[11px] text-secondary">
              <span>训练 n={r.train_hits} · 命中率 {formatRatio(r.train_strong_rate)} · 提升 {number(r.lift, 2)}倍</span>
              <span>验证 n={r.validation_hits} · 命中率 {formatRatio(r.validation_strong_rate)} · 提升 {number(r.validation_lift, 2)}倍</span>
              {!r.validation_eligible && <span className="text-amber-500">验证样本不足</span>}
            </div>
            <div className="mt-2 grid gap-2 sm:grid-cols-3">
              {HORIZONS.map(horizon => <div key={horizon} className="rounded-input border border-border/70 bg-base/40 px-2.5 py-2">
                <div className="text-[10px] font-medium text-muted">{horizon} 日窗口</div>
                <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 font-mono text-[11px] tabular-nums">
                  <span>最高 {fmtPct(ruleOutcomeValue(r, horizon, 'mfe'))}</span>
                  <span>期末 {fmtPct(ruleOutcomeValue(r, horizon, 'close_return'))}</span>
                  <span>不利 {fmtPct(ruleOutcomeValue(r, horizon, 'mae'))}</span>
                </div>
              </div>)}
            </div>
          </button>)}</div>
        </section>

        <section className="overflow-hidden rounded-card border border-border bg-surface">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border p-3">
            <h2 className="text-sm font-medium">{selectedRule ? '规则命中事件' : '全部首板事件'}</h2>
            <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted">
              <span>收益窗口</span>
              <select aria-label="事件收益窗口" className={inputClass} value={outcomeHorizon}
                onChange={e => setOutcomeHorizon(Number(e.target.value) as OutcomeHorizon)}>
                {HORIZONS.map(horizon => <option key={horizon} value={horizon}>{horizon} 日</option>)}
              </select>
              {ruleId && <button className="text-xs text-accent" onClick={() => { setRuleId(''); setPage(1) }}>清除规则筛选</button>}
            </div>
          </div>
          {events.isFetching ? <p role="status" className="p-8 text-center text-xs text-muted">正在读取事件…</p>
            : events.isError ? <ErrorBox error={events.error} retry={() => void events.refetch()} />
            : !events.data ? <p className="p-4 text-xs text-muted">正在读取事件…</p>
            : <div className="overflow-x-auto"><table className="w-full min-w-[800px] text-left text-xs">
              <thead className="bg-elevated text-muted"><tr>
                <th className="sticky left-0 z-20 min-w-[220px] bg-elevated px-3 py-2 font-normal">股票 / 事件日</th>
                {['参考入场日', `${outcomeHorizon} 日最高收益`, `${outcomeHorizon} 日期末收益`, '最大不利波动', '预测早损风险', '实际 5 日早损', '归属 / 状态'].map(s => <th key={s} className="whitespace-nowrap px-3 py-2 font-normal">{s}</th>)}
              </tr></thead>
              <tbody>{events.data.rows.map(row => <tr key={row.event_id} className="border-t border-border">
                <td className="sticky left-0 z-10 min-w-[220px] bg-surface px-3 py-2">{row.name || row.symbol}<span className="ml-2 text-muted">{row.symbol}</span><div className="mt-1 font-mono text-muted">{row.date}</div></td>
                <td className="px-3 py-2 font-mono">{row.entry_date ?? '—'}</td>
                <td className="px-3 py-2 font-mono">{fmtPct(outcomeValue(row, outcomeHorizon, 'mfe'))}</td>
                <td className="px-3 py-2 font-mono">{fmtPct(outcomeValue(row, outcomeHorizon, 'close_return'))}</td>
                <td className="px-3 py-2 font-mono">{fmtPct(outcomeValue(row, outcomeHorizon, 'mae'))}</td>
                <td className="whitespace-nowrap px-3 py-2 font-mono">{formatRatio(row.early_fail_probability)}
                  <div className={`mt-1 text-[10px] ${row.negative_veto ? 'text-amber-500' : 'text-muted'}`}>
                    {row.negative_veto == null ? '风险未知' : row.negative_veto ? '风险否决' : '风险保留'}
                  </div>
                </td>
                <td className="whitespace-nowrap px-3 py-2">{row.early_fail_5d == null ? '未标注'
                  : row.early_fail_5d ? '已触及 -8%' : '未触及 -8%'}</td>
                <td className="px-3 py-2"><div>{row.split === 'train' ? '训练' : row.split === 'validation' ? '验证' : row.split === 'purged' ? '边界隔离' : '排除'} · {row.strong == null ? '未标注' : row.strong ? '≥20%' : '<20%'}</div><div className="mt-1 text-[10px] text-amber-500">{qualityFlags(row).join(' · ')}</div></td>
              </tr>)}</tbody>
            </table>{!events.data.rows.length && <p className="p-8 text-center text-xs text-muted">没有命中事件</p>}</div>}
          <div className="flex flex-wrap items-center justify-end gap-3 border-t border-border p-3 text-xs text-secondary">
            <span>共 {events.data?.total ?? 0} 条 · 第 {page} 页</span>
            <button disabled={page <= 1 || events.isFetching} onClick={() => setPage(p => p - 1)} className="disabled:opacity-30">上一页</button>
            <button disabled={!events.data || page * 50 >= events.data.total || events.isFetching} onClick={() => setPage(p => p + 1)} className="disabled:opacity-30">下一页</button>
          </div>
        </section>
        <aside className="rounded-card border border-amber-400/30 bg-amber-400/5 p-3 text-[11px] leading-6 text-secondary">
          <div className="mb-1 flex items-center gap-2 font-medium text-amber-500"><AlertTriangle size={14} />研究口径与限制</div>
          {data.warnings.map(w => <p key={w}>{w}</p>)}
        </aside>
      </>}
    </main>
  </div>
}

function ErrorBox({ error, retry }: { error: Error | null; retry: () => void }) {
  return <div role="alert" className="rounded-card border border-danger/40 bg-danger/5 p-4 text-xs text-danger">
    {error?.message ?? '请求失败'}<button type="button" onClick={retry} className="ml-3 underline">重试</button>
  </div>
}

const extension: FrontendExtension = {
  id: 'official.firstboard-discovery',
  apiVersion: 1,
  routes: [{ id: 'firstboard-discovery', path: '/firstboard-discovery', component: FirstboardDiscovery }],
  navigation: [{ id: 'firstboard-discovery', routeId: 'firstboard-discovery', label: '首板因子区分', icon: Search, order: 430 }],
}
export default extension
