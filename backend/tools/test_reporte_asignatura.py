# -*- coding: utf-8 -*-
"""
EducaOne — Asignatura del reporte de conducta.

  M. Migración sobre el esquema ANTERIOR (reportes_conducta sin asignatura_id ni
     asignatura_nombre) con reportes existentes; segunda ejecución sin cambios.
  O. Opciones del selector: profesor con una y con varias materias, troncal y
     optativa, Dirección limitada al curso, aislamiento entre colegios (profesores
     con el mismo nombre).
  C. Crear: con asignatura, reporte general, IDs manipulados / de otro colegio /
     de otro curso / de otro profesor / inactivos -> rechazo sin registros.
  I. Doble envío: reintento (doble clic / respuesta perdida), misma clave con otra
     materia o con/sin materia -> 409, huella sin materia igual a la anterior,
     carrera determinista y carrera REAL de 8 peticiones.
  R. Renombrado posterior de la materia: el reporte y el PDF conservan el nombre.
  P. PDF: con materia, general, reporte antiguo, nombres largos.
  Z. Nada más cambia: reportes antiguos, asignaciones, nada enviado a padres.

Base temporal aislada (SQLite) o, con EO_PG_TEST_SERVER, una base PostgreSQL
TEMPORAL y exclusiva creada por la propia prueba (tools/pg_base_temporal.py):
se marca con un token, se verifica su identidad antes de cualquier DROP COLUMN
y al terminar se elimina solo esa base. Antes de crearla, una base ordinaria
con datos (EO_PG_TEST_ORDINARIA o, si no se indica, la de administración) debe
ser rechazada y quedar idéntica. EO_TEST_PG_URL ya no se acepta: nunca se
altera una base recibida directamente por una variable de entorno.

Uso (desde backend/):
    python tools/test_reporte_asignatura.py [carpeta_pdfs]                 # SQLite
    EO_PG_TEST_SERVER=postgresql://usuario@127.0.0.1:PUERTO/postgres \\
    [EO_PG_TEST_ORDINARIA=postgresql://usuario@127.0.0.1:PUERTO/base_con_datos] \\
        python tools/test_reporte_asignatura.py [carpeta_pdfs]             # PostgreSQL
"""
import datetime as dt
import hashlib
import json
import os
import socket
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(BK, 'tools'))
OUT = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix='reporte_asig_')
os.makedirs(OUT, exist_ok=True)

from test_utils import aislar_base_de_datos  # noqa: E402

if os.environ.get('EO_TEST_PG_URL'):
    raise SystemExit('EO_TEST_PG_URL ya no se acepta en esta prueba: use EO_PG_TEST_SERVER (la prueba crea y '
                     'elimina su propia base temporal; nunca altera una base indicada por variable de entorno).')
PG_SERVER = os.environ.get('EO_PG_TEST_SERVER')
PRE = []                                 # comprobaciones previas al import de la app
if PG_SERVER:
    import pg_base_temporal as PGT
    PG = PGT.BaseTemporal(PG_SERVER, prefijo='eo_tmp_repasig_')
    _ord = os.environ.get('EO_PG_TEST_ORDINARIA') or PG_SERVER
    import psycopg2 as _pg
    _c = _pg.connect(_ord)
    HUELLA_ORD = PGT.huella_base(_c)     # se vuelve a comparar al final de la prueba
    _c.close()
    _rech, _intacta, _motivo, _ntab, _nfil = PG.comprobar_rechazo(_ord)
    print('Base ordinaria de control: %d tablas, %d filas -> %s' % (_ntab, _nfil, _motivo or 'NO RECHAZADA'))
    PRE.append(('S-01 una base preexistente (%d tablas, %d filas) se rechaza antes de tocarla' % (_ntab, _nfil),
                _rech, _motivo))
    PRE.append(('S-02 ...y queda idéntica: tablas, filas, contenido y columnas', _intacta, ''))
    if not (_rech and _intacta):
        raise SystemExit('ABORTADO: la base ordinaria no fue rechazada o cambió.')
    os.environ['DATABASE_URL'] = PG.crear()
    PRE.append(('S-03 la base de la prueba es temporal, propia, marcada con el token y vacía', True, ''))
    TMP = None
else:
    PG = None
    TMP = aislar_base_de_datos('reporte_asignatura')

from database import engine, SessionLocal  # noqa: E402
from test_utils import verificar_engine_aislado  # noqa: E402

if PG:
    assert engine.dialect.name == 'postgresql' and engine.url.database == PG.nombre \
        and engine.url.host in ('127.0.0.1', 'localhost'), engine.url
    PG.engines.append(engine)
    print('Motor: PostgreSQL, base temporal %s' % engine.url.database)
