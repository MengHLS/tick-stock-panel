"""Contract tests for live Eastmoney opening-auction collection."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import httpx
import polars as pl
import pytest

import app.custom.eastmoney_auction as extension
from app.custom.eastmoney_auction import client as auction_client
from app.custom.eastmoney_auction import service
from app.extensions import BACKEND_EXTENSION_API_VERSION, ExtensionContext
from app.market_time import CN_TZ
from app.services.ext_data import ExtConfigStore

DAY = "2026-10-30"
SYMBOLS = ("600519.SH", "000001.SZ")


def _market_row(
    code: str,
    market: int,
    *,
    price: float = 10.0,
    volume: float = 100,
    amount: float = 100_000,
    open_: float = 10.0,
    prev_close: float = 9.5,
) -> dict:
    return {
        "f2": price,
        "f5": volume,
        "f6": amount,
        "f12": code,
        "f13": market,
        "f14": f"name-{code}",
        "f17": open_,
        "f18": prev_close,
    }


def _snapshot(observed_at: datetime) -> auction_client.MarketSnapshot:
    return auction_client.MarketSnapshot(
        rows=[
            auction_client.MarketRow(
                symbol="600519.SH",
                name="贵州茅台",
                reference_price=1364.88,
                cumulative_volume_lots=1534,
                cumulative_amount=209_084_200,
                auction_open=1363.0,
                prev_close=1354.0,
            ),
            auction_client.MarketRow(
                symbol="000001.SZ",
                name="平安银行",
                reference_price=11.38,
                cumulative_volume_lots=3612,
                cumulative_amount=4_110_456,
                auction_open=11.38,
                prev_close=11.2,
            ),
        ],
        total=2,
        observed_at=observed_at,
    )


def _final(symbol: str) -> auction_client.AuctionFinal:
    if symbol == "600519.SH":
        return auction_client.AuctionFinal(
            symbol=symbol,
            auction_open=1363.0,
            prev_close=1354.0,
            volume_lots=1534,
            amount=209_084_200,
            source_timestamp=f"{DAY} 09:26",
        )
    return auction_client.AuctionFinal(
        symbol=symbol,
        auction_open=11.38,
        prev_close=11.2,
        volume_lots=3612,
        amount=4_110_456,
        source_timestamp=f"{DAY} 09:26",
    )


class FakeClient:
    def __init__(
        self,
        snapshot: auction_client.MarketSnapshot,
        *,
        session: bool = True,
        final: dict[str, auction_client.AuctionFinal | Exception] | None = None,
    ) -> None:
        self.snapshot = snapshot
        self.session = session
        self.final = final or {}

    def verify_session(self, expected_date) -> bool:
        return self.session

    def fetch_market_snapshot(self, *, symbols, cancel_event=None):
        if cancel_event is not None and cancel_event.is_set():
            raise service.SyncCancelledError("cancelled")
        return self.snapshot

    def fetch_auction_final(self, symbol: str, expected_date) -> auction_client.AuctionFinal:
        result = self.final.get(symbol, _final(symbol))
        if isinstance(result, Exception):
            raise result
        return result


def test_ulist_batches_are_complete_and_stamped_at_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_batches: list[list[str]] = []
    monkeypatch.setattr(auction_client, "_BATCH_SIZE", 2)

    def handler(request: httpx.Request) -> httpx.Response:
        secids = request.url.params["secids"].split(",")
        seen_batches.append(secids)
        rows = []
        for secid in secids:
            market, code = secid.split(".", 1)
            rows.append(_market_row(code, int(market)))
        return httpx.Response(
            200,
            json={"data": {"total": len(rows), "diff": rows}},
            request=request,
        )

    completed_at = datetime(2026, 10, 30, 9, 20, 8, tzinfo=CN_TZ)
    client = auction_client.EastmoneyAuctionClient(
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        clock=lambda: completed_at,
    )
    snapshot = client.fetch_market_snapshot(
        symbols=["600519.SH", "000001.SZ", "300750.SZ"]
    )

    assert seen_batches == [
        ["1.600519", "0.000001"],
        ["0.300750"],
    ]
    assert snapshot.total == 3
    assert snapshot.observed_at == completed_at
    assert [row.symbol for row in snapshot.rows] == [
        "600519.SH",
        "000001.SZ",
        "300750.SZ",
    ]
    assert snapshot.rows[0].cumulative_volume_lots == 100
    assert snapshot.rows[0].cumulative_amount == 100_000


def test_ulist_partial_round_fails_closed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        rows = [_market_row("600519", 1)]
        return httpx.Response(
            200,
            json={"data": {"total": 1, "diff": rows}},
            request=request,
        )

    client = auction_client.EastmoneyAuctionClient(
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(auction_client.EastmoneyError, match="incomplete"):
        client.fetch_market_snapshot(symbols=["600519.SH", "000001.SZ"])


def test_stock_get_final_uses_single_symbol_cross_check() -> None:
    stamp = int(datetime(2026, 10, 30, 9, 26, 10, tzinfo=CN_TZ).timestamp())

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": {
                    "f43": 1363.0,
                    "f47": 1534,
                    "f48": 209084200,
                    "f57": "600519",
                    "f58": "贵州茅台",
                    "f60": 1354.0,
                    "f86": stamp,
                }
            },
            request=request,
        )

    client = auction_client.EastmoneyAuctionClient(
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    final = client.fetch_auction_final("600519.SH", date(2026, 10, 30))

    assert final.auction_open == 1363.0
    assert final.prev_close == 1354.0
    assert final.volume_lots == 1534
    assert final.amount == 209_084_200
    assert final.source_timestamp == "2026-10-30T09:26:10+08:00"


def test_session_check_rejects_previous_trading_day_timestamp() -> None:
    stamp = int(datetime(2026, 10, 30, 15, 0, tzinfo=CN_TZ).timestamp())

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"f86": stamp}}, request=request)

    client = auction_client.EastmoneyAuctionClient(
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert client.verify_session(date(2026, 10, 30))
    assert not client.verify_session(date(2026, 11, 2))


def test_step_configs_are_seeded_once_and_never_resurrected(tmp_path: Path) -> None:
    seeded = service.ensure_auction_configs(tmp_path)
    assert seeded[service.PREOPEN_CONFIG] is not None
    assert seeded[service.RESULT_CONFIG] is not None
    assert (tmp_path / "ext_data" / service.SEED_MARKER).exists()

    store = ExtConfigStore(tmp_path)
    assert store.delete(service.PREOPEN_CONFIG)
    assert service.ensure_auction_configs(tmp_path)[service.PREOPEN_CONFIG] is None


def test_local_universe_excludes_non_sh_sz_symbols(tmp_path: Path) -> None:
    path = tmp_path / "instruments" / "instruments.parquet"
    path.parent.mkdir(parents=True)
    pl.DataFrame(
        {"symbol": ["600519.SH", "000001.SZ", "920001.BJ", "000001.SH"]}
    ).write_parquet(path)

    assert service.local_stock_symbols(tmp_path) == ["000001.SZ", "600519.SH"]


def test_preopen_snapshot_keeps_observation_time_and_raw_lot_units(tmp_path: Path) -> None:
    service.ensure_auction_configs(tmp_path)
    observed = datetime(2026, 10, 30, 9, 20, 8, tzinfo=CN_TZ)
    fake = FakeClient(_snapshot(observed))

    result = service.sync_preopen_snapshot(
        tmp_path,
        client=fake,
        now=datetime(2026, 10, 30, 9, 20, 0, tzinfo=CN_TZ),
        create_config=False,
        symbols=list(SYMBOLS),
    )

    assert result["status"] == "written"
    path = (
        tmp_path / "ext_data" / service.PREOPEN_CONFIG / "timeseries"
        / f"date={DAY}" / "part.parquet"
    )
    frame = pl.read_parquet(path).sort("symbol")
    assert frame["cumulative_volume_lots"].to_list() == [3612.0, 1534.0]
    assert frame["cumulative_amount"].to_list() == [4_110_456.0, 209_084_200.0]
    assert frame["observed_at"].unique().to_list() == [observed.isoformat()]
    assert not {"matched_volume", "unmatched_buy", "unmatched_sell"} & set(frame.columns)


def test_process_round_finishing_after_0925_is_discarded(tmp_path: Path) -> None:
    service.ensure_auction_configs(tmp_path)
    fake = FakeClient(
        _snapshot(datetime(2026, 10, 30, 9, 25, 1, tzinfo=CN_TZ))
    )

    result = service.sync_preopen_snapshot(
        tmp_path,
        client=fake,
        now=datetime(2026, 10, 30, 9, 24, 55, tzinfo=CN_TZ),
        create_config=False,
        symbols=list(SYMBOLS),
    )

    assert result["status"] == "late"
    assert not list(
        (tmp_path / "ext_data" / service.PREOPEN_CONFIG / "timeseries").rglob("*.parquet")
    )


def test_final_result_is_published_only_after_independent_sample_gate(
    tmp_path: Path,
) -> None:
    service.ensure_auction_configs(tmp_path)
    observed = datetime(2026, 10, 30, 9, 26, 20, tzinfo=CN_TZ)
    fake = FakeClient(_snapshot(observed))

    result = service.sync_final_results(
        tmp_path,
        client=fake,
        now=datetime(2026, 10, 30, 9, 26, 10, tzinfo=CN_TZ),
        create_config=False,
        verify_sample_size=2,
        symbols=list(SYMBOLS),
    )

    assert result["status"] == "written"
    assert result["verified"] == 2
    path = (
        tmp_path / "ext_data" / service.RESULT_CONFIG / "timeseries"
        / f"date={DAY}" / "part.parquet"
    )
    frame = pl.read_parquet(path).sort("symbol")
    assert frame["volume_shares"].to_list() == [361_200.0, 153_400.0]
    assert frame["amount"].to_list() == [4_110_456.0, 209_084_200.0]
    assert frame["has_result"].to_list() == [1, 1]


def test_final_gate_mismatch_writes_nothing(tmp_path: Path) -> None:
    service.ensure_auction_configs(tmp_path)
    observed = datetime(2026, 10, 30, 9, 26, 20, tzinfo=CN_TZ)
    fake = FakeClient(
        _snapshot(observed),
        final={
            "600519.SH": auction_client.AuctionFinal(
                symbol="600519.SH",
                auction_open=1363.0,
                prev_close=1354.0,
                volume_lots=1534,
                amount=209_084_201,
                source_timestamp=f"{DAY} 09:26",
            )
        },
    )

    with pytest.raises(service.AuctionVerificationError, match="verification"):
        service.sync_final_results(
            tmp_path,
            client=fake,
            now=datetime(2026, 10, 30, 9, 26, 10, tzinfo=CN_TZ),
            create_config=False,
            verify_sample_size=2,
            symbols=list(SYMBOLS),
        )
    assert not list(
        (tmp_path / "ext_data" / service.RESULT_CONFIG / "timeseries").rglob("*.parquet")
    )


@pytest.mark.asyncio
async def test_scheduler_uses_process_then_final_windows(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []

    async def fake_to_thread(fn, *args, **kwargs):
        calls.append(getattr(fn, "__name__", getattr(fn, "func", fn).__name__))
        return {"status": "written", "rows": 1}

    monkeypatch.setattr(service.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(service.trading_day, "is_trading_day", lambda now=None: True)

    scheduler = service.EastmoneyAuctionScheduler()
    scheduler._enabled = True
    scheduler._data_dir = tmp_path

    assert (
        await scheduler.run_once(datetime(2026, 10, 30, 9, 14, 0, tzinfo=CN_TZ))
    )["status"] == "not_due"
    assert (
        await scheduler.run_once(datetime(2026, 10, 30, 9, 20, 0, tzinfo=CN_TZ))
    )["status"] == "written"
    assert (
        await scheduler.run_once(datetime(2026, 10, 30, 9, 20, 20, tzinfo=CN_TZ))
    )["status"] == "not_due"
    assert (
        await scheduler.run_once(datetime(2026, 10, 30, 9, 26, 10, tzinfo=CN_TZ))
    )["status"] == "written"
    assert calls == ["sync_preopen_snapshot", "sync_final_results"]


@pytest.mark.asyncio
async def test_extension_startup_seeds_and_starts_scheduler(tmp_path: Path, monkeypatch) -> None:
    calls: list[tuple] = []
    repository = object()
    monkeypatch.setattr(
        service,
        "ensure_auction_configs",
        lambda root: calls.append(("seed", root)),
    )
    monkeypatch.setattr(
        service.auction_scheduler,
        "start",
        lambda root, *, enabled, repository: calls.append(
            ("start", root, enabled, repository)
        ),
    )
    monkeypatch.setattr(
        extension.preferences,
        "get_data_sync_prefs",
        lambda: {"data_sync_ext_pull_enabled": True},
    )

    extension.startup(
        ExtensionContext(
            api_version=BACKEND_EXTENSION_API_VERSION,
            data_dir=tmp_path,
            repository=repository,
        )
    )

    assert calls == [
        ("seed", tmp_path),
        ("start", tmp_path, True, repository),
    ]
