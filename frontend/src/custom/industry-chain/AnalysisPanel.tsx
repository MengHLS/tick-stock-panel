import { AlertTriangle, BarChart3, Loader2, Plus, TrendingUp, X } from 'lucide-react'
import type {
  IndustryChainAnalysis,
  IndustryChainAnalysisStock,
  IndustryChainStockLink,
  IndustryChainWindowKey,
} from '@/lib/api'
import { fmtBigNum, fmtPct, priceColorClass } from '@/lib/format'
import { cn } from '@/lib/cn'
import { LINK_BASIS_LABELS } from './layout'

const WINDOW_LABELS: Record<IndustryChainWindowKey, string> = {
  d1: '最近交易日',
  d5: '近 5 日',
  d20: '近 20 日',
}

const WINDOW_ORDER: IndustryChainWindowKey[] = ['d1', 'd5', 'd20']

interface Props {
  title: string
  analysis: IndustryChainAnalysis | undefined
  loading: boolean
  error: string | null
  canAddStock: boolean
  embedded?: boolean
  onAddStock: () => void
  onClose: () => void
  onOpenLink: (link: IndustryChainStockLink) => void
}

export function AnalysisPanel({
  title,
  analysis,
  loading,
  error,
  canAddStock,
  embedded = false,
  onAddStock,
  onClose,
  onOpenLink,
}: Props) {
  return (
    <aside className={cn(
      'flex min-h-0 flex-col bg-surface/95 backdrop-blur dark:bg-[#0b1018]/97',
      embedded
        ? 'h-full w-full'
        : 'absolute inset-y-0 right-0 z-20 w-full max-w-[440px] border-l border-border shadow-2xl',
    )}>
      <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.16em] text-amber-600 dark:text-amber-300">
            <BarChart3 className="h-3 w-3" />
            CHAIN ANALYSIS
          </div>
          <h2 className="mt-0.5 truncate text-[16px] font-semibold text-foreground">{title}</h2>
          <p className="mt-0.5 truncate text-[10px] text-muted">
            {analysis
              ? `${analysis.chain.category_name} / ${analysis.chain.name}${analysis.node ? ` / ${analysis.node.path.map(item => item.name).join(' / ')}` : ''}`
              : '当前图谱成员口径'}
          </p>
        </div>
        <div className="flex items-center gap-1">
          {canAddStock && (
            <button
              type="button"
              onClick={onAddStock}
              className="inline-flex h-7 items-center gap-1 rounded border border-accent/30 bg-accent/10 px-2 text-[10px] text-accent hover:bg-accent/20"
              title="向当前节点添加股票"
            >
              <Plus className="h-3 w-3" />
              添加股票
            </button>
          )}
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭分析面板"
            className="grid h-7 w-7 place-items-center rounded text-muted hover:bg-elevated hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 pb-20">
        {loading && (
          <div className="grid h-48 place-items-center text-muted">
            <div className="flex items-center gap-2 text-[12px]">
              <Loader2 className="h-4 w-4 animate-spin" />
              计算产业链聚合
            </div>
          </div>
        )}
        {error && (
          <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-3 text-[11px] leading-5 text-danger">
            {error}
          </div>
        )}
        {analysis && !loading && (
          <div className="space-y-4">
            <div className="flex items-center justify-between rounded-lg border border-border bg-base/60 px-3 py-2 text-[10px] text-muted">
              <span>截至 {analysis.end}</span>
              <span>{analysis.stock_count} 只股票 · {analysis.link_count} 条关联</span>
            </div>

            <div className="grid grid-cols-3 gap-2">
              {WINDOW_ORDER.map(key => {
                const window = analysis.windows[key]
                return (
                  <div key={key} className="rounded-xl border border-border bg-base/55 p-2.5">
                    <div className="text-[9px] text-muted">{WINDOW_LABELS[key]}</div>
                    <div className={cn('mt-1 font-mono text-[18px] font-semibold tabular-nums', priceColorClass(window.return_pct))}>
                      {fmtPct(window.return_pct)}
                    </div>
                    <div className="mt-1 flex items-center justify-between text-[9px]">
                      <span className="text-bull">{window.up_count} 涨</span>
                      <span className="text-bear">{window.down_count} 跌</span>
                      <span className="text-muted">{window.priced_count}/{window.stock_count}</span>
                    </div>
                    <div className="mt-1.5 space-y-0.5 border-t border-border/60 pt-1.5 text-[9px] text-muted">
                      <div className="flex justify-between gap-1">
                        <span>父级</span>
                        <span className={priceColorClass(analysis.relative.parent.windows[key])}>
                          {fmtPct(analysis.relative.parent.windows[key])}
                        </span>
                      </div>
                      <div className="flex justify-between gap-1">
                        <span>整链</span>
                        <span className={priceColorClass(analysis.relative.chain.windows[key])}>
                          {fmtPct(analysis.relative.chain.windows[key])}
                        </span>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>

            <section className="rounded-xl border border-border bg-base/45 p-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5 text-[11px] font-medium text-foreground">
                  <TrendingUp className="h-3.5 w-3.5 text-accent" />
                  区间等权走势
                </div>
                <span className="font-mono text-[9px] text-muted">
                  {analysis.start} → {analysis.end}
                </span>
              </div>
              <Sparkline points={analysis.series} />
              <div className="mt-1 flex items-center justify-between text-[9px] text-muted">
                <span>起点 = {analysis.start} 首个交易日</span>
                <span>成交额 {fmtBigNum(analysis.windows.d1.amount)}</span>
              </div>
            </section>

            <section className="rounded-lg border border-border/70 bg-base/35 px-3 py-2 text-[10px] leading-4 text-muted">
              <div className="flex items-center justify-between">
                <span>口径</span>
                <span className="font-mono text-secondary">当前成员 · 等权 · 前复权</span>
              </div>
              <p className="mt-1">
                历史窗口使用当前图谱成员回看，不代表当时成分。节点范围包含全部子节点，同一股票按代码去重。
              </p>
            </section>

            {analysis.coverage.missing_count > 0 && (
              <div className="flex items-start gap-2 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-[10px] leading-4 text-warning">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>
                  {analysis.coverage.missing_count} 只股票缺少区间行情，已从收益聚合中剔除：
                  <span className="ml-1 font-mono">{analysis.coverage.missing_symbols.join('、')}</span>
                </span>
              </div>
            )}

            <section>
              <div className="mb-2 flex items-center justify-between">
                <h3 className="text-[12px] font-semibold text-foreground">成分股票</h3>
                <span className="text-[9px] text-muted">按最近交易日收益排序</span>
              </div>
              <div className="space-y-1.5">
                {analysis.stocks.length === 0 && (
                  <div className="rounded-lg border border-dashed border-border px-3 py-6 text-center text-[11px] text-muted">
                    当前节点还没有股票关联
                  </div>
                )}
                {analysis.stocks.map(stock => (
                  <StockRow key={stock.symbol} stock={stock} onOpenLink={onOpenLink} />
                ))}
              </div>
            </section>
          </div>
        )}
      </div>
    </aside>
  )
}

function StockRow({
  stock,
  onOpenLink,
}: {
  stock: IndustryChainAnalysisStock
  onOpenLink: (link: IndustryChainStockLink) => void
}) {
  const link = stock.links[0]
  return (
    <button
      type="button"
      onClick={() => link && onOpenLink(link)}
      className="w-full rounded-lg border border-border/70 bg-base/35 px-2.5 py-2 text-left transition-colors hover:border-accent/35 hover:bg-elevated/40"
    >
      <div className="flex items-center gap-2">
        <span className="min-w-0 flex-1 truncate text-[12px] font-medium text-foreground">
          {stock.name}
        </span>
        {stock.name !== stock.symbol && (
          <span className="shrink-0 font-mono text-[9px] text-muted">{stock.symbol}</span>
        )}
        <span className={cn('w-14 shrink-0 text-right font-mono text-[11px] tabular-nums', priceColorClass(stock.returns.d1))}>
          {fmtPct(stock.returns.d1)}
        </span>
      </div>
      <div className="mt-1 flex items-center gap-1.5">
        <span className="min-w-0 flex-1 truncate text-[10px] text-secondary">
          {link?.reason_short ?? '未填写关联理由'}
        </span>
        {stock.links.length > 1 && (
          <span className="shrink-0 rounded bg-elevated px-1 py-0.5 text-[8px] text-muted">
            {stock.links.length} 处关联
          </span>
        )}
      </div>
      <div className="mt-1 flex items-center gap-3 text-[9px] text-muted">
        <span className={priceColorClass(stock.returns.d5)}>5日 {fmtPct(stock.returns.d5)}</span>
        <span className={priceColorClass(stock.returns.d20)}>20日 {fmtPct(stock.returns.d20)}</span>
        {stock.missing_price && <span className="text-warning">缺行情</span>}
        {link && (
          <span className="ml-auto">
            {LINK_BASIS_LABELS[link.basis]} · {link.evidence_status === 'verified' ? '已核验' : '待核验'}
          </span>
        )}
      </div>
    </button>
  )
}

function Sparkline({ points }: { points: Array<{ date: string; return_pct: number }> }) {
  if (points.length < 2) {
    return (
      <div className="mt-2 grid h-16 place-items-center rounded-lg border border-dashed border-border/60 text-[10px] text-muted">
        区间行情不足，暂无法绘制
      </div>
    )
  }
  const width = 360
  const height = 64
  const values = points.map(point => point.return_pct)
  const min = Math.min(...values, 0)
  const max = Math.max(...values, 0)
  const span = max - min || 1
  const x = (index: number) => (index / (points.length - 1)) * width
  const y = (value: number) => height - ((value - min) / span) * height
  const line = points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${x(index).toFixed(1)} ${y(point.return_pct).toFixed(1)}`).join(' ')
  const area = `${line} L ${width} ${height} L 0 ${height} Z`
  const last = values[values.length - 1]
  const color = last >= 0 ? '#F04438' : '#12B76A'
  const zeroY = y(0)
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="mt-2 h-16 w-full" preserveAspectRatio="none" aria-hidden="true">
      <path d={area} fill={color} opacity="0.08" />
      {min < 0 && max > 0 && (
        <line x1="0" x2={width} y1={zeroY} y2={zeroY} stroke="currentColor" className="text-border" strokeDasharray="3 4" />
      )}
      <path d={line} fill="none" stroke={color} strokeWidth="1.6" vectorEffect="non-scaling-stroke" />
    </svg>
  )
}
