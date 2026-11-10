import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'
import { AlertTriangle, BarChart3 } from 'lucide-react'
import { cn } from '@/lib/cn'
import { MOOD_LABEL, SETUP_LABEL, type GroupStats, type TradeStats } from './types'

function pct(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  return `${v > 0 ? '+' : ''}${v.toFixed(2)}%`
}

function rate(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  return `${v.toFixed(0)}%`
}

const FLAG_ADVICE: Record<string, string> = {
  chase: '入场价超过计划上限，改为限价单或直接放弃。',
  stop_breach: '跌破止损未离场，开仓前先确认退出触发条件。',
  oversize: '实际仓位超过计划，下单前先算最大亏损。',
  no_stop: '计划缺少止损价，先写失效价再考虑买入。',
  no_review: '已结束但未写复盘，至少记录离场理由。',
  missed: '计划未执行，区分主动放弃与犹豫错过。',
  below_plan: '低于计划价成交，检查是否属于计划外低吸。',
}

function CumulativeChart({ stats }: { stats: TradeStats }) {
  const ref = useRef<HTMLDivElement>(null)
  const chartRef = useRef<echarts.ECharts | null>(null)

  useEffect(() => {
    if (!ref.current) return
    chartRef.current = echarts.init(ref.current, undefined, { renderer: 'canvas' })
    const onResize = () => chartRef.current?.resize()
    window.addEventListener('resize', onResize)
    return () => {
      window.removeEventListener('resize', onResize)
      chartRef.current?.dispose()
      chartRef.current = null
    }
  }, [])

  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    const dark = document.documentElement.classList.contains('dark')
    const axis = dark ? '#8E8E96' : '#52525B'
    const split = dark ? '#353539' : '#E4E4E7'
    const curve = stats.equity_curve
    chart.setOption({
      grid: { left: 44, right: 12, top: 18, bottom: 26 },
      tooltip: {
        trigger: 'axis',
        formatter: (items: any[]) => {
          const item = items[0]
          const point = curve[item.dataIndex]
          return `${point?.date ?? ''} ${point?.symbol ?? ''}<br/>单笔 ${pct(point?.pnl_pct)}<br/>累计 ${pct(point?.cum_pct)}`
        },
      },
      xAxis: {
        type: 'category',
        data: curve.map(point => point.date.slice(5)),
        axisLine: { lineStyle: { color: split } },
        axisLabel: { color: axis, fontSize: 9 },
      },
      yAxis: {
        type: 'value',
        scale: true,
        axisLabel: { color: axis, fontSize: 9, formatter: (value: number) => `${value}%` },
        splitLine: { lineStyle: { color: split } },
      },
      series: [{
        type: 'line',
        data: curve.map(point => point.cum_pct),
        showSymbol: true,
        symbolSize: 4,
        lineStyle: { color: '#8B5CF6', width: 1.8 },
        itemStyle: { color: '#8B5CF6' },
        areaStyle: { color: 'rgba(139,92,246,0.10)' },
      }],
    })
  }, [stats])

  return <div ref={ref} className="h-52 w-full" />
}

