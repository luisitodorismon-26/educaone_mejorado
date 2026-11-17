# -*- coding: utf-8 -*-
"""ENT1 · Caso «Abraham»: completar o corregir la nota de un estudiante RETIRADO
sin reactivarlo, imprimir su boletín y volver a retirarlo si ya tiene
asistencias posteriores a una reactivación. Datos SINTÉTICOS (SQLite temporal).

  A  completar una casilla VACÍA de un período abierto
  B  corregir una nota EXISTENTE
  C  modificar un período CERRADO
  D  el estudiante sigue retirado (estado, fecha, motivo, movimientos intactos)
  E  boletín del retirado (reporte para padres y oficial) con sus notas
  F  volver a retirar a quien fue reactivado y tiene asistencias posteriores

Uso (desde backend/):  python tools/test_ent1_abraham_retirado.py
"""
import datetime as dt
import os
import sys

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(BK, 'tools'))
from test_utils import aislar_base_de_datos, verificar_engine_aislado  # noqa: E402

TMP = aislar_base_de_datos('ent1_abraham')
from database import engine, SessionLocal  # noqa: E402
verificar_engine_aislado(engine, TMP)
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
    print(('  PASA  ' if ok else '  FALLA ') + nombre + ('' if ok else '  -> ' + str(detalle)[:400]))


def add(o):
    db.add(o)
    db.flush()
    return o


HOY = APP.today_rd()
col = add(M.Colegio(nombre='Colegio Sintético ENT1', codigo='SENT1', activo=True))
add(M.ConfiguracionColegio(colegio_id=col.id, nombre=col.nombre, regional='10', distrito='10-01', codigo_centro='9'))
otro = add(M.Colegio(nombre='Otro Colegio', codigo='SOTRO', activo=True))
ano = add(M.AnoEscolar(colegio_id=col.id, nombre='2026-2027', activo=True, fecha_inicio=dt.date(2026, 8, 24),
                       fecha_fin=dt.date(2027, 6, 30), periodo_activo=2, p1_cerrado=True,
                       p1_inicio=dt.date(2026, 8, 24), p1_fin=dt.date(2026, 10, 30),
                       p2_inicio=dt.date(2026, 11, 2), p2_fin=dt.date(2027, 1, 29),
                       p3_inicio=dt.date(2027, 2, 1), p3_fin=dt.date(2027, 4, 16),
                       p4_inicio=dt.date(2027, 4, 19), p4_fin=dt.date(2027, 6, 30)))
g = add(M.Grado(colegio_id=col.id, nombre='5to Secundaria', nivel='secundaria', orden=5, activo=True))
t = add(M.Tanda(colegio_id=col.id, nombre='Vespertina', activo=True))
V = add(M.Curso(colegio_id=col.id, nombre='A', grado_id=g.id, tanda_id=t.id, ano_escolar_id=ano.id, activo=True))
V2 = add(M.Curso(colegio_id=col.id, nombre='B', grado_id=g.id, tanda_id=t.id, ano_escolar_id=ano.id, activo=True))
art = add(M.Asignatura(colegio_id=col.id, nombre='Educación Artística', codigo='EA', area_curricular_codigo='EA'))


def usuario(u, rol, colegio=col):
    return add(M.Usuario(colegio_id=colegio.id, username=u, password_hash='x', nombre=u, apellido='Sint', role=rol,
                         activo=True, must_change_password=False, token_version=0))


dire, prof, prof2 = usuario('dir_ent1', 'direccion'), usuario('prof_ent1', 'profesor'), usuario('prof2_ent1', 'profesor')
dir_otro = usuario('dir_otro', 'direccion', otro)
add(M.AsignacionProfesor(colegio_id=col.id, profesor_id=prof.id, curso_id=V.id, asignatura_id=art.id,
                         ano_escolar_id=ano.id, activo=True))
add(M.AsignacionProfesor(colegio_id=col.id, profesor_id=prof2.id, curso_id=V2.id, asignatura_id=art.id,
                         ano_escolar_id=ano.id, activo=True))
ABR = add(M.Estudiante(colegio_id=col.id, nombre='Abraham', apellido='Sintetico', matricula='ENT1-ABR', curso_id=V.id,
                       no_lista=1, activo=True, condicion='activo', fecha_ingreso=dt.date(2026, 8, 20)))
OTRO = add(M.Estudiante(colegio_id=col.id, nombre='Beto', apellido='Sintetico', matricula='ENT1-BET', curso_id=V2.id,
                        no_lista=1, activo=True, condicion='activo', fecha_ingreso=dt.date(2026, 8, 20)))
add(M.CalificacionSecundaria(colegio_id=col.id, estudiante_id=ABR.id, asignatura_id=art.id, ano_escolar_id=ano.id,
                             competencia_numero=1, p1=60))           # P2 vacía
add(M.CalificacionSecundaria(colegio_id=col.id, estudiante_id=OTRO.id, asignatura_id=art.id, ano_escolar_id=ano.id,
                             competencia_numero=1, p1=50))
