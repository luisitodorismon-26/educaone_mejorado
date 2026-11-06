# -*- coding: utf-8 -*-
"""
Notas por Período (nota del período = último P registrado) y Boletín para
Padres con P y RP separados. Base SQLite AISLADA, datos sintéticos.

  A. La nota del período es la de la competencia más alta con valor (de la 4 a
     la 1), no el promedio: 70,75,80,85 -> 85. Incompletas, 0 y sin notas.
  B. Pantalla (vista resumen y vista por competencia), tabla general en PDF y
     Reporte del Período para padres dicen LO MISMO por estudiante y asignatura,
     escrito igual (sin truncar decimales). «Prom.» igual en pantalla y PDF.
  C. Boletín para Padres individual y por lote: fila P y fila RP por asignatura,
     competencia y período; «—» sin recuperación; leyenda; todas las
     asignaturas (Música y optativa incluidas) y todos los estudiantes.
  D. Regla de cada nivel: en Secundaria el PC usa el mayor entre P y RP (antes
     el reporte aplicaba la de Primaria y, con RP < P, salía más bajo).
  E. Permisos y aislamiento entre colegios. F. Cero pérdida: las notas
     guardadas no cambian.

Uso (desde backend/):  python tools/test_notas_periodo_boletin_padres.py [carpeta_pdfs]
"""
import datetime as dt
import hashlib
import json
import os
import sys
import tempfile

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(BK, 'tools'))
OUT = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix='notas_periodo_')
os.makedirs(OUT, exist_ok=True)
from test_utils import aislar_base_de_datos, verificar_engine_aislado  # noqa: E402

TMP = aislar_base_de_datos('notas_periodo_boletin')
from database import engine, SessionLocal  # noqa: E402
verificar_engine_aislado(engine, TMP)
import models as M  # noqa: E402
import app as APP  # noqa: E402
import pymupdf  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from auth import create_token  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402

M.Base.metadata.create_all(bind=engine)
db = SessionLocal()
OK, MAL = [], []


def check(nombre, cond, detalle=''):
    (OK if cond else MAL).append(nombre)
    print('  %s %s %s' % ('PASA ' if cond else 'FALLA', nombre, '' if cond else str(detalle)[:500]))


def add(o):
    db.add(o)
    db.flush()
    return o


def colegio(cod):
    col = add(M.Colegio(nombre='Colegio Sintético %s' % cod, codigo=cod, activo=True))
    add(M.ConfiguracionColegio(colegio_id=col.id, nombre=col.nombre, regional='10', distrito='10-01', codigo_centro='1'))
    ano = add(M.AnoEscolar(colegio_id=col.id, nombre='2026-2027', activo=True, cerrado=False, periodo_activo=1,
                           fecha_inicio=dt.date(2026, 9, 1), fecha_fin=dt.date(2027, 6, 30)))
    g = add(M.Grado(colegio_id=col.id, nombre='5to Secundaria', nivel='secundaria', orden=5, activo=True))
    t = add(M.Tanda(colegio_id=col.id, nombre='Matutina', hora_inicio='07:30', hora_fin='12:30', activo=True))
    cur = add(M.Curso(colegio_id=col.id, nombre='A', grado_id=g.id, tanda_id=t.id, ano_escolar_id=ano.id, activo=True))
    return col, ano, cur


def usuario(col, u, rol):
    return add(M.Usuario(colegio_id=col.id, username=u, password_hash='x', nombre=u, apellido='Sint', role=rol,
                         activo=True, must_change_password=False, token_version=0))


