/** 渲染与挖掘发布同构的单因子排名策略源码。 */
export function renderFactorStrategyCode(
  strategyId: string,
  name: string,
  factorId: string,
  direction: 'high' | 'low',
  description: string,
): string {
  const assetTypes = '["stock"]'
  return `"""${name}: 由因子库一键生成的单因子排名策略。"""
from app.strategy.research.factor_rank_research import FactorRankResearchMatrixStrategy

META = {
    "id": ${JSON.stringify(strategyId)},
    "name": ${JSON.stringify(name)},
    "description": ${JSON.stringify(description)},
    "tags": ["factor", "auto-generated"],
    "asset_types": ${assetTypes},
    "timeframes": ["1d"],
    "params": [
        {"id": "entry_score", "label": "入选评分下限", "type": "float", "default": 70.0, "min": 0.0, "max": 100.0, "step": 5.0},
        {"id": "exit_score", "label": "离场评分上限", "type": "float", "default": 40.0, "min": 0.0, "max": 100.0, "step": 5.0},
        {"id": "top_rank", "label": "每日入选上限", "type": "int", "default": 20, "min": 1, "max": 100, "step": 1},
    ],
    "scoring": {},
    "order_by": "score",
    "descending": True,
    "limit": 100,
}

EXECUTION_BACKEND = "matrix_native"
ENTRY_SIGNALS = ["signal_factor_rank_entry"]
EXIT_SIGNALS = ["signal_factor_rank_exit"]
STOP_LOSS = -0.08
MAX_HOLD_DAYS = 30

SCORING = {${JSON.stringify(factorId)}: 1.0}
DIRECTIONS = {${JSON.stringify(factorId)}: ${JSON.stringify(direction)}}
MATRIX_STRATEGY = FactorRankResearchMatrixStrategy(SCORING, DIRECTIONS)
`
}
