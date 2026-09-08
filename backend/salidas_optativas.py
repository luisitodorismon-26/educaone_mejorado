# -*- coding: utf-8 -*-
"""
Catálogo oficial de SALIDAS OPTATIVAS de la Modalidad Académica (4to-6to).

R3.1 — CONGELACIÓN DE POLÍTICA
==============================

Este módulo es el ÚNICO lugar donde vive el catálogo MINERD. Es una CONSTANTE
DEL SISTEMA EDUCATIVO DOMINICANO, no un dato del colegio: las 4 salidas y sus
18 componentes son idénticos en todos los centros. Por eso vive en código y NO
en tablas de base de datos:

  - no requiere seed (una escritura menos contra producción real);
  - no puede divergir entre entornos ni quedarse a medias en una migración;
  - queda versionado junto al código que lo usa;
  - es determinista en tests, sin fixtures.

Es exactamente el mismo criterio que ya sigue `registro_escolar.GRADO_CONFIG`
con el mapa de páginas del Registro Escolar.

Lo que SÍ es dato del colegio (y por tanto vive en la BD) es solamente:

  1. qué salida sigue cada curso   -> `Curso.salida_optativa_codigo`
  2. qué asignatura REAL del colegio implementa cada componente
                                   -> `CursoComponenteOptativo`

IDENTIDAD — REGLA INNEGOCIABLE
------------------------------
Nada aquí se resuelve por NOMBRE TEXTUAL ni por `Asignatura.codigo`. En
producción `asignaturas.codigo` está DUPLICADO (ids 1-8 y 9-16 comparten
LE/MA/CS/CN/IN/EF/EA/FH), así que no identifica nada. La cadena de resolución
es siempre por identificadores estables:

    Curso -> salida_optativa_codigo ('CYT')
         -> ComponenteOptativo.codigo ('CYT-CN-4')
         -> CursoComponenteOptativo.asignatura_id (FK real)
         -> página del Registro

Los `nombre_oficial` de abajo son SOLO para display e impresión. Fueron
extraídos literalmente de los templates oficiales del repo
(`Registro-{4to,5to,6to}-Grado-Sec-Academica-1-1.pdf`, páginas 211/212/214/
217/219/221), que corresponden a la Adecuación Curricular 2023. NUNCA deben
usarse como clave de búsqueda.

FUENTE: `backend/templates/registro_escolar/Registro-*-Sec-Academica-1-1.pdf`
"""

from typing import Dict, List, NamedTuple, Optional

# --- Grados de la Modalidad Académica que tienen Salida Optativa ---
GRADOS_CON_SALIDA = (4, 5, 6)

# --- Códigos estables de las 4 salidas (NUNCA cambian) ---
SALIDA_HLM = "HLM"
SALIDA_HCS = "HCS"
SALIDA_MYT = "MYT"
SALIDA_CYT = "CYT"

SALIDAS: Dict[str, str] = {
    SALIDA_HLM: "Humanidades y Lenguas Modernas",
    SALIDA_HCS: "Humanidades y Ciencias Sociales",
    SALIDA_MYT: "Matemática y Tecnología",
    SALIDA_CYT: "Ciencias y Tecnología",
}

# --- Áreas base (etiquetas internas; NO son `Asignatura.codigo`) ---
AREA_LENGUA = "lengua_espanola"
AREA_INGLES = "ingles"
AREA_MATEMATICA = "matematica"
AREA_SOCIALES = "ciencias_sociales"
AREA_NATURALEZA = "ciencias_naturaleza"

# Índice del área base dentro de `registro_escolar.ASIGNATURAS_CICLO_2`.
# Sirve para saber de qué asignatura troncal se desprende el componente; NO se
# usa para resolver la asignatura real del colegio.
AREA_BASE_IDX_CICLO_2: Dict[str, int] = {
    AREA_LENGUA: 0,      # Lengua Española
    AREA_INGLES: 1,      # Lenguas Extranjeras - Inglés
    AREA_MATEMATICA: 3,  # Matemática
    AREA_SOCIALES: 4,    # Ciencias Sociales
    AREA_NATURALEZA: 5,  # Ciencias de la Naturaleza
}


