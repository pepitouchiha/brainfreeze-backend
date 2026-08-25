from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import require_auth
from app.db.session import get_db
from app.models.categoria import Categoria
from app.models.insumo import ESTADO_OK, Insumo, calcular_estado
from app.schemas.insumo import AjusteStock, InsumoCreate, InsumoOut, InsumoUpdate

router = APIRouter(prefix="/insumos", tags=["insumos"], dependencies=[Depends(require_auth)])


def _validar_categoria(db: Session, categoria_id: int) -> None:
    if db.get(Categoria, categoria_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Categoría no encontrada")


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
def crear_insumo(payload: InsumoCreate, db: Session = Depends(get_db)) -> InsumoOut:
    _validar_categoria(db, payload.categoria_id)
    insumo = Insumo(
        nombre=payload.nombre,
        categoria_id=payload.categoria_id,
        stock=payload.stock,
        stock_minimo=payload.stock_minimo,
    )
    db.add(insumo)
    db.commit()
    db.refresh(insumo)
    return _a_out(insumo)


@router.put("/{insumo_id}", response_model=InsumoOut)
@router.patch("/{insumo_id}", response_model=InsumoOut)
def actualizar_insumo(insumo_id: int, payload: InsumoUpdate, db: Session = Depends(get_db)) -> InsumoOut:
    insumo = db.get(Insumo, insumo_id)
    if insumo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Insumo no encontrado")

    if payload.categoria_id is not None:
        _validar_categoria(db, payload.categoria_id)
        insumo.categoria_id = payload.categoria_id
    if payload.nombre is not None:
        insumo.nombre = payload.nombre
    if payload.stock_minimo is not None:
        insumo.stock_minimo = payload.stock_minimo

    db.commit()
    db.refresh(insumo)
    return _a_out(insumo)


@router.post("/{insumo_id}/ajustar-stock", response_model=InsumoOut)
def ajustar_stock(insumo_id: int, payload: AjusteStock, db: Session = Depends(get_db)) -> InsumoOut:
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
    return _a_out(insumo)


@router.delete("/{insumo_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def eliminar_insumo(insumo_id: int, db: Session = Depends(get_db)) -> None:
    insumo = db.get(Insumo, insumo_id)
    if insumo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Insumo no encontrado")
    db.delete(insumo)
    db.commit()
