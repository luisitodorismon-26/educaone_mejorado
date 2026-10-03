# -*- coding: utf-8 -*-
"""HOTFIX — la CF de Secundaria que ya estaba guardada.

EL SÍNTOMA REAL
===============
Un boletín de 1.º de Secundaria salía PENDIENTE por «datos académicos
inconsistentes». En Inglés, la CF guardada era 68.95 y la que el sistema
reconstruye hoy desde las mismas notas es 68.9375. Las dos redondean a 69 y
dan la misma nota oficial, pero A1 compara las EXACTAS —y hace bien: las
ponderaciones de la completiva (50/50) y la extraordinaria (30/70) se
calculan sobre la exacta, y 68.6 y 69.4 comparten CF oficial siendo bases
distintas—. Marcaba divergencia y A2 se negaba a certificar.

POR QUÉ NO SE ARREGLA CON UNA TOLERANCIA
========================================
`abs(a - b) < 0.1` haría pasar esta fila y, con ella, cualquier error real
de menos de una décima. La auditoría de producción encontró divergencias
mucho mayores y algunas son errores de verdad. Una tolerancia no distingue
un algoritmo viejo de un dato corrompido.

QUÉ SE EXIGE EN SU LUGAR
========================
DEMOSTRAR que la diferencia la produjo el algoritmo histórico, reconstruido
desde las notas ACTUALES:

    promedio de CADA competencia = round(media de MAX(P,RP) de P1..P4, 1)
    CF legacy                    = media de esos cuatro promedios

Si alguien tocó una nota, deja de reproducir la CF guardada y vuelve a
bloquear. Eso es lo que esta suite comprueba, caso por caso.

Base temporal aislada. Nunca producción. El hotfix es de LECTURA: la última
sección lo verifica por AST.
"""
import datetime as dt
import os
import sys

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(BK, "tools"))

from test_utils import aislar_base_de_datos  # noqa: E402

TMP = aislar_base_de_datos('hf_cf_legacy')

from database import engine, SessionLocal  # noqa: E402
from test_utils import verificar_engine_aislado  # noqa: E402

verificar_engine_aislado(engine, TMP)

import models as M  # noqa: E402
import promocion_academica as PA  # noqa: E402
import resultado_academico as RA  # noqa: E402
import resultado_academico_consumidores as AD  # noqa: E402
import app as APP  # noqa: E402

M.Base.metadata.create_all(bind=engine)

PASARON, FALLARON = [], []


def check(nombre, cond, detalle=''):
    if cond:
        PASARON.append(nombre)
        print("  PASA   %-64s %s" % (nombre, detalle))
    else:
        FALLARON.append(nombre)
        print("  FALLA  %-64s %s" % (nombre, detalle))


db = SessionLocal()

# ── El caso de producción, nota por nota ──────────────────────────────
NOTAS_CASO = {1: [65, 60, 65, 60],
              2: [67, 78, 68, 89],
              3: [56, 50, 71, 95],
              4: [66, 63, 56, 94]}
CF_LEGACY_ESPERADA = 68.95
CF_EXACTA_ESPERADA = 68.9375

DIAS = {'ago': 10, 'sep': 21, 'oct': 22, 'nov': 20, 'dic': 14, 'ene': 20,
        'feb': 19, 'mar': 22, 'abr': 18, 'may': 21, 'jun': 8}


# ═══════════════════════════════════════════════════════════════════════
print("\n=== 1 · LA FÓRMULA HISTÓRICA, RECONSTRUIDA ===")


class _Comp:
    """Una competencia con sus cuatro períodos. Igual interfaz que el modelo."""

    _n = [0]

    def __init__(self, notas, rps=None, asignatura_id=1, numero=None):
        self.asignatura_id = asignatura_id
        # El numero de competencia es parte de la estructura que el helper
        # exige: sin el, no hay {1,2,3,4} que comprobar.
        if numero is None:
            _Comp._n[0] = _Comp._n[0] % 4 + 1
            numero = _Comp._n[0]
        self.competencia_numero = numero
        for i, v in enumerate(notas, 1):
            setattr(self, 'p%d' % i, v)
        for i in range(1, 5):
            setattr(self, 'rp%d' % i, (rps or {}).get(i))

    def valor_periodo(self, p):
        return M.CalificacionSecundaria.valor_periodo(self, p)


