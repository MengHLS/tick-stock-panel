# 工作树交付清单（WORKTREE_SHIP_MANIFEST_20261107）· **v4.1**

> **本清单是「交付面证据」，不是提交动作。** 采集方式：`git status --porcelain -z` + 逐文件 `open(...,"rb")` 后 `hashlib.sha256` 与 `os.stat().st_mtime`，并逐个与 `HEAD:<path>` blob 逐字节比对。**本人未做任何 git 写操作**：未 add、未 restore、未 commit、未 stash、未 checkout；唯一写动作是本文件与同名 `.json`。

> **v4 为什么存在：v3 落盘（23:25:13）之后的 12 分钟里，交付面被彻底改写。** 23:30:21 `.git/index` 被更新，`research/` 下 630 个文件一次性进入暂存区；随后 `MengHLS` 连做四笔提交 `0542bef4`(23:32:19) / `6eda98bb`(23:32:34) / `42ac6b17`(23:36:17) / `286c1c86`(23:55:49)。v3 写的「A=0 / HEAD=`200238ec`」在落盘 5 分钟后即失效。**本版按盘上重测。**

| 项 | 值 |
| --- | --- |
| 本版采集时刻 | **2026-11-08 00:14:49（Asia/Shanghai）** |
| 上一版（v3） | 23:25:02 采集 / 23:25:13 落盘（20,587 B / 266 行 / `8f5f10b7…`）：记「A 0、M 19、?? 34、HEAD `200238ec`、15 个 / 611,945 B」—— 五项全部失效 |
| 仓库 / 分支 | `C:/work/sourcecode/tick-stock-panel` / `dev` |
| **HEAD** | **`286c1c862631042a2e9a43c57e9762c122e21f7f`** |
| `git status --porcelain` | **19 行**：`A` **0** / `M `（已暂存修改）**0** / ` M`（未暂存修改）**7** / `??` **12**；`--untracked-files=all` 展开 **19 行** |
| `.git/index` mtime | **2026-11-07 23:58:38** |
| 登记范围 | `backend/` + `docs/` 下**未提交**的 7 个（未暂存修改 4 + 未跟踪 3），不含本清单两份（§8） |
| 登记总体积 | **534,733 B** = 修改 4 个 **209,075 B** + 未跟踪 3 个 **325,658 B** |
| 已入库 | 11 个原 A + 5 个原 M **全部在 HEAD 内**，工作区 CLEAN（§2、§3） |

## 0 本版对 v3 的五处改写（逐条给证据）

| # | v3 写的 | 盘上现在是什么 | 证据 |
| ---: | --- | --- | --- |
| 1 | `HEAD` = `200238ec` | `HEAD` = `286c1c86`（较 v3 新增 4 笔：`0542bef4`/`6eda98bb`/`42ac6b17`/`286c1c86`） | `git rev-parse HEAD`、`git log -8` |
| 2 | `A` = 0 | 采集时 `A` = **0**（23:30:21 批量暂存，全部在 `research/`；`backend/`+`docs/` 的 A 为 **0** 个） | `git status --porcelain -z` 逐条计数 |
| 3 | ` M` = 19 | ` M` = **7**（其中 `backend/`+`docs/` 的 4 个） | 同上 |
| 4 | `??` = 34 | `??` = **12**（`research/` 已被批量暂存，`??` 只剩零散文件） | 同上 |
| 5 | 登记 15 个 / 611,945 B | 登记 **7 个 / 534,733 B** | §5 |

## 1 `git status --porcelain` 现状

```text
行数 19 = A 0 + "M " 0 + " M" 7 + "??" 12
展开（--untracked-files=all）19 行
.git/index mtime 2026-11-07 23:58:38
HEAD 286c1c862631042a2e9a43c57e9762c122e21f7f
```

### 1.1 `A`（已暂存新增）**0 个** —— 暂存区当前为空

