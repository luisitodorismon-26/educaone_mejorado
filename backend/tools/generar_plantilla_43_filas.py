"""REG-43 · Herramienta OFFLINE: fabrica la plantilla de 1ro de Secundaria con 43
filas a partir de la plantilla oficial de 40. No se ejecuta en el servidor: la
plantilla resultante se versiona como archivo fijo
(templates/registro_escolar/Registro-1er-Grado-Sec-General-43-filas.pdf) y el
generador solo la LEE. Requiere PyMuPDF, que no está en requirements.txt a
propósito.

Para cada página con tabla de 40 filas (franja detectada por sus 41 líneas
equiespaciadas):
  1. se mide lo que hay DENTRO de la franja: segmentos horizontales y
     verticales (con grosor y color), celdas sombreadas y los números de fila
     (fuente, tamaño, color, posición);
  2. se quita solo lo que cae COMPLETO dentro de la franja (redacción sin
     relleno: no pinta nada encima);
  3. se redibuja: los sombreados por celda, 44 líneas horizontales con el patrón
     de la original, las verticales en sus mismas x y los números 1..43 con la
     fuente de la plantilla.
Lo que está fuera de la franja (encabezados, TOTALES, pie, firmas) no se toca.

Uso: python tools/generar_plantilla_43_filas.py <plantilla.pdf> <salida.pdf> <informe.json> [filas=43]
"""
import collections
import json
import sys

import pymupdf

SRC, DST, INFORME = sys.argv[1], sys.argv[2], sys.argv[3]
N = int(sys.argv[4]) if len(sys.argv) > 4 else 43
doc = pymupdf.open(SRC)


def franja(p):
    hs = sorted({round(it[1].y, 1) for d in p.get_drawings() for it in d['items']
                 if it[0] == 'l' and abs(it[1].y - it[2].y) < 0.2 and it[1].y > 150})
    mejor = []
    for i in range(len(hs)):
        seq = [hs[i]]
        for y in hs[i + 1:]:
            if (13.6 if len(seq) < 40 else 11.5) < (y - seq[-1]) < 14.75:
                seq.append(y)
            elif y - seq[-1] >= 14.75:
                break
        if len(seq) > len(mejor):
            mejor = seq
    return mejor[:41] if len(mejor) >= 41 else None


