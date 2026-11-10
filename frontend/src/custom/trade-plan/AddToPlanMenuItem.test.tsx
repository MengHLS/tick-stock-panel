// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, expect, it, vi } from 'vitest'
import { AddToPlanMenuItem } from './AddToPlanMenuItem'

(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true

let container: HTMLDivElement
let root: Root

afterEach(() => {
  act(() => root?.unmount())
  container?.remove()
})

it('opens the plan form from the row menu and closes both layers', () => {
  const close = vi.fn()
  const setPinned = vi.fn()
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  act(() => {
    root.render(
      <QueryClientProvider client={queryClient}>
        <AddToPlanMenuItem
          apiVersion={1}
          symbol="000001.SZ"
          name="平安银行"
          close={close}
          setPinned={setPinned}
        />
      </QueryClientProvider>,
    )
  })

  const item = [...container.querySelectorAll('button')]
    .find(button => button.textContent?.includes('加入交易计划'))
  if (!item) throw new Error('menu item not found')
  act(() => item.dispatchEvent(new MouseEvent('click', { bubbles: true })))

  expect(setPinned).toHaveBeenCalledWith(true)
  expect(container.textContent).toContain('新建交易计划')
  expect(container.querySelector<HTMLInputElement>('input[placeholder="600000.SH"]')?.value).toBe('000001.SZ')
  expect(container.querySelector<HTMLInputElement>('input[placeholder="可选"]')?.value).toBe('平安银行')

  const cancel = [...container.querySelectorAll('button')]
    .find(button => button.textContent?.trim() === '取消')
  if (!cancel) throw new Error('cancel button not found')
  act(() => cancel.dispatchEvent(new MouseEvent('click', { bubbles: true })))

  expect(setPinned).toHaveBeenLastCalledWith(false)
  expect(close).toHaveBeenCalled()
})
