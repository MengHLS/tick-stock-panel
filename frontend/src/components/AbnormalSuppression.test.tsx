// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type {
  AbnormalSuppression as AbnormalSuppressionPayload,
  AbnormalWindowKey,
} from '@/lib/api'
import { AbnormalSuppressionRows } from './AbnormalSuppression'

vi.mock('./AbnormalMiniStructure', () => ({
  AbnormalMiniStructure: () => null,
}))

let host: HTMLDivElement
let root: Root

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
})

afterEach(async () => {
  await act(async () => root.unmount())
  host.remove()
})

function payload(windows: AbnormalSuppressionPayload['windows']): AbnormalSuppressionPayload {
  return {
    symbol: '002242.SZ',
    name: '九阳股份',
    close: 20,
    windows,
  }
}

function render(data: AbnormalSuppressionPayload, window?: AbnormalWindowKey) {
  return act(async () => {
    root.render(
      <AbnormalSuppressionRows data={data} symbol="002242.SZ" days={20} window={window} />,
    )
  })
}

it('展示今明后压制价与剩余空间', async () => {
  await render(payload({
    '10d': {
      threshold: 1,
      direction: 'up',
      current_deviation: 0.8,
      effective_days: 7,
      days: [
        { offset: 0, base_date: '2026-09-01', cap: 24, room_pct: 0.2 },
        { offset: 1, base_date: '2026-09-02', cap: 25, room_pct: 0.25 },
        { offset: 2, base_date: '2026-09-03', cap: 26, room_pct: 0.3 },
      ],
    },
    '30d': {
      threshold: 2,
      direction: 'up',
      current_deviation: 1,
      days: [
        { offset: 0, base_date: '2026-08-01', cap: 30, room_pct: 0.5 },
        { offset: 1, base_date: '2026-08-02', cap: 36, room_pct: 0.8 },
        { offset: 2, base_date: '2026-08-03', cap: 33, room_pct: 0.65 },
      ],
    },
  }))

  expect(host.textContent).toContain('后续压制')
  expect(host.textContent).toContain('10日(7日)')
  expect(host.textContent).toContain('24.00')
  expect(host.textContent).toContain('+20.0%')
  expect(host.textContent).toContain('30日')
  expect(host.textContent).toContain('36.00')
  expect(host.textContent).toContain('+80.0%')
})

it('已越过压制价时显示已超', async () => {
  await render(payload({
    '30d': {
      threshold: 2,
      direction: 'up',
      current_deviation: 2.05,
      days: [{ offset: 0, base_date: '2026-08-01', cap: 19, room_pct: -0.05 }],
    },
  }))

  expect(host.textContent).toContain('已超5.0%')
})

it('负向偏离展示下方压制与已破状态', async () => {
  await render(payload({
    '30d': {
      threshold: 0.7,
      direction: 'down',
      current_deviation: -0.5,
      days: [
        { offset: 0, base_date: '2026-08-01', cap: 6, room_pct: -0.4 },
        { offset: 1, base_date: '2026-08-02', cap: 12, room_pct: 0.02 },
      ],
    },
  }))

  expect(host.textContent).toContain('-40.0%')
  expect(host.textContent).toContain('已破2.0%')
})

it('没有可测算窗口时显示数据不足', async () => {
  await render(payload({}))
  expect(host.textContent).toContain('压制价数据不足')
})

it('指定窗口时只展示该窗口', async () => {
  await render(payload({
    '10d': {
      threshold: 1,
      direction: 'up',
      current_deviation: 0.8,
      days: [{ offset: 0, base_date: '2026-09-01', cap: 24, room_pct: 0.2 }],
    },
    '30d': {
      threshold: 2,
      direction: 'up',
      current_deviation: 1,
      days: [{ offset: 0, base_date: '2026-08-01', cap: 30, room_pct: 0.5 }],
    },
  }), '10d')

  expect(host.textContent).toContain('10日')
  expect(host.textContent).toContain('24.00')
  expect(host.textContent).not.toContain('30日')
  expect(host.textContent).not.toContain('30.00')
})
