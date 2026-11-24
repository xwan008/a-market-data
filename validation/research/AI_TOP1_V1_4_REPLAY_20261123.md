# V1.4 指定来源历史回放｜2026-11-23收盘
RESEARCH_ONLY / INCOMPLETE / NOT_VALIDATED。目标截止为11/23北京时间19:00，与前次回放一致。2026-11-24事后重新搜索，不复用前一报告的数据或选择；对话中已接触未来行情，不能算盲测。提示词blob 89609a4f1a2272ca84818518f4c6e8687573f40b；冻结候选blob 3057ef2f8e90419f3b9bf95ebfd5448d6fa11e52；当日技术归档blob 59e60aaca0807df724e477300c4b31f73d20b28d。原分项分数未取到，可选字段。未查询未来收益用于本轮选择，网页包含11/24行，排除。精确模型版本、每条网页首次可得时间UNKNOWN。

## A. 来源优先级执行与实际结果
对15只候选均直接打开 https://data.eastmoney.com/zjlx/{code}.html ，可打开页面，但工具未返回可用历史资金数据行。查询同花顺资金中心 https://data.10jqka.com.cn/funds/ggzjl/ ，可读当前排名而非固定11/23历史窗口；江化微 https://stockpage.10jqka.com.cn/603078/funds/ 历史行只到5月；万润 https://stockpage.10jqka.com.cn/002643/funds/ 仅加载占位。进一步尝试证券之星 https://quote.stockstar.com/cashflow/ 及个股历史表/限定搜索；部分个股可访问，部分超时。未完成所有个股同花顺、证券之星逐项直达及10/20日扩展检索，不能标全流程完成。
原始资金数值已覆盖15/15（非全组同口径验收）。单位亿元，5日为11/17、18、19、20、23五个交易日的近似加总。准上市页面标注东财口径且11/23价格与冻结一致；证券之星与准上市重叠记录（沪电、中京）日金额、占比吻合；崇达来自证券之星大单+超大单。江化微、万润来自芦苇复盘逐日表（原供应商未确认），江化微当日金额与证券之星摘要吻合；万润11/18金额与证券之星摘要吻合。不能凭这些抽查证明全部口径一致，也不能以当日行日期证明11/23 19:00前可得。
| 组 | 原排名 | 股票 | 当日资金 | 5日资金 | 来源 |
|---|---:|---|---:|---:|---|
| PCB |1|002579 中京电子|2.89|8.54|准上市/证券之星交叉|
| PCB |2|603386 骏亚科技|0.09|1.10|准上市|
| PCB |3|603920 世运电路|1.26|0.93|准上市|
| PCB |4|002815 崇达技术|3.99|5.63|证券之星|
| PCB |5|002463 沪电股份|3.50|22.50|准上市/证券之星交叉|
| 电子化学品 |1|603931 格林达|0.46|0.80|准上市|
| 电子化学品 |2|002741 光华科技|1.12|3.38|准上市|
| 电子化学品 |3|603078 江化微|0.446|3.57约|芦苇复盘|
| 电子化学品 |4|002643 万润股份|-0.060|-0.261|芦苇复盘|
| 电子化学品 |5|002584 西陇科学|2.18|2.43|准上市|
| 银行 |1|601658 邮储银行|0.25|-1.27|准上市|
| 银行 |2|601288 农业银行|2.04|-4.77|准上市|
| 银行 |3|601939 建设银行|-2.85|-6.97|准上市|
| 银行 |4|601328 交通银行|2.53|6.87|准上市|
| 银行 |5|601988 中国银行|0.94|0.02|准上市|
具体来源：准上市 https://www.zhunshangshi.com/hq/detail.php?tab=flow&ts_code={六位代码}.{SH或SZ} （实际读取12只，中京、骏亚、世运、沪电、格林达、光华、西陇及5家银行）；崇达 https://stock.quote.stockstar.com/capital_002815.shtml ，5日五行金额合计约5.63亿；沪电 https://stock.quote.stockstar.com/capital_002463.shtml ；中京 https://stock.quote.stockstar.com/capital_002579.shtml 。江化微 https://www.lwwhy.com/stock/detail/SH603078 （11/23到11/17主力净额分别4459.9万、-4651.9万、约2亿、7051.9万、8768.9万，超大单与大单的舍入值可用于约3.57亿估算）；万润 https://www.lwwhy.com/stock/detail/SZ002643 （-599.2、-97.8、-216.6、-464、-1235.9万元），两者11/23至11/17均取得数值。首选及备用未读到这两只股票的完整历史表，不将其记为同一口径已通过。证券之星同日摘要 https://wap.stockstar.com/detail/RB2026112300034887 ; https://wap.stockstar.com/detail/RB2026111800041315 。证券之星建设银行11/23资金榜与农业银行榜交叉验证 https://quote.stockstar.com/cashflow/main/day1_6_1_1.html ; https://quote.stockstar.com/cashflow/main/day1_4_1_2.html 。同日其他统计报道存在口径差异 https://stock.stockstar.com/IG2026112300026613.shtml （不混用）。