informe = {}
fuentes_cache = {}
for pno in range(len(doc)):
    p = doc[pno]
    lineas = franja(p)
    if not lineas:
        continue
    y0, y1 = lineas[0], lineas[-1]
    dentro = lambda r: r.y0 >= y0 - 0.6 and r.y1 <= y1 + 0.6  # noqa: E731
    horiz = collections.defaultdict(list)      # índice de línea -> [(x0, x1, w, color)]
    vert = collections.defaultdict(list)       # x -> [(w, color)]
    for d in p.get_drawings():
        for it in d['items']:
            if it[0] != 'l':
                continue
            a, b = it[1], it[2]
            seg = pymupdf.Rect(min(a.x, b.x), min(a.y, b.y), max(a.x, b.x), max(a.y, b.y))
            if not dentro(seg):
                continue
            w, col = d.get('width') or 0.5, d.get('color') or (0, 0, 0)
            if abs(a.y - b.y) < 0.2:
                k = min(range(41), key=lambda j: abs(lineas[j] - a.y))
                horiz[k].append((round(seg.x0, 2), round(seg.x1, 2), w, tuple(col)))
            elif abs(a.x - b.x) < 0.2:
                vert[round(a.x, 2)].append((w, tuple(col)))
    # Números de fila (texto dentro de la franja)
    nums = []
    for blk in p.get_text('dict')['blocks']:
        for ln in blk.get('lines', []):
            for sp in ln['spans']:
                t = sp['text'].strip()
                bb = pymupdf.Rect(sp['bbox'])
                if t.isdigit() and dentro(bb):
                    fila = int((bb.y0 + bb.y1) / 2 - y0) // ((y1 - y0) / 40)
                    nums.append(dict(t=t, fila=int(fila), font=sp['font'], size=sp['size'], color=sp['color'],
                                     cx=(bb.x0 + bb.x1) / 2, base=sp['origin'][1], top_fila=y0 + fila * (y1 - y0) / 40))
    # Rellenos por celda (columnas sombreadas): un rectángulo por fila dentro de la franja
    celdas = collections.Counter()
    for d in p.get_drawings():
        if d.get('fill') is None:
            continue
        for it in d['items']:
            if it[0] == 're' and dentro(it[1]):
                celdas[(round(it[1].x0, 2), round(it[1].x1, 2), tuple(d['fill']), d.get('fill_opacity') or 1)] += 1
    columnas_grises = [k for k, n in celdas.items() if n >= 30]
    celdas_sueltas = {str(k): n for k, n in celdas.items() if n < 30}
    # Fuente de los números ANTES de redactar: si los números eran el único texto
    # con esa fuente, la redacción la saca de los recursos de la página.
    xref_fuente = None
    if nums:
        _ref = collections.Counter((n['font'], round(n['size'], 2), n['color']) for n in nums).most_common(1)[0][0]
        # Puede haber varias fuentes con el mismo nombre (CID y TrueType): sirve la
        # que se puede extraer y trae los diez dígitos.
        for f in p.get_fonts():
            if _ref[0] not in f[3]:
                continue
            try:
                _buf = doc.extract_font(f[0])[3]
                _fo = pymupdf.Font(fontbuffer=_buf) if _buf else None
            except Exception:
                _fo = None
            if _fo and all(_fo.has_glyph(ord(c)) for c in '0123456789'):
                xref_fuente = f[0]
                fuentes_cache[f[0]] = _buf
                break
    # Verticales: una x cuenta si aparece en casi todas las filas
    xs_vert = {x: collections.Counter(v).most_common(1)[0][0] for x, v in vert.items() if len(v) >= 30}
    raras = {x: len(v) for x, v in vert.items() if len(v) < 30}
    patron = lambda k: sorted(set(horiz.get(k) or []))  # noqa: E731
    interior = collections.Counter(tuple(patron(k)) for k in range(1, 40)).most_common(1)[0][0]
    distintos = [k for k in range(1, 40) if tuple(patron(k)) != interior]

    # 2. Quitar lo que cae completo dentro de la franja (sin pintar encima)
    p.add_redact_annot(pymupdf.Rect(0, y0 - 0.6, p.rect.width, y1 + 0.6), fill=False)
    p.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                       graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
                       text=pymupdf.PDF_REDACT_TEXT_REMOVE)

    # 3. Redibujar: primero los rellenos, debajo de las líneas
    h = (y1 - y0) / N
    if columnas_grises:
        sf = p.new_shape()
        for x0, x1, fill, op in columnas_grises:
            for j in range(N):
                sf.draw_rect(pymupdf.Rect(x0, y0 + j * h, x1, y0 + (j + 1) * h))
                sf.finish(color=None, fill=fill, fill_opacity=op, width=0)
        sf.commit()
    sh = p.new_shape()
    for j in range(N + 1):
        segs = patron(0) if j == 0 else (patron(40) if j == N else list(interior))
        y = y0 + j * h
        for x0, x1, w, col in segs:
            sh.draw_line((x0, y), (x1, y))
            sh.finish(width=w, color=col)
    for x, (w, col) in sorted(xs_vert.items()):
        sh.draw_line((x, y0), (x, y1))
        sh.finish(width=w, color=col)
    sh.commit()
    if nums:
        ref = collections.Counter((n['font'], round(n['size'], 2), n['color']) for n in nums).most_common(1)[0][0]
        cx = sorted(n['cx'] for n in nums)[len(nums) // 2]
        desplaz = sorted(n['base'] - (n['top_fila'] + (y1 - y0) / 80) for n in nums)[len(nums) // 2]
        # Fuente de la plantilla (subconjunto: trae los 10 dígitos porque 1..40 los usa todos)
        xref = xref_fuente
        fname = 'helv'
        if xref:
            if xref not in fuentes_cache:
                nombre, ext, _, buf = doc.extract_font(xref)
                fuentes_cache[xref] = buf
            fname = 'F43_%d' % xref
            p.insert_font(fontname=fname, fontbuffer=fuentes_cache[xref])
        fobj = pymupdf.Font(fontbuffer=fuentes_cache[xref]) if xref else pymupdf.Font('helv')
        rgb = tuple(((ref[2] >> s) & 255) / 255 for s in (16, 8, 0))
        for i in range(N):
            t = str(i + 1)
            ancho = fobj.text_length(t, fontsize=ref[1])
            p.insert_text((cx - ancho / 2, y0 + i * h + h / 2 + desplaz), t, fontname=fname,
                          fontsize=ref[1], color=rgb)
    informe[pno + 1] = dict(y0=y0, y1=y1, alto_fila_original=round((y1 - y0) / 40, 3), alto_fila_nuevo=round(h, 3),
                            verticales=len(xs_vert), verticales_irregulares=raras,
                            horizontales_patron_distinto=distintos,
                            numeros=len(nums), fuente_numeros=(nums and [nums[0]['font'], nums[0]['size']]) or None,
                            columnas_sombreadas=len(columnas_grises), celdas_sombreadas_sueltas=celdas_sueltas,
                            fuente_reutilizada=bool(xref_fuente))

doc.save(DST, garbage=4, deflate=True, deflate_fonts=True)
json.dump(informe, open(INFORME, 'w'), indent=1)
print('páginas adaptadas:', len(informe))
for k, v in informe.items():
    if v['verticales_irregulares'] or v['horizontales_patron_distinto'] or v['celdas_sombreadas_sueltas']             or (v['numeros'] and not v['fuente_reutilizada']):
        print('  revisar pág', k, v)
