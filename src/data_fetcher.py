"""从飞书 NOVITA 工作表拉取并标准化成本数据。"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

import pandas as pd

from .feishu_client import FeishuClient

COST_COLUMNS = ["llm", "sd", "gpu_ondemand", "gpu_storage", "gpu_fixed"]

# 兼容全角/半角括号、大小写
COLUMN_ALIASES: dict[str, list[str]] = {
    "year": ["年"],
    "month": ["月"],
    "date": ["单位: 美元", "单位：美元", "日期", "日"],
    "llm": ["LLM"],
    "sd": ["sd", "SD"],
    "gpu_ondemand": ["GPU (按需)", "GPU（按需）", "GPU(按需)"],
    "gpu_storage": ["GPU (按需存储)", "GPU（按需存储）", "GPU(按需存储)"],
    "gpu_fixed": ["GPU 固定", "GPU（固定）", "GPU固定", "GPU (固定)"],
}

# 表头未匹配时，按 NOVITA 表固定列序兜底：A年 B月 C日 D~H 五项成本
POSITIONAL_INDEX = {
    "year": 0,
    "month": 1,
    "date": 2,
    "llm": 3,
    "sd": 4,
    "gpu_ondemand": 5,
    "gpu_storage": 6,
    "gpu_fixed": 7,
}

SKIP_KEYWORDS = ("合计", "环比", "当期", "上月同期", "单位")
DATE_RE = re.compile(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日")
MONTH_RE = re.compile(r"(\d{1,2})\s*月")


def resolve_spreadsheet_token(client: FeishuClient, wiki_token: str) -> str:
    node = client.get_wiki_node(wiki_token)
    if node.get("obj_type") != "sheet":
        raise ValueError(f"Wiki 节点类型不是电子表格: {node.get('obj_type')}")
    return node["obj_token"]


def _norm(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _parse_amount(value: Any) -> float:
    if value is None or _norm(value) == "":
        return 0.0
    text = _norm(value).replace(",", "").replace("¥", "").replace("$", "").replace("USD", "")
    try:
        return float(text)
    except ValueError:
        return 0.0


def _parse_int(value: Any) -> int | None:
    if value is None or _norm(value) == "":
        return None
    text = _norm(value).replace(",", "")
    try:
        return int(float(text))
    except ValueError:
        return None


def _parse_cn_date(value: Any, year: int | None, month: int | None) -> date | None:
    if value is None or _norm(value) == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = _norm(value)
    if any(k in text for k in SKIP_KEYWORDS):
        return None

    match = DATE_RE.search(text)
    if match:
        m, d = int(match.group(1)), int(match.group(2))
        y = year or datetime.now().year
        try:
            return date(y, m, d)
        except ValueError:
            return None

    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def _find_header_row(raw_rows: list[list[Any]]) -> tuple[int, list[str]]:
    for idx, row in enumerate(raw_rows[:10]):
        cells = [_norm(c) for c in row]
        joined = " ".join(cells)
        if "LLM" in joined and ("sd" in joined.lower() or "GPU" in joined):
            return idx, cells
    return 0, [_norm(c) for c in raw_rows[0]]


def _resolve_col_index(header: list[str], field: str) -> int:
    aliases = COLUMN_ALIASES[field]
    for i, name in enumerate(header):
        if name in aliases:
            return i
    return POSITIONAL_INDEX[field]


def parse_novita_rows(raw_rows: list[list[Any]]) -> pd.DataFrame:
    """把 NOVITA 工作表原始二维数组解析为标准 DataFrame。"""
    if not raw_rows:
        raise ValueError("飞书表格返回空数据，请检查 range 配置")

    header_idx, header = _find_header_row(raw_rows)
    col_index = {field: _resolve_col_index(header, field) for field in POSITIONAL_INDEX}

    records: list[dict[str, Any]] = []
    last_year: int | None = None
    last_month: int | None = None

    for row in raw_rows[header_idx + 1 :]:
        if not row or all(_norm(c) == "" for c in row):
            continue

        def cell(field: str) -> Any:
            i = col_index[field]
            return row[i] if i < len(row) else ""

        year = _parse_int(cell("year")) or last_year
        month = _parse_int(cell("month")) or last_month
        if year:
            last_year = year
        if month:
            last_month = month

        date_val = _parse_cn_date(cell("date"), year, month)
        if date_val is None:
            continue

        record = {"date": date_val}
        for key in COST_COLUMNS:
            record[key] = _parse_amount(cell(key))
        records.append(record)

    if not records:
        raise ValueError("未解析到有效数据行，请检查 NOVITA 表结构")

    df = pd.DataFrame(records).drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
    df["total_with_fixed"] = df[COST_COLUMNS].sum(axis=1)
    df["total_ondemand"] = df[["llm", "sd", "gpu_ondemand", "gpu_storage"]].sum(axis=1)
    df.attrs["sheet_mom"] = parse_sheet_mom_summary(raw_rows)
    df.attrs["sheet_overrides"] = parse_sheet_overrides(raw_rows)
    df.attrs["sheet_overview"] = parse_sheet_overview_table(raw_rows)
    return df


def fetch_cost_data(client: FeishuClient, config: dict[str, Any]) -> pd.DataFrame:
    ds = config["data_source"]
    spreadsheet_token = resolve_spreadsheet_token(client, ds["wiki_token"])

    sheet_id = ds.get("sheet_id")
    sheet_name = ds.get("sheet_name")
    if sheet_name:
        sheet_id = client.find_sheet_id_by_title(spreadsheet_token, sheet_name)
    if not sheet_id:
        raise ValueError("请在 config 中配置 sheet_id 或 sheet_name")

    raw_rows = client.read_sheet_values(spreadsheet_token, sheet_id, ds.get("range") or "A1:Z400")
    df = parse_novita_rows(raw_rows)
    return df


def _parse_pct(value: Any) -> float:
    """表底/对比表环比率：支持 29%、-14%、以及飞书返回的 0.29 / -0.14。"""
    raw = _norm(value)
    has_pct = "%" in raw or "％" in raw
    text = raw.replace("%", "").replace("％", "").replace("+", "").replace(",", "")
    if text == "":
        return float("nan")
    try:
        number = float(text)
    except ValueError:
        return float("nan")
    if not has_pct and 0 < abs(number) <= 1:
        return number * 100
    return number


def _normalize_pct_rate(rate: float, current: float, previous: float) -> float:
    """把小数比例（0.08）规范为百分比（8），并与当期/上月金额交叉校验。"""
    if rate != rate:
        _, rate = _mom_from_amounts(current, previous)
        return rate
    if 0 < abs(rate) <= 1:
        rate = rate * 100
    computed, _ = _mom_from_amounts(current, previous)
    if previous > 0 and computed == computed and abs(rate - computed) > 2 and abs(computed) > 0.5:
        return computed
    return rate


def _mom_from_amounts(current: float, previous: float) -> tuple[float, float]:
    change = current - previous
    rate = (change / previous * 100) if previous else float("nan")
    return rate, change


def _summary_kind(label: str) -> str | None:
    text = label.replace(" ", "").replace("　", "")
    if "环比率" in text or ("环比" in text and "率" in text):
        return "rate"
    if text in ("上月同期", "上月同期合计", "上月同期合计值", "上月同期合计数据"):
        return "previous"
    if "上月同期" in text:
        return "previous"
    if text in ("当期合计", "当期合计值", "当月合计", "当月合计值"):
        return "current"
    if any(k in text for k in ("当期合计", "当月合计", "本期合计", "当期总计", "当月总计")):
        return "current"
    if ("当期" in text or "当月" in text or "本期" in text) and ("合计" in text or "总计" in text):
        return "current"
    if text in ("环比", "环比额", "环比金额"):
        return "change"
    if "环比" in text and "率" not in text:
        return "change"
    return None


def _row_summary_meta(row: list[Any], col_index: dict[str, int]) -> tuple[str | None, int | None, int | None]:
    """从整行扫描表底汇总标签（兼容合并单元格）。"""
    date_idx = col_index["date"]
    primary = _norm(row[date_idx] if date_idx < len(row) else "")
    kind = _summary_kind(primary)
    label = primary
    label_col_idx = date_idx if kind else None
    month_match = MONTH_RE.search(primary)
    if kind is None:
        for i, cell in enumerate(row):
            candidate = _norm(cell)
            if not candidate:
                continue
            kind = _summary_kind(candidate)
            if kind:
                label = candidate
                label_col_idx = i
                if not month_match:
                    month_match = MONTH_RE.search(candidate)
                break
    month = int(month_match.group(1)) if month_match else None
    return kind, month, label_col_idx


def _amounts_from_row(
    row: list[Any],
    col_index: dict[str, int],
    as_rate: bool = False,
    total_idx: int = 8,
) -> dict[str, float]:
    parse = _parse_pct if as_rate else _parse_amount
    amounts = {}
    for key in COST_COLUMNS:
        i = col_index[key]
        amounts[key] = parse(row[i] if i < len(row) else "")
    total = parse(row[total_idx] if len(row) > total_idx else "")
    if as_rate:
        amounts["total_with_fixed"] = total
        amounts["total_ondemand"] = float("nan")
        return amounts
    if total != total or abs(total) < 1e-9:
        total = sum(amounts[k] for k in COST_COLUMNS)
    amounts["total_with_fixed"] = total
    amounts["total_ondemand"] = (
        amounts["llm"] + amounts["sd"] + amounts["gpu_ondemand"] + amounts["gpu_storage"]
    )
    return amounts


def parse_sheet_mom_summary(raw_rows: list[list[Any]]) -> dict[int, dict[str, dict[str, float]]]:
    """读取各月表底「当期合计 / 上月同期 / 环比 / 环比率」，供分项环比用。"""
    if not raw_rows:
        return {}
    _, header = _find_header_row(raw_rows)
    col_index = {field: _resolve_col_index(header, field) for field in POSITIONAL_INDEX}
    total_idx = 8
    for i, name in enumerate(header):
        if "总消耗" in name:
            total_idx = i
            break
    result: dict[int, dict[str, dict[str, float]]] = {}
    last_month: int | None = None

    for row in raw_rows:
        if not row or all(_norm(c) == "" for c in row):
            continue
        month = _parse_int(row[1] if len(row) > 1 else "") or last_month
        kind, label_month, _ = _row_summary_meta(row, col_index)
        if label_month:
            month = label_month
        if month:
            last_month = month
        if kind is None or month is None:
            continue
        block = result.setdefault(month, {})
        block[kind] = _amounts_from_row(
            row, col_index, as_rate=(kind == "rate"), total_idx=total_idx
        )
    return result


ACTUAL_RE = re.compile(r"实际[^0-9]*([\d,]+(?:\.\d+)?)")


def _overview_row_key(label: str) -> str | None:
    text = label.replace(" ", "").replace("　", "")
    if "预计" in text and "消耗" in text:
        return "forecast"
    if "当月总消耗" in text:
        return "month_total"
    if "日消耗" in text and "含固定" in text:
        return "daily_with_fixed"
    if "日消耗" in text and "按需" in text:
        return "daily_ondemand"
    return None


def _overview_numbers(row: list[Any], start: int) -> list[float]:
    """标签后依次取当期、上月、环比增减额、环比率。"""
    values: list[float] = []
    for cell in row[start + 1 :]:
        text = _norm(cell)
        if text == "":
            continue
        if len(values) >= 3:
            values.append(_parse_pct(cell))
        elif "%" in text or "％" in text:
            values.append(_parse_pct(cell))
        else:
            values.append(_parse_amount(cell))
        if len(values) >= 4:
            break
    return values


def parse_sheet_overview_table(raw_rows: list[list[Any]]) -> dict[str, dict[str, float]]:
    """读取飞书表里的 NOVITA 对比表：8月 / 7月 / 环比 / 环比率。第一个板块用这里的 7 月数，不自行加总。"""
    result: dict[str, dict[str, float]] = {}
    if not raw_rows:
        return result
    year_hint = 2026
    for row in raw_rows:
        if not row:
            continue
        if row[0] not in (None, ""):
            y = _parse_int(row[0])
            if y:
                year_hint = y
        for i, cell in enumerate(row):
            label = _norm(cell)
            key = _overview_row_key(label)
            if not key:
                continue
            nums = _overview_numbers(row, i)
            if len(nums) < 3:
                continue
            current, previous, change = nums[0], nums[1], nums[2]
            rate = nums[3] if len(nums) > 3 else float("nan")
            result[key] = {
                "current": current,
                "previous": previous,
                "change": change,
                "rate": rate,
            }
            if key == "month_total":
                from .report_date import parse_overview_period_end

                period_end = parse_overview_period_end(label, year_hint)
                if period_end:
                    result["period_end"] = period_end
            break
    return result


def parse_sheet_overrides(raw_rows: list[list[Any]]) -> dict[str, float]:
    """读取表内「预计 / 实际」汇总，优先用表上的预计全月，而不是简单按日线性外推。"""
    overrides: dict[str, float] = {}
    for row in raw_rows:
        if not row:
            continue
        for i, cell in enumerate(row):
            label = _norm(cell).replace(" ", "").replace("　", "")
            if not label:
                continue
            same_cell = ACTUAL_RE.search(label)
            if same_cell and ("剔除" in label or "$" in _norm(cell) or "消耗" in label):
                try:
                    overrides.setdefault("actual", float(same_cell.group(1).replace(",", "")))
                except ValueError:
                    pass
            amount = _first_amount_after(row, i)
            if amount is None:
                continue
            if "预计" in label and ("消耗" in label or "全月" in label or label.endswith("预计")):
                overrides.setdefault("forecast", amount)
            elif "实际" in label:
                overrides.setdefault("actual", amount)
    return overrides


def _first_amount_after(row: list[Any], start: int) -> float | None:
    for cell in row[start + 1 : start + 6]:
        if _norm(cell) == "":
            continue
        amount = _parse_amount(cell)
        if amount > 100:
            return amount
    return None
