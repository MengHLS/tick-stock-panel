import { useCallback, useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, ArrowUpRight, CalendarRange, Loader2, RefreshCw, Search, X } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { EmptyState } from '@/components/EmptyState'
import { DatePicker } from '@/components/DatePicker'
import { StockFinancialSearch } from '@/components/financials/StockFinancialSearch'
import { StockDailyKChart } from '@/components/StockDailyKChart'
import { WatchlistPanel } from '@/components/watchlist'
import { api, type WyckoffEvidenceCondition, type WyckoffResearchEvent, type WyckoffResearchResponse } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { cn } from '@/lib/cn'
import type { ChartMarker, ChartPriceLine, ChartRange } from '@/components/EChartsCandlestick'

/**
 * 威科夫研究页 —— 单股、日线、只读研究显示（方案 A 独立扩展页）。
 *
 * 边界：
 *  - 进入页面即工作：标的由左侧自选面板默认选中第一只，不设研究开关；
 *  - 图表与事件共用同一 as_of；截止日之后的确认与失效一律不出现（后端按输入截断 fail-closed）；
 *  - 标记落在 confirmed_at，形态日只在证据与表格里出现，不倒标历史极值；
 *  - 事件阈值由规格装载，未冻结时页面显式标注，不宣称规则有效，不提供买卖建议。
 */

const WINDOW_CHOICES = [60, 120, 250]
/** 预热根数与后端规格一致：日历日按 1.7 倍交易日折算，再加固定余量覆盖长假。 */
const WARMUP_BARS = 30

type Tone = 'accent' | 'warning' | 'danger' | 'muted'

const TONE_TEXT: Record<Tone, string> = {
  accent: 'text-accent',
  warning: 'text-warning',
  danger: 'text-danger',
  muted: 'text-muted',
}

type ViewState =
  | { kind: 'no-symbol' }
  | { kind: 'loading' }
  | { kind: 'error' }
  | { kind: 'payload'; data: WyckoffResearchResponse }

function isConfirmed(event: WyckoffResearchEvent) {
  return event.status === 'confirmed' && !!event.confirmed_at
}

function invalidationTargets(events: WyckoffResearchEvent[]) {
  const targets = new Set<string>()
  for (const event of events) {
    if (event.event_type === '失效' && event.linked_event_id) targets.add(event.linked_event_id)
  }
  return targets
}

function eventStatus(event: WyckoffResearchEvent, invalidated: Set<string>): { label: string; tone: Tone } {
  if (invalidated.has(event.event_id)) return { label: '已失效', tone: 'warning' }
  if (event.status === 'candidate') return { label: '候选', tone: 'muted' }
  return { label: '已确认', tone: 'accent' }
}

function formatActual(condition: WyckoffEvidenceCondition) {
  if (!condition.computable || condition.actual === null || condition.actual === undefined) return '不可计算'
  return typeof condition.actual === 'number' ? condition.actual.toFixed(2) : condition.actual
}

function keyEvidence(event: WyckoffResearchEvent) {
  const first = event.evidence[0]
  if (!first) return event.invalidation_rule
  return `${first.name} · ${formatActual(first)} ${first.threshold}`
}

/** 排序：确认日倒序，候选按形态日排在已确认之后。 */
function sortEvents(events: WyckoffResearchEvent[]) {
  return [...events].sort((left, right) => {
    const leftKey = left.confirmed_at ?? ''
    const rightKey = right.confirmed_at ?? ''
    if (leftKey !== rightKey) return rightKey.localeCompare(leftKey)
    return right.pattern_date.localeCompare(left.pattern_date)
  })
}

function StatusPill({ label, tone }: { label: string; tone: Tone }) {
  return (
    <span className={cn('inline-flex items-center gap-1.5 whitespace-nowrap text-[11px]', TONE_TEXT[tone])}>
      <span className={cn('h-1.5 w-1.5 rounded-full bg-current', tone === 'muted' && 'opacity-60')} />
      {label}
    </span>
  )
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return <span className="text-[10px] tracking-wide text-muted">{children}</span>
}

