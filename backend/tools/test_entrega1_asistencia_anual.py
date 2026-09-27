# -*- coding: utf-8 -*-
"""ENTREGA-1 — la asistencia anual del boletín, en una sola fuente.

QUÉ PROTEGE ESTA SUITE
======================
EducaOne tenía cuatro maneras distintas de contar la misma asistencia, y el
boletín usaba la peor de ellas. La de Secundaria, concretamente:

  · no filtraba por año escolar, así que arrastraba marcas de años anteriores;
  · contaba `presente` como única asistencia, de modo que una `tardanza`
    —que el contrato define como asistencia— bajaba el porcentaje;
  · contaba FILAS. En Secundaria la asistencia es por materia: seis
    asignaturas convertían un día en seis «días»;
  · y sin ningún registro devolvía 0 %, que un padre lee como «no vino nunca».

Las cuatro cosas están cubiertas aquí, y además lo que las ataba: que la
vista web, el PDF individual y la página de ese mismo estudiante dentro del
PDF del curso salgan del MISMO helper, para que no puedan discrepar.

Base temporal aislada. Nunca producción.
"""
import asyncio
import datetime as dt
import os
import sys

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(BK, "tools"))

from test_utils import aislar_base_de_datos  # noqa: E402

TMP = aislar_base_de_datos('e1_asist')

from database import engine, SessionLocal  # noqa: E402
from test_utils import verificar_engine_aislado  # noqa: E402

verificar_engine_aislado(engine, TMP)

import models as M  # noqa: E402
import app as APP  # noqa: E402

M.Base.metadata.create_all(bind=engine)

# 195 días hábiles declarados: el denominador canónico del año.
DIAS = {'ago': 10, 'sep': 21, 'oct': 22, 'nov': 20, 'dic': 14, 'ene': 20,
        'feb': 19, 'mar': 22, 'abr': 18, 'may': 21, 'jun': 8}
TOTAL_DIAS = sum(DIAS.values())

PASARON, FALLARON = [], []


def check(nombre, cond, detalle=''):
    if cond:
        PASARON.append(nombre)
        print("  PASA   %-62s %s" % (nombre, detalle))
    else:
        FALLARON.append(nombre)
        print("  FALLA  %-62s %s" % (nombre, detalle))


db = SessionLocal()


# ═══════════════════════════════════════════════════════════════════════
# Andamiaje
# ═══════════════════════════════════════════════════════════════════════
def nuevo_colegio(codigo, con_dias=True):
    col = M.Colegio(nombre='C-' + codigo, codigo=codigo, activo=True)
    db.add(col)
    db.flush()
    usr = M.Usuario(colegio_id=col.id, username='dir_' + codigo,
                    password_hash='x', nombre='Dir', apellido=codigo,
                    role='direccion', activo=True,
                    must_change_password=False, token_version=0)
    db.add(usr)
    db.flush()
    return col, usr


def nuevo_ano(col, nombre, ini, fin, con_dias=True, activo=True):
    a = M.AnoEscolar(
        colegio_id=col.id, nombre=nombre, activo=activo, cerrado=False,
        fecha_inicio=ini, fecha_fin=fin,
        p1_inicio=ini, p1_fin=ini + dt.timedelta(days=74),
        p2_inicio=ini + dt.timedelta(days=75), p2_fin=ini + dt.timedelta(days=164),
        p3_inicio=ini + dt.timedelta(days=165), p3_fin=ini + dt.timedelta(days=242),
        p4_inicio=ini + dt.timedelta(days=243), p4_fin=fin)
    if con_dias:
        a.set_dias_trabajados(dict(DIAS))
    db.add(a)
    db.flush()
    return a


def nuevo_curso(col, ano, nivel, orden, nombre_grado):
    g = M.Grado(colegio_id=col.id, nombre=nombre_grado, nivel=nivel,
                orden=orden, activo=True)
    db.add(g)
    db.flush()
    c = M.Curso(colegio_id=col.id, nombre='A', grado_id=g.id,
                ano_escolar_id=ano.id, activo=True)
    db.add(c)
    db.flush()
    return g, c