## B–E. 本轮定向搜索记录（部分，不当成完整矩阵）
PCB：巨潮逐股定向查询，沪电回购、骏亚增资、中京异常波动、崇达子公司撤回北交所上市材料/业绩说明会、世运回购专项贷款承诺函均找到公告索引或正文入口。来源 https://www.cninfo.com.cn/new/disclosure/stock?orgId=9900013929&stockCode=002463 ; https://www.cninfo.com.cn/new/disclosure/stock?orgId=9900033000&stockCode=603386 ; https://www.cninfo.com.cn/new/fulltextSearch?keyWord=002579 ; https://www.cninfo.com.cn/new/fulltextSearch?keyWord=002815 ; https://www.cninfo.com.cn/new/commonUrl/pageOfSearch?code=603920&endDate=2026-11-11&name=%E4%B8%96%E8%BF%90%E7%94%B5%E8%B7%AF&orgId=9900030580&startDate=2026-11-11&url=disclosure%2Flist%2Fsearch 。东方财富研报搜索，太平洋11/17预计沪电2026净利81.21亿元，属于单家预测，尚未核验全组市场预期： https://data.eastmoney.com/report/info/AP202611171831776413.html 。证券时报引用行业协会1–6月四层以上PCB出口额同比47.74%，但原料涨价及扩产风险存在，不能直接等同各股新增盈利： https://www.stcn.com/article/detail/4171840.html 。其余股票当期公告全文、市场预期与风险检索范围仍未全面核验。
电子化学品：巨潮搜索格林达三季度经营数据、江化微异常波动、西陇账户冻结进展；万润同花顺大事及证券之星互动记录显示九目化学注册批复、光刻胶原材料国内外均有销售、PEI试生产等。https://www.cninfo.com.cn/new/disclosure/stock?orgId=9900039864&stockCode=603931 ; https://www.cninfo.com.cn/new/commonUrl/pageOfSearch?code=603078&endDate=2026-11-20&name=%E6%B1%9F%E5%8C%96%E5%BE%AE&orgId=9900030584&startDate=2026-11-20&url=disclosure%2Flist%2Fsearch ; https://www.cninfo.com.cn/new/fulltextSearch?keyWord=002584 ; https://basic.10jqka.com.cn/002643/event.html ; https://stock.quote.stockstar.com/002643.shtml 。光华公告、全组近期行业传导与个股市场预期的完整核验未完成。
银行：国家金融监督管理总局11/20公布三季度商业银行拨备覆盖率199.49% https://www.nfra.gov.cn/cn/view/pages/ItemDetail.html?docId=1279786 。银行IR定向查询邮储11/6高管离任、农行公告列表、建行11/17非执行董事任职、中行11/17二级资本债赎回；交通银行三季报新浪公告正文入口、长江证券11/16研报称息差回升及利息净收入增速提升。https://www.psbc.com/cn/gyyc/tzzgx/gsgg/aggg/ ; https://www.abchina.com/cn//AboutABC/investor_relations/announcements/a-announcement/ ; https://group3.ccb.com/chn/home/investor/news/ybgg/index.shtml ; https://www.boc.cn/investor/ir5/index.html ; https://vip.stock.finance.sina.com.cn/corp/view/vCB_AllBulletinDetail.php?id=12685332 ; https://stock.finance.sina.com.cn/stock/go.php/vReport_Show/kind/search/rptid/848205260525/index.phtml 。研报市场预期和各股风险检索范围未全面完成。

## V1.4 gate
三组输入核验PASS。A原始数值覆盖15/15，口径与历史可得时间仍有缺口；未完成全部候选的10/20日检索尝试及B–E逐股完整证据矩阵（部分只定位索引或摘要），FAIL。全组正式比较、反证检查未达到输出条件，FAIL。V1.4只变更来源优先级，不改变V1.3硬门槛。
S270202 / S270601 / S480201: status=INCOMPLETE, top1_code=null, confidence=null。此次不输出临时TOP1，不用先前回放或未来收益补足。数值原始覆盖比前次改善，不能证明完整流程可运行；生产保持不变，不新增采集工程。