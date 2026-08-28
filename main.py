#!/usr/bin/env python3
"""NOVITA / AWS 成本日报：每天 11:10 拉取飞书表、汇总、出图并推送。"""

from __future__ import annotations

import argparse
import os
import sys
from calendar import monthrange
from datetime import date
from pathlib import Path

import pandas as pd
import yaml

from src.aws_charts import generate_aws_charts
from src.aws_data_fetcher import fetch_aws_data
from src.aws_insights import format_aws_brief
from src.aws_metrics import calculate_aws_metrics
from src.aws_sheet_analysis import analyze_aws_sheet, print_aws_sheet_analysis
from src.charts import generate_all_charts
from src.data_fetcher import fetch_cost_data
from src.feishu_client import FeishuClient
from src.metrics import calculate_metrics
from src.push_feishu import push_aws_report, push_daily_report
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


def build_sample_aws_dataframe() -> tuple[pd.DataFrame, dict[str, str]]:
    labels = {
        "rds": "RDS-数据库",
        "s3": "S3",
        "elb": "ELB-负载均衡",
        "ecs": "ECS",
        "ec2_instance": "EC2 实例",
        "amplify": "Amplify",
        "cloudfront": "CloudFront",
        "elasticache": "ElasticCache",
        "vpc": "VPC",
        "ec2_other": "EC2-其他",
    }
    keys = list(labels.keys())

    def _daily_value(month: int, day: int, *, current: bool) -> dict[str, float]:
        if not current:
            return {
                "rds": 73.0,
                "s3": 111.0,
                "elb": 48.0,
                "ecs": 49.0,
                "ec2_instance": 28.0,
                "amplify": 8.0,
                "cloudfront": 21.0,
                "elasticache": 16.3,
                "vpc": 16.8,
                "ec2_other": 9.0,
            }
        if day == 1:
            rds = 137.4
        elif day == 6:
            rds = 153.1
        elif day >= 20:
            rds = 88.0 + (25 - day) * 0.3
        else:
            rds = 137.4 - (day - 1) * 1.5 + (8 if day == 6 else 0)
        s3 = 98.0 + max(0, day - 14) * 1.9
        elb = 44.0 + max(0, day - 14) * 1.35
        amplify = 7.4 + max(0, day - 13) * 1.28
        if day == 25:
            amplify = 38.2
        elif day == 26:
            amplify = 39.0
        return {
            "rds": rds,
            "s3": s3,
            "elb": elb,
            "ecs": 47.0,
            "ec2_instance": 26.0,
            "amplify": amplify,
            "cloudfront": 18.0 if day < 20 else 12.0,
            "elasticache": 16.8,
            "vpc": 16.4,
            "ec2_other": 7.0,
        }

    rows = []
    for month_offset in (1, 0):
        year = 2026
        month = 8 if month_offset == 0 else 7
        days = 26 if month_offset == 0 else 26
        for day in range(1, days + 1):
            d = date(year, month, day)
            values = _daily_value(month, day, current=(month_offset == 0))
            rows.append({"date": d, **values})
    df = pd.DataFrame(rows)
    df["total"] = df[keys].sum(axis=1)
    df.attrs["service_labels"] = labels
    df.attrs["service_keys"] = keys
    df.attrs["sheet_overview"] = {
        "month_total": {"current": 14116.08, "previous": 13418.12, "change": 697.96, "rate": 5},
        "daily_avg": {"current": 564.64, "previous": 536.72, "change": 27.92, "rate": 5},
        "forecast": {"current": 17148.69, "previous": 16462.11, "change": 686.58, "rate": 4},
        "period_end": date(2026, 8, 26),
    }
    df.attrs["sheet_mom"] = {
        8: {
            "current": {
                "rds": 2885.74, "s3": 2708.06, "elb": 1408.28, "ecs": 1168.06,
                "ec2_instance": 650.88, "amplify": 525.82, "cloudfront": 457.13,
                "elasticache": 420.31, "vpc": 411.38, "ec2_other": 179.04, "total": 14116.08,
            },
            "previous": {
                "rds": 1824.86, "s3": 2771.28, "elb": 1205.69, "ecs": 1224.55,
                "ec2_instance": 691.83, "amplify": 253.08, "cloudfront": 642.71,
                "elasticache": 407.84, "vpc": 421.24, "ec2_other": 226.57, "total": 13418.12,
            },
            "rate": {
                "rds": 58, "s3": -2, "elb": 17, "ecs": -5, "ec2_instance": -6,
                "amplify": 108, "cloudfront": -29, "elasticache": 3, "vpc": -2,
                "ec2_other": -21, "total": 5,
            },
        }
    }
    return df, labels


