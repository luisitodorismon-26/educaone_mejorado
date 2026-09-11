"""
registro_escolar.py - Generador de Registro Escolar MINERD
===========================================================
Genera registros escolares oficiales del MINERD usando los PDFs originales
como plantilla base y escribiendo datos encima con overlay (reportlab + pypdf).

Los datos se escriben en color AZUL tipo lapicero sobre el formulario vacío.
Soporta grados 1ro-6to del Nivel Secundario.

Estructura:
- 1er-3er grado (Primer Ciclo, Sec. General): 170 páginas
- 4to-6to grado (Segundo Ciclo, Sec. Académica): 238-240 páginas

Autor: EducaOne
"""

import io
import os
import logging
from datetime import date
from typing import Dict, List, Optional, Any
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from pypdf import PdfReader, PdfWriter
from registro_borrador import (
    crear_xobject_borrador, estampar_borrador,
    crear_xobject_desde_overlay, estampar_xobject, nombre_xobject_libre,
)
# v2.19.7: el formato de las notas es el MISMO que ya usa el boletín oficial de
# secundaria — "entero si es CF, 1 decimal si es PC/competencia". Se importa en
# vez de reescribirlo para que no puedan divergir. `boletin_minerd_secundaria`
# no importa este módulo, así que no hay ciclo.
from boletin_minerd_secundaria import _fmt_nota
# v2.20.1-B2.1: la CF OFICIAL visible se redondea con el criterio académico
# (.5 SIEMPRE sube — Decimal + ROUND_HALF_UP), NUNCA con round() (half-to-even).
# Es el MISMO helper que v2.20.0 usa en el modelo y el endpoint; se importa para
# no poder divergir. reglas_academicas no importa este módulo (no hay ciclo).
from reglas_academicas import redondear_calificacion_final

logger = logging.getLogger(__name__)

# ============================================================================
# CONSTANTES
# ============================================================================

PAGE_W, PAGE_H = letter  # 612 x 792 pts

# Color azul tipo lapicero (RGB normalizado)
AZUL = (0, 0, 0.7)

# Fuentes disponibles en reportlab sin instalar extras
FONT_NORMAL = "Helvetica"
FONT_BOLD = "Helvetica-Bold"

# Tamaños de fuente por contexto
FONT_SIZE_PORTADA_ANIO = 14
FONT_SIZE_PORTADA_SECCION = 12
FONT_SIZE_CENTRO = 10
FONT_SIZE_TABLA = 7
FONT_SIZE_TABLA_NOMBRE = 6.5
FONT_SIZE_NOTA = 8
FONT_SIZE_ASISTENCIA = 6
FONT_SIZE_PROMOCION = 6
FONT_SIZE_ESTADISTICAS = 8

# Rutas de templates (relativas al directorio de la aplicación)
TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "registro_escolar")

TEMPLATE_FILES = {
    1: "Registro-1er-Grado-Sec-General-1-1.pdf",
    2: "Registro-2do-Grado-Sec-General-1-1.pdf",
    3: "Registro-3er-Grado-Sec-General-1-1.pdf",
    4: "Registro-4to-Grado-Sec-Academica-1-1.pdf",
    5: "Registro-5to-Grado-Sec-Academica-1-1.pdf",
    6: "Registro-6to-Grado-Sec-Academica-1-1.pdf",
}

# ============================================================================
# MAPEO DE PÁGINAS POR GRADO (1-indexed)
# ============================================================================

# Asignaturas por ciclo
ASIGNATURAS_CICLO_1 = [
    "Lengua Española",
    "Lenguas Extranjeras - Inglés",
    "Lenguas Extranjeras - Francés",
    "Matemática",
    "Ciencias Sociales",
    "Ciencias de la Naturaleza",
    "Educación Artística",
    "Educación Física",
    "Formación Integral Humana y Religiosa",
]

ASIGNATURAS_CICLO_2 = [
    "Lengua Española",
    "Lenguas Extranjeras - Inglés",
    "Lenguas Extranjeras - Francés",
    "Matemática",
    "Ciencias Sociales",
    "Ciencias de la Naturaleza",
    "Educación Artística",
    "Educación Física",
    "Formación Integral Humana y Religiosa",
    "Salida Optativa",
]


def get_asignaturas_por_grado(grado_numero: int):
    """
    Retorna lista de tuplas (key, nombre) de asignaturas según el grado.
    Compatible con el endpoint de preview en app.py.
    """
    if grado_numero >= 4:
        asigs = ASIGNATURAS_CICLO_2
    else:
        asigs = ASIGNATURAS_CICLO_1
    
    return [(a.lower().replace(" ", "_").replace("-", "_"), a) for a in asigs]

# ---------------------------------------------------------------------------
# R3.1 §5 — MAPA REAL DE PÁGINAS DE ASISTENCIA (Secundaria, 1ro-6to)
# ---------------------------------------------------------------------------
# Esto NO es una fórmula: es el mapa verificado PÁGINA POR PÁGINA contra los
# seis templates oficiales del repo, leyendo el rótulo de asignatura impreso en
# cada hoja. Los seis grados comparten exactamente el mismo mapa base.
#
# Hasta R3.0 el generador calculaba la página como
#     asistencia_inicio + a_idx * 5
# asumiendo 5 páginas para las nueve asignaturas. El template NO es uniforme:
# las seis asignaturas de mayor carga usan 5 páginas de 2 meses cada una, y las
# tres últimas (Ed. Artística, Ed. Física, FIHR) usan 3 páginas de 4 meses. La
# fórmula acertaba solo en las seis primeras y a partir de ahí se desfasaba:
#
#   a_idx 6 Ed. Artística : fórmula 47-51  | real 47-49  -> invadía Ed. Física
#   a_idx 7 Ed. Física    : fórmula 52-56  | real 50-52  -> invadía FIHR y pg 56
#   a_idx 8 FIHR          : fórmula 57-61  | real 53-55  -> escribía FUERA
#
# Y esas páginas 56-61 no están vacías:
#   * en 4to-6to son las hojas EN BLANCO de SALIDA OPTATIVA (56-65);
#   * en 1ro-3ro son "ASISTENCIA A EVALUACIONES COMPLETIVAS/EXTRAORDINARIAS".
#
# Por eso corregir esto es prerrequisito directo de la Salida Optativa: sin la
# tabla explícita, la asistencia de FIHR seguiría pisando sus páginas.
#
# `layout` describe la rejilla impresa en la hoja:
#   "2meses" -> 2 meses por página, 21 días por mes. Geometría de
#               ASISTENCIA_TABLE / draw_asistencia().
#   "4meses" -> 4 meses por página, 10 días por mes. Rejilla DISTINTA, con su
#               propia calibración: ASISTENCIA_TABLE_4MESES /
#               draw_asistencia_4meses(). Ambas están medidas contra el
#               template; ninguna aproxima a la otra.
ASISTENCIA_MAPA_SECUNDARIA = [
    {"paginas": [17, 18, 19, 20, 21], "layout": "2meses"},  # 0 Lengua Española
    {"paginas": [22, 23, 24, 25, 26], "layout": "2meses"},  # 1 Inglés
    {"paginas": [27, 28, 29, 30, 31], "layout": "2meses"},  # 2 Francés
    {"paginas": [32, 33, 34, 35, 36], "layout": "2meses"},  # 3 Matemática
    {"paginas": [37, 38, 39, 40, 41], "layout": "2meses"},  # 4 Ciencias Sociales
    {"paginas": [42, 43, 44, 45, 46], "layout": "2meses"},  # 5 Ciencias de la Naturaleza
    {"paginas": [47, 48, 49], "layout": "4meses"},          # 6 Educación Artística
    {"paginas": [50, 51, 52], "layout": "4meses"},          # 7 Educación Física
    {"paginas": [53, 54, 55], "layout": "4meses"},          # 8 FIHR
]

# Geometrías sin calibrar. Vacío desde el hardening de R3.1: las dos rejillas
# del Registro de Secundaria están medidas contra el template. Se conserva como
# barrera explícita — si algún día aparece un layout nuevo, se añade aquí y el
# generador dejará esas páginas EN BLANCO (tal como las imprime el MINERD,
# listas para llenar a mano) en vez de estampar marcas descuadradas.
ASISTENCIA_LAYOUT_SIN_CALIBRAR: set = set()

# Encabezado impreso de las páginas de asistencia de Salida Optativa. Medido
# sobre los tres templates con pymupdf: el rótulo es un único span
# "SALIDA OPTATIVA ______ ASIGNATURA ______" en x0=74.77..548.20, y0=51.41,
# y1=65.86, size 11, IDÉNTICO en las 10 páginas y en 4to, 5to y 6to.
#
#   "SALIDA OPTATIVA" termina en x=178.09 -> su hueco va de 178.09 a 329.89
#   "ASIGNATURA"      termina en x=406.30 -> su hueco va de 406.30 a 548.20
#
# El campo DOCENTE de estas páginas es el mismo de la rejilla normal (y0=86.40)
# y ya lo estampa `draw_asistencia`, así que aquí no se duplica.
ASISTENCIA_SALIDA_OPTATIVA_HEADER = {
    "y_plumber": 63.5,            # línea base, dentro de y0=51.41..y1=65.86
    "salida_x": 182.0,            # justo después de "SALIDA OPTATIVA "
    "salida_max_width": 144.0,    # hasta donde empieza "ASIGNATURA"
    "asignatura_x": 410.0,        # justo después de "ASIGNATURA "
    "asignatura_max_width": 136.0,
}

# Bloque de asistencia de la SALIDA OPTATIVA (solo 4to-6to): 10 páginas con el
# encabezado impreso "SALIDA OPTATIVA ____ ASIGNATURA ____", es decir 2
# componentes × 5 páginas. Un estudiante cursa como máximo 2 componentes, así
# que el bloque alcanza justo. R3.1 lo DOCUMENTA pero no lo estampa: el render
# de la Salida Optativa es R3.3.
ASISTENCIA_SALIDA_OPTATIVA_CICLO_2 = [
    [56, 57, 58, 59, 60],
    [61, 62, 63, 64, 65],
]

# Páginas de cada sección por grado
GRADO_CONFIG = {
    # --- PRIMER CICLO (1er-3er) ---
    1: {
        "ciclo": 1,
        "total_paginas": 170,
        "portada": [1, 2],
        "centro_educativo": 8,
        "datos_estudiantes": 11,
        "condicion_inicial": 12,
        "emergencias": 13,
        "parentesco": 14,
        # Asistencia: pgs 17-62 (9 asignaturas, ~5 pgs c/u, 2 meses por página)
        # LEGACY R3.1: estas dos claves YA NO enrutan la asistencia. El mapa
        # real es ASISTENCIA_MAPA_SECUNDARIA. Se conservan solo porque las
        # usan tests del pipeline XObject para elegir un rango de páginas.
        "asistencia_inicio": 17,
        "asistencia_pgs_por_asignatura": 5,
        # Calificaciones de rendimiento (spreads de 2 páginas por asignatura)
        "calificaciones_inicio": 131,
        "calificaciones_pgs_por_asignatura": 2,
        # Completivas/extraordinarias (1 pg por asignatura)
        # Completivas: 9 asignaturas base, 1 pg cada una
        # Pg 150=Lengua, 151=Inglés, 152=Francés, 153=Matemática,
        # 154=C.Sociales, 155=C.Naturaleza, 156=Ed.Artística, 157=Ed.Física, 158=FIHR
        "completiva_inicio": 150,
        "completiva_paginas": [150, 151, 152, 153, 154, 155, 156, 157, 158],
        # Promoción (spread landscape): Pg 159-160
        "promocion_inicio": 159,
        "promocion_paginas": 2,
        # Resumen / Experiencias: Pg 161-164
        "resumen_inicio": 161,
        "resumen_paginas": 4,
        # Estadísticas: Pg 169
        "estadisticas": 169,
    },
    2: {
        "ciclo": 1,
        "total_paginas": 170,
        "portada": [1, 2],
        "centro_educativo": 8,
        "datos_estudiantes": 11,
        "condicion_inicial": 12,
        "emergencias": 13,
        "parentesco": 14,
        # LEGACY R3.1: estas dos claves YA NO enrutan la asistencia. El mapa
        # real es ASISTENCIA_MAPA_SECUNDARIA. Se conservan solo porque las
        # usan tests del pipeline XObject para elegir un rango de páginas.
        "asistencia_inicio": 17,
        "asistencia_pgs_por_asignatura": 5,
        "calificaciones_inicio": 131,
        "calificaciones_pgs_por_asignatura": 2,
        "completiva_inicio": 150,
        "completiva_paginas": [150, 151, 152, 153, 154, 155, 156, 157, 158],
        "promocion_inicio": 159,
        "promocion_paginas": 2,
        "resumen_inicio": 161,
        "resumen_paginas": 4,
        "estadisticas": 169,
    },
    3: {
        "ciclo": 1,
        "total_paginas": 170,
        "portada": [1, 2],
        "centro_educativo": 8,
        "datos_estudiantes": 11,
        "condicion_inicial": 12,
        "emergencias": 13,
        "parentesco": 14,
        # LEGACY R3.1: estas dos claves YA NO enrutan la asistencia. El mapa
        # real es ASISTENCIA_MAPA_SECUNDARIA. Se conservan solo porque las
        # usan tests del pipeline XObject para elegir un rango de páginas.
        "asistencia_inicio": 17,
        "asistencia_pgs_por_asignatura": 5,
        "calificaciones_inicio": 131,
        "calificaciones_pgs_por_asignatura": 2,
        "completiva_inicio": 150,
        "completiva_paginas": [150, 151, 152, 153, 154, 155, 156, 157, 158],
        "promocion_inicio": 159,
        "promocion_paginas": 2,
        "resumen_inicio": 161,
        "resumen_paginas": 4,
        "estadisticas": 169,
    },
    # --- SEGUNDO CICLO (4to-6to) ---
    4: {
        "ciclo": 2,
        "total_paginas": 238,
        "portada": [1, 2],
        "centro_educativo": 8,
        "datos_estudiantes": 11,
        "condicion_inicial": 12,
        "emergencias": 13,
        "parentesco": 14,
        # LEGACY R3.1: estas dos claves YA NO enrutan la asistencia. El mapa
        # real es ASISTENCIA_MAPA_SECUNDARIA. Se conservan solo porque las
        # usan tests del pipeline XObject para elegir un rango de páginas.
        "asistencia_inicio": 17,
        "asistencia_pgs_por_asignatura": 5,
        "calificaciones_inicio": 179,
        "calificaciones_pgs_por_asignatura": 2,
        # Completivas: incluye salida optativa intercalada
        # Pg 210=Lengua, 211-212=SalidaOpt(Lengua), 213=Inglés, 214=SalidaOpt(Inglés),
        # 215=Francés, 216=Matemática, 217=SalidaOpt(Mat), 218=C.Sociales, 219=SalidaOpt(CS),
        # 220=C.Naturaleza(Bio), 221=SalidaOpt(CN), 222=Ed.Artística, 223=Ed.Física, 224=FIHR
        "completiva_inicio": 210,
        "completiva_paginas": [210, 213, 215, 216, 218, 220, 222, 223, 224],
        "completiva_salida_optativa": [211, 212, 214, 217, 219, 221],
        "promocion_inicio": 225,
        "promocion_paginas": 2,
        "resumen_inicio": 227,
        "resumen_paginas": 4,
        "estadisticas": 235,
    },
    5: {
        "ciclo": 2,
        "total_paginas": 238,
        "portada": [1, 2],
        "centro_educativo": 8,
        "datos_estudiantes": 11,
        "condicion_inicial": 12,
        "emergencias": 13,
        "parentesco": 14,
        # LEGACY R3.1: estas dos claves YA NO enrutan la asistencia. El mapa
        # real es ASISTENCIA_MAPA_SECUNDARIA. Se conservan solo porque las
        # usan tests del pipeline XObject para elegir un rango de páginas.
        "asistencia_inicio": 17,
        "asistencia_pgs_por_asignatura": 5,
        "calificaciones_inicio": 179,
        "calificaciones_pgs_por_asignatura": 2,
        "completiva_inicio": 210,
        "completiva_paginas": [210, 213, 215, 216, 218, 220, 222, 223, 224],
        "completiva_salida_optativa": [211, 212, 214, 217, 219, 221],
        "promocion_inicio": 225,
        "promocion_paginas": 2,
        "resumen_inicio": 227,
        "resumen_paginas": 4,
        "estadisticas": 235,
    },
    6: {
        "ciclo": 2,
        "total_paginas": 240,
        "portada": [1, 2],
        "centro_educativo": 8,
        "datos_estudiantes": 11,
        "condicion_inicial": 12,
        "emergencias": 13,
        "parentesco": 14,
        # LEGACY R3.1: estas dos claves YA NO enrutan la asistencia. El mapa
        # real es ASISTENCIA_MAPA_SECUNDARIA. Se conservan solo porque las
        # usan tests del pipeline XObject para elegir un rango de páginas.
        "asistencia_inicio": 17,
        "asistencia_pgs_por_asignatura": 5,
        "calificaciones_inicio": 179,
        "calificaciones_pgs_por_asignatura": 2,
        "completiva_inicio": 210,
        "completiva_paginas": [210, 213, 215, 216, 218, 220, 222, 223, 224],
        "completiva_salida_optativa": [211, 212, 214, 217, 219, 221],
        "promocion_inicio": 225,
        "promocion_paginas": 2,
        "resumen_inicio": 227,
        "resumen_paginas": 4,
        "estadisticas": 235,
    },
}


