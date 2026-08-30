from __future__ import annotations

from datetime import date, datetime, time

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.core.security import require_auth
from app.db.session import get_db
from app.models.producto import Producto
from app.models.venta import Venta, VentaItem
from app.routers.insumos import listar_insumos
from app.schemas.insumo import InsumoOut
from app.schemas.reporte import ReporteHoyOut, ReporteMensualOut, VentaPorHora, VentaPorMes

router = APIRouter(prefix="/reportes", tags=["reportes"], dependencies=[Depends(require_auth)])

# Nota (BE-018): el margen se calcula con el costo ACTUAL de cada producto
# (Producto.costo en el momento de generar el reporte), no un costo histórico
# "congelado" al momento de la venta, ya que VentaItem no guarda costo_unitario
# (mismo tipo de limitación punto-en-el-tiempo-vs-actual que BE-007 documentó
# para timezone). Items cuyo producto no tiene costo definido se excluyen de
# la suma (nunca se asume costo=0) y se señalizan vía *_incompleto=True.


def _margen_query(db: Session):
    return (
        db.query(
            func.coalesce(
                func.sum(
                    case(
                        (
                            Producto.costo.isnot(None),
                            (VentaItem.precio_unitario - Producto.costo) * VentaItem.cantidad,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("margen"),
            func.sum(case((Producto.costo.is_(None), 1), else_=0)).label("items_sin_costo"),
        )
        .join(Venta, VentaItem.venta_id == Venta.id)
        .join(Producto, VentaItem.producto_id == Producto.id)
    )


def _calcular_margen(db: Session, desde: datetime, hasta: datetime | None = None) -> tuple[int, bool]:
    query = _margen_query(db).filter(Venta.creado_en >= desde)
    if hasta is not None:
        query = query.filter(Venta.creado_en <= hasta)
    fila = query.one()
    return int(fila.margen or 0), (fila.items_sin_costo or 0) > 0


def _margen_por_mes(db: Session, desde: datetime) -> dict[tuple[int, int], tuple[int, bool]]:
    filas = (
        _margen_query(db)
        .add_columns(
            func.strftime("%Y", Venta.creado_en).label("anio"),
            func.strftime("%m", Venta.creado_en).label("mes"),
        )
        .filter(Venta.creado_en >= desde)
        .group_by("anio", "mes")
        .all()
    )
    return {
        (int(fila.anio), int(fila.mes)): (int(fila.margen or 0), (fila.items_sin_costo or 0) > 0)
        for fila in filas
    }


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
    inicio = datetime.combine(hoy, time.min)
    fin = datetime.combine(hoy, time.max)
    ventas = (
        db.query(Venta)
        .filter(Venta.creado_en >= inicio)
        .filter(Venta.creado_en <= fin)
        .all()
    )

    por_hora: dict[int, dict[str, int]] = {h: {"total": 0, "num_ventas": 0} for h in range(24)}
    for venta in ventas:
        bucket = por_hora[venta.creado_en.hour]
        bucket["total"] += venta.total
        bucket["num_ventas"] += 1

    margen, margen_incompleto = _calcular_margen(db, inicio, fin)

    return ReporteHoyOut(
        fecha=hoy,
        total=sum(v.total for v in ventas),
        num_ventas=len(ventas),
        por_hora=[
            VentaPorHora(hora=hora, total=datos["total"], num_ventas=datos["num_ventas"])
            for hora, datos in sorted(por_hora.items())
        ],
        margen=margen,
        margen_incompleto=margen_incompleto,
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
    agregados_margen = _margen_por_mes(db, datetime(anio_min, 1, 1))

    salida: list[VentaPorMes] = []
    for anio, mes in meses_solicitados:
        total, num_ventas = agregados.get((anio, mes), (0, 0))
        ticket_promedio = total / num_ventas if num_ventas else 0.0
        margen, margen_incompleto = agregados_margen.get((anio, mes), (0, False))
        salida.append(
            VentaPorMes(
                anio=anio,
                mes=mes,
                total=total,
                num_ventas=num_ventas,
                ticket_promedio=ticket_promedio,
                margen=margen,
                margen_incompleto=margen_incompleto,
            )
        )

    inicio_anio_actual = datetime.combine(date(hoy.year, 1, 1), time.min)
    ytd_total = (
        db.query(func.coalesce(func.sum(Venta.total), 0))
        .filter(Venta.creado_en >= inicio_anio_actual)
        .scalar()
    )
    ytd_margen, ytd_margen_incompleto = _calcular_margen(db, inicio_anio_actual)

    return ReporteMensualOut(
        meses=salida,
        ytd_total=ytd_total or 0,
        ytd_margen=ytd_margen,
        ytd_margen_incompleto=ytd_margen_incompleto,
    )


@router.get("/alertas-stock", response_model=list[InsumoOut])
def reporte_alertas_stock(db: Session = Depends(get_db)) -> list[InsumoOut]:
    return listar_insumos(solo_alertas=True, db=db)
