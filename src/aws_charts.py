"""AWS 深色看板：模板 KPI + Top10 表 + 前十项分项日趋势（不含总费用）。"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.gridspec import GridSpec
from matplotlib.patches import FancyBboxPatch
from matplotlib.ticker import FuncFormatter

from .aws_metrics import AwsReportMetrics
from .aws_sheet_analysis import AwsSheetAnalysis

# 配色从用户上传模板像素采样
BG = "#06121B"
CARD = "#0D202D"
CARD_ALT = "#112938"
CARD_LINE = "#183746"
TEXT = "#EDF4F7"
MUTED = "#9EB0B8"
GRID = "#1C313E"
ACCENT = "#F283C1"
TITLE = "#EDF4F7"
UP = "#F283C1"
DOWN = "#67DDB4"
HEADER = "#112938"
TABLE_EDGE = "#183746"
LABEL_BG = "#0D202D"
UNIT = "USD"
UNIT_TAG = "单位：USD"

SERVICE_COLORS = {
    "rds": "#5DA5E8",
    "s3": "#F2D84B",
    "elb": "#46D3D0",
    "ecs": "#67DDB4",
    "ec2_instance": "#A792ED",
    "amplify": "#F283C1",
    "cloudfront": "#F3A65E",
    "elasticache": "#EFD64B",
    "vpc": "#D6E86A",
    "ec2_other": "#5CA4E6",
}


def _setup_font() -> None:
    from matplotlib import font_manager

    candidates = [
        "Noto Sans CJK SC",
        "Noto Sans CJK JP",
        "Noto Sans SC",
        "WenQuanYi Micro Hei",
        "WenQuanYi Zen Hei",
        "Droid Sans Fallback",
        "SimHei",
    ]
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


def _fmt_amt(value: float, symbol: str = "") -> str:
    if value != value:
        return ""
    body = f"{value:,.2f}"
    return f"{symbol}{body}" if symbol else body


def _fmt_signed_amt(value: float, symbol: str = "") -> str:
    sign = "+" if value >= 0 else "-"
    body = f"{abs(value):,.2f}"
    return f"{sign}{symbol}{body}" if symbol else f"{sign}{body}"


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


def _value_label(ax, x, y, text: str, color: str, offset=(0, 8), fontsize: float = 7.5) -> None:
    if not text:
        return
    ax.annotate(
        text,
        (x, y),
        textcoords="offset points",
        xytext=offset,
        ha="center",
        va="center",
        fontsize=fontsize,
        color=color,
        zorder=6,
        annotation_clip=False,
        bbox={
            "boxstyle": "round,pad=0.18",
            "facecolor": LABEL_BG,
            "edgecolor": color,
            "linewidth": 0.55,
            "alpha": 0.96,
        },
    )


def _draw_kpi(ax, item: dict, metrics: AwsReportMetrics) -> None:
    sym = metrics.currency_symbol
    titles = {
        "month_total": ("当月总消耗", _period_range(metrics)),
        "daily_avg": ("日消耗", "本期日均"),
        "forecast": (f"预计{metrics.current_period.end.month}月总消耗", "按工作簿预估"),
    }
    title, subtitle = titles.get(item["key"], (item.get("label", ""), ""))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_facecolor(BG)
    ax.add_patch(
        FancyBboxPatch(
            (0.02, 0.06), 0.96, 0.88,
            boxstyle="round,pad=0.018,rounding_size=0.04",
            facecolor=CARD, edgecolor=CARD_LINE, linewidth=1.1,
            transform=ax.transAxes, clip_on=False,
        )
    )
    ax.add_patch(
        FancyBboxPatch(
            (0.02, 0.90), 0.96, 0.045,
            boxstyle="round,pad=0.002,rounding_size=0.01",
            facecolor=ACCENT, edgecolor="none",
            transform=ax.transAxes, clip_on=False,
        )
    )
    ax.text(0.07, 0.78, title, fontsize=17, fontweight="bold", color=TEXT, va="center", transform=ax.transAxes)
    ax.text(0.07, 0.62, subtitle, fontsize=13, color=MUTED, va="center", transform=ax.transAxes)
    ax.text(0.07, 0.40, _fmt_amt(item["current"], sym), fontsize=30, fontweight="bold", color=TEXT, va="center", transform=ax.transAxes)
    ax.text(
        0.07, 0.16,
        f"{_rate_arrow(item['rate'])} {_fmt_pct_signed(item['rate'])}    {_fmt_signed_amt(item['change'], sym)}",
        fontsize=14, color=_rate_color(item["rate"]), va="center", transform=ax.transAxes,
    )


def _plot_top10_table(ax, metrics: AwsReportMetrics) -> None:
    ax.axis("off")
    ax.set_facecolor(BG)
    p = metrics.current_period
    sym = metrics.currency_symbol
    ax.text(
        0, 1.02,
        f"累计消耗前10项 ｜ 分项环比明细 ｜ {UNIT_TAG}",
        fontsize=20, color=TITLE, fontweight="bold", transform=ax.transAxes, va="bottom",
    )
    ax.text(
        0, 0.97,
        "对比区间：本期明细与上月同期",
        fontsize=13, color=MUTED, transform=ax.transAxes, va="bottom",
    )

    rows = metrics.top10
    cell_text = []
    colors = []
    for idx, item in enumerate(rows):
        stripe = CARD_ALT if idx % 2 else CARD
        cell_text.append([
            item.label,
            _fmt_amt(item.current, sym),
            _fmt_amt(item.previous, sym),
            _fmt_signed_amt(item.change, sym),
            _fmt_pct_signed(item.rate),
            f"{item.share:.1f}%",
        ])
        colors.append([stripe] * 6)

    table = ax.table(
        cellText=cell_text,
        colLabels=[
            "计费项",
            f"{p.end.month}月合计（截至{p.end.day}日）",
            "上月同期",
            "增减金额",
            "环比率",
            "占本期成本",
        ],
        loc="center",
        cellLoc="center",
        colColours=[HEADER] * 6,
        cellColours=colors,
        bbox=[0, 0.02, 1, 0.90],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(13)
    table.scale(1, 1.95)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor(TABLE_EDGE)
        cell.set_linewidth(0.55)
        if row == 0:
            cell.set_text_props(fontweight="bold", color=TEXT)
        else:
            cell.set_text_props(color=TEXT)
            if col == 0:
                cell.set_text_props(ha="left", fontweight="bold")
                cell.PAD = 0.12
            if col in (3, 4):
                cell.set_text_props(color=_rate_color(rows[row - 1].rate), fontweight="bold")


def _date_labels(dates, month: int) -> list[str]:
    return [f"{month}月{int(d.day)}日" for d in dates]


def _service_color(key: str, index: int) -> str:
    return SERVICE_COLORS.get(key, list(SERVICE_COLORS.values())[index % len(SERVICE_COLORS)])


def _plot_service_trend(ax, metrics: AwsReportMetrics, svc, rank: int) -> None:
    """排名前十各分项单独日趋势，不画 AWS 总费用。"""
    df = metrics.trend_df.sort_values("date")
    _style_ax(ax)
    if df.empty or svc.key not in df.columns:
        ax.set_title(f"No.{rank} {svc.label}", loc="left", color=TITLE, fontweight="bold", fontsize=13)
        return

    month = metrics.current_period.end.month
    x = np.arange(len(df))
    labels = _date_labels(df["date"], month)
    color = _service_color(svc.key, rank - 1)
    series = df[svc.key]
    ax.plot(x, series, color=color, linewidth=2.2, marker="o", markersize=4.5, zorder=3)
    ymax = float(series.dropna().max()) if not series.dropna().empty else 1.0
    for j, (xi, value) in enumerate(zip(x, series)):
        if value != value:
            continue
        stagger = (0, 6 + (j % 2) * 3)
        _value_label(ax, xi, float(value), _fmt_amt(float(value)), color, offset=stagger, fontsize=6.5)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8, rotation=45, ha="right")
    ax.set_xlim(-0.5, len(x) - 0.5)
    ax.set_ylim(0, ymax * 1.35)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_title(f"No.{rank} {svc.label}", fontsize=13, color=TITLE, loc="left", pad=8, fontweight="bold")


def plot_aws_dashboard(metrics: AwsReportMetrics, output_dir: Path, *, analysis: AwsSheetAnalysis | None = None) -> Path:
    _setup_font()
    output_dir.mkdir(parents=True, exist_ok=True)
    p = metrics.current_period
    top10 = metrics.top10

    fig = plt.figure(figsize=(15.7, 28.0), facecolor=BG)
    outer = GridSpec(
        6, 1,
        height_ratios=[0.45, 0.82, 1.55, 0.16, 4.8, 0.22],
        hspace=0.22,
        top=0.975,
        bottom=0.03,
        left=0.06,
        right=0.94,
    )

    title_ax = fig.add_subplot(outer[0])
    title_ax.axis("off")
    title_ax.set_facecolor(BG)
    title_ax.text(
        0, 0.72,
        f"AWS {p.end.month}月成本概览 (截至 {p.end.month}/{p.end.day})",
        fontsize=34, fontweight="bold", color=TITLE, va="center",
    )
    title_ax.text(
        0, 0.22,
        f"统计区间：{_period_range(metrics)} · {UNIT_TAG}",
        fontsize=14, color=MUTED, va="center",
    )
    title_ax.text(
        1.0, 0.55,
        "成本前十项 · 分项日趋势",
        fontsize=14, color=MUTED, ha="right", va="center",
    )

    gs_kpi = outer[1].subgridspec(1, 3, wspace=0.08)
    for i, item in enumerate(metrics.overview):
        _draw_kpi(fig.add_subplot(gs_kpi[0, i]), item, metrics)

    _plot_top10_table(fig.add_subplot(outer[2]), metrics)

    trend_title_ax = fig.add_subplot(outer[3])
    trend_title_ax.axis("off")
    trend_title_ax.set_facecolor(BG)
    trend_title_ax.text(
        0, 0.5,
        "排名前十 ｜ 各分项成本日趋势（不含 AWS 总费用）",
        fontsize=18, color=TITLE, va="center", fontweight="bold",
    )

    gs_trend = outer[4].subgridspec(5, 2, hspace=0.55, wspace=0.18)
    for i, svc in enumerate(top10):
        row, col = divmod(i, 2)
        _plot_service_trend(fig.add_subplot(gs_trend[row, col]), metrics, svc, i + 1)

    footer = fig.add_subplot(outer[5])
    footer.axis("off")
    footer.set_facecolor(BG)
    footer.text(
        0, 0.65,
        f"口径说明：明细区间为 {_period_range(metrics)}；上月同期取表底 A35「上月同期」行；趋势仅展示排名前十各分项，不含 AWS 总费用。",
        fontsize=12, color=MUTED,
    )
    footer.text(0, 0.15, "数据来源：AWS.xlsx", fontsize=12, color=MUTED)
    footer.text(1.0, 0.15, f"金额单位：{UNIT}", fontsize=12, color=MUTED, ha="right")

    path = output_dir / "aws_dashboard.png"
    fig.savefig(path, dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)
    return _flatten_png(path)


def _flatten_png(path: Path) -> Path:
    from PIL import Image

    im = Image.open(path)
    if im.mode == "RGB":
        return path
    bg = Image.new("RGB", im.size, (6, 18, 27))
    rgba = im.convert("RGBA")
    bg.paste(rgba, mask=rgba.split()[-1])
    bg.save(path, "PNG", optimize=True)
    return path


def generate_aws_charts(
    metrics: AwsReportMetrics,
    output_dir: Path,
    *,
    analysis: AwsSheetAnalysis | None = None,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    return {"aws_dashboard": plot_aws_dashboard(metrics, output_dir, analysis=analysis)}
