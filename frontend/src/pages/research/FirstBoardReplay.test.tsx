// @vitest-environment jsdom
// 首板回放页交互检查:
// - 历史图/短周期图都不含 D 之后的数据; 展开后续不改动历史图
// - 后续走势默认折叠, 切换事件后重新折叠
// - 16 规则切换只改观察口径
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const chartProps: any[] = []
vi.mock('@/components/EChartsCandlestick', () => ({
  EChartsCandlestick: (props: any) => {
    chartProps.push(props)
    return null
  },
}))
vi.mock('@/components/PageHeader', () => ({
  PageHeader: ({ title, subtitle }: any) => <div>{title}<span>{typeof subtitle === 'string' ? subtitle : ''}</span></div>,
}))
vi.mock('@/components/Toast', () => ({ toast: vi.fn() }))

import { FirstBoardReplay } from './FirstBoardReplay'

const bundle = JSON.parse(readFileSync(
  resolve(process.cwd(), 'public/research/firstboard/replay.json'),
  'utf8',
))

let container: HTMLDivElement
let root: Root

async function flush(times = 6) {
  for (let i = 0; i < times; i += 1) {
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 15)) })
  }
}

function buttons(text: string): HTMLButtonElement[] {
  return Array.from(container.querySelectorAll('button'))
    .filter(b => (b.textContent ?? '').includes(text))
}

function chart(height: number) {
  return [...chartProps].reverse().find(p => p.height === height)
}

function lastDateOf(chartData: { date: string }[]): string {
  return chartData[chartData.length - 1]?.date ?? ''
}

beforeEach(() => {
  ;(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true
  chartProps.length = 0
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => bundle })))
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  act(() => {
    root.render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <FirstBoardReplay />
      </QueryClientProvider>,
    )
  })
})

afterEach(async () => {
  await act(async () => root.unmount())
  container.remove()
  vi.unstubAllGlobals()
})

it('keeps D-out data out of both history charts until the user expands it', async () => {
  await flush()
  const code = bundle.symbols[0].code
  const events = bundle.events.filter((e: any) => e.code === code)
  // 选一个早期事件: 若长图仍用全量数据, 就会在这里暴露 D 之后的 K 线
  const older = events[0]
  await act(async () => { buttons(older.date)[0].click() })
  await flush()

  const long = chart(300)
  const short = chart(340)
  expect(long).toBeTruthy()
  expect(short).toBeTruthy()

  expect(lastDateOf(long.data)).toBe(older.date)
  expect(long.data.every((b: any) => b.date <= older.date)).toBe(true)
  expect((long.markers ?? []).every((m: any) => m.date <= older.date)).toBe(true)
  expect(lastDateOf(short.data)).toBe(older.date)
  expect(short.data.every((b: any) => b.date <= older.date)).toBe(true)
  expect(short.data.length).toBeLessThanOrEqual(90)

  const longLenBefore = long.data.length
  const longJsonBefore = JSON.stringify(long.data)
  expect(container.textContent).not.toContain('后续可观测日')

  const expand = buttons('展开 D 后走势与结果')[0]
  expect(expand).toBeTruthy()
  await act(async () => { expand.click() })
  await flush()

  expect(container.textContent).toContain('后续可观测日')
  const future = chart(220)
  expect(future).toBeTruthy()
  // 后续图首根严格晚于 D, 不与历史图重叠
  expect(future.data[0].date > older.date).toBe(true)
  // 展开不改变历史图/短周期图的数据与缩放输入
  expect(JSON.stringify(long.data)).toBe(longJsonBefore)
  expect(long.data.length).toBe(longLenBefore)
  expect(lastDateOf(chart(340).data)).toBe(older.date)
})

it('keeps every one of the 27 frozen events truncated at D', async () => {
  await flush()
  let visited = 0
  for (const sym of bundle.symbols) {
    await act(async () => { buttons(sym.name)[0].click() })
    await flush(2)
    for (const ev of bundle.events.filter((e: any) => e.code === sym.code)) {
      await act(async () => { buttons(ev.date)[0].click() })
      await flush(2)
      const long = chart(300)
      const short = chart(340)
      expect(long, `${ev.event_id} long`).toBeTruthy()
      expect(short, `${ev.event_id} short`).toBeTruthy()
      expect(lastDateOf(long.data), `${ev.event_id} long max`).toBe(ev.date)
      expect(lastDateOf(short.data), `${ev.event_id} short max`).toBe(ev.date)
      expect((long.markers ?? []).every((m: any) => m.date <= ev.date), `${ev.event_id} markers`).toBe(true)
      visited += 1
    }
  }
  expect(visited).toBe(27)
}, 120000)

it('re-collapses the future view when switching to another frozen event', async () => {
  await flush()
  const code = bundle.symbols[0].code
  const events = bundle.events.filter((e: any) => e.code === code)
  const older = events[0]
  const newer = events[events.length - 1]
  expect(older.date).not.toBe(newer.date)

  await act(async () => { buttons('展开 D 后走势与结果')[0].click() })
  await flush()
  expect(container.textContent).toContain('后续可观测日')

  const olderButton = buttons(older.date)[0]
  expect(olderButton).toBeTruthy()
  await act(async () => { olderButton.click() })
  await flush()

  expect(container.textContent).not.toContain('后续可观测日')
  expect(buttons('展开 D 后走势与结果').length).toBe(1)
  expect(lastDateOf(chart(340).data)).toBe(older.date)
})

it('switching the candidate rule only changes the reference readout', async () => {
  await flush()
  expect(container.textContent).toContain('默认参考 · 暂定')
  const code = bundle.symbols[0].code
  const event = bundle.events.filter((e: any) => e.code === code).at(-1)
  const otherRule = bundle.rules.find((r: string) => r !== bundle.default_rule && event.rules[r]?.P != null)
  expect(otherRule).toBeTruthy()

  const row = Array.from(container.querySelectorAll('tr'))
    .find(tr => (tr.textContent ?? '').includes(otherRule!))
  expect(row).toBeTruthy()
  await act(async () => { (row as HTMLElement).click() })
  await flush()

  expect(container.textContent).toContain(`对比口径 ${otherRule}`)
  expect(container.textContent).not.toContain('默认参考 · 暂定')
})
