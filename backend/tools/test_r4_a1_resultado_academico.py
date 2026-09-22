# -*- coding: utf-8 -*-
"""
R4-A1 — el motor canónico de nota final por área/asignatura.

QUE COMPRUEBA
    Que `resultado_academico` responde bien la unica pregunta que le toca
    —en que situacion esta ESTA area— y que NO responde las que no le tocan.

    Lo mas importante no son los estados: es la seccion Z, la de
    NO-DIVERGENCIA. Ahi se cambian en caliente las formulas de los motores
    existentes y se exige que el resolver devuelva el numero nuevo. Si
    alguien copiara el 50/50 o el 30/70 dentro del resolver, esas pruebas
    fallarian. El objetivo de R4 es UNA formula con varios consumidores, y
    esto es lo que lo mantiene cierto.

    Son pruebas PURAS: sin base de datos, sin HTTP. Los objetos se construyen
    a mano.

Uso:
    cd backend
    python tools/test_r4_a1_resultado_academico.py
"""
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import resultado_academico as RA                               # noqa: E402
from calculo_primaria import MINIMO_APROBATORIO_PRIMARIA       # noqa: E402

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


# ── dobles mínimos, sin ORM ───────────────────────────────────────────
class _Comp:
    """Una fila CalificacionPrimaria, lo justo para que cf_area la lea."""

    def __init__(self, numero, p1=None, p2=None, p3=None, p4=None,
                 ne=()):
        self.competencia_numero = numero
        self.p1, self.p2, self.p3, self.p4 = p1, p2, p3, p4
        self.rp1 = self.rp2 = self.rp3 = self.rp4 = None
        for n in (1, 2, 3, 4):
            setattr(self, 'ne%d' % n, n in ne)

    # cf_area -> cf_competencia -> calcular_final: misma semantica que el
    # modelo real (R2/R3), reproducida aqui solo para no arrastrar el ORM.
    def es_ne(self, periodo):
        return bool(getattr(self, 'ne%d' % periodo, False))

    def valor_periodo(self, periodo):
        rp = getattr(self, 'rp%d' % periodo)
        return rp if rp is not None else getattr(self, 'p%d' % periodo)

    def calcular_final(self, minimo_periodos=1):
        valores = []
        for p in range(1, 5):
            if self.es_ne(p):
                continue
            v = self.valor_periodo(p)
            if v is None:
                return None
            valores.append(v)
        if not valores:
            return None
        return round(sum(valores) / len(valores), 2)


def _area(nota, ne=()):
    """Las tres competencias oficiales, todas con la misma nota."""
    return [_Comp(n, p1=nota, p2=nota, p3=nota, p4=nota, ne=ne)
            for n in (1, 2, 3)]


class _Rec:
    """Una fila RecuperacionPrimaria."""

    def __init__(self, recuperacion_final=None, recuperacion_especial=None):
        self.recuperacion_final = recuperacion_final
        self.recuperacion_especial = recuperacion_especial


class _Ev:
    """Una fila EvaluacionExtraSecundaria: se usan SUS metodos reales."""

    def __init__(self, cf_original=None, cec=None, ceex=None, ce=None):
        self.cf_original = cf_original
        self.cec, self.ceex, self.ce = cec, ceex, ce

    # Delegacion literal a los metodos del modelo real. No se copia ninguna
    # formula: se toman las funciones tal cual estan definidas en models.py.
    from models import EvaluacionExtraSecundaria as _M
    calcular_completiva_final = _M.calcular_completiva_final
    calcular_extraordinaria_final = _M.calcular_extraordinaria_final
    calcular_especial_final = _M.calcular_especial_final
    del _M


def igual(obtenido, esperado, msg=''):
    if obtenido != esperado:
        raise AssertionError('%s\n        esperado %r\n        obtenido %r'
                             % (msg, esperado, obtenido))


# ══════════════════ P · PRIMARIA ══════════════════
print(f"\n{B}PRIMARIA{X}")


@test("P1  sin CF -> SIN_CALIFICAR y pendiente")
def _():
    r = RA.resolver_nota_primaria([])
    igual(r['estado'], RA.SIN_CALIFICAR)
    igual(r['nota_final'], None)
    igual(r['pendiente'], True)
    igual(r['requiere_contexto_promocion'], False)


