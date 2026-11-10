import { expect, it } from 'vitest'
import {
  buildHourlyBars,
  summarizeStructure,
  type HourlyBar,
} from './AbnormalMiniStructure'

function row(datetime: string, high: number, low: number, close: number, volume: number) {
  return {
    datetime,
    open: close,
    high,
    low,
    close,
    volume,
    amount: null,
  }
}

function completeBar(high: number, low: number, close: number, volume: number, index: number): HourlyBar {
  return {
    date: `2026-11-0${Math.floor(index / 4) + 3}`,
    time: ['10:30', '11:30', '14:00', '15:00'][index % 4],
    high,
    low,
    close,
    volume,
    rows: 60,
    complete: true,
  }
}

it('分钟K按上午/下午四个60分钟桶聚合，不跨午休', () => {
  const bars = buildHourlyBars([{
    date: '2026-11-07',
    prev_close: 9,
    rows: [
      row('2026-11-07 09:30:00', 10, 9, 9.5, 100),
      row('2026-11-07 10:29:00', 10.5, 9.8, 10.2, 50),
      row('2026-11-07 10:30:00', 11, 10, 10.8, 120),
      row('2026-11-07 11:30:00', 11.2, 10.5, 11, 80),
      row('2026-11-07 13:00:00', 11.5, 10.9, 11.3, 90),
      row('2026-11-07 14:00:00', 12, 11.2, 11.9, 110),
      row('2026-11-07 15:00:00', 12.2, 11.7, 12, 70),
    ],
  }])

  expect(bars).toHaveLength(4)
  expect(bars.map(bar => bar.time)).toEqual(['10:30', '11:30', '14:00', '15:00'])
  expect(bars[0]).toMatchObject({ high: 10.5, low: 9, close: 10.2, volume: 150, rows: 2 })
  expect(bars[1]).toMatchObject({ high: 11.2, low: 10, close: 11, volume: 200, rows: 2 })
  expect(bars[2]).toMatchObject({ high: 11.5, low: 10.9, close: 11.3, volume: 90, rows: 1 })
  expect(bars[3]).toMatchObject({ high: 12.2, low: 11.2, close: 12, volume: 180, rows: 2 })
})

it('结构汇总：箱体、上沿距离、量能、抬高结构', () => {
  const highs = [10, 10.5, 10.2, 10.8, 10.5, 11.2, 10.9, 11.5, 11.3]
  const lows = [9.5, 9.8, 9.6, 10, 9.9, 10.3, 10.1, 10.5, 10.4]
  const bars = highs.map((high, index) =>
    completeBar(high, lows[index], index === highs.length - 1 ? 11.3 : high - 0.1, index === highs.length - 1 ? 200 : 100, index),
  )

  const summary = summarizeStructure(bars, 12)
  expect(summary).not.toBeNull()
  expect(summary).toMatchObject({
    sampleBars: 9,
    boxHigh: 11.5,
    boxLow: 9.5,
    current: 11.3,
    trend: 'up',
    volRatio: 2,
    volumeLabel: '放量',
  })
  expect(summary!.topDist).toBeCloseTo(11.5 / 11.3 - 1, 6)
  expect(summary!.capDist).toBeCloseTo(12 / 11.5 - 1, 6)
})

it('结构汇总：低点降低时识别为下行结构', () => {
  const highs = [11.5, 11.8, 11.4, 11.6, 11.1, 11.3, 10.8, 11.0, 10.7]
  const lows = [10.8, 11.0, 10.6, 10.9, 10.2, 10.5, 9.8, 10.1, 9.5]
  const bars = highs.map((high, index) =>
    completeBar(high, lows[index], index === highs.length - 1 ? 10.7 : high - 0.1, 100, index),
  )

  expect(summarizeStructure(bars, 12)?.trend).toBe('down')
})

it('不足4根60分钟K时不出结构', () => {
  const bars = [completeBar(10, 9, 9.5, 100, 0)]
  expect(summarizeStructure(bars, 12)).toBeNull()
})
