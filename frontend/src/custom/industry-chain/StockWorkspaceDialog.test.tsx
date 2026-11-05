// @vitest-environment jsdom
import { act, type ComponentProps } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, expect, it, vi } from 'vitest'
import type { IndustryChainGraph } from '@/lib/api'
import { api } from '@/lib/api'
import { clearFocusSymbol, setFocusSymbol } from '@/lib/useQuoteStream'
import { StockWorkspaceDialog } from './StockWorkspaceDialog'

const capability = vi.hoisted(() => ({ usable: true }))

vi.mock('@/lib/api', () => ({
  api: { industryChainAnalysis: vi.fn() },
}))

vi.mock('@/lib/useQuoteStream', () => ({
  setFocusSymbol: vi.fn(),
  clearFocusSymbol: vi.fn(),
}))

vi.mock('./AnalysisPanel', () => ({
  AnalysisPanel: ({ onClose, error }: { onClose: () => void; error: string | null }) => (
    <aside data-testid="analysis">
      {error}
      <button onClick={onClose} aria-label="关闭分析面板">返回股票行情</button>
    </aside>
  ),
}))

vi.mock('@/components/StockDailyKChart', () => ({
  getDefaultRange: () => ({ start: '2026-05-05', end: '2026-11-05' }),
  StockDailyKChart: ({ symbol, dateRange }: { symbol: string; dateRange: { start: string; end: string } }) => (
    <div data-testid="daily-chart" data-range={JSON.stringify(dateRange)}>{symbol}</div>
  ),
}))

vi.mock('@/components/StockMultiDayIntradayChart', () => ({
  StockMultiDayIntradayChart: ({ symbol, days }: { symbol: string; days: number }) => (
    <div data-testid="intraday-chart">{symbol}:{days}</div>
  ),
}))

vi.mock('@/lib/useSharedQueries', () => ({
  useCapabilityMatrix: () => ({ data: { capabilities: [{ id: 'minute', usable: capability.usable }] } }),
  usePreferences: () => ({ data: { minute_intraday_refresh_interval: 6 } }),
}))

const graph: IndustryChainGraph = {
  version: 1,
  updated_at: '',
  categories: [{ id: 'hard', name: '硬科技', order: 10 }],
  chains: [{ id: 'ai', category_id: 'hard', name: 'AI 产业链', order: 10 }],
  nodes: [
    { id: 'base', chain_id: 'ai', parent_id: null, name: '基础层', kind: 'segment', description: '底层能力。', order: 10 },
    { id: 'server', chain_id: 'ai', parent_id: 'base', name: 'AI 服务器', kind: 'product', description: '训练与推理服务器。', order: 10 },
    { id: 'empty', chain_id: 'ai', parent_id: 'base', name: '空环节', kind: 'product', description: '暂无关联。', order: 20 },
  ],
  stock_names: { '000977.SZ': '浪潮信息', '603019.SH': '中科曙光' },
  stock_links: [
    {
      id: 'server-inspur', node_id: 'server', symbol: '000977.SZ', reason_short: 'AI服务器与智算整机',
      note: '主营服务器', source_url: '', evidence_status: 'verified', basis: 'main_business', sort_order: 10,
    },
    {
      id: 'server-sugon', node_id: 'server', symbol: '603019.SH', reason_short: '高性能计算与AI服务器',
      note: '待核验', source_url: '', evidence_status: 'pending', basis: 'theme_clue', sort_order: 20,
    },
  ],
}

const quotes = {
  available: true,
  as_of: '2026-11-05',
  is_today: true,
  last_fetch_ms: 1_760_000_000_000,
  status: { enabled: true, running: true },
  rows: [
    { symbol: '000977.SZ', price: 103.66, prev_close: 100, change_pct: 0.0366, change_amount: 3.66 },
    { symbol: '603019.SH', price: 99, prev_close: 100, change_pct: -0.01, change_amount: -1 },
  ],
}

