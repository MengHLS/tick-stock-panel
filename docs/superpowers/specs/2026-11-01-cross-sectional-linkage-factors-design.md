# 截面联动因子物化设计

日期：2026-11-01

状态：已实现（2026-11-01）。本文件保留设计取舍；现行使用口径以
[`docs/features.md`](../../features.md) 为准。

## 实现结果

- 7 个因子已注册到「截面联动」组，并出现在因子库、检验、策略评分和
  `matrix_native` 因子排名研究中。
- `ext_hy_ths_pit` 提供按交易日时点保存的同花顺行业归属；sidecar 按
  `finalized_through` 覆盖，行业层级为第二级，最少同业数为 10；仅
  `require_complete=True` 的时序行业配置可作为 PIT 来源。
- 盘后管道在 enriched 发布成功后独立发布 `kline_daily_linkage`；支持全量重建和
  向后增量，使用独立 linkage generation 稳定读取。
- 面板与矩阵路径共用 sidecar 值；矩阵磁盘缓存只保存基础行情，命中后注入当前
  联动字段。覆盖不足、sidecar 缺失或 generation 不稳定时 fail-closed。
- 盘中监控引用 `industry_*` 条件时返回并显示 `daily_close_only`，不实时重算。

已知边界仍是首版范围：概念板块联动、全市场 Beta、残差动量、领先滞后网络和
盘中行业联动均未实现；行业因子只能从 `ext_hy_ths_pit` 实际开始积累的日期起
使用，60 日窗口的前段可能为空。

## 1. 目的

为因子平台增加一组真正具有参照系的截面联动因子：

- 个股相对所属交易所板块基准的超额收益；
- 个股相对同业均值的动量；
- 行业内动量排名；
- 个股与同业收益的相关性和 Beta。

这些因子必须同时可用于：

- 因子库、单因子检验、批量检验和因子组合；
- 自定义信号；
- 面板型策略评分；
- `matrix_native` 策略和因子排名研究；
- 历史回测和盘后扫描。

`matrix_native` 必须在这一期支持，因此不能在用户请求时临时构造列，也不能只改
因子检验服务。采用日管道物化、独立 sidecar 表和独立 `linkage` generation
发布的方案。sidecar 是日频覆盖物，不与每个盘中 tick generation 绑定。

## 2. 当前事实与约束

- enriched 主表当前只存 14 列基础行情，见
  `backend/app/indicators/pipeline.py` 的 `ENRICHED_STORAGE_COLS`。
- `deviate_3d/10d/30d` 已有基准偏离语义，但目前只在部分运行期读取位置附着，
  不进入因子注册表和因子检验。
- 因子 DSL 的 `rank/zscore/winsorize` 只按日期做全市场截面，不能按行业分组，
  见 `backend/app/factors/dsl.py`。
- 行业/概念预设当前是 `snapshot` 模式，不能用于历史点时研究。不得把当前
  行业归属回填到历史日期。
- 指数日 K 和交易所板块基准指数的选择规则已经存在，见
  `backend/app/indicators/pipeline.py` 的 `load_benchmark_momentum`。
- `matrix_native` 直接从 enriched Parquet 读取物理字段；未落盘的因子列不能
  直接进入矩阵字段。

## 3. 目标、非目标与反目标

### 3.1 目标

- 注册 7 个截面联动因子，统一归入“截面联动”组。
- 用全市场数据计算行业聚合，用户缩小股票池时复用已物化结果，不重新缩池计算。
- 通过独立 sidecar 表提供因子值，不改写 enriched 的 14 列存储契约。
- sidecar 使用独立 `EnrichedPublication(data_dir, "linkage")` 发布令牌；
  enriched 日发布成功后才把 linkage 发布切为 ready，构建失败时不会留下可读的
  半新半旧 sidecar；盘中 tick 只推进 stock generation，不影响 linkage generation；
- 联动因子只对 `finalized_through` 以内的日期有效。
- 因子检验、面板回测、矩阵回测、矩阵缓存预热和自定义信号使用同一份值。
- 历史行业归属按交易日点时读取；无法证明时点时返回空值并明确原因。
- 旧数据、旧策略和未使用联动因子的流程保持原行为。

