# -*- coding: utf-8 -*-
"""
EducaOne — FAM-DOC-1, correcciones de la revisión (pruebas dirigidas).

  A. Clave PROPIA de los enlaces: obligatoria en producción (≥ 32, distinta de
     SECRET_KEY y JWT_SECRET_KEY); nunca se usa la clave de inicio de sesión.
  B. Rotación: con ENLACE_FAMILIA_SECRETOS_ANTERIORES los enlaces enviados siguen
     abriendo y se pueden volver a compartir; los nuevos usan la clave actual;
     al retirar una clave sus enlaces dejan de abrir y se ofrece versión nueva.
  C. Dirección fija: ENLACE_FAMILIA_BASE_URL (https en producción); el dominio de
     las cabeceras (Host, X-Forwarded-Host/Proto) nunca entra en el enlace.
  D. Versiones: lista por estudiante de todos los años y períodos, y anulación
     de cualquier versión (también de años anteriores) sin borrar el PDF.
  E. Preparación interrumpida (panel cerrado): lo ya preparado se conserva y al
     volver a abrir solo se prepara lo que faltaba.

Base temporal aislada o PostgreSQL de prueba (mismas guardas que
test_documentos_familia.py). Datos y contactos sintéticos; sin mensajes reales.
"""
import hashlib
import json
import os
import subprocess
import sys

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(BK, "tools"))

CLAVE_A = 'clave-sintetica-A-enlaces-familia-0123456789abcdef'
CLAVE_B = 'clave-sintetica-B-enlaces-familia-fedcba9876543210'
BASE = 'https://educaone.ejemplo.invalid'
os.environ['ENLACE_FAMILIA_SECRET'] = CLAVE_A
os.environ.pop('ENLACE_FAMILIA_SECRETOS_ANTERIORES', None)
os.environ['ENLACE_FAMILIA_BASE_URL'] = BASE
os.environ.setdefault('DISABLE_GLOBAL_RATE_LIMIT', 'true')

from test_utils import aislar_base_de_datos  # noqa: E402

PG_URL = os.environ.get('EO_TEST_PG_URL')
if PG_URL:
    from urllib.parse import urlparse
    _u = urlparse(PG_URL)
    if _u.hostname not in ('127.0.0.1', 'localhost') or not _u.path.lstrip('/').startswith('eo_test'):
        raise SystemExit('EO_TEST_PG_URL debe ser un PostgreSQL LOCAL con base eo_test*')
    if not os.environ.get('EO_TEST_PG_DATADIR'):
        raise SystemExit('Con EO_TEST_PG_URL hace falta EO_TEST_PG_DATADIR.')
    os.environ['DATABASE_URL'] = PG_URL
    TMP = None
else:
    TMP = aislar_base_de_datos('fam_doc1_corr')

from database import engine, SessionLocal  # noqa: E402
from sqlalchemy import text  # noqa: E402
from test_utils import verificar_engine_aislado  # noqa: E402

if PG_URL:
    with engine.connect() as cn:
        real = os.path.normcase(os.path.realpath(cn.execute(text('SHOW data_directory')).scalar()))
        tablas = cn.execute(text("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")).scalar()
    if real != os.path.normcase(os.path.realpath(os.environ['EO_TEST_PG_DATADIR'])) or tablas:
        raise SystemExit('No es el clúster de prueba o la base no está vacía. No se ejecuta.')
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


class Entorno:
    """Cambia variables de entorno y las restaura al salir."""
    def __init__(self, **cambios):
        self.cambios = cambios
    def __enter__(self):
        self.antes = {k: os.environ.get(k) for k in self.cambios}
        for k, v in self.cambios.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    def __exit__(self, *a):
        for k, v in self.antes.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ═════════ A. Clave propia ═════════
print('\nA. Clave propia de los enlaces')
SK = 'clave-de-sesion-sintetica-0123456789-abcdefghijk'
JK = 'clave-jwt-sintetica-0123456789-abcdefghijklmnopq'
def errores(**env):
    base = dict(ENLACE_FAMILIA_SECRET=CLAVE_A, ENLACE_FAMILIA_SECRETOS_ANTERIORES=None, ENLACE_FAMILIA_BASE_URL=BASE,
                SECRET_KEY=SK, JWT_SECRET_KEY=JK)
    base.update(env)
    with Entorno(**base):
        return FAMDOC.errores_configuracion()

