"""
Generador de Boletín de Calificaciones - Formato MINERD
========================================================
Replica el formato oficial del boletín de calificaciones del MINERD
para Educación Secundaria (1er y 2do Ciclo).

Página 1: Portada con datos del centro y estudiante
Página 2: Tabla de calificaciones con estructura MINERD completa
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import inch, cm, mm
from reportlab.pdfgen import canvas
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from datetime import datetime, date
import io

PAGE_WIDTH, PAGE_HEIGHT = letter

# ========================================
# ASIGNATURAS OFICIALES MINERD
# ========================================

ASIGNATURAS_MINERD = [
    "Lengua Española",
    "Lenguas Extranjeras (Inglés)",
    "Lenguas Extranjeras (Francés)",
    "Matemática",
    "Ciencias Sociales",
    "Ciencias de la Naturaleza",
    "Educación Artística",
    "Educación Física",
    "Formación Integral Humana y Religiosa"
]

# Grados del 2do ciclo que incluyen "Salida Optativa"
GRADOS_CON_OPTATIVA = ['3ro', '3ero', '3er', '4to', '5to', '6to',
                        '3ro secundaria', '4to secundaria', '5to secundaria', '6to secundaria',
                        'tercero', 'cuarto', 'quinto', 'sexto']


def get_asignaturas_por_grado(grado_nombre):
    """Retorna la lista de asignaturas según el grado"""
    asigs = list(ASIGNATURAS_MINERD)
    if grado_nombre:
        grado_lower = grado_nombre.strip().lower()
        if any(g in grado_lower for g in GRADOS_CON_OPTATIVA):
            asigs.append("SALIDA OPTATIVA")
    return asigs

# Mapeo de nombres del sistema a nombres del boletín MINERD
MAPEO_ASIGNATURAS = {
    'lengua española': 'Lengua Española',
    'español': 'Lengua Española',
    'inglés': 'Lenguas Extranjeras (Inglés)',
    'ingles': 'Lenguas Extranjeras (Inglés)',
    'lenguas extranjeras: inglés': 'Lenguas Extranjeras (Inglés)',
    'lenguas extranjeras (inglés)': 'Lenguas Extranjeras (Inglés)',
    'francés': 'Lenguas Extranjeras (Francés)',
    'frances': 'Lenguas Extranjeras (Francés)',
    'lenguas extranjeras: francés': 'Lenguas Extranjeras (Francés)',
    'lenguas extranjeras (francés)': 'Lenguas Extranjeras (Francés)',
    'matemática': 'Matemática',
    'matematica': 'Matemática',
    'matemáticas': 'Matemática',
    'ciencias sociales': 'Ciencias Sociales',
    'sociales': 'Ciencias Sociales',
    'ciencias de la naturaleza': 'Ciencias de la Naturaleza',
    'ciencias naturales': 'Ciencias de la Naturaleza',
    'biología': 'Ciencias de la Naturaleza',
    'biologia': 'Ciencias de la Naturaleza',
    'educación artística': 'Educación Artística',
    'educacion artistica': 'Educación Artística',
    'artística': 'Educación Artística',
    'educación física': 'Educación Física',
    'educacion fisica': 'Educación Física',
    'física': 'Educación Física',
    'formación integral humana y religiosa': 'Formación Integral Humana y Religiosa',
    'formacion integral humana y religiosa': 'Formación Integral Humana y Religiosa',
    'fihr': 'Formación Integral Humana y Religiosa',
    'religión': 'Formación Integral Humana y Religiosa',
    'salida optativa': 'SALIDA OPTATIVA',
    'optativa': 'SALIDA OPTATIVA',
}

def normalizar_asignatura(nombre_sistema):
    """Convierte el nombre del sistema al nombre oficial MINERD"""
    nombre_lower = nombre_sistema.strip().lower()
    return MAPEO_ASIGNATURAS.get(nombre_lower, nombre_sistema)


def get_situacion_asignatura(cf):
    """Determina si aprobó o reprobó la asignatura"""
    if cf is None:
        return ''
    return 'A' if cf >= 70 else 'R'


def get_situacion_final(calificaciones_data):
    """Determina si el estudiante es Promovido o Repitente"""
    reprobadas = sum(1 for d in calificaciones_data if d.get('cf') and d['cf'] < 70)
    if reprobadas == 0:
        return 'Promovido/a'
    elif reprobadas <= 2:
        return 'Promovido/a con condiciones'
    return 'Repitente'


# ========================================
# PÁGINA 1: PORTADA
# ========================================

def dibujar_portada(c, config, estudiante, ano_escolar, curso, observaciones=''):
    """Dibuja la portada del boletín"""
    w, h = PAGE_WIDTH, PAGE_HEIGHT
    margin = 54
    
    # ---- Encabezado institucional ----
    c.setFont('Helvetica', 9)
    c.drawCentredString(w/2, h - 40, 'Viceministro de Servicios Técnicos y Pedagógicos')
    c.drawCentredString(w/2, h - 52, 'Dirección General de Educación Secundaria')
    
    c.setFont('Helvetica-Bold', 18)
    c.drawCentredString(w/2, h - 85, 'BOLETÍN DE CALIFICACIONES')
    
    # ---- Datos del año escolar ----
    y = h - 120
    c.setFont('Helvetica', 11)
    ano_nombre = ano_escolar.nombre if ano_escolar else '_______ _______'
    anos = ano_nombre.split('-') if '-' in str(ano_nombre) else [ano_nombre, '']
    c.drawString(margin, y, f'Año escolar: {ano_nombre}')
    c.line(margin + 85, y - 2, margin + 200, y - 2)
    
    # ---- Datos del estudiante ----
    y -= 30
    seccion = curso.seccion if hasattr(curso, 'seccion') and curso.seccion else (curso.nombre if curso else '')
    c.drawString(margin, y, f'Sección: {seccion}')
    c.drawString(w/2, y, f'Número de orden: {estudiante.no_lista or "___"}')
    
    y -= 25
    c.drawString(margin, y, 'Nombre (s):')
    c.drawString(margin + 80, y, f'{estudiante.nombre}')
    c.line(margin + 78, y - 2, w - margin, y - 2)
    y -= 25
    c.drawString(margin, y, 'Apellido (s):')
    c.drawString(margin + 85, y, f'{estudiante.apellido}')
    c.line(margin + 83, y - 2, w - margin, y - 2)
    y -= 25
    c.drawString(margin, y, f'ID estudiante (SIGERD): {estudiante.matricula or "___"}')
    
    # ---- Datos del docente ----
    y -= 30
    # Buscar el profesor encargado del curso
    docente_nombre = ''
    if hasattr(curso, 'asignaciones') and curso.asignaciones:
        for asig in curso.asignaciones:
            if asig.activo and asig.profesor:
                docente_nombre = asig.profesor.nombre_completo
                break
    c.drawString(margin, y, 'Docente:')
    c.drawString(margin + 55, y, f'{docente_nombre}')
    c.line(margin + 53, y - 2, w - margin, y - 2)
    
    # ---- Datos del centro educativo ----
    y -= 30
    c.drawString(margin, y, 'Centro educativo:')
    c.drawString(margin + 110, y, f'{config.nombre if config else ""}')
    c.line(margin + 108, y - 2, w - margin, y - 2)
    y -= 25
    c.drawString(margin, y, f'Código del centro: {config.distrito if config else "___"}')
    y -= 25
    tanda_nombre = ''
    if hasattr(curso, 'tanda') and curso.tanda:
        tanda_nombre = curso.tanda.nombre
    c.drawString(margin, y, f'Tanda: {tanda_nombre}')
    y -= 25
    c.drawString(margin, y, f'Teléfono del centro: {config.telefono if config else "___"}')
    y -= 25
    c.drawString(margin, y, f'Distrito educativo: {config.distrito if config else "___"}')
    y -= 25
    c.drawString(margin, y, f'Regional de educación: {config.regional if config else "___"}')
    y -= 25
    provincia = ''
    if config and config.direccion:
        # Intentar extraer provincia de la dirección
        provincia = config.direccion.split(',')[-1].strip() if ',' in config.direccion else config.direccion
    c.drawString(margin, y, f'Provincia: {provincia}')
    y -= 25
    c.drawString(margin, y, f'Municipio: ')
    
    # ---- Observaciones ----
    y -= 35
    c.setFont('Helvetica-Bold', 11)
    c.drawString(margin, y, 'Observaciones:')
    c.setFont('Helvetica', 10)
    y -= 5
    # Dibujar líneas para observaciones
    for i in range(8):
        y -= 18
        c.setStrokeColor(colors.Color(0.7, 0.7, 0.7))
        c.line(margin, y, w - margin, y)
    
    if observaciones:
        # Escribir observaciones sobre las líneas
        y_obs = y + 18 * 8 - 5
        for line in observaciones.split('\n')[:8]:
            c.drawString(margin + 5, y_obs, line[:80])
            y_obs -= 18
    
    # ---- Firma del padre ----
    y -= 30
    c.setFont('Helvetica-Bold', 10)
    c.drawString(margin, y, 'FIRMA DEL PADRE, MADRE O TUTOR')
    y -= 5
    c.setStrokeColor(colors.Color(0.7, 0.7, 0.7))
    c.line(margin, y, w/2, y)
    
    # ---- Períodos de Reportes ----
    y -= 35
    c.setFont('Helvetica-Bold', 11)
    c.drawString(margin, y, 'Períodos de Reportes de Calificaciones')
    c.setFont('Helvetica', 10)
    periodos = [
        'Ago – Sept – Oct',
        'Nov – Dic – Ene',
        'Feb – Mar',
        'Abr – May – Jun'
    ]
    for p in periodos:
        y -= 20
        c.drawString(margin, y, p)
        c.setStrokeColor(colors.Color(0.7, 0.7, 0.7))
        c.line(margin + 120, y - 2, w - margin, y - 2)


# ========================================
# PÁGINA 2: CALIFICACIONES (LANDSCAPE)
# ========================================

def dibujar_calificaciones(c, estudiante, curso, calificaciones_data, asistencia_data):
    """Dibuja la página de calificaciones en formato landscape"""
    # Usamos landscape
    w, h = PAGE_HEIGHT, PAGE_WIDTH  # Invertido para landscape
    margin_left = 28
    margin_top = 28
    
    # Determinar grado para saber si incluir Salida Optativa
    grado_nombre = ''
    if curso and hasattr(curso, 'grado') and curso.grado:
        grado_nombre = curso.grado.nombre
    elif curso and hasattr(curso, 'nombre'):
        grado_nombre = curso.nombre
    
    asignaturas_boletin = get_asignaturas_por_grado(grado_nombre)
    margin_left = 28
    margin_top = 28
    
    # ---- Encabezado ----
    c.setFont('Helvetica', 8)
    nombre_completo = f'{estudiante.nombre} {estudiante.apellido}'
    grado = ''
    if curso and hasattr(curso, 'grado') and curso.grado:
        grado = curso.grado.nombre
    seccion = curso.seccion if hasattr(curso, 'seccion') and curso.seccion else (curso.nombre if curso else '')
    
    c.drawString(margin_left, h - margin_top, f'Nombre(s) y apellido(s): {nombre_completo}')
    c.drawString(w/2 + 50, h - margin_top, f'Grado: {grado}')
    c.drawString(w - 200, h - margin_top, f'Sección: {seccion}')
    
    # ---- ENCABEZADO DE LA TABLA ----
    y_start = h - margin_top - 15
    
    # Definir columnas
    col_asignatura = 95  # Ancho de la columna de asignatura
    col_comp = 14        # Ancho de cada columna de competencia (P1-P4 x 4 periodos)
    col_pc = 16          # Ancho de PC
    col_cf = 22          # CF
    col_comp_extra = 22  # Completiva, extraordinaria, especial
    col_situacion = 15   # A/R
    
    # ---- ENCABEZADO SUPERIOR: "CALIFICACIONES DE RENDIMIENTO" ----
    c.setFont('Helvetica-Bold', 7)
    c.setFillColor(colors.Color(0.15, 0.15, 0.15))
    
    # Fila superior
    x = margin_left
    row_h = 12
    
    # Dibujar la tabla completa con la estructura MINERD
    # Columnas: Asignatura | P1P2P3P4 (Per1) | P1P2P3P4 (Per2) | P1P2P3P4 (Per3) | P1P2P3P4 (Per4) | PC1 PC2 PC3 PC4 | CF | Completiva | Extraordinaria | Especial | A R
    
    # Encabezado "CALIFICACIONES DE RENDIMIENTO"
    c.setFont('Helvetica-Bold', 8)
    total_width = w - margin_left * 2
    c.drawCentredString(margin_left + total_width/2, y_start + 5, 'CALIFICACIONES DE RENDIMIENTO')
    
    y = y_start - 8
    
    # Definir estructura de la tabla como datos para ReportLab Table
    # Esto es más limpio y preciso
    
    # Headers row 1
    header1 = ['ÁREAS\nCURRICULARES', 
               'COMPETENCIAS FUNDAMENTALES',  # Span across P columns
               '', '', '', '', '', '', '', '', '', '', '', '', '', '',
               'PROMEDIO\nGRUPO C.E.', '', '', '',
               'C.F.', 
               'C.E.C.', 'C.C.F.',
               'C.E.EX', 'C.EX.F.',
               'C.E.',
               'A', 'R']
    
    # Headers row 2 - Períodos  
    header2 = ['', 
               'P1', 'P2', 'P3', 'P4',  # Período 1
               'P1', 'P2', 'P3', 'P4',  # Período 2
               'P1', 'P2', 'P3', 'P4',  # Período 3
               'P1', 'P2', 'P3', 'P4',  # Período 4
               'PC1', 'PC2', 'PC3', 'PC4',
               '', 
               '50%\nC.F.', '50%\nC.E.C.',
               '30%\nC.F.', '70%\nC.E.EX',
               '',
               '', '']
    
    # Construir datos de cada asignatura
    table_data = []
    
    for asig_nombre in asignaturas_boletin:
        # Buscar calificaciones para esta asignatura
        cal_data = None
        for cd in calificaciones_data:
            nombre_normalizado = normalizar_asignatura(cd.get('asignatura', ''))
            if nombre_normalizado == asig_nombre:
                cal_data = cd
                break
        
        row = [asig_nombre]
        
        if cal_data:
            # Parciales de cada período (P1-P4 por cada período)
            for periodo in range(1, 5):
                for parcial in range(1, 5):
                    key = f'p{periodo}_p{parcial}'
                    val = cal_data.get(key)
                    row.append(str(int(val)) if val is not None else '')
            
            # PC1-PC4
            for p in range(1, 5):
                pc = cal_data.get(f'pc{p}')
                row.append(str(int(pc)) if pc is not None else '')
            
            # CF
            cf = cal_data.get('cf')
            row.append(str(int(cf)) if cf is not None else '')
            
            # Completiva: 50% CF + 50% CEC = CCF
            rp_vals = [cal_data.get(f'rp{p}') for p in range(1, 5)]
            tiene_completiva = any(v is not None for v in rp_vals)
            if tiene_completiva and cf is not None and cf < 70:
                # Mostrar la nota de completiva más reciente
                rp = next((v for v in reversed(rp_vals) if v is not None), None)
                row.append(str(int(cf)) if cf else '')  # 50% CF
                row.append(str(int(rp)) if rp else '')   # 50% CEC (la completiva)
            else:
                row.append('')
                row.append('')
            
            # Extraordinaria (no implementada aún)
            row.append('')  # 30% CF
            row.append('')  # 70% C.E.EX
            
            # Especial
            row.append('')
            
            # Situación: A/R
            situacion = get_situacion_asignatura(cf)
            row.append('X' if situacion == 'A' else '')
            row.append('X' if situacion == 'R' else '')
        else:
            # Sin calificaciones - llenar vacío
            row.extend([''] * 27)
        
        table_data.append(row)
    
    # ---- Construir tabla con ReportLab ----
    # Anchos de columna
    col_widths = [82]  # Asignatura
    col_widths += [13] * 16  # 4 parciales x 4 períodos
    col_widths += [17] * 4   # PC1-PC4
    col_widths += [20]        # CF
    col_widths += [17, 17]    # Completiva
    col_widths += [17, 17]    # Extraordinaria
    col_widths += [17]        # Especial
    col_widths += [13, 13]    # A, R
    
    # Header rows
    h1 = ['ÁREAS\nCURRICULARES']
    h1 += [''] * 16  # Competencias (se hace span)
    h1 += [''] * 4   # PC (se hace span)
    h1 += ['C.F.']
    h1 += ['C.E.C.', 'C.C.F.']
    h1 += ['C.E.\nEX', 'C.EX.\nF.']
    h1 += ['C.E.']
    h1 += ['', '']   # situacion span
    
    h2 = ['']
    # Período labels
    h2 += ['P1', 'P2', 'P3', 'P4'] * 4
    h2 += ['PC1', 'PC2', 'PC3', 'PC4']
    h2 += ['', '', '', '', '', '', '', '']
    
    all_data = [h1, h2] + table_data
    
    t = Table(all_data, colWidths=col_widths, rowHeights=[22, 16] + [20] * len(table_data))
    
    style_commands = [
        # General
        ('FONTSIZE', (0, 0), (-1, -1), 6),
        ('FONTNAME', (0, 0), (-1, 1), 'Helvetica-Bold'),
        ('FONTNAME', (0, 2), (0, -1), 'Helvetica'),
        ('FONTNAME', (1, 2), (-1, -1), 'Helvetica'),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.Color(0.35, 0.35, 0.35)),
        
        # Header row 1 - Azul MINERD oscuro
        ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.18, 0.30, 0.55)),  # Azul oscuro MINERD
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        
        # Header row 2 - Azul MINERD claro
        ('BACKGROUND', (0, 1), (-1, 1), colors.Color(0.30, 0.45, 0.70)),  # Azul medio
        ('TEXTCOLOR', (0, 1), (-1, 1), colors.white),
        
        # Asignatura column - fondo azul claro
        ('BACKGROUND', (0, 2), (0, -1), colors.Color(0.85, 0.90, 0.95)),
        ('FONTSIZE', (0, 2), (0, -1), 5.8),
        ('LEFTPADDING', (0, 0), (0, -1), 3),
        
        # Competencias P1-P4 de cada período - fondo ligeramente diferente por período
        ('BACKGROUND', (1, 2), (4, -1), colors.Color(1.0, 0.98, 0.92)),    # P1 - crema
        ('BACKGROUND', (5, 2), (8, -1), colors.Color(0.95, 0.97, 1.0)),     # P2 - azul muy claro
        ('BACKGROUND', (9, 2), (12, -1), colors.Color(0.98, 0.95, 0.98)),   # P3 - lila muy claro
        ('BACKGROUND', (13, 2), (16, -1), colors.Color(0.92, 0.98, 0.95)),  # P4 - verde muy claro
        
        # PC1-PC4 - fondo destacado
        ('BACKGROUND', (17, 2), (20, -1), colors.Color(0.88, 0.92, 0.98)),  # Azul claro
        ('FONTNAME', (17, 2), (20, -1), 'Helvetica-Bold'),
        
        # CF column - amarillo suave destacado
        ('BACKGROUND', (21, 0), (21, -1), colors.Color(0.95, 0.90, 0.70)),
        ('FONTNAME', (21, 2), (21, -1), 'Helvetica-Bold'),
        
        # Completiva - naranja suave
        ('BACKGROUND', (22, 2), (23, -1), colors.Color(1.0, 0.93, 0.85)),
        
        # Extraordinaria - rosa suave
        ('BACKGROUND', (24, 2), (25, -1), colors.Color(0.98, 0.90, 0.90)),
        
        # Especial - gris
        ('BACKGROUND', (26, 2), (26, -1), colors.Color(0.93, 0.93, 0.93)),
        
        # A/R - verde y rojo suave
        ('BACKGROUND', (27, 2), (27, -1), colors.Color(0.88, 0.96, 0.88)),  # A - verde
        ('BACKGROUND', (28, 2), (28, -1), colors.Color(0.98, 0.88, 0.88)),  # R - rojo
        
        # Período separadores visuales (líneas más gruesas entre períodos)
        ('LINEAFTER', (4, 0), (4, -1), 1.2, colors.Color(0.15, 0.25, 0.50)),
        ('LINEAFTER', (8, 0), (8, -1), 1.2, colors.Color(0.15, 0.25, 0.50)),
        ('LINEAFTER', (12, 0), (12, -1), 1.2, colors.Color(0.15, 0.25, 0.50)),
        ('LINEAFTER', (16, 0), (16, -1), 1.5, colors.Color(0.15, 0.25, 0.50)),
        ('LINEAFTER', (20, 0), (20, -1), 1.5, colors.Color(0.15, 0.25, 0.50)),
        ('LINEAFTER', (21, 0), (21, -1), 1, colors.Color(0.15, 0.25, 0.50)),
        
        # Header spans
        ('SPAN', (0, 0), (0, 1)),  # Áreas Curriculares
    ]
    
    t.setStyle(TableStyle(style_commands))
    
    # Dibujar tabla
    table_width, table_height = t.wrap(0, 0)
    x_pos = margin_left
    y_pos = y - table_height
    t.drawOn(c, x_pos, y_pos)
    
    # ---- RESUMEN DE ASISTENCIA ----
    y_asist = y_pos - 25
    c.setFont('Helvetica-Bold', 8)
    c.drawString(margin_left, y_asist, 'RESUMEN DE ASISTENCIA DEL/LA ESTUDIANTE')
    
    y_asist -= 5
    
    asist_headers = ['Períodos', 'Asistencia', 'Ausencia', '', 'Anual', 'Asistencia', 'Ausencia']
    asist_data = [asist_headers]
    
    total_asist = 0
    total_ausencia = 0
    for p in range(1, 5):
        p_data = asistencia_data.get(f'periodo_{p}', {})
        presentes = p_data.get('presentes', 0)
        ausentes = p_data.get('ausentes', 0)
        total_asist += presentes
        total_ausencia += ausentes
        asist_data.append([
            f'P{p}', str(presentes) if presentes else '', str(ausentes) if ausentes else '',
            '', '', '', ''
        ])
    
    # Agregar porcentaje anual en la primera fila de datos
    if total_asist + total_ausencia > 0:
        pct_asist = round(total_asist / (total_asist + total_ausencia) * 100, 1)
        pct_ausencia = round(100 - pct_asist, 1)
        asist_data[1][4] = '% de'
        asist_data[1][5] = f'{pct_asist}%'
        asist_data[1][6] = f'{pct_ausencia}%'
    
    asist_widths = [40, 50, 50, 10, 40, 50, 50]
    asist_table = Table(asist_data, colWidths=asist_widths, rowHeights=14)
    asist_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 6.5),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (2, -1), 0.5, colors.Color(0.4, 0.4, 0.4)),
        ('GRID', (4, 0), (-1, -1), 0.5, colors.Color(0.4, 0.4, 0.4)),
        ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.85, 0.85, 0.85)),
    ]))
    
    asist_table.wrapOn(c, 0, 0)
    asist_table.drawOn(c, margin_left, y_asist - 80)
    
    # ---- LEYENDA ----
    y_ley = y_asist - 80
    x_ley = margin_left + 320
    c.setFont('Helvetica-Bold', 7)
    c.drawString(x_ley, y_ley, 'LEYENDA:')
    c.setFont('Helvetica', 6)
    leyenda = [
        ('(P1)', 'Período 1'), ('(P2)', 'Período 2'), ('(P3)', 'Período 3'), ('(P4)', 'Período 4'),
        ('(PC)', 'Promedio Grupo de Competencias Específicas'), ('(C.F.)', 'Calificación Final'),
        ('(C.E.C.)', 'Calificación Evaluación Completiva'), ('(C.C.F.)', 'Calificación Completiva Final'),
        ('(C.E. EX)', 'Calificación Evaluación Extraordinaria'), ('(C.EX.F.)', 'Calificación Extraordinaria Final'),
        ('(C.E.)', 'Calificación Especial'), ('(A)', 'Aprobado'), ('(R)', 'Reprobado')
    ]
    y_l = y_ley - 10
    for abrev, desc in leyenda:
        c.setFont('Helvetica-Bold', 5.5)
        c.drawString(x_ley, y_l, abrev)
        c.setFont('Helvetica', 5.5)
        c.drawString(x_ley + 35, y_l, desc)
        y_l -= 9
    
    # ---- SITUACIÓN FINAL ----
    y_sit = y_asist - 105
    c.setFont('Helvetica-Bold', 8)
    situacion = get_situacion_final(calificaciones_data)
    promovido = 'X' if 'Promovido' in situacion else ''
    repitente = 'X' if 'Repitente' in situacion else ''
    
    c.drawString(margin_left, y_sit, f'SITUACIÓN DEL/DE LA ESTUDIANTE:    Promovido/a [{promovido}]    Repitente [{repitente}]')
    
    y_sit -= 15
    c.drawString(margin_left, y_sit, f'CONDICIÓN FINAL DEL/DE LA ESTUDIANTE: {situacion}')
    
    # ---- FIRMAS ----
    y_firma = y_sit - 30
    c.setFont('Helvetica', 8)
    c.line(margin_left, y_firma, margin_left + 200, y_firma)
    c.line(w/2 + 20, y_firma, w - margin_left, y_firma)
    c.drawString(margin_left, y_firma - 12, 'Maestro(a) encargado(a) del grado')
    c.drawString(w/2 - 30, y_firma - 12, 'Director(a) del Centro Educativo')


# ========================================
# FUNCIÓN PRINCIPAL
# ========================================

def generar_boletin_minerd(estudiante, curso, calificaciones, asistencias, config, ano_escolar, observaciones=''):
    """
    Genera el boletín completo en formato MINERD.
    
    Args:
        estudiante: Objeto Estudiante
        curso: Objeto Curso
        calificaciones: Lista de objetos Calificacion
        asistencias: Lista de objetos Asistencia
        config: Objeto ConfiguracionColegio
        ano_escolar: Objeto AnoEscolar
        observaciones: Texto de observaciones (opcional)
    
    Returns:
        BytesIO buffer con el PDF
    """
    buffer = io.BytesIO()
    
    # ---- Preparar datos de calificaciones ----
    calificaciones_data = []
    for cal in calificaciones:
        asig_nombre = cal.asignatura.nombre if cal.asignatura else 'Sin asignatura'
        data = {
            'asignatura': asig_nombre,
            'asignatura_id': cal.asignatura_id,
        }
        # Parciales de cada período
        for periodo in range(1, 5):
            for parcial in range(1, 5):
                key = f'p{periodo}_p{parcial}'
                data[key] = getattr(cal, key, None)
            data[f'pc{periodo}'] = getattr(cal, f'pc{periodo}', None)
            data[f'rp{periodo}'] = getattr(cal, f'rp{periodo}', None)
        
        data['cf'] = cal.cf
        data['literal'] = cal.literal or (cal.get_literal() if hasattr(cal, 'get_literal') else None)
        calificaciones_data.append(data)
    
    # ---- Preparar datos de asistencia por período ----
    asistencia_data = {}
    for p in range(1, 5):
        asist_periodo = [a for a in asistencias if hasattr(a, 'periodo') and a.periodo == p]
        if not asist_periodo:
            # Si no hay campo periodo, distribuir por fecha (aproximación)
            asist_periodo = asistencias  # fallback
        
        presentes = sum(1 for a in asist_periodo if a.estado == 'presente')
        ausentes = sum(1 for a in asist_periodo if a.estado in ('ausente', 'ausente_justificado'))
        asistencia_data[f'periodo_{p}'] = {
            'presentes': presentes if asist_periodo != asistencias else 0,
            'ausentes': ausentes if asist_periodo != asistencias else 0
        }
    
    # Si la asistencia no tiene campo periodo, calcular totales generales
    total_presentes = sum(1 for a in asistencias if a.estado == 'presente')
    total_ausentes = sum(1 for a in asistencias if a.estado in ('ausente', 'ausente_justificado'))
    if total_presentes > 0 and all(asistencia_data[f'periodo_{p}']['presentes'] == 0 for p in range(1, 5)):
        # Distribuir equitativamente entre períodos con datos
        for p in range(1, 5):
            asistencia_data[f'periodo_{p}'] = {
                'presentes': total_presentes // 4,
                'ausentes': total_ausentes // 4
            }
    
    # ---- Crear PDF ----
    # Página 1: Portada (portrait)
    c_pdf = canvas.Canvas(buffer, pagesize=letter)
    dibujar_portada(c_pdf, config, estudiante, ano_escolar, curso, observaciones)
    
    # Página 2: Calificaciones (landscape)
    c_pdf.showPage()
    c_pdf.setPageSize(landscape(letter))
    dibujar_calificaciones(c_pdf, estudiante, curso, calificaciones_data, asistencia_data)
    
    c_pdf.save()
    buffer.seek(0)
    return buffer
