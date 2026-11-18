# -*- coding: utf-8 -*-
"""RET-R · Retiro retroactivo y anulación de asistencias posteriores.

Último día real: 16/10. Retirado desde el 17/10 aunque Dirección lo registre el
18/11. Datos SINTÉTICOS en una base aislada (SQLite, o PostgreSQL temporal con
EO_PG_TEST_SERVER).

  R  vista previa, confirmación expresa (solo Dirección, motivo, huella), marcas
     originales intactas, auditoría, reintento
  I  inventario: cada consumidor de asistencia excluye las anuladas
  N  estudiantes SIN anulaciones: comportamiento idéntico
  E  escrituras: fuera de la permanencia (también desde pantalla desactualizada) y
     sobre anuladas: 409
  A  reactivación: no restaura anuladas ni reabre sus días
  V  reversión auditada: vista previa, conflictos, todo o nada, solo lo elegido
  C  corrección de la fecha de retiro (posterior): nada se restaura solo
  B  caso tipo «Abraham»: reactivación administrativa para completar notas
  K  notas: pendiente de período cursado sí; período no cursado no
  P  Primaria
  T  traslados sin cambios
  G  guarda de código: nadie lee `asistencias` fuera del ORM
  X  concurrencia real (solo PostgreSQL), con control sin bloqueo

Uso (desde backend/):  python tools/test_retiro_retroactivo.py
"""
import datetime as dt
import json
import os
import re
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
    PG = PGT.BaseTemporal(PG_SERVER, prefijo='eo_tmp_retiro_r_')
    os.environ['DATABASE_URL'] = PG.crear()
    TMP = None
else:
    PG = None
    TMP = aislar_base_de_datos('retiro_retroactivo')
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
import registro_validator as RV  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from auth import create_token  # noqa: E402

M.Base.metadata.create_all(bind=engine)
db = SessionLocal()
c = TestClient(APP.app)
D = dt.date
RES = []


def check(nombre, ok, detalle=''):
    RES.append((nombre, bool(ok)))
    print(('  PASA  ' if ok else '  FALLA ') + nombre + ('' if ok else '  -> ' + str(detalle)[:500]))


def add(o):
    db.add(o)
    db.flush()
    return o


# ── Datos sintéticos ─────────────────────────────────────────────────
col = add(M.Colegio(nombre='Colegio Sintetico RETR', codigo='SRETR', activo=True))
add(M.ConfiguracionColegio(colegio_id=col.id, nombre=col.nombre, regional='10', distrito='10-01', codigo_centro='9'))
otro = add(M.Colegio(nombre='Otro RETR', codigo='SORETR', activo=True))
ano = add(M.AnoEscolar(colegio_id=col.id, nombre='2026-2027', activo=True, fecha_inicio=D(2026, 8, 24),
                       fecha_fin=D(2027, 6, 30), periodo_activo=2,
                       p1_inicio=D(2026, 8, 24), p1_fin=D(2026, 10, 30), p2_inicio=D(2026, 11, 2),
                       p2_fin=D(2027, 1, 29), p3_inicio=D(2027, 2, 1), p3_fin=D(2027, 4, 16),
                       p4_inicio=D(2027, 4, 19), p4_fin=D(2027, 6, 30)))
gs = add(M.Grado(colegio_id=col.id, nombre='5to Secundaria', nivel='secundaria', orden=5, activo=True))
gp = add(M.Grado(colegio_id=col.id, nombre='3ro Primaria', nivel='primaria', orden=3, activo=True))
SA = add(M.Curso(colegio_id=col.id, nombre='A', grado_id=gs.id, ano_escolar_id=ano.id, activo=True))
SB = add(M.Curso(colegio_id=col.id, nombre='B', grado_id=gs.id, ano_escolar_id=ano.id, activo=True))
PA = add(M.Curso(colegio_id=col.id, nombre='A', grado_id=gp.id, ano_escolar_id=ano.id, activo=True))
art = add(M.Asignatura(colegio_id=col.id, nombre='Educacion Artistica', codigo='EA', area_curricular_codigo='EA'))
len_ = add(M.Asignatura(colegio_id=col.id, nombre='Lengua Espanola', codigo='LE', area_curricular_codigo='LE'))


def usuario(u, rol, colegio=col):
    return add(M.Usuario(colegio_id=colegio.id, username=u, password_hash='x', nombre=u, apellido='Sint', role=rol,
                         activo=True, must_change_password=False, token_version=0))


dire, secre, prof, tit = (usuario('dir_r', 'direccion'), usuario('sec_r', 'secretaria'),
                          usuario('prof_r', 'profesor'), usuario('tit_r', 'profesor'))
dir_otro = usuario('dir_or', 'direccion', otro)
for cur in (SA, SB):
    add(M.AsignacionProfesor(colegio_id=col.id, profesor_id=prof.id, curso_id=cur.id, asignatura_id=art.id,
                             ano_escolar_id=ano.id, es_titular=True, activo=True))
    for dia in ('Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes'):
        add(M.Horario(colegio_id=col.id, profesor_id=prof.id, curso_id=cur.id, asignatura_id=art.id, dia=dia,
                      hora_inicio='08:00', hora_fin='09:00', tipo_bloque='clase', activo=True))
add(M.AsignacionProfesor(colegio_id=col.id, profesor_id=tit.id, curso_id=PA.id, asignatura_id=len_.id,
                         ano_escolar_id=ano.id, es_titular=True, activo=True))
ESTADOS = ('presente', 'ausente', 'tardanza', 'excusa', 'presente', 'presente')


def est(nombre, cur, n):
    return add(M.Estudiante(colegio_id=col.id, nombre=nombre, apellido='Sint', matricula='RETR-%s' % nombre,
                            curso_id=cur.id, no_lista=n, activo=True, condicion='activo',
                            fecha_ingreso=D(2026, 8, 20)))


R, N, RC, AB, CO = est('Ret', SA, 1), est('Normal', SA, 2), est('RetCorr', SA, 3), est('Abra', SA, 4), est('Conc', SA, 5)
TR = est('Trasl', SA, 6)
PR, PN = est('PrimRet', PA, 1), est('PrimNormal', PA, 2)
HOY = D(2026, 11, 18)
FIN_N = D(2026, 11, 13)             # N deja de tener listas el 13/11 (para la prueba de vacaciones)


def dias(d0, d1):
    d = d0
    while d <= d1:
        if d.weekday() < 5:
            yield d
        d += dt.timedelta(days=1)


for e in (R, N, RC, CO, TR):
    for i, f in enumerate(dias(D(2026, 10, 1), D(2026, 11, 17))):
        if e is N and f > FIN_N:
            continue
        add(M.Asistencia(colegio_id=col.id, estudiante_id=e.id, curso_id=SA.id, asignatura_id=art.id, fecha=f,
                         estado=ESTADOS[(i + e.id) % len(ESTADOS)], registrado_por=prof.id,
                         observacion='obs %d' % i if i % 9 == 0 else None))
for e in (AB,):
    for i, f in enumerate(dias(D(2026, 10, 1), D(2026, 10, 16))):
        add(M.Asistencia(colegio_id=col.id, estudiante_id=e.id, curso_id=SA.id, asignatura_id=art.id, fecha=f,
                         estado=ESTADOS[i % len(ESTADOS)], registrado_por=prof.id))
for e in (PR, PN):
    for i, f in enumerate(dias(D(2026, 10, 1), D(2026, 11, 17))):
        add(M.Asistencia(colegio_id=col.id, estudiante_id=e.id, curso_id=PA.id, asignatura_id=None, fecha=f,
                         estado=ESTADOS[(i + e.id) % len(ESTADOS)], registrado_por=tit.id))
for e in (R, N, RC, AB):
    add(M.CalificacionSecundaria(colegio_id=col.id, estudiante_id=e.id, asignatura_id=art.id, ano_escolar_id=ano.id,
                                 competencia_numero=1, p1=80, p2=85 if e is AB else None))
    add(M.CalificacionSecundaria(colegio_id=col.id, estudiante_id=e.id, asignatura_id=art.id, ano_escolar_id=ano.id,
                                 competencia_numero=2, p1=None))
db.commit()

TOK = {k: create_token(u) for k, u in (('dir', dire), ('sec', secre), ('prof', prof), ('tit', tit),
                                       ('dir_otro', dir_otro))}


def req(m, url, k, body=None):
    r = c.request(m, url, headers={'Authorization': 'Bearer ' + TOK[k]}, json=body)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {'_bytes': r.content}


