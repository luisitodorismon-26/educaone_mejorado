# -*- coding: utf-8 -*-
"""TRAS-1 · Pruebas dirigidas a los cinco hallazgos de la auditoría de 7262168.

  R1  reintento con el mismo client_request_id: solo es reintento si el
      CONTENIDO es el mismo; si no, 409 y nada cambia.
  R2  numeración: en un curso con retiros o traslados el Registro no se emite
      comprimido cuando el número más alto no cabe en la plantilla.
  R3  concurrencia (solo PostgreSQL temporal): un traslado y una carga de
      asistencia o de notas del mismo estudiante no se cruzan.
  R4  lote: cada estudiante se autoriza en el curso de SU permanencia; el lote
      de varios cursos sigue funcionando si el docente está autorizado en todos.
  R5  GET /api/asistencia por permanencia.
  R1r primer retiro sin trayectoria: también conserva la solicitud y su huella.
  R2f el endpoint OFICIAL del Registro rechaza la numeración que no cabe.
  R3c (solo PostgreSQL) movimiento frente a un LOTE de asistencia.
  R1s (solo PostgreSQL) dos primeros retiros simultáneos con la misma clave.
  EX  evaluaciones extra de Secundaria frente a traslados y retiros.

Base: SQLite temporal aislada o, con EO_PG_TEST_SERVER, una base PostgreSQL
TEMPORAL propia (tools/pg_base_temporal.py). Datos sintéticos.

Uso (desde backend/):  python tools/test_retiros_traslados_auditoria.py
"""
import datetime as dt
import json
import os
import sys
import threading
import time

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(BK, 'tools'))
from test_utils import aislar_base_de_datos, verificar_engine_aislado  # noqa: E402

if os.environ.get('EO_TEST_PG_URL'):
    raise SystemExit('EO_TEST_PG_URL no se acepta: use EO_PG_TEST_SERVER.')
PG_SERVER = os.environ.get('EO_PG_TEST_SERVER')
if PG_SERVER:
    import pg_base_temporal as PGT
    PG = PGT.BaseTemporal(PG_SERVER, prefijo='eo_tmp_trasaud_')
    os.environ['DATABASE_URL'] = PG.crear()
    TMP = None
else:
    PG = None
    TMP = aislar_base_de_datos('tras_auditoria')
from database import engine, SessionLocal  # noqa: E402
if PG:
    assert engine.dialect.name == 'postgresql' and engine.url.database == PG.nombre, engine.url
    PG.engines.append(engine)
else:
    verificar_engine_aislado(engine, TMP)
print('Motor:', engine.dialect.name)

import models as M  # noqa: E402
import app as APP  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from auth import create_token  # noqa: E402

M.Base.metadata.create_all(bind=engine)
db = SessionLocal()
c = TestClient(APP.app)
RES = []


def check(nombre, ok, detalle=''):
    RES.append((nombre, bool(ok)))
    print(('  PASA  ' if ok else '  FALLA ') + nombre + ('' if ok else '  -> ' + str(detalle)[:500]))


def add(o):
    db.add(o)
    db.flush()
    return o


col = add(M.Colegio(nombre='Colegio Auditoría TRAS', codigo='SAUD', activo=True))
add(M.ConfiguracionColegio(colegio_id=col.id, nombre=col.nombre, regional='10', distrito='10-01', codigo_centro='9'))
ano = add(M.AnoEscolar(colegio_id=col.id, nombre='2026-2027', activo=True, fecha_inicio=dt.date(2026, 9, 1),
                       fecha_fin=dt.date(2027, 6, 30), periodo_activo=1,
                       p1_inicio=dt.date(2026, 9, 1), p1_fin=dt.date(2026, 11, 13),
                       p2_inicio=dt.date(2026, 11, 16), p2_fin=dt.date(2027, 1, 29),
                       p3_inicio=dt.date(2027, 2, 1), p3_fin=dt.date(2027, 4, 16),
                       p4_inicio=dt.date(2027, 4, 19), p4_fin=dt.date(2027, 6, 30)))
g5 = add(M.Grado(colegio_id=col.id, nombre='5to Secundaria', nivel='secundaria', orden=5, activo=True))
g4 = add(M.Grado(colegio_id=col.id, nombre='4to Secundaria', nivel='secundaria', orden=4, activo=True))
tm = add(M.Tanda(colegio_id=col.id, nombre='Matutina', activo=True))
tv = add(M.Tanda(colegio_id=col.id, nombre='Vespertina', activo=True))
V = add(M.Curso(colegio_id=col.id, nombre='A', grado_id=g5.id, tanda_id=tv.id, ano_escolar_id=ano.id, activo=True))
MA = add(M.Curso(colegio_id=col.id, nombre='A', grado_id=g5.id, tanda_id=tm.id, ano_escolar_id=ano.id, activo=True))
C4 = add(M.Curso(colegio_id=col.id, nombre='A', grado_id=g4.id, tanda_id=tm.id, ano_escolar_id=ano.id, activo=True))
art = add(M.Asignatura(colegio_id=col.id, nombre='Educación Artística', codigo='EA', area_curricular_codigo='EA'))


