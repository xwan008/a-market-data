# A股低风险买点榜｜行业自适应估值 Override

本文件覆盖 `PRICE_RANGE_OUTPUT_OVERRIDE.md` 中“价格区间如何计算”的方法部分，但不改变 READY/WAIT/UNCERTAIN/DROP 语义、价格区间完整性 Gate、Top5/6 预筛、Transmission / Expectation 或执行效率规则。

目标：把“低风险买点”定义为 **行业适配的估值锚 + 当前市场结构锚 + 安全边际**，而不是统一套 PE，也不是每天做完整 DCF。

---

## 1. 总原则

价格区间不是宣称公司的绝对内在价值，而是回答：

> 在当前已知基本面、同行估值和 60 日价格结构下，什么价格开始具备更合理的风险收益比；什么价格进一步具备低风险安全边际。

默认计算链：

```text
行业估值原型
→ 同三级行业 peer valuation statistics
→ 公司增长/ROE/盈利质量修正
→ fundamental_anchor_price
→ MA60 / support / volume-zone 结构锚
→ reasonable_price_range
→ 再加入波动与业务不确定性折价
→ low_risk_buy_range
```

Web 深研用于修正关键前瞻假设，不再作为“是否能算出价格区间”的默认前提。公司当前价格、财务、估值和 60 日结构事实只来自本轮 frozen working set。

---

## 2. 同业统计先于固定倍数

对每个 routed 三级行业，只使用 **frozen working set 中通过公司级硬过滤的全部公司** 计算 peer statistics。Freeze 后不得为同行统计重新读取 company_industry_index、shard 或 screening group。只使用正且可用的估值字段：

- `pe_dynamic`
- `pe_ttm`
- `pb`
- `roe`
- `revenue_yoy`
- `net_profit_yoy`
- `deduct_basic_eps_yoy`（如可用，优先于净利润同比作为核心利润增速代理）
- `gross_margin`
- `operating_cashflow_per_share`

至少保存：P25 / median / P75。

不得直接把跨行业统一 PE/PB 当作目标值。若同三级行业样本 < 3，则可退到同二级行业；仍不足再退到同一级行业或当前市场相似业务组，并降低 valuation_confidence。

---

## 3. 行业估值原型

### A. Growth / Technology / R&D-intensive
典型：半导体、电子、计算机、通信设备、高端装备、部分创新医药/CRO 等。

主锚：
1. `pe_dynamic` / `pe_ttm` 的同业中位数；
2. 增长质量修正后的目标 PE；
3. PEG 只作为合理性检查，不机械决定目标 PE；
4. PB 只做下限/资产质量 sanity check，除非公司明显资产重。

增长质量代理：
- 优先 `deduct_basic_eps_yoy`；
- 缺失时用 `net_profit_yoy`；
- 与 `revenue_yoy` 同向时可信度更高；
- 经营现金流明显背离时降低目标倍数。

目标倍数修正规则（相对于 peer median，避免绝对固定 PE）：
- 核心增长、收入增长、现金流质量均显著优于同业：允许 1.00–1.15 × peer median；
- 大致同业：0.90–1.05 × peer median；
- 增长依赖一次性收益、现金流差或估值显著拥挤：0.70–0.90 × peer median。

`fundamental_anchor_price = current_price × target_multiple / current_multiple`。
优先用 dynamic PE；dynamic PE 无效时回退 TTM PE。

### B. Mature / Stable Consumer & Service
典型：成熟消费、家电、食品饮料、稳定服务、成熟医药等。

主锚：
- TTM PE / dynamic PE；
- ROE 与现金流质量；
- 同业 PE/PB 中位数；
- 如仓库未来具备稳定股息数据，可增加 DDM / dividend-yield anchor。

稳定高 ROE、现金流质量好可接近 peer median 或略有溢价；低增长或利润质量弱应折价。

