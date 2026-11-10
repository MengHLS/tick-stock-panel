import { useDeferredValue, useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Loader2, Search } from 'lucide-react'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { boardTag } from '@/components/stock-table/primitives'
import { cn } from '@/lib/cn'

/** 交易计划表单的标的搜索：代码/名称模糊匹配，选中后回填 symbol + name。 */
export function InstrumentSearch({ onSelect }: {
  onSelect: (symbol: string, name: string) => void
}) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [activeIdx, setActiveIdx] = useState(-1)
  const containerRef = useRef<HTMLDivElement>(null)
  const deferred = useDeferredValue(query.trim())

  const search = useQuery({
    queryKey: QK.instrumentSearch(deferred, 'stock,etf'),
    queryFn: () => api.instrumentSearch(deferred, 20, 'stock,etf'),
    enabled: deferred.length > 0,
    staleTime: 30_000,
  })
  const results = search.data?.results ?? []

  useEffect(() => {
    function handleClick(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const select = (item: { symbol: string; name: string }) => {
    onSelect(item.symbol, item.name)
    setQuery('')
    setOpen(false)
    setActiveIdx(-1)
  }

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Escape') {
      setOpen(false)
      return
    }
    if (!open || results.length === 0) return
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActiveIdx(index => Math.min(index + 1, results.length - 1))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActiveIdx(index => Math.max(index - 1, -1))
    } else if (event.key === 'Enter') {
      event.preventDefault()
      select(results[activeIdx >= 0 ? activeIdx : 0])
    }
  }

  return (
    <div ref={containerRef} className="relative">
      <div className="relative flex items-center">
        <Search className="pointer-events-none absolute left-2.5 h-3.5 w-3.5 text-muted" />
        <input
          value={query}
          onChange={event => {
            setQuery(event.target.value)
            setOpen(true)
            setActiveIdx(-1)
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
          placeholder="搜索代码或名称"
          className="h-8 w-full rounded-btn border border-border bg-base pl-8 pr-8 text-[12px] text-foreground outline-none transition-colors placeholder:text-muted focus:border-accent/60"
        />
        {search.isFetching && (
          <Loader2 className="absolute right-2.5 h-3.5 w-3.5 animate-spin text-muted" />
        )}
      </div>

      {open && deferred.length > 0 && (
        <div className="absolute left-0 right-0 top-full z-40 mt-1 max-h-64 overflow-y-auto rounded-card border border-border bg-base shadow-xl">
          {search.isLoading ? (
            <div className="flex items-center justify-center gap-2 px-3 py-4 text-[10px] text-muted">
              <Loader2 className="h-3 w-3 animate-spin" /> 搜索中…
            </div>
          ) : results.length === 0 ? (
            <div className="px-3 py-4 text-center text-[10px] text-muted">未找到匹配标的</div>
          ) : (
            results.map((item, index) => {
              const board = boardTag(item.symbol)
              return (
                <button
                  key={item.symbol}
                  type="button"
                  onMouseDown={event => event.preventDefault()}
                  onClick={() => select(item)}
                  className={cn(
                    'flex w-full items-center gap-2 px-3 py-2 text-left text-[11px] transition-colors',
                    index === activeIdx
                      ? 'bg-accent/10 text-accent'
                      : 'text-foreground hover:bg-elevated',
                  )}
                >
                  <span className="w-[78px] shrink-0 font-mono text-[10px]">{item.symbol}</span>
                  <span className="min-w-0 flex-1 truncate">{item.name}</span>
                  {item.asset_type === 'etf' && (
                    <span className="shrink-0 rounded bg-sky-500/10 px-1 py-0.5 text-[8px] text-sky-400">ETF</span>
                  )}
                  {board && (
                    <span className={cn('shrink-0 rounded border px-1 py-0.5 text-[8px] leading-none', board.color)}>
                      {board.label}
                    </span>
                  )}
                </button>
              )
            })
          )}
        </div>
      )}
    </div>
  )
}
