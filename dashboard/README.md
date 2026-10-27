# 识势 · A 股决策中心

**识势（w.x.）** 是一个与现有 A 股 Python 定时任务隔离的 **React + Vite 只读金融研究看板**。界面参考 Koyfin 的信息密度分层与 TradingView 的固定导航交互，自行实现深色视觉风格；**不生成行情、不更改现有研判规则、不自动交易**。

## 模块与数据来源

| 模块 | 唯一来源 | 说明 |
| --- | --- | --- |
| 趋势池 | `research/trend_registry.json` | 状态、证据、失效条件与状态历史 |
| 优先趋势 | `research/trend_handoff.json` | 原始已发布 rank |
| 趋势买点 | `research/trend_buy_handoff.json` | V2 正式 READY / WAIT、计划入场区间和风险条件 |
| 盘中监测 | `research/intraday_monitor_state.json` | 文件缺失或无效时显示“尚无有效监测记录”，**不会推断信号** |
| 我的持仓 | 私有 Airtable「交易复盘日志 / 交易记录」 | 仅服务器使用 PAT 分页读取，不写入 GitHub |

数据源状态与研究交易日单独标记；不会把 `receivedAt` 当成行情时间、把盘中报价当成正式收盘价。页面仅在登录或重新打开时读取一次已发布文件；如需查看之后生成的新数据，使用页面右上角「刷新」按钮。不再自动每 120 秒轮询，因此不会因为看板持续打开而反复调用 Airtable；不创建额外行情采集任务。

## 部署 Vercel

1. 在 Vercel 创建新项目，导入 GitHub 仓库 `xwan008/a-market-data`，**Root Directory 设为 `dashboard`**；Framework Preset 为 Vite。保留根目录现有 Python / GitHub Actions 不变。
2. 在 Vercel Project → Settings → Environment Variables 配置：
   - `DASHBOARD_PASSWORD`：访问密码，至少 12 字符，避免使用其它站点重复密码。
   - `SESSION_SECRET`：随机会话签名密钥，至少 32 字符。可以通过 `openssl rand -hex 32` 生成。
   - `AIRTABLE_TOKEN`：新建 **只读** Airtable Personal Access Token，仅授权本项目的「交易复盘日志」base，权限至少 `data.records:read`。
   - `AIRTABLE_BASE_ID`：你的 Airtable base ID。
   - `AIRTABLE_TABLE_ID`：你的「交易记录」table ID。
   - 可选 `GITHUB_REPOSITORY`（默认 `xwan008/a-market-data`）与 `GITHUB_REF`（默认 `main`）。
3. 部署并打开 Vercel 给出的访问地址。首次访问需输入 `DASHBOARD_PASSWORD`。**不要将 `.env`、PAT 或密码提交到 GitHub；不要添加 `VITE_` 前缀**。
4. 建议在 Vercel 额外开启 Deployment Protection / WAF 限流，为密码登录提供额外保护。网页 HTML 静态壳可公开访问，但所有个人数据、市场数据 API 均需要受签名的 HttpOnly 会话 Cookie。

## 运行与检查

```bash
cd dashboard
npm ci # 如尚未提交 lockfile 可先 npm install
npm run dev       # 纯前端 Vite 仅用于样式开发；API 需独立 Vercel Functions
npm run build     # 生产构建
npm test          # 内置 Node 单测
# 要本地同时运行 Vite + serverless API，安装 Vercel CLI 后执行：
vercel dev
```

## 安全与交易边界

- 本网站**只读**：GitHub 文件 `GET`、Airtable 只读 API，不存在持仓写入/提交交易功能。
- 没有凭证时不返回数据；API 的响应禁用缓存，PAT 只存在服务器环境变量。会话签名、12 小时有效、HttpOnly + SameSite Strict Cookie。
- Airtable 翻页读取全部交易记录；缺字段、股票代码无效、操作类型不认识、卖出数量冲突等，标记“待核验”而非假定净持仓为零。
- 成本按移动加权平均法估算（不含手续费/税费），同日存在买卖混用等不确定顺序时不显示估算成本；**不将记录成本当作止损线**。
- 监测状态文件尚未生成、状态错误或时间不匹配时，仅展示来源/日期，不产生新的买卖动作。
- 有交易风险，页面仅提供研究信息，不构成投资建议。

## 文件结构

```
dashboard/
├── api/auth.js          # 登录、退出、会话检测
├── api/data.js          # 受保护的 GitHub + Airtable 只读数据接口
├── lib/auth.js          # 服务器侧会话签名与校验
├── src/App.jsx          # 多视图金融研究看板
├── src/model.js         # 数据适配和持仓核验
├── src/styles.css       # 响应式深色视觉系统
├── src/main.jsx
├── tests/model.test.js  # Node 内置测试
├── index.html
└── vercel.json
```
