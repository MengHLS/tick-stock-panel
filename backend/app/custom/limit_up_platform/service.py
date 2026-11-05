"""Platform limit-up stock pool as extension data.

The public REST route documented by the platform is not deployed on the
current host (it returns the SPA shell). The same read-only data is exposed
by the platform's tRPC endpoint, whose date argument is a JSON query value.
"""
from __future__ import annotations

import logging
from pathlib import Path

from app.services.ext_data import ExtConfig, ExtConfigStore, ExtField, PullConfig
from app.services.fs_utils import atomic_write_text

logger = logging.getLogger(__name__)

CONFIG_ID = "ext_limit_up_platform"
SOURCE_BASE = "https://stockanalyze-vwwjfde6.manus.space"
SOURCE_URL = f"{SOURCE_BASE}/api/trpc/limitUp.getByDate"
DATE_VALUE_TEMPLATE = '{"json":{"date":"{date}"}}'
SEED_MARKER = ".limit_up_platform_seeded_v1"


def limit_up_config() -> ExtConfig:
    """Return the complete, runnable pull recipe for the platform table."""
    return ExtConfig(
        id=CONFIG_ID,
        label="涨停股票池（平台）",
        mode="timeseries",
        description=(
            "平台涨停复盘数据（stockanalyze-vwwjfde6.manus.space）。"
            "按日拉取涨停股票、涨停时间、连板信息、题材与关键词；"
            "流通市值/成交额单位为亿元。工作日盘后定时刷新，支持历史回补。"
        ),
        symbol_map={"type": "mapped", "col": "symbol"},
        code_map={"type": "computed", "from": "symbol", "method": "strip_exchange"},
        pull=PullConfig(
            url=SOURCE_URL,
            method="GET",
            response_path="result.data.json",
            field_map={
                "stockCode": "symbol",
                "stockName": "name",
                "limitUpDate": "date",
                "limitUpTime": "limit_up_time",
                "boardCount": "board_count_text",
                "circulationValue": "circulation_value_yi",
                "turnover": "amount_yi",
                "sector": "sector",
                "keywords": "keywords",
                "createdBy": "created_by",
                "createdAt": "created_at",
                "updatedAt": "updated_at",
            },
            date_param="input",
            date_format="iso",
            date_value_template=DATE_VALUE_TEMPLATE,
            schedule_minutes=60,
            enabled=True,
            time_window_start="15:30",
            time_window_end="23:59",
            schedule_trading_only=True,
            timeout_seconds=30,
            granularity="daily",
        ),
        fields=[
            ExtField("symbol", "string", "标的代码"),
            ExtField("code", "string", "代码"),
            ExtField("date", "string", "涨停日期"),
            ExtField("name", "string", "股票名称"),
            ExtField("limit_up_time", "string", "涨停时间（北京时间）"),
            ExtField("board_count_text", "string", "连板信息"),
            ExtField("circulation_value_yi", "float", "流通市值（亿元）"),
            ExtField("amount_yi", "float", "成交额（亿元）"),
            ExtField("sector", "string", "题材板块"),
            ExtField("keywords", "string", "涨停关键词"),
            ExtField("id", "int", "记录ID"),
            ExtField("created_by", "int", "创建用户ID"),
            ExtField("created_at", "string", "记录创建时间（UTC）"),
            ExtField("updated_at", "string", "记录更新时间（UTC）"),
        ],
    )


def ensure_limit_up_config(data_dir: Path) -> ExtConfig | None:
    """Seed once; deleting the table must not revive it on the next start."""
    data_dir = Path(data_dir)
    store = ExtConfigStore(data_dir)
    config_path = data_dir / "ext_data" / CONFIG_ID / "config.json"
    marker = data_dir / "ext_data" / SEED_MARKER
    config = store.get(CONFIG_ID)
    if config_path.exists() and config is None:
        raise ValueError("Existing extension config is unreadable; refusing to overwrite")
    if config is not None:
        if not marker.exists():
            atomic_write_text(marker, "")
        return config
    if marker.exists():
        return None
    config = limit_up_config()
    store.upsert(config)
    atomic_write_text(marker, "")
    logger.info("扩展表 %s 配置已就绪 (平台涨停股票池)", CONFIG_ID)
    return config
