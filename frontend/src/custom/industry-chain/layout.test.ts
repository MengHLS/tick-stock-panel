// @vitest-environment node
import { describe, expect, it } from 'vitest'
import type { IndustryChainGraph } from '@/lib/api'
import {
  buildLayout,
  categoryKey,
  chainKey,
  defaultExpandedKeys,
  nodeKey,
  searchGraph,
  stockKey,
  stockChainAssociations,
  stockLinksForScope,
} from './layout'

const GRAPH: IndustryChainGraph = {
  version: 1,
  updated_at: '2026-11-04T10:00:00+00:00',
  stock_names: {
    '300308.SZ': '中际旭创',
    '300285.SZ': '国瓷材料',
  },
  categories: [
    { id: 'electronics', name: '电子与通信', order: 10 },
  ],
  chains: [
    { id: 'optical', category_id: 'electronics', name: '光通信', order: 10 },
    { id: 'mlcc', category_id: 'electronics', name: 'MLCC', order: 20 },
  ],
  nodes: [
    { id: 'module', chain_id: 'optical', parent_id: null, name: '光模块与光引擎', kind: 'segment', description: '', order: 10 },
    { id: 'datacom', chain_id: 'optical', parent_id: 'module', name: '数通高速光模块', kind: 'product', description: '', order: 10 },
    { id: 'material', chain_id: 'mlcc', parent_id: null, name: '上游材料', kind: 'segment', description: '', order: 10 },
  ],
  stock_links: [
    {
      id: 'l1', node_id: 'datacom', symbol: '300308.SZ', reason_short: '研发制造高速光收发模块',
      note: '', source_url: 'https://www.innolight.com/', evidence_status: 'verified',
      basis: 'main_business', sort_order: 10,
    },
    {
      id: 'l2', node_id: 'module', symbol: '300308.SZ', reason_short: '布局光模块与光引擎',
      note: '', source_url: '', evidence_status: 'pending', basis: 'theme_clue', sort_order: 20,
    },
    {
      id: 'l3', node_id: 'material', symbol: '300285.SZ', reason_short: '提供电容用陶瓷介电材料',
      note: '', source_url: 'https://www.sinocera.cn/', evidence_status: 'verified',
      basis: 'supply', sort_order: 10,
    },
  ],
}

const SINGLE_CHAIN_GRAPH: IndustryChainGraph = {
  version: 1,
  updated_at: '2026-11-04T10:00:00+00:00',
  stock_names: {},
  categories: [
    { id: 'ai', name: '人工智能', order: 10 },
  ],
  chains: [
    { id: 'ai-industry', category_id: 'ai', name: 'AI 产业链', order: 10 },
  ],
  nodes: [
    { id: 'base', chain_id: 'ai-industry', parent_id: null, name: '基础层', kind: 'segment', description: '', order: 10 },
  ],
  stock_links: [],
}

