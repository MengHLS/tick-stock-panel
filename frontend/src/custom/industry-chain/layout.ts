import type {
  IndustryChainGraph,
  IndustryChainNode,
  IndustryChainStockLink,
} from '@/lib/api'

export type GraphItemType = 'root' | 'category' | 'chain' | 'node'

export const LINK_BASIS_LABELS: Record<IndustryChainStockLink['basis'], string> = {
  main_business: '主营/产品',
  supply: '供应配套',
  theme_clue: '题材线索',
}

export function isExcludedStock(symbol: string, name?: string | null): boolean {
  if (symbol.toUpperCase().endsWith('.BJ')) return true
  const text = (name ?? '').toUpperCase()
  return text.includes('ST') || text.includes('退')
}

export function visibleStockLinks(graph: IndustryChainGraph): IndustryChainStockLink[] {
  const hidden = new Set(graph.hidden_stock_symbols ?? [])
  return graph.stock_links.filter(link =>
    !hidden.has(link.symbol)
    && !isExcludedStock(link.symbol, graph.stock_names?.[link.symbol]),
  )
}

export interface LayoutNode {
  key: string
  type: GraphItemType
  id: string
  chainId: string | null
  name: string
  description: string
  subtitle: string
  kind: IndustryChainNode['kind'] | null
  x: number
  y: number
  width: number
  height: number
  depth: number
  parentKey: string | null
  expanded: boolean
  hasChildren: boolean
  childCount: number
  stockCount: number
  matched: boolean
  dimmed: boolean
}

export interface LayoutEdge {
  key: string
  fromKey: string
  toKey: string
  x1: number
  y1: number
  x2: number
  y2: number
  lit: boolean
  dimmed: boolean
}

export interface GraphLayout {
  nodes: LayoutNode[]
  edges: LayoutEdge[]
  width: number
  height: number
  byKey: Map<string, LayoutNode>
}

export interface GraphSearchState {
  active: boolean
  query: string
  matched: Set<string>
  visible: Set<string>
  reveal: Set<string>
  count: number
  firstMatch: string | null
}

interface TreeItem {
  key: string
  type: GraphItemType
  id: string
  chainId: string | null
  name: string
  description: string
  subtitle: string
  kind: IndustryChainNode['kind'] | null
  parentKey: string | null
  order: number
  matched: boolean
  dimmed: boolean
  expanded: boolean
  hasChildren: boolean
  childCount: number
  stockCount: number
  children: TreeItem[]
}

const DIMENSIONS: Record<GraphItemType, { width: number; height: number }> = {
  root: { width: 176, height: 56 },
  category: { width: 158, height: 42 },
  chain: { width: 204, height: 48 },
  node: { width: 194, height: 54 },
}

const H_GAP = 70
const V_GAP = 18
const PADDING = 48

export const EMPTY_SEARCH: GraphSearchState = {
  active: false,
  query: '',
  matched: new Set<string>(),
  visible: new Set<string>(),
  reveal: new Set<string>(),
  count: 0,
  firstMatch: null,
}

export function categoryKey(id: string): string {
  return `category:${id}`
}

export function chainKey(id: string): string {
  return `chain:${id}`
}

export function nodeKey(id: string): string {
  return `node:${id}`
}

export function stockKey(id: string): string {
  return `stock:${id}`
}

export function stockChainAssociations(
  graph: IndustryChainGraph,
  symbol: string,
  currentNodeId: string,
): { link: IndustryChainStockLink; path: string }[] {
  const nodes = new Map(graph.nodes.map(node => [node.id, node]))
  const chains = new Map(graph.chains.map(chain => [chain.id, chain]))
  const currentChainId = nodes.get(currentNodeId)?.chain_id
  return visibleStockLinks(graph).flatMap(link => {
    const node = nodes.get(link.node_id)
    if (link.symbol !== symbol || !node || node.chain_id === currentChainId) return []
    const chain = chains.get(node.chain_id)
    if (!chain) return []
    const path = []
    const visited = new Set<string>()
    let current: IndustryChainNode | undefined = node
    while (current && !visited.has(current.id)) {
      visited.add(current.id)
      path.unshift(current.name)
      current = current.parent_id ? nodes.get(current.parent_id) : undefined
    }
    return [{ link, path: [chain.name, ...path].join(' › ') }]
  })
}

