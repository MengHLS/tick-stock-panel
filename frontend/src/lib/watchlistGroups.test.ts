import { describe, expect, it } from 'vitest'
import type { WatchlistGroup } from '@/lib/api'
import { filterEntriesVisibleInAll } from '@/lib/watchlistGroups'

const groups = [
  { id: 'shown', name: '显示', color: 'sky' },
  { id: 'hidden', name: '隐藏', color: 'rose', show_in_all: false },
] as WatchlistGroup[]

const entries = [
  { symbol: '000001.SZ', added_at: '', group_ids: [] },
  { symbol: '000002.SZ', added_at: '', group_ids: ['shown'] },
  { symbol: '000003.SZ', added_at: '', group_ids: ['hidden'] },
  { symbol: '000004.SZ', added_at: '', group_ids: ['hidden', 'shown'] },
]

describe('filterEntriesVisibleInAll', () => {
  it('未分组和任一可见分组成员进入全部，仅隐藏分组成员不进入', () => {
    expect(filterEntriesVisibleInAll(entries, groups).map(entry => entry.symbol)).toEqual([
      '000001.SZ',
      '000002.SZ',
      '000004.SZ',
    ])
  })

  it('没有分组数据时由调用方决定回退，不在此函数内猜测', () => {
    expect(filterEntriesVisibleInAll(entries, []).map(entry => entry.symbol)).toEqual([
      '000001.SZ',
    ])
  })
})
