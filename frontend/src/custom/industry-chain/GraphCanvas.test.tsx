// @vitest-environment jsdom
import { act, useState } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { IndustryChainGraph } from '@/lib/api'
import { GraphCanvas } from './GraphCanvas'
import { buildLayout, chainKey, nodeKey, searchGraph } from './layout'

const graph: IndustryChainGraph = {
  version: 1,
  updated_at: '',
  categories: [{ id: 'ai', name: '人工智能', order: 10 }],
  chains: [{ id: 'ai', category_id: 'ai', name: 'AI 产业链', order: 10 }],
  nodes: [
    { id: 'base', chain_id: 'ai', parent_id: null, name: '基础层', kind: 'segment', description: '', order: 10 },
    ...Array.from({ length: 24 }, (_, index) => ({
      id: `leaf-${index}`, chain_id: 'ai', parent_id: 'base',
      name: `末级 ${index}`, kind: 'product' as const, description: '', order: index,
    })),
  ],
  stock_links: [],
}

let host: HTMLDivElement
let root: Root
let resizeViewport: (width: number, height: number) => void

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  vi.stubGlobal('ResizeObserver', class {
    constructor(callback: ResizeObserverCallback) {
      resizeViewport = (width, height) => callback(
        [{ contentRect: { width, height } } as ResizeObserverEntry],
        this as unknown as ResizeObserver,
      )
    }
    observe() { resizeViewport(1000, 700) }
    disconnect() {}
  })
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
})

afterEach(() => {
  act(() => root.unmount())
  host.remove()
  vi.unstubAllGlobals()
})

function Harness({ resetSignal = 1, query = '' }: { resetSignal?: number; query?: string }) {
  const [expanded, setExpanded] = useState(new Set([chainKey('ai')]))
  const search = searchGraph(graph, query)
  return (
    <GraphCanvas
      layout={buildLayout(graph, expanded, search)}
      search={search}
      resetSignal={resetSignal}
      onToggle={key => setExpanded(current => {
        const next = new Set(current)
        if (next.has(key)) next.delete(key)
        else next.add(key)
        return next
      })}
      onAnalyze={vi.fn()}
      onAddStock={vi.fn()}
      onOpenStocks={vi.fn()}
    />
  )
}

function transform() {
  return host.querySelector<HTMLElement>('.origin-top-left')!.style.transform
}

function click(selector: string) {
  act(() => host.querySelector<HTMLElement>(selector)!.click())
}

function screenPosition(label: string) {
  const card = host.querySelector(`[aria-label="${label}"]`)!.closest<HTMLElement>('[data-graph-node]')!
  const values = transform().match(/translate\(([-\d.e]+)px,\s*([-\d.e]+)px\) scale\(([-\d.e]+)\)/)!
  const [offsetX, offsetY, scale] = values.slice(1).map(Number)
  return {
    x: offsetX + parseFloat(card.style.left) * scale,
    y: offsetY + parseFloat(card.style.top) * scale,
    scale,
  }
}

it('展开和折叠大分支保留缩放并固定点击节点的位置', () => {
  act(() => root.render(<Harness />))
  click('button[title="放大"]')
  const before = screenPosition('基础层，已折叠')

  click('[aria-label="基础层，已折叠"]')
  expect(host.querySelector('[aria-label="末级 23"]')).not.toBeNull()
  const expanded = screenPosition('基础层，已展开')
  expect(expanded.x).toBeCloseTo(before.x)
  expect(expanded.y).toBeCloseTo(before.y)
  expect(expanded.scale).toBe(before.scale)

  click('[aria-label="基础层，已展开"]')
  expect(host.querySelector('[aria-label="末级 23"]')).toBeNull()
  const collapsed = screenPosition('基础层，已折叠')
  expect(collapsed.x).toBeCloseTo(before.x)
  expect(collapsed.y).toBeCloseTo(before.y)
  expect(collapsed.scale).toBe(before.scale)
})

it('只在主动适应或收到新的恢复信号时重新适配图谱', () => {
  act(() => root.render(<Harness />))
  click('[aria-label="基础层，已折叠"]')
  click('button[title="放大"]')
  const enlarged = transform()
  click('button[title="适应画布"]')
  const fitted = transform()
  expect(fitted).not.toBe(enlarged)

  click('button[title="放大"]')
  expect(transform()).not.toBe(fitted)
  act(() => root.render(<Harness resetSignal={2} />))
  expect(transform()).toBe(fitted)

  const beforeCollapse = screenPosition('基础层，已展开')
  click('[aria-label="基础层，已展开"]')
  const afterCollapse = screenPosition('基础层，已折叠')
  expect(afterCollapse.y).toBeCloseTo(beforeCollapse.y)
  expect(afterCollapse.scale).toBe(beforeCollapse.scale)
})

it('窗口尺寸变化和普通重渲染不覆盖用户视角', () => {
  act(() => root.render(<Harness />))
  click('button[title="放大"]')
  const before = transform()
  act(() => resizeViewport(760, 600))
  expect(transform()).toBe(before)
  act(() => root.render(<Harness />))
  expect(transform()).toBe(before)
})

it('新的搜索仍展开命中路径并定位节点', () => {
  act(() => root.render(<Harness />))
  const before = transform()
  act(() => root.render(<Harness query="末级 23" />))
  expect(host.querySelector('[aria-label="末级 23"]')).not.toBeNull()
  expect(transform()).not.toBe(before)
})

it('末级环节打开右侧股票列表，不展开股票节点或改变视角', () => {
  const withStocks: IndustryChainGraph = {
    ...graph,
    stock_names: { '000977.SZ': '浪潮信息' },
    stock_links: [{
      id: 'stock', node_id: 'leaf-0', symbol: '000977.SZ',
      reason_short: 'AI服务器与智算整机', note: '', source_url: '',
      evidence_status: 'verified', basis: 'main_business', sort_order: 10,
    }],
  }
  const openStocks = vi.fn()
  const toggle = vi.fn()
  act(() => root.render(
    <GraphCanvas
      layout={buildLayout(withStocks, new Set([chainKey('ai'), nodeKey('base')]), searchGraph(withStocks, ''))}
      search={searchGraph(withStocks, '')}
      resetSignal={1}
      onToggle={toggle}
      onAnalyze={vi.fn()}
      onAddStock={vi.fn()}
      onOpenStocks={openStocks}
    />,
  ))
  const before = transform()
  click('[aria-label="末级 0，查看股票列表"]')
  expect(openStocks).toHaveBeenCalledWith({ chainId: 'ai', nodeId: 'leaf-0', name: '末级 0' })
  expect(toggle).not.toHaveBeenCalled()
  expect(transform()).toBe(before)
  expect(host.textContent).not.toContain('浪潮信息')
  click('[aria-label="查看基础层股票列表"]')
  expect(openStocks).toHaveBeenLastCalledWith({ chainId: 'ai', nodeId: 'base', name: '基础层' })
})
