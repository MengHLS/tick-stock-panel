"""Named exit-policy variants sharing one entry and cost model."""

from __future__ import annotations

from dataclasses import dataclass, replace

from .simulator import SimulationConfig


@dataclass(frozen=True)
class ExitVariant:
    name: str
    stop_loss_pct: float
    max_holding_days: int

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("exit variant name is required")
        if not 0 < self.stop_loss_pct < 1:
            raise ValueError("stop_loss_pct must be between zero and one")
        if self.max_holding_days < 1:
            raise ValueError("max_holding_days must be positive")

    def simulation_config(
        self,
        base: SimulationConfig,
    ) -> SimulationConfig:
        return replace(
            base,
            stop_loss_pct=self.stop_loss_pct,
            max_holding_days=self.max_holding_days,
        )


DEFAULT_EXIT_VARIANTS = (
    ExitVariant(
        name="baseline",
        stop_loss_pct=0.06,
        max_holding_days=20,
    ),
    ExitVariant(
        name="time10",
        stop_loss_pct=0.06,
        max_holding_days=10,
    ),
    ExitVariant(
        name="tight4_time10",
        stop_loss_pct=0.04,
        max_holding_days=10,
    ),
    ExitVariant(
        name="wide8_time20",
        stop_loss_pct=0.08,
        max_holding_days=20,
    ),
)


def parse_exit_variants(value: str) -> tuple[ExitVariant, ...]:
    by_name = {variant.name: variant for variant in DEFAULT_EXIT_VARIANTS}
    names = [item.strip() for item in value.split(",") if item.strip()]
    unknown = sorted(set(names) - set(by_name))
    if unknown:
        raise ValueError(f"unknown exit variants: {unknown}")
    if not names:
        raise ValueError("at least one exit variant is required")
    return tuple(by_name[name] for name in names)
