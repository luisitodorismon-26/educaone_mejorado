# -*- coding: utf-8 -*-
"""CIERRE DE ANO CORE-2.1 — historial canonico vs legacy, y estado sin adivinar.

Dos defectos que el paquete de evidencia de CORE-2 destapo:

  1. Dos filas de historial LEGACY del mismo estudiante y año —«activo» +
     «activo», que es lo que escribia el writer antiguo copiando
     `Estudiante.condicion`— se trataban como duplicado estructural y
     bloqueaban cerrar, promover y reabrir. Ninguna de las dos afirma un
     resultado academico: no demuestran que el proceso nuevo haya corrido.

  2. El resolutor de estado, cuando ningun año cerrado tenia gente
     pendiente, caia en «el ultimo cerrado» por id. Eso inventaba una
     transicion terminada y etiquetaba a A como origen para siempre.

Aqui se fija el comportamiento correcto de los dos.

Base temporal aislada. Nunca produccion.
"""
import asyncio
import os
import sys

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(BK, "tools"))

from test_utils import aislar_base_de_datos, fechar_ano, asistencia_completa  # noqa: E402

TMP = aislar_base_de_datos('c_core21')

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
        print("  PASA   %-64s %s" % (nombre, detalle))
    else:
        FALLARON.append(nombre)
        print("  FALLA  %-64s %s" % (nombre, detalle))


class Req:
    def __init__(self, body=None):
        self._b = body or {}
        self.client = type('C', (), {'host': '127.0.0.1'})()
        self.headers = {}
        self.url = type('U', (), {'path': '/api/x'})()
        self.method = 'POST'
        self.query_params = {}

    async def json(self):
        return self._b


def cuerpo(r):
    import json
    return json.loads(bytes(r.body).decode('utf-8'))


db = SessionLocal()
_seq = [0]


def montar(codigo, historial=(), cerrado=True, con_destino=False,
           notas_reales=False):
    """Un colegio con UN estudiante y las filas de historial que se pidan.

    `historial` es la lista de `condicion` a insertar para (estudiante, A).
    """
    _seq[0] += 1
    col = M.Colegio(nombre=codigo, codigo=codigo, activo=True)
    db.add(col)
    db.flush()
    A = M.AnoEscolar(colegio_id=col.id, nombre='2025-2026',
                     activo=not cerrado, cerrado=cerrado)
    A.set_dias_trabajados(DIAS)
    fechar_ano(A)   # ASISTENCIA CANÓNICA · días lectivos del año de origen
    db.add(A)
    db.flush()
    B = None
    if con_destino:
        B = M.AnoEscolar(colegio_id=col.id, nombre='2026-2027',
                         activo=True, cerrado=False)
        B.set_dias_trabajados(DIAS)
        db.add(B)
        db.flush()
    g = M.Grado(colegio_id=col.id, nombre='3ro Secundaria',
                nivel='secundaria', orden=3, activo=True)
    g4 = M.Grado(colegio_id=col.id, nombre='4to Secundaria',
                 nivel='secundaria', orden=4, activo=True)
    db.add_all([g, g4])
    db.flush()
    cA = M.Curso(colegio_id=col.id, nombre='A', grado_id=g.id,
                 ano_escolar_id=A.id, activo=True)
    db.add(cA)
    db.flush()
    if B is not None:
        db.add(M.Curso(colegio_id=col.id, nombre='A', grado_id=g4.id,
                       ano_escolar_id=B.id, activo=True))
        db.flush()
    usr = M.Usuario(colegio_id=col.id, username='dir-%s' % codigo,
                    password_hash='x', nombre='D', role='direccion',
                    activo=True, must_change_password=False, token_version=0)
    prof = M.Usuario(colegio_id=col.id, username='prof-%s' % codigo,
                     password_hash='x', nombre='P', role='profesor',
                     activo=True, must_change_password=False, token_version=0)
    db.add_all([usr, prof])
    db.flush()
    est = M.Estudiante(colegio_id=col.id, matricula='%s-1' % codigo,
                       nombre='E', apellido='S', curso_id=cA.id,
                       activo=True, condicion='activo')
    db.add(est)
    db.flush()
    # Lista completa: sin ella A2 no certifica y la suite dejaría de probar
    # el historial para probar la asistencia.
    asistencia_completa(db, M, est, cA.id, col.id, A)
    db.flush()

    if notas_reales:
        # Curriculo completo y aprobado: A2 dira PROMOVIDO.
        for cod in AREAS_SEC:
            asig = M.Asignatura(colegio_id=col.id, nombre=cod, codigo=cod[:10],
                                area='X', area_curricular_codigo=cod,
                                activo=True)
            db.add(asig)
            db.flush()
            db.add(M.AsignacionProfesor(
                colegio_id=col.id, profesor_id=prof.id, curso_id=cA.id,
                asignatura_id=asig.id, ano_escolar_id=A.id, activo=True))
            for n in range(1, 5):
                db.add(M.CalificacionSecundaria(
                    colegio_id=col.id, estudiante_id=est.id,
                    asignatura_id=asig.id, ano_escolar_id=A.id,
                    competencia_numero=n, p1=90, p2=90, p3=90, p4=90))

    for cond in historial:
        db.add(M.HistorialAcademico(
            colegio_id=col.id, estudiante_id=est.id, ano_escolar_id=A.id,
            grado_id=g.id, curso_id=cA.id, condicion=cond))
    db.commit()
    return col, A, B, usr, est


