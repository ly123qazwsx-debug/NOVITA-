"""AWS 表逻辑分析测试。"""

from __future__ import annotations

from datetime import date

from src.aws_data_fetcher import parse_aws_rows
from src.aws_metrics import calculate_aws_metrics
from src.aws_sheet_analysis import analyze_aws_sheet
from tests.test_aws import AWS_ROWS, AS_OF, TEST_CONFIG


def test_analyze_aws_sheet_detects_regions_and_sources():
    df, labels = parse_aws_rows(AWS_ROWS)
    metrics = calculate_aws_metrics(df, labels, TEST_CONFIG, as_of=AS_OF)
    analysis = analyze_aws_sheet(df, metrics)

    assert analysis.report_date == date(2026, 8, 26)
    assert analysis.daily_row_count == 3
    assert analysis.kpi_source.startswith("表内对比表")
    assert "表底汇总行" in analysis.mom_source
    assert "Top10" in analysis.trend_source or "分项" in analysis.trend_source
    assert len(analysis.regions) == 3
    assert analysis.top10_keys[0].startswith("RDS")