### C. Cyclical / Commodity / Materials
典型：煤炭、有色、钢铁、基础化工、石化、建材、航运、部分农产品链等。

禁止直接用周期高点/低点当期 PE 作为唯一估值锚。

主锚：
1. PB + ROE 相对同业；
2. 正常化盈利代理；
3. 当前 PE 只作辅助；
4. 价格结构权重高于成长行业。

若没有完整 5–10 年历史周期数据，日常任务使用可计算的轻量正常化代理：
- 计算同业当前报告期净利率中位数；
- `normalized_net_income_proxy = current_report_revenue × peer_median_net_margin`；
- 半年报可按同一口径年化，但必须标记 `normalization_confidence=medium/low`，不得视为完整穿越周期盈利；
- 结合 PB-ROE 结果取更保守的 valuation anchor。

若商品价格/价差已明显处周期极端，Web 的商品第一锚可进一步压低/抬高正常化假设，但不得用峰值利润直接外推。

### D. Financials
典型：银行、券商、保险。

银行主锚：PB-ROE；PE 仅辅助。

基本关系：长期 ROE 越高、资本质量越好，合理 PB 越高；ROE 接近资本成本时 PB 接近 1 的逻辑更可靠。

轻量模型：
- `target_pb = peer_median_pb × quality_adjustment`
- quality_adjustment 主要由公司 ROE 相对 peer median ROE 决定，并受资产质量/资本充足/信用风险证据修正。
- `fundamental_anchor_price = current_price × target_pb / current_pb`

保险如缺少 embedded value / NBV 等核心数据，只能用 PB-ROE / PE 做代理，valuation_confidence 降级；无法闭合时可 UNCERTAIN。

券商可 PB-ROE + normalized PE 双锚。

### E. Stable Yield / Utilities / Infrastructure
典型：公用事业、电网/燃气、部分交运基础设施、成熟运营商。

理想主锚：DDM / FCFE / dividend yield；若 frozen working set 暂无股息字段，则日常模型采用：
- peer PE / PB；
- ROE / 现金流稳定性；
- MA60 / 成交密集区权重提高。

这类公司波动通常低于成长股，低风险区不需要机械套用成长股同样大的估值折价。

### F. Industrial / Manufacturing
典型：机械、汽车零部件、风电设备、高端制造等。

主锚：
- dynamic/TTM PE；
- PB/ROE；
- 同业增长和现金流质量；
- 若订单/产能周期明显，则部分采用 cyclical normalization。

订单强、利润传导确认但股价先涨的公司，fundamental anchor 与 60 日结构锚应共同约束买入区。

### G. Real Estate / Asset-heavy / REIT-like
理想主锚：NAV / FFO / AFFO / PB。

A股普通地产开发商如果缺少可靠 NAV、杠杆和项目质量数据，不得只因为 PB 低就给出低风险结论；PB 只能是代理锚，并降低 valuation_confidence。

### H. Pipeline / Option-like Biotech
若盈利主要由单一创新药管线、临床/审批事件驱动，传统 PE/PB 可能失真。应优先 rNPV / pipeline scenario；当前 working set 与可核验证据无法支持时，允许转 UNCERTAIN，不强制机械给区间。

---

## 4. 基本面估值锚的通用组合

每家公司至少形成 1 个 primary valuation anchor；有两个及以上有效锚时取保守组合：

```text
fundamental_anchor_price = median(valid anchor prices)
```

若其中某锚明显依赖不稳定一次性利润、负现金流或周期峰值，则剔除或降低权重。

保存：
- `valuation_archetype`
- `primary_valuation_metric`
- `peer_median_multiple`
- `target_multiple_or_pb`
- `fundamental_anchor_price`
- `valuation_confidence`

---

## 5. 市场结构锚

结构数据只决定“在哪里更适合出手”，不得反向证明基本面价值。

有效结构锚：
- `ma60`
- 最近主要 `support_center`
- 主要 `volume_zone_center`
- 必要时 `ma20`