beforeEach(() => {
  capability.usable = true
  vi.clearAllMocks()
  vi.mocked(api.industryChainAnalysis).mockRejectedValue(new Error('分析暂不可用'))
})

function renderDialog(targetNode = 'server', overrides: Partial<ComponentProps<typeof StockWorkspaceDialog>> = {}) {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  const props: ComponentProps<typeof StockWorkspaceDialog> = {
    graph,
    target: { chainId: 'ai', nodeId: targetNode, name: targetNode === 'server' ? 'AI 服务器' : '空环节' },
    quotes,
    saving: false,
    saveError: null,
    onClose: vi.fn(),
    onSaveGraph: async () => undefined,
    onDeleteGraph: async () => undefined,
    ...overrides,
  }
  const render = (next: Partial<typeof props> = {}) => act(() => root.render(
    <QueryClientProvider client={queryClient}>
      <StockWorkspaceDialog {...props} {...next} />
    </QueryClientProvider>,
  ))
  render()
  return { host, root, render, queryClient }
}

function click(host: HTMLElement, label: string) {
  act(() => host.querySelector<HTMLButtonElement>(`button[aria-label="${label}"]`)!.click())
}

it('末级节点默认选中第一只股票，单击切股且日线/分时原位切换', () => {
  const { host, root } = renderDialog()
  try {
    expect(host.textContent).toContain('AI 服务器')
    expect(host.textContent).toContain('训练与推理服务器')
    expect(host.querySelector('[data-testid="daily-chart"]')?.textContent).toBe('000977.SZ')
    expect(host.textContent).toContain('+3.66%')

    click(host, '选择中科曙光')
    expect(host.querySelector('[data-testid="daily-chart"]')?.textContent).toBe('603019.SH')
    expect(host.textContent).toContain('-1.00%')

    act(() => host.querySelector<HTMLButtonElement>('button[role="tab"]:nth-child(2)')!.click())
    expect(host.querySelector('[data-testid="intraday-chart"]')?.textContent).toBe('603019.SH:1')

    click(host, '选择浪潮信息')
    expect(host.querySelector('[data-testid="intraday-chart"]')?.textContent).toBe('000977.SZ:1')
    expect(host.querySelector<HTMLButtonElement>('button[role="tab"]:nth-child(2)')!.getAttribute('aria-selected')).toBe('true')
  } finally {
    act(() => root.unmount())
    host.remove()
  }
})

it('筛选移除当前股票时选中第一只，结果为空时清空图表', () => {
  const { host, root } = renderDialog()
  try {
    click(host, '选择中科曙光')
    const input = host.querySelector<HTMLInputElement>('input[aria-label="筛选股票列表"]')!
    act(() => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, '000977')
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
    expect(host.querySelector('[data-testid="daily-chart"]')?.textContent).toBe('000977.SZ')

    act(() => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, '不存在')
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
    expect(host.textContent).toContain('没有符合筛选条件的关联')
    expect(host.textContent).toContain('暂无关联股票')
    expect(host.querySelector('[data-testid="daily-chart"]')).toBeNull()
  } finally {
    act(() => root.unmount())
    host.remove()
  }
})

it('搜索命中优先选中，行情刷新保留当前选择、分时周期与列表滚动', () => {
  const { host, root, render } = renderDialog('server', {
    target: { chainId: 'ai', nodeId: 'server', name: 'AI 服务器', initialSymbol: '603019.SH' },
  })
  try {
    expect(host.querySelector('[data-testid="daily-chart"]')?.textContent).toBe('603019.SH')
    act(() => host.querySelector<HTMLButtonElement>('button[role="tab"]:nth-child(2)')!.click())
    act(() => Array.from(host.querySelectorAll('button')).find(button => button.textContent === '5日')!.click())
    const list = host.querySelector<HTMLElement>('[aria-label="AI 服务器股票列表"] .overflow-y-auto')!
    list.scrollTop = 45
    click(host, '选择浪潮信息')
    render({ quotes: { ...quotes, rows: quotes.rows.map(row => ({ ...row, change_pct: 0.02 })) } })
    expect(host.querySelector('[data-testid="intraday-chart"]')?.textContent).toBe('000977.SZ:5')
    expect(list.scrollTop).toBe(45)
  } finally {
    act(() => root.unmount())
    host.remove()
  }
})

