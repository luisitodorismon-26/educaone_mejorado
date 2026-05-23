"""
Reproduce el bug del usuario usando los defaults que init_db prepara.
"""
import os
os.environ['DATABASE_URL'] = 'sqlite:///sge_repro.db'

if os.path.exists('sge_repro.db'):
    os.remove('sge_repro.db')

import sys
sys.path.insert(0, '.')

from fastapi.testclient import TestClient
from app import app

client = TestClient(app)

def step(n, txt):
    print(f"\n{'='*72}")
    print(f"  PASO {n}: {txt}")
    print(f"{'='*72}")

def ok(t): print(f"  ✓ {t}")
def err(t): print(f"  ✗ {t}")
def info(t): print(f"    {t}")

with client:
    pass

step(1, "Login direccion")
r = client.post('/api/auth/login', json={'username': 'direccion', 'password': 'admin123'})
info(f"Status: {r.status_code}")
assert r.status_code == 200, r.text
dir_token = r.json().get('access_token') or r.json().get('token')
H_DIR = {'Authorization': f'Bearer {dir_token}'}
ok("Director logueado")

r = client.get('/api/asignaturas', headers=H_DIR)
asigs = r.json() if r.status_code == 200 else []
info(f"Asignaturas existentes: {len(asigs)}")

step(2, "Asegurar Lengua Española")
le_asig = next((a for a in asigs if 'lengua espa' in a.get('nombre', '').lower()), None)
if not le_asig:
    r = client.post('/api/asignaturas',
        json={'nombre': 'Lengua Española', 'codigo': 'LE'}, headers=H_DIR)
    info(f"Crear LE: {r.status_code} {r.text[:200]}")
    le_asig = r.json()
ok(f"LE ID={le_asig['id']}, nombre='{le_asig['nombre']}'")
asig_le = le_asig['id']

step(3, "Curso")
r = client.get('/api/grados', headers=H_DIR)
grados = r.json() if r.status_code == 200 else []
grado = grados[0]
info(f"Grado: {grado['nombre']}")

r = client.get('/api/tandas', headers=H_DIR)
tandas = r.json() if r.status_code == 200 else []
if not tandas:
    r = client.post('/api/tandas', json={'nombre': 'Matutina'}, headers=H_DIR)
    tandas = [r.json()]
tanda = tandas[0]

r = client.get('/api/anos-escolares', headers=H_DIR)
anos = r.json() if r.status_code == 200 else []
ano = anos[0]
info(f"Año: {ano['nombre']} ({ano.get('fecha_inicio')} → {ano.get('fecha_fin')})")

r = client.get('/api/cursos', headers=H_DIR)
cursos = r.json() if r.status_code == 200 else []
curso = cursos[0] if cursos else None
if not curso:
    r = client.post('/api/cursos', json={
        'grado_id': grado['id'],
        'tanda_id': tanda['id'],
        'seccion': 'A',
        'ano_escolar_id': ano['id'],
        'nombre': 'A',
    }, headers=H_DIR)
    info(f"Crear curso: {r.status_code} {r.text[:300]}")
    curso = r.json()
curso_id = curso['id']
ok(f"Curso ID={curso_id}")

step(4, "Profesor")
r = client.post('/api/usuarios', json={
    'username': 'profe1', 'password': 'profe123',
    'nombre': 'Profesor', 'apellido': 'Uno',
    'role': 'profesor',
}, headers=H_DIR)
info(f"Crear profe: {r.status_code} {r.text[:200]}")
profe = r.json()
profe_id = profe['id']

r = client.post('/api/asignaciones', json={
    'profesor_id': profe_id,
    'curso_id': curso_id,
    'asignatura_id': asig_le,
    'titular': True,
}, headers=H_DIR)
info(f"Asignación: {r.status_code} {r.text[:150]}")

step(5, "Estudiantes")
est_ids = []
for i in range(1, 11):
    r = client.post('/api/estudiantes', json={
        'nombre': f'EstReal{i:02d}',
        'apellido': 'Test',
        'curso_id': curso_id,
        'no_lista': i,
        'sexo': 'F' if i % 2 else 'M',
        'fecha_nacimiento': f'2010-0{((i-1)%9)+1}-15',
        'matricula': f'R{i:04d}',
    }, headers=H_DIR)
    if r.status_code in (200, 201):
        est_ids.append(r.json()['id'])
    else:
        err(f"  est{i}: {r.status_code} {r.text[:120]}")
        break
ok(f"{len(est_ids)} estudiantes creados, IDs: {est_ids[:3]}...")

step(6, "Horario")
for dia in ['lunes', 'miércoles']:
    r = client.post('/api/horarios', json={
        'curso_id': curso_id,
        'asignatura_id': asig_le,
        'profesor_id': profe_id,
        'dia': dia,
        'hora_inicio': '08:00',
        'hora_fin': '08:45',
        'tipo_bloque': 'clase',
    }, headers=H_DIR)
    info(f"  {dia}: {r.status_code} {r.text[:150]}")

