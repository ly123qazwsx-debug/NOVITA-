"""统计截止日期：以表内数据与汇总行标注为准，不盲目用日历「昨天」。"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

OVERVIEW_PERIOD_RE = re.compile(r"(\d{1,2})\.(\d{1,2})[-–—](\d{1,2})\.(\d{1,2})")


def parse_overview_period_end(label: str, year: int) -> date | None:
    """从「当期总消耗（8.1-8.26）」解析截止日。"""
    text = (label or "").replace(" ", "").replace("　", "")
    match = OVERVIEW_PERIOD_RE.search(text)
    if not match:
        return None
    try:
        return date(year, int(match.group(3)), int(match.group(4)))
    except ValueError:
        return None


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, pd.Timestamp):
        return value.date()
    return None


def _latest_daily_in_month(df: pd.DataFrame, cap: date) -> date | None:
    month_start = cap.replace(day=1)
    subset = df[(df["date"] >= month_start) & (df["date"] <= cap)]
    if subset.empty:
        return None
    return _as_date(subset["date"].max())


def resolve_report_date(
    df: pd.DataFrame,
    config: dict[str, Any],
    *,
    as_of: date | None = None,
) -> date:
    """确定报告截止日。

    优先级：显式 as_of / 配置 > 表内汇总标注截止日 > 当月最新明细日 > 昨天。
    """
    tz = ZoneInfo(config["report"]["timezone"])
    cap = datetime.now(tz).date() - timedelta(days=1)

    forced = as_of
    configured = config.get("report", {}).get("as_of")
    if configured:
        forced = date.fromisoformat(str(configured))
    if forced is not None:
        return min(forced, cap)

    attrs = getattr(df, "attrs", {}) or {}
    overview = attrs.get("sheet_overview") or {}
    period_end = _as_date(overview.get("period_end"))
    if period_end and period_end <= cap:
        return period_end

    latest = _latest_daily_in_month(df, cap)
    if latest:
        return latest

    return cap


def overview_matches_report(sheet_overview: dict[str, Any], report_date: date) -> bool:
    """表内 KPI 汇总行是否与当前截止日一致。"""
    period_end = _as_date(sheet_overview.get("period_end"))
    if period_end is None:
        return True
    return period_end == report_date
