from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import config
from app.core.security import require_auth
from app.db.session import get_db
from app.models.categoria import Categoria
from app.models.insumo import Insumo
from app.models.producto import Producto
from app.schemas.categoria import CategoriaCreate, CategoriaOut, CategoriaUpdate
from app.services.sheets_service import sync_categoria_to_sheets

router = APIRouter(prefix="/categorias", tags=["categorias"], dependencies=[Depends(require_auth)])


def _contar_productos(db: Session, categoria_id: int) -> int:
    return (
        db.query(func.count(Producto.id)).filter(Producto.categoria_id == categoria_id).scalar()
        or 0
    )


def _contar_insumos(db: Session, categoria_id: int) -> int:
    return (
        db.query(func.count(Insumo.id)).filter(Insumo.categoria_id == categoria_id).scalar() or 0
    )


def _a_out(db: Session, categoria: Categoria) -> CategoriaOut:
    return CategoriaOut(
        id=categoria.id,
        nombre=categoria.nombre,
        color=categoria.color,
        productos_count=_contar_productos(db, categoria.id),
    )


@router.get("", response_model=list[CategoriaOut])
def listar_categorias(db: Session = Depends(get_db)) -> list[CategoriaOut]:
    categorias = db.query(Categoria).order_by(Categoria.nombre).all()
    return [_a_out(db, c) for c in categorias]


@router.post("", response_model=CategoriaOut, status_code=status.HTTP_201_CREATED)
def crear_categoria(
    payload: CategoriaCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> CategoriaOut:
    existe = db.query(Categoria).filter(Categoria.nombre == payload.nombre).first()
    if existe:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Ya existe una categoría con ese nombre")
    categoria = Categoria(nombre=payload.nombre, color=payload.color)
    db.add(categoria)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Ya existe una categoría con ese nombre")
    db.refresh(categoria)

    if config.SHEETS_SYNC_ENABLED:
        categoria_dict = {
            "id": categoria.id,
            "nombre": categoria.nombre,
            "color": categoria.color,
        }
        background_tasks.add_task(sync_categoria_to_sheets, categoria_dict)

    return _a_out(db, categoria)


@router.put("/{categoria_id}", response_model=CategoriaOut)
@router.patch("/{categoria_id}", response_model=CategoriaOut)
def actualizar_categoria(
    categoria_id: int,
    payload: CategoriaUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> CategoriaOut:
    categoria = db.get(Categoria, categoria_id)
    if categoria is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Categoría no encontrada")

    if payload.nombre is not None:
        duplicada = (
            db.query(Categoria)
            .filter(Categoria.nombre == payload.nombre, Categoria.id != categoria_id)
            .first()
        )
        if duplicada:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Ya existe una categoría con ese nombre")
        categoria.nombre = payload.nombre

    if payload.color is not None:
        categoria.color = payload.color

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Ya existe una categoría con ese nombre")
    db.refresh(categoria)

    if config.SHEETS_SYNC_ENABLED:
        categoria_dict = {
            "id": categoria.id,
            "nombre": categoria.nombre,
            "color": categoria.color,
        }
        background_tasks.add_task(sync_categoria_to_sheets, categoria_dict)

    return _a_out(db, categoria)


@router.delete("/{categoria_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def eliminar_categoria(categoria_id: int, db: Session = Depends(get_db)) -> None:
    categoria = db.get(Categoria, categoria_id)
    if categoria is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Categoría no encontrada")

    productos = _contar_productos(db, categoria_id)
    insumos = _contar_insumos(db, categoria_id)
    if productos or insumos:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                f"No se puede eliminar la categoría: tiene {productos} producto(s) y "
                f"{insumos} insumo(s) asociados"
            ),
        )

    db.delete(categoria)
    db.commit()