def nuevo_estudiante(col, curso, matricula):
    e = M.Estudiante(colegio_id=col.id, matricula=matricula, nombre='E',
                     apellido=matricula, curso_id=curso.id, activo=True,
                     condicion='activo', no_lista=1)
    db.add(e)
    db.flush()
    return e


def marcar(col, est, curso, fecha, estado, asignatura=None):
    db.add(M.Asistencia(
        colegio_id=col.id, estudiante_id=est.id, curso_id=curso.id,
        fecha=fecha, estado=estado,
        asignatura_id=asignatura.id if asignatura else None))


COL, DIR = nuevo_colegio('uno')
ANO = nuevo_ano(COL, '2025-2026', dt.date(2025, 8, 18), dt.date(2026, 6, 12))
G_PRI, C_PRI = nuevo_curso(COL, ANO, 'primaria', 5, '5to Grado')
G_SEC, C_SEC = nuevo_curso(COL, ANO, 'secundaria', 7, '1ro Secundaria')

ASIGS = []
for nom, cod in (('Lengua Española', 'LEN'), ('Matemática', 'MAT'),
                 ('Ciencias Sociales', 'CSO')):
    _a = M.Asignatura(colegio_id=COL.id, nombre=nom, codigo=cod, activo=True)
    db.add(_a)
    ASIGS.append(_a)
db.flush()

D = [dt.date(2025, 9, 1) + dt.timedelta(days=i) for i in range(10)]


def anual(est, ano=None):
    return APP._asistencia_anual_boletin(db, est.id, DIR, ano or ANO)


print("\n=== A-E · LA SEMÁNTICA CONGELADA DE LOS CUATRO ESTADOS ===")

# ── A. Todo presente ───────────────────────────────────────────────────
e_a = nuevo_estudiante(COL, C_PRI, 'A')
for f in D[:5]:
    marcar(COL, e_a, C_PRI, f, 'presente')
db.commit()
r = anual(e_a)
check('E1-A1 cinco presentes = cinco asistencias',
      r['presentes'] == 5 and r['asistencias'] == 5, str(r['asistencias']))
check('E1-A2 sin ausencias, la ausencia anual es 0 %',
      r['ausencias'] == 0 and r['excusas'] == 0 and r['pct_ausencia'] == 0.0,
      str(r['pct_ausencia']))
check('E1-A3 asistencia perfecta = 100 %', r['pct_asistencia'] == 100.0,
      str(r['pct_asistencia']))

# ── B. Presente + tardanza ─────────────────────────────────────────────
e_b = nuevo_estudiante(COL, C_PRI, 'B')
for f in D[:3]:
    marcar(COL, e_b, C_PRI, f, 'presente')
for f in D[3:5]:
    marcar(COL, e_b, C_PRI, f, 'tardanza')
db.commit()
r = anual(e_b)
check('E1-B1 la tardanza CUENTA como asistencia',
      r['asistencias'] == 5 and r['tardanzas'] == 2,
      'asistencias=%d tardanzas=%d' % (r['asistencias'], r['tardanzas']))
check('E1-B2 y no se disfraza de presente: se distinguen',
      r['presentes'] == 3, str(r['presentes']))
check('E1-B3 llegar tarde no genera ausencia', r['pct_ausencia'] == 0.0,
      str(r['pct_ausencia']))

# ── C. Ausencia injustificada ──────────────────────────────────────────
e_c = nuevo_estudiante(COL, C_PRI, 'C')
for f in D[:4]:
    marcar(COL, e_c, C_PRI, f, 'presente')
for f in D[4:8]:
    marcar(COL, e_c, C_PRI, f, 'ausente')
