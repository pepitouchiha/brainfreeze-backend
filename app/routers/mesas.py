from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import require_auth
from app.db.session import get_db
from app.models.mesa import ESTADO_LIBRE, Mesa
from app.models.venta import Venta
from app.schemas.mesa import MesaCreate, MesaOut, MesaUpdate

router = APIRouter(prefix="/mesas", tags=["mesas"], dependencies=[Depends(require_auth)])


def _contar_ventas(db: Session, mesa_id: int) -> int:
    return db.query(func.count(Venta.id)).filter(Venta.mesa_id == mesa_id).scalar() or 0


@router.get("", response_model=list[MesaOut])
def listar_mesas(db: Session = Depends(get_db)) -> list[Mesa]:
    return db.query(Mesa).order_by(Mesa.nombre_o_numero).all()


@router.post("", response_model=MesaOut, status_code=status.HTTP_201_CREATED)
def crear_mesa(payload: MesaCreate, db: Session = Depends(get_db)) -> Mesa:
    mesa = Mesa(nombre_o_numero=payload.nombre_o_numero, estado=ESTADO_LIBRE)
    db.add(mesa)
    db.commit()
    db.refresh(mesa)
    return mesa


@router.put("/{mesa_id}", response_model=MesaOut)
@router.patch("/{mesa_id}", response_model=MesaOut)
def actualizar_mesa(mesa_id: int, payload: MesaUpdate, db: Session = Depends(get_db)) -> Mesa:
    mesa = db.get(Mesa, mesa_id)
    if mesa is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Mesa no encontrada")
    mesa.nombre_o_numero = payload.nombre_o_numero
    db.commit()
    db.refresh(mesa)
    return mesa


@router.post("/{mesa_id}/liberar", response_model=MesaOut)
def liberar_mesa(mesa_id: int, db: Session = Depends(get_db)) -> Mesa:
    mesa = db.get(Mesa, mesa_id)
    if mesa is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Mesa no encontrada")
    mesa.estado = ESTADO_LIBRE
    db.commit()
    db.refresh(mesa)
    return mesa


@router.delete("/{mesa_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def eliminar_mesa(mesa_id: int, db: Session = Depends(get_db)) -> None:
    mesa = db.get(Mesa, mesa_id)
    if mesa is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Mesa no encontrada")

    ventas = _contar_ventas(db, mesa_id)
    if ventas:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"No se puede eliminar la mesa: tiene {ventas} venta(s) asociada(s)",
        )

    db.delete(mesa)
    db.commit()