| 项 | 值 |
| --- | --- |
| 数量 | **0** |
| 分布 | 无 `A` 行；`backend/` 与 `docs/` 的 `A` 为 **0** 个。23:30:21 批量暂存的 `research/` 630 个已由 `6eda98bb` 整批入库（§6） |
| 触发 | `.git/index` mtime **2026-11-07 23:58:38**（采集前最后一次索引写入）；此后 `A` 行恒为 0 |
| 性质 | **暂存 ≠ 提交**：未产生任何版本，可 `git reset` 全额退回；本人未参与该操作 |

> **纪律（裁定原文，见 §9）**：未经开发经理书面同意，任何人不得 `git commit`。此纪律在 23:32 起已被 `MengHLS` 的 **4 笔提交**绕开（`0542bef4` / `6eda98bb` / `42ac6b17` / `286c1c86`，见 §9 C4），**现况必须按已发生记录，而不是按应当发生**。

## 2 原「已暂存 A」11 个 —— **现已入库**，逐个指纹 + 与 HEAD blob 比对

> **brief 第 1 项的落点。** 11 个文件全部已在 HEAD 内，`git status` 里没有它们的任何行（A/CLEAN）。**但 brief 的「已暂存、未提交」这一状态描述已不成立**：`79bd04ee`(22:59:50) 引入其中 8 个，`0542bef4`(23:32:19) 又覆盖了其中 3 个。

| # | 文件 | 字节 | 全文 sha256（盘上） | mtime | 盘上 vs HEAD blob | 最后修改提交 | 引入提交 |
| ---: | --- | ---: | --- | --- | --- | --- | --- |
| 1 | `backend/app/custom/research_calendar_pack/__init__.py` | 502 | `00b36dbd40739a324550049725afffc932c60d4f265db3f38f3bc1ea640a0017` | 2026-11-07 21:57:34 | BYTE_EQUAL | `79bd04ee|2026-11-07 22:59:50|dev-manager` | `79bd04ee|2026-11-07 22:59:50|dev-manager` |
| 2 | `backend/app/custom/research_calendar_pack/calendar_axis.py` | 7,943 | `1c865c209ae4fc0072d44a825771b3e94dfd32527231579e17bcb78a9afe8a83` | 2026-11-07 21:57:34 | BYTE_EQUAL | `79bd04ee|2026-11-07 22:59:50|dev-manager` | `79bd04ee|2026-11-07 22:59:50|dev-manager` |
| 3 | `backend/app/custom/research_calendar_pack/factor_provider.py` | 4,829 | `60bc50644634ebc3a9a9545f72063e9e90c0695d1829ea3fdde0a8a11dbd4649` | 2026-11-07 21:57:34 | BYTE_EQUAL | `79bd04ee|2026-11-07 22:59:50|dev-manager` | `79bd04ee|2026-11-07 22:59:50|dev-manager` |
| 4 | `backend/app/custom/research_factor_pack/__init__.py` | 272 | `29a156cdfa78aa4985a4900edec4f1786e17ad62fed73a3fd14f8bbfffe95902` | 2026-11-07 14:33:08 | CRLF_ONLY | `79bd04ee|2026-11-07 22:59:50|dev-manager` | `79bd04ee|2026-11-07 22:59:50|dev-manager` |
| 5 | `backend/app/custom/research_factor_pack/factor_provider.py` | 4,553 | `7ea31aadbb54453790b45af04db90075cbca73d58259eb81436f19b0a1687b0a` | 2026-11-07 14:34:01 | CRLF_ONLY | `79bd04ee|2026-11-07 22:59:50|dev-manager` | `79bd04ee|2026-11-07 22:59:50|dev-manager` |
| 6 | `backend/app/custom/research_factor_pack/factor_specs.py` | 5,284 | `a7e71b399b72dc7c66722d25d2c4e49c222f8d20b857eac4e56de8802d274ed6` | 2026-11-07 23:08:47 | CRLF_ONLY | `0542bef4|2026-11-07 23:32:19|MengHLS` | `79bd04ee|2026-11-07 22:59:50|dev-manager` |
| 7 | `backend/app/custom/research_universe_pack/__init__.py` | 371 | `b2b210631907ab92635fd7848a5f4ea8b1ddde621c7a9101a9b71d4bed180653` | 2026-11-07 18:48:21 | BYTE_EQUAL | `79bd04ee|2026-11-07 22:59:50|dev-manager` | `79bd04ee|2026-11-07 22:59:50|dev-manager` |
| 8 | `backend/app/custom/research_universe_pack/factor_provider.py` | 4,894 | `90dbc6ca46f3f5b892f9a9fba0b49d8169596c40ce68d2e2130bbe99a21f69e8` | 2026-11-07 18:50:42 | BYTE_EQUAL | `79bd04ee|2026-11-07 22:59:50|dev-manager` | `79bd04ee|2026-11-07 22:59:50|dev-manager` |
| 9 | `backend/app/custom/research_universe_pack/universe.py` | 11,957 | `c45d0bcc26c730e0cdcd399581e1e91b2a7e231b8fbaab0e1cc3ad88841cf06d` | 2026-11-07 18:54:36 | CRLF_ONLY | `79bd04ee|2026-11-07 22:59:50|dev-manager` | `79bd04ee|2026-11-07 22:59:50|dev-manager` |
| 10 | `backend/app/factors/gate.py` | 27,570 | `39068c37a58321251dd4e9d8f87be5bd8eb9bf3e583ceeb053a1909bceaf1ecc` | 2026-11-07 23:08:35 | CRLF_ONLY | `0542bef4|2026-11-07 23:32:19|MengHLS` | `79bd04ee|2026-11-07 22:59:50|dev-manager` |
| 11 | `backend/tests/test_factor_gate.py` | 25,329 | `de1dbb986ec1baa10254bb91cb462afeb73614dabb1969db208379c991750ecd` | 2026-11-07 23:11:07 | CRLF_ONLY | `0542bef4|2026-11-07 23:32:19|MengHLS` | `79bd04ee|2026-11-07 22:59:50|dev-manager` |

