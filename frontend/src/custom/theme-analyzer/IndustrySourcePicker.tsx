import { useQuery } from '@tanstack/react-query'
import { api, type ThemeIndustrySource } from '@/lib/api'
import { QK } from '@/lib/queryKeys'

export function IndustrySourcePicker({
  open,
  value,
  onChange,
}: {
  open: boolean
  value: ThemeIndustrySource | null
  onChange: (value: ThemeIndustrySource | null) => void
}) {
  const graph = useQuery({
    queryKey: QK.industryChainGraph,
    queryFn: api.industryChainGraph,
    enabled: open,
    staleTime: 0,
  })
  const chains = graph.data?.chains ?? []
  const nodes = (graph.data?.nodes ?? []).filter(node => node.chain_id === value?.chain_id)
  return (
    <div className="space-y-2 rounded-xl border border-border bg-base/40 p-3">
      <label className="block text-xs font-medium text-secondary" htmlFor="theme-industry-source">股票池来源</label>
      <select
        id="theme-industry-source"
        value={value?.chain_id ?? ''}
        onChange={event => onChange(event.target.value ? { chain_id: event.target.value, node_ids: [] } : null)}
        className="h-9 w-full rounded-btn border border-border bg-surface px-2 text-sm text-foreground"
      >
        <option value="">自建股票池（手动添加）</option>
        {value && !chains.some(chain => chain.id === value.chain_id) && (
          <option value={value.chain_id}>原关联：{value.chain_id}（请检查来源）</option>
        )}
        {chains.map(chain => <option key={chain.id} value={chain.id}>{chain.name}</option>)}
      </select>
      {graph.isLoading && <p className="text-xs text-muted">正在加载产业链…</p>}
      {graph.isError && (
        <div className="text-xs text-danger">
          产业链加载失败
          <button type="button" onClick={() => void graph.refetch()} className="ml-2 underline">重试</button>
        </div>
      )}
      {value && (
        <>
          <p className="text-[11px] text-muted">不勾选环节时关联整条产业链；勾选后包含对应子环节，股票自动去重。</p>
          <div className="max-h-44 space-y-1 overflow-y-auto">
            {nodes.map(node => (
              <label key={node.id} className="flex items-center gap-2 py-1 text-xs text-secondary">
                <input
                  type="checkbox"
                  checked={value.node_ids.includes(node.id)}
                  onChange={event => onChange({
                    ...value,
                    node_ids: event.target.checked
                      ? [...value.node_ids, node.id]
                      : value.node_ids.filter(id => id !== node.id),
                  })}
                />
                {node.parent_id ? '↳ ' : ''}{node.name}
              </label>
            ))}
          </div>
        </>
      )}
      <p className="text-[11px] leading-5 text-muted">
        刷新时同步产业链股票，手动添加股继续保留；在主题内移除关联股只会将其排除，不修改产业链。解除关联后仅保留手动股。
      </p>
    </div>
  )
}