# ============================================================================
# COORDENADAS DE CELDAS (en puntos PDF, origen inferior-izquierdo)
# Nota: pdfplumber usa origen superior-izquierdo, aquí convertimos a PDF coords
# PDF_Y = PAGE_H - pdfplumber_Y
# ============================================================================

def _y(plumber_y: float) -> float:
    """Convierte coordenada Y de pdfplumber (top-left) a PDF (bottom-left)."""
    return PAGE_H - plumber_y


# --- PORTADA (Pg 1) ---
# Calibrado contra PDF MINERD oficial:
#   "20______ 20______" en y_plumber=659.7
#   Primer "20" empieza en x=181.3, sus "______" van hasta x≈225
#   Segundo "20" empieza en x=243.1, sus "______" van hasta x≈287
#   "SECCIÓN" en y_plumber=697.8, línea de sección de x=148 a x=275
PORTADA_COORDS = {
    "anio_inicio_x": 200,      # Sobre los guiones del primer "20" (181+19)
    "anio_inicio_y": _y(670),  # Pegado a la línea de los guiones (más bajo)
    "anio_fin_x": 261,         # Sobre los guiones del segundo "20" (243+18)
    "anio_fin_y": _y(670),
    "seccion_x": 165,          # Después del label "SECCIÓN" (start línea x=148 + margen)
    "seccion_y": _y(710),      # Sobre la línea de la sección
    "salida_optativa_x": 165,
    "salida_optativa_y": _y(735),
}

# --- CENTRO EDUCATIVO (Pg 8) ---
# Datos se escriben sobre las líneas horizontales, justo encima
# Los rects definen los campos: x0=47.3 labels, datos empiezan en ~160
CENTRO_COORDS = {
    "nombre_centro": {"x": 160, "y": _y(238)},
    "direccion": {"x": 160, "y": _y(276)},
    "correo_centro": {"x": 160, "y": _y(313)},
    "telefono_centro": {"x": 440, "y": _y(313)},
    "codigo_sigerd": {"x": 160, "y": _y(358)},
    "codigo_cartografia": {"x": 440, "y": _y(358)},
    "director": {"x": 160, "y": _y(397)},
    "correo_director": {"x": 160, "y": _y(434)},
    "telefono_director": {"x": 440, "y": _y(434)},
    "docente_encargado": {"x": 160, "y": _y(478)},
    "correo_docente": {"x": 160, "y": _y(517)},
    "telefono_docente": {"x": 440, "y": _y(517)},
    # Checkboxes de sector (marcar con X) - círculos justo después del texto
    # Y baja para que X caiga DENTRO del círculo (no encima)
    "sector_publico": {"x": 153, "y": _y(556)},
    "sector_privado": {"x": 237, "y": _y(556)},
    "sector_semioficial": {"x": 352, "y": _y(556)},
    # Zona — fila 1 (top=589 → círculos en y≈593)
    "zona_urbana": {"x": 152, "y": _y(597)},
    "zona_urbana_marginal": {"x": 280, "y": _y(597)},
    "zona_urbana_turistica": {"x": 399, "y": _y(597)},
    # Zona fila 2 (top=611.6 → círculos en y≈616)
    "zona_rural": {"x": 142, "y": _y(620)},
    "zona_rural_aislada": {"x": 262, "y": _y(620)},
    "zona_rural_turistica": {"x": 389, "y": _y(620)},
    # Jornada (top=652.8 → círculos en y≈657)
    "jornada_jee": {"x": 135, "y": _y(660)},
    "jornada_matutina": {"x": 230, "y": _y(660)},
    "jornada_vespertina": {"x": 346, "y": _y(660)},
    "jornada_nocturna": {"x": 455, "y": _y(660)},
    # Regional / Distrito
    "regional": {"x": 160, "y": _y(699)},
    "distrito": {"x": 440, "y": _y(699)},
}

# --- DATOS DEL ESTUDIANTE (Pg 11) ---
# Tabla de 40 filas con columnas:
# V-lines: 36.4, 59.2, 82.0, 106.5, 131.0, 155.5, 181.7, 210.4, 239.0, 318.6, 398.3, 575.5
# Columnas: No | Femenino | Masculino | Día | Mes | Año | Libro | Folio | Edad | Cédula/Pasaporte | RNE | Lugar
# H-lines start: 180.2, spacing: ~14.2

ESTUDIANTES_TABLE = {
    "primera_fila_y_plumber": 180.2,  # top of first row
    "row_height": 14.15,               # approx spacing
    "total_filas": 40,
    # v2.19.7 — CENTROS RE-MEDIDOS SOBRE EL TEMPLATE.
    #
    # Las líneas verticales reales de la tabla (pág. 11) son:
    #   36.4 | 59.2 | 82.0 | 106.5 | 131.0 | 155.5 | 181.7 | 210.4 | 239.0
    #        | 318.6 | 398.3 | 575.5
    # o sea ONCE columnas: Femenino, Masculino, Día, Mes, Año, Libro, Folio,
    # Edad, Cédula/Pasaporte, RNE, Lugar donde reside. NO hay columna de "No."
    # ni de nombre: al estudiante lo identifica su posición de fila, igual que
    # en el resto del cuaderno.
    #
    # La versión anterior daba por hecha una columna "numero" al principio, y
    # eso corría TODO un lugar a la derecha: el sexo se marcaba en la casilla
    # del día de nacimiento, el día en la del mes, la cédula en la del RNE...
    # Los comentarios ya traían los límites correctos; los centros no.
    "columnas": {
        # col_name: (x_center, width) - x_center para centrar texto
        "femenino": {"x": 47.8, "w": 22},          # 36.4 - 59.2  (marcar X)
        "masculino": {"x": 70.6, "w": 22},         # 59.2 - 82.0  (marcar X)
        "dia": {"x": 94.2, "w": 24},               # 82.0 - 106.5
        "mes": {"x": 118.7, "w": 24},              # 106.5 - 131.0
        "anio": {"x": 143.2, "w": 24},             # 131.0 - 155.5
        "libro": {"x": 168.6, "w": 25},            # 155.5 - 181.7
        "folio": {"x": 196.0, "w": 28},            # 181.7 - 210.4
        "edad": {"x": 224.7, "w": 28},             # 210.4 - 239.0
        "cedula": {"x": 278.8, "w": 76},           # 239.0 - 318.6
        "rne": {"x": 358.4, "w": 76},              # 318.6 - 398.3
        "lugar_residencia": {"x": 486.9, "w": 172},  # 398.3 - 575.5
    },
}

# --- CONDICIÓN INICIAL (Pg 12) ---
# Misma estructura de tabla pero con columnas diferentes
# V-lines similares, columnas: No | Correo | Promovido | Repitente | Reingreso
CONDICION_TABLE = {
    # v2.19.7: la primera fila de esta página empieza en 177.2, no en 180.2
    # (medido sobre el template). Con el valor anterior la línea base caía
    # justo en el borde entre la fila 1 y la 2.
    "primera_fila_y_plumber": 177.2,
    "row_height": 14.15,
    "total_filas": 40,
    # Verticales reales: 34.9 | 351.5 | 427.0 | 502.7 | 578.4
    # → Correo electrónico | Promovido | Repitente | Reingreso. Tampoco hay
    # columna de "No." acá.
    "columnas": {
        "correo": {"x": 40, "w": 300},        # 34.9 - 351.5 (texto a la izquierda)
        "promovido": {"x": 389.3, "w": 70},   # 351.5 - 427.0 (marcar X)
        "repitente": {"x": 464.9, "w": 70},   # 427.0 - 502.7 (marcar X)
        "reingreso": {"x": 540.6, "w": 70},   # 502.7 - 578.4 (marcar X)
    },
}

# --- CALIFICACIONES: SPREAD DE DOS PÁGINAS POR ASIGNATURA (v2.19.7) ---
#
# Medido sobre las cabeceras P1/RP1/P2/RP2/P3/RP3/P4/RP4 del template. La
# geometría es IDÉNTICA en todas las asignaturas y en los seis grados de
# secundaria (verificado en 1ro, 4to y 6to, sobre tres asignaturas cada uno),
# así que estos centros valen para todo el registro y no para una página suelta.
#
# Cada página lleva DOS bloques de ocho columnas. En orden de lectura:
#   página izquierda  → bloque 1 (competencia 1) y bloque 2 (competencia 2)
#   página derecha    → bloque 3 (competencia 3) y bloque 4 (competencia 4)
#
# El template rotula esos bloques con los códigos de competencia específica del
# MINERD —para Inglés: CE-LEI1 / CE-LEI2+CE-LEI3 / CE-LEI4+CE-LEI7 /
# CE-LEI5+CE-LEI6—, es decir agrupa siete competencias específicas en cuatro
# bloques evaluables. EducaOne numera las competencias 1-4
# (CalificacionSecundaria.competencia_numero), que es exactamente la numeración
# que usa el propio bloque resumen del template ("PC1: Competencia 1" …
# "PC4: Competencia 4"). Por eso el mapeo es posicional: bloque n ← competencia n.
CALIF_SPREAD = {
    # Filas: los números 1-40 vienen pre-impresos en el template; el centro de
    # la fila 1 está en 187.80 y la separación es 14.17 (medido).
    "centro_fila1_plumber": 187.80,
    "row_height": 14.17,
    "izq": {
        1: {"p1": 73.1, "rp1": 105.5, "p2": 137.9, "rp2": 170.4,
            "p3": 202.8, "rp3": 235.3, "p4": 267.7, "rp4": 300.1},
        2: {"p1": 332.7, "rp1": 365.1, "p2": 397.5, "rp2": 430.0,
            "p3": 462.4, "rp3": 494.9, "p4": 527.3, "rp4": 559.7},
    },
    "der": {
        3: {"p1": 66.2, "rp1": 91.8, "p2": 117.4, "rp2": 143.1,
            "p3": 168.7, "rp3": 194.4, "p4": 220.0, "rp4": 245.6},
        4: {"p1": 271.4, "rp1": 297.0, "p2": 322.6, "rp2": 348.3,
            "p3": 373.9, "rp3": 399.6, "p4": 425.2, "rp4": 450.8},
    },
    # Bloque "Promedio de Competencias Específicas" + Calificación final.
    #
    # v2.19.7 (3): centros RE-MEDIDOS sobre las líneas verticales del template
    # —463.7 | 486.1 | 508.5 | 530.9 | 553.3 | 575.8, idénticas en las tres
    # asignaturas y los tres grados comprobados—. Los valores anteriores
    # (480, 502, 525, 547) caían unos 5 puntos a la derecha del centro de su
    # casilla. El de la Calificación final ya estaba bien.
    #
    # Cada columna es el promedio FINAL de UNA competencia: el template las
    # rotula "PC1: Competencia 1" … "PC4: Competencia 4".
    "resumen": {"pc1": 474.9, "pc2": 497.3, "pc3": 519.7, "pc4": 542.1, "cf": 564.6},
}

# --- ASISTENCIA (Pgs 17+) ---
# Coordenadas EXACTAS medidas del template PDF de 1er grado
# Página Letter (612x792), coordenadas plumber (0=arriba)
ASISTENCIA_TABLE = {
    "primera_fila_y_plumber": 179.88,  # y_plumber del centro de la fila 1
    "row_height": 14.21,               # espaciado exacto entre filas
    "total_filas": 40,
    # Mes izquierdo - centros exactos de cada columna de día
    "mes_izq_nombre_x": 150,
    "mes_izq_nombre_y_plumber": 115.9,
    # Fila "DÍAS" del template MINERD: medido en 169.3 (entre los números fijos
    # del template en 150.8 y la primera fila de datos en 180.7).
    # Aquí se escriben los días reales trabajados (19, 26, 3, 4, ...) sin tapar
    # los números fijos 1-21 de cabecera del template.
    "mes_izq_dias_header_y_plumber": 169.3,
    "mes_izq_dia_centers": [
        53.05, 64.55, 76.04, 87.53, 99.03, 110.52, 122.02, 133.50,
        145.00, 156.50, 167.99, 179.48, 190.97, 202.47, 213.96,
        225.45, 236.94, 248.44, 259.94, 271.43, 282.92
    ],
    "mes_izq_total_x": 294.42,
    "mes_izq_porcentaje_x": 305.90,
    # Mes derecho - centros exactos
    "mes_der_nombre_x": 440,
    "mes_der_nombre_y_plumber": 115.9,
    "mes_der_dias_header_y_plumber": 169.3,  # Fila DÍAS real (ver mes_izq)
    "mes_der_dia_centers": [
        317.40, 328.89, 340.38, 351.88, 363.38, 374.87, 386.36, 397.86,
        409.35, 420.84, 432.33, 443.82, 455.32, 466.81, 478.31,
        489.80, 501.30, 512.78, 524.28, 535.77, 547.26
    ],
    "mes_der_total_x": 558.76,
    "mes_der_porcentaje_x": 570.25,
    # Nombre del docente
    "docente_x": 115,         # 'DOCENTE' termina en x=96.6, necesita separación visual
    "docente_y_plumber": 92,
    # Compatibilidad con formato viejo (se usan los arrays de centers ahora)
    "mes_izq_dia1_x": 53.05,
    "mes_izq_dia_spacing": 11.49,
    "mes_der_dia1_x": 317.40,
    "mes_der_dia_spacing": 11.49,
}

# --- ASISTENCIA COMPACTA: 4 meses × 10 días (Pgs 47-55) ---
#
# R3.1 hardening. Educación Artística, Educación Física y FIHR usan en el
# template una rejilla DISTINTA de la de las seis asignaturas troncales: en vez
# de 5 páginas de 2 meses × 21 días, ocupan 3 páginas de 4 meses × 10 días. Son
# asignaturas de pocas horas semanales, así que 10 columnas de día por mes
# bastan; el MINERD comprime tres asignaturas donde las otras usan cinco hojas.
#
# CALIBRACIÓN — cómo se obtuvieron estos números
# ----------------------------------------------
# Se extrajeron las líneas vectoriales de las 54 páginas reales (6 grados × 9
# páginas 47-55) de los templates oficiales del repo. Resultados:
#
#   * cada página tiene EXACTAMENTE 49 líneas verticales de rejilla entre
#     x=47.4 y x=577.1, es decir 48 celdas = 4 bloques × (10 días + T + %);
#   * la dispersión entre las 54 páginas es 0.0000 pt dentro de cada paridad:
#     la geometría es IDÉNTICA en los seis grados, así que NO hacen falta mapas
#     por grado;
#   * las páginas PARES están desplazadas +0.4364 pt en X respecto a las
#     impares —constante en las 49 líneas—. Se modela explícitamente en vez de
#     promediarse;
#   * filas: 41 líneas horizontales, primera en y=180.485 y paso 14.1719,
#     40 estudiantes; idéntico en las 54 páginas;
#   * rótulos: 4 "Mes", 1 "DOCENTE" y 1 "DÍAS" por página, en las 54.
#
# VALIDACIÓN INDEPENDIENTE: los centros derivados de estas v-lines se
# compararon contra los dígitos 1-10/T/% que el propio template imprime en la
# cabecera. Desviación MÁXIMA sobre 54 páginas × 48 columnas = 0.13 pt, con
# celdas de 11.03 pt de ancho. La suite R3.1 vuelve a comprobarlo.
#
# Nada de esto altera la rejilla de 2 meses: ASISTENCIA_TABLE queda intacta.
_ASISTENCIA_4M_VLINES_IMPAR = [
    47.43, 58.47, 69.50, 80.53, 91.57, 102.60, 113.64, 124.67, 135.71, 146.74,
    157.77, 168.81, 179.84, 190.88, 201.91, 212.95, 223.98, 235.01, 246.05,
    257.08, 268.12, 279.15, 290.19, 301.22, 312.25, 323.29, 334.32, 345.36,
    356.39, 367.43, 378.46, 389.49, 400.53, 411.56, 422.60, 433.63, 444.67,
    455.70, 466.73, 477.77, 488.80, 499.84, 510.87, 521.90, 532.94, 543.97,
    555.01, 566.04, 577.08,
]

ASISTENCIA_TABLE_4MESES = {
    "vlines_impar": _ASISTENCIA_4M_VLINES_IMPAR,
    # Desplazamiento medido de las páginas pares (48, 50, 52, 54).
    "dx_pagina_par": 0.4364,
    "bloques": 4,
    "dias_por_bloque": 10,
    "cols_por_bloque": 12,           # 10 días + T + %
    "primera_fila_y_plumber": 180.485,
    "row_height": 14.1719,
    "total_filas": 40,
    # Fila "DÍAS" que el template deja en blanco para los días realmente
    # trabajados, justo debajo de los números fijos 1-10 (top=149.4).
    "dias_header_y_plumber": 169.4,
    # Fila del nombre del mes, a la derecha del rótulo "Mes" de cada bloque.
    "nombre_y_plumber": 115.9,
    "nombre_x_impar": [75.7, 208.1, 340.5, 472.9],
    "nombre_max_width": 100.0,
    # El template imprime UN solo campo DOCENTE por página.
    "docente_x": 115.0,
    "docente_y_plumber": 92.0,
}


