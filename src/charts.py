"""深色综合看板：KPI + 分项环比表 + 主成本/按需日趋势（对齐业务模板）。"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.gridspec import GridSpec
from matplotlib.patches import FancyBboxPatch
from matplotlib.ticker import FuncFormatter

from .metrics import CATEGORY_LABELS, ReportMetrics

BG = "#0C0C0C"
CARD = "#161410"
CARD_LINE = "#3D3820"
TEXT = "#F7F4E8"
MUTED = "#B8B08A"
GRID = "#332F1C"
ACCENT = "#FFD400"
BAR_FIXED = "#FFD400"
UP = "#FF7B7B"
DOWN = "#5FD68A"
HEADER_GOLD = "#3A3100"
UNIT = "美元"
UNIT_TAG = "单位：美元"

LINE_COLORS = {
    "llm": "#5CE1E6",
    "sd": "#FF6B2C",
    "gpu_ondemand": "#C4A0FF",
    "gpu_storage": "#7DD3FC",
}

# 分项表行顺序与模板一致
MOM_ROW_ORDER = ["llm", "sd", "gpu_ondemand", "gpu_storage", "gpu_fixed"]


def _setup_font() -> None:
    from matplotlib import font_manager

    candidates = [
        "Noto Sans CJK SC",
        "Noto Sans CJK JP",
        "Noto Sans SC",
        "Source Han Sans SC",
        "WenQuanYi Zen Hei",
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
    number = int(round(rate))
    if number > 0:
        return f"+{number}%"
    return f"{number}%"


def _fmt_amt(value: float, decimals: int = 2) -> str:
    if value != value:
        return ""
    return f"{value:,.{decimals}f}"


def _fmt_signed_amt(value: float) -> str:
    sign = "+" if value >= 0 else "-"
    return f"{sign}{abs(value):,.2f}"


def _fmt_day_amt(value: float) -> str:
    return _fmt_amt(value)


def _money_axis(ax) -> None:
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))


def _titled(title: str) -> str:
    return f"{title}  ｜  {UNIT_TAG}"


def _period_range_label(metrics: ReportMetrics) -> str:
    p = metrics.current_period
    return f"{p.start.month}/{p.start.day}-{p.end.month}/{p.end.day}"


def _kpi_title_subtitle(item: dict, metrics: ReportMetrics) -> tuple[str, str]:
    key = item["key"]
    month = metrics.current_period.end.month
    mapping = {
        "month_total": ("当月总消耗", _period_range_label(metrics)),
        "daily_with_fixed": ("日消耗 · 含固定GPU", "本期日均"),
        "daily_ondemand": ("日消耗 · 按需计费", "LLM/SD/按需GPU/存储"),
        "forecast": (f"预计{month}月总消耗", "按现有数据口径"),
    }
    return mapping.get(key, (item.get("label", key), UNIT_TAG))


def _style_ax(ax, *, both_grids: bool = False) -> None:
    ax.set_facecolor(CARD)
    ax.grid(axis="y", color=GRID, linestyle=":", linewidth=1.0, zorder=0)
    if both_grids:
        ax.grid(True, color=GRID, linestyle=":", linewidth=0.9, zorder=0)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(CARD_LINE)
    ax.spines["bottom"].set_color(CARD_LINE)
    ax.tick_params(labelsize=13, colors=MUTED, width=1.1, length=5)
    ax.title.set_color(TEXT)


def _legend(ax, **kwargs) -> None:
    kwargs.setdefault("fontsize", 14)
    kwargs.setdefault("handlelength", 1.6)
    kwargs.setdefault("borderpad", 0.6)
    leg = ax.legend(frameon=True, **kwargs)
    if leg is None:
        return
    frame = leg.get_frame()
    frame.set_facecolor("#14120A")
    frame.set_edgecolor(CARD_LINE)
    frame.set_linewidth(0.6)
    for text in leg.get_texts():
        text.set_color(TEXT)


def _value_label(ax, x, y, text: str, color: str, offset=(0, 9), fontsize: float = 9.0) -> None:
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
            "boxstyle": "round,pad=0.22",
            "facecolor": "#14120A",
            "edgecolor": color,
            "linewidth": 0.7,
            "alpha": 0.94,
        },
    )


def _draw_kpi(ax, item: dict, metrics: ReportMetrics) -> None:
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_facecolor(BG)
    ax.add_patch(
        FancyBboxPatch(
            (0.02, 0.06),
            0.96,
            0.88,
            boxstyle="round,pad=0.018,rounding_size=0.04",
            facecolor=CARD,
            edgecolor=CARD_LINE,
            linewidth=1.1,
            transform=ax.transAxes,
            clip_on=False,
        )
    )
    ax.add_patch(
        FancyBboxPatch(
            (0.02, 0.90),
            0.96,
            0.045,
            boxstyle="round,pad=0.002,rounding_size=0.01",
            facecolor=ACCENT,
            edgecolor="none",
            transform=ax.transAxes,
            clip_on=False,
        )
    )
    title, subtitle = _kpi_title_subtitle(item, metrics)
    ax.text(0.07, 0.78, title, fontsize=17, fontweight="bold", color=TEXT, va="center", transform=ax.transAxes)
    ax.text(0.07, 0.62, subtitle, fontsize=13, color=MUTED, va="center", transform=ax.transAxes)
    ax.text(
        0.07,
        0.40,
        _fmt_amt(item["current"]),
        fontsize=30,
        fontweight="bold",
        color=TEXT,
        va="center",
        transform=ax.transAxes,
    )
    rate = item["rate"]
    change = item["change"]
    ax.text(
        0.07,
        0.16,
        f"{_rate_arrow(rate)} {_fmt_pct_signed(rate)}    {_fmt_signed_amt(change)}",
        fontsize=14,
        color=_rate_color(rate),
        va="center",
        transform=ax.transAxes,
    )


def _plot_detail_table(ax, metrics: ReportMetrics) -> None:
    ax.axis("off")
    ax.set_facecolor(BG)
    month_total = metrics.current_period.totals["total_with_fixed"]
    cur_m = metrics.current_period.end.month
    end_day = metrics.current_period.end.day
    ax.set_title(
        _titled("分项环比明细 (上月同期)"),
        fontsize=20,
        color=ACCENT,
        loc="left",
        pad=10,
        fontweight="bold",
    )

    rows = [{"key": k, "label": CATEGORY_LABELS[k], **metrics.mom_changes[k]} for k in MOM_ROW_ORDER]
    rows.append({"key": "total", "label": "总消耗", **metrics.mom_changes["total_with_fixed"]})

    cell_text = []
    cell_colors = []
    for idx, item in enumerate(rows):
        share = item["current"] / month_total * 100 if month_total else 0
        is_total = item["key"] == "total"
        stripe = "#2E2A12" if is_total else ("#1C1A12" if idx % 2 else "#141310")
        rate = item["rate"]
        cell_text.append(
            [
                item["label"],
                _fmt_amt(item["current"]),
                _fmt_amt(item["previous"]),
                _fmt_signed_amt(item["change"]),
                _fmt_pct_signed(rate) if rate == rate else "N/A",
                f"{share:.1f}%",
            ]
        )
        cell_colors.append([stripe] * 6)

    table = ax.table(
        cellText=cell_text,
        colLabels=[
            "计费项",
            f"{cur_m}月合计（截至{end_day}日）",
            "上月同期",
            "增减额",
            "环比率",
            "占本期成本",
        ],
        loc="center",
        cellLoc="center",
        colColours=[HEADER_GOLD] * 6,
        cellColours=cell_colors,
    )
    table.auto_set_font_size(False)
    table.set_fontsize(15)
    table.scale(1, 2.05)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#4A4018")
        cell.set_linewidth(0.55)
        if row == 0:
            cell.set_text_props(fontweight="bold", color=TEXT)
            cell.set_facecolor(HEADER_GOLD)
        else:
            cell.set_text_props(color=TEXT)
            if col == 0:
                cell.set_text_props(ha="left", fontweight="bold")
                cell.PAD = 0.12
            if col == 4:
                rate = rows[row - 1]["rate"]
                cell.set_text_props(color=_rate_color(rate), fontweight="bold")
            if row == len(rows):
                cell.set_text_props(fontweight="bold")
                if col in (1, 2, 3, 5):
                    cell.set_text_props(color=ACCENT)
                elif col == 4:
                    cell.set_text_props(color=_rate_color(rows[row - 1]["rate"]))


def _date_labels(dates, month: int) -> list[str]:
    return [f"{month}/{int(d.day)}" if hasattr(d, "day") else str(d) for d in dates]


def _plot_main_trend(ax, metrics: ReportMetrics) -> None:
    """GPU 固定（左轴柱）+ LLM / sd（右轴折线）。"""
    df = metrics.trend_df.sort_values("date").copy()
    _style_ax(ax, both_grids=True)
    if df.empty:
        ax.set_title("暂无趋势数据", loc="left", color=ACCENT)
        return

    month = metrics.current_period.end.month
    x = np.arange(len(df))
    labels = _date_labels(df["date"], month)

    mask = df["gpu_fixed"].notna()
    ax.bar(
        x[mask.to_numpy()],
        df.loc[mask, "gpu_fixed"],
        width=0.68,
        color=BAR_FIXED,
        alpha=0.92,
        label="GPU固定",
        zorder=2,
    )
    ax.set_ylabel(f"GPU固定（{UNIT}）", fontsize=14, color=BAR_FIXED)
    ax.tick_params(axis="y", colors=BAR_FIXED, labelsize=12)
    _money_axis(ax)

    ax2 = ax.twinx()
    ax2.set_facecolor("none")
    ax2.spines["top"].set_visible(False)
    ax2.spines["left"].set_visible(False)
    ax2.spines["right"].set_color("#5CE1E6")
    ax2.grid(False)
    ax2.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax2.tick_params(axis="y", labelsize=12, colors="#5CE1E6")

    line_specs = [
        ("llm", "LLM", "o", (0, 12), LINE_COLORS["llm"]),
        ("sd", "sd", "s", (0, -12), LINE_COLORS["sd"]),
    ]
    for key, label, marker, offset, color in line_specs:
        ax2.plot(
            x,
            df[key],
            color=color,
            linewidth=2.6,
            marker=marker,
            markersize=7.5,
            label=label,
            zorder=3,
        )
        for i, (xi, value) in enumerate(zip(x, df[key])):
            if value != value:
                continue
            day_offset = (0, offset[1] + (4 if i % 2 == 0 else -4))
            _value_label(ax2, xi, float(value), _fmt_day_amt(float(value)), color, offset=day_offset, fontsize=9)

    ax2.set_ylabel(f"LLM / sd（{UNIT}）", fontsize=14, color=MUTED)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=11, rotation=0)
    ax.set_xlim(-0.65, len(x) - 0.35)
    vals = df["gpu_fixed"].dropna()
    ax.set_ylim(0, max(float(vals.max()) * 1.28 if not vals.empty else 0.0, 1))
    ondemand_max = 0.0
    for key, _, _, _, _ in line_specs:
        series = df[key].dropna()
        if not series.empty:
            ondemand_max = max(ondemand_max, float(series.max()))
    ax2.set_ylim(0, max(ondemand_max * 1.42, 1))

    for xi, value in zip(x[mask.to_numpy()], df.loc[mask, "gpu_fixed"]):
        _value_label(ax, xi, float(value), _fmt_day_amt(float(value)), BAR_FIXED, offset=(0, 11), fontsize=9)

    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.set_title(
        _titled(f"NOVITA {month}月日度趋势详情 ｜ 主要成本"),
        fontsize=20,
        color=ACCENT,
        loc="left",
        pad=30,
        fontweight="bold",
    )
    _legend(
        ax,
        handles=h1 + h2,
        labels=l1 + l2,
        loc="lower left",
        bbox_to_anchor=(0.0, 1.01),
        ncol=3,
        borderaxespad=0,
    )


def _plot_ondemand_trend(ax, metrics: ReportMetrics) -> None:
    """按需成本趋势：GPU 按需 + GPU 按需存储。"""
    df = metrics.trend_df.sort_values("date").copy()
    _style_ax(ax, both_grids=True)
    _money_axis(ax)
    if df.empty:
        ax.set_title("暂无趋势数据", loc="left", color=ACCENT)
        return

    month = metrics.current_period.end.month
    x = np.arange(len(df))
    labels = _date_labels(df["date"], month)
    specs = [
        ("gpu_ondemand", "GPU (按需)", "o", (0, 10), LINE_COLORS["gpu_ondemand"]),
        ("gpu_storage", "GPU (按需存储)", "D", (0, -11), LINE_COLORS["gpu_storage"]),
    ]
    ymax = 1.0
    for key, label, marker, offset, color in specs:
        ax.plot(
            x,
            df[key],
            color=color,
            linewidth=2.6,
            marker=marker,
            markersize=7.5,
            label=label,
            zorder=3,
        )
        series = df[key].dropna()
        if not series.empty:
            ymax = max(ymax, float(series.max()))
        for i, (xi, value) in enumerate(zip(x, df[key])):
            if value != value:
                continue
            amount = float(value)
            if amount < 1:
                day_offset = (-14 if key == "gpu_ondemand" else 14, 10)
            else:
                stagger = 4 if i % 2 == 0 else -4
                day_offset = (0, offset[1] + stagger)
            _value_label(ax, xi, amount, _fmt_day_amt(amount), color, offset=day_offset, fontsize=9)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=11)
    ax.set_xlim(-0.65, len(x) - 0.35)
    ax.set_ylim(0, max(ymax * 1.45, 10))
    ax.set_ylabel(f"金额（{UNIT}）", fontsize=14, color=MUTED)
    ax.set_title(
        _titled("按需成本趋势 (GPU按需 / GPU按需存储)"),
        fontsize=20,
        color=ACCENT,
        loc="left",
        pad=28,
        fontweight="bold",
    )
    _legend(ax, loc="lower left", bbox_to_anchor=(0.0, 1.01), ncol=2, borderaxespad=0)


def plot_dashboard(
    metrics: ReportMetrics,
    output_dir: Path,
    extra_notes: list[str] | None = None,
) -> Path:
    _setup_font()
    output_dir.mkdir(parents=True, exist_ok=True)

    p = metrics.current_period
    fig = plt.figure(figsize=(22.0, 24.5), facecolor=BG)
    outer = GridSpec(
        6,
        1,
        height_ratios=[0.55, 0.95, 1.55, 3.15, 2.35, 0.28],
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
        0.0,
        0.55,
        f"NOVITA {p.end.month}月成本概览（截至{p.end.month}/{p.end.day}）",
        fontsize=36,
        fontweight="bold",
        color=ACCENT,
        va="center",
        transform=title_ax.transAxes,
    )
    title_ax.text(
        1.0,
        0.55,
        "源表口径已剔除异常消耗 / 金额按工作簿现有数据展示",
        fontsize=15,
        color=MUTED,
        ha="right",
        va="center",
        transform=title_ax.transAxes,
    )

    gs_kpi = outer[1].subgridspec(1, 4, wspace=0.06)
    for i, item in enumerate(metrics.overview):
        _draw_kpi(fig.add_subplot(gs_kpi[0, i]), item, metrics)

    _plot_detail_table(fig.add_subplot(outer[2]), metrics)
    _plot_main_trend(fig.add_subplot(outer[3]), metrics)
    _plot_ondemand_trend(fig.add_subplot(outer[4]), metrics)

    footer_ax = fig.add_subplot(outer[5])
    footer_ax.axis("off")
    footer_ax.set_facecolor(BG)
    footer_ax.text(
        0.0,
        0.65,
        f"口径说明：明细区间为 {_period_range_label(metrics)}；汇总数据按工作簿现有口径展示。",
        fontsize=12,
        color=MUTED,
        va="center",
        transform=footer_ax.transAxes,
    )
    footer_ax.text(
        0.0,
        0.15,
        "数据来源：NOVITA.xlsx",
        fontsize=12,
        color=MUTED,
        va="center",
        transform=footer_ax.transAxes,
    )
    footer_ax.text(
        1.0,
        0.15,
        f"金额单位：{UNIT}",
        fontsize=12,
        color=MUTED,
        ha="right",
        va="center",
        transform=footer_ax.transAxes,
    )

    path = output_dir / "novita_dashboard.png"
    fig.savefig(path, dpi=165, facecolor=fig.get_facecolor())
    plt.close(fig)
    return _flatten_png_to_rgb(path)


def _flatten_png_to_rgb(path: Path) -> Path:
    """飞书上传不认 RGBA 透明 PNG，压成不透明 RGB。"""
    from PIL import Image

    im = Image.open(path)
    if im.mode == "RGB":
        return path
    bg = Image.new("RGB", im.size, (12, 12, 10))
    rgba = im.convert("RGBA")
    bg.paste(rgba, mask=rgba.split()[-1])
    bg.save(path, "PNG", optimize=True)
    return path


def generate_all_charts(
    metrics: ReportMetrics,
    output_dir: Path,
    extra_notes: list[str] | None = None,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    return {"dashboard": plot_dashboard(metrics, output_dir, extra_notes)}
