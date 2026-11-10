import type { FrontendExtension } from '@/extensions/types'
import { DynamicGroupButton } from './DynamicGroupButton'

const extension: FrontendExtension = {
  id: 'official.dynamic-watchlist',
  apiVersion: 1,
  slots: [{
    name: 'watchlist.toolbar',
    id: 'dynamic-group-manager',
    order: 100,
    component: DynamicGroupButton,
  }],
}

export default extension