@test("P2  CF=65 -> APROBADA en fase normal")
def _():
    r = RA.resolver_nota_primaria(_area(65))
    igual(r['estado'], RA.APROBADA)
    igual(r['nota_base'], 65)
    igual(r['nota_final'], 65)
    igual(r['fase'], RA.FASE_NORMAL)
    igual(r['pendiente'], False)


@test("P3  CF=64 sin recuperacion -> PENDIENTE_RECUPERACION_FINAL")
def _():
    r = RA.resolver_nota_primaria(_area(64))
    igual(r['estado'], RA.PENDIENTE_RECUPERACION_FINAL)
    igual(r['nota_base'], 64)
    igual(r['nota_final'], None, 'un area pendiente no tiene nota final')
    igual(r['pendiente'], True)


@test("P4  CF=64 + rec.final=65 -> APROBADA_RECUPERACION_FINAL")
def _():
    r = RA.resolver_nota_primaria(_area(64), _Rec(recuperacion_final=65))
    igual(r['estado'], RA.APROBADA_RECUPERACION_FINAL)
    igual(r['nota_final'], 65)
    igual(r['fase'], RA.FASE_RECUPERACION_FINAL)


@test("P5  CF=64 + rec.final=64 -> NO_APROBADA + requiere contexto")
def _():
    r = RA.resolver_nota_primaria(_area(64), _Rec(recuperacion_final=64),
                                  grado_numero=4)
    igual(r['estado'], RA.NO_APROBADA_TRAS_RECUPERACION_FINAL)
    igual(r['nota_final'], 64)
    igual(r['requiere_contexto_promocion'], True,
          'si toca Especial o repitencia lo decide A2, no A1')
    igual(r['pendiente'], False)


@test("P6  especial=65 en 4to -> APROBADA_RECUPERACION_ESPECIAL")
def _():
    r = RA.resolver_nota_primaria(
        _area(60), _Rec(recuperacion_final=62, recuperacion_especial=65),
        grado_numero=4)
    igual(r['estado'], RA.APROBADA_RECUPERACION_ESPECIAL)
    igual(r['nota_final'], 65)
    igual(r['fase'], RA.FASE_RECUPERACION_ESPECIAL)
    igual(r['requiere_contexto_promocion'], False)


@test("P7  especial=64 en 4to -> REPROBADA_DEFINITIVA")
def _():
    r = RA.resolver_nota_primaria(
        _area(60), _Rec(recuperacion_final=62, recuperacion_especial=64),
        grado_numero=4)
    igual(r['estado'], RA.REPROBADA_DEFINITIVA)
    igual(r['nota_final'], 64)


@test("P8  el 0 no se pierde en ningun punto")
def _():
    r = RA.resolver_nota_primaria(_area(0))
    igual(r['nota_base'], 0, 'un area con 0 tiene CF 0, no None')
    igual(r['estado'], RA.PENDIENTE_RECUPERACION_FINAL)
    # 0 como resultado de la final: sigue siendo una nota
    r2 = RA.resolver_nota_primaria(_area(0), _Rec(recuperacion_final=0),
                                   grado_numero=5)
    igual(r2['nota_final'], 0, 'la final de 0 no puede volverse None')
    igual(r2['estado'], RA.NO_APROBADA_TRAS_RECUPERACION_FINAL)
    # 0 como resultado de la especial
    r3 = RA.resolver_nota_primaria(
        _area(0), _Rec(recuperacion_final=0, recuperacion_especial=0),
        grado_numero=5)
    igual(r3['nota_final'], 0)
    igual(r3['estado'], RA.REPROBADA_DEFINITIVA)


@test("P9  competencia incompleta -> SIN_CALIFICAR (R3 manda)")
def _():
    # Solo C1 y C2: cf_area exige el conjunto oficial completo.
    igual(RA.resolver_nota_primaria(_area(80)[:2])['estado'], RA.SIN_CALIFICAR)
    # Las tres, pero una sin P4 -> tampoco hay CF (R2)
    comps = _area(80)
    comps[2].p4 = None
    igual(RA.resolver_nota_primaria(comps)['estado'], RA.SIN_CALIFICAR)


