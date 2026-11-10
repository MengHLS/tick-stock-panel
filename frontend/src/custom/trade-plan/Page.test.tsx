// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api } from '@/lib/api'
import type { TradeStats } from './types'

(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true

vi.mock('echarts', () => ({
  init: () => ({
    setOption: vi.fn(),
    resize: vi.fn(),
    dispose: vi.fn(),
  }),
}))

const emptyStats: TradeStats = {
  total: 0,
  planned: 0,
  entered: 0,
  exited: 0,
  missed: 0,
  cancelled: 0,
  executed: 0,
  execution_rate: null,
  closed: 0,
  win_rate: null,
  avg_pnl_pct: null,
  total_pnl_pct: null,
  avg_r: null,
  total_r: null,
  avg_win_pct: null,
  avg_loss_pct: null,
  profit_factor: null,
  discipline_score: null,
  chase_count: 0,
  stop_breach_count: 0,
  flag_counts: [],
  by_setup: [],
  by_mood: [],
  equity_curve: [],
}

vi.mock('./client', () => ({
  tradePlanKeys: {
    list: (filters: unknown) => ['custom', 'trade-plan', 'plans', filters],
    reports: ['custom', 'trade-plan', 'reports'],
  },
  tradePlanApi: {
    list: vi.fn(() => Promise.resolve({ plans: [], stats: emptyStats })),
    reports: vi.fn(() => Promise.resolve({ reports: [] })),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
    saveReport: vi.fn(),
    deleteReport: vi.fn(),
  },
}))

import { TradePlanPage } from './Page'

let container: HTMLDivElement
let root: Root

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  act(() => {
    root.render(
      <QueryClientProvider client={queryClient}>
        <TradePlanPage />
      </QueryClientProvider>,
    )
  })
}

async function settle() {
  await act(async () => {
    await new Promise(resolve => setTimeout(resolve, 0))
  })
}

async function waitForText(text: string) {
  await act(async () => {
    for (let i = 0; i < 50; i += 1) {
      if (container.textContent?.includes(text)) return
      await new Promise(resolve => setTimeout(resolve, 10))
    }
  })
}

function click(text: string) {
  const button = [...container.querySelectorAll('button')]
    .find(item => item.textContent?.includes(text))
  if (!button) throw new Error(`button not found: ${text}`)
  act(() => button.dispatchEvent(new MouseEvent('click', { bubbles: true })))
}

beforeEach(() => {
  vi.clearAllMocks()
})

afterEach(() => {
  act(() => root?.unmount())
  container?.remove()
})

it('renders empty plan state and switches tabs', async () => {
  renderPage()
  await waitForText('还没有交易计划')

  expect(container.textContent).toContain('还没有交易计划')
  expect(container.textContent).toContain('计划 / 执行率')

  click('执行分析')
  expect(container.textContent).toContain('累计单笔收益')

  click('AI 复盘')
  expect(container.textContent).toContain('用计划与执行记录生成超短复盘')
})

it('opens the create form', async () => {
  renderPage()
  await settle()

  click('新建计划')
  expect(container.textContent).toContain('新建交易计划')
  expect(container.textContent).toContain('计划价格与仓位')
})

it('fills code and name from instrument search', async () => {
  const search = vi.spyOn(api, 'instrumentSearch').mockResolvedValue({
    results: [{ symbol: '000001.SZ', name: '平安银行', code: '000001', asset_type: 'stock' }],
  })
  renderPage()
  await waitForText('还没有交易计划')
  click('新建计划')

  const input = container.querySelector<HTMLInputElement>('input[placeholder="搜索代码或名称"]')
  if (!input) throw new Error('instrument search input not found')
  act(() => {
    const setValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set
    setValue?.call(input, '平安')
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })

  await waitForText('平安银行')
  click('平安银行')

  const code = container.querySelector<HTMLInputElement>('input[placeholder="600000.SH"]')
  const name = container.querySelector<HTMLInputElement>('input[placeholder="可选"]')
  expect(code?.value).toBe('000001.SZ')
  expect(name?.value).toBe('平安银行')
  search.mockRestore()
})
