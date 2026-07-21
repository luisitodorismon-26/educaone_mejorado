"""
PDF: Planilla de calificaciones por curso + asignatura (v2.16).

Un solo documento sirve para todo el ciclo de vida:
- Curso sin calificar  -> planilla EN BLANCO (para trabajar a lápiz)
- Curso a medias       -> muestra lo cargado y deja vacío lo que falta
- Curso completo       -> constancia física para corroborar sin computadora

Estructura (hoja carta HORIZONTAL):
- Encabezado del colegio (mismos helpers que la lista de estudiantes)
- Línea de contexto: curso · asignatura · profesor · fecha
- Tabla: # | Estudiante | por cada competencia: P1 P2 P3 P4 F | CF
  * El valor mostrado es el EFECTIVO del período: max(P, RP).
    Si la RP mejoró la nota, se marca con «*» (leyenda al pie).
  * F (final de competencia): primaria = final_competencia guardado;
    secundaria = PC calculado SOLO si los 4 períodos están completos
    (regla MINERD: sin autocompletar con parciales).
  * CF: promedio de las F redondeado a entero, solo si todas están.
- Firmas: Profesor(a) y Coordinación. Multipágina con encabezado repetido.

Niveles SEPARADOS: primaria (3 competencias, corte 65) y secundaria
(4 competencias, corte 70) solo comparten el dibujo — los datos llegan
ya armados desde su propio carril en app.py.
"""
import io
from datetime import date

from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch

from pdf_helpers import (
    datos_colegio_para_header, dibujar_encabezado,
)

AZUL = HexColor('#1a3f7a')
GRIS_TXT = HexColor('#444444')
GRIS_SUAVE = HexColor('#888888')
FONDO_HEADER = HexColor('#eef2fa')
FONDO_F = HexColor('#f3f6fc')
FONDO_CF = HexColor('#e8eef9')

FILA_ALTO = 0.235 * inch


def _fmt(v):
    """Formatea una nota: entero sin decimales, 87.5 con uno, None -> ''."""
    if v is None:
        return ''
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return str(int(f)) if f == int(f) else f'{f:.1f}'


