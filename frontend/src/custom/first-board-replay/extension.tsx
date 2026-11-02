import { History } from 'lucide-react'

import type { FrontendExtension } from '@/extensions/types'

import { FirstBoardReplay } from './FirstBoardReplay'

const extension: FrontendExtension = {
  id: 'official.first-board-replay',
  apiVersion: 1,
  routes: [{
    id: 'first-board-replay',
    path: '/research/firstboard',
    component: FirstBoardReplay,
  }],
  navigation: [{
    id: 'first-board-replay',
    routeId: 'first-board-replay',
    label: '首板回放',
    icon: History,
    order: 435,
  }],
}

export default extension