step(7, "Login profesor")
r = client.post('/api/auth/login', json={'username': 'profe1', 'password': 'profe123'})
profe_token = r.json().get('access_token') or r.json().get('token')
H_PROF = {'Authorization': f'Bearer {profe_token}'}
ok("Profe logueado")

step(8, "Calificaciones (10 est, 2 parciales del P1)")
cal_ok = 0
for idx, est_id in enumerate(est_ids[:10]):
    r = client.post('/api/calificaciones', json={
        'estudiante_id': est_id,
        'asignatura_id': asig_le,
        'p1_p1': 70 + idx,
        'p1_p2': 71 + idx,
    }, headers=H_PROF)
    if r.status_code in (200, 201):
        cal_ok += 1
    else:
        if cal_ok < 2:
            err(f"  cal{idx+1}: {r.status_code} {r.text[:200]}")
ok(f"Calificaciones OK: {cal_ok}/10")

step(9, "Asistencia (5 días en LE)")
fechas = ['2024-09-02', '2024-09-04', '2024-09-09', '2024-09-11', '2024-09-16']
asists_ok = 0
asists_fail = 0
for fecha in fechas:
    for est_id in est_ids[:10]:
        r = client.post('/api/asistencia', json={
            'estudiante_id': est_id,
            'asignatura_id': asig_le,
            'fecha': fecha,
            'estado': 'presente',
        }, headers=H_PROF)
        if r.status_code in (200, 201):
            asists_ok += 1
        else:
            asists_fail += 1
            if asists_fail <= 2:
                err(f"  asist {fecha}/{est_id}: {r.status_code} {r.text[:200]}")
ok(f"Asistencias OK: {asists_ok}, fail: {asists_fail}")

step(10, "Verificar BD")
from database import SessionLocal
from models import Calificacion, Asistencia

db = SessionLocal()
califs_db = db.query(Calificacion).filter_by(asignatura_id=asig_le).all()
ok(f"BD: {len(califs_db)} calificaciones LE")
if califs_db:
    c = califs_db[0]
    info(f"  Ejemplo: p1_p1={c.p1_p1} p1_p2={c.p1_p2} p1_p3={c.p1_p3} p1_p4={c.p1_p4}")
    info(f"  pc1 persistido={c.pc1}, calcular_pc(1)={c.calcular_pc(1)}, cf={c.cf}")

asists_db = db.query(Asistencia).filter_by(asignatura_id=asig_le).all()
ok(f"BD: {len(asists_db)} asistencias LE")
nulls = db.query(Asistencia).filter(Asistencia.asignatura_id.is_(None)).count()
if nulls:
    err(f"BD: {nulls} asistencias con asignatura_id=NULL")

if asists_db:
    s = asists_db[0]
    info(f"  Sample: est={s.estudiante_id} curso={s.curso_id} fecha={s.fecha} estado='{s.estado}'")

step(11, "GET /api/registros/secundaria/{curso_id}/preview-pdf")
r = client.get(f'/api/registros/secundaria/{curso_id}/preview-pdf', headers=H_DIR)
info(f"Status: {r.status_code}")
info(f"CT: {r.headers.get('content-type')}")
info(f"size: {len(r.content)} bytes")
if r.status_code == 200 and 'pdf' in r.headers.get('content-type', ''):
    open('/home/claude/registro_repro.pdf', 'wb').write(r.content)
    ok("PDF guardado /home/claude/registro_repro.pdf")
else:
    err(f"Error: {r.text[:500]}")

step(12, "_cargar_datos_asignaturas_secundaria — qué construye?")
from app import _cargar_datos_asignaturas_secundaria
from models import Estudiante, Usuario

est_objs = db.query(Estudiante).filter_by(curso_id=curso_id, activo=True).all()
director = db.query(Usuario).filter_by(username='direccion').first()
data = _cargar_datos_asignaturas_secundaria(db, director, curso_id, 1, est_objs)

print()
print(f"  Claves del dict: {list(data.keys())[:7]}")

le_data = data.get('Lengua Española')
if not le_data:
    err("'Lengua Española' NO en el dict — bug de mapeo")
    err(f"  Claves disponibles: {list(data.keys())}")
else:
    ok("'Lengua Española' está")
    info(f"  docente: '{le_data.get('docente')}'")
    
    matriz = le_data.get('asistencia_matriz', [])
    info(f"  asistencia_matriz: {len(matriz)} meses")
    for mes in matriz:
        con = sum(1 for f in mes['filas'] if any(f['valores']))
        info(f"    {mes['mes']}: {mes['total_dias']} días, fuente='{mes.get('fuente_dias')}', {con}/{len(mes['filas'])} ests con marcas")
        if mes['total_dias'] > 0:
            info(f"      días esperados: {mes['dias'][:8]}{'...' if len(mes['dias'])>8 else ''}")
            info(f"      días con reg:   {mes.get('dias_con_registro', [])}")
    
    califs = le_data.get('calificaciones', {})
    info(f"  calificaciones: {len(califs)} estudiantes")
    for k, v in list(califs.items())[:3]:
        info(f"    idx {k}: {v}")

db.close()
print("\n" + "="*72 + "\n  FIN\n" + "="*72)
