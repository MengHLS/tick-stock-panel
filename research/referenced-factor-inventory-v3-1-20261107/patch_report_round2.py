import io, sys
sys.stdout.reconfigure(encoding='utf-8')
P='research/referenced-factor-inventory-v3-1-20261107/REPORT_v3_1.md'
s=io.open(P,encoding='utf-8').read()

old_git = """`git status --porcelain` 前后对照：`git_status_before_v3_1.txt`（36 行，18:00 开工前）vs `git_status_after_v3_1.txt`（37 行，18:14）。

**唯一新增一行不是本单造成的**：

```
15a16
> ?? research/b2-engine-20261107/
```

该目录 mtime `18:10:03`，内容 `probe_e3.py` + `logs/`（另一条并行工作线在建），与清单返工无关，**未触碰**。除它之外 36 行逐行相同：`backend/app/` 仍是开工前那三个（`M api/factors.py`、`M factors/store.py`、`?? custom/research_factor_pack/`），本单新增的只有 `research/referenced-factor-inventory-v3-1-20261107/` 一个目录。"""

new_git = """`git status --porcelain` 三拍对照（集合差，逐行）：`git_status_before_v3_1.txt`（36 行，18:00 开工前）→ `git_status_after_v3_1.txt`（37 行，18:14）→ `git_status_final_v3_1.txt`（33 行，本报告定稿时）。

**开工前 → 定稿时，只有 5 行变化，全部不是本单造成的：**

```
+ ?? research/b2-engine-20261107/            # 另一条并行工作线在建（18:10:03），未触碰
- ?? research/tmp_cb.txt                     # 他人临时文件，已被其作者删除
- ?? research/tmp_check_before.txt           # 同上
- ?? research/tmp_meta_revision_note.txt     # 同上
- ?? research/tmp_sc.txt                     # 同上
```

`backend/app/` 三拍完全一致，仍是开工前那三项（`M api/factors.py`、`M factors/store.py`、`?? custom/research_factor_pack/`），**没有本单造成的任何改动**；`backend/scripts/build_referenced_factor_inventory.py` 仍是 `??`（未跟踪）。本单新增的只有 `research/referenced-factor-inventory-v3-1-20261107/` 一个目录。"""

assert s.count(old_git)==1
s=s.replace(old_git,new_git)

old_v3 = """| 不覆盖 `research/referenced-factor-inventory-v3-20261107/` 旧报告 | **未覆盖，且目录回到原状**。新报告另开本目录 `REPORT_v3_1.md`；改动前源码快照放在本目录 `build_referenced_factor_inventory.v3.bak.py`（`582c9287…`），v3 目录未留任何新增件 |"""
new_v3 = """| 不覆盖 `research/referenced-factor-inventory-v3-20261107/` 旧报告 | **未覆盖**。目录 17 个文件 mtime 全部停在 `17:25`–`17:28`（本单开工 18:00 之前），`REPORT_v3.md` 未变；新报告另开本目录 `REPORT_v3_1.md`；改动前源码快照放在本目录 `build_referenced_factor_inventory.v3.bak.py`（`582c9287…`） |"""
assert s.count(old_v3)==1
s=s.replace(old_v3,new_v3)

tail_add = """
---

## 12. 报告定稿后的二次复核（同一份落盘产物，未重生成）

本单在写报告之后又把四条独立证据全部重跑一遍，产物与侧车**未被改写**（`referenced_factor_inventory.json` mtime 仍是 `18:05:22` / sha 仍 `b661c8cd…4df4`）：

| 复核 | 命令（`backend\.venv\Scripts\python.exe`） | 结果 |
| --- | --- | --- |
| 自检全项 | `backend/scripts/build_referenced_factor_inventory.py --data-dir D:/TSP/data --out research/.../run_finalcheck.json --quiet` | **40 PASS / 0 FAIL / EXIT=0**（`run_finalcheck.log`）；新跑出的 canonical 与落盘相同 `aefdf528…` |
| §7.12.4 独立复算 | `verify_independent.py` | 一致 `True`；五类扰动行为全符合；EXIT=0 |
| 回源取字面量 | `trace_side_key.py` | 产物 93 条 / 期望表 93 条，不一致 **0**；EXIT=0 |
| `side_key` 非功能性 | `check_sidekey_nonfunctional.py` | 唯一键 218/218 去重 0 重复；改写 `side_key` 后判据字段全等、唯一键集合相同；与 v3 比只 `side_key` 95 条变；EXIT=0 |
| 与期望表 v3.2 比对 | `compare_final_utf8.py` | 表内 22 字段差异 **0**（`side_key` 0/93）；表外仅 `note` 14 条措辞；`side_key` 逐条相等 `True` |

`compare_final_utf8.py` 是重写过的比对脚本（原 `compare_expected_v3_2.py` 在中文 Windows 控制台输出被 GBK 截断，日志 `compare_v3_2.log` 里中文是乱码）：新脚本 `sys.stdout.reconfigure(encoding='utf-8')`，并把「字段缺失」与「值为 null」统一按 `None` 比较，输出 `compare_final_utf8.log`。结论与首轮一致，只是可读。

**给签认方的一条事实**（不在本单范围，但会影响签认）：期望表 v3.2 里的 `signature_triple` 仍指向 `2026-11-07T17:27:45 (184,643 B)` 那批字节的 `184e4728…`；那批字节已被本次产物覆盖（现 `186,343 B` / `aefdf528…`）。按期望表自己写的 `scope_note`（「Any regeneration changes records and therefore the digest; re-sign after each run.」），**需要因子工程师对新字节重签**，本单不代签、不代改 `docs/factors/**`。
"""
s = s.rstrip('\n') + '\n' + tail_add
io.open(P,'w',encoding='utf-8',newline='\n').write(s)
print('written', len(s.encode('utf-8')), 'bytes')