colA, anoA, curA = colegio('NPA')
colB, anoB, curB = colegio('NPB')
dirA, coordA = usuario(colA, 'np_dir', 'direccion'), usuario(colA, 'np_coord', 'coordinador')
profLE, profOtro = usuario(colA, 'np_prof_le', 'profesor'), usuario(colA, 'np_prof_otro', 'profesor')
dirB = usuario(colB, 'np_dir_b', 'direccion')
ASIG = {}
for nombre, area in (('Lengua Española', 'LE'), ('Matemática', 'MAT'), ('Música', None),
                     ('Optativa HLM: Literatura y Sociedad', None),
                     ('Formación Integral Humana y Religiosa', 'FIHR')):
    a = add(M.Asignatura(colegio_id=colA.id, nombre=nombre, codigo=nombre[:3].upper(), area_curricular_codigo=area))
    ASIG[nombre] = a
    add(M.AsignacionProfesor(colegio_id=colA.id, profesor_id=(profLE if area == 'LE' else dirA).id, curso_id=curA.id,
                             asignatura_id=a.id, ano_escolar_id=anoA.id, activo=True))
otro_curso = add(M.Curso(colegio_id=colA.id, nombre='B', grado_id=curA.grado_id, ano_escolar_id=anoA.id, activo=True))
add(M.AsignacionProfesor(colegio_id=colA.id, profesor_id=profOtro.id, curso_id=otro_curso.id, asignatura_id=ASIG['Matemática'].id,
                         ano_escolar_id=anoA.id, activo=True))
LE, MAT, MUS = ASIG['Lengua Española'], ASIG['Matemática'], ASIG['Música']
OPT, FIHR = ASIG['Optativa HLM: Literatura y Sociedad'], ASIG['Formación Integral Humana y Religiosa']


def est(nombre, apellido, n, col=colA, cur=curA):
    return add(M.Estudiante(colegio_id=col.id, nombre=nombre, apellido=apellido, curso_id=cur.id, no_lista=n, activo=True,
                            matricula='%s-%d' % (col.codigo, n), sexo='F', fecha_ingreso=dt.date(2026, 8, 20)))


E1, E2, E3, E4 = est('Ana', 'Cuatro', 1), est('Beto', 'Recupera', 2), est('Caro', 'Sinnotas', 3), est('Dani', 'Decimal', 4)
EB = est('Ana', 'Cuatro', 1, col=colB, cur=curB)          # mismo nombre en otro colegio


def nota(e, asig, comp, **campos):
    return add(M.CalificacionSecundaria(colegio_id=colA.id, estudiante_id=e.id, asignatura_id=asig.id,
                                        ano_escolar_id=anoA.id, competencia_numero=comp, **campos))


# E1 — P1: cuatro notas distintas, incompleta, cero, una sola competencia, sin notas.
for comp, v in zip((1, 2, 3, 4), (70, 75, 80, 85)):
    nota(E1, LE, comp, p1=v)                        # -> 85 (promedio sería 77.5)
nota(E1, MAT, 1, p1=90)
nota(E1, MAT, 2, p1=88)                             # incompleta -> 88
for comp, v in zip((1, 2, 3, 4), (80, 80, 80, 0)):
    nota(E1, MUS, comp, p1=v)                       # el 0 es nota -> 0
nota(E1, OPT, 1, p1=75)                             # optativa, una competencia -> 75
nota(E1, MAT, 4, p2=66)                             # dato en P2: NO cuenta para el período 1
# E2 — recuperaciones: RP mayor, menor e igual que P (Secundaria: vale el mayor).
nota(E2, LE, 1, p1=60, rp1=75, p2=70, p3=70, p4=70)          # RP mayor
nota(E2, LE, 2, p1=80, rp1=70, p2=80, p3=80, p4=80)          # RP menor -> PC 80 (Primaria daría 77.5)
nota(E2, LE, 3, p1=70, rp1=70)                                # igual
nota(E2, MUS, 1, p1=91)
nota(E2, OPT, 1, p1=81)
nota(E2, OPT, 2, p1=81.5)
# E3 — sin notas. E4 — decimales y promedio con .x5.
nota(E4, MAT, 1, p1=84.6)
nota(E4, LE, 1, p1=81)
nota(E4, MUS, 1, p1=81.5)
db.commit()

