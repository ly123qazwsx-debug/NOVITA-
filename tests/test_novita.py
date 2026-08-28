"""NOVITA 表解析与指标口径测试。"""

from __future__ import annotations

from datetime import date

import pandas as pd

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


TEST_CONFIG = {"report": {"timezone": "Asia/Shanghai", "currency": "USD", "currency_symbol": "$"}}
AS_OF = date(2026, 8, 19)


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
    metrics = calculate_metrics(df, TEST_CONFIG, as_of=AS_OF)
    # 今天 8.20 → 统计到 8.19
    assert metrics.report_date == date(2026, 8, 19)
    assert metrics.current_period.start == date(2026, 8, 1)
    assert metrics.current_period.end == date(2026, 8, 19)
    assert metrics.current_period.days == 19
    month_total = df.loc[
        (df["date"] >= date(2026, 8, 1)) & (df["date"] <= date(2026, 8, 19)),
        "total_with_fixed",
    ].sum()
    assert abs(metrics.current_period.totals["total_with_fixed"] - month_total) < 1e-6
    overview_keys = [row["key"] for row in metrics.overview]
    assert overview_keys == ["month_total", "daily_with_fixed", "daily_ondemand", "forecast"]
    daily = next(r for r in metrics.overview if r["key"] == "daily_with_fixed")
    assert abs(daily["current"] - month_total / 19) < 1e-6
    assert not metrics.prev_trend_df.empty


def test_metrics_exclude_today_even_if_present():
    df = parse_novita_rows(SAMPLE_ROWS)
    extra = df.iloc[[-1]].copy()
    extra["date"] = date(2026, 8, 20)
    extra["llm"] = 9999
    df = pd.concat([df, extra], ignore_index=True)
    metrics = calculate_metrics(df, TEST_CONFIG, as_of=AS_OF)
    assert metrics.report_date == date(2026, 8, 19)
    assert metrics.current_period.start == date(2026, 8, 1)
    assert metrics.current_period.end == date(2026, 8, 19)
    assert metrics.current_period.days == 19
    assert 9999 not in set(metrics.trend_df["llm"].dropna())
    assert len(metrics.trend_df) == 19


def test_metrics_do_not_slide_to_older_month():
    import pytest

    df = parse_novita_rows(SAMPLE_ROWS)
    df = df[df["date"] < date(2026, 8, 1)].copy()
    with pytest.raises(ValueError, match="没有"):
        calculate_metrics(df, TEST_CONFIG, as_of=AS_OF)


def test_mom_uses_august_footer_not_july_sd_anomaly():
    """sd 7.12-7.14 异常很大，分项环比必须用 8 月表底上月同期，不能按 7 月逐日相加。"""
    from src.data_fetcher import parse_sheet_mom_summary

    rows = [
        ["年", "月", "单位: 美元", "LLM", "sd", "GPU (按需)", "GPU (按需存储)", "GPU 固定", "NOVITA 总消耗"],
        [2026, 7, "7月12日", 300, 8000, 5, 20, 1400, 9725],
        [2026, 7, "7月13日", 300, 8000, 5, 20, 1400, 9725],
        [2026, 7, "7月14日", 300, 8000, 5, 20, 1400, 9725],
        [2026, 8, "8月1日", 295.9, 167.42, 0, 37.56, 260, 760.88],
        [2026, 8, "8月19日", 545.17, 107.86, 0, 37.56, 1300, 1990.59],
        ["", "", "08月 当期合计值", 6793.52, 2398.50, 128.73, 525.84, 31095.51, 40942.11],
        ["", "", "08月 上月同期合计值", 5256.78, 2782.87, 773.17, 500.22, 24376.68, 33689.72],
        ["", "", "08月 环比率", "29%", "-14%", "-83%", "5%", "28%", "22%"],
    ]
    parsed = parse_sheet_mom_summary(rows)
    assert parsed[8]["previous"]["sd"] == 2782.87
    assert parsed[8]["rate"]["sd"] == -14
    assert parsed[8]["rate"]["total_with_fixed"] == 22

    df = parse_novita_rows(rows)
    metrics = calculate_metrics(df, TEST_CONFIG, as_of=AS_OF)
    assert metrics.mom_source == "sheet_footer"
    assert abs(metrics.mom_changes["sd"]["previous"] - 2782.87) < 1e-6
    assert abs(metrics.mom_changes["sd"]["current"] - 2398.50) < 1e-6
    assert int(round(metrics.mom_changes["sd"]["rate"])) == -14
    assert int(round(metrics.mom_changes["llm"]["rate"])) == 29
    assert int(round(metrics.mom_changes["gpu_ondemand"]["rate"])) == -83
    assert abs(metrics.mom_changes["total_with_fixed"]["current"] - 40942.11) < 1e-6
    assert int(round(metrics.overview[0]["rate"])) == 22
    # 若误用 7 月逐日，sd 上月会远大于表底 2782
    assert metrics.mom_changes["sd"]["previous"] < 5000