def marcas_crudas(eid):
    """Las filas de `asistencias` TAL CUAL (incluidas anuladas)."""
    db.expire_all()
    return sorted((a.id, a.fecha, a.estado, a.registrado_por, a.observacion, a.curso_id, a.asignatura_id)
                  for a in db.query(M.Asistencia).filter_by(estudiante_id=eid)
                  .execution_options(incluir_anuladas=True).all())


def canonica(e):
    db.expire_all()
    return APP._asistencia_canonica(db, dire, db.get(M.Estudiante, e.id), db.get(M.AnoEscolar, ano.id))


def esperado(eid, hasta):
    out = {'presente': 0, 'ausente': 0, 'tardanza': 0, 'excusa': 0}
    for (_i, f, est_, *_r) in marcas_crudas(eid):
        if f <= hasta:
            out[est_] += 1
    return out


def fila_reg(curso, asig, eid, ests=None, ventanas=None):
    mat = REG.build_asistencia_registro(db, curso.id, asignatura_id=asig.id if asig else None,
                                        estudiantes=ests, ventanas_por_est=ventanas)
    out = []
    for m in mat:
        f = next((x for x in m['filas'] if x['estudiante_id'] == eid), None)
        if f:
            out.append((m['clave'], m['dias'], f['valores'], f['presentes'], f['ausentes'], f['porcentaje']))
    return out


def lista_dia(curso, fecha, asig, quien='prof'):
    url = '/api/asistencia/curso/%d?fecha=%s' % (curso.id, fecha.isoformat())
    if asig:
        url += '&asignatura_id=%d' % asig.id
    st, js = req('GET', url, quien)
    return {x['estudiante']['id']: x for x in js.get('asistencias', [])} if st == 200 else {}


def tarjetas_texto():
    import pymupdf
    r = c.get('/api/calificaciones/por-periodo/tarjetas?curso_id=%d&periodo=1' % SA.id,
              headers={'Authorization': 'Bearer ' + TOK['dir']})
    if r.status_code != 200:
        return 'HTTP %d' % r.status_code
    return ''.join(p.get_text() for p in pymupdf.open(stream=r.content, filetype='pdf'))


def foto_normal():
    """Todo lo que ve un estudiante SIN anulaciones (N y PN)."""
    db.expire_all()
    cn, cp = canonica(N), canonica(PN)
    _, hist = req('GET', '/api/estudiantes/%d/historial' % N.id, 'dir')
    _, rp = req('GET', '/api/asistencia/resumen-periodos/curso/%d' % SA.id, 'dir')
    filas_rp = rp.get('estudiantes') if isinstance(rp, dict) else rp
    return {
        'canonica_N': {k: cn[k] for k in ('dias_lectivos', 'presentes', 'ausencias', 'tardanzas', 'excusas')},
        'canonica_PN': {k: cp[k] for k in ('dias_lectivos', 'presentes', 'ausencias', 'tardanzas', 'excusas')},
        'registro_N': fila_reg(SA, art, N.id), 'registro_PN': fila_reg(PA, None, PN.id),
        'lista_N': [(lista_dia(SA, f, art).get(N.id) or {}).get('asistencia') for f in (D(2026, 10, 5), D(2026, 11, 3))],
        'historial_N': hist.get('asistencia'),
        'resumen_N': next((x for x in (filas_rp or []) if (x.get('estudiante_id') or
                                                          (x.get('estudiante') or {}).get('id')) == N.id), None),
    }


NORMAL_0 = foto_normal()
CAN_R0 = canonica(R)
REG_R0 = fila_reg(SA, art, R.id)
CRUDAS_R0 = marcas_crudas(R.id)
TARJ0 = tarjetas_texto()

# ═════════════ R. Vista previa y confirmación ═════════════
print('\n== R. Retiro desde el 17/10 con anulación de las marcas posteriores ==')
# Pantalla abierta ANTES del retiro (para E2: luego se envía desde ella).
LISTA_VIEJA = lista_dia(SA, D(2026, 11, 17), art)
st, pv = req('GET', '/api/estudiantes/%d/movimiento/preparar?tipo=retiro&desde=2026-10-17' % R.id, 'dir')
posteriores = [m for m in CRUDAS_R0 if m[1] >= D(2026, 10, 17)]
check('R1 vista previa: todas las marcas desde el 17/10 (y ninguna anterior), con autor',
      st == 200 and sorted(x['asistencia_id'] for x in pv['conflictos']) == sorted(m[0] for m in posteriores)
      and all(x.get('registrado_por') == prof.id for x in pv['conflictos']), (st, pv.get('conflictos', [])[:2]))
por_est = {k: sum(1 for m in posteriores if m[2] == k) for k in ('presente', 'ausente', 'tardanza', 'excusa')}
check('R1 resumen por estado: presentes, ausentes, tardanzas y excusas',
      pv.get('anulacion', {}).get('resumen', {}).get('por_estado') == por_est and all(por_est.values()),
      (pv.get('anulacion'), por_est))
check('R1 último día 16/10, puede anular (Dirección) y huella', pv.get('ultimo_dia') == '2026-10-16'
      and pv['anulacion']['puede_anular'] is True and len(pv['anulacion']['huella']) == 64)
HUELLA = pv['anulacion']['huella']
st_s, pv_s = req('GET', '/api/estudiantes/%d/movimiento/preparar?tipo=retiro&desde=2026-10-17' % R.id, 'sec')
check('R1 Secretaría ve la vista previa pero no puede anular', st_s != 200 or pv_s['anulacion']['puede_anular'] is False,
      (st_s, pv_s.get('anulacion') if isinstance(pv_s, dict) else pv_s))
st, js = req('POST', '/api/estudiantes/%d/retiro' % R.id, 'dir', {'desde': '2026-10-17', 'motivo': 'Dejó de asistir'})
check('R2 sin confirmar la anulación: como antes, 409 con conflictos y fecha sugerida; y la opción de anular',
      st == 409 and js.get('error') == 'CONFLICTOS_CON_LA_FECHA' and js.get('fecha_sugerida') == '2026-11-18'
      and js.get('puede_anular') is True and js.get('huella') == HUELLA, js)
base = {'desde': '2026-10-17', 'motivo': 'Dejó de asistir', 'anular_marcas_posteriores': True,
        'motivo_anulacion': 'No asistió desde el 17/10; listas pasadas por error', 'huella_vista_previa': HUELLA}
st, js = req('POST', '/api/estudiantes/%d/retiro' % R.id, 'sec', base)
check('R3 Secretaría no puede anular (403)', st == 403 and js.get('error') == 'SOLO_DIRECCION', js)
st, js = req('POST', '/api/estudiantes/%d/retiro' % R.id, 'dir', dict(base, motivo_anulacion='  '))
check('R3 sin motivo de anulación: 400', st == 400 and js.get('error') == 'MOTIVO_REQUERIDO', js)
st, js = req('POST', '/api/estudiantes/%d/retiro' % R.id, 'dir', dict(base, huella_vista_previa='0' * 64))
check('R3 huella distinta: 409 VISTA_PREVIA_CAMBIO', st == 409 and js.get('error') == 'VISTA_PREVIA_CAMBIO', js)
db.expire_all()
check('R3 nada cambió (ficha activa, marcas intactas, sin anulaciones)',
      db.get(M.Estudiante, R.id).activo and marcas_crudas(R.id) == CRUDAS_R0
      and db.query(M.AnulacionAsistencia).count() == 0)
st, js = req('POST', '/api/estudiantes/%d/retiro' % R.id, 'dir', dict(base, client_request_id='ret-R-1'))
db.expire_all()
e_r = db.get(M.Estudiante, R.id)
anul = db.query(M.AnulacionAsistencia).filter_by(estudiante_id=R.id).one_or_none()
filas_an = db.query(M.AsistenciaAnulada).filter_by(anulacion_id=anul.id).all() if anul else []
check('R4 confirmado: retirado desde el 17/10 (último día 16/10)', st == 200 and not e_r.activo
      and e_r.fecha_retiro == D(2026, 10, 16), js)
check('R4 una anulación con motivo, autor, fecha y huella; una fila por marca',
      anul is not None and anul.registrado_por == dire.id and anul.motivo.startswith('No asistió')
      and anul.registrado_en is not None and anul.huella_vista_previa == HUELLA
      and sorted(f.asistencia_id for f in filas_an) == sorted(m[0] for m in posteriores))
check('R4 marcas originales INTACTAS (id, fecha, estado, autor, observación, curso, materia) — nada borrado',
      marcas_crudas(R.id) == CRUDAS_R0)
check('R4 copia defensiva del estado y autor en cada anulada',
      all((f.estado_original, f.registrado_por_original) == next((m[2], m[3]) for m in CRUDAS_R0 if m[0] == f.asistencia_id)
          for f in filas_an))