check('configuración correcta → sin errores', errores() == [], errores())
check('sin ENLACE_FAMILIA_SECRET → error', any('no está configurada' in e for e in errores(ENLACE_FAMILIA_SECRET=None)))
check('clave corta (< 32) → error', any('demasiado corta' in e for e in errores(ENLACE_FAMILIA_SECRET='corta-123')))
check('clave igual a SECRET_KEY → error (debe ser independiente)', any('independiente' in e for e in errores(ENLACE_FAMILIA_SECRET=SK)))
check('clave igual a JWT_SECRET_KEY → error', any('independiente' in e for e in errores(ENLACE_FAMILIA_SECRET=JK)))
check('clave anterior corta → error', any('n.º 1 es demasiado corta' in e for e in errores(ENLACE_FAMILIA_SECRETOS_ANTERIORES='corta')))
check('clave anterior = actual → error', any('repite la actual' in e for e in errores(ENLACE_FAMILIA_SECRETOS_ANTERIORES=CLAVE_A)))
check('clave anterior = clave de sesión → error', any('inicio de sesión' in e for e in errores(ENLACE_FAMILIA_SECRETOS_ANTERIORES=SK)))
check('sin ENLACE_FAMILIA_BASE_URL → error', any('BASE_URL no está configurada' in e for e in errores(ENLACE_FAMILIA_BASE_URL=None)))
check('base http:// en producción → error', any('https://' in e for e in errores(ENLACE_FAMILIA_BASE_URL='http://educaone.ejemplo.invalid')))
check('base con ruta o parámetros → error', all(any('solo el origen' in e for e in errores(ENLACE_FAMILIA_BASE_URL=b))
                                               for b in (BASE + '/app', BASE + '/?x=1', 'https://u:p@educaone.ejemplo.invalid')))

# Sin clave propia nunca se usa SECRET_KEY: en desarrollo, clave de desarrollo; en producción, error.
with Entorno(ENLACE_FAMILIA_SECRET=None, SECRET_KEY=SK):
    _modo = FAMDOC.MODO_DESARROLLO
    FAMDOC.MODO_DESARROLLO = True
    t_dev = FAMDOC.token_de('semilla-prueba')
    t_con_sk = FAMDOC.token_de('semilla-prueba', SK.encode())
    FAMDOC.MODO_DESARROLLO = False
    try:
        FAMDOC.token_de('semilla-prueba'); sin_error = True
    except RuntimeError:
        sin_error = False
    FAMDOC.MODO_DESARROLLO = _modo
check('desarrollo sin clave: no se usa SECRET_KEY', t_dev != t_con_sk)
check('producción sin clave: no se genera ningún enlace (error)', not sin_error)

# La app se niega a arrancar en producción sin la configuración de enlaces.
hijo = r'''
import os, sys
sys.path.insert(0, sys.argv[1])
try:
    import app
    print('ARRANCO')
except RuntimeError as e:
    print('RECHAZO:' + ('ENLACE_FAMILIA_SECRET' in str(e) and 'S' or 'N') + ('ENLACE_FAMILIA_BASE_URL' in str(e) and 'S' or 'N'))
'''
def arranque(**env):
    e = dict(os.environ, RENDER='true', DEBUG='false', SECRET_KEY=SK, JWT_SECRET_KEY=JK,
             ALLOWED_ORIGINS='https://educaone.ejemplo.invalid', PYTHONIOENCODING='utf-8')
    for k, v in env.items():
        if v is None:
            e.pop(k, None)
        else:
            e[k] = v
    out = subprocess.run([sys.executable, '-c', hijo, BK], env=e, capture_output=True, encoding='utf-8', errors='replace',
                         timeout=180, cwd=os.path.dirname(TMP) if TMP else None)
    return (out.stdout.strip().splitlines() or [''])[-1]
r = arranque(ENLACE_FAMILIA_SECRET=None, ENLACE_FAMILIA_BASE_URL=None)
check('producción sin clave ni dirección → no arranca y lo explica', r == 'RECHAZO:SS', r)
r = arranque()
check('producción con clave y dirección válidas → sin errores de enlaces', r in ('ARRANCO', 'RECHAZO:NN'), r)

# ═════════ Datos sintéticos ═════════
M.Base.metadata.create_all(bind=engine)
with TestClient(APP.app):
    pass
db = SessionLocal()


def add(o):
    db.add(o); db.flush(); return o


def usuario(col, username, role, nivel=None):
    return add(M.Usuario(colegio_id=col.id, username=username, password_hash='x', nombre=username, apellido='T',
                         role=role, activo=True, must_change_password=False, token_version=0, nivel_asignado=nivel))