def usuario(u, rol):
    return add(M.Usuario(colegio_id=col.id, username=u, password_hash='x', nombre=u, apellido='Sint', role=rol,
                         activo=True, must_change_password=False, token_version=0))


dire = usuario('dir_aud', 'direccion')
pV, pM, pVM = usuario('p_v', 'profesor'), usuario('p_m', 'profesor'), usuario('p_vm', 'profesor')
for p, cur in ((pV, V), (pM, MA), (pVM, V), (pVM, MA)):
    add(M.AsignacionProfesor(colegio_id=col.id, profesor_id=p.id, curso_id=cur.id, asignatura_id=art.id,
                             ano_escolar_id=ano.id, activo=True))


def estudiante(nombre, curso, n):
    return add(M.Estudiante(colegio_id=col.id, nombre=nombre, apellido='Aud', matricula='AUD-%d-%d' % (curso.id, n),
                            curso_id=curso.id, no_lista=n, activo=True, condicion='activo',
                            fecha_ingreso=dt.date(2026, 8, 20)))


EV = [estudiante('V%d' % n, V, n) for n in range(1, 7)]
EM = [estudiante('M%d' % n, MA, n) for n in range(1, 3)]
EC4 = [estudiante('C4a', C4, 1), estudiante('C4b', C4, 45)]          # huecos SIN movimientos
for e in EV:
    add(M.CalificacionSecundaria(colegio_id=col.id, estudiante_id=e.id, asignatura_id=art.id,
                                 ano_escolar_id=ano.id, competencia_numero=1, p1=80))
    add(M.Asistencia(colegio_id=col.id, estudiante_id=e.id, curso_id=V.id, asignatura_id=art.id,
                     fecha=dt.date(2026, 10, 14), estado='presente', registrado_por=pV.id))
ER = estudiante('V7', V, 7)        # R1r: primer retiro sin trayectoria
EE = estudiante('V8', V, 8)        # R1r: retirado y luego eliminado por error
EL1, EL2 = estudiante('V9', V, 9), estudiante('V10', V, 10)   # R3c
RS1, RS2 = estudiante('V11', V, 11), estudiante('V12', V, 12)  # R1s
EXA, EXB, EXC = estudiante('V13', V, 13), estudiante('V14', V, 14), estudiante('V15', V, 15)  # EX
for _e in (EXA, EXB, EXC):
    add(M.EvaluacionExtraSecundaria(colegio_id=col.id, estudiante_id=_e.id, asignatura_id=art.id,
                                    ano_escolar_id=ano.id, cf_original=60.0)).recalcular_todo()
db.commit()
IDS = {'dire': dire.id, 'pV': pV.id, 'pM': pM.id, 'pVM': pVM.id}
TOK = {k: create_token(u) for k, u in (('dire', dire), ('pV', pV), ('pM', pM), ('pVM', pVM))}


def H(k):
    return {'Authorization': 'Bearer ' + TOK[k]}


def post(url, k, body):
    r = c.post(url, headers=H(k), json=body)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {'_t': r.text[:300]}


def estado_ficha(eid):
    db.expire_all()
    e = db.get(M.Estudiante, eid)
    movs = db.query(M.MovimientoEstudiante).filter_by(estudiante_id=eid).count()
    res = sorted((r.curso_id, r.no_lista) for r in db.query(M.ReservaNumeroLista).filter_by(estudiante_id=eid))
    asis = sorted((a.id, a.curso_id, a.fecha.isoformat(), a.estado) for a in db.query(M.Asistencia).filter_by(estudiante_id=eid))
    return (e.curso_id, e.no_lista, e.activo, movs, res, asis)


# ═════════════ R1. REINTENTOS ═════════════
print('\n== R1. Reintentos comparan el contenido ==')
RIC = EV[2]
cuerpo = {'curso_destino_id': MA.id, 'desde': '2026-10-21', 'motivo': 'Cambio de tanda', 'client_request_id': 'aud-1'}
st, js = post('/api/estudiantes/%d/traslado' % RIC.id, 'dire', cuerpo)
check('R1a traslado inicial con identificador de solicitud', st == 200, js)
mov_id = (js.get('movimiento') or {}).get('id')
antes = estado_ficha(RIC.id)
st, js = post('/api/estudiantes/%d/traslado' % RIC.id, 'dire', dict(cuerpo))
check('R1b mismo identificador y MISMO contenido: reintento, el mismo movimiento', st == 200 and js.get('reintento')
      and js['movimiento']['id'] == mov_id and estado_ficha(RIC.id) == antes, js)
for campo, valor in (('desde', '2026-10-22'), ('no_lista', 7), ('motivo', 'Otro motivo'), ('curso_destino_id', C4.id)):
    st, js = post('/api/estudiantes/%d/traslado' % RIC.id, 'dire', dict(cuerpo, **{campo: valor}))
    check('R1c mismo identificador con otro %s: 409 y nada cambia' % campo,
          st == 409 and js.get('error') == 'SOLICITUD_REPETIDA_DISTINTA' and estado_ficha(RIC.id) == antes, (st, js))