check('R4 movimiento de retiro registrado y auditoría', db.query(M.MovimientoEstudiante).filter_by(
    estudiante_id=R.id, tipo='retiro').count() == 1 and db.query(M.LogAuditoria).filter(
    M.LogAuditoria.accion == 'retirar', M.LogAuditoria.registro_id == R.id).count() >= 1)
st, js = req('POST', '/api/estudiantes/%d/retiro' % R.id, 'dir', dict(base, client_request_id='ret-R-1'))
check('R5 reintento con la misma clave: el mismo resultado, sin duplicar', st == 200 and js.get('reintento') is True
      and db.query(M.AnulacionAsistencia).filter_by(estudiante_id=R.id).count() == 1, js)
st, js = req('POST', '/api/estudiantes/%d/retiro' % R.id, 'dir',
             dict(base, client_request_id='ret-R-1', motivo_anulacion='otro'))
check('R5 misma clave con otro contenido: 409', st == 409, js)

# ═════════════ I. Inventario de consumidores ═════════════
print('\n== I. Ningún consumidor cuenta las anuladas ==')
HASTA = D(2026, 10, 16)
esp = esperado(R.id, HASTA)
can = canonica(R)
check('I1 asistencia canónica: solo hasta el 16/10', (can['presentes'], can['ausencias'], can['tardanzas'],
                                                     can['excusas']) == (esp['presente'], esp['ausente'],
                                                                         esp['tardanza'], esp['excusa'])
      and max(can['dias']) <= HASTA, (can['presentes'], esp))
_, bol = req('GET', '/api/boletines/estudiante/%d' % R.id, 'dir')


def buscar(o, clave):
    if isinstance(o, dict):
        for k, v in o.items():
            if k == clave and not isinstance(v, (dict, list)):
                yield v
            yield from buscar(v, clave)
    elif isinstance(o, list):
        for v in o:
            yield from buscar(v, clave)


check('I3 boletín: presentes anuales = los de hasta el 16/10', esp['presente'] in list(buscar(bol, 'presentes')),
      (list(buscar(bol, 'presentes'))[:4], esp))
st, js = req('GET', '/api/asistencia/resumen/%d' % SA.id, 'dir')
nov = json.dumps(js)
check('I4 resumen mensual del curso: 200 y R sin noviembre', st == 200, st)
lst = lista_dia(SA, D(2026, 11, 3), art)
row = lst.get(R.id) or {}
check('I5 lista de asistencia del curso: R «No aplica», sin marca, con la anulada aparte (solo lectura)',
      row.get('estudiante', {}).get('aplica') is False and row.get('asistencia') is None
      and (row['estudiante'].get('asistencia_anulada') or {}).get('estado_original') in ESTADOS
      and row['estudiante']['asistencia_anulada']['motivo'].startswith('No asistió'), row)
st, vr = req('GET', '/api/asistencia/vista-rapida/%d?fecha=2026-11-03' % SA.id, 'dir')
vr_txt = json.dumps(vr)
check('I6 vista rápida: R no aparece con marca ese día', st == 200 and 'Ret Sint' not in vr_txt.split('lista_')[0]
      or all(x.get('id') != R.id for k in ('lista_ausentes', 'lista_tardanzas', 'lista_excusas')
             for b in [vr] + list(vr.get('materias', []) if isinstance(vr, dict) else [])
             for x in (b.get(k) or []) if isinstance(b, dict)), vr_txt[:300])
st, hist = req('GET', '/api/estudiantes/%d/historial' % R.id, 'dir')
tot = sum(esp.values())
check('I7 historial: totales sin anuladas; las anuladas listadas aparte con motivo y autor',
      st == 200 and hist['asistencia']['total'] == tot and len(hist['asistencias_anuladas']) == len(posteriores)
      and all(x['motivo'] and x['anulada_por'] == dire.id for x in hist['asistencias_anuladas']),
      (hist.get('asistencia', {}).get('total'), tot, len(hist.get('asistencias_anuladas', []))))
st, rep_p = req('GET', '/api/reportes/notas/estudiante/%d/periodo/2' % R.id, 'dir')
check('I8 reporte de notas por período: presentes y total sin las anuladas (el reporte cuenta todo el año)',
      st == 200 and rep_p['asistencia']['presentes'] == esp['presente'] and rep_p['asistencia']['total'] == tot,
      (st, rep_p.get('asistencia'), esp, tot))
miembros, ventanas, _h = RV._permanencia_registro(db, SA, col.id)
ests_reg = [m.estudiante for m in miembros]
fr_reg = fila_reg(SA, art, R.id, ests_reg, ventanas)
celdas_post = [v for (clave, ds, vals, *_x) in fr_reg for d, v in zip(ds, vals)
               if D(int(clave[:4]), int(clave[5:]), d) > HASTA]
check('I9 Registro: desde el 17/10 todas sus celdas «-» (No aplica), ninguna anulada visible',
      celdas_post and set(celdas_post) == {'-'}, celdas_post[:8])
vsec = RV.validar_registro_secundaria(db, SA.id, col.id)
check('I10 validador del Registro: ninguna «marca fuera de permanencia» de R',
      not any('Ret Sint' in w for w in vsec.warnings), vsec.warnings[:3])
st, g = req('GET', '/api/dashboard/graficos', 'dir')
check('I11 panel (gráficos): responde', st == 200, st)
txt = tarjetas_texto()
m_tot = re.findall(r'Total: (\d+)', txt)
check('I12 tarjetas de calificaciones: total de R = sus marcas hasta el 16/10',
      str(tot) in m_tot, (m_tot[:6], tot))
for ruta in ('/api/dashboard/alertas', '/api/alertas', '/api/dashboard/direccion', '/api/dashboard/stats'):
    st, _js = req('GET', ruta, 'dir')
    check('I13 %s responde con el filtro activo' % ruta, st == 200, st)
# Vacaciones: las anuladas de R no son conflicto (sin borrar nada: el total de la
# vista previa debe ser exactamente el de las marcas NO anuladas del rango).
db.expire_all()
_rango = (M.Asistencia.fecha >= D(2026, 11, 16), M.Asistencia.fecha <= D(2026, 11, 17))
_todas = db.query(M.Asistencia).filter(*_rango).execution_options(incluir_anuladas=True).count()
_de_r = db.query(M.Asistencia).filter(*_rango, M.Asistencia.estudiante_id == R.id).execution_options(
    incluir_anuladas=True).count()
st, js = req('POST', '/api/vacaciones/vista-previa', 'dir', {'nombre': 'X', 'fecha_inicio': '2026-11-16',
                                                             'fecha_fin': '2026-11-17'})
check('I14 vacaciones: las marcas anuladas no son conflicto (total = las no anuladas del rango)',
      st == 200 and _de_r > 0 and js.get('total_marcas') == _todas - _de_r, (js.get('total_marcas'), _todas, _de_r))
# Protecciones: las anuladas siguen contando como historia.
imp = APP._impacto_eliminacion(db, dire, db.get(M.Estudiante, R.id))
check('I15 protección de borrado: cuenta también las anuladas', imp.get('asistencias') == len(CRUDAS_R0), imp)
st, js = req('POST', '/api/estudiantes/%d/eliminar-por-error' % R.id, 'dir', {'motivo': 'x'})
check('I15 su ficha no se puede eliminar por error (tiene trayectoria)', st == 409, js)
# Formas de consulta sobre los modelos REALES.
ids_an = {f.asistencia_id for f in filas_an}
q_ok = [
    ('query(Asistencia)', {a.id for a in db.query(M.Asistencia).filter_by(estudiante_id=R.id).all()}),
    ('query(A.id)', {i for (i,) in db.query(M.Asistencia.id).filter_by(estudiante_id=R.id).all()}),
    ('relación estudiante.asistencias', {a.id for a in SessionLocal().get(M.Estudiante, R.id).asistencias}),
]
check('I16 formas ORM sobre los modelos reales: ninguna devuelve una anulada',
      all(not (v & ids_an) for _n, v in q_ok), [(n, len(v & ids_an)) for n, v in q_ok])
check('I16 conteo func.count = marcas no anuladas', db.query(APP.func.count(M.Asistencia.id)).filter(
    M.Asistencia.estudiante_id == R.id).scalar() == tot)
check('I16 .count() con incluir_anuladas (protecciones) = todas',
      db.query(M.Asistencia.id).filter(M.Asistencia.estudiante_id == R.id)
      .execution_options(incluir_anuladas=True).count() == len(CRUDAS_R0))

