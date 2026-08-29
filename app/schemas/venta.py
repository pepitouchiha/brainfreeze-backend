from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MetodoPago(str, Enum):
    efectivo = "efectivo"
    transferencia = "transferencia"


class VentaItemCreate(BaseModel):
    producto_id: int
    cantidad: int = Field(gt=0)


class VentaCreate(BaseModel):
    items: list[VentaItemCreate]
    metodo_pago: MetodoPago
    mesa_id: int | None = None

    @field_validator("items")
    @classmethod
    def validar_items(cls, v: list[VentaItemCreate]) -> list[VentaItemCreate]:
        if not v:
            raise ValueError("La venta debe tener al menos un item")
        return v


class VentaItemOut(BaseModel):
    id: int
    producto_id: int
    cantidad: int
    precio_unitario: int

    model_config = ConfigDict(from_attributes=True)


class VentaOut(BaseModel):
    id: int
    mesa_id: int | None
    metodo_pago: MetodoPago
    total: int
    creado_en: datetime
    items: list[VentaItemOut]

    model_config = ConfigDict(from_attributes=True)
