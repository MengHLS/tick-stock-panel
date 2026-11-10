import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { MinuteKlineRow, MinuteKlineSession } from '@/lib/api'
import { klineMinuteQueryOptions, klineMinuteRangeQueryOptions } from '@/lib/kline'
import { fmtPct, fmtPrice } from '@/lib/format'

const BUCKET_LABELS = ['10:30', '11:30', '14:00', '15:00'] as const

export interface HourlyBar {
  date: string
  time: string
  high: number
  low: number
  close: number
  volume: number
  rows: number
  complete: boolean
}

export interface MiniStructureSummary {
  sampleBars: number
  boxHigh: number
  boxLow: number
  current: number
  topDist: number
  capDist: number | null
  volRatio: number | null
  volumeLabel: '放量' | '缩量' | '平量' | null
  trend: 'up' | 'down' | 'range' | null
}

function minuteOf(datetime: string | undefined): number | null {
  const text = String(datetime ?? '')
  const hhmm = text.length >= 16 ? text.slice(11, 16) : text.slice(0, 5)
  const [hour, minute] = hhmm.split(':').map(Number)
  if (!Number.isFinite(hour) || !Number.isFinite(minute)) return null
  return hour * 60 + minute
}

function bucketIndex(minute: number): number {
  if (minute >= 570 && minute < 630) return 0
  if (minute >= 630 && minute <= 690) return 1
  if (minute >= 780 && minute < 840) return 2
  if (minute >= 840 && minute <= 900) return 3
  return -1
}

/** 把多日 1 分钟 K 聚合成 4 根/日的 60 分钟 K（不跨午休）。 */
export function buildHourlyBars(sessions: MinuteKlineSession[]): HourlyBar[] {
  const out: HourlyBar[] = []
  for (const session of sessions) {
    const buckets: MinuteKlineRow[][] = [[], [], [], []]
    for (const row of session.rows ?? []) {
      const minute = minuteOf(row.datetime)
      if (minute == null) continue
      const index = bucketIndex(minute)
      if (index >= 0) buckets[index].push(row)
    }
    for (let index = 0; index < buckets.length; index += 1) {
      const rows = buckets[index]
      if (rows.length === 0) continue
      const highs = rows.map(row => Number(row.high)).filter(Number.isFinite)
      const lows = rows.map(row => Number(row.low)).filter(Number.isFinite)
      const closes = rows.map(row => Number(row.close)).filter(Number.isFinite)
      if (highs.length === 0 || lows.length === 0 || closes.length === 0) continue
      const volume = rows.reduce((sum, row) => {
        const value = Number(row.volume)
        return sum + (Number.isFinite(value) ? value : 0)
      }, 0)
      out.push({
        date: session.date,
        time: BUCKET_LABELS[index],
        high: Math.max(...highs),
        low: Math.min(...lows),
        close: closes[closes.length - 1],
        volume,
        rows: rows.length,
        complete: rows.length >= 30,
      })
    }
  }
  return out
}

/** 最近 5 个交易日 60 分钟结构：箱体、上沿距离、量能、摆动高低点方向。 */
export function summarizeStructure(
  bars: HourlyBar[],
  cap: number | null | undefined,
): MiniStructureSummary | null {
  const valid = bars.filter(
    bar =>
      Number.isFinite(bar.high) &&
      Number.isFinite(bar.low) &&
      Number.isFinite(bar.close) &&
      bar.high >= bar.low,
  )
  if (valid.length < 4) return null

  const boxHigh = Math.max(...valid.map(bar => bar.high))
  const boxLow = Math.min(...valid.map(bar => bar.low))
  const current = valid[valid.length - 1].close
  if (!(boxHigh > 0) || !(current > 0)) return null

  const complete = valid.filter(bar => bar.complete)
  let volRatio: number | null = null
  let volumeLabel: MiniStructureSummary['volumeLabel'] = null
  if (complete.length >= 2) {
    const last = complete[complete.length - 1]
    const previous = complete.slice(-4, -1)
    const average = previous.reduce((sum, bar) => sum + bar.volume, 0) / previous.length
    if (average > 0) {
      volRatio = last.volume / average
      volumeLabel = volRatio >= 1.5 ? '放量' : volRatio <= 0.7 ? '缩量' : '平量'
    }
  }

  const swingHighs: number[] = []
  const swingLows: number[] = []
  for (let index = 1; index < complete.length - 1; index += 1) {
    const previous = complete[index - 1]
    const currentBar = complete[index]
    const next = complete[index + 1]
    if (currentBar.high > previous.high && currentBar.high > next.high) {
      swingHighs.push(currentBar.high)
    }
    if (currentBar.low < previous.low && currentBar.low < next.low) {
      swingLows.push(currentBar.low)
    }
  }

  let trend: MiniStructureSummary['trend'] = null
  if (swingHighs.length >= 2 && swingLows.length >= 2) {
    const higherHigh = swingHighs[swingHighs.length - 1] > swingHighs[swingHighs.length - 2]
    const higherLow = swingLows[swingLows.length - 1] > swingLows[swingLows.length - 2]
    trend = higherHigh && higherLow ? 'up' : !higherHigh && !higherLow ? 'down' : 'range'
  }

  return {
    sampleBars: valid.length,
    boxHigh,
    boxLow,
    current,
    topDist: boxHigh / current - 1,
    capDist: cap != null && cap > 0 ? cap / boxHigh - 1 : null,
    volRatio,
    volumeLabel,
    trend,
  }
}

