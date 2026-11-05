import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Activity,
  AlertTriangle,
  CalendarRange,
  Check,
  ChevronDown,
  ChevronUp,
  Clock3,
  Crown,
  Layers3,
  Loader2,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Tags,
  Trash2,
  TrendingUp,
  X,
} from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { EmptyState } from '@/components/EmptyState'
import { Modal } from '@/components/Modal'
import { DatePicker } from '@/components/DatePicker'
import { StockPreviewDialog } from '@/components/StockPreviewDialog'
import { toast } from '@/components/Toast'
import {
  api,
  type ThemeAnalyzerAnalysis,
  type ThemeAnalyzerLeader,
  type ThemeAnalyzerMinute,
  type ThemeAnalyzerTheme,
  type ThemeIndustrySource,
} from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { cn } from '@/lib/cn'
import { fmtPct, priceColorClass } from '@/lib/format'
import { MinuteSmallMultiples, ThemeTrendChart } from './charts'
import { LimitRouteMap } from './LimitRouteMap'
import { IndustrySourcePicker } from './IndustrySourcePicker'

const THEME_COLORS = ['#F59E0B', '#22D3EE', '#FB7185', '#A78BFA', '#A3E635', '#60A5FA']
const MINUTE_COLORS = ['#F59E0B', '#22D3EE', '#A78BFA', '#FB7185', '#A3E635']
const MAX_MINUTE_STOCKS = 5
const SELECTED_THEME_KEY = 'tf-theme-analyzer-selected'

type ThemeEditorPayload = {
  name: string
  description: string
  color: string
  industry_source: ThemeIndustrySource | null
}

function loadSelectedTheme() {
  try {
    return localStorage.getItem(SELECTED_THEME_KEY) ?? ''
  } catch {
    return ''
  }
}

function saveSelectedTheme(themeId: string) {
  try {
    if (themeId) localStorage.setItem(SELECTED_THEME_KEY, themeId)
    else localStorage.removeItem(SELECTED_THEME_KEY)
  } catch {
    // 本地选择仅用于体验，不影响服务端主题数据
  }
}

function shortDate(value: string | null | undefined) {
  return value ? value.slice(5) : '—'
}

function errorText(error: unknown) {
  return error instanceof Error ? error.message : '请求失败'
}

function leaderMap(leaders: ThemeAnalyzerLeader[] | undefined) {
  return new Map((leaders ?? []).map(leader => [leader.symbol, leader]))
}

function StatCard({
  label,
  value,
  hint,
  icon: Icon,
  tone = 'neutral',
}: {
  label: string
  value: ReactNode
  hint?: ReactNode
  icon: typeof Activity
  tone?: 'neutral' | 'up' | 'down' | 'accent'
}) {
  const toneClass = tone === 'up'
    ? 'text-bull'
    : tone === 'down'
      ? 'text-bear'
      : tone === 'accent'
        ? 'text-accent'
        : 'text-foreground'
  return (
    <div className="rounded-card border border-border/80 bg-surface/90 p-3.5">
      <div className="flex items-center justify-between gap-2 text-[10px] text-muted">
        <span>{label}</span>
        <Icon size={14} strokeWidth={1.8} />
      </div>
      <div className={cn('mt-2 font-mono text-xl font-semibold tabular-nums', toneClass)}>{value}</div>
      {hint && <div className="mt-1 truncate text-[10px] text-muted">{hint}</div>}
    </div>
  )
}

function SectionCard({
  title,
  hint,
  action,
  children,
  className,
}: {
  title: string
  hint?: ReactNode
  action?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={cn('overflow-hidden rounded-2xl border border-border bg-surface/92', className)}>
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-border/70 px-4 py-3">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-foreground">{title}</h2>
          {hint && <p className="mt-0.5 text-[10px] leading-4 text-muted">{hint}</p>}
        </div>
        {action}
      </header>
      {children}
    </section>
  )
}

