// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import extension, {
  FirstboardDiscovery,
  formatQValue,
  formatRatio,
  qualityFlags,
  ruleText,
} from './extension'

let root: Root | undefined
let container: HTMLDivElement | undefined

afterEach(() => {
  if (root) act(() => root!.unmount())
  container?.remove()
  vi.unstubAllGlobals()
  root = undefined
})

async function renderPage() {
  ;(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  await act(async () => {
    root!.render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })}>
        <FirstboardDiscovery />
      </QueryClientProvider>,
    )
  })
}

async function flush() {
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 25)) })
}

async function click(text: string) {
  const button = [...container!.querySelectorAll('button')].find(b => b.textContent?.includes(text))
  expect(button, `button ${text}`).toBeTruthy()
  await act(async () => button!.click())
  await flush()
}

const fixtureReport = {
  run_id: 'run-20261029', saved_at: '2026-10-29T14:00:00+00:00',
  generation: 'generation-1', algorithm_version: 'test-v1', elapsed_ms: 1000,
  sample: { status: 'ok', total_events: 80, eligible_events: 70, excluded_events: 10, excluded: { right_censored: 10 }, base_strong_rate: .2 },
  split: { train_start: '2024-01-01', train_end: '2025-01-01', validation_start: '2025-02-01', validation_end: '2026-01-01', train_count: 45, validation_count: 25, train_base_rate: .15, validation_base_rate: .25 },
  factors: [
    { factor_id: 'factor_a', label: '测试量能', snapshot: 'D_close', direction: 'high', auc: .6, q_value: .05, coverage: .9, validation_auc: .55, validation_count: 25 },
    { factor_id: 'factor_b', label: '测试位置', snapshot: 'D_minus_1', direction: 'low', auc: .3, q_value: .02, coverage: .8, validation_auc: .4, validation_count: 25 },
  ],
  rules: [{
    id: 'rule-1', conditions: [{ factor_id: 'factor_a', snapshot: 'D_close', operator: '>=', threshold: 1.5 }],
    dimension: 1, train_hits: 30, validation_hits: 20, validation_eligible: true,
    train_strong_rate: .3, validation_strong_rate: .35, lift: 2, validation_lift: 1.4,
    mean_mfe_5d: .08, mean_close_return_5d: .01, mean_mae_5d: -.03,
    mean_mfe_10d: .12, mean_close_return_10d: -.01, mean_mae_10d: -.06,
    mean_mfe_20d: .15, mean_close_return_20d: -.02, mean_mae_20d: -.08,
  }],
  warnings: ['测试提示：最高收益不是可兑现收益'],
}
const eventFixture = (name: string) => ({
  event_id: name, symbol: '000001.SZ', name, date: '2025-05-01', entry_date: '2025-05-06',
  mfe_5d: .08, close_return_5d: .02, mae_5d: -.03,
  mfe_10d: .12, close_return_10d: .04, mae_10d: -.05,
  mfe_20d: .25, close_return_20d: .05, mae_20d: -.08,
  strong: true, split: 'validation', rule_ids: ['rule-1'],
})
function mockResponses(report = fixtureReport, eventsGeneration = report.generation) {
  return vi.fn(async (url: string) => {
    const query = new URL(url, 'http://localhost')
    const eventsPayload = {
      generation: eventsGeneration, total: query.searchParams.has('rule_id') ? 1 : 80, page_size: 50,
      rows: [eventFixture(query.searchParams.has('rule_id') ? '规则样本' : query.searchParams.get('page') === '2' ? '第二页样本' : '全部样本')],
    }
    let payload: unknown
    if (query.pathname.endsWith('/runs')) {
      payload = {
        items: [{
          run_id: report.run_id, saved_at: report.saved_at, algorithm_version: report.algorithm_version,
          generation: report.generation, params: { start: '2024-01-01', end: '2026-10-28', snapshot_mode: 'both' },
          sample_status: report.sample.status, total_events: report.sample.total_events,
          eligible_events: report.sample.eligible_events, event_count: report.sample.total_events,
          factor_count: report.factors.length, rule_count: report.rules.length,
          train_count: report.split.train_count, validation_count: report.split.validation_count,
          elapsed_ms: report.elapsed_ms,
        }],
      }
    } else if (/\/runs\/[^/]+\/events$/.test(query.pathname) || query.pathname.endsWith('/events')) {
      payload = eventsPayload
    } else {
      payload = report
    }
    return { ok: true, json: async () => structuredClone(payload) }
  })
}

