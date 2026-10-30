"""SALIDAS-MIXTAS — concurrencia REAL en PostgreSQL al configurar componentes.

Peticiones simultáneas (hilos con su propio TestClient, cada uno con su sesión
y su bucle de eventos) contra una base PostgreSQL TEMPORAL creada por la propia
prueba:

  1. el mismo componente varias veces a la vez  -> 1 vínculo y 1 asignatura;
  2. componentes distintos que juntos superan la capacidad -> nunca más de 2
     componentes, y los rechazados no dejan asignaturas huérfanas;
  3. PUT (componente de la salida) y POST (de otra salida) a la vez -> lo mismo.

Para que la carrera sea reproducible, el test ensancha la ventana entre leer y
escribir con un retardo dentro de `crear_asignatura_dedicada` (solo en el
test). Se ejecuta dos veces:
  * CONTROL sin `_bloquear_curso_optativas`: debe aparecer alguna violación,
    lo que demuestra que el test detecta la carrera;
  * con el bloqueo (el código real): ninguna violación.

SEGURIDAD DE LA BASE
--------------------
Que el servidor sea local no basta: en local también hay bases con datos. Por
eso la prueba NUNCA trabaja sobre una base que no haya creado ella misma:

  * `EO_PG_TEST_SERVER` es solo la conexión de administración a un servidor
    local (127.0.0.1/localhost). En esa base no se crea ni se borra nada.
  * La prueba crea su propia base con un nombre único (`eo_tmp_salidas_<hex>`)
    y la marca con un comentario que lleva un token aleatorio de esta ejecución.
  * Antes de crear una sola tabla, `verificar_base_temporal` exige que la base
    conectada sea exactamente esa, que lleve ese token y que esté vacía. Si no,
    se aborta sin tocar nada. No hay `drop_all`.
  * La misma comprobación se ejecuta primero contra una base ordinaria (la de
    administración, o la de `EO_PG_TEST_ORDINARIA` si se indica) y debe
    rechazarla sin modificarla.
  * Al terminar se elimina ÚNICAMENTE la base temporal, tras volver a verificar
    su nombre y su token.

Uso (desde backend/):
    EO_PG_TEST_SERVER=postgresql://usuario@127.0.0.1:PUERTO/postgres \\
        python tools/test_salidas_concurrencia_pg.py
"""
import atexit
import datetime as dt
import os
import sys
import threading
import time
import uuid
from urllib.parse import urlparse, urlunparse

import psycopg2
from psycopg2 import sql

SERVIDOR = os.environ.get('EO_PG_TEST_SERVER', '')
_u = urlparse(SERVIDOR)
if not SERVIDOR.startswith('postgresql') or _u.hostname not in ('127.0.0.1', 'localhost'):
    print('EO_PG_TEST_SERVER debe ser la conexión de administración a un PostgreSQL local '
          '(127.0.0.1/localhost).')
    sys.exit(2)

PREFIJO = 'eo_tmp_salidas_'
NOMBRE = PREFIJO + uuid.uuid4().hex[:16]
TOKEN = 'eo-test-temporal:' + uuid.uuid4().hex
OK, MAL = [], []


def check(nombre, cond, detalle=''):
    (OK if cond else MAL).append(nombre)
    print('  %s %s %s' % ('PASA ' if cond else 'FALLA', nombre, '' if cond else str(detalle)[:400]))


def _admin():
    cn = psycopg2.connect(SERVIDOR)
    cn.autocommit = True
    return cn


def _url_de(base):
    return urlunparse(_u._replace(path='/' + base))


class BaseNoTemporal(RuntimeError):
    pass


def verificar_base_temporal(cn, nombre, token):
    """Aborta si la conexión `cn` no es la base temporal vacía de ESTA ejecución.

    Solo lee: current_database(), el comentario de la base y si hay tablas.
    """
    cur = cn.cursor()
    cur.execute("SELECT current_database()")
    actual = cur.fetchone()[0]
    if actual != nombre or not actual.startswith(PREFIJO):
        raise BaseNoTemporal('la base conectada es %r, no la temporal %r' % (actual, nombre))
    cur.execute("SELECT shobj_description(oid, 'pg_database') FROM pg_database "
                "WHERE datname = current_database()")
    marca = cur.fetchone()[0]
    if marca != token:
        raise BaseNoTemporal('la base %r no lleva el token de esta ejecución' % actual)
    cur.execute("SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema NOT IN ('pg_catalog', 'information_schema')")
    if cur.fetchone()[0]:
        raise BaseNoTemporal('la base %r no está vacía' % actual)


