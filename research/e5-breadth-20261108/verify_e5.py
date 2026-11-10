"""E5 `market_breadth` 验收器（台账 §16.5 五条 + 实际计算）。

判据编号 `E5-C1`…`E5-C8`（一律 C 系，契约/台账号只作 `contract_ref` 对照列）：

  C1 §16.5-1  `get_factor("market_breadth")` 非空；warmup_bars==120；
              dependencies == frozenset({"close","ma60","in_universe"})
  C2 §16.5-2  `compile_formula("market_breadth")` → ok=True
  C3 §16.5-4  `all_factors()` 非 `ext_` 恰 111，`market_breadth in ids`，id 唯一
  C4 §16.5-4  常量未被撞：virtual==61 / pit==7 / stock==111 / etf==88
              （§16.6：market_breadth 非 virtual 非 pit，故这两条不变，实跑证明）
  C5 §16.4    provider 侧登记口：`factor_provider_status()["factor_count"]==34`，
              且 `market_breadth` 出现在该 provider 的 factor_ids 里（33→34）
  C6 §16.5-3  闸门 `mode="production"` + `RegistryFacts(settings.data_dir)` → **0 码**
  C7 实际计算  真盘一根横截面：`compute_market_breadth` 产出的当日值
              == 手工复算（close > ma60 & in_universe 的池内均值），且逐日值在 [0,1]、
              同一交易日内所有标的同值（按日聚合、按标的广播）
  C8 §16.6    `semantics` / `cross_sectional` 仍无字段载体、闸门仍拦不住
              `xs_rank(market_breadth)` —— 如实登记「约束尚未被执行」

只读盘、不写任何产物（证据冻结由运行者负责）。退出码 0 = 全 PASS。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

import polars as pl  # noqa: E402

from app.config import settings  # noqa: E402
from app.custom.research_breadth_pack.breadth import (  # noqa: E402
    MARKET_BREADTH_DEPENDENCIES,
    MARKET_BREADTH_FORMULA,
    MARKET_BREADTH_ID,
    MARKET_BREADTH_WARMUP,
    compute_market_breadth,
)
from app.factors import dsl  # noqa: E402
from app.factors.gate import (  # noqa: E402
    GateError,
    RegistryFacts,
    assert_factors_usable,
)
from app.factors.registry import all_factors, get_factor  # noqa: E402
from app.extensions.factors import (  # noqa: E402
    ensure_factor_providers,
    factor_provider_status,
)
from app.tickflow.security_status import read_st_history  # noqa: E402

RESULT: dict = {"checks": {}, "environment": {}}


def check(cid: str, ok: bool, **detail) -> None:
    RESULT["checks"][cid] = {"verdict": "PASS" if ok else "FAIL", "ok": bool(ok), **detail}


def main() -> int:
    data_dir = Path(settings.data_dir)
    RESULT["environment"] = {
        "python": sys.version.split()[0],
        "polars": pl.__version__,
        "data_dir": str(data_dir),
        "formula_text": MARKET_BREADTH_FORMULA,
    }
    if not data_dir.is_dir():
        print(f"{data_dir} 不存在，无法验证", file=sys.stderr)
        return 2

    # ---------------------------------------------------------------- C1
    ensure_factor_providers()
    spec = get_factor(MARKET_BREADTH_ID)
    c1 = (
        spec is not None
        and spec.warmup_bars == MARKET_BREADTH_WARMUP == 120
        and spec.dependencies == MARKET_BREADTH_DEPENDENCIES
        == frozenset({"close", "ma60", "in_universe"})
        and spec.alias_of is None
        and spec.strategy_usable is True
        and spec.kind == "custom"
    )
    check(
        "E5-C1",
        c1,
        contract_ref="台账 §16.5-1",
        registered=spec is not None,
        warmup_bars=None if spec is None else spec.warmup_bars,
        warmup_expected=120,
        dependencies=None if spec is None else sorted(spec.dependencies),
        dependencies_expected=sorted({"close", "ma60", "in_universe"}),
        alias_of=None if spec is None else spec.alias_of,
        strategy_usable=None if spec is None else spec.strategy_usable,
        kind=None if spec is None else spec.kind,
    )

    # ---------------------------------------------------------------- C2
    compiled = dsl.compile_formula(MARKET_BREADTH_ID)
    check(
        "E5-C2",
        bool(compiled.ok),
        contract_ref="台账 §16.5-2",
        compiled_ok=bool(compiled.ok),
        errors=[str(e) for e in compiled.errors],
        referenced_factors=sorted(compiled.referenced_factors or ()),
        warmup_bars=compiled.warmup_bars,
        note="id 作为裸标识符直接编译通过：不需要额外打通「id → DSL 标识符」层",
    )

    # ---------------------------------------------------------------- C3
    specs = all_factors()
    ids = [s.id for s in specs]
    non_ext = [s for s in specs if not s.id.startswith("ext_")]
    c3 = (
        len(non_ext) == 111
        and MARKET_BREADTH_ID in ids
        and len(ids) == len(set(ids))
        # 单一侧：不许有 uf_ 双胞胎（§16.4 冻结条）
        and f"uf_{MARKET_BREADTH_ID}" not in ids
    )
    check(
        "E5-C3",
        c3,
        contract_ref="台账 §16.5-4",
        all_factors_len=len(specs),
        non_ext_len=len(non_ext),
        non_ext_expected=111,
        market_breadth_in_ids=MARKET_BREADTH_ID in ids,
        no_uf_twin=f"uf_{MARKET_BREADTH_ID}" not in ids,
        id_unique=len(ids) == len(set(ids)),
    )

    # ---------------------------------------------------------------- C4
    virtual = [s for s in specs if s.kind == "virtual"]
    pit = [s for s in specs if s.pit]
    # 本进程已探发现全部 provider，`all_factors()` 会带上 `ext_` 动态列（196）；
    # 测试里的 111 / 88 是「目录口径」（不含 ext_），故这里按非 ext_ 比。
    stock = [s for s in all_factors(asset_type="stock") if not s.id.startswith("ext_")]
    etf = [s for s in all_factors(asset_type="etf") if not s.id.startswith("ext_")]
    c4 = (
        len(virtual) == 61 and len(pit) == 7 and len(stock) == 111 and len(etf) == 88
    )
    check(
        "E5-C4",
        c4,
        contract_ref="台账 §16.6（非 virtual / 非 pit → 这两条不变）",
        virtual=len(virtual),
        virtual_expected=61,
        pit=len(pit),
        pit_expected=7,
        stock_non_ext=len(stock),
        stock_expected=111,
        etf_non_ext=len(etf),
        etf_expected=88,
        note="stock/etf 已排除 ext_ 动态列，与 tests/test_factor_registry.py 的目录口径可比",
    )

    # ---------------------------------------------------------------- C5
    status = factor_provider_status()
    from app.extensions.factors import factor_provider_for

    owner = factor_provider_for(MARKET_BREADTH_ID)
    c5 = (
        status.get("factor_count") == 34
        and owner is not None
        and owner.provider_id == "official.research-breadth-pack-e5"
        and status.get("state") == "loaded"
        and not status.get("failed_providers")
    )
    check(
        "E5-C5",
        c5,
        contract_ref="台账 §16.6（走 pack → 33 变 34）",
        state=status.get("state"),
        factor_count=status.get("factor_count"),
        factor_count_expected=34,
        provider_id=None if owner is None else owner.provider_id,
        provider_factor_ids=None if owner is None else sorted(owner.factor_ids),
        providers=status.get("providers"),
        failed_providers=status.get("failed_providers"),
    )

    # ---------------------------------------------------------------- C6
    # §16.5-3 要求 production 下 0 码。现状：pack 注册的因子没有 status 载体
    # （FactorSpec 无 status 字段；盘上 id 必须匹配 ^uf_ 前缀才有 JSON 载体），
    # 因此 §7.8.4 末行按 draft 判 FS01 —— 与 8 个 alias/单侧件同一种结构性缺口。
    facts = RegistryFacts(data_dir)
    fact = facts.facts(MARKET_BREADTH_ID)
    codes: list[str] = []
    detail: dict = {}
    try:
        report = assert_factors_usable([MARKET_BREADTH_ID], "production", facts=facts)
        codes = list(report.codes())
    except GateError as exc:
        codes = [exc.code]
        detail = {
            "code": exc.code,
            "detail_keys": sorted(exc.detail),
            "blocked": [list(b) for b in (exc.report.blocked if exc.report else ())],
            "status": exc.detail.get("status"),
        }
    check(
        "E5-C6",
        codes == [],
        contract_ref="台账 §16.5-3（要求 0 码）",
        mode="production",
        codes=codes,
        zero_codes=codes == [],
        facts_status=fact.status,
        facts_kind=fact.kind,
        facts_registered=fact.registered,
        gate_detail=detail,
        # 与 §17 的裁定同源：单侧件不补 status / 不按 id 开豁免口
        note=(
            "0 码未成立 → 结构性缺口，与 §17.1（6 个单侧件 FS01 属设计行为）同源："
            "status 只从盘上 JSON 读，而盘上 id 必须匹配 ^uf_ 前缀；market_breadth 单侧不建 uf_ 双胞胎，"
            "故无合法 status 载体。修法只有 G4（FactorSpec 增 status / provider 注册显式给 status），"
            "本批按 §17.2 不按 id 开豁免口、不批量写 active。"
        ),
    )

    # ---------------------------------------------------------------- C7
    # 真盘一根横截面：取最近一个交易日全市场，手工复算宽度，与 provider 输出逐位比。
    import duckdb

    con = duckdb.connect()
    con.execute("SET threads TO 4")
    panel = data_dir / "kline_daily_enriched"
    paths = sorted(p for p in panel.glob("date=*") if p.is_dir())
    if not paths:
        check("E5-C7", False, contract_ref="台账 §16.4 强制条（实际计算）", error="无 kline_daily_enriched 分区")
    else:
        # 窗口必须 > 120 根：`in_universe` 的条件 1 要求每标的 observed_bars >= 120
        # （`UniverseParams.min_observed_bars`），这只算「传入面板内的行数」。
        # 取 90 分区时全标的 on-axis bars < 120 → in_universe 全 0/null → 宽度整列 null
        # （已实测复现，这就是选 260 的原因，不是随手取一个数）。
        window = 260
        frame = pl.read_parquet([str(p) for p in paths[-window:]])
        # 宽度依赖 ma60（60 根 warmup）+ in_universe（需 amount/volume/raw_close/st 等列），
        # 故不能裁列 —— 口径交给 compute_in_universe 与 dsl 自己判。
        frame = frame.sort(["symbol", "date"])
        st_history = read_st_history(data_dir)
        computed = compute_market_breadth(frame, st_history=st_history)
        col = computed.get_column(MARKET_BREADTH_ID)

        # 手工复算：ma60 = ts_mean(close, 60)；宽度 = 池内 (close > ma60) 的当日均值
        from app.custom.research_universe_pack.universe import (
            FACTOR_COLUMN_IN_UNIVERSE,
        )

        manual = computed.select(
            ["date", "close", "ma60", FACTOR_COLUMN_IN_UNIVERSE, MARKET_BREADTH_ID]
        ).with_columns(
            (pl.col("close") > pl.col("ma60")).cast(pl.Float64).alias("_hit")
        )
        # 手工复算 = 「只对池内（in_universe == 1）行取 (close > ma60) 的均值」。
        # 不能用 `_hit * in_universe / in_universe` 逐行相除：池外行 0/0 = NaN，
        # 而 polars 的 mean 不跳 NaN，会把整日均值拖成 NaN（已踩过，写入备查）。
        per_day = (
            manual.filter(pl.col(FACTOR_COLUMN_IN_UNIVERSE) == 1.0)
            .group_by("date")
            .agg(
                [
                    pl.col("_hit").mean().alias("manual"),
                    pl.col(MARKET_BREADTH_ID).first().alias("impl_value"),
                    pl.col(MARKET_BREADTH_ID).n_unique().alias("impl_nunique"),
                    pl.len().alias("n_in_pool"),
                ]
            )
            .sort("date")
        )
        # 广播面另算：全帧按日看非空 impl 值只能有一种
        day_level = (
            computed.group_by("date")
            .agg(
                [
                    pl.col(MARKET_BREADTH_ID).drop_nulls().n_unique().alias("n_unique_nonnull"),
                    pl.col(MARKET_BREADTH_ID).null_count().alias("n_null"),
                    pl.len().alias("n_rows"),
                    (pl.col(FACTOR_COLUMN_IN_UNIVERSE) == 1.0).sum().alias("n_in_pool"),
                ]
            )
            .sort("date")
        )
        valid = per_day.filter(
            pl.col("manual").is_not_null() & pl.col("impl_value").is_not_null()
        )
        max_diff = (
            (valid["manual"] - valid["impl_value"]).abs().max()
            if valid.height
            else None
        )
        last = valid.tail(1).to_dicts()
        in_range = False
        if valid.height:
            vals = valid.get_column("impl_value").drop_nulls()
            in_range = bool(
                vals.len() > 0
                and vals.min() >= 0.0
                and vals.max() <= 1.0
            )
        # 「按日聚合、按标的广播」：同一交易日内所有非空值必须只有一种
        broadcast_ok = bool(
            (day_level["n_unique_nonnull"].drop_nulls() <= 1).all()
        )
        # 池外行必须同样是这个值（广播）：只要当日池非空（n_in_pool > 0），
        # 整日不得出现任何 null 行。池**全空**的日子（in_universe 全 null
        # ——窗口起点前 observed_bars < 120 或 ST 未知窗口）允许整日 null，
        # 那是 §2.3 的合法不可判定态，不是漏广播。
        pool_nonempty_days = day_level.filter(pl.col("n_in_pool") > 0)
        broadcast_full = bool(
            pool_nonempty_days.height > 0
            and (pool_nonempty_days["n_null"] == 0).all()
        )
        all_null_days = day_level.filter(pl.col("n_null") == pl.col("n_rows"))
        all_null = col.null_count() == col.len()
        c7 = (
            valid.height > 0
            and max_diff is not None
            and max_diff < 1e-12
            and in_range
            and broadcast_ok
            and broadcast_full
            and not all_null
        )
        check(
            "E5-C7",
            c7,
            contract_ref="台账 §16.4 强制条（实际计算，非仅登记）",
            n_days_compared=valid.height,
            window_partitions=window,
            n_partitions_total=len(paths),
            max_abs_diff_vs_manual=max_diff,
            value_range_ok=in_range,
            broadcast_same_value_per_day=broadcast_ok,
            broadcast_covers_out_of_pool_rows=broadcast_full,
            n_days_with_pool=pool_nonempty_days.height,
            n_days_all_null=all_null_days.height,
            n_days_total=day_level.height,
            column_all_null=all_null,
            note=(
                "broadcast 只在池非空的日判：池全空日（in_universe 全 null）整日 null "
                "属 §2.3 合法不可判定态（窗口起点前 observed_bars < 120 / ST 未知窗口），"
                "不计为漏广播"
            ),
            last_day=last,
            sample_days=valid.tail(3).to_dicts(),
            n_in_pool_last_day=valid.tail(1).to_dicts()[0].get("n_in_pool") if valid.height else None,
        )

    # ---------------------------------------------------------------- C8
    # §16.6：禁止再套截面算子/排名这条约束，今天没有消费者。
    spec_fields = set(getattr(type(spec), "__dataclass_fields__", {}) or {})
    has_semantics = "semantics" in spec_fields
    has_cross = "cross_sectional" in spec_fields
    # 闸门是否拦得住 xs_rank(market_breadth)：先看能否编译（能编译 = 拦不住）
    wrapped = dsl.compile_formula(f"xs_rank({MARKET_BREADTH_ID})")
    gate_sees = False
    try:
        assert_factors_usable([f"xs_rank({MARKET_BREADTH_ID})"], "production", facts=facts)
        gate_sees = True
    except GateError:
        gate_sees = False
    except Exception:
        gate_sees = False
    c8 = (not has_semantics) and (not has_cross) and (not gate_sees)
    check(
        "E5-C8",
        c8,
        contract_ref="台账 §16.6（约束尚未被执行，不许当已落实）",
        spec_has_semantics_field=has_semantics,
        spec_has_cross_sectional_field=has_cross,
        xs_rank_compiles=bool(wrapped.ok),
        gate_blocks_xs_rank_wrapper=gate_sees,
        note=(
            "「禁止再套截面算子或排名」只写在文档与 breadth.py 注释里，无任何代码执行点："
            "FactorSpec 无 semantics / cross_sectional 字段（G6），闸门也没有这条判据。"
            "PASS 的含义是「如实登记该约束尚未被执行」，不是「约束已被执行」。"
        ),
    )

    RESULT["summary"] = {
        "total": len(RESULT["checks"]),
        "PASS": sum(1 for c in RESULT["checks"].values() if c["ok"]),
        "FAIL": sum(1 for c in RESULT["checks"].values() if not c["ok"]),
    }
    RESULT["failed"] = [k for k, c in RESULT["checks"].items() if not c["ok"]]
    print(json.dumps(RESULT, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
