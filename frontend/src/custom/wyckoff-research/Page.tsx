import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, CalendarRange, Loader2, RefreshCw, Search, X } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { EmptyState } from '@/components/EmptyState'
import { DatePicker } from '@/components/DatePicker'
import { StockFinancialSearch } from '@/components/financials/StockFinancialSearch'
import { StockDailyKChart } from '@/components/StockDailyKChart'
import { useLastStock } from '@/lib/useLastStock'
import { api, type WyckoffEvidenceCondition, type WyckoffResearchEvent, type WyckoffResearchResponse } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { cn } from '@/lib/cn'
import type { ChartMarker, ChartPriceLine, ChartRange } from '@/components/EChartsCandlestick'

/**
 * 威科夫研究页 —— 单股、日线、只读研究显示（方案 A 独立扩展页）。
 *
 * 边界：
 *  - 研究开关默认关闭，关闭与未选标的时都不发起事件查询；
 *  - 图表与事件共用同一 as_of；截止日之后的确认与失效一律不出现（后端按输入截断 fail-closed）；
 *  - 标记落在 confirmed_at，形态日只在证据与表格里出现，不倒标历史极值；
 *  - 事件阈值由规格装载，未冻结时页面显式标注，不宣称规则有效，不提供买卖建议。
 */

const WINDOW_CHOICES = [60, 120, 250]
/** 预热根数与后端规格一致：日历日按 1.7 倍交易日折算，再加固定余量覆盖长假。 */
const WARMUP_BARS = 30

type ViewState =
  | { kind: 'off' }
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

