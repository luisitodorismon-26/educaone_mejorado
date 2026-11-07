# -*- coding: utf-8 -*-
"""TRAS-1 · Cómo aparecen las dos tablas nuevas al desplegar, y que no tocan nada.

Simula una base EXISTENTE (todas las tablas de antes, con datos, SIN
`movimientos_estudiante` ni `reservas_numero_lista`) y arranca la aplicación
como en un despliegue (el `lifespan` de app.py, que ejecuta
`Base.metadata.create_all` bajo el bloqueo de migración). Comprueba:

  * se crean las dos tablas con sus restricciones únicas e índices;
  * ninguna fila existente cambia (estudiantes, cursos, asistencias, notas);
  * un segundo arranque no hace nada (idempotente).

SQLite temporal aislada, o PostgreSQL temporal propio con EO_PG_TEST_SERVER
(tools/pg_base_temporal.py). Nunca sge.db ni una base indicada por variable.
"""
import datetime as dt
import hashlib
import json
import os
import sys

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(BK, 'tools'))
from test_utils import aislar_base_de_datos, verificar_engine_aislado  # noqa: E402

if os.environ.get('EO_TEST_PG_URL'):
    raise SystemExit('EO_TEST_PG_URL no se acepta: use EO_PG_TEST_SERVER.')
PG_SERVER = os.environ.get('EO_PG_TEST_SERVER')
if PG_SERVER:
    import pg_base_temporal as PGT
    PG = PGT.BaseTemporal(PG_SERVER, prefijo='eo_tmp_trasmig_')
    os.environ['DATABASE_URL'] = PG.crear()
    TMP = None
else:
    PG = None
    TMP = aislar_base_de_datos('retiros_traslados_mig')

from database import engine, SessionLocal  # noqa: E402
if PG:
    assert engine.dialect.name == 'postgresql' and engine.url.database == PG.nombre, engine.url
    PG.engines.append(engine)
else:
    verificar_engine_aislado(engine, TMP)
print('Motor:', engine.dialect.name)

from sqlalchemy import inspect, text  # noqa: E402
import models as M  # noqa: E402

NUEVAS = ('movimientos_estudiante', 'reservas_numero_lista')
RES = []


def check(nombre, ok, detalle=''):
    RES.append((nombre, bool(ok)))
    print(('  PASA  ' if ok else '  FALLA ') + nombre + ('' if ok else '  -> ' + str(detalle)[:400]))


# 1. La base «de antes»: todas las tablas menos las dos nuevas.
viejas = [t for t in M.Base.metadata.sorted_tables if t.name not in NUEVAS]
M.Base.metadata.create_all(bind=engine, tables=viejas)
check('M0 base de partida sin las tablas nuevas',
      not (set(NUEVAS) & set(inspect(engine).get_table_names())), inspect(engine).get_table_names())

db = SessionLocal()


def add(o):
    db.add(o)
    db.flush()
    return o


col = add(M.Colegio(nombre='Colegio Migración', codigo='SMIG', activo=True))
ano = add(M.AnoEscolar(colegio_id=col.id, nombre='2026-2027', activo=True, fecha_inicio=dt.date(2026, 9, 1),
                       fecha_fin=dt.date(2027, 6, 30)))
g = add(M.Grado(colegio_id=col.id, nombre='5to Secundaria', nivel='secundaria', orden=5, activo=True))
cur = add(M.Curso(colegio_id=col.id, nombre='A', grado_id=g.id, ano_escolar_id=ano.id, activo=True))
asig = add(M.Asignatura(colegio_id=col.id, nombre='Educación Artística', codigo='EA'))
prof = add(M.Usuario(colegio_id=col.id, username='p_mig', password_hash='x', nombre='P', apellido='M',
                     role='profesor', activo=True, must_change_password=False, token_version=0))
for n in range(1, 6):
    e = add(M.Estudiante(colegio_id=col.id, nombre='E%d' % n, apellido='Mig', curso_id=cur.id, no_lista=n,
                         activo=(n != 5), condicion='activo' if n != 5 else 'retirado',
                         fecha_retiro=None if n != 5 else dt.date(2026, 10, 1)))
    add(M.CalificacionSecundaria(colegio_id=col.id, estudiante_id=e.id, asignatura_id=asig.id,
                                 ano_escolar_id=ano.id, competencia_numero=1, p1=60 + n, rp1=75 if n == 1 else None))
    for d in (dt.date(2026, 9, 7), dt.date(2026, 9, 9)):
        add(M.Asistencia(colegio_id=col.id, estudiante_id=e.id, curso_id=cur.id, asignatura_id=asig.id,
                         fecha=d, estado='presente', registrado_por=prof.id))
db.commit()
db.close()

TABLAS_DATOS = ('colegios', 'ano_escolar', 'cursos', 'estudiantes', 'calificaciones_secundaria', 'asistencias')


def huella():
    out = {}
    with engine.connect() as cn:
        for t in TABLAS_DATOS:
            filas = [tuple(str(v) for v in r) for r in cn.execute(text('SELECT * FROM %s ORDER BY id' % t))]
            out[t] = (len(filas), hashlib.sha256(json.dumps(filas).encode()).hexdigest()[:16])
    return out


ANTES = huella()

# 2. Despliegue: el arranque de la aplicación (lifespan) como en Render.
import app as APP  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
with TestClient(APP.app):
    pass
insp = inspect(engine)
check('M1 el arranque crea las dos tablas nuevas', set(NUEVAS) <= set(insp.get_table_names()))
uniq_m = {tuple(u['column_names']) for u in insp.get_unique_constraints('movimientos_estudiante')}
uniq_r = {tuple(u['column_names']) for u in insp.get_unique_constraints('reservas_numero_lista')}
check('M2 movimientos: únicos (colegio, client_request_id) y (estudiante, año, secuencia)',
      ('colegio_id', 'client_request_id') in uniq_m and ('estudiante_id', 'ano_escolar_id', 'secuencia') in uniq_m, uniq_m)
check('M3 reservas: únicos (curso, número) y (curso, estudiante)',
      ('curso_id', 'no_lista') in uniq_r and ('curso_id', 'estudiante_id') in uniq_r, uniq_r)
with engine.connect() as cn:
    vacias = [cn.execute(text('SELECT count(*) FROM %s' % t)).scalar() for t in NUEVAS]
check('M4 las tablas nuevas nacen VACÍAS (no se rellena ningún historial)', vacias == [0, 0], vacias)
DESPUES = huella()
check('M5 ninguna fila existente cambió (colegios, años, cursos, estudiantes, notas con RP, asistencias)',
      DESPUES == ANTES, (ANTES, DESPUES))
with TestClient(APP.app):
    pass
check('M6 un segundo arranque no cambia nada (idempotente)', huella() == ANTES
      and set(NUEVAS) <= set(inspect(engine).get_table_names()))

ok = sum(1 for _, c in RES if c)
print('\nRESULTADO MIGRACION TRAS-1 (%s): %d PASARON / %d FALLARON' % (engine.dialect.name, ok, len(RES) - ok))
sys.exit(0 if ok == len(RES) else 1)
