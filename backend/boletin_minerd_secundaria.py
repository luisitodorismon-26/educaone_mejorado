"""
Boletín de Calificaciones MINERD — SECUNDARIA (v2.13 PIXEL-EXACTO)
==================================================================
Genera el boletín oficial de secundaria del MINERD overlayendo los
datos del estudiante sobre la plantilla PDF oficial.

A diferencia de boletin_minerd.py (que dibuja todo desde cero en Letter
horizontal), este módulo usa el PDF oficial MINERD (Legal landscape
1008x612 pts) como plantilla y solo dibuja los números encima.
Resultado: pixel-exacto al PDF que MINERD requiere oficialmente.

Coordenadas calibradas con pdfplumber sobre los PDFs oficiales 2do y 6to
grado NS (julio 2023). Ver tools/calibrar_boletin_minerd.py para reproducir.

ESTRUCTURA DE DATOS REQUERIDA:
- estudiante: objeto Estudiante (necesita: nombre, apellido, curso, etc.)
- curso: objeto Curso (con .grado, .seccion, .nivel, .ciclo)
- calificaciones_por_asig: dict
    {asignatura_id: {
        'asignatura_nombre': str,
        'competencias': lista[4 CalificacionSecundaria],
        'pc_por_periodo': {pc1, pc2, pc3, pc4: float|None},
        'a_r_por_periodo': {p1, p2, p3, p4: {a, r, pendientes}},
        'cf': int|None,
        'literal': str|None,
        'evaluacion_extra': EvaluacionExtraSecundaria|None,
    }}
- asistencias_por_periodo: dict {p1, p2, p3, p4: {asistencia, ausencia, %asis_anual, %aus_anual}}
- config: ConfiguracionColegio
- ano_escolar: AnoEscolar (para los años: 2024, 2025)
- observaciones: str

USO:
    buffer = generar_boletin_secundaria_minerd(
        estudiante=est,
        curso=curso,
        calificaciones_por_asig={5: {...}, 6: {...}, ...},
        asistencias_por_periodo={'p1': {...}, ...},
        config=config,
        ano_escolar=ano,
        observaciones='...',
    )
    # buffer es io.BytesIO listo para StreamingResponse
"""
from __future__ import annotations

import io
import os
import base64
import re
from typing import Any

from reportlab.lib.colors import Color
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from pypdf import PdfReader, PdfWriter


# ─────────────────────────────────────────────────────────────────────
# CONSTANTES PIXEL-EXACTAS (calibradas sobre PDF oficial MINERD)
# Página tamaño: Legal landscape = 1008 × 612 pts
# Sistema de coordenadas: pdfplumber reporta "top" desde arriba (y_top).
# ReportLab usa origen abajo-izq, así que convertimos: y_rl = PAGE_H - y_top
# ─────────────────────────────────────────────────────────────────────

PAGE_W = 1008.0
PAGE_H = 612.0

# v2.13.11: cambiado de azul oscuro a negro a pedido del usuario
# (las copias impresas son siempre en blanco y negro, el azul perdía detalle).
# El alias COLOR_DATOS se mantiene para compatibilidad con el código existente.
COLOR_DATOS = Color(0, 0, 0)  # antes Color(0.0, 0.0, 0.7) — azul oscuro MINERD
COLOR_NEGRO = Color(0, 0, 0)

# Path al directorio de plantillas
_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), 'templates', 'boletin_secundaria')


# ═════════════════════════════════════════════════════════════════════
# PÁGINA 1 — Portada (lado derecho del PDF, datos del estudiante)
# ═════════════════════════════════════════════════════════════════════

# X inicio del texto en cada línea (después del ':' del label + 4pt buffer)
# Calibrado caracter-por-caracter contra el PDF oficial.
PORTADA_X = {
    'ano1':            735,   # inicio del 1er underline (después de "20")
    'ano2':            805,   # inicio del 2do underline (después de "20")
    'seccion':         585,   # después de "Sección:"
    'numero_orden':    847,   # después de "Número de orden:"
    'nombre':          604,   # después de "Nombre (s):"
    'apellido':        604,   # después de "Apellido (s):"
    'sigerd':          745,   # después de "ID estudiante (Número de identificación SIGERD):"
    'docente':         589,   # después de "Docente:"
    'centro':          636,   # después de "Centro educativo:"
    'codigo':          642,   # después de "Código del centro:"
    'tanda':           577,   # después de "Tanda:"
    'telefono':        648,   # después de "Teléfono del centro:"
    'distrito':        636,   # después de "Distrito educativo:"
    'regional':        666,   # después de "Regional de educación:"
    'provincia':       593,   # después de "Provincia:"
    'municipio':       596,   # después de "Municipio:"
}

# Y_top de cada campo (pdfplumber → debe convertirse a y_rl)
# Estos Y reflejan la línea de base del texto: el texto se "sienta" sobre la línea de underline.
PORTADA_Y = {
    'ano1':         290, 'ano2':         290,
    'seccion':      318, 'numero_orden': 318,
    'nombre':       340, 'apellido':     362,
    'sigerd':       384, 'docente':      406,
    'centro':       428, 'codigo':       450,
    'tanda':        472, 'telefono':     494,
    'distrito':     516, 'regional':     538,
    'provincia':    560, 'municipio':    582,
}