优先选当前价下方或接近当前价、且有 touches / volume_share 支持的结构区。

计算 `structure_anchor_center` 时，优先级：
1. 强支撑 / 高成交密集区；
2. MA60；
3. MA20。

若结构锚明显高于 fundamental anchor，则不能因为技术支撑而抬高合理买入区；应等待价格向估值锚靠拢。

---

## 6. 合理买入区与低风险买入区

### 6.1 合理买入区

合理买入区是 fundamental anchor 与 structure anchor 的共同可接受区。

执行原则：
- 若两者重叠：以重叠区为核心，允许小幅扩宽成可执行区间；
- 若结构区低于 fundamental anchor：优先采用结构区，只要仍低于保守估值上限；
- 若结构区高于 fundamental anchor：以 fundamental anchor 附近为上限，等待价格回归，不得用技术位抬高价值区。

### 6.2 低风险买入区

在合理区之下进一步加入安全边际。安全边际根据行业原型和 60 日波动自适应，不使用全市场统一百分比。

可使用：

```text
volatility_proxy = (high_60d - low_60d) / ma60
```

建议运行区间：
- 稳定成熟/公用事业/金融：约 8%–15% 的额外折价；
- 工业/一般成长：约 10%–20%；
- 高成长科技/高估值：约 15%–25%；
- 周期/商品：约 15%–30%，并优先参考更低一级支撑/成交密集区。

以上是系统的风险控制参数，不是市场事实；应根据 volatility_proxy 在区间内自适应。

低风险区不得高于合理买入区。

---

## 7. 什么时候仍然 UNCERTAIN

即使有 PE/PB/MA60，也不是任何公司都必须算价格：

- 正 PE 主要来自一次性收益，核心盈利不可识别；
- 管线型 biotech 缺少 rNPV / 关键临床概率信息；
- 地产/保险等行业缺失关键 NAV / EV / 资产质量信息且代理锚冲突巨大；
- fundamental anchor 与多个结构锚差异极端，且无法解释；
- 同业样本过少且没有可靠上级行业 fallback；
- 估值锚之间分歧过大，无法形成保守区间。

但“没有做完整 DCF”本身不再构成 UNCERTAIN 理由。

---

## 8. 输出要求

READY / WAIT 必须增加：
- `valuation_archetype`
- `primary_valuation_metric`
- `fundamental_anchor_price`
- `structure_anchor_center`
- `reasonable_price_range`
- `low_risk_buy_range`
- `price_range_basis`
- `reentry_trigger`

用户主榜继续输出：

| 公司 | 方向 | 当前价 | 合理买入价位 | 低风险买入价位 | 状态 | 等待/触发条件 |

可在备注中简要说明估值方法，例如：
- 半导体：`Growth-Tech / dynamic PE + peer growth adjustment`
- 风电设备：`Industrial / PE+PB + order-cycle adjustment`
- 煤炭：`Cyclical / normalized earnings + PB`
- 银行：`Financial / PB-ROE`

---

## 9. 研究来源原则

本框架依据通行估值原则：
- CFA Institute：P/E 的核心驱动包括增长与要求回报率；周期公司应使用 normalized EPS；P/B 与 ROE 密切相关；
- Aswath Damodaran：周期/商品公司应正常化盈利与利润率；金融机构估值核心是 ROE、增长和 PB；成长/R&D 密集公司需考虑增长、可持续利润率及无形资产会计扭曲；
- McKinsey：周期公司单点倍数容易误导，应使用 through-cycle / normalized 场景；高增长公司不宜机械依赖单点倍数；
- CFA real estate：REIT/地产证券应使用 NAV、FFO/AFFO 等更贴合资产与现金流的指标。

这些来源决定“选什么估值工具”；具体 A 股买入区不照搬海外行业倍数，而使用本轮 A 股同三级行业 peer statistics + 公司质量 + frozen working set 价格结构计算。
