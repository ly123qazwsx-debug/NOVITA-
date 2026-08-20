# NOVITA 成本自动日报

每天 **11:10**（北京时间）自动从飞书 Wiki 的 **NOVITA** 工作表拉取你 11:00 前填好的基础数据，汇总环比、生成图表，并推送到飞书。

数据源：[NOVITA 飞书表](https://dreamonvip.feishu.cn/wiki/AbzbwxIJiiyxIAkMFkKcRHJZnKG?sheet=v9euzu)

## 你只需要做的事

1. 每天 **11:00 前** 把截至昨日的基础数据填进 NOVITA 表
2. **11:10** 自动收到一张当月看板（例如今天 8 月 20 日，统计 8 月 1 日～8 月 19 日）

## 报告口径（截至昨日）

| 指标 | 计算方式 |
|------|----------|
| 统计区间 | 本月 1 日 ～ 昨天（不含当天） |
| 当月总消耗 | 区间内五项合计 |
| 日消耗-含固定GPU | 当月总消耗 / 已过天数 |
| 日消耗-按需计费 | (LLM+sd+GPU按需+存储) / 已过天数 |
| 预计当月总消耗 | 当月总消耗 / 已过天数 × 本月总天数，对比上月全月实际 |
| 上月同期 / 环比 / 环比率 | 上月相同日期区间对比 |

分项环比明细：LLM、sd、GPU (按需)、GPU (按需存储)、GPU 固定。

## 一张综合看板

飞书每天只推 **1 张图**：

1. **顶部 4 个 KPI**：当月总消耗、日消耗（含固定）、日消耗（按需）、预计全月
2. **累计 / 预计对比**、**日均对比**（当月 vs 上月）
3. **五项日度趋势（双轴）**：GPU 固定用柱（左轴），LLM / sd / GPU按需 / 存储用折线（右轴），避免固定费用把按需项压扁
4. **分项环比明细表**：当月累计、上月同期、环比、环比率、占比

红涨绿跌。统计截止到昨天。

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
