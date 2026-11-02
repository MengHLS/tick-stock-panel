import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, ChevronDown, ChevronRight, ExternalLink, RotateCcw } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { EChartsCandlestick, type ChartMarker, type ChartPriceLine, type ChartRange, type OHLC } from '@/components/EChartsCandlestick'
import { toast } from '@/components/Toast'
import { fmtPct } from '@/lib/format'
import {
  barsUpToD,
  describeEvent,
  describeRule,
  describeScaleCheck,
  futureWindow,
  pctText,
  replayWindow,
  scaleStateLabel,
  toBars,
  type FbBar,
  type FbEvent,
  type FbReplayData,
  type FbSymbol,
} from './firstboardModel'

const DATA_URL = '/research/firstboard/replay-v012.json'

function loadReplay(): Promise<FbReplayData> {
  return fetch(DATA_URL).then(async res => {
    if (!res.ok) throw new Error(`读取冻结材料失败（${res.status}）`)
    return res.json() as Promise<FbReplayData>
  })
}

function toOhlc(bars: FbBar[]): OHLC[] {
  return bars.map(bar => ({ date: bar.date, open: bar.open, high: bar.high, low: bar.low, close: bar.close }))
}

function factorValue(factors: FbEvent['factors_D_close'], key: keyof FbEvent['factors_D_close']): number | null {
  const value = factors[key]
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

/** 因子小图: 只用固定尺度的三条, 避免数字墙 */
function FactorBar({ label, hint, value, display, scale }: {
  label: string
  hint: string
  value: number | null
  display: string
  scale: { min: number; max: number }
}) {
  const ratio = value == null ? 0 : Math.max(0, Math.min(1, (value - scale.min) / (scale.max - scale.min)))
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs font-medium text-foreground">{label}</span>
        <span className="num text-xs text-secondary">{display}</span>
      </div>
      <div className="mt-1 h-2 overflow-hidden rounded-full bg-elevated">
        <div className="h-full rounded-full bg-accent/70" style={{ width: `${(ratio * 100).toFixed(1)}%` }} />
      </div>
      <div className="mt-1 text-[10px] leading-4 text-muted">{hint}</div>
    </div>
  )
}

function StatusChip({ text, tone = 'muted' }: { text: string; tone?: 'muted' | 'warn' }) {
  return (
    <span className={`rounded border px-1.5 py-px text-[10px] ${tone === 'warn'
      ? 'border-amber-400/40 bg-amber-400/10 text-amber-500'
      : 'border-border bg-elevated text-muted'}`}>
      {text}
    </span>
  )
}

