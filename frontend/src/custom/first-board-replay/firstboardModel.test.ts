import { describe, expect, it } from 'vitest'
import {
  barsUpToD,
  describeEvent,
  describeRule,
  describeScaleCheck,
  futureWindow,
  positionBucket,
  replayWindow,
  scaleStateLabel,
  toBars,
  type FbBar,
  type FbEvent,
  type FbScaleCheck,
  type FbSymbol,
} from './firstboardModel'

function bar(date: string, close: number, firstBoard = false): FbBar {
  return { date, open: close, high: close + 1, low: close - 1, close, rawClose: close, firstBoard }
}

const bars: FbBar[] = [
  bar('2026-07-01', 10),
  bar('2026-07-02', 11),
  bar('2026-07-03', 12, true),
  bar('2026-07-06', 13),
  bar('2026-07-07', 14),
]

describe('D 日截断', () => {
  it('barsUpToD never returns bars after D', () => {
    const cut = barsUpToD(bars, '2026-07-03')
    expect(cut.map(b => b.date)).toEqual(['2026-07-01', '2026-07-02', '2026-07-03'])
  })

  it('replayWindow keeps the last n bars only up to D', () => {
    const win = replayWindow(bars, '2026-07-03', 2)
    expect(win.map(b => b.date)).toEqual(['2026-07-02', '2026-07-03'])
  })

  it('futureWindow only exists when explicitly requested and starts strictly after D', () => {
    const future = futureWindow(bars, '2026-07-03', 20)
    expect(future.map(b => b.date)).toEqual(['2026-07-06', '2026-07-07'])
    expect(future.every(b => b.date > '2026-07-03')).toBe(true)
  })

  it('changing D never changes the long-history bars themselves', () => {
    expect(barsUpToD(bars, '2026-07-01')).toHaveLength(1)
    expect(barsUpToD(bars, '2026-07-06')).toHaveLength(4)
    expect(bars).toHaveLength(5)
  })

  it('future price extremes cannot leak into history selections', () => {
    const d = '2026-07-03'
    const before = barsUpToD(bars, d).map(b => ({ ...b }))
    const mutated = bars.map(b => (b.date > d ? { ...b, close: 9999, high: 9999, low: 1 } : b))
    expect(barsUpToD(mutated, d)).toEqual(before)
    expect(replayWindow(mutated, d, 10)).toEqual(replayWindow(bars, d, 10))
  })
})

describe('transforms', () => {
  const symbol: FbSymbol = {
    code: '000810.SZ',
    name: '创维数字',
    board: 'MAIN',
    listing_date: '1998-06-02',
    firstboard_identity: 'HISTORICAL_REGIME_UNCERTIFIED',
    first_boards: ['2026-07-03'],
    bars: [
      ['2026-07-02', 10, 11, 9, 10.5, 10.2, 0],
      ['2026-07-03', 11, 12, 10, 11.5, 11.4, 1],
    ],
  }
  it('maps compact arrays to bars including the platform first-board flag', () => {
    const mapped = toBars(symbol)
    expect(mapped[1]).toMatchObject({ date: '2026-07-03', close: 11.5, rawClose: 11.4, firstBoard: true })
    expect(mapped[0].firstBoard).toBe(false)
  })

  it('maps position into plain-language buckets with no invented score', () => {
    expect(positionBucket(0.9)).toBe('位于近250日区间上部')
    expect(positionBucket(0.5)).toBe('位于近250日区间中部')
    expect(positionBucket(0.1)).toBe('位于近250日区间下部')
    expect(positionBucket(null)).toBe('位置数据缺失')
  })
})