# Lado izquierdo: Observaciones (18 líneas) + Períodos de Reporte (4)
OBSERV_X_INICIO = 41
OBSERV_X_MAX    = 464
OBSERV_Y_INICIO = 220     # primera línea
OBSERV_LINE_H   = 20      # alto entre líneas
OBSERV_MAX_LINEAS = 18

PERIODOS_REPORTE_X = {
    'ago_oct': 115,    # "Ago-Sept-Oct ___" (después del label)
    'nov_ene': 109,    # "Nov-Dic-Ene ___"
    'feb_mar':  90,    # "Feb-Mar ___"
    'abr_jun': 113,    # "Abr-May-Jun ___"
}
PERIODOS_REPORTE_Y = {
    'ago_oct': 73, 'nov_ene': 101, 'feb_mar': 129, 'abr_jun': 157,
}


# ═════════════════════════════════════════════════════════════════════
# PÁGINA 2 — Tabla de calificaciones
# ═════════════════════════════════════════════════════════════════════
#
# IMPORTANTE: las plantillas oficiales MINERD para primer ciclo (1er-3er NS)
# y segundo ciclo (4to-6to NS) NO son idénticas. Aunque comparten estructura,
# las coordenadas Y de algunas zonas difieren porque el segundo ciclo incluye
# 2 filas adicionales para "SALIDA OPTATIVA" que desplazan todo lo de abajo.
#
# Por eso mantenemos dos sets de coordenadas, y elegimos en runtime según
# `_es_segundo_ciclo(curso)`. Las X de columnas son idénticas en ambos.
# ═════════════════════════════════════════════════════════════════════

# Header del estudiante (parte superior de página 2) — IGUAL en ambos ciclos
HEADER_P2 = {
    'nombre': (173, 36),
    'grado':  (557, 36),
    'seccion':(790, 36),
}

# X centrales de cada columna P por competencia — IGUAL en ambos ciclos
COMP_X = {
    1: {'p1': 173, 'p2': 198, 'p3': 223, 'p4': 249},  # Comunicativa
    2: {'p1': 274, 'p2': 299, 'p3': 325, 'p4': 350},  # Pensam.Lógico+Resol.Problemas
    3: {'p1': 375, 'p2': 401, 'p3': 426, 'p4': 451},  # Científ+Ambiental
    4: {'p1': 477, 'p2': 502, 'p3': 527, 'p4': 552},  # Ética+Desarrollo Personal
}

# X centrales de PC1-PC4 y columnas derecha — IGUAL en ambos ciclos
PC_X = {'pc1': 577, 'pc2': 601, 'pc3': 625, 'pc4': 649}
RIGHT_X = {
    'cf':       673,    # Calificación Final del Área
    'p_cf_50':  697,    # 50% C.F. (bloque completiva)
    'cec':      717,    # C.E.C.
    'p_cec_50': 745,    # 50% C.E.C.
    'ccf':      773,    # C.C.F. (completiva final)
    'p_cf_30':  793,    # 30% C.F. (bloque extraordinaria)
    'ceex':     820,    # C.E. EX
    'p_ceex_70':840,    # 70% C.E. EX
    'cexf':     870,    # C.EX.F. (extraordinaria final)
    'esp_cf':   893,    # C.F. (bloque especial)
    'esp_ce':   920,    # C.E. (especial)
    'A':        947,    # Aprobado
    'R':        977,    # Reprobado
}

# Asistencia: X iguales en ambos ciclos
ASIST_X = {'asis': 109, 'ausen': 159, 'pct_asis': 211, 'pct_ausen': 259}

# X de Promovido/a y Repitente: iguales en ambos ciclos (812.6 y 901.2)
SITUACION_PROMOVIDO_X = 813
SITUACION_REPITENTE_X = 901

# X de Condición Final: igual en ambos ciclos
CONDICION_FINAL_X = 670


# ─── Coordenadas Y por ciclo ──────────────────────────────────────────

# SEGUNDO CICLO (4to-6to NS, plantilla con SALIDA OPTATIVA)
ROW_Y_SEGUNDO = {
    'Lengua Española':                       152,
    'Lenguas Extranjeras (Inglés)':          178,
    'Lenguas Extranjeras (Francés)':         202,
    'Matemática':                            227,
    'Ciencias Sociales':                     252,
    'Ciencias de la Naturaleza':             276,
    'Educación Artística':                   305,
    'Educación Física':                      329,
    'Formación Integral Humana y Religiosa': 353,
    'SALIDA OPTATIVA 1': 386,
    'SALIDA OPTATIVA 2': 410,
}
ASIST_Y_SEGUNDO    = {'p1': 492, 'p2': 517, 'p3': 542, 'p4': 567}
SITUACION_Y_SEGUNDO = 446
CONDICION_FINAL_Y_SEGUNDO = 504


# PRIMER CICLO (1ro-3ro NS, plantilla SIN SALIDA OPTATIVA — todo lo de abajo
# está corrido hacia arriba ~30pts)
ROW_Y_PRIMERO = {
    'Lengua Española':                       155,
    'Lenguas Extranjeras (Inglés)':          181,
    'Lenguas Extranjeras (Francés)':         207,
    'Matemática':                            232,
    'Ciencias Sociales':                     257,
    'Ciencias de la Naturaleza':             282,
    'Educación Artística':                   308,
    'Educación Física':                      333,
    'Formación Integral Humana y Religiosa': 358,
}
ASIST_Y_PRIMERO    = {'p1': 478, 'p2': 504, 'p3': 530, 'p4': 558}
SITUACION_Y_PRIMERO = 415
CONDICION_FINAL_Y_PRIMERO = 472