else:
    verificar_engine_aislado(engine, TMP)
    print('Motor: SQLite temporal')

from sqlalchemy import inspect, text  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import pymupdf  # noqa: E402

import models as M  # noqa: E402
import app as APP  # noqa: E402
from auth import create_token  # noqa: E402

RES = []


def check(nombre, ok, detalle=''):
    RES.append((nombre, bool(ok)))
    print(('  OK  ' if ok else '  FALLA ') + nombre + ('' if ok else '  -> ' + str(detalle)[:300]))


if PRE:
    print('\n=== S. SEGURIDAD DE LA BASE ===')
    for _n, _ok, _d in PRE:
        check(_n, _ok, _d)


# ── Esquema ANTERIOR: reportes_conducta sin las columnas de asignatura ─────────
M.Base.metadata.create_all(bind=engine)
with engine.begin() as conn:
    if engine.dialect.name == 'postgresql':
        # Solo sobre la base temporal de ESTA ejecución: se vuelve a verificar
        # nombre y token en la misma conexión que va a ejecutar el DROP COLUMN.
        PG.verificar_identidad(conn.connection.driver_connection)
        conn.execute(text('ALTER TABLE reportes_conducta DROP COLUMN asignatura_id'))
        conn.execute(text('ALTER TABLE reportes_conducta DROP COLUMN asignatura_nombre'))
    else:
        # SQLite no borra una columna con FK: se reconstruye la tabla sin ellas.
        sql = conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='reportes_conducta'")).scalar()
        idx = [r[0] for r in conn.execute(text(
            "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='reportes_conducta' AND sql IS NOT NULL"))]
        lineas = [l for l in sql.split('\n') if 'asignatura_id' not in l and 'asignatura_nombre' not in l]
        viejo = '\n'.join(lineas)
        import re as _re
        viejo = _re.sub(r',\s*\)\s*$', '\n)', viejo)
        assert 'asignatura' not in viejo, viejo
        conn.execute(text('DROP TABLE reportes_conducta'))
        conn.execute(text(viejo))
        for s in idx:
            conn.execute(text(s))
cols0 = {c['name'] for c in inspect(engine).get_columns('reportes_conducta')}
assert not {'asignatura_id', 'asignatura_nombre'} & cols0, cols0

db = SessionLocal()


def add(o):
    db.add(o)
    db.flush()
    return o


def usuario(col, username, nombre, apellido, role):
    return add(M.Usuario(colegio_id=col.id, username=username, password_hash='x', nombre=nombre, apellido=apellido,
                         role=role, activo=True, must_change_password=False, token_version=0))


def colegio(cod):
    col = add(M.Colegio(nombre='Colegio %s' % cod, codigo=cod, activo=True))
    ano = add(M.AnoEscolar(colegio_id=col.id, nombre='2026-2027', activo=True, cerrado=False,
                           fecha_inicio=dt.date(2026, 9, 1), fecha_fin=dt.date(2027, 6, 30)))
    g = add(M.Grado(colegio_id=col.id, nombre='4to Secundaria', nivel='secundaria', orden=4, activo=True))
    return col, ano, g


def curso(col, ano, g, nombre):
    return add(M.Curso(colegio_id=col.id, nombre=nombre, grado_id=g.id, ano_escolar_id=ano.id, activo=True))


def asignatura(col, nombre, area='LE', activo=True):
    return add(M.Asignatura(colegio_id=col.id, nombre=nombre, codigo=nombre[:3].upper(),
                            area_curricular_codigo=area, activo=activo))


def asignar(col, ano, prof, cur, asig, activo=True):
    return add(M.AsignacionProfesor(colegio_id=col.id, profesor_id=prof.id, curso_id=cur.id, asignatura_id=asig.id,
                                    ano_escolar_id=ano.id, activo=activo))


def estudiante(col, cur, nombre, n):
    return add(M.Estudiante(colegio_id=col.id, nombre=nombre, apellido='Prueba', curso_id=cur.id, activo=True,
                            no_lista=n, fecha_ingreso=dt.date(2026, 8, 20)))


add(M.Usuario(colegio_id=None, username='superadmin', password_hash='x', nombre='S', apellido='A',
              role='superadmin', activo=True, must_change_password=False, token_version=0))
