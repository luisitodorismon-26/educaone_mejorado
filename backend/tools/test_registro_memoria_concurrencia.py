# -*- coding: utf-8 -*-
"""
MEM-REG · Liberación de memoria y límite de generaciones del Registro de Secundaria.

Base SINTÉTICA temporal (REG-43). Comprueba:
  - el límite de turnos (en el proceso, entre procesos y tras la muerte del
    proceso que lo tenía);
  - que el turno se toma DESPUÉS de los permisos: un profesor sin asignación
    recibe 403 y otro colegio 404 aunque no haya turno; quien sí puede, 503
    con Retry-After;
  - que el turno se suelta también si la generación falla;
  - que dos borradores a la vez en el MISMO worker (van al pool de hilos) ya no
    generan en paralelo con un turno, y sí con dos;
  - que tras generar no queda ningún PdfReader/PdfWriter vivo y que todos los
    lectores abiertos se cerraron.

    cd <carpeta temporal> && python <repo>/backend/tools/test_registro_memoria_concurrencia.py
"""
import asyncio
import gc
import os
import subprocess
import sys
import tempfile
import threading
import time

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(BK, 'tools'))
CANDADOS = tempfile.mkdtemp(prefix='mem_reg_candados_')
os.environ['REGISTRO_CANDADO_DIR'] = CANDADOS
os.environ['REGISTRO_GENERACIONES_SIMULTANEAS'] = '1'
os.environ['REGISTRO_ESPERA_SEG'] = '0.6'
os.environ.setdefault('DISABLE_GLOBAL_RATE_LIMIT', 'true')
os.environ.setdefault('ENLACE_FAMILIA_SECRET', 'clave-enlaces-sintetica-mem-reg-0123456789abcdef')
os.environ.setdefault('ENLACE_FAMILIA_BASE_URL', 'https://educaone.ejemplo.invalid')

from test_utils import aislar_base_de_datos  # noqa: E402
TMP = aislar_base_de_datos('mem_reg')
from database import engine, SessionLocal  # noqa: E402
from test_utils import verificar_engine_aislado  # noqa: E402
verificar_engine_aislado(engine, TMP)
import logging  # noqa: E402
logging.disable(logging.WARNING)
from fastapi.testclient import TestClient  # noqa: E402
import pypdf  # noqa: E402
import models as M  # noqa: E402
import app as APP  # noqa: E402
import registro_escolar as RE  # noqa: E402
import limite_generacion as LG  # noqa: E402
from auth import create_token  # noqa: E402
import registro_43_semilla as S  # noqa: E402

RES = []


def check(nombre, ok, detalle=''):
    RES.append((nombre, bool(ok)))
    print(('  OK  ' if ok else '  FALLA ') + nombre + ('' if ok else '  -> ' + str(detalle)[:300]))


M.Base.metadata.create_all(bind=engine)
with TestClient(APP.app):
    pass
db = SessionLocal()
sem = S.sembrar(db, M, [(1, 'A', 40)])
CUR = sem['cursos']['A'].id
PROF_SIN = M.Usuario(colegio_id=sem['colegio'].id, username='mem_prof_sin', password_hash='x', nombre='P', apellido='S',
                     role='profesor', activo=True, must_change_password=False, token_version=0)
OTRO = M.Colegio(nombre='Otro', codigo='MEMOTRO2', activo=True)
db.add_all([PROF_SIN, OTRO]); db.flush()
DIR_OTRO = M.Usuario(colegio_id=OTRO.id, username='mem_dir_otro2', password_hash='x', nombre='D', apellido='O',
                     role='direccion', activo=True, must_change_password=False, token_version=0)
db.add(DIR_OTRO); db.commit()
client = TestClient(APP.app)
H = lambda u: {'Authorization': 'Bearer ' + create_token(u)}  # noqa: E731
OFICIAL = '/api/registros/secundaria/%d?force=true' % CUR
BORRADOR = '/api/registros/secundaria/%d/preview-pdf' % CUR

# ═════════ 1. Turnos ═════════
print('\n1. Turnos')


async def _dos_en_el_proceso():
    async with LG.generacion_pesada():
        try:
            async with LG.generacion_pesada(espera=0.3):
                return 'segundo entró'
        except LG.GeneracionOcupada:
            pass
    async with LG.generacion_pesada(espera=0.3):
        return 'libre tras soltar'
check('en el mismo proceso: con 1 turno, el segundo espera y sale «ocupado»; al soltar entra',
      asyncio.run(_dos_en_el_proceso()) == 'libre tras soltar')

os.environ['REGISTRO_GENERACIONES_SIMULTANEAS'] = '2'


async def _tres_con_dos():
    async with LG.generacion_pesada():
        async with LG.generacion_pesada(espera=0.3):
            try:
                async with LG.generacion_pesada(espera=0.3):
                    return 'tercero entró'
            except LG.GeneracionOcupada:
                return 'tercero ocupado'
