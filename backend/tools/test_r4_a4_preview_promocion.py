# -*- coding: utf-8 -*-
"""
R4-A4 — la previsualizacion de Direccion, contra el motor canonico.

QUE COMPRUEBA
    Que las dos pantallas que ANTICIPAN la promocion dicen lo mismo, y que lo
    que dicen sale de A2 y no de una regla propia.

    Antes de A4 cada una tenia la suya, y no coincidian:

      GET /api/promocion/estudiantes   recalculaba CF, cortaba en 70 y
                                       repartia en Promovido / "Promovido
                                       condicional" / Reprobado
      GET /api/cierre-ano/promocion    recalculaba CF otra vez y decidia
                                       "cualquier fallo reprueba", ademas de
                                       calcular la asistencia como
                                       presentes / filas existentes

    «Promovido condicional» no existe en la Ordenanza ni en el motor. Lo que
    existe es el APLAZADO: quien todavia tiene derecho a un proceso de
    recuperacion. Llamarlo promovido adelanta una promocion que no ocurrio;
    llamarlo reprobado le quita un derecho.

COMO ESTAN HECHAS
    Se siembra un colegio real en una base temporal aislada y se llaman las
    funciones de endpoint DIRECTAMENTE, con la sesion y un usuario de
    direccion. No se simula la respuesta: se ejecuta el mismo codigo que
    correria en produccion, SQL incluido.

Uso:
    cd backend
    python tools/test_r4_a4_preview_promocion.py
"""
import asyncio
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

from test_utils import aislar_base_de_datos, verificar_engine_aislado  # noqa: E402

_TMP = aislar_base_de_datos('r4_a4')
from database import engine, SessionLocal                      # noqa: E402
verificar_engine_aislado(engine, _TMP)

import models as M                                             # noqa: E402
import promocion_academica as PA                               # noqa: E402
import resultado_academico as RA                               # noqa: E402
import resultado_academico_consumidores as AD                  # noqa: E402
import app as APP                                              # noqa: E402

M.Base.metadata.create_all(bind=engine)

G, R, B, C, X = "\033[92m", "\033[91m", "\033[1m", "\033[96m", "\033[0m"
_fail, _ok, _total = [], 0, 0


def test(nombre):
    def deco(fn):
        global _total, _ok
        _total += 1
        try:
            fn()
            _ok += 1
            print(f"  {G}PASA{X}  {nombre}")
        except Exception as e:
            import traceback
            _fail.append((nombre, str(e)))
            print(f"  {R}FALLA{X} {nombre}\n        {e}")
            traceback.print_exc()
        return fn
    return deco


def igual(obtenido, esperado, msg=''):
    if obtenido != esperado:
        raise AssertionError('%s\n        esperado %r\n        obtenido %r'
                             % (msg, esperado, obtenido))


# ═══════════════════ EL COLEGIO DE PRUEBA ═══════════════════
#
# Un centro con Primaria y Secundaria completas, para poder comprobar que una
# misma Asignatura sirve en los dos niveles y que el destino se resuelve por
# (nivel, grado) y no por el `orden` global.

AREAS_SEC = list(AD.curriculo_oficial_esperado(RA.NIVEL_SECUNDARIA, 3)[0])
DIAS = {'ago': 20, 'sep': 20, 'oct': 20, 'nov': 20, 'dic': 15, 'ene': 20,
        'feb': 18, 'mar': 20, 'abr': 18, 'may': 20, 'jun': 15}

_DB = SessionLocal()
_COL = M.Colegio(nombre='A4', codigo='A4TEST', activo=True)
_DB.add(_COL)
_DB.flush()
_ANO = M.AnoEscolar(colegio_id=_COL.id, nombre='2025-2026', activo=True)
_ANO.set_dias_trabajados(DIAS)
_DB.add(_ANO)
_DB.flush()

# Grados: Secundaria 1-6 con orden 1-6, Primaria 1-6 con orden 7-12. Ese
# reparto es el real de un colegio mixto (R4-A3.1) y es justo el que rompe
# cualquier resolucion de destino basada en `orden + 1`.
# Los ordinales reales del sistema: '1ro', '2do', ... Escribirlos con
# '%do' % n daba "4o" —el %d se come la d— y el test comparaba contra un
# nombre que ningun colegio usa.
ORDINAL = {1: '1ro', 2: '2do', 3: '3ro', 4: '4to', 5: '5to', 6: '6to'}

_GRADOS = {}
for _n in range(1, 7):
    _GRADOS[('secundaria', _n)] = M.Grado(
        colegio_id=_COL.id, nombre='%s Secundaria' % ORDINAL[_n],
        nivel='secundaria', orden=_n, activo=True)
    _GRADOS[('primaria', _n)] = M.Grado(
        colegio_id=_COL.id, nombre='%s Primaria' % ORDINAL[_n],
        nivel='primaria', orden=_n + 6, activo=True)
_DB.add_all(list(_GRADOS.values()))
_DB.flush()

_PROF = M.Usuario(colegio_id=_COL.id, nombre='P', username='a4prof',
                  password_hash='x', role='profesor', activo=True)
_DB.add(_PROF)
_DB.flush()

# Una sola fila por area, compartida entre niveles: es lo que demuestra que
# `area_curricular_codigo` vale para los dos (R4-A3.3).
_ASIG = {}
for _cod in AREAS_SEC:
    a = M.Asignatura(colegio_id=_COL.id, nombre=_cod, codigo=_cod[:10],
                     area='X', area_curricular_codigo=_cod, activo=True)
    _DB.add(a)
    _DB.flush()
    _ASIG[_cod] = a
_MUSICA = M.Asignatura(colegio_id=_COL.id, nombre='Musica', codigo='MUS',
                       area='X', area_curricular_codigo=None, activo=True)
_DB.add(_MUSICA)
_DB.commit()

_cursos = {}
_contador = [0]


def curso(nivel, grado_numero):
    """Un curso del colegio, creado una vez por (nivel, grado)."""
    clave = (nivel, grado_numero)
    if clave in _cursos:
        return _cursos[clave]
    c = M.Curso(colegio_id=_COL.id, nombre='A', grado_id=_GRADOS[clave].id,
                ano_escolar_id=_ANO.id, activo=True)
    _DB.add(c)
    _DB.commit()
    _cursos[clave] = c
    return c


