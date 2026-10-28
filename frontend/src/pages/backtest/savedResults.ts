/**
 * 已保存回测结果的页面级判定 (纯函数, 便于回归):
 * - canSaveResult: 只有「当前刚完成的一次运行」可保存; 正在查看历史快照时禁止再保存。
 * - pageAfterDelete: 删除后页码回收, 避免 total>0 却停在空页。
 */

export interface SaveGate {
  /** 回测任务仍在运行 */
  isPending: boolean
  /** 当前展示的是历史快照 */
  viewingSaved: boolean
}

export function canSaveResult(
  result: { error?: string | null; run_id?: string | null } | null | undefined,
  gate: SaveGate,
): boolean {
  if (!result) return false
  if (gate.isPending) return false
  if (gate.viewingSaved) return false
  if (result.error) return false
  return !!result.run_id
}

export function pageAfterDelete(page: number, totalAfterDelete: number, pageSize: number): number {
  const size = Math.max(1, Math.floor(pageSize))
  const pages = Math.max(1, Math.ceil(Math.max(0, totalAfterDelete) / size))
  return Math.max(1, Math.min(Math.floor(page) || 1, pages))
}
