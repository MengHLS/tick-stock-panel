import { lazy } from 'react'
import { LineChart } from 'lucide-react'
import type { FrontendExtension } from '@/extensions/types'

export const TradeAnalysisPage = lazy(() =>
  import('./Page').then(module => ({ default: module.TradeAnalysisPage })),
)

const extension: FrontendExtension = {
  id: 'official.trade-analysis',
  apiVersion: 1,
  routes: [
    { id: 'trade-analysis', path: '/trade-analysis', component: TradeAnalysisPage },
  ],
  navigation: [
    { id: 'trade-analysis', routeId: 'trade-analysis', label: '交易分析', icon: LineChart },
  ],
}

export default extension
