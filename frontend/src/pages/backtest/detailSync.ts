/**
 * 策略详情到达时的表单同步决策 (纯函数)。
 *
 * 关键行为:
 * - 同一个策略（即使 refetch 后配置签名变化）不重复重置表单, 保留用户手改;
 * - 只有切换到另一个策略才按该策略默认重置;
 * - 候选方案载入 / 同策略草稿恢复是明确分支, 优先于默认重置;
 * - 迟到/过期的详情响应不能回填到当前选择。
 */

export type DetailSyncAction = 'skip' | 'keep' | 'candidate' | 'restoreDraft' | 'reset'

export interface DetailSyncInput {
  /** 详情对应的策略 id (迟到响应可能不是当前选择) */
  detailId: string | null | undefined
  /** 当前选中的策略 id */
  selectedStrategy: string | null
  /** 已应用过同步的身份键 (assetType:strategyId), null 表示尚未加载过 */
  loadedIdentity: string | null
  /** 本次详情对应的身份键 */
  identity: string
  /** 是否有该策略的同签名 localStorage 草稿可恢复 */
  hasDraftRestore: boolean
  /** 是否有候选方案正在等待详情补齐成交口径 */
  candidatePending: boolean
}

export function decideDetailSync(input: DetailSyncInput): DetailSyncAction {
  if (!input.detailId || input.detailId !== input.selectedStrategy) return 'skip'
  if (input.loadedIdentity === input.identity) return 'keep'
  if (input.candidatePending) return 'candidate'
  if (input.hasDraftRestore) return 'restoreDraft'
  return 'reset'
}
