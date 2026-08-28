"""AWS 飞书表结构与数据口径分析。

在生成看板前先梳理表格分区、各指标来源与一致性校验，
避免「没读懂表就画图」。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd

from .aws_metrics import AwsReportMetrics


@dataclass
class SheetRegion:
    name: str
    description: str
    rows_hint: str
    used_for: list[str]


@dataclass
class AwsSheetAnalysis:
    """AWS 工作表逻辑拆解与可视化数据映射。"""

    report_date: date
    period_label: str
    service_count: int
    daily_row_count: int
    daily_range: tuple[date | None, date | None]
    regions: list[SheetRegion] = field(default_factory=list)
    kpi_source: str = ""
    mom_source: str = ""
    trend_source: str = ""
    top10_keys: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def summary_lines(self) -> list[str]:
        lines = [
            f"【AWS 表分析】截止 {self.report_date.month}/{self.report_date.day}，区间 {self.period_label}",
            f"  日明细：{self.daily_row_count} 行（{self._fmt_range()}），{self.service_count} 个计费项",
            f"  KPI 口径：{self.kpi_source}",
            f"  分项环比：{self.mom_source}",
            f"  趋势图口径：{self.trend_source}",
        ]
        if self.top10_keys:
            lines.append(f"  Top10：{', '.join(self.top10_keys[:5])}…")
        for w in self.warnings:
            lines.append(f"  ⚠ {w}")
        return lines

    def _fmt_range(self) -> str:
        start, end = self.daily_range
        if not start or not end:
            return "无"
        return f"{start.month}/{start.day}-{end.month}/{end.day}"


def _period_label(metrics: AwsReportMetrics) -> str:
    p = metrics.current_period
    return f"{p.start.month}.{p.start.day}-{p.end.month}.{p.end.day}"


def analyze_aws_sheet(df: pd.DataFrame, metrics: AwsReportMetrics) -> AwsSheetAnalysis:
    attrs = getattr(df, "attrs", {}) or {}
    sheet_overview = attrs.get("sheet_overview") or {}
    sheet_mom = attrs.get("sheet_mom") or {}
    footer = sheet_mom.get(metrics.report_date.month) or {}

    daily = df[(df["date"] >= metrics.current_period.start) & (df["date"] <= metrics.report_date)]
    daily_start = daily["date"].min() if not daily.empty else None
    daily_end = daily["date"].max() if not daily.empty else None

    kpi_source = (
        "表内对比表（当期总消耗 / 日消耗 / 预计月总消耗）"
        if metrics.overview_source == "sheet_table"
        else "由日明细加总推算"
    )
    if footer.get("current") and footer.get("previous"):
        mom_source = "表底汇总行（当期合计 / 上月同期 / 环比率）"
    else:
        mom_source = "由上月同区间日明细加总推算"

    trend_source = f"日明细区逐日金额（{metrics.report_date.month}/1–{metrics.report_date.month}/{metrics.report_date.day}），仅 Top10 分项，不含 AWS 总消耗列"

    regions = [
        SheetRegion(
            name="日明细区",
            description="每行一天，列为各 AWS 计费项当日消耗 + AWS 总消耗",
            rows_hint="表头下一行至表底汇总行之前",
            used_for=["趋势折线图（Top10 各分项日消耗）"],
        ),
        SheetRegion(
            name="表底汇总区",
            description="当期合计、上月同期、环比率三行；上月同期为同区间对照值（非简单按月加总）",
            rows_hint="通常在第 34–36 行附近（上月同期常见在第 35 行）",
            used_for=["Top10 环比表：当期 / 上月同期 / 环比率 / 占比"],
        ),
        SheetRegion(
            name="对比表区",
            description="当期总消耗、日消耗、预计月总消耗；含本期/上期/增减/环比",
            rows_hint="表右侧或明细区下方独立行",
            used_for=["3 个 KPI 卡片"],
        ),
    ]

    warnings: list[str] = []
    period_end = sheet_overview.get("period_end")
    if period_end and period_end != metrics.report_date:
        warnings.append(f"对比表截止日 {period_end} 与报告日 {metrics.report_date} 不一致")

    if daily_end and daily_end < metrics.report_date:
        warnings.append(f"日明细最新日为 {daily_end.day} 日，早于报告截止日 {metrics.report_date.day} 日")

    if footer.get("current") and footer.get("previous"):
        footer_total = footer["current"].get("total")
        overview_total = (sheet_overview.get("month_total") or {}).get("current")
        if footer_total and overview_total and abs(footer_total - overview_total) > 1:
            warnings.append(
                f"表底当期合计 {footer_total:,.2f} 与对比表当期总消耗 {overview_total:,.2f} 有差异，KPI 以对比表为准"
            )

    return AwsSheetAnalysis(
        report_date=metrics.report_date,
        period_label=_period_label(metrics),
        service_count=len(metrics.service_keys),
        daily_row_count=len(daily),
        daily_range=(daily_start, daily_end),
        regions=regions,
        kpi_source=kpi_source,
        mom_source=mom_source,
        trend_source=trend_source,
        top10_keys=[s.label for s in metrics.top10],
        warnings=warnings,
    )


def print_aws_sheet_analysis(analysis: AwsSheetAnalysis) -> None:
    for line in analysis.summary_lines():
        print(line)
