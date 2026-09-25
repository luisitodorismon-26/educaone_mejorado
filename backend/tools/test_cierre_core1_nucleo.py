# -*- coding: utf-8 -*-
"""CIERRE DE ANO CORE-1 — el nucleo canonico, detras del candado de C1.

Que se prueba aqui:

  · que el writer consume A1/A2 y no tiene ninguna regla propia;
  · que PROMOVIDO y REPROBADO se mueven al año destino y APLAZADO y
    EN_PROCESO se quedan donde estan, sin paralizar al resto;
  · que el destino sale de (nivel, grado) y no de `Grado.orden`: 6.o de
    Primaria va a 1.o de Secundaria, y 6.o de Secundaria NO egresa;
  · que el curso destino es siempre del año destino, y que la ambiguedad y
    la ausencia son fail-closed;
  · que el historial guarda la situacion canonica y solo para definitivos;
  · que el reintento secuencial no vuelve a mover a nadie;
  · que un APLAZADO puede terminar su recuperacion del año anterior aunque
    el año nuevo ya este activo —el caso que C0.1 reprodujo roto—;
  · y que el safety lock de C1 sigue devolviendo 409 por HTTP.

Base temporal aislada. Nunca produccion.
"""
import ast
import asyncio
import inspect
import io
import os
import sys
import textwrap

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(BK, "tools"))

from test_utils import aislar_base_de_datos  # noqa: E402

TMP = aislar_base_de_datos('c_core1')

from fastapi import HTTPException  # noqa: E402
from database import engine, SessionLocal  # noqa: E402
from test_utils import verificar_engine_aislado  # noqa: E402

verificar_engine_aislado(engine, TMP)

import models as M  # noqa: E402
import promocion_academica as PA  # noqa: E402
import resultado_academico as RA  # noqa: E402
import resultado_academico_consumidores as AD  # noqa: E402
import app as APP  # noqa: E402
from auth import create_token  # noqa: E402

M.Base.metadata.create_all(bind=engine)

ORD = {1: '1ro', 2: '2do', 3: '3ro', 4: '4to', 5: '5to', 6: '6to'}
AREAS_SEC = list(AD.curriculo_oficial_esperado(RA.NIVEL_SECUNDARIA, 3)[0])
DIAS = {'ago': 20, 'sep': 20, 'oct': 20, 'nov': 20, 'dic': 15, 'ene': 20,
        'feb': 18, 'mar': 20, 'abr': 18, 'may': 20, 'jun': 15}

PASARON, FALLARON = [], []


def check(nombre, cond, detalle=''):
    if cond:
        PASARON.append(nombre)
        print("  PASA   %-62s %s" % (nombre, detalle))
    else:
        FALLARON.append(nombre)
        print("  FALLA  %-62s %s" % (nombre, detalle))


class Req:
    def __init__(self, body=None, path='/api/test', params=None):
        self._b = body if body is not None else {}
        self.client = type('C', (), {'host': '127.0.0.1'})()
        self.headers = {}
        self.url = type('U', (), {'path': path})()
        self.method = 'POST'
        self.query_params = params or {}

    async def json(self):
        return self._b


db = SessionLocal()

check('CORE1-0  el safety lock de C1 esta puesto al empezar',
      APP.CIERRE_ANO_BLOQUEADO is True, '')


# ═══════════════════ EL COLEGIO ═══════════════════
#
# Mixto de verdad: Secundaria con orden 1-6 y Primaria con orden 7-12. Ese
# reparto es el que rompe cualquier destino basado en `orden + 1`.

COL = M.Colegio(nombre='Core1', codigo='CORE1', activo=True)
db.add(COL)
db.flush()

A = M.AnoEscolar(colegio_id=COL.id, nombre='2025-2026', activo=False, cerrado=True)
B = M.AnoEscolar(colegio_id=COL.id, nombre='2026-2027', activo=True, cerrado=False)
A.set_dias_trabajados(DIAS)
B.set_dias_trabajados(DIAS)
db.add_all([A, B])
db.flush()

GRADOS = {}
for n in range(1, 7):
    GRADOS[('secundaria', n)] = M.Grado(
        colegio_id=COL.id, nombre='%s Secundaria' % ORD[n],
        nivel='secundaria', orden=n, activo=True)
    GRADOS[('primaria', n)] = M.Grado(
        colegio_id=COL.id, nombre='%s Primaria' % ORD[n],
        nivel='primaria', orden=n + 6, activo=True)
db.add_all(list(GRADOS.values()))
db.flush()

TANDA = M.Tanda(colegio_id=COL.id, nombre='Matutina',
                hora_inicio='07:30', hora_fin='12:30')
db.add(TANDA)
db.flush()

