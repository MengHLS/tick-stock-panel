import { useState } from 'react'

interface Group {
  id: string; count: number; coverage: number; strong_rate: number | null
  early_fail_rate: number | null; strong_lift: number | null
  [key: string]: string | number | null
}
interface CalibrationBin {
  lower: number; upper: number; count: number
  predicted: number | null; observed: number | null
}
export interface NegativeResearchReport {
  status: string; groups: Group[]
  paired_count?: number; unscored_count?: number; evaluation_cutoff?: string
  main_retention?: number | null; main_strong_retention?: number | null
  main_early_fail_removed?: number | null; lockbox_excluded_count?: number
  model?: {
    status: string; decision_threshold?: number | null
    fit_count?: number; calibration_count?: number; calibration_start?: string
    validation_auc?: number | null; validation_brier?: number | null
    validation_baseline_brier?: number | null
    features?: { factor_id: string; snapshot: string; coefficient: number }[]
    validation_calibration?: CalibrationBin[]
  }
  combined_vs_main?: {
    early_fail_difference_95?: number[] | null; strong_difference_95?: number[] | null
  }
  bootstrap?: { block_dates: number; samples: number }
}

const names: Record<string, string> = {
  baseline: '全样本基准（共同可评分）', main_only: '仅主信号',
  negative_only: '仅负面否决', combined: '主信号 + 负面否决',
}
const unavailable: Record<string, string> = {
  insufficient_sample: '训练样本不足，无法建立独立早损模型。',
  no_supported_factor: '拟合段未找到满足支持度的负面因子，未生成否决信号。',
  insufficient_calibration: '校准段可评分样本不足，未固定风险阈值。',
  fit_failed: '模型未收敛，未生成风险预测。',
  main_feature_unavailable: '缺少主信号所需的 T-1 布林带宽，请选择包含 T-1 的特征时点。',
  no_scorable_validation: '验证期没有共同可评分事件。',
  no_data: '所选区间暂无可评估事件。',
}
const ratio = (value: number | null | undefined) =>
  value == null ? '—' : `${(value * 100).toFixed(2)}%`
const decimal = (value: number | null | undefined) => value == null ? '—' : value.toFixed(3)
const interval = (value?: number[] | null) =>
  value ? `${(value[0] * 100).toFixed(2)} ～ ${(value[1] * 100).toFixed(2)} 个百分点` : '—'
const cell = 'whitespace-nowrap px-3 py-2 text-right font-mono tabular-nums'

