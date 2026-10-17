"""
registro_primaria.py — Registro Escolar MINERD Nivel Primario (1ro-6to)
=======================================================================
Llena los PDFs OFICIALES del MINERD (1ro-6to Primaria) por overlay.

REG-3 · TODA LA GEOMETRÍA ESTÁ MEDIDA con pymupdf sobre las seis plantillas
reales (líneas, rectángulos y círculos del propio PDF). Donde un grado difiere
de otro, la tabla lo dice explícitamente; donde no, se comprobó que es igual.

Qué llena y de dónde sale cada dato (sin reglas nuevas):
  1. PORTADA: centro, código, año, grado, sección, tanda, regional, distrito.
     1ro tiene su geometría; 2do-6to la misma desplazada 32 pt hacia abajo.
  2. DATOS DEL CENTRO (pág 7, igual en los 6 grados): correo, teléfono,
     dirección, zona y sector (círculos), regional, distrito, director y el
     nombre del maestro TITULAR en "Datos del maestro o la maestra".
  3. DATOS GENERALES DEL ESTUDIANTE: hoja DOBLE (págs 10 y 11) de 45 filas.
     El estudiante se identifica por su Nº de orden (fila), igual que en la
     asistencia: la hoja NO tiene columna de nombre. Izquierda: nacionalidad,
     sexo, fecha de nacimiento, edad. Derecha: dirección y condición inicial
     (tres variantes de columnas: 1ro, 2do y 3ro-6to).
  4. ASISTENCIA MENSUAL: 12 formularios SEMANALES (5 semanas × lunes-viernes
     + resumen del mes). Cada fecha va a SU semana y SU día de la semana; el
     mes sale de REG-1 (formulario 1 = mes de fecha_inicio).
  5. CALIFICACIONES POR ÁREA: hoja DOBLE (izq: C1 y C2; der: C3, promedio por
     competencia y calificación del área). Dos variantes: 1ro-2do (solo P1-P4)
     y 3ro-6to (P y RP por período, y recuperación especial).
  6. ACTA DE RENDIMIENTO: cuatro variantes (1ro, 2do, 3ro, 4to-6to).
  7. ESTADÍSTICAS DE MATRÍCULA (cuadro de edad y sexo).

Los promedios, la calificación del área, la situación final y los porcentajes
de asistencia llegan YA CALCULADOS desde app.py (motor canónico y
asistencia canónica). El PDF no promedia nada por su cuenta.

FAIL CLOSED: más de 45 estudiantes, o una fecha que no cabe en el formulario
semanal (sábado/domingo, más de 5 semanas), no producen un Registro recortado:
se rechaza con `RegistroExcedePlantilla` (422 en app.py).

La recuperación pedagógica (formulario narrativo), las páginas de NEAE/salud,
padres y la ficha completa del docente quedan para llenado manual.

Color tinta azul MINERD. Firma pública compatible con app.py existente.
"""
import io
import json
import os
import unicodedata
from datetime import date
from typing import Dict, List, Optional

from reportlab.pdfgen import canvas
from pypdf import PdfReader, PdfWriter

AZUL_TINTA = (0, 0, 0.7)
FONT_NOTA = 7.5
FONT_DATO = 6.5
FILAS_POR_PAGINA = 45      # todas las tablas de estudiantes del Registro de Primaria


# ─────────────────────────── GEOMETRÍA MEDIDA (REG-3) ───────────────────────────
# Convención: x en puntos desde la izquierda; y "desde arriba" (como pdfplumber
# y pymupdf). Una celda es (x0, x1). Las filas se dan como (primera_y, paso).

# 1 · PORTADA — líneas de 1ro en y = 530.7 / 565.0 / 601.5 / 638.0; las de
# 2do-6to en 562.8 / 597.0 / 633.5 / 670.0 (todo +32 pt). Mismas x.
PORTADA_DY = {1: 0.0, 2: 32.0, 3: 32.0, 4: 32.0, 5: 32.0, 6: 32.0}
PORTADA_CAMPOS = {           # (x, línea base en 1ro)
    'centro': (192, 526), 'codigo': (120, 562), 'anio_inicio': (405, 562),
    'anio_fin': (501, 562), 'grado': (110, 599), 'seccion': (305, 599),
    'tanda': (475, 599), 'regional': (228, 635.5), 'distrito': (481, 635.5),
}

# 2 · DATOS DEL CENTRO (pág 7) — línea base 2.5 pt sobre cada línea.
CENTRO_CAMPOS = {            # (x, línea base, ancho útil)
    'email': (154, 116.8, 230), 'telefono': (443, 116.8, 118),
    'direccion': (108, 135.5, 452), 'regional': (103, 271.4, 212),
    'distrito': (364, 271.4, 196), 'director': (217, 336.5, 343),
    'docente_titular': (181, 501.8, 380),
}
CENTRO_CIRCULOS = {          # centros medidos de los círculos (x, y)
    'zona': {'urbana': (117.0, 198.2), 'urbana_marginal': (232.5, 198.2),
             'urbana_turistica': (380.2, 198.2), 'rural': (117.0, 216.9),
             'rural_aislada': (232.5, 216.9), 'rural_turistica': (380.2, 216.9)},
    'sector': {'publico': (117.0, 239.6), 'privado': (232.5, 239.6),
               'semioficial': (380.2, 239.6)},
}

# 3 · DATOS GENERALES DEL ESTUDIANTE — filas 162.7 + 12.889·i (45 filas).
EST_FILAS = (162.7, 12.889)
EST_IZQ = {                  # pág 10: idéntica en los 6 grados
    'nacionalidad': (36.0, 175.7), 'femenino': (175.7, 203.5), 'masculino': (203.5, 231.3),
    'dia': (231.3, 253.4), 'mes': (253.4, 275.5), 'anio': (275.5, 297.6),
    'edad': (360.2, 396.9),
    # Libro (297.6-328.9), Folio (328.9-360.2) y Parentesco (396.9-575.5): el
    # sistema no los guarda → en blanco.
}
EST_DER = {                  # pág 11: tres variantes
    1: {'direccion': (52.9, 293.0), 'nuevo_ingreso': (446.5, 472.1),
        'promovido': (472.1, 497.7), 'reentrante': (497.7, 523.2)},
    2: {'direccion': (52.9, 332.6), 'promovido': (486.1, 515.8),
        'repitente': (515.8, 545.6), 'reentrante': (545.6, 575.3)},
    3: {'direccion': (52.9, 324.7), 'aplazado': (483.8, 506.8),
        'promovido': (506.8, 529.7), 'repitente': (529.7, 552.7),
        'reentrante': (552.7, 575.6)},
}
# condicion_entrada → columna. Solo lo que el dato DICE: "nuevo" (nuevo en el
# centro) solo es "Nuevo ingreso" en 1ro, que es donde la plantilla lo define
# como "entra por primera vez a primer grado"; "transferido" no tiene columna.
CONDICION_A_COLUMNA = {'promovido': 'promovido', 'repitente': 'repitente',
                       'reingreso': 'reentrante', 'reentrante': 'reentrante',
                       'aplazado': 'aplazado'}

