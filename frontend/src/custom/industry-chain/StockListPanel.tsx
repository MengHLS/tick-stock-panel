import { useMemo, useState } from 'react'
import { BarChart3, List, Pencil, Plus, Search, X } from 'lucide-react'
import type { IndustryChainGraph, IndustryChainStockLink } from '@/lib/api'
import { cn } from '@/lib/cn'
import { LINK_BASIS_LABELS, stockLinksForScope } from './layout'

type RelationFilter = 'all' | 'main_business' | 'supply' | 'theme_clue' | 'equity' | 'cooperation' | 'rumor'
type RelationTag = 'equity' | 'cooperation' | 'rumor' | 'supply'

const RELATION_FILTERS: Array<{ value: RelationFilter; label: string }> = [
  { value: 'all', label: '全部' },
  { value: 'main_business', label: '主营/产品' },
  { value: 'supply', label: '供应配套' },
  { value: 'theme_clue', label: '题材线索' },
  { value: 'equity', label: '参股' },
  { value: 'cooperation', label: '合作' },
  { value: 'rumor', label: '传闻' },
]

const RELATION_TAG_LABELS: Record<RelationTag, string> = {
  equity: '参股',
  cooperation: '合作',
  rumor: '传闻',
  supply: '供货',
}

export interface StockListTarget {
  chainId: string
  nodeId: string | null
  name: string
  filter?: string
}

interface Props {
  graph: IndustryChainGraph
  target: StockListTarget
  onClose: () => void
  onOpenLink: (link: IndustryChainStockLink) => void
  onAnalyze: () => void
  onAddStock: () => void
}

