"""生成可视化图表。"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from .data_fetcher import COST_COLUMNS
from .metrics import CATEGORY_LABELS, ReportMetrics

# 中文字体回退
plt.rcParams["font.sans-serif"] = ["Noto Sans CJK SC", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
sns.set_theme(style="whitegrid", font="Noto Sans CJK SC")


def _money(x: float, symbol: str) -> str:
    return f"{symbol}{x:,.2f}"


def plot_daily_trend(metrics: ReportMetrics, output_dir: Path) -> Path:
    df = metrics.trend_df.copy()
    df["date_str"] = df["date"].astype(str)

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(df["date"], df["total_with_fixed"], marker="o", linewidth=2, label="日消耗（含固定 GPU）")
    ax.plot(df["date"], df["total_ondemand"], marker="s", linewidth=2, label="日消耗（按需计费）")
    ax.set_title("当月日消耗趋势", fontsize=14, fontweight="bold")
    ax.set_xlabel("日期")
    ax.set_ylabel(f"金额 ({metrics.currency})")
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()

    path = output_dir / "daily_trend.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def plot_category_stacked(metrics: ReportMetrics, output_dir: Path) -> Path:
    df = metrics.trend_df.copy()
    labels = [CATEGORY_LABELS[c] for c in COST_COLUMNS]

    fig, ax = plt.subplots(figsize=(12, 5))
    bottom = pd.Series([0.0] * len(df))
    colors = sns.color_palette("Set2", n_colors=len(COST_COLUMNS))

    for idx, col in enumerate(COST_COLUMNS):
        ax.bar(df["date"], df[col], bottom=bottom, label=labels[idx], color=colors[idx], width=0.8)
        bottom = bottom + df[col].values

    ax.set_title("分项每日消耗（堆叠）", fontsize=14, fontweight="bold")
    ax.set_xlabel("日期")
    ax.set_ylabel(f"金额 ({metrics.currency})")
    ax.legend(loc="upper left", fontsize=9)
    fig.autofmt_xdate()
    fig.tight_layout()

    path = output_dir / "category_stacked.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def plot_category_lines(metrics: ReportMetrics, output_dir: Path) -> Path:
    df = metrics.trend_df.copy()

    fig, ax = plt.subplots(figsize=(12, 5))
    for col in COST_COLUMNS:
        ax.plot(df["date"], df[col], marker="o", linewidth=1.8, label=CATEGORY_LABELS[col])

    ax.set_title("各分项每日消耗趋势", fontsize=14, fontweight="bold")
    ax.set_xlabel("日期")
    ax.set_ylabel(f"金额 ({metrics.currency})")
    ax.legend(loc="upper left", fontsize=9)
    fig.autofmt_xdate()
    fig.tight_layout()

    path = output_dir / "category_lines.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def plot_mom_comparison(metrics: ReportMetrics, output_dir: Path) -> Path:
    keys = COST_COLUMNS
    labels = [CATEGORY_LABELS[k] for k in keys]
    current = [metrics.mom_changes[k]["current"] for k in keys]
    previous = [metrics.mom_changes[k]["previous"] for k in keys]

    x = range(len(keys))
    width = 0.35
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.bar([i - width / 2 for i in x], current, width, label="当月同期", color="#4C78A8")
    ax.bar([i + width / 2 for i in x], previous, width, label="上月同期", color="#BAB0AC")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=15, ha="right")
    ax.set_title("分项消耗：当月同期 vs 上月同期", fontsize=14, fontweight="bold")
    ax.set_ylabel(f"金额 ({metrics.currency})")
    ax.legend()
    fig.tight_layout()

    path = output_dir / "mom_comparison.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def plot_mom_rate(metrics: ReportMetrics, output_dir: Path) -> Path:
    keys = COST_COLUMNS
    labels = [CATEGORY_LABELS[k] for k in keys]
    rates = [metrics.mom_changes[k]["rate"] for k in keys]
    colors = ["#E45756" if (r == r and r > 0) else "#54A24B" for r in rates]

    fig, ax = plt.subplots(figsize=(10, 4))
    bars = ax.barh(labels, [0 if r != r else r for r in rates], color=colors)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_title("分项环比率", fontsize=14, fontweight="bold")
    ax.set_xlabel("环比率 (%)")

    for bar, rate in zip(bars, rates):
        if rate != rate:
            text = "N/A"
        else:
            text = f"{rate:+.1f}%"
        ax.text(bar.get_width(), bar.get_y() + bar.get_height() / 2, f"  {text}", va="center")

    fig.tight_layout()
    path = output_dir / "mom_rate.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def generate_all_charts(metrics: ReportMetrics, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    return {
        "daily_trend": plot_daily_trend(metrics, output_dir),
        "category_stacked": plot_category_stacked(metrics, output_dir),
        "category_lines": plot_category_lines(metrics, output_dir),
        "mom_comparison": plot_mom_comparison(metrics, output_dir),
        "mom_rate": plot_mom_rate(metrics, output_dir),
    }
