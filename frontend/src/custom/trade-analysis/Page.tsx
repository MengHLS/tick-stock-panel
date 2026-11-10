import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as echarts from 'echarts'
import {
  ExternalLink, RefreshCw, Search, StickyNote, Upload, X,
} from 'lucide-react'
import { cn } from '@/lib/cn'
import { fmtPct, fmtPrice, priceColorClass } from '@/lib/format'
import { api } from '@/lib/api'
import { PageHeader } from '@/components/PageHeader'
import { Modal } from '@/components/Modal'
import { toast } from '@/components/Toast'
import {
  EChartsCandlestick,
  type ChartMarker,
  type ChartPriceLine,
  type ChartRange,
  type OHLC,
} from '@/components/EChartsCandlestick'
import { openStockPreview } from '@/extensions/stockPreview'
import {
  tradeAnalysisApi,
  type OpenPosition,
  type SymbolSummary,
  type TradeOverview,
  type TradeRow,
} from './client'

const QK = ['trade-analysis', 'overview'] as const

function money(value: number | null | undefined, signed = false): string {
  if (value == null || !Number.isFinite(value)) return '—'
  const text = Math.abs(value).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  if (!signed) return value < 0 ? `-${text}` : text
  return `${value > 0 ? '+' : value < 0 ? '-' : ''}${text}`
}

function priceDigits(symbol: string): number {
  return symbol.startsWith('15') || symbol.startsWith('5') ? 3 : 2
}

function shortDate(value: string | null | undefined): string {
  if (!value) return '—'
  return value.length >= 10 ? value.slice(5, 10) : value
}

function shiftDate(value: string, days: number): string {
  const day = new Date(`${value}T00:00:00`)
  day.setDate(day.getDate() + days)
  return day.toISOString().slice(0, 10)
}

function cycleLabel(openDate: string, closeDate: string): string {
  return openDate.slice(0, 4) === closeDate.slice(0, 4)
    ? `${openDate} → ${closeDate.slice(5)}`
    : `${openDate} → ${closeDate}`
}

function useEChart(option: echarts.EChartsOption | null, deps: unknown[]) {
  const elementRef = useRef<HTMLDivElement>(null)
  const instanceRef = useRef<echarts.ECharts | null>(null)

  useEffect(() => {
    if (!elementRef.current) return
    if (!instanceRef.current) {
      instanceRef.current = echarts.init(elementRef.current, undefined, { renderer: 'canvas' })
    }
    instanceRef.current.setOption(option ?? {}, true)
  }, deps)

  useEffect(() => {
    const element = elementRef.current
    if (!element) return
    const observer = new ResizeObserver(() => instanceRef.current?.resize())
    observer.observe(element)
    const onResize = () => instanceRef.current?.resize()
    window.addEventListener('resize', onResize)
    return () => {
      observer.disconnect()
      window.removeEventListener('resize', onResize)
      instanceRef.current?.dispose()
      instanceRef.current = null
    }
  }, [])

  return elementRef
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-btn border border-border bg-surface px-3 py-2.5">
      <div className="text-[10px] tracking-wide text-muted">{label}</div>
      <div className={cn('mt-1 font-mono text-lg tabular-nums', tone ?? 'text-foreground')}>{value}</div>
    </div>
  )
}

function Tag({ children, tone = 'default' }: { children: React.ReactNode; tone?: 'default' | 'bull' | 'bear' }) {
  return (
    <span
      className={cn(
        'shrink-0 whitespace-nowrap rounded px-1.5 py-px text-[10px]',
        tone === 'bull' && 'bg-bull/10 text-bull',
        tone === 'bear' && 'bg-bear/10 text-bear',
        tone === 'default' && 'bg-elevated text-secondary',
      )}
    >
      {children}
    </span>
  )
}