def asignar(curso_obj, codigos):
    existentes = {a.asignatura_id for a in _DB.query(M.AsignacionProfesor)
                  .filter_by(curso_id=curso_obj.id).all()}
    for cod in codigos:
        asig = _ASIG[cod] if cod in _ASIG else _MUSICA
        if asig.id in existentes:
            continue
        _DB.add(M.AsignacionProfesor(
            colegio_id=_COL.id, profesor_id=_PROF.id, curso_id=curso_obj.id,
            asignatura_id=asig.id, ano_escolar_id=_ANO.id, activo=True))
    _DB.commit()


def estudiante(curso_obj=None):
    _contador[0] += 1
    e = M.Estudiante(colegio_id=_COL.id, matricula='A4-%d' % _contador[0],
                     nombre='E%d' % _contador[0], apellido='S',
                     curso_id=curso_obj.id if curso_obj else None,
                     no_lista=_contador[0], activo=True)
    _DB.add(e)
    _DB.commit()
    return e


def notas_sec(est, codigo, nota):
    for n in range(1, 5):
        _DB.add(M.CalificacionSecundaria(
            colegio_id=_COL.id, estudiante_id=est.id,
            asignatura_id=_ASIG[codigo].id, ano_escolar_id=_ANO.id,
            competencia_numero=n, p1=nota, p2=nota, p3=nota, p4=nota))
    _DB.commit()


def notas_prim(est, codigo, nota):
    for n in (1, 2, 3):
        _DB.add(M.CalificacionPrimaria(
            colegio_id=_COL.id, estudiante_id=est.id,
            asignatura_id=_ASIG[codigo].id, ano_escolar_id=_ANO.id,
            competencia_numero=n, competencia_nombre='C%d' % n,
            p1=nota, p2=nota, p3=nota, p4=nota))
    _DB.commit()


def recuperacion_prim(est, codigo, cf, final=None, especial=None):
    _DB.add(M.RecuperacionPrimaria(
        colegio_id=_COL.id, estudiante_id=est.id,
        asignatura_id=_ASIG[codigo].id, ano_escolar_id=_ANO.id,
        cf_area=cf, recuperacion_final=final, recuperacion_especial=especial))
    _DB.commit()


def extra_sec(est, codigo, **campos):
    _DB.add(M.EvaluacionExtraSecundaria(
        colegio_id=_COL.id, estudiante_id=est.id,
        asignatura_id=_ASIG[codigo].id, ano_escolar_id=_ANO.id, **campos))
    _DB.commit()


def sembrar_secundaria(grado, notas=None, extras=None):
    """Un estudiante de Secundaria con todo el curriculo cargado."""
    c = curso('secundaria', grado)
    asignar(c, AREAS_SEC)
    est = estudiante(c)
    for cod in AREAS_SEC:
        notas_sec(est, cod, (notas or {}).get(cod, 90))
    for cod, campos in (extras or {}).items():
        extra_sec(est, cod, **campos)
    return est


def sembrar_primaria(grado, notas=None, recuperaciones=None, extras_areas=()):
    c = curso('primaria', grado)
    oficiales = list(AD.curriculo_oficial_esperado(RA.NIVEL_PRIMARIA, grado)[0])
    asignar(c, oficiales + list(extras_areas))
    est = estudiante(c)
    for cod in oficiales + list(extras_areas):
        notas_prim(est, cod, (notas or {}).get(cod, 90))
    for cod, datos in (recuperaciones or {}).items():
        recuperacion_prim(est, cod, **datos)
    return est


class _Direccion:
    colegio_id = _COL.id
    role = 'direccion'
    id = 1


_USER = _Direccion()


def preview_cierre():
    """GET /api/cierre-ano/promocion, ejecutado de verdad."""
    return asyncio.run(APP.get_datos_promocion(db=_DB, current_user=_USER))


def preview_promocion():
    """GET /api/promocion/estudiantes, ejecutado de verdad."""
    return asyncio.run(APP.get_estudiantes_promocion(
        request=None, db=_DB, current_user=_USER))


def fila(est, datos=None):
    datos = datos if datos is not None else preview_cierre()
    for f in datos['estudiantes']:
        if f['id'] == est.id:
            return f
    raise AssertionError('el estudiante %s no aparece en la preview' % est.id)


# ═══════════════ LOS DOS GET COINCIDEN ═══════════════
print(f"\n{B}A4-1 · LA MISMA VERDAD EN LAS DOS PANTALLAS{X}")

_E_PROM = sembrar_secundaria(3)
_E_APL1 = sembrar_secundaria(2, notas={AREAS_SEC[0]: 50}, extras={
    AREAS_SEC[0]: dict(cf_original=50.0, cec=40.0, completiva_final=55.0,
                       ceex=40.0, extraordinaria_final=60.0)})


@test("A4-1  ambos GET dan la MISMA condicion canonica para cada estudiante")
def _():
    cierre = {f['id']: f['condicion_canonica'] for f in preview_cierre()['estudiantes']}
    promo = {f['id']: f['condicion_canonica'] for f in preview_promocion()['estudiantes']}
    igual(promo, cierre, 'dos pantallas de la misma Direccion no pueden '
                         'contradecirse sobre el mismo estudiante')
    assert cierre, 'la preview no puede venir vacia'


@test("A4-1b los dos endpoints llaman al MISMO helper")
def _():
    import inspect
    for nombre in ('get_estudiantes_promocion', 'get_datos_promocion'):
        fuente = inspect.getsource(getattr(APP, nombre))
        assert '_preview_promocion_canonica' in fuente, nombre


# ═══════════════ SECUNDARIA ═══════════════
print(f"\n{B}A4-2..7 · SECUNDARIA, LA CASCADA COMPLETA{X}")


