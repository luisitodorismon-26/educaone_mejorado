"""
registro_primaria.py — Registro Escolar MINERD Nivel Primario (v2.17 · F1)
===========================================================================
Llena los PDFs OFICIALES del MINERD (1ro-6to Primaria) por overlay, con
coordenadas REALES extraídas con pdfplumber (ver MAPA_REGISTRO_PRIMARIA.md).
Nada estimado: el experimento de aterrizaje 1:1 está verificado (Fase 0.2).

F1 (esta versión) rellena:
  1. PORTADA — centro, código, año, grado, sección, tanda, regional, distrito
  2. DATOS DE ESTUDIANTES — No., nombre, sexo, fecha de nacimiento
     (2 páginas del template: filas 1-45 y 46-90)
  3. CALIFICACIONES POR ÁREA — P1-P4 por competencia (C1/C2/C3, valor
     efectivo max(P,RP)) + Promedio del área con LINAJE ESTRICTO
     (solo si las 3 finales de competencia están completas)

F2 (esta versión): ASISTENCIA MENSUAL — 12 formularios (agosto-julio),
números de día en la banda Fecha, códigos P/A/T/E por estudiante×día,
mes y días trabajados. F3 (esta versión): ACTA DE RENDIMIENTO de fin de año — final por área
con linaje estricto, recuperación final/especial, % asistencia del año y
observaciones. F4 (esta versión): ESTADÍSTICAS DE MATRÍCULA (cuadro de edad y sexo).
La recuperación pedagógica queda para llenado manual por diseño: es un
formulario narrativo (estrategias, evidencias) sin filas predefinidas.
Esta versión NO dibuja nada en esas secciones (nada aproximado).

ARQUITECTURA CLAVE — índice dinámico de secciones:
Los 6 templates tienen DISTINTA cantidad de páginas (1ro=142, 6to=114) y las
secciones se corren. Por eso las páginas se localizan POR TEXTO con pypdf
(sin dependencias nuevas) y el índice se cachea por grado.

Carril SEPARADO de secundaria: solo datos de CalificacionPrimaria.
Color tinta azul MINERD. Firma pública compatible con app.py existente.
"""
import io
import json
import os
import unicodedata
from typing import Dict, List, Optional

from reportlab.pdfgen import canvas
from pypdf import PdfReader, PdfWriter

# ─────────────────────────── CALIBRACIÓN (REAL) ───────────────────────────
AZUL_TINTA = (0, 0, 0.7)

# Grid de filas COMPARTIDO por estudiantes/calificaciones (medido):
ROW_Y0 = 165.7        # y_top de la fila 1 (pdfplumber, desde arriba)
ROW_H = 12.88         # espaciado entre filas
FILAS_POR_PAGINA = 45
# Ajuste vertical del texto dentro de la fila. El experimento (Fase 0.2):
# baseline = alto - y_top - 9 dejó el texto 2.3 pts bajo el top de la fila.
# 7.0 lo alinea con los números impresos del template. Calibrable ±2 al ojo.
AJUSTE_FILA = 7.0

# Página de CALIFICACIONES — centros de columna (x0+x1)/2 de los headers:
CAL_COLS = {
    1: (88.5, 153.5, 218.5, 283.5),    # C1 Comunicativa: P1 P2 P3 P4
    2: (348.5, 413.0, 478.0, 542.5),   # C2 Pensamiento Lógico
    3: (700.5, 766.0, 831.0, 896.5),   # C3 Ética y Ciudadana
}
COL_PROMEDIO = 1005.5                  # "Promedio de competencia" (965-1046)

# Página de DATOS DE ESTUDIANTES — columnas (headers medidos):
EST_COL_NO = 46        # centro de la columna No. (entre verticales 36-56)
EST_COL_NOMBRE = 60    # inicio del nombre (hasta ~185)
EST_COL_SEXO = 200     # centro (header 'Sexo' x=191)
EST_COL_FECHA = 265    # inicio fecha nacimiento (header 262-311)
EST_NOMBRE_MAX = 36    # chars a font 6.5 sin invadir Sexo

FONT_NOTA = 7.5
FONT_DATO = 6.5

