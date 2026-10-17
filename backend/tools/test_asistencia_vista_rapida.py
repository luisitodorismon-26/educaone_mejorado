# -*- coding: utf-8 -*-
"""
EducaOne — ASIS-DASH-1: vista rápida de asistencia para Dirección/Coordinación.

GET /api/asistencia/vista-rapida/{curso_id}?fecha=YYYY-MM-DD

    · Primaria: toma diaria del curso (asignatura NULL); registrada / parcial /
      sin asistencia; P/A/T/E y listas. Sin marcas NUNCA es "presente".
    · Secundaria: una entrada por asignatura con clase ese día según el
      horario, con profesor y horas; cada materia con su propia toma.
    · Permisos: solo direccion/coordinador; coordinador de nivel fijo no cruza
      de nivel; otro colegio = 404.
    · SOLO LECTURA: ningún INSERT/UPDATE/DELETE al consultar.

Base temporal aislada. Nunca producción.

Uso:
    cd backend
    python tools/test_asistencia_vista_rapida.py
"""
import os
import sys
from datetime import date

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(BK, "tools"))

from test_utils import aislar_base_de_datos  # noqa: E402

TMP = aislar_base_de_datos('asis_dash_1')

from database import engine, SessionLocal  # noqa: E402
from test_utils import verificar_engine_aislado  # noqa: E402

verificar_engine_aislado(engine, TMP)

from sqlalchemy import event  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import models as M  # noqa: E402
import app as APP  # noqa: E402
from auth import create_token  # noqa: E402

M.Base.metadata.create_all(bind=engine)
client = TestClient(APP.app)
RES = []


def check(nombre, ok, detalle=''):
    RES.append((nombre, bool(ok)))
    print(('  OK  ' if ok else '  FALLA ') + nombre + ('' if ok else '  -> ' + str(detalle)[:300]))


HOY = date(2026, 10, 14)          # miércoles
db = SessionLocal()


def colegio(nombre):
    c = M.Colegio(nombre=nombre, codigo=nombre.lower(), activo=True)
    db.add(c)
    db.flush()
    ano = M.AnoEscolar(colegio_id=c.id, nombre='2026-2027', activo=True, cerrado=False,
                       fecha_inicio=date(2026, 9, 7), fecha_fin=date(2027, 6, 25))
    db.add(ano)
    db.flush()
    return c, ano


def usuario(col, username, role, nivel=None, nombre='U'):
    u = M.Usuario(colegio_id=col.id, username=username, password_hash='x', nombre=nombre,
                  apellido='Prueba', role=role, activo=True, must_change_password=False,
                  token_version=0, nivel_asignado=nivel)
    db.add(u)
    db.flush()
    return u


def curso(col, ano, nombre_grado, nivel, n_est=4):
    g = M.Grado(colegio_id=col.id, nombre=nombre_grado, nivel=nivel, orden=4, activo=True)
    db.add(g)
    db.flush()
    c = M.Curso(colegio_id=col.id, nombre='A', grado_id=g.id, ano_escolar_id=ano.id, activo=True)
    db.add(c)
    db.flush()
    ests = [M.Estudiante(colegio_id=col.id, matricula='%s-%d-%d' % (nivel[0], c.id, i),
                         nombre='Est%d' % (i + 1), apellido='%s%d' % (nivel[:3].title(), c.id),
                         curso_id=c.id, activo=True, no_lista=i + 1) for i in range(n_est)]
    db.add_all(ests)
    db.flush()
    return c, ests


def marcar(col, c, est, estado, asig=None, fecha=HOY):
    db.add(M.Asistencia(colegio_id=col.id, estudiante_id=est.id, curso_id=c.id,
                        asignatura_id=asig.id if asig else None, fecha=fecha, estado=estado))


COL, ANO = colegio('VR1')
OTRO, ANO2 = colegio('VR2')
DIR = usuario(COL, 'vr_dir', 'direccion')
COORD_P = usuario(COL, 'vr_cp', 'coordinador', 'primaria')
COORD_S = usuario(COL, 'vr_cs', 'coordinador', 'secundaria')
PROF_TIT = usuario(COL, 'vr_tit', 'profesor', nombre='Titular')
PROF_IN = usuario(COL, 'vr_in', 'profesor', nombre='Juan')
PROF_MA = usuario(COL, 'vr_ma', 'profesor', nombre='Maria')
SECRE = usuario(COL, 'vr_sec', 'secretaria')
DIR_OTRO = usuario(OTRO, 'vr_dir2', 'direccion')

