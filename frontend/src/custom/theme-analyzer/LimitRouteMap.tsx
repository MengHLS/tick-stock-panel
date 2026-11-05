import { useMemo, useRef, useState } from 'react'
import {
  ArrowRight,
  Crown,
  Flame,
  Radio,
  Sparkles,
  Timer,
  TrendingUp,
  Zap,
} from 'lucide-react'
import type {
  ThemeAnalyzerLimitRoute,
  ThemeAnalyzerLimitRouteRow,
  ThemeAnalyzerSwitchDay,
} from '@/lib/api'
import { cn } from '@/lib/cn'
import { fmtBigNum, fmtPct } from '@/lib/format'

function routeColor(index: number) {
  const hue = (18 + index * 137.508) % 360
  const lightness = 52 + (index % 3) * 4
  return `hsl(${hue.toFixed(1)} 74% ${lightness}%)`
}

function shortDate(day: string) {
  return day.slice(5).replace('-', '/')
}

function compactTime(value: string | null | undefined) {
  return value && value !== '—' ? value.slice(0, 5) : '—'
}

function switchTone(label: string) {
  if (label.includes('领涨切换')) return 'border-amber-400/35 bg-amber-400/[0.06]'
  if (label.includes('龙头涨幅峰值')) return 'border-rose-400/35 bg-rose-400/[0.06]'
  if (label.includes('补涨')) return 'border-yellow-300/30 bg-yellow-300/[0.05]'
  if (label.includes('启动')) return 'border-cyan-400/30 bg-cyan-400/[0.05]'
  if (label.includes('分歧')) return 'border-emerald-400/25 bg-emerald-400/[0.04]'
  return 'border-border bg-base/35'
}

function RouteMetric({
  label,
  value,
  detail,
  icon: Icon,
  tone = 'neutral',
}: {
  label: string
  value: string
  detail: string
  icon: typeof Crown
  tone?: 'neutral' | 'up' | 'accent'
}) {
  return (
    <div className="rounded-xl border border-border/70 bg-base/35 px-3 py-2.5">
      <div className="flex items-center gap-1.5 text-[9px] text-muted">
        <Icon size={11} className={tone === 'accent' ? 'text-amber-400' : tone === 'up' ? 'text-bull' : ''} />
        {label}
      </div>
      <div className={cn(
        'mt-1 truncate text-[12px] font-semibold',
        tone === 'accent' ? 'text-amber-300' : tone === 'up' ? 'text-bull' : 'text-foreground',
      )}>
        {value}
      </div>
      <div className="mt-0.5 truncate font-mono text-[8px] text-muted">{detail}</div>
    </div>
  )
}

type RouteDensity = 'overview' | 'comfort' | 'large'

const DENSITY = {
  overview: { labelWidth: 150, dateWidth: 0 },
  comfort: { labelWidth: 210, dateWidth: 34 },
  large: { labelWidth: 260, dateWidth: 46 },
} as const

