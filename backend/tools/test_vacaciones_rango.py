# -*- coding: utf-8 -*-
"""ENT-B · Vacaciones por rango. Datos SINTÉTICOS en una base aislada.

  V  validación (nombre, fechas, año escolar) y permisos (solo Dirección)
  P  vista previa: rango, días, ya no laborables, conflictos; no escribe nada
  C  asistencia registrada en el rango: se detiene sin borrar ni anular nada
  R  confirmar: días del calendario creados una sola vez; reintento y solapamiento
  A  asistencia bloqueada en el servidor (individual, lote, desmarcar; Primaria
     y Secundaria; bordes incluidos); un feriado suelto sigue sin bloquear
  G  la lista de asistencia avisa del rango (lo que usa la pantalla)
  N  las notas se siguen guardando con sus permisos habituales
  S  «No hubo clase» se conserva (fila y columna del Registro)
  D  días esperados: asistencia canónica, resumen por períodos, boletín y Registro
  Q  quitar el rango: desactiva solo lo que creó; nada se borra
  F  «Cargar Feriados RD» no queda oculto por un rango
  O  otro colegio: ni ve ni se ve afectado
  X  concurrencia real (solo PostgreSQL temporal): reintentos y solapes
     simultáneos, y rango frente a una lista que se pasa a la vez

Uso (desde backend/):
    python tools/test_vacaciones_rango.py                      # SQLite aislado
    EO_PG_TEST_SERVER=postgresql://usuario@127.0.0.1:PUERTO/postgres \\
        python tools/test_vacaciones_rango.py                  # PostgreSQL temporal
"""
import datetime as dt
import os
import sys
import threading
import time

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(BK, 'tools'))
from test_utils import aislar_base_de_datos, verificar_engine_aislado  # noqa: E402

PG_SERVER = os.environ.get('EO_PG_TEST_SERVER')
if PG_SERVER:
    import pg_base_temporal as PGT
    PG = PGT.BaseTemporal(PG_SERVER, prefijo='eo_tmp_vacaciones_')
    os.environ['DATABASE_URL'] = PG.crear()
    TMP = None
else:
    PG = None
    TMP = aislar_base_de_datos('vacaciones_rango')
from database import engine, SessionLocal  # noqa: E402
if PG:
    assert engine.dialect.name == 'postgresql' and engine.url.database == PG.nombre, engine.url
    PG.engines.append(engine)
else:
    verificar_engine_aislado(engine, TMP)
print('Motor:', engine.dialect.name)

import models as M  # noqa: E402
import app as APP  # noqa: E402
import registro_asistencia as REG  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from auth import create_token  # noqa: E402

M.Base.metadata.create_all(bind=engine)
db = SessionLocal()
c = TestClient(APP.app)
RES = []
D = dt.date


def check(nombre, ok, detalle=''):
    RES.append((nombre, bool(ok)))
    print(('  PASA  ' if ok else '  FALLA ') + nombre + ('' if ok else '  -> ' + str(detalle)[:500]))


def add(o):
    db.add(o)
    db.flush()
    return o


# ── Datos sintéticos ─────────────────────────────────────────────────
col = add(M.Colegio(nombre='Colegio Sintetico ENTB', codigo='SENTB', activo=True))
add(M.ConfiguracionColegio(colegio_id=col.id, nombre=col.nombre, regional='10', distrito='10-01', codigo_centro='9'))
otro = add(M.Colegio(nombre='Otro Colegio ENTB', codigo='SOTRB', activo=True))
add(M.ConfiguracionColegio(colegio_id=otro.id, nombre=otro.nombre, regional='10', distrito='10-01', codigo_centro='8'))


def ano_de(colegio):
    return add(M.AnoEscolar(colegio_id=colegio.id, nombre='2026-2027', activo=True, fecha_inicio=D(2026, 8, 24),
                            fecha_fin=D(2027, 6, 30), periodo_activo=2,
                            p1_inicio=D(2026, 8, 24), p1_fin=D(2026, 10, 30),
                            p2_inicio=D(2026, 11, 2), p2_fin=D(2027, 1, 29),
                            p3_inicio=D(2027, 2, 1), p3_fin=D(2027, 4, 16),
                            p4_inicio=D(2027, 4, 19), p4_fin=D(2027, 6, 30)))


