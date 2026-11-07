# B2 证据包复审（第二轮）：四问判定

- 审核人：独立审核工程师（不参与实现，自己写命令、自己复跑，不复用被审方脚本）
- 时间：2026-11-07 22:44–23:0x（Asia/Shanghai）
- 仓库 HEAD：`65c6e42f`（索引 16 文件 staged，**未 commit、未 push**）
- 被审对象（我实测，与派发书一致）：
  - `research/b2-engine-20261107/EVIDENCE_20261107.json` — 66,348 B / mtime 22:42:54 / sha256 `d4815e2b9bb17e95d050d7f6ba38c2a19049c67708da69b384d9bc6bb824c00f`
  - `research/b2-engine-20261107/B2_IMPLEMENTATION_20261107.md` — 28,045 B / mtime 22:42:43 / sha256 `6234a9d5a63221a0…`
- 本轮不重审 B2 实现、不重判 F-A5、不判 R8/R10/R11、不判 `rsi_14`。
- 纪律：TSP 生产目录只读（跑前跑后 15 个 json 的 `sha256 + size + mtime_ns` 三项全同）；临时目录跑；未重跑 `f_class_parity.py` 等会覆盖证据的脚本；未改他人文件；未提交/部署/重启。

## 单一结论

**证据包 PASS 可收**——四项判据全部通过、49 条断言可与盘上实测对上、原命令可复现 74/0、边界未破；但附两条须记账的缺陷（D-1 P2 追溯指针错、D-2/D-3/D-4 P3 笔误），且「干净检出全绿」这条交付结论**仍未达成**（门禁套件在索引态上 4 红，唯一原因是 docs 产物未入库，裁定权在开发经理）。

---

## 一、备注披露是否补齐 —— **PASS**（附 P3 笔误）

### 命令与退出码

```
$ stat -c '%s %y' backend/tests/test_factor_registry.py backend/tests/test_factor_store.py      # exit 0
$ sha256sum <同上>                                                                              # exit 0
$ git diff --cached --numstat -- backend/tests/test_factor_registry.py backend/tests/test_factor_store.py   # exit 0
$ git show HEAD:<file> | grep -c 'assert '                                                       # exit 0
$ grep -c '20:48:59|22:01:47|test_files_changed|未改任何测试' B2_IMPLEMENTATION_20261107.md      # exit 0
```

### 实测数字

| 项 | 证据声称 | 我实测 | 判定 |
|---|---|---|---|
| `test_factor_registry.py` mtime | 22:01:47 | **22:01:47** | ✅ |
| 同文件 bytes / lines / sha256 | 28,187 / 403 / `81e4b1f9…` | **28,187 / 403 / `81e4b1f9803642e77281249cfa0f3a8ec46e30008d7b91144aa545a5b5c2507d`** | ✅ |
| `test_factor_store.py` mtime | 22:01:47 | **22:01:47** | ✅ |
| 同文件 bytes / lines / sha256 | 6,793 / 171 / `79de1eca…` | **6,793 / 171 / `79de1eca6cc65522e8ed83b51c6dbb5c9fc74637faa1ac817b561dcc81a7dd9e`** | ✅ |
| numstat vs HEAD | +25/−6、+3/−3 | **25/6、3/3** | ✅ |
| `assert ` 条数 | 45→45、20→20 | HEAD 45/20 → 现盘 **45/20** | ✅ |
| MD 里 `20:48:59` / `22:01:47` / `test_files_changed` | 有 | **2 / 3 / 1 处命中** | ✅ |
| MD 里「本批未改任何测试」 | 不应再出现 | **grep 命中 0** | ✅ |

**派发书写「mtime 是否仍为 20:48:59」——已不成立，实际是 22:01:47**（B4 日历包 `month_end`/`week_end` 注册即进目录，本部门随之第二次更新过期计数）。新证据**自己没有掩饰这一点**，反而把两次更新都写进去了：`test_status.test_files_changed`（逐文件 mtime/bytes/lines/sha/assert 计数/why）+ `unchanged_on_purpose[3]` + MD 第 8 行与第 213 行。披露是**补齐的，且比派发书要求的更完整**。

