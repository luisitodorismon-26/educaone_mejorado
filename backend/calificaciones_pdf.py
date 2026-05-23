"""
PDF: Calificaciones por período.

Muestra las notas de un curso/asignatura para un período específico (P1-P4):
- 4 parciales del período
- PC (Promedio del período)
- RP (Recuperación pedagógica, si aplica)
- Literal (A/B/C/D/F)
- Estadísticas al pie: promedio del curso, aprobados, reprobados, mejor nota.
"""
import io
from reportlab.lib.pagesizes import letter
from reportlab.lib.colors import HexColor, black, white
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch

from pdf_helpers import (
    COLOR_PRIMARIO, COLOR_SECUNDARIO, COLOR_TEXTO, COLOR_BORDE,
    datos_colegio_para_header, dibujar_encabezado, dibujar_pie_firmas,
)


def _literal(nota):
    """Devuelve la letra MINERD según la nota numérica."""
    if nota is None:
        return '—'
    if nota >= 90:
        return 'A'
    if nota >= 80:
        return 'B'
    if nota >= 70:
        return 'C'
    return 'F'


def _color_literal(literal):
    """Color del literal según escala MINERD."""
    if literal == 'A':
        return HexColor('#085041')
    if literal == 'B':
        return HexColor('#185FA5')
    if literal == 'C':
        return HexColor('#854F0B')
    if literal == 'F':
        return HexColor('#993556')
    return HexColor('#888888')


