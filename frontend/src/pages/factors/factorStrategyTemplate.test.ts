// @vitest-environment node
import { describe, expect, it } from 'vitest'

import { renderFactorStrategyCode } from './factorStrategyTemplate'

describe('renderFactorStrategyCode', () => {
  it('uses the safety-whitelisted factor research module', () => {
    const code = renderFactorStrategyCode(
      'custom_factor_first_board_chain_stage',
      '首板事件链阶段排名策略',
      'first_board_chain_stage',
      'high',
      'generated',
    )

    expect(code).toContain(
      'from app.strategy.research.factor_rank_research import FactorRankResearchMatrixStrategy',
    )
    expect(code).not.toContain('app.strategy.builtin.factor_rank_research')
  })
})