db.commit()
TOK = {k: create_token(u) for k, u in (('dir', dire), ('prof', prof), ('prof2', prof2), ('dir_otro', dir_otro))}
IDS = {'ABR': ABR.id, 'OTRO': OTRO.id}


def H(k):
    return {'Authorization': 'Bearer ' + TOK[k]}


def req(m, url, k, body=None):
    r = c.request(m, url, headers=H(k), json=body)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {'_bytes': len(r.content), '_pdf': r.content[:4] == b'%PDF'}


def ficha(eid):
    db.expire_all()
    e = db.get(M.Estudiante, eid)
    return (e.activo, e.condicion, e.fecha_retiro, e.motivo_retiro, e.retirado_por,
            db.query(M.MovimientoEstudiante).filter_by(estudiante_id=eid).count())


def nota(eid, campo):
    db.expire_all()
    return getattr(db.query(M.CalificacionSecundaria).filter_by(estudiante_id=eid, asignatura_id=art.id,
                                                                competencia_numero=1).one(), campo)


def guardar(k, eid, **campos):
    return req('POST', '/api/calificaciones-secundaria', k,
               dict({'estudiante_id': eid, 'asignatura_id': art.id, 'competencia_numero': 1}, **campos))


# ── Retiro (primer retiro sin trayectoria) ──
st, js = req('POST', '/api/estudiantes/%d/retiro' % ABR.id, 'dir', {'desde': '2026-11-02', 'motivo': 'Ya no asiste (sintético)'})
check('0 retiro desde 02/11', st == 200, js)
base = ficha(ABR.id)

print('\n== A. Completar una casilla VACÍA (P2, período abierto) del retirado ==')
st, js = guardar('prof', ABR.id, p2=75)
check('A1 sin permiso: 403 (retirado: requiere el permiso de corrección de Dirección); la casilla sigue vacía',
      st == 403 and nota(ABR.id, 'p2') is None, (st, js))
st, js = req('POST', '/api/periodos/permiso-temporal', 'dir',
             {'profesor_id': prof.id, 'curso_id': V.id, 'asignatura_id': art.id, 'periodo': 2, 'horas': 24,
              'motivo': 'Completar nota faltante de retirado (sintético)'})
check('A2 Dirección concede permiso (curso, Artística, P2)', st in (200, 201), js)
st, js = guardar('prof', ABR.id, p2=75)
check('A3 con permiso de P2: se completa la casilla (75) y el estudiante SIGUE retirado',
      st == 200 and nota(ABR.id, 'p2') == 75 and ficha(ABR.id) == base, (st, js, ficha(ABR.id)))
aud = [a for a in db.query(M.LogAuditoria).filter(M.LogAuditoria.tabla.in_(['calificaciones_secundaria', 'calificacion_secundaria']))]
check('A4 la auditoría de la nota anota el permiso usado', any('permiso' in ((a.datos_nuevos or '') + (a.detalles or '')).lower()
                                                            for a in aud), [((a.datos_nuevos or '')[-160:]) for a in aud][-2:])

print('\n== B. Corregir una nota EXISTENTE ==')
st, js = guardar('prof', ABR.id, p2=78)
check('B1 corregir P2 (75 -> 78) con el mismo permiso vigente de P2: 200', st == 200 and nota(ABR.id, 'p2') == 78, (st, js))

print('\n== C. Período CERRADO (P1) ==')
st, js = guardar('prof', ABR.id, p1=65)
check('C1 corregir P1 (cerrado) solo con permiso de P2: rechazado y P1 sigue en 60',
      st in (403, 409) or nota(ABR.id, 'p1') == 60, (st, js))
check('C1b P1 intacto', nota(ABR.id, 'p1') == 60, nota(ABR.id, 'p1'))
st, js = req('POST', '/api/periodos/permiso-temporal', 'dir',
             {'profesor_id': prof.id, 'curso_id': V.id, 'asignatura_id': art.id, 'periodo': 1, 'horas': 24,
              'motivo': 'Corrección P1 cerrado (sintético)'})
st, js = guardar('prof', ABR.id, p1=65)
check('C2 con permiso de P1: se corrige el período cerrado (65) y sigue retirado',
      st == 200 and nota(ABR.id, 'p1') == 65 and ficha(ABR.id) == base, (st, js))
st, js = guardar('prof', ABR.id, rp1=70)
check('C3 completar una casilla vacía del período cerrado (RP1) con el permiso de P1: 200',
      st == 200 and nota(ABR.id, 'rp1') == 70, (st, js))
# Permiso de período cerrado de OTRO curso: ¿sirve para un estudiante ACTIVO de este?
st, js = req('POST', '/api/periodos/permiso-temporal', 'dir',
             {'profesor_id': prof2.id, 'curso_id': V2.id, 'asignatura_id': art.id, 'periodo': 1, 'horas': 24,
              'motivo': 'Permiso de su curso (sintético)'})
st, js = guardar('prof2', OTRO.id, p1=55)
check('C4 docente de su curso, P1 cerrado, permiso de su curso: corrige (control)', st == 200 and nota(OTRO.id, 'p1') == 55, (st, js))

