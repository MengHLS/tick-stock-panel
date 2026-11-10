import { useState } from 'react'
import { ListFilter } from 'lucide-react'
import type { FrontendSlotContextMap } from '@/extensions/types'
import { DynamicGroupDialog } from './DynamicGroupDialog'

export function DynamicGroupButton({ selectedGroup, refresh }: FrontendSlotContextMap['watchlist.toolbar']) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex h-8 items-center gap-1.5 rounded-btn bg-elevated px-2.5 text-xs text-secondary transition-colors hover:bg-elevated/80 hover:text-foreground"
        title="管理动态分组"
        aria-label="管理动态分组"
      >
        <ListFilter className="h-4 w-4" />
        <span className="hidden xl:inline">动态分组</span>
      </button>
      {open && (
        <DynamicGroupDialog
          currentGroupId={selectedGroup}
          onClose={() => setOpen(false)}
          onChanged={refresh}
        />
      )}
    </>
  )
}