class ComponenteOptativo(NamedTuple):
    """Un componente optativo oficial: (salida, grado, slot)."""
    codigo: str          # identidad estable, p.ej. 'CYT-CN-4'
    salida: str          # 'HLM' | 'HCS' | 'MYT' | 'CYT'
    grado: int           # 4 | 5 | 6
    slot: int            # 0..5 — posición en el Registro (ver más abajo)
    area_base: str       # AREA_*
    nombre_oficial: str  # SOLO display/impresión
    horas_semana: int


# ---------------------------------------------------------------------------
# SLOTS
# ---------------------------------------------------------------------------
# El slot es la posición del componente dentro del Registro Escolar y es la
# MISMA en 4to, 5to y 6to (solo cambia el nombre del componente). El orden lo
# fija el template, no nosotros:
#
#   slot 0 -> pg 211 -> HLM / Lengua
#   slot 1 -> pg 212 -> HCS / Lengua
#   slot 2 -> pg 214 -> HLM / Inglés
#   slot 3 -> pg 217 -> MYT / Matemática
#   slot 4 -> pg 219 -> HCS / Ciencias Sociales
#   slot 5 -> pg 221 -> CYT / Ciencias de la Naturaleza
#
# `registro_escolar.GRADO_CONFIG[g]['completiva_salida_optativa']` lista esas
# 6 páginas EN ESTE MISMO ORDEN, de modo que slot == índice en esa lista.
# `test_salida_optativa_r31.py` verifica esa correspondencia.
#
# Cada salida aporta 4 horas/semana repartidas en 1 o 2 componentes, así que un
# estudiante cursa como MÁXIMO 2 componentes optativos.
# ---------------------------------------------------------------------------

_CATALOGO: List[ComponenteOptativo] = [
    # ---------------- 4to ----------------
    ComponenteOptativo("HLM-LE-4", SALIDA_HLM, 4, 0, AREA_LENGUA,
                       "Apreciación y Producción Literarias", 2),
    ComponenteOptativo("HCS-LE-4", SALIDA_HCS, 4, 1, AREA_LENGUA,
                       "Apreciación y Producción Literarias", 2),
    ComponenteOptativo("HLM-IN-4", SALIDA_HLM, 4, 2, AREA_INGLES,
                       "Manejo de la Información en Inglés", 2),
    ComponenteOptativo("MYT-MA-4", SALIDA_MYT, 4, 3, AREA_MATEMATICA,
                       "Matemática Financiera y Tecnología", 4),
    ComponenteOptativo("HCS-CS-4", SALIDA_HCS, 4, 4, AREA_SOCIALES,
                       "Filosofía Social y Pensamiento Dominicano", 2),
    ComponenteOptativo("CYT-CN-4", SALIDA_CYT, 4, 5, AREA_NATURALEZA,
                       "Biología y Computación", 4),

    # ---------------- 5to ----------------
    ComponenteOptativo("HLM-LE-5", SALIDA_HLM, 5, 0, AREA_LENGUA,
                       "Apreciación y Producción Literarias", 2),
    ComponenteOptativo("HCS-LE-5", SALIDA_HCS, 5, 1, AREA_LENGUA,
                       "Apreciación y Producción Literarias", 2),
    ComponenteOptativo("HLM-IN-5", SALIDA_HLM, 5, 2, AREA_INGLES,
                       "Apreciación de la Literatura Anglófona", 2),
    ComponenteOptativo("MYT-MA-5", SALIDA_MYT, 5, 3, AREA_MATEMATICA,
                       "Estadística, Probabilidad y Tecnología", 4),
    ComponenteOptativo("HCS-CS-5", SALIDA_HCS, 5, 4, AREA_SOCIALES,
                       "Geografía Humana y Demografía", 2),
    ComponenteOptativo("CYT-CN-5", SALIDA_CYT, 5, 5, AREA_NATURALEZA,
                       "Química y Computación", 4),

    # ---------------- 6to ----------------
    ComponenteOptativo("HLM-LE-6", SALIDA_HLM, 6, 0, AREA_LENGUA,
                       "Análisis y Producción de Textos Periodísticos y Publicitarios", 2),
    ComponenteOptativo("HCS-LE-6", SALIDA_HCS, 6, 1, AREA_LENGUA,
                       "Análisis y Producción de Textos Científicos y Profesionales", 2),
    ComponenteOptativo("HLM-IN-6", SALIDA_HLM, 6, 2, AREA_INGLES,
                       "Análisis Crítico y Evaluación de Textos en Inglés", 2),
    ComponenteOptativo("MYT-MA-6", SALIDA_MYT, 6, 3, AREA_MATEMATICA,
                       "Trigonometría, Cálculo Diferencial y Tecnología", 4),
    ComponenteOptativo("HCS-CS-6", SALIDA_HCS, 6, 4, AREA_SOCIALES,
                       "Ciudadanía y Democracia Participativa", 2),
    ComponenteOptativo("CYT-CN-6", SALIDA_CYT, 6, 5, AREA_NATURALEZA,
                       "Física y Computación", 4),
]

