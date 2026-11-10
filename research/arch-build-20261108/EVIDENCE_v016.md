# v0.16 取证与复跑说明（架构师，2026-11-08 04:4x）

对象：`docs/architecture/FACTOR_ENGINE_CONTRACTS_20261108_v0.16.md`
底本：`docs/architecture/FACTOR_ENGINE_CONTRACTS_20261108_v0.15.md`（**未改一字**，297,167 B / `146b96b2a3426853`）

未做：未提交、未改 `backend/**`、未改 `docs/factors/**`、未部署、未重启。

## 一、四元组（原生命令实测，不取脚本自报）

```bash
cd C:/work/sourcecode/tick-stock-panel
F=docs/architecture/FACTOR_ENGINE_CONTRACTS_20261108_v0.16.md
wc -c < "$F"            # 316155
wc -l < "$F"            # 2476
sha256sum "$F"          # 848df9762431e9d432ed047263b7527ae364d6e4ae26512f7b748c4c437a77a9
stat -c '%y' "$F"       # 2026-11-08 04:38:45.831454000 +0800
head -c 313158 "$F" | sha256sum
# d58d90b577af07b427636f6dc28fbfa293eac7f75fd63460bf819edc85ecc9bb  ← 与 footer 自报逐位相同
```

正文 = 全文去掉最后一行 footer（以换行结尾）：`313,158 B` / `2,475` 行 / `d58d90b5…`。

## 二、硬约束复算

```bash
# §7.1 块：LF 2514 / 6d3db013，CRLF 2541 / a8e88134（由 verify_v016.py B1/B2 独立切片重算）
# 且与 v0.15 的同块逐字节相等（B3 byte_equal_to_v015=True）
PYTHONIOENCODING=utf-8 python research/arch-build-20261108/verify_v016.py
```

判据行全量对照（不只看 E1 抽样的 20 行）：

| 项 | v0.15 | v0.16 |
| --- | --- | --- |
| 判据行总数 | 72 | 78 |
| 共有且逐行相等 | 72 | 72（`differing=[]`） |
| 新增 | — | `F-A48-1..4`、`F-A49-1..2` |
| `F-A1`–`F-A47` 缺失或改动 | — | 无 |

## 三、缺口 1（P1）条款与取证

条款位置：§7.16.4，`7 键之上的追加键只有三处` 之后。
唯一算法：`|detail| = 7 + |{status, violations, dual_ids} ∩ 实产键|`，三键成立条件互不重叠：

- `status` ⇔ `code == "FS01"`
- `violations` ⇔ `code != "FS04"` 且 `blocked` 含 ≥2 个不同 `submitted_id`
- `dual_ids` ⇔ `code == "FS04"`（`FS04` 恒优先，出现 `dual_ids` 时永不追加 `violations`）

表内补 4 行组合行：②`FS01`+`violations`=9、③`FS04`+≥2 id=`{dual_ids}`=8、④`FS03/FS06/…`+≥2 id=8、⑤批量入口=8（与④同集合，单列以便对照）。键数取值域 **{7,8,9}**。

```bash
backend/.venv/Scripts/python.exe research/arch-build-20261108/probe_v016_gaps.py   # 真盘 D:/TSP/data
PYTHONIOENCODING=utf-8 python research/arch-build-20261108/repro_v016.py            # 独立复算算法
```

结果：42 次调用（14 组输入 × 3 模式）中 **31 次抛 `GateError` 带 `detail`，算法 31/31 成立**，键数实取 {7,8,9}；另 **11 次 `diagnostic` 放行、不产 `detail`**，键数判据不适用。文档四处口径（修订记录 / §7.16.4 / §15 R16-5 / footer）统一为「42 次调用、31/31」，旧「42/42」零残留（A10 实测 `旧42/42残留=0`）。

`F-A47-4` 的「逐键等于 7 键」对 `FS09` 仍成立（追加键集合恒 `{}`），同处已写明「其余变体按追加键集合判定、不按固定键数」。

## 四、缺口 2（P0）条款与取证

条款位置：§7.7.2（闸门层签名句之后）+ §7.17.5（`F-A48` 4 条、`F-A49` 2 条）。复用 `FS09`，**不新增错误码**（`FS01`–`FS10` 已全占，新开 `FS11` 会与 §7.10.2 `code` 枚举及 §7.17.4 C4 冲突）。

```bash
cd backend
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe /tmp/probe_v016_fa48b.py
```

实测（2026-11-08 04:4x，`D:/TSP/data`）：

| 判据 | 实测 |
| --- | --- |
| `F-A48-1` | `settings.data_dir = D:/TSP/data`；`default_facts_source()._data_dir = D:/TSP/data`；两者相等 → **已过** |
| `F-A48-2` | 8 只 `active` 不传 `facts`，`production`/`research`/`diagnostic` 三模式全 `ok=True` → **已过** |
| `F-A48-3` | `settings.data_dir=None` → 抛 `GateError` `code=FS09`、`keys=7`、`submitted_id='data_dir'` → **已过** |
| `F-A48-4` | ①`data_dir=None` → `FS09`(7 键)；②看得见的空目录 → `FS01`(8 键，带 `status`，`status=None`)。**两码不同** → **已过** |
| `F-A49-1` | `detail.mode` 在 `research`/`diagnostic` 下仍报 `"production"`（保真 1/3）→ **未过，执行归系统开发** |
| `F-A49-2` | 三次 `detail` 恰 7 键、`submitted_id='data_dir'`、其余三键 `None` → **已过** |

`F-A49-1` 是本节唯一点名的未过项，文档 §7.17.5 末段「今天的状态」已如实标注。

## 五、本轮自查发现并修掉的文档缺陷（新）

§7.16.4 组合实测表中 `["no_such_xyz","uf_dist_prior_high_250"]` 的 `diagnostic` 格原写「**通过**（`diagnostic` 放行 `FS01`，只剩 `FS02` → 7）」，与实产不符：该模式下 `FS02` 仍抛错、`detail` 7 键。已改为 `FS02` → **7**（并说明「只剩 `FS02` 一码、`blocked` 只 1 个 id ⇒ 不追加 `violations`」）。

为防止同类「文档表与证据不符」再发生，`verify_v016.py` 新增 **A11**：把文档该表 13 行 × 3 列逐格与 `EVIDENCE_v016.json` 的 `gap1_matrix` 比对。负向测试：注入「`FS01` 9→8」与「回退成『通过』」两处错误，均被抓出。

## 六、幂等性

```bash
python research/arch-build-20261108/build_contract_v016.py >/dev/null && sha256sum docs/architecture/FACTOR_ENGINE_CONTRACTS_20261108_v0.16.md
```

连续两次构建输出同一 `848df976…`，字节数不变。

## 七、校验清单

`verify_v016.py` → **SUMMARY ALL PASS**（A1 A2 B1 B2 B3 A4 E1 E2 A6 A7 A8 A9 A10 A11，共 14 项）。
