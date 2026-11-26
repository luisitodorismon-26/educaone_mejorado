"""Siembra la base SINTÉTICA de la prueba (REG-43). Corre DENTRO de un contenedor
sin límite, con el código de una versión montado en /app.

Solo acepta el PostgreSQL de la prueba (host `pg`, base `eo_test_*`, vacía).
Escribe /out/semilla.json con los ids de los cursos y del director sintético.
"""
import json, os, sys
sys.path.insert(0, '/app'); sys.path.insert(0, '/app/tools')
os.chdir('/tmp')
import logging; logging.disable(logging.WARNING)
from sqlalchemy import text
from database import engine, SessionLocal
assert engine.url.host == 'pg' and str(engine.url.database).startswith('eo_test'), engine.url
with engine.connect() as cn:
    tablas = cn.execute(text("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")).scalar()
if tablas:
    raise SystemExit('La base de prueba no está vacía; no se siembra.')
from fastapi.testclient import TestClient
import app as APP, models as M
import registro_43_semilla as S
with TestClient(APP.app):
    pass
db = SessionLocal()
sem = S.sembrar(db, M, [(1, 'A', 40), (1, 'B', 43), (1, 'C', 44), (4, 'D', 40), (5, 'E', 40), (6, 'F', 40)])
db.commit()
salida = {'director_id': sem['director'].id, 'cursos': {k: v.id for k, v in sem['cursos'].items()}}
json.dump(salida, open('/out/semilla.json', 'w'))
print(salida)
