// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { expect, it, vi } from 'vitest'
import { api, type IndustryChainGraph } from '@/lib/api'
import { IndustryChainPage } from './Page'

const graph: IndustryChainGraph = {
  version: 1,
  updated_at: '',
  categories: [{ id: 'hard', name: '硬科技', order: 10 }],
  chains: [{ id: 'ai', category_id: 'hard', name: 'AI 产业链', order: 10 }],
  nodes: [
    { id: 'server', chain_id: 'ai', parent_id: null, name: 'AI 服务器', kind: 'product', description: '', order: 10 },
  ],
  stock_names: {},
  stock_links: [],
}

vi.mock('@/lib/api', () => ({
  ApiError: class ApiError extends Error {},
  api: {
    industryChainGraph: vi.fn(),
    industryChainQuotes: vi.fn(),
    industryChainSaveGraph: vi.fn(),
  },
}))

vi.mock('./GraphCanvas', () => ({
  GraphCanvas: ({ onAnalyze, onOpenStocks }: {
    onAnalyze: (target: { chainId: string; nodeId: string; name: string }) => void
    onOpenStocks: (target: { chainId: string; nodeId: string; name: string }) => void
  }) => (
    <>
      <button aria-label="打开股票" onClick={() => onOpenStocks({ chainId: 'ai', nodeId: 'server', name: 'AI 服务器' })} />
      <button aria-label="打开分析" onClick={() => onAnalyze({ chainId: 'ai', nodeId: 'server', name: 'AI 服务器' })} />
    </>
  ),
}))

vi.mock('./StockWorkspaceDialog', () => ({
  StockWorkspaceDialog: ({ target, initialAnalysis, onClose }: {
    target: { name: string }
    initialAnalysis: boolean
    onClose: () => void
  }) => (
    <div data-testid="workspace" data-analysis={String(initialAnalysis)}>
      {target.name}
      <button aria-label="关闭统一弹窗" onClick={onClose} />
    </div>
  ),
}))

it('股票入口与分析入口复用同一弹窗，分析只在主动进入时开启', async () => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  vi.mocked(api.industryChainGraph).mockResolvedValue(graph)
  vi.mocked(api.industryChainQuotes).mockResolvedValue({
    available: false,
    as_of: null,
    is_today: false,
    last_fetch_ms: null,
    status: {},
    rows: [],
  })
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  try {
    await act(async () => {
      root.render(
        <QueryClientProvider client={queryClient}>
          <IndustryChainPage />
        </QueryClientProvider>,
      )
    })
    for (let attempt = 0; attempt < 20 && !host.querySelector('button[aria-label="打开股票"]'); attempt += 1) {
      await act(async () => {
        await new Promise(resolve => setTimeout(resolve, 5))
      })
    }
    act(() => host.querySelector<HTMLButtonElement>('button[aria-label="打开股票"]')!.click())
    expect(host.querySelector('[data-testid="workspace"]')?.getAttribute('data-analysis')).toBe('false')

    act(() => host.querySelector<HTMLButtonElement>('button[aria-label="关闭统一弹窗"]')!.click())
    act(() => host.querySelector<HTMLButtonElement>('button[aria-label="打开分析"]')!.click())
    expect(host.querySelector('[data-testid="workspace"]')?.getAttribute('data-analysis')).toBe('true')
    expect(host.querySelectorAll('[data-testid="workspace"]')).toHaveLength(1)
  } finally {
    act(() => root.unmount())
    host.remove()
  }
})
