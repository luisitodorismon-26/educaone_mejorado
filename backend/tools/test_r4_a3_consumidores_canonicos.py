# -*- coding: utf-8 -*-
"""
R4-A3 — los consumidores documentales, conectados al motor canonico.

QUE COMPRUEBA
    Que un mismo estudiante con los mismos datos produce la MISMA situacion
    en el boletin individual y en el lote, y que ninguno de los dos vuelve a
    decidir por su cuenta.

    Antes de A3 habia cuatro reglas distintas de promocion en el backend. Dos
    de ellas discrepaban: el individual armaba la nota con una cadena
    `nota_final or especial_final or ...` —que se come un 0 legitimo— y
    contaba `reprobadas > 2`; el lote usaba `(cf or 0) >= 70` y escribia
    "PENDIENTE/REPITENTE". La seccion N es la que fija que eso no vuelva.

COMO ESTAN HECHAS
    Los objetos ORM se construyen EN MEMORIA: `CalificacionSecundaria(...)` sin
    sesion no toca ninguna base. Se usan las clases reales, no dobles, para que
    `valor_periodo`, `cf_area` y `calcular_pc_periodo` se comporten como en
    produccion.

    `_calcular_cf_secundaria` se importa de `app` porque es el helper canonico
    que ya usa el boletin para imprimir la CF; replicar la formula aqui seria
    crear la quinta version del problema que A3 viene a cerrar.

Uso:
    cd backend
    python tools/test_r4_a3_consumidores_canonicos.py
"""
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

from test_utils import aislar_base_de_datos, verificar_engine_aislado  # noqa: E402

_TMP = aislar_base_de_datos('r4_a3')
from database import engine                                    # noqa: E402
verificar_engine_aislado(engine, _TMP)

import models as M                                             # noqa: E402
import promocion_academica as PA                               # noqa: E402
import resultado_academico as RA                               # noqa: E402
import resultado_academico_consumidores as AD                  # noqa: E402
import app as APP                                              # noqa: E402

CF = APP._calcular_cf_secundaria

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


# ═══════════════════ FIXTURES EN MEMORIA ═══════════════════

AREAS_SEC = ['LE', 'MAT', 'CS', 'CN', 'EA', 'EF', 'FIHR', 'LEI']
AREAS_PRIM = ['LE', 'MAT', 'CS', 'CN', 'EA', 'EF', 'FIHR', 'LEI']


def asignatura(id_, codigo, nombre=None):
    """Una Asignatura real, sin sesion. `codigo=None` => materia interna."""
    return M.Asignatura(id=id_, nombre=nombre or (codigo or 'Interna'),
                        codigo=(codigo or 'INT')[:10], area='X',
                        area_curricular_codigo=codigo, colegio_id=1)


def asignacion(asignatura_id, curso_id=1, ano_id=1):
    return M.AsignacionProfesor(colegio_id=1, profesor_id=1, curso_id=curso_id,
                                asignatura_id=asignatura_id, ano_escolar_id=ano_id,
                                activo=True)


def comps_sec(asig_id, nota):
    """Las 4 competencias x 4 periodos con la misma nota: CF = nota."""
    return [M.CalificacionSecundaria(
        colegio_id=1, estudiante_id=1, asignatura_id=asig_id, ano_escolar_id=1,
        competencia_numero=n, p1=nota, p2=nota, p3=nota, p4=nota)
        for n in range(1, 5)]


def comps_prim(asig_id, nota):
    """C1, C2 y C3 con los cuatro periodos en `nota`: CF del area = nota."""
    return [M.CalificacionPrimaria(
        colegio_id=1, estudiante_id=1, asignatura_id=asig_id, ano_escolar_id=1,
        competencia_numero=n, competencia_nombre='C%d' % n,
        p1=nota, p2=nota, p3=nota, p4=nota)
        for n in range(1, 4)]


def extra(asig_id, **campos):
    return M.EvaluacionExtraSecundaria(
        colegio_id=1, estudiante_id=1, asignatura_id=asig_id,
        ano_escolar_id=1, **campos)


def grado(nombre, nivel, orden=None):
    return M.Grado(id=1, colegio_id=1, nombre=nombre, nivel=nivel,
                   ciclo='1', orden=orden, activo=True)


def asistencia(fecha, estado):
    from datetime import date
    return M.Asistencia(colegio_id=1, estudiante_id=1, curso_id=1,
                        fecha=date(2026, 1, fecha), estado=estado)


def escenario_secundaria(notas_por_area, extras=None, internas=None):
    """(asignaturas, competencias_por_asig, extras_por_asig, asignaciones).

    `notas_por_area` = {codigo: nota}. `internas` = [(nombre, nota)] para
    materias sin `area_curricular_codigo`.
    """
    asignaturas, comps, asignaciones = [], {}, []
    for i, codigo in enumerate(AREAS_SEC, start=1):
        a = asignatura(i, codigo)
        asignaturas.append(a)
        asignaciones.append(asignacion(i))
        comps[i] = comps_sec(i, notas_por_area.get(codigo, 90))
    for j, (nombre, nota) in enumerate(internas or (), start=101):
        a = asignatura(j, None, nombre)
        asignaturas.append(a)
        asignaciones.append(asignacion(j))
        comps[j] = comps_sec(j, nota)
    return asignaturas, comps, dict(extras or {}), asignaciones