ano, ano_o = ano_de(col), ano_de(otro)
gs = add(M.Grado(colegio_id=col.id, nombre='5to Secundaria', nivel='secundaria', orden=5, activo=True))
gp = add(M.Grado(colegio_id=col.id, nombre='3ro Primaria', nivel='primaria', orden=3, activo=True))
gso = add(M.Grado(colegio_id=otro.id, nombre='5to Secundaria', nivel='secundaria', orden=5, activo=True))
SA = add(M.Curso(colegio_id=col.id, nombre='A', grado_id=gs.id, ano_escolar_id=ano.id, activo=True))
PA = add(M.Curso(colegio_id=col.id, nombre='A', grado_id=gp.id, ano_escolar_id=ano.id, activo=True))
SO = add(M.Curso(colegio_id=otro.id, nombre='A', grado_id=gso.id, ano_escolar_id=ano_o.id, activo=True))
art = add(M.Asignatura(colegio_id=col.id, nombre='Educacion Artistica', codigo='EA', area_curricular_codigo='EA'))
len_ = add(M.Asignatura(colegio_id=col.id, nombre='Lengua Espanola', codigo='LE', area_curricular_codigo='LE'))
art_o = add(M.Asignatura(colegio_id=otro.id, nombre='Educacion Artistica', codigo='EA', area_curricular_codigo='EA'))


def usuario(u, rol, colegio=col):
    return add(M.Usuario(colegio_id=colegio.id, username=u, password_hash='x', nombre=u, apellido='Sint', role=rol,
                         activo=True, must_change_password=False, token_version=0))


dire, secre, coord = usuario('dir_entb', 'direccion'), usuario('sec_entb', 'secretaria'), usuario('coo_entb', 'coordinador')
prof, tit = usuario('prof_entb', 'profesor'), usuario('tit_entb', 'profesor')
dir_o, prof_o = usuario('dir_o_entb', 'direccion', otro), usuario('prof_o_entb', 'profesor', otro)
add(M.AsignacionProfesor(colegio_id=col.id, profesor_id=prof.id, curso_id=SA.id, asignatura_id=art.id,
                         ano_escolar_id=ano.id, activo=True))
add(M.AsignacionProfesor(colegio_id=col.id, profesor_id=tit.id, curso_id=PA.id, asignatura_id=len_.id,
                         ano_escolar_id=ano.id, es_titular=True, activo=True))
add(M.AsignacionProfesor(colegio_id=otro.id, profesor_id=prof_o.id, curso_id=SO.id, asignatura_id=art_o.id,
                         ano_escolar_id=ano_o.id, activo=True))
for dia in ('Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes'):
    add(M.Horario(colegio_id=col.id, profesor_id=prof.id, curso_id=SA.id, asignatura_id=art.id, dia=dia,
                  hora_inicio='08:00', hora_fin='09:00', tipo_bloque='clase', activo=True))


def est(nombre, cur, n, colegio=col):
    return add(M.Estudiante(colegio_id=colegio.id, nombre=nombre, apellido='Sint', matricula='ENTB-%s' % nombre,
                            curso_id=cur.id, no_lista=n, activo=True, condicion='activo',
                            fecha_ingreso=D(2026, 8, 20)))


E1, E2 = est('Sec1', SA, 1), est('Sec2', SA, 2)
P1 = est('Prim1', PA, 1)
EO = est('OtroSec', SO, 1, otro)
add(M.CalificacionSecundaria(colegio_id=col.id, estudiante_id=E1.id, asignatura_id=art.id, ano_escolar_id=ano.id,
                             competencia_numero=1, p1=70))
# Un feriado suelto ya existente DENTRO del rango principal (11/11) y otro fuera (25/11).
FER = add(M.DiaNoLaborable(colegio_id=col.id, fecha=D(2026, 11, 11), nombre='Feriado sintetico', tipo='feriado',
                           recurrente=False, ano_escolar_id=ano.id, activo=True))
FER2 = add(M.DiaNoLaborable(colegio_id=col.id, fecha=D(2026, 11, 16), nombre='Feriado suelto', tipo='feriado',
                            recurrente=False, ano_escolar_id=ano.id, activo=True))
# «No hubo clase» del 12/11 en Artística de 5to A (dentro del rango principal).
SNI = add(M.SesionNoImpartida(colegio_id=col.id, fecha=D(2026, 11, 12), curso_id=SA.id, asignatura_id=art.id,
                              profesor_id=prof.id, dia_semana_snapshot='Jueves', motivo_codigo='SUSP_CURSO',
                              registrado_por=prof.id, activo=True))
# Marcas reales en la semana del 26-30/10 (rango con conflicto).
for f in (D(2026, 10, 27), D(2026, 10, 28)):
    add(M.Asistencia(colegio_id=col.id, estudiante_id=E1.id, curso_id=SA.id, asignatura_id=art.id, fecha=f,
                     estado='presente', registrado_por=prof.id))
add(M.Asistencia(colegio_id=col.id, estudiante_id=P1.id, curso_id=PA.id, asignatura_id=None, fecha=D(2026, 10, 28),
                 estado='ausente', registrado_por=tit.id))
db.commit()