print()
print("=" * 104)
print("BLOQUE 1 — clasificacion: canonico manda, legacy informa")
print("=" * 104)

CASOS = [
    ("solo legacy: activo + activo", ['activo', 'activo'], False, False, True),
    ("solo legacy: Promovido + activo", ['Promovido', 'activo'], False, False, True),
    ("solo legacy: Inscrito + Repitente", ['Inscrito', 'Repitente'], False, False, True),
    ("un canonico + legacy", ['PROMOVIDO', 'activo'], True, False, False),
    ("dos canonicos iguales", ['PROMOVIDO', 'PROMOVIDO'], False, True, False),
    ("dos canonicos distintos", ['PROMOVIDO', 'REPROBADO'], False, True, False),
]

for i, (etiqueta, conds, esp_def, esp_amb, esp_legacy) in enumerate(CASOS):
    col, A, B, usr, est = montar('CL%02d' % i, historial=conds)
    definitivos, ambiguos, legacy = APP._historiales_definitivos_del_ano(
        db, usr, A)
    ok = ((est.id in definitivos) == esp_def
          and (est.id in ambiguos) == esp_amb
          and (est.id in legacy) == esp_legacy)
    check('CORE2.1-C %-32s' % etiqueta, ok,
          'definitivo=%s ambiguo=%s legacy_dup=%s' % (
              est.id in definitivos, est.id in ambiguos, est.id in legacy))


print()
print("=" * 104)
print("BLOQUE 2 — dos filas legacy NO bloquean nada (el caso del evidence pack)")
print("=" * 104)

# ── CORE2.1-1: reapertura ─────────────────────────────────────────
col, A, B, usr, est = montar('LG01', historial=['activo', 'activo'])
ejecutada, motivos = APP._transicion_ejecutada(db, usr, A)
r = asyncio.run(APP.reabrir_ano_escolar(
    id=A.id, request=Req({}), db=db, current_user=usr))
check('CORE2.1-1  dos legacy "activo" -> reapertura PERMITIDA',
      not hasattr(r, 'status_code') and not ejecutada,
      'motivos=%s' % motivos)
db.expire_all()
check('CORE2.1-1b y el año quedo efectivamente reabierto',
      db.get(M.AnoEscolar, A.id).cerrado is False, '')

# ── CORE2.1-2: cierre ─────────────────────────────────────────────
col, A, B, usr, est = montar('LG02', historial=['activo', 'activo'],
                             cerrado=False, notas_reales=True)
try:
    ano_c, vista = APP._cerrar_ano_canonico(db, usr, A.id, request=Req({}))
    db.expire_all()
    check('CORE2.1-2  dos legacy "activo" -> el cierre NO se bloquea',
          db.get(M.AnoEscolar, A.id).cerrado is True,
          'cohorte=%s' % vista['totales'])
except APP.TransicionCierreInvalida as ex:
    check('CORE2.1-2  dos legacy "activo" -> el cierre NO se bloquea',
          False, 'BLOQUEADO con %s' % ex.codigo)

