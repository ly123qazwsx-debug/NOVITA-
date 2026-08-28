"""AWS 表解析、指标与汇总测试。"""

from __future__ import annotations

from datetime import date

from src.aws_data_fetcher import parse_aws_overview_table, parse_aws_rows
from src.aws_insights import format_aws_brief, is_rising_since
from src.aws_metrics import calculate_aws_metrics
from src.aws_charts import generate_aws_charts

TEST_CONFIG = {"report": {"timezone": "Asia/Shanghai", "currency": "USD", "currency_symbol": "$"}}
AS_OF = date(2026, 8, 26)

AWS_ROWS = [
    ["年", "月", "单位: 美元", "RDS-数据库", "S3", "ELB-负载均衡", "ECS", "EC2 实例", "Amplify", "CloudFront", "ElasticCache", "VPC", "EC2-其他", "AWS 总消耗"],
    [2026, 8, "8月1日", 137.4, 98.0, 44.0, 47.0, 26.0, 7.4, 18.0, 16.8, 16.4, 7.0, 417.0],
    [2026, 8, "8月25日", 88.0, 126.8, 64.2, 47.0, 26.0, 38.2, 12.0, 16.8, 16.4, 7.0, 442.4],
    [2026, 8, "8月26日", 87.0, 128.0, 65.0, 47.0, 26.0, 39.0, 12.0, 16.8, 16.4, 7.0, 444.0],
    ["", "", "08月 当期合计值", 2885.74, 2708.06, 1408.28, 1168.06, 650.88, 525.82, 457.13, 420.31, 411.38, 179.04, 14116.08],
    ["", "", "08月 上月同期合计值", 1824.86, 2771.28, 1205.69, 1224.55, 691.83, 253.08, 642.71, 407.84, 421.24, 226.57, 13418.12],
    ["", "", "08月 环比率", "58%", "-2%", "17%", "-5%", "-6%", "108%", "-29%", "3%", "-2%", "-21%", "5%"],
    ["当期总消耗（8.1-8.26）", 14116.08, 13418.12, 697.96, "5%"],
    ["日消耗", 564.64, 536.72, 27.92, "5%"],
    ["预计8月总消耗", 17148.69, 16462.11, 686.58, "4%"],
]


def test_parse_aws_rows_without_year_month_columns():
    """真实 AWS 表可能只有「8月1日」列，没有年/月列；不能把金额误当年份。"""
    rows = [
        ["单位: 美元", "RDS-数据库", "S3", "ELB-负载均衡", "ECS", "EC2 实例", "Amplify", "CloudFront", "ElasticCache", "VPC", "EC2-其他", "AWS 总消耗"],
        ["8月1日", 137.4, 98.0, 44.0, 47.0, 26.0, 7.4, 18.0, 16.8, 16.4, 7.0, 417.0],
        ["8月26日", 87.0, 128.0, 65.0, 47.0, 26.0, 39.0, 12.0, 16.8, 16.4, 7.0, 444.0],
        ["当期总消耗（8.1-8.26）", 14116.08, 13418.12, 697.96, "5%"],
        ["日消耗", 564.64, 536.72, 27.92, "5%"],
        ["预计8月总消耗", 17148.69, 16462.11, 686.58, "4%"],
    ]
    df, labels = parse_aws_rows(rows)
    assert len(df) == 2
    assert df["date"].min().month == 8
    assert df["date"].min().day == 1
    assert df["date"].max().day == 26
    assert df["date"].max().year >= 2020
    assert "rds" in labels


def test_parse_aws_rows_and_overview():
    df, labels = parse_aws_rows(AWS_ROWS)
    assert "rds" in labels
    assert len(df) == 3
    overview = parse_aws_overview_table(AWS_ROWS)
    assert overview["period_end"] == date(2026, 8, 26)
    assert int(round(overview["month_total"]["rate"])) == 5
    metrics = calculate_aws_metrics(df, labels, TEST_CONFIG, as_of=AS_OF)
    assert metrics.report_date == date(2026, 8, 26)
    assert len(metrics.top10) == 10
    assert metrics.top10[0].label.startswith("RDS")
    assert int(round(metrics.top10[0].rate)) == 58