@test("P10 NE sigue resolviendose por el motor R2/R3")
def _():
    # P4 en NE: la CF sale del promedio de los evaluados, no bloquea.
    comps = [_Comp(n, p1=80, p2=80, p3=80, p4=None, ne=(4,)) for n in (1, 2, 3)]
    r = RA.resolver_nota_primaria(comps)
    igual(r['estado'], RA.APROBADA)
    igual(r['nota_base'], 80)


@test("P11 1ro con Especial legacy -> inconsistencia, sin usar el dato")
def _():
    r = RA.resolver_nota_primaria(
        _area(60), _Rec(recuperacion_final=62, recuperacion_especial=90),
        grado_numero=1)
    assert RA.INCONSISTENCIA_ESPECIAL_EN_PRIMER_CICLO in r['inconsistencias'], \
        r['inconsistencias']
    igual(r['estado'], RA.NO_APROBADA_TRAS_RECUPERACION_FINAL,
          'la Especial de 1ro NO puede aprobar el area')
    igual(r['nota_final'], 62, 'la nota es la de la final, no la especial')


@test("P12 2do con Especial legacy -> misma inconsistencia")
def _():
    r = RA.resolver_nota_primaria(
        _area(60), _Rec(recuperacion_final=62, recuperacion_especial=90),
        grado_numero=2)
    assert RA.INCONSISTENCIA_ESPECIAL_EN_PRIMER_CICLO in r['inconsistencias']
    igual(r['estado'], RA.NO_APROBADA_TRAS_RECUPERACION_FINAL)


@test("P13 1ro/2do SI tienen CF y Recuperacion Final numerica")
def _():
    # La correccion normativa: en 1ro y 2do la Recuperacion FINAL del area es
    # numerica (distinta de la recuperacion pedagogica del periodo, que es
    # cualitativa). El resolver debe tratarla con normalidad.
    for grado in (1, 2):
        r = RA.resolver_nota_primaria(_area(60), _Rec(recuperacion_final=70),
                                      grado_numero=grado)
        igual(r['estado'], RA.APROBADA_RECUPERACION_FINAL,
              'grado %d' % grado)
        igual(r['nota_final'], 70)


@test("P14 A1 nunca produce repitencia ni promocion")
def _():
    for caso in (RA.resolver_nota_primaria(_area(10), grado_numero=1),
                 RA.resolver_nota_primaria(_area(10), _Rec(recuperacion_final=10),
                                           grado_numero=6)):
        texto = repr(caso).lower()
        for palabra in ('promovido', 'repite', 'repitente', 'aplazado'):
            assert palabra not in texto, (palabra, caso)


@test("P15 grado desconocido con Especial -> se avisa que no se valido")
def _():
    r = RA.resolver_nota_primaria(
        _area(60), _Rec(recuperacion_final=62, recuperacion_especial=70))
    assert RA.INCONSISTENCIA_GRADO_DESCONOCIDO in r['inconsistencias']
    igual(r['estado'], RA.APROBADA_RECUPERACION_ESPECIAL,
          'sin grado no se cambia la decision, solo se informa')


# ══════════════════ S · SECUNDARIA ══════════════════
print(f"\n{B}SECUNDARIA{X}")


@test("S1  sin CF -> SIN_CALIFICAR")
def _():
    igual(RA.resolver_nota_secundaria(_Ev())['estado'], RA.SIN_CALIFICAR)
    igual(RA.resolver_nota_secundaria(None)['estado'], RA.SIN_CALIFICAR)


@test("S2  CF oficial 70 -> APROBADA")
def _():
    r = RA.resolver_nota_secundaria(_Ev(cf_original=70))
    igual(r['estado'], RA.APROBADA)
    igual(r['nota_final'], 70)
    igual(r['fase'], RA.FASE_NORMAL)


@test("S3  CF 69 sin CEC -> PENDIENTE_COMPLETIVA")
def _():
    r = RA.resolver_nota_secundaria(_Ev(cf_original=69))
    igual(r['estado'], RA.PENDIENTE_COMPLETIVA)
    igual(r['nota_base'], 69)
    igual(r['nota_final'], None)
    igual(r['pendiente'], True)