### 2.1 逐条说明

- **`BYTE_EQUAL`（5 个）**：盘上字节与 `HEAD` blob 完全相同。
- **`CRLF_ONLY`（6 个）**：仓库 `core.autocrlf=true`，blob 内是 LF、盘上是 CRLF；去掉 CRLF 后逐字节相同，**不是内容差异**（复核代码见 §7）。**v3 曾把后 3 个判为 `DIFF`，那是它们当时确实落后于盘上；现已被 `0542bef4` 入库，判据改为 CRLF_ONLY。**
- **HEAD blob 字节均比盘上小等于行数**：正是每行少一个 `
`，与 `CRLF_ONLY` 自洽。

### 2.2 新增文件的落盘时刻（brief 第 1 项要求）

| 文件 | brief 给的入库版 | 现在盘上 | 落盘时刻 |
| --- | --- | --- | --- |
| `research_calendar_pack/__init__.py` | — | 502 B / `00b36dbd…` | **21:57:34** |
| `research_calendar_pack/calendar_axis.py` | — | 7,943 B / `1c865c20…` | **21:57:34** |
| `research_calendar_pack/factor_provider.py` | — | 4,829 B / `60bc5064…` | **21:57:34** |
| `backend/app/factors/gate.py` | 25,829 B / `39a9d9cf…` / 21:40:12 | **27,570 B / `39068c37…` / 23:08:35** | **21:40:12**（初版）/ 23:08:35（现版） |
| `backend/tests/test_factor_gate.py` | 18,056 B / `84591d2a…` | **25,329 B / `de1dbb98…` / 23:11:07** | **21:40:32**（初版）/ 23:11:07（现版） |

> **brief 的 `gate.py` 25,829 B / `39a9d9cf…` / 21:40:12 完全正确**，那是 21:40 的初版、也是 `79bd04ee` 入库的版本。盘上现在已是 27,570 B / `39068c37…`（23:08:35，经 `0542bef4` 入库）。**两版都记，引用时必须写明哪一版。**

