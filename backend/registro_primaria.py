"""
registro_primaria.py - Generador Registro Escolar MINERD Nivel Primario
========================================================================
Llena los PDFs oficiales del MINERD (1ro-6to Primaria) con overlay de datos
desde el sistema: portada, estudiantes, asistencia por mes, calificaciones
por competencia (C1, C2, C3) por período.

Color tinta azul lapicero (RGB 0, 0, 0.7) — formato MINERD.

Autor: EducaOne
"""

import io
import os
from datetime import date
from typing import Dict, List, Optional, Any
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from pypdf import PdfReader, PdfWriter

# Color tinta azul
AZUL_TINTA = (0, 0, 0.7)

# Áreas MINERD primaria (orden oficial)
AREAS_PRIMER_CICLO = [   # 1ro-3ro
    "Lengua Española",
    "Matemática",
    "Ciencias Sociales",
    "Ciencias de la Naturaleza",
    "Educación Física",
    "Educación Artística",
    "Formación Integral Humana y Religiosa",
    "Lenguas Extranjeras",  # solo 2do-3ro
]

AREAS_SEGUNDO_CICLO = [  # 4to-6to
    "Lengua Española",
    "Matemática",
    "Ciencias Sociales",
    "Ciencias de la Naturaleza",
    "Lenguas Extranjeras - Inglés",
    "Educación Física",
    "Educación Artística",
    "Formación Integral Humana y Religiosa",
    "Talleres Optativos",
]


def get_areas_por_grado(grado_numero: int) -> List[str]:
    """Devuelve la lista de áreas según el grado (ciclo MINERD)."""
    if grado_numero <= 3:
        return AREAS_PRIMER_CICLO
    return AREAS_SEGUNDO_CICLO


def get_template_path(grado_numero: int) -> str:
    """Ruta al template PDF MINERD del grado."""
    nombres = {
        1: "Registro-1er-Grado-Primaria.pdf",
        2: "Registro-2do-Grado-Primaria.pdf",
        3: "Registro-3er-Grado-Primaria.pdf",
        4: "Registro-4to-Grado-Primaria.pdf",
        5: "Registro-5to-Grado-Primaria.pdf",
        6: "Registro-6to-Grado-Primaria.pdf",
    }
    fname = nombres.get(grado_numero)
    if not fname:
        raise ValueError(f"Grado {grado_numero} inválido para primaria (debe ser 1-6)")
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_dir, "templates", "registro_escolar", "primaria", fname)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Template primaria no encontrada: {path}")
    return path


def _draw_text(c: canvas.Canvas, x: float, y: float, texto: str, size: int = 10):
    """Dibuja texto en el overlay con color azul tinta."""
    c.setFillColorRGB(*AZUL_TINTA)
    c.setFont("Helvetica", size)
    c.drawString(x, y, str(texto) if texto else "")