st, js = post('/api/estudiantes/%d/traslado' % EV[3].id, 'dire', dict(cuerpo))
check('R1d mismo identificador para OTRO estudiante: 409 y ninguno cambia',
      st == 409 and js.get('error') == 'SOLICITUD_REPETIDA_DISTINTA' and estado_ficha(RIC.id) == antes
      and estado_ficha(EV[3].id)[3] == 0, (st, js))

# ═════════════ R5. GET /api/asistencia por permanencia ═════════════
print('\n== R5. GET /api/asistencia ==')
st, js = post('/api/asistencia', 'pM', {'estudiante_id': RIC.id, 'curso_id': MA.id, 'asignatura_id': art.id,
                                        'fecha': '2026-10-22', 'estado': 'presente'})
check('R5a el destino carga su marca del 22/10', st == 200, js)


def get_lista(curso, fecha):
    r = c.get('/api/asistencia?curso_id=%d&asignatura_id=%d&fecha=%s' % (curso.id, art.id, fecha), headers=H('dire'))
    return {x['estudiante_id']: x for x in r.json()} if r.status_code == 200 else r.status_code


lv_antes, lv_desp = get_lista(V, '2026-10-14'), get_lista(V, '2026-10-26')
lm_antes, lm_desp = get_lista(MA, '2026-10-14'), get_lista(MA, '2026-10-22')
check('R5b origen 14/10: aparece con su n.º 3 y su marca de la tarde', RIC.id in lv_antes
      and lv_antes[RIC.id]['no_lista'] == 3 and lv_antes[RIC.id]['estado'] == 'presente', lv_antes.get(RIC.id))
check('R5c origen 26/10 (ya trasladado): no aparece', RIC.id not in lv_desp, lv_desp.get(RIC.id))
check('R5d destino 14/10 (aún no incorporado): no aparece ni trae la marca de la tarde', RIC.id not in lm_antes,
      lm_antes.get(RIC.id))
check('R5e destino 22/10: aparece con su número en el destino y SOLO la marca de la mañana', RIC.id in lm_desp
      and lm_desp[RIC.id]['no_lista'] == 3 and lm_desp[RIC.id]['estado'] == 'presente', lm_desp.get(RIC.id))

# ═════════════ R4. LOTE ═════════════
print('\n== R4. Lote autorizado por estudiante ==')
asis_antes = sorted(a.id for a in db.query(M.Asistencia))
st, js = post('/api/asistencia/masivo', 'pV', {'fecha': '2026-10-28', 'asignatura_id': art.id,
                                                'asistencias': [{'estudiante_id': EV[0].id, 'estado': 'presente'},
                                                                {'estudiante_id': EM[0].id, 'estado': 'presente'}]})
db.expire_all()
check('R4a lote de dos cursos de un docente autorizado SOLO en uno: 403 y no se escribe ninguna fila',
      st == 403 and sorted(a.id for a in db.query(M.Asistencia)) == asis_antes, (st, js))
st, js = post('/api/asistencia/masivo', 'pM', {'fecha': '2026-10-28', 'asignatura_id': art.id,
                                                'asistencias': [{'estudiante_id': EM[0].id, 'estado': 'presente'},
                                                                {'estudiante_id': EV[0].id, 'estado': 'presente'}]})
db.expire_all()
check('R4b igual si el primero es de SU curso y el segundo no (antes pasaba por el primero): 403, nada escrito',
      st == 403 and sorted(a.id for a in db.query(M.Asistencia)) == asis_antes, (st, js))
st, js = post('/api/asistencia/masivo', 'pVM', {'fecha': '2026-10-28', 'asignatura_id': art.id,
                                                 'asistencias': [{'estudiante_id': EV[0].id, 'estado': 'presente'},
                                                                 {'estudiante_id': EM[0].id, 'estado': 'ausente'}]})
db.expire_all()
filas = {a.estudiante_id: a.curso_id for a in db.query(M.Asistencia).filter_by(fecha=dt.date(2026, 10, 28))}
check('R4c lote de varios cursos con docente autorizado en ambos: se conserva y cada fila lleva SU curso',
      st == 200 and filas.get(EV[0].id) == V.id and filas.get(EM[0].id) == MA.id, (st, js, filas))

# ═════════════ R2. NUMERACIÓN ═════════════
print('\n== R2. Numeración que no cabe ==')
st, js = post('/api/estudiantes/%d/traslado' % EV[1].id, 'dire',
              {'curso_destino_id': MA.id, 'desde': '2026-10-29', 'no_lista': 45})
check('R2a un número disponible alto (45) se admite en el destino', st == 200, js)
val = c.get('/api/registros/validar/%d' % MA.id, headers=H('dire')).json()
txt = json.dumps(val, ensure_ascii=False)
check('R2b el validador del curso con movimientos lo explica: NUMERACION_EXCEDE_PLANTILLA', 'NUMERACION_EXCEDE_PLANTILLA' in txt
      and '45' in txt, txt[:400])
db.expire_all()
filas_m, _ = APP._estudiantes_registro(db, db.get(M.Usuario, IDS['dire']), db.get(M.Curso, MA.id))
check('R2c con movimientos NO se comprime: la lista llega a la fila 45 (el generador la rechazará si no cabe)',
      len(filas_m) == 45 and filas_m[44].id == EV[1].id, len(filas_m))
