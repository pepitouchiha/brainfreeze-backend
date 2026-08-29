"""Sincronización de ventas a Google Sheets (backup/dashboard de solo lectura).

Autenticación OAuth de cuenta personal (`gspread.oauth`), nunca cuenta de
servicio: el dueño autoriza una vez corriendo
`python -m app.scripts.setup_google_sheets` y de ahí en adelante este módulo
reutiliza `authorized_user.json` sin volver a interactuar con un navegador.

Todas las excepciones se capturan y solo se loguean: esta sincronización es
de mejor esfuerzo (backup externo), nunca debe romper el flujo de creación
de una venta ni bloquear el threadpool del servidor con un flujo interactivo.
"""

from __future__ import annotations

import logging
from typing import Any

import gspread
import gspread.exceptions
import google.auth.exceptions
import requests.exceptions

from app.core import config

logger = logging.getLogger(__name__)

_worksheet: gspread.Worksheet | None = None
_headers_checked: bool = False

_HEADERS = ["ID Venta", "Fecha", "Método de pago", "Mesa", "Total", "Productos"]


def _ensure_headers(worksheet: gspread.Worksheet) -> None:
    """Inserta la fila de encabezados si la hoja está vacía.

    Se cachea el intento (no el éxito) vía `_headers_checked`: si esta
    verificación falla, no se reintenta en llamadas posteriores dentro del
    mismo proceso (ver BE-013).
    """
    global _headers_checked

    if _headers_checked:
        return
    _headers_checked = True

    try:
        if not worksheet.acell("A1").value:
            worksheet.insert_row(_HEADERS, index=1)
    except gspread.exceptions.APIError as exc:
        logger.warning(
            "Error de la API de Google Sheets al insertar encabezados: %s", exc
        )
    except google.auth.exceptions.GoogleAuthError as exc:
        logger.warning(
            "Error de autenticación con Google al insertar encabezados en Sheets: %s",
            exc,
        )
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
        logger.warning(
            "Error de red al insertar encabezados en Google Sheets: %s", exc
        )
    except Exception:
        logger.exception("Fallo inesperado al insertar encabezados en Google Sheets")


def _get_worksheet() -> gspread.Worksheet | None:
    global _worksheet

    if _worksheet is not None:
        return _worksheet

    if not config.SHEETS_AUTHORIZED_USER_FILE.exists():
        logger.warning(
            "No se encontró '%s'. Corre 'python -m app.scripts.setup_google_sheets' "
            "una vez para autorizar el acceso a Google Sheets antes de activar "
            "SHEETS_SYNC_ENABLED.",
            config.SHEETS_AUTHORIZED_USER_FILE,
        )
        return None

    client = gspread.oauth(
        credentials_filename=str(config.SHEETS_CREDENTIALS_FILE),
        authorized_user_filename=str(config.SHEETS_AUTHORIZED_USER_FILE),
    )
    spreadsheet = client.open(config.SHEETS_SPREADSHEET_NAME)
    worksheet = spreadsheet.worksheet(config.SHEETS_WORKSHEET_NAME)
    _worksheet = worksheet
    return _worksheet


def sync_venta_to_sheets(venta: dict[str, Any]) -> None:
    try:
        worksheet = _get_worksheet()
        if worksheet is None:
            return

        _ensure_headers(worksheet)

        items_resumen = "; ".join(
            f"{item['nombre_producto']} x{item['cantidad']} (${item['precio_unitario']})"
            for item in venta.get("items", [])
        )
        worksheet.append_row(
            [
                venta.get("id"),
                venta.get("creado_en"),
                venta.get("metodo_pago"),
                venta.get("mesa_id"),
                venta.get("total"),
                items_resumen,
            ]
        )
    except gspread.exceptions.SpreadsheetNotFound:
        logger.warning(
            "No se encontró el spreadsheet '%s' en la cuenta de Google autorizada. "
            "Verifica el nombre o que el archivo exista.",
            config.SHEETS_SPREADSHEET_NAME,
        )
    except gspread.exceptions.WorksheetNotFound:
        logger.warning(
            "No se encontró la hoja '%s' dentro del spreadsheet '%s'.",
            config.SHEETS_WORKSHEET_NAME,
            config.SHEETS_SPREADSHEET_NAME,
        )
    except gspread.exceptions.APIError as exc:
        logger.warning("Error de la API de Google Sheets al sincronizar venta: %s", exc)
    except google.auth.exceptions.GoogleAuthError as exc:
        logger.warning(
            "Error de autenticación con Google al sincronizar venta a Sheets: %s", exc
        )
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
        logger.warning("Error de red al sincronizar venta a Google Sheets: %s", exc)
    except Exception:
        logger.exception("Fallo inesperado al sincronizar venta a Google Sheets")
