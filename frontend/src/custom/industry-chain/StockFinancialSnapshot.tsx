import { useFinancialIncome, useFinancialMetrics } from '@/lib/useFinancials'
import { fmtBigNum } from '@/lib/format'

interface Props {
  symbol: string
}

export function StockFinancialSnapshot({ symbol }: Props) {
  const metricsQuery = useFinancialMetrics(symbol)
  const incomeQuery = useFinancialIncome(symbol)
  const latestMetrics = latestRecord(metricsQuery.data?.data)
  const latestIncome = latestRecord(incomeQuery.data?.data)
  const period = latestPeriod(latestMetrics?.period_end, latestIncome?.period_end)
  const metrics = latestMetrics?.period_end === period ? latestMetrics : undefined
  const income = latestIncome?.period_end === period ? latestIncome : undefined
  const loading = (metricsQuery.isLoading && !latestMetrics) || (incomeQuery.isLoading && !latestIncome)
  const error = !metrics && !income && (metricsQuery.isError || incomeQuery.isError)
  const items = [
    { label: '营业收入', value: fmtAmount(income?.revenue) },
    {
      label: '归母净利润',
      value: fmtAmount(income?.net_income_attributable ?? income?.net_income),
    },
    { label: '营收同比', value: fmtPctPoint(metrics?.revenue_yoy) },
    { label: '净利同比', value: fmtPctPoint(metrics?.net_income_yoy) },
    { label: 'ROE', value: fmtPctPoint(metrics?.roe) },
    { label: '毛利率', value: fmtPctPoint(metrics?.gross_margin) },
    { label: '净利率', value: fmtPctPoint(metrics?.net_margin) },
    { label: '资产负债率', value: fmtPctPoint(metrics?.debt_to_asset_ratio) },
  ]
  const hasData = items.some(item => item.value !== '—')

  return (
    <section className="mt-3 rounded-lg border border-border bg-base/50 px-3 py-2.5">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-[11px] font-medium text-secondary">基础财务</h3>
        {period && <span className="font-mono text-[9px] text-muted">{period}</span>}
      </div>
      {!hasData ? (
        <p className="mt-2 text-[10px] text-muted">
          {loading ? '财务数据加载中…' : error ? '财务数据读取失败' : '暂无财务数据'}
        </p>
      ) : (
        <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1.5 sm:grid-cols-4">
          {items.map(item => (
            <div key={item.label} className="min-w-0">
              <div className="text-[9px] text-muted">{item.label}</div>
              <div className="truncate font-mono text-[11px] tabular-nums text-foreground">
                {item.value}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

function latestRecord<T extends { period_end: string }>(rows: T[] | undefined): T | undefined {
  return [...(rows ?? [])].sort((a, b) => b.period_end.localeCompare(a.period_end))[0]
}

function latestPeriod(...periods: Array<string | undefined>): string | undefined {
  return periods.filter((value): value is string => !!value).sort().at(-1)
}

function fmtPctPoint(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  return `${value.toFixed(2)}%`
}

function fmtAmount(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  return `${value < 0 ? '-' : ''}${fmtBigNum(Math.abs(value))}`
}
