"""从飞书 AWS 工作表拉取并标准化成本数据。"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

import pandas as pd

from .data_fetcher import (
    MONTH_RE,
    _mom_from_amounts,
    _norm,
    _overview_numbers,
    _parse_amount,
    _parse_cn_date,
    _parse_int,
    _parse_pct,
    _row_summary_meta,
    resolve_spreadsheet_token,
)
from .feishu_client import FeishuClient
from .report_date import parse_overview_period_end

DATE_RE = re.compile(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日")
SKIP_KEYWORDS = ("合计", "环比", "当期", "上月同期", "单位", "总消耗")
META_HEADERS = {"年", "月", "日期", "日", "单位: 美元", "单位：美元"}


def _valid_year(value: int | None) -> int | None:
    if value is None or value < 2000 or value > 2100:
        return None
    return value


def _valid_month(value: int | None) -> int | None:
    if value is None or value < 1 or value > 12:
        return None
    return value


SERVICE_KEY_HINTS: list[tuple[str, str]] = [
    ("RDS", "rds"),
    ("S3", "s3"),
    ("ELB", "elb"),
    ("ECS", "ecs"),
    ("EC2-其他", "ec2_other"),
    ("EC2其他", "ec2_other"),
    ("EC2实例", "ec2_instance"),
    ("Amplify", "amplify"),
    ("CloudFront", "cloudfront"),
    ("Elasticache", "elasticache"),
    ("ElastiCache", "elasticache"),
    ("VPC", "vpc"),
]


def _service_key(label: str) -> str:
    compact = label.replace(" ", "").replace("　", "").replace("-", "").replace("_", "")
    compact_upper = compact.upper()
    if "ELASTIC" in compact_upper:
        return "elasticache"
    for hint, key in SERVICE_KEY_HINTS:
        hint_compact = hint.replace("-", "").replace("_", "").upper()
        if hint_compact in compact_upper or compact_upper.startswith(hint_compact):
            return key
    if compact_upper.startswith("EC2"):
        return "ec2_instance"
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "_", label.strip()).strip("_").lower()
    return slug or "service"


def _find_aws_header(
    raw_rows: list[list[Any]],
) -> tuple[int, list[str], dict[str, dict[str, Any]], dict[str, int | None]]:
    for idx, row in enumerate(raw_rows[:15]):
        cells = [_norm(c) for c in row]
        joined = " ".join(cells)
        if "RDS" in joined or "S3" in joined:
            services: dict[str, dict[str, Any]] = {}
            year_idx: int | None = None
            month_idx: int | None = None
            date_idx: int | None = None
            total_idx: int | None = None
            for i, name in enumerate(cells):
                if not name:
                    continue
                if name == "年":
                    year_idx = i
                    continue
                if name == "月":
                    month_idx = i
                    continue
                if name in ("日期", "日") or name in META_HEADERS or "单位" in name:
                    date_idx = i
                    continue
                if "总消耗" in name or name in ("合计", "AWS合计"):
                    total_idx = i
                    continue
                key = _service_key(name)
                if key in services:
                    key = f"{key}_{i}"
                services[key] = {"index": i, "label": name}
            if date_idx is None:
                for i, name in enumerate(cells):
                    if "月" in name or "日" in name:
                        date_idx = i
                        break
            if date_idx is None:
                date_idx = 0
            if services:
                layout = {
                    "year_idx": year_idx,
                    "month_idx": month_idx,
                    "date_idx": date_idx,
                    "total_idx": total_idx,
                }
                return idx, cells, services, layout
    raise ValueError("未找到 AWS 表头行，请确认工作表包含 RDS / S3 等列")


def _amounts_from_service_row(
    row: list[Any],
    services: dict[str, dict[str, Any]],
    *,
    as_rate: bool = False,
    total_idx: int | None = None,
    index_offset: int = 0,
) -> dict[str, float]:
    parse = _parse_pct if as_rate else _parse_amount
    amounts: dict[str, float] = {}
    for key, meta in services.items():
        i = meta["index"] + index_offset
        amounts[key] = parse(row[i] if i < len(row) else "")
    if total_idx is not None:
        total_col = total_idx + index_offset
        total = parse(row[total_col] if total_col < len(row) else "")
    else:
        total = float("nan")
    if as_rate:
        amounts["total"] = total
        return amounts
    if total != total or abs(total) < 1e-9:
        total = sum(v for v in amounts.values() if v == v)
    amounts["total"] = total
    return amounts


def parse_aws_mom_summary(
    raw_rows: list[list[Any]],
    services: dict[str, dict[str, Any]],
    layout: dict[str, int | None],
) -> dict:
    result: dict[int, dict[str, dict[str, float]]] = {}
    last_month: int | None = None
    date_idx = layout.get("date_idx") or 0
    month_idx = layout.get("month_idx")
    total_idx = layout.get("total_idx")
    for row in raw_rows:
        if not row or all(_norm(c) == "" for c in row):
            continue
        month = None
        if month_idx is not None and month_idx < len(row):
            month = _valid_month(_parse_int(row[month_idx]))
        month = month or last_month
        kind, label_month, label_col_idx = _row_summary_meta(row, {"date": date_idx})
        if label_month:
            month = label_month
        if month:
            last_month = month
        if kind is None or month is None:
            continue
        index_offset = 0
        if label_col_idx is not None and label_col_idx != date_idx:
            index_offset = label_col_idx - date_idx
        block = result.setdefault(month, {})
        block[kind] = _amounts_from_service_row(
            row,
            services,
            as_rate=(kind == "rate"),
            total_idx=total_idx,
            index_offset=index_offset,
        )
    return result


def _aws_overview_row_key(label: str) -> str | None:
    text = label.replace(" ", "").replace("　", "")
    if "预计" in text and "消耗" in text:
        return "forecast"
    if "当期总消耗" in text or "当月总消耗" in text:
        return "month_total"
    if "日消耗" in text and "含" not in text and "按需" not in text:
        return "daily_avg"
    return None


def parse_aws_overview_table(raw_rows: list[list[Any]]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    year_hint = datetime.now().year
    for row in raw_rows:
        if not row:
            continue
        if row[0] not in (None, ""):
            y = _valid_year(_parse_int(row[0]))
            if y:
                year_hint = y
        for i, cell in enumerate(row):
            label = _norm(cell)
            key = _aws_overview_row_key(label)
            if not key:
                continue
            nums = _overview_numbers(row, i)
            if len(nums) < 3:
                continue
            current, previous, change = nums[0], nums[1], nums[2]
            rate = nums[3] if len(nums) > 3 else float("nan")
            if previous > 0:
                computed, _ = _mom_from_amounts(current, previous)
                rate = computed
            result[key] = {"current": current, "previous": previous, "change": change, "rate": rate}
            if key == "month_total":
                period_end = parse_overview_period_end(label, year_hint)
                if period_end:
                    result["period_end"] = period_end
            break
    return result


def parse_aws_rows(raw_rows: list[list[Any]]) -> tuple[pd.DataFrame, dict[str, str]]:
    if not raw_rows:
        raise ValueError("飞书 AWS 表返回空数据")

    header_idx, header, services, layout = _find_aws_header(raw_rows)
    year_idx = layout.get("year_idx")
    month_idx = layout.get("month_idx")
    date_idx = layout.get("date_idx") or 0
    total_idx = layout.get("total_idx")

    labels = {key: meta["label"] for key, meta in services.items()}
    records: list[dict[str, Any]] = []
    last_year: int | None = None
    last_month: int | None = None
    default_year = datetime.now().year

    for row in raw_rows[header_idx + 1 :]:
        if not row or all(_norm(c) == "" for c in row):
            continue

        year = last_year
        month = last_month
        if year_idx is not None and year_idx < len(row):
            parsed_year = _valid_year(_parse_int(row[year_idx]))
            if parsed_year:
                year = parsed_year
                last_year = year
        if month_idx is not None and month_idx < len(row):
            parsed_month = _valid_month(_parse_int(row[month_idx]))
            if parsed_month:
                month = parsed_month
                last_month = month

        date_cell = row[date_idx] if date_idx < len(row) else ""
        text = _norm(date_cell)
        if any(k in text for k in SKIP_KEYWORDS):
            continue
        date_val = _parse_cn_date(date_cell, year or default_year, month)
        if date_val is None:
            continue
        if not _valid_year(date_val.year):
            continue

        record: dict[str, Any] = {"date": date_val}
        for key, meta in services.items():
            i = meta["index"]
            record[key] = _parse_amount(row[i] if i < len(row) else "")
        if total_idx is not None:
            record["total"] = _parse_amount(row[total_idx] if total_idx < len(row) else "")
        else:
            record["total"] = sum(record[k] for k in services)
        records.append(record)

    if not records:
        raise ValueError("未解析到 AWS 有效数据行")

    df = pd.DataFrame(records).drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
    df.attrs["service_labels"] = labels
    df.attrs["service_keys"] = list(services.keys())
    df.attrs["sheet_mom"] = parse_aws_mom_summary(raw_rows, services, layout)
    df.attrs["sheet_overview"] = parse_aws_overview_table(raw_rows)
    return df, labels


def fetch_aws_data(client: FeishuClient, config: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, str]]:
    ds = config.get("aws", {}).get("data_source") or config["data_source"]
    wiki_token = ds.get("wiki_token") or config["data_source"]["wiki_token"]
    spreadsheet_token = resolve_spreadsheet_token(client, wiki_token)

    sheet_id = ds.get("sheet_id")
    sheet_name = ds.get("sheet_name", "AWS")
    if sheet_name and not sheet_id:
        sheet_id = client.find_sheet_id_by_title(spreadsheet_token, sheet_name)
    if not sheet_id:
        raise ValueError("请在 config.aws.data_source 中配置 sheet_name 或 sheet_id")

    raw_rows = client.read_sheet_values(spreadsheet_token, sheet_id, ds.get("range") or "A1:Z400")
    return parse_aws_rows(raw_rows)
