"""成本指标计算（对齐 NOVITA 表右侧汇总口径）。"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from .data_fetcher import COST_COLUMNS

CATEGORY_LABELS = {
    "llm": "LLM",
    "sd": "sd",
    "gpu_ondemand": "GPU (按需)",
    "gpu_storage": "GPU (按需存储)",
    "gpu_fixed": "GPU 固定",
    "total_with_fixed": "NOVITA 总消耗",
    "total_ondemand": "按需合计",
}

OVERVIEW_KEYS = ("month_total", "daily_with_fixed", "daily_ondemand", "forecast")


@dataclass
class PeriodMetrics:
    start: date
    end: date
    days: int
    totals: dict[str, float]
    daily_avg: dict[str, float]


@dataclass
class ReportMetrics:
    report_date: date
    currency: str
    currency_symbol: str
    current_period: PeriodMetrics
    previous_period: PeriodMetrics
    today: dict[str, float]
    forecast_month_total: float
    prev_forecast_month_total: float
    prev_month_full_total: float
    mom_changes: dict[str, dict[str, float]]
    overview: list[dict[str, Any]] = field(default_factory=list)
    trend_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    prev_trend_df: pd.DataFrame = field(default_factory=pd.DataFrame)


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _same_period_last_month(end_date: date) -> tuple[date, date]:
    if end_date.month == 1:
        prev_month, prev_year = 12, end_date.year - 1
    else:
        prev_month, prev_year = end_date.month - 1, end_date.year

    prev_start = date(prev_year, prev_month, 1)
    prev_end = date(prev_year, prev_month, min(end_date.day, monthrange(prev_year, prev_month)[1]))
    return prev_start, prev_end


def _sum_period(df: pd.DataFrame, start: date, end: date) -> dict[str, float]:
    mask = (df["date"] >= start) & (df["date"] <= end)
    subset = df.loc[mask]
    keys = COST_COLUMNS + ["total_with_fixed", "total_ondemand"]
    return {k: float(subset[k].sum()) if not subset.empty else 0.0 for k in keys}


def _mom(current: float, previous: float) -> tuple[float, float]:
    change = current - previous
    rate = (change / previous * 100) if previous else float("nan")
    return change, rate


def _item(current: float, previous: float) -> dict[str, float]:
    change, rate = _mom(current, previous)
    return {"current": current, "previous": previous, "change": change, "rate": rate}


def _period_end_through_yesterday(df: pd.DataFrame, tz: ZoneInfo) -> date:
    """今天 8 月 20 日则统计到 8 月 19 日（不含当天）。"""
    today = datetime.now(tz).date()
    as_of = today - timedelta(days=1)
    eligible = df.loc[df["date"] <= as_of, "date"]
    if eligible.empty:
        raise ValueError(f"没有截至 {as_of} 的数据，无法生成当月日报")
    return eligible.max()


def calculate_metrics(df: pd.DataFrame, config: dict[str, Any]) -> ReportMetrics:
    tz = ZoneInfo(config["report"]["timezone"])
    report_date = _period_end_through_yesterday(df, tz)

    cur_start = _month_start(report_date)
    cur_end = report_date
    prev_start, prev_end = _same_period_last_month(report_date)

    cur_days = (cur_end - cur_start).days + 1
    prev_days = (prev_end - prev_start).days + 1

    cur_totals = _sum_period(df, cur_start, cur_end)
    prev_totals = _sum_period(df, prev_start, prev_end)

    current_period = PeriodMetrics(
        start=cur_start,
        end=cur_end,
        days=cur_days,
        totals=cur_totals,
        daily_avg={k: v / cur_days for k, v in cur_totals.items()},
    )
    previous_period = PeriodMetrics(
        start=prev_start,
        end=prev_end,
        days=prev_days,
        totals=prev_totals,
        daily_avg={k: v / prev_days for k, v in prev_totals.items()},
    )

    today_row = df[df["date"] == report_date]
    keys = COST_COLUMNS + ["total_with_fixed", "total_ondemand"]
    if today_row.empty:
        today = {k: 0.0 for k in keys}
    else:
        today = {k: float(today_row.iloc[0][k]) for k in keys}

    days_in_month = monthrange(report_date.year, report_date.month)[1]
    days_in_prev = monthrange(prev_start.year, prev_start.month)[1]
    prev_full_end = date(prev_start.year, prev_start.month, days_in_prev)
    prev_month_full_total = _sum_period(df, prev_start, prev_full_end)["total_with_fixed"]
    forecast = cur_totals["total_with_fixed"] / cur_days * days_in_month if cur_days else 0.0
    prev_forecast = prev_totals["total_with_fixed"] / prev_days * days_in_prev if prev_days else 0.0

    mom_changes = {key: _item(cur_totals[key], prev_totals[key]) for key in keys}

    period_label = f"{cur_start.month}.{cur_start.day}-{cur_end.month}.{cur_end.day}"
    overview = [
        {
            "key": "month_total",
            "label": f"当月总消耗 ({period_label})",
            **_item(cur_totals["total_with_fixed"], prev_totals["total_with_fixed"]),
        },
        {
            "key": "daily_with_fixed",
            "label": "日消耗-含固定GPU",
            **_item(current_period.daily_avg["total_with_fixed"], previous_period.daily_avg["total_with_fixed"]),
        },
        {
            "key": "daily_ondemand",
            "label": "日消耗-按需计费",
            **_item(current_period.daily_avg["total_ondemand"], previous_period.daily_avg["total_ondemand"]),
        },
        {
            "key": "forecast",
            "label": f"预计{report_date.month}月总消耗",
            **_item(forecast, prev_month_full_total),
        },
    ]

    trend_df = df[(df["date"] >= cur_start) & (df["date"] <= cur_end)].copy()
    prev_trend_df = df[(df["date"] >= prev_start) & (df["date"] <= prev_end)].copy()

    return ReportMetrics(
        report_date=report_date,
        currency=config["report"]["currency"],
        currency_symbol=config["report"]["currency_symbol"],
        current_period=current_period,
        previous_period=previous_period,
        today=today,
        forecast_month_total=forecast,
        prev_forecast_month_total=prev_forecast,
        prev_month_full_total=prev_month_full_total,
        mom_changes=mom_changes,
        overview=overview,
        trend_df=trend_df,
        prev_trend_df=prev_trend_df,
    )