function eventStatus(event: WyckoffResearchEvent, invalidated: Set<string>) {
  if (invalidated.has(event.event_id)) return { label: '已失效', className: 'text-warning' }
  if (event.status === 'candidate') return { label: '候选', className: 'text-muted' }
  return { label: '已确认', className: 'text-accent' }
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

export function WyckoffResearchPage() {
  const { last, remember } = useLastStock('wyckoff-research')
  const [symbol, setSymbol] = useState(last?.symbol ?? '')
  const [name, setName] = useState(last?.name ?? '')
  const [enabled, setEnabled] = useState(false)
  const [asOf, setAsOf] = useState<string | null>(null)
  const [windowBars, setWindowBars] = useState(120)
  const [structureLayer, setStructureLayer] = useState(true)
  const [invalidationLayer, setInvalidationLayer] = useState(true)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const eventsQ = useQuery({
    queryKey: QK.wyckoffEvents(symbol, asOf, windowBars, null),
    queryFn: () => api.wyckoffResearchEvents({ symbol, asOf, window: windowBars }),
    enabled: enabled && !!symbol,
    retry: 1,
    staleTime: 60_000,
  })

  const state: ViewState = !enabled
    ? { kind: 'off' }
    : !symbol
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
    if (state.kind === 'off') return { label: '未启用', className: 'text-muted' }
    if (state.kind === 'no-symbol') return { label: '待选标的', className: 'text-muted' }
    if (state.kind === 'loading') return { label: '读取中', className: 'text-secondary' }
    if (state.kind === 'error') return { label: '请求失败', className: 'text-danger' }
    const status = state.data.status
    if (status === 'ready') return state.data.events.length
      ? { label: '示例快照', className: 'text-secondary' }
      : { label: '无事件', className: 'text-muted' }
    if (status === 'no_daily') return { label: '无日线', className: 'text-muted' }
    if (status === 'insufficient_data') return { label: '历史不足', className: 'text-warning' }
    if (status === 'not_computable') return { label: '不可计算', className: 'text-warning' }
    if (status === 'spec_missing') return { label: '规格缺失', className: 'text-warning' }
    return { label: '数据换代', className: 'text-warning' }
  })()

  const statusHint = (text: string) => (
    <div className="flex items-center justify-center gap-2 py-10 text-[11px] text-muted">{text}</div>
  )

  return (
    <div className="h-full min-h-0 flex flex-col">
      <PageHeader
        title="威科夫研究"
        right={
          <div className="flex items-center gap-3">
            <span className={cn('text-[11px] tabular', badge.className)}>{badge.label}</span>
            <button
              type="button"
              role="switch"
              aria-checked={enabled}
              aria-label="开启威科夫研究"
              onClick={() => setEnabled(value => !value)}
              className={cn(
                'relative h-4 w-7 shrink-0 rounded-full transition-colors',
                enabled ? 'bg-accent/60' : 'bg-elevated hover:bg-elevated/80',
              )}
            >
              <span
                className={cn(
                  'absolute top-0.5 h-3 w-3 rounded-full transition-all',
                  enabled ? 'left-[14px] bg-white' : 'left-0.5 bg-muted',
                )}
              />
            </button>
          </div>
        }
      />

      <div className="flex flex-wrap items-center gap-2 border-b border-border/70 px-5 py-2">
        <div className="w-[220px]">
          <StockFinancialSearch
            assetTypes="stock"
            onSelect={(nextSymbol, nextName) => {
              setSymbol(nextSymbol)
              setName(nextName)
              remember(nextSymbol, nextName)
            }}
          />
        </div>
        {symbol && (
          <span className="text-[11px] text-secondary num">{symbol} {name}</span>
        )}
        <div className="flex items-center gap-1 text-[11px]">
          <CalendarRange className="h-3.5 w-3.5 text-muted" strokeWidth={1.5} />
          <DatePicker value={asOf ?? ''} onChange={value => setAsOf(value || null)} max={new Date().toISOString().slice(0, 10)} placeholder="截止日期" />
          {asOf && (
            <button type="button" className="text-muted hover:text-foreground" onClick={() => setAsOf(null)} aria-label="清除截止日期">
              <X className="h-3.5 w-3.5" strokeWidth={1.5} />
            </button>
          )}
        </div>
        <div className="flex items-center gap-0.5">
          {WINDOW_CHOICES.map(size => (
            <button
              key={size}
              type="button"
              aria-pressed={windowBars === size}
              onClick={() => setWindowBars(size)}
              className={cn(
                'h-5 rounded px-2 text-[11px] tabular',
                windowBars === size ? 'bg-accent/20 text-accent' : 'text-muted hover:bg-elevated hover:text-secondary',
              )}
            >
              {size}日
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            aria-pressed={structureLayer}
            onClick={() => setStructureLayer(value => !value)}
            className={cn('h-5 rounded px-2 text-[11px]', structureLayer ? 'bg-accent/20 text-accent' : 'text-muted hover:bg-elevated')}
          >
            结构事件
          </button>
          <button
            type="button"
            aria-pressed={invalidationLayer}
            onClick={() => setInvalidationLayer(value => !value)}
            className={cn('h-5 rounded px-2 text-[11px]', invalidationLayer ? 'bg-warning/20 text-warning' : 'text-muted hover:bg-elevated')}
          >
            失效
          </button>
        </div>
      </div>

      {state.kind === 'off' && <EmptyState icon={AlertTriangle} title="研究未启用" hint="开启后按截止日期读取日线事件快照；关闭时不发起请求。" />}
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
          <div className="grid flex-1 min-h-0 grid-cols-1 gap-3 px-5 py-3 xl:grid-cols-[minmax(0,1fr)_320px]">
            <div className="min-w-0">
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
                height={360}
                onDateClick={date => {
                  const hit = events.find(event => event.confirmed_at === date)
                  if (hit) setSelectedId(hit.event_id)
                }}
              />
            </div>
            <aside className="min-w-0 border-l border-border/70 pl-3">
              {selected ? (
                <div className="space-y-2">
                  <div className="flex items-baseline justify-between gap-2">
                    <h2 className="text-[13px] font-medium">{selected.event_type} · {selected.phase}</h2>
                    <span className={cn('text-[11px]', eventStatus(selected, invalidated).className)}>
                      {eventStatus(selected, invalidated).label}
                    </span>
                  </div>
                  <dl className="space-y-0.5 text-[11px]">
                    <div className="flex justify-between gap-2"><dt className="text-muted">形态日</dt><dd className="num">{selected.pattern_date}</dd></div>
                    <div className="flex justify-between gap-2"><dt className="text-muted">确认日</dt><dd className="num">{selected.confirmed_at ?? '未确认'}</dd></div>
                    <div className="flex justify-between gap-2"><dt className="text-muted">可用边界</dt><dd className="num">{selected.available_at ? `${selected.available_at} 收盘后` : '不可计算'}</dd></div>
                    <div className="flex justify-between gap-2"><dt className="text-muted">规则版本</dt><dd className="num">{selected.rule_version}</dd></div>
                    <div className="flex justify-between gap-2"><dt className="text-muted">数据</dt><dd className="num">{selected.data_generation ?? '-'}</dd></div>
                  </dl>
                  {selected.linked_event_id && (
                    <button
                      type="button"
                      className="text-[11px] text-accent hover:underline"
                      onClick={() => setSelectedId(selected.linked_event_id)}
                    >
                      关联事件 {selected.linked_event_id}
                    </button>
                  )}
                  <table className="w-full text-[11px]">
                    <thead className="text-muted">
                      <tr><th className="text-left font-normal">条件</th><th className="text-right font-normal">实际</th><th className="text-right font-normal">阈值</th><th className="text-right font-normal">窗口</th></tr>
                    </thead>
                    <tbody>
                      {selected.evidence.map(condition => (
                        <tr key={condition.name} className="border-t border-border/50">
                          <td className="py-0.5">{condition.name}</td>
                          <td className={cn('py-0.5 text-right num', !condition.computable && 'text-warning')}>{formatActual(condition)}</td>
                          <td className="py-0.5 text-right num">{condition.threshold}</td>
                          <td className="py-0.5 text-right num">{condition.window}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <p className="text-[11px] text-secondary">失效规则：{selected.invalidation_rule}</p>
                </div>
              ) : (
                statusHint('该截止日期窗口内无事件证据')
              )}
            </aside>
          </div>

          <div className="border-t border-border/70 px-5 py-2">
            <div className="flex items-center justify-between">
              <h2 className="text-[12px] font-medium">事件</h2>
              <span className="text-[11px] text-muted tabular">{events.length} 条 · 截至 {data.as_of}</span>
            </div>
            {events.length === 0 ? (
              statusHint('窗口内无确认事件；确认前不显示标记')
            ) : (
              <div className="mt-1 max-h-[200px] overflow-auto">
                <table className="w-full text-[11px]" data-testid="event-table">
                  <thead className="sticky top-0 bg-surface text-muted">
                    <tr>
                      <th className="py-1 pr-2 text-left font-normal">事件</th>
                      <th className="py-1 pr-2 text-left font-normal">阶段</th>
                      <th className="py-1 pr-2 text-right font-normal">形态日</th>
                      <th className="py-1 pr-2 text-right font-normal">确认日</th>
                      <th className="py-1 pr-2 text-left font-normal">状态</th>
                      <th className="py-1 text-left font-normal">关键证据</th>
                    </tr>
                  </thead>
                  <tbody>
                    {events.map(event => {
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
                            'cursor-pointer border-t border-border/40 hover:bg-elevated/60',
                            event.event_id === selected?.event_id && 'bg-accent/10',
                          )}
                        >
                          <td className="py-1 pr-2">{event.event_type}</td>
                          <td className="py-1 pr-2 text-secondary">{event.phase}</td>
                          <td className="py-1 pr-2 text-right num">{event.pattern_date}</td>
                          <td className="py-1 pr-2 text-right num">{event.confirmed_at ?? '—'}</td>
                          <td className={cn('py-1 pr-2', status.className)}>{status.label}</td>
                          <td className="py-1 text-secondary">{keyEvidence(event)}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
            <p className="mt-1 text-[11px] text-muted">
              {data.spec_status === 'unfrozen_demo' ? '规则未冻结，事件口径仅供界面与状态验收' : `规则 ${data.rule_version} · 参数 ${data.params_hash}`}
            </p>
          </div>
        </>
      )}
    </div>
  )
}
