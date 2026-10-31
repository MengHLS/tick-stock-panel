"""Contract tests for the Tencent minute-only data-source plugin."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import httpx
import yaml

from app.plugins.tencent.provider import TencentProvider


def _payload(rows: list[list[object]], symbol: str = "sh600519") -> dict:
    return {
        "code": 0,
        "msg": "",
        "data": {
            symbol: {
                "m1": rows,
                "qt": {symbol: ["", "", "", "", "", "", ""]},
            }
        },
    }


def _client(payload: dict) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload, request=request)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _provider(payload: dict) -> TencentProvider:
    provider = TencentProvider()
    provider._client = _client(payload)
    return provider


def test_manifest_declares_only_minute_source() -> None:
    manifest = yaml.safe_load(
        (Path(__file__).parents[1] / "app/plugins/tencent/plugin.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["display_name"] == "腾讯行情"
    assert set(manifest["datasets"]) == {"minute"}


def test_maps_ohlcv_and_keeps_null_amount() -> None:
    rows = [
        ["202610300930", "10.00", "10.10", "10.20", "9.90", "123.45", {}, "1.00"],
        ["202610300931", "10.10", "10.15", "10.16", "10.08", "67.00", {}, "0.50"],
    ]
    df = _provider(_payload(rows)).get_minute(
        ["600519.SH"],
        datetime(2026, 10, 30, 9, 25),
        datetime(2026, 10, 30, 15, 5),
    )
    assert df.columns == [
        "symbol", "datetime", "open", "high", "low", "close", "volume", "amount",
    ]
    assert df["symbol"].to_list() == ["600519.SH", "600519.SH"]
    assert df["datetime"].to_list() == [
        datetime(2026, 10, 30, 9, 30),
        datetime(2026, 10, 30, 9, 31),
    ]
    assert df["open"].to_list() == [10.0, 10.1]
    assert df["high"].to_list() == [10.2, 10.16]
    assert df["low"].to_list() == [9.9, 10.08]
    assert df["close"].to_list() == [10.1, 10.15]
    assert df["volume"].to_list() == [123.45, 67.0]
    assert df["amount"].null_count() == 2


def test_uses_800_bar_cap_and_applies_requested_window() -> None:
    rows = [
        ["202610291459", "1", "1", "1", "1", "1", {}, "0"],
        ["202610300930", "1", "1", "1", "1", "1", {}, "0"],
        ["202610300931", "1", "1", "1", "1", "1", {}, "0"],
        ["202610300932", "1", "1", "1", "1", "1", {}, "0"],
    ]
    df = _provider(_payload(rows)).get_minute(
        ["600519.SH"],
        datetime(2026, 10, 30, 9, 31),
        datetime(2026, 10, 30, 9, 32),
    )
    assert df["datetime"].to_list() == [
        datetime(2026, 10, 30, 9, 31),
        datetime(2026, 10, 30, 9, 32),
    ]


def test_rejects_malformed_or_out_of_session_bars() -> None:
    rows = [
        ["202610300930", "10", "10", "10", "10", "1", {}, "0"],
        ["202610301200", "10", "10", "10", "10", "1", {}, "0"],
        ["bad", "10", "10", "10", "10", "1", {}, "0"],
    ]
    df = _provider(_payload(rows)).get_minute(
        ["600519.SH"],
        datetime(2026, 10, 30, 9, 25),
        datetime(2026, 10, 30, 15, 5),
    )
    assert df.height == 1
    assert df["datetime"].to_list() == [datetime(2026, 10, 30, 9, 30)]


def test_hard_failure_is_isolated_between_symbols() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "sz000001" in str(request.url):
            return httpx.Response(500, request=request)
        return httpx.Response(
            200,
            json=_payload([
                ["202610300930", "10", "10", "10", "10", "1", {}, "0"],
            ]),
            request=request,
        )

    provider = TencentProvider()
    provider._client = httpx.Client(transport=httpx.MockTransport(handler))
    progress: list[tuple[int, int]] = []
    df = provider.get_minute(
        ["600519.SH", "000001.SZ"],
        datetime(2026, 10, 30, 9, 25),
        datetime(2026, 10, 30, 15, 5),
        on_chunk_done=lambda cur, total: progress.append((cur, total)),
    )
    assert df["symbol"].unique().to_list() == ["600519.SH"]
    assert progress == [(1, 2), (2, 2)]


def test_rejects_bj_and_non_one_minute_without_network() -> None:
    provider = TencentProvider()
    df = provider.get_minute(
        ["920001.BJ"],
        datetime(2026, 10, 30, 9, 25),
        datetime(2026, 10, 30, 15, 5),
    )
    assert df.is_empty()
    assert provider.get_minute(
        ["600519.SH"], None, None, freq="5m",
    ).is_empty()


def test_test_dataset_reports_real_frame_shape() -> None:
    provider = _provider(_payload([
        ["202610300930", "10", "10", "10", "10", "1", {}, "0"],
    ]))
    result = provider.test_dataset("minute", ["600519.SH"])
    assert result["rows"] == 1
    assert result["preview"][0]["datetime"] == "2026-10-30T09:30:00"


def test_loader_registers_tencent_minute(tmp_path: Path) -> None:
    from app.data_providers import custom

    custom.load_all(tmp_path)
    try:
        assert custom.provider_has_dataset("tencent", "minute")
        assert custom.get_provider("tencent").name == "tencent"
        assert custom.plugin_manifest("tencent")["datasets"] == ["minute"]
    finally:
        custom.load_all()