colA, anoA, gA = colegio('ASIGA')
colB, anoB, gB = colegio('ASIGB')
cur1 = curso(colA, anoA, gA, 'A')
cur2 = curso(colA, anoA, gA, 'B')
curB = curso(colB, anoB, gB, 'A')
DIR = usuario(colA, 'direccion', 'Dir', 'A', 'direccion')
DIR2 = usuario(colA, 'dir2', 'Dir2', 'A', 'direccion')
COORD = usuario(colA, 'coord', 'Coord', 'A', 'coordinador')
JULIO = usuario(colA, 'julio_a', 'Julio', 'Sena', 'profesor')        # dos materias en cur1
ANA = usuario(colA, 'ana_a', 'Ana', 'Mejía', 'profesor')             # una materia en cur1
DIR_B = usuario(colB, 'dir_b', 'Dir', 'B', 'direccion')
JULIO_B = usuario(colB, 'julio_b', 'Julio', 'Sena', 'profesor')      # mismo nombre, otro colegio
LE = asignatura(colA, 'Lengua Española', 'LE')
MAT = asignatura(colA, 'Matemática', 'MAT')
OPT = asignatura(colA, 'Literatura y Sociedad (Optativa HLM)', None)  # optativa dedicada
MUS = asignatura(colA, 'Música', None)
VIEJA = asignatura(colA, 'Asignatura retirada', 'CS', activo=False)
SOLO_B = asignatura(colA, 'Ciencias Sociales', 'CS')                # solo en cur2
LE_B = asignatura(colB, 'Lengua Española', 'LE')
asignar(colA, anoA, JULIO, cur1, LE)
asignar(colA, anoA, JULIO, cur1, OPT)
asignar(colA, anoA, JULIO, cur1, MUS, activo=False)   # asignación retirada: no cuenta
asignar(colA, anoA, JULIO, cur1, VIEJA)               # asignatura inactiva: no cuenta
asignar(colA, anoA, ANA, cur1, MAT)
asignar(colA, anoA, ANA, cur2, SOLO_B)
asignar(colB, anoB, JULIO_B, curB, LE_B)
EST1 = estudiante(colA, cur1, 'María', 1)
EST2 = estudiante(colA, cur2, 'Pedro', 1)
EST_B = estudiante(colB, curB, 'Rosa', 1)
db.commit()

# Reportes EXISTENTES con el esquema anterior: uno sin clave y uno con clave y
# huella calculada con la fórmula de siempre (5 elementos).
CLAVE_VIEJA = str(uuid.uuid4())
HUELLA_VIEJA = hashlib.sha256(json.dumps([EST1.id, 'Antiguo con clave', 'Texto antiguo', 'conducta', 'leve'],
                                         ensure_ascii=False).encode('utf-8')).hexdigest()
with engine.begin() as conn:
    conn.execute(text(
        "INSERT INTO reportes_conducta (colegio_id, estudiante_id, reportado_por, tipo, gravedad, titulo, descripcion, "
        "fecha, estado, numero_reporte, enviado_padres, confirmado_padre) VALUES (:c, :e, :u, 'conducta', 'leve', "
        "'Antiguo sin clave', 'Texto antiguo', :fd, 'respondido', '2026-0001', :f, :f)"),
        {'c': colA.id, 'e': EST1.id, 'u': JULIO.id, 'f': False, 'fd': dt.datetime(2026, 10, 5, 9, 30)})
    conn.execute(text(
        "INSERT INTO reportes_conducta (colegio_id, estudiante_id, reportado_por, tipo, gravedad, titulo, descripcion, "
        "fecha, estado, numero_reporte, client_request_id, client_request_hash, enviado_padres, confirmado_padre) "
        "VALUES (:c, :e, :u, 'conducta', 'leve', 'Antiguo con clave', 'Texto antiguo', :fd, 'pendiente', '2026-0002', "
        ":k, :hh, :f, :f)"),
        {'c': colA.id, 'e': EST1.id, 'u': JULIO.id, 'k': CLAVE_VIEJA, 'hh': HUELLA_VIEJA, 'f': False,
         'fd': dt.datetime(2026, 10, 6, 10, 0)})
COLS_LEGACY = ('id, colegio_id, estudiante_id, reportado_por, tipo, gravedad, titulo, descripcion, estado, '
               'numero_reporte, client_request_id, client_request_hash, enviado_padres, confirmado_padre')


def legacy():
    with engine.connect() as conn:
        return [tuple(r) for r in conn.execute(text(
            'SELECT %s FROM reportes_conducta WHERE numero_reporte IN (:a, :b) ORDER BY id' % COLS_LEGACY),
            {'a': '2026-0001', 'b': '2026-0002'})]


