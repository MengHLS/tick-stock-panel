"""Platform limit-up extension data contract."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest

from app.custom.limit_up_platform import service
from app.services.ext_data import (
    ExtConfig,
    ExtConfigStore,
    ExtField,
    PullConfig,
    apply_config_mapping,
    cast_df_to_schema,
)
from app.services.ext_pull import _apply_field_map, _assert_rows_date


def test_config_is_a_runnable_daily_timeseries_pull() -> None:
    cfg = service.limit_up_config()
    pull = cfg.pull
    assert cfg.mode == "timeseries"
    assert pull is not None
    assert pull.url == service.SOURCE_URL
    assert pull.response_path == "result.data.json"
    assert pull.date_param == "input"
    assert pull.date_value_template == service.DATE_VALUE_TEMPLATE
    assert pull.schedule_trading_only is True
    assert pull.granularity == "daily"
    assert pull.enabled is True
    assert {field.name for field in cfg.fields} >= {
        "symbol", "code", "date", "name", "limit_up_time", "board_count_text",
        "circulation_value_yi", "amount_yi", "sector", "keywords",
    }


def test_row_mapping_generates_symbol_code_and_date_guard(tmp_path: Path) -> None:
    cfg = service.limit_up_config()
    assert cfg.pull is not None
    rows = _apply_field_map(
        [{
            "id": 8620625,
            "stockCode": "000002.SZ",
            "stockName": "万科A",
            "limitUpDate": "2026-09-29",
            "limitUpTime": "14:07:24",
            "boardCount": "1",
            "circulationValue": "396.4",
            "turnover": "31.8",
            "sector": "地产",
            "keywords": "房地产+物业管理",
            "createdBy": 1,
            "createdAt": "2026-09-29T11:30:44.000Z",
            "updatedAt": "2026-09-29T11:30:44.000Z",
        }],
        cfg.pull.field_map,
    )
    frame = cast_df_to_schema(
        apply_config_mapping(pl.DataFrame(rows), cfg, tmp_path),
        cfg.fields,
    )
    assert frame["symbol"].to_list() == ["000002.SZ"]
    assert frame["code"].to_list() == ["000002"]
    assert frame["date"].to_list() == ["2026-09-29"]
    assert frame["circulation_value_yi"].dtype == pl.Float64
    assert frame["amount_yi"].to_list() == [31.8]
    _assert_rows_date(rows, date(2026, 9, 29))
    with pytest.raises(ValueError, match="不一致"):
        _assert_rows_date(rows, date(2026, 9, 28))


def test_config_is_seeded_once_and_deleted_table_is_not_revived(tmp_path: Path) -> None:
    seeded = service.ensure_limit_up_config(tmp_path)
    assert seeded is not None
    store = ExtConfigStore(tmp_path)
    assert store.get(service.CONFIG_ID) is not None
    assert (tmp_path / "ext_data" / service.SEED_MARKER).exists()

    assert store.delete(service.CONFIG_ID) is True
    assert service.ensure_limit_up_config(tmp_path) is None
    assert store.get(service.CONFIG_ID) is None


def test_existing_user_config_is_not_overwritten(tmp_path: Path) -> None:
    store = ExtConfigStore(tmp_path)
    store.upsert(ExtConfig(
        id=service.CONFIG_ID,
        label="我的自定义表",
        mode="snapshot",
        fields=[ExtField("symbol", "string")],
        pull=PullConfig(url="https://example.test/mine"),
    ))

    service.ensure_limit_up_config(tmp_path)

    current = store.get(service.CONFIG_ID)
    assert current is not None
    assert current.label == "我的自定义表"
    assert current.pull is not None and current.pull.url == "https://example.test/mine"
