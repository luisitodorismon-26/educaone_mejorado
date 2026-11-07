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
    finally:
        APP._instantanea_notas = _orig_inst

ok = sum(1 for _, c_ in RES if c_)
print('\nRESULTADO AUDITORIA TRAS-1 (%s): %d PASARON / %d FALLARON' % (engine.dialect.name, ok, len(RES) - ok))
db.close()
sys.exit(0 if ok == len(RES) else 1)
