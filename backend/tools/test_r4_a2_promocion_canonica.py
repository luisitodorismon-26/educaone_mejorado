# -*- coding: utf-8 -*-
"""
R4-A2 — el motor canonico de situacion academica del estudiante.

QUE COMPRUEBA
    Que A2 decide bien y, sobre todo, que NO decide cuando no puede. La
    mayoria de estas pruebas son de lo segundo: curriculo incompleto,
    areas sin calificar, inconsistencias heredadas de A1, datos humanos que
    nadie informo. En todos esos casos la respuesta correcta es EN_PROCESO,
    nunca una promocion por omision.

LA SECCION QUE MAS IMPORTA
    E · ELEGIBILIDAD DEL PROCESO ESPECIAL. A1 mira un area y, si encuentra
    una Especial cargada, la lee: no puede saber cuantas areas mas cayeron.
    A2 si. Si el estudiante no era elegible, esa Especial no le rescata por
    mucho que exista en la base. Las mutaciones de esa seccion demuestran
    que el gate esta vivo.

    Son pruebas PURAS: sin base de datos, sin HTTP. Los resultados de A1 se
    construyen con builders, y varios casos llaman al A1 REAL para que la
    forma del contrato no se separe.

Uso:
    cd backend
    python tools/test_r4_a2_promocion_canonica.py
"""
import copy
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import promocion_academica as PA                              # noqa: E402
import resultado_academico as RA                              # noqa: E402

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


# ── builders de resultados A1 ────────────────────────────────────────
# Centinela: permite pedir explicitamente `fase=None` para los casos de
# incoherencia, sin que se confunda con «no me importa la fase».
_FASE_DEL_CONTRATO = object()


def area(codigo, estado, fase=_FASE_DEL_CONTRATO, nota_final=None,
         inconsistencias=(), nivel=RA.NIVEL_PRIMARIA):
    """Un resultado de A1. Por defecto, con la fase QUE A1 EMITIRIA.

    Antes ponia `fase=None` siempre, lo que producia pares que A1 nunca
    genera —APROBADA sin fase normal— y que A2.2 rechaza con razon.
    """
    if fase is _FASE_DEL_CONTRATO:
        fase = PA.CONTRATO_ESTADO_FASE.get(nivel, {}).get(estado)
    return {
        'nivel': nivel, 'nota_base': None, 'fase': fase,
        'nota_final': nota_final, 'estado': estado, 'pendiente': False,
        'requiere_contexto_promocion': False,
        'area_curricular_codigo': codigo,
        'inconsistencias': tuple(inconsistencias),
        'cf_exacta_disponible': None,
    }


CURRICULO_PRIM = ['LE', 'MAT', 'CS', 'CN', 'EA', 'EF', 'FIHR', 'LEI']
CURRICULO_SEC = ['LE', 'MAT', 'CS', 'CN', 'EA', 'EF', 'FIHR', 'LEI']

# Asistencia limpia: para no repetirla en cada caso academico.
OK_ASIST = {'porcentaje_ausencias_no_justificadas': 5}


def todas(estado=RA.APROBADA, curriculo=None, nivel=RA.NIVEL_PRIMARIA):
    return [area(c, estado, nivel=nivel) for c in (curriculo or CURRICULO_PRIM)]


def con_fallos(n, estado_fallo, fase=_FASE_DEL_CONTRATO, curriculo=None,
               nivel=RA.NIVEL_PRIMARIA):
    """Currículo completo con `n` áreas en el estado de fallo indicado."""
    curriculo = curriculo or CURRICULO_PRIM
    out = []
    for i, c in enumerate(curriculo):
        if i < n:
            out.append(area(c, estado_fallo, fase=fase, nivel=nivel))
        else:
            out.append(area(c, RA.APROBADA, nivel=nivel))
    return out


def prim(grado, resultados, contexto=None, curriculo=None):
    ctx = dict(OK_ASIST)
    ctx.update(contexto or {})
    return PA.resolver_situacion_estudiante(
        RA.NIVEL_PRIMARIA, grado, resultados,
        curriculo if curriculo is not None else CURRICULO_PRIM, ctx)


def sec(grado, resultados, contexto=None, curriculo=None):
    ctx = dict(OK_ASIST)
    ctx.update(contexto or {})
    return PA.resolver_situacion_estudiante(
        RA.NIVEL_SECUNDARIA, grado, resultados,
        curriculo if curriculo is not None else CURRICULO_SEC, ctx)


# ══════════════════ G · GATES GENERALES ══════════════════
print(f"\n{B}GATES GENERALES{X}")


@test("G1  nivel desconocido -> EN_PROCESO")
def _():
    r = PA.resolver_situacion_estudiante('inicial', 1, [], ['LE'], OK_ASIST)
    igual(r['condicion'], PA.EN_PROCESO)
    assert PA.BLOQUEO_NIVEL_NO_RECONOCIDO in r['bloqueos']


@test("G2  grado sin declarar -> EN_PROCESO")
def _():
    r = PA.resolver_situacion_estudiante(RA.NIVEL_PRIMARIA, None,
                                         todas(), CURRICULO_PRIM, OK_ASIST)
    igual(r['condicion'], PA.EN_PROCESO)
    assert PA.BLOQUEO_GRADO_NO_DECLARADO in r['bloqueos']


@test("G3  curriculo esperado no declarado -> EN_PROCESO")
def _():
    r = PA.resolver_situacion_estudiante(RA.NIVEL_PRIMARIA, 4, todas(),
                                         None, OK_ASIST)
    igual(r['condicion'], PA.EN_PROCESO)
    assert PA.BLOQUEO_CURRICULO_NO_DECLARADO in r['bloqueos']
    igual(r['es_definitiva'], False)


@test("G4  curriculo esperado vacio -> no se promueve")
def _():
    r = PA.resolver_situacion_estudiante(RA.NIVEL_PRIMARIA, 4, todas(),
                                         [], OK_ASIST)
    igual(r['condicion'], PA.EN_PROCESO)
    assert PA.BLOQUEO_SIN_CURRICULO_OFICIAL in r['bloqueos']


@test("G5  curriculo INCOMPLETO -> EN_PROCESO (el bug original)")
def _():
    # Dos areas cargadas de ocho: antes salia «promovido».
    r = prim(4, [area('LE', RA.APROBADA), area('MAT', RA.APROBADA)])
    igual(r['condicion'], PA.EN_PROCESO)
    assert PA.BLOQUEO_CURRICULO_INCOMPLETO in r['bloqueos']
    igual(r['es_definitiva'], False)


@test("G6  codigos esperados como MULTICONJUNTO, no como set")
def _():
    # El grado declara LE dos veces; presentarla una sola vez no basta.
    r = PA.resolver_situacion_estudiante(
        RA.NIVEL_PRIMARIA, 4,
        [area('LE', RA.APROBADA), area('MAT', RA.APROBADA)],
        ['LE', 'LE', 'MAT'], OK_ASIST)
    igual(r['condicion'], PA.EN_PROCESO)
    assert PA.BLOQUEO_CURRICULO_INCOMPLETO in r['bloqueos'], \
        'un set habria dado el curriculo por completo'
    # Con las dos, pasa.
    r2 = PA.resolver_situacion_estudiante(
        RA.NIVEL_PRIMARIA, 4,
        [area('LE', RA.APROBADA), area('LE', RA.APROBADA),
         area('MAT', RA.APROBADA)],
        ['LE', 'LE', 'MAT'], OK_ASIST)
    igual(r2['condicion'], PA.PROMOVIDO)


@test("G7  SIN_CALIFICAR bloquea, no reprueba")
def _():
    r = prim(4, con_fallos(1, RA.SIN_CALIFICAR))
    igual(r['condicion'], PA.EN_PROCESO)
    assert PA.BLOQUEO_AREAS_PENDIENTES in r['bloqueos']
    igual(r['no_aprobadas'], 0, 'una ausencia no es una reprobacion')
    igual(r['pendientes'], 1)


@test("G8  cada estado pendiente bloquea")
def _():
    for estado in (RA.SIN_CALIFICAR, RA.PENDIENTE_RECUPERACION_FINAL,
                   RA.PENDIENTE_COMPLETIVA, RA.PENDIENTE_EXTRAORDINARIA):
        r = prim(4, con_fallos(1, estado))
        igual(r['condicion'], PA.EN_PROCESO, estado)


@test("G9  una inconsistencia de A1 bloquea la certificacion")
def _():
    resultados = todas()
    resultados[0] = area('LE', RA.APROBADA,
                         inconsistencias=(RA.INCONSISTENCIA_CF_DIVERGENTE,))
    r = prim(4, resultados)
    igual(r['condicion'], PA.EN_PROCESO)
    assert PA.BLOQUEO_DATOS_INCONSISTENTES in r['bloqueos']
    assert RA.INCONSISTENCIA_CF_DIVERGENTE in r['inconsistencias'], \
        'A2 propaga, no borra'


@test("G10 materia interna reprobada NO impide la promocion")
def _():
    resultados = todas() + [area(None, RA.REPROBADA_DEFINITIVA)]
    r = prim(4, resultados)
    igual(r['condicion'], PA.PROMOVIDO, 'Musica no puede hacer repetir')
    igual(r['total_oficiales'], 8)
    igual(len(r['codigos_no_oficiales']), 1)


@test("G11 materia interna SIN_CALIFICAR tampoco bloquea")
def _():
    r = prim(4, todas() + [area(None, RA.SIN_CALIFICAR)])
    igual(r['condicion'], PA.PROMOVIDO)
    igual(r['pendientes'], 0, 'la interna no cuenta entre las pendientes')


