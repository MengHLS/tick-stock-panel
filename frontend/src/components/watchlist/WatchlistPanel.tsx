import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search } from 'lucide-react'
import { api, type WatchlistGroup } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { cn } from '@/lib/cn'
import { WatchlistGroupMenu } from '@/components/WatchlistAddMenu'
import {
  filterWatchlistEntries,
  watchlistGroupCounts,
  type WatchlistGroupFilter,
} from '@/lib/watchlistGroups'

/**
 * 自选列表面板（可复用插件件）。
 *
 * - 与自选页共享 QK.watchlist / QK.watchlistGroups 缓存，不产生第二套列表数据；
 * - 分组来自后端分组配置，支持全部 / 未分组 / 具体分组切换；
 * - 仅负责展示与选择，不写自选，不改变调用方状态模型。
 */
export interface WatchlistPanelProps {
  activeSymbol?: string
  onSelect: (symbol: string, name: string | null) => void
  /** 是否显示本地搜索框（默认显示） */
  showSearch?: boolean
  className?: string
  title?: string
  initialGroup?: WatchlistGroupFilter
}

export function WatchlistPanel({
  activeSymbol,
  onSelect,
  showSearch = true,
  className,
  title = '自选',
  initialGroup = 'all',
}: WatchlistPanelProps) {
  const [group, setGroup] = useState<WatchlistGroupFilter>(initialGroup)
  const [query, setQuery] = useState('')

  const entriesQ = useQuery({
    queryKey: QK.watchlist,
    queryFn: api.watchlistList,
    staleTime: 60_000,
  })
  const groupsQ = useQuery({
    queryKey: QK.watchlistGroups,
    queryFn: api.watchlistGroups,
    staleTime: 60_000,
  })

  const entries = entriesQ.data?.symbols ?? []
  const groups: WatchlistGroup[] = groupsQ.data?.groups ?? []
  const counts = useMemo(() => watchlistGroupCounts(entries), [entries])
  const groupLabel = group === 'all'
    ? '全部'
    : group === 'ungrouped'
      ? '未分组'
      : groups.find(item => item.id === group)?.name ?? '全部'

  const filtered = useMemo(() => {
    const scoped = filterWatchlistEntries(entries, group)
    const keyword = query.trim().toLowerCase()
    if (!keyword) return scoped
    return scoped.filter(entry =>
      entry.symbol.toLowerCase().includes(keyword)
      || (entry.name ?? '').toLowerCase().includes(keyword),
    )
  }, [entries, group, query])

  return (
    <aside className={cn('flex min-h-0 flex-col', className)} aria-label="自选列表">
      <div className="flex items-center justify-between px-3 pb-1 pt-2">
        <span className="text-[11px] text-muted">{title}</span>
        <span className="text-[10px] text-muted tabular">{filtered.length}/{entries.length}</span>
      </div>
      <div className="px-1.5 pb-1">
        <WatchlistGroupMenu
          includeAll
          counts={counts}
          total={entries.length}
          /* 菜单用 null 表示“未分组”，'all' 为独立取值，不能合并 */
          onSelect={groupId => setGroup(groupId === 'all' ? 'all' : groupId === null ? 'ungrouped' : groupId)}
          preferredGroupId={group === 'all' ? '__all__' : group === 'ungrouped' ? null : group}
          disabled={entriesQ.isPending}
          menuLabel="选择自选分组"
          ariaLabel="选择自选分组"
          align="left"
          triggerClassName="flex w-full items-center justify-between gap-1 rounded border border-border bg-surface px-2 py-1 text-[11px] text-secondary hover:border-accent/50 hover:text-foreground disabled:opacity-50"
        >
          <span className="truncate">{groupLabel}</span>
        </WatchlistGroupMenu>
      </div>
      {showSearch && (
        <div className="px-1.5 pb-1">
          <label className="flex items-center gap-1 rounded border border-border bg-surface px-1.5 py-1">
            <Search className="h-3 w-3 shrink-0 text-muted" strokeWidth={1.5} />
            <input
              value={query}
              onChange={event => setQuery(event.target.value)}
              placeholder="筛选"
              aria-label="筛选自选标的"
              className="min-w-0 flex-1 bg-transparent text-[11px] text-foreground outline-none placeholder:text-muted"
            />
          </label>
        </div>
      )}
      <div className="min-h-0 flex-1 overflow-auto px-1.5 pb-2">
        {entriesQ.isPending && <p className="px-2 py-2 text-[11px] text-muted">读取中</p>}
        {!entriesQ.isPending && entries.length === 0 && <p className="px-2 py-2 text-[11px] text-muted">自选为空</p>}
        {!entriesQ.isPending && entries.length > 0 && filtered.length === 0 && (
          <p className="px-2 py-2 text-[11px] text-muted">{query.trim() ? '无匹配' : '该分组暂无标的'}</p>
        )}
        {filtered.map(entry => (
          <button
            key={entry.symbol}
            type="button"
            aria-current={entry.symbol === activeSymbol ? 'true' : undefined}
            onClick={() => onSelect(entry.symbol, entry.name ?? null)}
            className={cn(
              'mb-0.5 flex w-full flex-col items-start rounded px-2 py-1 text-left hover:bg-elevated/70',
              entry.symbol === activeSymbol && 'bg-accent/10',
            )}
          >
            <span className="w-full truncate text-[12px]">{entry.name || entry.symbol}</span>
            <span className="text-[10px] text-muted num">{entry.symbol}</span>
          </button>
        ))}
      </div>
    </aside>
  )
}
