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
    config = {"report": {"timezone": "Asia/Shanghai", "currency": "USD", "currency_symbol": "$"}}
    metrics = calculate_metrics(df, config)
    assert metrics.report_date == date(2026, 8, 19)
    assert metrics.current_period.end == date(2026, 8, 19)
    assert 9999 not in set(metrics.trend_df["llm"])


def test_dashboard_generates_one_image():
    import tempfile
    from pathlib import Path

    from src.charts import generate_all_charts

    df = parse_novita_rows(SAMPLE_ROWS)
    config = {"report": {"timezone": "Asia/Shanghai", "currency": "USD", "currency_symbol": "$"}}
    metrics = calculate_metrics(df, config)
    with tempfile.TemporaryDirectory() as td:
        charts = generate_all_charts(metrics, Path(td), ["机器本月新加12台：5090普*3台、4090*9台"])
        assert list(charts) == ["dashboard"]
        assert charts["dashboard"].exists()
        assert charts["dashboard"].stat().st_size > 20_000
        from PIL import Image

        im = Image.open(charts["dashboard"])
        assert im.mode == "RGB"


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


def test_daily_brief_matches_business_template():
    from src.insights import detect_recent_spikes, format_daily_brief, mom_cn

    assert mom_cn(22.1) == "环比上涨22%"
    assert mom_cn(-13.6) == "环比下降14%"
    assert mom_cn(0) == "环比持平"

    config = {"report": {"timezone": "Asia/Shanghai", "currency": "USD", "currency_symbol": "$"}}
    metrics = calculate_metrics(_mtd_frame(), config)
    note = "机器本月新加12台：5090普*3台、4090*9台"
    brief = format_daily_brief(metrics, [note])

    assert brief.startswith("NOVITA（截止到8月19号）：")
    assert "1、当月总消耗（8.1-8.19）——" in brief
    assert "2、日消耗-含固定GPU——" in brief
    assert "3、日消耗-按需(LLM/SD/GPU按需/存储）——" in brief
    assert "4、预计8月总消耗——" in brief
    assert "环比上涨" in brief
    assert "其中：" in brief
    assert f"以LLM、机器上涨比较明显（{note}）" in brief
    assert "LLM18号、19号消耗增长较大，辛苦查看一下异常" in brief
    spikes = detect_recent_spikes(metrics)
    assert any("LLM18号、19号" in s for s in spikes)