def _caidas_extra(n):
    """`n` asignaturas que cayeron tras la Extraordinaria."""
    notas, extras = {}, {}
    for i in range(n):
        cod = AREAS_SEC[i]
        notas[cod] = 50
        extras[cod] = dict(cf_original=50.0, cec=40.0, completiva_final=55.0,
                           ceex=40.0, extraordinaria_final=60.0)
    return notas, extras


@test("A4-2  Secundaria sin fallos -> PROMOVIDO")
def _():
    igual(fila(_E_PROM)['condicion_canonica'], PA.PROMOVIDO)
    igual(fila(_E_PROM)['condicion'], 'promovido')


@test("A4-3  1 asignatura caida tras la Extraordinaria -> APLAZADO")
def _():
    f = fila(_E_APL1)
    igual(f['condicion_canonica'], PA.APLAZADO)
    igual(f['condicion'], 'aplazado')
    igual(f['requiere_evaluacion_especial'], True)


@test("A4-4  2 asignaturas caidas -> APLAZADO")
def _():
    notas, extras = _caidas_extra(2)
    est = sembrar_secundaria(4, notas=notas, extras=extras)
    igual(fila(est)['condicion_canonica'], PA.APLAZADO)


@test("A4-5  3 asignaturas caidas -> REPROBADO")
def _():
    notas, extras = _caidas_extra(3)
    est = sembrar_secundaria(5, notas=notas, extras=extras)
    f = fila(est)
    igual(f['condicion_canonica'], PA.REPROBADO)
    igual(f['condicion'], 'reprobado')


@test("A4-6  Evaluacion Especial superada -> PROMOVIDO")
def _():
    cod = AREAS_SEC[0]
    est = sembrar_secundaria(3, notas={cod: 50}, extras={cod: dict(
        cf_original=50.0, cec=40.0, completiva_final=55.0, ceex=40.0,
        extraordinaria_final=60.0, ce=80.0, especial_final=70.0)})
    igual(fila(est)['condicion_canonica'], PA.PROMOVIDO)


@test("A4-7  Evaluacion Especial fallida -> REPROBADO")
def _():
    cod = AREAS_SEC[0]
    est = sembrar_secundaria(3, notas={cod: 50}, extras={cod: dict(
        cf_original=50.0, cec=40.0, completiva_final=55.0, ceex=40.0,
        extraordinaria_final=60.0, ce=10.0, especial_final=55.0)})
    igual(fila(est)['condicion_canonica'], PA.REPROBADO)


# ═══════════════ PRIMARIA ═══════════════
print(f"\n{B}A4-8..11 · PRIMARIA POR CICLO{X}")


@test("A4-8  Primaria 1.o con Ingles adicional: no bloquea")
def _():
    est = sembrar_primaria(1, extras_areas=('LEI',))
    f = fila(est)
    igual(f['condicion_canonica'], PA.PROMOVIDO,
          'LEI no es oficial en 1.o: no puede frenar la promocion')
    igual(f['bloqueos'], [])
    igual(f['total_asignaturas'], 7)


@test("A4-9  Primaria 3.o sin dato de alfabetizacion -> EN_PROCESO")
def _():
    est = sembrar_primaria(3)
    f = fila(est)
    igual(f['condicion_canonica'], PA.EN_PROCESO)
    igual(f['condicion'], 'en_proceso')
    assert PA.BLOQUEO_ALFABETIZACION_NO_INFORMADA in f['bloqueos'], f['bloqueos']


@test("A4-10 Primaria 3.o APLAZADO sigue APLAZADO")
def _():
    est = sembrar_primaria(3, notas={'LE': 50},
                           recuperaciones={'LE': dict(cf=50, final=55)})
    f = fila(est)
    igual(f['condicion_canonica'], PA.APLAZADO,
          'la alfabetizacion llega despues del proceso especial (A2.3)')
    igual(f['requiere_recuperacion_especial'], True)


@test("A4-11 Primaria 4.o sin Ingles -> CURRICULO_OFICIAL_INCOMPLETO")
def _():
    c = curso('primaria', 4)
    oficiales = [x for x in AD.curriculo_oficial_esperado(
        RA.NIVEL_PRIMARIA, 4)[0] if x != 'LEI']
    asignar(c, oficiales)
    est = estudiante(c)
    for cod in oficiales:
        notas_prim(est, cod, 90)
    f = fila(est)
    igual(f['condicion_canonica'], PA.EN_PROCESO)
    assert PA.BLOQUEO_CURRICULO_INCOMPLETO in f['bloqueos'], f['bloqueos']


# ═══════════════ CASOS LIMITE ═══════════════
print(f"\n{B}A4-12..16 · LO QUE NO PUEDE INVENTARSE{X}")


@test("A4-12 estudiante sin curso -> EN_PROCESO, y NO desaparece")
def _():
    est = estudiante(None)
    f = fila(est)
    igual(f['condicion_canonica'], PA.EN_PROCESO)
    igual(f['curso'], None)
    igual(f['nuevo_grado'], None)
    assert APP.DIAG_ESTUDIANTE_SIN_CURSO in f['diagnosticos'], f['diagnosticos']


@test("A4-13 el promedio NO decide la condicion")
def _():
    # Un aplazado puede tener buen promedio y un promovido puede tenerlo justo.
    for f in preview_cierre()['estudiantes']:
        if f['promedio_general'] is None:
            continue
        assert f['condicion_canonica'] in PA.CONDICIONES
    # Y el promedio nunca aparece como criterio en el codigo migrado.
    import inspect
    for nombre in ('_fila_preview', '_preview_promocion_canonica',
                   '_promedio_informativo'):
        fuente = inspect.getsource(getattr(APP, nombre))
        for prohibido in ('>= 70', '< 70', '>= 65', '< 65'):
            assert prohibido not in fuente, '%s: %r' % (nombre, prohibido)


@test("A4-14 una ausencia desconocida NO se convierte en 0")
def _():
    # Con dias trabajados declarados sale un numero; sin ellos, None.
    con = fila(_E_PROM)['porcentaje_ausencias_no_justificadas']
    assert con is not None, 'con dias declarados debe calcularse'
    _ANO.set_dias_trabajados({})
    _DB.commit()
    try:
        sin = fila(_E_PROM)['porcentaje_ausencias_no_justificadas']
        igual(sin, None, 'sin denominador fiable, None; nunca 0%')
    finally:
        _ANO.set_dias_trabajados(DIAS)
        _DB.commit()


