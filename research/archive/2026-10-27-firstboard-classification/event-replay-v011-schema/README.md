# v0.1.1：候选导出模式修正

本目录只提供候选分类的模式修正版。计算规则版本仍为replay-v01-discussion-20261028；27事件×16候选=432条，不增加事件或规则。其他价格、因子、结果与跟踪仍引用event-replay-v01中的原文件，未重算或复制。

## 修正

早退状态no_first_decline、no_post_anchor_high、no_setup中缺失的depth、recovery_raw、recovery_applicable改为显式null，新增null_reason_codes逐字段解释，分别为NO_FIRST_DECLINE_BEFORE_D、POST_ANCHOR_HIGH_REQUIREMENT_FAILED、NO_PREBREAK_SETUP_LOW。未知适用状态保留null，不伪装成false。

schema-differences.json列出每一个新增空值的事件、规则及JSON路径。manifest.json保存输入输出哈希及全部旧目录文件的哈希。

## 自检结果与计数

- 432条候选全部保留，92条包含新增空值。
- selected与trace在JSON中分别序列化；共160个节点补齐，3字段合计480处新增null，其中selected 162处、trace 318处。每个补齐节点另有一个原因码映射。
- 验证员原报告为170处缺字段检查，与本版按实际JSON路径统计的口径尚未逐项对齐，不将两数混称。差异清单供复核，不为凑数遗漏缺键。
- 移除本次新增字段及原因码映射后，与v0.1深比较完全相等；原有标签、日期、数值和规则版本不变。
- event-replay-v01目录所有原有文件SHA256与修正前一致；未覆盖已验版本。

该修正不是新计算验收。未来数据隔离、后续结果、每日跟踪、全部因子时点和首板身份仍按各自审查状态管理。v0.1中432次自检只比较相同前缀的确定性，不能当作因果性证据。
