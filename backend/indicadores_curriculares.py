# -*- coding: utf-8 -*-
"""
Resolución curricular para Indicadores de Logro (R2.1C).

Traduce los datos institucionales del colegio a las coordenadas del catálogo
oficial: de un `Curso` sale el grado, de una `Asignatura` sale el bloque
curricular. Ambas resoluciones son EXPLÍCITAS y estructurales; ninguna usa el
nombre, el código legacy ni el rótulo `area`.

Es la única puerta por la que la API decide qué parte del catálogo puede ver un
profesor. El cliente nunca envía grado, área ni versión: los deriva el servidor.
"""

import logging
from typing import Optional, Tuple

import catalogo_indicadores as CAT

logger = logging.getLogger(__name__)

# (ok, valor_o_None, error_o_None)
Resolucion = Tuple[bool, Optional[object], Optional[str]]

# Motivo por el que una asignatura no tiene catálogo. Se distingue del error
# porque NO es un fallo de configuración: hay materias del colegio (Música, por
# ejemplo) que legítimamente no ocupan ninguno de los 9 bloques del Registro.
SIN_VINCULO_CURRICULAR = "sin_vinculo_curricular"

GRADOS_SECUNDARIA = (1, 2, 3, 4, 5, 6)


def grado_numero_de_curso(db, curso) -> Resolucion:
    """
    Número de grado (1-6) de un curso de Secundaria.

    `Curso.grado_id` es la relación AUTORITATIVA: nunca se busca otro Grado por
    nombre ni por orden (en producción hay grados duplicados con el mismo
    nombre y el mismo `orden`, y solo uno tiene cursos).

    `Grado.orden` es la fuente del número, pero es un orden GLOBAL: primaria usa
    7..12. Por eso se exige `nivel == 'secundaria'` y `1 <= orden <= 6`.

    El nombre se usa SOLO como invariante de alarma. Si `orden` y `nombre`
    discrepan no se elige ninguno en silencio: es un error explícito.
    """
    from registro_validator import _extraer_grado_numero, _normalizar_nivel

    grado = getattr(curso, 'grado', None)
    if grado is None:
        return False, None, "El curso no tiene grado asignado."

    nivel = _normalizar_nivel(getattr(grado, 'nivel', None))
    if nivel != 'secundaria':
        return False, None, (
            f"Los Indicadores de Logro oficiales son del Nivel Secundario; "
            f"este curso es de {nivel}."
        )

    orden = getattr(grado, 'orden', None)
    if orden not in GRADOS_SECUNDARIA:
        return False, None, (
            f"El grado {grado.nombre!r} tiene orden={orden!r}, fuera del rango "
            f"1-6 de Secundaria. Corrija el orden del grado en Configuración."
        )

    por_nombre = _extraer_grado_numero(getattr(grado, 'nombre', '') or '')
    if por_nombre != orden:
        # No se adivina: los dos datos del propio colegio se contradicen.
        logger.error(
            "Grado %s incoherente: orden=%s pero el nombre %r sugiere %s",
            getattr(grado, 'id', '?'), orden, grado.nombre, por_nombre,
        )
        return False, None, (
            f"El grado {grado.nombre!r} es incoherente: su orden es {orden} pero "
            f"su nombre indica {por_nombre}. Corríjalo antes de registrar "
            f"Indicadores de Logro."
        )

    return True, orden, None


def area_de_asignatura(asignatura) -> Resolucion:
    """
    Bloque curricular oficial de una asignatura.

    Se lee EXCLUSIVAMENTE de `area_curricular_codigo`. Jamás se infiere de
    `nombre`, `codigo` ni `area`: en producción `area` vale "Lenguas" para
    Lengua Española, Inglés y Francés a la vez, y `codigo` se repite entre
    filas. Una heurística acertaría en este colegio y fallaría en silencio en
    el siguiente.

    Un valor NULL devuelve `SIN_VINCULO_CURRICULAR`, que NO es un error de
    configuración: es el estado normal de las materias complementarias.
    """
    codigo = getattr(asignatura, 'area_curricular_codigo', None)
    if not codigo:
        return False, SIN_VINCULO_CURRICULAR, (
            "Esta asignatura no está vinculada a un área curricular del Registro "
            "Escolar de Secundaria. Si corresponde incluirla en el Registro "
            "oficial, Dirección puede configurar su área curricular."
        )
    if not CAT.area_valida(codigo):
        return False, None, (
            f"El área curricular {codigo!r} no existe en el catálogo oficial "
            f"{CAT.VERSION_ACTUAL}."
        )
    return True, codigo, None


