# 识势 · 独立趋势验证（前瞻性档案）

本目录是**只读研究输出的附属模块**。原版板块榜、趋势买点榜、Python 辅助发现、盘中扫描、Airtable 和仓位管理保持原样。

## 目录

- archive/YYYY-MM-DD/：当日正式 trend_registry、trend_handoff、trend_buy_formal_result、trend_buy_handoff 四份原始文件的不可变副本，另有来源 Git blob SHA 的 manifest.json 和**当日冻结**的板块成分 universe.json。
- prices/YYYY-MM-DD.json：以原 data/history_shards 完成日线生成的增量价格快照；记录市场等权日收益代理，仅追踪仍在验证窗口内的股票。
- results/summary.json、trends.json、stocks.json：由 analyze.py 计算的只读前瞻结果。
- archive_signals.py：只认同交易日、收盘完整正式研究和通过源 SHA 校验的买点 handoff；已有档案永不修改。
- analyze.py：价格、市场基准及生命周期计算；原交易判断不被更改。
- test_validation.py：测试归档断档、次日降级和行情缺口。

## 调度

独立的 .github/workflows/validation-archive.yml 在 main 分支的 research/trend_buy_handoff.json 正式交接文件被提交时尝试自动运行（push/path 触发）；工作日北京时间约 20:10 的 cron 仅用于兜底，并可在 GitHub Actions 手动执行。GitHub 定时运行可能延迟；本模块不修改原正式研究工作流，也不修改原研究文件。若上游由 Actions 默认 GITHUB_TOKEN 提交而未产生 push 触发，20:10 兜底仍会尝试执行。

## 验证口径（第一版）

1. 板块事件：首次正式「趋势确认」开启一个确认事件，连续确认按交易日计数；首次降为非确认状态记录 lost_confirmation，**不等于产业趋势完全失效**。缺失完整归档时记录 censored_data_gap，而非成功或失败。
2. 未来收益：信号日完成日收盘价到第 1/3/5/10/20 个完整交易日收盘价。该指标是**前瞻观察结果**，不是假设可在信号日收盘买入。冻结同日成分股，计算等权买入持有的平均收益；覆盖率不足 90% 不出结论。
3. 市场基准：来自历史分片当日具有有效新鲜日线的主板股票的等权日收益均值，逐日复利。它是**市场代理**，不是沪深300等可交易指数；无完整日价格归档则不计算超额收益。
4. 个股：分别保留每日正式研究中 READY、WAIT、UNCERTAIN、DROP 的原样状态，记录其事后收盘收益和相对**当日冻结板块篮子**的超额收益。**第一版不模拟 READY 交易触发、止损、滑点，不宣称真实策略收益。**
5. 样本不足、右删失、停牌缺失、价源/复权口径不一致应当保持 pending 或 data_gap。连续多日同一股票信号属于相关样本，不得当作独立统计显著性证明。

## 边界

- **所有**归档和行情增量写入均在 validation/ 内；原研究文件只读。
- 每日档案首次写入后不会因榜单更新而覆盖。首次上线前不存在完整正式快照的交易日不冒充历史正式信号。
- 代码、数据和前端要部署运行后才会产生真实统计结果；没有样本时页面应显示数据积累中。
- Python 单元测试：python -m unittest discover -s validation -p 'test_*.py' -v。
