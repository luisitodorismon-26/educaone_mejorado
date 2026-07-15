"""
════════════════════════════════════════════════════════════════════════
BOLETÍN DE PRIMARIA — "INFORME DE APRENDIZAJE" (v2.13.46)
════════════════════════════════════════════════════════════════════════

Carril SEPARADO de secundaria. No importa nada de boletin_minerd_secundaria.

Técnica: overlay sobre la plantilla oficial del MINERD (igual que secundaria).
Las coordenadas fueron EXTRAÍDAS del propio PDF oficial con pdfplumber, no
estimadas: filas de áreas cada 27pt, 27 columnas de notas, columnas finales.

Estructura oficial (Informe de Aprendizaje, Nivel Primario):
  - 3 competencias fundamentales (C1 Comunicativa, C2 Pensamiento Lógico,
    C3 Ética y Ciudadana), cada una con P1-P4 y RP1-RP4.
  - Columnas finales: Calificación final por competencia (C1/C2/C3),
    Calificación final del área, Recuperación final, Recuperación especial.
  - Aprueba con 65.

Variantes por grado:
  - 1ro y 2do: SIN columnas RP, sin recuperación especial, 7 áreas.
  - 3ro:       CON RP, 7 áreas (sin Inglés).
  - 4to-6to:   CON RP, 8 áreas (con Inglés).
"""

import io
import os
import base64
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from pypdf import PdfReader, PdfWriter

# ─── Dimensiones de la plantilla oficial (apaisada) ───
PAGE_W = 834.0
PAGE_H = 654.0

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), 'templates', 'boletin_primaria')


def _y(y_top: float) -> float:
    """Convierte coordenada 'desde arriba' (pdfplumber) a ReportLab (desde abajo)."""
    return PAGE_H - y_top


# v2.13.47: las líneas de escritura (guiones bajos) miden 10pt de alto y la
# línea visible está cerca del BORDE INFERIOR, no del superior. Para que el
# texto quede escrito SOBRE la línea (y no flotando encima) hay que bajar
# la baseline ~8pt respecto del `top` que devuelve pdfplumber.
BASELINE_OFFSET = 8.0


def _y_linea(y_top: float) -> float:
    """Baseline para escribir SOBRE una línea de la plantilla."""
    return PAGE_H - (y_top + BASELINE_OFFSET) + 1.5


# ════════════════════════════════════════════════════════════════════
# CALIBRACIÓN — extraída del PDF oficial (4to/5to/6to comparten valores)
# ════════════════════════════════════════════════════════════════════

# Columnas de notas: 3 competencias × (P1,RP1,P2,RP2,P3,RP3,P4,RP4)
COMP_X = {
    1: {'p1': 187.7, 'rp1': 207.4, 'p2': 227.3, 'rp2': 247.1,
        'p3': 267.0, 'rp3': 286.9, 'p4': 306.8, 'rp4': 326.5},
    2: {'p1': 346.7, 'rp1': 366.4, 'p2': 386.3, 'rp2': 406.2,
        'p3': 426.1, 'rp3': 446.0, 'p4': 465.8, 'rp4': 485.5},
    3: {'p1': 505.8, 'rp1': 525.5, 'p2': 545.4, 'rp2': 565.3,
        'p3': 585.2, 'rp3': 605.1, 'p4': 625.0, 'rp4': 644.7},
}

# Calificación final por competencia
CF_COMP_X = {1: 666.7, 2: 689.9, 3: 713.1}

# Columnas finales del área
CF_AREA_X = 736.7      # Calificación final del área
REC_FINAL_X = 760.1    # Calificación recuperación final
REC_ESPECIAL_X = 783.5 # Calificación recuperación especial

# ─── 1ro y 2do (SIN RP): columnas más anchas, posiciones distintas ───
# Extraídas de la plantilla oficial: 3 competencias × 4 períodos (sin RP),
# columnas finales sin "recuperación especial".
COMP_X_SIN_RP = {
    1: {'p1': 211.9, 'p2': 249.1, 'p3': 286.4, 'p4': 323.5},
    2: {'p1': 361.2, 'p2': 398.3, 'p3': 435.7, 'p4': 472.8},
    3: {'p1': 510.5, 'p2': 547.6, 'p3': 584.9, 'p4': 622.1},
}
CF_COMP_X_SIN_RP = {1: 656.5, 2: 686.9, 3: 717.4}
CF_AREA_X_SIN_RP = 748.4
REC_FINAL_X_SIN_RP = 779.0
# (1ro y 2do no tienen columna de recuperación especial)