def asignaciones():
    with engine.connect() as conn:
        return [tuple(r) for r in conn.execute(text(
            'SELECT id, profesor_id, curso_id, asignatura_id, activo FROM asignaciones_profesor ORDER BY id'))]


LEGACY = legacy()
ASIGNACIONES = asignaciones()
assert len(LEGACY) == 2

print('\n=== M. MIGRACIÓN (arranque de la app sobre el esquema anterior) ===')
ctx = TestClient(APP.app)
client = ctx.__enter__()                 # lifespan: migraciones + verificación del esquema
cols = {c['name'] for c in inspect(engine).get_columns('reportes_conducta')}
check('M-01 la migración agrega asignatura_id y asignatura_nombre', {'asignatura_id', 'asignatura_nombre'} <= cols, cols)
with engine.connect() as conn:
    nulos = conn.execute(text('SELECT COUNT(*) FROM reportes_conducta WHERE asignatura_id IS NULL '
                              'AND asignatura_nombre IS NULL')).scalar()
check('M-02 los reportes existentes quedan intactos y SIN asignatura (no se deduce de las asignaciones)',
      legacy() == LEGACY and nulos == 2, (legacy(), nulos))
ctx.__exit__(None, None, None)
ctx = TestClient(APP.app)
client = ctx.__enter__()                 # segunda ejecución de la migración
cols2 = [c['name'] for c in inspect(engine).get_columns('reportes_conducta')]
check('M-03 segunda ejecución: sin error, columnas una sola vez, reportes intactos',
      cols2.count('asignatura_id') == 1 and cols2.count('asignatura_nombre') == 1 and legacy() == LEGACY, cols2)
if engine.dialect.name == 'postgresql':
    fks = inspect(engine).get_foreign_keys('reportes_conducta')
    check('M-04 (PostgreSQL) asignatura_id referencia asignaturas.id',
          any(f['constrained_columns'] == ['asignatura_id'] and f['referred_table'] == 'asignaturas' for f in fks), fks)


def h(u):
    return {'Authorization': 'Bearer ' + create_token(u)}


def opciones(u, est):
    r = client.get('/api/reportes/asignaturas-opciones', params={'estudiante_id': est.id}, headers=h(u))
    return r.status_code, [a['nombre'] for a in r.json().get('asignaturas', [])] if r.status_code == 200 else r.json()


def cuerpo(est=None, asig=None, clave=None, titulo='Interrupción en clase', descripcion='Interrumpió varias veces.'):
    b = {'estudiante_id': (est or EST1).id, 'titulo': titulo, 'descripcion': descripcion,
         'tipo': 'conducta', 'gravedad': 'leve'}
    if asig is not None:
        b['asignatura_id'] = asig
    if clave is not None:
        b['client_request_id'] = clave
    return b


def n_reportes():
    db.expire_all()
    return db.query(M.ReporteConducta).count()


def n_notif():
    db.expire_all()
    return db.query(M.Notificacion).count()


def rep(rid):
    db.expire_all()
    return db.get(M.ReporteConducta, rid)


print('\n=== O. OPCIONES DEL SELECTOR ===')
check('O-01 profesor con VARIAS materias: troncal y optativa, solo las suyas, activas y del curso',
      opciones(JULIO, EST1) == (200, ['Lengua Española', 'Literatura y Sociedad (Optativa HLM)']), opciones(JULIO, EST1))
check('O-02 profesor con UNA materia: solo esa', opciones(ANA, EST1) == (200, ['Matemática']), opciones(ANA, EST1))
check('O-03 Dirección: las materias con asignación activa del curso del estudiante (sin retiradas ni inactivas)',
      opciones(DIR, EST1) == (200, ['Lengua Española', 'Literatura y Sociedad (Optativa HLM)', 'Matemática']),
      opciones(DIR, EST1))
check('O-04 cambio de estudiante: otro curso, otras opciones', opciones(DIR, EST2) == (200, ['Ciencias Sociales']),
      opciones(DIR, EST2))
check('O-05 profesor sin asignación en el curso del estudiante: 403', opciones(JULIO, EST2)[0] == 403, opciones(JULIO, EST2))
check('O-06 estudiante de otro colegio: 404 (profesor y Dirección)',
      opciones(JULIO, EST_B)[0] == 404 and opciones(DIR, EST_B)[0] == 404, '')
check('O-07 «Julio Sena» del otro colegio ve solo su materia y no ve estudiantes de este colegio',
      opciones(JULIO_B, EST_B) == (200, ['Lengua Española']) and opciones(JULIO_B, EST1)[0] == 404, '')
check('O-08 Dirección del otro colegio no ve este estudiante (404)', opciones(DIR_B, EST1)[0] == 404, '')