check('con 2 turnos: dos a la vez, el tercero «ocupado»', asyncio.run(_tres_con_dos()) == 'tercero ocupado')
os.environ['REGISTRO_GENERACIONES_SIMULTANEAS'] = '1'

HIJO = r'''
import asyncio, os, sys, time
sys.path.insert(0, sys.argv[1])
import limite_generacion as LG
async def main():
    async with LG.generacion_pesada():
        print('TOMADO', flush=True)
        sys.stdin.readline()
asyncio.run(main())
'''


def otro_proceso_con_turno():
    p = subprocess.Popen([sys.executable, '-c', HIJO, BK], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                         env=dict(os.environ))
    assert p.stdout.readline().strip() == 'TOMADO'
    return p


p = otro_proceso_con_turno()


async def _intento():
    try:
        async with LG.generacion_pesada(espera=0.3):
            return 'entró'
    except LG.GeneracionOcupada:
        return 'ocupado'
check('entre procesos: si otro worker tiene el turno, aquí «ocupado»', asyncio.run(_intento()) == 'ocupado')

# ═════════ 2. Endpoints con el turno tomado por otro proceso ═════════
print('\n2. Endpoints sin turno libre')
r = client.get(OFICIAL, headers=H(sem['director']))
check('oficial → 503 con Retry-After y motivo', r.status_code == 503 and r.headers.get('retry-after') == '15'
      and r.json().get('motivo') == 'generacion_ocupada', (r.status_code, r.text[:200]))
r = client.get(BORRADOR, headers=H(sem['director']))
check('borrador → 503', r.status_code == 503, r.status_code)
r = client.get(OFICIAL, headers=H(PROF_SIN))
check('profesor sin asignación → 403 (los permisos van antes del turno)', r.status_code == 403
      and 'tus cursos asignados' in r.json().get('error', ''), (r.status_code, r.text[:150]))
r = client.get(BORRADOR, headers=H(PROF_SIN))
check('… también en el borrador → 403', r.status_code == 403, r.status_code)
check('otro colegio → 404 aunque no haya turno', client.get(OFICIAL, headers=H(DIR_OTRO)).status_code == 404
      and client.get(BORRADOR, headers=H(DIR_OTRO)).status_code == 404)
check('sin sesión → 401', client.get(OFICIAL).status_code == 401)
p.kill(); p.wait()  # el worker que tenía el turno MUERE sin soltarlo
check('si el proceso que tenía el turno muere, el turno queda libre', asyncio.run(_intento()) == 'entró')
r = client.get(OFICIAL, headers=H(sem['director']))
check('con turno libre → 200 PDF', r.status_code == 200 and r.content[:4] == b'%PDF', r.status_code)

# ═════════ 3. El turno se suelta si la generación falla ═════════
print('\n3. Fallo durante la generación')
_orig = RE.generar_registro_desde_sistema


def _falla(*a, **k):
    raise RuntimeError('fallo sintético de generación')
RE.generar_registro_desde_sistema = _falla
r = client.get(OFICIAL, headers=H(sem['director']))
RE.generar_registro_desde_sistema = _orig
check('la generación falla → 500 de siempre', r.status_code == 500, r.status_code)
check('… y el turno quedó libre', asyncio.run(_intento()) == 'entró')

# ═════════ 4. Borradores simultáneos en el mismo worker (pool de hilos) ═════════
print('\n4. Dos borradores a la vez en el mismo proceso')
os.environ['REGISTRO_ESPERA_SEG'] = '120'
estado = {'ahora': 0, 'max': 0}
cerrojo = threading.Lock()


def _contando(*a, **k):
    with cerrojo:
        estado['ahora'] += 1
        estado['max'] = max(estado['max'], estado['ahora'])
    try:
        time.sleep(0.8)  # que se solapen si nada lo impide
        return _orig(*a, **k)
    finally:
        with cerrojo:
            estado['ahora'] -= 1


def dos_borradores():
    estado.update(ahora=0, max=0)
    res = []
    hs = [threading.Thread(target=lambda: res.append(TestClient(APP.app).get(BORRADOR, headers=H(sem['director'])).status_code))
          for _ in range(2)]
    [h.start() for h in hs]; [h.join() for h in hs]
    return res, estado['max']


RE.generar_registro_desde_sistema = _contando
res1, max1 = dos_borradores()
os.environ['REGISTRO_GENERACIONES_SIMULTANEAS'] = '2'
res2, max2 = dos_borradores()
os.environ['REGISTRO_GENERACIONES_SIMULTANEAS'] = '1'
RE.generar_registro_desde_sistema = _orig
check('con 1 turno: los dos borradores responden 200 y NUNCA generan a la vez', res1 == [200, 200] and max1 == 1, (res1, max1))
check('control: con 2 turnos sí se solapan (la prueba no es ciega)', res2 == [200, 200] and max2 == 2, (res2, max2))