# ─────────────────────────────────────────────────────────────────────
# Helpers internos
# ─────────────────────────────────────────────────────────────────────

def _y(y_top: float) -> float:
    """Convierte y_top (desde arriba) a coordenadas ReportLab (desde abajo)."""
    return PAGE_H - y_top


def _fmt_nota(v, ints_only: bool = False) -> str:
    """Formatea una nota: entero si es CF, 1 decimal si es PC/competencia."""
    if v is None:
        return ''
    try:
        v = float(v)
    except (TypeError, ValueError):
        return ''
    if ints_only or abs(v - round(v)) < 0.05:
        return str(int(round(v)))
    return f"{v:.1f}"


def _normalizar_nombre_asignatura(nombre: str) -> str:
    """Mapea variantes a los nombres oficiales del boletín MINERD.
    
    El sistema interno puede tener "Inglés", "ingles", "Lengua Extranjera Inglés", etc.
    Aquí los normalizamos a la forma exacta que aparece en la plantilla oficial.
    """
    if not nombre:
        return ''
    n = nombre.strip().lower()
    
    mapeo = {
        'lengua española': 'Lengua Española',
        'lengua espanola': 'Lengua Española',
        'español': 'Lengua Española',
        'espanol': 'Lengua Española',
        
        'inglés': 'Lenguas Extranjeras (Inglés)',
        'ingles': 'Lenguas Extranjeras (Inglés)',
        'lengua extranjera inglés': 'Lenguas Extranjeras (Inglés)',
        'lengua extranjera ingles': 'Lenguas Extranjeras (Inglés)',
        'lenguas extranjeras (inglés)': 'Lenguas Extranjeras (Inglés)',
        'lenguas extranjeras (ingles)': 'Lenguas Extranjeras (Inglés)',
        'lenguas extranjeras inglés': 'Lenguas Extranjeras (Inglés)',
        
        'francés': 'Lenguas Extranjeras (Francés)',
        'frances': 'Lenguas Extranjeras (Francés)',
        'lenguas extranjeras (francés)': 'Lenguas Extranjeras (Francés)',
        'lenguas extranjeras (frances)': 'Lenguas Extranjeras (Francés)',
        
        'matemática': 'Matemática',
        'matematica': 'Matemática',
        'matematicas': 'Matemática',
        'matemáticas': 'Matemática',
        
        'ciencias sociales': 'Ciencias Sociales',
        'sociales': 'Ciencias Sociales',
        
        'ciencias de la naturaleza': 'Ciencias de la Naturaleza',
        'ciencias naturales': 'Ciencias de la Naturaleza',
        'naturales': 'Ciencias de la Naturaleza',
        
        'educación artística': 'Educación Artística',
        'educacion artistica': 'Educación Artística',
        'artística': 'Educación Artística',
        'artistica': 'Educación Artística',
        'arte': 'Educación Artística',
        
        'educación física': 'Educación Física',
        'educacion fisica': 'Educación Física',
        'física': 'Educación Física',
        'fisica': 'Educación Física',
        
        'formación integral humana y religiosa': 'Formación Integral Humana y Religiosa',
        'formacion integral humana y religiosa': 'Formación Integral Humana y Religiosa',
        'fihr': 'Formación Integral Humana y Religiosa',
        'religión': 'Formación Integral Humana y Religiosa',
        'religion': 'Formación Integral Humana y Religiosa',
        'humana y religiosa': 'Formación Integral Humana y Religiosa',
    }
    return mapeo.get(n, nombre)  # si no encuentra, mantiene el original


def _texto_de(valor, attr='nombre') -> str:
    """Extrae texto de un valor que puede ser objeto SQLAlchemy o string o None.
    
    v2.13.12: helper genérico para evitar el bug recurrente de aplicar
    métodos de string (.strip(), .lower()) sobre objetos de relación
    SQLAlchemy (Tanda, Grado, etc).
    
    Ejemplos:
      _texto_de(tanda_obj) → tanda_obj.nombre → "Matutina"
      _texto_de("Matutina") → "Matutina"
      _texto_de(None) → ""
      _texto_de(grado_obj, 'nombre') → "1ro"
    """
    if valor is None:
        return ''
    if isinstance(valor, str):
        return valor.strip()
    # Es un objeto: intentar el atributo pedido
    attr_val = getattr(valor, attr, None)
    if attr_val is not None:
        return str(attr_val).strip()
    # Último fallback: str() del objeto
    return str(valor).strip()


def _nombre_grado_normalizado(curso) -> str:
    """Devuelve el nombre del grado en formato normalizado (lowercase) para comparar.
    
    v2.13.10: helper robusto. `curso.grado` puede ser objeto Grado, string o None.
    v2.13.12: delega en _texto_de para consistencia.
    """
    if not curso:
        return ''
    return _texto_de(getattr(curso, 'grado', None), 'nombre').lower()