# Filas de áreas (centro vertical de cada fila; 8 filas × 27pt)
FILA_ALTO = 27.0
FILAS_Y = {
    'Lengua Española':                       136.9,
    'Matemática':                            163.9,
    'Ciencias Sociales':                     190.9,
    'Ciencias de la Naturaleza':             217.9,
    'Lenguas Extranjeras (inglés)':          244.9,
    'Educación Física':                      271.9,
    'Formación Integral Humana y Religiosa': 298.9,
    'Educación Artística':                   325.9,
}

# Grados de 1ro-3ro: no tienen Inglés → las áreas suben una fila
FILAS_Y_SIN_INGLES = {
    'Lengua Española':                       136.9,
    'Matemática':                            163.9,
    'Ciencias Sociales':                     190.9,
    'Ciencias de la Naturaleza':             217.9,
    'Educación Física':                      244.9,
    'Formación Integral Humana y Religiosa': 271.9,
    'Educación Artística':                   298.9,
}

# ─── Portada: coordenadas de cada campo (x = inicio de la línea) ───
PORTADA = {
    'ano_desde':   (593.9, 321.5),
    'ano_hasta':   (664.0, 321.5),
    'seccion':     (491.8, 347.5),
    'no_orden':    (685.8, 347.5),
    'nombres':     (505.8, 367.5),
    'apellidos':   (507.0, 387.5),
    'id_sigerd':   (655.9, 407.5),
    'docente':     (496.0, 427.5),
    'centro':      (542.7, 447.5),
    'codigo':      (548.2, 467.5),
    'tanda':       (484.1, 487.5),
    'telefono':    (554.2, 507.5),
    'distrito':    (548.7, 527.5),
    'regional':    (570.7, 547.5),
    'provincia':   (507.9, 567.5),
    'municipio':   (506.9, 587.5),
}

# Zona del escudo MINERD en la portada (se tapa con el logo del colegio)
ESCUDO_X0, ESCUDO_X1 = 500.0, 742.0
ESCUDO_Y0, ESCUDO_Y1 = 25.0, 148.0   # y_top
LOGO_MAX_W, LOGO_MAX_H = 115.0, 105.0

# ─── Situación del estudiante (portada) — centros reales de cada celda ───
SITUACION_X = {'promovido': 113.0, 'aplazado': 228.3, 'repitente': 343.7}
SITUACION_Y = 259.0   # centro de la celda de marca (entre 245.9 y 272.3)

# Condición final (portada): 2 líneas de escritura
CONDICION_X = 62.0
CONDICION_Y = [308.8, 324.8]

# Observaciones (portada): 12 líneas cada 15pt
OBSERVACIONES_X = 62.0
OBSERVACIONES_Y0 = 375.7
OBSERVACIONES_INTERLINEA = 15.0
OBSERVACIONES_MAX_LINEAS = 12

# ─── Resumen de asistencia (página 2) ───
ASISTENCIA_Y = {1: 544.0, 2: 563.3, 3: 582.7, 4: 602.1}
ASISTENCIA_X = {'asistencia': 113.9, 'ausencia': 163.4,
                'pct_asistencia': 213.4, 'pct_ausencia': 262.6}


def _envolver(texto: str, ancho: int) -> list:
    """Parte un texto en líneas de como máximo `ancho` caracteres."""
    palabras, lineas, actual = texto.split(), [], ''
    for palabra in palabras:
        if len(actual) + len(palabra) + 1 <= ancho:
            actual = f"{actual} {palabra}".strip()
        else:
            if actual:
                lineas.append(actual)
            actual = palabra
    if actual:
        lineas.append(actual)
    return lineas


def _fmt(v, decimales=0):
    """Formatea una nota para imprimir (vacío si None)."""
    if v is None:
        return ''
    try:
        if decimales == 0:
            return str(int(round(float(v))))
        return f"{float(v):.{decimales}f}".rstrip('0').rstrip('.')
    except (TypeError, ValueError):
        return ''


def _get_plantilla_path(grado_nombre: str) -> str:
    """Devuelve la ruta de la plantilla oficial según el grado."""
    g = (grado_nombre or '').lower()
    if '1' in g or 'primer' in g or 'uno' in g:
        archivo = 'IDA-1ro-grado.pdf'
    elif '2' in g or 'segundo' in g:
        archivo = 'IDA-2do-grado.pdf'
    elif '3' in g or 'tercer' in g:
        archivo = 'IDA-3ro-grado.pdf'
    elif '4' in g or 'cuarto' in g:
        archivo = 'IDA-4to-grado.pdf'
    elif '6' in g or 'sexto' in g:
        archivo = 'IDA-6to-grado.pdf'
    else:
        archivo = 'IDA-5to-grado.pdf'  # default: 5to
    return os.path.join(TEMPLATES_DIR, archivo)