@test("A4-15 `Promovido condicional` no existe en ninguna respuesta")
def _():
    for datos in (preview_cierre(), preview_promocion()):
        texto = repr(datos)
        assert 'condicional' not in texto.lower(), 'sigue vivo'
        assert 'Sin calificaciones' not in texto
    for f in preview_cierre()['estudiantes']:
        assert f['condicion'] in ('promovido', 'aplazado', 'reprobado',
                                  'en_proceso'), f['condicion']


@test("A4-16 6.o de Secundaria PROMOVIDO no dice Graduado ni Egresado")
def _():
    est = sembrar_secundaria(6)
    f = fila(est)
    igual(f['condicion_canonica'], PA.PROMOVIDO)
    igual(f['nuevo_grado'], None, 'la titulacion no es un grado siguiente')
    igual(f['destino_diagnostico'], APP.DESTINO_TITULACION_PENDIENTE)
    assert PA.ADV_TITULACION_PENDIENTE in f['advertencias'], f['advertencias']
    texto = repr(f)
    for prohibido in ('Graduado', 'Egresado', 'Titulado'):
        assert prohibido not in texto, prohibido


# ═══════════════ DESTINO ═══════════════
print(f"\n{B}A4-17..19 · EL DESTINO PREVISTO{X}")


@test("A4-17 el destino usa (nivel, grado), no el `orden` global")
def _():
    # En este colegio Primaria tiene orden 7-12. `orden + 1` sobre un 3.o de
    # Secundaria (orden 3) daria "4to Secundaria" por casualidad, pero sobre un
    # 6.o de Secundaria (orden 6) daria "1ro Primaria". Eso es lo que se evita.
    est = sembrar_secundaria(3)
    igual(fila(est)['nuevo_grado'], '4to Secundaria')
    prim = sembrar_primaria(2)
    igual(fila(prim)['nuevo_grado'], '3ro Primaria')
    # 6.o de Primaria pasa a 1.o de Secundaria, no al siguiente `orden`.
    prim6 = sembrar_primaria(6)
    igual(fila(prim6)['nuevo_grado'], '1ro Secundaria')


@test("A4-18 un APLAZADO no tiene nuevo grado")
def _():
    f = fila(_E_APL1)
    igual(f['condicion_canonica'], PA.APLAZADO)
    igual(f['nuevo_grado'], None,
          'ofrecer un grado siguiente invitaria a promover a quien no ha '
          'terminado su proceso')
    igual(f['accion_sugerida'], None)
    igual(f['listo_para_decidir'], False)


@test("A4-19 un EN_PROCESO no tiene nuevo grado")
def _():
    est = sembrar_primaria(3)
    f = fila(est)
    igual(f['condicion_canonica'], PA.EN_PROCESO)
    igual(f['nuevo_grado'], None)
    igual(f['accion_sugerida'], None)
    igual(f['listo_para_decidir'], False)


@test("A4-19b un REPROBADO repite el grado que ya cursa")
def _():
    notas, extras = _caidas_extra(3)
    est = sembrar_secundaria(2, notas=notas, extras=extras)
    f = fila(est)
    igual(f['condicion_canonica'], PA.REPROBADO)
    igual(f['nuevo_grado'], '2do Secundaria')
    igual(f['accion_sugerida'], 'repite')


# ═══════════════ LA INTERFAZ ═══════════════
print(f"\n{B}A4-20..21 · LOS GUARDS DE LA PANTALLA{X}")

_FE = os.path.join(os.path.dirname(os.path.dirname(_AQUI)),
                   'frontend', 'src', 'pages', 'cierre-ano',
                   'CierreAnoPage.tsx')


def _fuente_fe():
    import io as _io
    return _io.open(_FE, encoding='utf-8').read()


@test("A4-20 un REPROBADO no se preselecciona como promover")
def _():
    notas, extras = _caidas_extra(4)
    est = sembrar_secundaria(4, notas=notas, extras=extras)
    igual(fila(est)['accion_sugerida'], 'repite')
    fe = _fuente_fe()
    # La pantalla ya no rellena con 'promueve' por omision.
    assert "acciones[est.id] || 'promueve'" not in fe, \
        'el default ciego a promover sigue vivo'
    assert 'e.accion_sugerida' in fe, 'la accion sale del motor'


@test("A4-21 APLAZADO / EN_PROCESO deshabilitan el boton de ejecutar")
def _():
    datos = preview_cierre()
    assert datos['hay_procesos_pendientes'] is True, \
        'la fixture tiene aplazados: el backend debe avisarlo'
    fe = _fuente_fe()
    assert 'listo_para_decidir' in fe
    assert 'disabled={!est.listo_para_decidir}' in fe, \
        'el selector de accion debe bloquearse'
    assert 'Hay estudiantes con proceso académico pendiente.' in fe
    assert "estudiantesPromocion.some(e => !e.listo_para_decidir)" in fe, \
        'el boton Ejecutar debe mirar si queda algo pendiente'


@test("A4-21b la pantalla representa los CUATRO estados")
def _():
    fe = _fuente_fe()
    for estado in ('promovido', 'aplazado', 'reprobado', 'en_proceso'):
        assert estado in fe, estado
    for texto in ('Promovido', 'Aplazado', 'Reprobado', 'En proceso'):
        assert texto in fe, texto
    # Y ya no traduce "todo lo que no sea promovido" a Reprobado.
    assert "est.condicion === 'promovido' ? 'Promovido' : 'Reprobado'" not in fe
    assert "est.promedio_general >= 70" not in fe, \
        'el promedio no puede pintar la situacion academica'


# ═══════════════ INVARIANTES ═══════════════
print(f"\n{B}A4-22..25 · LO QUE NO PUEDE CAMBIAR{X}")

_SHA_A3 = '3aa2020782c66325ab5bd6bbec1979e59be87e90'
_REPO = os.path.dirname(os.path.dirname(_AQUI))


