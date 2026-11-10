import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { toast } from '@/components/Toast'
import { IconPlan } from '@/components/BrandIcons'
import type { FrontendSlotContextMap } from '@/extensions/types'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { PlanForm } from './PlanForm'

/** 自选页工具栏入口：把当前筛选标的带入交易计划弹窗。 */
export function AddToPlanButton({ symbols }: FrontendSlotContextMap['watchlist.toolbar']) {
  const [open, setOpen] = useState(false)
  const uniqueSymbols = useMemo(() => Array.from(new Set(symbols)), [symbols])

  const namesQuery = useQuery({
    queryKey: QK.instrumentNames(uniqueSymbols),
    queryFn: () => api.instrumentNames(uniqueSymbols),
    enabled: open && uniqueSymbols.length > 0,
    staleTime: 300_000,
  })
  const names = namesQuery.data?.names ?? {}
  const options = uniqueSymbols.map(symbol => ({ symbol, name: names[symbol] ?? '' }))
  const single = uniqueSymbols.length === 1 ? options[0] : null

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        disabled={uniqueSymbols.length === 0}
        className="inline-flex h-8 items-center gap-1.5 rounded-btn bg-elevated px-2.5 text-xs text-secondary transition-colors hover:bg-elevated/80 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-45"
        title={uniqueSymbols.length === 0 ? '当前筛选没有标的' : '加入交易计划'}
        aria-label="加入交易计划"
      >
        <IconPlan className="h-4 w-4" />
        <span className="hidden xl:inline">加入计划</span>
      </button>

      {open && (
        <PlanForm
          plan={null}
          initialSymbol={single?.symbol}
          initialName={single?.name}
          symbolOptions={uniqueSymbols.length > 1 ? options : undefined}
          onClose={() => setOpen(false)}
          onSaved={() => {
            toast('已加入交易计划', 'success')
          }}
        />
      )}
    </>
  )
}