### 3.2 非目标

- 首版不实现概念板块联动。概念是多对多关系，需要单独定义权重和去重口径。
- 首版不实现市场 Beta、残差动量、领先滞后网络或全行业中性化框架。
- 首版不提供盘中实时更新。行业联动因子是日收盘因子；盘中请求不得复用昨日值，
  也不进入盘中监控。
- 首版不新增通用 DSL `group_rank/group_zscore` 语法。
- 首版不承诺能够从现有行业快照恢复历史行业归属。

### 3.3 反目标

- 用当前行业成员关系回填全部历史，制造未来函数。
- 用用户选中的少量股票重新计算“行业均值”，导致同一因子在不同回测股票池下变值。
- 行业或基准数据缺失时填 0、前向填充到无穷远，或静默退化到全市场均值。
- 为 `matrix_native` 再写一套临时公式，造成检验值和策略值口径分叉。
- 通过修改 enriched 主表 14 列 schema 来强行承载联动因子。

## 4. 方案选择

### 4.1 候选方案

| 方案 | 说明 | 结论 |
| --- | --- | --- |
| 运行时补列 | 检验、面板和矩阵各自在请求时计算 | 不采用；矩阵缓存、重复计算和口径一致性风险最高 |
| 写入 enriched 主表 | 扩展 14 列主表并全量回填 | 不采用；schema、增量、上游升级和存储契约影响过大 |
| 独立 sidecar 物化 | 日管道生成 `kline_daily_linkage`，在 enriched 日发布中原子写入 | 采用 |

### 4.2 选择理由

sidecar 方案把复杂行为放在一个小接口后面：

- 上层只需要知道“按 symbol/date 读取联动因子列”；
- 全市场聚合、点时行业、基准指数和缺失处理都留在因子模块；
- enriched 主表、ETF/指数表和既有增量语义不变；
- `matrix_native` 可以把 sidecar 当作与扩展数据、财务因子同类的后置字段注入；
- 回滚时可以停止读取 sidecar，主行情数据和旧策略不受破坏。

## 5. 因子定义

### 5.1 注册表条目

所有因子满足：

- `asset_types = {"stock"}`；
- `scale_free = true`；
- `direction = "none"`，方向由检验结果决定；
- `incremental_safe = false`，因为行业聚合依赖全市场截面。

| ID | 名称 | 单位 | warmup | 说明 |
| --- | --- | --- | --- | --- |
| `deviate_3d` | 3日基准偏离 | ratio | 4 | 个股 3 日收益减所属板块基准 3 日收益 |
| `deviate_10d` | 10日基准偏离 | ratio | 11 | 个股 10 日收益减基准收益 |
| `deviate_30d` | 30日基准偏离 | ratio | 31 | 个股 30 日收益减基准收益 |
| `industry_relative_momentum_20d` | 行业相对动量(20日) | ratio | 21 | 个股 20 日动量减同业均值 |
| `industry_rank_momentum_20d` | 行业内动量排名(20日) | score | 21 | 个股动量在行业内的百分位，范围 (0,1] |
| `industry_corr_60d` | 行业收益相关(60日) | ratio | 61 | 个股与同业组合的 60 日收益相关 |
| `industry_beta_60d` | 行业Beta(60日) | ratio | 61 | 个股对同业组合的 60 日 Beta |

`deviate_*` 复用现有 ID，保持候选方案和历史配置兼容。其余因子为新增稳定 ID，
不得在后续版本随意改名。

### 5.2 基准偏离

对窗口 `N ∈ {3, 10, 30}`：

```text
stock_mom_N = close_t / close_{t-N} - 1
bench_mom_N = bench_close_t / bench_close_{t-N} - 1
deviate_N   = stock_mom_N - bench_mom_N
```

- `close` 使用 enriched 前复权收盘价；
- 基准指数使用 `kline_index_daily`；
- 板块映射和候选指数顺序沿用现有 SH / STAR / SZ / GEM / BJ 规则；
- 某板块没有声明候选可用时，保留现有兼容行为，回退到任一可用基准；
- 只有全部基准数据都不可用时因子才为 null，不回退到全市场或 0；
- ETF、指数不注册这些因子。

