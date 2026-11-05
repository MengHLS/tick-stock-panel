"""Request models for the generic theme analyzer extension."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class IndustrySource(BaseModel):
    chain_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    node_ids: list[str] = Field(default_factory=list, max_length=500)


class ThemeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    description: str = Field(default="", max_length=300)
    color: str = Field(default="#F59E0B", pattern=r"^#[0-9A-Fa-f]{6}$")
    symbols: list[str] = Field(default_factory=list, max_length=500)
    industry_source: IndustrySource | None = None

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("主题名称不能为空")
        return stripped

    @field_validator("description")
    @classmethod
    def _strip_description(cls, value: str) -> str:
        return value.strip()


class ThemeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=40)
    description: str | None = Field(default=None, max_length=300)
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    symbols: list[str] | None = Field(default=None, max_length=500)
    industry_source: IndustrySource | None = None

    @field_validator("name")
    @classmethod
    def _strip_optional_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("主题名称不能为空")
        return stripped

    @field_validator("description")
    @classmethod
    def _strip_optional_description(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class StockAddRequest(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=500)