print('\n=== C. CREAR ===')
r = client.post('/api/reportes', json=cuerpo(asig=LE.id), headers=h(JULIO))
ID_LE = r.json().get('id')
check('C-01 profesor con troncal: 201, guarda asignatura_id y el nombre',
      r.status_code == 201 and rep(ID_LE).asignatura_id == LE.id and rep(ID_LE).asignatura_nombre == 'Lengua Española',
      r.text)
r = client.post('/api/reportes', json=cuerpo(asig=OPT.id, titulo='En la optativa'), headers=h(JULIO))
ID_OPT = r.json().get('id')
check('C-02 profesor con optativa: 201 y se guarda',
      r.status_code == 201 and rep(ID_OPT).asignatura_nombre == 'Literatura y Sociedad (Optativa HLM)', r.text)
r = client.post('/api/reportes', json=cuerpo(asig=MAT.id, titulo='Una materia'), headers=h(ANA))
check('C-03 profesor con una sola materia: 201', r.status_code == 201 and rep(r.json()['id']).asignatura_id == MAT.id, r.text)
generales = []
for valor in (None, 0, '', '0'):
    b = cuerpo(titulo='General %r' % (valor,))
    if valor is not None:
        b['asignatura_id'] = valor
    rg = client.post('/api/reportes', json=b, headers=h(JULIO))
    generales.append((rg.status_code, rep(rg.json()['id']).asignatura_id if rg.status_code == 201 else 'x'))
ID_GENERAL = rg.json().get('id')
check('C-04 reporte general (sin campo, null, 0, "", "0"): 201 sin asignatura',
      generales == [(201, None)] * 4, generales)
r = client.post('/api/reportes', json=cuerpo(asig=MAT.id, titulo='Dirección'), headers=h(DIR))
check('C-05 Dirección con una materia del curso: 201', r.status_code == 201, r.text)

antes_r, antes_n = n_reportes(), n_notif()
rechazos = {
    'materia de OTRO profesor del curso': (JULIO, cuerpo(asig=MAT.id), 400),
    'asignación retirada': (JULIO, cuerpo(asig=MUS.id), 400),
    'asignatura inactiva': (JULIO, cuerpo(asig=VIEJA.id), 400),
    'asignatura de OTRO colegio': (JULIO, cuerpo(asig=LE_B.id), 404),
    'ID inexistente': (JULIO, cuerpo(asig=987654), 404),
    'ID negativo': (JULIO, cuerpo(asig=-1), 404),
    'texto': (JULIO, cuerpo(asig='abc'), 400),
    'booleano': (JULIO, cuerpo(asig=True), 400),
    'decimal': (JULIO, cuerpo(asig=1.5), 400),
    'lista': (JULIO, cuerpo(asig=[LE.id]), 400),
    'Dirección: materia de otro curso': (DIR, cuerpo(asig=SOLO_B.id), 400),
    'cambio de estudiante con la materia del anterior': (DIR, cuerpo(est=EST2, asig=LE.id), 400),
    '«Julio Sena» de otro colegio con la materia de este': (JULIO_B, cuerpo(est=EST_B, asig=LE.id), 404),
    'Dirección de otro colegio con materia de este': (DIR_B, cuerpo(est=EST_B, asig=MAT.id), 404),
}
mal = []
for nombre, (u, b, esperado) in rechazos.items():
    rr = client.post('/api/reportes', json=b, headers=h(u))
    if rr.status_code != esperado:
        mal.append((nombre, rr.status_code, rr.text[:120]))
check('C-06 IDs manipulados, de otro colegio/curso/profesor, retirados o inactivos: rechazados (%d casos)'
      % len(rechazos), not mal, mal)
check('C-07 ...sin registros parciales ni notificaciones', n_reportes() == antes_r and n_notif() == antes_n,
      (n_reportes(), antes_r, n_notif(), antes_n))

print('\n=== I. DOBLE ENVÍO ===')
K1 = str(uuid.uuid4())
r1 = client.post('/api/reportes', json=cuerpo(asig=LE.id, clave=K1, titulo='Con clave'), headers=h(JULIO))
ID_K1 = r1.json().get('id')
avisos_k1 = n_notif()
r2 = client.post('/api/reportes', json=cuerpo(asig=LE.id, clave=K1, titulo='Con clave'), headers=h(JULIO))
check('I-01 doble clic / respuesta perdida: mismo reporte (200, reintento), sin duplicar ni notificar otra vez',
      r1.status_code == 201 and r2.status_code == 200 and r2.json().get('id') == ID_K1
      and r2.json().get('reintento') is True and n_notif() == avisos_k1, (r1.text, r2.text))
