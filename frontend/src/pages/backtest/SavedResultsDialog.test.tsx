// @vitest-environment jsdom
// 已保存结果弹窗交互回归:
// - 损坏/不支持记录被跳过时, 无论是否分页都要给出提示
// - 保存时未命名的记录显示「未命名结果」而不是空白
// - 删掉最后一页最后一条后回收到非空页, 不出现 total>0 却空页
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { SavedResultsDialog } from './SavedResultsDialog'
import type { SavedStrategyBacktestSummary } from '@/lib/api'

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  get: vi.fn(),
  del: vi.fn(),
}))

vi.mock('@/lib/api', () => ({
  api: {
    savedStrategyBacktestResults: mocks.list,
    savedStrategyBacktestResult: mocks.get,
    deleteSavedStrategyBacktestResult: mocks.del,
  },
}))
vi.mock('@/components/Toast', () => ({ toast: vi.fn() }))

function summary(index: number, overrides: Partial<SavedStrategyBacktestSummary> = {}): SavedStrategyBacktestSummary {
  return {
    schema_version: 1,
    saved_id: index.toString(16).padStart(16, '0'),
    run_id: `run-${index}`,
    name: `结果${index}`,
    strategy_id: 'first_limit_pullback_3f_runner_t74',
    strategy_name: '首板3F回踩 · T74 Runner',
    start: '2025-01-02',
    end: '2025-02-28',
    mode: 'position',
    n_trades: 3,
    total_return: 0.05,
    completed_at: '2026-10-28T09:00:00+00:00',
    saved_at: '2026-10-28T09:12:34+00:00',
    ...overrides,
  }
}

let container: HTMLDivElement
let root: Root

function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
}

async function flush(times = 4) {
  for (let i = 0; i < times; i += 1) {
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 15))
    })
  }
}

function buttonByText(text: string): HTMLButtonElement | undefined {
  return Array.from(container.querySelectorAll('button')).find(b => (b.textContent ?? '').includes(text))
}

beforeEach(() => {
  ;(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  mocks.list.mockReset()
  mocks.get.mockReset()
  mocks.del.mockReset()
})

afterEach(async () => {
  await act(async () => root.unmount())
  container.remove()
  vi.unstubAllGlobals()
})

function render(onOpen = vi.fn(), onDeleted = vi.fn()) {
  act(() => {
    root.render(
      <QueryClientProvider client={makeClient()}>
        <SavedResultsDialog onOpen={onOpen} onDeleted={onDeleted} onClose={vi.fn()} />
      </QueryClientProvider>,
    )
  })
}

it('shows the skipped-record warning and falls back for a null name', async () => {
  mocks.list.mockResolvedValue({
    items: [summary(1, { name: null, strategy_name: null })],
    page: 1,
    page_size: 20,
    total: 1,
    has_more: false,
    skipped: 2,
  })
  render()
  await flush()
  const text = container.textContent ?? ''
  expect(text).toContain('有 2 条保存记录已损坏或版本不受支持')
  expect(text).toContain('未命名结果')
})

it('recycles to a non-empty page after deleting the last row of the last page', async () => {
  const pageOne = Array.from({ length: 20 }, (_, i) => summary(i + 1))
  mocks.list.mockImplementation(async (page: number) => ({
    items: page === 1 ? pageOne : [summary(21)],
    page,
    page_size: 20,
    total: 21,
    has_more: page === 1,
    skipped: 0,
  }))
  mocks.del.mockResolvedValue({ ok: true })
  vi.stubGlobal('confirm', vi.fn(() => true))

  render()
  await flush()

  const next = buttonByText('下一页')
  expect(next).toBeTruthy()
  await act(async () => { next!.click() })
  await flush()
  expect(mocks.list).toHaveBeenLastCalledWith(2, 20)

  const del = Array.from(container.querySelectorAll('button'))
    .find(b => (b.getAttribute('aria-label') ?? '').startsWith('删除已保存结果'))
  expect(del).toBeTruthy()
  await act(async () => { del!.click() })
  await flush(6)

  expect(mocks.del).toHaveBeenCalledWith(summary(21).saved_id)
  expect(mocks.list).toHaveBeenLastCalledWith(1, 20)
})
