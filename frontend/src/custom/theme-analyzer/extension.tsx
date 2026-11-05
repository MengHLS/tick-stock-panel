import { lazy } from 'react'
import { Tags } from 'lucide-react'
import type { FrontendExtension } from '@/extensions/types'

const ThemeAnalyzerPage = lazy(() =>
  import('./Page').then(module => ({ default: module.ThemeAnalyzerPage })),
)

const extension: FrontendExtension = {
  id: 'local.theme-analyzer',
  apiVersion: 1,
  routes: [
    { id: 'theme-analyzer', path: '/theme-analyzer', component: ThemeAnalyzerPage },
  ],
  navigation: [
    {
      id: 'theme-analyzer',
      routeId: 'theme-analyzer',
      label: '主题分析',
      icon: Tags,
      order: 180,
    },
  ],
}

export default extension

