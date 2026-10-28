import { describe, expect, it } from 'vitest'
import { canSaveResult, pageAfterDelete } from './savedResults'

describe('canSaveResult', () => {
  const okResult = { error: null, run_id: 'r1' }

  it('allows saving a freshly completed run', () => {
    expect(canSaveResult(okResult, { isPending: false, viewingSaved: false })).toBe(true)
  })

  it('forbids re-saving while viewing a saved snapshot', () => {
    expect(canSaveResult(okResult, { isPending: false, viewingSaved: true })).toBe(false)
  })

  it('forbids saving while a backtest is running', () => {
    expect(canSaveResult(okResult, { isPending: true, viewingSaved: false })).toBe(false)
  })

  it('forbids error results and results without a run_id', () => {
    expect(canSaveResult({ error: 'boom', run_id: 'r1' }, { isPending: false, viewingSaved: false })).toBe(false)
    expect(canSaveResult({ error: null, run_id: null }, { isPending: false, viewingSaved: false })).toBe(false)
    expect(canSaveResult(null, { isPending: false, viewingSaved: false })).toBe(false)
  })
})

describe('pageAfterDelete', () => {
  it('keeps the current page when it still has records', () => {
    // 45 条 20/页 → 删 1 条后 44 条仍 3 页, 第 3 页有 4 条
    expect(pageAfterDelete(3, 44, 20)).toBe(3)
  })

  it('recycles to a non-empty page when the last page becomes empty', () => {
    // 41 条 20/页 → 删 1 条后 40 条恰好 2 页, 空掉的第 3 页回到 2
    expect(pageAfterDelete(3, 40, 20)).toBe(2)
    // 21 条 → 删 1 条后 20 条只有 1 页, 第 2 页回到 1
    expect(pageAfterDelete(2, 20, 20)).toBe(1)
  })

  it('never returns page < 1 even when everything is gone', () => {
    expect(pageAfterDelete(5, 0, 20)).toBe(1)
    expect(pageAfterDelete(0, 0, 20)).toBe(1)
  })
})