# ═════════════ N. Estudiantes sin anulaciones ═════════════
print('\n== N. Estudiantes SIN anulaciones: comportamiento idéntico ==')
FOTO_N = foto_normal()
for k in NORMAL_0:
    check('N %s idéntico antes y después' % k, NORMAL_0[k] == FOTO_N[k], (NORMAL_0[k], FOTO_N[k]) if k != 'registro_N' else '')

# ═════════════ E. Escrituras ═════════════
print('\n== E. Escrituras fuera de la permanencia o sobre anuladas ==')
st, js = req('POST', '/api/asistencia', 'prof', {'estudiante_id': R.id, 'curso_id': SA.id, 'asignatura_id': art.id,
                                                 'fecha': '2026-11-18', 'estado': 'presente'})
check('E1 marca nueva después del retiro: rechazada y nada escrito', st in (400, 403, 409)
      and marcas_crudas(R.id) == CRUDAS_R0, (st, js))
check('E2 la pantalla abierta antes del retiro lo mostraba activo', (LISTA_VIEJA.get(R.id) or {}).get(
    'estudiante', {}).get('aplica') is True)
st, js = req('POST', '/api/asistencia/masivo', 'prof', {'fecha': '2026-11-17', 'curso_id': SA.id,
                                                        'asignatura_id': art.id,
                                                        'asistencias': [{'estudiante_id': R.id, 'estado': 'presente'}]})
check('E2 enviar desde esa pantalla desactualizada (lote): rechazado, nada escrito', st in (400, 403, 409)
      and marcas_crudas(R.id) == CRUDAS_R0, (st, js))
st, js = req('DELETE', '/api/asistencia/%d?fecha=2026-11-03&asignatura_id=%d' % (R.id, art.id), 'prof')
check('E3 desmarcar una anulada: rechazado y la fila sigue', st in (403, 409) and marcas_crudas(R.id) == CRUDAS_R0, js)

# ═════════════ A. Reactivación ═════════════
print('\n== A. Reactivación: no restaura anuladas ==')
st, js = req('POST', '/api/estudiantes/%d/reactivar' % R.id, 'dir', {'desde': '2026-11-10'})
check('A1 reactivar sobre días con anuladas: rechazado (FECHA_CON_MARCAS_ANULADAS)',
      st == 400 and js.get('error') == 'FECHA_CON_MARCAS_ANULADAS', js)
st, js = req('POST', '/api/estudiantes/%d/reactivar' % R.id, 'dir', {'desde': '2026-11-18'})
can2 = canonica(R)
check('A2 reactivado desde el 18/11: las anuladas siguen sin contar',
      st == 200 and (can2['presentes'], can2['ausencias']) == (esp['presente'], esp['ausente'])
      and db.query(M.AsistenciaAnulada).filter(M.AsistenciaAnulada.revertida_en.isnot(None)).count() == 0,
      (st, js, can2['presentes'], esp))
_, rp = req('GET', '/api/asistencia/resumen-periodos/curso/%d' % SA.id, 'dir')
fr = next((x for x in rp if x.get('estudiante_id') == R.id), {})
check('I2 resumen por períodos del curso (R reactivado; el resumen lista activos): asistencia anual sin '
      'anuladas y P2 sin asistencia', fr.get('total_asistencia') == esp['presente'] + esp['tardanza']
      and (fr.get('periodos', {}).get('p2') or {}).get('asistencia') == 0,
      (fr.get('total_asistencia'), esp, fr.get('periodos', {}).get('p2')))
st, js = req('POST', '/api/estudiantes/%d/retiro' % R.id, 'dir', {'desde': '2026-11-19', 'motivo': 'otra vez'})
check('A3 nuevo retiro sin conflictos: 200; el historial conserva retiro, reactivación y retiro',
      st == 200 and [m.tipo for m in db.query(M.MovimientoEstudiante).filter_by(estudiante_id=R.id)
                     .order_by(M.MovimientoEstudiante.secuencia)] == ['retiro', 'reactivacion', 'retiro'], js)

# ═════════════ V. Reversión ═════════════
print('\n== V. Reversión auditada ==')
st, ls = req('GET', '/api/estudiantes/%d/anulaciones' % R.id, 'dir')
check('V1 vista previa de la reversión: cada anulada con su conflicto (fuera de la permanencia)',
      st == 200 and ls['anuladas'] and all(any(x['codigo'] == 'FUERA_DE_PERMANENCIA'
                                                for x in a['conflictos_reversion']) for a in ls['anuladas']), ls)
uno = ls['anuladas'][0]['asistencia_id']
st, js = req('POST', '/api/estudiantes/%d/anulaciones/revertir' % R.id, 'dir', {'asistencia_ids': [uno], 'motivo': 'x'})
check('V2 revertir con conflicto: 409 y no se revierte nada', st == 409 and js.get('error') == 'CONFLICTOS_REVERSION'
      and db.query(M.AsistenciaAnulada).filter(M.AsistenciaAnulada.revertida_en.isnot(None)).count() == 0, js)
st, js = req('POST', '/api/estudiantes/%d/anulaciones/revertir' % R.id, 'prof', {'asistencia_ids': [uno], 'motivo': 'x'})
check('V3 un profesor no revierte (403)', st == 403, st)
st, js = req('GET', '/api/estudiantes/%d/anulaciones' % R.id, 'dir_otro')
check('V3 Dirección de otro colegio: 404', st == 404, st)

# ═════════════ C. Corrección de la fecha (posterior) ═════════════
print('\n== C. Corregir la fecha de retiro: nada se restaura solo ==')
CR_RC = marcas_crudas(RC.id)
st, pv = req('GET', '/api/estudiantes/%d/movimiento/preparar?tipo=retiro&desde=2026-10-17' % RC.id, 'dir')
st, js = req('POST', '/api/estudiantes/%d/retiro' % RC.id, 'dir', {
    'desde': '2026-10-17', 'motivo': 'retiro', 'anular_marcas_posteriores': True, 'motivo_anulacion': 'sin asistir',
    'huella_vista_previa': pv['anulacion']['huella']})
check('C0 RC retirado desde el 17/10 con anulación', st == 200, js)
st, cv = req('GET', '/api/estudiantes/%d/retiro/corregir/vista-previa?desde=2026-10-24' % RC.id, 'dir')
dentro = sorted(x['fecha'] for x in cv.get('anuladas_que_quedarian_dentro', []))
check('C1 vista previa: el 19-23/10 quedarían dentro de su permanencia (se informan, no se restauran)',
      st == 200 and dentro == ['2026-10-%02d' % d for d in (19, 20, 21, 22, 23)] and not cv['conflictos']
      and cv['periodos_que_dejan_de_cursarse'] == [], cv)
st, js = req('POST', '/api/estudiantes/%d/retiro/corregir' % RC.id, 'dir', {'desde': '2026-10-24',
                                                                           'motivo': 'Su último día fue el 23'})
db.expire_all()
check('C2 corregida: último día 23/10; movimiento «correccion»; las anuladas siguen anuladas',
      st == 200 and db.get(M.Estudiante, RC.id).fecha_retiro == D(2026, 10, 23)
      and db.query(M.AsistenciaAnulada).join(M.AnulacionAsistencia).filter(
          M.AnulacionAsistencia.estudiante_id == RC.id, M.AsistenciaAnulada.revertida_en.is_(None)).count()
      == len([m for m in CR_RC if m[1] >= D(2026, 10, 17)]), js)
check('C2 marcas de RC intactas', marcas_crudas(RC.id) == CR_RC)
c_rc = canonica(RC)
st, ls = req('GET', '/api/estudiantes/%d/anulaciones' % RC.id, 'dir')
sel = [a['asistencia_id'] for a in ls['anuladas'] if a['fecha'] in ('2026-10-19', '2026-10-20')]
fuera = [a['asistencia_id'] for a in ls['anuladas'] if a['fecha'] == '2026-10-27']
check('C3 vista previa: 19-23/10 sin conflictos; 27/10 sigue fuera de la permanencia',
      all(not a['conflictos_reversion'] for a in ls['anuladas'] if a['fecha'] <= '2026-10-23')
      and all(a['conflictos_reversion'] for a in ls['anuladas'] if a['fecha'] >= '2026-10-24'))
st, js = req('POST', '/api/estudiantes/%d/anulaciones/revertir' % RC.id, 'dir',
             {'asistencia_ids': sel + fuera, 'motivo': 'Sí vino esos días'})
check('C4 todo o nada: con una fuera de la permanencia, no se revierte ninguna', st == 409, js)
st, js = req('POST', '/api/estudiantes/%d/anulaciones/revertir' % RC.id, 'dir', {'asistencia_ids': sel, 'motivo': ''})
check('C4 sin motivo: 400', st == 400, js)
st, js = req('POST', '/api/estudiantes/%d/anulaciones/revertir' % RC.id, 'dir',
             {'asistencia_ids': sel, 'motivo': 'Sí vino esos días'})
