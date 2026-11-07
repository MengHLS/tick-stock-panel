### 7.7 `status` 闸门（v0.3 新增；直接约束批二 E1/E2 的验收设计）

#### 7.7.1 事实（逐条实测）

| # | 事实 | 依据 |
| --- | --- | --- |
| 1 | 运行时对象 `FactorSpec` **没有** `status` 字段 | `app/factors/registry.py:33-56` 的字段清单（21 个）无 `status`；`hasattr(spec,"status") == False`，`getattr(spec,"status",None) is None` |
| 2 | `status` 只活在 JSON 定义里，并在 `to_spec` 时被**投影为 `stability`**（`active → stable`，其余 `experimental`）后丢弃 | `store.py:66-68`（取值校验）、`:94`、`:110`、`:165` |
| 3 | 没有任何计算/加载路径读 `status` 做准入 | `grep -rn "status" backend/app/factors/registry.py` 零命中 |
| 4 | `POST /custom/{id}/status` 确实存在，但只改 JSON + `unregister → register`，不构成闸门 | `api/factors.py:510-531` |
| 5 | 结论：§7.5-5「未过 V3 不得标 active」**当前只是登记纪律，运行时没有闸门**；`draft` 因子可被策略、回测、执行器直接引用 | 上 1–4 |

#### 7.7.2 决策：两层落地，闸门放在「消费入口」，不放在求值层

**数据层（P2 扩字段，与 §7.2 的 `unit`/`scale_free` 同批）**：`FactorSpec` 末尾新增 `status: Literal["draft","active","watch","retired"] = "draft"`；`store.to_spec` 的三个分支（dsl / python / composite）填入同一个值。默认 `draft` 是**安全方向**（漏填 → 拒绝，而不是放行）；新字段带默认值，现有构造调用不受影响。

**闸门层（单一实现，禁止各入口各写一遍）**：新增 `app/factors/gate.py#assert_factors_usable(factor_ids, mode, *, allow_non_active=False, allow_retired=False) -> GateReport`。
- `GateReport` 字段（固定，便于验收断言）：`ok: bool`、`blocked: tuple[(factor_id, status, code)]`、`non_active: tuple[str, ...]`、`unknown: tuple[str, ...]`、`mode: str`、`historical_only: bool`。
- 判定矩阵（机械可判）：

| status | `mode="production"` | `mode="research"` |
| --- | --- | --- |
| `active` | 允许 | 允许 |
| `watch` | **拒绝** `FS01` | 允许，记入 `non_active` |
| `draft` | **拒绝** `FS01` | 仅当 `allow_non_active=true` 允许，记入 `non_active`；否则 `FS01` |
| `retired` | **拒绝** `FS01` | 仅当 `allow_retired=true` 允许，报告标 `historical_only=true`；否则 `FS01` |
| 未登记（registry 与 custom store 都没有） | **拒绝** `FS02` | **拒绝** `FS02` |
| `kind` ∈ {`base`, `virtual`} | 不适用（两者都无 `status`；准入由台账 G1–G3 与代码审核承担，见 §7.8.3） | 同左 |

**为什么放在入口而不是求值层**：① 求值层（`scoring.py#materialize_scoring_columns`、`matrix.py#_compute_matrix_feature`）是逐列热路径，闸门放那里等于每帧重判；② 同一因子被不同调用方引用时必须结论一致，判定只能发生在「谁在用」这一层；③ 回测允许 `draft`（研究要试）而生产不允许（钱），这个差异只有入口知道。

#### 7.7.3 调用点（逐个接，不留实现者猜）

