import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Check, ChevronsUp, Folder } from 'lucide-react'
import type { WatchlistGroup } from '@/lib/api'
import { ExtensionSlot } from '@/extensions/ExtensionSlot'
import { cn } from '@/lib/cn'
import { resolveWatchlistGroupColor } from '@/lib/watchlist-group-colors'

export interface WatchlistRowMenuState {
  x: number
  y: number
  symbol: string
  name: string | null
}

/** 自选行右键菜单：核心操作 + 扩展插槽。 */
export function WatchlistRowMenu({
  menu,
  onClose,
  groups,
  groupIds,
  inWatchlist,
  isTop,
  moveTopBusy,
  groupBusy,
  onMoveToTop,
  onToggleGroup,
}: {
  menu: WatchlistRowMenuState
  onClose: () => void
  groups: WatchlistGroup[]
  groupIds: string[]
  inWatchlist: boolean
  isTop: boolean
  moveTopBusy: boolean
  groupBusy: boolean
  onMoveToTop: () => void
  onToggleGroup: (groupId: string, member: boolean) => void
}) {
  const menuRef = useRef<HTMLDivElement>(null)
  const pinnedRef = useRef(false)
  const [position, setPosition] = useState({ left: menu.x, top: menu.y })

  useLayoutEffect(() => {
    const rect = menuRef.current?.getBoundingClientRect()
    if (!rect) return
    const margin = 8
    const left = Math.max(margin, Math.min(menu.x, window.innerWidth - rect.width - margin))
    const top = Math.max(margin, Math.min(menu.y, window.innerHeight - rect.height - margin))
    setPosition(prev => (prev.left === left && prev.top === top ? prev : { left, top }))
  }, [menu.x, menu.y])

  useEffect(() => {
    const closeOnOutside = (event: MouseEvent) => {
      if (pinnedRef.current) return
      const target = event.target as Node
      if (menuRef.current?.contains(target)) return
      onClose()
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (pinnedRef.current || event.key !== 'Escape') return
      event.preventDefault()
      event.stopPropagation()
      onClose()
    }
    const closeOnScroll = (event: Event) => {
      if (pinnedRef.current) return
      if (event.target instanceof Node && menuRef.current?.contains(event.target)) return
      onClose()
    }

    document.addEventListener('mousedown', closeOnOutside)
    document.addEventListener('keydown', closeOnEscape)
    document.addEventListener('scroll', closeOnScroll, true)
    return () => {
      document.removeEventListener('mousedown', closeOnOutside)
      document.removeEventListener('keydown', closeOnEscape)
      document.removeEventListener('scroll', closeOnScroll, true)
    }
  }, [onClose])

  return createPortal(
    <div
      ref={menuRef}
      role="menu"
      className="fixed z-[60] w-[240px] overflow-hidden rounded-card border border-border bg-surface py-1 shadow-2xl"
      style={{ left: position.left, top: position.top }}
    >
      <div className="flex items-center gap-2 border-b border-border/60 px-3 py-2">
        <span className="font-mono text-[10px] text-secondary">{menu.symbol}</span>
        {menu.name && <span className="min-w-0 truncate text-[10px] text-muted">{menu.name}</span>}
      </div>

      {inWatchlist && (
        <div className="py-0.5">
          <button
            type="button"
            role="menuitem"
            disabled={isTop || moveTopBusy}
            onClick={() => {
              onMoveToTop()
              onClose()
            }}
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-[11px] text-foreground transition-colors hover:bg-elevated disabled:cursor-not-allowed disabled:opacity-40"
          >
            <ChevronsUp className="h-3.5 w-3.5 text-accent" />
            置顶股票
          </button>
        </div>
      )}

      {inWatchlist && groups.length > 0 && (
        <>
          <div className="border-t border-border/60 px-3 pb-0.5 pt-1.5 text-[9px] text-muted">分组</div>
          <div className="max-h-44 overflow-y-auto pb-0.5">
            {groups.map(group => {
              const member = groupIds.includes(group.id)
              const color = resolveWatchlistGroupColor(group.color)
              return (
                <button
                  key={group.id}
                  type="button"
                  role="menuitemcheckbox"
                  aria-checked={member}
                  disabled={groupBusy}
                  onClick={() => onToggleGroup(group.id, !member)}
                  className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[11px] text-foreground transition-colors hover:bg-elevated disabled:cursor-wait disabled:opacity-50"
                >
                  <Folder className={cn('h-3.5 w-3.5 shrink-0', color?.text ?? 'text-muted')} />
                  <span className="min-w-0 flex-1 truncate">{group.name}</span>
                  <Check className={cn('h-3.5 w-3.5 shrink-0', member ? 'text-accent' : 'text-transparent')} />
                </button>
              )
            })}
          </div>
        </>
      )}

      <div className="border-t border-border/60 py-0.5">
        <ExtensionSlot
          name="watchlist.row-menu"
          context={{
            apiVersion: 1,
            symbol: menu.symbol,
            name: menu.name,
            close: onClose,
            setPinned: pinned => { pinnedRef.current = pinned },
          }}
        />
      </div>
    </div>,
    document.body,
  )
}