TOK = {k: create_token(u) for k, u in (('dir', dire), ('sec', secre), ('coo', coord), ('prof', prof), ('tit', tit),
                                       ('dir_o', dir_o), ('prof_o', prof_o))}
H = lambda k: {'Authorization': 'Bearer ' + TOK[k]}  # noqa: E731


def req(m, url, k, body=None):
    r = c.request(m, url, headers=H(k), json=body)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {'_pdf': r.content[:4] == b'%PDF', '_bytes': len(r.content)}


def huella():
    """Filas de las tablas que la operación podría tocar (y su contenido)."""
    db.expire_all()
    return (
        sorted((a.id, a.estudiante_id, a.fecha, a.estado, a.asignatura_id, a.curso_id) for a in db.query(M.Asistencia).all()),
        sorted((d.id, d.fecha, d.nombre, d.tipo, d.activo) for d in db.query(M.DiaNoLaborable).all()),
        sorted((r.id, r.activo) for r in db.query(M.RangoVacaciones).all()),
        sorted((s.id, s.activo, s.fecha) for s in db.query(M.SesionNoImpartida).all()),
    )


PRINCIPAL = {'nombre': 'Vacaciones sinteticas', 'fecha_inicio': '2026-11-07', 'fecha_fin': '2026-11-13'}
CONFLICTO = {'nombre': 'Semana con listas', 'fecha_inicio': '2026-10-26', 'fecha_fin': '2026-10-30'}

# Antes de nada: días esperados y Registro sin rango.
db.expire_all()
CAN0 = APP._asistencia_canonica(db, dire, db.get(M.Estudiante, E2.id), db.get(M.AnoEscolar, ano.id))
REG0 = REG.build_asistencia_registro(db, SA.id, asignatura_id=art.id)
_, RPER0 = req('GET', '/api/asistencia/resumen-periodos/curso/%d' % SA.id, 'dir')
st_b0, BOL0 = req('GET', '/api/boletines/estudiante/%d' % E2.id, 'dir')


# ═════════════ V. Validación y permisos ═════════════
print('\n== V. Validación y permisos ==')
h0 = huella()
for etiqueta, body, esperado in (
        ('sin nombre', dict(PRINCIPAL, nombre='  '), 400),
        ('final antes que inicial', dict(PRINCIPAL, fecha_inicio='2026-11-13', fecha_fin='2026-11-07'), 400),
        ('fecha inválida', dict(PRINCIPAL, fecha_inicio='13/11/2026'), 400),
        ('fuera del año escolar', dict(PRINCIPAL, fecha_inicio='2027-06-28', fecha_fin='2027-07-05'), 400)):
    st1, _ = req('POST', '/api/vacaciones/vista-previa', 'dir', body)
    st2, _ = req('POST', '/api/vacaciones', 'dir', body)
    check('V %s -> %d (vista previa y confirmar)' % (etiqueta, esperado), st1 == esperado and st2 == esperado, (st1, st2))
for k in ('prof', 'sec', 'coo'):
    st1, _ = req('POST', '/api/vacaciones/vista-previa', k, PRINCIPAL)
    st2, _ = req('POST', '/api/vacaciones', k, PRINCIPAL)
    check('V %s no configura vacaciones (403)' % k, st1 == 403 and st2 == 403, (st1, st2))
check('V ninguna validación escribió nada', huella() == h0)

# ═════════════ P. Vista previa ═════════════
print('\n== P. Vista previa (no escribe) ==')
h0 = huella()
st, P = req('POST', '/api/vacaciones/vista-previa', 'dir', PRINCIPAL)
check('P vista previa 200', st == 200, P)
check('P rango del 07/11 al 13/11, ambas fechas incluidas: 7 días de calendario',
      P.get('fecha_inicio') == '2026-11-07' and P.get('fecha_fin') == '2026-11-13' and P.get('dias_calendario') == 7, P)
check('P días de clase que dejan de contar: 4 (sin sábado, domingo ni el feriado del 11/11)',
      P.get('dias_lectivos_excluidos') == 4, P.get('dias_lectivos_excluidos'))
check('P el feriado ya existente aparece como «ya no laborable» y se mantiene',
      [d['fecha'] for d in P.get('ya_no_laborables', [])] == ['2026-11-11'], P.get('ya_no_laborables'))
check('P informa el «No hubo clase» del rango (se conserva)', P.get('sesiones_no_impartidas') == 1, P)
check('P sin conflictos: puede confirmarse', P.get('total_marcas') == 0 and P.get('puede_confirmar') is True, P)
st, PC = req('POST', '/api/vacaciones/vista-previa', 'dir', CONFLICTO)
check('P con listas registradas: conflictos por fecha y curso, no puede confirmarse',
      st == 200 and PC.get('total_marcas') == 3 and PC.get('puede_confirmar') is False
      and [(x['fecha'], x['marcas']) for x in PC['conflictos_asistencia']]
      == [('2026-10-27', 1), ('2026-10-28', 1), ('2026-10-28', 1)], PC)