| 入口 | 位置 | mode | 说明 |
| --- | --- | --- | --- |
| 因子校验接口 | `app/api/factors.py:78` `POST /validate` | research | `allow_non_active=true`，响应附 `non_active` |
| 策略保存/更新 | `app/api/strategy.py:473` `POST /config`、`:493` `PATCH /config` | research | 引用 `draft` 且未显式允许 → 400 `FS01`；允许时把 `non_active` 写进策略元数据 |
| 回测入口 | `app/api/backtest.py`（`FactorConfig` 解析后、`engine.run_backtest` 前） | research | 回测报告必须带 `non_active_factors`；同一次回测内不得混用两种判定 |
| X1 组合级执行 | `app/strategy/rebalance.py#build_target_portfolio`（§6.3.1） | production | 只认 `active`；拒绝即 fail-closed，整计划不生成 |
| 生产自动执行 | `app/strategy/paper_auto.py#on_rule_events` 装载规则时 | production | 同上 |
| 因子求值 | `scoring.py#materialize_scoring_columns`、`matrix.py#_compute_matrix_feature` | — | **不 gate**（见 7.7.2 理由） |

#### 7.7.4 与 E1/E2 的关系（批二验收按此设计）

1. E1（`xs_mean`）与 E2（三个 `xs_rank_*`）是**算子**，不是可登记因子，`status` 闸门看不见它们 → 它们的版本纪律由 `rank_version` / `breadth_version` 承担，**不参与 status 判定**。
2. 若 E2 的三个 id 以「别名因子」形式登记（供诊断与台账引用），同样受闸门约束：`xs_rank_pct` 的 status 必须是 `watch` 或 `retired`，**不得 `active`**（它只用于历史复现与差异证明）；`xs_rank_market` 同理。`xs_rank_pool` 在 XS-A1–A8 全过并经独立审核后方可 `active`。
3. 批二验收因此分两段：**数值段**验算子/因子的口径判据（§3.4 / §4.6），**闸门段**验「引用一个 `draft` 别名因子时生产入口拒绝、研究入口按 `allow_non_active` 放行（并回报）」。两段都过才算可用。

#### 7.7.5 错误码（新增命名空间，不与 DSL `E0xx`、T2 `E2xx` 冲突）

| 码 | 含义 | 触发 | 处置 |
| --- | --- | --- | --- |
| `FS01` | 因子状态不允许在该模式使用 | 7.7.2 矩阵 | 400；`detail` 含 `factor_id` / `status` / `mode` |
| `FS02` | 因子未登记 | 既不在 `registry` 也不在 `custom_factors` | 400，fail-closed（G8） |

#### 7.7.6 版本与缓存

- `status` 变更**不改数值**。当前内容签名把 `status` 计入（`store.py:183-198` 节注释；`_NON_CONTENT_FIELDS` 定义在 `:199`，只排除 `version/created_at/updated_at`）→ 改状态会抬版本 → 该因子 `materialize_cache` 键变化 → **单因子重算一次**。这是**可接受的代价**（数值逐位不变，只花一次算力），本条按现状登记，不要求改实现。
- 硬要求：`status` 变更后重算结果必须与变更前**逐位相同**（`max_abs_diff == 0`）；若不同，说明 status 实际影响了计算，属缺陷。
- 若后续把 `status` 移出内容签名（省掉这次重算），**必须同时**落状态审计（`status_history`：谁 / 何时 / 依据哪份报告 digest），否则治理链断裂。

#### 7.7.7 验收判据（与 §7.6 同表编号）

| # | 判据 | 度量 |
| --- | --- | --- |
| F-A7 | 运行时可见 | `get_factor("<uf_*>").status` 返回四个合法值之一（字段已落 `FactorSpec`）；`getattr(..., "status", None)` 不再是 `None` |
| F-A8 | 闸门可判 | 同一因子依次置 `draft/watch/active/retired`，`assert_factors_usable` 在 `production`/`research` 两模式下的 8 个组合逐个等于 7.7.2 矩阵；`FS01`/`FS02` 逐字匹配 |
| F-A9 | 不可绕过 | `production` 模式引用 `draft` 因子：X1 计划不生成、`paper_auto` 规则装载失败；断言「订单数 == 0」且报告含 `FS01` |

---