def test_footer_label_found_in_any_cell():
    """表底汇总标签不一定在日期列（合并单元格时）。"""
    from src.data_fetcher import parse_sheet_mom_summary

    rows = [
        ["年", "月", "单位: 美元", "LLM", "sd", "GPU (按需)", "GPU (按需存储)", "GPU 固定", "NOVITA 总消耗"],
        [2026, 8, "8月1日", 300, 100, 5, 20, 1400, 1825],
        ["08月 当期合计值", "", "", 9060.87, 3274.06, 733.91, 790.96, 43935.51, 57795.31],
        ["08月 上月同期合计值", "", "", 7614.18, 3648.95, 1063.67, 688.02, 40625.47, 53506.63],
        ["08月 环比率", "", "", "19%", "-10%", "-31%", "15%", "8%", "8%"],
    ]
    parsed = parse_sheet_mom_summary(rows)
    assert 8 in parsed
    assert abs(parsed[8]["current"]["llm"] - 9060.87) < 1e-6
    assert int(round(parsed[8]["rate"]["llm"])) == 19


def test_overview_decimal_rate_parsed_as_percent():
    """飞书对比表环比率常返回 0.08 而非 8%，不能显示成 +0.1% / 环比持平。"""
    from src.data_fetcher import parse_sheet_overview_table

    rows = [
        ["当月总消耗（8.1-8.19）", 57795.31, 53506.63, 4288.68, 0.08],
        ["日消耗-含固定GPU", 2222.90, 2057.95, 164.95, 0.08],
        ["日消耗-按需计费", 533.07, 500.11, 32.96, 0.07],
        ["预计8月总消耗", 61309.65, 58026.69, 3282.96, 0.06],
    ]
    parsed = parse_sheet_overview_table(rows)
    assert int(round(parsed["month_total"]["rate"])) == 8
    assert int(round(parsed["daily_with_fixed"]["rate"])) == 8

    df = parse_novita_rows(SAMPLE_ROWS)
    df.attrs["sheet_overview"] = parsed
    metrics = calculate_metrics(df, TEST_CONFIG, as_of=AS_OF)
    month_total = next(r for r in metrics.overview if r["key"] == "month_total")
    assert int(round(month_total["rate"])) == 8


def test_overview_uses_feishu_july_table():
    """第一个板块用飞书对比表里的 7 月数，不用逐日加总。"""
    from src.data_fetcher import parse_sheet_overview_table, parse_sheet_overrides

    rows = SAMPLE_ROWS + [
        ["NOVITA", "8月（截止8月20号）", "7月", "环比", "环比率"],
        ["当月总消耗（8.1-8.20）", 43829.99, 39081.35, 4748.64, "12%"],
        ["日消耗-含固定GPU", 2191.50, 1954.07, 237.43, "12%"],
        ["日消耗-按需(LLM/SD/GPU按需/存储）", 521.72, 490.23, 31.49, "6%"],
        ["预计8月总消耗", 59552.27, 58026.69, 1525.58, "3%"],
        ["实际$60,910.12，已剔除异常消耗"],
    ]
    parsed = parse_sheet_overview_table(rows)
    assert abs(parsed["month_total"]["previous"] - 39081.35) < 1e-6
    assert abs(parsed["forecast"]["previous"] - 58026.69) < 1e-6
    assert int(round(parsed["forecast"]["rate"])) == 3
    assert parse_sheet_overrides(rows)["actual"] == 60910.12

    df = parse_novita_rows(rows)
    metrics = calculate_metrics(df, TEST_CONFIG, as_of=date(2026, 8, 20))
    assert metrics.overview_source == "sheet_table"
    month_total = next(r for r in metrics.overview if r["key"] == "month_total")
    forecast = next(r for r in metrics.overview if r["key"] == "forecast")
    assert abs(month_total["current"] - 43829.99) < 1e-6
    assert abs(month_total["previous"] - 39081.35) < 1e-6
    assert int(round(month_total["rate"])) == 12
    assert abs(forecast["current"] - 59552.27) < 1e-6
    assert abs(forecast["previous"] - 58026.69) < 1e-6
    assert int(round(forecast["rate"])) == 3
    assert abs(metrics.sheet_actual - 60910.12) < 1e-6
    # 7 月对比不能用逐日加总（SAMPLE 里 7 月只有两天）
    assert abs(forecast["previous"] - 58026.69) < 1e-6


