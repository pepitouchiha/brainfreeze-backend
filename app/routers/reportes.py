from __future__ import annotations

from datetime import date, datetime, time

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import require_auth
from app.db.session import get_db
from app.models.venta import Venta
from app.routers.insumos import listar_insumos
from app.schemas.insumo import InsumoOut
from app.schemas.reporte import ReporteHoyOut, ReporteMensualOut, VentaPorHora, VentaPorMes

router = APIRouter(prefix="/reportes", tags=["reportes"], dependencies=[Depends(require_auth)])


def _ultimos_n_meses(n: int, referencia: date) -> list[tuple[int, int]]:
    meses: list[tuple[int, int]] = []
    anio, mes = referencia.year, referencia.month
    for _ in range(n):
        meses.append((anio, mes))
        mes -= 1
        if mes == 0:
            mes = 12
            anio -= 1
    meses.reverse()
    return meses


@router.get("/hoy", response_model=ReporteHoyOut)
def reporte_hoy(db: Session = Depends(get_db)) -> ReporteHoyOut:
    hoy = date.today()
    ventas = (
        db.query(Venta)
        .filter(Venta.creado_en >= datetime.combine(hoy, time.min))
        .filter(Venta.creado_en <= datetime.combine(hoy, time.max))
        .all()
    )

    por_hora: dict[int, dict[str, int]] = {h: {"total": 0, "num_ventas": 0} for h in range(24)}
    for venta in ventas:
        bucket = por_hora[venta.creado_en.hour]
        bucket["total"] += venta.total
        bucket["num_ventas"] += 1

    return ReporteHoyOut(
        fecha=hoy,
        total=sum(v.total for v in ventas),
        num_ventas=len(ventas),
        por_hora=[
            VentaPorHora(hora=hora, total=datos["total"], num_ventas=datos["num_ventas"])
            for hora, datos in sorted(por_hora.items())
        ],
    )


@router.get("/mensual", response_model=ReporteMensualOut)
def reporte_mensual(
    meses: int = Query(default=12, ge=1, le=60),
    db: Session = Depends(get_db),
) -> ReporteMensualOut:
    hoy = date.today()
    meses_solicitados = _ultimos_n_meses(meses, hoy)
    anio_min = meses_solicitados[0][0]

    filas = (
        db.query(
            func.strftime("%Y", Venta.creado_en).label("anio"),
            func.strftime("%m", Venta.creado_en).label("mes"),
            func.sum(Venta.total).label("total"),
            func.count(Venta.id).label("num_ventas"),
        )
        .filter(Venta.creado_en >= datetime(anio_min, 1, 1))
        .group_by("anio", "mes")
        .all()
    )
    agregados = {(int(fila.anio), int(fila.mes)): (fila.total or 0, fila.num_ventas) for fila in filas}

    salida: list[VentaPorMes] = []
    for anio, mes in meses_solicitados:
        total, num_ventas = agregados.get((anio, mes), (0, 0))
        ticket_promedio = total / num_ventas if num_ventas else 0.0
        salida.append(
            VentaPorMes(
                anio=anio,
                mes=mes,
                total=total,
                num_ventas=num_ventas,
                ticket_promedio=ticket_promedio,
            )
        )

    inicio_anio_actual = datetime.combine(date(hoy.year, 1, 1), time.min)
    ytd_total = (
        db.query(func.coalesce(func.sum(Venta.total), 0))
        .filter(Venta.creado_en >= inicio_anio_actual)
        .scalar()
    )

    return ReporteMensualOut(meses=salida, ytd_total=ytd_total or 0)


@router.get("/alertas-stock", response_model=list[InsumoOut])
def reporte_alertas_stock(db: Session = Depends(get_db)) -> list[InsumoOut]:
    return listar_insumos(solo_alertas=True, db=db)