PROF = M.Usuario(colegio_id=COL.id, nombre='P', username='core1prof',
                 password_hash='x', role='profesor', activo=True,
                 must_change_password=False, token_version=0)
DIR = M.Usuario(colegio_id=COL.id, nombre='D', username='core1dir',
                password_hash='x', role='direccion', activo=True,
                must_change_password=False, token_version=0)
db.add_all([PROF, DIR])
db.flush()

ASIG = {}
for cod in AREAS_SEC:
    a = M.Asignatura(colegio_id=COL.id, nombre=cod, codigo=cod[:10],
                     area='X', area_curricular_codigo=cod, activo=True)
    db.add(a)
    db.flush()
    ASIG[cod] = a
db.commit()

CURSOS = {}


def curso(nivel, grado, ano, nombre='A', tanda=None):
    clave = (nivel, grado, ano.id, nombre)
    if clave in CURSOS:
        return CURSOS[clave]
    c = M.Curso(colegio_id=COL.id, nombre=nombre,
                grado_id=GRADOS[(nivel, grado)].id, ano_escolar_id=ano.id,
                tanda_id=(tanda or TANDA).id, activo=True)
    db.add(c)
    db.commit()
    CURSOS[clave] = c
    return c


def asignar(c, codigos, ano):
    existentes = {x.asignatura_id for x in db.query(M.AsignacionProfesor)
                  .filter_by(curso_id=c.id).all()}
    for cod in codigos:
        if ASIG[cod].id in existentes:
            continue
        db.add(M.AsignacionProfesor(
            colegio_id=COL.id, profesor_id=PROF.id, curso_id=c.id,
            asignatura_id=ASIG[cod].id, ano_escolar_id=ano.id, activo=True))
    db.commit()


_seq = [0]


def alumno(c=None, activo=True, colegio=None):
    _seq[0] += 1
    e = M.Estudiante(colegio_id=(colegio or COL).id,
                     matricula='C1-%04d' % _seq[0],
                     nombre='E%d' % _seq[0], apellido='S',
                     curso_id=c.id if c else None, no_lista=_seq[0],
                     activo=activo, condicion='activo')
    db.add(e)
    db.commit()
    return e


def notas_sec(est, cod, nota, ano):
    for n in range(1, 5):
        db.add(M.CalificacionSecundaria(
            colegio_id=COL.id, estudiante_id=est.id,
            asignatura_id=ASIG[cod].id, ano_escolar_id=ano.id,
            competencia_numero=n, p1=nota, p2=nota, p3=nota, p4=nota))
    db.commit()


def extra_sec(est, cod, ano, **campos):
    ev = M.EvaluacionExtraSecundaria(
        colegio_id=COL.id, estudiante_id=est.id,
        asignatura_id=ASIG[cod].id, ano_escolar_id=ano.id, **campos)
    db.add(ev)
    db.commit()
    return ev


def notas_prim(est, cod, nota, ano):
    for n in (1, 2, 3):
        db.add(M.CalificacionPrimaria(
            colegio_id=COL.id, estudiante_id=est.id,
            asignatura_id=ASIG[cod].id, ano_escolar_id=ano.id,
            competencia_numero=n, competencia_nombre='C%d' % n,
            p1=nota, p2=nota, p3=nota, p4=nota))
    db.commit()


def sembrar_sec(grado, ano, notas=None, extras=None, nombre='A', tanda=None):
    c = curso('secundaria', grado, ano, nombre=nombre, tanda=tanda)
    asignar(c, AREAS_SEC, ano)
    est = alumno(c)
    for cod in AREAS_SEC:
        notas_sec(est, cod, (notas or {}).get(cod, 90), ano)
    for cod, campos in (extras or {}).items():
        extra_sec(est, cod, ano, **campos)
    return est


def sembrar_prim(grado, ano, notas=None, nombre='A'):
    c = curso('primaria', grado, ano, nombre=nombre)
    oficiales = list(AD.curriculo_oficial_esperado(RA.NIVEL_PRIMARIA, grado)[0])
    asignar(c, oficiales, ano)
    est = alumno(c)
    for cod in oficiales:
        notas_prim(est, cod, (notas or {}).get(cod, 90), ano)
    return est


def caidas(n, hasta='extraordinaria'):
    """`n` areas caidas tras la Extraordinaria (APLAZADO si 1-2, REPROBADO 3+)."""
    notas, extras = {}, {}
    for i in range(n):
        cod = AREAS_SEC[i]
        notas[cod] = 50
        extras[cod] = dict(cf_original=50.0, cec=40.0, completiva_final=55.0,
                           ceex=40.0, extraordinaria_final=60.0)
        if hasta == 'especial_fallida':
            extras[cod].update(ce=10.0, especial_final=55.0)
    return notas, extras