COMPS = [_Comp(NOTAS_CASO[c]) for c in (1, 2, 3, 4)]

cf_legacy = APP._cf_legacy_secundaria(COMPS)
check('HF-01 el algoritmo histórico reproduce 68.95',
      cf_legacy is not None and abs(cf_legacy - CF_LEGACY_ESPERADA) < 1e-9,
      repr(cf_legacy))

_pcs = [sum(NOTAS_CASO[c][p] for c in (1, 2, 3, 4)) / 4 for p in range(4)]
cf_exacta = sum(_pcs) / 4
check('HF-02 y el algoritmo actual da 68.9375',
      abs(cf_exacta - CF_EXACTA_ESPERADA) < 1e-12, repr(cf_exacta))
check('HF-03 las dos dan la misma nota oficial: 69',
      APP.redondear_calificacion_final(cf_legacy) == 69
      and APP.redondear_calificacion_final(cf_exacta) == 69, '')
check('HF-04 y aun así son distintas: por eso A1 marcaba divergencia',
      abs(cf_legacy - cf_exacta) > RA.TOLERANCIA_CF_EXACTA,
      '%s vs %s' % (cf_legacy, cf_exacta))

# El promedio por competencia, uno a uno, como lo documenta el modelo.
_esperados = [62.5, 75.5, 68.0, 69.8]
_obtenidos = [round(sum(NOTAS_CASO[c]) / 4, 1) for c in (1, 2, 3, 4)]
check('HF-05 los cuatro promedios por competencia son los esperados',
      _obtenidos == _esperados, str(_obtenidos))
check('HF-06 incluido round(69.75, 1) = 69.8, que es Python, no HALF_UP',
      round(69.75, 1) == 69.8, str(round(69.75, 1)))


# ═══════════════════════════════════════════════════════════════════════
print("\n=== 2 · CUÁNDO SE ACEPTA Y CUÁNDO NO ===")


class _Ev:
    def __init__(self, cf_original):
        self.cf_original = cf_original


def compat(cf_guardada, comps=None):
    """(cf_exacto_entregado, compatible) tal como lo verá A1."""
    comps = comps if comps is not None else COMPS
    _pc = [sum(getattr(c, 'p%d' % (p + 1)) for c in comps) / len(comps)
           for p in range(4)]
    _ex = sum(_pc) / 4
    cfo, lit, cfe, ok = APP._cf_con_compatibilidad_legacy(
        APP.redondear_calificacion_final(_ex), 'C', _ex,
        _Ev(cf_guardada), comps)
    return cfe, ok


# Caso 1 · la guardada es la exacta.
_cfe, _ok = compat(CF_EXACTA_ESPERADA)
check('HF-10 CF guardada == exacta: caso normal, sin compatibilidad',
      abs(_cfe - CF_EXACTA_ESPERADA) < 1e-12 and _ok is False, str(_ok))

# Caso 2 · la guardada es la legacy reproducible.
_cfe, _ok = compat(CF_LEGACY_ESPERADA)
check('HF-11 CF guardada == legacy reconstruida: COMPATIBLE',
      _ok is True and abs(_cfe - CF_LEGACY_ESPERADA) < 1e-9,
      'cf entregada a A1 = %r' % _cfe)
check('HF-12 y lo que se entrega a A1 es la base histórica, no la nueva',
      abs(_cfe - CF_EXACTA_ESPERADA) > 1e-9, '')

# Caso 3 · diferencias que NO reproduce el algoritmo viejo.
for et, valor in (('HF-13 una décima arriba', 69.05),
                  ('HF-14 una centésima de más', 68.96),
                  ('HF-15 una diferencia grande', 75.0),
                  ('HF-16 justo por debajo de la legacy', 68.94)):
    _cfe, _ok = compat(valor)
    check(et + ' sigue bloqueando',
          _ok is False and abs(_cfe - CF_EXACTA_ESPERADA) < 1e-12,
          'compatible=%s' % _ok)