@test("G12 el input NO se muta")
def _():
    resultados = todas()
    antes = copy.deepcopy(resultados)
    contexto = dict(OK_ASIST)
    ctx_antes = copy.deepcopy(contexto)
    PA.resolver_situacion_estudiante(RA.NIVEL_PRIMARIA, 4, resultados,
                                     CURRICULO_PRIM, contexto)
    igual(resultados, antes, 'se modifico la lista de resultados')
    igual(contexto, ctx_antes, 'se modifico el contexto')


@test("G13 el contrato trae siempre las mismas claves")
def _():
    CLAVES = {'nivel', 'grado_numero', 'condicion', 'es_definitiva', 'motivo',
              'total_oficiales', 'aprobadas', 'pendientes', 'no_aprobadas',
              'codigos_aprobados', 'codigos_pendientes', 'codigos_no_aprobados',
              'codigos_no_oficiales',
              'requiere_recuperacion_especial', 'requiere_evaluacion_especial',
              'bloqueos', 'advertencias', 'inconsistencias'}
    casos = [
        PA.resolver_situacion_estudiante('x', None, [], None, None),
        prim(1, todas()), prim(4, con_fallos(5, RA.NO_APROBADA_TRAS_RECUPERACION_FINAL)),
        sec(2, todas(nivel=RA.NIVEL_SECUNDARIA)),
    ]
    for r in casos:
        igual(set(r), CLAVES)
        assert r['condicion'] in PA.CONDICIONES, r['condicion']


@test("G14 una nota 0 aprobada sigue siendo un area aprobada")
def _():
    resultados = todas()
    resultados[0] = area('LE', RA.APROBADA, nota_final=0)
    r = prim(4, resultados)
    igual(r['aprobadas'], 8, 'un 0 no puede desaparecer del conteo')


@test("G15 A2 consume el A1 REAL sin romperse")
def _():
    comps = []
    class _C:
        def __init__(s, n, nota):
            s.competencia_numero = n
            s.p1 = s.p2 = s.p3 = s.p4 = nota
            s.rp1 = s.rp2 = s.rp3 = s.rp4 = None
            s.ne1 = s.ne2 = s.ne3 = s.ne4 = False
        def es_ne(s, p): return False
        def valor_periodo(s, p): return getattr(s, 'p%d' % p)
        def calcular_final(s, minimo_periodos=1): return s.p1
    reales = []
    for cod in CURRICULO_PRIM:
        tres = [_C(n, 80) for n in (1, 2, 3)]
        reales.append(RA.resolver_nota_primaria(tres, grado_numero=4,
                                                area_curricular_codigo=cod))
    r = prim(4, reales)
    igual(r['condicion'], PA.PROMOVIDO)
    igual(r['aprobadas'], 8)


# ══════════════════ P1 · PRIMARIA 1.º Y 2.º ══════════════════
print(f"\n{B}PRIMARIA 1.o Y 2.o{X}")


@test("A1  1ro todas aprobadas -> PROMOVIDO")
def _():
    r = prim(1, todas())
    igual(r['condicion'], PA.PROMOVIDO)
    igual(r['es_definitiva'], True)


@test("A2  1ro con areas bajo el minimo tras la Final -> PROMOVIDO asistido")
def _():
    r = prim(1, con_fallos(3, RA.NO_APROBADA_TRAS_RECUPERACION_FINAL))
    igual(r['condicion'], PA.PROMOVIDO, 'en 1ro no se contempla la repitencia')
    igual(r['motivo'], PA.MOTIVO_SIN_REPITENCIA_PRIMER_CICLO)
    assert PA.ADV_PROMOCION_ASISTIDA in r['advertencias']
    igual(r['no_aprobadas'], 3, 'el dato no se esconde')


@test("A3  1ro con Recuperacion Final pendiente -> EN_PROCESO")
def _():
    r = prim(1, con_fallos(1, RA.PENDIENTE_RECUPERACION_FINAL))
    igual(r['condicion'], PA.EN_PROCESO)


@test("A4  2do: mismos tres casos")
def _():
    igual(prim(2, todas())['condicion'], PA.PROMOVIDO)
    r = prim(2, con_fallos(4, RA.NO_APROBADA_TRAS_RECUPERACION_FINAL))
    igual(r['condicion'], PA.PROMOVIDO, '4 fallos tampoco repiten en 2do')
    assert PA.ADV_PROMOCION_ASISTIDA in r['advertencias']
    igual(prim(2, con_fallos(1, RA.PENDIENTE_RECUPERACION_FINAL))['condicion'],
          PA.EN_PROCESO)


@test("A5  2do sin decision colegiada NO repite automaticamente")
def _():
    r = prim(2, con_fallos(8, RA.NO_APROBADA_TRAS_RECUPERACION_FINAL))
    igual(r['condicion'], PA.PROMOVIDO,
          'ni con las ocho areas caidas se repite sin decision humana')


@test("A6  2do con decision colegiada + antecedente -> REPROBADO")
def _():
    # CAMBIO DE CONTRATO (A2.1): la norma permite la repeticion excepcional
    # de 2do UNA SOLA VEZ, asi que hace falta saber si ya se uso.
    r = prim(2, todas(), {'decision_excepcional_segundo': 'repetir',
                          'repeticion_excepcional_segundo_ya_utilizada': False})
    igual(r['condicion'], PA.REPROBADO)
    igual(r['motivo'], PA.MOTIVO_EXCEPCION_SEGUNDO)
    igual(r['es_definitiva'], True)


@test("A6b 2do con decision pero SIN antecedente -> EN_PROCESO")
def _():
    r = prim(2, todas(), {'decision_excepcional_segundo': 'repetir'})
    igual(r['condicion'], PA.EN_PROCESO)
    assert PA.BLOQUEO_ANTECEDENTE_EXCEPCION_2DO in r['bloqueos'], r['bloqueos']


@test("A6c 2do con la excepcion YA utilizada -> no se repite otra vez")
def _():
    r = prim(2, todas(), {'decision_excepcional_segundo': 'repetir',
                          'repeticion_excepcional_segundo_ya_utilizada': True})
    igual(r['condicion'], PA.EN_PROCESO)
    assert PA.INC_EXCEPCION_SEGUNDO_YA_UTILIZADA in r['inconsistencias'], \
        r['inconsistencias']


@test("A6d un valor invalido de la excepcion NO se ignora")
def _():
    for valor in ('REPETIR', 'si', 1, True, [], {}):
        r = prim(2, todas(), {'decision_excepcional_segundo': valor})
        igual(r['condicion'], PA.EN_PROCESO, repr(valor))
        assert PA.INC_EXCEPCION_SEGUNDO_INVALIDA in r['inconsistencias'], valor


@test("A7  la excepcion de 2do NO se admite en 1ro")
def _():
    r = prim(1, todas(), {'decision_excepcional_segundo': 'repetir'})
    igual(r['condicion'], PA.EN_PROCESO,
          'la inconsistencia bloquea; nunca se repite en 1ro')
    assert PA.INC_EXCEPCION_SEGUNDO_FUERA_DE_LUGAR in r['inconsistencias']


@test("A8  la excepcion tampoco se admite en 3ro-6to")
def _():
    for grado in (3, 4, 5, 6):
        r = prim(grado, todas(),
                 {'decision_excepcional_segundo': 'repetir',
                  'alfabetizacion_inicial': True})
        assert r['condicion'] != PA.REPROBADO or \
            r['motivo'] != PA.MOTIVO_EXCEPCION_SEGUNDO, grado


# ══════════════════ P2 · PRIMARIA 3.º A 6.º ══════════════════
print(f"\n{B}PRIMARIA 3.o A 6.o{X}")

ALFA_OK = {'alfabetizacion_inicial': True}


@test("B1  0 fallos tras la Final -> PROMOVIDO")
def _():
    for grado in (3, 4, 5, 6):
        ctx = ALFA_OK if grado == 3 else {}
        r = prim(grado, todas(), ctx)
        igual(r['condicion'], PA.PROMOVIDO, 'grado %d' % grado)


@test("B2  1, 2 y 3 fallos tras la Final -> APLAZADO y elegible")
def _():
    for n in (1, 2, 3):
        r = prim(4, con_fallos(n, RA.NO_APROBADA_TRAS_RECUPERACION_FINAL))
        igual(r['condicion'], PA.APLAZADO, '%d fallos' % n)
        igual(r['es_definitiva'], False)
        igual(r['requiere_recuperacion_especial'], True)
        igual(r['motivo'], PA.MOTIVO_ELEGIBLE_ESPECIAL)


@test("B3  4 y 5+ fallos tras la Final -> REPROBADO")
def _():
    for n in (4, 5, 6, 8):
        r = prim(4, con_fallos(n, RA.NO_APROBADA_TRAS_RECUPERACION_FINAL))
        igual(r['condicion'], PA.REPROBADO, '%d fallos' % n)
        igual(r['es_definitiva'], True)
        igual(r['motivo'], PA.MOTIVO_DEMASIADAS_NO_APROBADAS)
        igual(r['requiere_recuperacion_especial'], False)


@test("B4  Especial completa y todas aprobadas -> PROMOVIDO")
def _():
    r = prim(4, con_fallos(3, RA.APROBADA_RECUPERACION_ESPECIAL,
                           fase=RA.FASE_RECUPERACION_ESPECIAL))
    igual(r['condicion'], PA.PROMOVIDO)
    igual(r['motivo'], PA.MOTIVO_ESPECIAL_SUPERADA)