# ── F4: ESTADÍSTICAS DE MATRÍCULA — cuadro 1 "Cantidad de estudiantes,
# sexo y edad" (medido: verticales 50.1/149.8/227.9/306.0, bandas de 23.75).
# Solo se llena ESTE cuadro: es dato duro (fecha de nacimiento + sexo).
# Los cuadros 2 (sobreedad), 3 (NEAE por categoría) y 4 (nivel educativo de
# los padres) quedan para llenado manual: el sistema no tiene esos datos
# categorizados y NO se inventan criterios en un documento oficial.
EDAD_COL_EDAD = 100.0      # centro de la columna Edad
EDAD_COL_MASC = 188.9
EDAD_COL_FEM = 267.0
EDAD_FILA_Y0 = 126.1       # borde superior de la primera banda
EDAD_FILA_H = 23.75
EDAD_FILAS_MAX = 10        # 10 filas de edad + 1 fila TOTAL
EDAD_AJUSTE = 16.0         # baseline dentro de la banda

# ── F3: ACTA DE RENDIMIENTO DE FIN DE AÑO (calibración MEDIDA por grado) ──
# Las páginas se localizan dinámicamente; estas son las COLUMNAS de cada grado.
# 1ro-2do: 2 columnas por área (Final del área, Recuperación final).
# 3ro-6to: 3 columnas (Final, Recuperación final, Recuperación ESPECIAL) —
# coincide con la cascada de calculo_primaria.py. 4to-6to suman Inglés.
ACTA_ROW_Y0 = 165.0        # y_top de la fila 1 del acta
ACTA_ROW_H = 12.7          # espaciado entre filas
ACTA_FILAS_MAX = 45        # el acta cubre 45 estudiantes
ACTA_COL_NO = 46.0
ACTA_COL_NOMBRE = 104.8
ACTA_NOMBRE_MAX = 30