export function NegativeResearch({
  report, labels,
}: { report?: NegativeResearchReport; labels: Record<string, string> }) {
  const [horizon, setHorizon] = useState(5)
  const model = report?.model
  return <section className="overflow-hidden rounded-card border border-border bg-surface">
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border p-3">
      <h2 className="text-sm font-medium">早损否决研究</h2>
      {report?.status === 'ok' && <label className="text-xs text-muted">观察窗口{' '}
        <select aria-label="风险对比收益窗口" className="h-8 rounded-input border border-border bg-base px-2"
          value={horizon} onChange={e => setHorizon(Number(e.target.value))}>
          {[5, 10, 20].map(value => <option key={value} value={value}>{value} 日</option>)}
        </select>
      </label>}
    </div>
    <p className="px-3 py-2 text-xs leading-6 text-secondary">
      早损：T+1 开盘后前 5 个交易日最低价触及 -8%。主信号固定为 T-1 布林带宽 ≥0.419863。
      负面模型在训练期内拟合，使用较晚的校准段固定风险阈值。
      高风险约 20% 的目标比例仅针对校准段，验证期实际剔除比例可能不同。
    </p>
    {!report ? <p className="p-3 text-xs text-muted">此历史记录未包含早损模型；重新计算或打开含早损研究的新记录后查看。</p>
      : report.status !== 'ok' ? <p role="status" className="p-3 text-xs text-amber-500">
        {unavailable[report.status] ?? '早损研究暂不可用。'}
      </p> : <>
        <div className="grid gap-2 px-3 pb-3 sm:grid-cols-3">
          {[
            ['主信号样本保留', ratio(report.main_retention)],
            ['上涨机会保留', ratio(report.main_strong_retention)],
            ['主信号早损事件剔除', ratio(report.main_early_fail_removed)],
          ].map(([label, value]) => <div key={label} className="rounded-input border border-border bg-base/50 p-3">
            <div className="text-[11px] text-muted">{label}</div>
            <div className="mt-1 font-mono text-lg">{value}</div>
          </div>)}
        </div>
        <p className="border-t border-border px-3 py-2 text-[11px] leading-5 text-muted">
          共同可评分 {report.paired_count?.toLocaleString()} 条 · 缺失输入或标签 {report.unscored_count ?? 0} 条。
          上涨机会保留指原主信号中达到 ≥20% 的事件仍被保留的比例，需同时看早损减少和机会损失。
          {report.evaluation_cutoff ? ` 事件评估截至 ${report.evaluation_cutoff}。` : ''}
          {report.lockbox_excluded_count ? ` 此历史记录按当时设置排除了 ${report.lockbox_excluded_count} 条后续事件；重新计算使用当前所选日期。` : ''}
        </p>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[940px] text-left text-xs">
            <thead className="bg-elevated text-muted"><tr>
              <th className="sticky left-0 z-10 min-w-[180px] whitespace-nowrap bg-elevated px-3 py-2 font-normal">验证分组</th>
              {['事件数', '覆盖率', '≥20% 比例', '5 日早损率', `${horizon} 日最高`, `${horizon} 日期末`, `${horizon} 日不利`].map(title =>
                <th key={title} className="whitespace-nowrap px-3 py-2 text-right font-normal">{title}</th>)}
            </tr></thead>
            <tbody>{report.groups.map(group => <tr key={group.id} className={`border-t border-border ${group.id === 'combined' ? 'text-accent' : ''}`}>
              <td className="sticky left-0 min-w-[180px] whitespace-nowrap bg-surface px-3 py-2">{names[group.id] ?? group.id}</td>
              <td className={cell}>{group.count.toLocaleString()}</td>
              <td className={cell}>{ratio(group.coverage)}</td>
              <td className={cell}>{ratio(group.strong_rate)}</td>
              <td className={cell}>{ratio(group.early_fail_rate)}</td>
              {['mfe', 'close_return', 'mae'].map(metric => <td key={metric} className={cell}>
                {ratio(group[`mean_${metric}_${horizon}d`] as number | null)}
              </td>)}
            </tr>)}</tbody>
          </table>
        </div>
        <div className="border-t border-border p-3 text-[11px] leading-6 text-secondary">
          <p>组合相对主信号的早损率差 95% 区间：{interval(report.combined_vs_main?.early_fail_difference_95)}；
            强首板率差：{interval(report.combined_vs_main?.strong_difference_95)}。</p>
          <p className="text-muted">按事件交易日连续 {report.bootstrap?.block_dates ?? 20} 日分块重采样
            {report.bootstrap?.samples ?? 500} 次；区间含 0 时，当前样本不足以确认改善。已观察历史上的反复研究仍可能过拟合。</p>
        </div>
        <details className="border-t border-border p-3 text-xs">
          <summary className="cursor-pointer text-secondary">负面因子、校准与模型诊断</summary>
          <div className="mt-2 space-y-2 text-[11px] leading-6 text-muted">
            <p>拟合 {model?.fit_count} 条 · 校准 {model?.calibration_count} 条
              （自 {model?.calibration_start}）· 否决阈值 {ratio(model?.decision_threshold)}。</p>
            <p>验证 AUC {decimal(model?.validation_auc)} · Brier {decimal(model?.validation_brier)}
              {' · '}验证常数概率基准 {decimal(model?.validation_baseline_brier)}（Brier 越小越好）。</p>
            {(model?.features ?? []).map(feature => <p key={`${feature.snapshot}-${feature.factor_id}`}>
              {feature.snapshot === 'D_minus_1' ? 'T-1 收盘' : 'T 日收盘'} · {labels[feature.factor_id] ?? feature.factor_id}
              {' · '}标准化系数 {decimal(feature.coefficient)}（正值对应更高预测风险）
            </p>)}
            <div className="overflow-x-auto"><table className="w-full min-w-[420px] text-left">
              <thead><tr>{['预测风险档', '样本', '平均预测', '实际早损'].map(title => <th key={title} className="p-1 font-normal">{title}</th>)}</tr></thead>
              <tbody>{(model?.validation_calibration ?? []).map(bin => <tr key={bin.lower}>
                <td className="p-1">{ratio(bin.lower)} ～ {ratio(bin.upper)}</td>
                <td className="p-1">{bin.count}</td><td className="p-1">{ratio(bin.predicted)}</td>
                <td className="p-1">{ratio(bin.observed)}</td>
              </tr>)}</tbody>
            </table></div>
          </div>
        </details>
      </>}
  </section>
}