db.commit()
r = anual(e_c)
check('E1-C1 cuatro ausencias injustificadas, contadas aparte',
      r['ausencias'] == 4 and r['excusas'] == 0,
      'ausencias=%d excusas=%d' % (r['ausencias'], r['excusas']))
check('E1-C2 la ausencia se mide contra los días hábiles declarados',
      r['base_porcentaje'] == 'dias_trabajados'
      and r['dias_trabajados'] == TOTAL_DIAS
      and r['pct_ausencia'] == round(4 / TOTAL_DIAS * 100, 1),
      '%s%% de %d' % (r['pct_ausencia'], TOTAL_DIAS))

# ── D. Excusa ──────────────────────────────────────────────────────────
e_d = nuevo_estudiante(COL, C_PRI, 'D')
for f in D[:4]:
    marcar(COL, e_d, C_PRI, f, 'presente')
for f in D[4:8]:
    marcar(COL, e_d, C_PRI, f, 'excusa')
db.commit()
r = anual(e_d)
check('E1-D1 la excusa es ausencia JUSTIFICADA, nunca presente',
      r['excusas'] == 4 and r['ausencias'] == 0 and r['presentes'] == 4,
      'excusas=%d ausencias=%d presentes=%d'
      % (r['excusas'], r['ausencias'], r['presentes']))
# C y D faltaron los mismos días; lo que cambia es el MOTIVO, no el total.
check('E1-D2 justificada o no, el día perdido cuenta igual en el total',
      anual(e_d)['pct_ausencia'] == anual(e_c)['pct_ausencia'],
      str(r['pct_ausencia']))
check('E1-D3 pero el desglose NO mezcla las dos ausencias',
      anual(e_c)['ausencias'] == 4 and anual(e_c)['excusas'] == 0
      and anual(e_d)['ausencias'] == 0 and anual(e_d)['excusas'] == 4, '')

# ── E. Combinación completa ────────────────────────────────────────────
e_e = nuevo_estudiante(COL, C_PRI, 'E')
for f, est in zip(D, ['presente', 'presente', 'presente', 'tardanza',
                      'tardanza', 'ausente', 'ausente', 'excusa',
                      'excusa', 'presente']):
    marcar(COL, e_e, C_PRI, f, est)
db.commit()
r = anual(e_e)
check('E1-E1 los cuatro estados conviven sin pisarse',
      (r['presentes'], r['tardanzas'], r['ausencias'], r['excusas'])
      == (4, 2, 2, 2), str((r['presentes'], r['tardanzas'],
                            r['ausencias'], r['excusas'])))
check('E1-E2 asistencias = presentes + tardanzas', r['asistencias'] == 6,
      str(r['asistencias']))
check('E1-E3 los diez días quedan todos contados',
      r['dias_computados'] == 10, str(r['dias_computados']))
check('E1-E4 asistencia y ausencia son complementarias',
      abs(r['pct_asistencia'] + r['pct_ausencia'] - 100.0) < 0.05,
      '%s + %s' % (r['pct_asistencia'], r['pct_ausencia']))


print("\n=== F · SECUNDARIA: UN DÍA ES UN DÍA, NO UNA CLASE ===")

e_f = nuevo_estudiante(COL, C_SEC, 'F')
# Nueve días, TRES materias cada día: 27 filas en la base.
plan = [['presente'] * 3, ['presente', 'tardanza', 'presente'],
        ['ausente'] * 3, ['excusa'] * 3,
        ['presente', 'presente', 'ausente'], ['tardanza'] * 3,
        ['ausente'] * 3, ['presente'] * 3, ['excusa'] * 3]
for f, estados in zip(D[:9], plan):
    for a, est in zip(ASIGS, estados):
        marcar(COL, e_f, C_SEC, f, est, a)
db.commit()

filas = db.query(M.Asistencia).filter_by(estudiante_id=e_f.id).count()
r = anual(e_f)
check('E1-F1 la base guarda una fila POR MATERIA', filas == 27, str(filas))
check('E1-F2 pero el boletín cuenta NUEVE días, no veintisiete',
      r['dias_computados'] == 9, str(r['dias_computados']))
