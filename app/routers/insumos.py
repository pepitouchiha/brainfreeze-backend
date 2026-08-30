from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core import config
from app.core.security import require_auth
from app.db.session import get_db
from app.models.categoria import Categoria
from app.models.insumo import ESTADO_OK, Insumo, calcular_estado
from app.schemas.insumo import AjusteStock, InsumoCreate, InsumoOut, InsumoUpdate
from app.services.sheets_service import sync_insumo_to_sheets

router = APIRouter(prefix="/insumos", tags=["insumos"], dependencies=[Depends(require_auth)])


def _validar_categoria(db: Session, categoria_id: int) -> Categoria:
    categoria = db.get(Categoria, categoria_id)
    if categoria is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Categoría no encontrada")
    return categoria


def _insumo_dict_para_sheets(insumo: Insumo, categoria_nombre: str) -> dict[str, object]:
    return {
        "id": insumo.id,
        "nombre": insumo.nombre,
        "categoria_nombre": categoria_nombre,
        "stock": insumo.stock,
        "stock_minimo": insumo.stock_minimo,
        "estado": calcular_estado(insumo.stock, insumo.stock_minimo),
    }


def _a_out(insumo: Insumo) -> InsumoOut:
    return InsumoOut(
        id=insumo.id,
        nombre=insumo.nombre,
        categoria_id=insumo.categoria_id,
        stock=insumo.stock,
        stock_minimo=insumo.stock_minimo,
        estado=calcular_estado(insumo.stock, insumo.stock_minimo),
    )


@router.get("", response_model=list[InsumoOut])
def listar_insumos(
    solo_alertas: bool = False,
    db: Session = Depends(get_db),
) -> list[InsumoOut]:
    insumos = db.query(Insumo).order_by(Insumo.nombre).all()
    salida = [_a_out(i) for i in insumos]
    if solo_alertas:
        salida = [i for i in salida if i.estado.value != ESTADO_OK]
    return salida


@router.get("/{insumo_id}", response_model=InsumoOut)
def obtener_insumo(insumo_id: int, db: Session = Depends(get_db)) -> InsumoOut:
    insumo = db.get(Insumo, insumo_id)
    if insumo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Insumo no encontrado")
    return _a_out(insumo)


@router.post("", response_model=InsumoOut, status_code=status.HTTP_201_CREATED)
def crear_insumo(
    payload: InsumoCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> InsumoOut:
    categoria = _validar_categoria(db, payload.categoria_id)
    insumo = Insumo(
        nombre=payload.nombre,
        categoria_id=payload.categoria_id,
        stock=payload.stock,
        stock_minimo=payload.stock_minimo,
    )
    db.add(insumo)
    db.commit()
    db.refresh(insumo)

    if config.SHEETS_SYNC_ENABLED:
        background_tasks.add_task(
            sync_insumo_to_sheets, _insumo_dict_para_sheets(insumo, categoria.nombre)
        )

    return _a_out(insumo)


@router.put("/{insumo_id}", response_model=InsumoOut)
@router.patch("/{insumo_id}", response_model=InsumoOut)
def actualizar_insumo(
    insumo_id: int,
    payload: InsumoUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> InsumoOut:
    insumo = db.get(Insumo, insumo_id)
    if insumo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Insumo no encontrado")

    categoria: Categoria | None = None
    if payload.categoria_id is not None:
        categoria = _validar_categoria(db, payload.categoria_id)
        insumo.categoria_id = payload.categoria_id
    if payload.nombre is not None:
        insumo.nombre = payload.nombre
    if payload.stock_minimo is not None:
        insumo.stock_minimo = payload.stock_minimo

    db.commit()
    db.refresh(insumo)

    if config.SHEETS_SYNC_ENABLED:
        categoria_nombre = (
            categoria.nombre if categoria is not None else _validar_categoria(db, insumo.categoria_id).nombre
        )
        background_tasks.add_task(
            sync_insumo_to_sheets, _insumo_dict_para_sheets(insumo, categoria_nombre)
        )

    return _a_out(insumo)


@router.post("/{insumo_id}/ajustar-stock", response_model=InsumoOut)
def ajustar_stock(
    insumo_id: int,
    payload: AjusteStock,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> InsumoOut:
    insumo = db.get(Insumo, insumo_id)
    if insumo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Insumo no encontrado")

    nuevo_stock = insumo.stock + payload.cantidad
    if nuevo_stock < 0:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"El ajuste dejaría el stock en {nuevo_stock}, no puede ser negativo",
        )
    insumo.stock = nuevo_stock
    db.commit()
    db.refresh(insumo)

    if config.SHEETS_SYNC_ENABLED:
        categoria_nombre = _validar_categoria(db, insumo.categoria_id).nombre
        background_tasks.add_task(
            sync_insumo_to_sheets, _insumo_dict_para_sheets(insumo, categoria_nombre)
        )

    return _a_out(insumo)


@router.delete("/{insumo_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def eliminar_insumo(insumo_id: int, db: Session = Depends(get_db)) -> None:
    insumo = db.get(Insumo, insumo_id)
    if insumo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Insumo no encontrado")
    db.delete(insumo)
    db.commit()
