"""Broker statement CSV parsing for the trade-analysis extension."""
from __future__ import annotations

import csv
import hashlib
import io
import re
from datetime import UTC, datetime
from typing import Any

_CODE_RE = re.compile(r"(\d{6})")


class ImportError(ValueError):
    """The uploaded statement cannot be parsed safely."""


def _text(value: Any) -> str:
    return str(value or "").strip().strip('"')


def _number(value: Any, default: float = 0.0) -> float:
    text = _text(value).replace(",", "")
    if text in {"", "--", "-"}:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def _normalize_code(value: Any) -> str:
    text = _text(value).replace("=", "").replace('"', "").strip()
    match = _CODE_RE.fullmatch(text)
    return match.group(1) if match else ""


def _symbol(code: str) -> str:
    if code.startswith(("6", "5", "9")):
        return f"{code}.SH"
    if code.startswith(("4", "8")):
        return f"{code}.BJ"
    return f"{code}.SZ"


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "gb18030", "gbk", "utf-8"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ImportError("无法识别对账单编码，请导出 UTF-8 或 GBK 编码的 CSV")


def _header_index(headers: list[str]) -> dict[str, int]:
    normalized = {re.sub(r"\s+", "", _text(item)): index for index, item in enumerate(headers)}
    required = ("发生日期", "证券代码", "交易类别", "成交数量", "成交均价")
    missing = [name for name in required if name not in normalized]
    if missing:
        raise ImportError(f"对账单缺少必要列：{'、'.join(missing)}")
    return normalized


def parse_statement(raw: bytes, *, source_file: str = "") -> list[dict[str, Any]]:
    text = _decode(raw)
    reader = csv.reader(io.StringIO(text))
    try:
        headers = next(reader)
    except StopIteration as exc:
        raise ImportError("对账单为空") from exc
    index = _header_index(headers)

    def cell(row: list[str], name: str) -> str:
        position = index.get(name)
        return row[position] if position is not None and position < len(row) else ""

    imported_at = datetime.now(UTC).isoformat(timespec="seconds")
    rows: list[dict[str, Any]] = []
    for row in reader:
        if not row:
            continue
        raw_type = _text(cell(row, "交易类别"))
        if "买入" in raw_type:
            side = "B"
        elif "卖出" in raw_type:
            side = "S"
        else:
            continue
        code = _normalize_code(cell(row, "证券代码"))
        qty = int(_number(cell(row, "成交数量")))
        price = _number(cell(row, "成交均价"))
        if not code or qty <= 0 or price <= 0:
            continue

        trade_date = _text(cell(row, "发生日期")) or _text(cell(row, "交收日期"))
        trade_time = _text(cell(row, "发生时间")) or "00:00:00"
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", trade_date[:10]):
            continue
        trade_date = trade_date[:10]

        amount = _number(cell(row, "成交金额"))
        if amount <= 0:
            amount = qty * price
        cash_flow = _number(cell(row, "发生金额"))
        if cash_flow == 0:
            cash_flow = amount if side == "S" else -amount

        commission = abs(_number(cell(row, "佣金")))
        other_fee = abs(_number(cell(row, "其他费用")))
        stamp_tax = abs(_number(cell(row, "印花税")))
        transfer_fee = abs(_number(cell(row, "过户费")))
        deal_no = _text(cell(row, "成交编号"))
        cash_balance_text = _text(cell(row, "资金余额"))
        cash_balance = _number(cash_balance_text) if cash_balance_text not in {"", "--"} else None
        name = re.sub(r"\s+", " ", _text(cell(row, "证券名称")))

        identity = "|".join(
            (trade_date, trade_time, code, side, str(qty), f"{price:.4f}", f"{cash_flow:.4f}", deal_no)
        )
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
        rows.append({
            "id": f"{trade_date}-{digest}",
            "trade_date": trade_date,
            "trade_time": trade_time,
            "symbol": _symbol(code),
            "name": name,
            "side": side,
            "qty": qty,
            "price": price,
            "amount": amount,
            "cash_flow": cash_flow,
            "commission": commission,
            "other_fee": other_fee,
            "stamp_tax": stamp_tax,
            "transfer_fee": transfer_fee,
            "deal_no": deal_no,
            "cash_balance": cash_balance,
            "source_file": source_file,
            "imported_at": imported_at,
        })
    if not rows:
        raise ImportError("对账单中没有找到可用的买入/卖出记录")
    return rows
