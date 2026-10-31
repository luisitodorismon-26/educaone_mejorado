"""Salida Optativa — lo que necesita la pantalla compacta del modal del curso.

Base SQLite AISLADA, datos sintéticos, endpoints reales:

  1. Curso SIN salida: «Guardar asignación» de un componente fija la salida del
     curso con la de ese componente. Si el curso ya tiene salida, no se cambia.
  2. Guardar una asignación conserva la otra (mismo curso, otra salida).
  3. Explorar otra salida no es un cambio: el GET no altera nada.
  4. Dos colegios con docentes del MISMO nombre: /api/usuarios solo devuelve los
     del colegio propio y guardar con un profesor del otro colegio se rechaza
     sin cambiar nada.

Uso (desde backend/):  python tools/test_salidas_modal_compacto.py
"""
import datetime as dt
import os
import sys

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(BK, 'tools'))
from test_utils import aislar_base_de_datos, verificar_engine_aislado

TMP = aislar_base_de_datos('salidas_modal_compacto')
from database import engine, SessionLocal
verificar_engine_aislado(engine, TMP)
import models as M
import app as APP
from fastapi.testclient import TestClient
from auth import create_token

M.Base.metadata.create_all(bind=engine)
db = SessionLocal()
OK, MAL = [], []


def check(nombre, cond, detalle=''):
    (OK if cond else MAL).append(nombre)
    print('  %s %s %s' % ('PASA ' if cond else 'FALLA', nombre, '' if cond else str(detalle)[:300]))


def add(o):
    db.add(o)
    db.flush()
    return o


def colegio(codigo):
    col = add(M.Colegio(nombre='Colegio %s' % codigo, codigo=codigo, activo=True))
    ano = add(M.AnoEscolar(colegio_id=col.id, nombre='2026-2027', activo=True, cerrado=False,
                           fecha_inicio=dt.date(2026, 9, 1), fecha_fin=dt.date(2027, 6, 30)))
    g = add(M.Grado(colegio_id=col.id, nombre='4to Secundaria', nivel='secundaria', orden=4, activo=True))
    u = lambda n, a, r: add(M.Usuario(colegio_id=col.id, username='%s_%s' % (codigo, n.lower()), password_hash='x',
                                      nombre=n, apellido=a, role=r, activo=True, must_change_password=False,
                                      token_version=0))
    dire = u('Dir', 'X', 'direccion')
    julio = u('Julio', 'Sena', 'profesor')          # mismo nombre en los dos colegios
    rosana = u('Rosana', 'Pérez', 'profesor')
    return col, ano, g, dire, julio, rosana


A_col, A_ano, A_g, A_dir, A_julio, A_rosana = colegio('UNO')
B_col, B_ano, B_g, B_dir, B_julio, B_rosana = colegio('DOS')
curso = add(M.Curso(colegio_id=A_col.id, nombre='A', grado_id=A_g.id, ano_escolar_id=A_ano.id, activo=True))
db.commit()
c = TestClient(APP.app)
H = {'Authorization': 'Bearer ' + create_token(A_dir)}
URL = '/api/cursos/%d/salida-optativa' % curso.id


def estado():
    return c.get(URL, headers=H).json()


def asignaciones():
    db.expire_all()
    return sorted((a.profesor_id, a.asignatura_id, bool(a.activo))
                  for a in db.query(M.AsignacionProfesor).filter_by(curso_id=curso.id))


print('\n=== 1. Curso sin salida: la primera asignación fija la salida ===')
e0 = estado()
check('1a el curso empieza sin salida y sin asignaciones',
      e0['salida_optativa_codigo'] is None and not [x for x in e0['componentes'] if x['asignatura_id']], e0)
check('1a2 sin salida, la pantalla ya recibe el catálogo completo del grado (6 componentes de 4to)',
      sorted(d['componente_codigo'] for d in e0['componentes_disponibles'])
      == ['CYT-CN-4', 'HCS-CS-4', 'HCS-LE-4', 'HLM-IN-4', 'HLM-LE-4', 'MYT-MA-4'], e0['componentes_disponibles'])