## 3 原「已修改 M」5 个 —— 同样已入库，重测指纹

| 文件 | 字节 | 全文 sha256 | mtime | 盘上 vs HEAD blob | 最后修改提交 |
| --- | ---: | --- | --- | --- | --- |
| `backend/app/api/factors.py` | 24,629 | `b17228b3dcdfab26be21057c262ce43919a8f2d0904adf6addfb43d13e274ac0` | 2026-11-07 16:33:57 | CRLF_ONLY | `79bd04ee|2026-11-07 22:59:50|dev-manager` |
| `backend/app/factors/dsl.py` | 36,785 | `49f3a1106095ad0cf4a6c1cb8ccde42283957756f89ac1f226bf1624fea0c78b` | 2026-11-07 22:11:19 | CRLF_ONLY | `79bd04ee|2026-11-07 22:59:50|dev-manager` |
| `backend/app/factors/store.py` | 21,104 | `f6f3ffa82758e25aa025785a442e674a9cca761661583969c2c47c94306e3f88` | 2026-11-07 23:08:05 | CRLF_ONLY | `0542bef4|2026-11-07 23:32:19|MengHLS` |
| `backend/tests/test_factor_registry.py` | 28,187 | `81e4b1f9803642e77281249cfa0f3a8ec46e30008d7b91144aa545a5b5c2507d` | 2026-11-07 22:01:47 | CRLF_ONLY | `79bd04ee|2026-11-07 22:59:50|dev-manager` |
| `backend/tests/test_factor_store.py` | 6,793 | `79de1eca6cc65522e8ed83b51c6dbb5c9fc74637faa1ac817b561dcc81a7dd9e` | 2026-11-07 22:01:47 | CRLF_ONLY | `79bd04ee|2026-11-07 22:59:50|dev-manager` |

### 3.1 `dsl.py` 注记（brief 第 2 项，照写 + 补实测）

- 全文 sha256 = **`49f3a1106095ad0cf4a6c1cb8ccde42283957756f89ac1f226bf1624fea0c78b`**（与 brief 的 `49f3a110…` 一致），size = **36,785 B**，**mtime = 2026-11-07 22:11:19**。
- **凡引用 `dsl.py`，不许拿 mtime 当变更证据**，只认 size + 全文 sha256：今天它被同内容重写刷新过三次（18:37:48 → 21:50:12 → 22:11:19），而 size 始终 36,785 B、sha 始终 `49f3a110…`。
- **补一条 brief 未提的实测**：`dsl.py` 已随 `79bd04ee` 入库、工作区 `CLEAN`，`git status` 里没有它的行。brief 说它「已修改」，那是 22:4x 之前的事实；且它的 HEAD blob（35,935 B / `5d7fe021…`）与盘上只差 CRLF。

### 3.2 另 4 个现状

| 文件 | 现状 |
| --- | --- |
| `backend/app/api/factors.py` | 24,629 B / `b17228b3…` / 16:33:57，CLEAN，未再改动 |
| `backend/tests/test_factor_registry.py` | 28,187 B / `81e4b1f9…` / 22:01:47，CLEAN；期望值 108 → **110** 已入库 |
| `backend/tests/test_factor_store.py` | 6,793 B / `79de1eca…` / 22:01:47，CLEAN；`builtin_count` 108 → **110** |
| `backend/app/factors/store.py` | 21,104 B / `f6f3ffa8…` / 23:08:05，CLEAN；由 `0542bef4` 入库 |

## 4 干净检出（clean checkout）—— 实测，含**未通过项**

方法：`git archive <commit> | tar -x -C C:/tmp/clean_h3`，在副本里用仓库 `.venv` 跑测试。**不改工作树、不移动目录、不碰他人文件。**