def generar_calificaciones_pdf(calificaciones, curso, grado, tanda, asignatura, periodo: int,
                                  config, colegio, ano_escolar: str = None) -> bytes:
    """
    Genera PDF de calificaciones de un período.
    
    calificaciones: lista de dicts {'estudiante': {...}, 'calificacion': {...}}
                    como devuelve el endpoint GET /api/calificaciones/curso/{c}/asignatura/{a}
    periodo: 1, 2, 3 o 4
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    ancho, alto = letter
    
    datos = datos_colegio_para_header(config, colegio)
    
    # Encabezado
    y = dibujar_encabezado(c, datos, ancho, alto - 0.4*inch,
                            ano_escolar=ano_escolar,
                            titulo_seccion="Calificaciones por período")
    
    # Subtítulo: curso · asignatura · período
    grado_nombre = getattr(grado, 'nombre', '') if grado else ''
    curso_nombre = getattr(curso, 'nombre', '') if curso else ''
    tanda_nombre = getattr(tanda, 'nombre', '') if tanda else ''
    asig_nombre = getattr(asignatura, 'nombre', '') if asignatura else ''
    subtitulo = f"{grado_nombre} {curso_nombre} · Tanda {tanda_nombre} · {asig_nombre} · Período {periodo}".strip()
    
    c.setFont('Helvetica', 11)
    c.setFillColor(HexColor('#444444'))
    c.drawCentredString(ancho / 2, y, subtitulo)
    y -= 0.40 * inch
    
    margen_izq = 0.5 * inch
    margen_der = 0.5 * inch
    ancho_util = ancho - margen_izq - margen_der
    
    # Columnas para la tabla
    cols = [
        ('#', 0.30 * inch),
        ('Estudiante', 2.20 * inch),
        (f'P{periodo}.1', 0.55 * inch),
        (f'P{periodo}.2', 0.55 * inch),
        (f'P{periodo}.3', 0.55 * inch),
        (f'P{periodo}.4', 0.55 * inch),
        ('PC', 0.65 * inch),
        ('RP', 0.55 * inch),
        ('Lit.', 0.50 * inch),
    ]
    
    # Header de tabla
    c.setFillColor(HexColor('#F0F0F0'))
    c.rect(margen_izq, y - 0.05*inch, ancho_util, 0.30*inch, stroke=0, fill=1)
    
    c.setFont('Helvetica-Bold', 9)
    c.setFillColor(black)
    x = margen_izq + 0.06*inch
    for label, w in cols:
        if label in ['#', 'Lit.']:
            c.drawCentredString(x + w/2 - 0.06*inch, y + 0.10*inch, label)
        elif label.startswith('P') or label in ['PC', 'RP']:
            c.drawCentredString(x + w/2 - 0.06*inch, y + 0.10*inch, label)
        else:
            c.drawString(x, y + 0.10*inch, label)
        x += w
    
    c.setStrokeColor(HexColor('#999999'))
    c.setLineWidth(0.5)
    c.line(margen_izq, y - 0.05*inch, ancho - margen_der, y - 0.05*inch)
    y -= 0.30 * inch
    
    # Filas
    total_pc = 0
    count_pc = 0
    aprobados = 0
    reprobados = 0
    mejor = None
    
    for i, item in enumerate(calificaciones, start=1):
        if y < 1.5 * inch:
            c.setFont('Helvetica', 8)
            c.setFillColor(COLOR_SECUNDARIO)
            c.drawString(margen_izq, 0.5*inch, f"Página {c.getPageNumber()}")
            c.showPage()
            y = alto - 0.6*inch
        
        est = item.get('estudiante', {})
        cal = item.get('calificacion', {}) or {}
        
        # Saltar retirados (opcional — los mostramos pero marcados)
        nombre_completo = est.get('nombre_completo') or f"{est.get('apellido','')}, {est.get('nombre','')}"
        nombre_completo = nombre_completo[:32]
        
        # Tomar parciales del período correcto
        p1 = cal.get(f'p{periodo}_p1')
        p2 = cal.get(f'p{periodo}_p2')
        p3 = cal.get(f'p{periodo}_p3')
        p4 = cal.get(f'p{periodo}_p4')
        pc = cal.get(f'pc{periodo}')
        rp = cal.get(f'rp{periodo}')
        
        # Determinar literal del período (priorizando RP si existe)
        nota_final_periodo = rp if rp is not None else pc
        literal_letra = _literal(nota_final_periodo)
        
        # Estadísticas
        if pc is not None:
            total_pc += pc
            count_pc += 1
            if mejor is None or pc > mejor:
                mejor = pc
            if (nota_final_periodo or 0) >= 70:
                aprobados += 1
            else:
                reprobados += 1
        
        x = margen_izq + 0.06*inch
        c.setFont('Helvetica', 9)
        c.setFillColor(COLOR_TEXTO)
        
        # #
        c.drawCentredString(x + cols[0][1]/2 - 0.06*inch, y + 0.05*inch, str(i))
        x += cols[0][1]
        # Estudiante
        c.drawString(x, y + 0.05*inch, nombre_completo)
        x += cols[1][1]
        # P.1-P.4
        for valor in [p1, p2, p3, p4]:
            txt = f"{valor:.0f}" if isinstance(valor, (int, float)) else '—'
            c.drawCentredString(x + cols[2][1]/2 - 0.06*inch, y + 0.05*inch, txt)
            x += cols[2][1]
        # PC (destacado)
        c.setFillColor(HexColor('#FAEEDA'))
        c.rect(x - 0.04*inch, y - 0.02*inch, cols[6][1] - 0.04*inch, 0.26*inch, stroke=0, fill=1)
        c.setFillColor(HexColor('#993556') if (pc is not None and pc < 70) else COLOR_TEXTO)
        c.setFont('Helvetica-Bold', 9)
        pc_txt = f"{pc:.1f}" if isinstance(pc, (int, float)) else '—'
        c.drawCentredString(x + cols[6][1]/2 - 0.06*inch, y + 0.05*inch, pc_txt)
        x += cols[6][1]
        # RP
        c.setFillColor(COLOR_TEXTO)
        c.setFont('Helvetica', 9)
        rp_txt = f"{rp:.1f}" if isinstance(rp, (int, float)) else '—'
        c.drawCentredString(x + cols[7][1]/2 - 0.06*inch, y + 0.05*inch, rp_txt)
        x += cols[7][1]
        # Literal (con color)
        c.setFillColor(HexColor('#E6F1FB'))
        c.rect(x - 0.04*inch, y - 0.02*inch, cols[8][1] - 0.04*inch, 0.26*inch, stroke=0, fill=1)
        c.setFillColor(_color_literal(literal_letra))
        c.setFont('Helvetica-Bold', 10)
        c.drawCentredString(x + cols[8][1]/2 - 0.06*inch, y + 0.05*inch, literal_letra)
        
        # Línea separadora suave
        c.setStrokeColor(HexColor('#EEEEEE'))
        c.setLineWidth(0.3)
        c.line(margen_izq, y - 0.04*inch, ancho - margen_der, y - 0.04*inch)
        
        y -= 0.28 * inch
    
    # Estadísticas al pie
    y -= 0.15 * inch
    promedio_curso = (total_pc / count_pc) if count_pc > 0 else 0
    
    c.setFillColor(HexColor('#F9F9F9'))
    c.rect(margen_izq, y - 0.45*inch, ancho_util, 0.45*inch, stroke=0, fill=1)
    
    c.setFont('Helvetica-Bold', 9)
    c.setFillColor(black)
    stats = [
        ("Promedio del curso", f"{promedio_curso:.1f}"),
        ("Aprobados", str(aprobados)),
        ("Reprobados", str(reprobados)),
        ("Mejor nota", f"{mejor:.1f}" if mejor is not None else "—"),
    ]
    ancho_stat = ancho_util / len(stats)
    for i, (label, valor) in enumerate(stats):
        x_stat = margen_izq + i * ancho_stat + 0.1*inch
        c.setFont('Helvetica', 8)
        c.setFillColor(COLOR_SECUNDARIO)
        c.drawString(x_stat, y - 0.15*inch, label)
        c.setFont('Helvetica-Bold', 11)
        c.setFillColor(black)
        c.drawString(x_stat, y - 0.32*inch, valor)
    y -= 0.55 * inch
    
    # Leyenda
    c.setFont('Helvetica', 7)
    c.setFillColor(COLOR_SECUNDARIO)
    leyenda = (f"Leyenda: P{periodo}.1-P{periodo}.4 = Parciales · PC = Promedio del Período · "
                f"RP = Recuperación Pedagógica · Literal: A (90-100), B (80-89), C (70-79), F (<70)")
    c.drawString(margen_izq, y, leyenda)
    y -= 0.20 * inch
    
    # Firmas
    y_firmas = max(y - 0.8*inch, 1.0*inch)
    dibujar_pie_firmas(c, ancho, y_firmas,
                        etiquetas=["Profesor", "Dirección"])
    
    c.save()
    return buf.getvalue()
