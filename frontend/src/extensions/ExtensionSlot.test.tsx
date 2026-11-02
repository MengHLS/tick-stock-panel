// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterAll, beforeAll, expect, it, vi } from 'vitest'
import { ExtensionSlot } from './ExtensionSlot'
import {
  finalizeFrontendExtensions,
  loadFrontendExtensions,
} from './registry'
import type {
  StrategyBacktestResult,
  StrategyBacktestTrade,
} from '@/lib/api'
import type {
  FrontendSlotContextMap,
  FrontendSlotRegistration,
} from './types'

const result = {
  run_id: 'run-1',
  total_return: 0.1234,
} as unknown as StrategyBacktestResult
const trade = {
  symbol: '000001.SZ',
  entry_date: '2026-01-05',
  exit_date: '2026-01-06',
} as unknown as StrategyBacktestTrade

let container: HTMLDivElement
let root: Root

function render(node: React.ReactNode) {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  act(() => root.render(node))
}

beforeAll(async () => {
  ;(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true
  await loadFrontendExtensions({
    'slot-order': async () => ({
      default: {
        id: 'test.slot-order',
        apiVersion: 1,
        slots: [
          {
            name: 'backtest.result.extra',
            id: 'second',
            order: 20,
            component: ({
              result,
            }: FrontendSlotContextMap['backtest.result.extra']) => (
              <span>second:{result.run_id}</span>
            ),
          },
          {
            name: 'backtest.result.extra',
            id: 'first',
            order: 10,
            component: () => <span>first</span>,
          },
        ] as FrontendSlotRegistration[],
      },
    }),
    'slot-broken': async () => ({
      default: {
        id: 'test.slot-broken',
        apiVersion: 1,
        slots: [{
          name: 'backtest.result.extra',
          id: 'broken',
          order: 15,
          component: () => {
            throw new Error('boom')
          },
        }] as FrontendSlotRegistration[],
      },
    }),
    'slot-trades': async () => ({
      default: {
        id: 'test.slot-trades',
        apiVersion: 1,
        slots: [{
          name: 'backtest.trades.extra',
          id: 'trades',
          component: ({
            trades,
            onSelectTrade,
          }: FrontendSlotContextMap['backtest.trades.extra']) => (
            <button type="button" onClick={() => onSelectTrade(trades[0])}>
              trade:{trades[0]?.symbol}
            </button>
          ),
        }] as FrontendSlotRegistration[],
      },
    }),
    'slot-saved': async () => ({
      default: {
        id: 'test.slot-saved',
        apiVersion: 1,
        slots: [{
          name: 'backtest.savedResults.extra',
          id: 'saved',
          component: ({
            currentSavedId,
            openSaved,
            busy,
          }: FrontendSlotContextMap['backtest.savedResults.extra']) => (
            <button
              type="button"
              disabled={busy}
              onClick={() => openSaved('saved-2')}
            >
              saved:{currentSavedId}
            </button>
          ),
        }] as FrontendSlotRegistration[],
      },
    }),
    'slot-settings': async () => ({
      default: {
        id: 'test.slot-settings',
        apiVersion: 1,
        slots: [{
          name: 'backtest.settings.extra',
          id: 'settings',
          component: ({
            strategyId,
            strategyName,
            defaults,
          }: FrontendSlotContextMap['backtest.settings.extra']) => (
            <span>
              settings:{strategyId}:{strategyName}:{String(defaults.max_positions)}
            </span>
          ),
        }] as FrontendSlotRegistration[],
      },
    }),
  })
  finalizeFrontendExtensions(new Set())
})

afterAll(() => {
  act(() => root?.unmount())
  container?.remove()
})

it('renders all backtest slots with bounded context and isolates failures', () => {
  const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
  const onSelectTrade = vi.fn()
  const openSaved = vi.fn()

  render(
    <>
      <ExtensionSlot name="backtest.result.extra" context={{ apiVersion: 1, result }} />
      <ExtensionSlot
        name="backtest.trades.extra"
        context={{
          apiVersion: 1,
          result,
          trades: [trade],
          selectedTrade: trade,
          onSelectTrade,
        }}
      />
      <ExtensionSlot
        name="backtest.savedResults.extra"
        context={{
          apiVersion: 1,
          currentSavedId: 'saved-1',
          openSaved,
          busy: false,
        }}
      />
      <ExtensionSlot
        name="backtest.settings.extra"
        context={{
          apiVersion: 1,
          strategyId: 'strategy-1',
          strategyName: '测试策略',
          defaults: { max_positions: 8 },
        }}
      />
    </>,
  )

  const text = container.textContent ?? ''
  expect(text).toContain('first')
  expect(text).toContain('second:run-1')
  expect(text).toContain('扩展 test.slot-broken 暂时不可用')
  expect(text).toContain('trade:000001.SZ')
  expect(text).toContain('saved:saved-1')
  expect(text).toContain('settings:strategy-1:测试策略:8')
  expect(text.indexOf('first')).toBeLessThan(text.indexOf('test.slot-broken'))
  expect(text.indexOf('test.slot-broken')).toBeLessThan(text.indexOf('second:'))

  const buttons = Array.from(container.querySelectorAll('button'))
  act(() => buttons[0].click())
  act(() => buttons[1].click())
  expect(onSelectTrade).toHaveBeenCalledWith(trade)
  expect(openSaved).toHaveBeenCalledWith('saved-2')
  consoleError.mockRestore()
})
