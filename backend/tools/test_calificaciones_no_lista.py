# -*- coding: utf-8 -*-
"""
EducaOne — CAL-NL-1: Calificaciones de Secundaria por número de lista.

La tabla mostraba la POSICIÓN (idx + 1) sobre una lista ordenada por apellido,
así que un estudiante con no_lista=37 aparecía como 32. Ahora el endpoint
entrega `no_lista` y ordena por él; sin número, al final y el frontend
muestra «—». Cambiar el orden NO cambia a quién pertenece cada nota: todo
sigue indexado por estudiante_id.

Con SNAP=<ruta> guarda {estudiante_id: fila sin no_lista} para comparar con
la versión anterior del endpoint.

Base temporal aislada. Nunca producción.

Uso:
    cd backend
    python tools/test_calificaciones_no_lista.py
"""
import json
import os
import sys

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(BK, "tools"))

from test_utils import aislar_base_de_datos  # noqa: E402

TMP = aislar_base_de_datos('cal_no_lista')

from database import engine, SessionLocal  # noqa: E402
from test_utils import verificar_engine_aislado  # noqa: E402

verificar_engine_aislado(engine, TMP)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import event  # noqa: E402

import models as M  # noqa: E402
import app as APP  # noqa: E402
from auth import create_token  # noqa: E402

M.Base.metadata.create_all(bind=engine)
client = TestClient(APP.app)
RES = []


def check(nombre, ok, detalle=''):
    RES.append((nombre, bool(ok)))
    print(('  OK  ' if ok else '  FALLA ') + nombre + ('' if ok else '  -> ' + str(detalle)[:300]))


db = SessionLocal()


def add(o):
    db.add(o)
    db.flush()
    return o


COL = add(M.Colegio(nombre='C1', codigo='c1', activo=True))
ANO = add(M.AnoEscolar(colegio_id=COL.id, nombre='2026-2027', activo=True))
T_M = add(M.Tanda(colegio_id=COL.id, nombre='Matutina', hora_inicio='07:30', hora_fin='12:30', activo=True))
G = add(M.Grado(colegio_id=COL.id, nombre='2do Secundaria', nivel='secundaria', orden=2))
CUR = add(M.Curso(colegio_id=COL.id, nombre='A', grado_id=G.id, tanda_id=T_M.id, ano_escolar_id=ANO.id, activo=True))
ASIG = add(M.Asignatura(colegio_id=COL.id, nombre='Lengua', codigo='LE', area='X', activo=True))
DIR = add(M.Usuario(colegio_id=COL.id, username='dir', password_hash='x', nombre='Dir', apellido='T',
                    role='direccion', activo=True, must_change_password=False, token_version=0))
PROF = add(M.Usuario(colegio_id=COL.id, username='prof', password_hash='x', nombre='Prof', apellido='T',
                     role='profesor', activo=True, must_change_password=False, token_version=0))
add(M.AsignacionProfesor(colegio_id=COL.id, profesor_id=PROF.id, curso_id=CUR.id, asignatura_id=ASIG.id,
                         ano_escolar_id=ANO.id, activo=True))

# El orden alfabético NO coincide con el número de lista (el caso real: 37 se veía como 32).
FICHAS = [  # (apellido, nombre, no_lista, activo)
    ('Alvarez', 'Ana', 3, True),
    ('Baez', 'Bruno', 37, True),          # "Ney" del caso real: alfabéticamente 2.º, su número es 37
    ('Castro', 'Carla', 1, True),
    ('Diaz', 'Dario', None, True),        # sin número guardado -> «—», al final
    ('Espinal', 'Eva', 2, True),
    ('Fermin', 'Fabio', 5, False),        # retirado: este endpoint no lo lista (como antes)
    ('Garcia', 'Gema', None, True),
]
ESTS = []
for i, (ap, nom, nl, act) in enumerate(FICHAS):
    e = add(M.Estudiante(colegio_id=COL.id, nombre=nom, apellido=ap, curso_id=CUR.id, activo=act, no_lista=nl))
    ESTS.append(e)
    # Nota distinta por estudiante y competencia: 50 + 10*i + competencia.
    for comp in range(1, 5):
        add(M.CalificacionSecundaria(colegio_id=COL.id, estudiante_id=e.id, asignatura_id=ASIG.id,
                                     ano_escolar_id=ANO.id, competencia_numero=comp,
                                     p1=50 + 10 * i + comp, p2=40 + 10 * i + comp))
db.commit()
NOTA_ESPERADA = {e.id: {c: (50 + 10 * i + c, 40 + 10 * i + c) for c in range(1, 5)} for i, e in enumerate(ESTS)}

