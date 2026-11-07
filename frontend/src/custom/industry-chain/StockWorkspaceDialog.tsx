import { useEffect, useMemo, useRef, useState } from 'react'
import { ExternalLink, LineChart, Plus, Clock, X } from 'lucide-react'
import type {
  IndustryChainGraph,
  IndustryChainQuotes,
  IndustryChainStockLink,
} from '@/lib/api'
import { cn } from '@/lib/cn'
import { fmtPct, priceColorClass } from '@/lib/format'
import { useCapabilityMatrix, usePreferences } from '@/lib/useSharedQueries'
import { useDialogBackdrop } from '@/lib/useDialogBackdrop'
import { clearFocusSymbol, setFocusSymbol } from '@/lib/useQuoteStream'
import { StockDailyKChart, getDefaultRange } from '@/components/StockDailyKChart'
import { StockMultiDayIntradayChart } from '@/components/StockMultiDayIntradayChart'
import { StockLinkDrawer, type StockDrawerTarget } from './StockLinkDrawer'
import { StockListPanel, quoteMeta, type StockListTarget } from './StockListPanel'
import { StockFinancialSnapshot } from './StockFinancialSnapshot'
import {
  LINK_BASIS_LABELS,
  stockLinksForScope,
} from './layout'

type ChartView = 'daily' | 'intraday'
const INTRADAY_DAYS = [1, 3, 5, 10] as const

interface Props {
  graph: IndustryChainGraph
  target: StockListTarget
  quotes?: IndustryChainQuotes
  quotesLoading?: boolean
  quotesError?: string | null
  saving: boolean
  saveError: string | null
  initialEditor?: StockDrawerTarget | null
  onClose: () => void
  onSaveGraph: (next: IndustryChainGraph) => Promise<unknown>
  onDeleteGraph: (next: IndustryChainGraph) => Promise<unknown>
}