ESPERADO = {   # (estudiante, asignatura) -> nota del período 1
    (E1.id, LE.id): 85, (E1.id, MAT.id): 88, (E1.id, MUS.id): 0, (E1.id, OPT.id): 75, (E1.id, FIHR.id): None,
    (E2.id, LE.id): 70, (E2.id, MAT.id): None, (E2.id, MUS.id): 91, (E2.id, OPT.id): 81.5, (E2.id, FIHR.id): None,
    (E3.id, LE.id): None, (E3.id, MAT.id): None, (E3.id, MUS.id): None, (E3.id, OPT.id): None, (E3.id, FIHR.id): None,
    (E4.id, LE.id): 81, (E4.id, MAT.id): 84.6, (E4.id, MUS.id): 81.5, (E4.id, OPT.id): None, (E4.id, FIHR.id): None,
}
from nota_periodo import formatear_nota, promedio_de_notas  # noqa: E402
ESCRITO = {k: (formatear_nota(v) if v is not None else None) for k, v in ESPERADO.items()}
ESTS = (E1, E2, E3, E4)
NOMBRE = {a.id: a.nombre for a in ASIG.values()}


def huella_notas():
    db.expire_all()
    filas = sorted((c.id, c.estudiante_id, c.asignatura_id, c.competencia_numero, c.p1, c.rp1, c.p2, c.rp2, c.p3, c.rp3,
                    c.p4, c.rp4, c.promedio_competencia) for c in db.query(M.CalificacionSecundaria))
    return len(filas), hashlib.sha256(json.dumps(filas).encode()).hexdigest()


HUELLA0 = huella_notas()
c = TestClient(APP.app)
H = lambda u: {'Authorization': 'Bearer ' + create_token(u)}  # noqa: E731


def pdf(url, user=dirA):
    r = c.get(url, headers=H(user))
    return r.status_code, (pymupdf.open(stream=r.content, filetype='pdf') if r.status_code == 200 else None), r


# ════════════════ A + B. NOTA DEL PERÍODO: PANTALLA = PDF = REPORTE ════════════════
print('\n=== A/B. Nota del período: pantalla, tabla general en PDF y Reporte del Período ===')
r = c.get('/api/calificaciones/por-periodo?curso_id=%d&periodo=1' % curA.id, headers=H(dirA))
pant = {}
for e in r.json()['estudiantes']:
    for asig_nom, v in e['asignaturas'].items():
        aid = next(a.id for a in ASIG.values() if a.nombre == asig_nom)
        pant[(e['estudiante_id'], aid)] = v
mal = {k: (pant.get(k), v) for k, v in ESPERADO.items() if pant.get(k) != v}
check('A1 pantalla: nota del período = último P (85 y no 77.5), incompleta, 0, sin notas, decimales', not mal, mal)
check('A2 un dato de P2 no altera el período 1 (Matemática de Ana sigue en 88)', pant[(E1.id, MAT.id)] == 88, pant[(E1.id, MAT.id)])
prom_pant = {e['estudiante_id']: e['promedio'] for e in r.json()['estudiantes']}
check('A3 «Prom.» de la pantalla: promedio de las notas del período con redondeo half-up (81, 84.6, 81.5 -> 82.4; '
      'Ana 85, 88, 0, 75 -> 62)', prom_pant[E4.id] == promedio_de_notas([81, 84.6, 81.5]) and prom_pant[E1.id] == 62.0
      and prom_pant[E3.id] is None, prom_pant)

r = c.get('/api/calificaciones-secundaria/curso/%d/periodo/1/competencias' % curA.id, headers=H(dirA))
comp_view = {(e['estudiante_id'], a['asignatura_id']): a['ultimo_p'] for e in r.json()['estudiantes'] for a in e['asignaturas']}
check('A4 vista por competencia: «Nota P1 (último P)» igual que la vista resumen',
      all(comp_view.get(k) == v for k, v in ESPERADO.items()), {k: comp_view.get(k) for k in ESPERADO})

