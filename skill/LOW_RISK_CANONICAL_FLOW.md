# A股低风险买点榜｜唯一主流程

本文件定义“A股低风险买点榜”的唯一主流程。若其他协议/Override 对执行顺序、Universe 来源、数据读取方式存在冲突，以本文件为准；其他文件只负责各阶段具体判定算法。

## 1. 唯一主流程

```text
Trend Handoff
→ 解析本轮三级行业
→ 读取 data/low_risk/index.json
→ 对每个 routed 行业读取 manifest.json
→ 按 manifest.parts 顺序读取全部 part-xxx.json，并在本轮上下文中拼接完整行业事实
→ 校验 manifest / parts / index 覆盖完全一致
→ 映射为本轮 run-local working set
→ Freeze；以下阶段不再读取任何 company_industry_index / shard / low_risk manifest / part / legacy 单文件
→ 公司级硬过滤
→ 行业内轻量预筛（Top5 / 并列第6）
→ Transmission（SUPPORTED / EARLY_EVIDENCE / NOT_SUPPORTED / UNCERTAIN）
→ Expectation（仅 SUPPORTED；EARLY_EVIDENCE 留在独立观察池）
→ 行业自适应估值 + 价格结构
→ reasonable_price_range / low_risk_buy_range
→ READY / WAIT / UNCERTAIN / DROP
→ 正式榜单
```

不得建立第二套并行主流程。

### 正式版 / 手动版 Fresh Run 纪律

19:00 正式版与任何手动正式版，每次执行都必须从 Trend Handoff 开始重新完整执行本文件主流程。上一轮 `latest_formal_result.json`、上一轮 working set、上一轮 pre-screen、Transmission、Expectation、valuation / Price Range 结论只能用于任务结束后的对比，不得作为本轮计算输入，也不得用于跳过任何阶段。

07:00 早间版是唯一允许基于上一份 COMPLETE 做增量复核的例外，具体规则由 `RUNTIME_READ_PROTOCOL.md` 定义。

### 运行时 UTF-8 字节校验前置自检（正式版/手动版强制）

在本轮首次读取 data/low_risk/index.json、manifest 或 part **之前**，必须在本轮实际分片校验所用的同一执行环境完成校验器自检。禁止假设 TextEncoder、Node Buffer 或浏览器全局对象一定存在。优先使用下面无需任何外部 API 的严格 UTF-8 字节计数器；若改用 Python 3，可对**同一原始正文**以 len(raw.encode("utf-8")) 等价校验。

```javascript
function exactUtf8ByteLength(s) {
  let n = 0;
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    if (c <= 0x7F) n++;
    else if (c <= 0x7FF) n += 2;
    else if (c >= 0xD800 && c <= 0xDBFF) {
      const next = s.charCodeAt(++i);
      if (!(next >= 0xDC00 && next <= 0xDFFF)) throw new Error("INVALID_UTF16");
      n += 4;
    } else if (c >= 0xDC00 && c <= 0xDFFF) throw new Error("INVALID_UTF16");
    else n += 3;
  }
  return n;
}
```

自检必须在同一执行环境实际执行并断言：ASCII 为 5 字节、中文“中”为 3 字节、表情“😀”为 4 字节、字符串 `A中😀` 加一个实际 LF 换行共 9 字节；不完整 UTF-16 代理项必须抛错。Python 替代实现也要进行对应严格编码测试。自检未执行、无法执行或不通过时，报 RUNTIME_BYTE_VALIDATOR_UNAVAILABLE，停止本轮 Working Set 文件读取及后续研究/写入，绝不跳过 byte_size Gate。

**byte_size 精确定义：** 生产脚本 scripts/build_low_risk_working_sets.py 通过 json.dumps(payload, ensure_ascii=False, indent=2) 加末尾 LF 换行，再按 UTF-8 写入 part；manifest.parts[*].byte_size 是这一**完整原始文件文本**的 UTF-8 字节数（含缩进、空格及末尾换行），不是压缩或重新序列化后的 JSON 长度。读取 part 后保留未经变更的从第 1 行到 EOF 的 raw 正文，直接核对 exactUtf8ByteLength(raw) === manifest 中对应 byte_size，然后再 JSON.parse(raw) 并验证身份、计数及覆盖。不得通过 JSON.stringify、去除或增加末尾换行、换行归一化，或复制工具附加行号的显示文本去核对长度。

