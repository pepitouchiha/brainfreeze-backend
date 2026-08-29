from __future__ import annotations

from datetime import date, datetime, time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.core import config
from app.core.security import require_auth
from app.db.session import get_db
from app.models.mesa import ESTADO_OCUPADA, Mesa
from app.models.producto import Producto
from app.models.venta import Venta, VentaItem
from app.schemas.venta import VentaCreate, VentaOut
from app.services.sheets_service import sync_venta_to_sheets

router = APIRouter(prefix="/ventas", tags=["ventas"], dependencies=[Depends(require_auth)])


@router.get("", response_model=list[VentaOut])
def listar_ventas(
    desde: date | None = None,
    hasta: date | None = None,
    mesa_id: int | None = None,
    db: Session = Depends(get_db),
) -> list[Venta]:
    query = db.query(Venta).options(joinedload(Venta.items))
    if desde is not None:
        query = query.filter(Venta.creado_en >= datetime.combine(desde, time.min))
    if hasta is not None:
        query = query.filter(Venta.creado_en <= datetime.combine(hasta, time.max))
    if mesa_id is not None:
        query = query.filter(Venta.mesa_id == mesa_id)
    return query.order_by(Venta.creado_en.desc()).all()


@router.post("", response_model=VentaOut, status_code=status.HTTP_201_CREATED)
def crear_venta(
    payload: VentaCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Venta:
    mesa: Mesa | None = None
    if payload.mesa_id is not None:
        mesa = db.get(Mesa, payload.mesa_id)
        if mesa is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Mesa no encontrada")

    productos_por_id: dict[int, Producto] = {}
    for item in payload.items:
        if item.producto_id in productos_por_id:
            continue
        producto = db.get(Producto, item.producto_id)
        if producto is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=f"Producto {item.producto_id} no encontrado",
            )
        productos_por_id[item.producto_id] = producto

    total = 0
    venta_items: list[VentaItem] = []
    for item in payload.items:
        producto = productos_por_id[item.producto_id]
        total += producto.precio * item.cantidad
        venta_items.append(
            VentaItem(
                producto_id=producto.id,
                cantidad=item.cantidad,
                precio_unitario=producto.precio,
            )
        )

    venta = Venta(
        mesa_id=payload.mesa_id,
        metodo_pago=payload.metodo_pago.value,
        total=total,
        items=venta_items,
    )
    db.add(venta)

    if mesa is not None:
        mesa.estado = ESTADO_OCUPADA

    db.commit()
    db.refresh(venta)

    if config.SHEETS_SYNC_ENABLED:
        venta_dict = {
            "id": venta.id,
            "creado_en": venta.creado_en.isoformat(),
            "metodo_pago": venta.metodo_pago,
            "mesa_id": venta.mesa_id,
            "total": venta.total,
            "items": [
                {
                    "producto_id": item.producto_id,
                    "cantidad": item.cantidad,
                    "precio_unitario": item.precio_unitario,
                    "nombre_producto": productos_por_id[item.producto_id].nombre,
                }
                for item in venta.items
            ],
        }
        background_tasks.add_task(sync_venta_to_sheets, venta_dict)

    return venta
