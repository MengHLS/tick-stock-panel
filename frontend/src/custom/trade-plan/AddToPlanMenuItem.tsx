import { useState } from 'react'
import { toast } from '@/components/Toast'
import { IconPlan } from '@/components/BrandIcons'
import type { FrontendSlotContextMap } from '@/extensions/types'
import { PlanForm } from './PlanForm'

/** 自选行右键菜单项：打开交易计划弹窗，并保持父菜单在弹窗期间挂载。 */
export function AddToPlanMenuItem({
  symbol,
  name,
  close,
  setPinned,
}: FrontendSlotContextMap['watchlist.row-menu']) {
  const [open, setOpen] = useState(false)

  const finish = () => {
    setOpen(false)
    setPinned(false)
    close()
  }

  return (
    <>
      <button
        type="button"
        role="menuitem"
        onClick={() => {
          setPinned(true)
          setOpen(true)
        }}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-[11px] text-foreground transition-colors hover:bg-elevated"
      >
        <IconPlan className="h-3.5 w-3.5 text-accent" />
        加入交易计划
      </button>

      {open && (
        <PlanForm
          plan={null}
          initialSymbol={symbol}
          initialName={name ?? undefined}
          onClose={finish}
          onSaved={() => {
            toast('已加入交易计划', 'success')
          }}
        />
      )}
    </>
  )
}
