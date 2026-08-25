from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict


class VentaPorHora(BaseModel):
    hora: int
    total: int
    num_ventas: int

    model_config = ConfigDict(from_attributes=True)


class ReporteHoyOut(BaseModel):
    fecha: date
    total: int
    num_ventas: int
    por_hora: list[VentaPorHora]

    model_config = ConfigDict(from_attributes=True)


class VentaPorMes(BaseModel):
    anio: int
    mes: int
    total: int
    num_ventas: int
    ticket_promedio: float

    model_config = ConfigDict(from_attributes=True)


class ReporteMensualOut(BaseModel):
    meses: list[VentaPorMes]
    ytd_total: int

    model_config = ConfigDict(from_attributes=True)