@test("B5  Especial completa con UNA fallida -> REPROBADO")
def _():
    resultados = con_fallos(3, RA.APROBADA_RECUPERACION_ESPECIAL,
                            fase=RA.FASE_RECUPERACION_ESPECIAL)
    resultados[0] = area('LE', RA.REPROBADA_DEFINITIVA,
                         fase=RA.FASE_RECUPERACION_ESPECIAL)
    r = prim(4, resultados)
    igual(r['condicion'], PA.REPROBADO)
    igual(r['motivo'], PA.MOTIVO_ESPECIAL_NO_SUPERADA)


@test("B6  Especial a medias -> sigue APLAZADO")
def _():
    resultados = con_fallos(3, RA.NO_APROBADA_TRAS_RECUPERACION_FINAL)
    resultados[0] = area('LE', RA.APROBADA_RECUPERACION_ESPECIAL,
                         fase=RA.FASE_RECUPERACION_ESPECIAL)
    r = prim(4, resultados)
    igual(r['condicion'], PA.APLAZADO)
    igual(r['requiere_recuperacion_especial'], True)


@test("B7  las areas que pasaron por Especial CUENTAN como caidas tras Final")
def _():
    # Cuatro areas ya en Especial: si no se contaran, pareceria 0 fallos.
    r = prim(4, con_fallos(4, RA.APROBADA_RECUPERACION_ESPECIAL,
                           fase=RA.FASE_RECUPERACION_ESPECIAL))
    igual(r['condicion'], PA.REPROBADO,
          'cuatro en Especial siguen siendo cuatro fallos tras la Final')


# ══════════════════ P3 · TERCERO Y ALFABETIZACION ══════════════════
print(f"\n{B}TERCERO: ALFABETIZACION INICIAL{X}")


@test("C1  areas OK + alfabetizacion True -> PROMOVIDO")
def _():
    r = prim(3, todas(), {'alfabetizacion_inicial': True})
    igual(r['condicion'], PA.PROMOVIDO)


@test("C2  areas OK + alfabetizacion False -> REPROBADO")
def _():
    r = prim(3, todas(), {'alfabetizacion_inicial': False})
    igual(r['condicion'], PA.REPROBADO)
    igual(r['motivo'], PA.MOTIVO_ALFABETIZACION_NO_LOGRADA)


@test("C3  areas OK + alfabetizacion None -> EN_PROCESO")
def _():
    r = prim(3, todas(), {'alfabetizacion_inicial': None})
    igual(r['condicion'], PA.EN_PROCESO)
    assert PA.BLOQUEO_ALFABETIZACION_NO_INFORMADA in r['bloqueos']


@test("C4  4+ areas caidas + alfabetizacion None -> REPROBADO por areas")
def _():
    r = prim(3, con_fallos(4, RA.NO_APROBADA_TRAS_RECUPERACION_FINAL))
    igual(r['condicion'], PA.REPROBADO,
          'ya hay causa suficiente; el dato que falta no lo convierte en otra cosa')
    igual(r['motivo'], PA.MOTIVO_DEMASIADAS_NO_APROBADAS)
    assert PA.ADV_ALFABETIZACION_NO_INFORMADA in r['advertencias']


@test("C5  Especial superada + alfabetizacion False -> REPROBADO")
def _():
    r = prim(3, con_fallos(2, RA.APROBADA_RECUPERACION_ESPECIAL,
                           fase=RA.FASE_RECUPERACION_ESPECIAL),
             {'alfabetizacion_inicial': False})
    igual(r['condicion'], PA.REPROBADO)
    igual(r['motivo'], PA.MOTIVO_ALFABETIZACION_NO_LOGRADA)


@test("C6  la alfabetizacion NO se infiere de ninguna nota")
def _():
    import inspect
    fuente = inspect.getsource(PA)
    ini = fuente.index('def _gate_alfabetizacion')
    cuerpo = fuente[ini:fuente.index('\ndef ', ini + 10)]
    for prohibido in ('LE', 'MAT', 'nota', 'cf', 'edad', 'asistencia'):
        assert ("'%s'" % prohibido) not in cuerpo, prohibido
    assert "contexto.get('alfabetizacion_inicial')" in cuerpo


@test("C7  la alfabetizacion fuera de 3ro es una inconsistencia")
def _():
    for grado in (1, 2, 4, 5, 6):
        r = prim(grado, todas(), {'alfabetizacion_inicial': False})
        if grado in (1, 2):
            continue   # 1ro/2do no pasan por la cascada de 3ro-6to
        assert PA.INC_ALFABETIZACION_FUERA_DE_TERCERO in r['inconsistencias'], \
            grado
        igual(r['condicion'], PA.EN_PROCESO, 'la inconsistencia bloquea')


# ══════════ L · ORDEN NORMATIVO DE LA ALFABETIZACION (A2.3) ══════════
#
# La norma pide repitencia en 3.o por alfabetizacion no lograda «luego de
# haber participado en TODOS los procesos de recuperacion pedagogica y
# especial». Mientras al estudiante le falte la Especial, la alfabetizacion
# todavia no decide: ni lo reprueba ni lo esconde detras de un EN_PROCESO.
print(f"\n{B}TERCERO: LA ALFABETIZACION LLEGA DESPUES DE LA ESPECIAL{X}")

# Un 3.o al que le falta la Recuperacion Especial: 1 area caida tras la Final.
def _aplazado_3ro():
    return con_fallos(1, RA.NO_APROBADA_TRAS_RECUPERACION_FINAL)


# Un 3.o que YA hizo la Especial y la supero en las dos areas que cayeron.
def _especial_superada_3ro():
    return con_fallos(2, RA.APROBADA_RECUPERACION_ESPECIAL)


@test("L1  APLAZADO + alfabetizacion False -> sigue APLAZADO, NO REPROBADO")
def _():
    r = prim(3, _aplazado_3ro(), {'alfabetizacion_inicial': False})
    igual(r['condicion'], PA.APLAZADO,
          'reprobarlo aqui le quita la Especial a la que tiene derecho')
    igual(r['es_definitiva'], False)
    igual(r['requiere_recuperacion_especial'], True)
    assert PA.ADV_ALFABETIZACION_NO_LOGRADA_ESPECIAL_PENDIENTE \
        in r['advertencias'], r['advertencias']
    igual(r['motivo'], PA.MOTIVO_ELEGIBLE_ESPECIAL)


@test("L2  APLAZADO + alfabetizacion None -> sigue APLAZADO, NO EN_PROCESO")
def _():
    r = prim(3, _aplazado_3ro(), {'alfabetizacion_inicial': None})
    igual(r['condicion'], PA.APLAZADO,
          'un EN_PROCESO aqui esconde que le falta la Especial')
    igual(r['requiere_recuperacion_especial'], True)
    igual(r['bloqueos'], ())
    assert PA.ADV_ALFABETIZACION_PENDIENTE_REVISION in r['advertencias'], \
        r['advertencias']


@test("L3  APLAZADO + alfabetizacion True -> sigue APLAZADO")
def _():
    r = prim(3, _aplazado_3ro(), {'alfabetizacion_inicial': True})
    igual(r['condicion'], PA.APLAZADO,
          'la alfabetizacion lograda tampoco adelanta el final del proceso')
    igual(r['requiere_recuperacion_especial'], True)
    igual(r['bloqueos'], ())


@test("L4  Especial superada + alfabetizacion True -> PROMOVIDO")
def _():
    r = prim(3, _especial_superada_3ro(), {'alfabetizacion_inicial': True})
    igual(r['condicion'], PA.PROMOVIDO)
    igual(r['motivo'], PA.MOTIVO_ESPECIAL_SUPERADA)
    igual(r['es_definitiva'], True)


@test("L5  Especial superada + alfabetizacion False -> REPROBADO")
def _():
    r = prim(3, _especial_superada_3ro(), {'alfabetizacion_inicial': False})
    igual(r['condicion'], PA.REPROBADO,
          'agotado el proceso academico, ahora si decide la alfabetizacion')
    igual(r['motivo'], PA.MOTIVO_ALFABETIZACION_NO_LOGRADA)
    igual(r['es_definitiva'], True)


@test("L6  Especial superada + alfabetizacion None -> EN_PROCESO")
def _():
    r = prim(3, _especial_superada_3ro(), {'alfabetizacion_inicial': None})
    igual(r['condicion'], PA.EN_PROCESO,
          'a punto de promover no se certifica sin el dato')
    assert PA.BLOQUEO_ALFABETIZACION_NO_INFORMADA in r['bloqueos'], \
        r['bloqueos']
    igual(r['es_definitiva'], False)


@test("L7  sin Especial que hacer + alfabetizacion False -> REPROBADO")
def _():
    r = prim(3, todas(), {'alfabetizacion_inicial': False})
    igual(r['condicion'], PA.REPROBADO,
          'no hay proceso pendiente: la alfabetizacion es el ultimo gate')
    igual(r['motivo'], PA.MOTIVO_ALFABETIZACION_NO_LOGRADA)


@test("L8  REPROBADO por 4+ areas + alfabetizacion None -> REPROBADO")
def _():
    r = prim(3, con_fallos(4, RA.NO_APROBADA_TRAS_RECUPERACION_FINAL),
             {'alfabetizacion_inicial': None})
    igual(r['condicion'], PA.REPROBADO)
    igual(r['motivo'], PA.MOTIVO_DEMASIADAS_NO_APROBADAS)
    assert PA.ADV_ALFABETIZACION_NO_INFORMADA in r['advertencias']
    igual(r['bloqueos'], (), 'el dato que falta no abre un proceso ya cerrado')