| 项 | 结果 |
| --- | --- |
| 被测 commit | `6eda98bb`（23:32:34）与 `42ac6b17`（23:36:17），内容上因子面无差异 |
| pack 文件 | **9 个**（`research_calendar_pack` 3 / `research_factor_pack` 3 / `research_universe_pack` 3） |
| `backend/app/factors/gate.py` | **在**（27,570 B） |
| `backend/tests/test_factor_gate.py` | **在**（25,329 B） |
| `backend/tests/test_factor_provider_discovery.py` | **在**（7,759 B，v3 时还是 `??`，已由 `0542bef4` 入库） |
| 因子面 4 文件单跑 | **87 passed, 1 warning**（`test_factor_registry` + `test_factor_store` + `test_factor_gate` + `test_factor_provider_discovery`） |
| 因子面 3 文件单跑 | **80 passed**（`test_factor_registry` + `test_factor_store` + `test_factor_gate`） |
| **全量 `tests/` 跑** | **49 failed, 5113 passed, 16 skipped, 1 xfailed**（479.85s） |

### 4.1 全量跑的失败集中在两处，且**因子面在同一跑里会红**

| 用例文件 | 失败数 |
| --- | ---: |
| `tests/test_paper_execution_extension.py` | 26 |
| `tests/test_factor_registry.py` | 5 |
| `tests/test_assistant_actions.py` | 4 |
| `tests/test_strategy_run_all_parallel.py` | 2 |
| `tests/test_factor_gate.py` | 2 |
| `tests/test_api_strategy_bundle.py` | 2 |
| 其余 9 个文件各 1 | 9 |

**根因实测（不是推断）**：全量跑时 `all_factors()` 只返回 **93**，而用例断言 **110**——3 个研究 pack 贡献的 17 个因子在全量跑里丢了。同样的用例单独跑是 `1 passed`、3 文件跑 `80 passed`。**即：因子注册表被先前跑过的其它测试污染（进程内状态未隔离），不是实现缺因子。**

```text
# 全量跑时的真实断言
assert len(specs) == 110
E   AssertionError: assert 93 == 110
```

> **结论必须这样写，不能用「74/87 passed」概括交付面**：
> 1. v2 §4/§5 的「干净检出必然红、缺 17 个因子」**已不成立**——pack、gate、gate 测试都在 HEAD 里（`B-2` 缺口关闭）。
> 2. 但「干净检出全绿」**同样不成立**：全量 `tests/` 是 **49 failed**，其中因子面 8 个（`test_factor_registry` 5 + `test_factor_gate` 2 + `test_factor_store` 1）。
> 3. 因子面**单独跑全绿**（87 / 80 passed），全量跑变红 ⇒ 这是**测试隔离缺陷（用例顺序污染）**，不是因子实现缺陷。**该判定属实现/审核侧，本清单只登记实测数字与复现命令。**

> **引用限定（他人结论，我不改）**：独立审核 `docs/architecture/AUDIT_R2_20261107.md` 记 **B-3-b**（`extensions/factors.py:209/217` 两处 `except Exception` 只 warning）；`docs/architecture/DELIVERY_SCHEDULE_20261107.md` v7 §2 把 B2 结项写成「**附条件**」并明令 **修完前不得把 passed 数当稳定结论对外引用**。

## 5 `backend/` + `docs/` 下当前未提交文件逐个指纹

### 5.1 未暂存修改 ` M`（4 个）

| 文件 | 字节 | 全文 sha256 | mtime |
| --- | ---: | --- | --- |
| `docs/INDEX_20261107.md` | 62,563 | `83f0fad31908ff7d0fe9665e93b4a42cffb2d02e5ce9fec0ddca065f65690ef3` | 2026-11-07 23:44:34 |
| `docs/architecture/CLAUSE_NAMESPACE_COLLISION_20261107.md` | 24,535 | `8f5560527a5fa233a02f1005c316cc45f8d2c57f881476c6c572a2176e08bdf4` | 2026-11-07 23:06:45 |
| `docs/architecture/CONTRACT_REVISION_R11_20261107.md` | 22,063 | `c8bb82407a026202d462faf89b7ec262798677c553debc87bc2e0da38c5409fa` | 2026-11-07 23:20:35 |
| `docs/research/caliber-decisions-20261107.md` | 99,914 | `be2b1d2ace7222b1069d8ca73893500897150200f1e0f04b1fabfe7ae852c60b` | 2026-11-07 23:15:02 |

