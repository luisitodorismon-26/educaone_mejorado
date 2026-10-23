# -*- coding: utf-8 -*-
"""
EducaOne — REP-DUP-1: idempotencia de POST /api/reportes.

El formulario envía un `client_request_id` por envío y lo conserva al
reintentar. La base de datos (índice único parcial colegio + autor + clave)
admite UN reporte por clave, también con peticiones simultáneas; el reintento
devuelve el reporte ya creado y no vuelve a notificar. Sin clave, o con otra
clave, un reporte con el mismo texto es un incidente nuevo y se crea.

Incluye:
  - la MIGRACIÓN sobre una base con el esquema anterior (sin las columnas ni el
    índice) y reportes existentes, que deben quedar intactos;
  - una carrera REAL: 8 peticiones HTTP simultáneas contra un uvicorn local.

Base temporal aislada. Nunca producción.

Uso:
    cd backend
    python tools/test_reportes_idempotencia.py                 # SQLite temporal
    EO_TEST_PG_URL=postgresql://eo_test@127.0.0.1:55432/eo_test_repdup \\
        python tools/test_reportes_idempotencia.py             # PostgreSQL LOCAL y vacío

Con EO_TEST_PG_URL solo se acepta un PostgreSQL en localhost cuya base empiece
por `eo_test` (vacía; la suite crea y altera tablas).
"""
import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(BK, "tools"))

from test_utils import aislar_base_de_datos  # noqa: E402

PG_URL = os.environ.get('EO_TEST_PG_URL')
if PG_URL:
    from urllib.parse import urlparse
    _u = urlparse(PG_URL)
    if _u.hostname not in ('127.0.0.1', 'localhost') or not _u.path.lstrip('/').startswith('eo_test'):
        raise SystemExit('EO_TEST_PG_URL debe ser un PostgreSQL LOCAL con base eo_test*: %s' % _u.hostname)
    os.environ['DATABASE_URL'] = PG_URL
    TMP = None
else:
    TMP = aislar_base_de_datos('rep_dup1')

from database import engine, SessionLocal  # noqa: E402
from test_utils import verificar_engine_aislado  # noqa: E402

if PG_URL:
    assert engine.dialect.name == 'postgresql' and engine.url.host in ('127.0.0.1', 'localhost') \
        and str(engine.url.database).startswith('eo_test'), engine.url
    print('Motor: PostgreSQL local aislado (%s:%s/%s)' % (engine.url.host, engine.url.port, engine.url.database))
else:
    verificar_engine_aislado(engine, TMP)
    print('Motor: SQLite temporal')

from sqlalchemy import inspect, text  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import models as M  # noqa: E402
import app as APP  # noqa: E402
from auth import create_token  # noqa: E402

RES = []


def check(nombre, ok, detalle=''):
    RES.append((nombre, bool(ok)))
    print(('  OK  ' if ok else '  FALLA ') + nombre + ('' if ok else '  -> ' + str(detalle)[:300]))


# ── Esquema ANTERIOR: tablas actuales, pero reportes_conducta sin las columnas nuevas ni el índice ──
M.Base.metadata.create_all(bind=engine)
with engine.begin() as conn:
    conn.execute(text('DROP INDEX IF EXISTS uq_reporte_autor_client_request'))
    conn.execute(text('ALTER TABLE reportes_conducta DROP COLUMN client_request_id'))
    conn.execute(text('ALTER TABLE reportes_conducta DROP COLUMN client_request_hash'))

db = SessionLocal()


def add(o):
    db.add(o)
    db.flush()
    return o


def usuario(col, username, role):
    return add(M.Usuario(colegio_id=col.id, username=username, password_hash='x', nombre=username, apellido='T',
                         role=role, activo=True, must_change_password=False, token_version=0))