# Primaria: P1 completa con P/A/T/E, P2 sin ninguna marca, P3 parcial.
P1, E1 = curso(COL, ANO, '4to Primaria', 'primaria')
P2, E2 = curso(COL, ANO, '5to Primaria', 'primaria')
P3, E3 = curso(COL, ANO, '6to Primaria', 'primaria')
le = M.Asignatura(colegio_id=COL.id, nombre='Lengua', codigo='LEP', area='X', activo=True)
db.add(le)
db.flush()
db.add(M.AsignacionProfesor(colegio_id=COL.id, profesor_id=PROF_TIT.id, curso_id=P1.id,
                            asignatura_id=le.id, ano_escolar_id=ANO.id, activo=True, es_titular=True))
for est, estado in zip(E1, ('presente', 'ausente', 'tardanza', 'excusa')):
    marcar(COL, P1, est, estado)
marcar(COL, P3, E3[0], 'presente')

# Secundaria: S1 con Inglés (registrada) y Matemática (sin asistencia) hoy,
# profesor distinto por materia; S2 con ambas registradas; S3 sin clases hoy.
S1, ES1 = curso(COL, ANO, '3ro Secundaria', 'secundaria')
S2, ES2 = curso(COL, ANO, '2do Secundaria', 'secundaria')
S3, ES3 = curso(COL, ANO, '1ro Secundaria', 'secundaria')
ing = M.Asignatura(colegio_id=COL.id, nombre='Inglés', codigo='IN', area='X', activo=True)
mat = M.Asignatura(colegio_id=COL.id, nombre='Matemática', codigo='MA', area='X', activo=True)
db.add_all([ing, mat])
db.flush()
for c in (S1, S2):
    db.add(M.Horario(colegio_id=COL.id, profesor_id=PROF_IN.id, curso_id=c.id, asignatura_id=ing.id,
                     dia='Miércoles', hora_inicio='08:00', hora_fin='08:45', tipo_bloque='clase', activo=True))
    db.add(M.Horario(colegio_id=COL.id, profesor_id=PROF_MA.id, curso_id=c.id, asignatura_id=mat.id,
                     dia='Miércoles', hora_inicio='09:00', hora_fin='09:45', tipo_bloque='clase', activo=True))
db.add(M.Horario(colegio_id=COL.id, profesor_id=PROF_MA.id, curso_id=S3.id, asignatura_id=mat.id,
                 dia='Lunes', hora_inicio='09:00', hora_fin='09:45', tipo_bloque='clase', activo=True))
for est, estado in zip(ES1, ('presente', 'presente', 'ausente', 'tardanza')):
    marcar(COL, S1, est, estado, ing)
for est in ES2:
    marcar(COL, S2, est, 'presente', ing)
    marcar(COL, S2, est, 'ausente' if est is ES2[0] else 'presente', mat)
POTRO, _ = curso(OTRO, ANO2, '4to Primaria', 'primaria')
db.commit()


def h(u):
    return {'Authorization': 'Bearer ' + create_token(u)}


# Detector de escrituras durante las consultas.
ESCRITURAS = []


@event.listens_for(engine, 'before_cursor_execute')
def _espia(conn, cursor, statement, params, context, executemany):
    if statement.lstrip().split(' ', 1)[0].upper() in ('INSERT', 'UPDATE', 'DELETE'):
        ESCRITURAS.append(statement[:80])


def vista(c, u, fecha=HOY):
    return client.get('/api/asistencia/vista-rapida/%d?fecha=%s' % (c.id, fecha.isoformat()), headers=h(u))


print("\n=== PRIMARIA ===")
r = vista(P1, DIR)
j = r.json()
p = j.get('primaria') or {}
check('VR-01 Primaria con P/A/T/E: registrada, 1 P / 1 A / 1 T / 1 E',
      r.status_code == 200 and p.get('estado') == 'registrada'
      and (p['presentes'], p['ausentes'], p['tardanzas'], p['excusas']) == (1, 1, 1, 1), j)
check('VR-02 listas de ausentes, tardanzas y excusas con el estudiante correcto',
      [x['nombre'] for x in p.get('lista_ausentes', [])] == [E1[1].nombre_completo]
      and [x['nombre'] for x in p.get('lista_tardanzas', [])] == [E1[2].nombre_completo]
      and [x['nombre'] for x in p.get('lista_excusas', [])] == [E1[3].nombre_completo], p)
