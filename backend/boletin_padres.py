"""
═══════════════════════════════════════════════════════════════════════
  BOLETÍN PARA PADRES — Reporte detallado de calificaciones
═══════════════════════════════════════════════════════════════════════

Documento formal con el detalle completo de calificaciones por competencia
y período. Sirve para:
  1. Comunicación con padres (progreso del estudiante)
  2. Constancia de traslado (la otra escuela copia los parciales a su registro)

REGLAS:
  - Muestra TODAS las asignaturas del curso.
  - Cada asignatura tiene sus 4 competencias, cada una con P1, P2, P3, P4.
  - El PC de una competencia SOLO aparece si sus 4 períodos están completos.
  - Los parciales no cargados se muestran como "—".
  - Datos del colegio en el encabezado (genérico).

Formato: horizontal (apaisado) por el ancho de la tabla detallada.
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import io
import base64
import re
from datetime import date

from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


# Colores del documento
AZUL = colors.HexColor('#1e4d8b')
AZUL_CLARO = colors.HexColor('#e8eef5')
DORADO = colors.HexColor('#d4a017')
DORADO_CLARO = colors.HexColor('#faf3d8')
GRIS = colors.HexColor('#f5f7fa')
GRIS_TEXTO = colors.HexColor('#999999')
BORDE = colors.HexColor('#cccccc')


def _fmt(valor) -> str:
    """Formatea una nota: entero si tiene valor, '—' si está vacío."""
    if valor is None:
        return '—'
    try:
        return str(int(round(float(valor))))
    except (ValueError, TypeError):
        return '—'


def _valor_periodo(comp, periodo: int):
    """Valor efectivo del período: max(P, RP) si hay RP, si no P."""
    p = getattr(comp, f'p{periodo}', None)
    rp = getattr(comp, f'rp{periodo}', None)
    if p is None:
        return None
    if rp is not None:
        return max(p, rp)
    return p


def _pc_competencia(comp):
    """PC de una competencia = promedio de sus 4 períodos.
    SOLO se calcula si los 4 períodos están completos. Si falta uno → None.
    """
    vals = []
    for p in range(1, 5):
        v = _valor_periodo(comp, p)
        if v is None:
            return None  # falta un período → sin PC
        vals.append(v)
    return round(sum(vals) / 4, 1)


def _dibujar_logo(c, config, x, y, max_w, max_h):
    """Dibuja el logo del colegio si existe. Devuelve True si lo dibujó."""
    logo_raw = getattr(config, 'logo', None) if config else None
    if not logo_raw:
        return False
    try:
        if isinstance(logo_raw, str) and 'base64,' in logo_raw:
            logo_b64 = logo_raw.split('base64,', 1)[1]
        else:
            logo_b64 = logo_raw
        logo_b64 = re.sub(r'\s+', '', logo_b64)
        img = ImageReader(io.BytesIO(base64.b64decode(logo_b64)))
        iw, ih = img.getSize()
        if iw and ih:
            ratio = min(max_w / iw, max_h / ih)
            w, h = iw * ratio, ih * ratio
        else:
            w, h = max_w, max_h
        c.drawImage(img, x, y - h, width=w, height=h, mask='auto',
                    preserveAspectRatio=True)
        return True
    except Exception:
        return False


def generar_boletin_padres(estudiante, curso, asignaturas_data, config,
                            ano_nombre: str) -> io.BytesIO:
    """Genera el boletín de padres detallado en PDF (apaisado).

    asignaturas_data: lista de dicts, cada uno:
        {
          'nombre': 'Lengua Española',
          'competencias': { 1: comp_obj, 2: comp_obj, 3: comp_obj, 4: comp_obj }
        }
        donde comp_obj tiene atributos p1,rp1,p2,rp2,p3,rp3,p4,rp4
        (o None si esa competencia no tiene datos).
    """
    buf = io.BytesIO()
    W, H = landscape(letter)  # 792 x 612
    c = canvas.Canvas(buf, pagesize=(W, H))

    margin = 1.2 * cm
    y = H - margin

    # ─── Encabezado del colegio ───
    nombre_colegio = getattr(config, 'nombre', None) or 'Colegio'
    tiene_logo = _dibujar_logo(c, config, margin, y, 1.4 * cm, 1.4 * cm)
    tx = margin + (1.7 * cm if tiene_logo else 0)

    c.setFont('Helvetica-Bold', 14)
    c.setFillColor(AZUL)
    c.drawString(tx, y - 14, nombre_colegio)

    c.setFont('Helvetica', 8)
    c.setFillColor(colors.black)
    linea2 = []
    if getattr(config, 'direccion', None):
        linea2.append(config.direccion)
    if getattr(config, 'telefono', None):
        linea2.append(f'Tel: {config.telefono}')
    if linea2:
        c.drawString(tx, y - 28, '  •  '.join(linea2))
    linea3 = []
    if getattr(config, 'codigo_centro', None):
        linea3.append(f'Código: {config.codigo_centro}')
    if getattr(config, 'distrito', None):
        linea3.append(f'Distrito: {config.distrito}')
    if getattr(config, 'regional', None):
        linea3.append(f'Regional: {config.regional}')
    if linea3:
        c.drawString(tx, y - 39, '  •  '.join(linea3))

    y -= 52
    c.setStrokeColor(BORDE)
    c.setLineWidth(1)
    c.line(margin, y, W - margin, y)

    # ─── Título ───
    y -= 18
    c.setFont('Helvetica-Bold', 13)
    c.setFillColor(AZUL)
    c.drawCentredString(W / 2, y, 'REPORTE DE CALIFICACIONES')

    # ─── Datos del estudiante ───
    y -= 22
    c.setFont('Helvetica', 9)
    c.setFillColor(colors.black)
    nombre_est = f'{estudiante.nombre} {estudiante.apellido}'.strip().upper()
    grado_nombre = ''
    try:
        grado_nombre = curso.grado.nombre if curso and curso.grado else ''
    except Exception:
        grado_nombre = ''
    curso_nombre = getattr(curso, 'nombre', '') if curso else ''
    matricula = getattr(estudiante, 'sigerd', None) or getattr(estudiante, 'matricula', None) or '___'
    datos = f'Estudiante: {nombre_est}    Grado/Curso: {grado_nombre} {curso_nombre}    Año escolar: {ano_nombre}    Matrícula: {matricula}'
    c.drawString(margin, y, datos)

    # ─── Tabla de calificaciones ───
    y -= 20
    tabla_x = margin
    col_asig = 3.4 * cm          # ancho columna asignatura
    col_parcial = 0.85 * cm      # ancho de cada parcial (P1-P4)
    col_comp = col_parcial * 4   # ancho de una competencia (4 parciales)
    col_pc = 2.4 * cm            # ancho columna PC (los 4 PC)

    # Encabezado nivel 1: nombres de competencias
    header_y = y
    c.setFont('Helvetica-Bold', 7)
    # Celda "Asignatura"
    c.setFillColor(AZUL_CLARO)
    c.rect(tabla_x, header_y - 30, col_asig, 30, fill=1, stroke=1)
    c.setFillColor(colors.black)
    c.drawString(tabla_x + 3, header_y - 20, 'Asignatura')

    cx = tabla_x + col_asig
    for comp_num in range(1, 5):
        c.setFillColor(AZUL_CLARO if comp_num % 2 else colors.HexColor('#dde8f2'))
        c.rect(cx, header_y - 15, col_comp, 15, fill=1, stroke=1)
        c.setFillColor(colors.black)
        c.drawCentredString(cx + col_comp / 2, header_y - 11, f'Competencia {comp_num}')
        # Sub-encabezado: P1 P2 P3 P4
        c.setFont('Helvetica', 6)
        for i, p in enumerate(['P1', 'P2', 'P3', 'P4']):
            px = cx + i * col_parcial
            c.setFillColor(GRIS)
            c.rect(px, header_y - 30, col_parcial, 15, fill=1, stroke=1)
            c.setFillColor(colors.black)
            c.drawCentredString(px + col_parcial / 2, header_y - 26, p)
        c.setFont('Helvetica-Bold', 7)
        cx += col_comp

    # Celda PC
    c.setFillColor(DORADO)
    c.rect(cx, header_y - 30, col_pc, 30, fill=1, stroke=1)
    c.setFillColor(colors.white)
    c.drawCentredString(cx + col_pc / 2, header_y - 20, 'PC (1·2·3·4)')

    # Filas de asignaturas
    row_y = header_y - 30
    row_h = 16
    c.setFont('Helvetica', 7)
    for asig in asignaturas_data:
        if row_y - row_h < margin + 40:
            # Nueva página si no cabe
            c.showPage()
            row_y = H - margin - 20
        row_y -= row_h
        # Nombre asignatura
        c.setFillColor(colors.white)
        c.rect(tabla_x, row_y, col_asig, row_h, fill=1, stroke=1)
        c.setFillColor(colors.black)
        c.setFont('Helvetica', 7)
        nombre_asig = asig['nombre'][:28]
        c.drawString(tabla_x + 3, row_y + 5, nombre_asig)

        cx = tabla_x + col_asig
        pcs = []
        for comp_num in range(1, 5):
            comp = asig['competencias'].get(comp_num)
            for i in range(1, 5):
                px = cx + (i - 1) * col_parcial
                c.setFillColor(colors.white)
                c.rect(px, row_y, col_parcial, row_h, fill=1, stroke=1)
                val = _valor_periodo(comp, i) if comp else None
                if val is None:
                    c.setFillColor(GRIS_TEXTO)
                else:
                    c.setFillColor(colors.black)
                c.drawCentredString(px + col_parcial / 2, row_y + 5, _fmt(val))
            # PC de esta competencia
            pc = _pc_competencia(comp) if comp else None
            pcs.append(pc)
            cx += col_comp

        # Celda PC (los 4)
        c.setFillColor(DORADO_CLARO)
        c.rect(cx, row_y, col_pc, row_h, fill=1, stroke=1)
        c.setFillColor(colors.black)
        c.setFont('Helvetica-Bold', 6)
        pc_str = ' · '.join(_fmt(p) for p in pcs)
        c.drawCentredString(cx + col_pc / 2, row_y + 5, pc_str)
        c.setFont('Helvetica', 7)

    # ─── Nota aclaratoria ───
    row_y -= 24
    c.setFillColor(colors.HexColor('#eef5fc'))
    c.rect(margin, row_y - 6, W - 2 * margin, 24, fill=1, stroke=0)
    c.setFillColor(colors.black)
    c.setFont('Helvetica', 7)
    c.drawString(margin + 6, row_y + 8,
                 'El PC (Promedio por Competencia) aparece solo cuando los 4 períodos de esa competencia están completos.')
    c.drawString(margin + 6, row_y - 1,
                 'Los "—" indican parciales aún no registrados. Este reporte refleja el estado actual de las calificaciones.')

    # ─── Firmas ───
    firma_y = margin + 30
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.5)
    c.line(margin + 40, firma_y, margin + 200, firma_y)
    c.setFont('Helvetica', 8)
    c.drawCentredString(margin + 120, firma_y - 10, 'Firma del Director / Sello')
    c.line(W - margin - 200, firma_y, W - margin - 40, firma_y)
    c.drawCentredString(W - margin - 120, firma_y - 10, 'Firma del Padre/Tutor')

    # ─── Pie ───
    c.setFont('Helvetica', 6)
    c.setFillColor(GRIS_TEXTO)
    hoy = date.today().strftime('%d/%m/%Y')
    c.drawCentredString(W / 2, margin - 2,
                        f'Documento generado por EducaOne — Sistema de Gestión Escolar  •  Fecha de emisión: {hoy}')

    c.showPage()
    c.save()
    buf.seek(0)
    return buf