ACTA_CAL = {
    1: {
        'areas': {
            'lengua espanola': {'cara': 0, 'final': 281.4, 'rec_final': 308.4, 'rec_especial': None},
            'matematica': {'cara': 0, 'final': 343.1, 'rec_final': 370.1, 'rec_especial': None},
            'ciencias sociales': {'cara': 0, 'final': 404.8, 'rec_final': 431.8, 'rec_especial': None},
            'ciencias de la naturaleza': {'cara': 0, 'final': 466.5, 'rec_final': 493.5, 'rec_especial': None},
            'educacion fisica': {'cara': 0, 'final': 528.2, 'rec_final': 555.2, 'rec_especial': None},
            'formacion integral humana y religiosa': {'cara': 1, 'final': 68.0, 'rec_final': 97.1, 'rec_especial': None},
            'educacion artistica': {'cara': 1, 'final': 133.8, 'rec_final': 162.8, 'rec_especial': None},
        },
        'extras': {'cara': 1, 'pct_asistencia': 200.5, 'pct_ausencia': 228.0, 'pct_excusa': 255.6, 'observaciones': 391.7},
    },
    2: {
        'areas': {
            'lengua espanola': {'cara': 0, 'final': 281.4, 'rec_final': 308.4, 'rec_especial': None},
            'matematica': {'cara': 0, 'final': 343.1, 'rec_final': 370.1, 'rec_especial': None},
            'ciencias sociales': {'cara': 0, 'final': 404.8, 'rec_final': 431.8, 'rec_especial': None},
            'ciencias de la naturaleza': {'cara': 0, 'final': 466.5, 'rec_final': 493.5, 'rec_especial': None},
            'educacion fisica': {'cara': 0, 'final': 528.2, 'rec_final': 555.2, 'rec_especial': None},
            'formacion integral humana y religiosa': {'cara': 1, 'final': 68.0, 'rec_final': 97.1, 'rec_especial': None},
            'educacion artistica': {'cara': 1, 'final': 133.8, 'rec_final': 162.8, 'rec_especial': None},
        },
        'extras': {'cara': 1, 'pct_asistencia': 200.5, 'pct_ausencia': 228.0, 'pct_excusa': 255.6, 'observaciones': 391.7},
    },
    3: {
        'areas': {
            'lengua espanola': {'cara': 0, 'final': 277.0, 'rec_final': 293.8, 'rec_especial': 314.3},
            'matematica': {'cara': 0, 'final': 338.7, 'rec_final': 355.5, 'rec_especial': 376.0},
            'ciencias sociales': {'cara': 0, 'final': 400.4, 'rec_final': 417.2, 'rec_especial': 437.6},
            'ciencias de la naturaleza': {'cara': 0, 'final': 462.1, 'rec_final': 478.9, 'rec_especial': 499.3},
            'educacion fisica': {'cara': 0, 'final': 523.7, 'rec_final': 540.6, 'rec_especial': 561.0},
            'formacion integral humana y religiosa': {'cara': 1, 'final': 63.3, 'rec_final': 81.5, 'rec_especial': 103.3},
            'educacion artistica': {'cara': 1, 'final': 129.0, 'rec_final': 147.2, 'rec_especial': 169.0},
        },
        'extras': {'cara': 1, 'pct_asistencia': 198.2, 'pct_ausencia': 219.6, 'pct_excusa': 240.9, 'observaciones': 415.4},
    },
    4: {
        'areas': {
            'lengua espanola': {'cara': 0, 'final': 275.6, 'rec_final': 292.4, 'rec_especial': 312.8},
            'matematica': {'cara': 0, 'final': 337.3, 'rec_final': 354.1, 'rec_especial': 374.5},
            'ciencias sociales': {'cara': 0, 'final': 398.9, 'rec_final': 415.8, 'rec_especial': 436.2},
            'ciencias de la naturaleza': {'cara': 0, 'final': 460.6, 'rec_final': 477.4, 'rec_especial': 497.9},
            'lenguas extranjeras': {'cara': 0, 'final': 522.3, 'rec_final': 539.1, 'rec_especial': 559.6},
            'educacion fisica': {'cara': 1, 'final': 63.7, 'rec_final': 81.9, 'rec_especial': 103.7},
            'formacion integral humana y religiosa': {'cara': 1, 'final': 129.5, 'rec_final': 147.7, 'rec_especial': 169.5},
            'educacion artistica': {'cara': 1, 'final': 195.2, 'rec_final': 213.4, 'rec_especial': 235.2},
        },
        'extras': {'cara': 1, 'pct_asistencia': 264.4, 'pct_ausencia': 285.8, 'pct_excusa': 307.2, 'observaciones': 448.4},
    },
    5: {
        'areas': {
            'lengua espanola': {'cara': 0, 'final': 275.6, 'rec_final': 292.4, 'rec_especial': 312.8},
            'matematica': {'cara': 0, 'final': 337.3, 'rec_final': 354.1, 'rec_especial': 374.5},
            'ciencias sociales': {'cara': 0, 'final': 398.9, 'rec_final': 415.8, 'rec_especial': 436.2},
            'ciencias de la naturaleza': {'cara': 0, 'final': 460.6, 'rec_final': 477.4, 'rec_especial': 497.9},
            'lenguas extranjeras': {'cara': 0, 'final': 522.3, 'rec_final': 539.1, 'rec_especial': 559.6},
            'educacion fisica': {'cara': 1, 'final': 63.7, 'rec_final': 81.9, 'rec_especial': 103.7},
            'formacion integral humana y religiosa': {'cara': 1, 'final': 129.5, 'rec_final': 147.7, 'rec_especial': 169.5},
            'educacion artistica': {'cara': 1, 'final': 195.2, 'rec_final': 213.4, 'rec_especial': 235.2},
        },
        'extras': {'cara': 1, 'pct_asistencia': 264.4, 'pct_ausencia': 285.8, 'pct_excusa': 307.2, 'observaciones': 448.4},
    },
    6: {
        'areas': {
            'lengua espanola': {'cara': 0, 'final': 275.6, 'rec_final': 292.4, 'rec_especial': 312.8},
            'matematica': {'cara': 0, 'final': 337.3, 'rec_final': 354.1, 'rec_especial': 374.5},
            'ciencias sociales': {'cara': 0, 'final': 398.9, 'rec_final': 415.8, 'rec_especial': 436.2},
            'ciencias de la naturaleza': {'cara': 0, 'final': 460.6, 'rec_final': 477.4, 'rec_especial': 497.9},
            'lenguas extranjeras': {'cara': 0, 'final': 522.3, 'rec_final': 539.1, 'rec_especial': 559.6},
            'educacion fisica': {'cara': 1, 'final': 63.7, 'rec_final': 81.9, 'rec_especial': 103.7},
            'formacion integral humana y religiosa': {'cara': 1, 'final': 129.5, 'rec_final': 147.7, 'rec_especial': 169.5},
            'educacion artistica': {'cara': 1, 'final': 195.2, 'rec_final': 213.4, 'rec_especial': 235.2},
        },
        'extras': {'cara': 1, 'pct_asistencia': 264.4, 'pct_ausencia': 285.8, 'pct_excusa': 307.2, 'observaciones': 448.4},
    },
}