function eventFixture(): FbEvent {
  const factors = {
    asof: '2026-07-03',
    amount: 1,
    volume: 100,
    turnover_rate: null,
    return_5: 0.1,
    return_20: -0.2,
    return_60: 0.3,
    return_120: 0.4,
    return_250: 0.5,
    position_250: 0.8,
    position_240: 0.8,
    ma_bias_20: 0,
    daily_return_std_20: 0.02,
    volume_ratio_vs_prior5: 2,
    coverage_250: 250,
  }
  return {
    event_id: '000810.SZ@2026-07-03',
    code: '000810.SZ',
    date: '2026-07-03',
    version: 'v1',
    raw_open: 11,
    raw_high: 12,
    raw_low: 10,
    raw_close: 11.5,
    previous_observed_raw_close: 10.5,
    raw_change_vs_previous_observed_close: 0.0952,
    board_identity_certification: 'HISTORICAL_REGIME_UNCERTIFIED',
    shape_certification: 'PENDING',
    coverage_reason: 'AVAILABLE_SYMBOL_BARS_NOT_OFFICIAL_CALENDAR',
    structural_price_basis: 'fixed adjusted snapshot',
    preclose_reason: 'EXCHANGE_PRECLOSE_NOT_IN_SOURCE',
    factors_D_minus_1: { ...factors, asof: '2026-07-02' },
    factors_D_close: factors,
    rules: {
      PA_q0_03_G0_R0: {
        anchor: '2026-06-01', P: 20, P_date: '2026-06-01', P_known_at: '2026-06-02',
        L_setup: 15, L_setup_date: '2026-06-05', first_break: '2026-06-10',
        path_state: 'prior_close_break', skip: false, new_high_after_anchor: false,
        depth: 0.25, nearest_anchor: '2026-06-01', examined: 1, stop: 'nearest_only',
        reason: 'CANDIDATE_RULE_UNFINALIZED', trace: [],
      },
    },
    outcomes: [
      { horizon: 1, available: 1, complete: true, horizon_end: '2026-07-04', close_return: 0.01, max_high_return: 0.02, min_low_return: -0.03, reason: null },
      { horizon: 20, available: 3, complete: false, horizon_end: '2026-07-07', close_return: null, max_high_return: null, min_low_return: null, reason: 'RIGHT_CENSORED' },
    ],
    tracking: [],
  }
}

describe('narrative', () => {
  it('describes background/recent/local without claiming certified board identity', () => {
    const text = describeEvent(eventFixture())
    expect(text.background).toContain('位于近250日区间上部')
    expect(text.background).toContain('近20日下跌')
    expect(text.local).toContain('不是官方涨幅')
    expect(text.board).toContain('未认证')
  })

  it('explains P/L as price levels with knowable dates', () => {
    const rule = eventFixture().rules.PA_q0_03_G0_R0
    const explained = describeRule(rule)
    expect(explained.text).toContain('P=20')
    expect(explained.text).toContain('结构低点 L=15')
    expect(explained.dates.join(' ')).toContain('P 形成于 2026-06-01')
    expect(explained.dates.join(' ')).toContain('最早可知 2026-06-02')
  })

  it('returns an honest message when the rule found no anchor', () => {
    expect(describeRule(null).text).toContain('没有选出')
  })
})

