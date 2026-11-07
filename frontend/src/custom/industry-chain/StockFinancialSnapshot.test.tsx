// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { expect, it, vi } from 'vitest'
import { StockFinancialSnapshot } from './StockFinancialSnapshot'

vi.mock('@/lib/useFinancials', () => ({
  useFinancialMetrics: () => ({
    data: {
      data: [{
        period_end: '2026-09-30',
        revenue_yoy: 12.3,
        net_income_yoy: -4.5,
        roe: 8.2,
        gross_margin: 30.1,
        net_margin: 10.2,
        debt_to_asset_ratio: 45.6,
      }],
    },
    isLoading: false,
    isError: false,
  }),
  useFinancialIncome: () => ({
    data: {
      data: [{
        period_end: '2026-09-30',
        revenue: 1_234_567_890,
        net_income_attributable: 123_456_789,
      }],
    },
    isLoading: false,
    isError: false,
  }),
}))

it('展示最新一期基础财务指标', () => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  try {
    act(() => root.render(<StockFinancialSnapshot symbol="000070.SZ" />))

    expect(host.textContent).toContain('基础财务')
    expect(host.textContent).toContain('2026-09-30')
    expect(host.textContent).toContain('12.35亿')
    expect(host.textContent).toContain('1.23亿')
    expect(host.textContent).toContain('12.30%')
    expect(host.textContent).toContain('-4.50%')
    expect(host.textContent).toContain('8.20%')
    expect(host.textContent).toContain('30.10%')
    expect(host.textContent).toContain('10.20%')
    expect(host.textContent).toContain('45.60%')
  } finally {
    act(() => root.unmount())
    host.remove()
  }
})