st, doc, _ = pdf('/api/calificaciones/por-periodo/pdf?curso_id=%d&periodo=1' % curA.id)
open(os.path.join(OUT, 'tabla_general_P1.pdf'), 'wb').write(_.content)
tabla = doc[0].find_tables().tables[0].extract()
cab = tabla[0]
# El PDF ordena las asignaturas por nombre: columnas 2..n en ese orden.
col_de = {a.id: 2 + i for i, a in enumerate(sorted(ASIG.values(), key=lambda a: a.nombre))}
check('B0 el encabezado de cada columna es el nombre completo de la asignatura',
      all(''.join((cab[col_de[a.id]] or '').split()) == ''.join(a.nombre.split()) for a in ASIG.values()), cab)
pdf_vals, pdf_prom = {}, {}
for fila in tabla[1:]:
    e = next(x for x in ESTS if x.nombre_completo[:25] == (fila[1] or '').replace('\n', ' '))
    for aid, i in col_de.items():
        pdf_vals[(e.id, aid)] = None if fila[i] in ('-', None) else fila[i]
    pdf_prom[e.id] = None if fila[-1] == '-' else fila[-1]
mal = {k: (pdf_vals.get(k), v) for k, v in ESCRITO.items() if pdf_vals.get(k) != v}
check('B1 tabla general PDF = pantalla por estudiante y asignatura, escrita igual (84.6 y 81.5, sin truncar; 0 visible)',
      not mal, mal)
mal = {e.id: (pdf_prom[e.id], prom_pant[e.id]) for e in ESTS
       if pdf_prom[e.id] != (None if prom_pant[e.id] is None else '%.1f' % prom_pant[e.id])}
check('B2 «Prom.» del PDF = «Prom.» de la pantalla (mismo redondeo)', not mal, mal)
check('B3 el PDF explica que cada celda es la nota del período (último P), no el promedio',
      'último P registrado' in doc[0].get_text() and 'no el promedio' in doc[0].get_text(), '')

rep_vals = {}
for e in ESTS:
    st, d, rr = pdf('/api/calificaciones-secundaria/reporte-padres/curso/%d/pdf?periodo=1&estudiante_id=%d' % (curA.id, e.id))
    if e is E2:
        open(os.path.join(OUT, 'reporte_periodo_P1_Beto.pdf'), 'wb').write(rr.content)
    lineas = {}
    for b in d[0].get_text('dict')['blocks']:
        for ln in b.get('lines', []):
            for s in ln['spans']:
                lineas.setdefault(round(s['bbox'][1]), []).append((s['bbox'][0], s['text'].strip()))
    for aid, nom in NOMBRE.items():
        fila = next((v for v in lineas.values() if any(t == nom[:45] for _, t in v)), None)
        valor = next((t for x, t in fila if 12 * cm <= x < 15 * cm), None) if fila else 'FILA NO ENCONTRADA'
        rep_vals[(e.id, aid)] = None if valor == 'Sin nota' else valor
mal = {k: (rep_vals.get(k), v) for k, v in ESCRITO.items() if rep_vals.get(k) != v}
check('B4 Reporte del Período para padres = pantalla, escrito igual («85», no «85.0»; 0 visible; «Sin nota» si no hay)',
      not mal, mal)

# ════════════════ C + D. BOLETÍN PARA PADRES ════════════════
print('\n=== C/D. Boletín para Padres: P y RP separados ===')
from reportlab.lib.pagesizes import letter, landscape  # noqa: E402
MARGEN, COL_ASIG, COL_PC = 1.2 * cm, 3.4 * cm, 2.4 * cm
COL_PAR = (landscape(letter)[0] - 2 * MARGEN - COL_ASIG - COL_PC) / 32    # 4 comp x 4 per x (P, RP)