check('P la vista previa no escribió nada', huella() == h0)

# ═════════════ C. Conflicto con asistencia registrada ═════════════
print('\n== C. Asistencia registrada en el rango: se detiene ==')
h0 = huella()
st, js = req('POST', '/api/vacaciones', 'dir', CONFLICTO)
check('C confirmar con listas en el rango -> 409 ASISTENCIA_REGISTRADA con la lista de conflictos',
      st == 409 and js.get('error') == 'ASISTENCIA_REGISTRADA' and js['analisis']['total_marcas'] == 3, js)
check('C no se creó rango ni día, y ninguna marca se borró, anuló ni cambió', huella() == h0)

# ═════════════ R. Confirmar, reintento y solapamiento ═════════════
print('\n== R. Confirmar; reintento y solapamiento ==')
st, js = req('POST', '/api/vacaciones', 'dir', PRINCIPAL)
check('R confirmar -> 201', st == 201, js)
RID = (js.get('vacaciones') or {}).get('id')
# Días esperados JUSTO después de confirmar (antes de pasar más listas).
db.expire_all()
CAN1 = APP._asistencia_canonica(db, dire, db.get(M.Estudiante, E2.id), db.get(M.AnoEscolar, ano.id))
REG1 = REG.build_asistencia_registro(db, SA.id, asignatura_id=art.id)
_, RPER1 = req('GET', '/api/asistencia/resumen-periodos/curso/%d' % SA.id, 'dir')
st_b1, BOL1 = req('GET', '/api/boletines/estudiante/%d' % E2.id, 'dir')
db.expire_all()
dias_rango = db.query(M.DiaNoLaborable).filter_by(colegio_id=col.id, tipo='vacaciones', activo=True).all()
check('R un día del calendario por cada fecha que no era no laborable (6: todas menos el feriado del 11/11)',
      sorted(d.fecha.day for d in dias_rango) == [7, 8, 9, 10, 12, 13] and js.get('dias_creados') == 6,
      sorted(d.fecha for d in dias_rango))
check('R los días quedan en el año escolar activo y no recurrentes',
      all(d.ano_escolar_id == ano.id and not d.recurrente for d in dias_rango))
check('R el feriado del 11/11 sigue igual (no se duplicó la fecha)',
      db.query(M.DiaNoLaborable).filter_by(colegio_id=col.id, fecha=D(2026, 11, 11), activo=True).count() == 1
      and db.get(M.DiaNoLaborable, FER.id).tipo == 'feriado')
h1 = huella()
st, js = req('POST', '/api/vacaciones', 'dir', PRINCIPAL)
check('R reintento idéntico -> 200 «ya estaba registrado», sin duplicar', st == 200 and js.get('ya_existia') is True
      and huella() == h1, js)
for etiqueta, body in (('dentro', {'nombre': 'Otro', 'fecha_inicio': '2026-11-09', 'fecha_fin': '2026-11-10'}),
                       ('que lo contiene', {'nombre': 'Otro', 'fecha_inicio': '2026-11-02', 'fecha_fin': '2026-11-20'}),
                       ('borde final', {'nombre': 'Otro', 'fecha_inicio': '2026-11-13', 'fecha_fin': '2026-11-14'}),
                       ('mismas fechas, otro nombre', dict(PRINCIPAL, nombre='Otro nombre'))):
    st1, pv = req('POST', '/api/vacaciones/vista-previa', 'dir', body)
    st, js = req('POST', '/api/vacaciones', 'dir', body)
    check('R solapamiento %s -> vista previa lo muestra y confirmar da 409 SOLAPAMIENTO, sin escribir' % etiqueta,
          st1 == 200 and pv['solapes'] and not pv['puede_confirmar']
          and st == 409 and js.get('error') == 'SOLAPAMIENTO' and huella() == h1, (pv, js))
st, js = req('GET', '/api/vacaciones', 'prof')
check('R el personal ve el rango (GET /api/vacaciones)', st == 200 and [r['id'] for r in js] == [RID], js)
st, js = req('GET', '/api/dias-no-laborables', 'dir')
check('R el calendario marca los días del rango con su rango (la pantalla los agrupa)',
      sorted(d['fecha'] for d in js if d.get('rango_vacaciones_id') == RID)
      == ['2026-11-%02d' % d for d in (7, 8, 9, 10, 12, 13)]
      and next(d for d in js if d['id'] == FER.id).get('rango_vacaciones_id') is None, js)