it('编辑返回保留筛选、选股与日线范围', () => {
  const { host, root } = renderDialog()
  try {
    act(() => Array.from(host.querySelectorAll('button')).find(button => button.textContent === '1年')!.click())
    const range = host.querySelector('[data-testid="daily-chart"]')!.getAttribute('data-range')
    click(host, '仅看已核验关联')
    click(host, '编辑浪潮信息关联：AI 服务器')
    click(host, '关闭')
    expect(host.querySelector('button[aria-label="仅看已核验关联"]')!.getAttribute('aria-pressed')).toBe('true')
    expect(host.querySelector('[data-testid="daily-chart"]')!.getAttribute('data-range')).toBe(range)
    expect(host.querySelector('[data-testid="daily-chart"]')!.textContent).toBe('000977.SZ')
  } finally {
    act(() => root.unmount())
    host.remove()
  }
})

it('分钟能力不可用时显示提示，日线仍可使用；关闭释放焦点订阅', () => {
  capability.usable = false
  const { host, root } = renderDialog()
  try {
    expect(setFocusSymbol).toHaveBeenLastCalledWith('000977.SZ')
    act(() => host.querySelector<HTMLButtonElement>('button[role="tab"]:nth-child(2)')!.click())
    expect(host.textContent).toContain('当前数据源未提供分钟K能力')
    expect(host.querySelector('[data-testid="intraday-chart"]')).toBeNull()
    act(() => host.querySelector<HTMLButtonElement>('button[role="tab"]:first-child')!.click())
    expect(host.querySelector('[data-testid="daily-chart"]')).not.toBeNull()
    act(() => root.unmount())
    expect(clearFocusSymbol).toHaveBeenCalled()
  } finally {
    host.remove()
  }
})

it('分析仅主动打开时查询，在原弹窗显示错误并可返回行情', async () => {
  const { host, root } = renderDialog()
  try {
    expect(api.industryChainAnalysis).not.toHaveBeenCalled()
    await act(async () => {
      Array.from(host.querySelectorAll('button')).find(button => button.textContent === '行情分析')!.click()
    })
    expect(api.industryChainAnalysis).toHaveBeenCalledWith({ chainId: 'ai', nodeId: 'server' })
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 20))
    })
    expect(host.textContent).toContain('分析暂不可用')
    expect(host.querySelectorAll('[role="dialog"]')).toHaveLength(1)
    click(host, '关闭分析面板')
    expect(host.querySelector('[data-testid="daily-chart"]')?.textContent).toBe('000977.SZ')
  } finally {
    act(() => root.unmount())
    host.remove()
  }
})

it('编辑关联在同一弹窗内打开表单，取消后回到原股票与图表', () => {
  const { host, root } = renderDialog()
  try {
    click(host, '选择中科曙光')
    click(host, '编辑中科曙光关联：AI 服务器')
    expect(host.textContent).toContain('编辑股票关联')
    expect(host.querySelector('[data-testid="daily-chart"]')!.closest('.hidden')).not.toBeNull()

    act(() => host.querySelector<HTMLButtonElement>('aside button[aria-label="关闭"]')!.click())
    expect(host.querySelector('[data-testid="daily-chart"]')?.textContent).toBe('603019.SH')
  } finally {
    act(() => root.unmount())
    host.remove()
  }
})

it('无关联股票的末级节点显示空状态和添加入口', () => {
  const { host, root } = renderDialog('empty')
  try {
    expect(host.textContent).toContain('暂无关联股票')
    expect(host.textContent).toContain('添加股票')
  } finally {
    act(() => root.unmount())
    host.remove()
  }
})
