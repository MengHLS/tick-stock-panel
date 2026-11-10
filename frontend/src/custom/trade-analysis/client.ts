export interface TradeLeg {
  date: string
  time: string
  side: 'B' | 'S'
  qty: number
  price: number
  cash_flow: number
  fees: number
}

export interface TradeRow {
  trade_key: string
  symbol: string
  name: string
  open_date: string
  open_time: string
  close_date: string
  close_time: string
  qty: number
  buy_price: number
  sell_price: number
  cost: number
  proceeds: number
  pnl: number
  ret: number | null
  fees: number
  hold_days: number
  hold_td: number | null
  buy_count: number
  sell_count: number
  legs: TradeLeg[]
  analysis: string
  analysis_status: 'full' | 'basic'
  tags: string[]
  mfe: number | null
  mae: number | null
  buy_range_pct: number | null
  exit_range_pct: number | null
  ma5_dev: number | null
  ma20_dev: number | null
  post5: number | null
  post10: number | null
  fee_ratio: number | null
  note: string
  user_tags: string[]
  patterns: string[]
  note_updated_at: string | null
}

export interface SymbolSummary {
  symbol: string
  name: string
  trades: number
  wins: number
  pnl: number
  avg_ret: number | null
  win_rate: number | null
  last_close: string
}

export interface OpenPosition {
  symbol: string
  name: string
  qty: number
  avg_cost: number
  open_date: string
  open_time: string
}

export interface CurvePoint {
  date: string
  pnl: number
  cum_pnl: number
}

export interface TradeOverview {
  fills: number
  trades: number
  open_positions: number
  total_pnl: number
  win_rate: number | null
  profit_factor: number | null
  payoff: number | null
  avg_win: number | null
  avg_loss: number | null
  avg_ret: number | null
  avg_hold_days: number | null
  total_fees: number
  max_drawdown: number
  first_date: string | null
  last_date: string | null
  last_import_at: string | null
  curve: CurvePoint[]
  symbols: SymbolSummary[]
  positions: OpenPosition[]
  trade_rows?: TradeRow[]
}

export interface ImportResult {
  inserted: number
  duplicates: number
  trades: number
  open_positions: number
  analyzed: number
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) {
    let message = `请求失败（${response.status}）`
    try {
      const body = await response.json()
      if (typeof body?.detail === 'string') message = body.detail
    } catch {
      // Keep the status-based message when the body is not JSON.
    }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

export const tradeAnalysisApi = {
  overview: () =>
    request<TradeOverview>('/api/custom/trade-analysis/overview?include_trades=true'),
  saveNote: (tradeKey: string, note: string, tags: string[] = []) =>
    request<{ note: string; tags: string[]; updated_at: string }>(
      `/api/custom/trade-analysis/trades/${encodeURIComponent(tradeKey)}/note`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ note, tags }),
      },
    ),
  importStatement: (file: File) => {
    const body = new FormData()
    body.append('file', file)
    return request<ImportResult>('/api/custom/trade-analysis/import', {
      method: 'POST',
      body,
    })
  },
  reanalyze: () =>
    request<{ trades: number; analyzed: number }>(
      '/api/custom/trade-analysis/reanalyze',
      { method: 'POST' },
    ),
}
