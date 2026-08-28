"""AWS 成本指标计算。"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from .data_fetcher import _mom_from_amounts
from .aws_data_fetcher import _is_billable_service
from .report_date import overview_matches_report, resolve_report_date

AWS_OVERVIEW_KEYS = ("month_total", "daily_avg", "forecast")


@dataclass
class PeriodMetrics:
    start: date
    end: date
    days: int
    totals: dict[str, float]


@dataclass
class ServiceMom:
    key: str
    label: str
    current: float
    previous: float
    change: float
    rate: float
    share: float


@dataclass
class AwsReportMetrics:
    report_date: date
    generated_on: date
    currency: str
    currency_symbol: str
    current_period: PeriodMetrics
    previous_period: PeriodMetrics
    overview: list[dict[str, Any]]
    top10: list[ServiceMom]
    mom_by_key: dict[str, ServiceMom]
    trend_df: pd.DataFrame
    service_labels: dict[str, str]
    service_keys: list[str]
    overview_source: str = "computed"
    mom_source: str = "daily"


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


def _sum_period(df: pd.DataFrame, keys: list[str], start: date, end: date) -> dict[str, float]:
    mask = (df["date"] >= start) & (df["date"] <= end)
    subset = df.loc[mask]
    totals = {k: float(subset[k].sum()) if not subset.empty else 0.0 for k in keys}
    totals["total"] = float(subset["total"].sum()) if "total" in subset.columns and not subset.empty else sum(totals.values())
    return totals


def _apply_footer(base: dict[str, float], footer: dict[str, float]) -> dict[str, float]:
    merged = dict(base)
    for key, value in footer.items():
        if value == value:
            merged[key] = float(value)
    if "total" not in merged or merged["total"] != merged["total"]:
        merged["total"] = sum(v for k, v in merged.items() if k != "total" and v == v)
    return merged


def _item(current: float, previous: float, change: float | None = None, rate: float | None = None) -> dict[str, float]:
    if change is None or change != change:
        change = current - previous
    if previous > 0:
        rate = (change / previous) * 100
    elif rate is None or rate != rate:
        rate = float("nan")
    elif abs(rate) <= 1:
        rate = rate * 100
    return {"current": current, "previous": previous, "change": change, "rate": rate}


def _reindex_days(df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    subset = df[(df["date"] >= start) & (df["date"] <= end)].copy()
    full = pd.DataFrame({"date": [start + timedelta(days=i) for i in range((end - start).days + 1)]})
    return full.merge(subset.drop_duplicates("date"), on="date", how="left")


def calculate_aws_metrics(
    df: pd.DataFrame,
    labels: dict[str, str],
    config: dict[str, Any],
    as_of: date | None = None,
) -> AwsReportMetrics:
    tz = ZoneInfo(config["report"]["timezone"])
    generated_on = datetime.now(tz).date()
    report_date = resolve_report_date(df, config, as_of=as_of)

    keys: list[str] = list(getattr(df, "attrs", {}).get("service_keys") or [c for c in df.columns if c not in ("date", "total")])
    labels_map = labels or (getattr(df, "attrs", {}).get("service_labels") or {})
    keys = [k for k in keys if _is_billable_service(labels_map.get(k, k))]
    cur_start = _month_start(report_date)
    cur_end = report_date
    if df[(df["date"] >= cur_start) & (df["date"] <= cur_end)].empty:
        raise ValueError(f"AWS 表没有 {cur_start} ~ {cur_end} 的数据")

    prev_start, prev_end = _same_period_last_month(report_date)
    cur_days = (cur_end - cur_start).days + 1
    prev_days = (prev_end - prev_start).days + 1

    cur_totals = _sum_period(df, keys, cur_start, cur_end)
    prev_totals = _sum_period(df, keys, prev_start, prev_end)
    mom_source = "daily"
    sheet_mom = (getattr(df, "attrs", {}) or {}).get("sheet_mom") or {}
    footer = sheet_mom.get(report_date.month) or {}
    if footer.get("current") and footer.get("previous"):
        cur_totals = _apply_footer(cur_totals, footer["current"])
        prev_totals = _apply_footer(prev_totals, footer["previous"])
        mom_source = "sheet_footer"

    month_total = cur_totals.get("total", 0.0)
    mom_by_key: dict[str, ServiceMom] = {}
    for key in keys:
        cur = cur_totals.get(key, 0.0)
        prev = prev_totals.get(key, 0.0)
        change = (footer.get("change") or {}).get(key)
        rate = (footer.get("rate") or {}).get(key)
        item = _item(cur, prev, change, rate)
        share = cur / month_total * 100 if month_total else 0.0
        mom_by_key[key] = ServiceMom(
            key=key,
            label=labels.get(key, key),
            current=item["current"],
            previous=item["previous"],
            change=item["change"],
            rate=item["rate"],
            share=share,
        )

    ranked = sorted(mom_by_key.values(), key=lambda s: s.current, reverse=True)
    top10 = ranked[:10]

    period_label = f"{cur_start.month}.{cur_start.day}-{cur_end.month}.{cur_end.day}"
    sheet_overview = (getattr(df, "attrs", {}) or {}).get("sheet_overview") or {}
    overview_labels = {
        "month_total": f"当期总消耗 ({period_label})",
        "daily_avg": "日消耗",
        "forecast": f"预计{report_date.month}月总消耗",
    }
    overview_source = "computed"
    days_in_month = monthrange(report_date.year, report_date.month)[1]
    linear_forecast = month_total / cur_days * days_in_month if cur_days else 0.0
    prev_month_full = prev_totals.get("total", 0.0) / prev_days * days_in_month if prev_days else 0.0

    if all(k in sheet_overview for k in AWS_OVERVIEW_KEYS) and overview_matches_report(sheet_overview, report_date):
        overview_source = "sheet_table"
        overview = [
            {"key": k, "label": overview_labels[k], **_item(
                sheet_overview[k]["current"],
                sheet_overview[k]["previous"],
                sheet_overview[k].get("change"),
                sheet_overview[k].get("rate"),
            )}
            for k in AWS_OVERVIEW_KEYS
        ]
        linear_forecast = sheet_overview["forecast"]["current"]
        prev_month_full = sheet_overview["forecast"]["previous"]
    else:
        overview = [
            {"key": "month_total", "label": overview_labels["month_total"], **_item(month_total, prev_totals.get("total", 0.0))},
            {"key": "daily_avg", "label": overview_labels["daily_avg"], **_item(month_total / cur_days, prev_totals.get("total", 0.0) / prev_days)},
            {"key": "forecast", "label": overview_labels["forecast"], **_item(linear_forecast, prev_month_full)},
        ]

    return AwsReportMetrics(
        report_date=report_date,
        generated_on=generated_on,
        currency=config["report"]["currency"],
        currency_symbol=config["report"]["currency_symbol"],
        current_period=PeriodMetrics(cur_start, cur_end, cur_days, cur_totals),
        previous_period=PeriodMetrics(prev_start, prev_end, prev_days, prev_totals),
        overview=overview,
        top10=top10,
        mom_by_key=mom_by_key,
        trend_df=_reindex_days(df, cur_start, cur_end),
        service_labels=labels,
        service_keys=keys,
        overview_source=overview_source,
        mom_source=mom_source,
    )
