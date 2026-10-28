/**
 * 策略回测「成交口径」默认值解析。
 *
 * 规则（架构契约）: 新选中策略/恢复默认时, 买卖两侧取
 *   策略合法 entry_fill/exit_fill → 合法 backtest_defaults.matching → 系统默认 open_t+1;
 * 不得沿用上一策略的表单值。候选方案载入时:
 *   候选显式 fill → 候选 matching → 策略默认。已保存快照不参与这里, 打开时不重算。
 *
 * 这里只做纯解析, 不读表单、不读 store, 便于回归测试。
 */

export type EntryFill = 'close_t' | 'open_t+1'
export type ExitFill = EntryFill | 'signal_next_minute'

export interface BacktestFillDefaults {
  entry_fill?: unknown
  exit_fill?: unknown
  matching?: unknown
}

export interface StrategyFills {
  entry: EntryFill
  exit: ExitFill
}

/** 候选方案可提供的部分口径: 缺失的一侧由策略默认补齐, 不能留上一策略值。 */
export interface CandidateFills {
  entry?: EntryFill
  exit?: ExitFill
}

export const DEFAULT_ENTRY_FILL: EntryFill = 'open_t+1'
export const DEFAULT_EXIT_FILL: ExitFill = 'open_t+1'

export function isEntryFill(value: unknown): value is EntryFill {
  return value === 'close_t' || value === 'open_t+1'
}

export function isExitFill(value: unknown): value is ExitFill {
  return isEntryFill(value) || value === 'signal_next_minute'
}

/** 策略默认成交口径: 两侧各自从该策略声明解析, 缺省次日开盘。 */
export function resolveStrategyFills(defaults?: BacktestFillDefaults | null): StrategyFills {
  return {
    entry: isEntryFill(defaults?.entry_fill)
      ? defaults.entry_fill
      : isEntryFill(defaults?.matching)
        ? defaults.matching
        : DEFAULT_ENTRY_FILL,
    exit: isExitFill(defaults?.exit_fill)
      ? defaults.exit_fill
      : isEntryFill(defaults?.matching)
        ? defaults.matching
        : DEFAULT_EXIT_FILL,
  }
}

/**
 * 候选方案自带口径: 显式 fill 优先于旧候选 matching。
 * 两侧都没有时返回 null (调用方回落到策略默认/系统默认)。
 */
export function resolveCandidateFills(config?: Record<string, unknown> | null): CandidateFills | null {
  if (!config) return null
  const entry = isEntryFill(config.entry_fill)
    ? config.entry_fill
    : isEntryFill(config.matching)
      ? config.matching
      : undefined
  const exit = isExitFill(config.exit_fill)
    ? config.exit_fill
    : isEntryFill(config.matching)
      ? config.matching
      : undefined
  if (entry === undefined && exit === undefined) return null
  return { entry, exit }
}