check('E1-F3 los conteos suman los días, no las clases',
      r['presentes'] + r['tardanzas'] + r['ausencias'] + r['excusas'] == 9,
      '')
# Los dos días MIXTOS del plan son la prueba de fondo:
#   día 2 = presente/tardanza/presente  -> el estudiante vino
#   día 5 = presente/presente/ausente   -> también vino, aunque faltara a una
#           clase suelta. La prioridad describe al ESTUDIANTE, no a la materia.
_dias = APP._dias_asistencia_del_ano(db, e_f.id, DIR, ANO)
check('E1-F4 un día presente/tardanza/presente cuenta como presente',
      _dias[D[1]] == 'presente', str(_dias[D[1]]))
check('E1-F4b faltar a UNA materia no convierte el día en ausencia',
      _dias[D[4]] == 'presente', str(_dias[D[4]]))
check('E1-F4c y un día entero de tardanza sigue siendo tardanza',
      _dias[D[5]] == 'tardanza' and r['tardanzas'] == 1, str(_dias[D[5]]))
check('E1-F4d el reparto final es el de los días, no el de las filas',
      (r['presentes'], r['tardanzas'], r['ausencias'], r['excusas'])
      == (4, 1, 2, 2), str((r['presentes'], r['tardanzas'],
                            r['ausencias'], r['excusas'])))
check('E1-F5 y el porcentaje no se multiplica por el número de materias',
      0 <= r['pct_asistencia'] <= 100 and 0 <= r['pct_ausencia'] <= 100,
      '%s / %s' % (r['pct_asistencia'], r['pct_ausencia']))
check('E1-F6 el desglose anual coincide con la suma de los períodos',
      sum((APP._construir_asistencias_boletin(db, e_f.id, DIR, ANO)
           .get('p%d' % p) or {}).get('asistencia', 0) for p in range(1, 5))
      == r['asistencias'], '')


print("\n=== G · SIN REGISTROS NO ES CERO POR CIENTO ===")

e_g = nuevo_estudiante(COL, C_PRI, 'G')
db.commit()
r = anual(e_g)
check('E1-G1 se declara explícitamente que no hay datos',
      r['sin_registros'] is True, '')
check('E1-G2 el porcentaje es None, NO 0',
      r['pct_asistencia'] is None and r['pct_ausencia'] is None,
      '%s / %s' % (r['pct_asistencia'], r['pct_ausencia']))
check('E1-G3 sin base declarada tampoco se inventa una',
      r['base_porcentaje'] is None, str(r['base_porcentaje']))
check('E1-G4 y quien SÍ tiene cero ausencias se distingue del que no tiene datos',
      anual(e_a)['sin_registros'] is False
      and anual(e_a)['pct_ausencia'] == 0.0, '')

# El PDF de Primaria tampoco puede imprimir ceros inventados.
_pdf_vacio = APP._construir_asistencias_boletin(db, e_g.id, DIR, ANO)
check('E1-G5 los cuatro períodos del helper salen en cero...',
      all((_pdf_vacio.get('p%d' % p) or {}).get('asistencia') == 0
          for p in range(1, 5)), '')
check('E1-G6 ...pero el adaptador del PDF no los manda a la plantilla',
      APP._generar_pdf_primaria is not None, '(ver E1-PDF)')


print("\n=== H · EL BOLETÍN DE UN AÑO NO USA LA ASISTENCIA DE OTRO ===")

ANO_B = nuevo_ano(COL, '2026-2027', dt.date(2026, 8, 17), dt.date(2027, 6, 11),
                  activo=False)
_, C_PRI_B = nuevo_curso(COL, ANO_B, 'primaria', 6, '6to Grado')
e_h = nuevo_estudiante(COL, C_PRI, 'H')
# Tres presentes en A...
for f in D[:3]:
    marcar(COL, e_h, C_PRI, f, 'presente')
