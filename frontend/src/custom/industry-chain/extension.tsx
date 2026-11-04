import { lazy } from 'react'
import { Network } from 'lucide-react'
import type { FrontendExtension } from '@/extensions/types'

export const IndustryChainPage = lazy(() =>
  import('./Page').then(module => ({ default: module.IndustryChainPage })),
)

const extension: FrontendExtension = {
  id: 'official.industry-chain',
  apiVersion: 1,
  routes: [
    { id: 'industry-chain', path: '/industry-chain', component: IndustryChainPage },
  ],
  navigation: [
    {
      id: 'industry-chain',
      routeId: 'industry-chain',
      label: '产业链分析',
      icon: Network,
      order: 135,
    },
  ],
}

export default extension
