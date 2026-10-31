"""Install the opening-auction factor pack into the existing custom factor store.

Run from backend:
    python -m scripts.install_auction_factor_pack --data-dir D:/TSP/data

The pack is deliberately experimental. It measures order-book pressure,
matched-volume acceleration, and auction participation relative to history.
Its draft directions come from a 2025-2026 fit and a 2020-2024 IC check; the
checked close-to-close long-short returns were negative, so it is not deployable.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from app.factors.ext_factors import ensure_synced
from app.factors.registry import get_factor
from app.factors.store import load_all, register_definition, save_one

FACTOR_DEFINITIONS = (
    {
        "id": "uf_auction_tail_imbalance",
        "kind": "custom",
        "label": "竞价尾段买卖失衡",
        "group": "竞价",
        "formula": "ext_auction_preopen_last_imbalance",
        "description": (
            "09:25前最后快照的(买方未匹配-卖方未匹配)/(匹配+双方未匹配)。"
            "正值偏买，负值偏卖；仅表示申报压力，不保证收益方向。"
        ),
        "direction": "high",
        "status": "draft",
    },
    {
        "id": "uf_auction_tail_match_growth",
        "kind": "custom",
        "label": "竞价末分钟匹配加速",
        "group": "竞价",
        "formula": "ext_auction_preopen_last_minute_matched_growth",
        "description": "09:24至最后竞价快照的虚拟匹配量增速，衡量尾段参与突增。",
        "direction": "low",
        "status": "draft",
    },
    {
        "id": "uf_auction_post0920_match_growth",
        "kind": "custom",
        "label": "09:20后匹配增长",
        "group": "竞价",
        "formula": "ext_auction_preopen_post0920_matched_growth",
        "description": (
            "09:20至最后快照的匹配量增速。09:20后不可撤单，"
            "更接近新增申报带来的匹配变化。"
        ),
        "direction": "low",
        "status": "draft",
    },
    {
        "id": "uf_auction_volume_vs_prev",
        "kind": "custom",
        "label": "竞价量占昨日成交",
        "group": "竞价",
        "formula": "ext_auction_result_volume_shares / (ts_delay(volume, 1) * 100)",
        "description": (
            "最终竞价成交量(股) / 前一交易日全天成交量(股)。"
            "只使用09:25前可知信息，不引用当日收盘成交量。"
        ),
        "direction": "low",
        "status": "draft",
    },
    {
        "id": "uf_auction_volume_surprise",
        "kind": "custom",
        "label": "竞价量20日惊喜",
        "group": "竞价",
        "formula": (
            "ext_auction_result_volume_shares / "
            "ts_mean(ext_auction_result_volume_shares, 20)"
        ),
        "description": "最终竞价成交量 / 近20个交易日竞价成交量均值，衡量相对放量。",
        "direction": "low",
        "status": "draft",
    },
)

COMPOSITE_ID = "cf_auction_resonance"
COMPOSITE_DEFINITION = {
    "id": COMPOSITE_ID,
    "kind": "composite",
    "label": "竞价偏买不拥挤(实验)",
    "group": "竞价",
    "members": {
        "uf_auction_tail_imbalance": 0.35,
        "uf_auction_post0920_match_growth": -0.30,
        "uf_auction_volume_vs_prev": -0.20,
        "uf_auction_volume_surprise": -0.15,
    },
    "description": (
        "买方未匹配占优加分；匹配过度加速和竞价相对放量减分。"
        "方向来自2025-2026训练段，仍须用更早样本和成交约束验证。"
    ),
    "direction": "high",
    "status": "draft",
}
FACTOR_IDS = tuple(item["id"] for item in FACTOR_DEFINITIONS)
_SEMANTIC_KEYS = (
    "kind", "label", "group", "formula", "members", "description", "direction", "status",
)


def _semantic(definition: dict) -> dict:
    return {key: definition.get(key) for key in _SEMANTIC_KEYS}


def install(data_dir: Path) -> dict[str, int]:
    data_dir = Path(data_dir)
    ensure_synced(data_dir)
    existing = {str(item["id"]): item for item in load_all(data_dir)}
    created = updated = unchanged = 0
    now = datetime.now().isoformat(timespec="seconds")
    for desired in (*FACTOR_DEFINITIONS, COMPOSITE_DEFINITION):
        current = existing.get(desired["id"])
        if current is not None and _semantic(current) == _semantic(desired):
            registered = get_factor(str(current["id"]))
            if registered is None or registered.version < int(current.get("version", 1)):
                register_definition(current)
            unchanged += 1
            continue
        definition = dict(desired)
        if current is None:
            definition.update(version=1, created_at=now, updated_at=now)
            created += 1
        else:
            definition.update(
                version=int(current.get("version", 1)) + 1,
                created_at=current.get("created_at", now),
                updated_at=now,
            )
            updated += 1
        register_definition(definition)
        save_one(data_dir, definition)
    return {"created": created, "updated": updated, "unchanged": unchanged}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(install(args.data_dir), ensure_ascii=False))


if __name__ == "__main__":
    main()