export function FirstBoardReplay() {
  const meta = useQuery({ queryKey: ['firstboard-replay', 'v012'], queryFn: loadReplay, staleTime: 300_000 })
  const [code, setCode] = useState<string | null>(null)
  const [eventId, setEventId] = useState<string | null>(null)
  const [rule, setRule] = useState<string | null>(null)
  const [showFuture, setShowFuture] = useState(false)

  const data = meta.data
  const symbol: FbSymbol | null = useMemo(() => {
    if (!data) return null
    return data.symbols.find(s => s.code === (code ?? data.symbols[0]?.code)) ?? data.symbols[0] ?? null
  }, [data, code])

  const eventsOfSymbol = useMemo(
    () => (data && symbol ? data.events.filter(e => e.code === symbol.code) : []),
    [data, symbol],
  )

  const event: FbEvent | null = useMemo(() => {
    if (!eventsOfSymbol.length) return null
    return eventsOfSymbol.find(e => e.event_id === eventId) ?? eventsOfSymbol[eventsOfSymbol.length - 1]
  }, [eventsOfSymbol, eventId])

  const activeRule = rule ?? data?.default_rule ?? null
  const ruleResult = event && activeRule ? event.rules[activeRule] : null
  const bars = useMemo(() => (symbol ? toBars(symbol) : []), [symbol])
  // 历史长图同样截断到 D: 揭示后续之前, D 之后的 K 线/标记/轴范围都不进入历史图
  const longBars = useMemo(() => (event && bars.length ? barsUpToD(bars, event.date) : []), [bars, event])
  const shortBars = useMemo(() => (event && bars.length ? replayWindow(bars, event.date, 90) : []), [bars, event])
  const futureBars = useMemo(() => (event && showFuture && bars.length ? futureWindow(bars, event.date, 20) : []), [bars, event, showFuture])
  const narrative = useMemo(() => (event ? describeEvent(event) : null), [event])
  const ruleText = useMemo(() => describeRule(ruleResult), [ruleResult])
  const scaleInfo = useMemo(() => describeScaleCheck(event?.scale_check), [event])

  const selectSymbol = (nextCode: string) => {
    setCode(nextCode)
    const first = data?.events.filter(e => e.code === nextCode)
    setEventId(first?.[first.length - 1]?.event_id ?? null)
    setShowFuture(false)
  }

  const selectEvent = (nextEventId: string) => {
    setEventId(nextEventId)
    setShowFuture(false)
  }

  const header = (
    <PageHeader
      title="首板回放"
      subtitle="27 个冻结事件 · 4 只开发样本 · 研究材料浏览，不是收益结论"
      className="shrink-0 flex-wrap gap-x-4 gap-y-2 bg-base/95 px-3 lg:px-5"
    />
  )

  if (meta.isLoading) {
    return (
      <div className="flex min-h-full flex-col">
        {header}
        <div className="grid flex-1 place-items-center text-sm text-secondary">正在读取冻结回放材料…</div>
      </div>
    )
  }
  if (meta.isError || !data || !symbol || !event) {
    return (
      <div className="flex min-h-full flex-col">
        {header}
        <div className="mx-auto mt-10 max-w-lg rounded-card border border-danger/40 bg-danger/5 p-4 text-sm text-danger">
          <div className="flex items-center gap-2 font-medium"><AlertTriangle className="h-4 w-4" />回放材料读取失败</div>
          <div className="mt-2 text-xs">{String((meta.error as Error)?.message ?? '无可用的冻结事件')}</div>
          <button
            type="button"
            onClick={() => meta.refetch()}
            className="mt-3 inline-flex items-center gap-1 rounded-btn border border-danger/40 px-2 py-1 text-xs"
          >
            <RotateCcw className="h-3 w-3" />重试
          </button>
        </div>
      </div>
    )
  }

  const longMarkers: ChartMarker[] = longBars
    .filter(bar => bar.firstBoard)
    .map(bar => {
      const inFrozen = data.events.some(e => e.code === symbol.code && e.date === bar.date)
      const selected = bar.date === event.date
      return {
        date: bar.date,
        kind: 'neutral' as const,
        label: selected ? 'D' : inFrozen ? '首板·回放' : '首板',
        above: true,
        color: selected ? '#f59e0b' : inFrozen ? '#3b82f6' : '#94a3b8',
      }
    })

  const longRanges: ChartRange[] = [
    {
      start: shortBars[0]?.date ?? event.date,
      end: event.date,
      label: '短周期窗口',
      color: 'rgba(59,130,246,0.06)',
    },
  ]

  const shortMarkers: ChartMarker[] = []
  if (!scaleInfo.invalidatesJudgment) {
    if (ruleResult?.P_known_at) shortMarkers.push({ date: ruleResult.P_known_at, kind: 'neutral', label: 'P可知', above: false, color: '#8b5cf6' })
    if (ruleResult?.first_break) shortMarkers.push({ date: ruleResult.first_break, kind: 'neutral', label: '首次突破', above: true, color: '#0ea5e9' })
    if (ruleResult?.L_setup_date) shortMarkers.push({ date: ruleResult.L_setup_date, kind: 'neutral', label: 'L', above: false, color: '#10b981' })
  }

  const shortPriceLines: ChartPriceLine[] = []
  if (!scaleInfo.invalidatesJudgment) {
    if (ruleResult?.P != null) shortPriceLines.push({ value: ruleResult.P, label: `P 锚点 ${ruleResult.P}`, color: '#8b5cf6', start: shortBars[0]?.date, end: event.date })
    if (ruleResult?.L_setup != null) shortPriceLines.push({ value: ruleResult.L_setup, label: `L 结构低点 ${ruleResult.L_setup}`, color: '#10b981', start: shortBars[0]?.date, end: event.date })
  }
  shortPriceLines.push({ value: event.raw_close, label: `D 收盘 ${event.raw_close}`, color: '#f59e0b', start: shortBars[0]?.date, end: event.date })

  const futurePriceLines: ChartPriceLine[] = futureBars.length
    ? [{ value: event.raw_close, label: `D 收盘 ${event.raw_close}`, color: '#f59e0b' }]
    : []

  const bgFactors = event.factors_D_minus_1
  const closeFactors = event.factors_D_close
  const outcomeRows = event.outcomes.slice().sort((a, b) => (a.horizon ?? 0) - (b.horizon ?? 0))

  return (
    <div className="flex min-h-full flex-col bg-base">
      {header}
      <main className="grid min-h-0 flex-1 grid-cols-1 gap-3 px-3 pb-4 pt-3 lg:grid-cols-[15rem_minmax(0,1fr)] lg:px-4">
        {/* 左: 股票与历史首板日期导航 */}
        <aside className="space-y-3 lg:overflow-y-auto">
          <section className="rounded-card border border-border bg-surface/70 p-2.5">
            <div className="mb-1.5 text-[11px] font-medium text-secondary">股票（4 只开发样本）</div>
            <div className="space-y-1">
              {data.symbols.map(item => (
                <button
                  key={item.code}
                  type="button"
                  onClick={() => selectSymbol(item.code)}
                  className={`w-full rounded-btn border px-2 py-1.5 text-left text-xs transition-colors ${item.code === symbol.code
                    ? 'border-accent/50 bg-accent/10 text-accent'
                    : 'border-border bg-base text-secondary hover:border-accent/40'}`}
                >
                  <div className="font-medium">{item.name}</div>
                  <div className="mt-0.5 font-mono text-[10px] text-muted">{item.code} · {item.board}</div>
                </button>
              ))}
            </div>
          </section>

          <section className="rounded-card border border-border bg-surface/70 p-2.5">
            <div className="mb-1 flex items-baseline justify-between">
              <span className="text-[11px] font-medium text-secondary">可观测日K区间内首板</span>
              <span className="text-[10px] text-muted">{symbol.first_boards.length} 个</span>
            </div>
            <div className="max-h-[26rem] space-y-0.5 overflow-y-auto pr-0.5">
              {symbol.first_boards.slice().reverse().map(date => {
                const frozen = data.events.find(e => e.code === symbol.code && e.date === date)
                const scaleLabel = frozen ? scaleStateLabel(frozen.scale_check?.state, frozen.scale_check?.judgment) : null
                const active = date === event.date
                return (
                  <button
                    key={date}
                    type="button"
                    onClick={() => frozen ? selectEvent(frozen.event_id) : toast('该首板不在 27 个冻结回放事件内，只标注、不展开判定')}
                    className={`flex w-full items-center justify-between gap-2 rounded px-1.5 py-1 text-left text-[11px] transition-colors ${active
                      ? 'bg-accent/15 text-accent'
                      : frozen ? 'text-secondary hover:bg-elevated' : 'text-muted hover:bg-elevated/60'}`}
                  >
                    <span className="font-mono">{date}</span>
                    <span className="flex items-center gap-1">
                      {scaleLabel && <span className="text-[9px] text-amber-500">{scaleLabel}</span>}
                      <span className={`text-[9px] ${frozen ? 'text-accent/80' : 'text-muted/70'}`}>
                        {frozen ? '冻结回放' : '仅标注'}
                      </span>
                    </span>
                  </button>
                )
              })}
            </div>
            <div className="mt-1.5 text-[10px] leading-4 text-muted">
              长图只标注到当前事件 D 日为止的平台首板；只有 27 个冻结事件带完整判定与后续材料。导航列表覆盖可观测日K区间内全部首板（含 D 之后，仅作事件定位，不进入历史图）。
            </div>
          </section>

          <section className="rounded-card border border-border bg-surface/70 p-2.5 text-[10px] leading-4 text-muted">
            <div className="mb-1 text-[11px] font-medium text-secondary">材料状态</div>
            <div className="flex flex-wrap gap-1">
              <StatusChip text="首板身份未认证" tone="warn" />
              <StatusChip text="amount 未核验" tone="warn" />
              <StatusChip text="右截断不补零" tone="warn" />
              <StatusChip text="复权断裂已报告" />
              <StatusChip text={`分类源 ${data.classification?.schema_version ?? 'v0.1'}`} />
              <StatusChip text="跨尺度事件已标注" />
              <StatusChip text="暂定参考规则" />
            </div>
            <div className="mt-1.5">冻结版本 {data.rule_version}，冻结截断 2026-10-23；不构成收益或策略结论。</div>
          </section>
        </aside>

        {/* 右: 行情为主体, 判断在后, 后续主动展开 */}
        <section className="min-w-0 space-y-3 lg:overflow-y-auto">
          {scaleInfo.tone !== 'muted' && (
            <div className={`rounded-card border p-3 ${scaleInfo.tone === 'danger'
              ? 'border-danger/40 bg-danger/5'
              : 'border-amber-400/40 bg-amber-400/10'}`}>
              <div className={`flex items-center gap-2 text-xs font-medium ${scaleInfo.tone === 'danger' ? 'text-danger' : 'text-amber-500'}`}>
                <AlertTriangle className="h-3.5 w-3.5" />{scaleInfo.title}
              </div>
              <p className="mt-1 text-[11px] leading-5 text-foreground/90">{scaleInfo.summary}</p>
              <p className="mt-1 text-[10px] leading-4 text-foreground/80">公司行动原因：{scaleInfo.causeText}</p>
              {scaleInfo.details.length > 0 && (
                <details className="mt-1">
                  <summary className="cursor-pointer text-[10px] text-muted">核对证据</summary>
                  <ul className="mt-1 space-y-0.5 text-[10px] leading-4 text-muted">
                    {scaleInfo.details.map((item, index) => <li key={index}>{item}</li>)}
                  </ul>
                </details>
              )}
              <p className="mt-1 text-[10px] leading-4 text-muted">
                90日窗口 {event.scale_check?.short_window_start ?? event.scale_check?.window_start} ~ {event.scale_check?.window_end}；
                锚点区间 {event.scale_check?.anchor_window_start ?? event.scale_check?.window_start} ~ {event.scale_check?.window_end}；
                状态 {event.scale_check?.verification}
              </p>
              {event.scale_check?.factor_events?.map(factor => (
                <p key={factor.date} className="mt-0.5 text-[10px] leading-4 text-muted">
                  因子事件 {factor.date}：
                  ex_factor={factor.ex_factor ?? '—'}、
                  dividend={factor.dividend ?? '—'}、
                  bonus={factor.bonus ?? '—'}、
                  prev_close={factor.prev_close ?? '—'}
                  （{factor.source}；{factor.in_short_window ? '90日窗口内' : '仅锚点区间'}；
                  {factor.date !== event.date ? '非 D 日' : 'D 日'}；公告原件未归档）
                </p>
              ))}
              {event.scale_check && event.scale_check.gap_dates.length > 0 && (
                <p className="mt-0.5 text-[10px] leading-4 text-muted">
                  价格台阶日 {event.scale_check.gap_dates.join('、')}
                  {event.scale_check.gap_dates.every(d => d !== event.date) ? '，非 D 日' : '（含 D 日）'}。
                </p>
              )}
              {(event.scale_check?.factor_events?.length ?? 0) > 0 && (
                <p className="mt-0.5 text-[10px] leading-4 text-amber-500">
                  窗口内因子事件未应用到冻结价；跨该日的收益/动量/P-L/位置指标均按未复权序列计算，不能当作已认证复权值。
                </p>
              )}
            </div>
          )}

          <div className="rounded-card border border-border bg-surface p-3">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold text-foreground">{symbol.name}</span>
              <span className="font-mono text-[11px] text-muted">{symbol.code}</span>
              <span className="text-[11px] text-secondary">上市 {symbol.listing_date} · {symbol.board}</span>
              <span className="ml-auto text-[11px] text-secondary">
                当前事件 <span className="font-mono text-foreground">{event.date}</span>
              </span>
            </div>
            <div className="mb-1 text-[11px] text-muted">
              长周期：截至 D 日的可观测日K与首板标注（{longBars.length} 根；D 之后不进入本图，也不参与纵轴缩放）
            </div>
            <EChartsCandlestick data={toOhlc(longBars)} markers={longMarkers} ranges={longRanges} height={300} showMA={false} />
          </div>

          <div className="rounded-card border border-border bg-surface p-3">
            <div className="mb-1 flex flex-wrap items-baseline gap-2">
              <span className="text-[11px] text-muted">短周期：截至 D 日收盘（D 之后数据不进入本图）</span>
              <span className="ml-auto text-[10px] text-muted">{shortBars.length} 根</span>
            </div>
            {scaleInfo.invalidatesJudgment && (
              <p className="mb-1 text-[10px] leading-4 text-danger">
                结构判断已作废：图上不绘制 P/L 参考线与结构标记，避免跨价格台阶误读；P/L 数值仅在上方文字中作为历史材料。
              </p>
            )}
            {shortBars.length > 0 ? (
              <EChartsCandlestick
                data={toOhlc(shortBars)}
                markers={shortMarkers}
                priceLines={shortPriceLines}
                height={340}
                showMA={false}
              />
            ) : (
              <div className="py-10 text-center text-xs text-muted">该事件缺少 D 之前的日K窗口</div>
            )}
          </div>

          {/* 中文简述: 先看行情再理解判断 */}
          {narrative && (
            <div className="grid gap-2 md:grid-cols-3">
              <div className="rounded-card border border-border bg-surface p-3">
                <div className="text-[11px] font-medium text-secondary">背景位置（D-1 收盘）</div>
                <p className="mt-1 text-xs leading-5 text-foreground/90">{narrative.background}</p>
              </div>
              <div className="rounded-card border border-border bg-surface p-3">
                <div className="text-[11px] font-medium text-secondary">近期走势</div>
                <p className="mt-1 text-xs leading-5 text-foreground/90">{narrative.recent}</p>
              </div>
              <div className="rounded-card border border-border bg-surface p-3">
                <div className="text-[11px] font-medium text-secondary">局部事件（D 日）</div>
                <p className="mt-1 text-xs leading-5 text-foreground/90">{narrative.local}</p>
              </div>
            </div>
          )}

          <div className="rounded-card border border-border bg-surface p-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-medium text-foreground">当日判断（参考规则，暂定未定稿）</span>
              <span className="rounded border border-amber-400/40 bg-amber-400/10 px-1.5 py-px text-[10px] text-amber-500">
                {activeRule === data.default_rule ? '默认参考 · 暂定' : `对比口径 ${activeRule}`}
              </span>
              {scaleInfo.invalidatesJudgment && (
                <span className="rounded border border-danger/40 bg-danger/10 px-1.5 py-px text-[10px] text-danger">
                  结构判断作废·待重算
                </span>
              )}
              <span className="text-[10px] text-muted">P/L 是研究里“锚点高点/结构低点”的价格位，不是盈亏</span>
            </div>
            {scaleInfo.invalidatesJudgment && (
              <p className="mt-1.5 rounded border border-danger/30 bg-danger/5 px-2 py-1 text-[11px] leading-5 text-danger">
                该事件锚点 P/L 跨 {event.scale_check?.gap_dates.join('、')} 的价格台阶，下面的规则解释只保留为历史材料，不能作为有效判断。
              </p>
            )}
            <p className="mt-1.5 text-xs leading-5 text-foreground/90">{ruleText.text}</p>
            {ruleText.dates.length > 0 && (
              <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-muted">
                {ruleText.dates.map(item => <span key={item}>{item}</span>)}
              </div>
            )}
            <p className="mt-2 text-[10px] leading-4 text-muted">
              判定只使用 D 日及以前可知的信息；后续结果默认折叠，需要你主动展开。
            </p>
            {event.scale_check?.state === 'NO_GAP_DETECTED' && (
              <p className="mt-1 text-[10px] leading-4 text-muted">
                尺度核对：冻结 CSV 未发现可识别除权台阶；这不等于无除权（UNKNOWN）。
              </p>
            )}
          </div>

          {/* 后续结果: 主动展开 */}
          <div className="rounded-card border border-border bg-surface p-3">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setShowFuture(v => !v)}
                className="inline-flex items-center gap-1 rounded-btn border border-border bg-base px-2.5 py-1 text-xs text-secondary transition-colors hover:border-accent/40 hover:text-accent"
              >
                {showFuture ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                {showFuture ? '收起 D 后走势与结果' : '展开 D 后走势与结果'}
              </button>
              <span className="text-[10px] text-muted">展开的是 D 之后才发生的数据，不参与上面的判断与历史图缩放</span>
            </div>

            {showFuture && (
              <div className="mt-3 space-y-2">
                {futureBars.length > 0 ? (
                  <EChartsCandlestick data={toOhlc(futureBars)} priceLines={futurePriceLines} height={220} showMA={false} />
                ) : (
                  <div className="py-6 text-center text-xs text-muted">D 之后没有可观测的日K（可能已到冻结截断）</div>
                )}
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[34rem] text-xs text-foreground">
                    <thead className="text-left text-secondary">
                      <tr>
                        <th className="px-2 py-1 font-medium">后续可观测日</th>
                        <th className="px-2 py-1 font-medium">区间终点</th>
                        <th className="px-2 py-1 text-right font-medium">收盘变化</th>
                        <th className="px-2 py-1 text-right font-medium">最高价变化</th>
                        <th className="px-2 py-1 text-right font-medium">最低价变化</th>
                        <th className="px-2 py-1 font-medium">状态</th>
                      </tr>
                    </thead>
                    <tbody>
                      {outcomeRows.map(row => (
                        <tr key={`${row.horizon}-${row.horizon_end}`} className="border-t border-border/60">
                          <td className="px-2 py-1 num">{row.horizon ?? '—'}</td>
                          <td className="px-2 py-1 font-mono text-[11px] text-secondary">{row.horizon_end ?? '—'}</td>
                          <td className="px-2 py-1 text-right num">{pctText(row.close_return)}</td>
                          <td className="px-2 py-1 text-right num">{pctText(row.max_high_return)}</td>
                          <td className="px-2 py-1 text-right num">{pctText(row.min_low_return)}</td>
                          <td className="px-2 py-1 text-[10px] text-muted">
                            {row.complete ? '可观测' : '右截断：不补零'}
                            {row.reason ? ` · ${row.reason}` : ''}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="text-[10px] leading-4 text-muted">
                  这些是描述性价格路径，不是可执行收益，也不是回测成交；{event.structural_price_basis}。
                </p>
              </div>
            )}
          </div>

          {/* 少量因子图 + 解释 */}
          <div className="rounded-card border border-border bg-surface p-3">
            <div className="flex flex-wrap items-baseline gap-2">
              <span className="text-xs font-medium text-foreground">影响判断的三个位置/动能指标</span>
              <span className="text-[10px] text-muted">只用固定尺度, 全部原始数字默认折叠</span>
            </div>
            <div className="mt-3 grid gap-4 sm:grid-cols-3">
              <FactorBar
                label="250日位置"
                hint="收盘在近250日最高/最低区间的位置：0=区间最低，1=区间最高；窗口含当日，不是历史最低价。"
                value={factorValue(closeFactors, 'position_250')}
                display={factorValue(closeFactors, 'position_250') == null ? '—' : factorValue(closeFactors, 'position_250')!.toFixed(2)}
                scale={{ min: 0, max: 1 }}
              />
              <FactorBar
                label="20日动量"
                hint="近20个交易日收盘涨幅；正数表示上涨。"
                value={factorValue(closeFactors, 'return_20')}
                display={fmtPct(factorValue(closeFactors, 'return_20') ?? undefined)}
                scale={{ min: -0.5, max: 0.5 }}
              />
              <FactorBar
                label="量比（D 收盘）"
                hint="当日成交量 / 前5个交易日平均成交量；1 表示与前5日均量相当。"
                value={factorValue(closeFactors, 'volume_ratio_vs_prior5')}
                display={factorValue(closeFactors, 'volume_ratio_vs_prior5') == null ? '—' : `${factorValue(closeFactors, 'volume_ratio_vs_prior5')!.toFixed(2)}×`}
                scale={{ min: 0, max: 4 }}
              />
            </div>
            <div className="mt-2 text-[10px] text-muted">
              背景时点 {bgFactors.asof}，D 收盘时点 {closeFactors.asof}。位置口径为 position_highlow_250d，本批未与注册表逐位认证。
            </div>
            {event.scale_check?.factor_events && event.scale_check.factor_events.length > 0 && (
              <p className="mt-1 text-[10px] leading-4 text-amber-500">
                该事件窗口含因子日 {event.scale_check.factor_events.map(item => item.date).join('、')}；下方位置/动量按未复权 close 计算，跨尺度，不能当已认证值。
              </p>
            )}
            <details className="mt-2 text-[11px] text-secondary">
              <summary className="cursor-pointer text-muted">原始因子数字（D-1 / D 收盘）</summary>
              <div className="mt-2 grid gap-x-6 gap-y-1 sm:grid-cols-2">
                {[
                  ['position_250', '开区间位置'], ['return_5', '5日涨幅'], ['return_20', '20日涨幅'],
                  ['return_60', '60日涨幅'], ['return_120', '120日涨幅'], ['return_250', '250日涨幅'],
                  ['volume_ratio_vs_prior5', '量比'], ['daily_return_std_20', '20日波动'],
                  ['ma_bias_20', '20日乖离'], ['amount', '成交额（未核验）'],
                ].map(([key, label]) => (
                  <div key={key} className="flex justify-between gap-3 border-b border-border/40 py-0.5">
                    <span className="text-muted">{label}</span>
                    <span className="num">
                      {String(factorValue(bgFactors, key as keyof typeof bgFactors) ?? '—')}
                      <span className="mx-1 text-muted/50">/</span>
                      {String(factorValue(closeFactors, key as keyof typeof closeFactors) ?? '—')}
                    </span>
                  </div>
                ))}
              </div>
            </details>
          </div>

          {/* 高级: 16 候选规则对比 */}
          <details className="rounded-card border border-border bg-surface p-3">
            <summary className="cursor-pointer text-xs font-medium text-foreground">
              高级对比：16 套候选规则（同一事件的不同口径，不代表已定稿）
            </summary>
            <div className="mt-2 overflow-x-auto">
              <table className="w-full min-w-[46rem] text-xs">
                <thead className="text-left text-secondary">
                  <tr>
                    <th className="px-2 py-1 font-medium">规则</th>
                    <th className="px-2 py-1 font-medium">锚点</th>
                    <th className="px-2 py-1 text-right font-medium">P</th>
                    <th className="px-2 py-1 font-medium">P 可知</th>
                    <th className="px-2 py-1 text-right font-medium">L</th>
                    <th className="px-2 py-1 font-medium">首次突破</th>
                    <th className="px-2 py-1 font-medium">跳过</th>
                    <th className="px-2 py-1 text-right font-medium">回调深度</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rules.map(key => {
                    const item = event.rules[key]
                    const isDefault = key === data.default_rule
                    return (
                      <tr
                        key={key}
                        onClick={() => setRule(key)}
                        className={`cursor-pointer border-t border-border/60 hover:bg-elevated/60 ${key === activeRule ? 'bg-accent/10' : ''}`}
                        title="点击用这套口径更新上面的 P/L 与判断解释"
                      >
                        <td className="px-2 py-1 font-mono text-[11px]">
                          {key}{isDefault && <span className="ml-1 rounded bg-amber-400/10 px-1 text-[9px] text-amber-500">默认·暂定</span>}
                        </td>
                        <td className="px-2 py-1 font-mono text-[11px] text-secondary">{item?.anchor ?? '—'}</td>
                        <td className="px-2 py-1 text-right num">{item?.P ?? '—'}</td>
                        <td className="px-2 py-1 font-mono text-[11px] text-secondary">{item?.P_known_at ?? '—'}</td>
                        <td className="px-2 py-1 text-right num">{item?.L_setup ?? '—'}</td>
                        <td className="px-2 py-1 font-mono text-[11px] text-secondary">{item?.first_break ?? '—'}</td>
                        <td className="px-2 py-1 text-[11px]">{item?.skip == null ? '—' : item.skip ? '是' : '否'}</td>
                        <td className="px-2 py-1 text-right num">{item?.depth == null ? '—' : `${(item.depth * 100).toFixed(1)}%`}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-[10px] leading-4 text-muted">
              16 套 = P取法(A/B) × 回调阈值(3%/5%) × 新峰值要求(是/否) × 锚点回溯(仅最近/继续回溯)。切换只是换观察口径，不产生综合评分，也不是收益比较。
            </p>
          </details>

          <div className="rounded-card border border-border bg-surface/60 p-3 text-[10px] leading-4 text-muted">
            <div className="mb-1 text-[11px] font-medium text-secondary">来源与边界</div>
            <p>{narrative?.board}</p>
            <p className="mt-1">研究材料目录：<span className="font-mono">{data.research_root}</span>；页面只读冻结副本，不回写研究目录、不重算收益。</p>
            <p className="mt-1">
              因子事件来自当前本地 adj_factor 只读核对（覆盖上界 2026-10-28）；价格序列来自冻结 CSV（截断 2026-10-23）。这是文档快照/当前数据差异；页面不据此重算收益。
            </p>
            {data.classification && (
              <div className="mt-1 space-y-0.5">
                <p>
                  分类源 {data.classification.schema_version}（计算口径 {data.classification.calculation_version}）；
                  v0.1.2 相对 {data.classification.source_version} 只补 {data.classification.added_null_keys} 个 null 键与 reason，不改分类计算值。
                </p>
                <p className="font-mono text-[9px]">Web 数据 schema {data.schema}</p>
                <p className="font-mono text-[9px]">
                  源 sha256 {data.classification.source_sha256.slice(0, 16)}… · 输出 {data.classification.output_sha256.slice(0, 16)}…
                </p>
                <p className="font-mono text-[9px]">
                  旧 v0.1 源 {data.classification.legacy_v01.sha256.slice(0, 16)}…；旧页面输出 replay.json 保留未覆盖。
                </p>
              </div>
            )}
            <p className="mt-1">
              D 后后续数据（135 条期限结果、449 条逐日跟踪）已包含在公开静态 JSON 中；默认折叠只是回放展示约定，不是访问控制。
            </p>
            <p className="mt-1">
              复权说明：冻结序列全区间 adj_ratio=1.0 且 close==raw_close，属未复权/跨尺度序列，不能当已连续复权；2026-06-25 等台阶在 close 与 raw_close 两列都保留。跨台阶日的收益、动量、P-L、位置指标均跨尺度；正确复权须另用因子链重算并独立认证。本页用冻结 CSV 的原始价台阶识别跨尺度事件（已证实者标“作废/待重算”，仅有外部报告/因子记录者标“待核实 UNKNOWN”）；台阶不证明转增/除权类型，公告原件/公司行动原因仍待核对，不据此推断无除权。
            </p>
            <p className="mt-1">
              已检索范围未发现可信覆盖来源；代码签名完整性不等于上游覆盖真实性。
            </p>
            <details className="mt-1.5">
              <summary className="cursor-pointer flex items-center gap-1 text-muted">
                <ExternalLink className="h-3 w-3" />数据文件与指纹
              </summary>
              <div className="mt-1 space-y-0.5">
                {Object.entries(data.sources).map(([key, src]) => (
                  <div key={key} className="flex flex-wrap justify-between gap-2">
                    <span className="font-mono text-[9px]">{src.path}</span>
                    <span className="font-mono text-[9px] text-muted/70">{src.sha256.slice(0, 16)}…</span>
                  </div>
                ))}
                <div className="pt-1">{data.limitations.join('；')}。</div>
              </div>
            </details>
          </div>
        </section>
      </main>
    </div>
  )
}