def _grado_tiene_rp(grado_nombre: str) -> bool:
    """1ro y 2do no tienen columnas RP en el boletín oficial."""
    g = (grado_nombre or '').lower()
    return not ('1' in g or 'primer' in g or '2' in g or 'segundo' in g)


def _grado_tiene_ingles(grado_nombre: str) -> bool:
    """Solo 4to, 5to y 6to tienen Lenguas Extranjeras (inglés)."""
    g = (grado_nombre or '').lower()
    return any(k in g for k in ('4', 'cuarto', '5', 'quinto', '6', 'sexto'))


def _normalizar_area(nombre: str) -> str:
    """Mapea el nombre de la asignatura del colegio a la fila oficial."""
    n = (nombre or '').lower().strip()
    mapeo = {
        'lengua española': 'Lengua Española',
        'lengua espanola': 'Lengua Española',
        'español': 'Lengua Española',
        'matemática': 'Matemática',
        'matematica': 'Matemática',
        'matemáticas': 'Matemática',
        'ciencias sociales': 'Ciencias Sociales',
        'sociales': 'Ciencias Sociales',
        'ciencias de la naturaleza': 'Ciencias de la Naturaleza',
        'ciencias naturales': 'Ciencias de la Naturaleza',
        'naturales': 'Ciencias de la Naturaleza',
        'lenguas extranjeras (inglés)': 'Lenguas Extranjeras (inglés)',
        'lenguas extranjeras (ingles)': 'Lenguas Extranjeras (inglés)',
        'inglés': 'Lenguas Extranjeras (inglés)',
        'ingles': 'Lenguas Extranjeras (inglés)',
        'educación física': 'Educación Física',
        'educacion fisica': 'Educación Física',
        'física': 'Educación Física',
        'formación integral humana y religiosa': 'Formación Integral Humana y Religiosa',
        'formacion integral humana y religiosa': 'Formación Integral Humana y Religiosa',
        'formación integral': 'Formación Integral Humana y Religiosa',
        'religión': 'Formación Integral Humana y Religiosa',
        'educación artística': 'Educación Artística',
        'educacion artistica': 'Educación Artística',
        'artística': 'Educación Artística',
    }
    return mapeo.get(n, nombre)


def _dibujar_logo_colegio(c: canvas.Canvas, config) -> bool:
    """Tapa el escudo del MINERD y dibuja el logo del colegio (privado)."""
    logo_raw = getattr(config, 'logo', None) if config else None
    if not logo_raw:
        return False
    try:
        if ',' in str(logo_raw):
            logo_raw = str(logo_raw).split(',', 1)[1]
        logo_bytes = base64.b64decode(logo_raw)
        img = ImageReader(io.BytesIO(logo_bytes))
    except Exception:
        return False

    # Tapar el escudo y los textos del ministerio
    c.setFillColorRGB(1, 1, 1)
    c.rect(ESCUDO_X0, _y(ESCUDO_Y1), ESCUDO_X1 - ESCUDO_X0, ESCUDO_Y1 - ESCUDO_Y0,
           fill=1, stroke=0)
    c.setFillColorRGB(0, 0, 0)

    # Dibujar el logo centrado, respetando su proporción
    try:
        iw, ih = img.getSize()
        escala = min(LOGO_MAX_W / iw, LOGO_MAX_H / ih)
        w, h = iw * escala, ih * escala
        cx = (ESCUDO_X0 + ESCUDO_X1) / 2
        cy_top = (ESCUDO_Y0 + ESCUDO_Y1) / 2
        c.drawImage(img, cx - w / 2, _y(cy_top) - h / 2, width=w, height=h, mask='auto')
        return True
    except Exception:
        return False