def _resumen(cn):
    """Huella de una base para comprobar que no cambió: tablas y filas por tabla."""
    cur = cn.cursor()
    cur.execute("SELECT table_schema, table_name FROM information_schema.tables "
                "WHERE table_schema NOT IN ('pg_catalog', 'information_schema') ORDER BY 1, 2")
    tablas = cur.fetchall()
    filas = []
    for esq, tab in tablas:
        cur.execute(sql.SQL('SELECT count(*) FROM {}.{}').format(sql.Identifier(esq), sql.Identifier(tab)))
        filas.append(cur.fetchone()[0])
    return list(zip(tablas, filas))


print('\n=== SEGURIDAD: una base ordinaria se rechaza antes de modificarla ===')
ORDINARIA = os.environ.get('EO_PG_TEST_ORDINARIA') or SERVIDOR
_uo = urlparse(ORDINARIA)
if _uo.hostname not in ('127.0.0.1', 'localhost'):
    print('EO_PG_TEST_ORDINARIA debe ser local.')
    sys.exit(2)
cn_ord = psycopg2.connect(ORDINARIA)
antes = _resumen(cn_ord)
try:
    verificar_base_temporal(cn_ord, NOMBRE, TOKEN)
    rechazada = False
except BaseNoTemporal as e:
    rechazada = True
    print('    rechazo:', e)
despues = _resumen(cn_ord)
cn_ord.close()
check('una base ordinaria (%s) se rechaza' % _uo.path.lstrip('/'), rechazada)
check('la base ordinaria queda idéntica (%d tablas, mismas filas)' % len(antes), antes == despues,
      (antes, despues))

print('\n=== Base temporal de esta ejecución ===')
_cn = _admin()
_cur = _cn.cursor()
_cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", [NOMBRE])
if _cur.fetchone():
    print('Ya existe una base %r: no se toca.' % NOMBRE)
    sys.exit(2)
_cur.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(NOMBRE)))
_cur.execute(sql.SQL('COMMENT ON DATABASE {} IS {}').format(sql.Identifier(NOMBRE), sql.Literal(TOKEN)))
_cn.close()
print('    creada %s' % NOMBRE)


def _eliminar_temporal():
    """Borra SOLO la base temporal, tras comprobar de nuevo nombre y token."""
    try:
        engine.dispose()
    except Exception:
        pass
    cn = _admin()
    cur = cn.cursor()
    cur.execute("SELECT shobj_description(oid, 'pg_database') FROM pg_database WHERE datname = %s", [NOMBRE])
    fila = cur.fetchone()
    if fila is None:
        cn.close()
        return
    if not NOMBRE.startswith(PREFIJO) or fila[0] != TOKEN:
        print('NO se elimina %r: su marca no coincide.' % NOMBRE)
        cn.close()
        return
    cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()", [NOMBRE])
    cur.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(NOMBRE)))
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", [NOMBRE])
    print('    base temporal %s %s' % (NOMBRE, 'ELIMINADA' if cur.fetchone() is None else 'NO SE PUDO ELIMINAR'))
    cn.close()


engine = None
atexit.register(_eliminar_temporal)

_cn = psycopg2.connect(_url_de(NOMBRE))
try:
    verificar_base_temporal(_cn, NOMBRE, TOKEN)
except BaseNoTemporal as e:
    print('ABORTADO antes de crear tablas:', e)
    sys.exit(2)
finally:
    _cn.close()
check('la base temporal es la creada por esta ejecución, con su token y vacía', True)

os.environ['DATABASE_URL'] = _url_de(NOMBRE)
BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
from database import engine, SessionLocal  # noqa: E402
assert engine.url.database == NOMBRE and engine.url.host in ('127.0.0.1', 'localhost'), engine.url
import models as M  # noqa: E402
import app as APP  # noqa: E402
import salida_optativa_docente as DOC  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from auth import create_token  # noqa: E402

M.Base.metadata.create_all(bind=engine)


db = SessionLocal()


def add(o):
    db.add(o)
    db.flush()
    return o