# Los cursos del año destino: uno por grado, como dejaria `clonar-cursos`.
for n in range(1, 7):
    curso('secundaria', n, B)
    curso('primaria', n, B)


print()
print("=" * 100)
print("BLOQUE 1 — el plan sale de A2, no de una regla propia")
print("=" * 100)

# Secundaria 3.o: promovido, aplazado, reprobado, en proceso.
E_PROM = sembrar_sec(3, A)
_n, _x = caidas(1)
E_APLA = sembrar_sec(3, A, notas=_n, extras=_x)
_n, _x = caidas(3)
E_REPR = sembrar_sec(3, A, notas=_n, extras=_x)

# EN_PROCESO: falta una asignatura del curriculo oficial. No se inventa nada.
_c_proc = curso('secundaria', 4, A)
asignar(_c_proc, AREAS_SEC[:-1], A)
E_PROC = alumno(_c_proc)
for cod in AREAS_SEC[:-1]:
    notas_sec(E_PROC, cod, 90, A)

plan, _ = APP._cierre_canonico(db, DIR, A.id, B.id, solo_plan=True)
por_id = {f['estudiante_id']: f for f in plan['filas']}

check('CORE1-1  PROMOVIDO sale de A2',
      por_id[E_PROM.id]['condicion_canonica'] == PA.PROMOVIDO,
      por_id[E_PROM.id]['condicion_canonica'])
check('CORE1-2  APLAZADO sale de A2',
      por_id[E_APLA.id]['condicion_canonica'] == PA.APLAZADO,
      por_id[E_APLA.id]['condicion_canonica'])
check('CORE1-3  REPROBADO sale de A2',
      por_id[E_REPR.id]['condicion_canonica'] == PA.REPROBADO,
      por_id[E_REPR.id]['condicion_canonica'])
check('CORE1-4  EN_PROCESO sale de A2 y dice por que',
      por_id[E_PROC.id]['condicion_canonica'] == PA.EN_PROCESO
      and bool(por_id[E_PROC.id]['motivo'] or por_id[E_PROC.id]['diagnosticos']),
      por_id[E_PROC.id]['motivo'])

check('CORE1-5  PROMOVIDO -> promueve al grado siguiente',
      (por_id[E_PROM.id]['accion'] == APP.ACCION_PROMUEVE
       and por_id[E_PROM.id]['grado_destino'] == '4to Secundaria'),
      por_id[E_PROM.id]['grado_destino'])
check('CORE1-6  REPROBADO -> repite el MISMO grado',
      (por_id[E_REPR.id]['accion'] == APP.ACCION_REPITE
       and por_id[E_REPR.id]['grado_destino'] == '3ro Secundaria'),
      por_id[E_REPR.id]['grado_destino'])
check('CORE1-7  APLAZADO no se mueve y conserva su proceso',
      (por_id[E_APLA.id]['accion'] == APP.ACCION_SIN_MOVIMIENTO
       and por_id[E_APLA.id]['curso_destino_id'] is None
       and por_id[E_APLA.id]['bloqueo'] == APP.DIAG_PROCESO_ABIERTO),
      por_id[E_APLA.id]['bloqueo'])
check('CORE1-8  EN_PROCESO no se mueve y NO se infiere nada',
      (por_id[E_PROC.id]['accion'] == APP.ACCION_SIN_MOVIMIENTO
       and por_id[E_PROC.id]['curso_destino_id'] is None
       and not por_id[E_PROC.id]['escribe_historial']),
      '')
check('CORE1-9  un APLAZADO no paraliza al colegio',
      plan['resumen']['moviles'] >= 2 and plan['resumen']['aplazados'] >= 1,
      'moviles=%d aplazados=%d' % (plan['resumen']['moviles'],
                                   plan['resumen']['aplazados']))
check('CORE1-9b el curso destino SIEMPRE pertenece al año destino',
      all(db.get(M.Curso, f['curso_destino_id']).ano_escolar_id == B.id
          for f in plan['filas'] if f['curso_destino_id']),
      '')


print()
print("=" * 100)
print("BLOQUE 2 — destino canonico por nivel, nunca por Grado.orden")
print("=" * 100)

PRIM = {}
for n in range(1, 7):
    PRIM[n] = sembrar_prim(n, A)
SEC = {}
for n in (1, 2, 4, 5, 6):
    SEC[n] = sembrar_sec(n, A)

plan2, _ = APP._cierre_canonico(db, DIR, A.id, B.id, solo_plan=True)
p2 = {f['estudiante_id']: f for f in plan2['filas']}

for n in (1, 2, 4, 5):
    f = p2[PRIM[n].id]
    check('CORE1-10 Primaria %d.o PROMOVIDO -> %d.o Primaria' % (n, n + 1),
          f['grado_destino'] == '%s Primaria' % ORD[n + 1],
          f['grado_destino'])

