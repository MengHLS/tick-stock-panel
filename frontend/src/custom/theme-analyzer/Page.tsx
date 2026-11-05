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
  ArrowDownRight,
  ArrowUpRight,
  CalendarRange,
  Check,
  Clock3,
  Crown,
  Flame,
  Layers3,
  Loader2,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  ShieldAlert,
  Sparkles,
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
import { fmtBigNum, fmtPct, priceColorClass } from '@/lib/format'
import { MinuteOverlayChart, ThemeQuadrantChart, ThemeTrendChart } from './charts'
import { LimitRouteMap } from './LimitRouteMap'
import { IndustrySourcePicker } from './IndustrySourcePicker'

const THEME_COLORS = ['#F59E0B', '#22D3EE', '#FB7185', '#A78BFA', '#A3E635', '#60A5FA']
const MINUTE_COLORS = ['#F59E0B', '#22D3EE', '#A78BFA', '#FB7185', '#A3E635', '#60A5FA', '#FB923C', '#34D399']
const MAX_MINUTE_STOCKS = 8
const MAX_HEATMAP_ROWS = 18
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

function pctPoint(value: number | null | undefined, digits = 2) {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${value > 0 ? '+' : ''}${value.toFixed(digits)}%`
}

function shortDate(value: string | null | undefined) {
  return value ? value.slice(5) : '—'
}

function leaderMap(leaders: ThemeAnalyzerLeader[] | undefined) {
  return new Map((leaders ?? []).map(leader => [leader.symbol, leader]))
}

function errorText(error: unknown) {
  return error instanceof Error ? error.message : '请求失败'
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
            <p className="mt-1 text-[11px] text-muted">
              支持自建股票池或动态关联产业链，行情分析按请求计算。
            </p>
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
              placeholder="例如：阳 / 洋 / 羊"
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
              placeholder="记录主题来源、观察线索或交易假设"
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
          {theme && <p className="text-[10px] text-muted">当前股票池 {theme.symbols.length} 只，创建后可在主页面继续增删。</p>}
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
            <p className="mt-1 text-[10px] leading-4 text-muted">新建后把股票加入池中，页面会自动生成整套分析。</p>
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
      <div className="border-t border-border px-3.5 py-2.5 text-[9px] leading-4 text-muted">
        主题数据保存在本地用户目录；不同主题共享同一套行情计算口径。
      </div>
    </div>
  )
}

function StockSearch({
  theme,
  busy,
  onAdd,
}: {
  theme: ThemeAnalyzerTheme
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
  const existing = useMemo(() => new Set(theme.symbols), [theme.symbols])
  const results = (search.data?.results ?? []).filter(item => !existing.has(item.symbol))

  return (
    <div className="relative min-w-[220px] flex-1">
      <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
      <input
        value={query}
        onChange={event => setQuery(event.target.value)}
        placeholder="添加股票：代码 / 名称 / 拼音"
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
              {search.data?.results?.length ? '搜索结果已全部在主题中' : '没有找到股票'}
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

function InsightCard({
  title,
  icon: Icon,
  name,
  value,
  detail,
  tone,
}: {
  title: string
  icon: typeof Crown
  name: string
  value: string
  detail: string
  tone: 'up' | 'down' | 'accent'
}) {
  return (
    <div className="relative overflow-hidden rounded-2xl border border-border bg-surface/90 p-4">
      <div className="pointer-events-none absolute -right-6 -top-6 h-24 w-24 rounded-full bg-elevated/50 blur-2xl" />
      <div className="flex items-center gap-2 text-[10px] text-muted">
        <Icon size={14} className={tone === 'down' ? 'text-bear' : tone === 'accent' ? 'text-accent' : 'text-bull'} />
        {title}
      </div>
      <div className="mt-3 flex items-end justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-base font-semibold text-foreground">{name}</div>
          <div className="mt-1 text-[10px] leading-4 text-muted">{detail}</div>
        </div>
        <div className={cn(
          'shrink-0 font-mono text-lg font-semibold tabular-nums',
          tone === 'down' ? 'text-bear' : tone === 'accent' ? 'text-accent' : 'text-bull',
        )}>
          {value}
        </div>
      </div>
    </div>
  )
}

function WindowTable({
  leaders,
  activeOnly,
  onToggleActive,
  onSelect,
}: {
  leaders: ThemeAnalyzerLeader[]
  activeOnly: boolean
  onToggleActive: () => void
  onSelect: (symbol: string, name: string) => void
}) {
  const rows = activeOnly ? leaders.filter(leader => leader.active) : leaders
  return (
    <SectionCard
      title="3 / 10 / 30 日窗口峰值"
      hint="最大涨幅 = 收盘(t) / 收盘(t−N) − 1，在窗口内取最大值；日期为发生日"
      action={
        <button
          type="button"
          onClick={onToggleActive}
          className={cn(
            'rounded-btn border px-2.5 py-1 text-[10px]',
            activeOnly
              ? 'border-amber-400/35 bg-amber-400/10 text-amber-400'
              : 'border-border bg-base/50 text-muted hover:text-foreground',
          )}
        >
          {activeOnly ? '仅看涨停活跃' : '全部股票'}
        </button>
      }
    >
      <div className="max-h-[520px] overflow-auto">
        <table className="w-full min-w-[980px] border-collapse text-xs">
          <thead className="sticky top-0 z-10 bg-surface text-[10px] text-muted">
            <tr className="border-b border-border">
              <th className="px-4 py-2.5 text-left font-medium">股票</th>
              <th className="px-3 py-2.5 text-right font-medium">30日最大</th>
              <th className="px-3 py-2.5 text-right font-medium">10日最大</th>
              <th className="px-3 py-2.5 text-right font-medium">3日最大</th>
              <th className="px-3 py-2.5 text-right font-medium">当前3日</th>
              <th className="px-3 py-2.5 text-right font-medium">主动&gt;2%</th>
              <th className="px-3 py-2.5 text-right font-medium">日均偏离</th>
              <th className="px-3 py-2.5 text-right font-medium">收盘位置</th>
              <th className="px-4 py-2.5 text-right font-medium">事件</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(leader => (
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
                        {leader.active && <span className="rounded bg-amber-400/10 px-1 py-0.5 text-[8px] text-amber-400">活跃</span>}
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
                <td className="px-3 py-2.5 text-right font-mono text-secondary">{leader.active_gt2} 天</td>
                <td className={cn('px-3 py-2.5 text-right font-mono tabular-nums', priceColorClass(leader.avg_deviate))}>
                  {fmtPct(leader.avg_deviate, 2)}
                </td>
                <td className="px-3 py-2.5 text-right font-mono text-secondary">
                  {leader.avg_close_pos == null ? '—' : `${(leader.avg_close_pos * 100).toFixed(1)}%`}
                </td>
                <td className="px-4 py-2.5 text-right font-mono text-muted">{leader.event_count || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SectionCard>
  )
}

function HeatmapTable({
  analysis,
  showAll,
  onToggle,
  onSelect,
}: {
  analysis: ThemeAnalyzerAnalysis
  showAll: boolean
  onToggle: () => void
  onSelect: (symbol: string, name: string) => void
}) {
  const rows = showAll ? analysis.heatmap.rows : analysis.heatmap.rows.slice(0, MAX_HEATMAP_ROWS)
  return (
    <SectionCard
      title="逐日相对强弱热力图（辅助）"
      hint="主动偏离 = 个股当日涨幅 − 所属板块基准当日涨幅；用于看扩散与退潮，路线切换以上方涨停接力图为准"
      action={
        <button
          type="button"
          onClick={onToggle}
          className="rounded-btn border border-border bg-base/50 px-2.5 py-1 text-[10px] text-muted hover:text-foreground"
        >
          {showAll ? '收起' : `展开全部 ${analysis.heatmap.rows.length}`}
        </button>
      }
    >
      <div className="max-h-[480px] overflow-auto">
        <table className="border-separate border-spacing-0 text-[9px]">
          <thead>
            <tr>
              <th className="sticky left-0 top-0 z-20 min-w-[100px] border-b border-r border-border bg-surface px-3 py-2 text-left font-medium text-muted">
                股票
              </th>
              {analysis.heatmap.dates.map(day => (
                <th key={day} className="sticky top-0 z-10 min-w-[32px] border-b border-border bg-surface px-0.5 py-1.5 text-center font-mono font-normal text-muted">
                  {shortDate(day)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(row => (
              <tr key={row.symbol}>
                <td className="sticky left-0 z-10 border-b border-r border-border/60 bg-surface px-3 py-1.5">
                  <button
                    type="button"
                    onClick={() => onSelect(row.symbol, row.name)}
                    className="flex max-w-[120px] items-center gap-1.5 text-left hover:text-accent"
                  >
                    <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', row.active ? 'bg-amber-400' : 'bg-border')} />
                    <span className="truncate text-[10px] text-secondary">{row.name}</span>
                  </button>
                </td>
                {row.values.map((value, index) => {
                  const marker = row.markers[index]
                  const intensity = value == null ? 0 : Math.min(Math.abs(value) / 0.12, 1)
                  const background = value == null
                    ? 'transparent'
                    : value >= 0
                      ? `rgba(240, 68, 56, ${0.06 + intensity * 0.34})`
                      : `rgba(18, 183, 106, ${0.06 + intensity * 0.30})`
                  return (
                    <td
                      key={`${row.symbol}-${analysis.heatmap.dates[index]}`}
                      title={`${analysis.heatmap.dates[index]} · ${row.name} · ${value == null ? '—' : fmtPct(value, 1)}${marker === 'seal' ? ' · 封板' : marker === 'broken' ? ' · 炸板' : ''}`}
                      className="relative h-7 border-b border-border/40 p-0 text-center"
                      style={{ background }}
                    >
                      {marker && (
                        <span className={cn(
                          'absolute right-0.5 top-0.5 rounded px-0.5 text-[7px] font-bold leading-none',
                          marker === 'seal' ? 'bg-bull/80 text-white' : 'bg-bear/80 text-white',
                        )}>
                          {marker === 'seal' ? 'S' : 'B'}
                        </span>
                      )}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SectionCard>
  )
}

function MinuteLab({
  analysis,
  stockSegments,
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
  stockSegments?: Record<string, string[]>
  minuteDate: string
  onDateChange: (date: string) => void
  selectedSymbols: string[]
  onToggleSymbol: (symbol: string) => void
  minute: ThemeAnalyzerMinute | undefined
  loading: boolean
  error: unknown
  onRetry: () => void
}) {
  const topStocks = useMemo(() => {
    const leaderBySymbol = new Map(analysis.leaders.map(leader => [leader.symbol, leader]))
    const minuteNames = new Map((minute?.stocks ?? []).map(stock => [stock.symbol, stock.name]))
    const symbols = [
      ...selectedSymbols,
      ...analysis.leaders
        .filter(leader => leader.active)
        .slice(0, 12)
        .map(leader => leader.symbol),
    ]
    return [...new Set(symbols)].map(symbol => ({
      symbol,
      name: leaderBySymbol.get(symbol)?.name ?? minuteNames.get(symbol) ?? symbol,
    }))
  }, [analysis.leaders, minute?.stocks, selectedSymbols])
  const colorMap = useMemo(
    () => Object.fromEntries(selectedSymbols.map((symbol, index) => [symbol, MINUTE_COLORS[index % MINUTE_COLORS.length]])),
    [selectedSymbols],
  )
  const switchDay = analysis.limit_route.switch_days.find(day => day.date === minuteDate)
  return (
    <SectionCard
      title="切换日 / 关键日分时实验室"
      hint="优先从上方切换节点进入；分钟线、同一时间轴 5 分钟叠加表和日内量价特征共用一份样本"
      action={
        analysis.minute_dates.length ? (
          <label className="flex items-center gap-1.5 text-[10px] text-muted">
            <CalendarRange size={12} />
            <select
              value={minuteDate}
              onChange={event => onDateChange(event.target.value)}
              className="h-7 rounded-btn border border-border bg-base px-2 font-mono text-[10px] text-foreground outline-none focus:border-accent/60"
            >
              {[...analysis.minute_dates].reverse().map(day => (
                <option key={day} value={day}>{day}</option>
              ))}
            </select>
          </label>
        ) : null
      }
    >
      {analysis.minute_dates.length === 0 ? (
        <EmptyState icon={Clock3} title="暂无分钟数据" hint="本地分钟分区尚未覆盖当前窗口，补齐分钟数据后即可叠加。"
        />
      ) : (
        <>
          {switchDay && (
            <div className="border-b border-border/70 bg-amber-400/[0.05] px-4 py-3">
              <p className="text-xs font-medium text-foreground">{switchDay.date} · {switchDay.label}</p>
              <p className="mt-1 text-[11px] leading-5 text-secondary">{switchDay.reason}</p>
              <p className="mt-1 text-[11px] leading-5 text-muted">
                前任领涨：{switchDay.previous_leader_name ?? '—'}　→　当日领涨：{switchDay.leader_name ?? '—'}　·　空间龙头：{analysis.limit_route.space_leader_name ?? '—'}
              </p>
            </div>
          )}
          <div className="border-b border-border/70 px-4 py-3">
            <div className="mb-2 flex items-center justify-between gap-3">
              <span className="text-[10px] text-muted">叠加股票（最多 {MAX_MINUTE_STOCKS} 只）</span>
              <span className="font-mono text-[9px] text-muted">{selectedSymbols.length}/{MAX_MINUTE_STOCKS}</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {topStocks.map(stock => {
                const selected = selectedSymbols.includes(stock.symbol)
                return (
                  <button
                    key={stock.symbol}
                    type="button"
                    onClick={() => onToggleSymbol(stock.symbol)}
                    className={cn(
                      'inline-flex items-center gap-1 rounded-full border px-2 py-1 text-[10px] transition-colors',
                      selected
                        ? 'border-transparent text-white'
                        : 'border-border bg-base/50 text-muted hover:border-accent/30 hover:text-foreground',
                    )}
                    style={selected ? { backgroundColor: colorMap[stock.symbol] ?? '#64748B' } : undefined}
                    title={stockSegments?.[stock.symbol]?.join(' / ')}
                  >
                    <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: selected ? '#fff' : colorMap[stock.symbol] ?? '#64748B' }} />
                    {stock.name}
                    {!!stockSegments?.[stock.symbol]?.length && <span className="opacity-70">· {stockSegments[stock.symbol].join(' / ')}</span>}
                  </button>
                )
              })}
            </div>
          </div>
          {loading ? (
            <div className="flex min-h-72 items-center justify-center gap-2 text-xs text-muted">
              <Loader2 size={15} className="animate-spin text-accent" /> 正在计算分钟主动性
            </div>
          ) : error ? (
            <div className="flex min-h-72 flex-col items-center justify-center gap-3 px-6 text-center">
              <AlertTriangle size={24} className="text-danger" />
              <p className="text-xs text-danger">{errorText(error)}</p>
              <button type="button" onClick={onRetry} className="inline-flex items-center gap-1.5 rounded-btn border border-border bg-elevated px-3 py-1.5 text-xs text-secondary hover:text-foreground">
                <RefreshCw size={12} /> 重试
              </button>
            </div>
          ) : !minute || minute.status === 'no_data' || minute.status === 'empty' ? (
            <EmptyState icon={Clock3} title="该日分钟样本不足" hint="可能是一字板、停牌或本地分钟尚未入库。换一个关键日或补齐数据后再看。" />
          ) : (
            <div className="space-y-4 p-4">
              <MinuteOverlayChart minute={minute} colors={colorMap} height={320} />

              <div>
                <div className="mb-2 flex items-center gap-2 text-[10px] text-muted">
                  <Layers3 size={13} className="text-accent" />
                  同一时间轴叠加表 · 5 分钟采样
                </div>
                <div className="max-h-[390px] overflow-auto rounded-xl border border-border">
                  <table className="w-full min-w-max border-collapse text-[10px]">
                    <thead className="sticky top-0 z-10 bg-surface">
                      <tr className="border-b border-border">
                        <th className="sticky left-0 z-20 min-w-[58px] border-r border-border bg-surface px-2 py-2 text-left font-medium text-muted">时间</th>
                        {minute.stocks.map(stock => (
                          <th key={stock.symbol} className="min-w-[76px] px-2 py-2 text-right font-medium text-secondary">
                            <span className="inline-flex items-center gap-1">
                              <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: colorMap[stock.symbol] }} />
                              {stock.name}
                            </span>
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {minute.table.times.map(time => (
                        <tr key={time} className="border-b border-border/40 last:border-0">
                          <td className="sticky left-0 z-10 border-r border-border bg-surface px-2 py-1 font-mono text-muted">{time}</td>
                          {minute.stocks.map(stock => {
                            const value = minute.table.series[stock.symbol]?.[minute.table.times.indexOf(time)]
                            return (
                              <td key={stock.symbol} className={cn('px-2 py-1 text-right font-mono tabular-nums', priceColorClass(value))}>
                                {pctPoint(value, 2)}
                              </td>
                            )
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div>
                <div className="mb-2 flex items-center gap-2 text-[10px] text-muted">
                  <Activity size={13} className="text-accent" />
                  日内特征 · 量价方向代理
                </div>
                <div className="overflow-auto rounded-xl border border-border">
                  <table className="w-full min-w-[820px] border-collapse text-[10px]">
                    <thead className="bg-elevated/40 text-muted">
                      <tr className="border-b border-border">
                        <th className="px-3 py-2 text-left font-medium">股票</th>
                        <th className="px-2 py-2 text-right font-medium">全日</th>
                        <th className="px-2 py-2 text-right font-medium">前30分</th>
                        <th className="px-2 py-2 text-right font-medium">上午</th>
                        <th className="px-2 py-2 text-right font-medium">下午</th>
                        <th className="px-2 py-2 text-right font-medium">尾30分</th>
                        <th className="px-2 py-2 text-right font-medium">最大回撤</th>
                        <th className="px-2 py-2 text-right font-medium">VWAP偏离</th>
                        <th className="px-2 py-2 text-right font-medium">上涨量占比</th>
                        <th className="px-3 py-2 text-right font-medium">样本</th>
                      </tr>
                    </thead>
                    <tbody>
                      {minute.stocks.map(stock => {
                        const feature = minute.features[stock.symbol]
                        if (!feature) {
                          return (
                            <tr key={stock.symbol} className="border-b border-border/40 last:border-0">
                              <td className="px-3 py-2 text-secondary">{stock.name}</td>
                              <td colSpan={9} className="px-3 py-2 text-right text-muted">无分钟样本</td>
                            </tr>
                          )
                        }
                        return (
                          <tr key={stock.symbol} className="border-b border-border/40 last:border-0">
                            <td className="px-3 py-2 text-secondary">{stock.name}</td>
                            {(['day', 'open30', 'am', 'pm', 'tail30', 'max_dd'] as const).map(key => (
                              <td key={key} className={cn('px-2 py-2 text-right font-mono tabular-nums', priceColorClass(feature[key]))}>
                                {pctPoint(feature[key])}
                              </td>
                            ))}
                            <td className="px-2 py-2 text-right font-mono text-secondary">{pctPoint(feature.vwap_dev)}</td>
                            <td className="px-2 py-2 text-right font-mono text-secondary">
                              {feature.up_ratio == null ? '—' : `${feature.up_ratio.toFixed(1)}%`}
                            </td>
                            <td className="px-3 py-2 text-right font-mono text-muted">{feature.sample || '—'}</td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
                <p className="mt-2 text-[9px] leading-4 text-muted">
                  上涨量占比 = 上涨分钟成交量 /（上涨 + 下跌分钟成交量），仅作方向代理；金额缺失时 VWAP 使用收盘价 × 成交量 × 100 估算。
                </p>
              </div>
            </div>
          )}
        </>
      )}
    </SectionCard>
  )
}

function StockPool({
  theme,
  analysis,
  busy,
  onAdd,
  onRemove,
  onSelect,
}: {
  theme: ThemeAnalyzerTheme
  analysis: ThemeAnalyzerAnalysis | undefined
  busy: boolean
  onAdd: (symbol: string) => void
  onRemove: (symbol: string) => void
  onSelect: (symbol: string, name: string) => void
}) {
  const stats = leaderMap(analysis?.leaders)
  return (
    <SectionCard
      title="股票池"
      hint={`${theme.symbols.length} 只标的；支持搜索代码、名称或拼音首字母添加`}
      action={<StockSearch theme={theme} busy={busy} onAdd={onAdd} />}
    >
      {!!theme.excluded_symbols?.length && (
        <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-2 text-xs text-muted">
          本主题已排除：
          {theme.excluded_symbols.map(symbol => (
            <button key={symbol} type="button" disabled={busy} onClick={() => onAdd(symbol)} className="rounded border border-border px-2 py-1 text-accent disabled:opacity-40">
              恢复 {symbol}
            </button>
          ))}
        </div>
      )}
      {theme.symbols.length === 0 ? (
        <EmptyState icon={Plus} title="股票池为空" hint="在上方搜索框输入股票代码或名称，加入第一只股票后即可生成分析。" />
      ) : (
        <div className="max-h-[390px] overflow-auto">
          <table className="w-full min-w-[760px] border-collapse text-xs">
            <thead className="sticky top-0 z-10 bg-surface text-[10px] text-muted">
              <tr className="border-b border-border">
                <th className="px-4 py-2 text-left font-medium">股票</th>
                <th className="px-3 py-2 text-right font-medium">最新价</th>
                <th className="px-3 py-2 text-right font-medium">30日最大</th>
                <th className="px-3 py-2 text-right font-medium">当前3日</th>
                <th className="px-3 py-2 text-right font-medium" title="窗口内个股日涨幅相对基准超额 >2% 的天数">跑赢天数</th>
                <th className="px-3 py-2 text-right font-medium">事件</th>
                <th className="px-4 py-2 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {theme.symbols.map(symbol => {
                const stat = stats.get(symbol)
                return (
                  <tr key={symbol} className="border-b border-border/50 last:border-0 hover:bg-elevated/35">
                    <td className="px-4 py-2">
                      <button
                        type="button"
                        onClick={() => onSelect(symbol, stat?.name ?? symbol)}
                        className="flex items-center gap-2 text-left"
                      >
                        <span className={cn('h-1.5 w-1.5 rounded-full', stat?.active ? 'bg-amber-400' : 'bg-border')} />
                        <span>
                          <span className="block font-medium text-foreground">{stat?.name ?? symbol}</span>
                          <span className="mt-0.5 block font-mono text-[9px] text-muted">{symbol}</span>
                          <span className="mt-0.5 block text-[10px] text-accent">
                            {theme.stock_segments?.[symbol]?.join(' / ') || '手动添加'}
                          </span>
                        </span>
                      </button>
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-secondary">{stat?.last_close?.toFixed(2) ?? '—'}</td>
                    <td className={cn('px-3 py-2 text-right font-mono tabular-nums', priceColorClass(stat?.max_ret_30))}>{fmtPct(stat?.max_ret_30, 1)}</td>
                    <td className={cn('px-3 py-2 text-right font-mono tabular-nums', priceColorClass(stat?.latest_ret_3))}>{fmtPct(stat?.latest_ret_3, 1)}</td>
                    <td className="px-3 py-2 text-right font-mono text-secondary">{stat?.active_gt2 ?? '—'}</td>
                    <td className="px-3 py-2 text-right font-mono text-muted">{stat?.event_count || '—'}</td>
                    <td className="px-4 py-2 text-right">
                      <button
                        type="button"
                        onClick={() => onRemove(symbol)}
                        disabled={busy}
                        className="rounded p-1.5 text-muted hover:bg-danger/10 hover:text-danger disabled:opacity-40"
                        aria-label={`从主题移除 ${symbol}`}
                        title={theme.inherited_symbols?.includes(symbol) ? '仅在本主题排除，不修改产业链' : '移除手动添加股'}
                      >
                        <Trash2 size={13} />
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </SectionCard>
  )
}

function SealStructure({
  analysis,
  onSelect,
}: {
  analysis: ThemeAnalyzerAnalysis
  onSelect: (symbol: string, name: string) => void
}) {
  const seal = analysis.seal
  return (
    <SectionCard
      title="最新封板结构"
      hint={`${seal.date} · 封 ${seal.sealed_count} / 炸 ${seal.broken_count} · 触及 ${seal.touched} · 封板率 ${seal.seal_rate == null ? '—' : `${(seal.seal_rate * 100).toFixed(1)}%`}`}
    >
      <div className="grid gap-0 lg:grid-cols-2">
        <div className="border-b border-border/70 p-4 lg:border-b-0 lg:border-r">
          <div className="mb-3 flex items-center gap-2 text-[10px] font-medium text-bull">
            <Flame size={13} /> 封板 {seal.sealed_count}
          </div>
          <div className="space-y-1.5">
            {seal.sealed.length === 0 ? (
              <p className="py-8 text-center text-[11px] text-muted">当前窗口内没有主题股票封板</p>
            ) : seal.sealed.map(row => (
              <button
                key={row.symbol}
                type="button"
                onClick={() => onSelect(row.symbol, row.name)}
                className="flex w-full items-center justify-between gap-3 rounded-lg border border-border/60 bg-base/35 px-2.5 py-2 text-left hover:border-bull/30 hover:bg-bull/5"
              >
                <span className="min-w-0">
                  <span className="block truncate text-xs font-medium text-foreground">{row.name}</span>
                  <span className="mt-0.5 block truncate font-mono text-[9px] text-muted">
                    首封 {row.first} · {row.opens ? `开板 ${row.opens} 次` : '未开板'} · 窗口累计 {row.total_lu} 次 · {row.reason || '—'}
                  </span>
                </span>
                <span className="shrink-0 text-right">
                  <span className="block font-mono text-[11px] text-bull">{row.consec}连板</span>
                  <span className="mt-0.5 block text-[9px] text-muted">
                    {row.opens && row.last !== '—' ? `回封 ${row.last}` : row.money ? fmtBigNum(row.money) : '—'}
                  </span>
                </span>
              </button>
            ))}
          </div>
        </div>
        <div className="p-4">
          <div className="mb-3 flex items-center gap-2 text-[10px] font-medium text-bear">
            <ArrowDownRight size={13} /> 炸板 {seal.broken_count}
          </div>
          <div className="space-y-1.5">
            {seal.broken.length === 0 ? (
              <p className="py-8 text-center text-[11px] text-muted">当前窗口内没有主题股票炸板</p>
            ) : seal.broken.map(row => (
              <button
                key={row.symbol}
                type="button"
                onClick={() => onSelect(row.symbol, row.name)}
                className="flex w-full items-center justify-between gap-3 rounded-lg border border-border/60 bg-base/35 px-2.5 py-2 text-left hover:border-bear/30 hover:bg-bear/5"
              >
                <span className="min-w-0">
                  <span className="block truncate text-xs font-medium text-foreground">{row.name}</span>
                  <span className="mt-0.5 block truncate font-mono text-[9px] text-muted">{row.first} → {row.last}</span>
                </span>
                <span className="shrink-0 font-mono text-[10px] text-bear">{row.opens ? `开板 ${row.opens}` : '炸板'}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </SectionCard>
  )
}

export function ThemeAnalyzerPage() {
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState(loadSelectedTheme)
  const [editorOpen, setEditorOpen] = useState(false)
  const [editingTheme, setEditingTheme] = useState<ThemeAnalyzerTheme | null>(null)
  const [rangeStart, setRangeStart] = useState('')
  const [rangeEnd, setRangeEnd] = useState('')
  const [activeOnly, setActiveOnly] = useState(false)
  const [showAllHeatmap, setShowAllHeatmap] = useState(false)
  const [minuteDate, setMinuteDate] = useState('')
  const [minuteSymbols, setMinuteSymbols] = useState<string[]>([])
  const [previewSymbol, setPreviewSymbol] = useState<string | null>(null)
  const [previewName, setPreviewName] = useState('')
  const lastMinuteTheme = useRef('')
  const minuteLabRef = useRef<HTMLDivElement | null>(null)

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
    if (!themes.some(theme => theme.id === selectedId)) {
      setSelectedId(themes[0].id)
    }
  }, [selectedId, themes, themesQuery.isLoading])

  useEffect(() => {
    saveSelectedTheme(selectedId)
    setRangeStart('')
    setRangeEnd('')
    setActiveOnly(false)
    setShowAllHeatmap(false)
    setMinuteDate('')
    setMinuteSymbols([])
    lastMinuteTheme.current = ''
  }, [selectedId])

  const analysisQuery = useQuery({
    queryKey: QK.themeAnalyzerAnalysis(selectedId, rangeStart, rangeEnd, poolKey),
    queryFn: () => api.themeAnalyzerAnalysis(selectedId, {
      start: rangeStart || undefined,
      end: rangeEnd || undefined,
    }),
    enabled: !!selectedTheme && !selectedTheme.source_error,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  })
  const analysis = analysisQuery.data

  const minuteQuery = useQuery({
    queryKey: QK.themeAnalyzerMinute(selectedId, minuteDate, [...minuteSymbols].sort().join(','), poolKey),
    queryFn: () => api.themeAnalyzerMinute(selectedId, minuteDate, minuteSymbols),
    enabled: !!selectedTheme && !selectedTheme.source_error && !!minuteDate && minuteSymbols.length > 0,
    staleTime: 120_000,
    refetchOnWindowFocus: false,
  })

  useEffect(() => {
    if (!analysis) return
    const context = `${analysis.theme_id}:${analysis.window_start}:${analysis.window_end}:${poolKey}`
    if (lastMinuteTheme.current === context) return
    lastMinuteTheme.current = context
    const defaults = analysis.leaders.slice(0, Math.min(MAX_MINUTE_STOCKS, analysis.leaders.length)).map(leader => leader.symbol)
    setMinuteSymbols(defaults)
    setMinuteDate(analysis.latest_minute_date ?? analysis.minute_dates[analysis.minute_dates.length - 1] ?? '')
  }, [analysis, poolKey])

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
        current => ({
          items: [theme, ...(current?.items ?? []).filter(item => item.id !== theme.id)],
        }),
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
        current => ({
          items: (current?.items ?? []).filter(theme => theme.id !== themeId),
        }),
      )
      if (selectedId === themeId) setSelectedId('')
      void queryClient.invalidateQueries({ queryKey: QK.themeAnalyzerThemes })
    },
    onError: error => toast(errorText(error)),
  })
  const addStockMutation = useMutation({
    mutationFn: ({ id, symbol }: { id: string; symbol: string }) => api.themeAnalyzerAddStocks(id, [symbol]),
    onSuccess: theme => {
      toast('已加入股票池', 'success')
      invalidateTheme(theme.id)
    },
    onError: error => toast(errorText(error)),
  })
  const removeStockMutation = useMutation({
    mutationFn: ({ id, symbol }: { id: string; symbol: string }) => api.themeAnalyzerRemoveStock(id, symbol),
    onSuccess: theme => {
      toast('已从主题移除', 'success')
      invalidateTheme(theme.id)
    },
    onError: error => toast(errorText(error)),
  })

  const stockBusy = addStockMutation.isPending || removeStockMutation.isPending
  const rangeStartValue = rangeStart || analysis?.window_start || ''
  const rangeEndValue = rangeEnd || analysis?.window_end || ''
  const previewLeader = analysis?.leaders.find(leader => leader.symbol === previewSymbol)
  const previewNav = useMemo(
    () => (analysis?.leaders ?? []).map(leader => ({ symbol: leader.symbol, name: leader.name })),
    [analysis?.leaders],
  )

  const activeLeaders = (analysis?.leaders ?? []).filter(leader => leader.active)
  const spaceLeader = (analysis?.leaders ?? []).find(leader => leader.max_ret_30 != null)
  const currentLeader = [...(analysis?.leaders ?? [])]
    .filter(leader => leader.latest_ret_3 != null)
    .sort((left, right) => (right.latest_ret_3 ?? -Infinity) - (left.latest_ret_3 ?? -Infinity))[0]
  const weakCount = activeLeaders.filter(leader => (leader.latest_ret_3 ?? 0) < 0).length

  const openPreview = (symbol: string, name: string) => {
    setPreviewSymbol(symbol)
    setPreviewName(name)
  }

  const handleDeleteTheme = (theme: ThemeAnalyzerTheme) => {
    if (!window.confirm(`删除主题「${theme.name}」？股票池会一并删除，行情数据不受影响。`)) return
    deleteMutation.mutate(theme.id)
  }

  const toggleMinuteSymbol = (symbol: string) => {
    setMinuteSymbols(current => {
      if (current.includes(symbol)) {
        return current.length <= 1 ? current : current.filter(item => item !== symbol)
      }
      if (current.length >= MAX_MINUTE_STOCKS) {
        toast(`分钟叠加最多选择 ${MAX_MINUTE_STOCKS} 只`, 'error')
        return current
      }
      return [...current, symbol]
    })
  }

  const focusMinuteDay = (day: string, symbols: string[]) => {
    if (!analysis?.minute_dates.includes(day)) {
      toast('该日无分钟数据', 'error')
      return
    }
    setMinuteDate(day)
    setMinuteSymbols(current => {
      const next = [...new Set(symbols.filter(Boolean))].slice(0, MAX_MINUTE_STOCKS)
      return next.length > 0 ? next : current
    })
    requestAnimationFrame(() => {
      minuteLabRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-base">
      <PageHeader
        title="主题分析"
        subtitle="自建主题 · 涨停接力路线 · 3/10/30 日空间 · 切换日分钟叠加"
        right={
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => {
                setEditingTheme(selectedTheme)
                setEditorOpen(true)
              }}
              className="rounded-btn border border-border px-2.5 py-1.5 text-[11px] text-accent hover:bg-surface"
            >
              关联产业链
            </button>
            <button
              type="button"
              onClick={() => {
                void themesQuery.refetch()
                void analysisQuery.refetch()
                void minuteQuery.refetch()
              }}
              disabled={analysisQuery.isFetching || minuteQuery.isFetching}
              className="rounded-btn p-1.5 text-muted hover:bg-surface hover:text-foreground disabled:opacity-40"
              title="刷新"
            >
              <RefreshCw size={15} className={cn((analysisQuery.isFetching || minuteQuery.isFetching) && 'animate-spin')} />
            </button>
            <button
              type="button"
              onClick={() => {
                setEditingTheme(null)
                setEditorOpen(true)
              }}
              className="inline-flex items-center gap-1.5 rounded-btn border border-border bg-surface px-2.5 py-1.5 text-[11px] text-secondary hover:border-accent/35 hover:text-accent"
            >
              <Plus size={13} /> 新建主题
            </button>
          </div>
        }
      />

      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[268px_minmax(0,1fr)]">
        <aside className="max-h-56 min-h-0 border-b border-border bg-surface/70 lg:max-h-none lg:border-b-0 lg:border-r">
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

        <main className="min-h-0 overflow-y-auto bg-[radial-gradient(circle_at_10%_0%,rgba(245,158,11,0.10),transparent_27%),radial-gradient(circle_at_88%_4%,rgba(34,211,238,0.07),transparent_26%)]">
          <div className="mx-auto max-w-[1760px] space-y-4 px-4 py-4 lg:px-6 lg:py-5">
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
              <EmptyState
                icon={Tags}
                title="先创建一个主题"
                hint="主题是股票池的容器。创建后可以搜索股票并持续增删，页面会自动按同一口径重算。"
              />
            ) : selectedTheme.source_error ? (
              <div className="rounded-2xl border border-danger/30 bg-danger/5 p-6">
                <p className="text-sm text-danger">{selectedTheme.source_error}</p>
                <button type="button" onClick={() => { setEditingTheme(selectedTheme); setEditorOpen(true) }} className="mt-3 text-xs text-accent">重新选择股票池来源</button>
              </div>
            ) : !analysisQuery.isLoading && analysis && analysis.pool_count === 0 ? (
              <div className="space-y-4">
                <div className="rounded-2xl border border-border bg-surface p-5" style={{ background: `linear-gradient(135deg, ${selectedTheme.color}14, transparent 55%)` }}>
                  <div className="flex items-center gap-3">
                    <span className="h-3 w-3 rounded-full" style={{ backgroundColor: selectedTheme.color }} />
                    <h2 className="text-lg font-semibold text-foreground">{selectedTheme.name}</h2>
                  </div>
                  <p className="mt-2 text-xs leading-5 text-secondary">{selectedTheme.description || '还没有说明'}</p>
                  {selectedTheme.source_name && <p className="mt-2 text-xs text-accent">动态关联：{selectedTheme.source_name} · 当前关联范围暂无有效股票</p>}
                  <div className="mt-4 max-w-xl"><StockSearch theme={selectedTheme} busy={stockBusy} onAdd={symbol => addStockMutation.mutate({ id: selectedTheme.id, symbol })} /></div>
                  {!!selectedTheme.excluded_symbols?.length && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {selectedTheme.excluded_symbols.map(symbol => (
                        <button key={symbol} type="button" disabled={stockBusy} onClick={() => addStockMutation.mutate({ id: selectedTheme.id, symbol })} className="rounded border border-border px-2 py-1 text-xs text-accent">恢复 {symbol}</button>
                      ))}
                    </div>
                  )}
                </div>
                <EmptyState icon={Plus} title="股票池为空" hint="搜索代码或名称，加入第一只股票后开始分析。" />
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
                <Loader2 size={18} className="animate-spin text-accent" /> 计算窗口峰值与主动性
              </div>
            ) : (
              <>
                <section
                  className="relative overflow-hidden rounded-2xl border border-border bg-surface/92 p-4 lg:p-5"
                  style={{ background: `linear-gradient(130deg, ${selectedTheme.color}18, transparent 48%)` }}
                >
                  <div className="pointer-events-none absolute -right-16 -top-20 h-56 w-56 rounded-full border border-white/5 bg-white/[0.02]" />
                  <div className="relative flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: selectedTheme.color }} />
                        <h2 className="text-lg font-semibold tracking-tight text-foreground">{selectedTheme.name}</h2>
                        <span className="rounded-full border border-border bg-base/40 px-2 py-0.5 font-mono text-[9px] text-muted">
                          {analysis.window_start} → {analysis.window_end}
                        </span>
                      </div>
                      <p className="mt-2 max-w-2xl text-xs leading-5 text-secondary">{selectedTheme.description || '未填写主题说明'}</p>
                      {(selectedTheme.source_name || selectedTheme.source_error) && (
                        <p className={cn('mt-2 text-xs', selectedTheme.source_error ? 'text-danger' : 'text-accent')}>
                          {selectedTheme.source_error ?? `动态关联：${selectedTheme.source_name} · 关联股 ${selectedTheme.inherited_symbols?.length ?? 0} 只 · 手动股 ${selectedTheme.manual_symbols?.length ?? 0} 只`}
                        </p>
                      )}
                      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[10px] text-muted">
                        <span className="inline-flex items-center gap-1"><Layers3 size={12} /> 池 {analysis.pool_count}</span>
                        <span className="inline-flex items-center gap-1"><Flame size={12} className="text-amber-400" /> 活跃 {analysis.active_count}</span>
                        <span className="inline-flex items-center gap-1"><Activity size={12} /> 有行情 {analysis.quoted_count}</span>
                        <span className="inline-flex items-center gap-1"><Clock3 size={12} /> 分钟截至 {analysis.latest_minute_date ?? '—'}</span>
                      </div>
                      <div className="mt-4 flex max-w-2xl flex-wrap items-center gap-2">
                        <StockSearch
                          theme={selectedTheme}
                          busy={stockBusy}
                          onAdd={symbol => addStockMutation.mutate({ id: selectedTheme.id, symbol })}
                        />
                        <DatePicker value={rangeStartValue} onChange={setRangeStart} max={rangeEndValue || analysis.window_end} buttonClassName="h-9 text-[11px]" placeholder="窗口开始" />
                        <span className="text-[10px] text-muted">至</span>
                        <DatePicker value={rangeEndValue} onChange={setRangeEnd} min={rangeStartValue || undefined} buttonClassName="h-9 text-[11px]" placeholder="窗口结束" />
                        {(rangeStart || rangeEnd) && (
                          <button
                            type="button"
                            onClick={() => {
                              setRangeStart('')
                              setRangeEnd('')
                            }}
                            className="rounded-btn border border-border px-2.5 py-1.5 text-[10px] text-muted hover:text-foreground"
                          >
                            恢复默认窗口
                          </button>
                        )}
                      </div>
                    </div>
                    <div className="flex shrink-0 flex-wrap items-center gap-1.5">
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

                <div className="grid grid-cols-2 gap-2.5 md:grid-cols-3 xl:grid-cols-6">
                  <StatCard label="主题池" value={analysis.pool_count} hint={`${analysis.quoted_count} 只有行情`} icon={Layers3} />
                  <StatCard label="活跃标的" value={analysis.active_count} hint="窗口内出现过涨停/炸板" icon={Flame} tone="accent" />
                  <StatCard label="主题池涨幅" value={fmtPct(analysis.pool_return, 1)} hint="等权，窗口起点=100" icon={TrendingUp} tone={(analysis.pool_return ?? 0) >= 0 ? 'up' : 'down'} />
                  <StatCard label="活跃等权涨幅" value={fmtPct(analysis.active_return, 1)} hint="仅窗口内活跃标的" icon={Sparkles} tone={(analysis.active_return ?? 0) >= 0 ? 'up' : 'down'} />
                  <StatCard label="上证同期" value={fmtPct(analysis.sh_return, 1)} hint="000001.SH" icon={Activity} tone={(analysis.sh_return ?? 0) >= 0 ? 'up' : 'down'} />
                  <StatCard label="最新封板率" value={analysis.seal.seal_rate == null ? '—' : `${(analysis.seal.seal_rate * 100).toFixed(1)}%`} hint={`封 ${analysis.seal.sealed_count} / 炸 ${analysis.seal.broken_count}`} icon={ShieldAlert} />
                </div>

                <div className="grid gap-3 md:grid-cols-3">
                  <InsightCard
                    title="空间龙头"
                    icon={Crown}
                    name={spaceLeader?.name ?? '—'}
                    value={fmtPct(spaceLeader?.max_ret_30, 1)}
                    detail={spaceLeader ? `30日峰值 ${spaceLeader.max_ret_30_date ?? '—'}；跑赢基准>2% ${spaceLeader.active_gt2} 天` : '窗口样本不足'}
                    tone="accent"
                  />
                  <InsightCard
                    title="当前3日最强"
                    icon={ArrowUpRight}
                    name={currentLeader?.name ?? '—'}
                    value={fmtPct(currentLeader?.latest_ret_3, 1)}
                    detail={currentLeader ? `当前3日涨幅 / 30日峰值 ${fmtPct(currentLeader.max_ret_30, 1)}` : '暂无当前3日数据'}
                    tone="up"
                  />
                  <InsightCard
                    title="退潮风险"
                    icon={AlertTriangle}
                    name={weakCount ? `${weakCount} 只转负` : '暂未转负'}
                    value={weakCount ? `${((weakCount / Math.max(1, activeLeaders.length)) * 100).toFixed(0)}%` : '0%'}
                    detail={`${activeLeaders.length} 只活跃标的中 ${weakCount} 只当前3日为负`}
                    tone={weakCount ? 'down' : 'accent'}
                  />
                </div>

                <LimitRouteMap
                  key={`${analysis.theme_id}:${analysis.window_start}:${analysis.window_end}`}
                  data={analysis.limit_route}
                  stockSegments={selectedTheme.stock_segments}
                  onFocusDay={focusMinuteDay}
                  onSelectStock={openPreview}
                />

                <div ref={minuteLabRef} className="scroll-mt-4">
                  <MinuteLab
                    analysis={analysis}
                    stockSegments={selectedTheme.stock_segments}
                    minuteDate={minuteDate}
                    onDateChange={setMinuteDate}
                    selectedSymbols={minuteSymbols}
                    onToggleSymbol={toggleMinuteSymbol}
                    minute={minuteQuery.data}
                    loading={minuteQuery.isLoading}
                    error={minuteQuery.error}
                    onRetry={() => void minuteQuery.refetch()}
                  />
                </div>

                <div className="grid gap-4 xl:grid-cols-[1.25fr_0.75fr]">
                  <SectionCard title="整波路径" hint="活跃等权 / 主题池等权 / 上证指数，窗口起点归一为 100">
                    <div className="p-2 pt-0">
                      <ThemeTrendChart analysis={analysis} height={320} />
                    </div>
                  </SectionCard>
                  <SectionCard title="空间 vs 当下" hint="横轴当前3日，纵轴30日最大；气泡大小=跑赢天数；点击圆点打开个股">
                    <div className="p-2 pt-0">
                      <ThemeQuadrantChart leaders={analysis.leaders} height={320} onSelect={symbol => {
                        const leader = analysis.leaders.find(item => item.symbol === symbol)
                        openPreview(symbol, leader?.name ?? symbol)
                      }} />
                    </div>
                  </SectionCard>
                </div>

                <WindowTable
                  leaders={analysis.leaders}
                  activeOnly={activeOnly}
                  onToggleActive={() => setActiveOnly(value => !value)}
                  onSelect={openPreview}
                />

                <HeatmapTable
                  analysis={analysis}
                  showAll={showAllHeatmap}
                  onToggle={() => setShowAllHeatmap(value => !value)}
                  onSelect={openPreview}
                />

                <div className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
                  <StockPool
                    theme={selectedTheme}
                    analysis={analysis}
                    busy={stockBusy}
                    onAdd={symbol => addStockMutation.mutate({ id: selectedTheme.id, symbol })}
                    onRemove={symbol => removeStockMutation.mutate({ id: selectedTheme.id, symbol })}
                    onSelect={openPreview}
                  />
                  <SealStructure analysis={analysis} onSelect={openPreview} />
                </div>

                <p className="pb-2 text-[9px] leading-5 text-muted">
                  仅基于本地日线、分钟线与涨停/炸板扩展数据，不构成投资建议。3/10/30 日最大涨幅回答“这一波最多涨过多少”，当前3日回答“现在还剩多少”；20% 涨跌幅板块与 10% 板块的涨幅不可直接横比。
                </p>
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
          if (editingTheme) {
            updateMutation.mutate({ id: editingTheme.id, payload })
          } else {
            createMutation.mutate(payload)
          }
        }}
      />
      <StockPreviewDialog
        symbol={previewSymbol}
        name={previewName || previewLeader?.name}
        navList={previewNav}
        onNavigate={(symbol, name) => {
          setPreviewSymbol(symbol)
          setPreviewName(name ?? '')
        }}
        onClose={() => setPreviewSymbol(null)}
      />
    </div>
  )
}

