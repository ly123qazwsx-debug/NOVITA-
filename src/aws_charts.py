"""AWS 深色看板：3 KPI + Top10 表 + 两组日趋势。"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.gridspec import GridSpec
from matplotlib.patches import FancyBboxPatch
from matplotlib.ticker import FuncFormatter

from .aws_metrics import AwsReportMetrics

BG = "#0C0C0C"
CARD = "#161410"
CARD_LINE = "#3D3820"
TEXT = "#F7F4E8"
MUTED = "#B8B08A"
GRID = "#332F1C"
ACCENT = "#FF4DA6"
UP = "#FF7B7B"
DOWN = "#5FD68A"
HEADER = "#3A1028"
UNIT = "美元"
UNIT_TAG = "单位：美元"

TREND_COLORS = [
    "#4A6FA5",
    "#F5B800",
    "#5CB8B2",
    "#8BC34A",
    "#9B7BD4",
    "#FF6B9D",
    "#9E9E9E",
    "#FFA726",
    "#66BB6A",
    "#AB47BC",
]


def _setup_font() -> None:
    from matplotlib import font_manager

    candidates = ["Noto Sans CJK SC", "Noto Sans CJK JP", "Noto Sans SC", "WenQuanYi Zen Hei", "SimHei"]
    available = {f.name for f in font_manager.fontManager.ttflist}
    chosen = next((name for name in candidates if name in available), "DejaVu Sans")
    plt.rcParams["font.sans-serif"] = [chosen, "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.facecolor"] = BG
    plt.rcParams["savefig.facecolor"] = BG
    plt.rcParams["text.color"] = TEXT
    plt.rcParams["axes.labelcolor"] = MUTED
    plt.rcParams["xtick.color"] = MUTED
    plt.rcParams["ytick.color"] = MUTED


def _rate_color(rate: float) -> str:
    if rate != rate or rate == 0:
        return MUTED
    return UP if rate > 0 else DOWN


def _rate_arrow(rate: float) -> str:
    if rate != rate or rate == 0:
        return "–"
    return "▲" if rate > 0 else "▼"


def _fmt_pct_signed(rate: float) -> str:
    if rate != rate:
        return "N/A"
    n = int(round(rate))
    return f"+{n}%" if n > 0 else f"{n}%"


def _fmt_amt(value: float) -> str:
    if value != value:
        return ""
    return f"{value:,.2f}"


def _fmt_signed_amt(value: float) -> str:
    sign = "+" if value >= 0 else "-"
    return f"{sign}{abs(value):,.2f}"


def _titled(title: str) -> str:
    return f"{title}  ｜  {UNIT_TAG}"


def _period_range(metrics: AwsReportMetrics) -> str:
    p = metrics.current_period
    return f"{p.start.month}/{p.start.day}-{p.end.month}/{p.end.day}"


def _style_ax(ax, *, grid: bool = True) -> None:
    ax.set_facecolor(CARD)
    if grid:
        ax.grid(True, color=GRID, linestyle=":", linewidth=0.9, zorder=0)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color(CARD_LINE)
    ax.spines["bottom"].set_color(CARD_LINE)
    ax.tick_params(labelsize=11, colors=MUTED)


def _value_label(ax, x, y, text: str, color: str, offset=(0, 8), fontsize: float = 8.5) -> None:
    if not text:
        return
    ax.annotate(
        text,
        (x, y),
        textcoords="offset points",
        xytext=offset,
        ha="center",
        fontsize=fontsize,
        color=color,
        zorder=6,
        bbox={"boxstyle": "round,pad=0.2", "facecolor": "#14120A", "edgecolor": color, "linewidth": 0.6, "alpha": 0.94},
    )


def _draw_kpi(ax, item: dict, metrics: AwsReportMetrics) -> None:
    titles = {
        "month_total": ("当月总消耗", _period_range(metrics)),
        "daily_avg": ("日消耗", "本期日均"),
        "forecast": (f"预计{metrics.current_period.end.month}月总消耗", "按工作日口径预估"),
    }
    title, subtitle = titles.get(item["key"], (item.get("label", ""), ""))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_facecolor(BG)
    ax.add_patch(FancyBboxPatch((0.02, 0.06), 0.96, 0.88, boxstyle="round,pad=0.018,rounding_size=0.04", facecolor=CARD, edgecolor=CARD_LINE, linewidth=1.1, transform=ax.transAxes, clip_on=False))
    ax.add_patch(FancyBboxPatch((0.02, 0.90), 0.96, 0.045, boxstyle="round,pad=0.002,rounding_size=0.01", facecolor=ACCENT, edgecolor="none", transform=ax.transAxes, clip_on=False))
    ax.text(0.07, 0.78, title, fontsize=17, fontweight="bold", color=TEXT, va="center", transform=ax.transAxes)
    ax.text(0.07, 0.62, subtitle, fontsize=13, color=MUTED, va="center", transform=ax.transAxes)
    ax.text(0.07, 0.40, _fmt_amt(item["current"]), fontsize=30, fontweight="bold", color=TEXT, va="center", transform=ax.transAxes)
    ax.text(0.07, 0.16, f"{_rate_arrow(item['rate'])} {_fmt_pct_signed(item['rate'])}    {_fmt_signed_amt(item['change'])}", fontsize=14, color=_rate_color(item["rate"]), va="center", transform=ax.transAxes)


def _plot_top10_table(ax, metrics: AwsReportMetrics) -> None:
    ax.axis("off")
    ax.set_facecolor(BG)
    end_day = metrics.current_period.end.day
    cur_m = metrics.current_period.end.month
    ax.set_title(_titled("累计消耗前10项 ｜ 分项环比明细"), fontsize=20, color=ACCENT, loc="left", pad=10, fontweight="bold")

    rows = metrics.top10
    cell_text = []
    colors = []
    for idx, item in enumerate(rows):
        stripe = "#1C1A12" if idx % 2 else "#141310"
        cell_text.append([
            item.label,
            _fmt_amt(item.current),
            _fmt_amt(item.previous),
            _fmt_signed_amt(item.change),
            _fmt_pct_signed(item.rate),
            f"{item.share:.1f}%",
        ])
        colors.append([stripe] * 6)

    table = ax.table(
        cellText=cell_text,
        colLabels=["计费项", f"{cur_m}月合计（截至{end_day}日）", "上月同期", "增减额", "环比率", "占本期成本"],
        loc="center",
        cellLoc="center",
        colColours=[HEADER] * 6,
        cellColours=colors,
    )
    table.auto_set_font_size(False)
    table.set_fontsize(13)
    table.scale(1, 1.95)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#4A1830")
        if row == 0:
            cell.set_text_props(fontweight="bold", color=TEXT)
        else:
            cell.set_text_props(color=TEXT)
            if col == 0:
                cell.set_text_props(ha="left", fontweight="bold")
            if col == 4:
                cell.set_text_props(color=_rate_color(rows[row - 1].rate), fontweight="bold")


def _date_labels(dates, month: int) -> list[str]:
    return [f"{month}/{int(d.day)}" for d in dates]


def _plot_trend(ax, metrics: AwsReportMetrics, services: list, title: str) -> None:
    df = metrics.trend_df.sort_values("date")
    _style_ax(ax)
    if df.empty or not services:
        ax.set_title(title, loc="left", color=ACCENT)
        return
    month = metrics.current_period.end.month
    x = np.arange(len(df))
    labels = _date_labels(df["date"], month)
    ymax = 1.0
    handles, labels_leg = [], []
    for i, svc in enumerate(services):
        color = TREND_COLORS[i % len(TREND_COLORS)]
        if svc.key not in df.columns:
            continue
        ax.plot(x, df[svc.key], color=color, linewidth=2.4, marker="o", markersize=5.5, label=svc.label, zorder=3)
        series = df[svc.key].dropna()
        if not series.empty:
            ymax = max(ymax, float(series.max()))
        for j, (xi, value) in enumerate(zip(x, df[svc.key])):
            if value != value or j % 3 != 0:
                continue
            _value_label(ax, xi, float(value), _fmt_amt(float(value)), color, offset=(0, 6 + (i % 3) * 4), fontsize=7.5)
        handles.append(ax.lines[-1])
        labels_leg.append(svc.label)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_xlim(-0.5, len(x) - 0.5)
    ax.set_ylim(0, ymax * 1.35)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_ylabel(f"金额（{UNIT}）", fontsize=13, color=MUTED)
    ax.set_title(_titled(title), fontsize=18, color=ACCENT, loc="left", pad=26, fontweight="bold")
    if handles:
        leg = ax.legend(handles, labels_leg, loc="lower left", bbox_to_anchor=(0, 1.01), ncol=min(5, len(handles)), fontsize=11, frameon=True)
        if leg:
            leg.get_frame().set_facecolor("#14120A")
            leg.get_frame().set_edgecolor(CARD_LINE)


def plot_aws_dashboard(metrics: AwsReportMetrics, output_dir: Path) -> Path:
    _setup_font()
    output_dir.mkdir(parents=True, exist_ok=True)
    p = metrics.current_period
    top5 = metrics.top10[:5]
    rest = metrics.top10[5:10]

    fig = plt.figure(figsize=(22.0, 24.0), facecolor=BG)
    outer = GridSpec(6, 1, height_ratios=[0.52, 0.88, 1.65, 2.55, 2.35, 0.28], hspace=0.22, top=0.975, bottom=0.03, left=0.06, right=0.94)

    title_ax = fig.add_subplot(outer[0])
    title_ax.axis("off")
    title_ax.text(0, 0.55, f"AWS {p.end.month}月成本概览（截至{p.end.month}/{p.end.day}）", fontsize=36, fontweight="bold", color=ACCENT, va="center")
    title_ax.text(1.0, 0.55, "源表口径按工作簿现有数据展示", fontsize=15, color=MUTED, ha="right", va="center")

    gs_kpi = outer[1].subgridspec(1, 3, wspace=0.08)
    for i, item in enumerate(metrics.overview):
        _draw_kpi(fig.add_subplot(gs_kpi[0, i]), item, metrics)

    _plot_top10_table(fig.add_subplot(outer[2]), metrics)
    _plot_trend(fig.add_subplot(outer[3]), metrics, top5, f"AWS {p.end.month}月日度趋势详情 ｜ 主要成本（排名 1~5）")
    _plot_trend(fig.add_subplot(outer[4]), metrics, rest, f"AWS {p.end.month}月日度趋势详情 ｜ 剩余成本（排名 6~10）")

    footer = fig.add_subplot(outer[5])
    footer.axis("off")
    footer.text(0, 0.65, f"口径说明：明细区间为 {_period_range(metrics)}；汇总数据按工作簿现有口径展示。", fontsize=12, color=MUTED)
    footer.text(0, 0.15, "数据来源：AWS.xlsx", fontsize=12, color=MUTED)
    footer.text(1.0, 0.15, f"金额单位：{UNIT}", fontsize=12, color=MUTED, ha="right")

    path = output_dir / "aws_dashboard.png"
    fig.savefig(path, dpi=165, facecolor=fig.get_facecolor())
    plt.close(fig)
    return _flatten_png(path)


def _flatten_png(path: Path) -> Path:
    from PIL import Image

    im = Image.open(path)
    if im.mode == "RGB":
        return path
    bg = Image.new("RGB", im.size, (12, 12, 10))
    rgba = im.convert("RGBA")
    bg.paste(rgba, mask=rgba.split()[-1])
    bg.save(path, "PNG", optimize=True)
    return path


def generate_aws_charts(metrics: AwsReportMetrics, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    return {"aws_dashboard": plot_aws_dashboard(metrics, output_dir)}