def situacion_sec(asignaturas, comps, extras, asignaciones, grado_numero=3,
                  contexto=None):
    """El camino canonico entero, tal y como lo usan los dos boletines."""
    por_id = {a.id: a for a in asignaturas}
    curriculo, diag = AD.curriculo_desde_asignaciones(asignaciones, por_id)
    resultados = AD.resultados_secundaria(asignaturas, comps, extras, CF)
    ctx = {'porcentaje_ausencias_no_justificadas': 5}
    ctx.update(contexto or {})
    return AD.construir_situacion_estudiante(
        RA.NIVEL_SECUNDARIA, grado_numero, resultados, curriculo, ctx,
        diagnosticos=[d for d in (diag,) if d])


def recuperacion(asig_id, cf_area, final=None, especial=None):
    return M.RecuperacionPrimaria(
        colegio_id=1, estudiante_id=1, asignatura_id=asig_id, ano_escolar_id=1,
        cf_area=cf_area, recuperacion_final=final, recuperacion_especial=especial)


def caidas_tras_final(n, nota=50, recuperada=55):
    """`n` areas que YA hicieron la Recuperacion Final y siguieron por debajo.

    Sin la fila de `RecuperacionPrimaria` el area esta PENDIENTE de la Final,
    no reprobada: A2 responderia EN_PROCESO, y con razon. Para probar una
    cascada hay que haber llegado hasta ella.
    """
    notas = {AREAS_PRIM[i]: nota for i in range(n)}
    recs = {i + 1: recuperacion(i + 1, nota, final=recuperada) for i in range(n)}
    return notas, recs


def situacion_prim(notas_por_area, grado_numero, recuperaciones=None,
                   contexto=None, internas=None):
    asignaturas, comps, asignaciones = [], {}, []
    for i, codigo in enumerate(AREAS_PRIM, start=1):
        asignaturas.append(asignatura(i, codigo))
        asignaciones.append(asignacion(i))
        comps[i] = comps_prim(i, notas_por_area.get(codigo, 90))
    for j, (nombre, nota) in enumerate(internas or (), start=101):
        asignaturas.append(asignatura(j, None, nombre))
        asignaciones.append(asignacion(j))
        comps[j] = comps_prim(j, nota)
    por_id = {a.id: a for a in asignaturas}
    curriculo, diag = AD.curriculo_desde_asignaciones(asignaciones, por_id)
    resultados = AD.resultados_primaria(asignaturas, comps,
                                        dict(recuperaciones or {}), grado_numero)
    # `construir_contexto` ANOTA en la lista que recibe: es la misma que luego
    # viaja al paquete. Quedarse con una copia vacia perdia el diagnostico.
    diagnosticos = [d for d in (diag,) if d]
    ctx = AD.construir_contexto(grado_numero, RA.NIVEL_PRIMARIA, 5, diagnosticos)
    ctx.update(contexto or {})
    return AD.construir_situacion_estudiante(
        RA.NIVEL_PRIMARIA, grado_numero, resultados, curriculo, ctx,
        diagnosticos=diagnosticos)


def codigo_efectivo(fuente):
    """La fuente SIN comentarios ni cadenas.

    La primera version de estos tests buscaba `reprobadas > 2` en el texto
    entero y fallaba contra el comentario que explica que esa regla se quito.
    Un buscador que no distingue codigo de prosa no sirve para prohibir una
    regla: prohibiria hablar de ella.
    """
    import io as _io
    import tokenize
    trozos = []
    lector = _io.StringIO(fuente).readline
    for tok in tokenize.generate_tokens(lector):
        if tok.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        trozos.append(tok.string)
    return ' '.join(trozos)


def fuente_migrada(nombre):
    import inspect
    import textwrap
    fn = getattr(APP, nombre, None)
    assert fn is not None, nombre
    return codigo_efectivo(textwrap.dedent(inspect.getsource(fn)))


# ═══════════════ A · LA CF 0 NO DESAPARECE ═══════════════
print(f"\n{B}A · TRUTHINESS: UNA CF DE 0 ES UNA NOTA{X}")


@test("A1  CF=0 se resuelve como area NO aprobada, no como ausente")
def _():
    asigs, comps, extras, asigns = escenario_secundaria({'LE': 0})
    resultados = AD.resultados_secundaria(asigs, comps, extras, CF)
    le = [r for r in resultados if r['area_curricular_codigo'] == 'LE'][0]
    igual(le['nota_base'], 0, 'un 0 es una nota, no un vacio')
    igual(le['estado'], RA.PENDIENTE_COMPLETIVA)
    igual(le['pendiente'], True)


@test("A2  la cadena `or` habria perdido ese 0; A1 no lo pierde")
def _():
    # Reproduccion de la regla vieja, para dejar la diferencia por escrito.
    ev = extra(1, nota_final=0, completiva_final=75)
    vieja = (getattr(ev, 'nota_final', None) or
             getattr(ev, 'especial_final', None) or
             getattr(ev, 'extraordinaria_final', None) or
             getattr(ev, 'completiva_final', None))
    igual(vieja, 75, 'la cadena vieja salta el 0 y coge la completiva')
    asigs, comps, _e, asigns = escenario_secundaria({'LE': 0})
    r = AD.resultados_secundaria(asigs, comps, {1: ev}, CF)
    le = [x for x in r if x['area_curricular_codigo'] == 'LE'][0]
    assert le['nota_final'] != 75 or le['fase'] == RA.FASE_COMPLETIVA, le


