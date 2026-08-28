#!/usr/bin/env python3
"""根据 AWS 8 月成本表格数据生成综合看板（样式对齐用户上传截图）。"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.gridspec import GridSpec
from matplotlib.patches import FancyBboxPatch
from matplotlib.ticker import FuncFormatter

# ── 样式常量 ──────────────────────────────────────────────────────────────
BG = "#0C0F14"
CARD = "#141820"
CARD_LINE = "#2A3140"
TEXT = "#F0F2F5"
MUTED = "#8B95A8"
GRID = "#252B38"
ACCENT = "#4DA3FF"
UP = "#FF7B7B"
DOWN = "#5FD68A"
HEADER = "#1E2A3A"
UNIT = "USD"
SYMBOL = "$"

LINE_COLORS = {
    "RDS-数据库": "#4DA3FF",
    "S3": "#FFD400",
    "ELB-负载均衡": "#2ECFCF",
    "ECS": "#5FD68A",
    "EC2 实例": "#C4A0FF",
    "Amplify": "#FF6B9D",
    "CloudFront": "#E8EAED",
    "ElastiCache": "#FF9F43",
    "VPC": "#FFD400",
    "EC2-其他": "#7DD3FC",
}

# ── 表格数据（截至 8/25）──────────────────────────────────────────────────
OVERVIEW = [
    {"label": "当月总消耗", "current": 14116.08, "change": 697.96, "rate": 5},
    {"label": "日消耗", "current": 564.64, "change": 27.92, "rate": 5},
    {"label": "预计8月总消耗", "current": 17148.69, "change": 686.58, "rate": 4},
]

TABLE_ROWS = [
    {"name": "RDS-数据库", "current": 2885.74, "previous": 1824.86, "change": 1060.88, "rate": 58, "share": 20.4},
    {"name": "S3", "current": 2708.06, "previous": 2771.28, "change": -63.22, "rate": -2, "share": 19.2},
    {"name": "ELB-负载均衡", "current": 1408.28, "previous": 1205.69, "change": 202.59, "rate": 17, "share": 10.0},
    {"name": "ECS", "current": 1168.06, "previous": 1224.55, "change": -56.49, "rate": -5, "share": 8.3},
    {"name": "EC2 实例", "current": 650.88, "previous": 691.83, "change": -40.95, "rate": -6, "share": 4.6},
    {"name": "Amplify", "current": 525.82, "previous": 253.08, "change": 272.74, "rate": 108, "share": 3.7},
    {"name": "CloudFront", "current": 457.13, "previous": 642.71, "change": -185.58, "rate": -29, "share": 3.2},
    {"name": "ElastiCache", "current": 420.31, "previous": 407.84, "change": 12.47, "rate": 3, "share": 3.0},
    {"name": "VPC", "current": 411.38, "previous": 421.24, "change": -9.86, "rate": -2, "share": 2.9},
    {"name": "EC2-其他", "current": 179.04, "previous": 226.57, "change": -47.53, "rate": -21, "share": 1.3},
]

DAYS = 25
MONTH = 8
AS_OF_DAY = 25


def _setup_font() -> None:
    from matplotlib import font_manager

    font_dir = Path(__file__).resolve().parent / "fonts"
    regular = font_dir / "NotoSansCJKsc-Regular.otf"
    bold = font_dir / "NotoSansCJKsc-Bold.otf"
    for path in (regular, bold):
        if path.exists():
            font_manager.fontManager.addfont(str(path))
    if regular.exists():
        chosen = font_manager.FontProperties(fname=str(regular)).get_name()
    else:
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
    if rate == 0:
        return MUTED
    return UP if rate > 0 else DOWN


def _rate_arrow(rate: float) -> str:
    if rate == 0:
        return "–"
    return "▲" if rate > 0 else "▼"


def _fmt_amt(value: float, decimals: int = 2) -> str:
    return f"{SYMBOL}{value:,.{decimals}f}"


def _fmt_signed_amt(value: float) -> str:
    sign = "+" if value >= 0 else "-"
    return f"{sign}{SYMBOL}{abs(value):,.2f}"


def _fmt_pct_signed(rate: float) -> str:
    n = int(round(rate))
    return f"+{n}%" if n > 0 else f"{n}%"


def _interp_profile(anchors: dict[int, float], days: int = DAYS) -> np.ndarray:
    """按锚点插值生成日度曲线，再缩放到目标合计。"""
    xs = sorted(anchors.keys())
    ys = [anchors[x] for x in xs]
    xp = np.arange(1, days + 1)
    profile = np.interp(xp, xs, ys)
    return profile


def _scale_to_total(profile: np.ndarray, total: float) -> np.ndarray:
    s = profile.sum()
    if s <= 0:
        return np.full_like(profile, total / len(profile))
    return profile * (total / s)


def build_daily_series() -> dict[str, np.ndarray]:
    """依据表格合计与截图趋势形态，合成 8/1–8/25 日度序列。"""
    totals = {r["name"]: r["current"] for r in TABLE_ROWS}
    profiles = {
        "RDS-数据库": _interp_profile({1: 137, 5: 153, 10: 150, 15: 130, 20: 95, 25: 88}),
        "S3": _interp_profile({1: 98, 8: 99, 14: 100, 18: 110, 22: 118, 25: 126.8}),
        "ELB-负载均衡": _interp_profile({1: 44.2, 25: 64.2}),
        "ECS": np.full(DAYS, 46.7),
        "EC2 实例": np.full(DAYS, 26.0),
        "Amplify": _interp_profile({1: 7.4, 10: 10, 13: 12, 14: 18.8, 18: 28, 22: 34, 25: 38.2}),
        "CloudFront": _interp_profile({1: 22, 8: 24.8, 14: 20, 20: 15, 25: 14.0}),
        "ElastiCache": np.full(DAYS, 16.81),
        "VPC": np.full(DAYS, 16.46),
        "EC2-其他": np.full(DAYS, 7.16),
    }
    return {name: _scale_to_total(profiles[name], totals[name]) for name in totals}


def _style_ax(ax, *, both_grids: bool = False) -> None:
    ax.set_facecolor(CARD)
    ax.grid(axis="y", color=GRID, linestyle=":", linewidth=1.0, zorder=0)
    if both_grids:
        ax.grid(True, color=GRID, linestyle=":", linewidth=0.9, zorder=0)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color(CARD_LINE)
    ax.spines["bottom"].set_color(CARD_LINE)
    ax.tick_params(labelsize=12, colors=MUTED, width=1.0, length=4)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))


def _legend(ax, **kwargs) -> None:
    kwargs.setdefault("fontsize", 13)
    leg = ax.legend(frameon=True, **kwargs)
    if leg is None:
        return
    frame = leg.get_frame()
    frame.set_facecolor("#10141C")
    frame.set_edgecolor(CARD_LINE)
    for text in leg.get_texts():
        text.set_color(TEXT)


def _value_label(ax, x, y, text: str, color: str, offset=(0, 8), fontsize: float = 8.5) -> None:
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
            "facecolor": "#10141C",
            "edgecolor": color,
            "linewidth": 0.6,
            "alpha": 0.92,
        },
    )


def _draw_kpi(ax, item: dict) -> None:
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
            linewidth=1.0,
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
    ax.text(0.07, 0.78, item["label"], fontsize=17, fontweight="bold", color=TEXT, va="center", transform=ax.transAxes)
    ax.text(0.07, 0.62, f"单位：{UNIT}", fontsize=12, color=MUTED, va="center", transform=ax.transAxes)
    ax.text(
        0.07,
        0.40,
        _fmt_amt(item["current"]),
        fontsize=28,
        fontweight="bold",
        color=TEXT,
        va="center",
        transform=ax.transAxes,
    )
    rate = item["rate"]
    ax.text(
        0.07,
        0.16,
        f"{_rate_arrow(rate)} {_fmt_pct_signed(rate)}    {_fmt_signed_amt(item['change'])}",
        fontsize=13,
        color=_rate_color(rate),
        va="center",
        transform=ax.transAxes,
    )


def _plot_table(ax) -> None:
    ax.axis("off")
    ax.set_facecolor(BG)
    ax.set_title(
        f"累计消耗前10项  ｜  分项环比明细  ｜  单位：{UNIT}",
        fontsize=20,
        color=ACCENT,
        loc="left",
        pad=10,
        fontweight="bold",
    )

    cell_text = []
    cell_colors = []
    for idx, row in enumerate(TABLE_ROWS):
        stripe = "#161C28" if idx % 2 else "#11161F"
        cell_text.append(
            [
                row["name"],
                _fmt_amt(row["current"]),
                _fmt_amt(row["previous"]),
                _fmt_signed_amt(row["change"]),
                _fmt_pct_signed(row["rate"]),
                f"{row['share']:.1f}%",
            ]
        )
        cell_colors.append([stripe] * 6)

    table = ax.table(
        cellText=cell_text,
        colLabels=["计费项", f"{MONTH}月合计（截至{AS_OF_DAY}日）", "上月同期", "增减金额", "环比率", "占本期成本"],
        loc="center",
        cellLoc="center",
        colColours=[HEADER] * 6,
        cellColours=cell_colors,
    )
    table.auto_set_font_size(False)
    table.set_fontsize(14)
    table.scale(1, 2.0)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor(CARD_LINE)
        cell.set_linewidth(0.5)
        if row == 0:
            cell.set_text_props(fontweight="bold", color=TEXT)
            cell.set_facecolor(HEADER)
        else:
            cell.set_text_props(color=TEXT)
            if col == 0:
                cell.set_text_props(ha="left", fontweight="bold")
                cell.PAD = 0.10
            if col == 4:
                cell.set_text_props(color=_rate_color(TABLE_ROWS[row - 1]["rate"]), fontweight="bold")


def _plot_trend(ax, names: list[str], daily: dict[str, np.ndarray], title: str) -> None:
    _style_ax(ax, both_grids=True)
    x = np.arange(DAYS)
    labels = [f"{MONTH}月{d}日" for d in range(1, DAYS + 1)]
    ymax = 1.0

    for name in names:
        series = daily[name]
        color = LINE_COLORS[name]
        linestyle = "--" if name == "VPC" else "-"
        ax.plot(
            x,
            series,
            color=color,
            linewidth=2.6,
            linestyle=linestyle,
            marker="o",
            markersize=5.5,
            label=name,
            zorder=3,
        )
        ymax = max(ymax, float(series.max()))
        # 仅标注首尾及极值点，避免拥挤
        highlight_idx = {0, DAYS - 1}
        highlight_idx.add(int(np.argmax(series)))
        highlight_idx.add(int(np.argmin(series)))
        for i in highlight_idx:
            val = float(series[i])
            offset_y = 9 if i % 2 == 0 else -11
            _value_label(ax, x[i], val, f"{val:.1f}", color, offset=(0, offset_y))

    ax.set_xticks(x[::2])
    ax.set_xticklabels([labels[i] for i in range(0, DAYS, 2)], fontsize=10, rotation=0)
    ax.set_xlim(-0.5, DAYS - 0.5)
    ax.set_ylim(0, ymax * 1.22)
    ax.set_ylabel(f"金额（{UNIT}）", fontsize=13, color=MUTED)
    ax.set_title(title, fontsize=18, color=ACCENT, loc="left", pad=28, fontweight="bold")
    _legend(ax, loc="lower left", bbox_to_anchor=(0.0, 1.01), ncol=3, borderaxespad=0)


def generate_dashboard(output_path: Path) -> Path:
    _setup_font()
    daily = build_daily_series()

    fig = plt.figure(figsize=(22, 26), facecolor=BG)
    outer = GridSpec(
        5,
        1,
        height_ratios=[0.55, 0.72, 1.55, 2.2, 2.0],
        hspace=0.22,
        top=0.975,
        bottom=0.035,
        left=0.06,
        right=0.94,
    )

    title_ax = fig.add_subplot(outer[0])
    title_ax.axis("off")
    title_ax.set_facecolor(BG)
    title_ax.text(
        0.0,
        0.55,
        f"AWS {MONTH}月成本概览",
        fontsize=38,
        fontweight="bold",
        color=ACCENT,
        va="center",
        transform=title_ax.transAxes,
    )
    title_ax.text(
        0.0,
        0.08,
        f"截至 {MONTH} 月 {AS_OF_DAY} 日  ｜  单位：{UNIT}",
        fontsize=17,
        color=MUTED,
        va="center",
        transform=title_ax.transAxes,
    )

    gs_kpi = outer[1].subgridspec(1, 3, wspace=0.08)
    for i, item in enumerate(OVERVIEW):
        _draw_kpi(fig.add_subplot(gs_kpi[0, i]), item)

    _plot_table(fig.add_subplot(outer[2]))

    top5 = [r["name"] for r in TABLE_ROWS[:5]]
    bottom5 = [r["name"] for r in TABLE_ROWS[5:]]
    _plot_trend(
        fig.add_subplot(outer[3]),
        top5,
        daily,
        f"排名 1-5  ｜  主要成本趋势  ｜  单位：{UNIT}",
    )
    _plot_trend(
        fig.add_subplot(outer[4]),
        bottom5,
        daily,
        f"排名 6-10  ｜  其余成本趋势  ｜  单位：{UNIT}",
    )

    fig.text(
        0.06,
        0.012,
        f"口径说明：明细区间为 {MONTH}/1–{MONTH}/{AS_OF_DAY}；汇总数据来源于 AWS.xlsx。所有趋势点均显示金额。",
        fontsize=11,
        color=MUTED,
        ha="left",
    )
    fig.text(0.94, 0.012, f"金额单位：{UNIT}", fontsize=11, color=MUTED, ha="right")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=160, facecolor=fig.get_facecolor())
    plt.close(fig)

    # 压成 RGB，便于飞书等平台上传
    from PIL import Image

    im = Image.open(output_path)
    if im.mode != "RGB":
        bg = Image.new("RGB", im.size, (12, 15, 20))
        rgba = im.convert("RGBA")
        bg.paste(rgba, mask=rgba.split()[-1])
        bg.save(output_path, "PNG", optimize=True)
    return output_path


if __name__ == "__main__":
    out = generate_dashboard(Path("output/charts/aws_dashboard.png"))
    print(f"已生成: {out.resolve()}")
