import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import * as echarts from 'echarts'
import { keepPreviousData } from '@tanstack/react-query'
import { ArrowRight, Loader2, RefreshCw, TrendingDown, TrendingUp, Minus } from 'lucide-react'
import { api, type MaxBoardEvent, type MaxBoardStock } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { useChartTheme } from '@/lib/theme'
import { fmtPct, priceColorClass } from '@/lib/format'
import { cn } from '@/lib/cn'
import { openStockPreview } from '@/extensions/stockPreview'
import type { StockPreviewItem } from '@/extensions/stockPreview'

type RangeDays = 30 | 60 | 120
type EventFilter = 'all' | 'taken_over' | 'vacant'

const RANGE_OPTIONS: RangeDays[] = [30, 60, 120]
const FILTER_OPTIONS: { value: EventFilter; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'taken_over', label: '已接替' },
  { value: 'vacant', label: '空档' },
]

function firstStock(stocks: MaxBoardStock[]) {
  return stocks[0] ?? null
}

function statusLabel(status: MaxBoardEvent['status']) {
  if (status === 'taken_over') return '已接替'
  if (status === 'vacant') return '空档'
  return '待确认'
}

function statusClass(status: MaxBoardEvent['status']) {
  if (status === 'taken_over') return 'border-accent/35 bg-accent/10 text-accent'
  if (status === 'vacant') return 'border-warning/35 bg-warning/10 text-warning'
  return 'border-border bg-elevated text-muted'
}

function useEChart(option: echarts.EChartsOption | null, deps: unknown[]) {
  const ref = useRef<HTMLDivElement>(null)
  const instRef = useRef<echarts.ECharts | null>(null)

  useEffect(() => {
    if (!ref.current) return
    if (!instRef.current) {
      instRef.current = echarts.init(ref.current, undefined, { renderer: 'canvas' })
    }
    if (option) instRef.current.setOption(option, true)
  }, deps)

  useEffect(() => {
    const element = ref.current
    if (!element) return
    const observer = new ResizeObserver(() => instRef.current?.resize())
    observer.observe(element)
    const onResize = () => instRef.current?.resize()
    window.addEventListener('resize', onResize)
    return () => {
      observer.disconnect()
      window.removeEventListener('resize', onResize)
      instRef.current?.dispose()
      instRef.current = null
    }
  }, [])

  return ref
}

function SummaryValue({
  label,
  children,
  className,
}: {
  label: string
  children: React.ReactNode
  className?: string
}) {
  return (
    <div className="min-w-0">
      <div className="text-[10px] tracking-wide text-muted">{label}</div>
      <div className={cn('mt-0.5 truncate text-sm text-foreground', className)}>{children}</div>
    </div>
  )
}

function StockLink({
  stock,
  onClick,
  className,
}: {
  stock: MaxBoardStock
  onClick: () => void
  className?: string
}) {
  return (
    <button
      type="button"
      data-stock={stock.symbol}
      title={`${stock.name} 日K`}
      onClick={onClick}
      className={cn('text-foreground hover:text-accent hover:underline', className)}
    >
      {stock.name}
    </button>
  )
}