### 5.3 行业归属

行业来源必须满足：

- 来源是扩展数据中的行业维度字段；
- 配置模式必须是 `timeseries`；
- 新增内置预设 `ext_hy_ths_pit`（时序行业），保留现有 `ext_hy_ths`
  快照用于展示和监控；联动因子只接受时序来源；
- `ext_hy_ths_pit` 的 fanout 配置启用 `require_complete=true`：任一板块拉取
  失败时该日分区不得写成成功快照；或写分区级完整性标记，sidecar builder
  只能读取完整分区；
- 所有可用的时序行业来源中必须恰好一个候选，否则 fail-closed；
- 每个 `(symbol, date)` 最多一个主行业；
- 行业路径 `一级-二级-三级` 默认取第 2 级；不足两级时使用原值；
- 日期 `t` 使用不晚于 `t` 的最近一次行业快照；
- 最近快照距 `t` 超过 30 个自然日时视为未知；
- `snapshot` 配置不能参与历史物化，只能给出“需要时序行业归属”的不可用原因；
- 来源配置必须完整拉取；部分缺失的行不得被解释为“已移出行业”，只按未知处理。
- 新增分预设迁移标记，使升级用户也获得 `ext_hy_ths_pit`；不得重新创建用户
  已主动删除的旧预设。

首版只支持一个主行业，不支持多行业等权展开。

### 5.4 行业聚合

所有行业因子先在**全市场**面板上计算，再供任意股票池读取。

个股权益使用剔除自身后的同业等权值。设股票 `i` 在日期 `t` 所属行业为 `g`：

```text
peer_count_i,t = count(group=g, t) - 1
peer_mean(x)_i,t = (sum(x, group=g, t) - x_i,t) / peer_count_i,t
```

当 `peer_count < 10` 时所有行业因子为 null。

#### 行业相对动量

```text
industry_relative_momentum_20d
  = momentum_20d_i - peer_mean(momentum_20d)_i
```

#### 行业内排名

```text
industry_rank_momentum_20d
  = average_rank(momentum_20d within date, industry) / group_size
```

排名包含股票自身，范围 `(0,1]`。

#### 行业相关与 Beta

先用全市场日收益计算剔除自身后的同业日收益：

```text
r_i,t        = close_t / close_{t-1} - 1
peer_return  = (sum(r, group=g, t) - r_i,t) / (group_size - 1)
```

随后按 symbol 做 60 个交易日的滚动统计：

```text
industry_corr_60d = corr(r_i, peer_return, 60)
industry_beta_60d = cov(r_i, peer_return, 60) / var(peer_return, 60)
```

- 60 个样本必须完整，`min_samples = 60`；
- 同业收益方差接近 0 时 Beta 为 null；
- 任一侧标准差为 0 时相关为 null；
- 窗口内缺行业或同业不足的日期使该期结果为 null，不得跳行缩短窗口。

## 6. 存储与发布

### 6.1 Sidecar 路径

```text
data/kline_daily_linkage/
  manifest.json
  date=YYYY-MM-DD/
    part.parquet
```

每个分区至少包含：

```text
symbol: Utf8
date: Date
deviate_3d: Float64
deviate_10d: Float64
deviate_30d: Float64
industry_relative_momentum_20d: Float64
industry_rank_momentum_20d: Float64
industry_corr_60d: Float64
industry_beta_60d: Float64
```

不把行业名称写入因子分区，避免扩大数据契约；行业来源和覆盖信息放 manifest。

### 6.2 Manifest

`manifest.json` 至少记录：

```json
{
  "version": 1,
  "methodology_version": "linkage_v1",
  "factor_ids": ["..."],
  "min_peers": 10,
  "industry_source": "ext_hy_ths_pit",
  "industry_level": 2,
  "industry_source_signature": "<config + partition signature>",
  "industry_pit": true,
  "industry_coverage_start": "2026-11-01",
  "coverage_start": "2026-11-01",
  "finalized_through": "2026-11-01"
}
```

没有合法时序行业来源时：

- 三个基准偏离因子仍正常物化；
- 四个行业因子列仍写入 schema，但值全为 null；
- manifest 写入明确的不可用原因。

