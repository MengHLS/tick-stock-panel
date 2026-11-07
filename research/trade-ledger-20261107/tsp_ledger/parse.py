"""交割单解析层：编码识别、脏值还原、事件分类、稳定去重键。

设计约束
--------
* 只读券商导出的 CSV，不改动源文件。
* 券商导出的字段是"定宽 + 前导等号包裹"的 Excel 友好格式，
  例如 ``= "603618      "``，必须还原成 ``603618``；否则按字符串比对会全部失配。
* 去重键必须稳定：同一文件重复导入不得产生新行，且同一事件在不同导出批次里
  （只要券商没改成交编号）也必须命中同一主键。
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

# ── 编码 ─────────────────────────────────────────────────────────────


def detect_encoding(raw: bytes) -> str:
    """按 BOM → UTF-8 → GB18030 顺序探测。

    GB18030 是 GBK 的超集，券商桌面导出多为 GBK/GB18030，
    用 GB18030 解码可覆盖生僻字而不改变常用字结果。
    """
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    try:
        raw.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass
    for enc in ("gb18030", "gbk"):
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    raise ValueError("无法识别交割单编码（已尝试 utf-8 / gb18030 / gbk）")


# ── 脏值还原 ─────────────────────────────────────────────────────────

_FORMULA_RE = re.compile(r'^=\s*"(.*)"\s*$', re.S)
_WS = " \t\r\n\u3000"


def clean_cell(value: Any) -> str:
    """还原 ``= "xxx      "`` 这类导出污染，并去掉定宽补空格。"""
    if value is None:
        return ""
    s = str(value)
    m = _FORMULA_RE.match(s.strip())
    if m:
        s = m.group(1)
    s = s.strip().strip('"').strip(_WS)
    if s in {"--", "-", "—", "None", "nan", "NaN"}:
        return ""
    return s


def to_float(value: Any, default: float = 0.0) -> float:
    s = clean_cell(value).replace(",", "")
    if s in {"", "--"}:
        return default
    try:
        return float(s)
    except ValueError:
        return default


def to_int(value: Any, default: int = 0) -> int:
    s = clean_cell(value).replace(",", "")
    if s == "":
        return default
    try:
        return int(float(s))
    except ValueError:
        return default


def normalize_code(value: Any) -> str:
    """6 位证券代码；非证券行（转账/利息）返回空串。"""
    s = clean_cell(value)
    if not s:
        return ""
    digits = re.sub(r"\D", "", s.split(".")[0])
    if len(digits) == 6:
        return digits
    return s  # 保留原始值便于人工核对，不擅自补零


# ── 事件分类 ─────────────────────────────────────────────────────────

CATEGORY = {
    "证券买入": "trade_buy",
    "证券卖出": "trade_sell",
    "银行转证券": "deposit_in",
    "证券转银行": "deposit_out",
    "台账间现金划转取": "internal_out",
    "台账间现金划转存": "internal_in",
    "配售缴款": "allocation_pay",
    "新股入账": "security_in",
    "红利入账": "dividend",
    "股息红利差异扣税": "dividend_tax",
    "利息归本": "interest",
    "投顾服务费扣收": "advisory_fee",
}

#: 计入"外部净入金"的类别
DEPOSIT_CATEGORIES = {"deposit_in", "deposit_out"}
#: 计入"其他损益"（非交易）的类别
OTHER_PNL_CATEGORIES = {"dividend", "dividend_tax", "interest", "advisory_fee"}

ETF_PREFIX = re.compile(r"^(15[0-9]\d{3}|16[0-9]\d{3}|5[0-8]\d{4})$")
BOND_PREFIX = re.compile(r"^(110|111|113|118|123|127|128|132)\d{3}$")
BOND_SUBSCRIBE_PREFIX = re.compile(r"^(07[0-9]\d{3}|37[0-9]\d{3}|71[0-9]\d{3}|75[0-9]\d{3})$")


def classify_kind(code: str) -> str:
    """证券类别。仅用于分桶统计，不参与盈亏计算。"""
    if not code:
        return ""
    if BOND_PREFIX.match(code):
        return "转债"
    if BOND_SUBSCRIBE_PREFIX.match(code):
        return "发债"
    if ETF_PREFIX.match(code):
        return "ETF"
    if re.match(r"^(60|68|00|30|43|83|87|92)\d{4}$", code):
        return "股票"
    return "其他"


@dataclass
class Event:
    """一条交割单事件（一行）。"""

    event_uid: str
    trade_date: str            # 发生日期；若券商留空则回落交收日期
    settle_date: str
    trade_time: str
    code: str
    name: str
    raw_type: str
    category: str
    qty: int
    price: float
    amount: float              # 成交金额
    cash: float                # 发生金额（已含费用）
    comm: float
    other_fee: float
    stamp: float
    transfer_fee: float
    shares_after: int
    cash_after: float
    deal_no: str
    holder: str
    serial: str
    market: str
    ccy: str
    kind: str = ""
    side: str = ""             # B / S / ''
    net_px: float = 0.0        # 含费单价
    row_no: int = 0
    date_from_settle: bool = False
    source_file: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def ts(self) -> str:
        return f"{self.trade_date} {self.trade_time or '00:00:00'}"

    def as_row(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d.pop("extra", None)
        return d


HEADER_ALIASES = {
    "交收日期": "settle_date",
    "发生日期": "trade_date",
    "发生时间": "trade_time",
    "证券代码": "code",
    "证券名称": "name",
    "交易类别": "raw_type",
    "成交数量": "qty",
    "成交均价": "price",
    "成交金额": "amount",
    "发生金额": "cash",
    "佣金": "comm",
    "其他费用": "other_fee",
    "印花税": "stamp",
    "过户费": "transfer_fee",
    "股份余额": "shares_after",
    "资金余额": "cash_after",
    "成交编号": "deal_no",
    "股东账号": "holder",
    "流水号": "serial",
    "交易市场": "market",
    "币种": "ccy",
}


def _build_uid(ev: dict[str, Any], raw_row: list[str]) -> str:
    """稳定去重键。

    优先 (发生日期, 发生时间, 成交编号)；转账/利息等无成交编号的行
    退化为整行规范化内容的哈希，保证同一文件重复导入恒定。
    """
    deal_no = ev["deal_no"]
    trade_date = ev["trade_date"] or ev["settle_date"]
    if deal_no and deal_no not in {"0"} and trade_date:
        return f"{trade_date}|{ev['trade_time']}|{deal_no}"
    digest = hashlib.sha1(
        "|".join(clean_cell(c) for c in raw_row).encode("utf-8")
    ).hexdigest()[:16]
    return f"{trade_date}|{ev['trade_time']}|h:{digest}"


@dataclass
class ParseResult:
    events: list[Event]
    encoding: str
    total_rows: int
    skipped_rows: int
    header: list[str]
    warnings: list[str] = field(default_factory=list)


def read_jiaogedan(path: str | Path) -> ParseResult:
    """读取券商交割单 CSV，返回结构化事件流（按发生时间升序）。"""
    p = Path(path)
    raw = p.read_bytes()
    enc = detect_encoding(raw)
    text = raw.decode(enc)
    if text and text[0] == "\ufeff":
        text = text[1:]
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise ValueError(f"{p} 为空文件")

    # 跳过表头前的空行
    idx = 0
    while idx < len(rows) and not any(clean_cell(c) for c in rows[idx]):
        idx += 1
    header = [clean_cell(c) for c in rows[idx]]
    col = {name: i for i, name in enumerate(header) if name}
    missing = [h for h in HEADER_ALIASES if h not in col]
    if missing:
        raise ValueError(f"交割单缺少必要列: {missing}; 实际表头: {header}")

    events: list[Event] = []
    skipped = 0
    warnings: list[str] = []
    for offset, row in enumerate(rows[idx + 1:], start=idx + 2):
        if not any(clean_cell(c) for c in row):
            skipped += 1
            continue
        ev = {key: clean_cell(row[col[h]]) if col[h] < len(row) else "" for h, key in HEADER_ALIASES.items()}
        raw_type = ev["raw_type"]
        category = CATEGORY.get(raw_type)
        if category is None:
            warnings.append(f"第 {offset} 行未知交易类别 {raw_type!r}，按 other 归类")
            category = "other"

        trade_date = ev["trade_date"] or ev["settle_date"]
        date_from_settle = not ev["trade_date"] and bool(ev["settle_date"])
        if date_from_settle:
            warnings.append(f"第 {offset} 行发生日期为空，回落交收日期 {ev['settle_date']}")

        code = normalize_code(ev["code"])
        qty = to_int(ev["qty"])
        amount = to_float(ev["amount"])
        cash = to_float(ev["cash"])

        if category in {"trade_buy", "trade_sell", "security_in", "allocation_pay"}:
            fees = to_float(ev["comm"]) + to_float(ev["other_fee"]) + to_float(ev["stamp"]) + to_float(ev["transfer_fee"])
            if qty:
                if category == "trade_sell":
                    net_px = (abs(amount) - fees) / qty
                elif category == "security_in":
                    net_px = 0.0
                else:
                    net_px = (abs(amount) + fees) / qty
            else:
                net_px = 0.0
        else:
            net_px = 0.0

        side = ""
        if category == "trade_buy":
            side = "B"
        elif category == "trade_sell":
            side = "S"
        elif category == "allocation_pay":
            side = "S"   # 缴款：现金流出，等价于买入成本（按币种 100 元/张）
        elif category == "security_in":
            side = "B"

        item = {
            "trade_date": trade_date,
            "settle_date": ev["settle_date"],
            "trade_time": ev["trade_time"],
            "code": code,
            "name": ev["name"],
            "raw_type": raw_type,
            "category": category,
            "qty": qty,
            "price": to_float(ev["price"]),
            "amount": amount,
            "cash": cash,
            "comm": to_float(ev["comm"]),
            "other_fee": to_float(ev["other_fee"]),
            "stamp": to_float(ev["stamp"]),
            "transfer_fee": to_float(ev["transfer_fee"]),
            "shares_after": to_int(ev["shares_after"]),
            "cash_after": to_float(ev["cash_after"]),
            "deal_no": ev["deal_no"],
            "holder": ev["holder"],
            "serial": ev["serial"],
            "market": ev["market"],
            "ccy": ev["ccy"],
        }
        uid = _build_uid(item, row)
        events.append(
            Event(
                event_uid=uid,
                kind=classify_kind(code),
                side=side,
                net_px=net_px,
                row_no=offset,
                date_from_settle=date_from_settle,
                source_file=str(p),
                **item,
            )
        )

    # 稳定排序：日期 → 时间 → 成交编号；同一秒内按成交编号升序（成交编号单调递增）
    events.sort(key=lambda e: (e.trade_date, e.trade_time, e.deal_no.zfill(20), -e.row_no))
    return ParseResult(
        events=events,
        encoding=enc,
        total_rows=len(rows) - (idx + 1),
        skipped_rows=skipped,
        header=header,
        warnings=warnings,
    )
