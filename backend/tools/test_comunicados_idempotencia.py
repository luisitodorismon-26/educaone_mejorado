# -*- coding: utf-8 -*-
"""
EducaOne — COM-DUP-1: creación de comunicados idempotente y atómica.

El formulario envía un `client_request_id` por intento de publicación y lo
conserva al reintentar. El índice único parcial (colegio + autor + clave) admite
UN comunicado por clave, también con peticiones simultáneas; el reintento
devuelve solo el id y no notifica ni audita de nuevo. Con o sin clave, el
comunicado, TODAS sus notificaciones y la auditoría CREAR_COMUNICADO se guardan
en una sola transacción.

Incluye:
  - MIGRACIÓN sobre una base con el esquema anterior y datos existentes
    (comunicados, lecturas y notificaciones), que deben quedar intactos;
  - destinatarios idénticos al algoritmo anterior, aislamiento entre colegios;
  - fallos antes, durante y en el commit (nada a medias) y DESPUÉS del commit
    (todo guardado; el reintento lo recupera sin duplicar);
  - respuesta perdida seguida de un reintento con permisos revocados;
  - carrera determinista y 8 peticiones HTTP simultáneas.

Base temporal aislada. Nunca producción.

Uso:
    cd <carpeta temporal>      # para que ninguna base por defecto pueda crearse en backend/
    python <repo>/backend/tools/test_comunicados_idempotencia.py               # SQLite temporal
    EO_TEST_PG_URL=postgresql://eo_test@127.0.0.1:<puerto>/eo_test_comdup \\
    EO_TEST_PG_DATADIR=<directorio de datos del clúster DE PRUEBA> \\
        python <repo>/backend/tools/test_comunicados_idempotencia.py           # PostgreSQL de prueba

Con PostgreSQL solo se acepta un servidor LOCAL, una base `eo_test*` vacía y,
además, que el servidor conectado tenga como directorio de datos exactamente
EO_TEST_PG_DATADIR (el clúster desechable de la prueba). Si no, no se ejecuta.
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
    if not os.environ.get('EO_TEST_PG_DATADIR'):
        raise SystemExit('Con EO_TEST_PG_URL hace falta EO_TEST_PG_DATADIR (directorio del clúster de prueba).')
    os.environ['DATABASE_URL'] = PG_URL
    TMP = None
else:
    TMP = aislar_base_de_datos('com_dup1')

from database import engine, SessionLocal  # noqa: E402
from test_utils import verificar_engine_aislado  # noqa: E402
from sqlalchemy import inspect, text  # noqa: E402


def _exigir_cluster_de_prueba():
    """Aborta salvo que el servidor conectado sea EL clúster desechable de la prueba."""
    esperado = os.path.normcase(os.path.realpath(os.environ['EO_TEST_PG_DATADIR']))
    with engine.connect() as cn:
        real = os.path.normcase(os.path.realpath(cn.execute(text('SHOW data_directory')).scalar()))
        tablas = cn.execute(text("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")).scalar()
    if real != esperado:
        raise SystemExit('El PostgreSQL conectado NO es el clúster de prueba (%s). No se ejecuta.' % real)
    if tablas:
        raise SystemExit('La base de prueba no está vacía (%d tablas). No se ejecuta.' % tablas)


if PG_URL:
    assert engine.dialect.name == 'postgresql' and engine.url.host in ('127.0.0.1', 'localhost') \
        and str(engine.url.database).startswith('eo_test'), engine.url
    _exigir_cluster_de_prueba()
    print('Motor: PostgreSQL de prueba (%s:%s/%s)' % (engine.url.host, engine.url.port, engine.url.database))
else:
    verificar_engine_aislado(engine, TMP)
    print('Motor: SQLite temporal')

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session as _SesionORM  # noqa: E402
import models as M  # noqa: E402
import app as APP  # noqa: E402
from auth import create_token  # noqa: E402

RES = []


def check(nombre, ok, detalle=''):
    RES.append((nombre, bool(ok)))
    print(('  OK  ' if ok else '  FALLA ') + nombre + ('' if ok else '  -> ' + str(detalle)[:400]))


# ── Esquema ANTERIOR: tablas actuales, pero `comunicados` sin las columnas nuevas ni el índice ──
M.Base.metadata.create_all(bind=engine)
with engine.begin() as conn:
    conn.execute(text('DROP INDEX IF EXISTS uq_comunicado_autor_client_request'))
    conn.execute(text('ALTER TABLE comunicados DROP COLUMN client_request_id'))
    conn.execute(text('ALTER TABLE comunicados DROP COLUMN client_request_hash'))

db = SessionLocal()


def add(o):
    db.add(o)
    db.flush()
    return o


COL, OTRO = (add(M.Colegio(nombre=n, codigo=n.lower(), activo=True)) for n in ('C1', 'C2'))
add(M.Usuario(colegio_id=None, username='superadmin', password_hash='x', nombre='S', apellido='A',
              role='superadmin', activo=True, must_change_password=False, token_version=0))


def usuario(col, username, role, nivel=None, activo=True):
    return add(M.Usuario(colegio_id=col.id, username=username, password_hash='x', nombre=username, apellido='T',
                         role=role, activo=activo, must_change_password=False, token_version=0,
                         nivel_asignado=nivel))


DIR = usuario(COL, 'direccion', 'direccion')
DIR2 = usuario(COL, 'dir2', 'direccion')
CN = usuario(COL, 'coord_n', 'coordinador')
CP = usuario(COL, 'coord_p', 'coordinador', 'primaria')
CS = usuario(COL, 'coord_s', 'coordinador', 'secundaria')
PN = usuario(COL, 'prof_n', 'profesor')
PP = usuario(COL, 'prof_p', 'profesor', 'primaria')
PS = usuario(COL, 'prof_s', 'profesor', 'secundaria')
PSIS = usuario(COL, 'psi_s', 'psicologia', 'secundaria')
PSIN = usuario(COL, 'psi_n', 'psicologia')
INACT = usuario(COL, 'prof_inactivo', 'profesor', activo=False)
SECRE = usuario(COL, 'secretaria', 'secretaria')
DIR_O = usuario(OTRO, 'dir_o', 'direccion')
PROF_O = usuario(OTRO, 'prof_o', 'profesor')
SUPER = db.query(M.Usuario).filter_by(username='superadmin').one()
db.commit()

# Datos EXISTENTES (esquema anterior): dos comunicados con el mismo texto, una lectura y notificaciones.
with engine.begin() as conn:
    for n in (1, 2):
        conn.execute(text(
            "INSERT INTO comunicados (colegio_id, autor_id, titulo, contenido, tipo, para_profesores, "
            "para_coordinadores, para_psicologia, activo) VALUES (:c, :a, 'Legacy igual', 'mismo texto', 'general', "
            ":t, :t, :t, :t)"), {'c': COL.id, 'a': DIR.id, 't': True})
    cid = conn.execute(text("SELECT min(id) FROM comunicados")).scalar()
    conn.execute(text("INSERT INTO comunicados_leidos (colegio_id, comunicado_id, usuario_id) VALUES (:c, :i, :u)"),
                 {'c': COL.id, 'i': cid, 'u': PN.id})
    conn.execute(text("INSERT INTO notificaciones (usuario_id, colegio_id, titulo, mensaje, tipo, link, leida) "
                      "VALUES (:u, :c, '📢 Legacy igual', 'mismo texto', 'comunicado', '/comunicacion', :f)"),
                 {'u': PN.id, 'c': COL.id, 'f': False})

CONSULTAS_LEGACY = {
    'comunicados': 'SELECT id, colegio_id, autor_id, titulo, contenido, tipo, activo FROM comunicados ORDER BY id',
    'comunicados_leidos': 'SELECT id, comunicado_id, usuario_id FROM comunicados_leidos ORDER BY id',
    'notificaciones': 'SELECT id, usuario_id, titulo, mensaje, tipo, link FROM notificaciones ORDER BY id',
}


def foto(consultas):
    with engine.connect() as conn:
        return {t: [tuple(r) for r in conn.execute(text(q))] for t, q in consultas.items()}


ANTES = foto(CONSULTAS_LEGACY)
IDS_LEGACY = [r[0] for r in ANTES['comunicados']]

print("\n=== MIGRACIÓN (arranque de la app sobre el esquema anterior) ===")
client_ctx = TestClient(APP.app, raise_server_exceptions=False)
client = client_ctx.__enter__()          # ejecuta el lifespan: migraciones + verificación
insp = inspect(engine)
cols = {c['name'] for c in insp.get_columns('comunicados')}
idx = {i['name']: i for i in insp.get_indexes('comunicados')}
check('G-01 la migración agrega client_request_id y client_request_hash a comunicados',
      {'client_request_id', 'client_request_hash'} <= cols, cols)
check('G-02 crea el índice único parcial uq_comunicado_autor_client_request',
      'uq_comunicado_autor_client_request' in idx and idx['uq_comunicado_autor_client_request'].get('unique'),
      idx.keys())
check('G-03 comunicados, lecturas y notificaciones existentes quedan intactos', foto(CONSULTAS_LEGACY) == ANTES,
      foto(CONSULTAS_LEGACY))
with engine.connect() as conn:
    nulos = conn.execute(text('SELECT count(*) FROM comunicados WHERE client_request_id IS NULL '
                              'AND client_request_hash IS NULL')).scalar()
check('G-04 los comunicados existentes quedan con clave y huella NULL', nulos == 2, nulos)


def h(u):
    return {'Authorization': 'Bearer ' + create_token(u)}


def cuerpo(titulo='Reunión de padres', contenido='El viernes a las 8:00.', alcance='general', clave=None, **extra):
    b = {'titulo': titulo, 'contenido': contenido, 'tipo': alcance}
    b.update(extra)
    if clave is not None:
        b['client_request_id'] = clave
    return b


def n_comunicados():
    db.expire_all()
    return db.query(M.Comunicado).count()


def avisos_de(cid):
    db.expire_all()
    return sorted(n.usuario_id for n in db.query(M.Notificacion).filter_by(evento_key='comunicado:%d:creado' % cid))


def auditorias_de(cid):
    db.expire_all()
    return db.query(M.LogAuditoria).filter_by(accion='CREAR_COMUNICADO', registro_id=cid).count()


def n_notificaciones():
    db.expire_all()
    return db.query(M.Notificacion).count()


def n_auditorias():
    db.expire_all()
    return db.query(M.LogAuditoria).filter_by(accion='CREAR_COMUNICADO').count()


def esperados(alcance, autor=None, profes=True, coords=True, psico=True):
    """Algoritmo ANTERIOR (main) reproducido: roles marcados × usuarios del nivel."""
    nivel = None if alcance == 'general' else alcance
    roles = [r for r, on in (('profesor', profes), ('coordinador', coords), ('psicologia', psico)) if on]
    s = []
    for r in roles:
        s += APP.usuarios_autorizados_para_nivel(db, COL.id, r, nivel)
    return sorted(s)


print("\n=== SIN CLAVE: comportamiento de siempre, ahora atómico ===")
a_ant = n_auditorias()
r1, r2 = (client.post('/api/comunicados', json=cuerpo('Mismo texto sin clave'), headers=h(DIR)) for _ in range(2))
ok12 = r1.status_code == r2.status_code == 201 and r1.json()['id'] != r2.json()['id']
check('I-01 sin clave: dos envíos iguales son dos comunicados', ok12, (r1.text, r2.text))
if ok12:
    check('I-02 ...cada uno con TODAS sus notificaciones (destinatarios de siempre)',
          avisos_de(r1.json()['id']) == esperados('general') == avisos_de(r2.json()['id']),
          (avisos_de(r1.json()['id']), esperados('general')))
    check('I-03 ...y su auditoría CREAR_COMUNICADO guardada (D4)',
          auditorias_de(r1.json()['id']) == 1 and auditorias_de(r2.json()['id']) == 1 and n_auditorias() == a_ant + 2,
          (auditorias_de(r1.json()['id']), auditorias_de(r2.json()['id'])))

print("\n=== CON CLAVE: reintento tras respuesta perdida ===")
K1 = str(uuid.uuid4())
r = client.post('/api/comunicados', json=cuerpo(clave=K1), headers=h(DIR))
ID1 = r.json().get('id')
check('I-04 con clave nueva: 201 y un comunicado', r.status_code == 201 and ID1, r.text)
AV1 = avisos_de(ID1)
check('I-05 notifica a los destinatarios de siempre, una vez', AV1 == esperados('general'), (AV1, esperados('general')))
check('I-06 auditoría CREAR_COMUNICADO una vez', auditorias_de(ID1) == 1, auditorias_de(ID1))
antes_c, antes_n, antes_a = n_comunicados(), n_notificaciones(), n_auditorias()
rr = client.post('/api/comunicados', json=cuerpo(clave=K1), headers=h(DIR))
check('I-07 reintento (misma clave y contenido): 200, mismo id, SOLO id y confirmación (D2)',
      rr.status_code == 200 and rr.json() == {'message': 'Comunicado ya publicado', 'id': ID1, 'reintento': True},
      rr.text)
check('I-08 ...no crea otro comunicado, no repite notificaciones ni auditoría (D3)',
      (n_comunicados(), n_notificaciones(), n_auditorias()) == (antes_c, antes_n, antes_a) and avisos_de(ID1) == AV1,
      (n_comunicados(), n_notificaciones(), n_auditorias(), antes_c, antes_n, antes_a))

print("\n=== MISMA CLAVE CON OTRO CONTENIDO: 409, nada cambia ===")
for nombre, b in (('título', cuerpo('Otro título', clave=K1)), ('contenido', cuerpo(contenido='Otro texto', clave=K1)),
                  ('alcance', cuerpo(alcance='primaria', clave=K1)), ('imagen', cuerpo(clave=K1, imagen='data:image/png;base64,AAAA'))):
    r409 = client.post('/api/comunicados', json=b, headers=h(DIR))
    check('I-09 otro %s con la misma clave: 409 motivo clave_con_otro_contenido' % nombre,
          r409.status_code == 409 and r409.json().get('motivo') == 'clave_con_otro_contenido', r409.text)
db.expire_all()
c1 = db.get(M.Comunicado, ID1)
check('I-10 ...ni se crea nada ni se modifica el comunicado guardado',
      (n_comunicados(), n_notificaciones()) == (antes_c, antes_n) and c1.titulo == 'Reunión de padres'
      and c1.tipo == 'general', (n_comunicados(), c1.titulo, c1.tipo))

print("\n=== PUBLICACIONES INTENCIONALES IDÉNTICAS (claves distintas) ===")
ra = client.post('/api/comunicados', json=cuerpo('Idéntico', clave=str(uuid.uuid4())), headers=h(DIR))
rb = client.post('/api/comunicados', json=cuerpo('Idéntico', clave=str(uuid.uuid4())), headers=h(DIR))
check('I-11 claves distintas con contenido idéntico: dos comunicados',
      ra.status_code == rb.status_code == 201 and ra.json()['id'] != rb.json()['id'], (ra.text, rb.text))

print("\n=== AISLAMIENTO entre usuarios y colegios ===")
r_dir2 = client.post('/api/comunicados', json=cuerpo(clave=K1), headers=h(DIR2))
r_otro = client.post('/api/comunicados', json=cuerpo(clave=K1), headers=h(DIR_O))
check('I-12 la misma clave de OTRA persona del colegio crea su propio comunicado (sin 409 ni id ajeno)',
      r_dir2.status_code == 201 and r_dir2.json()['id'] != ID1, r_dir2.text)
check('I-13 la misma clave en OTRO colegio crea su propio comunicado', r_otro.status_code == 201
      and r_otro.json()['id'] not in (ID1, r_dir2.json().get('id')), r_otro.text)
db.expire_all()
c_otro = db.get(M.Comunicado, r_otro.json()['id'])
av_otro = avisos_de(c_otro.id)
check('I-14 el comunicado del otro colegio solo notifica a su colegio',
      c_otro.colegio_id == OTRO.id and av_otro == [PROF_O.id], (c_otro.colegio_id, av_otro))

print("\n=== FORMATO DE LA CLAVE Y PERMISOS ===")
antes_c = n_comunicados()
check('I-15 clave con formato inválido: 400 y nada creado',
      client.post('/api/comunicados', json=cuerpo(clave='x y'), headers=h(DIR)).status_code == 400
      and client.post('/api/comunicados', json=cuerpo(clave='a' * 65), headers=h(DIR)).status_code == 400
      and n_comunicados() == antes_c, '')
r_sa = client.post('/api/comunicados', json=cuerpo(clave=str(uuid.uuid4())), headers=h(SUPER))
check('I-16 clave de un usuario SIN colegio: 400 y nada creado', r_sa.status_code == 400 and n_comunicados() == antes_c,
      r_sa.text)
r_psi = client.post('/api/comunicados', json=cuerpo(alcance='primaria', clave=str(uuid.uuid4())), headers=h(PSIS))
r_prof = client.post('/api/comunicados', json=cuerpo(clave=str(uuid.uuid4())), headers=h(PN))
check('I-17 permisos sin cambios: Psicología fuera de su división 403, profesor 403, nada creado',
      r_psi.status_code == 403 and r_prof.status_code == 403 and n_comunicados() == antes_c, (r_psi.text, r_prof.text))

print("\n=== DESTINATARIOS idénticos al algoritmo anterior ===")
for alcance in ('general', 'primaria', 'secundaria'):
    for flags in ({}, {'para_profesores': False}, {'para_coordinadores': False, 'para_psicologia': False}):
        rd = client.post('/api/comunicados', json=cuerpo('Dest %s %s' % (alcance, sorted(flags)), alcance=alcance,
                                                         clave=str(uuid.uuid4()), **flags), headers=h(DIR))
        esp = esperados(alcance, profes=flags.get('para_profesores', True),
                        coords=flags.get('para_coordinadores', True), psico=flags.get('para_psicologia', True))
        check('I-18 destinatarios %s %s' % (alcance, flags or '(todos los roles)'),
              rd.status_code == 201 and avisos_de(rd.json()['id']) == esp, (rd.text, avisos_de(rd.json().get('id', 0)), esp))
check('I-19 nunca se notifica a inactivos, secretaría, dirección ni a otro colegio',
      not ({INACT.id, SECRE.id, DIR2.id, PROF_O.id, DIR_O.id} & set(esperados('general'))), esperados('general'))

print("\n=== RESPUESTA PERDIDA + REINTENTO CON PERMISOS REVOCADOS ===")
K_REV = str(uuid.uuid4())
rp = client.post('/api/comunicados', json=cuerpo('Antes de revocar', clave=K_REV), headers=h(CN))
ID_REV = rp.json().get('id')                  # el cliente «no recibió» esta respuesta
cn_db = db.get(M.Usuario, CN.id)
cn_db.role = 'profesor'                        # se le retiran los permisos de publicar
db.commit()
r_rev = client.post('/api/comunicados', json=cuerpo('Antes de revocar', clave=K_REV), headers=h(cn_db))
db.expire_all()
filas_rev = db.query(M.Comunicado).filter_by(client_request_id=K_REV).all()
check('P-01 el reintento con permisos revocados es RECHAZADO (403)', r_rev.status_code == 403, r_rev.text)
check('P-02 ...y el comunicado del envío anterior SIGUE guardado, una vez y completo',
      rp.status_code == 201 and len(filas_rev) == 1 and filas_rev[0].id == ID_REV and len(avisos_de(ID_REV)) > 0
      and auditorias_de(ID_REV) == 1, (rp.text, [f.id for f in filas_rev]))
cn_db.role = 'coordinador'
db.commit()

print("\n=== ATOMICIDAD: fallos antes, durante y en el commit → nada a medias ===")


def estado():
    return (n_comunicados(), n_notificaciones(), n_auditorias())


def con_parche(nombre_attr, sustituto, objetivo=APP):
    original = getattr(objetivo, nombre_attr)
    setattr(objetivo, nombre_attr, sustituto)
    return lambda: setattr(objetivo, nombre_attr, original)


def caso_fallo(etiqueta, nombre_attr, sustituto, objetivo=APP):
    for con_clave in (True, False):
        k = str(uuid.uuid4()) if con_clave else None
        ini = estado()
        deshacer = con_parche(nombre_attr, sustituto, objetivo)
        try:
            rf = client.post('/api/comunicados', json=cuerpo('Fallo %s' % etiqueta, clave=k), headers=h(DIR))
        finally:
            deshacer()
        check('%s (%s): 500 y NADA guardado (ni comunicado, ni notificaciones, ni auditoría)'
              % (etiqueta, 'con clave' if con_clave else 'sin clave'),
              rf.status_code == 500 and estado() == ini, (rf.status_code, ini, estado()))
        if con_clave:
            rr2 = client.post('/api/comunicados', json=cuerpo('Fallo %s' % etiqueta, clave=k), headers=h(DIR))
            check('%s: el reintento con la misma clave crea UNO completo' % etiqueta,
                  rr2.status_code == 201 and avisos_de(rr2.json()['id']) == esperados('general')
                  and auditorias_de(rr2.json()['id']) == 1, rr2.text)


def _falla_destinatarios(*a, **k):
    raise RuntimeError('fallo simulado antes de crear notificaciones')


_orig_notifs = APP._notificaciones_comunicado_estrictas


def _falla_en_la_tercera(db_, comunicado, destinatarios, evento_key):
    for i, uid in enumerate(destinatarios):
        if i == 2:
            raise RuntimeError('fallo simulado durante las notificaciones')
        db_.add(M.Notificacion(usuario_id=uid, colegio_id=comunicado.colegio_id, titulo='x', mensaje='x',
                               tipo='comunicado', link='/comunicacion', evento_key=evento_key))


def _duplica_un_aviso(db_, comunicado, destinatarios, evento_key):
    _orig_notifs(db_, comunicado, destinatarios, evento_key)
    db_.add(M.Notificacion(usuario_id=destinatarios[0], colegio_id=comunicado.colegio_id, titulo='x', mensaje='x',
                           tipo='comunicado', link='/comunicacion', evento_key=evento_key))   # viola el índice único


def _omite_un_aviso(db_, comunicado, destinatarios, evento_key):
    _orig_notifs(db_, comunicado, destinatarios[1:], evento_key)


caso_fallo('F1 excepción NO SQL antes de las notificaciones', '_destinatarios_comunicado', _falla_destinatarios)
caso_fallo('F2 excepción NO SQL durante las notificaciones (tras añadir 2)', '_notificaciones_comunicado_estrictas',
           _falla_en_la_tercera)
caso_fallo('F3 error SQL durante las notificaciones (índice usuario+evento)', '_notificaciones_comunicado_estrictas',
           _duplica_un_aviso)
caso_fallo('F5 notificaciones incompletas (falta un destinatario)', '_notificaciones_comunicado_estrictas',
           _omite_un_aviso)

_commit_real = _SesionORM.commit


def _commit_que_falla(self):
    raise RuntimeError('fallo simulado del commit')


caso_fallo('F4 el commit falla', 'commit', _commit_que_falla, objetivo=_SesionORM)

print("\n=== FALLO DESPUÉS DEL COMMIT: error, pero todo guardado; el reintento lo recupera ===")
K6 = str(uuid.uuid4())
ini = estado()
_llamadas = {'n': 0}


def _commit_y_luego_falla(self):
    _commit_real(self)
    _llamadas['n'] += 1
    raise RuntimeError('fallo simulado DESPUÉS del commit')


deshacer = con_parche('commit', _commit_y_luego_falla, _SesionORM)
try:
    r6 = client.post('/api/comunicados', json=cuerpo('Tras el commit', clave=K6), headers=h(DIR))
finally:
    deshacer()
db.expire_all()
f6 = db.query(M.Comunicado).filter_by(client_request_id=K6).all()
check('F6 la respuesta es un error (500) aunque se guardó', r6.status_code == 500, r6.status_code)
check('F6 ...el comunicado, TODAS sus notificaciones y su auditoría están guardados',
      len(f6) == 1 and avisos_de(f6[0].id) == esperados('general') and auditorias_de(f6[0].id) == 1,
      [x.id for x in f6])
r6b = client.post('/api/comunicados', json=cuerpo('Tras el commit', clave=K6), headers=h(DIR))
check('F6 ...el reintento con la misma clave lo recupera (200, mismo id) sin duplicar nada',
      r6b.status_code == 200 and f6 and r6b.json().get('id') == f6[0].id
      and estado() == (ini[0] + 1, ini[1] + len(esperados('general')), ini[2] + 1), (r6b.text, ini, estado()))

print("\n=== notify() conserva su contrato (no se tocó) ===")
try:
    res_notify = APP.notify(db, COL.id, 'x', usuario_ids=object())    # argumento que hace fallar su interior
    check('F7 notify() sigue sin propagar errores (devuelve [])', res_notify == [], res_notify)
except Exception as e:  # pragma: no cover
    check('F7 notify() sigue sin propagar errores (devuelve [])', False, e)
db.rollback()

print("\n=== CARRERA DETERMINISTA (ambas pasan la consulta previa) ===")
K2 = str(uuid.uuid4())
_orig_nuevo = APP._nuevo_comunicado
GANADOR = {}


def _gana_otra_peticion(current_user, campos, clave, huella):
    # Entre la consulta previa y el insert, OTRA petición con la misma clave
    # termina primero (sesión aparte), con sus notificaciones. Solo el índice
    # único puede detectarlo.
    s2 = SessionLocal()
    try:
        g = M.Comunicado(autor_id=DIR.id, colegio_id=COL.id, client_request_id=clave, client_request_hash=huella,
                         **dict(campos, titulo=campos['titulo']))
        s2.add(g)
        s2.flush()
        for uid in esperados('general'):
            s2.add(M.Notificacion(usuario_id=uid, colegio_id=COL.id, titulo='📢 ' + g.titulo, mensaje='x',
                                  tipo='comunicado', link='/comunicacion', evento_key='comunicado:%d:creado' % g.id))
        s2.commit()
        GANADOR['id'] = g.id
    finally:
        s2.close()
    return _orig_nuevo(current_user, campos, clave, huella)


APP._nuevo_comunicado = _gana_otra_peticion
ini = estado()
try:
    rc = client.post('/api/comunicados', json=cuerpo('Carrera', clave=K2), headers=h(DIR))
finally:
    APP._nuevo_comunicado = _orig_nuevo
db.expire_all()
filas_k2 = db.query(M.Comunicado).filter_by(client_request_id=K2).all()
check('C-01 el índice único detecta la carrera: 200 con el comunicado ganador, sin crear otro',
      rc.status_code == 200 and rc.json().get('id') == GANADOR.get('id') and len(filas_k2) == 1, rc.text)
check('C-02 ...la petición perdedora no deja notificaciones ni auditoría',
      estado() == (ini[0] + 1, ini[1] + len(esperados('general')), ini[2]), (ini, estado()))

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

# Ensancha la ventana entre la consulta previa y el insert para que TODAS las
# peticiones pasen la consulta antes de que la primera guarde.
APP._nuevo_comunicado = lambda *a: (time.sleep(0.4), _orig_nuevo(*a))[1]


def rafaga(claves):
    resultados = []
    barrera = threading.Barrier(len(claves), timeout=30)
    cab = dict(h(DIR), **{'Content-Type': 'application/json'})
    datos = [json.dumps(cuerpo('Carrera real', clave=k)).encode('utf-8') for k in claves]

    def enviar(i):
        req = urllib.request.Request('http://127.0.0.1:%d/api/comunicados' % PORT, method='POST',
                                     data=datos[i], headers=cab)
        barrera.wait()
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                resultados.append((resp.status, json.load(resp)))
        except urllib.error.HTTPError as e:
            resultados.append((e.code, json.load(e)))

    hilos = [threading.Thread(target=enviar, args=(i,)) for i in range(len(claves))]
    for t in hilos:
        t.start()
    for t in hilos:
        t.join(timeout=90)
    return resultados


K3 = str(uuid.uuid4())
ini = estado()
res = rafaga([K3] * 8)
db.expire_all()
filas_k3 = db.query(M.Comunicado).filter_by(client_request_id=K3).all()
estados = sorted(s for s, _ in res)
check('R-01 8 peticiones simultáneas con la misma clave: un solo comunicado', len(filas_k3) == 1, len(filas_k3))
check('R-02 todas responden con el MISMO comunicado (1 × 201, 7 × 200)',
      estados == [200] * 7 + [201] and {j.get('id') for _, j in res} == {filas_k3[0].id}, (estados, res[:2]))
check('R-03 un solo juego de notificaciones y una sola auditoría',
      avisos_de(filas_k3[0].id) == esperados('general') and auditorias_de(filas_k3[0].id) == 1
      and estado() == (ini[0] + 1, ini[1] + len(esperados('general')), ini[2] + 1), (ini, estado()))
claves = [str(uuid.uuid4()) for _ in range(8)]
res2 = rafaga(claves)
db.expire_all()
check('R-04 control: 8 simultáneas con claves DISTINTAS crean 8 comunicados completos',
      sorted(s for s, _ in res2) == [201] * 8
      and db.query(M.Comunicado).filter(M.Comunicado.client_request_id.in_(claves)).count() == 8, res2[:2])
APP._nuevo_comunicado = _orig_nuevo
server.should_exit = True

print("\n=== AL FINAL ===")
final = foto(CONSULTAS_LEGACY)
check('G-05 los datos existentes siguen intactos',
      [r for r in final['comunicados'] if r[0] in IDS_LEGACY] == ANTES['comunicados']
      and final['comunicados_leidos'] == ANTES['comunicados_leidos']
      and [r for r in final['notificaciones'] if r[0] in {x[0] for x in ANTES['notificaciones']}] == ANTES['notificaciones'],
      '')
client_ctx.__exit__(None, None, None)
db.close()

ok = sum(1 for _, r in RES if r)
print('\nRESULTADO COM-DUP-1: %d PASARON / %d FALLARON' % (ok, len(RES) - ok))
sys.exit(0 if ok == len(RES) else 1)
