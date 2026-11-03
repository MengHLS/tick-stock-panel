from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import polars as pl
import pytest

from app.data_providers import custom as custom_sources
from app.data_providers.custom.loader import _sanitize_for_yaml, create_provider
from app.data_providers.local_st_history import LocalStHistoryProvider
from app.services import preferences
from app.tickflow.repository import KlineRepository
from app.tickflow.security_status import normalize_st_history


def _write_history(root, rows: list[dict]) -> None:
    path = root / "st_history" / "part.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows, schema={
        "symbol": pl.String,
        "flag_date": pl.Date,
        "st_flag": pl.Boolean,
    }).write_parquet(path)


def test_local_st_history_provider_filters_without_changing_status_semantics(tmp_path) -> None:
    _write_history(tmp_path, [
        {"symbol": "A", "flag_date": date(2025, 1, 2), "st_flag": False},
        {"symbol": "A", "flag_date": date(2025, 2, 1), "st_flag": True},
        {"symbol": "B", "flag_date": date(2025, 1, 2), "st_flag": False},
    ])

    provider = LocalStHistoryProvider(tmp_path)
    frame = provider.get_st_history(symbols=["A"])

    assert frame.rows() == [
        ("A", date(2025, 1, 2), False),
        ("A", date(2025, 2, 1), True),
    ]


def test_custom_st_history_provider_maps_and_validates_contract() -> None:
    provider = create_provider({
        "name": "history_http",
        "display_name": "History HTTP",
        "auth": {"type": "none"},
        "datasets": {
            "st_history": {
                "url": "https://example.test/st-history",
                "method": "POST",
                "response_path": "data",
                "field_map": {
                    "ts_code": "symbol",
                    "effective_date": "flag_date",
                    "is_st": "st_flag",
                },
            },
        },
    })
    try:
        provider._request_rows = lambda *args, **kwargs: [  # type: ignore[method-assign]
            {"ts_code": "000001.SZ", "effective_date": "2025-01-02", "is_st": False},
            {"ts_code": "000001.SZ", "effective_date": "2025-02-01", "is_st": True},
        ]
        frame = provider.get_st_history(["000001.SZ"])
    finally:
        provider.close()

    assert frame.schema == {
        "symbol": pl.String,
        "flag_date": pl.Date,
        "st_flag": pl.Boolean,
    }
    assert frame["st_flag"].to_list() == [False, True]


def test_custom_source_config_keeps_st_history_dataset() -> None:
    cleaned = _sanitize_for_yaml({
        "name": "history_http",
        "auth": {"type": "none"},
        "datasets": {
            "st_history": {
                "url": "https://example.test/st-history",
                "field_map": {
                    "ts_code": "symbol",
                    "effective_date": "flag_date",
                    "is_st": "st_flag",
                },
            },
        },
    })
    assert set(cleaned["datasets"]) == {"st_history"}


def test_normalize_st_history_rejects_conflicts_and_missing_fields() -> None:
    with pytest.raises(ValueError, match="缺少字段"):
        normalize_st_history(pl.DataFrame({"symbol": ["A"]}))
    with pytest.raises(ValueError, match="冲突"):
        normalize_st_history(pl.DataFrame({
            "symbol": ["A", "A"],
            "flag_date": [date(2025, 1, 2), date(2025, 1, 2)],
            "st_flag": [False, True],
        }))


def test_repository_routes_to_local_or_custom_provider(monkeypatch, tmp_path) -> None:
    _write_history(tmp_path, [
        {"symbol": "A", "flag_date": date(2025, 1, 2), "st_flag": True},
    ])
    repo = KlineRepository.__new__(KlineRepository)
    repo.store = SimpleNamespace(data_dir=tmp_path)

    monkeypatch.setattr(
        preferences, "get_st_history_provider", lambda: "local_st_history"
    )
    assert repo.get_st_history()["st_flag"].to_list() == [True]

    fake = SimpleNamespace(
        get_st_history=lambda: pl.DataFrame({
            "symbol": ["B"],
            "flag_date": [date(2025, 3, 3)],
            "st_flag": [False],
        }),
    )
    monkeypatch.setattr(
        preferences, "get_st_history_provider", lambda: "custom_history"
    )
    monkeypatch.setattr(custom_sources, "is_custom_provider", lambda name: True)
    monkeypatch.setattr(custom_sources, "provider_has_dataset", lambda name, ds: True)
    monkeypatch.setattr(custom_sources, "get_provider", lambda name: fake)
    assert repo.get_st_history()["symbol"].to_list() == ["B"]


def test_repository_rejects_provider_without_st_history(monkeypatch, tmp_path) -> None:
    repo = KlineRepository.__new__(KlineRepository)
    repo.store = SimpleNamespace(data_dir=tmp_path)
    monkeypatch.setattr(
        preferences, "get_st_history_provider", lambda: "tickflow"
    )
    with pytest.raises(ValueError, match="不提供历史 ST"):
        repo.get_st_history()
