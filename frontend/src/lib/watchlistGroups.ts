import type { WatchlistEntry } from '@/lib/api'

export type WatchlistGroupFilter = 'all' | 'ungrouped' | string

/** 多组并存：一只标的计入每个所属分组。 */
export function watchlistGroupCounts(entries: WatchlistEntry[]): Record<string, number> {
  const counts: Record<string, number> = { ungrouped: 0 }
  for (const entry of entries) {
    const groupIds = entry.group_ids ?? []
    if (groupIds.length === 0) counts.ungrouped += 1
    else for (const groupId of groupIds) counts[groupId] = (counts[groupId] ?? 0) + 1
  }
  return counts
}

export function filterWatchlistEntries(entries: WatchlistEntry[], filter: WatchlistGroupFilter): WatchlistEntry[] {
  if (filter === 'all') return entries
  if (filter === 'ungrouped') return entries.filter(entry => (entry.group_ids ?? []).length === 0)
  return entries.filter(entry => (entry.group_ids ?? []).includes(filter))
}