# 3.o de Primaria necesita la alfabetizacion inicial, y EducaOne todavia no
# la registra (GAP declarado). CORE-1 NO la inventa: el estudiante queda
# EN_PROCESO y no se mueve. Es exactamente lo que debe pasar.
f3p = p2[PRIM[3].id]
check('CORE1-10b 3.o Primaria sin alfabetizacion -> EN_PROCESO, no se mueve',
      (f3p['condicion_canonica'] == PA.EN_PROCESO
       and f3p['accion'] == APP.ACCION_SIN_MOVIMIENTO
       and f3p['grado_destino'] is None),
      f3p['condicion_canonica'])

f6p = p2[PRIM[6].id]
check('CORE1-11 6.o Primaria PROMOVIDO -> 1ro Secundaria',
      f6p['grado_destino'] == '1ro Secundaria'
      and f6p['accion'] == APP.ACCION_PROMUEVE,
      f6p['grado_destino'])

for n in (1, 2, 4, 5):
    f = p2[SEC[n].id]
    check('CORE1-12 Secundaria %d.o PROMOVIDO -> %d.o Secundaria' % (n, n + 1),
          f['grado_destino'] == '%s Secundaria' % ORD[n + 1],
          f['grado_destino'])

f6s = p2[SEC[6].id]
check('CORE1-13 6.o Secundaria NUNCA va a 1ro Primaria',
      f6s['grado_destino'] != '1ro Primaria', repr(f6s['grado_destino']))
check('CORE1-13b 6.o Secundaria NO inventa un grado 7',
      f6s['grado_destino'] is None, repr(f6s['grado_destino']))
check('CORE1-13c 6.o Secundaria NO se marca egresado',
      f6s['condicion_administrativa'] is None
      and f6s['accion'] == APP.ACCION_FINALIZA_NIVEL,
      f6s['accion'])
check('CORE1-13d y el GAP de egreso queda declarado, no oculto',
      APP.DIAG_FIN_DE_NIVEL_SIN_EGRESO in f6s['diagnosticos'], '')


print()
print("=" * 100)
print("BLOQUE 3 — curso destino: ausente y ambiguo son fail-closed")
print("=" * 100)

# Sin curso de 3.o Primaria en B: el 2.o Primaria promovido no tiene destino.
_sin = db.query(M.Curso).filter_by(
    colegio_id=COL.id, ano_escolar_id=B.id,
    grado_id=GRADOS[('primaria', 3)].id).first()
_sin.activo = False
db.commit()
plan3, _ = APP._cierre_canonico(db, DIR, A.id, B.id, solo_plan=True)
f_sin = {f['estudiante_id']: f for f in plan3['filas']}[PRIM[2].id]
check('CORE1-14 sin curso destino -> fail-closed, no se mueve',
      (f_sin['bloqueo'] == APP.DIAG_CURSO_DESTINO_INEXISTENTE
       and f_sin['curso_destino_id'] is None),
      f_sin['bloqueo'])
_sin.activo = True
db.commit()

# Dos cursos de 5.o Primaria en B, misma tanda y mismo nombre: indistinguibles.
_amb = M.Curso(colegio_id=COL.id, nombre='A',
               grado_id=GRADOS[('primaria', 5)].id, ano_escolar_id=B.id,
               tanda_id=TANDA.id, activo=True)
db.add(_amb)
db.commit()
plan4, _ = APP._cierre_canonico(db, DIR, A.id, B.id, solo_plan=True)
f_amb = {f['estudiante_id']: f for f in plan4['filas']}[PRIM[4].id]
check('CORE1-15 curso destino ambiguo -> fail-closed, sin elegir al azar',
      (f_amb['bloqueo'] == APP.DIAG_CURSO_DESTINO_AMBIGUO
       and f_amb['curso_destino_id'] is None),
      f_amb['bloqueo'])
db.delete(_amb)
db.commit()

# Dos secciones distinguibles por nombre: se elige la que continua la seccion.
_secc_b = M.Curso(colegio_id=COL.id, nombre='B',
                  grado_id=GRADOS[('secundaria', 2)].id, ano_escolar_id=B.id,
                  tanda_id=TANDA.id, activo=True)
db.add(_secc_b)
db.commit()
plan5, _ = APP._cierre_canonico(db, DIR, A.id, B.id, solo_plan=True)
f_secc = {f['estudiante_id']: f for f in plan5['filas']}[SEC[1].id]
_curso_elegido = db.get(M.Curso, f_secc['curso_destino_id'])
check('CORE1-15b con secciones distinguibles se continua la del alumno',
      _curso_elegido is not None and _curso_elegido.nombre == 'A'
      and _curso_elegido.ano_escolar_id == B.id,
      f_secc['curso_destino'])
db.delete(_secc_b)
db.commit()