describe('scale check narrative', () => {
  const base: FbScaleCheck = {
    state: 'CROSS_SCALE_VERIFIED',
    judgment: 'INVALID_PENDING_REBUILD',
    window_start: '2026-02-03',
    short_window_start: '2026-03-05',
    anchor_window_start: '2026-02-03',
    structure_window_start: '2026-02-03',
    window_end: '2026-07-15',
    gap_dates: ['2026-06-25'],
    gaps: [],
    reported_note: '外部报告称窗口跨 2026-06-25 转增',
    evidence: ['2026-06-25 原始价台阶：前原始收盘 14.94 → 10.31（-30.99%）'],
    verification: 'VERIFIED_FROM_FROZEN_CSV',
    cause_status: 'PRICE_SCALE_ONLY_PENDING_ANNOUNCEMENT',
    factor_events: [{
      date: '2026-06-25',
      ex_factor: 1.409434,
      dividend: 0.1,
      bonus: 0.4,
      prev_close: 14.94,
      source: 'adj_factor/all.parquet · 本地只读 · sha256 5a957525e43a9c07…',
      announcement_status: 'PENDING_ORIGINAL_ANNOUNCEMENT',
      in_short_window: true,
    }],
  }

  it('invalidates the structure judgment for a verified cross-scale window', () => {
    const explained = describeScaleCheck(base)
    expect(explained.tone).toBe('danger')
    expect(explained.invalidatesJudgment).toBe(true)
    expect(explained.title).toContain('作废')
    expect(explained.summary).toContain('2026-06-25')
    expect(explained.summary).toContain('只证明尺度异常')
    expect(explained.causeText).toContain('公告原件')
  })

  it('keeps externally reported ex-rights as UNKNOWN, not verified', () => {
    const explained = describeScaleCheck({
      ...base,
      state: 'CROSS_SCALE_UNVERIFIED',
      judgment: 'UNVERIFIED',
      gap_dates: [],
      evidence: ['冻结 CSV 的 adj_ratio 在本区间恒为 1'],
      verification: 'UNKNOWN',
      cause_status: 'UNKNOWN',
    })
    expect(explained.tone).toBe('warn')
    expect(explained.invalidatesJudgment).toBe(false)
    expect(explained.title).toContain('待核实')
    expect(explained.title).toContain('UNKNOWN')
    expect(explained.summary).toContain('不把口述当已验证')
    expect(explained.causeText).toContain('UNKNOWN')
    expect(explained.details.join(' ')).toContain('外部报告')
  })

  it('marks local factor records as cross-scale without claiming announcement authority', () => {
    const explained = describeScaleCheck({
      ...base,
      state: 'CROSS_SCALE_FACTOR_RECORD',
      judgment: 'UNVERIFIED',
      gap_dates: [],
      verification: 'LOCAL_FACTOR_RECORD_ONLY',
      cause_status: 'LOCAL_FACTOR_RECORD_COVERAGE_UNVERIFIED',
    })
    expect(explained.tone).toBe('warn')
    expect(explained.invalidatesJudgment).toBe(false)
    expect(explained.title).toContain('本地因子记录')
    expect(explained.summary).toContain('非公告权威')
    expect(explained.causeText).toContain('未认证')
  })

  it('does not claim no corporate action when no gap is detected', () => {
    const explained = describeScaleCheck({
      ...base,
      state: 'NO_GAP_DETECTED',
      judgment: 'UNVERIFIED',
      gap_dates: [],
      reported_note: null,
      verification: 'UNKNOWN',
      cause_status: 'UNKNOWN',
    })
    expect(explained.tone).toBe('muted')
    expect(explained.title).toContain('未发现')
    expect(explained.summary).toContain('不等于无除权')
    expect(explained.causeText).toContain('未核对')
  })

  it('does not invalidate structure when anchors are after the price step', () => {
    const explained = describeScaleCheck({
      ...base,
      judgment: 'UNVERIFIED',
      structure_window_start: '2026-07-16',
    })
    expect(explained.tone).toBe('warn')
    expect(explained.invalidatesJudgment).toBe(false)
    expect(explained.title).toContain('图表/指标')
    expect(explained.summary).toContain('结构锚点')
  })

  it('labels only confirmed or pending cross-scale states', () => {
    expect(scaleStateLabel('CROSS_SCALE_VERIFIED', 'INVALID_PENDING_REBUILD')).toContain('作废')
    expect(scaleStateLabel('CROSS_SCALE_VERIFIED', 'UNVERIFIED')).toContain('窗口')
    expect(scaleStateLabel('CROSS_SCALE_FACTOR_RECORD')).toContain('因子记录')
    expect(scaleStateLabel('CROSS_SCALE_UNVERIFIED')).toContain('待核实')
    expect(scaleStateLabel('NO_GAP_DETECTED')).toBeNull()
  })
})