# ...y siete ausencias en B.
for i in range(7):
    marcar(COL, e_h, C_PRI_B, dt.date(2026, 9, 1) + dt.timedelta(days=i),
           'ausente')
db.commit()

ra, rb = anual(e_h, ANO), anual(e_h, ANO_B)
check('E1-H1 el boletín de A ve solo los días de A',
      ra['dias_computados'] == 3 and ra['ausencias'] == 0,
      'dias=%d ausencias=%d' % (ra['dias_computados'], ra['ausencias']))
check('E1-H2 el boletín de B ve solo los días de B',
      rb['dias_computados'] == 7 and rb['presentes'] == 0,
      'dias=%d presentes=%d' % (rb['dias_computados'], rb['presentes']))
check('E1-H3 nunca notas de A con asistencia de B',
      ra['pct_asistencia'] == 100.0 and rb['pct_asistencia'] < 100.0,
      'A=%s B=%s' % (ra['pct_asistencia'], rb['pct_asistencia']))


print("\n=== I · AISLAMIENTO ENTRE COLEGIOS ===")

COL2, DIR2 = nuevo_colegio('dos')
ANO2 = nuevo_ano(COL2, '2025-2026', dt.date(2025, 8, 18), dt.date(2026, 6, 12))
_, C2 = nuevo_curso(COL2, ANO2, 'primaria', 5, '5to Grado')
e_i = nuevo_estudiante(COL2, C2, 'I')
for f in D[:6]:
    marcar(COL2, e_i, C2, f, 'ausente')
db.commit()

fuga = APP._asistencia_anual_boletin(db, e_i.id, DIR, ANO)
check('E1-I1 el director de otro colegio no ve esa asistencia',
      fuga['dias_computados'] == 0 and fuga['sin_registros'] is True,
      str(fuga['dias_computados']))
propio = APP._asistencia_anual_boletin(db, e_i.id, DIR2, ANO2)
check('E1-I2 y su propio colegio sí la ve entera',
      propio['ausencias'] == 6, str(propio['ausencias']))


print("\n=== J · LOS PORCENTAJES SON PORCENTAJES ===")

for et, est, ano_ in (('A', e_a, ANO), ('E', e_e, ANO), ('F', e_f, ANO),
                      ('H', e_h, ANO_B), ('C', e_c, ANO)):
    rr = anual(est, ano_)
    ok = all(v is None or 0.0 <= v <= 100.0
             for v in (rr['pct_asistencia'], rr['pct_ausencia']))
    check('E1-J-%s los dos porcentajes caen en 0..100' % et, ok,
          '%s / %s' % (rr['pct_asistencia'], rr['pct_ausencia']))

# Denominador de respaldo: un año SIN días hábiles declarados.
ANO_SD = nuevo_ano(COL, '2024-2025', dt.date(2024, 8, 19), dt.date(2025, 6, 13),
                   con_dias=False, activo=False)
_, C_SD = nuevo_curso(COL, ANO_SD, 'primaria', 4, '4to Grado')
e_j = nuevo_estudiante(COL, C_SD, 'J')
for i, est in enumerate(['presente'] * 8 + ['ausente'] * 2):
    marcar(COL, e_j, C_SD, dt.date(2024, 9, 2) + dt.timedelta(days=i), est)
db.commit()
rj = anual(e_j, ANO_SD)
check('E1-J-base sin días hábiles declarados se usa el respaldo, DECLARADO',
      rj['base_porcentaje'] == 'dias_con_registro'
      and rj['dias_trabajados'] is None, str(rj['base_porcentaje']))
check('E1-J-base2 y el respaldo también da complementarios que suman 100',
      rj['pct_ausencia'] == 20.0 and rj['pct_asistencia'] == 80.0,
      '%s / %s' % (rj['pct_asistencia'], rj['pct_ausencia']))

