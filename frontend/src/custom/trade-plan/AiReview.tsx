import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { History, Sparkles, Square, Trash2 } from 'lucide-react'
import { MarkdownRenderer } from '@/components/financials/MarkdownRenderer'
import { toast } from '@/components/Toast'
import { cn } from '@/lib/cn'
import { friendlyStreamError } from '@/lib/api'
import { tradePlanApi, tradePlanKeys } from './client'
import type { AiPlanReport, AnalyzeMeta } from './types'

type Phase = 'idle' | 'loading' | 'streaming' | 'done' | 'error'

function fmtPct(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  return `${v > 0 ? '+' : ''}${v.toFixed(2)}%`
}

function fmtTime(iso: string): string {
  return iso ? `${iso.slice(5, 10)} ${iso.slice(11, 16)}` : '—'
}

function MetaChip({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-border bg-elevated/60 px-2 py-0.5 text-[9px] text-muted">
      {label} <span className="font-mono text-foreground">{value}</span>
    </span>
  )
}

export function AiReview({ start, end }: { start?: string; end?: string }) {
  const qc = useQueryClient()
  const [limit, setLimit] = useState(60)
  const [focus, setFocus] = useState('')
  const [phase, setPhase] = useState<Phase>('idle')
  const [content, setContent] = useState('')
  const [error, setError] = useState('')
  const [meta, setMeta] = useState<AnalyzeMeta | null>(null)
  const [saved, setSaved] = useState(false)
  const [viewingId, setViewingId] = useState<string | null>(null)
  const [analyzedRange, setAnalyzedRange] = useState<{ start?: string; end?: string } | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => () => abortRef.current?.abort(), [])

  const reportsQ = useQuery({
    queryKey: tradePlanKeys.reports,
    queryFn: tradePlanApi.reports,
    staleTime: 30_000,
  })

  const saveMut = useMutation({
    mutationFn: () => tradePlanApi.saveReport({
      start: analyzedRange?.start ?? null,
      end: analyzedRange?.end ?? null,
      focus,
      content,
      summary: meta
        ? `${meta.plan_count} 条计划 / ${meta.closed_count} 笔结束 / 胜率 ${
            meta.win_rate == null ? '—' : `${meta.win_rate.toFixed(0)}%`
          }`
        : '',
      stats: meta
        ? {
            total: meta.plan_count,
            closed: meta.closed_count,
            execution_rate: meta.execution_rate,
            win_rate: meta.win_rate,
            avg_pnl_pct: meta.avg_pnl_pct,
            avg_r: meta.avg_r,
            discipline_score: meta.discipline_score,
          }
        : {},
    }),
    onSuccess: () => {
      setSaved(true)
      qc.invalidateQueries({ queryKey: tradePlanKeys.reports })
      toast('已归档', 'success')
    },
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => tradePlanApi.deleteReport(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: tradePlanKeys.reports })
      toast('已删除', 'success')
    },
  })

  const stop = () => {
    abortRef.current?.abort()
    abortRef.current = null
    setPhase(content ? 'done' : 'idle')
  }

  const generate = async () => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setPhase('loading')
    setContent('')
    setError('')
    setMeta(null)
    setSaved(false)
    setViewingId(null)
    setAnalyzedRange({ start, end })
    let buffer = ''
    try {
      for await (const event of tradePlanApi.analyzeStream(
        { start, end, limit, focus },
        controller.signal,
      )) {
        if (controller.signal.aborted) return
        if (event.type === 'meta') {
          setMeta({
            plan_count: event.plan_count ?? 0,
            closed_count: event.closed_count ?? 0,
            execution_rate: event.execution_rate ?? null,
            win_rate: event.win_rate ?? null,
            avg_pnl_pct: event.avg_pnl_pct ?? null,
            avg_r: event.avg_r ?? null,
            discipline_score: event.discipline_score ?? null,
          })
          setPhase('streaming')
        } else if (event.type === 'delta' && event.content) {
          buffer += event.content
          setContent(buffer)
          setPhase('streaming')
        } else if (event.type === 'error') {
          setError(event.message || 'AI 复盘失败')
          setPhase('error')
          return
        } else if (event.type === 'done') {
          setPhase('done')
        }
      }
      if (buffer) setPhase('done')
    } catch (err: any) {
      if (controller.signal.aborted) return
      setError(friendlyStreamError(err?.message) || 'AI 复盘失败')
      setPhase('error')
    } finally {
      if (abortRef.current === controller) abortRef.current = null
    }
  }

  const viewReport = (report: AiPlanReport) => {
    abortRef.current?.abort()
    abortRef.current = null
    setViewingId(report.id)
    setAnalyzedRange({ start: report.start ?? undefined, end: report.end ?? undefined })
    setContent(report.content)
    setFocus(report.focus)
    setSaved(true)
    setError('')
    setPhase('done')
    const stats = report.stats || {}
    setMeta({
      plan_count: Number(stats.total ?? 0),
      closed_count: Number(stats.closed ?? 0),
      execution_rate: stats.execution_rate ?? null,
      win_rate: stats.win_rate ?? null,
      avg_pnl_pct: stats.avg_pnl_pct ?? null,
      avg_r: stats.avg_r ?? null,
      discipline_score: stats.discipline_score ?? null,
    })
  }

  const busy = phase === 'loading' || phase === 'streaming'
  const reports = reportsQ.data?.reports ?? []

  return (
    <div className="grid min-h-0 gap-4 xl:grid-cols-[minmax(0,1fr)_300px]">
      <div className="flex min-h-[520px] min-w-0 flex-col rounded-card border border-border bg-surface">
        <div className="flex flex-wrap items-center gap-2 border-b border-border px-3 py-2">
          <select
            value={limit}
            onChange={event => setLimit(Number(event.target.value))}
            disabled={busy}
            className="h-7 rounded-btn border border-border bg-base px-2 text-[10px] text-secondary outline-none focus:border-accent/60"
          >
            <option value={20}>最近 20 条</option>
            <option value={50}>最近 50 条</option>
            <option value={60}>最近 60 条</option>
            <option value={100}>最近 100 条</option>
          </select>
          <input
            value={focus}
            onChange={event => setFocus(event.target.value)}
            placeholder="这次重点看什么（可选）"
            className="h-7 min-w-0 flex-1 rounded-btn border border-border bg-base px-2.5 text-[11px] text-foreground outline-none focus:border-accent/60"
          />
          <button
            onClick={busy ? stop : generate}
            className={cn(
              'inline-flex h-7 items-center gap-1.5 rounded-btn px-3 text-[11px] font-medium',
              busy
                ? 'border border-border bg-elevated text-secondary hover:text-foreground'
                : 'bg-accent text-white hover:bg-accent/90',
            )}
          >
            {busy ? <Square className="h-3 w-3" /> : <Sparkles className="h-3.5 w-3.5" />}
            {busy ? '停止' : '生成复盘'}
          </button>
          {phase === 'done' && content && (
            <button
              onClick={() => saveMut.mutate()}
              disabled={saved || saveMut.isPending || viewingId !== null}
              className="h-7 rounded-btn border border-border px-2.5 text-[10px] text-secondary hover:bg-elevated disabled:opacity-45"
            >
              {saved ? '已归档' : '归档'}
            </button>
          )}
        </div>

        {meta && (
          <div className="flex flex-wrap gap-1.5 border-b border-border/60 px-3 py-2">
            <MetaChip
              label="区间"
              value={analyzedRange?.start
                ? `${analyzedRange.start.slice(5)}~${(analyzedRange.end ?? '').slice(5)}`
                : '全部'}
            />
            <MetaChip label="计划" value={String(meta.plan_count)} />
            <MetaChip label="结束" value={String(meta.closed_count)} />
            <MetaChip label="执行率" value={meta.execution_rate == null ? '—' : `${meta.execution_rate.toFixed(0)}%`} />
            <MetaChip label="胜率" value={meta.win_rate == null ? '—' : `${meta.win_rate.toFixed(0)}%`} />
            <MetaChip label="平均" value={fmtPct(meta.avg_pnl_pct)} />
            <MetaChip label="平均R" value={meta.avg_r == null ? '—' : meta.avg_r.toFixed(2)} />
            <MetaChip label="纪律" value={meta.discipline_score == null ? '—' : meta.discipline_score.toFixed(0)} />
          </div>
        )}

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
          {phase === 'idle' && !content && (
            <div className="grid h-full min-h-72 place-items-center text-center">
              <div>
                <Sparkles className="mx-auto h-8 w-8 text-muted" strokeWidth={1.5} />
                <div className="mt-3 text-[12px] text-secondary">用计划与执行记录生成超短复盘</div>
              </div>
            </div>
          )}
          {phase === 'loading' && !content && (
            <div className="flex items-center gap-2 text-[11px] text-muted">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
              正在读取计划并生成…
            </div>
          )}
          {error && (
            <div className="rounded-btn border border-danger/30 bg-danger/5 px-3 py-2 text-[11px] text-danger">
              {error}
            </div>
          )}
          {content && <MarkdownRenderer content={content} />}
        </div>
      </div>

      <div className="rounded-card border border-border bg-surface">
        <div className="flex items-center gap-1.5 border-b border-border px-3 py-2 text-[11px] font-medium text-foreground">
          <History className="h-3.5 w-3.5 text-muted" /> 历史复盘
        </div>
        {reports.length === 0 ? (
          <div className="px-3 py-8 text-center text-[10px] text-muted">暂无归档</div>
        ) : (
          <div className="max-h-[560px] divide-y divide-border/60 overflow-y-auto">
            {reports.map(report => (
              <div
                key={report.id}
                className={cn(
                  'group flex cursor-pointer items-start gap-2 px-3 py-2.5 hover:bg-elevated/40',
                  viewingId === report.id && 'bg-accent/5',
                )}
                onClick={() => viewReport(report)}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[10px] text-secondary">{fmtTime(report.created_at)}</span>
                    {report.stats?.closed != null && (
                      <span className="font-mono text-[9px] text-muted">{report.stats.closed} 笔</span>
                    )}
                  </div>
                  <p className="mt-0.5 line-clamp-2 text-[10px] leading-relaxed text-muted">
                    {report.focus || report.summary || '执行复盘'}
                  </p>
                </div>
                <button
                  onClick={event => {
                    event.stopPropagation()
                    if (window.confirm('删除这条复盘？')) deleteMut.mutate(report.id)
                  }}
                  className="rounded p-1 text-muted opacity-0 transition-opacity hover:text-danger group-hover:opacity-100"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
