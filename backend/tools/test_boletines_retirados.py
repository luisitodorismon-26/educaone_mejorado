# -*- coding: utf-8 -*-
"""ENT-A · Boletines y notas de RETIRADOS sin reactivarlos; permiso de período
cerrado filtrado por curso. Datos SINTÉTICOS (SQLite temporal).

  K  permiso de período cerrado: del curso de la nota o general (Secundaria y Primaria)
  C  casillas autorizadas que calcula el servidor (campos_autorizados)
  G  guardado de una casilla autorizada / no autorizada; el estudiante sigue retirado
  L  lista de Boletines con retirados (cohorte del curso y año)
  I  impresión sin permiso de corrección; otro colegio

Uso (desde backend/):  python tools/test_boletines_retirados.py
"""
import datetime as dt
import os
import sys

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(BK, 'tools'))
from test_utils import aislar_base_de_datos, verificar_engine_aislado  # noqa: E402

TMP = aislar_base_de_datos('boletines_retirados')
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


col = add(M.Colegio(nombre='Colegio Sintetico ENTA', codigo='SENTA', activo=True))
add(M.ConfiguracionColegio(colegio_id=col.id, nombre=col.nombre, regional='10', distrito='10-01', codigo_centro='9'))
otro = add(M.Colegio(nombre='Otro Colegio ENTA', codigo='SOTRA', activo=True))
ano = add(M.AnoEscolar(colegio_id=col.id, nombre='2026-2027', activo=True, fecha_inicio=dt.date(2026, 8, 24),
                       fecha_fin=dt.date(2027, 6, 30), periodo_activo=2, p1_cerrado=True,
                       p1_inicio=dt.date(2026, 8, 24), p1_fin=dt.date(2026, 10, 30),
                       p2_inicio=dt.date(2026, 11, 2), p2_fin=dt.date(2027, 1, 29),
                       p3_inicio=dt.date(2027, 2, 1), p3_fin=dt.date(2027, 4, 16),
                       p4_inicio=dt.date(2027, 4, 19), p4_fin=dt.date(2027, 6, 30)))
gs = add(M.Grado(colegio_id=col.id, nombre='5to Secundaria', nivel='secundaria', orden=5, activo=True))
gp = add(M.Grado(colegio_id=col.id, nombre='3ro Primaria', nivel='primaria', orden=3, activo=True))
SA = add(M.Curso(colegio_id=col.id, nombre='A', grado_id=gs.id, ano_escolar_id=ano.id, activo=True))
SB = add(M.Curso(colegio_id=col.id, nombre='B', grado_id=gs.id, ano_escolar_id=ano.id, activo=True))
PA = add(M.Curso(colegio_id=col.id, nombre='A', grado_id=gp.id, ano_escolar_id=ano.id, activo=True))
PB = add(M.Curso(colegio_id=col.id, nombre='B', grado_id=gp.id, ano_escolar_id=ano.id, activo=True))
art = add(M.Asignatura(colegio_id=col.id, nombre='Educacion Artistica', codigo='EA', area_curricular_codigo='EA'))
len_ = add(M.Asignatura(colegio_id=col.id, nombre='Lengua Espanola', codigo='LE', area_curricular_codigo='LE'))


def usuario(u, rol, colegio=col):
    return add(M.Usuario(colegio_id=colegio.id, username=u, password_hash='x', nombre=u, apellido='Sint', role=rol,
                         activo=True, must_change_password=False, token_version=0))


dire, secre = usuario('dir_enta', 'direccion'), usuario('sec_enta', 'secretaria')
prof, prof_otro = usuario('prof_enta', 'profesor'), usuario('prof2_enta', 'profesor')
dir_otro = usuario('dir_otro_enta', 'direccion', otro)
for cur, asig, tit in ((SA, art, False), (SB, art, False), (PA, len_, True), (PB, len_, True)):
    add(M.AsignacionProfesor(colegio_id=col.id, profesor_id=prof.id, curso_id=cur.id, asignatura_id=asig.id,
                             ano_escolar_id=ano.id, es_titular=tit, activo=True))


