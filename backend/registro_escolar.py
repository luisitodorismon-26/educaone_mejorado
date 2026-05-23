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
from datetime import date
from typing import Dict, List, Optional, Any
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from pypdf import PdfReader, PdfWriter

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

# Páginas de cada sección por grado
# Las páginas de asistencia son 5 pgs por asignatura (10 meses en 5 hojas de 2 meses)
# excepto la última asignatura que puede tener menos
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
        "asistencia_inicio": 17,
        "asistencia_pgs_por_asignatura": 5,  # Salida optativa agrega más
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
    "columnas": {
        # col_name: (x_center, width) - x_center para centrar texto
        "numero": {"x": 42, "w": 18},        # 36.4 - 59.2
        "femenino": {"x": 67, "w": 18},       # 59.2 - 82.0 (marcar X)
        "masculino": {"x": 90, "w": 18},      # 82.0 - 106.5 (marcar X)
        "dia": {"x": 116, "w": 20},           # 106.5 - 131.0
        "mes": {"x": 141, "w": 20},           # 131.0 - 155.5
        "anio": {"x": 166, "w": 22},          # 155.5 - 181.7
        "libro": {"x": 194, "w": 24},         # 181.7 - 210.4
        "folio": {"x": 222, "w": 24},         # 210.4 - 239.0
        "edad": {"x": 256, "w": 14},          # ~239 - ~275
        "cedula": {"x": 340, "w": 75},        # 318.6 - 398.3 (o RNE)
        "rne": {"x": 420, "w": 40},           # 398.3 - ~440
        "lugar_residencia": {"x": 510, "w": 130},  # 398.3 - 575.5
    },
}

