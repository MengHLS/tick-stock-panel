# referenced_factor_inventory 交付（L0 闸门第一个交付）

- 生成时间：2026-11-07 17:00（Asia/Shanghai）
- 生成人：系统开发工程师（契约 §7.10.2：生成＝系统开发，签认＝因子工程师，消费＝闸门只读）
- 依据：`docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.5.md` §7.10.2（产物字段）、§7.10.3（N1/N2/N3）、§7.10.5（今天的逐 id 结论）、§7.10.6（F-A22–F-A26）
- 本批范围：**只加这三样**——`backend/scripts/build_referenced_factor_inventory.py`、`docs/architecture/evidence/referenced_factor_inventory.json`、同名 `.sha256`。未改后端源码、未改活配置、未提交、未部署、未重启。

---

## 1. 交付物

| # | 路径 | 说明 |
| --- | --- | --- |
| 1 | `backend/scripts/build_referenced_factor_inventory.py` | 生成器（36,946 B；`ruff check` All checks passed） |
| 2 | `docs/architecture/evidence/referenced_factor_inventory.json` | 产物，167 条记录 / 67 个被解析文件 |
| 3 | `docs/architecture/evidence/referenced_factor_inventory.json.sha256` | `3c9a186aad77078065e29d8fcfcc531d69021f4b0b4a1ed82dbb2810cca1ae91  referenced_factor_inventory.json` |

重跑命令（在仓库根）：

```
backend\.venv\Scripts\python.exe -X utf8 backend\scripts\build_referenced_factor_inventory.py
```

`--data-dir` 缺省取 `app.config.settings.data_dir`（本机 = `D:\TSP\data`，扫描 `D:\TSP\data\user_data`）；`--out` 可改输出路径；`--quiet` 只打自检。

---

## 2. 运行的命令与结果

| 命令 | 退出码 | 结果 |
| --- | --- | --- |
| `build_referenced_factor_inventory.py`（完整输出，跑 ≥4 次） | **0** | 13 项自检全 PASS（见 §3） |
| `build_referenced_factor_inventory.py --quiet`（紧接着再跑一次） | **0** | 除 `generated_at` 外与上次逐字节相同（外部 `diff` 验证） |
| `ruff check backend/scripts/build_referenced_factor_inventory.py` | **0** | All checks passed |

顶层实测值：

```
data_root      : D:\TSP\data\user_data
repo_head      : 65c6e42f1fcd6362e72699afb118bdbcb247b3d3
scanned_sources: 67  {custom_signal 21, monitor_rule 1, strategy_override 4,
                      custom_factor 15, strategy_config 25, research_strategy 1}
records        : 167
summary        : by_verdict {allow 63, exempt 104} / by_code {null 167}
                 by_namespace {column 63, factor 104}
stale_count    : 0
```

`records` 构成：`strategy_config 76 / custom_signal 52 / custom_factor 20 / research_strategy 14 / strategy_override 4 / monitor_rule 1`；其中 `both_collision=true` 的伴生记录 **8 条**（F-A24 要求）。`path_scope` 取值：`history 166 / intraday 1`（无 `both`，理由见 §5.2）。

`code` 全为 null：`FS01`–`FS07` 一条未触发；`verdict` 无 `block`、无 `unknown`。

---

## 3. 13 项自检（脚本内建，随生成一起打）

| # | 判据 | 实测 |
| --- | --- | --- |
| 1 | F-A22 幂等 | 两次生成除 `generated_at` 外逐字节相同（PASS） |
| 2 | §7.10.2 字段 | 17 字段 / 167 条，越界 0 条（PASS） |
| 3 | F-A25 无 `unknown` | 0 条（PASS） |
| 4 | F-A26 新鲜度 | `stale_count` 复算 0 / 记录值 0（PASS） |
| 5 | F-A24 冲突必报 | 4 个冲突名的 `column` 侧命中 4/4，伴生记录 8 条（PASS） |
| 6 | F-A23 不全文 grep | 散文/展示列误计 0 条（PASS） |
| 7 | 22 条 enabled 源 | enabled 源 22 条（期望 22），缺 verdict 0 条（PASS） |
| 8 | 7 条冲突信号=column | 判错 0 条（PASS） |
| 9 | 2 个 virtual 不拦 | virtual 记录 2 条，判错 0 条（PASS） |
| 10 | FS01 实拦 | **0 条**（PASS） |
| 11 | `path_scope` 无悬空 both | 取值集合 `['history','intraday']`（PASS） |
| 12 | **N3 通道可触发**（反向对照） | `ma20` 按 `both` 解析 → `divergence=True`、`verdict=block`（PASS） |
| 13 | **FS01 通道可触发**（反向对照） | 15 个 `draft` 定义逐个当因子试探 → 15/15 判 `block`+`FS01`（PASS） |