def _es_segundo_ciclo(curso) -> bool:
    """Determina si el curso es Segundo Ciclo de Secundaria (4to-6to NS).
    
    v2.13.10: usa helper normalizado para evitar el bug de `.lower()` sobre objeto Grado.
    
    v2.13.11 FIX CRÍTICO confirmado por usuario:
      Primer Ciclo NS: 1ro, 2do, 3ro
      Segundo Ciclo NS: 4to, 5to, 6to (los que tienen "Salida Optativa")
    
    El código histórico marcaba 3ro como segundo ciclo, lo cual hacía que
    los boletines de 3ro NS mostraran columna "Salida Optativa" cuando NO
    deberían tenerla según MINERD oficial.
    """
    grado = _nombre_grado_normalizado(curso)
    return any(g in grado for g in ['4to', '4ta', '5to', '5ta', '6to', '6ta',
                                     'cuarto', 'quinto', 'sexto'])


def _identificar_grado(curso) -> str:
    """Devuelve 'PRIMERO', 'SEGUNDO', ..., 'SEXTO' o 'DESCONOCIDO'.
    
    v2.13.10: necesario para elegir la plantilla específica por grado.
    """
    g = _nombre_grado_normalizado(curso)
    if any(x in g for x in ['1ro', '1ra', '1er', 'primer', 'primero']):
        return 'PRIMERO'
    if any(x in g for x in ['2do', '2da', 'segundo']):
        return 'SEGUNDO'
    if any(x in g for x in ['3ro', '3er', '3ero', 'tercero']):
        return 'TERCERO'
    if any(x in g for x in ['4to', '4ta', 'cuarto']):
        return 'CUARTO'
    if any(x in g for x in ['5to', '5ta', 'quinto']):
        return 'QUINTO'
    if any(x in g for x in ['6to', '6ta', 'sexto']):
        return 'SEXTO'
    return 'DESCONOCIDO'


def _get_plantilla_path(curso) -> str:
    """Devuelve el path al PDF plantilla MINERD correcto según el grado específico.
    
    v2.13.10: routing por grado específico, con fallback inteligente al
    grado más cercano DEL MISMO CICLO si la plantilla específica no existe.
    
    Esquema de plantillas:
      1ro NS → Boletin-1ro-grado-NS.pdf (primer ciclo)
      2do NS → Boletin-2do-grado-NS.pdf (primer ciclo)
      3ro NS → Boletin-3ro-grado-NS.pdf (primer ciclo)
      4to NS → Boletin-4to-grado-NS.pdf (segundo ciclo)
      5to NS → Boletin-5to-grado-NS.pdf (segundo ciclo)
      6to NS → Boletin-6to-grado-NS.pdf (segundo ciclo)
    
    Fallback cuando no existe la plantilla específica:
      Primer ciclo (1-3) → 2do o cualquier otra disponible del primer ciclo
      Segundo ciclo (4-6) → 6to o cualquier otra disponible del segundo ciclo
    
    Las plantillas del mismo ciclo son visualmente IDÉNTICAS en estructura
    (mismo tamaño, mismas competencias, mismas coordenadas). El único cambio
    visible es el header donde dice "Boletín de calificaciones de Xro grado".
    """
    grado_id = _identificar_grado(curso)
    
    # Mapeo grado → archivo preferido
    archivos_por_grado = {
        'PRIMERO': 'Boletin-1ro-grado-NS.pdf',
        'SEGUNDO': 'Boletin-2do-grado-NS.pdf',
        'TERCERO': 'Boletin-3ro-grado-NS.pdf',
        'CUARTO':  'Boletin-4to-grado-NS.pdf',
        'QUINTO':  'Boletin-5to-grado-NS.pdf',
        'SEXTO':   'Boletin-6to-grado-NS.pdf',
    }
    
    # 1) Intentar plantilla específica
    archivo_preferido = archivos_por_grado.get(grado_id)
    if archivo_preferido:
        path_preferido = os.path.join(_TEMPLATES_DIR, archivo_preferido)
        if os.path.exists(path_preferido):
            return path_preferido
    
    # 2) Fallback al mismo ciclo
    es_seg = grado_id in ('CUARTO', 'QUINTO', 'SEXTO') or _es_segundo_ciclo(curso)
    if es_seg:
        candidatos = ['Boletin-6to-grado-NS.pdf', 'Boletin-5to-grado-NS.pdf', 'Boletin-4to-grado-NS.pdf']
        ciclo_str = 'Segundo Ciclo (4to-6to)'
    else:
        candidatos = ['Boletin-2do-grado-NS.pdf', 'Boletin-1ro-grado-NS.pdf', 'Boletin-3ro-grado-NS.pdf']
        ciclo_str = 'Primer Ciclo (1ro-3ro)'
    
    for cand in candidatos:
        path_cand = os.path.join(_TEMPLATES_DIR, cand)
        if os.path.exists(path_cand):
            return path_cand
    
    # 3) Nada existe — error con mensaje útil
    raise FileNotFoundError(
        f"No hay plantilla MINERD oficial para {ciclo_str}. "
        f"Necesitás al menos una de: {', '.join(candidatos)} en "
        f"{_TEMPLATES_DIR}. Verificá que el directorio esté incluido en el deploy."
    )


# ─────────────────────────────────────────────────────────────────────
# Dibujado de cada página
# ─────────────────────────────────────────────────────────────────────

