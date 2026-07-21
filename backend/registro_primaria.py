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
mes y días trabajados. F3 pendiente: recuperación pedagógica, actas,
estadísticas de matrícula.
Esta versión NO dibuja nada en esas secciones (nada aproximado).

ARQUITECTURA CLAVE — índice dinámico de secciones:
Los 6 templates tienen DISTINTA cantidad de páginas (1ro=142, 6to=114) y las
secciones se corren. Por eso las páginas se localizan POR TEXTO con pypdf
(sin dependencias nuevas) y el índice se cachea por grado.

Carril SEPARADO de secundaria: solo datos de CalificacionPrimaria.
Color tinta azul MINERD. Firma pública compatible con app.py existente.
"""
import io
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


def _construir_indice(grado_numero: int) -> Dict:
    """Escanea el template UNA vez con pypdf y localiza secciones por texto.

    Devuelve: {'portada': int, 'estudiantes': [pág 1-45, pág 46-90],
               'calificaciones': {area_canon: [pág 1-45, pág 46-90]}}
    Cacheado por grado (el proceso completo toma ~1-2 s y solo la 1ra vez).
    """
    if grado_numero in _INDICE_CACHE:
        return _INDICE_CACHE[grado_numero]

    reader = PdfReader(get_template_path(grado_numero))
    indice = {'portada': None, 'estudiantes': [], 'asistencia': [], 'calificaciones': {}}

    for i, page in enumerate(reader.pages):
        try:
            txt = page.extract_text() or ''
        except Exception:
            txt = ''
        plano = _sin_acentos(txt)

        if indice['portada'] is None and 'registro' in plano and 'nivel primario' in plano \
                and 'centro educativo' in plano:
            indice['portada'] = i
            continue

        # 'orden alfabetico' distingue las páginas REALES de la tabla de
        # estudiantes (10-11) de la página del ÍNDICE, que solo lista el título.
        if 'orden alfabetico' in plano and len(indice['estudiantes']) < 2:
            indice['estudiantes'].append(i)
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
    asistencia_data=None,       # F2 — se recibe pero aún no se dibuja
    dias_trabajados=None,       # F2
) -> bytes:
    """Genera el Registro Escolar Primaria MINERD (F1: portada + estudiantes
    + calificaciones). estudiantes: hasta 90 (45 por página del template)."""
    reader = PdfReader(get_template_path(grado_numero))
    writer = PdfWriter()
    indice = _construir_indice(grado_numero)
    estudiantes = list(estudiantes or [])[:FILAS_POR_PAGINA * 2]

    # ── Portada (coordenadas medidas, conservadas del trabajo previo) ──
    def draw_portada(c, w, h):
        c.setFont("Helvetica", 10)
        c.drawString(165, h - 530, str(datos_centro.get('nombre', '') or ''))
        c.drawString(115, h - 564, str(datos_centro.get('codigo_centro', '') or ''))
        c.drawString(415, h - 564, str(datos_portada.get('anio_inicio', '') or ''))
        c.drawString(510, h - 564, str(datos_portada.get('anio_fin', '') or ''))
        c.drawString(110, h - 600, f"{grado_numero}°")
        c.drawString(305, h - 600, str(datos_portada.get('seccion', 'A') or 'A'))
        c.drawString(475, h - 600, str(datos_portada.get('tanda', '') or ''))
        c.drawString(232, h - 637, str(datos_centro.get('regional', '') or ''))
        c.drawString(481, h - 637, str(datos_centro.get('distrito', '') or ''))

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

    # ── Mapear calificaciones del colegio → páginas del template por área ──
    agendar(indice['portada'], draw_portada)
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
    }
    return generar_registro_primaria(
        grado_numero=grado_numero,
        datos_centro=datos_centro,
        datos_portada=datos_portada,
        estudiantes=estudiantes,
        calificaciones_data=calificaciones_por_area,
        asistencia_data=asistencia_por_mes,
        dias_trabajados=dias_trabajados,
    )