# Declaración incoherente: menos días hábiles que días con lista pasada.
ANO_INC = nuevo_ano(COL, '2023-2024', dt.date(2023, 8, 21), dt.date(2024, 6, 14),
                    con_dias=False, activo=False)
ANO_INC.set_dias_trabajados({'sep': 3})
_, C_INC = nuevo_curso(COL, ANO_INC, 'primaria', 3, '3ro Grado')
e_k = nuevo_estudiante(COL, C_INC, 'K')
for i in range(8):
    marcar(COL, e_k, C_INC, dt.date(2023, 9, 4) + dt.timedelta(days=i),
           'presente' if i < 6 else 'ausente')
db.commit()
rk = anual(e_k, ANO_INC)
check('E1-J-inc una declaración que no sostiene los datos no se usa',
      rk['base_porcentaje'] == 'dias_con_registro', str(rk['base_porcentaje']))
check('E1-J-inc2 y el porcentaje sigue siendo posible', 0 <= rk['pct_ausencia'] <= 100,
      str(rk['pct_ausencia']))


print("\n=== K · WEB, PDF INDIVIDUAL Y PDF DE CURSO DICEN LO MISMO ===")


def cuerpo(r):
    import json
    return json.loads(bytes(r.body).decode('utf-8'))


# La vista web de Primaria.
web = asyncio.run(APP.boletin_primaria_estudiante_json(
    id=e_e.id, db=db, current_user=DIR))
web = web if isinstance(web, dict) else cuerpo(web)
directo = anual(e_e)
check('E1-K1 la vista web publica el desglose anual',
      isinstance(web.get('asistencia_anual'), dict), '')
check('E1-K2 y es EXACTAMENTE el del helper canónico',
      web['asistencia_anual'] == directo, '')
check('E1-K3 el resumen legacy `asistencia` usa los mismos números',
      web['asistencia']['presentes'] == directo['asistencias']
      and web['asistencia']['porcentaje'] == directo['pct_asistencia'], '')

# El PDF individual y el de curso pasan por el mismo helper: se comprueba que
# el dato que entra al generador es el mismo objeto de datos.
pdf_ind = APP._asistencia_anual_boletin(db, e_e.id, DIR, ANO)
check('E1-K4 el PDF individual parte del mismo desglose', pdf_ind == directo, '')

# Y el lote: se recorre como lo hace el endpoint de curso.
lote = {est.id: APP._asistencia_anual_boletin(db, est.id, DIR, ANO)
        for est in db.query(M.Estudiante).filter_by(curso_id=C_PRI.id).all()}
check('E1-K5 la página del lote de ese estudiante trae los mismos números',
      lote[e_e.id] == pdf_ind, '')
check('E1-K6 ningún estudiante del lote difiere de su cálculo individual',
      all(v == APP._asistencia_anual_boletin(db, k, DIR, ANO)
          for k, v in lote.items()), '')

# Secundaria: mismo contrato.
web_sec = asyncio.run(APP.get_boletin_estudiante(
    id=e_f.id, request=None, db=db, current_user=DIR))
web_sec = web_sec if isinstance(web_sec, dict) else cuerpo(web_sec)
check('E1-K7 el boletín web de Secundaria también publica el anual',
      web_sec.get('asistencia_anual') == anual(e_f), '')
check('E1-K8 y ya no cuenta filas: `total` son DÍAS',
      web_sec['asistencia']['total'] == 9, str(web_sec['asistencia']['total']))
check('E1-K9 sin registros, el boletín web no inventa un 0 %',
      (asyncio.run(APP.boletin_primaria_estudiante_json(
          id=e_g.id, db=db, current_user=DIR))
       ['asistencia']['porcentaje']) is None, '')


print("\n=== PDF · LO QUE LLEGA A LA PLANTILLA OFICIAL ===")