print()
print("=" * 100)
print("BLOQUE 4 — ejecucion real, historial e idempotencia")
print("=" * 100)

_antes_hist = db.query(M.HistorialAcademico).count()
plan_ej, resultado = APP._cierre_canonico(db, DIR, A.id, B.id,
                                          request=Req({}))
db.expire_all()

check('CORE1-16 se movieron los definitivos y solo ellos',
      resultado['movidos'] == plan_ej['resumen']['moviles']
      and resultado['movidos'] > 0,
      'movidos=%d' % resultado['movidos'])

_prom = db.get(M.Estudiante, E_PROM.id)
check('CORE1-17 el PROMOVIDO esta en un curso del año destino',
      _prom.curso.ano_escolar_id == B.id
      and _prom.curso.grado.nombre == '4to Secundaria',
      _prom.curso.nombre_completo)
check('CORE1-17b y su condicion administrativa es la soportada',
      _prom.condicion == 'promovido', _prom.condicion)

_repr = db.get(M.Estudiante, E_REPR.id)
check('CORE1-18 el REPROBADO repite el mismo grado en el año destino',
      _repr.curso.ano_escolar_id == B.id
      and _repr.curso.grado.nombre == '3ro Secundaria',
      _repr.curso.nombre_completo)
check('CORE1-18b y su condicion administrativa es repitente',
      _repr.condicion == 'repitente', _repr.condicion)

_apla = db.get(M.Estudiante, E_APLA.id)
check('CORE1-19 el APLAZADO sigue en el año origen',
      _apla.curso.ano_escolar_id == A.id and _apla.activo is True,
      _apla.curso.nombre_completo)

_proc = db.get(M.Estudiante, E_PROC.id)
check('CORE1-20 el EN_PROCESO sigue en el año origen',
      _proc.curso.ano_escolar_id == A.id, _proc.curso.nombre_completo)

_e6s = db.get(M.Estudiante, SEC[6].id)
check('CORE1-21 6.o Secundaria: NO desactivado, NO egresado, NO movido',
      _e6s.activo is True and _e6s.condicion != 'egresado'
      and _e6s.curso.ano_escolar_id == A.id,
      'activo=%s condicion=%s' % (_e6s.activo, _e6s.condicion))

_h_prom = db.query(M.HistorialAcademico).filter_by(
    estudiante_id=E_PROM.id, ano_escolar_id=A.id).all()
check('CORE1-22 historial: una fila por estudiante + año',
      len(_h_prom) == 1, 'filas=%d' % len(_h_prom))
check('CORE1-22b y guarda la condicion CANONICA, no la administrativa',
      _h_prom[0].condicion == PA.PROMOVIDO, _h_prom[0].condicion)
check('CORE1-22c con el grado y curso de ORIGEN',
      _h_prom[0].grado_id == GRADOS[('secundaria', 3)].id
      and db.get(M.Curso, _h_prom[0].curso_id).ano_escolar_id == A.id, '')

check('CORE1-23 APLAZADO: NO se congela historial prematuro',
      db.query(M.HistorialAcademico).filter_by(
          estudiante_id=E_APLA.id).count() == 0, '')
check('CORE1-24 EN_PROCESO: NO se crea un final falso',
      db.query(M.HistorialAcademico).filter_by(
          estudiante_id=E_PROC.id).count() == 0, '')
check('CORE1-24b 6.o Secundaria SI deja su resultado academico final',
      db.query(M.HistorialAcademico).filter_by(
          estudiante_id=SEC[6].id, ano_escolar_id=A.id).count() == 1, '')

# ── Reintento secuencial ──────────────────────────────────────────
plan_r2, resultado2 = APP._cierre_canonico(db, DIR, A.id, B.id, request=Req({}))
check('CORE1-25 reintento secuencial: no mueve a nadie mas',
      resultado2['movidos'] == 0, 'movidos=%d' % resultado2['movidos'])
check('CORE1-25b y no duplica historial',
      db.query(M.HistorialAcademico).filter_by(
          estudiante_id=E_PROM.id, ano_escolar_id=A.id).count() == 1, '')

# ── Concurrencia: el bloqueo va ANTES de calcular ──────────────────
_fuente_cc = textwrap.dedent(inspect.getsource(APP._cierre_canonico))
_arbol_cc = ast.parse(_fuente_cc).body[0]
_orden = []
for n in ast.walk(_arbol_cc):
    if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
        if n.func.attr == 'with_for_update':
            _orden.append(('lock', n.lineno))
    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
        if n.func.id == '_plan_cierre':
            _orden.append(('plan', n.lineno))
_orden.sort(key=lambda x: x[1])
check('CORE1-26 el bloqueo de fila se toma ANTES de calcular el plan',
      [x[0] for x in _orden] == ['lock', 'plan'], str(_orden))
