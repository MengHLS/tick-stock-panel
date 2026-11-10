import { ApiError } from '@/lib/api'
import type {
  AiPlanReport,
  PlanStatus,
  SetupType,
  TradePlan,
  TradePlanPayload,
  TradeStats,
} from './types'

const BASE = '/api/custom/trade-plan'

export interface PlanFilters {
  start?: string
  end?: string
  setup?: SetupType | ''
  status?: PlanStatus | ''
  q?: string
}

export interface PlanListResult {
  plans: TradePlan[]
  stats: TradeStats
}

export const tradePlanKeys = {
  list: (filters: PlanFilters) => [
    'custom',
    'trade-plan',
    'plans',
    filters.start ?? '',
    filters.end ?? '',
    filters.setup ?? '',
    filters.status ?? '',
    filters.q ?? '',
  ] as const,
  reports: ['custom', 'trade-plan', 'reports'] as const,
}

function queryOf(filters: PlanFilters) {
  const params = new URLSearchParams()
  if (filters.start) params.set('start', filters.start)
  if (filters.end) params.set('end', filters.end)
  if (filters.setup) params.set('setup', filters.setup)
  if (filters.status) params.set('status', filters.status)
  if (filters.q?.trim()) params.set('q', filters.q.trim())
  const text = params.toString()
  return text ? `?${text}` : ''
}

function errorMessage(payload: any, status: number): string {
  const detail = payload?.detail
  if (typeof detail === 'string') return status === 401 ? `未登录 (401)：${detail}` : detail
  if (Array.isArray(detail)) return detail.map((item: any) => item?.msg || String(item)).join('；')
  return status === 401 ? '未登录 (401)' : `交易计划请求失败 (${status})`
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 30_000)
  try {
    const response = await fetch(path, { ...init, signal: controller.signal })
    const payload = await response.json().catch(() => null)
    if (!response.ok) throw new ApiError(errorMessage(payload, response.status), response.status)
    return payload as T
  } catch (error) {
    if (controller.signal.aborted) throw new Error('交易计划请求超时，请稍后重试')
    throw error
  } finally {
    window.clearTimeout(timeout)
  }
}

export const tradePlanApi = {
  list: (filters: PlanFilters) => request<PlanListResult>(`${BASE}/plans${queryOf(filters)}`),

  create: (plan: TradePlanPayload) =>
    request<{ plan: TradePlan }>(`${BASE}/plans`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(plan),
    }),

  update: (planId: string, plan: TradePlanPayload) =>
    request<{ plan: TradePlan }>(`${BASE}/plans/${encodeURIComponent(planId)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(plan),
    }),

  remove: (planId: string) =>
    request<{ ok: boolean }>(`${BASE}/plans/${encodeURIComponent(planId)}`, { method: 'DELETE' }),

  reports: () => request<{ reports: AiPlanReport[] }>(`${BASE}/reports`),

  saveReport: (report: {
    start: string | null
    end: string | null
    focus: string
    content: string
    summary: string
    stats: Record<string, unknown>
  }) =>
    request<{ ok: boolean; report: AiPlanReport }>(`${BASE}/reports`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(report),
    }),

  deleteReport: (reportId: string) =>
    request<{ ok: boolean }>(`${BASE}/reports/${encodeURIComponent(reportId)}`, { method: 'DELETE' }),

  async *analyzeStream(
    params: { start?: string; end?: string; limit: number; focus: string },
    signal?: AbortSignal,
  ): AsyncGenerator<{
    type: 'meta' | 'delta' | 'error' | 'done' | 'ping'
    content?: string
    message?: string
    plan_count?: number
    closed_count?: number
    execution_rate?: number | null
    win_rate?: number | null
    avg_pnl_pct?: number | null
    avg_r?: number | null
    discipline_score?: number | null
  }> {
    const response = await fetch(`${BASE}/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        start: params.start ?? null,
        end: params.end ?? null,
        limit: params.limit,
        focus: params.focus,
      }),
      signal,
    })
    if (!response.ok) {
      const payload = await response.json().catch(() => null)
      throw new ApiError(errorMessage(payload, response.status), response.status)
    }
    if (!response.body) throw new Error('响应无 body')

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''
      for (const line of lines) {
        const text = line.trim()
        if (!text) continue
        try {
          yield JSON.parse(text)
        } catch {
          /* 忽略坏行，保持流可继续 */
        }
      }
    }
    if (buffer.trim()) {
      try {
        yield JSON.parse(buffer.trim())
      } catch {
        /* ignore */
      }
    }
  },
}
