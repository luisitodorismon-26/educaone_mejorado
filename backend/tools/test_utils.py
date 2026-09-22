# -*- coding: utf-8 -*-
"""
Aislamiento de base de datos para las suites que no lo traían.

POR QUÉ EXISTE
    Seis suites legacy empezaban así:

        _BASE = .../backend
        for ext in ['', '-shm', '-wal']:
            os.remove(os.path.join(_BASE, 'sge.db' + ext))
        os.remove(os.path.join(_BASE, 'INITIAL_CREDENTIALS.txt'))
        from database import engine          # -> sqlite:///sge.db (relativa)
        Base.metadata.create_all(bind=engine)

    Es decir: BORRABAN la base local de quien ejecutara la suite y la
    reconstruían con sus propios datos de prueba. No era un riesgo teórico —
    `database.py` resuelve `sqlite:///sge.db` contra el directorio actual, y
    la forma documentada de lanzarlas es `cd backend && python tools/…`, con
    lo que la ruta relativa cae exactamente sobre el fichero que el bloque
    acababa de borrar. Además dejaban dentro todos sus datos.

    Aquí no se copia ni se renombra nada: la prueba NACE aislada, sobre un
    directorio temporal propio que se borra al terminar.

CÓMO SE USA

    import sys, os
    _AQUI = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(_AQUI))   # backend/
    sys.path.insert(0, _AQUI)                    # tools/  (para este módulo)
    from test_utils import aislar_base_de_datos, verificar_engine_aislado

    _TMP = aislar_base_de_datos('mi_suite')      # ANTES de cualquier import
    from database import engine, SessionLocal
    verificar_engine_aislado(engine, _TMP)

EL ORDEN IMPORTA
    `database.py` construye el engine EN EL MOMENTO DE IMPORTARSE, leyendo
    `DATABASE_URL` del entorno. Cambiar la variable después no mueve el
    engine: seguiría apuntando a la base real. Por eso `aislar_base_de_datos`
    se niega a trabajar si `database`, `models` o `app` ya están importados,
    en vez de dar una falsa sensación de aislamiento.
"""
import atexit
import os
import shutil
import sys
import tempfile
import time

# Nombres de bases reales que jamás deben aparecer en la URL de una suite.
BASES_REALES = ('sge.db', 'educaone.db')

# Módulos que congelan la URL al importarse.
MODULOS_QUE_FIJAN_EL_ENGINE = ('database', 'models', 'app')


def _ruta_segura_para_borrar(ruta):
    """¿Está `ruta` realmente dentro del temp del sistema?

    El guard mira rutas REALES (resueltos los symlinks) y compara por
    componentes, no por texto: así `/tmp/eo` no cuenta como padre de
    `/tmp/eo_otro`.
    """
    try:
        objetivo = os.path.realpath(ruta)
        raiz_tmp = os.path.realpath(tempfile.gettempdir())
    except OSError:
        return False
    if objetivo == raiz_tmp:
        return False                      # nunca el temp entero
    try:
        return os.path.commonpath([objetivo, raiz_tmp]) == raiz_tmp
    except ValueError:
        return False                      # unidades distintas en Windows


def _cerrar_engine():
    """Suelta el fichero SQLite antes de intentar borrarlo.

    En Windows un fichero abierto no se puede borrar, y cuando corre
    `atexit` el engine todavía tiene su conexión viva. Sin este dispose el
    rmtree falla y el temporal se queda ahí para siempre.
    """
    modulo = sys.modules.get('database')
    engine = getattr(modulo, 'engine', None)
    if engine is not None:
        try:
            engine.dispose()
        except Exception:
            pass


def _limpiar(tmpdir):
    """Borra el temporal de la suite, y solo eso.

    A propósito SIN `ignore_errors`: una limpieza que falla en silencio es
    peor que ninguna, porque deja creer que el temporal desapareció. Si no
    se puede borrar, se dice.
    """
    if not _ruta_segura_para_borrar(tmpdir):
        # Un test no tiene por qué borrar nada fuera de su propio temporal.
        sys.stderr.write(
            '[test_utils] NO se borra %r: esta fuera del directorio temporal\n'
            % (tmpdir,))
        return

    _cerrar_engine()
    ultimo_error = None
    for intento in range(5):
        try:
            shutil.rmtree(tmpdir)
            return
        except FileNotFoundError:
            return
        except OSError as e:
            ultimo_error = e
            time.sleep(0.2 * (intento + 1))
    sys.stderr.write(
        '[test_utils] AVISO: no se pudo borrar el temporal %r (%s). '
        'Ninguna base real esta afectada, pero conviene revisarlo.\n'
        % (tmpdir, ultimo_error))


def aislar_base_de_datos(prefijo='eo_test'):
    """Apunta DATABASE_URL a una SQLite temporal propia. Devuelve el tempdir.

    Llamar ANTES de importar `database`, `models` o `app`.
    """
    ya_importados = [m for m in MODULOS_QUE_FIJAN_EL_ENGINE if m in sys.modules]
    if ya_importados:
        raise RuntimeError(
            'aislar_base_de_datos() se llamo DESPUES de importar %s. El engine '
            'ya esta construido sobre la base anterior y cambiar DATABASE_URL '
            'ahora no lo mueve: la suite escribiria en la base real.'
            % ', '.join(ya_importados))

    tmpdir = tempfile.mkdtemp(prefix='%s_' % prefijo)
    ruta = os.path.join(tmpdir, 'test.db')
    # SQLAlchemy quiere barras normales incluso en Windows.
    os.environ['DATABASE_URL'] = 'sqlite:///' + ruta.replace('\\', '/')
    atexit.register(_limpiar, tmpdir)
    return tmpdir


def verificar_engine_aislado(engine, tmpdir):
    """Aborta si el engine no quedó dentro del temporal de la suite.

    Se comprueba DESPUÉS del import porque es lo único que demuestra que el
    aislamiento funcionó de verdad: la variable de entorno por sí sola no
    prueba nada si algún módulo se había importado antes.
    """
    url = str(engine.url).replace('\\', '/')
    esperado = tmpdir.replace('\\', '/')
    problemas = []
    if esperado not in url:
        problemas.append('la URL no apunta al temporal de la suite')
    for real in BASES_REALES:
        if real in url:
            problemas.append('la URL menciona la base real %r' % real)
    if problemas:
        sys.stderr.write(
            '[test_utils] AISLAMIENTO ROTO: %s\n  url      = %s\n  esperado = %s\n'
            % ('; '.join(problemas), url, esperado))
        raise SystemExit(9)
    return True