@test("S4  completiva >=70 -> APROBADA_COMPLETIVA")
def _():
    # 50%*60 + 50%*80 = 70
    r = RA.resolver_nota_secundaria(_Ev(cf_original=60, cec=80))
    igual(r['estado'], RA.APROBADA_COMPLETIVA)
    igual(r['nota_final'], 70)
    igual(r['fase'], RA.FASE_COMPLETIVA)


@test("S5  completiva <70 y sin CEEX -> PENDIENTE_EXTRAORDINARIA")
def _():
    # 50%*60 + 50%*78 = 69
    r = RA.resolver_nota_secundaria(_Ev(cf_original=60, cec=78))
    igual(r['estado'], RA.PENDIENTE_EXTRAORDINARIA)
    igual(r['pendiente'], True)
    igual(r['nota_final'], None)


@test("S6  extraordinaria >=70 -> APROBADA_EXTRAORDINARIA")
def _():
    # 30%*60 + 70%*75 = 18 + 52.5 = 70.5 -> 71
    r = RA.resolver_nota_secundaria(_Ev(cf_original=60, cec=10, ceex=75))
    igual(r['estado'], RA.APROBADA_EXTRAORDINARIA)
    igual(r['nota_final'], 71)
    igual(r['fase'], RA.FASE_EXTRAORDINARIA)


@test("S7  extraordinaria <70 sin CE -> NO_APROBADA + requiere contexto")
def _():
    # 30%*60 + 70%*60 = 60
    r = RA.resolver_nota_secundaria(_Ev(cf_original=60, cec=10, ceex=60))
    igual(r['estado'], RA.NO_APROBADA_TRAS_EXTRAORDINARIA)
    igual(r['nota_final'], 60)
    igual(r['requiere_contexto_promocion'], True,
          'si le tocaba Especial lo decide A2')
    igual(r['pendiente'], False)


@test("S8  especial cargada >=70 -> APROBADA_ESPECIAL")
def _():
    # base CF oficial 60 + CE 10 = 70
    r = RA.resolver_nota_secundaria(_Ev(cf_original=60, cec=10, ceex=60, ce=10))
    igual(r['estado'], RA.APROBADA_ESPECIAL)
    igual(r['nota_final'], 70)
    igual(r['fase'], RA.FASE_ESPECIAL)


@test("S9  especial cargada <70 -> REPROBADA_DEFINITIVA")
def _():
    r = RA.resolver_nota_secundaria(_Ev(cf_original=60, cec=10, ceex=60, ce=9))
    igual(r['estado'], RA.REPROBADA_DEFINITIVA)
    igual(r['nota_final'], 69)


@test("S10 un 0 en CEC / CEEX / CE no desaparece")
def _():
    # CEC = 0 es una nota: hay completiva, y da 50%*60+50%*0 = 30.
    # Con `or` se habria leido como «no hay completiva» -> PENDIENTE.
    r = RA.resolver_nota_secundaria(_Ev(cf_original=60, cec=0))
    igual(r['estado'], RA.PENDIENTE_EXTRAORDINARIA,
          'CEC=0 es una completiva REPROBADA, no una completiva ausente')
    # CEEX = 0
    r2 = RA.resolver_nota_secundaria(_Ev(cf_original=60, cec=0, ceex=0))
    igual(r2['estado'], RA.NO_APROBADA_TRAS_EXTRAORDINARIA)
    igual(r2['nota_final'], 18, '30%*60 + 70%*0 = 18')
    # CE = 0
    r3 = RA.resolver_nota_secundaria(_Ev(cf_original=60, cec=0, ceex=0, ce=0))
    igual(r3['estado'], RA.REPROBADA_DEFINITIVA)
    igual(r3['nota_final'], 60, 'CF oficial 60 + CE 0 = 60')


@test("S11 el redondeo academico 69.5 -> 70 se conserva")
def _():
    r = RA.resolver_nota_secundaria(_Ev(cf_original=69.5))
    igual(r['estado'], RA.APROBADA, 'CF oficial 69.5 -> 70')
    igual(r['nota_final'], 70)
    # y el caso historico de la extraordinaria: 0.3*17 + 0.7*92 = 69.5 -> 70
    r2 = RA.resolver_nota_secundaria(_Ev(cf_original=17, cec=10, ceex=92))
    igual(r2['estado'], RA.APROBADA_EXTRAORDINARIA)
    igual(r2['nota_final'], 70)