def _cuerpo_en(sha, nombre):
    import ast as _ast
    import subprocess
    fuente = subprocess.run(['git', 'show', '%s:backend/app.py' % sha],
                            capture_output=True, cwd=_REPO).stdout.decode('utf-8')
    arbol = _ast.parse(fuente)
    for n in _ast.walk(arbol):
        if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef)) and n.name == nombre:
            # `end_lineno` y no `max(lineno)`: cuando la funcion termina en un
            # literal multilinea, el nodo con mayor `lineno` es la ultima clave
            # del dict, no la llave que lo cierra, y el fragmento salia
            # truncado — comparable como texto, pero imposible de parsear.
            return chr(10).join(fuente.splitlines()[n.lineno - 1:n.end_lineno])
    return None


def _cuerpo_actual(nombre):
    """El mismo troceo por AST que `_cuerpo_en`, sobre el app.py de disco.

    Comparar el corte por AST de git contra `inspect.getsource` no vale: uno
    incluye el decorador y el otro no, y los limites de linea difieren. Dos
    metodos distintos no comparan nada.
    """
    import ast as _ast
    import io as _io
    ruta = os.path.join(os.path.dirname(_AQUI), 'app.py')
    fuente = _io.open(ruta, encoding='utf-8').read()
    arbol = _ast.parse(fuente)
    for n in _ast.walk(arbol):
        if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef)) and n.name == nombre:
            return chr(10).join(fuente.splitlines()[n.lineno - 1:n.end_lineno])
    return None


def _cola_legacy(cuerpo):
    """El cuerpo sin la firma ni el docstring: solo la logica ejecutable.

    La comparacion byte a byte del cuerpo ENTERO dejo de servir cuando C1
    antepuso el safety lock. Pero lo que este invariante protege no es el
    docstring: es que nadie reescriba en silencio la logica legacy mientras
    dice estar bloqueandola. Esa logica es la cola, y la cola sigue exigiendose
    IDENTICA.
    """
    import ast as _ast
    lineas = cuerpo.splitlines()
    arbol = _ast.parse(cuerpo)
    fn = arbol.body[0]
    cuerpos = list(fn.body)
    if (cuerpos and isinstance(cuerpos[0], _ast.Expr)
            and isinstance(cuerpos[0].value, _ast.Constant)
            and isinstance(cuerpos[0].value.value, str)):
        cuerpos = cuerpos[1:]           # fuera el docstring
    assert cuerpos, 'funcion sin cuerpo ejecutable'
    return chr(10).join(lineas[cuerpos[0].lineno - 1:])


def _primera_sentencia(cuerpo):
    import ast as _ast
    fn = _ast.parse(cuerpo).body[0]
    cuerpos = [n for n in fn.body
               if not (isinstance(n, _ast.Expr)
                       and isinstance(n.value, _ast.Constant)
                       and isinstance(n.value.value, str))]
    return cuerpos[0]


@test("A4-22 la logica legacy de los POST sigue sin reescribirse")
def _():
    for nombre in ('ejecutar_promocion', 'ejecutar_promocion_cierre_ano',
                   'promover_estudiantes'):
        antes = _cuerpo_en(_SHA_A3, nombre)
        ahora = _cuerpo_actual(nombre)
        assert antes and ahora, nombre
        cola = _cola_legacy(antes)
        assert cola in ahora, (
            '%s: la logica legacy cambio, no solo se le antepuso un guard'
            % nombre)


@test("A4-22b lo unico que se les antepuso es el safety lock de C1")
def _():
    import ast as _ast
    for nombre in ('ejecutar_promocion', 'ejecutar_promocion_cierre_ano',
                   'promover_estudiantes', 'cerrar_ano_escolar'):
        n = _primera_sentencia(_cuerpo_actual(nombre))
        # La PRIMERA sentencia ejecutable debe ser el guard. Si alguien
        # colocase una consulta, un `await request.json()` o un log por
        # delante, el rechazo dejaria de ser fail-closed limpio.
        assert isinstance(n, _ast.If), (
            '%s: su primera sentencia ya no es el guard (%s)'
            % (nombre, type(n).__name__))
        assert isinstance(n.test, _ast.Name) and n.test.id == 'CIERRE_ANO_BLOQUEADO', (
            '%s: la primera sentencia no comprueba CIERRE_ANO_BLOQUEADO' % nombre)
        assert isinstance(n.body[0], _ast.Return), (
            '%s: el guard no retorna de inmediato' % nombre)


@test("A4-23 construir la preview NO escribe nada")
def _():
    from sqlalchemy import event
    escrituras = []

    def _vigilar(sesion, ctx, instancias):
        escrituras.append((list(sesion.new), list(sesion.dirty),
                           list(sesion.deleted)))

    event.listen(SessionLocal, 'before_flush', _vigilar)
    try:
        preview_cierre()
        preview_promocion()
        _DB.flush()
    finally:
        event.remove(SessionLocal, 'before_flush', _vigilar)
    igual([e for e in escrituras if any(e)], [],
          'una previsualizacion no puede mover a nadie')


@test("A4-23b la preview no usa `Estudiante.condicion` como verdad academica")
def _():
    # Por AST: se busca cualquier acceso al ATRIBUTO `condicion` de un objeto,
    # que es lo prohibido. Las claves de diccionario 'condicion' son salida,
    # no entrada, y buscarlas como texto solo producia ruido.
    import ast as _ast
    import inspect
    import textwrap
    for nombre in ('_preview_promocion_canonica', '_fila_preview',
                   '_destino_previsto', 'get_datos_promocion',
                   'get_estudiantes_promocion'):
        arbol = _ast.parse(textwrap.dedent(inspect.getsource(getattr(APP, nombre))))
        for n in _ast.walk(arbol):
            if isinstance(n, _ast.Attribute):
                assert n.attr != 'condicion',                     '%s lee el atributo `condicion` de un objeto' % nombre
        # Sobre codigo SIN comentarios ni cadenas: el docstring del helper
        # EXPLICA que no se usa `Estudiante.condicion`, y buscarlo como texto
        # acusaba justo al parrafo que lo prohibe.
        import io as _io
        import tokenize as _tk
        _fuente = textwrap.dedent(inspect.getsource(getattr(APP, nombre)))
        _trozos = [t.string for t in _tk.generate_tokens(
            _io.StringIO(_fuente).readline)
            if t.type not in (_tk.COMMENT, _tk.STRING)]
        assert 'Estudiante . condicion' not in ' '.join(_trozos), nombre