function RouteCell({
  row,
  date,
  event,
  isLeader,
  isSwitch,
  density,
  color,
  onFocus,
}: {
  row: ThemeAnalyzerLimitRouteRow
  date: string
  event: ThemeAnalyzerLimitRouteRow['events'][number] | undefined
  isLeader: boolean
  isSwitch: boolean
  density: RouteDensity
  color: string
  onFocus: () => void
}) {
  const overview = density === 'overview'
  const large = density === 'large'
  const cellHeight = overview ? 'h-7' : density === 'comfort' ? 'h-9' : 'h-11'
  if (!event) {
    return (
      <td className={cn(cellHeight, 'border-b border-border/25 p-0 text-center', isSwitch && 'bg-amber-400/[0.035]')}>
        {isLeader && <Crown size={9} className="mx-auto text-amber-300/60" />}
      </td>
    )
  }

  const detail = event.type === 'seal'
    ? `${event.consec || 1}板 · ${event.reason || '封板'}`
    : `炸板 · ${event.reason || '分歧'}`
  const title = [
    date,
    row.name,
    `${compactTime(event.first_time)} ${detail}`,
    event.money ? `封单 ${fmtBigNum(event.money)}` : null,
    event.catch_up ? '龙头涨幅峰值后首次封板（补涨新人）' : null,
    event.relay ? '龙头涨幅峰值后继续封板（接力）' : null,
  ].filter(Boolean).join(' · ')

  return (
    <td className={cn(cellHeight, 'border-b border-border/25 p-0 text-center align-middle', isSwitch && 'bg-amber-400/[0.035]')}>
      <button
        type="button"
        onClick={onFocus}
        title={title}
        className="group flex h-full w-full flex-col items-center justify-center gap-0.5 outline-none"
      >
        <span className={cn('relative inline-flex h-4 items-center justify-center', overview ? 'w-full' : 'min-w-4')}>
          <span
            className={cn('absolute rounded-sm opacity-20', overview ? 'inset-x-0 top-1/2 h-1 -translate-y-1/2' : '-left-1 -right-1 top-1/2 h-px -translate-y-1/2')}
            style={{ backgroundColor: color }}
          />
          {event.type === 'seal' ? (
            <span className={cn(
              'relative inline-flex items-center justify-center font-bold leading-none text-white ring-1 ring-inset ring-white/35',
              overview
                ? 'h-3.5 w-full max-w-[17px] rounded-sm text-[8px]'
                : large
                  ? 'h-5 min-w-5 rounded-full px-1 text-[10px]'
                  : 'h-4 min-w-4 rounded-full px-0.5 text-[9px]',
              event.catch_up && 'ring-2 ring-amber-100/90',
              !overview && event.opens && 'outline outline-1 outline-offset-1 outline-rose-300/40',
            )} style={{ backgroundColor: color }}>
              {event.consec || 1}
            </span>
          ) : (
            <span className={cn(
              'relative inline-flex items-center justify-center border border-dashed bg-base font-bold',
              overview
                ? 'h-4 w-full max-w-[18px] rounded-sm text-[8px]'
                : large
                  ? 'h-5 min-w-5 rounded-full text-[9px]'
                  : 'h-4 min-w-4 rounded-full text-[8px]',
            )} style={{ borderColor: color, color }}>
              {large ? '炸' : '×'}
            </span>
          )}
          {isLeader && (
            <Crown
              size={overview ? 6 : large ? 8 : 7}
              className={cn('absolute -top-1.5 text-amber-300 drop-shadow', overview ? 'left-1/2 -translate-x-1/2' : large ? '-right-2' : '-right-1.5')}
            />
          )}
        </span>
        {!overview && <span className={cn('block font-mono leading-none tabular-nums', large ? 'text-[9px]' : 'text-[8px]')} style={{ color }}>
          {compactTime(event.first_time)}
        </span>}
      </button>
    </td>
  )
}