@test("S12 NO se lee condicion_final (dice reprobado con fases pendientes)")
def _():
    ev = _Ev(cf_original=69)
    ev.condicion_final = 'reprobado'     # lo que hoy guarda el modelo
    ev.nota_final = 69
    r = RA.resolver_nota_secundaria(ev)
    igual(r['estado'], RA.PENDIENTE_COMPLETIVA,
          'la fase pendiente manda sobre condicion_final')


@test("S13 A1 nunca produce promocion ni repitencia")
def _():
    texto = repr(RA.resolver_nota_secundaria(
        _Ev(cf_original=10, cec=0, ceex=0))).lower()
    for palabra in ('promovido', 'repite', 'repitente', 'aplazado'):
        assert palabra not in texto, palabra


# ══════════════════ Z · NO-DIVERGENCIA DE FORMULAS ══════════════════
#
# Lo que de verdad importa: que los numeros NO esten escritos aqui.
print(f"\n{B}NO-DIVERGENCIA DE FORMULAS{X}")


@test("Z1  el resolver NO contiene las formulas (50/50, 30/70, CF+CE)")
def _():
    import inspect
    fuente = inspect.getsource(RA)
    # Quitar comentarios y docstrings: los numeros pueden citarse al explicar.
    import ast
    arbol = ast.parse(fuente)
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.Module, ast.FunctionDef, ast.ClassDef)):
            if (nodo.body and isinstance(nodo.body[0], ast.Expr)
                    and isinstance(nodo.body[0].value, ast.Constant)
                    and isinstance(nodo.body[0].value.value, str)):
                nodo.body[0].value.value = ''
    codigo = ast.unparse(arbol)
    for prohibido in ('0.5', '0.3', '0.7', '"0.5"', "'0.5'"):
        assert prohibido not in codigo, \
            'el resolver parece reimplementar una ponderacion: %r' % prohibido
    assert 'ponderar_y_redondear' not in codigo, \
        'ni siquiera debe ponderar: eso lo hace el modelo'


@test("Z2  si cambia la formula de la completiva, el resolver la sigue")
def _():
    from models import EvaluacionExtraSecundaria as M
    original = M.calcular_completiva_final
    try:
        # Mutacion: la completiva pasa a ser siempre 100.
        M.calcular_completiva_final = lambda self: 100
        _Ev.calcular_completiva_final = M.calcular_completiva_final
        r = RA.resolver_nota_secundaria(_Ev(cf_original=60, cec=1))
        igual(r['estado'], RA.APROBADA_COMPLETIVA,
              'el resolver deberia usar la formula del modelo, no una copia')
        igual(r['nota_final'], 100)
    finally:
        M.calcular_completiva_final = original
        _Ev.calcular_completiva_final = original


@test("Z3  si cambia la extraordinaria, el resolver la sigue")
def _():
    from models import EvaluacionExtraSecundaria as M
    original = M.calcular_extraordinaria_final
    try:
        M.calcular_extraordinaria_final = lambda self: 99
        _Ev.calcular_extraordinaria_final = M.calcular_extraordinaria_final
        r = RA.resolver_nota_secundaria(_Ev(cf_original=60, cec=10, ceex=1))
        igual(r['estado'], RA.APROBADA_EXTRAORDINARIA)
        igual(r['nota_final'], 99)
    finally:
        M.calcular_extraordinaria_final = original
        _Ev.calcular_extraordinaria_final = original


@test("Z4  si cambia la especial, el resolver la sigue")
def _():
    from models import EvaluacionExtraSecundaria as M
    original = M.calcular_especial_final
    try:
        M.calcular_especial_final = lambda self: 5
        _Ev.calcular_especial_final = M.calcular_especial_final
        r = RA.resolver_nota_secundaria(_Ev(cf_original=60, cec=10, ceex=10, ce=1))
        igual(r['estado'], RA.REPROBADA_DEFINITIVA)
        igual(r['nota_final'], 5)
    finally:
        M.calcular_especial_final = original
        _Ev.calcular_especial_final = original


