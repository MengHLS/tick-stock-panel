// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api, type MaxBoardRelayResult } from '@/lib/api'
import { MaxBoardPage } from './Page'

vi.mock('echarts', () => ({
  init: () => ({
    setOption: vi.fn(),
    resize: vi.fn(),
    dispose: vi.fn(),
    getDom: () => document.createElement('div'),
  }),
  graphic: {
    LinearGradient: class {
      constructor(..._args: unknown[]) {}
    },
  },
}))
const stockPreview = vi.hoisted(() => ({ open: vi.fn(() => true) }))
vi.mock('@/extensions/stockPreview', () => ({
  openStockPreview: stockPreview.open,
}))

const fixture: MaxBoardRelayResult = {
  as_of: '2026-11-10',
  range: { start: '2026-11-06', end: '2026-11-10', days: 3 },
  exclude_st: true,
  total: 2,
  series: [
    { date: '2026-11-06', height: 6, leaders: [{ symbol: '000001.SZ', name: '甲股份', boards: 6, change_pct: 0.1, close: 10 }] },
    { date: '2026-11-09', height: 4, leaders: [{ symbol: '000002.SZ', name: '乙科技', boards: 4, change_pct: 0.1, close: 8 }] },
    { date: '2026-11-10', height: 5, leaders: [{ symbol: '000003.SZ', name: '丙电子', boards: 5, change_pct: 0.1, close: 9 }] },
  ],
  current: {
    date: '2026-11-10', height: 5,
    leaders: [{ symbol: '000003.SZ', name: '丙电子', boards: 5, change_pct: 0.1, close: 9 }],
    delta_height: 1, last_break_date: '2026-11-09', days_since_break: 1,
    last_event: null,
  },
  events: [
    {
      id: '2026-11-09', break_date: '2026-11-09', previous_date: '2026-11-06',
      previous_height: 6,
      previous_leaders: [{ symbol: '000001.SZ', name: '甲股份', boards: 6, change_pct: 0.1, close: 10 }],
      break_day: {
        date: '2026-11-09', height: 4,
        leaders: [{ symbol: '000002.SZ', name: '乙科技', boards: 4, change_pct: 0.1, close: 8 }],
        former_leaders: [{ symbol: '000001.SZ', name: '甲股份', boards: 6, change_pct: -0.03, close: 9.7 }],
      },
      successor: {
        date: '2026-11-10', height: 5,
        leaders: [{ symbol: '000003.SZ', name: '丙电子', boards: 5, change_pct: 0.1, close: 9 }],
      },
      status: 'taken_over', height_gap: 1,
    },
    {
      id: '2026-10-30', break_date: '2026-10-30', previous_date: '2026-10-29',
      previous_height: 5,
      previous_leaders: [{ symbol: '000004.SZ', name: '丁材料', boards: 5, change_pct: 0.1, close: 12 }],
      break_day: {
        date: '2026-10-30', height: 2,
        leaders: [{ symbol: '000005.SZ', name: '戊股份', boards: 2, change_pct: 0.1, close: 6 }],
        former_leaders: [{ symbol: '000004.SZ', name: '丁材料', boards: 5, change_pct: -0.05, close: 11.4 }],
      },
      successor: { date: '2026-11-02', height: 1, leaders: [] },
      status: 'vacant', height_gap: 4,
    },
  ],
}

let host: HTMLDivElement
let root: Root
let client: QueryClient

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  stockPreview.open.mockClear()
  vi.stubGlobal('ResizeObserver', class {
    observe() {}
    disconnect() {}
  })
  vi.spyOn(api, 'maxBoardRelay').mockResolvedValue(fixture)
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } })
})

afterEach(async () => {
  await act(async () => root.unmount())
  client.clear()
  host.remove()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

async function settle() {
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)) })
}

async function render() {
  await act(async () => root.render(
    <QueryClientProvider client={client}><MaxBoardPage /></QueryClientProvider>,
  ))
  await settle()
}

it('展示当前最高板、断板接替链与详情联动', async () => {
  await render()
  expect(host.textContent).toContain('5板')
  expect(host.textContent).toContain('丙电子')
  expect(host.textContent).toContain('甲股份')
  expect(host.textContent).toContain('已接替')
  expect(host.textContent).toContain('事件详情')

  const vacant = host.querySelector<HTMLButtonElement>('[data-event-id="2026-10-30"]')!
  await act(async () => vacant.click())
  await settle()
  expect(host.textContent).toContain('丁材料')
  expect(host.textContent).toContain('空档')
})

it('切换区间会重新查询对应交易日窗口', async () => {
  await render()
  const button = [...host.querySelectorAll<HTMLButtonElement>('button')].find(el => el.textContent?.trim() === '30日')!
  await act(async () => button.click())
  await settle()
  expect(api.maxBoardRelay).toHaveBeenLastCalledWith(30)
})

it('点击接力链股票名称打开该股 K 线弹窗', async () => {
  await render()
  const stock = host.querySelector<HTMLButtonElement>('[data-stock="000001.SZ"]')!
  await act(async () => stock.click())
  await settle()
  expect(stockPreview.open).toHaveBeenCalledWith(expect.objectContaining({ symbol: '000001.SZ' }))
})
