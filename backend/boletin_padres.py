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


def _fmt_registrada(valor) -> str:
    """Una P o RP tal como se registró: entera si lo es, si no con un decimal."""
    if valor is None:
        return '—'
    from nota_periodo import formatear_nota
    try:
        return formatear_nota(valor)
    except (ValueError, TypeError):
        return '—'


def _valor_periodo(comp, periodo: int):
    """Valor efectivo del período con la regla VIGENTE del nivel de la fila.

    Cada modelo trae la suya: `CalificacionSecundaria.valor_periodo` toma el
    mayor entre P y RP; `CalificacionPrimaria.valor_periodo` toma la RP si
    existe (`calculo_primaria.valor_periodo_primaria`). Antes este reporte
    aplicaba SIEMPRE la de Primaria, también a Secundaria —que es lo que recibe
    hoy—, así que con una RP menor que la P el PC de la competencia salía más
    bajo que en el boletín oficial y en el registro.
    """
    if hasattr(comp, 'valor_periodo'):
        return comp.valor_periodo(periodo)
    from calculo_primaria import valor_periodo_primaria
    return valor_periodo_primaria(
        getattr(comp, f'p{periodo}', None), getattr(comp, f'rp{periodo}', None))


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




RP_FONDO = colors.HexColor('#fdf1e6')     # columnas de recuperación pedagógica
ALTO_LINEA_NOMBRE = 8                     # interlineado del nombre de la asignatura (letra de 7 pt)

# ── Presentación (REP-PADRES-1) ────────────────────────────────────────────
#
# Solo cambia la PRESENTACIÓN. Los valores salen de los mismos helpers de
# arriba (`_fmt_registrada`, `_pc_competencia` con `_valor_periodo`) y la
# tabla conserva su geometría: margen 1,2 cm (≥ 10 mm imprimible), columna de
# asignatura 3,4 cm, columna PC 2,4 cm y 32 celdas P/RP en el ancho restante.
NAVY = colors.HexColor('#16365f')          # títulos y franjas (oscuro: legible en B/N)
NAVY_SUAVE = colors.HexColor('#e9eef6')    # sombreado de encabezados
GRIS_SUAVE = colors.HexColor('#f4f6f9')    # fondo de la ficha del estudiante
LINEA = colors.HexColor('#8c98a8')         # bordes finos (gris medio: se imprime en B/N)
GRIS_ETIQUETA = colors.HexColor('#4a5563')
PC_FONDO = colors.HexColor('#fbf3d6')
PC_CABECERA = colors.HexColor('#f3dc8c')

MARGEN = 1.2 * cm                          # 34 pt ≈ 12 mm por los cuatro lados
COL_ASIG = 3.4 * cm
COL_PC = 2.4 * cm

# Los cuatro grupos de competencias fundamentales del boletín oficial de
# Secundaria (MINERD), en el mismo orden que `competencia_numero` 1-4 y que las
# columnas de `boletin_minerd_secundaria.COMP_X`.
COMPETENCIAS_SECUNDARIA = {
    1: ('Comunicativa',),
    2: ('Pensamiento lógico, creativo y crítico', 'Resolución de problemas'),
    3: ('Científica y tecnológica', 'Ambiental y de la salud'),
    4: ('Ética y ciudadana', 'Desarrollo personal y espiritual'),
}

# Zona inferior de la ÚLTIMA página (de abajo arriba): pie, firmas, leyenda y
# asistencia. La tabla nunca baja de LIMITE_TABLA en ninguna página.
Y_PIE = MARGEN + 1
Y_FIRMA = MARGEN + 34
LINEA_TXT = 9.5                            # interlineado de los textos de 7 pt


def _partir_nombre(c, texto, ancho, fuente, tam):
    """Líneas del nombre que caben en `ancho`, sin perder ningún carácter.

    Corta por palabras; una palabra que sola no cabe se parte por caracteres.
    """
    lineas, actual = [], ''
    for palabra in str(texto).split():
        prueba = (actual + ' ' + palabra).strip()
        if c.stringWidth(prueba, fuente, tam) <= ancho:
            actual = prueba
            continue
        if actual:
            lineas.append(actual)
            actual = ''
        for ch in palabra:
            if actual and c.stringWidth(actual + ch, fuente, tam) > ancho:
                lineas.append(actual)
                actual = ''
            actual += ch
    if actual:
        lineas.append(actual)
    return lineas or ['']


