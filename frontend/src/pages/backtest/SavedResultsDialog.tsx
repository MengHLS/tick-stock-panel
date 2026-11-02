import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Archive, Loader2, Trash2, X } from 'lucide-react'
import { Modal } from '@/components/Modal'
import { ExtensionSlot } from '@/extensions/ExtensionSlot'
import { toast } from '@/components/Toast'
import { api, type SavedStrategyBacktestDetail } from '@/lib/api'
import { cnDateTimeFromUtc, fmtPct } from '@/lib/format'
import { QK } from '@/lib/queryKeys'
import { pageAfterDelete } from './savedResults'

const PAGE_SIZE = 20

/**
 * 已保存回测结果: 打开即恢复保存时的完整快照 (交易/曲线/统计/配置), 不触发回测。
 * 与「候选方案」不同: 候选只存配置与指标摘要, 这里存的是那次运行的原始结果。
 */
export function SavedResultsDialog({ onOpen, onDeleted, currentSavedId, onClose }: {
  onOpen: (detail: SavedStrategyBacktestDetail) => void
  onDeleted: (savedId: string) => void
  /** 当前正在查看的保存记录 (用于高亮) */
  currentSavedId?: string | null
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const list = useQuery({
    queryKey: QK.savedStrategyResults(page, PAGE_SIZE),
    queryFn: () => api.savedStrategyBacktestResults(page, PAGE_SIZE),
  })

  const open = useMutation({
    mutationFn: (savedId: string) => api.savedStrategyBacktestResult(savedId),
    onSuccess: detail => onOpen(detail),
    onError: error => toast(`打开失败 · ${String((error as Error).message || error)}`, 'error'),
  })

  const remove = useMutation({
    mutationFn: (savedId: string) => api.deleteSavedStrategyBacktestResult(savedId),
    onSuccess: (_data, savedId) => {
      // 删除后回收页码: 否则停在最后一页会 total>0 却空页
      const nextTotal = Math.max(0, total - 1)
      setPage(current => pageAfterDelete(current, nextTotal, PAGE_SIZE))
      queryClient.invalidateQueries({ queryKey: ['backtest-saved-results'] })
      queryClient.removeQueries({ queryKey: QK.savedStrategyResult(savedId) })
      onDeleted(savedId)
      toast('已删除保存的回测结果', 'success')
    },
    onError: error => toast(`删除失败 · ${String((error as Error).message || error)}`, 'error'),
  })

  const items = list.data?.items ?? []
  const total = list.data?.total ?? 0
  const skipped = list.data?.skipped ?? 0
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const safePage = Math.max(1, Math.min(page, pages))

  return (
    <Modal
      onClose={onClose}
      labelledBy="saved-results-title"
      panelClassName="flex max-h-[82vh] w-[94vw] max-w-5xl flex-col overflow-hidden rounded-card border border-border bg-base shadow-2xl"
    >
      <header className="flex shrink-0 items-center gap-3 border-b border-border px-4 py-3">
        <Archive className="h-4 w-4 text-accent" />
        <div className="min-w-0">
          <h2 id="saved-results-title" className="text-sm font-semibold text-foreground">已保存的回测结果</h2>
          <div className="mt-0.5 text-[11px] text-muted">打开的是保存当时的完整快照，不会重新回测；之后改参数或策略改动都不影响它</div>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="关闭已保存结果"
          className="ml-auto rounded-btn p-1.5 text-muted transition-colors hover:bg-elevated hover:text-foreground"
        >
          <X className="h-4 w-4" />
        </button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
        {list.isLoading && (
          <div className="flex items-center gap-2 py-10 text-sm text-secondary">
            <Loader2 className="h-4 w-4 animate-spin" />
            加载中…
          </div>
        )}
        {list.isError && (
          <div className="rounded-card border border-danger/40 bg-danger/5 px-3 py-2 text-xs text-danger">
            历史结果加载失败 · {String((list.error as Error)?.message || list.error)}
          </div>
        )}
        {!list.isLoading && !list.isError && skipped > 0 && (
          <div className="mb-2 rounded-btn border border-amber-400/40 bg-amber-400/5 px-3 py-2 text-xs text-amber-500">
            有 {skipped} 条保存记录已损坏或版本不受支持，已在列表中跳过（文件未删除）
          </div>
        )}
        {!list.isLoading && !list.isError && items.length === 0 && (
          <div className="py-12 text-center">
            <div className="text-sm font-medium text-secondary">
              {total > 0 ? '本页已无记录' : '暂无已保存结果'}
            </div>
            <div className="mt-1 text-xs text-muted">
              {total > 0 ? '已自动回到有记录的一页' : '在结果区点「保存结果」，即可把这次运行完整保存下来'}
            </div>
          </div>
        )}
        {items.length > 0 && (
          <table className="w-full min-w-[860px] text-sm text-foreground">
            <thead className="bg-elevated">
              <tr className="text-left text-secondary">
                <th className="px-3 py-2 font-medium">名称</th>
                <th className="px-3 py-2 font-medium">策略</th>
                <th className="px-3 py-2 font-medium">区间</th>
                <th className="px-3 py-2 font-medium">模式</th>
                <th className="px-3 py-2 text-right font-medium">交易</th>
                <th className="px-3 py-2 text-right font-medium">总收益</th>
                <th className="px-3 py-2 font-medium">保存时间</th>
                <th className="px-3 py-2 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {items.map(item => (
                <tr
                  key={item.saved_id}
                  className={`border-t border-border ${item.saved_id === currentSavedId ? 'bg-accent/10' : ''}`}
                >
                  <td className="px-3 py-2">
                    <div className="max-w-[16rem] truncate font-medium text-foreground" title={item.name ?? undefined}>
                      {item.name || item.strategy_name || '未命名结果'}
                    </div>
                    <div className="mt-0.5 font-mono text-[10px] text-muted">{item.saved_id}</div>
                  </td>
                  <td className="px-3 py-2 text-secondary">{item.strategy_name || item.strategy_id || '—'}</td>
                  <td className="px-3 py-2 font-mono text-[11px] text-secondary">
                    {item.start ? String(item.start).slice(0, 10) : '—'} ~ {item.end ? String(item.end).slice(0, 10) : '—'}
                  </td>
                  <td className="px-3 py-2 text-[11px] text-secondary">{item.mode === 'full' ? '全量' : item.mode === 'position' ? '仓位' : item.mode || '—'}</td>
                  <td className="px-3 py-2 text-right num">{item.n_trades ?? '—'}</td>
                  <td className="px-3 py-2 text-right num">{item.total_return == null ? '—' : fmtPct(item.total_return)}</td>
                  <td className="px-3 py-2 text-[11px] text-secondary">{cnDateTimeFromUtc(item.saved_at) || item.saved_at}</td>
                  <td className="px-3 py-2">
                    <div className="flex items-center justify-end gap-1.5">
                      <button
                        type="button"
                        onClick={() => open.mutate(item.saved_id)}
                        disabled={open.isPending && open.variables === item.saved_id}
                        className="rounded-btn border border-border bg-surface px-2 py-1 text-xs text-secondary transition-colors hover:border-accent/40 hover:text-accent disabled:opacity-50"
                      >
                        {open.isPending && open.variables === item.saved_id ? '打开中…' : '打开'}
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          const label = item.name || item.strategy_name || '未命名结果'
                          if (window.confirm(`确认删除已保存结果「${label}」？`)) remove.mutate(item.saved_id)
                        }}
                        aria-label={`删除已保存结果 ${item.name || item.saved_id}`}
                        title="删除这条保存记录"
                        className="rounded-btn p-1.5 text-muted transition-colors hover:bg-danger/10 hover:text-danger"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <ExtensionSlot
        name="backtest.savedResults.extra"
        context={{
          apiVersion: 1,
          currentSavedId: currentSavedId ?? null,
          openSaved: savedId => open.mutate(savedId),
          busy: open.isPending,
        }}
      />

      {total > PAGE_SIZE && (
        <footer className="flex shrink-0 items-center justify-between gap-3 border-t border-border px-4 py-2 text-xs text-muted">
          <span>共 {total} 条</span>
          <div className="flex items-center gap-2">
            <span className="num">{safePage} / {pages}</span>
            <button
              type="button"
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={safePage <= 1}
              className="rounded-btn border border-border bg-surface px-2.5 py-1 text-xs text-secondary transition-colors hover:border-accent/40 hover:text-accent disabled:cursor-not-allowed disabled:opacity-45"
            >
              上一页
            </button>
            <button
              type="button"
              onClick={() => setPage(p => Math.min(pages, p + 1))}
              disabled={safePage >= pages}
              className="rounded-btn border border-border bg-surface px-2.5 py-1 text-xs text-secondary transition-colors hover:border-accent/40 hover:text-accent disabled:cursor-not-allowed disabled:opacity-45"
            >
              下一页
            </button>
          </div>
        </footer>
      )}
    </Modal>
  )
}