@test("A4-24 aislamiento de tenant: otro colegio no ve estos estudiantes")
def _():
    otro = M.Colegio(nombre='Otro', codigo='OTRO1', activo=True)
    _DB.add(otro)
    _DB.commit()

    class Ajeno:
        colegio_id = otro.id
        role = 'direccion'
        id = 2

    datos = asyncio.run(APP.get_datos_promocion(db=_DB, current_user=Ajeno()))
    igual(datos['estudiantes'], [],
          'la preview de un colegio no puede filtrar al de al lado')
    assert preview_cierre()['estudiantes'], 'el propio si ve los suyos'


@test("A4-25 el numero de consultas crece por CURSO, no por estudiante")
def _():
    # Contar consultas contra un umbral absoluto no mide nada: depende de
    # cuantos cursos tenga la fixture. Lo que distingue un N+1 es el
    # CRECIMIENTO: se mide el mismo curso con 3 alumnos y luego con 9, y el
    # numero de consultas tiene que ser el mismo.
    from sqlalchemy import event
    c = curso('secundaria', 1)
    asignar(c, AREAS_SEC)

    def poblar(cuantos):
        for _ in range(cuantos):
            est = estudiante(c)
            for cod in AREAS_SEC:
                notas_sec(est, cod, 85)

    def medir():
        consultas = []

        def _contar(conn, cursor, statement, params, ctx, many):
            if statement.lstrip().upper().startswith('SELECT'):
                consultas.append(statement)

        event.listen(engine, 'before_cursor_execute', _contar)
        try:
            preview_cierre()
        finally:
            event.remove(engine, 'before_cursor_execute', _contar)
        return len(consultas)

    poblar(3)
    con_pocos = medir()
    poblar(6)
    con_muchos = medir()

    igual(con_muchos, con_pocos,
          'triplicar el alumnado de un curso no puede cambiar el numero de '
          'consultas: eso seria N+1')
    # Y el coste total sigue siendo del orden del numero de cursos.
    cursos = len({f['curso_id'] for f in preview_cierre()['estudiantes']})
    assert con_muchos <= cursos * 12 + 12,         '%d consultas para %d cursos' % (con_muchos, cursos)


# ═══════════════ ESTATICOS ═══════════════
print(f"\n{B}ESTATICOS: LAS REGLAS VIEJAS NO VUELVEN{X}")

_MIGRADOS = ('get_estudiantes_promocion', 'get_datos_promocion',
             '_preview_promocion_canonica', '_fila_preview',
             '_destino_previsto')


def codigo_efectivo(fuente):
    """Sin comentarios ni cadenas: prohibir una regla no es prohibir nombrarla."""
    import io as _io
    import tokenize
    trozos = []
    for tok in tokenize.generate_tokens(_io.StringIO(fuente).readline):
        if tok.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        trozos.append(tok.string)
    return ' '.join(trozos)


@test("S1  ningun camino migrado decide con cortes numericos")
def _():
    import inspect
    import textwrap
    for nombre in _MIGRADOS:
        fuente = codigo_efectivo(textwrap.dedent(
            inspect.getsource(getattr(APP, nombre))))
        for prohibido in ('>= 70', '< 70', '>= 65', '< 65',
                          'asignaturas_reprobadas == 0', 'todas_aprobadas',
                          'valor_periodo', 'calcular_pc_periodo'):
            assert prohibido not in fuente, '%s: %r' % (nombre, prohibido)


@test("S2  ningun camino migrado resuelve el destino con `orden + 1`")
def _():
    import inspect
    import textwrap
    for nombre in _MIGRADOS:
        fuente = codigo_efectivo(textwrap.dedent(
            inspect.getsource(getattr(APP, nombre))))
        for prohibido in ('orden + 1', 'Grado . orden', 'orden >'):
            assert prohibido not in fuente, '%s: %r' % (nombre, prohibido)


@test("S3  A1, A2 y A3 siguen congelados")
def _():
    import subprocess
    for sha, ruta in (('25d6d649b2d97cea2134f4fe23aaa917ca6b7585',
                       'backend/resultado_academico.py'),
                      ('d784da67dc279d018abb45b8dc25d482752d18a5',
                       'backend/promocion_academica.py'),
                      (_SHA_A3, 'backend/resultado_academico_consumidores.py'),
                      (_SHA_A3, 'backend/catalogo_primaria.py'),
                      (_SHA_A3, 'backend/models.py')):
        d = subprocess.run(['git', 'diff', '--stat', sha, '--', ruta],
                           capture_output=True, cwd=_REPO).stdout.decode('utf-8')
        igual(d.strip(), '', ruta)




# ═══════════ A4Y · EL AÑO ACADEMICO ORIGEN ═══════════
#
# AÑO ACTIVO NO ES AÑO QUE SE ESTA PROMOVIENDO.
#
# El flujo real de Cierre cierra 2025-2026 y crea 2026-2027, que queda activo
# y VACIO. Preferir el ano activo hacia que la preview mirara ahi: un
# estudiante PROMOVIDO pasaba a EN_PROCESO por CURRICULO_OFICIAL_INCOMPLETO.
# Crear el ano siguiente cambiaba la situacion academica del ano que se estaba
# cerrando.
print(f"\n{B}A4Y · EL AÑO ORIGEN, FIJADO{X}")

# Un colegio aparte, para no perturbar el resto de la suite.
_DB2 = SessionLocal()
_COL2 = M.Colegio(nombre='A4Y', codigo='A4YTEST', activo=True)
_DB2.add(_COL2)
_DB2.flush()

# Ano A: el que se promueve. Cerrado, con TODAS las notas.
_ANO_A = M.AnoEscolar(colegio_id=_COL2.id, nombre='2025-2026', activo=False,
                      cerrado=True)
