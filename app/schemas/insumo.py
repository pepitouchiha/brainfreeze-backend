from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EstadoInsumo(str, Enum):
    critico = "Crítico"
    bajo = "Bajo"
    ok = "OK"


class InsumoCreate(BaseModel):
    nombre: str = Field(min_length=1, max_length=150)
    categoria_id: int
    stock: float = Field(default=0, ge=0)
    stock_minimo: float = Field(default=0, ge=0)

    @field_validator("nombre")
    @classmethod
    def validar_nombre(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("nombre no puede estar vacío")
        return v


class InsumoUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=150)
    categoria_id: int | None = None
    stock_minimo: float | None = Field(default=None, ge=0)

    @field_validator("nombre")
    @classmethod
    def validar_nombre(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("nombre no puede estar vacío")
        return v


class AjusteStock(BaseModel):
    cantidad: float = Field(description="Delta a aplicar al stock actual, positivo o negativo")

    @field_validator("cantidad")
    @classmethod
    def validar_cantidad(cls, v: float) -> float:
        if v == 0:
            raise ValueError("cantidad no puede ser 0")
        return v


class InsumoOut(BaseModel):
    id: int
    nombre: str
    categoria_id: int
    stock: float
    stock_minimo: float
    estado: EstadoInsumo

    model_config = ConfigDict(from_attributes=True)
