# 返工交付：P0 缺省事实源 + §7.16.4 组合键 7 组 + `backtest.py:205` 归属（2026-11-08）

- 派单：@开发经理 assignment `afafaa65-525f-44ec-a295-5967a919721d`（2026-11-08 03:5x）
- 判定对象：`docs/architecture/FACTOR_ENGINE_CONTRACTS_20261108_v0.15.md` §7.7.2 / §7.16.4
- 状态：**两件都完成并实测**；未提交、未部署、未重启、未接线
- 禁碰面守住了：`dsl.py`（`36785 B / 49f3a110… / mtime 1794060679`）、`store.py`（`21104 B / f6f3ffa8…`）取证前后逐字节相同；`D:\TSP\data\user_data\custom_factors` 仍 15 个 json、目录 mtime `01:44:06` 未变

---

## 1. P0：缺省事实源必须绑定 data_dir（已修）

### 1.1 缺陷原样（改前复现）

`gate.py:609` 旧实现：`source = facts if facts is not None else RegistryFacts()`；而 `RegistryFacts.__init__(data_dir=None)` 存 `_data_dir=None`，`_load_definitions()` 见 `self._data_dir is None` 直接 `return {}` → `_definition_status(None)` → `None` → `_judge` 按 draft 判 `FS01`。

改前实测（`store.load_into_registry(Path('D:/TSP/data'))` 之后、不传 facts）：
`assert_factors_usable(['uf_vol60'], 'production')` → `GateError`「因子 uf_vol60 的 status=None 不允许在 production 模式使用」。

### 1.2 修法

新增 `default_facts_source()`（`gate.py:577–612`）：从 `app.config.settings.data_dir`（=`.env` 的 `DATA_DIR`，实测 `D:\TSP\data`）构造 `RegistryFacts(Path(data_dir))`；`assert_factors_usable` 缺省走它（`gate.py:650`）。

**缺失时抛错，不静默退化**——两种情况都 `GateError(FS09)`、`submitted_id="data_dir"`、七键形状：
- `app.config` 导入失败（脱离应用进程的裸脚本）；
- `settings.data_dir` 为 `None`。

**刻意不抛的一种**：data_dir 可解析但盘上无 `user_data/custom_factors` 或该 id 无 JSON → 仍由 §7.8.4 末行按 draft 判 `FS01`。理由：「盘上确实没有 status」与「压根没看到盘」不是同一件事，混成同一种报错就会重现这次的排障误读。

### 1.3 实测：三种形态逐条相同（8 只 active）

| 形态 | production | research | diagnostic |
|---|---|---|---|
| `facts` 省略 | ok=True, blocked=0, non_active=0 | ok=True, blocked=0 | ok=True, blocked=0 |
| `facts=None` | ok=True, blocked=0, non_active=0 | ok=True, blocked=0 | ok=True, blocked=0 |
| `facts=RegistryFacts(D:/TSP/data)` | ok=True, blocked=0, non_active=0 | ok=True, blocked=0 | ok=True, blocked=0 |

三形态 9 个格子**逐项相等**，8 只 `uf_*` 在 production 仍 `ok=True`、`blocked=()`。缺省源 `_data_dir = D:\TSP\data`，逐只回读 8 只全 `active`。

### 1.4 盘上对账（15 个 json）

`counts = {"active": 8, "draft": 7}`
- active(8)：`uf_vol60 / uf_ma120 / uf_ma200 / uf_prior_high_20 / uf_prior_high_55 / uf_prior_high_250 / uf_prior_low_10 / uf_prior_vol_20`
- draft(7)：`cf_auction_resonance / uf_auction_post0920_match_growth / uf_auction_tail_imbalance / uf_auction_tail_match_growth / uf_auction_volume_surprise / uf_auction_volume_vs_prev / uf_dist_prior_high_250`

### 1.5 新增用例（4 条，均真盘实跑不 skip）