r = c.get('/api/registros/secundaria/%d/preview-pdf' % MA.id, headers=H('dire'))
check('R2d el borrador tampoco se emite comprimido: 422 ESTUDIANTES_EXCEDEN_PLANTILLA',
      r.status_code == 422 and 'EXCEDEN_PLANTILLA' in r.text, (r.status_code, r.text[:200]))
filas_c4, _ = APP._estudiantes_registro(db, db.get(M.Usuario, IDS['dire']), db.get(M.Curso, C4.id))
check('R2e curso SIN movimientos con hueco que no cabe: como en main (en orden), documentado',
      len(filas_c4) == 2, len(filas_c4))

# ═════════════ R2f. ENDPOINT OFICIAL ═════════════
print('\n== R2f. Registro oficial con numeración que no cabe ==')
import registro_validator as RV  # noqa: E402


def estado_numeros():
    db.expire_all()
    return (sorted((e.id, e.curso_id, e.no_lista) for e in db.query(M.Estudiante).filter_by(colegio_id=col.id)),
            sorted((r.curso_id, r.no_lista, r.estudiante_id) for r in db.query(M.ReservaNumeroLista)))


nums_antes = estado_numeros()
for q in ('', '?force=true'):
    r = c.get('/api/registros/secundaria/%d%s' % (MA.id, q), headers=H('dire'))
    det = r.json().get('detalle') if r.headers.get('content-type', '').startswith('application/json') else None
    check('R2f oficial%s: 400 con NUMERACION_EXCEDE_PLANTILLA, sin PDF' % (' (force)' if q else ''),
          r.status_code == 400 and any('NUMERACION_EXCEDE_PLANTILLA' in str(x) for x in (det or []))
          and not r.content.startswith(b'%PDF'), (r.status_code, str(det)[:300]))
_orig_val = RV.validar_registro_secundaria


def _val_sin_otros_errores(*a, **k):
    # Simula un curso por lo demás completo (titular, horario...): se quitan
    # TODOS los errores, también el de numeración, para ver la segunda defensa.
    r_ = _orig_val(*a, **k)
    r_.errors.clear()
    r_.warnings.clear()
    return r_


RV.validar_registro_secundaria = _val_sin_otros_errores
try:
    r = c.get('/api/registros/secundaria/%d?force=true' % MA.id, headers=H('dire'))
finally:
    RV.validar_registro_secundaria = _orig_val
check('R2g aunque la validación pasara, el oficial no se imprime comprimido: 422 EXCEDEN_PLANTILLA',
      r.status_code == 422 and 'EXCEDEN_PLANTILLA' in r.text and not r.content.startswith(b'%PDF'),
      (r.status_code, r.text[:200]))
check('R2h nada se renumeró: fichas y reservas idénticas (el 45 sigue siendo 45)', estado_numeros() == nums_antes
      and db.get(M.Estudiante, EV[1].id).no_lista == 45)

# ═════════════ R1r. PRIMER RETIRO SIN TRAYECTORIA ═════════════
print('\n== R1r. Primer retiro sin trayectoria: solicitud y huella ==')


def estado_retiro(eid):
    db.expire_all()
    e = db.get(M.Estudiante, eid)
    ficha = None if e is None else (e.activo, e.condicion, e.fecha_retiro, e.motivo_retiro, e.retirado_por,
                                    e.curso_id, e.no_lista)
    return (ficha, db.query(M.MovimientoEstudiante).filter_by(estudiante_id=eid).count(),
            db.query(M.LogAuditoria).filter_by(registro_id=eid, accion='retirar').count())


cuerpo_r = {'desde': '2026-10-20', 'motivo': 'Mudanza (sintético)', 'client_request_id': 'aud-ret-1'}
st, js = post('/api/estudiantes/%d/retiro' % ER.id, 'dire', cuerpo_r)
ret0 = estado_retiro(ER.id)
check('R1r-a primer retiro: ficha con fecha, motivo y autor; sin fila de movimiento; una auditoría',
      st == 200 and ret0 == ((False, 'retirado', dt.date(2026, 10, 19), 'Mudanza (sintético)', IDS['dire'], V.id, 7), 0, 1),
      (st, js, ret0))
aud = db.query(M.LogAuditoria).filter_by(registro_id=ER.id, accion='retirar').one()
check('R1r-b la auditoría guarda el identificador y la huella de la solicitud',
      "'client_request_id': 'aud-ret-1'" in aud.datos_nuevos and "'solicitud':" in aud.datos_nuevos
      and "'motivo': 'Mudanza (sintético)'" in aud.datos_nuevos, aud.datos_nuevos[-300:])
st, js = post('/api/estudiantes/%d/retiro' % ER.id, 'dire', dict(cuerpo_r))
check('R1r-c mismo identificador y mismo contenido: el resultado anterior, sin cambios',
      st == 200 and js.get('reintento') and js.get('fecha_retiro') == '2026-10-19' and js.get('desde') == '2026-10-20'
      and estado_retiro(ER.id) == ret0, (st, js))