c_rc2 = canonica(RC)
rev = db.query(M.AsistenciaAnulada).filter(M.AsistenciaAnulada.asistencia_id.in_(sel)).all()
check('C5 solo las elegidas (19 y 20/10) vuelven a contar, con autor, fecha y motivo; el resto sigue anulado',
      st == 200 and c_rc2['con_dato'] == c_rc['con_dato'] + 2 and all(r.revertida_por == dire.id and r.revertida_en
                                                                      and r.motivo_reversion for r in rev)
      and len(rev) == 2, (st, js, c_rc['con_dato'], c_rc2['con_dato']))
check('C5 la fila de anulación no se borra', db.query(M.AsistenciaAnulada).filter(
    M.AsistenciaAnulada.asistencia_id.in_(sel)).count() == 2)

# ═════════════ B. Caso tipo Abraham ═════════════
print('\n== B. Reactivación administrativa para completar notas ==')
st1, _ = req('POST', '/api/estudiantes/%d/retiro' % AB.id, 'dir', {'desde': '2026-10-17', 'motivo': 'Se fue'})
st2, _ = req('POST', '/api/estudiantes/%d/reactivar' % AB.id, 'dir', {'desde': '2026-11-05',
                                                                       'motivo': 'Solo para completar notas'})
for f in (D(2026, 11, 5), D(2026, 11, 9), D(2026, 11, 11)):
    req('POST', '/api/asistencia', 'prof', {'estudiante_id': AB.id, 'curso_id': SA.id, 'asignatura_id': art.id,
                                            'fecha': f.isoformat(), 'estado': 'presente'})
st3, _ = req('POST', '/api/estudiantes/%d/retiro' % AB.id, 'dir', {'desde': '2026-11-12', 'motivo': 'Ya no asiste'})
CR_AB = marcas_crudas(AB.id)
MOV_AB = [(m.id, m.tipo, m.fecha_efectiva) for m in db.query(M.MovimientoEstudiante).filter_by(estudiante_id=AB.id)
          .order_by(M.MovimientoEstudiante.secuencia)]
check('B0 historia como la real: retiro → reactivación administrativa → marcas → nuevo retiro',
      (st1, st2, st3) == (200, 200, 200) and [t for _i, t, _f in MOV_AB] == ['reactivacion', 'retiro'], (st1, st2, st3, MOV_AB))
st, js = req('GET', '/api/estudiantes/%d/retiro/corregir/vista-previa?desde=2026-10-17' % AB.id, 'dir')
check('B1a sin indicar la reactivación administrativa: no se deja sin efecto nada automáticamente '
      '(400 FECHA_ANTERIOR_AL_REGRESO)', st == 400 and js.get('error') == 'FECHA_ANTERIOR_AL_REGRESO', js)
REAC_AB = MOV_AB[0][0]
st, cv = req('GET', '/api/estudiantes/%d/retiro/corregir/vista-previa?desde=2026-10-17&reactivacion_administrativa_id=%d'
             % (AB.id, REAC_AB), 'dir')
check('B1 con la reactivación administrativa indicada: deja sin efecto SOLO esa reactivación y el retiro posterior',
      st == 200 and [m['id'] for m in cv['deja_sin_efecto']] == [MOV_AB[0][0], MOV_AB[1][0]]
      and cv['reactivacion_administrativa']['id'] == REAC_AB, cv)
st, js = req('GET', '/api/estudiantes/%d/retiro/corregir/vista-previa?desde=2026-11-06&reactivacion_administrativa_id=%d'
             % (AB.id, REAC_AB), 'dir')
check('B1b fecha posterior a la reactivación administrativa: rechazada', st == 400
      and js.get('error') == 'FECHA_POSTERIOR_A_LA_REACTIVACION', js)
check('B1 la vista previa trae TODAS las marcas afectadas con fecha, materia, estado y autor',
      all(x['fecha'] and x['asignatura'] and x['estado'] and x['registrado_por_nombre'] for x in cv['conflictos']))
check('B1 marcas del periodo administrativo (5, 9 y 11/11) a anular, con huella',
      sorted(x['fecha'] for x in cv['conflictos']) == ['2026-11-05', '2026-11-09', '2026-11-11'])
check('B1 P2 dejaría de ser cursado y se muestran sus notas registradas (P2=85)',
      cv['periodos_que_dejan_de_cursarse'] == [2] and any(n['periodo'] == 2 and n['valor'] == 85
                                                          for n in cv['notas_en_esos_periodos']), cv)
body = {'desde': '2026-10-17', 'motivo': 'La reactivación fue administrativa (notas); no volvió a clases',
        'anular_marcas_posteriores': True, 'motivo_anulacion': 'Listas pasadas sin que asistiera',
        'huella_vista_previa': cv['huella'], 'reactivacion_administrativa_id': REAC_AB}
st, js = req('POST', '/api/estudiantes/%d/retiro/corregir' % AB.id, 'dir', dict(body, confirmar_periodos_no_cursados=True))
check('B2a sin confirmar expresamente la reactivación administrativa: 409, nada cambia',
      st == 409 and js.get('error') == 'CONFIRMAR_REACTIVACION_ADMINISTRATIVA'
      and db.query(M.MovimientoEstudiante).filter_by(estudiante_id=AB.id).count() == 2, js)
body['confirmar_reactivacion_administrativa'] = True
st, js = req('POST', '/api/estudiantes/%d/retiro/corregir' % AB.id, 'dir', body)
check('B2 sin confirmar los períodos que dejan de cursarse: 409, nada cambia',
      st == 409 and js.get('error') == 'PERIODOS_DEJAN_DE_CURSARSE'
      and db.query(M.MovimientoEstudiante).filter_by(estudiante_id=AB.id).count() == 2, js)
st, js = req('POST', '/api/estudiantes/%d/retiro/corregir' % AB.id, 'dir', dict(body, confirmar_periodos_no_cursados=True))
db.expire_all()
movs = db.query(M.MovimientoEstudiante).filter_by(estudiante_id=AB.id).order_by(M.MovimientoEstudiante.secuencia).all()
import permanencia as PERM  # noqa: E402
tr = PERM.tramos_de(db, db.get(M.Estudiante, AB.id), ano.id)
check('B3 corregida: los 3 movimientos se conservan (más la corrección); la reactivación queda SIN EFECTO',
      st == 200 and [m.tipo for m in movs] == ['reactivacion', 'retiro', 'correccion']
      and PERM.ids_sin_efecto(movs) == {MOV_AB[0][0], MOV_AB[1][0]}, (st, js))
check('B3 permanencia real: un solo tramo hasta el 16/10 (no se finge un regreso)',
      len(tr) == 1 and tr[0].hasta == D(2026, 10, 16), tr)
check('B3 marcas del periodo administrativo anuladas; ninguna fila borrada', marcas_crudas(AB.id) == CR_AB
      and canonica(AB)['con_dato'] == len([m for m in CR_AB if m[1] <= D(2026, 10, 16)]))
cal_ab = db.query(M.CalificacionSecundaria).filter_by(estudiante_id=AB.id, competencia_numero=1).one()
check('B4 notas conservadas tal cual (P1=80, P2=85 en la base)', (cal_ab.p1, cal_ab.p2) == (80, 85))
st, js = req('POST', '/api/estudiantes/%d/retiro/corregir' % AB.id, 'dir', dict(body, confirmar_periodos_no_cursados=True))
check('B5 repetir la corrección: no hay nada que corregir (misma fecha)', st in (400, 409), js)

# ═════════════ RG. Regreso REAL: se conserva ═════════════
print('\n== RG. Retiro → regreso real → retiro: corregir solo el último retiro ==')
RG = est('Regreso', SA, 9)
for i, f in enumerate(dias(D(2026, 10, 1), D(2026, 10, 16))):
    add(M.Asistencia(colegio_id=col.id, estudiante_id=RG.id, curso_id=SA.id, asignatura_id=art.id, fecha=f,
                     estado=ESTADOS[i % len(ESTADOS)], registrado_por=prof.id))
db.commit()
s1, _ = req('POST', '/api/estudiantes/%d/retiro' % RG.id, 'dir', {'desde': '2026-10-17', 'motivo': 'Viaje'})
s2, _ = req('POST', '/api/estudiantes/%d/reactivar' % RG.id, 'dir', {'desde': '2026-11-02', 'motivo': 'Regresó a clases'})
# Tras su regreso real, el docente pasa lista con normalidad.
for i, f in enumerate(dias(D(2026, 11, 2), D(2026, 11, 17))):
    add(M.Asistencia(colegio_id=col.id, estudiante_id=RG.id, curso_id=SA.id, asignatura_id=art.id, fecha=f,
                     estado=ESTADOS[i % len(ESTADOS)], registrado_por=prof.id))
