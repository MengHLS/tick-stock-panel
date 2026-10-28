import { describe, expect, it } from 'vitest'
import { decideDetailSync } from './detailSync'

const base = {
  detailId: 'a',
  selectedStrategy: 'a',
  loadedIdentity: null as string | null,
  identity: 'stock:a',
  hasDraftRestore: false,
  candidatePending: false,
}

describe('decideDetailSync', () => {
  it('applies defaults the first time a strategy is selected', () => {
    expect(decideDetailSync(base)).toBe('reset')
  })

  it('keeps manual edits on a same-strategy refetch, even if the config signature changed', () => {
    // identity 不含配置签名: refetch 后签名变化, 身份不变 → 不重置表单
    expect(decideDetailSync({ ...base, loadedIdentity: 'stock:a' })).toBe('keep')
    expect(decideDetailSync({ ...base, loadedIdentity: 'stock:a', identity: 'stock:a' })).toBe('keep')
  })

  it('resets when switching to a different strategy', () => {
    expect(decideDetailSync({ ...base, selectedStrategy: 'b', detailId: 'b', loadedIdentity: 'stock:a', identity: 'stock:b' }))
      .toBe('reset')
  })

  it('drops late responses that are not the current selection', () => {
    expect(decideDetailSync({ ...base, selectedStrategy: 'b', detailId: 'a' })).toBe('skip')
    expect(decideDetailSync({ ...base, detailId: null })).toBe('skip')
  })

  it('prefers a pending candidate over a draft/default reset', () => {
    expect(decideDetailSync({ ...base, candidatePending: true })).toBe('candidate')
  })

  it('restores an owned same-strategy draft before default reset', () => {
    expect(decideDetailSync({ ...base, hasDraftRestore: true })).toBe('restoreDraft')
  })
})