uno = next(d for d in js if d.get('rango_vacaciones_id') == RID)
st, js = req('DELETE', '/api/dias-no-laborables/%d' % uno['id'], 'dir')
check('R un día del rango no se quita suelto (409 DIA_DE_RANGO)', st == 409 and js.get('error') == 'DIA_DE_RANGO'
      and huella() == h1, js)

# ═════════════ A. Asistencia bloqueada en el servidor ═════════════
print('\n== A. Asistencia bloqueada en el servidor ==')
h1 = huella()
for f in ('2026-11-07', '2026-11-09', '2026-11-11', '2026-11-13'):
    st, js = req('POST', '/api/asistencia', 'prof', {'estudiante_id': E1.id, 'curso_id': SA.id,
                                                     'asignatura_id': art.id, 'fecha': f, 'estado': 'presente'})
    ok = st == 409 and js.get('error') == 'VACACIONES' if f != '2026-11-07' else st in (400, 409)
    check('A Secundaria individual %s -> rechazada%s' % (f, ' (sábado)' if f == '2026-11-07' else ' 409 VACACIONES'),
          ok, (st, js))
st, js = req('POST', '/api/asistencia/masivo', 'prof', {'fecha': '2026-11-10', 'curso_id': SA.id, 'asignatura_id': art.id,
                                                        'asistencias': [{'estudiante_id': E1.id, 'estado': 'presente'},
                                                                        {'estudiante_id': E2.id, 'estado': 'ausente'}]})
check('A Secundaria lote -> 409 VACACIONES, ninguna fila', st == 409 and js.get('error') == 'VACACIONES', js)
st, js = req('POST', '/api/asistencia/masivo', 'tit', {'fecha': '2026-11-12', 'curso_id': PA.id,
                                                       'asistencias': [{'estudiante_id': P1.id, 'estado': 'presente'}]})
check('A Primaria lote (titular) -> 409 VACACIONES', st == 409 and js.get('error') == 'VACACIONES', js)
st, js = req('POST', '/api/asistencia', 'tit', {'estudiante_id': P1.id, 'curso_id': PA.id, 'fecha': '2026-11-09',
                                                'estado': 'presente'})
check('A Primaria individual -> 409 VACACIONES', st == 409 and js.get('error') == 'VACACIONES', js)
st, js = req('DELETE', '/api/asistencia/%d?fecha=2026-11-09&asignatura_id=%d' % (E1.id, art.id), 'prof')
check('A desmarcar dentro del rango -> 409 VACACIONES', st == 409 and js.get('error') == 'VACACIONES', js)
check('A ninguna escritura entró', huella() == h1)
st, js = req('POST', '/api/asistencia', 'prof', {'estudiante_id': E1.id, 'curso_id': SA.id, 'asignatura_id': art.id,
                                                 'fecha': '2026-11-06', 'estado': 'presente'})
st2, js2 = req('POST', '/api/asistencia', 'prof', {'estudiante_id': E1.id, 'curso_id': SA.id, 'asignatura_id': art.id,
                                                   'fecha': '2026-11-17', 'estado': 'presente'})
check('A el día anterior (06/11) y uno posterior (17/11) se registran con normalidad', st == 200 and st2 == 200, (js, js2))
st, js = req('POST', '/api/asistencia', 'prof', {'estudiante_id': E2.id, 'curso_id': SA.id, 'asignatura_id': art.id,
                                                 'fecha': '2026-11-16', 'estado': 'presente'})
check('A un feriado SUELTO (16/11) sigue sin bloquear la asistencia (S1 §3)', st == 200, js)
st, js = req('POST', '/api/asistencia', 'prof_o', {'estudiante_id': EO.id, 'curso_id': SO.id, 'asignatura_id': art_o.id,
                                                   'fecha': '2026-11-10', 'estado': 'presente'})
check('O otro colegio pasa lista ese mismo día (no le afecta el rango)', st == 200, js)

# ═════════════ G. La lista avisa ═════════════
print('\n== G. La lista de asistencia avisa del rango ==')
st, js = req('GET', '/api/asistencia/curso/%d?fecha=2026-11-10&asignatura_id=%d' % (SA.id, art.id), 'prof')
check('G fecha en el rango: «vacaciones» con nombre y fechas', st == 200 and (js.get('vacaciones') or {}).get('nombre')
      == PRINCIPAL['nombre'] and js['vacaciones']['fecha_fin'] == '2026-11-13', js.get('vacaciones'))
st, js = req('GET', '/api/asistencia/curso/%d?fecha=2026-11-12' % PA.id, 'tit')
check('G también en Primaria', st == 200 and js.get('vacaciones'), js.get('vacaciones'))
st, js = req('GET', '/api/asistencia/curso/%d?fecha=2026-11-14&asignatura_id=%d' % (SA.id, art.id), 'prof')
check('G fuera del rango: vacaciones = null', st == 200 and js.get('vacaciones') is None, js.get('vacaciones'))