### 6.3 原子发布

- stock enriched 使用 `EnrichedPublication(data_dir, "stock")`；
- sidecar 使用独立 `EnrichedPublication(data_dir, "linkage")`；构建开始时先
  claim linkage 发布，读者在 publishing 状态下持续 fail-closed；
- 启动恢复列表增加 `linkage`，异常退出后不能永久卡在 publishing；
- 新增 `EnrichedPublication.write_json(payload, out)`，与 `write_parquet()` 一样
  参与发布锁、临时文件替换、fsync 和 `_changed` 标记；manifest-only 更新也必须
  产生新 generation；
- manifest 不记录提交后才生成的 generation；读者以 linkage generation 作为
  缓存失效和稳定读取令牌，以 `coverage_start/finalized_through` 作为日频边界；
- `finalized_through` 只能推进到已收盘且官方日线完整的交易日；手工午间运行
  管道可以更新 enriched，但不得把当天推进为联动因子完成日；
- 发布顺序固定为：stock enriched 全部写完并 commit → linkage 分区和 manifest
  写完并 commit；stock commit 失败时 linkage 保持 publishing/abandon，不产生
  可读的新 sidecar；
- 盘中 enriched tick 可以继续推进 stock generation，但联动因子只允许读取
  `finalized_through` 以内的日期；请求超过该日期时 fail-closed，不得把盘中价
  当作已完成日线因子；
- linkage generation 变化后，联动因子结果缓存、矩阵联动字段和前端查询失效；
  stock generation 变化仍按现有规则使基础行情缓存失效；
- 所有 sidecar 读取使用 `stable_linkage_read(data_dir, expected_generation)`：
  - 读取前后调用 `get_enriched_generation(data_dir, "linkage")`；发布进行中或
    linkage 代际变化时重试；
  - 重试耗尽仍不稳定则 fail-closed；
  - 读取 manifest、目标日期分区和注入映射必须在同一个稳定窗口内完成；
  - `attach_linkage_columns`、`attach_matrix_linkage_fields` 和
    `ScreenerService` 共用该读取协议，禁止直接 scan sidecar 绕过发布检查。

### 6.4 完成交易日判定

`finalized_trading_dates()` 只返回同时满足以下条件的日期：

- `date < cn_today()`，或 `date == cn_today()` 且北京时间已过 15:30；
- `kline_daily/date=...` 官方日线分区存在；
- enriched 分区存在，且停牌过滤后的 symbol 覆盖与官方日线一致；
- enriched `raw_close` 与官方日线收盘价在半个最小报价单位内一致；
- 现有数据完整性扫描对该日期没有未解决的坏分区；
- 逐候选日直接检查 `kline_daily` 分区中的盘中快照残留，不受最近扫描窗口限制。

校验规则复用 `data_integrity` 和 daily pipeline 现有的覆盖/价格校验，不另写一套
“看起来完整”的判断。任何一项无法证明时，该日期不进入 `finalized_through`；
读取请求超过该日期时返回明确错误。

## 7. 计算流水线

新增：

```text
backend/app/factors/linkage.py
backend/app/factors/linkage_store.py
```

职责：

- `linkage.py`：纯计算、因子定义、缺失和边界规则，不做 IO；
- `linkage_store.py`：读取基准/行业来源、构建 sidecar、扫描 sidecar、矩阵注入。

对外接口保持小：

```python
LINKAGE_FACTOR_IDS: frozenset[str]

def compute_linkage_fields(
    enriched: pl.DataFrame,
    benchmarks: pl.DataFrame,
    membership: pl.DataFrame,
    target_dates: set[date],
) -> pl.DataFrame: ...

def attach_linkage_columns(
    frame: pl.DataFrame,
    names: Collection[str],
    data_dir: Path,
    *,
    expected_generation: str | None,
    require_complete: bool,
) -> pl.DataFrame: ...
```

### 7.1 全量重建

1. 从 enriched 分区取得交易日轴，再用统一
   `finalized_trading_dates(asset_type="stock")` 过滤到 `finalized_through`
   以内的日期。
