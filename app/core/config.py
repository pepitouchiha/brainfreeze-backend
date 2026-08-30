from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent

load_dotenv(BASE_DIR / ".env")

DATABASE_URL: str = os.getenv(
    "DATABASE_URL", f"sqlite:///{(BASE_DIR / 'brainfreeze.db').as_posix()}"
)

CORS_ORIGINS: list[str] = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origin.strip()
]

JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "dev-secret-change-me")
JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))

SHEETS_SYNC_ENABLED: bool = os.getenv("SHEETS_SYNC_ENABLED", "false").strip().lower() == "true"
SHEETS_SPREADSHEET_NAME: str = os.getenv("SHEETS_SPREADSHEET_NAME", "BrainFreeze POS")
SHEETS_WORKSHEET_NAME: str = os.getenv("SHEETS_WORKSHEET_NAME", "Ventas_Diarias")
SHEETS_WORKSHEET_CATEGORIAS: str = os.getenv("SHEETS_WORKSHEET_CATEGORIAS", "Categorias")
SHEETS_WORKSHEET_PRODUCTOS: str = os.getenv("SHEETS_WORKSHEET_PRODUCTOS", "Productos")
SHEETS_WORKSHEET_INSUMOS: str = os.getenv("SHEETS_WORKSHEET_INSUMOS", "Insumos")
SHEETS_CREDENTIALS_FILE: Path = Path(
    os.getenv("SHEETS_CREDENTIALS_FILE", str(BASE_DIR / "credentials.json"))
)
SHEETS_AUTHORIZED_USER_FILE: Path = Path(
    os.getenv("SHEETS_AUTHORIZED_USER_FILE", str(BASE_DIR / "authorized_user.json"))
)
