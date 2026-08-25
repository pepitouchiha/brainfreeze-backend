from __future__ import annotations

from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

ESTADO_CRITICO = "Crítico"
ESTADO_BAJO = "Bajo"
ESTADO_OK = "OK"


def calcular_estado(stock: float, stock_minimo: float) -> str:
    """Deriva el estado del insumo comparando `stock` contra `stock_minimo`.

    Umbrales (replican `tagStyleFor` del mockup):
    - `stock <= 0` -> 'Crítico'
    - `0 < stock <= stock_minimo` -> 'Bajo'
    - `stock > stock_minimo` -> 'OK'
    """
    if stock <= 0:
        return ESTADO_CRITICO
    if stock <= stock_minimo:
        return ESTADO_BAJO
    return ESTADO_OK


class Insumo(Base):
    __tablename__ = "insumos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categorias.id"), nullable=False)
    stock: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    stock_minimo: Mapped[float] = mapped_column(Float, nullable=False, default=0)