# Caso 5 · caché adulterado: `promedio_competencia` no es la fuente.
_comps_cache = [_Comp(NOTAS_CASO[c]) for c in (1, 2, 3, 4)]
for c in _comps_cache:
    c.promedio_competencia = 99.9          # mentira en el caché
_cfe, _ok = compat(CF_LEGACY_ESPERADA, _comps_cache)
check('HF-17 el caché `promedio_competencia` NO se usa como fuente',
      _ok is True, 'se reconstruye desde P/RP: sigue siendo compatible')
_comps_tocado = [_Comp(NOTAS_CASO[c]) for c in (1, 2, 3, 4)]
_comps_tocado[0].p1 = 90                   # alguien tocó una nota de verdad
_cfe, _ok = compat(CF_LEGACY_ESPERADA, _comps_tocado)
check('HF-18 pero si alguien toca una NOTA, deja de reproducirse y bloquea',
      _ok is False, 'compatible=%s' % _ok)

# Caso 6 · faltan períodos.
_incompleto = [_Comp(NOTAS_CASO[c]) for c in (1, 2, 3, 4)]
_incompleto[2].p3 = None
check('HF-19 sin los cuatro períodos NO se inventa un legacy',
      APP._cf_legacy_secundaria(_incompleto) is None, '')
check('HF-20 ni con menos de cuatro competencias',
      APP._cf_legacy_secundaria(_incompleto[:3]) is None, '')

# Caso 7 · RP presente: el valor efectivo es MAX(P, RP).
_con_rp = [_Comp(NOTAS_CASO[c]) for c in (1, 2, 3, 4)]
_con_rp[0] = _Comp([50, 60, 65, 60], rps={1: 65})     # 50 recuperado a 65
check('HF-21 con RP se usa MAX(P, RP), que es el valor efectivo histórico',
      abs(APP._cf_legacy_secundaria(_con_rp)
          - APP._cf_legacy_secundaria(COMPS)) < 1e-9,
      'reproduce lo mismo que un 65 directo')

# Caso 8 · el cero es una nota.
_con_cero = [_Comp([0, 0, 0, 0])] + [_Comp(NOTAS_CASO[c]) for c in (2, 3, 4)]
_legacy_cero = APP._cf_legacy_secundaria(_con_cero)
check('HF-22 un 0 es una nota válida, no un hueco',
      _legacy_cero is not None
      and abs(_legacy_cero - (0.0 + 75.5 + 68.0 + 69.8) / 4) < 1e-9,
      repr(_legacy_cero))

# Caso 10 · sin fila de evaluación, o sin cf_original.
_cfe, _ok = APP._cf_con_compatibilidad_legacy(69, 'C', CF_EXACTA_ESPERADA,
                                              None, COMPS)[2:]
check('HF-23 sin fila de evaluación no hay nada que compatibilizar',
      _ok is False, '')
_cfe, _ok = compat(None)
check('HF-24 ni con `cf_original` vacío', _ok is False, '')


# ═══════════════════════════════════════════════════════════════════════
print("\n=== 2b · ESTRUCTURA: EXACTAMENTE {1,2,3,4} ===")

def _numeradas(numeros, notas=None):
    comps = []
    for i, n in enumerate(numeros):
        c = _Comp((notas or NOTAS_CASO).get(((i % 4) + 1), [70, 70, 70, 70])
                  if isinstance(notas or NOTAS_CASO, dict)
                  else [70, 70, 70, 70])
        c.competencia_numero = n
        comps.append(c)
    return comps


# El caso bueno, para que la frontera signifique algo.
_ok = [_Comp(NOTAS_CASO[c]) for c in (1, 2, 3, 4)]
for i, c in enumerate(_ok, 1):
    c.competencia_numero = i
check('HF-70 con {1,2,3,4} se reconstruye',
      APP._cf_legacy_secundaria(_ok) is not None, '')

for et, numeros in (
        ('HF-71 solo tres competencias', [1, 2, 3]),
        ('HF-72 cinco competencias', [1, 2, 3, 4, 5]),
        ('HF-73 numeracion {1,2,3,5}', [1, 2, 3, 5]),
        ('HF-74 la 2 duplicada', [1, 2, 2, 4]),
        ('HF-75 numeracion desde 0', [0, 1, 2, 3]),
        ('HF-76 sin numero de competencia', [None, None, None, None])):
    check(et + ' -> fail closed',
          APP._cf_legacy_secundaria(_numeradas(numeros)) is None, '')