ESCRITURAS = []


@event.listens_for(engine, 'before_cursor_execute')
def _detector(conn, cursor, statement, params, context, executemany):
    if statement.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')):
        ESCRITURAS.append(statement.split()[0:3])


def pedir(u):
    r = client.get('/api/calificaciones-secundaria/curso/%d/asignatura/%d' % (CUR.id, ASIG.id),
                   headers={'Authorization': 'Bearer ' + create_token(u)})
    return r.status_code, r.json()


cod, data = pedir(DIR)
filas = data.get('calificaciones', [])
if os.environ.get('SNAP'):
    json.dump({str(f['estudiante']['id']): {**f, 'estudiante': {k: v for k, v in f['estudiante'].items()
                                                                 if k != 'no_lista'}} for f in filas},
              open(os.environ['SNAP'], 'w', encoding='utf-8'), ensure_ascii=False, indent=1, sort_keys=True)

por_id = {e.id: e for e in ESTS}
print("\n=== ORDEN Y NÚMERO ===")
check('N-01 responde 200', cod == 200, data)
check('N-02 cada fila trae el no_lista GUARDADO (sin inventar)',
      all(f['estudiante'].get('no_lista', 'falta') == por_id[f['estudiante']['id']].no_lista for f in filas),
      [(f['estudiante']['nombre_completo'], f['estudiante'].get('no_lista', 'falta')) for f in filas])
check('N-03 orden por número de lista; sin número al final (por apellido)',
      [f['estudiante']['nombre_completo'] for f in filas]
      == ['Castro, Carla', 'Espinal, Eva', 'Alvarez, Ana', 'Baez, Bruno', 'Diaz, Dario', 'Garcia, Gema'],
      [f['estudiante']['nombre_completo'] for f in filas])
fila_37 = next(f for f in filas if f['estudiante']['nombre_completo'] == 'Baez, Bruno')
check('N-04 el estudiante con no_lista=37 se identifica como 37, no por su posición',
      fila_37['estudiante']['no_lista'] == 37 and filas.index(fila_37) + 1 != 37, '')
check('N-05 sin número: no_lista es null (el frontend muestra «—»)',
      [f['estudiante']['no_lista'] for f in filas if f['estudiante']['nombre_completo'].startswith(('Diaz', 'Garcia'))]
      == [None, None], '')

print("\n=== PERTENENCIA DE LAS NOTAS ===")
check('N-06 aparecen todos los estudiantes activos, una vez cada uno',
      sorted(f['estudiante']['id'] for f in filas) == sorted(e.id for e in ESTS if e.activo), '')
check('N-07 el retirado sigue fuera de este listado (tratamiento previo)',
      ESTS[5].id not in {f['estudiante']['id'] for f in filas}, '')
check('N-08 cada nota pertenece a su estudiante_id (p1 y p2 de las 4 competencias)',
      all((f['competencias'][str(c)]['p1'], f['competencias'][str(c)]['p2'])
          == NOTA_ESPERADA[f['estudiante']['id']][c] for f in filas for c in range(1, 5)),
      [(f['estudiante']['id'], {c: (f['competencias'][str(c)]['p1'], f['competencias'][str(c)]['p2'])
                                for c in range(1, 5)}) for f in filas][:2])
check('N-09 el PC de cada fila corresponde a sus propias competencias',
      all(abs(f['pc_por_periodo']['pc1'] - sum(NOTA_ESPERADA[f['estudiante']['id']][c][0] for c in range(1, 5)) / 4) < 0.6
          for f in filas), [f['pc_por_periodo'] for f in filas][:2])
cod_p, data_p = pedir(PROF)
check('N-10 el profesor asignado recibe el mismo orden y los mismos números',
      cod_p == 200 and [(f['estudiante']['id'], f['estudiante']['no_lista']) for f in data_p['calificaciones']]
      == [(f['estudiante']['id'], f['estudiante']['no_lista']) for f in filas], cod_p)
check('N-11 consultar no escribe nada', not ESCRITURAS, ESCRITURAS)
db.expire_all()
check('N-12 los datos guardados no cambian (no_lista y notas)',
      [db.get(M.Estudiante, e.id).no_lista for e in ESTS] == [f[2] for f in FICHAS]
      and db.query(M.CalificacionSecundaria).count() == 4 * len(ESTS), '')
db.close()

ok = sum(1 for _, r in RES if r)
print('\nRESULTADO CAL-NL-1: %d PASARON / %d FALLARON' % (ok, len(RES) - ok))
sys.exit(0 if ok == len(RES) else 1)
