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
  const option = useMemo<EChartsOption>(() => ({
    backgroundColor: 'transparent',
    animation: false,
    color: ['#F59E0B', '#22D3EE', '#94A3B8'],
    textStyle: baseText(ct),
    legend: {
      top: 4,
      right: 8,
      textStyle: baseText(ct),
      itemWidth: 16,
      itemHeight: 2,
      data: ['活跃等权', '主题池等权', '上证指数'],
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
      name: '起点=100',
      nameTextStyle: baseText(ct),
      axisLabel: baseText(ct),
      splitLine: { lineStyle: { color: ct.grid } },
    },
    series: [
      {
        name: '活跃等权',
        type: 'line',
        data: analysis.index.active,
        showSymbol: false,
        connectNulls: true,
        lineStyle: { width: 2.4 },
        areaStyle: { opacity: 0.06 },
      },
      {
        name: '主题池等权',
        type: 'line',
        data: analysis.index.pool,
        showSymbol: false,
        connectNulls: true,
        lineStyle: { width: 1.8 },
      },
      {
        name: '上证指数',
        type: 'line',
        data: analysis.index.sh,
        showSymbol: false,
        connectNulls: true,
        lineStyle: { width: 1.4, type: 'dashed' },
      },
    ],
  }), [analysis.index, ct])
  const ref = useEChart(option)
  return <div ref={ref} className={className} style={{ height }} aria-label="主题等权路径图" />
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

