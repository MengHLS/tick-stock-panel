// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { expect, it, vi } from 'vitest'
import { StockDailyKChart } from './StockDailyKChart'

const query = vi.hoisted(() => ({
  value: { data: undefined as { rows: unknown[] } | undefined, isLoading: false, isError: false },
}))

vi.mock('@tanstack/react-query', () => ({
  useQuery: () => query.value,
}))

vi.mock('./EChartsCandlestick', () => ({
  EChartsCandlestick: () => <div data-testid="chart" />,
  OVERLAY_INDICATORS: [],
  SUB_CHARTS: [],
}))

it('没有日线数据时显示空状态，而不是空白图表', () => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  try {
    act(() => root.render(<StockDailyKChart symbol="000977.SZ" />))
    expect(host.textContent).toContain('暂无日线数据')
    expect(host.querySelector('[data-testid="chart"]')).toBeNull()
  } finally {
    act(() => root.unmount())
    host.remove()
  }
})
