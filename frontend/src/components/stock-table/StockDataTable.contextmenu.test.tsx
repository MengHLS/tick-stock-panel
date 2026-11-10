// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, expect, it, vi } from 'vitest'
import type { ColumnConfig } from '@/lib/list-columns'
import { StockDataTable } from './StockDataTable'

(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true

const columns: ColumnConfig[] = [{
  id: 'builtin:symbol',
  source: { type: 'builtin', key: 'symbol' },
  label: '代码',
  visible: true,
}]

let container: HTMLDivElement
let root: Root

afterEach(() => {
  act(() => root?.unmount())
  container?.remove()
})

it('forwards row contextmenu events to the caller', () => {
  const onRowContextMenu = vi.fn()
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  act(() => {
    root.render(
      <StockDataTable
        columns={columns}
        rows={[{ symbol: '000001.SZ' }]}
        renderCell={(row: any) => <td>{row.symbol}</td>}
        onRowContextMenu={onRowContextMenu}
      />,
    )
  })

  const row = container.querySelector('tbody tr')
  if (!row) throw new Error('row not found')
  act(() => {
    row.dispatchEvent(new MouseEvent('contextmenu', {
      bubbles: true,
      clientX: 120,
      clientY: 80,
    }))
  })

  expect(onRowContextMenu).toHaveBeenCalledTimes(1)
  expect(onRowContextMenu.mock.calls[0][0].symbol).toBe('000001.SZ')
  expect(onRowContextMenu.mock.calls[0][1].clientX).toBe(120)
})