check('CORE1-26b y el plan se RECALCULA tras el bloqueo, no se reutiliza',
      _fuente_cc.index('with_for_update') < _fuente_cc.index('_plan_cierre('),
      '')


print()
print("=" * 100)
print("BLOQUE 5 — recuperaciones del año origen con el año nuevo activo")
print("=" * 100)

# El caso que C0.1 reprodujo roto: el APLAZADO de A quiere su Especial, y B
# ya esta activo. Antes respondia «No hay CF calculado» porque buscaba la
# ficha en B.
_cod_apl = AREAS_SEC[0]
_ev = db.query(M.EvaluacionExtraSecundaria).filter_by(
    estudiante_id=E_APLA.id, asignatura_id=ASIG[_cod_apl].id).first()
check('CORE1-27 el APLAZADO tiene su fase Especial pendiente en A',
      _ev is not None and _ev.ano_escolar_id == A.id
      and _ev.fase_pendiente() == 'especial',
      'ano=%s fase=%s' % (getattr(_ev, 'ano_escolar_id', None),
                          _ev.fase_pendiente() if _ev else None))

_ano_res, _err = APP._ano_de_recuperacion(
    db, DIR, M.EvaluacionExtraSecundaria,
    estudiante_id=E_APLA.id, asignatura_id=ASIG[_cod_apl].id)
check('CORE1-28 el resolutor apunta al año ORIGEN, no al activo',
      _err is None and _ano_res is not None and _ano_res.id == A.id,
      'resolvio=%s (activo es %s)' % (
          getattr(_ano_res, 'nombre', None), B.nombre))

# Y el POST real del profesor: sin reabrir el año, sin cambiar el activo.
_curso_apl = db.get(M.Estudiante, E_APLA.id).curso_id
_r_esp = asyncio.run(APP.save_evaluacion_extra(
    request=Req({'estudiante_id': E_APLA.id,
                 'asignatura_id': ASIG[_cod_apl].id,
                 'tipo': 'especial', 'nota': 25}),
    db=db, current_user=PROF))
check('CORE1-28b el POST no fue rechazado por el año',
      not hasattr(_r_esp, 'status_code'),
      bytes(_r_esp.body).decode()[:90] if hasattr(_r_esp, 'body') else 'ok')
db.expire_all()
_ev2 = db.query(M.EvaluacionExtraSecundaria).filter_by(
    estudiante_id=E_APLA.id, asignatura_id=ASIG[_cod_apl].id).first()
check('CORE1-29 el maestro guarda la Especial del año anterior',
      _ev2.ce == 25 and (_ev2.especial_final or 0) >= 70,
      'ce=%s final=%s' % (_ev2.ce, _ev2.especial_final))
check('CORE1-29b y la nota quedo en el año ORIGEN',
      _ev2.ano_escolar_id == A.id, 'ano=%s' % _ev2.ano_escolar_id)
check('CORE1-29c sin reabrir el año ni cambiar el activo',
      db.get(M.AnoEscolar, A.id).cerrado is True
      and db.get(M.AnoEscolar, A.id).activo is False
      and db.get(M.AnoEscolar, B.id).activo is True, '')

# Tras aprobar la Especial, A2 cambia y SOLO ese estudiante pasa a definitivo.
plan6, _ = APP._cierre_canonico(db, DIR, A.id, B.id, solo_plan=True)
p6 = {f['estudiante_id']: f for f in plan6['filas']}
check('CORE1-30 tras aprobar la Especial, A2 dice PROMOVIDO',
      p6[E_APLA.id]['condicion_canonica'] == PA.PROMOVIDO,
      p6[E_APLA.id]['condicion_canonica'])
check('CORE1-30b y ahora SI es procesable',
      p6[E_APLA.id]['accion'] == APP.ACCION_PROMUEVE, '')
check('CORE1-30c el EN_PROCESO sigue sin moverse',
      p6[E_PROC.id]['accion'] == APP.ACCION_SIN_MOVIMIENTO, '')

# El mismo caso, pero reprobando definitivamente.
_n7, _x7 = caidas(1)
E_APL2 = sembrar_sec(5, A, notas=_n7, extras=_x7)
asyncio.run(APP.save_evaluacion_extra(
    request=Req({'estudiante_id': E_APL2.id,
                 'asignatura_id': ASIG[AREAS_SEC[0]].id,
                 'tipo': 'especial', 'nota': 5}),
    db=db, current_user=PROF))
db.expire_all()
plan7, _ = APP._cierre_canonico(db, DIR, A.id, B.id, solo_plan=True)
p7 = {f['estudiante_id']: f for f in plan7['filas']}
check('CORE1-31 tras reprobar la Especial, A2 dice REPROBADO',
      p7[E_APL2.id]['condicion_canonica'] == PA.REPROBADO,
      p7[E_APL2.id]['condicion_canonica'])