@test("Z5  si cambia cf_area, Primaria lo sigue")
def _():
    import calculo_primaria as CP
    original = CP.cf_area
    try:
        CP.cf_area = lambda comps: (99.0, 99)
        RA.cf_area = CP.cf_area
        r = RA.resolver_nota_primaria([])
        igual(r['estado'], RA.APROBADA, 'deberia usar cf_area, no un promedio propio')
        igual(r['nota_base'], 99)
    finally:
        CP.cf_area = original
        RA.cf_area = original


@test("Z6  el corte de Secundaria coincide con el del modelo")
def _():
    # Si alguien cambiara el 70 dentro de EvaluacionExtraSecundaria, esta
    # prueba lo detecta: el modelo debe cambiar de decision justo en el
    # umbral que declara el resolver.
    m = RA.MINIMO_APROBATORIO_SECUNDARIA
    igual(RA.resolver_nota_secundaria(_Ev(cf_original=m))['estado'], RA.APROBADA)
    igual(RA.resolver_nota_secundaria(_Ev(cf_original=m - 1))['estado'],
          RA.PENDIENTE_COMPLETIVA)
    ev = _Ev(cf_original=m)
    ev.recalcular_todo = None
    from models import EvaluacionExtraSecundaria as M
    real = M(cf_original=float(m))
    igual(real.calcular_condicion_final()[0], 'aprobado_normal',
          'el modelo debe aprobar en el mismo umbral que declara el resolver')


@test("Z7  el corte de Primaria sale de calculo_primaria")
def _():
    igual(MINIMO_APROBATORIO_PRIMARIA, 65)
    igual(RA.resolver_nota_primaria(_area(MINIMO_APROBATORIO_PRIMARIA))['estado'],
          RA.APROBADA)
    igual(RA.resolver_nota_primaria(
        _area(MINIMO_APROBATORIO_PRIMARIA - 1))['estado'],
        RA.PENDIENTE_RECUPERACION_FINAL)


@test("Z8  el contrato trae siempre las mismas claves")
def _():
    CLAVES = {'nivel', 'nota_base', 'fase', 'nota_final', 'estado',
              'pendiente', 'requiere_contexto_promocion',
              'area_curricular_codigo', 'inconsistencias'}
    for r in (RA.resolver_nota_primaria([]),
              RA.resolver_nota_primaria(_area(80)),
              RA.resolver_nota_secundaria(_Ev()),
              RA.resolver_nota_secundaria(_Ev(cf_original=60, cec=0, ceex=0))):
        igual(set(r), CLAVES)
        assert r['estado'] in RA.ESTADOS, r['estado']


@test("Z9  el codigo curricular oficial se transporta, no se inventa")
def _():
    r = RA.resolver_nota_primaria(_area(80), area_curricular_codigo='LE')
    igual(r['area_curricular_codigo'], 'LE')
    r2 = RA.resolver_nota_secundaria(_Ev(cf_original=80),
                                     area_curricular_codigo=None)
    igual(r2['area_curricular_codigo'], None, 'NULL es valido (Musica)')
    import inspect
    fuente = inspect.getsource(RA)
    for prohibido in ("asignatura.nombre", ".codigo ==", "nombre =="):
        assert prohibido not in fuente, prohibido


@test("Z10 el modulo es puro: no importa models, app ni database")
def _():
    import ast, inspect
    arbol = ast.parse(inspect.getsource(RA))
    importados = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            importados.update(a.name.split('.')[0] for a in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            importados.add(nodo.module.split('.')[0])
    for prohibido in ('models', 'app', 'database', 'sqlalchemy'):
        assert prohibido not in importados, (prohibido, importados)
    igual(importados, {'calculo_primaria', 'reglas_academicas'})


print("\n" + "=" * 68)
if _fail:
    print(f"{R}{B}R4-A1: {len(_fail)} fallo(s) de {_total}{X}")
    for n, e in _fail:
        print(f"  - {n}: {e}")
    sys.exit(1)
print(f"{B}R4-A1 RESULTADO ACADEMICO: {_ok}/{_total} pruebas{X}")
print(f"{G}{B}TODO VERDE{X}")
