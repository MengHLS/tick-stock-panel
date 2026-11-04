import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from 'react'
import {
  BarChart3,
  ChevronDown,
  ChevronRight,
  Maximize2,
  Minus,
  List,
  Plus,
  RotateCcw,
} from 'lucide-react'
import { cn } from '@/lib/cn'
import type { GraphLayout, GraphSearchState, LayoutNode } from './layout'

interface ViewState {
  x: number
  y: number
  scale: number
  instant?: boolean
}

interface Props {
  layout: GraphLayout
  search: GraphSearchState
  onToggle: (key: string) => void
  onAnalyze: (target: { chainId: string; nodeId: string | null; name: string }) => void
  onAddStock: (nodeId: string, nodeName: string) => void
  onOpenStocks: (target: { chainId: string; nodeId: string | null; name: string }) => void
  resetSignal: number
}

export function GraphCanvas({
  layout,
  search,
  onToggle,
  onAnalyze,
  onAddStock,
  onOpenStocks,
  resetSignal,
}: Props) {
  const viewportRef = useRef<HTMLDivElement>(null)
  const dragRef = useRef<{ pointerId: number; x: number; y: number; vx: number; vy: number } | null>(null)
  const lastFocusToken = useRef('')
  const lastFittedResetSignal = useRef<number | null>(null)
  const pendingAnchor = useRef<{ key: string; x: number; y: number } | null>(null)
  const [size, setSize] = useState({ width: 0, height: 0 })
  const [view, setView] = useState<ViewState>({ x: 0, y: 0, scale: 1 })
  const [panning, setPanning] = useState(false)

  useEffect(() => {
    const element = viewportRef.current
    if (!element) return
    const observer = new ResizeObserver(entries => {
      const rect = entries[0]?.contentRect
      if (rect) setSize({ width: rect.width, height: rect.height })
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  const fit = useCallback(() => {
    if (!size.width || !size.height) return
    const scale = clamp(
      Math.min((size.width - 36) / layout.width, (size.height - 36) / layout.height),
      0.3,
      1.05,
    )
    setView({
      x: (size.width - layout.width * scale) / 2,
      y: (size.height - layout.height * scale) / 2,
      scale,
    })
  }, [layout.height, layout.width, size.height, size.width])

  useEffect(() => {
    if (!size.width || !size.height || lastFittedResetSignal.current === resetSignal) return
    lastFittedResetSignal.current = resetSignal
    fit()
  }, [fit, resetSignal, size.height, size.width])

  useLayoutEffect(() => {
    const anchor = pendingAnchor.current
    if (!anchor) return
    pendingAnchor.current = null
    const node = layout.byKey.get(anchor.key)
    if (!node) return
    setView(current => ({
      ...current,
      x: current.x + (anchor.x - node.x) * current.scale,
      y: current.y + (anchor.y - node.y) * current.scale,
      instant: true,
    }))
  }, [layout])

  useEffect(() => {
    const key = search.active ? search.firstMatch : null
    if (!key || !size.width || !size.height) return
    const node = layout.byKey.get(key)
    if (!node) return
    const token = `${key}:${search.query}`
    if (lastFocusToken.current === token) return
    lastFocusToken.current = token
    const scale = Math.max(view.scale, 0.82)
    setView({
      x: size.width / 2 - (node.x + node.width / 2) * scale,
      y: size.height / 2 - (node.y + node.height / 2) * scale,
      scale,
    })
  }, [
    layout,
    search.active,
    search.firstMatch,
    search.query,
    size.height,
    size.width,
    view.scale,
  ])

  useEffect(() => {
    const element = viewportRef.current
    if (!element) return
    const onWheel = (event: WheelEvent) => {
      event.preventDefault()
      const rect = element.getBoundingClientRect()
      const factor = event.deltaY < 0 ? 1.12 : 1 / 1.12
      setView(current => zoomAt(
        current,
        event.clientX - rect.left,
        event.clientY - rect.top,
        factor,
      ))
    }
    element.addEventListener('wheel', onWheel, { passive: false })
    return () => element.removeEventListener('wheel', onWheel)
  }, [])

  const zoomButton = (factor: number) => {
    setView(current => zoomAt(current, size.width / 2, size.height / 2, factor))
  }

  const toggleNode = (key: string) => {
    const node = layout.byKey.get(key)
    if (node) pendingAnchor.current = { key, x: node.x, y: node.y }
    onToggle(key)
  }

  const onPointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return
    const target = event.target as HTMLElement
    if (target.closest('[data-graph-node]') || target.closest('[data-map-control]')) return
    dragRef.current = {
      pointerId: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      vx: view.x,
      vy: view.y,
    }
    event.currentTarget.setPointerCapture(event.pointerId)
    setPanning(true)
  }

  const onPointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current
    if (!drag || drag.pointerId !== event.pointerId) return
    setView(current => ({
      ...current,
      x: drag.vx + event.clientX - drag.x,
      y: drag.vy + event.clientY - drag.y,
    }))
  }

  const endPan = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (dragRef.current?.pointerId !== event.pointerId) return
    dragRef.current = null
    setPanning(false)
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId)
    }
  }

  return (
    <div
      ref={viewportRef}
      role="region"
      aria-label="产业链思维导图画布，可拖拽平移和缩放"
      className={cn(
        'relative h-full w-full overflow-hidden bg-[#f3f5f8] touch-none select-none dark:bg-[#070a0f]',
        panning ? 'cursor-grabbing' : 'cursor-grab',
      )}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endPan}
      onPointerCancel={endPan}
    >
      <div
        className="pointer-events-none absolute inset-0 opacity-70 dark:opacity-80"
        style={{
          backgroundImage: 'radial-gradient(circle, hsl(var(--fg-muted) / 0.38) 1px, transparent 1px)',
          backgroundSize: `${24 * view.scale}px ${24 * view.scale}px`,
          backgroundPosition: `${view.x}px ${view.y}px`,
        }}
      />
      <div
        className="absolute left-0 top-0 origin-top-left"
        style={{
          width: layout.width,
          height: layout.height,
          transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})`,
          transition: panning || view.instant ? 'none' : 'transform 120ms cubic-bezier(0.16, 1, 0.3, 1)',
        }}
      >
        <svg
          className="pointer-events-none absolute left-0 top-0 overflow-visible"
          width={layout.width}
          height={layout.height}
          aria-hidden="true"
        >
          {layout.edges.map(edge => (
            <path
              key={edge.key}
              d={curve(edge.x1, edge.y1, edge.x2, edge.y2)}
              fill="none"
              stroke="currentColor"
              strokeWidth={edge.lit ? 1.8 : 1.25}
              className={cn(
                edge.lit
                  ? 'text-amber-500/80 dark:text-amber-300/80'
                  : 'text-secondary/50 dark:text-secondary/30',
                edge.dimmed && 'opacity-15',
              )}
            />
          ))}
        </svg>
        {layout.nodes.map(node => (
          <GraphNodeCard
            key={node.key}
            node={node}
            onToggle={toggleNode}
            onAnalyze={onAnalyze}
            onAddStock={onAddStock}
            onOpenStocks={onOpenStocks}
          />
        ))}
      </div>

      <div
        data-map-control
        className="absolute bottom-3 right-3 flex items-center gap-1 rounded-lg border border-border bg-surface/90 p-1 shadow-lg backdrop-blur"
      >
        <ToolButton title="缩小" onClick={() => zoomButton(1 / 1.16)}>
          <Minus className="h-3.5 w-3.5" />
        </ToolButton>
        <span className="w-11 text-center font-mono text-[10px] text-secondary">
          {Math.round(view.scale * 100)}%
        </span>
        <ToolButton title="放大" onClick={() => zoomButton(1.16)}>
          <Plus className="h-3.5 w-3.5" />
        </ToolButton>
        <ToolButton title="适应画布" onClick={fit}>
          <Maximize2 className="h-3.5 w-3.5" />
        </ToolButton>
        <ToolButton title="恢复视图" onClick={fit}>
          <RotateCcw className="h-3.5 w-3.5" />
        </ToolButton>
      </div>

      <div className="pointer-events-none absolute bottom-3 left-3 hidden rounded-lg border border-border bg-surface/90 px-2.5 py-1.5 text-[10px] text-muted shadow-sm backdrop-blur md:block">
        拖拽空白平移 · 滚轮缩放 · 点击环节展开 · 末级股票在右侧列表展示
      </div>
    </div>
  )
}

function GraphNodeCard({
  node,
  onToggle,
  onAnalyze,
  onAddStock,
  onOpenStocks,
}: {
  node: LayoutNode
  onToggle: (key: string) => void
  onAnalyze: (target: { chainId: string; nodeId: string | null; name: string }) => void
  onAddStock: (nodeId: string, nodeName: string) => void
  onOpenStocks: (target: { chainId: string; nodeId: string | null; name: string }) => void
}) {
  const canAnalyze = node.type === 'chain' || (node.type === 'node' && !!node.chainId)
  const canAdd = node.type === 'node'
  const openStocks = () => {
    if (!node.chainId) return
    onOpenStocks({
      chainId: node.chainId,
      nodeId: node.type === 'chain' ? null : node.id,
      name: node.name,
    })
  }
  const handleActivate = () => {
    if (node.hasChildren) {
      onToggle(node.key)
      return
    }
    if (canAnalyze && node.stockCount > 0) {
      openStocks()
      return
    }
    if (canAnalyze && node.chainId) {
      onAnalyze({
        chainId: node.chainId,
        nodeId: node.type === 'chain' ? null : node.id,
        name: node.name,
      })
    }
  }
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'Enter' && event.key !== ' ') return
    event.preventDefault()
    handleActivate()
  }

  return (
    <div
      data-graph-node
      className={cn(
        'group absolute transition-opacity duration-150',
        node.dimmed && 'opacity-[0.18] saturate-50',
      )}
      style={{ left: node.x, top: node.y, width: node.width, height: node.height }}
    >
      <div
        role="button"
        tabIndex={0}
        aria-label={`${node.name}${node.hasChildren ? (node.expanded ? '，已展开' : '，已折叠') : node.stockCount > 0 ? '，查看股票列表' : ''}`}
        onClick={handleActivate}
        onKeyDown={onKeyDown}
        className={cn(
          'relative flex h-full w-full cursor-pointer flex-col justify-center overflow-hidden rounded-lg border px-3 text-left outline-none transition-colors focus-visible:ring-2 focus-visible:ring-accent/70',
          cardClass(node),
          node.matched && 'border-amber-400/80 ring-2 ring-amber-400/35 dark:border-amber-300/75 dark:ring-amber-300/35',
        )}
      >
        {node.type === 'root' && (
          <span className="absolute left-3 right-3 top-0 h-px bg-gradient-to-r from-amber-300/0 via-amber-300/80 to-amber-300/0" />
        )}
        <StandardContent node={node} />
      </div>

      <div className="absolute right-1.5 top-1.5 flex items-center gap-1 opacity-60 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
        {canAnalyze && node.chainId && (
          <NodeAction
            title="进入分析"
            label="分析"
            onClick={() => onAnalyze({
              chainId: node.chainId!,
              nodeId: node.type === 'chain' ? null : node.id,
              name: node.name,
            })}
          >
            <BarChart3 className="h-3 w-3" />
          </NodeAction>
        )}
        {canAdd && (
          <NodeAction title="添加股票" onClick={() => onAddStock(node.id, node.name)}>
            <Plus className="h-3 w-3" />
          </NodeAction>
        )}
      </div>

      <div className="absolute bottom-1 right-1.5 flex items-center gap-1 text-[9px] text-muted">
        {canAnalyze && node.stockCount > 0 && (
          <button
            type="button"
            aria-label={`查看${node.name}股票列表`}
            onClick={openStocks}
            className="inline-flex items-center gap-0.5 rounded bg-elevated px-1 py-0.5 text-secondary hover:text-accent"
          >
            <List className="h-2.5 w-2.5" />
            股票 {node.stockCount}
          </button>
        )}
        {node.hasChildren && (
          <span className="pointer-events-none inline-flex items-center gap-0.5 rounded bg-elevated/80 px-1 py-0.5 font-mono">
            {node.childCount}
            {node.expanded
              ? <ChevronDown className="h-2.5 w-2.5" />
              : <ChevronRight className="h-2.5 w-2.5" />}
          </span>
        )}
      </div>
    </div>
  )
}

function StandardContent({ node }: { node: LayoutNode }) {
  if (node.type === 'root') {
    return (
      <>
        <div className="font-mono text-[9px] tracking-[0.16em] text-amber-600 dark:text-amber-300">INDUSTRY MAP</div>
        <div className="mt-0.5 truncate text-[16px] font-semibold text-foreground">{node.name}</div>
        <div className="mt-0.5 truncate text-[10px] text-muted">{node.subtitle}</div>
      </>
    )
  }
  if (node.type === 'category') {
    return (
      <>
        <div className="truncate pr-10 text-[13px] font-semibold text-foreground">{node.name}</div>
        <div className="mt-0.5 truncate text-[10px] text-muted">{node.subtitle}</div>
      </>
    )
  }
  if (node.type === 'chain') {
    return (
      <>
        <div className="flex min-w-0 items-center gap-1.5 pr-16">
          <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500 dark:bg-amber-300" />
          <span className="truncate text-[13px] font-semibold text-foreground">{node.name}</span>
        </div>
        <div className="mt-1 truncate pr-20 text-[10px] text-muted">{node.subtitle}</div>
      </>
    )
  }
  const kindLabel = node.kind === 'product' ? '产品' : node.kind === 'application' ? '应用' : '环节'
  return (
    <>
      <div className="flex min-w-0 items-center gap-1.5 pr-10">
        <span className={cn(
          'shrink-0 rounded px-1 py-px text-[8px]',
          node.kind === 'product'
            ? 'bg-cyan-500/10 text-cyan-700 dark:text-cyan-300'
            : node.kind === 'application'
              ? 'bg-violet-500/10 text-violet-700 dark:text-violet-300'
              : 'bg-sky-500/10 text-sky-700 dark:text-sky-300',
        )}>
          {kindLabel}
        </span>
        <span className="truncate text-[12px] font-medium text-foreground">{node.name}</span>
      </div>
      <div className="mt-1 truncate pr-20 text-[10px] text-muted">{node.subtitle}</div>
    </>
  )
}

function NodeAction({
  title,
  label,
  onClick,
  children,
}: {
  title: string
  label?: string
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      onClick={event => {
        event.stopPropagation()
        onClick()
      }}
      className={cn(
        'flex h-5 items-center justify-center gap-0.5 rounded border border-border bg-surface/90 px-1 text-secondary shadow-sm backdrop-blur transition-colors hover:border-accent/50 hover:bg-elevated hover:text-foreground',
        label ? 'min-w-8 text-[8px]' : 'w-5',
      )}
    >
      {children}
      {label && <span>{label}</span>}
    </button>
  )
}

function ToolButton({
  title,
  onClick,
  children,
}: {
  title: string
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      onClick={onClick}
      className="grid h-7 w-7 place-items-center rounded text-secondary transition-colors hover:bg-elevated hover:text-foreground"
    >
      {children}
    </button>
  )
}

function cardClass(node: LayoutNode): string {
  switch (node.type) {
    case 'root':
      return 'border-amber-500/60 bg-surface shadow-lg dark:border-amber-300/40 dark:bg-[#111823] dark:shadow-[0_0_0_4px_rgba(215,176,106,0.04),0_16px_36px_rgba(0,0,0,0.34)]'
    case 'category':
      return 'border-border bg-surface hover:border-accent/50 hover:bg-elevated'
    case 'chain':
      return 'border-amber-500/50 bg-surface hover:border-amber-500/80 hover:bg-elevated dark:border-amber-300/30 dark:bg-[#121720] dark:hover:border-amber-300/60 dark:hover:bg-[#171d27]'
    default:
      if (node.kind === 'product') {
        return 'border-cyan-600/45 bg-surface hover:border-cyan-600/70 hover:bg-elevated dark:border-cyan-400/25 dark:bg-[#0f1720] dark:hover:border-cyan-400/55 dark:hover:bg-[#121d28]'
      }
      if (node.kind === 'application') {
        return 'border-violet-600/45 bg-surface hover:border-violet-600/70 hover:bg-elevated dark:border-violet-400/25 dark:bg-[#12111c] dark:hover:border-violet-400/55 dark:hover:bg-[#171525]'
      }
      return 'border-sky-600/45 bg-surface hover:border-sky-600/70 hover:bg-elevated dark:border-sky-400/25 dark:bg-[#0f151e] dark:hover:border-sky-400/55 dark:hover:bg-[#121b26]'
  }
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value))
}

function zoomAt(current: ViewState, px: number, py: number, factor: number): ViewState {
  const scale = clamp(current.scale * factor, 0.3, 2)
  const ratio = scale / current.scale
  return {
    scale,
    x: px - (px - current.x) * ratio,
    y: py - (py - current.y) * ratio,
  }
}

function curve(x1: number, y1: number, x2: number, y2: number): string {
  const dx = Math.max(24, (x2 - x1) * 0.48)
  return `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`
}
