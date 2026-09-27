# -*- coding: utf-8 -*-
"""CIERRE DE ANO CORE-2 — finalizacion funcional, detras del candado de C1.

Que se prueba aqui:

  · que sobre un año CERRADO solo se escribe la fase pendiente, y que sobre
    uno abierto se conserva la correccion de siempre;
  · que un alumno ya movido al año siguiente no puede recibir notas del
    anterior mandando `ano_id` a mano;
  · que el GET de pendientes no muta un año cerrado;
  · que la cohorte de un año son sus pendientes MAS sus ya procesados, sin
    duplicados y sin mezclar las notas de un año con el grado del otro;
  · que 6.o de Secundaria se finaliza UNA vez y no vuelve a ser candidato,
    sin egresar y sin desactivarse;
  · que el cierre administrativo es canonico: rechaza EN_PROCESO, admite
    APLAZADO y no crea historial;
  · que las decisiones humanas se persisten, se auditan y cambian A2;
  · que un error estructural aborta el lote entero sin escribir nada;
  · que reabrir despues de mover se rechaza;
  · que el estado del asistente se deriva de la base y sobrevive a un
    refresco;
  · y que el safety lock de C1 sigue puesto.

Base temporal aislada. Nunca produccion.
"""
import asyncio
import os
import sys

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(BK, "tools"))

from test_utils import aislar_base_de_datos  # noqa: E402

TMP = aislar_base_de_datos('c_core2')

from fastapi import HTTPException  # noqa: E402
from database import engine, SessionLocal  # noqa: E402
from test_utils import verificar_engine_aislado  # noqa: E402

verificar_engine_aislado(engine, TMP)

import models as M  # noqa: E402
import promocion_academica as PA  # noqa: E402
import resultado_academico as RA  # noqa: E402
import resultado_academico_consumidores as AD  # noqa: E402
import app as APP  # noqa: E402

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


def cuerpo(r):
    import json
    return json.loads(bytes(r.body).decode('utf-8'))


db = SessionLocal()

check('CORE2-0  el safety lock de C1 esta puesto al empezar',
      APP.CIERRE_ANO_BLOQUEADO is True, '')


# ═══════════════════ EL COLEGIO ═══════════════════

COL = M.Colegio(nombre='Core2', codigo='CORE2', activo=True)
db.add(COL)
db.flush()

A = M.AnoEscolar(colegio_id=COL.id, nombre='2025-2026', activo=True, cerrado=False)
B = M.AnoEscolar(colegio_id=COL.id, nombre='2026-2027', activo=False, cerrado=False)
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

PROF = M.Usuario(colegio_id=COL.id, nombre='P', username='c2prof',
                 password_hash='x', role='profesor', activo=True,
                 must_change_password=False, token_version=0)
