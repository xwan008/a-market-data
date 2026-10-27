# 辅助发现覆盖与外部报价输入（仅供研究，非正式决策）

新增字段 \`discovery_coverage_audit\` 写入原有 sector discovery 快照及审计，不改变前三个程序复核信号、正式市场状态、买点资格或任务时间。按当日真实数据生成全部申万三级监测线索与二级分类分组，二级分组的三级成分股中位数**不等于二级行业指数行情**。

可以选择提供以下两个日期一致的外部输入，但没有可靠来源时**不要创建任何模拟行情文件**；程序应明确返回 \`UNAVAILABLE_NO_VERIFIED_SOURCE\`。

1. \`data/research/sw2_index_asof.json\`：JSON 包含 \`schema_version=1\`、\`as_of_trade_date\`、\`source\` 和 \`indices[]\`；每个指数写 \`sw_level2_code\`（6位数字且以00结尾）、\`return_1d_pct\`、\`quote_at\`（含时区）和具体 \`source\`。需要使用经核对的**实际二级指数涨跌幅**。
2. \`data/research/price_anchors_asof.json\`：JSON 包含 \`schema_version=1\`、\`as_of_trade_date\`、\`source\` 和 \`anchors[]\`；每项写 \`anchor_id\`、\`instrument\`、\`market\`、\`price_basis\`、\`price\`、\`unit\`、\`quote_at\`、\`source\`、\`research_sw3_codes[]\`。可选 \`change_5d_pct\`，只有核实同口径历史报价后才填写，禁止由单次价格推算。三级代码仅是研究线索，不是受益确认。

两个来源必须覆盖目标 \`trade_date\`、真实存档且报价时点不晚于当日北京时间18:30。来源字段和时间格式通过只表示“可进一步独立核实”，并不证明数据真实。过期记录不应用于当前判断，未来数据必须拒绝。没有上游数据时不覆盖该渠道，不影响现有行业量价研究的独立进行。

补充的量价触发数值只用于影子研究线索，不得在正式Skill中作为行业准入或趋势自动确认门槛。历史回放应从当时存在的资料版本获取证据，不使用事后新闻、静态映射重写过去。