def resolver_contexto(db, curso, asignatura) -> Resolucion:
    """
    Coordenadas completas del catálogo para un (curso, asignatura):

        {'grado_numero': 4, 'area_codigo': 'LEF', 'version': 'SEC-2023',
         'area_nombre': 'Lenguas Extranjeras Francés'}

    Devuelve `(False, SIN_VINCULO_CURRICULAR, mensaje)` cuando la asignatura no
    pertenece a ningún bloque oficial, para que la API pueda responder de forma
    controlada en vez de tratarlo como un fallo.
    """
    ok, grado_numero, err = grado_numero_de_curso(db, curso)
    if not ok:
        return False, None, err

    ok, area, err = area_de_asignatura(asignatura)
    if not ok:
        return False, area, err       # `area` lleva SIN_VINCULO_CURRICULAR o None

    return True, {
        "grado_numero": grado_numero,
        "area_codigo": area,
        "area_nombre": CAT.nombre_area(area),
        "version": CAT.VERSION_ACTUAL,
    }, None


def validar_catalogo_clave(clave: str, contexto: dict) -> Resolucion:
    """
    ¿Puede guardarse `clave` en este (curso, asignatura)?

    No basta con que la clave exista en el JSON: debe pertenecer EXACTAMENTE a
    la versión, el grado y el área del contexto. Una clave perfectamente válida
    de otro grado o de otra área se rechaza — si no, un cliente podría guardar
    indicadores de 6to Matemática en 1ro Inglés.
    """
    try:
        entrada = CAT.resolver(clave)
    except CAT.CatalogoError as e:
        return False, None, str(e)

    if entrada["version_curricular"] != contexto["version"]:
        return False, None, (
            f"{clave}: pertenece a la versión {entrada['version_curricular']}, "
            f"no a {contexto['version']}."
        )
    if entrada["grado_numero"] != contexto["grado_numero"]:
        return False, None, (
            f"{clave}: pertenece a {entrada['grado_numero']}to grado, no a "
            f"{contexto['grado_numero']}to."
        )
    if entrada["area_codigo"] != contexto["area_codigo"]:
        return False, None, (
            f"{clave}: pertenece al área {entrada['area_codigo']}, no a "
            f"{contexto['area_codigo']}."
        )
    return True, entrada, None


def catalogo_agrupado(contexto: dict, q: Optional[str] = None) -> list:
    """
    Catálogo listo para la UI: Competencia Fundamental → CE (banda) → IL.

    Con `q` se filtran los indicadores por código o texto, conservando el
    contexto (CF y CE) de cada coincidencia para poder distinguir códigos
    repetidos. Los grupos que quedan sin indicadores se omiten.
    """
    grupos = CAT.agrupar(contexto["version"], contexto["grado_numero"],
                         contexto["area_codigo"])
    if not q or not str(q).strip():
        return grupos

    claves = {e["catalogo_clave"] for e in CAT.buscar(
        q, contexto["version"], contexto["grado_numero"], contexto["area_codigo"],
        limite=10_000)}

    filtrados = []
    for cf in grupos:
        ces = []
        for ce in cf["competencias_especificas"]:
            ils = [il for il in ce["indicadores"] if il["catalogo_clave"] in claves]
            if ils:
                ces.append({**ce, "indicadores": ils})
        if ces:
            filtrados.append({**cf, "competencias_especificas": ces})
    return filtrados