col = add(M.Colegio(nombre='Colegio Concurrencia', codigo='CONC', activo=True))
ano = add(M.AnoEscolar(colegio_id=col.id, nombre='2026-2027', activo=True, cerrado=False,
                       fecha_inicio=dt.date(2026, 9, 1), fecha_fin=dt.date(2027, 6, 30)))
g4 = add(M.Grado(colegio_id=col.id, nombre='4to Secundaria', nivel='secundaria', orden=4, activo=True))
dire = add(M.Usuario(colegio_id=col.id, username='conc_dir', password_hash='x', nombre='Dir', apellido='C',
                     role='direccion', activo=True, must_change_password=False, token_version=0))
profes = [add(M.Usuario(colegio_id=col.id, username='conc_p%d' % i, password_hash='x', nombre='P%d' % i,
                        apellido='C', role='profesor', activo=True, must_change_password=False,
                        token_version=0)) for i in range(4)]
db.commit()
HD = {'Authorization': 'Bearer ' + create_token(dire)}
PIDS = [p.id for p in profes]

_crear_original = DOC.crear_asignatura_dedicada


def _crear_lento(db_, curso, componente):
    time.sleep(0.25)          # ensancha la ventana leer -> escribir
    return _crear_original(db_, curso, componente)


DOC.crear_asignatura_dedicada = _crear_lento

N_CURSO = [0]


def curso_nuevo(salida='HLM', con_hlm_le=False):
    N_CURSO[0] += 1
    s = SessionLocal()
    c = M.Curso(colegio_id=col.id, nombre='C%d' % N_CURSO[0], grado_id=g4.id, ano_escolar_id=ano.id,
                activo=True, salida_optativa_codigo=salida)
    s.add(c)
    s.commit()
    cid = c.id
    s.close()
    if con_hlm_le:
        r = TestClient(APP.app).put('/api/cursos/%d/salida-optativa' % cid, headers=HD,
                                    json={'profesores': {'HLM-LE-4': PIDS[0]}})
        assert r.status_code == 200, r.text
    return cid


def a_la_vez(peticiones):
    """[(metodo, url, json)] lanzadas juntas tras una barrera -> [(status, json)]."""
    barrera = threading.Barrier(len(peticiones))
    res = [None] * len(peticiones)

    def run(i, metodo, url, body):
        cli = TestClient(APP.app)
        barrera.wait()
        try:
            r = getattr(cli, metodo)(url, headers=HD, json=body)
            res[i] = (r.status_code, r.json() if 'json' in r.headers.get('content-type', '') else r.text)
        except Exception as e:        # una excepción no controlada es un 500
            res[i] = (500, repr(e))

    hs = [threading.Thread(target=run, args=(i,) + p) for i, p in enumerate(peticiones)]
    for h in hs:
        h.start()
    for h in hs:
        h.join()
    return res


def estado(cid):
    s = SessionLocal()
    try:
        maps = [(m.componente_codigo, m.asignatura_id) for m in
                s.query(M.CursoComponenteOptativo).filter_by(curso_id=cid)]
        ligadas = {a.asignatura_id for a in s.query(M.AsignacionProfesor).filter_by(curso_id=cid)}
        asigs = [(a.id, a.codigo) for a in s.query(M.Asignatura).filter(M.Asignatura.id.in_(ligadas | {x[1] for x in maps}))]
        return maps, asigs
    finally:
        s.close()


def huerfanas():
    """Asignaturas dedicadas sin vínculo ni asignación (restos de una petición rechazada)."""
    s = SessionLocal()
    try:
        mapeadas = {r[0] for r in s.query(M.CursoComponenteOptativo.asignatura_id)}
        asignadas = {r[0] for r in s.query(M.AsignacionProfesor.asignatura_id)}
        return [a.id for a in s.query(M.Asignatura).filter(M.Asignatura.area_curricular_codigo.is_(None))
                if a.id not in mapeadas and a.id not in asignadas]
    finally:
        s.close()


RONDAS = 6


