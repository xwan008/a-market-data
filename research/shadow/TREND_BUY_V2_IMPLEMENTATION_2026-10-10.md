# A股趋势买点榜 V2｜实施与迁移审计

**结论：SHADOW_ENGINE_PASSED / PRODUCTION_MIGRATION_BLOCKED。**
项目目标已从“低PE/估值折价买点”重定义为“已筛选公司中可复核的趋势入场结构、交易失效及风险约束”。现有正式任务和用户盘中任务仍运行旧协议，只有后续风险检验与全链路发布Gate均通过，才能切换同一任务的名称与规则。

## 已实施

1. 唯一目标与V2规范：skill/TREND_BUY_CANONICAL.md。原上游趋势榜、公司硬过滤、已更新的增长/质量/估值匹配/趋势健康预筛保留；PE/PB/MA60属公司风险筛选而非买价。
2. 独立趋势价格确认：scripts/trend_buy_engine.py，支持完成收盘日的 BREAKOUT 与 PULLBACK，次日入场区、价格上限、结构失效、风险比例、退出原则，以及 WAIT_BREAKOUT/WAIT_PULLBACK/WAIT_CONFIRMATION/WAIT_RISK_REWARD。试验阈值未经过样本外优化：入场价至失效价结构损失<=6%、距MA20>8%禁止追价、可识别上方阻力不足1.5R则暂缓。这些数值不能视为最佳投资策略。
3. 每日价格事实生产：.github/workflows/update-data.yml 已接入 scripts/build_full_market_price_structure.py，输出 data/research/full_market_price_structure.json；日K必须完整并同交易日，压力位基于当日之前K线。新增当天OHLC/前收盘以防误把单纯触及MA当作回调承接，且引入按历史分片前缀缓存提升全市场重算效率。
4. 独立V2协议：scripts/trend_buy_handoff.py、research/trend_buy_formal_result.json和research/trend_buy_handoff.json是**规划中的正式输出**，实际仅生成shadow路径/CI制品，尚未创建生产文件；旧合理估值区字段禁止在V2中出现。
5. 盘中兼容：scripts/build_intraday_snapshot.py 可以在正式V2 handoff存在且证据齐全时选新版本，旧版仍能继续运行；快照 stock_handoff_kind 区分版本，新版参数放在 trend_entry_plan，不重释 reasonable_buy_range、low_risk_buy_range。skill/INTRADAY_MONITOR_CANONICAL.md 已增加V2执行解释与超价不追原则；update-intraday-snapshot.yml 新增版本判定。
6. 自动验证：tests/test_trend_buy_engine.py、tests/test_trend_buy_handoff.py、tests/test_trend_buy_snapshot_bridge.py；.github/workflows/validate-trend-buy-v2.yml 完成单元、实际全市场价格结构重算、42候选历史重放、handoff无旧字段审计并存档制品。

## 2026-10-09历史数据回放

正式旧研究池42只，对应的历史筛选/部分传导研究属于**继承研究**，不是10/09全量重新独立搜证。2026-10-09收盘同日数据：全市场3177只技术结构可计算、满足基础右侧类型筛选约584只；在原研究池42只上跑新的风险买点模型，得到：

| 状态 | 数量 |
|---|---:|
| READY（模拟） | 1 |
| WAIT（模拟） | 17 |
| UNCERTAIN（模拟） | 18 |
| DROP（模拟） | 6 |

唯一模拟 READY：电投能源 002128，回调确认结构，参考次日入场区28.656–29.146元、结构失效27.557元、按买价上沿计算损失约5.45%。**这是历史影子信号，不是对2026-10-10的实时交易推荐。** 涉及盘中高开、跳空、滑点、假跌破及衰退证据的规则仍待交易结果验证。

WAIT原因（模拟）：WAIT_BREAKOUT 8，WAIT_CONFIRMATION 4，WAIT_PULLBACK 5，WAIT_RISK_REWARD 0。无完成公司最新动态及绩效验证时，数量不得用于评价策略有效性。

CI: https://github.com/xwan008/a-market-data/actions/runs/38024034159
Artifact: GitHub Actions run下的 trend-buy-shadow-2026-10-09，含独立结果JSON与独立handoff JSON。

## 未满足的上线门槛

- **统计验证**：跨多轮真实历史公司入选池（不是拿10月9日未来筛选名单倒灌到更早交易日）、未来5/10/20日持仓/浮亏/跳空成交及交易费用，估算止损失败、假突破、胜率、收益风险、最大回撤及换手率；用连续样本外期间验证，不能仅看一日READY的数量。
- **正式研究输入**：按新规则从真实每轮冻结工作集完成完整公司研究、每只公司入场条件与风控审计；现有回放仅是继承研究的算法测试。
- **生产契约**：新结果正式发布、SHA回读、handoff投影、实际盘中快照完整运行和连续性校验尚未在生产链验证。此时脚本 production_eligible=false，是**刻意阻断**，不能绕过。
- **定时任务切换**：原“A股低风险买点榜”07:00/19:00定时任务仍保留旧版名称和执行指令。只有上述门槛通过后，才在**同一任务**上改名为“A股趋势买点榜”、更新其唯一入口为skill/TREND_BUY_CANONICAL.md且保持原时区/交易日/时间；独立盘中监控维持原排程。

## 正式数据未覆盖验证

- research/latest_formal_result.json 原 SHA = 790d5c986f504683e8d8caa8b35acf0eee0cbd02；
- research/low_risk_handoff.json 原 SHA = 42280db691a32aa09a6661e6e290529c3f1f1e61。

两者均未被影子计算改写。本报告中的“V2生产已切换”不得在现阶段被宣称成立。
