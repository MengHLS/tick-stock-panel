import { lazy } from 'react'
import { ChartCandlestick } from 'lucide-react'
import type { FrontendExtension } from '@/extensions/types'

const Page = lazy(() => import('./Page').then(m => ({ default: m.WyckoffResearchPage })))

const extension: FrontendExtension = {
  id: 'official.wyckoff-research',
  apiVersion: 1,
  routes: [
    { id: 'wyckoff-research', path: '/wyckoff-research', component: Page },
  ],
  navigation: [
    {
      id: 'wyckoff-research',
      routeId: 'wyckoff-research',
      label: '威科夫研究',
      icon: ChartCandlestick,
      order: 530,
    },
  ],
}

export default extension