function EventRow({
  event,
  number,
  selected,
  onSelect,
  onStockClick,
}: {
  event: MaxBoardEvent
  number: number
  selected: boolean
  onSelect: () => void
  onStockClick: (stock: MaxBoardStock) => void
}) {
  const previous = firstStock(event.previous_leaders)
  const successor = event.successor ? firstStock(event.successor.leaders) : null
  const former = firstStock(event.break_day.former_leaders)
  return (
    <div
      role="button"
      tabIndex={0}
      data-event-id={event.id}
      onClick={onSelect}
      onKeyDown={e => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onSelect()
        }
      }}
      className={cn(
        'grid w-full grid-cols-[88px_minmax(0,1fr)_24px_minmax(0,1fr)_72px] items-center gap-3 border-b border-border/60 px-3 py-2.5 text-left transition-colors last:border-b-0',
        selected ? 'bg-accent/10' : 'hover:bg-elevated/60',
      )}
    >
      <span className="flex items-center gap-1.5 font-mono text-[10px] text-muted">
        <span className="grid h-4 w-4 shrink-0 place-items-center rounded-full border border-border text-[9px] text-foreground">{number}</span>
        {event.break_date.slice(5)}
      </span>
      <span className="min-w-0">
        <span className="flex items-baseline gap-1.5">
          {previous ? (
            <button
              type="button"
              data-stock={previous.symbol}
              title={`${previous.name} 日K`}
              onClick={e => {
                e.stopPropagation()
                onStockClick(previous)
              }}
              className="truncate text-xs font-medium text-foreground hover:text-accent hover:underline"
            >
              {previous.name}
            </button>
          ) : <span className="text-xs text-muted">—</span>}
          <span className="shrink-0 font-mono text-[10px] text-bull">{previous?.boards ?? event.previous_height}板</span>
        </span>
        <span className="mt-0.5 flex items-center gap-2 font-mono text-[10px] text-muted">
          <span className="truncate">{previous?.symbol ?? '—'}</span>
          {former?.change_pct != null && (
            <span className={priceColorClass(former.change_pct)}>{fmtPct(former.change_pct)}</span>
          )}
        </span>
      </span>
      <ArrowRight className="h-3.5 w-3.5 text-muted" aria-hidden="true" />
      <span className="min-w-0">
        <span className="flex items-baseline gap-1.5">
          {successor ? (
            <button
              type="button"
              data-stock={successor.symbol}
              title={`${successor.name} 日K`}
              onClick={e => {
                e.stopPropagation()
                onStockClick(successor)
              }}
              className="truncate text-xs font-medium text-foreground hover:text-accent hover:underline"
            >
              {successor.name}
            </button>
          ) : (
            <span className="truncate text-xs font-medium text-muted">
              {event.status === 'pending' ? '待下一交易日' : '无有效接力'}
            </span>
          )}
          {successor && <span className="shrink-0 font-mono text-[10px] text-accent">{successor.boards}板</span>}
        </span>
        <span className="mt-0.5 flex items-center gap-2 font-mono text-[10px] text-muted">
          <span>{successor?.symbol ?? event.successor?.date?.slice(5) ?? '—'}</span>
          {successor && event.previous_height > successor.boards && (
            <span className="text-warning">−{event.previous_height - successor.boards}</span>
          )}
        </span>
      </span>
      <span className={cn('justify-self-end rounded border px-1.5 py-0.5 text-[10px]', statusClass(event.status))}>
        {statusLabel(event.status)}
      </span>
    </div>
  )
}

function MobileEventCard({
  event,
  number,
  selected,
  onSelect,
  onStockClick,
}: {
  event: MaxBoardEvent
  number: number
  selected: boolean
  onSelect: () => void
  onStockClick: (stock: MaxBoardStock) => void
}) {
  const previous = firstStock(event.previous_leaders)
  const successor = event.successor ? firstStock(event.successor.leaders) : null
  return (
    <div
      role="button"
      tabIndex={0}
      data-event-id={event.id}
      onClick={onSelect}
      onKeyDown={e => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onSelect()
        }
      }}
      className={cn(
        'w-full rounded-btn border px-3 py-2.5 text-left transition-colors',
        selected ? 'border-accent/45 bg-accent/10' : 'border-border bg-elevated/25',
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 font-mono text-[10px] text-muted">
          <span className="grid h-4 w-4 place-items-center rounded-full border border-border text-[9px] text-foreground">{number}</span>
          {event.break_date}
        </span>
        <span className={cn('rounded border px-1.5 py-0.5 text-[10px]', statusClass(event.status))}>
          {statusLabel(event.status)}
        </span>
      </div>
      <div className="mt-1.5 flex items-center gap-2 text-xs">
        {previous ? (
          <button
            type="button"
            data-stock={previous.symbol}
            onClick={e => {
              e.stopPropagation()
              onStockClick(previous)
            }}
            className="min-w-0 truncate text-foreground hover:text-accent hover:underline"
          >
            {previous.name}
          </button>
        ) : <span className="text-muted">—</span>}
        <span className="font-mono text-bull">{previous?.boards ?? event.previous_height}板</span>
        <ArrowRight className="h-3 w-3 text-muted" />
        {successor ? (
          <button
            type="button"
            data-stock={successor.symbol}
            onClick={e => {
              e.stopPropagation()
              onStockClick(successor)
            }}
            className="min-w-0 truncate text-foreground hover:text-accent hover:underline"
          >
            {successor.name}
          </button>
        ) : <span className="text-muted">无有效接力</span>}
        {successor && <span className="font-mono text-accent">{successor.boards}板</span>}
      </div>
    </div>
  )
}