# ── CORE2.1-3: promocion ──────────────────────────────────────────
col, A, B, usr, est = montar('LG03', historial=['activo', 'activo'],
                             con_destino=True, notas_reales=True)
A.activo = False
db.commit()
try:
    plan, resultado = APP._cierre_canonico(db, usr, A.id, B.id,
                                           request=Req({}))
    db.expire_all()
    check('CORE2.1-3  dos legacy "activo" -> la promocion NO se bloquea',
          resultado['movidos'] == 1
          and db.get(M.Estudiante, est.id).curso.ano_escolar_id == B.id,
          'movidos=%d' % resultado['movidos'])
except APP.TransicionCierreInvalida as ex:
    check('CORE2.1-3  dos legacy "activo" -> la promocion NO se bloquea',
          False, 'BLOQUEADO con %s' % ex.codigo)

check('CORE2.1-3b y la fila legacy se ACTUALIZO, no se duplico',
      db.query(M.HistorialAcademico).filter_by(
          estudiante_id=est.id, ano_escolar_id=A.id).count() == 2,
      'filas=%d' % db.query(M.HistorialAcademico).filter_by(
          estudiante_id=est.id, ano_escolar_id=A.id).count())

# ── CORE2.1-4 ─────────────────────────────────────────────────────
col, A, B, usr, est = montar('LG04', historial=['Promovido', 'activo'])
definitivos, ambiguos, legacy = APP._historiales_definitivos_del_ano(db, usr, A)
check('CORE2.1-4  "Promovido" legacy NO es canonico',
      est.id not in definitivos and est.id not in ambiguos,
      'definitivos=%s ambiguos=%s' % (sorted(definitivos), ambiguos))

# ── CORE2.1-5 ─────────────────────────────────────────────────────
col, A, B, usr, est = montar('LG05', historial=['PROMOVIDO', 'activo', 'Inscrito'])
definitivos, ambiguos, legacy = APP._historiales_definitivos_del_ano(db, usr, A)
check('CORE2.1-5  un canonico + legacy -> procesado UNA sola vez',
      est.id in definitivos and not ambiguos
      and definitivos[est.id].condicion == PA.PROMOVIDO,
      'condicion=%s' % definitivos[est.id].condicion)
vista = APP._vista_cohorte_ano(db, usr, A)
filas_est = [f for f in vista['filas'] if f.get('estudiante_id') == est.id]
check('CORE2.1-5b y aparece UNA sola fila en la cohorte',
      len(filas_est) == 1 and filas_est[0]['procesado'] is True
      and filas_est[0]['origen_del_dato'] == 'historial',
      'filas=%d' % len(filas_est))
check('CORE2.1-5c la cohorte sigue siendo FIABLE', vista['fiable'] is True, '')

# ── CORE2.1-6 y 7 ─────────────────────────────────────────────────
for etiqueta, conds in (('dos PROMOVIDO', ['PROMOVIDO', 'PROMOVIDO']),
                        ('PROMOVIDO + REPROBADO', ['PROMOVIDO', 'REPROBADO'])):
    n = 6 if 'dos' in etiqueta else 7
    col, A, B, usr, est = montar('AM%d' % n, historial=conds,
                                 con_destino=True)
    A.activo = False
    db.commit()
    vista = APP._vista_cohorte_ano(db, usr, A)
    bloqueo = None
    try:
        APP._cierre_canonico(db, usr, A.id, B.id, request=Req({}))
    except APP.TransicionCierreInvalida as ex:
        bloqueo = ex.codigo
    check('CORE2.1-%d  %s -> fail-closed' % (n, etiqueta),
          vista['fiable'] is False and est.id in vista['historiales_ambiguos']
          and bloqueo == APP.ERROR_CIERRE_ESTRUCTURA_ROTA,
          'fiable=%s bloqueo=%s' % (vista['fiable'], bloqueo))
    check('CORE2.1-%db y NO se borro ninguna de las dos filas' % n,
          db.query(M.HistorialAcademico).filter_by(
              estudiante_id=est.id, ano_escolar_id=A.id).count() == 2, '')


print()
print("=" * 104)
print("BLOQUE 3 — la preview solo usa historial CANONICO")
print("=" * 104)