如工具明确截断，沿用原有从第 1 行连续分页至 EOF 的唯一许可并无损拼接，再校验；已完整返回的 part 禁止重新分页或再次读取。如果无法确认原始文本完整、字节等价，报 PART_RAW_TEXT_UNVERIFIED；若实际字节数不一致，报 PART_BYTE_SIZE_MISMATCH。两种情况都不得 Freeze 或发布。

**同轮失败恢复：** 对已完整读取的 part 绝不重新获取。若本轮全部原始内容与来源仍无损保留在本地，只允许在缓存上重新执行修复后的校验（不增加读次数），并重做全部身份/覆盖 Gate；缓存不存在、本轮已结束时，保持失败且不覆盖原 COMPLETE 或 handoff。下一次独立 Fresh Run 必须先自检，再重新按既定规则读取本轮 index、handoff、manifest 与全部 parts；不能复用上一轮缓存或研究结论。

## 2. 第一步：Trend Handoff 只决定行业

读取 `research/trend_handoff.json`。

只负责：
- 当期新仓优先趋势；
- 对应申万三级行业代码；
- 趋势/市场状态透传。

不负责个股准入、个股估值或买入区间。

## 3. 第二步：从预物化行业事实生成本轮 Working Set

### 3.1 数据权威与运行时视图

低风险榜的数据权威没有改变：
- Universe 权威来源：`data/research/company_industry_index.json`；
- 公司事实权威来源：`data/shards/<前5位>.json`。

正式版 / 手动版运行时不得现场解析上述大 JSON。GitHub Actions 每次有效正式收盘后运行 `scripts/build_low_risk_working_sets.py`，确定性执行：

```text
company_industry_index.json + data/shards/*.json
→ industry partition / exact join / standard fact projection / validation
→ data/low_risk/index.json
→ data/low_risk/by_industry/<industry_code>/manifest.json
→ data/low_risk/by_industry/<industry_code>/part-001.json ...
```

迁移期暂时继续生成旧 `data/low_risk/by_industry/<industry_code>.json`，但新正式主流程禁止读取该 legacy 单文件。

chunk 生产约束：
- 每 part 默认最多 5 家公司；
- 每 part 紧凑 JSON 默认不得超过 96 KiB；
- 若达到字节上限，允许少于 5 家；
- 单家公司本身超过上限则构建失败；
- manifest 必须列出全部 part、各 part 的 company codes、company_count 与 byte_size。

GitHub 构建必须保证 mapped company coverage、industry partition、trade_date、industry mapping、chunk manifest、chunk company coverage 与 chunk size 全部校验通过；否则不得提交半成品。

### 3.2 Runtime Materialized View Gate

先读取 `data/low_risk/index.json`，必须满足：
- `runtime_format == "low_risk_industry_working_set_index"`；
- `validation.status == "passed"`；
- `materialized_layout == "chunked_manifest_v1"`；
- `validation.chunk_manifest_complete == true`；
- `validation.chunk_company_coverage_exact == true`；
- `validation.chunk_size_within_limit == true`；
- `trade_date == 本轮最新有效正式收盘 trade_date`。

对每个 routed 行业：
- 若存在于 index，必须读取其 `manifest_file`；
- 若在已通过全量覆盖校验的 index 中不存在，标记 `NO_UNIVERSE_MEMBER`；
- `manifest_file` 必须指向 `data/low_risk/by_industry/<industry_code>/manifest.json`；
- index 中 `legacy_file` / `file` 只用于迁移兼容，正式版 / 手动版不得读取。

任何 index / manifest / part 无效时阻断 Working Set Gate；不得回退读取完整 company_industry_index、shards 或 legacy 单文件。

### 3.3 Manifest + Chunk 读取协议

对每个 routed 且有 Universe 的行业：

