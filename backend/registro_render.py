"""
registro_render.py
==================
Render de la matriz de asistencia sobre PDF MINERD con coordenadas EXACTAS.

Cada celda se dibuja en posición calculada: x = base_x + col * spacing_x
                                              y = base_y - row * spacing_y

Tinta azul lapicero (RGB 0, 0, 0.8) — Helvetica-Oblique como fallback.
Logs de cada draw para auditoría de coordenadas.
"""

import io
from typing import List, Dict, Optional
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from pypdf import PdfReader, PdfWriter


# Color oficial
AZUL_LAPICERO = (0, 0, 0.8)

# Fuentes en orden de preferencia (intenta manuscrita, cae a oblique)
FUENTES_PREFERIDAS = ['SegoeScript', 'Bradley Hand ITC', 'Helvetica-Oblique', 'Helvetica']


def _seleccionar_fuente(c: canvas.Canvas) -> str:
    """Intenta usar una fuente manuscrita. Si no está disponible, Helvetica-Oblique."""
    from reportlab.pdfbase.pdfmetrics import getRegisteredFontNames
    disponibles = getRegisteredFontNames()
    for f in FUENTES_PREFERIDAS:
        if f in disponibles:
            return f
    return 'Helvetica-Oblique'


class CoordLogger:
    """Acumula logs de cada operación de dibujo para auditoría."""
    
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.entries: List[Dict] = []
    
    def log(self, valor: str, x: float, y: float, contexto: str = ''):
        if not self.enabled:
            return
        entry = {
            'valor': str(valor),
            'x': round(x, 1),
            'y': round(y, 1),
            'contexto': contexto,
        }
        self.entries.append(entry)
        print(f"Draw '{valor}' en ({x:.1f}, {y:.1f})  [{contexto}]")
    
    def summary(self) -> Dict:
        return {
            'total_draws': len(self.entries),
            'por_contexto': self._por_contexto(),
        }
    
    def _por_contexto(self) -> Dict[str, int]:
        out = {}
        for e in self.entries:
            out[e['contexto']] = out.get(e['contexto'], 0) + 1
        return out


# ============================================================
# COORDENADAS DE REFERENCIA
# Estas son las coordenadas base para una página de asistencia
# MINERD secundaria. En producción, se calibran página por página.
# ============================================================

COORDS_ASISTENCIA_SEC = {
    # Tabla de asistencia del Registro MINERD Secundaria
    # Formato: PDF letter (612 x 792)
    'base_x_dias': 120,        # X donde empieza la columna del día 1
    'base_y_dias_header': 680, # Y del header con números de día
    'spacing_x_dia': 15,       # Ancho de cada columna de día
    
    'base_x_valor': 120,       # X donde empieza la primera columna de valores
    'base_y_valor': 660,       # Y de la primera fila de valores
    'spacing_y_fila': 16,      # Alto de cada fila de estudiante
    
    'x_total_P': 450,           # X de la columna TOTAL PRESENTES
    'x_porcentaje': 490,        # X de la columna PORCENTAJE
    
    'tamanio_fuente_dia': 7,
    'tamanio_fuente_valor': 8,
}