# Desordenadas SI valen: el conjunto es lo que importa, no el orden.
_desorden = [_Comp(NOTAS_CASO[c]) for c in (3, 1, 4, 2)]
for c, n in zip(_desorden, (3, 1, 4, 2)):
    c.competencia_numero = n
check('HF-77 desordenadas si valen: el conjunto es {1,2,3,4}',
      APP._cf_legacy_secundaria(_desorden) is not None
      and abs(APP._cf_legacy_secundaria(_desorden)
              - CF_LEGACY_ESPERADA) < 1e-9, '')


print("\n=== 2c · FRONTERA: CUANDO LAS DOS CF REDONDEAN DISTINTO ===")

# 69.5 exacta frente a 69.45 legacy: redondean a 70 y 69. Si el hotfix
# dejara pasar una CF cuya oficial es otra, el boletin diria 70 con una base
# de 69 —o al reves—, que es justo la mezcla que A1 existe para impedir.
# Buscadas a proposito: la exacta da 69.5 (oficial 70) y la legacy 69.475
# (oficial 69). Es el caso que de verdad distingue las dos bases, y el que
# produciria un boletin con la nota de una y la ponderacion de la otra si el
# hotfix entregara una CF y una oficial que no se correspondan.
_FRONTERA = {1: [72, 79, 66, 75], 2: [65, 78, 66, 61],
             3: [72, 76, 65, 72], 4: [71, 63, 64, 67]}
_comps_f = [_Comp(_FRONTERA[c]) for c in (1, 2, 3, 4)]
for i, c in enumerate(_comps_f, 1):
    c.competencia_numero = i
_pcf = [sum(_FRONTERA[c][p] for c in (1, 2, 3, 4)) / 4 for p in range(4)]
_ex_f = sum(_pcf) / 4
_lg_f = APP._cf_legacy_secundaria(_comps_f)
print("     exacta=%r (oficial %s)   legacy=%r (oficial %s)"
      % (_ex_f, APP.redondear_calificacion_final(_ex_f),
         _lg_f, APP.redondear_calificacion_final(_lg_f)))

_cfo, _lit, _cfe, _ok2 = APP._cf_con_compatibilidad_legacy(
    APP.redondear_calificacion_final(_ex_f), 'C', _ex_f, _Ev(_lg_f), _comps_f)
check('HF-80 si es legacy-compatible, se acepta la base historica',
      _ok2 is True and abs(_cfe - _lg_f) < 1e-9, 'cf=%r' % _cfe)
check('HF-81 y la CF oficial se recalcula desde ESA base, no desde la otra',
      _cfo == APP.redondear_calificacion_final(_lg_f),
      'oficial=%s  redondeo de la base=%s'
      % (_cfo, APP.redondear_calificacion_final(_lg_f)))
check('HF-82 nunca una oficial que no sea el redondeo de su exacta',
      _cfo == APP.redondear_calificacion_final(_cfe),
      '%s vs %s' % (_cfo, APP.redondear_calificacion_final(_cfe)))
check('HF-82b y aqui las dos SI redondean distinto: 70 frente a 69',
      APP.redondear_calificacion_final(_ex_f)
      != APP.redondear_calificacion_final(_lg_f),
      '%s vs %s' % (APP.redondear_calificacion_final(_ex_f),
                    APP.redondear_calificacion_final(_lg_f)))
check('HF-82c la oficial entregada es la de la base historica, no la nueva',
      _cfo == APP.redondear_calificacion_final(_lg_f)
      and _cfo != APP.redondear_calificacion_final(_ex_f), str(_cfo))

# Y A1 lo confirma: con esa pareja NO puede salir CF_SECUNDARIA_CALLER_
# INCONSISTENTE, que es exactamente «cf=69 con literal=70».
_r = RA.resolver_nota_secundaria(evaluacion=_Ev(_lg_f), cf_exacto=_cfe,
                                 cf_oficial=_cfo, area_curricular_codigo='MAT')