# 4 · ASISTENCIA (12 formularios, mismas columnas en los 6 grados)
ASIST_VERTICALES = [67.0, 85.0, 102.0, 118.1, 135.1, 152.2,      # 1ra semana (L-V)
                    169.2, 186.2, 203.3, 220.3, 237.3,            # 2da
                    254.4, 271.4, 288.4, 305.4, 322.5,            # 3ra
                    339.5, 356.5, 373.6, 390.6, 407.6,            # 4ta
                    424.7, 441.7, 458.7, 475.7, 492.8]            # 5ta
ASIST_RESUMEN = {'presente': (492.8, 509.8), 'tardanza': (509.8, 526.8),
                 'ausente': (526.8, 543.9), 'excusa': (543.9, 560.9)}
ASIST_FILAS = (162.7, 12.889)       # 45 filas hasta 743.2
ASIST_FECHA_Y = 158.0               # banda "Fecha" (148.3-162.7)
ASIST_TOTAL_Y = 752.5               # fila "Total de asistencia" (743.2-756.1)
ASIST_MES = (82, 69.5)              # tras "Mes:" (guiones 79.4-235.4, base 71.1)
ASIST_DIAS_TRAB = (321, 69.5)       # tras "Días trabajados:" (guiones 317.7-539.7)
ASIST_SEMANAS = 5

# 5 · CALIFICACIONES — filas 163.0 + 12.898·i (45 filas hasta 743.4)
CAL_FILAS = (163.0, 12.898)
CAL_VARIANTE = {1: 'A', 2: 'A', 3: 'B', 4: 'B', 5: 'B', 6: 'B'}
CAL_GEOMETRIA = {
    # 1ro-2do: solo P1-P4 (el valor del período ya incluye la recuperación).
    'A': {
        'izq': {1: [('p1', 56.2, 121.1), ('p2', 121.1, 185.9), ('p3', 185.9, 250.8), ('p4', 250.8, 315.7)],
                2: [('p1', 315.7, 380.6), ('p2', 380.6, 445.5), ('p3', 445.5, 510.5), ('p4', 510.5, 575.4)]},
        'der': {3: [('p1', 55.8, 121.1), ('p2', 121.1, 186.3), ('p3', 186.3, 251.6), ('p4', 251.6, 316.8)]},
        'promedio': {1: (316.8, 368.9), 2: (369.0, 421.1), 3: (421.1, 473.2)},
        'final': (473.2, 525.4), 'rec_final': (525.4, 575.8), 'rec_especial': None,
    },
    # 3ro-6to: P y RP de cada período en columnas separadas.
    'B': {
        'izq': {1: [('p1', 56.2, 88.6), ('rp1', 88.6, 121.1), ('p2', 121.1, 153.5), ('rp2', 153.5, 185.9),
                    ('p3', 185.9, 218.4), ('rp3', 218.4, 250.8), ('p4', 250.8, 283.3), ('rp4', 283.3, 315.7)],
                2: [('p1', 315.7, 348.2), ('rp1', 348.2, 380.6), ('p2', 380.6, 413.1), ('rp2', 413.1, 445.5),
                    ('p3', 445.5, 478.0), ('rp3', 478.0, 510.5), ('p4', 510.5, 542.9), ('rp4', 542.9, 575.4)]},
        'der': {3: [('p1', 55.8, 88.4), ('rp1', 88.4, 121.1), ('p2', 121.1, 153.7), ('rp2', 153.7, 186.3),
                    ('p3', 186.3, 218.9), ('rp3', 218.9, 251.6), ('p4', 251.6, 284.2), ('rp4', 284.2, 316.8)]},
        'promedio': {1: (316.8, 360.0), 2: (360.0, 403.1), 3: (403.1, 446.3)},
        'final': (446.3, 489.4), 'rec_final': (489.4, 532.6), 'rec_especial': (532.6, 575.8),
    },
}

# 6 · ACTA DE RENDIMIENTO — cuatro variantes medidas. Cada área: (cara,
# final, rec_final, rec_especial) como celdas; `rec_especial` None en 1ro-2do.
_A12 = {
    'lengua espanola': {'cara': 0, 'final': (267.9, 298.7), 'rec_final': (298.7, 329.5), 'rec_especial': None},
    'matematica': {'cara': 0, 'final': (329.5, 360.4), 'rec_final': (360.4, 391.2), 'rec_especial': None},
    'ciencias sociales': {'cara': 0, 'final': (391.2, 422.1), 'rec_final': (422.1, 452.9), 'rec_especial': None},
    'ciencias de la naturaleza': {'cara': 0, 'final': (452.9, 483.7), 'rec_final': (483.7, 514.6), 'rec_especial': None},
    'educacion fisica': {'cara': 0, 'final': (514.6, 545.4), 'rec_final': (545.4, 576.3), 'rec_especial': None},
    'formacion integral humana y religiosa': {'cara': 1, 'final': (53.4, 86.3), 'rec_final': (86.3, 119.2), 'rec_especial': None},
    'educacion artistica': {'cara': 1, 'final': (119.2, 152.1), 'rec_final': (152.1, 185.0), 'rec_especial': None},
}
_CAB_12 = {'centro': (117, 52.2), 'regional': (79, 68.2, 46), 'distrito': (210.5, 68.2, 46),
           'grado': (292, 68.2, 46), 'seccion': (384.5, 68.2, 46),
           'anio_inicio': (511, 68.2, 24), 'anio_fin': (557, 68.2, 18)}