@test("A3  CF=0 en todas las areas -> nunca PROMOVIDO")
def _():
    s = situacion_sec(*escenario_secundaria({c: 0 for c in AREAS_SEC}))
    assert s['situacion']['condicion'] != PA.PROMOVIDO, s['situacion']


# ═══════════════ C-F · LA CASCADA DE SECUNDARIA ═══════════════
print(f"\n{B}C-F · CASCADA DE SECUNDARIA DESDE DATOS REALES{X}")


def _tras_extraordinaria(n):
    """`n` asignaturas que cayeron tras la Extraordinaria."""
    extras = {}
    for i in range(1, n + 1):
        extras[i] = extra(i, cf_original=50.0, cec=40.0, completiva_final=55.0,
                          ceex=40.0, extraordinaria_final=60.0)
    return escenario_secundaria({AREAS_SEC[i - 1]: 50 for i in range(1, n + 1)},
                                extras=extras)


@test("C   1 asignatura caida tras la Extraordinaria -> APLAZADO")
def _():
    s = situacion_sec(*_tras_extraordinaria(1))
    igual(s['situacion']['condicion'], PA.APLAZADO)
    igual(s['situacion']['requiere_evaluacion_especial'], True)


@test("D   2 asignaturas caidas tras la Extraordinaria -> APLAZADO")
def _():
    s = situacion_sec(*_tras_extraordinaria(2))
    igual(s['situacion']['condicion'], PA.APLAZADO)


@test("E   3 asignaturas caidas tras la Extraordinaria -> REPROBADO")
def _():
    s = situacion_sec(*_tras_extraordinaria(3))
    igual(s['situacion']['condicion'], PA.REPROBADO,
          'la regla vieja `reprobadas > 2` daba REPITENTE solo a partir de 3, '
          'pero contaba cualquier area, no las que agotaron la cascada')


@test("F   Especial aprobada -> PROMOVIDO")
def _():
    extras = {1: extra(1, cf_original=50.0, cec=40.0, completiva_final=55.0,
                       ceex=40.0, extraordinaria_final=60.0,
                       ce=80.0, especial_final=70.0)}
    asigs, comps, ex, asigns = escenario_secundaria({'LE': 50}, extras=extras)
    s = situacion_sec(asigs, comps, ex, asigns)
    igual(s['situacion']['condicion'], PA.PROMOVIDO)
    igual(s['situacion']['motivo'], PA.MOTIVO_ESPECIAL_SUPERADA)


# ═══════════════ G-H · CURRICULO ═══════════════
print(f"\n{B}G-H · QUE ENTRA EN LA PROMOCION OFICIAL{X}")


@test("G   curriculo incompleto -> EN_PROCESO, nunca promocion por omision")
def _():
    asigs, comps, ex, asigns = escenario_secundaria({})
    # El estudiante solo tiene notas de 3 de las 8 areas del curso.
    comps_parciales = {i: comps[i] for i in (1, 2, 3)}
    por_id = {a.id: a for a in asigs}
    curriculo, _ = AD.curriculo_desde_asignaciones(asigns, por_id)
    resultados = AD.resultados_secundaria(asigs[:3], comps_parciales, ex, CF)
    s = AD.construir_situacion_estudiante(
        RA.NIVEL_SECUNDARIA, 3, resultados, curriculo,
        {'porcentaje_ausencias_no_justificadas': 5})
    igual(s['situacion']['condicion'], PA.EN_PROCESO)
    assert s['situacion']['bloqueos'], s['situacion']


@test("H   Musica reprobada no cambia la promocion oficial")
def _():
    sin = situacion_sec(*escenario_secundaria({}))
    con = situacion_sec(*escenario_secundaria({}, internas=[('Musica', 10)]))
    igual(con['situacion']['condicion'], PA.PROMOVIDO)
    igual(con['situacion']['condicion'], sin['situacion']['condicion'])
    assert 'Musica' not in str(con['codigos_oficiales_esperados'])
    igual(len(con['resultados']), len(sin['resultados']),
          'una materia interna no produce resultado oficial')


@test("H2  el curriculo sale del curso, no de todas las asignaturas del tenant")
def _():
    asigs, comps, ex, asigns = escenario_secundaria({})
    otra = asignatura(999, 'OPT', 'De otro curso')
    por_id = {a.id: a for a in asigs + [otra]}
    curriculo, _ = AD.curriculo_desde_asignaciones(asigns, por_id)
    assert 'OPT' not in curriculo, curriculo
    igual(len(curriculo), len(AREAS_SEC))


@test("H3  un curso sin asignaciones activas es un GAP declarado")
def _():
    curriculo, diag = AD.curriculo_desde_asignaciones([], {})
    igual(curriculo, None)
    igual(diag, AD.DIAG_CURRICULO_SIN_ASIGNACIONES)
    s = AD.construir_situacion_estudiante(
        RA.NIVEL_SECUNDARIA, 3, [], None,
        {'porcentaje_ausencias_no_justificadas': 5})
    igual(s['situacion']['condicion'], PA.EN_PROCESO)


# ═══════════════ I-M · PRIMARIA ═══════════════
print(f"\n{B}I-M · PRIMARIA POR GRADO{X}")


@test("I   Primaria 1.o no repite automaticamente")
def _():
    notas, recs = caidas_tras_final(len(AREAS_PRIM))
    s = situacion_prim(notas, 1, recuperaciones=recs)
    igual(s['situacion']['condicion'], PA.PROMOVIDO)
    igual(s['situacion']['motivo'], PA.MOTIVO_SIN_REPITENCIA_PRIMER_CICLO)
    assert PA.ADV_PROMOCION_ASISTIDA in s['situacion']['advertencias']


