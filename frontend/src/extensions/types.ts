import type { ComponentType, ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import type { PluginDataSourceItem } from '@/lib/api'
import type { BrandIconProps } from '@/components/BrandIcons'
import type {
  StrategyBacktestResult,
  StrategyBacktestTrade,
} from '@/lib/api'

export const FRONTEND_EXTENSION_API_VERSION = 1 as const

export interface FrontendSlotContextMap {
  'settings.data-sources.toolbar': {
    refresh: () => void
    selectSource: (name: string) => void
  }
  'settings.data-sources.detail-actions': {
    plugin: PluginDataSourceItem
    refresh: () => void
  }
  'layout.navigation.extra': {
    collapsed: boolean
    pathname: string
  }
  /** 侧栏头部快捷行 (数据源/AI 配置行下方) — 扩展注册快捷入口行, 行内自带顶部发丝线 */
  'layout.header.quick': Record<string, never>
  /** 设置→系统「界面」区尾部 — 扩展注册系统级开关行 (样式与核心 ToggleRow 同款) */
  'settings.system.section': Record<string, never>
  /** 个股详情对话框底部扩展区 (日K/分时图表下方) */
  'stock-preview.footer': {
    symbol: string
    name: string | null
    view: 'daily' | 'intraday'
  }
  /** 自选页工具栏扩展区 (按钮行末尾) */
  'watchlist.toolbar': {
    /** 当前筛选/排序后视图中的标的 */
    symbols: string[]
    viewMode: 'table' | 'card'
    selectedGroup: string
    /** 刷新自选增强数据 (扩展修改数据后调用) */
    refresh: () => void
  }
  /** 策略回测结果区尾部 — 基于已完成结果快照做只读扩展展示 */
  'backtest.result.extra': {
    apiVersion: 1
    result: StrategyBacktestResult
  }
  /** 交易明细页签尾部 — 可查看当前选中交易并请求打开核心 K 线回放 */
  'backtest.trades.extra': {
    apiVersion: 1
    result: StrategyBacktestResult
    trades: StrategyBacktestTrade[]
    selectedTrade: StrategyBacktestTrade | null
    onSelectTrade: (trade: StrategyBacktestTrade) => void
  }
  /** 已保存结果弹窗尾部 — 只暴露保存 ID 与受控打开回调 */
  'backtest.savedResults.extra': {
    apiVersion: 1
    currentSavedId: string | null
    openSaved: (savedId: string) => void
    busy: boolean
  }
  /** 策略设置区尾部 — 只读策略标识和声明的回测默认值 */
  'backtest.settings.extra': {
    apiVersion: 1
    strategyId: string
    strategyName: string
    defaults: Record<string, unknown>
  }
}

export type FrontendSlotName = keyof FrontendSlotContextMap

export type FrontendSlotRegistration<K extends FrontendSlotName = FrontendSlotName> = K extends FrontendSlotName ? {
  name: K
  id: string
  order?: number
  component: ComponentType<FrontendSlotContextMap[K]>
} : never

export interface FrontendExtensionRoute {
  id: string
  path: `/${string}`
  component: ComponentType
}

export interface FrontendExtensionNavigation {
  id: string
  routeId: string
  label: string
  /** lucide 图标或侧栏品牌图标族 (BrandIcons) — 与 Layout NavIcon 同口径 */
  icon: LucideIcon | ((props: BrandIconProps) => ReactNode)
  order?: number
  badge?: string
}

export interface FrontendExtension {
  id: string
  apiVersion: typeof FRONTEND_EXTENSION_API_VERSION
  routes?: FrontendExtensionRoute[]
  navigation?: FrontendExtensionNavigation[]
  slots?: FrontendSlotRegistration[]
}

export interface FrontendExtensionModule {
  default: FrontendExtension
}

export interface FrontendExtensionLoadError {
  source: string
  extensionId?: string
  error: string
}
