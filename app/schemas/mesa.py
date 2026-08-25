from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EstadoMesa(str, Enum):
    libre = "libre"
    ocupada = "ocupada"


class MesaCreate(BaseModel):
    nombre_o_numero: str = Field(min_length=1, max_length=50)

    @field_validator("nombre_o_numero")
    @classmethod
    def validar_nombre(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("nombre_o_numero no puede estar vacío")
        return v


class MesaUpdate(BaseModel):
    nombre_o_numero: str = Field(min_length=1, max_length=50)

    @field_validator("nombre_o_numero")
    @classmethod
    def validar_nombre(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("nombre_o_numero no puede estar vacío")
        return v


class MesaOut(BaseModel):
    id: int
    nombre_o_numero: str
    estado: EstadoMesa

    model_config = ConfigDict(from_attributes=True)