db.commit()
_st, pv = req('GET', '/api/estudiantes/%d/movimiento/preparar?tipo=retiro&desde=2026-11-16' % RG.id, 'dir')
s3, _ = req('POST', '/api/estudiantes/%d/retiro' % RG.id, 'dir', {
    'desde': '2026-11-16', 'motivo': 'Se fue', 'anular_marcas_posteriores': True, 'motivo_anulacion': 'no vino',
    'huella_vista_previa': pv['anulacion']['huella']})
MOV_RG = [m.id for m in db.query(M.MovimientoEstudiante).filter_by(estudiante_id=RG.id)
          .order_by(M.MovimientoEstudiante.secuencia)]
check('RG0 historia: retiro 17/10 (en la ficha) → regreso real 02/11 → retiro 16/11',
      (s1, s2, s3) == (200, 200, 200) and len(MOV_RG) == 2, (s1, s2, s3, MOV_RG))
st, js = req('GET', '/api/estudiantes/%d/retiro/corregir/vista-previa?desde=2026-10-30' % RG.id, 'dir')
check('RG1 sin indicarlo, no se puede «borrar» el regreso real: fecha anterior al regreso → 400',
      st == 400 and js.get('error') == 'FECHA_ANTERIOR_AL_REGRESO', js)
st, cv = req('GET', '/api/estudiantes/%d/retiro/corregir/vista-previa?desde=2026-11-12' % RG.id, 'dir')
check('RG2 corregir al 12/11: deja sin efecto SOLO el último retiro; el primer retiro y el regreso se conservan',
      st == 200 and [m['id'] for m in cv['deja_sin_efecto']] == [MOV_RG[1]] and cv['reactivacion_administrativa'] is None
      and sorted(x['fecha'] for x in cv['conflictos']) == ['2026-11-12', '2026-11-13'], cv)
st, js = req('POST', '/api/estudiantes/%d/retiro/corregir' % RG.id, 'dir', {
    'desde': '2026-11-12', 'motivo': 'Último día real 11/11', 'anular_marcas_posteriores': True,
    'motivo_anulacion': 'no vino', 'huella_vista_previa': cv['huella']})
db.expire_all()
movs_rg = db.query(M.MovimientoEstudiante).filter_by(estudiante_id=RG.id).order_by(M.MovimientoEstudiante.secuencia).all()
tr_rg = PERM.tramos_de(db, db.get(M.Estudiante, RG.id), ano.id)
check('RG3 corregida: el primer retiro y el regreso siguen CON efecto; dos tramos (hasta 16/10 y 02/11–11/11)',
      st == 200 and PERM.ids_sin_efecto(movs_rg) == {MOV_RG[1]}
      and [(t.desde, t.hasta) for t in tr_rg] == [(None, D(2026, 10, 16)), (D(2026, 11, 2), D(2026, 11, 11))],
      (st, js, [(t.desde, t.hasta) for t in tr_rg]))
c_rg = canonica(RG)
check('RG4 su asistencia del regreso (02–11/11) sigue contando', any(D(2026, 11, 2) <= f <= D(2026, 11, 11)
                                                                    for f in c_rg['dias']))

# ═════════════ HM. Historial mixto: administrativa, luego regreso real ═════════════
print('\n== HM. Retiro → reactivación administrativa → retiro → regreso real → retiro ==')
HM = est('Mixto', SA, 10)
add(M.CalificacionSecundaria(colegio_id=col.id, estudiante_id=HM.id, asignatura_id=art.id, ano_escolar_id=ano.id,
                             competencia_numero=1, p1=75, p2=88))
for i, f in enumerate(dias(D(2026, 10, 1), D(2026, 10, 16))):
    add(M.Asistencia(colegio_id=col.id, estudiante_id=HM.id, curso_id=SA.id, asignatura_id=art.id, fecha=f,
                     estado=ESTADOS[i % len(ESTADOS)], registrado_por=prof.id))
db.commit()
h = [req('POST', '/api/estudiantes/%d/retiro' % HM.id, 'dir', {'desde': '2026-10-17', 'motivo': 'Se fue'})[0],
     req('POST', '/api/estudiantes/%d/reactivar' % HM.id, 'dir', {'desde': '2026-10-26',
                                                                 'motivo': 'Solo para completar notas'})[0],
     req('POST', '/api/estudiantes/%d/retiro' % HM.id, 'dir', {'desde': '2026-10-28', 'motivo': 'Notas listas'})[0],
     req('POST', '/api/estudiantes/%d/reactivar' % HM.id, 'dir', {'desde': '2026-11-02', 'motivo': 'Regresó a clases'})[0]]
for i, f in enumerate(dias(D(2026, 11, 2), D(2026, 11, 17))):       # regreso real: asiste
    add(M.Asistencia(colegio_id=col.id, estudiante_id=HM.id, curso_id=SA.id, asignatura_id=art.id, fecha=f,
                     estado=ESTADOS[i % len(ESTADOS)], registrado_por=prof.id))
db.commit()
_st, pv = req('GET', '/api/estudiantes/%d/movimiento/preparar?tipo=retiro&desde=2026-11-16' % HM.id, 'dir')
h.append(req('POST', '/api/estudiantes/%d/retiro' % HM.id, 'dir', {
    'desde': '2026-11-16', 'motivo': 'Se fue', 'anular_marcas_posteriores': True, 'motivo_anulacion': 'no vino',
    'huella_vista_previa': pv['anulacion']['huella']})[0])


def foto_hm():
    db.expire_all()
    return (
        [(m.id, m.tipo, m.secuencia, m.fecha_efectiva, m.detalle) for m in db.query(M.MovimientoEstudiante)
         .filter_by(estudiante_id=HM.id).order_by(M.MovimientoEstudiante.secuencia)],
        marcas_crudas(HM.id),
        sorted((a.asistencia_id, a.revertida_en) for a in db.query(M.AsistenciaAnulada).join(M.AnulacionAsistencia)
               .filter(M.AnulacionAsistencia.estudiante_id == HM.id)),
        [(c.competencia_numero, c.p1, c.p2) for c in db.query(M.CalificacionSecundaria).filter_by(estudiante_id=HM.id)],
        db.get(M.Estudiante, HM.id).fecha_retiro,
    )


FOTO_HM = foto_hm()
movs_hm = [m for m in FOTO_HM[0]]
reacs = [m[0] for m in movs_hm if m[1] == 'reactivacion']
check('HM0 historia registrada: 5 pasos (el primer retiro en la ficha) y dos reactivaciones',
      h == [200] * 5 and [m[1] for m in movs_hm] == ['reactivacion', 'retiro', 'reactivacion', 'retiro'], (h, movs_hm))
st, js = req('GET', '/api/estudiantes/%d/retiro/corregir/vista-previa?desde=2026-10-17&reactivacion_administrativa_id=%d'
             % (HM.id, reacs[0]), 'dir')
check('HM1 vista previa con la PRIMERA reactivación (administrativa) y un regreso real después: rechazada '
      '(409 HISTORIAL_REQUIERE_REVISION), sin anular en bloque',
      st == 409 and js.get('error') == 'HISTORIAL_REQUIERE_REVISION' and 'revisión individual' in js.get('message', ''), js)
st, js = req('POST', '/api/estudiantes/%d/retiro/corregir' % HM.id, 'dir', {
    'desde': '2026-10-17', 'motivo': 'x', 'reactivacion_administrativa_id': reacs[0],
    'confirmar_reactivacion_administrativa': True, 'anular_marcas_posteriores': True, 'motivo_anulacion': 'x',
    'huella_vista_previa': 'x', 'confirmar_periodos_no_cursados': True})
check('HM2 confirmar igualmente: 409 HISTORIAL_REQUIERE_REVISION', st == 409
      and js.get('error') == 'HISTORIAL_REQUIERE_REVISION', js)
check('HM3 no cambió nada: movimientos, marcas, anulaciones, notas y fecha de retiro idénticos', foto_hm() == FOTO_HM)

# ═════════════ K. Notas ═════════════
print('\n== K. Notas: pendiente de período cursado sí; no cursado no ==')
st, js = req('POST', '/api/periodos/permiso-temporal', 'dir', {'profesor_id': prof.id, 'curso_id': SA.id,
                                                              'asignatura_id': art.id, 'periodo': 1, 'horas': 24,
                                                              'motivo': 'sintético'})
st, js = req('POST', '/api/calificaciones-secundaria', 'prof', {'estudiante_id': R.id, 'asignatura_id': art.id,
                                                                'curso_id': SA.id, 'competencia_numero': 2, 'p1': 77})
