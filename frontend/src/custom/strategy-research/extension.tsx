import { lazy } from 'react'
import { Microscope } from 'lucide-react'
import type { FrontendExtension } from '@/extensions/types'

const Page = lazy(() => import('./Page').then(m => ({ default: m.StrategyResearchPage })))

const extension: FrontendExtension = {
  id: 'official.strategy-research',
  apiVersion: 1,
  routes: [
    { id: 'strategy-research', path: '/strategy-research', component: Page },
  ],
  navigation: [
    {
      id: 'strategy-research',
      routeId: 'strategy-research',
      label: '策略研究',
      icon: Microscope,
      order: 520,
    },
  ],
}

export default extension