function GroupTable({ title, groups, label }: {
  title: string
  groups: GroupStats[]
  label: (key: string) => string
}) {
  return (
    <div className="rounded-card border border-border bg-surface">
      <div className="flex items-center gap-1.5 border-b border-border px-3 py-2 text-[11px] font-medium text-foreground">
        <BarChart3 className="h-3.5 w-3.5 text-muted" /> {title}
      </div>
      {groups.length === 0 ? (
        <div className="px-3 py-6 text-center text-[10px] text-muted">暂无执行样本</div>
      ) : (
        <div className="divide-y divide-border/60">
          <div className="grid grid-cols-[1fr_52px_52px_66px_58px] px-3 py-1.5 text-[9px] text-muted">
            <span>分组</span><span className="text-right">执行</span><span className="text-right">胜率</span>
            <span className="text-right">平均收益</span><span className="text-right">平均R</span>
          </div>
          {groups.map(group => (
            <div key={group.key} className="grid grid-cols-[1fr_52px_52px_66px_58px] px-3 py-2 text-[10px]">
              <span className="truncate text-foreground">{label(group.key)}</span>
              <span className="text-right font-mono text-secondary">{group.count}</span>
              <span className="text-right font-mono text-secondary">{rate(group.win_rate)}</span>
              <span className={cn('text-right font-mono', (group.avg_pnl_pct ?? 0) > 0 ? 'text-bull' : (group.avg_pnl_pct ?? 0) < 0 ? 'text-bear' : 'text-secondary')}>
                {pct(group.avg_pnl_pct)}
              </span>
              <span className={cn('text-right font-mono', (group.avg_r ?? 0) > 0 ? 'text-bull' : (group.avg_r ?? 0) < 0 ? 'text-bear' : 'text-secondary')}>
                {group.avg_r == null ? '—' : group.avg_r.toFixed(2)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function Analytics({ stats }: { stats: TradeStats }) {
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
      <div className="space-y-4">
        <div className="rounded-card border border-border bg-surface">
          <div className="flex items-center justify-between border-b border-border px-3 py-2">
            <span className="text-[11px] font-medium text-foreground">累计单笔收益</span>
            <span className="text-[9px] text-muted">等权累加 · {stats.closed} 笔</span>
          </div>
          {stats.equity_curve.length > 0
            ? <CumulativeChart stats={stats} />
            : <div className="grid h-52 place-items-center text-[10px] text-muted">暂无已结束计划</div>}
        </div>

        <div className="grid gap-3 sm:grid-cols-3">
          <div className="rounded-card border border-border bg-surface px-4 py-3">
            <div className="text-[10px] text-muted">平均盈利</div>
            <div className="mt-1 font-mono text-lg font-semibold text-bull">{pct(stats.avg_win_pct)}</div>
          </div>
          <div className="rounded-card border border-border bg-surface px-4 py-3">
            <div className="text-[10px] text-muted">平均亏损</div>
            <div className="mt-1 font-mono text-lg font-semibold text-bear">{pct(stats.avg_loss_pct)}</div>
          </div>
          <div className="rounded-card border border-border bg-surface px-4 py-3">
            <div className="text-[10px] text-muted">盈亏比</div>
            <div className="mt-1 font-mono text-lg font-semibold text-foreground">
              {stats.profit_factor == null ? '—' : stats.profit_factor.toFixed(2)}
            </div>
          </div>
        </div>

        <div className="grid gap-3 lg:grid-cols-2">
          <GroupTable title="按模式" groups={stats.by_setup} label={key => SETUP_LABEL[key as keyof typeof SETUP_LABEL] ?? key} />
          <GroupTable title="按情绪" groups={stats.by_mood} label={key => MOOD_LABEL[key as keyof typeof MOOD_LABEL] ?? key} />
        </div>
      </div>

      <div className="rounded-card border border-border bg-surface">
        <div className="flex items-center gap-1.5 border-b border-border px-3 py-2 text-[11px] font-medium text-foreground">
          <AlertTriangle className="h-3.5 w-3.5 text-warning" /> 执行漏洞
        </div>
        {stats.flag_counts.length === 0 ? (
          <div className="px-3 py-8 text-center text-[10px] text-muted">暂无执行偏差</div>
        ) : (
          <div className="divide-y divide-border/60">
            {stats.flag_counts.map(flag => (
              <div key={flag.code} className="px-3 py-2.5">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[11px] text-foreground">{flag.label}</span>
                  <span className="font-mono text-[10px] text-warning">{flag.count} 次</span>
                </div>
                <p className="mt-1 text-[10px] leading-relaxed text-muted">{FLAG_ADVICE[flag.code] ?? '检查该类偏差的触发场景。'}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