COL = add(M.Colegio(nombre='Colegio Sintético Uno', codigo='cs1', activo=True))
OTRO = add(M.Colegio(nombre='Colegio Sintético Dos', codigo='cs2', activo=True))
add(M.ConfiguracionColegio(colegio_id=COL.id, nombre='Colegio Sintético Uno'))
ANO_VIEJO = add(M.AnoEscolar(colegio_id=COL.id, nombre='2025-2026', activo=False, periodo_activo=4))
ANO = add(M.AnoEscolar(colegio_id=COL.id, nombre='2026-2027', activo=True, periodo_activo=1))
T = add(M.Tanda(colegio_id=COL.id, nombre='Matutina', hora_inicio='07:30', hora_fin='12:30', activo=True))
G = add(M.Grado(colegio_id=COL.id, nombre='6to Secundaria', nivel='secundaria', orden=6))
CUR = add(M.Curso(colegio_id=COL.id, nombre='A', grado_id=G.id, tanda_id=T.id, ano_escolar_id=ANO.id, activo=True))
CUR_VIEJO = add(M.Curso(colegio_id=COL.id, nombre='A', grado_id=G.id, tanda_id=T.id, ano_escolar_id=ANO_VIEJO.id, activo=False))
DIR = usuario(COL, 'sint_dir', 'direccion')
COORD_P = usuario(COL, 'sint_coord_p', 'coordinador', 'primaria')
PROF = usuario(COL, 'sint_prof', 'profesor')
DIR2 = usuario(OTRO, 'sint_dir_otro', 'direccion')
ASIG = add(M.Asignatura(colegio_id=COL.id, nombre='Lengua Española', codigo='LEN', area='X', activo=True))
add(M.AsignacionProfesor(colegio_id=COL.id, profesor_id=PROF.id, curso_id=CUR.id, asignatura_id=ASIG.id,
                         ano_escolar_id=ANO.id, activo=True))
ESTS = []
for i in range(25):
    e = add(M.Estudiante(colegio_id=COL.id, nombre='Est%02d' % i, apellido='Sintetico', curso_id=CUR.id, activo=True,
                         no_lista=i + 1, nombre_madre='Madre', telefono_madre='809555%04d' % i))
    ESTS.append(e)
    for comp in range(1, 5):
        add(M.CalificacionSecundaria(colegio_id=COL.id, estudiante_id=e.id, asignatura_id=ASIG.id,
                                     ano_escolar_id=ANO.id, competencia_numero=comp, p1=80 + comp))
db.commit()
client = TestClient(APP.app)


def H(u, **extra):
    h = {'Authorization': 'Bearer ' + create_token(u)}
    h.update(extra)
    return h


def preparar(ids, u=DIR, **cab):
    return client.post('/api/documentos-familia/preparar', headers=H(u, **cab),
                       json={'curso_id': CUR.id, 'periodo': 1, 'estudiante_ids': ids})


def listar(u=DIR):
    return {e['estudiante_id']: e for e in client.get('/api/documentos-familia/curso/%d?periodo=1' % CUR.id,
                                                       headers=H(u)).json()['estudiantes']}


def ruta(url):
    return '/' + url.split('/', 3)[3]


def contar(tabla):
    with engine.connect() as cn:
        return cn.execute(text('SELECT count(*) FROM %s' % tabla)).scalar()


anon = TestClient(APP.app)

# ═════════ C. Dirección fija ═════════
print('\nC. Dirección fija')
r = preparar([ESTS[0].id], **{'Host': 'atacante.ejemplo.invalid', 'X-Forwarded-Host': 'otro.ejemplo.invalid',
                              'X-Forwarded-Proto': 'http'})
u0 = r.json()['estudiantes'][0]['documento']['url']
check('el enlace usa la dirección configurada, no la de las cabeceras',
      r.status_code == 200 and u0.startswith(BASE + '/doc/') and 'atacante' not in u0 and 'otro.ejemplo' not in u0, u0)
u0b = listar()[ESTS[0].id]['documento']['url']
check('al volver a consultar, el mismo enlace con la misma dirección', u0b == u0)
_modo = FAMDOC.MODO_DESARROLLO
FAMDOC.MODO_DESARROLLO = False
with Entorno(ENLACE_FAMILIA_BASE_URL='http://educaone.ejemplo.invalid'):
    try:
        FAMDOC.base_url(); ok_http = True
    except RuntimeError:
        ok_http = False
FAMDOC.MODO_DESARROLLO = _modo
check('en producción una dirección http:// no se usa (error)', not ok_http)