export function LimitRouteMap({
  data,
  stockSegments,
  onFocusDay,
  onSelectStock,
}: {
  data: ThemeAnalyzerLimitRoute
  stockSegments?: Record<string, string[]>
  onFocusDay: (day: string, symbols: string[]) => void
  onSelectStock: (symbol: string, name: string) => void
}) {
  const [activeDate, setActiveDate] = useState('')
  const [density, setDensity] = useState<RouteDensity>('comfort')
  const tableScrollRef = useRef<HTMLDivElement>(null)
  const topScrollRef = useRef<HTMLDivElement>(null)
  const sizing = DENSITY[density]
  const scrollable = density !== 'overview'
  const tableWidth = sizing.labelWidth + data.dates.length * sizing.dateWidth
  const dateLabelStep = Math.max(1, Math.ceil(data.dates.length / 10))
  const dateIndex = useMemo(
    () => new Map(data.dates.map((day, index) => [day, index])),
    [data.dates],
  )
  const colorBySymbol = useMemo(
    () => new Map(data.rows.map((row, index) => [row.symbol, routeColor(index)])),
    [data.rows],
  )
  const stockColor = (symbol: string) => colorBySymbol.get(symbol) ?? '#94A3B8'
  const switchByDate = useMemo(
    () => new Map(data.switch_days.map(day => [day.date, day])),
    [data.switch_days],
  )
  const leaderByDate = useMemo(
    () => new Map(data.daily_leaders.map(leader => [leader.date, leader])),
    [data.daily_leaders],
  )
  const phases = useMemo(() => {
    const segments: Array<{ kind: 'phase'; phase: (typeof data.leader_phases)[number]; span: number } | { kind: 'gap'; span: number }> = []
    let cursor = 0
    data.leader_phases.forEach(phase => {
      const start = dateIndex.get(phase.start)
      const end = dateIndex.get(phase.end)
      if (start == null || end == null || end < start) return
      if (start > cursor) segments.push({ kind: 'gap', span: start - cursor })
      segments.push({ kind: 'phase', phase, span: end - start + 1 })
      cursor = end + 1
    })
    if (cursor < data.dates.length) {
      segments.push({ kind: 'gap', span: data.dates.length - cursor })
    }
    return segments
  }, [data.dates.length, data.leader_phases, dateIndex])

  const firstStarter = data.rows[0]
  const currentLeader = data.daily_leaders[data.daily_leaders.length - 1]
  const spaceLeader = data.rows.find(row => row.symbol === data.space_leader_symbol)
  const catchUpCount = data.rows.reduce(
    (count, row) => count + row.events.filter(event => event.catch_up).length,
    0,
  )
  const relayCount = data.rows.reduce(
    (count, row) => count + row.events.filter(event => event.relay).length,
    0,
  )
  const keySwitchDays = [...data.switch_days].reverse()

  const focusDay = (day: string, symbols: string[], fallbackSymbol?: string) => {
    setActiveDate(day)
    const fallback = fallbackSymbol ? [fallbackSymbol] : []
    onFocusDay(day, [...new Set([...fallback, ...symbols].filter(Boolean))].slice(0, 8))
  }

  const focusSwitchDay = (day: ThemeAnalyzerSwitchDay) => {
    if (!day.has_minute) return
    focusDay(day.date, day.minute_symbols, day.daily_leader ?? undefined)
  }

  return (
    <section className="overflow-hidden rounded-2xl border border-border bg-surface/92">
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-border/70 px-4 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Zap size={15} className="text-amber-400" />
            <h2 className="text-sm font-semibold text-foreground">涨停接力路线</h2>
            <span className="rounded-full border border-amber-400/20 bg-amber-400/[0.06] px-1.5 py-0.5 font-mono text-[8px] text-amber-300">
              {data.rows.length} 只封过板
            </span>
          </div>
          <p className="mt-1 text-[10px] leading-4 text-muted">
            按窗口内首次封板排序；连板高度优先、首封时间其次识别当日领涨。点击节点或切换日，叠加前任领涨、接力股和空间龙头分时。
          </p>
          <p className="mt-1 text-[10px] leading-4 text-muted">
            金圈为龙头 30 日涨幅峰值后首次封板的新人；峰值后继续封板标为接力。涨幅峰值不等于股价见顶，补涨关系需结合当日分时确认。
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[9px] text-muted">
          <span className="inline-flex items-center gap-1">
            <i className="h-2 w-2 rounded-full" style={{ background: 'conic-gradient(from 0deg, #F59E0B, #22D3EE, #A78BFA, #FB7185, #F59E0B)' }} /> 封板（实心=股票色）
          </span>
          <span className="inline-flex items-center gap-1"><i className="h-2 w-2 rounded-full border border-dashed border-muted" /> 炸板（虚线=股票色）</span>
          <span className="inline-flex items-center gap-1"><i className="h-2 w-2 rounded-full bg-rose-500 ring-2 ring-amber-100" /> 补涨新人</span>
          <span className="inline-flex items-center gap-1"><Crown size={9} className="text-amber-300" /> 当日领涨</span>
          <span className="inline-flex items-center gap-1"><i className="h-1 w-4 rounded-full bg-[linear-gradient(90deg,#F59E0B,#22D3EE,#A78BFA,#FB7185)]" /> 股票色=首封顺序</span>
        </div>
      </header>

      <div className="grid grid-cols-2 gap-2 border-b border-border/60 p-3 lg:grid-cols-5">
        <RouteMetric
          label="窗口内最早封板"
          value={firstStarter ? firstStarter.name : '—'}
          detail={firstStarter ? `${firstStarter.first_seal_date ?? firstStarter.first_date ?? '—'} ${firstStarter.first_time}` : '窗口内无封板'}
          icon={Radio}
          tone="up"
        />
        <RouteMetric
          label="最近封板日领涨"
          value={currentLeader?.name ?? '—'}
          detail={currentLeader ? `${currentLeader.date} · ${currentLeader.consec || 1}板 · ${currentLeader.first_time}` : '暂无连续封板'}
          icon={Crown}
          tone="accent"
        />
        <RouteMetric
          label="空间龙头"
          value={data.space_leader_name ?? spaceLeader?.name ?? '—'}
          detail={spaceLeader ? `30日 ${fmtPct(spaceLeader.max_ret_30, 1)} · 峰值 ${spaceLeader.max_ret_30_date ?? '—'}` : '样本不足'}
          icon={TrendingUp}
          tone="accent"
        />
        <RouteMetric
          label="峰值后新人补涨"
          value={catchUpCount ? `${catchUpCount} 次首封` : '暂未出现'}
          detail={data.space_leader_peak_date ? `峰值后接力 ${relayCount} 次 · ${data.space_leader_peak_date}` : '尚无龙头峰值日'}
          icon={Sparkles}
        />
        <RouteMetric
          label="路线事件"
          value={`${data.seal_count} 次封板`}
          detail={`封板 + 炸板共 ${data.event_count} 次`}
          icon={Radio}
        />
      </div>

      {data.rows.length === 0 ? (
        <div className="px-5 py-12 text-center">
          <Flame size={22} className="mx-auto text-muted/60" />
          <p className="mt-2 text-xs text-secondary">当前窗口内没有已封板标的</p>
          <p className="mt-1 text-[10px] text-muted">放宽日期窗口，或确认本地涨停扩展数据已覆盖该区间。</p>
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/70 px-3 py-2">
            <div className="text-[11px] text-secondary">
              {data.dates[0]} → {data.dates[data.dates.length - 1]}
              <span className="ml-2 text-muted">共 {data.dates.length} 个交易日 · {data.rows.length} 只股票全部展示</span>
            </div>
            <div className="flex items-center gap-2">
              {scrollable && (
                <>
                  <button type="button" onClick={() => tableScrollRef.current?.scrollTo({ left: 0 })} className="rounded px-2 py-1 text-[11px] text-secondary hover:bg-elevated">回到启动</button>
                  <button type="button" onClick={() => tableScrollRef.current?.scrollTo({ left: tableScrollRef.current.scrollWidth })} className="rounded px-2 py-1 text-[11px] text-accent hover:bg-elevated">跳到最新</button>
                </>
              )}
              <div className="flex rounded-btn border border-border bg-base/60 p-0.5">
                {([
                  ['overview', '全貌'],
                  ['comfort', '标准'],
                  ['large', '放大'],
                ] as const).map(([mode, label]) => (
                  <button
                    key={mode}
                    type="button"
                    aria-pressed={density === mode}
                    onClick={() => {
                      setDensity(mode)
                      if (tableScrollRef.current) tableScrollRef.current.scrollLeft = 0
                      if (topScrollRef.current) topScrollRef.current.scrollLeft = 0
                    }}
                    className={cn('rounded px-2.5 py-1 text-[11px]', density === mode ? 'bg-accent/15 text-accent' : 'text-muted hover:text-foreground')}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <p className="w-full text-[10px] text-muted">
              {density === 'overview'
                ? '全貌在同一屏宽内展示完整日期；格内数字为连板高度，× 为炸板。悬停查看首封时间，点击查看分时。'
                : density === 'comfort'
                  ? '标准视图放大单格并显示首封时间，可横向滚动；需要更大字号时切换“放大”。'
                  : '放大视图使用最大单元格和首封时间，适合逐个切换节点复盘。'}
            </p>
          </div>
          {scrollable && (
            <div
              ref={topScrollRef}
              aria-label="路线日期横向滚动条"
              className="overflow-x-auto"
              onScroll={event => {
                if (tableScrollRef.current) tableScrollRef.current.scrollLeft = event.currentTarget.scrollLeft
              }}
            >
              <div style={{ width: tableWidth, height: 1 }} />
            </div>
          )}
          <div
            ref={tableScrollRef}
            className={scrollable ? 'overflow-x-auto' : 'w-full'}
            onScroll={event => {
              if (topScrollRef.current) topScrollRef.current.scrollLeft = event.currentTarget.scrollLeft
            }}
          >
            <table
              className="table-fixed border-separate border-spacing-0 text-[10px]"
              aria-label={density === 'overview' ? '涨停接力路线全貌' : density === 'large' ? '涨停接力路线放大' : '涨停接力路线标准'}
              style={scrollable ? { width: tableWidth, minWidth: tableWidth } : { width: '100%' }}
            >
              <colgroup>
                <col style={{ width: sizing.labelWidth }} />
                {data.dates.map(day => <col key={day} style={scrollable ? { width: sizing.dateWidth } : undefined} />)}
              </colgroup>
              <thead>
                <tr>
                  <th className="sticky left-0 top-0 z-30 border-b border-r border-border bg-surface px-3 py-2 text-left font-medium text-muted">
                    股票 / 首次封板
                  </th>
                  {data.dates.map((day, index) => {
                    const leader = leaderByDate.get(day)
                    const isSwitch = switchByDate.has(day)
                    const showDateLabel = scrollable || index % dateLabelStep === 0 || index === data.dates.length - 1
                    return (
                      <th
                        key={day}
                        title={`${day}${leader ? ` · 领涨 ${leader.name}` : ''}${isSwitch ? ' · 切换节点' : ''}`}
                        className={cn(
                          'sticky top-0 h-9 border-b border-border bg-surface p-0 text-center font-mono text-[10px] font-normal text-muted',
                          showDateLabel ? 'z-20' : 'z-10',
                          isSwitch && 'bg-amber-400/[0.07] text-amber-200',
                        )}
                      >
                        {showDateLabel && (
                          <span className={cn(
                            'whitespace-nowrap',
                            scrollable ? 'block' : 'absolute top-2 text-[9px]',
                            !scrollable && (index === data.dates.length - 1 ? 'right-0' : index === 0 ? 'left-0' : 'left-1/2 -translate-x-1/2'),
                          )}>{shortDate(day)}</span>
                        )}
                        {(leader || isSwitch) && (
                          <span className={cn('mx-auto block h-0.5 max-w-full rounded-full', scrollable ? 'mt-0.5 w-3' : 'mt-5 w-1', isSwitch ? 'bg-amber-400' : 'bg-rose-400/70')} />
                        )}
                      </th>
                    )
                  })}
                </tr>
                <tr>
                  <th className="sticky left-0 z-20 border-b border-r border-border bg-surface px-3 py-1.5 text-left font-medium text-muted">
                    领涨阶段 <span className="font-normal text-muted/70">（仅封板日）</span>
                  </th>
                  {phases.map((segment, index) => {
                    if (segment.kind === 'gap') {
                      return <td key={`gap-${index}`} colSpan={segment.span} className="border-b border-border/50 bg-base/20" />
                    }
                    const phaseColor = stockColor(segment.phase.symbol)
                    return (
                      <td
                        key={`${segment.phase.symbol}-${segment.phase.start}-${index}`}
                        colSpan={segment.span}
                        className="overflow-hidden border-b border-border/50 px-1 py-1"
                        style={{ background: `${phaseColor}26`, borderLeft: `1px solid ${phaseColor}` }}
                      >
                        <button
                          type="button"
                          onClick={() => {
                            const switchDay = switchByDate.get(segment.phase.end)
                            focusDay(
                              segment.phase.end,
                              switchDay?.minute_symbols ?? [],
                              segment.phase.symbol,
                            )
                          }}
                          className="block h-4 w-full truncate text-left text-[8px] font-medium"
                          style={{ color: phaseColor }}
                          title={`${segment.phase.name} · ${segment.phase.start} → ${segment.phase.end} · ${segment.phase.days} 个封板日`}
                        >
                          {density !== 'overview' || segment.span >= dateLabelStep
                            ? `${segment.phase.name} · ${segment.phase.days}日`
                            : <Crown size={6} className="mx-auto" />}
                        </button>
                      </td>
                    )
                  })}
                </tr>
              </thead>
              <tbody>
                {data.rows.map(row => {
                  const eventsByDate = new Map(row.events.map(event => [event.date, event]))
                  const color = stockColor(row.symbol)
                  return (
                    <tr key={row.symbol} className="group">
                      <th className={cn(
                        'sticky left-0 z-20 border-b border-r border-border/60 bg-surface text-left font-normal',
                        density === 'large' ? 'px-2 py-1' : density === 'comfort' ? 'px-1.5 py-0.5' : 'px-1 py-0.5',
                        activeDate && eventsByDate.has(activeDate) && 'ring-1 ring-inset ring-amber-400/40',
                      )}>
                        <div className="flex items-center gap-1.5">
                          <span className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-border/70 font-mono text-[7px] text-muted">
                            <span className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
                          </span>
                          <button
                            type="button"
                            onClick={() => onSelectStock(row.symbol, row.name)}
                            className="min-w-0 flex-1 truncate text-left text-[12px] font-medium text-secondary hover:text-accent"
                            title={`${row.name} ${row.symbol}`}
                          >
                            {row.name}
                          </button>
                          {row.is_space_leader && (
                            <span className="shrink-0 rounded bg-amber-400/15 px-1 py-0.5 text-[7px] font-semibold text-amber-300">空间龙</span>
                          )}
                        </div>
                        {!!stockSegments?.[row.symbol]?.length && (
                          <div className="truncate pl-5 text-[9px] text-accent" title={stockSegments[row.symbol].join(' / ')}>
                            {stockSegments[row.symbol].join(' / ')}
                          </div>
                        )}
                        {density === 'large' && <div className="mt-0.5 flex items-center gap-1.5 whitespace-nowrap pl-5 font-mono text-[9px] text-muted">
                          <span>{shortDate(row.first_seal_date ?? row.first_date ?? '')} {compactTime(row.first_time)}</span>
                          <span className="text-border">|</span>
                          <span>最高 {row.max_consec || 1}板</span>
                          <span className="text-border">|</span>
                          <span>累计 {row.total_lu}板</span>
                          <span className="text-border">|</span>
                          <span className="text-amber-300/70">30日 {fmtPct(row.max_ret_30, 1)}</span>
                        </div>}
                      </th>
                      {data.dates.map(day => {
                        const event = eventsByDate.get(day)
                        const leader = leaderByDate.get(day)
                        const isSwitch = switchByDate.has(day)
                        return (
                          <RouteCell
                            key={`${row.symbol}-${day}`}
                            row={row}
                            date={day}
                            event={event}
                            isLeader={leader?.symbol === row.symbol}
                            isSwitch={isSwitch}
                            density={density}
                            color={color}
                            onFocus={() => {
                              const switchDay = switchByDate.get(day)
                              focusDay(
                                day,
                                switchDay?.minute_symbols ?? [],
                                row.symbol,
                              )
                            }}
                          />
                        )
                      })}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          <div className="border-t border-border/70 px-3 py-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-1.5 text-[10px] text-muted">
                <ArrowRight size={12} className="text-amber-400" />
                关键切换节点
                <span className="font-mono text-[8px]">{data.switch_days.length}</span>
              </div>
              <span className="text-[10px] text-muted">优先看“领涨切换 / 补涨新人 / 龙头涨幅峰值”</span>
            </div>
            {keySwitchDays.length === 0 ? (
              <p className="mt-2 text-[10px] text-muted">当前窗口还没有可识别的切换节点。</p>
            ) : (
              <div className="mt-2 flex gap-2 overflow-x-auto pb-1">
                {keySwitchDays.map(day => (
                  <button
                    key={`${day.date}-${day.label}`}
                    type="button"
                    disabled={!day.has_minute}
                    onClick={() => focusSwitchDay(day)}
                    className={cn(
                      'min-w-[260px] max-w-[300px] shrink-0 rounded-xl border p-3 text-left transition-colors',
                      switchTone(day.label),
                      day.has_minute ? 'hover:border-accent/45' : 'cursor-not-allowed opacity-55',
                      activeDate === day.date && 'ring-1 ring-amber-300/60',
                    )}
                    title={day.has_minute ? `查看 ${day.date} 日内叠加` : '该日没有本地分钟数据'}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="shrink-0 font-mono text-[11px] text-foreground">{day.date}</span>
                      <span className="rounded-full border border-current/20 px-1.5 py-0.5 text-[9px] text-secondary">{day.label}</span>
                    </div>
                    <div className="mt-1.5 line-clamp-2 min-h-8 text-[11px] leading-4 text-secondary">
                      {day.reason || (day.leader_name ? `${day.leader_name} 领涨` : '封板结构变化')}
                    </div>
                    <div className="mt-1.5 flex items-center gap-2 text-[8px] text-muted">
                      <span>封 {day.sealed.length}</span>
                      <span>炸 {day.broken.length}</span>
                      <span>新 {day.new_starters.length}</span>
                      {day.sealed.some(item => item.catch_up) && (
                        <span className="text-amber-300/80">补 {day.sealed.filter(item => item.catch_up).length}</span>
                      )}
                      {day.leader_name && <span className="truncate text-amber-300/80">{day.leader_name}</span>}
                    </div>
                    <div className="mt-1.5 flex items-center gap-1 text-[8px] text-accent">
                      <Timer size={9} />
                      {day.has_minute ? '看切换日分时' : '无分钟数据'}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </section>
  )
}
