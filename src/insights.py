"""按业务日报模版生成文字汇总，并检测近几日与周度异常。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from .data_fetcher import COST_COLUMNS
from .metrics import ReportMetrics


def _fmt_money(value: float, symbol: str) -> str:
    return f"{symbol}{value:,.2f}"


RISE_LABELS = {
    "llm": "LLM",
    "sd": "sd",
    "gpu_ondemand": "GPU按需",
    "gpu_storage": "GPU按需存储",
    "gpu_fixed": "机器",
}

# 业务模版优先点名这两项（LLM / 机器）
HEADLINE_KEYS = (("llm", "LLM"), ("gpu_fixed", "机器"))


def _pct(rate: float) -> int | None:
    if rate != rate:
        return None
    return int(round(rate))


def mom_cn(rate: float) -> str:
    pct = _pct(rate)
    if pct is None:
        return "环比暂无对照"
    if pct > 0:
        return f"环比上涨{pct}%"
    if pct < 0:
        return f"环比下降{abs(pct)}%"
    return "环比持平"


def _md(d: date) -> str:
    return f"{d.month}.{d.day}"


def detect_recent_spikes(metrics: ReportMetrics, lookback: int = 2, ratio: float = 1.35) -> list[str]:
    """近 lookback 天相对此前当月日均明显偏高的分项，文案对齐业务模版。"""
    df = metrics.trend_df.sort_values("date")
    if df.empty:
        return []
    recent = df.tail(lookback)
    if recent[list(RISE_LABELS)].dropna(how="all").empty:
        return []
    baseline = df.iloc[:-lookback]
    lines: list[str] = []
    for key in ("llm", "sd", "gpu_ondemand", "gpu_fixed"):
        base_avg = float(baseline[key].mean()) if not baseline.empty else 0.0
        if base_avg <= 0 or base_avg != base_avg:
            continue
        hot = recent[recent[key] >= base_avg * ratio]
        hot = hot.dropna(subset=[key])
        if hot.empty:
            continue
        day_txt = "、".join(f"{int(row.date.day)}号" for row in hot.itertuples())
        lines.append(f"{RISE_LABELS[key]}{day_txt}消耗增长较大，辛苦查看一下异常")
    return lines


def rising_items(metrics: ReportMetrics, min_rate: float = 8.0) -> list[str]:
    ranked = []
    for key in COST_COLUMNS:
        rate = metrics.mom_changes[key]["rate"]
        if rate == rate and rate >= min_rate:
            ranked.append((rate, key))
    ranked.sort(reverse=True)
    return [f"{RISE_LABELS[k]}（{mom_cn(r)}）" for r, k in ranked]


def _rising_headline(metrics: ReportMetrics, extra_notes: list[str], min_rate: float = 8.0) -> str | None:
    names: list[str] = []
    for key, label in HEADLINE_KEYS:
        rate = metrics.mom_changes[key]["rate"]
        if rate == rate and rate >= min_rate:
            names.append(label)
    if not names:
        names = [item.split("（")[0] for item in rising_items(metrics, min_rate)]
    if names:
        text = "以" + "\\".join(names) + "上涨比较明显"
        if extra_notes:
            text += "（" + "；".join(extra_notes) + "）"
        return text
    if extra_notes:
        return "；".join(extra_notes)
    return None


@dataclass
class WeekBucket:
    index: int
    start: date
    end: date
    totals: dict[str, float]
    daily_avg: dict[str, float]
    days: int


def _week_index(day: int) -> int:
    return (day - 1) // 7 + 1


def _bucket_weeks(df: pd.DataFrame, month: int) -> list[WeekBucket]:
    if df.empty:
        return []
    subset = df[df["date"].apply(lambda d: d.month == month)].copy()
    if subset.empty:
        return []
    subset = subset.sort_values("date")
    buckets: dict[int, list[dict]] = {}
    for row in subset.itertuples():
        idx = _week_index(row.date.day)
        buckets.setdefault(idx, []).append(row._asdict())

    result: list[WeekBucket] = []
    for idx in sorted(buckets):
        rows = buckets[idx]
        start = min(r["date"] for r in rows)
        end = max(r["date"] for r in rows)
        days = len(rows)
        totals = {key: float(sum(r.get(key, 0.0) or 0.0 for r in rows)) for key in COST_COLUMNS}
        totals["total_with_fixed"] = float(sum(r.get("total_with_fixed", 0.0) or 0.0 for r in rows))
        totals["total_ondemand"] = float(sum(r.get("total_ondemand", 0.0) or 0.0 for r in rows))
        daily_avg = {key: totals[key] / days if days else 0.0 for key in totals}
        result.append(WeekBucket(index=idx, start=start, end=end, totals=totals, daily_avg=daily_avg, days=days))
    return result


def _week_label(bucket: WeekBucket) -> str:
    return f"第{bucket.index}周（{bucket.start.month}.{bucket.start.day}-{bucket.end.month}.{bucket.end.day}）"


def _fmt_week_money(value: float, symbol: str) -> str:
    return f"{symbol}{value:,.2f}"


def build_weekly_summary(metrics: ReportMetrics) -> list[str]:
    """按自然周（每月 1-7、8-14…）汇总当周总消耗与环比。"""
    weeks = _bucket_weeks(metrics.trend_df, metrics.current_period.end.month)
    if not weeks:
        return []
    sym = metrics.currency_symbol
    lines = ["【每周消耗汇总】"]
    for i, week in enumerate(weeks):
        total = week.totals["total_with_fixed"]
        if i == 0:
            lines.append(f"{_week_label(week)}：总消耗 {_fmt_week_money(total, sym)}（首周，无上周对照）")
            continue
        prev = weeks[i - 1].totals["total_with_fixed"]
        if prev <= 0:
            lines.append(f"{_week_label(week)}：总消耗 {_fmt_week_money(total, sym)}")
            continue
        rate = (total - prev) / prev * 100
        lines.append(
            f"{_week_label(week)}：总消耗 {_fmt_week_money(total, sym)}（较上周 {mom_cn(rate)}，"
            f"日均 {_fmt_week_money(total / week.days, sym)}）"
        )
    return lines


def detect_weekly_anomalies(
    metrics: ReportMetrics,
    *,
    wow_threshold: float = 20.0,
    daily_ratio: float = 1.45,
) -> list[str]:
    """检测周环比异常抬升，以及周内明显高于当周均值的日子。"""
    month = metrics.current_period.end.month
    weeks = _bucket_weeks(metrics.trend_df, month)
    if len(weeks) < 1:
        return []

    sym = metrics.currency_symbol
    lines: list[str] = []
    for i, week in enumerate(weeks):
        if i > 0:
            prev = weeks[i - 1]
            for key in COST_COLUMNS:
                cur = week.totals[key]
                base = prev.totals[key]
                if base <= 0 or cur <= 0:
                    continue
                rate = (cur - base) / base * 100
                if rate >= wow_threshold:
                    lines.append(
                        f"{_week_label(week)} {RISE_LABELS[key]} 较上周上涨 {int(round(rate))}%"
                        f"（{_fmt_week_money(cur, sym)} vs {_fmt_week_money(base, sym)}）"
                    )

        week_df = metrics.trend_df[
            (metrics.trend_df["date"] >= week.start) & (metrics.trend_df["date"] <= week.end)
        ]
        for key in COST_COLUMNS:
            series = week_df[["date", key]].dropna()
            if series.empty:
                continue
            avg = float(series[key].mean())
            if avg <= 0:
                continue
            hot = series[series[key] >= avg * daily_ratio]
            if hot.empty:
                continue
            day_txt = "、".join(f"{int(row.date.day)}号" for row in hot.itertuples())
            lines.append(
                f"{_week_label(week)} {RISE_LABELS[key]} 在 {day_txt} 明显高于当周日均"
                f"（当周日均 {_fmt_week_money(avg, sym)}）"
            )

    # 与上月同周对照（例如 8 月第 2 周 vs 7 月第 2 周）
    prev_df = metrics.prev_trend_df
    if not prev_df.empty:
        prev_month = metrics.previous_period.end.month
        prev_weeks = _bucket_weeks(prev_df, prev_month)
        prev_map = {w.index: w for w in prev_weeks}
        for week in weeks:
            prev_week = prev_map.get(week.index)
            if not prev_week:
                continue
            for key in ("total_with_fixed", "llm", "gpu_fixed"):
                cur = week.totals[key]
                base = prev_week.totals[key]
                if base <= 0:
                    continue
                rate = (cur - base) / base * 100
                if rate >= wow_threshold:
                    label = "总消耗" if key == "total_with_fixed" else RISE_LABELS[key]
                    lines.append(
                        f"{_week_label(week)} {label} 高于上月同周 {int(round(rate))}%"
                        f"（{_fmt_week_money(cur, sym)} vs {_fmt_week_money(base, sym)}）"
                    )
    return lines


def format_weekly_section(metrics: ReportMetrics) -> str:
    summary = build_weekly_summary(metrics)
    anomalies = detect_weekly_anomalies(metrics)
    if not summary and not anomalies:
        return ""
    parts = list(summary)
    if anomalies:
        parts.append("")
        parts.append("【周度异常】")
        for i, line in enumerate(anomalies, start=1):
            parts.append(f"{i}、{line}")
    return "\n".join(parts)


def build_highlights(metrics: ReportMetrics, extra_notes: list[str] | None = None) -> list[str]:
    extra_notes = [str(n).strip() for n in (extra_notes or []) if str(n).strip()]
    points: list[str] = []

    headline = _rising_headline(metrics, extra_notes)
    if headline:
        points.append(headline)

    spikes = detect_recent_spikes(metrics)
    if spikes:
        points.extend(spikes)
    return points


def format_daily_brief(metrics: ReportMetrics, extra_notes: list[str] | None = None) -> str:
    """业务指定的日报文字模版。"""
    p = metrics.current_period
    ov = {row["key"]: row for row in metrics.overview}
    sym = metrics.currency_symbol

    def money(key: str) -> str:
        return _fmt_money(ov[key]["current"], sym)

    lines = [
        f"NOVITA（截止到{p.end.month}月{p.end.day}号）：",
        f"1、当月总消耗（{_md(p.start)}-{_md(p.end)}）——{money('month_total')}  ({mom_cn(ov['month_total']['rate'])}）",
        f"2、日消耗-含固定GPU——{money('daily_with_fixed')}  ({mom_cn(ov['daily_with_fixed']['rate'])}）",
        f"3、日消耗-按需(LLM/SD/GPU按需/存储）——{money('daily_ondemand')}  ({mom_cn(ov['daily_ondemand']['rate'])}）",
        f"4、预计{p.end.month}月总消耗——{money('forecast')}  （{mom_cn(ov['forecast']['rate'])}）",
        "",
        "其中：",
    ]
    for i, point in enumerate(build_highlights(metrics, extra_notes), start=1):
        lines.append(f"{i}、{point}")
    weekly = format_weekly_section(metrics)
    if weekly:
        lines.extend(["", weekly])
    return "\n".join(lines)
