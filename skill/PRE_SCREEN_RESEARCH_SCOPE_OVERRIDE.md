# A股趋势买点榜｜V4唯一正式预筛与模型深研范围

> 正式版本：V4-B1（自切换后的下一次完整研究日生效）。本协议取代旧版“70%机会+30%财务、允许并列第6名”的前置选股定义。仅有一条正式选股链；旧方案不再运行或用于正式候选递补。

## 1. 唯一执行顺序

```text
同日且独立确认CORE/DIRECT受益的申万三级行业
 → 已冻结的完整行业Universe、manifest和company index
 → Python全量硬过滤、低成本量价/财务/多周期同业扫描
 → V4-B1：每三级行业3席LEADERSHIP + 2席ENTRY_LOCATION（最多5家）
 → 只对这至多5家公司做当日大模型公告/业绩/预期/反证深度研究
 → 模型对所研究公司给出同主题内唯一v4_model_rank及可核对的v4_model_reason
 → 原独立技术买点、结构失效、赔率与READY/WAIT风控Gate
 → 唯一正式Top5、result和handoff
```

**生产实现**：`scripts/v4_prepare_research_candidates.py` 产生并验证 `research/trend_buy_v4_candidates/latest.json`；`scripts/build_trend_buy_manual_research.py --v4-admission ...` 校验并且只能消耗该名单；`scripts/trend_buy_engine.py` 将模型研究次序应用于READY/WAIT的相应层内，并保持交易风控独立。

## 2. 输入与硬过滤

- 只读正式同日期的`research/trend_handoff.json`、`data/low_risk/index.json`与manifest全部parts。只有已确认、直接受益、经趋势登记配对Gate校验的三级行业有资格。 **绝不能据此跳过上游唯一的“趋势确认＋独立受益申万三级行业”Gate**：Python扫描与V4模型排序均无权将观察/候选行业、RELATED外围公司或未确认板块升级为正式买点研究范围。
- 全量轻量扫描，模型不得先查全行业。工作集同日冻结，历史K线不能包含未来记录；不足65根有效K线、当日价格口径偏差超过1.5%或关键技术信息不可靠的公司不得占V4研究席位。
- 保留原有硬过滤：ST/退市；价格、均线、估值或关键财务缺失；营收同比小于-20%且归母净利同比小于-50%。此处硬过滤与正式技术入场准入不同，低于MA60本身不是淘汰原因。
- 已知同行主营不符合主题、公告明确证伪关联，必须标记`NOT_SUPPORTED`；未知时模型研究后只能`UNCERTAIN`或阻断，不可按推断补造商业证据。

## 3. V4-B1同业双通道预筛

同一申万三级行业hard-eligible公司内，用截至本日的已验证日K，计算10/20/60日相对同行中位数收益分位、近10日上涨次数和当前入场结构代理。全行业轻量扫描后按**两个独立通道**选人：

- **持续领涨3席**：多周期强弱和10日持续性合成分 `continuity=.40*20d_pctile + .30*60d_pctile + .20*10d_pctile + .10*positive10_pctile`，最终领导分 `0.80*continuity + 0.20*fundamental_score`。
- **当前位置2席**：`0.65*entry_reference_score + 0.20*price_structure_score + 0.15*fundamental_score`。
- 每个通道按分从高到低取人，交叉去重；最后一个通道不足时只在已全量验证且有资格的同行中补位，**绝不加第6席**。有效同比较公司不足3家，必须报告数据不足，不以模型补造分位与成员。
- 财务基础分是经过F10报告期、公告发布时间、更新日期与冻结交易日审计后的`CORE_FIRST`同业质量评分。**优先扣非净利润同比**，缺失才回退既有扣非EPS或归母同比；额外考察经营现金流、非经常性收益占比、估值和利润兑现可靠性。不得以同比高增证明已经超市场预期。
- 参数目前是已声明的V4研究假设，**不是可靠的未来收益预测概率**；程序先缩小研究范围，后续模型进行业务和财务证据核验，不能将Python分数直接输出为最终买点排序。

## 4. 模型深研与最终排序

仅可对程序入选每个三级行业最多5家公司查阅上市公司公告、交易所披露、历史财报、扣非利润、经营现金流、新品/订单兑现、可信一致预期变化和重大反证。必须记录来源URL、`published_at<=trade_date`、所属财报期，以及模型推断与已知事实之间的区别。缺少可信当时一致预期时标记UNKNOWN，不凭主观填数。

当日`research/trend_buy_company_reviews/latest.json`的`reviews`代码集合必须与已冻结的V4候选**完全相同**。对真实传导成立、材料有来源的公司提供`v4_model_rank`正整数（同主题不重复）及不少于24字符的`v4_model_reason`，解释财务与预期、行业商业逻辑、市场相对强度和反证。研究不足、模型名次缺失、来源超时点一律`BLOCKED`，不得复用旧版已深研公司或旧模型名次。

**最终展示顺序**：先经独立准入Gate得到READY/WAIT；READY先于WAIT，同状态内采用已核验的模型研究顺序，技术持续性和入场风险作为说明与等位核查。即使模型排名第一也不能升级READY。经证伪公司从最终候选淘汰；不能为了凑5家公司调用额外模型全行业扫描。

## 5. 正式发布与失败处理

- `research/trend_buy_v4_candidates/latest.json`应有同日`trade_date`、完整三级行业集合、每行业1~5只公司、数据源SHA256、`prescreen_version=V4_B1`及`PROGRAM_VERIFIED_MODEL_RESEARCH_PENDING`。生成后READBACK校验，不可由大模型凭印象构造代码名单。
- `run-trend-buy-formal.yml`只能在经过同日程序预筛、同日公司深研证据以及独立买点风控全套Gate后发布唯一`research/trend_buy_formal_result.json`和`research/trend_buy_handoff.json`；来源、日期、Git Blob SHA不一致时停止发布。
- 上游合法零确认行业时报告`NO_ELIGIBLE_CONFIRMED_TREND`，不复用旧榜；非零行业但数据缺失或无有效可研究公司时报告明确阻断。
- 保留技术买点/结构止损、风险≤6%、上方已核验阻力≥1.5R、短期过热>8%相关防追涨规则、READY/WAIT以及handoff只允许条件入场的既有契约。
- 不允许独立第二套日常V4榜单、原规则平行发布或第二个模型深度研究调度；历史PR仅供审计。