export function StockListPanel({ graph, target, onClose, onOpenLink, onAnalyze, onAddStock }: Props) {
  const [filter, setFilter] = useState(target.filter ?? '')
  const [relationFilter, setRelationFilter] = useState<RelationFilter>('all')
  const [verifiedOnly, setVerifiedOnly] = useState(false)
  const links = useMemo(
    () => stockLinksForScope(graph, target.chainId, target.nodeId),
    [graph, target.chainId, target.nodeId],
  )
  const visibleLinks = useMemo(
    () => links.filter(link =>
      matchesRelation(link, relationFilter)
      && (!verifiedOnly || link.evidence_status === 'verified'),
    ),
    [links, relationFilter, verifiedOnly],
  )
  const stocks = useMemo(() => groupStockLinks(links, graph.stock_names), [graph.stock_names, links])
  const visibleStocks = useMemo(
    () => groupStockLinks(visibleLinks, graph.stock_names),
    [graph.stock_names, visibleLinks],
  )
  const nodeNames = useMemo(
    () => new Map(graph.nodes.map(node => [node.id, node.name])),
    [graph.nodes],
  )
  const query = filter.trim().toLowerCase().replace(/\s+/g, '')
  const filtered = visibleStocks.filter(stock => !query || [
    stock.symbol, stock.name,
    ...stock.links.flatMap(link => [link.reason_short, link.note, nodeNames.get(link.node_id) ?? '']),
  ].some(text => text.toLowerCase().replace(/\s+/g, '').includes(query)))
  const filteredLinkCount = filtered.reduce((sum, stock) => sum + stock.links.length, 0)
  const hasChipFilter = relationFilter !== 'all' || verifiedOnly

  return (
    <aside
      aria-label={`${target.name}股票列表`}
      className="absolute inset-y-0 right-0 z-20 flex w-full max-w-[440px] flex-col border-l border-border bg-surface shadow-2xl"
    >
      <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 text-[10px] text-muted">
            <List className="h-3 w-3" />
            成分股票
          </div>
          <h2 className="mt-0.5 truncate text-[16px] font-semibold text-foreground">{target.name}</h2>
          <p className="mt-1 text-[10px] text-muted">
            {stocks.length} 只股票 · {links.length} 条关联
            {hasChipFilter && ` · 筛选后 ${filtered.length} 只 / ${filteredLinkCount} 条`}
          </p>
        </div>
        <button
          type="button"
          aria-label="关闭股票列表"
          onClick={onClose}
          className="grid h-7 w-7 place-items-center rounded text-muted hover:bg-elevated hover:text-foreground"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="space-y-2 border-b border-border px-4 py-3">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted" />
          <input
            aria-label="筛选股票列表"
            placeholder="股票名称 / 代码 / 关联理由"
            value={filter}
            onChange={event => setFilter(event.target.value)}
            className="h-9 w-full rounded-lg border border-border bg-base pl-8 pr-3 text-[12px] text-foreground outline-none placeholder:text-muted/70 focus:border-accent/60"
          />
        </div>
        <div className="flex flex-wrap gap-1">
          {RELATION_FILTERS.map(item => (
            <button
              key={item.value}
              type="button"
              aria-label={`筛选关联性质：${item.label}`}
              aria-pressed={relationFilter === item.value}
              onClick={() => setRelationFilter(item.value)}
              className={cn(
                'rounded-full border px-2 py-1 text-[10px] transition-colors',
                relationFilter === item.value
                  ? 'border-accent/40 bg-accent/15 text-accent'
                  : 'border-border text-muted hover:bg-elevated hover:text-foreground',
              )}
            >
              {item.label}
            </button>
          ))}
        </div>
        <div className="flex items-center justify-between gap-2">
          <button
            type="button"
            aria-label="仅看已核验关联"
            aria-pressed={verifiedOnly}
            onClick={() => setVerifiedOnly(value => !value)}
            className={cn(
              'rounded-full border px-2 py-1 text-[10px] transition-colors',
              verifiedOnly
                ? 'border-accent/40 bg-accent/15 text-accent'
                : 'border-border text-muted hover:bg-elevated hover:text-foreground',
            )}
          >
            仅看已核验
          </button>
          {hasChipFilter && (
            <button
              type="button"
              onClick={() => { setRelationFilter('all'); setVerifiedOnly(false) }}
              className="text-[10px] text-muted hover:text-foreground"
            >
              清除筛选
            </button>
          )}
          <button
            type="button"
            onClick={onAnalyze}
            className="ml-auto inline-flex items-center gap-1 text-[11px] text-muted hover:text-foreground"
          >
            <BarChart3 className="h-3 w-3" />
            查看行情分析
          </button>
          {target.nodeId && (
            <button
              type="button"
              onClick={onAddStock}
              className="inline-flex items-center gap-1 text-[11px] text-accent hover:opacity-80"
            >
              <Plus className="h-3 w-3" />
              添加股票
            </button>
          )}
        </div>
      </div>

      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-4 pb-20">
        {filtered.length === 0 && (
          <p className="py-10 text-center text-[12px] text-muted">
            {stocks.length === 0
              ? '当前范围暂无关联股票'
              : hasChipFilter || query
                ? '没有符合筛选条件的关联'
                : '未找到匹配股票'}
          </p>
        )}
        {filtered.map(stock => (
          <div key={stock.symbol} className="rounded-xl border border-border bg-base/60 p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="truncate text-[13px] font-semibold text-foreground">{stock.name}</span>
              <span className="shrink-0 font-mono text-[10px] text-muted">{stock.symbol}</span>
            </div>
            <div className="mt-2 space-y-1">
              {stock.links.map(link => {
                const tags = relationTags(link)
                return (
                  <button
                    key={link.id}
                    type="button"
                    aria-label={`编辑${stock.name}关联：${nodeNames.get(link.node_id) ?? ''}`}
                    onClick={() => onOpenLink(link)}
                    className="group block w-full rounded-lg px-2 py-2 text-left hover:bg-elevated"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-[12px] leading-5 text-secondary">{link.reason_short}</span>
                      <span className="flex shrink-0 items-center gap-1">
                        {tags.map(tag => (
                          <span
                            key={tag}
                            className={cn(
                              'rounded-full px-1.5 py-0.5 text-[8px]',
                              tag === 'supply'
                                ? 'bg-accent/10 text-accent'
                                : 'bg-warning/10 text-warning',
                            )}
                          >
                            {RELATION_TAG_LABELS[tag]}
                          </span>
                        ))}
                        <Pencil className="mt-1 h-3 w-3 text-muted opacity-50 group-hover:opacity-100" />
                      </span>
                    </div>
                    <div className="mt-1 flex items-center justify-between gap-2 text-[10px]">
                      <span className="truncate text-muted">{nodeNames.get(link.node_id)}</span>
                      <span className="shrink-0 text-muted">{LINK_BASIS_LABELS[link.basis]}</span>
                      <span className={cn(
                        'shrink-0',
                        link.evidence_status === 'verified' ? 'text-accent' : 'text-warning',
                      )}>
                        {link.evidence_status === 'verified' ? '已核验' : '待核验'}
                      </span>
                    </div>
                  </button>
                )
              })}
            </div>
          </div>
        ))}
      </div>
    </aside>
  )
}

function groupStockLinks(
  links: IndustryChainStockLink[],
  stockNames: Record<string, string> | undefined,
) {
  const grouped = new Map<string, IndustryChainStockLink[]>()
  for (const link of links) {
    const entries = grouped.get(link.symbol) ?? []
    entries.push(link)
    grouped.set(link.symbol, entries)
  }
  return [...grouped.entries()]
    .sort(([first], [second]) => first.localeCompare(second))
    .map(([symbol, entries]) => ({
      symbol,
      name: stockNames?.[symbol] ?? symbol,
      links: entries,
    }))
}

function relationTags(link: IndustryChainStockLink): RelationTag[] {
  const text = `${link.reason_short} ${link.note}`
    .replace(/未核验当前主营[、，,]?\s*产品或供货关系[。]?/g, '')
  const rules: Array<[RelationTag, RegExp]> = [
    ['equity', /参股|持股|入股|股权/],
    ['cooperation', /合作|联合|共建|签署|战略/],
    ['rumor', /传闻|网传|猜测|预期|可能|市场消息/],
    ['supply', /供应|供货|客户|订单|配套/],
  ]
  return rules.filter(([, pattern]) => pattern.test(text)).map(([tag]) => tag)
}

function matchesRelation(link: IndustryChainStockLink, filter: RelationFilter): boolean {
  if (filter === 'all') return true
  if (filter === 'main_business' || filter === 'theme_clue') return link.basis === filter
  if (filter === 'supply') return link.basis === 'supply' || relationTags(link).includes('supply')
  return relationTags(link).includes(filter)
}
