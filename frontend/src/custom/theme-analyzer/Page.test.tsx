// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { ThemeAnalyzerAnalysis } from '@/lib/api'

const mocks = vi.hoisted(() => ({
  themes: vi.fn(),
  analysis: vi.fn(),
  minute: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  remove: vi.fn(),
  add: vi.fn(),
  delete: vi.fn(),
  search: vi.fn(),
}))

vi.mock('@/lib/api', () => ({
  api: {
    themeAnalyzerThemes: mocks.themes,
    themeAnalyzerAnalysis: mocks.analysis,
    themeAnalyzerMinute: mocks.minute,
    themeAnalyzerCreate: mocks.create,
    themeAnalyzerUpdate: mocks.update,
    themeAnalyzerRemoveStock: mocks.remove,
    themeAnalyzerAddStocks: mocks.add,
    themeAnalyzerDelete: mocks.delete,
    instrumentSearch: mocks.search,
  },
}))

vi.mock('./charts', () => ({
  ThemeTrendChart: () => <div data-testid="core-trend" />,
  MinuteSmallMultiples: () => <div data-testid="minute-small-multiples" />,
}))
vi.mock('./LimitRouteMap', () => ({ LimitRouteMap: () => <div data-testid="limit-route" /> }))
vi.mock('@/components/StockPreviewDialog', () => ({ StockPreviewDialog: () => null }))

import { ThemeAnalyzerPage } from './Page'

let host: HTMLDivElement
let root: Root
let queryClient: QueryClient

function analysis(): ThemeAnalyzerAnalysis {
  const leaders = Array.from({ length: 6 }, (_, index) => ({
    symbol: `00000${index + 1}.SZ`,
    name: `股票${index + 1}`,
    board: '深主板' as const,
    is_mainboard: true,
    active: index < 3,
    last_date: '2026-11-04',
    last_close: 10 + index,
    max_ret_3: 0.1,
    max_ret_3_date: '2026-11-04',
    max_ret_10: 0.2,
    max_ret_10_date: '2026-11-04',
    max_ret_30: 0.3 - index * 0.01,
    max_ret_30_date: '2026-11-03',
    latest_ret_3: 0.05,
    latest_ret_10: 0.1,
    latest_ret_30: 0.2,
    active_gt2: 4,
    avg_deviate: 0.03,
    max_deviate: 0.08,
    avg_close_pos: 0.7,
    active_days: 10,
    event_count: 2,
  }))
  return {
    theme_id: 'ai',
    theme_name: 'AI 算力',
    as_of: '2026-11-04',
    window_start: '2026-09-01',
    window_end: '2026-11-04',
    default_window_days: 60,
    pool_count: 7,
    candidate_count: 6,
    filtered_count: 1,
    quoted_count: 6,
    active_count: 3,
    mainboard_only: true,
    active_return: 0.2,
    pool_return: 0.18,
    sh_return: 0.03,
    latest_minute_date: '2026-11-04',
    minute_dates: ['2026-11-03', '2026-11-04'],
    recent_dates: ['2026-09-01', '2026-11-04'],
    core_stocks: leaders.slice(0, 5).map((leader, index) => ({
      symbol: leader.symbol,
      name: leader.name,
      board: leader.board,
      reasons: [index === 0 ? '区间涨幅峰值' : `区间涨停 ${index + 1} 次`],
    })),
    leaders,
    index: {
      dates: ['2026-11-03', '2026-11-04'],
      active: [100, 105],
      pool: [100, 103],
      sh: [100, 101],
    },
    core_series: Object.fromEntries(leaders.slice(0, 5).map(leader => [leader.symbol, [100, 110]])),
    heatmap: { dates: [], rows: [] },
    breadth: [],
    seal: {
      date: '2026-11-04',
      sealed: [],
      broken: [],
      sealed_count: 0,
      broken_count: 0,
      touched: 0,
      seal_rate: null,
      share: null,
    },
    limit_route: {
      dates: ['2026-11-03', '2026-11-04'],
      rows: [],
      daily_leaders: [],
      leader_phases: [],
      switch_days: [{
        date: '2026-11-04',
        label: '领涨切换',
        reason: '股票1 → 股票2',
        symbols: ['000001.SZ', '000002.SZ'],
        minute_symbols: ['000001.SZ', '000002.SZ'],
        sealed: [],
        broken: [],
        new_starters: [],
        daily_leader: '000002.SZ',
        leader_name: '股票2',
        previous_leader: '000001.SZ',
        previous_leader_name: '股票1',
        has_minute: true,
      }],
      event_count: 0,
      seal_count: 0,
      space_leader_symbol: '000001.SZ',
      space_leader_name: '股票1',
      space_leader_peak_date: '2026-11-03',
    },
  }
}

