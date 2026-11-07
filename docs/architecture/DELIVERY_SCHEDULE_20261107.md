# 交付排期（DELIVERY SCHEDULE）v9 — 2026-11-08 02:0x

责任人：开发经理（系统开发部门）。v1–v8 作废，仅保留修订记录；本文件为唯一排期口径。
契约 footer 的版本自述只作参考，版本线以本文件 §1 为准。

## 0. 本轮（v9）改了什么

1. 版本线换到 **v0.13**（277,296 B / 2,295 行），状态「候选 · 未签发」；v0.12 降历史。
2. **新增 P0-X（本人实测，审核未报）：单条 alias 在真盘上 detail = 8 键（多 violations），与 §7.16.4「单条 FS03 恰 7 键」冲突。**
3. **新增 P0-Y（本人实测 + 独立审核同结论）：契约 §5.6 E4-A4 与真盘相反**（2024-02-29 在轴上且就是月末）→ B4 返工前必须先改契约。
4. B4 维持 **FAIL**，返工未交付（派单 provider_error）。
5. market_breadth 仍未交付（backend/app 0 命中，目录 195/110 不含它）。
6. 全量 tests/ 49 红维持 P0，根因分三类（36 顺序污染 / 7 缺数据环境 / 6 过期或真漂移）。
7. 闸门状态改判：**载体已补、机制已通、未接线**；生产调用点仍 0。

## 1. 版本线（唯一口径）

| 版本 | 文件 | 字节 / 行 | 全文 sha256 | 正文前缀 sha256 | 状态 |
|---|---|---|---|---|---|
| **v0.3** | docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md | 89,833 / 914 | 5eb97724…565903 | head -c 89350 = b082d902…f9bfef | **冻结 · 唯一验收锚** |
| **v0.13** | docs/architecture/FACTOR_ENGINE_CONTRACTS_20261108_v0.13.md | **277,296 / 2,295** | a1374eb5cc526e11… | head -c 275854 = 73901fd0faff9711… | **候选 · 未签发**（可进冻结评审，须先改 P0-Y / P0-X / P2-1） |
| v0.12 | docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.12.md | 269,092 / 2,248 | d7df40ff… | head -c 267257 = d97f657b… | 历史（6 键口径，被 v0.13 取代） |
| v0.11 | docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.11.md | 245,364 / 2,061 | c2eec518… | — | **未签发**（footer 抄 v0.10 数） |
| v0.10 及更早 | — | — | — | — | 历史 |
| 活文件 | docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md | 128,007 / 1,226 | 5bd81a74… | — | 作废（v0.4） |

注意：v0.12 的文件名日期段是 **20261107**，v0.13 是 **20261108**。按 20261108_v0.12 取会 MISSING，不要据此判「v0.12 不存在」。

## 2. 版本锚

