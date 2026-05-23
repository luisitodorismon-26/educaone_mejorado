"""
PDF: Reporte de Conducta profesional.

Rediseño v2.11.1: layout limpio, sin solapamientos, profesional.

Estructura:
- Encabezado: 3 columnas (LOGO | datos colegio | badge nº reporte + fechas)
- Título grande centrado
- Grid 3×2 de datos del estudiante con etiquetas pequeñas
- 3 secciones de contenido con borde lateral de color
- Barra de metadatos (reportado por · estado · fecha)
- Firmas duales: Coordinación/Dirección + Padre/Tutor
"""
import io
from reportlab.lib.pagesizes import letter
from reportlab.lib.colors import HexColor, black, white
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.pdfbase.pdfmetrics import stringWidth

from pdf_helpers import (
    COLOR_PRIMARIO, COLOR_SECUNDARIO, COLOR_TEXTO, COLOR_BORDE,
    _logo_image_from_base64, datos_colegio_para_header,
    formato_fecha_corto, padre_tutor_principal,
)

# Colores del nuevo diseño
COLOR_AZUL_BORDE = HexColor('#185FA5')
COLOR_AZUL_FONDO = HexColor('#F8FAFC')
COLOR_VERDE_BORDE = HexColor('#085041')
COLOR_VERDE_FONDO = HexColor('#F4FAF7')
COLOR_AMBAR_BORDE = HexColor('#854F0B')
COLOR_AMBAR_FONDO = HexColor('#FDF8EF')
COLOR_GRIS_BORDE = HexColor('#666666')
COLOR_GRIS_FONDO = HexColor('#F5F5F5')
COLOR_GRID_FONDO = HexColor('#F9F9F9')
COLOR_META_FONDO = HexColor('#F0F4F8')
COLOR_TITULO_ROJO = HexColor('#993C1D')


def _color_gravedad(gravedad: str):
    g = (gravedad or '').lower()
    if g in ('grave', 'severa', 'alta'):
        return HexColor('#FBE3E8'), HexColor('#993556')
    if g in ('moderada', 'moderado', 'media'):
        return HexColor('#FAEEDA'), HexColor('#854F0B')
    return HexColor('#E1F5EE'), HexColor('#085041')


