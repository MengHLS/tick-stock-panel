"""固定合成样本验证；不读取或修改用户模拟账户。"""
from copy import deepcopy

import pytest
from review_reconciliation import capture, main, reconcile


def sample(status="filled"):
    order = {"id": "order_1", "symbol": "000001.SZ", "side": "buy", "qty": 100,
             "asset_type": "stock", "status": status, "reason": None}
    fill = {"order_id": "order_1", "kind": "fill", "symbol": "000001.SZ",
            "side": "buy", "asset_type": "stock", "qty": 100, "price": 10., "seq": 1}
    return {"binding": {"revision": "synthetic", "snapshot": {"params": {"x": 1}},
                        "events": [{"order_id": "order_1", "symbol": "000001.SZ",
                                    "side": "buy", "message": "已提交委托"}]},
            "orders": [order], "fills": [fill] if status == "filled" else []}


def test_capture_is_stable_and_detached():
    data = sample()
    snapshot = capture(data)
    assert capture(dict(reversed(list(data.items())))) == snapshot
    data["binding"]["snapshot"]["params"]["x"] = 2
    assert capture(data)["input_sha256"] != snapshot["input_sha256"]
    assert snapshot["payload"]["binding"]["snapshot"]["params"]["x"] == 1
    first = reconcile(snapshot)
    first["orders"].clear()
    assert len(reconcile(snapshot)["orders"]) == 1


def test_filled_requires_matching_ledger():
    data = sample()
    report = reconcile(capture(data))
    assert report["ledger_consistent"]
    assert not report["plan_reconciled"]
    assert report["orders"][0]["simulated_fill_qty"] == 100
    data["fills"] = []
    report = reconcile(capture(data))
    assert not report["ledger_consistent"]
    assert report["orders"][0]["fill_difference_qty"] == -100


@pytest.mark.parametrize("status", ["pending", "cancelled", "expired"])
def test_nonfilled_is_not_rejection_or_fill(status):
    data = sample(status)
    data["orders"][0]["reason"] = "合成状态原因"
    report = reconcile(capture(data))
    assert report["ledger_consistent"]
    assert report["orders"][0]["status"] == status
    assert report["orders"][0]["simulated_fill_qty"] == 0


def test_repeated_symbol_does_not_cross_link():
    data = sample()
    second = {**data["orders"][0], "id": "order_2", "status": "pending"}
    data["orders"].append(second)
    report = reconcile(capture(data))
    assert [row["simulated_fill_qty"] for row in report["orders"]] == [100, 0]


@pytest.mark.parametrize("change,code", [
    ({"order_id": "missing"}, "orphan_fill"),
    ({"side": "sell"}, "fill_identity_mismatch"),
    ({"symbol": "000002.SZ"}, "fill_identity_mismatch"),
    ({"qty": 200}, "order_ledger_mismatch"),
])
def test_corrupt_fill_is_visible(change, code):
    data = sample()
    data["fills"][0].update(change)
    report = reconcile(capture(data))
    assert code in {issue["code"] for issue in report["issues"]}
    assert not report["ledger_consistent"]


def test_duplicate_fill_not_double_counted():
    data = sample()
    data["fills"].append(deepcopy(data["fills"][0]))
    report = reconcile(capture(data))
    assert report["orders"][0]["simulated_fill_qty"] == 100
    assert report["issues"] == [{"code": "duplicate_fill", "order_id": "order_1"}]


def test_legacy_event_without_order_is_unknown():
    data = sample()
    data["binding"]["events"] += [{"message": "预算不足一手，未下单", "order_id": None},
                                 {"message": "资金不足", "order_id": None}]
    report = reconcile(capture(data))
    assert all(row["state"] == "unsubmitted_unknown" for row in report["events"][1:])
    assert all(row["planned_qty"] is None for row in report["events"])


@pytest.mark.parametrize("event,code", [
    ({"order_id": "missing"}, "event_order_missing"),
    ({"order_id": "order_1", "side": "sell", "symbol": "000001.SZ"},
     "event_identity_mismatch"),
])
def test_event_identity(event, code):
    data = sample()
    data["binding"]["events"] = [event]
    assert reconcile(capture(data))["issues"][0]["code"] == code


def test_nonfill_ledger_event_not_counted():
    data = sample()
    data["fills"].append({"kind": "dividend", "amount": 123})
    assert reconcile(capture(data))["orders"][0]["simulated_fill_qty"] == 100


@pytest.mark.parametrize("qty", [0, -100, True, 100.5, "100"])
def test_invalid_quantity(qty):
    data = sample()
    data["orders"][0]["qty"] = qty
    with pytest.raises(ValueError):
        capture(data)


def test_duplicate_order_and_nan_fail_closed():
    data = sample()
    data["orders"] *= 2
    with pytest.raises(ValueError):
        capture(data)
    data = sample()
    data["fills"][0]["price"] = float("nan")
    with pytest.raises(ValueError):
        capture(data)


def test_tampering_and_unknown_version_fail():
    snapshot = capture(sample())
    snapshot["payload"]["orders"][0]["qty"] = 200
    with pytest.raises(ValueError, match="校验"):
        reconcile(snapshot)
    snapshot = capture(sample())
    snapshot["schema_version"] = 2
    with pytest.raises(ValueError, match="版本"):
        reconcile(snapshot)


@pytest.mark.parametrize("error", [PermissionError, FileNotFoundError])
def test_cli_read_failure_is_explicit(monkeypatch, capsys, error):
    def fail(*args, **kwargs):
        raise error("synthetic")
    monkeypatch.setattr("review_reconciliation.Path.read_text", fail)
    assert main(["capture", "synthetic.json"]) == 2
    assert error.__name__ in capsys.readouterr().err


def test_cli_capture_and_replay(monkeypatch, capsys):
    import json
    monkeypatch.setattr("review_reconciliation.Path.read_text", lambda *a, **k: json.dumps(sample()))
    assert main(["capture", "synthetic.json"]) == 0
    snapshot = capsys.readouterr().out
    monkeypatch.setattr("review_reconciliation.Path.read_text", lambda *a, **k: snapshot)
    assert main(["replay", "synthetic.json"]) == 0
    assert json.loads(capsys.readouterr().out)["ledger_consistent"]
    broken = sample()
    broken["fills"] = []
    monkeypatch.setattr("review_reconciliation.Path.read_text",
                        lambda *a, **k: json.dumps(capture(broken)))
    assert main(["replay", "synthetic.json"]) == 1


@pytest.mark.parametrize("raw", ["[]", "{}", "not json"])
def test_cli_malformed_input(monkeypatch, capsys, raw):
    monkeypatch.setattr("review_reconciliation.Path.read_text", lambda *a, **k: raw)
    assert main(["replay", "synthetic.json"]) == 2
    assert "复盘失败" in capsys.readouterr().err


def test_actual_cli_preserves_utf8_snapshot():
    import json
    import subprocess
    import sys
    from pathlib import Path

    directory = Path(__file__).parent
    result = subprocess.run(
        [sys.executable, "-B", str(directory / "review_reconciliation.py"),
         "capture", str(directory / "synthetic_input.json")],
        capture_output=True, check=False, timeout=15,
    )
    assert result.returncode == 0, result.stderr
    snapshot = json.loads(result.stdout.decode("utf-8"))
    assert snapshot["payload"]["binding"]["events"][0]["message"] == "已提交委托"
    assert reconcile(snapshot)["ledger_consistent"]