COL, OTRO = (add(M.Colegio(nombre=n, codigo=n.lower(), activo=True)) for n in ('C1', 'C2'))
for c in (COL, OTRO):
    ano = add(M.AnoEscolar(colegio_id=c.id, nombre='2026-2027', activo=True))
    g = add(M.Grado(colegio_id=c.id, nombre='1ro Secundaria', nivel='secundaria', orden=1))
    cur = add(M.Curso(colegio_id=c.id, nombre='A', grado_id=g.id, ano_escolar_id=ano.id, activo=True))
    add(M.Estudiante(colegio_id=c.id, nombre='Est', apellido=c.nombre, curso_id=cur.id, activo=True, no_lista=1))
# Usuarios 'superadmin' y 'direccion' presentes: el arranque (init_db) no crea cuentas de
# arranque ni escribe credenciales iniciales.
add(M.Usuario(colegio_id=None, username='superadmin', password_hash='x', nombre='S', apellido='A',
              role='superadmin', activo=True, must_change_password=False, token_version=0))
DIR = usuario(COL, 'direccion', 'direccion')
DIR2 = usuario(COL, 'dir2', 'direccion')
COORD = usuario(COL, 'coord', 'coordinador')
DIR_O = usuario(OTRO, 'dir_o', 'direccion')
EST = db.query(M.Estudiante).filter_by(colegio_id=COL.id).one()
EST_O = db.query(M.Estudiante).filter_by(colegio_id=OTRO.id).one()
db.commit()
# Reportes EXISTENTES (esquema viejo): dos con el mismo texto, como pasó en producción.
with engine.begin() as conn:
    for n in (1, 2):
        conn.execute(text(
            "INSERT INTO reportes_conducta (colegio_id, estudiante_id, reportado_por, tipo, gravedad, titulo, "
            "descripcion, estado, numero_reporte) VALUES (:c, :e, :u, 'conducta', 'leve', 'Legacy igual', "
            "'mismo texto', 'pendiente', :num)"), {'c': COL.id, 'e': EST.id, 'u': DIR.id, 'num': '2026-000%d' % n})
LEGACY = [tuple(r) for r in engine.connect().execute(text(
    'SELECT id, titulo, descripcion, estado, numero_reporte FROM reportes_conducta ORDER BY id'))]

print("\n=== MIGRACIÓN (arranque de la app sobre el esquema anterior) ===")
client_ctx = TestClient(APP.app)
client = client_ctx.__enter__()          # ejecuta el lifespan: migraciones + verificación
insp = inspect(engine)
cols = {c['name'] for c in insp.get_columns('reportes_conducta')}
idx = {i['name']: i for i in insp.get_indexes('reportes_conducta')}
check('G-01 la migración agrega client_request_id y client_request_hash', {'client_request_id', 'client_request_hash'} <= cols, cols)
check('G-02 crea el índice único uq_reporte_autor_client_request',
      'uq_reporte_autor_client_request' in idx and idx['uq_reporte_autor_client_request'].get('unique'), idx.keys())
with engine.connect() as conn:
    despues = [tuple(r) for r in conn.execute(text(
        'SELECT id, titulo, descripcion, estado, numero_reporte FROM reportes_conducta ORDER BY id'))]
    claves_legacy = conn.execute(text('SELECT COUNT(*) FROM reportes_conducta WHERE client_request_id IS NULL')).scalar()
check('G-03 los reportes existentes quedan intactos (incluidos los de texto repetido) y con clave NULL',
      despues == LEGACY and claves_legacy == 2, (LEGACY, despues))


def h(u):
    return {'Authorization': 'Bearer ' + create_token(u)}


def cuerpo(titulo='Incidente en el aula', descripcion='Detalle', clave=None, est=None):
    b = {'estudiante_id': (est or EST).id, 'titulo': titulo, 'descripcion': descripcion,
         'tipo': 'conducta', 'gravedad': 'leve'}
    if clave is not None:
        b['client_request_id'] = clave
    return b


def n_reportes():
    db.expire_all()
    return db.query(M.ReporteConducta).count()


def avisos_de(rep_id):
    db.expire_all()
    return sorted(n.usuario_id for n in db.query(M.Notificacion).filter_by(evento_key='reporte:%d:creado' % rep_id))


