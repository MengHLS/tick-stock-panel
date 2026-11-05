import { describe, expect, it } from 'vitest'
import extension from './extension'

describe('theme analyzer extension', () => {
  it('registers the generic theme route and navigation entry', () => {
    expect(extension.id).toBe('local.theme-analyzer')
    expect(extension.apiVersion).toBe(1)
    expect(extension.routes).toEqual([
      expect.objectContaining({
        id: 'theme-analyzer',
        path: '/theme-analyzer',
      }),
    ])
    expect(extension.navigation).toEqual([
      expect.objectContaining({
        id: 'theme-analyzer',
        routeId: 'theme-analyzer',
        label: '主题分析',
      }),
    ])
  })
})