# --- CONDICIÓN INICIAL (Pg 12) ---
# Misma estructura de tabla pero con columnas diferentes
# V-lines similares, columnas: No | Correo | Promovido | Repitente | Reingreso
CONDICION_TABLE = {
    "primera_fila_y_plumber": 180.2,
    "row_height": 14.15,
    "total_filas": 40,
    "columnas": {
        "numero": {"x": 42, "w": 18},
        "correo": {"x": 200, "w": 200},
        "promovido": {"x": 410, "w": 40},     # X mark
        "repitente": {"x": 470, "w": 40},     # X mark
        "reingreso": {"x": 530, "w": 40},     # X mark
    },
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

# --- CALIFICACIONES COMPLETIVAS (Pgs 150+) ---
# V-lines: 37.5, 54.4, 98.4, 137.9, 177.6, 217.3, 257.0, 296.7, 336.3, 376.0, 415.7, 455.4, 495.1, 534.8, 574.5
# Columnas: No | CF | [Completiva: CF 50%, CEC 50%, CCF, CF] | [Extraordinaria: 30%, CEX, CF, EEX, CEEX, EXF] | [Especiales: CF, CE, A, R]
COMPLETIVA_TABLE = {
    "primera_fila_y_plumber": 179.6,
    "row_height": 14.2,
    "total_filas": 40,
    "docente_x": 100,
    "docente_y_plumber": 73,
    "columnas": {
        "numero": {"x": 43, "w": 14},
        "cf_original": {"x": 73, "w": 38},         # 54.4 - 98.4
        "comp_cf_50": {"x": 116, "w": 36},          # 98.4 - 137.9
        "comp_cec_50": {"x": 156, "w": 36},         # 137.9 - 177.6
        "comp_ccf": {"x": 196, "w": 36},            # 177.6 - 217.3
        "comp_cf": {"x": 235, "w": 36},             # 217.3 - 257.0
        "extra_30": {"x": 275, "w": 36},            # 257.0 - 296.7
        "extra_c": {"x": 315, "w": 36},             # 296.7 - 336.3
        "extra_70_c": {"x": 354, "w": 36},          # 336.3 - 376.0
        "extra_cf": {"x": 394, "w": 36},            # 376.0 - 415.7
        "espec_cf": {"x": 434, "w": 36},            # 415.7 - 455.4
        "espec_ce": {"x": 473, "w": 36},            # 455.4 - 495.1
        "espec_a": {"x": 513, "w": 36},             # 495.1 - 534.8
        "espec_r": {"x": 553, "w": 36},             # 534.8 - 574.5
    },
}

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
        
        # Número
        _draw_text(c, cols["numero"]["x"], y,
                   str(est.get("numero", i + 1)),
                   size=FONT_SIZE_TABLA, center=True)
        
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
        
        # Número
        _draw_text(c, cols["numero"]["x"], y,
                   str(est.get("numero", i + 1)),
                   size=FONT_SIZE_TABLA, center=True)
        
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
            _draw_text(c, cols["correo"]["x"] - 80, y,
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


def draw_completiva(c: canvas.Canvas, datos: Dict):
    """
    Dibuja calificaciones completivas/extraordinarias (1 pg por asignatura).
    datos: {
        "docente": str,
        "calificaciones": [
            {  # por estudiante (hasta 40)
                "cf_original": float,
                "comp_cf_50": float,
                "comp_cec_50": float,
                "comp_ccf": float,
                "comp_cf": float,
                "extra_30": float,
                "extra_c": float,
                "extra_70_c": float,
                "extra_cf": float,
                "espec_cf": float,
                "espec_ce": float,
                "espec_a": str,  # "A" = Aprobado
                "espec_r": str,  # "R" = Reprobado
            }
        ]
    }
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
                continue  # El número ya está impreso
            
            valor = est.get(col_name)
            if valor is not None and valor != "":
                text = str(valor)
                if isinstance(valor, float):
                    text = f"{valor:.0f}" if valor == int(valor) else f"{valor:.1f}"
                _draw_text(c, col_info["x"], y, text,
                           size=FONT_SIZE_NOTA, center=True)


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
    completiva_data: Optional[Dict] = None,
    promocion_data: Optional[List[Dict]] = None,
    estadisticas_data: Optional[Dict] = None,
    template_dir: Optional[str] = None,
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
        completiva_data: Dict con calificaciones completivas/extraordinarias
        promocion_data: Lista de estudiantes con notas finales para promoción
        estadisticas_data: Dict con estadísticas de fin de año
        template_dir: Directorio donde están los PDFs template (override)
    
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
    if asistencia_data:
        asist_inicio = config["asistencia_inicio"] - 1  # 0-indexed
        pgs_por_asig = config["asistencia_pgs_por_asignatura"]
        
        for a_idx, asig in enumerate(asignaturas):
            asig_key = asig.lower().replace(" ", "_").replace("-", "_")
            asig_data = asistencia_data.get(asig_key, {})
            
            if not asig_data:
                continue
            
            # Cada asignatura tiene ~5 páginas (10 meses, 2 por página)
            meses = asig_data.get("meses", [])
            
            for pg_offset in range(pgs_por_asig):
                pg_idx = asist_inicio + (a_idx * pgs_por_asig) + pg_offset
                
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
            
            # Página izquierda — P1 y P2
            buf = io.BytesIO()
            c_cal = canvas.Canvas(buf, pagesize=letter)
            has_data = False
            
            # === Página IZQUIERDA: PC1, RP1, PC2, RP2 (Competencia 1) ===
            # Geometría medida del template MINERD pag 131 (1ro Sec):
            #   h-lines de filas de notas: 180.72, 194.89, 209.06, ...  (alto = 14.17)
            #   centro vertical fila 1 = (180.72 + 194.89) / 2 = 187.80
            # ReportLab dibuja desde la baseline: para centrar visualmente un texto de
            # FONT_SIZE_NOTA puntos en una celda, la baseline debe caer ~0.35 * font
            # por debajo del centro geométrico de la celda.
            CENTRO_FILA1_PLUMBER = 187.80
            ROW_HEIGHT = 14.17
            row_start_y = _y(CENTRO_FILA1_PLUMBER + FONT_SIZE_NOTA * 0.35)
            row_spacing = ROW_HEIGHT
            # Columnas (x_centro) CE-LE1 medidas: P1=73, RP1=105, P2=138, RP2=170
            COL_P1   = 73
            COL_RP1  = 105
            COL_P2   = 138
            COL_RP2  = 170
            
            for est_idx, est_data in asig_califs.items():
                if not isinstance(est_data, dict):
                    continue
                ei = int(est_idx) if isinstance(est_idx, str) else est_idx
                if ei >= 40:
                    continue
                
                y = row_start_y - (ei * row_spacing)
                
                # MINERD: la página IZQUIERDA muestra el consolidado del período (PC) y su recuperación (RP).
                # PC SOLO aparece cuando los 4 parciales del período están completos
                # (lógica garantizada por Calificacion.calcular_pc en el modelo).
                pc1 = est_data.get('pc1')
                if pc1 is not None:
                    _draw_text(c_cal, COL_P1, y, str(int(pc1)), size=FONT_SIZE_NOTA, center=True)
                    has_data = True
                
                rp1 = est_data.get('rp1')
                if rp1 is not None:
                    _draw_text(c_cal, COL_RP1, y, str(int(rp1)), size=FONT_SIZE_NOTA, center=True)
                
                pc2 = est_data.get('pc2')
                if pc2 is not None:
                    _draw_text(c_cal, COL_P2, y, str(int(pc2)), size=FONT_SIZE_NOTA, center=True)
                    has_data = True
                
                rp2 = est_data.get('rp2')
                if rp2 is not None:
                    _draw_text(c_cal, COL_RP2, y, str(int(rp2)), size=FONT_SIZE_NOTA, center=True)
            
            if has_data:
                c_cal.showPage()
                c_cal.save()
                buf.seek(0)
                overlays[pg_izq] = buf
            
            # Página derecha (pag 132): bloque "Promedio de Competencias Específicas"
            # MINERD: las columnas centrales de la pag derecha son P1/RP1/P2/RP2/P3/RP3/P4/RP4
            # de OTRAS competencias específicas (CE-LEF4 y CE-LEF5). NO son los parciales
            # del consolidado del período. Esas columnas se dejan VACÍAS — el modelo de
            # secundaria del SGE solo lleva 4 períodos (pc1-pc4) y no rompe los indicadores
            # por competencia específica individual.
            if pg_der and pg_der < total_pages:
                buf2 = io.BytesIO()
                c_cal2 = canvas.Canvas(buf2, pagesize=letter)
                has_data2 = False
                
                for est_idx, est_data in asig_califs.items():
                    if not isinstance(est_data, dict):
                        continue
                    ei = int(est_idx) if isinstance(est_idx, str) else est_idx
                    if ei >= 40:
                        continue
                    
                    y = row_start_y - (ei * row_spacing)
                    
                    # Bloque "Promedio de Competencias Específicas" (columna gris derecha)
                    # Coordenadas medidas del PDF MINERD pag 132:
                    # PC1=480, PC2=502, PC3=525, PC4=547, CF=564.5
                    # Cada PC se imprime individualmente cuando el período está completo.
                    pc1 = est_data.get('pc1')
                    if pc1 is not None:
                        _draw_text(c_cal2, 480, y, str(int(pc1)), size=FONT_SIZE_NOTA, center=True)
                        has_data2 = True
                    
                    pc2 = est_data.get('pc2')
                    if pc2 is not None:
                        _draw_text(c_cal2, 502, y, str(int(pc2)), size=FONT_SIZE_NOTA, center=True)
                        has_data2 = True
                    
                    pc3 = est_data.get('pc3')
                    if pc3 is not None:
                        _draw_text(c_cal2, 525, y, str(int(pc3)), size=FONT_SIZE_NOTA, center=True)
                        has_data2 = True
                    
                    pc4 = est_data.get('pc4')
                    if pc4 is not None:
                        _draw_text(c_cal2, 547, y, str(int(pc4)), size=FONT_SIZE_NOTA, center=True)
                        has_data2 = True
                    
                    # Calificación Final — solo cuando los 4 PC están completos
                    # (lógica del modelo Calificacion.calcular_cf en models.py).
                    cf = est_data.get('cf')
                    if cf is not None:
                        _draw_text(c_cal2, 564.5, y, str(int(cf)), size=FONT_SIZE_NOTA, center=True)
                        has_data2 = True
                
                if has_data2:
                    c_cal2.showPage()
                    c_cal2.save()
                    buf2.seek(0)
                    overlays[pg_der] = buf2
    
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
            
            # Salida optativa (solo 4to-6to)
            salida_opt_paginas = config.get("completiva_salida_optativa", [])
            if salida_opt_paginas:
                asig_key = "salida_optativa"
                asig_comp = completiva_data.get(asig_key, {})
                if asig_comp:
                    for pg_num in salida_opt_paginas:
                        pg_idx = pg_num - 1
                        if pg_idx < total_pages:
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
    
    for pg_idx in range(total_pages):
        template_page = template_reader.pages[pg_idx]
        
        if pg_idx in overlays:
            overlay_reader = PdfReader(overlays[pg_idx])
            if len(overlay_reader.pages) > 0:
                overlay_page = overlay_reader.pages[0]
                template_page.merge_page(overlay_page)
        
        writer.add_page(template_page)
    
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

def generar_registro_desde_sistema(colegio_info, curso_info, ano_escolar, estudiantes, asignaturas_data, grado_numero):
    """
    Wrapper que traduce datos de app.py al formato del generador de registro.
    
    asignaturas_data[nombre_asig] = {
        'docente': str,
        'asistencias': {idx_est: {idx_mes: {dia: char}}},
        'calificaciones': {idx_est: {'p1':val, 'rp1':val, ..., 'cf':val}}
    }
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
            "rne": est.get('matricula', ''),
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
                        "docente": data.get('docente', '') if not meses_list else '',
                        "asistencias": est_list,
                        "dias_labels": dias_mes,
                    })
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
        promocion_data=promocion_data if any(p for p in promocion_data) else None,
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