describe('industry-chain layout', () => {
  it('按股票代码查找其他产业链的位置和独立理由', () => {
    const graph: IndustryChainGraph = {
      ...GRAPH,
      stock_links: [
        ...GRAPH.stock_links,
        {
          ...GRAPH.stock_links[0], id: 'cross-chain', node_id: 'material',
          reason_short: '另一产业的关联理由', evidence_status: 'pending',
        },
      ],
    }
    const related = stockChainAssociations(graph, '300308.SZ', 'datacom')
    expect(related).toHaveLength(1)
    expect(related[0].path).toBe('MLCC › 上游材料')
    expect(related[0].link.reason_short).toBe('另一产业的关联理由')
    expect(related[0].link.evidence_status).toBe('pending')
    expect(graph.stock_links[0].reason_short).toBe('研发制造高速光收发模块')
    expect(stockChainAssociations(graph, '999999.SZ', 'datacom')).toEqual([])
  })

  it('单链分类直接并入根节点，避免分类与产业链重复', () => {
    const expanded = defaultExpandedKeys(SINGLE_CHAIN_GRAPH)
    const layout = buildLayout(SINGLE_CHAIN_GRAPH, expanded, searchGraph(SINGLE_CHAIN_GRAPH, ''))

    expect(expanded.has(categoryKey('ai'))).toBe(false)
    expect(layout.byKey.has(categoryKey('ai'))).toBe(false)
    expect(layout.byKey.get(chainKey('ai-industry'))?.parentKey).toBe('root')
    expect(layout.byKey.get('root')?.childCount).toBe(1)

    const search = searchGraph(SINGLE_CHAIN_GRAPH, '人工智能')
    expect(search.firstMatch).toBe(chainKey('ai-industry'))
    expect(search.visible.has(chainKey('ai-industry'))).toBe(true)
  })

  it('默认展开产业路径但不将股票渲染到脑图', () => {
    const expanded = defaultExpandedKeys(GRAPH)
    expect(expanded.has(chainKey('optical'))).toBe(true)
    expect(expanded.has(nodeKey('module'))).toBe(true)
    expect(expanded.has(nodeKey('datacom'))).toBe(true)

    const layout = buildLayout(GRAPH, expanded, searchGraph(GRAPH, ''))
    expect(layout.byKey.has(stockKey('l1'))).toBe(false)
    expect(layout.byKey.get(nodeKey('datacom'))?.stockCount).toBe(1)
    expect(layout.byKey.get(nodeKey('datacom'))?.hasChildren).toBe(false)
    expect(layout.byKey.has(nodeKey('material'))).toBe(false)
    expect(layout.nodes.every(node => !node.key.startsWith('stock:'))).toBe(true)
    expect(stockLinksForScope(GRAPH, 'optical', 'module').map(link => link.id)).toEqual(['l1', 'l2'])
  })

  it('节点说明优先作为单行副标题，卡片不展示股票或方向数量', () => {
    const described: IndustryChainGraph = {
      ...GRAPH,
      nodes: GRAPH.nodes.map(node => node.id === 'datacom'
        ? { ...node, description: '数据中心和 AI 集群使用的 400G/800G 光模块。' }
        : node),
    }
    const layout = buildLayout(described, defaultExpandedKeys(described), searchGraph(described, ''))
    const node = layout.byKey.get(nodeKey('datacom'))

    expect(node?.subtitle).toBe('数据中心和 AI 集群使用的 400G/800G 光模块。')
    expect(node?.stockCount).toBe(1)
    expect(layout.byKey.get(chainKey('optical'))?.subtitle).toBe('')
    expect(layout.byKey.get('root')?.subtitle).toBe('')
  })

  it('搜索股票代码自动展开祖先并保留其它链作为暗化上下文', () => {
    const search = searchGraph(GRAPH, '300308')
    expect(search.count).toBe(2)
    expect(search.firstMatch).toBe(nodeKey('datacom'))
    expect(search.matched.has(stockKey('l1'))).toBe(true)
    expect(search.matched.has(stockKey('l2'))).toBe(true)
    expect(search.visible.has(nodeKey('datacom'))).toBe(true)

    const layout = buildLayout(GRAPH, defaultExpandedKeys(GRAPH), search)
    expect(layout.byKey.get(nodeKey('datacom'))?.matched).toBe(true)
    expect(layout.byKey.get(nodeKey('module'))?.matched).toBe(true)
    expect(layout.byKey.get(chainKey('mlcc'))?.dimmed).toBe(true)
    expect(layout.byKey.has(stockKey('l1'))).toBe(false)
  })

  it('命中关联理由时聚焦所属环节，直属与子环节的理由不串', () => {
    const search = searchGraph(GRAPH, '布局光模块')
    expect(search.firstMatch).toBe(nodeKey('module'))

    const layout = buildLayout(GRAPH, defaultExpandedKeys(GRAPH), search)
    expect(layout.byKey.get(nodeKey('module'))?.matched).toBe(true)
    expect(stockLinksForScope(GRAPH, 'optical', 'datacom')[0].reason_short).toBe('研发制造高速光收发模块')
    expect(stockLinksForScope(GRAPH, 'mlcc', 'module')).toEqual([])
  })

  it('搜索无结果时保留结构但全部暗化', () => {
    const search = searchGraph(GRAPH, '不存在的股票')
    expect(search.count).toBe(0)
    expect(search.firstMatch).toBeNull()

    const layout = buildLayout(GRAPH, defaultExpandedKeys(GRAPH), search)
    expect(layout.nodes.every(node => node.key === 'root' || node.dimmed)).toBe(true)
  })

  it('退市、北交所和 ST 股票不进入列表、搜索或节点计数', () => {
    const hiddenGraph: IndustryChainGraph = {
      ...GRAPH,
      hidden_stock_symbols: ['300308.SZ'],
    }

    expect(stockLinksForScope(hiddenGraph, 'optical', 'module')).toEqual([])
    expect(stockChainAssociations(hiddenGraph, '300308.SZ', 'datacom')).toEqual([])
    expect(searchGraph(hiddenGraph, '300308').count).toBe(0)

    const layout = buildLayout(
      hiddenGraph,
      new Set([
        categoryKey('electronics'),
        chainKey('optical'),
        nodeKey('module'),
        nodeKey('datacom'),
      ]),
      searchGraph(hiddenGraph, ''),
    )
    expect(layout.byKey.get(nodeKey('datacom'))?.stockCount).toBe(0)

    const stGraph: IndustryChainGraph = {
      ...GRAPH,
      stock_names: { ...GRAPH.stock_names, '300308.SZ': '*ST旭创' },
    }
    expect(stockLinksForScope(stGraph, 'optical', 'module')).toEqual([])
  })
})