def _asistencia_4meses_bloques(pagina: int) -> List[Dict]:
    """
    Centros de columna de los 4 bloques de mes de una página 47-55.

    `pagina` es el número 1-based del Registro: su paridad decide el
    desplazamiento medido de +0.4364 pt. Devuelve, por bloque, los 10 centros
    de día, el de T, el de % y los bordes del bloque (estos últimos solo para
    que los tests puedan comprobar que nada se sale de la celda).
    """
    t = ASISTENCIA_TABLE_4MESES
    dx = t["dx_pagina_par"] if pagina % 2 == 0 else 0.0
    v = [x + dx for x in t["vlines_impar"]]
    ancho = t["cols_por_bloque"]
    bloques = []
    for m in range(t["bloques"]):
        base = m * ancho
        bloques.append({
            "dias": [(v[base + k] + v[base + k + 1]) / 2 for k in range(t["dias_por_bloque"])],
            "total_x": (v[base + 10] + v[base + 11]) / 2,
            "porcentaje_x": (v[base + 11] + v[base + 12]) / 2,
            "nombre_x": t["nombre_x_impar"][m] + dx,
            "x0": v[base],
            "x1": v[base + ancho],
        })
    return bloques

# --- CALIFICACIONES COMPLETIVAS / EXTRAORDINARIAS / ESPECIALES (Pgs 150+) ---
# v2.20.1-B2: los x-center se DERIVAN de las v-lines oficiales del template,
# (left + right) / 2, en vez de valores aproximados a mano. Los nombres de
# columna representan EXACTAMENTE el encabezado oficial MINERD, en orden:
#   No | C.F. |
#   COMPLETIVA:      50% C.F. | C.E.C | 50% C.E.C | C.C.F
#   EXTRAORDINARIA:  30% C.F. | C.E.EX | 70% C.E.EX | C.EX.F
#   ESPECIALES:      C.F. | C.E
#   SITUACIÓN FINAL EN LA ASIGNATURA:  A | R
_COMPLETIVA_VLINES = [
    37.5, 54.4, 98.4, 137.9, 177.6, 217.3, 257.0, 296.7,
    336.3, 376.0, 415.7, 455.4, 495.1, 534.8, 574.5,
]
_COMPLETIVA_COLS_ORDER = [
    "numero",         # 37.5 - 54.4   (ya impreso en el template)
    "cf",             # 54.4 - 98.4   C.F. oficial (entera)
    "comp_cf_50",     # 98.4 - 137.9  50% C.F. (de la CF EXACTA)
    "comp_cec",       # 137.9 - 177.6 C.E.C (nota examen completivo)
    "comp_cec_50",    # 177.6 - 217.3 50% C.E.C
    "comp_ccf",       # 217.3 - 257.0 C.C.F (completiva_final, almacenada)
    "extra_cf_30",    # 257.0 - 296.7 30% C.F. (de la CF EXACTA)
    "extra_ceex",     # 296.7 - 336.3 C.E.EX
    "extra_ceex_70",  # 336.3 - 376.0 70% C.E.EX
    "extra_final",    # 376.0 - 415.7 C.EX.F (extraordinaria_final, almacenada)
    "espec_cf",       # 415.7 - 455.4 C.F. oficial (bloque especial)
    "espec_ce",       # 455.4 - 495.1 C.E.
    "situacion_a",    # 495.1 - 534.8 A (aprobado) — nota_final
    "situacion_r",    # 534.8 - 574.5 R (reprobado) — nota_final
]
COMPLETIVA_TABLE = {
    "primera_fila_y_plumber": 179.6,
    "row_height": 14.2,
    "total_filas": 40,
    # v2.20.1.1 — ajuste visual del nombre del docente. El label "DOCENTE" del
    # template ocupa x≈64.2–105.1, y_top≈72.9–81.7 (baseline PDF ≈ 710.3),
    # idéntico en los 6 grados. Antes docente_x=100 pisaba el label y
    # docente_y_plumber=73 (baseline PDF 719) lo dejaba ~9 pt por encima.
    # Ahora el nombre arranca después del recuadro y su baseline coincide con
    # la del label. No toca ninguna otra celda (row_height, primera_fila_y y
    # las 13 columnas siguen igual).
    "docente_x": 128,
    "docente_y_plumber": 82,
    "columnas": {
        name: {
            "x": round((_COMPLETIVA_VLINES[i] + _COMPLETIVA_VLINES[i + 1]) / 2, 2),
            "left": _COMPLETIVA_VLINES[i],
            "right": _COMPLETIVA_VLINES[i + 1],
            "w": round(_COMPLETIVA_VLINES[i + 1] - _COMPLETIVA_VLINES[i], 2),
        }
        for i, name in enumerate(_COMPLETIVA_COLS_ORDER)
    },
}

# --- INDICADORES DE LOGRO (R2) ---
# Tabla "ESPECIFICACIÓN CURRICULAR APLICADA POR PERÍODO", una página por
# asignatura y por período. Columnas del template: CE | Indicadores de Logro |
# Contenidos Claves. EducaOne solo posee el texto de "Indicadores de Logro",
# así que SOLO se escribe en esa columna; CE y Contenidos Claves quedan
# intactos (no se inventa contenido).
#
# Geometría verificada sobre el template (idéntica en los 6 grados, pág. 612x792):
#   v-lines : 36.2 | 96.0 | 335.8 | 575.5   -> col "Indicadores de Logro" = 96.0..335.8
#   h-lines : 36.2 (título) | 57.9 | 79.5 (fin encabezados) | 756.0 (fin del cuerpo)
INDICADOR_BOX = {
    "x0": 96.0,
    "x1": 335.8,
    "y_top_plumber": 79.5,     # borde inferior de la fila de encabezados
    "y_bottom_plumber": 756.0,  # borde inferior del cuerpo
    "padding": 4.0,
    "font_size": 8.0,
    "line_height": 10.0,
}

# --- ESPECIFICACIÓN CURRICULAR APLICADA POR PERÍODO (R2.1D) ---
#
# La tabla oficial tiene TRES columnas. `INDICADOR_BOX` (arriba) describe la
# central desde R2; aquí se añaden las otras dos con la geometría medida sobre
# los templates.
#
# Medición: las 216 páginas de la sección (6 grados × 9 asignaturas base ×
# 4 períodos) comparten UNA SOLA firma geométrica, dispersión nula:
#
#   v-lines : 36.25 | 96.01 | 335.76 | 575.50
#   h-lines : 36.25 (título) | 57.86 (encabezados) | 79.47 (inicio cuerpo)
#             | 756.00 (fin cuerpo)
#
# El cuerpo está VACÍO en el template: no hay filas preimpresas que respetar,
# solo los bordes de las tres columnas. `INDICADOR_BOX` coincide con la columna
# central dentro de 0.04 pt, así que se conserva tal cual —lo usa el renderer
# de R2 y su suite— y las dos nuevas llevan el valor exacto medido.
CE_BOX = {
    "x0": 36.25,
    "x1": 96.01,
    "y_top_plumber": 79.47,
    "y_bottom_plumber": 756.0,
    "padding": 4.0,
}
CONTENIDOS_BOX = {
    "x0": 335.76,
    "x1": 575.50,
    "y_top_plumber": 79.47,
    "y_bottom_plumber": 756.0,
    "padding": 4.0,
}

# Escalas admitidas, en orden. NO hay búsqueda continua ni tamaños menores:
# o cabe en una de las dos, o el Registro no se emite.
ESPEC_ESCALAS = ((8.0, 10.0), (6.5, 8.0))


class EspecificacionCurricularOverflow(Exception):
    """
    La especificación curricular de un período no cabe ni en la escala menor.

    Un Registro oficial incompleto no es aceptable: antes que recortar texto
    oficial en silencio, la generación se detiene y el endpoint lo convierte en
    un 422 con el detalle de qué período se pasó y por cuánto. NO se borra ni se
    modifica ningún dato: la decisión de redistribuir es del centro.
    """

    def __init__(self, detalle: Dict):
        self.detalle = detalle
        super().__init__(detalle.get("mensaje", "especificacion_curricular_no_cabe"))

# Páginas (1-indexed) del PERÍODO 1 de cada asignatura BASE, por ciclo. Los
# períodos 2, 3 y 4 son las tres páginas siguientes.
# Ciclo 1 (1ro-3ro): bloques regulares de 6 págs (2 de referencia + 4 períodos).
# Ciclo 2 (4to-6to): irregular, porque los bloques de Salida Optativa se
# intercalan entre las asignaturas base. Verificado página por página en los
# seis templates; el orden es el de ASIGNATURAS_CICLO_1 (las 9 base).
INDICADORES_P1_CICLO_1 = [65, 71, 77, 83, 89, 95, 101, 107, 113]
INDICADORES_P1_CICLO_2 = [77, 95, 107, 113, 125, 137, 149, 155, 161]


def pagina_indicador(ciclo: int, asig_idx: int, periodo: int) -> Optional[int]:
    """Página (1-indexed) de la tabla de indicadores de una asignatura/período.

    Devuelve None si el índice de asignatura no es una de las 9 base (p. ej.
    Salida Optativa, cuyo mapeo por modalidad aún no existe — ver R3).
    """
    base = INDICADORES_P1_CICLO_2 if ciclo == 2 else INDICADORES_P1_CICLO_1
    if not (0 <= asig_idx < len(base)) or periodo not in (1, 2, 3, 4):
        return None
    return base[asig_idx] + (periodo - 1)


# --- PROMOCIÓN DEL GRADO (Pgs 159+) ---
# Spread landscape - cada página muestra la mitad
# V-lines pg 159: 36.8, 48.7, 190.7, 332.7, luego cada ~20.2
# Columnas: No | Apellidos | Nombres | [por asignatura: Final, Completivo, Extraordinario, Especial] | Situación
PROMOCION_TABLE = {
    "primera_fila_y_plumber": 179.9,
    "row_height": 14.15,
    "total_filas": 40,
    "columnas_pg_izq": {
        "numero": {"x": 41, "w": 10},
        "apellidos": {"x": 118, "w": 138},     # 48.7 - 190.7
        "nombres": {"x": 260, "w": 138},       # 190.7 - 332.7
        # Asignaturas empiezan en x=332.7, cada una tiene 4 sub-columnas de ~20.2
        "asig_inicio_x": 332.7,
        "asig_sub_width": 20.2,
        "sub_cols": ["final", "completivo", "extraordinario", "especial"],
    },
    # Página derecha continúa las asignaturas y termina con situación final
    "columnas_pg_der": {
        # Continúa desde donde quedó la izquierda
        # La posición X depende de cuántas asignaturas caben en la izq
        "situacion_final_x": 555,
        "situacion_final_w": 18,
    },
}


# ============================================================================
# FUNCIONES AUXILIARES
# ============================================================================

def _draw_text(c: canvas.Canvas, x: float, y: float, text: str,
               font: str = FONT_NORMAL, size: float = FONT_SIZE_TABLA,
               center: bool = False, max_width: float = 0):
    """Dibuja texto en el canvas con color azul."""
    c.setFont(font, size)
    c.setFillColorRGB(*AZUL)
    
    if not text:
        return
    
    text = str(text)
    
    # Truncar si excede max_width
    if max_width > 0:
        while c.stringWidth(text, font, size) > max_width and len(text) > 1:
            text = text[:-1]
    
    if center:
        tw = c.stringWidth(text, font, size)
        x = x - tw / 2
    
    c.drawString(x, y, text)


def _draw_x_mark(c: canvas.Canvas, x: float, y: float, size: float = 8):
    """Dibuja una X como marca de checkbox."""
    c.setFont(FONT_BOLD, size)
    c.setFillColorRGB(*AZUL)
    c.drawString(x, y, "X")