### 5.2 未跟踪 `??`（3 个）

| 文件 | 字节 | 全文 sha256 | mtime |
| --- | ---: | --- | --- |
| `docs/architecture/CONTRACT_REVISION_R12_20261107.md` | 24,194 | `a92aa22662e48595e687fb852cd611303cb8031a1d2f0bc8698fb382a37dd06a` | 2026-11-07 23:33:02 |
| `docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.12.md` | 269,092 | `d7df40ffa284d9961e83b9fb074dc4e5263bab9299969b3d0387a020df1c1ce6` | 2026-11-07 23:11:30 |
| `docs/research/AUDIT_R3_20261107.md` | 32,372 | `67d7d87e6ea177ddb21f91c87863e8a7efd86868ab3bbcaa395ba013f396771f` | 2026-11-07 23:34:50 |

### 5.3 未跟踪明细（全域 12 条，含不在登记范围者）

```text
docs/architecture/CONTRACT_REVISION_R12_20261107.md
docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.12.md
docs/research/AUDIT_R3_20261107.md
research/_intake/modes.jpg
research/independent-review-20261107/audit_r3_collision.py
tmp_p8.py
tmp_probe2.py
tmp_probe3.py
tmp_probe4.py
tmp_probe5.py
tmp_probe6.py
tmp_probe7.py
```

## 6 边界与免责

- **本清单不覆盖 `research/`**：该目录下 630 个文件在 23:30:21 被批量暂存、随后整批由 `6eda98bb` 入库，属过程产物，不属交付面。需要时另行出清单。
- **不判断内容对错**：只登记「磁盘上现在是什么字节」。任何 PASS/FAIL 仍需按 `docs/factors/README.md` 的口径写死 size + 全文 sha256 + 读取时间。
- **活文件警告（本版尤其严重）**：本版采集横跨 23:25–00:14，期间仓库被推进 **4 笔提交 + 1 次批量暂存**（`0542bef4` / `6eda98bb` / `42ac6b17` / `286c1c86`，及 23:30:21 的 `research/` 批量暂存）、`git status` 行数在 17–19 间反复跳动、出现并消失过 `tmp_probe2..7.py`、`tmp_p1.md`、`tmp_m3/m4.json` 等临时文件。**本表是 2026-11-08 00:14:49 这一刻的快照**，任何引用都应重新算一次 `sha256`。
- **「已入库」不等于「已验收」**：只陈述「字节在 HEAD 里、单独跑能过」，**不构成任何 PASS 结论**。

## 7 复算方法（任何人可重跑）

```bash
cd C:/work/sourcecode/tick-stock-panel
git status --porcelain                          # 折叠
git status --porcelain -z | tr " " "
" | sed -n "s/^..//p" | grep -c .   # 条目数
git status --porcelain --untracked-files=all    # 展开到文件
git rev-parse HEAD
git log -8 --pretty=format:"%h|%ad|%an|%s" --date=format:"%Y-%m-%d %H:%M:%S"
git cat-file -p HEAD:<path> | wc -c             # HEAD blob 字节
```

```python
# 逐文件 size / sha256 / mtime，并与 HEAD blob 比对（本表口径）
import os, hashlib, subprocess, datetime
ROOT = "C:/work/sourcecode/tick-stock-panel"
for rel in [l.strip() for l in open("filelist.txt", encoding="utf-8") if l.strip()]:
    p = ROOT + "/" + rel
    disk = open(p, "rb").read()
    blob = subprocess.run(["git", "cat-file", "-p", "HEAD:" + rel],
                          cwd=ROOT, capture_output=True).stdout
    if disk == blob:
        same = "BYTE_EQUAL"
    elif disk.replace(b"

", b"
") == blob:   # core.autocrlf=true
        same = "CRLF_ONLY"
    else:
        same = "DIFF"
    print(rel, len(disk), hashlib.sha256(disk).hexdigest(),
          datetime.datetime.fromtimestamp(os.stat(p).st_mtime).strftime("%H:%M:%S"), same)
```

