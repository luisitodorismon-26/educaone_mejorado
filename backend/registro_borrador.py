"""
registro_borrador.py
====================
Aplica marca de agua "BORRADOR" diagonal a un PDF para distinguir
las vistas previas de los registros oficiales.
"""

import io
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter


def _crear_overlay_borrador(width: float = 612, height: float = 792) -> io.BytesIO:
    """Crea un overlay PDF con la palabra BORRADOR diagonal en gris claro."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, height))
    
    # Texto diagonal grande, gris muy claro
    c.saveState()
    c.translate(width / 2, height / 2)
    c.rotate(45)
    c.setFillColorRGB(0.85, 0.85, 0.85, alpha=0.4)
    c.setFont("Helvetica-Bold", 100)
    
    # Múltiples líneas para cubrir toda la diagonal
    for offset in [-200, 0, 200]:
        c.drawCentredString(0, offset, "BORRADOR")
    
    c.restoreState()
    
    # Etiqueta esquina superior derecha
    c.saveState()
    c.setFillColorRGB(0.6, 0, 0)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(width - 180, height - 25, "VISTA PREVIA — NO OFICIAL")
    c.restoreState()
    
    c.showPage()
    c.save()
    buf.seek(0)
    return buf


def aplicar_marca_borrador(pdf_bytes: bytes) -> bytes:
    """
    Aplica marca de agua 'BORRADOR' a todas las páginas de un PDF.
    
    Args:
        pdf_bytes: bytes del PDF original
    Returns:
        bytes del PDF con marca de agua
    """
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    
    for page in reader.pages:
        # Crear overlay del tamaño exacto de cada página
        w = float(page.mediabox.width)
        h = float(page.mediabox.height)
        overlay_buf = _crear_overlay_borrador(w, h)
        overlay_reader = PdfReader(overlay_buf)
        overlay_page = overlay_reader.pages[0]
        
        page.merge_page(overlay_page)
        writer.add_page(page)
    
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()
