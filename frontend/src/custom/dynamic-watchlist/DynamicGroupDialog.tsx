import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Check, Plus, Trash2, X } from 'lucide-react'
import { Modal } from '@/components/Modal'
import { api, type DynamicGroupCondition, type DynamicGroupRule, type WatchlistGroup, type WatchlistGroupColor } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import {
  DEFAULT_WATCHLIST_GROUP_COLOR,
  WATCHLIST_GROUP_COLORS,
  resolveWatchlistGroupColor,
} from '@/lib/watchlist-group-colors'

interface Draft {
  id: string | null
  name: string
  color: WatchlistGroupColor
  conditions: DynamicGroupCondition[]
  maxResults: number
}

const EMPTY_CONDITION: DynamicGroupCondition = {
  left: 'consecutive_limit_ups',
  op: '==',
  right: '1',
  leftDays: 0,
  rightDays: 0,
}

const NEW_DRAFT: Draft = {
  id: null,
  name: '',
  color: DEFAULT_WATCHLIST_GROUP_COLOR,
  conditions: [EMPTY_CONDITION],
  maxResults: 200,
}

const PRESETS: { label: string; conditions: DynamicGroupCondition[] }[] = [
  {
    label: '当日首板',
    conditions: [{ left: 'consecutive_limit_ups', op: '==', right: '1', leftDays: 0, rightDays: 0 }],
  },
  {
    label: '昨日首板',
    conditions: [{ left: 'consecutive_limit_ups', op: '==', right: '1', leftDays: 1, rightDays: 0 }],
  },
  {
    label: '5板后断板',
    conditions: [
      { left: 'consecutive_limit_ups', op: '>=', right: '5', leftDays: 1, rightDays: 0 },
      { left: 'consecutive_limit_ups', op: '==', right: '0', leftDays: 0, rightDays: 0 },
    ],
  },
  {
    label: '5板后炸板',
    conditions: [
      { left: 'consecutive_limit_ups', op: '>=', right: '5', leftDays: 1, rightDays: 0 },
      { left: 'raw_high', op: '>=', right: 'field:limit_up_price', leftDays: 0, rightDays: 0 },
      { left: 'raw_close', op: '<', right: 'field:limit_up_price', leftDays: 0, rightDays: 0 },
    ],
  },
]

function ruleToDraft(group: WatchlistGroup): Draft {
  const rule = group.rule
  return {
    id: group.id,
    name: group.name,
    color: group.color,
    conditions: rule?.conditions?.length ? rule.conditions : [EMPTY_CONDITION],
    maxResults: rule?.max_results ?? 200,
  }
}

function buildRule(draft: Draft): DynamicGroupRule {
  return {
    type: 'conditions',
    schema_version: 1,
    logic: 'and',
    conditions: draft.conditions,
    max_results: draft.maxResults,
  }
}