# Índice por código — la única forma admitida de resolver un componente.
COMPONENTES_POR_CODIGO: Dict[str, ComponenteOptativo] = {
    c.codigo: c for c in _CATALOGO
}


def salida_valida(codigo: Optional[str]) -> bool:
    """True si `codigo` es una de las 4 salidas oficiales."""
    return codigo in SALIDAS


def nombre_salida(codigo: Optional[str]) -> Optional[str]:
    """Nombre oficial para display. None si el código no existe."""
    if codigo is None:
        return None
    return SALIDAS.get(codigo)


def grado_admite_salida(grado_numero: Optional[int]) -> bool:
    """
    Solo 4to, 5to y 6to de la Modalidad Académica tienen Salida Optativa.
    1ro-3ro (Nivel Secundario, Primer Ciclo) NO la tienen: su Registro ni
    siquiera imprime las páginas correspondientes.
    """
    return grado_numero in GRADOS_CON_SALIDA


def componente(codigo: Optional[str]) -> Optional[ComponenteOptativo]:
    """Resuelve un componente por su código estable. None si no existe."""
    if codigo is None:
        return None
    return COMPONENTES_POR_CODIGO.get(codigo)


def componentes_de(salida_codigo: Optional[str], grado_numero: Optional[int]) -> List[ComponenteOptativo]:
    """
    Componentes que un curso de `grado_numero` debe cursar si sigue
    `salida_codigo`, ordenados por slot. Lista vacía si la combinación no es
    válida (nunca lanza: el llamador decide si eso es un error).
    """
    if not salida_valida(salida_codigo) or not grado_admite_salida(grado_numero):
        return []
    return sorted(
        (c for c in _CATALOGO if c.salida == salida_codigo and c.grado == grado_numero),
        key=lambda c: c.slot,
    )


def componente_pertenece(codigo: Optional[str], salida_codigo: Optional[str],
                         grado_numero: Optional[int]) -> bool:
    """
    True solo si el componente existe Y pertenece a esa salida Y a ese grado.

    Esta es la validación que impide, por ejemplo, mapear 'HLM-LE-4' en un
    curso configurado como CYT, o 'CYT-CN-4' en un 5to.
    """
    comp = componente(codigo)
    if comp is None:
        return False
    return comp.salida == salida_codigo and comp.grado == grado_numero


def horas_totales(salida_codigo: Optional[str], grado_numero: Optional[int]) -> int:
    """Carga semanal total de la salida (4 h/semana en las cuatro)."""
    return sum(c.horas_semana for c in componentes_de(salida_codigo, grado_numero))