function tagTone(tag: string): 'default' | 'bull' | 'bear' {
  if (tag === '盈利' || tag === '低吸') return 'bull'
  if (tag === '亏损' || tag === '追高' || tag === '卖飞' || tag === '止损偏慢') return 'bear'
  return 'default'
}

function SymbolRow({
  item,
  active,
  onSelect,
}: {
  item: SymbolSummary
  active: boolean
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        'grid w-full grid-cols-[minmax(0,1fr)_44px_58px_88px] items-center gap-2 border-b border-border/60 px-3 py-2 text-left transition-colors last:border-b-0 hover:bg-elevated/40',
        active && 'bg-accent/8',
      )}
    >
      <span className="min-w-0">
        <span className="block truncate text-xs text-foreground">{item.name || item.symbol}</span>
        <span className="font-mono text-[10px] text-muted">{item.symbol}</span>
      </span>
      <span className="text-right font-mono text-[10px] text-muted">{item.trades}笔</span>
      <span className="text-right font-mono text-[10px] text-secondary">
        {item.win_rate == null ? '—' : `${(item.win_rate * 100).toFixed(0)}%`}
      </span>
      <span className={cn('text-right font-mono text-xs', priceColorClass(item.pnl))}>
        {money(item.pnl, true)}
      </span>
    </button>
  )
}

function PositionRow({ item }: { item: OpenPosition }) {
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_56px_82px_76px] items-center gap-2 border-b border-border/60 px-3 py-2 last:border-b-0">
      <span className="min-w-0">
        <span className="block truncate text-xs text-foreground">{item.name || item.symbol}</span>
        <span className="font-mono text-[10px] text-muted">{item.symbol}</span>
      </span>
      <span className="text-right font-mono text-[10px] text-secondary">{item.qty}</span>
      <span className="text-right font-mono text-[10px] text-secondary">
        {fmtPrice(item.avg_cost, priceDigits(item.symbol))}
      </span>
      <span className="text-right font-mono text-[10px] text-muted">{shortDate(item.open_date)}</span>
    </div>
  )
}