export function MaxBoardPage() {
  const ct = useChartTheme()
  const [days, setDays] = useState<RangeDays>(60)
  const [filter, setFilter] = useState<EventFilter>('all')
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const query = useQuery({
    queryKey: QK.maxBoardRelay(days),
    queryFn: () => api.maxBoardRelay(days),
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  })

  const data = query.data
  const events = useMemo(() => {
    const rows = data?.events ?? []
    const filtered = filter === 'all' ? rows : rows.filter(e => e.status === filter)
    return filtered.slice().reverse()
  }, [data?.events, filter])

  useEffect(() => {
    if (events.length === 0) {
      setSelectedId(null)
      return
    }
    if (!selectedId || !events.some(e => e.id === selectedId)) {
      setSelectedId(events[0].id)
    }
  }, [events, selectedId])

  const selected = events.find(e => e.id === selectedId) ?? null
  const current = data?.current ?? null
  const currentLeader = current?.leaders[0] ?? null
  const series = data?.series ?? []
  const maxHeight = Math.max(5, ...series.map(p => p.height))
  const allEvents = data?.events ?? []
  const eventNumberById = useMemo(
    () => new Map(allEvents.map((event, index) => [event.id, index + 1])),
    [allEvents],
  )
  const previewNavList = useMemo<StockPreviewItem[]>(() => {
    const seen = new Set<string>()
    const out: StockPreviewItem[] = []
    const add = (stocks: MaxBoardStock[]) => {
      for (const stock of stocks) {
        if (!stock.symbol || seen.has(stock.symbol)) continue
        seen.add(stock.symbol)
        out.push({ symbol: stock.symbol, name: stock.name })
      }
    }
    for (const event of allEvents) {
      add(event.previous_leaders)
      add(event.break_day.leaders)
      add(event.break_day.former_leaders)
      if (event.successor) add(event.successor.leaders)
    }
    return out
  }, [allEvents])
  const openStock = useCallback((stock: MaxBoardStock) => {
    openStockPreview({ symbol: stock.symbol, name: stock.name, navList: previewNavList })
  }, [previewNavList])

  const option = useMemo<echarts.EChartsOption | null>(() => {
    if (series.length === 0) return null
    const dates = series.map(p => p.date)
    const heights = series.map(p => p.height)
    const minPeakGap = Math.max(4, Math.round(series.length / 8))
    const stageHighCandidates = series
      .map((point, index) => ({ point, index }))
      .filter(({ point, index }) => {
        if (point.height < 4 || point.leaders.length === 0) return false
        const prev = series[index - 1]?.height ?? 0
        const next = series[index + 1]?.height ?? 0
        return point.height >= prev && point.height >= next
      })
      .sort((a, b) => b.point.height - a.point.height || a.index - b.index)
    const pickedPeaks: typeof stageHighCandidates = []
    for (const candidate of stageHighCandidates) {
      if (pickedPeaks.length >= 5) break
      if (pickedPeaks.every(item => Math.abs(item.index - candidate.index) >= minPeakGap)) {
        pickedPeaks.push(candidate)
      }
    }
    const stageHighs: any[] = pickedPeaks
      .sort((a, b) => a.index - b.index)
      .map(({ point }) => {
        const leader = point.leaders[0]
        return {
          value: [point.date, point.height] as [string, number],
          label: {
            show: true,
            position: 'top',
            distance: 4,
            formatter: `${leader.name} ${leader.boards}板`,
            color: ct.textStrong,
            fontSize: 9,
            fontWeight: 600,
            textBorderColor: ct.tooltipBg,
            textBorderWidth: 2,
          },
          itemStyle: { color: '#ef4444' },
        }
      })
    const breakLines: any[] = allEvents.map(e => [
      { coord: [e.break_date, e.previous_height] },
      { coord: [e.break_date, e.break_day.height] },
    ])
    const selectedArea: any = selected
      ? {
          silent: true,
          itemStyle: { color: 'rgba(59,130,246,0.055)' },
          data: [[
            { xAxis: selected.break_date },
            { xAxis: selected.successor?.date ?? selected.break_date },
          ]],
        }
      : undefined
    return {
      backgroundColor: 'transparent',
      animationDuration: 260,
      tooltip: {
        trigger: 'axis',
        confine: true,
        backgroundColor: ct.tooltipBg,
        borderColor: ct.tooltipBorder,
        textStyle: { color: ct.tooltipText, fontSize: 11 },
        axisPointer: { type: 'line', snap: true, lineStyle: { color: ct.crosshair } },
        formatter: (params: any) => {
          const list = Array.isArray(params) ? params : [params]
          const date = list[0]?.axisValue as string
          const point = series.find(p => p.date === date)
          const event = allEvents.find(e => e.break_date === date)
          if (!point) return ''
          const leaders = point.leaders.length
            ? point.leaders.map(s => `${s.name} ${s.boards}板`).join(' · ')
            : '无连板'
          const lines = [`<b>${date}</b>　最高 <span style="color:#ef4444">${point.height}板</span>`, leaders]
          if (event) {
            const next = event.successor?.leaders[0]
            lines.push(`断板：${event.previous_leaders[0]?.name ?? '—'} ${event.previous_height}板`)
            lines.push(next ? `次日接替：${next.name} ${next.boards}板` : '次日无有效接替')
          }
          return lines.join('<br/>')
        },
      },
      legend: {
        top: 0,
        right: 0,
        itemWidth: 10,
        itemHeight: 6,
        textStyle: { color: ct.text, fontSize: 10 },
        data: ['最高板高度', '阶段高点'],
      },
      grid: { left: 38, right: 24, top: 46, bottom: 36 },
      xAxis: {
        type: 'category',
        data: dates,
        boundaryGap: false,
        axisLine: { lineStyle: { color: ct.grid } },
        axisTick: { show: false },
        axisLabel: {
          color: ct.text,
          fontSize: 9,
          formatter: (v: string) => v.slice(5),
          interval: Math.max(0, Math.ceil(dates.length / 8) - 1),
        },
      },
      yAxis: {
        type: 'value',
        min: 0,
        max: maxHeight + 1,
        interval: maxHeight <= 10 ? 1 : undefined,
        name: '板',
        nameTextStyle: { color: ct.text, fontSize: 10 },
        axisLabel: { color: ct.text, fontSize: 9 },
        axisLine: { show: false },
        splitLine: { lineStyle: { color: ct.grid } },
      },
      series: [
        {
          name: '最高板高度',
          type: 'line',
          data: heights,
          symbol: 'none',
          lineStyle: { color: '#ef4444', width: 2.4 },
          itemStyle: { color: '#ef4444' },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(239,68,68,0.13)' },
              { offset: 1, color: 'rgba(239,68,68,0.01)' },
            ]),
          },
          markArea: selectedArea,
          markLine: {
            silent: true,
            symbol: ['none', 'none'],
            label: { show: false },
            lineStyle: { color: '#f59e0b', type: 'dashed', width: 1, opacity: 0.7 },
            data: breakLines,
          },
          z: 2,
        },
        {
          name: '阶段高点',
          type: 'scatter',
          data: stageHighs,
          symbol: 'circle',
          symbolSize: 4,
          z: 4,
          tooltip: { show: false },
        },
      ],
    }
  }, [series, maxHeight, allEvents, selected, ct])

  const chartRef = useEChart(option, [option])

  const lastBreakDays = current?.days_since_break
  const delta = current?.delta_height ?? 0

  return (
    <div className="h-full overflow-auto bg-base p-4">
      <header className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-semibold text-foreground">最高板接力</h1>
            {data?.as_of && <span className="font-mono text-[10px] text-muted">{data.as_of}</span>}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="inline-flex rounded-btn border border-border bg-surface p-0.5" role="group" aria-label="时间范围">
            {RANGE_OPTIONS.map(value => (
              <button
                key={value}
                type="button"
                onClick={() => setDays(value)}
                aria-pressed={days === value}
                className={cn(
                  'rounded px-2.5 py-1 text-[11px] transition-colors',
                  days === value ? 'bg-elevated text-foreground' : 'text-muted hover:text-foreground',
                )}
              >
                {value}日
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={() => query.refetch()}
            disabled={query.isFetching}
            className="inline-flex items-center gap-1.5 rounded-btn border border-border bg-surface px-2.5 py-1.5 text-[11px] text-secondary hover:bg-elevated disabled:opacity-50"
          >
            {query.isFetching ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
            刷新
          </button>
        </div>
      </header>

      <section className="overflow-hidden rounded-card border border-border bg-surface">
        <div className="flex flex-wrap items-center gap-x-8 gap-y-2 border-b border-border/70 px-4 py-3">
          <SummaryValue label="当前最高">
            <span className="font-mono text-2xl font-semibold text-bull">{current?.height ?? '—'}</span>
            <span className="ml-1 text-xs text-muted">板</span>
            {currentLeader && (
              <span className="ml-2 text-xs text-foreground">
                {currentLeader.name}
                <span className="ml-1 font-mono text-[10px] text-muted">{currentLeader.symbol}</span>
              </span>
            )}
          </SummaryValue>
          <SummaryValue label="较昨日">
            <span className={cn('inline-flex items-center gap-1 font-mono', delta > 0 ? 'text-bull' : delta < 0 ? 'text-bear' : 'text-muted')}>
              {delta > 0 ? <TrendingUp className="h-3.5 w-3.5" /> : delta < 0 ? <TrendingDown className="h-3.5 w-3.5" /> : <Minus className="h-3.5 w-3.5" />}
              {delta > 0 ? '+' : ''}{delta}板
            </span>
          </SummaryValue>
          <SummaryValue label="最近断板">
            {current?.last_break_date ? (
              <span className="font-mono">{current.last_break_date.slice(5)}</span>
            ) : '—'}
            {lastBreakDays != null && <span className="ml-2 text-[10px] text-muted">{lastBreakDays}个交易日前</span>}
          </SummaryValue>
          <SummaryValue label="最近接力">
            {current?.last_event ? (
              <span className={cn(
                'rounded border px-1.5 py-0.5 text-[10px]',
                statusClass(current.last_event.status),
              )}>
                {statusLabel(current.last_event.status)}
              </span>
            ) : '—'}
          </SummaryValue>
        </div>

        <div className="px-2 pt-2">
          {query.isLoading ? (
            <div className="grid h-[340px] place-items-center text-xs text-muted">加载中…</div>
          ) : query.isError ? (
            <div className="grid h-[340px] place-items-center gap-2 text-xs text-muted">
              <span>最高板数据加载失败</span>
              <button type="button" onClick={() => query.refetch()} className="rounded-btn border border-border px-3 py-1 text-foreground">
                重试
              </button>
            </div>
          ) : series.length === 0 ? (
            <div className="grid h-[340px] place-items-center text-xs text-muted">暂无连板数据</div>
          ) : (
            <div ref={chartRef} className="h-[360px] w-full" role="img" aria-label="最高板高度走势与断板接替标注" />
          )}
        </div>
        {series.length > 0 && (
          <div className="flex flex-wrap items-center gap-4 border-t border-border/60 px-4 py-2 text-[10px] text-muted">
            <span className="inline-flex items-center gap-1.5"><i className="h-0.5 w-4 bg-bull" />最高板高度</span>
            <span className="inline-flex items-center gap-1.5"><i className="h-2 w-2 rounded-full bg-bull" />阶段高点</span>
            <span className="inline-flex items-center gap-1.5"><i className="h-3 w-px border-l border-dashed border-warning" />断板</span>
          </div>
        )}
      </section>

      <section className="mt-3 grid gap-3 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0 overflow-hidden rounded-card border border-border bg-surface">
          <div className="flex items-center justify-between gap-3 border-b border-border/70 px-3 py-2">
            <h2 className="text-xs font-medium text-foreground">接力链</h2>
            <div className="inline-flex rounded-btn border border-border bg-elevated/40 p-0.5" role="group" aria-label="接力状态筛选">
              {FILTER_OPTIONS.map(item => (
                <button
                  key={item.value}
                  type="button"
                  onClick={() => setFilter(item.value)}
                  aria-pressed={filter === item.value}
                  className={cn(
                    'rounded px-2 py-0.5 text-[10px] transition-colors',
                    filter === item.value ? 'bg-surface text-foreground' : 'text-muted hover:text-foreground',
                  )}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
          <div className="hidden md:block">
            {events.length === 0 ? (
              <div className="grid h-40 place-items-center text-xs text-muted">所选范围内无断板事件</div>
            ) : (
              <>
                <div className="grid grid-cols-[88px_minmax(0,1fr)_24px_minmax(0,1fr)_72px] gap-3 border-b border-border/60 bg-elevated/30 px-3 py-1.5 text-[10px] text-muted">
                  <span>断板日</span><span>前最高板</span><span /><span>次日接替</span><span className="text-right">状态</span>
                </div>
                {events.map(event => (
                  <EventRow
                    key={event.id}
                    event={event}
                    number={eventNumberById.get(event.id) ?? 0}
                    selected={selected?.id === event.id}
                    onSelect={() => setSelectedId(event.id)}
                    onStockClick={openStock}
                  />
                ))}
              </>
            )}
          </div>
          <div className="grid gap-2 p-2 md:hidden">
            {events.length === 0
              ? <div className="grid h-32 place-items-center text-xs text-muted">所选范围内无断板事件</div>
              : events.map(event => (
                <MobileEventCard
                  key={event.id}
                  event={event}
                  number={eventNumberById.get(event.id) ?? 0}
                  selected={selected?.id === event.id}
                  onSelect={() => setSelectedId(event.id)}
                  onStockClick={openStock}
                />
              ))}
          </div>
        </div>

        <aside className="rounded-card border border-border bg-surface p-3 lg:sticky lg:top-3 lg:self-start">
          {selected ? (
            <>
              <div className="flex items-center justify-between gap-2">
                <h2 className="text-xs font-medium text-foreground">事件详情</h2>
                <span className={cn('rounded border px-1.5 py-0.5 text-[10px]', statusClass(selected.status))}>
                  {statusLabel(selected.status)}
                </span>
              </div>
              <dl className="mt-3 grid gap-2 text-[11px]">
                <div className="flex items-start justify-between gap-3">
                  <dt className="text-muted">断板日</dt>
                  <dd className="font-mono text-foreground">{selected.break_date}</dd>
                </div>
                <div className="flex items-start justify-between gap-3">
                  <dt className="text-muted">前最高板</dt>
                  <dd className="text-right">
                    {selected.previous_leaders.map(stock => (
                      <div key={stock.symbol} className="text-foreground">
                        <StockLink stock={stock} onClick={() => openStock(stock)} />
                        <span className="ml-1 font-mono text-bull">{stock.boards}板</span>
                      </div>
                    ))}
                  </dd>
                </div>
                <div className="flex items-start justify-between gap-3">
                  <dt className="text-muted">断板日最高</dt>
                  <dd className="text-right">
                    {selected.break_day.leaders.length > 0 ? selected.break_day.leaders.map(stock => (
                      <div key={stock.symbol} className="text-foreground">
                        <StockLink stock={stock} onClick={() => openStock(stock)} />
                        <span className="ml-1 font-mono text-accent">{stock.boards}板</span>
                      </div>
                    )) : <span className="text-muted">无连板</span>}
                  </dd>
                </div>
                <div className="flex items-start justify-between gap-3">
                  <dt className="text-muted">次日接替</dt>
                  <dd className="text-right">
                    {selected.successor?.leaders.length ? selected.successor.leaders.map(stock => (
                      <div key={stock.symbol} className="text-foreground">
                        <StockLink stock={stock} onClick={() => openStock(stock)} />
                        <span className="ml-1 font-mono text-accent">{stock.boards}板</span>
                      </div>
                    )) : <span className="text-muted">{selected.status === 'pending' ? '待下一交易日' : '空档'}</span>}
                  </dd>
                </div>
                <div className="flex items-start justify-between gap-3 border-t border-border/60 pt-2">
                  <dt className="text-muted">高度变化</dt>
                  <dd className="font-mono text-foreground">
                    {selected.previous_height}板 <ArrowRight className="mx-1 inline h-3 w-3 text-muted" />
                    {selected.successor?.height ?? selected.break_day.height}板
                    <span className="ml-1 text-warning">−{selected.height_gap}</span>
                  </dd>
                </div>
                <div className="flex items-start justify-between gap-3">
                  <dt className="text-muted">断板日表现</dt>
                  <dd className="text-right">
                    {selected.break_day.former_leaders.map(stock => (
                      <div key={stock.symbol} className="text-foreground">
                        <StockLink stock={stock} onClick={() => openStock(stock)} />{' '}
                        <span className={priceColorClass(stock.change_pct)}>{stock.change_pct == null ? '—' : fmtPct(stock.change_pct)}</span>
                      </div>
                    ))}
                  </dd>
                </div>
              </dl>
            </>
          ) : (
            <div className="grid h-40 place-items-center text-xs text-muted">选择左侧事件查看接力详情</div>
          )}
        </aside>
      </section>

    </div>
  )
}