export function stockLinksForScope(
  graph: IndustryChainGraph,
  chainId: string,
  nodeId: string | null,
): IndustryChainStockLink[] {
  const nodes = graph.nodes.filter(node => node.chain_id === chainId)
  if (nodeId && !nodes.some(node => node.id === nodeId)) return []
  const scope = new Set<string>()
  const pending = nodeId ? [nodeId] : nodes.map(node => node.id)
  while (pending.length) {
    const current = pending.pop()!
    if (scope.has(current)) continue
    scope.add(current)
    for (const node of nodes) {
      if (node.parent_id === current) pending.push(node.id)
    }
  }
  return visibleStockLinks(graph).filter(link => scope.has(link.node_id))
}

export function defaultExpandedKeys(graph: IndustryChainGraph): Set<string> {
  const counts = chainCountsByCategory(graph)
  const expanded = new Set<string>(
    graph.categories
      .filter(item => (counts.get(item.id) ?? 0) > 1)
      .map(item => categoryKey(item.id)),
  )
  const chains = [...graph.chains].sort(byOrder)
  const preferred = chains.find(item => item.name.includes('AI')) ?? chains[0]
  if (!preferred) return expanded
  if ((counts.get(preferred.category_id) ?? 0) > 1) {
    expanded.add(categoryKey(preferred.category_id))
  }
  expanded.add(chainKey(preferred.id))

  const chainNodes = graph.nodes.filter(item => item.chain_id === preferred.id)
  const nodeIds = new Set(chainNodes.map(item => item.id))
  const firstLink = [...visibleStockLinks(graph)]
    .filter(item => nodeIds.has(item.node_id))
    .sort((a, b) => a.sort_order - b.sort_order || a.id.localeCompare(b.id))[0]
  if (!firstLink) return expanded

  const byId = new Map(chainNodes.map(item => [item.id, item]))
  let current: IndustryChainNode | undefined = byId.get(firstLink.node_id)
  while (current) {
    expanded.add(nodeKey(current.id))
    current = current.parent_id ? byId.get(current.parent_id) : undefined
  }
  return expanded
}

