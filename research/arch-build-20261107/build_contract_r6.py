# -*- coding: utf-8 -*-
"""R6 追加块的确定性构建器（只追加，不改 v0.3/v0.4/v0.5）。

默认 --out 指向临时目录（不落 docs/）。用途:
 1) 逐条断言插入锚点唯一（锚点漂移即停）；
 2) 在临时副本上合并，算出合并后的四元组与 +/- diff；
 3) 供 CONTRACT_REVISION_R6_20261107.md 引用其数值。
"""
from __future__ import annotations
import argparse, hashlib, os, subprocess, sys, tempfile

ROOT = r"C:\work\sourcecode\tick-stock-panel"
V05 = os.path.join(ROOT, "docs", "architecture", "FACTOR_ENGINE_CONTRACTS_20261107_v0.5.md")
MARK = "本文件正文 sha256："


def crlf(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\n", "\r\n")


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


A_G21 = crlf("""**G2.1 执行口径必须显式传入（R6 追加；G2 的子条款，不改变 §1 的 G1–G8 条数）**

G2 的原句只定义结果口径（「最早成交在 T+1 开盘」），未约束**调用方如何把口径传进来**；而三处默认值可静默给出相反口径：`MatcherConfig.matching="close_t"`、`entry_price_basis="adjusted"`（`app/backtest/engine.py:229`、`:258`），且 `entry_fill is None` 时 `__post_init__` 回退到 `matching`（`:280-283`）；`META.backtest_defaults.entry_price_basis` 缺省 `"adjusted"`（`app/backtest/execution_policy.py:78`、`:141-144`）。漏传即静默违反 G2，且**不报错、不告警**。故追加硬约束如下。

1. **必须显式传入**：`entry_fill`、`entry_price_basis`、`exit_fill`。缺任一个 → **报错**；禁止回退默认、禁止告警降级、禁止「等于默认值即视为未传」的启发式（显式传 `close_t` 与不传必须可区分）。
2. **判定方式**：`MatcherConfig`（`engine.py:227`）与 `StrategyBacktestConfig`（`backtest/strategy.py:709`）的上述三字段改为 sentinel（`_UNSET`）缺省，`__post_init__` 见到 `_UNSET` 即抛 `G2CaliberError`（不得落到 `matching` 回退分支）。
3. **校验时机**：在**数据加载之前**（构造 cfg 之后、任何 parquet 读取之前），位置与 full 模式的 fail-closed 校验相同（`backtest/strategy.py:1578-1580` 是先例；`engine.py:296` 的 `plan_at_signal_close` 校验是同类先例）。
4. **错误契约**：HTTP 400，`detail = {"code": "FS08", "missing": [<缺失字段名>...], "mode": "position|full|minute", "hint": "<补 META 的具体路径>"}`。`FS08` 在 `FS` 族内递增（`FS01`–`FS07` 已占用），**不占用** DSL 的 `E0xx`。
5. **例外必须显式标记，不得默认**：
   - `mode="full"` 与 `entry_price_basis="raw"` 不相容（`_FULL_UNSUPPORTED_RULES` 已含该字段，`engine.py:341-356`）：拒绝文案须含 `FS08`，**不得**改判为 `adjusted` 续跑。
   - 分钟路径 `_run_minute_backtest` 硬编码 `entry_fill="close_t"`（`strategy.py:2613`）：结果须标 `execution_caliber="minute_t"`，**不得**进入 G2 验收（回测-模拟盘逐日一致率）。
   - legacy 信号回测 `POST /api/backtest/run`（`BacktestRequest.matching="close_t"`，`api/backtest.py:95`）：不在 G2 适用面，结果须标 `g2_exempt=true, reason="legacy_signal_backtest"`；不得被策略/因子回测复用。
6. **迁移属数据变更，不属于代码默认**：为每个策略 `META.backtest_defaults` 显式写 `"entry_price_basis": "raw"`、`"entry_fill": "open_t+1"`。现状实测：`backend/app/strategy/seeds/` 10 个种子**无一**声明 `backtest_defaults`（`grep -rl backtest_defaults backend/app/strategy/seeds | wc -l` → `0`），`D:/TSP/data/user_data` 下无 `strategies` 目录 → 本条款生效后，未补 META 的策略**全部** `FS08`。禁止用代码默认值代偿。

判据 **F-A34**（4 条，可写成 4 个 pytest 用例）

| # | 断言 |
| --- | --- |
| F-A34-1 | 只缺 `entry_fill` → `G2CaliberError`，`detail["code"]=="FS08"` 且 `detail["missing"]==["entry_fill"]` |
| F-A34-2 | 只缺 `entry_price_basis` → 同上，`detail["missing"]==["entry_price_basis"]` |
| F-A34-3 | 两者都显式传入（含显式传 `close_t`+`adjusted`）→ 构造成功；`research` 模式结果标 `g2_override=true`，`production` 模式 400 `FS08` |
| F-A34-4 | 校验发生在读盘之前：monkeypatch 计数 `build_market_data_matrix` 与 `repo.*` 读调用 == 0 |
""")

B_12 = crlf("""### 7.12 矩阵回测路径的能力清单与准入前置（R6 追加）

**7.12.1 现状（实测，2026-11-07）**

14 个研究基线因子（`backend/app/custom/research_factor_pack/factor_specs.py`，A1 9 个 + A2 5 个）在矩阵路径的解析结果：

| # | factor_id | 面板路径 | 矩阵路径 | 机制 |
| --- | --- | --- | --- | --- |
| 1 | `ma20` | 可算 | 可算 | 前缀约定 `name[2:].isdigit()`（`matrix.py:4220`、`:4293`） |
| 2 | `ma60` | 可算 | 可算 | 同上 |
| 3 | `ma120` | 可算 | 可算 | 同上 |
| 4 | `ma200` | 可算 | 可算 | 同上 |
| 5 | `boll_upper` | 可算 | 可算 | `_MATRIX_COMPUTED_FEATURES` |
| 6 | `boll_lower` | 可算 | 可算 | `_MATRIX_COMPUTED_FEATURES` |
| 7 | `sd20` | 可算 | **不可算** | 不在白名单，不匹配任何前缀 |
| 8 | `prior_high_20` | 可算 | **不可算** | 同上 |
| 9 | `prior_low_10` | 可算 | **不可算** | 同上 |
| 10 | `prior_high_55` | 可算 | **不可算** | 同上 |
| 11 | `prior_vol_20` | 可算 | **不可算** | 同上 |
| 12 | `prior_high_250` | 可算 | **不可算** | 同上 |
| 13 | `vol60` | 可算 | **不可算** | 同上（`vol_ma5`/`vol_ma10` 在白名单，`vol60` 不是） |
| 14 | `prior_amount_20` | 可算 | **不可算** | 同上 |

覆盖率 **6/14**；缺的 8 个是：`sd20`、`prior_high_20`、`prior_low_10`、`prior_high_55`、`prior_vol_20`、`prior_high_250`、`vol60`、`prior_amount_20`。

**7.12.2 失败方式与真正的缺陷位置**

8 个缺失因子在 `matrix_feature` 里 fail-closed（`matrix.py:4557` 抛 `ValueError: unsupported matrix feature: <id>`），**不产生静默错值** —— 比「悄悄给 null」好。真正的缺陷有两处：①**抛错时机在回测中途**（评分列物化时，已加载全市场矩阵并算过前序因子）；②`FactorProvider.materialize_matrix_field` 基类**静默** `return None`（`app/extensions/factors.py:86-88`），把「未实现」编码成「无值」，任何新 Provider 都继承这个默认。

**7.12.3 硬要求（字段级）**

1. **准入前置**：策略/因子回测与 X1 计划生成，必须在**消费行情之前**判所引用因子集的 `matrix_supported`；有 false → 400 `FS10`，`detail = {"code":"FS10","factor_id":"<id>","matrix_supported":false,"panel_supported":true}`。禁止把判定留到 `matrix_feature` 中途抛错。
2. **能力来源单一化**：矩阵能力不得由「名字白名单 + 前缀启发式」两套规则共同决定（现有五条：`_MATRIX_COMPUTED_FEATURES` ∪ `startswith("ma"|"ema")` 带 `_bias` ∪ 纯数字后缀 `maN`/`emaN` ∪ `rsi_N` ∪ `momentum_Nd`，`matrix.py:4217-4222`）。改为**一张显式映射表** `MATRIX_KERNELS: dict[str, Callable]`（键 = factor_id，值 = 逐元素 numpy 实现），`matrix_supported(fid) = fid in MATRIX_KERNELS`。
3. **两条路径不得各自长口径**：映射表项与其 `_compute_matrix_feature` 分支一一对应；新增因子只允许「加一个键 + 一个分支」，禁止再扩前缀规则（否则 `vol60` 这类名字永远靠猜）。
4. **锁一致性**：断言 `set(MATRIX_KERNELS) ⊇ RESEARCH_BASELINE_FACTOR_IDS`，且对 14 个 id 全表枚举时 `matrix_supported(fid)` 与「`matrix_feature` 实际可解析」**同真同假**。
5. **8 个缺失因子的数值口径**（与面板逐位/容差一致的唯一写法）：`sd20 = ts_std(close,20)`（ddof=1）；`prior_* = ts_delay(ts_max|ts_min|ts_mean(x,N), 1)`，第 N 根（0-based）为 `null`；`vol60` 的分子**必须**写 `(close - shift(1)) / shift(1)`，**不得**写 `close/shift(1) - 1`（二进制差 1 ULP，实测 1.11e-16、4.6% 行不等，见 `factor_specs.py` 头部注释）；`prior_amount_20` 需矩阵侧存在 `amount` 字段。

判据 **F-A35**

| # | 断言 |
| --- | --- |
| F-A35-1 | 8 个 id 的 `matrix_feature` 不抛异常，返回 `dtype == float32` |
| F-A35-2 | 8 个 id 全过 `F-A11a`/`F-A11b`/`F-A11c`（见 §7.13） |
| F-A35-3 | 用一个**未实现**矩阵核的已注册因子（现状取 `uf_auction_tail_imbalance`）请求 `POST /api/backtest/strategy/run` → 400 `FS10`，且 `build_market_data_matrix` 调用计数 == 0 |
| F-A35-4 | `MATRIX_KERNELS` 与 `RESEARCH_BASELINE_FACTOR_IDS` 的一致性断言通过（§7.12.3-4） |

### 7.13 `F-A11` 判据替换：float32 存储下 `1e-10` 不可达（R6 裁定）

**7.13.1 原判据**（§8.1 判据表，v0.5 `:1267`）：面板路径 vs 矩阵路径逐位 `max_abs_diff < 1e-10`，且 NaN 位置逐个一致。

**7.13.2 不可达的原因（与实现质量无关）**：矩阵字段一律 float32（基础行情 `matrix.py:1005-1009`；财务因子 `fundamentals.py:143-146`，docstring 明写「构建 TxN float32 字段」）。float32 的存储量化下界是 `2^-24·|x|`，任何算法都无法低于它。实测（320 个交易日 × 5,612 只，n = 1,753,345 行，float64 值 → cast float32 → 比差）：

| factor_id | 中位量级 | max abs diff | 相对误差 max |
| --- | ---: | ---: | ---: |
| `sd20` | 0.62 | 2.94e-05 | 5.96e-08 |
| `vol60` | 0.0277 | 7.41e-09 | 5.96e-08 |
| `prior_amount_20` | 1.50e+08 | 2.03e+03 | 5.96e-08 |
| `ma20`（已「覆盖」） | 15.6 | 1.19e-04 | 5.96e-08 |

相对误差 max 每一列都恰好 `5.96e-08`（= `2^-24`），即纯量化、无算法差。**且这是下界**（只算存储舍入，不含 float32 累加）。更要紧：连 6 个「已覆盖」的也过不了 `1e-10`（`ma20` 1.19e-04）→ 按字面 F-A11 是 **14/14 不成立**，不是 8/14。

**7.13.3 裁定：分层判据（替代 `F-A11`，编号 `F-A11a`–`F-A11d`）**

| # | 判据 | 可判定断言 |
| --- | --- | --- |
| **F-A11a** | 结构一致（零容忍） | `np.isnan(a) == np.isnan(b)` 全元素为真；NaN 位置集合对称差为空 |
| **F-A11b** | 数值一致（float32 容差） | 逐元素 `abs(a-b) <= 2**-23 * max(1.0, abs(a), abs(b))`，即 `eps32 = 1.19209290e-07`；报告 `max_rel_diff` / `p99_rel_diff` / 超容差行数（须为 0） |
| **F-A11c** | 决策等价 | 对策略实际引用的每个布尔谓词（如 `close >= prior_high_20`、`vol60 <= 0.10`）：`jaccard >= 0.9999` 且 `abs(only_panel - only_matrix) <= 0.0005 * union` |
| **F-A11d** | 权威路径 | **面板路径（float64）是唯一权威**：台账数值、`F-A10` 对账、研究复核只取面板；矩阵值不得回写台账/证据；矩阵结果必须标 `matrix_path=true` 与 `tolerance="eps32"` |

**7.13.4 为什么这不叫降标准**

`F-A11` 的原始意图是抓「两套实现语义不同」。放宽到相对 `2^-23` 后仍能抓住真正的语义错：若 `prior_high_20` 漏写 `shift(1)`（误写 `rolling_max(high,20)`），实测相对误差 max = **0.6682**、绝对 max = **678**，`close >= prior_high_20` 的 jaccard 掉到 **0.1975**；而 float32 量化对同一谓词的影响实测为 jaccard = **1.0000**、翻转 **0** 行。两类误差差 4 个数量级，判据不会混淆。

**7.13.5 被否决的两个候选**

| 候选 | 代价 | 否决理由 |
| --- | --- | --- |
| 矩阵侧全改 float64 | 每字段 48.1 MB → 96.1 MB（12.0M 格 = 2,141 日 × 5,612 只），20 字段 0.96 GB → 1.92 GB；磁盘缓存上限 512 MB（`matrix.py:66`）被压穿；`dtype=np.float32` 71 处、`float32` 引用 160 处逐个复核；8 个新核按 float64 重验 | 为末位比特付 2 倍内存 + 71 处改动风险 |
| 面板侧 cast 成 float32 再比 | 差异归零 | 判据变成自证；同时摧毁 `F-A10`（对研究侧 float64 的 `1e-10` 锚） |
""")

# B_12 一次承载 §7.12 + §7.13 两节（同一插入点，保持相邻）；B_13 仅为占位。
B_13 = ""

C_ROW = crlf("""| **R6（D5 / 矩阵路径 / `F-A11` 替换）** | 见 `docs/architecture/CONTRACT_REVISION_R6_20261107.md`：①§1 新增 **`G2.1`** 执行口径显式化（`entry_fill`/`entry_price_basis`/`exit_fill` 缺省即 `FS08`，3 条例外，判据 `F-A34`）；②新增 **§7.12** 矩阵路径能力清单与准入前置（6/14，点名 8 个未同步因子，`FS10`，`F-A35`）；③新增 **§7.13** `F-A11` 替换为 `F-A11a`–`F-A11d`（float32 存储下 `1e-10` 不可达，权威路径 = 面板 float64）。三条均为**条款级新增**，不改其余判据语义 |""")

D_ROW = crlf("""| v0.6（R6） | 2026-11-07 | **R6（只追加；不改冻结 v0.3、不改 v0.4 正文、不就地改写 v0.5）**：①§1 插入 `G2.1`（执行口径必须显式传入，缺省即 `FS08`；3 条例外；判据 `F-A34`）；②新增 §7.12（矩阵路径 6/14，点名 8 个未同步因子，准入前置 `FS10`，`F-A35`）；③新增 §7.13（`F-A11` 替换为 `F-A11a`–`F-A11d`，权威路径 = 面板 float64）。逐条原句/新句/实测见 `docs/architecture/CONTRACT_REVISION_R6_20261107.md` | 开发经理 G-A2 开门条件（D5）+ B0b 交付范围（矩阵路径）+ 架构师本机实测（14 个 id 矩阵解析、1.75M 行 float32 量化）|""")

E_TPL = (
    "本文件正文 sha256：`{body_sha}`（校验：`head -c {body_len} \"{name}\" | sha256sum`）· "
    "正文 `{body_len} B` · 行数 `{lines}` · 版本 **v0.6（2026-11-07 R6 追加，未冻结）**· "
    "冻结四元组（size / lines / body-prefix / full sha）见 `docs/architecture/CONTRACT_REVISION_R6_20261107.md` §6（不写进正文，避免自指）· "
    "生成 2026-11-07 v0.6 = v0.5 逐字节为底 + R6 只追加：§1 新增 `G2.1` / 新增 §7.12 矩阵路径能力清单与准入前置 / 新增 §7.13 `F-A11` 替换 / 修订记录与 §9 各 +1 行 · "
    "**v0.4（`FACTOR_ENGINE_CONTRACTS_20261107.md`，128,007 B / 1,226 行 / 正文 `head -c 127043` → `71708877…d16bc` / 全文 `5bd81a74…c5531`）仍为 `F-A5` 绑定对象；"
    "v0.5（138,729 B / 1,298 行 / 全文 `c7740508…c4a21a`）仍为 `F-A30`–`F-A33` 绑定对象** · "
    "v0.3 冻结态（89,833 B / 914 行 / 全文 `5eb97724…565903`）逐字节归档于 `docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md`"
)

G2_ANCHOR = "任何在 T 日使用 T+1 数据的实现，验收直接不通过。"
S8_ANCHOR = "## 8. 改动性质总表（改引擎 / 新增模块 / 现有已够）"
C_ANCHOR = "| 实现与验收 | 分别由系统开发工程师、独立审核工程师承担；**本文件不下验收结论** |"
D_ANCHOR = "| v0.5（追认） | 2026-11-07 |"


def _one(lines: list[str], needle: str) -> int:
    hits = [i for i, ln in enumerate(lines) if needle in ln]
    if len(hits) != 1:
        sys.exit("锚点不唯一/缺失: %r -> %r" % (needle, hits))
    return hits[0]


def merge(raw: str, name: str):
    idx = raw.index(MARK)
    body = raw[:idx]
    lines = body.split("\r\n")
    i = _one(lines, G2_ANCHOR)
    lines[i + 2:i + 2] = A_G21.rstrip("\r\n").split("\r\n") + [""]
    j = _one(lines, S8_ANCHOR)
    lines[j:j] = (B_12 + B_13).rstrip("\r\n").split("\r\n") + [""]
    k = _one(lines, C_ANCHOR)
    lines[k + 1:k + 1] = [C_ROW]
    d = _one(lines, D_ANCHOR)
    lines[d + 1:d + 1] = [D_ROW]
    body_new = "\r\n".join(lines)
    bb = body_new.encode("utf-8")
    footer = crlf(E_TPL.format(body_sha=sha(bb), body_len=len(bb), lines=body_new.count(chr(10)) + 1, name=name)) + chr(13) + chr(10)
    return body_new, footer


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(tempfile.gettempdir(), "v06_candidate.md"))
    args = ap.parse_args()

    raw = open(V05, "rb").read().decode("utf-8")
    name = "docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.6.md"
    body_new, footer = merge(raw, name)
    v06 = (body_new + footer).encode("utf-8")
    bb = body_new.encode("utf-8")
    print("MERGE_BODY_BYTES", len(bb))
    print("MERGE_LINES", body_new.count("\n"))
    print("MERGE_BODY_SHA", sha(bb))
    print("MERGE_BYTES", len(v06))
    print("MERGE_SHA", sha(v06))

    open(args.out, "wb").write(v06)
    r = subprocess.run(["git", "diff", "--no-index", "--numstat", V05, args.out],
                       cwd=ROOT, capture_output=True, text=True)
    print("NUMSTAT", r.stdout.strip())
    print("BLOCK_A_LINES", A_G21.rstrip("\r\n").count("\n") + 1)
    print("BLOCK_AB_LINES", (B_12 + B_13).rstrip("\r\n").count("\n") + 1)
    print("BLOCK_AB_SHA", sha((B_12 + B_13).encode("utf-8")))
    in_temp = os.path.dirname(os.path.abspath(args.out)) == os.path.abspath(tempfile.gettempdir())
    if in_temp:
        os.remove(args.out)
        print("TEMP_REMOVED", args.out)


if __name__ == "__main__":
    main()