def _dibujar_encabezado_3cols(c, datos, ancho_pag, alto_pag, numero_reporte, ano_escolar):
    """Encabezado en 3 columnas: LOGO | nombre+datos | badge+fechas."""
    margen_izq = 0.5 * inch
    margen_der = 0.5 * inch
    ancho_util = ancho_pag - margen_izq - margen_der
    
    col_logo_w = 0.85 * inch
    col_badge_w = 1.55 * inch
    col_centro_w = ancho_util - col_logo_w - col_badge_w - 0.30*inch
    
    x_logo = margen_izq
    x_centro = margen_izq + col_logo_w + 0.15*inch
    x_badge = ancho_pag - margen_der - col_badge_w
    
    y_top = alto_pag - 0.5*inch
    
    # COLUMNA 1: LOGO
    logo = _logo_image_from_base64(datos.get('logo_b64'),
                                       max_width=0.75*inch, max_height=0.75*inch)
    if logo:
        logo.drawHeight = 0.75 * inch
        logo.drawWidth = 0.75 * inch
        logo.drawOn(c, x_logo, y_top - 0.75*inch)
    else:
        c.setStrokeColor(HexColor('#DDDDDD'))
        c.setFillColor(HexColor('#FAFAFA'))
        c.circle(x_logo + 0.375*inch, y_top - 0.375*inch, 0.35*inch, stroke=1, fill=1)
        c.setFont('Helvetica', 7)
        c.setFillColor(HexColor('#AAAAAA'))
        c.drawCentredString(x_logo + 0.375*inch, y_top - 0.40*inch, 'LOGO')
    
    # COLUMNA 2: nombre + datos
    c.setFont('Helvetica-Bold', 7.5)
    c.setFillColor(COLOR_PRIMARIO)
    c.drawString(x_centro, y_top - 0.10*inch, "REPÚBLICA DOMINICANA · MINERD")
    
    c.setFont('Helvetica-Bold', 14)
    c.setFillColor(black)
    nombre = datos['nombre'] or 'Centro Educativo'
    if stringWidth(nombre, 'Helvetica-Bold', 14) > col_centro_w - 0.1*inch:
        c.setFont('Helvetica-Bold', 12)
    c.drawString(x_centro, y_top - 0.30*inch, nombre)
    
    partes = []
    if datos.get('rnc'):
        partes.append(f"RNC: {datos['rnc']}")
    if datos.get('direccion'):
        partes.append(datos['direccion'])
    if datos.get('telefono'):
        partes.append(f"Tel: {datos['telefono']}")
    if datos.get('email'):
        partes.append(datos['email'])
    linea_datos = ' · '.join(partes)
    
    c.setFont('Helvetica', 8)
    c.setFillColor(COLOR_SECUNDARIO)
    if linea_datos:
        c.drawString(x_centro, y_top - 0.48*inch, linea_datos[:140])
    
    # COLUMNA 3: badge + fechas
    badge_w = col_badge_w
    badge_h = 0.42 * inch
    badge_y = y_top - badge_h
    
    c.setFillColor(HexColor('#FAEEDA'))
    c.roundRect(x_badge, badge_y, badge_w, badge_h, 4, stroke=0, fill=1)
    
    c.setFont('Helvetica-Bold', 7)
    c.setFillColor(HexColor('#854F0B'))
    c.drawCentredString(x_badge + badge_w/2, badge_y + badge_h - 0.14*inch, "REPORTE Nº")
    
    c.setFont('Helvetica-Bold', 13)
    c.setFillColor(HexColor('#854F0B'))
    c.drawCentredString(x_badge + badge_w/2, badge_y + 0.10*inch, numero_reporte)
    
    from datetime import datetime as _dt
    fecha_hoy = _dt.now().strftime('%d/%m/%Y')
    
    c.setFont('Helvetica', 8)
    c.setFillColor(COLOR_SECUNDARIO)
    y_meta = badge_y - 0.16*inch
    if ano_escolar:
        c.drawRightString(ancho_pag - margen_der, y_meta, f"Año {ano_escolar}")
        y_meta -= 0.14*inch
    c.drawRightString(ancho_pag - margen_der, y_meta, f"Emitido: {fecha_hoy}")
    
    # Línea separadora azul
    y_linea = y_top - 0.85*inch
    c.setStrokeColor(COLOR_PRIMARIO)
    c.setLineWidth(1.5)
    c.line(margen_izq, y_linea, ancho_pag - margen_der, y_linea)
    
    return y_linea - 0.10*inch