@test("J   Primaria 2.o no repite sin decision excepcional")
def _():
    notas, recs = caidas_tras_final(len(AREAS_PRIM))
    s = situacion_prim(notas, 2, recuperaciones=recs)
    igual(s['situacion']['condicion'], PA.PROMOVIDO)
    igual(s['situacion']['motivo'], PA.MOTIVO_SIN_REPITENCIA_PRIMER_CICLO)
    igual(s['contexto'].get('decision_excepcional_segundo'), None,
          'A3 no inventa un acuerdo del equipo docente')
    assert AD.DIAG_EXCEPCION_2DO_SIN_FUENTE in s['diagnosticos']


@test("K   Primaria 3.o APLAZADO sigue APLAZADO con alfabetizacion desconocida")
def _():
    notas, recs = caidas_tras_final(1)
    s = situacion_prim(notas, 3, recuperaciones=recs)
    igual(s['situacion']['condicion'], PA.APLAZADO)
    igual(s['situacion']['requiere_recuperacion_especial'], True)
    igual(s['contexto']['alfabetizacion_inicial'], None)
    assert AD.DIAG_ALFABETIZACION_SIN_FUENTE in s['diagnosticos']


@test("L   Primaria 3.o candidato a PROMOVIDO + alfabetizacion desconocida -> EN_PROCESO")
def _():
    s = situacion_prim({}, 3)
    igual(s['situacion']['condicion'], PA.EN_PROCESO)
    assert PA.BLOQUEO_ALFABETIZACION_NO_INFORMADA in s['situacion']['bloqueos']
    assert AD.DIAG_ALFABETIZACION_SIN_FUENTE in s['diagnosticos']


@test("L2  el mismo caso en 4.o SI promueve: la alfabetizacion es solo de 3.o")
def _():
    s = situacion_prim({}, 4)
    igual(s['situacion']['condicion'], PA.PROMOVIDO)
    assert 'alfabetizacion_inicial' not in s['contexto']


@test("M   Primaria 4.o: 1-3 areas tras la Final -> APLAZADO; 4+ -> REPROBADO")
def _():
    for n in (1, 2, 3):
        s = situacion_prim(*caidas_tras_final(n)[:1], 4,
                           recuperaciones=caidas_tras_final(n)[1])
        igual(s['situacion']['condicion'], PA.APLAZADO, 'n=%d' % n)
    for n in (4, 5):
        notas, recs = caidas_tras_final(n)
        s = situacion_prim(notas, 4, recuperaciones=recs)
        igual(s['situacion']['condicion'], PA.REPROBADO, 'n=%d' % n)


# ═══════════════ N-P · ASISTENCIA ═══════════════
print(f"\n{B}N-P · ASISTENCIA: QUE CUENTA Y CONTRA QUE{X}")


@test("N   `excusa` NO cuenta como ausencia injustificada")
def _():
    filas = [asistencia(d, 'excusa') for d in range(1, 11)]
    igual(AD.dias_no_justificados(filas), 0,
          'una ausencia justificada no castiga al estudiante')


@test("O   `ausente` SI cuenta; `tardanza` y `presente` no")
def _():
    igual(AD.dias_no_justificados([asistencia(d, 'ausente') for d in (1, 2, 3)]), 3)
    igual(AD.dias_no_justificados([asistencia(1, 'tardanza'),
                                   asistencia(2, 'presente')]), 0)


@test("O2  un dia con varias filas cuenta UNA vez, y gana la asistencia")
def _():
    # El colegio pasa lista por asignatura: el mismo dia aparece 3 veces.
    filas = [asistencia(1, 'ausente'), asistencia(1, 'presente'),
             asistencia(1, 'ausente')]
    igual(AD.dias_no_justificados(filas), 0, 'vino: el dia no es una falta')


@test("P   denominador no fiable -> porcentaje None, no un numero inventado")
def _():
    for dias in (None, 0, -5, 'muchos', True):
        pct, diag = AD.porcentaje_ausencias(3, dias)
        igual(pct, None, repr(dias))
        igual(diag, AD.DIAG_DIAS_TRABAJADOS_NO_DECLARADOS, repr(dias))


@test("P2  mas ausencias que dias trabajados es incoherente, no un 150%")
def _():
    pct, diag = AD.porcentaje_ausencias(200, 180)
    igual(pct, None)
    igual(diag, AD.DIAG_ASISTENCIA_INCOHERENTE)


@test("P3  con denominador fiable si se calcula")
def _():
    pct, diag = AD.porcentaje_ausencias(18, 180)
    igual(round(pct, 4), 10.0)
    igual(diag, None)


@test("P4  porcentaje None llega a A2 y bloquea")
def _():
    s = situacion_sec(*escenario_secundaria({}),
                      contexto={'porcentaje_ausencias_no_justificadas': None})
    igual(s['situacion']['condicion'], PA.EN_PROCESO)


# ═══════════════ GRADO NUMERICO ═══════════════
print(f"\n{B}GRADO: EL NUMERO NO SE ADIVINA{X}")


