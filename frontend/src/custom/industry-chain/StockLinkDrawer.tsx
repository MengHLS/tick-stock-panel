import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ExternalLink, Loader2, Search, Trash2, X } from 'lucide-react'
import { api, type IndustryChainGraph, type IndustryChainStockLink } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { cn } from '@/lib/cn'
import { LINK_BASIS_LABELS, stockChainAssociations } from './layout'

export interface StockDrawerTarget {
  mode: 'edit' | 'add'
  nodeId: string
  nodeName: string
  link?: IndustryChainStockLink
}

interface Props {
  graph: IndustryChainGraph
  target: StockDrawerTarget
  saving: boolean
  error: string | null
  embedded?: boolean
  onClose: () => void
  onSave: (graph: IndustryChainGraph) => void
  onDelete: (graph: IndustryChainGraph) => void
  onOpenQuote: (symbol: string, name: string) => void
  onOpenRelated: (link: IndustryChainStockLink) => void
}

export function StockLinkDrawer({
  graph,
  target,
  saving,
  error,
  embedded = false,
  onClose,
  onSave,
  onDelete,
  onOpenQuote,
  onOpenRelated,
}: Props) {
  const link = target.link
  const [symbol, setSymbol] = useState(link?.symbol ?? '')
  const [stockName, setStockName] = useState(
    link ? graph.stock_names?.[link.symbol] ?? link.symbol : '',
  )
  const [symbolQuery, setSymbolQuery] = useState('')
  const [reason, setReason] = useState(link?.reason_short ?? '')
  const [note, setNote] = useState(link?.note ?? '')
  const [sourceUrl, setSourceUrl] = useState(link?.source_url ?? '')
  const [status, setStatus] = useState<'verified' | 'pending'>(
    link?.evidence_status ?? 'pending',
  )
  const [basis, setBasis] = useState<'main_business' | 'supply' | 'theme_clue'>(
    link?.basis ?? 'main_business',
  )
  const [localError, setLocalError] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(false)

  const searchQuery = useQuery({
    queryKey: QK.instrumentSearch(symbolQuery.trim(), 'stock'),
    queryFn: () => api.instrumentSearch(symbolQuery.trim(), 20, 'stock'),
    enabled: target.mode === 'add' && !symbol && symbolQuery.trim().length > 0,
  })
  const results = searchQuery.data?.results ?? []
  const typedSymbol = useMemo(() => normalizeSymbol(symbolQuery), [symbolQuery])
  const reasonLength = [...reason.trim()].length
  const reasonInvalid = reasonLength < 5 || reasonLength > 20
  const related = useMemo(
    () => stockChainAssociations(graph, symbol, target.nodeId),
    [graph, symbol, target.nodeId],
  )

  const choose = (nextSymbol: string, nextName: string) => {
    setSymbol(nextSymbol)
    setStockName(nextName)
    setSymbolQuery('')
    setLocalError('')
  }

  const submit = () => {
    setLocalError('')
    if (!symbol) {
      setLocalError('请先选择股票')
      return
    }
    if (!/^\d{6}\.(SH|SZ|BJ)$/.test(symbol)) {
      setLocalError('股票代码格式应为 000001.SZ')
      return
    }
    if (reasonInvalid) {
      setLocalError('产业关联理由需为 5～20 个字符')
      return
    }
    if (sourceUrl.trim() && !/^https?:\/\//i.test(sourceUrl.trim())) {
      setLocalError('来源链接只允许 http(s) 地址')
      return
    }
    const duplicate = graph.stock_links.some(item =>
      item.id !== link?.id && item.node_id === target.nodeId && item.symbol === symbol,
    )
    if (duplicate) {
      setLocalError('该节点已关联这只股票，请直接编辑原关联')
      return
    }

    const nextLink: IndustryChainStockLink = {
      id: link?.id ?? newLinkId(),
      node_id: target.nodeId,
      symbol,
      reason_short: reason.trim(),
      note: note.trim(),
      source_url: sourceUrl.trim(),
      evidence_status: status,
      basis,
      sort_order: link?.sort_order ?? nextSortOrder(graph, target.nodeId),
    }
    onSave({
      ...graph,
      stock_links: link
        ? graph.stock_links.map(item => item.id === link.id ? nextLink : item)
        : [...graph.stock_links, nextLink],
    })
  }

  const remove = () => {
    if (!link) return
    onDelete({
      ...graph,
      stock_links: graph.stock_links.filter(item => item.id !== link.id),
    })
  }

  return (
    <div className={embedded ? 'flex h-full min-h-0 w-full' : 'absolute inset-0 z-30 flex justify-end'}>
      {!embedded && (
        <button
          type="button"
          aria-label="关闭股票关联面板"
          className="absolute inset-0 bg-black/30 backdrop-blur-[1px] dark:bg-black/45"
          onClick={onClose}
        />
      )}
      <aside className={cn(
        'flex h-full w-full flex-col bg-surface',
        embedded ? 'min-h-0' : 'relative max-w-[420px] border-l border-border shadow-2xl',
      )}>
        <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
          <div className="min-w-0">
            <div className="text-[10px] uppercase tracking-[0.16em] text-muted">
              {target.mode === 'add' ? 'ADD STOCK LINK' : 'STOCK LINK'}
            </div>
            <h2 className="mt-0.5 truncate text-[16px] font-semibold text-foreground">
              {target.mode === 'add' ? '添加股票关联' : '编辑股票关联'}
            </h2>
            <div className="mt-0.5 truncate text-[11px] text-secondary">
              节点 · {target.nodeName}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="grid h-7 w-7 place-items-center rounded text-muted hover:bg-elevated hover:text-foreground"
            aria-label="关闭"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4">
          {error && (
            <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-[11px] text-danger">
              {error}
            </div>
          )}
          {localError && (
            <div className="rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-[11px] text-warning">
              {localError}
            </div>
          )}

          <section className="space-y-1.5">
            <label className="text-[11px] font-medium text-secondary">股票</label>
            {symbol ? (
              <div className="flex items-center gap-2 rounded-lg border border-border bg-base px-3 py-2.5">
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[13px] font-medium text-foreground">
                    {stockName || symbol}
                  </div>
                  {stockName !== symbol && (
                    <div className="font-mono text-[10px] text-muted">{symbol}</div>
                  )}
                </div>
                {target.mode === 'edit' ? !embedded && (
                  <button
                    type="button"
                    onClick={() => onOpenQuote(symbol, stockName || symbol)}
                    className="inline-flex items-center gap-1 rounded border border-border px-2 py-1 text-[10px] text-secondary hover:border-accent/50 hover:text-foreground"
                  >
                    <ExternalLink className="h-3 w-3" />
                    打开行情
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => { setSymbol(''); setStockName('') }}
                    className="text-[10px] text-muted hover:text-foreground"
                  >
                    更换
                  </button>
                )}
              </div>
            ) : (
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted" />
                <input
                  value={symbolQuery}
                  onChange={event => setSymbolQuery(event.target.value)}
                  placeholder="输入代码或股票名称"
                  autoFocus
                  className="h-9 w-full rounded-lg border border-border bg-base pl-8 pr-3 text-[12px] text-foreground outline-none placeholder:text-muted/70 focus:border-accent/60"
                />
                {(symbolQuery.trim() || results.length > 0) && (
                  <div className="absolute left-0 right-0 top-10 z-10 max-h-52 overflow-y-auto rounded-lg border border-border bg-surface p-1 shadow-2xl">
                    {typedSymbol && (
                      <button
                        type="button"
                        onClick={() => choose(typedSymbol, typedSymbol)}
                        className="flex w-full items-center justify-between rounded px-2 py-2 text-left hover:bg-elevated"
                      >
                        <span className="text-[12px] text-foreground">使用代码 {typedSymbol}</span>
                        <span className="text-[10px] text-muted">手动指定</span>
                      </button>
                    )}
                    {results.map(item => (
                      <button
                        key={item.symbol}
                        type="button"
                        onClick={() => choose(item.symbol, item.name)}
                        className="flex w-full items-center justify-between gap-3 rounded px-2 py-2 text-left hover:bg-elevated"
                      >
                        <span className="truncate text-[12px] text-foreground">{item.name}</span>
                        <span className="shrink-0 font-mono text-[10px] text-muted">{item.symbol}</span>
                      </button>
                    ))}
                    {!typedSymbol && results.length === 0 && !searchQuery.isLoading && (
                      <div className="px-2 py-3 text-center text-[11px] text-muted">未找到匹配股票</div>
                    )}
                    {searchQuery.isLoading && (
                      <div className="flex items-center justify-center gap-2 px-2 py-3 text-[11px] text-muted">
                        <Loader2 className="h-3 w-3 animate-spin" />
                        搜索中
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </section>

          {related.length > 0 && (
            <section className="space-y-1.5">
              <h3 className="text-[11px] font-medium text-secondary">其他产业链关联</h3>
              <p className="text-[10px] leading-4 text-muted">
                同一股票可服务多个产业，每处理由和核验状态单独维护。
              </p>
              {related.map(item => (
                <button
                  key={item.link.id}
                  type="button"
                  disabled={saving}
                  onClick={() => onOpenRelated(item.link)}
                  className="block w-full rounded-lg border border-border bg-base px-3 py-2 text-left hover:bg-elevated disabled:opacity-50"
                >
                  <div className="text-[10px] leading-4 text-muted">{item.path}</div>
                  <div className="mt-1 text-[12px] text-foreground">{item.link.reason_short}</div>
                  <div className="mt-1 text-[10px] text-muted">
                    {LINK_BASIS_LABELS[item.link.basis]} · {item.link.evidence_status === 'verified' ? '已核验' : '待核验'}
                  </div>
                </button>
              ))}
            </section>
          )}

          <section className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-[11px] font-medium text-secondary">产业关联理由</label>
              <span className={cn(
                'font-mono text-[10px]',
                reasonInvalid ? 'text-warning' : 'text-muted',
              )}>
                {reasonLength}/20
              </span>
            </div>
            <textarea
              value={reason}
              onChange={event => setReason(event.target.value)}
              rows={2}
              maxLength={20}
              placeholder="例：研发制造高速光收发模块"
              className="w-full resize-none rounded-lg border border-border bg-base px-3 py-2 text-[12px] leading-5 text-foreground outline-none placeholder:text-muted/70 focus:border-accent/60"
            />
            <p className="text-[10px] leading-4 text-muted">
              5～20 字，直接显示在右侧股票列表中；同一股票在不同节点的理由各自独立。
            </p>
          </section>

          <section className="space-y-1.5">
            <label className="text-[11px] font-medium text-secondary">归属依据</label>
            <div className="grid grid-cols-3 gap-1 rounded-lg border border-border bg-base p-1">
              {([
                ['main_business', '主营/产品', '公司自身业务'],
                ['supply', '供应配套', '产品或材料供应'],
                ['theme_clue', '题材线索', '待正式核验'],
              ] as const).map(([value, label, hint]) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setBasis(value)}
                  className={cn(
                    'rounded-md px-2 py-1.5 text-left transition-colors',
                    basis === value
                      ? 'bg-accent/15 text-accent'
                      : 'text-muted hover:bg-elevated hover:text-foreground',
                  )}
                >
                  <div className="text-[10px] font-medium">{label}</div>
                  <div className="mt-0.5 text-[8px] opacity-75">{hint}</div>
                </button>
              ))}
            </div>
            <p className="text-[10px] leading-4 text-muted">
              历史涨停题材仅是线索；只有公司主营或供应关系有来源支持时，才使用前两类。
            </p>
          </section>

          <section className="space-y-1.5">
            <label className="text-[11px] font-medium text-secondary">核验状态</label>
            <div className="grid grid-cols-2 gap-1 rounded-lg border border-border bg-base p-1">
              {([
                ['verified', '已核验', '有可追溯来源'],
                ['pending', '待核验', '保留研究线索'],
              ] as const).map(([value, label, hint]) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setStatus(value)}
                  className={cn(
                    'rounded-md px-2 py-1.5 text-left transition-colors',
                    status === value
                      ? value === 'verified'
                        ? 'bg-accent/15 text-accent'
                        : 'bg-warning/15 text-warning'
                      : 'text-muted hover:bg-elevated hover:text-foreground',
                  )}
                >
                  <div className="text-[11px] font-medium">{label}</div>
                  <div className="mt-0.5 text-[9px] opacity-75">{hint}</div>
                </button>
              ))}
            </div>
          </section>

          <section className="space-y-1.5">
            <label className="text-[11px] font-medium text-secondary">来源链接</label>
            <input
              value={sourceUrl}
              onChange={event => setSourceUrl(event.target.value)}
              maxLength={500}
              placeholder="https://..."
              className="h-9 w-full rounded-lg border border-border bg-base px-3 text-[12px] text-foreground outline-none placeholder:text-muted/70 focus:border-accent/60"
            />
            <p className="text-[10px] text-muted">只填写可公开访问的公司公告、官网或交易所页面。</p>
          </section>

          <section className="space-y-1.5">
            <label className="text-[11px] font-medium text-secondary">长备注</label>
            <textarea
              value={note}
              onChange={event => setNote(event.target.value)}
              rows={4}
              maxLength={2000}
              placeholder="补充产品、客户、产能或核验记录；不要填写未经验证的份额或订单预测。"
              className="w-full resize-y rounded-lg border border-border bg-base px-3 py-2 text-[12px] leading-5 text-foreground outline-none placeholder:text-muted/70 focus:border-accent/60"
            />
          </section>
        </div>

        <div className="flex items-center justify-between gap-2 border-t border-border px-4 py-3">
          <div>
            {target.mode === 'edit' && !confirmDelete && (
              <button
                type="button"
                onClick={() => setConfirmDelete(true)}
                disabled={saving}
                className="inline-flex items-center gap-1.5 rounded-btn px-2 py-1.5 text-[11px] text-danger hover:bg-danger/10 disabled:opacity-50"
              >
                <Trash2 className="h-3.5 w-3.5" />
                删除关联
              </button>
            )}
            {target.mode === 'edit' && confirmDelete && (
              <div className="flex items-center gap-1.5 text-[10px]">
                <span className="text-danger">确认删除？</span>
                <button
                  type="button"
                  onClick={() => setConfirmDelete(false)}
                  className="rounded px-1.5 py-1 text-muted hover:bg-elevated hover:text-foreground"
                >
                  取消
                </button>
                <button
                  type="button"
                  onClick={remove}
                  disabled={saving}
                  className="rounded bg-danger/15 px-1.5 py-1 font-medium text-danger hover:bg-danger/25 disabled:opacity-50"
                >
                  确认删除
                </button>
              </div>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-btn border border-border px-3 py-1.5 text-[11px] text-secondary hover:bg-elevated hover:text-foreground"
            >
              取消
            </button>
            <button
              type="button"
              onClick={submit}
              disabled={saving || reasonInvalid || !symbol}
              className="inline-flex items-center gap-1.5 rounded-btn bg-accent px-3 py-1.5 text-[11px] font-medium text-white hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              {saving ? '保存中' : '保存'}
            </button>
          </div>
        </div>
      </aside>
    </div>
  )
}

function nextSortOrder(graph: IndustryChainGraph, nodeId: string): number {
  const values = graph.stock_links
    .filter(item => item.node_id === nodeId)
    .map(item => item.sort_order)
  return (values.length ? Math.max(...values) : 0) + 10
}

function newLinkId(): string {
  return `l-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

function normalizeSymbol(value: string): string | null {
  const raw = value.trim().toUpperCase()
  if (/^\d{6}\.(SH|SZ|BJ)$/.test(raw)) return raw
  if (!/^\d{6}$/.test(raw)) return null
  if (raw.startsWith('6')) return `${raw}.SH`
  if (raw.startsWith('4') || raw.startsWith('8')) return `${raw}.BJ`
  return `${raw}.SZ`
}