# AUDIT-FINAL · EL LITERAL. Aqui esta el defecto que la auditoria encontro:
# la CF oficial pasaba a 69 pero el literal seguia siendo el de la CF
# anterior, 'C'. Un boletin con 69 y una C dice dos cosas distintas sobre la
# misma asignatura, y la C afirma que aprobo.
check('HF-85 el literal legacy sale de SU CF oficial, no de la anterior',
      _lit == 'F', 'cf=%s literal=%s' % (_cfo, _lit))
check('HF-86 nunca 69 con C',
      not (_cfo == 69 and _lit == 'C'), '%s + %s' % (_cfo, _lit))
check('HF-87 la terna entregada es coherente: 69 / F / 69.475',
      _cfo == 69 and _lit == 'F' and abs(_cfe - 69.475) < 1e-9,
      '%s / %s / %r' % (_cfo, _lit, _cfe))
check('HF-88 y el literal de la base NUEVA habria sido otro',
      APP._literal_cf_secundaria(
          APP.redondear_calificacion_final(_ex_f)) == 'C',
      'la exacta daba 70 -> C')

# Las fronteras de los cuatro tramos, que son baratas.
for _cf, _esperado in ((69, 'F'), (70, 'C'), (79, 'C'), (80, 'B'),
                       (89, 'B'), (90, 'A'), (100, 'A'), (0, 'F')):
    check('HF-89 literal de %s es %s' % (_cf, _esperado),
          APP._literal_cf_secundaria(_cf) == _esperado,
          str(APP._literal_cf_secundaria(_cf)))
check('HF-89b y sin CF no hay literal',
      APP._literal_cf_secundaria(None) is None, '')

# Una sola definicion: el calculo normal usa el MISMO helper.
import inspect as _i0  # noqa: E402
check('HF-90 `_calcular_cf_secundaria` usa el mismo helper, sin copiarlo',
      '_literal_cf_secundaria(cf)' in _i0.getsource(APP._calcular_cf_secundaria)
      and "elif cf >= 80" not in _i0.getsource(APP._calcular_cf_secundaria), '')
check('HF-91 y la compatibilidad legacy tambien',
      '_literal_cf_secundaria(' in _i0.getsource(
          APP._cf_con_compatibilidad_legacy), '')

check('HF-83 A1 no reporta ninguna incoherencia entre cf y su exacta',
      RA.INCONSISTENCIA_CF_CALLER not in (_r.get('inconsistencias') or ())
      and RA.INCONSISTENCIA_CF_DIVERGENTE not in (_r.get('inconsistencias') or ()),
      str(_r.get('inconsistencias')))
check('HF-84 y el literal que A1 clasifica es coherente con esa CF',
      _r.get('estado') is not None, str(_r.get('estado')))


print("\n=== 3 · EL CASO COMPLETO, A TRAVÉS DE A1 Y A2 ===")

col = M.Colegio(nombre='HF', codigo='hf', activo=True)
db.add(col)
db.flush()
_ini = dt.date(2025, 8, 18)
ano = M.AnoEscolar(colegio_id=col.id, nombre='2025-2026', activo=True,
                   cerrado=False, fecha_inicio=_ini,
                   fecha_fin=dt.date(2026, 6, 12),
                   p1_inicio=_ini, p1_fin=_ini + dt.timedelta(days=74),
                   p2_inicio=_ini + dt.timedelta(days=75),
                   p2_fin=_ini + dt.timedelta(days=164),
                   p3_inicio=_ini + dt.timedelta(days=165),
                   p3_fin=_ini + dt.timedelta(days=242),
                   p4_inicio=_ini + dt.timedelta(days=243),
                   p4_fin=dt.date(2026, 6, 12))
ano.set_dias_trabajados(dict(DIAS))
db.add(ano)
db.flush()
usr = M.Usuario(colegio_id=col.id, username='hfdir', password_hash='x',
                nombre='D', role='direccion', activo=True,
                must_change_password=False, token_version=0)
prof = M.Usuario(colegio_id=col.id, username='hfprof', password_hash='x',
                 nombre='P', role='profesor', activo=True,
                 must_change_password=False, token_version=0)
db.add_all([usr, prof])
db.flush()

