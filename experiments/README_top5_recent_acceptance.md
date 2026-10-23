# Top5近期承接观察试验（SHADOW ONLY）

**目的**：给正式主题Top5补充可复核的*本轮*（最近5–10日趋势背景、当日向前1–3日观察）承接证据，在验证前**不修改正式榜单排序、基本面预筛、买点规则、READY/WAIT、风控阈值、定时任务或交易交接**。

## 唯一事实范围

- `--asof` 日期必须与现有正式研究冻结日一致，历史日K严格截断至该日。
- 对每只已入选股票比较当日与其前1～3根日K的最低价：在前期低点上下0.5%内测试并强势收回，标为 `LOCAL_SUPPORT_HOLD`；先跌破前期低点0.5%以上、当日放量强势收回，则为 `SAME_DAY_SWEEP_RECLAIM`。否则仅观察，不能给止损。
- 观察价用**截至该日的收盘价**，假设零滑点，仅用于横向比较；观察失效代理：守住旧低点则用该低点下0.5%，假跌破重新收回则用当日新低下0.5%；不拿旧趋势起点或长期均线代替近端失效价。
- 用同日可核验**最近上方历史阻力**计算`conditional_close_R`。历史高点只用作当前的近端障碍，不用来形成止损。
- 结构以日K为证，缺乏分时成交分布：只得出“当天观察到的承接形态”，**不能证明这是本轮第一次承接**。一日强收盘也不能保证下一交易日有效。所有结果固定`SHADOW_OBSERVATION_NOT_EXECUTABLE`，不升级READY。
- 正式1.5R与6%不是用本工具执行Gate；这里只并排展示同口径是否越线，保留证据不足和参数敏感性，**无通过候选则不强排买入序号**。

## 执行

```bash
python experiments/top5_recent_acceptance_shadow.py --asof 2026-10-23
python experiments/top5_recent_acceptance_shadow.py --asof 2026-10-23 --lookback 1
python -m unittest discover -s tests -p 'test_top5_recent_acceptance_shadow.py' -v
```

可以用`--output /tmp/top5_shadow.json`写入单独临时文件；脚本禁止覆盖`research/trend_buy_formal_result.json`。

**边界与下一步**：仅依靠5只、1个交易日无法证明更好的排名，也无法验证“第一次”的序号属性。需要足够多的历史正式Top5冻结日与事后独立的后续收益/止损结果（严格防未来数据）后，再与旧30/30/25/15排序比较，评价买点确认率、兑现的R、风险和回撤。没有这类跨日数据与验证结果，不应替换正式Top5。