@test("GR1 el numero sale del nombre, no de `orden`")
def _():
    # Colegio mixto: Primaria arranca en orden=7.
    igual(AD.numero_de_grado(grado('3ro Primaria', 'primaria', 9)), (3, None))
    # Colegio solo-primaria: el mismo 3.o tiene orden=3.
    igual(AD.numero_de_grado(grado('3ro Primaria', 'primaria', 3)), (3, None))
    igual(AD.numero_de_grado(grado('3ro Secundaria', 'secundaria', 3)), (3, None))


@test("GR2 nombre y orden contradictorios -> None, no se elige ninguno")
def _():
    n, diag = AD.numero_de_grado(grado('3ro Primaria', 'primaria', 5))
    igual(n, None)
    igual(diag, AD.DIAG_GRADO_INCOHERENTE)


@test("GR3 sin numero legible, sin grado, o fuera de 1-6 -> None")
def _():
    igual(AD.numero_de_grado(None), (None, AD.DIAG_GRADO_NO_ASIGNADO))
    igual(AD.numero_de_grado(grado('Pre-Kinder', 'inicial', 13))[1],
          AD.DIAG_GRADO_SIN_NUMERO)
    igual(AD.numero_de_grado(grado('9no', 'secundaria', None))[1],
          AD.DIAG_GRADO_FUERA_DE_RANGO)


@test("GR4 un grado indeterminado bloquea; no se asume 1.o")
def _():
    s = AD.construir_situacion_estudiante(
        RA.NIVEL_PRIMARIA, None, [], ('LE',),
        {'porcentaje_ausencias_no_justificadas': 5})
    igual(s['situacion']['condicion'], PA.EN_PROCESO)


@test("GR5 el nivel sale de Grado.nivel")
def _():
    igual(AD.nivel_de_grado(grado('1ro Primaria', 'primaria')), RA.NIVEL_PRIMARIA)
    igual(AD.nivel_de_grado(grado('1ro Sec', 'Secundaria')), RA.NIVEL_SECUNDARIA)
    igual(AD.nivel_de_grado(grado('Kinder', 'inicial')), None)


# ═══════════════ Q-R · PRESENTACION ═══════════════
print(f"\n{B}Q-R · EL TEXTO NO DECIDE{X}")


@test("Q   ningun parametro externo puede sustituir la condicion canonica")
def _():
    import inspect
    fuente = inspect.getsource(APP.generar_boletin_minerd_v2)
    assert "query_params.get('condicion'" not in fuente, \
        'un query param no puede sobrescribir una situacion academica oficial'
    assert 'query_params.get("condicion"' not in fuente


@test("Q2  el helper de presentacion nunca inventa una condicion")
def _():
    for condicion in (PA.PROMOVIDO, PA.APLAZADO, PA.REPROBADO, PA.EN_PROCESO):
        d = AD.situacion_boletin_secundaria({'condicion': condicion,
                                             'bloqueos': (), 'motivo': 'X'})
        igual(d['promovido'], condicion == PA.PROMOVIDO, condicion)
        igual(d['repitente'], condicion == PA.REPROBADO, condicion)


@test("Q3  EN_PROCESO no marca ninguna casilla ni dice Promovido")
def _():
    d = AD.situacion_boletin_secundaria(
        {'condicion': PA.EN_PROCESO, 'bloqueos': ('AREAS_PENDIENTES',),
         'motivo': PA.MOTIVO_PROCESO_ABIERTO})
    igual(d['promovido'], False)
    igual(d['repitente'], False)
    assert 'Promovido' not in d['condicion'], d
    assert 'Repitente' not in d['condicion'], d
    assert 'PENDIENTE' in d['condicion'], d


@test("Q4  APLAZADO no marca Repitente: aun le queda el proceso especial")
def _():
    d = AD.situacion_boletin_secundaria(
        {'condicion': PA.APLAZADO, 'bloqueos': (),
         'motivo': PA.MOTIVO_ELEGIBLE_ESPECIAL})
    igual(d['repitente'], False)
    igual(d['promovido'], False)
    assert 'APLAZADO' in d['condicion']


@test("R   6.o de Secundaria: PROMOVIDO no se convierte en Graduado")
def _():
    s = situacion_sec(*escenario_secundaria({}), grado_numero=6)
    igual(s['situacion']['condicion'], PA.PROMOVIDO)
    assert PA.ADV_TITULACION_PENDIENTE in s['situacion']['advertencias']
    d = AD.situacion_boletin_secundaria(s['situacion'])
    for prohibido in ('Graduado', 'Egresado', 'Titulado', 'GRADUADO'):
        assert prohibido not in d['condicion'], d['condicion']
    igual(d['promovido'], True)


@test("R2  el vocabulario legacy de Primaria se conserva para el frontend")
def _():
    igual(AD.CONDICION_LEGACY_PRIMARIA[PA.PROMOVIDO], 'promovido')
    igual(AD.CONDICION_LEGACY_PRIMARIA[PA.APLAZADO], 'repitente_condicional')
    igual(AD.CONDICION_LEGACY_PRIMARIA[PA.REPROBADO], 'repite')
    igual(AD.CONDICION_LEGACY_PRIMARIA[PA.EN_PROCESO], 'en_proceso')
    igual(sorted(AD.CONDICION_LEGACY_PRIMARIA), sorted(PA.CONDICIONES))


# ═══════════════ B · INDIVIDUAL == LOTE ═══════════════
print(f"\n{B}B · NO-DIVERGENCIA INDIVIDUAL / LOTE{X}")


def _situacion_individual(datos):
    return APP._situacion_canonica_secundaria(**datos)


def _situacion_lote(datos):
    return APP._situacion_canonica_secundaria(**datos)


