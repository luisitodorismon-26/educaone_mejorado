# -*- coding: utf-8 -*-
"""
EducaOne — COM-DUP-1: idempotencia con DOS PROCESOS de servidor contra el
mismo PostgreSQL.

Arranca dos uvicorn independientes (procesos distintos, cada uno con su propio
pool de conexiones) sobre la misma base PostgreSQL de PRUEBA. Ambos llevan un
punto de encuentro justo después de la consulta previa por clave (envuelve
`_nuevo_comunicado`, que solo se llama si esa consulta no encontró nada):
ninguno inserta hasta que los dos la superaron. La única barrera que queda es el
índice único de la base de datos.

Debe quedar: un comunicado, ambas respuestas con el mismo id (201 + 200), un
solo juego de notificaciones y una sola auditoría. Control: con claves
distintas, dos comunicados.

Solo el clúster PostgreSQL de prueba: EO_TEST_PG_URL (localhost, base eo_test*,
vacía) y EO_TEST_PG_DATADIR (su directorio de datos). Nunca producción.

Uso:
    cd <carpeta temporal>
    EO_TEST_PG_URL=postgresql://eo_test@127.0.0.1:<puerto>/eo_test_comdup_multi \\
    EO_TEST_PG_DATADIR=<directorio del clúster de prueba> \\
        python <repo>/backend/tools/test_comunicados_idempotencia_multiproceso.py
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
DATADIR = os.environ.get('EO_TEST_PG_DATADIR')
if not PG_URL or not DATADIR:
    raise SystemExit('Requiere EO_TEST_PG_URL y EO_TEST_PG_DATADIR (clúster PostgreSQL de prueba). Sin ellas no se ejecuta.')
_u = urllib.parse.urlparse(PG_URL)
if _u.hostname not in ('127.0.0.1', 'localhost') or not _u.path.lstrip('/').startswith('eo_test'):
    raise SystemExit('EO_TEST_PG_URL debe ser un PostgreSQL LOCAL con base eo_test*')
os.environ['DATABASE_URL'] = PG_URL


def exigir_cluster_de_prueba(engine, exigir_vacia):
    from sqlalchemy import text
    esperado = os.path.normcase(os.path.realpath(DATADIR))
    with engine.connect() as cn:
        real = os.path.normcase(os.path.realpath(cn.execute(text('SHOW data_directory')).scalar()))
        tablas = cn.execute(text("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")).scalar()
    if real != esperado:
        raise SystemExit('El PostgreSQL conectado NO es el clúster de prueba (%s). No se ejecuta.' % real)
    if exigir_vacia and tablas:
        raise SystemExit('La base de prueba no está vacía (%d tablas). No se ejecuta.' % tablas)


# ─────────────── modo SERVIDOR (proceso hijo) ───────────────
def servidor(puerto, dir_encuentro):
    import app as APP
    import uvicorn
    from database import engine
    assert engine.dialect.name == 'postgresql' and engine.url.host in ('127.0.0.1', 'localhost')
    exigir_cluster_de_prueba(engine, exigir_vacia=False)
    _orig = APP._nuevo_comunicado

    def _encuentro_tras_consulta_previa(*args):
        # Solo se llega aquí si la consulta previa por clave NO encontró nada.
        open(os.path.join(dir_encuentro, 'paso_consulta_%d' % os.getpid()), 'w').close()
        limite = time.time() + 20
        while len(os.listdir(dir_encuentro)) < 2 and time.time() < limite:
            time.sleep(0.02)
        return _orig(*args)

    APP._nuevo_comunicado = _encuentro_tras_consulta_previa
    uvicorn.run(APP.app, host='127.0.0.1', port=puerto, lifespan='off', log_level='warning')


if len(sys.argv) >= 4 and sys.argv[1] == '--servidor':
    servidor(int(sys.argv[2]), sys.argv[3])
    sys.exit(0)

# ─────────────── modo PRUEBA (proceso principal) ───────────────
from database import engine, SessionLocal  # noqa: E402
from sqlalchemy import inspect  # noqa: E402

assert engine.dialect.name == 'postgresql' and engine.url.host in ('127.0.0.1', 'localhost') \
    and str(engine.url.database).startswith('eo_test'), engine.url
exigir_cluster_de_prueba(engine, exigir_vacia=True)

import models as M  # noqa: E402
import app as APP  # noqa: E402
from auth import create_token  # noqa: E402

print('Motor: PostgreSQL de prueba (%s:%s/%s)' % (engine.url.host, engine.url.port, engine.url.database))
RES = []


def check(nombre, ok, detalle=''):
    RES.append((nombre, bool(ok)))
    print(('  OK  ' if ok else '  FALLA ') + nombre + ('' if ok else '  -> ' + str(detalle)[:300]))


M.Base.metadata.create_all(bind=engine)
check('P-00 el índice único existe en PostgreSQL',
      'uq_comunicado_autor_client_request' in {i['name'] for i in inspect(engine).get_indexes('comunicados')}, '')
db = SessionLocal()


def add(o):
    db.add(o)
    db.flush()
    return o


add(M.Usuario(colegio_id=None, username='superadmin', password_hash='x', nombre='S', apellido='A',
              role='superadmin', activo=True, must_change_password=False, token_version=0))
COL = add(M.Colegio(nombre='C1', codigo='c1', activo=True))


def usuario(username, role):
    return add(M.Usuario(colegio_id=COL.id, username=username, password_hash='x', nombre=username, apellido='T',
                         role=role, activo=True, must_change_password=False, token_version=0))


DIR, PROF, COORD = usuario('direccion', 'direccion'), usuario('prof', 'profesor'), usuario('coord', 'coordinador')
db.commit()
ESPERADOS = sorted([PROF.id, COORD.id])
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
        log = open(os.path.join(tempfile.gettempdir(), 'comdup_srv_%d_%d.log' % (p, i)), 'w')
        procesos.append(subprocess.Popen([sys.executable, os.path.abspath(__file__), '--servidor', str(p), dir_encuentro],
                                         cwd=tempfile.gettempdir(), env=dict(os.environ), stdout=log,
                                         stderr=subprocess.STDOUT))
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
        body = json.dumps({'titulo': 'Dos procesos', 'contenido': 'Mismo envío', 'tipo': 'general',
                           'client_request_id': claves[i]}).encode('utf-8')
        req = urllib.request.Request('http://127.0.0.1:%d/api/comunicados' % puertos[i], data=body,
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


def avisos(cid):
    db.expire_all()
    return sorted(n.usuario_id for n in db.query(M.Notificacion).filter_by(evento_key='comunicado:%d:creado' % cid))


def auditorias(cid):
    db.expire_all()
    return db.query(M.LogAuditoria).filter_by(accion='CREAR_COMUNICADO', registro_id=cid).count()


for caso, claves in (('MISMA clave', [str(uuid.uuid4())] * 2),
                     ('claves DISTINTAS (control)', [str(uuid.uuid4()), str(uuid.uuid4())])):
    print('\n=== Dos procesos de servidor, %s ===' % caso)
    dir_encuentro = tempfile.mkdtemp(prefix='comdup_encuentro_')
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
    filas = db.query(M.Comunicado).filter(M.Comunicado.client_request_id.in_(set(claves))).all()
    estados = sorted(r[0] for r in res if r)
    ids_resp = [r[1].get('id') for r in res if r]
    if claves[0] == claves[1]:
        check('P-01 ambos procesos superaron la consulta previa antes de insertar', pasaron == 2, pasaron)
        check('P-02 un solo comunicado', len(filas) == 1, len(filas))
        check('P-03 respuestas 201 + 200 con el MISMO id', estados == [200, 201] and len(set(ids_resp)) == 1
              and filas and ids_resp[0] == filas[0].id, (res, [f.id for f in filas]))
        check('P-04 un solo juego de notificaciones y una sola auditoría',
              filas and avisos(filas[0].id) == ESPERADOS and auditorias(filas[0].id) == 1,
              filas and (avisos(filas[0].id), auditorias(filas[0].id)))
        check('P-05 ninguna notificación ni auditoría huérfana del perdedor',
              db.query(M.Notificacion).filter(M.Notificacion.evento_key.like('comunicado:%')).count() == len(ESPERADOS)
              and db.query(M.LogAuditoria).filter_by(accion='CREAR_COMUNICADO').count() == 1, '')
    else:
        check('P-06 control: con claves distintas ambos procesos crean su comunicado (dos)',
              pasaron == 2 and len(filas) == 2 and estados == [201, 201], (pasaron, len(filas), estados))
        check('P-07 ...cada uno con su propio juego de notificaciones y su auditoría',
              all(avisos(f.id) == ESPERADOS and auditorias(f.id) == 1 for f in filas), [avisos(f.id) for f in filas])
db.close()

ok = sum(1 for _, r in RES if r)
print('\nRESULTADO COM-DUP-1 multiproceso: %d PASARON / %d FALLARON' % (ok, len(RES) - ok))
sys.exit(0 if ok == len(RES) else 1)