_ANO_A.set_dias_trabajados(DIAS)
# Ano B: el destino. Activo y sin una sola calificacion.
_ANO_B = M.AnoEscolar(colegio_id=_COL2.id, nombre='2026-2027', activo=True,
                      cerrado=False)
_GRD2 = M.Grado(colegio_id=_COL2.id, nombre='3ro Secundaria',
                nivel='secundaria', orden=3, activo=True)
_DB2.add_all([_ANO_A, _ANO_B, _GRD2])
_DB2.flush()
_CURSO2 = M.Curso(colegio_id=_COL2.id, nombre='A', grado_id=_GRD2.id,
                  ano_escolar_id=_ANO_A.id, activo=True)
_PROF2 = M.Usuario(colegio_id=_COL2.id, nombre='P', username='a4yprof',
                   password_hash='x', role='profesor', activo=True)
_DB2.add_all([_CURSO2, _PROF2])
_DB2.flush()
_EST2 = M.Estudiante(colegio_id=_COL2.id, matricula='A4Y-1', nombre='E',
                     apellido='S', curso_id=_CURSO2.id, activo=True)
_DB2.add(_EST2)
_DB2.flush()
for _cod in AREAS_SEC:
    _a = M.Asignatura(colegio_id=_COL2.id, nombre=_cod, codigo=_cod[:10],
                      area='X', area_curricular_codigo=_cod, activo=True)
    _DB2.add(_a)
    _DB2.flush()
    _DB2.add(M.AsignacionProfesor(
        colegio_id=_COL2.id, profesor_id=_PROF2.id, curso_id=_CURSO2.id,
        asignatura_id=_a.id, ano_escolar_id=_ANO_A.id, activo=True))
    for _n in range(1, 5):
        _DB2.add(M.CalificacionSecundaria(
            colegio_id=_COL2.id, estudiante_id=_EST2.id, asignatura_id=_a.id,
            ano_escolar_id=_ANO_A.id, competencia_numero=_n,
            p1=90, p2=90, p3=90, p4=90))
_DB2.commit()


class _Direccion2:
    colegio_id = _COL2.id
    role = 'direccion'
    id = 3


_USER2 = _Direccion2()


def cierre2(ano_id=None):
    return asyncio.run(APP.get_datos_promocion(
        ano_id=ano_id, db=_DB2, current_user=_USER2))


def promocion2(ano_id=None):
    return asyncio.run(APP.get_estudiantes_promocion(
        request=None, ano_id=ano_id, db=_DB2, current_user=_USER2))


@test("A4Y-1 tras crear el ano nuevo, el Cierre sigue mirando el ano CERRADO")
def _():
    datos = cierre2()
    igual(datos['ano_escolar_id'], _ANO_A.id,
          'el ano nuevo esta vacio: mirar ahi convierte un PROMOVIDO en '
          'EN_PROCESO por curriculo incompleto')
    igual(datos['ano_escolar'], '2025-2026')
    f = datos['estudiantes'][0]
    igual(f['condicion_canonica'], PA.PROMOVIDO)
    igual(f['bloqueos'], [])


@test("A4Y-2 con `ano_id` explicito, los dos GET dan lo mismo")
def _():
    a = cierre2(ano_id=_ANO_A.id)
    b = promocion2(ano_id=_ANO_A.id)
    igual(a['ano_escolar_id'], _ANO_A.id)
    igual(b['ano_escolar_id'], _ANO_A.id)
    igual({f['id']: f['condicion_canonica'] for f in b['estudiantes']},
          {f['id']: f['condicion_canonica'] for f in a['estudiantes']},
          'el mismo ano tiene que dar la misma verdad academica')
    # Y con el ano vacio, los dos coinciden tambien: en que no se puede.
    a2 = cierre2(ano_id=_ANO_B.id)
    b2 = promocion2(ano_id=_ANO_B.id)
    igual({f['id']: f['condicion_canonica'] for f in b2['estudiantes']},
          {f['id']: f['condicion_canonica'] for f in a2['estudiantes']})
    igual(a2['estudiantes'][0]['condicion_canonica'], PA.EN_PROCESO)


@test("A4Y-3 la promocion general SIN parametro conserva el ano ACTIVO")
def _():
    datos = promocion2()
    igual(datos['ano_escolar_id'], _ANO_B.id,
          'este endpoint es de consulta durante el curso: su ano es el activo')


@test("A4Y-4 el Cierre SIN parametro toma el cerrado mas reciente")
def _():
    igual(cierre2()['ano_escolar_id'], _ANO_A.id)


@test("A4Y-5 antes de cerrar nada, el Cierre usa el activo y NO viene vacio")
def _():
    # Un colegio que todavia no cerro ningun ano.
    col = M.Colegio(nombre='Nuevo', codigo='NUEVO1', activo=True)
    _DB2.add(col)
    _DB2.flush()
    ano = M.AnoEscolar(colegio_id=col.id, nombre='2025-2026', activo=True,
                       cerrado=False)
    ano.set_dias_trabajados(DIAS)
    grd = M.Grado(colegio_id=col.id, nombre='2do Primaria', nivel='primaria',
                  orden=8, activo=True)
    _DB2.add_all([ano, grd])
    _DB2.flush()
    c = M.Curso(colegio_id=col.id, nombre='A', grado_id=grd.id,
                ano_escolar_id=ano.id, activo=True)
    prof = M.Usuario(colegio_id=col.id, nombre='P', username='nuevoprof',
                     password_hash='x', role='profesor', activo=True)
    _DB2.add_all([c, prof])
    _DB2.flush()
    est = M.Estudiante(colegio_id=col.id, matricula='N-1', nombre='E',
                       apellido='S', curso_id=c.id, activo=True)
    _DB2.add(est)
    _DB2.flush()
    for cod in AD.curriculo_oficial_esperado(RA.NIVEL_PRIMARIA, 2)[0]:
        a = M.Asignatura(colegio_id=col.id, nombre=cod, codigo=cod[:10],
                         area='X', area_curricular_codigo=cod, activo=True)
        _DB2.add(a)
        _DB2.flush()
        _DB2.add(M.AsignacionProfesor(
            colegio_id=col.id, profesor_id=prof.id, curso_id=c.id,
            asignatura_id=a.id, ano_escolar_id=ano.id, activo=True))
        for n in (1, 2, 3):
            _DB2.add(M.CalificacionPrimaria(
                colegio_id=col.id, estudiante_id=est.id, asignatura_id=a.id,
                ano_escolar_id=ano.id, competencia_numero=n,
                competencia_nombre='C%d' % n, p1=90, p2=90, p3=90, p4=90))
    _DB2.commit()

    class Usr:
        colegio_id = col.id
        role = 'direccion'
        id = 4

    datos = asyncio.run(APP.get_datos_promocion(db=_DB2, current_user=Usr()))
    igual(datos['ano_escolar_id'], ano.id,
          'sin ningun ano cerrado, el Cierre usa el activo')
    assert datos['estudiantes'], 'no puede venir vacio solo por no haber cerrado'
    igual(datos['estudiantes'][0]['condicion_canonica'], PA.PROMOVIDO)


