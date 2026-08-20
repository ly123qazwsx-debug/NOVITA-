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

    raw_rows = client.read_sheet_values(spreadsheet_token, sheet_id, ds["range"])
    return parse_novita_rows(raw_rows)