export function searchGraph(graph: IndustryChainGraph, query: string): GraphSearchState {
  const raw = query.trim()
  if (!raw) return EMPTY_SEARCH
  const q = raw.toLowerCase()
  const compact = q.replace(/\s+/g, '')

  const chainsByCategory = new Map<string, typeof graph.chains>()
  for (const chain of graph.chains) {
    const list = chainsByCategory.get(chain.category_id) ?? []
    list.push(chain)
    chainsByCategory.set(chain.category_id, list)
  }
  const counts = new Map(
    [...chainsByCategory.entries()].map(([categoryId, chains]) => [categoryId, chains.length]),
  )
  const nodesByChain = new Map<string, IndustryChainNode[]>()
  for (const node of graph.nodes) {
    const list = nodesByChain.get(node.chain_id) ?? []
    list.push(node)
    nodesByChain.set(node.chain_id, list)
  }
  const nodeById = new Map(graph.nodes.map(node => [node.id, node]))
  const chainById = new Map(graph.chains.map(chain => [chain.id, chain]))
  const stockLinks = visibleStockLinks(graph)
  const linksByNode = new Map<string, IndustryChainStockLink[]>()
  for (const link of stockLinks) {
    const list = linksByNode.get(link.node_id) ?? []
    list.push(link)
    linksByNode.set(link.node_id, list)
  }

  const matched = new Set<string>()
  const visible = new Set<string>()
  const reveal = new Set<string>()

  const parentOf = (key: string): string | null => {
    if (key === 'root') return null
    if (key.startsWith('category:')) return 'root'
    if (key.startsWith('chain:')) {
      const chain = chainById.get(key.slice('chain:'.length))
      if (!chain) return 'root'
      return (counts.get(chain.category_id) ?? 0) > 1
        ? categoryKey(chain.category_id)
        : 'root'
    }
    if (key.startsWith('node:')) {
      const node = nodeById.get(key.slice('node:'.length))
      if (!node) return null
      return node.parent_id ? nodeKey(node.parent_id) : chainKey(node.chain_id)
    }
    if (key.startsWith('stock:')) {
      const link = stockLinks.find(item => item.id === key.slice('stock:'.length))
      return link ? nodeKey(link.node_id) : null
    }
    return null
  }

  const revealPath = (key: string) => {
    let current: string | null = key
    while (current) {
      visible.add(current)
      reveal.add(current)
      current = parentOf(current)
    }
  }

  const markChainSubtree = (chainId: string) => {
    visible.add(chainKey(chainId))
    for (const node of nodesByChain.get(chainId) ?? []) {
      visible.add(nodeKey(node.id))
      for (const link of linksByNode.get(node.id) ?? []) visible.add(stockKey(link.id))
    }
  }

  const markNodeSubtree = (nodeId: string) => {
    const stack = [nodeId]
    while (stack.length) {
      const current = stack.pop()!
      visible.add(nodeKey(current))
      for (const link of linksByNode.get(current) ?? []) visible.add(stockKey(link.id))
      for (const node of graph.nodes) {
        if (node.parent_id === current) stack.push(node.id)
      }
    }
  }

  const matches = (value: string | null | undefined) => {
    if (!value) return false
    const text = value.toLowerCase()
    return text.includes(q) || text.replace(/\s+/g, '').includes(compact)
  }

  let firstMatch: string | null = null
  const remember = (key: string, focusKey = key) => {
    matched.add(key)
    if (!firstMatch) firstMatch = focusKey
  }

  for (const category of [...graph.categories].sort(byOrder)) {
    if (!matches(category.name)) continue
    const categoryChains = chainsByCategory.get(category.id) ?? []
    if (categoryChains.length > 1) {
      const key = categoryKey(category.id)
      remember(key)
      visible.add(key)
      for (const chain of categoryChains) markChainSubtree(chain.id)
      revealPath(key)
      continue
    }
    for (const chain of categoryChains) {
      const key = chainKey(chain.id)
      remember(key)
      markChainSubtree(chain.id)
      revealPath(key)
    }
  }

  for (const chain of [...graph.chains].sort(byOrder)) {
    if (!matches(chain.name)) continue
    const key = chainKey(chain.id)
    remember(key)
    markChainSubtree(chain.id)
    revealPath(key)
  }

  for (const node of graph.nodes) {
    if (!matches(node.name) && !matches(node.description)) continue
    const key = nodeKey(node.id)
    remember(key)
    markNodeSubtree(node.id)
    revealPath(key)
  }

  for (const link of stockLinks) {
    const name = graph.stock_names?.[link.symbol] ?? ''
    if (
      !matches(link.symbol)
      && !matches(name)
      && !matches(link.reason_short)
      && !matches(link.note)
    ) continue
    const key = stockKey(link.id)
    remember(key, nodeKey(link.node_id))
    visible.add(key)
    revealPath(key)
  }

  return {
    active: true,
    query: raw,
    matched,
    visible,
    reveal,
    count: matched.size,
    firstMatch,
  }
}

