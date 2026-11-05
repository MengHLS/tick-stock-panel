import { useEffect, useMemo, useRef } from 'react'
import * as echarts from 'echarts'
import type { ECharts, EChartsOption } from 'echarts'
import { useChartTheme, type ChartTheme } from '@/lib/theme'
import type { ThemeAnalyzerAnalysis, ThemeAnalyzerLeader, ThemeAnalyzerMinute } from '@/lib/api'

interface BaseChartProps {
  height?: number
  className?: string
}

function useEChart(
  option: EChartsOption,
  onClick?: (params: any) => void,
) {
  const ref = useRef<HTMLDivElement>(null)
  const chartRef = useRef<ECharts | null>(null)
  const clickRef = useRef(onClick)
  clickRef.current = onClick

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const chart = echarts.init(el, undefined, { renderer: 'canvas' })
    chartRef.current = chart
    const onChartClick = (params: any) => clickRef.current?.(params)
    chart.on('click', onChartClick)
    const observer = new ResizeObserver(() => chart.resize())
    observer.observe(el)
    return () => {
      observer.disconnect()
      chart.off('click', onChartClick)
      chart.dispose()
      chartRef.current = null
    }
  }, [])

  useEffect(() => {
    chartRef.current?.setOption(option, true)
  }, [option])

  return ref
}

function baseText(ct: ChartTheme) {
  return {
    color: ct.text,
    fontFamily: 'Inter, system-ui, sans-serif',
    fontSize: 11,
  }
}

export function ThemeTrendChart({
  analysis,
  height = 320,
  className,
}: BaseChartProps & { analysis: ThemeAnalyzerAnalysis }) {
  const ct = useChartTheme()
  const option = useMemo<EChartsOption>(() => {
    const colors = ['#F59E0B', '#22D3EE', '#FB7185', '#A78BFA', '#A3E635']
    const core = analysis.core_stocks ?? []
    return {
      backgroundColor: 'transparent',
      animation: false,
      color: [...colors, '#64748B', '#94A3B8'],
      textStyle: baseText(ct),
      legend: {
        top: 4,
        right: 8,
        type: 'scroll',
        textStyle: baseText(ct),
        itemWidth: 16,
        itemHeight: 2,
        data: [...core.map(item => item.name), '题材等权', '上证指数'],
      },
      tooltip: {
        trigger: 'axis',
        backgroundColor: ct.tooltipBg,
        borderColor: ct.tooltipBorder,
        textStyle: { color: ct.tooltipText, fontSize: 11 },
        axisPointer: { type: 'line', lineStyle: { color: ct.crosshair } },
        valueFormatter: (value: unknown) =>
          typeof value === 'number' ? value.toFixed(1) : '—',
      },
      grid: { left: 44, right: 18, top: 42, bottom: 28 },
      xAxis: {
        type: 'category',
        boundaryGap: false,
        data: analysis.index.dates,
        axisLine: { lineStyle: { color: ct.border } },
        axisTick: { show: false },
        axisLabel: {
          ...baseText(ct),
          formatter: (value: string) => value.slice(5),
          hideOverlap: true,
        },
      },
      yAxis: {
        type: 'value',
        scale: true,
        name: '前收=100',
        nameTextStyle: baseText(ct),
        axisLabel: baseText(ct),
        splitLine: { lineStyle: { color: ct.grid } },
      },
      series: [
        ...core.map((stock, index) => ({
          name: stock.name,
          type: 'line' as const,
          data: analysis.core_series[stock.symbol] ?? [],
          showSymbol: false,
          lineStyle: { width: index === 0 ? 2.6 : 1.8, color: colors[index % colors.length] },
          itemStyle: { color: colors[index % colors.length] },
          emphasis: { focus: 'series' as const },
        })),
        {
          name: '题材等权',
          type: 'line',
          data: analysis.index.pool,
          showSymbol: false,
          connectNulls: true,
          lineStyle: { width: 1.4, color: '#64748B' },
        },
        {
          name: '上证指数',
          type: 'line',
          data: analysis.index.sh,
          showSymbol: false,
          connectNulls: true,
          lineStyle: { width: 1.2, type: 'dashed', color: '#94A3B8' },
        },
      ],
    }
  }, [analysis.core_series, analysis.core_stocks, analysis.index, ct])
  const ref = useEChart(option)
  return <div ref={ref} className={className} style={{ height }} aria-label="核心股整波路径图" />
}

