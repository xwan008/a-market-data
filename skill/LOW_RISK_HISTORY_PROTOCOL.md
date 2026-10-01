# A股低风险买点榜｜历史信号账本与每日回溯（发布后附属协议）

## 1. 不能改变的边界

本协议只在低风险榜本轮**完整 Fresh Run**、正式结果 `research/latest_formal_result.json` 提交并 READBACK 成功、且 19:00 正式 `research/low_risk_handoff.json` 按原契约成功发布之后，独立管理历史信号。正式榜筛选、全量覆盖、预筛、Transmission、Expectation、估值、价格区间、READY/WAIT 排名与盘中 handoff **完全不读取**本账本，也不由历史名单扩容；早间 07:00 版本不刷新正式历史账本。独立任务失败不能撤销或修改已成功发布的正式榜、handoff，也不能虚称历史已更新。

`research/low_risk_signal_registry.json` 是历史信号摘要；`research/low_risk_history/YYYY-MM-DD.json` 是逐正式交易日的回溯事件与当日状态快照。对应的确定性生成器为 `scripts/update_low_risk_history.py`，维护工作流为 `.github/workflows/reconcile-low-risk-history.yml`。正常情况下，GitHub 19:00 handoff 成功提交后触发独立工作流；如果触发或写入失败，可在 GitHub Actions 手动调用 `workflow_dispatch` 恢复。不得把独立工作流是否成功作为原正式榜发布 Gate。

## 2. 严格来源与验证

生成器只读本轮已经落库的完整正式结果和同轮完整 handoff，并核验：
- 双方 `status=COMPLETE`；`trade_date`、`run_id/source_run_id` 相同；
- handoff 的 `source_formal_blob_sha` 等于 Git 真实正式结果 blob SHA；
- READY+WAIT 身份、rank、主状态、合法 `wait_reason`、行业身份及两档买入价格区间与正式结果逐项精确一致，任何缺口停止，不触碰旧账本或快照；
- 账本只允许严格向前推进交易日；相同交易日新正式版本必须从该日快照内 `prior_registry` 重放，不叠加伪造二次迁移；相同来源重跑幂等。

首次建立历史仅从第一份可验证的同轮正式榜+handoff 开始，`status=BOOTSTRAP_PARTIAL`；不能将更早的推荐、价格表现或退出理由反推为已核验事实。此后验证通过的新增正式交易日账本可标 `COMPLETE`，但 `history_start_trade_date` 始终保留真实起点。

## 3. 信号的身份和生命周期

信号按 `code + trend_name + industry_code + episode` 唯一识别，同一公司可在不同板块拥有不同信号，不能通过公司代码将不同趋势信号强行拼成一条。仅以本轮完整筛选出的 READY/WAIT 为当前新仓候选。

- 本轮仍在榜且保持原趋势/行业身份：ACTIVE，连续比较正式状态、排名、买入区间，旧数值只用于**事后解释**。
- 板块/三级行业暂不在本轮当前新仓 handoff：PAUSED_OUT_OF_SCOPE，暂停旧信号的新仓资格，保留初始条件及观察；这**不是**趋势已经失效或应卖出现有持仓的证据。
- 板块仍在，但个股正式结果已不再入选：CLOSED，优先记录当轮 `hard_filtered_out/pre_screened_out/early_evidence/uncertain/drop` 的真实分类与已提供原因；没有对应信息只能标 `NOT_SELECTED_THIS_RUN`，不可臆造失效原因。
- 同公司转入不同趋势/行业：旧信号终止为 `ROUTE_CHANGED`，新信号重新建档。
- 已暂停或已关闭信号日后重新入选，即使同公司同板块，开启新的 episode，重新记录买入区间，不能继承过时的入场条件。
- 连续超出新仓范围 30 次有效账本更新后，旧暂停信号结束本轮观察；历史记录不删除。

历史个股的日度价格仅使用数据生产层的 `data/history_shards/<code前4位>.json`；仅当**目标交易日**存在 high/medium 置信度收盘价时记录观察。能找到同一复权历史序列内首次入榜日的有效收盘价时，可计算标注为“区间行情表现”的复权价格变化；否则明确 UNAVAILABLE，不拿上一日价格伪装今天、不把行情涨跌当作已成交策略收益。不对已关闭超过 30 次账本更新的历史信号继续做每日行情追踪，永久保留身份和退出原因。

## 4. 发布、验证、输出与持仓边界

正式榜和 handoff 的写入及 READBACK 仍严格遵循现有 canonical 文件。独立工作流运行测试、预验双方完整性，再在**一个 Git commit** 内写入 registry + 当日历史快照；不得修改正式榜、handoff、盘中快照、盘中 state 或板块趋势榜。GitHub commit/READBACK 未确认时，历史输出标 `HISTORY_PENDING` 或 `HISTORY_WRITE_FAILED`，禁止宣称已归档；旧 registry 保留。历史回溯报告可在正式研究发布后对比上一份可信 registry 与本轮新结果，呈现新增、延续、退出/暂停及明确证据，但不能回填本轮估值、排序或盘中监测输入。

仅新正式 READY/WAIT 交给现有盘中监测；仍然持有但已经退出新仓榜单的个股，将来必须由**独立真实持仓监控**持续覆盖，不能通过把历史信号塞回新仓榜单解决。目前本协议只是候选信号研究跟踪，不代表已经接入真实持仓或自动产生交易动作。