def test_parse_sheet_forecast_override():
    from src.data_fetcher import parse_sheet_overrides

    rows = [
        ["预计8月总消耗", 59552.27, "实际", 60910.12],
    ]
    parsed = parse_sheet_overrides(rows)
    assert parsed["forecast"] == 59552.27
    assert parsed["actual"] == 60910.12
    df = parse_novita_rows(SAMPLE_ROWS)
    df.attrs["sheet_overrides"] = {"forecast": 59552.27}
    metrics = calculate_metrics(df, TEST_CONFIG, as_of=AS_OF)
    assert abs(metrics.forecast_month_total - 59552.27) < 1e-6
    assert metrics.forecast_source == "sheet"


def test_dashboard_generates_one_image():
    import tempfile
    from pathlib import Path

    from src.charts import generate_all_charts

    df = parse_novita_rows(SAMPLE_ROWS)
    metrics = calculate_metrics(df, TEST_CONFIG, as_of=AS_OF)
    with tempfile.TemporaryDirectory() as td:
        charts = generate_all_charts(metrics, Path(td), ["机器本月新加12台：5090普*3台、4090*9台"])
        assert list(charts) == ["dashboard"]
        assert charts["dashboard"].exists()
        assert charts["dashboard"].stat().st_size > 20_000
        from PIL import Image

        im = Image.open(charts["dashboard"])
        assert im.mode == "RGB"
        pixel = im.getpixel((12, 12))
        assert pixel[0] < 50 and pixel[1] < 50 and pixel[2] < 50


def test_image_upload_error_explains_missing_bot():
    from src.feishu_client import _explain_image_upload_error

    text = _explain_image_upload_error(400, {"code": 234007, "msg": "App does not enable bot feature."})
    assert "234007" in text
    assert "机器人" in text


def _mtd_frame() -> pd.DataFrame:
    """7.1-7.19 / 8.1-8.19，LLM 在 8.18、8.19 抬升，GPU 固定本月上涨。"""
    rows = []
    for day in range(1, 20):
        rows.append(
            {
                "date": date(2026, 7, day),
                "llm": 300,
                "sd": 100,
                "gpu_ondemand": 5,
                "gpu_storage": 20,
                "gpu_fixed": 1400,
            }
        )
        llm = 520 if day >= 18 else 330
        rows.append(
            {
                "date": date(2026, 8, day),
                "llm": llm,
                "sd": 110,
                "gpu_ondemand": 6,
                "gpu_storage": 25,
                "gpu_fixed": 1636.61,
            }
        )
    df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    df["total_with_fixed"] = df[["llm", "sd", "gpu_ondemand", "gpu_storage", "gpu_fixed"]].sum(axis=1)
    df["total_ondemand"] = df[["llm", "sd", "gpu_ondemand", "gpu_storage"]].sum(axis=1)
    return df


def test_weekly_summary_and_anomalies():
    from src.insights import (
        build_weekly_summary,
        detect_weekly_anomalies,
        format_daily_brief,
        format_weekly_section,
    )

    metrics = calculate_metrics(_mtd_frame(), TEST_CONFIG, as_of=AS_OF)
    summary = build_weekly_summary(metrics)
    assert summary
    assert summary[0].startswith("【每周消耗汇总】")
    assert "第1周" in summary[1]
    anomalies = detect_weekly_anomalies(metrics)
    assert anomalies
    section = format_weekly_section(metrics)
    assert "【周度异常】" in section
    brief = format_daily_brief(metrics, ["机器本月新加12台：5090普*3台、4090*9台"])
    assert "【每周消耗汇总】" in brief
    assert "【周度异常】" in brief


def test_daily_brief_matches_business_template():
    from src.insights import detect_recent_spikes, format_daily_brief, mom_cn

    assert mom_cn(22.1) == "环比上涨22%"
    assert mom_cn(-13.6) == "环比下降14%"
    assert mom_cn(0) == "环比持平"

    metrics = calculate_metrics(_mtd_frame(), TEST_CONFIG, as_of=AS_OF)
    note = "机器本月新加12台：5090普*3台、4090*9台"
    brief = format_daily_brief(metrics, [note])

    lines = brief.splitlines()
    assert lines[0] == "NOVITA（截止到8月19号）："
    assert lines[1].startswith("1、当月总消耗（8.1-8.19）——$")
    assert lines[2].startswith("2、日消耗-含固定GPU——$")
    assert lines[3].startswith("3、日消耗-按需(LLM/SD/GPU按需/存储）——$")
    assert lines[4].startswith("4、预计8月总消耗——$")
    assert "（环比" in lines[4]
    assert lines[5] == ""
    assert lines[6] == "其中："
    assert lines[7] == f"1、以LLM\\机器上涨比较明显（{note}）"
    assert lines[8] == "2、LLM18号、19号消耗增长较大，辛苦查看一下异常"
    assert "分项环比" not in brief
    assert "暂未见" not in brief
    spikes = detect_recent_spikes(metrics)
    assert any("LLM18号、19号" in s for s in spikes)