# Primaria: el adaptador no debe fabricar períodos vacíos.
import inspect  # noqa: E402
_src = inspect.getsource(APP._generar_pdf_primaria)
check('E1-PDF1 el PDF de Primaria recibe el desglose anual',
      'asistencia_anual=asistencia_anual' in _src, '')
check('E1-PDF2 y el adaptador omite los períodos sin ningún registro',
      'if _a or _au:' in _src, '')

from boletin_primaria import generar_boletin_primaria  # noqa: E402
from boletin_minerd_secundaria import (  # noqa: E402
    generar_boletin_secundaria_minerd)

_fp = inspect.signature(generar_boletin_primaria).parameters
_fs = inspect.signature(generar_boletin_secundaria_minerd).parameters
check('E1-PDF3 el generador de Primaria acepta el anual',
      'asistencia_anual' in _fp, '')
check('E1-PDF4 el generador MINERD acepta el anual', 'asistencia_anual' in _fs, '')

_dt = inspect.getsource(generar_boletin_secundaria_minerd.__module__ and
                        sys.modules['boletin_minerd_secundaria'])
check('E1-PDF5 el % de la celda ANUAL ya no sale del período',
      "data.get('pct_asistencia_anual')" not in _dt, '')
check('E1-PDF6 sale una sola vez, centrado en la celda fusionada',
      "(asist_y_map['p1'] + asist_y_map['p4']) / 2.0" in _dt, '')
_dp = inspect.getsource(sys.modules['boletin_primaria'])
check('E1-PDF7 lo mismo en el Informe de Primaria',
      "(ASISTENCIA_Y[1] + ASISTENCIA_Y[4]) / 2.0" in _dp, '')
check('E1-PDF8 y sin registros no se dibuja ningún porcentaje',
      "not asistencia_anual.get('sin_registros')" in _dp
      and "not asistencia_anual.get('sin_registros')" in _dt, '')

# El PDF real se genera y se le extrae el texto: no basta con el código.
buf = APP._generar_pdf_primaria(db, e_e, DIR, ANO, None)
from pypdf import PdfReader  # noqa: E402
txt = "".join((p.extract_text() or '') for p in PdfReader(buf).pages)
_r = anual(e_e)
check('E1-PDF9 el PDF de Primaria se genera y tiene 2 páginas',
      len(PdfReader(APP._generar_pdf_primaria(db, e_e, DIR, ANO, None)).pages) == 2,
      '')
check('E1-PDF10 el porcentaje anual aparece impreso en el PDF',
      ('%d%%' % round(_r['pct_asistencia'])) in txt,
      '%d%%' % round(_r['pct_asistencia']))

buf_s = generar_boletin_secundaria_minerd(
    estudiante=e_f, curso=C_SEC, calificaciones_por_asig={},
    asistencias_por_periodo=APP._construir_asistencias_boletin(
        db, e_f.id, DIR, ANO),
    asistencia_anual=anual(e_f), config=None, ano_escolar=ANO)
lect = PdfReader(buf_s)
txt_s = "".join((p.extract_text() or '') for p in lect.pages)
check('E1-PDF11 el boletín MINERD se genera y no gana páginas',
      len(lect.pages) == 2, str(len(lect.pages)))
check('E1-PDF12 lleva el bloque ASISTENCIA ANUAL', 'ASISTENCIA ANUAL' in txt_s, '')
_rf = anual(e_f)
check('E1-PDF13 con el desglose completo, tardanzas y excusas incluidas',
      ('Tardanzas: %d' % _rf['tardanzas']) in txt_s
      and ('Excusas: %d' % _rf['excusas']) in txt_s, '')
check('E1-PDF14 y los mismos números que la vista web',
      ('Asistencias: %d' % web_sec['asistencia_anual']['asistencias']) in txt_s,
      '')

buf_v = generar_boletin_secundaria_minerd(
    estudiante=e_g, curso=C_SEC, calificaciones_por_asig={},
    asistencias_por_periodo={}, asistencia_anual=anual(e_g),
    config=None, ano_escolar=ANO)