antes_r, antes_n = n_reportes(), n_notif()
r3 = client.post('/api/reportes', json=cuerpo(asig=OPT.id, clave=K1, titulo='Con clave'), headers=h(JULIO))
r4 = client.post('/api/reportes', json=cuerpo(clave=K1, titulo='Con clave'), headers=h(JULIO))
K2 = str(uuid.uuid4())
r5 = client.post('/api/reportes', json=cuerpo(clave=K2, titulo='Sin materia primero'), headers=h(JULIO))
r6 = client.post('/api/reportes', json=cuerpo(asig=LE.id, clave=K2, titulo='Sin materia primero'), headers=h(JULIO))
check('I-02 misma clave con OTRA materia: 409', r3.status_code == 409, r3.text)
check('I-03 misma clave pasando de CON materia a SIN materia: 409', r4.status_code == 409, r4.text)
check('I-04 misma clave pasando de SIN materia a CON materia: 409', r5.status_code == 201 and r6.status_code == 409,
      (r5.text, r6.text))
check('I-05 ...ninguno crea reportes ni notifica, y el original no cambia',
      n_reportes() == antes_r + 1 and rep(ID_K1).asignatura_id == LE.id and rep(r5.json()['id']).asignatura_id is None,
      (n_reportes(), antes_r))
check('I-06 sin materia, la huella es EXACTAMENTE la de antes (5 elementos)',
      rep(r5.json()['id']).client_request_hash == hashlib.sha256(json.dumps(
          [EST1.id, 'Sin materia primero', 'Interrumpió varias veces.', 'conducta', 'leve'],
          ensure_ascii=False).encode('utf-8')).hexdigest(), '')
check('I-07 con materia, la huella incluye su ID validado de forma inequívoca',
      rep(ID_K1).client_request_hash == APP._huella_reporte(EST1.id, 'Con clave', 'Interrumpió varias veces.',
                                                            'conducta', 'leve', LE.id)
      and APP._huella_reporte(EST1.id, 'a', 'b', 'conducta', 'leve', LE.id)
      != APP._huella_reporte(EST1.id, 'a', 'b', 'conducta', 'leve', OPT.id)
      and APP._huella_reporte(EST1.id, 'a', 'b', 'conducta', 'leve', LE.id)
      != APP._huella_reporte(EST1.id, 'a', 'b', 'conducta', 'leve'), '')
id_viejo = [x[0] for x in LEGACY if x[9] == '2026-0002'][0]
rv = client.post('/api/reportes', json=cuerpo(clave=CLAVE_VIEJA, titulo='Antiguo con clave', descripcion='Texto antiguo'),
                 headers=h(JULIO))
rv2 = client.post('/api/reportes', json=cuerpo(asig=LE.id, clave=CLAVE_VIEJA, titulo='Antiguo con clave',
                                               descripcion='Texto antiguo'), headers=h(JULIO))
check('I-08 reporte anterior a la migración reintentado sin materia: el mismo reporte (200)',
      rv.status_code == 200 and rv.json().get('id') == id_viejo, rv.text)
check('I-09 ...y con materia: 409', rv2.status_code == 409, rv2.text)

# Carrera determinista: otra petición con la misma clave gana entre la consulta previa y el commit.
_orig = APP._generar_numero_reporte


def carrera(clave, asig_ganador):
    def _gana(db_, colegio_id):
        s2 = SessionLocal()
        try:
            b = cuerpo(clave=clave, asig=asig_ganador.id, titulo='Carrera')
            s2.add(M.ReporteConducta(colegio_id=colegio_id, estudiante_id=EST1.id, reportado_por=JULIO.id,
                                     titulo=b['titulo'], descripcion=b['descripcion'], tipo='conducta', gravedad='leve',
                                     estado='pendiente', numero_reporte='GANADOR', client_request_id=clave,
                                     asignatura_id=asig_ganador.id, asignatura_nombre=asig_ganador.nombre,
                                     client_request_hash=APP._huella_reporte(
                                         EST1.id, b['titulo'], b['descripcion'], 'conducta', 'leve', asig_ganador.id)))
            s2.commit()
        finally:
            s2.close()
        return _orig(db_, colegio_id)
    return _gana


K3, K4 = str(uuid.uuid4()), str(uuid.uuid4())
APP._generar_numero_reporte = carrera(K3, LE)
try:
    rc = client.post('/api/reportes', json=cuerpo(clave=K3, asig=LE.id, titulo='Carrera'), headers=h(JULIO))
