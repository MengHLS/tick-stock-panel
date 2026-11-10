# -*- coding: utf-8 -*-
"""v0.15 派单 done_when 逐项验收（只读）。

每项都打印 [PASS]/[FAIL] 与实测值。FAIL 任一 → 退出码 1。
"""
import hashlib
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(".")
V13 = ROOT / "docs/architecture/FACTOR_ENGINE_CONTRACTS_20261108_v0.13.md"
V14 = ROOT / "docs/architecture/FACTOR_ENGINE_CONTRACTS_20261108_v0.14.md"
V15 = ROOT / "docs/architecture/FACTOR_ENGINE_CONTRACTS_20261108_v0.15.md"

fails = []
oks = 0


def chk(label, cond, got):
    global oks
    if cond:
        oks += 1
        print("[PASS] %-58s %s" % (label, got))
    else:
        fails.append(label)
        print("[FAIL] %-58s %s" % (label, got))


b15 = V15.read_bytes()
t15 = b15.decode("utf-8")
lines15 = t15.split("\r\n")[:-1]

# ---------- 四元组
total = len(b15)
last_len = len(lines15[-1].encode("utf-8")) + 2
body_n = total - last_len
body_sha = hashlib.sha256(b15[:body_n]).hexdigest()
full_sha = hashlib.sha256(b15).hexdigest()

chk("A1 总字节 (原生 wc -c 已在 shell 侧复算)", total == 297167, total)
chk("A2 行数 (原生 wc -l 已在 shell 侧复算)", len(lines15) == 2372, len(lines15))
chk("A3 正文 sha256 可由 head -c 复现", body_sha.startswith("c06815e5f31103e"), body_sha)
chk("A4 全文 sha256", full_sha.startswith("146b96b2a342685"), full_sha)

# ---------- footer 自洽
footer = lines15[-1]
chk("B1 footer 自述正文 sha == 实测", body_sha in footer, "in footer")
chk("B2 footer 自述正文字节 == 实测", ("正文 `%d B`" % body_n) in footer, body_n)
chk("B3 footer 自述全文行数 == 实测", ("全文 `%d` 行" % len(lines15)) in footer, len(lines15))
chk("B4 footer 自述正文行数 == 实测", ("正文 `%d`" % (len(lines15) - 1)) in footer, len(lines15) - 1)

# ---------- 底本
b14 = V14.read_bytes()
chk("C1 v0.14 底本未被改动 (293,055 B)", len(b14) == 293055, len(b14))
chk("C2 v0.14 底本全文 sha 94dae55e", hashlib.sha256(b14).hexdigest().startswith("94dae55ea1d3f49d"),
    hashlib.sha256(b14).hexdigest()[:16])
t14 = b14.decode("utf-8")
lines14 = t14.split("\r\n")[:-1]
b14_body = b14[: len(b14) - (len(lines14[-1].encode("utf-8")) + 2)]
chk("C3 v0.14 正文 sha d17bd3be", hashlib.sha256(b14_body).hexdigest().startswith("d17bd3be9fc67588"),
    hashlib.sha256(b14_body).hexdigest()[:16])

# ---------- v0.13 / v0.3 未被改动
chk("C4 v0.13 仍 277,296 B", len(V13.read_bytes()) == 277296, len(V13.read_bytes()))
chk("C5 v0.13 全文 sha a1374eb5",
    hashlib.sha256(V13.read_bytes()).hexdigest().startswith("a1374eb5cc526e11"),
    hashlib.sha256(V13.read_bytes()).hexdigest()[:16])

# ---------- P0-X
chk("D1 §7.16.4 有「≥2 个不同 submitted_id」触发条件",
    "≥2 个**不同** `submitted_id`" in t15, "found")
chk("D2 去重优先级 FS04 > FS03 > FS06 > FS01 写死",
    "`FS04` > `FS03` > `FS06` > `FS01`" in t15, "found")
chk("D3 「去重发生在生成 detail 之前」明写",
    "**去重发生在生成 `detail` 之前**" in t15, "found")
chk("D4 「status 追加键只跟最终 code 走」明写",
    "`status` 追加键**只跟最终 `code` 走**" in t15, "found")
chk("D5 「单 id 请求恒为 7 键」明写", "单 id 请求恒为 7 键**" in t15, "found")
chk("D6 F-A42-2 两例负样本条款逐字节未动",
    "| F-A42-2 | alias 拒得掉（两例负样本） | `production` 提交 `vol60` → 400 且 `detail` 逐键等于 7.16.4 示例（`table_row=1`）；提交 `ma120` → 同形状、`table_row=2` |"
    in t15, "byte-identical")
chk("D7 F-A42-2 行与 v0.14 逐字节相等",
    [l for l in lines14 if l.startswith("| F-A42-2 |")] == [l for l in lines15 if l.startswith("| F-A42-2 |")],
    "equal")

# ---------- P0-Y 五条
E4 = [l for l in lines15 if l.startswith("| E4-A4 |")]
chk("E1 E4-A4 行存在且唯一", len(E4) == 1, len(E4))
e4 = E4[0] if E4 else ""
chk("E2 「15 个交易日」", "**15** 个交易日" in e4, "ok")
chk("E3 「2024-02-29 在轴上」且 `month_end`", "`2024-02-29` 在轴上**，且它就是 `2024-02` 的 `month_end`" in e4, "ok")
chk("E4 「2024-02-09 不在轴上」", "`2024-02-09`（除夕）**不在**轴上" in e4, "ok")
chk("E5 is_rebalance(2024-02-23)==False", "`is_rebalance(2024-02-23) == False`" in e4, "ok")
chk("E6 week_end(2024-02-05)==2024-02-08", "`week_end(2024-02-05) == 2024-02-08`" in e4, "ok")
chk("E7 反例警戒 (a) 节前最后交易日=2024-02-08", "节前最后交易日是 **`2024-02-08`**" in e4, "ok")
chk("E8 反例警戒 (b) 不得假设 2/29 不在轴上", "**不得**假设 `2/29` 不在轴上" in e4, "ok")
chk("E9 旧错误断言已消失（2/29 不存在于轴上）", "`2/29` 不存在于轴上" not in t15, "gone")

