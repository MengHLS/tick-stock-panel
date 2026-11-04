// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { expect, it, vi } from 'vitest'
import type { IndustryChainGraph } from '@/lib/api'
import { StockListPanel } from './StockListPanel'

const graph: IndustryChainGraph = {
  version: 1, updated_at: '',
  categories: [{ id: 'ai', name: '人工智能', order: 10 }],
  chains: [{ id: 'ai', category_id: 'ai', name: 'AI 产业链', order: 10 }],
  nodes: [
    { id: 'root', chain_id: 'ai', parent_id: null, name: '算力硬件', kind: 'segment', description: '', order: 10 },
    { id: 'server', chain_id: 'ai', parent_id: 'root', name: 'AI 服务器', kind: 'product', description: '', order: 10 },
  ],
  stock_names: { '000977.SZ': '浪潮信息', '603019.SH': '中科曙光' },
  stock_links: [
    { id: 'server-inspur', node_id: 'server', symbol: '000977.SZ', reason_short: 'AI服务器与智算整机', note: '主营AI服务器与智算整机', source_url: '', evidence_status: 'verified', basis: 'main_business', sort_order: 10 },
    { id: 'root-inspur', node_id: 'root', symbol: '000977.SZ', reason_short: '提供算力硬件产品', note: '参股某算力公司，待核验', source_url: '', evidence_status: 'pending', basis: 'theme_clue', sort_order: 10 },
    { id: 'server-sugon', node_id: 'server', symbol: '603019.SH', reason_short: '高性能计算与AI服务器', note: '市场传闻与客户合作，尚未证实', source_url: '', evidence_status: 'pending', basis: 'theme_clue', sort_order: 20 },
  ],
}

it('右侧列表去重股票，保留各处理由，支持筛选和编辑关联', () => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  const openLink = vi.fn()
  const close = vi.fn()
  try {
    act(() => root.render(
      <StockListPanel
        graph={graph}
        target={{ chainId: 'ai', nodeId: 'root', name: '算力硬件' }}
        onClose={close}
        onOpenLink={openLink}
        onAnalyze={vi.fn()}
        onAddStock={vi.fn()}
      />,
    ))
    expect(host.textContent).toContain('2 只股票')
    expect(host.textContent).toContain('3 条关联')
    expect(host.textContent).toContain('AI服务器与智算整机')
    expect(host.textContent).toContain('提供算力硬件产品')
    expect(host.textContent).toContain('主营/产品')
    expect(host.textContent).toContain('题材线索')
    const input = host.querySelector<HTMLInputElement>('input[aria-label="筛选股票列表"]')!
    act(() => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, '603019')
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
    expect(host.textContent).toContain('中科曙光')
    expect(host.textContent).not.toContain('浪潮信息')
    act(() => host.querySelector<HTMLButtonElement>('button[aria-label="编辑中科曙光关联：AI 服务器"]')!.click())
    expect(openLink).toHaveBeenCalledWith(graph.stock_links[2])
    act(() => host.querySelector<HTMLButtonElement>('button[aria-label="关闭股票列表"]')!.click())
    expect(close).toHaveBeenCalledOnce()
  } finally {
    act(() => root.unmount())
    host.remove()
  }
})

it('支持按参股、合作、传闻和核验状态筛选关联', () => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  try {
    act(() => root.render(
      <StockListPanel
        graph={graph}
        target={{ chainId: 'ai', nodeId: 'root', name: '算力硬件' }}
        onClose={vi.fn()}
        onOpenLink={vi.fn()}
        onAnalyze={vi.fn()}
        onAddStock={vi.fn()}
      />,
    ))

    const click = (label: string) => {
      act(() => host.querySelector<HTMLButtonElement>(`button[aria-label="${label}"]`)!.click())
    }

    click('筛选关联性质：参股')
    expect(host.textContent).toContain('浪潮信息')
    expect(host.textContent).toContain('提供算力硬件产品')
    expect(host.textContent).not.toContain('中科曙光')
    expect(host.textContent).toContain('1 只 / 1 条')

    click('筛选关联性质：传闻')
    expect(host.textContent).toContain('中科曙光')
    expect(host.textContent).not.toContain('浪潮信息')
    expect(host.textContent).toContain('传闻')

    click('筛选关联性质：合作')
    expect(host.textContent).toContain('中科曙光')

    click('筛选关联性质：全部')
    click('仅看已核验关联')
    expect(host.textContent).toContain('浪潮信息')
    expect(host.textContent).not.toContain('中科曙光')
    expect(host.textContent).toContain('1 只 / 1 条')
  } finally {
    act(() => root.unmount())
    host.remove()
  }
})

it('题材线索的免责声明不会被误判为供货关联', () => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  try {
    act(() => root.render(
      <StockListPanel
        graph={{
          ...graph,
          stock_links: [{
            id: 'theme-only',
            node_id: 'root',
            symbol: '000977.SZ',
            reason_short: '涨停题材：大模型',
            note: '历史涨停题材线索，未核验当前主营、产品或供货关系。',
            source_url: '',
            evidence_status: 'pending',
            basis: 'theme_clue',
            sort_order: 10,
          }],
        }}
        target={{ chainId: 'ai', nodeId: 'root', name: '算力硬件' }}
        onClose={vi.fn()}
        onOpenLink={vi.fn()}
        onAnalyze={vi.fn()}
        onAddStock={vi.fn()}
      />,
    ))
    expect(host.textContent).not.toContain('供货')
    act(() => host.querySelector<HTMLButtonElement>('button[aria-label="筛选关联性质：供应配套"]')!.click())
    expect(host.textContent).toContain('没有符合筛选条件的关联')
  } finally {
    act(() => root.unmount())
    host.remove()
  }
})
