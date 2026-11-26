# -*- coding: utf-8 -*-
"""
EducaOne — FAM-DOC-1: medición al preparar los reportes de cursos completos.

Datos SINTÉTICOS: 3 cursos de N estudiantes (por defecto 40) con 12 asignaturas
× 4 competencias, y un logo sintético de ~60 KB (ruido, poco comprimible),
para que el tamaño del PDF se parezca al de un colegio con logo.

Mide por curso: tiempo de «preparar», pico de memoria de Python (tracemalloc),
memoria del proceso (RSS, si psutil está instalado), bytes guardados y, en
PostgreSQL, el tamaño en disco de las tablas nuevas. También el tiempo de abrir
la página y el PDF con el enlace.

Uso (base temporal o PostgreSQL de prueba, como test_documentos_familia.py):
    cd <carpeta temporal>
    python <repo>/backend/tools/medir_documentos_familia.py [N]
    EO_TEST_PG_URL=... EO_TEST_PG_DATADIR=... python <repo>/backend/tools/medir_documentos_familia.py [N]
"""
import base64
import os
import random
import statistics
import struct
import sys
import time
import tracemalloc
import zlib

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(BK, "tools"))
os.environ.setdefault('ENLACE_FAMILIA_SECRET', 'secreto-de-medicion-no-produccion')
os.environ.setdefault('DISABLE_GLOBAL_RATE_LIMIT', 'true')
os.environ.setdefault('ENLACE_FAMILIA_BASE_URL', 'https://educaone.ejemplo.invalid')
N = int(sys.argv[1]) if len(sys.argv) > 1 else 40

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
    TMP = aislar_base_de_datos('fam_doc1_medir')

from database import engine, SessionLocal  # noqa: E402
from sqlalchemy import text  # noqa: E402
from test_utils import verificar_engine_aislado  # noqa: E402

if PG_URL:
    with engine.connect() as cn:
        real = os.path.normcase(os.path.realpath(cn.execute(text('SHOW data_directory')).scalar()))
        tablas = cn.execute(text("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")).scalar()
    if real != os.path.normcase(os.path.realpath(os.environ['EO_TEST_PG_DATADIR'])) or tablas:
        raise SystemExit('No es el clúster de prueba o la base no está vacía. No se ejecuta.')
    motor = 'PostgreSQL %s' % engine.dialect.server_version_info[0] if engine.dialect.server_version_info else 'PostgreSQL'
else:
    verificar_engine_aislado(engine, TMP)
    motor = 'SQLite temporal'

from fastapi.testclient import TestClient  # noqa: E402
import models as M  # noqa: E402
import app as APP  # noqa: E402
from auth import create_token  # noqa: E402

def _memoria_windows():
    import ctypes
    from ctypes import wintypes

    class PMC(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD),
                    ('PeakWorkingSetSize', ctypes.c_size_t), ('WorkingSetSize', ctypes.c_size_t),
                    ('QuotaPeakPagedPoolUsage', ctypes.c_size_t), ('QuotaPagedPoolUsage', ctypes.c_size_t),
                    ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t), ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                    ('PagefileUsage', ctypes.c_size_t), ('PeakPagefileUsage', ctypes.c_size_t)]
    k32 = ctypes.WinDLL('kernel32'); psapi = ctypes.WinDLL('psapi')
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]

    def leer():
        m = PMC(); m.cb = ctypes.sizeof(PMC)
        psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(m), m.cb)
        return m.WorkingSetSize, m.PeakWorkingSetSize
    return leer


try:
    import psutil
    _proc = psutil.Process()
    rss = lambda: (_proc.memory_info().rss, None)
except Exception:  # pragma: no cover
    rss = _memoria_windows() if os.name == 'nt' else None


def png_ruido(ancho=160, alto=160, semilla=7):
    rnd = random.Random(semilla)
    filas = b''.join(b'\x00' + bytes(rnd.getrandbits(8) for _ in range(ancho * 3)) for _ in range(alto))
    def bloque(tipo, datos):
        return struct.pack('>I', len(datos)) + tipo + datos + struct.pack('>I', zlib.crc32(tipo + datos) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + bloque(b'IHDR', struct.pack('>IIBBBBB', ancho, alto, 8, 2, 0, 0, 0))
            + bloque(b'IDAT', zlib.compress(filas, 9)) + bloque(b'IEND', b''))


M.Base.metadata.create_all(bind=engine)
with TestClient(APP.app):
    pass
db = SessionLocal()


def add(o):
    db.add(o)
    db.flush()
    return o


logo = png_ruido()
COL = add(M.Colegio(nombre='Colegio Medición', codigo='med', activo=True))
add(M.ConfiguracionColegio(colegio_id=COL.id, nombre='Colegio Medición Sintético',
                           logo='data:image/png;base64,' + base64.b64encode(logo).decode()))
ANO = add(M.AnoEscolar(colegio_id=COL.id, nombre='2026-2027', activo=True, periodo_activo=1))
T = add(M.Tanda(colegio_id=COL.id, nombre='Matutina', hora_inicio='07:30', hora_fin='12:30', activo=True))
G = add(M.Grado(colegio_id=COL.id, nombre='6to Secundaria', nivel='secundaria', orden=6))
DIR = add(M.Usuario(colegio_id=COL.id, username='dir', password_hash='x', nombre='D', apellido='T', role='direccion',
                    activo=True, must_change_password=False, token_version=0))
ASIGS = [add(M.Asignatura(colegio_id=COL.id, nombre='Asignatura sintética %02d' % k, codigo='A%02d' % k, area='X', activo=True))
         for k in range(12)]