function ThemeRail({
  themes,
  selectedId,
  loading,
  onSelect,
  onCreate,
  onEdit,
  onDelete,
}: {
  themes: ThemeAnalyzerTheme[]
  selectedId: string
  loading: boolean
  onSelect: (id: string) => void
  onCreate: () => void
  onEdit: (theme: ThemeAnalyzerTheme) => void
  onDelete: (theme: ThemeAnalyzerTheme) => void
}) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between border-b border-border px-3.5 py-3">
        <div className="flex items-center gap-2">
          <Tags size={15} className="text-accent" />
          <span className="text-xs font-semibold text-foreground">主题库</span>
          <span className="rounded-full bg-elevated px-1.5 py-0.5 font-mono text-[9px] text-muted">{themes.length}</span>
        </div>
        <button
          type="button"
          onClick={onCreate}
          className="inline-flex items-center gap-1 rounded-btn border border-accent/35 bg-accent/10 px-2 py-1 text-[10px] font-medium text-accent hover:bg-accent/20"
        >
          <Plus size={12} /> 新建
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {loading ? (
          <div className="flex items-center justify-center gap-2 py-10 text-xs text-muted">
            <Loader2 size={14} className="animate-spin" /> 加载主题
          </div>
        ) : themes.length === 0 ? (
          <div className="px-3 py-10 text-center">
            <Tags size={26} className="mx-auto text-muted/60" strokeWidth={1.4} />
            <p className="mt-3 text-xs text-secondary">还没有主题</p>
          </div>
        ) : themes.map(theme => {
          const selected = theme.id === selectedId
          return (
            <div
              key={theme.id}
              className={cn(
                'group mb-1.5 rounded-xl border px-2.5 py-2.5 transition-colors',
                selected
                  ? 'border-accent/35 bg-accent/10'
                  : 'border-transparent bg-transparent hover:border-border hover:bg-elevated/55',
              )}
            >
              <button type="button" onClick={() => onSelect(theme.id)} className="flex w-full min-w-0 items-start gap-2.5 text-left">
                <span className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: theme.color }} />
                <span className="min-w-0 flex-1">
                  <span className="flex items-center justify-between gap-2">
                    <span className={cn('truncate text-xs font-medium', selected ? 'text-foreground' : 'text-secondary')}>{theme.name}</span>
                    <span className="shrink-0 font-mono text-[9px] text-muted">{theme.symbols.length}</span>
                  </span>
                  <span className="mt-1 line-clamp-2 text-[10px] leading-4 text-muted">{theme.description || '未填写说明'}</span>
                </span>
              </button>
              <div className={cn('mt-2 flex justify-end gap-1', selected ? 'opacity-100' : 'opacity-0 group-hover:opacity-100')}>
                <button
                  type="button"
                  onClick={() => onEdit(theme)}
                  className="rounded p-1 text-muted hover:bg-surface hover:text-foreground"
                  aria-label={`编辑 ${theme.name}`}
                >
                  <Pencil size={12} />
                </button>
                <button
                  type="button"
                  onClick={() => onDelete(theme)}
                  className="rounded p-1 text-muted hover:bg-surface hover:text-danger"
                  aria-label={`删除 ${theme.name}`}
                >
                  <Trash2 size={12} />
                </button>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function ThemeEditorDialog({
  open,
  theme,
  busy,
  onClose,
  onSave,
}: {
  open: boolean
  theme: ThemeAnalyzerTheme | null
  busy: boolean
  onClose: () => void
  onSave: (payload: ThemeEditorPayload) => void
}) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [color, setColor] = useState(THEME_COLORS[0])
  const [industrySource, setIndustrySource] = useState<ThemeIndustrySource | null>(null)

  useEffect(() => {
    if (!open) return
    setName(theme?.name ?? '')
    setDescription(theme?.description ?? '')
    setColor(theme?.color ?? THEME_COLORS[0])
    setIndustrySource(theme?.industry_source?.chain_id ? {
      chain_id: theme.industry_source.chain_id,
      node_ids: theme.industry_source.node_ids ?? [],
    } : null)
  }, [open, theme])

  if (!open) return null
  return (
    <Modal
      labelledBy="theme-editor-title"
      onClose={onClose}
      panelClassName="max-h-[90vh] w-[92vw] max-w-lg overflow-y-auto rounded-card border border-border bg-surface shadow-2xl"
    >
      <form
        onSubmit={event => {
          event.preventDefault()
          if (!name.trim() || busy) return
          onSave({ name: name.trim(), description: description.trim(), color, industry_source: industrySource })
        }}
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <div>
            <h2 id="theme-editor-title" className="text-base font-semibold text-foreground">
              {theme ? '编辑主题' : '新建主题'}
            </h2>
            <p className="mt-1 text-[11px] text-muted">选择自建股票池或关联产业链环节。</p>
          </div>
          <button type="button" onClick={onClose} className="rounded p-1.5 text-muted hover:bg-elevated hover:text-foreground" aria-label="关闭">
            <X size={16} />
          </button>
        </div>
        <div className="space-y-4 px-5 py-4">
          <label className="block">
            <span className="mb-1.5 block text-xs font-medium text-secondary">主题名称</span>
            <input
              autoFocus
              value={name}
              onChange={event => setName(event.target.value)}
              maxLength={40}
              placeholder="例如：AI 算力"
              className="h-9 w-full rounded-btn border border-border bg-base px-3 text-sm text-foreground outline-none focus:border-accent/60"
            />
          </label>
          <label className="block">
            <span className="mb-1.5 block text-xs font-medium text-secondary">说明</span>
            <textarea
              value={description}
              onChange={event => setDescription(event.target.value)}
              maxLength={300}
              rows={3}
              placeholder="记录主题来源或观察线索"
              className="w-full resize-none rounded-btn border border-border bg-base px-3 py-2 text-sm leading-5 text-foreground outline-none focus:border-accent/60"
            />
          </label>
          <IndustrySourcePicker open={open} value={industrySource} onChange={setIndustrySource} />
          <div>
            <span className="mb-2 block text-xs font-medium text-secondary">标记色</span>
            <div className="flex flex-wrap items-center gap-2">
              {THEME_COLORS.map(item => (
                <button
                  key={item}
                  type="button"
                  onClick={() => setColor(item)}
                  className={cn(
                    'h-7 w-7 rounded-full border-2 transition-transform',
                    color === item ? 'scale-110 border-foreground' : 'border-transparent hover:scale-105',
                  )}
                  style={{ backgroundColor: item }}
                  aria-label={`选择颜色 ${item}`}
                />
              ))}
              <input
                type="color"
                value={color}
                onChange={event => setColor(event.target.value.toUpperCase())}
                className="h-8 w-9 cursor-pointer rounded border border-border bg-base p-0.5"
                aria-label="自定义颜色"
              />
            </div>
          </div>
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-border px-5 py-3">
          <button type="button" onClick={onClose} className="rounded-btn px-3 py-1.5 text-xs text-secondary hover:bg-elevated hover:text-foreground">
            取消
          </button>
          <button
            type="submit"
            disabled={!name.trim() || busy}
            className="inline-flex items-center gap-1.5 rounded-btn bg-accent px-3 py-1.5 text-xs font-medium text-white hover:bg-accent/90 disabled:opacity-40"
          >
            {busy ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />}
            {theme ? '保存修改' : '创建主题'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

function StockSearchBox({
  symbols,
  busy,
  onAdd,
}: {
  symbols: string[]
  busy: boolean
  onAdd: (symbol: string) => void
}) {
  const [query, setQuery] = useState('')
  const [debounced, setDebounced] = useState('')

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(query.trim()), 220)
    return () => window.clearTimeout(timer)
  }, [query])

  const search = useQuery({
    queryKey: QK.instrumentSearch(debounced, 'stock'),
    queryFn: () => api.instrumentSearch(debounced, 20, 'stock'),
    enabled: debounced.length > 0,
    staleTime: 30_000,
  })
  const existing = useMemo(() => new Set(symbols), [symbols])
  const results = (search.data?.results ?? []).filter(item => !existing.has(item.symbol))

  return (
    <div className="relative min-w-[220px] flex-1">
      <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
      <input
        value={query}
        onChange={event => setQuery(event.target.value)}
        placeholder="搜索代码 / 名称 / 拼音"
        className="h-9 w-full rounded-btn border border-border bg-base/80 pl-9 pr-8 text-xs text-foreground outline-none placeholder:text-muted/60 focus:border-accent/60"
        autoComplete="off"
      />
      {query && (
        <button
          type="button"
          onClick={() => setQuery('')}
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted hover:text-foreground"
          aria-label="清空搜索"
        >
          <X size={12} />
        </button>
      )}
      {debounced && (
        <div className="absolute left-0 right-0 top-[calc(100%+6px)] z-30 max-h-72 overflow-y-auto rounded-xl border border-border bg-surface p-1.5 shadow-2xl">
          {search.isLoading ? (
            <div className="flex items-center justify-center gap-2 py-4 text-[11px] text-muted">
              <Loader2 size={13} className="animate-spin" /> 搜索中
            </div>
          ) : results.length === 0 ? (
            <div className="px-3 py-4 text-center text-[11px] text-muted">
              {search.data?.results?.length ? '搜索结果已全部在股票池中' : '没有找到股票'}
            </div>
          ) : results.map(item => (
            <button
              key={item.symbol}
              type="button"
              disabled={busy}
              onMouseDown={event => event.preventDefault()}
              onClick={() => {
                onAdd(item.symbol)
                setQuery('')
              }}
              className="flex w-full items-center justify-between gap-3 rounded-lg px-2.5 py-2 text-left hover:bg-elevated disabled:opacity-50"
            >
              <span className="min-w-0">
                <span className="block truncate text-xs text-foreground">{item.name}</span>
                <span className="mt-0.5 block font-mono text-[9px] text-muted">{item.symbol}</span>
              </span>
              <Plus size={13} className="shrink-0 text-accent" />
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function StockPoolDialog({
  open,
  theme,
  analysis,
  busy,
  onClose,
  onSave,
}: {
  open: boolean
  theme: ThemeAnalyzerTheme | null
  analysis: ThemeAnalyzerAnalysis | undefined
  busy: boolean
  onClose: () => void
  onSave: (add: string[], remove: string[]) => void
}) {
  const [draft, setDraft] = useState<string[]>([])
  useEffect(() => {
    if (open && theme) setDraft(theme.symbols)
  }, [open, theme])

  if (!open || !theme) return null
  const stats = leaderMap(analysis?.leaders)
  const existing = new Set(theme.symbols)
  const restored = (theme.excluded_symbols ?? []).filter(symbol => !draft.includes(symbol))
  const add = draft.filter(symbol => !existing.has(symbol))
  const remove = theme.symbols.filter(symbol => !draft.includes(symbol))

  return (
    <Modal
      labelledBy="stock-pool-title"
      onClose={onClose}
      panelClassName="flex max-h-[88vh] w-[94vw] max-w-4xl flex-col rounded-card border border-border bg-surface shadow-2xl"
    >
      <div className="flex items-center justify-between border-b border-border px-5 py-4">
        <div>
          <h2 id="stock-pool-title" className="text-base font-semibold text-foreground">管理股票池</h2>
          <p className="mt-1 text-[11px] text-muted">
            {theme.name} · {theme.symbols.length} 只 · 保存后重算分析
          </p>
        </div>
        <button type="button" onClick={onClose} className="rounded p-1.5 text-muted hover:bg-elevated hover:text-foreground" aria-label="关闭">
          <X size={16} />
        </button>
      </div>
      <div className="border-b border-border px-5 py-3">
        <StockSearchBox
          symbols={draft}
          busy={busy}
          onAdd={symbol => setDraft(current => current.includes(symbol) ? current : [...current, symbol])}
        />
        {restored.length > 0 && (
          <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px] text-muted">
            已排除：
            {restored.map(symbol => (
              <button
                key={symbol}
                type="button"
                onClick={() => setDraft(current => [...current, symbol])}
                className="rounded border border-border px-2 py-1 text-accent"
              >
                恢复 {stats.get(symbol)?.name ?? symbol}
              </button>
            ))}
          </div>
        )}
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        {draft.length === 0 ? (
          <EmptyState icon={Plus} title="股票池为空" hint="搜索股票并加入后即可生成分析。" />
        ) : (
          <table className="w-full min-w-[720px] border-collapse text-xs">
            <thead className="sticky top-0 z-10 bg-surface text-[10px] text-muted">
              <tr className="border-b border-border">
                <th className="px-5 py-2 text-left font-medium">股票</th>
                <th className="px-3 py-2 text-left font-medium">来源</th>
                <th className="px-3 py-2 text-right font-medium">30日最大</th>
                <th className="px-3 py-2 text-right font-medium">当前3日</th>
                <th className="px-5 py-2 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {draft.map(symbol => {
                const stat = stats.get(symbol)
                return (
                  <tr key={symbol} className="border-b border-border/50 last:border-0">
                    <td className="px-5 py-2.5">
                      <div className="font-medium text-foreground">{stat?.name ?? symbol}</div>
                      <div className="mt-0.5 font-mono text-[9px] text-muted">{symbol}</div>
                    </td>
                    <td className="px-3 py-2.5 text-[10px] text-muted">
                      {theme.stock_segments?.[symbol]?.join(' / ') || '手动添加'}
                    </td>
                    <td className={cn('px-3 py-2.5 text-right font-mono tabular-nums', priceColorClass(stat?.max_ret_30))}>
                      {fmtPct(stat?.max_ret_30, 1)}
                    </td>
                    <td className={cn('px-3 py-2.5 text-right font-mono tabular-nums', priceColorClass(stat?.latest_ret_3))}>
                      {fmtPct(stat?.latest_ret_3, 1)}
                    </td>
                    <td className="px-5 py-2.5 text-right">
                      <button
                        type="button"
                        onClick={() => setDraft(current => current.filter(item => item !== symbol))}
                        className="rounded p-1.5 text-muted hover:bg-danger/10 hover:text-danger"
                        aria-label={`移除 ${symbol}`}
                      >
                        <Trash2 size={13} />
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
      <div className="flex items-center justify-between border-t border-border px-5 py-3">
        <span className="text-[10px] text-muted">
          {draft.length} 只 · 新增 {add.length} · 移除 {remove.length}
        </span>
        <div className="flex items-center gap-2">
          <button type="button" onClick={onClose} className="rounded-btn px-3 py-1.5 text-xs text-secondary hover:bg-elevated">
            取消
          </button>
          <button
            type="button"
            disabled={busy || (add.length === 0 && remove.length === 0)}
            onClick={() => onSave(add, remove)}
            className="inline-flex items-center gap-1.5 rounded-btn bg-accent px-3 py-1.5 text-xs font-medium text-white hover:bg-accent/90 disabled:opacity-40"
          >
            {busy ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />}
            保存
          </button>
        </div>
      </div>
    </Modal>
  )
}

function CoreStockCards({
  analysis,
  onSelect,
}: {
  analysis: ThemeAnalyzerAnalysis
  onSelect: (symbol: string, name: string) => void
}) {
  const leaders = leaderMap(analysis.leaders)
  return (
    <SectionCard
      title="核心股"
      hint="按区间涨幅峰值、连板高度、涨停次数排序；使用区间结束后的完整数据，仅作复盘"
      action={<span className="text-[10px] text-muted">默认展示前 {Math.min(5, analysis.core_stocks.length)} 只</span>}
    >
      <div className="grid gap-2 p-3 md:grid-cols-2 xl:grid-cols-5">
        {analysis.core_stocks.map((stock, index) => {
          const leader = leaders.get(stock.symbol)
          return (
            <button
              key={stock.symbol}
              type="button"
              onClick={() => onSelect(stock.symbol, stock.name)}
              className="rounded-xl border border-border/70 bg-base/45 p-3 text-left transition-colors hover:border-accent/40 hover:bg-elevated/45"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="font-mono text-[9px] text-accent">#{index + 1}</span>
                    <span className="truncate text-xs font-semibold text-foreground">{stock.name}</span>
                  </div>
                  <div className="mt-0.5 font-mono text-[9px] text-muted">{stock.symbol} · {stock.board}</div>
                </div>
                {index === 0 && <Crown size={13} className="shrink-0 text-amber-400" />}
              </div>
              <div className={cn('mt-2 font-mono text-base font-semibold tabular-nums', priceColorClass(leader?.max_ret_30))}>
                {fmtPct(leader?.max_ret_30, 1)}
              </div>
              <div className="mt-1 text-[9px] text-muted">30日最大</div>
              <div className="mt-2 flex flex-wrap gap-1">
                {stock.reasons.map(reason => (
                  <span key={reason} className="rounded bg-elevated px-1.5 py-0.5 text-[9px] text-secondary">{reason}</span>
                ))}
              </div>
            </button>
          )
        })}
        {analysis.core_stocks.length === 0 && (
          <div className="col-span-full py-8 text-center text-xs text-muted">窗口内没有可展示的核心股</div>
        )}
      </div>
    </SectionCard>
  )
}

function LeaderTable({
  analysis,
  onSelect,
}: {
  analysis: ThemeAnalyzerAnalysis
  onSelect: (symbol: string, name: string) => void
}) {
  const [showAll, setShowAll] = useState(false)
  const coreSymbols = useMemo(
    () => new Set(analysis.core_stocks.map(stock => stock.symbol)),
    [analysis.core_stocks],
  )
  const rows = showAll
    ? analysis.leaders
    : analysis.leaders.filter(leader => coreSymbols.has(leader.symbol))
  const visible = rows.length ? rows : analysis.leaders.slice(0, 5)

  return (
    <SectionCard
      title="股票列表"
      hint={`${analysis.candidate_count} 只候选 · ${analysis.filtered_count} 只因主板筛选隐藏 · ${analysis.quoted_count} 只有行情`}
      action={(
        <button
          type="button"
          onClick={() => setShowAll(value => !value)}
          className="inline-flex items-center gap-1 rounded-btn border border-border px-2.5 py-1 text-[10px] text-secondary hover:text-foreground"
        >
          {showAll ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          {showAll ? '只看核心股' : `查看全部 ${analysis.leaders.length} 只`}
        </button>
      )}
    >
      <div className="max-h-[560px] overflow-auto">
        <table className="w-full min-w-[760px] border-collapse text-xs">
          <thead className="sticky top-0 z-10 bg-surface text-[10px] text-muted">
            <tr className="border-b border-border">
              <th className="px-4 py-2.5 text-left font-medium">股票</th>
              <th className="px-3 py-2.5 text-right font-medium">30日最大</th>
              <th className="px-3 py-2.5 text-right font-medium">10日最大</th>
              <th className="px-3 py-2.5 text-right font-medium">3日最大</th>
              <th className="px-3 py-2.5 text-right font-medium">当前3日</th>
              <th className="px-3 py-2.5 text-right font-medium">涨停事件</th>
              <th className="px-4 py-2.5 text-right font-medium">最新价</th>
            </tr>
          </thead>
          <tbody>
            {visible.map(leader => (
              <tr
                key={leader.symbol}
                tabIndex={0}
                onClick={() => onSelect(leader.symbol, leader.name)}
                onKeyDown={event => {
                  if (event.key === 'Enter' || event.key === ' ') onSelect(leader.symbol, leader.name)
                }}
                className="cursor-pointer border-b border-border/50 transition-colors last:border-0 hover:bg-elevated/40 focus:bg-elevated/50 focus:outline-none"
              >
                <td className="px-4 py-2.5">
                  <div className="flex items-center gap-2">
                    <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', leader.active ? 'bg-amber-400' : 'bg-border')} />
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className="max-w-32 truncate font-medium text-foreground">{leader.name}</span>
                        {coreSymbols.has(leader.symbol) && <span className="rounded bg-accent/10 px-1 py-0.5 text-[8px] text-accent">核心</span>}
                        <span className="text-[9px] text-muted">{leader.board}</span>
                      </div>
                      <div className="mt-0.5 font-mono text-[9px] text-muted">{leader.symbol}</div>
                    </div>
                  </div>
                </td>
                <td className="px-3 py-2.5 text-right">
                  <div className={cn('font-mono font-medium tabular-nums', priceColorClass(leader.max_ret_30))}>{fmtPct(leader.max_ret_30, 1)}</div>
                  <div className="mt-0.5 text-[9px] text-muted">{shortDate(leader.max_ret_30_date)}</div>
                </td>
                <td className="px-3 py-2.5 text-right">
                  <div className={cn('font-mono tabular-nums', priceColorClass(leader.max_ret_10))}>{fmtPct(leader.max_ret_10, 1)}</div>
                  <div className="mt-0.5 text-[9px] text-muted">{shortDate(leader.max_ret_10_date)}</div>
                </td>
                <td className="px-3 py-2.5 text-right">
                  <div className={cn('font-mono tabular-nums', priceColorClass(leader.max_ret_3))}>{fmtPct(leader.max_ret_3, 1)}</div>
                  <div className="mt-0.5 text-[9px] text-muted">{shortDate(leader.max_ret_3_date)}</div>
                </td>
                <td className={cn('px-3 py-2.5 text-right font-mono tabular-nums', priceColorClass(leader.latest_ret_3))}>
                  {fmtPct(leader.latest_ret_3, 1)}
                </td>
                <td className="px-3 py-2.5 text-right font-mono text-secondary">{leader.event_count || '—'}</td>
                <td className="px-4 py-2.5 text-right font-mono text-secondary">{leader.last_close?.toFixed(2) ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SectionCard>
  )
}

function minuteReason(
  analysis: ThemeAnalyzerAnalysis,
  day: string,
  symbol: string,
  coreSymbols: Set<string>,
) {
  const switchDay = analysis.limit_route.switch_days.find(item => item.date === day)
  if (!switchDay) return coreSymbols.has(symbol) ? '区间核心股' : '当日活跃'
  if (switchDay.daily_leader === symbol) return '当日领涨'
  if (switchDay.new_starters.some(item => item.symbol === symbol)) return '当日首次封板'
  const sealed = switchDay.sealed.find(item => item.symbol === symbol)
  if (sealed?.catch_up) return '峰值后补涨首封'
  if (sealed?.relay) return '峰值后接力封板'
  if (switchDay.broken.some(item => item.symbol === symbol)) return '当日炸板'
  if (coreSymbols.has(symbol)) return '区间核心股'
  return '当日活跃'
}

function MinuteLab({
  analysis,
  minuteDate,
  onDateChange,
  selectedSymbols,
  onToggleSymbol,
  minute,
  loading,
  error,
  onRetry,
}: {
  analysis: ThemeAnalyzerAnalysis
  minuteDate: string
  onDateChange: (date: string) => void
  selectedSymbols: string[]
  onToggleSymbol: (symbol: string) => void
  minute: ThemeAnalyzerMinute | undefined
  loading: boolean
  error: unknown
  onRetry: () => void
}) {
  const leaders = leaderMap(analysis.leaders)
  const coreSymbols = useMemo(
    () => new Set(analysis.core_stocks.map(stock => stock.symbol)),
    [analysis.core_stocks],
  )
  const switchDay = analysis.limit_route.switch_days.find(item => item.date === minuteDate)
  const candidates = Array.from(new Set([
    ...(switchDay?.minute_symbols ?? []),
    ...analysis.core_stocks.map(stock => stock.symbol),
  ])).filter(symbol => leaders.has(symbol)).slice(0, 8)
  const colors = Object.fromEntries(candidates.map((symbol, index) => [symbol, MINUTE_COLORS[index % MINUTE_COLORS.length]]))

  return (
    <SectionCard
      title="关键日复盘"
      hint="分钟 K 相对前一交易日收盘；最多同时查看 5 只代表股"
      action={(
        <DatePicker
          value={minuteDate}
          onChange={onDateChange}
          min={analysis.window_start}
          max={analysis.window_end}
          buttonClassName="h-8 text-[10px]"
          placeholder="选择日期"
        />
      )}
    >
      <div className="space-y-3 p-3">
        <div className="rounded-xl border border-border/70 bg-base/40 px-3 py-2">
          <div className="flex flex-wrap items-center gap-2 text-[11px]">
            <CalendarRange size={13} className="text-accent" />
            <span className="font-medium text-foreground">{minuteDate || '未选择日期'}</span>
            {switchDay && <span className="rounded bg-accent/10 px-1.5 py-0.5 text-[9px] text-accent">{switchDay.label}</span>}
          </div>
          {switchDay?.reason && <p className="mt-1 text-[10px] leading-4 text-secondary">{switchDay.reason}</p>}
          {!switchDay && <p className="mt-1 text-[10px] text-muted">该日没有自动识别的涨停切换事件，可继续查看核心股分时。</p>}
          <div className="mt-2 flex flex-wrap gap-1.5">
            {analysis.limit_route.switch_days.slice(-4).map(day => (
              <button
                key={day.date}
                type="button"
                onClick={() => onDateChange(day.date)}
                className={cn(
                  'rounded border px-2 py-1 text-[9px]',
                  day.date === minuteDate ? 'border-accent/40 bg-accent/10 text-accent' : 'border-border text-muted hover:text-foreground',
                )}
              >
                {shortDate(day.date)} · {day.label}
              </button>
            ))}
          </div>
        </div>

        {candidates.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {candidates.map(symbol => {
              const selected = selectedSymbols.includes(symbol)
              return (
                <button
                  key={symbol}
                  type="button"
                  onClick={() => onToggleSymbol(symbol)}
                  title={minuteReason(analysis, minuteDate, symbol, coreSymbols)}
                  className={cn(
                    'inline-flex items-center gap-1.5 rounded-full border px-2 py-1 text-[10px]',
                    selected ? 'border-accent/40 bg-accent/10 text-foreground' : 'border-border text-muted hover:text-foreground',
                  )}
                >
                  <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: colors[symbol] }} />
                  {leaders.get(symbol)?.name ?? symbol}
                  <span className="text-[9px] text-muted">{minuteReason(analysis, minuteDate, symbol, coreSymbols)}</span>
                </button>
              )
            })}
          </div>
        )}

        {loading ? (
          <div className="flex h-40 items-center justify-center gap-2 text-xs text-muted">
            <Loader2 size={15} className="animate-spin" /> 加载分钟数据
          </div>
        ) : error ? (
          <div className="flex items-center justify-between gap-3 rounded-xl border border-danger/30 bg-danger/5 px-3 py-3 text-xs text-danger">
            <span>{errorText(error)}</span>
            <button type="button" onClick={onRetry} className="inline-flex items-center gap-1 rounded border border-danger/30 px-2 py-1">
              <RefreshCw size={11} /> 重试
            </button>
          </div>
        ) : !minute || minute.status !== 'ok' || minute.stocks.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border px-3 py-10 text-center text-xs text-muted">
            {minute?.missing?.length ? `缺少分钟数据：${minute.missing.join('、')}` : '该日没有分钟数据'}
          </div>
        ) : (
          <>
            <MinuteSmallMultiples minute={minute} colors={colors} />
            {minute.missing.length > 0 && (
              <p className="text-[10px] text-warning">缺少分钟数据：{minute.missing.join('、')}</p>
            )}
            <div className="overflow-x-auto">
              <table className="w-full min-w-[600px] text-[10px]">
                <thead className="text-muted">
                  <tr className="border-b border-border">
                    <th className="px-2 py-1.5 text-left font-medium">股票</th>
                    <th className="px-2 py-1.5 text-right font-medium">全天</th>
                    <th className="px-2 py-1.5 text-right font-medium">开盘30分</th>
                    <th className="px-2 py-1.5 text-right font-medium">上午</th>
                    <th className="px-2 py-1.5 text-right font-medium">下午</th>
                    <th className="px-2 py-1.5 text-right font-medium">尾盘30分</th>
                    <th className="px-2 py-1.5 text-right font-medium">最大回撤</th>
                  </tr>
                </thead>
                <tbody>
                  {minute.stocks.map(stock => {
                    const feature = minute.features[stock.symbol]
                    return (
                      <tr key={stock.symbol} className="border-b border-border/40 last:border-0">
                        <td className="px-2 py-1.5 text-foreground">{stock.name}</td>
                        <td className={cn('px-2 py-1.5 text-right font-mono', priceColorClass(feature?.day))}>{fmtPct(feature?.day, 2)}</td>
                        <td className={cn('px-2 py-1.5 text-right font-mono', priceColorClass(feature?.open30))}>{fmtPct(feature?.open30, 2)}</td>
                        <td className={cn('px-2 py-1.5 text-right font-mono', priceColorClass(feature?.am))}>{fmtPct(feature?.am, 2)}</td>
                        <td className={cn('px-2 py-1.5 text-right font-mono', priceColorClass(feature?.pm))}>{fmtPct(feature?.pm, 2)}</td>
                        <td className={cn('px-2 py-1.5 text-right font-mono', priceColorClass(feature?.tail30))}>{fmtPct(feature?.tail30, 2)}</td>
                        <td className="px-2 py-1.5 text-right font-mono text-bear">{fmtPct(feature?.max_dd, 2)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </SectionCard>
  )
}

export function ThemeAnalyzerPage() {
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState(loadSelectedTheme)
  const [editorOpen, setEditorOpen] = useState(false)
  const [editingTheme, setEditingTheme] = useState<ThemeAnalyzerTheme | null>(null)
  const [poolOpen, setPoolOpen] = useState(false)
  const [rangeStart, setRangeStart] = useState('')
  const [rangeEnd, setRangeEnd] = useState('')
  const [mainboardOnly, setMainboardOnly] = useState(true)
  const [minuteDate, setMinuteDate] = useState('')
  const [minuteSymbols, setMinuteSymbols] = useState<string[]>([])
  const [previewSymbol, setPreviewSymbol] = useState<string | null>(null)
  const [previewName, setPreviewName] = useState('')
  const lastMinuteContext = useRef('')

  const themesQuery = useQuery({
    queryKey: QK.themeAnalyzerThemes,
    queryFn: api.themeAnalyzerThemes,
    staleTime: 30_000,
  })
  const themes = themesQuery.data?.items ?? []
  const selectedTheme = themes.find(theme => theme.id === selectedId) ?? null
  const poolKey = JSON.stringify([selectedTheme?.symbols ?? [], selectedTheme?.industry_source, selectedTheme?.source_error])

  useEffect(() => {
    if (themesQuery.isLoading) return
    if (themes.length === 0) {
      if (selectedId) setSelectedId('')
      return
    }
    if (!themes.some(theme => theme.id === selectedId)) setSelectedId(themes[0].id)
  }, [selectedId, themes, themesQuery.isLoading])

  useEffect(() => {
    saveSelectedTheme(selectedId)
    setRangeStart('')
    setRangeEnd('')
    setMinuteDate('')
    setMinuteSymbols([])
    lastMinuteContext.current = ''
  }, [selectedId])

  const analysisQuery = useQuery({
    queryKey: QK.themeAnalyzerAnalysis(selectedId, rangeStart, rangeEnd, mainboardOnly, poolKey),
    queryFn: () => api.themeAnalyzerAnalysis(selectedId, {
      start: rangeStart || undefined,
      end: rangeEnd || undefined,
      mainboardOnly,
    }),
    enabled: !!selectedTheme && !selectedTheme.source_error,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  })
  const analysis = analysisQuery.data

  const minuteQuery = useQuery({
    queryKey: QK.themeAnalyzerMinute(
      selectedId,
      minuteDate,
      [...minuteSymbols].sort().join(','),
      mainboardOnly,
      poolKey,
    ),
    queryFn: () => api.themeAnalyzerMinute(selectedId, minuteDate, minuteSymbols, mainboardOnly),
    enabled: !!selectedTheme && !selectedTheme.source_error && !!minuteDate && minuteSymbols.length > 0,
    staleTime: 120_000,
    refetchOnWindowFocus: false,
  })

  useEffect(() => {
    if (!analysis) return
    const context = `${analysis.theme_id}:${analysis.window_start}:${analysis.window_end}:${mainboardOnly}:${poolKey}`
    if (lastMinuteContext.current === context) return
    lastMinuteContext.current = context
    setMinuteSymbols(analysis.core_stocks.map(stock => stock.symbol).slice(0, MAX_MINUTE_STOCKS))
    setMinuteDate(analysis.latest_minute_date ?? analysis.minute_dates[analysis.minute_dates.length - 1] ?? '')
  }, [analysis, mainboardOnly, poolKey])

  const invalidateTheme = useCallback((themeId: string) => {
    void queryClient.invalidateQueries({ queryKey: QK.themeAnalyzerThemes })
    void queryClient.invalidateQueries({ queryKey: ['theme-analyzer', 'analysis', themeId] })
    void queryClient.invalidateQueries({ queryKey: ['theme-analyzer', 'minute', themeId] })
  }, [queryClient])

  const createMutation = useMutation({
    mutationFn: api.themeAnalyzerCreate,
    onSuccess: theme => {
      toast(`已创建主题「${theme.name}」`, 'success')
      setEditorOpen(false)
      setEditingTheme(null)
      queryClient.setQueryData<{ items: ThemeAnalyzerTheme[] }>(
        QK.themeAnalyzerThemes,
        current => ({ items: [theme, ...(current?.items ?? []).filter(item => item.id !== theme.id)] }),
      )
      setSelectedId(theme.id)
      void queryClient.invalidateQueries({ queryKey: QK.themeAnalyzerThemes })
    },
    onError: error => toast(errorText(error)),
  })
  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: ThemeEditorPayload }) =>
      api.themeAnalyzerUpdate(id, payload),
    onSuccess: theme => {
      toast('主题信息已保存', 'success')
      setEditorOpen(false)
      setEditingTheme(null)
      invalidateTheme(theme.id)
    },
    onError: error => toast(errorText(error)),
  })
  const deleteMutation = useMutation({
    mutationFn: api.themeAnalyzerDelete,
    onSuccess: (_, themeId) => {
      toast('主题已删除', 'success')
      queryClient.setQueryData<{ items: ThemeAnalyzerTheme[] }>(
        QK.themeAnalyzerThemes,
        current => ({ items: (current?.items ?? []).filter(item => item.id !== themeId) }),
      )
      void queryClient.invalidateQueries({ queryKey: QK.themeAnalyzerThemes })
      if (selectedId === themeId) setSelectedId('')
    },
    onError: error => toast(errorText(error)),
  })
  const savePoolMutation = useMutation({
    mutationFn: async ({ themeId, add, remove }: { themeId: string; add: string[]; remove: string[] }) => {
      if (add.length > 0) await api.themeAnalyzerAddStocks(themeId, add)
      for (const symbol of remove) await api.themeAnalyzerRemoveStock(themeId, symbol)
    },
    onSuccess: (_, variables) => {
      toast('股票池已保存', 'success')
      setPoolOpen(false)
      invalidateTheme(variables.themeId)
    },
    onError: error => toast(errorText(error)),
  })

  const handleDeleteTheme = useCallback((theme: ThemeAnalyzerTheme) => {
    if (!window.confirm(`删除主题「${theme.name}」？股票池会一并删除，行情数据不受影响。`)) return
    deleteMutation.mutate(theme.id)
  }, [deleteMutation])

  const openPreview = useCallback((symbol: string, name: string) => {
    setPreviewSymbol(symbol)
    setPreviewName(name)
  }, [])

  const handleMinuteDate = useCallback((day: string) => {
    setMinuteDate(day)
    if (!analysis) return
    const switchDay = analysis.limit_route.switch_days.find(item => item.date === day)
    const valid = new Set(analysis.leaders.map(leader => leader.symbol))
    const preferred = [
      ...(switchDay?.minute_symbols ?? []),
      ...analysis.core_stocks.map(stock => stock.symbol),
    ].filter(symbol => valid.has(symbol))
    if (preferred.length > 0) {
      setMinuteSymbols(Array.from(new Set(preferred)).slice(0, MAX_MINUTE_STOCKS))
    }
  }, [analysis])

  const toggleMinuteSymbol = useCallback((symbol: string) => {
    setMinuteSymbols(current => {
      if (current.includes(symbol)) {
        if (current.length === 1) {
          toast('至少保留一只股票')
          return current
        }
        return current.filter(item => item !== symbol)
      }
      if (current.length >= MAX_MINUTE_STOCKS) {
        toast(`最多同时查看 ${MAX_MINUTE_STOCKS} 只`)
        return current
      }
      return [...current, symbol]
    })
  }, [])

  const setQuickRange = useCallback((days: number) => {
    if (!analysis?.recent_dates.length) return
    const dates = analysis.recent_dates
    setRangeStart(dates[Math.max(0, dates.length - days)])
    setRangeEnd(dates[dates.length - 1])
  }, [analysis?.recent_dates])

  const analysisReady = analysis && analysis.candidate_count > 0
  const previewLeader = previewSymbol ? leaderMap(analysis?.leaders).get(previewSymbol) : undefined

  return (
    <div className="flex h-full min-h-0 flex-col">
      <PageHeader
        title="主题分析"
        subtitle="核心股 · 整波路径 · 关键日复盘"
        right={(
          <button
            type="button"
            onClick={() => void analysisQuery.refetch()}
            disabled={analysisQuery.isFetching}
            className="inline-flex items-center gap-1 rounded-btn border border-border px-2.5 py-1.5 text-[10px] text-secondary hover:text-foreground disabled:opacity-50"
          >
            <RefreshCw size={12} className={analysisQuery.isFetching ? 'animate-spin' : ''} />
            刷新
          </button>
        )}
      />

      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[252px_minmax(0,1fr)]">
        <aside className="max-h-52 min-h-0 border-b border-border bg-surface/70 lg:max-h-none lg:border-b-0 lg:border-r">
          <ThemeRail
            themes={themes}
            selectedId={selectedId}
            loading={themesQuery.isLoading}
            onSelect={setSelectedId}
            onCreate={() => {
              setEditingTheme(null)
              setEditorOpen(true)
            }}
            onEdit={theme => {
              setEditingTheme(theme)
              setEditorOpen(true)
            }}
            onDelete={handleDeleteTheme}
          />
        </aside>

        <main className="min-h-0 overflow-y-auto">
          <div className="mx-auto max-w-[1680px] space-y-3 px-3 py-3 lg:px-5 lg:py-4">
            {themesQuery.isError ? (
              <div className="rounded-2xl border border-danger/30 bg-danger/5 p-6">
                <div className="flex items-center gap-2 text-sm text-danger"><AlertTriangle size={16} /> 主题库加载失败</div>
                <p className="mt-2 text-xs text-secondary">{errorText(themesQuery.error)}</p>
                <button type="button" onClick={() => void themesQuery.refetch()} className="mt-3 rounded-btn border border-border px-3 py-1.5 text-xs text-secondary hover:text-foreground">
                  重试
                </button>
              </div>
            ) : themesQuery.isLoading ? (
              <div className="flex min-h-[420px] items-center justify-center gap-2 text-sm text-muted">
                <Loader2 size={18} className="animate-spin text-accent" /> 加载主题库
              </div>
            ) : !selectedTheme ? (
              <EmptyState icon={Tags} title="先创建一个主题" hint="新建主题并加入股票后开始分析。" />
            ) : selectedTheme.source_error ? (
              <div className="rounded-2xl border border-danger/30 bg-danger/5 p-6">
                <p className="text-sm text-danger">{selectedTheme.source_error}</p>
                <button type="button" onClick={() => { setEditingTheme(selectedTheme); setEditorOpen(true) }} className="mt-3 text-xs text-accent">
                  重新选择股票池来源
                </button>
              </div>
            ) : analysisQuery.isError ? (
              <div className="rounded-2xl border border-danger/30 bg-danger/5 p-6">
                <div className="flex items-center gap-2 text-sm text-danger"><AlertTriangle size={16} /> 分析计算失败</div>
                <p className="mt-2 text-xs text-secondary">{errorText(analysisQuery.error)}</p>
                <button type="button" onClick={() => void analysisQuery.refetch()} className="mt-3 rounded-btn border border-border px-3 py-1.5 text-xs text-secondary hover:text-foreground">
                  重试
                </button>
              </div>
            ) : !analysis ? (
              <div className="flex min-h-[420px] items-center justify-center gap-2 text-sm text-muted">
                <Loader2 size={18} className="animate-spin text-accent" /> 计算区间路径
              </div>
            ) : (
              <>
                <section className="rounded-2xl border border-border bg-surface/92 p-4">
                  <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: selectedTheme.color }} />
                        <h2 className="text-lg font-semibold tracking-tight text-foreground">{selectedTheme.name}</h2>
                        <span className="rounded-full border border-border bg-base/40 px-2 py-0.5 font-mono text-[9px] text-muted">
                          {analysis.window_start} → {analysis.window_end}
                        </span>
                      </div>
                      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] text-muted">
                        <span className="inline-flex items-center gap-1"><Layers3 size={12} /> 股票池 {analysis.pool_count}</span>
                        <span className="inline-flex items-center gap-1"><Activity size={12} /> 候选 {analysis.candidate_count}</span>
                        <span className="inline-flex items-center gap-1"><Clock3 size={12} /> 分钟截至 {analysis.latest_minute_date ?? '—'}</span>
                      </div>
                      <div className="mt-3 flex flex-wrap items-center gap-1.5">
                        <DatePicker
                          value={rangeStart || analysis.window_start}
                          onChange={setRangeStart}
                          max={rangeEnd || analysis.window_end}
                          buttonClassName="h-8 text-[10px]"
                          placeholder="开始日期"
                        />
                        <span className="text-[10px] text-muted">至</span>
                        <DatePicker
                          value={rangeEnd || analysis.window_end}
                          onChange={setRangeEnd}
                          min={rangeStart || undefined}
                          max={analysis.window_end}
                          buttonClassName="h-8 text-[10px]"
                          placeholder="结束日期"
                        />
                        {[20, 60, 120].map(days => (
                          <button
                            key={days}
                            type="button"
                            onClick={() => setQuickRange(days)}
                            className="rounded border border-border px-2 py-1 text-[10px] text-muted hover:text-foreground"
                          >
                            近 {days} 日
                          </button>
                        ))}
                        <label className="ml-1 inline-flex items-center gap-1.5 text-[10px] text-secondary">
                          <input
                            type="checkbox"
                            checked={mainboardOnly}
                            onChange={event => setMainboardOnly(event.target.checked)}
                            className="h-3.5 w-3.5 accent-amber-500"
                          />
                          仅沪深主板
                        </label>
                        {(rangeStart || rangeEnd) && (
                          <button
                            type="button"
                            onClick={() => {
                              setRangeStart('')
                              setRangeEnd('')
                            }}
                            className="rounded border border-border px-2 py-1 text-[10px] text-muted hover:text-foreground"
                          >
                            恢复默认
                          </button>
                        )}
                      </div>
                    </div>
                    <div className="flex shrink-0 flex-wrap items-center gap-1.5">
                      <button
                        type="button"
                        onClick={() => setPoolOpen(true)}
                        className="inline-flex items-center gap-1 rounded-btn border border-accent/35 bg-accent/10 px-2.5 py-1.5 text-[10px] text-accent hover:bg-accent/20"
                      >
                        <Layers3 size={12} /> 管理股票池
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setEditingTheme(selectedTheme)
                          setEditorOpen(true)
                        }}
                        className="inline-flex items-center gap-1 rounded-btn border border-border bg-base/40 px-2.5 py-1.5 text-[10px] text-secondary hover:text-foreground"
                      >
                        <Pencil size={12} /> 编辑
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDeleteTheme(selectedTheme)}
                        className="inline-flex items-center gap-1 rounded-btn border border-border bg-base/40 px-2.5 py-1.5 text-[10px] text-muted hover:border-danger/30 hover:text-danger"
                      >
                        <Trash2 size={12} /> 删除
                      </button>
                    </div>
                  </div>
                </section>

                {!analysisReady ? (
                  <EmptyState
                    icon={Plus}
                    title="当前筛选下没有股票"
                    hint={analysis.filtered_count > 0 ? '股票池中的非主板股票已被隐藏，可关闭“仅沪深主板”或管理股票池。' : '打开“管理股票池”加入股票。'}
                  />
                ) : (
                  <>
                    <div className="grid grid-cols-2 gap-2.5 md:grid-cols-4">
                      <StatCard label="候选股票" value={analysis.candidate_count} hint={`主板筛选隐藏 ${analysis.filtered_count} 只`} icon={Layers3} />
                      <StatCard label="核心股" value={analysis.core_stocks.length} hint="区间复盘名单" icon={Crown} tone="accent" />
                      <StatCard
                        label="题材等权"
                        value={fmtPct(analysis.pool_return, 1)}
                        hint="仅作辅助对照"
                        icon={TrendingUp}
                        tone={(analysis.pool_return ?? 0) >= 0 ? 'up' : 'down'}
                      />
                      <StatCard
                        label="上证同期"
                        value={fmtPct(analysis.sh_return, 1)}
                        hint="000001.SH"
                        icon={Activity}
                        tone={(analysis.sh_return ?? 0) >= 0 ? 'up' : 'down'}
                      />
                    </div>

                    <CoreStockCards analysis={analysis} onSelect={openPreview} />

                    <SectionCard title="整波路径" hint="核心股以区间前一交易日收盘=100；缺口不补零">
                      <div className="p-2 pt-0">
                        <ThemeTrendChart analysis={analysis} height={340} />
                      </div>
                    </SectionCard>

                    <LimitRouteMap
                      key={`${analysis.theme_id}:${analysis.window_start}:${analysis.window_end}:${mainboardOnly}`}
                      data={analysis.limit_route}
                      stockSegments={selectedTheme.stock_segments}
                      onFocusDay={handleMinuteDate}
                      onSelectStock={openPreview}
                    />

                    <MinuteLab
                      analysis={analysis}
                      minuteDate={minuteDate}
                      onDateChange={handleMinuteDate}
                      selectedSymbols={minuteSymbols}
                      onToggleSymbol={toggleMinuteSymbol}
                      minute={minuteQuery.data}
                      loading={minuteQuery.isLoading}
                      error={minuteQuery.error}
                      onRetry={() => void minuteQuery.refetch()}
                    />

                    <LeaderTable analysis={analysis} onSelect={openPreview} />
                  </>
                )}
              </>
            )}
          </div>
        </main>
      </div>

      <ThemeEditorDialog
        open={editorOpen}
        theme={editingTheme}
        busy={createMutation.isPending || updateMutation.isPending}
        onClose={() => {
          if (createMutation.isPending || updateMutation.isPending) return
          setEditorOpen(false)
          setEditingTheme(null)
        }}
        onSave={payload => {
          if (editingTheme) updateMutation.mutate({ id: editingTheme.id, payload })
          else createMutation.mutate(payload)
        }}
      />

      <StockPoolDialog
        open={poolOpen}
        theme={selectedTheme}
        analysis={analysis}
        busy={savePoolMutation.isPending}
        onClose={() => {
          if (!savePoolMutation.isPending) setPoolOpen(false)
        }}
        onSave={(add, remove) => {
          if (!selectedTheme) return
          savePoolMutation.mutate({ themeId: selectedTheme.id, add, remove })
        }}
      />

      <StockPreviewDialog
        symbol={previewSymbol}
        name={previewName || previewLeader?.name}
        navList={analysis?.leaders.map(leader => ({ symbol: leader.symbol, name: leader.name })) ?? []}
        onNavigate={(symbol, name) => {
          setPreviewSymbol(symbol)
          setPreviewName(name ?? '')
        }}
        onClose={() => setPreviewSymbol(null)}
      />
    </div>
  )
}
