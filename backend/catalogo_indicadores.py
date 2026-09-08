# -*- coding: utf-8 -*-
"""
Lectura del catálogo oficial de Indicadores de Logro (R2.1B).

El catálogo MINERD es una CONSTANTE GLOBAL y versionada: las mismas ~1 134
entradas para todos los colegios. Vive en `backend/catalogos/*.json`, no en
PostgreSQL, por las mismas razones por las que el catálogo de Salidas Optativas
vive en `salidas_optativas.py` (R3.1):

  * no pertenece a ningún tenant;
  * no necesita seed ni ~1 134 INSERT durante la migración;
  * queda versionado junto al código que lo consume;
  * es determinista en tests, sin fixtures;
  * `version_curricular` permite que 2023 y una futura 2027 CONVIVAN, de modo
    que una selección histórica siga resolviendo contra su propio catálogo.

El JSON es SOURCE OF TRUTH y se genera OFFLINE con
`tools/extraer_catalogo_indicadores.py`. La aplicación jamás lo regenera.

IDENTIDAD
---------
La clave estable es `catalogo_clave`:

    SEC-2023|2|EF|CE05|IL02
    versión | grado | área | banda CE | posición IL

`CE05` e `IL02` son `orden_ce` y `orden_il`: la POSICIÓN ESTRUCTURAL de la
entrada dentro del bloque del documento (banda de la tabla, y lugar dentro de
esa banda). Son identidad TÉCNICA de EducaOne, NO códigos académicos: no
existen en el documento oficial y no se imprimen nunca.

La clave NO puede construirse con los códigos académicos porque el documento
oficial los repite dentro de un mismo grado y área:

  * `il_codigo` — 6to Educación Física reinicia la numeración en la banda 6, así
    que IL-4..IL-9 aparecen dos veces en el mismo bloque;
  * `ce_codigo` — 2do Educación Física rotula DOS bandas distintas como CE-EF4
    (falta CE-EF5), y sus textos son competencias diferentes.

Esos códigos se conservan EXACTAMENTE como los imprime el MINERD y se usan solo
para display y para el Registro Escolar: `ce_codigo`, `il_codigo`, `ce_texto`,
`il_texto`. Nunca se renumeran para ganar unicidad.

Por eso `IL-19` por sí solo NUNCA identifica nada, y tampoco lo hace
`(grado, área, il_codigo)`: `buscar_por_codigo()` devuelve una LISTA. La única
forma de obtener exactamente una entrada es `resolver(catalogo_clave)`.
"""

import io
import json
import os
import threading
import unicodedata
from typing import Dict, List, Optional

CATALOGOS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "catalogos")

# Versión que usan las selecciones nuevas mientras no se publique otra.
VERSION_ACTUAL = "SEC-2023"

_ARCHIVOS = {
    "SEC-2023": "indicadores_secundaria_2023.json",
}

_cache: Dict[str, dict] = {}
_lock = threading.Lock()


class CatalogoError(Exception):
    """Error explícito del catálogo. Nunca se degrada a un fallback por nombre."""


def _normalizar(texto: str) -> str:
    """Minúsculas sin acentos, solo para BUSCAR. No altera datos."""
    if not texto:
        return ""
    desc = unicodedata.normalize("NFD", str(texto).lower())
    return "".join(c for c in desc if unicodedata.category(c) != "Mn")


def versiones_disponibles() -> List[str]:
    return sorted(_ARCHIVOS)


def _cargar(version: str) -> dict:
    """Carga perezosa y cacheada de un catálogo versionado."""
    if version in _cache:
        return _cache[version]
    with _lock:
        if version in _cache:
            return _cache[version]
        nombre = _ARCHIVOS.get(version)
        if nombre is None:
            raise CatalogoError(
                f"Versión curricular desconocida: {version!r}. "
                f"Disponibles: {', '.join(versiones_disponibles())}."
            )
        ruta = os.path.join(CATALOGOS_DIR, nombre)
        if not os.path.exists(ruta):
            raise CatalogoError(f"Falta el archivo de catálogo {nombre!r}.")
        with io.open(ruta, encoding="utf-8") as fh:
            doc = json.load(fh)

        por_clave = {}
        for e in doc.get("entradas", []):
            clave = e["catalogo_clave"]
            if clave in por_clave:
                raise CatalogoError(f"Catálogo {version}: clave duplicada {clave!r}.")
            por_clave[clave] = e
        doc["_por_clave"] = por_clave
        doc["_busqueda"] = {
            c: _normalizar(f"{e['il_codigo']} {e['il_texto']} {e['ce_codigo']} {e['ce_texto']}")
            for c, e in por_clave.items()
        }
        _cache[version] = doc
        return doc


def resolver(catalogo_clave: str, version: Optional[str] = None) -> dict:
    """
    Entrada oficial de una `catalogo_clave`.

    Lanza CatalogoError si no existe. NO hay fallback por nombre ni por código
    suelto: una clave desconocida es un error, no una coincidencia aproximada.
    """
    if not catalogo_clave or "|" not in str(catalogo_clave):
        raise CatalogoError(f"catalogo_clave inválida: {catalogo_clave!r}.")
    ver = version or str(catalogo_clave).split("|", 1)[0]
    doc = _cargar(ver)
    entrada = doc["_por_clave"].get(catalogo_clave)
    if entrada is None:
        raise CatalogoError(
            f"catalogo_clave desconocida en {ver}: {catalogo_clave!r}."
        )
    return entrada