@test("A4Y-6 un `ano_id` de otro colegio no revela nada")
def _():
    from fastapi import HTTPException
    # `_ANO_A` es del colegio A4Y; se pide desde el colegio de la suite.
    for endpoint in (APP.get_datos_promocion,):
        try:
            asyncio.run(endpoint(ano_id=_ANO_A.id, db=_DB, current_user=_USER))
            raise AssertionError('un ano de otro colegio no puede resolverse')
        except HTTPException as e:
            igual(e.status_code, 404,
                  'mismo 404 que un id inexistente: sin filtracion')
    try:
        asyncio.run(APP.get_estudiantes_promocion(
            request=None, ano_id=_ANO_A.id, db=_DB, current_user=_USER))
        raise AssertionError('un ano de otro colegio no puede resolverse')
    except HTTPException as e:
        igual(e.status_code, 404)
    # Un id que no existe en ningun sitio da exactamente lo mismo.
    try:
        asyncio.run(APP.get_datos_promocion(
            ano_id=999999, db=_DB, current_user=_USER))
        raise AssertionError('deberia ser 404')
    except HTTPException as e:
        igual(e.status_code, 404)


@test("A4Y-7 la pantalla pide el ano ORIGEN, nunca el destino")
def _():
    fe = _fuente_fe()
    assert 'anoOrigenId' in fe, 'falta el estado del ano origen'
    # La carga de la preview manda `ano_id`, y el valor sale del origen.
    assert 'params: { ano_id: origen }' in fe, fe[:0]
    assert 'const origen = origenId ?? anoOrigenId' in fe
    # Y el destino NUNCA se usa para LEER NOTAS. Se mira la llamada de la
    # preview, no una subcadena suelta: `nuevo_ano_id: nuevoAnoId` es el
    # destino del POST de promocion y es correcto que exista.
    assert 'cargarDatosPromocion(nuevoAnoId)' not in fe
    assert 'cargarDatosPromocion(anoId)' not in fe
    _carga = fe[fe.index('const cargarDatosPromocion'):
                fe.index('const cargarDatosPromocion') + 900]
    assert 'nuevoAnoId' not in _carga,         'la carga de la preview no puede tocar el ano destino'
    assert "api.get('/cierre-ano/promocion'" in _carga
    # El origen se captura ANTES de crear el ano siguiente.
    pos_captura = fe.index('const origenId = anoOrigenId')
    pos_crear = fe.index("await api.post('/ano-escolar', nuevoAno)")
    assert pos_captura < pos_crear, \
        'el origen hay que anotarlo antes de que el ano nuevo pase a activo'
    assert 'await cargarDatosPromocion(origenId)' in fe


@test("A4Y-8 tras un refresco, sin estado en el navegador, el Cierre acierta")
def _():
    # No se manda `ano_id`: es exactamente lo que ocurre cuando el usuario
    # recarga la pagina y React perdio su estado. La garantia es del backend.
    datos = cierre2(ano_id=None)
    igual(datos['ano_escolar_id'], _ANO_A.id)
    igual(datos['estudiantes'][0]['condicion_canonica'], PA.PROMOVIDO)
    # Y la respuesta dice que ano se uso, para que la pantalla lo recupere.
    assert 'ano_escolar_id' in datos and 'ano_escolar' in datos
    fe = _fuente_fe()
    assert 'if (res.data?.ano_escolar_id) setAnoOrigenId(res.data.ano_escolar_id);' in fe


@test("A4Y-9 los cursos del ano origen son los que se leen")
def _():
    # El estudiante sigue en su curso del ano A; el ano B no tiene cursos.
    datos = cierre2()
    f = datos['estudiantes'][0]
    igual(f['curso_id'], _CURSO2.id)
    igual(f['grado_actual'], '3ro Secundaria')
    igual(f['total_asignaturas'], len(AREAS_SEC))


@test("A4Y-10 el resolver es explicito sobre sus tres caminos")
def _():
    import inspect
    firma = inspect.signature(APP._resolver_ano_preview).parameters
    igual(sorted(firma), ['ano_id', 'current_user', 'db', 'preferir_cerrado'])
    cuerpo = inspect.getsource(APP._resolver_ano_preview)
    assert 'get_tenant_or_404' in cuerpo, 'el ano_id del cliente es tenant-safe'
    # Y el endpoint de Cierre pide el cerrado.
    assert 'preferir_cerrado=True' in inspect.getsource(APP.get_datos_promocion)
    assert 'preferir_cerrado' not in inspect.getsource(
        APP.get_estudiantes_promocion), \
        'la promocion general conserva su semantica de ano activo'


print("\n" + "=" * 70)
if _fail:
    print(f"{R}{B}R4-A4: {len(_fail)} fallo(s) de {_total}{X}")
    for n, e in _fail:
        print(f"  - {n}: {e}")
    sys.exit(1)
print(f"{B}R4-A4 PREVIEW CANONICA: {_ok}/{_total} pruebas{X}")
print(f"{G}{B}TODO VERDE{X}")