# ═════════ B. Rotación ═════════
print('\nB. Rotación de la clave')
TOK_A = u0.rsplit('/', 1)[1]
sha_a = hashlib.sha256(anon.get(ruta(u0) + '/pdf').content).hexdigest()
with Entorno(ENLACE_FAMILIA_SECRET=CLAVE_B, ENLACE_FAMILIA_SECRETOS_ANTERIORES=CLAVE_A):
    check('clave nueva + anterior: el enlace ya enviado sigue abriendo',
          anon.get(ruta(u0)).status_code == 200 and hashlib.sha256(anon.get(ruta(u0) + '/pdf').content).hexdigest() == sha_a)
    d = listar()[ESTS[0].id]['documento']
    check('… y se puede volver a compartir EXACTAMENTE el mismo enlace', d['url'] == u0 and d['enlace_disponible'] is True, d)
    r = preparar([ESTS[1].id])
    u1 = r.json()['estudiantes'][0]['documento']['url']
    t1 = u1.rsplit('/', 1)[1]
    with engine.connect() as cn:
        nonce1 = cn.execute(text('SELECT token_nonce FROM documentos_familia WHERE estudiante_id=:e'), {'e': ESTS[1].id}).scalar()
    check('los documentos nuevos se firman con la clave ACTUAL',
          t1 == FAMDOC.token_de(nonce1, CLAVE_B.encode()) and t1 != FAMDOC.token_de(nonce1, CLAVE_A.encode()))
    check('el nuevo abre', anon.get(ruta(u1)).status_code == 200)
with Entorno(ENLACE_FAMILIA_SECRET=CLAVE_B, ENLACE_FAMILIA_SECRETOS_ANTERIORES=None):
    check('al retirar la clave anterior, su enlace deja de abrir (404 genérico)', anon.get(ruta(u0)).status_code == 404)
    d = listar()[ESTS[0].id]['documento']
    check('… la lista no inventa un enlace y avisa (enlace_disponible = false)', d['url'] is None and d['enlace_disponible'] is False, d)
    check('… el firmado con la clave actual sigue abriendo', anon.get(ruta(u1)).status_code == 200)
    rv = client.post('/api/documentos-familia/%d/version' % d['id'], headers=H(DIR))
    d2 = listar()[ESTS[0].id]['documento']
    check('… «Preparar nueva versión» da un enlace nuevo que abre', rv.status_code == 200 and d2['url'] and d2['enlace_disponible']
          and anon.get(ruta(d2['url'])).status_code == 200, (rv.text, d2))
    U0_V2 = d2['url']
# Volvemos a la clave A sola: el de la clave B deja de abrir (simétrico) y el v1 (A) vuelve, como «reemplazado».
check('restaurar la clave A: el enlace v1 vuelve a abrir (como reemplazado, con aviso)',
      anon.get(ruta(u0)).status_code == 200 and 'versión más reciente' in anon.get(ruta(u0)).text)
os.environ['ENLACE_FAMILIA_SECRET'] = CLAVE_B
os.environ['ENLACE_FAMILIA_SECRETOS_ANTERIORES'] = CLAVE_A  # configuración de rotación para el resto

# ═════════ D. Versiones y anulación de años anteriores ═════════
print('\nD. Versiones y anulación')
# Documento de un AÑO ANTERIOR (como si se hubiera preparado entonces): mismo modelo, misma tabla de PDF.
nonce_v = FAMDOC.nueva_semilla()
tok_v = FAMDOC.token_de(nonce_v, CLAVE_A.encode())
vista_v = {'colegio': 'Colegio Sintético Uno', 'estudiante': ESTS[0].nombre_completo, 'curso': 'Curso anterior',
           'matricula': None, 'ano': '2025-2026', 'periodo': 4, 'filas': [], 'preparado': '20/06/2026'}
pdf_v = b'%PDF-1.4 sintetico del ano anterior'
viejo = add(M.DocumentoFamilia(colegio_id=COL.id, estudiante_id=ESTS[0].id, curso_id=CUR_VIEJO.id,
                               ano_escolar_id=ANO_VIEJO.id, tipo='reporte_periodo', periodo=4, version=1, estado='activo',
                               token_nonce=nonce_v, token_hash=FAMDOC.hash_token(tok_v),
                               contenido_sha256=hashlib.sha256(pdf_v).hexdigest(), datos_sha256='x' * 64,
                               vista_json=json.dumps(vista_v), tamano_bytes=len(pdf_v), nombre_archivo='Reporte.pdf',
                               preparado_por=DIR.id))