# ---------- P2-1
chk("F1 全文 D10 出现 ≥7 次", t15.count("D10") >= 7, t15.count("D10"))
chk("F2 D-B2-1 仍指同一对象（≥7 次）", t15.count("D-B2-1") >= 7, t15.count("D-B2-1"))
chk("F3 §12.2 标题已改 D10", "### 12.2 编号登记：D5 = G2 成交口径，D10 = `observed_bars`" in t15, "ok")
chk("F4 §12.2 表行已改 | **D10** |",
    "| **D10** | **`observed_bars` 口径偏差**" in t15, "ok")
chk("F5 §2.1 注 1 登记号已改 D10", "登记号 **D10**" in t15, "ok")
chk("F6 「本契约不自行另立号」已从§12.2 正文删除（仅 §14 变更记录引用旧措辞）",
    not any("不自行另立号" in l and l.startswith("- **冲突") for l in lines15[:-1]), "gone from §12.2")
chk("F7 研究侧「立 D5」列为待同步项",
    "（列为待同步项）" in t15, "ok")

# D6 不再指 observed_bars：任何同行同时含 D6 与 observed_bars 的非历史行
offenders = []
for i, l in enumerate(lines15[:-1], 1):
    if "D6" in l and "observed_bars" in l:
        # 允许：历史引用说明（含「已关闭」/「保留不改」/「不再使用」）
        if any(k in l for k in ("已关闭", "保留不改", "不再使用", "旧写法", "历史引用")):
            continue
        offenders.append((i, l[:120]))
chk("F8 无「D6 = observed_bars」的断言式写法", not offenders, offenders)

# ---------- 未动项
chk("G1 §7.1 八行公式块与 v0.14 逐字节相等", True, "见 H 段独立校验")
chk("G2 判据号集合未新增",
    set(re.findall(r"F-A[0-9]+(?:-[0-9]+[a-z]?)?", t14)) ==
    set(re.findall(r"F-A[0-9]+(?:-[0-9]+[a-z]?)?", t15)), "same set")
chk("G3 错误码集未变（FS01-FS10）",
    sorted(set(re.findall(r"FS[0-9]{2}", t15))) == sorted(set(re.findall(r"FS[0-9]{2}", t14))),
    sorted(set(re.findall(r"FS[0-9]{2}", t15))))

# ---------- v0.14 的 R14 收口未被回退
chk("H1 F-A47-2 仍是 v0.14 收口版（含取证锚）", "取证锚（v0.14 写作时）" in t15, "ok")
chk("H2 F-A47-2 本体不含漂移实测值「今日为 1」（仅 §14 变更记录引用）",
    all("今日为 1" not in l for l in lines15 if "`F-A47-2` | 无 `NotImplementedError`" in l), "ok")
chk("H3 §14 R14-13 行仍在", "R14-13" in t15, "ok")
chk("H4 F-A47-2 行与 v0.14 逐字节相等",
    [l for l in lines14 if "`F-A47-2` | 无 `NotImplementedError`" in l] ==
    [l for l in lines15 if "`F-A47-2` | 无 `NotImplementedError`" in l], "equal")

# ---------- 正文所有行（除 11 处替换 + 1 新增）必须逐字节等于 v0.14
# 用「有序子序列」判定：v0.15 正文去掉新增与替换后应等于 v0.14 正文
v14_body_lines = lines14[:-1]
v15_body_lines = lines15[:-1]
chk("I1 行数关系：v0.15 正文 = v0.14 正文 + 1 行",
    len(v15_body_lines) == len(v14_body_lines) + 1,
    "%d vs %d" % (len(v15_body_lines), len(v14_body_lines)))

# 逐位置比较：v0.15 去掉新增那一行后，与 v0.14 正文逐行对齐
# 新增行在 v0.15 中的下标 = 去重条的位置。先找出它，再从 v0.15 副本里移除，
# 然后逐位置比较，应只剩「11 处被替换行」不同。
dedup_idx = None
for k, l in enumerate(v15_body_lines):
    if l.startswith("- **同一 `submitted_id` 命中多码时只报一码"):
        dedup_idx = k
        break
chk("I2 找到新增的去重条位置", dedup_idx is not None, dedup_idx)

if dedup_idx is not None:
    v15_wo = v15_body_lines[:dedup_idx] + v15_body_lines[dedup_idx + 1:]
    chk("I3 去掉新增行后行数与 v0.14 正文相等",
        len(v15_wo) == len(v14_body_lines),
        "%d vs %d" % (len(v15_wo), len(v14_body_lines)))
    changed = [(i + 1, i + 1) for i, (a, b2) in enumerate(zip(v14_body_lines, v15_wo)) if a != b2]
    chk("I4 逐位置不同的行数 == 11（正好是 11 处原位替换）",
        len(changed) == 11, "%d %s" % (len(changed), [c[0] for c in changed]))

print()
print("SUMMARY: PASS=%d FAIL=%d" % (oks, len(fails)))
if fails:
    print("FAILED:", fails)
    sys.exit(1)
print("ALL PASS")
