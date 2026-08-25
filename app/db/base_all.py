"""Punto único de importación de todos los modelos SQLAlchemy.

Cada tarea que agregue un modelo nuevo (BE-002 en adelante) debe importarlo
aquí para que `Base.metadata.create_all` en app/main.py lo registre y cree la
tabla correspondiente al arrancar el servidor.
"""

from app.db.base import Base  # noqa: F401
from app.models.categoria import Categoria  # noqa: F401
from app.models.insumo import Insumo  # noqa: F401
from app.models.mesa import Mesa  # noqa: F401
from app.models.producto import Producto  # noqa: F401
from app.models.usuario import Usuario  # noqa: F401
from app.models.venta import Venta, VentaItem  # noqa: F401
