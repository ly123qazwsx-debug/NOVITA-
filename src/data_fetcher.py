"""从飞书 NOVITA 工作表拉取并标准化成本数据。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from .feishu_client import FeishuClient

COST_COLUMNS = ["llm", "sd", "gpu_ondemand", "gpu_storage", "gpu_fixed"]


def resolve_spreadsheet_token(client: FeishuClient, wiki_token: str) -> str:
    node = client.get_wiki_node(wiki_token)
    if node.get("obj_type") != "sheet":
        raise ValueError(f"Wiki 节点类型不是电子表格: {node.get('obj_type')}")
    return node["obj_token"]


def _parse_date(value: Any) -> datetime | None:
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime()


def _parse_amount(value: Any) -> float:
    if value is None or str(value).strip() == "":
        return 0.0
    text = str(value).replace(",", "").replace("¥", "").replace("$", "").strip()
    try:
        return float(text)
    except ValueError:
        return 0.0


def fetch_cost_data(client: FeishuClient, config: dict[str, Any]) -> pd.DataFrame:
    ds = config["data_source"]
    cols = config["columns"]

    spreadsheet_token = resolve_spreadsheet_token(client, ds["wiki_token"])

    sheet_id = ds.get("sheet_id")
    sheet_name = ds.get("sheet_name")
    if sheet_name:
        sheet_id = client.find_sheet_id_by_title(spreadsheet_token, sheet_name)
    if not sheet_id:
        raise ValueError("请在 config 中配置 sheet_id 或 sheet_name")

    raw_rows = client.read_sheet_values(spreadsheet_token, sheet_id, ds["range"])
    if not raw_rows:
        raise ValueError("飞书表格返回空数据，请检查 range 配置")

    header = [str(c).strip() for c in raw_rows[0]]
    records: list[dict[str, Any]] = []

    for row in raw_rows[1:]:
        if not row or all(str(c).strip() == "" for c in row):
            continue
        row_map = {header[i]: row[i] if i < len(row) else "" for i in range(len(header))}
        date_val = _parse_date(row_map.get(cols["date"]))
        if date_val is None:
            continue
        record = {"date": date_val.date()}
        for key in COST_COLUMNS:
            record[key] = _parse_amount(row_map.get(cols[key], 0))
        records.append(record)

    if not records:
        raise ValueError("未解析到有效数据行，请检查列名映射是否与表格一致")

    df = pd.DataFrame(records).sort_values("date").reset_index(drop=True)
    df["total_with_fixed"] = df[COST_COLUMNS].sum(axis=1)
    df["total_ondemand"] = df[["llm", "sd", "gpu_ondemand", "gpu_storage"]].sum(axis=1)
    return df
