from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core import config
from app.core.security import require_auth
from app.db.session import get_db
from app.models.categoria import Categoria
from app.models.producto import Producto
from app.schemas.producto import ProductoCreate, ProductoOut, ProductoUpdate
from app.services.sheets_service import sync_producto_to_sheets

router = APIRouter(prefix="/productos", tags=["productos"], dependencies=[Depends(require_auth)])


def _validar_categoria(db: Session, categoria_id: int) -> Categoria:
    categoria = db.get(Categoria, categoria_id)
    if categoria is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Categoría no encontrada")
    return categoria


def _producto_dict_para_sheets(producto: Producto, categoria_nombre: str) -> dict[str, object]:
    return {
        "id": producto.id,
        "nombre": producto.nombre,
        "categoria_nombre": categoria_nombre,
        "precio": producto.precio,
        "costo": producto.costo,
        "estado": producto.estado,
        "sabor": producto.sabor,
        "tamano": producto.tamano,
    }


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
def crear_producto(
    payload: ProductoCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Producto:
    categoria = _validar_categoria(db, payload.categoria_id)
    producto = Producto(
        nombre=payload.nombre,
        categoria_id=payload.categoria_id,
        precio=payload.precio,
        costo=payload.costo,
        estado=payload.estado.value,
        sabor=payload.sabor,
        tamano=payload.tamano,
        imagen_base64=payload.imagen_base64,
    )
    db.add(producto)
    db.commit()
    db.refresh(producto)

    if config.SHEETS_SYNC_ENABLED:
        background_tasks.add_task(
            sync_producto_to_sheets, _producto_dict_para_sheets(producto, categoria.nombre)
        )

    return producto


@router.put("/{producto_id}", response_model=ProductoOut)
@router.patch("/{producto_id}", response_model=ProductoOut)
def actualizar_producto(
    producto_id: int,
    payload: ProductoUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Producto:
    producto = db.get(Producto, producto_id)
    if producto is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Producto no encontrado")

    categoria: Categoria | None = None
    if payload.categoria_id is not None:
        categoria = _validar_categoria(db, payload.categoria_id)
        producto.categoria_id = payload.categoria_id
    if payload.nombre is not None:
        producto.nombre = payload.nombre
    if payload.precio is not None:
        producto.precio = payload.precio
    if payload.estado is not None:
        producto.estado = payload.estado.value

    campos_enviados = payload.model_dump(exclude_unset=True)
    if "sabor" in campos_enviados:
        producto.sabor = payload.sabor
    if "tamano" in campos_enviados:
        producto.tamano = payload.tamano
    if "imagen_base64" in campos_enviados:
        producto.imagen_base64 = payload.imagen_base64
    if "costo" in campos_enviados:
        producto.costo = payload.costo

    db.commit()
    db.refresh(producto)

    if config.SHEETS_SYNC_ENABLED:
        categoria_nombre = (
            categoria.nombre if categoria is not None else _validar_categoria(db, producto.categoria_id).nombre
        )
        background_tasks.add_task(
            sync_producto_to_sheets, _producto_dict_para_sheets(producto, categoria_nombre)
        )

    return producto


@router.delete("/{producto_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def eliminar_producto(producto_id: int, db: Session = Depends(get_db)) -> None:
    producto = db.get(Producto, producto_id)
    if producto is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Producto no encontrado")
    db.delete(producto)
    db.commit()
