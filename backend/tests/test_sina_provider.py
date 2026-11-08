"""Contract tests for the Sina minute-only data-source plugin."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
import yaml


def _row(
    day: str = "2026-11-02 09:31:00",
    open_: str = "22.260",
    high: str = "22.440",
    low: str = "22.140",
    close: str = "22.180",
    volume: str = "90900",
    amount: str = "2023460.9989",
) -> dict[str, str]:
    return {
        "day": day,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "amount": amount,
    }


def _provider(payload: object, capture: list[httpx.Request] | None = None):
    from app.plugins.sina.provider import SinaProvider

    def handler(request: httpx.Request) -> httpx.Response:
        if capture is not None:
            capture.append(request)
        return httpx.Response(200, json=payload, request=request)

    provider = SinaProvider()
    provider._client = httpx.Client(transport=httpx.MockTransport(handler))
    return provider


def test_manifest_declares_minute_and_main_board_full_minute() -> None:
    manifest = yaml.safe_load(
        (Path(__file__).parents[1] / "app/plugins/sina/plugin.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["name"] == "sina"
    assert manifest["display_name"] == "新浪行情"
    assert set(manifest["datasets"]) == {"minute", "full_minute"}


def test_request_uses_sina_one_minute_contract() -> None:
    capture: list[httpx.Request] = []
    provider = _provider([_row()], capture)
    provider.get_minute(
        ["600519.SH"],
        datetime(2026, 11, 2, 9, 25),
        datetime(2026, 11, 2, 15, 5),
    )
    assert len(capture) == 1
    request = capture[0]
    assert request.url.path == "/cn/api/json_v2.php/CN_MarketDataService.getKLineData"
    assert dict(request.url.params) == {
        "symbol": "sh600519",
        "scale": "1",
        "ma": "no",
        "datalen": "1500",
    }


def test_maps_ohlcv_and_converts_share_volume_to_hands() -> None:
    provider = _provider([_row()])
    frame = provider.get_minute(
        ["300930.SZ"],
        datetime(2026, 11, 2, 9, 25),
        datetime(2026, 11, 2, 15, 5),
    )
    assert frame.columns == [
        "symbol", "datetime", "open", "high", "low", "close", "volume", "amount",
    ]
    assert frame["symbol"].to_list() == ["300930.SZ"]
    assert frame["datetime"].to_list() == [datetime(2026, 11, 2, 9, 31)]
    assert frame["open"].to_list() == [22.26]
    assert frame["high"].to_list() == [22.44]
    assert frame["low"].to_list() == [22.14]
    assert frame["close"].to_list() == [22.18]
    assert frame["volume"].to_list() == [909.0]
    assert frame["amount"].to_list() == [2023460.9989]


def test_applies_window_sorts_and_deduplicates_bars() -> None:
    provider = _provider([
        _row("2026-11-02 09:33:00", close="22.20"),
        _row("2026-11-02 09:31:00"),
        _row("2026-11-02 09:32:00", close="22.19"),
        _row("2026-11-02 09:32:00", close="22.21"),
        _row("2026-11-03 09:31:00"),
    ])
    frame = provider.get_minute(
        ["300930.SZ"],
        datetime(2026, 11, 2, 9, 31),
        datetime(2026, 11, 2, 9, 33),
    )
    assert frame["datetime"].to_list() == [
        datetime(2026, 11, 2, 9, 31),
        datetime(2026, 11, 2, 9, 32),
        datetime(2026, 11, 2, 9, 33),
    ]
    assert frame["close"].to_list() == [22.18, 22.21, 22.20]


def test_rejects_malformed_or_out_of_session_bars() -> None:
    provider = _provider([
        _row(),
        _row("2026-11-02 12:00:00"),
        _row("bad"),
        _row(open_="0"),
        _row(high="22.00"),
        _row(volume="-1"),
    ])
    frame = provider.get_minute(
        ["300930.SZ"],
        datetime(2026, 11, 2, 9, 25),
        datetime(2026, 11, 2, 15, 5),
    )
    assert frame.height == 1
    assert frame["datetime"].to_list() == [datetime(2026, 11, 2, 9, 31)]


def test_http_failure_is_not_converted_to_empty_data() -> None:
    from app.data_providers.base import ProviderRequestError

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request)

    from app.plugins.sina.provider import SinaProvider

    provider = SinaProvider()
    provider._client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderRequestError):
        provider.get_minute(
            ["600519.SH"],
            datetime(2026, 11, 2, 9, 25),
            datetime(2026, 11, 2, 15, 5),
        )


def test_null_payload_is_not_converted_to_empty_data() -> None:
    from app.data_providers.base import ProviderRequestError

    with pytest.raises(ProviderRequestError):
        _provider(None).get_minute(["600519.SH"], None, None)


def test_empty_array_is_valid_no_data() -> None:
    frame = _provider([]).get_minute(["600519.SH"], None, None)
    assert frame.is_empty()
    assert frame.columns == [
        "symbol", "datetime", "open", "high", "low", "close", "volume", "amount",
    ]


def test_unsupported_scope_fails_before_network() -> None:
    from app.data_providers.base import ProviderRequestError
    from app.plugins.sina.provider import SinaProvider

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("unsupported scope must not request upstream")

    provider = SinaProvider()
    provider._client = httpx.Client(transport=httpx.MockTransport(handler))
    for symbols, kwargs in [
        (["920001.BJ"], {}),
        (["600519.SH"], {"freq": "5m"}),
        (["600519.SH"], {"asset_type": "etf"}),
    ]:
        with pytest.raises(ProviderRequestError):
            provider.get_minute(symbols, None, None, **kwargs)


def test_progress_reports_each_symbol() -> None:
    provider = _provider([_row()])
    progress: list[tuple[int, int]] = []
    frame = provider.get_minute(
        ["600519.SH", "300930.SZ"],
        datetime(2026, 11, 2, 9, 25),
        datetime(2026, 11, 2, 15, 5),
        on_chunk_done=lambda current, total: progress.append((current, total)),
    )
    assert set(frame["symbol"].unique().to_list()) == {"300930.SZ", "600519.SH"}
    assert progress == [(1, 2), (2, 2)]


def test_test_dataset_reports_real_frame_shape() -> None:
    provider = _provider([_row()])
    result = provider.test_dataset("minute", ["300930.SZ"])
    assert result["provider"] == "sina"
    assert result["rows"] == 1
    assert result["preview"][0]["datetime"] == "2026-11-02T09:31:00"
    assert result["preview"][0]["volume"] == 909.0


def test_loader_registers_sina_minute(tmp_path: Path) -> None:
    from app.data_providers import custom

    custom.load_all(tmp_path)
    try:
        assert custom.provider_has_dataset("sina", "minute")
        assert custom.get_provider("sina").name == "sina"
        assert set(custom.plugin_manifest("sina")["datasets"]) == {"minute", "full_minute"}
    finally:
        custom.load_all()


def _intraday_provider(handler):
    from app.plugins.sina.provider import SinaProvider

    provider = SinaProvider()
    provider._client = httpx.Client(transport=httpx.MockTransport(handler))
    return provider


def test_intraday_batch_filters_main_board_and_today() -> None:
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    today_text = today.isoformat()
    yesterday_text = (today - timedelta(days=1)).isoformat()
    capture: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        capture.append(request)
        return httpx.Response(200, json=[
            _row(f"{today_text} 09:31:00"),
            _row(f"{yesterday_text} 09:31:00"),
        ], request=request)

    provider = _intraday_provider(handler)
    frame = provider.get_intraday_batch(["600519.SH", "300930.SZ", "000001.SZ"])
    requested = {request.url.params["symbol"] for request in capture}
    assert requested == {"sh600519", "sz000001"}
    assert all(request.url.params["datalen"] == "300" for request in capture)
    assert set(frame["symbol"].unique().to_list()) == {"600519.SH", "000001.SZ"}
    assert {value.date().isoformat() for value in frame["datetime"].to_list()} == {today_text}
    assert frame["volume"].to_list() == [909.0, 909.0]


def test_intraday_batch_isolates_symbol_failures() -> None:
    today_text = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["symbol"] == "sz000001":
            return httpx.Response(503, request=request)
        return httpx.Response(200, json=[_row(f"{today_text} 09:31:00")], request=request)

    frame = _intraday_provider(handler).get_intraday_batch(["600519.SH", "000001.SZ"])
    assert frame["symbol"].unique().to_list() == ["600519.SH"]


def test_intraday_batch_fails_closed_when_all_symbols_fail() -> None:
    from app.data_providers.base import ProviderRequestError

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request)

    with pytest.raises(ProviderRequestError):
        _intraday_provider(handler).get_intraday_batch(["600519.SH", "000001.SZ"])


def test_intraday_batch_without_main_board_symbols_does_not_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("unsupported board must not request upstream")

    frame = _intraday_provider(handler).get_intraday_batch(["300930.SZ", "688184.SH"])
    assert frame.is_empty()


def test_intraday_batch_rejects_non_stock_asset_type() -> None:
    from app.data_providers.base import ProviderRequestError

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("unsupported asset type must not request upstream")

    with pytest.raises(ProviderRequestError):
        _intraday_provider(handler).get_intraday_batch(["600519.SH"], asset_type="etf")


def test_intraday_batch_has_no_cheap_increment_endpoint() -> None:
    from app.services.minute_refresh import MinuteRefreshService

    provider = _intraday_provider(lambda request: httpx.Response(200, json=[]))
    assert MinuteRefreshService(None)._custom_supports_increment(provider) is False


def test_test_dataset_supports_full_minute() -> None:
    today_text = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[_row(f"{today_text} 09:31:00")], request=request)

    result = _intraday_provider(handler).test_dataset("full_minute", ["600519.SH"])
    assert result["provider"] == "sina"
    assert result["dataset"] == "full_minute"
    assert result["rows"] == 1
    assert result["preview"][0]["volume"] == 909.0
