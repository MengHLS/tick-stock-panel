import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Loader2,
  RefreshCw,
  RotateCcw,
  Search,
  X,
} from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { toast } from '@/components/Toast'
import { ApiError, api, type IndustryChainGraph } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { cn } from '@/lib/cn'
import { GraphCanvas } from './GraphCanvas'
import type { StockDrawerTarget } from './StockLinkDrawer'
import type { StockListTarget } from './StockListPanel'
import { StockWorkspaceDialog } from './StockWorkspaceDialog'
import {
  EMPTY_SEARCH,
  buildLayout,
  defaultExpandedKeys,
  searchGraph,
  nodeKey,
  stockKey,
  visibleStockLinks,
} from './layout'

export function IndustryChainPage() {
  const queryClient = useQueryClient()
  const initialized = useRef(false)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [search, setSearch] = useState('')
  const [resetSignal, setResetSignal] = useState(0)
  const [stockListTarget, setStockListTarget] = useState<StockListTarget | null>(null)
  const [workspaceEditor, setWorkspaceEditor] = useState<StockDrawerTarget | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)

  const graphQuery = useQuery({
    queryKey: QK.industryChainGraph,
    queryFn: api.industryChainGraph,
    staleTime: 30_000,
  })
  const graph = graphQuery.data

  useEffect(() => {
    if (!graph || initialized.current) return
    initialized.current = true
    setExpanded(defaultExpandedKeys(graph))
    setResetSignal(value => value + 1)
  }, [graph])

  const searchState = useMemo(
    () => graph ? searchGraph(graph, search) : EMPTY_SEARCH,
    [graph, search],
  )
  const layout = useMemo(
    () => graph ? buildLayout(graph, expanded, searchState) : null,
    [expanded, graph, searchState],
  )

  useEffect(() => {
    if (!graph || !searchState.active || !searchState.firstMatch?.startsWith('node:')) return
    const matched = visibleStockLinks(graph).find(link =>
      nodeKey(link.node_id) === searchState.firstMatch && searchState.matched.has(stockKey(link.id)),
    )
    const node = matched && graph.nodes.find(item => item.id === matched.node_id)
    if (!node) return
    setWorkspaceEditor(null)
    setStockListTarget({
      chainId: node.chain_id,
      nodeId: node.id,
      name: node.name,
      filter: searchState.query,
      initialSymbol: matched.symbol,
    })
  }, [graph, searchState])

  const quotesQuery = useQuery({
    queryKey: QK.industryChainQuotes,
    queryFn: api.industryChainQuotes,
    enabled: !!stockListTarget,
    // 面板打开时一次拉取全图谱股票；SSE 到达时立即失效，轮询仅作兜底。
    staleTime: 15_000,
    refetchInterval: stockListTarget ? 30_000 : false,
  })

  const saveMutation = useMutation({
    mutationFn: (next: IndustryChainGraph) =>
      api.industryChainSaveGraph(next, next.updated_at),
    onSuccess: saved => {
      queryClient.setQueryData(QK.industryChainGraph, saved)
      queryClient.invalidateQueries({ queryKey: QK.industryChainRoot })
      queryClient.invalidateQueries({ queryKey: QK.industryChainQuotes })
      queryClient.invalidateQueries({ queryKey: QK.themeAnalyzerRoot })
      setSaveError(null)
      toast('股票关联已保存', 'success')
    },
    onError: error => {
      setSaveError(error instanceof Error ? error.message : String(error))
      if (error instanceof ApiError && error.status === 409) {
        void graphQuery.refetch()
      }
    },
  })

  const toggle = (key: string) => {
    setExpanded(current => {
      const next = new Set(current)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const openStocks = (target: StockListTarget) => {
    setWorkspaceEditor(null)
    setSaveError(null)
    setStockListTarget(target)
  }

  const openAddStock = (nodeId: string, nodeName: string) => {
    if (!graph) return
    const node = graph.nodes.find(item => item.id === nodeId)
    if (!node) return
    setSaveError(null)
    setStockListTarget({ chainId: node.chain_id, nodeId, name: nodeName })
    setWorkspaceEditor({ mode: 'add', nodeId, nodeName })
  }

  const resetView = () => {
    if (graph) setExpanded(defaultExpandedKeys(graph))
    setSearch('')
    setStockListTarget(null)
    setWorkspaceEditor(null)
    setSaveError(null)
    setResetSignal(value => value + 1)
  }

  const refresh = () => {
    void graphQuery.refetch()
    if (stockListTarget) void quotesQuery.refetch()
  }

  return (
    <div className="flex h-full min-h-[640px] flex-col overflow-hidden bg-base">
      <PageHeader
        title="产业链图谱"
        right={
          <div className="flex items-center gap-1.5">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted" />
              <input
                value={search}
                onChange={event => {
                  setSearch(event.target.value)
                }}
                placeholder="搜索产业链 / 节点 / 股票 / 理由"
                className="h-8 w-[210px] rounded-lg border border-border bg-surface pl-8 pr-8 text-[11px] text-foreground outline-none placeholder:text-muted/70 focus:border-accent/60 lg:w-[280px]"
                aria-label="搜索产业链图谱"
              />
              {search && (
                <button
                  type="button"
                  onClick={() => setSearch('')}
                  aria-label="清除搜索"
                  className="absolute right-1.5 top-1/2 grid h-5 w-5 -translate-y-1/2 place-items-center rounded text-muted hover:bg-elevated hover:text-foreground"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </div>
            <button
              type="button"
              onClick={refresh}
              disabled={graphQuery.isFetching}
              className="grid h-8 w-8 place-items-center rounded-lg border border-border bg-surface text-muted hover:text-foreground disabled:opacity-50"
              title="刷新图谱"
            >
              <RefreshCw className={cn('h-3.5 w-3.5', graphQuery.isFetching && 'animate-spin')} />
            </button>
            <button
              type="button"
              onClick={resetView}
              className="grid h-8 w-8 place-items-center rounded-lg border border-border bg-surface text-muted hover:text-foreground"
              title="恢复默认展开与视图"
            >
              <RotateCcw className="h-3.5 w-3.5" />
            </button>
          </div>
        }
      />

      <div className="min-h-0 flex-1 p-3 lg:p-4">
        <div className="relative h-full min-h-[560px] overflow-hidden rounded-2xl border border-border bg-[#f3f5f8] shadow-sm dark:bg-[#070a0f] dark:shadow-[0_20px_60px_rgba(0,0,0,0.28)]">
          {graphQuery.isLoading && (
            <div className="grid h-full place-items-center text-muted">
              <div className="flex items-center gap-2 text-[12px]">
                <Loader2 className="h-4 w-4 animate-spin" />
                载入产业链图谱
              </div>
            </div>
          )}

          {graphQuery.isError && (
            <div className="grid h-full place-items-center px-6 text-center">
              <div>
                <p className="text-[13px] text-foreground">产业链图谱读取失败</p>
                <p className="mt-1 max-w-md text-[11px] leading-5 text-muted">
                  {graphQuery.error instanceof Error ? graphQuery.error.message : String(graphQuery.error)}
                </p>
                <button
                  type="button"
                  onClick={() => void graphQuery.refetch()}
                  className="mt-3 rounded-btn border border-border px-3 py-1.5 text-[11px] text-secondary hover:bg-elevated hover:text-foreground"
                >
                  重试
                </button>
              </div>
            </div>
          )}

          {graph && layout && !graphQuery.isLoading && (
            <>
              <GraphCanvas
                layout={layout}
                search={searchState}
                onToggle={toggle}
                onAddStock={openAddStock}
                onOpenStocks={openStocks}
                resetSignal={resetSignal}
              />

              {searchState.active && (
                <div className="pointer-events-none absolute left-1/2 top-3 z-10 hidden -translate-x-1/2 rounded-full border border-border bg-surface/90 px-3 py-1 text-[10px] text-secondary shadow-sm backdrop-blur md:block">
                  {searchState.count > 0
                    ? `${searchState.count} 个直接匹配 · 已自动展开命中路径`
                    : '没有匹配项 · 试试股票代码、节点名或关联理由'}
                </div>
              )}

              {stockListTarget && (
                <StockWorkspaceDialog
                  key={`${stockListTarget.nodeId ?? stockListTarget.chainId}:${stockListTarget.filter ?? ''}:${stockListTarget.initialSymbol ?? ''}`}
                  graph={graph}
                  target={stockListTarget}
                  quotes={quotesQuery.data}
                  quotesLoading={quotesQuery.isLoading}
                  quotesError={quotesQuery.isError || quotesQuery.isRefetchError
                    ? (quotesQuery.error instanceof Error
                      ? quotesQuery.error.message
                      : String(quotesQuery.error))
                    : null}
                  saving={saveMutation.isPending}
                  saveError={saveError}
                  initialEditor={workspaceEditor}
                  onClose={() => {
                    setStockListTarget(null)
                    setWorkspaceEditor(null)
                    setSaveError(null)
                  }}
                  onSaveGraph={next => saveMutation.mutateAsync(next)}
                  onDeleteGraph={next => saveMutation.mutateAsync(next)}
                />
              )}

            </>
          )}
        </div>
      </div>

    </div>
  )
}
