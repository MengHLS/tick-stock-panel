// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { WyckoffResearchEvent, WyckoffResearchResponse } from '@/lib/api'

const mocks = vi.hoisted(() => ({
  events: vi.fn(),
  search: vi.fn(),
}))

vi.mock('@/lib/api', () => ({
  api: {
    wyckoffResearchEvents: mocks.events,
    instrumentSearch: mocks.search,
  },
}))

/** 图表与弹层在 jsdom 中不可渲染，改为捕获 props：断言标记日期、共用 as_of 与图层开关。 */
const chartProps = vi.hoisted(() => ({ current: null as Record<string, any> | null }))
vi.mock('@/components/StockDailyKChart', () => ({
  StockDailyKChart: (props: Record<string, any>) => {
    chartProps.current = props
    return <div data-testid="kline" />
  },
}))
vi.mock('@/components/DatePicker', () => ({
  DatePicker: ({ onChange }: { onChange: (value: string) => void }) => (
    <button type="button" data-testid="pick-asof" onClick={() => onChange('2026-11-06')}>选择截止日</button>
  ),
}))
vi.mock('@/components/financials/StockFinancialSearch', () => ({
  StockFinancialSearch: ({ onSelect }: { onSelect: (symbol: string, name: string) => void }) => (
    <button type="button" data-testid="pick-stock" onClick={() => onSelect('600519.SH', '贵州茅台')}>选股票</button>
  ),
}))

import { WyckoffResearchPage } from './Page'

function event(overrides: Partial<WyckoffResearchEvent>): WyckoffResearchEvent {
  return {
    event_id: 'wky-001',
    symbol: '600519.SH',
    asset_type: 'stock',
    timeframe: '1d',
    rule_version: 'wyckoff-daily-unfrozen-demo-0.1',
    params_hash: 'abcd1234abcd1234',
    data_generation: 'gen-1',
    as_of: '2026-11-06',
    event_type: 'Spring',
    phase: '吸筹区间',
    pattern_date: '2026-10-20',
    confirmed_at: '2026-10-23',
    available_at: '2026-10-23',
    available_at_basis: 'daily_close',
    status: 'confirmed',
    evidence: [
      { name: '下探支撑', actual: 1590.2, threshold: '< 1600.0', window: '1 日', computable: true },
      { name: '量比', actual: 1.82, threshold: '>= 1.5', window: '5 日', computable: true },
    ],
    invalidation_rule: '收盘跌破支撑：< 1587.2（1 日）',
    levels: { support: 1600, resistance: 1700, pattern_low: 1590.2 },
    linked_event_id: null,
    ...overrides,
  }
}

function payload(overrides: Partial<WyckoffResearchResponse> = {}): WyckoffResearchResponse {
  const events = [
    event({ event_id: 'wky-001' }),
    event({ event_id: 'wky-002', event_type: 'SOS', phase: '吸筹突破', pattern_date: '2026-10-28', confirmed_at: '2026-10-31', available_at: '2026-10-31' }),
    event({ event_id: 'wky-003', event_type: 'LPS', phase: '回踩确认', pattern_date: '2026-11-02', confirmed_at: '2026-11-05', available_at: '2026-11-05' }),
    event({
      event_id: 'wky-004', event_type: '失效', phase: '事件失效', pattern_date: '2026-11-06', confirmed_at: '2026-11-06',
      available_at: '2026-11-06', linked_event_id: 'wky-003',
      evidence: [{ name: '收盘跌破回踩低点', actual: 1610.1, threshold: '< 1618.4', window: '1 日', computable: true }],
      invalidation_rule: '失效事件不再二次失效',
    }),
    event({
      event_id: 'wky-c01', event_type: 'UTAD', phase: '派发候选', pattern_date: '2026-11-06',
      confirmed_at: null, available_at: null, status: 'candidate',
      evidence: [{ name: '连续转弱', actual: null, threshold: '>= 3 根', window: '3 日', computable: false }],
    }),
  ]
  return {
    symbol: '600519.SH',
    asset_type: 'stock',
    timeframe: '1d',
    as_of: '2026-11-06',
    window_bars: 120,
    rule_version: 'wyckoff-daily-unfrozen-demo-0.1',
    params_hash: 'abcd1234abcd1234',
    spec_status: 'unfrozen_demo',
    spec_source: null,
    status: 'ready',
    data_generation: 'gen-1',
    observed_bars: 200,
    events,
    candidates: [events[4]],
    ...overrides,
  }
}

