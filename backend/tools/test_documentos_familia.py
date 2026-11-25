# -*- coding: utf-8 -*-
"""
EducaOne — FAM-DOC-1: Reporte del Período compartido con las familias.

Comprueba, solo con datos y contactos SINTÉTICOS (no se envía ningún mensaje):
  - migración: las tres tablas nuevas se crean en el arranque sobre una base
    con datos existentes, que no cambian;
  - contactos: un contacto con nombre pero sin teléfono no se sugiere;
  - permisos y aislamiento entre colegios, divisiones y estudiantes;
  - copia fija: abrir el enlace no recalcula; cambiar notas no cambia el
    documento compartido; versión nueva solo a pedido;
  - anulación, reintentos, doble clic y peticiones simultáneas sin duplicados;
  - límite de generación simultánea (503 «ocupado» sin dejar nada a medias);
  - página pública: tarjeta genérica, cabeceras privadas, aviso de reenvío;
  - las descargas existentes siguen igual (mismo PDF que el individual);
  - persistencia tras reiniciar el proceso (otro proceso abre el mismo enlace).

Base temporal aislada. Nunca producción.

Uso:
    cd <carpeta temporal>
    python <repo>/backend/tools/test_documentos_familia.py                 # SQLite temporal
    EO_TEST_PG_URL=postgresql://eo_test@127.0.0.1:<puerto>/eo_test_famdoc \\
    EO_TEST_PG_DATADIR=<directorio de datos del clúster DE PRUEBA> \\
        python <repo>/backend/tools/test_documentos_familia.py             # PostgreSQL de prueba
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import threading

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(BK, "tools"))

os.environ.setdefault('ENLACE_FAMILIA_SECRET', 'secreto-de-prueba-famdoc-no-produccion')
os.environ.setdefault('DISABLE_GLOBAL_RATE_LIMIT', 'true')

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
    TMP = aislar_base_de_datos('fam_doc1')

from database import engine, SessionLocal  # noqa: E402
from test_utils import verificar_engine_aislado  # noqa: E402
from sqlalchemy import inspect, text  # noqa: E402

if PG_URL:
    esperado = os.path.normcase(os.path.realpath(os.environ['EO_TEST_PG_DATADIR']))
    with engine.connect() as cn:
        real = os.path.normcase(os.path.realpath(cn.execute(text('SHOW data_directory')).scalar()))
        tablas = cn.execute(text("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")).scalar()
    if real != esperado:
        raise SystemExit('El PostgreSQL conectado NO es el clúster de prueba (%s). No se ejecuta.' % real)
    if tablas:
        raise SystemExit('La base de prueba no está vacía (%d tablas). No se ejecuta.' % tablas)
    print('Motor: PostgreSQL de prueba (%s:%s/%s)' % (engine.url.host, engine.url.port, engine.url.database))
else:
    verificar_engine_aislado(engine, TMP)
    print('Motor: SQLite temporal')

from fastapi.testclient import TestClient  # noqa: E402
import models as M  # noqa: E402
import app as APP  # noqa: E402
import documentos_familia as FAMDOC  # noqa: E402
from auth import create_token  # noqa: E402

RES = []


def check(nombre, ok, detalle=''):
    RES.append((nombre, bool(ok)))
    print(('  OK  ' if ok else '  FALLA ') + nombre + ('' if ok else '  -> ' + str(detalle)[:400]))


NUEVAS = ('documentos_familia_eventos', 'documentos_familia_archivos', 'documentos_familia')

# ── Esquema ANTERIOR: todas las tablas salvo las tres nuevas ──
M.Base.metadata.create_all(bind=engine)
with engine.begin() as conn:
    for t in NUEVAS:
        conn.execute(text('DROP TABLE %s' % t))
check('esquema anterior sin las tablas nuevas',
      not (set(NUEVAS) & set(inspect(engine).get_table_names())))

db = SessionLocal()


def add(o):
    db.add(o)
    db.flush()
    return o


def usuario(col, username, role, nivel=None):
    return add(M.Usuario(colegio_id=col.id if col else None, username=username, password_hash='x', nombre=username,
                         apellido='T', role=role, activo=True, must_change_password=False, token_version=0,
                         nivel_asignado=nivel))


COL = add(M.Colegio(nombre='Colegio Sintético Uno', codigo='cs1', activo=True))
OTRO = add(M.Colegio(nombre='Colegio Sintético Dos', codigo='cs2', activo=True))
add(M.ConfiguracionColegio(colegio_id=COL.id, nombre='Colegio Sintético Uno'))
add(M.ConfiguracionColegio(colegio_id=OTRO.id, nombre='Colegio Sintético Dos'))
ANO = add(M.AnoEscolar(colegio_id=COL.id, nombre='2026-2027', activo=True, periodo_activo=1))
ANO2 = add(M.AnoEscolar(colegio_id=OTRO.id, nombre='2026-2027', activo=True, periodo_activo=1))
T1 = add(M.Tanda(colegio_id=COL.id, nombre='Matutina', hora_inicio='07:30', hora_fin='12:30', activo=True))
T2 = add(M.Tanda(colegio_id=OTRO.id, nombre='Matutina', hora_inicio='07:30', hora_fin='12:30', activo=True))
GS = add(M.Grado(colegio_id=COL.id, nombre='6to Secundaria', nivel='secundaria', orden=6))
GP = add(M.Grado(colegio_id=COL.id, nombre='3ro Primaria', nivel='primaria', orden=3))
GS2 = add(M.Grado(colegio_id=OTRO.id, nombre='6to Secundaria', nivel='secundaria', orden=6))
CUR = add(M.Curso(colegio_id=COL.id, nombre='A', grado_id=GS.id, tanda_id=T1.id, ano_escolar_id=ANO.id, activo=True))
CURB = add(M.Curso(colegio_id=COL.id, nombre='B', grado_id=GS.id, tanda_id=T1.id, ano_escolar_id=ANO.id, activo=True))
CURP = add(M.Curso(colegio_id=COL.id, nombre='A', grado_id=GP.id, tanda_id=T1.id, ano_escolar_id=ANO.id, activo=True))
CUR2 = add(M.Curso(colegio_id=OTRO.id, nombre='A', grado_id=GS2.id, tanda_id=T2.id, ano_escolar_id=ANO2.id, activo=True))

DIR = usuario(COL, 'direccion', 'direccion')
COORD = usuario(COL, 'coord', 'coordinador')
COORD_P = usuario(COL, 'coord_p', 'coordinador', 'primaria')
COORD_S = usuario(COL, 'coord_s', 'coordinador', 'secundaria')
PROF = usuario(COL, 'prof', 'profesor')
SECRE = usuario(COL, 'secre', 'secretaria')
PSI = usuario(COL, 'psi', 'psicologia')
DIR2 = usuario(OTRO, 'dir_otro', 'direccion')
SUPER = usuario(None, 'superadmin', 'superadmin')

MATERIAS = ['Lengua Española', 'Matemática', 'Inglés']
ASIGS = [add(M.Asignatura(colegio_id=COL.id, nombre=n, codigo=n[:3].upper(), area='X', activo=True)) for n in MATERIAS]
ASIG2 = add(M.Asignatura(colegio_id=OTRO.id, nombre='Lengua Española', codigo='LEN', area='X', activo=True))
for a in ASIGS:
    add(M.AsignacionProfesor(colegio_id=COL.id, profesor_id=PROF.id, curso_id=CUR.id, asignatura_id=a.id,
                             ano_escolar_id=ANO.id, activo=True))
add(M.AsignacionProfesor(colegio_id=OTRO.id, profesor_id=DIR2.id, curso_id=CUR2.id, asignatura_id=ASIG2.id,
                         ano_escolar_id=ANO2.id, activo=True))

# Contactos sintéticos (números de ejemplo, nadie recibe nada).
FICHAS = [
    # apellido, nombre, padre(nombre, tel), madre(nombre, tel), tutor(nombre, tel)
    ('Pérez', 'Ana', ('Pedro Pérez', ''), ('Lucía Gómez', '809-555-2048'), (None, None)),
    ('Gómez', 'Luis', ('Raúl Gómez', '(829) 555-1111'), ('Marta Ruiz', '849 555 2222'), ('Tío Juan', '+1 809 555 7132')),
    ('Santos', 'Carla', ('Ramón Santos', '8095553333'), (None, None), ('Abuela Rosa', '')),  # tutor con nombre SIN teléfono
    ('Díaz', 'Mateo', (None, None), (None, None), (None, None)),                              # sin contactos
    ('Ruiz', 'Elena', ('Padre Ruiz', '555-12'), ('Madre Ruiz', '1234'), (None, None)),       # teléfonos inválidos
]
ESTS = []
for i, (ap, nom, pa, ma, tu) in enumerate(FICHAS):
    e = add(M.Estudiante(colegio_id=COL.id, nombre=nom, apellido=ap, curso_id=CUR.id, activo=True, no_lista=i + 1,
                         matricula='M-%03d' % (i + 1),
                         nombre_padre=pa[0], telefono_padre=pa[1], nombre_madre=ma[0], telefono_madre=ma[1],
                         tutor=tu[0], telefono_tutor=tu[1], parentesco_tutor=('Tío' if tu[0] else None),
                         email='estudiante%d@ejemplo.invalid' % i))
    ESTS.append(e)
    for j, a in enumerate(ASIGS):
        if nom == 'Carla' and j == 1:
            continue  # Carla: Matemática pendiente (informativo, no bloquea)
        for comp in range(1, 5):
            add(M.CalificacionSecundaria(colegio_id=COL.id, estudiante_id=e.id, asignatura_id=a.id,
                                         ano_escolar_id=ANO.id, competencia_numero=comp,
                                         p1=80 + i + j + comp, p2=70 + i + comp))
EB = add(M.Estudiante(colegio_id=COL.id, nombre='Bruno', apellido='Otro', curso_id=CURB.id, activo=True, no_lista=1,
                      telefono_padre='8095550000', nombre_padre='P'))
EP = add(M.Estudiante(colegio_id=COL.id, nombre='Pía', apellido='Primaria', curso_id=CURP.id, activo=True, no_lista=1))
E2 = add(M.Estudiante(colegio_id=OTRO.id, nombre='Zoe', apellido='Ajena', curso_id=CUR2.id, activo=True, no_lista=1,
                      nombre_madre='M', telefono_madre='8095559999'))
for comp in range(1, 5):
    add(M.CalificacionSecundaria(colegio_id=OTRO.id, estudiante_id=E2.id, asignatura_id=ASIG2.id,
                                 ano_escolar_id=ANO2.id, competencia_numero=comp, p1=90))
db.commit()

# Huella de datos existentes (no deben cambiar con la migración).
def _huella_existente():
    with engine.connect() as cn:
        filas = cn.execute(text('SELECT id, estudiante_id, asignatura_id, competencia_numero, p1, p2 '
                                'FROM calificaciones_secundaria ORDER BY id')).fetchall()
        ests = cn.execute(text('SELECT id, nombre, telefono_padre, telefono_madre, telefono_tutor '
                               'FROM estudiantes ORDER BY id')).fetchall()
    return hashlib.sha256(repr((filas, ests)).encode()).hexdigest()


HUELLA_ANTES = _huella_existente()

# ── Arranque (lifespan): migración ──
with TestClient(APP.app) as _c:
    pass
insp = inspect(engine)
check('migración: tablas nuevas creadas en el arranque', set(NUEVAS) <= set(insp.get_table_names()))
idx_nombres = {i['name'] for i in insp.get_indexes('documentos_familia')}
uqs = {u['name'] for u in insp.get_unique_constraints('documentos_familia')}
check('migración: índice único parcial del documento activo', 'uq_doc_familia_activo' in idx_nombres, idx_nombres)
check('migración: unicidad de versión y de enlace', {'uq_doc_familia_version', 'uq_doc_familia_token'} <= (uqs | idx_nombres),
      (uqs, idx_nombres))
check('migración: datos existentes intactos', _huella_existente() == HUELLA_ANTES)
with TestClient(APP.app) as _c:
    pass
check('migración: segundo arranque sin cambios ni errores', _huella_existente() == HUELLA_ANTES)

client = TestClient(APP.app)


def H(u):
    return {'Authorization': 'Bearer ' + create_token(u)}


def preparar(u, ids, curso=None, periodo=1):
    return client.post('/api/documentos-familia/preparar', headers=H(u),
                       json={'curso_id': (curso or CUR).id, 'periodo': periodo, 'estudiante_ids': ids})


def listar(u, curso=None, periodo=1):
    return client.get('/api/documentos-familia/curso/%d?periodo=%d' % ((curso or CUR).id, periodo), headers=H(u))


def ndocs():
    with engine.connect() as cn:
        return (cn.execute(text('SELECT count(*) FROM documentos_familia')).scalar(),
                cn.execute(text('SELECT count(*) FROM documentos_familia_archivos')).scalar())


def ruta(url):
    return '/' + url.split('/', 3)[3]


# ═════════ 1. Contactos ═════════
print('\n1. Contactos')
check('teléfono RD de 10 dígitos → con 1 delante', FAMDOC.telefono_whatsapp('809-555-2048') == '18095552048')
check('teléfono con +1 → igual', FAMDOC.telefono_whatsapp('+1 809 555 7132') == '18095557132')
check('teléfono corto → no utilizable', FAMDOC.telefono_whatsapp('555-12') is None)
check('10 dígitos sin código de país (no RD) → no utilizable', FAMDOC.telefono_whatsapp('3055551234') is None)
r = listar(DIR)
check('listar 200', r.status_code == 200, r.text)
L = {e['estudiante_id']: e for e in r.json()['estudiantes']}
ana, luis, carla, mateo, elena = (L[e.id] for e in ESTS)
check('Ana: el padre tiene nombre sin teléfono → se sugiere la madre', ana['contacto_sugerido'] == 'madre', ana)
check('Luis: tutor con teléfono → tutor', luis['contacto_sugerido'] == 'tutor', luis)
check('Carla: tutor con nombre SIN teléfono no se sugiere → padre', carla['contacto_sugerido'] == 'padre', carla)
check('Mateo: sin contactos → ninguno', mateo['contacto_sugerido'] is None and mateo['contactos'] == [], mateo)
check('Elena: teléfonos inválidos → ninguno, pero se listan para corregir',
      elena['contacto_sugerido'] is None and len(elena['contactos']) == 2 and not any(c['valido'] for c in elena['contactos']))
check('el correo del estudiante no aparece como contacto',
      'ejemplo.invalid' not in json.dumps(r.json()))
check('notas pendientes informativas (Carla: 1)', carla['notas_pendientes'] == 1 and ana['notas_pendientes'] == 0)
check('sin documentos todavía', all(e['documento'] is None for e in L.values()))

# ═════════ 2. Permisos y aislamiento ═════════
print('\n2. Permisos y aislamiento')
for u, nombre in ((PROF, 'profesor'), (SECRE, 'secretaría'), (PSI, 'psicología')):
    check('%s no puede listar ni preparar (403)' % nombre,
          listar(u).status_code == 403 and preparar(u, [ESTS[0].id]).status_code == 403)
check('coordinación de Primaria no puede en un curso de Secundaria (403)',
      listar(COORD_P).status_code == 403 and preparar(COORD_P, [ESTS[0].id]).status_code == 403)
check('coordinación de Secundaria sí (200)', listar(COORD_S).status_code == 200)
check('otro colegio: el curso no existe para él (404)',
      listar(DIR2).status_code == 404 and preparar(DIR2, [ESTS[0].id]).status_code == 404)
r = preparar(DIR, [E2.id])
check('estudiante de otro colegio en mi curso → 404 sin revelar', r.status_code == 404, r.text)
r = preparar(DIR, [EB.id])
check('estudiante de otro curso → 404', r.status_code == 404 and r.json().get('motivo') == 'estudiante_fuera_del_curso', r.text)
r = preparar(DIR, [EP.id], curso=CURP)
check('curso de Primaria → 409 (el reporte aún no incluye Primaria)', r.status_code == 409
      and r.json().get('motivo') == 'nivel_no_soportado', r.text)
check('superadmin sin colegio → 403', listar(SUPER).status_code == 403)
check('sin sesión → 401', client.get('/api/documentos-familia/curso/%d?periodo=1' % CUR.id).status_code == 401)
check('período inválido → 400', listar(DIR, periodo=7).status_code == 400)
check('nada creado por los intentos rechazados', ndocs() == (0, 0), ndocs())

# ═════════ 3. Preparar: copia fija, idempotencia ═════════
print('\n3. Preparar')
IDS = [e.id for e in ESTS[:3]]
r = preparar(DIR, IDS)
check('preparar 3 → 200 y 3 creados', r.status_code == 200 and r.json()['creados'] == 3, r.text)
P1 = {e['estudiante_id']: e for e in r.json()['estudiantes']}
urls = {i: P1[i]['documento']['url'] for i in IDS}
check('cada enlace es distinto y sin datos personales', len(set(urls.values())) == 3 and all(
    re.search(r'/doc/[A-Za-z0-9_-]{43}$', u) and 'Ana' not in u and str(i) not in u.rsplit('/', 1)[1][:0] for i, u in urls.items()), urls)
check('no se guarda el enlace en la base (solo semilla y hash)', not any(
    u.rsplit('/', 1)[1] in json.dumps([list(map(str, f)) for f in
                                       engine.connect().execute(text('SELECT * FROM documentos_familia')).fetchall()])
    for u in urls.values()))
r2 = preparar(DIR, IDS)
check('repetir (doble clic/reintento) → 0 creados, mismos enlaces', r2.status_code == 200 and r2.json()['creados'] == 0
      and {e['estudiante_id']: e['documento']['url'] for e in r2.json()['estudiantes']} == urls, r2.text)
check('3 documentos y 3 PDF guardados', ndocs() == (3, 3), ndocs())
r3 = preparar(COORD, IDS)
check('otra persona del colegio ve los mismos enlaces (no duplica)', r3.json()['creados'] == 0
      and {e['estudiante_id']: e['documento']['url'] for e in r3.json()['estudiantes']} == urls)

# Simultáneas: 6 hilos piden lo mismo para 2 estudiantes nuevos.
IDS2 = [ESTS[3].id, ESTS[4].id]
res_hilos = []


def _hilo():
    res_hilos.append(TestClient(APP.app).post('/api/documentos-familia/preparar', headers=H(DIR),
                                              json={'curso_id': CUR.id, 'periodo': 1, 'estudiante_ids': IDS2}))


hs = [threading.Thread(target=_hilo) for _ in range(6)]
[h.start() for h in hs]
[h.join() for h in hs]
codigos = sorted(x.status_code for x in res_hilos)
ok_resp = [x for x in res_hilos if x.status_code == 200]
check('6 peticiones simultáneas → todas 200', codigos == [200] * 6, codigos)
check('… y una sola copia por estudiante', ndocs() == (5, 5) and sum(x.json()['creados'] for x in ok_resp) == 2, ndocs())
check('… con el mismo enlace para todas', len({json.dumps([e['documento']['url'] for e in x.json()['estudiantes']])
                                                for x in ok_resp}) == 1)

# Límite de generación simultánea.
_tomados = 0
while APP._FAMDOC_SEM.acquire(blocking=False):  # ocupar TODOS los turnos de generación
    _tomados += 1
_espera = APP._FAMDOC_ESPERA_SEG
APP._FAMDOC_ESPERA_SEG = 0.2
try:
    db2 = SessionLocal()
    nuevo = M.Estudiante(colegio_id=COL.id, nombre='Nora', apellido='Nueva', curso_id=CUR.id, activo=True, no_lista=9,
                         nombre_madre='M', telefono_madre='8095551234')
    db2.add(nuevo)
    db2.commit()
    NORA = nuevo.id
    db2.close()
    r = preparar(DIR, [NORA])
    check('servidor ocupado → 503 «ocupado» sin crear nada', r.status_code == 503 and r.json().get('motivo') == 'ocupado'
          and ndocs() == (5, 5), (r.status_code, r.text, ndocs()))
    r = preparar(DIR, IDS)
    check('… pero devolver los ya preparados no espera (200)', r.status_code == 200 and r.json()['creados'] == 0)
finally:
    for _ in range(_tomados):
        APP._FAMDOC_SEM.release()
    APP._FAMDOC_ESPERA_SEG = _espera
r = preparar(DIR, [NORA])
check('liberado → se prepara', r.status_code == 200 and r.json()['creados'] == 1 and ndocs() == (6, 6), r.text)

# ═════════ 4. Página pública y PDF ═════════
print('\n4. Página pública')
anon = TestClient(APP.app)
u_ana = ruta(urls[ESTS[0].id])
r = anon.get(u_ana)
cuerpo = r.text
cab = cuerpo.split('</head>')[0]
check('página 200', r.status_code == 200, r.status_code)
check('muestra estudiante, curso, período y notas', 'Ana' in cuerpo and 'Pérez' in cuerpo and 'Primer período' in cuerpo
      and 'Lengua Española' in cuerpo)
check('tarjeta de vista previa genérica: sin nombre ni notas del estudiante',
      'Ana' not in cab and 'Pérez' not in cab and not re.search(r'\b(8\d|9\d|7\d)\b', cab)
      and 'Reporte de notas disponible' in cab and 'Colegio Sintético Uno' in cab, cab)
check('aviso de reenvío visible', 'cualquier persona que lo reciba' in cuerpo)
check('sin vencimiento automático y anulable', 'sin vencimiento automático' in cuerpo and 'puede anularlo' in cuerpo)
check('sin scripts', '<script' not in cuerpo.lower())
check('cabeceras privadas (no-store, noindex, no-referrer)',
      'no-store' in r.headers.get('cache-control', '') and 'noindex' in r.headers.get('x-robots-tag', '')
      and r.headers.get('referrer-policy') == 'no-referrer', dict(r.headers))
check('no se puede incrustar (frame-ancestors / DENY)', r.headers.get('x-frame-options') == 'DENY')
rp = anon.get(u_ana + '/pdf')
rd = anon.get(u_ana + '/pdf?descargar=1')
check('PDF en línea', rp.status_code == 200 and rp.headers['content-type'] == 'application/pdf'
      and rp.headers['content-disposition'].startswith('inline') and rp.content[:4] == b'%PDF')
check('«Descargar PDF» → adjunto', rd.headers['content-disposition'].startswith('attachment')
      and rd.content == rp.content)
check('PDF también privado', 'no-store' in rp.headers.get('cache-control', '') and 'noindex' in rp.headers.get('x-robots-tag', ''))
anon.get(u_ana, headers={'User-Agent': 'WhatsApp/2.23.20.0 A'})
anon.get(u_ana, headers={'User-Agent': 'facebookexternalhit/1.1'})
d = {e['estudiante_id']: e for e in listar(DIR).json()['estudiantes']}[ESTS[0].id]['documento']
check('visitas contadas aparte de las vistas previas', d['visitas'] == 2 and d['descargas'] == 1 and d['vistas_previas'] == 2, d)
check('nada se marca entregado ni leído', not any(k in json.dumps(d).lower() for k in ('entregado', 'leido', 'leído')))
for mala in ('/doc/corto', '/doc/' + 'A' * 43, '/doc/' + 'A' * 43 + '/pdf', '/doc/%2e%2e%2fetc', '/doc/' + 'A' * 44):
    rr = anon.get(mala)
    check('enlace inválido %s… → 404 genérico' % mala[:12], rr.status_code == 404 and 'Colegio' not in rr.text, rr.status_code)
# Enlace de un documento no da acceso a otro.
u_luis = ruta(urls[ESTS[1].id])
check('cada enlace abre solo SU documento', 'Luis' in anon.get(u_luis).text and 'Ana' not in anon.get(u_luis).text)
# Otro secreto en el servidor → el enlace deja de valer (defensa HMAC).
_s = os.environ['ENLACE_FAMILIA_SECRET']
os.environ['ENLACE_FAMILIA_SECRET'] = 'otro-secreto'
check('con otro secreto el enlace no abre', anon.get(u_ana).status_code == 404)
os.environ['ENLACE_FAMILIA_SECRET'] = _s
check('con su secreto vuelve a abrir', anon.get(u_ana).status_code == 200)

# ═════════ 5. Formato: el PDF compartido es el mismo que el individual ═════════
print('\n5. Formato y descargas existentes')


def _norm(pdf):
    return re.sub(rb'/(CreationDate|ModDate) \(D:[^)]*\)|/ID\s*\[[^\]]*\]', b'', pdf)


ri = client.get('/api/calificaciones-secundaria/reporte-padres/curso/%d/pdf?periodo=1&estudiante_id=%d'
                % (CUR.id, ESTS[0].id), headers=H(DIR))
check('PDF compartido = PDF individual de siempre (salvo fecha e id interno)', _norm(ri.content) == _norm(rp.content))
for u, nombre in ((DIR, 'dirección'), (COORD, 'coordinación'), (PROF, 'profesor del curso'), (SECRE, 'secretaría')):
    rc = client.get('/api/calificaciones-secundaria/reporte-padres/curso/%d/pdf?periodo=1' % CUR.id, headers=H(u))
    check('reporte del curso sigue igual para %s (200 PDF)' % nombre, rc.status_code == 200 and rc.content[:4] == b'%PDF')
rt = client.get('/api/calificaciones/por-periodo/pdf?curso_id=%d&periodo=1' % CUR.id, headers=H(DIR))
check('tabla general PDF sigue (200)', rt.status_code == 200 and rt.content[:4] == b'%PDF')
rpp = client.get('/api/calificaciones/por-periodo?curso_id=%d&periodo=1' % CUR.id, headers=H(DIR))
check('tabla de notas sigue (200)', rpp.status_code == 200 and len(rpp.json()['estudiantes']) == 6)
rx = client.get('/api/calificaciones-secundaria/reporte-padres/curso/%d/pdf?periodo=1' % CUR2.id, headers=H(DIR))
check('reporte de un curso ajeno sigue en 404', rx.status_code == 404)
# Filas de la página = lo dibujado en el PDF = cálculo actual.
dbx = SessionLocal()
dirx = dbx.get(M.Usuario, DIR.id)
ctx = APP._famdoc_curso(dbx, dirx, CUR.id, 1)
filas_pdf = {}
APP.generar_reporte_periodo_pdf(dbx, dirx, ctx['curso'], ctx['ano'], 1, ctx['estudiantes'], ctx['config'],
                                filas_por_estudiante=filas_pdf)
filas_hoy = APP._famdoc_filas_actuales(dbx, dirx, ctx['curso'], ctx['ano'], 1, ctx['estudiantes'])
check('filas del PDF = filas calculadas para la página', filas_pdf == filas_hoy, (filas_pdf, filas_hoy))
dbx.close()

# ═════════ 6. Copia fija y versiones ═════════
print('\n6. Copia fija y versiones')
sha_antes = hashlib.sha256(anon.get(u_ana + '/pdf').content).hexdigest()
pag_antes = anon.get(u_ana).text
with engine.begin() as cn:
    cn.execute(text('UPDATE calificaciones_secundaria SET p1 = 55 WHERE estudiante_id = :e'), {'e': ESTS[0].id})
check('cambiar notas NO cambia el PDF compartido', hashlib.sha256(anon.get(u_ana + '/pdf').content).hexdigest() == sha_antes)
CELDA_55 = "<td class='n'>55</td>"
check('… ni la página', anon.get(u_ana).text == pag_antes and CELDA_55 not in anon.get(u_ana).text)
L = {e['estudiante_id']: e for e in listar(DIR).json()['estudiantes']}
check('la lista avisa que quedó desactualizado', L[ESTS[0].id]['desactualizado'] is True
      and L[ESTS[1].id]['desactualizado'] is False, (L[ESTS[0].id]['desactualizado'], L[ESTS[1].id]['desactualizado']))
r = preparar(DIR, [ESTS[0].id])
check('preparar de nuevo NO crea versión silenciosa', r.json()['creados'] == 0
      and r.json()['estudiantes'][0]['documento']['url'] == urls[ESTS[0].id])
doc_v1 = L[ESTS[0].id]['documento']['id']
rv = client.post('/api/documentos-familia/%d/version' % doc_v1, headers=H(DIR))
check('nueva versión explícita → v2', rv.status_code == 200 and rv.json()['version'] == 2 and rv.json()['creado'], rv.text)
rv2 = client.post('/api/documentos-familia/%d/version' % doc_v1, headers=H(DIR))
check('doble clic en «nueva versión» → la misma v2, sin v3', rv2.status_code == 200 and rv2.json()['documento_id']
      == rv.json()['documento_id'] and not rv2.json()['creado'], rv2.text)
L = {e['estudiante_id']: e for e in listar(DIR).json()['estudiantes']}
url_v2 = L[ESTS[0].id]['documento']['url']
check('v2 con enlace nuevo y al día', url_v2 != urls[ESTS[0].id] and L[ESTS[0].id]['desactualizado'] is False
      and L[ESTS[0].id]['documento']['version'] == 2)
check('v2 muestra las notas nuevas', CELDA_55 in anon.get(ruta(url_v2)).text)
viejo = anon.get(u_ana)
check('el enlace de v1 sigue mostrando lo compartido, con aviso de versión nueva',
      viejo.status_code == 200 and 'versión más reciente' in viejo.text and CELDA_55 not in viejo.text)
# Simultáneas sobre v2.
doc_v2 = L[ESTS[0].id]['documento']['id']
res_v = []


def _hilo_v():
    res_v.append(TestClient(APP.app).post('/api/documentos-familia/%d/version' % doc_v2, headers=H(DIR)))


hs = [threading.Thread(target=_hilo_v) for _ in range(5)]
[h.start() for h in hs]
[h.join() for h in hs]
with engine.connect() as cn:
    vers = cn.execute(text('SELECT version, estado FROM documentos_familia WHERE estudiante_id=:e ORDER BY version'),
                      {'e': ESTS[0].id}).fetchall()
check('5 «nueva versión» simultáneas → una sola v3 y un solo activo',
      [v for v, _ in vers] == [1, 2, 3] and [s for _, s in vers].count('activo') == 1
      and all(x.status_code == 200 for x in res_v), (vers, [x.status_code for x in res_v]))

# ═════════ 7. Anular ═════════
print('\n7. Anular')
doc_luis = L[ESTS[1].id]['documento']['id']
check('profesor no puede anular (403)', client.post('/api/documentos-familia/%d/anular' % doc_luis, headers=H(PROF)).status_code == 403)
check('otro colegio no ve el documento (404)',
      client.post('/api/documentos-familia/%d/anular' % doc_luis, headers=H(DIR2)).status_code == 404
      and client.post('/api/documentos-familia/%d/version' % doc_luis, headers=H(DIR2)).status_code == 404
      and client.post('/api/documentos-familia/%d/whatsapp' % doc_luis, headers=H(DIR2),
                      json={'contacto_rol': 'tutor'}).status_code == 404)
check('coordinación de Primaria no puede anular uno de Secundaria (403)',
      client.post('/api/documentos-familia/%d/anular' % doc_luis, headers=H(COORD_P)).status_code == 403)
ra = client.post('/api/documentos-familia/%d/anular' % doc_luis, headers=H(DIR), json={'motivo': 'Número equivocado'})
check('anular → 200', ra.status_code == 200 and ra.json()['estado'] == 'anulado', ra.text)
check('anular de nuevo → idempotente', client.post('/api/documentos-familia/%d/anular' % doc_luis, headers=H(DIR)).json()['ya_estaba'])
check('enlace anulado → 410 y PDF 410', anon.get(u_luis).status_code == 410 and anon.get(u_luis + '/pdf').status_code == 410)
check('la página de anulado no muestra datos', 'Luis' not in anon.get(u_luis).text)
r = preparar(DIR, [ESTS[1].id])
nuevo_luis = r.json()['estudiantes'][0]['documento']
check('preparar tras anular → versión nueva con otro enlace', r.json()['creados'] == 1 and nuevo_luis['version'] == 2
      and ruta(nuevo_luis['url']) != u_luis)
check('el enlace anulado sigue anulado', anon.get(u_luis).status_code == 410)
check('nueva versión de un anulado → 409', client.post('/api/documentos-familia/%d/version' % doc_luis,
                                                        headers=H(DIR)).status_code == 409)

# ═════════ 8. WhatsApp abierto (no es «enviado») ═════════
print('\n8. WhatsApp abierto')
doc_carla = L[ESTS[2].id]['documento']['id']
rw = client.post('/api/documentos-familia/%d/whatsapp' % doc_carla, headers=H(DIR), json={'contacto_rol': 'tutor'})
check('tutor sin teléfono → 400', rw.status_code == 400 and rw.json()['motivo'] == 'contacto_invalido', rw.text)
rw = client.post('/api/documentos-familia/%d/whatsapp' % doc_carla, headers=H(DIR), json={'contacto_rol': 'padre'})
check('padre con teléfono → anotado', rw.status_code == 200 and rw.json()['whatsapp_abierto'] == 1, rw.text)
d = {e['estudiante_id']: e for e in listar(DIR).json()['estudiantes']}[ESTS[2].id]['documento']
check('queda «WhatsApp abierto» con el contacto y 4 dígitos, sin «enviado»',
      d['whatsapp_abierto'] == 1 and d['ultimo_whatsapp']['contacto_rol'] == 'padre'
      and d['ultimo_whatsapp']['telefono_final'] == '3333' and d['estado'] == 'activo', d)
with engine.connect() as cn:
    tel = cn.execute(text("SELECT telefono_final FROM documentos_familia_eventos WHERE tipo='whatsapp_abierto'")).scalar()
check('el evento guarda solo los 4 últimos dígitos', tel == '3333')
check('anulado no admite WhatsApp (409)', client.post('/api/documentos-familia/%d/whatsapp' % doc_luis, headers=H(DIR),
                                                    json={'contacto_rol': 'tutor'}).status_code == 409)

# ═════════ 9. Auditoría ═════════
with engine.connect() as cn:
    acc = dict(cn.execute(text("SELECT accion, count(*) FROM logs_auditoria WHERE tabla='documentos_familia' GROUP BY accion")).fetchall()) \
        if 'logs_auditoria' in inspect(engine).get_table_names() else {}
if not acc:
    tabla_aud = M.LogAuditoria.__tablename__
    with engine.connect() as cn:
        acc = dict(cn.execute(text("SELECT accion, count(*) FROM %s WHERE tabla='documentos_familia' GROUP BY accion" % tabla_aud)).fetchall())
check('auditoría: preparar, nueva versión y anular registrados una vez cada uno',
      acc.get('PREPARAR_DOCUMENTO_FAMILIA') == 7 and acc.get('NUEVA_VERSION_DOCUMENTO_FAMILIA') == 2
      and acc.get('ANULAR_DOCUMENTO_FAMILIA') == 1, acc)

# La auditoría automática guarda «MÉTODO ruta» en un campo de 50 caracteres:
# con una ruta más larga el registro se pierde en PostgreSQL (SQLite no lo nota).
tabla_aud = M.LogAuditoria.__tablename__
with engine.connect() as cn:
    autos = [a for (a,) in cn.execute(text("SELECT accion FROM %s WHERE tabla='_auto' AND accion LIKE 'POST /api/documentos-familia/%%'" % tabla_aud)).fetchall()]
check('auditoría automática registrada para preparar, versión, anular y WhatsApp',
      all(any(a.endswith(s) for a in autos) for s in ('/preparar', '/version', '/anular', '/whatsapp')), sorted(set(autos))[:8])
largo_max = max(len('POST ' + r.path.replace('{doc_id}', '9' * 9)) for r in APP.app.routes
                if getattr(r, 'path', '').startswith('/api/documentos-familia'))
check('rutas cortas: «POST ruta» con un id de 9 cifras cabe en 50 caracteres', largo_max <= 50, largo_max)

# ═════════ 10. Persistencia tras reiniciar ═════════
print('\n10. Persistencia tras reiniciar el proceso')
db.close()
engine.dispose()
url_v3 = {e['estudiante_id']: e for e in listar(DIR).json()['estudiantes']}[ESTS[0].id]['documento']['url']
sha_v3 = hashlib.sha256(anon.get(ruta(url_v3) + '/pdf').content).hexdigest()
hijo = r'''
import os, sys, hashlib
sys.path.insert(0, sys.argv[1])
from fastapi.testclient import TestClient
import app as APP
with TestClient(APP.app) as c:
    r = c.get(sys.argv[2]); p = c.get(sys.argv[2] + '/pdf'); a = c.get(sys.argv[3])
    print(r.status_code, hashlib.sha256(p.content).hexdigest(), a.status_code)
'''
env = dict(os.environ, PYTHONIOENCODING='utf-8')
out = subprocess.run([sys.executable, '-c', hijo, BK, ruta(url_v3), u_luis], env=env, capture_output=True,
                     encoding='utf-8', errors='replace', timeout=180)
partes = (out.stdout.strip().splitlines() or [''])[-1].split()
check('otro proceso (reinicio, con migración del arranque) abre el mismo documento',
      len(partes) == 3 and partes[0] == '200' and partes[1] == sha_v3 and partes[2] == '410', (out.stdout[-300:], out.stderr[-800:]))

# ═════════ Resumen ═════════
ok = sum(1 for _, b in RES if b)
print('\n%d/%d' % (ok, len(RES)))
sys.exit(0 if ok == len(RES) else 1)
