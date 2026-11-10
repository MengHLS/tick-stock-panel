"""动态自选分组契约与声明式条件求值。"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import polars as pl
import pytest
from fastapi import HTTPException

from app.api import watchlist as watchlist_api
from app.config import settings
from app.custom import dynamic_watchlist
from app.custom.dynamic_watchlist import resolver
from app.services import watchlist, watchlist_group_resolvers

_RESOLVER_KIND = "test_static"


def _register_static_resolver() -> None:
    if watchlist_group_resolvers.is_registered(_RESOLVER_KIND):
        return

    def _resolve(rule, as_of, context):
        return [{"symbol": "600000.SH", "name": "测试"}]

    watchlist_group_resolvers.register(_RESOLVER_KIND, _resolve)


def _request():
    repo = MagicMock()
    repo.get_name_map.return_value = {}
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(repo=repo)))


def test_dynamic_group_persists_kind_and_rejects_manual_members(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    _register_static_resolver()

    groups, created = watchlist.create_group(
        "测试动态",
        "rose",
        kind="dynamic",
        rule={"type": _RESOLVER_KIND},
    )
    assert created["kind"] == "dynamic"
    assert created["rule"] == {"type": _RESOLVER_KIND}
    assert groups[0]["kind"] == "dynamic"

    with pytest.raises(ValueError, match="不能手工添加成员"):
        watchlist.add("600000.SH", group_id=created["id"])
    with pytest.raises(ValueError, match="没有手工成员"):
        watchlist.clear_group(created["id"])

    group, rows = watchlist.resolve_group(
        created["id"],
        as_of=date(2026, 1, 5),
        context={},
    )
    assert group["id"] == created["id"]
    assert rows == [{
        "symbol": "600000.SH",
        "name": "测试",
        "group_ids": [created["id"]],
        "asset_type": "stock",
    }]


def test_dynamic_group_api_contract(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    _register_static_resolver()

    created = watchlist_api.create_group(
        watchlist_api.GroupNameRequest(
            name="接口动态",
            color="teal",
            kind="dynamic",
            rule={"type": _RESOLVER_KIND},
        )
    )
    group_id = created["group"]["id"]
    result = watchlist_api.resolve_group(
        group_id,
        _request(),
        as_of=date(2026, 1, 5),
    )
    assert result["as_of"] == "2026-01-05"
    assert result["rows"][0]["symbol"] == "600000.SH"

    with pytest.raises(HTTPException) as exc:
        watchlist_api.resolve_group("missing", _request(), as_of=date(2026, 1, 5))
    assert exc.value.status_code == 404


def test_manual_group_payload_stays_backward_compatible(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    _, created = watchlist.create_group("手工")
    assert created == {"id": created["id"], "name": "手工", "color": "sky"}
    assert watchlist.list_groups()[0] == created


def _condition_frame() -> pl.DataFrame:
    d1 = date(2026, 1, 2)
    d2 = date(2026, 1, 5)
    rows = [
        # 5 板后断板（未摸板）
        ("000001.SZ", d1, 5, 10.0, 11.0, 11.0),
        ("000001.SZ", d2, 0, 10.0, 10.4, 11.0),
        # 5 板后炸板（摸板未封）
        ("000002.SZ", d1, 5, 10.0, 11.0, 11.0),
        ("000002.SZ", d2, 0, 11.0, 10.6, 11.0),
        # 昨日首板今日晋级 2 板
        ("000003.SZ", d1, 1, 10.0, 11.0, 11.0),
        ("000003.SZ", d2, 2, 11.0, 12.1, 12.1),
        # 当日首板
        ("000004.SZ", d1, 0, 10.0, 10.2, 11.0),
        ("000004.SZ", d2, 1, 10.2, 11.0, 11.0),
    ]
    return pl.DataFrame(
        rows,
        schema={
            "symbol": pl.Utf8,
            "date": pl.Date,
            "consecutive_limit_ups": pl.UInt32,
            "raw_high": pl.Float64,
            "raw_close": pl.Float64,
            "limit_up_price": pl.Float64,
        },
        orient="row",
    ).with_columns([
        pl.col("raw_close").alias("close"),
        pl.lit(0.0).alias("change_pct"),
    ]).sort(["symbol", "date"])


def _resolve(conditions, as_of=date(2026, 1, 5)):
    screener = SimpleNamespace(load_enriched_history=lambda target, days: _condition_frame())
    return resolver.resolve(
        {
            "type": "conditions",
            "schema_version": 1,
            "logic": "and",
            "conditions": conditions,
        },
        as_of,
        {"screener": screener},
    )


def test_condition_resolver_first_board_and_previous_first_board():
    today_first = _resolve([{
        "left": "consecutive_limit_ups", "op": "==", "right": "1",
        "leftDays": 0, "rightDays": 0,
    }])
    assert [row["symbol"] for row in today_first] == ["000004.SZ"]

    yesterday_first = _resolve([{
        "left": "consecutive_limit_ups", "op": "==", "right": "1",
        "leftDays": 1, "rightDays": 0,
    }])
    assert [row["symbol"] for row in yesterday_first] == ["000003.SZ"]


def test_condition_resolver_five_board_break_and_broken():
    failed = _resolve([
        {"left": "consecutive_limit_ups", "op": ">=", "right": "5", "leftDays": 1, "rightDays": 0},
        {"left": "consecutive_limit_ups", "op": "==", "right": "0", "leftDays": 0, "rightDays": 0},
    ])
    assert [row["symbol"] for row in failed] == ["000001.SZ", "000002.SZ"]

    broken = _resolve([
        {"left": "consecutive_limit_ups", "op": ">=", "right": "5", "leftDays": 1, "rightDays": 0},
        {"left": "consecutive_limit_ups", "op": "==", "right": "0", "leftDays": 0, "rightDays": 0},
        {"left": "raw_high", "op": ">=", "right": "field:limit_up_price", "leftDays": 0, "rightDays": 0},
        {"left": "raw_close", "op": "<", "right": "field:limit_up_price", "leftDays": 0, "rightDays": 0},
    ])
    assert [row["symbol"] for row in broken] == ["000002.SZ"]


def test_condition_rule_validation():
    with pytest.raises(ValueError, match="至少需要 1 个条件"):
        resolver.validate({"type": "conditions", "conditions": []})
    with pytest.raises(ValueError, match="AND"):
        resolver.validate({
            "type": "conditions",
            "logic": "or",
            "conditions": [{"left": "close", "op": ">", "right": "1"}],
        })
    with pytest.raises(ValueError, match="版本"):
        resolver.validate({
            "type": "conditions",
            "schema_version": 2,
            "conditions": [{"left": "close", "op": ">", "right": "1"}],
        })


def test_extension_registers_conditions_resolver(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    dynamic_watchlist.setup(None)
    groups, created = watchlist.create_group(
        "条件动态",
        kind="dynamic",
        rule={
            "type": "conditions",
            "schema_version": 1,
            "logic": "and",
            "conditions": [{"left": "consecutive_limit_ups", "op": "==", "right": "1"}],
        },
    )
    assert created["kind"] == "dynamic"
    assert groups[0]["rule"]["type"] == "conditions"

    with pytest.raises(ValueError, match="至少需要 1 个条件"):
        watchlist.create_group(
            "空条件",
            kind="dynamic",
            rule={"type": "conditions", "conditions": []},
        )