@test("L9  REPROBADO tras la Especial + alfabetizacion True -> REPROBADO")
def _():
    r = prim(3, con_fallos(1, RA.REPROBADA_DEFINITIVA),
             {'alfabetizacion_inicial': True})
    igual(r['condicion'], PA.REPROBADO,
          'la alfabetizacion lograda no rescata una Especial fallida')
    igual(r['motivo'], PA.MOTIVO_ESPECIAL_NO_SUPERADA)


@test("L10 APLAZADO + alfabetizacion 'NO' -> EN_PROCESO por dato invalido")
def _():
    r = prim(3, _aplazado_3ro(), {'alfabetizacion_inicial': 'NO'})
    igual(r['condicion'], PA.EN_PROCESO,
          'el tipo invalido sigue siendo inconsistencia de entrada (A2.1)')
    assert PA.INC_ALFABETIZACION_VALOR_INVALIDO in r['inconsistencias']
    assert PA.BLOQUEO_DATOS_INCONSISTENTES in r['bloqueos']


@test("L11 los valores invalidos NO se relajan en ningun escenario de 3ro")
def _():
    for escenario in (todas(), _aplazado_3ro(), _especial_superada_3ro(),
                      con_fallos(4, RA.NO_APROBADA_TRAS_RECUPERACION_FINAL)):
        for malo in ('NO', 0, 1, [], {}, 1.0, 'True'):
            r = prim(3, escenario, {'alfabetizacion_inicial': malo})
            igual(r['condicion'], PA.EN_PROCESO, repr(malo))
            assert PA.BLOQUEO_DATOS_INCONSISTENTES in r['bloqueos'], repr(malo)


# ══════════════════ S · SECUNDARIA ══════════════════
print(f"\n{B}SECUNDARIA{X}")


def sec_todas(estado=RA.APROBADA):
    return todas(estado, CURRICULO_SEC, nivel=RA.NIVEL_SECUNDARIA)


def sec_fallos(n, estado, fase=_FASE_DEL_CONTRATO):
    return con_fallos(n, estado, fase, CURRICULO_SEC,
                      nivel=RA.NIVEL_SECUNDARIA)


@test("D1  todo aprobado normal -> PROMOVIDO")
def _():
    r = sec(2, sec_todas())
    igual(r['condicion'], PA.PROMOVIDO)
    igual(r['es_definitiva'], True)


@test("D2  Completiva pendiente -> EN_PROCESO")
def _():
    r = sec(2, sec_fallos(1, RA.PENDIENTE_COMPLETIVA))
    igual(r['condicion'], PA.EN_PROCESO)
    assert PA.BLOQUEO_AREAS_PENDIENTES in r['bloqueos']


@test("D3  Extraordinaria pendiente -> EN_PROCESO")
def _():
    r = sec(2, sec_fallos(1, RA.PENDIENTE_EXTRAORDINARIA))
    igual(r['condicion'], PA.EN_PROCESO)


@test("D4  1 y 2 no aprobadas tras Extraordinaria -> APLAZADO")
def _():
    for n in (1, 2):
        r = sec(2, sec_fallos(n, RA.NO_APROBADA_TRAS_EXTRAORDINARIA))
        igual(r['condicion'], PA.APLAZADO, '%d' % n)
        igual(r['requiere_evaluacion_especial'], True)
        igual(r['es_definitiva'], False)


@test("D5  3 y 4+ tras Extraordinaria -> REPROBADO")
def _():
    for n in (3, 4, 5):
        r = sec(2, sec_fallos(n, RA.NO_APROBADA_TRAS_EXTRAORDINARIA))
        igual(r['condicion'], PA.REPROBADO, '%d' % n)
        igual(r['requiere_evaluacion_especial'], False)


@test("D6  1 y 2 Especiales aprobadas -> PROMOVIDO")
def _():
    for n in (1, 2):
        r = sec(2, sec_fallos(n, RA.APROBADA_ESPECIAL, fase=RA.FASE_ESPECIAL))
        igual(r['condicion'], PA.PROMOVIDO, '%d' % n)
        igual(r['motivo'], PA.MOTIVO_ESPECIAL_SUPERADA)


@test("D7  una Especial reprobada -> REPROBADO")
def _():
    resultados = sec_fallos(2, RA.APROBADA_ESPECIAL, fase=RA.FASE_ESPECIAL)
    resultados[0] = area('LE', RA.REPROBADA_DEFINITIVA, fase=RA.FASE_ESPECIAL,
                         nivel=RA.NIVEL_SECUNDARIA)
    r = sec(2, resultados)
    igual(r['condicion'], PA.REPROBADO)
    igual(r['motivo'], PA.MOTIVO_ESPECIAL_NO_SUPERADA)


@test("D8  Especial a medias -> sigue APLAZADO")
def _():
    resultados = sec_fallos(2, RA.NO_APROBADA_TRAS_EXTRAORDINARIA)
    resultados[0] = area('LE', RA.APROBADA_ESPECIAL, fase=RA.FASE_ESPECIAL,
                         nivel=RA.NIVEL_SECUNDARIA)
    r = sec(2, resultados)
    igual(r['condicion'], PA.APLAZADO)


@test("D9  las que pasaron por Especial cuentan como caidas tras Extra")
def _():
    r = sec(2, sec_fallos(3, RA.APROBADA_ESPECIAL, fase=RA.FASE_ESPECIAL))
    igual(r['condicion'], PA.REPROBADO,
          'tres en Especial siguen siendo tres fallos tras la Extraordinaria')


# ══════════════════ E · ELEGIBILIDAD DEL PROCESO ESPECIAL ══════════════════
#
# Lo que A1 no podia saber. Esta es la seccion critica de A2.
print(f"\n{B}ELEGIBILIDAD DEL PROCESO ESPECIAL{X}")


@test("E1  PRIMARIA: la Especial NO rescata con 4+ caidas tras la Final")
def _():
    # Las cuatro tienen Especial APROBADA. A1, area por area, las dio por
    # aprobadas. A2 ve el conjunto y no lo permite.
    r = prim(4, con_fallos(4, RA.APROBADA_RECUPERACION_ESPECIAL,
                           fase=RA.FASE_RECUPERACION_ESPECIAL))
    igual(r['condicion'], PA.REPROBADO)
    assert PA.INC_ESPECIAL_NO_ELEGIBLE_PRIMARIA in r['inconsistencias'], \
        r['inconsistencias']


@test("E2  PRIMARIA: mezcla de Especial aprobada y no aprobada con 5 caidas")
def _():
    resultados = con_fallos(5, RA.APROBADA_RECUPERACION_ESPECIAL,
                            fase=RA.FASE_RECUPERACION_ESPECIAL)
    r = prim(4, resultados)
    igual(r['condicion'], PA.REPROBADO)
    assert PA.INC_ESPECIAL_NO_ELEGIBLE_PRIMARIA in r['inconsistencias']


@test("E3  SECUNDARIA: la Especial NO rescata con 3+ caidas tras Extra")
def _():
    r = sec(2, sec_fallos(3, RA.APROBADA_ESPECIAL, fase=RA.FASE_ESPECIAL))
    igual(r['condicion'], PA.REPROBADO)
    assert PA.INC_ESPECIAL_NO_ELEGIBLE_SECUNDARIA in r['inconsistencias'], \
        r['inconsistencias']


@test("E4  SECUNDARIA: con 4 tampoco")
def _():
    r = sec(2, sec_fallos(4, RA.APROBADA_ESPECIAL, fase=RA.FASE_ESPECIAL))
    igual(r['condicion'], PA.REPROBADO)
    assert PA.INC_ESPECIAL_NO_ELEGIBLE_SECUNDARIA in r['inconsistencias']


@test("E5  el limite exacto: 3 en Primaria SI, 4 NO")
def _():
    tres = prim(4, con_fallos(3, RA.APROBADA_RECUPERACION_ESPECIAL,
                              fase=RA.FASE_RECUPERACION_ESPECIAL))
    igual(tres['condicion'], PA.PROMOVIDO)
    igual(tres['inconsistencias'], ())
    cuatro = prim(4, con_fallos(4, RA.APROBADA_RECUPERACION_ESPECIAL,
                                fase=RA.FASE_RECUPERACION_ESPECIAL))
    igual(cuatro['condicion'], PA.REPROBADO)


@test("E6  el limite exacto: 2 en Secundaria SI, 3 NO")
def _():
    dos = sec(2, sec_fallos(2, RA.APROBADA_ESPECIAL, fase=RA.FASE_ESPECIAL))
    igual(dos['condicion'], PA.PROMOVIDO)
    igual(dos['inconsistencias'], ())
    tres = sec(2, sec_fallos(3, RA.APROBADA_ESPECIAL, fase=RA.FASE_ESPECIAL))
    igual(tres['condicion'], PA.REPROBADO)


# ══════════════════ F · ASISTENCIA ══════════════════
print(f"\n{B}ASISTENCIA{X}")


def asist(**ctx):
    return PA.resolver_situacion_estudiante(
        RA.NIVEL_PRIMARIA, 4, todas(), CURRICULO_PRIM, ctx)


@test("F1  20% exacto no dispara revision")
def _():
    r = asist(porcentaje_ausencias_no_justificadas=20)
    igual(r['condicion'], PA.PROMOVIDO)


@test("F2  20.01% sin decision humana -> EN_PROCESO")
def _():
    r = asist(porcentaje_ausencias_no_justificadas=20.01)
    igual(r['condicion'], PA.EN_PROCESO)
    assert PA.BLOQUEO_REVISION_ASISTENCIA in r['bloqueos']


@test("F3  25% + PERMITIR_APROBACION -> sigue la regla academica")
def _():
    r = asist(porcentaje_ausencias_no_justificadas=25,
              decision_asistencia=PA.ASISTENCIA_PERMITIR_APROBACION)
    igual(r['condicion'], PA.PROMOVIDO)