# Posición del escudo del MINERD y textos del ministerio en la portada.
# Los colegios privados sustituyen TODO esto (escudo + "Viceministro..." +
# "Dirección General...") por su propio sello.
ESCUDO_CX = 754.6   # centro X (pts)
# Área del recuadro blanco que tapa el escudo Y los textos del ministerio:
TAPA_CY = 533.9     # centro Y del área a tapar (desde abajo)
TAPA_W = 200.0      # ancho del recuadro blanco (cubre los textos anchos)
TAPA_H = 112.0      # alto del recuadro (desde arriba del escudo hasta debajo de los textos)
# Tamaño al que se dibuja el logo del colegio (centrado, sin estirar):
LOGO_MAX_W = 105.0  # ancho máximo del logo (pts)
LOGO_MAX_H = 95.0   # alto máximo del logo (pts)
LOGO_CY = 540.0     # centro Y donde se dibuja el logo (un poco más arriba que el centro de la tapa)


def _dibujar_logo_colegio(c: canvas.Canvas, config) -> bool:
    """Dibuja el logo del colegio (privado) sobre el escudo del MINERD.

    Los colegios privados usan su propio sello en lugar del escudo del Ministerio.
    Tapa el escudo oficial con un recuadro blanco y dibuja el logo del colegio
    centrado en la misma posición. Devuelve True si dibujó el logo.

    El logo se guarda como Base64 en config.logo (puede venir como
    'data:image/png;base64,XXXX' o solo 'XXXX').
    """
    logo_raw = getattr(config, 'logo', None) if config else None
    if not logo_raw:
        return False  # sin logo → se deja el escudo del MINERD

    try:
        # Extraer los datos base64 (quitar el prefijo 'data:image/...;base64,')
        if isinstance(logo_raw, str) and 'base64,' in logo_raw:
            logo_b64 = logo_raw.split('base64,', 1)[1]
        else:
            logo_b64 = logo_raw
        # Limpiar espacios/saltos de línea que pueda tener el base64
        logo_b64 = re.sub(r'\s+', '', logo_b64)
        logo_bytes = base64.b64decode(logo_b64)
        img = ImageReader(io.BytesIO(logo_bytes))

        # 1) Tapar el escudo del MINERD Y los textos del ministerio con blanco
        c.setFillColorRGB(1, 1, 1)
        c.rect(ESCUDO_CX - TAPA_W / 2, TAPA_CY - TAPA_H / 2,
               TAPA_W, TAPA_H, fill=1, stroke=0)

        # 2) Dibujar el logo del colegio centrado, manteniendo proporción
        iw, ih = img.getSize()
        if iw and ih:
            ratio = min(LOGO_MAX_W / iw, LOGO_MAX_H / ih)
            draw_w = iw * ratio
            draw_h = ih * ratio
        else:
            draw_w, draw_h = LOGO_MAX_W, LOGO_MAX_H
        draw_x = ESCUDO_CX - draw_w / 2
        draw_y = LOGO_CY - draw_h / 2
        c.drawImage(img, draw_x, draw_y, width=draw_w, height=draw_h,
                    mask='auto', preserveAspectRatio=True)
        return True
    except Exception:
        # Si el logo falla (base64 inválido, formato raro), no romper el boletín:
        # simplemente se deja el escudo del MINERD.
        return False