finally:
    APP._generar_numero_reporte = _orig
APP._generar_numero_reporte = carrera(K4, LE)
try:
    rc2 = client.post('/api/reportes', json=cuerpo(clave=K4, asig=OPT.id, titulo='Carrera'), headers=h(JULIO))
finally:
    APP._generar_numero_reporte = _orig
db.expire_all()
check('I-10 carrera con la misma materia: 200 con el reporte ganador, uno solo',
      rc.status_code == 200 and rc.json().get('numero_reporte') == 'GANADOR'
      and db.query(M.ReporteConducta).filter_by(client_request_id=K3).count() == 1, rc.text)
check('I-11 carrera con OTRA materia: 409 y sigue habiendo uno solo',
      rc2.status_code == 409 and db.query(M.ReporteConducta).filter_by(client_request_id=K4).count() == 1, rc2.text)

# Carrera REAL: 8 peticiones HTTP simultáneas con la misma clave y materia.
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
APP._generar_numero_reporte = lambda db_, cid: (time.sleep(0.4), _orig(db_, cid))[1]
K5 = str(uuid.uuid4())
barrera = threading.Barrier(8, timeout=30)
resultados = []
CAB = dict(h(JULIO), **{'Content-Type': 'application/json'})
DATOS = json.dumps(cuerpo(clave=K5, asig=OPT.id, titulo='Carrera real')).encode('utf-8')


def enviar():
    req = urllib.request.Request('http://127.0.0.1:%d/api/reportes' % PORT, method='POST', data=DATOS, headers=CAB)
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
filas = db.query(M.ReporteConducta).filter_by(client_request_id=K5).all()
avisos = db.query(M.Notificacion).filter_by(evento_key='reporte:%d:creado' % filas[0].id).count() if filas else -1
check('I-12 8 peticiones simultáneas con materia: un solo reporte (1 × 201, 7 × 200, mismo id) y con su materia',
      len(filas) == 1 and sorted(s for s, _ in resultados) == [200] * 7 + [201]
      and {j.get('id') for _, j in resultados} == {filas[0].id} and filas[0].asignatura_id == OPT.id,
      (len(filas), sorted(s for s, _ in resultados)))
check('I-13 ...un solo conjunto de notificaciones', avisos == 3, avisos)   # Dirección ×2 + coordinación

print('\n=== R. RENOMBRADO POSTERIOR DE LA MATERIA ===')
db.query(M.Asignatura).filter_by(id=LE.id).update({'nombre': 'Lengua Española y Literatura'})
db.commit()
lista = {x['id']: x for x in client.get('/api/reportes', headers=h(DIR)).json()}
check('R-01 el reporte conserva el nombre guardado al crearlo',
      rep(ID_LE).asignatura_nombre == 'Lengua Española' and lista[ID_LE]['asignatura_nombre'] == 'Lengua Española',
      lista.get(ID_LE))
check('R-02 las opciones del selector ya muestran el nombre nuevo',
      'Lengua Española y Literatura' in opciones(JULIO, EST1)[1], opciones(JULIO, EST1))


def texto_pdf(rid, u=JULIO, nombre=None):
    r = client.get('/api/reportes/%d/pdf' % rid, headers=h(u))
    assert r.status_code == 200, r.text
    if nombre:
        open(os.path.join(OUT, nombre), 'wb').write(r.content)
    return r.content, pymupdf.open(stream=r.content, filetype='pdf')[0].get_text()


print('\n=== P. PDF ===')
_, t = texto_pdf(ID_LE, nombre='reporte_con_asignatura.pdf')
check('P-01 con materia: «Reportado por» y «Asignatura del reporte» con el nombre GUARDADO (no el renombrado)',
      'REPORTADO POR:' in t and 'Julio Sena' in t and 'ASIGNATURA DEL REPORTE:' in t and 'Lengua Española' in t
      and 'y Literatura' not in t, t[-500:])
_, t = texto_pdf(ID_OPT, nombre='reporte_con_optativa.pdf')
check('P-02 con optativa', 'Literatura y Sociedad (Optativa HLM)' in t.replace('\n', ' '), '')
_, t = texto_pdf(ID_GENERAL, nombre='reporte_general.pdf')
check('P-03 reporte general: sin línea de asignatura', 'REPORTADO POR:' in t and 'ASIGNATURA DEL REPORTE' not in t, '')
id_antiguo = [x[0] for x in LEGACY if x[9] == '2026-0001'][0]
_, t = texto_pdf(id_antiguo, nombre='reporte_antiguo.pdf')
check('P-04 reporte antiguo: sin asignatura y sin materias deducidas del autor',
      'ASIGNATURA DEL REPORTE' not in t and not any(n in t for n in ('Lengua', 'Literatura', 'Matemática')), '')