def _partir_segmentos(c, segmentos, separador, ancho, fuente, tam):
    """Une `segmentos` con `separador` en líneas de `ancho`; un segmento no se
    parte salvo que solo ya no quepa (entonces por palabras)."""
    lineas, actual = [], ''
    for seg in segmentos:
        prueba = seg if not actual else actual + separador + seg
        if c.stringWidth(prueba, fuente, tam) <= ancho:
            actual = prueba
            continue
        if actual:
            lineas.append(actual)
        if c.stringWidth(seg, fuente, tam) <= ancho:
            actual = seg
        else:
            partes = _partir_nombre(c, seg, ancho, fuente, tam)
            lineas.extend(partes[:-1])
            actual = partes[-1]
    if actual:
        lineas.append(actual)
    return lineas


def _texto(valor):
    """Texto limpio de un dato configurado; None si está vacío."""
    if valor is None:
        return None
    t = str(valor).strip()
    return t or None


def _attr(obj, *ruta):
    for nombre in ruta:
        if obj is None:
            return None
        try:
            obj = getattr(obj, nombre, None)
        except Exception:
            return None
    return obj


def _cargar_logo(config):
    """ImageReader del logo del colegio (el de ESTA configuración), o None."""
    logo_raw = getattr(config, 'logo', None) if config else None
    if not logo_raw:
        return None
    try:
        if isinstance(logo_raw, str) and 'base64,' in logo_raw:
            logo_b64 = logo_raw.split('base64,', 1)[1]
        else:
            logo_b64 = logo_raw
        img = ImageReader(io.BytesIO(base64.b64decode(re.sub(r'\s+', '', logo_b64))))
        iw, ih = img.getSize()
        return img if iw and ih else None
    except Exception:
        return None


def _datos_centro(config):
    """[(etiqueta, valor)] del centro, SOLO los configurados (nada inventado)."""
    campos = (('Código del centro', 'codigo_centro'), ('Regional', 'regional'), ('Distrito', 'distrito'),
              ('Dirección', 'direccion'), ('Teléfono', 'telefono'))
    return [(et, _texto(getattr(config, attr, None))) for et, attr in campos
            if _texto(getattr(config, attr, None))]


def _datos_estudiante(estudiante, curso, ano_nombre):
    """[(etiqueta, valor)] de la ficha. Se omite lo que no está registrado.

    El n.º de lista solo se muestra si es el de ESTE curso (en un reporte de un
    curso anterior, el número de la ficha sería el de su curso actual)."""
    nombre = f'{estudiante.nombre} {estudiante.apellido}'.strip().upper()
    matricula = _texto(getattr(estudiante, 'sigerd', None)) or _texto(getattr(estudiante, 'matricula', None))
    no_lista = None
    if getattr(estudiante, 'no_lista', None) and curso is not None \
            and getattr(estudiante, 'curso_id', None) == getattr(curso, 'id', object()):
        no_lista = str(estudiante.no_lista)
    datos = [('Estudiante', nombre), ('Grado', _texto(_attr(curso, 'grado', 'nombre'))),
             ('Sección', _texto(_attr(curso, 'nombre'))), ('Tanda', _texto(_attr(curso, 'tanda', 'nombre'))),
             ('N.º de lista', no_lista), ('Matrícula', matricula), ('Año escolar', _texto(ano_nombre))]
    return [(et, v) for et, v in datos if v]