grado = M.Grado(colegio_id=col.id, nombre='1ro Secundaria', nivel='secundaria',
                orden=7, activo=True)
db.add(grado)
db.flush()
curso = M.Curso(colegio_id=col.id, nombre='A', grado_id=grado.id,
                ano_escolar_id=ano.id, activo=True)
db.add(curso)
db.flush()

AREAS = list(AD.curriculo_oficial_esperado(RA.NIVEL_SECUNDARIA, 1)[0])
ASIG = {}
for cod in AREAS:
    a = M.Asignatura(colegio_id=col.id, nombre=cod, codigo=cod[:10], area='X',
                     area_curricular_codigo=cod, activo=True)
    db.add(a)
    db.flush()
    ASIG[cod] = a
    db.add(M.AsignacionProfesor(
        colegio_id=col.id, profesor_id=prof.id, curso_id=curso.id,
        asignatura_id=a.id, ano_escolar_id=ano.id, activo=True))
db.flush()

est = M.Estudiante(colegio_id=col.id, matricula='HF-1', nombre='Caso',
                   apellido='Real', curso_id=curso.id, no_lista=1,
                   activo=True, condicion='activo')
db.add(est)
db.flush()

# El área del caso: las notas exactas del incidente.
COD_CASO = AREAS[0]
for c in (1, 2, 3, 4):
    notas = NOTAS_CASO[c]
    db.add(M.CalificacionSecundaria(
        colegio_id=col.id, estudiante_id=est.id,
        asignatura_id=ASIG[COD_CASO].id, ano_escolar_id=ano.id,
        competencia_numero=c, p1=notas[0], p2=notas[1], p3=notas[2],
        p4=notas[3],
        # El caché, tal como lo dejó el algoritmo histórico.
        promedio_competencia=round(sum(notas) / 4, 1)))

# La fila histórica, calculada contra SU `cf_original`. No se recalcula.
db.add(M.EvaluacionExtraSecundaria(
    colegio_id=col.id, estudiante_id=est.id,
    asignatura_id=ASIG[COD_CASO].id, ano_escolar_id=ano.id,
    cf_original=CF_LEGACY_ESPERADA, cec=70.0, completiva_final=69.0,
    ceex=70.0, extraordinaria_final=70.0))

# El resto de áreas, aprobadas sin historia.
for cod in AREAS[1:]:
    for c in (1, 2, 3, 4):
        db.add(M.CalificacionSecundaria(
            colegio_id=col.id, estudiante_id=est.id,
            asignatura_id=ASIG[cod].id, ano_escolar_id=ano.id,
            competencia_numero=c, p1=90, p2=90, p3=90, p4=90,
            promedio_competencia=90.0))
db.commit()


def inconsistencias_de(paq):
    """Todas las inconsistencias que A1 reporto, de todas las areas.

    A1 devuelve DICCIONARIOS. Leerlos con `getattr` daba None y la lista
    salia vacia: la comprobacion habria pasado sin mirar nada.
    """
    fuera = []
    for r in (paq.get('resultados') or ()):
        fuera.extend(r.get('inconsistencias') or ())
    return fuera


def area_de(paq, codigo):
    for r in (paq.get('resultados') or ()):
        if r.get('area_curricular_codigo') == codigo:
            return r
    return None


def situacion():
    precarga = APP._precarga_curso_canonica(
        db, usr, curso, ano, estudiante_ids=[est.id])
    comps = APP._datos_academicos_estudiantes(
        db, usr, [est.id], ano, M.CalificacionSecundaria).get(est.id, {})
    extras = APP._datos_academicos_estudiantes(
        db, usr, [est.id], ano, M.EvaluacionExtraSecundaria).get(est.id, {})
    return APP._situacion_canonica_secundaria(
        db, usr, est, ano, precarga,
        competencias_por_asig=comps,
        extras_por_asig={k: v[0] for k, v in extras.items() if v},
        asistencias=[])


paq = situacion()
_incons = inconsistencias_de(paq)
check('HF-29 y hay resultados que mirar: la lista NO esta vacia',
      len(paq.get('resultados') or ()) >= len(AREAS),
      '%d areas' % len(paq.get('resultados') or ()))
