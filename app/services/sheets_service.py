"""Sincronización de datos a Google Sheets (backup/dashboard de solo lectura).

Autenticación OAuth de cuenta personal (`gspread.oauth`), nunca cuenta de
servicio: el dueño autoriza una vez corriendo
`python -m app.scripts.setup_google_sheets` y de ahí en adelante este módulo
reutiliza `authorized_user.json` sin volver a interactuar con un navegador.

El mismo spreadsheet (`config.SHEETS_SPREADSHEET_NAME`) contiene varias hojas,
una por entidad sincronizada. **Ventas** es un log de solo-append (una fila
nueva por cada venta, nunca se sobrescribe una fila existente). **Categorías**,
**Productos** e **Insumos** en cambio reflejan el *estado actual* de cada
registro: una sola fila por ID, actualizada in place vía upsert
(`_upsert_row_by_id`) cuando el registro se crea, edita o (en el caso de
insumos) se le ajusta el stock.

Todas las excepciones se capturan y solo se loguean: esta sincronización es
de mejor esfuerzo (backup externo), nunca debe romper el flujo normal de la
API ni bloquear el threadpool del servidor con un flujo interactivo.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import gspread
import gspread.exceptions
import gspread.utils
import google.auth.exceptions
import requests.exceptions

from app.core import config

logger = logging.getLogger(__name__)

_client: gspread.Client | None = None
_spreadsheet: gspread.Spreadsheet | None = None
_worksheets: dict[str, gspread.Worksheet] = {}
_headers_checked: dict[str, bool] = {}

_HEADERS_VENTAS = ["ID Venta", "Fecha", "Método de pago", "Mesa", "Total", "Productos"]
_HEADERS_CATEGORIAS = ["ID Categoria", "Nombre", "Color"]
_HEADERS_PRODUCTOS = [
    "ID Producto",
    "Nombre",
    "Categoría",
    "Precio",
    "Estado",
    "Sabor",
    "Tamaño",
    "Costo",
]
_HEADERS_INSUMOS = ["ID Insumo", "Nombre", "Categoría", "Stock", "Stock mínimo", "Estado"]

# `gspread.exceptions.CellNotFound` no existe en todas las versiones de la
# librería (en 6.1.2, `Worksheet.find` retorna `None` cuando no hay
# coincidencia en vez de lanzar). Se arma este tuple dinámicamente para
# manejar ambos comportamientos sin romper si la excepción no existe en la
# versión instalada.
_CELL_NOT_FOUND_EXCEPTIONS: tuple[type[Exception], ...] = tuple(
    exc
    for exc in (getattr(gspread.exceptions, "CellNotFound", None),)
    if exc is not None
)


def _columna_a1(numero_columna: int) -> str:
    """Convierte un número de columna (1-based) a su letra A1 (ej. 3 -> 'C')."""
    celda = gspread.utils.rowcol_to_a1(1, numero_columna)
    return re.sub(r"\d+$", "", celda)


def _ensure_headers(worksheet: gspread.Worksheet, headers: list[str]) -> None:
    """Inserta la fila de encabezados si la hoja está vacía.

    Se cachea el intento (no el éxito), por nombre de hoja: si esta
    verificación falla, no se reintenta en llamadas posteriores dentro del
    mismo proceso para esa misma hoja (ver BE-013).
    """
    clave = worksheet.title

    if _headers_checked.get(clave):
        return
    _headers_checked[clave] = True

    try:
        if not worksheet.acell("A1").value:
            worksheet.insert_row(headers, index=1)
    except gspread.exceptions.APIError as exc:
        logger.warning(
            "Error de la API de Google Sheets al insertar encabezados en '%s': %s",
            clave,
            exc,
        )
    except google.auth.exceptions.GoogleAuthError as exc:
        logger.warning(
            "Error de autenticación con Google al insertar encabezados en '%s': %s",
            clave,
            exc,
        )
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
        logger.warning(
            "Error de red al insertar encabezados en la hoja '%s': %s", clave, exc
        )
    except Exception:
        logger.exception(
            "Fallo inesperado al insertar encabezados en la hoja '%s'", clave
        )


def _get_worksheet(worksheet_name: str) -> gspread.Worksheet | None:
    global _client, _spreadsheet

    if worksheet_name in _worksheets:
        return _worksheets[worksheet_name]

    if not config.SHEETS_AUTHORIZED_USER_FILE.exists():
        logger.warning(
            "No se encontró '%s'. Corre 'python -m app.scripts.setup_google_sheets' "
            "una vez para autorizar el acceso a Google Sheets antes de activar "
            "SHEETS_SYNC_ENABLED.",
            config.SHEETS_AUTHORIZED_USER_FILE,
        )
        return None

    if _client is None:
        _client = gspread.oauth(
            credentials_filename=str(config.SHEETS_CREDENTIALS_FILE),
            authorized_user_filename=str(config.SHEETS_AUTHORIZED_USER_FILE),
        )

    if _spreadsheet is None:
        _spreadsheet = _client.open(config.SHEETS_SPREADSHEET_NAME)

    worksheet = _spreadsheet.worksheet(worksheet_name)
    _worksheets[worksheet_name] = worksheet
    return worksheet


def _upsert_row_by_id(
    worksheet: gspread.Worksheet,
    headers: list[str],
    entity_id: Any,
    row_values: list[Any],
) -> None:
    """Inserta o actualiza (in place) la fila cuyo ID está en la columna A.

    Reutilizable por cualquier `sync_*_to_sheets` cuya entidad se identifique
    por un valor único en la primera columna (categorías, productos, insumos
    - a diferencia de ventas, que es append-only y no usa esta función).
    """
    try:
        cell = worksheet.find(str(entity_id), in_column=1)
    except _CELL_NOT_FOUND_EXCEPTIONS:
        cell = None

    if cell is not None:
        ultima_columna = _columna_a1(len(headers))
        worksheet.update([row_values], range_name=f"A{cell.row}:{ultima_columna}{cell.row}")
        return

    _ensure_headers(worksheet, headers)
    worksheet.append_row(row_values)


def sync_venta_to_sheets(venta: dict[str, Any]) -> None:
    try:
        worksheet = _get_worksheet(config.SHEETS_WORKSHEET_NAME)
        if worksheet is None:
            return

        _ensure_headers(worksheet, _HEADERS_VENTAS)

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


def sync_categoria_to_sheets(categoria: dict[str, Any]) -> None:
    try:
        worksheet = _get_worksheet(config.SHEETS_WORKSHEET_CATEGORIAS)
        if worksheet is None:
            return

        row_values = [categoria["id"], categoria["nombre"], categoria["color"]]
        _upsert_row_by_id(worksheet, _HEADERS_CATEGORIAS, categoria["id"], row_values)
    except gspread.exceptions.SpreadsheetNotFound:
        logger.warning(
            "No se encontró el spreadsheet '%s' en la cuenta de Google autorizada. "
            "Verifica el nombre o que el archivo exista.",
            config.SHEETS_SPREADSHEET_NAME,
        )
    except gspread.exceptions.WorksheetNotFound:
        logger.warning(
            "No se encontró la hoja '%s' dentro del spreadsheet '%s'.",
            config.SHEETS_WORKSHEET_CATEGORIAS,
            config.SHEETS_SPREADSHEET_NAME,
        )
    except gspread.exceptions.APIError as exc:
        logger.warning(
            "Error de la API de Google Sheets al sincronizar categoría: %s", exc
        )
    except google.auth.exceptions.GoogleAuthError as exc:
        logger.warning(
            "Error de autenticación con Google al sincronizar categoría a Sheets: %s",
            exc,
        )
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
        logger.warning("Error de red al sincronizar categoría a Google Sheets: %s", exc)
    except Exception:
        logger.exception("Fallo inesperado al sincronizar categoría a Google Sheets")


def sync_producto_to_sheets(producto: dict[str, Any]) -> None:
    try:
        worksheet = _get_worksheet(config.SHEETS_WORKSHEET_PRODUCTOS)
        if worksheet is None:
            return

        row_values = [
            producto["id"],
            producto["nombre"],
            producto["categoria_nombre"],
            producto["precio"],
            producto["estado"],
            producto.get("sabor") or "",
            producto.get("tamano") or "",
            producto.get("costo") if producto.get("costo") is not None else "",
        ]
        _upsert_row_by_id(worksheet, _HEADERS_PRODUCTOS, producto["id"], row_values)
    except gspread.exceptions.SpreadsheetNotFound:
        logger.warning(
            "No se encontró el spreadsheet '%s' en la cuenta de Google autorizada. "
            "Verifica el nombre o que el archivo exista.",
            config.SHEETS_SPREADSHEET_NAME,
        )
    except gspread.exceptions.WorksheetNotFound:
        logger.warning(
            "No se encontró la hoja '%s' dentro del spreadsheet '%s'.",
            config.SHEETS_WORKSHEET_PRODUCTOS,
            config.SHEETS_SPREADSHEET_NAME,
        )
    except gspread.exceptions.APIError as exc:
        logger.warning(
            "Error de la API de Google Sheets al sincronizar producto: %s", exc
        )
    except google.auth.exceptions.GoogleAuthError as exc:
        logger.warning(
            "Error de autenticación con Google al sincronizar producto a Sheets: %s",
            exc,
        )
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
        logger.warning("Error de red al sincronizar producto a Google Sheets: %s", exc)
    except Exception:
        logger.exception("Fallo inesperado al sincronizar producto a Google Sheets")


def sync_insumo_to_sheets(insumo: dict[str, Any]) -> None:
    try:
        worksheet = _get_worksheet(config.SHEETS_WORKSHEET_INSUMOS)
        if worksheet is None:
            return

        row_values = [
            insumo["id"],
            insumo["nombre"],
            insumo["categoria_nombre"],
            insumo["stock"],
            insumo["stock_minimo"],
            insumo["estado"],
        ]
        _upsert_row_by_id(worksheet, _HEADERS_INSUMOS, insumo["id"], row_values)
    except gspread.exceptions.SpreadsheetNotFound:
        logger.warning(
            "No se encontró el spreadsheet '%s' en la cuenta de Google autorizada. "
            "Verifica el nombre o que el archivo exista.",
            config.SHEETS_SPREADSHEET_NAME,
        )
    except gspread.exceptions.WorksheetNotFound:
        logger.warning(
            "No se encontró la hoja '%s' dentro del spreadsheet '%s'.",
            config.SHEETS_WORKSHEET_INSUMOS,
            config.SHEETS_SPREADSHEET_NAME,
        )
    except gspread.exceptions.APIError as exc:
        logger.warning(
            "Error de la API de Google Sheets al sincronizar insumo: %s", exc
        )
    except google.auth.exceptions.GoogleAuthError as exc:
        logger.warning(
            "Error de autenticación con Google al sincronizar insumo a Sheets: %s",
            exc,
        )
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
        logger.warning("Error de red al sincronizar insumo a Google Sheets: %s", exc)
    except Exception:
        logger.exception("Fallo inesperado al sincronizar insumo a Google Sheets")