# ═════════════ N. Notas ═════════════
print('\n== N. Las notas se siguen trabajando ==')
st, js = req('POST', '/api/calificaciones-secundaria', 'prof', {'estudiante_id': E1.id, 'asignatura_id': art.id,
                                                                'curso_id': SA.id, 'competencia_numero': 1, 'p2': 81})
db.expire_all()
n = db.query(M.CalificacionSecundaria).filter_by(estudiante_id=E1.id, asignatura_id=art.id, competencia_numero=1).one()
check('N guardar una nota del período abierto durante las vacaciones -> 200 y queda guardada',
      st == 200 and n.p2 == 81 and n.p1 == 70, (st, js, n.p1, n.p2))
db.query(M.AnoEscolar).filter_by(id=ano.id).update({'p1_cerrado': True})
db.commit()
st, js = req('POST', '/api/calificaciones-secundaria', 'prof', {'estudiante_id': E1.id, 'asignatura_id': art.id,
                                                                'curso_id': SA.id, 'competencia_numero': 1, 'p1': 99})
db.expire_all()
check('N un período cerrado sigue exigiendo su permiso (no cambia nada)',
      db.query(M.CalificacionSecundaria).filter_by(estudiante_id=E1.id, competencia_numero=1).one().p1 == 70, (st, js))
db.query(M.AnoEscolar).filter_by(id=ano.id).update({'p1_cerrado': False})
db.commit()

# ═════════════ S. «No hubo clase» ═════════════
print('\n== S. «No hubo clase» se conserva ==')
db.expire_all()
s = db.get(M.SesionNoImpartida, SNI.id)
check('S la sesión no impartida del 12/11 sigue activa y sin cambios', s.activo and s.motivo_codigo == 'SUSP_CURSO')
nov0 = next(m for m in REG0 if m['clave'] == '2026-11')
nov1 = next(m for m in REG1 if m['clave'] == '2026-11')
check('S el Registro conserva la columna del 12/11 con su motivo', 12 in nov1['dias'] and 12 in nov1['no_impartidas'],
      (nov1['dias'], nov1['no_impartidas']))

# ═════════════ D. Días esperados ═════════════
print('\n== D. Días esperados (canónica, resumen, boletín, Registro) ==')
check('D asistencia canónica: 4 días lectivos menos (09, 10, 12 y 13/11)',
      CAN0['dias_lectivos'] - CAN1['dias_lectivos'] == 4
      and not any(f in CAN1['dias'] for f in (D(2026, 11, 9), D(2026, 11, 10), D(2026, 11, 12), D(2026, 11, 13))),
      (CAN0['dias_lectivos'], CAN1['dias_lectivos']))
check('D por período: P2 baja 4 días; P1 igual',
      CAN0['periodos']['p2']['dias_lectivos'] - CAN1['periodos']['p2']['dias_lectivos'] == 4
      and CAN0['periodos']['p1']['dias_lectivos'] == CAN1['periodos']['p1']['dias_lectivos'])


def lectivos_resumen(js, eid):
    filas = js.get('estudiantes') if isinstance(js, dict) else js
    f = next(x for x in filas if (x.get('estudiante_id') or (x.get('estudiante') or {}).get('id')) == eid)
    return f.get('dias_lectivos')


try:
    l0, l1 = lectivos_resumen(RPER0, E2.id), lectivos_resumen(RPER1, E2.id)
except Exception as exc:  # noqa: BLE001
    l0 = l1 = repr(exc)
check('D resumen por períodos del curso: 4 días lectivos menos', isinstance(l0, int) and l0 - l1 == 4, (l0, l1))


def buscar(o, clave):
    if isinstance(o, dict):
        for k, v in o.items():
            if k == clave and isinstance(v, int):
                yield v
            yield from buscar(v, clave)
    elif isinstance(o, list):
        for v in o:
            yield from buscar(v, clave)


b0, b1 = list(buscar(BOL0, 'dias_lectivos')), list(buscar(BOL1, 'dias_lectivos'))
check('D boletín: los días lectivos del año bajan 4', st_b0 == 200 and st_b1 == 200 and b0 and b1 and b0[0] - b1[0] == 4,
      (st_b0, st_b1, b0[:3], b1[:3]))
check('D Registro de noviembre: sin columnas 09, 10 y 13; el 12 (No hubo clase) se queda; el resto igual',
      [d for d in nov0['dias'] if d not in (9, 10, 13)] == nov1['dias'], (nov0['dias'], nov1['dias']))