**我实测的「改了什么」**（`git diff --cached` 逐行核对，与证据的 93→108 四处、70→85 两处一致）：
- `test_factor_registry.py`：改 6 处 assert 数字（`len(specs)` / `id 唯一` / `len(stock)` / `len(factors)` 由 93→110；两处 `len(etf)` 70→87）+ `GOLDEN_COLUMNS` 追加 19 行（日历包 2 + 研究补充 14 + `in_universe` 1 + 2 行注释）。
- `test_factor_store.py`：`builtin_count` 常量、1 处 `assert len(factor_columns_view())`、1 行同步注释，共 3 行。
- 断言条数不变（45/20），无 `skip`/`xfail`/`-k`，未退化为 `>=`。**即「改的是数字，不是判据」。**

### 本项缺陷

- **D-2（P3，计数笔误）**：证据写「② 108→110 **三处**（22:01:47）」。我数现盘为 **四处**（`test_factor_registry.py:289 / :290 / :329 / :377`），且第二步的另一半「85→87 两处」（`:330`、`:400`）**未写**。总数（6 处）对，分步拆分错一。
- **D-3（P3，措辞风险）**：`unchanged_on_purpose[3]` 仍以「backend/tests/** — B2 编码期内未改任何测试。」开头，而同一句紧接着披露的 20:48:59 那次 93→108 正是本批 `in_universe` 触发的。读者扫首句会读到旧口径。建议改为「改过两次（20:48:59 / 22:01:47），只动计数与 golden 追加」。

---

## 二、按证据自己的原命令复跑 —— **PASS（74 passed / 0 failed）**

### 命令（照抄证据 `test_status.command`，cwd = 仓库内 backend）

```
cd C:/work/sourcecode/tick-stock-panel/backend
PYTHONUTF8=1 ./.venv/Scripts/python.exe -m pytest tests/test_factor_dsl.py tests/test_factor_registry.py \
  tests/test_factor_api.py tests/test_factor_store.py tests/test_factor_provider_contracts.py -q
```

### 实测

| 项 | 证据 | 我实测 |
|---|---|---|
| 结果 | 74 passed, 1 warning in 8.75s（22:03:37） | **74 passed, 1 warning in 7.35s** |
| 退出码 | 0 | **PYTEST_EXIT=0** |
| Python | 3.11.15 | **3.11.15** |
| pytest | 9.2.0 | **9.2.0** |
| 复跑第二次 | — | 74 passed in 6.56s，exit 0 |

**与 74 相符，无差异。** 另外 `tests/test_factor_gate.py` 在我仓内工作区单独跑：**56 passed, 1 warning in 2.29s，EXIT=0**（与证据 `gate_suite.result` 一致）。

---

## 三、干净检出 6 红（B-1b）现在的状态 —— **PASS（但结论形态已变，须改写）**

### 证据里的 `checkout_probe` 到底做了什么

是真做了，不是声称：`git checkout-index -a --prefix=<临时空目录>` 导出**索引内容**（16 个 staged 文件，含 3 个 pack 目录共 9 个文件 + `gate.py` + `test_factor_gate.py` + `factors.py`/`dsl.py`/`store.py`/两个测试文件），在导出树的 `backend/` 下用同一个 `backend/.venv` 跑 pytest。`index_state`：`committed=false`、`pushed=false`、`staged_count=16`。

**我自己重做了一遍**（不用它的脚本，`/tmp/idxprobe`）：

| 步骤 | 命令 | 我的实测 | 退出码 |
|---|---|---|---|
| 导出索引 | `git checkout-index -a --prefix=/tmp/idxprobe/` | 2,057 个文件；`docs/architecture/evidence` **不存在** | 0 |
| 确认导入来源 | `python -c "import app;print(app.__file__)"` | `…\Temp\idxprobe\backend\app\__init__.py`（确实从导出树导入，不是工作区） | 0 |
| 五文件套件 | 同 §二 | **74 passed, 1 warning in 8.85s** | **0** |
| 门禁套件 | `pytest tests/test_factor_gate.py -q` | **4 failed, 52 passed in 3.76s** | **1** |
| 补一份产物后 | `cp docs/architecture/evidence/referenced_factor_inventory.json <导出树>/同路径` | **56 passed in 2.49s** | **0** |

4 条红的 test id 与证据**逐字相同**：`test_live_config_allowlist_shape_matches_the_artifact`、`…_reads_only_the_inventory_json`、`…_fails_closed_on_summary_mismatch`、`test_live_config_ids_are_all_known_and_never_blocked_as_columns`。

### 翻转原因我也独立复现了

把导出树里那两个测试文件换回 HEAD 版本（= 22:28 那次「pack 已 add、tests 未 staged」的状态）再跑：

```
6 failed, 68 passed, 1 warning in 8.19s      EXIT=1
FAILED test_factor_registry.py::test_factor_columns_snapshot / test_catalog_counts_and_kinds /
       test_asset_type_filter / test_factors_api_contract / test_factors_api_asset_filter_and_validation
FAILED test_factor_store.py::test_custom_factor_definition_roundtrip
```

**与 B-1b 原判的 6 红、6 个 test id 完全一致。** 所以「6 红」的机制被证实为真：**索引里 pack 已 110、索引里 tests 仍押 93**；tests 一进索引即绿。

### 这条判据现在应改成什么结论

- 原结论「**干净检出 = 6 红**」对**五文件套件**已被索引态**关闭**：0 红（74/0）。
- 但「**干净检出全绿**」**未达成**：把 16 个 staged 文件原样提交后做干净检出，**门禁套件仍 4 红**，唯一原因是 `docs/architecture/evidence/referenced_factor_inventory.json` 未跟踪（`docs/architecture/` 整个是 `??`），导出树里没有 → 4 条 allowlist 用例 `FileNotFoundError`。补这一份 json 即 56 passed，索引未动。
- 故 B-1b 应改写为：**「干净检出：五文件套件 0 红；门禁套件 4 红，成因是交付面缺口（docs 产物未入库），非代码缺陷」**。
- 另需注意措辞：`checkout_probe` 问的是「**按索引检出**」，不是「HEAD 克隆」。它证明的是「这 16 个文件若这样提交，索引树是什么状态」，不等于「已提交的交付物干净检出全绿」。
- **D-4（P3）**：`gate_suite.remedy_proven` 说须把该产物「**及其 .sha256**」一并纳入索引。我实测**只要 .json 即 56 passed**（`.sha256` 侧车 99 B 存在但测试不需要）。建议删掉「及其 .sha256」，否则会给交付面增加无谓的入库项。

---

## 四、边界复核 —— **PASS**

| 检查项 | 声称 | 实测 | 判定 |
|---|---|---|---|
| `backend/app/factors/dsl.py` bytes / sha256 | 36,785 / `49f3a110…` | **36,785 B / `49f3a1106095ad0cf4a6c1cb8ccde42283957756f89ac1f226bf1624fea0c78b`** | ✅ |
| dsl.py mtime | 22:11:19（内容未变） | **22:11:19**（sha 与证据一致，内容确未变） | ✅ |
| `len(OPERATORS)` | 29 | **29**（含 `xs_rank_pool` / `xs_rank_market` / `xs_rank_pct` / `xs_mean`） | ✅ |
| `CROSS_OPERATORS` | 3 | **3 = {rank, winsorize, zscore}** | ✅ |
| `E017` / `MASK_FACTOR_TAG` | 在 | **均在** | ✅ |
| `gate.py` bytes / sha | 25,829 / `39a9d9cf…` | **25,829 B / `39a9d9cf3a17f1a6…`** | ✅ |
| `gate.py` 零生产调用方 | 只有 gate.py 与 test 提到 `assert_factors_usable` | **全仓 `assert_factors_usable` 只在 `backend/app/factors/gate.py:435`（定义 + docstring 2 处）与 `backend/tests/test_factor_gate.py`（7 处，含 helper）；`backend/app/**` 无任何 `from app.factors.gate` / `import gate`；其余 grep 命中全是 `api_gateway` / `data_sync_gate` / `mining_gate` 等无关同名** | ✅ |

命令：`stat`/`sha256sum`/`grep -rn`（exit 0）、`python -c "from app.factors import dsl; print(len(dsl.OPERATORS), …)"`（exit 0）。

---

## 五、附带的独立核验（非四问，但影响「能否收」）

1. **49 条断言 = 48 PASS / 1 INFO / 0 FAIL**：我自己重算 `Counter` 一致，`id` 无重复。✅
2. **31 个被引用的证据产物**（`path`+`sha256`+`bytes` 三元组）**全部存在、sha 全部命中、size 全部命中**（total=31 / ok=31 / mismatch=0 / missing=0）。✅
3. **证据 JSON 的确定性**：文件 = `json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=False)` 再把 `\n` 换 `\r\n`，**逐字节相等**；顶层无 `generated_at`。→ 内容不含时间戳 + 序列化配方固定 ⇒ 「两次重建 sha 相同」**由构造保证**（我未实跑其生成器）。
4. **生产目录零改动**：`D:/TSP/data/user_data/custom_factors` 15 个 json，跑前跑后 `sha256+size+mtime_ns` 三项全同（`identical=True`）。

### 本项缺陷（新增，属证据可追溯性）

- **D-1（P2，追溯指针错）**：`test_status.isolation.states[]` 四条 `artifact` 路径指向的是 **21:37–21:38 的 108 口径**旧文件，不是 `measured_at=22:04:54` 那轮：
  - `b0_only` → `logs/catalog_support_b0_only.json`（该文件 `catalog_size=107`，而声称 109）
  - `all_on` → `logs/catalog_support_all_on.json`（该文件 `catalog_size=108`，而声称 110）
  - `calendar_only` → `logs/catalog_support_calendar_only.json` — **该文件根本不存在**（盘上只有 `catalog_support_calendar_only_110.json`）
  - `none` → 数值碰巧一致（93/79/14），属侥幸
  实质数据没丢：`isolation.artifact` = `logs/isolation_recheck_110.json`（17,559 B，sha `e4eb2c6d…` 已核）里完整含 93/95/109/110、74/0、6/68×3 与同一 6 条红 id。但**照 `states[].artifact` 去核会把 107 当 109、108 当 110，或直接读不到文件**。修法：4 条路径改指 `*_110.json`。

---

## 六、仍不可复现的条目（诚实清单）

| # | 条目 | 状态 |
|---|---|---|
| 1 | `test_status.isolation` 四态（93/95/109/110）实跑 | **未复跑**（需把 3 个 pack 目录 mv 出 `app/custom`，属改工作区）；只核了 `isolation_recheck_110.json` 存在与 sha，并读了其中数字 |
| 2 | `matrix_catalog_test_per_state`（19:47–19:54 的 `ValueError: 缺少必需列 ['raw_close']` / `unsupported matrix feature: prior_amount_20`） | **未复跑**；该路径属矩阵口径、归 B0b，且需改目录态 |
| 3 | 49 条断言背后的原始脚本（`verify_e3.py` / `e2_*.py` / `window` / `wiring` / `id_refs` / `evidence_build.py`） | **未重跑**（会覆盖 logs 证据）；只做了 31/31 哈希核验 |
| 4 | 「两次重建 sha 相同（`d4815e2b…` ×2）」 | **未实跑生成器**；以「文件 = canonical dump 逐字节重建成功 + 无 `generated_at`」间接证明必然确定 |
| 5 | 22:01:47 那次测试更新由 B4 日历包触发 | 只验最终自洽（110 = 93+15+2、87 = 70+15+2）；**未核 B4 交付面** |
| 6 | 门禁 4 红在真实提交后的 CI 首跑 | **未验证**（未提交、无 CI）；「提交 16 文件 + 不带 docs 产物 ⇒ 4 红」是按索引检出推得，不是 CI 实测 |

---

## 七、收下 / 退回

**收下（PASS 可收）。** 四条判据全过：披露补齐（且比要求更完整）、原命令复现 74/0、`checkout_probe` 真做了且我独立复现 74/0 + 4/52 + 补产物 56/0、边界四项与 `OPERATORS 29 / CROSS 3` 未破。B-1b 的 6 红机制也被我独立复现，不再是「声称的结论」。

同时须随收下记账、但不阻断：

| 编号 | 级别 | 内容 | 处置 |
|---|---|---|---|
| D-1 | **P2** | `isolation.states[].artifact` 四条指针指向 108 口径旧文件，其中一条文件不存在 | 改指 `*_110.json`，重出证据 |
| D-2 | P3 | 「108→110 三处」应为四处，漏写「85→87 两处」 | 改数字 |
| D-3 | P3 | `unchanged_on_purpose[3]` 首句仍像「本批未改测试」 | 改写首句 |
| D-4 | P3 | 门禁补产物只需 `.json`，不需「及其 `.sha256`」 | 删该括注 |

**交付面另记一笔（不属证据包缺陷，属待裁定）**：干净检出「全绿」未达成——门禁套件 4 红，唯一成因是 `docs/architecture/evidence/referenced_factor_inventory.json` 未入索引。要么把该产物（及其生成方式）纳入提交范围，要么让门禁用例在产物缺失时降级为 skip（后者会弱化 fail-closed，不建议）。此裁定在开发经理。
