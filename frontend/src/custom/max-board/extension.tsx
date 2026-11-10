import { lazy } from 'react'
import type { FrontendExtension } from '@/extensions/types'
import { IconLadder } from '@/components/BrandIcons'

const MaxBoardPage = lazy(() => import('./Page').then(m => ({ default: m.MaxBoardPage })))

const extension: FrontendExtension = {
  id: 'official.max-board',
  apiVersion: 1,
  routes: [
    { id: 'max-board', path: '/max-board', component: MaxBoardPage },
  ],
  navigation: [
    { id: 'max-board', routeId: 'max-board', label: '最高板', icon: IconLadder },
  ],
}

export default extension
