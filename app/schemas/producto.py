from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EstadoProducto(str, Enum):
    disponible = "disponible"
    agotado = "agotado"


class ProductoCreate(BaseModel):
    nombre: str = Field(min_length=1, max_length=150)
    categoria_id: int
    precio: int = Field(gt=0)
    estado: EstadoProducto = EstadoProducto.disponible
    sabor: str | None = Field(default=None, max_length=50)
    tamano: str | None = Field(default=None, max_length=50)

    @field_validator("nombre")
    @classmethod
    def validar_nombre(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("nombre no puede estar vacío")
        return v

    @field_validator("sabor", "tamano")
    @classmethod
    def normalizar_opcional(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        return v or None


class ProductoUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=150)
    categoria_id: int | None = None
    precio: int | None = Field(default=None, gt=0)
    estado: EstadoProducto | None = None
    sabor: str | None = Field(default=None, max_length=50)
    tamano: str | None = Field(default=None, max_length=50)

    @field_validator("nombre")
    @classmethod
    def validar_nombre(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("nombre no puede estar vacío")
        return v

    @field_validator("sabor", "tamano")
    @classmethod
    def normalizar_opcional(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        return v or None


class ProductoOut(BaseModel):
    id: int
    nombre: str
    categoria_id: int
    precio: int
    estado: EstadoProducto
    sabor: str | None
    tamano: str | None
    creado_en: datetime

    model_config = ConfigDict(from_attributes=True)