for campo, valor in (('desde', '2026-10-21'), ('motivo', 'Otro motivo'), ('motivo', None)):
    st, js = post('/api/estudiantes/%d/retiro' % ER.id, 'dire', dict(cuerpo_r, **{campo: valor}))
    check('R1r-d mismo identificador con otro %s=%r: 409 y nada cambia' % (campo, valor),
          st == 409 and js.get('error') == 'SOLICITUD_REPETIDA_DISTINTA' and estado_retiro(ER.id) == ret0, (st, js))
st, js = post('/api/estudiantes/%d/traslado' % EV[0].id, 'dire',
              {'curso_destino_id': MA.id, 'desde': '2026-10-21', 'client_request_id': 'aud-ret-1'})
check('R1r-e el identificador de ese retiro, usado para otro estudiante/tipo: 409 y nadie cambia',
      st == 409 and js.get('error') == 'SOLICITUD_REPETIDA_DISTINTA' and estado_retiro(ER.id) == ret0
      and db.query(M.MovimientoEstudiante).filter_by(estudiante_id=EV[0].id).count() == 0, (st, js))
st, js = post('/api/estudiantes/%d/reactivar' % ER.id, 'dire', {'desde': '2026-10-27'})
db.expire_all()
mv = db.query(M.MovimientoEstudiante).filter_by(estudiante_id=ER.id).one_or_none()
rp = (mv.get_detalle().get('retiro_previo') if mv else None) or {}
check('R1r-f la reactivación conserva el retiro previo (fecha, motivo y autor) en su movimiento',
      st == 200 and rp.get('fecha_retiro') == '2026-10-19' and rp.get('motivo_retiro') == 'Mudanza (sintético)'
      and rp.get('retirado_por') == IDS['dire'], (st, js, rp))
tras_reac = estado_retiro(ER.id)
st, js = post('/api/estudiantes/%d/retiro' % ER.id, 'dire', dict(cuerpo_r))
check('R1r-g tras reactivar, repetir la solicitud original devuelve su resultado y NO vuelve a retirar',
      st == 200 and js.get('reintento') and js.get('fecha_retiro') == '2026-10-19'
      and estado_retiro(ER.id) == tras_reac and tras_reac[0][0] is True, (st, js, tras_reac))
check('R1r-h la auditoría del retiro sigue ahí tras la reactivación',
      db.query(M.LogAuditoria).filter_by(registro_id=ER.id, accion='retirar').count() == 1)
EE_ID = EE.id
st, js = post('/api/estudiantes/%d/retiro' % EE_ID, 'dire',
              {'desde': '2026-10-20', 'motivo': 'Ficha duplicada (sintético)', 'client_request_id': 'aud-ret-2'})
r = c.post('/api/estudiantes/%d/eliminar-por-error' % EE_ID, headers=H('dire'),
           json={'confirmar_estudiante_id': EE_ID, 'motivo': 'Duplicada (sintético)'})
db.expire_all()
aud_r = db.query(M.LogAuditoria).filter_by(registro_id=EE_ID, accion='retirar').one_or_none()
aud_e = [a for a in db.query(M.LogAuditoria).filter_by(registro_id=EE_ID) if a.accion != 'retirar']
check('R1r-i eliminada por error una ficha retirada: su auditoría de retiro (solicitud, huella, fecha, motivo, autor) se conserva',
      st == 200 and r.status_code == 200 and db.get(M.Estudiante, EE_ID) is None and aud_r is not None
      and "'client_request_id': 'aud-ret-2'" in aud_r.datos_nuevos and "'solicitud':" in aud_r.datos_nuevos
      and "'fecha_retiro': '2026-10-19'" in aud_r.datos_nuevos and aud_r.usuario_id == IDS['dire'],
      (st, r.status_code, r.text[:200]))
check('R1r-j y la traza de la eliminación también lleva la fecha, el motivo y el autor del retiro',
      any("'fecha_retiro': '2026-10-19'" in (a.datos_anteriores or '') and 'Ficha duplicada' in (a.datos_anteriores or '')
          and ("'retirado_por': %d" % IDS['dire']) in (a.datos_anteriores or '') for a in aud_e),
      [(a.accion, (a.datos_anteriores or '')[:200]) for a in aud_e])
st, js = post('/api/estudiantes/%d/retiro' % ER.id, 'dire',
              {'desde': '2026-10-20', 'motivo': 'Mudanza', 'client_request_id': 'aud-ret-2'})
check('R1r-k el identificador de la ficha eliminada no se reutiliza: 409', st == 409
      and js.get('error') == 'SOLICITUD_REPETIDA_DISTINTA' and estado_retiro(ER.id) == tras_reac, (st, js))

# ═════════════ EX. EVALUACIONES EXTRA ═════════════
print('\n== EX. Evaluaciones extra de Secundaria frente a traslados ==')


def ev_de(eid):
    db.expire_all()
    e_ = db.query(M.EvaluacionExtraSecundaria).filter_by(estudiante_id=eid, asignatura_id=art.id).one()
    return (e_.cec, e_.ceex, e_.ce, e_.completiva_final, e_.extraordinaria_final, e_.condicion_final)


def extra(k, eid, tipo, nota):
    return post('/api/calificaciones-secundaria/evaluacion-extra', k,
                {'estudiante_id': eid, 'asignatura_id': art.id, 'tipo': tipo, 'nota': nota})


