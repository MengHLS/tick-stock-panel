import { describe, expect, it } from 'vitest'
import {
  resolveCandidateFills,
  resolveStrategyFills,
} from './fillDefaults'

describe('resolveStrategyFills', () => {
  it('uses the strategy declared entry_fill/exit_fill', () => {
    expect(resolveStrategyFills({ entry_fill: 'close_t', exit_fill: 'signal_next_minute' }))
      .toEqual({ entry: 'close_t', exit: 'signal_next_minute' })
  })

  it('falls back to legacy matching for both sides when fills are absent', () => {
    expect(resolveStrategyFills({ matching: 'close_t' })).toEqual({ entry: 'close_t', exit: 'close_t' })
  })

  it('defaults both sides to next open (no leakage from a previous strategy)', () => {
    expect(resolveStrategyFills(null)).toEqual({ entry: 'open_t+1', exit: 'open_t+1' })
    expect(resolveStrategyFills({})).toEqual({ entry: 'open_t+1', exit: 'open_t+1' })
  })

  it('ignores illegal declared values instead of passing them through', () => {
    expect(resolveStrategyFills({ entry_fill: 'next_open', exit_fill: 'open_t+2' }))
      .toEqual({ entry: 'open_t+1', exit: 'open_t+1' })
    expect(resolveStrategyFills({ entry_fill: 'bad', matching: 'close_t' }))
      .toEqual({ entry: 'close_t', exit: 'close_t' })
  })

  it('keeps a legal declared fill ahead of matching', () => {
    expect(resolveStrategyFills({ entry_fill: 'open_t+1', matching: 'close_t' }))
      .toEqual({ entry: 'open_t+1', exit: 'close_t' })
  })
})

describe('resolveCandidateFills', () => {
  it('prefers the candidate explicit fills', () => {
    expect(resolveCandidateFills({ entry_fill: 'close_t', exit_fill: 'open_t+1', matching: 'close_t' }))
      .toEqual({ entry: 'close_t', exit: 'open_t+1' })
  })

  it('uses legacy candidate matching when fills are absent', () => {
    expect(resolveCandidateFills({ matching: 'close_t' })).toEqual({ entry: 'close_t', exit: 'close_t' })
  })

  it('returns null when the candidate carries no fill information', () => {
    expect(resolveCandidateFills(null)).toBeNull()
    expect(resolveCandidateFills({})).toBeNull()
    expect(resolveCandidateFills({ entry_fill: 'bad', exit_fill: 'bad' })).toBeNull()
  })

  it('leaves a missing side undefined so the strategy default can fill it', () => {
    expect(resolveCandidateFills({ entry_fill: 'close_t' })).toEqual({ entry: 'close_t', exit: undefined })
    expect(resolveCandidateFills({ exit_fill: 'signal_next_minute' }))
      .toEqual({ entry: undefined, exit: 'signal_next_minute' })
  })
})
