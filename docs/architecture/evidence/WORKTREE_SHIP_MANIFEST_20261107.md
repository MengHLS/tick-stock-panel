# 工作树交付清单（WORKTREE_SHIP_MANIFEST_20261107）

> **本清单是「交付面证据」，不是提交动作。** 本轮纪律：**不提交、不部署、不重启**。它的用途只有一个——在不提交的前提下，把「哪些文件、什么字节」固定下来，使任何人可以按本表逐个核对后重建。
>
> 采集方式：`git status --porcelain` + 对每个文件 `open(...,'rb')` 后 `hashlib.sha256` 与 `os.stat().st_mtime`（逐字节算，不抄别人的表）。

| 项 | 值 |
| --- | --- |
| 首次采集时刻 | **2026-11-07 21:45:46（Asia/Shanghai）** |
| 复核时刻 | **2026-11-07 21:54（Asia/Shanghai）**：82 条指纹逐条与盘上复算，**80 条逐字节一致**；2 条已重钉 —— `docs/factors/README.md`（本人写入索引，24,895 → 27,854 B）、`docs/factors/B2_IMPLEMENTATION_20261107.md`（他人 21:52:41 改写，18,384 → 20,067 B）。另：`backend/app/factors/dsl.py` 字节未变而 mtime 被刷新（18:37:48 → 21:50:12）；`git status` 44 → 48 行（6 个 pack 文件被暂存），见 §1.3 |
| 仓库 | `C:/work/sourcecode/tick-stock-panel` |
| 分支 / HEAD | `dev` / `65c6e42f1fcd6362e72699afb118bdbcb247b3d3`（`chore(gitignore): ignore local session artifacts`，2026-11-07 12:56:05） |
| `git status --porcelain` | **48 行**（首次采集 44 行；21:53 复核时 48 行）：已修改 `M` **10** / 未跟踪 `??` **32** / **已暂存 `A` 6**（见 §1.3） |
| 本清单登记范围 | `backend/` 与 `docs/` 下的**已修改 5 个 + 未跟踪 77 个文件**（`??` 目录已展开到文件；`__pycache__/*.pyc` **7 个不计入**） |
| 登记文件总体积 | **3,703,214 B**（约 3.53 MiB）＝未跟踪 77 个 **3,587,863 B** ＋ 已修改 5 个 **115,351 B**（首版此行只算了未跟踪那一半，已改正） |
| 未登记 | `research/` 下全部未跟踪与已修改文件（**本轮交付面不含 research/**，见 §6 边界） |

## 1 `git status --porcelain` 全量分组（原文，未改写）

### 1.1 已修改 `M`（10）

```text
 M backend/app/api/factors.py
 M backend/app/factors/dsl.py
 M backend/app/factors/store.py
 M backend/tests/test_factor_registry.py
 M backend/tests/test_factor_store.py
 M research/strategy-search-20261107/REPORT.md
 M research/strategy-search-20261107/results/registry.csv
 M research/strategy-search-20261107/results/registry.json
 M research/strategy-search-20261107/results/registry_table.md
 M research/strategy-search-20261107/scripts/make_report.py
```

### 1.2 未跟踪 `??`（32 条，目录未展开；首次采集为 34 条，其中两个 pack 目录已转为 §1.3 的 `A`）

```text
?? backend/app/custom/research_factor_pack/
?? backend/app/custom/research_universe_pack/
?? backend/app/factors/gate.py
?? backend/scripts/build_referenced_factor_inventory.py
?? backend/tests/test_factor_gate.py
?? docs/INDEX_20261107.md
?? docs/architecture/
?? docs/factors/
?? docs/research/caliber-decisions-20261107.md
?? docs/research/factor-audit-20261107/
?? research/_intake/
?? research/arch-build-20261107/
?? research/b0-correction-20261107/
?? research/b2-engine-20261107/
?? research/e3-data-availability-20261107/
?? research/factor-registration-20261107/
?? research/factor-registration-b2-20261107/
?? research/factor-registration-fa5b-20261107/
?? research/gate-core-20261107/
?? research/independent-review-20261106/_b0report_final.md
?? research/independent-review-20261107/
?? research/jiaogedan-review-20261107/
?? research/mgr-verify-20261107/
?? research/pattern-review-20261107/
?? research/referenced-factor-inventory-20261107/
?? research/referenced-factor-inventory-v3-1-20261107/
?? research/referenced-factor-inventory-v3-20261107/
?? research/strategy-search-20261107/FACTOR_MAP_v1.md
?? research/strategy-search-20261107/RULE-CHANGE-20261107.md
?? research/strategy-search-20261107/factor_map_v1.json
?? research/strategy-search-20261107/results/e2_caliber_check_20261107.json
?? research/strategy-search-20261107/scripts/factor_map_build.py
?? research/tmp_sources.txt
?? research/trade-ledger-20261107/
```

### 1.3 已暂存 `A`（6）—— 复核时新出现，交付面性质变了

```text
A  backend/app/custom/research_factor_pack/__init__.py
A  backend/app/custom/research_factor_pack/factor_provider.py
A  backend/app/custom/research_factor_pack/factor_specs.py
A  backend/app/custom/research_universe_pack/__init__.py
A  backend/app/custom/research_universe_pack/factor_provider.py
A  backend/app/custom/research_universe_pack/universe.py
```

- 采集时刻（21:45:46）这 6 个还是 `??`；**复核时（21:53）已在索引里（`A`）**，字节与 mtime 未变（`__init__.py` 272 B / 14:33:08 … `universe.py` 11,957 B / 18:54:36）。
- **「不提交」仍成立**：`HEAD` 仍是 `65c6e42f1fcd6362e72699afb118bdbcb247b3d3`，`git log --oneline -1` 未见新提交。但**已暂存 ≠ 未跟踪**：此刻任何一次 `git commit` 都会把这两个 pack 带进库，而它们是 §4 判「干净检出缺 pack ⇒ 6 红」的前提。
- 采购面因此分两种读法：① 只看 `??`：pack 仍不在库，B-2 的干净检出结论按原样成立；② 看索引：pack 已在索引，若放行提交则 B-2 自动消解（但会引入未经审核的 pack 入库）。
- **本人未做任何 git 操作**（未 `add`、未 `restore --staged`、未 `commit`）。是否保留暂存，由开发经理裁定并指派执行人。
## 2 `backend/` 下的逐个指纹（已修改 5 个）

| 文件 | 字节 | 全文 sha256 | mtime | `git diff --numstat` |
| --- | ---: | --- | --- | --- |
| `backend/app/api/factors.py` | 24,629 | `b17228b3dcdfab26be21057c262ce43919a8f2d0904adf6addfb43d13e274ac0` | 16:33:57 | 14 / 18 |
| `backend/app/factors/dsl.py` | 36,785 | `49f3a1106095ad0cf4a6c1cb8ccde42283957756f89ac1f226bf1624fea0c78b` | 21:50:12 | 108 / 12；**复核：字节与 sha256 一位不差，但 mtime 由 18:37:48 被刷新到 21:50:12（同内容重写）** |
| `backend/app/factors/store.py` | 19,502 | `de77eae6815adecd5e6f75a97329967752bd6b3fe52208a412a88c5641701199` | 16:33:52 | 187 / 1 |
| `backend/tests/test_factor_registry.py` | 27,642 | `de3ce0ad9e310f2af284d83b96a1eef1575ac3d4023f2eb55ac6b075219f7403` | 20:48:59 | 22 / 6 |
| `backend/tests/test_factor_store.py` | 6,793 | `07cf3dc26288f7e0aa04bd26e997e2f2bf163f8dcc96439a7100912bc84e1df2` | 20:48:59 | 3 / 3 |

其余 5 个 `M` 全在 `research/strategy-search-20261107/`（`REPORT.md`、`results/registry.csv`、`results/registry.json`、`results/registry_table.md`、`scripts/make_report.py`）——**不在本次交付面**，仅按 §1.1 原文登记。

## 3 `backend/` + `docs/` 未跟踪文件逐个指纹（77 个）

### 3.1 研究因子 pack（`research_factor_pack`）（3 个，9,221 B；**复核时已被 `git add`，现为 `A`，见 §1.3**）

| 文件 | 字节 | 全文 sha256 | mtime |
| --- | ---: | --- | --- |
| `backend/app/custom/research_factor_pack/__init__.py` | 272 | `29a156cdfa78aa4985a4900edec4f1786e17ad62fed73a3fd14f8bbfffe95902` | 14:33:08 |
| `backend/app/custom/research_factor_pack/factor_provider.py` | 4,553 | `7ea31aadbb54453790b45af04db90075cbca73d58259eb81436f19b0a1687b0a` | 14:34:01 |
| `backend/app/custom/research_factor_pack/factor_specs.py` | 4,396 | `4411ca96b4c7e4e60556817886b5cce9cde9f026843026054b5f1e923c3ed109` | 14:42:21 |

### 3.2 研究域 pack（`research_universe_pack`）（3 个，17,222 B；**复核时已被 `git add`，现为 `A`，见 §1.3**）

| 文件 | 字节 | 全文 sha256 | mtime |
| --- | ---: | --- | --- |
| `backend/app/custom/research_universe_pack/__init__.py` | 371 | `b2b210631907ab92635fd7848a5f4ea8b1ddde621c7a9101a9b71d4bed180653` | 18:48:21 |
| `backend/app/custom/research_universe_pack/factor_provider.py` | 4,894 | `90dbc6ca46f3f5b892f9a9fba0b49d8169596c40ce68d2e2130bbe99a21f69e8` | 18:50:42 |
| `backend/app/custom/research_universe_pack/universe.py` | 11,957 | `c45d0bcc26c730e0cdcd399581e1e91b2a7e231b8fbaab0e1cc3ad88841cf06d` | 18:54:36 |

### 3.3 闸门与其测试（2 个，43,885 B）

| 文件 | 字节 | 全文 sha256 | mtime |
| --- | ---: | --- | --- |
| `backend/app/factors/gate.py` | 25,829 | `39a9d9cf3a17f1a657400c4eb80a29b1cec474490298614286e6397485d62375` | 21:40:12 |
| `backend/tests/test_factor_gate.py` | 18,056 | `84591d2a32c321d0d305b362543f0e0160c411fdfd9ab805dbe8b0a8c2ba6974` | 21:40:32 |

### 3.4 清单生成脚本（`backend/scripts/`）（1 个，64,975 B）

| 文件 | 字节 | 全文 sha256 | mtime |
| --- | ---: | --- | --- |
| `backend/scripts/build_referenced_factor_inventory.py` | 64,975 | `b96f25a01d4f18d0046dd7dc18be091202b5b266f8a53aef35a6814f8413a45f` | 19:23:04 |

### 3.5 `docs/architecture/`（24 个，1,920,670 B）

| 文件 | 字节 | 全文 sha256 | mtime |
| --- | ---: | --- | --- |
| `docs/architecture/ARCH_DECISION_FACTOR_ID_CANONICAL_20261107.md` | 28,028 | `caa957bffae31fe1caec5298fb85b9d985bee294d4ea6f437ce46469ffb64eab` | 16:55:29 |
| `docs/architecture/B0_ACCEPTANCE_AND_V07_REVIEW_20261107.md` | 28,213 | `6d906751cca1c2da60826706deaa8d3bdf5d9282d86ea9cdeb84e8dd37d2fc38` | 18:40:26 |
| `docs/architecture/B2_ACCEPTANCE_20261107.md` | 18,442 | `bb1a8fa82503ba6cf06f5f01229706edf5cb7dcf87c559825e31e0d9411981b2` | 21:03:36 |
| `docs/architecture/CONTRACT_REVIEW_20261107.md` | 44,221 | `cbea72b24c5483fa088874dd88bb5fd92e65824b52ef15daeb90ee1aa5940553` | 16:38:05 |
| `docs/architecture/CONTRACT_REVISION_R2_20261107.md` | 29,801 | `151d9b2f8d4b4fe2752768566c2f205f569b0998de93f4492abf01aa74dc822e` | 15:51:33 |
| `docs/architecture/CONTRACT_REVISION_R3_20261107.md` | 22,451 | `bfb149fc880d61ab7fd50196ad5b76cb64bdf222b352025961629789f8ee3bde` | 16:19:05 |
| `docs/architecture/CONTRACT_REVISION_R4_20261107.md` | 16,721 | `f2ef6446f33e2b706652864fbd43f33b024b886534c19ffaba062c1fb3a36f9f` | 16:40:16 |
| `docs/architecture/CONTRACT_REVISION_R5_20261107.md` | 17,945 | `a2c0bdd7b89dcab0046714ee9b8fc2df9855152109638e1fc572a9fa48829cfa` | 16:52:39 |
| `docs/architecture/CONTRACT_REVISION_R6_20261107.md` | 11,382 | `1f7b7e5d6e6492fa8511f9928cd396d8f3aa4d0c0710cf3c4826d880f81fee11` | 17:16:36 |
| `docs/architecture/CONTRACT_REVISION_R7_20261107.md` | 50,328 | `8fc0cdbd13f0ad0bf608389c390abfd193fbbadd875c1c40df8716799eea988c` | 18:04:34 |
| `docs/architecture/CONTRACT_REVISION_R8_20261107.md` | 20,119 | `1da9c9182138c2eff5696d4811c9c8b1089fa7ee89bf6a814e93c83b9cf80174` | 21:04:09 |
| `docs/architecture/CONTRACT_REVISION_R9_20261107.md` | 24,466 | `09310c162fdbd567cc904a58a6ff1021ddda98fa31fc159ba7803790148542a2` | 21:39:09 |
| `docs/architecture/DELIVERY_SCHEDULE_20261107.md` | 15,410 | `cff2d789e5384088fbd27e8576ede97d250f5e171bf6df158f63ec4ace43391f` | 21:30:55 |
| `docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md` | 128,007 | `5bd81a7472f10509dd3b000cabcd7ccaa1c1d8faa3a8edd303120edd58ec5531` | 16:40:09 |
| `docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.10.md` | 244,093 | `8a3115aaf0e8c5162e8b5aa15f70affd34e342e3288018dec412cd3e08b5a007` | 21:39:53 |
| `docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.5.md` | 138,729 | `c7740508c358a2c0748aa87fb14c60c8a37f6f721b3f917a7fff7b67c0c4a21a` | 16:52:31 |
| `docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.6.md` | 162,361 | `946a1d8675de6e4e945dc587f65b94ba0ce91922be338774b46b72022a616810` | 17:16:36 |
| `docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.7.md` | 193,586 | `5a87d4b090d996abf28f45cce9f1b5bc6c97c7505371e512b12fe89c1f8723e8` | 18:03:23 |
| `docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.8.md` | 206,608 | `2cf85ccbaaf1fed7e5316bf2c83c73b5193fc02f3aadf3b3e453600aabaedd2f` | 21:04:09 |
| `docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.9.md` | 228,478 | `5d0abbb59636ae9c38929ed04d35899b0a2b11727a99d2c2a84ef601bc8b4b0c` | 21:14:03 |
| `docs/architecture/FACTOR_ENGINE_INTEGRATION_MAP_20261107.md` | 15,006 | `55955ebc13221b1ae96c4cce2e8b00a399b292fd1c0fb8b8aec111553f486eac` | 15:45:18 |
| `docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md` | 89,833 | `5eb9772411f723576b657f85af7c0aa26427137a41fb53b5774b935942565903` | 16:11:32 |
| `docs/architecture/evidence/referenced_factor_inventory.json` | 186,343 | `df5e1a63e98f8834e95517bbdde556a2550bb901d865ba09c1ac7f4040b32e49` | 19:23:57 |
| `docs/architecture/evidence/referenced_factor_inventory.json.sha256` | 99 | `45bd3dbaedf58a26c41b06f0ccb02f4ecc202e37a2d2433780de0cc65fc5f755` | 19:23:57 |

### 3.6 `docs/factors/`（30 个，1,096,994 B）

| 文件 | 字节 | 全文 sha256 | mtime |
| --- | ---: | --- | --- |
| `docs/factors/B2_IMPLEMENTATION_20261107.md` | 20,067 | `c12f016230995a56961f4860a9c4e26d4dd44bdee025c462859417d7e61b2bc4` | 21:52:41 | **复核时正在被改写**（18,384 → 20,067 B），活文件 |
| `docs/factors/E3_DATA_AVAILABILITY_20261107.md` | 14,520 | `7f6f44fd846a911adf025ba32449191fc581cdc870cb6ee32d9d4593181033a1` | 17:27:48 |
| `docs/factors/FACTOR_ENTRY_RULE_20261107.md` | 58,349 | `d19719887b93409807f1b2e618643b148e35c2470032b987d1e0234ad82d15a4` | 18:08:15 |
| `docs/factors/FACTOR_GAP_SPEC_20261107.md` | 35,298 | `092a78461c4fc51304b989f0a06bd82689b34fdeb3ddb2a22d5a1535d889738e` | 17:29:17 |
| `docs/factors/FACTOR_REGISTRY_CORE_93_20261107.md` | 36,306 | `1410bf2944883c38b4d0e096e7c4280bbc57d49e6f629c68ca28c4da87a68f47` | 13:43:53 |
| `docs/factors/F_CLASS_REGISTRATION_20261107.md` | 115,537 | `9f7fc90f51a2d2b1118e70137dc810bfe39dba682876731c1c6f53900de85d0a` | 19:37:46 |
| `docs/factors/README.md` | 27854 | `ddc9610f17544f4b242468d625703bdec6bf4c6d61d2c8b472893740fad20ecd` | 21:55:51 |
| `docs/factors/REGISTRATION_B0_20261107.md` | 20,873 | `d474fcc8a31a595bfbc7bab438e1d3658483e3306af0adfa3b0380286cea802e` | 20:53:26 |
| `docs/factors/STRATEGY_INPUT_FACTOR_MAP_20261107.md` | 17,613 | `09213723d33660d9ed3384d1c31741cb25560b3fdff88b2d43054c0624b04f5c` | 13:49:23 |
| `docs/factors/XS_RANK_POOL_SPEC_20261107.md` | 25,536 | `5cd6ed39f57ae02e555563288befd8eb53047360c1480a30137742b2b26fdd66` | 17:22:17 |
| `docs/factors/evidence/E3_DATA_AVAILABILITY_20261107.md` | 48,555 | `719c78cb00679316f039d3962f4e2c42fdf9534ac6c5034490200e343af539a5` | 15:18:41 |
| `docs/factors/evidence/F_CLASS_PARITY_20261107.json` | 12,007 | `e37071d11f270e40a8a3f182f679f477a99d82465384f9214205a167c96598da` | 15:25:43 |
| `docs/factors/evidence/F_CLASS_PARITY_20261107.md` | 9,036 | `f3260f53ff77598efc42fa78e8690a390f02e4bf5110bc163a6551cf800cc1b1` | 14:37:18 |
| `docs/factors/evidence/F_CLASS_RANK_PARITY_20261107.json` | 11,378 | `3d8ab8780650a88c8e74db2d354c5da4012ab3ca3450d8e9e7a30d8737d47887` | 16:25:21 |
| `docs/factors/evidence/F_CLASS_RANK_PARITY_20261107.md` | 6,047 | `f56dcfa425af8d15bed2244850b086af4996faf5752c720ec1926f75acaaeeee` | 16:25:35 |
| `docs/factors/evidence/REFERENCED_FACTOR_INVENTORY_EXPECTED_20261107.md` | 12,216 | `8b9d78e69e1a0de74b6f61d4cb9879ebe2ed56ea569e84fc66204130a0325f7d` | 19:18:19 |
| `docs/factors/evidence/compare_stats.json` | 40,611 | `b10d32b089a8e6fab53e2b4d98c8ab8a4d82c95f83ac47f737c40fb0f242091b` | 13:48:24 |
| `docs/factors/evidence/e3_b2_fixtures_20261107.json` | 74,023 | `e75106a9aa1b66b394d8803ef308cef2950b48a4978d7f4fdaa86345e9ca236e` | 18:02:41 |
| `docs/factors/evidence/e3_data_availability_20261107.json` | 33,346 | `45d61859ea13f573e1919a99bc085f88e4dc938bd1fd13c7b52faabaf2279b8a` | 17:27:23 |
| `docs/factors/evidence/f_class_registry.json` | 119,029 | `56d3092873145335ed40612d617442cbc4db876dd9570c9ea35656940b15c5a8` | 19:37:15 |
| `docs/factors/evidence/factors_inventory.json` | 110,813 | `afcd5455dc7022c77fb6d11a471eb0d8e97e43f5b1f0c99e567ddf538d1069fb` | 13:48:24 |
| `docs/factors/evidence/factors_inventory_core93_20261107.csv` | 41,701 | `9c98ca60a2e6ddd602970fa1a7d8d7fac9095b5514f8bb7fc80ee7ab607b7fba` | 13:43:53 |
| `docs/factors/evidence/referenced_factor_inventory_expected_20261107.json` | 99,935 | `184dcdf9ef2a545ddd0fc942b6534797b102b9ff6e6cefa6a241b5dd7c5596af` | 19:27:39 |
| `docs/factors/evidence/registration_b0_20261107.json` | 21,959 | `5873de40e438f0d0480e03fafb328ca605adade6257f32c42f95a67b8519f7f8` | 14:48:41 |
| `docs/factors/evidence/scripts/check_f_class_ledger.py` | 29,356 | `3e4b677ee9a281ff3086847c6b62bf2f9b224f8c04c5e7cf23af36a0ead1d496` | 21:34:11 |
| `docs/factors/evidence/scripts/f_class_parity.py` | 15,841 | `1c45e0dfe112b3e8064a2a1e153a3b88c23bb291615be543cd67f9136ad22565` | 14:36:36 |
| `docs/factors/evidence/scripts/f_class_rank_parity.py` | 10,352 | `79fcd61e658a89bfb83d7c638d40a9f4c87bd5c706ec69aa2abf88c5df5af0f0` | 16:24:58 |
| `docs/factors/evidence/strategy_factor_map.json` | 17,950 | `ee75671cb96154903f69ba02513c128460f2984ff47959c44d9aad021c5ac7ac` | 13:49:23 |
| `docs/factors/evidence/xs_rank_family_specs_20261107.json` | 8,272 | `d72b296bd294bc48c961ea149cb3513415dac0ead654343f02a9c60fb85fa9fd` | 14:32:46 |
| `docs/factors/evidence/xs_rank_stats.json` | 2,614 | `cd9b07bc11a327abe27d776c8bfacf05b5ee1b5f035970fa469a650c830d501f` | 13:48:24 |

### 3.7 `docs/research/` 与 `docs/INDEX_20261107.md`（14 个，434,896 B）

| 文件 | 字节 | 全文 sha256 | mtime |
| --- | ---: | --- | --- |
| `docs/INDEX_20261107.md` | 45,782 | `0583affec11bea3ce14f1badfb5175a89c20def345ce68394393aaa27d214c41` | 21:26:30 |
| `docs/research/caliber-decisions-20261107.md` | 69,796 | `588eea1098aa8b3d8eb75b620c60d5c33d34b4986f106f9f3644671788e8204f` | 20:53:48 |
| `docs/research/factor-audit-20261107/FACTOR_GAP_SPEC_20261107.md` | 25,276 | `cc27dfe3b664660d5d8844e1e56c6b68015708761095652e3abd21cb9c752b7e` | 13:49:23 |
| `docs/research/factor-audit-20261107/compare_stats.json` | 40,611 | `b10d32b089a8e6fab53e2b4d98c8ab8a4d82c95f83ac47f737c40fb0f242091b` | 13:36:48 |
| `docs/research/factor-audit-20261107/factors_inventory.csv` | 41,701 | `9c98ca60a2e6ddd602970fa1a7d8d7fac9095b5514f8bb7fc80ee7ab607b7fba` | 13:36:53 |
| `docs/research/factor-audit-20261107/factors_inventory.json` | 110,813 | `afcd5455dc7022c77fb6d11a471eb0d8e97e43f5b1f0c99e567ddf538d1069fb` | 13:36:53 |
| `docs/research/factor-audit-20261107/run_compare.log` | 114 | `e6aff4efa2bde052af5bbb09a555ab569808df2ce04503d48bc576b708ce9172` | 13:36:52 |
| `docs/research/factor-audit-20261107/scripts/audit_compare.py` | 14,634 | `a0dd2c9b5699fac8101b78b95bb615f46510e1e267687a8fe88b47b705ceb926` | 13:37:22 |
| `docs/research/factor-audit-20261107/scripts/audit_xs_rank.py` | 8,519 | `288df8320afd59cc88d1199a321f2f3de7ce89259cacffb669ebe3852ff29645` | 13:42:06 |
| `docs/research/factor-audit-20261107/scripts/build_inventory.py` | 26,419 | `42559de8c0d0b06e6ba12be53981f688bcdc0483a9cb8efc6ad51b0c91399ea6` | 13:36:46 |
| `docs/research/factor-audit-20261107/scripts/build_strategy_map.py` | 21,250 | `0fe6279064838a8553b8085aa0f8da212778572a7d68d81dc695c6c2de2f8114` | 13:49:23 |
| `docs/research/factor-audit-20261107/scripts/render_inventory_md.py` | 9,417 | `5c4f5b13f4a0ecb2be4f1ba1a87ef1abf579927115c5c01337ff17ddca20f965` | 13:43:48 |
| `docs/research/factor-audit-20261107/strategy_factor_map.json` | 17,950 | `ee75671cb96154903f69ba02513c128460f2984ff47959c44d9aad021c5ac7ac` | 13:49:23 |
| `docs/research/factor-audit-20261107/xs_rank_stats.json` | 2,614 | `cd9b07bc11a327abe27d776c8bfacf05b5ee1b5f035970fa469a650c830d501f` | 13:42:29 |

## 4 干净检出（clean checkout）会缺哪些

按 §1.2 逐条判定：凡是 `??` 的目录/文件，`git clone` 后**一个都不会出现**。因此下列内容在干净检出里**不存在**：

| # | 缺什么 | 规模 | 后果 |
| --- | --- | --- | --- |
| 1 | `backend/app/custom/research_factor_pack/`（3 个 .py） | 9,221 B | 研究基线 **14 个因子**（`ma20`/`ma60`/`boll_lower`/`boll_upper`/`sd20`/`prior_high_20`/`prior_low_10`/`prior_high_55`/`prior_vol_20`/`ma120`/`vol60`/`prior_high_250`/`prior_amount_20`/`ma200`）整体消失 |
| 2 | `backend/app/custom/research_universe_pack/`（3 个 .py） | 17,222 B | **`in_universe` 因子在干净检出里根本不存在**（provider `official.research-universe-pack-e3` 唯一产出）；依赖它的掩码/选股逻辑同时失效 |
| 3 | `docs/architecture/`（24 个文件） | 1,920,670 B | **全部判据文件、契约 v0.3–v0.10、R2–R9 修订记录、`evidence/referenced_factor_inventory.json` 全部不在库里**——任何引用契约指纹的结论都**不可复算** |
| 4 | `docs/factors/`（30 个文件） | 1,096,994 B | 台账、F 类注册证据、对账原件（`F_CLASS_PARITY_*.json` 等）与 `README.md`（本索引）全部不在库里 |
| 5 | `backend/scripts/build_referenced_factor_inventory.py`（1 个） | 64,975 B | 清单产物 `referenced_factor_inventory.json` **无法重新生成**（产物本身也在 #3 里缺失） |
| 6 | `backend/app/factors/gate.py` + `backend/tests/test_factor_gate.py` | 25,829 B + 18,056 B | 闸门实现与其测试不在库里；**任何引用 `app.factors.gate` 的代码在干净检出里 import 失败** |
| 7 | `docs/INDEX_20261107.md`、`docs/research/**`（13 个文件） | 45,782 B + 389,114 B | 顶层索引与研究报告不在库里 |

## 5 影响：干净检出必然红，且 `in_universe` 不存在

- **测试期望是 108 个 builtin**：`backend/tests/test_factor_registry.py` 第 286/287/326/374 行 `assert len(...) == 108`，`backend/tests/test_factor_store.py` 第 79 行 `builtin_count = 108`、第 88 行 `assert len(factor_columns_view()) == 108`（本清单采集时逐行读出，未改写）。
- **我实测的当前真实值**（`backend/.venv` 直接调用发现器，只读）：`ensure_factor_providers()` 发现 **4 个 provider** —— `official.first-board-event-chain`(9) / **`official.research-factor-pack-b0`(14)** / **`official.research-universe-pack-e3`(1)** / `official.cross-sectional-linkage`(7)；`registry.factor_columns_view()` = **108**。
- **推算干净检出**：108 − 14 − 1 = **93**（两个 pack 都不在库里时，发现器扫不到它们；`backend/app/extensions/factors.py:191` 用 `pkgutil.iter_modules(app.custom)` 发现 `factor_provider` 模块，**目录不在就没有 provider**）。
- **独立审核已判 B-2 阻塞**：测试期望 108，而两个 pack 未入库 ⇒ **干净检出必然 6 红**，且 `in_universe` 在干净检出里**根本不存在**（`research/independent-review-20261107/BATCH2_ABC_AUDIT_20261107.md`）。
- **我必须说清的部分**：上面「6 红」是**引述独立审核**，**我没有复现**——复现需要把两个 pack 目录临时移走再跑测试，会污染工作树与他人正在跑的任务，不在我的写权限与纪律内。可复现的只有「108 − 15 = 93」这条算式与 provider 计数（见上一条实测）。

## 6 边界与免责

- **本清单不覆盖 `research/`**：该目录 34 条 `??` 条目里有大量过程产物（各批次研究、审核、复算脚本），它们不是交付面；若需要，另行出清单。
- **`__pycache__/*.pyc`（7 个）不计入**：它们是 pack 目录下 import 产生的字节码，随源码重建，不属交付面。
- **本清单不判断内容对错**：只登记「磁盘上现在是什么字节」。任何 PASS/FAIL 仍需按《docs/factors/README.md·三条流程结论》写死 `size + 全文 sha256 + 读取时间`。
- **活文件警告**：本轮契约、台账、闸门都在持续改写（我这一轮内就观测到 R9 21:39:09 → v0.10 21:39:53 → `gate.py` 21:40:12 → `test_factor_gate.py` 21:40:32）。**本表的 mtime 是采集时刻的快照**；任何引用都应重新 `sha256` 一次。

## 7 复算方法（任何人可重跑）

```bash
cd C:/work/sourcecode/tick-stock-panel
git status --porcelain
git rev-parse --abbrev-ref HEAD && git rev-parse HEAD
```

```python
# 逐文件 size / sha256 / mtime（与本表同口径）
import os, hashlib, datetime
ROOT = r'C:/work/sourcecode/tick-stock-panel'
for rel in open('filelist.txt', encoding='utf-8'):
    rel = rel.strip()
    if not rel: continue
    p = os.path.join(ROOT, rel.replace('/', os.sep))
    b = open(p, 'rb').read()
    print(rel, len(b), hashlib.sha256(b).hexdigest(),
          datetime.datetime.fromtimestamp(os.stat(p).st_mtime).strftime('%H:%M:%S'))
```

## 8 本文件自身

本文件是 §3.5 里 `docs/architecture/` 的**新增内容**（因此它自己也未跟踪），**其 size/行数/sha256/mtime 由交付回执给出**（本文件不自指，避免自指哈希）。

**计数口径提醒**：§3 的 **77 个**是「采集时刻」的文件数，**不含本文件**，也不含同桌的 `.json`；加上这两个，`backend/` + `docs/` 下未跟踪文件为 **79 个**。

---

登记人：文档管理员（只读采集；只写本文件与同名 `.json`）。**未提交、未部署、未重启。**