第 12/13 项是本轮补的**反向对照**：证明「FS01=0」不是「闸门永远不响」，而是「今天没有任何活配置真的把注册表因子当因子引用」。审核若怀疑通道是死代码，看这两条。

---

## 4. done_when 逐条回答

| 要求 | 结果 |
| --- | --- |
| 脚本 exit 0 | **0**（多次连续运行均 0） |
| 22 条 enabled 引用逐条有 verdict | **22 个源 / 53 条记录全部有 verdict**；其中 45 条 `allow`（全是 `column`）、8 条是 F-A24 伴生记录（`exempt`，不参与放行）。**22 条活配置里没有任何一条引用注册表因子**，因此 `FS01` 无从触发 |
| 7 条命名空间冲突信号判 `column` | **7/7**：`ma20_breakdown`、`ma20_breakout`、`ma_dead_5_20`、`ma_golden_20_60`、`ma_golden_5_20`、`boll_breakdown_lower`、`boll_breakout_upper`，逐条主记录 `ref_namespace=column` / `verdict=allow`；每条另配 `both_collision=true` 的因子侧伴生记录 |
| 2 个 virtual 不判 block | `distance_to_high_60d`、`limit_up_count_20d`（另含同源 `position_240d`）均 `class=virtual` / `verdict=exempt`，**0 条 block** |
| `stale_count` 复算为 0 | 记录值 0、按盘上字节重算 0 |
| 按现在规则被 FS01 真拦的是几条 | **0 条**（且 0 条 `block`、0 条 `unknown`） |

---

## 5. 口径是怎么落的（N1 / N2 / N3 + 本轮修正）

### 5.1 N1：命名空间先于分类

- 条件右值的 `field:` 前缀先剥掉再查 `ALLOWED_FIELDS`（与 `custom_signals._parse_right` 同口径），命中即 `namespace=column`、不进因子闸门；未命中才回落 `factors.registry`。
- `resolve()` 里 `column` 与 `factor` 是**互斥分支**，不是并集：`ALLOWED_FIELDS ∪ registry` 只用于「这个字段合不合法」，不用于判 namespace。
- 判定用的列集合是**按路径**取的：历史路径用 `ALLOWED_FIELDS`，盘中路径用盘中列集合（§5.2）。`resolve()` 的 `column` 成员判定与 `path_namespace()` 用同一集合，两处不会各说各话。

### 5.2 N3：path_scope 按真实求值路径记，不写「both」

本轮修正了上一版的建模错误，4 处改动（全部在生成器内，无后端改动）：

| 改动 | 上一版 | 本版 | 代码依据 |
| --- | --- | --- | --- |
| 盘中列集合 | `ENRICHED_COLUMNS`（59，含 `ma20`/`boll_*`/`rsi_*`） | `ENRICHED_STORAGE_COLS`(15) + `limit_up_price`/`limit_down_price` + `INTRADAY_FEATURES`(11) = **28** | 指标列不落盘：`ENRICHED_STORAGE_COLS` 只有 16 个存储列，`ma20` 等由 `pipeline` 在历史窗口上现算。上一版等于宣称「单日快照里有 ma20」，事实相反 |
| 日线 custom_signal 的 `path_scope` | `both` | `history` | `custom_signals.build_intraday_expressions` 显式 `if sig.get("timeframe") != TIMEFRAME_INTRADAY: continue`；日线信号只在 `compute_signals`（历史帧）上求值。`timeframe=intraday` 的才记 `intraday` |
| `strategy_override` / `strategy_config` 的 `path_scope` | `both` | `history` | 策略侧 `scoring` 键与 overlay 条件由 `materialize_scoring_columns` 在 enriched 历史帧上兑现；回测与实时都用同一条历史帧管线 |
| `resolve()` 的 `column` 成员集合 | 恒用 `ALLOWED_FIELDS` | 按 `path_scope` 取（盘中用盘中列集合） | 同上；否则 `INTRADAY_FEATURES` 里的 `vwap`/`price` 会被判 `unknown`→`FS02` |