ACTA_CAL = {
    1: {'filas': (162.7, 12.776), 'nombre': (51.0, 267.9), 'areas': _A12,
        'extras': {'cara': 1, 'pct_asistencia': (185.0, 212.6), 'pct_ausencia': (212.6, 240.2),
                   'pct_excusa': (240.2, 267.8), 'observaciones': (267.8, 574.9)},
        'situacion': None, 'cabecera': _CAB_12},
    2: {'filas': (162.7, 12.889), 'nombre': (51.0, 267.9), 'areas': _A12,
        'extras': {'cara': 1, 'pct_asistencia': (185.0, 212.6), 'pct_ausencia': (212.6, 240.2),
                   'pct_excusa': (240.2, 267.8), 'observaciones': (267.8, 574.9)},
        'situacion': None, 'cabecera': _CAB_12},
    3: {'filas': (154.9, 12.889), 'nombre': (51.7, 268.6),
        'areas': {
            'lengua espanola': {'cara': 0, 'final': (268.6, 289.1), 'rec_final': (289.1, 309.7), 'rec_especial': (309.7, 330.2)},
            'matematica': {'cara': 0, 'final': (330.2, 350.8), 'rec_final': (350.8, 371.4), 'rec_especial': (371.4, 391.9)},
            'ciencias sociales': {'cara': 0, 'final': (391.9, 412.5), 'rec_final': (412.5, 433.0), 'rec_especial': (433.0, 453.6)},
            'ciencias de la naturaleza': {'cara': 0, 'final': (453.6, 474.2), 'rec_final': (474.2, 494.7), 'rec_especial': (494.7, 515.3)},
            'educacion fisica': {'cara': 0, 'final': (515.3, 535.8), 'rec_final': (535.8, 556.4), 'rec_especial': (556.4, 577.0)},
            'formacion integral humana y religiosa': {'cara': 1, 'final': (54.1, 76.0), 'rec_final': (76.0, 98.0), 'rec_especial': (98.0, 119.9)},
            'educacion artistica': {'cara': 1, 'final': (119.9, 141.8), 'rec_final': (141.8, 163.7), 'rec_especial': (163.7, 185.7)},
        },
        'extras': {'cara': 1, 'pct_asistencia': (185.7, 207.2), 'pct_ausencia': (207.2, 228.7),
                   'pct_excusa': (228.7, 250.2), 'observaciones': (314.7, 575.6)},
        'situacion': {'aplazado': (250.2, 271.7), 'promovido': (271.7, 293.2), 'reprobado': (293.2, 314.7)},
        'cabecera': {'centro': (118, 52.2), 'regional': (79.7, 68.2, 46), 'distrito': (211.2, 68.2, 46),
                     'grado': (292.9, 68.2, 46), 'seccion': (385.3, 68.2, 46),
                     'anio_inicio': (511.6, 68.2, 24), 'anio_fin': (557.3, 68.2, 18)}},
}
_A46 = {
    'lengua espanola': {'cara': 0, 'final': (267.1, 287.7), 'rec_final': (287.7, 308.2), 'rec_especial': (308.2, 328.8)},
    'matematica': {'cara': 0, 'final': (328.8, 349.4), 'rec_final': (349.4, 369.9), 'rec_especial': (369.9, 390.5)},
    'ciencias sociales': {'cara': 0, 'final': (390.5, 411.0), 'rec_final': (411.0, 431.6), 'rec_especial': (431.6, 452.2)},
    'ciencias de la naturaleza': {'cara': 0, 'final': (452.2, 472.7), 'rec_final': (472.7, 493.3), 'rec_especial': (493.3, 513.8)},
    'lenguas extranjeras': {'cara': 0, 'final': (513.8, 534.4), 'rec_final': (534.4, 555.0), 'rec_especial': (555.0, 575.5)},
    'educacion fisica': {'cara': 1, 'final': (54.6, 76.5), 'rec_final': (76.5, 98.4), 'rec_especial': (98.4, 120.3)},
    'formacion integral humana y religiosa': {'cara': 1, 'final': (120.3, 142.3), 'rec_final': (142.3, 164.2), 'rec_especial': (164.2, 186.1)},
    'educacion artistica': {'cara': 1, 'final': (186.1, 208.0), 'rec_final': (208.0, 230.0), 'rec_especial': (230.0, 251.9)},
}
for _g in (4, 5, 6):        # 4to, 5to y 6to: plantilla idéntica (verificado)
    ACTA_CAL[_g] = {
        'filas': (155.6, 12.889), 'nombre': (51.7, 267.1), 'areas': _A46,
        'extras': {'cara': 1, 'pct_asistencia': (251.9, 273.4), 'pct_ausencia': (273.4, 294.9),
                   'pct_excusa': (294.9, 316.4), 'observaciones': (380.9, 575.5)},
        'situacion': {'aplazado': (316.4, 337.9), 'promovido': (337.9, 359.4), 'reprobado': (359.4, 380.9)},
        'cabecera': {'centro': (118, 52.9), 'regional': (79.7, 68.9, 46), 'distrito': (211.1, 68.9, 46),
                     'grado': (292.6, 68.9, 46), 'seccion': (384.7, 68.9, 46),
                     'anio_inicio': (510.3, 68.9, 24), 'anio_fin': (555.9, 68.9, 18)},
    }
# Condición canónica (promocion_academica) → columna de "Situación del/de la
# estudiante". EN_PROCESO no marca nada: el año no ha decidido todavía.
SITUACION_A_COLUMNA = {'PROMOVIDO': 'promovido', 'APLAZADO': 'aplazado', 'REPROBADO': 'reprobado'}

# 7 · ESTADÍSTICAS DE MATRÍCULA (cuadro 1 "Cantidad de estudiantes, sexo y
# edad"). Ya estaba bien medido (verticales 50.1/149.8/227.9/306.0, bandas de
# 23.75); se conserva tal cual.
EDAD_COL_EDAD = 100.0
EDAD_COL_MASC = 188.9
EDAD_COL_FEM = 267.0
EDAD_FILA_Y0 = 126.1
EDAD_FILA_H = 23.75
EDAD_FILAS_MAX = 10
EDAD_AJUSTE = 16.0

# ─────────────────────────── ÁREAS OFICIALES ───────────────────────────
# nombre canónico → variantes con que puede venir la asignatura del colegio
# (espejo del normalizador del boletín de primaria)
AREAS_CANON = {
    'lengua espanola': ['lengua espanola', 'espanol', 'lengua'],
    'matematica': ['matematica', 'matematicas'],
    'ciencias sociales': ['ciencias sociales', 'sociales'],
    'ciencias de la naturaleza': ['ciencias de la naturaleza', 'ciencias naturales', 'naturales'],
    'educacion fisica': ['educacion fisica'],
    'educacion artistica': ['educacion artistica', 'artistica'],
    'formacion integral humana y religiosa': ['formacion integral humana y religiosa',
                                              'formacion integral', 'religion'],
    'lenguas extranjeras': ['lenguas extranjeras (ingles)', 'lenguas extranjeras', 'ingles',
                            'lenguas extranjeras - ingles'],
    'talleres optativos': ['talleres optativos', 'talleres'],
}