DIR = M.Usuario(colegio_id=COL.id, nombre='D', username='c2dir',
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


def curso(nivel, grado, ano, nombre='A'):
    clave = (nivel, grado, ano.id, nombre)
    if clave in CURSOS:
        return CURSOS[clave]
    c = M.Curso(colegio_id=COL.id, nombre=nombre,
                grado_id=GRADOS[(nivel, grado)].id, ano_escolar_id=ano.id,
                tanda_id=TANDA.id, activo=True)
    db.add(c)
    db.commit()
    CURSOS[clave] = c
    return c


def asignar(c, codigos, ano):
    hay = {x.asignatura_id for x in db.query(M.AsignacionProfesor)
           .filter_by(curso_id=c.id).all()}
    for cod in codigos:
        if ASIG[cod].id in hay:
            continue
        db.add(M.AsignacionProfesor(
            colegio_id=COL.id, profesor_id=PROF.id, curso_id=c.id,
            asignatura_id=ASIG[cod].id, ano_escolar_id=ano.id, activo=True))
    db.commit()


_seq = [0]


def alumno(c=None):
    _seq[0] += 1
    e = M.Estudiante(colegio_id=COL.id, matricula='C2-%04d' % _seq[0],
                     nombre='E%d' % _seq[0], apellido='S',
                     curso_id=c.id if c else None, no_lista=_seq[0],
                     activo=True, condicion='activo')
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


def sembrar_sec(grado, ano, notas=None, extras=None):
    c = curso('secundaria', grado, ano)
    asignar(c, AREAS_SEC, ano)
    est = alumno(c)
    for cod in AREAS_SEC:
        notas_sec(est, cod, (notas or {}).get(cod, 90), ano)
    for cod, campos in (extras or {}).items():
        extra_sec(est, cod, ano, **campos)
    return est


def sembrar_prim(grado, ano, notas=None):
    c = curso('primaria', grado, ano)
    oficiales = list(AD.curriculo_oficial_esperado(RA.NIVEL_PRIMARIA, grado)[0])
    asignar(c, oficiales, ano)
    est = alumno(c)
    for cod in oficiales:
        notas_prim(est, cod, (notas or {}).get(cod, 90), ano)
    return est


def caidas(n):
    notas, extras = {}, {}
    for i in range(n):
        cod = AREAS_SEC[i]
        notas[cod] = 50
        extras[cod] = dict(cf_original=50.0, cec=40.0, completiva_final=55.0,
                           ceex=40.0, extraordinaria_final=60.0)
    return notas, extras


# Cursos del año destino, como los dejaría clonar-cursos.
for n in range(1, 7):
    curso('secundaria', n, B)
    curso('primaria', n, B)

E_PROM = sembrar_sec(3, A)
_n, _x = caidas(1)
E_APLA = sembrar_sec(3, A, notas=_n, extras=_x)
_n, _x = caidas(3)
E_REPR = sembrar_sec(3, A, notas=_n, extras=_x)
E_6SEC = sembrar_sec(6, A)
E_3PRI = sembrar_prim(3, A)      # sin alfabetizacion -> EN_PROCESO


print()
print("=" * 100)
print("BLOQUE 1 — el cierre administrativo es canonico")
print("=" * 100)

# ── EN_PROCESO bloquea ────────────────────────────────────────────
_hist_antes = db.query(M.HistorialAcademico).count()
try:
    APP._cerrar_ano_canonico(db, DIR, A.id, request=Req({}))
    check('CORE2-1  EN_PROCESO bloquea el cierre', False, 'NO rechazo')
except APP.TransicionCierreInvalida as ex:
    check('CORE2-1  EN_PROCESO bloquea el cierre',
          ex.codigo == APP.ERROR_CIERRE_TIENE_EN_PROCESO, ex.codigo)

db.expire_all()
check('CORE2-2  el rechazo no cerro nada',
      db.get(M.AnoEscolar, A.id).cerrado is False
      and db.get(M.AnoEscolar, A.id).activo is True, '')
check('CORE2-3  y NO creo historial prematuro',
      db.query(M.HistorialAcademico).count() == _hist_antes, '')

# ── La decision humana resuelve el EN_PROCESO ─────────────────────
_r = asyncio.run(APP.guardar_decision_academica(
    request=Req({'estudiante_id': E_3PRI.id, 'ano_id': A.id,
                 'alfabetizacion_inicial': True,
                 'observacion': 'Acta del consejo del 30/06'}),
    db=db, current_user=DIR))
check('CORE2-4  Direccion aporta el DATO humano y A2 produce la condicion',
      not hasattr(_r, 'status_code') and _r['condicion_canonica'] == PA.PROMOVIDO,
      _r.get('condicion_canonica') if isinstance(_r, dict) else cuerpo(_r))

_fila = (db.query(M.DecisionAcademicaEstudiante)
         .filter_by(estudiante_id=E_3PRI.id, ano_escolar_id=A.id).first())
check('CORE2-5  la decision quedo persistida y auditada',
      _fila is not None and _fila.alfabetizacion_inicial is True
      and _fila.registrado_por == DIR.id and _fila.fecha_registro is not None,
      'registrado_por=%s' % getattr(_fila, 'registrado_por', None))
check('CORE2-5b con su justificacion',
      (_fila.observacion or '').startswith('Acta'), _fila.observacion)

_aud = (db.query(M.LogAuditoria)
        .filter_by(accion='DECISION_ACADEMICA').count()
        if hasattr(M, 'LogAuditoria') else 1)
check('CORE2-5c y con registro de auditoria', _aud >= 1, 'entradas=%s' % _aud)

# ── Dirección no puede escribir el resultado ──────────────────────
_r = asyncio.run(APP.guardar_decision_academica(
    request=Req({'estudiante_id': E_3PRI.id, 'ano_id': A.id,
                 'condicion': 'PROMOVIDO'}),
    db=db, current_user=DIR))
check('CORE2-6  Direccion NO puede escribir la condicion directamente',
      hasattr(_r, 'status_code') and _r.status_code == 400, '')

# ── Valores fuera del contrato de A2 ──────────────────────────────
_r = asyncio.run(APP.guardar_decision_academica(
    request=Req({'estudiante_id': E_3PRI.id, 'ano_id': A.id,
                 'decision_asistencia': 'LO_QUE_SEA'}),
    db=db, current_user=DIR))
check('CORE2-7  un valor que A2 no reconoce se rechaza',
      hasattr(_r, 'status_code') and _r.status_code == 400
      and cuerpo(_r)['error'] == APP.ERROR_DECISION_FUERA_DE_LUGAR, '')

_r = asyncio.run(APP.guardar_decision_academica(
    request=Req({'estudiante_id': E_PROM.id, 'ano_id': A.id,
                 'alfabetizacion_inicial': True}),
    db=db, current_user=DIR))
check('CORE2-8  la alfabetizacion fuera de 3.o de Primaria se rechaza',
      hasattr(_r, 'status_code') and _r.status_code == 400, '')

# ── APLAZADO no impide cerrar ─────────────────────────────────────
_hist_antes = db.query(M.HistorialAcademico).count()
_ano_cerrado, _vista = APP._cerrar_ano_canonico(db, DIR, A.id, request=Req({}))
db.expire_all()
check('CORE2-9  con APLAZADOS pero sin EN_PROCESO, el año SI cierra',
      db.get(M.AnoEscolar, A.id).cerrado is True
      and db.get(M.AnoEscolar, A.id).activo is False,
      'aplazados=%d' % _vista['totales']['aplazados'])
check('CORE2-10 cerrar NO crea historial academico',
      db.query(M.HistorialAcademico).count() == _hist_antes, '')
check('CORE2-11 cerrar NO movio a nadie',
      db.get(M.Estudiante, E_PROM.id).curso.ano_escolar_id == A.id, '')
check('CORE2-12 cerrar NO creo el año siguiente',
      db.query(M.AnoEscolar).filter_by(colegio_id=COL.id).count() == 2, '')

try:
    APP._cerrar_ano_canonico(db, DIR, A.id, request=Req({}))
    check('CORE2-13 cerrar dos veces se rechaza', False, 'NO rechazo')
except APP.TransicionCierreInvalida as ex:
    check('CORE2-13 cerrar dos veces se rechaza',
          ex.codigo == APP.ERROR_ANO_YA_CERRADO, ex.codigo)


print()
print("=" * 100)
print("BLOQUE 2 — recuperacion sobre año cerrado: solo la fase pendiente")
print("=" * 100)

B.activo = True
db.commit()

_cod = AREAS_SEC[0]
_ev = (db.query(M.EvaluacionExtraSecundaria)
       .filter_by(estudiante_id=E_APLA.id, asignatura_id=ASIG[_cod].id).first())
check('CORE2-14 el APLAZADO tiene la Especial pendiente en el año cerrado',
      _ev.fase_pendiente() == 'especial' and _ev.ano_escolar_id == A.id, '')

# Intentar CORREGIR una fase ya resuelta sobre un año cerrado.
_r = asyncio.run(APP.save_evaluacion_extra(
    request=Req({'estudiante_id': E_APLA.id, 'asignatura_id': ASIG[_cod].id,
                 'tipo': 'completiva', 'nota': 30}),
    db=db, current_user=PROF))
check('CORE2-15 año cerrado: NO se puede corregir una fase ya resuelta',
      hasattr(_r, 'status_code') and _r.status_code == 409
      and cuerpo(_r)['error'] == APP.ERROR_RECUPERACION_ANO_CERRADO,
      cuerpo(_r).get('error') if hasattr(_r, 'body') else '')
db.expire_all()
check('CORE2-16 y la nota anterior quedo intacta',
      db.get(M.EvaluacionExtraSecundaria, _ev.id).cec == 40.0, '')

# La fase pendiente SI se puede cargar.
_r = asyncio.run(APP.save_evaluacion_extra(
    request=Req({'estudiante_id': E_APLA.id, 'asignatura_id': ASIG[_cod].id,
                 'tipo': 'especial', 'nota': 25}),
    db=db, current_user=PROF))
db.expire_all()
_ev2 = db.get(M.EvaluacionExtraSecundaria, _ev.id)
check('CORE2-17 la fase PENDIENTE si se carga, con el año cerrado',
      not hasattr(_r, 'status_code') and _ev2.ce == 25,
      'ce=%s' % _ev2.ce)

# Y ya no queda fase pendiente: no se puede escribir mas.
_r = asyncio.run(APP.save_evaluacion_extra(
    request=Req({'estudiante_id': E_APLA.id, 'asignatura_id': ASIG[_cod].id,
                 'tipo': 'especial', 'nota': 40}),
    db=db, current_user=PROF))
check('CORE2-18 terminado el proceso, el año cerrado no admite mas escritura',
      hasattr(_r, 'status_code') and _r.status_code == 409
      and cuerpo(_r)['error'] == APP.ERROR_RECUPERACION_ANO_CERRADO,
      '%s %s' % (getattr(_r, 'status_code', None),
                 (cuerpo(_r) if hasattr(_r, 'body') else _r)))
db.expire_all()
check('CORE2-19 y la Especial conserva su valor',
      db.get(M.EvaluacionExtraSecundaria, _ev.id).ce == 25, '')

# En un año ABIERTO se conserva la correccion de siempre.
_ab = sembrar_sec(4, B, notas={AREAS_SEC[0]: 50},
                  extras={AREAS_SEC[0]: dict(cf_original=50.0)})
_r1 = asyncio.run(APP.save_evaluacion_extra(
    request=Req({'estudiante_id': _ab.id, 'asignatura_id': ASIG[AREAS_SEC[0]].id,
                 'tipo': 'completiva', 'nota': 10}),
    db=db, current_user=PROF))
_r2 = asyncio.run(APP.save_evaluacion_extra(
    request=Req({'estudiante_id': _ab.id, 'asignatura_id': ASIG[AREAS_SEC[0]].id,
                 'tipo': 'completiva', 'nota': 15}),
    db=db, current_user=PROF))
check('CORE2-20 año ABIERTO: la correccion legitima se conserva',
      not hasattr(_r1, 'status_code') and not hasattr(_r2, 'status_code'),
      'r1=%s r2=%s' % (type(_r1).__name__, type(_r2).__name__))


print()
print("=" * 100)
print("BLOQUE 3 — cohorte: pendientes + procesados, sin mezclar años")
print("=" * 100)

_vista = APP._vista_cohorte_ano(db, DIR, A)
_por_id = {f.get('estudiante_id'): f for f in _vista['filas']}
check('CORE2-21 el APLAZADO que aprobo la Especial ahora es PROMOVIDO',
      _por_id[E_APLA.id]['condicion'] == 'promovido',
      _por_id[E_APLA.id]['condicion'])

_plan, _res = APP._cierre_canonico(db, DIR, A.id, B.id, request=Req({}))
db.expire_all()
check('CORE2-22 la transicion movio a los definitivos',
      _res['movidos'] > 0, 'movidos=%d' % _res['movidos'])

_prom = db.get(M.Estudiante, E_PROM.id)
check('CORE2-23 el promovido esta en un curso del año destino',
      _prom.curso.ano_escolar_id == B.id, _prom.curso.nombre_completo)

# EL DEFECTO DE C0.1 §4: la preview de A no puede usar el grado de B.
_vista2 = APP._vista_cohorte_ano(db, DIR, A)
_p2 = {f.get('estudiante_id'): f for f in _vista2['filas']}
check('CORE2-24 tras mover, el promovido SIGUE en la cohorte de A',
      E_PROM.id in _p2, 'ids=%s' % sorted(_p2))
check('CORE2-25 y se lee del HISTORIAL, no se recalcula',
      _p2[E_PROM.id]['origen_del_dato'] == 'historial'
      and _p2[E_PROM.id]['procesado'] is True, '')
check('CORE2-26 con el grado de ORIGEN, no el de destino',
      _p2[E_PROM.id]['grado'] == '3ro Secundaria',
      _p2[E_PROM.id]['grado'])
check('CORE2-27 su condicion sigue siendo la que se decidio en A',
      _p2[E_PROM.id]['condicion'] == 'promovido',
      _p2[E_PROM.id]['condicion'])
check('CORE2-28 una sola fila por estudiante: sin duplicados',
      len(_vista2['filas']) == len({f.get('estudiante_id')
                                    for f in _vista2['filas']}),
      'filas=%d unicos=%d' % (len(_vista2['filas']),
                              len({f.get('estudiante_id') for f in _vista2['filas']})))

_resumen = asyncio.run(APP.get_resumen_cierre_ano(
    ano_id=A.id, db=db, current_user=DIR))
check('CORE2-29 el resumen cuenta la MISMA cohorte',
      _resumen['totales']['estudiantes'] == len(_vista2['filas']),
      'resumen=%d vista=%d' % (_resumen['totales']['estudiantes'],
                               len(_vista2['filas'])))
check('CORE2-30 los promovidos NO desaparecen del resumen tras moverse',
      _resumen['totales']['promovidos'] >= 1,
      str(_resumen['totales']))


print()
print("=" * 100)
print("BLOQUE 4 — 6.o de Secundaria: finaliza UNA vez")
print("=" * 100)

_h6 = db.query(M.HistorialAcademico).filter_by(
    estudiante_id=E_6SEC.id, ano_escolar_id=A.id).all()
check('CORE2-31 6.o Secundaria tiene historial definitivo, una sola fila',
      len(_h6) == 1 and _h6[0].condicion == PA.PROMOVIDO,
      'filas=%d condicion=%s' % (len(_h6), _h6[0].condicion if _h6 else None))

_e6 = db.get(M.Estudiante, E_6SEC.id)
check('CORE2-32 NO egresa, NO se desactiva, NO cambia de grado',
      _e6.activo is True and _e6.condicion != 'egresado'
      and _e6.curso.ano_escolar_id == A.id,
      'activo=%s condicion=%s' % (_e6.activo, _e6.condicion))

_cands, _diag = APP._candidatos_pendientes_del_ano_origen(db, DIR, A)
check('CORE2-33 y YA NO vuelve a ser candidato en el reintento',
      E_6SEC.id not in [e.id for e in _cands],
      'candidatos=%s' % [e.id for e in _cands])
check('CORE2-33b se distingue del APLAZADO, que tambien sigue en A',
      E_6SEC.id in _diag['ya_finalizados'], str(_diag['ya_finalizados']))

_plan_r, _res_r = APP._cierre_canonico(db, DIR, A.id, B.id, request=Req({}))
check('CORE2-34 el reintento no vuelve a finalizarlo',
      db.query(M.HistorialAcademico).filter_by(
          estudiante_id=E_6SEC.id, ano_escolar_id=A.id).count() == 1, '')
check('CORE2-35 ni mueve a nadie mas',
      _res_r['movidos'] == 0, 'movidos=%d' % _res_r['movidos'])


print()
print("=" * 100)
print("BLOQUE 5 — alumno ya movido: no recibe notas del año anterior")
print("=" * 100)

_ev_prom = (db.query(M.EvaluacionExtraSecundaria)
            .filter_by(estudiante_id=E_PROM.id).first())
if _ev_prom is None:
    _ev_prom = extra_sec(E_PROM, AREAS_SEC[1], A, cf_original=50.0)
_r = asyncio.run(APP.save_evaluacion_extra(
    request=Req({'estudiante_id': E_PROM.id,
                 'asignatura_id': _ev_prom.asignatura_id,
                 'tipo': 'completiva', 'nota': 30, 'ano_id': A.id}),
    db=db, current_user=PROF))
check('CORE2-36 un alumno ya movido a B no recibe notas de A',
      hasattr(_r, 'status_code') and _r.status_code == 409
      and cuerpo(_r)['error'] == APP.ERROR_RECUPERACION_CURSO_DE_OTRO_ANO,
      cuerpo(_r).get('error') if hasattr(_r, 'body') else type(_r).__name__)
check('CORE2-37 y el rechazo no dice nada del otro año',
      '2026-2027' not in str(cuerpo(_r)) if hasattr(_r, 'body') else True, '')


print()
print("=" * 100)
print("BLOQUE 6 — error estructural: cero escrituras en el lote")
print("=" * 100)

# Un alumno definitivo de 1.o Primaria sin curso destino en B.
_p1 = sembrar_prim(1, A)
_curso_b1 = db.query(M.Curso).filter_by(
    colegio_id=COL.id, ano_escolar_id=B.id,
    grado_id=GRADOS[('primaria', 2)].id).first()
_curso_b1.activo = False
db.commit()

_estado_antes = sorted(
    (e.id, e.curso_id) for e in db.query(M.Estudiante)
    .filter_by(colegio_id=COL.id).all())
_hist_antes = db.query(M.HistorialAcademico).count()

try:
    APP._cierre_canonico(db, DIR, A.id, B.id, request=Req({}))
    check('CORE2-38 un destino roto aborta el lote', False, 'NO aborto')
except APP.TransicionCierreInvalida as ex:
    check('CORE2-38 un destino roto aborta el lote',
          ex.codigo == APP.ERROR_CIERRE_ESTRUCTURA_ROTA, ex.codigo)

db.expire_all()
check('CORE2-39 y NO movio a nadie: cero escrituras',
      sorted((e.id, e.curso_id) for e in db.query(M.Estudiante)
             .filter_by(colegio_id=COL.id).all()) == _estado_antes, '')
check('CORE2-40 ni creo historial',
      db.query(M.HistorialAcademico).count() == _hist_antes, '')

_curso_b1.activo = True
db.commit()
_plan_ok, _res_ok = APP._cierre_canonico(db, DIR, A.id, B.id, request=Req({}))
check('CORE2-41 arreglada la estructura, el reintento si procesa',
      _res_ok['movidos'] >= 1, 'movidos=%d' % _res_ok['movidos'])


print()
print("=" * 100)
print("BLOQUE 7 — reapertura y estado del asistente")
print("=" * 100)

_r = asyncio.run(APP.reabrir_ano_escolar(
    id=A.id, request=Req({}), db=db, current_user=DIR))
check('CORE2-42 reabrir despues de mover se RECHAZA',
      hasattr(_r, 'status_code') and _r.status_code == 409
      and cuerpo(_r)['error'] == APP.ERROR_ANO_CON_CIERRE_EJECUTADO,
      cuerpo(_r).get('error') if hasattr(_r, 'body') else type(_r).__name__)
db.expire_all()
check('CORE2-43 y el año sigue cerrado',
      db.get(M.AnoEscolar, A.id).cerrado is True, '')

# Un colegio limpio: reabrir antes de mover SI se permite.
COL2 = M.Colegio(nombre='Limpio', codigo='CORE2B', activo=True)
db.add(COL2)
db.flush()
A2_ = M.AnoEscolar(colegio_id=COL2.id, nombre='2025-2026', activo=False, cerrado=True)
db.add(A2_)
db.flush()
DIR2 = M.Usuario(colegio_id=COL2.id, nombre='D', username='c2dir2',
                 password_hash='x', role='direccion', activo=True,
                 must_change_password=False, token_version=0)
db.add(DIR2)
db.commit()
_r = asyncio.run(APP.reabrir_ano_escolar(
    id=A2_.id, request=Req({}), db=db, current_user=DIR2))
db.expire_all()
check('CORE2-44 reabrir ANTES de mover sigue permitido',
      not hasattr(_r, 'status_code')
      and db.get(M.AnoEscolar, A2_.id).cerrado is False, '')

_estado = asyncio.run(APP.get_estado_cierre_ano(db=db, current_user=DIR))
# CORE-2.1 cambio este contrato a proposito. En este punto de la suite la
# transicion A->B ya termino: todos los definitivos se movieron y 6.o de
# Secundaria quedo finalizado, asi que A no tiene a nadie pendiente. Antes
# el estado seguia etiquetando a A como origen para siempre, porque caia en
# «el ultimo cerrado» por id. Una transicion existe solo si hay evidencia de
# ella, y aqui ya no la hay.
check('CORE2-45 el estado se deriva de la base, no del navegador',
      isinstance(_estado, dict) and 'ano_origen' in _estado
      and _estado['ano_activo_id'] == B.id,
      'origen=%s destino=%s activo=%s' % (
          (_estado['ano_origen'] or {}).get('nombre'),
          (_estado['ano_destino'] or {}).get('nombre'),
          _estado['ano_activo_id']))
check('CORE2-46 terminada la transicion, NO queda ninguna en progreso',
      _estado['transicion_en_progreso'] is False
      and _estado['ano_origen'] is None,
      'en_progreso=%s origen=%s' % (_estado['transicion_en_progreso'],
                                    _estado['ano_origen']))
check('CORE2-46b pero A sigue teniendo su transicion EJECUTADA registrada',
      APP._transicion_ejecutada(db, DIR, db.get(M.AnoEscolar, A.id))[0] is True,
      '')
check('CORE2-47 y NO propone cerrar un año ya cerrado',
      _estado['puede_cerrar'] is False, '')
check('CORE2-48 nunca presenta B como el año a cerrar',
      (_estado['ano_origen'] or {}).get('id') != B.id,
      (_estado['ano_origen'] or {}).get('nombre'))
check('CORE2-48b ni vuelve a ofrecer una promocion ya hecha',
      _estado['puede_promover'] is False, '')
check('CORE2-49 informa el safety lock',
      _estado['bloqueado_por_safety_lock'] is True, '')


print()
print("=" * 100)
print("BLOQUE 8 — historial duplicado: fail-closed, sin borrar nada")
print("=" * 100)

_dup = M.HistorialAcademico(
    colegio_id=COL.id, estudiante_id=E_PROM.id, ano_escolar_id=A.id,
    condicion=PA.REPROBADO)
db.add(_dup)
db.commit()

_vista_dup = APP._vista_cohorte_ano(db, DIR, A)
# CORE-2.1: son DOS filas CANONICAS (PROMOVIDO + REPROBADO), o sea una
# ambiguedad academica real. La clave paso a llamarse `historiales_ambiguos`
# para distinguirla de los duplicados meramente legacy, que no bloquean.
check('CORE2-50 la cohorte declara la ambiguedad canonica',
      E_PROM.id in _vista_dup['historiales_ambiguos']
      and _vista_dup['fiable'] is False,
      str(_vista_dup['historiales_ambiguos']))
_filas_dup = [f for f in _vista_dup['filas']
              if f.get('estudiante_id') == E_PROM.id]
check('CORE2-51 y NO elige una de las dos en silencio',
      len(_filas_dup) <= 1
      and not any(f.get('origen_del_dato') == 'historial' for f in _filas_dup),
      'filas=%d' % len(_filas_dup))

try:
    APP._cierre_canonico(db, DIR, A.id, B.id, request=Req({}))
    check('CORE2-52 con duplicados, la transicion se detiene', False, 'NO aborto')
except APP.TransicionCierreInvalida as ex:
    check('CORE2-52 con duplicados, la transicion se detiene',
          ex.codigo == APP.ERROR_CIERRE_ESTRUCTURA_ROTA, ex.codigo)

check('CORE2-53 y no se borro ninguno de los dos historiales',
      db.query(M.HistorialAcademico).filter_by(
          estudiante_id=E_PROM.id, ano_escolar_id=A.id).count() == 2, '')
db.delete(_dup)
db.commit()


print()
print("=" * 100)
print("BLOQUE 9 — el safety lock de C1 sigue puesto")
print("=" * 100)

from fastapi.testclient import TestClient  # noqa: E402
from auth import create_token  # noqa: E402

TOK = create_token(DIR)
with TestClient(APP.app) as cli:
    for etiqueta, ruta, body, codigo in [
        ('cierre-ano/promover', '/api/cierre-ano/promover',
         {'ano_origen_id': A.id, 'ano_destino_id': B.id},
         'CIERRE_ANO_TEMPORALMENTE_BLOQUEADO'),
        ('ano-escolar/{id}/cerrar', '/api/ano-escolar/%d/cerrar' % B.id, {},
         'CIERRE_ANO_TEMPORALMENTE_BLOQUEADO'),
        ('promocion/ejecutar', '/api/promocion/ejecutar',
         {'estudiantes': [E_PROM.id]}, 'PROMOCION_LEGACY_BLOQUEADA'),
        ('ano-escolar/promover', '/api/ano-escolar/promover', {},
         'PROMOCION_LEGACY_BLOQUEADA'),
    ]:
        r = cli.post(ruta, json=body,
                     headers={'Authorization': 'Bearer %s' % TOK})
        check('CORE2-54 %s sigue en 409' % etiqueta,
              r.status_code == 409 and r.json().get('error') == codigo,
              'status=%s error=%s' % (r.status_code, r.json().get('error')))

check('CORE2-55 la bandera sigue en True al terminar',
      APP.CIERRE_ANO_BLOQUEADO is True, '')


print()
print("=" * 100)
print("RESULTADO: %d PASARON / %d FALLARON" % (len(PASARON), len(FALLARON)))
print("=" * 100)
for f in FALLARON:
    print("  FALLA:", f)

db.close()
sys.exit(1 if FALLARON else 0)
