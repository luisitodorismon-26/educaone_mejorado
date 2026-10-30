"""Alineación del boletín de Secundaria: valores centrados en las casillas REALES.

4to-6to: en TODAS las filas (9 troncales, SO1, SO2 y la fila compacta) cada
valor —16 períodos, PC1-PC4, CF, completiva, extraordinaria, especial y A/R—
debe quedar en su columna, centrado en su casilla de la plantilla del grado y
lejos de los bordes. Cada fila lleva su propio CF y su propia nota final, así
que un dato en la fila de otra materia se detecta.

1ro-3ro: NO cambia. Sus valores siguen en las coordenadas de siempre
(COMP_X / PC_X / RIGHT_X).

Generador real, sin base. Uso (desde backend/):
    python tools/test_boletin_alineacion_4to6to.py [carpeta_pdfs]
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix='alineacion_')
os.makedirs(OUT, exist_ok=True)
import pymupdf
import boletin_minerd_secundaria as B

OKS, MAL = 0, []


def ck(nombre, cond, det=''):
    global OKS
    if cond:
        OKS += 1
    else:
        MAL.append(nombre)
    print('  %s %s %s' % ('PASA ' if cond else 'FALLA', nombre, '' if cond else str(det)[:400]))


class Comp:
    def __init__(self, n, vals):
        self.competencia_numero, self.vals = n, vals

    def valor_periodo(self, p):
        return self.vals[p - 1]


class Obj:
    def __init__(self, **k):
        self.__dict__.update(k)


PERIODOS = [0, 9, 70, 99, 100, 85.5, 72.3, 64.8, 55, 81, 92.5, 66, 77, 88, 33.3, 44]
PCS = [98.5, 90.3, 61.5, 50.8]
COLUMNAS = (['P%d-C%d' % (p, c) for c in (1, 2, 3, 4) for p in (1, 2, 3, 4)] + ['PC1', 'PC2', 'PC3', 'PC4', 'CF']
            + ['50%CF', 'CEC', '50%CEC', 'CCF', '30%CF', 'CEEX', '70%CEEX', 'CEXF', 'ESP-CF', 'ESP-CE', 'A', 'R'])
TRONCALES = [('Lengua Española', 'LE'), ('Inglés', 'LEI'), ('Francés', 'LEF'), ('Matemática', 'MAT'),
             ('Ciencias Sociales', 'CS'), ('Ciencias de la Naturaleza', 'CN'), ('Educación Artística', 'EA'),
             ('Educación Física', 'EF'), ('Formación Integral Humana y Religiosa', 'FIHR')]


def fila(nombre, cf, nota_final, area=None, so=None):
    comps = [Comp(c, PERIODOS[(c - 1) * 4:(c - 1) * 4 + 4]) for c in (1, 2, 3, 4)]
    ev = Obj(cec=65, completiva_final=71, ceex=74, extraordinaria_final=76, ce=79, especial_final=None,
             nota_final=nota_final)
    d = {'asignatura_nombre': nombre, 'competencias': comps,
         'pc_por_periodo': {'pc%d' % (i + 1): v for i, v in enumerate(PCS)}, 'cf': cf, 'cf_exacto': cf,
         'literal': '', 'evaluacion_extra': ev, 'area_curricular_codigo': area}
    if so is not None:
        d.update(es_salida_optativa=True, so_orden=so)
    return d


def esperado(cf, nota_final):
    cols = [('P%d-C%d' % (p, c), B._fmt_nota(PERIODOS[(c - 1) * 4 + p - 1])) for c in (1, 2, 3, 4) for p in (1, 2, 3, 4)]
    cols += [('PC%d' % (i + 1), B._fmt_nota(v)) for i, v in enumerate(PCS)]
    cols += [('CF', str(cf)), ('50%CF', B._fmt_nota(round(cf * 0.5, 1))), ('CEC', '65'),
             ('50%CEC', '32.5'), ('CCF', '71'), ('30%CF', B._fmt_nota(round(cf * 0.3, 1))), ('CEEX', '74'),
             ('70%CEEX', '51.8'), ('CEXF', '76'), ('ESP-CF', str(cf)), ('ESP-CE', '79')]
    cols += [('A', str(nota_final))] if nota_final >= 70 else [('R', str(nota_final))]
    return cols


def generar(curso, califs):
    return B.generar_boletin_secundaria_minerd(Obj(nombre='E', apellido='S', sigerd='', numero_orden=1),
                                               curso, califs).getvalue()


# ---------------------------------------------------------------- 4to-6to
for gn in ('4to', '5to', '6to'):
    print('\n=== %s ===' % gn)
    curso = Obj(grado=Obj(nombre='%s Secundaria' % gn), seccion='A', nombre='A', tanda=None, tutor=None,
                nivel='secundaria')
    # CF y nota final DISTINTOS por fila: 60+i y 80+i (o 50+i para una fila en R).
    filas = []
    califs = {}
    for i, (n, a) in enumerate(TRONCALES):
        cf, nf = 60 + i, (50 + i if a == 'MAT' else 80 + i)
        califs[i + 1] = fila(n, cf, nf, area=a)
        filas.append((n, B.ROW_Y_SEGUNDO[B.AREA_CURRICULAR_A_FILA[a]], cf, nf))
    for k, (lab, so) in enumerate((('SALIDA OPTATIVA 1', 0), ('SALIDA OPTATIVA 2', 1))):
        cf, nf = 90 + k, 92 + k
        califs[101 + k] = fila('Componente %d' % (k + 1), cf, nf, so=so)
        filas.append((lab, B.ROW_Y_SEGUNDO[lab], cf, nf))
    califs[201] = fila('Música', 97, 69)
    filas.append(('FILA COMPACTA (Música)', B.ROW_Y_FILA_COMPACTA, 97, 69))
    pdf = generar(curso, califs)
    open(os.path.join(OUT, 'alineacion_%s.pdf' % gn), 'wb').write(pdf)
    pag = pymupdf.open(stream=pdf, filetype='pdf')[1]
    v = B.FILA_COMPACTA_GEOMETRIA['Boletin-%s-grado-NS.pdf' % gn]['verticales']
    casillas = [(v[i], v[i + 1]) for i in range(2, len(v) - 1)]
    words = pag.get_text('words')
    for nombre, ry, cf, nf in filas:
        enfila = [w for w in words if abs((w[1] + w[3]) / 2 - ry) < 7 and w[0] > 163]
        esp = esperado(cf, nf)
        malos = []
        for col, txt in esp:
            x0c, x1c = casillas[COLUMNAS.index(col)]
            cand = [w for w in enfila if w[4] == txt and x0c <= (w[0] + w[2]) / 2 < x1c]
            if len(cand) != 1:
                malos.append('%s=%s no está (una vez) en su casilla' % (col, txt))
                continue
            w = cand[0]
            desv = (w[0] + w[2]) / 2 - (x0c + x1c) / 2
            marg = min(w[0] - x0c, x1c - w[2])
            if abs(desv) > 0.3 or marg < 1.0:
                malos.append('%s=%s desvío %.2f margen %.2f' % (col, txt, desv, marg))
        ck('%s %-38s %d valores en su columna, centrados, dentro de los bordes; CF %d y %s %d de ESTA fila'
           % (gn, nombre, len(esp), cf, 'A' if nf >= 70 else 'R', nf),
           not malos and len(enfila) == len(esp), (malos, len(enfila), len(esp)))

# ---------------------------------------------------------------- 1ro-3ro
for gn in ('1ro', '2do', '3ro'):
    curso = Obj(grado=Obj(nombre='%s Secundaria' % gn), seccion='A', nombre='A', tanda=None, tutor=None,
                nivel='secundaria')
    califs = {1: fila('Lengua Española', 61, 81, area='LE'), 2: fila('Matemática', 62, 52, area='MAT')}
    pag = pymupdf.open(stream=generar(curso, califs), filetype='pdf')[1]
    xs = ([B.COMP_X[c]['p%d' % p] for c in (1, 2, 3, 4) for p in (1, 2, 3, 4)]
          + [B.PC_X['pc%d' % i] for i in (1, 2, 3, 4)]
          + [B.RIGHT_X[k] for k in ('cf', 'p_cf_50', 'cec', 'p_cec_50', 'ccf', 'p_cf_30', 'ceex', 'p_ceex_70',
                                    'cexf', 'esp_cf', 'esp_ce')])
    for nombre, area, cf, nf in (('Lengua Española', 'LE', 61, 81), ('Matemática', 'MAT', 62, 52)):
        ry = B.ROW_Y_PRIMERO[B.AREA_CURRICULAR_A_FILA[area]]
        enfila = sorted((w for w in pag.get_text('words') if abs((w[1] + w[3]) / 2 - ry) < 7 and w[0] > 160),
                        key=lambda w: w[0])
        centros = [(w[0] + w[2]) / 2 for w in enfila]
        xs_fila = xs + [B.RIGHT_X['A'] if nf >= 70 else B.RIGHT_X['R']]
        ck('%s %s: los valores siguen en las coordenadas de siempre (sin cambios)' % (gn, nombre),
           len(centros) == len(xs_fila) and all(abs(a - b) < 0.3 for a, b in zip(centros, xs_fila)),
           [(round(a, 1), b) for a, b in zip(centros, xs_fila) if abs(a - b) >= 0.3][:5])

print('\n%d PASARON / %d FALLARON' % (OKS, len(MAL)))
sys.exit(1 if MAL else 0)