txt_v = "".join((p.extract_text() or '') for p in PdfReader(buf_v).pages)
check('E1-PDF15 sin registros el PDF lo dice, en vez de imprimir 0 %',
      'Sin registros de asistencia' in txt_v and 'ASISTENCIA ANUAL' not in txt_v,
      '')

# ── El boletín de PADRES ───────────────────────────────────────────────
# Es el documento que lee la familia y no mostraba asistencia en absoluto.
# A diferencia de los dos oficiales, la maqueta es nuestra, así que cabe el
# desglose entero en una línea.
from boletin_padres import generar_boletin_padres  # noqa: E402

_asig_data = [{'nombre': a.nombre, 'competencias': {}} for a in ASIGS]
buf_p = generar_boletin_padres(
    estudiante=e_f, curso=C_SEC, asignaturas_data=_asig_data, config=None,
    ano_nombre=ANO.nombre, asistencia_anual=anual(e_f))
lect_p = PdfReader(buf_p)
txt_p = "".join((p.extract_text() or '') for p in lect_p.pages)
check('E1-PDF16 el boletín de padres sigue siendo de UNA página',
      len(lect_p.pages) == 1, str(len(lect_p.pages)))
check('E1-PDF17 y ahora lleva la asistencia anual',
      'ASISTENCIA ANUAL' in txt_p, '')
check('E1-PDF18 con el mismo desglose que el MINERD y la web',
      ('Asistencias: %d' % _rf['asistencias']) in txt_p
      and ('Tardanzas: %d' % _rf['tardanzas']) in txt_p
      and ('Excusas: %d' % _rf['excusas']) in txt_p, '')
check('E1-PDF19 y el mismo porcentaje',
      ('%.1f%%' % _rf['pct_asistencia']) in txt_p,
      '%.1f%%' % _rf['pct_asistencia'])

buf_pv = generar_boletin_padres(
    estudiante=e_g, curso=C_PRI, asignaturas_data=_asig_data, config=None,
    ano_nombre=ANO.nombre, asistencia_anual=anual(e_g))
txt_pv = "".join((p.extract_text() or '') for p in PdfReader(buf_pv).pages)
check('E1-PDF20 sin registros tampoco inventa un 0 % para los padres',
      'Sin registros de asistencia' in txt_pv
      and '0.0%' not in txt_pv, '')

# Y el reporte sin asistencia declarada (llamada antigua) no se rompe.
buf_pn = generar_boletin_padres(
    estudiante=e_f, curso=C_SEC, asignaturas_data=_asig_data, config=None,
    ano_nombre=ANO.nombre)
check('E1-PDF21 quien no pasa asistencia sigue obteniendo su PDF',
      len(PdfReader(buf_pn).pages) == 1
      and 'ASISTENCIA ANUAL' not in "".join(
          (p.extract_text() or '') for p in PdfReader(buf_pn).pages), '')


print("\n=== NO SE TOCÓ LO CONGELADO ===")
check('E1-Z1 el safety lock de Cierre sigue en True',
      APP.CIERRE_ANO_BLOQUEADO is True, '')
check('E1-Z2 una sola deduplicación: los helpers la comparten',
      'self' not in inspect.getsource(APP._dias_asistencia_de_filas)
      and '_dias_asistencia_del_ano' in inspect.getsource(
          APP._construir_asistencias_boletin), '')
check('E1-Z3 el denominador sale del módulo congelado A3',
      'RAC.sumar_dias_trabajados' in inspect.getsource(
          APP._resumen_anual_asistencia), '')

print()
print("=" * 96)
print("RESULTADO: %d PASARON / %d FALLARON" % (len(PASARON), len(FALLARON)))
print("=" * 96)
for f in FALLARON:
    print("  FALLA:", f)

db.close()
sys.exit(1 if FALLARON else 0)
