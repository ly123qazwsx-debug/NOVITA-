"""NOVITA 表解析与指标口径测试。"""

from __future__ import annotations

from datetime import date

from src.data_fetcher import parse_novita_rows
from src.metrics import calculate_metrics


SAMPLE_ROWS = [
    ["年", "月", "单位: 美元", "LLM", "sd", "GPU (按需)", "GPU (按需存储)", "GPU 固定", "NOVITA 总消耗", "", "按需合计", "固定合计"],
    [2026, 7, "7月1日", 300, 100, 5, 20, 1636.61, 2061.61, "", 425, 1636.61],
    [2026, 7, "7月19日", 310, 105, 6, 22, 1636.61, 2079.61, "", 443, 1636.61],
    [2026, 8, "8月1日", 330, 120, 6.5, 27, 1636.61, 2120.11, "", 483.5, 1636.61],
    ["", "", "8月19日", 360, 130, 7, 28, 1636.61, 2161.61, "", 525, 1636.61],
    ["", "", "08月 当期合计数据", 690, 250, 13.5, 55, 3273.22, 4281.72, "", "", ""],
    ["", "", "08月 上月同期合计数据", 610, 205, 11, 42, 3273.22, 4141.22, "", "", ""],
    ["", "", "08月 环比", 80, 45, 2.5, 13, 0, 140.5, "", "", ""],
    ["", "", "08月 环比率", "13%", "22%", "23%", "31%", "0%", "3%", "", "", ""],
]


def test_parse_skips_summary_and_handles_cn_dates():
    df = parse_novita_rows(SAMPLE_ROWS)
    assert list(df["date"]) == [
        date(2026, 7, 1),
        date(2026, 7, 19),
        date(2026, 8, 1),
        date(2026, 8, 19),
    ]
    assert df.loc[df["date"] == date(2026, 8, 19), "llm"].iloc[0] == 360
    assert df.loc[df["date"] == date(2026, 8, 19), "gpu_fixed"].iloc[0] == 1636.61


def test_metrics_match_sheet_overview_logic():
    df = parse_novita_rows(SAMPLE_ROWS)
    config = {"report": {"timezone": "Asia/Shanghai", "currency": "USD", "currency_symbol": "$"}}
    metrics = calculate_metrics(df, config)
    assert metrics.report_date == date(2026, 8, 19)
    assert metrics.current_period.days == 19
    month_total = df.loc[df["date"] >= date(2026, 8, 1), "total_with_fixed"].sum()
    assert abs(metrics.current_period.totals["total_with_fixed"] - month_total) < 1e-6
    overview_keys = [row["key"] for row in metrics.overview]
    assert overview_keys == ["month_total", "daily_with_fixed", "daily_ondemand", "forecast"]
    daily = next(r for r in metrics.overview if r["key"] == "daily_with_fixed")
    assert abs(daily["current"] - month_total / 19) < 1e-6
    assert not metrics.prev_trend_df.empty


def test_dashboard_generates_one_image():
    import tempfile
    from pathlib import Path

    from src.charts import generate_all_charts

    df = parse_novita_rows(SAMPLE_ROWS)
    config = {"report": {"timezone": "Asia/Shanghai", "currency": "USD", "currency_symbol": "$"}}
    metrics = calculate_metrics(df, config)
    with tempfile.TemporaryDirectory() as td:
        charts = generate_all_charts(metrics, Path(td))
        assert list(charts) == ["dashboard"]
        assert charts["dashboard"].exists()
        assert charts["dashboard"].stat().st_size > 20_000