describe('first-board discovery extension', () => {
  it('registers an independent page and explains rule bounds and quality', () => {
    expect(extension.routes?.[0]?.path).toBe('/firstboard-discovery')
    expect(extension.navigation?.[0]?.label).toBe('首板因子区分')
    expect(qualityFlags({ right_censored: true })).toContain('20日未走完')
    expect(ruleText([{ factor_id: 'momentum_5d', snapshot: 'D_minus_1', operator: '>=', threshold: 0.1 }], {}))
      .toContain('T-1');
  })

  it('formats rates without return signs and keeps tiny q values legible', () => {
    expect(formatRatio(1)).toBe('100.00%')
    expect(formatRatio(.2)).toBe('20.00%')
    expect(formatRatio(null)).toBe('—')
    expect(formatQValue(0)).toBe('<0.001')
    expect(formatQValue(.0004)).toBe('<0.001')
    expect(formatQValue(.025)).toBe('0.025')
    expect(formatQValue(null)).toBe('—')
  })

  it('does not launch expensive research until the user starts it', async () => {
    const fetcher = vi.fn()
    vi.stubGlobal('fetch', fetcher)
    await renderPage()
    expect(container!.textContent).toContain('开始自动发现')
    expect(container!.textContent).toContain('T+1 开盘')
    expect(container!.textContent).toContain('试验结果待验证')
    expect(fetcher).not.toHaveBeenCalled()
  })

  it('renders report labels and supports rule filtering and pagination', async () => {
    vi.stubGlobal('fetch', mockResponses())
    await renderPage()
    await click('开始自动发现')
    await flush()
    expect(container!.textContent).toContain('测试量能')
    expect(container!.textContent).toContain('验证样本')
    expect(container!.textContent).toContain('90.00%')
    expect(container!.textContent).toContain('0.050')
    expect(container!.textContent).toContain('已保存结果')
    expect(container!.textContent).toContain('全部样本')
    expect(container!.textContent).toContain('最高收益不是可兑现收益')
    await click('下一页')
    expect(container!.textContent).toContain('第二页样本')
    await click('测试量能 >=')
    expect(container!.textContent).toContain('规则样本')
    expect(container!.textContent).toContain('第 1 页')
    expect(container!.textContent).not.toContain('第二页样本')
    await click('清除规则筛选')
    expect(container!.textContent).toContain('全部样本')
  })

  it('switches event outcome windows and reopens saved reports', async () => {
    const fetcher = mockResponses()
    vi.stubGlobal('fetch', fetcher)
    await renderPage()
    await click('开始自动发现')
    await flush()

    const windowSelect = container!.querySelector<HTMLSelectElement>('select[aria-label="事件收益窗口"]')
    expect(windowSelect).toBeTruthy()
    await act(async () => {
      windowSelect!.value = '5'
      windowSelect!.dispatchEvent(new Event('change', { bubbles: true }))
    })
    expect(container!.textContent).toContain('5 日最高收益')
    expect(container!.textContent).toContain('+8.00%')

    const savedSelect = container!.querySelector<HTMLSelectElement>('select[aria-label="已保存结果"]')
    expect(savedSelect).toBeTruthy()
    await act(async () => {
      savedSelect!.value = fixtureReport.run_id
      savedSelect!.dispatchEvent(new Event('change', { bubbles: true }))
    })
    await flush()
    await flush()
    expect(fetcher.mock.calls.some(([url]) => String(url).includes(`/runs/${fixtureReport.run_id}/report`))).toBe(true)
    expect(container!.textContent).toContain('全部样本')
  })

  it('shows report failures and allows retry', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce({
      ok: false, status: 503, json: async () => ({ detail: '后端尚未就绪' }),
    }).mockImplementation(mockResponses())
    vi.stubGlobal('fetch', fetcher)
    await renderPage()
    await click('开始自动发现')
    expect(container!.textContent).toContain('后端尚未就绪')
    await click('重试')
    await flush()
    expect(container!.textContent).toContain('全部样本')
  })

  it('hides event rows when their generation differs from the report', async () => {
    vi.stubGlobal('fetch', mockResponses(fixtureReport, 'new-generation'))
    await renderPage()
    await click('开始自动发现')
    await flush()
    expect(container!.textContent).toContain('数据版本已变化')
    expect(container!.textContent).not.toContain('全部样本')
  })

  it('shows no-data and insufficient-sample guidance', async () => {
    const report = { ...fixtureReport, factors: [], rules: [], sample: { ...fixtureReport.sample, status: 'insufficient_sample' } }
    vi.stubGlobal('fetch', mockResponses(report))
    await renderPage()
    await click('开始自动发现')
    await flush()
    expect(container!.textContent).toContain('样本不足，暂不生成自动规则')
    expect(container!.textContent).toContain('暂无可展示的因子')
    expect(container!.textContent).toContain('暂无满足训练支持度的规则')
  })

  it('keeps the form available during report loading', async () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})))
    await renderPage()
    await click('开始自动发现')
    expect(container!.textContent).toContain('加载行情、计算因子与训练规则中')
    expect(container!.querySelector<HTMLButtonElement>('button')!.disabled).toBe(true)
    expect(container!.querySelectorAll('input[type=date]').length).toBe(2)
  })

  it('keeps report visible when event loading fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => url.includes('/events?')
      ? { ok: false, status: 500, json: async () => ({ detail: '事件读取失败' }) }
      : { ok: true, json: async () => structuredClone(fixtureReport) }))
    await renderPage()
    await click('开始自动发现')
    await flush()
    expect(container!.textContent).toContain('因子区分能力')
    expect(container!.textContent).toContain('事件读取失败')
  })
})