def _create_overlay_page(draw_func, *args, **kwargs) -> io.BytesIO:
    """Crea un PDF de una página con el contenido del overlay."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    try:
        draw_func(c, *args, **kwargs)
    except Exception as e:
        # Si la función de dibujo falla, generar página vacía
        pass
    c.showPage()  # Asegurar que siempre hay al menos 1 página
    c.save()
    buf.seek(0)
    return buf


# ============================================================================
# FUNCIONES DE DIBUJO POR SECCIÓN
# ============================================================================

def draw_portada(c: canvas.Canvas, datos: Dict):
    """
    Dibuja datos en la portada.
    datos: {
        "anio_inicio": "24",  # 2 dígitos
        "anio_fin": "25",
        "seccion": "A",
        "salida_optativa": "Informática"  # Solo 4to-6to
    }
    """
    coords = PORTADA_COORDS
    
    if datos.get("anio_inicio"):
        _draw_text(c, coords["anio_inicio_x"], coords["anio_inicio_y"],
                   datos["anio_inicio"], size=FONT_SIZE_PORTADA_ANIO)
    
    if datos.get("anio_fin"):
        _draw_text(c, coords["anio_fin_x"], coords["anio_fin_y"],
                   datos["anio_fin"], size=FONT_SIZE_PORTADA_ANIO)
    
    if datos.get("seccion"):
        _draw_text(c, coords["seccion_x"], coords["seccion_y"],
                   datos["seccion"], size=FONT_SIZE_PORTADA_SECCION)
    
    if datos.get("salida_optativa"):
        _draw_text(c, coords["salida_optativa_x"], coords["salida_optativa_y"],
                   datos["salida_optativa"], size=FONT_SIZE_PORTADA_SECCION)


def draw_centro_educativo(c: canvas.Canvas, datos: Dict):
    """
    Dibuja datos del centro educativo.
    datos: {
        "nombre_centro": str,
        "direccion": str,
        "correo_centro": str,
        "telefono_centro": str,
        "codigo_sigerd": str,
        "codigo_cartografia": str,
        "director": str,
        "correo_director": str,
        "telefono_director": str,
        "docente_encargado": str,
        "correo_docente": str,
        "telefono_docente": str,
        "sector": "publico" | "privado" | "semioficial",
        "zona": "urbana" | "urbana_marginal" | "urbana_turistica" | "rural" | "rural_aislada" | "rural_turistica",
        "jornada": "jee" | "matutina" | "vespertina" | "nocturna",
        "regional": str,
        "distrito": str,
    }
    """
    coords = CENTRO_COORDS
    
    # Campos de texto
    text_fields = [
        "nombre_centro", "direccion", "correo_centro", "telefono_centro",
        "codigo_sigerd", "codigo_cartografia", "director",
        "correo_director", "telefono_director", "docente_encargado",
        "correo_docente", "telefono_docente", "regional", "distrito",
    ]
    
    for field in text_fields:
        if datos.get(field) and field in coords:
            _draw_text(c, coords[field]["x"], coords[field]["y"],
                       datos[field], size=FONT_SIZE_CENTRO, max_width=200)
    
    # Sector (checkbox)
    sector = datos.get("sector", "").lower()
    if sector:
        key = f"sector_{sector}"
        if key in coords:
            _draw_x_mark(c, coords[key]["x"], coords[key]["y"])
    
    # Zona (checkbox)
    zona = datos.get("zona", "").lower()
    if zona:
        key = f"zona_{zona}"
        if key in coords:
            _draw_x_mark(c, coords[key]["x"], coords[key]["y"])
    
    # Jornada (checkbox)
    jornada = datos.get("jornada", "").lower()
    if jornada:
        key = f"jornada_{jornada}"
        if key in coords:
            _draw_x_mark(c, coords[key]["x"], coords[key]["y"])


def draw_datos_estudiantes(c: canvas.Canvas, estudiantes: List[Dict]):
    """
    Dibuja la tabla de datos generales del estudiante (Pg 11).
    estudiantes: lista de hasta 40 dicts con:
    {
        "numero": int,
        "sexo": "F" | "M",
        "dia_nac": str, "mes_nac": str, "anio_nac": str,
        "libro": str, "folio": str, "edad": int,
        "cedula": str, "rne": str,
        "lugar_residencia": str,
        # Si está retirado, se marca al margen con fecha:
        "retirado": bool,
        "fecha_retiro": str (ISO YYYY-MM-DD),
    }
    """
    table = ESTUDIANTES_TABLE
    
    for i, est in enumerate(estudiantes[:40]):
        if not est:
            continue
        
        # Coordenada Y de esta fila (PDF coords)
        row_y_plumber = table["primera_fila_y_plumber"] + (i * table["row_height"])
        # Posicionar texto en medio de la fila
        y = _y(row_y_plumber + table["row_height"] - 3)
        
        cols = table["columnas"]
        
        # v2.19.7: el template no tiene columna de "No." en esta página; el
        # número de lista que se dibujaba acá caía dentro de la casilla de
        # Femenino y parecía una marca de sexo.
        
        # Sexo (marcar X en columna correspondiente)
        sexo = est.get("sexo", "").upper()
        if sexo == "F":
            _draw_x_mark(c, cols["femenino"]["x"], y, size=FONT_SIZE_TABLA)
        elif sexo == "M":
            _draw_x_mark(c, cols["masculino"]["x"], y, size=FONT_SIZE_TABLA)
        
        # Fecha de nacimiento
        for campo, col_name in [("dia_nac", "dia"), ("mes_nac", "mes"), ("anio_nac", "anio")]:
            if est.get(campo):
                _draw_text(c, cols[col_name]["x"], y,
                           str(est[campo]), size=FONT_SIZE_TABLA, center=True)
        
        # Libro, Folio, Edad
        for campo, col_name in [("libro", "libro"), ("folio", "folio"), ("edad", "edad")]:
            if est.get(campo):
                _draw_text(c, cols[col_name]["x"], y,
                           str(est[campo]), size=FONT_SIZE_TABLA, center=True)
        
        # Cédula/Pasaporte
        if est.get("cedula"):
            _draw_text(c, cols["cedula"]["x"], y,
                       est["cedula"], size=FONT_SIZE_TABLA_NOMBRE,
                       max_width=cols["cedula"]["w"])
        
        # RNE
        if est.get("rne"):
            _draw_text(c, cols["rne"]["x"], y,
                       est["rne"], size=FONT_SIZE_TABLA_NOMBRE,
                       max_width=cols["rne"]["w"])
        
        # Lugar de residencia (con marca de RETIRADO si aplica)
        lugar = est.get("lugar_residencia", "") or ""
        if est.get("retirado") and est.get("fecha_retiro"):
            # Anteponer marca de retiro a la dirección. Formato compacto: "RET DD/MM/YY"
            try:
                fr = est["fecha_retiro"]  # YYYY-MM-DD
                marca = f"[RET {fr[8:10]}/{fr[5:7]}/{fr[2:4]}]"
            except Exception:
                marca = "[RETIRADO]"
            lugar_con_marca = f"{marca} {lugar}".strip()
        else:
            lugar_con_marca = lugar
        if lugar_con_marca:
            _draw_text(c, cols["lugar_residencia"]["x"] - 40, y,
                       lugar_con_marca, size=FONT_SIZE_TABLA_NOMBRE,
                       max_width=cols["lugar_residencia"]["w"])


def draw_condicion_inicial(c: canvas.Canvas, estudiantes: List[Dict]):
    """
    Dibuja la tabla de condición inicial (Pg 12).
    estudiantes: lista de dicts con:
    {
        "numero": int,
        "correo": str,
        "condicion": "nuevo" | "promovido" | "repitente" | "reingreso" | "transferido" | "retirado",
        "retirado": bool,            # opcional, si True el estudiante se retiró durante el año
        "fecha_retiro": "YYYY-MM-DD", # opcional
    }

    Si el estudiante está retirado:
      - NO se marca columna de promovido/repitente/reingreso (no aplica).
      - Se imprime una marca textual "RET DD/MM" al lado del correo para
        que quien revise el registro sepa por qué quedó sin marca.
    """
    table = CONDICION_TABLE
    
    for i, est in enumerate(estudiantes[:40]):
        if not est:
            continue
        
        row_y_plumber = table["primera_fila_y_plumber"] + (i * table["row_height"])
        y = _y(row_y_plumber + table["row_height"] - 3)
        
        cols = table["columnas"]
        
        # v2.19.7: sin columna de "No." en el template (ver CONDICION_TABLE).
        
        # Correo electrónico (con marca de retiro si aplica)
        es_retirado = bool(est.get("retirado")) or str(est.get("condicion", "")).lower() == "retirado"
        correo = est.get("correo") or ""
        if es_retirado:
            try:
                fr = est.get("fecha_retiro") or ""
                marca_ret = f"[RET {fr[8:10]}/{fr[5:7]}]" if fr else "[RETIRADO]"
            except Exception:
                marca_ret = "[RETIRADO]"
            correo = f"{marca_ret} {correo}".strip()
        if correo:
            _draw_text(c, cols["correo"]["x"], y,
                       correo, size=FONT_SIZE_TABLA_NOMBRE,
                       max_width=cols["correo"]["w"])
        
        # Condición (marcar X) — pero NO si está retirado
        if not es_retirado:
            # Aceptar tanto "condicion" como "condicion_entrada" (el endpoint manda esta última)
            condicion = str(est.get("condicion") or est.get("condicion_entrada") or "").lower()
            if condicion in ("nuevo", "promovido", ""):
                _draw_x_mark(c, cols["promovido"]["x"], y, size=FONT_SIZE_TABLA)
            elif condicion == "repitente":
                _draw_x_mark(c, cols["repitente"]["x"], y, size=FONT_SIZE_TABLA)
            elif condicion in ("reingreso", "transferido"):
                _draw_x_mark(c, cols["reingreso"]["x"], y, size=FONT_SIZE_TABLA)


def draw_asistencia(c: canvas.Canvas, datos_mes: Dict, es_mes_derecho: bool = False):
    """
    Dibuja asistencia de un mes en media página.
    datos_mes: {
        "nombre_mes": str,
        "docente": str,
        "asistencias": [
            {  # por estudiante (hasta 40)
                "dias": [None/str] * 21,  # "P"=presente, "A"=ausente, "E"=excusa
                "total": int,
                "porcentaje": float,
            }
        ]
    }
    """
    table = ASISTENCIA_TABLE
    prefix = "mes_der" if es_mes_derecho else "mes_izq"
    
    # Centros exactos de las columnas de días
    dia_centers = table.get(f"{prefix}_dia_centers")
    if not dia_centers:
        dia_centers = [table[f"{prefix}_dia1_x"] + (d * table[f"{prefix}_dia_spacing"]) for d in range(21)]
    
    # Nombre del mes
    if datos_mes.get("nombre_mes"):
        _draw_text(c, table[f"{prefix}_nombre_x"], _y(table[f"{prefix}_nombre_y_plumber"]),
                   datos_mes["nombre_mes"], size=FONT_SIZE_NOTA)

    dias_labels = datos_mes.get("dias_labels", [])
    # Centro vertical de la fila DÍAS (entre h-lines 161.8 y 180.1).
    # _y convierte plumber-top a coord ReportLab; sumamos un pequeño offset para
    # que la baseline quede ~30% del font size por debajo del centro de la celda.
    header_y_plumber = table.get(f"{prefix}_dias_header_y_plumber", table[f"{prefix}_nombre_y_plumber"] + 15)
    header_y = _y(header_y_plumber + 2.2)  # baseline ajustado para centrar visualmente
    for d, valor_dia in enumerate(dias_labels[:21]):
        if d >= len(dia_centers):
            break
        # NOTA: los números fijos 1-21 del template (top=150.8) NO se tapan.
        # Aquí escribimos en la fila "DÍAS" justo debajo (top≈169.3), que el
        # template MINERD deja en blanco para los días reales trabajados.
        _draw_text(c, dia_centers[d], header_y, str(valor_dia), size=7, center=True)
    
    # Nombre del docente (solo en el mes izquierdo del primer par)
    if not es_mes_derecho and datos_mes.get("docente"):
        _draw_text(c, table["docente_x"], _y(table["docente_y_plumber"]),
                   datos_mes["docente"], size=FONT_SIZE_NOTA, max_width=200)
    
    for i, est in enumerate(datos_mes.get("asistencias", [])[:40]):
        if not est:
            continue
        
        row_y_plumber = table["primera_fila_y_plumber"] + (i * table["row_height"])
        y = _y(row_y_plumber + table["row_height"] / 2 + 2)
        
        # Días 1-21
        for d, valor in enumerate(est.get("dias", [])[:21]):
            if valor is None or valor == "":
                continue
            if d >= len(dia_centers):
                break
            
            x = dia_centers[d]
            
            if valor is True or valor == "P":
                mark = "P"
            elif valor == "A":
                mark = "A"
            elif valor == "E":
                mark = "E"
            elif valor == "T":
                mark = "T"
            elif valor == "J":
                mark = "J"
            else:
                mark = str(valor)
            
            _draw_text(c, x, y, mark, size=FONT_SIZE_ASISTENCIA, center=True)
        
        # Total y porcentaje
        if est.get("total") is not None:
            _draw_text(c, table[f"{prefix}_total_x"], y,
                       str(est["total"]), size=FONT_SIZE_ASISTENCIA, center=True)
        
        if est.get("porcentaje") is not None:
            _draw_text(c, table[f"{prefix}_porcentaje_x"], y,
                       f"{est['porcentaje']:.0f}", size=FONT_SIZE_ASISTENCIA, center=True)


def draw_asistencia_4meses(c: canvas.Canvas, meses_pagina: List[Optional[Dict]],
                           pagina: int, docente: str = "", asignatura: str = ""):
    """
    Dibuja una página COMPLETA de la rejilla compacta 4 meses × 10 días
    (páginas 47-55: Ed. Artística, Ed. Física y FIHR).

    `meses_pagina` son los hasta 4 meses de ESA página, en orden; los huecos
    pueden venir None o vacíos y se dejan en blanco. Cada mes tiene la misma
    forma que en la rejilla de 2 meses (`nombre_mes`, `dias_labels`,
    `asistencias` con `dias`/`total`/`porcentaje`), así que NO hay ninguna
    transformación de datos: solo cambian las coordenadas.

    Los estados P/A/E/T/J y el significado de total y porcentaje son EXACTAMENTE
    los mismos que en `draw_asistencia`. Un valor None o "" se deja en blanco:
    nunca se inventa una asistencia.
    """
    t = ASISTENCIA_TABLE_4MESES
    bloques = _asistencia_4meses_bloques(pagina)
    max_dias = t["dias_por_bloque"]

    # Docente: el template imprime un único campo por página.
    if docente:
        _draw_text(c, t["docente_x"], _y(t["docente_y_plumber"]),
                   docente, size=FONT_SIZE_NOTA, max_width=200)

    for m, datos_mes in enumerate(meses_pagina[:t["bloques"]]):
        if not datos_mes:
            continue
        blk = bloques[m]

        if datos_mes.get("nombre_mes"):
            _draw_text(c, blk["nombre_x"], _y(t["nombre_y_plumber"]),
                       datos_mes["nombre_mes"], size=FONT_SIZE_NOTA,
                       max_width=t["nombre_max_width"])

        # Fila "DÍAS": los días realmente trabajados. La hoja oficial solo tiene
        # 10 huecos por mes en esta rejilla; si se capturaron más, se avisa en
        # vez de desbordar la celda o de escribir fuera de la tabla.
        dias_labels = datos_mes.get("dias_labels", []) or []
        if len(dias_labels) > max_dias:
            logger.warning(
                "Asistencia compacta (pg %s, %s, mes %r): %d días capturados y la hoja "
                "oficial solo tiene %d columnas; se imprimen los primeros %d.",
                pagina, asignatura or "?", datos_mes.get("nombre_mes", ""),
                len(dias_labels), max_dias, max_dias,
            )
        header_y = _y(t["dias_header_y_plumber"] + 2.2)
        for d, valor_dia in enumerate(dias_labels[:max_dias]):
            _draw_text(c, blk["dias"][d], header_y, str(valor_dia), size=7, center=True)

        for i, est in enumerate(datos_mes.get("asistencias", [])[:t["total_filas"]]):
            if not est:
                continue
            row_y_plumber = t["primera_fila_y_plumber"] + (i * t["row_height"])
            y = _y(row_y_plumber + t["row_height"] / 2 + 2)

            for d, valor in enumerate((est.get("dias") or [])[:max_dias]):
                if valor is None or valor == "":
                    continue
                if valor is True or valor == "P":
                    mark = "P"
                elif valor in ("A", "E", "T", "J"):
                    mark = valor
                else:
                    mark = str(valor)
                _draw_text(c, blk["dias"][d], y, mark,
                           size=FONT_SIZE_ASISTENCIA, center=True)

            if est.get("total") is not None:
                _draw_text(c, blk["total_x"], y, str(est["total"]),
                           size=FONT_SIZE_ASISTENCIA, center=True)

            if est.get("porcentaje") is not None:
                _draw_text(c, blk["porcentaje_x"], y, f"{est['porcentaje']:.0f}",
                           size=FONT_SIZE_ASISTENCIA, center=True)


def _fila_completiva(cd: Optional[Dict]) -> Optional[Dict]:
    """v2.20.1-B2: traduce la entrada de calificaciones de UN estudiante/asignatura
    a las 13 columnas oficiales de la página Completiva/Extraordinaria/Especial.

    Fuente ÚNICA de la cascada: el dict serializado `evaluacion_extra` (de
    EvaluacionExtraSecundaria). Las notas FINALES se toman almacenadas, NO se
    recalculan. Los porcentajes intermedios se calculan desde la CF EXACTA
    (`ev.cf_original` / `cf_exacto`), como el Boletín MINERD en producción.

    Devuelve un dict con solo las columnas que tienen dato, o None si la fila
    no aporta nada (ni CF ni evaluación extra).
    """
    if not cd:
        return None
    cf = cd.get('cf')                 # CF OFICIAL (entera, v2.20.0)
    cf_exacto = cd.get('cf_exacto')   # CF EXACTA interna (para %)
    ev = cd.get('evaluacion_extra')   # dict serializado o None

    if cf is None and not ev:
        return None

    # CF OFICIAL: redondeo académico (.5 sube), no round() builtin. La ruta
    # moderna ya entrega `cf` entero, pero el fallback legacy puede traer decimal.
    cf_oficial = redondear_calificacion_final(cf) if cf is not None else None

    # Base EXACTA para los porcentajes: preferir cf_original de la evaluación
    # extra (es el valor exacto cacheado), luego cf_exacto, luego la CF oficial.
    if ev is not None and ev.get('cf_original') is not None:
        base_pct = ev['cf_original']
    elif cf_exacto is not None:
        base_pct = cf_exacto
    else:
        base_pct = cf

    reprobo_ano = cf_oficial is not None and cf_oficial < 70
    fila: Dict = {}

    # --- C.F. oficial ---
    if cf_oficial is not None:
        fila['cf'] = cf_oficial

    # --- COMPLETIVA ---
    if reprobo_ano and base_pct is not None:
        fila['comp_cf_50'] = round(base_pct * 0.5, 1)
    if ev is not None and ev.get('cec') is not None:
        fila['comp_cec'] = ev['cec']
        fila['comp_cec_50'] = round(ev['cec'] * 0.5, 1)
    if ev is not None and ev.get('completiva_final') is not None:
        fila['comp_ccf'] = ev['completiva_final']

    # --- EXTRAORDINARIA (se "inicia" al no aprobar completiva o al cargar CEEX) ---
    extra_iniciada = ev is not None and (
        ev.get('ceex') is not None
        or ev.get('fase_pendiente') == 'extraordinaria'
        or (ev.get('completiva_final') is not None and ev['completiva_final'] < 70)
    )
    if extra_iniciada and base_pct is not None:
        fila['extra_cf_30'] = round(base_pct * 0.3, 1)
    if ev is not None and ev.get('ceex') is not None:
        fila['extra_ceex'] = ev['ceex']
        fila['extra_ceex_70'] = round(ev['ceex'] * 0.7, 1)
    if ev is not None and ev.get('extraordinaria_final') is not None:
        fila['extra_final'] = ev['extraordinaria_final']

    # --- ESPECIAL (se "inicia" al no aprobar extraordinaria o al cargar CE) ---
    espec_iniciada = ev is not None and (
        ev.get('ce') is not None
        or ev.get('fase_pendiente') == 'especial'
        or (ev.get('extraordinaria_final') is not None and ev['extraordinaria_final'] < 70)
    )
    if espec_iniciada and cf_oficial is not None:
        fila['espec_cf'] = cf_oficial
    if ev is not None and ev.get('ce') is not None:
        fila['espec_ce'] = ev['ce']

    # --- SITUACIÓN FINAL EN LA ASIGNATURA (A / R) ---
    # Regla B2: NO marcar A ni R mientras haya una fase pendiente. La columna
    # afirma un resultado FINAL; un estado provisional 'reprobado' no lo es.
    a = r = None
    if ev is not None:
        fp = ev.get('fase_pendiente')
        if fp in ('completiva', 'extraordinaria', 'especial'):
            a = r = None
        else:
            cond = ev.get('condicion_final') or ''
            nf = ev.get('nota_final')
            if cond.startswith('aprobado_'):
                a = nf
            elif cond == 'reprobado':
                r = nf
    else:
        # Sin evaluación extra: solo cuenta la CF normal.
        if cf_oficial is not None and cf_oficial >= 70:
            a = cf_oficial
        # cf_oficial < 70 y sin ev => pendiente de Completiva => A/R vacío.

    if a is not None:
        fila['situacion_a'] = a
    if r is not None:
        fila['situacion_r'] = r

    return fila or None


def draw_completiva(c: canvas.Canvas, datos: Dict):
    """
    Dibuja calificaciones completivas / extraordinarias / especiales
    (1 página por asignatura). v2.20.1-B2.

    datos: {
        "docente": str,
        "calificaciones": [ <fila> | None, ... ]   # índice = fila del estudiante
    }
    donde <fila> es lo que devuelve `_fila_completiva`: subconjunto de
      cf, comp_cf_50, comp_cec, comp_cec_50, comp_ccf,
      extra_cf_30, extra_ceex, extra_ceex_70, extra_final,
      espec_cf, espec_ce, situacion_a, situacion_r
    Un valor 0 es válido y SE dibuja (se usa `is not None`, nunca `if valor`).
    """
    table = COMPLETIVA_TABLE

    # Docente
    if datos.get("docente"):
        _draw_text(c, table["docente_x"], _y(table["docente_y_plumber"]),
                   datos["docente"], size=FONT_SIZE_NOTA, max_width=250)

    for i, est in enumerate(datos.get("calificaciones", [])[:40]):
        if not est:
            continue

        row_y_plumber = table["primera_fila_y_plumber"] + (i * table["row_height"])
        y = _y(row_y_plumber + table["row_height"] - 3)

        for col_name, col_info in table["columnas"].items():
            if col_name == "numero":
                continue  # El número ya está impreso en el template

            valor = est.get(col_name)
            if valor is None:
                continue  # 0 SÍ se dibuja; None no

            texto = _fmt_nota(valor)  # entero si ~entero, si no 1 decimal (igual que el Boletín)
            if texto == "":
                continue
            _draw_text(c, col_info["x"], y, texto,
                       size=FONT_SIZE_NOTA, center=True)


def _wrap_texto(texto: str, ancho_max: float, font: str, size: float) -> List[str]:
    """Parte `texto` en líneas que caben en `ancho_max`. Determinista.

    Respeta los saltos de línea que escribió el docente. Una palabra más ancha
    que la columna se corta por caracteres en vez de desbordar la caja.
    """
    from reportlab.pdfbase.pdfmetrics import stringWidth

    lineas: List[str] = []
    for parrafo in str(texto).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        palabras = parrafo.split()
        if not palabras:
            lineas.append("")
            continue
        actual = ""
        for palabra in palabras:
            # Palabra sola más ancha que la columna: partirla por caracteres.
            while stringWidth(palabra, font, size) > ancho_max:
                corte = len(palabra)
                while corte > 1 and stringWidth(palabra[:corte], font, size) > ancho_max:
                    corte -= 1
                if actual:
                    lineas.append(actual)
                    actual = ""
                lineas.append(palabra[:corte])
                palabra = palabra[corte:]
            tentativa = f"{actual} {palabra}".strip()
            if actual and stringWidth(tentativa, font, size) > ancho_max:
                lineas.append(actual)
                actual = palabra
            else:
                actual = tentativa
        if actual:
            lineas.append(actual)
    return lineas


def draw_indicadores(c: canvas.Canvas, datos: Dict):
    """Escribe los indicadores de logro del período en su columna oficial.

    datos: {"texto": str}. Solo se dibuja dentro de la columna
    "Indicadores de Logro" del template (ver INDICADOR_BOX). Si el texto no
    cabe, se trunca de forma determinista con '…' — NUNCA se dibuja fuera de
    la caja ni se invade la grilla vecina.
    """
    texto = (datos or {}).get("texto")
    if not texto or not str(texto).strip():
        return

    box = INDICADOR_BOX
    pad = box["padding"]
    size = box["font_size"]
    lh = box["line_height"]
    x = box["x0"] + pad
    ancho = (box["x1"] - box["x0"]) - (2 * pad)
    y_top = _y(box["y_top_plumber"]) - pad - size
    y_min = _y(box["y_bottom_plumber"]) + pad
    max_lineas = max(int((y_top - y_min) // lh) + 1, 0)
    if max_lineas <= 0:
        return

    lineas = _wrap_texto(str(texto).strip(), ancho, FONT_NORMAL, size)
    if len(lineas) > max_lineas:
        lineas = lineas[:max_lineas]
        if lineas:
            from reportlab.pdfbase.pdfmetrics import stringWidth
            ultima = lineas[-1]
            while ultima and stringWidth(ultima + "…", FONT_NORMAL, size) > ancho:
                ultima = ultima[:-1]
            lineas[-1] = (ultima + "…") if ultima else "…"

    for i, linea in enumerate(lineas):
        if not linea:
            continue
        _draw_text(c, x, y_top - (i * lh), linea, size=size)


def _espec_capacidad(box: Dict, size: float, line_height: float) -> int:
    """Cuántas líneas de `size` caben en el cuerpo de una columna."""
    y_top = _y(box["y_top_plumber"]) - box["padding"] - size
    y_min = _y(box["y_bottom_plumber"]) + box["padding"]
    return max(int((y_top - y_min) // line_height) + 1, 0)


def _espec_maquetar(datos: Dict, size: float, line_height: float) -> Dict:
    """
    Maqueta un período a una escala dada, SIN dibujar y SIN recortar.

    Devuelve el plan completo —incluidas las líneas que se salen— para que el
    llamador decida: nunca trunca por su cuenta.

      filas_il   : líneas de la columna "Indicadores de Logro"
      marcas_ce  : [(índice_de_línea, ce_codigo)] para alinear cada código CE
                   con el arranque de su grupo
      filas_cc   : líneas de la columna "Contenidos Claves"
      cabe       : bool
    """
    ancho_il = (INDICADOR_BOX["x1"] - INDICADOR_BOX["x0"]) - 2 * INDICADOR_BOX["padding"]
    ancho_cc = (CONTENIDOS_BOX["x1"] - CONTENIDOS_BOX["x0"]) - 2 * CONTENIDOS_BOX["padding"]

    filas_il: List[str] = []
    marcas_ce: List[tuple] = []

    # Los grupos vienen ya ordenados por `orden_ce` desde el loader; se reordena
    # aquí también para que el render sea determinista aunque cambie la fuente.
    grupos = sorted((datos or {}).get("grupos_ce") or [],
                    key=lambda g: (g.get("orden_ce") or 0, g.get("ce_codigo") or ""))
    for grupo in grupos:
        indicadores = sorted(grupo.get("indicadores") or [],
                             key=lambda i: (i.get("orden_il") or 0, i.get("il_codigo") or ""))
        if not indicadores:
            continue
        if filas_il:
            filas_il.append("")            # separación entre grupos de CE
        # El código de la CE se alinea con la PRIMERA línea de su primer IL.
        marcas_ce.append((len(filas_il), grupo.get("ce_codigo") or ""))
        for pos, il in enumerate(indicadores):
            if pos:
                filas_il.append("")        # separación entre indicadores
            etiqueta = f"{il.get('il_codigo') or ''} {il.get('il_texto') or ''}".strip()
            filas_il.extend(_wrap_texto(etiqueta, ancho_il, FONT_NORMAL, size))

    filas_cc: List[str] = []
    for linea in (datos or {}).get("contenidos") or []:
        texto = str(linea)
        if not texto.strip():
            continue                       # una línea vacía no es un contenido
        filas_cc.extend(_wrap_texto(texto, ancho_cc, FONT_NORMAL, size))

    cap_il = _espec_capacidad(INDICADOR_BOX, size, line_height)
    cap_cc = _espec_capacidad(CONTENIDOS_BOX, size, line_height)
    return {
        "size": size,
        "line_height": line_height,
        "filas_il": filas_il,
        "marcas_ce": marcas_ce,
        "filas_cc": filas_cc,
        "capacidad_il": cap_il,
        "capacidad_cc": cap_cc,
        "cabe": len(filas_il) <= cap_il and len(filas_cc) <= cap_cc,
    }


def espec_plan(datos: Dict, contexto: Optional[Dict] = None) -> Dict:
    """
    Elige la escala de una página de especificación curricular.

    Preflight determinista y acotado: se prueba 8/10 y, si algo no cabe, se
    recalcula TODA la página —CE, Indicadores y Contenidos— con 6.5/8. La misma
    escala rige las tres columnas de esa página.

    Si tampoco cabe en 6.5/8 lanza `EspecificacionCurricularOverflow`: no se
    emite un Registro parcial ni se recorta texto oficial.
    """
    plan = None
    for size, lh in ESPEC_ESCALAS:
        plan = _espec_maquetar(datos, size, lh)
        if plan["cabe"]:
            return plan

    ctx = dict(contexto or {})
    detalle = {
        "motivo": "especificacion_curricular_no_cabe",
        "lineas_indicadores": len(plan["filas_il"]),
        "lineas_contenidos": len(plan["filas_cc"]),
        "capacidad": min(plan["capacidad_il"], plan["capacidad_cc"]),
        "capacidad_indicadores": plan["capacidad_il"],
        "capacidad_contenidos": plan["capacidad_cc"],
        "font_size_minimo": plan["size"],
        "mensaje": (
            "La especificación curricular del período excede el espacio disponible "
            "del Registro Escolar. Reduzca o distribuya los indicadores/contenidos "
            "entre períodos."
        ),
    }
    detalle.update(ctx)
    logger.warning(
        "Especificación curricular sin espacio: %s líneas IL / %s líneas CC "
        "para capacidades %s / %s (contexto=%s)",
        detalle["lineas_indicadores"], detalle["lineas_contenidos"],
        plan["capacidad_il"], plan["capacidad_cc"], ctx,
    )
    raise EspecificacionCurricularOverflow(detalle)


def draw_especificacion_curricular(c: canvas.Canvas, datos: Dict):
    """
    Dibuja las TRES columnas de "ESPECIFICACIÓN CURRICULAR APLICADA POR PERÍODO".

    `datos` es el plan que devuelve `espec_plan()` bajo la clave "plan", más el
    contenido ya maquetado. No trunca NUNCA: si algo no cabía, `espec_plan()` ya
    habría abortado la generación antes de llegar aquí.

    CE          : solo `ce_codigo`, una vez por grupo, alineado con el arranque
                  de su primer indicador. El texto completo de una CE ocuparía
                  32 líneas en una columna de 51.8 pt: el MINERD imprime códigos.
    Indicadores : `il_codigo` + `il_texto` verbatim del catálogo oficial.
    Contenidos  : una entrada por línea escrita por el docente, en su orden.

    Nunca se imprime `catalogo_clave`, `orden_ce`, `orden_il` ni la versión
    curricular: son identidad técnica interna.
    """
    plan = (datos or {}).get("plan")
    if not plan:
        return
    size = plan["size"]
    lh = plan["line_height"]

    def _pinta(box, filas, x_extra=0.0):
        x = box["x0"] + box["padding"] + x_extra
        y_top = _y(box["y_top_plumber"]) - box["padding"] - size
        for i, linea in enumerate(filas):
            if linea:
                _draw_text(c, x, y_top - (i * lh), linea, size=size)

    _pinta(INDICADOR_BOX, plan["filas_il"])
    _pinta(CONTENIDOS_BOX, plan["filas_cc"])

    # Códigos de CE, cada uno a la altura de su grupo.
    x_ce = CE_BOX["x0"] + CE_BOX["padding"]
    y_ce_top = _y(INDICADOR_BOX["y_top_plumber"]) - INDICADOR_BOX["padding"] - size
    for indice, ce_codigo in plan["marcas_ce"]:
        if ce_codigo:
            _draw_text(c, x_ce, y_ce_top - (indice * lh), ce_codigo, size=size)


def draw_promocion_izq(c: canvas.Canvas, estudiantes: List[Dict], asignaturas: List[str]):
    """
    Dibuja la página izquierda del spread de promoción.
    estudiantes: lista de dicts con:
    {
        "numero": int,
        "apellidos": str,
        "nombres": str,
        "notas": {
            "asignatura_key": {
                "final": float,
                "completivo": float,
                "extraordinario": float,
                "especial": str,
            }
        }
    }
    """
    table = PROMOCION_TABLE
    cols = table["columnas_pg_izq"]
    
    for i, est in enumerate(estudiantes[:40]):
        if not est:
            continue
        
        row_y_plumber = table["primera_fila_y_plumber"] + (i * table["row_height"])
        y = _y(row_y_plumber + table["row_height"] - 3)
        
        # Número - NO dibujar, ya está impreso en el template
        
        # Apellidos
        if est.get("apellidos"):
            _draw_text(c, cols["apellidos"]["x"] - 65, y,
                       est["apellidos"], size=FONT_SIZE_PROMOCION,
                       max_width=cols["apellidos"]["w"])
        
        # Nombres
        if est.get("nombres"):
            _draw_text(c, cols["nombres"]["x"] - 65, y,
                       est["nombres"], size=FONT_SIZE_PROMOCION,
                       max_width=cols["nombres"]["w"])
        
        # Notas por asignatura (las que caben en esta página)
        notas = est.get("notas", {})
        asig_x = cols["asig_inicio_x"]
        sub_w = cols["asig_sub_width"]
        
        # Calculamos cuántas asignaturas caben en la página izquierda
        # Desde x=332.7 hasta x=575.5 (borde derecho) = ~243 pts
        # Cada asignatura = 4 sub-cols × 20.2 = 80.8 pts
        # Caben ~3 asignaturas en la izquierda
        max_asig_izq = int((575.5 - asig_x) / (sub_w * 4))
        
        for a_idx, asig in enumerate(asignaturas[:max_asig_izq]):
            asig_key = asig.lower().replace(" ", "_").replace("-", "_")
            nota_asig = notas.get(asig_key, {})
            
            base_x = asig_x + (a_idx * sub_w * 4)
            
            for s_idx, sub_col in enumerate(cols["sub_cols"]):
                valor = nota_asig.get(sub_col)
                if valor is not None and valor != "":
                    text = str(valor)
                    if isinstance(valor, float):
                        text = f"{valor:.0f}" if valor == int(valor) else f"{valor:.1f}"
                    sx = base_x + (s_idx * sub_w) + sub_w / 2
                    _draw_text(c, sx, y, text,
                               size=FONT_SIZE_PROMOCION, center=True)


def draw_promocion_der(c: canvas.Canvas, estudiantes: List[Dict],
                        asignaturas: List[str], offset_asig: int = 3):
    """
    Dibuja la página derecha del spread de promoción.
    offset_asig: cuántas asignaturas ya se dibujaron en la izquierda.
    """
    table = PROMOCION_TABLE
    cols_der = table["columnas_pg_der"]
    cols_izq = table["columnas_pg_izq"]
    sub_w = cols_izq["asig_sub_width"]
    
    for i, est in enumerate(estudiantes[:40]):
        if not est:
            continue
        
        row_y_plumber = table["primera_fila_y_plumber"] + (i * table["row_height"])
        y = _y(row_y_plumber + table["row_height"] - 3)
        
        notas = est.get("notas", {})
        
        # Continuar asignaturas desde offset
        # En la página derecha, X empieza desde el borde izquierdo (~36)
        # pero el contenido del spread continúa desde donde quedó
        # Como es un spread, las coordenadas reales del contenido son las mismas
        # pero la página derecha muestra la segunda mitad
        # Sin embargo, al escribir el overlay, escribimos en coords de 0-612
        # Para la página derecha, hay que calcular el offset:
        # En el spread completo, la derecha empieza en X=612
        # Pero nosotros escribimos en X de 0-612 en esta página
        # Entonces: X_overlay = X_spread - 612
        
        asig_x_spread = cols_izq["asig_inicio_x"] + (offset_asig * sub_w * 4)
        
        remaining_asigs = asignaturas[offset_asig:]
        for a_idx, asig in enumerate(remaining_asigs):
            asig_key = asig.lower().replace(" ", "_").replace("-", "_")
            nota_asig = notas.get(asig_key, {})
            
            base_x_spread = asig_x_spread + (a_idx * sub_w * 4)
            base_x = base_x_spread - 612  # Convertir a coords de página derecha
            
            if base_x > 575:  # Fuera de página
                break
            
            for s_idx, sub_col in enumerate(cols_izq["sub_cols"]):
                valor = nota_asig.get(sub_col)
                if valor is not None and valor != "":
                    text = str(valor)
                    if isinstance(valor, float):
                        text = f"{valor:.0f}" if valor == int(valor) else f"{valor:.1f}"
                    sx = base_x + (s_idx * sub_w) + sub_w / 2
                    if 0 < sx < 612:
                        _draw_text(c, sx, y, text,
                                   size=FONT_SIZE_PROMOCION, center=True)
        
        # Situación final
        sit = est.get("situacion_final", "")
        if sit:
            _draw_text(c, cols_der["situacion_final_x"], y,
                       sit, size=FONT_SIZE_PROMOCION, center=True)


def draw_estadisticas(c: canvas.Canvas, datos: Dict):
    """
    Dibuja estadísticas de fin de año escolar.
    datos: {
        "aprobados": {"femenino": {edad: count, ...}, "masculino": {edad: count, ...}},
        "repitentes": {"femenino": {}, "masculino": {}},
        "abandono": {"femenino": {}, "masculino": {}},
    }
    """
    # Las estadísticas son complejas y varían por grado
    # Por ahora placeholder - se refinará con coordenadas exactas
    pass


# ============================================================================
# GENERADOR PRINCIPAL
# ============================================================================

def generar_registro_escolar(
    grado: int,
    datos_centro: Dict,
    datos_portada: Dict,
    estudiantes: List[Dict],
    asistencia_data: Optional[Dict] = None,
    calificaciones_data: Optional[Dict] = None,
    indicadores_data: Optional[Dict] = None,
    especificacion_data: Optional[Dict] = None,
    completiva_data: Optional[Dict] = None,
    salida_optativa_data: Optional[Dict] = None,
    salida_optativa_asistencia: Optional[Dict] = None,
    promocion_data: Optional[List[Dict]] = None,
    estadisticas_data: Optional[Dict] = None,
    template_dir: Optional[str] = None,
    marca_borrador: bool = False,
) -> bytes:
    """
    Genera el registro escolar completo para un grado.
    
    Args:
        grado: 1-6
        datos_centro: Dict con datos del centro educativo
        datos_portada: Dict con año escolar, sección, etc.
        estudiantes: Lista de hasta 40 estudiantes con sus datos
        asistencia_data: Dict con asistencia por asignatura y mes
        calificaciones_data: Dict con calificaciones por competencia (spreads)
        especificacion_data: {slot_bloque: {periodo: {"grupos_ce": [...],
            "contenidos": [...]}}} — R2.1D. `slot_bloque` sale de
            `Asignatura.area_curricular_codigo`, no del nombre de la materia.
        indicadores_data: LEGACY R2. {asig_idx: {periodo: texto}} — indicadores de logro
            trabajados; se escriben en la columna "Indicadores de Logro" de la
            página de ESPECIFICACIÓN CURRICULAR de esa asignatura y período.
        completiva_data: Dict con calificaciones completivas/extraordinarias
        promocion_data: Lista de estudiantes con notas finales para promoción
        estadisticas_data: Dict con estadísticas de fin de año
        template_dir: Directorio donde están los PDFs template (override)
        marca_borrador: v2.19.6 — estampa el sello BORRADOR durante ESTA misma
            pasada. Por defecto False: el registro OFICIAL sale exactamente
            igual que antes, sin sello y sin un solo objeto extra.
    
    Returns:
        bytes del PDF generado
    """
    if grado not in GRADO_CONFIG:
        raise ValueError(f"Grado {grado} no válido. Debe ser 1-6.")
    
    config = GRADO_CONFIG[grado]
    ciclo = config["ciclo"]
    asignaturas = ASIGNATURAS_CICLO_2 if ciclo == 2 else ASIGNATURAS_CICLO_1
    
    # Cargar template
    tpl_dir = template_dir or TEMPLATE_DIR
    tpl_path = os.path.join(tpl_dir, TEMPLATE_FILES[grado])
    
    if not os.path.exists(tpl_path):
        raise FileNotFoundError(f"Template no encontrado: {tpl_path}")
    
    template_reader = PdfReader(tpl_path)
    total_pages = len(template_reader.pages)
    
    # Crear diccionario de overlays: {page_index_0based: overlay_buffer}
    overlays = {}
    
    # --- PORTADA (Pg 1) ---
    if datos_portada:
        buf = _create_overlay_page(draw_portada, datos_portada)
        overlays[0] = buf  # Pg 1 = index 0
    
    # --- CENTRO EDUCATIVO ---
    if datos_centro:
        pg_idx = config["centro_educativo"] - 1
        buf = _create_overlay_page(draw_centro_educativo, datos_centro)
        overlays[pg_idx] = buf
    
    # --- DATOS DEL ESTUDIANTE (Pg 11) ---
    if estudiantes:
        pg_idx = config["datos_estudiantes"] - 1
        buf = _create_overlay_page(draw_datos_estudiantes, estudiantes)
        overlays[pg_idx] = buf
    
    # --- CONDICIÓN INICIAL (Pg 12) ---
    if estudiantes:
        pg_idx = config["condicion_inicial"] - 1
        buf = _create_overlay_page(draw_condicion_inicial, estudiantes)
        overlays[pg_idx] = buf
    
    # --- ASISTENCIA ---
    # R3.1 §5: el destino de cada página sale de ASISTENCIA_MAPA_SECUNDARIA
    # (mapa verificado contra el template), NO de una fórmula. Ver el comentario
    # extenso junto a esa tabla: la fórmula anterior desfasaba las tres últimas
    # asignaturas y terminaba escribiendo sobre las páginas de Salida Optativa
    # (4to-6to) o sobre las de evaluaciones completivas (1ro-3ro).
    if asistencia_data:
        for a_idx, asig in enumerate(asignaturas):
            if a_idx >= len(ASISTENCIA_MAPA_SECUNDARIA):
                # a_idx 9 = "Salida Optativa" en ciclo 2. Su bloque de
                # asistencia (pgs 56-65) se estampa en R3.3, no aquí.
                continue

            asig_key = asig.lower().replace(" ", "_").replace("-", "_")
            asig_data = asistencia_data.get(asig_key, {})

            if not asig_data:
                continue

            entrada = ASISTENCIA_MAPA_SECUNDARIA[a_idx]
            meses = asig_data.get("meses", [])

            if entrada["layout"] in ASISTENCIA_LAYOUT_SIN_CALIBRAR:
                # Barrera: una rejilla sin medir se deja EN BLANCO antes que
                # estampar marcas en columnas que no le corresponden.
                logger.warning(
                    "Asistencia de '%s' no se estampa: la rejilla '%s' no está "
                    "calibrada (páginas %s).",
                    asig, entrada["layout"], entrada["paginas"],
                )
                continue

            if entrada["layout"] == "4meses":
                # Ed. Artística / Ed. Física / FIHR: 3 páginas de 4 meses × 10
                # días. Rejilla propia, calibrada en ASISTENCIA_TABLE_4MESES.
                # El template imprime el DOCENTE en cada una de las 3 páginas;
                # el constructor de datos solo lo pone en el primer mes.
                docente = ""
                for _m in meses:
                    if _m and _m.get("docente"):
                        docente = _m["docente"]
                        break
                por_pagina = ASISTENCIA_TABLE_4MESES["bloques"]
                for pg_offset, pagina in enumerate(entrada["paginas"]):
                    pg_idx = pagina - 1
                    if pg_idx >= total_pages:
                        break
                    grupo = meses[pg_offset * por_pagina:(pg_offset + 1) * por_pagina]
                    if not any(grupo):
                        continue
                    buf = io.BytesIO()
                    c_asist = canvas.Canvas(buf, pagesize=letter)
                    draw_asistencia_4meses(c_asist, grupo, pagina,
                                           docente=docente, asignatura=asig)
                    c_asist.showPage()
                    c_asist.save()
                    buf.seek(0)
                    overlays[pg_idx] = buf
                if len(meses) > por_pagina * len(entrada["paginas"]):
                    logger.warning(
                        "Asistencia de '%s': %d meses capturados y la hoja oficial "
                        "solo tiene %d huecos (páginas %s).",
                        asig, len(meses), por_pagina * len(entrada["paginas"]),
                        entrada["paginas"],
                    )
                continue

            # Cada asignatura tiene 5 páginas (10 meses, 2 por página)
            for pg_offset, pagina in enumerate(entrada["paginas"]):
                pg_idx = pagina - 1  # 0-indexed

                if pg_idx >= total_pages:
                    break

                # Mes izquierdo
                mes_izq_idx = pg_offset * 2
                mes_der_idx = pg_offset * 2 + 1
                
                has_data = False
                buf = io.BytesIO()
                c_asist = canvas.Canvas(buf, pagesize=letter)
                
                if mes_izq_idx < len(meses) and meses[mes_izq_idx]:
                    draw_asistencia(c_asist, meses[mes_izq_idx], es_mes_derecho=False)
                    has_data = True
                
                if mes_der_idx < len(meses) and meses[mes_der_idx]:
                    draw_asistencia(c_asist, meses[mes_der_idx], es_mes_derecho=True)
                    has_data = True
                
                if has_data:
                    c_asist.showPage()
                    c_asist.save()
                    buf.seek(0)
                    overlays[pg_idx] = buf

    # --- ASISTENCIA DE SALIDA OPTATIVA (R3.4.1, solo 4to-6to) ---
    # El template trae 10 páginas con el encabezado impreso "SALIDA OPTATIVA
    # ____ ASIGNATURA ____": 2 componentes × 5 páginas, porque un estudiante
    # cursa como máximo 2 componentes. R3.1 las documentó en
    # ASISTENCIA_SALIDA_OPTATIVA_CICLO_2 y las dejó para el render de la Salida
    # Optativa; hasta R3.4.1 salían siempre vírgenes.
    #
    # Llega desde app.py ya resuelta por `CursoComponenteOptativo` e indexada por
    # SLOT, igual que `salida_optativa_data`. Los datos son los del
    # `asignatura_id` del componente, NUNCA los de la troncal.
    #
    # La clave es el ÍNDICE DE BLOQUE (0 o 1), que app.py deriva de la posición
    # del componente dentro de los que define su salida. Así un componente
    # conserva su bloque aunque el otro no tenga datos.
    #
    # Misma rejilla y mismo `draw_asistencia` del layout "2meses" de las
    # materias normales: ninguna geometría nueva.
    if salida_optativa_asistencia and config.get("ciclo") == 2:
        bloques = ASISTENCIA_SALIDA_OPTATIVA_CICLO_2
        for bloque_idx in sorted(k for k in salida_optativa_asistencia
                                 if isinstance(k, int)):
            if not (0 <= bloque_idx < len(bloques)):
                logger.warning(
                    "Asistencia de Salida Optativa: bloque %s fuera de las %d hojas "
                    "oficiales; no se estampa.", bloque_idx, len(bloques))
                continue
            datos_bloque = salida_optativa_asistencia[bloque_idx] or {}
            meses = datos_bloque.get("meses") or []
            # ROTULADO (R3.4.1 §4-§5). El template deja en blanco "SALIDA
            # OPTATIVA ____ ASIGNATURA ____", así que la rejilla sola no dice a
            # qué materia pertenece. Los nombres vienen del CATÁLOGO y del
            # mapping explícito, nunca de una búsqueda por nombre.
            #
            # Se rotula aunque todavía no haya ni una asistencia: un componente
            # configurado ya ocupa ese espacio del Registro y conviene que la
            # hoja lo identifique. Rotular NO rellena días ni inventa marcas —
            # la rejilla sigue vacía, tal como la imprime el MINERD.
            rotulo_salida = (datos_bloque.get("salida_nombre") or "").strip()
            rotulo_asig = (datos_bloque.get("componente_nombre") or "").strip()
            if not any(meses) and not (rotulo_salida or rotulo_asig):
                continue
            _hdr = ASISTENCIA_SALIDA_OPTATIVA_HEADER
            for pg_offset, pagina in enumerate(bloques[bloque_idx]):
                pg_idx = pagina - 1
                if pg_idx >= total_pages:
                    break
                mes_izq_idx = pg_offset * 2
                mes_der_idx = pg_offset * 2 + 1
                has_data = False
                buf = io.BytesIO()
                c_asist = canvas.Canvas(buf, pagesize=letter)
                # El rótulo va en TODAS las páginas del bloque: cada hoja del
                # Registro tiene que poder leerse por separado.
                if rotulo_salida:
                    _draw_text(c_asist, _hdr["salida_x"], _y(_hdr["y_plumber"]),
                               rotulo_salida, size=FONT_SIZE_NOTA,
                               max_width=_hdr["salida_max_width"])
                if rotulo_asig:
                    _draw_text(c_asist, _hdr["asignatura_x"], _y(_hdr["y_plumber"]),
                               rotulo_asig, size=FONT_SIZE_NOTA,
                               max_width=_hdr["asignatura_max_width"])
                if mes_izq_idx < len(meses) and meses[mes_izq_idx]:
                    draw_asistencia(c_asist, meses[mes_izq_idx], es_mes_derecho=False)
                    has_data = True
                if mes_der_idx < len(meses) and meses[mes_der_idx]:
                    draw_asistencia(c_asist, meses[mes_der_idx], es_mes_derecho=True)
                    has_data = True
                if has_data or rotulo_salida or rotulo_asig:
                    c_asist.showPage()
                    c_asist.save()
                    buf.seek(0)
                    overlays[pg_idx] = buf

    # --- CALIFICACIONES DE RENDIMIENTO (P1-P4, PC por período) ---
    if calificaciones_data:
        calif_inicio = config.get("calificaciones_inicio", 131) - 1  # 0-indexed
        calif_pgs = config.get("calificaciones_pgs_por_asignatura", 2)
        
        for a_idx, asig in enumerate(asignaturas):
            asig_califs = calificaciones_data.get(a_idx, {})
            if not asig_califs:
                continue
            
            # Cada asignatura tiene 2 páginas (spread landscape)
            # Página izquierda: P1, P2 | Página derecha: P3, P4, CF
            pg_izq = calif_inicio + (a_idx * calif_pgs)
            pg_der = pg_izq + 1 if calif_pgs >= 2 else None
            
            if pg_izq >= total_pages:
                break
            
            # === SPREAD DE CALIFICACIONES (v2.19.7) ===
            #
            # El spread MINERD tiene CUATRO bloques de detalle P1/RP1..P4/RP4
            # —uno por competencia— repartidos dos por página, más el bloque
            # resumen en la página derecha. Antes solo se dibujaba el resumen y
            # se escribía el PC del período dentro del bloque de detalle de la
            # competencia 1: los cuatro bloques quedaban vacíos o con el número
            # equivocado. La nota de cada competencia y período ya viene en
            # est_data['competencias'][n], sin colapsar.
            row_start_y = _y(CALIF_SPREAD['centro_fila1_plumber'] + FONT_SIZE_NOTA * 0.35)
            row_spacing = CALIF_SPREAD['row_height']

            def _dibujar_detalle(lienzo, columnas_por_competencia):
                """Dibuja los bloques de detalle de una página del spread.

                Devuelve True si escribió al menos un valor. Una celda sin dato
                se deja en blanco: nunca se rellena con cero ni con promedios.
                """
                escribio = False
                for est_idx, est_data in asig_califs.items():
                    if not isinstance(est_data, dict):
                        continue
                    ei = int(est_idx) if isinstance(est_idx, str) else est_idx
                    if ei >= 40:
                        continue
                    detalle = est_data.get('competencias') or {}
                    if not detalle:
                        continue
                    y = row_start_y - (ei * row_spacing)
                    for num_comp, columnas in columnas_por_competencia.items():
                        notas = detalle.get(num_comp) or detalle.get(str(num_comp))
                        if not notas:
                            continue
                        for celda, x in columnas.items():
                            texto = _fmt_nota(notas.get(celda))
                            if texto:
                                _draw_text(lienzo, x, y, texto,
                                           size=FONT_SIZE_NOTA, center=True)
                                escribio = True
                return escribio

            # --- Página IZQUIERDA: competencias 1 y 2 ---
            buf = io.BytesIO()
            c_cal = canvas.Canvas(buf, pagesize=letter)
            has_data = _dibujar_detalle(c_cal, CALIF_SPREAD['izq'])

            if has_data:
                c_cal.showPage()
                c_cal.save()
                buf.seek(0)
                overlays[pg_izq] = buf

            # --- Página DERECHA: competencias 3 y 4 + resumen ---
            if pg_der and pg_der < total_pages:
                buf2 = io.BytesIO()
                c_cal2 = canvas.Canvas(buf2, pagesize=letter)
                has_data2 = _dibujar_detalle(c_cal2, CALIF_SPREAD['der'])

                # Bloque "Promedio de Competencias Específicas" + Calificación
                # final.
                #
                # v2.19.7 (3): la columna PCn es el promedio FINAL de la
                # COMPETENCIA n a lo largo de P1-P4 —así lo rotula el template:
                # "PC1: Competencia 1" … "PC4: Competencia 4"—. Antes se
                # imprimía el promedio de las cuatro competencias en cada
                # PERÍODO, que es otro número. El valor sale de
                # CalificacionSecundaria.calcular_promedio_competencia(), que ya
                # aplica valor_periodo() = max(P, RP) y devuelve None si falta
                # algún período.
                resumen = CALIF_SPREAD['resumen']
                for est_idx, est_data in asig_califs.items():
                    if not isinstance(est_data, dict):
                        continue
                    ei = int(est_idx) if isinstance(est_idx, str) else est_idx
                    if ei >= 40:
                        continue

                    y = row_start_y - (ei * row_spacing)

                    promedios = est_data.get('promedios_competencia') or {}
                    for num_comp in (1, 2, 3, 4):
                        valor = promedios.get(num_comp, promedios.get(str(num_comp)))
                        texto = _fmt_nota(valor)
                        if texto:
                            _draw_text(c_cal2, resumen[f'pc{num_comp}'], y, texto,
                                       size=FONT_SIZE_NOTA, center=True)
                            has_data2 = True

                    # La calificación final es entera (regla del boletín).
                    texto_cf = _fmt_nota(est_data.get('cf'), ints_only=True)
                    if texto_cf:
                        _draw_text(c_cal2, resumen['cf'], y, texto_cf,
                                   size=FONT_SIZE_NOTA, center=True)
                        has_data2 = True

                if has_data2:
                    c_cal2.showPage()
                    c_cal2.save()
                    buf2.seek(0)
                    overlays[pg_der] = buf2
    
    # --- ESPECIFICACIÓN CURRICULAR: CE + IL + CONTENIDOS CLAVES (R2.1D) ---
    # Una página por (bloque oficial, período). La clave es el SLOT del bloque
    # curricular (LE=0 … FIHR=8), derivado de `Asignatura.area_curricular_codigo`
    # por el loader: NUNCA del nombre, del código legacy ni del rótulo `area`.
    # Un período sin datos deja su página idéntica al template.
    if especificacion_data:
        for slot, por_periodo in (especificacion_data or {}).items():
            if not por_periodo:
                continue
            try:
                slot_int = int(slot)
            except (TypeError, ValueError):
                continue
            for periodo, datos_periodo in por_periodo.items():
                if not datos_periodo:
                    continue
                try:
                    periodo_int = int(periodo)
                except (TypeError, ValueError):
                    continue
                if not (datos_periodo.get("grupos_ce") or datos_periodo.get("contenidos")):
                    continue
                pg_num = pagina_indicador(ciclo, slot_int, periodo_int)
                if not pg_num:
                    continue
                pg_idx = pg_num - 1
                if pg_idx >= total_pages:
                    continue
                # Preflight: elige 8/10 o 6.5/8, o aborta la generación entera.
                plan = espec_plan(datos_periodo, {
                    "slot": slot_int,
                    "periodo": periodo_int,
                    "pagina": pg_num,
                    **{k: v for k, v in datos_periodo.items()
                       if k in ("asignatura_id", "area_codigo", "asignatura")},
                })
                overlays[pg_idx] = _create_overlay_page(
                    draw_especificacion_curricular, {"plan": plan})

    # --- INDICADORES DE LOGRO (R2 legacy) ---
    # Camino anterior, de texto libre en una sola columna. El loader ya no lo
    # alimenta —un período con `contenido` legacy bloquea la generación con 409
    # para no falsificar el Registro—, pero se conserva funcional porque su
    # suite lo ejercita directamente y porque borrarlo no aportaría nada.
    if indicadores_data:
        for a_idx, por_periodo in (indicadores_data or {}).items():
            if not por_periodo:
                continue
            try:
                a_idx_int = int(a_idx)
            except (TypeError, ValueError):
                continue
            for periodo, texto in por_periodo.items():
                if not texto or not str(texto).strip():
                    continue
                try:
                    periodo_int = int(periodo)
                except (TypeError, ValueError):
                    continue
                pg_num = pagina_indicador(ciclo, a_idx_int, periodo_int)
                if not pg_num:
                    continue
                pg_idx = pg_num - 1
                if pg_idx >= total_pages:
                    continue
                overlays[pg_idx] = _create_overlay_page(draw_indicadores, {"texto": texto})

    # --- CALIFICACIONES COMPLETIVAS ---
    if completiva_data:
        # Usar lista explícita de páginas si existe, sino calcular por offset
        comp_paginas = config.get("completiva_paginas", None)
        
        if comp_paginas:
            # Las asignaturas base (sin salida optativa) mapean 1:1 con comp_paginas
            asig_base = ASIGNATURAS_CICLO_1  # 9 asignaturas base
            for a_idx, asig in enumerate(asig_base):
                if a_idx >= len(comp_paginas):
                    break
                
                asig_key = asig.lower().replace(" ", "_").replace("-", "_")
                asig_comp = completiva_data.get(asig_key, {})
                
                if not asig_comp:
                    continue
                
                pg_idx = comp_paginas[a_idx] - 1  # Convertir a 0-indexed
                if pg_idx >= total_pages:
                    break
                
                buf = _create_overlay_page(draw_completiva, asig_comp)
                overlays[pg_idx] = buf
            
        else:
            # Fallback: calcular por offset
            comp_inicio = config["completiva_inicio"] - 1
            for a_idx, asig in enumerate(asignaturas):
                asig_key = asig.lower().replace(" ", "_").replace("-", "_")
                asig_comp = completiva_data.get(asig_key, {})
                if not asig_comp:
                    continue
                pg_idx = comp_inicio + a_idx
                if pg_idx >= total_pages:
                    break
                buf = _create_overlay_page(draw_completiva, asig_comp)
                overlays[pg_idx] = buf
    
    # --- SALIDA OPTATIVA (R3.3) ---
    # Reemplaza al bloque desactivado en v2.20.1-B2.1. Aquel se apagó porque
    # EducaOne modelaba UNA asignatura genérica "Salida Optativa" y estampar su
    # nota en las seis páginas habría inventado información académica. R3.1/R3.2
    # aportaron el mapeo que faltaba, así que ahora cada página recibe SOLO la
    # nota del componente que le corresponde.
    #
    # El slot es la posición del componente en el catálogo oficial y, por
    # construcción, el índice en `completiva_salida_optativa`:
    #   slot 0 -> pg 211 (HLM/Lengua)   slot 3 -> pg 217 (MYT/Matemática)
    #   slot 1 -> pg 212 (HCS/Lengua)   slot 4 -> pg 219 (HCS/C. Sociales)
    #   slot 2 -> pg 214 (HLM/Inglés)   slot 5 -> pg 221 (CYT/C. Naturaleza)
    # Verificado contra los templates oficiales: cada una de esas páginas lleva
    # impreso "SALIDA OPTATIVA: <salida>" con el nombre del componente.
    #
    # Los números son PÁGINA HUMANA (1-based) y se convierten con `- 1`, igual
    # que `completiva_paginas` y `promocion_inicio`.
    #
    # Se usan `draw_completiva` y `_create_overlay_page` existentes: mismo
    # pipeline XObject, sin `merge_page`, sin motor nuevo.
    if salida_optativa_data:
        salida_opt_paginas = config.get("completiva_salida_optativa", [])
        for slot, datos_comp in salida_optativa_data.items():
            try:
                slot_int = int(slot)
            except (TypeError, ValueError):
                continue
            if not (0 <= slot_int < len(salida_opt_paginas)):
                continue
            if not datos_comp:
                continue
            # R3.3 §14: si NINGUNA fila trae dato, la página se queda idéntica al
            # template. Un overlay vacío no es neutro: dejaría constancia de que
            # EducaOne escribió esa página del Registro sin tener nada que
            # escribir. El wrapper `generar_registro_desde_sistema` ya filtra
            # así, pero esta función también se llama directamente y la regla
            # tiene que valer en los dos caminos.
            if not any(f for f in (datos_comp.get("calificaciones") or [])):
                continue
            pg_idx = salida_opt_paginas[slot_int] - 1
            if pg_idx >= total_pages:
                continue
            overlays[pg_idx] = _create_overlay_page(draw_completiva, datos_comp)

    # --- PROMOCIÓN ---
    if promocion_data:
        prom_inicio = config["promocion_inicio"] - 1
        
        # Página izquierda
        buf = _create_overlay_page(draw_promocion_izq, promocion_data, asignaturas)
        overlays[prom_inicio] = buf
        
        # Página derecha
        if prom_inicio + 1 < total_pages:
            buf = _create_overlay_page(draw_promocion_der, promocion_data, asignaturas, offset_asig=3)
            overlays[prom_inicio + 1] = buf
    
    # ========================================
    # MERGE: Template + Overlays
    # ========================================
    writer = PdfWriter()

    # v2.19.6: el sello BORRADOR se estampa acá, en la MISMA pasada. Antes se
    # generaba el PDF entero, se serializaba, se volvía a parsear y se recorrían
    # las 170 páginas otra vez solo para sellarlas. El sello se construye una
    # vez por geometría de página (en la práctica, una sola vez).
    #
    # v2.19.9: los overlays de DATOS también se aplican como Form XObject (misma
    # técnica que el sello), NO con merge_page(). merge_page descomprimía y
    # re-parseaba el content-stream del template en cada página —el 73 % del
    # tiempo de generación (auditoría v2.19.9)—. Ahora el template no se toca:
    # la página gana una referencia `/EODataOverlayN Do`. Orden de dibujo por
    # página: TEMPLATE -> DATOS -> BORRADOR.
    refs_borrador = {}

    for pg_idx in range(total_pages):
        template_page = template_reader.pages[pg_idx]

        pagina = writer.add_page(template_page)

        # DATOS: overlay ReportLab de esta página como Form XObject encadenado
        # al /Contents. `pg_idx in overlays` solo es cierto para páginas con
        # contenido real (portada, centro, estudiantes, asistencia con datos,
        # calificaciones, promoción): las demás no reciben ningún XObject.
        if pg_idx in overlays:
            overlay_reader = PdfReader(overlays[pg_idx])
            if len(overlay_reader.pages) > 0:
                nombre = nombre_xobject_libre(pagina, "/EODataOverlay")
                ref = crear_xobject_desde_overlay(writer, overlay_reader.pages[0])
                estampar_xobject(writer, pagina, ref, nombre)

        if marca_borrador:
            # Después de los DATOS, para que el sello quede ENCIMA de todo.
            ancho = float(pagina.mediabox.width)
            alto = float(pagina.mediabox.height)
            clave = (round(ancho, 2), round(alto, 2))
            if clave not in refs_borrador:
                refs_borrador[clave] = crear_xobject_borrador(writer, ancho, alto)
            estampar_borrador(writer, pagina, refs_borrador[clave])
    
    # Escribir resultado
    output = io.BytesIO()
    writer.write(output)
    output.seek(0)
    
    return output.getvalue()


# ============================================================================
# FUNCIÓN DE CONVENIENCIA PARA FASTAPI
# ============================================================================

def generar_registro_desde_db(
    db,
    colegio_id: int,
    grado: int,
    seccion: str,
    anio_escolar: str,
    template_dir: Optional[str] = None,
) -> bytes:
    """
    Genera el registro escolar consultando datos de la base de datos.
    
    Args:
        db: SQLAlchemy session
        colegio_id: ID del colegio
        grado: 1-6
        seccion: "A", "B", etc.
        anio_escolar: "2024-2025"
        template_dir: Override para directorio de templates
    
    Returns:
        bytes del PDF generado
    """
    # Importar modelos (evitar import circular)
    from models import (
        Colegio, Estudiante, Calificacion, Asistencia,
        Profesor, ConfiguracionColegio, MatriculaEstudiante
    )
    
    # Obtener datos del colegio
    colegio = db.query(Colegio).filter(Colegio.id == colegio_id).first()
    if not colegio:
        raise ValueError(f"Colegio {colegio_id} no encontrado")
    
    config_col = db.query(ConfiguracionColegio).filter(
        ConfiguracionColegio.colegio_id == colegio_id
    ).first()
    
    # Años
    anios = anio_escolar.split("-")
    anio_inicio = anios[0][-2:] if len(anios) > 0 else ""
    anio_fin = anios[1][-2:] if len(anios) > 1 else ""
    
    datos_portada = {
        "anio_inicio": anio_inicio,
        "anio_fin": anio_fin,
        "seccion": seccion,
    }
    
    # Datos del centro educativo
    datos_centro = {
        "nombre_centro": colegio.nombre or "",
        "direccion": colegio.direccion or "",
        "correo_centro": colegio.email or "",
        "telefono_centro": colegio.telefono or "",
        "codigo_sigerd": getattr(colegio, 'codigo_sigerd', '') or "",
        "codigo_cartografia": getattr(colegio, 'codigo_cartografia', '') or "",
        "director": getattr(colegio, 'director', '') or "",
        "correo_director": getattr(colegio, 'correo_director', '') or "",
        "telefono_director": getattr(colegio, 'telefono_director', '') or "",
        "docente_encargado": "",  # Se llena del profesor asignado
        "correo_docente": "",
        "telefono_docente": "",
        "sector": getattr(colegio, 'sector', 'publico') or "publico",
        "zona": getattr(colegio, 'zona', 'urbana') or "urbana",
        "jornada": getattr(colegio, 'jornada', 'matutina') or "matutina",
        "regional": getattr(colegio, 'regional', '') or "",
        "distrito": getattr(colegio, 'distrito', '') or "",
    }
    
    # Obtener estudiantes matriculados
    matriculas = db.query(MatriculaEstudiante).filter(
        MatriculaEstudiante.colegio_id == colegio_id,
        MatriculaEstudiante.grado == grado,
        MatriculaEstudiante.seccion == seccion,
        MatriculaEstudiante.anio_escolar == anio_escolar,
        MatriculaEstudiante.estado == "activo",
    ).all()
    
    # Ordenar por apellido
    est_ids = [m.estudiante_id for m in matriculas]
    estudiantes_db = db.query(Estudiante).filter(
        Estudiante.id.in_(est_ids)
    ).order_by(Estudiante.apellidos, Estudiante.nombres).all()
    
    # Preparar datos de estudiantes
    estudiantes = []
    for idx, est in enumerate(estudiantes_db[:40]):
        fecha_nac = est.fecha_nacimiento
        estudiantes.append({
            "numero": idx + 1,
            "sexo": est.sexo or "",
            "dia_nac": str(fecha_nac.day) if fecha_nac else "",
            "mes_nac": str(fecha_nac.month) if fecha_nac else "",
            "anio_nac": str(fecha_nac.year) if fecha_nac else "",
            "libro": getattr(est, 'libro', '') or "",
            "folio": getattr(est, 'folio', '') or "",
            "edad": _calcular_edad(fecha_nac) if fecha_nac else "",
            "cedula": est.cedula or getattr(est, 'pasaporte', '') or "",
            "rne": getattr(est, 'rne', '') or "",
            "lugar_residencia": getattr(est, 'direccion', '') or "",
            "correo": est.email or "",
            "condicion": getattr(est, 'condicion_inicial', 'promovido') or "promovido",
        })
    
    # Obtener calificaciones completivas
    ciclo = 2 if grado >= 4 else 1
    asignaturas = ASIGNATURAS_CICLO_2 if ciclo == 2 else ASIGNATURAS_CICLO_1
    
    completiva_data = {}
    for asig in asignaturas:
        asig_key = asig.lower().replace(" ", "_").replace("-", "_")
        califs = []
        
        for est in estudiantes_db[:40]:
            calif = db.query(Calificacion).filter(
                Calificacion.estudiante_id == est.id,
                Calificacion.colegio_id == colegio_id,
                Calificacion.asignatura == asig,
                Calificacion.anio_escolar == anio_escolar,
            ).first()
            
            if calif:
                califs.append({
                    "cf_original": calif.cf or "",
                    "comp_cf_50": "",  # Se calcula si aplica
                    "comp_cec_50": "",
                    "comp_ccf": "",
                    "comp_cf": "",
                    "extra_30": "",
                    "extra_c": "",
                    "extra_70_c": "",
                    "extra_cf": "",
                    "espec_cf": calif.cf or "",
                    "espec_ce": "",
                    "espec_a": "A" if (calif.cf and calif.cf >= 70) else "",
                    "espec_r": "R" if (calif.cf and calif.cf < 70) else "",
                })
            else:
                califs.append(None)
        
        if any(califs):
            completiva_data[asig_key] = {"calificaciones": califs}
    
    # Obtener datos para promoción
    promocion_data = []
    for idx, est in enumerate(estudiantes_db[:40]):
        notas = {}
        for asig in asignaturas:
            asig_key = asig.lower().replace(" ", "_").replace("-", "_")
            calif = db.query(Calificacion).filter(
                Calificacion.estudiante_id == est.id,
                Calificacion.colegio_id == colegio_id,
                Calificacion.asignatura == asig,
                Calificacion.anio_escolar == anio_escolar,
            ).first()
            
            if calif:
                notas[asig_key] = {
                    "final": calif.cf or "",
                    "completivo": "",
                    "extraordinario": "",
                    "especial": calif.literal or "",
                }
        
        # Determinar situación final
        todas_notas = [n.get("final", 0) for n in notas.values() if n.get("final")]
        situacion = ""
        if todas_notas:
            reprobadas = sum(1 for n in todas_notas if isinstance(n, (int, float)) and n < 70)
            if reprobadas == 0:
                situacion = "AP"  # Aprobado
            elif reprobadas <= 2:
                situacion = "AZ"  # Aplazado
            else:
                situacion = "RP"  # Reprobado
        
        promocion_data.append({
            "numero": idx + 1,
            "apellidos": est.apellidos or "",
            "nombres": est.nombres or "",
            "notas": notas,
            "situacion_final": situacion,
        })
    
    # Generar el PDF
    return generar_registro_escolar(
        grado=grado,
        datos_centro=datos_centro,
        datos_portada=datos_portada,
        estudiantes=estudiantes,
        asistencia_data=None,  # TODO: implementar consulta de asistencia
        calificaciones_data=None,  # Spreads de competencias - fase 2
        completiva_data=completiva_data if completiva_data else None,
        promocion_data=promocion_data if promocion_data else None,
        estadisticas_data=None,  # TODO
        template_dir=template_dir,
    )


def _calcular_edad(fecha_nacimiento) -> int:
    """Calcula la edad a partir de la fecha de nacimiento."""
    from datetime import date
    today = date.today()
    age = today.year - fecha_nacimiento.year
    if (today.month, today.day) < (fecha_nacimiento.month, fecha_nacimiento.day):
        age -= 1
    return age


# ============================================================================
# TEST: Generar un registro de prueba
# ============================================================================

def generar_registro_desde_sistema(colegio_info, curso_info, ano_escolar, estudiantes,
                                   asignaturas_data, grado_numero, marca_borrador=False,
                                   especificacion_data=None, salida_optativa_data=None,
                                   salida_optativa_asistencia=None):
    """
    Wrapper que traduce datos de app.py al formato del generador de registro.
    
    asignaturas_data[nombre_asig] = {
        'docente': str,
        'asistencias': {idx_est: {idx_mes: {dia: char}}},
        'calificaciones': {idx_est: {'p1':val, 'rp1':val, ..., 'cf':val}}
    }

    marca_borrador: v2.19.6 — sella BORRADOR en la misma pasada de generación.
    Los llamadores del registro OFICIAL no lo pasan y su PDF no cambia.
    """
    anios = str(ano_escolar).split('-')
    anio_inicio = anios[0][-2:] if len(anios) > 0 else ""
    anio_fin = anios[1][-2:] if len(anios) > 1 else ""
    
    datos_portada = {
        "anio_inicio": anio_inicio,
        "anio_fin": anio_fin,
        "seccion": curso_info.get('seccion', 'A'),
    }
    
    datos_centro = {
        "nombre_centro": colegio_info.get('nombre', ''),
        "direccion": colegio_info.get('direccion', ''),
        "correo_centro": colegio_info.get('correo_centro', '') or colegio_info.get('email', ''),
        "telefono_centro": colegio_info.get('telefono', ''),
        "codigo_sigerd": colegio_info.get('codigo_centro', ''),
        "codigo_cartografia": colegio_info.get('codigo_cartografia', ''),
        "director": colegio_info.get('director', ''),
        "correo_director": colegio_info.get('correo_director', ''),
        "telefono_director": colegio_info.get('telefono_director', ''),
        "docente_encargado": colegio_info.get('coordinador', ''),
        "correo_docente": "",
        "telefono_docente": "",
        "sector": colegio_info.get('sector', ''),
        "zona": colegio_info.get('zona', ''),
        "jornada": curso_info.get('tanda', '') or colegio_info.get('tanda_operacion', ''),
        "regional": colegio_info.get('regional', ''),
        "distrito": colegio_info.get('distrito', ''),
    }
    
    estudiantes_nuevo = []
    for idx, est in enumerate(estudiantes[:40]):
        fn = est.get('fecha_nacimiento')
        estudiantes_nuevo.append({
            "numero": est.get('no_lista', idx + 1),
            "nombre": est.get('nombre', ''),
            "sexo": est.get('sexo', 'M') if est.get('sexo') else '',
            "dia_nac": str(fn.day) if fn else '',
            "mes_nac": str(fn.month) if fn else '',
            "anio_nac": str(fn.year) if fn else '',
            "edad": str((date.today() - fn).days // 365) if fn else '',
            "cedula": est.get('cedula', ''),
            # v2.19.7: el RNE es el Registro Nacional del Estudiante, un número
            # que asigna el MINERD. EducaOne no lo guarda: no existe columna
            # `rne` en Estudiante. Acá se imprimía la MATRÍCULA interna del
            # colegio en esa casilla, con lo que el registro afirmaba un dato
            # nacional que nadie había cargado. Si algún día el modelo tiene
            # `rne`, este `est.get('rne')` lo toma solo; mientras tanto la
            # casilla va vacía, que es la verdad.
            "rne": est.get('rne', '') or '',
            "lugar_residencia": est.get('direccion', ''),
            "correo": est.get('email', '') or '',
            "condicion": est.get('condicion_entrada', 'nuevo'),
            # Flags de retiro: el draw_* los usa para marcar el registro
            # con "RET DD/MM" y NO marcar promovido/repitente/reingreso.
            "retirado": bool(est.get('retirado')) or not bool(est.get('activo', True)),
            "fecha_retiro": est.get('fecha_retiro'),
            "motivo_retiro": est.get('motivo_retiro'),
        })
    
    asigs_minerd = ASIGNATURAS_CICLO_2 if grado_numero >= 4 else ASIGNATURAS_CICLO_1
    num_est = len(estudiantes[:40])
    
    # === TRADUCIR ASISTENCIA ===
    # Prioriza la matriz real construida desde horario + días no laborables + captura diaria.
    asistencia_data = {}
    for asig_nombre in asigs_minerd:
        if asig_nombre not in asignaturas_data:
            continue
        data = asignaturas_data[asig_nombre]
        matriz = data.get('asistencia_matriz', [])
        raw = data.get('asistencias', {})
        if not matriz and not raw:
            continue
        
        asig_key = asig_nombre.lower().replace(" ", "_").replace("-", "_")
        meses_list = []

        if matriz:
            for mes_data in matriz:
                dias_mes = list(mes_data.get('dias', []))[:21]
                est_list = []
                for fila in mes_data.get('filas', [])[:num_est]:
                    valores = list(fila.get('valores', []))[:21]
                    dias = [None] * 21
                    for idx_dia, valor in enumerate(valores):
                        dias[idx_dia] = valor or None
                    est_list.append({
                        "dias": dias,
                        "total": fila.get("presentes", 0),
                        "porcentaje": fila.get("porcentaje", 0),
                    })

                if est_list:
                    meses_list.append({
                        "nombre_mes": mes_data.get("mes", ""),
                        "docente": "",
                        "asistencias": est_list,
                        "dias_labels": dias_mes,
                        # marca interna para priorizar los meses con captura real
                        "_tiene_marcas": any(v for f in est_list for v in f["dias"]),
                    })
            # v2.19.7: la hoja MINERD tiene 10 huecos de mes por asignatura
            # (5 páginas x 2). Cuando el año escolar y las fechas realmente
            # capturadas no coinciden, la matriz puede traer más de 10 meses y
            # los últimos se perderían — justo los que tienen asistencia. Se
            # ponen delante los meses CON captura, conservando entre ellos el
            # orden del año escolar (agosto→julio). No se altera ningún dato:
            # solo se decide qué meses ocupan los huecos disponibles.
            meses_list = (
                [m for m in meses_list if m.get("_tiene_marcas")]
                + [m for m in meses_list if not m.get("_tiene_marcas")]
            )
            for m in meses_list:
                m.pop("_tiene_marcas", None)
            if meses_list:
                # El template imprime el docente una sola vez, en el primer mes.
                meses_list[0]["docente"] = data.get('docente', '')
        else:
            meses_legacy = sorted({mes_idx for est_raw in raw.values() for mes_idx in est_raw.keys()})
            for mes_idx in meses_legacy:
                est_list = []
                has_any = False
                dias_labels = []
                for ei in range(num_est):
                    est_raw = raw.get(ei, {})
                    mes_raw = est_raw.get(mes_idx, {})
                    dias = [None] * 21
                    tp = 0
                    td = 0
                    for dia_num, estado in mes_raw.items():
                        d = int(dia_num) if isinstance(dia_num, str) else dia_num
                        if 1 <= d <= 31 and len(dias_labels) < 21 and d not in dias_labels:
                            dias_labels.append(d)
                        if 1 <= d <= 21:
                            dias[d - 1] = estado
                            td += 1
                            if estado == 'P':
                                tp += 1
                            has_any = True
                    est_list.append({"dias": dias, "total": tp, "porcentaje": round(tp / td * 100) if td > 0 else 0})

                if has_any:
                    meses_list.append({
                        "nombre_mes": f"mes_{mes_idx + 1}",
                        "docente": data.get('docente', '') if not meses_list else '',
                        "asistencias": est_list,
                        "dias_labels": dias_labels[:21],
                    })
        
        if any(m for m in meses_list):
            asistencia_data[asig_key] = {"meses": meses_list}
    
    # === TRADUCIR CALIFICACIONES ===
    calificaciones_data = {}
    for asig_idx, asig_nombre in enumerate(asigs_minerd):
        if asig_nombre not in asignaturas_data:
            continue
        califs = asignaturas_data[asig_nombre].get('calificaciones', {})
        if califs:
            calificaciones_data[asig_idx] = califs

    # === TRADUCIR INDICADORES DE LOGRO (R2) ===
    # asignaturas_data[nombre]['indicadores'] = {periodo: texto} — ya resuelto
    # en una sola consulta por el loader. Se reindexa por posición MINERD para
    # que `pagina_indicador()` sepa a qué página va cada asignatura/período.
    indicadores_data = {}
    for asig_idx, asig_nombre in enumerate(asigs_minerd):
        if asig_nombre not in asignaturas_data:
            continue
        por_periodo = asignaturas_data[asig_nombre].get('indicadores') or {}
        limpio = {
            int(p): str(t).strip()
            for p, t in por_periodo.items()
            if t is not None and str(t).strip()
        }
        if limpio:
            indicadores_data[asig_idx] = limpio

    # === TRADUCIR COMPLETIVA / EXTRAORDINARIA / ESPECIAL (v2.20.1-B2) ===
    # Una entrada por asignatura, con una lista alineada al orden de estudiantes
    # del Registro. Fuente única de la cascada: `evaluacion_extra` ya serializado
    # en asignaturas_data[...]['calificaciones'][idx]. Si ninguna fila aporta
    # dato (ni CF ni evaluación extra), la asignatura NO entra y su página queda
    # idéntica al template.
    #
    # v2.20.1-B2.1 — SALIDA OPTATIVA: en el template de ciclo 2 hay SEIS páginas
    # (211,212,214,217,219,221) que son bloques de Salida Optativa intercalados
    # con distintas áreas. EducaOne modela hoy UNA sola asignatura genérica
    # "Salida Optativa"; NO existe todavía un mapeo inequívoco asignatura real →
    # página específica. Estampar la misma nota en las seis páginas produciría
    # información académica falsa, así que la Salida Optativa se EXCLUYE de la
    # integración: sus seis páginas quedan sin overlay de notas extra.
    # TODO futuro: mapear la Salida Optativa real por área/página antes de activarla.
    _EXCLUIR_COMPLETIVA = {"Salida Optativa"}
    completiva_data = {}
    for asig_nombre in asigs_minerd:
        if asig_nombre not in asignaturas_data:
            continue
        if asig_nombre in _EXCLUIR_COMPLETIVA:
            continue
        data_asig = asignaturas_data[asig_nombre]
        califs = data_asig.get('calificaciones', {}) or {}
        filas = []
        tiene_algo = False
        for i in range(num_est):
            fila = _fila_completiva(califs.get(i))
            filas.append(fila)
            if fila:
                tiene_algo = True
        if tiene_algo:
            asig_key = asig_nombre.lower().replace(" ", "_").replace("-", "_")
            completiva_data[asig_key] = {
                "docente": data_asig.get('docente', ''),
                "calificaciones": filas,
            }

    # === TRADUCIR SALIDA OPTATIVA (R3.3) ===
    # Llega desde app.py ya resuelta por `CursoComponenteOptativo` e indexada por
    # SLOT. Aquí solo se aplica `_fila_completiva`, EXACTAMENTE la misma función
    # que traduce una asignatura normal: misma cascada, mismo redondeo, ninguna
    # fórmula nueva. Un componente sin ninguna fila con dato NO entra, y su
    # página queda idéntica al template.
    salida_optativa_filas = {}
    for slot, data_comp in (salida_optativa_data or {}).items():
        califs = (data_comp or {}).get('calificaciones', {}) or {}
        filas = []
        tiene_algo = False
        for i in range(num_est):
            fila = _fila_completiva(califs.get(i))
            filas.append(fila)
            if fila:
                tiene_algo = True
        if tiene_algo:
            salida_optativa_filas[slot] = {
                'docente': (data_comp or {}).get('docente', ''),
                'calificaciones': filas,
            }

    # === TRADUCIR PROMOCION ===
    promocion_data = []
    for idx in range(num_est):
        est_promo = {"notas_finales": {}}
        for asig_idx, asig_nombre in enumerate(asigs_minerd):
            if asig_nombre in asignaturas_data:
                califs = asignaturas_data[asig_nombre].get('calificaciones', {})
                if idx in califs:
                    cf = califs[idx].get('cf')
                    if cf is not None:
                        est_promo["notas_finales"][asig_idx] = cf
        promocion_data.append(est_promo if est_promo["notas_finales"] else None)
    
    return generar_registro_escolar(
        grado=grado_numero,
        datos_centro=datos_centro,
        datos_portada=datos_portada,
        estudiantes=estudiantes_nuevo,
        asistencia_data=asistencia_data if asistencia_data else None,
        calificaciones_data=calificaciones_data if calificaciones_data else None,
        indicadores_data=indicadores_data if indicadores_data else None,
        # R2.1D: llega ya resuelto y validado desde app.py, indexado por SLOT
        # del bloque curricular oficial. Ningún objeto ORM cruza al threadpool.
        especificacion_data=especificacion_data or None,
        completiva_data=completiva_data if completiva_data else None,
        # R3.3: indexada por SLOT del catálogo oficial, igual que especificacion_data.
        salida_optativa_data=salida_optativa_filas or None,
        # R3.4.1: asistencia de los componentes, también por SLOT. Llega ya
        # construida con `build_asistencia_registro`, el mismo constructor de las
        # materias normales, así que no hay una segunda forma de contar faltas.
        salida_optativa_asistencia=salida_optativa_asistencia or None,
        promocion_data=promocion_data if any(p for p in promocion_data) else None,
        marca_borrador=marca_borrador,
    )

if __name__ == "__main__":
    import sys
    
    # Test básico con datos ficticios
    grado = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    template_dir = sys.argv[2] if len(sys.argv) > 2 else None
    
    # Datos ficticios
    datos_portada = {
        "anio_inicio": "24",
        "anio_fin": "25",
        "seccion": "A",
    }
    
    datos_centro = {
        "nombre_centro": "Centro Educativo Ejemplo",
        "direccion": "Calle Principal #123, Santo Domingo",
        "correo_centro": "info@centroejemplo.edu.do",
        "telefono_centro": "809-555-1234",
        "codigo_sigerd": "12345",
        "codigo_cartografia": "67890",
        "director": "Juan Pérez García",
        "correo_director": "jperez@centroejemplo.edu.do",
        "telefono_director": "809-555-5678",
        "docente_encargado": "María López",
        "correo_docente": "mlopez@centroejemplo.edu.do",
        "telefono_docente": "809-555-9012",
        "sector": "publico",
        "zona": "urbana",
        "jornada": "matutina",
        "regional": "10",
        "distrito": "03",
    }
    
    # Estudiantes ficticios
    estudiantes = []
    nombres_f = ["Ana", "María", "Rosa", "Carmen", "Luz"]
    nombres_m = ["Juan", "Pedro", "Carlos", "Luis", "Miguel"]
    apellidos = ["García", "Rodríguez", "Martínez", "López", "Hernández",
                 "Pérez", "Sánchez", "Ramírez", "Torres", "Flores"]
    
    for i in range(20):
        sexo = "F" if i % 2 == 0 else "M"
        nombre = nombres_f[i % 5] if sexo == "F" else nombres_m[i % 5]
        apellido = apellidos[i % 10]
        
        estudiantes.append({
            "numero": i + 1,
            "sexo": sexo,
            "dia_nac": str((i * 3 % 28) + 1),
            "mes_nac": str((i % 12) + 1),
            "anio_nac": str(2010 + (i % 3)),
            "libro": str(100 + i),
            "folio": str(200 + i),
            "edad": 14 + (i % 3),
            "cedula": f"402-{3000000 + i * 1000:07d}-{i:01d}",
            "rne": f"RNE{100000 + i}",
            "lugar_residencia": f"Sector {i+1}, Santo Domingo",
            "correo": f"{nombre.lower()}.{apellido.lower()}@email.com",
            "condicion": "promovido",
        })
    
    # Calificaciones completivas de ejemplo
    asignaturas = ASIGNATURAS_CICLO_2 if grado >= 4 else ASIGNATURAS_CICLO_1
    completiva_data = {}
    
    for asig in asignaturas[:3]:  # Solo primeras 3 para test
        asig_key = asig.lower().replace(" ", "_").replace("-", "_")
        califs = []
        for i in range(20):
            nota = 65 + (i * 2 % 35)
            califs.append({
                "cf_original": nota,
                "espec_cf": nota,
                "espec_a": "A" if nota >= 70 else "",
                "espec_r": "R" if nota < 70 else "",
            })
        completiva_data[asig_key] = {
            "docente": f"Prof. Docente de {asig}",
            "calificaciones": califs,
        }
    
    # Promoción
    promocion_data = []
    for i, est in enumerate(estudiantes):
        notas = {}
        for asig in asignaturas:
            asig_key = asig.lower().replace(" ", "_").replace("-", "_")
            nota = 65 + (i * 3 % 35)
            notas[asig_key] = {
                "final": nota,
                "completivo": "",
                "extraordinario": "",
                "especial": "A" if nota >= 70 else "R",
            }
        
        todas_notas = [n["final"] for n in notas.values()]
        reprobadas = sum(1 for n in todas_notas if n < 70)
        situacion = "AP" if reprobadas == 0 else ("AZ" if reprobadas <= 2 else "RP")
        
        promocion_data.append({
            "numero": i + 1,
            "apellidos": apellidos[i % 10] + " " + apellidos[(i + 1) % 10],
            "nombres": est.get("sexo") == "F" and nombres_f[i % 5] or nombres_m[i % 5],
            "notas": notas,
            "situacion_final": situacion,
        })
    
    # Generar
    pdf_bytes = generar_registro_escolar(
        grado=grado,
        datos_centro=datos_centro,
        datos_portada=datos_portada,
        estudiantes=estudiantes,
        completiva_data=completiva_data,
        promocion_data=promocion_data,
        template_dir=template_dir,
    )
    
    output_path = f"registro_{grado}to_grado_test.pdf"
    with open(output_path, "wb") as f:
        f.write(pdf_bytes)
    
    print(f"Registro generado: {output_path} ({len(pdf_bytes):,} bytes)")
