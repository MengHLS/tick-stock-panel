"""手动数据同步入口开关。

自动调度在启动时读取一次偏好并决定是否注册；这里的门控只服务手动入口
(HTTP / AI 工具)，按当前偏好立即生效，避免关闭后仍能绕过。
"""
from __future__ import annotations

from typing import Literal

from app.services import preferences

DataSyncKind = Literal["pipeline", "ext_pull", "financial"]

_PREF_KEYS: dict[str, str] = {
    "pipeline": "data_sync_pipeline_enabled",
    "ext_pull": "data_sync_ext_pull_enabled",
    "financial": "data_sync_financial_enabled",
}

_LABELS: dict[str, str] = {
    "pipeline": "盘后数据同步",
    "ext_pull": "扩展数据拉取",
    "financial": "财务数据同步",
}


class DataSyncDisabledError(RuntimeError):
    """手动数据同步入口被系统设置关闭。"""

    def __init__(self, kind: DataSyncKind) -> None:
        self.kind = kind
        super().__init__(
            f"{_LABELS[kind]}已在设置中关闭，请在设置 → 系统设置 → 数据同步与调度中开启并重启服务"
        )


def ensure_enabled(kind: DataSyncKind) -> None:
    """关闭时抛 DataSyncDisabledError，由应用异常处理器统一映射为 409。"""
    if not preferences.get_data_sync_prefs()[_PREF_KEYS[kind]]:
        raise DataSyncDisabledError(kind)