print("\n=== SIN CLAVE / CLAVE NUEVA: comportamiento normal ===")
r1, r2 = (client.post('/api/reportes', json=cuerpo('Mismo texto'), headers=h(DIR)) for _ in range(2))
check('I-01 sin clave: dos envíos con el mismo texto son dos reportes (incidentes distintos)',
      r1.status_code == r2.status_code == 201 and r1.json()['id'] != r2.json()['id'], (r1.text, r2.text))
K1 = str(uuid.uuid4())
r = client.post('/api/reportes', json=cuerpo(clave=K1), headers=h(DIR))
ID1 = r.json().get('id')
check('I-02 con clave nueva: 201 y un reporte', r.status_code == 201 and ID1, r.text)
AV1 = avisos_de(ID1)
check('I-03 notifica una vez a los destinatarios de siempre', AV1 == sorted([DIR2.id, COORD.id]), AV1)

print("\n=== REINTENTO TRAS RESPUESTA PERDIDA ===")
antes = n_reportes()
rr = client.post('/api/reportes', json=cuerpo(clave=K1), headers=h(DIR))
check('I-04 reintento con la misma clave y contenido: 200, mismo id y número, marcado como reintento',
      rr.status_code == 200 and rr.json().get('id') == ID1 and rr.json().get('reintento') is True
      and rr.json().get('numero_reporte') == r.json().get('numero_reporte'), rr.text)
check('I-05 ...no crea otro reporte ni repite notificaciones', n_reportes() == antes and avisos_de(ID1) == AV1, '')
db.expire_all()
_n_notif = db.query(M.Notificacion).count()
rx = client.post('/api/reportes', json=cuerpo(descripcion='OTRO contenido', clave=K1), headers=h(DIR))
db.expire_all()
check('I-06 misma clave con otro contenido: 409, nada creado ni notificado',
      rx.status_code == 409 and n_reportes() == antes and db.query(M.Notificacion).count() == _n_notif, rx.text)
r4 = client.post('/api/reportes', json=cuerpo(clave=str(uuid.uuid4())), headers=h(DIR))
check('I-07 mismo texto con OTRA clave (reporte nuevo intencional): se crea',
      r4.status_code == 201 and r4.json()['id'] != ID1, r4.text)
r5 = client.post('/api/reportes', json=cuerpo(clave=K1), headers=h(DIR2))
check('I-08 la clave está limitada al autor: otro autor con la misma clave crea su propio reporte',
      r5.status_code == 201 and r5.json()['id'] != ID1, r5.text)
r6 = client.post('/api/reportes', json=cuerpo(clave=K1, est=EST_O), headers=h(DIR_O))
check('I-09 ...y al colegio: otro colegio con la misma clave es independiente', r6.status_code == 201, r6.text)
antes = n_reportes()
check('I-10 clave con formato inválido: 400 y nada creado',
      client.post('/api/reportes', json=cuerpo(clave='x y'), headers=h(DIR)).status_code == 400
      and client.post('/api/reportes', json=cuerpo(clave='a' * 65), headers=h(DIR)).status_code == 400
      and n_reportes() == antes, '')

print("\n=== CARRERA DETERMINISTA (ambas pasan la consulta previa) ===")
K2 = str(uuid.uuid4())
_orig = APP._generar_numero_reporte


def _gana_otra_peticion(db_, colegio_id):
    # Entre la consulta previa y el commit, OTRA petición con la misma clave
    # termina primero (sesión aparte). Solo el índice único puede detectarlo.
    s2 = SessionLocal()
    try:
        b = cuerpo(clave=K2)
        s2.add(M.ReporteConducta(colegio_id=colegio_id, estudiante_id=EST.id, reportado_por=DIR.id,
                                 titulo=b['titulo'], descripcion=b['descripcion'], tipo='conducta', gravedad='leve',
                                 estado='pendiente', numero_reporte='GANADOR', client_request_id=K2,
                                 client_request_hash=APP._huella_reporte(EST.id, b['titulo'], b['descripcion'],
                                                                         'conducta', 'leve')))
        s2.commit()
    finally:
        s2.close()
    return _orig(db_, colegio_id)


