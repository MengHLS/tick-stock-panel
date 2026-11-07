"""离线模拟盘复盘；只消费调用方导出的 binding/orders/fills，不执行策略或撮合。"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _qty(value):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("数量必须为正整数股数")
    return value


def _validate(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("binding"), dict):
        raise TypeError("需要 binding 对象")
    for name in ("orders", "fills"):
        if not isinstance(payload.get(name), list) or any(
            not isinstance(row, dict) for row in payload[name]
        ):
            raise ValueError(f"需要 {name} 对象列表")
    events = payload["binding"].get("events", [])
    if not isinstance(events, list) or any(not isinstance(row, dict) for row in events):
        raise ValueError("events 必须为对象列表")
    ids = set()
    for order in payload["orders"]:
        oid = order.get("id")
        if not isinstance(oid, str) or not oid or oid in ids:
            raise ValueError("订单 ID 缺失或重复")
        ids.add(oid)
        if order.get("status") not in {"pending", "filled", "cancelled", "expired"}:
            raise ValueError("未知订单状态")
        if order.get("side") not in {"buy", "sell"} or not order.get("symbol"):
            raise ValueError("订单缺少证券或方向")
        _qty(order.get("qty"))
    for fill in payload["fills"]:
        if fill.get("kind") == "fill":
            _qty(fill.get("qty"))


def capture(payload: dict) -> dict:
    """保留全部原始导出字段，隔离调用方后续修改；拒绝 NaN 等非 JSON 数值。"""
    payload = json.loads(canonical(deepcopy(payload)))
    _validate(payload)
    return {"schema_version": 1, "input_sha256": digest(payload), "payload": payload}


def reconcile(snapshot: dict) -> dict:
    if not isinstance(snapshot, dict):
        raise TypeError("快照必须为对象")
    if snapshot.get("schema_version") != 1:
        raise ValueError("不支持的复盘快照版本")
    payload = deepcopy(snapshot["payload"])
    if digest(payload) != snapshot.get("input_sha256"):
        raise ValueError("复盘输入校验失败")
    _validate(payload)
    orders = {row["id"]: row for row in payload["orders"]}
    totals = {oid: 0 for oid in orders}
    issues, seen = [], set()
    for fill in payload["fills"]:
        if fill.get("kind") != "fill":
            continue  # 分红/送股等台账事件不是模拟成交。
        fingerprint = digest(fill)
        if fingerprint in seen:
            issues.append({"code": "duplicate_fill", "order_id": fill.get("order_id")})
            continue
        seen.add(fingerprint)
        oid = fill.get("order_id")
        if oid not in orders:
            issues.append({"code": "orphan_fill", "order_id": oid})
            continue
        order = orders[oid]
        if any(fill.get(key) != order.get(key) for key in ("symbol", "side", "asset_type")):
            issues.append({"code": "fill_identity_mismatch", "order_id": oid})
            continue
        totals[oid] += fill["qty"]
    rows = []
    for oid, order in orders.items():
        actual = totals[oid]
        expected = order["qty"] if order["status"] == "filled" else 0
        if actual != expected:
            issues.append({"code": "order_ledger_mismatch", "order_id": oid})
        rows.append({
            "order_id": oid, "symbol": order["symbol"], "side": order["side"],
            "status": order["status"], "ordered_qty": order["qty"],
            "simulated_fill_qty": actual, "expected_fill_qty": expected,
            "fill_difference_qty": actual - expected,
            "reason": order.get("reason"),
        })
    events = []
    for index, event in enumerate(payload["binding"].get("events", [])):
        oid = event.get("order_id")
        state = "unsubmitted_unknown"
        if oid:
            state = "linked" if oid in orders else "missing_order"
            if oid not in orders:
                issues.append({"code": "event_order_missing", "event_index": index})
            elif any(event.get(key) != orders[oid].get(key) for key in ("symbol", "side")):
                state = "identity_mismatch"
                issues.append({"code": "event_identity_mismatch", "event_index": index})
        events.append({"event_index": index, "order_id": oid, "state": state,
                       "planned_qty": None, "message": event.get("message")})
    return {
        "schema_version": 1, "input_sha256": snapshot["input_sha256"],
        "scope": "single_account_export_all_records",
        "ledger_consistent": not issues, "plan_reconciled": False,
        "limitations": ["事件仅保留最近100条，完整历史计划未知",
                        "旧事件未保存请求数量，无订单不能判定为拒单",
                        "调用方负责同一账户一致性读取；快照固定导出内容，不证明采集原子性"],
        "orders": rows, "events": events, "issues": issues,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("capture", "replay"))
    parser.add_argument("input", help="调用方导出的 JSON 或冻结快照")
    args = parser.parse_args(argv)
    try:
        raw = json.loads(Path(args.input).read_text(encoding="utf-8-sig"))
        result = capture(raw) if args.mode == "capture" else reconcile(raw)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"复盘失败: {type(exc).__name__}", file=sys.stderr)
        return 2
    print(canonical(result))
    return 1 if args.mode == "replay" and result["issues"] else 0


if __name__ == "__main__":
    # Windows 重定向默认编码可能改变中文输入，破坏保存后快照的内容指纹。
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