check('VR-03 Primaria informa el titular', p.get('titular') == PROF_TIT.nombre_completo, p.get('titular'))
p2 = vista(P2, DIR).json().get('primaria') or {}
check('VR-04 Primaria SIN marcas: "sin_asistencia", 0 presentes (nunca asume presentes)',
      p2.get('estado') == 'sin_asistencia' and p2.get('presentes') == 0 and p2.get('sin_marcar') == 4, p2)
p3 = vista(P3, DIR).json().get('primaria') or {}
check('VR-05 Primaria parcial: "parcial" con 1 presente y 3 sin marcar',
      p3.get('estado') == 'parcial' and p3.get('presentes') == 1 and p3.get('sin_marcar') == 3, p3)
check('VR-06 Primaria no incluye bloque de Secundaria', 'secundaria' not in vista(P1, DIR).json(), '')

print("\n=== SECUNDARIA ===")
s1 = (vista(S1, DIR).json().get('secundaria') or {}).get('sesiones', [])
por = {s['asignatura']: s for s in s1}
check('VR-07 dos materias hoy: Inglés registrada (2P/1A/1T) y Matemática sin asistencia',
      por.get('Inglés', {}).get('estado') == 'registrada'
      and (por['Inglés']['presentes'], por['Inglés']['ausentes'], por['Inglés']['tardanzas']) == (2, 1, 1)
      and por.get('Matemática', {}).get('estado') == 'sin_asistencia', s1)
check('VR-08 profesor distinto por asignatura y horas trazables',
      por['Inglés']['profesor'] == PROF_IN.nombre_completo
      and por['Matemática']['profesor'] == PROF_MA.nombre_completo
      and por['Inglés']['bloques'][0]['hora_inicio'] == '08:00', [(s['asignatura'], s['profesor']) for s in s1])
check('VR-09 faltar en Inglés NO marca ausente en Matemática (no hay "ausente del día")',
      por['Matemática']['ausentes'] == 0 and por['Matemática']['sin_marcar'] == 4
      and 'primaria' not in vista(S1, DIR).json(), por['Matemática'])
s2 = (vista(S2, DIR).json().get('secundaria') or {}).get('sesiones', [])
check('VR-10 ambas registradas: Inglés 4P y Matemática 3P/1A',
      {s['asignatura']: (s['estado'], s['presentes'], s['ausentes']) for s in s2}
      == {'Inglés': ('registrada', 4, 0), 'Matemática': ('registrada', 3, 1)}, s2)
s3 = vista(S3, DIR).json().get('secundaria') or {}
check('VR-11 curso sin clases programadas hoy: lo dice y no inventa sesiones',
      s3.get('sin_clases_programadas') is True and s3.get('sesiones') == [], s3)

print("\n=== PERMISOS ===")
check('VR-12 coordinador de Primaria NO consulta Secundaria (403)', vista(S1, COORD_P).status_code == 403, '')
check('VR-13 coordinador de Secundaria NO consulta Primaria (403)', vista(P1, COORD_S).status_code == 403, '')
check('VR-14 coordinador de Primaria SÍ consulta Primaria', vista(P1, COORD_P).status_code == 200, '')
check('VR-15 curso de otro colegio: 404', vista(POTRO, DIR).status_code == 404, vista(POTRO, DIR).status_code)
check('VR-16 Dirección de otro colegio tampoco ve este curso (404)', vista(P1, DIR_OTRO).status_code == 404, '')
check('VR-17 profesor y secretaría no ganan acceso (403)',
      vista(P1, PROF_TIT).status_code == 403 and vista(P1, SECRE).status_code == 403, '')
check('VR-18 fecha inválida: 400', client.get('/api/asistencia/vista-rapida/%d?fecha=hoy' % P1.id,
                                               headers=h(DIR)).status_code == 400, '')

print("\n=== SOLO LECTURA ===")
antes = (db.query(M.Asistencia).count(), db.query(M.Estudiante).count(), db.query(M.Horario).count())
ESCRITURAS.clear()
for c in (P1, P2, P3, S1, S2, S3):
    vista(c, DIR)
check('VR-19 abrir la vista no provoca ningún INSERT/UPDATE/DELETE', not ESCRITURAS, ESCRITURAS[:3])
check('VR-20 conteos de asistencia/estudiantes/horarios intactos',
      antes == (db.query(M.Asistencia).count(), db.query(M.Estudiante).count(), db.query(M.Horario).count()), '')
db.close()

ok = sum(1 for _, r in RES if r)
print('\nRESULTADO ASIS-DASH-1: %d PASARON / %d FALLARON' % (ok, len(RES) - ok))
sys.exit(0 if ok == len(RES) else 1)