@test("F4  25% + REPETIR_GRADO -> REPROBADO por decision del equipo")
def _():
    r = asist(porcentaje_ausencias_no_justificadas=25,
              decision_asistencia=PA.ASISTENCIA_REPETIR_GRADO)
    igual(r['condicion'], PA.REPROBADO)
    igual(r['motivo'], PA.MOTIVO_DECISION_ASISTENCIA)
    igual(r['es_definitiva'], True)


@test("F5  asistencia no disponible -> no hay decision oficial definitiva")
def _():
    r = PA.resolver_situacion_estudiante(RA.NIVEL_PRIMARIA, 4, todas(),
                                         CURRICULO_PRIM, {})
    igual(r['condicion'], PA.EN_PROCESO)
    assert PA.BLOQUEO_ASISTENCIA_NO_EVALUADA in r['bloqueos']
    igual(r['es_definitiva'], False)


@test("F6  REPROBAR_ASIGNATURAS -> GAP normativo declarado, no inventado")
def _():
    r = asist(porcentaje_ausencias_no_justificadas=25,
              decision_asistencia=PA.ASISTENCIA_REPROBAR_ASIGNATURAS)
    igual(r['condicion'], PA.EN_PROCESO)
    assert PA.BLOQUEO_REPROBAR_ASIGNATURAS_SIN_NORMA in r['bloqueos'], \
        r['bloqueos']


@test("F7  una decision desconocida no se interpreta como permiso")
def _():
    r = asist(porcentaje_ausencias_no_justificadas=25,
              decision_asistencia='LO_QUE_SEA')
    igual(r['condicion'], PA.EN_PROCESO)


@test("F8  si ya es REPROBADO por areas, la asistencia no lo bloquea")
def _():
    r = PA.resolver_situacion_estudiante(
        RA.NIVEL_PRIMARIA, 4,
        con_fallos(5, RA.NO_APROBADA_TRAS_RECUPERACION_FINAL),
        CURRICULO_PRIM, {})
    igual(r['condicion'], PA.REPROBADO,
          'ya hay causa suficiente: bloquear no lo revertiria')
    igual(r['es_definitiva'], True)
    assert PA.ADV_ASISTENCIA_NO_REVISADA in r['advertencias']


# ══════════════════ H · SEXTO DE SECUNDARIA ══════════════════
print(f"\n{B}SEXTO DE SECUNDARIA{X}")


@test("H1  6to PROMOVIDO no dice graduado, titulado ni egresado")
def _():
    r = sec(6, sec_todas())
    igual(r['condicion'], PA.PROMOVIDO)
    texto = repr(r).lower()
    for palabra in ('graduado', 'titulado', 'egresado'):
        assert palabra not in texto, palabra


@test("H2  6to PROMOVIDO avisa de que la titulacion es otra fase")
def _():
    r = sec(6, sec_todas())
    assert PA.ADV_TITULACION_PENDIENTE in r['advertencias'], r['advertencias']


@test("H3  el aviso no aparece en los demas grados ni si no promueve")
def _():
    igual(PA.ADV_TITULACION_PENDIENTE in sec(5, sec_todas())['advertencias'],
          False)
    r = sec(6, sec_fallos(3, RA.NO_APROBADA_TRAS_EXTRAORDINARIA))
    igual(PA.ADV_TITULACION_PENDIENTE in r['advertencias'], False)


# ══════════════════ W · GATES ENDURECIDOS (A2.1) ══════════════════
print(f"\n{B}GATES ENDURECIDOS (A2.1){X}")

CUATRO = ['LE', 'MAT', 'CS', 'CN']


@test("W1  EL BUG: una oficial SOBRANTE no altera la decision")
def _():
    # Cuatro esperadas aprobadas + una oficial NO esperada reprobada.
    # Antes subia total_oficiales a 5, contaba como reprobada y convertia
    # el PROMOVIDO en APLAZADO.
    res = [area(c, RA.APROBADA) for c in CUATRO]
    res.append(area('EF', RA.NO_APROBADA_TRAS_RECUPERACION_FINAL))
    r = prim(4, res, curriculo=CUATRO)
    igual(r['total_oficiales'], 4, 'la sobrante no cuenta')
    igual(r['no_aprobadas'], 0, 'la sobrante no puede aparecer como reprobada')
    igual(r['aprobadas'], 4)
    assert 'EF' not in r['codigos_no_aprobados'], r['codigos_no_aprobados']
    assert PA.INC_AREAS_OFICIALES_NO_ESPERADAS in r['inconsistencias']
    igual(r['condicion'], PA.EN_PROCESO, 'tampoco se promueve en silencio')
    assert PA.BLOQUEO_DATOS_INCONSISTENTES in r['bloqueos']


@test("W2  una sobrante APROBADA tambien bloquea")
def _():
    res = [area(c, RA.APROBADA) for c in CUATRO] + [area('EF', RA.APROBADA)]
    r = prim(4, res, curriculo=CUATRO)
    igual(r['total_oficiales'], 4)
    igual(r['aprobadas'], 4, 'la sobrante no infla el conteo')
    igual(r['condicion'], PA.EN_PROCESO)
    assert PA.INC_AREAS_OFICIALES_NO_ESPERADAS in r['inconsistencias']


@test("W3  seleccion EXACTA del multiconjunto: LE, LE, MAT con tres LE")
def _():
    res = [area('LE', RA.APROBADA), area('LE', RA.APROBADA),
           area('LE', RA.NO_APROBADA_TRAS_RECUPERACION_FINAL),
           area('MAT', RA.APROBADA)]
    r = prim(4, res, curriculo=['LE', 'LE', 'MAT'])
    igual(r['total_oficiales'], 3, 'participan LE, LE y MAT; la tercera LE no')
    igual(r['no_aprobadas'], 0, 'la LE sobrante no entra')
    assert PA.INC_AREAS_OFICIALES_NO_ESPERADAS in r['inconsistencias']


@test("W4  sin sobrantes, el multiconjunto repetido funciona con normalidad")
def _():
    res = [area('LE', RA.APROBADA), area('LE', RA.APROBADA),
           area('MAT', RA.APROBADA)]
    r = prim(4, res, curriculo=['LE', 'LE', 'MAT'])
    igual(r['condicion'], PA.PROMOVIDO)
    igual(r['total_oficiales'], 3)
    igual(r['inconsistencias'], ())


@test("W5  grado invalido -> EN_PROCESO en los seis casos")
def _():
    for grado in (0, 7, -1, '3', True, 3.5):
        r = PA.resolver_situacion_estudiante(RA.NIVEL_PRIMARIA, grado, todas(),
                                             CURRICULO_PRIM, OK_ASIST)
        igual(r['condicion'], PA.EN_PROCESO, repr(grado))
        igual(r['es_definitiva'], False, repr(grado))
        assert PA.BLOQUEO_GRADO_INVALIDO in r['bloqueos'], repr(grado)


@test("W6  los grados 1..6 se aceptan")
def _():
    for grado in (1, 2, 3, 4, 5, 6):
        ctx = {'alfabetizacion_inicial': True} if grado == 3 else {}
        r = prim(grado, todas(), ctx)
        assert PA.BLOQUEO_GRADO_INVALIDO not in r['bloqueos'], grado
        igual(r['condicion'], PA.PROMOVIDO, 'grado %d' % grado)


@test("W7  nivel de A1 incompatible -> fail-closed")
def _():
    res = todas()
    res[0] = area('LE', RA.APROBADA, nivel=RA.NIVEL_SECUNDARIA)
    r = prim(4, res)
    igual(r['condicion'], PA.EN_PROCESO)
    assert PA.INC_NIVEL_INCOMPATIBLE in r['inconsistencias'], r['inconsistencias']
    assert PA.BLOQUEO_DATOS_INCONSISTENTES in r['bloqueos']


@test("W8  estado A1 desconocido NO se interpreta como reprobacion")
def _():
    for estado in (None, '', 'XYZ', 'aprobada', 123):
        res = todas()
        res[0] = area('LE', estado)
        r = prim(4, res)
        igual(r['condicion'], PA.EN_PROCESO, repr(estado))
        igual(r['no_aprobadas'], 0,
              'un estado desconocido no puede hacer repetir: %r' % (estado,))
        assert PA.INC_ESTADO_A1_DESCONOCIDO in r['inconsistencias'], repr(estado)


@test("W9  alfabetizacion con valor invalido -> EN_PROCESO, no PROMOVIDO")
def _():
    # «NO» no es False ni None: sin esto, 3ro salia PROMOVIDO.
    for valor in ('NO', 'SI', 0, 1, [], {}, 'False'):
        r = prim(3, todas(), {'alfabetizacion_inicial': valor})
        igual(r['condicion'], PA.EN_PROCESO, repr(valor))
        assert PA.INC_ALFABETIZACION_VALOR_INVALIDO in r['inconsistencias'], \
            repr(valor)


@test("W10 los tres valores validos de alfabetizacion siguen funcionando")
def _():
    igual(prim(3, todas(), {'alfabetizacion_inicial': True})['condicion'],
          PA.PROMOVIDO)
    igual(prim(3, todas(), {'alfabetizacion_inicial': False})['condicion'],
          PA.REPROBADO)
    igual(prim(3, todas(), {'alfabetizacion_inicial': None})['condicion'],
          PA.EN_PROCESO)