export function DynamicGroupDialog({
  currentGroupId,
  onClose,
  onChanged,
}: {
  currentGroupId: string
  onClose: () => void
  onChanged: () => void
}) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const groupsQ = useQuery({ queryKey: QK.watchlistGroups, queryFn: api.watchlistGroups })
  const optionsQ = useQuery({
    queryKey: QK.customSignalsOptions,
    queryFn: api.customSignalsOptions,
    staleTime: 60_000,
  })
  const dynamicGroups = useMemo(
    () => (groupsQ.data?.groups ?? []).filter(group => group.kind === 'dynamic'),
    [groupsQ.data?.groups],
  )
  const [draft, setDraft] = useState<Draft>(NEW_DRAFT)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const prefilled = useRef(false)

  const options = optionsQ.data
  const stringFields = useMemo(() => new Set(options?.stringFields ?? []), [options?.stringFields])
  const fieldGroups = useMemo(() => {
    const source = options?.groups?.length
      ? options.groups
      : [{ key: 'all', label: '字段', fields: options?.fields ?? [] }]
    const grouped = source
      .map(group => ({
        ...group,
        fields: group.fields.filter(field => !stringFields.has(field.key)),
      }))
      .filter(group => group.fields.length > 0)
    const seen = new Set(grouped.flatMap(group => group.fields.map(field => field.key)))
    const extra = (options?.fields ?? []).filter(
      field => !stringFields.has(field.key) && !seen.has(field.key),
    )
    return extra.length > 0
      ? [...grouped, { key: 'other', label: '其他', fields: extra }]
      : grouped
  }, [options?.fields, options?.groups, stringFields])
  const operators = options?.operators ?? ['>', '>=', '<', '<=', '==', '!=']
  const maxDays = options?.maxDays ?? 60

  useEffect(() => {
    if (!groupsQ.isSuccess || prefilled.current) return
    prefilled.current = true
    const current = dynamicGroups.find(group => group.id === currentGroupId)
    if (current) setDraft(ruleToDraft(current))
  }, [currentGroupId, dynamicGroups, groupsQ.isSuccess])

  const update = (patch: Partial<Draft>) => setDraft(prev => ({ ...prev, ...patch }))
  const updateCondition = (index: number, patch: Partial<DynamicGroupCondition>) => {
    setDraft(prev => ({
      ...prev,
      conditions: prev.conditions.map((condition, i) => i === index ? { ...condition, ...patch } : condition),
    }))
  }

  const save = async () => {
    const name = draft.name.trim()
    if (!name) {
      setError('请输入分组名称')
      return
    }
    if (draft.conditions.length === 0) {
      setError('至少需要 1 个条件')
      return
    }
    setPending(true)
    setError('')
    try {
      const rule = buildRule(draft)
      if (draft.id) {
        await api.watchlistGroupRename(draft.id, name, draft.color, rule)
        await qc.invalidateQueries({ queryKey: QK.watchlistGroupResolved(draft.id) })
      } else {
        const created = await api.watchlistGroupCreate(name, draft.color, {
          kind: 'dynamic',
          rule,
        })
        setDraft(ruleToDraft(created.group))
        navigate(`/watchlist?group=${encodeURIComponent(created.group.id)}`)
      }
      await qc.invalidateQueries({ queryKey: QK.watchlistGroups })
      onChanged()
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败')
    } finally {
      setPending(false)
    }
  }

  const remove = async (groupId: string) => {
    setPending(true)
    setError('')
    try {
      await api.watchlistGroupDelete(groupId)
      await qc.invalidateQueries({ queryKey: QK.watchlistGroups })
      if (draft.id === groupId) setDraft(NEW_DRAFT)
      if (currentGroupId === groupId) navigate('/watchlist')
      onChanged()
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除失败')
    } finally {
      setPending(false)
    }
  }

  return (
    <Modal
      onClose={onClose}
      labelledBy="dynamic-group-title"
      panelClassName="w-[94vw] max-w-3xl bg-surface border border-border rounded-card shadow-xl"
    >
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <h2 id="dynamic-group-title" className="text-sm font-semibold text-foreground">动态分组</h2>
        <button type="button" onClick={onClose} className="h-8 w-8 inline-flex items-center justify-center text-muted hover:text-foreground" aria-label="关闭">
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="grid max-h-[72vh] grid-cols-1 md:grid-cols-[220px_1fr]">
        <div className="border-b border-border md:border-b-0 md:border-r">
          <div className="p-2">
            <button
              type="button"
              onClick={() => setDraft({ ...NEW_DRAFT, conditions: [{ ...EMPTY_CONDITION }] })}
              className="inline-flex h-8 w-full items-center justify-center gap-1.5 rounded-btn bg-elevated text-xs text-secondary hover:text-foreground"
            >
              <Plus className="h-3.5 w-3.5" />
              新建动态分组
            </button>
          </div>
          <div className="max-h-[240px] overflow-y-auto px-2 pb-2 md:max-h-[56vh]">
            {dynamicGroups.length === 0 && (
              <p className="px-2 py-6 text-center text-[11px] text-muted">暂无动态分组</p>
            )}
            {dynamicGroups.map(group => {
              const color = resolveWatchlistGroupColor(group.color)
              const active = draft.id === group.id
              return (
                <div
                  key={group.id}
                  className={`mb-1 flex items-center gap-1 rounded-btn px-2 py-1.5 ${active ? 'bg-accent/10' : 'hover:bg-elevated/70'}`}
                >
                  <button
                    type="button"
                    onClick={() => setDraft(ruleToDraft(group))}
                    className="flex min-w-0 flex-1 items-center gap-1.5 text-left"
                  >
                    <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${color.dot}`} />
                    <span className="truncate text-xs text-secondary">{group.name}</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => void remove(group.id)}
                    disabled={pending}
                    className="p-1 text-muted hover:text-danger disabled:opacity-50"
                    aria-label={`删除${group.name}`}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              )
            })}
          </div>
        </div>

        <div className="min-h-0 overflow-y-auto p-4">
          <div className="flex flex-wrap items-center gap-2">
            <input
              value={draft.name}
              maxLength={24}
              onChange={event => update({ name: event.target.value })}
              placeholder="分组名称"
              className="h-8 min-w-[180px] flex-1 rounded-btn border border-border bg-elevated px-3 text-xs text-foreground outline-none focus:border-accent/50"
            />
            <div className="flex items-center gap-1">
              {WATCHLIST_GROUP_COLORS.map(option => (
                <button
                  key={option.id}
                  type="button"
                  onClick={() => update({ color: option.id })}
                  title={option.label}
                  aria-label={option.label}
                  className={`h-5 w-5 rounded-full border ${option.border} ${option.background} ${draft.color === option.id ? `ring-2 ${option.ring}` : ''}`}
                >
                  <span className={`mx-auto block h-2.5 w-2.5 rounded-full ${option.dot}`} />
                </button>
              ))}
            </div>
          </div>

          <div className="mt-3 flex flex-wrap gap-1">
            {PRESETS.map(preset => (
              <button
                key={preset.label}
                type="button"
                onClick={() => update({ conditions: preset.conditions.map(condition => ({ ...condition })) })}
                className="rounded-btn border border-border px-2 py-1 text-[11px] text-muted hover:border-accent/40 hover:text-foreground"
              >
                {preset.label}
              </button>
            ))}
          </div>

          <div className="mt-4 space-y-2">
            {draft.conditions.map((condition, index) => (
              <div key={index} className="grid grid-cols-[1.4fr_64px_1.2fr_48px_48px_28px] items-center gap-1.5">
                <select
                  value={condition.left}
                  onChange={event => updateCondition(index, { left: event.target.value })}
                  className="h-8 min-w-0 rounded-btn border border-border bg-elevated px-2 text-xs text-foreground outline-none"
                >
                  {fieldGroups.map(group => (
                    <optgroup key={group.key} label={group.label}>
                      {group.fields.map(field => (
                        <option key={field.key} value={field.key}>{field.label}</option>
                      ))}
                    </optgroup>
                  ))}
                </select>
                <select
                  value={condition.op}
                  onChange={event => updateCondition(index, { op: event.target.value })}
                  className="h-8 rounded-btn border border-border bg-elevated px-1 text-xs text-foreground outline-none"
                >
                  {operators.map(op => <option key={op} value={op}>{op}</option>)}
                </select>
                <input
                  value={String(condition.right)}
                  onChange={event => updateCondition(index, { right: event.target.value })}
                  placeholder="数字或 field:字段"
                  className="h-8 min-w-0 rounded-btn border border-border bg-elevated px-2 text-xs text-foreground outline-none focus:border-accent/50"
                />
                <input
                  type="number"
                  min={0}
                  max={maxDays}
                  value={condition.leftDays ?? 0}
                  onChange={event => updateCondition(index, { leftDays: Math.max(0, Math.min(maxDays, Number(event.target.value) || 0)) })}
                  title="左字段前 N 个交易日"
                  className="h-8 rounded-btn border border-border bg-elevated px-1 text-center text-xs text-foreground outline-none"
                />
                <input
                  type="number"
                  min={0}
                  max={maxDays}
                  value={condition.rightDays ?? 0}
                  onChange={event => updateCondition(index, { rightDays: Math.max(0, Math.min(maxDays, Number(event.target.value) || 0)) })}
                  title="右字段前 N 个交易日"
                  className="h-8 rounded-btn border border-border bg-elevated px-1 text-center text-xs text-foreground outline-none"
                />
                <button
                  type="button"
                  onClick={() => update({ conditions: draft.conditions.filter((_, i) => i !== index) })}
                  className="p-1 text-muted hover:text-danger"
                  aria-label="删除条件"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>

          <button
            type="button"
            onClick={() => update({ conditions: [...draft.conditions, { ...EMPTY_CONDITION }] })}
            className="mt-2 inline-flex items-center gap-1 rounded-btn px-2 py-1 text-[11px] text-muted hover:bg-elevated hover:text-foreground"
          >
            <Plus className="h-3 w-3" />
            添加条件
          </button>

          {error && <p className="mt-2 text-xs text-danger">{error}</p>}

          <div className="mt-4 flex items-center justify-end gap-2 border-t border-border pt-3">
            <button
              type="button"
              onClick={onClose}
              className="rounded-btn bg-elevated px-3 py-1.5 text-xs text-secondary hover:bg-elevated/80"
            >
              取消
            </button>
            <button
              type="button"
              onClick={() => void save()}
              disabled={pending}
              className="inline-flex items-center gap-1.5 rounded-btn bg-accent px-3 py-1.5 text-xs text-white disabled:opacity-50"
            >
              <Check className="h-3.5 w-3.5" />
              {draft.id ? '保存' : '创建'}
            </button>
          </div>
        </div>
      </div>
    </Modal>
  )
}