def generar_boletin_padres(estudiante, curso, asignaturas_data, config,
                            ano_nombre: str, asistencia_anual=None) -> io.BytesIO:
    """Genera el reporte de calificaciones para los padres en PDF (carta apaisada).

    asignaturas_data: lista de dicts, cada uno:
        {
          'nombre': 'Lengua Española',
          'competencias': { 1: comp_obj, 2: comp_obj, 3: comp_obj, 4: comp_obj }
        }
        donde comp_obj tiene atributos p1,rp1,p2,rp2,p3,rp3,p4,rp4
        (o None si esa competencia no tiene datos).

    Todo se dibuja dentro de un margen de 1,2 cm por lado, así que se imprime
    al 100 % sin «ajustar a página». La paginación se calcula ANTES de dibujar:
    si un caso excepcional no cabe en una página, la siguiente repite la
    identificación del estudiante y el encabezado de la tabla, y la
    asistencia, la leyenda y las firmas van al final de la última.
    """
    buf = io.BytesIO()
    W, H = landscape(letter)  # 792 x 612
    c = canvas.Canvas(buf, pagesize=(W, H))
    c.setTitle('Reporte de calificaciones')

    margin = MARGEN
    ancho_util = W - 2 * margin
    tabla_x = margin
    col_asig, col_pc = COL_ASIG, COL_PC
    # 4 competencias x 4 períodos x (P, RP) = 32 celdas en el ancho restante.
    col_parcial = (ancho_util - col_asig - col_pc) / 32
    col_comp = col_parcial * 8
    nombre_colegio = _texto(getattr(config, 'nombre', None)) or 'Colegio'
    datos_est = _datos_estudiante(estudiante, curso, ano_nombre)
    hoy = date.today().strftime('%d/%m/%Y')

    # ─── Zona inferior (última página): asistencia + leyenda, sobre las firmas ───
    leyenda = [
        ('Cómo leer este reporte:',
         'P = nota del período.   RP (al lado de su P) = recuperación pedagógica de ese período, si se hizo.   '
         '— = sin nota registrada (en una columna RP: sin recuperación).'),
        (None, 'El PC (Promedio por Competencia) aparece solo cuando los 4 períodos de esa competencia están completos; '
               'cuando hay recuperación, cada período cuenta con la nota que establece la norma vigente.'),
        (None, 'Este reporte refleja el estado actual de las calificaciones.'),
    ]
    x_ley = margin + 8
    ancho_ley = ancho_util - 16
    lineas_ley = []                       # [(etiqueta|None, texto)]
    for etiqueta, texto in leyenda:
        sangria = (c.stringWidth(etiqueta, 'Helvetica-Bold', 7) + 6) if etiqueta else 0
        partes = _partir_nombre(c, texto, ancho_ley - sangria, 'Helvetica', 7)
        lineas_ley.append((etiqueta, sangria, partes[0]))
        lineas_ley.extend((None, sangria, p) for p in partes[1:])
    alto_ley = len(lineas_ley) * LINEA_TXT + 8

    lineas_asis = []
    x_asis = margin + 94
    if asistencia_anual is not None:
        if asistencia_anual.get('sin_registros'):
            # Un 0 % aquí le diría al padre que su hijo no fue nunca.
            segs = ['Sin registros de asistencia para este año escolar.']
        else:
            _pa = asistencia_anual.get('pct_asistencia')
            _pau = asistencia_anual.get('pct_ausencia')
            segs = ['Asistencias: %d' % asistencia_anual.get('asistencias', 0),
                    'Tardanzas: %d' % asistencia_anual.get('tardanzas', 0),
                    'Ausencias: %d' % asistencia_anual.get('ausencias', 0),
                    'Excusas: %d' % asistencia_anual.get('excusas', 0)]
            if _pa is not None and _pau is not None:
                segs += ['Asistencia: %.1f%%' % _pa, 'Ausencia: %.1f%%' % _pau]
            else:
                segs.append('Porcentaje: N/D')
            _lect = asistencia_anual.get('dias_lectivos')
            if _lect:
                segs.append('Cobertura: %d de %d días registrados'
                            % (asistencia_anual.get('dias_computados') or 0, _lect))
        lineas_asis = _partir_segmentos(c, segs, '   ·   ', W - margin - 8 - x_asis, 'Helvetica', 7)
    alto_asis = (len(lineas_asis) * LINEA_TXT + 8) if lineas_asis else 0

    y_ley_base = Y_FIRMA + 14                          # borde inferior de la leyenda
    y_asis_base = y_ley_base + alto_ley + 5
    limite_tabla = y_asis_base + alto_asis + (6 if alto_asis else 1)

    # ─── Encabezado de la tabla: alto según los nombres de las competencias ───
    tam_comp = 6.5
    lineas_comp = {}
    for n, grupos in COMPETENCIAS_SECUNDARIA.items():
        ls = []
        for g in grupos:
            ls.extend(_partir_nombre(c, g, col_comp - 6, 'Helvetica-Bold', tam_comp))
        lineas_comp[n] = ls
    alto_comp = max(20, max(len(v) for v in lineas_comp.values()) * 7.5 + 6)
    alto_sub = 12
    alto_franja = 14
    alto_cab_tabla = alto_franja + alto_comp + alto_sub

    def _encabezado_tabla(y_top):
        """«COMPETENCIAS FUNDAMENTALES» + Asignatura | 4 grupos x (P1 RP1 … P4 RP4) | PC.
        Como en el Registro, la RP de cada período va AL LADO de su P."""
        c.setLineWidth(0.4)
        c.setStrokeColor(LINEA)
        c.setFillColor(NAVY)
        c.rect(tabla_x, y_top - alto_franja, ancho_util, alto_franja, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont('Helvetica-Bold', 8.5)
        c.drawCentredString(tabla_x + ancho_util / 2, y_top - alto_franja + 4.3, 'COMPETENCIAS FUNDAMENTALES')
        y1 = y_top - alto_franja
        alto = alto_comp + alto_sub
        c.setFillColor(NAVY_SUAVE)
        c.rect(tabla_x, y1 - alto, col_asig, alto, fill=1, stroke=1)
        c.setFillColor(NAVY)
        c.setFont('Helvetica-Bold', 8)
        c.drawString(tabla_x + 4, y1 - alto / 2 - 3, 'Asignatura')
        cx = tabla_x + col_asig
        for n in range(1, 5):
            c.setFillColor(NAVY_SUAVE)
            c.rect(cx, y1 - alto_comp, col_comp, alto_comp, fill=1, stroke=1)
            c.setFillColor(NAVY)
            c.setFont('Helvetica-Bold', tam_comp)
            ls = lineas_comp[n]
            y_l = y1 - alto_comp / 2 + (len(ls) * 7.5) / 2 - 6
            for linea in ls:
                c.drawCentredString(cx + col_comp / 2, y_l, linea)
                y_l -= 7.5
            c.setFont('Helvetica-Bold', 6)
            for k in range(8):
                px = cx + k * col_parcial
                es_rp = k % 2 == 1
                c.setFillColor(RP_FONDO if es_rp else colors.white)
                c.rect(px, y1 - alto, col_parcial, alto_sub, fill=1, stroke=1)
                c.setFillColor(colors.black)
                c.drawCentredString(px + col_parcial / 2, y1 - alto + 3.8,
                                    ('RP%d' if es_rp else 'P%d') % (k // 2 + 1))
            cx += col_comp
        c.setFillColor(PC_CABECERA)
        c.rect(cx, y1 - alto, col_pc, alto, fill=1, stroke=1)
        c.setFillColor(colors.black)
        c.setFont('Helvetica-Bold', 9)
        c.drawCentredString(cx + col_pc / 2, y1 - alto / 2 + 1.5, 'PC')
        c.setFont('Helvetica', 6.5)
        c.drawCentredString(cx + col_pc / 2, y1 - alto / 2 - 7, '(1·2·3·4)')
        # Separación más marcada entre grupos (también en B/N).
        c.setLineWidth(0.9)
        c.setStrokeColor(NAVY)
        for k in range(5):
            gx = tabla_x + col_asig + k * col_comp
            c.line(gx, y1, gx, y1 - alto)
        c.setLineWidth(0.4)
        c.setStrokeColor(LINEA)
        return y_top - alto_cab_tabla

    # ─── Encabezado institucional (primera página) ───
    logo = _cargar_logo(config)
    centro = _datos_centro(config)
    nivel = (_texto(_attr(curso, 'grado', 'nivel')) or '').lower()
    subtitulo = {'secundaria': 'Nivel Secundario', 'primaria': 'Nivel Primario'}.get(nivel)

    LOGO_MAX_W, LOGO_MAX_H = 88, 50
    if logo is not None:
        iw, ih = logo.getSize()
        r = min(LOGO_MAX_W / iw, LOGO_MAX_H / ih)
        logo_w, logo_h = iw * r, ih * r
    else:
        logo_w = logo_h = 0
    ancho_centro = 0
    lineas_centro = []          # cada línea: [(etiqueta|None, texto)]
    TAM_C, SEP_C = 7.5, 14

    def _w_item(et, v):
        return c.stringWidth((et + ': ') if et else '', 'Helvetica', TAM_C) + c.stringWidth(v, 'Helvetica', TAM_C)
    if centro:
        # Ancho según el contenido (dato más largo), entre 200 y 330 pt.
        ancho_centro = min(330, max(200, max(_w_item(et, v) for et, v in centro)))
        actual, w_actual = [], 0
        for et, v in centro:
            w = _w_item(et, v)
            if actual and w_actual + SEP_C + w <= ancho_centro:
                actual.append((et, v))
                w_actual += SEP_C + w
                continue
            if actual:
                lineas_centro.append(actual)
            if w <= ancho_centro:
                actual, w_actual = [(et, v)], w
            else:
                # Un dato que solo no cabe (una dirección larga) se parte dentro
                # de su propio bloque, sin compartir línea con otro dato.
                w_et = c.stringWidth(et + ': ', 'Helvetica', TAM_C)
                partes = _partir_nombre(c, v, ancho_centro - w_et, 'Helvetica', TAM_C)
                lineas_centro.append([(et, partes[0])])
                lineas_centro.extend([[(None, p, w_et)] for p in partes[1:]])
                actual, w_actual = [], 0
        if actual:
            lineas_centro.append(actual)
    tx = margin + (logo_w + 10 if logo is not None else 0)
    x_sep = W - margin - ancho_centro - 12 if centro else W - margin
    ancho_nombre = x_sep - tx - 10
    tam_nombre = 15
    while tam_nombre > 11 and c.stringWidth(nombre_colegio, 'Helvetica-Bold', tam_nombre) > ancho_nombre:
        tam_nombre -= 0.5
    lineas_nombre = _partir_nombre(c, nombre_colegio, ancho_nombre, 'Helvetica-Bold', tam_nombre)
    alto_bloque_nombre = len(lineas_nombre) * (tam_nombre + 2) + (12 if subtitulo else 0)
    alto_cab = max(LOGO_MAX_H, alto_bloque_nombre, len(lineas_centro) * 10.5) + 4

    # ─── Ficha del estudiante: celdas «Etiqueta: valor» ───
    tam_ficha = 8

    def _ancho_celda(et, v):
        return (c.stringWidth(et + ': ', 'Helvetica-Bold', tam_ficha)
                + c.stringWidth(v, 'Helvetica', tam_ficha) + 14)

    def _fila_ficha(items):
        """Celdas de una fila de la ficha a lo ancho útil. Solo el NOMBRE del
        estudiante puede partirse en líneas; los demás datos nunca se cortan."""
        anchos = [_ancho_celda(et, v) for et, v in items]
        libre = ancho_util - sum(anchos)
        if libre >= 0:
            if items[0][0] == 'Estudiante':
                anchos[0] += libre * 0.6
                resto_n = len(anchos) - 1
                for k in range(1, len(anchos)):
                    anchos[k] += libre * 0.4 / max(1, resto_n)
                if resto_n == 0:
                    anchos[0] += libre * 0.4
            else:
                anchos = [a + libre / len(anchos) for a in anchos]
        else:
            anchos[0] = max(ancho_util - sum(anchos[1:]), 120)
        celdas_f = []
        for (et, v), a in zip(items, anchos):
            w_et = c.stringWidth(et + ': ', 'Helvetica-Bold', tam_ficha)
            ls = _partir_nombre(c, v, a - 12 - w_et, 'Helvetica', tam_ficha)
            celdas_f.append((et, ls, a, w_et))
        return celdas_f, max(len(ls) for _, ls, _, _ in celdas_f) * 10 + 9

    if sum(_ancho_celda(et, v) for et, v in datos_est) <= ancho_util:
        filas_ficha = [_fila_ficha(datos_est)]
    else:
        # No cabe en una fila: nombre, matrícula y año arriba; grado, sección,
        # tanda y n.º de lista abajo.
        arriba = [d for d in datos_est if d[0] in ('Estudiante', 'Matrícula', 'Año escolar')]
        abajo = [d for d in datos_est if d not in arriba]
        filas_ficha = [_fila_ficha(arriba)] + ([_fila_ficha(abajo)] if abajo else [])
    alto_ficha = sum(h for _, h in filas_ficha)

    def _ficha(y_top):
        c.setLineWidth(0.4)
        c.setStrokeColor(LINEA)
        y_f = y_top
        for celdas_f, alto_f in filas_ficha:
            x = margin
            for et, ls, a, w_et in celdas_f:
                c.setFillColor(GRIS_SUAVE)
                c.rect(x, y_f - alto_f, a, alto_f, fill=1, stroke=1)
                y_l = y_f - alto_f / 2 + (len(ls) * 10) / 2 - 7.5
                c.setFillColor(GRIS_ETIQUETA)
                c.setFont('Helvetica-Bold', tam_ficha)
                c.drawString(x + 6, y_l, et + ':')
                c.setFillColor(colors.black)
                c.setFont('Helvetica', tam_ficha)
                for linea in ls:
                    c.drawString(x + 6 + w_et, y_l, linea)
                    y_l -= 10
                x += a
            y_f -= alto_f
        return y_top - alto_ficha

    def _cabecera_primera():
        y0 = H - margin
        if logo is not None:
            c.drawImage(logo, margin, y0 - alto_cab / 2 - logo_h / 2, width=logo_w, height=logo_h,
                        mask='auto', preserveAspectRatio=True)
        y_n = y0 - alto_cab / 2 + alto_bloque_nombre / 2 - tam_nombre + 1
        c.setFillColor(NAVY)
        c.setFont('Helvetica-Bold', tam_nombre)
        for linea in lineas_nombre:
            c.drawString(tx, y_n, linea)
            y_n -= tam_nombre + 2
        if subtitulo:
            c.setFont('Helvetica', 9.5)
            c.setFillColor(GRIS_ETIQUETA)
            c.drawString(tx, y_n + 1, subtitulo)
        if centro:
            c.setStrokeColor(LINEA)
            c.setLineWidth(0.6)
            c.line(x_sep, y0 - 2, x_sep, y0 - alto_cab + 2)
            y_c = y0 - alto_cab / 2 + len(lineas_centro) * 10.5 / 2 - 8
            c.setFont('Helvetica', TAM_C)
            for linea in lineas_centro:
                x_c = x_sep + 12
                # «Etiqueta:» en gris, valor en negro; la continuación de un
                # dato partido se alinea con su valor.
                for item in linea:
                    et, v = item[0], item[1]
                    if et:
                        c.setFillColor(GRIS_ETIQUETA)
                        c.drawString(x_c, y_c, et + ': ')
                        x_c += c.stringWidth(et + ': ', 'Helvetica', TAM_C)
                    else:
                        x_c += item[2]          # continuación: alineada con su valor
                    c.setFillColor(colors.black)
                    c.drawString(x_c, y_c, v)
                    x_c += c.stringWidth(v, 'Helvetica', TAM_C) + SEP_C
                y_c -= 10.5
        y = y0 - alto_cab - 3
        c.setStrokeColor(NAVY)
        c.setLineWidth(1.2)
        c.line(margin, y, W - margin, y)
        y -= 19
        c.setFillColor(NAVY)
        c.setFont('Helvetica-Bold', 15)
        c.drawCentredString(W / 2, y, 'REPORTE DE CALIFICACIONES')
        return _ficha(y - 9) - 7

    # Cabecera de las páginas siguientes: el título conserva su sitio a la
    # derecha y el nombre del centro ocupa el resto, en las líneas que necesite
    # (un nombre de hasta 200 caracteres no se monta sobre el título ni sale
    # del margen). Su alto real entra en la paginación (`_inicio_tabla`).
    TITULO_CONT = 'REPORTE DE CALIFICACIONES (continuación)'
    LINEA_CONT = 11
    ancho_tit_cont = c.stringWidth(TITULO_CONT, 'Helvetica-Bold', 9)
    lineas_cont = _partir_nombre(c, nombre_colegio, ancho_util - ancho_tit_cont - 18, 'Helvetica-Bold', 9)
    alto_cab_cont = 19 + (len(lineas_cont) - 1) * LINEA_CONT      # 19 con una línea, como antes

    def _cabecera_continuacion():
        """Páginas siguientes: centro, título y la identificación completa."""
        y0 = H - margin
        c.setFillColor(NAVY)
        c.setFont('Helvetica-Bold', 9)
        y_l = y0 - 9
        for linea in lineas_cont:
            c.drawString(margin, y_l, linea)
            y_l -= LINEA_CONT
        c.drawRightString(W - margin, y0 - 9, TITULO_CONT)
        y_regla = y0 - alto_cab_cont + 5
        c.setStrokeColor(NAVY)
        c.setLineWidth(0.8)
        c.line(margin, y_regla, W - margin, y_regla)
        return _ficha(y0 - alto_cab_cont) - 7

    # ─── Filas: alto de cada una (el nombre completo, en las líneas que necesite) ───
    ancho_nombre_asig = col_asig - 6          # 3 pt de margen a cada lado: nunca invade P/RP
    filas = []
    for asig in asignaturas_data:
        lineas = _partir_nombre(c, asig['nombre'], ancho_nombre_asig, 'Helvetica', 7)
        filas.append((asig, lineas, max(18, ALTO_LINEA_NOMBRE * len(lineas) + 6)))

    # ─── Paginación, calculada antes de dibujar ───
    def _inicio_tabla(primera):
        return (H - margin - alto_cab - 3 - 19 - 9 - alto_ficha - 7 if primera
                else H - margin - alto_cab_cont - alto_ficha - 7) - alto_cab_tabla
    # Las páginas intermedias llegan hasta el pie; la ÚLTIMA deja sitio para
    # asistencia, leyenda y firmas. Si lo que queda no cabe ahí, sus últimas
    # filas pasan a una página más (que repite identificación y encabezado).
    limite_intermedia = Y_PIE + 14
    paginas = [[]]
    y_disp = _inicio_tabla(True)
    for fila in filas:
        if y_disp - fila[2] < limite_intermedia and paginas[-1]:
            paginas.append([])
            y_disp = _inicio_tabla(False)
        paginas[-1].append(fila)
        y_disp -= fila[2]
    if y_disp < limite_tabla:
        # La última fila pasa a una página nueva junto con el cierre (nunca
        # queda una página con solo firmas: lleva al menos esa fila).
        paginas.append([paginas[-1].pop()] if len(paginas[-1]) > 1 else [])
    total = len(paginas)

    def _pie(n):
        c.setFont('Helvetica', 6)
        c.setFillColor(GRIS_TEXTO)
        texto = f'Documento generado por EducaOne — Sistema de Gestión Escolar  •  Fecha de emisión: {hoy}'
        if total > 1:
            texto += f'  •  Página {n} de {total}'
        c.drawCentredString(W / 2, Y_PIE, texto)

    for n_pag, filas_pag in enumerate(paginas, start=1):
        y_tab = _cabecera_primera() if n_pag == 1 else _cabecera_continuacion()
        row_y = _encabezado_tabla(y_tab)
        # En cada competencia y período, la nota original P y su recuperación RP
        # van en columnas contiguas (como en el Registro), «—» si no la hubo:
        # ninguna sustituye visualmente a la otra.
        for asig, lineas, row_h in filas_pag:
            row_y -= row_h
            c.setLineWidth(0.4)
            c.setStrokeColor(LINEA)
            c.setFillColor(colors.white)
            c.rect(tabla_x, row_y, col_asig, row_h, fill=1, stroke=1)
            c.setFillColor(colors.black)
            c.setFont('Helvetica', 7)
            alto_texto = ALTO_LINEA_NOMBRE * len(lineas)
            y_linea = row_y + (row_h + alto_texto) / 2 - 6.5      # centrado vertical
            for linea in lineas:
                c.drawString(tabla_x + 3, y_linea, linea)
                y_linea -= ALTO_LINEA_NOMBRE

            cx = tabla_x + col_asig
            pcs = []
            for comp_num in range(1, 5):
                comp = asig['competencias'].get(comp_num)
                for i in range(1, 5):
                    for k, campo in ((0, 'p'), (1, 'rp')):
                        px = cx + ((i - 1) * 2 + k) * col_parcial
                        val = getattr(comp, f'{campo}{i}', None) if comp else None
                        c.setFillColor(RP_FONDO if k else colors.white)
                        c.rect(px, row_y, col_parcial, row_h, fill=1, stroke=1)
                        c.setFillColor(GRIS_TEXTO if val is None else colors.black)
                        c.setFont('Helvetica', 7)
                        # La nota TAL COMO SE REGISTRÓ (81.5 se ve 81.5, no 82).
                        c.drawCentredString(px + col_parcial / 2, row_y + row_h / 2 - 2.4, _fmt_registrada(val))
                # PC de esta competencia (regla vigente del nivel, ver _valor_periodo)
                pcs.append(_pc_competencia(comp) if comp else None)
                cx += col_comp

            c.setFillColor(PC_FONDO)
            c.rect(cx, row_y, col_pc, row_h, fill=1, stroke=1)
            c.setFillColor(colors.black)
            c.setFont('Helvetica-Bold', 7)
            c.drawCentredString(cx + col_pc / 2, row_y + row_h / 2 - 2.4, ' · '.join(_fmt(p) for p in pcs))
            c.setLineWidth(0.9)
            c.setStrokeColor(NAVY)
            for k in range(5):
                gx = tabla_x + col_asig + k * col_comp
                c.line(gx, row_y, gx, row_y + row_h)
        # Borde exterior de la tabla.
        c.setLineWidth(0.8)
        c.setStrokeColor(NAVY)
        c.rect(tabla_x, row_y, ancho_util, y_tab - alto_franja - row_y, fill=0, stroke=1)

        if n_pag == total:
            # ─── Asistencia anual ───
            # ENTREGA-1 · las cuatro cuentas, los dos porcentajes y la
            # cobertura, del mismo cálculo que los PDF oficiales.
            if lineas_asis:
                c.setFillColor(colors.HexColor('#eef4ee'))
                c.setStrokeColor(LINEA)
                c.setLineWidth(0.4)
                c.rect(margin, y_asis_base, ancho_util, alto_asis, fill=1, stroke=1)
                c.setFillColor(NAVY)
                c.setFont('Helvetica-Bold', 7.5)
                y_l = y_asis_base + alto_asis - 4 - 7
                c.drawString(margin + 8, y_l, 'ASISTENCIA ANUAL')
                c.setFillColor(colors.black)
                c.setFont('Helvetica', 7)
                for linea in lineas_asis:
                    c.drawString(x_asis, y_l, linea)
                    y_l -= LINEA_TXT
            # ─── Leyenda ───
            c.setFillColor(GRIS_SUAVE)
            c.setStrokeColor(LINEA)
            c.setLineWidth(0.4)
            c.rect(margin, y_ley_base, ancho_util, alto_ley, fill=1, stroke=1)
            y_l = y_ley_base + alto_ley - 4 - 7
            for etiqueta, sangria, texto in lineas_ley:
                if etiqueta:
                    c.setFillColor(NAVY)
                    c.setFont('Helvetica-Bold', 7)
                    c.drawString(x_ley, y_l, etiqueta)
                c.setFillColor(colors.black)
                c.setFont('Helvetica', 7)
                c.drawString(x_ley + sangria, y_l, texto)
                y_l -= LINEA_TXT
            # ─── Firmas ───
            c.setStrokeColor(colors.black)
            c.setLineWidth(0.5)
            c.setFillColor(colors.black)
            c.setFont('Helvetica', 8)
            c.line(margin + 40, Y_FIRMA, margin + 230, Y_FIRMA)
            c.drawCentredString(margin + 135, Y_FIRMA - 10, 'Firma del Director / Sello')
            c.line(W - margin - 230, Y_FIRMA, W - margin - 40, Y_FIRMA)
            c.drawCentredString(W - margin - 135, Y_FIRMA - 10, 'Firma del Padre/Tutor')
        _pie(n_pag)
        c.showPage()

    c.save()
    buf.seek(0)
    return buf
