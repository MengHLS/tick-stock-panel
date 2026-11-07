import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  FlaskConical,
  GitCompare,
  Loader2,
  Microscope,
  Plus,
  RefreshCw,
  Search,
} from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { EmptyState } from '@/components/EmptyState'
import { api, type StrategyResearchEvent } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { cn } from '@/lib/cn'
import { fmtPct } from '@/lib/format'
import { toast } from '@/components/Toast'

type Tab = 'path' | 'experiments' | 'factors'

const EXIT_LABEL: Record<string, string> = {
  signal: '均线信号',
  stop_loss: '止损',
  time_exit: '时间退出',
  trailing_take_profit: '峰值回撤',
  end: '期末未平仓',
}

const OUTCOME_LABEL: Record<string, string> = {
  all: '全部事件',
  hit: '命中右尾',
  miss: '未命中右尾',
  stop_before_hit: '止损后才出现',
  hit_before_stop: '先出现后止损',
  no_hit_stop: '无右尾止损',
  same_day_ambiguous: '同日目标/止损',
}

const PURPOSE_LABEL: Record<string, string> = {
  entry_filter: '入场过滤',
  candidate_rank: '同日排序',
  hold_exit: '持有/退出',
  position: '仓位',
}

const STATUS_LABEL: Record<string, string> = {
  proposed: '待验证',
  testing: '验证中',
  adopted: '已采纳',
  rejected: '已否决',
  inconclusive: '无结论',
  pending: '待结论',
}

function pct(value: number | null | undefined) {
  return fmtPct(value, 2)
}

function pctInput(value: string): number[] {
  return value
    .split(',')
    .map(item => Number(item.trim().replace('%', '')))
    .filter(value => Number.isFinite(value) && value > 0 && value <= 1000)
    .map(value => value / 100)
}

export function StrategyResearchPage() {
  const [tab, setTab] = useState<Tab>('path')
  return (
    <>
      <PageHeader
        title="策略研究"
        subtitle="T74 右尾机会与退出兑现"
        right={
          <div className="flex items-center gap-1 rounded-btn border border-border bg-surface p-0.5">
            {([
              ['path', '路径诊断', Microscope],
              ['experiments', '实验对照', GitCompare],
              ['factors', '因子记录', FlaskConical],
            ] as const).map(([key, label, Icon]) => (
              <button
                key={key}
                type="button"
                onClick={() => setTab(key)}
                className={cn(
                  'inline-flex h-7 items-center gap-1.5 rounded-[5px] px-3 text-[11px] transition-colors',
                  tab === key
                    ? 'bg-accent/15 text-accent'
                    : 'text-secondary hover:text-foreground',
                )}
              >
                <Icon className="h-3.5 w-3.5" />
                {label}
              </button>
            ))}
          </div>
        }
      />
      <div className="min-h-0 flex-1 overflow-auto px-5 py-4">
        {tab === 'path' && <PathDiagnostics />}
        {tab === 'experiments' && <ExperimentCompare />}
        {tab === 'factors' && <FactorLedger />}
      </div>
    </>
  )
}

