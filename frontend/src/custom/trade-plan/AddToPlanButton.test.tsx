// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api } from '@/lib/api'
import { AddToPlanButton } from './AddToPlanButton'

(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true

let container: HTMLDivElement
let root: Root

function renderButton(symbols: string[]) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  act(() => {
    root.render(
      <QueryClientProvider client={queryClient}>
        <AddToPlanButton
          symbols={symbols}
          viewMode="table"
          selectedGroup=""
          refresh={() => {}}
        />
      </QueryClientProvider>,
    )
  })
}

function click(text: string) {
  const button = [...container.querySelectorAll('button')]
    .find(item => item.textContent?.includes(text))
  if (!button) throw new Error(`button not found: ${text}`)
  act(() => button.dispatchEvent(new MouseEvent('click', { bubbles: true })))
}

async function waitFor(check: () => boolean) {
  await act(async () => {
    for (let i = 0; i < 50; i += 1) {
      if (check()) return
      await new Promise(resolve => setTimeout(resolve, 10))
    }
  })
}

beforeEach(() => {
  vi.clearAllMocks()
})

afterEach(() => {
  act(() => root?.unmount())
  container?.remove()
})

it('opens the plan dialog with the only selected symbol prefilled', async () => {
  vi.spyOn(api, 'instrumentNames').mockResolvedValue({
    names: { '000001.SZ': '平安银行' },
  })
  renderButton(['000001.SZ'])
  click('加入计划')

  const code = () => container.querySelector<HTMLInputElement>('input[placeholder="600000.SH"]')
  const name = () => container.querySelector<HTMLInputElement>('input[placeholder="可选"]')
  await waitFor(() => code()?.value === '000001.SZ' && name()?.value === '平安银行')

  expect(container.textContent).toContain('新建交易计划')
  expect(code()?.value).toBe('000001.SZ')
  expect(name()?.value).toBe('平安银行')
})

it('lets the user pick one symbol when the watchlist view has many', async () => {
  vi.spyOn(api, 'instrumentNames').mockResolvedValue({
    names: { '000001.SZ': '平安银行', '000002.SZ': '万科A' },
  })
  renderButton(['000001.SZ', '000002.SZ'])
  click('加入计划')

  const symbolSelect = [...container.querySelectorAll('select')]
    .find(select => [...select.options].some(option => option.textContent === '选择标的'))
  if (!symbolSelect) throw new Error('symbol select not found')
  await waitFor(() => [...symbolSelect.options].some(option => option.textContent?.includes('万科A')))

  act(() => {
    const setValue = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value')?.set
    setValue?.call(symbolSelect, '000002.SZ')
    symbolSelect.dispatchEvent(new Event('change', { bubbles: true }))
  })

  await waitFor(() => (
    container.querySelector<HTMLInputElement>('input[placeholder="600000.SH"]')?.value === '000002.SZ'
  ))
  expect(container.querySelector<HTMLInputElement>('input[placeholder="可选"]')?.value).toBe('万科A')
})