2. 以不超过 20 个目标交易日为一个计算块。
3. 每个块额外读取它之前的 61 个交易日作为预热。
4. 在全市场面板上计算日收益、60 日滚动统计和行业聚合。
5. 只保留目标日期的 sidecar 行并原子写入日期分区。
6. 全部日期完成后写 manifest。

行业和基准的原始来源不得通过逐股票循环读取。

### 7.2 新增交易日

- 只选择已收盘且官方日线完整的日期；
- 读取新增日期及其之前 61 个交易日；
- 只写新增日期的 sidecar 分区；
- 已有历史日期不重写。

### 7.3 复权因子变化

复权收盘价变化会改变所有同业收益和聚合值。只要本次 enriched 计算包含
除权因子增量或价位变化，就必须重建 sidecar 的全部日期，不能只重算变更个股。

### 7.4 行业与基准来源变化

manifest 记录行业来源签名。以下任一变化触发从最早受影响日期开始的全量重建：

- 行业来源 ID 改变；
- 时序行业分区新增或修改；
- 任一 `kline_index_daily` 日期分区新增或修改；
- 行业层级 `industry_level` 改变；
- 行业规范化规则改变；
- `min_peers` 改变；
- 因子公式或 `methodology_version` 改变。

## 8. 读取接入

### 8.1 因子平台

- 注册表新增 7 个 `kind="base"` 因子；
- `GET /api/factors`、因子库、编辑器字段和 AI 提示词自动出现；
- 因子服务在加载基础行情前捕获 linkage generation，基础面板与 sidecar 附着后
  再次校验；变化时整次面板读取和附着重跑，不能只重读 sidecar；
- `FactorBacktestService._load_factor_panel` 在基础行情加载后调用
  `attach_linkage_columns(..., require_complete=True)`，内部使用稳定读取协议；
- 单因子、批量检验和 `/api/factors/trial` 使用同一读取入口；
- 请求了联动因子但 sidecar 日期覆盖不完整时，返回明确错误，不进入“全 null
  被当作计算完成”的状态；
- 单行同业不足导致的 null 是合法数据，不算读取失败。

### 8.2 面板策略

- `ResolvedFeaturePlan` 新增 `linkage_columns`；
- `_resolve_base_columns` 不把联动因子当作 enriched 物理列；
- `BacktestEngine.load_panel_for_backtest` 在基础行情和财务字段之后附着 sidecar；
- 加载基础行情前捕获 linkage generation，基础面板和 sidecar 附着后再次校验；
  变化时整次读取重跑。stock tick generation 不作为联动因子稳定令牌；
- 策略 result cache、参数扰动和共享优化面板都包含联动因子列；
- 自定义信号引用的联动因子通过同一面板读取路径获得；
- `ScreenerService` 组装筛选帧后调用共享 `attach_linkage_columns`，覆盖
  SQL 筛选和策略扫描的 live/post-close 上下文；请求日期超过
  `finalized_through` 时返回“仅日频可用”，不得静默丢掉因子列。

### 8.3 Matrix-native

- `field_columns` 和矩阵磁盘缓存字段从 Parquet 物理列中剔除联动因子；
- 矩阵基础数据加载前捕获 linkage generation，字段注入后再次校验；变化时重建
  本次矩阵请求，不允许在一次结果中混入不同 linkage 快照；
- 基础矩阵加载和缓存命中后，调用
  `attach_matrix_linkage_fields(market, data_dir, names)`，内部使用稳定读取协议；
- 注入方式复用扩展时序字段和财务因子的矩阵后置字段适配模式；
- 矩阵缓存键不需要包含 sidecar 文件内容；每次命中后仍从当前日频 sidecar
  注入，且 manifest 覆盖区间必须包含请求的全部日期；
- `factor_rank_research` 生成的单因子/多因子排名策略可以直接使用联动因子；
- `_matrix_field_columns` 和 `StrategyEngine` 的矩阵 live 运行路径都必须声明
  联动字段，不能只在磁盘回测路径注入；
- 联动因子缺失或覆盖不足时矩阵加载 fail-closed，不创建全 NaN 因子列继续回测；
- 筛选/实时扫描的 panel 和 matrix-native 两条 `run_all` 路径都要有定向测试。