# ── F2: Formulario mensual de ASISTENCIA (12 páginas, medido en pág 18) ──
ASIST_DIA_X0 = 110.5      # centro de la 1ra celda de día (rects x0=102, ancho 17.05)
ASIST_DIA_STEP = 17.05
ASIST_DIAS_MAX = 27       # celdas de día disponibles en el formulario
ASIST_FECHA_Y = 154.1     # banda "Fecha" donde se escriben los números de día
ASIST_MES_X = 85          # tras la etiqueta "Mes:____" (x0=57)
ASIST_DIAS_TRAB_X = 352   # tras "Días trabajados:____"
ASIST_INFO_Y = 63.0
ASIST_FILAS_MAX = 45      # un formulario por mes: 45 estudiantes
# Orden del calendario escolar dominicano: agosto → julio
MESES_ESCOLARES = [8, 9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7]

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
def _y_fila(alto_pagina: float, fila: int) -> float:
    """y de ReportLab (desde abajo) para la fila 0-based dentro de su página."""
    return alto_pagina - (ROW_Y0 + fila * ROW_H) - AJUSTE_FILA


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
    """Valor del período: max(P, RP) — la RP nunca baja la nota."""
    pv = comp_data.get(f'p{p}')
    rv = comp_data.get(f'rp{p}')
    if pv is not None and rv is not None:
        return max(float(pv), float(rv))
    if rv is not None:
        return float(rv)
    if pv is not None:
        return float(pv)
    return None


