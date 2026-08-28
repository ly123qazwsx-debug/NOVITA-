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
    _summary_kind,
    resolve_spreadsheet_token,
)
from .feishu_client import FeishuClient
from .report_date import parse_overview_period_end

DATE_RE = re.compile(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日")
SKIP_KEYWORDS = ("合计", "环比", "当期", "上月同期", "单位", "总消耗")
META_HEADERS = {"年", "月", "日期", "日", "单位: 美元", "单位：美元"}

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


def _find_aws_header(raw_rows: list[list[Any]]) -> tuple[int, list[str], dict[str, dict[str, Any]]]:
    for idx, row in enumerate(raw_rows[:15]):
        cells = [_norm(c) for c in row]
        joined = " ".join(cells)
        if ("RDS" in joined or "S3" in joined) and ("月" in joined or "日" in joined):
            services: dict[str, dict[str, Any]] = {}
            date_idx = 2
            total_idx = None
            for i, name in enumerate(cells):
                if not name:
                    continue
                if name in ("年",):
                    continue
                if name in ("月",):
                    continue
                if name in META_HEADERS or "单位" in name:
                    date_idx = i
                    continue
                if "总消耗" in name or name in ("合计", "AWS合计"):
                    total_idx = i
                    continue
                key = _service_key(name)
                if key in services:
                    key = f"{key}_{i}"
                services[key] = {"index": i, "label": name}
            if services:
                return idx, cells, services
    raise ValueError("未找到 AWS 表头行，请确认工作表包含 RDS / S3 等列")


def _amounts_from_service_row(
    row: list[Any],
    services: dict[str, dict[str, Any]],
    *,
    as_rate: bool = False,
    total_idx: int | None = None,
) -> dict[str, float]:
    parse = _parse_pct if as_rate else _parse_amount
    amounts: dict[str, float] = {}
    for key, meta in services.items():
        i = meta["index"]
        amounts[key] = parse(row[i] if i < len(row) else "")
    if total_idx is not None and total_idx < len(row):
        total = parse(row[total_idx])
    else:
        total = float("nan")
    if as_rate:
        amounts["total"] = total
        return amounts
    if total != total or abs(total) < 1e-9:
        total = sum(v for v in amounts.values() if v == v)
    amounts["total"] = total
    return amounts


def parse_aws_mom_summary(raw_rows: list[list[Any]], services: dict[str, dict[str, Any]], total_idx: int | None) -> dict:
    result: dict[int, dict[str, dict[str, float]]] = {}
    last_month: int | None = None
    date_idx = 2
    for row in raw_rows:
        if not row or all(_norm(c) == "" for c in row):
            continue
        month = _parse_int(row[1] if len(row) > 1 else "") or last_month
        kind, label_month = _row_summary_meta(row, {"date": date_idx})
        if label_month:
            month = label_month
        if month:
            last_month = month
        if kind is None or month is None:
            continue
        block = result.setdefault(month, {})
        block[kind] = _amounts_from_service_row(row, services, as_rate=(kind == "rate"), total_idx=total_idx)
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

    header_idx, header, services = _find_aws_header(raw_rows)
    total_idx = None
    for i, name in enumerate(header):
        if "总消耗" in name or name in ("合计", "AWS合计"):
            total_idx = i
            break

    labels = {key: meta["label"] for key, meta in services.items()}
    records: list[dict[str, Any]] = []
    last_year: int | None = None
    last_month: int | None = None

    for row in raw_rows[header_idx + 1 :]:
        if not row or all(_norm(c) == "" for c in row):
            continue

        year = _parse_int(row[0] if len(row) > 0 else "") or last_year
        month = _parse_int(row[1] if len(row) > 1 else "") or last_month
        if year:
            last_year = year
        if month:
            last_month = month

        date_cell = row[2] if len(row) > 2 else ""
        text = _norm(date_cell)
        if any(k in text for k in SKIP_KEYWORDS):
            continue
        date_val = _parse_cn_date(date_cell, year, month)
        if date_val is None:
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
    df.attrs["sheet_mom"] = parse_aws_mom_summary(raw_rows, services, total_idx)
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