1. 读取一次 `manifest.json`；
2. 校验：
   - `runtime_format == "low_risk_industry_working_set_manifest"`；
   - `layout_version == 1`；
   - trade_date / industry_code / industry_name 与 index 一致；
   - company_count 与 index 一致；
   - `len(universe_company_codes) == company_count`；
   - `chunking.part_count == len(parts)`；
3. 按 `parts[*].part_number` 升序读取全部 part。part 文件是 pretty-print 多行 JSON，且由生产层限制为有界大小；默认每个 part 使用一次完整文件读取（不指定行范围），该次返回必须覆盖第 1 行到 EOF。只有工具明确返回截断、响应大小限制或无法获得完整 EOF 时，才改用行范围分页（推荐每段 100–150 行），从第 1 行连续读取到 EOF。已一次完整返回的 part 禁止再次分页或重读；
4. 将同一 part 的 segment 按行顺序无损拼接成完整原始正文，先按本文件的前置 UTF-8 协议验证 manifest 对应的 byte_size，再成功解析完整 JSON；只有字节、解析及下列字段校验全部通过后才计为 1 次逻辑 `materialized_part_read_count`；
5. 每个 part 必须满足：
   - `runtime_format == "low_risk_industry_working_set_chunk"`；
   - trade_date / industry identity 与 manifest 一致；
   - part_number 与 manifest entry 一致；
   - `company_count == len(company_codes) == len(companies)`；
   - `set(companies[*].code) == set(company_codes)`；
   - company_codes 与 manifest 对应 entry 完全一致；
6. 拼接全部 part 的 companies 形成该行业 run-local working set。

公司事实字段仍至少覆盖 code/name、价格/市值、PE/PB/ROE、收入利润现金流、MA20/MA60、60日高低与位置、support/resistance/dense/volume zones、trend_state/break_state/invalidation 等硬过滤、预筛和估值所需事实。

### 3.4 Freeze Gate

Freeze 前每个 routed 行业必须证明：

```text
manifest.trade_date == index.trade_date
manifest.company_count == len(manifest.universe_company_codes)
manifest.company_count == sum(parts[*].company_count)
manifest.parts 中 company_codes 的按序拼接 == manifest.universe_company_codes
实际读取 part company codes 的按序拼接 == manifest.universe_company_codes
set(all part companies[*].code) == set(manifest.universe_company_codes)
不存在重复 code
index.industries[industry_code].company_count == manifest.company_count
实际完整解析并校验通过的逻辑 part 数 == manifest.chunking.part_count == index.industries[industry_code].part_count
working_set_count == routed_industry_with_universe_count
working_set_company_count == sum(routed industries with universe 的 company_count)
```

通过后 Freeze。此后硬过滤、预筛、Transmission、Expectation、估值和价格区间只消费 frozen working set；不得再读取 company_industry_index、shards、manifest、part 或 legacy 单文件。

## 4. Stage A：公司级硬过滤

只对 frozen working set 中的公司执行公司级硬条件：
- ST；
- 无效/非正价格；
- 关键数据严重缺失；
- revenue_yoy < -20% 且 net_profit_yoy < -50%；
- 其他正式协议公司级硬条件。

行业景气字段不得作为个股准入 Gate。

## 5. Stage B：行业内轻量预筛

仅对 hard-eligible 公司，使用 working set 已包含的：
- 收入增长；
- 核心利润增长；
- 现金流/一次性收益质量；
- 估值；
- 60日位置。

每个三级行业原则上 Top5；第6名与第5名满足既定 tie 规则时可一起进入，最多6家。

未进入深研：`PRE_SCREENED_OUT`。

## 6. Stage C：Transmission

只对 pre-screen selected 公司验证行业趋势与公司业务的可归因传导。未来 1–2 季度是重点研究窗口，不是 SUPPORTED 的强制订单兑现或精确利润预测门槛。已核实的、与本轮趋势直接相关的有效订单、客户认证、明确商业化项目或实际交付，可以支持商业传导；必须核验其与本轮趋势的直接关联，不能把普通业务订单冒充趋势订单。只有政策、技术储备或研发进展且已核实公司直接业务关联、但尚无可靠商业验证时记 `EARLY_EVIDENCE`，进入独立观察池，不进入 Expectation、READY/WAIT 或正式 handoff。订单兑现时间、盈利弹性与市场计价的不确定性移交 Expectation 和 Risk–Reward，不因缺少精确季度利润预测而判 UNCERTAIN。

