from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import require_auth
from app.db.session import get_db
from app.models.categoria import Categoria
from app.models.producto import Producto
from app.schemas.producto import ProductoCreate, ProductoOut, ProductoUpdate

router = APIRouter(prefix="/productos", tags=["productos"], dependencies=[Depends(require_auth)])


def _validar_categoria(db: Session, categoria_id: int) -> None:
    if db.get(Categoria, categoria_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Categoría no encontrada")


@router.get("", response_model=list[ProductoOut])
def listar_productos(
    search: str | None = None,
    categoria_id: int | None = None,
    db: Session = Depends(get_db),
) -> list[Producto]:
    query = db.query(Producto)
    if search:
        query = query.filter(func.lower(Producto.nombre).contains(search.strip().lower()))
    if categoria_id is not None:
        query = query.filter(Producto.categoria_id == categoria_id)
    return query.order_by(Producto.nombre).all()


@router.get("/{producto_id}", response_model=ProductoOut)
def obtener_producto(producto_id: int, db: Session = Depends(get_db)) -> Producto:
    producto = db.get(Producto, producto_id)
    if producto is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Producto no encontrado")
    return producto


@router.post("", response_model=ProductoOut, status_code=status.HTTP_201_CREATED)
def crear_producto(payload: ProductoCreate, db: Session = Depends(get_db)) -> Producto:
    _validar_categoria(db, payload.categoria_id)
    producto = Producto(
        nombre=payload.nombre,
        categoria_id=payload.categoria_id,
        precio=payload.precio,
        estado=payload.estado.value,
        sabor=payload.sabor,
        tamano=payload.tamano,
    )
    db.add(producto)
    db.commit()
    db.refresh(producto)
    return producto


@router.put("/{producto_id}", response_model=ProductoOut)
@router.patch("/{producto_id}", response_model=ProductoOut)
def actualizar_producto(
    producto_id: int, payload: ProductoUpdate, db: Session = Depends(get_db)
) -> Producto:
    producto = db.get(Producto, producto_id)
    if producto is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Producto no encontrado")

    if payload.categoria_id is not None:
        _validar_categoria(db, payload.categoria_id)
        producto.categoria_id = payload.categoria_id
    if payload.nombre is not None:
        producto.nombre = payload.nombre
    if payload.precio is not None:
        producto.precio = payload.precio
    if payload.estado is not None:
        producto.estado = payload.estado.value
    if payload.sabor is not None:
        producto.sabor = payload.sabor
    if payload.tamano is not None:
        producto.tamano = payload.tamano

    db.commit()
    db.refresh(producto)
    return producto


@router.delete("/{producto_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def eliminar_producto(producto_id: int, db: Session = Depends(get_db)) -> None:
    producto = db.get(Producto, producto_id)
    if producto is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Producto no encontrado")
    db.delete(producto)
    db.commit()