@test("W11 porcentaje de asistencia invalido -> EN_PROCESO")
def _():
    for valor in ('20', [], True, -1, 100.1, float('nan'), float('inf'), {}):
        r = PA.resolver_situacion_estudiante(
            RA.NIVEL_PRIMARIA, 4, todas(), CURRICULO_PRIM,
            {'porcentaje_ausencias_no_justificadas': valor})
        igual(r['condicion'], PA.EN_PROCESO, repr(valor))
        assert PA.BLOQUEO_ASISTENCIA_INVALIDA in r['bloqueos'], repr(valor)


@test("W12 porcentajes validos en los bordes")
def _():
    for valor in (0, 0.0, 20, 20.0, 100):
        r = PA.resolver_situacion_estudiante(
            RA.NIVEL_PRIMARIA, 4, todas(), CURRICULO_PRIM,
            {'porcentaje_ausencias_no_justificadas': valor,
             'decision_asistencia': PA.ASISTENCIA_PERMITIR_APROBACION})
        assert PA.BLOQUEO_ASISTENCIA_INVALIDA not in r['bloqueos'], repr(valor)


@test("W13 curriculo esperado como CADENA -> invalido, no se deshace en letras")
def _():
    r = PA.resolver_situacion_estudiante(RA.NIVEL_PRIMARIA, 4, todas(),
                                         'LE', OK_ASIST)
    igual(r['condicion'], PA.EN_PROCESO)
    assert PA.BLOQUEO_CURRICULO_INVALIDO in r['bloqueos'], r['bloqueos']


@test("W14 elementos invalidos del curriculo -> bloqueo")
def _():
    for curr in ([''], ['  '], [None], ['LE', 3], ['LE', b'MAT']):
        r = PA.resolver_situacion_estudiante(RA.NIVEL_PRIMARIA, 4, todas(),
                                             curr, OK_ASIST)
        igual(r['condicion'], PA.EN_PROCESO, repr(curr))
        assert PA.BLOQUEO_CURRICULO_INVALIDO in r['bloqueos'], repr(curr)


# ── El momento normativo de la asistencia ──
@test("W15 APLAZADO sin asistencia sigue APLAZADO, no EN_PROCESO")
def _():
    # El proceso academico NO ha terminado: la revision de asistencia todavia
    # no toca, y esconder el aplazamiento ocultaria que queda una Especial.
    r = PA.resolver_situacion_estudiante(
        RA.NIVEL_PRIMARIA, 4,
        con_fallos(1, RA.NO_APROBADA_TRAS_RECUPERACION_FINAL),
        CURRICULO_PRIM, {})
    igual(r['condicion'], PA.APLAZADO)
    igual(r['requiere_recuperacion_especial'], True)
    assert PA.ADV_ASISTENCIA_PENDIENTE_DE_REVISION in r['advertencias']


@test("W16 SECUNDARIA: APLAZADO sin asistencia sigue APLAZADO")
def _():
    r = PA.resolver_situacion_estudiante(
        RA.NIVEL_SECUNDARIA, 2,
        con_fallos(1, RA.NO_APROBADA_TRAS_EXTRAORDINARIA,
                   curriculo=CURRICULO_SEC, nivel=RA.NIVEL_SECUNDARIA),
        CURRICULO_SEC, {})
    igual(r['condicion'], PA.APLAZADO)
    igual(r['requiere_evaluacion_especial'], True)


@test("W17 al pasar a PROMOVIDO, la asistencia SI se exige")
def _():
    # Misma area, ya superada la Especial: ahora el gate corresponde.
    r = PA.resolver_situacion_estudiante(
        RA.NIVEL_PRIMARIA, 4,
        con_fallos(1, RA.APROBADA_RECUPERACION_ESPECIAL,
                   fase=RA.FASE_RECUPERACION_ESPECIAL),
        CURRICULO_PRIM, {})
    igual(r['condicion'], PA.EN_PROCESO, 'ahora si toca revisar la asistencia')
    assert PA.BLOQUEO_ASISTENCIA_NO_EVALUADA in r['bloqueos']


@test("W18 1ro NO puede repetir por la via generica de asistencia")
def _():
    r = PA.resolver_situacion_estudiante(
        RA.NIVEL_PRIMARIA, 1, todas(), CURRICULO_PRIM,
        {'porcentaje_ausencias_no_justificadas': 25,
         'decision_asistencia': PA.ASISTENCIA_REPETIR_GRADO})
    igual(r['condicion'], PA.EN_PROCESO, 'en 1ro no se contempla la repitencia')
    assert PA.BLOQUEO_REPETIR_NO_APLICA_1RO in r['bloqueos'], r['bloqueos']


@test("W19 2do exige formalizar por la excepcion colegiada")
def _():
    r = PA.resolver_situacion_estudiante(
        RA.NIVEL_PRIMARIA, 2, todas(), CURRICULO_PRIM,
        {'porcentaje_ausencias_no_justificadas': 25,
         'decision_asistencia': PA.ASISTENCIA_REPETIR_GRADO})
    igual(r['condicion'], PA.EN_PROCESO)
    assert PA.BLOQUEO_REPETIR_2DO_REQUIERE_EXCEPCION in r['bloqueos'], \
        r['bloqueos']


@test("W20 3ro-6to y Secundaria SI aceptan REPETIR_GRADO por asistencia")
def _():
    for grado in (3, 4, 5, 6):
        ctx = {'porcentaje_ausencias_no_justificadas': 25,
               'decision_asistencia': PA.ASISTENCIA_REPETIR_GRADO}
        if grado == 3:
            ctx['alfabetizacion_inicial'] = True
        r = PA.resolver_situacion_estudiante(RA.NIVEL_PRIMARIA, grado, todas(),
                                             CURRICULO_PRIM, ctx)
        igual(r['condicion'], PA.REPROBADO, 'grado %d' % grado)
        igual(r['motivo'], PA.MOTIVO_DECISION_ASISTENCIA)
    r2 = PA.resolver_situacion_estudiante(
        RA.NIVEL_SECUNDARIA, 3, sec_todas(), CURRICULO_SEC,
        {'porcentaje_ausencias_no_justificadas': 25,
         'decision_asistencia': PA.ASISTENCIA_REPETIR_GRADO})
    igual(r2['condicion'], PA.REPROBADO)


@test("W21 nada de lo recibido se muta, ni el curriculo")
def _():
    resultados = todas()
    curriculo = list(CURRICULO_PRIM)
    contexto = dict(OK_ASIST)
    a, b, c = (copy.deepcopy(resultados), copy.deepcopy(curriculo),
               copy.deepcopy(contexto))
    PA.resolver_situacion_estudiante(RA.NIVEL_PRIMARIA, 4, resultados,
                                     curriculo, contexto)
    igual(resultados, a, 'resultados mutados')
    igual(curriculo, b, 'curriculo mutado')
    igual(contexto, c, 'contexto mutado')


# ══════════════════ X · EXCEPCION DE 2.o, ESTRICTA (A2.2) ══════════════════
print(f"\n{B}EXCEPCION DE 2.o: TIPOS Y AMBITO{X}")


def _exc(grado=2, nivel=RA.NIVEL_PRIMARIA, **ctx):
    base = dict(OK_ASIST)
    base.update(ctx)
    curr = CURRICULO_PRIM if nivel == RA.NIVEL_PRIMARIA else CURRICULO_SEC
    return PA.resolver_situacion_estudiante(
        nivel, grado, todas(curriculo=curr, nivel=nivel), curr, base)


@test("X1  ya_utilizada=False -> la repeticion excepcional es valida")
def _():
    r = _exc(decision_excepcional_segundo='repetir',
             repeticion_excepcional_segundo_ya_utilizada=False)
    igual(r['condicion'], PA.REPROBADO)
    igual(r['motivo'], PA.MOTIVO_EXCEPCION_SEGUNDO)


@test("X2  ya_utilizada=True -> bloqueada, no hay segunda vez")
def _():
    r = _exc(decision_excepcional_segundo='repetir',
             repeticion_excepcional_segundo_ya_utilizada=True)
    igual(r['condicion'], PA.EN_PROCESO)
    assert PA.INC_EXCEPCION_SEGUNDO_YA_UTILIZADA in r['inconsistencias']


@test("X3  ya_utilizada=None -> antecedente no informado")
def _():
    r = _exc(decision_excepcional_segundo='repetir',
             repeticion_excepcional_segundo_ya_utilizada=None)
    igual(r['condicion'], PA.EN_PROCESO)
    assert PA.BLOQUEO_ANTECEDENTE_EXCEPCION_2DO in r['bloqueos'], r['bloqueos']


@test("X4-X7 un antecedente que no sea bool NO autoriza nada")
def _():
    # EL BUG: `1 is True` es False, asi que un 1 caia por la rama del else y
    # AUTORIZABA la repeticion.
    for valor in (1, 0, 'no', 'false', 'true', [], {}, 1.0):
        r = _exc(decision_excepcional_segundo='repetir',
                 repeticion_excepcional_segundo_ya_utilizada=valor)
        igual(r['condicion'], PA.EN_PROCESO, repr(valor))
        assert PA.INC_ANTECEDENTE_EXCEPCION_INVALIDO in r['inconsistencias'], \
            repr(valor)


@test("X8  decision de 2.o en Primaria 3.o-6.o -> EN_PROCESO")
def _():
    for grado in (1, 3, 4, 5, 6):
        r = _exc(grado=grado, decision_excepcional_segundo='repetir',
                 repeticion_excepcional_segundo_ya_utilizada=False)
        igual(r['condicion'], PA.EN_PROCESO, 'grado %d' % grado)
        assert PA.INC_EXCEPCION_SEGUNDO_FUERA_DE_LUGAR in r['inconsistencias'], \
            grado