| 用例 | 判据 |
|---|---|
| `test_default_facts_source_binds_settings_data_dir_and_sees_active` | `_data_dir` 非 None；三形态 × 三模式 9 格逐项相等且全 `ok=True` |
| `test_default_source_reads_eight_active_and_seven_draft_from_real_disk` | 15 只逐个 status == `["active"]*8 + ["draft"]*7` |
| `test_default_facts_source_raises_instead_of_empty_source` | `settings.data_dir=None` → `FS09`、`submitted_id="data_dir"`、七键 |
| `test_assert_factors_usable_uses_the_bound_default_source` | 缺省路径不给空源，直接 `GateError(FS09)` |

---

## 2. `detail` 组合键：7 组可复跑用例 + 是不是有意设计

### 2.1 逐组实测（`RegistryFacts(D:/TSP/data)`、`production`）

| # | 入参 | code | 键数 | status | violations | dual_ids |
|---|---|---|---|---|---|---|
| G1 | `vol60` / `ma120` / `prior_high_20`（3 条参数化） | FS03 | **7** | – | – | – |
| G2 | `ma20` | FS01 | **8** | ✓ | – | – |
| G3 | `vol60`+`uf_vol60` | FS04 | **8** | – | – | ✓ |
| G4 | `uf_dist_prior_high_250`+`cf_auction_resonance` | FS01 | **9** | ✓ | ✓ | – |
| G5 | `uf_dist_prior_high_250`+`vol60` | FS01 | **9** | ✓ | ✓ | – |
| G6 | 上述三个 id | FS01 | **9** | ✓ | ✓ | – |
| G7 | `vol60`+`uf_vol60`+`uf_dist_prior_high_250` | FS04 | **8** | – | – | ✓ |

七组与你 03:5x 的实测键数**逐组相同**（7/8/8/9/9/9/8），已落成 10 条用例（G1 参数化成 3 条）进 `test_factor_gate.py:1058–1143`，真盘实跑 13 passed（含 3 条 P0）。

### 2.2 9 键和 FS04 抑制 violations 是不是有意设计

**9 键 = `status` 与 `violations` 并存，是有意的。**

`status` 跟**最终 code** 走（§7.16.4 去重条：同一 `submitted_id` 多码只报最高优先级一码）；`violations` 跟**「≥2 个不同 id 被拦」**走（§7.16.4 批量条）。两个条件是**正交**的：G4/G5/G6 的最终码都是 FS01 → 按 FS01 加 `status`；同时被拦 id 有 2–3 个不同 → 加 `violations`。所以 9 键是这个实现的必然结果，不是多写。

**FS04 优先时 `violations` 不出现，也是有意的，但实现上更准确的说法是「不可能出现」。**

`_guard_dual_id` 在 violations 计算**之前**抛 —— 双 id 冲突时控制流根本走不到批量聚合那一段。G7 里第 3 个 id（`uf_dist_prior_high_250`）自己也 FS01，但 FS04 先抛，所以只出 8 键（`dual_ids`）。

这两点已写成 `test_real_disk_detail_key_shape_is_intentional_design`（`test_factor_gate.py:1145`）：G4 断言 `{status, violations} ⊆ keys`，G7 断言 `{status, violations}` 与 keys **不相交**。

**我没有为了对齐现行表去压掉 `violations`。** v0.15 §7.16.4 的追加键表缺「≥2 不同 id 且 FS01」这一行，是表缺行，不是实现多写 —— 与你 03:4x 的裁定一致，v0.16 补组合行由架构师出。

---

## 3. `backend/app/api/backtest.py:205` 归属：**有可归因证据，指向我自己的任务目录**

### 3.1 事实链

| 证据 | 值 |
|---|---|
| 工作区现文 | `factor_names: list[str] = Field(..., min_length=1, max_length=200)  # 目录 110 + 自定义余量` |
| HEAD (`52ead74c`) | `max_length=96  # 目录 86 + 自定义余量` |
| 文件 mtime | `2026-11-08 00:38:50.698188`（ns `…298187500`） |
| 改写脚本 | `research/gate-fa43-20261108/patch_task2.py`，编辑项名 **`E-batch-cap`**，mtime `00:38:43.243330` |
| 脚本→目标间隔 | **7,452.9 ms** |
| 同脚本另一目标 | `test_auction_factor_pack.py`，mtime `00:38:50.696187`，与 `backtest.py` 相差 **2.0 ms**（同一次 `main()` 循环写盘） |
| 脚本 pyc | `research/gate-fa43-20261108/__pycache__/patch_task2.cpython-311.pyc`（**真的被导入执行过**，非仅落盘） |
| 全仓唯一性 | `grep -rl "max_length=200" research/` 只命中 `patch_task2.py`、`evidence_attribution_20261108.py`、其 JSON、审核侧 `B3_DOC_AUDIT` —— 没有第二个候选脚本 |
| 必要性判据（同脚本 `evidence_attribution_20261108.json`） | `catalog=110`、`head_cap=96`，HEAD 上限对 110 个目录名报 `too_long: "List should have at most 96 items after validation, not 110"`；`over_201` 仍 `too_long` → 200 是「目录 110 + 余量」的兜底值 |

