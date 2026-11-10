// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { TradeAnalysisPage } from './Page'
import type { TradeOverview } from './client'
import { api } from '@/lib/api'

vi.mock('echarts', () => ({
  init: () => ({
    setOption: vi.fn(),
    resize: vi.fn(),
    dispose: vi.fn(),
  }),
}))
vi.mock('@/components/EChartsCandlestick', () => ({
  EChartsCandlestick: () => <div data-testid="k-chart" />,
}))

const tradeApi = vi.hoisted(() => ({
  overview: vi.fn(),
  saveNote: vi.fn(),
  importStatement: vi.fn(),
  reanalyze: vi.fn(),
}))
vi.mock('./client', () => ({ tradeAnalysisApi: tradeApi }))
vi.mock('@/extensions/stockPreview', () => ({ openStockPreview: vi.fn() }))
vi.mock('@/components/Toast', () => ({ toast: vi.fn() }))

const fixture: TradeOverview = {
  fills: 2,
  trades: 1,
  open_positions: 1,
  total_pnl: 152.8,
  win_rate: 1,
  profit_factor: 1.2,
  payoff: 1.2,
  avg_win: 152.8,
  avg_loss: null,
  avg_ret: 0.0112,
  avg_hold_days: 2,
  total_fees: 27.2,
  max_drawdown: 0,
  first_date: '2026-11-04',
  last_date: '2026-11-06',
  last_import_at: '2026-11-10T12:00:00+00:00',
  curve: [{ date: '2026-11-06', pnl: 152.8, cum_pnl: 152.8 }],
  symbols: [{
    symbol: '603618.SH', name: '杭电股份', trades: 1, wins: 1, pnl: 152.8,
    avg_ret: 0.0112, win_rate: 1, last_close: '2026-11-06',
  }],
  positions: [{
    symbol: '603618.SH', name: '杭电股份', qty: 700, avg_cost: 22.49,
    open_date: '2026-11-06', open_time: '09:33:16',
  }],
  trade_rows: [{
    trade_key: 'k1',
    symbol: '603618.SH',
    name: '杭电股份',
    open_date: '2026-11-04',
    open_time: '10:35:50',
    close_date: '2026-11-06',
    close_time: '14:52:31',
    qty: 600,
    buy_price: 22.83,
    sell_price: 23.08,
    cost: 13695.13,
    proceeds: 13847.93,
    pnl: 152.8,
    ret: 0.0112,
    fees: 27.2,
    hold_days: 2,
    hold_td: 2,
    buy_count: 1,
    sell_count: 1,
    legs: [{
      date: '2026-11-04', time: '10:35:50', side: 'B', qty: 600,
      price: 22.83, cash_flow: -13695.13, fees: 9.6,
    }, {
      date: '2026-11-06', time: '14:52:31', side: 'S', qty: 600,
      price: 23.08, cash_flow: 13847.93, fees: 6.7,
    }],
    analysis: '2026-11-04 买入，2026-11-06 卖出。持有 2 个交易日，净收益 +1.12%。',
    analysis_status: 'full',
    tags: ['盈利', '短线'],
    mfe: 0.0677,
    mae: -0.0787,
    buy_range_pct: 0.73,
    exit_range_pct: 0.52,
    ma5_dev: -0.037,
    ma20_dev: null,
    post5: null,
    post10: null,
    fee_ratio: 0.002,
    note: '',
    user_tags: [],
    patterns: ['突破'],
    note_updated_at: null,
  }],
}

let host: HTMLDivElement
let root: Root
let client: QueryClient

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  vi.stubGlobal('ResizeObserver', class {
    observe() {}
    disconnect() {}
  })
  tradeApi.overview.mockResolvedValue(fixture)
  vi.spyOn(api, 'klineDailyBatch').mockResolvedValue({ data: {} })
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } })
})

afterEach(async () => {
  await act(async () => root.unmount())
  client.clear()
  host.remove()
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})

async function settle() {
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)) })
}

it('loads the overview and opens per-trade analysis', async () => {
  await act(async () => root.render(
    <QueryClientProvider client={client}><TradeAnalysisPage /></QueryClientProvider>,
  ))
  await settle()

  expect(tradeApi.overview).toHaveBeenCalledTimes(1)
  expect(host.textContent).toContain('+152.80')
  expect(host.textContent).toContain('杭电股份')
  expect(host.textContent).toContain('盈利')
  expect(host.textContent).toContain('交易模式')
  expect(host.textContent).toContain('突破')

  const row = host.querySelector('tbody tr')
  expect(row).not.toBeNull()
  await act(async () => {
    row?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  })
  await settle()

  expect(host.textContent).toContain('2026-11-04 买入')
  expect(host.textContent).toContain('最大浮盈')
  expect(host.textContent).toContain('复盘笔记')
})
