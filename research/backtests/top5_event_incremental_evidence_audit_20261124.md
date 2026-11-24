# 消息优先＋原排序兜底：历史制度与增量证据核验（2026-11-24）
研究分支，仅诊断。没有修改main、正式榜或定时任务。

## 1. 历史口径全量对账
对上一轮35个次日成熟组，从下一数据提交之前的历史正式结果读取top5_by_theme、READY/WAIT和SW3；逐组证据见同目录 top5_event_formal_state_scope_audit_full_20261124.json（提交 c4da7e28627b3f64e7211a4220afb29b461fbb77）。
35组中32组历史名单及顺序完全一致；10-20半导体、10-23半导体和工业自动化三组不一致，不能用作严格验证。10组同时满足历史名单顺序一致、完整5只、全员已确认、同一SW3；仍非现行全历史重放。
使用旧回顾事件标签、保持READY/WAIT层，收盘至收盘：
|周期|组数|原TOP1均值%|事件优先均值%|原/新领涨命中率%|实际改变榜首数|
|---|---:|---:|---:|---:|---:|
|1|10|0.0543976|0.2285577|10/30|2|
|3|7|-0.6162434|-0.9398297|42.857/28.571|1|
|5|5|-4.0630426|-4.4282624|20/0|1|
全部实际改变为恺英网络，且均WAIT。只有一组次日严格样本榜首READY，未发生改序。无法判断实际成交收益。11-04游戏未进入完整3/5日旧价格数据。剔除恺英事件，榜首增量收益归零。旧标签仍非独立验证。

## 2. 重点游戏样本逐股公开检索（8家，非穷尽）
对11-03/04/05历史名单全部8家分别检索，以下为发现的同期证据，不能据此声称其他公告全覆盖。判断不使用未来价格；已知回测结果，不能称盲测。
- 恺英网络：10-29业绩说明会、三季报披露经营及产品情况。前三季收入+78.11%，归母+30.69%；第三季归母仅+1.22%。SoonPlay 10-20已上线；未验证历史一致预期、盈利预测改变量及信号前定价。潜在催化，尚不能确定组内唯一优先。https://vip.stock.finance.sina.com.cn/corp/view/vCB_AllBulletinDetail.php?id=12679587&stockid=002517 ; https://money.finance.sina.com.cn/corp/view/vCB_AllBulletinDetail.php?id=12670942&stockid=002517
- 世纪华通：10-29三季报、东吴证券10-29报告将26/27/28年利润预测86.1/105.8/124.0亿元调整为86.5/105.9/125.0亿元，至少存在单机构历史预测变化（并非一致预期），幅度有限。https://vip.stock.finance.sina.com.cn/corp/view/vCB_AllBulletinDetail.php?id=12673241&stockid=002602 ; https://stock.finance.sina.com.cn/stock/go.php/vReport_Show/kind/company/rptid/846638541839/index.phtml
- 巨人网络：10-30三季报，前三季扣非+108.72%，单季+27.18%；11-10回购在截止之后。同比不能替代预期差。https://vip.stock.finance.sina.com.cn/corp/view/vCB_AllBulletinDetail.php?id=12680896 ; https://money.finance.sina.com.cn/corp/go.php/vCB_AllBulletin/stockid/002558.phtml
- 吉比特：10-23业绩说明会，境外营收增长及新产品已公开，距11-03超过主窗口，不作为新催化。https://vip.stock.finance.sina.com.cn/corp/view/vCB_AllBulletinDetail.php?id=12660041&stockid=603444
- 三七互娱：10-30三季报及利润分配预案，第三季归母亏损，前三季归母-37.29%；需核实利润分配及盈利预期变化。https://vip.stock.finance.sina.com.cn/corp/view/vCB_AllBulletinDetail.php?CompanyCode=80167146&gather=1&id=12679054 ; https://www.cninfo.com.cn/new/disclosure/stock?orgId=9900018279&stockCode=002555
- 完美世界：10-29/30三季报及投资者交流，《异环》截至10-28全球流水逾27亿元，另有产品获得版号；前三季归母-41.83%，推广费和旧业务拖累。属于恺英同期竞争性产品证据，不能独占事件标签。https://vip.stock.finance.sina.com.cn/corp/view/vCB_AllBulletinDetail.php?id=12675060 ; https://money.finance.sina.com.cn/corp/view/vCB_AllBulletinDetail.php?id=12682224&stockid=002624
- 浙数文化：10-30三季报、董事会披露；暂未从检索验证可超越同组的明确增量催化。https://money.finance.sina.com.cn/corp/view/vCB_AllBulletinDetail.php?id=12676170&stockid=600633 ; https://www.sse.com.cn/assortment/stock/list/info/announcement/index.shtml?productId=600633
- 姚记科技：11-03 00:29报道回购进度，原方案5月已通过，尚未证实进度超原预期。https://stock.stockstar.com/notice/SN2026110300001506.shtml

估值：恢复财务分片 batch5–10，11-04 吉比特11.62、三七18.20、巨人12.77、完美47.93、恺英15.14（均为历史快照pe字段，不假称一致口径远期PE）。11-05 浙数28.93、吉比特11.79、巨人12.82、姚记20.64、恺英15.51。11-03估值实际11-02，带valuation_stale_fallback标记，不冒充当日。无法据PE单独判断是否充分定价。
以上证据不够支持唯一高信心事件提升；保守不改序。该判断为本轮回顾性证据复核，不是新独立收益回测。

## 3. 线下药店样本对称检索（5家）
- 大参林：10-30已公布注销672.23万股（0.5696%）计划；11-16股东会通过，11-18债权通知。新进展为审批落地而非新增回购，尚不足证明重大预期改变。https://paper.cnstock.com/html/2026-10/30/content_2284351.htm ; https://money.finance.sina.com.cn/corp/view/vCB_AllBulletinDetail.php?id=12708646&stockid=603233
- 老百姓：11-17披露9月已公布的5000万元基金投资进展，11-18另有高管工作调整；不自动判定为重大正向催化。https://epaper.cs.com.cn/zgzqb/html/2026-11/17/nw.D110000zgzqb_20261117_3-B030.htm ; https://money.finance.sina.com.cn/corp/view/vCB_AllBulletinDetail.php?id=12712564&stockid=603883
- 益丰药房：11-12闲置募集资金现金管理；回购进展11-19才披露，不回填17/18。https://webf10.gw.com.cn/SH/B14/SH603939_B14.html ; https://money.finance.sina.com.cn/corp/go.php/vCB_AllNewsStock/symbol/sh603939.phtml
- 一心堂：定向检索到11-03现金管理及11-21董事会等，未穷尽窗口内信息；未知，不声明无消息。https://money.finance.sina.com.cn/corp/go.php/vCB_AllBulletin/stockid/002727.phtml?ftype=0
- 第一医药：11-19高管离任披露不用于17/18信号（未证实提前公开）。https://vip.stock.finance.sina.com.cn/corp/go.php/vCB_AllBulletin/stockid/600833.phtml
上述为实际检索的13家（游戏8+药店5），不是110家完整公告检索；未获取所有历史预期及价格定价证据。另有家电、银行主题初步检索，不计逐股覆盖。

## 4. 决策
维持原排序；不满足独立事件、3/5日风险及交易可执行性验收。研究目标仍为新消息的边际定价影响，而非找到事后上涨理由。不要用新的规则阈值拟合上述反例，不因单次收益差把大参林等候选强行提升。继续使用已冻结方案，对尚未覆盖的候选做逐股检索；新增事件在观察未来收益前固定标签，再验证样本外。不宣称完成全量深研或实现样本外验证。