def generar_planilla_calificaciones_pdf(
    estudiantes, notas, competencias, curso, tanda, grado, asignatura,
    config, colegio, nivel, ano_escolar=None, docente_nombre=None,
) -> bytes:
    """
    estudiantes: lista de Estudiante activos, ya ordenados por apellido.
    notas: {est_id: {comp_num: {'vals': [4 x float|None], 'rp': [4 x bool],
                                 'final': float|None}}}
    competencias: lista de (numero, etiqueta) p.ej. [(1, 'C1 · Comunicativa'), ...]
    nivel: 'primaria' | 'secundaria' (solo informa el pie de página).
    """
    buf = io.BytesIO()
    pagina = landscape(letter)
    c = canvas.Canvas(buf, pagesize=pagina)
    ancho, alto = pagina

    datos = datos_colegio_para_header(config, colegio)

    n_comp = len(competencias)
    margen = 0.4 * inch
    col_num = 0.3 * inch
    col_nombre = (2.35 if n_comp == 3 else 1.85) * inch
    restante = ancho - 2 * margen - col_num - col_nombre
    sub_cols = n_comp * 5 + 1  # (P1..P4 + F) por competencia + CF
    w_sub = restante / sub_cols

    corte = 65 if nivel == 'primaria' else 70

    def encabezado_pagina():
        y = dibujar_encabezado(c, datos, ancho, alto - 0.35 * inch,
                               ano_escolar=ano_escolar,
                               titulo_seccion='Planilla de calificaciones')
        # Línea de contexto
        grado_n = getattr(grado, 'nombre', '') if grado else ''
        curso_n = getattr(curso, 'nombre', '') if curso else ''
        tanda_n = getattr(tanda, 'nombre', '') if tanda else ''
        asig_n = getattr(asignatura, 'nombre', '') if asignatura else ''
        c.setFont('Helvetica-Bold', 9.5)
        c.setFillColor(GRIS_TXT)
        c.drawString(margen, y, f'{grado_n} {curso_n} · {tanda_n}'.strip(' ·'))
        c.setFont('Helvetica', 9.5)
        c.drawCentredString(ancho / 2, y, f'Asignatura: {asig_n}')
        doc = docente_nombre or '________________________'
        c.drawRightString(ancho - margen, y, f'Profesor(a): {doc}   Fecha: {date.today().strftime("%d/%m/%Y")}')
        return y - 0.16 * inch

    def cabecera_tabla(y):
        """Dos filas: nombres de competencia (agrupados) y subcolumnas."""
        h1, h2 = 0.20 * inch, 0.20 * inch
        # Fila 1: agrupadores
        x = margen
        c.setFillColor(FONDO_HEADER)
        c.rect(x, y - h1 - h2, col_num + col_nombre, h1 + h2, fill=1, stroke=0)
        x2 = margen + col_num + col_nombre
        for i, (_, etiqueta) in enumerate(competencias):
            wg = w_sub * 5
            c.setFillColor(FONDO_HEADER)
            c.rect(x2, y - h1, wg, h1, fill=1, stroke=0)
            c.setFillColor(AZUL)
            c.setFont('Helvetica-Bold', 7.5)
            c.drawCentredString(x2 + wg / 2, y - h1 + 0.055 * inch, etiqueta)
            x2 += wg
        c.setFillColor(FONDO_CF)
        c.rect(x2, y - h1 - h2, w_sub, h1 + h2, fill=1, stroke=0)
        c.setFillColor(AZUL)
        c.setFont('Helvetica-Bold', 7.5)
        c.drawCentredString(x2 + w_sub / 2, y - h1 - h2 / 2 - 0.02 * inch, 'CF')

        # Fila 2: subcolumnas
        c.setFillColor(AZUL)
        c.setFont('Helvetica-Bold', 7.5)
        c.drawCentredString(margen + col_num / 2, y - h1 - h2 + 0.055 * inch, '#')
        c.drawString(margen + col_num + 4, y - h1 - h2 + 0.055 * inch, 'Estudiante')
        x2 = margen + col_num + col_nombre
        for _ in competencias:
            for sub in ('P1', 'P2', 'P3', 'P4', 'F'):
                if sub == 'F':
                    c.setFillColor(FONDO_F)
                    c.rect(x2, y - h1 - h2, w_sub, h2, fill=1, stroke=0)
                c.setFillColor(AZUL)
                c.drawCentredString(x2 + w_sub / 2, y - h1 - h2 + 0.055 * inch, sub)
                x2 += w_sub
        # Bordes de la cabecera
        c.setStrokeColor(GRIS_SUAVE)
        c.setLineWidth(0.6)
        c.rect(margen, y - h1 - h2, ancho - 2 * margen, h1 + h2, fill=0, stroke=1)
        return y - h1 - h2

    def fila_estudiante(y, idx, est):
        c.setStrokeColor(GRIS_SUAVE)
        c.setLineWidth(0.4)
        # Fondos suaves de F y CF para guiar el ojo
        x = margen + col_num + col_nombre
        for _ in competencias:
            c.setFillColor(FONDO_F)
            c.rect(x + w_sub * 4, y - FILA_ALTO, w_sub, FILA_ALTO, fill=1, stroke=0)
            x += w_sub * 5
        c.setFillColor(FONDO_CF)
        c.rect(x, y - FILA_ALTO, w_sub, FILA_ALTO, fill=1, stroke=0)

        c.setFillColor(GRIS_TXT)
        c.setFont('Helvetica', 8)
        c.drawCentredString(margen + col_num / 2, y - FILA_ALTO + 0.065 * inch, str(idx))
        nombre = f'{est.apellido}, {est.nombre}'.upper()
        max_chars = 40 if n_comp == 3 else 30
        if len(nombre) > max_chars:
            nombre = nombre[:max_chars - 3] + '...'
        c.drawString(margen + col_num + 4, y - FILA_ALTO + 0.065 * inch, nombre)

        datos_est = notas.get(est.id, {})
        x = margen + col_num + col_nombre
        finales = []
        for num, _ in competencias:
            d = datos_est.get(num, {})
            vals = d.get('vals') or [None] * 4
            rp_flags = d.get('rp') or [False] * 4
            for i in range(4):
                txt = _fmt(vals[i])
                if txt:
                    if rp_flags[i]:
                        txt += '*'
                    v = float(vals[i])
                    c.setFillColor(HexColor('#b02a2a') if v < corte else GRIS_TXT)
                    c.setFont('Helvetica', 7.5)
                    c.drawCentredString(x + w_sub / 2, y - FILA_ALTO + 0.065 * inch, txt)
                x += w_sub
            f = d.get('final')
            finales.append(f)
            if f is not None:
                c.setFillColor(HexColor('#b02a2a') if float(f) < corte else AZUL)
                c.setFont('Helvetica-Bold', 7.5)
                c.drawCentredString(x + w_sub / 2, y - FILA_ALTO + 0.065 * inch, _fmt(f))
            x += w_sub
        # CF: solo con TODAS las finales (regla MINERD, sin autocompletar)
        if finales and all(f is not None for f in finales):
            cf = round(sum(float(f) for f in finales) / len(finales))
            c.setFillColor(HexColor('#b02a2a') if cf < corte else AZUL)
            c.setFont('Helvetica-Bold', 8)
            c.drawCentredString(x + w_sub / 2, y - FILA_ALTO + 0.065 * inch, str(cf))

        # Líneas de la fila
        c.setStrokeColor(GRIS_SUAVE)
        c.line(margen, y - FILA_ALTO, ancho - margen, y - FILA_ALTO)
        xv = margen
        for wcol in [col_num, col_nombre] + [w_sub] * sub_cols:
            xv += wcol
            c.line(xv, y, xv, y - FILA_ALTO)
        c.line(margen, y, margen, y - FILA_ALTO)
        return y - FILA_ALTO

    def pie_final(y):
        c.setFont('Helvetica', 7)
        c.setFillColor(GRIS_SUAVE)
        c.drawString(margen, y - 0.18 * inch,
                     f'* Nota con recuperación de período (RP) aplicada · '
                     f'F = final de competencia · CF = calificación final (solo con las {n_comp} completas) · '
                     f'Nivel {nivel} · aprueba con {corte}')
        y2 = y - 0.62 * inch
        c.setStrokeColor(GRIS_TXT)
        c.setLineWidth(0.7)
        for x0, etiqueta in ((margen + 0.6 * inch, 'Firma del Profesor(a)'),
                             (ancho / 2 + 0.6 * inch, 'Firma de Coordinación')):
            c.line(x0, y2, x0 + 2.4 * inch, y2)
            c.setFont('Helvetica', 7.5)
            c.setFillColor(GRIS_TXT)
            c.drawCentredString(x0 + 1.2 * inch, y2 - 0.14 * inch, etiqueta)

    # ── Render ──
    y = encabezado_pagina()
    y = cabecera_tabla(y)
    minimo_y = 1.15 * inch  # reservar espacio del pie en la última página
    for idx, est in enumerate(estudiantes, start=1):
        if y - FILA_ALTO < minimo_y:
            c.showPage()
            y = encabezado_pagina()
            y = cabecera_tabla(y)
        y = fila_estudiante(y, idx, est)

    pie_final(y)
    c.showPage()
    c.save()
    return buf.getvalue()
