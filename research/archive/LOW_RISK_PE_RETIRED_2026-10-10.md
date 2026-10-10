# 历史归档｜低风险PE买点榜已退役

2026-10-10经用户确认正式由 **A股趋势买点榜** 单版本接管。旧系统的具体研究结果、契约和脚本不再参与选股、调度、盘中监控或失败恢复。本文件只用于历史审计，并非第二条研究链。

退役前最终有效历史标本：2026-10-09，正式结果 original blob SHA=`790d5c986f504683e8d8caa8b35acf0eee0cbd02`，handoff blob SHA=`42280db691a32aa09a6661e6e290529c3f1f1e61`。其删除前内容保留在 Git 历史中，可用 `git show 53f4a467a6e70f4c107586fb7e214f7a3258eaf3:research/latest_formal_result.json` 和 `git show 53f4a467a6e70f4c107586fb7e214f7a3258eaf3:research/low_risk_handoff.json` 读取。**不允许将这些历史数据改名为今天的新正式榜**。

唯一活跃公司榜规则：`skill/TREND_BUY_CANONICAL.md`；唯一活跃结果目标：`research/trend_buy_formal_result.json`；唯一活跃交接目标：`research/trend_buy_handoff.json`；盘中唯一股票入口：`research/intraday_market_snapshot.json` 中 `trend_buy_stocks`。旧估值/低风险区间字段及旧WAIT原因不得复制到新版。旧文件删除不影响Git历史查询。

首个合规正式新版需要从当轮有效趋势handoff、冻结公司工作集、全量公司研究及同日已完成结构重新计算；此前新版基线缺失时只报告不可用，不启用旧版回退。工程参数可边运行边迭代，但不能放宽日期、覆盖、异常停止或真实readback要求。