# ─────────────────────────── GENERADOR ───────────────────────────
def generar_registro_primaria(
    grado_numero: int,
    datos_centro: Dict,
    datos_portada: Dict,
    estudiantes: List[Dict],
    calificaciones_data: Optional[Dict] = None,
    asistencia_data=None,
    dias_trabajados=None,
    recuperaciones_data: Optional[Dict] = None,   # F3: {est_idx: {area: {'final':x,'especial':y}}}
    condiciones_data: Optional[Dict] = None,      # F3: {est_idx: 'Promovido(a)'|'Repitente'|...}
) -> bytes:
    """Genera el Registro Escolar Primaria MINERD (F1: portada + estudiantes
    + calificaciones). estudiantes: hasta 90 (45 por página del template)."""
    reader = PdfReader(get_template_path(grado_numero))
    writer = PdfWriter()
    indice = _construir_indice(grado_numero)
    estudiantes = list(estudiantes or [])[:FILAS_POR_PAGINA * 2]

    # ── Portada (coordenadas medidas, conservadas del trabajo previo) ──
    def draw_portada(c, w, h):
        # Coordenadas calibradas contra la plantilla real (pdfplumber). Cada
        # dato va DESPUÉS de su etiqueta y sobre la línea, no encima del texto.
        c.setFont("Helvetica", 10)
        # Centro Educativo: (etiqueta termina en x=181, top=516)
        c.drawString(192, h - 526, str(datos_centro.get('nombre', '') or ''))
        # Código: (etiqueta termina en x=110)
        c.drawString(120, h - 564, str(datos_centro.get('codigo_centro', '') or ''))
        # Año Escolar 20__ - 20__ : la plantilla YA trae "20", solo van 2 dígitos.
        def _dos_digitos(anio):
            s = str(anio or '').strip()
            return s[-2:] if len(s) >= 2 else s
        c.drawString(405, h - 564, _dos_digitos(datos_portada.get('anio_inicio')))
        c.drawString(501, h - 564, _dos_digitos(datos_portada.get('anio_fin')))
        # Grado: / Sección: / Tanda:  (fila top=591)
        c.drawString(110, h - 601, f"{grado_numero}°")
        c.drawString(305, h - 601, str(datos_portada.get('seccion', 'A') or 'A'))
        c.drawString(475, h - 601, str(datos_portada.get('tanda', '') or ''))
        # Regional de Educación: (termina x=221) / Distrito Educativo: (termina x=474)
        c.drawString(228, h - 637, str(datos_centro.get('regional', '') or ''))
        c.drawString(481, h - 637, str(datos_centro.get('distrito', '') or ''))

    # ── Datos del Centro Educativo (coordenadas medidas pág 7) ──
    # Solo se llena lo que el sistema TIENE guardado. Paraje, municipio,
    # provincia, zona y sector quedan en blanco para llenado manual (no están
    # en el modelo y no se inventan en un documento oficial).
    def draw_centro(c, w, h):
        c.setFont("Helvetica", 9.5)
        email = str(datos_centro.get('email', '') or '')
        tel = str(datos_centro.get('telefono', '') or '')
        direccion = str(datos_centro.get('direccion', '') or '')
        regional = str(datos_centro.get('regional', '') or '')
        distrito = str(datos_centro.get('distrito', '') or '')
        director = str(datos_centro.get('director', '') or '')
        if email:
            c.drawString(150, h - 122, email)       # Correo (x1=143.6, top=112)
        if tel:
            c.drawString(446, h - 122, tel)          # Teléfono (x1=439.7)
        if direccion:
            c.drawString(104, h - 141, direccion[:60])  # Dirección (x1=97.2, top=130.7)
        if regional:
            c.drawString(100, h - 277, regional)     # Regional (x1=93.8, top=266.6)
        if distrito:
            c.drawString(367, h - 277, distrito)     # Distrito (x1=360.7)
        if director:
            c.drawString(219, h - 342, director[:55])   # Director(a) (x1=212, top=331.7)
        # ── Datos del maestro o la maestra (misma página, parte inferior) ──
        # Solo el nombre: fecha de ingreso, cédula, estado civil, título, etc.
        # son datos personales que el sistema no guarda → llenado manual.
        titular = str(datos_centro.get('docente_titular', '') or '')
        if titular:
            c.drawString(176, h - 507, titular[:50])   # Nombre(s) y apellido(s): (x1=169.6, top=497.1)

    # ── Datos de estudiantes (página_slot: 0 = filas 1-45, 1 = 46-90) ──
    def draw_estudiantes(pagina_slot):
        def draw(c, w, h):
            c.setFont("Helvetica", FONT_DATO)
            ini = pagina_slot * FILAS_POR_PAGINA
            for local, est in enumerate(estudiantes[ini:ini + FILAS_POR_PAGINA]):
                y = _y_fila(h, local)
                c.drawCentredString(EST_COL_NO, y, str(est.get('no_lista', ini + local + 1)))
                nombre = str(est.get('nombre', '') or '')[:EST_NOMBRE_MAX]
                c.drawString(EST_COL_NOMBRE, y, nombre)
                sexo = str(est.get('sexo', '') or '')[:1].upper()
                if sexo:
                    c.drawCentredString(EST_COL_SEXO, y, sexo)
                fn = est.get('fecha_nacimiento')
                if fn:
                    try:
                        fecha = fn.strftime('%d/%m/%Y')
                    except AttributeError:
                        fecha = str(fn)[:10]
                    c.drawString(EST_COL_FECHA, y, fecha)
        return draw

    # ── Calificaciones de un área (pagina_slot igual que arriba) ──
    def draw_calificaciones(area_data: Dict, pagina_slot: int):
        def draw(c, w, h):
            ini = pagina_slot * FILAS_POR_PAGINA
            for est_idx in range(ini, min(ini + FILAS_POR_PAGINA, len(estudiantes))):
                comps = area_data.get(est_idx) or area_data.get(str(est_idx)) or {}
                if not comps:
                    continue
                fila = est_idx - ini
                y = _y_fila(h, fila)
                c.setFont("Helvetica", FONT_NOTA)
                finales = []
                for comp_num in (1, 2, 3):
                    cd = comps.get(comp_num) or comps.get(str(comp_num)) or {}
                    cols = CAL_COLS[comp_num]
                    for p in (1, 2, 3, 4):
                        val = _valor_efectivo(cd, p)
                        if val is not None:
                            c.drawCentredString(cols[p - 1], y, _fmt_nota(val))
                    finales.append(cd.get('final_competencia'))
                # Promedio del área — LINAJE ESTRICTO: solo con las 3 finales
                if len(finales) == 3 and all(f is not None for f in finales):
                    prom = round(sum(float(f) for f in finales) / 3)
                    c.setFont("Helvetica-Bold", FONT_NOTA)
                    c.drawCentredString(COL_PROMEDIO, y, str(int(prom)))
        return draw

    overlays_por_pagina: Dict[int, list] = {}

    def agendar(pg_idx, fn):
        if pg_idx is not None and 0 <= pg_idx < len(reader.pages):
            overlays_por_pagina.setdefault(pg_idx, []).append(fn)

    # ── F2: Asistencia mensual (un formulario del template por mes) ──
    def draw_asistencia_mes(mes_data: Dict):
        def draw(c, w, h):
            # Cabecera: mes y días trabajados configurados
            c.setFont("Helvetica-Bold", 9)
            c.drawString(ASIST_MES_X, h - ASIST_INFO_Y - 7.5,
                         str(mes_data.get('mes', '') or '').upper())
            dt = mes_data.get('dias_trabajados_configurados')
            if dt:
                c.drawString(ASIST_DIAS_TRAB_X, h - ASIST_INFO_Y - 7.5, str(dt))
            # Números de día en la banda "Fecha" (máximo 27 celdas del template)
            dias = list(mes_data.get('dias') or [])[:ASIST_DIAS_MAX]
            c.setFont("Helvetica", 6.5)
            for j, dia in enumerate(dias):
                c.drawCentredString(ASIST_DIA_X0 + j * ASIST_DIA_STEP,
                                    h - ASIST_FECHA_Y - 7, str(dia))
            # Códigos P/A/T/E por estudiante × día (grid de filas compartido)
            for fila_idx, fila in enumerate((mes_data.get('filas') or [])[:ASIST_FILAS_MAX]):
                y = _y_fila(h, fila_idx)
                valores = fila.get('valores') or []
                for j in range(min(len(valores), len(dias))):
                    cod = (valores[j] or '').strip()
                    if cod:
                        c.setFont("Helvetica", 6.5)
                        c.drawCentredString(ASIST_DIA_X0 + j * ASIST_DIA_STEP, y, cod)
        return draw

    # Cada mes del resultado va a SU formulario según el calendario escolar
    # (formulario 0 = agosto … 11 = julio), no por orden de aparición.
    paginas_asist = indice.get('asistencia') or []
    for mes_data in (asistencia_data or []):
        mes_num = mes_data.get('mes_num')
        if mes_num in MESES_ESCOLARES:
            slot = MESES_ESCOLARES.index(mes_num)
            if slot < len(paginas_asist):
                agendar(paginas_asist[slot], draw_asistencia_mes(mes_data))

    # ── F4: Estadísticas de matrícula — cuadro de edad y sexo ──
    def draw_estadisticas(c, w, h):
        from datetime import date as _date
        try:
            anio_corte = int(str(datos_portada.get('anio_inicio') or '').strip())
        except (TypeError, ValueError):
            anio_corte = _date.today().year
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
        # Fila TOTAL (la banda 11 del cuadro)
        y_tot = h - (EDAD_FILA_Y0 + EDAD_FILAS_MAX * EDAD_FILA_H) - EDAD_AJUSTE
        c.setFont("Helvetica-Bold", 8.5)
        c.drawCentredString(EDAD_COL_MASC, y_tot, str(tot_m))
        c.drawCentredString(EDAD_COL_FEM, y_tot, str(tot_f))

    agendar(indice.get('estadisticas'), draw_estadisticas)

    # ── F3: ACTA DE RENDIMIENTO DE FIN DE AÑO ──
    def _final_area_de(est_idx: int, area_canon: str):
        """Final del área = promedio de las 3 finales de competencia.
        LINAJE ESTRICTO: None si alguna competencia está incompleta."""
        for nombre_asig, area_data in (calificaciones_data or {}).items():
            if area_canonica(nombre_asig) != area_canon:
                continue
            comps = area_data.get(est_idx) or area_data.get(str(est_idx)) or {}
            finales = []
            for cn in (1, 2, 3):
                cd = comps.get(cn) or comps.get(str(cn)) or {}
                finales.append(cd.get('final_competencia'))
            if len(finales) == 3 and all(f is not None for f in finales):
                return round(sum(float(f) for f in finales) / 3)
            return None
        return None

    def _pct_asistencia_anual(est_idx: int):
        """% de asistencia/ausencia/excusa del año, sumando todos los meses."""
        pres = aus = exc = tot = 0
        for mes in (asistencia_data or []):
            filas = mes.get('filas') or []
            if est_idx >= len(filas):
                continue
            for cod in (filas[est_idx].get('valores') or []):
                c = (cod or '').strip().upper()
                if not c:
                    continue
                tot += 1
                if c in ('P', 'T'):
                    pres += 1
                elif c == 'E':
                    exc += 1
                elif c == 'A':
                    aus += 1
        if not tot:
            return None, None, None
        r = lambda n: int(round(n * 100.0 / tot))
        return r(pres), r(aus), r(exc)

    def draw_acta(cara: int, cal_grado: Dict):
        def draw(c, w, h):
            for est_idx, est in enumerate(estudiantes[:ACTA_FILAS_MAX]):
                y = h - (ACTA_ROW_Y0 + est_idx * ACTA_ROW_H) - AJUSTE_FILA
                c.setFont("Helvetica", FONT_DATO)
                # Nº y nombre solo en la cara izquierda
                if cara == 0:
                    c.drawCentredString(ACTA_COL_NO, y, str(est.get('no_lista', est_idx + 1)))
                    nombre = str(est.get('nombre', '') or '')[:ACTA_NOMBRE_MAX]
                    c.drawString(ACTA_COL_NOMBRE, y, nombre)
                # Notas por área (cada área sabe en qué cara vive)
                c.setFont("Helvetica", FONT_NOTA)
                for area_canon, cols in cal_grado['areas'].items():
                    if cols['cara'] != cara:
                        continue
                    val = _final_area_de(est_idx, area_canon)
                    if val is not None:
                        c.drawCentredString(cols['final'] + 5, y, str(int(val)))
                    rec = ((recuperaciones_data or {}).get(est_idx)
                           or (recuperaciones_data or {}).get(str(est_idx)) or {}).get(area_canon) or {}
                    if rec.get('final') is not None and cols.get('rec_final'):
                        c.drawCentredString(cols['rec_final'] + 5, y, _fmt_nota(rec['final']))
                    if rec.get('especial') is not None and cols.get('rec_especial'):
                        c.drawCentredString(cols['rec_especial'] + 5, y, _fmt_nota(rec['especial']))
                # Extras (% asistencia y observaciones) en la cara derecha
                if cara == cal_grado['extras']['cara']:
                    ex = cal_grado['extras']
                    pa, pau, pe = _pct_asistencia_anual(est_idx)
                    if pa is not None:
                        c.drawCentredString(ex['pct_asistencia'] + 5, y, str(pa))
                        c.drawCentredString(ex['pct_ausencia'] + 5, y, str(pau))
                        c.drawCentredString(ex['pct_excusa'] + 5, y, str(pe))
                    cond = ((condiciones_data or {}).get(est_idx)
                            or (condiciones_data or {}).get(str(est_idx)))
                    if cond:
                        c.setFont("Helvetica", FONT_DATO)
                        c.drawString(ex['observaciones'], y, str(cond)[:26])
        return draw

    _cal_acta = ACTA_CAL.get(grado_numero)
    _pags_acta = indice.get('acta') or []
    if _cal_acta and len(_pags_acta) >= 2:
        for cara in (0, 1):
            agendar(_pags_acta[cara], draw_acta(cara, _cal_acta))

    # ── Mapear calificaciones del colegio → páginas del template por área ──
    agendar(indice['portada'], draw_portada)
    agendar(indice.get('centro'), draw_centro)
    for slot, pg in enumerate(indice['estudiantes'][:2]):
        agendar(pg, draw_estudiantes(slot))

    necesita_slot_2 = len(estudiantes) > FILAS_POR_PAGINA
    for nombre_asig, area_data in (calificaciones_data or {}).items():
        canon = area_canonica(nombre_asig)
        if not canon:
            continue  # asignatura sin área oficial (no se pinta nada aproximado)
        paginas = indice['calificaciones'].get(canon) or []
        if paginas:
            agendar(paginas[0], draw_calificaciones(area_data, 0))
            if necesita_slot_2 and len(paginas) > 1:
                agendar(paginas[1], draw_calificaciones(area_data, 1))

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
    """Wrapper con la MISMA firma que consume app.py (sin cambios allá)."""
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
