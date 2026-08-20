#!/usr/bin/env python3
"""NOVITA 成本日报：每天 11:10 拉取飞书表、汇总、出图并推送。"""

from __future__ import annotations

import argparse
import os
import sys
from calendar import monthrange
from datetime import date
from pathlib import Path

import pandas as pd
import yaml

from src.charts import generate_all_charts
from src.data_fetcher import fetch_cost_data
from src.feishu_client import FeishuClient
from src.metrics import calculate_metrics
from src.push_feishu import push_daily_report
from src.report import generate_html_report, generate_markdown_summary


def load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _env_or_config(config: dict, env_key: str, *config_keys: str, default: str = "") -> str:
    value = os.environ.get(env_key)
    if value:
        return value
    cursor: object = config
    for key in config_keys:
        if not isinstance(cursor, dict):
            return default
        cursor = cursor.get(key)
    if cursor is None:
        return default
    return str(cursor)


def _placeholder(value: str) -> bool:
    return not value or "xxxx" in value or value.endswith("xxxxxxxx")


def build_sample_dataframe() -> pd.DataFrame:
    """构造含上月同期的示例数据，便于 dry-run 看环比。"""
    today = date.today()
    rows = []
    for month_offset in (1, 0):
        year = today.year if today.month - month_offset >= 1 else today.year - 1
        month = today.month - month_offset if today.month - month_offset >= 1 else today.month - month_offset + 12
        days = min(today.day, monthrange(year, month)[1])
        for day in range(1, days + 1):
            d = date(year, month, day)
            bump = 30 if month_offset == 0 else 0
            llm_spike = 180 if month_offset == 0 and day >= 18 else 0
            rows.append(
                {
                    "date": d,
                    "llm": 320 + day * 2 + bump + llm_spike,
                    "sd": 110 + day + bump // 2,
                    "gpu_ondemand": 6 + day * 0.2,
                    "gpu_storage": 25 + day * 0.3,
                    "gpu_fixed": 1636.61 if month_offset == 0 else 1400.0,
                }
            )
    df = pd.DataFrame(rows)
    df["total_with_fixed"] = df[["llm", "sd", "gpu_ondemand", "gpu_storage", "gpu_fixed"]].sum(axis=1)
    df["total_ondemand"] = df[["llm", "sd", "gpu_ondemand", "gpu_storage"]].sum(axis=1)
    return df


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 NOVITA 成本日报并推送到飞书")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径")
    parser.add_argument("--dry-run", action="store_true", help="使用示例数据，不请求飞书表格")
    parser.add_argument("--push", action="store_true", help="即使 dry-run 也推送到飞书")
    parser.add_argument("--no-push", action="store_true", help="只生成报告，不推送")
    args = parser.parse_args()

    load_dotenv()
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"配置文件不存在: {config_path}")
        print("请复制 config.example.yaml 为 config.yaml")
        return 1

    config = load_config(config_path)
    output_dir = Path(config["report"]["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    app_id = _env_or_config(config, "FEISHU_APP_ID", "feishu", "app_id")
    app_secret = _env_or_config(config, "FEISHU_APP_SECRET", "feishu", "app_secret")
    webhook = _env_or_config(config, "FEISHU_WEBHOOK_URL", "push", "webhook_url")
    webhook_secret = _env_or_config(config, "FEISHU_WEBHOOK_SECRET", "push", "webhook_secret")
    receive_id = _env_or_config(config, "FEISHU_RECEIVE_ID", "push", "receive_id")
    receive_id_type = _env_or_config(config, "FEISHU_RECEIVE_ID_TYPE", "push", "receive_id_type", default="chat_id")
    has_push_target = (not _placeholder(webhook)) or bool(receive_id)

    client: FeishuClient | None = None
    if args.dry_run:
        df = build_sample_dataframe()
        print(f"使用 dry-run 示例数据，共 {len(df)} 条")
    else:
        if _placeholder(app_id) or _placeholder(app_secret):
            print("请配置飞书 FEISHU_APP_ID 和 FEISHU_APP_SECRET")
            return 1
        client = FeishuClient(app_id, app_secret)
        print("正在从飞书 NOVITA 工作表拉取数据...")
        df = fetch_cost_data(client, config)
        print(f"已读取 {len(df)} 条记录，日期范围 {df['date'].min()} ~ {df['date'].max()}")
        month_start = date.today().replace(day=1)
        if df["date"].max() < month_start:
            print(
                f"警告：最新数据停在 {df['date'].max()}，未覆盖本月。"
                "请确认 NOVITA 表已填到昨天，并把 data_source.range 设为 A1:L400 一类能覆盖全年的区域。"
            )

    extra_notes = list(config.get("insights", {}).get("extra_notes") or [])

    metrics = calculate_metrics(df, config)
    charts = generate_all_charts(metrics, output_dir / "charts", extra_notes)
    html_path = generate_html_report(metrics, charts, output_dir)
    md_path = output_dir / f"novita_summary_{metrics.report_date.isoformat()}.md"
    md_path.write_text(generate_markdown_summary(metrics, extra_notes), encoding="utf-8")

    print(f"HTML 报告: {html_path}")
    print(f"Markdown 摘要: {md_path}")
    print(f"图表目录: {output_dir / 'charts'}")
    print(generate_markdown_summary(metrics, extra_notes))

    if args.no_push:
        print("--no-push：跳过飞书推送")
        return 0
    if args.dry_run and not args.push:
        print("dry-run：跳过飞书推送（加 --push 可发送示例数据）")
        return 0

    if not has_push_target:
        print("未配置 Webhook 或 receive_id，跳过推送")
        return 0

    if client is None and not _placeholder(app_id) and not _placeholder(app_secret):
        client = FeishuClient(app_id, app_secret)

    push_daily_report(
        client,
        metrics,
        charts,
        webhook_url="" if _placeholder(webhook) else webhook,
        webhook_secret=webhook_secret,
        receive_id=receive_id,
        receive_id_type=receive_id_type,
        extra_notes=extra_notes,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
