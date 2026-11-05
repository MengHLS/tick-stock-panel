// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { ThemeAnalyzerLimitRoute } from '@/lib/api'
import { LimitRouteMap } from './LimitRouteMap'

let host: HTMLDivElement
let root: Root
const focusDay = vi.fn()
const selectStock = vi.fn()

function route(): ThemeAnalyzerLimitRoute {
  return {
    dates: ['2026-10-29', '2026-10-30'],
    rows: [{
      symbol: '002242.SZ',
      name: '九阳股份',
      active: true,
      first_date: '2026-10-29',
      first_seal_date: '2026-10-29',
      first_time: '09:30',
      last_date: '2026-10-29',
      total_lu: 1,
      max_consec: 6,
      max_ret_30: 1.7,
      max_ret_30_date: '2026-10-29',
      is_space_leader: true,
      start_rank: 1,
      events: [{
        date: '2026-10-29', type: 'seal', first_time: '09:30', last_time: '10:00',
        opens: 1, consec: 6, money: 1e8, reason: '题材', catch_up: false, relay: false,
      }],
    }],
    daily_leaders: [{
      date: '2026-10-29', symbol: '002242.SZ', name: '九阳股份',
      consec: 6, total_lu: 6, first_time: '09:30', switch: false,
    }],
    leader_phases: [{
      symbol: '002242.SZ', name: '九阳股份',
      start: '2026-10-29', end: '2026-10-29', days: 1,
    }],
    switch_days: [{
      date: '2026-10-29', label: '领涨切换', reason: '旧龙 → 新龙',
      symbols: ['000001.SZ', '000002.SZ'],
      minute_symbols: ['000001.SZ', '000002.SZ'],
      sealed: [], broken: [], new_starters: [],
      daily_leader: '000001.SZ', leader_name: '新龙',
      previous_leader: '000002.SZ', previous_leader_name: '旧龙',
      has_minute: true,
    }],
    space_leader_symbol: '002242.SZ',
    space_leader_name: '九阳股份',
    space_leader_peak_date: '2026-10-29',
    event_count: 1,
    seal_count: 1,
  }
}

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
  vi.clearAllMocks()
})

afterEach(() => {
  act(() => root.unmount())
  host.remove()
})

function render(data = route()) {
  act(() => root.render(
    <LimitRouteMap data={data} onFocusDay={focusDay} onSelectStock={selectStock} />,
  ))
}

it('opens a switch day with its related stocks and opens stock details separately', () => {
  render()
  const dayButton = host.querySelector<HTMLButtonElement>('button[title="查看 2026-10-29 日内叠加"]')!
  act(() => dayButton.click())
  expect(focusDay).toHaveBeenCalledWith('2026-10-29', ['000001.SZ', '000002.SZ'])
  const stockButton = host.querySelector<HTMLButtonElement>('button[title="九阳股份 002242.SZ"]')!
  act(() => stockButton.click())
  expect(selectStock).toHaveBeenCalledWith('002242.SZ', '九阳股份')
})

it('keeps the clicked stock when a switch day already fills all eight minute slots', () => {
  const data = route()
  data.switch_days[0].minute_symbols = Array.from({ length: 8 }, (_, index) => `00000${index}.SZ`)
  render(data)
  const eventButton = [...host.querySelectorAll<HTMLButtonElement>('button')]
    .find(button => button.title.startsWith('2026-10-29 · 九阳股份'))!
  act(() => eventButton.click())
  const selected = focusDay.mock.calls[0][1] as string[]
  expect(selected).toHaveLength(8)
  expect(selected[0]).toBe('002242.SZ')
})

it('disables switch-day links when minute coverage is missing', () => {
  const data = route()
  data.switch_days[0].has_minute = false
  render(data)
  const dayButton = host.querySelector<HTMLButtonElement>('button[title="该日没有本地分钟数据"]')!
  expect(dayButton.disabled).toBe(true)
  act(() => dayButton.click())
  expect(focusDay).not.toHaveBeenCalled()
})

it('explains the empty route without treating missing data as zero performance', () => {
  const data = route()
  data.rows = []
  data.daily_leaders = []
  data.leader_phases = []
  data.switch_days = []
  render(data)
  expect(host.textContent).toContain('当前窗口内没有已封板标的')
  expect(host.querySelector('table')).toBeNull()
})

it('shows the whole 60-day relay and later boards with a readable default scale', () => {
  const data = route()
  data.dates = Array.from({ length: 60 }, (_, index) =>
    new Date(Date.UTC(2026, 8, index + 1)).toISOString().slice(0, 10),
  )
  const lastDate = data.dates[data.dates.length - 1]
  data.rows[0].events.push({
    ...data.rows[0].events[0], date: lastDate, consec: 7,
  })
  render(data)
  const table = host.querySelector<HTMLTableElement>('table')!
  expect(table.style.width).toBe('2250px')
  expect(table.style.minWidth).toBe('2250px')
  expect(table.parentElement?.className).not.toContain('max-h-')
  expect(table.querySelectorAll('thead tr:first-child th')).toHaveLength(61)
  expect([...table.querySelectorAll('button')].some(button =>
    button.title.startsWith(`${lastDate} · 九阳股份`) && button.title.includes('7板'),
  )).toBe(true)
})

it('lets users switch between overview, comfortable, and enlarged route scales', () => {
  render()
  const comfort = [...host.querySelectorAll<HTMLButtonElement>('button')]
    .find(button => button.textContent === '标准')!
  expect(comfort.getAttribute('aria-pressed')).toBe('true')
  expect(host.querySelector('table')?.style.width).toBe('278px')
  const large = [...host.querySelectorAll<HTMLButtonElement>('button')]
    .find(button => button.textContent === '放大')!
  act(() => large.click())
  expect(large.getAttribute('aria-pressed')).toBe('true')
  expect(host.querySelector('table')?.style.width).toBe('352px')
  const overview = [...host.querySelectorAll<HTMLButtonElement>('button')]
    .find(button => button.textContent === '全貌')!
  act(() => overview.click())
  expect(host.querySelector('table')?.style.width).toBe('100%')
  expect(overview.getAttribute('aria-pressed')).toBe('true')
})