# ── CORE2.1-8 ─────────────────────────────────────────────────────
col, A, B, usr, est = montar('PV08', historial=['activo', 'Egresado'],
                             notas_reales=True)
vista = APP._vista_cohorte_ano(db, usr, A)
fila = [f for f in vista['filas'] if f.get('estudiante_id') == est.id][0]
check('CORE2.1-8  con SOLO legacy, el alumno NO se considera procesado',
      fila['procesado'] is False and fila['origen_del_dato'] == 'calculo',
      'procesado=%s origen=%s' % (fila['procesado'], fila['origen_del_dato']))
check('CORE2.1-8b su condicion sale de A2, no del historial legacy',
      fila['condicion'] == 'promovido', fila['condicion'])

# ── CORE2.1-9 ─────────────────────────────────────────────────────
col, A, B, usr, est = montar('PV09', historial=['REPROBADO', 'activo'],
                             notas_reales=True)
vista = APP._vista_cohorte_ano(db, usr, A)
fila = [f for f in vista['filas'] if f.get('estudiante_id') == est.id][0]
check('CORE2.1-9  con un canonico + legacy, la preview usa el CANONICO',
      fila['procesado'] is True
      and fila['condicion_canonica'] == PA.REPROBADO,
      'condicion=%s origen=%s' % (fila['condicion_canonica'],
                                  fila['origen_del_dato']))
check('CORE2.1-9b aunque A2 en vivo diria otra cosa (notas aprobadas)',
      fila['condicion'] == 'reprobado',
      'el historial manda sobre el recalculo')


print()
print("=" * 104)
print("BLOQUE 4 — el estado no adivina la transicion")
print("=" * 104)

# ── CORE2.1-10: transicion TERMINADA ──────────────────────────────
col, A, B, usr, est = montar('ST10', historial=['PROMOVIDO'],
                             con_destino=True)
A.activo = False
est.curso_id = db.query(M.Curso).filter_by(
    colegio_id=col.id, ano_escolar_id=B.id).first().id
db.commit()
estado = asyncio.run(APP.get_estado_cierre_ano(db=db, current_user=usr))
check('CORE2.1-10 transicion terminada -> NO se escoge el ultimo cerrado',
      estado['ano_origen'] is None
      and estado['transicion_en_progreso'] is False,
      'origen=%s en_progreso=%s' % (estado['ano_origen'],
                                    estado['transicion_en_progreso']))
check('CORE2.1-10b y no se ofrece promover',
      estado['puede_promover'] is False, '')
check('CORE2.1-10c el colegio sigue trabajando sobre su año activo',
      estado['ano_activo_id'] == B.id, '')

# ── CORE2.1-11: A cerrado con pendientes, sin B ───────────────────
col, A, B, usr, est = montar('ST11', notas_reales=True)
estado = asyncio.run(APP.get_estado_cierre_ano(db=db, current_user=usr))
check('CORE2.1-11 A cerrado con pendientes y sin B -> origen=A, destino=None',
      (estado['ano_origen'] or {}).get('id') == A.id
      and estado['ano_destino'] is None
      and estado['transicion_en_progreso'] is True,
      'origen=%s destino=%s' % ((estado['ano_origen'] or {}).get('nombre'),
                                estado['ano_destino']))

# ── CORE2.1-12: movimiento parcial ────────────────────────────────
col, A, B, usr, est = montar('ST12', con_destino=True, notas_reales=True)
A.activo = False
db.commit()
otro = M.Estudiante(colegio_id=col.id, matricula='ST12-2', nombre='E2',
                    apellido='S', curso_id=est.curso_id, activo=True,
                    condicion='activo')
db.add(otro)
db.flush()
db.add(M.HistorialAcademico(
    colegio_id=col.id, estudiante_id=otro.id, ano_escolar_id=A.id,
    condicion=PA.PROMOVIDO))
otro.curso_id = db.query(M.Curso).filter_by(
    colegio_id=col.id, ano_escolar_id=B.id).first().id
db.commit()
estado = asyncio.run(APP.get_estado_cierre_ano(db=db, current_user=usr))
check('CORE2.1-12 movimiento parcial -> A->B reconocido, sin memoria React',
      (estado['ano_origen'] or {}).get('id') == A.id
      and (estado['ano_destino'] or {}).get('id') == B.id
      and estado['transicion_en_progreso'] is True,
      'cohorte=%s' % estado['cohorte'])

