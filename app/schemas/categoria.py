from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.categoria import COLOR_DEFAULT

_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


class CategoriaCreate(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    color: str = Field(default=COLOR_DEFAULT, max_length=7)

    @field_validator("nombre")
    @classmethod
    def validar_nombre(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("nombre no puede estar vacío")
        return v

    @field_validator("color")
    @classmethod
    def validar_color(cls, v: str) -> str:
        if not _HEX_COLOR_RE.match(v):
            raise ValueError("color debe ser un hex de 6 dígitos, ej. #22c55e")
        return v


class CategoriaUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=100)
    color: str | None = Field(default=None, max_length=7)

    @field_validator("nombre")
    @classmethod
    def validar_nombre(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("nombre no puede estar vacío")
        return v

    @field_validator("color")
    @classmethod
    def validar_color(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not _HEX_COLOR_RE.match(v):
            raise ValueError("color debe ser un hex de 6 dígitos, ej. #22c55e")
        return v


class CategoriaOut(BaseModel):
    id: int
    nombre: str
    color: str
    productos_count: int

    model_config = ConfigDict(from_attributes=True)