export function buildLayout(
  graph: IndustryChainGraph,
  expanded: ReadonlySet<string>,
  search: GraphSearchState,
): GraphLayout {
  const isExpanded = (key: string) =>
    key === 'root' || expanded.has(key) || (search.active && search.reveal.has(key))
  const isDimmed = (key: string) => search.active && !search.visible.has(key)

  const stockLinks = visibleStockLinks(graph)
  const linksByNode = new Map<string, IndustryChainStockLink[]>()
  for (const link of stockLinks) {
    const list = linksByNode.get(link.node_id) ?? []
    list.push(link)
    linksByNode.set(link.node_id, list)
  }

  const stockCountCache = new Map<string, number>()
  const symbolsUnderNode = (nodeId: string): Set<string> => {
    const symbols = new Set<string>()
    const stack = [nodeId]
    while (stack.length) {
      const current = stack.pop()!
      for (const link of linksByNode.get(current) ?? []) symbols.add(link.symbol)
      for (const node of graph.nodes) {
        if (node.parent_id === current) stack.push(node.id)
      }
    }
    return symbols
  }
  const countUnderNode = (nodeId: string): number => {
    const cached = stockCountCache.get(nodeId)
    if (cached != null) return cached
    const count = symbolsUnderNode(nodeId).size
    stockCountCache.set(nodeId, count)
    return count
  }

  const buildNode = (node: IndustryChainNode, parentKey: string): TreeItem => {
    const key = nodeKey(node.id)
    const childNodes = graph.nodes
      .filter(item => item.parent_id === node.id)
      .sort(byOrder)
    const links = [...(linksByNode.get(node.id) ?? [])]
      .sort((a, b) => a.sort_order - b.sort_order || a.id.localeCompare(b.id))
    const directCount = childNodes.length
    const expandedNow = isExpanded(key) && directCount > 0
    const children: TreeItem[] = []
    if (expandedNow) {
      for (const child of childNodes) children.push(buildNode(child, key))
    }
    const stockCount = countUnderNode(node.id)
    return {
      key,
      type: 'node',
      id: node.id,
      chainId: node.chain_id,
      name: node.name,
      description: node.description,
      subtitle: node.description,
      kind: node.kind,
      parentKey,
      order: node.order,
      matched: search.matched.has(key) || links.some(link => search.matched.has(stockKey(link.id))),
      dimmed: isDimmed(key),
      expanded: expandedNow,
      hasChildren: directCount > 0,
      childCount: directCount,
      stockCount,
      children,
    }
  }

  const buildChain = (chainId: string, parentKey: string): TreeItem | null => {
    const chain = graph.chains.find(item => item.id === chainId)
    if (!chain) return null
    const key = chainKey(chain.id)
    const roots = graph.nodes
      .filter(item => item.chain_id === chain.id && !item.parent_id)
      .sort(byOrder)
    const expandedNow = isExpanded(key) && roots.length > 0
    const children = expandedNow ? roots.map(node => buildNode(node, key)) : []
    const symbols = new Set<string>()
    for (const node of graph.nodes.filter(item => item.chain_id === chain.id)) {
      for (const link of linksByNode.get(node.id) ?? []) symbols.add(link.symbol)
    }
    return {
      key,
      type: 'chain',
      id: chain.id,
      chainId: chain.id,
      name: chain.name,
      description: '',
      subtitle: '',
      kind: null,
      parentKey,
      order: chain.order,
      matched: search.matched.has(key),
      dimmed: isDimmed(key),
      expanded: expandedNow,
      hasChildren: roots.length > 0,
      childCount: roots.length,
      stockCount: symbols.size,
      children,
    }
  }

  const counts = chainCountsByCategory(graph)
  const categories = [...graph.categories]
    .filter(category => (counts.get(category.id) ?? 0) > 1)
    .sort(byOrder)
    .map(category => {
      const key = categoryKey(category.id)
      const chains = graph.chains
        .filter(item => item.category_id === category.id)
        .sort(byOrder)
      const expandedNow = isExpanded(key) && chains.length > 0
      return {
        key,
        type: 'category' as const,
        id: category.id,
        chainId: null,
        name: category.name,
        description: '',
        subtitle: '',
        kind: null,
        parentKey: 'root',
        order: category.order,
        matched: search.matched.has(key),
        dimmed: isDimmed(key),
        expanded: expandedNow,
        hasChildren: chains.length > 0,
        childCount: chains.length,
        stockCount: 0,
        children: expandedNow
          ? chains.map(chain => buildChain(chain.id, key)).filter((item): item is TreeItem => !!item)
          : [],
      } satisfies TreeItem
    })
  const directChains = graph.chains
    .filter(chain => (counts.get(chain.category_id) ?? 0) <= 1)
    .sort(byOrder)
    .map(chain => buildChain(chain.id, 'root'))
    .filter((item): item is TreeItem => !!item)
  const rootChildren = [...categories, ...directChains].sort(byOrder)

  const totalSymbols = new Set(stockLinks.map(link => link.symbol)).size
  const root: TreeItem = {
    key: 'root',
    type: 'root',
    id: 'root',
    chainId: null,
    name: '产业链研究',
    description: '',
    subtitle: '',
    kind: null,
    parentKey: null,
    order: 0,
    matched: search.matched.has('root'),
    dimmed: false,
    expanded: true,
    hasChildren: rootChildren.length > 0,
    childCount: rootChildren.length,
    stockCount: totalSymbols,
    children: rootChildren,
  }

  const depthWidths = new Map<number, number>()
  const scan = (item: TreeItem, depth: number) => {
    const size = DIMENSIONS[item.type]
    depthWidths.set(depth, Math.max(depthWidths.get(depth) ?? 0, size.width))
    for (const child of item.children) scan(child, depth + 1)
  }
  scan(root, 0)

  const xByDepth = new Map<number, number>()
  const maxDepth = Math.max(...depthWidths.keys())
  let cursor = PADDING
  for (let depth = 0; depth <= maxDepth; depth += 1) {
    xByDepth.set(depth, cursor)
    cursor += (depthWidths.get(depth) ?? 0) + H_GAP
  }
  const width = cursor - H_GAP + PADDING

  const measure = (item: TreeItem): number => {
    const own = DIMENSIONS[item.type].height
    if (!item.expanded || item.children.length === 0) return own
    const childrenHeight = item.children.reduce((sum, child) => sum + measure(child), 0)
      + V_GAP * (item.children.length - 1)
    return Math.max(own, childrenHeight)
  }

  const nodes: LayoutNode[] = []
  const byKey = new Map<string, LayoutNode>()
  const place = (item: TreeItem, depth: number, top: number) => {
    const size = DIMENSIONS[item.type]
    const subtreeHeight = measure(item)
    const y = top + (subtreeHeight - size.height) / 2
    const layoutNode: LayoutNode = {
      key: item.key,
      type: item.type,
      id: item.id,
      chainId: item.chainId,
      name: item.name,
      description: item.description,
      subtitle: item.subtitle,
      kind: item.kind,
      x: xByDepth.get(depth) ?? PADDING,
      y,
      width: size.width,
      height: size.height,
      depth,
      parentKey: item.parentKey,
      expanded: item.expanded,
      hasChildren: item.hasChildren,
      childCount: item.childCount,
      stockCount: item.stockCount,
      matched: item.matched,
      dimmed: item.dimmed,
    }
    nodes.push(layoutNode)
    byKey.set(item.key, layoutNode)
    if (!item.expanded) return
    let childTop = top
    for (const child of item.children) {
      place(child, depth + 1, childTop)
      childTop += measure(child) + V_GAP
    }
  }
  place(root, 0, PADDING)

  const edges: LayoutEdge[] = []
  const connect = (item: TreeItem) => {
    if (!item.expanded) return
    const parent = byKey.get(item.key)
    if (parent) {
      for (const child of item.children) {
        const target = byKey.get(child.key)
        if (!target) continue
        edges.push({
          key: `${item.key}->${child.key}`,
          fromKey: item.key,
          toKey: child.key,
          x1: parent.x + parent.width,
          y1: parent.y + parent.height / 2,
          x2: target.x,
          y2: target.y + target.height / 2,
          lit: child.matched,
          dimmed: parent.dimmed || child.dimmed,
        })
      }
    }
    for (const child of item.children) connect(child)
  }
  connect(root)

  return {
    nodes,
    edges,
    width: Math.max(width, 720),
    height: Math.max(measure(root) + PADDING * 2, 420),
    byKey,
  }
}

function byOrder<T extends { order: number; name: string }>(a: T, b: T): number {
  return a.order - b.order || a.name.localeCompare(b.name, 'zh-CN')
}

function chainCountsByCategory(graph: IndustryChainGraph): Map<string, number> {
  const counts = new Map<string, number>()
  for (const chain of graph.chains) {
    counts.set(chain.category_id, (counts.get(chain.category_id) ?? 0) + 1)
  }
  return counts
}