function TradeDetail({
  trade,
  onClose,
}: {
  trade: TradeRow
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [note, setNote] = useState(trade.note)
  const [tags, setTags] = useState<string[]>(trade.patterns ?? [])
  const [tagInput, setTagInput] = useState('')
  const digits = priceDigits(trade.symbol)
  const autoTags = trade.tags ?? []

  useEffect(() => {
    setNote(trade.note)
    setTags(trade.patterns ?? [])
    setTagInput('')
  }, [trade.trade_key, trade.note, trade.patterns])

  const klineQuery = useQuery({
    queryKey: ['trade-analysis', 'kline', trade.symbol, trade.open_date, trade.close_date],
    queryFn: async () => {
      // 批量接口比单股区间接口快得多；先取足够长历史，再在前端裁到交易窗口。
      const days = Math.min(
        2000,
        Math.max(120, Math.ceil((Date.now() - new Date(`${trade.open_date}T00:00:00`).getTime()) / 86_400_000 * 0.8) + 120),
      )
      const response = await api.klineDailyBatch([trade.symbol], days)
      return response.data?.[trade.symbol] ?? []
    },
    staleTime: 300_000,
  })

  const chartData = useMemo<OHLC[]>(() => (
    (klineQuery.data ?? [])
      .filter(row => row.date >= shiftDate(trade.open_date, -90) && row.date <= shiftDate(trade.close_date, 45))
      .map(row => ({
      date: row.date,
      open: row.open,
      high: row.high,
      low: row.low,
      close: row.close,
      volume: row.volume,
      ma5: row.ma5,
      ma10: row.ma10,
      ma20: row.ma20,
      ma60: row.ma60,
      }))
  ), [klineQuery.data, trade.open_date, trade.close_date])

  const markers = useMemo<ChartMarker[]>(() => {
    const grouped = new Map<string, { date: string; kind: 'buy' | 'sell'; qty: number }>()
    for (const leg of trade.legs ?? []) {
      const key = `${leg.date}-${leg.side}`
      const current = grouped.get(key)
      if (current) {
        current.qty += leg.qty
      } else {
        grouped.set(key, {
          date: leg.date,
          kind: leg.side === 'B' ? 'buy' : 'sell',
          qty: leg.qty,
        })
      }
    }
    return Array.from(grouped.values()).map(item => ({
      date: item.date,
      kind: item.kind,
      label: `${item.kind === 'buy' ? 'B' : 'S'}${item.qty}`,
      above: item.kind === 'sell',
    }))
  }, [trade.legs])

  const ranges = useMemo<ChartRange[]>(() => [{
    start: trade.open_date,
    end: trade.close_date,
    label: '持仓',
    color: 'rgba(56,189,248,0.16)',
  }], [trade.open_date, trade.close_date])

  const priceLines = useMemo<ChartPriceLine[]>(() => {
    // K 线使用前复权价，成交价是原始价；按建仓/清仓当日 close/raw_close 折算。
    const rows = klineQuery.data ?? []
    const openRow = rows.find(row => row.date === trade.open_date)
    const closeRow = rows.find(row => row.date === trade.close_date)
    const buyScale = openRow?.raw_close ? openRow.close / openRow.raw_close : 1
    const sellScale = closeRow?.raw_close ? closeRow.close / closeRow.raw_close : 1
    return [
      { value: trade.buy_price * buyScale, label: `均价买 ${fmtPrice(trade.buy_price, digits)}`, color: '#f59e0b' },
      { value: trade.sell_price * sellScale, label: `均价卖 ${fmtPrice(trade.sell_price, digits)}`, color: '#38bdf8' },
    ]
  }, [klineQuery.data, trade.buy_price, trade.sell_price, trade.open_date, trade.close_date, digits])

  const saveMutation = useMutation({
    mutationFn: (payload: { note: string; tags: string[] }) =>
      tradeAnalysisApi.saveNote(trade.trade_key, payload.note, payload.tags),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: QK })
      toast('复盘已保存', 'success')
    },
    onError: (error: Error) => toast(error.message, 'error'),
  })

  const stats = [
    ['均价买入', fmtPrice(trade.buy_price, digits)],
    ['均价卖出', fmtPrice(trade.sell_price, digits)],
    ['持有交易日', trade.hold_td == null ? `${trade.hold_days}天` : `${trade.hold_td}日`],
    ['最大浮盈', fmtPct(trade.mfe)],
    ['最大浮亏', fmtPct(trade.mae)],
    ['买入分位', trade.buy_range_pct == null ? '—' : `${(trade.buy_range_pct * 100).toFixed(0)}%`],
    ['卖后5日', fmtPct(trade.post5)],
    ['卖后10日', fmtPct(trade.post10)],
  ]

  const addTag = () => {
    const value = tagInput.trim()
    if (!value) return
    setTags(current => current.includes(value) ? current : [...current, value].slice(0, 8))
    setTagInput('')
  }

  const saveReview = () => {
    const pending = tagInput.trim()
    const nextTags = pending && !tags.includes(pending) ? [...tags, pending].slice(0, 8) : tags
    setTags(nextTags)
    setTagInput('')
    saveMutation.mutate({ note, tags: nextTags })
  }

  return (
    <Modal
      onClose={onClose}
      ariaLabel="交易复盘"
      panelClassName="w-[min(1120px,96vw)] max-h-[90vh] overflow-y-auto rounded-card border border-border bg-surface shadow-xl"
    >
      <div className="sticky top-0 z-10 flex items-start justify-between gap-3 border-b border-border bg-surface/95 px-5 py-3 backdrop-blur">
        <div className="min-w-0">
          <div className="flex items-baseline gap-2">
            <h2 className="truncate text-base font-medium text-foreground">{trade.name || trade.symbol}</h2>
            <span className="font-mono text-[10px] text-muted">{trade.symbol}</span>
          </div>
          <div className="mt-0.5 flex items-center gap-2 font-mono text-[11px] text-muted">
            <span>{trade.open_date} {trade.open_time.slice(0, 5)}</span>
            <span>→</span>
            <span>{trade.close_date} {trade.close_time.slice(0, 5)}</span>
            <span>·</span>
            <span>{trade.buy_count}买 / {trade.sell_count}卖 · {trade.qty}股</span>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            onClick={() => openStockPreview({ symbol: trade.symbol, name: trade.name })}
            className="rounded-btn border border-border px-2 py-1 text-[11px] text-secondary hover:text-foreground"
          >
            <ExternalLink className="mr-1 inline h-3 w-3" />
            个股
          </button>
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭"
            className="rounded-btn p-1.5 text-muted hover:bg-elevated hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="space-y-4 px-5 py-4">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <span className={cn('font-mono text-xl', priceColorClass(trade.pnl))}>{money(trade.pnl, true)}</span>
          <span className={cn('font-mono text-sm', priceColorClass(trade.ret))}>{fmtPct(trade.ret)}</span>
          <span className="font-mono text-[11px] text-muted">成本 {money(trade.cost)}</span>
          <span className="font-mono text-[11px] text-muted">费用 {money(trade.fees)}</span>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {autoTags.map(tag => <Tag key={tag} tone={tagTone(tag)}>{tag}</Tag>)}
          {tags.filter(tag => !autoTags.includes(tag)).map(tag => (
            <span key={tag} className="inline-flex items-center gap-1 rounded bg-accent/10 px-1.5 py-px text-[10px] text-accent">
              {tag}
              <button
                type="button"
                aria-label={`移除标签 ${tag}`}
                onClick={() => setTags(current => current.filter(item => item !== tag))}
                className="text-accent/70 hover:text-accent"
              >
                <X className="h-2.5 w-2.5" />
              </button>
            </span>
          ))}
        </div>

        <div className="rounded-card border border-border bg-base/30">
          <div className="flex items-center justify-between border-b border-border px-3 py-2">
            <span className="text-xs font-medium text-foreground">日K</span>
            <span className="font-mono text-[10px] text-muted">
              {trade.open_date} → {trade.close_date}
            </span>
          </div>
          {klineQuery.isLoading && <div className="grid h-[360px] place-items-center text-xs text-muted">加载中…</div>}
          {klineQuery.isError && (
            <div className="grid h-[360px] place-items-center text-xs text-danger">{(klineQuery.error as Error).message}</div>
          )}
          {!klineQuery.isLoading && !klineQuery.isError && chartData.length === 0 && (
            <div className="grid h-[360px] place-items-center text-xs text-muted">暂无日K数据</div>
          )}
          {chartData.length > 0 && (
            <EChartsCandlestick
              data={chartData}
              assetType={trade.symbol.startsWith('15') || trade.symbol.startsWith('5') ? 'etf' : 'stock'}
              markers={markers}
              ranges={ranges}
              priceLines={priceLines}
              height={360}
              showInfoBar={false}
              visibleBars="all"
              stockInfo={{ name: trade.name }}
            />
          )}
        </div>

        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {stats.map(([label, value]) => (
            <div key={label} className="rounded-btn border border-border bg-base/40 px-2.5 py-2">
              <div className="text-[10px] text-muted">{label}</div>
              <div className="mt-0.5 font-mono text-xs text-foreground">{value}</div>
            </div>
          ))}
        </div>

        <div>
          <div className="mb-1 text-[10px] tracking-wide text-muted">分析</div>
          <p className="text-sm leading-6 text-secondary">{trade.analysis || '暂无市场区间数据，仅保留成交与盈亏。'}</p>
        </div>

        <div>
          <div className="mb-1 text-[10px] tracking-wide text-muted">交易模式</div>
          <div className="flex flex-wrap items-center gap-1.5">
            {tags.filter(tag => !autoTags.includes(tag)).map(tag => (
              <span key={tag} className="rounded bg-elevated px-2 py-0.5 text-[11px] text-secondary">{tag}</span>
            ))}
            <input
              value={tagInput}
              onChange={event => setTagInput(event.target.value)}
              onKeyDown={event => {
                if (event.key === 'Enter') {
                  event.preventDefault()
                  addTag()
                }
              }}
              placeholder="输入交易模式后回车"
              className="h-7 w-40 rounded-btn border border-border bg-base/40 px-2 text-xs text-foreground outline-none focus:border-accent/60"
            />
          </div>
        </div>

        <div>
          <div className="mb-1 flex items-center justify-between">
            <span className="text-[10px] tracking-wide text-muted">复盘笔记</span>
            <button
              type="button"
              disabled={saveMutation.isPending}
              onClick={saveReview}
              className="rounded-btn bg-accent px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
            >
              保存
            </button>
          </div>
          <textarea
            value={note}
            onChange={event => setNote(event.target.value)}
            rows={5}
            placeholder="记下当时的判断和这次交易的得失"
            className="w-full resize-y rounded-btn border border-border bg-base/40 px-3 py-2 text-sm text-foreground outline-none focus:border-accent/60"
          />
        </div>
      </div>
    </Modal>
  )
}

