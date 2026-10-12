# 持仓补充行情监测

- 本功能不会修改正式 trend-buy handoff，也不会改变 READY/WAIT 研判。
- 仓库的 research/holding_watchlist.json 仅保存代码、名称、同步日期；不保存股数、成本、交易明细和 Airtable 密钥。
- scripts/build_intraday_snapshot.py 将持仓股票代码合并到行情目标集合，去重后获取 Sina/Tencent 快照，并独立输出 holding_stocks。
- dashboard/api/data.js 的受保护接口提供行情快照，现有首页与我的持仓风险判断可以使用有效同日持仓补充报价；没有修改界面布局。
- 在 GitHub 仓库 Settings > Secrets and variables > Actions 中新增三个 repository secrets：AIRTABLE_TOKEN、AIRTABLE_BASE_ID、AIRTABLE_TABLE_ID。三项齐全时盘中快照 workflow 会先从 Airtable 同步持仓，再查询报价。
- 缺少上述密钥时使用仓库中的已提交名单；名单不会随新买卖自动变更，需要人工维护。若 Airtable 请求或交易记录校验失败则任务失败，绝不静默重用过期名单冒充最新持仓。
- 密钥仅需 Airtable 的 data.records:read 权限，仅授权交易复盘日志 base。
- 验证：python -m unittest discover -s tests -p test_holding_watchlist.py；cd dashboard && npm test。
