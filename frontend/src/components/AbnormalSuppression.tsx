import { useQuery } from '@tanstack/react-query'
import {
  api,
  type AbnormalSuppression as AbnormalSuppressionPayload,
  type AbnormalSuppressionWindow,
  type AbnormalWindowKey,
} from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { fmtPrice } from '@/lib/format'
import { AbnormalMiniStructure } from '@/components/AbnormalMiniStructure'

const WINDOW_ORDER = ['3d', '10d', '30d'] as const
const WINDOW_LABELS: Record<string, string> = {
  '3d': '3日',
  '10d': '10日',
  '30d': '30日',
}
const DAY_LABELS = ['今', '明', '后']
const FORWARD_DAYS = 5
const VISIBLE_DAYS = 3

function roomClass(room: number, direction: 'up' | 'down'): string {
  if (direction === 'up') {
    if (room < 0) return 'text-danger'
    return room < 0.05 ? 'text-warning' : 'text-bull'
  }
  if (room > 0) return 'text-danger'
  return room > -0.05 ? 'text-warning' : 'text-bear'
}

function roomText(room: number, direction: 'up' | 'down'): string {
  if (Math.abs(room) < 1e-4) return '临界'
  const pct = (Math.abs(room) * 100).toFixed(1)
  if (direction === 'up') {
    return room >= 0 ? `+${pct}%` : `已超${pct}%`
  }
  return room <= 0 ? `-${pct}%` : `已破${pct}%`
}

function windowTitle(key: string, window: AbnormalSuppressionWindow, nearest: boolean): string {
  const sign = window.direction === 'up' ? '+' : '−'
  return [
    `${WINDOW_LABELS[key]}偏离阈值 ${sign}${(window.threshold * 100).toFixed(0)}%`,
    `当前偏离 ${(window.current_deviation * 100).toFixed(1)}%`,
    `本轮 ${window.effective_days ?? parseInt(key, 10)} 日${window.days?.[0]?.base_date ? ` · 起点 ${window.days[0].base_date}` : ''}`,
    '按收盘价测算；假设对应指数保持当前点位，窗口逐日滚动',
    nearest ? '最临近压制' : '',
  ].filter(Boolean).join(' · ')
}

export function AbnormalSuppressionRows({
  data, symbol, days, window: selectedWindow,
}: {
  data: AbnormalSuppressionPayload
  symbol: string
  days: number
  window?: AbnormalWindowKey
}) {
  const keys = (selectedWindow ? [selectedWindow] : WINDOW_ORDER)
    .filter(key => data.windows?.[key])
  if (keys.length === 0) {
    return (
      <div className="flex shrink-0 items-center border-b border-border/60 bg-base/40 px-5 py-1.5 text-[10px] text-muted">
        压制价数据不足
      </div>
    )
  }

  const nearest = data.nearest?.window
  const capWindow = selectedWindow && data.windows[selectedWindow]
    ? selectedWindow
    : keys[0]
  return (
    <>
      <div className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-1 border-b border-border/60 bg-base/40 px-5 py-1.5">
        <span
          className="shrink-0 text-[10px] text-muted"
          title="将异动偏离阈值反解为收盘价；窗口每个交易日向前滚动，明日按新的 N 日基准重算"
        >
          后续压制
        </span>
        {keys.map(key => {
          const window = data.windows[key]
          const active = nearest === key
          const actualDays = window.effective_days
          const label = actualDays != null && actualDays !== parseInt(key, 10)
            ? `${WINDOW_LABELS[key]}(${actualDays}日)`
            : WINDOW_LABELS[key]
          return (
            <div key={key} className="flex min-w-0 items-center gap-1.5">
              <span
                className={`shrink-0 text-[10px] ${active ? 'font-semibold text-foreground' : 'text-muted'}`}
                title={windowTitle(key, window, active)}
              >
                {label}
              </span>
              {window.days.slice(0, VISIBLE_DAYS).map((day, index) => (
                <span
                  key={day.offset}
                  className={`inline-flex items-center gap-1 rounded border px-1 py-0.5 font-mono text-[10px] ${
                    active ? 'border-border bg-elevated' : 'border-border/50 bg-surface/50'
                  }`}
                  title={`窗口基准日 ${day.base_date} · 收盘压制价 ${fmtPrice(day.cap)}`}
                >
                  <span className="text-muted">{DAY_LABELS[index] ?? `+${day.offset}`}</span>
                  <span className={active ? 'font-semibold text-foreground' : 'text-secondary'}>
                    {fmtPrice(day.cap)}
                  </span>
                  <span className={roomClass(day.room_pct, window.direction)}>
                    {roomText(day.room_pct, window.direction)}
                  </span>
                </span>
              ))}
            </div>
          )
        })}
        <span
          className="ml-auto shrink-0 text-[9px] text-muted/70"
          title={`按 ${data.asof ?? '最新'} 收盘价测算；假设对应指数保持当前点位`}
        >
          收盘口径
        </span>
      </div>
      <AbnormalMiniStructure
        symbol={symbol}
        days={days}
        cap={capWindow ? data.windows[capWindow]?.days?.[0]?.cap ?? null : null}
      />
    </>
  )
}

export function AbnormalSuppression({
  symbol, days, window,
}: {
  symbol: string
  days: number
  window?: AbnormalWindowKey
}) {
  const query = useQuery({
    queryKey: QK.abnormalSuppression(symbol, FORWARD_DAYS, window),
    queryFn: () => api.abnormalSuppression(symbol, FORWARD_DAYS, window),
    staleTime: 30_000,
    refetchInterval: 60_000,
  })

  if (query.isLoading || query.isError || !query.data) return null
  return (
    <AbnormalSuppressionRows
      data={query.data}
      symbol={symbol}
      days={days}
      window={window}
    />
  )
}
