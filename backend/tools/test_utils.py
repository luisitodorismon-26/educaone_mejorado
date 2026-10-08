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

DOS COSAS QUE SE ENDURECIERON DESPUÉS (A1)
    La primera versión de los guards funcionaba para el caso real, pero era
    más laxa de lo que decía ser, y ambas cosas se comprobaron fallando:

      · el cleanup aceptaba CUALQUIER ruta bajo el TEMP del sistema, así que
        podía borrar el temporal de otro programa que no tenía nada que ver.
        Ahora solo borra rutas que este mismo módulo creó, y lo sabe porque
        las lleva apuntadas;

      · la verificación del engine comparaba la URL como TEXTO, de modo que
        un temporal `…/eo_test_123_otro` pasaba por estar dentro de
        `…/eo_test_123`. Ahora se compara la ruta real del fichero por
        componentes, no por prefijo de cadena.
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

# Temporales creados POR ESTE MÓDULO. Es la única autorización de borrado:
# estar dentro del TEMP del sistema no convierte un directorio en nuestro.
_TEMPORALES_PROPIOS = set()


def _clave(ruta):
    """Forma canónica de una ruta para comparar y para el registro.

    `realpath` resuelve symlinks y `normcase` iguala mayúsculas y
    separadores, que en Windows hacen falta para que dos formas de escribir
    la misma ruta cuenten como la misma.
    """
    return os.path.normcase(os.path.realpath(os.path.abspath(ruta)))


def _esta_dentro_de(hijo, padre):
    """¿`hijo` cuelga de `padre`, comparando por COMPONENTES?

    No vale `hijo.startswith(padre)`: con eso `/tmp/eo_1_otro` parecería
    estar dentro de `/tmp/eo_1`. `commonpath` compara tramo a tramo.
    Lanza ValueError si están en unidades distintas (Windows), y eso
    significa que no cuelga: no es un error, es un «no».
    """
    try:
        return os.path.commonpath([hijo, padre]) == padre
    except ValueError:
        return False