def _create_overlay_page(draw_func, page_size=letter) -> io.BytesIO:
    """Crea una página de overlay y devuelve su buffer."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=page_size)
    draw_func(c)
    c.showPage()
    c.save()
    buf.seek(0)
    return buf


def generar_registro_primaria(
    grado_numero: int,
    datos_centro: Dict,
    datos_portada: Dict,
    estudiantes: List[Dict],
    calificaciones_data: Optional[Dict] = None,
    asistencia_data: Optional[Dict] = None,
    dias_trabajados: Optional[Dict] = None,
) -> bytes:
    """
    Genera el Registro Escolar Primaria MINERD.
    
    Args:
        grado_numero: 1-6
        datos_centro: {nombre, regional, distrito, codigo_centro, ...}
        datos_portada: {anio_inicio, anio_fin, seccion, tanda}
        estudiantes: [{nombre, sexo, fecha_nacimiento, ...}] hasta 40
        calificaciones_data: {area_nombre: {estudiante_idx: {c1_p1, c2_p2, cf, ...}}}
        asistencia_data: {mes_nombre: {estudiante_idx: {dia: estado}}}
        dias_trabajados: {mes_nombre: int}
    
    Returns:
        bytes del PDF final
    """
    template_path = get_template_path(grado_numero)
    reader = PdfReader(template_path)
    writer = PdfWriter()
    
    # === Crear overlays por página ===
    # Esta implementación sigue siendo aproximada visualmente, pero ya integra:
    # - Portada
    # - Dos páginas de estudiantes
    # - Resumen de asistencia esperado vs capturado
    # - Resumen de calificaciones finales por estudiante
    
    # Overlay para portada (página 2 del PDF MINERD primaria)
    # Coordenadas medidas del PDF original:
    # Líneas (donde escribir): Centro=531, Código=565, Grado=601, Regional=638
    # Para que el texto descanse SOBRE la línea, y_canvas = 792 - line_y - 1
    def draw_portada(c):
        # Centro Educativo (línea en y_top=531)
        _draw_text(c, 165, 792 - 530, datos_centro.get('nombre', ''), 10)
        
        # Código (línea en y_top=565)
        _draw_text(c, 115, 792 - 564, datos_centro.get('codigo_centro', ''), 10)
        
        # Año Escolar — primer "20" termina x≈396, segundo "20" termina x≈491
        # Las líneas están en x=401-457 (1er) y x=497-558 (2do)
        _draw_text(c, 415, 792 - 564, datos_portada.get('anio_inicio', ''), 10)
        _draw_text(c, 510, 792 - 564, datos_portada.get('anio_fin', ''), 10)
        
        # Grado (línea en y_top=601, x=104-225)
        _draw_text(c, 110, 792 - 600, f"{grado_numero}°", 10)
        
        # Sección (línea en y_top=601, x=297-408)
        _draw_text(c, 305, 792 - 600, datos_portada.get('seccion', 'A'), 10)
        
        # Tanda (línea en y_top=601, x=468-558)
        _draw_text(c, 475, 792 - 600, datos_portada.get('tanda', ''), 10)
        
        # Regional de Educación (línea en y_top=638, x=225-328)
        _draw_text(c, 232, 792 - 637, datos_centro.get('regional', ''), 10)
        
        # Distrito Educativo (línea en y_top=638, x=474-558)
        _draw_text(c, 481, 792 - 637, datos_centro.get('distrito', ''), 10)
    
    def draw_estudiantes_page(start_idx: int):
        def draw(c):
            y_start = 600
            y_delta = 18
            subset = estudiantes[start_idx:start_idx + 20]
            for local_idx, est in enumerate(subset):
                y = y_start - (local_idx * y_delta)
                numero = est.get('no_lista', start_idx + local_idx + 1)
                _draw_text(c, 50, y, str(numero), 8)
                _draw_text(c, 80, y, est.get('nombre', ''), 8)
                _draw_text(c, 280, y, est.get('sexo', ''), 8)
                fn = est.get('fecha_nacimiento')
                if fn:
                    _draw_text(c, 320, y, str(fn)[:10], 8)
        return draw

    def draw_asistencia_resumen(c):
        _draw_text(c, 50, 720, "RESUMEN DE ASISTENCIA", 11)
        y = 695
        meses_cfg = dias_trabajados or {}
        _draw_text(c, 50, y, "Dias trabajados configurados por mes:", 9)
        y -= 16
        if meses_cfg:
            for mes, valor in meses_cfg.items():
                _draw_text(c, 60, y, f"{str(mes).upper()}: {valor}", 8)
                y -= 13
        else:
            _draw_text(c, 60, y, "No hay dias trabajados configurados", 8)
            y -= 13

        y -= 8
        _draw_text(c, 50, y, "Cobertura detectada por mes:", 9)
        y -= 16
        for mes_data in (asistencia_data or [])[:10]:
            linea = (
                f"{str(mes_data.get('mes', '')).upper()} | "
                f"dias={mes_data.get('total_dias', 0)} | "
                f"cfg={mes_data.get('dias_trabajados_configurados', 0)} | "
                f"cobertura={mes_data.get('cobertura_registro_pct', 0)}%"
            )
            _draw_text(c, 60, y, linea, 8)
            y -= 13
            if y < 80:
                break

    def draw_calificaciones_resumen(c):
        _draw_text(c, 50, 720, "RESUMEN DE CALIFICACIONES", 11)
        areas = list((calificaciones_data or {}).keys())
        if not areas:
            _draw_text(c, 50, 700, "No hay calificaciones para imprimir", 9)
            return

        headers = ["No", "Estudiante"] + [a[:14] for a in areas[:4]]
        x_positions = [45, 75, 275, 370, 465, 550]
        y = 695
        for idx, header in enumerate(headers[:len(x_positions)]):
            _draw_text(c, x_positions[idx], y, header, 8)
        y -= 16

        for idx, est in enumerate(estudiantes[:22]):
            _draw_text(c, x_positions[0], y, str(est.get('no_lista', idx + 1)), 7)
            _draw_text(c, x_positions[1], y, est.get('nombre', '')[:28], 7)
            for area_idx, area in enumerate(areas[:4], start=2):
                valor_area = ""
                area_data = (calificaciones_data or {}).get(area, {})
                competencias = area_data.get(idx, {})
                finales = [
                    comp_data.get('final_competencia')
                    for comp_data in competencias.values()
                    if isinstance(comp_data, dict) and comp_data.get('final_competencia') is not None
                ]
                if finales:
                    valor_area = f"{round(sum(finales) / len(finales), 1)}"
                _draw_text(c, x_positions[area_idx], y, valor_area, 7)
            y -= 13
            if y < 70:
                break
    
    # Procesar cada página del template
    for pg_idx in range(len(reader.pages)):
        page = reader.pages[pg_idx]
        
        # Aplicar overlay según página
        overlay_buf = None
        if pg_idx == 1:  # Portada (página 2 del PDF)
            overlay_buf = _create_overlay_page(draw_portada)
        elif pg_idx == 10:
            overlay_buf = _create_overlay_page(draw_estudiantes_page(0))
        elif pg_idx == 11:
            overlay_buf = _create_overlay_page(draw_estudiantes_page(20))
        elif pg_idx == 12:
            overlay_buf = _create_overlay_page(draw_asistencia_resumen)
        elif pg_idx == 13:
            overlay_buf = _create_overlay_page(draw_calificaciones_resumen)
        
        if overlay_buf:
            overlay_reader = PdfReader(overlay_buf)
            overlay_page = overlay_reader.pages[0]
            page.merge_page(overlay_page)
        
        writer.add_page(page)
    
    # Escribir resultado
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def generar_registro_primaria_desde_sistema(
    colegio_info: Dict,
    curso_info: Dict,
    ano_escolar: str,
    estudiantes: List[Dict],
    calificaciones_por_area: Dict,
    asistencia_por_mes: List[Dict],
    dias_trabajados: Dict,
    grado_numero: int,
) -> bytes:
    """
    Wrapper que traduce datos del sistema al formato del generador.
    
    Args:
        colegio_info: datos del centro
        curso_info: {grado, seccion, tanda}
        ano_escolar: "2024-2025"
        estudiantes: lista del curso con {id, no_lista, nombre, sexo, fecha_nacimiento}
        calificaciones_por_area: {area_nombre: {estudiante_idx: {competencia_numero: {p1, p2, p3, p4, cf}}}}
        asistencia_por_mes: matriz mensual ya normalizada
        dias_trabajados: {'ago': int, 'sep': int, ...}
        grado_numero: 1-6
    """
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
        "codigo_cartografia": colegio_info.get('codigo_cartografia', ''),
        "direccion": colegio_info.get('direccion', ''),
        "director": colegio_info.get('director', ''),
        "docente": colegio_info.get('docente_titular', ''),
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
