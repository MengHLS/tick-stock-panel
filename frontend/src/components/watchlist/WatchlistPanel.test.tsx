// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  entries: vi.fn(),
  groups: vi.fn(),
}))

vi.mock('@/lib/api', () => ({
  api: {
    watchlistList: mocks.entries,
    watchlistGroups: mocks.groups,
  },
}))

import { WatchlistPanel } from './WatchlistPanel'

let host: HTMLDivElement
let root: Root
let queryClient: QueryClient
const flush = () => act(async () => { await new Promise(resolve => setTimeout(resolve, 0)) })

function renderPanel(onSelect = vi.fn(), activeSymbol?: string) {
  act(() => root.render(
    <QueryClientProvider client={queryClient}>
      <WatchlistPanel activeSymbol={activeSymbol} onSelect={onSelect} />
    </QueryClientProvider>,
  ))
  return onSelect
}

async function chooseGroup(label: string) {
  const trigger = host.querySelector<HTMLButtonElement>('button[aria-label="选择自选分组"]')!
  act(() => trigger.click())
  await flush()
  const option = [...document.body.querySelectorAll<HTMLButtonElement>('[role="menuitem"]')]
    .find(node => node.textContent?.includes(label))!
  act(() => option.click())
  await flush()
}

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  mocks.entries.mockResolvedValue({
    symbols: [
      { symbol: '600519.SH', name: '贵州茅台', added_at: '2026-11-01', group_ids: ['g-core'] },
      { symbol: '601318.SH', name: '中国平安', added_at: '2026-11-01', group_ids: ['g-core'] },
      { symbol: '603618.SH', name: '杭电股份', added_at: '2026-11-02' },
    ],
  })
  mocks.groups.mockResolvedValue({
    groups: [
      { id: 'g-core', name: '核心', color: 'blue' },
      { id: 'g-empty', name: '观察', color: 'rose' },
    ],
  })
})

afterEach(() => {
  act(() => root.unmount())
  queryClient.clear()
  host.remove()
  vi.clearAllMocks()
})

it('展示自选总数与分组，可切换到具体分组', async () => {
  renderPanel()
  await flush()
  await vi.waitFor(() => expect(host.textContent).toContain('贵州茅台'), { timeout: 2_000 })
  expect(host.textContent).toContain('3/3')

  await chooseGroup('核心')
  expect(host.textContent).toContain('2/3')
  expect(host.textContent).toContain('贵州茅台')
  expect(host.textContent).not.toContain('杭电股份')

  await chooseGroup('观察')
  expect(host.textContent).toContain('该分组暂无标的')
  expect(host.textContent).toContain('0/3')

  await chooseGroup('未分组')
  expect(host.textContent).toContain('1/3')
  expect(host.textContent).toContain('杭电股份')
})

it('本地筛选按名称或代码过滤', async () => {
  renderPanel()
  await flush()
  await vi.waitFor(() => expect(host.textContent).toContain('贵州茅台'), { timeout: 2_000 })

  const input = host.querySelector<HTMLInputElement>('input[aria-label="筛选自选标的"]')!
  act(() => {
    const setValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!
    setValue.call(input, '603618')
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await flush()
  expect(host.textContent).toContain('杭电股份')
  expect(host.textContent).not.toContain('贵州茅台')

  act(() => {
    const setValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!
    setValue.call(input, '不存在')
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await flush()
  expect(host.textContent).toContain('无匹配')
})

it('点击标的回调并高亮当前标的', async () => {
  const onSelect = renderPanel(vi.fn(), '603618.SH')
  await flush()
  await vi.waitFor(() => expect(host.textContent).toContain('贵州茅台'), { timeout: 2_000 })

  const active = host.querySelector<HTMLButtonElement>('button[aria-current="true"]')
  expect(active?.textContent).toContain('603618.SH')

  const target = [...host.querySelectorAll<HTMLButtonElement>('button')]
    .find(node => node.textContent?.includes('贵州茅台'))!
  act(() => target.click())
  expect(onSelect).toHaveBeenCalledWith('600519.SH', '贵州茅台')
})