async function flush() {
  await act(async () => {
    await new Promise(resolve => window.setTimeout(resolve, 0))
  })
}

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  mocks.themes.mockResolvedValue({
    items: [{
      id: 'ai',
      name: 'AI 算力',
      description: '',
      color: '#F59E0B',
      symbols: ['000001.SZ', '000002.SZ'],
      created_at: '2026-11-01',
      updated_at: '2026-11-01',
    }],
  })
  mocks.analysis.mockResolvedValue(analysis())
  mocks.minute.mockResolvedValue({
    theme_id: 'ai',
    date: '2026-11-04',
    status: 'no_data',
    stocks: [],
    times: [],
    series: {},
    table: { times: [], series: {} },
    features: {},
    missing: [],
  })
})

afterEach(() => {
  act(() => root.unmount())
  queryClient.clear()
  host.remove()
  vi.clearAllMocks()
})

it('shows core stocks, range controls, and the stock-pool entry without legacy panels', async () => {
  act(() => root.render(
    <QueryClientProvider client={queryClient}>
      <ThemeAnalyzerPage />
    </QueryClientProvider>,
  ))
  await flush()
  await flush()
  await vi.waitFor(() => expect(host.textContent).toContain('管理股票池'), { timeout: 2_000 })

  expect(host.textContent).toContain('核心股')
  expect(host.textContent).toContain('整波路径')
  expect(host.textContent).toContain('管理股票池')
  expect(host.textContent).toContain('仅沪深主板')
  expect(host.querySelector<HTMLInputElement>('input[type=checkbox]')?.checked).toBe(true)
  expect(host.textContent).not.toContain('逐日相对强弱热力图')
  expect(host.textContent).not.toContain('最新封板结构')
  expect(host.textContent).toContain('区间涨停 2 次')

  const showAll = [...host.querySelectorAll<HTMLButtonElement>('button')]
    .find(button => button.textContent?.includes('查看全部 6 只'))!
  act(() => showAll.click())
  expect(host.querySelectorAll('tbody tr')).toHaveLength(6)
})

it('keeps stock-pool edits local until save', async () => {
  act(() => root.render(
    <QueryClientProvider client={queryClient}>
      <ThemeAnalyzerPage />
    </QueryClientProvider>,
  ))
  await flush()
  await vi.waitFor(() => expect(host.textContent).toContain('管理股票池'), { timeout: 2_000 })

  const manage = [...host.querySelectorAll<HTMLButtonElement>('button')]
    .find(button => button.textContent?.includes('管理股票池'))!
  act(() => manage.click())
  await flush()

  const dialog = host.querySelector('[role="dialog"]')!
  const remove = dialog.querySelector<HTMLButtonElement>('button[aria-label="移除 000001.SZ"]')!
  act(() => remove.click())
  const cancel = [...dialog.querySelectorAll<HTMLButtonElement>('button')]
    .find(button => button.textContent === '取消')!
  act(() => cancel.click())

  expect(mocks.remove).not.toHaveBeenCalled()
  expect(mocks.add).not.toHaveBeenCalled()
})

it('formats minute percentage points without multiplying by 100 again', async () => {
  mocks.minute.mockResolvedValue({
    theme_id: 'ai',
    date: '2026-11-04',
    status: 'ok',
    stocks: [{
      symbol: '000001.SZ',
      name: '股票1',
      prev_close: 10,
      has_data: true,
      limit_pct: 10,
    }],
    times: ['09:31'],
    series: { '000001.SZ': [10.4] },
    table: { times: ['09:31'], series: { '000001.SZ': [4.0] } },
    features: {
      '000001.SZ': {
        sample: 5,
        complete: false,
        day: 4.0,
        open30: 4.0,
        am: 4.0,
        pm: 0.0,
        tail30: 0.0,
        max_dd: -1.0,
        vwap_dev: 0.0,
        up_ratio: 100.0,
      },
    },
    missing: [],
  })

  act(() => root.render(
    <QueryClientProvider client={queryClient}>
      <ThemeAnalyzerPage />
    </QueryClientProvider>,
  ))
  await vi.waitFor(() => expect(host.textContent).toContain('+4.00%'), { timeout: 2_000 })

  expect(host.textContent).toContain('-1.00%')
  expect(host.textContent).not.toContain('+400.00%')
  expect(host.textContent).not.toContain('-100.00%')
})