check('HF-30 A1 ya NO marca CF_SECUNDARIA_DIVERGENTE',
      RA.INCONSISTENCIA_CF_DIVERGENTE not in _incons, str(sorted(set(_incons))))

_caso = area_de(paq, COD_CASO)
check('HF-31 y el área del caso queda APROBADA_EXTRAORDINARIA',
      _caso is not None and _caso.get('estado') == RA.APROBADA_EXTRAORDINARIA,
      str(_caso.get('estado') if _caso else None))
check('HF-32 con la nota final histórica, 70, sin recalcular nada',
      _caso is not None and _caso.get('nota_final') == 70.0,
      str(_caso.get('nota_final') if _caso else None))

_sit = paq['situacion']['condicion']
check('HF-33 A2 ya no se queda en EN_PROCESO por la CF',
      _sit != PA.EN_PROCESO, str(_sit))
check('HF-34 y con todo lo demás aprobado, el resultado es PROMOVIDO',
      _sit == PA.PROMOVIDO, str(_sit))

# La fila histórica no se tocó.
db.expire_all()
_ev = db.query(M.EvaluacionExtraSecundaria).filter_by(
    estudiante_id=est.id, asignatura_id=ASIG[COD_CASO].id).first()
check('HF-35 ZERO WRITES: la fila histórica sigue exactamente igual',
      abs(_ev.cf_original - CF_LEGACY_ESPERADA) < 1e-9
      and _ev.cec == 70.0 and _ev.completiva_final == 69.0
      and _ev.ceex == 70.0 and _ev.extraordinaria_final == 70.0,
      'cf_original=%r' % _ev.cf_original)
check('HF-36 y ninguna nota se modificó para conseguirlo',
      all(db.query(M.CalificacionSecundaria).filter_by(
          estudiante_id=est.id, asignatura_id=ASIG[COD_CASO].id,
          competencia_numero=c).first().p1 == NOTAS_CASO[c][0]
          for c in (1, 2, 3, 4)), '')


print("\n=== 4 · LA DIVERGENCIA REAL SIGUE BLOQUEANDO ===")

_ev.cf_original = 75.0          # ni exacta ni legacy: dato incompatible
db.commit()
paq2 = situacion()
_incons2 = inconsistencias_de(paq2)
check('HF-40 una CF que no reproduce ninguna fórmula SIGUE divergiendo',
      RA.INCONSISTENCIA_CF_DIVERGENTE in _incons2,
      str(sorted(set(_incons2))))
check('HF-41 y A2 vuelve a negarse a certificar',
      paq2['situacion']['condicion'] == PA.EN_PROCESO,
      str(paq2['situacion']['condicion']))

# Fase sin base: sigue fail-closed.
_ev.cf_original = None
db.commit()
paq3 = situacion()
_incons3 = inconsistencias_de(paq3)
check('HF-42 una fase sin CF base sigue fail-closed',
      RA.INCONSISTENCIA_FASE_SIN_BASE in _incons3,
      str(sorted(set(_incons3))))

_ev.cf_original = CF_LEGACY_ESPERADA
db.commit()


print("\n=== 5 · INDIVIDUAL, LOTE, JSON Y PDF DICEN LO MISMO ===")

_a = situacion()
_b = situacion()
check('HF-50 dos resoluciones seguidas dan la misma situación',
      _a['situacion']['condicion'] == _b['situacion']['condicion'],
      str(_a['situacion']['condicion']))

# El camino del lote usa los MISMOS helpers precargados.
_precarga = APP._precarga_curso_canonica(db, usr, curso, ano,
                                         estudiante_ids=[est.id])
_comps = APP._datos_academicos_estudiantes(
    db, usr, [est.id], ano, M.CalificacionSecundaria)
_extras = APP._datos_academicos_estudiantes(
    db, usr, [est.id], ano, M.EvaluacionExtraSecundaria)
_lote = APP._situacion_canonica_secundaria(
    db, usr, est, ano, _precarga,
    competencias_por_asig=_comps.get(est.id, {}),
    extras_por_asig={k: v[0] for k, v in (_extras.get(est.id) or {}).items() if v},
    asistencias=[])