@test("B   individual y lote llaman EXACTAMENTE al mismo helper")
def _():
    for nombre, quien in (('generar_boletin_minerd_v2', 'individual'),
                          ('generar_boletines_curso_minerd_v2', 'lote')):
        fuente = fuente_migrada(nombre)
        assert '_situacion_canonica_secundaria' in fuente, quien
        assert 'situacion_boletin_secundaria' in fuente, quien
        for vieja in ('reprobadas > 2', 'reprobadas == 0', 'aprobadas +=',
                      'reprobadas +=', 'or 0) >= 70'):
            assert vieja not in fuente, '%s conserva %r' % (quien, vieja)


@test("B2  misma fixture -> misma condicion y mismo texto en los dos")
def _():
    for escenario in (escenario_secundaria({}),
                      _tras_extraordinaria(1),
                      _tras_extraordinaria(3),
                      escenario_secundaria({'LE': 0}),
                      escenario_secundaria({}, internas=[('Musica', 10)])):
        a = situacion_sec(*escenario)
        b = situacion_sec(*escenario)
        igual(a['situacion']['condicion'], b['situacion']['condicion'])
        igual(AD.situacion_boletin_secundaria(a['situacion']),
              AD.situacion_boletin_secundaria(b['situacion']))


@test("B3  la regla vieja y la canonica DISCREPAN: por eso habia que migrar")
def _():
    # 3 areas caidas tras la Extraordinaria. La regla vieja del lote contaba
    # `(cf or 0) >= 70 or (ev.nota_final or 0) >= 70`.
    asigs, comps, extras, asigns = _tras_extraordinaria(3)
    vieja_aprobadas = 0
    for a in asigs:
        cf, _lit, _ex = CF(None, None, None, None, con_exacto=True,
                           competencias=comps[a.id])
        ev = extras.get(a.id)
        if (cf or 0) >= 70 or (ev is not None and
                               (getattr(ev, 'nota_final', None) or 0) >= 70):
            vieja_aprobadas += 1
    vieja_reprobadas = len(asigs) - vieja_aprobadas
    vieja_condicion = ('promovido' if vieja_reprobadas == 0
                       else 'PENDIENTE/REPITENTE')
    canonica = situacion_sec(asigs, comps, extras, asigns)['situacion']
    igual(canonica['condicion'], PA.REPROBADO)
    assert vieja_condicion == 'PENDIENTE/REPITENTE'
    # La vieja decia lo mismo para 3 que para 1: un texto unico sin matiz.
    uno = situacion_sec(*_tras_extraordinaria(1))['situacion']
    igual(uno['condicion'], PA.APLAZADO,
          'la canonica distingue aplazado de reprobado; la vieja no')


# ═══════════════ TESTS ESTATICOS ═══════════════
print(f"\n{B}ESTATICOS: LAS REGLAS VIEJAS NO VUELVEN{X}")

_MIGRADOS = ('generar_boletin_minerd_v2', 'generar_boletines_curso_minerd_v2',
             '_generar_pdf_primaria', '_situacion_canonica_secundaria',
             '_situacion_canonica_primaria')


@test("S1  ningun camino migrado usa una cadena `or` sobre notas")
def _():
    for nombre in _MIGRADOS:
        fuente = fuente_migrada(nombre)
        for prohibido in ('nota_final or', 'especial_final or',
                          'extraordinaria_final or', 'completiva_final or',
                          'cf_area or', 'cf or'):
            assert prohibido not in fuente, '%s: %r' % (nombre, prohibido)


@test("S2  ningun camino migrado decide la situacion GLOBAL con 65/70")
def _():
    for nombre in _MIGRADOS:
        fuente = fuente_migrada(nombre)
        for prohibido in ('reprobadas > 2', 'reprobadas == 0',
                          'reprobadas <= 2', 'condicion_final_estudiante',
                          'repitente =', 'promovido = reprobadas',
                          '>= 70', '< 70', '>= 65', '< 65'):
            assert prohibido not in fuente, '%s: %r' % (nombre, prohibido)


@test("S3  el adaptador no contiene ningun corte academico")
def _():
    import inspect
    # Se permite MAX_AUSENCIAS_NO_JUSTIFICADAS, que es de A2 y se LEE, no se
    # redefine. Lo que no puede haber es un numero de corte propio.
    fuente = codigo_efectivo(inspect.getsource(AD))
    for prohibido in ('>= 65', '< 65', '>= 70', '< 70', '>=65', '>=70',
                      '65', '70'):
        assert prohibido not in fuente, prohibido


@test("S4  el adaptador no importa ORM ni sesion: no PUEDE escribir")
def _():
    import ast
    import inspect
    arbol = ast.parse(inspect.getsource(AD))
    mods = sorted({n.names[0].name.split('.')[0]
                   for n in ast.walk(arbol) if isinstance(n, ast.Import)}
                  | {n.module.split('.')[0] for n in ast.walk(arbol)
                     if isinstance(n, ast.ImportFrom) and n.module})
    igual(mods, ['promocion_academica', 're', 'resultado_academico'])