# Nombres largos: autor y materia (100 caracteres, el máximo de la columna).
# El caso real más extremo: longitudes MÁXIMAS de las columnas (materia 100, nombre y apellido 50 cada
# uno) y en mayúsculas, que es lo más ancho que se escribe. El ajuste a varias líneas de textos que ni
# así caben lo cubre test_reporte_pdf_autoria.py (generador).
LARGO = asignatura(colA, 'FORMACIÓN INTEGRAL HUMANA Y RELIGIOSA CON ORIENTACIÓN VOCACIONAL, ÉTICA Y PROYECTO DE '
                         'VIDA ESCOLAR', 'FIHR')
PROF_L = usuario(colA, 'prof_largo', 'MARÍA DE LOS ÁNGELES ALTAGRACIA DEL CARMEN ROSARIO',
                 'FERNÁNDEZ DE LA ROSA SANTOS HERNÁNDEZ PEÑA MATOS', 'profesor')
assert 95 <= len(LARGO.nombre) <= 100 and 45 <= len(PROF_L.nombre) <= 50 and 45 <= len(PROF_L.apellido) <= 50
asignar(colA, anoA, PROF_L, cur1, LARGO)
db.commit()
rl = client.post('/api/reportes', json=cuerpo(asig=LARGO.id, titulo='Nombres largos'), headers=h(PROF_L))
pdf_l, t = texto_pdf(rl.json()['id'], u=PROF_L, nombre='reporte_nombres_largos.pdf')
pag = pymupdf.open(stream=pdf_l, filetype='pdf')[0]
ws = pag.get_text('words')
plano = ''.join(t.split())
y_estado = min(w[1] for w in ws if w[4] == 'ESTADO:')
# La barra «Estado / Generado» empieza en su propia línea: la franja es todo lo que queda por encima
# (el valor «Pendiente…» usa letra mayor y su caja empieza un poco antes que la etiqueta).
linea_estado = min(w[1] for w in ws if abs(w[3] - [x for x in ws if x[4] == 'ESTADO:'][0][3]) < 3)
banda = [w for w in ws if w[1] < linea_estado - 1 and w[1] >= min(x[1] for x in ws if x[4] == 'REPORTADO')]
check('P-05 nombres de longitud máxima: autor y materia completos, dentro de márgenes, sin superponer «Estado»',
      ''.join(LARGO.nombre.split()) in plano and ''.join((PROF_L.nombre + PROF_L.apellido).split()) in plano
      and len({round(w[1]) for w in banda}) >= 2 and all(w[2] <= pag.rect.width - 36 + 0.5 for w in ws)
      and max(w[3] for w in banda) <= linea_estado, (len({round(w[1]) for w in banda}), max(w[3] for w in banda), linea_estado))

print('\n=== Z. NADA MÁS CAMBIA ===')
db.expire_all()
check('Z-01 los reportes antiguos siguen intactos y sin asignatura',
      legacy() == LEGACY and all(rep(x[0]).asignatura_id is None for x in LEGACY), legacy())
check('Z-02 las asignaciones docentes no cambiaron (salvo la que esta prueba añadió para P-05)',
      [x for x in asignaciones() if x[1] != PROF_L.id] == ASIGNACIONES, '')
check('Z-03 nada se envió a los padres',
      db.query(M.ReporteConducta).filter_by(enviado_padres=True).count() == 0
      and db.query(M.HistorialReportePadres).count() == 0, '')

ctx.__exit__(None, None, None)
db.close()
engine.dispose()
if PG:
    PG.eliminar()
    _c = _pg.connect(PG_SERVER)
    _cur = _c.cursor()
    _cur.execute('SELECT 1 FROM pg_database WHERE datname = %s', [PG.nombre])
    _sigue = _cur.fetchone() is not None
    _c.close()
    _c = _pg.connect(_ord)
    _final = PGT.huella_base(_c)
    _c.close()
    check('S-04 al terminar se eliminó SOLO la base temporal de la prueba', not _sigue, PG.nombre)
    check('S-05 la base preexistente sigue idéntica al final de la prueba', _final == HUELLA_ORD, '')
ok = sum(1 for _, r in RES if r)
print('\nPDFs en: %s' % OUT)
print('RESULTADO ASIGNATURA DEL REPORTE: %d PASARON / %d FALLARON' % (ok, len(RES) - ok))
sys.exit(0 if ok == len(RES) else 1)
