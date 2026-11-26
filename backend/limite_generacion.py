"""
MEM-REG · Límite de generaciones PESADAS simultáneas en la instancia.

Generar un Registro Escolar de Secundaria (~170 páginas sobre la plantilla del
MINERD) reserva del orden de 50-100 MiB por generación, encima de la memoria de
reposo de cada worker. Con dos workers en una instancia de 512 MiB, dos
generaciones a la vez (una por worker) son las que acercan la instancia al
límite. Este módulo deja que corran como mucho N a la vez en TODA la instancia,
y se adquiere ANTES de validar y cargar los datos del curso: quien espera aún
no ha reservado nada.

Cómo:
  - N «turnos» = N archivos de candado en un directorio local de la instancia
    (todos los workers lo comparten). Un turno se toma con un candado exclusivo
    NO bloqueante (fcntl.flock en Linux; msvcrt.locking en Windows). El sistema
    operativo lo suelta si el proceso muere: no quedan turnos huérfanos.
  - Mientras no hay turno se espera con `asyncio.sleep` (el worker sigue
    atendiendo otras peticiones). Pasado el tiempo máximo -> `GeneracionOcupada`
    y el endpoint responde 503 con Retry-After.

Configuración (variables de entorno):
  REGISTRO_GENERACIONES_SIMULTANEAS   turnos en la instancia (por defecto 1)
  REGISTRO_ESPERA_SEG                 espera máxima por un turno (por defecto 60)
  REGISTRO_CANDADO_DIR                directorio de los candados (por defecto
                                      <temp>/educaone-generacion-pesada)
"""
import asyncio
import contextlib
import os
import tempfile
import time

if os.name == 'nt':
    import msvcrt
else:
    import fcntl


class GeneracionOcupada(Exception):
    """No hubo turno libre dentro del tiempo máximo de espera."""


def _turnos():
    try:
        return max(1, int(os.environ.get('REGISTRO_GENERACIONES_SIMULTANEAS', '1')))
    except ValueError:
        return 1


def _espera():
    try:
        return max(0.0, float(os.environ.get('REGISTRO_ESPERA_SEG', '60')))
    except ValueError:
        return 60.0


def _directorio():
    d = os.environ.get('REGISTRO_CANDADO_DIR') or os.path.join(tempfile.gettempdir(), 'educaone-generacion-pesada')
    os.makedirs(d, exist_ok=True)
    return d


def _intentar(ruta):
    """Descriptor con el candado tomado, o None si otro lo tiene."""
    fd = os.open(ruta, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if os.name == 'nt':
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except OSError:
        os.close(fd)
        return None


def _soltar(fd):
    try:
        if os.name == 'nt':
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


@contextlib.asynccontextmanager
async def generacion_pesada(espera=None, intervalo=0.25):
    """`async with generacion_pesada():` — toma un turno o lanza GeneracionOcupada."""
    limite = time.monotonic() + (_espera() if espera is None else espera)
    d = _directorio()
    rutas = [os.path.join(d, 'turno-%d.lock' % i) for i in range(_turnos())]
    fd = None
    while True:
        for ruta in rutas:
            fd = _intentar(ruta)
            if fd is not None:
                break
        if fd is not None:
            break
        if time.monotonic() >= limite:
            raise GeneracionOcupada()
        await asyncio.sleep(intervalo)
    try:
        yield
    finally:
        _soltar(fd)