function mergeSessions(
  history: MinuteKlineSession[],
  latest: { date?: string | null; prev_close?: number | null; rows?: MinuteKlineRow[] } | undefined,
  days: number,
): MinuteKlineSession[] {
  const byDate = new Map(history.map(session => [session.date, session]))
  if (latest?.date && (latest.rows?.length ?? 0) > 0) {
    byDate.set(latest.date, {
      date: latest.date,
      prev_close: latest.prev_close ?? null,
      rows: latest.rows ?? [],
    })
  }
  return Array.from(byDate.values())
    .sort((left, right) => left.date.localeCompare(right.date))
    .slice(-days)
}

const TREND_LABELS: Record<NonNullable<MiniStructureSummary['trend']>, string> = {
  up: '高点抬高·低点抬高',
  down: '高点降低·低点降低',
  range: '震荡',
}

const TREND_CLASSES: Record<NonNullable<MiniStructureSummary['trend']>, string> = {
  up: 'text-bull',
  down: 'text-bear',
  range: 'text-muted',
}

const VOLUME_CLASSES: Record<NonNullable<MiniStructureSummary['volumeLabel']>, string> = {
  放量: 'text-warning',
  缩量: 'text-muted',
  平量: 'text-secondary',
}

export function AbnormalMiniStructure({
  symbol,
  days,
  cap,
}: {
  symbol: string
  days: number
  cap?: number | null
}) {
  const structureDays = Math.max(5, days)
  const history = useQuery({
    ...klineMinuteRangeQueryOptions(symbol, structureDays),
    enabled: !!symbol,
  })
  const latest = useQuery({
    ...klineMinuteQueryOptions(symbol, undefined, true),
    enabled: !!symbol,
  })

  const sessions = useMemo(
    () => mergeSessions(history.data?.sessions ?? [], latest.data, structureDays),
    [history.data?.sessions, latest.data, structureDays],
  )
  const bars = useMemo(() => buildHourlyBars(sessions.slice(-5)), [sessions])
  const summary = useMemo(() => summarizeStructure(bars, cap), [bars, cap])

  if (history.isLoading && !latest.data) return null
  if (!summary) {
    return (
      <div className="flex shrink-0 items-center gap-2 border-b border-border/60 bg-base/30 px-5 py-1.5 text-[10px] text-muted">
        <span>60分结构</span>
        <span>数据不足</span>
      </div>
    )
  }

  const capText = summary.capDist == null
    ? null
    : summary.capDist >= 0
      ? `上沿距压制 ${fmtPct(summary.capDist, 1)}`
      : `上沿高于压制 ${fmtPct(-summary.capDist, 1)}`
  const volumeText = summary.volRatio != null
    ? `${summary.volumeLabel ?? '量能'} ${summary.volRatio.toFixed(1)}×`
    : null

  return (
    <div className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1 border-b border-border/60 bg-base/30 px-5 py-1.5 text-[10px]">
      <span
        className="shrink-0 text-muted"
        title="最近5个交易日60分钟K：箱体=最高/最低；量能=最后一根完整60分钟量/前3根均量；结构=最近两个摆动高低点"
      >
        60分结构
      </span>
      <span className="font-mono text-secondary">
        箱体 {fmtPrice(summary.boxLow)}–{fmtPrice(summary.boxHigh)}
      </span>
      <span className="font-mono text-secondary">距上沿 {fmtPct(summary.topDist, 1)}</span>
      {capText && (
        <span className={`font-mono ${summary.capDist != null && summary.capDist < 0 ? 'text-warning' : 'text-secondary'}`}>
          {capText}
        </span>
      )}
      {volumeText && (
        <span className={summary.volumeLabel ? VOLUME_CLASSES[summary.volumeLabel] : 'text-secondary'}>
          {volumeText}
        </span>
      )}
      <span className={summary.trend ? TREND_CLASSES[summary.trend] : 'text-muted'}>
        {summary.trend ? TREND_LABELS[summary.trend] : '结构样本不足'}
      </span>
      <span className="ml-auto shrink-0 text-[9px] text-muted/70">最近5日</span>
    </div>
  )
}
