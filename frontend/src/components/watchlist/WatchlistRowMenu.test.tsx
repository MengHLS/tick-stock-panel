// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, expect, it, vi } from 'vitest'
import * as extensionRegistry from '@/extensions/registry'
import { WatchlistRowMenu } from './WatchlistRowMenu'

(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true

let root: Root

afterEach(() => {
  act(() => root?.unmount())
})

function click(text: string) {
  const button = [...document.querySelectorAll('button')]
    .find(item => item.textContent?.includes(text))
  if (!button) throw new Error(`button not found: ${text}`)
  act(() => button.dispatchEvent(new MouseEvent('click', { bubbles: true })))
}

it('moves the stock to top and toggles group membership', () => {
  vi.spyOn(extensionRegistry, 'getFrontendSlotRegistrations').mockReturnValue([])
  const onMoveToTop = vi.fn()
  const onClose = vi.fn()
  const onToggleGroup = vi.fn()
  const host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)

  act(() => {
    root.render(
      <WatchlistRowMenu
        menu={{ x: 20, y: 20, symbol: '000001.SZ', name: '平安银行' }}
        onClose={onClose}
        groups={[
          { id: 'g1', name: '科技', color: 'blue' },
          { id: 'g2', name: '趋势', color: 'emerald' },
        ]}
        groupIds={['g2']}
        inWatchlist
        isTop={false}
        moveTopBusy={false}
        groupBusy={false}
        onMoveToTop={onMoveToTop}
        onToggleGroup={onToggleGroup}
      />,
    )
  })

  click('置顶股票')
  expect(onMoveToTop).toHaveBeenCalledTimes(1)
  expect(onClose).toHaveBeenCalledTimes(1)

  click('科技')
  expect(onToggleGroup).toHaveBeenLastCalledWith('g1', true)

  click('趋势')
  expect(onToggleGroup).toHaveBeenLastCalledWith('g2', false)
})
