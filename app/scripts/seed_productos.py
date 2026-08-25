"""Puebla la base de datos con categorías y productos de ejemplo (granizados).

Idempotente: si una categoría o producto con el mismo nombre ya existe, no lo
duplica (se actualiza el precio/estado del producto existente en vez de
crear otro).

Uso (desde backend/, con el venv activado):
    python -m app.scripts.seed_productos
"""

from __future__ import annotations

from app.db.base_all import Base
from app.db.session import SessionLocal, engine
from app.models.categoria import Categoria
from app.models.producto import ESTADO_DISPONIBLE, Producto

CATEGORIAS = [
    {"nombre": "Granizados", "color": "#22c55e"},
    {"nombre": "Toppings", "color": "#f59e0b"},
    {"nombre": "Bebidas", "color": "#3b82f6"},
]

SABORES_GRANIZADO = ["Fresa", "Mora", "Limón", "Mango", "Uva"]
TAMANOS_GRANIZADO = [
    {"nombre": "Chico", "precio": 5000},
    {"nombre": "Grande", "precio": 8000},
]

TOPPINGS = [
    {"nombre": "Chispas de chocolate", "precio": 1500},
    {"nombre": "Gomitas", "precio": 1500},
    {"nombre": "Crema chantilly", "precio": 2000},
]

BEBIDAS = [
    {"nombre": "Agua en botella", "precio": 2500},
    {"nombre": "Gaseosa", "precio": 3000},
]


def _obtener_o_crear_categoria(db, nombre: str, color: str) -> Categoria:
    categoria = db.query(Categoria).filter(Categoria.nombre == nombre).first()
    if categoria is None:
        categoria = Categoria(nombre=nombre, color=color)
        db.add(categoria)
        db.flush()
    return categoria


def _crear_o_actualizar_producto(
    db,
    nombre: str,
    categoria_id: int,
    precio: int,
    sabor: str | None = None,
    tamano: str | None = None,
) -> None:
    producto = db.query(Producto).filter(Producto.nombre == nombre).first()
    if producto is None:
        producto = Producto(
            nombre=nombre,
            categoria_id=categoria_id,
            precio=precio,
            estado=ESTADO_DISPONIBLE,
            sabor=sabor,
            tamano=tamano,
        )
        db.add(producto)
    else:
        producto.categoria_id = categoria_id
        producto.precio = precio
        producto.sabor = sabor
        producto.tamano = tamano


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        categorias_por_nombre = {
            c["nombre"]: _obtener_o_crear_categoria(db, c["nombre"], c["color"]) for c in CATEGORIAS
        }

        cat_granizados = categorias_por_nombre["Granizados"]
        for sabor in SABORES_GRANIZADO:
            for tamano in TAMANOS_GRANIZADO:
                nombre = f"Granizado {sabor} {tamano['nombre']}"
                _crear_o_actualizar_producto(
                    db,
                    nombre=nombre,
                    categoria_id=cat_granizados.id,
                    precio=tamano["precio"],
                    sabor=sabor,
                    tamano=tamano["nombre"],
                )

        cat_toppings = categorias_por_nombre["Toppings"]
        for topping in TOPPINGS:
            _crear_o_actualizar_producto(
                db,
                nombre=topping["nombre"],
                categoria_id=cat_toppings.id,
                precio=topping["precio"],
            )

        cat_bebidas = categorias_por_nombre["Bebidas"]
        for bebida in BEBIDAS:
            _crear_o_actualizar_producto(
                db,
                nombre=bebida["nombre"],
                categoria_id=cat_bebidas.id,
                precio=bebida["precio"],
            )

        db.commit()
        total_productos = db.query(Producto).count()
        print(
            f"Seed completado: {len(categorias_por_nombre)} categorías, "
            f"{total_productos} productos en la base de datos."
        )
    finally:
        db.close()


if __name__ == "__main__":
    seed()