def test_aws_brief_template():
    df, labels = parse_aws_rows(AWS_ROWS)
    extra_days = []
    for day in range(1, 27):
        elb = 44.0 + max(0, day - 14) * 1.0
        s3 = 98.0 + max(0, day - 14) * 1.2
        extra_days.append(
            {
                "date": date(2026, 8, day),
                "rds": 100.0,
                "s3": s3,
                "elb": elb,
                "ecs": 47.0,
                "ec2_instance": 26.0,
                "amplify": 10.0,
                "cloudfront": 18.0,
                "elasticache": 16.8,
                "vpc": 16.4,
                "ec2_other": 7.0,
                "total": 100 + s3 + elb + 47 + 26 + 10 + 18 + 16.8 + 16.4 + 7,
            }
        )
    import pandas as pd

    df = pd.DataFrame(extra_days)
    df.attrs["service_labels"] = labels
    df.attrs["service_keys"] = list(labels.keys())
    df.attrs["sheet_overview"] = parse_aws_overview_table(AWS_ROWS)
    metrics = calculate_aws_metrics(df, labels, TEST_CONFIG, as_of=AS_OF)
    assert metrics.report_date == date(2026, 8, 26)
    assert is_rising_since(metrics.trend_df, "elb", 15)
    assert is_rising_since(metrics.trend_df, "s3", 15)
    watch = [
        {"key": "elb", "label": "ELB 负载均衡", "rise_since_day": 15, "note": "重点检查 prod-api-ecs"},
        {"key": "s3", "label": "S3", "rise_since_day": 15, "note": "重点检查 digen-asset"},
    ]
    brief = format_aws_brief(metrics, watch)
    assert brief.startswith("AWS 成本同步（截至 8 月 26日）")
    assert "当期总消耗（8.1–8.26）" in brief
    assert "【ELB 负载均衡】" in brief
    assert "【S3】" in brief


def test_aws_mom_footer_a35_label_previous():
    """A35 单元格标记「上月同期」，金额从 B 列起与表头服务列对齐。"""
    header = [
        "单位: 美元", "RDS-数据库", "S3", "ELB-负载均衡", "ECS", "EC2 实例",
        "Amplify", "CloudFront", "ElasticCache", "VPC", "EC2-其他", "AWS 总消耗",
    ]
    rows = [header]
    for day in range(1, 32):
        rows.append([f"8月{day}日"] + [100.0] * 10 + [1000.0])
    rows.append([""] * 12)
    rows.append(["当期合计", 2885.74, 2708.06, 1408.28, 1168.06, 650.88, 525.82, 457.13, 420.31, 411.38, 179.04, 14116.08])
    rows.append(["上月同期", 1824.86, 2771.28, 1205.69, 1224.55, 691.83, 253.08, 642.71, 407.84, 421.24, 226.57, 13418.12])
    rows.append(["环比率", "58%", "-2%", "17%", "-5%", "-6%", "108%", "-29%", "3%", "-2%", "-21%", "5%"])
    assert len(rows) == 36
    assert rows[34][0] == "上月同期"  # 第 35 行 A 列
    df, labels = parse_aws_rows(rows)
    metrics = calculate_aws_metrics(df, labels, TEST_CONFIG, as_of=AS_OF)
    assert metrics.mom_source == "sheet_footer"
    assert abs(metrics.mom_by_key["rds"].previous - 1824.86) < 1e-6


def test_aws_mom_footer_row35_with_shifted_label_column():
    """飞书 AWS 表底「上月同期」常在第 35 行，标签在 B 列时金额整体右移一列。"""
    header = [
        "单位: 美元", "RDS-数据库", "S3", "ELB-负载均衡", "ECS", "EC2 实例",
        "Amplify", "CloudFront", "ElasticCache", "VPC", "EC2-其他", "AWS 总消耗",
    ]
    rows = [header]
    for day in range(1, 32):
        rows.append([f"8月{day}日"] + [100.0] * 10 + [1000.0])
    rows.append([""] * 13)  # 空行
    # 第 34-36 行：当期 / 上月同期 / 环比率（标签在 B 列）
    rows.append(["", "08月 当期合计值", 2885.74, 2708.06, 1408.28, 1168.06, 650.88, 525.82, 457.13, 420.31, 411.38, 179.04, 14116.08])
    rows.append(["", "08月 上月同期合计值", 1824.86, 2771.28, 1205.69, 1224.55, 691.83, 253.08, 642.71, 407.84, 421.24, 226.57, 13418.12])
    rows.append(["", "08月 环比率", "58%", "-2%", "17%", "-5%", "-6%", "108%", "-29%", "3%", "-2%", "-21%", "5%"])
    assert len(rows) == 36
    assert "上月同期" in str(rows[34][1])  # 第 35 行
    df, labels = parse_aws_rows(rows)
    assert len(df) == 31
    metrics = calculate_aws_metrics(df, labels, TEST_CONFIG, as_of=AS_OF)
    assert metrics.mom_source == "sheet_footer"
    assert abs(metrics.mom_by_key["rds"].previous - 1824.86) < 1e-6
    assert abs(metrics.mom_by_key["rds"].current - 2885.74) < 1e-6
    assert int(round(metrics.mom_by_key["rds"].rate)) == 58
    assert abs(metrics.previous_period.totals["total"] - 13418.12) < 1e-6


def test_aws_dashboard_generates():
    import tempfile
    from pathlib import Path

    df, labels = parse_aws_rows(AWS_ROWS)
    df.attrs["sheet_overview"] = parse_aws_overview_table(AWS_ROWS)
    metrics = calculate_aws_metrics(df, labels, TEST_CONFIG, as_of=AS_OF)
    assert metrics.current_period.end == date(2026, 8, 26)
    with tempfile.TemporaryDirectory() as td:
        charts = generate_aws_charts(metrics, Path(td))
        assert charts["aws_dashboard"].exists()
        assert charts["aws_dashboard"].stat().st_size > 20_000