def _dibujar_grid_datos(c, x, y, ancho_total, items, alto_fila=0.55*inch):
    """
    Grid de datos del estudiante. El primer item (estudiante) puede ocupar
    2 columnas si su valor es largo, para evitar que choque con la columna 2.
    Layout adaptativo:
      - Nombre corto (<25 chars): 3 columnas normales por fila
      - Nombre largo: fila 1 = [estudiante (2 cols)] [matrícula]
                      fila 2 = [curso] [fecha] [padre/tutor]
                      fila 3 = [gravedad]
    """
    n_cols = 3
    col_w = ancho_total / n_cols
    
    # Detectar si el nombre del estudiante (primer item) es largo
    primer_valor = str(items[0].get('valor', '')) if items else ''
    nombre_largo = len(primer_valor) > 22
    
    # Calcular altura total
    if nombre_largo:
        # Reorganizar: estudiante ocupa 2 cols
        n_filas = 3  # est+matricula / curso+fecha+padre / gravedad
    else:
        n_filas = (len(items) + n_cols - 1) // n_cols
    alto_total = alto_fila * n_filas + 0.20*inch
    
    c.setFillColor(COLOR_GRID_FONDO)
    c.roundRect(x, y - alto_total, ancho_total, alto_total, 5, stroke=0, fill=1)
    
    # Determinar posiciones de cada item
    if nombre_largo:
        # items asume orden: [estudiante, matricula, curso, fecha, padre, gravedad]
        posiciones = [
            (0, 0, 2),  # estudiante: fila 0, col 0, ocupa 2
            (0, 2, 1),  # matricula: fila 0, col 2, ocupa 1
            (1, 0, 1),  # curso: fila 1, col 0
            (1, 1, 1),  # fecha: fila 1, col 1
            (1, 2, 1),  # padre: fila 1, col 2
            (2, 0, 1),  # gravedad: fila 2, col 0
        ]
    else:
        # 3 columnas × 2 filas normales
        posiciones = [(i // n_cols, i % n_cols, 1) for i in range(len(items))]
    
    for item, (fila, col, span) in zip(items, posiciones):
        cell_x = x + col * col_w + 0.15*inch
        cell_y = y - fila * alto_fila - 0.20*inch
        ancho_celda = col_w * span - 0.30*inch
        
        label = item.get('label', '')
        valor = item.get('valor', '')
        es_badge = item.get('badge', False)
        es_italic_gris = item.get('italic_gris', False)
        
        c.setFont('Helvetica-Bold', 7)
        c.setFillColor(HexColor('#888888'))
        c.drawString(cell_x, cell_y, label.upper())
        
        if es_badge:
            color_fondo, color_texto = _color_gravedad(valor)
            c.setFont('Helvetica-Bold', 8)
            badge_text = (valor or 'LEVE').upper()
            text_w = stringWidth(badge_text, 'Helvetica-Bold', 8)
            badge_w = text_w + 12
            badge_h = 14
            c.setFillColor(color_fondo)
            c.roundRect(cell_x, cell_y - 0.22*inch, badge_w, badge_h, 3, stroke=0, fill=1)
            c.setFillColor(color_texto)
            c.drawString(cell_x + 6, cell_y - 0.22*inch + 4, badge_text)
        elif es_italic_gris:
            c.setFont('Helvetica-Oblique', 9)
            c.setFillColor(HexColor('#999999'))
            # Truncar al ancho de la celda
            max_chars = int(ancho_celda / 0.06)
            c.drawString(cell_x, cell_y - 0.15*inch, str(valor)[:max_chars])
        else:
            # Auto-ajustar el tamaño de fuente si el texto no cabe
            font_size = 10
            font_name = 'Helvetica-Bold'
            texto = str(valor)
            while font_size > 7 and stringWidth(texto, font_name, font_size) > ancho_celda:
                font_size -= 0.5
            c.setFont(font_name, font_size)
            c.setFillColor(black)
            c.drawString(cell_x, cell_y - 0.15*inch, texto)
    
    return y - alto_total - 0.12*inch


def _dibujar_seccion(c, x, y, ancho, titulo, contenido,
                      color_borde, color_fondo,
                      es_pendiente=False, alto_minimo=0.55*inch):
    """Sección con cuadrado de color al lado del título + caja."""
    c.setFillColor(color_borde)
    c.rect(x, y - 0.13*inch, 3, 0.13*inch, stroke=0, fill=1)
    
    c.setFont('Helvetica-Bold', 8)
    c.setFillColor(color_borde)
    c.drawString(x + 0.10*inch, y - 0.10*inch, titulo.upper())
    
    y_caja_top = y - 0.20*inch
    
    styles = getSampleStyleSheet()
    estilo_normal = ParagraphStyle(
        'Cuerpo', parent=styles['Normal'], fontName='Helvetica',
        fontSize=10, leading=13, textColor=COLOR_TEXTO, alignment=TA_LEFT,
    )
    estilo_pendiente = ParagraphStyle(
        'Pendiente', parent=styles['Normal'], fontName='Helvetica-Oblique',
        fontSize=9, leading=12, textColor=HexColor('#888888'), alignment=TA_LEFT,
    )
    
    estilo = estilo_pendiente if es_pendiente else estilo_normal
    contenido_html = (contenido or '').replace('\n', '<br/>')
    p = Paragraph(contenido_html, estilo)
    
    ancho_caja = ancho - 0.10*inch
    _, h_necesaria = p.wrap(ancho_caja - 0.20*inch, 8*inch)
    alto_caja = max(h_necesaria + 0.14*inch, alto_minimo)
    
    c.setFillColor(color_fondo)
    c.roundRect(x + 0.10*inch, y_caja_top - alto_caja, ancho_caja, alto_caja,
                 3, stroke=0, fill=1)
    
    p.drawOn(c, x + 0.22*inch, y_caja_top - h_necesaria - 0.04*inch)
    
    return y_caja_top - alto_caja - 0.10*inch


def _dibujar_barra_metadatos(c, x, y, ancho, items):
    """Barra horizontal con metadatos."""
    alto = 0.28*inch
    c.setFillColor(COLOR_META_FONDO)
    c.roundRect(x, y - alto, ancho, alto, 3, stroke=0, fill=1)
    
    n = len(items)
    if n == 0:
        return y - alto - 0.10*inch
    col_w = ancho / n
    
    for i, (label, valor, color) in enumerate(items):
        cell_x = x + i * col_w + 0.12*inch
        c.setFont('Helvetica-Bold', 7.5)
        c.setFillColor(HexColor('#475569'))
        c.drawString(cell_x, y - 0.11*inch, f"{label.upper()}:")
        
        label_w = stringWidth(f"{label.upper()}:", 'Helvetica-Bold', 7.5)
        c.setFont('Helvetica', 8.5)
        c.setFillColor(color or HexColor('#0F172A'))
        c.drawString(cell_x + label_w + 4, y - 0.11*inch, str(valor)[:50])
    
    return y - alto - 0.10*inch


def generar_reporte_conducta_pdf(reporte, estudiante, curso, grado, tanda,
                                    reportador, respondedor, config, colegio,
                                    ano_escolar: str = None) -> bytes:
    """Genera el PDF del reporte de conducta."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    ancho_pag, alto_pag = letter
    margen_izq = 0.5 * inch
    margen_der = 0.5 * inch
    ancho_util = ancho_pag - margen_izq - margen_der
    
    datos = datos_colegio_para_header(config, colegio)
    numero_rep = reporte.numero_reporte or f"#{reporte.id:04d}"
    
    # ENCABEZADO
    y = _dibujar_encabezado_3cols(c, datos, ancho_pag, alto_pag, numero_rep, ano_escolar)
    
    # TÍTULO
    y -= 0.20*inch
    c.setFont('Helvetica-Bold', 17)
    c.setFillColor(COLOR_TITULO_ROJO)
    c.drawCentredString(ancho_pag / 2, y, "REPORTE DE CONDUCTA")
    y -= 0.18*inch
    c.setFont('Helvetica', 9)
    c.setFillColor(COLOR_SECUNDARIO)
    c.drawCentredString(ancho_pag / 2, y, "Comunicación oficial a padres/tutores")
    y -= 0.30*inch
    
    # GRID DATOS ESTUDIANTE
    grado_nombre = getattr(grado, 'nombre', '') if grado else ''
    curso_nombre = getattr(curso, 'nombre', '') if curso else ''
    tanda_nombre = getattr(tanda, 'nombre', '') if tanda else ''
    
    padre = padre_tutor_principal(estudiante)
    padre_es_vacio = padre == "(sin datos)"
    fecha_incidente = formato_fecha_corto(reporte.fecha)
    gravedad = reporte.gravedad or 'leve'
    
    nombre_completo = f"{estudiante.apellido or ''}, {estudiante.nombre or ''}".strip(', ')
    curso_completo = f"{grado_nombre} {curso_nombre} · {tanda_nombre}".strip()
    
    items_grid = [
        {'label': 'Estudiante', 'valor': nombre_completo},
        {'label': 'Matrícula', 'valor': estudiante.matricula or '—'},
        {'label': 'Curso · Tanda', 'valor': curso_completo},
        {'label': 'Fecha del incidente', 'valor': fecha_incidente},
        {'label': 'Padre / Tutor', 'valor': padre, 'italic_gris': padre_es_vacio},
        {'label': 'Gravedad', 'valor': gravedad, 'badge': True},
    ]
    y = _dibujar_grid_datos(c, margen_izq, y, ancho_util, items_grid)
    
    # SECCIONES
    y = _dibujar_seccion(c, margen_izq, y, ancho_util,
                          "Descripción del incidente",
                          reporte.descripcion or "(Sin descripción)",
                          color_borde=COLOR_AZUL_BORDE,
                          color_fondo=COLOR_AZUL_FONDO)
    
    acciones_centro = reporte.acciones_centro
    y = _dibujar_seccion(c, margen_izq, y, ancho_util,
                          "Acciones tomadas por el centro",
                          acciones_centro or "Pendiente de completar por la dirección.",
                          color_borde=COLOR_VERDE_BORDE,
                          color_fondo=COLOR_VERDE_FONDO,
                          es_pendiente=not acciones_centro)
    
    acciones_hogar = reporte.acciones_hogar
    y = _dibujar_seccion(c, margen_izq, y, ancho_util,
                          "Acciones esperadas en el hogar",
                          acciones_hogar or "Pendiente de completar por la dirección.",
                          color_borde=COLOR_AMBAR_BORDE,
                          color_fondo=COLOR_AMBAR_FONDO,
                          es_pendiente=not acciones_hogar)
    
    if reporte.respuesta:
        y = _dibujar_seccion(c, margen_izq, y, ancho_util,
                              "Comentario adicional",
                              reporte.respuesta,
                              color_borde=COLOR_GRIS_BORDE,
                              color_fondo=COLOR_GRIS_FONDO,
                              alto_minimo=0.45*inch)
    
    # METADATOS
    reporter_nombre = "—"
    if reportador:
        n = f"{reportador.nombre or ''} {reportador.apellido or ''}".strip()
        rol = (reportador.role or '').capitalize()
        reporter_nombre = f"{n} ({rol})" if rol else n
    
    estado = (reporte.estado or 'pendiente').lower()
    if estado == 'pendiente':
        estado_label = "Pendiente de respuesta"
        estado_color = HexColor('#854F0B')
    elif reporte.confirmado_padre:
        estado_label = "Firmado por padre"
        estado_color = HexColor('#085041')
    elif reporte.enviado_padres:
        estado_label = "Enviado al padre"
        estado_color = HexColor('#185FA5')
    else:
        estado_label = "Respondido"
        estado_color = HexColor('#085041')
    
    fecha_gen = formato_fecha_corto(reporte.fecha_respuesta or reporte.fecha)
    
    y -= 0.05*inch
    y = _dibujar_barra_metadatos(c, margen_izq, y, ancho_util, [
        ("Reportado por", reporter_nombre, None),
        ("Estado", estado_label, estado_color),
        ("Generado", fecha_gen, None),
    ])
    
    # FIRMAS
    y_firmas = max(y - 0.6*inch, 1.3*inch)
    ancho_firma = (ancho_util - 0.6*inch) / 2
    
    x1_centro = margen_izq + ancho_firma/2
    c.setStrokeColor(black)
    c.setLineWidth(0.7)
    c.line(margen_izq, y_firmas, margen_izq + ancho_firma, y_firmas)
    c.setFont('Helvetica-Bold', 9)
    c.setFillColor(black)
    c.drawCentredString(x1_centro, y_firmas - 0.16*inch, "Coordinación / Dirección")
    c.setFont('Helvetica', 7.5)
    c.setFillColor(HexColor('#888888'))
    c.drawCentredString(x1_centro, y_firmas - 0.30*inch, "Firma y fecha")
    
    x2_start = ancho_pag - margen_der - ancho_firma
    x2_centro = x2_start + ancho_firma/2
    c.line(x2_start, y_firmas, ancho_pag - margen_der, y_firmas)
    c.setFont('Helvetica-Bold', 9)
    c.setFillColor(black)
    c.drawCentredString(x2_centro, y_firmas - 0.16*inch, "Padre / Tutor")
    c.setFont('Helvetica', 7.5)
    c.setFillColor(HexColor('#888888'))
    c.drawCentredString(x2_centro, y_firmas - 0.30*inch, "Firma de recibido")
    
    # PIE
    c.setStrokeColor(HexColor('#DDDDDD'))
    c.setLineWidth(0.3)
    c.line(margen_izq, 0.55*inch, ancho_pag - margen_der, 0.55*inch)
    c.setFont('Helvetica', 7)
    c.setFillColor(HexColor('#999999'))
    c.drawCentredString(ancho_pag / 2, 0.42*inch,
                          "Este documento es una comunicación oficial del centro educativo. "
                          "Una copia ha sido archivada en el expediente del estudiante.")
    
    c.save()
    return buf.getvalue()