print('\n== D. Nada cambió en la ficha ni en la trayectoria ==')
check('D1 activo, condición, fecha, motivo, autor del retiro y movimientos: idénticos', ficha(ABR.id) == base,
      (ficha(ABR.id), base))

print('\n== E. Boletín del retirado ==')
st, js = req('GET', '/api/boletines/estudiante/%d/pdf' % ABR.id, 'dir')
check('E1 reporte para padres del retirado: PDF', st == 200 and js.get('_pdf'), (st, js))
r = c.get('/api/boletines/estudiante/%d/pdf' % ABR.id, headers=H('dir'))
try:
    import pymupdf
    txt = ''.join(p.get_text() for p in pymupdf.open(stream=r.content, filetype='pdf'))
    check('E2 el reporte lleva sus notas conservadas (65, RP 70, 78)', all(v in txt for v in ('65', '70', '78')), txt[:200])
except ImportError:
    pass
st, js = req('GET', '/api/boletines/estudiante/%d/pdf-minerd-v2' % ABR.id, 'dir')
print('     (boletín oficial MINERD del retirado: HTTP %s %s)' % (st, '' if js.get('_pdf') else str(js)[:160]))
check('E3 boletín oficial MINERD del retirado: se imprime (o se explica por qué no)', st == 200 and js.get('_pdf')
      or (st in (400, 409, 422) and (js.get('error') or js.get('detalle'))), (st, str(js)[:200]))
st, js = req('GET', '/api/boletines/estudiante/%d/pdf' % ABR.id, 'dir_otro')
check('E4 Dirección de otro colegio: 404', st == 404, st)
st, js = req('GET', '/api/asistencia/curso/%d?fecha=2026-11-04&asignatura_id=%d' % (V.id, art.id), 'dir_otro')
check('E5 la lista de asistencia del curso tampoco se ve desde otro colegio: 404', st == 404, st)

print('\n== F. Volver a retirar tras una reactivación con asistencias posteriores ==')
st, js = req('POST', '/api/estudiantes/%d/reactivar' % ABR.id, 'dir', {'desde': '2026-11-05'})
check('F1 reactivación desde 05/11 (conserva el retiro previo)', st == 200, js)
dias = [d for d in (dt.date(2026, 11, 5), dt.date(2026, 11, 9), dt.date(2026, 11, 11)) if d <= HOY]
for d in dias:
    req('POST', '/api/asistencia', 'prof', {'estudiante_id': ABR.id, 'curso_id': V.id, 'asignatura_id': art.id,
                                            'fecha': d.isoformat(), 'estado': 'presente'})
db.expire_all()
marcas = sorted(a.fecha for a in db.query(M.Asistencia).filter_by(estudiante_id=ABR.id))
check('F2 asistencias registradas tras la reactivación', marcas == dias, marcas)
st, js = req('POST', '/api/estudiantes/%d/retiro' % ABR.id, 'dir', {'desde': '2026-11-06', 'motivo': 'Ya no asiste'})
check('F3 retirar «desde» una fecha anterior a esas marcas: 409 con las marcas en conflicto y una fecha sugerida; nada cambia',
      st == 409 and js.get('fecha_sugerida') and ficha(ABR.id)[0] is True, (st, js))
sug = js.get('fecha_sugerida')
st, js = req('POST', '/api/estudiantes/%d/retiro' % ABR.id, 'dir', {'desde': sug, 'motivo': 'Ya no asiste'})
db.expire_all()
marcas2 = sorted(a.fecha for a in db.query(M.Asistencia).filter_by(estudiante_id=ABR.id))
movs = db.query(M.MovimientoEstudiante).filter_by(estudiante_id=ABR.id).order_by(M.MovimientoEstudiante.secuencia).all()
rp = (movs[0].get_detalle().get('retiro_previo') or {}) if movs else {}
check('F4 con la fecha sugerida (día siguiente a la última marca): retirado; las marcas se conservan',
      st == 200 and ficha(ABR.id)[0] is False and marcas2 == dias, (st, js, marcas2))
check('F5 la trayectoria conserva el primer retiro (fecha, motivo y autor), la reactivación y el nuevo retiro',
      [m.tipo for m in movs] == ['reactivacion', 'retiro'] and rp.get('motivo_retiro') == 'Ya no asiste (sintético)'
      and rp.get('retirado_por') == dire.id, ([m.tipo for m in movs], rp))
st, js = guardar('prof', ABR.id, p2=80)
check('F6 de nuevo retirado: completar/corregir sigue exigiendo el permiso de Dirección (vigente de P2): 200',
      st == 200 and nota(ABR.id, 'p2') == 80 and ficha(ABR.id)[0] is False, (st, js))

ok = sum(1 for _, x in RES if x)
print('\nRESULTADO ENT1 ABRAHAM: %d PASARON / %d FALLARON' % (ok, len(RES) - ok))
db.close()
sys.exit(0 if ok == len(RES) else 1)
