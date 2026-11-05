// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { expect, it, vi } from 'vitest'
import { QK } from '@/lib/queryKeys'
import { IndustrySourcePicker } from './IndustrySourcePicker'

it('selects a chain, narrows to a node, and detaches without editing stock membership', () => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  queryClient.setQueryData(QK.industryChainGraph, {
    chains: [{ id: 'cpo', name: 'CPO' }],
    nodes: [{ id: 'optical', chain_id: 'cpo', name: '光模块' }],
  })
  const change = vi.fn()
  const render = (value: { chain_id: string; node_ids: string[] } | null) => {
    act(() => root.render(
      <QueryClientProvider client={queryClient}>
        <IndustrySourcePicker open={false} value={value} onChange={change} />
      </QueryClientProvider>,
    ))
  }
  try {
    render(null)
    const source = host.querySelector('select')!
    act(() => {
      source.value = 'cpo'
      source.dispatchEvent(new Event('change', { bubbles: true }))
    })
    expect(change).toHaveBeenLastCalledWith({ chain_id: 'cpo', node_ids: [] })
    render({ chain_id: 'cpo', node_ids: [] })
    act(() => host.querySelector<HTMLInputElement>('input[type=checkbox]')!.click())
    expect(change).toHaveBeenLastCalledWith({ chain_id: 'cpo', node_ids: ['optical'] })
    act(() => {
      source.value = ''
      source.dispatchEvent(new Event('change', { bubbles: true }))
    })
    expect(change).toHaveBeenLastCalledWith(null)
  } finally {
    act(() => root.unmount())
    queryClient.clear()
    host.remove()
  }
})
