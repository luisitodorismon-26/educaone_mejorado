"""SALIDAS-MIXTAS — FILA COMPACTA del boletín de 4to-6to (generador real, sin base).

Caso: las dos filas de Salida Optativa ocupadas por los componentes y una
materia del colegio con notas (Música). Para 4to, 5to y 6to comprueba que:
  * todo lo que está ENCIMA de la tabla y DEBAJO de la fila (asistencia,
    leyenda, situación final, firmas) es idéntico píxel a píxel al mismo
    boletín sin Música: la fila no tapa ni desplaza nada;
  * todo lo de la fila queda dentro de su franja (416.9-432.4);
  * Música imprime sus 16 notas, PC1-PC4, CF y la condición en A o en R con
    las reglas de siempre;
  * la cuadrícula y el color son los de la plantilla de cada grado.

Uso (desde backend/):  python tools/test_boletin_fila_compacta.py [carpeta_pdfs]
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix='fila_compacta_')
os.makedirs(OUT, exist_ok=True)
import pymupdf
import boletin_minerd_secundaria as B


class Comp:
    def __init__(self, n, vals):
        self.competencia_numero, self.vals = n, vals

    def valor_periodo(self, p):
        return self.vals[p - 1]


class Obj:
    def __init__(self, **k):
        self.__dict__.update(k)


def materia(nombre, base, area=None, so=None):
    comps = [Comp(c, [base + c + p for p in (1, 2, 3, 4)]) for c in (1, 2, 3, 4)]
    pcs = {'pc%d' % c: sum(base + c + p for p in (1, 2, 3, 4)) / 4 for c in (1, 2, 3, 4)}
    cf = round(sum(pcs.values()) / 4)
    d = {'asignatura_nombre': nombre, 'competencias': comps, 'pc_por_periodo': pcs, 'cf': cf, 'cf_exacto': cf,
         'literal': '', 'evaluacion_extra': None, 'area_curricular_codigo': area}
    if so is not None:
        d.update(es_salida_optativa=True, so_orden=so)
    return d


def califs(musica_base=None):
    d = {1: materia('Lengua Española', 70, 'LE'), 2: materia('Inglés', 74, 'LEI'),
         3: materia('Matemática', 66, 'MAT'), 4: materia('Ciencias Sociales', 78, 'CS'),
         5: materia('Ciencias de la Naturaleza', 72, 'CN'), 6: materia('Educación Artística', 80, 'EA'),
         7: materia('Educación Física', 84, 'EF'), 8: materia('Formación Integral Humana y Religiosa', 76, 'FIHR'),
         101: materia('Componente Uno', 60, so=0), 102: materia('Componente Dos', 64, so=1)}
    if musica_base is not None:
        d[201] = materia('Música', musica_base)
    return d


ASIST = {'p%d' % i: {'asistencia': 40 + i, 'ausencia': i, 'pct_asistencia_anual': 95.0,
                     'pct_ausencia_anual': 5.0} for i in (1, 2, 3, 4)}
SIT = {'promovido': True, 'repitente': False, 'condicion': 'PROMOVIDO'}
OKS, MAL = 0, []


def ck(nombre, cond, det=''):
    global OKS
    if cond:
        OKS += 1
    else:
        MAL.append(nombre)
    print('  %s %s %s' % ('PASA ' if cond else 'FALLA', nombre, '' if cond else str(det)[:300]))


for g, gn in ((4, '4to'), (5, '5to'), (6, '6to')):
    curso = Obj(grado=Obj(nombre='%s Secundaria' % gn), seccion='A', nombre='A', tanda=None, tutor=None,
                nivel='secundaria')
    est = Obj(nombre='Est', apellido='Sint', sigerd='', numero_orden=1)
    gen = lambda c_: B.generar_boletin_secundaria_minerd(est, curso, c_, asistencias_por_periodo=ASIST,
                                                         situacion_final=SIT).getvalue()
    sin = gen(califs())
    con = gen(califs(86))          # Música CF 91 -> A
    baja = gen(califs(56))         # Música CF 61 -> R
    open(os.path.join(OUT, 'boletin_%s_2optativas_musica.pdf' % gn), 'wb').write(con)
    ps, pc, pb = (pymupdf.open(stream=x, filetype='pdf')[1] for x in (sin, con, baja))
    W, H = ps.rect.width, ps.rect.height
    for nombre, clip in (('encima de la tabla (y<416.5)', (0, 0, W, 416.5)),
                         ('debajo de la fila (y>434.0: asistencia, leyenda, situación, firmas)', (0, 434.0, W, H))):
        a = ps.get_pixmap(dpi=150, clip=pymupdf.Rect(*clip)).samples
        b = pc.get_pixmap(dpi=150, clip=pymupdf.Rect(*clip)).samples
        ck('%s: %s idéntico al boletín sin Música' % (gn, nombre), a == b)
    banda = [w for w in pc.get_text('words') if (w[1] + w[3]) / 2 > 416.5 and (w[1] + w[3]) / 2 < 434]
    ck('%s: todo lo de la fila queda dentro de 416.9-432.4' % gn,
       banda and all(w[1] >= 416.9 and w[3] <= 432.4 for w in banda), [(w[4], w[1], w[3]) for w in banda][:6])
    textos = [w[4] for w in sorted(banda, key=lambda w: w[0])]
    esperado = ['Música'] + [str(86 + c + p) for c in (1, 2, 3, 4) for p in (1, 2, 3, 4)] + \
        [B._fmt_nota(sum(86 + c + p for p in (1, 2, 3, 4)) / 4) for c in (1, 2, 3, 4)] + ['91', '91']
    ck('%s: Música con 16 notas, PC1-PC4, CF 91 y A' % gn, textos == esperado, textos)
    x_a = [w for w in banda if w[4] == '91' and abs((w[0] + w[2]) / 2 - B.RIGHT_X['A']) < 6]
    ck('%s: la condición va en la columna A' % gn, len(x_a) == 1, [(w[4], round(w[0])) for w in banda][-3:])
    bandab = [w for w in pb.get_text('words') if 416.5 < (w[1] + w[3]) / 2 < 434]
    x_r = [w for w in bandab if w[4] == '61' and abs((w[0] + w[2]) / 2 - B.RIGHT_X['R']) < 6]
    ck('%s: con CF 61 la condición va en la columna R' % gn, len(x_r) == 1, [(w[4], round(w[0])) for w in bandab][-3:])
    geo = B.FILA_COMPACTA_GEOMETRIA['Boletin-%s-grado-NS.pdf' % gn]
    xs = sorted({round(it[1].x, 1) for d in pc.get_drawings() for it in d['items']
                 if it[0] == 'l' and abs(it[1].x - it[2].x) < 0.3 and min(it[1].y, it[2].y) > 416 and max(it[1].y, it[2].y) < 433})
    ck('%s: las verticales de la fila son las de su plantilla' % gn,
       all(any(abs(x - v) < 0.3 for x in xs) for v in geo['verticales'] if v != 63.0), xs[:8])
    # Color de los fondos de la fila = el de la plantilla (muestra en la celda C.F.)
    xcf = geo['fondos'][1]
    pix = pc.get_pixmap(dpi=72, clip=pymupdf.Rect(xcf[0] + 2, 420, xcf[0] + 4, 422))
    rgb = tuple(round(v / 255, 2) for v in pix.pixel(0, 0))
    ck('%s: el fondo de la fila tiene el color de su plantilla %s' % (gn, rgb),
       all(abs(a - b) < 0.02 for a, b in zip(rgb, geo['color'])), (rgb, geo['color']))
    pc.get_pixmap(dpi=72, clip=pymupdf.Rect(30, 300, W - 10, 470)).save(os.path.join(OUT, '%s_100pct.png' % gn))
    pc.get_pixmap(dpi=300, clip=pymupdf.Rect(30, 395, 520, 445)).save(os.path.join(OUT, '%s_300dpi_detalle.png' % gn))
# Centrado de Música en las casillas REALES de cada plantilla, con valores que
# detectan cruces y columnas intercambiadas: 0, 9, 70, 99, 100 y decimales.
PER = [0, 9, 70, 99, 100, 85.5, 72.3, 64.8, 55, 81, 92.5, 66, 77, 88, 33.3, 44]
PCS = [98.5, 90.3, 61.5, 50.8]
COLS = (['P%d-C%d' % (p_, c_) for c_ in (1, 2, 3, 4) for p_ in (1, 2, 3, 4)] + ['PC1', 'PC2', 'PC3', 'PC4', 'CF']
        + ['50%CF', 'CEC', '50%CEC', 'CCF', '30%CF', 'CEEX', '70%CEEX', 'CEXF', 'ESP-CF', 'ESP-CE', 'A', 'R'])
for gn in ('4to', '5to', '6to'):
    curso = Obj(grado=Obj(nombre='%s Secundaria' % gn), seccion='A', nombre='A', tanda=None, tutor=None,
                nivel='secundaria')
    for nf in (100, 9):
        mus = materia('Música', 0)
        mus['competencias'] = [Comp(c_, PER[(c_ - 1) * 4:(c_ - 1) * 4 + 4]) for c_ in (1, 2, 3, 4)]
        mus['pc_por_periodo'] = {'pc%d' % (i + 1): v_ for i, v_ in enumerate(PCS)}
        mus['cf'] = mus['cf_exacto'] = 97
        mus['evaluacion_extra'] = Obj(cec=65, completiva_final=71, ceex=74, extraordinaria_final=76, ce=79,
                                      especial_final=None, nota_final=nf)
        d_ = califs()
        d_[201] = mus
        pdf = B.generar_boletin_secundaria_minerd(Obj(nombre='E', apellido='S', sigerd='', numero_orden=1),
                                                  curso, d_).getvalue()
        if nf == 100:
            open(os.path.join(OUT, 'musica_centrada_%s.pdf' % gn), 'wb').write(pdf)
        pag = pymupdf.open(stream=pdf, filetype='pdf')[1]
        v = B.FILA_COMPACTA_GEOMETRIA['Boletin-%s-grado-NS.pdf' % gn]['verticales']
        cas = [(v[i], v[i + 1]) for i in range(2, len(v) - 1)]
        esp = [(COLS[(c_ - 1) * 4 + p_ - 1], B._fmt_nota(PER[(c_ - 1) * 4 + p_ - 1]))
               for c_ in (1, 2, 3, 4) for p_ in (1, 2, 3, 4)]
        esp += [('PC%d' % (i + 1), B._fmt_nota(v_)) for i, v_ in enumerate(PCS)]
        esp += [('CF', '97'), ('50%CF', '48.5'), ('CEC', '65'), ('50%CEC', '32.5'), ('CCF', '71'), ('30%CF', '29.1'),
                ('CEEX', '74'), ('70%CEEX', '51.8'), ('CEXF', '76'), ('ESP-CF', '97'), ('ESP-CE', '79'),
                (('A', str(nf)) if nf >= 70 else ('R', str(nf)))]
        fila_w = [w for w in pag.get_text('words') if 416.9 <= (w[1] + w[3]) / 2 <= 432.4 and w[0] > 163]
        malos = []
        for col, txt in esp:
            x0c, x1c = cas[COLS.index(col)]
            cand = [w for w in fila_w if w[4] == txt and x0c <= (w[0] + w[2]) / 2 < x1c]
            if len(cand) != 1:
                malos.append('%s=%s no está en su casilla' % (col, txt))
                continue
            w = cand[0]
            if abs((w[0] + w[2]) / 2 - (x0c + x1c) / 2) > 0.3 or min(w[0] - x0c, x1c - w[2]) < 1.0:
                malos.append('%s=%s desvío %.2f margen %.2f' % (col, txt, (w[0] + w[2]) / 2 - (x0c + x1c) / 2,
                                                                min(w[0] - x0c, x1c - w[2])))
        ck('%s (condición %d): los %d valores de Música centrados en su casilla, sin cruces' % (gn, nf, len(esp)),
           not malos and len(fila_w) == len(esp), (malos, len(fila_w)))
        nom = [w for w in pag.get_text('words') if 416.9 <= (w[1] + w[3]) / 2 <= 432.4 and w[0] < 163]
        ck('%s (condición %d): el nombre Música sigue alineado a la izquierda' % (gn, nf),
           len(nom) == 1 and nom[0][4] == 'Música' and abs(nom[0][0] - B.SO_NOMBRE_X) < 0.5, nom)
print('\n%d PASARON / %d FALLARON' % (OKS, len(MAL)))