按 `EXECUTION_EFFICIENCY_OVERRIDE.md` **两步搜证**：每行业一次研究批次，批次内按具体产业环节分组（每组约 2–3 家）并行短查询，覆盖公告、财报、交易所披露及 IR，不限单一检索站点；批量后逐家检查无来源、证据过期及遗漏趋势相关业务的缺口，只有补证可能改变判断时才对该公司最多一次定向补证。Web/公告/IR 只补 working set 不可能提供的前瞻证据；不机械要求每家公司单独公告、精确利润预测或额外重复检索。

每家入选公司都须有独立判断记录：关键证据及来源（允许共享行业来源，但必须验证公司关联）、行业驱动→业务敞口→商业传导证据/未来兑现窗口、未解决缺口/反证及最终 Transmission 状态。正常搜证仍不能确认公司直接关联或关键商业事实时记 UNCERTAIN；仅政策主题而无可核实公司直接业务关联不能标 EARLY_EVIDENCE。对拟判 UNCERTAIN/NOT_SUPPORTED 者必须检查已取得的一手公告、财报、IR 中是否存在与结论相矛盾的相关订单、客户认证或交付证据；发现具体矛盾时先做必要定向核查。必要检索因工具故障未执行或已发现的关键矛盾未核清时记 RESEARCH_INCOMPLETE，不进入发布。

### Transmission Research Gate

正式发布前验证：全部 pre-screen selected 公司均有上述可追溯记录，并逐家记录具体趋势业务关联、所属批量短查询、取得证据及新鲜度、无来源/过期/遗漏业务的缺口检查结果、是否需要定向补证及执行结果或不补证理由；EARLY_EVIDENCE 必须单列并记录公司直接关联证据、尚未商业验证的缺口与下一次验证触发条件；各 Transmission 状态计数之和必须等于 pre_screen selected 去重公司数；存在可能改变判断的可核查关键缺口时，必要补证须已执行。无来源不自动视为完成研究；无可核查关联或补证不会改变判断时可不补查，但必须说明。不存在未完成的必要检索或以统一模板冒充独立判断。

全部满足时 `coverage.transmission_research_gate = "PASSED"`，否则为 `"FAILED"`，不得发布 COMPLETE。该 Gate 仅检查研究是否真实充分执行，不要求出现 READY/WAIT，不改变 SUPPORTED、EARLY_EVIDENCE、NOT_SUPPORTED、UNCERTAIN 或估值/价格区间标准。

## 7. Stage D：Expectation

只对 Transmission=SUPPORTED 公司判断：EARLY / CONFIRMING / PRICED_IN / EXHAUSTED / UNCERTAIN。Transmission=EARLY_EVIDENCE 仅留在独立观察池，不进入 Expectation、READY/WAIT 或正式 handoff。

## 8. Stage E：行业自适应估值与买点

只使用 frozen working set 的估值、财务与价格结构事实，再结合前两阶段必要的前瞻结论：

```text
行业估值原型
+ 同行业 hard-eligible peer statistics
+ 公司增长/ROE/现金流/盈利质量修正
→ fundamental_anchor_price

fundamental_anchor_price
+ MA60 / support / volume-zone
→ reasonable_price_range

reasonable_price_range
+ 行业与60日波动安全边际
→ low_risk_buy_range
```

技术结构只负责择时，不得抬高基本面估值上限。

“没有完整 DCF”本身不得作为 UNCERTAIN 理由。

## 9. 唯一最终状态与交接契约