@test("X9  decision de 2.o en cualquier grado de Secundaria -> EN_PROCESO")
def _():
    for grado in (1, 2, 3, 4, 5, 6):
        r = _exc(grado=grado, nivel=RA.NIVEL_SECUNDARIA,
                 decision_excepcional_segundo='repetir',
                 repeticion_excepcional_segundo_ya_utilizada=False)
        igual(r['condicion'], PA.EN_PROCESO, 'secundaria %d' % grado)
        assert PA.INC_EXCEPCION_SEGUNDO_FUERA_DE_LUGAR in r['inconsistencias']


@test("X10 un antecedente SIN decision no desaparece en silencio")
def _():
    for valor in (True, False):
        r = _exc(repeticion_excepcional_segundo_ya_utilizada=valor)
        igual(r['condicion'], PA.EN_PROCESO, repr(valor))
        assert PA.INC_ANTECEDENTE_SIN_DECISION in r['inconsistencias'], repr(valor)
    # None explicito no es un contexto stale: no molesta.
    r = _exc(repeticion_excepcional_segundo_ya_utilizada=None)
    igual(r['condicion'], PA.PROMOVIDO)


# ══════════════════ Y · CONTRATO A1 -> A2 (A2.2) ══════════════════
print(f"\n{B}CONTRATO A1 -> A2{X}")


@test("Y1  estado exclusivo de Secundaria en Primaria -> EN_PROCESO")
def _():
    for estado in (RA.APROBADA_COMPLETIVA, RA.PENDIENTE_COMPLETIVA,
                   RA.APROBADA_EXTRAORDINARIA, RA.PENDIENTE_EXTRAORDINARIA,
                   RA.NO_APROBADA_TRAS_EXTRAORDINARIA, RA.APROBADA_ESPECIAL):
        res = todas()
        res[0] = area('LE', estado, nivel=RA.NIVEL_PRIMARIA)
        r = prim(4, res)
        igual(r['condicion'], PA.EN_PROCESO, estado)
        assert PA.INC_ESTADO_INCOMPATIBLE_CON_NIVEL in r['inconsistencias'], estado


@test("Y2  estado exclusivo de Primaria en Secundaria -> EN_PROCESO")
def _():
    for estado in (RA.APROBADA_RECUPERACION_FINAL,
                   RA.PENDIENTE_RECUPERACION_FINAL,
                   RA.NO_APROBADA_TRAS_RECUPERACION_FINAL,
                   RA.APROBADA_RECUPERACION_ESPECIAL):
        res = sec_todas()
        res[0] = area('LE', estado, nivel=RA.NIVEL_SECUNDARIA)
        r = sec(3, res)
        igual(r['condicion'], PA.EN_PROCESO, estado)
        assert PA.INC_ESTADO_INCOMPATIBLE_CON_NIVEL in r['inconsistencias'], estado


@test("Y3  EL BUG: REPROBADA_DEFINITIVA sin fase NO puede promover")
def _():
    # Se clasificaba como no aprobada, pero `_fallo_tras_extraordinaria`
    # devolvia False, asi que `caidas` quedaba vacia y salia PROMOVIDO con un
    # area definitivamente reprobada.
    res = sec_todas()
    res[0] = area('LE', RA.REPROBADA_DEFINITIVA, fase=None,
                  nivel=RA.NIVEL_SECUNDARIA)
    r = sec(3, res)
    igual(r['condicion'], PA.EN_PROCESO, 'jamas PROMOVIDO')
    assert PA.INC_ESTADO_FASE_INCOHERENTE in r['inconsistencias'], \
        r['inconsistencias']


@test("Y4  lo mismo en Primaria")
def _():
    res = todas()
    res[0] = area('LE', RA.REPROBADA_DEFINITIVA, fase=None)
    r = prim(4, res)
    igual(r['condicion'], PA.EN_PROCESO)
    assert PA.INC_ESTADO_FASE_INCOHERENTE in r['inconsistencias']


@test("Y5  los pares incoherentes de Secundaria")
def _():
    for estado, fase in ((RA.APROBADA_ESPECIAL, None),
                         (RA.APROBADA_COMPLETIVA, RA.FASE_ESPECIAL),
                         (RA.NO_APROBADA_TRAS_EXTRAORDINARIA, None),
                         (RA.APROBADA, RA.FASE_ESPECIAL),
                         (RA.SIN_CALIFICAR, RA.FASE_NORMAL)):
        res = sec_todas()
        res[0] = area('LE', estado, fase=fase, nivel=RA.NIVEL_SECUNDARIA)
        r = sec(3, res)
        igual(r['condicion'], PA.EN_PROCESO, '%s + %s' % (estado, fase))
        assert PA.INC_ESTADO_FASE_INCOHERENTE in r['inconsistencias'], \
            '%s + %s' % (estado, fase)


@test("Y6  los pares incoherentes de Primaria")
def _():
    for estado, fase in ((RA.APROBADA_RECUPERACION_ESPECIAL, None),
                         (RA.NO_APROBADA_TRAS_RECUPERACION_FINAL, None),
                         (RA.APROBADA_RECUPERACION_FINAL, RA.FASE_NORMAL),
                         (RA.APROBADA, RA.FASE_RECUPERACION_ESPECIAL),
                         (RA.PENDIENTE_RECUPERACION_FINAL, RA.FASE_NORMAL)):
        res = todas()
        res[0] = area('LE', estado, fase=fase)
        r = prim(4, res)
        igual(r['condicion'], PA.EN_PROCESO, '%s + %s' % (estado, fase))
        assert PA.INC_ESTADO_FASE_INCOHERENTE in r['inconsistencias'], \
            '%s + %s' % (estado, fase)


@test("Y7  TODOS los pares legitimos de A1 pasan la validacion")
def _():
    # Si A2 rechazara una salida legitima de A1, esto lo detecta.
    for nivel, matriz in PA.CONTRATO_ESTADO_FASE.items():
        curr = CURRICULO_PRIM if nivel == RA.NIVEL_PRIMARIA else CURRICULO_SEC
        for estado, fase in matriz.items():
            res = todas(curriculo=curr, nivel=nivel)
            res[0] = area('LE', estado, fase=fase, nivel=nivel)
            r = PA.resolver_situacion_estudiante(
                nivel, 4, res, curr,
                dict(OK_ASIST, alfabetizacion_inicial=True))
            assert PA.INC_ESTADO_FASE_INCOHERENTE not in r['inconsistencias'], \
                '%s %s + %s' % (nivel, estado, fase)
            assert PA.INC_ESTADO_INCOMPATIBLE_CON_NIVEL not in r['inconsistencias'], \
                '%s %s' % (nivel, estado)


@test("Y8  la matriz cubre exactamente los estados de cada nivel")
def _():
    todos = set()
    for matriz in PA.CONTRATO_ESTADO_FASE.values():
        todos |= set(matriz)
    igual(todos, set(RA.ESTADOS), 'la matriz debe cubrir todos los estados de A1')
    # REPROBADA_DEFINITIVA y SIN_CALIFICAR y APROBADA son de los dos niveles.
    comunes = (set(PA.CONTRATO_ESTADO_FASE[RA.NIVEL_PRIMARIA])
               & set(PA.CONTRATO_ESTADO_FASE[RA.NIVEL_SECUNDARIA]))
    igual(comunes, {RA.SIN_CALIFICAR, RA.APROBADA, RA.REPROBADA_DEFINITIVA})


# ══════════════════ V · ENTRADAS MALFORMADAS (A2.2) ══════════════════
print(f"\n{B}ENTRADAS MALFORMADAS{X}")


@test("V1  items de `resultados` que no son mappings -> bloqueo, sin traceback")
def _():
    for entrada in ([None], ['texto'], [5], [[]], [None, {}]):
        r = PA.resolver_situacion_estudiante(RA.NIVEL_PRIMARIA, 4, entrada,
                                             CURRICULO_PRIM, OK_ASIST)
        igual(r['condicion'], PA.EN_PROCESO, repr(entrada))
        assert PA.BLOQUEO_RESULTADOS_INVALIDOS in r['bloqueos'], repr(entrada)


@test("V2  `resultados` que no es una coleccion de materias -> bloqueo")
def _():
    for entrada in ('texto', b'bytes', 123, 4.5):
        r = PA.resolver_situacion_estudiante(RA.NIVEL_PRIMARIA, 4, entrada,
                                             CURRICULO_PRIM, OK_ASIST)
        igual(r['condicion'], PA.EN_PROCESO, repr(entrada))
        assert PA.BLOQUEO_RESULTADOS_INVALIDOS in r['bloqueos'], repr(entrada)


@test("V3  `resultados` vacio o None no revienta")
def _():
    for entrada in (None, [], ()):
        r = PA.resolver_situacion_estudiante(RA.NIVEL_PRIMARIA, 4, entrada,
                                             CURRICULO_PRIM, OK_ASIST)
        igual(r['condicion'], PA.EN_PROCESO, repr(entrada))
        assert PA.BLOQUEO_CURRICULO_INCOMPLETO in r['bloqueos']


@test("V4  `resultados` como generator se consume UNA vez")
def _():
    gen = (a for a in todas())
    r = PA.resolver_situacion_estudiante(RA.NIVEL_PRIMARIA, 4, gen,
                                         CURRICULO_PRIM, OK_ASIST)
    igual(r['condicion'], PA.PROMOVIDO)
    igual(r['total_oficiales'], 8)