def _dibujar_portada(c: canvas.Canvas, estudiante, curso, config, ano_escolar,
                     docente_nombre='', situacion_final=None, condicion_final='',
                     observaciones=''):
    """Página 1: logo, datos del estudiante y del centro, situación."""
    _dibujar_logo_colegio(c, config)
    c.setFont("Helvetica", 9)
    c.setFillColorRGB(0, 0, 0)

    def escribir(campo, texto, size=9):
        if not texto:
            return
        x, y_top = PORTADA[campo]
        c.setFont("Helvetica", size)
        c.drawString(x + 2, _y_linea(y_top), str(texto)[:60])

    # Año escolar: la plantilla ya trae "20__ 20__"
    nombre_ano = getattr(ano_escolar, 'nombre', '') or ''
    partes = nombre_ano.replace('/', '-').split('-')
    if len(partes) == 2:
        escribir('ano_desde', partes[0].strip()[-2:])
        escribir('ano_hasta', partes[1].strip()[-2:])

    # Datos del estudiante
    escribir('seccion', getattr(curso, 'nombre', '') or '')
    escribir('no_orden', getattr(estudiante, 'no_lista', '') or '')
    escribir('nombres', getattr(estudiante, 'nombre', '') or '')
    escribir('apellidos', getattr(estudiante, 'apellido', '') or '')
    escribir('id_sigerd', getattr(estudiante, 'matricula', '') or '', size=8)
    escribir('docente', docente_nombre)

    # Datos del centro
    if config:
        escribir('centro', getattr(config, 'nombre', '') or '')
        escribir('codigo', getattr(config, 'codigo_centro', '') or '')
        escribir('telefono', getattr(config, 'telefono', '') or '')
        escribir('distrito', getattr(config, 'distrito_educativo', '') or '')
        escribir('regional', getattr(config, 'regional', '') or '')
        escribir('provincia', getattr(config, 'provincia', '') or '')
        escribir('municipio', getattr(config, 'municipio', '') or '')
    # `tanda` puede ser una relación (objeto Tanda) o un string
    tanda_val = getattr(curso, 'tanda', None)
    if tanda_val is not None and not isinstance(tanda_val, str):
        tanda_val = getattr(tanda_val, 'nombre', '') or ''
    escribir('tanda', tanda_val or '')

    # Situación del estudiante (X en la celda correspondiente)
    if situacion_final:
        cond = str(situacion_final).lower()
        if 'promovido' in cond:
            marca = 'promovido'
        elif 'repite' in cond or 'repitente' in cond:
            marca = 'repitente'
        elif 'aplazado' in cond or 'condicional' in cond:
            marca = 'aplazado'
        else:
            marca = None
        if marca:
            c.setFont("Helvetica-Bold", 14)
            c.drawCentredString(SITUACION_X[marca], _y(SITUACION_Y), 'X')

    # Condición final (2 líneas disponibles)
    if condicion_final:
        c.setFont("Helvetica", 8)
        for i, linea in enumerate(_envolver(str(condicion_final), 80)[:2]):
            c.drawString(CONDICION_X, _y_linea(CONDICION_Y[i]), linea)

    # Observaciones (12 líneas disponibles)
    if observaciones:
        c.setFont("Helvetica", 8)
        for i, linea in enumerate(_envolver(str(observaciones), 80)[:OBSERVACIONES_MAX_LINEAS]):
            y_obs = OBSERVACIONES_Y0 + i * OBSERVACIONES_INTERLINEA
            c.drawString(OBSERVACIONES_X, _y_linea(y_obs), linea)