公司研究最终 `status` 仅允许 `READY / WAIT / UNCERTAIN / DROP` 四种主状态；`WAIT_PRICE / WAIT_MARGIN / WAIT_EXPECTATION / WAIT_CATALYST` 只是 `wait_reason` 的合法枚举，不是新增主状态。WAIT 必须具备合法的 `wait_reason`，READY 的 `wait_reason` 为 null。原有自然语言 `wait_reason` 描述另存为 `wait_reason_detail`，不得混用分类字段。分类语义及价格区间 Gate 由 `SKILL.md` 和 `PRICE_RANGE_OUTPUT_OVERRIDE.md` 负责。

正式结果 `ready` / `wait` 数组，以及用于后续盘中监控的 `research/low_risk_handoff.json.items` 必须使用完全相同的 `status` 和 `wait_reason`；handoff 逐项复制正式结果中全部 READY/WAIT 的公司、原排序、交易日期、买入区间和触发条件。写入前与写入回读后校验公司代码集合、数量、rank、status 与 wait_reason 精确一致。不认识的主状态和不合法/缺失的 WAIT 原因必须阻断发布，绝不静默过滤成空榜。07:00 增量版沿用同一状态契约，不自行改写正式 handoff。

### 9.1 资金流向与量价配合（非决策性观察）

**定位与执行顺序：** 本节只为已按原主流程完成研究和价格区间判定的个股增加辅助观察，尤其为最终 READY/WAIT 榜单提供量价与资金流向的风险提示。先按既定硬过滤、Top5/并列第6预筛、Transmission、Expectation、Risk–Reward 和买入区间规则完整确定最终状态与原排序，再附加资金观察；不得把资金数据提前加入 Universe、硬过滤、预筛分数、Transmission、Expectation、估值、买入区间、安全边际、READY/WAIT 或 handoff 的计算。资金观察不生成新的状态或等待原因；持续流出时只提示按**原有**价格结构与基本面规则复核，不能直接将 READY 改为 WAIT、改价、剔除或改变排名。资金持续流入也不能直接升级状态或提高买入价格。

**观察维度：** 在现有 frozen working set 的技术/成交结构事实基础上，只在能取得同口径、可溯源且截至同一有效交易日的资金数据时，补充当日、近5个交易日、近20个交易日的净流入/净流出方向与金额；可得时同时查看区间流入/流出天数、区间成交额和净流入相对成交额占比。结合对应窗口的股价变化、成交量/成交额及原有 MA20/MA60、支撑/压力、成交密集区判断是否量价配合。三个资金窗口可能重叠，不能误写为三组独立证据；单纯放量并不能证明资金净流入。个股资金指标仅为数据商按成交单统计方法估算，不等于机构真实持仓增减，不得将数据商“主力资金”称为已核实的机构买卖。

**描述方式：** 对可核验数据使用“资金与量价相互印证”“资金与价格背离”“短期转向待确认”“暂无明确增量信号”四类非决策性观察，展示具体时窗、资金方向及其对应价格/成交事实。短期净流出但价格结构稳定不自动判趋势衰退；连续净流出且价格、成交结构同步恶化可提示注意原有失效条件；净流入但股价滞涨、上涨伴随净流出等背离应客观描述，不未经证实地解释为吸筹或出货。不能把净流入绝对金额跨市值公司直接排序，不能因单日异动推断20日资金趋势。

**来源、时效与成本：** 先使用 frozen working set 已有的股价及成交结构，禁止为了本节重新读取已 Freeze 的 shard、index、manifest、part、legacy 文件，或为已有事实再次上网。资金数据如不在 working set，可在原深研完成后，优先针对原 READY/WAIT 用少量批量同源查询补充，不为未入选/已 DROP/UNCERTAIN/PRE_SCREENED_OUT 个股重新扩大检索；同一来源同轮不重复读取。数据必须标明供应方、统计定义/口径、个股身份、窗口和截至交易日，避免不同平台、复权口径和交易日不一致直接拼接。19:00及手动正式版不得把盘中未完结数据当成正式收盘数据；07:00早间增量版仅能展示上一有效收盘资金背景和有明确时点的隔夜信息，不把旧数据称作今日资金。

