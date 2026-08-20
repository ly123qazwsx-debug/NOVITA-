#!/usr/bin/env python3
"""NOVITA 成本日报生成入口。"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml

from src.charts import generate_all_charts
from src.data_fetcher import fetch_cost_data
from src.feishu_client import FeishuClient
from src.metrics import calculate_metrics
from src.push_feishu import push_text_summary
from src.report import generate_html_report, generate_markdown_summary


def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 NOVITA 成本日报")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径")
    parser.add_argument("--dry-run", action="store_true", help="使用本地 sample 数据测试")
    parser.add_argument("--no-push", action="store_true", help="不推送到飞书")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"配置文件不存在: {config_path}")
        print("请复制 config.example.yaml 为 config.yaml 并填写飞书凭证")
        return 1

    config = load_config(config_path)
    output_dir = Path(config["report"]["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        import pandas as pd
        from datetime import date, timedelta

        rows = []
        base = date.today().replace(day=1)
        for i in range(20):
            d = base + timedelta(days=i)
            rows.append(
                {
                    "date": d,
                    "llm": 100 + i * 2,
                    "sd": 50 + i,
                    "gpu_ondemand": 200 + i * 3,
                    "gpu_storage": 20,
                    "gpu_fixed": 500,
                }
            )
        df = pd.DataFrame(rows)
        df["total_with_fixed"] = df[["llm", "sd", "gpu_ondemand", "gpu_storage", "gpu_fixed"]].sum(axis=1)
        df["total_ondemand"] = df[["llm", "sd", "gpu_ondemand", "gpu_storage"]].sum(axis=1)
        print("使用 dry-run 示例数据")
    else:
        app_id = os.environ.get("FEISHU_APP_ID") or config["feishu"]["app_id"]
        app_secret = os.environ.get("FEISHU_APP_SECRET") or config["feishu"]["app_secret"]
        if not app_id or not app_secret or "xxxx" in app_id:
            print("请配置飞书 app_id 和 app_secret（config.yaml 或环境变量）")
            return 1

        client = FeishuClient(app_id, app_secret)
        print("正在从飞书 NOVITA 工作表拉取数据...")
        df = fetch_cost_data(client, config)
        print(f"已读取 {len(df)} 条记录，日期范围 {df['date'].min()} ~ {df['date'].max()}")

    metrics = calculate_metrics(df, config)
    charts = generate_all_charts(metrics, output_dir / "charts")
    html_path = generate_html_report(metrics, charts, output_dir)
    md_path = output_dir / f"novita_summary_{metrics.report_date.isoformat()}.md"
    md_path.write_text(generate_markdown_summary(metrics), encoding="utf-8")

    print(f"HTML 报告: {html_path}")
    print(f"Markdown 摘要: {md_path}")
    print(f"图表目录: {output_dir / 'charts'}")

    push_cfg = config.get("push", {})
    if push_cfg.get("enabled") and not args.no_push and not args.dry_run:
        webhook = os.environ.get("FEISHU_WEBHOOK_URL") or push_cfg.get("webhook_url", "")
        secret = os.environ.get("FEISHU_WEBHOOK_SECRET") or push_cfg.get("webhook_secret", "")
        if webhook and "xxxx" not in webhook:
            app_id = os.environ.get("FEISHU_APP_ID") or config["feishu"]["app_id"]
            app_secret = os.environ.get("FEISHU_APP_SECRET") or config["feishu"]["app_secret"]
            client = FeishuClient(app_id, app_secret)
            push_text_summary(client, webhook, metrics, secret)
            print("已推送到飞书群")
        else:
            print("未配置 webhook，跳过推送")

    return 0


if __name__ == "__main__":
    sys.exit(main())