def _sin_acentos(s: str) -> str:
    return unicodedata.normalize('NFKD', (s or '')).encode('ascii', 'ignore').decode('ascii').lower().strip()


def area_canonica(nombre_asignatura: str) -> Optional[str]:
    """Mapea el nombre de la asignatura del colegio al área oficial MINERD."""
    n = _sin_acentos(nombre_asignatura)
    for canon, variantes in AREAS_CANON.items():
        if n == canon or n in variantes:
            return canon
    return None


def get_template_path(grado_numero: int) -> str:
    nombres = {1: "Registro-1er-Grado-Primaria.pdf", 2: "Registro-2do-Grado-Primaria.pdf",
               3: "Registro-3er-Grado-Primaria.pdf", 4: "Registro-4to-Grado-Primaria.pdf",
               5: "Registro-5to-Grado-Primaria.pdf", 6: "Registro-6to-Grado-Primaria.pdf"}
    fname = nombres.get(grado_numero)
    if not fname:
        raise ValueError(f"Grado {grado_numero} inválido para primaria (debe ser 1-6)")
    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_dir, "templates", "registro_escolar", "primaria", fname)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Template primaria no encontrada: {path}")
    return path


# ─────────────────── ÍNDICE DINÁMICO DE SECCIONES ───────────────────
_INDICE_CACHE: Dict[int, Dict] = {}
# Subir esta versión invalida los índices guardados en disco (si cambian las
# anclas de búsqueda o la estructura del índice).
_INDICE_VERSION = 3