### 8.4 盘中路径

- 首版联动因子只保证日收盘数据；
- 盘中单日快照不重算行业 60 日相关/Beta，也不使用昨日因子值冒充今日值；
- 行业联动因子在保存为盘中监控条件时直接拒绝，并返回 `daily_close_only` 原因；
  已有规则在运行期遇到 `industry_*` 时输出明确 degraded 状态，不能只写日志后静默丢弃；
- 监控评估结果增加可序列化的 `unavailable_reason`，通过现有监控 API
  和页面显示“仅日频可用”；不得把缺列当成条件未命中；
- `deviate_*` 保留既有 `quote_service` 盘中运行期计算，用于异动/展示；
  该路径与 sidecar 必须复用同一纯公式和单位，但盘中值不写入联动因子 sidecar；
- 盘后管道完成并推进 `finalized_through` 后，下一个日频扫描/回测读取新 sidecar；
- 自定义信号在盘中可以沿用现有实时偏离列；历史回测和盘后评分只认已完成日期的
  sidecar，两者不得在同一结果中混用。

## 9. API、前端与可观测性

- 不新增因子专用 CRUD API。
- `/api/factors` 自动返回新增因子。
- 因子库显示分组“截面联动”、公式、预热天数和“股票”适用范围。
- 因子发现页新增“截面联动”预设，选择该组全部因子。
- 行业来源不可用时，因子检验错误必须包含：
  - 缺少时序行业归属；
  - 需要配置的数据能力；
  - 不提供历史回填或当前快照替代。
- 自动挖掘默认调度仍按原有前 48 项顺序，不自动把实验性的行业联动因子插入
  默认挖掘池；用户可通过显式选择或后续单独调度启用。

## 10. 缓存与性能

- sidecar 分区按日期读取，只有目标股票池和目标列参与 join；
- `compute_linkage_fields` 使用 Polars `group_by/join/rolling_*`，不得逐股票循环；
- 全量重建按 20 个目标交易日分块，单块额外保留 61 个交易日预热；
- 矩阵基础数据缓存不缓存 sidecar 派生列，命中缓存后只追加轻量字段注入；
- stock generation 变化必须使 PanelCache 和基础矩阵缓存失效；
- linkage generation 必须进入任何引用联动因子的因子结果、策略结果和筛选结果缓存键；
- 相同 linkage generation、manifest 签名、日期范围和列集合的 sidecar 读取允许
  进程内短期缓存，缓存键必须包含 `data_dir`、asset type、linkage generation、
  manifest 签名、符号集合和日期范围；
- 性能验收至少覆盖 5 年、全市场规模的生成耗时、sidecar 大小和矩阵加载增量；
  没有实测前后数据前不得声称性能等价。

## 11. 迁移与兼容

- 不修改 enriched 14 列 schema，不要求删除已有 enriched。
- 升级后首次运行盘后管道或“重建 enriched”时生成 sidecar。
- sidecar 生成前，联动因子可以出现在因子库，但检验/回测必须明确报“尚未物化”。
- 删除 sidecar 是安全操作；下一次全量重建会恢复。
- 旧候选方案、策略 JSON、自定义信号和 API 字段保持可读。
- 回滚时停止注册和读取联动因子即可，旧 enriched 和指数数据不受影响。
- 行业点时数据从可用时序来源开始；在此之前行业因子覆盖不足必须如实显示，
  不得生成历史归属。

## 12. 测试矩阵

### 12.1 纯计算

- 三个板块偏离窗口的固定样本数值；
- SH / STAR / SZ / GEM / BJ 映射、声明候选回退和“任一可用基准”兼容回退；
- 缺基准、缺行业、未知行业、多行业冲突和同业不足的 null 语义；
- 行业均值和行业收益必须剔除自身；
- 行业内排名包含自身且范围正确；
- 60 日相关完整、零方差、缺样本和窗口截断边界；
- 行业归属 change point 前后使用各自时点成员，不出现未来成员。

### 12.2 Sidecar 发布