def celdas_boletin(page, asig_nombre):
    """{(comp, periodo): (P, RP)} leyendo el PDF por posición: la RP va en la columna contigua a su P."""
    ws = page.get_text('words')
    w = next((w for w in ws if w[4] == asig_nombre.split()[0] and w[0] < MARGEN + COL_ASIG), None)
    if w is None:
        return None
    yc = (w[1] + w[3]) / 2

    def en(xc):
        t = sorted((abs((x[1] + x[3]) / 2 - yc), x[4]) for x in ws
                   if abs((x[0] + x[2]) / 2 - xc) < COL_PAR / 2 and abs((x[1] + x[3]) / 2 - yc) < 9)
        return t[0][1] if t else None
    out = {}
    for comp in range(1, 5):
        for per in range(1, 5):
            x0 = MARGEN + COL_ASIG + (comp - 1) * 8 * COL_PAR + (per - 1) * 2 * COL_PAR
            out[(comp, per)] = (en(x0 + COL_PAR / 2), en(x0 + 1.5 * COL_PAR))
    xpc = MARGEN + COL_ASIG + 32 * COL_PAR
    out['PC'] = ' '.join(x[4] for x in sorted(ws, key=lambda x: x[0])
                         if x[0] >= xpc and abs((x[1] + x[3]) / 2 - yc) < 9)
    return out


st, doc, rr = pdf('/api/boletines/estudiante/%d/pdf' % E2.id)
open(os.path.join(OUT, 'boletin_padres_Beto.pdf'), 'wb').write(rr.content)
cel = celdas_boletin(doc[0], 'Lengua Española')
check('C1 RP MAYOR que P: competencia 1, período 1 -> P «60» y, a su lado, RP «75»', cel[(1, 1)] == ('60', '75'), cel)
cab_txt = [x[4] for x in sorted(doc[0].get_text('words'), key=lambda x: x[0]) if x[4] in ('P1', 'RP1', 'P2', 'RP2', 'P3', 'RP3', 'P4', 'RP4')]
check('C0 encabezado como en el Registro: P1 RP1 P2 RP2 P3 RP3 P4 RP4 en cada competencia',
      cab_txt == ['P1', 'RP1', 'P2', 'RP2', 'P3', 'RP3', 'P4', 'RP4'] * 4, cab_txt[:10])
check('C2 RP MENOR que P: competencia 2, período 1 -> P «80» y RP «70» (no se sustituye una por otra)',
      cel[(2, 1)] == ('80', '70'), cel[(2, 1)])
check('C3 RP IGUAL a P: competencia 3, período 1 -> «70» y «70»', cel[(3, 1)] == ('70', '70'), cel[(3, 1)])
check('C4 sin recuperación -> «—» en la columna RP (competencia 1, períodos 2-4)',
      [cel[(1, p)] for p in (2, 3, 4)] == [('70', '—')] * 3, [cel[(1, p)] for p in (2, 3, 4)])
check('C5 sin nota ni recuperación -> «—» y «—» (competencia 4)', all(cel[(4, p)] == ('—', '—') for p in range(1, 5)),
      [cel[(4, p)] for p in range(1, 5)])
# D: PC de la competencia 2 = (max(80,70) + 80*3)/4 = 80 en Secundaria; con la regla de Primaria (RP reemplaza) 77.5 -> «78».
pcs = [x.strip() for x in cel['PC'].replace(' ', '').split('·')]
check('D1 regla de Secundaria: PC de la competencia 2 = 80 (mayor entre P y RP); con la de Primaria habría sido 78',
      len(pcs) == 4 and pcs[1] == '80', cel['PC'])
check('D2 los 4 PC de Lengua: 71 (60->RP 75), 80, — (incompleta), —', pcs == ['71', '80', '—', '—'], cel['PC'])
txt = doc[0].get_text()
check('C6 leyenda: P = nota del período, RP = recuperación, — = sin recuperación',
      'P = nota del período' in txt and 'recuperación pedagógica' in txt and 'sin recuperación' in txt, '')
plano = ''.join(''.join(p.get_text().split()) for p in doc)
check('C7 todas las asignaturas, incluidas Música, la optativa y el nombre largo (sin recortarlo)',
      all(''.join(a.nombre.split()) in plano for a in ASIG.values()), [a.nombre for a in ASIG.values() if ''.join(a.nombre.split()) not in plano])
