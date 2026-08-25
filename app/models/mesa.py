from __future__ import annotations

from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

ESTADO_LIBRE = "libre"
ESTADO_OCUPADA = "ocupada"


class Mesa(Base):
    __tablename__ = "mesas"
    __table_args__ = (
        CheckConstraint(f"estado IN ('{ESTADO_LIBRE}', '{ESTADO_OCUPADA}')", name="ck_mesas_estado"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre_o_numero: Mapped[str] = mapped_column(String(50), nullable=False)
    estado: Mapped[str] = mapped_column(String(10), nullable=False, default=ESTADO_LIBRE)
