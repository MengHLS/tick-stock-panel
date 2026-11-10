from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.custom.trade_plan import store
from app.custom.trade_plan.ai import build_user_prompt
from app.custom.trade_plan.metrics import derive_plan, summarize, with_metrics
from app.custom.trade_plan.models import PlanInput
from app.custom.trade_plan.routes import build_router


def _plan(**overrides) -> dict:
    data = {
        "plan_date": date(2026, 11, 10),
        "symbol": "600001.SH",
        "name": "测试股",
        "setup": "first_board",
        "market_mood": "ferment",
        "confidence": 4,
        "planned_hold": "overnight",
        "planned_entry_low": 10.0,
        "planned_entry_high": 10.5,
        "stop_loss": 9.8,
        "target_price": 11.5,
        "planned_position_pct": 20,
        "status": "exited",
        "actual_entry_price": 10.6,
        "entry_at": "2026-11-10T09:35",
        "actual_position_pct": 30,
        "actual_exit_price": 11.2,
        "exit_at": "2026-11-10T10:10",
        "exit_reason": "target",
        "review": "按计划止盈",
    }
    data.update(overrides)
    return PlanInput(**data).model_dump(mode="json")


def test_derive_plan_uses_percentage_points_and_actual_risk():
    plan = _plan()
    metrics = derive_plan(plan)

    assert metrics["planned_entry_mid"] == 10.25
    assert metrics["entry_deviation_pct"] == pytest.approx(3.41, abs=0.01)
    assert metrics["chase_pct"] == pytest.approx(0.95, abs=0.01)
    assert metrics["pnl_pct"] == pytest.approx(5.66, abs=0.01)
    assert metrics["actual_risk_pct"] == pytest.approx(7.55, abs=0.01)
    assert metrics["r_multiple"] == pytest.approx(0.75, abs=0.01)
    assert metrics["entry_in_plan"] is False
    assert metrics["position_in_plan"] is False
    assert metrics["discipline_score"] == 50
    assert metrics["hold_minutes"] == 35


def test_flags_expose_chase_oversize_and_stop_breach():
    row = with_metrics(_plan())
    codes = {flag["code"] for flag in row["flags"]}
    assert {"chase", "oversize"} <= codes

    breached = with_metrics(_plan(actual_exit_price=9.7, exit_reason="manual"))
    breached_codes = {flag["code"] for flag in breached["flags"]}
    assert "stop_breach" in breached_codes
    assert breached["metrics"]["stop_respected"] is False


def test_summarize_separates_execution_from_performance():
    win = _plan()
    loss = _plan(
        symbol="600002.SH",
        status="exited",
        actual_entry_price=10.2,
        actual_exit_price=9.9,
        exit_reason="stop",
        actual_position_pct=20,
    )
    missed = _plan(symbol="600003.SH", status="missed", actual_entry_price=None,
                   entry_at=None, actual_exit_price=None, exit_at=None,
                   actual_position_pct=None, exit_reason=None)

    stats = summarize([win, loss, missed])

    assert stats["total"] == 3
    assert stats["executed"] == 2
    assert stats["closed"] == 2
    assert stats["execution_rate"] == pytest.approx(66.67, abs=0.01)
    assert stats["win_rate"] == 50
    assert stats["avg_pnl_pct"] == pytest.approx(1.36, abs=0.01)
    assert stats["by_setup"][0]["key"] == "first_board"
    assert stats["by_mood"][0]["closed"] == 2
    assert len(stats["equity_curve"]) == 2


def test_ai_prompt_uses_chinese_labels_and_user_focus():
    plan = _plan()
    rows = [with_metrics(plan)]
    prompt = build_user_prompt(rows, summarize([plan]), "重点看追高")
    assert "首板打板" in prompt
    assert "发酵" in prompt
    assert "已结束" in prompt
    assert "重点看追高" in prompt


def test_plan_validation_rejects_bad_ranges_and_incomplete_exit():
    with pytest.raises(ValidationError, match="区间下限"):
        _plan(planned_entry_low=10.8, planned_entry_high=10.2)
    with pytest.raises(ValidationError, match="实际卖出价"):
        _plan(actual_exit_price=None)
    with pytest.raises(ValidationError, match="实际买入价"):
        _plan(status="entered", actual_entry_price=None)


def test_store_create_update_delete_and_reports(tmp_path):
    created = store.save_plan(tmp_path, _plan())
    assert created["id"].startswith("tp_")
    assert created["created_at"]

    updated_payload = _plan(review="更新后的复盘")
    updated = store.save_plan(tmp_path, updated_payload, plan_id=created["id"])
    assert updated["id"] == created["id"]
    assert updated["created_at"] == created["created_at"]
    assert store.list_plans(tmp_path)[0]["review"] == "更新后的复盘"

    assert store.list_plans(tmp_path, setup="relay") == []
    assert store.list_plans(tmp_path, query="600001")
    assert store.delete_plan(tmp_path, created["id"]) is True
    assert store.list_plans(tmp_path) == []

    report = store.save_report(tmp_path, {"content": "# 复盘", "stats": {"closed": 1}})
    assert report["id"].startswith("tpr_")
    assert store.list_reports(tmp_path)[0]["content"] == "# 复盘"
    assert store.delete_report(tmp_path, report["id"]) is True


def _client(tmp_path) -> TestClient:
    app = FastAPI()
    app.state.repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    app.include_router(build_router())
    return TestClient(app)


def test_api_crud_and_validation(tmp_path):
    client = _client(tmp_path)
    payload = _plan()

    created = client.post("/api/custom/trade-plan/plans", json=payload)
    assert created.status_code == 200
    plan = created.json()["plan"]
    assert plan["metrics"]["pnl_pct"] == pytest.approx(5.66, abs=0.01)

    listed = client.get("/api/custom/trade-plan/plans", params={"setup": "first_board"})
    assert listed.status_code == 200
    assert listed.json()["stats"]["closed"] == 1
    assert listed.json()["plans"][0]["flags"]

    payload["review"] = "补充复盘"
    updated = client.put(f"/api/custom/trade-plan/plans/{plan['id']}", json=payload)
    assert updated.status_code == 200
    assert updated.json()["plan"]["review"] == "补充复盘"

    invalid = client.post(
        "/api/custom/trade-plan/plans",
        json={**_plan(), "status": "exited", "actual_exit_price": None},
    )
    assert invalid.status_code == 422

    assert client.delete(f"/api/custom/trade-plan/plans/{plan['id']}").status_code == 200
    assert client.delete(f"/api/custom/trade-plan/plans/{plan['id']}").status_code == 404


def test_api_report_crud(tmp_path):
    client = _client(tmp_path)
    saved = client.post(
        "/api/custom/trade-plan/reports",
        json={"content": "# 执行复盘", "stats": {"closed": 2}},
    )
    assert saved.status_code == 200
    report = saved.json()["report"]
    assert client.get("/api/custom/trade-plan/reports").json()["reports"][0]["id"] == report["id"]
    assert client.delete(f"/api/custom/trade-plan/reports/{report['id']}").status_code == 200
