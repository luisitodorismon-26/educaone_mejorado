# -*- coding: utf-8 -*-
"""
EducaOne — REP-DUP-1: idempotencia con DOS PROCESOS de servidor contra el
mismo PostgreSQL.

Arranca dos uvicorn independientes (procesos distintos, cada uno con su propio
pool de conexiones) sobre la misma base PostgreSQL LOCAL y aislada. Ambos
procesos llevan un punto de encuentro de PRUEBA justo después de la consulta
previa por clave (envuelve `_generar_numero_reporte`, que se llama solo si esa
consulta no encontró nada): ninguno inserta hasta que los dos la superaron.
Así la única barrera que queda es el índice único de la base de datos.

Debe quedar: un reporte, ambas respuestas con el mismo id (201 + 200) y un
solo conjunto de notificaciones. Control: con claves distintas, dos reportes.

Solo PostgreSQL local (EO_TEST_PG_URL, host localhost, base eo_test*, vacía).
Nunca producción.

Uso:
    cd backend
    EO_TEST_PG_URL=postgresql://eo_test@127.0.0.1:55432/eo_test_multi \\
        python tools/test_reportes_idempotencia_multiproceso.py
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)

PG_URL = os.environ.get('EO_TEST_PG_URL')
if not PG_URL:
    raise SystemExit('Requiere EO_TEST_PG_URL (PostgreSQL local y vacío). Sin ella no se ejecuta.')
_u = urllib.parse.urlparse(PG_URL)
if _u.hostname not in ('127.0.0.1', 'localhost') or not _u.path.lstrip('/').startswith('eo_test'):
    raise SystemExit('EO_TEST_PG_URL debe ser un PostgreSQL LOCAL con base eo_test*')
os.environ['DATABASE_URL'] = PG_URL


# ─────────────── modo SERVIDOR (proceso hijo) ───────────────
def servidor(puerto, dir_encuentro):
    import app as APP
    import uvicorn
    from database import engine
    assert engine.dialect.name == 'postgresql' and engine.url.host in ('127.0.0.1', 'localhost')
    _orig = APP._generar_numero_reporte

    def _encuentro_tras_consulta_previa(db, colegio_id):
        # Solo se llega aquí si la consulta previa por clave NO encontró nada.
        open(os.path.join(dir_encuentro, 'paso_consulta_%d' % os.getpid()), 'w').close()
        limite = time.time() + 20
        while len(os.listdir(dir_encuentro)) < 2 and time.time() < limite:
            time.sleep(0.02)
        return _orig(db, colegio_id)

    APP._generar_numero_reporte = _encuentro_tras_consulta_previa
    uvicorn.run(APP.app, host='127.0.0.1', port=puerto, lifespan='off', log_level='warning')


if len(sys.argv) >= 4 and sys.argv[1] == '--servidor':
    servidor(int(sys.argv[2]), sys.argv[3])
    sys.exit(0)

# ─────────────── modo PRUEBA (proceso principal) ───────────────
from database import engine, SessionLocal  # noqa: E402
from sqlalchemy import inspect  # noqa: E402

import models as M  # noqa: E402
from auth import create_token  # noqa: E402

assert engine.dialect.name == 'postgresql' and engine.url.host in ('127.0.0.1', 'localhost') \
    and str(engine.url.database).startswith('eo_test'), engine.url
print('Motor: PostgreSQL local aislado (%s:%s/%s)' % (engine.url.host, engine.url.port, engine.url.database))
RES = []


def check(nombre, ok, detalle=''):
    RES.append((nombre, bool(ok)))
    print(('  OK  ' if ok else '  FALLA ') + nombre + ('' if ok else '  -> ' + str(detalle)[:300]))


M.Base.metadata.create_all(bind=engine)
check('P-00 el índice único existe en PostgreSQL',
      'uq_reporte_autor_client_request' in {i['name'] for i in inspect(engine).get_indexes('reportes_conducta')}, '')
db = SessionLocal()


def add(o):
    db.add(o)
    db.flush()
    return o


add(M.Usuario(colegio_id=None, username='superadmin', password_hash='x', nombre='S', apellido='A',
              role='superadmin', activo=True, must_change_password=False, token_version=0))
COL = add(M.Colegio(nombre='C1', codigo='c1', activo=True))
ano = add(M.AnoEscolar(colegio_id=COL.id, nombre='2026-2027', activo=True))
g = add(M.Grado(colegio_id=COL.id, nombre='1ro Secundaria', nivel='secundaria', orden=1))
cur = add(M.Curso(colegio_id=COL.id, nombre='A', grado_id=g.id, ano_escolar_id=ano.id, activo=True))
EST = add(M.Estudiante(colegio_id=COL.id, nombre='Est', apellido='Sint', curso_id=cur.id, activo=True, no_lista=1))


def usuario(username, role):
    return add(M.Usuario(colegio_id=COL.id, username=username, password_hash='x', nombre=username, apellido='T',
                         role=role, activo=True, must_change_password=False, token_version=0))


DIR, DIR2, COORD = usuario('direccion', 'direccion'), usuario('dir2', 'direccion'), usuario('coord', 'coordinador')
db.commit()
EST_ID, DIR_ID, ESPERADOS = EST.id, DIR.id, sorted([DIR2.id, COORD.id])
CABECERAS = {'Authorization': 'Bearer ' + create_token(DIR), 'Content-Type': 'application/json'}


def puerto_libre():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def levantar_servidores(dir_encuentro):
    procesos, puertos = [], []
    for i in range(2):
        p = puerto_libre()
        log = open(os.path.join(tempfile.gettempdir(), 'repdup_srv_%d_%d.log' % (p, i)), 'w')
        procesos.append(subprocess.Popen([sys.executable, os.path.abspath(__file__), '--servidor', str(p), dir_encuentro],
                                         cwd=BK, env=dict(os.environ), stdout=log, stderr=subprocess.STDOUT))
        puertos.append(p)
    for p in puertos:
        limite = time.time() + 90
        while time.time() < limite:
            try:
                socket.create_connection(('127.0.0.1', p), timeout=1).close()
                break
            except OSError:
                time.sleep(0.3)
        else:
            raise SystemExit('el servidor del puerto %d no arrancó' % p)
    return procesos, puertos


def enviar_a_la_vez(puertos, claves):
    resultados = [None, None]
    barrera = threading.Barrier(2, timeout=30)

    def uno(i):
        body = json.dumps({'estudiante_id': EST_ID, 'titulo': 'Dos procesos', 'descripcion': 'Mismo envío',
                           'tipo': 'conducta', 'gravedad': 'leve', 'client_request_id': claves[i]}).encode('utf-8')
        req = urllib.request.Request('http://127.0.0.1:%d/api/reportes' % puertos[i], data=body,
                                     method='POST', headers=CABECERAS)
        barrera.wait()
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                resultados[i] = (r.status, json.load(r))
        except urllib.error.HTTPError as e:
            resultados[i] = (e.code, json.load(e))

    hilos = [threading.Thread(target=uno, args=(i,)) for i in range(2)]
    for t in hilos:
        t.start()
    for t in hilos:
        t.join(timeout=90)
    return resultados


def avisos(rep_id):
    db.expire_all()
    return sorted(n.usuario_id for n in db.query(M.Notificacion).filter_by(evento_key='reporte:%d:creado' % rep_id))


for caso, claves in (('MISMA clave', [str(uuid.uuid4())] * 2), ('claves DISTINTAS (control)', [str(uuid.uuid4()), str(uuid.uuid4())])):
    print('\n=== Dos procesos de servidor, %s ===' % caso)
    dir_encuentro = tempfile.mkdtemp(prefix='repdup_encuentro_')
    procesos, puertos = levantar_servidores(dir_encuentro)
    try:
        res = enviar_a_la_vez(puertos, claves)
    finally:
        for pr in procesos:
            pr.terminate()
        for pr in procesos:
            try:
                pr.wait(timeout=20)
            except subprocess.TimeoutExpired:
                pr.kill()
    pasaron = len(os.listdir(dir_encuentro))
    db.expire_all()
    filas = db.query(M.ReporteConducta).filter(M.ReporteConducta.client_request_id.in_(set(claves))).all()
    estados = sorted(r[0] for r in res if r)
    ids_resp = [r[1].get('id') for r in res if r]
    if claves[0] == claves[1]:
        check('P-01 ambos procesos superaron la consulta previa antes de insertar', pasaron == 2, pasaron)
        check('P-02 un solo reporte', len(filas) == 1, len(filas))
        check('P-03 respuestas 201 + 200 con el MISMO id', estados == [200, 201] and len(set(ids_resp)) == 1
              and filas and ids_resp[0] == filas[0].id, (res, [f.id for f in filas]))
        check('P-04 un solo conjunto de notificaciones', filas and avisos(filas[0].id) == ESPERADOS,
              filas and avisos(filas[0].id))
    else:
        check('P-05 control: con claves distintas ambos procesos crean su reporte (dos)',
              pasaron == 2 and len(filas) == 2 and estados == [201, 201], (pasaron, len(filas), estados))
        check('P-06 ...cada uno con su propio conjunto de notificaciones',
              all(avisos(f.id) == ESPERADOS for f in filas), [avisos(f.id) for f in filas])
db.close()

ok = sum(1 for _, r in RES if r)
print('\nRESULTADO REP-DUP-1 multiproceso: %d PASARON / %d FALLARON' % (ok, len(RES) - ok))
sys.exit(0 if ok == len(RES) else 1)