def _ruta_segura_para_borrar(ruta):
    """¿Puede esta ruta borrarse? Solo si la creamos nosotros.

    Las cinco condiciones, en orden:
      1. está registrada como temporal propio;
      2. cuelga del TEMP del sistema;
      3. no es la raíz del TEMP;
      4. no es —ni contiene— el repositorio;
      5. no es padre de otro temporal propio.
    """
    objetivo = _clave(ruta)

    # 1. Propiedad explícita. Es la condición que de verdad decide.
    if objetivo not in _TEMPORALES_PROPIOS:
        return False

    try:
        raiz_tmp = _clave(tempfile.gettempdir())
    except OSError:
        return False

    # 3. Nunca el TEMP entero.
    if objetivo == raiz_tmp:
        return False

    # 2. Dentro del TEMP, por componentes.
    if not _esta_dentro_de(objetivo, raiz_tmp):
        return False

    # 4. Nunca el repositorio, ni un directorio que lo contenga. Esto no
    #    debería poder pasar si 1 y 2 se cumplen, pero un temporal es barato
    #    y un repositorio no.
    repo = _clave(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if objetivo == repo or _esta_dentro_de(repo, objetivo):
        return False

    # 5. No borrar un directorio que contenga OTRO temporal propio: sería
    #    llevarse por delante el aislamiento de otra suite.
    for otro in _TEMPORALES_PROPIOS:
        if otro != objetivo and _esta_dentro_de(otro, objetivo):
            return False

    return True


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
    """Borra un temporal PROPIO, y solo eso.

    A propósito SIN `ignore_errors`: una limpieza que falla en silencio es
    peor que ninguna, porque deja creer que el temporal desapareció. Si no
    se puede borrar, se dice.
    """
    objetivo = _clave(tmpdir)

    if not _ruta_segura_para_borrar(tmpdir):
        if not os.path.exists(tmpdir):
            _TEMPORALES_PROPIOS.discard(objetivo)   # ya no está: solo olvidarlo
            return
        sys.stderr.write(
            '[test_utils] NO se borra %r: no es un temporal creado por este '
            'modulo\n' % (tmpdir,))
        return

    _cerrar_engine()
    ultimo_error = None
    for intento in range(5):
        try:
            shutil.rmtree(tmpdir)
            _TEMPORALES_PROPIOS.discard(objetivo)
            return
        except FileNotFoundError:
            _TEMPORALES_PROPIOS.discard(objetivo)
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
    _TEMPORALES_PROPIOS.add(_clave(tmpdir))
    ruta = os.path.join(tmpdir, 'test.db')
    # SQLAlchemy quiere barras normales incluso en Windows.
    os.environ['DATABASE_URL'] = 'sqlite:///' + ruta.replace('\\', '/')
    atexit.register(_limpiar, tmpdir)
    return tmpdir


def verificar_engine_aislado(engine, tmpdir):
    """Aborta si el fichero del engine no está DENTRO del temporal indicado.

    Se comprueba DESPUÉS del import porque es lo único que demuestra que el
    aislamiento funcionó de verdad: la variable de entorno por sí sola no
    prueba nada si algún módulo se había importado antes.

    La pertenencia se decide sobre la ruta real del fichero, tomada de
    `engine.url.database` —SQLAlchemy ya la tiene parseada, no hay por qué
    volver a trocear la URL a mano— y comparada por componentes.
    """
    problemas = []
    esperado = _clave(tmpdir)

    backend = engine.url.get_backend_name()
    if backend != 'sqlite':
        problemas.append('el engine no es SQLite sino %r' % backend)

    db = engine.url.database
    if not db:
        problemas.append('el engine no tiene fichero (¿base en memoria?)')
        db_real = None
    else:
        db_real = _clave(db)
        if os.path.basename(db_real) in [n.lower() for n in BASES_REALES]:
            problemas.append('apunta a una base real (%s)'
                             % os.path.basename(db))
        if db_real == esperado:
            problemas.append('la ruta de la base es el propio directorio')
        elif not _esta_dentro_de(db_real, esperado):
            problemas.append('la base NO cuelga del temporal de la suite')

    if problemas:
        sys.stderr.write(
            '[test_utils] AISLAMIENTO ROTO: %s\n'
            '  base     = %s\n'
            '  esperado = %s\n'
            % ('; '.join(problemas), db_real or engine.url, esperado))
        raise SystemExit(9)
    return True


# ═══════════════════════════════════════════════════════════════════════
# ASISTENCIA CANÓNICA · fixtures
# ═══════════════════════════════════════════════════════════════════════
#
# Desde la asistencia canónica, un día lectivo SIN lista no cuenta como
# presente: A2 solo certifica con cobertura COMPLETA. Las suites que prueban
# otra cosa (Cierre, promoción, boletines) necesitan entonces que sus
# estudiantes tengan asistencia real, o quedarían todos EN_PROCESO por
# asistencia y lo que prueban dejaría de verse.
#
# Una semana lectiva YA PASADA basta: la ventana de asistencia termina hoy, y
# una semana en el futuro no tendría días que evaluar.

def semana_lectiva_pasada():
    """(lunes, viernes) de una semana fija ya pasada, igual para todas las
    suites: 2026-03-02 .. 2026-03-06."""
    import datetime as _dt
    return _dt.date(2026, 3, 2), _dt.date(2026, 3, 6)


def fechar_ano(ano):
    """Le da al año la semana lectiva de prueba si no tiene fechas."""
    ini, fin = semana_lectiva_pasada()
    if getattr(ano, 'fecha_inicio', None) is None:
        ano.fecha_inicio = ini
    if getattr(ano, 'fecha_fin', None) is None:
        ano.fecha_fin = fin
    return ano


def asistencia_completa(db, M, estudiante, curso_id, colegio_id, ano,
                        estado='presente'):
    """Una marca por cada día hábil del año (hasta hoy) para ese estudiante."""
    import datetime as _dt
    if ano is None or ano.fecha_inicio is None or ano.fecha_fin is None:
        return 0
    fin = min(ano.fecha_fin, _dt.date.today())
    d, n = ano.fecha_inicio, 0
    while d <= fin:
        if d.weekday() < 5:
            db.add(M.Asistencia(colegio_id=colegio_id, estudiante_id=estudiante.id,
                                curso_id=curso_id, fecha=d, estado=estado))
            n += 1
        d += _dt.timedelta(days=1)
    return n