**缺失与兼容：** 数据不可得、口径不一致或查询成本明显超过辅助价值时，直接标记“资金观察未验证/不可比”，保留原完整榜单，不以缺失触发新的 Gate、UNCERTAIN 或发布失败。完整的正式研究、原有 Coverage/Publication Gate、主榜价格完整性、原状态与顺序、research/latest_formal_result.json 的既定必需字段，以及 research/low_risk_handoff.json 的结构和消费者契约完全不变。本节为报告辅助信息，不引入新必填 JSON 字段；已有格式容许附注时可保留有来源和日期的观察，否则只放在本轮用户可见报告。

**输出：** 必须先展示原 READY/WAIT 主榜（公司、现价、合理买入区、低风险买入区、状态及触发条件），随后可用紧凑附表展示各 READY/WAIT 个股的资金流向与量价配合观察；没有可靠数据的逐项明确“未验证”，不得因补充观察延迟、删减或改写原正式研究结论。

## 10. I/O 规则

一轮正式执行应近似：

```text
1次 trend_handoff
1次 data/low_risk/index.json
N次 routed industry manifest（N == routed_industry_with_universe_count）
P个逻辑 part（P == 所有 routed manifest 声明的 part_count 总和；每个 part 默认 1 次完整文件 fetch，只有明确截断时才可由多个连续按行 segment fetch 完成）
working set freeze
后续 0 次 manifest/part/legacy materialized 读取
全程 0 次 company_industry_index 大文件读取
全程 0 次 data/shards/*.json 读取
必要的行业批次 Web/公告研究
```

禁止：
- 正式榜现场解析 company_industry_index 或 shards；
- 读取 legacy `data/low_risk/by_industry/<industry_code>.json`；
- 跳读、抽样或重复读取 manifest 声明的 part；
- Freeze 后再读取 manifest / part；
- 使用 screening_groups、candidate/compact cache 作为正式主流程数据层；
- 为物化视图已有 PE/PB/MA60/support/volume-zone 再上 Web；
- 将上一轮 working set 或阶段结论作为本轮输入。

旧 snapshot/runtime/screening_groups/industry_state 及 legacy 单行业大文件可暂时保留，但已退出活动生产链。

## 11. 执行审计

正式结果保存：

```json
"data_access_audit": {
  "routed_industry_count": 0,
  "routed_industry_with_universe_count": 0,
  "no_universe_industry_count": 0,
  "universe_company_count": 0,
  "working_set_company_count": 0,
  "working_set_count": 0,
  "materialized_index_read_count": 1,
  "materialized_manifest_read_count": 0,
  "materialized_part_read_count": 0,
  "materialized_part_segment_fetch_count": 0,
  "materialized_industry_complete_count": 0,
  "unique_shard_read_count": 0,
  "legacy_industry_file_read_count": 0,
  "post_freeze_shard_read_count": 0,
  "post_freeze_materialized_read_count": 0
}
```

发布前要求：
- `materialized_manifest_read_count == routed_industry_with_universe_count`；
- `materialized_part_read_count == routed manifest 声明的 part_count 总和`；
- `materialized_part_segment_fetch_count >= materialized_part_read_count`，且所有 segment 必须连续覆盖各 part 从第1行到 EOF；
- `materialized_industry_complete_count == routed_industry_with_universe_count`；
- `legacy_industry_file_read_count == 0`；
- `unique_shard_read_count == 0`；
- `working_set_company_count == universe_company_count`；
- `working_set_count == routed_industry_with_universe_count`；
- 两类 post-freeze read count 都为 0。

同时要求 `coverage.transmission_research_gate == "PASSED"`。允许行业批次共用来源，但公司结论、搜证轨迹及必要补证必须可逐家审计；研究工具故障未完成必要检索时不得以 UNCERTAIN 掩盖失败，也不得发布 COMPLETE。

否则不得把执行路径描述为 canonical complete。

## 12. 一句话版本

> GitHub Actions 把 company_industry_index + shards 确定性物化成“行业 manifest + 有界、pretty-print 的多行 part”；低风险榜按 Trend Handoff 对每个 part 优先一次完整读取到 EOF，只有明确截断时才连续分页，完整解析后证明 Universe 无遗漏再 Freeze，从根源规避单行大 JSON 无法分页导致的截断。