@test("V5  un dict vacio como item no es valido academicamente pero no rompe")
def _():
    r = PA.resolver_situacion_estudiante(RA.NIVEL_PRIMARIA, 4, [{}],
                                         CURRICULO_PRIM, OK_ASIST)
    igual(r['condicion'], PA.EN_PROCESO)
    # Sin codigo curricular es una materia interna: no bloquea por si misma,
    # pero el curriculo queda incompleto.
    assert PA.BLOQUEO_CURRICULO_INCOMPLETO in r['bloqueos'], r['bloqueos']


@test("V6  `contexto` malformado -> bloqueo, sin traceback")
def _():
    for ctx in ('texto', [1, 2], 123, 4.5, b'x'):
        r = PA.resolver_situacion_estudiante(RA.NIVEL_PRIMARIA, 4, todas(),
                                             CURRICULO_PRIM, ctx)
        igual(r['condicion'], PA.EN_PROCESO, repr(ctx))
        assert PA.BLOQUEO_CONTEXTO_INVALIDO in r['bloqueos'], repr(ctx)


@test("V7  `contexto` None o vacio se tratan igual")
def _():
    for ctx in (None, {}):
        r = PA.resolver_situacion_estudiante(RA.NIVEL_PRIMARIA, 4, todas(),
                                             CURRICULO_PRIM, ctx)
        igual(r['condicion'], PA.EN_PROCESO, repr(ctx))
        assert PA.BLOQUEO_ASISTENCIA_NO_EVALUADA in r['bloqueos']


@test("V8  EL GENERATOR DE CURRICULO se consume UNA vez")
def _():
    # Antes `_curriculo_utilizable` lo vaciaba y `Counter` recibia nada, asi
    # que el curriculo parecia inexistente.
    gen = (c for c in CURRICULO_PRIM)
    r = PA.resolver_situacion_estudiante(RA.NIVEL_PRIMARIA, 4, todas(),
                                         gen, OK_ASIST)
    igual(r['condicion'], PA.PROMOVIDO)
    assert PA.BLOQUEO_SIN_CURRICULO_OFICIAL not in r['bloqueos']
    # Identico a pasarlo como lista.
    r2 = prim(4, todas())
    igual(r['condicion'], r2['condicion'])
    igual(r['total_oficiales'], r2['total_oficiales'])


@test("V9  materias internas no necesitan el contrato academico completo")
def _():
    # Sin codigo curricular no participan: que su estado no encaje da igual.
    res = todas() + [{'area_curricular_codigo': None, 'estado': 'LO_QUE_SEA',
                      'nivel': 'otro', 'fase': 'rara', 'inconsistencias': ()}]
    r = prim(4, res)
    igual(r['condicion'], PA.PROMOVIDO)
    igual(len(r['codigos_no_oficiales']), 1)


@test("V10 nada de lo recibido se muta, tampoco un generator materializado")
def _():
    resultados = todas()
    curriculo = list(CURRICULO_PRIM)
    contexto = dict(OK_ASIST)
    a, b, c = (copy.deepcopy(resultados), copy.deepcopy(curriculo),
               copy.deepcopy(contexto))
    PA.resolver_situacion_estudiante(RA.NIVEL_PRIMARIA, 4, resultados,
                                     curriculo, contexto)
    igual(resultados, a)
    igual(curriculo, b)
    igual(contexto, c)


# ══════════════════ Z · PUREZA Y NO-DIVERGENCIA ══════════════════
print(f"\n{B}PUREZA Y NO-DIVERGENCIA{X}")


@test("Z1  A2 no importa models, app, database ni sqlalchemy")
def _():
    import ast, inspect
    arbol = ast.parse(inspect.getsource(PA))
    importados = set()
    for n in ast.walk(arbol):
        if isinstance(n, ast.Import):
            importados.update(a.name.split('.')[0] for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module:
            importados.add(n.module.split('.')[0])
    for prohibido in ('models', 'app', 'database', 'sqlalchemy'):
        assert prohibido not in importados, (prohibido, importados)
    igual(importados, {'collections', 'resultado_academico'})


@test("Z2  A2 no recalcula ninguna nota")
def _():
    import ast, inspect
    fuente = inspect.getsource(PA)
    arbol = ast.parse(fuente)
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.Module, ast.FunctionDef, ast.ClassDef)):
            if (nodo.body and isinstance(nodo.body[0], ast.Expr)
                    and isinstance(nodo.body[0].value, ast.Constant)
                    and isinstance(nodo.body[0].value.value, str)):
                nodo.body[0].value.value = ''
    codigo = ast.unparse(arbol)
    for prohibido in ('0.5', '0.3', '0.7', 'cf_area', 'redondear_calificacion',
                      'calcular_completiva', 'calcular_extraordinaria',
                      'calcular_especial', '65', '70'):
        assert prohibido not in codigo, \
            'A2 parece recalcular o repetir un corte: %r' % prohibido


@test("Z3  A2 no muta nada ni toca la base")
def _():
    import ast, inspect
    arbol = ast.parse(inspect.getsource(PA))
    for n in ast.walk(arbol):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
            assert n.func.id != 'setattr', 'setattr en A2'
        if isinstance(n, ast.Assign):
            for t in n.targets:
                assert not isinstance(t, ast.Attribute), ast.unparse(t)
    fuente = inspect.getsource(PA)
    for prohibido in ('db.', 'session', 'query(', 'commit'):
        assert prohibido not in fuente, prohibido


@test("Z4  no hay vocabulario paralelo de condiciones")
def _():
    import ast as _a, inspect
    arbol = _a.parse(inspect.getsource(PA))
    for nodo in _a.walk(arbol):
        if isinstance(nodo, (_a.Module, _a.FunctionDef, _a.ClassDef)):
            if (nodo.body and isinstance(nodo.body[0], _a.Expr)
                    and isinstance(nodo.body[0].value, _a.Constant)
                    and isinstance(nodo.body[0].value.value, str)):
                nodo.body[0].value.value = ''
    fuente = _a.unparse(arbol).lower()
    for paralelo in ('repitente_condicional', 'promovido_condicional',
                     "'repite'", 'repitente'):
        assert paralelo not in fuente, paralelo


@test("Z5  no se decide por el nombre textual de la asignatura")
def _():
    import inspect
    fuente = inspect.getsource(PA)
    for prohibido in ('asignatura.nombre', '.nombre ==', "== 'Musica'",
                      "== 'Música'"):
        assert prohibido not in fuente, prohibido


@test("Z6  `or` no se usa para elegir valores academicos")
def _():
    import ast, inspect
    arbol = ast.parse(inspect.getsource(PA))
    ors = [n for n in ast.walk(arbol)
           if isinstance(n, ast.BoolOp) and isinstance(n.op, ast.Or)]
    # Solo se admiten sobre colecciones/contexto, nunca sobre notas.
    for n in ors:
        texto = ast.unparse(n)
        for nota in ('nota', 'cf', 'final'):
            assert nota not in texto.lower(), texto


@test("Z7  ningun camino promueve con bloqueos")
def _():
    casos = [
        PA.resolver_situacion_estudiante(RA.NIVEL_PRIMARIA, 4, todas(), None, OK_ASIST),
        prim(4, [area('LE', RA.APROBADA)]),
        prim(3, todas(), {'alfabetizacion_inicial': None}),
        PA.resolver_situacion_estudiante(RA.NIVEL_PRIMARIA, 4, todas(),
                                         CURRICULO_PRIM, {}),
    ]
    for r in casos:
        if r['bloqueos']:
            igual(r['condicion'], PA.EN_PROCESO, str(r['bloqueos']))
            igual(r['es_definitiva'], False)


@test("Z8  una sola funcion cambia la condicion por alfabetizacion")
def _():
    # A2.3 elimino el GATE 12 duplicado. Si alguien vuelve a decidir por
    # alfabetizacion en otro sitio, las dos reglas se separan en silencio.
    import ast as _ast
    import inspect
    arbol = _ast.parse(inspect.getsource(PA))
    decisorias = {
        'BLOQUEO_ALFABETIZACION_NO_INFORMADA',
        'MOTIVO_ALFABETIZACION_NO_LOGRADA',
        'ADV_ALFABETIZACION_NO_INFORMADA',
        'ADV_ALFABETIZACION_NO_LOGRADA_ESPECIAL_PENDIENTE',
        'ADV_ALFABETIZACION_PENDIENTE_REVISION',
    }
    usuarias = []
    for nodo in arbol.body:
        if not isinstance(nodo, _ast.FunctionDef):
            continue
        nombres = {n.id for n in _ast.walk(nodo) if isinstance(n, _ast.Name)}
        if nombres & decisorias:
            usuarias.append(nodo.name)
    igual(sorted(usuarias), ['_gate_alfabetizacion'],
          'la semantica de alfabetizacion vive en un solo sitio')


@test("Z9  el orden de gates de 3ro esta escrito, no solo implicito")
def _():
    import inspect
    ini = inspect.getsource(PA).index('def _gate_alfabetizacion')
    cuerpo = inspect.getsource(PA)[ini:]
    cuerpo = cuerpo[:cuerpo.index('\ndef ', 10)]
    # Las tres condiciones de entrada se tratan por separado y en ese orden.
    assert cuerpo.index('condicion == APLAZADO') \
        < cuerpo.index('condicion == REPROBADO'), \
        'el aplazamiento se resuelve antes que nada'
    assert 'PROMOVIDO' in cuerpo or 'Candidato' in cuerpo


print("\n" + "=" * 70)
if _fail:
    print(f"{R}{B}R4-A2: {len(_fail)} fallo(s) de {_total}{X}")
    for n, e in _fail:
        print(f"  - {n}: {e}")
    sys.exit(1)
print(f"{B}R4-A2 PROMOCION CANONICA: {_ok}/{_total} pruebas{X}")
print(f"{G}{B}TODO VERDE{X}")