**这条修正的影响是可验证的**：上一版因为「盘中也有 ma20」，`path_divergence` 结构上永远为假——N3 的分叉通道等于死代码。本版把它接活，并在自检第 12 项用反向对照证明它会响。

**敏感度（给口径归属方一个数）**：若把 7 条冲突信号按 `both` 记（即认为它们也在盘中单日快照上求值），4 个冲突名都会 `divergence=True → verdict=block`，逐条就是这 7 条：

```
ma20        history ns=column / intraday ns=factor     → block
ma60        history ns=column / intraday ns=factor     → block
boll_lower  history ns=column / intraday ns=factor     → block
boll_upper  history ns=column / intraday ns=factor     → block
→ 命中 ma20_breakdown / ma20_breakout / ma_dead_5_20 / ma_golden_20_60 /
      ma_golden_5_20 / boll_breakdown_lower / boll_breakout_upper 共 7 条
```

也就是说：**「7 条判 column、FS01=0」与「path_scope=history」是同一个判断的两面**。若谁认定日线信号也跑盘中路径，这 7 条会变成 `path_divergence` 而非 `column`，与 §7.10.5 的结论互斥。我按 §7.10.5 + 代码事实取了 `history`。

### 5.3 N2：伴生记录

4 个冲突名（`ma20`/`ma60`/`boll_lower`/`boll_upper`）主记录一律 `column`/`allow`，另出一条 `both_collision=true` 的因子侧视图（`ref_namespace=factor`、`class=custom_dsl`、`verdict=exempt`、`code=null`、`evidence` 末尾加 `# N2 伴生记录: 同名基础列优先, 不参与放行`）。

**口径选择（需签认方确认）**：伴生记录的 `verdict` 我**强制 `exempt` 而不是照因子侧实判**。若照实判，`ma20` 的 pack 定义是 `draft`，伴生记录会变成 `block`+`FS01`，`summary.by_verdict` 就会凭空多出 8 条 block，与「FS01 实拦 0 条」自相矛盾。伴生记录的作用是「登记冲突」而不是「提供放行输入」，所以我让它不参与放行。这一条契约没写，属我按 F-A24 意图取的口径，请因子工程师签认。

### 5.4 fail-closed 方向

- 任一侧解析不出（既不在列集合也不在注册表）→ `namespace=unknown`、`verdict=block`、`code=FS02`（F-A25 要求清单里 `verdict=unknown` 为 0；本版 0 条）。
- 两路径结论不一致 → `path_divergence=true` 且**不得判 `allow`**（N3）。
- `source_enabled` 三态：`custom_signals`/`monitor_rules` 取顶层 `enabled`；`strategy_overrides` 与 `strategy_config` 无顶层开关 → `null`（未声明，既非 true 也非 false，不计入 22）；`custom_factors` 与 `research_strategy` 是定义不是活配置 → `null`。

---

## 6. 「只多了这三样」的证据

```
$ git status --porcelain -uall | grep architecture/evidence
?? docs/architecture/evidence/referenced_factor_inventory.json
?? docs/architecture/evidence/referenced_factor_inventory.json.sha256
$ # 计数 = 2

$ find backend -name "*.py" -newermt "2026-11-07 16:50" -not -path "*/.venv/*"
backend/scripts/build_referenced_factor_inventory.py        ← 本批唯一新增/改动的后端文件

$ ls --time-style=full-iso backend/app/api/factors.py backend/app/factors/store.py
2026-11-07 16:33:57  backend/app/api/factors.py      ← F-A5 批次留下的改动，本批未碰
2026-11-07 16:33:52  backend/app/factors/store.py    ← 同上（sha256 de77eae6…，F-A5 绑定对象）
```