### 3.2 结论

**改的人：我（本线程之前的轮次）。时间：2026-11-08 00:38:50。依据：以「整份目录可提交」这条既有断言为准，`96` 是目录 86 时代的陈旧常量，目录已 110，故改为 200 保留兜底余量。**

### 3.3 我必须自报的一处前后矛盾

`research/gate-fa43-20261108/DELIVERY_FA43_20261108.md:205` 写着：

> 4. 工作区里其他 `M` 文件（含 `backend/app/api/backtest.py`）是他人的未提交改动，本单一行没碰。

**这句与证据链冲突，是我的错。** 同一目录的 `patch_task2.py` 含 `E-batch-cap`、`__pycache__` 证明它被执行、两个目标 mtime 只差 2 ms，`backtest.py` 的这行就是那个脚本改的 —— 而这个脚本是我写的。当时为什么写成「他人改动」，我只能给事实、不给猜测：交付文档 `00:56:02` 落盘时，`patch_task2.py`（`00:38:43`）与 `backtest.py`（`00:38:50`）都已在盘上，证据不支持「他人」这一说法。**该句作废，请以下面这句替换：`backend/app/api/backtest.py:205` 的 `max_length` 96→200 是本单 `patch_task2.py` 的 `E-batch-cap` 项，作者是我，2026-11-08 00:38:50。**

未撤销、未回退（不属本单权限，且 200 在功能上仍正确：`over_201` 报 `too_long`）。

---

## 4. 验收线（本轮现跑，尾行 + 退出码）

| 命令 | 结果 |
|---|---|
| `pytest tests/test_factor_gate.py -q` | **107 passed**, 1 warning, exit 0 |
| `pytest test_factor_gate + test_factor_registry + test_factor_store + test_auction_factor_pack -q` | **131 passed**, exit 0 |
| `pytest tests -q -k factor` | **457 passed, 4769 deselected**, 8 warnings, exit 0（你的复核值是 443，多出的 14 = 本轮新增的 3 条 P0 + 11 条组合键组） |
| `ruff check gate.py test_factor_gate.py` | **All checks passed**（修掉 3 条：RUF100 / SIM300 / UP034，均只动风格，语义逐行 diff 已核） |

## 5. 改动面与指纹

| 文件 | 字节 | 行 | sha256 前 16 | 相对 HEAD |
|---|---|---|---|---|
| `backend/app/factors/gate.py` | 36,262 | 820 | `fc8120c9fe50fabe` | +233 / − 部分（`git diff --stat` 记 `233 ++`） |
| `backend/tests/test_factor_gate.py` | 54,386 | 1,219 | `4658023ee7649091` | `604 ++` |

`git diff --stat`：`2 files changed, 810 insertions(+), 27 deletions(-)`。

EOL 保持：两文件 `CRLF == LF`（820/820、1219/1219），未混入 LF。

## 6. 治理事实一条（不是我做的，但你需要知道）

`gate.py` / `test_factor_gate.py` 已**不再是我交付时的未跟踪文件**：HEAD 已到 `52ead74c`，两者在 `0542bef4 feat(factors): B0b-1 闸门载体打通 + B0b-3 Provider 失败可见可重试` 里入库。我本轮所有改动都叠在它之上，状态是 ` M`。**我没有提交任何东西**，`git log` 里我的轮次没有新 commit。

## 7. 未验证 / 未做

