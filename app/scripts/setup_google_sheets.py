"""Autoriza el acceso de BrainFreeze a Google Sheets con tu cuenta personal.

Corre este script una sola vez, de forma interactiva (abre el navegador para
que inicies sesión con tu cuenta de Gmail y autorices el acceso). Requiere
tener `credentials.json` (OAuth client ID tipo "Aplicación de escritorio",
generado en Google Cloud Console) en la raíz de `backend/` — o en la ruta
indicada por `SHEETS_CREDENTIALS_FILE` en tu `.env`.

Al terminar, guarda `authorized_user.json` con el token de acceso, que el
backend reutiliza en cada venta sin volver a interactuar con un navegador.

Uso (desde backend/, con el venv activado):
    python -m app.scripts.setup_google_sheets
"""

from __future__ import annotations

import sys

import gspread

from app.core import config


def main() -> None:
    if not config.SHEETS_CREDENTIALS_FILE.exists():
        print(
            f"No se encontró '{config.SHEETS_CREDENTIALS_FILE}'. Genera un OAuth "
            "client ID tipo 'Aplicación de escritorio' en Google Cloud Console "
            "con tu cuenta personal de Gmail, descarga el JSON y guárdalo en esa "
            "ruta (o ajusta SHEETS_CREDENTIALS_FILE en tu .env).",
            file=sys.stderr,
        )
        raise SystemExit(1)

    gspread.oauth(
        credentials_filename=str(config.SHEETS_CREDENTIALS_FILE),
        authorized_user_filename=str(config.SHEETS_AUTHORIZED_USER_FILE),
    )

    print(
        "Autenticación completa. 'authorized_user.json' guardado en "
        f"'{config.SHEETS_AUTHORIZED_USER_FILE}'. Ya puedes activar "
        "SHEETS_SYNC_ENABLED=true en tu .env."
    )


if __name__ == "__main__":
    main()