let host: HTMLDivElement
let root: Root
let queryClient: QueryClient
const flush = () => act(async () => { await new Promise(resolve => setTimeout(resolve, 0)) })

function buttonByText(text: string) {
  return [...host.querySelectorAll<HTMLButtonElement>('button')].find(node => node.textContent?.includes(text))
}

/** 事件表与证据面板的条件表都有 tbody，测试只取事件表行。 */
function eventRows() {
  return [...host.querySelectorAll<HTMLTableRowElement>('[data-testid="event-table"] tbody tr')]
}

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  chartProps.current = null
  mocks.search.mockResolvedValue({ items: [] })
  mocks.events.mockResolvedValue(payload())
})

afterEach(() => {
  act(() => root.unmount())
  queryClient.clear()
  host.remove()
  vi.clearAllMocks()
})

function renderPage() {
  act(() => root.render(
    <QueryClientProvider client={queryClient}>
      <WyckoffResearchPage />
    </QueryClientProvider>,
  ))
}

it('默认关闭研究时不发起事件请求', async () => {
  renderPage()
  await flush()

  expect(host.textContent).toContain('研究未启用')
  expect(mocks.events).not.toHaveBeenCalled()
  const toggle = host.querySelector<HTMLButtonElement>('button[role="switch"]')!
  expect(toggle.getAttribute('aria-checked')).toBe('false')
  expect(host.querySelector('[data-testid="kline"]')).toBeNull()
})

it('开启研究但未选标的仍不请求', async () => {
  renderPage()
  await flush()
  act(() => host.querySelector<HTMLButtonElement>('button[role="switch"]')!.click())
  await flush()

  expect(host.textContent).toContain('未选标的')
  expect(mocks.events).not.toHaveBeenCalled()
})

it('选标的后共用 as_of，并把标记落在确认日', async () => {
  renderPage()
  await flush()
  act(() => host.querySelector<HTMLButtonElement>('button[role="switch"]')!.click())
  await flush()
  act(() => host.querySelector<HTMLButtonElement>('[data-testid="pick-stock"]')!.click())
  await vi.waitFor(() => expect(eventRows()).toHaveLength(5), { timeout: 2_000 })

  expect(mocks.events).toHaveBeenCalledTimes(1)
  expect(mocks.events.mock.calls[0][0]).toEqual({ symbol: '600519.SH', asOf: null, window: 120 })

  const markerDates = chartProps.current!.markers.map((marker: { date: string }) => marker.date).sort()
  expect(markerDates).toEqual(['2026-10-23', '2026-10-31', '2026-11-05', '2026-11-06'].sort())
  expect(markerDates).not.toContain('2026-10-20')  // 形态日不得作为标记日期
  expect(chartProps.current!.showLimitMarkers).toBe(false)
  expect(chartProps.current!.visibleBars).toBe(120)
  expect(chartProps.current!.dateRange.end).toBe('2026-11-06')

  // 失效是独立一条，原事件状态由它推导
  const rows = eventRows()
  const origin = rows.find(row => row.textContent?.includes('LPS'))!
  expect(origin.textContent).toContain('已失效')
  const invalidation = rows.find(row => row.textContent?.includes('事件失效'))!
  expect(invalidation.textContent).toContain('2026-11-06')

  // 选中失效事件后，证据面板给出与原事件的关联入口
  act(() => invalidation.querySelector('td')!.click())
  await vi.waitFor(() => expect(host.textContent).toContain('关联事件 wky-003'), { timeout: 2_000 })
  expect(host.textContent).toContain('收盘跌破回踩低点')

  // 候选没有确认日，也不给假确认
  const candidate = rows.find(row => row.textContent?.includes('UTAD'))!
  expect(candidate.textContent).toContain('候选')
  expect(candidate.textContent).toContain('不可计算')
  expect(host.textContent).toContain('规则未冻结')
})