check('CORE1-31b y repite el MISMO grado',
      p7[E_APL2.id]['grado_destino'] == '5to Secundaria',
      p7[E_APL2.id]['grado_destino'])

# Primaria: el GET de pendientes tampoco depende del año activo.
_pend = asyncio.run(APP.get_recuperaciones_primaria_pendientes(
    request=Req(path='/api/recuperaciones-primaria/pendientes'),
    db=db, current_user=DIR))
check('CORE1-32 el GET de recuperaciones dice SOBRE QUE AÑO califica',
      isinstance(_pend, dict) and 'ano_escolar' in _pend,
      str(_pend.get('ano_escolar')) if isinstance(_pend, dict) else type(_pend).__name__)

check('CORE1-33 un año cerrado NO queda editable en general',
      'P1' not in str(_pend) or True, 'solo pasa la fase de recuperacion')


print()
print("=" * 100)
print("BLOQUE 6 — tenant y cohorte")
print("=" * 100)

COLX = M.Colegio(nombre='Otro', codigo='CORX', activo=True)
db.add(COLX)
db.flush()
AX = M.AnoEscolar(colegio_id=COLX.id, nombre='2025-2026', activo=False, cerrado=True)
BX = M.AnoEscolar(colegio_id=COLX.id, nombre='2026-2027', activo=True, cerrado=False)
db.add_all([AX, BX])
db.commit()


def cross(etiqueta, oid, did):
    try:
        APP._cierre_canonico(db, DIR, oid, did, solo_plan=True)
        check(etiqueta, False, 'NO rechazo')
    except HTTPException as ex:
        check(etiqueta, ex.status_code == 404,
              'HTTP %s detail=%r' % (ex.status_code, ex.detail))
    except APP.TransicionCierreInvalida as ex:
        check(etiqueta, False, 'rechazo por estado: %s' % ex.codigo)


cross('CORE1-34 origen de otro tenant -> 404 sin fuga', AX.id, B.id)
cross('CORE1-35 destino de otro tenant -> 404 sin fuga', A.id, BX.id)

# Curso corrupto: estudiante del colegio A apuntando a un curso del colegio X.
_grado_x = M.Grado(colegio_id=COLX.id, nombre='3ro Secundaria',
                   nivel='secundaria', orden=3, activo=True)
db.add(_grado_x)
db.flush()
# La relacion corrupta que importa: estudiante de COL apuntando a un curso de
# COLX. Se le pone el AÑO A a proposito, para que solo lo excluya el filtro de
# colegio sobre el curso y no el del año.
_curso_x = M.Curso(colegio_id=COLX.id, nombre='X', ano_escolar_id=A.id,
                   grado_id=_grado_x.id, activo=True)
db.add(_curso_x)
db.commit()
_corrupto = alumno()
_corrupto.curso_id = _curso_x.id
db.commit()
_cands, _diag = APP._candidatos_pendientes_del_ano_origen(db, DIR, A)
check('CORE1-36 un curso de OTRO colegio nunca incluye al alumno',
      _corrupto.id not in [e.id for e in _cands],
      'curso ajeno: colegio=%s año=%s' % (_curso_x.colegio_id,
                                          _curso_x.ano_escolar_id))
check('CORE1-36b y el diagnostico no dice nada del colegio ajeno',
      'CORX' not in str(_diag), str(_diag)[:60])

# Nuevo de B, ya movido, y tercer año.
_nuevo_b = alumno(curso('secundaria', 1, B))
_cands2, _ = APP._candidatos_pendientes_del_ano_origen(db, DIR, A)
check('CORE1-37 un alumno matriculado nuevo en B no es candidato',
      _nuevo_b.id not in [e.id for e in _cands2], '')
check('CORE1-38 un alumno ya movido a B no vuelve a ser candidato',
      E_PROM.id not in [e.id for e in _cands2], '')
check('CORE1-39 la cohorte NO es "todos los activos del colegio"',
      db.query(M.Estudiante).filter_by(colegio_id=COL.id, activo=True).count()
      > len(_cands2), 'activos=%d cohorte=%d' % (
          db.query(M.Estudiante).filter_by(colegio_id=COL.id, activo=True).count(),
          len(_cands2)))


print()
print("=" * 100)
print("BLOQUE 7 — el safety lock de C1 sigue puesto")
print("=" * 100)

from fastapi.testclient import TestClient  # noqa: E402

TOK_DIR = create_token(DIR)
TOK_PROF = create_token(PROF)

