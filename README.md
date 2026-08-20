# NOVITA 成本自动日报

每天 **11:10**（北京时间）自动从飞书 Wiki 的 **NOVITA** 工作表拉取你 11:00 前填好的基础数据，汇总环比、生成图表，并推送到飞书。

数据源：[NOVITA 飞书表](https://dreamonvip.feishu.cn/wiki/AbzbwxIJiiyxIAkMFkKcRHJZnKG?sheet=v9euzu)

## 你只需要做的事

1. 每天 **11:00 前** 在 NOVITA 表填好当天 LLM / sd / GPU(按需) / GPU(按需存储) / GPU 固定
2. **11:10** 自动收到飞书消息：一张综合看板（概览 KPI、分项趋势对比上月、环比率、明细表）

## 报告口径（与表右侧汇总一致）

| 指标 | 计算方式 |
|------|----------|
| 当月总消耗 | 本月 1 日～最新一天，五项合计 |
| 日消耗-含固定GPU | 当月总消耗 / 已过天数 |
| 日消耗-按需计费 | (LLM+sd+GPU按需+存储) / 已过天数 |
| 预计当月总消耗 | 当月总消耗 / 已过天数 × 本月总天数 |
| 上月同期 / 环比 / 环比率 | 上月相同日期区间对比 |

分项环比明细：LLM、sd、GPU (按需)、GPU (按需存储)、GPU 固定。

## 一张综合看板

飞书每天只推 **1 张图**，包含全部内容：

1. **顶部 4 个 KPI**：当月总消耗、日消耗（含固定）、日消耗（按需）、预计全月 — 附环比率
2. **5 个分项趋势**：LLM / sd / GPU按需 / 存储 / GPU固定，各自独立坐标（避免固定 GPU 把按需数据压扁）；实线当月、虚线上月同期，一眼看涨跌
3. **每日总消耗**：含固定 vs 按需
4. **分项环比率条形图**：跨分项对比谁涨最多
5. **底部明细表**：当月、上月同期、环比、环比率

红涨绿跌。

## 一次性配置

### 1. 创建飞书应用（读表）

1. 打开 [飞书开放平台](https://open.feishu.cn/app) → 创建企业自建应用
2. 开通权限：`wiki:wiki:readonly`、`sheets:spreadsheet:readonly`、`im:message`、`im:resource`
3. 创建版本并发布，管理后台审批
4. 打开 NOVITA Wiki 文档 → 右上角 `...` → 添加文档应用

### 2. 创建群机器人（收报告）

1. 新建飞书群，例如「NOVITA 成本日报」（可以只有你）
2. 群设置 → 群机器人 → 添加自定义机器人
3. 复制 Webhook 地址

### 3. 配置密钥

**GitHub 仓库** Settings → Secrets and variables → Actions，添加：

| Secret | 必填 | 说明 |
|--------|------|------|
| `FEISHU_APP_ID` | 是 | 飞书应用 App ID |
| `FEISHU_APP_SECRET` | 是 | 飞书应用 App Secret |
| `FEISHU_WEBHOOK_URL` | 是 | 群机器人 Webhook |

配置完成后，可在 Actions 里手动点一次 **NOVITA Daily Cost Report → Run workflow** 验证。之后每天 11:10 自动跑。

## 本地试跑

```bash
pip install -r requirements.txt
cp config.example.yaml config.yaml
python3 main.py --dry-run
```

报告输出在 `output/`：HTML、Markdown、图表 PNG。

连飞书正式跑：

```bash
export FEISHU_APP_ID=cli_xxx
export FEISHU_APP_SECRET=xxx
export FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
python3 main.py
```

## NOVITA 表结构（已按你的表适配）

| 列 | 内容 |
|----|------|
| A 年 | 2026 |
| B 月 | 8 |
| C | 8月1日 … 8月19日（表头为「单位: 美元」） |
| D LLM | 按需 |
| E sd | 按需 |
| F GPU (按需) | 按需 |
| G GPU (按需存储) | 按需 |
| H GPU 固定 | 固定计费 |
| I / K / L | 表内合计列，脚本会自行重算，不依赖这些列 |

底部「当期合计 / 上月同期 / 环比 / 环比率」行会自动跳过。

## 项目结构

```
├── main.py                      # 入口
├── config.example.yaml
├── src/
│   ├── feishu_client.py         # 飞书 API
│   ├── data_fetcher.py          # 解析 NOVITA 表
│   ├── metrics.py               # 指标与环比
│   ├── charts.py                # 图表
│   ├── report.py                # HTML / Markdown
│   └── push_feishu.py           # 飞书推送
├── tests/test_novita.py
└── .github/workflows/daily-report.yml   # 每天 11:10
```