export function StockWorkspaceDialog({
  graph,
  target,
  quotes,
  quotesLoading = false,
  quotesError = null,
  saving,
  saveError,
  initialEditor = null,
  onClose,
  onSaveGraph,
  onDeleteGraph,
}: Props) {
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(target.initialSymbol ?? null)
  const [visibleSymbols, setVisibleSymbols] = useState<string[]>([])
  const [view, setView] = useState<ChartView>('daily')
  const [dailyRange, setDailyRange] = useState(getDefaultRange)
  const [intradayDays, setIntradayDays] = useState<number>(1)
  const [intradayDates, setIntradayDates] = useState<string[]>([])
  const [editor, setEditor] = useState<StockDrawerTarget | null>(initialEditor)
  const [listCollapsed, setListCollapsed] = useState(false)
  const userSelectedRef = useRef(false)
  const backdrop = useDialogBackdrop(onClose)
  const matrix = useCapabilityMatrix()
  const prefs = usePreferences()
  const minuteCapLoading = matrix.isLoading
  const hasMinuteCap = !!matrix.data?.capabilities.find(item => item.id === 'minute')?.usable
  const hasFinancialCap = !!matrix.data?.capabilities.find(item => item.id === 'financial')?.usable
  const intradayRefetchMs = (prefs.data?.minute_intraday_refresh_interval ?? 6) * 1000

  useEffect(() => {
    if (initialEditor) setEditor(initialEditor)
  }, [initialEditor])

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !editor) onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [editor, onClose])

  const visibleKey = visibleSymbols.join(',')
  useEffect(() => {
    const symbols = visibleKey ? visibleKey.split(',') : []
    setSelectedSymbol(current => {
      if (current && symbols.includes(current)) return current
      if (!userSelectedRef.current && target.initialSymbol && symbols.includes(target.initialSymbol)) {
        return target.initialSymbol
      }
      return symbols[0] ?? null
    })
  }, [target.initialSymbol, visibleKey])

  useEffect(() => {
    if (!selectedSymbol) {
      clearFocusSymbol()
      return
    }
    setFocusSymbol(selectedSymbol)
    return () => clearFocusSymbol()
  }, [selectedSymbol])

  useEffect(() => {
    setIntradayDates([])
  }, [selectedSymbol])

  const selectStock = (symbol: string) => {
    userSelectedRef.current = true
    setSelectedSymbol(symbol)
  }

  const node = target.nodeId
    ? graph.nodes.find(item => item.id === target.nodeId)
    : undefined
  const chain = graph.chains.find(item => item.id === target.chainId)
  const category = chain
    ? graph.categories.find(item => item.id === chain.category_id)
    : undefined
  const path = useMemo(() => {
    const byId = new Map(graph.nodes.map(item => [item.id, item]))
    const names: string[] = []
    let current = node
    const visited = new Set<string>()
    while (current && !visited.has(current.id)) {
      visited.add(current.id)
      names.unshift(current.name)
      current = current.parent_id ? byId.get(current.parent_id) : undefined
    }
    return [category?.name, chain?.name, ...names].filter(Boolean).join(' / ')
  }, [category?.name, chain?.name, graph.nodes, node])

  const scopedLinks = useMemo(
    () => stockLinksForScope(graph, target.chainId, target.nodeId),
    [graph, target.chainId, target.nodeId],
  )
  const selectedLinks = selectedSymbol
    ? scopedLinks.filter(link => link.symbol === selectedSymbol)
    : []
  const selectedThemeLinks = selectedLinks.filter(link => link.basis === 'theme_clue')
  const selectedName = selectedSymbol
    ? graph.stock_names?.[selectedSymbol] ?? selectedSymbol
    : null
  const selectedQuote = selectedSymbol
    ? quotes?.rows.find(row => row.symbol === selectedSymbol)
    : undefined
  const intradayDate = intradayDates[intradayDates.length - 1]
  const quoteDate = view === 'intraday'
    ? intradayDate ?? '分时日期加载中'
    : quotes?.as_of ?? '行情日期未知'
  const selectRange = (months: number) => {
    const end = new Date()
    const start = new Date()
    start.setMonth(start.getMonth() - months)
    setDailyRange({
      start: start.toISOString().slice(0, 10),
      end: end.toISOString().slice(0, 10),
    })
  }

  const openEditor = (next: StockDrawerTarget) => setEditor(next)
  const closeEditor = () => setEditor(null)
  const addStock = () => {
    if (!target.nodeId) return
    openEditor({ mode: 'add', nodeId: target.nodeId, nodeName: target.name })
  }
  const editLink = (link: IndustryChainStockLink) => openEditor({
    mode: 'edit',
    nodeId: link.node_id,
    nodeName: graph.nodes.find(item => item.id === link.node_id)?.name ?? target.name,
    link,
  })
  const saveGraph = async (next: IndustryChainGraph) => {
    try {
      await onSaveGraph(next)
      closeEditor()
    } catch {
      return
    }
  }
  const deleteGraph = async (next: IndustryChainGraph) => {
    try {
      await onDeleteGraph(next)
      closeEditor()
    } catch {
      return
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4">
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        {...backdrop}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`${target.name}股票与行情`}
        className="relative flex h-[94vh] w-full max-w-[1500px] flex-col overflow-hidden rounded-dialog border border-border bg-surface shadow-2xl"
      >
        <div className="flex shrink-0 items-start justify-between gap-4 border-b border-border px-4 py-3">
          <div className="min-w-0">
            <div className="truncate font-mono text-[9px] uppercase tracking-[0.14em] text-muted">
              {path || chain?.name || '产业链'}
            </div>
            <div className="mt-0.5 flex items-center gap-2">
              <h2 className="truncate text-[17px] font-semibold text-foreground">{target.name}</h2>
              <span className="shrink-0 rounded-full bg-elevated px-2 py-0.5 text-[9px] text-muted">
                {node?.description ? node.kind === 'product' ? '产品' : node.kind === 'application' ? '应用' : '环节' : '节点'}
              </span>
            </div>
          </div>
          {!editor && (
            <button
              type="button"
              onClick={() => setListCollapsed(current => !current)}
              aria-expanded={!listCollapsed}
              className="ml-auto shrink-0 rounded border border-border px-2 py-1.5 text-[10px] text-muted md:hidden"
            >
              {listCollapsed ? '展开股票列表' : '收起股票列表'}
            </button>
          )}
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭产业链股票与行情"
            className="grid h-8 w-8 shrink-0 place-items-center rounded text-muted hover:bg-elevated hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="min-h-0 flex-1">
          {editor && (
            <StockLinkDrawer
              embedded
              key={editor.link?.id ?? `${editor.mode}:${editor.nodeId}`}
              graph={graph}
              target={editor}
              saving={saving}
              error={saveError}
              onClose={closeEditor}
              onSave={next => { void saveGraph(next) }}
              onDelete={next => { void deleteGraph(next) }}
              onOpenQuote={() => undefined}
              onOpenRelated={editLink}
            />
          )}
            <div className={cn('h-full min-h-0 flex-col md:grid-cols-[300px_minmax(0,1fr)]', editor ? 'hidden' : 'flex md:grid')}>
              <div className={cn(
                'h-[44%] min-h-0 shrink-0 overflow-auto md:block md:h-full',
                listCollapsed && 'hidden',
              )}>
                <StockListPanel
                  embedded
                  graph={graph}
                  target={target}
                  quotes={quotes}
                  quotesLoading={quotesLoading}
                  quotesError={quotesError}
                  selectedSymbol={selectedSymbol}
                  onSelect={selectStock}
                  onVisibleSymbolsChange={setVisibleSymbols}
                  onOpenLink={editLink}
                  onAddStock={addStock}
                />
              </div>

              <section className="flex min-h-0 min-w-0 flex-1 flex-col">
                {selectedSymbol && selectedName ? (
                  <>
                    <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border px-4 py-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="truncate text-[15px] font-semibold text-foreground">{selectedName}</span>
                          <span className="font-mono text-[10px] text-muted">{selectedSymbol}</span>
                          <span className={cn('font-mono text-[11px] tabular-nums', priceColorClass(selectedQuote?.change_pct))}>
                            {fmtPct(selectedQuote?.change_pct)}
                          </span>
                        </div>
                        {selectedThemeLinks.length > 0 && (
                          <p
                            className="mt-1 truncate text-[10px] text-warning/90"
                            title={selectedThemeLinks.map(link => link.reason_short).join(' · ')}
                          >
                            {selectedThemeLinks.map(link => link.reason_short).join(' · ')}
                          </p>
                        )}
                        <p className="mt-1 text-[10px] text-muted">
                          {view === 'intraday' ? '分时日期' : '行情日期'} {quoteDate}
                        </p>
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        <div role="tablist" aria-label="产业链股票图表视图" className="inline-flex items-center rounded border border-border bg-base p-0.5">
                          <button
                            type="button"
                            role="tab"
                            aria-selected={view === 'daily'}
                            onClick={() => setView('daily')}
                            className={cn(
                              'inline-flex h-7 items-center gap-1 rounded px-2.5 text-[11px]',
                              view === 'daily' ? 'bg-accent/20 text-accent' : 'text-muted hover:text-foreground',
                            )}
                          >
                            <LineChart className="h-3 w-3" />日线
                          </button>
                          <button
                            type="button"
                            role="tab"
                            aria-selected={view === 'intraday'}
                            onClick={() => setView('intraday')}
                            className={cn(
                              'inline-flex h-7 items-center gap-1 rounded px-2.5 text-[11px]',
                              view === 'intraday' ? 'bg-accent/20 text-accent' : 'text-muted hover:text-foreground',
                            )}
                          >
                            <Clock className="h-3 w-3" />分时
                          </button>
                        </div>
                        {view === 'daily' ? (
                          <div className="inline-flex items-center rounded border border-border bg-base p-0.5">
                            {[
                              { label: '半年', months: 6 },
                              { label: '1年', months: 12 },
                            ].map(item => (
                              <button
                                key={item.label}
                                type="button"
                                onClick={() => selectRange(item.months)}
                                className="h-7 rounded px-2 text-[10px] text-muted hover:bg-elevated hover:text-foreground"
                              >
                                {item.label}
                              </button>
                            ))}
                          </div>
                        ) : (
                          <div className="inline-flex items-center rounded border border-border bg-base p-0.5" aria-label="分时周期">
                            {INTRADAY_DAYS.map(days => (
                              <button
                                key={days}
                                type="button"
                                aria-pressed={intradayDays === days}
                                onClick={() => setIntradayDays(days)}
                                className={cn(
                                  'h-7 rounded px-2 text-[10px]',
                                  intradayDays === days ? 'bg-accent/20 text-accent' : 'text-muted hover:text-foreground',
                                )}
                              >
                                {days}日
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="min-h-0 flex-1 overflow-auto p-3">
                      {view === 'intraday' && minuteCapLoading ? (
                        <div className="grid h-[420px] place-items-center rounded-lg border border-dashed border-border px-6 text-center">
                          <p className="text-[11px] text-muted">正在检查分钟数据能力…</p>
                        </div>
                      ) : view === 'intraday' && !hasMinuteCap ? (
                        <div className="grid h-[420px] place-items-center rounded-lg border border-dashed border-border px-6 text-center">
                          <div>
                            <p className="text-[12px] text-foreground">当前数据源未提供分钟K能力</p>
                            <p className="mt-1 text-[10px] text-muted">可继续查看日线，或在数据源设置中启用分钟数据。</p>
                          </div>
                        </div>
                      ) : view === 'daily' ? (
                        <StockDailyKChart
                          key={`daily:${selectedSymbol}`}
                          symbol={selectedSymbol}
                          height={430}
                          dateRange={dailyRange}
                          showInfoBar={false}
                          visibleBars={80}
                        />
                      ) : (
                        <StockMultiDayIntradayChart
                          key={`intraday:${selectedSymbol}:${intradayDays}`}
                          symbol={selectedSymbol}
                          days={intradayDays}
                          height={430}
                          refetchIntervalMs={intradayRefetchMs}
                          onSessionsChange={setIntradayDates}
                        />
                      )}

                      {hasFinancialCap && (
                        <StockFinancialSnapshot symbol={selectedSymbol} />
                      )}

                      {selectedLinks.length > 0 && (
                        <details className="mt-3 rounded-lg border border-border bg-base/50 px-3 py-2 text-[10px]">
                          <summary className="cursor-pointer select-none text-[11px] font-medium text-secondary">
                            关联说明、来源与核验状态（{selectedLinks.length} 条）
                          </summary>
                          <div className="mt-2 space-y-2">
                            {selectedLinks.map(link => (
                              <div key={link.id} className="rounded border border-border/70 bg-surface/60 px-2.5 py-2">
                                <div className="flex flex-wrap items-center gap-2">
                                  <span className="text-[11px] text-foreground">{link.reason_short}</span>
                                  <span className="rounded bg-elevated px-1.5 py-0.5 text-[8px] text-muted">
                                    {LINK_BASIS_LABELS[link.basis]}
                                  </span>
                                  <span className={cn(
                                    'rounded px-1.5 py-0.5 text-[8px]',
                                    link.evidence_status === 'verified'
                                      ? 'bg-accent/10 text-accent'
                                      : 'bg-warning/10 text-warning',
                                  )}>
                                    {link.evidence_status === 'verified' ? '已核验' : '待核验'}
                                  </span>
                                  <button
                                    type="button"
                                    onClick={() => editLink(link)}
                                    aria-label={`编辑${selectedName}关联：${graph.nodes.find(item => item.id === link.node_id)?.name ?? target.name}`}
                                    className="ml-auto text-[10px] text-accent hover:opacity-80"
                                  >
                                    编辑
                                  </button>
                                </div>
                                {link.note && <p className="mt-1 whitespace-pre-wrap text-muted">{link.note}</p>}
                                {link.source_url && (
                                  <a
                                    href={link.source_url}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="mt-1 inline-flex items-center gap-1 text-accent hover:underline"
                                  >
                                    <ExternalLink className="h-3 w-3" />
                                    查看来源
                                  </a>
                                )}
                              </div>
                            ))}
                          </div>
                        </details>
                      )}
                    </div>
                  </>
                ) : (
                  <div className="grid h-full min-h-[360px] place-items-center px-6 text-center">
                    <div>
                      <p className="text-[13px] text-foreground">暂无关联股票</p>
                      <p className="mt-1 text-[11px] text-muted">
                        {quotesLoading ? '正在读取行情…' : quoteMeta(quotes, quotesLoading, quotesError)}
                      </p>
                      {target.nodeId && (
                        <button
                          type="button"
                          onClick={addStock}
                          className="mt-3 inline-flex items-center gap-1 rounded-btn bg-accent px-3 py-1.5 text-[11px] font-medium text-white hover:bg-accent/90"
                        >
                          <Plus className="h-3.5 w-3.5" />
                          添加股票
                        </button>
                      )}
                    </div>
                  </div>
                )}
              </section>
            </div>
        </div>

        {!editor && quotes && (
          <div className="shrink-0 border-t border-border bg-base/40 px-4 py-1.5 text-[10px] text-muted">
            {quoteMeta(quotes, quotesLoading, quotesError)}
          </div>
        )}
      </div>
    </div>
  )
}
