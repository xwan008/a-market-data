# A股板块趋势榜｜完整趋势状态协议（增量扩展）

> 本文件仅为“A股板块趋势榜”增加跨轮完整趋势状态管理。既有产业 T0/T1/T2 判定、市场状态判断、全行业扫描、早间增量复核、ETF 时机、新仓优先榜选择、行业路由及写入审计均保持原逻辑。本文件不得作为低风险买点榜或盘中监测的新输入。

## 1. 两份输出与职责边界

- `research/trend_registry.json`：完整趋势状态账本，仅供下一轮**趋势榜**复核；保存新仓优先榜以内、以外的全部已发现且未证实失效的趋势，以及待复核的历史趋势。不能仅根据当期优先榜反推完整趋势池。
- `research/trend_handoff.json`：原格式、原排序、原生成资格，**仅当期新仓优先榜**；供低风险买点榜及其下游盘中快照继续使用。不得混入高潮/衰退但不适合新仓的其他方向，也不得扩展 schema/更改消费者。
- “退出新仓优先榜”与“趋势失效”是不同事件；前者不可自动触发后者。
- 盘中监测仍读取已冻结的当期 handoff 和低风险 handoff，不额外监测仅在 registry 中的旧方向。

## 2. 读取与事实优先级

每轮趋势榜在原有交易日、日期/模式 Gate 之后，读取 main 的 `research/trend_registry.json`、`research/trend_handoff.json`（需要时）以及原有数据/行业路由文件；记录最新文件 blob SHA。registry 仅提供**历史待复核对象、上期记录与状态转换线索**，不能直接证明当期状态、维持资格或代表今日行情，也不得反向取代当前商品、订单、产业、板块行情与正式全市场扫描。

18:40 完整收盘版仍须从**全行业/主要概念板块的全量扫描**开始，独立核验所有上期 registry 中尚未证实失效/待复核的方向，并扫描新增异动。逐一记录保留、状态转换、待复核或已证实失效的证据，不能只审当期 Top 2–3，也不能把 registry 读入视作完成全量扫描。过去状态只有新证据满足原任务已定义的确认/失效标准才能变化；没有足够新证据时标记“待复核”，原记录及其原始日期保留，不宣称昨天结论今天仍成立。明确失效者保留历史记录而不继续列为有效趋势。

06:40 早间增量版延续原有 previous_trade_date 与隔夜证据规则；只能从同一 previous_trade_date 已完成、已成功提交及 READBACK 的正式 registry 基线做增量复核。隔夜证据不足时状态不迁移，不做全市场收盘版伪重算。若 registry 缺失、日期不匹配、结构无效或为 BOOTSTRAP_PARTIAL，标记 REGISTRY_BASELINE_UNAVAILABLE，不把历史资料当正式基线；在下一次有效 18:40 完整版进行首轮正式全量重建。原有交易日与 handoff Gate 仍必须遵守。

## 3. 正式 registry 数据契约

正式版顶层字段：
- `schema_version=1`, `result_kind=a_share_trend_registry`, `trade_date`, `generated_at`, `timezone=Asia/Shanghai`, `status=COMPLETE`；
- `scan_audit` 至少包含：`full_market_scan_completed`, `previous_registry_trade_date`, `previous_trend_count`, `previous_trend_rechecked_count`, `new_trend_count`, `pending_revalidation_count`, `invalidated_count`, `new_position_count`, `evidence_cutoff_trade_date`。06:40 增量版额外注明模式，不能宣称进行当日全量收盘扫描；
- `trends`：完整趋势/待复核记录集合，稳定主题身份不得因为改名或退出新仓榜重复造身份；每条至少有 `trend_name`, `trend_state`(T0/T1/T2/待核验), `market_state`, `lifecycle_status`(有效/待复核/已失效), `first_seen_trade_date`, `last_verified_trade_date`, `industry_codes`, `industry_names`, `in_new_position_priority`, `supporting_evidence`, `contrary_evidence`, `invalidation_condition`, `change_reason`, `state_history`。证据每项注明来源和日期；历史事件包括原状态、目标状态、日期和原因。待复核历史项必须保留其 last_known_* 原始日期，不得谎称现状；
- `invalidated_history`：保留当轮及历史已验证失效的主题与失效证据/日期，禁止无记录删除；
- `recheck_queue`：针对不能由可靠文件恢复具体历史状态的旧主题，明确标记 provenance/unknown，待下次全市场扫描单独核验，不占用新仓名额。

如果字段名未来要调整，须同步升级 schema 与本协议；不允许静默混用或输出省略号。不得把历史 `高潮/衰退` 自动当成当日结论。完整账本指覆盖本轮能识别的全部现存趋势及未解决历史主题，并不声称从 2026-09-17 之前恢复了不存在的历史资料。

## 4. 初始化与兼容

初始 `trend_registry.json` 如为 `status=BOOTSTRAP_PARTIAL`，只是从已验证文件恢复的**待核验历史线索**，不是已完成的当日完整趋势分析。首次后续有效 18:40 正式运行必须完整扫市场，复核全部现存 bootstrap 条目及 recheck_queue 后才可写 `status=COMPLETE`；旧方向没找到足够当期证据时仍存为“待复核”，不能默默清空，也不得假定有效或失效。

先完成本轮全部研究，构造并校验完整 registry（包括全部旧方向去向），再依据原逻辑生成仅含新仓优先方向的 handoff。正式 handoff **必须继续保持原有 schema 和字段顺序/含义**，不添加任何旧趋势。仅用 handoff 作低风险买点榜及盘中监测输入；不得改变任何下游任务、工作流或文件的读取契约。

## 5. 一致性、提交与失败处理

只有本轮独立研究、数据/覆盖 Gate 与 registry schema/覆盖/状态迁移审计均通过才允许正式落库；先取得 main 的目标文件最新 SHA，JSON.stringify 后再 JSON.parse 验证同一完整 UTF-8 内容。先正常提交 registry，取得新 commit/content SHA，立即重新 fetch + 完整解析并核验日期、主题去重/覆盖、状态转移与新 SHA；只有成功后才能按原任务写 `trend_handoff.json` 并 READBACK。hand-off 的 signals 必须与 registry 同轮 `in_new_position_priority=true` 主题**名称和顺序一致**，但格式必须是原有的简化格式。

任何无法验证的正式全扫、registry 写入失败或 READBACK 不符均报告 REGISTRY_INCOMPLETE/REGISTRY_WRITE_FAILED/REGISTRY_READBACK_FAILED；本轮不得发布一份号称成功的新 handoff，不把未落库内容当已持久化历史。保留原有预写 JSON 验证、错误分类、最小审计和安全检查要求；不要为了完成 registry 绕过拒绝或更换写入通道。

写入结果向用户同时展示“完整趋势池（含高潮/衰退及待核验）”“当期新仓优先榜”以及所有旧趋势的状态变化/退出原因。完整趋势池不设 2–3 名上限；只有新仓优先榜沿用原数量选择逻辑。