CURSOS = []
for ci in range(4):  # 3 para tiempo, 1 (con tracemalloc) para memoria de Python
    cur = add(M.Curso(colegio_id=COL.id, nombre=chr(65 + ci), grado_id=G.id, tanda_id=T.id, ano_escolar_id=ANO.id, activo=True))
    for a in ASIGS:
        add(M.AsignacionProfesor(colegio_id=COL.id, profesor_id=DIR.id, curso_id=cur.id, asignatura_id=a.id,
                                 ano_escolar_id=ANO.id, activo=True))
    ests = []
    for i in range(N):
        e = add(M.Estudiante(colegio_id=COL.id, nombre='Est%02d' % i, apellido='Curso%s' % chr(65 + ci), curso_id=cur.id,
                             activo=True, no_lista=i + 1, nombre_madre='Madre', telefono_madre='809555%04d' % i))
        ests.append(e.id)
        for a in ASIGS:
            for comp in range(1, 5):
                db.add(M.CalificacionSecundaria(colegio_id=COL.id, estudiante_id=e.id, asignatura_id=a.id,
                                                ano_escolar_id=ANO.id, competencia_numero=comp, p1=70 + (i + comp) % 30))
    CURSOS.append((cur.id, ests))
db.commit()

client = TestClient(APP.app)
H = {'Authorization': 'Bearer ' + create_token(DIR)}
print('Motor: %s · %d estudiantes por curso · logo sintético %.1f KB' % (motor, N, len(logo) / 1024))
LOTE = 10  # como el panel: peticiones de 10 estudiantes


def preparar_curso(cur_id, ests):
    lotes = []
    for i in range(0, len(ests), LOTE):
        t0 = time.perf_counter()
        r = client.post('/api/documentos-familia/preparar', headers=H,
                        json={'curso_id': cur_id, 'periodo': 1, 'estudiante_ids': ests[i:i + LOTE]})
        lotes.append(time.perf_counter() - t0)
        assert r.status_code == 200 and r.json()['creados'] == len(ests[i:i + LOTE]), (r.status_code, r.text[:300])
    return lotes


tiempos, lote_max, bytes_curso = [], [], []
mem0 = rss() if rss else None
for cur_id, ests in CURSOS[:3]:
    lotes = preparar_curso(cur_id, ests)
    with engine.connect() as cn:
        b = cn.execute(text('SELECT coalesce(sum(tamano_bytes),0) FROM documentos_familia WHERE curso_id=:c'), {'c': cur_id}).scalar()
    tiempos.append(sum(lotes)); lote_max.append(max(lotes)); bytes_curso.append(b)
    print('  curso %d: %.2f s en %d peticiones (la más larga %.2f s) · PDFs %.1f KB (%.1f KB/estudiante)' % (
        cur_id, sum(lotes), len(lotes), max(lotes), b / 1024, b / 1024 / N))
mem1 = rss() if rss else None
# Memoria de Python (tracemalloc enlentece mucho: solo en este curso, sin medir tiempo).
tracemalloc.start()
preparar_curso(*CURSOS[3])
_, pico = tracemalloc.get_traced_memory()
tracemalloc.stop()
picos = [pico]

# Repetir la preparación de un curso ya preparado (no genera nada).
t0 = time.perf_counter()
r = client.post('/api/documentos-familia/preparar', headers=H,
                json={'curso_id': CURSOS[0][0], 'periodo': 1, 'estudiante_ids': CURSOS[0][1]})
t_rep = time.perf_counter() - t0
assert r.json()['creados'] == 0
url = r.json()['estudiantes'][0]['documento']['url']
ruta = '/' + url.split('/', 3)[3]
anon = TestClient(APP.app)
tp, tpdf = [], []
for _ in range(20):
    t0 = time.perf_counter(); anon.get(ruta); tp.append(time.perf_counter() - t0)
    t0 = time.perf_counter(); anon.get(ruta + '/pdf'); tpdf.append(time.perf_counter() - t0)

print('\nResumen (3 cursos de %d):' % N)
print('  preparar un curso: mediana %.2f s (mín %.2f, máx %.2f) · %.2f s por estudiante' % (
    statistics.median(tiempos), min(tiempos), max(tiempos), statistics.median(tiempos) / N))
print('  petición más larga (lote de %d): %.2f s' % (LOTE, max(lote_max)))
print('  pico de memoria de Python al preparar un curso (tracemalloc): %.1f MB' % (max(picos) / 1e6))
if rss:
    print('  memoria del proceso: %.1f MB antes de los 3 cursos, %.1f MB después; pico del proceso %s' % (
        mem0[0] / 1e6, mem1[0] / 1e6, ('%.1f MB' % (mem1[1] / 1e6)) if mem1[1] else 'n/d'))
print('  repetir un curso ya preparado: %.2f s (0 PDF nuevos)' % t_rep)
print('  abrir la página: mediana %.1f ms · abrir el PDF: mediana %.1f ms' % (
    statistics.median(tp) * 1000, statistics.median(tpdf) * 1000))
print('  almacenamiento por estudiante (PDF): %.1f KB · por curso: %.1f KB' % (
    statistics.mean(bytes_curso) / N / 1024, statistics.mean(bytes_curso) / 1024))
if PG_URL:
    with engine.connect() as cn:
        for t in ('documentos_familia', 'documentos_familia_archivos', 'documentos_familia_eventos'):
            print('  PostgreSQL %s: %.1f KB en disco (con índices y TOAST)' % (
                t, cn.execute(text("SELECT pg_total_relation_size(:t)"), {'t': t}).scalar() / 1024))