function buildCurveOption(data: TradeOverview | undefined): echarts.EChartsOption | null {
  const curve = data?.curve ?? []
  if (curve.length === 0) return null
  const values = curve.map(point => point.cum_pnl)
  const positive = (values[values.length - 1] ?? 0) >= 0
  const color = positive ? '#f04438' : '#12b76a'
  return {
    animation: false,
    grid: { left: 44, right: 12, top: 12, bottom: 26 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(15,23,42,.92)',
      borderWidth: 0,
      textStyle: { color: '#e2e8f0', fontSize: 11 },
      formatter: (params: unknown) => {
        const list = params as Array<{ axisValue: string; value: number }>
        const item = list?.[0]
        if (!item) return ''
        return `${item.axisValue}<br/>累计 ${money(Number(item.value), true)}`
      },
    },
    xAxis: {
      type: 'category',
      data: curve.map(point => point.date),
      axisLine: { lineStyle: { color: 'rgba(148,163,184,.25)' } },
      axisTick: { show: false },
      axisLabel: { color: '#94a3b8', fontSize: 10, formatter: (value: string) => shortDate(value) },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: 'rgba(148,163,184,.12)' } },
      axisLabel: { color: '#94a3b8', fontSize: 10 },
    },
    series: [{
      type: 'line',
      data: values,
      showSymbol: false,
      lineStyle: { color, width: 1.6 },
      areaStyle: {
        color: {
          type: 'linear',
          x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: `${color}44` },
            { offset: 1, color: `${color}05` },
          ],
        },
      },
    }],
  }
}