st, doc1, rr = pdf('/api/boletines/estudiante/%d/pdf' % E1.id)
open(os.path.join(OUT, 'boletin_padres_Ana.pdf'), 'wb').write(rr.content)
cm_ = celdas_boletin(doc1[0], 'Música')
check('C8 Música de Ana: el 0 se muestra como «0» (competencia 4, P1), RP «—»', cm_[(4, 1)] == ('0', '—'), cm_[(4, 1)])
co = celdas_boletin(doc1[0], 'Optativa')
check('C9 optativa de Ana: «75» en la competencia 1, P1', co[(1, 1)] == ('75', '—'), co[(1, 1)])
cb = celdas_boletin(doc[0], 'Optativa')
check('C9b una P con decimal se ve tal como se registró: «81.5», no «82» (optativa de Beto, competencia 2)',
      cb[(2, 1)] == ('81.5', '—'), cb[(2, 1)])

st, lote, rr = pdf('/api/boletines/curso/%d/pdf' % curA.id)
open(os.path.join(OUT, 'boletines_padres_lote.pdf'), 'wb').write(rr.content)
textos = [p.get_text() for p in lote]
check('C10 lote: un boletín por estudiante, sin omitir a ninguno (también al que no tiene notas)',
      st == 200 and all(sum(e.nombre.upper() in t and e.apellido.upper() in t for t in textos) == 1 for e in ESTS),
      [(e.nombre, sum(e.nombre.upper() in t for t in textos)) for e in ESTS])
cl = celdas_boletin(next(p for p in lote if 'BETO' in p.get_text()), 'Lengua Española')
check('C11 la página del lote dice lo mismo que el boletín individual', cl == cel, (cl, cel))
check('C12 cada página del lote tiene todas las asignaturas',
      all(all(''.join(a.nombre.split()) in ''.join(t.split()) for a in ASIG.values()) for t in textos), '')

# ════════════════ E. PERMISOS Y AISLAMIENTO ════════════════
print('\n=== E. Permisos y aislamiento ===')
check('E1 profesor sin asignación en el curso: 403 en la vista del período',
      c.get('/api/calificaciones/por-periodo?curso_id=%d&periodo=1' % curA.id, headers=H(profOtro)).status_code == 403, '')
check('E2 profesor: 403 en la tabla general PDF (Dirección y Coordinación)',
      c.get('/api/calificaciones/por-periodo/pdf?curso_id=%d&periodo=1' % curA.id, headers=H(profLE)).status_code == 403, '')
check('E3 Coordinación sí la descarga', c.get('/api/calificaciones/por-periodo/pdf?curso_id=%d&periodo=1' % curA.id,
                                             headers=H(coordA)).status_code == 200, '')
otros = {u: c.get(u, headers=H(dirB)).status_code for u in (
    '/api/calificaciones/por-periodo?curso_id=%d&periodo=1' % curA.id,
    '/api/calificaciones/por-periodo/pdf?curso_id=%d&periodo=1' % curA.id,
    '/api/calificaciones-secundaria/reporte-padres/curso/%d/pdf?periodo=1' % curA.id,
    '/api/boletines/estudiante/%d/pdf' % E1.id, '/api/boletines/curso/%d/pdf' % curA.id)}
check('E4 Dirección de otro colegio (con una «Ana Cuatro» propia): 404 en todo', set(otros.values()) == {404}, otros)
st, dB, rB = pdf('/api/boletines/estudiante/%d/pdf' % EB.id, user=dirB)
check('E5 su «Ana Cuatro» no trae nada del colegio A (su curso no tiene asignaturas: 400 «sin asignaturas»)',
      (st == 400 and 'no tiene asignaturas' in rB.text) or (st == 200 and '85' not in dB[0].get_text()), (st, rB.text[:150]))

# ════════════════ F. CERO PÉRDIDA ════════════════
print('\n=== F. Cero pérdida ===')
check('F1 las notas guardadas no cambiaron (mismas filas y valores)', huella_notas() == HUELLA0, (huella_notas(), HUELLA0))

db.close()
engine.dispose()
print('\nPDFs en:', OUT)
print('RESULTADO NOTAS POR PERÍODO + BOLETÍN PADRES: %d PASARON / %d FALLARON' % (len(OK), len(MAL)))
sys.exit(1 if MAL else 0)
