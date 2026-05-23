"""
PDF Helpers — utilidades comunes para generar PDFs con identidad del colegio.

Estos helpers se usan en:
- Lista de estudiantes (lista_estudiantes_pdf.py)
- Calificaciones por período (calificaciones_pdf.py)
- Reportes de conducta (reporte_conducta_pdf.py)

Todos los PDFs comparten el mismo encabezado con logo + nombre + RNC + dirección.
"""
import base64
import io
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib.colors import HexColor, white, black, grey
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.platypus import Image
from reportlab.pdfbase.pdfmetrics import stringWidth


# Colores estándar del sistema
COLOR_PRIMARIO = HexColor('#185FA5')      # azul institucional
COLOR_SECUNDARIO = HexColor('#666666')    # gris medio
COLOR_TEXTO = HexColor('#222222')          # casi negro
COLOR_FONDO_SECCION = HexColor('#F5F5F5')  # gris muy claro
COLOR_BORDE = HexColor('#CCCCCC')          # gris para líneas
COLOR_ESTADO_OK = HexColor('#085041')      # verde para "activo"
COLOR_ESTADO_OK_FONDO = HexColor('#E1F5EE')
COLOR_ESTADO_WARN = HexColor('#854F0B')    # ambar para "retirado"
COLOR_ESTADO_WARN_FONDO = HexColor('#FAEEDA')
COLOR_ESTADO_REP = HexColor('#993556')     # rojo suave para "reprobado"


def _logo_image_from_base64(logo_b64: str, max_width=0.8*inch, max_height=0.8*inch):
    """
    Convierte un string base64 (con o sin prefijo data:image/...) en un Image
    de reportlab. Devuelve None si el base64 es inválido o vacío.
    
    Usado para incrustar el logo del colegio en el encabezado de los PDFs.
    """
    if not logo_b64:
        return None
    try:
        # Quitar prefijo "data:image/png;base64," si viene del frontend
        if ',' in logo_b64:
            logo_b64 = logo_b64.split(',', 1)[1]
        raw = base64.b64decode(logo_b64)
        img_io = io.BytesIO(raw)
        img = Image(img_io, width=max_width, height=max_height, kind='proportional')
        return img
    except Exception:
        return None


def datos_colegio_para_header(config, colegio):
    """
    Devuelve un dict con los datos del colegio para el encabezado de PDF.
    Centraliza la lógica de fallback: si falta algún campo, se omite limpiamente.
    """
    return {
        'nombre': (config.nombre if config else None) or (colegio.nombre if colegio else 'Centro Educativo'),
        'rnc': getattr(config, 'rnc', None) if config else None,
        'direccion': getattr(config, 'direccion', None) if config else None,
        'telefono': getattr(config, 'telefono', None) if config else None,
        'email': getattr(config, 'email', None) if config else None,
        'logo_b64': getattr(config, 'logo', None) if config else None,
    }


def dibujar_encabezado(c: canvas.Canvas, datos: dict, ancho_pagina: float,
                        y_inicio: float, ano_escolar: str = None, titulo_seccion: str = None):
    """
    Dibuja el encabezado estándar en el PDF.
    
    Layout:
      [LOGO] [NOMBRE COLEGIO            ]  [Año escolar]
             [RNC | dirección | tel | email]  [Emitido: fecha]
      ────────────────────────────────────────────────────────
                          [TÍTULO SECCIÓN]
    
    Devuelve la coordenada Y donde puede continuar el contenido.
    """
    margen_izq = 0.5 * inch
    margen_der = 0.5 * inch
    y = y_inicio
    
    # Logo (si hay)
    logo_x = margen_izq
    text_x = margen_izq
    logo = _logo_image_from_base64(datos.get('logo_b64'))
    if logo:
        # Dibujar logo a la izquierda
        logo.drawHeight = 0.8 * inch
        logo.drawWidth = 0.8 * inch
        logo.drawOn(c, logo_x, y - 0.8*inch)
        text_x = logo_x + 0.95 * inch
    
    # Etiqueta MINERD pequeña
    c.setFont('Helvetica-Bold', 8)
    c.setFillColor(COLOR_PRIMARIO)
    c.drawString(text_x, y - 0.12*inch, "REPÚBLICA DOMINICANA · MINERD")
    
    # Nombre del colegio
    c.setFont('Helvetica-Bold', 14)
    c.setFillColor(black)
    c.drawString(text_x, y - 0.30*inch, datos['nombre'])
    
    # Línea de datos: RNC | dirección | tel | email
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
    
    c.setFont('Helvetica', 9)
    c.setFillColor(COLOR_SECUNDARIO)
    if linea_datos:
        c.drawString(text_x, y - 0.45*inch, linea_datos[:120])
    
    # Lado derecho: año escolar y fecha de emisión
    fecha_hoy = datetime.now().strftime('%d/%m/%Y')
    c.setFont('Helvetica', 9)
    c.setFillColor(COLOR_SECUNDARIO)
    if ano_escolar:
        c.drawRightString(ancho_pagina - margen_der, y - 0.12*inch, f"Año escolar {ano_escolar}")
    c.drawRightString(ancho_pagina - margen_der, y - 0.28*inch, f"Emitido: {fecha_hoy}")
    
    # Línea separadora
    y_linea = y - 0.65 * inch
    c.setStrokeColor(COLOR_BORDE)
    c.setLineWidth(0.5)
    c.line(margen_izq, y_linea, ancho_pagina - margen_der, y_linea)
    
    # Título de sección (si hay)
    if titulo_seccion:
        c.setFont('Helvetica-Bold', 14)
        c.setFillColor(black)
        c.drawCentredString(ancho_pagina / 2, y_linea - 0.30*inch, titulo_seccion)
        return y_linea - 0.55 * inch
    
    return y_linea - 0.15 * inch