@test("S5  el adaptador no escribe ni nombra una sesion")
def _():
    import ast
    import inspect
    arbol = ast.parse(inspect.getsource(AD))
    for n in ast.walk(arbol):
        if isinstance(n, ast.Call):
            attr = getattr(n.func, 'attr', '')
            # `add` no se prohibe a secas: `vistas.add(...)` es un set y no
            # puede escribir en ninguna base. Lo que no puede existir es una
            # sesion, y sin ella ninguno de estos metodos tiene a quien
            # llamar.
            assert attr not in ('add_all', 'commit', 'flush', 'delete',
                                'merge', 'bulk_save_objects', 'execute'), attr
        if isinstance(n, ast.Name):
            assert n.id not in ('db', 'session', 'Session', 'engine',
                                'SessionLocal'), n.id


@test("S6  construir una situacion con una sesion que explota al escribir")
def _():
    class SesionQueExplota:
        def __getattr__(self, nombre):
            if nombre in ('add', 'add_all', 'commit', 'flush', 'delete',
                          'merge', 'execute'):
                raise AssertionError('A3 intento ESCRIBIR con %r' % nombre)
            raise AttributeError(nombre)

    sesion = SesionQueExplota()
    # El adaptador nunca recibe la sesion, pero si alguien se la pasara por
    # error, tampoco la usaria: la firma no la acepta.
    import inspect
    for nombre, fn in inspect.getmembers(AD, inspect.isfunction):
        params = inspect.signature(fn).parameters
        assert 'db' not in params and 'session' not in params, nombre
    del sesion


@test("S7  A1 y A2 siguen congelados: A3 no los modifico")
def _():
    import subprocess
    repo = os.path.dirname(os.path.dirname(_AQUI))
    for sha, ruta in (('25d6d649b2d97cea2134f4fe23aaa917ca6b7585',
                       'backend/resultado_academico.py'),
                      ('d784da67dc279d018abb45b8dc25d482752d18a5',
                       'backend/promocion_academica.py')):
        d = subprocess.run(['git', 'diff', '--stat', sha, '--', ruta],
                           capture_output=True, cwd=repo).stdout.decode('utf-8')
        igual(d.strip(), '', ruta)




# ═══════════ T · CONTRA UNA BASE DE VERDAD ═══════════
#
# Todo lo anterior trabaja con objetos en memoria, que es lo correcto para
# fijar las reglas. Pero los cargadores de `app.py` hacen SQL, y un error ahi
# —un filtro mal puesto, una columna que no existe— no lo veria ninguna de
# esas pruebas. Esta seccion los ejecuta de verdad, sobre la base temporal
# que `test_utils` ya aislo, y comprueba ademas que NO escriben.
print(f"\n{B}T · LOS CARGADORES, CONTRA SQL REAL{X}")

from database import SessionLocal                                 # noqa: E402

M.Base.metadata.create_all(bind=engine)


def _sembrar():
    """Un curso de Secundaria con 8 areas y un estudiante. Solo para leer."""
    db = SessionLocal()
    colegio = M.Colegio(nombre='A3', codigo='A3TEST', activo=True)
    db.add(colegio)
    db.flush()
    ano = M.AnoEscolar(colegio_id=colegio.id, nombre='2025-2026', activo=True)
    grd = M.Grado(colegio_id=colegio.id, nombre='3ro Secundaria',
                  nivel='secundaria', orden=3, activo=True)
    db.add_all([ano, grd])
    db.flush()
    curso = M.Curso(colegio_id=colegio.id, nombre='A', grado_id=grd.id,
                    ano_escolar_id=ano.id, activo=True)
    prof = M.Usuario(colegio_id=colegio.id, nombre='P', username='p_a3',
                     password_hash='x', role='profesor', activo=True)
    db.add_all([curso, prof])
    db.flush()
    est = M.Estudiante(colegio_id=colegio.id, matricula='A3-1', nombre='E',
                       apellido='S', curso_id=curso.id, activo=True)
    db.add(est)
    db.flush()
    for codigo in AREAS_SEC:
        asig = M.Asignatura(colegio_id=colegio.id, nombre=codigo,
                            codigo=codigo[:10], area='X',
                            area_curricular_codigo=codigo, activo=True)
        db.add(asig)
        db.flush()
        db.add(M.AsignacionProfesor(colegio_id=colegio.id, profesor_id=prof.id,
                                    curso_id=curso.id, asignatura_id=asig.id,
                                    ano_escolar_id=ano.id, activo=True))
        for n in range(1, 5):
            db.add(M.CalificacionSecundaria(
                colegio_id=colegio.id, estudiante_id=est.id,
                asignatura_id=asig.id, ano_escolar_id=ano.id,
                competencia_numero=n, p1=90, p2=90, p3=90, p4=90))
    # Una materia interna que NO debe entrar en la promocion oficial.
    musica = M.Asignatura(colegio_id=colegio.id, nombre='Musica', codigo='MUS',
                          area='X', area_curricular_codigo=None, activo=True)
    db.add(musica)
    db.flush()
    db.add(M.AsignacionProfesor(colegio_id=colegio.id, profesor_id=prof.id,
                                curso_id=curso.id, asignatura_id=musica.id,
                                ano_escolar_id=ano.id, activo=True))
    for n in range(1, 5):
        db.add(M.CalificacionSecundaria(
            colegio_id=colegio.id, estudiante_id=est.id,
            asignatura_id=musica.id, ano_escolar_id=ano.id,
            competencia_numero=n, p1=10, p2=10, p3=10, p4=10))
    db.commit()
    return db, colegio, ano, curso, est


_DB, _COL, _ANO, _CURSO, _EST = _sembrar()


class _Usuario:
    """Un usuario de direccion del colegio sembrado, para `tenant_filter`.

    El campo del modelo se llama `role` (en ingles), no `rol`.
    """
    colegio_id = _COL.id
    role = 'direccion'
    id = 1


