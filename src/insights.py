"""按业务日报模版生成文字汇总，并检测近几日异常。"""

from __future__ import annotations

from datetime import date

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
    return "\n".join(lines)