def est(nombre, cur, n):
    return add(M.Estudiante(colegio_id=col.id, nombre=nombre, apellido='Sint', matricula='ENTA-%s' % nombre,
                            curso_id=cur.id, no_lista=n, activo=True, condicion='activo',
                            fecha_ingreso=dt.date(2026, 8, 20)))


RET = est('Retirado', SA, 1)            # se retira desde el 16/11: cursó P1 y parte de P2
ACT = est('ActivoA', SA, 2)
ACTB = est('ActivoB', SB, 1)
PRA, PRB = est('PrimA', PA, 1), est('PrimB', PB, 1)
add(M.CalificacionSecundaria(colegio_id=col.id, estudiante_id=RET.id, asignatura_id=art.id, ano_escolar_id=ano.id,
                             competencia_numero=1, p1=60))
for e in (ACT, ACTB):
    add(M.CalificacionSecundaria(colegio_id=col.id, estudiante_id=e.id, asignatura_id=art.id, ano_escolar_id=ano.id,
                                 competencia_numero=1, p1=60))
for e in (PRA, PRB):
    add(M.CalificacionPrimaria(colegio_id=col.id, estudiante_id=e.id, asignatura_id=len_.id, ano_escolar_id=ano.id,
                               competencia_numero=1, p1=60))
db.commit()
TOK = {k: create_token(u) for k, u in (('dir', dire), ('sec', secre), ('prof', prof), ('prof2', prof_otro),
                                       ('dir_otro', dir_otro))}
H = lambda k: {'Authorization': 'Bearer ' + TOK[k]}  # noqa: E731


def req(m, url, k, body=None):
    r = c.request(m, url, headers=H(k), json=body)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {'_pdf': r.content[:4] == b'%PDF', '_bytes': len(r.content)}


def nota(modelo, eid, campo='p1'):
    db.expire_all()
    return getattr(db.query(modelo).filter_by(estudiante_id=eid, competencia_numero=1).one(), campo)


def permiso(profesor, curso, asig, periodo, horas=24):
    st, js = req('POST', '/api/periodos/permiso-temporal', 'dir',
                 {'profesor_id': profesor.id, 'curso_id': curso.id if curso else None,
                  'asignatura_id': asig.id, 'periodo': periodo, 'horas': horas, 'motivo': 'sintético'})
    assert st == 201, (st, js)
    return js['id']


def limpiar_permisos():
    db.query(M.PermisoTemporalCalificacion).delete()
    db.commit()


def ficha(eid):
    db.expire_all()
    e = db.get(M.Estudiante, eid)
    return (e.activo, e.condicion, e.fecha_retiro, e.motivo_retiro, e.retirado_por, e.curso_id, e.no_lista,
            db.query(M.MovimientoEstudiante).filter_by(estudiante_id=eid).count(),
            db.query(M.Asistencia).filter_by(estudiante_id=eid).count())


print('\n== K. Permiso de período CERRADO (P1): del curso de la nota o general ==')
for nivel, ruta, modelo, A, B, eA, eB, asig in (
        ('Secundaria', '/api/calificaciones-secundaria', M.CalificacionSecundaria, SA, SB, ACT, ACTB, art),
        ('Primaria', '/api/calificaciones-primaria', M.CalificacionPrimaria, PA, PB, PRA, PRB, len_)):
    guardar = lambda e, v: req('POST', ruta, 'prof', {'estudiante_id': e.id, 'asignatura_id': asig.id,  # noqa: E731
                                                       'competencia_numero': 1, 'p1': v})
    guardar(eA, 61)
    check('K1 %s sin permiso: el P1 cerrado del curso A no cambia' % nivel, nota(modelo, eA.id) == 60)
    permiso(prof, B, asig, 1)
    guardar(eA, 63)
    check('K2 %s permiso SOLO del curso B: el P1 cerrado del curso A sigue sin cambiar (antes: 63)' % nivel,
          nota(modelo, eA.id) == 60, nota(modelo, eA.id))
    guardar(eB, 62)
    check('K3 %s control: con ese permiso sí se corrige el P1 del curso B' % nivel, nota(modelo, eB.id) == 62)
    limpiar_permisos()
    permiso(prof, None, asig, 1)
    guardar(eA, 64)
    check('K4 %s permiso GENERAL (sin curso) concedido por Dirección: se conserva y corrige el curso A' % nivel,
          nota(modelo, eA.id) == 64, nota(modelo, eA.id))
    limpiar_permisos()