```bash
# 干净检出实测（只读副本，不动工作树）
rm -rf /c/tmp/clean_h3 && mkdir -p /c/tmp/clean_h3
git archive 42ac6b17 | tar -x -C /c/tmp/clean_h3
cd /c/tmp/clean_h3/backend
C:/work/sourcecode/tick-stock-panel/backend/.venv/Scripts/python.exe -m pytest tests/ -q          # 全量
C:/work/sourcecode/tick-stock-panel/backend/.venv/Scripts/python.exe -m pytest\
  tests/test_factor_registry.py tests/test_factor_store.py\
  tests/test_factor_gate.py tests/test_factor_provider_discovery.py -q   # 因子面
```

## 8 本文件自身与计数口径

- 本文件与同名 `.json` **已在 HEAD 内**，当前均处 ` M`（本版改写）。它们**不计入 §5 计数**，避免自我扰动；自身 size / 行数 / sha256 / mtime 由交付回执给出。
- **计数口径**：§5 的 **7 个**（未暂存修改 4 + 未跟踪 3，合计 **534,733 B**）= 「`backend/` + `docs/` 下当前未提交文件、排除本清单两份」。
- **`__pycache__/*.pyc` 不计入**：按目录名排除，本次实测 0 个。
- **与 v3 口径对比**：v3 登记 15 个 / 611,945 B；本版 **7 个 / 534,733 B**（因 `docs/INDEX_20261107.md` 新增为 ` M`，且有 3 个转入 `??`）。
- **`A` 的 630 个不在 §5**：全部在 `research/`，超出本清单登记范围（§6）。

---

登记人：文档管理员（只读采集；只写本文件与同名 `.json`）。**未提交、未部署、未重启、未做任何 git 写操作。**
## 9 开发经理裁定与纪律（照写）· **附冲突标记**

> 本节按开发经理 2026-11-07 22:4x 的交办原样登记其裁定与纪律。**登记人在此不改其结论**；但其立论前提已被盘上事实推翻，按职责另起 §9.2 标记冲突，请责任方裁定。

### 9.1 裁定原文（照写）

**裁定一：保留暂存态，不退回 `??`。**

> 理由：这 11 个文件就是「要交付的那一套」（3 个研究 pack + 闸门 + 闸门测试），退回等于把 B-2「干净检出缺 pack ⇒ 6 红」的缺口重新打开。

**裁定二（纪律）：未经开发经理书面同意，任何人不得 `git commit`。**

> 理由原文：今天全部工作都在工作区，无版本可回放，一次误提交会把未审完的实现钉进历史。

### 9.2 冲突标记（登记人不改裁定，只报事实）

| # | 裁定的前提 | 盘上事实 | 证据 |
| ---: | --- | --- | --- |
| C1 | 「11 个文件还在暂存区、未提交」 | **已不再是暂存态**：11 个全部在 HEAD 内，`git status` 无它们的行 | §2 表；`git log --diff-filter=A -1 -- <文件>` |
| C2 | 「退回 `??` 等于重开 B-2 缺口」 | 缺口已由入库关闭：干净检出含 9 个 pack + `gate.py` + gate 测试，因子面单跑 87 passed | §4 |
| C3 | 「今天全部工作都在工作区，无版本可回放」 | **已有 7 笔提交可回放**：`79bd04ee`/`484f81f3`/`200238ec`（dev-manager 22:59–23:01，3 笔）、`0542bef4`/`6eda98bb`/`42ac6b17`/`286c1c86`（MengHLS 23:32–23:55，4 笔） | `git log -8` |
| C4 | 「任何人不得 commit」 | **纪律已被绕开 4 次**：`0542bef4`@23:32:19、`6eda98bb`@23:32:34、`42ac6b17`@23:36:17、`286c1c86`@23:55:49，作者均为 `MengHLS` | `git log` 的 `%an` 列 |
| C5 | brief：`M 10 / A 11 / ?? 31`、`HEAD 仍 65c6e42f` | 采集时 **`A` 0 / `M ` 0 / ` M` 7 / `??` 12**，`HEAD` = `286c1c86` | §1 |