def _dibujar_tabla(c: canvas.Canvas, areas_data, grado_nombre, asistencias_por_periodo=None):
    """Página 2: notas de cada área en sus casillas oficiales.

    areas_data: dict {nombre_area: {
        'competencias': {1: obj, 2: obj, 3: obj},   # CalificacionPrimaria
        'cf_area': int|None,
        'recuperacion_final': int|None,
        'recuperacion_especial': int|None,
    }}
    """
    tiene_rp = _grado_tiene_rp(grado_nombre)
    filas = FILAS_Y if _grado_tiene_ingles(grado_nombre) else FILAS_Y_SIN_INGLES

    # v2.13.52: 1ro y 2do (sin RP) tienen columnas más anchas y en otras
    # posiciones. Se elige el juego de coordenadas correcto según el grado.
    if tiene_rp:
        comp_x, cf_comp_x = COMP_X, CF_COMP_X
        cf_area_x, rec_final_x, rec_especial_x = CF_AREA_X, REC_FINAL_X, REC_ESPECIAL_X
    else:
        comp_x, cf_comp_x = COMP_X_SIN_RP, CF_COMP_X_SIN_RP
        cf_area_x, rec_final_x, rec_especial_x = CF_AREA_X_SIN_RP, REC_FINAL_X_SIN_RP, None

    c.setFont("Helvetica", 7.5)
    c.setFillColorRGB(0, 0, 0)

    for nombre_area, data in (areas_data or {}).items():
        area = _normalizar_area(nombre_area)
        if area not in filas:
            continue  # área no oficial: no tiene fila en la plantilla
        y_row = _y(filas[area])

        comps = data.get('competencias') or {}
        for num in (1, 2, 3):
            comp = comps.get(num)
            if comp is None:
                continue
            cols = comp_x[num]
            for per in (1, 2, 3, 4):
                # Período
                p_val = getattr(comp, f'p{per}', None)
                if p_val is not None:
                    c.drawCentredString(cols[f'p{per}'], y_row, _fmt(p_val))
                # Recuperación pedagógica (solo grados que la tienen)
                if tiene_rp:
                    rp_val = getattr(comp, f'rp{per}', None)
                    if rp_val is not None:
                        c.drawCentredString(cols[f'rp{per}'], y_row, _fmt(rp_val))

            # Calificación final por competencia (C1/C2/C3)
            final_comp = getattr(comp, 'final_competencia', None)
            if final_comp is None and hasattr(comp, 'calcular_final'):
                try:
                    final_comp = comp.calcular_final()
                except Exception:
                    final_comp = None
            if final_comp is not None:
                c.setFont("Helvetica-Bold", 7.5)
                c.drawCentredString(cf_comp_x[num], y_row, _fmt(final_comp))
                c.setFont("Helvetica", 7.5)

        # Calificación final del área
        cf_area = data.get('cf_area')
        if cf_area is not None:
            c.setFont("Helvetica-Bold", 8)
            c.drawCentredString(cf_area_x, y_row, _fmt(cf_area))
            c.setFont("Helvetica", 7.5)

        # Recuperación final
        rec_f = data.get('recuperacion_final')
        if rec_f is not None:
            c.drawCentredString(rec_final_x, y_row, _fmt(rec_f))

        # Recuperación especial (no existe en 1ro/2do)
        rec_e = data.get('recuperacion_especial')
        if rec_e is not None and rec_especial_x is not None:
            c.drawCentredString(rec_especial_x, y_row, _fmt(rec_e))

    # Resumen de asistencia por período
    if asistencias_por_periodo:
        c.setFont("Helvetica", 8)
        for per, datos in asistencias_por_periodo.items():
            if per not in ASISTENCIA_Y:
                continue
            y_a = _y(ASISTENCIA_Y[per])
            presentes = (datos or {}).get('presentes')
            ausentes = (datos or {}).get('ausentes')
            if presentes is not None:
                c.drawCentredString(ASISTENCIA_X['asistencia'], y_a, str(presentes))
            if ausentes is not None:
                c.drawCentredString(ASISTENCIA_X['ausencia'], y_a, str(ausentes))
            # % anual de asistencia / ausencia
            if presentes is not None and ausentes is not None:
                total = presentes + ausentes
                if total > 0:
                    c.drawCentredString(ASISTENCIA_X['pct_asistencia'], y_a,
                                        f"{round(presentes / total * 100)}%")
                    c.drawCentredString(ASISTENCIA_X['pct_ausencia'], y_a,
                                        f"{round(ausentes / total * 100)}%")


def generar_boletin_primaria(estudiante, curso, grado_nombre, areas_data, config,
                             ano_escolar, docente_nombre='', situacion_final=None,
                             condicion_final='', observaciones='',
                             asistencias_por_periodo=None) -> io.BytesIO:
    """Genera el Informe de Aprendizaje (primaria) como io.BytesIO.

    Compone un overlay con los datos sobre la plantilla oficial del MINERD.
    """
    overlay_buf = io.BytesIO()
    c = canvas.Canvas(overlay_buf, pagesize=(PAGE_W, PAGE_H))

    _dibujar_portada(c, estudiante, curso, config, ano_escolar, docente_nombre,
                     situacion_final, condicion_final, observaciones)
    c.showPage()

    _dibujar_tabla(c, areas_data, grado_nombre, asistencias_por_periodo)
    c.showPage()
    c.save()
    overlay_buf.seek(0)

    plantilla = PdfReader(_get_plantilla_path(grado_nombre))
    overlay = PdfReader(overlay_buf)
    writer = PdfWriter()
    for i, page in enumerate(plantilla.pages):
        if i < len(overlay.pages):
            page.merge_page(overlay.pages[i])
        writer.add_page(page)

    out = io.BytesIO()
    writer.write(out)
    out.seek(0)
    return out
