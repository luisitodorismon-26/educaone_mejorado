# -*- coding: utf-8 -*-
"""
EducaOne — ASIS-TANDA-1: "Asistencia hoy" agrupable por tanda.

El panel del dashboard agrupa los cursos por tanda (Matutina, Vespertina,
sin tanda al final) y ordena por grado y sección. El backend solo AÑADE a
cada fila los datos estructurados de tanda y grado: los cursos, conteos,
porcentajes y "Sin registrar" no cambian, y consultar no escribe nada.

Con la variable de entorno SNAP=<ruta> guarda la respuesta en JSON para
comparar antes/después del cambio.

Base temporal aislada. Nunca producción.

Uso:
    cd backend
    python tools/test_asistencia_hoy_tanda.py
"""
import json
import os
import sys

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(BK, "tools"))

from test_utils import aislar_base_de_datos  # noqa: E402

TMP = aislar_base_de_datos('asis_tanda1')

from database import engine, SessionLocal  # noqa: E402
from test_utils import verificar_engine_aislado  # noqa: E402

verificar_engine_aislado(engine, TMP)

from datetime import date  # noqa: E402

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
# Vespertina se crea PRIMERO: el orden no puede depender del id.
T_V = add(M.Tanda(colegio_id=COL.id, nombre='Vespertina', hora_inicio='14:00', hora_fin='18:00', activo=True))
T_M = add(M.Tanda(colegio_id=COL.id, nombre='Matutina', hora_inicio='07:30', hora_fin='12:30', activo=True))
G_S2 = add(M.Grado(colegio_id=COL.id, nombre='2do Secundaria', nivel='secundaria', orden=2))
G_P1 = add(M.Grado(colegio_id=COL.id, nombre='1ro Primaria', nivel='primaria', orden=7))
G_S1 = add(M.Grado(colegio_id=COL.id, nombre='1ro Secundaria', nivel='secundaria', orden=1))
DIR = add(M.Usuario(colegio_id=COL.id, username='dir', password_hash='x', nombre='Dir', apellido='T',
                    role='direccion', activo=True, must_change_password=False, token_version=0))


def curso(g, t, sec):
    return add(M.Curso(colegio_id=COL.id, nombre=sec, grado_id=g.id, tanda_id=t.id if t else None,
                       ano_escolar_id=ANO.id, activo=True))


CURSOS = [curso(G_S2, T_V, 'A'), curso(G_S1, T_V, 'B'), curso(G_S1, T_V, 'A'), curso(G_P1, T_V, 'A'),
          curso(G_S2, T_M, 'A'), curso(G_P1, T_M, 'B'), curso(G_P1, T_M, 'A'), curso(G_S1, None, 'A')]
VACIO = curso(G_S1, T_M, 'C')       # sin matrícula: no aparece, como antes
HOY = date.today()
for i, c in enumerate(CURSOS):
    ests = [add(M.Estudiante(colegio_id=COL.id, nombre='E%d_%d' % (i, k), apellido='T', curso_id=c.id, activo=True))
            for k in range(3)]
    if i % 3 == 2:
        continue                    # este curso no pasó lista hoy: "Sin registrar"
    for k, e in enumerate(ests):
        add(M.Asistencia(colegio_id=COL.id, estudiante_id=e.id, curso_id=c.id, fecha=HOY,
                         estado=('presente', 'ausente', 'tardanza')[(i + k) % 3], registrado_por=DIR.id))
db.commit()

ESCRITURAS = []


@event.listens_for(engine, 'before_cursor_execute')
def _detector(conn, cursor, statement, params, context, executemany):
    if statement.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')):
        ESCRITURAS.append(statement.split()[0:3])


def graficos(nivel=None):
    hd = {'Authorization': 'Bearer ' + create_token(DIR)}
    if nivel:
        hd['X-Nivel'] = nivel
    return client.get('/api/dashboard/graficos', headers=hd).json()


g = graficos()
gp = graficos('primaria')
if os.environ.get('SNAP'):
    json.dump({'todos': g.get('asistencia_hoy_por_curso'), 'primaria': gp.get('asistencia_hoy_por_curso'),
               'asistencia_hoy': g.get('asistencia_hoy'), 'asistencia_resumen': g.get('asistencia_resumen')},
              open(os.environ['SNAP'], 'w', encoding='utf-8'), ensure_ascii=False, indent=1, sort_keys=True)

filas = g.get('asistencia_hoy_por_curso') or []
por_id = {f['curso_id']: f for f in filas}
print("\n=== DATOS ===")
check('A-01 aparecen exactamente los cursos con matrícula (el vacío no)',
      set(por_id) == {c.id for c in CURSOS} and VACIO.id not in por_id, sorted(por_id))
check('A-02 cada fila trae tanda y grado estructurados',
      all({'tanda_id', 'tanda', 'tanda_hora_inicio', 'grado_nivel', 'grado_orden', 'seccion'} <= set(f) for f in filas),
      filas[:1])
check('A-03 los datos estructurados coinciden con el curso',
      all(por_id[c.id]['tanda_id'] == c.tanda_id and por_id[c.id]['seccion'] == c.nombre
          and por_id[c.id]['grado_orden'] == db.get(M.Grado, c.grado_id).orden for c in CURSOS), '')
check('A-04 curso sin tanda: tanda vacía (el panel lo muestra aparte, al final)',
      por_id[CURSOS[-1].id]['tanda_id'] is None and por_id[CURSOS[-1].id]['tanda'] is None, por_id[CURSOS[-1].id])
check('A-05 "Sin registrar" se conserva', [f['registrado'] for f in filas].count(False) == 2
      and all(f['porcentaje'] == 0 for f in filas if not f['registrado']), '')
check('A-06 el lente de división sigue aplicando (X-Nivel primaria)',
      {f['curso_id'] for f in gp['asistencia_hoy_por_curso']}
      == {c.id for c in CURSOS if c.grado_id == G_P1.id}, gp.get('asistencia_hoy_por_curso'))
check('A-07 consultar el dashboard no escribe nada', not ESCRITURAS, ESCRITURAS)
db.close()

ok = sum(1 for _, r in RES if r)
print('\nRESULTADO ASIS-TANDA-1: %d PASARON / %d FALLARON' % (ok, len(RES) - ok))
sys.exit(0 if ok == len(RES) else 1)