db.expire_all()
check('K1 retirado: nota pendiente de P1 (cursado) se digita con el permiso, sin reactivarlo',
      st == 200 and db.query(M.CalificacionSecundaria).filter_by(estudiante_id=R.id, competencia_numero=2).one().p1 == 77
      and not db.get(M.Estudiante, R.id).activo, js)
req('POST', '/api/periodos/permiso-temporal', 'dir', {'profesor_id': prof.id, 'curso_id': SA.id,
                                                     'asignatura_id': art.id, 'periodo': 2, 'horas': 24, 'motivo': 's'})
st, js = req('POST', '/api/calificaciones-secundaria', 'prof', {'estudiante_id': AB.id, 'asignatura_id': art.id,
                                                                'curso_id': SA.id, 'competencia_numero': 1, 'p2': 90})
db.expire_all()
check('K2 período NO cursado (P2 de AB tras la corrección): no se habilita, ni con permiso',
      st == 403 and db.query(M.CalificacionSecundaria).filter_by(estudiante_id=AB.id, competencia_numero=1).one().p2 == 85,
      (st, js))

# ═════════════ P. Primaria ═════════════
print('\n== P. Primaria ==')
CR_PR = marcas_crudas(PR.id)
st, pv = req('GET', '/api/estudiantes/%d/movimiento/preparar?tipo=retiro&desde=2026-10-17' % PR.id, 'dir')
st, js = req('POST', '/api/estudiantes/%d/retiro' % PR.id, 'dir', {
    'desde': '2026-10-17', 'motivo': 'retiro', 'anular_marcas_posteriores': True, 'motivo_anulacion': 'no asistió',
    'huella_vista_previa': pv['anulacion']['huella']})
c_pr = canonica(PR)
check('P1 Primaria: retirado con anulación; canónica solo hasta el 16/10; marcas intactas',
      st == 200 and max(c_pr['dias']) <= D(2026, 10, 16) and marcas_crudas(PR.id) == CR_PR, js)
mp, vp, _h = RV._permanencia_registro(db, PA, col.id)
fp = fila_reg(PA, None, PR.id, [m.estudiante for m in mp], vp)
post = [v for (clave, ds, vals, *_x) in fp for d, v in zip(ds, vals) if D(int(clave[:4]), int(clave[5:]), d) > D(2026, 10, 16)]
check('P2 Registro de Primaria: «-» desde el 17/10', post and set(post) == {'-'}, post[:6])
st, js = req('POST', '/api/asistencia', 'tit', {'estudiante_id': PR.id, 'curso_id': PA.id, 'fecha': '2026-11-18',
                                                'estado': 'presente'})
check('P3 Primaria: marca después del retiro rechazada y nada escrito', st in (400, 403, 409)
      and marcas_crudas(PR.id) == CR_PR, (st, js))

# ═════════════ T. Traslados ═════════════
print('\n== T. Traslados sin cambios ==')
st, js = req('POST', '/api/estudiantes/%d/traslado' % TR.id, 'dir', {
    'curso_destino_id': SB.id, 'desde': '2026-10-17', 'anular_marcas_posteriores': True,
    'motivo_anulacion': 'x', 'huella_vista_previa': 'x'})
check('T1 traslado con marcas posteriores en el origen: 409 como siempre, sin opción de anular',
      st == 409 and js.get('error') == 'CONFLICTOS_CON_LA_FECHA' and 'puede_anular' not in js
      and db.query(M.AnulacionAsistencia).filter_by(estudiante_id=TR.id).count() == 0, js)

# ═════════════ G. Guarda de código ═════════════
print('\n== G. Nadie lee `asistencias` fuera del ORM ==')
malos = []
for raiz, _d, archivos in os.walk(BK):
    if any(x in raiz for x in ('tools', '__pycache__', 'venv', 'node_modules')):
        continue
    for a in archivos:
        if not a.endswith('.py'):
            continue
        for i, linea in enumerate(open(os.path.join(raiz, a), encoding='utf-8', errors='ignore'), 1):
            l = linea.strip()
            if l.startswith('#'):
                continue
            if re.search(r'asistencias\.(any|has)\(|Asistencia\.__table__', l) or (
                    re.search(r'(FROM|JOIN|UPDATE|DELETE FROM)\s+asistencias\b', l, re.I)
                    and 'CREATE' not in l.upper()):
                malos.append('%s:%d %s' % (a, i, l[:100]))
check('G1 sin SQL directo, Core ni .any()/.has() sobre asistencias en el backend', not malos, malos)

# ═════════════ X. Concurrencia (solo PostgreSQL) ═════════════
print('\n== X. Concurrencia real ==')
if engine.dialect.name != 'postgresql':
    print('  (omitida: la concurrencia se verifica en PostgreSQL temporal)')