def esperado(**valores):
    t = M.EvaluacionExtraSecundaria(cf_original=60.0, **valores)
    t.recalcular_todo()
    return (t.cec, t.ceex, t.ce, t.completiva_final, t.extraordinaria_final, t.condicion_final)


st, js = extra('pV', EXA.id, 'completiva', 65)
check('EX-a el docente del origen registra la completiva antes del traslado', st == 200
      and ev_de(EXA.id) == esperado(cec=65.0), (st, js, ev_de(EXA.id)))
st, js = post('/api/estudiantes/%d/traslado' % EXA.id, 'dire', {'curso_destino_id': MA.id, 'desde': '2026-11-03'})
db.expire_all()
_mv = db.query(M.MovimientoEstudiante).filter_by(estudiante_id=EXA.id).one_or_none()
_snapx = ((_mv.get_detalle().get('notas_previas') or {}).get('extra_secundaria') or {}) if _mv else {}
check('EX-b el traslado guarda en su instantánea la completiva ya registrada', st == 200
      and any(v['valores'].get('cec') == 65 for v in _snapx.values()), (st, js, _snapx))
base_ex = ev_de(EXA.id)
st, js = extra('pM', EXA.id, 'completiva', 80)
check('EX-c el docente del destino NO sobrescribe la completiva previa sin permiso: 409 y nada cambia',
      st == 409 and js.get('error') == 'NOTA_PREVIA_AL_TRASLADO' and ev_de(EXA.id) == base_ex, (st, js))
st, js = extra('pV', EXA.id, 'completiva', 70)
check('EX-d el docente del origen ya no escribe (el estudiante es de otro curso): 403 y nada cambia',
      st == 403 and ev_de(EXA.id) == base_ex, (st, js))
add(M.PermisoTemporalCalificacion(colegio_id=col.id, profesor_id=pM.id, curso_id=MA.id, asignatura_id=art.id,
                                  periodo=2, fecha_fin=dt.datetime(2030, 1, 1), otorgado_por=dire.id, activo=True))
db.commit()
st, js = extra('pM', EXA.id, 'completiva', 80)
check('EX-e un permiso de UN período no basta para corregir la evaluación extra: 409 y nada cambia',
      st == 409 and ev_de(EXA.id) == base_ex, (st, js))
_perm = add(M.PermisoTemporalCalificacion(colegio_id=col.id, profesor_id=pM.id, curso_id=MA.id, asignatura_id=art.id,
                                          periodo=None, fecha_fin=dt.datetime(2030, 1, 1), otorgado_por=dire.id,
                                          activo=True))
db.commit()
_perm_id = _perm.id


def _ultima_aud_ex():
    db.expire_all()
    return db.query(M.LogAuditoria).filter_by(accion='EVALUACION_EXTRA_GUARDADA').order_by(M.LogAuditoria.id.desc()).first()


st, js = extra('pM', EXA.id, 'completiva', 66)
check('EX-f con el permiso de corrección de todo el año el destino corrige la completiva previa (fórmulas de '
      'siempre) y la auditoría anota el permiso', st == 200 and ev_de(EXA.id) == esperado(cec=66.0)
      and ("'permiso_correccion_id': %d" % _perm_id) in (_ultima_aud_ex().datos_nuevos or ''), (st, js, ev_de(EXA.id)))
st, js = extra('pM', EXA.id, 'extraordinaria', 75)
check('EX-g la fase vacía (extraordinaria) la completa el destino sin necesitar permiso; la completiva queda',
      st == 200 and ev_de(EXA.id) == esperado(cec=66.0, ceex=75.0)
      and 'permiso_correccion_id' not in (_ultima_aud_ex().datos_nuevos or ''), (st, js, ev_de(EXA.id)))
st, js = extra('pV', EXC.id, 'completiva', 66)
st2, js2 = extra('pV', EXC.id, 'completiva', 67)
check('EX-h sin traslado, como siempre: el docente del curso registra y corrige su última fase sin permiso',
      st == 200 and st2 == 200 and ev_de(EXC.id) == esperado(cec=67.0), (st, js, st2, js2))

# ═════════════ R3. CONCURRENCIA (solo PostgreSQL) ═════════════
print('\n== R3. Movimiento frente a cargas simultáneas ==')
if engine.dialect.name != 'postgresql':
    print('  (omitida: la concurrencia se verifica en PostgreSQL temporal)')
