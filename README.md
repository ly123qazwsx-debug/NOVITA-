# NOVITA 成本自动日报

每天自动从飞书 Wiki 中的 **NOVITA** 工作表拉取成本数据，生成汇总报告和可视化图表，并可推送到飞书群。

数据源：[飞书 Wiki 表格](https://dreamonvip.feishu.cn/wiki/AbzbwxIJiiyxIAkMFkKcRHJZnKG?sheet=v9euzu)

## 报告内容

- **当月总消耗**（含固定 GPU）
- **日消耗**（含固定 / 仅按需）
- **预计当月总消耗**（按日均线性外推）
- **上月同期对比、环比、环比率**
- **5 张趋势图**：日消耗双线、分项堆叠、分项折线、同期柱状对比、环比率
- **分项环比明细表**：LLM、SD、GPU（按需）、GPU（按需存储）、GPU（固定）

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
# macOS/Linux 中文字体（图表用）
# Ubuntu: sudo apt install fonts-noto-cjk
# macOS: 系统自带，无需额外安装
```

### 2. 创建飞书自建应用

1. 打开 [飞书开放平台](https://open.feishu.cn/app) → 创建企业自建应用
2. 在「权限管理」开通：
   - `wiki:wiki:readonly` — 读取 Wiki
   - `sheets:spreadsheet:readonly` — 读取电子表格
3. 发布应用版本，并在飞书管理后台审批通过
4. 将应用添加到 Wiki 文档（文档右上角「...」→ 添加文档应用）

### 3. 配置

```bash
cp config.example.yaml config.yaml
```

编辑 `config.yaml`：

```yaml
feishu:
  app_id: "cli_你的AppID"
  app_secret: "你的AppSecret"

data_source:
  wiki_token: "AbzbwxIJiiyxIAkMFkKcRHJZnKG"
  sheet_name: "NOVITA"
  range: "A1:H500"    # 按实际数据范围调整

columns:
  date: "日期"           # 改成你表格里的实际列名
  llm: "LLM"
  sd: "SD"
  gpu_ondemand: "GPU（按需）"
  gpu_storage: "GPU（按需存储）"
  gpu_fixed: "GPU（固定）"
```

> **重要**：请对照 NOVITA 工作表的实际列名修改 `columns` 配置。如果列名不一致，脚本会解析不到数据。

### 4. 本地测试（无需飞书凭证）

```bash
python main.py --dry-run
```

会在 `output/` 目录生成示例报告和图表。

### 5. 正式运行

```bash
python main.py
```

输出：
- `output/novita_report_YYYY-MM-DD.html` — 完整 HTML 报告
- `output/novita_summary_YYYY-MM-DD.md` — Markdown 摘要
- `output/charts/*.png` — 5 张图表

## 飞书群推送（可选）

1. 在目标飞书群 → 设置 → 群机器人 → 添加自定义机器人
2. 复制 Webhook 地址，填入 `config.yaml`：

```yaml
push:
  enabled: true
  webhook_url: "https://open.feishu.cn/open-apis/bot/v2/hook/xxxx"
  webhook_secret: ""   # 若机器人启用了签名校验则填写
```

## 每日自动运行（GitHub Actions）

在 GitHub 仓库 Settings → Secrets 添加：

| Secret | 说明 |
|--------|------|
| `FEISHU_APP_ID` | 飞书应用 App ID |
| `FEISHU_APP_SECRET` | 飞书应用 App Secret |
| `FEISHU_WEBHOOK_URL` | 群机器人 Webhook（可选） |
| `FEISHU_WEBHOOK_SECRET` | Webhook 签名密钥（可选） |

工作流默认每天 **北京时间 09:00** 自动执行，报告以 Artifact 形式保存 90 天。

也可手动触发：Actions → NOVITA Daily Cost Report → Run workflow。

## 表格格式要求

NOVITA 工作表建议格式：

| 日期 | LLM | SD | GPU（按需） | GPU（按需存储） | GPU（固定） |
|------|-----|----|-----------|--------------|-----------|
| 2026-08-01 | 120.5 | 80.0 | 350.0 | 25.0 | 500.0 |
| 2026-08-02 | ... | ... | ... | ... | ... |

- 每天一行，日期不重复
- 金额统一币种
- 空值视为 0

## 项目结构

```
├── main.py                  # 入口
├── config.example.yaml      # 配置模板
├── requirements.txt
├── src/
│   ├── feishu_client.py     # 飞书 API
│   ├── data_fetcher.py      # 数据拉取
│   ├── metrics.py           # 指标计算
│   ├── charts.py            # 图表生成
│   ├── report.py            # HTML/Markdown 报告
│   └── push_feishu.py       # 飞书推送
└── .github/workflows/
    └── daily-report.yml     # 定时任务
```

## 常见问题

**Q: 提示「未解析到有效数据行」**  
A: 检查 `columns` 中的列名是否与飞书表格表头完全一致（含括号、空格）。

**Q: 提示「未找到工作表 NOVITA」**  
A: 确认工作表名称大小写一致，或改用 `sheet_id: "v9euzu"`。

**Q: 权限不足**  
A: 确认应用已发布、权限已审批，且已添加到 Wiki 文档。

**Q: 图表中文乱码**  
A: 安装 `fonts-noto-cjk` 字体包。