APP._generar_numero_reporte = _gana_otra_peticion
try:
    rc = client.post('/api/reportes', json=cuerpo(clave=K2), headers=h(DIR))
finally:
    APP._generar_numero_reporte = _orig
db.expire_all()
filas_k2 = db.query(M.ReporteConducta).filter_by(client_request_id=K2).all()
check('C-01 el índice único detecta la carrera: 200 con el reporte ganador, sin crear otro',
      rc.status_code == 200 and rc.json().get('numero_reporte') == 'GANADOR' and len(filas_k2) == 1, rc.text)
check('C-02 ...y la petición perdedora no notifica', avisos_de(filas_k2[0].id) == [], avisos_de(filas_k2[0].id))

print("\n=== CARRERA REAL: 8 peticiones HTTP simultáneas (uvicorn local) ===")
import uvicorn  # noqa: E402

sock = socket.socket()
sock.bind(('127.0.0.1', 0))
PORT = sock.getsockname()[1]
sock.close()
server = uvicorn.Server(uvicorn.Config(APP.app, host='127.0.0.1', port=PORT, lifespan='off', log_level='warning'))
threading.Thread(target=server.run, daemon=True).start()
for _ in range(100):
    if server.started:
        break
    time.sleep(0.05)

# Ensancha la ventana entre la consulta previa y el commit para que TODAS las
# peticiones pasen la consulta antes de que la primera guarde.
APP._generar_numero_reporte = lambda db_, cid: (time.sleep(0.4), _orig(db_, cid))[1]
K3 = str(uuid.uuid4())
barrera = threading.Barrier(8, timeout=30)
resultados = []
# Token y cuerpo se calculan UNA vez, fuera de los hilos: la sesión de la
# prueba no es segura entre hilos.
CABECERAS = dict(h(DIR), **{'Content-Type': 'application/json'})
DATOS = json.dumps(cuerpo(titulo='Carrera real', clave=K3)).encode('utf-8')


def enviar():
    req = urllib.request.Request('http://127.0.0.1:%d/api/reportes' % PORT, method='POST',
                                 data=DATOS, headers=CABECERAS)
    barrera.wait()
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            resultados.append((resp.status, json.load(resp)))
    except urllib.error.HTTPError as e:
        resultados.append((e.code, json.load(e)))


hilos = [threading.Thread(target=enviar) for _ in range(8)]
for t in hilos:
    t.start()
for t in hilos:
    t.join(timeout=90)
APP._generar_numero_reporte = _orig
server.should_exit = True
db.expire_all()
filas_k3 = db.query(M.ReporteConducta).filter_by(client_request_id=K3).all()
estados = sorted(s for s, _ in resultados)
ids = {j.get('id') for _, j in resultados}
check('R-01 8 peticiones simultáneas con la misma clave: un solo reporte', len(filas_k3) == 1, len(filas_k3))
check('R-02 todas responden éxito con el MISMO reporte (1 × 201, 7 × 200)',
      estados == [200] * 7 + [201] and ids == {filas_k3[0].id}, (estados, ids))
check('R-03 un solo conjunto de notificaciones', avisos_de(filas_k3[0].id) == sorted([DIR2.id, COORD.id]),
      avisos_de(filas_k3[0].id))

with engine.connect() as conn:
    final = [tuple(r) for r in conn.execute(text(
        'SELECT id, titulo, descripcion, estado, numero_reporte FROM reportes_conducta WHERE id IN (%s) ORDER BY id'
        % ','.join(str(x[0]) for x in LEGACY)))]
check('G-04 al final, los reportes existentes siguen intactos', final == LEGACY, final)
client_ctx.__exit__(None, None, None)
db.close()

ok = sum(1 for _, r in RES if r)
print('\nRESULTADO REP-DUP-1: %d PASARON / %d FALLARON' % (ok, len(RES) - ok))
sys.exit(0 if ok == len(RES) else 1)
