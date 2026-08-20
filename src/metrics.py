"""成本指标计算。"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from .data_fetcher import COST_COLUMNS

CATEGORY_LABELS = {
    "llm": "LLM",
    "sd": "SD",
    "gpu_ondemand": "GPU（按需）",
    "gpu_storage": "GPU（按需存储）",
    "gpu_fixed": "GPU（固定）",
    "total_with_fixed": "总计（含固定）",
    "total_ondemand": "总计（按需）",
}


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
    mom_changes: dict[str, dict[str, float]]
    trend_df: pd.DataFrame


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _same_period_last_month(report_date: date) -> tuple[date, date]:
    if report_date.month == 1:
        prev_month = 12
        prev_year = report_date.year - 1
    else:
        prev_month = report_date.month - 1
        prev_year = report_date.year

    prev_start = date(prev_year, prev_month, 1)
    prev_end = date(prev_year, prev_month, min(report_date.day, monthrange(prev_year, prev_month)[1]))
    return prev_start, prev_end


def _sum_period(df: pd.DataFrame, start: date, end: date) -> dict[str, float]:
    mask = (df["date"] >= start) & (df["date"] <= end)
    subset = df.loc[mask]
    keys = COST_COLUMNS + ["total_with_fixed", "total_ondemand"]
    return {k: float(subset[k].sum()) if not subset.empty else 0.0 for k in keys}


def _mom(current: float, previous: float) -> tuple[float, float | None]:
    change = current - previous
    rate = (change / previous * 100) if previous else None
    return change, rate


def calculate_metrics(df: pd.DataFrame, config: dict[str, Any]) -> ReportMetrics:
    tz = ZoneInfo(config["report"]["timezone"])
    report_date = datetime.now(tz).date()

    # 用数据中最新日期作为报告基准（若今天无数据）
    if report_date not in set(df["date"]):
        report_date = df["date"].max()

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
    if today_row.empty:
        today = {k: 0.0 for k in COST_COLUMNS + ["total_with_fixed", "total_ondemand"]}
    else:
        today = {k: float(today_row.iloc[0][k]) for k in COST_COLUMNS + ["total_with_fixed", "total_ondemand"]}

    days_in_month = monthrange(report_date.year, report_date.month)[1]
    forecast = cur_totals["total_with_fixed"] / cur_days * days_in_month if cur_days else 0.0

    mom_changes: dict[str, dict[str, float]] = {}
    for key in COST_COLUMNS + ["total_with_fixed", "total_ondemand"]:
        change, rate = _mom(cur_totals[key], prev_totals[key])
        mom_changes[key] = {
            "current": cur_totals[key],
            "previous": prev_totals[key],
            "change": change,
            "rate": rate if rate is not None else float("nan"),
        }

    trend_start = date(report_date.year, report_date.month, 1)
    trend_df = df[(df["date"] >= trend_start) & (df["date"] <= report_date)].copy()

    return ReportMetrics(
        report_date=report_date,
        currency=config["report"]["currency"],
        currency_symbol=config["report"]["currency_symbol"],
        current_period=current_period,
        previous_period=previous_period,
        today=today,
        forecast_month_total=forecast,
        mom_changes=mom_changes,
        trend_df=trend_df,
    )
