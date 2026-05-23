"""
PDF: Lista de estudiantes por curso.

Genera un PDF imprimible con:
- Encabezado del colegio (logo, nombre, RNC, dirección)
- Título: "Lista de estudiantes — [curso] [tanda]"
- Tabla con: #, Apellido, Nombre, Sexo, Edad, Matrícula, Estado
- Pie con totales y firmas

Quién puede generar:
- Dirección, Coordinador, Psicología, Secretaría → cualquier curso del colegio
- Profesor → solo cursos donde tiene asignación activa
"""
import io
from reportlab.lib.pagesizes import letter
from reportlab.lib.colors import HexColor, black, white
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.pdfbase.pdfmetrics import stringWidth

from pdf_helpers import (
    COLOR_PRIMARIO, COLOR_SECUNDARIO, COLOR_TEXTO, COLOR_BORDE,
    COLOR_ESTADO_OK, COLOR_ESTADO_OK_FONDO,
    COLOR_ESTADO_WARN, COLOR_ESTADO_WARN_FONDO,
    datos_colegio_para_header, dibujar_encabezado, dibujar_pie_firmas,
    dibujar_badge, formato_fecha_corto, calcular_edad,
)


def generar_lista_estudiantes_pdf(estudiantes, curso, tanda, grado, config, colegio,
                                    ano_escolar: str = None) -> bytes:
    """
    Genera el PDF en memoria y devuelve los bytes.
    
    estudiantes: lista de objetos Estudiante (ya filtrados por curso + permisos)
    curso, tanda, grado: objetos del modelo
    config, colegio: ConfiguracionColegio + Colegio para datos de encabezado
    ano_escolar: string "2026-2027" (opcional)
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    ancho, alto = letter
    
    datos = datos_colegio_para_header(config, colegio)
    
    # Encabezado
    y = dibujar_encabezado(c, datos, ancho, alto - 0.4*inch,
                            ano_escolar=ano_escolar,
                            titulo_seccion="Lista de estudiantes")
    
    # Subtítulo del curso/tanda
    grado_nombre = getattr(grado, 'nombre', '') if grado else ''
    curso_nombre = getattr(curso, 'nombre', '') if curso else ''
    tanda_nombre = getattr(tanda, 'nombre', '') if tanda else ''
    subtitulo = f"{grado_nombre} {curso_nombre} · Tanda {tanda_nombre}".strip()
    
    c.setFont('Helvetica', 11)
    c.setFillColor(HexColor('#444444'))
    c.drawCentredString(ancho / 2, y, subtitulo)
    y -= 0.35 * inch
    
    # Tabla — encabezado
    margen_izq = 0.5 * inch
    margen_der = 0.5 * inch
    ancho_util = ancho - margen_izq - margen_der
    
    # Columnas y anchos (proporciones)
    columnas = [
        ('#', 0.30 * inch, 'center'),
        ('Apellido', 1.50 * inch, 'left'),
        ('Nombre', 1.50 * inch, 'left'),
        ('Sexo', 0.45 * inch, 'center'),
        ('Edad', 0.45 * inch, 'center'),
        ('Matrícula', 1.10 * inch, 'left'),
        ('Estado', 1.40 * inch, 'left'),
    ]
    
    # Fondo encabezado
    c.setFillColor(HexColor('#F0F0F0'))
    c.rect(margen_izq, y - 0.05*inch, ancho_util, 0.30*inch, stroke=0, fill=1)
    
    # Texto encabezado
    c.setFont('Helvetica-Bold', 9)
    c.setFillColor(black)
    x = margen_izq + 0.06*inch
    for label, w, align in columnas:
        if align == 'center':
            c.drawCentredString(x + w/2, y + 0.10*inch, label)
        else:
            c.drawString(x, y + 0.10*inch, label)
        x += w
    
    # Línea bajo encabezado
    c.setStrokeColor(HexColor('#999999'))
    c.setLineWidth(0.5)
    c.line(margen_izq, y - 0.05*inch, ancho - margen_der, y - 0.05*inch)
    y -= 0.30 * inch
    
    # Filas de estudiantes
    c.setFont('Helvetica', 9)
    c.setFillColor(COLOR_TEXTO)
    activos = 0
    retirados = 0
    
    for i, est in enumerate(estudiantes, start=1):
        # Salto de página si nos quedamos sin espacio
        if y < 1.5 * inch:
            # Pie de página simple
            c.setFont('Helvetica', 8)
            c.setFillColor(COLOR_SECUNDARIO)
            c.drawString(margen_izq, 0.5*inch, f"Página {c.getPageNumber()}")
            c.showPage()
            y = alto - 0.6*inch
            c.setFont('Helvetica', 9)
            c.setFillColor(COLOR_TEXTO)
        
        retirado = bool(getattr(est, 'fecha_retiro', None))
        if retirado:
            retirados += 1
        else:
            activos += 1
        
        x = margen_izq + 0.06*inch
        # #
        c.setFillColor(COLOR_TEXTO)
        c.drawCentredString(x + columnas[0][1]/2 - 0.06*inch, y + 0.05*inch, str(i))
        x += columnas[0][1]
        # Apellido
        apellido = (est.apellido or '')[:30]
        c.drawString(x, y + 0.05*inch, apellido)
        x += columnas[1][1]
        # Nombre
        nombre = (est.nombre or '')[:30]
        c.drawString(x, y + 0.05*inch, nombre)
        x += columnas[2][1]
        # Sexo
        sexo = (est.sexo or '')[:1].upper() if est.sexo else ''
        c.drawCentredString(x + columnas[3][1]/2 - 0.06*inch, y + 0.05*inch, sexo)
        x += columnas[3][1]
        # Edad
        edad = calcular_edad(est.fecha_nacimiento)
        c.drawCentredString(x + columnas[4][1]/2 - 0.06*inch, y + 0.05*inch,
                            str(edad) if edad is not None else '—')
        x += columnas[4][1]
        # Matrícula
        matricula = (est.matricula or '—')[:12]
        c.drawString(x, y + 0.05*inch, matricula)
        x += columnas[5][1]
        # Estado (badge)
        if retirado:
            fecha_ret = formato_fecha_corto(est.fecha_retiro)
            dibujar_badge(c, x, y + 0.02*inch,
                          f"Retirado {fecha_ret[:5]}",
                          COLOR_ESTADO_WARN_FONDO, COLOR_ESTADO_WARN,
                          font_size=7)
        else:
            dibujar_badge(c, x, y + 0.02*inch, "Activo",
                          COLOR_ESTADO_OK_FONDO, COLOR_ESTADO_OK,
                          font_size=7)
        
        # Línea separadora suave
        c.setStrokeColor(HexColor('#EEEEEE'))
        c.setLineWidth(0.3)
        c.line(margen_izq, y - 0.04*inch, ancho - margen_der, y - 0.04*inch)
        
        c.setFont('Helvetica', 9)
        c.setFillColor(COLOR_TEXTO)
        y -= 0.28 * inch
    
    # Pie con totales
    y -= 0.15 * inch
    c.setFont('Helvetica', 8)
    c.setFillColor(COLOR_SECUNDARIO)
    total = len(estudiantes)
    c.drawString(margen_izq, y,
                  f"Total: {total} estudiantes · Activos: {activos} · Retirados: {retirados}")
    c.drawRightString(ancho - margen_der, y, f"Página {c.getPageNumber()}")
    
    # Firmas
    y_firmas = max(y - 1.2*inch, 1.0*inch)
    dibujar_pie_firmas(c, ancho, y_firmas,
                        etiquetas=["Profesor titular", "Dirección"])
    
    c.save()
    return buf.getvalue()
