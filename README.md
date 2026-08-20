# NOVITA 成本自动日报

每天 **11:10**（北京时间）自动从飞书 Wiki 的 **NOVITA** 工作表拉取你 11:00 前填好的基础数据，汇总环比、生成图表，并推送到飞书。

数据源：[NOVITA 飞书表](https://dreamonvip.feishu.cn/wiki/AbzbwxIJiiyxIAkMFkKcRHJZnKG?sheet=v9euzu)

## 你只需要做的事

1. 每天 **11:00 前** 把截至昨日的基础数据填进 NOVITA 表
2. **11:10** 自动收到一张当月看板（例如今天 8 月 20 日，统计 8 月 1 日～8 月 19 日）

## 日报文字模版

飞书正文按下面格式输出（数字每天按表重算，环比为整数百分比）：

```
NOVITA（截止到8月19号）：
1、当月总消耗（8.1-8.19）——$40,942.11  (环比上涨22%）
2、日消耗-含固定GPU——$2,154.85  (环比上涨22%）
3、日消耗-按需(LLM/SD/GPU按需/存储）——$518.24  (环比上涨6%）
4、预计8月总消耗——$59,552.27  （环比上涨3%）

其中：
1、以LLM\机器上涨比较明显（机器本月新加12台：5090普*3台、4090*9台）
2、LLM18号、19号消耗增长较大，辛苦查看一下异常
```

「其中」第 1 条会带上 `config.yaml` 里的 `insights.extra_notes`（本月新机器等人工备注）。第 2 条由脚本自动检测：近两日某分项若高于此前当月日均约 35%，会点名日期并请核查异常。

## 报告口径（截至昨日）

| 指标 | 计算方式 |
|------|----------|
| 统计区间 | **本月 1 日 ～ 昨天**。例如今天 8 月 20 日，只统计 8 月 1 日～8 月 19 日，不含当天；不会因为表格最后一行是更早的日期而改成别的月份 |
| 当月总消耗 | 区间内五项合计 |
| 日消耗-含固定GPU | 当月总消耗 / 已过天数 |
| 日消耗-按需计费 | (LLM+sd+GPU按需+存储) / 已过天数 |
| 预计当月总消耗 | 当月总消耗 / 已过天数 × 本月总天数，对比上月全月实际 |
| 上月同期 / 环比 / 环比率 | **优先用当月表底**「当期合计 / 上月同期合计 / 环比率」。因为 sd 在 7 月 12–14 日有异常，表底上月同期已按业务口径剔除，不再用 7 月逐日相加 |

分项环比明细：LLM、sd、GPU (按需)、GPU (按需存储)、GPU 固定。

## 一张综合看板（深色，两段组合）

飞书每天只推 **1 张图**，深色底、字和图表放大，**每一块都标明单位：美元**：

1. **成本概览**：4 个 KPI + 累计/预计对比、日消耗对比（柱上标金额和环比）
2. **分项环比明细表**：用当月表底「当期合计 / 上月同期 / 环比率」（上月同期不含 sd 7.12-7.14 异常）
3. **日度趋势（拆成两张图，避免量级差太大）**
   - 主要成本：GPU 固定用柱（左轴），LLM / sd 用折线（右轴），**每个点都标当天金额**
   - 低金额成本：GPU 按需、GPU 按需存储单独放大，**每个点都标当天金额**

标题为「NOVITA X月成本概览」，并写明截至昨日。若表里有「预计X月总消耗」数字，预计全月优先用表上的值。

## 一次性配置

### 1. 创建飞书应用（读表）

1. 打开 [飞书开放平台](https://open.feishu.cn/app) → 创建企业自建应用
2. 开通权限：`wiki:wiki:readonly`、`sheets:spreadsheet:readonly`、`im:message`、`im:resource`
3. **必须开启「机器人」能力**（应用能力 → 机器人）。没有这一项，图表文件生成了也传不进飞书群
4. 创建版本并发布，管理后台审批
5. 打开 NOVITA Wiki 文档 → 右上角 `...` → 添加文档应用

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

## 群里只有文字、没有图？

图**已经生成了**（在 Actions 的 Artifacts 里能下载 `novita_dashboard.png`）。群里看不到，是因为飞书上传图片失败。上次日志是：

`上传图表 dashboard 失败: 400 Client Error ... /im/v1/images`

请检查飞书应用：

1. 开放平台 → 你的应用 → **应用能力** → 开启 **机器人**
2. 权限管理开通 **`im:resource`（获取与上传图片或文件资源）**
3. **创建版本 → 发布**（改权限后必须重新发布才生效）
4. 再跑一次 Actions

合并本仓库最新修复后：上传会改用 RGB/JPEG（飞书不认透明 PNG），失败原因会直接写在群消息里。

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

底部「当期合计 / 上月同期 / 环比 / 环比率」行会自动跳过。读取范围默认 `A1:R400`，以覆盖全年，并尽量读到表右侧的预计/实际汇总。

## 项目结构

```
├── main.py                      # 入口
├── config.example.yaml
├── src/
│   ├── feishu_client.py         # 飞书 API
│   ├── data_fetcher.py          # 解析 NOVITA 表
│   ├── metrics.py               # 指标与环比
│   ├── insights.py              # 日报文字模版与异常检测
│   ├── charts.py                # 图表
│   ├── report.py                # HTML / Markdown
│   └── push_feishu.py           # 飞书推送
├── tests/test_novita.py
└── .github/workflows/daily-report.yml   # 每天 11:10
```