# ── CORE2.1-13: A terminado, B normal ─────────────────────────────
col, A, B, usr, est = montar('ST13', historial=['PROMOVIDO'],
                             con_destino=True)
A.activo = False
est.curso_id = db.query(M.Curso).filter_by(
    colegio_id=col.id, ano_escolar_id=B.id).first().id
db.commit()
estado = asyncio.run(APP.get_estado_cierre_ano(db=db, current_user=usr))
check('CORE2.1-13 A terminado + B activo -> NO hay transicion pendiente',
      estado['transicion_en_progreso'] is False
      and estado['ano_origen'] is None, '')

# ── CORE2.1-14: dos años cerrados con pendientes ──────────────────
col, A, B, usr, est = montar('ST14', notas_reales=True)
C = M.AnoEscolar(colegio_id=col.id, nombre='2024-2025', activo=False,
                 cerrado=True)
C.set_dias_trabajados(DIAS)
db.add(C)
db.flush()
gC = db.query(M.Grado).filter_by(colegio_id=col.id,
                                 nombre='3ro Secundaria').first()
cC = M.Curso(colegio_id=col.id, nombre='A', grado_id=gC.id,
             ano_escolar_id=C.id, activo=True)
db.add(cC)
db.flush()
est2 = M.Estudiante(colegio_id=col.id, matricula='ST14-2', nombre='E2',
                    apellido='S', curso_id=cC.id, activo=True,
                    condicion='activo')
db.add(est2)
db.commit()
estado = asyncio.run(APP.get_estado_cierre_ano(db=db, current_user=usr))
check('CORE2.1-14 dos años cerrados con pendientes -> ambiguedad fail-closed',
      estado['ano_origen'] is None and len(estado['origen_ambiguo']) == 2,
      'candidatos=%s' % [a['nombre'] for a in estado['origen_ambiguo']])
check('CORE2.1-14b NO se elige el de mayor id',
      estado['puede_promover'] is False and estado['puede_cerrar'] is False,
      '')
check('CORE2.1-14c y se devuelven los dos para que Direccion resuelva',
      {a['id'] for a in estado['origen_ambiguo']} == {A.id, C.id}, '')

# ── CORE2.1-15: 6.o Secundaria finalizado ─────────────────────────
col, A, B, usr, est = montar('ST15', con_destino=True)
g6 = M.Grado(colegio_id=col.id, nombre='6to Secundaria', nivel='secundaria',
             orden=6, activo=True)
db.add(g6)
db.flush()
c6 = M.Curso(colegio_id=col.id, nombre='A', grado_id=g6.id,
             ano_escolar_id=A.id, activo=True)
db.add(c6)
db.flush()
est.curso_id = c6.id
db.add(M.HistorialAcademico(
    colegio_id=col.id, estudiante_id=est.id, ano_escolar_id=A.id,
    grado_id=g6.id, curso_id=c6.id, condicion=PA.PROMOVIDO))
A.activo = False
db.commit()
estado = asyncio.run(APP.get_estado_cierre_ano(db=db, current_user=usr))
check('CORE2.1-15 6.o Sec finalizado NO mantiene la transicion abierta',
      estado['transicion_en_progreso'] is False,
      'origen=%s' % (estado['ano_origen'] or {}).get('nombre'))
db.expire_all()
_e = db.get(M.Estudiante, est.id)
check('CORE2.1-15b y sigue activo, sin egresar, en su curso de A',
      _e.activo is True and _e.condicion != 'egresado'
      and _e.curso.ano_escolar_id == A.id,
      'activo=%s condicion=%s' % (_e.activo, _e.condicion))


print()
print("=" * 104)
print("BLOQUE 5 — los candados, en su estado de release")
print("=" * 104)

check('CORE2.1-16 las banderas estan en su estado de release',
      APP.CIERRE_ANO_BLOQUEADO is False
      and APP.PROMOCION_LEGACY_BLOQUEADA is True, '')


print()
print("=" * 104)
print("RESULTADO: %d PASARON / %d FALLARON" % (len(PASARON), len(FALLARON)))
print("=" * 104)
for f in FALLARON:
    print("  FALLA:", f)

db.close()
sys.exit(1 if FALLARON else 0)
