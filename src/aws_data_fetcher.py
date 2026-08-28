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


def _normalize_footer_label(text: str) -> str:
    return text.replace("【", "").replace("】", "").replace(" ", "").replace("　", "")


def _is_total_column(name: str) -> bool:
    text = _normalize_footer_label(_norm(name))
    if not text:
        return False
    if "总消耗" in text or text in ("合计", "AWS合计"):
        return True
    if "总费用" in text:
        return True
    if text.upper().startswith("AWS") and ("总" in text or "TOTAL" in text.upper()):
        return True
    return False


def _is_billable_service(label: str) -> bool:
    return not _is_total_column(label)


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
                if _is_total_column(name):
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


def _footer_kind_and_col(row: list[Any]) -> tuple[str | None, int | None]:
    """扫描整行找表底标签（兼容合并单元格导致 A 列不在 row[0]）。"""
    for i, cell in enumerate(row):
        text = _normalize_footer_label(_norm(cell))
        if not text:
            continue
        kind = _summary_kind(text)
        if kind:
            return kind, i
    return None, None


def _footer_index_offset(
    row: list[Any],
    label_col: int | None,
    services: dict[str, dict[str, Any]],
    total_idx: int | None,
    date_idx: int,
) -> int:
    first_svc = min(meta["index"] for meta in services.values())
    if label_col is not None and label_col != date_idx:
        return label_col - date_idx

    numeric_cols: list[int] = []
    scan_from = 0 if label_col is None else (label_col + 1)
    for i in range(scan_from, len(row)):
        val = _parse_amount(row[i] if i < len(row) else "")
        if val == val and abs(val) > 1e-9:
            numeric_cols.append(i)
    if not numeric_cols:
        return 0
    if label_col is None and len(numeric_cols) >= 2 and total_idx is not None:
        # 合并单元格无标签时，行首第一个数通常是总费用，分项从第二个数起
        amount_col = numeric_cols[1]
    else:
        amount_col = numeric_cols[0]
        if total_idx is not None and amount_col == total_idx and len(numeric_cols) > 1:
            amount_col = numeric_cols[1]
    return amount_col - first_svc


def _footer_row_has_amounts(row: list[Any], services: dict[str, dict[str, Any]]) -> bool:
    first_svc = min(meta["index"] for meta in services.values())
    val = _parse_amount(row[first_svc] if first_svc < len(row) else "")
    return val == val and abs(val) > 1e-9


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

    def _row_month(row: list[Any]) -> int | None:
        month = None
        if month_idx is not None and month_idx < len(row):
            month = _valid_month(_parse_int(row[month_idx]))
        if month:
            return month
        for cell in row:
            m = MONTH_RE.search(_norm(cell))
            if m:
                return int(m.group(1))
        return last_month

    def _store_footer_row(row: list[Any], kind: str, month: int, label_col: int | None) -> None:
        offset = _footer_index_offset(row, label_col, services, total_idx, date_idx)
        block = result.setdefault(month, {})
        block[kind] = _amounts_from_service_row(
            row,
            services,
            as_rate=(kind == "rate"),
            total_idx=total_idx,
            index_offset=offset,
        )

    for row in raw_rows:
        if not row or all(_norm(c) == "" for c in row):
            continue
        month = _row_month(row)
        kind, label_col = _footer_kind_and_col(row)
        if month:
            last_month = month
        if kind is None or month is None:
            continue
        _store_footer_row(row, kind, month, label_col)

    # 兜底：第 35 行（index 34）按位置识别上月同期，即使 A 列合并单元格未返回值
    if len(raw_rows) >= 35:
        row35 = raw_rows[34]
        month = last_month
        if month is None:
            for row in raw_rows:
                m = _row_month(row)
                if m:
                    month = m
        if month and _footer_row_has_amounts(row35, services):
            block = result.setdefault(month, {})
            prev = block.get("previous") or {}
            prev_total = prev.get("total") if prev else 0
            if not prev or not prev_total or prev_total != prev_total:
                kind, label_col = _footer_kind_and_col(row35)
                if kind != "previous":
                    label_col = None
                _store_footer_row(row35, "previous", month, label_col)

    # 三行连续表底：当期 → 上月同期 → 环比率（不依赖行号）
    for i in range(len(raw_rows) - 2):
        r1, r2, r3 = raw_rows[i], raw_rows[i + 1], raw_rows[i + 2]
        k1, c1 = _footer_kind_and_col(r1)
        k2, c2 = _footer_kind_and_col(r2)
        k3, c3 = _footer_kind_and_col(r3)
        if k1 == "current" and k2 == "previous" and k3 == "rate":
            month = _row_month(r1) or _row_month(r2) or last_month
            if month:
                _store_footer_row(r1, "current", month, c1)
                _store_footer_row(r2, "previous", month, c2)
                _store_footer_row(r3, "rate", month, c3)
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
