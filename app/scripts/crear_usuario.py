"""Crea o actualiza el usuario administrador de BrainFreeze.

No existe endpoint público de registro (BE-008): este script es la única
forma soportada de dar de alta o cambiar la contraseña del usuario que
inicia sesión en el sistema.

Uso (desde backend/, con el venv activado):
    python -m app.scripts.crear_usuario admin@brainfreeze.com "MiPassword123"

Si el email ya existe, actualiza su contraseña (upsert); si no existe, lo crea.
"""

from __future__ import annotations

import argparse
import sys

from app.core.security import hash_password
from app.db.base_all import Base
from app.db.session import SessionLocal, engine
from app.models.usuario import Usuario


def crear_o_actualizar_usuario(email: str, password: str) -> None:
    email = email.strip().lower()
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        usuario = db.query(Usuario).filter(Usuario.email == email).first()
        if usuario is None:
            usuario = Usuario(email=email, password_hash=hash_password(password))
            db.add(usuario)
            accion = "creado"
        else:
            usuario.password_hash = hash_password(password)
            accion = "actualizado"
        db.commit()
        print(f"Usuario '{email}' {accion} correctamente.")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Crea o actualiza la contraseña del usuario administrador de BrainFreeze."
    )
    parser.add_argument("email")
    parser.add_argument("password")
    args = parser.parse_args()

    if len(args.password) < 6:
        print("La contraseña debe tener al menos 6 caracteres.", file=sys.stderr)
        raise SystemExit(1)

    crear_o_actualizar_usuario(args.email, args.password)


if __name__ == "__main__":
    main()