st, js = req('GET', '/api/boletines/estudiante/%d/pdf-minerd-v2' % E1.id, 'dir')
check('D boletín oficial (PDF) se genera con su plantilla', st == 200 and js.get('_pdf'), (st, js))

# ═════════════ Q. Quitar el rango ═════════════
print('\n== Q. Quitar el rango ==')
st, js = req('DELETE', '/api/vacaciones/%d' % RID, 'prof')
check('Q un profesor no lo quita (403)', st == 403, js)
st, js = req('DELETE', '/api/vacaciones/%d' % RID, 'dir_o')
check('O Dirección de otro colegio no lo ve ni lo quita (404)', st == 404, js)
st, js = req('DELETE', '/api/vacaciones/%d' % RID, 'dir')
db.expire_all()
r = db.get(M.RangoVacaciones, RID)
check('Q Dirección lo quita: queda inactivo con quién y cuándo (no se borra)',
      st == 200 and r is not None and not r.activo and r.quitado_por == dire.id and r.quitado_en, js)
check('Q se desactivan SOLO los 6 días que creó; el feriado del 11/11 sigue activo',
      db.query(M.DiaNoLaborable).filter_by(colegio_id=col.id, tipo='vacaciones', activo=True).count() == 0
      and db.query(M.DiaNoLaborable).filter_by(colegio_id=col.id, tipo='vacaciones').count() == 6
      and db.get(M.DiaNoLaborable, FER.id).activo)
st, js = req('POST', '/api/asistencia', 'prof', {'estudiante_id': E1.id, 'curso_id': SA.id, 'asignatura_id': art.id,
                                                 'fecha': '2026-11-10', 'estado': 'presente'})
CAN2 = APP._asistencia_canonica(db, dire, db.get(M.Estudiante, E2.id), db.get(M.AnoEscolar, ano.id))
# Vuelven los 4 días; y el 16/11 (feriado suelto) cuenta ahora porque en A se
# pasó lista ese día (una marca real nunca se descarta): CAN0 + 1.
check('Q tras quitarlo se puede pasar lista y los días vuelven a contar',
      st == 200 and CAN2['dias_lectivos'] == CAN0['dias_lectivos'] + 1, (st, js, CAN0['dias_lectivos'], CAN2['dias_lectivos']))
st, js = req('POST', '/api/vacaciones', 'dir', PRINCIPAL)
check('Q registrar de nuevo el mismo rango se detiene: la lista del 10/11 pasada tras quitarlo es un conflicto',
      st == 409 and js.get('error') == 'ASISTENCIA_REGISTRADA'
      and [x['fecha'] for x in js['analisis']['conflictos_asistencia']] == ['2026-11-10'], js)

# ═════════════ F. Feriados oficiales y rangos ═════════════
print('\n== F. «Cargar Feriados RD» con un rango que cubre un feriado ==')
st, js = req('POST', '/api/vacaciones', 'dir', {'nombre': 'Navidad sintetica', 'fecha_inicio': '2026-12-21',
                                                'fecha_fin': '2026-12-31'})
RNAV = (js.get('vacaciones') or {}).get('id')
check('F rango de Navidad (21-31/12) registrado', st == 201, js)
st, js = req('POST', '/api/dias-no-laborables/cargar-feriados-rd', 'dir', {'ano': 2026})
db.expire_all()
nav = [d for d in db.query(M.DiaNoLaborable).filter_by(colegio_id=col.id, fecha=D(2026, 12, 25), activo=True).all()]
check('F el feriado de Navidad se carga aunque el rango cubra el 25/12 (no queda oculto por el rango)',
      st == 200 and any(d.tipo == 'feriado' and d.recurrente for d in nav), [(d.tipo, d.nombre) for d in nav])
st, js = req('DELETE', '/api/vacaciones/%d' % RNAV, 'dir')
db.expire_all()
check('F al quitar el rango, el feriado de Navidad sigue en el calendario',
      st == 200 and db.query(M.DiaNoLaborable).filter_by(colegio_id=col.id, fecha=D(2026, 12, 25), tipo='feriado',
                                                         activo=True).count() == 1)

# ═════════════ O. Otro colegio ═════════════
print('\n== O. Otro colegio ==')
st, js = req('GET', '/api/vacaciones', 'dir_o')
check('O no ve los rangos del otro colegio', st == 200 and js == [], js)

# ═════════════ X. Concurrencia (solo PostgreSQL) ═════════════
print('\n== X. Concurrencia real ==')
if engine.dialect.name != 'postgresql':
    print('  (omitida: la concurrencia se verifica en PostgreSQL temporal)')
