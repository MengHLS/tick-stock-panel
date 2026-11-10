# E5 交付：`market_breadth` 注册 + 实际计算验证

日期 2026-11-08 · 系统开发工程师 · 未提交 / 未部署 / 未接线

## 1. 改了什么

| 文件 | 改动 |
| --- | --- |
| `backend/app/custom/research_breadth_pack/`（**新增**） | `__init__.py` / `factor_provider.py` / `breadth.py`；`provider_id="official.research-breadth-pack-e5"`，仅 1 只因子 `market_breadth`，单侧、**无 `uf_` 双胞胎** |
| `backend/tests/test_factor_registry.py` | `== 110` → `== 111` **brief 点名的 4 处**（diff 后行号 `:291`、`:292`、`:331`、`:379`；brief 引的是 diff 前行号 `:289`、`:290`、`:329`、`:377`）+ **连带 2 处** `== 87` → `== 88`（`:332`、`:402`，etf 计数） |
| `backend/tests/test_factor_store.py` | `== 110` → `== 111` **第 5 处**：`:88` `assert len(factor_columns_view()) == 111` —— **brief 只写了 4 处，这是第 5 处**，不改则 `test_factor_store` 留 1 条红 |

登记参数逐项照抄台账 §16.4，**一字未改**：

| 字段 | 值 |
| --- | --- |
| `id` | `market_breadth` |
| `formula_text` | `xs_mean(close > ma60, in_universe)` |
| `warmup_bars` | `120` |
| `dependencies` | `{close, ma60, in_universe}` |
| `strategy_usable` | `true` |
| `alias_of` | `null`（单侧件，不建 `uf_` 双胞胎） |
| `kind` | `custom` |
| 截面约束 | **未加任何截面算子或排名** |

未改：`registry.py` 的 `_CATALOG`、`dsl`、`store`、`matrix.py`、任何消费入口。

## 2. done_when ③ 实测：达成

```
backend/.venv/Scripts/python.exe -m pytest tests/test_factor_registry.py -q
→ 11 passed, 1 warning

backend/.venv/Scripts/python.exe -m pytest tests -k factor -q
→ 466 passed, 4769 deselected, 8 warnings in 90.06s   (exit 0, PYTEST_EXIT=0)

注：本报告初稿的 457 / 129.28s 是加 9 条真盘闸门用例之前的快照；457→466 与其他两份报告同源，不是回归。
```

`all_factors()` 非 `ext_` = **111**（`market_breadth in ids` = True）；`factor_provider_status()["factor_count"]` 33 → **34**，未撞其它常量。

## 3. 台账 §16.5 五条逐条（7 PASS / 1 FAIL）

复跑：`research/e5-breadth-20261108/verify_e5.py`
证据：`research/e5-breadth-20261108/logs/run_final_1.json` / `run_final_2.json`（UTF-8）
```
sha256 4e9c6212b032dd857d902e2e85c6f8d78318c934d1690d5112f339638e97c008  6043 B  (两次连跑相同)
summary {"total": 8, "PASS": 7, "FAIL": 1}   failed ["E5-C6"]
```

> 04:40 那对 `run_C.json` / `run_C2.json` 是**同一份 JSON 的 UTF-16 控制台重定向输出**（10806 B，带 BOM），
> 解析后与 `run_final_1.json` **逐键相等**（规范化 sha 均 `4f4b65d9dfea7318…`）；字节不同仅因编码，
> 不是内容变了。旧文件保留未删。

| 号 | 判据 | 结果 | 实测 |
| --- | --- | --- | --- |
| C1 | 登记参数 | PASS | `warmup_bars=120`、`dependencies={close,in_universe,ma60}`、`alias_of=null`、`strategy_usable=true`、`kind=custom` |
| C2 | `compile_formula` | PASS | `ok=true`、`errors=[]`、`referenced_factors=["market_breadth"]`、`warmup_bars=120` —— **id 作为裸标识符直接编译通过**，不需额外打通「id → DSL 标识符」层 |
| C3 | 目录计数 | PASS | `all_factors=196`、非 `ext_`=**111**、`market_breadth in ids=true`、无 `uf_` 双胞胎、id 唯一 |
| C4 | virtual / pit 不受影响 | PASS | `virtual=61`、`pit=7`、stock 非 ext=111、etf 非 ext=88（均与改前相同） |
| C5 | provider 计数 | PASS | `factor_count=34`、`state=loaded`、`failed_providers=[]`、6 个 provider 全在 |
| C6 | **production 下 0 码** | **FAIL** | `codes=["FS01"]`、`detail.status=null`、`facts_registered=true` → 见 §4 |
| C7 | **实际计算**（非仅登记） | PASS | 与手工复算 `max_abs_diff=0.0`、127 天池非空、逐日广播到全帧（`impl_nunique=1`）、`value_range_ok` |
| C8 | 截面约束未被执行（如实登记） | PASS | `FactorSpec` 无 `semantics` / `cross_sectional` 字段；闸门无此判据 → **PASS 的含义是「如实登记该约束尚未被执行」，不是「约束已被执行」** |

C7 抽样（真盘）：`2026-10-19` manual = impl = `0.2610854913089748`，池内 2,819 只；`2026-10-16` = `0.2618710134656272` / 2,822 只。

## 4. E5-C6：与台账 §17.1 的结构冲突（我不自行消解，报出）

§16.5-3 要求 `assert_factors_usable(["market_breadth"], "production", facts=RegistryFacts(settings.data_dir))` → **0 码**。
实测 `FS01`，根因与 §17.1 已裁定的 6 个单侧件**完全同源**：

1. `status` 只从盘上定义 JSON 读（`gate.py` 不读 `spec.stability`，§7.8.4 末段）。
2. 盘上 id 必须匹配 `^uf_[a-z0-9_]{1,40}$`（`store.py:17`），`market_breadth` 不带 `uf_` → **没有任何合法载体承载 status**。
3. `FactorSpec` 数据类没有 `status` 字段。
4. §16.4 门票明令**不建 `uf_market_breadth` 双胞胎**（会触发 §7.16.6 FS04）。

三条 Release 通道都已被明确禁止：补 `status`（无载体）、建双胞胎（门票禁止）、按 id 开白名单（§17.2 硬约束，要求「必须先回来改本节裁定并在台账留改判依据」，不属于实现批可自主的范围）。

**唯一正解是 G4**（`FactorSpec` 增 `status`，或 provider 注册路径显式给 `status`），即 §17.2 写的正确路径。G4 属架构契约 + 引擎改动，跨批。

所以本节结论是：**§16.5 的 1–4 条中，第 3 条在 G4 落地前不可能成立**；C6 是那一格 FAIL 的实测，不是实现缺陷。本批按 §17.2 拒绝任何形式的例外放行，没有为了把 C6 刷成 PASS 而改闸门、改状态载体或改名。

## 5. 未做的事

不 commit、不 push、不动 `docs/architecture/**`、不动 `matrix.py`、不动 `docs/factors/**`、不跑收益回测。
`gate.py` 的 `_CODE_PRIORITY` 与本 pack 均未接线到任何生产调用点（生产调用点仍为 0）。

## 6. 非我方产物（只登记）

`nul`（不存在）、`backend/tests/test_zz_probe_tmp.py`（源码已不存在，只剩 `__pycache__` 中 .pyc）、`.factor_engineer_batch/`（存在）三项均非我产物，未动、未删、未认领。