`git status --porcelain` 在「生成前 / 生成后」两次调用**逐行相同**（`diff` 空），说明生成过程没有顺手改动任何被跟踪文件；`docs/architecture/` 整体仍是未跟踪目录（契约等文档由架构师创建，早于本批），其下本批新增仅 evidence 这两个文件。

`--data-dir` 只读：生成器对 `D:\TSP\data\user_data` 只做 `read_text`/哈希，无写入；`stale_count=0` 与 `source_sha256` 逐条复核是同一件事（每次运行都按盘上字节重算）。

另：上一轮曾在 `research/factor-registration-fa5b-20261107/scripts/` 留过一份暂存副本（16:53、34,688 B，是修正前的版本）。已删除，避免出现两个定义源；现在全仓 `build_referenced_factor_inventory.py` 只有 `backend/scripts/` 一处（`find . -name build_referenced_factor_inventory.py` 单命中）。

---

## 7. 待裁定（3 条，都写在这里等签认，我没有自行扩权）

1. **`path_scope` 模型**（§5.2）：我按「日线信号只在历史帧求值」取 `history`，因此 7 条冲突信号判 `column`、FS01=0。若因子工程师/架构师认定日线信号也跑盘中单日快照，这 7 条会翻成 `block`（`path_divergence`），与 §7.10.5 互斥——请二者之一给最终口径，我按新口径重跑。
2. **伴生记录的 `verdict`**（§5.3）：我取 `exempt`（不参与放行）。若要照因子侧实判（会产生 8 条 `block`+`FS01`），改一行即可，但会影响 `summary.by_verdict`。
3. **`records[]` 17 字段的第 16/17 个**：§7.10.2 表格只列了 15 个，F-A24 要求的 `both_collision` 与 N3 要求的 `path_divergence` 是我补的两个字段（顺序固定在 `evidence` 之后）。请架构师确认这两个字段名与位置，避免闸门消费端对不上。

---

## 8. 未验证 / 未知

- **`user_data` 之外的 config 覆盖**：生成器只扫 `data_root/user_data` 下的 `custom_signals`/`monitor_rules`/`strategy_overrides`/`custom_factors`，加仓库内 `strategy_config`（seeds META）与 `research_strategy`（研究侧 json）。若生产另有 config 根（例如按账户分目录），本清单覆盖不到——我没找到这样的根，但也没证明不存在。
- **`INTRADAY_FEATURES` 以外的盘中列**：盘中列集合取 `ENRICHED_STORAGE_COLS ∪ {limit_up_price, limit_down_price} ∪ INTRADAY_FEATURES`。`prev_close`/`change_pct` 等是否在分钟帧上存在，我按「不保证存在」处理（即不算盘中列）——今日 0 条 intraday 信号，不影响结果。
- **`ext_` 扩展列**：`ALLOWED_FIELDS` 之外还有 string 扩展字段（`ext_string_fields()`）与数值扩展因子。本版 `column` 集合只取 `ALLOWED_FIELDS`（严格按 N1 原文），所以配置里若引用 `ext_` 列会走注册表判定。今日 22 条活配置里 `ext_` 命中 0 条。
- **清单与闸门的一致性**：`assert_factors_usable` 尚未接线（F-A27：清单先于闸门）。清单里 `verdict` 的消费方式（只读主记录，还是连伴生记录一起读）由闸门实现时定，本版只保证伴生记录不参与放行。
- **`generated_at` 每次不同 → `.sha256` 每次不同**：F-A22 只要求「除 `generated_at` 外逐字节相同」，因此 `.sha256` 只对应它旁边那一份 json 的字节。本报告贴的 `3c9a186a…` 对应 `generated_at=2026-11-07T16:59:55+08:00` 那一份；任何人重跑都会得到新 sha（这是设计，不是漂移）。若要一个稳定锚点，需要一份「去时间戳」的规范化副本——需架构师定，我不擅自加产物。