add(M.DocumentoFamiliaArchivo(documento_id=viejo.id, colegio_id=COL.id, pdf=pdf_v))
db.commit()
RUTA_VIEJO = FAMDOC.ruta_publica(tok_v)
check('el enlace del año anterior abre antes de anular', anon.get(RUTA_VIEJO).status_code == 200)
rl = client.get('/api/documentos-familia/estudiante/%d/versiones' % ESTS[0].id, headers=H(DIR))
V = rl.json().get('versiones', [])
check('la lista incluye todas las versiones: años y períodos anteriores también',
      rl.status_code == 200 and [(v['ano'], v['periodo'], v['version'], v['estado']) for v in V] ==
      [('2026-2027', 1, 2, 'activo'), ('2026-2027', 1, 1, 'reemplazado'), ('2025-2026', 4, 1, 'activo')], V)
check('cada versión trae fecha de preparación y no expone enlaces', all(v['fecha_preparado'] for v in V)
      and 'url' not in json.dumps(V) and '/doc/' not in json.dumps(V))
check('profesor no ve la lista (403)', client.get('/api/documentos-familia/estudiante/%d/versiones' % ESTS[0].id, headers=H(PROF)).status_code == 403)
check('otro colegio: 404', client.get('/api/documentos-familia/estudiante/%d/versiones' % ESTS[0].id, headers=H(DIR2)).status_code == 404)
check('coordinación de Primaria: 403 (documentos de Secundaria)',
      client.get('/api/documentos-familia/estudiante/%d/versiones' % ESTS[0].id, headers=H(COORD_P)).status_code == 403)
check('otro colegio no puede anular el del año anterior (404)',
      client.post('/api/documentos-familia/%d/anular' % viejo.id, headers=H(DIR2)).status_code == 404)
pdfs_antes = contar('documentos_familia_archivos')
ra = client.post('/api/documentos-familia/%d/anular' % viejo.id, headers=H(DIR), json={'motivo': 'prueba'})
check('anular el documento del año anterior → 200', ra.status_code == 200 and ra.json()['estado'] == 'anulado', ra.text)
check('… su enlace deja de abrir (410)', anon.get(RUTA_VIEJO).status_code == 410 and anon.get(RUTA_VIEJO + '/pdf').status_code == 410)
check('… y el PDF NO se borra', contar('documentos_familia_archivos') == pdfs_antes
      and engine.connect().execute(text('SELECT length(pdf) FROM documentos_familia_archivos WHERE documento_id=:i'),
                                   {'i': viejo.id}).scalar() == len(pdf_v))
v1_id = next(v['id'] for v in V if v['version'] == 1 and v['ano'] == '2026-2027')
check('anular una versión reemplazada → su enlace deja de abrir',
      client.post('/api/documentos-familia/%d/anular' % v1_id, headers=H(DIR)).status_code == 200
      and anon.get(ruta(u0)).status_code == 410)
check('… la versión activa sigue abriendo', anon.get(ruta(U0_V2)).status_code == 200)
V2 = client.get('/api/documentos-familia/estudiante/%d/versiones' % ESTS[0].id, headers=H(DIR)).json()['versiones']
check('la lista refleja los anulados con su fecha', [v['estado'] for v in V2] == ['activo', 'anulado', 'anulado']
      and all(v['fecha_anulado'] for v in V2 if v['estado'] == 'anulado'), V2)
check('estudiante inexistente → 404', client.get('/api/documentos-familia/estudiante/999999/versiones', headers=H(DIR)).status_code == 404)

# ═════════ E. Preparación interrumpida ═════════
print('\nE. Preparación interrumpida (panel cerrado)')
IDS = [e.id for e in ESTS[2:25]]  # 23 estudiantes nuevos
r1 = preparar(IDS[:10])  # el primer lote llegó; el panel se cerró antes del resto
urls_1 = {e['estudiante_id']: e['documento']['url'] for e in r1.json()['estudiantes']}
n_docs = contar('documentos_familia')
r2 = None
total_creados = 0
for i in range(0, len(IDS), 10):  # al volver a abrir: el panel recorre TODOS los lotes
    r2 = preparar(IDS[i:i + 10])
    total_creados += r2.json()['creados']
check('al volver a abrir solo se prepara lo que faltaba (13 de 23)', total_creados == 13, total_creados)
check('lo preparado antes conserva su enlace', all(listar()[i]['documento']['url'] == u for i, u in urls_1.items()))
check('sin duplicados', contar('documentos_familia') == n_docs + 13)

ok = sum(1 for _, b in RES if b)
print('\n%d/%d' % (ok, len(RES)))
sys.exit(0 if ok == len(RES) else 1)