function PathDiagnostics() {
  const qc = useQueryClient()
  const inboxQ = useQuery({
    queryKey: QK.strategyResearchInbox,
    queryFn: api.strategyResearchInbox,
  })
  const reportsQ = useQuery({
    queryKey: QK.strategyResearchReports,
    queryFn: () => api.strategyResearchReports(),
  })
  const savedQ = useQuery({
    queryKey: QK.savedStrategyResults(1, 50),
    queryFn: () => api.savedStrategyBacktestResults(1, 50),
  })
  const reports = reportsQ.data?.items ?? []
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [sourceKind, setSourceKind] = useState<'file' | 'saved'>('file')
  const [file, setFile] = useState('')
  const [savedId, setSavedId] = useState('')
  const [horizon, setHorizon] = useState('20')
  const [thresholds, setThresholds] = useState('20,30,50')
  const [outcome, setOutcome] = useState('all')
  const [threshold, setThreshold] = useState<number | null>(null)
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(1)

  useEffect(() => {
    if (!selectedId && reports.length > 0) setSelectedId(reports[0].report_id)
  }, [reports, selectedId])

  const selected = useMemo(
    () => reports.find(item => item.report_id === selectedId) ?? null,
    [reports, selectedId],
  )

  useEffect(() => {
    setThreshold(selected?.config.thresholds[0] ?? null)
    setPage(1)
  }, [selected?.report_id])

  const eventsQ = useQuery({
    queryKey: QK.strategyResearchEvents(
      selectedId ?? '',
      threshold,
      outcome,
      query,
      page,
      30,
    ),
    queryFn: () =>
      api.strategyResearchEvents(selectedId!, {
        threshold: threshold ?? undefined,
        outcome,
        q: query || undefined,
        page,
        page_size: 30,
      }),
    enabled: !!selectedId,
  })

  const createMut = useMutation({
    mutationFn: () =>
      api.strategyResearchCreateReport({
        source:
          sourceKind === 'file'
            ? { kind: 'file', file_name: file }
            : { kind: 'saved', saved_id: savedId },
        horizon_sessions: Number(horizon) || 20,
        thresholds: pctInput(thresholds),
      }),
    onSuccess: result => {
      toast('路径报告已生成')
      setSelectedId(result.report.report_id)
      qc.invalidateQueries({ queryKey: QK.strategyResearchReports })
    },
  })

  const inbox = inboxQ.data?.items ?? []
  const savedResults = savedQ.data?.items ?? []
  const firstThreshold = selected?.config.thresholds[0] ?? null
  const thresholdSummary = selected?.summary.by_threshold.find(
    row => row.threshold === threshold,
  ) ?? selected?.summary.by_threshold[0]

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-2 rounded-card border border-border bg-surface p-3">
        <label className="flex w-28 flex-col gap-1">
          <span className="text-[10px] text-muted">基线来源</span>
          <select
            value={sourceKind}
            onChange={event => setSourceKind(event.target.value as 'file' | 'saved')}
            className="h-8 rounded-btn border border-border bg-panel px-2 text-xs text-foreground outline-none focus:border-accent/60"
          >
            <option value="file">Inbox JSON</option>
            <option value="saved">已保存结果</option>
          </select>
        </label>
        <label className="flex min-w-[280px] flex-1 flex-col gap-1">
          <span className="text-[10px] text-muted">基线</span>
          {sourceKind === 'file' ? (
            <select
              value={file}
              onChange={event => setFile(event.target.value)}
              className="h-8 rounded-btn border border-border bg-panel px-2 text-xs text-foreground outline-none focus:border-accent/60"
            >
              <option value="">从 research inbox 选择</option>
              {inbox.map(item => (
                <option key={item.file_name} value={item.file_name}>
                  {item.file_name}
                </option>
              ))}
            </select>
          ) : (
            <select
              value={savedId}
              onChange={event => setSavedId(event.target.value)}
              className="h-8 rounded-btn border border-border bg-panel px-2 text-xs text-foreground outline-none focus:border-accent/60"
            >
              <option value="">选择已保存回测</option>
              {savedResults.map(item => (
                <option key={item.saved_id} value={item.saved_id}>
                  {item.name || item.strategy_name || item.saved_id}
                </option>
              ))}
            </select>
          )}
        </label>
        <label className="flex w-24 flex-col gap-1">
          <span className="text-[10px] text-muted">未来交易日</span>
          <input
            value={horizon}
            onChange={event => setHorizon(event.target.value)}
            className="h-8 rounded-btn border border-border bg-panel px-2 text-xs text-foreground outline-none focus:border-accent/60"
          />
        </label>
        <label className="flex w-32 flex-col gap-1">
          <span className="text-[10px] text-muted">右尾阈值 %</span>
          <input
            value={thresholds}
            onChange={event => setThresholds(event.target.value)}
            className="h-8 rounded-btn border border-border bg-panel px-2 text-xs text-foreground outline-none focus:border-accent/60"
          />
        </label>
        <button
          type="button"
          disabled={
            (sourceKind === 'file' ? !file : !savedId)
            || pctInput(thresholds).length === 0
            || createMut.isPending
          }
          onClick={() => createMut.mutate()}
          className="inline-flex h-8 items-center gap-1.5 rounded-btn bg-accent px-3 text-xs font-medium text-white transition-colors hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {createMut.isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Plus className="h-3.5 w-3.5" />
          )}
          生成报告
        </button>
        <button
          type="button"
          onClick={() => {
            qc.invalidateQueries({ queryKey: QK.strategyResearchInbox })
            qc.invalidateQueries({ queryKey: QK.strategyResearchReports })
          }}
          className="grid h-8 w-8 place-items-center rounded-btn border border-border text-muted hover:text-foreground"
          title="刷新"
        >
          <RefreshCw className="h-3.5 w-3.5" />
        </button>
      </div>

      {reportsQ.isLoading ? (
        <div className="grid h-40 place-items-center text-xs text-muted">加载中</div>
      ) : reports.length === 0 ? (
        <EmptyState
          icon={Microscope}
          title="还没有路径报告"
          hint="把回测结果 JSON 放入 research inbox，再生成第一份事件路径报告。"
        />
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={selectedId ?? ''}
              onChange={event => setSelectedId(event.target.value)}
              className="h-8 min-w-[280px] rounded-btn border border-border bg-surface px-2 text-xs text-foreground outline-none focus:border-accent/60"
            >
              {reports.map(item => (
                <option key={item.report_id} value={item.report_id}>
                  {item.label}
                </option>
              ))}
            </select>
            {selected && (
              <span className="text-[10px] text-muted">
                {selected.baseline.start} ~ {selected.baseline.end} ·{' '}
                {selected.summary.event_count} 笔
              </span>
            )}
          </div>

          {selected && (
            <>
              <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                <Metric label="事件" value={String(selected.summary.event_count)} />
                <Metric
                  label="止损"
                  value={`${selected.summary.stop_loss_count} · ${pct(selected.summary.stop_loss_rate)}`}
                />
                <Metric
                  label={`右尾 ≥ ${pct(thresholdSummary?.threshold)}`}
                  value={`${thresholdSummary?.hit_count ?? 0} · ${pct(thresholdSummary?.hit_rate)}`}
                />
                <Metric
                  label="止损后才出现"
                  value={String(thresholdSummary?.stopped_before_hit_count ?? 0)}
                />
                <Metric
                  label="无右尾止损"
                  value={String(thresholdSummary?.no_hit_stopped_count ?? 0)}
                />
                <Metric
                  label="右尾后止损"
                  value={String(thresholdSummary?.hit_before_stop_count ?? 0)}
                />
                <Metric
                  label="实际兑现"
                  value={`${thresholdSummary?.actual_realized_count ?? 0} · ${pct(thresholdSummary?.actual_realized_rate)}`}
                />
                <Metric
                  label="到达前中位回撤"
                  value={pct(thresholdSummary?.median_pre_target_adverse_excursion)}
                />
              </div>

              <div className="flex flex-wrap items-center gap-2 rounded-card border border-border bg-surface p-2">
                <select
                  value={threshold ?? firstThreshold ?? ''}
                  onChange={event => {
                    setThreshold(Number(event.target.value))
                    setPage(1)
                  }}
                  className="h-7 rounded-btn border border-border bg-panel px-2 text-[11px] text-foreground outline-none"
                >
                  {selected.config.thresholds.map(value => (
                    <option key={value} value={value}>
                      ≥ {pct(value)}
                    </option>
                  ))}
                </select>
                <select
                  value={outcome}
                  onChange={event => {
                    setOutcome(event.target.value)
                    setPage(1)
                  }}
                  className="h-7 rounded-btn border border-border bg-panel px-2 text-[11px] text-foreground outline-none"
                >
                  {Object.entries(OUTCOME_LABEL).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
                <div className="relative">
                  <Search className="pointer-events-none absolute left-2 top-1.5 h-3.5 w-3.5 text-muted" />
                  <input
                    value={query}
                    onChange={event => {
                      setQuery(event.target.value)
                      setPage(1)
                    }}
                    placeholder="代码 / 事件"
                    className="h-7 w-44 rounded-btn border border-border bg-panel pl-7 pr-2 text-[11px] text-foreground outline-none placeholder:text-muted/70 focus:border-accent/60"
                  />
                </div>
                <span className="ml-auto text-[10px] text-muted">
                  {eventsQ.data?.total ?? 0} 条
                </span>
              </div>

              <div className="overflow-hidden rounded-card border border-border bg-surface">
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[1050px] border-collapse text-left text-[11px]">
                    <thead className="bg-panel text-muted">
                      <tr>
                        <Th>事件</Th>
                        <Th>入场</Th>
                        <Th>收益</Th>
                        <Th>最大上涨</Th>
                        <Th>最大回撤</Th>
                        <Th>目标日</Th>
                        <Th>到达前回撤</Th>
                        <Th>实际退出</Th>
                        <Th>标签</Th>
                      </tr>
                    </thead>
                    <tbody>
                      {(eventsQ.data?.items ?? []).map(event => (
                        <EventRow
                          key={event.event_id}
                          event={event}
                          threshold={threshold ?? firstThreshold}
                        />
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="flex items-center justify-between border-t border-border px-3 py-2 text-[10px] text-muted">
                  <button
                    type="button"
                    disabled={page <= 1}
                    onClick={() => setPage(value => Math.max(1, value - 1))}
                    className="rounded-btn border border-border px-2 py-1 disabled:opacity-40"
                  >
                    上一页
                  </button>
                  <span>第 {page} 页</span>
                  <button
                    type="button"
                    disabled={!eventsQ.data?.has_more}
                    onClick={() => setPage(value => value + 1)}
                    className="rounded-btn border border-border px-2 py-1 disabled:opacity-40"
                  >
                    下一页
                  </button>
                </div>
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-card border border-border bg-surface px-3 py-2">
      <div className="text-[10px] text-muted">{label}</div>
      <div className="mt-1 font-mono text-sm text-foreground">{value}</div>
    </div>
  )
}

function Th({ children }: { children: React.ReactNode }) {
  return <th className="whitespace-nowrap px-3 py-2 font-medium">{children}</th>
}

function EventRow({
  event,
  threshold,
}: {
  event: StrategyResearchEvent
  threshold: number | null
}) {
  const row = threshold == null
    ? event.thresholds[0]
    : event.thresholds.find(item => item.threshold === threshold) ?? event.thresholds[0]
  const tone = row?.hit
    ? 'text-danger'
    : row?.tail_vs_exit === 'stop_before_tail'
      ? 'text-warning'
      : 'text-muted'
  return (
    <tr className="border-t border-border/70 hover:bg-panel/60">
      <td className="whitespace-nowrap px-3 py-2 font-mono text-foreground">{event.event_id}</td>
      <td className="whitespace-nowrap px-3 py-2">
        <div className="font-mono text-foreground">{event.entry_date}</div>
        <div className="text-[10px] text-muted">{event.entry_price.toFixed(2)}</div>
      </td>
      <td className={cn('whitespace-nowrap px-3 py-2 font-mono', (event.pnl_pct ?? 0) >= 0 ? 'text-danger' : 'text-success')}>
        {pct(event.pnl_pct)}
      </td>
      <td className="whitespace-nowrap px-3 py-2 font-mono">{pct(event.max_favorable_excursion)}</td>
      <td className="whitespace-nowrap px-3 py-2 font-mono">{pct(event.max_adverse_excursion)}</td>
      <td className="whitespace-nowrap px-3 py-2 font-mono">
        {row?.first_target_date ?? '—'}
        {row?.days_to_target != null && (
          <span className="ml-1 text-[10px] text-muted">T+{row.days_to_target}</span>
        )}
      </td>
      <td className="whitespace-nowrap px-3 py-2 font-mono">
        {pct(row?.pre_target_adverse_excursion)}
      </td>
      <td className="whitespace-nowrap px-3 py-2">
        <div className={tone}>{EXIT_LABEL[event.exit_reason ?? ''] ?? event.exit_reason ?? '—'}</div>
        <div className="text-[10px] text-muted">{event.exit_date ?? '—'}</div>
      </td>
      <td className="whitespace-nowrap px-3 py-2">
        <span className={cn('rounded-full border px-2 py-0.5 text-[10px]', tone)}>
          {labelForOutcome(row?.tail_vs_exit)}
        </span>
      </td>
    </tr>
  )
}

function labelForOutcome(value: string | undefined) {
  if (value === 'stop_before_tail') return '止损后才出现'
  if (value === 'tail_before_stop') return '先出现后止损'
  if (value === 'tail_before_exit') return '右尾在退出前'
  if (value === 'tail_after_exit') return '右尾在退出后'
  if (value === 'no_tail') return '无右尾'
  if (value === 'unknown_exit') return '退出未知'
  return '不可评估'
}

function ExperimentCompare() {
  const qc = useQueryClient()
  const reportsQ = useQuery({
    queryKey: QK.strategyResearchReports,
    queryFn: () => api.strategyResearchReports(),
  })
  const experimentsQ = useQuery({
    queryKey: QK.strategyResearchExperiments,
    queryFn: api.strategyResearchExperiments,
  })
  const reports = reportsQ.data?.items ?? []
  const [controlId, setControlId] = useState('')
  const [variantId, setVariantId] = useState('')
  const [name, setName] = useState('')
  const [hypothesis, setHypothesis] = useState('')
  const [changedDecision, setChangedDecision] = useState('hold_exit')
  const [conclusion, setConclusion] = useState('pending')

  useEffect(() => {
    if (!controlId && reports[0]) setControlId(reports[0].report_id)
    if (!variantId && reports[1]) setVariantId(reports[1].report_id)
  }, [reports, controlId, variantId])

  const createMut = useMutation({
    mutationFn: () =>
      api.strategyResearchCreateExperiment({
        name,
        hypothesis,
        changed_decision: changedDecision,
        control_report_id: controlId,
        variant_report_id: variantId,
        conclusion,
      }),
    onSuccess: () => {
      toast('实验记录已保存')
      setName('')
      setHypothesis('')
      qc.invalidateQueries({ queryKey: QK.strategyResearchExperiments })
    },
  })

  const experiments = experimentsQ.data?.items ?? []
  return (
    <div className="space-y-4">
      <div className="grid gap-2 rounded-card border border-border bg-surface p-3 md:grid-cols-2 xl:grid-cols-6">
        <label className="flex flex-col gap-1">
          <span className="text-[10px] text-muted">对照</span>
          <select
            value={controlId}
            onChange={event => setControlId(event.target.value)}
            className="h-8 rounded-btn border border-border bg-panel px-2 text-[11px] text-foreground outline-none"
          >
            {reports.map(item => (
              <option key={item.report_id} value={item.report_id}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[10px] text-muted">变体</span>
          <select
            value={variantId}
            onChange={event => setVariantId(event.target.value)}
            className="h-8 rounded-btn border border-border bg-panel px-2 text-[11px] text-foreground outline-none"
          >
            {reports.map(item => (
              <option key={item.report_id} value={item.report_id}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[10px] text-muted">唯一改动</span>
          <select
            value={changedDecision}
            onChange={event => setChangedDecision(event.target.value)}
            className="h-8 rounded-btn border border-border bg-panel px-2 text-[11px] text-foreground outline-none"
          >
            {Object.entries(PURPOSE_LABEL).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[10px] text-muted">结论</span>
          <select
            value={conclusion}
            onChange={event => setConclusion(event.target.value)}
            className="h-8 rounded-btn border border-border bg-panel px-2 text-[11px] text-foreground outline-none"
          >
            {Object.entries(STATUS_LABEL).filter(([value]) => value === 'pending' || value === 'adopted' || value === 'rejected' || value === 'inconclusive').map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[10px] text-muted">实验名</span>
          <input
            value={name}
            onChange={event => setName(event.target.value)}
            className="h-8 rounded-btn border border-border bg-panel px-2 text-[11px] text-foreground outline-none"
          />
        </label>
        <button
          type="button"
          disabled={!controlId || !variantId || !name || !hypothesis || createMut.isPending}
          onClick={() => createMut.mutate()}
          className="mt-4 inline-flex h-8 items-center justify-center gap-1.5 rounded-btn bg-accent px-3 text-[11px] font-medium text-white disabled:opacity-50"
        >
          {createMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
          保存对照
        </button>
        <label className="flex flex-col gap-1 md:col-span-2 xl:col-span-6">
          <span className="text-[10px] text-muted">假设</span>
          <input
            value={hypothesis}
            onChange={event => setHypothesis(event.target.value)}
            className="h-8 rounded-btn border border-border bg-panel px-2 text-[11px] text-foreground outline-none"
          />
        </label>
      </div>

      {experiments.length === 0 ? (
        <EmptyState
          icon={GitCompare}
          title="还没有实验对照"
          hint="先分别生成对照和变体的路径报告，再按同一窗口与阈值配对。"
        />
      ) : (
        <div className="space-y-3">
          {experiments.map(experiment => (
            <div key={experiment.experiment_id} className="rounded-card border border-border bg-surface p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium text-foreground">{experiment.name}</span>
                <span className="rounded-full border border-border px-2 py-0.5 text-[10px] text-secondary">
                  {STATUS_LABEL[experiment.conclusion] ?? experiment.conclusion}
                </span>
                <span className="text-[10px] text-muted">
                  {String((experiment.control as { label?: string }).label ?? '')} →{' '}
                  {String((experiment.variant as { label?: string }).label ?? '')}
                </span>
              </div>
              <div className="mt-1 text-[11px] text-secondary">{experiment.hypothesis}</div>
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-muted">
                <span>
                  累计收益 {pct(experiment.comparison.control_stats?.total_return)} →{' '}
                  {pct(experiment.comparison.variant_stats?.total_return)}
                </span>
                <span>
                  最大回撤 {pct(experiment.comparison.control_stats?.max_drawdown)} →{' '}
                  {pct(experiment.comparison.variant_stats?.max_drawdown)}
                </span>
                <span>
                  交易 {experiment.comparison.control_event_count} →{' '}
                  {experiment.comparison.variant_event_count}
                </span>
              </div>
              <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                {experiment.comparison.by_threshold.map(row => (
                  <div key={row.threshold} className="rounded-btn border border-border/70 bg-panel p-2 text-[11px]">
                    <div className="flex items-center justify-between">
                      <span className="text-muted">右尾 ≥ {pct(row.threshold)}</span>
                      <span className="font-mono text-foreground">
                        保留 {row.both_hit_count}/{row.control_hit_count}
                      </span>
                    </div>
                    <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-secondary">
                      <span>丢失 {row.lost_tail_count}</span>
                      <span>新增 {row.gained_tail_count}</span>
                      <span>止损 {row.control_stop_loss_count}→{row.variant_stop_loss_count}</span>
                      <span>兑现 {row.control_actual_realized_count}→{row.variant_actual_realized_count}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function FactorLedger() {
  const qc = useQueryClient()
  const factorsQ = useQuery({
    queryKey: QK.strategyResearchFactors,
    queryFn: api.strategyResearchFactors,
  })
  const [form, setForm] = useState({
    factor_key: '',
    name: '',
    purpose: 'candidate_rank',
    earliest_known_at: 'T日收盘后',
    direction: '',
    missing_policy: '缺失不参与排序',
    hypothesis: '',
  })
  const createMut = useMutation({
    mutationFn: () =>
      api.strategyResearchCreateFactor({
        ...form,
        status: 'proposed',
      }),
    onSuccess: () => {
      toast('因子假设已保存')
      setForm({
        factor_key: '',
        name: '',
        purpose: 'candidate_rank',
        earliest_known_at: 'T日收盘后',
        direction: '',
        missing_policy: '缺失不参与排序',
        hypothesis: '',
      })
      qc.invalidateQueries({ queryKey: QK.strategyResearchFactors })
    },
  })
  const updateMut = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      api.strategyResearchUpdateFactor(id, { status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: QK.strategyResearchFactors }),
  })
  const factors = factorsQ.data?.items ?? []
  const set = (key: keyof typeof form) => (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm(value => ({ ...value, [key]: event.target.value }))

  return (
    <div className="space-y-4">
      <div className="grid gap-2 rounded-card border border-border bg-surface p-3 md:grid-cols-2 xl:grid-cols-4">
        <Field label="因子标识">
          <input value={form.factor_key} onChange={set('factor_key')} className={inputClass} />
        </Field>
        <Field label="名称">
          <input value={form.name} onChange={set('name')} className={inputClass} />
        </Field>
        <Field label="用途">
          <select value={form.purpose} onChange={set('purpose')} className={inputClass}>
            {Object.entries(PURPOSE_LABEL).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </Field>
        <Field label="最早可知">
          <input value={form.earliest_known_at} onChange={set('earliest_known_at')} className={inputClass} />
        </Field>
        <Field label="方向假设">
          <input value={form.direction} onChange={set('direction')} className={inputClass} />
        </Field>
        <Field label="缺失处理">
          <input value={form.missing_policy} onChange={set('missing_policy')} className={inputClass} />
        </Field>
        <Field label="假设" className="md:col-span-2">
          <input value={form.hypothesis} onChange={set('hypothesis')} className={inputClass} />
        </Field>
        <button
          type="button"
          disabled={!form.factor_key || !form.name || !form.hypothesis || createMut.isPending}
          onClick={() => createMut.mutate()}
          className="mt-4 inline-flex h-8 items-center justify-center gap-1.5 rounded-btn bg-accent px-3 text-[11px] font-medium text-white disabled:opacity-50"
        >
          {createMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
          保存因子
        </button>
      </div>

      {factors.length === 0 ? (
        <EmptyState
          icon={FlaskConical}
          title="还没有因子假设"
          hint="先写清用途、可知时点和缺失政策，再进入一次只改一个决策环节的实验。"
        />
      ) : (
        <div className="overflow-hidden rounded-card border border-border bg-surface">
          <table className="w-full border-collapse text-left text-[11px]">
            <thead className="bg-panel text-muted">
              <tr>
                <Th>因子</Th>
                <Th>用途</Th>
                <Th>可知时点</Th>
                <Th>假设</Th>
                <Th>状态</Th>
              </tr>
            </thead>
            <tbody>
              {factors.map(factor => (
                <tr key={factor.factor_id} className="border-t border-border/70">
                  <td className="px-3 py-2">
                    <div className="text-foreground">{factor.name}</div>
                    <div className="font-mono text-[10px] text-muted">{factor.factor_key}</div>
                  </td>
                  <td className="px-3 py-2 text-secondary">{PURPOSE_LABEL[factor.purpose] ?? factor.purpose}</td>
                  <td className="px-3 py-2 text-secondary">{factor.earliest_known_at}</td>
                  <td className="max-w-[420px] px-3 py-2 text-secondary">{factor.hypothesis}</td>
                  <td className="px-3 py-2">
                    <select
                      value={factor.status}
                      onChange={event => updateMut.mutate({ id: factor.factor_id, status: event.target.value })}
                      className="h-7 rounded-btn border border-border bg-panel px-2 text-[10px] text-foreground outline-none"
                    >
                      {Object.entries(STATUS_LABEL).filter(([value]) => value !== 'pending').map(([value, label]) => (
                        <option key={value} value={value}>{label}</option>
                      ))}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

const inputClass = 'h-8 rounded-btn border border-border bg-panel px-2 text-[11px] text-foreground outline-none focus:border-accent/60'

function Field({
  label,
  className,
  children,
}: {
  label: string
  className?: string
  children: React.ReactNode
}) {
  return (
    <label className={cn('flex flex-col gap-1', className)}>
      <span className="text-[10px] text-muted">{label}</span>
      {children}
    </label>
  )
}