else:
    def _req_hilo(metodo, url, k, body, out, clave):
        try:
            cl = TestClient(APP.app)
            r_ = cl.request(metodo, url, headers=H(k), json=body)
            out[clave] = (r_.status_code, r_.json())
        except Exception as exc:  # noqa: BLE001
            out[clave] = ('excepcion', repr(exc)[:300])

    _orig_an = APP._analisis_vacaciones
    _orig_bloq = APP._bloquear_colegio

    def _an_lento(*a, **k):
        r_ = _orig_an(*a, **k)
        time.sleep(1.0)        # ensancha la ventana entre comprobar y escribir
        return r_

    def correr(lotes, pausa=0.15):
        out, hilos = {}, []
        for i, (m, url, k, body) in enumerate(lotes):
            t = threading.Thread(target=_req_hilo, args=(m, url, k, body, out, i))
            hilos.append(t)
            t.start()
            time.sleep(pausa)
        for t in hilos:
            t.join()
        return out

    def rangos_activos(nombre_like=None):
        db.expire_all()
        q = db.query(M.RangoVacaciones).filter_by(colegio_id=col.id, activo=True)
        return [x for x in q.all() if nombre_like is None or x.nombre.startswith(nombre_like)]

    def escenario(control):
        APP._analisis_vacaciones = _an_lento
        if control:
            APP._bloquear_colegio = lambda *a, **k: None
        try:
            tag = 'CTRL' if control else 'REAL'
            dia_rep = {'nombre': 'Rep %s' % tag, 'fecha_inicio': '2026-12-01' if control else '2026-12-07',
                       'fecha_fin': '2026-12-02' if control else '2026-12-08'}
            out1 = correr([('POST', '/api/vacaciones', 'dir', dia_rep)] * 3)
            n1 = len(rangos_activos('Rep %s' % tag))
            base = '2027-01-1' if control else '2027-02-1'
            out2 = correr([('POST', '/api/vacaciones', 'dir', {'nombre': 'Sol %s A' % tag, 'fecha_inicio': base + '1',
                                                               'fecha_fin': base + '5'}),
                           ('POST', '/api/vacaciones', 'dir', {'nombre': 'Sol %s B' % tag, 'fecha_inicio': base + '3',
                                                               'fecha_fin': base + '9'})])
            n2 = len(rangos_activos('Sol %s' % tag))
            # Rango que contiene HOY-1 frente a una lista de ese día, a la vez.
            fecha = '2026-11-%02d' % (3 if control else 4)
            out3 = correr([('POST', '/api/vacaciones', 'dir', {'nombre': 'Car %s' % tag, 'fecha_inicio': fecha,
                                                               'fecha_fin': fecha}),
                           ('POST', '/api/asistencia', 'prof', {'estudiante_id': E2.id, 'curso_id': SA.id,
                                                                'asignatura_id': art.id, 'fecha': fecha,
                                                                'estado': 'presente'})], pausa=0.4)
            db.expire_all()
            n3r = len(rangos_activos('Car %s' % tag))
            n3a = db.query(M.Asistencia).filter_by(estudiante_id=E2.id, fecha=dt.date.fromisoformat(fecha)).count()
            return (n1, out1), (n2, out2), (n3r, n3a, out3)
        finally:
            APP._analisis_vacaciones = _orig_an
            APP._bloquear_colegio = _orig_bloq

    (c1, o1), (c2, o2), (c3r, c3a, o3) = escenario(control=True)
    print('    CONTROL sin bloqueo: reintentos -> %d rangos; solapes -> %d; rango+lista -> rango %d, marcas %d'
          % (c1, c2, c3r, c3a))
    check('X CONTROL: sin el bloqueo la prueba SÍ detecta la carrera (duplicado, solape o rango con marca)',
          c1 > 1 or c2 > 1 or (c3r and c3a), (o1, o2, o3))
    (c1, o1), (c2, o2), (c3r, c3a, o3) = escenario(control=False)
    check('X 3 confirmaciones idénticas a la vez -> 1 rango (las otras: «ya estaba registrado»)',
          c1 == 1 and sorted(v[0] for v in o1.values()) == [200, 200, 201], o1)
    check('X 2 rangos solapados a la vez -> 1 rango; el otro 409 SOLAPAMIENTO',
          c2 == 1 and sorted(v[0] for v in o2.values()) == [201, 409], o2)
    check('X rango y lista del mismo día a la vez -> nunca ambos (o el rango y ninguna marca, o la marca y ningún rango)',
          (c3r, c3a) in ((1, 0), (0, 1)), (c3r, c3a, o3))

print('\nRESULTADO ENT-B VACACIONES POR RANGO (%s): %d PASARON / %d FALLARON'
      % (engine.dialect.name, sum(1 for _, ok in RES if ok), sum(1 for _, ok in RES if not ok)))
db.close()
sys.exit(0 if all(ok for _, ok in RES) else 1)
