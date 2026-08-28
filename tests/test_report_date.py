"""报告截止日解析测试。"""

from __future__ import annotations

from datetime import date

import pandas as pd

from src.aws_data_fetcher import parse_aws_overview_table
from src.report_date import parse_overview_period_end, resolve_report_date

TEST_CONFIG = {"report": {"timezone": "Asia/Shanghai"}}


def test_parse_overview_period_end():
    assert parse_overview_period_end("当期总消耗（8.1-8.26）", 2026) == date(2026, 8, 26)
    assert parse_overview_period_end("当月总消耗（8.1–8.25）", 2026) == date(2026, 8, 25)


def test_resolve_report_date_prefers_sheet_period_end():
    df = pd.DataFrame({"date": [date(2026, 8, d) for d in (1, 25, 26)]})
    df.attrs["sheet_overview"] = {"period_end": date(2026, 8, 26)}
    assert resolve_report_date(df, TEST_CONFIG) == date(2026, 8, 26)


def test_resolve_report_date_uses_latest_daily_when_no_overview():
    df = pd.DataFrame({"date": [date(2026, 8, d) for d in range(1, 27)]})
    assert resolve_report_date(df, TEST_CONFIG) == date(2026, 8, 26)


def test_resolve_report_date_honors_explicit_as_of():
    df = pd.DataFrame({"date": [date(2026, 8, d) for d in range(1, 27)]})
    assert resolve_report_date(df, TEST_CONFIG, as_of=date(2026, 8, 20)) == date(2026, 8, 20)


def test_parse_aws_overview_period_end():
    rows = [["当期总消耗（8.1-8.26）", 100.0, 90.0, 10.0, "11%"]]
    overview = parse_aws_overview_table(rows)
    assert overview["period_end"] == date(2026, 8, 26)