export function TradeAnalysisPage() {
  const queryClient = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [resultFilter, setResultFilter] = useState<'all' | 'win' | 'loss'>('all')
  const [tagFilter, setTagFilter] = useState('')
  const [search, setSearch] = useState('')
  const [selectedKey, setSelectedKey] = useState<string | null>(null)

  const overviewQuery = useQuery({
    queryKey: QK,
    queryFn: tradeAnalysisApi.overview,
    staleTime: 30_000,
  })
  const data = overviewQuery.data
  const trades = useMemo(() => data?.trade_rows ?? [], [data?.trade_rows])
  const allTags = useMemo(() => {
    const values = new Set<string>()
    for (const item of trades) {
      for (const tag of item.patterns ?? []) values.add(tag)
    }
    return Array.from(values).sort((a, b) => a.localeCompare(b, 'zh-CN'))
  }, [trades])

  const filtered = useMemo(() => {
    const keyword = search.trim().toLowerCase()
    return trades.filter(item => {
      if (resultFilter === 'win' && item.pnl <= 0) return false
      if (resultFilter === 'loss' && item.pnl >= 0) return false
      if (tagFilter && !(item.patterns ?? []).includes(tagFilter)) return false
      if (!keyword) return true
      return item.symbol.toLowerCase().includes(keyword) || item.name.toLowerCase().includes(keyword)
    })
  }, [trades, resultFilter, tagFilter, search])

  const selected = trades.find(item => item.trade_key === selectedKey) ?? null
  const chartOption = useMemo(() => buildCurveOption(data), [data])
  const chartRef = useEChart(chartOption, [chartOption])

  const importMutation = useMutation({
    mutationFn: tradeAnalysisApi.importStatement,
    onSuccess: result => {
      void queryClient.invalidateQueries({ queryKey: QK })
      toast(`新增 ${result.inserted} 条成交，忽略重复 ${result.duplicates} 条`, 'success')
    },
    onError: (error: Error) => toast(error.message, 'error'),
  })

  const reanalyzeMutation = useMutation({
    mutationFn: tradeAnalysisApi.reanalyze,
    onSuccess: result => {
      void queryClient.invalidateQueries({ queryKey: QK })
      toast(`已重算 ${result.analyzed} 笔交易`, 'success')
    },
    onError: (error: Error) => toast(error.message, 'error'),
  })

  const onPickFile = (file: File | undefined) => {
    if (!file) return
    importMutation.mutate(file)
    if (fileRef.current) fileRef.current.value = ''
  }

  const subtitle = data && data.fills > 0
    ? `${data.trades} 笔 · ${data.first_date ?? ''} 至 ${data.last_date ?? ''}`
    : undefined

  return (
    <div className="flex h-full min-h-0 flex-col">
      <PageHeader
        title="交易分析"
        subtitle={subtitle}
        right={(
          <div className="flex items-center gap-1.5">
            <input
              ref={fileRef}
              type="file"
              accept=".csv,.txt"
              className="hidden"
              onChange={event => onPickFile(event.target.files?.[0])}
            />
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              disabled={importMutation.isPending}
              className="flex items-center gap-1 rounded-btn border border-border px-2.5 py-1 text-xs text-secondary transition-colors hover:text-foreground disabled:opacity-50"
            >
              <Upload className="h-3.5 w-3.5" />
              导入对账单
            </button>
            <button
              type="button"
              title="重新分析"
              onClick={() => reanalyzeMutation.mutate()}
              disabled={reanalyzeMutation.isPending || trades.length === 0}
              className="rounded-btn border border-border p-1.5 text-secondary transition-colors hover:text-foreground disabled:opacity-40"
            >
              <RefreshCw className={cn('h-3.5 w-3.5', reanalyzeMutation.isPending && 'animate-spin')} />
            </button>
          </div>
        )}
      />

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        {overviewQuery.isError && (
          <div className="rounded-card border border-danger/30 bg-danger/5 px-4 py-3 text-sm text-danger">
            {(overviewQuery.error as Error).message}
          </div>
        )}

        {!overviewQuery.isLoading && data && data.fills === 0 && (
          <div className="grid min-h-[320px] place-items-center rounded-card border border-dashed border-border">
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              className="flex flex-col items-center gap-2 text-muted transition-colors hover:text-foreground"
            >
              <Upload className="h-8 w-8" />
              <span className="text-sm">导入券商对账单</span>
            </button>
          </div>
        )}

        {data && data.fills > 0 && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-6">
              <Metric label="已平仓盈亏" value={money(data.total_pnl, true)} tone={priceColorClass(data.total_pnl)} />
              <Metric label="胜率" value={data.win_rate == null ? '—' : `${(data.win_rate * 100).toFixed(1)}%`} />
              <Metric label="盈亏比" value={data.payoff == null ? '—' : data.payoff.toFixed(2)} />
              <Metric label="交易笔数" value={String(data.trades)} />
              <Metric label="平均收益" value={fmtPct(data.avg_ret)} tone={priceColorClass(data.avg_ret)} />
              <Metric label="最大回撤" value={money(data.max_drawdown, true)} tone={data.max_drawdown < 0 ? 'text-bear' : undefined} />
            </div>

            <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_390px]">
              <section className="rounded-card border border-border bg-surface">
                <div className="flex items-center justify-between border-b border-border px-3 py-2">
                  <span className="text-xs font-medium text-foreground">累计盈亏</span>
                  <span className="font-mono text-[10px] text-muted">均持有 {data.avg_hold_days?.toFixed(1) ?? '—'} 天 · 费用 {money(data.total_fees)}</span>
                </div>
                <div ref={chartRef} className="h-[240px] w-full" />
              </section>

              <section className="rounded-card border border-border bg-surface">
                <div className="flex items-center justify-between border-b border-border px-3 py-2">
                  <span className="text-xs font-medium text-foreground">股票</span>
                  <span className="font-mono text-[10px] text-muted">{data.symbols.length}</span>
                </div>
                <div className="max-h-[212px] overflow-y-auto">
                  {data.symbols.slice(0, 30).map(item => (
                    <SymbolRow
                      key={item.symbol}
                      item={item}
                      active={search === item.symbol || search === item.name}
                      onSelect={() => setSearch(item.symbol)}
                    />
                  ))}
                </div>
              </section>
            </div>

            {data.positions.length > 0 && (
              <section className="rounded-card border border-border bg-surface">
                <div className="flex items-center justify-between border-b border-border px-3 py-2">
                  <span className="text-xs font-medium text-foreground">持仓中</span>
                  <span className="font-mono text-[10px] text-muted">{data.open_positions}</span>
                </div>
                <div className="max-h-[180px] overflow-y-auto">
                  {data.positions.map((item, index) => (
                    <PositionRow key={`${item.symbol}-${item.open_date}-${index}`} item={item} />
                  ))}
                </div>
              </section>
            )}

            <section className="rounded-card border border-border bg-surface">
              <div className="flex flex-wrap items-center gap-2 border-b border-border px-3 py-2">
                <span className="text-xs font-medium text-foreground">逐笔交易</span>
                <div className="ml-auto flex items-center gap-1.5">
                  <div className="relative">
                    <Search className="pointer-events-none absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-muted" />
                    <input
                      value={search}
                      onChange={event => setSearch(event.target.value)}
                      placeholder="代码 / 名称"
                      className="h-7 w-40 rounded-btn border border-border bg-base/40 pl-6 pr-2 text-xs text-foreground outline-none focus:border-accent/60"
                    />
                  </div>
                  <select
                    value={tagFilter}
                    onChange={event => setTagFilter(event.target.value)}
                    className="h-7 max-w-[120px] rounded-btn border border-border bg-base/40 px-2 text-[11px] text-secondary outline-none focus:border-accent/60"
                  >
                    <option value="">全部模式</option>
                    {allTags.map(tag => <option key={tag} value={tag}>{tag}</option>)}
                  </select>
                  <div className="flex overflow-hidden rounded-btn border border-border">
                    {([['all', '全部'], ['win', '盈利'], ['loss', '亏损']] as const).map(([value, label]) => (
                      <button
                        key={value}
                        type="button"
                        onClick={() => setResultFilter(value)}
                        className={cn(
                          'px-2.5 py-1 text-[11px] transition-colors',
                          resultFilter === value ? 'bg-elevated text-foreground' : 'text-muted hover:text-foreground',
                        )}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full min-w-[1160px] border-collapse text-left">
                  <thead>
                    <tr className="border-b border-border text-[10px] text-muted">
                      <th className="px-3 py-1.5 font-normal">建仓 → 清仓</th>
                      <th className="px-2 py-1.5 font-normal">股票</th>
                      <th className="px-2 py-1.5 font-normal">交易模式</th>
                      <th className="px-2 py-1.5 text-right font-normal">均价买</th>
                      <th className="px-2 py-1.5 text-right font-normal">均价卖</th>
                      <th className="px-2 py-1.5 text-right font-normal">数量 / 次数</th>
                      <th className="px-2 py-1.5 text-right font-normal">盈亏</th>
                      <th className="px-2 py-1.5 text-right font-normal">收益率</th>
                      <th className="whitespace-nowrap px-2 py-1.5 text-right font-normal">持有</th>
                      <th className="px-3 py-1.5 font-normal">分析</th>
                      <th className="w-8 px-1 py-1.5" />
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map(item => (
                      <tr
                        key={item.trade_key}
                        onClick={() => setSelectedKey(item.trade_key)}
                        className="cursor-pointer border-b border-border/60 text-xs transition-colors last:border-b-0 hover:bg-elevated/40"
                      >
                        <td className="whitespace-nowrap px-3 py-1.5 font-mono text-[10px] text-muted">
                          {cycleLabel(item.open_date, item.close_date)}
                        </td>
                        <td className="px-2 py-1.5">
                          <div className="max-w-[130px] truncate text-foreground">{item.name || item.symbol}</div>
                          <div className="font-mono text-[10px] text-muted">{item.symbol}</div>
                        </td>
                        <td className="px-2 py-1.5">
                          {(item.patterns ?? []).length > 0 ? (
                            <div className="flex max-w-[150px] flex-wrap gap-1">
                              {(item.patterns ?? []).map(tag => (
                                <span key={tag} className="shrink-0 whitespace-nowrap rounded bg-accent/10 px-1.5 py-px text-[10px] text-accent">
                                  {tag}
                                </span>
                              ))}
                            </div>
                          ) : <span className="text-[10px] text-muted">—</span>}
                        </td>
                        <td className="px-2 py-1.5 text-right font-mono text-[11px] text-secondary">{fmtPrice(item.buy_price, priceDigits(item.symbol))}</td>
                        <td className="px-2 py-1.5 text-right font-mono text-[11px] text-secondary">{fmtPrice(item.sell_price, priceDigits(item.symbol))}</td>
                        <td className="px-2 py-1.5 text-right">
                          <div className="font-mono text-[11px] text-secondary">{item.qty}</div>
                          <div className="font-mono text-[9px] text-muted">{item.buy_count}买{item.sell_count}卖</div>
                        </td>
                        <td className={cn('px-2 py-1.5 text-right font-mono text-[11px]', priceColorClass(item.pnl))}>{money(item.pnl, true)}</td>
                        <td className={cn('px-2 py-1.5 text-right font-mono text-[11px]', priceColorClass(item.ret))}>{fmtPct(item.ret)}</td>
                        <td className="px-2 py-1.5 text-right font-mono text-[11px] text-muted">
                          {item.hold_td == null ? `${item.hold_days}天` : `${item.hold_td}日`}
                        </td>
                        <td className="px-3 py-1.5">
                          <div className="flex max-w-[360px] items-center gap-1 overflow-hidden">
                            {(item.tags ?? []).slice(0, 3).map(tag => (
                              <Tag key={tag} tone={tagTone(tag)}>{tag}</Tag>
                            ))}
                            <span className="truncate text-[10px] text-muted">{item.analysis}</span>
                          </div>
                        </td>
                        <td className="px-1 py-1.5 text-center">
                          {item.note && <StickyNote className="h-3 w-3 text-accent" aria-label="有复盘笔记" />}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {filtered.length === 0 && (
                  <div className="px-3 py-8 text-center text-xs text-muted">没有符合条件的交易</div>
                )}
              </div>
            </section>
          </div>
        )}
      </div>

      {selected && <TradeDetail trade={selected} onClose={() => setSelectedKey(null)} />}
    </div>
  )
}