def existe(catalogo_clave: str) -> bool:
    try:
        resolver(catalogo_clave)
        return True
    except CatalogoError:
        return False


def listar_por(version: Optional[str] = None, grado: Optional[int] = None,
               area: Optional[str] = None) -> List[dict]:
    """
    Entradas del catálogo, ordenadas por (grado, área, orden_ce, orden_il).
    `grado` y `area` son filtros opcionales.
    """
    doc = _cargar(version or VERSION_ACTUAL)
    salida = doc["entradas"]
    if grado is not None:
        salida = [e for e in salida if e["grado_numero"] == int(grado)]
    if area is not None:
        salida = [e for e in salida if e["area_codigo"] == area]
    return salida


def agrupar(version: Optional[str] = None, grado: Optional[int] = None,
            area: Optional[str] = None) -> List[dict]:
    """
    El catálogo en la forma en que lo pinta la UI:

        Competencia Fundamental
          └─ Competencia Específica (CE)
               └─ Indicadores de Logro (IL)

    Conserva el orden oficial del template (orden_ce, orden_il).
    """
    grupos: List[dict] = []
    indice_cf: Dict[str, dict] = {}
    indice_ce: Dict[str, dict] = {}

    for e in listar_por(version, grado, area):
        cf_key = f"{e['grado_numero']}|{e['area_codigo']}|{e['competencia_fundamental_codigo']}"
        cf = indice_cf.get(cf_key)
        if cf is None:
            cf = {
                "competencia_fundamental_codigo": e["competencia_fundamental_codigo"],
                "competencia_fundamental_nombre": e["competencia_fundamental_nombre"],
                "grado_numero": e["grado_numero"],
                "area_codigo": e["area_codigo"],
                "competencias_especificas": [],
            }
            indice_cf[cf_key] = cf
            grupos.append(cf)

        # La BANDA se agrupa por POSICIÓN (orden_ce), nunca por `ce_codigo`:
        # el documento oficial rotula dos bandas distintas de 2do Educación
        # Física con el mismo `CE-EF4`. Agrupar por código las fusionaría y
        # perdería una competencia entera.
        ce_key = f"{e['grado_numero']}|{e['area_codigo']}|{e['orden_ce']}"
        ce = indice_ce.get(ce_key)
        if ce is None:
            ce = {
                "ce_codigo": e["ce_codigo"],
                "ce_texto": e["ce_texto"],
                "orden_ce": e["orden_ce"],
                "indicadores": [],
            }
            indice_ce[ce_key] = ce
            cf["competencias_especificas"].append(ce)

        ce["indicadores"].append({
            "catalogo_clave": e["catalogo_clave"],
            "il_codigo": e["il_codigo"],
            "il_texto": e["il_texto"],
            "orden_il": e["orden_il"],
        })
    return grupos


def buscar_por_codigo(il_codigo: str, version: Optional[str] = None,
                      grado: Optional[int] = None,
                      area: Optional[str] = None) -> List[dict]:
    """
    Entradas cuyo código oficial de indicador es `il_codigo`.

    Devuelve una LISTA porque `(grado, área, il_codigo)` NO identifica una sola
    entrada: en 6to Educación Física el documento reinicia la numeración y, por
    ejemplo, `IL-7` existe dos veces dentro del mismo bloque. Para obtener una
    entrada concreta hay que usar `resolver(catalogo_clave)`.
    """
    objetivo = (il_codigo or "").strip().upper()
    if not objetivo:
        return []
    return [e for e in listar_por(version, grado, area)
            if e["il_codigo"].upper() == objetivo]


def buscar(texto: str, version: Optional[str] = None, grado: Optional[int] = None,
           area: Optional[str] = None, limite: int = 50) -> List[dict]:
    """
    Busca por código ('IL-19') o por texto parcial ('argumentativas').
    Insensible a mayúsculas y acentos. Devuelve entradas del catálogo.
    """
    consulta = _normalizar(texto).strip()
    if not consulta:
        return []
    doc = _cargar(version or VERSION_ACTUAL)
    idx = doc["_busqueda"]
    salida = []
    for e in listar_por(version, grado, area):
        if consulta in idx.get(e["catalogo_clave"], ""):
            salida.append(e)
            if len(salida) >= limite:
                break
    return salida


def metadatos(version: Optional[str] = None) -> dict:
    """Cabecera del catálogo (áreas, competencias fundamentales, fuentes)."""
    doc = _cargar(version or VERSION_ACTUAL)
    return {
        "version_curricular": doc["version_curricular"],
        "nivel": doc["nivel"],
        "areas": doc["areas"],
        "competencias_fundamentales": doc["competencias_fundamentales"],
        "fuentes": doc["fuentes"],
        "total_entradas": doc["total_entradas"],
    }
