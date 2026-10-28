"""已完成策略回测结果的短期缓存与轻量快照存储 (schema_version=1)。

设计约束:
- 保存的是服务端真实完成的原始结果, 不重算、不接受浏览器提交的统计/成交。
- 只保存回测相关配置与 provenance, 不写凭证、本机路径或策略源码。
- 每条记录独立 JSON, 同目录临时文件 + fsync + 原子替换, 失败不留半成品。
- 损坏文件、未知 schema、路径穿越、超额写入都 fail-closed, 互不影响。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
import time
from collections import OrderedDict
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
RESULTS_SUBDIR = Path("user_data") / "strategy_backtest_results"

# 完成运行的短期有界缓存: run_id -> 结果, 保存请求只按 run_id 取。
# 条数与“序列化字节”双重硬预算: 任何时刻累计序列化字节 <= RUN_CACHE_MAX_BYTES
# 且条数 <= RUN_CACHE_MAX_ENTRIES。单条本身超出可保存上限 (MAX_RECORD_BYTES) 或
# 无法序列化时不登记 (只记一个有界的拒绝原因), 不驱逐已有可用缓存; 保存时据此
# 给出“过大/无法序列化”的明确原因, 不误报为“已过期”。
# 注意: 这里的字节是缓存载荷的 JSON 序列化字节预算, 不是进程 RSS 上限。
RUN_CACHE_TTL_SECONDS = 1800.0
RUN_CACHE_MAX_ENTRIES = 32
RUN_CACHE_MAX_BYTES = 128 * 1024 * 1024

# 拒绝原因: 结果太大 (超过单条可保存上限) 或无法序列化。
RUN_REJECT_TOO_LARGE = "too_large"
RUN_REJECT_UNSERIALIZABLE = "unserializable"

MAX_SAVED_RECORDS = 200
MAX_RECORD_BYTES = 64 * 1024 * 1024
MAX_NAME_LENGTH = 120
MAX_PAGE_SIZE = 100

_SAVED_ID_RE = re.compile(r"^[0-9a-f]{16}$")
_SUMMARY_STAT_KEYS = (
    "total_return",
    "annual_return",
    "max_drawdown",
    "sharpe",
    "calmar",
    "win_rate",
    "n_trades",
)


class ResultStoreError(Exception):
    """结果存储的基类错误 (消息可直接给用户看)。"""


class RunResultExpiredError(ResultStoreError):
    """run_id 不在完成缓存中 (未完成、失败、取消或已过期)。"""


class RunResultNotSavableError(ResultStoreError):
    """结果可运行但无法保存 (例如包含无法序列化的内容), 与“过期”区分。"""


class SavedResultNotFoundError(ResultStoreError):
    """saved_id 对应的记录不存在。"""


class SavedResultCorruptError(ResultStoreError):
    """记录文件无法解析或结构损坏。"""


class UnsupportedResultSchemaError(ResultStoreError):
    """记录 schema_version 不受当前版本支持。"""


class SavedResultLimitExceededError(ResultStoreError):
    """记录数量或单条体积超过上限。"""


class InvalidSavedIdError(ValueError):
    """saved_id 格式非法 (同时防止路径穿越)。"""


def _serialized_size(value: Any) -> int | None:
    """结果对象的 JSON 字节数 (与落盘编码一致), 供缓存字节预算使用。

    无法序列化时返回 None (调用方据此拒绝登记并记录原因)。
    """
    try:
        return len(
            json.dumps(
                value, ensure_ascii=False, separators=(",", ":"), default=str,
            ).encode("utf-8")
        )
    except (TypeError, ValueError):
        return None


class CompletedRunCache:
    def __init__(
        self,
        *,
        ttl_seconds: float = RUN_CACHE_TTL_SECONDS,
        max_entries: int = RUN_CACHE_MAX_ENTRIES,
        max_bytes: int = RUN_CACHE_MAX_BYTES,
        max_entry_bytes: int = MAX_RECORD_BYTES,
    ) -> None:
        self._ttl = float(ttl_seconds)
        self._max_entries = int(max_entries)
        self._max_bytes = int(max_bytes)
        self._max_entry_bytes = int(max_entry_bytes)
        self._items: OrderedDict[str, tuple[float, dict]] = OrderedDict()
        self._sizes: dict[str, int] = {}
        self._total_bytes = 0
        # 有界轻量拒绝状态: run_id -> (时间, 原因); 用于保存时给出真实原因。
        self._rejections: OrderedDict[str, tuple[float, str]] = OrderedDict()
        self._lock = threading.Lock()

    def register(self, result: Any) -> str | None:
        if not isinstance(result, dict):
            return None
        if result.get("error"):
            return None
        run_id = result.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            return None
        size = _serialized_size(result)
        now = time.monotonic()
        with self._lock:
            self._prune_locked(now)
            if size is None:
                self._reject_locked(run_id, RUN_REJECT_UNSERIALIZABLE, now)
                return None
            # 单条超过可保存上限 (或超过缓存预算): 不登记, 也不动已有缓存。
            if size > self._max_entry_bytes or size > self._max_bytes:
                self._reject_locked(run_id, RUN_REJECT_TOO_LARGE, now)
                return None
            self._rejections.pop(run_id, None)
            self._drop_locked(run_id)
            # 先按条数与累计字节淘汰最久未用, 再写入, 保证累计字节不超预算。
            while self._items and (
                len(self._items) >= self._max_entries
                or self._total_bytes + size > self._max_bytes
            ):
                oldest, _ = self._items.popitem(last=False)
                self._total_bytes -= self._sizes.pop(oldest, 0)
            self._items[run_id] = (now, result)
            self._sizes[run_id] = size
            self._total_bytes += size
        return run_id

    def rejection_reason(self, run_id: str) -> str | None:
        now = time.monotonic()
        with self._lock:
            self._prune_locked(now)
            item = self._rejections.get(run_id)
            return item[1] if item is not None else None

    def get(self, run_id: str) -> dict | None:
        now = time.monotonic()
        with self._lock:
            self._prune_locked(now)
            item = self._items.get(run_id)
            if item is None:
                return None
            self._items.move_to_end(run_id)
            return item[1]

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self._sizes.clear()
            self._rejections.clear()
            self._total_bytes = 0

    def _reject_locked(self, run_id: str, reason: str, now: float) -> None:
        self._drop_locked(run_id)
        self._rejections[run_id] = (now, reason)
        self._rejections.move_to_end(run_id)
        while len(self._rejections) > self._max_entries:
            self._rejections.popitem(last=False)

    def _drop_locked(self, run_id: str) -> None:
        if self._items.pop(run_id, None) is not None:
            self._total_bytes -= self._sizes.pop(run_id, 0)

    def _prune_locked(self, now: float) -> None:
        expired = [
            run_id
            for run_id, (stamp, _) in self._items.items()
            if now - stamp > self._ttl
        ]
        for run_id in expired:
            self._drop_locked(run_id)
        for run_id, (stamp, _) in list(self._rejections.items()):
            if now - stamp > self._ttl:
                self._rejections.pop(run_id, None)


_CACHE = CompletedRunCache()


def register_completed_run(result: Any) -> str | None:
    """登记一次真实完成的结果; 失败/取消/无 run_id 的不登记。

    完成时间在登记时固定 (即 worker 返回结果时), 不随随后的保存时间漂移。
    结果过大/无法序列化时不登记, 只记录有界拒绝原因供保存时报明确错误。
    """
    if (
        isinstance(result, dict)
        and not result.get("error")
        and isinstance(result.get("run_id"), str)
        and result["run_id"]
    ):
        stored = dict(result)
        stored.setdefault("completed_at", _now_iso())
        return _CACHE.register(stored)
    return _CACHE.register(result)


def get_completed_run(run_id: str) -> dict | None:
    return _CACHE.get(run_id)


def get_run_rejection(run_id: str) -> str | None:
    """返回该 run 未进入缓存的原因 (too_large/unserializable), 无则 None。"""
    return _CACHE.rejection_reason(run_id)


def clear_completed_runs() -> None:
    _CACHE.clear()


def results_dir(data_dir: str | Path) -> Path:
    return Path(data_dir) / RESULTS_SUBDIR


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _summary_stats(stats: dict) -> dict:
    summary = {key: stats.get(key) for key in _SUMMARY_STAT_KEYS if key in stats}
    if "n_trades" not in summary:
        summary["n_trades"] = stats.get("n_trades")
    return summary


def summarize_record(record: dict) -> dict:
    result = record.get("result") or {}
    stats = result.get("stats") or {}
    meta = record.get("meta") or {}
    return {
        "schema_version": record.get("schema_version"),
        "saved_id": record.get("saved_id"),
        "run_id": record.get("run_id"),
        "name": record.get("name"),
        "saved_at": record.get("saved_at"),
        "completed_at": record.get("completed_at"),
        "strategy_id": meta.get("strategy_id"),
        "strategy_name": meta.get("strategy_name"),
        "start": meta.get("start"),
        "end": meta.get("end"),
        "mode": meta.get("mode"),
        "asset_type": meta.get("asset_type"),
        "n_trades": stats.get("n_trades"),
        "total_return": stats.get("total_return"),
        "annual_return": stats.get("annual_return"),
        "max_drawdown": stats.get("max_drawdown"),
        "sharpe": stats.get("sharpe"),
        "win_rate": stats.get("win_rate"),
    }


def _read_record(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SavedResultCorruptError("保存的回测结果文件已损坏，无法读取") from exc
    if not isinstance(payload, dict):
        raise SavedResultCorruptError("保存的回测结果文件格式无效")
    return payload


def _record_path(directory: Path, saved_id: str) -> Path:
    if not isinstance(saved_id, str) or not _SAVED_ID_RE.match(saved_id):
        raise InvalidSavedIdError("无效的结果 ID")
    path = (directory / f"{saved_id}.json").resolve()
    if path.parent != directory.resolve():
        raise InvalidSavedIdError("无效的结果 ID")
    return path


def _iter_record_paths(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(directory.glob("*.json"))


def _find_by_run_id(directory: Path, run_id: str) -> dict | None:
    for path in _iter_record_paths(directory):
        try:
            record = _read_record(path)
        except SavedResultCorruptError:
            continue
        if record.get("run_id") == run_id:
            return record
    return None


def _saved_id_for_run(run_id: str) -> str:
    """由 run_id 派生稳定的 saved_id。

    同一 run 无论并发多少次、落在哪个进程, 都指向同一个文件,
    配合下面的原子 create-if-absent 实现跨线程/跨进程幂等。
    """
    return hashlib.blake2b(run_id.encode("utf-8"), digest_size=8).hexdigest()


def _build_record(
    result: dict,
    *,
    saved_id: str,
    name: str | None,
) -> dict:
    config = result.get("config") or {}
    strategy_info = result.get("strategy_info") or {}
    provenance = result.get("provenance") or {}
    strategy_id = config.get("strategy_id") or strategy_info.get("id")
    return {
        "schema_version": SCHEMA_VERSION,
        "saved_id": saved_id,
        "run_id": result.get("run_id"),
        "name": name,
        "saved_at": _now_iso(),
        # 完成时间来自登记时刻; 不使用保存时刻冒充 (缺失则明确留空)。
        "completed_at": result.get("completed_at"),
        "meta": {
            "strategy_id": strategy_id,
            "strategy_name": strategy_info.get("name") or strategy_id,
            "start": config.get("start"),
            "end": config.get("end"),
            "mode": config.get("mode"),
            "asset_type": config.get("asset_type"),
        },
        "provenance": provenance,
        "result": result,
    }


def _atomic_create(path: Path, payload: dict) -> bool:
    """原子写入一条新记录; 目标已存在时不覆盖, 返回 False。

    先写同目录临时文件并 fsync, 再用硬链接 create-if-absent 落位:
    内容要么完整可见, 要么不存在; 并发方只有一个能成功创建。
    """
    data = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), default=str,
    ).encode("utf-8")
    if len(data) > MAX_RECORD_BYTES:
        raise SavedResultLimitExceededError(
            "本次回测结果过大，超过单条保存上限，无法保存"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=".tmp-result-", suffix=".json",
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(tmp_name, path)
        except FileExistsError:
            return False
        return True
    finally:
        # 链接成功后临时名只是同一 inode 的第二个名字, 删除不影响记录。
        with suppress(OSError):
            os.unlink(tmp_name)


_SAVE_LOCK = threading.Lock()


def save_completed_result(
    data_dir: str | Path,
    *,
    run_id: str,
    name: str | None = None,
) -> dict:
    """保存缓存中的一次完成结果; 同一 run_id 幂等返回已有记录摘要。

    并发保障:
    - 进程内用 _SAVE_LOCK 串行化 "查重 + 限额 + 落盘";
    - 落盘用硬链接 create-if-absent, 即使多进程 (或未来多 worker) 同时保存同一
      run, 也只会产生一条记录, 后到者读到先到者的记录。
    部署现状为单 uvicorn worker (dev.ps1 未启用 --workers), 进程内锁足够约束
    条数上限; create-if-absent 另外兜住跨进程重复。
    """
    if not isinstance(run_id, str) or not run_id:
        raise RunResultExpiredError(
            "本次回测结果已过期或未完成，无法保存，请重新运行回测"
        )
    trimmed = None
    if isinstance(name, str):
        trimmed = name.strip()[:MAX_NAME_LENGTH] or None
    directory = results_dir(data_dir)
    saved_id = _saved_id_for_run(run_id)
    with _SAVE_LOCK:
        existing = _find_by_run_id(directory, run_id)
        if existing is not None:
            return summarize_record(existing)
        result = get_completed_run(run_id)
        if result is None:
            reason = get_run_rejection(run_id)
            if reason == RUN_REJECT_TOO_LARGE:
                raise SavedResultLimitExceededError(
                    "本次回测结果过大，超过可保存上限，无法保存"
                )
            if reason == RUN_REJECT_UNSERIALIZABLE:
                raise RunResultNotSavableError(
                    "本次回测结果包含无法序列化的内容，无法保存"
                )
            raise RunResultExpiredError(
                "本次回测结果已过期或未完成，无法保存，请重新运行回测"
            )
        stored_paths = _iter_record_paths(directory)
        if len(stored_paths) >= MAX_SAVED_RECORDS:
            raise SavedResultLimitExceededError(
                f"已保存的回测结果达到上限（{MAX_SAVED_RECORDS} 条），请先删除旧结果"
            )
        record = _build_record(result, saved_id=saved_id, name=trimmed)
        created = _atomic_create(_record_path(directory, saved_id), record)
        if not created:
            # 另一进程已抢先写入同一 run 的记录 (本进程的锁管不到它)。
            existing = _find_by_run_id(directory, run_id)
            if existing is not None:
                return summarize_record(existing)
            raise ResultStoreError("保存回测结果时发生并发冲突，请重试")
        return summarize_record(record)


def list_saved_results(
    data_dir: str | Path,
    *,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    page = max(int(page), 1)
    page_size = min(max(int(page_size), 1), MAX_PAGE_SIZE)
    directory = results_dir(data_dir)
    items: list[dict] = []
    skipped = 0
    for path in _iter_record_paths(directory):
        try:
            record = _read_record(path)
            if record.get("schema_version") != SCHEMA_VERSION:
                skipped += 1
                continue
            items.append(summarize_record(record))
        except SavedResultCorruptError:
            skipped += 1
            continue
    items.sort(key=lambda item: (item.get("saved_at") or "", item.get("saved_id") or ""), reverse=True)
    total = len(items)
    start = (page - 1) * page_size
    return {
        "items": items[start:start + page_size],
        "page": page,
        "page_size": page_size,
        "total": total,
        "has_more": start + page_size < total,
        "skipped": skipped,
    }


def get_saved_result(data_dir: str | Path, saved_id: str) -> dict:
    directory = results_dir(data_dir)
    path = _record_path(directory, saved_id)
    if not path.exists():
        raise SavedResultNotFoundError("保存的回测结果不存在")
    record = _read_record(path)
    version = record.get("schema_version")
    if version != SCHEMA_VERSION:
        raise UnsupportedResultSchemaError(
            f"保存的结果版本不受支持（{version!r}），请升级后重试"
        )
    return record


def delete_saved_result(data_dir: str | Path, saved_id: str) -> None:
    directory = results_dir(data_dir)
    path = _record_path(directory, saved_id)
    if not path.exists():
        raise SavedResultNotFoundError("保存的回测结果不存在")
    try:
        path.unlink()
    except OSError as exc:
        raise ResultStoreError("删除保存的回测结果失败，请稍后重试") from exc