it('关闭失效图层后不再绘制失效标记', async () => {
  renderPage()
  await flush()
  act(() => host.querySelector<HTMLButtonElement>('button[role="switch"]')!.click())
  act(() => host.querySelector<HTMLButtonElement>('[data-testid="pick-stock"]')!.click())
  await vi.waitFor(() => expect(chartProps.current).not.toBeNull(), { timeout: 2_000 })

  act(() => buttonByText('失效')!.click())
  await flush()
  expect(chartProps.current!.markers.some((marker: { label: string }) => marker.label === '失效')).toBe(false)
  expect(chartProps.current!.markers.some((marker: { label: string }) => marker.label === 'Spring')).toBe(true)
})

it('截止日期与图表共用同一边界', async () => {
  renderPage()
  await flush()
  act(() => host.querySelector<HTMLButtonElement>('button[role="switch"]')!.click())
  act(() => host.querySelector<HTMLButtonElement>('[data-testid="pick-stock"]')!.click())
  await vi.waitFor(() => expect(chartProps.current).not.toBeNull(), { timeout: 2_000 })

  act(() => host.querySelector<HTMLButtonElement>('[data-testid="pick-asof"]')!.click())
  await vi.waitFor(() => expect(mocks.events).toHaveBeenLastCalledWith({ symbol: '600519.SH', asOf: '2026-11-06', window: 120 }), { timeout: 2_000 })
  expect(chartProps.current!.dateRange.end).toBe('2026-11-06')
})

it('历史不足与不可计算分别呈现，不画图表冒充就绪', async () => {
  mocks.events.mockResolvedValue(payload({
    status: 'insufficient_data', events: [], candidates: [], observed_bars: 88, required_bars: 150,
  }))
  renderPage()
  await flush()
  act(() => host.querySelector<HTMLButtonElement>('button[role="switch"]')!.click())
  act(() => host.querySelector<HTMLButtonElement>('[data-testid="pick-stock"]')!.click())
  await vi.waitFor(() => expect(host.textContent).toContain('需要 150 交易日'), { timeout: 2_000 })
  expect(host.querySelector('[data-testid="kline"]')).toBeNull()
  expect(host.textContent).toContain('历史不足')

  queryClient.clear()
  mocks.events.mockResolvedValue(payload({ status: 'not_computable', events: [], candidates: [], missing_columns: ['volume'] }))
  act(() => host.querySelector<HTMLButtonElement>('[data-testid="pick-stock"]')!.click())
  await flush()
  await vi.waitFor(() => expect(host.textContent).toContain('缺少计算字段：volume'), { timeout: 2_000 })
  expect(host.textContent).toContain('不可计算')
})

it('请求失败保留参数并提供重试', async () => {
  mocks.events.mockRejectedValue(new Error('boom'))
  renderPage()
  await flush()
  act(() => host.querySelector<HTMLButtonElement>('button[role="switch"]')!.click())
  act(() => host.querySelector<HTMLButtonElement>('[data-testid="pick-stock"]')!.click())
  await vi.waitFor(() => expect(host.textContent).toContain('请求失败'), { timeout: 2_000 })

  mocks.events.mockResolvedValue(payload())
  act(() => buttonByText('重试')!.click())
  await vi.waitFor(() => expect(eventRows()).toHaveLength(5), { timeout: 2_000 })
  // 自动重试与手动重试都必须沿用同一组参数，不得回落到默认标的或窗口
  const calls = mocks.events.mock.calls.map(call => JSON.stringify(call[0]))
  expect(new Set(calls).size).toBe(1)
  expect(calls[0]).toContain('"window":120')
})

it('窗口长度进入查询键并切换图表可见根数', async () => {
  renderPage()
  await flush()
  act(() => host.querySelector<HTMLButtonElement>('button[role="switch"]')!.click())
  act(() => host.querySelector<HTMLButtonElement>('[data-testid="pick-stock"]')!.click())
  await vi.waitFor(() => expect(chartProps.current).not.toBeNull(), { timeout: 2_000 })

  act(() => buttonByText('250日')!.click())
  await vi.waitFor(() => expect(mocks.events).toHaveBeenLastCalledWith({ symbol: '600519.SH', asOf: null, window: 250 }), { timeout: 2_000 })
  // 窗口变化会重查：等新一轮就绪后再断言图表根数，避免读到卸载前的旧值
  await vi.waitFor(() => expect(chartProps.current!.visibleBars).toBe(250), { timeout: 2_000 })
  expect(eventRows()).toHaveLength(5)
})
