// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { FactorDiscovery, PRESETS } from './FactorDiscovery'
import { unavailableReasonLabel } from '@/custom/monitor/Page'
import { api } from '@/lib/api'

vi.mock('@/lib/api', () => ({
  api: {
    factorColumns: vi.fn(async () => ({ columns: [] })),
    watchlistList: vi.fn(async () => ({ symbols: [] })),
    factorBatch: vi.fn(),
    researchCandidateCreate: vi.fn(),
  },
}))

const columns = [
  {
    id: 'industry_relative_momentum_20d',
    label: '行业相对动量',
    group: '截面联动',
    desc: '个股动量减同业均值',
  },
  {
    id: 'industry_corr_60d',
    label: '行业相关性',
    group: '截面联动',
    desc: '与行业基准的 60 日相关性',
  },
]

let host: HTMLDivElement
let root: Root
let client: QueryClient

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  vi.clearAllMocks()
  localStorage.clear()
  sessionStorage.clear()
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
  client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  vi.mocked(api.factorColumns).mockResolvedValue({ columns })
})

afterEach(async () => {
  await act(async () => root.unmount())
  client.clear()
  host.remove()
})

async function flush() {
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 25)) })
}

async function renderPage() {
  await act(async () => root.render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <FactorDiscovery />
      </QueryClientProvider>
    </MemoryRouter>,
  ))
  await flush()
}

async function click(text: string) {
  const button = [...host.querySelectorAll('button')]
    .find(item => item.textContent?.includes(text))
  expect(button, `button ${text}`).toBeTruthy()
  await act(async () => button!.click())
  await flush()
}

it('defines a linkage preset and selects the whole group', async () => {
  const preset = PRESETS.find(item => item.id === 'linkage')
  expect(preset).toEqual({
    id: 'linkage',
    label: '截面联动',
    hint: '基准偏离与行业联动',
    groups: ['截面联动'],
  })

  await renderPage()
  await click('截面联动')
  await click('筛选 2 个因子')

  expect(api.factorBatch).toHaveBeenCalledWith(
    expect.objectContaining({
      factor_names: [
        'industry_relative_momentum_20d',
        'industry_corr_60d',
      ],
    }),
    expect.any(AbortSignal),
  )
})

it('shows sidecar coverage errors without unmounting the configuration', async () => {
  vi.mocked(api.factorBatch).mockRejectedValue(
    new Error('联动因子覆盖不足: 缺 sidecar 分区 2026-04-07'),
  )
  await renderPage()
  await click('截面联动')
  await click('筛选 2 个因子')

  expect(host.textContent).toContain('联动因子覆盖不足')
  expect(host.textContent).toContain('选择因子')
  expect(host.textContent).toContain('资产与范围')
})

it('renders the backend daily-close-only reason as a clear status', () => {
  expect(unavailableReasonLabel('daily_close_only')).toBe('仅日频可用')
  expect(unavailableReasonLabel('sidecar_missing')).toBe('sidecar_missing')
})

it('keeps the configuration visible while factors load or are empty', async () => {
  vi.mocked(api.factorColumns).mockReturnValue(new Promise(() => {}))
  await renderPage()
  expect(host.textContent).toContain('因子加载中')
  expect(host.textContent).toContain('选择因子')

  await act(async () => root.unmount())
  client.clear()
  root = createRoot(host)
  vi.mocked(api.factorColumns).mockResolvedValue({ columns: [] })
  await renderPage()
  expect(host.textContent).toContain('无匹配因子')
  expect(host.textContent).toContain('资产与范围')
  expect(host.querySelector('.grid-cols-1')).toBeTruthy()
})