print('\n== Retiro del estudiante (desde 16/11) ==')
st, js = req('POST', '/api/estudiantes/%d/retiro' % RET.id, 'dir', {'desde': '2026-11-16', 'motivo': 'Ya no asiste (sintético)'})
check('0 retiro', st == 200, js)
base = ficha(RET.id)
URL_NOTAS = '/api/calificaciones-secundaria/curso/%d/asignatura/%d' % (SA.id, art.id)


def campos(k):
    st, js = req('GET', URL_NOTAS, k)
    fila = next((x for x in js.get('calificaciones', []) if x['estudiante']['id'] == RET.id), None) if st == 200 else None
    return (fila or {}).get('permanencia', {}).get('campos_autorizados') if fila else ('HTTP', st)


print('\n== C. Casillas autorizadas que decide el servidor ==')
check('C1 sin permiso: ninguna casilla (todo en solo lectura)', campos('prof') == [], campos('prof'))
pid = permiso(prof, SA, art, 2)
check('C2 permiso del curso A, Artística, P2: solo P2 y RP2', campos('prof') == ['p2', 'rp2'], campos('prof'))
check('C3 otro docente sin asignación: ninguna', campos('prof2') in ([], ('HTTP', 403)), campos('prof2'))
check('C4 Dirección (consulta): ninguna casilla editable', campos('dir') == [], campos('dir'))
db.query(M.PermisoTemporalCalificacion).filter_by(id=pid).update({'fecha_fin': dt.datetime(2020, 1, 1)})
db.commit()
check('C5 permiso VENCIDO: ninguna', campos('prof') == [], campos('prof'))
limpiar_permisos()
permiso(prof, SB, art, 2)
check('C6 permiso de OTRO curso (B): ninguna', campos('prof') == [], campos('prof'))
limpiar_permisos()
permiso(prof, SA, art, 4)
check('C7 permiso de un período que no cursó (P4): ninguna', campos('prof') == [], campos('prof'))
limpiar_permisos()
permiso(prof, SA, art, 1)
check('C8 permiso de P1 (cerrado, cursado): P1 y RP1', campos('prof') == ['p1', 'rp1'], campos('prof'))

print('\n== G. Guardado de casillas autorizadas y no autorizadas ==')
st, js = req('POST', '/api/calificaciones-secundaria', 'prof',
             {'estudiante_id': RET.id, 'asignatura_id': art.id, 'competencia_numero': 1, 'p2': 75})
check('G1 P2 sin permiso de P2: rechazado (403) y vacío', st == 403 and nota(M.CalificacionSecundaria, RET.id, 'p2') is None,
      (st, js))
st, js = req('POST', '/api/calificaciones-secundaria', 'prof',
             {'estudiante_id': RET.id, 'asignatura_id': art.id, 'competencia_numero': 1, 'p1': 66})
check('G2 P1 (cerrado) con su permiso: corregido a 66', st == 200 and nota(M.CalificacionSecundaria, RET.id) == 66, (st, js))
permiso(prof, SA, art, 2)
st, js = req('POST', '/api/calificaciones-secundaria', 'prof',
             {'estudiante_id': RET.id, 'asignatura_id': art.id, 'competencia_numero': 1, 'p2': 75})
check('G3 P2 vacía con permiso de P2: completada (75)', st == 200 and nota(M.CalificacionSecundaria, RET.id, 'p2') == 75, (st, js))
check('G4 el estudiante SIGUE retirado: estado, fecha, motivo, autor, curso, número, movimientos y asistencia intactos',
      ficha(RET.id) == base, (ficha(RET.id), base))