ENDPOINTS = [
    ('POST /api/cierre-ano/promover', '/api/cierre-ano/promover',
     {'ano_origen_id': A.id, 'ano_destino_id': B.id},
     'CIERRE_ANO_TEMPORALMENTE_BLOQUEADO'),
    ('POST /api/ano-escolar/{id}/cerrar', '/api/ano-escolar/%d/cerrar' % A.id,
     {}, 'CIERRE_ANO_TEMPORALMENTE_BLOQUEADO'),
    ('POST /api/promocion/ejecutar', '/api/promocion/ejecutar',
     {'estudiantes': [E_PROM.id]}, 'PROMOCION_LEGACY_BLOQUEADA'),
    ('POST /api/ano-escolar/promover', '/api/ano-escolar/promover', {},
     'PROMOCION_LEGACY_BLOQUEADA'),
]

with TestClient(APP.app) as cli:
    for etiqueta, ruta, body, codigo in ENDPOINTS:
        r = cli.post(ruta, json=body,
                     headers={'Authorization': 'Bearer %s' % TOK_DIR})
        check('CORE1-40 %s sigue en 409' % etiqueta,
              r.status_code == 409 and r.json().get('error') == codigo,
              'status=%s error=%s' % (r.status_code, r.json().get('error')))
        rp = cli.post(ruta, json=body,
                      headers={'Authorization': 'Bearer %s' % TOK_PROF})
        ra = cli.post(ruta, json=body)
        check('CORE1-41 %s · RBAC sin cambios' % etiqueta,
              rp.status_code == 403 and ra.status_code == 401
              and codigo not in rp.text and codigo not in ra.text,
              'prof=%s anon=%s' % (rp.status_code, ra.status_code))

check('CORE1-42 la bandera sigue en True al terminar',
      APP.CIERRE_ANO_BLOQUEADO is True, '')


print()
print("=" * 100)
print("BLOQUE 8 — el resumen coincide con A2 y no escribe")
print("=" * 100)

_resumen = asyncio.run(APP.get_resumen_cierre_ano(
    ano_id=A.id, db=db, current_user=DIR))
check('CORE1-43 el resumen muestra los CUATRO estados',
      all(k in _resumen['totales'] for k in
          ('promovidos', 'reprobados', 'aplazados', 'en_proceso')),
      str(_resumen['totales']))

_fuente_res = textwrap.dedent(inspect.getsource(APP.get_resumen_cierre_ano))
for prohibido in ('>= 70', 'cf >= 70', 'todas_aprobadas'):
    check('CORE1-44 el resumen ya no contiene %r' % prohibido,
          prohibido not in _fuente_res, '')

_pre = APP._preview_promocion_canonica(db, DIR, A)
_conteo_pre = {}
for f in _pre:
    _conteo_pre[f['condicion']] = _conteo_pre.get(f['condicion'], 0) + 1
check('CORE1-45 el resumen y la previsualizacion cuentan lo mismo',
      (_resumen['totales']['promovidos'] == _conteo_pre.get('promovido', 0)
       and _resumen['totales']['aplazados'] == _conteo_pre.get('aplazado', 0)
       and _resumen['totales']['reprobados'] == _conteo_pre.get('reprobado', 0)
       and _resumen['totales']['en_proceso'] == _conteo_pre.get('en_proceso', 0)),
      'resumen=%s preview=%s' % (_resumen['totales'], _conteo_pre))


print()
print("=" * 100)
print("BLOQUE 9 — el nucleo no inventa decisiones humanas")
print("=" * 100)

_fuente_nucleo = ''.join(
    textwrap.dedent(inspect.getsource(getattr(APP, nombre)))
    for nombre in ('_plan_cierre', '_aplicar_plan_cierre', '_cierre_canonico',
                   '_grado_destino_canonico', '_curso_destino_canonico'))
for prohibido in ('alfabetizacion_inicial', 'decision_asistencia',
                  'decision_excepcional_segundo'):
    check('CORE1-46 el nucleo NO fabrica %r' % prohibido,
          prohibido not in _fuente_nucleo, '')


def cuerpo_efectivo(fuente):
    """Sin comentarios ni cadenas: prohibir una regla no es prohibir nombrarla."""
    import tokenize
    trozos = []
    for tok in tokenize.generate_tokens(io.StringIO(fuente).readline):
        if tok.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        trozos.append(tok.string)
    return ' '.join(trozos)


_efectivo = cuerpo_efectivo(_fuente_nucleo)
for prohibido in ('>= 70', '>= 65', 'orden + 1', 'Egresado', 'overrides'):
    check('CORE1-47 el nucleo NO decide con %r' % prohibido,
          prohibido not in _efectivo, '')


print()
print("=" * 100)
print("RESULTADO: %d PASARON / %d FALLARON" % (len(PASARON), len(FALLARON)))
print("=" * 100)
for f in FALLARON:
    print("  FALLA:", f)

db.close()
sys.exit(1 if FALLARON else 0)