export function ThemeQuadrantChart({
  leaders,
  height = 340,
  className,
  onSelect,
}: BaseChartProps & {
  leaders: ThemeAnalyzerLeader[]
  onSelect?: (symbol: string) => void
}) {
  const ct = useChartTheme()
  const option = useMemo<EChartsOption>(() => {
    const points = leaders
      .filter(leader => leader.latest_ret_3 != null && leader.max_ret_30 != null)
      .map(leader => ({
        value: [
          (leader.latest_ret_3 ?? 0) * 100,
          (leader.max_ret_30 ?? 0) * 100,
          leader.name,
          leader.symbol,
          leader.active_gt2,
        ],
        itemStyle: { color: leader.active ? '#F59E0B' : '#94A3B8' },
        symbolSize: 8 + Math.min(leader.active_gt2, 20) * 0.75,
      }))
    return {
      backgroundColor: 'transparent',
      animation: false,
      textStyle: baseText(ct),
      tooltip: {
        trigger: 'item',
        backgroundColor: ct.tooltipBg,
        borderColor: ct.tooltipBorder,
        textStyle: { color: ct.tooltipText, fontSize: 11 },
        formatter: (params: any) => {
          const data = params.data?.value ?? []
          return [
            `<b>${data[2] ?? ''}</b>`,
            `当前3日 ${Number(data[0] ?? 0).toFixed(1)}%`,
            `30日最大 ${Number(data[1] ?? 0).toFixed(1)}%`,
            `跑赢天数 ${Number(data[4] ?? 0)}`,
          ].join('<br/>')
        },
      },
      grid: { left: 48, right: 20, top: 28, bottom: 42 },
      xAxis: {
        type: 'value',
        name: '当前3日 %',
        nameLocation: 'middle',
        nameGap: 26,
        nameTextStyle: baseText(ct),
        axisLabel: { ...baseText(ct), formatter: '{value}%' },
        splitLine: { lineStyle: { color: ct.grid } },
      },
      yAxis: {
        type: 'value',
        name: '30日最大 %',
        nameTextStyle: baseText(ct),
        axisLabel: { ...baseText(ct), formatter: '{value}%' },
        splitLine: { lineStyle: { color: ct.grid } },
      },
      series: [{
        type: 'scatter',
        data: points,
        emphasis: { scale: 1.3 },
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { color: ct.border, type: 'dashed' },
          label: { show: false },
          data: [{ xAxis: 0 }, { yAxis: 0 }],
        },
      }],
    }
  }, [ct, leaders])
  const ref = useEChart(option, params => {
    const symbol = params?.data?.value?.[3]
    if (typeof symbol === 'string') onSelect?.(symbol)
  })
  return <div ref={ref} className={className} style={{ height }} aria-label="空间与当前强度四象限" />
}

export function MinuteOverlayChart({
  minute,
  colors,
  height = 300,
  className,
}: BaseChartProps & {
  minute: ThemeAnalyzerMinute
  colors: Record<string, string>
}) {
  const ct = useChartTheme()
  const option = useMemo<EChartsOption>(() => {
    const series = minute.stocks.map(stock => ({
      name: stock.name,
      type: 'line' as const,
      data: minute.series[stock.symbol] ?? [],
      showSymbol: false,
      connectNulls: false,
      lineStyle: { width: 1.8, color: colors[stock.symbol] ?? '#94A3B8' },
      itemStyle: { color: colors[stock.symbol] ?? '#94A3B8' },
      emphasis: { focus: 'series' as const },
    }))
    return {
      backgroundColor: 'transparent',
      animation: false,
      color: minute.stocks.map(stock => colors[stock.symbol] ?? '#94A3B8'),
      textStyle: baseText(ct),
      legend: {
        top: 2,
        left: 4,
        right: 4,
        type: 'scroll',
        textStyle: baseText(ct),
        itemWidth: 14,
        itemHeight: 2,
      },
      tooltip: {
        trigger: 'axis',
        backgroundColor: ct.tooltipBg,
        borderColor: ct.tooltipBorder,
        textStyle: { color: ct.tooltipText, fontSize: 11 },
        axisPointer: { type: 'line', lineStyle: { color: ct.crosshair } },
        valueFormatter: (value: unknown) =>
          typeof value === 'number' ? `${value > 0 ? '+' : ''}${value.toFixed(2)}%` : '—',
      },
      grid: { left: 46, right: 16, top: 44, bottom: 30 },
      xAxis: {
        type: 'category',
        boundaryGap: false,
        data: minute.times,
        axisLine: { lineStyle: { color: ct.border } },
        axisTick: { show: false },
        axisLabel: {
          ...baseText(ct),
          interval: (index: number, value: string) =>
            ['09:31', '10:30', '11:30', '14:00', '15:00'].includes(value) || index === minute.times.length - 1,
          hideOverlap: true,
        },
      },
      yAxis: {
        type: 'value',
        name: '相对昨收 %',
        nameTextStyle: baseText(ct),
        axisLabel: { ...baseText(ct), formatter: '{value}%' },
        splitLine: { lineStyle: { color: ct.grid } },
      },
      series,
    }
  }, [colors, ct, minute])
  const ref = useEChart(option)
  return <div ref={ref} className={className} style={{ height }} aria-label="关键日多股分钟叠加图" />
}