def _dibujar_portada(c: canvas.Canvas, estudiante, curso, config, ano_escolar, observaciones: str = '', docente_nombre: str = '') -> None:
    """Página 1: portada con datos del estudiante (lado derecho) y observaciones (izquierda)."""
    # Si el colegio tiene logo propio, sustituye el escudo del MINERD
    _dibujar_logo_colegio(c, config)

    c.setFillColor(COLOR_DATOS)
    c.setFont("Helvetica", 11)
    
    # Año escolar (dos casillas de 2 dígitos)
    if ano_escolar:
        nombre_ano = (getattr(ano_escolar, 'nombre', '') or '').strip()
        # Formato esperado: "2024-2025" o "24-25". Sacar los dos años.
        partes = nombre_ano.replace('—', '-').replace('–', '-').split('-')
        if len(partes) >= 2:
            a1 = partes[0].strip()[-2:] if partes[0].strip() else ''
            a2 = partes[1].strip()[-2:] if partes[1].strip() else ''
            if a1:
                c.drawString(PORTADA_X['ano1'], _y(PORTADA_Y['ano1']), a1)
            if a2:
                c.drawString(PORTADA_X['ano2'], _y(PORTADA_Y['ano2']), a2)
    
    # Sección + número de orden
    seccion = (getattr(curso, 'seccion', '') or getattr(curso, 'nombre', '') or '').strip()
    if seccion:
        c.drawString(PORTADA_X['seccion'], _y(PORTADA_Y['seccion']), seccion[:30])
    
    numero_orden = (getattr(estudiante, 'no_lista', None) or
                    getattr(estudiante, 'numero_orden', None) or
                    getattr(estudiante, 'numero', None))
    if numero_orden:
        c.drawString(PORTADA_X['numero_orden'], _y(PORTADA_Y['numero_orden']), str(numero_orden))
    
    # Nombre y apellido
    nombre = (getattr(estudiante, 'nombre', '') or '').strip()
    apellido = (getattr(estudiante, 'apellido', '') or '').strip()
    if nombre:
        c.drawString(PORTADA_X['nombre'], _y(PORTADA_Y['nombre']), nombre[:55])
    if apellido:
        c.drawString(PORTADA_X['apellido'], _y(PORTADA_Y['apellido']), apellido[:55])
    
    # SIGERD / matrícula
    sigerd = (getattr(estudiante, 'matricula', None) or
              getattr(estudiante, 'sigerd', None) or
              getattr(estudiante, 'documento_identidad', None) or '')
    sigerd = str(sigerd).strip()
    if sigerd:
        c.drawString(PORTADA_X['sigerd'], _y(PORTADA_Y['sigerd']), sigerd[:30])
    
    # Docente: se pasa como parámetro opcional, sino se intenta del tutor del curso
    docente = (docente_nombre or '').strip()
    if not docente and curso and getattr(curso, 'tutor', None):
        tutor = curso.tutor
        docente = f"{getattr(tutor, 'nombre', '')} {getattr(tutor, 'apellido', '')}".strip()
    if docente:
        c.drawString(PORTADA_X['docente'], _y(PORTADA_Y['docente']), docente[:60])
    
    # Centro educativo (de config)
    if config:
        centro = (getattr(config, 'nombre_centro', None) or getattr(config, 'nombre_colegio', None) or getattr(config, 'nombre', None) or '').strip()
        codigo = (getattr(config, 'codigo_centro', None) or '').strip()
        # v2.13.12: tanda puede ser objeto Tanda o string
        tanda = _texto_de(getattr(curso, 'tanda', None), 'nombre') or _texto_de(getattr(config, 'tanda_default', None)) or ''
        telefono = (getattr(config, 'telefono', None) or getattr(config, 'telefono_centro', None) or '').strip()
        # v2.13.12 FIX: el campo real es 'distrito' y 'regional', no 'distrito_educativo'
        distrito = (getattr(config, 'distrito', None) or getattr(config, 'distrito_educativo', None) or '').strip()
        regional = (getattr(config, 'regional', None) or '').strip()
        provincia = (getattr(config, 'provincia', None) or '').strip()
        municipio = (getattr(config, 'municipio', None) or '').strip()
        
        if centro: c.drawString(PORTADA_X['centro'], _y(PORTADA_Y['centro']), centro[:60])
        if codigo: c.drawString(PORTADA_X['codigo'], _y(PORTADA_Y['codigo']), codigo[:20])
        if tanda: c.drawString(PORTADA_X['tanda'], _y(PORTADA_Y['tanda']), tanda[:30])
        if telefono: c.drawString(PORTADA_X['telefono'], _y(PORTADA_Y['telefono']), telefono[:25])
        if distrito: c.drawString(PORTADA_X['distrito'], _y(PORTADA_Y['distrito']), distrito[:50])
        if regional: c.drawString(PORTADA_X['regional'], _y(PORTADA_Y['regional']), regional[:50])
        if provincia: c.drawString(PORTADA_X['provincia'], _y(PORTADA_Y['provincia']), provincia[:50])
        if municipio: c.drawString(PORTADA_X['municipio'], _y(PORTADA_Y['municipio']), municipio[:50])
    
    # Observaciones (lado izquierdo, 18 líneas de ancho 423pts)
    if observaciones:
        c.setFont("Helvetica", 9)
        lineas = _wrap_text(observaciones, ancho_pts=420, font="Helvetica", size=9)
        for i, linea in enumerate(lineas[:OBSERV_MAX_LINEAS]):
            y_obs = _y(OBSERV_Y_INICIO + i * OBSERV_LINE_H)
            c.drawString(OBSERV_X_INICIO + 2, y_obs, linea)