def _ruta_cache_indice(grado_numero: int) -> str:
    """Archivo JSON donde se persiste el índice de un grado."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    cache_dir = os.path.join(base_dir, '.cache_registro')
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f'indice_primaria_{grado_numero}.json')


def _construir_indice(grado_numero: int) -> Dict:
    """Escanea el template UNA vez con pypdf y localiza secciones por texto.

    Devuelve: {'portada': int, 'estudiantes': [pág 1-45, pág 46-90],
               'calificaciones': {area_canon: [pág 1-45, pág 46-90]}}
    Cacheado por grado (el proceso completo toma ~1-2 s y solo la 1ra vez).
    """
    if grado_numero in _INDICE_CACHE:
        return _INDICE_CACHE[grado_numero]

    # v2.17 PERF: el índice es DETERMINISTA (el template oficial no cambia).
    # Escanearlo cuesta ~6 s por grado, así que se persiste en disco: la
    # primera generación lo calcula, todas las demás lo leen en milisegundos
    # (sobrevive a reinicios del servidor y sirve a todos los workers).
    _ruta = _ruta_cache_indice(grado_numero)
    try:
        if os.path.exists(_ruta):
            with open(_ruta, 'r', encoding='utf-8') as fh:
                guardado = json.load(fh)
            if guardado.get('_v') == _INDICE_VERSION:
                indice = guardado['indice']
                # JSON convierte las claves de dict a string: restaurar tipos
                indice['calificaciones'] = dict(indice.get('calificaciones') or {})
                _INDICE_CACHE[grado_numero] = indice
                return indice
    except Exception:
        pass  # cache corrupto o ilegible: se recalcula

    reader = PdfReader(get_template_path(grado_numero))
    indice = {'portada': None, 'centro': None, 'estudiantes': [], 'asistencia': [], 'acta': [],
              'estadisticas': None, 'calificaciones': {}}

    # v2.17 PERF: parada temprana. Todas las secciones que buscamos viven en
    # las primeras ~112 páginas; el resto del template son anexos. Cuando ya
    # tenemos todo, cortamos el escaneo en vez de leer las 142 páginas.
    def _indice_completo() -> bool:
        return (indice['portada'] is not None
                and indice['centro'] is not None
                and indice['estadisticas'] is not None
                and len(indice['estudiantes']) >= 2
                and len(indice['asistencia']) >= 12
                and len(indice['acta']) >= 2
                and len(indice['calificaciones']) >= 7)

    for i, page in enumerate(reader.pages):
        if _indice_completo():
            break
        try:
            txt = page.extract_text() or ''
        except Exception:
            txt = ''
        plano = _sin_acentos(txt)

        if indice['portada'] is None and 'registro' in plano and 'nivel primario' in plano \
                and 'centro educativo' in plano:
            indice['portada'] = i
            continue

        # Datos del Centro Educativo: título + 'paraje' (evita confusiones)
        if indice['centro'] is None and 'datos del centro educativo' in plano \
                and 'paraje' in plano:
            indice['centro'] = i
            continue

        # 'orden alfabetico' distingue las páginas REALES de la tabla de
        # estudiantes (10-11) de la página del ÍNDICE, que solo lista el título.
        if 'orden alfabetico' in plano and len(indice['estudiantes']) < 2:
            indice['estudiantes'].append(i)
            continue

        # F4: Estadísticas de matrícula (cuadro de edad y sexo)
        if indice['estadisticas'] is None and 'cantidad de estudiantes, sexo y edad' in plano:
            indice['estadisticas'] = i
            continue

        # F3: Acta de rendimiento de fin de año (2 caras del mismo pliego).
        # 'centro educativo' descarta la página de instrucciones, que menciona
        # el acta pero no tiene el formulario.
        if 'acta de rendimiento' in plano and 'centro educativo' in plano \
                and 'indice' not in plano and len(indice['acta']) < 2:
            indice['acta'].append(i)
            continue

        # Formulario mensual de asistencia (12 páginas): título COMPLETO de la
        # sección + banda "Fecha" del grid. El título completo evita el falso
        # positivo de "Datos del docente" (que menciona asistencia y fecha).
        # Triple ancla del formulario REAL: título de sección + "Semana"
        # (encabezados 1ra-5ta) + banda "Fecha" del grid. Descarta a la vez la
        # ficha del docente (sin semana) y las instrucciones (sin fecha).
        if 'control de asistencia y puntualidad' in plano and 'semana' in plano \
                and 'fecha' in plano and len(indice['asistencia']) < 12:
            indice['asistencia'].append(i)
            continue

        # Página de calificaciones: menciona las competencias PERO NO es una
        # página de "Aspectos trabajados" (30-79) ni el índice — verificado
        # empíricamente: pág 80 no contiene 'aspectos trabajados'; 42 y 5 sí.
        if 'comunicativa' in plano and 'aspectos trabajados' not in plano:
            for canon in AREAS_CANON:
                if canon in plano:
                    indice['calificaciones'].setdefault(canon, [])
                    if len(indice['calificaciones'][canon]) < 2:
                        indice['calificaciones'][canon].append(i)
                    break

    _INDICE_CACHE[grado_numero] = indice
    try:
        with open(_ruta_cache_indice(grado_numero), 'w', encoding='utf-8') as fh:
            json.dump({'_v': _INDICE_VERSION, 'indice': indice}, fh)
    except Exception:
        pass  # si el disco es de solo lectura, seguimos con el cache en memoria
    return indice


# ─────────────────────────── DIBUJO ───────────────────────────
def _excede(motivo: str, mensaje: str, **detalle):
    """REG-3 · FAIL CLOSED con la MISMA excepción que el Registro de
    Secundaria, que app.py ya convierte en 422."""
    from registro_escolar import RegistroExcedePlantilla
    raise RegistroExcedePlantilla(dict({'motivo': motivo, 'mensaje': mensaje}, **detalle))


def _fmt_nota(v) -> str:
    if v is None:
        return ''
    f = float(v)
    return str(int(f)) if f == int(f) else f'{f:.1f}'


def _overlay(page, draw_func):
    """Crea un overlay del tamaño EXACTO del mediabox de la página y lo fusiona.
    (Verificado Fase 0.2: el espacio del overlay coincide 1:1 con el medido.)"""
    w = float(page.mediabox.width)
    h = float(page.mediabox.height)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(w, h))
    c.setFillColorRGB(*AZUL_TINTA)
    draw_func(c, w, h)
    c.showPage()
    c.save()
    buf.seek(0)
    page.merge_page(PdfReader(buf).pages[0])


def _valor_efectivo(comp_data: Dict, p: int):
    """Valor del período, según la definición canónica de Primaria."""
    from calculo_primaria import valor_periodo_primaria
    pv = comp_data.get(f'p{p}')
    rv = comp_data.get(f'rp{p}')
    v = valor_periodo_primaria(
        float(pv) if pv is not None else None,
        float(rv) if rv is not None else None)
    return None if v is None else float(v)


def _base_fila(filas, i: int, alto_pagina: float, ajuste: float = 9.2) -> float:
    """Línea base (ReportLab, desde abajo) de la fila i (0-based)."""
    y0, paso = filas
    return alto_pagina - (y0 + i * paso + ajuste)


def _centro(celda) -> float:
    return (celda[0] + celda[1]) / 2.0


def _texto_en_celda(c, celda, y, texto, size, centrado=False, margen=1.5):
    """Texto dentro de la celda: se achica hasta caber y, solo si aun así no
    cabe, se corta con "…" (visible). Nunca invade la celda vecina."""
    texto = str(texto)
    util = (celda[1] - celda[0]) - 2 * margen
    s = size
    while s > 4.5 and c.stringWidth(texto, 'Helvetica', s) > util:
        s -= 0.25
    if c.stringWidth(texto, 'Helvetica', s) > util:
        while len(texto) > 1 and c.stringWidth(texto + '…', 'Helvetica', s) > util:
            texto = texto[:-1]
        texto += '…'
    c.setFont('Helvetica', s)
    if centrado:
        c.drawCentredString(_centro(celda), y, texto)
    else:
        c.drawString(celda[0] + margen, y, texto)


def _x(c, celda, y, size=7.5):
    c.setFont('Helvetica-Bold', size)
    c.drawCentredString(_centro(celda), y, 'X')


def _clave(texto) -> str:
    return unicodedata.normalize('NFKD', str(texto or '')).encode(
        'ascii', 'ignore').decode('ascii').strip().lower().replace(' ', '_')


def _semana_y_dia(fecha: date):
    """(semana 0-4, día 0-4) de una fecha en el formulario semanal del mes.

    La 1ra semana es la primera semana del mes que tiene un día lunes-viernes;
    las demás siguen el calendario. Así una fecha cae siempre en la columna de
    su día de la semana, y un mes ocupa como mucho 5 semanas.
    """
    primero = date(fecha.year, fecha.month, 1)
    lunes0 = date.fromordinal(primero.toordinal() - primero.weekday())
    if primero.weekday() >= 5:      # empieza en fin de semana: la 1ra es la siguiente
        lunes0 = date.fromordinal(lunes0.toordinal() + 7)
    return (fecha.toordinal() - lunes0.toordinal()) // 7, fecha.weekday()


# ─────────────────────────── GENERADOR ───────────────────────────
def generar_registro_primaria(
    grado_numero: int,
    datos_centro: Dict,
    datos_portada: Dict,
    estudiantes: List[Dict],
    calificaciones_data: Optional[Dict] = None,
    asistencia_data=None,
    dias_trabajados=None,
    recuperaciones_data: Optional[Dict] = None,   # {est_idx: {area: {'final':x,'especial':y}}}
    condiciones_data: Optional[Dict] = None,      # {est_idx: {'condicion', 'etiqueta', 'asistencia'}}
) -> bytes:
    """Genera el Registro Escolar de Primaria MINERD."""
    estudiantes = list(estudiantes or [])
    if len(estudiantes) > FILAS_POR_PAGINA:
        _excede('ESTUDIANTES_EXCEDEN_PLANTILLA',
                f'El curso tiene {len(estudiantes)} estudiantes y el Registro de Primaria solo '
                f'tiene {FILAS_POR_PAGINA} filas. No se emite un Registro que deje estudiantes fuera.',
                estudiantes=len(estudiantes), filas=FILAS_POR_PAGINA)

    reader = PdfReader(get_template_path(grado_numero))
    writer = PdfWriter()
    indice = _construir_indice(grado_numero)
    recuperaciones_data = recuperaciones_data or {}
    condiciones_data = condiciones_data or {}

    def _rec(est_idx, area):
        return ((recuperaciones_data.get(est_idx) or recuperaciones_data.get(str(est_idx)) or {})
                .get(area) or {})

    # ── 1 · Portada ──
    def draw_portada(c, w, h):
        dy = PORTADA_DY[grado_numero]
        c.setFont("Helvetica", 10)

        def _dos_digitos(anio):
            s = str(anio or '').strip()
            return s[-2:] if len(s) >= 2 else s
        valores = {
            'centro': datos_centro.get('nombre', ''), 'codigo': datos_centro.get('codigo_centro', ''),
            'anio_inicio': _dos_digitos(datos_portada.get('anio_inicio')),
            'anio_fin': _dos_digitos(datos_portada.get('anio_fin')),
            'grado': f"{grado_numero}°", 'seccion': datos_portada.get('seccion', 'A') or 'A',
            'tanda': datos_portada.get('tanda', ''), 'regional': datos_centro.get('regional', ''),
            'distrito': datos_centro.get('distrito', ''),
        }
        for campo, (x, base) in PORTADA_CAMPOS.items():
            if valores.get(campo):
                c.drawString(x, h - base - dy, str(valores[campo]))

    # ── 2 · Datos del Centro + nombre del maestro titular ──
    def draw_centro(c, w, h):
        for campo, (x, base, ancho) in CENTRO_CAMPOS.items():
            valor = str(datos_centro.get(campo, '') or '')
            if valor:
                _texto_en_celda(c, (x, x + ancho), h - base, valor, 9.5)
        for grupo in ('zona', 'sector'):
            pos = CENTRO_CIRCULOS[grupo].get(_clave(datos_centro.get(grupo)))
            if pos:
                c.setFont('Helvetica-Bold', 9)
                c.drawCentredString(pos[0], h - pos[1] - 3.2, 'X')

    # ── 3 · Datos generales del estudiante (hoja doble) ──
    variante_der = 1 if grado_numero == 1 else 2 if grado_numero == 2 else 3

    def _edad(fn):
        """Edad cumplida al 31-dic del año de inicio (mismo criterio que la
        estadística de matrícula de esta plantilla)."""
        try:
            corte = int(str(datos_portada.get('anio_inicio') or '').strip())
        except (TypeError, ValueError):
            return None
        return corte - fn.year

    def draw_estudiantes_izq(c, w, h):
        for i, est in enumerate(estudiantes):
            y = _base_fila(EST_FILAS, i, h)
            if est.get('nacionalidad'):
                _texto_en_celda(c, EST_IZQ['nacionalidad'], y, est['nacionalidad'], FONT_DATO)
            sexo = str(est.get('sexo', '') or '')[:1].upper()
            if sexo in ('F', 'M'):
                _x(c, EST_IZQ['femenino' if sexo == 'F' else 'masculino'], y, 7)
            fn = est.get('fecha_nacimiento')
            if fn and hasattr(fn, 'year'):
                c.setFont('Helvetica', FONT_DATO)
                for campo, valor in (('dia', fn.day), ('mes', fn.month), ('anio', fn.year)):
                    c.drawCentredString(_centro(EST_IZQ[campo]), y, str(valor))
                edad = _edad(fn)
                if edad is not None and 0 < edad < 30:
                    c.drawCentredString(_centro(EST_IZQ['edad']), y, str(edad))

    def draw_estudiantes_der(c, w, h):
        cols = EST_DER[variante_der]
        for i, est in enumerate(estudiantes):
            y = _base_fila(EST_FILAS, i, h)
            if est.get('direccion'):
                _texto_en_celda(c, cols['direccion'], y, est['direccion'], FONT_DATO)
            cond = str(est.get('condicion_entrada', '') or '').strip().lower()
            col = CONDICION_A_COLUMNA.get(cond)
            if cond == 'nuevo' and grado_numero == 1:
                col = 'nuevo_ingreso'
            if col and col in cols:
                _x(c, cols[col], y, 7)

    # ── 4 · Asistencia mensual: formulario SEMANAL ──
    def draw_asistencia_mes(mes_data: Dict):
        anio = mes_data.get('anio')
        mes_num = mes_data.get('mes_num')
        dias = list(mes_data.get('dias') or [])
        filas = list(mes_data.get('filas') or [])
        # Columna de cada día del mes: (semana, día de la semana).
        columnas = []
        for dia in dias:
            if not (anio and mes_num):
                _excede('ASISTENCIA_SIN_FECHA', 'El mes de asistencia no trae año: no se puede '
                        'ubicar cada día en su semana.', mes=mes_data.get('mes'))
            f = date(int(anio), int(mes_num), int(dia))
            semana, dsem = _semana_y_dia(f)
            if dsem >= 5 or semana >= ASIST_SEMANAS:
                _excede('DIA_FUERA_DEL_FORMULARIO',
                        f'{f.isoformat()} no tiene casilla en el formulario semanal de Primaria '
                        f'(lunes a viernes, 5 semanas). No se imprime un Registro que lo esconda.',
                        fecha=f.isoformat())
            columnas.append(semana * 5 + dsem)

        def draw(c, w, h):
            c.setFont("Helvetica-Bold", 9)
            nombre = str(mes_data.get('mes', '') or '').upper()
            if anio:
                nombre = f"{nombre} {anio}"
            c.drawString(ASIST_MES[0], h - ASIST_MES[1], nombre)
            dt = mes_data.get('dias_trabajados_configurados')
            if dt:
                c.drawString(ASIST_DIAS_TRAB[0], h - ASIST_DIAS_TRAB[1], str(dt))
            c.setFont("Helvetica", 6.5)
            for j, dia in enumerate(dias):
                k = columnas[j]
                celda = (ASIST_VERTICALES[k], ASIST_VERTICALES[k + 1])
                c.drawCentredString(_centro(celda), h - ASIST_FECHA_Y, str(dia))
            totales = [0] * len(dias)
            for i, fila in enumerate(filas):
                y = _base_fila(ASIST_FILAS, i, h)
                valores = fila.get('valores') or []
                c.setFont("Helvetica", 6.5)
                for j in range(min(len(valores), len(dias))):
                    cod = (valores[j] or '').strip()
                    if not cod:
                        continue
                    k = columnas[j]
                    c.drawCentredString(_centro((ASIST_VERTICALES[k], ASIST_VERTICALES[k + 1])), y, cod)
                    if cod in ('P', 'T'):
                        totales[j] += 1
                # Resumen del mes: los conteos de la asistencia canónica (la
                # celda «-», NO APLICA, y las sesiones no impartidas no cuentan).
                excusas = max((fila.get('con_dato') or 0) - (fila.get('presentes') or 0)
                              - (fila.get('tardanzas') or 0) - (fila.get('ausentes') or 0), 0)
                if fila.get('con_dato'):
                    for campo, valor in (('presente', fila.get('presentes')), ('tardanza', fila.get('tardanzas')),
                                         ('ausente', fila.get('ausentes')), ('excusa', excusas)):
                        c.drawCentredString(_centro(ASIST_RESUMEN[campo]), y, str(valor or 0))
            # Total de asistencia (presentes + tardanzas) de cada día con marcas.
            c.setFont("Helvetica-Bold", 6.5)
            no_imp = mes_data.get('dias_no_impartidos') or []
            for j, dia in enumerate(dias):
                if totales[j] and dia not in no_imp:
                    k = columnas[j]
                    c.drawCentredString(_centro((ASIST_VERTICALES[k], ASIST_VERTICALES[k + 1])),
                                        h - ASIST_TOTAL_Y, str(totales[j]))
        return draw

    # ── 5 · Calificaciones de un área (hoja doble) ──
    var_cal = CAL_GEOMETRIA[CAL_VARIANTE[grado_numero]]

    def _celdas_periodos(c, y, cd, columnas):
        c.setFont("Helvetica", FONT_NOTA)
        for clave, x0, x1 in columnas:
            if CAL_VARIANTE[grado_numero] == 'A':
                val = _valor_efectivo(cd, int(clave[-1]))      # P ya con su recuperación
            else:
                val = cd.get(clave)                              # P y RP por separado
                val = float(val) if val is not None else None
            if val is not None:
                c.drawCentredString((x0 + x1) / 2, y, _fmt_nota(val))

    def draw_cal_izq(area_data: Dict):
        def draw(c, w, h):
            for est_idx in range(len(estudiantes)):
                comps = area_data.get(est_idx) or area_data.get(str(est_idx)) or {}
                y = _base_fila(CAL_FILAS, est_idx, h)
                for num, columnas in var_cal['izq'].items():
                    cd = comps.get(num) or comps.get(str(num)) or {}
                    if cd:
                        _celdas_periodos(c, y, cd, columnas)
        return draw

    def draw_cal_der(area_data: Dict, canon: str):
        def draw(c, w, h):
            for est_idx in range(len(estudiantes)):
                comps = area_data.get(est_idx) or area_data.get(str(est_idx)) or {}
                y = _base_fila(CAL_FILAS, est_idx, h)
                for num, columnas in var_cal['der'].items():
                    cd = comps.get(num) or comps.get(str(num)) or {}
                    if cd:
                        _celdas_periodos(c, y, cd, columnas)
                # Promedio del área por competencia: la CF oficial de cada
                # competencia que calcula EducaOne (no se promedia aquí).
                c.setFont("Helvetica", FONT_NOTA)
                for num, celda in var_cal['promedio'].items():
                    cd = comps.get(num) or comps.get(str(num)) or {}
                    v = cd.get('cf_oficial', cd.get('final_competencia'))
                    if v is not None:
                        c.drawCentredString(_centro(celda), y, _fmt_nota(v))
                area = comps.get('_area') or {}
                if area.get('cf') is not None:
                    c.setFont("Helvetica-Bold", FONT_NOTA)
                    c.drawCentredString(_centro(var_cal['final']), y, _fmt_nota(area['cf']))
                rec = _rec(est_idx, canon)
                c.setFont("Helvetica", FONT_NOTA)
                if rec.get('final') is not None:
                    c.drawCentredString(_centro(var_cal['rec_final']), y, _fmt_nota(rec['final']))
                if rec.get('especial') is not None and var_cal['rec_especial']:
                    c.drawCentredString(_centro(var_cal['rec_especial']), y, _fmt_nota(rec['especial']))
        return draw

    overlays_por_pagina: Dict[int, list] = {}

    def agendar(pg_idx, fn):
        if pg_idx is not None and 0 <= pg_idx < len(reader.pages):
            overlays_por_pagina.setdefault(pg_idx, []).append(fn)

    # REG-1: cada mes va al formulario de SU POSICIÓN en el año escolar del
    # colegio (formulario 1 = mes de fecha_inicio); un mes sin marcas conserva su
    # formulario. FAIL CLOSED: fuera del año, o más meses que formularios.
    from registro_asistencia import (verificar_dentro_del_ano, verificar_huecos,
                                     meses_necesarios)
    paginas_asist = indice.get('asistencia') or []
    if asistencia_data:
        verificar_dentro_del_ano(asistencia_data, 'Asistencia de Primaria')
        verificar_huecos(meses_necesarios(asistencia_data), len(paginas_asist),
                         'Asistencia de Primaria')
    for i, mes_data in enumerate(asistencia_data or []):
        if not mes_data:
            continue
        if len(mes_data.get('filas') or []) > FILAS_POR_PAGINA:
            _excede('ESTUDIANTES_EXCEDEN_PLANTILLA', 'El formulario de asistencia tiene 45 filas.')
        slot = mes_data.get('posicion', i)
        agendar(paginas_asist[slot], draw_asistencia_mes(mes_data))

    # ── 7 · Estadísticas de matrícula — cuadro de edad y sexo ──
    def draw_estadisticas(c, w, h):
        try:
            anio_corte = int(str(datos_portada.get('anio_inicio') or '').strip())
        except (TypeError, ValueError):
            anio_corte = date.today().year
        # Edad cumplida al 31 de diciembre del año de inicio (criterio MINERD)
        conteo = {}
        for est in estudiantes:
            fn = est.get('fecha_nacimiento')
            if not fn:
                continue
            try:
                anio_nac = fn.year
            except AttributeError:
                try:
                    anio_nac = int(str(fn)[:4])
                except (TypeError, ValueError):
                    continue
            edad = anio_corte - anio_nac
            if not (3 <= edad <= 25):
                continue
            sexo = str(est.get('sexo', '') or '').strip().upper()[:1]
            m, f = conteo.get(edad, (0, 0))
            if sexo == 'M':
                conteo[edad] = (m + 1, f)
            elif sexo == 'F':
                conteo[edad] = (m, f + 1)
        if not conteo:
            return
        c.setFont("Helvetica", 8.5)
        tot_m = tot_f = 0
        for i, edad in enumerate(sorted(conteo)[:EDAD_FILAS_MAX]):
            m, f = conteo[edad]
            tot_m += m
            tot_f += f
            y = h - (EDAD_FILA_Y0 + i * EDAD_FILA_H) - EDAD_AJUSTE
            c.drawCentredString(EDAD_COL_EDAD, y, str(edad))
            c.drawCentredString(EDAD_COL_MASC, y, str(m))
            c.drawCentredString(EDAD_COL_FEM, y, str(f))
        y_tot = h - (EDAD_FILA_Y0 + EDAD_FILAS_MAX * EDAD_FILA_H) - EDAD_AJUSTE
        c.setFont("Helvetica-Bold", 8.5)
        c.drawCentredString(EDAD_COL_MASC, y_tot, str(tot_m))
        c.drawCentredString(EDAD_COL_FEM, y_tot, str(tot_f))

    agendar(indice.get('estadisticas'), draw_estadisticas)

    # ── 6 · Acta de rendimiento de fin de año ──
    def draw_acta(cara: int, cal_grado: Dict):
        def draw(c, w, h):
            # Cabecera (las dos caras la repiten).
            cab = cal_grado['cabecera']
            c.setFont("Helvetica", 7.5)
            x, base = cab['centro']
            if datos_centro.get('nombre'):
                _texto_en_celda(c, (x, 572), h - base, datos_centro['nombre'], 8)
            for campo, valor in (('regional', datos_centro.get('regional')),
                                 ('distrito', datos_centro.get('distrito')),
                                 ('grado', f"{grado_numero}°"),
                                 ('seccion', datos_portada.get('seccion')),
                                 ('anio_inicio', str(datos_portada.get('anio_inicio') or '')[-2:]),
                                 ('anio_fin', str(datos_portada.get('anio_fin') or '')[-2:])):
                if valor:
                    x, base, ancho = cab[campo]
                    _texto_en_celda(c, (x, x + ancho), h - base, valor, 7.5)

            for est_idx, est in enumerate(estudiantes):
                y = _base_fila(cal_grado['filas'], est_idx, h)
                # El Nº de orden ya viene impreso; el nombre solo en la cara 0.
                if cara == 0 and est.get('nombre'):
                    _texto_en_celda(c, cal_grado['nombre'], y, est['nombre'], FONT_DATO)
                c.setFont("Helvetica", FONT_NOTA)
                for area_canon, cols in cal_grado['areas'].items():
                    if cols['cara'] != cara:
                        continue
                    final = _final_area(est_idx, area_canon)
                    if final is not None:
                        c.drawCentredString(_centro(cols['final']), y, _fmt_nota(final))
                    rec = _rec(est_idx, area_canon)
                    if rec.get('final') is not None and cols.get('rec_final'):
                        c.drawCentredString(_centro(cols['rec_final']), y, _fmt_nota(rec['final']))
                    if rec.get('especial') is not None and cols.get('rec_especial'):
                        c.drawCentredString(_centro(cols['rec_especial']), y, _fmt_nota(rec['especial']))
                ex = cal_grado['extras']
                if cara != ex['cara']:
                    continue
                cond = condiciones_data.get(est_idx) or condiciones_data.get(str(est_idx)) or {}
                if isinstance(cond, str):          # contrato anterior: solo la etiqueta
                    cond = {'etiqueta': cond}
                # Presencia y ausencia: la asistencia anual CANÓNICA. Los
                # porcentajes oficiales solo existen con cobertura completa.
                anual = cond.get('asistencia') or {}
                if anual.get('cobertura_completa'):
                    c.setFont("Helvetica", FONT_NOTA)
                    for campo in ('pct_asistencia', 'pct_ausencia', 'pct_excusa'):
                        v = anual.get(campo)
                        if v is not None:
                            c.drawCentredString(_centro(ex[campo]), y, str(int(round(v))))
                # Situación final: la del motor canónico. EN_PROCESO no marca.
                col = SITUACION_A_COLUMNA.get(cond.get('condicion') or '')
                if cal_grado['situacion'] and col:
                    _x(c, cal_grado['situacion'][col], y, 7)
                elif not cal_grado['situacion'] and col and cond.get('etiqueta'):
                    # 1ro-2do no tienen columnas de situación: va en Observaciones.
                    _texto_en_celda(c, ex['observaciones'], y, cond['etiqueta'], FONT_DATO)
        return draw

    def _final_area(est_idx, area_canon):
        """Calificación final del área: la CF oficial que calcula EducaOne
        (`calculo_primaria.cf_area`), llegada en `_area`. Nada se promedia aquí."""
        for nombre_asig, area_data in (calificaciones_data or {}).items():
            if area_canonica(nombre_asig) != area_canon:
                continue
            comps = area_data.get(est_idx) or area_data.get(str(est_idx)) or {}
            return (comps.get('_area') or {}).get('cf')
        return None

    _cal_acta = ACTA_CAL.get(grado_numero)
    _pags_acta = indice.get('acta') or []
    if _cal_acta and len(_pags_acta) >= 2:
        for cara in (0, 1):
            agendar(_pags_acta[cara], draw_acta(cara, _cal_acta))

    agendar(indice['portada'], draw_portada)
    agendar(indice.get('centro'), draw_centro)
    _pags_est = indice['estudiantes'][:2]
    if estudiantes and len(_pags_est) == 2:
        agendar(_pags_est[0], draw_estudiantes_izq)
        agendar(_pags_est[1], draw_estudiantes_der)

    # Calificaciones: cada área ocupa UNA hoja doble (izquierda + derecha).
    for nombre_asig, area_data in (calificaciones_data or {}).items():
        canon = area_canonica(nombre_asig)
        if not canon:
            continue  # asignatura sin área oficial (no se pinta nada aproximado)
        paginas = indice['calificaciones'].get(canon) or []
        if len(paginas) >= 2:
            agendar(paginas[0], draw_cal_izq(area_data))
            agendar(paginas[1], draw_cal_der(area_data, canon))

    # ── Ensamblar ──
    for pg_idx, page in enumerate(reader.pages):
        for fn in overlays_por_pagina.get(pg_idx, []):
            _overlay(page, fn)
        writer.add_page(page)

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def generar_registro_primaria_desde_sistema(
    colegio_info: Dict, curso_info: Dict, ano_escolar: str,
    estudiantes: List[Dict], calificaciones_por_area: Dict,
    asistencia_por_mes, dias_trabajados: Dict, grado_numero: int,
    recuperaciones_por_area: Optional[Dict] = None,
    condiciones_finales: Optional[Dict] = None,
) -> bytes:
    """Wrapper con la MISMA firma que consume app.py."""
    anios = str(ano_escolar).split('-')
    datos_portada = {
        "anio_inicio": anios[0] if len(anios) > 0 else "",
        "anio_fin": anios[1] if len(anios) > 1 else "",
        "seccion": curso_info.get('seccion', 'A'),
        "tanda": curso_info.get('tanda', ''),
    }
    datos_centro = {
        "nombre": colegio_info.get('nombre', ''),
        "regional": colegio_info.get('regional', ''),
        "distrito": colegio_info.get('distrito', ''),
        "codigo_centro": colegio_info.get('codigo_centro', ''),
        "email": colegio_info.get('email', ''),
        "telefono": colegio_info.get('telefono', ''),
        "direccion": colegio_info.get('direccion', ''),
        "director": colegio_info.get('director', ''),
        "docente_titular": colegio_info.get('docente_titular', ''),
        "zona": colegio_info.get('zona', ''),
        "sector": colegio_info.get('sector', ''),
    }
    return generar_registro_primaria(
        grado_numero=grado_numero,
        datos_centro=datos_centro,
        datos_portada=datos_portada,
        estudiantes=estudiantes,
        calificaciones_data=calificaciones_por_area,
        asistencia_data=asistencia_por_mes,
        dias_trabajados=dias_trabajados,
        recuperaciones_data=recuperaciones_por_area,
        condiciones_data=condiciones_finales,
    )
