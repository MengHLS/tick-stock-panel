"""enriched 复权认证 (schema=2): 仅完整历史+全标的验证可签发全局证据。

认证范围收紧要点:
- 证据记录 `scope=full_history_all_symbols` 与内容 manifest (raw/因子/覆盖元数据/
  enriched 每个文件的大小与 sha256)。读取时按内容复核, 同 generation 的原地改写、
  增删分区都会失效; 成本为 O(相关文件字节数), 不再宣称 O(1)。
- 只有全量管道完成校验后才写证据; 增量/局部/实时发布只使旧证据失效, 不补签。
- 因子覆盖必须来自独立覆盖元数据且状态 COMPLETE 才可通过; 无覆盖证据为 UNKNOWN,
  即使代码正确也不能认证 (真实数据缺失需单列依赖)。
- 加载边界用发布时签发的版本令牌做低成本复核; 认证、加载与复核使用同一令牌。
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import polars as pl

QUALITY_SCHEMA_VERSION = 2
QUALITY_SCOPE = "full_history_all_symbols"
QUALITY_ALGORITHM = "price_scale_v2"
QUALITY_STAMP_TEMPLATE = ".enriched_price_quality_{asset}.json"
QUALITY_MANIFEST_TEMPLATE = ".enriched_quality_manifest_{asset}.json"
QUALITY_DIAGNOSTIC_TEMPLATE = ".enriched_price_quality_{asset}.diagnostic.json"
COVERAGE_TEMPLATE = Path("adj_factor") / "coverage_{asset}.json"

MIN_EX_FACTOR = 0.2
MAX_EX_FACTOR = 5.0
DEFAULT_SCALE_RTOL = 1e-4

FACTOR_REQUIRED_COLUMNS = ("symbol", "trade_date", "ex_factor")
PRICE_COLUMNS = ("open", "high", "low", "close")

# 认证过的版本令牌 (进程内): 记录 manifest 内容摘要与 stamp 内容摘要。
_TOKENS: dict[tuple[str, str], dict] = {}


class AdjustmentIntegrityError(RuntimeError):
    """复权链路完整性错误 (消息可直接展示)。"""


class FactorDataError(AdjustmentIntegrityError):
    """复权因子缺失、不可读、非法或冲突。"""


class PriceScaleError(AdjustmentIntegrityError):
    """复权尺度不一致、认证缺失/失效, 或版本未经认证。"""


# ── 因子加载 ─────────────────────────────────────────────────────


def load_adj_factors_strict(
    factor_path: str | Path,
    *,
    symbols: list[str] | None = None,
) -> pl.DataFrame:
    """严格读取复权因子; 不可用状态一律失败, 不允许退化为不复权。"""
    path = Path(factor_path)
    if not path.exists():
        raise FactorDataError(
            f"复权因子文件缺失 ({path.name})，已中止 enriched 生成，避免写出未复权数据"
        )
    try:
        factors = pl.read_parquet(path)
    except Exception as exc:
        raise FactorDataError(
            f"复权因子读取失败 ({path.name}): {exc}; 已中止 enriched 生成"
        ) from exc

    missing = [c for c in FACTOR_REQUIRED_COLUMNS if c not in factors.columns]
    if missing:
        raise FactorDataError(f"复权因子缺少字段: {', '.join(missing)}")
    if factors.is_empty():
        raise FactorDataError("复权因子为空表，已中止 enriched 生成")

    factors = factors.select(*FACTOR_REQUIRED_COLUMNS).with_columns(
        pl.col("symbol").cast(pl.Utf8, strict=False),
        pl.col("trade_date").cast(pl.Date, strict=False),
        pl.col("ex_factor").cast(pl.Float64, strict=False),
    )
    if factors.filter(pl.col("symbol").is_null()).height:
        raise FactorDataError("复权因子存在空 symbol")
    if factors.filter(pl.col("trade_date").is_null()).height:
        raise FactorDataError("复权因子存在空 trade_date")
    bad = factors.filter(
        pl.col("ex_factor").is_null()
        | ~pl.col("ex_factor").is_finite()
        | (pl.col("ex_factor") < MIN_EX_FACTOR)
        | (pl.col("ex_factor") > MAX_EX_FACTOR)
    )
    if bad.height:
        raise FactorDataError(
            f"复权因子存在非法值 (需在 {MIN_EX_FACTOR}~{MAX_EX_FACTOR}): "
            f"{bad.head(3).to_dicts()}"
        )
    dup = (
        factors.group_by(["symbol", "trade_date"])
        .agg(pl.col("ex_factor").n_unique().alias("variants"))
        .filter(pl.col("variants") > 1)
    )
    if dup.height:
        raise FactorDataError(f"同证券同日复权因子冲突: {dup.head(3).to_dicts()}")

    factors = factors.unique(subset=["symbol", "trade_date"], keep="first").sort(
        ["symbol", "trade_date"]
    )
    if symbols:
        factors = factors.filter(pl.col("symbol").is_in(list(symbols)))
    return factors


def factor_fingerprint(factors: pl.DataFrame) -> str:
    if factors.is_empty():
        return hashlib.sha256(b"empty").hexdigest()
    digest = hashlib.sha256()
    for symbol, day, ex_factor in factors.select(
        pl.col("symbol").cast(pl.Utf8),
        pl.col("trade_date").cast(pl.Date).cast(pl.Utf8),
        pl.col("ex_factor").cast(pl.Float64),
    ).sort(["symbol", "trade_date"]).iter_rows():
        digest.update(f"{symbol}|{day}|{float(ex_factor):.12g}\n".encode())
    return digest.hexdigest()


# ── 尺度校验 (含键集合覆盖断言) ──────────────────────────────────


def _attach_expected_scale(frame: pl.DataFrame, factors: pl.DataFrame) -> pl.DataFrame:
    if factors.is_empty():
        return frame.with_columns(pl.lit(1.0).alias("q_expected"))
    cumulative = factors.with_columns(
        pl.col("ex_factor").cum_prod().over("symbol").alias("cum_factor"),
    ).select(pl.col("symbol"), pl.col("trade_date"), pl.col("cum_factor"))
    total = cumulative.group_by("symbol").agg(
        pl.col("cum_factor").last().alias("total_factor")
    )
    ordered = frame.sort(["symbol", "date"]).join_asof(
        cumulative.sort(["symbol", "trade_date"]),
        left_on="date",
        right_on="trade_date",
        by="symbol",
        strategy="backward",
    ).join(total, on="symbol", how="left")
    return ordered.with_columns(
        (pl.col("cum_factor").fill_null(1.0) / pl.col("total_factor").fill_null(1.0))
        .alias("q_expected")
    ).drop(["trade_date", "cum_factor", "total_factor"])


def _keyset_error(name: str, keys: pl.DataFrame) -> PriceScaleError:
    return PriceScaleError(
        f"复权尺度校验键集合不闭合 ({name}, {keys.height} 行): {keys.head(3).to_dicts()}"
    )


def validate_adjusted_scale(
    adjusted: pl.DataFrame,
    raw: pl.DataFrame,
    factors: pl.DataFrame,
    *,
    rtol: float = DEFAULT_SCALE_RTOL,
) -> dict:
    """发布前尺度校验: 键集合闭合 + OHLC 同比例 + 比例等于因子推算值。"""
    if adjusted.is_empty():
        return {"rows": 0, "symbols": 0, "factor_fingerprint": factor_fingerprint(factors)}
    need = ["symbol", "date", *PRICE_COLUMNS]
    for label, frame in (("enriched", adjusted), ("原始价", raw)):
        missing = [c for c in need if c not in frame.columns]
        if missing:
            raise PriceScaleError(f"{label}缺少字段: {', '.join(missing)}")

    adjusted_keys = adjusted.select(
        pl.col("symbol").cast(pl.Utf8), pl.col("date").cast(pl.Date)
    )
    if adjusted_keys.height != adjusted_keys.unique().height:
        raise _keyset_error("enriched 存在重复键", adjusted_keys)

    # 合法停牌过滤后的预期键集合 (与 compute_enriched 同口径)。
    from app.indicators.pipeline import filter_halt_days

    expected_keys = filter_halt_days(raw).select(
        pl.col("symbol").cast(pl.Utf8), pl.col("date").cast(pl.Date)
    ).unique()
    missing_keys = expected_keys.join(adjusted_keys, on=["symbol", "date"], how="anti")
    if missing_keys.height:
        raise _keyset_error("缺少 enriched 行", missing_keys)
    extra_keys = adjusted_keys.join(expected_keys, on=["symbol", "date"], how="anti")
    if extra_keys.height:
        raise _keyset_error("存在多余 enriched 行", extra_keys)

    raw_px = raw.select(
        pl.col("symbol").cast(pl.Utf8),
        pl.col("date").cast(pl.Date),
        *[pl.col(c).cast(pl.Float64).alias(f"raw_{c}") for c in PRICE_COLUMNS],
    )
    adj_px = adjusted.select(
        pl.col("symbol").cast(pl.Utf8),
        pl.col("date").cast(pl.Date),
        *[pl.col(c).cast(pl.Float64).alias(f"adj_{c}") for c in PRICE_COLUMNS],
    )
    joined = adj_px.join(raw_px, on=["symbol", "date"], how="inner")
    if joined.height != adj_px.height:
        raise _keyset_error("enriched 与原始价无法一一匹配", adj_px)

    ratios = joined.with_columns(
        *[(pl.col(f"adj_{c}") / pl.col(f"raw_{c}")).alias(f"q_{c}") for c in PRICE_COLUMNS]
    )
    q_cols = [f"q_{c}" for c in PRICE_COLUMNS]
    invalid = ratios.filter(
        pl.any_horizontal([(pl.col(c) <= 0) | ~pl.col(c).is_finite() for c in q_cols])
    )
    if invalid.height:
        row = invalid.head(1).to_dicts()[0]
        raise PriceScaleError(
            f"复权比例非法: {row['symbol']} {row['date']} "
            f"q={ {c: row[c] for c in q_cols} }"
        )
    inconsistent = ratios.with_columns(
        pl.max_horizontal(*[((pl.col(c) / pl.col("q_close")) - 1).abs() for c in q_cols]).alias("_spread")
    ).filter(pl.col("_spread") > rtol)
    if inconsistent.height:
        row = inconsistent.sort("_spread", descending=True).head(1).to_dicts()[0]
        raise PriceScaleError(
            f"OHLC 复权比例不一致: {row['symbol']} {row['date']} "
            f"q={ {c: row[c] for c in q_cols} }"
        )

    checked = _attach_expected_scale(ratios, factors)
    scale_bad = checked.filter(((pl.col("q_close") / pl.col("q_expected")) - 1).abs().gt(rtol))
    if scale_bad.height:
        row = scale_bad.with_columns(
            ((pl.col("q_close") / pl.col("q_expected")) - 1).abs().alias("_dev")
        ).sort("_dev", descending=True).head(1).to_dicts()[0]
        raise PriceScaleError(
            f"复权尺度与因子不符: {row['symbol']} {row['date']} "
            f"实际 q={row['q_close']:.8g}, 期望 q={row['q_expected']:.8g} "
            f"(无事件跳变或除权幅度与因子不一致)"
        )
    return {
        "rows": checked.height,
        "symbols": int(checked["symbol"].n_unique()),
        "rtol": rtol,
        "factor_fingerprint": factor_fingerprint(factors),
    }


# ── 覆盖元数据 ───────────────────────────────────────────────────


def coverage_path(data_dir: str | Path, asset_type: str = "stock") -> Path:
    return Path(data_dir) / COVERAGE_TEMPLATE.with_name(
        COVERAGE_TEMPLATE.name.format(asset=asset_type)
    )


def load_factor_coverage(data_dir: str | Path, asset_type: str = "stock") -> dict | None:
    """读取独立覆盖元数据; 不存在视为没有可信覆盖 (UNKNOWN)。"""
    path = coverage_path(data_dir, asset_type)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FactorDataError(f"因子覆盖元数据损坏: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise FactorDataError("因子覆盖元数据格式无效")
    return payload


def _coverage_ok(
    coverage: dict | None, symbol: str, start: date, end: date,
) -> tuple[bool, str]:
    if coverage is None:
        return False, "无覆盖元数据(UNKNOWN)"
    basis_text = coverage.get("basis_date")
    basis = date.fromisoformat(basis_text) if basis_text else None
    required_end = max(end, basis) if basis else end
    for record in coverage.get("records") or []:
        if record.get("symbol") != symbol:
            continue
        if record.get("status") != "COMPLETE":
            continue
        try:
            rec_start = date.fromisoformat(str(record.get("start")))
            rec_end = date.fromisoformat(str(record.get("end")))
        except (TypeError, ValueError):
            continue
        if rec_start <= start and rec_end >= required_end:
            return True, "COMPLETE"
    return False, "UNKNOWN/覆盖不足"


# ── 内容 manifest 与证据 ─────────────────────────────────────────


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(data_dir: Path, path: Path) -> str:
    return path.resolve().relative_to(data_dir.resolve()).as_posix()


def _managed_relative_paths(root: Path, asset_type: str) -> list[str]:
    """受管数据集中参与认证的全部文件相对路径 (raw/因子/覆盖/enriched)。"""
    files: list[Path] = []
    for pattern in (
        "kline_daily/**/*.parquet",
        "adj_factor/**/*.parquet",
        "kline_daily_enriched/**/*.parquet" if asset_type == "stock" else f"kline_{asset_type}_enriched/**/*.parquet",
    ):
        files.extend(sorted(root.glob(pattern)))
    coverage = coverage_path(root, asset_type)
    if coverage.exists():
        files.append(coverage)
    return sorted(_relative(root, path) for path in files)


def build_content_manifest(data_dir: str | Path, asset_type: str = "stock") -> list[dict]:
    """列出参与认证的全部文件及内容哈希 (raw/因子/覆盖元数据/enriched)。"""
    root = Path(data_dir).resolve()
    entries = []
    for relative in _managed_relative_paths(root, asset_type):
        path = root / relative
        entries.append({
            "path": relative,
            "size": path.stat().st_size,
            "sha256": _sha256_file(path),
        })
    return entries



def manifest_digest(entries: list[dict]) -> str:
    digest = hashlib.sha256()
    for entry in entries:
        digest.update(f"{entry['path']}|{entry['size']}|{entry['sha256']}\n".encode())
    return digest.hexdigest()


def _atomic_write_json(path: Path, payload: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return hashlib.sha256(data).hexdigest()


def stamp_path(data_dir: str | Path, asset_type: str = "stock") -> Path:
    return Path(data_dir) / QUALITY_STAMP_TEMPLATE.format(asset=asset_type)


def manifest_path(data_dir: str | Path, asset_type: str = "stock") -> Path:
    return Path(data_dir) / QUALITY_MANIFEST_TEMPLATE.format(asset=asset_type)


def invalidate_certification(
    data_dir: str | Path, asset_type: str = "stock", *, reason: str = "",
) -> None:
    """任何内容变更前先失效旧证据; 增量/局部模式更新后不补签。"""
    root = Path(data_dir)
    stamp_path(root, asset_type).unlink(missing_ok=True)
    manifest_path(root, asset_type).unlink(missing_ok=True)
    _TOKENS.pop((str(root.resolve()), asset_type), None)
    if reason:
        diagnostic = {
            "schema_version": QUALITY_SCHEMA_VERSION,
            "asset_type": asset_type,
            "certified": False,
            "reason": reason,
            "algorithm": QUALITY_ALGORITHM,
        }
        _atomic_write_json(
            root / QUALITY_DIAGNOSTIC_TEMPLATE.format(asset=asset_type), diagnostic,
        )


def certify_full_history(
    data_dir: str | Path,
    asset_type: str,
    *,
    symbols_with_dates: dict[str, tuple[date, date]],
    factors: pl.DataFrame,
    source_generation: str | None = None,
) -> dict | None:
    """全历史+全标的完整验证后才签发全局证据; 覆盖未知则拒绝并留诊断。"""
    root = Path(data_dir)
    coverage = load_factor_coverage(root, asset_type)
    missing: list[dict] = []
    for symbol, (start, end) in sorted(symbols_with_dates.items()):
        ok, reason = _coverage_ok(coverage, symbol, start, end)
        if not ok:
            missing.append({"symbol": symbol, "start": str(start), "end": str(end), "reason": reason})
    if missing:
        invalidate_certification(
            root, asset_type,
            reason=f"因子覆盖未知/不足: {missing[:5]}",
        )
        return None

    from app.enriched_generation import (
        _exclusive_generation_lock,
        enriched_publication_incomplete,
    )

    with _exclusive_generation_lock(root, asset_type):
        if enriched_publication_incomplete(root, asset_type):
            raise PriceScaleError("enriched 仍在发布中，拒绝签发认证证据")
        return _certify_full_history_locked(
            root, asset_type,
            symbols_with_dates=symbols_with_dates,
            factors=factors,
            source_generation=source_generation,
            coverage=coverage,
        )


def _certify_full_history_locked(
    root: Path,
    asset_type: str,
    *,
    symbols_with_dates: dict[str, tuple[date, date]],
    factors: pl.DataFrame,
    source_generation: str | None,
    coverage: dict | None,
) -> dict | None:
    from app.enriched_generation import get_enriched_generation

    generation = get_enriched_generation(root, asset_type)
    if source_generation and generation != source_generation:
        invalidate_certification(root, asset_type, reason="发布 generation 与认证输入不一致")
        return None

    entries = build_content_manifest(root, asset_type)
    digest = manifest_digest(entries)
    manifest_file = manifest_path(root, asset_type)
    _atomic_write_json(manifest_file, {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "algorithm": QUALITY_ALGORITHM,
        "asset_type": asset_type,
        "generation": generation,
        "files": entries,
    })
    symbol_digest = hashlib.sha256(
        "\n".join(sorted(symbols_with_dates)).encode()
    ).hexdigest()
    stamp = {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "scope": QUALITY_SCOPE,
        "algorithm": QUALITY_ALGORITHM,
        "asset_type": asset_type,
        "generation": generation,
        "manifest_path": manifest_file.name,
        "manifest_sha256": digest,
        "symbols_sha256": symbol_digest,
        "symbols": len(symbols_with_dates),
        "date_start": str(min(value[0] for value in symbols_with_dates.values())),
        "date_end": str(max(value[1] for value in symbols_with_dates.values())),
        "factor_fingerprint": factor_fingerprint(factors),
        "coverage_source": (coverage or {}).get("source"),
        "coverage_acquired_at": (coverage or {}).get("acquired_at"),
        "created_at": _now_iso(),
    }
    stamp_sha = _atomic_write_json(stamp_path(root, asset_type), stamp)
    _TOKENS[(str(root.resolve()), asset_type)] = {
        "generation": generation,
        "manifest_sha256": digest,
        "stamp_sha256": stamp_sha,
    }
    (root / QUALITY_DIAGNOSTIC_TEMPLATE.format(asset=asset_type)).unlink(missing_ok=True)
    return stamp


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat(timespec="seconds")


def _read_json(path: Path) -> dict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise PriceScaleError(f"认证文件损坏: {path.name} ({exc})") from exc
    if not isinstance(payload, dict):
        raise PriceScaleError(f"认证文件格式无效: {path.name}")
    return payload


def read_quality_stamp(data_dir: str | Path, asset_type: str = "stock") -> dict | None:
    stamp = _read_json(stamp_path(data_dir, asset_type))
    if stamp is None:
        return None
    if stamp.get("schema_version") != QUALITY_SCHEMA_VERSION:
        raise PriceScaleError("认证证据版本不受支持，拒绝使用该版本数据")
    if stamp.get("scope") != QUALITY_SCOPE:
        raise PriceScaleError("认证证据范围不是完整历史+全标的，拒绝使用该版本数据")
    return stamp


def verify_certification(data_dir: str | Path, asset_type: str = "stock") -> dict:
    """按内容复核全局证据 (O 文件字节数), 通过后签发进程内版本令牌。"""
    from app.enriched_generation import enriched_publication_incomplete, get_enriched_generation

    root = Path(data_dir)
    if enriched_publication_incomplete(root, asset_type):
        raise PriceScaleError("enriched 正在发布, 拒绝使用未完成版本回测")
    stamp = read_quality_stamp(root, asset_type)
    if stamp is None:
        raise PriceScaleError(
            "当前 enriched 行情没有完整认证证据 (需全历史+全标的校验)，已拒绝。"
        )
    generation = get_enriched_generation(root, asset_type)
    if not generation or stamp.get("generation") != generation:
        raise PriceScaleError("enriched 版本与认证证据不一致 (generation 已变化)，请重新完整认证")
    manifest = _read_json(manifest_path(root, asset_type))
    if manifest is None:
        raise PriceScaleError("认证 manifest 缺失，拒绝使用")
    entries = manifest.get("files")
    if not isinstance(entries, list):
        raise PriceScaleError("认证 manifest 格式无效")
    manifest_paths = {entry["path"] for entry in entries}
    actual_paths = set(_managed_relative_paths(root, asset_type))
    added = sorted(actual_paths - manifest_paths)
    if added:
        raise PriceScaleError(f"认证后新增文件: {added[:3]}，拒绝使用该版本数据")
    removed = sorted(manifest_paths - actual_paths)
    if removed:
        raise PriceScaleError(f"认证后文件被删除: {removed[:3]}，拒绝使用")

    digest = manifest_digest(entries)
    if digest != stamp.get("manifest_sha256"):
        raise PriceScaleError("认证 manifest 内容与证据指纹不一致，拒绝使用")
    for entry in entries:
        path = root / entry["path"]
        if not path.exists():
            raise PriceScaleError(f"认证后文件被删除: {entry['path']}")
        if path.stat().st_size != entry["size"]:
            raise PriceScaleError(f"认证后文件大小变化: {entry['path']}")
        if _sha256_file(path) != entry["sha256"]:
            raise PriceScaleError(f"认证后文件内容被修改: {entry['path']}")
    stamp_sha = _sha256_file(stamp_path(root, asset_type))
    _TOKENS[(str(root.resolve()), asset_type)] = {
        "generation": generation,
        "manifest_sha256": digest,
        "stamp_sha256": stamp_sha,
    }
    return stamp


@contextmanager
def certification_submission(data_dir: str | Path, asset_type: str = "stock"):
    """最终认证检查+产��登记与发布写入互斥 (同进程写锁 + 发布状态校验)。"""
    from app.enriched_generation import _exclusive_generation_lock

    with _exclusive_generation_lock(Path(data_dir), asset_type):
        yield


def verify_certification_for_generation(
    data_dir: str | Path,
    asset_type: str,
    expected_generation: str,
) -> dict:
    """挖掘任务固定入队版本: 认证必须对应入队 generation, 首次漂移即失败。"""
    stamp = verify_certification(data_dir, asset_type)
    actual = stamp.get("generation")
    if actual != expected_generation:
        raise PriceScaleError(
            f"入队数据版本 {expected_generation} 与当前已认证版本 {actual} 不一致"
        )
    return stamp


def require_active_token(
    data_dir: str | Path,
    asset_type: str = "stock",
    *,
    start: date | None = None,
    end: date | None = None,
) -> dict:
    """加载边界复核: 令牌未变且全部受管内容仍与认证一致才放行。

    内容一致性必须重新核对 (同 generation/同大小的原地改写也要发现), 成本为
    O(受管文件字节数); 这是当前的明确安全取舍。
    """
    from app.enriched_generation import enriched_publication_incomplete, get_enriched_generation

    root = Path(data_dir)
    if enriched_publication_incomplete(root, asset_type):
        raise PriceScaleError("enriched 正在发布, 拒绝加载未完成版本")
    token = _TOKENS.get((str(root.resolve()), asset_type))
    if token is None:
        # 首次/子进程: 先做完整内容复核并签发令牌; 失败即拒绝。
        verify_certification(root, asset_type)
        token = _TOKENS.get((str(root.resolve()), asset_type))
        if token is None:
            raise PriceScaleError("当前数据版本未经完整认证, 拒绝加载")
    stamp = verify_certification(root, asset_type)  # 全内容复核 + 文件集合求差
    generation = get_enriched_generation(root, asset_type)
    if generation != token["generation"]:
        raise PriceScaleError("版本令牌已失效 (generation 变化), 拒绝加载")
    stamp_file = stamp_path(root, asset_type)
    if not stamp_file.exists():
        raise PriceScaleError("认证证据已被移除, 拒绝加载")
    if _sha256_file(stamp_file) != token["stamp_sha256"]:
        raise PriceScaleError("认证证据已变化, 拒绝加载")
    if start is not None or end is not None:
        certified_start = stamp.get("date_start")
        certified_end = stamp.get("date_end")
        if certified_start and certified_end:
            cert_start = date.fromisoformat(certified_start)
            cert_end = date.fromisoformat(certified_end)
            # 只拒绝与认证覆盖完全不相交的请求; 含休市/上市前空白的相邻请求不误拒
            # (认证覆盖的是实际存在的全部受管文件, 额外文件由 manifest 求差拒绝)。
            if start is not None and start > cert_end:
                raise PriceScaleError(f"请求 {start} 晚于已认证范围 {certified_end}，拒绝读取")
            if end is not None and end < cert_start:
                raise PriceScaleError(f"请求 {end} 早于已认证范围 {certified_start}，拒绝读取")
    return token


def require_price_quality(data_dir: str | Path, asset_type: str = "stock") -> dict:
    """产品入口: 完整复核并签发令牌; 调用后同一次运行内加载使用令牌复核。"""
    return verify_certification(data_dir, asset_type)