export function WyckoffResearchPage() {
  const [symbol, setSymbol] = useState('')
  const [name, setName] = useState('')
  const [asOf, setAsOf] = useState<string | null>(null)
  const [windowBars, setWindowBars] = useState(120)
  const [structureLayer, setStructureLayer] = useState(true)
  const [invalidationLayer, setInvalidationLayer] = useState(true)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const eventsQ = useQuery({
    queryKey: QK.wyckoffEvents(symbol, asOf, windowBars, null),
    queryFn: () => api.wyckoffResearchEvents({ symbol, asOf, window: windowBars }),
    enabled: !!symbol,
    retry: 1,
    staleTime: 60_000,
  })
  const selectStock = useCallback((nextSymbol: string, nextName: string | null) => {
    setSymbol(nextSymbol)
    setName(nextName ?? '')
  }, [])

  const state: ViewState = !symbol
    ? { kind: 'no-symbol' }
    : eventsQ.isPending
      ? { kind: 'loading' }
      : eventsQ.isError
        ? { kind: 'error' }
        : { kind: 'payload', data: eventsQ.data }

  const data = state.kind === 'payload' ? state.data : null
  const events = useMemo(() => sortEvents(data?.events ?? []), [data])
  const invalidated = useMemo(() => invalidationTargets(events), [events])
  const selected = useMemo(
    () => events.find(event => event.event_id === selectedId) ?? events.find(event => isConfirmed(event) && event.event_type !== '失效') ?? null,
    [events, selectedId],
  )
  const selectedStatus = selected ? eventStatus(selected, invalidated) : null

  // 切换标的或窗口后旧选中失效，回落到最近一条已确认事件。
  useEffect(() => {
    setSelectedId(null)
  }, [symbol, windowBars, asOf])

  // 图表与事件共用同一 as_of：服务端把截止日回钳到最后一根已完成日线后，以其返回值为准
  const chartRange = useMemo(() => {
    const end = data?.as_of ?? asOf ?? new Date().toISOString().slice(0, 10)
    const startDate = new Date(end)
    startDate.setDate(startDate.getDate() - Math.round((windowBars + WARMUP_BARS) * 1.7))
    return { start: startDate.toISOString().slice(0, 10), end }
  }, [data?.as_of, asOf, windowBars])

  const markers: ChartMarker[] = useMemo(() => {
    if (!data) return []
    const rows: ChartMarker[] = []
    for (const event of events) {
      if (!isConfirmed(event)) continue
      const isInvalidate = event.event_type === '失效'
      if (isInvalidate ? !invalidationLayer : !structureLayer) continue
      rows.push({
        date: event.confirmed_at as string,
        kind: 'neutral',
        label: isInvalidate ? '失效' : event.event_type,
        color: isInvalidate ? '#F79009' : undefined,
      })
    }
    return rows
  }, [data, events, invalidationLayer, selected?.event_id, structureLayer])

  // 只画选中事件形态当时已知的边界；不回放未来完成的箱体
  const knownLevels = selected?.levels ?? {}
  const support = knownLevels.support
  const resistance = knownLevels.resistance
  const ranges: ChartRange[] = support !== undefined && resistance !== undefined
    ? [{ start: selected?.pattern_date ?? chartRange.start, end: data?.as_of ?? chartRange.end, label: '已知区间' }]
    : []
  const priceLines: ChartPriceLine[] = []
  if (support !== undefined) priceLines.push({ value: support, label: `支撑 ${support.toFixed(2)}`, start: selected?.pattern_date, end: data?.as_of })
  if (resistance !== undefined) priceLines.push({ value: resistance, label: `阻力 ${resistance.toFixed(2)}`, start: selected?.pattern_date, end: data?.as_of })

  const badge = (() => {
    if (state.kind === 'no-symbol') return { label: '待选标的', tone: 'muted' as Tone }
    if (state.kind === 'loading') return { label: '读取中', tone: 'muted' as Tone }
    if (state.kind === 'error') return { label: '请求失败', tone: 'danger' as Tone }
    const status = state.data.status
    if (status === 'ready') return state.data.events.length
      ? { label: '快照就绪', tone: 'accent' as Tone }
      : { label: '无事件', tone: 'muted' as Tone }
    if (status === 'no_daily') return { label: '无日线', tone: 'muted' as Tone }
    if (status === 'insufficient_data') return { label: '历史不足', tone: 'warning' as Tone }
    if (status === 'not_computable') return { label: '不可计算', tone: 'warning' as Tone }
    if (status === 'spec_missing') return { label: '规格缺失', tone: 'warning' as Tone }
    return { label: '数据换代', tone: 'warning' as Tone }
  })()

  const statusHint = (text: string) => (
    <div className="mx-4 my-3 flex items-center justify-center rounded-xl border border-border/60 bg-surface/40 px-4 py-12 text-[12px] text-muted">
      {text}
    </div>
  )

  return (
    <div className="h-full min-h-0 flex flex-col">
      <PageHeader
        title="威科夫研究"
        right={<StatusPill label={badge.label} tone={badge.tone} />}
      />

      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-border/70 bg-surface/40 px-5 py-2.5">
        <div className="w-[220px]">
          <StockFinancialSearch
            assetTypes="stock"
            onSelect={selectStock}
          />
        </div>
        {symbol && (
          <span className="inline-flex items-baseline gap-1.5 rounded-md bg-elevated/50 px-2 py-1 text-[11px]">
            <span className="num text-secondary">{symbol}</span>
            {name && <span className="text-muted">{name}</span>}
          </span>
        )}
        <span className="hidden h-4 w-px bg-border/70 sm:block" />
        <div className="flex items-center gap-1 rounded-md bg-elevated/50 px-1.5 py-1 text-[11px]">
          <CalendarRange className="h-3.5 w-3.5 text-muted" strokeWidth={1.5} />
          <DatePicker value={asOf ?? ''} onChange={value => setAsOf(value || null)} max={new Date().toISOString().slice(0, 10)} placeholder="截止日期" />
          {asOf && (
            <button type="button" className="text-muted hover:text-foreground" onClick={() => setAsOf(null)} aria-label="清除截止日期">
              <X className="h-3.5 w-3.5" strokeWidth={1.5} />
            </button>
          )}
        </div>
        <div className="flex items-center gap-0.5 rounded-md bg-elevated/50 p-0.5">
          {WINDOW_CHOICES.map(size => (
            <button
              key={size}
              type="button"
              aria-pressed={windowBars === size}
              onClick={() => setWindowBars(size)}
              className={cn(
                'h-5 rounded px-2 text-[11px] tabular transition-colors',
                windowBars === size ? 'bg-accent/15 text-accent' : 'text-muted hover:text-secondary',
              )}
            >
              {size}日
            </button>
          ))}
        </div>
        <div className="flex items-center gap-0.5 rounded-md bg-elevated/50 p-0.5">
          <button
            type="button"
            aria-pressed={structureLayer}
            onClick={() => setStructureLayer(value => !value)}
            className={cn('h-5 rounded px-2 text-[11px] transition-colors', structureLayer ? 'bg-accent/15 text-accent' : 'text-muted hover:text-secondary')}
          >
            结构事件
          </button>
          <button
            type="button"
            aria-pressed={invalidationLayer}
            onClick={() => setInvalidationLayer(value => !value)}
            className={cn('h-5 rounded px-2 text-[11px] transition-colors', invalidationLayer ? 'bg-warning/15 text-warning' : 'text-muted hover:text-secondary')}
          >
            失效
          </button>
        </div>
      </div>

      <div className="flex min-h-0 flex-1">
        <WatchlistPanel
          className="hidden w-[176px] shrink-0 border-r border-border/70 lg:flex"
          activeSymbol={symbol}
          autoSelectFirst
          onSelect={selectStock}
        />
        <div className="flex min-w-0 flex-1 flex-col">
      {state.kind === 'no-symbol' && <EmptyState icon={Search} title="未选标的" hint="搜索并选择一只股票；未选标的时不请求事件。" />}
      {state.kind === 'loading' && (
        <div className="flex items-center justify-center gap-2 py-16 text-secondary">
          <Loader2 className="h-4 w-4 animate-spin" />
          <span className="text-[12px]">读取事件</span>
        </div>
      )}
      {state.kind === 'error' && (
        <div className="flex flex-col items-center">
          <EmptyState icon={AlertTriangle} title="请求失败" hint="保留当前参数，重试后重新读取。" />
          <button
            type="button"
            onClick={() => void eventsQ.refetch()}
            className="mb-6 inline-flex items-center gap-1.5 rounded border border-border px-2.5 py-1 text-[11px] text-secondary hover:bg-elevated"
          >
            <RefreshCw className="h-3.5 w-3.5" strokeWidth={1.5} />重试
          </button>
        </div>
      )}

      {data && data.status !== 'ready' && (
        <div className="px-5">
          {data.status === 'no_daily' && statusHint(`${symbol} 在本地日线中无可用数据`)}
          {data.status === 'insufficient_data' && statusHint(
            `需要 ${data.required_bars} 交易日（含预热），当前只有 ${data.observed_bars} 根，不输出事件`,
          )}
          {data.status === 'not_computable' && statusHint(`缺少计算字段：${(data.missing_columns ?? []).join('、')}；缺失即不可计算`)}
          {data.status === 'spec_missing' && statusHint(`规格字段缺失：${(data.missing_fields ?? []).join('、')}`)}
          {data.status === 'generation_changed' && statusHint(`读取期间数据换代 ${data.data_generation ?? '-'} → ${data.observed_generation ?? '-'}，本次不混合新旧数据`)}
        </div>
      )}

      {(state.kind === 'payload' && data && data.status === 'ready') && (
        <>
          <div className="grid flex-1 min-h-0 grid-cols-1 gap-3 px-4 py-3 xl:grid-cols-[minmax(0,1fr)_340px]">
            <section className="flex min-w-0 flex-col overflow-hidden rounded-xl border border-border/60 bg-surface/50">
              <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-border/50 px-3 py-2">
                <span className="text-[13px] font-medium">{name || symbol}</span>
                <span className="num text-[10px] text-muted">{symbol}</span>
                <span className="text-[10px] text-muted">日 K · 前复权</span>
                <span className="ml-auto num text-[10px] text-muted">as_of {data.as_of} · {events.length} 事件</span>
              </header>
              <div className="min-h-0 flex-1 px-1 pb-1 pt-2">
              <StockDailyKChart
                symbol={symbol}
                dateRange={chartRange}
                visibleBars={windowBars}
                markers={markers}
                ranges={ranges}
                priceLines={priceLines}
                showLimitMarkers={false}
                showMarkerToggle={false}
                showIndicatorControls={false}
                height={380}
                onDateClick={date => {
                  const hit = events.find(event => event.confirmed_at === date)
                  if (hit) setSelectedId(hit.event_id)
                }}
              />
              </div>
              <footer className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-border/50 px-3 py-1.5 text-[10px] text-muted">
                <span>支撑 <span className="num text-secondary">{support !== undefined ? support.toFixed(2) : '不可计算'}</span></span>
                <span>阻力 <span className="num text-secondary">{resistance !== undefined ? resistance.toFixed(2) : '不可计算'}</span></span>
                <span className="ml-auto truncate num">generation {data.data_generation ?? '-'}</span>
              </footer>
            </section>
            <aside className="flex min-w-0 flex-col overflow-hidden rounded-xl border border-border/60 bg-surface/50 p-3">
              {selected && selectedStatus ? (
                <div className="flex h-full flex-col gap-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex min-w-0 items-baseline gap-1.5">
                      <h2 className="truncate text-[13px] font-medium">{selected.event_type}</h2>
                      <span className="truncate text-[11px] text-muted">{selected.phase}</span>
                    </div>
                    <StatusPill label={selectedStatus.label} tone={selectedStatus.tone} />
                  </div>

                  <div className="grid grid-cols-2 gap-x-3 gap-y-2 rounded-lg bg-elevated/40 px-2.5 py-2">
                    <div className="flex flex-col gap-0.5"><FieldLabel>形态日</FieldLabel><span className="num text-[11px]">{selected.pattern_date}</span></div>
                    <div className="flex flex-col gap-0.5"><FieldLabel>确认日</FieldLabel><span className="num text-[11px]">{selected.confirmed_at ?? '未确认'}</span></div>
                    <div className="flex flex-col gap-0.5"><FieldLabel>可用边界</FieldLabel><span className="text-[11px]">{selected.available_at ? `${selected.available_at} 收盘后` : '不可计算'}</span></div>
                    <div className="flex flex-col gap-0.5"><FieldLabel>数据</FieldLabel><span className="truncate num text-[11px]">{selected.data_generation ?? '-'}</span></div>
                  </div>

                  {selected.linked_event_id && (
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 self-start text-[11px] text-accent hover:underline"
                      onClick={() => setSelectedId(selected.linked_event_id!)}
                    >
                      关联事件 {selected.linked_event_id}
                      <ArrowUpRight className="h-3 w-3" strokeWidth={1.5} />
                    </button>
                  )}

                  <div className="min-h-0">
                    <FieldLabel>条件证据</FieldLabel>
                    <table className="mt-1 w-full text-[11px]">
                      <thead className="text-muted">
                        <tr><th className="pb-1 text-left font-normal">条件</th><th className="pb-1 text-right font-normal">实际</th><th className="pb-1 text-right font-normal">阈值</th><th className="pb-1 text-right font-normal">窗口</th></tr>
                      </thead>
                      <tbody>
                        {selected.evidence.map(condition => (
                          <tr key={condition.name} className="border-t border-border/40">
                            <td className="py-1 pr-2">{condition.name}</td>
                            <td className={cn('py-1 pr-2 text-right num', !condition.computable && 'text-warning')}>{formatActual(condition)}</td>
                            <td className="py-1 pr-2 text-right num">{condition.threshold}</td>
                            <td className="py-1 text-right num">{condition.window}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  <div className="mt-auto rounded-lg border border-border/50 bg-elevated/30 px-2.5 py-2">
                    <FieldLabel>失效规则</FieldLabel>
                    <p className="mt-0.5 text-[11px] text-secondary">{selected.invalidation_rule}</p>
                  </div>
                </div>
              ) : (
                statusHint('该截止日期窗口内无事件证据')
              )}
            </aside>
          </div>

          <section className="mx-4 mb-4 overflow-hidden rounded-xl border border-border/60 bg-surface/50">
            <header className="flex items-center justify-between gap-3 border-b border-border/50 px-3 py-2">
              <div className="flex items-baseline gap-2">
                <h2 className="text-[12px] font-medium">事件</h2>
                <span className="num text-[10px] text-muted">{events.length} 条</span>
              </div>
              <span className="num text-[10px] text-muted">截至 {data.as_of}</span>
            </header>
            {events.length === 0 ? (
              <div className="px-3 py-10 text-center text-[12px] text-muted">窗口内无确认事件；确认前不显示标记</div>
            ) : (
              <div className="max-h-[240px] overflow-auto">
                <table className="w-full text-[11px]" data-testid="event-table">
                  <thead className="sticky top-0 bg-surface/95 text-muted backdrop-blur">
                    <tr>
                      <th className="px-3 py-1.5 text-left font-normal">事件</th>
                      <th className="px-3 py-1.5 text-left font-normal">阶段</th>
                      <th className="px-3 py-1.5 text-right font-normal">形态日</th>
                      <th className="px-3 py-1.5 text-right font-normal">确认日</th>
                      <th className="px-3 py-1.5 text-left font-normal">状态</th>
                      <th className="px-3 py-1.5 text-left font-normal">关键证据</th>
                    </tr>
                  </thead>
                  <tbody>
                    {events.map((event, index) => {
                      const status = eventStatus(event, invalidated)
                      return (
                        <tr
                          key={event.event_id}
                          tabIndex={0}
                          aria-selected={event.event_id === selected?.event_id}
                          onClick={() => setSelectedId(event.event_id)}
                          onKeyDown={key => {
                            if (key.key === 'Enter' || key.key === ' ') {
                              key.preventDefault()
                              setSelectedId(event.event_id)
                            }
                          }}
                          className={cn(
                            'cursor-pointer border-t border-border/40 transition-colors hover:bg-elevated/60',
                            index % 2 === 1 && 'bg-elevated/20',
                            event.event_id === selected?.event_id && 'bg-accent/10 hover:bg-accent/10',
                          )}
                        >
                          <td className="px-3 py-1.5">{event.event_type}</td>
                          <td className="px-3 py-1.5 text-secondary">{event.phase}</td>
                          <td className="px-3 py-1.5 text-right num">{event.pattern_date}</td>
                          <td className="px-3 py-1.5 text-right num">{event.confirmed_at ?? '—'}</td>
                          <td className="px-3 py-1.5"><StatusPill label={status.label} tone={status.tone} /></td>
                          <td className="px-3 py-1.5 text-secondary">{keyEvidence(event)}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
            <footer className="border-t border-border/50 px-3 py-1.5 text-[10px] text-muted">
              {data.spec_status === 'unfrozen_demo' ? '规则未冻结，事件口径仅供界面与状态验收' : `规则 ${data.rule_version} · 参数 ${data.params_hash}`}
            </footer>
          </section>
        </>
      )}
        </div>
      </div>
    </div>
  )
}