**请责任方裁定（登记人不代裁）**：

1. 纪律 C4 是否需要一个事后追认或书面说明？4 笔提交已进历史，`git reset` 属改写历史，登记人**不做**。
2. 裁定一的「保留暂存态」已无对象可保——11 个文件在 HEAD 里，不存在「退回 `??`」这一动作了。**建议**把该裁定的目的改述为「`0542bef4` 之前的 `79bd04ee` 版本不得回退」，但这属开发经理的判断。
3. `research/` 630 个文件被整批入库（`6eda98bb`，635 files changed / +221,859），其中含 MB 级中间件已被 `.gitignore` 排除。这是否符合本单「交付面」定义，请开发经理确认。


## 10 复核回执（2026-11-08 00:21:21）· 三方一致，0 漂移

| 复核项 | 结果 |
| --- | --- |
| 复核时刻 | **2026-11-08 00:21:21（Asia/Shanghai）** |
| md 记录行 | **23** |
| json 记录行 | **23**（`former_staged_A` 11 + `former_modified_M_backend` 5 + `modified` 4 + `untracked` 3） |
| md ↔ json ↔ 盘上 | **0 漂移**（逐条比 bytes / sha256 / mtime，复算代码见 §7） |
| 体积算术 | 209,075 + 325,658 = **534,733 B**，与 json `total_bytes` 一致 |
| 计数算术 | 4 + 3 = **7** = json `total_files`（= §5 登记范围） |
| `git status --porcelain` | **19 行** = ` M` 7 + `??` 12；`A` 0 / `M ` 0（与 §1 一致） |
| `HEAD` | `286c1c862631042a2e9a43c57e9762c122e21f7f`（与 §1 一致） |
| `.git/index` mtime | 2026-11-07 23:58:38（与 §1 一致） |
| 采集后漂移 | **无**：00:14:49 采集 → 00:21 复核，`HEAD` / 计数 / 索引 mtime 三项均未变 |

### 10.1 本版（v4.1）相对 v4 的两处改动

| # | 位置 | 改动 | 性质 |
| ---: | --- | --- | --- |
| 1 | §1.1 标题与「分布 / 触发」两行 | v4 写「`A` 0 个 —— 全部在 `research/`」，字面像是「暂存区里躺着 `research/` 的东西」；改为「暂存区当前为空」，并写明那 630 个已由 `6eda98bb` 整批入库 | **措辞校正，未动任何数字** |
| 2 | 新增 §10 | 登记 00:21 的独立复核结果（0 漂移） | 新增证据，不改结论 |
| 3 | §0 引言 / §0 表第 1 行 / §1.1 纪律脚注 / §6 活文件警告 / §9 C3 | **四处内部计数自相矛盾**（引言写「三笔」而 §9 C4 写 4 笔；§6 写「5 笔提交」却只列 4 个 SHA + 1 次暂存；§9 C3 写「6 笔」却列 7 个 SHA；§0 表「新增」漏列 `286c1c86`）→ 按 `git log` 实测量统一为 **4 笔 MengHLS 提交 + 3 笔 dev-manager 提交 = 7 笔** | **同一事实的两处写法对齐，未改任何指纹/数字口径** |

> v4 的 23 条记录与指纹、11 个 `A` 逐条指纹、5 个 `M` 逐条指纹、`dsl.py` 注记、§4 干净检出实测、§9 裁定原文与冲突标记 **一字未改**。

---

复核人：文档管理员（只读采集；只写本文件与同名 `.json`）。**未提交、未部署、未重启、未做任何 git 写操作。**