- HEAD = **286c1c862631042a2e9a43c57e9762c122e21f7f**，分支 dev，**未 push**；工作区 38 条改动（含 5 个 M 的 backend/**）。
- 三笔提交：79bd04ee（backend 17 文件 +3,625/−40）、484f81f3（docs 76 文件 +56,026）、200238ec（排期 v7 +155/−127）。
- **namespace / FS09 / violations 只在未提交的工作区**：HEAD 版 gate.py 546 行、namespace 命中 1（仅注释）、FS09 命中 0。任何「已入版」表述都不成立。

## 3. 本轮我亲手复算的（02:0x，非转述）

| 项 | 实测 |
|---|---|
| v0.13 四元组 | 277,296 B / 2,295 LF / 全文 a1374eb5cc526e11… / head -c 275854 = 73901fd0faff9711… —— 四项命中 |
| gate.py | 32,611 B / 758 LF / 6b59f799…；FS03×15、FS04×9、FS09×10、FS08=0、FS10=0、GATED_KINDS=0、namespace×28、NotImplementedError×1 |
| test_factor_gate.py | 39,708 B / 924 LF / 08d46aac… |
| 测试（我跑） | gate **89 passed** / suite5 **74 passed**（与各报数一致，但**都不是全量**） |
| 因子目录 | all_factors() = **195**，非 ext_ = **110**，market_breadth **不在目录** |
| market_breadth | backend/app **0 命中** |
| 闸门接线 | assert_factors_usable 在 backend/app 仅 gate.py 自身 3 处（2 docstring + 1 def）→ **生产调用点 0**；GateError 无 handler |
| FactorSpec | **23 字段**，含 alias_of / strategy_usable，**无 status** |
| 真盘 status | custom_factors/ 15 个 JSON：**8 active**（23:33:57）+ 7 draft；全 user_data 含 "status":"active" 的文件 = **8** |
| E4 日历 | 2,141 日 / 首 2018-01-08 / 末 2026-11-06；month_end 全轴 **107**、评估窗 **88**；ISO week_end 全轴 **452**、窗内 **376** |
| 2024-02 | **15** 个交易日；02-29 **在轴上且就是 month_end**；02-09 不在轴；节前末日 02-08 |

## 4. P0-X：单条 alias 的 detail 是 8 键，不是 7 键（本人实测，审核未报）

真盘实跑（RegistryFacts(D:/TSP/data)，mode=production，单个 id）：

```
vol60   -> code=FS03, blocked=(('vol60',None,'FS03'), ('vol60',None,'FS01'))
           detail keys = 8: code/mode/submitted_id/resolved_id/canonical_id/table_row/message/violations
uf_vol60 -> OK, blocked=()
ma20    -> code=FS01, detail keys = 8 (7 + status)
```

根因：8 个 alias 的 FactorSpec 来自 pack，**没有 status 载体** → 除 FS03 外必然再出一条 FS01，report.blocked 长度 2 → 触发 gate.py:660 追加 violations。

这不是边界，是**全部 8 个 alias 的常规路径**。后果：契约 §7.16.4「单条 FS03 恰好 7 键」与 F-A42-2「detail 逐键等于 7.16.4 示例」**按字面判必失败**；而测试里 set(error.detail) == FS03_DETAIL_KEYS 之所以全绿，是因为单测用合成事实源，未复现真盘双码。

裁定（本部门内）：**同一 submitted_id 命中多码时只报最高优先级一码，不写 violations；violations 仅当 blocked 含 ≥2 个不同 id 时出现。** 优先级 FS04 > FS03 > FS06 > FS01。契约补一句，实现补去重，审核补真盘回归。

## 5. P0-Y：契约 §5.6 E4-A4 与真盘相反

契约 v0.13:605 写「春节所在月（如 2024-02）month_end == 节前最后一个交易日，2/29 不存在于轴上」。

真盘相反：02-29 **在轴上**且**就是** 2024-02 的 month_end；节前最后交易日是 02-08；除夕 02-09 不在轴；该周（02-05…02-08）的 week_end = 02-08。

**不改这条，B4 返工必交一份红。**

## 6. 交付判定

| 批 | 判定 | 附条件 |
|---|---|---|
| B0（14 因子注册） | **结项** | ①不得写「alias 已隔离」；②矩阵路径 uf_* 0/9；③REGISTRATION_B0 的 4.6% 已作废，正确值 77.06% |
| B2（E3/E2/E1 frame 实现） | **维持结项** | ①证据口径固定「限定文件集 + 干净检出」（74 passed），不得引用全量；②36 条顺序污染单独立项；③6 条过期/真红挂回归清单 |
| B4（E4 调仓日轴） | **FAIL · 待返工** | 数字全对（88/376 我独立命中），败在判据编号与 E4-A4 与真盘相反 |
| B0b-1（闸门载体） | **已交付 · 未接线** | 生产调用点 0 ⇒ 当前零拦截 |
| market_breadth | **未交付** | 门票已冻结，backend/app 0 命中 |
| G4（6 个单侧件 FS01） | **P0** | 按 id 豁免不允许；唯一解除路径是 FactorSpec 增 status + 逐只 V3 |
| 全量 tests/ 49 红 | **P0** | 36 顺序污染 / 7 缺数据环境 / 6 过期或真漂移 |

## 7. 闸门的准确状态（口径固定，别再说错）

**「已实现 · 已测 · 载体已补 · 未接线」。**

| 输入 | mode=production | 说明 |
|---|---|---|
| 8 个 alias + facts=RegistryFacts(D:/TSP/data) | FS03 8/8 | 但 detail 8 键（见 P0-X） |
| 8 个 canonical + 真盘 facts | **OK 8/8** | 23:33:57 升 active 后才成立 |
| 8 个 canonical + **库默认 facts** | **FS02 8/8** | 默认事实源看不到盘上 JSON 的 status，是载体断链第二口子 |
| 6 个单侧件 | FS01 6/6（detail 带 status） | 设计行为 |
| 8 alias + 8 canonical 同批 | FS04 + dual_ids，8 键 | 与 C2/C7 一致 |
| diagnostic 提交 alias | OK | 设计行为 |
| research 提交 alias | FS01 | 设计行为 |

## 8. 12 条策略（三列不合并）

- 因子侧可表达（frame 路径）：**11/12**（仅 S04 缺 rsi_14_pct）
- 可回测（矩阵路径）：**0/12**（uf_* 0/9，unsupported 23→25）
- 可上生产：**0/12**（未接线 + X1 未实现）

S09 / S02：**口径层可准入、策略层判死**。S09 提交态复跑 732 笔 / 59,011.37 / −94.0989% 与 registry 逐值相同（差异 0），「S09 不可复现」已撤回。

## 9. 本轮派工

| 对象 | 任务 |
|---|---|
| 系统开发工程师 | ① gate.py 单 id 多码去重（P0-X）+ 真盘回归用例 ② B4 返工按 P0-Y 改写后的判据 ③ market_breadth 注册（4 处 110 常量→111） |
| 系统架构师 | v0.14 一次性改齐三项：P0-Y E4-A4 改写、P2-1 D10 落字、P0-X 去重口径一句；四元组自复算；声明冻结前最后一版 |
| 独立审核工程师 | ① 复核 P0-X 并给 B4 返工最终可执行断言 ② 6 条过期/真红的归属与验收 ③ v0.14 签发条件 |
| 行情数据工程师 | 7 条缺数据环境失败的三处数据前置 + st_history 于 2026-10-20 批量写 198 行 False 的成因 |

## 10. 未证 / 未做

- v0.13 **无签发结论**，不得当冻结版引用；v0.14 未出。
- 本轮**未跑任何收益回测、无收益数字**。
- F-A40 / F-A41 / F-A11a–d **实现仍为零**（G2CaliberError / FS08 / FS10 / MATRIX_KERNELS 在 backend/app 各 0 命中）。
- B5 / B6 / B0b-2 未开工。
- research/ 与 docs/research/ 是两个目录，前者复现锚只在部分文件上。
- 工作区有非本部门产物待清：根目录 nul、backend/tests/test_zz_probe_tmp.py、.factor_engineer_batch/。

## 11. 修订记录

v9 本轮（换 v0.13、立 P0-X / P0-Y、B4 维持 FAIL、闸门四段状态表、E4 独立复算）→ v8（v0.12 候选、B4 判 FAIL、G4 P0、49 红 P0）→ v7（首版本锚 + 检出探针）→ v6（12 条三列、D10、110）→ v5（契约谱系 v0.9）→ v1–v4 作废。