else:
    _orig_inst = APP._instantanea_notas

    def _inst_lenta(*a, **k):
        time.sleep(2.0)            # el traslado tiene la ficha bloqueada mientras tanto
        return _orig_inst(*a, **k)

    def _en_hilo(fn, out, clave):
        try:
            out[clave] = fn()
        except Exception as exc:
            out[clave] = ('excepcion', repr(exc)[:300])

    def _req(metodo, url, k, body):
        cl = TestClient(APP.app)
        r_ = cl.request(metodo, url, headers=H(k), json=body)
        try:
            return r_.status_code, r_.json()
        except Exception:
            return r_.status_code, {'_t': r_.text[:200]}

    APP._instantanea_notas = _inst_lenta
    try:
        # R3a: asistencia del origen en un día que, tras el traslado, ya no le pertenece.
        e = EV[4]
        out = {}
        ta = threading.Thread(target=_en_hilo, args=(lambda: _req('POST', '/api/estudiantes/%d/traslado' % e.id, 'dire',
                              {'curso_destino_id': MA.id, 'desde': '2026-11-02'}), out, 'mov'))
        tb = threading.Thread(target=_en_hilo, args=(lambda: _req('POST', '/api/asistencia', 'pV',
                              {'estudiante_id': e.id, 'curso_id': V.id, 'asignatura_id': art.id,
                               'fecha': '2026-11-04', 'estado': 'presente'}), out, 'asis'))
        ta.start()
        time.sleep(0.7)
        tb.start()
        ta.join()
        tb.join()
        db.expire_all()
        marca = db.query(M.Asistencia).filter_by(estudiante_id=e.id, fecha=dt.date(2026, 11, 4)).count()
        check('R3a traslado y carga de asistencia simultáneos: el traslado entra; la carga espera, se reevalúa y '
              'se rechaza; no queda una marca del origen fuera de su permanencia',
              out['mov'][0] == 200 and out['asis'][0] in (403, 409) and marca == 0, out)
        # R3b: nota del docente de origen mientras se traslada.
        e = EV[5]
        out = {}
        ta = threading.Thread(target=_en_hilo, args=(lambda: _req('POST', '/api/estudiantes/%d/traslado' % e.id, 'dire',
                              {'curso_destino_id': MA.id, 'desde': '2026-11-02'}), out, 'mov'))
        tb = threading.Thread(target=_en_hilo, args=(lambda: _req('POST', '/api/calificaciones-secundaria', 'pV',
                              {'estudiante_id': e.id, 'asignatura_id': art.id, 'competencia_numero': 1, 'p1': 55}),
                              out, 'nota'))
        ta.start()
        time.sleep(0.7)
        tb.start()
        ta.join()
        tb.join()
        db.expire_all()
        p1 = db.query(M.CalificacionSecundaria).filter_by(estudiante_id=e.id, asignatura_id=art.id,
                                                          competencia_numero=1).one().p1
        mv = db.query(M.MovimientoEstudiante).filter_by(estudiante_id=e.id).one()
        snap = [v['valores'] for v in (mv.get_detalle().get('notas_previas') or {}).get('secundaria', {}).values()]
        check('R3b traslado y nota del curso de origen simultáneos: la nota espera y se rechaza (ya es de curso '
              'anterior, requiere permiso); la nota sigue en 80 y la instantánea la recoge',
              out['mov'][0] == 200 and out['nota'][0] == 403 and p1 == 80 and {'p1': 80.0} in snap, (out, p1, snap))
        # R3c: LOTE de asistencia frente a un traslado de uno de sus estudiantes.
        def _carrera(eid_mov, k_lote, cuerpo_lote):
            out_ = {}
            fin = {}

            def _m():
                out_['mov'] = _req('POST', '/api/estudiantes/%d/traslado' % eid_mov, 'dire',
                                   {'curso_destino_id': MA.id, 'desde': '2026-11-09'})
                fin['mov'] = time.time()

            def _l():
                t0 = time.time()
                out_['lote'] = _req('POST', '/api/asistencia/masivo', k_lote, cuerpo_lote)
                fin['lote'] = time.time() - t0      # duración del lote
            ta_, tb_ = threading.Thread(target=_m), threading.Thread(target=_l)
            ta_.start()
            time.sleep(0.7)
            tb_.start()
            ta_.join()
            tb_.join()
            return out_, fin

        for etiqueta, eid_mov, k_lote, extra, fecha_l in (
                ('docente solo del origen, lote sin curso_id', EL1.id, 'pV', {}, '2026-11-10'),
                ('docente de ambos cursos, lote con curso_id del origen', EL2.id, 'pVM', {'curso_id': V.id}, '2026-11-11')):
            db.expire_all()
            antes_l = sorted((a.id, a.estudiante_id, a.curso_id, a.fecha, a.estado) for a in db.query(M.Asistencia))
            cuerpo_l = dict(extra, fecha=fecha_l, asignatura_id=art.id,
                            asistencias=[{'estudiante_id': EV[0].id, 'estado': 'presente'},
                                         {'estudiante_id': eid_mov, 'estado': 'presente'}])
            out, fin = _carrera(eid_mov, k_lote, cuerpo_l)
            db.expire_all()
            despues_l = sorted((a.id, a.estudiante_id, a.curso_id, a.fecha, a.estado) for a in db.query(M.Asistencia))
            check('R3c %s: el traslado entra; el lote ESPERA (≥1 s, bloqueado), se reevalúa y se rechaza entero; '
                  'ni siquiera la fila del compañero se escribe' % etiqueta,
                  out['mov'][0] == 200 and out['lote'][0] in (403, 409) and fin['lote'] >= 1.0
                  and despues_l == antes_l, (out, round(fin.get('lote', 0), 2)))
        def _a_la_vez(f1, f2):
            out_, fin_ = {}, {}

            def _w(clave, f):
                t0 = time.time()
                out_[clave] = f()
                fin_[clave] = time.time() - t0      # duración de esa petición
            t1 = threading.Thread(target=_w, args=('a', f1))
            t2 = threading.Thread(target=_w, args=('b', f2))
            t1.start()
            time.sleep(0.7)
            t2.start()
            t1.join()
            t2.join()
            return out_, fin_

        # EX-con: evaluación extra del docente del ORIGEN mientras se traslada.
        out, fin = _a_la_vez(
            lambda: _req('POST', '/api/estudiantes/%d/traslado' % EXB.id, 'dire',
                         {'curso_destino_id': MA.id, 'desde': '2026-11-03'}),
            lambda: _req('POST', '/api/calificaciones-secundaria/evaluacion-extra', 'pV',
                         {'estudiante_id': EXB.id, 'asignatura_id': art.id, 'tipo': 'completiva', 'nota': 64}))
        check('EX-con-a traslado y evaluación extra del origen simultáneos: la evaluación espera, se reautoriza '
              'con el curso nuevo y se rechaza; nada escrito',
              out['a'][0] == 200 and out['b'][0] == 403 and fin['b'] >= 1.0 and ev_de(EXB.id) == esperado(),
              (out, round(fin['b'], 2), ev_de(EXB.id), esperado()))

        _orig_log = APP.log_auditoria

        def _log_lento(db_, accion, *a, **k):
            r_ = _orig_log(db_, accion, *a, **k)
            if accion == 'retirar':
                time.sleep(2.0)          # el retiro tiene la ficha bloqueada mientras tanto
            return r_
        APP.log_auditoria = _log_lento
        try:
            antes_c = ev_de(EXC.id)
            out, fin = _a_la_vez(
                lambda: _req('POST', '/api/estudiantes/%d/retiro' % EXC.id, 'dire',
                             {'desde': '2026-11-05', 'motivo': 'Retiro (sintético)'}),
                lambda: _req('POST', '/api/calificaciones-secundaria/evaluacion-extra', 'pV',
                             {'estudiante_id': EXC.id, 'asignatura_id': art.id, 'tipo': 'completiva', 'nota': 90}))
            check('EX-con-b retiro y evaluación extra simultáneos: la evaluación espera y se rechaza (retirado); '
                  'la completiva previa se conserva', out['a'][0] == 200 and out['b'][0] == 403
                  and fin['b'] >= 1.0 and ev_de(EXC.id) == antes_c, (out, round(fin['b'], 2), ev_de(EXC.id), antes_c))

            # R1s: dos primeros retiros simultáneos con la MISMA clave.
            cuerpo_s = {'desde': '2026-10-20', 'motivo': 'Mudanza (sintético)', 'client_request_id': 'aud-con-1'}
            out, _ = _a_la_vez(lambda: _req('POST', '/api/estudiantes/%d/retiro' % RS1.id, 'dire', dict(cuerpo_s)),
                               lambda: _req('POST', '/api/estudiantes/%d/retiro' % RS1.id, 'dire', dict(cuerpo_s)))
            ret1 = estado_retiro(RS1.id)
            check('R1s-a misma clave y MISMO contenido a la vez: uno retira, el otro recibe el resultado original '
                  '(reintento, misma fecha); una sola auditoría',
                  out['a'][0] == 200 and out['b'][0] == 200 and not out['a'][1].get('reintento')
                  and out['b'][1].get('reintento') and out['b'][1].get('fecha_retiro') == '2026-10-19'
                  and out['b'][1].get('desde') == '2026-10-20'
                  and ret1 == ((False, 'retirado', dt.date(2026, 10, 19), 'Mudanza (sintético)', IDS['dire'], V.id, 11),
                               0, 1), (out, ret1))
            out, _ = _a_la_vez(
                lambda: _req('POST', '/api/estudiantes/%d/retiro' % RS2.id, 'dire',
                             {'desde': '2026-10-20', 'motivo': 'Motivo A', 'client_request_id': 'aud-con-2'}),
                lambda: _req('POST', '/api/estudiantes/%d/retiro' % RS2.id, 'dire',
                             {'desde': '2026-10-20', 'motivo': 'Motivo B', 'client_request_id': 'aud-con-2'}))
            ret2 = estado_retiro(RS2.id)
            check('R1s-b misma clave y contenido DISTINTO a la vez: el primero retira; el segundo 409 '
                  'SOLICITUD_REPETIDA_DISTINTA; la ficha conserva el motivo del primero; una sola auditoría',
                  out['a'][0] == 200 and out['b'][0] == 409
                  and out['b'][1].get('error') == 'SOLICITUD_REPETIDA_DISTINTA'
                  and ret2 == ((False, 'retirado', dt.date(2026, 10, 19), 'Motivo A', IDS['dire'], V.id, 12), 0, 1),
                  (out, ret2))
        finally:
            APP.log_auditoria = _orig_log
    finally:
        APP._instantanea_notas = _orig_inst

ok = sum(1 for _, c_ in RES if c_)
print('\nRESULTADO AUDITORIA TRAS-1 (%s): %d PASARON / %d FALLARON' % (engine.dialect.name, ok, len(RES) - ok))
db.close()
sys.exit(0 if ok == len(RES) else 1)