r = c.post(URL + '/componentes', headers=H, json={'componente_codigo': 'HCS-CS-4', 'profesor_id': A_rosana.id})
e1 = r.json()
check('1b «Guardar asignación» HCS-CS-4 con Rosana: 200', r.status_code == 200, r.text[:200])
check('1c la salida del curso pasa a HCS (la del componente)', e1.get('salida_optativa_codigo') == 'HCS',
      e1.get('salida_optativa_codigo'))
check('1d Rosana queda guardada en HCS-CS-4',
      [(x['componente_codigo'], x['profesor_nombre']) for x in e1['componentes'] if x['asignatura_id']]
      == [('HCS-CS-4', 'Rosana Pérez')], e1['componentes'])

print('\n=== 2. Guardar otra asignación conserva la primera ===')
r = c.post(URL + '/componentes', headers=H, json={'componente_codigo': 'HLM-LE-4', 'profesor_id': A_julio.id})
e2 = r.json()
check('2a HLM-LE-4 con Julio: 200', r.status_code == 200, r.text[:200])
check('2b las dos asignaciones guardadas: Julio y Rosana',
      sorted((x['componente_codigo'], x['profesor_nombre']) for x in e2['componentes'] if x['asignatura_id'])
      == [('HCS-CS-4', 'Rosana Pérez'), ('HLM-LE-4', 'Julio Sena')], e2['componentes'])
check('2c la salida del curso NO cambia al guardar un componente de otra salida',
      e2['salida_optativa_codigo'] == 'HCS', e2['salida_optativa_codigo'])
antes = asignaciones()

print('\n=== 3. Explorar no es un cambio ===')
for _ in range(3):
    estado()
check('3a consultar el estado varias veces no cambia nada', asignaciones() == antes, (asignaciones(), antes))
check('3b el catálogo del grado está completo: 2 en el curso + 4 disponibles',
      len(estado()['componentes']) + len(estado()['componentes_disponibles']) == 6,
      (len(estado()['componentes']), len(estado()['componentes_disponibles'])))

print('\n=== 4. Dos colegios con docentes del mismo nombre ===')
usuarios = c.get('/api/usuarios', headers=H).json()
ids = {u['id'] for u in usuarios}
check('4a /api/usuarios solo trae los del colegio propio (no el Julio del otro colegio)',
      A_julio.id in ids and B_julio.id not in ids and B_rosana.id not in ids, sorted(ids))
check('4b hay un solo «Julio Sena» en la lista', [u['nombre_completo'] for u in usuarios].count('Julio Sena') == 1,
      [u['nombre_completo'] for u in usuarios])
r = c.post(URL + '/componentes', headers=H, json={'componente_codigo': 'HLM-LE-4', 'profesor_id': B_julio.id})
check('4c cambiar el profesor a un Julio del OTRO colegio: rechazado (404) y nada cambia',
      r.status_code == 404 and asignaciones() == antes, (r.status_code, r.text[:200]))
# En un curso vacío (sin el límite de 2 de por medio): ni asignatura, ni vínculo,
# ni salida a medias.
curso2 = add(M.Curso(colegio_id=A_col.id, nombre='B', grado_id=A_g.id, ano_escolar_id=A_ano.id, activo=True))
db.commit()
n_asig = db.query(M.Asignatura).count()
r = c.post('/api/cursos/%d/salida-optativa/componentes' % curso2.id, headers=H,
           json={'componente_codigo': 'HLM-IN-4', 'profesor_id': B_rosana.id})
db.expire_all()
c2 = db.get(M.Curso, curso2.id)
check('4d añadir un componente con una profesora del otro colegio: 404 y no queda nada a medias',
      r.status_code == 404 and db.query(M.Asignatura).count() == n_asig
      and not db.query(M.CursoComponenteOptativo).filter_by(curso_id=curso2.id).count()
      and not db.query(M.AsignacionProfesor).filter_by(curso_id=curso2.id).count()
      and c2.salida_optativa_codigo is None,
      (r.status_code, db.query(M.Asignatura).count(), n_asig, c2.salida_optativa_codigo))
HB = {'Authorization': 'Bearer ' + create_token(B_dir)}
r = c.get(URL, headers=HB)
check('4e la Dirección del otro colegio no puede ver este curso', r.status_code == 404, r.status_code)

db.close()
engine.dispose()
print('\n%d PASARON / %d FALLARON' % (len(OK), len(MAL)))
sys.exit(1 if MAL else 0)