def dibujar_pie_firmas(c: canvas.Canvas, ancho_pagina: float, y: float, etiquetas=None):
    """
    Dibuja líneas de firma al pie del PDF.
    
    etiquetas: lista de strings para cada firma (default: ["Profesor titular", "Dirección"])
    """
    if etiquetas is None:
        etiquetas = ["Profesor titular", "Dirección"]
    
    margen_izq = 0.5 * inch
    margen_der = 0.5 * inch
    ancho_util = ancho_pagina - margen_izq - margen_der
    n = len(etiquetas)
    ancho_firma = min(2.2 * inch, ancho_util / n - 0.2*inch)
    
    c.setStrokeColor(black)
    c.setLineWidth(0.5)
    c.setFont('Helvetica', 9)
    c.setFillColor(black)
    
    for i, etiqueta in enumerate(etiquetas):
        # Distribuir uniformemente
        if n == 1:
            x_centro = ancho_pagina / 2
        else:
            x_centro = margen_izq + (ancho_util / (n - 1)) * i if n > 1 else ancho_pagina / 2
            # Ajuste para que no se peguen al borde
            if i == 0:
                x_centro = margen_izq + ancho_firma / 2
            elif i == n - 1:
                x_centro = ancho_pagina - margen_der - ancho_firma / 2
        
        x_inicio = x_centro - ancho_firma / 2
        x_fin = x_centro + ancho_firma / 2
        c.line(x_inicio, y, x_fin, y)
        c.drawCentredString(x_centro, y - 0.18*inch, etiqueta)


def dibujar_badge(c: canvas.Canvas, x: float, y: float, texto: str,
                   color_fondo, color_texto, padding=4, font_size=8):
    """
    Dibuja un badge pequeño con texto centrado. Útil para "Activo", "Retirado", etc.
    """
    c.setFont('Helvetica-Bold', font_size)
    ancho_texto = stringWidth(texto, 'Helvetica-Bold', font_size)
    ancho_badge = ancho_texto + 2 * padding
    alto_badge = font_size + 4
    
    c.setFillColor(color_fondo)
    c.roundRect(x, y, ancho_badge, alto_badge, 3, stroke=0, fill=1)
    
    c.setFillColor(color_texto)
    c.drawString(x + padding, y + 3, texto)
    
    return ancho_badge  # devolver el ancho para que el caller pueda continuar


def formato_fecha_corto(fecha) -> str:
    """Formato dd/mm/yyyy para mostrar en PDFs."""
    if not fecha:
        return ''
    if hasattr(fecha, 'strftime'):
        return fecha.strftime('%d/%m/%Y')
    return str(fecha)


def calcular_edad(fecha_nacimiento) -> int:
    """Calcula edad en años a partir de fecha de nacimiento."""
    if not fecha_nacimiento:
        return None
    if isinstance(fecha_nacimiento, str):
        try:
            fecha_nacimiento = datetime.strptime(fecha_nacimiento, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return None
    hoy = datetime.now().date()
    return hoy.year - fecha_nacimiento.year - (
        (hoy.month, hoy.day) < (fecha_nacimiento.month, fecha_nacimiento.day)
    )


def padre_tutor_principal(estudiante) -> str:
    """
    Retorna el contacto principal según Opción 1 (fallback):
    tutor → padre → madre → "(sin datos)"
    
    NOTA: el campo del modelo se llama 'tutor' (no 'nombre_tutor').
    """
    nombre_tutor = getattr(estudiante, 'tutor', None)
    if nombre_tutor:
        return nombre_tutor
    nombre_padre = getattr(estudiante, 'nombre_padre', None)
    if nombre_padre:
        return nombre_padre
    nombre_madre = getattr(estudiante, 'nombre_madre', None)
    if nombre_madre:
        return nombre_madre
    return "(sin datos)"


def safe_filename_ascii(nombre: str, default: str = "documento.pdf") -> str:
    """
    Sanitiza un nombre de archivo para que sea seguro en el header Content-Disposition.
    
    Los headers HTTP usan latin-1 por defecto; si pasamos UTF-8 (ñ, á, etc.) starlette
    crashea con UnicodeDecodeError. Convertimos a ASCII reemplazando acentos por sus
    versiones planas y descartando lo que no sea alfanumérico, '_', '-' o '.'.
    """
    import unicodedata
    if not nombre:
        return default
    # Descomponer acentos (NFD) y quedarnos solo con caracteres ASCII.
    # "Ñoño" → "Nono", "Pérez" → "Perez"
    nfkd = unicodedata.normalize('NFKD', nombre)
    sin_acentos = ''.join(c for c in nfkd if not unicodedata.combining(c))
    # Reemplazar espacios y caracteres raros por _
    seguro = ''.join(c if (c.isalnum() or c in '_-.') else '_' for c in sin_acentos)
    # Sin guiones bajos consecutivos
    while '__' in seguro:
        seguro = seguro.replace('__', '_')
    seguro = seguro.strip('_.')
    return seguro or default