print('\n== L. Lista de Boletines con retirados ==')
url = '/api/estudiantes?curso_id=%d&ano_id=%d' % (SA.id, ano.id)
st, js = req('GET', url, 'dir')
check('L1 sin la opción: solo activos (como antes)', st == 200 and RET.id not in [e['id'] for e in js], [e['id'] for e in js])
st, js = req('GET', url + '&incluir_retirados=true', 'dir')
fila = next((e for e in js if e['id'] == RET.id), None) if st == 200 else None
check('L2 con la opción: aparece, identificado como retirado (activo=False, condición «retirado»)',
      fila is not None and fila['activo'] is False and fila['condicion'] == 'retirado', fila)
st, js = req('GET', url + '&incluir_retirados=true', 'sec')
check('L3 Secretaría también lo ve', st == 200 and RET.id in [e['id'] for e in js], st)
st, js = req('GET', '/api/estudiantes?curso_id=%d&ano_id=%d&incluir_retirados=true' % (SB.id, ano.id), 'dir')
check('L4 otro curso del mismo año: no aparece', st == 200 and RET.id not in [e['id'] for e in js])
st, js = req('GET', url + '&incluir_retirados=true', 'dir_otro')
check('L5 Dirección de otro colegio: no lo ve', st in (403, 404) or RET.id not in [e['id'] for e in (js if isinstance(js, list) else [])],
      st)

print('\n== I. Impresión sin permiso de corrección ==')
limpiar_permisos()
for nombre, u in (('reporte para padres', '/api/boletines/estudiante/%d/pdf'), ('boletín oficial MINERD', '/api/boletines/estudiante/%d/pdf-minerd-v2')):
    st, js = req('GET', u % RET.id, 'dir')
    check('I1 %s del retirado, SIN permisos vigentes: PDF' % nombre, st == 200 and js.get('_pdf'), (st, js))
st, js = req('GET', '/api/boletines/estudiante/%d' % RET.id, 'sec')
check('I2 vista previa del boletín (Secretaría)', st == 200, st)
r = c.get('/api/boletines/estudiante/%d/pdf' % RET.id, headers=H('dir'))
try:
    import pymupdf
    txt = ''.join(p.get_text() for p in pymupdf.open(stream=r.content, filetype='pdf'))
    check('I3 el reporte lleva las notas completadas/corregidas (66 y 75)', '66' in txt and '75' in txt, txt[:200])
except ImportError:
    pass
st, js = req('GET', '/api/boletines/curso/%d/pdf' % SA.id, 'dir')
check('I4 lote del curso: incluye al retirado (PDF)', st == 200 and js.get('_pdf'), st)
st, js = req('GET', '/api/boletines/estudiante/%d/pdf' % RET.id, 'dir_otro')
check('I5 Dirección de otro colegio: 404', st == 404, st)
st, js = req('POST', '/api/periodos/permiso-temporal', 'dir_otro',
             {'profesor_id': prof.id, 'curso_id': SA.id, 'asignatura_id': art.id, 'periodo': 2, 'horas': 24})
check('I6 Dirección de otro colegio no puede conceder permiso a este docente: 404', st == 404, (st, js))
st, js = req('POST', '/api/periodos/permiso-temporal', 'sec',
             {'profesor_id': prof.id, 'curso_id': SA.id, 'asignatura_id': art.id, 'periodo': 2, 'horas': 24})
check('I7 Secretaría no concede permisos (403)', st == 403, st)
check('I8 tras imprimir, el estudiante sigue retirado y sin cambios', ficha(RET.id) == base)

ok = sum(1 for _, x in RES if x)
print('\nRESULTADO ENT-A BOLETINES RETIRADOS: %d PASARON / %d FALLARON' % (ok, len(RES) - ok))
db.close()
sys.exit(0 if ok == len(RES) else 1)