- 全量重建日期覆盖与 enriched 一致；
- 增量新增日期可正确复用前 61 个交易日；
- 除权因子变化触发全量 sidecar 重建；
- `snapshot` 行业源不能生成历史值；
- `ext_hy_ths_pit` 时序来源、二级行业规范化和 30 日最大陈旧边界；
- `ext_hy_ths_pit` fanout 任一板块失败时不产出完整分区；
- 完整快照中真实移出行业的股票不会被误判为“拉取失败”；
- 从旧安装目录升级时只补建缺失的新预设，不恢复用户删除的旧预设；
- 生成中途失败时发布保持 fail-closed；
- `write_json()` 的 manifest-only 更新会推进 generation，且崩溃时不暴露半写文件；
- manifest 的覆盖区间、来源、层级、签名和不可用原因准确；
- sidecar 发布后发生盘中 enriched 写入时，历史日期仍可读，超过
  `finalized_through` 的日期明确失败；
- 历史读取期间连续发生 stock tick generation 变化时，linkage 稳定读取不失败；
- stock 日发布与 sidecar 附着之间发生 linkage generation 变化时，整次面板读取重跑；
- 午间手工运行管道后当天不进入 `finalized_through`；
- sidecar 发布过程中并发读取会重试或 fail-closed，不读取新旧混合分区。

### 12.3 读取与策略

- 因子注册表快照、API 契约和因子库分组；
- 因子批量检验在用户指定小股票池时仍使用全市场预计算值；
- 因子 trial 和单因子详情；
- 面板型策略评分；
- `ScreenerService` 的 panel 和 matrix-native live/post-close 筛选；
- `StrategyEngine._materialize_scoring_frames` 的当前/历史帧附着；
- `matrix_native` 直接加载与磁盘缓存命中后注入；
- `factor_rank_research` 生成的单因子排名策略；
- 自定义信号条件引用联动因子，以及 `deviate_*` 盘中实时路径回归；
- 盘中监控规则引用 `industry_*` 时保存被拒或运行期返回可见 degraded 原因；
- sidecar 缺失时上述路径均给出明确错误，而不是 0 分或全 NaN 结果。

### 12.4 前端与回归

- “截面联动”预设的选择集正确；
- 行业来源缺失、sidecar 缺失、正常值和部分 null 的界面状态；
- `pnpm build`；
- 未使用联动因子的既有因子检验、策略回测和矩阵缓存测试保持通过；
- `git diff --check`。

## 13. 验收标准

满足以下全部条件才算完成：

- 7 个因子可从 `/api/factors` 和因子库看到；
- 基准偏离因子的结果与现有 `deviate_*` 语义逐值一致；
- 行业因子在全市场生成后，缩小股票池不会改变任一股票当天的因子值；
- 行业归属变化点测试证明没有未来数据；
- 单因子检验、批量检验、面板回测和 `matrix_native` 因子排名策略均可读取；
- stock 日发布成功后才把 linkage 切换为 ready；失败时没有可读的混合快照；
- sidecar 读取经过 publication 稳定窗口，并发发布时不会读到新旧混合分区；
- `finalized_through` 不包含未收盘或官方日线不完整的日期；
- 盘中监控引用 `industry_*` 时有可见的“仅日频可用”状态，不静默跳过；
- 未使用联动因子时现有测试、前端构建和矩阵行为不变；
- 文档明确区分“已物化日频因子”与“尚未支持的盘中/概念联动”。

## 14. 已知风险

- 现有行业预设是快照；升级后会新增 `ext_hy_ths_pit`，但其历史只能从启用
  时序拉取后开始积累，不能立即得到更早历史的研究结果。
- 60 日行业 Beta/相关需要完整全市场历史；新股、停牌和行业调整会导致覆盖下降。
- 除权变化触发全量 sidecar 重建，可能明显增加盘后计算时间。
- fanout 严格完整性会降低行业时序分区成功率；失败时必须保持上一份完整快照，
  不能用残缺成员关系继续推进日频覆盖。
- `matrix_native` 的后置字段注入需要同时覆盖直接加载、磁盘缓存命中和预热缓存
  三条路径，漏一条会产生看似成功但字段缺失的结果，因此三者都必须有定向测试。
- 首版只支持单一主行业，不等同于完整行业中性化或多因子风险模型。