def draw_asistencia_overlay(
    c: canvas.Canvas,
    matriz_mes: Dict,
    coords: Dict = None,
    logger: Optional[CoordLogger] = None,
    fuente: Optional[str] = None,
):
    """
    Dibuja la asistencia de UN MES en el overlay.
    
    Args:
        c: canvas de ReportLab
        matriz_mes: un dict del array devuelto por build_asistencia_registro
        coords: dict con coordenadas base (default: COORDS_ASISTENCIA_SEC)
        logger: opcional CoordLogger para registrar cada draw
        fuente: nombre de fuente a usar
    """
    coords = coords or COORDS_ASISTENCIA_SEC
    logger = logger or CoordLogger(enabled=False)
    
    # Configurar tinta
    c.setFillColorRGB(*AZUL_LAPICERO)
    
    if not fuente:
        fuente = _seleccionar_fuente(c)
    
    dias = matriz_mes.get('dias', [])
    filas = matriz_mes.get('filas', [])
    
    # === HEADER: números de día ===
    c.setFont(fuente, coords['tamanio_fuente_dia'])
    for col, dia in enumerate(dias):
        x = coords['base_x_dias'] + col * coords['spacing_x_dia']
        y = coords['base_y_dias_header']
        c.drawString(x, y, str(dia))
        logger.log(str(dia), x, y, 'header_dia')
    
    # === FILAS DE ESTUDIANTES ===
    c.setFont(fuente, coords['tamanio_fuente_valor'])
    for row, fila in enumerate(filas):
        y = coords['base_y_valor'] - row * coords['spacing_y_fila']
        
        for col, valor in enumerate(fila['valores']):
            if not valor:
                continue
            x = coords['base_x_valor'] + col * coords['spacing_x_dia']
            c.drawString(x, y, valor)
            logger.log(valor, x, y, f'est_{fila["no"]}_dia_{dias[col]}')
        
        # Total presentes
        x_total = coords['x_total_P']
        c.drawString(x_total, y, str(fila['presentes']))
        logger.log(str(fila['presentes']), x_total, y, f'total_presentes_est_{fila["no"]}')
        
        # Porcentaje
        x_pct = coords['x_porcentaje']
        c.drawString(x_pct, y, f"{fila['porcentaje']:.0f}")
        logger.log(f"{fila['porcentaje']:.0f}", x_pct, y, f'pct_est_{fila["no"]}')


def render_asistencia_standalone_pdf(
    matriz: List[Dict],
    output_buf: Optional[io.BytesIO] = None,
    logger: Optional[CoordLogger] = None,
) -> bytes:
    """
    Genera un PDF standalone (sin overlay MINERD) con toda la matriz de asistencia.
    Útil para debug o para colegios que no quieran usar el PDF oficial.
    """
    buf = output_buf or io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    logger = logger or CoordLogger(enabled=True)
    fuente = _seleccionar_fuente(c)
    
    for mes_data in matriz:
        # Título del mes
        c.setFillColorRGB(0, 0, 0)
        c.setFont('Helvetica-Bold', 14)
        c.drawString(50, 750, f"Asistencia — {mes_data['mes'].upper()}")
        logger.log(mes_data['mes'], 50, 750, 'titulo_mes')
        
        # Render de la matriz con el layout standalone
        coords_standalone = {
            'base_x_dias': 100,
            'base_y_dias_header': 720,
            'spacing_x_dia': 18,
            'base_x_valor': 100,
            'base_y_valor': 700,
            'spacing_y_fila': 18,
            'x_total_P': 500,
            'x_porcentaje': 540,
            'tamanio_fuente_dia': 9,
            'tamanio_fuente_valor': 10,
        }
        
        # Header "No. | Nombre" 
        c.setFillColorRGB(0, 0, 0)
        c.setFont('Helvetica-Bold', 8)
        c.drawString(50, 720, 'No.')
        c.drawString(70, 720, 'Nombre')
        c.drawString(500, 720, 'P')
        c.drawString(540, 720, '%')
        
        # Nombres de estudiantes
        c.setFillColorRGB(0, 0, 0)
        c.setFont('Helvetica', 8)
        for row, fila in enumerate(mes_data['filas']):
            y = coords_standalone['base_y_valor'] - row * coords_standalone['spacing_y_fila']
            c.drawString(50, y, str(fila['no']))
            c.drawString(70, y, fila['nombre'][:35])
        
        # Asistencia con tinta azul
        draw_asistencia_overlay(c, mes_data, coords_standalone, logger, fuente)
        
        c.showPage()
    
    c.save()
    buf.seek(0)
    return buf.getvalue()