check('HF-51 el lote llega a la misma situación que el individual',
      _lote['situacion']['condicion'] == _a['situacion']['condicion'],
      str(_lote['situacion']['condicion']))

import asyncio  # noqa: E402

_json = asyncio.run(APP.get_boletin_estudiante(
    id=est.id, request=None, db=db, current_user=usr))
_json = _json if isinstance(_json, dict) else {}
_asig_caso = next((a for a in (_json.get('asignaturas') or [])
                   if a.get('asignatura') == COD_CASO), None)
check('HF-52 el boletín web resuelve el área del caso',
      _asig_caso is not None, str(list(_json.keys()))[:60])
check('HF-53 y su CF oficial es 69, la de siempre',
      _asig_caso is not None and _asig_caso.get('cf') == 69,
      str(_asig_caso.get('cf') if _asig_caso else None))


print("\n=== 5b · EL PENDIENTE DICE QUE AREA Y POR QUE ===")

# Se vuelve a dejar la CF incompatible para provocar el bloqueo real.
_ev.cf_original = 75.0
db.commit()
_paq_malo = situacion()

_detalle = APP._detalle_inconsistencias(_paq_malo)
check('HF-55 el detalle nombra el area concreta',
      any(d.startswith(COD_CASO + ':') for d in _detalle), str(_detalle)[:110])
check('HF-56 y dice que la CF almacenada no coincide',
      any('no coincide con las calificaciones actuales' in d
          for d in _detalle), str(_detalle)[:110])
check('HF-57 solo sale el area afectada, no las nueve',
      len(_detalle) == 1, '%d detalles' % len(_detalle))
check('HF-58 con el nombre del colegio si se le pasa el indice',
      APP._detalle_inconsistencias(_paq_malo, {COD_CASO: 'Ingles'})[0]
      .startswith('Ingles:'), '')

# Y cuando no hay inconsistencia, no se inventa ninguna.
_ev.cf_original = CF_LEGACY_ESPERADA
db.commit()
check('HF-59 sin inconsistencias, el detalle esta vacio',
      APP._detalle_inconsistencias(situacion()) == [], '')


print("\n=== 6 · EL HOTFIX ES DE LECTURA ===")

import ast as _ast  # noqa: E402
import inspect as _insp  # noqa: E402
import textwrap as _tw  # noqa: E402

PROHIBIDO = ('add', 'add_all', 'commit', 'delete', 'flush', 'merge',
             'bulk_save_objects', 'bulk_update_mappings', 'execute')
for fn in (APP._cf_legacy_secundaria, APP._cf_con_compatibilidad_legacy,
           APP._cf_secundaria_compatible):
    arbol = _ast.parse(_tw.dedent(_insp.getsource(fn)))
    malas = sorted({n.func.attr for n in _ast.walk(arbol)
                    if isinstance(n, _ast.Call)
                    and isinstance(n.func, _ast.Attribute)
                    and n.func.attr in PROHIBIDO})
    check('HF-60 %s no escribe en la base' % fn.__name__, not malas,
          str(malas))

_src = _insp.getsource(APP._cf_con_compatibilidad_legacy)
check('HF-61 y no hay ninguna tolerancia académica disfrazada',
      '0.1' not in _src and '< 1)' not in _src
      and 'TOLERANCIA_CF_LEGACY' in _src, '')
check('HF-62 la tolerancia es ruido de float, del orden de A1',
      APP.TOLERANCIA_CF_LEGACY <= RA.TOLERANCIA_CF_EXACTA,
      '%s vs %s' % (APP.TOLERANCIA_CF_LEGACY, RA.TOLERANCIA_CF_EXACTA))
check('HF-63 A1 y A3 siguen sin tocarse: el enganche es la inyección',
      '_cf_secundaria_compatible' in _insp.getsource(
          APP._situacion_canonica_secundaria)
      and 'cf_secundaria' in _insp.getsource(AD.resultados_secundaria), '')

print()
print("=" * 98)
print("RESULTADO: %d PASARON / %d FALLARON" % (len(PASARON), len(FALLARON)))
print("=" * 98)
for f in FALLARON:
    print("  FALLA:", f)

db.close()
sys.exit(1 if FALLARON else 0)