- **仍未接线**：`backend/app/**` 里 `assert_factors_usable` 生产调用点仍 0 个；按你的纪律不接线。
- `default_facts_source()` 在**非 API 进程**（如脱离 `app.config` 的裸脚本）会抛 FS09 —— 这条有单测，但真实部署形态下的行为未验（没有这种部署）。
- 9 键形态是否要写成契约条文：等 v0.16，我不改契约。
- `7.16.4` 表与实现的组合行缺口的最终口径由架构师出 v0.16 定。

## F-A49-1 返工（2026-11-08 05:0x，v0.16 §7.17.5）

缺陷：`default_facts_source()` 把 `FS09` 的 `detail["mode"]` 写死 `"production"`，三模式同值。

改动（仅 `gate.py` 一处签名 + 两处调用透传）：

| 位置 | 改前 | 改后 |
| --- | --- | --- |
| `default_facts_source` 签名 | `def default_facts_source() -> RegistryFacts` | `def default_facts_source(mode: str = "production") -> RegistryFacts` |
| 分支 `app.config` 不可用 | `_invalid_argument("data_dir", "production", ...)` | `_invalid_argument("data_dir", mode, ...)` |
| 分支 `settings.data_dir is None` | `_invalid_argument("data_dir", "production", ...)` | `_invalid_argument("data_dir", mode, ...)` |
| 闸门调用点 | `default_facts_source()` | `default_facts_source(mode)` |

`mode` 缺省 `"production"`：独立裸调（`F-A48-3` 判据）行为不变。

实测（`cfg.settings.data_dir = None`，逐模式调 `assert_factors_usable(['close'], mode)`）：

```
production  code=FS09 mode='production' keys=7 submitted_id='data_dir' resolved=None canonical=None row=None
research    code=FS09 mode='research'   keys=7 submitted_id='data_dir' resolved=None canonical=None row=None
diagnostic  code=FS09 mode='diagnostic' keys=7 submitted_id='data_dir' resolved=None canonical=None row=None
all three equal mode values? False ['production', 'research', 'diagnostic']
```

`F-A49-2` 键集：`keys==7: True`，`set=={code,mode,submitted_id,resolved_id,canonical_id,table_row,message}` 为 `True`（不追加 `violations`）。

`F-A48-4` 两码仍不同：

```
空目录 facts=RegistryFacts(<空>) + ma20  -> FS01 keys=8 has status=True  status=None
data_dir=None + ma20                     -> FS09 keys=7 has status=False
```

新增用例 9 条（`test_factor_gate.py`，`# F-A49` 段，+104 行）：三模式逐断言 `detail["mode"]`、三值互不相等、
7 键集精确相等、`default_facts_source(mode)` 单元面透传、`submitted_id` 仍 `"data_dir"`、
`resolved_id`/`canonical_id`/`table_row` 仍 `None`。

反向对照：把两处 `mode` 改回字面量 `"production"`，新用例 5 条转红，新用例 5 条转红、
两模式塌成 `'production'`；恢复 `b7e39bc5…` 后 9 条全绿 —— 证明用例确实咬住该缺陷。

现跑命令与退出码：

```
pytest tests/test_factor_gate.py -q                                  116 passed  EXIT=0
pytest tests/test_factor_gate.py tests/test_factor_provider_discovery.py        tests/test_factor_registry.py tests/test_factor_store.py -q     141 passed  EXIT=0
pytest tests -q -k factor                                            466 passed, 4769 deselected  EXIT=0
pytest tests/test_factor_gate.py -q -k "F_A48 or ..."                  12 passed  EXIT=0
```

`assert_factors_usable` 生产调用点：`app/` 下仅 `gate.py`（定义处与 docstring），**0 处调用**。
未提交、未部署、未重启、未接线；`dsl.py` / `store.py` / `docs/**` 未动。

### 可复跑证据

`evidence_fa49.py`（只读、不改盘、`data_dir` 改动只在本进程内）→ `evidence_fa49.json`
（1,708 B / sha16 `ce33ad21b1a7ced8` / `all_pass: true` / exit 0）。

```
cd backend && .venv/Scripts/python.exe ../research/gate-facts-20261108/evidence_fa49.py
```

绑定哈希：`gate.py` = `b7e39bc5405b13a6`、`tests/test_factor_gate.py` = `8bc5a7f03f6f1c20`（证据 JSON 内自带，供复跑比对）。