function MinuteMiniChart({
  name,
  values,
  color,
  times,
  limitPct,
}: {
  name: string
  values: (number | null)[]
  color: string
  times: string[]
  limitPct?: number | null
}) {
  const ct = useChartTheme()
  const option = useMemo<EChartsOption>(() => ({
    backgroundColor: 'transparent',
    animation: false,
    textStyle: baseText(ct),
    tooltip: {
      trigger: 'axis',
      backgroundColor: ct.tooltipBg,
      borderColor: ct.tooltipBorder,
      textStyle: { color: ct.tooltipText, fontSize: 10 },
      valueFormatter: (value: unknown) =>
        typeof value === 'number' ? `${value > 0 ? '+' : ''}${value.toFixed(2)}%` : '—',
    },
    grid: { left: 30, right: 8, top: 16, bottom: 20 },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: times,
      axisLine: { lineStyle: { color: ct.border } },
      axisTick: { show: false },
      axisLabel: {
        ...baseText(ct),
        fontSize: 9,
        interval: (index: number, value: string) =>
          ['10:30', '11:30', '14:00', '15:00'].includes(value) || index === times.length - 1,
        hideOverlap: true,
      },
    },
    yAxis: {
      type: 'value',
      axisLabel: { ...baseText(ct), fontSize: 9, formatter: '{value}%' },
      splitLine: { lineStyle: { color: ct.grid } },
    },
    series: [{
      name,
      type: 'line',
      data: values,
      showSymbol: false,
      lineStyle: { width: 1.6, color },
      itemStyle: { color },
      markLine: {
        silent: true,
        symbol: 'none',
        label: { show: false },
        lineStyle: { color: ct.border, type: 'dashed' },
        data: limitPct
          ? [
              { yAxis: 0 },
              {
                yAxis: limitPct,
                lineStyle: { color: '#F59E0B', type: 'dashed' },
                label: {
                  show: true,
                  formatter: `涨停 +${limitPct.toFixed(0)}%`,
                  color: '#F59E0B',
                  fontSize: 9,
                  position: 'insideEndTop',
                },
              },
            ]
          : [{ yAxis: 0 }],
      },
    }],
  }), [color, ct, limitPct, name, times, values])
  const ref = useEChart(option)
  return <div ref={ref} style={{ height: 132 }} aria-label={`${name} 当日分时`} />
}

export function MinuteSmallMultiples({
  minute,
  colors,
}: {
  minute: ThemeAnalyzerMinute
  colors: Record<string, string>
}) {
  return (
    <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
      {minute.stocks.map(stock => (
        <div key={stock.symbol} className="min-w-0 rounded-xl border border-border/70 bg-base/40 p-1.5">
          <div className="flex items-center justify-between gap-2 px-1 text-[10px]">
            <span className="truncate font-medium text-secondary">{stock.name}</span>
            <span className="shrink-0 font-mono text-muted">{stock.symbol}</span>
          </div>
          <MinuteMiniChart
            name={stock.name}
            times={minute.times}
            values={minute.series[stock.symbol] ?? []}
            color={colors[stock.symbol] ?? '#94A3B8'}
            limitPct={stock.limit_pct}
          />
        </div>
      ))}
    </div>
  )
}