def run_novita(config: dict, client: FeishuClient | None, args, output_dir: Path) -> None:
    if args.dry_run:
        df = build_sample_dataframe()
        print(f"NOVITA dry-run 示例数据，共 {len(df)} 条")
    else:
        print("正在从飞书 NOVITA 工作表拉取数据...")
        df = fetch_cost_data(client, config)
        print(f"NOVITA 已读取 {len(df)} 条，{df['date'].min()} ~ {df['date'].max()}")

    extra_notes = list(config.get("insights", {}).get("extra_notes") or [])
    metrics = calculate_metrics(df, config, as_of=args.as_of_date)
    print(
        f"NOVITA 统计：{metrics.current_period.start.month}/{metrics.current_period.start.day}"
        f"-{metrics.current_period.end.month}/{metrics.current_period.end.day}"
    )
    charts = generate_all_charts(metrics, output_dir / "charts", extra_notes)
    generate_html_report(metrics, charts, output_dir)
    md_path = output_dir / f"novita_summary_{metrics.report_date.isoformat()}.md"
    md_path.write_text(generate_markdown_summary(metrics, extra_notes), encoding="utf-8")
    print(md_path.read_text(encoding="utf-8"))

    if not args.no_push and (args.push or not args.dry_run):
        webhook = _env_or_config(config, "FEISHU_WEBHOOK_URL", "push", "webhook_url")
        receive_id = _env_or_config(config, "FEISHU_RECEIVE_ID", "push", "receive_id")
        if _placeholder(webhook) and not receive_id:
            print("未配置 Webhook 或 receive_id，跳过 NOVITA 推送")
            return
        push_daily_report(
            client,
            metrics,
            charts,
            webhook_url=_env_or_config(config, "FEISHU_WEBHOOK_URL", "push", "webhook_url"),
            webhook_secret=_env_or_config(config, "FEISHU_WEBHOOK_SECRET", "push", "webhook_secret"),
            receive_id=_env_or_config(config, "FEISHU_RECEIVE_ID", "push", "receive_id"),
            receive_id_type=_env_or_config(config, "FEISHU_RECEIVE_ID_TYPE", "push", "receive_id_type", default="chat_id"),
            extra_notes=extra_notes,
        )


def run_aws(config: dict, client: FeishuClient | None, args, output_dir: Path) -> None:
    if args.dry_run:
        df, labels = build_sample_aws_dataframe()
        print(f"AWS dry-run 示例数据，共 {len(df)} 条")
    else:
        print("正在从飞书 AWS 工作表拉取数据...")
        df, labels = fetch_aws_data(client, config)
        print(f"AWS 已读取 {len(df)} 条，{df['date'].min()} ~ {df['date'].max()}")

    watch_items = list((config.get("aws") or {}).get("insights", {}).get("watch_services") or [])
    metrics = calculate_aws_metrics(df, labels, config, as_of=args.as_of_date)
    analysis = analyze_aws_sheet(df, metrics)
    print_aws_sheet_analysis(analysis)
    print(
        f"AWS 统计：{metrics.current_period.start.month}/{metrics.current_period.start.day}"
        f"-{metrics.current_period.end.month}/{metrics.current_period.end.day}"
    )
    charts = generate_aws_charts(metrics, output_dir / "charts", analysis=analysis)
    md_path = output_dir / f"aws_summary_{metrics.report_date.isoformat()}.md"
    md_path.write_text(format_aws_brief(metrics, watch_items), encoding="utf-8")
    print(md_path.read_text(encoding="utf-8"))

    if not args.no_push and (args.push or not args.dry_run):
        webhook = _env_or_config(config, "FEISHU_WEBHOOK_URL", "push", "webhook_url")
        receive_id = _env_or_config(config, "FEISHU_RECEIVE_ID", "push", "receive_id")
        if _placeholder(webhook) and not receive_id:
            print("未配置 Webhook 或 receive_id，跳过 AWS 推送")
            return
        push_aws_report(
            client,
            metrics,
            charts,
            webhook_url=_env_or_config(config, "FEISHU_WEBHOOK_URL", "push", "webhook_url"),
            webhook_secret=_env_or_config(config, "FEISHU_WEBHOOK_SECRET", "push", "webhook_secret"),
            receive_id=_env_or_config(config, "FEISHU_RECEIVE_ID", "push", "receive_id"),
            receive_id_type=_env_or_config(config, "FEISHU_RECEIVE_ID_TYPE", "push", "receive_id_type", default="chat_id"),
            watch_items=watch_items,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 NOVITA / AWS 成本日报并推送到飞书")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--report", choices=("novita", "aws", "all"), default="all")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--no-push", action="store_true")
    parser.add_argument("--as-of", dest="as_of_date", type=lambda s: date.fromisoformat(s), help="统计截止日期 YYYY-MM-DD（默认取表内最新日期）")
    args = parser.parse_args()

    load_dotenv()
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"配置文件不存在: {config_path}")
        return 1

    config = load_config(config_path)
    output_dir = Path(config["report"]["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    client: FeishuClient | None = None
    if not args.dry_run:
        app_id = _env_or_config(config, "FEISHU_APP_ID", "feishu", "app_id")
        app_secret = _env_or_config(config, "FEISHU_APP_SECRET", "feishu", "app_secret")
        if _placeholder(app_id) or _placeholder(app_secret):
            print("请配置飞书 FEISHU_APP_ID 和 FEISHU_APP_SECRET")
            return 1
        client = FeishuClient(app_id, app_secret)

    try:
        errors: list[str] = []
        if args.report in ("novita", "all"):
            try:
                run_novita(config, client, args, output_dir)
            except Exception as exc:
                errors.append(f"NOVITA: {exc}")
                print(f"NOVITA 报告失败: {exc}")
        if args.report in ("aws", "all"):
            try:
                run_aws(config, client, args, output_dir)
            except Exception as exc:
                errors.append(f"AWS: {exc}")
                print(f"AWS 报告失败: {exc}")
        if errors:
            raise RuntimeError("；".join(errors))
    except Exception as exc:
        print(f"报告生成失败: {exc}")
        return 1

    if args.no_push:
        print("--no-push：跳过飞书推送")
    elif args.dry_run and not args.push:
        print("dry-run：跳过飞书推送（加 --push 可发送）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
