"""交易计划请求模型与字段约束。"""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PlanStatus = Literal["planned", "entered", "exited", "missed", "cancelled"]
SetupType = Literal[
    "first_board",
    "relay",
    "dip",
    "halfway",
    "reversal",
    "leader_first_yin",
    "other",
]
MarketMood = Literal["ice", "repair", "ferment", "climax", "ebb", "skip"]
HoldingPlan = Literal["intraday", "overnight", "one_two_days", "three_days_plus"]


class PlanInput(BaseModel):
    """一条交易计划。价格均为原始价，收益/风险在服务端换算为百分比点。"""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    plan_date: date
    symbol: str = Field(min_length=1, max_length=24)
    name: str = Field(default="", max_length=40)
    setup: SetupType = "other"
    market_mood: MarketMood = "skip"
    confidence: int = Field(default=3, ge=1, le=5)
    planned_hold: HoldingPlan = "overnight"

    thesis: str = Field(default="", max_length=2000)
    trigger: str = Field(default="", max_length=1000)
    invalidation: str = Field(default="", max_length=1000)

    planned_entry_low: float | None = Field(default=None, gt=0)
    planned_entry_high: float | None = Field(default=None, gt=0)
    stop_loss: float | None = Field(default=None, gt=0)
    target_price: float | None = Field(default=None, gt=0)
    planned_position_pct: float | None = Field(default=None, ge=0, le=100)

    status: PlanStatus = "planned"
    actual_entry_price: float | None = Field(default=None, gt=0)
    entry_at: str | None = Field(
        default=None,
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$",
    )
    actual_position_pct: float | None = Field(default=None, ge=0, le=100)
    actual_exit_price: float | None = Field(default=None, gt=0)
    exit_at: str | None = Field(
        default=None,
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$",
    )
    exit_reason: str | None = Field(default=None, max_length=20)
    review: str = Field(default="", max_length=3000)
    tags: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def validate_plan(self):
        low, high = self.planned_entry_low, self.planned_entry_high
        if low is not None and high is not None and low > high:
            raise ValueError("计划买入区间下限不能高于上限")

        mid = _entry_mid(low, high)
        if mid is not None and self.stop_loss is not None and self.stop_loss >= mid:
            raise ValueError("止损价应低于计划买入价")
        if mid is not None and self.target_price is not None and self.target_price <= mid:
            raise ValueError("目标价应高于计划买入价")

        if self.status in ("entered", "exited") and self.actual_entry_price is None:
            raise ValueError("记录成交状态时需填写实际买入价")
        if self.status == "exited":
            if self.actual_exit_price is None:
                raise ValueError("已结束计划需填写实际卖出价")
            if not self.exit_at:
                raise ValueError("已结束计划需填写卖出时间")
        return self


def _entry_mid(low: float | None, high: float | None) -> float | None:
    if low is not None and high is not None:
        return (low + high) / 2
    return low if low is not None else high


class AnalyzeRequest(BaseModel):
    """AI 执行复盘范围。默认最近 60 条计划。"""

    model_config = ConfigDict(extra="forbid")

    start: date | None = None
    end: date | None = None
    limit: int = Field(default=60, ge=1, le=100)
    focus: str = Field(default="", max_length=1000)


class ReportInput(BaseModel):
    """归档一条 AI 执行复盘。"""

    model_config = ConfigDict(extra="forbid")

    start: str | None = None
    end: str | None = None
    focus: str = Field(default="", max_length=1000)
    content: str = Field(min_length=1, max_length=100_000)
    summary: str = Field(default="", max_length=1000)
    stats: dict = Field(default_factory=dict)