def escenarios(etiqueta):
    """Devuelve el número de violaciones encontradas en todas las rondas."""
    viol = []
    for r_ in range(RONDAS):
        # 1. Mismo componente, 4 a la vez.
        cid = curso_nuevo(con_hlm_le=True)
        url = '/api/cursos/%d/salida-optativa/componentes' % cid
        res = a_la_vez([('post', url, {'componente_codigo': 'HCS-CS-4', 'profesor_id': PIDS[i]})
                        for i in range(4)])
        maps, asigs = estado(cid)
        n_hcs = [a for a in asigs if a[1] == 'HCS-CS-4']
        if any(st >= 500 for st, _ in res):
            viol.append(('mismo componente: 500', res))
        if len([m for m in maps if m[0] == 'HCS-CS-4']) != 1 or len(n_hcs) != 1:
            viol.append(('mismo componente: vínculos=%d asignaturas=%d' % (
                len([m for m in maps if m[0] == 'HCS-CS-4']), len(n_hcs)), maps, asigs))
        # 2. Componentes distintos: HLM-LE ya está; 3 más a la vez -> solo cabe 1.
        cid = curso_nuevo(con_hlm_le=True)
        url = '/api/cursos/%d/salida-optativa/componentes' % cid
        res = a_la_vez([('post', url, {'componente_codigo': c, 'profesor_id': PIDS[1]})
                        for c in ('HCS-CS-4', 'MYT-MA-4', 'CYT-CN-4')])
        maps, _ = estado(cid)
        if any(st >= 500 for st, _ in res):
            viol.append(('distintos: 500', res))
        if len(maps) > 2:
            viol.append(('distintos: %d componentes' % len(maps), maps))
        if sorted(st for st, _ in res) != [200, 409, 409]:
            viol.append(('distintos: respuestas %s' % sorted(st for st, _ in res), res))
        # 3. PUT de un componente de la salida y POST de otra salida a la vez.
        cid = curso_nuevo(con_hlm_le=True)
        res = a_la_vez([('put', '/api/cursos/%d/salida-optativa' % cid,
                         {'profesores': {'HLM-IN-4': PIDS[2]}}),
                        ('post', '/api/cursos/%d/salida-optativa/componentes' % cid,
                         {'componente_codigo': 'HCS-CS-4', 'profesor_id': PIDS[3]})])
        maps, _ = estado(cid)
        if any(st >= 500 for st, _ in res):
            viol.append(('PUT+POST: 500', res))
        if len(maps) > 2:
            viol.append(('PUT+POST: %d componentes' % len(maps), maps))
    h = huerfanas()
    if h:
        viol.append(('asignaturas huérfanas tras rechazos', h))
    print('  [%s] %d violaciones en %d rondas x 3 escenarios' % (etiqueta, len(viol), RONDAS))
    for v in viol[:6]:
        print('     -', str(v)[:300])
    return viol


print('\n=== CONTROL: sin bloqueo del curso (debe aparecer la carrera) ===')
_bloqueo_real = APP._bloquear_curso_optativas
APP._bloquear_curso_optativas = lambda db_, curso: curso
v_control = escenarios('sin bloqueo')
check('CONTROL: sin bloqueo el test detecta al menos una violación', len(v_control) > 0,
      'no se reprodujo la carrera: el test no demostraría nada')
APP._bloquear_curso_optativas = _bloqueo_real

# Las huérfanas del control no deben contaminar la ronda real.
_s = SessionLocal()
_base_huerfanas = set(huerfanas())
_s.close()
_huerfanas_original = huerfanas
huerfanas = lambda: [x for x in _huerfanas_original() if x not in _base_huerfanas]  # noqa: E731

print('\n=== CON EL BLOQUEO (código real) ===')
v_real = escenarios('con bloqueo')
check('con bloqueo: mismo componente a la vez -> 1 vínculo, 1 asignatura, sin 500',
      not [v for v in v_real if v[0].startswith('mismo')], [v for v in v_real if v[0].startswith('mismo')])
check('con bloqueo: componentes distintos -> nunca más de 2; 1 aceptado y 2 rechazados con 409',
      not [v for v in v_real if v[0].startswith('distintos')], [v for v in v_real if v[0].startswith('distintos')])
check('con bloqueo: PUT y POST a la vez -> nunca más de 2, sin 500',
      not [v for v in v_real if v[0].startswith('PUT')], [v for v in v_real if v[0].startswith('PUT')])
check('con bloqueo: ningún rechazo deja asignaturas huérfanas',
      not [v for v in v_real if v[0].startswith('asignaturas')], [v for v in v_real if v[0].startswith('asignaturas')])

DOC.crear_asignatura_dedicada = _crear_original
db.close()
engine.dispose()
print('\n%d PASARON / %d FALLARON' % (len(OK), len(MAL)))
sys.exit(1 if MAL else 0)