# ═════════ 5. Liberación de lectores y escritores ═════════
print('\n5. Liberación de lectores, escritores y buffers')
abiertos, cerrados = [], []
_Lector = RE.PdfReader


class LectorContado(_Lector):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        abiertos.append(id(self))

    def close(self):
        cerrados.append(id(self))
        super().close()


RE.PdfReader = LectorContado
gc.collect()
r = client.get(OFICIAL, headers=H(sem['director']))
RE.PdfReader = _Lector
check('genera bien con lectores contados', r.status_code == 200, r.status_code)
check('cada lector abierto se cerró (plantilla y overlays)', len(abiertos) > 50 and set(abiertos) <= set(cerrados),
      (len(abiertos), len(set(abiertos) - set(cerrados))))
vivos = [o for o in gc.get_objects() if isinstance(o, (pypdf.PdfReader, pypdf.PdfWriter))]
check('tras la respuesta no queda ningún PdfReader/PdfWriter vivo', not vivos, len(vivos))
r = client.get(BORRADOR, headers=H(sem['director']))
vivos = [o for o in gc.get_objects() if isinstance(o, (pypdf.PdfReader, pypdf.PdfWriter))]
check('ídem tras el borrador (sello incluido)', r.status_code == 200 and not vivos, (r.status_code, len(vivos)))

# ═════════ 6. Errores ANTES de la fusión final ═════════
print('\n6. Errores antes de la fusión final del PDF')
import io as _io  # noqa: E402

buffers = []


class BufferContado(_io.BytesIO):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        buffers.append(self)


class _IOContado:
    BytesIO = BufferContado

    def __getattr__(self, nombre):
        return getattr(_io, nombre)


def fallo_controlado(nombre, parchear, restaurar, esperado):
    abiertos.clear(); cerrados.clear(); buffers.clear()
    RE.PdfReader = LectorContado
    _io_orig = RE.io
    RE.io = _IOContado()
    parchear()
    try:
        r = TestClient(APP.app, raise_server_exceptions=False).get(OFICIAL, headers=H(sem['director']))
    finally:
        restaurar()
        RE.io = _io_orig
        RE.PdfReader = _Lector
    vivos = [o for o in gc.get_objects() if isinstance(o, (pypdf.PdfReader, pypdf.PdfWriter))]
    check('%s → %s (igual que antes)' % (nombre, esperado), r.status_code == esperado, (r.status_code, r.text[:160]))
    if abiertos:
        check('%s: la plantilla y los lectores abiertos se cerraron' % nombre, set(abiertos) <= set(cerrados),
              (len(abiertos), len(set(abiertos) - set(cerrados))))
    check('%s: ningún buffer quedó abierto (%d creados)' % (nombre, len(buffers)),
          all(b.closed for b in buffers), sum(1 for b in buffers if not b.closed))
    check('%s: ningún PdfReader/PdfWriter vivo' % nombre, not vivos, len(vivos))
    check('%s: el turno quedó libre' % nombre, asyncio.run(_intento()) == 'entró')


# a) Rechazo deliberado al DIBUJAR una página (el dato no cabe): antes de la fusión.
_dibujo = RE.draw_promocion_izq


def _no_cabe(*a, **k):
    raise RE.RegistroExcedePlantilla({'motivo': 'PRUEBA_NO_CABE', 'mensaje': 'rechazo sintético al dibujar'})
fallo_controlado('rechazo al dibujar una página', lambda: setattr(RE, 'draw_promocion_izq', _no_cabe),
                 lambda: setattr(RE, 'draw_promocion_izq', _dibujo), 422)

# b) Excepción inesperada al dibujar (va por el mismo camino que siempre: página vacía + log).
# c) Excepción en la FUSIÓN, ya con plantilla y overlays abiertos.
_xobj = RE.crear_xobject_desde_overlay


def _rompe_fusion(*a, **k):
    raise RuntimeError('fallo sintético en la fusión')
fallo_controlado('excepción en la fusión', lambda: setattr(RE, 'crear_xobject_desde_overlay', _rompe_fusion),
                 lambda: setattr(RE, 'crear_xobject_desde_overlay', _xobj), 500)

# d) Excepción al CARGAR los datos (antes de abrir ningún PDF).
_carga = APP._cargar_datos_asignaturas_secundaria


def _rompe_carga(*a, **k):
    raise RuntimeError('fallo sintético al cargar datos')
fallo_controlado('excepción al cargar datos', lambda: setattr(APP, '_cargar_datos_asignaturas_secundaria', _rompe_carga),
                 lambda: setattr(APP, '_cargar_datos_asignaturas_secundaria', _carga), 500)

ok = sum(1 for _, b in RES if b)
print('\n%d/%d' % (ok, len(RES)))
sys.exit(0 if ok == len(RES) else 1)
