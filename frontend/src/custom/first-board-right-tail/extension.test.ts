import { describe, expect, it } from 'vitest'
import extension from './extension'


describe('first-board right-tail extension', () => {
  it('registers one stable route and navigation entry', () => {
    expect(extension.id).toBe('official.first-board-right-tail')
    expect(extension.apiVersion).toBe(1)
    expect(extension.routes).toEqual([
      expect.objectContaining({
        id: 'first-board-right-tail',
        path: '/first-board-right-tail',
      }),
    ])
    expect(extension.navigation).toEqual([
      expect.objectContaining({
        id: 'first-board-right-tail',
        routeId: 'first-board-right-tail',
        label: '首板右尾',
      }),
    ])
  })
})
