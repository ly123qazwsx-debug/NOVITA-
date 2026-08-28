"""AWS 成本同步文字汇总与连续上涨检测。"""

from __future__ import annotations

from datetime import date

import pandas as pd

from .aws_metrics import AwsReportMetrics


def _fmt_money(value: float, symbol: str) -> str:
    return f"{symbol}{value:,.2f}"


def _pct(rate: float) -> int | None:
    if rate != rate:
        return None
    return int(round(rate))


def mom_cn(rate: float) -> str:
    pct = _pct(rate)
    if pct is None:
        return "环比暂无对照"
    if pct > 0:
        return f"环比上涨 {pct}%"
    if pct < 0:
        return f"环比下降 {abs(pct)}%"
    return "环比持平"


def _md_range(start: date, end: date) -> str:
    return f"{start.month}.{start.day}–{end.month}.{end.day}"


def is_rising_since(df: pd.DataFrame, key: str, since_day: int, *, min_days: int = 4) -> bool:
    """从 since_day 日起是否整体呈连续上涨趋势。"""
    if key not in df.columns:
        return False
    subset = df[df["date"].apply(lambda d: d.day >= since_day)].sort_values("date")
    series = subset[key].dropna()
    if len(series) < min_days:
        return False
    values = [float(v) for v in series]
    if values[-1] <= values[0] * 1.02:
        return False
    increases = sum(1 for i in range(1, len(values)) if values[i] >= values[i - 1] * 0.995)
    return increases >= max(min_days - 1, len(values) - 2)


def build_watch_highlights(metrics: AwsReportMetrics, watch_items: list[dict] | None) -> list[str]:
    lines: list[str] = []
    month = metrics.current_period.end.month
    for item in watch_items or []:
        key = item.get("key", "")
        label = item.get("label") or metrics.service_labels.get(key, key)
        since_day = int(item.get("rise_since_day") or 0)
        note = str(item.get("note") or "").strip()
        if not key or not since_day:
            continue
        if not is_rising_since(metrics.trend_df, key, since_day):
            continue
        line = f"【{label}】：从 {month} 月 {since_day} 日起，消耗连续上涨。"
        if note:
            line += note
        lines.append(line)
    return lines


def format_aws_brief(metrics: AwsReportMetrics, watch_items: list[dict] | None = None) -> str:
    p = metrics.current_period
    ov = {row["key"]: row for row in metrics.overview}
    sym = metrics.currency_symbol

    lines = [
        f"AWS 成本同步（截至 {p.end.month} 月 {p.end.day}日）",
        "",
        f"1、当期总消耗（{_md_range(p.start, p.end)}）：{_fmt_money(ov['month_total']['current'], sym)}，{mom_cn(ov['month_total']['rate'])}。",
        "",
        f"2、日消耗：{_fmt_money(ov['daily_avg']['current'], sym)}，{mom_cn(ov['daily_avg']['rate'])}。",
        "",
        f"3、预计 {p.end.month} 月总消耗：{_fmt_money(ov['forecast']['current'], sym)}，{mom_cn(ov['forecast']['rate'])}。",
        "",
        "其中：",
    ]
    highlights = build_watch_highlights(metrics, watch_items)
    if highlights:
        lines.extend(highlights)
    else:
        lines.append("（暂无配置的重点服务上涨提示，可在 config.aws.insights.watch_services 中配置）")
    return "\n".join(lines)