def _wrap_text(texto: str, ancho_pts: float, font: str = "Helvetica", size: int = 9) -> list:
    """Wrap simple por palabras según ancho disponible en pts."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    palabras = texto.split()
    lineas = []
    actual = ''
    for w in palabras:
        candidato = (actual + ' ' + w).strip()
        if stringWidth(candidato, font, size) <= ancho_pts:
            actual = candidato
        else:
            if actual:
                lineas.append(actual)
            actual = w
    if actual:
        lineas.append(actual)
    return lineas


def _dibujar_tabla_calificaciones(c: canvas.Canvas,
                                   estudiante,
                                   curso,
                                   calificaciones_por_asig: dict,
                                   asistencias_por_periodo: dict,
                                   situacion_final: dict | None = None) -> None:
    """Página 2: tabla pixel-exacta de calificaciones.
    
    Elige el set de coordenadas Y correcto según el ciclo del curso:
    - Primer ciclo (1ro-3ro NS): sin SALIDA OPTATIVA, todo más arriba
    - Segundo ciclo (4to-6to NS): con SALIDA OPTATIVA, todo más abajo
    """
    # Seleccionar coordenadas según ciclo
    if _es_segundo_ciclo(curso):
        row_y_map = ROW_Y_SEGUNDO
        asist_y_map = ASIST_Y_SEGUNDO
        situacion_y = SITUACION_Y_SEGUNDO
        condicion_y = CONDICION_FINAL_Y_SEGUNDO
    else:
        row_y_map = ROW_Y_PRIMERO
        asist_y_map = ASIST_Y_PRIMERO
        situacion_y = SITUACION_Y_PRIMERO
        condicion_y = CONDICION_FINAL_Y_PRIMERO
    
    c.setFillColor(COLOR_DATOS)
    
    # Header del estudiante
    # v2.13.12: usar helper _texto_de (curso.grado puede ser objeto Grado o string)
    c.setFont("Helvetica", 9)
    nombre_completo = f"{(getattr(estudiante, 'nombre', '') or '').strip()} {(getattr(estudiante, 'apellido', '') or '').strip()}".strip()
    grado = _texto_de(getattr(curso, 'grado', None), 'nombre')
    seccion = _texto_de(getattr(curso, 'seccion', None)) or _texto_de(getattr(curso, 'nombre', None))
    
    c.drawString(HEADER_P2['nombre'][0], _y(HEADER_P2['nombre'][1]), nombre_completo[:60])
    c.drawString(HEADER_P2['grado'][0], _y(HEADER_P2['grado'][1]), grado[:25])
    c.drawString(HEADER_P2['seccion'][0], _y(HEADER_P2['seccion'][1]), seccion[:25])
    
    # Tabla de notas
    c.setFont("Helvetica", 8)
    
    for asig_id, asig_data in calificaciones_por_asig.items():
        nombre_asig = _normalizar_nombre_asignatura(asig_data.get('asignatura_nombre', ''))
        
        # Determinar fila correcta
        if nombre_asig in row_y_map:
            y_row = _y(row_y_map[nombre_asig])
        elif asig_data.get('es_salida_optativa') and 'SALIDA OPTATIVA 1' in row_y_map:
            # Solo segundo ciclo tiene SALIDA OPTATIVA
            y_row = _y(row_y_map['SALIDA OPTATIVA 1'])
        else:
            # Asignatura no reconocida o intento de Salida Optativa en primer ciclo
            continue
        
        competencias = asig_data.get('competencias', [])
        if not competencias:
            continue
        
        # 4 competencias × 4 períodos (notas P1-P4 — usando valor_efectivo = max(P,RP))
        for comp in competencias:
            comp_n = getattr(comp, 'competencia_numero', None)
            if not comp_n or comp_n not in COMP_X:
                continue
            for p in range(1, 5):
                valor = comp.valor_periodo(p) if hasattr(comp, 'valor_periodo') else None
                if valor is not None:
                    x = COMP_X[comp_n][f'p{p}']
                    c.drawCentredString(x, y_row - 3, _fmt_nota(valor))
        
        # PC1-PC4
        pcs = asig_data.get('pc_por_periodo', {}) or {}
        for p in range(1, 5):
            v = pcs.get(f'pc{p}')
            if v is not None:
                c.drawCentredString(PC_X[f'pc{p}'], y_row - 3, _fmt_nota(v))
        
        # CF — entero, negrita
        cf = asig_data.get('cf')
        if cf is not None:
            c.setFont("Helvetica-Bold", 8)
            c.drawCentredString(RIGHT_X['cf'], y_row - 3, _fmt_nota(cf, ints_only=True))
            c.setFont("Helvetica", 8)
        
        # Evaluación extra (si existe)
        ev = asig_data.get('evaluacion_extra')
        if ev:
            cec = getattr(ev, 'cec', None)
            ccf = getattr(ev, 'completiva_final', None)
            ceex = getattr(ev, 'ceex', None)
            cexf = getattr(ev, 'extraordinaria_final', None)
            ce = getattr(ev, 'ce', None)
            esp_final = getattr(ev, 'especial_final', None)
            
            if cec is not None or ccf is not None:
                if cf is not None:
                    c.drawCentredString(RIGHT_X['p_cf_50'], y_row - 3, _fmt_nota(cf, ints_only=True))
                if cec is not None:
                    c.drawCentredString(RIGHT_X['cec'], y_row - 3, _fmt_nota(cec, ints_only=True))
                    c.drawCentredString(RIGHT_X['p_cec_50'], y_row - 3, _fmt_nota(cec, ints_only=True))
                if ccf is not None:
                    c.setFont("Helvetica-Bold", 8)
                    c.drawCentredString(RIGHT_X['ccf'], y_row - 3, _fmt_nota(ccf, ints_only=True))
                    c.setFont("Helvetica", 8)
            
            if ceex is not None or cexf is not None:
                if cf is not None:
                    c.drawCentredString(RIGHT_X['p_cf_30'], y_row - 3, _fmt_nota(cf, ints_only=True))
                if ceex is not None:
                    c.drawCentredString(RIGHT_X['ceex'], y_row - 3, _fmt_nota(ceex, ints_only=True))
                    c.drawCentredString(RIGHT_X['p_ceex_70'], y_row - 3, _fmt_nota(ceex, ints_only=True))
                if cexf is not None:
                    c.setFont("Helvetica-Bold", 8)
                    c.drawCentredString(RIGHT_X['cexf'], y_row - 3, _fmt_nota(cexf, ints_only=True))
                    c.setFont("Helvetica", 8)
            
            if ce is not None or esp_final is not None:
                if cf is not None:
                    c.drawCentredString(RIGHT_X['esp_cf'], y_row - 3, _fmt_nota(cf, ints_only=True))
                if ce is not None:
                    c.drawCentredString(RIGHT_X['esp_ce'], y_row - 3, _fmt_nota(ce, ints_only=True))
        
        # A/R por asignatura
        nota_final = None
        if ev:
            nota_final = (getattr(ev, 'nota_final', None) or 
                         getattr(ev, 'especial_final', None) or
                         getattr(ev, 'extraordinaria_final', None) or
                         getattr(ev, 'completiva_final', None))
        if nota_final is None:
            nota_final = cf
        
        if nota_final is not None:
            if nota_final >= 70:
                c.drawCentredString(RIGHT_X['A'], y_row - 3, '1')
            else:
                c.drawCentredString(RIGHT_X['R'], y_row - 3, '1')
    
    # Resumen de asistencia
    if asistencias_por_periodo:
        for p_key in ['p1', 'p2', 'p3', 'p4']:
            data = asistencias_por_periodo.get(p_key) or {}
            y_a = _y(asist_y_map[p_key])
            asis = data.get('asistencia')
            ausen = data.get('ausencia')
            pct_a = data.get('pct_asistencia_anual')
            pct_au = data.get('pct_ausencia_anual')
            if asis is not None:
                c.drawCentredString(ASIST_X['asis'], y_a - 3, str(int(asis)))
            if ausen is not None:
                c.drawCentredString(ASIST_X['ausen'], y_a - 3, str(int(ausen)))
            if pct_a is not None:
                c.drawCentredString(ASIST_X['pct_asis'], y_a - 3, f"{int(round(pct_a))}%")
            if pct_au is not None:
                c.drawCentredString(ASIST_X['pct_ausen'], y_a - 3, f"{int(round(pct_au))}%")
    
    # Situación final del estudiante (Promovido/a o Repitente)
    if situacion_final:
        c.setFont("Helvetica-Bold", 14)
        c.setFillColor(COLOR_DATOS)
        es_promovido = situacion_final.get('promovido', False)
        es_repitente = situacion_final.get('repitente', False)
        if es_promovido:
            c.drawCentredString(SITUACION_PROMOVIDO_X, _y(situacion_y) - 4, 'X')
        if es_repitente:
            c.drawCentredString(SITUACION_REPITENTE_X, _y(situacion_y) - 4, 'X')
        
        # Condición final
        condicion = situacion_final.get('condicion', '')
        if condicion:
            c.setFont("Helvetica", 10)
            lineas = _wrap_text(condicion, ancho_pts=290, font="Helvetica", size=10)
            for i, linea in enumerate(lineas[:3]):
                c.drawString(CONDICION_FINAL_X, _y(condicion_y + i * 14), linea)


# ─────────────────────────────────────────────────────────────────────
# Función pública: generar boletín completo (overlay sobre plantilla)
# ─────────────────────────────────────────────────────────────────────

def generar_boletin_secundaria_minerd(
    estudiante,
    curso,
    calificaciones_por_asig: dict[int, dict[str, Any]],
    asistencias_por_periodo: dict[str, dict[str, Any]] | None = None,
    config=None,
    ano_escolar=None,
    observaciones: str = '',
    situacion_final: dict | None = None,
    docente_nombre: str = '',
) -> io.BytesIO:
    """Genera el boletín MINERD pixel-exacto como io.BytesIO.
    
    Args:
        estudiante: objeto Estudiante con .nombre, .apellido, .sigerd, .numero_orden
        curso: objeto Curso con .grado, .seccion, .tanda, .tutor, .nivel
        calificaciones_por_asig: dict {asignatura_id: {
            'asignatura_nombre': str,
            'competencias': lista de 4 CalificacionSecundaria,
            'pc_por_periodo': {'pc1', 'pc2', 'pc3', 'pc4': float},
            'cf': int,
            'literal': str,
            'evaluacion_extra': EvaluacionExtraSecundaria (opcional),
            'es_salida_optativa': bool (opcional),
        }}
        asistencias_por_periodo: dict {'p1': {'asistencia', 'ausencia', 'pct_asistencia_anual', 'pct_ausencia_anual'}, ...}
        config: ConfiguracionColegio
        ano_escolar: AnoEscolar
        observaciones: texto libre (lado izquierdo de portada)
        situacion_final: {'promovido': bool, 'repitente': bool, 'condicion': str}
    
    Returns:
        io.BytesIO con el PDF generado.
    """
    # 1) Generar overlay (PDF transparente con solo los textos)
    overlay_buf = io.BytesIO()
    c = canvas.Canvas(overlay_buf, pagesize=(PAGE_W, PAGE_H))
    
    # Página 1: portada
    _dibujar_portada(c, estudiante, curso, config, ano_escolar, observaciones, docente_nombre)
    c.showPage()
    
    # Página 2: tabla calificaciones
    _dibujar_tabla_calificaciones(c, estudiante, curso, calificaciones_por_asig,
                                    asistencias_por_periodo or {}, situacion_final)
    c.showPage()
    c.save()
    overlay_buf.seek(0)
    
    # 2) Componer overlay sobre la plantilla oficial MINERD
    plantilla_path = _get_plantilla_path(curso)
    plantilla = PdfReader(plantilla_path)
    overlay = PdfReader(overlay_buf)
    writer = PdfWriter()
    
    for i, page in enumerate(plantilla.pages):
        if i < len(overlay.pages):
            page.merge_page(overlay.pages[i])
        writer.add_page(page)
    
    # 3) Devolver buffer final
    out = io.BytesIO()
    writer.write(out)
    out.seek(0)
    return out
