import { lazy } from 'react'
import type { FrontendExtension } from '@/extensions/types'
import { IconPlan } from '@/components/BrandIcons'
import { AddToPlanButton } from './AddToPlanButton'
import { AddToPlanMenuItem } from './AddToPlanMenuItem'

export const TradePlanPage = lazy(() => import('./Page').then(m => ({ default: m.TradePlanPage })))

const extension: FrontendExtension = {
  id: 'official.trade-plan',
  apiVersion: 1,
  routes: [
    { id: 'trade-plan', path: '/trade-plan', component: TradePlanPage },
  ],
  navigation: [
    { id: 'trade-plan', routeId: 'trade-plan', label: '交易计划', icon: IconPlan },
  ],
  slots: [{
    name: 'watchlist.toolbar',
    id: 'trade-plan-add',
    order: 90,
    component: AddToPlanButton,
  }, {
    name: 'watchlist.row-menu',
    id: 'trade-plan-add-row',
    order: 90,
    component: AddToPlanMenuItem,
  }],
}

export default extension