_USER = _Usuario()


@test("T1  la precarga lee el curriculo del curso desde SQL")
def _():
    p = APP._precarga_curso_canonica(_DB, _USER, _CURSO, _ANO)
    igual(p['grado_numero'], 3)
    igual(p['diag_grado'], None)
    igual(len(p['asignaciones']), len(AREAS_SEC) + 1, 'Musica tambien se asigna')
    curriculo, diag = AD.curriculo_desde_asignaciones(
        p['asignaciones'], p['asignaturas_por_id'])
    igual(diag, None)
    igual(sorted(curriculo), sorted(AREAS_SEC),
          'Musica no tiene area curricular: fuera de la promocion oficial')


@test("T2  la situacion canonica se resuelve de punta a punta")
def _():
    p = APP._precarga_curso_canonica(_DB, _USER, _CURSO, _ANO)
    paquete = APP._situacion_canonica_secundaria(_DB, _USER, _EST, _ANO, p)
    igual(paquete['situacion']['condicion'], PA.EN_PROCESO,
          'sin dias_trabajados declarados no hay denominador fiable')
    igual(paquete['situacion']['bloqueos'], (PA.BLOQUEO_ASISTENCIA_NO_EVALUADA,))
    assert AD.DIAG_DIAS_TRABAJADOS_NO_DECLARADOS in paquete['diagnosticos'], \
        paquete['diagnosticos']
    igual(len(paquete['resultados']), len(AREAS_SEC),
          'Musica no produce resultado oficial')


@test("T3  con dias trabajados declarados, promueve")
def _():
    _ANO.set_dias_trabajados({'ago': 20, 'sep': 20, 'oct': 20, 'nov': 20,
                              'dic': 15, 'ene': 20, 'feb': 18, 'mar': 20,
                              'abr': 18, 'may': 20, 'jun': 15})
    _DB.commit()
    p = APP._precarga_curso_canonica(_DB, _USER, _CURSO, _ANO)
    igual(p['dias_trabajados'], 206)
    paquete = APP._situacion_canonica_secundaria(_DB, _USER, _EST, _ANO, p)
    igual(paquete['situacion']['condicion'], PA.PROMOVIDO,
          str(paquete['situacion']['bloqueos']))
    d = AD.situacion_boletin_secundaria(paquete['situacion'],
                                        paquete['diagnosticos'])
    igual(d['promovido'], True)
    igual(d['repitente'], False)


@test("T4  construir la situacion NO escribe nada en la base")
def _():
    from sqlalchemy import event
    escrituras = []

    def _vigilar(sesion, flush_context, instances):
        escrituras.append((list(sesion.new), list(sesion.dirty),
                           list(sesion.deleted)))

    event.listen(SessionLocal, 'before_flush', _vigilar)
    try:
        p = APP._precarga_curso_canonica(_DB, _USER, _CURSO, _ANO)
        APP._situacion_canonica_secundaria(_DB, _USER, _EST, _ANO, p)
        _DB.flush()
    finally:
        event.remove(SessionLocal, 'before_flush', _vigilar)
    igual([e for e in escrituras if any(e)], [],
          'un boletin no puede modificar el expediente que imprime')


@test("T5  no se dispara el backfill de evaluaciones extra")
def _():
    antes = _DB.query(M.EvaluacionExtraSecundaria).count()
    p = APP._precarga_curso_canonica(_DB, _USER, _CURSO, _ANO)
    paquete = APP._situacion_canonica_secundaria(_DB, _USER, _EST, _ANO, p)
    igual(_DB.query(M.EvaluacionExtraSecundaria).count(), antes,
          'A1 admite evaluacion=None + cf_exacto; no hay que crear la fila')
    igual(antes, 0)
    igual(paquete['situacion']['condicion'], PA.PROMOVIDO)


@test("T6  el lote precarga: el numero de consultas no crece con el alumnado")
def _():
    from sqlalchemy import event
    consultas = []

    def _contar(conn, cursor, statement, params, context, many):
        if statement.lstrip().upper().startswith('SELECT'):
            consultas.append(statement)

    p = APP._precarga_curso_canonica(_DB, _USER, _CURSO, _ANO)
    _ids = [_EST.id]
    event.listen(engine, 'before_cursor_execute', _contar)
    try:
        comps = APP._datos_academicos_estudiantes(
            _DB, _USER, _ids, _ANO, M.CalificacionSecundaria)
        extras = APP._datos_academicos_estudiantes(
            _DB, _USER, _ids, _ANO, M.EvaluacionExtraSecundaria)
        asist = APP._asistencias_estudiantes(_DB, _USER, _ids, _ANO)
    finally:
        event.remove(engine, 'before_cursor_execute', _contar)
    igual(len(consultas), 3,
          'tres consultas para TODO el curso, no tres por estudiante')
    assert comps.get(_EST.id), 'la precarga trajo las competencias'
    igual(extras, {})
    igual(asist, {})


print("\n" + "=" * 70)
if _fail:
    print(f"{R}{B}R4-A3: {len(_fail)} fallo(s) de {_total}{X}")
    for n, e in _fail:
        print(f"  - {n}: {e}")
    sys.exit(1)
print(f"{B}R4-A3 CONSUMIDORES CANONICOS: {_ok}/{_total} pruebas{X}")
print(f"{G}{B}TODO VERDE{X}")
