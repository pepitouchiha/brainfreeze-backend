from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

ESTADO_DISPONIBLE = "disponible"
ESTADO_AGOTADO = "agotado"


class Producto(Base):
    __tablename__ = "productos"
    __table_args__ = (
        CheckConstraint(
            f"estado IN ('{ESTADO_DISPONIBLE}', '{ESTADO_AGOTADO}')", name="ck_productos_estado"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categorias.id"), nullable=False)
    precio: Mapped[int] = mapped_column(Integer, nullable=False)
    estado: Mapped[str] = mapped_column(String(10), nullable=False, default=ESTADO_DISPONIBLE)
    sabor: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tamano: Mapped[str | None] = mapped_column(String(50), nullable=True)
    imagen_base64: Mapped[str | None] = mapped_column(Text, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