else:
    def _req_hilo(m, url, k, body, out, clave):
        try:
            cl = TestClient(APP.app)
            r_ = cl.request(m, url, headers={'Authorization': 'Bearer ' + TOK[k]}, json=body)
            out[clave] = (r_.status_code, r_.json())
        except Exception as exc:  # noqa: BLE001
            out[clave] = ('excepcion', repr(exc)[:300])

    _orig_conf = APP._conflictos_movimiento
    _orig_bloq = APP._bloquear_ficha

    def _conf_lento(*a, **k):
        r_ = _orig_conf(*a, **k)
        if a[3] == 'retiro':
            time.sleep(1.5)        # ensancha la ventana entre comprobar y escribir
        return r_

    def escenario(control, e, dia_marca):
        APP._conflictos_movimiento = _conf_lento
        if control:
            APP._bloquear_ficha = lambda *a, **k: None
        try:
            _st, pv_ = req('GET', '/api/estudiantes/%d/movimiento/preparar?tipo=retiro&desde=2026-11-16' % e.id, 'dir')
            out = {}
            ta = threading.Thread(target=_req_hilo, args=('POST', '/api/estudiantes/%d/retiro' % e.id, 'dir', {
                'desde': '2026-11-16', 'motivo': 'x', 'anular_marcas_posteriores': True, 'motivo_anulacion': 'x',
                'huella_vista_previa': pv_['anulacion']['huella']}, out, 'ret'))
            tb = threading.Thread(target=_req_hilo, args=('POST', '/api/asistencia', 'prof', {
                'estudiante_id': e.id, 'curso_id': SA.id, 'asignatura_id': art.id, 'fecha': dia_marca,
                'estado': 'presente'}, out, 'asis'))
            ta.start()
            time.sleep(0.5)
            tb.start()
            ta.join()
            tb.join()
            db.expire_all()
            ee = db.get(M.Estudiante, e.id)
            nueva = db.query(M.Asistencia).filter(M.Asistencia.estudiante_id == e.id,
                                                   M.Asistencia.fecha == D.fromisoformat(dia_marca)).first()
            return (not ee.activo), nueva is not None, out
        finally:
            APP._conflictos_movimiento = _orig_conf
            APP._bloquear_ficha = _orig_bloq

    # CO tiene marcas hasta el 17/11; la carrera usa el 18/11 (hoy), aún sin marca.
    CO2 = add(M.Estudiante(colegio_id=col.id, nombre='Conc2', apellido='Sint', matricula='RETR-Conc2', curso_id=SA.id,
                           no_lista=7, activo=True, condicion='activo', fecha_ingreso=D(2026, 8, 20)))
    for i, f in enumerate(dias(D(2026, 10, 1), D(2026, 11, 17))):
        add(M.Asistencia(colegio_id=col.id, estudiante_id=CO2.id, curso_id=SA.id, asignatura_id=art.id, fecha=f,
                         estado='presente', registrado_por=prof.id))
    db.commit()
    ret_c, nueva_c, out_c = escenario(True, CO2, '2026-11-18')
    print('    CONTROL sin bloqueo: retiro aplicado=%s, marca nueva fuera de la permanencia=%s' % (ret_c, nueva_c))
    check('X1 CONTROL: sin el bloqueo la prueba SÍ detecta la carrera (retiro aplicado + marca nueva del 18/11)',
          ret_c and nueva_c, out_c)
    ret_r, nueva_r, out_r = escenario(False, CO, '2026-11-18')
    check('X2 retiro con anulación y una lista del mismo estudiante a la vez: nunca ambos '
          '(la lista espera el bloqueo y se rechaza, o la vista previa cambió y no se aplica nada)',
          (ret_r and not nueva_r) or (not ret_r and nueva_r and out_r['ret'][1].get('error') == 'VISTA_PREVIA_CAMBIO'),
          (ret_r, nueva_r, out_r))
    # Doble confirmación simultánea con la misma clave.
    E3 = add(M.Estudiante(colegio_id=col.id, nombre='Conc3', apellido='Sint', matricula='RETR-Conc3', curso_id=SA.id,
                          no_lista=8, activo=True, condicion='activo', fecha_ingreso=D(2026, 8, 20)))
    for f in dias(D(2026, 11, 2), D(2026, 11, 17)):
        add(M.Asistencia(colegio_id=col.id, estudiante_id=E3.id, curso_id=SA.id, asignatura_id=art.id, fecha=f,
                         estado='ausente', registrado_por=prof.id))
    db.commit()
    _st, pv3 = req('GET', '/api/estudiantes/%d/movimiento/preparar?tipo=retiro&desde=2026-11-02' % E3.id, 'dir')
    cuerpo = {'desde': '2026-11-02', 'motivo': 'x', 'anular_marcas_posteriores': True, 'motivo_anulacion': 'x',
              'huella_vista_previa': pv3['anulacion']['huella'], 'client_request_id': 'doble-1'}
    out = {}
    hs = [threading.Thread(target=_req_hilo, args=('POST', '/api/estudiantes/%d/retiro' % E3.id, 'dir', cuerpo, out, i))
          for i in range(3)]
    [h.start() for h in hs]
    [h.join() for h in hs]
    db.expire_all()
    check('X3 tres confirmaciones idénticas a la vez: 1 movimiento y 1 anulación',
          db.query(M.MovimientoEstudiante).filter_by(estudiante_id=E3.id).count() == 1
          and db.query(M.AnulacionAsistencia).filter_by(estudiante_id=E3.id).count() == 1
          and all(v[0] == 200 for v in out.values()), out)

    # ── Reversión frente a crear vacaciones y frente a «No hubo clase» ──
    # Un curso propio (SC) con un único estudiante por caso y marcas en fechas
    # donde nadie más tiene listas: así el único conflicto posible es la marca
    # que se revierte. Anulada por retiro desde el 18/11 y luego la fecha se
    # corrige al 20/11: esas marcas quedan dentro de la permanencia y son
    # revertibles (no se restauran solas).
    SC = add(M.Curso(colegio_id=col.id, nombre='C', grado_id=gs.id, ano_escolar_id=ano.id, activo=True))
    add(M.AsignacionProfesor(colegio_id=col.id, profesor_id=prof.id, curso_id=SC.id, asignatura_id=art.id,
                             ano_escolar_id=ano.id, activo=True))
    for dia in ('Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes'):
        add(M.Horario(colegio_id=col.id, profesor_id=prof.id, curso_id=SC.id, asignatura_id=art.id, dia=dia,
                      hora_inicio='10:00', hora_fin='11:00', tipo_bloque='clase', activo=True))
    db.commit()

    def revertible(nombre, n, fecha):
        e = add(M.Estudiante(colegio_id=col.id, nombre=nombre, apellido='Sint', matricula='RETR-' + nombre,
                             curso_id=SC.id, no_lista=n, activo=True, condicion='activo', fecha_ingreso=D(2026, 8, 20)))
        a = add(M.Asistencia(colegio_id=col.id, estudiante_id=e.id, curso_id=SC.id, asignatura_id=art.id,
                             fecha=fecha, estado='presente', registrado_por=prof.id))
        db.commit()
        _s, p_ = req('GET', '/api/estudiantes/%d/movimiento/preparar?tipo=retiro&desde=%s' % (e.id, fecha.isoformat()),
                     'dir')
        s1_, _ = req('POST', '/api/estudiantes/%d/retiro' % e.id, 'dir', {
            'desde': fecha.isoformat(), 'motivo': 'x', 'anular_marcas_posteriores': True, 'motivo_anulacion': 'x',
            'huella_vista_previa': p_['anulacion']['huella']})
        s2_, _ = req('POST', '/api/estudiantes/%d/retiro/corregir' % e.id, 'dir',
                     {'desde': (fecha + dt.timedelta(days=2)).isoformat(), 'motivo': 'fecha real posterior'})
        return e, a.id, (s1_, s2_)

    _orig_cr = APP._conflictos_reversion
    _orig_bc = APP._bloquear_colegio

    def _cr_lento(*a, **k):
        r_ = _orig_cr(*a, **k)
        time.sleep(1.5)            # la reversión ya revisó conflictos y aún no escribe
        return r_

    def carrera(control, e, aid, otra):
        APP._conflictos_reversion = _cr_lento
        if control:
            APP._bloquear_colegio = lambda *a, **k: None
        try:
            out = {}
            ta = threading.Thread(target=_req_hilo, args=('POST', '/api/estudiantes/%d/anulaciones/revertir' % e.id,
                                                          'dir', {'asistencia_ids': [aid], 'motivo': 'sí vino'},
                                                          out, 'rev'))
            tb = threading.Thread(target=_req_hilo, args=otra + (out, 'otra'))
            ta.start()
            time.sleep(0.5)
            tb.start()
            ta.join()
            tb.join()
            db.expire_all()
            revertida = db.query(M.AsistenciaAnulada).filter(M.AsistenciaAnulada.asistencia_id == aid,
                                                             M.AsistenciaAnulada.revertida_en.isnot(None)).count() == 1
            return revertida, out
        finally:
            APP._conflictos_reversion = _orig_cr
            APP._bloquear_colegio = _orig_bc

    # X4 · vacaciones que cubren el día de la marca revertida.
    # Fechas sin ninguna otra lista en el colegio (X1/X2 dejan marcas el 18/11).
    for control, nombre, n, f in ((True, 'RevVacC', 21, D(2026, 11, 20)), (False, 'RevVacR', 22, D(2026, 11, 24))):
        e, aid, sts = revertible(nombre, n, f)
        rev, out = carrera(control, e, aid, ('POST', '/api/vacaciones', 'dir',
                                             {'nombre': 'Vac %s' % nombre, 'fecha_inicio': f.isoformat(),
                                              'fecha_fin': f.isoformat()}))
        vac = db.query(M.RangoVacaciones).filter(M.RangoVacaciones.nombre == 'Vac %s' % nombre,
                                                 M.RangoVacaciones.activo == True).count() == 1  # noqa: E712
        if control:
            print('    CONTROL sin bloqueo: marca revertida=%s y vacaciones creadas=%s' % (rev, vac))
            check('X4 CONTROL: sin el bloqueo SÍ aparece la carrera (marca revertida dentro de unas vacaciones)',
                  sts == (200, 200) and rev and vac, (sts, out))
        else:
            check('X4 reversión y vacaciones del mismo día a la vez: nunca ambas (las vacaciones esperan el bloqueo '
                  'del colegio y ven la marca: 409)', sts == (200, 200) and rev and not vac
                  and out['otra'][0] == 409, (sts, rev, vac, out))
        # se quitan para no interferir con lo siguiente (datos sintéticos)
        for r_ in db.query(M.RangoVacaciones).filter(M.RangoVacaciones.nombre == 'Vac %s' % nombre).all():
            req('DELETE', '/api/vacaciones/%d' % r_.id, 'dir')

    # X5 · «No hubo clase» de esa clase ese día.
    for control, nombre, n, f in ((True, 'RevS1C', 23, D(2026, 11, 16)), (False, 'RevS1R', 24, D(2026, 11, 17))):
        e, aid, sts = revertible(nombre, n, f)
        rev, out = carrera(control, e, aid, ('POST', '/api/sesiones-no-impartidas', 'prof', {
            'curso_id': SC.id, 'asignatura_id': art.id, 'fecha': f.isoformat(), 'motivo_codigo': 'SUSP_CURSO'}))
        s1 = db.query(M.SesionNoImpartida).filter_by(curso_id=SC.id, asignatura_id=art.id, fecha=f, activo=True).count() == 1
        if control:
            print('    CONTROL sin bloqueo: marca revertida=%s y «No hubo clase»=%s' % (rev, s1))
            check('X5 CONTROL: sin el bloqueo SÍ aparece la carrera (marca revertida en una clase «no impartida»)',
                  sts == (200, 200) and rev and s1, (sts, out))
        else:
            check('X5 reversión y «No hubo clase» de esa clase a la vez: nunca ambas (la declaración espera el '
                  'bloqueo del colegio y ve la marca: 409)', sts == (200, 200) and rev and not s1
                  and out['otra'][0] == 409, (sts, rev, s1, out))

print('\nRESULTADO RET-R RETIRO RETROACTIVO (%s): %d PASARON / %d FALLARON'
      % (engine.dialect.name, sum(1 for _, ok in RES if ok), sum(1 for _, ok in RES if not ok)))
db.close()
sys.exit(0 if all(ok for _, ok in RES) else 1)
