"""Probar escenarios específicos para encontrar el bug del usuario."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import engine
db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'sge.db')
for ext in ['', '-shm', '-wal']:
    if os.path.exists(db_path + ext): os.remove(db_path + ext)

from models import Base
Base.metadata.create_all(bind=engine)

from fastapi.testclient import TestClient
from app import app

client = TestClient(app)
def auth(t): return {'Authorization': f'Bearer {t}'}

with client:
    tok = client.post('/api/auth/login', json={'username':'direccion','password':'admin123'}).json()['token']
    
    # init_db crea ya 6 grados de secundaria
    grados = client.get('/api/grados', headers=auth(tok)).json()
    print(f"Grados auto-creados: {len(grados)}")
    for g in grados:
        print(f"  ID={g['id']} '{g['nombre']}' nivel='{g.get('nivel')}'")
    
    # Crear curso con uno de esos grados
    grado_sec = grados[0]
    tandas = client.get('/api/tandas', headers=auth(tok)).json()
    print(f"\nTandas: {tandas}")
    
    r = client.post('/api/cursos', json={'grado_id': grado_sec['id'], 'tanda_id': tandas[0]['id'], 'nombre':'A', 'seccion':'A'}, headers=auth(tok))
    print(f"Curso secundaria: {r.status_code}")
    curso_id = r.json().get('id')
    
    # Asignatura
    asig = client.post('/api/asignaturas', json={'nombre':'Lengua','codigo':'LEN'}, headers=auth(tok)).json()['id']
    prof = client.post('/api/usuarios', json={'username':'p1','password':'profesor123','nombre':'P','apellido':'X','email':'p1@x.com','role':'profesor'}, headers=auth(tok)).json()['id']
    
    # === ESCENARIO 1: dia con mayúscula ===
    print("\n=== ESCENARIO 1: dia 'Lunes' con mayúscula (lo que manda el frontend) ===")
    r = client.post('/api/horarios', json={
        'curso_id': curso_id, 'asignatura_id': asig, 'profesor_id': prof,
        'dia': 'Lunes', 'hora_inicio': '08:00', 'hora_fin': '08:45', 'tipo_bloque': 'clase',
    }, headers=auth(tok))
    print(f"  status={r.status_code} body={r.text[:300]}")
    
    # === ESCENARIO 2: hora_inicio con segundos ===
    print("\n=== ESCENARIO 2: hora con segundos ===")
    r = client.post('/api/horarios', json={
        'curso_id': curso_id, 'asignatura_id': asig, 'profesor_id': prof,
        'dia': 'Martes', 'hora_inicio': '07:30:00', 'hora_fin': '08:20:00', 'tipo_bloque': 'clase',
    }, headers=auth(tok))
    print(f"  status={r.status_code} body={r.text[:300]}")
    
    # === ESCENARIO 3: profesor que no tiene asignación al curso ===
    print("\n=== ESCENARIO 3: profesor SIN asignación al curso ===")
    r = client.post('/api/horarios', json={
        'curso_id': curso_id, 'asignatura_id': asig, 'profesor_id': prof,
        'dia': 'Miércoles', 'hora_inicio': '09:00', 'hora_fin': '09:45', 'tipo_bloque': 'clase',
    }, headers=auth(tok))
    print(f"  status={r.status_code} body={r.text[:300]}")
    
    # === ESCENARIO 4: tipo_bloque sin enviar ===
    print("\n=== ESCENARIO 4: sin tipo_bloque ===")
    r = client.post('/api/horarios', json={
        'curso_id': curso_id, 'asignatura_id': asig, 'profesor_id': prof,
        'dia': 'Jueves', 'hora_inicio': '10:00', 'hora_fin': '10:45',
    }, headers=auth(tok))
    print(f"  status={r.status_code} body={r.text[:300]}")
    
    # === ESCENARIO 5: curso_id que NO existe ===
    print("\n=== ESCENARIO 5: curso_id inexistente (9999) ===")
    r = client.post('/api/horarios', json={
        'curso_id': 9999, 'asignatura_id': asig, 'profesor_id': prof,
        'dia': 'Viernes', 'hora_inicio': '11:00', 'hora_fin': '11:45', 'tipo_bloque': 'clase',
    }, headers=auth(tok))
    print(f"  status={r.status_code} body={r.text[:300]}")
    
    # === ESCENARIO 6: tipos numéricos como string ===
    print("\n=== ESCENARIO 6: IDs como strings ===")
    r = client.post('/api/horarios', json={
        'curso_id': str(curso_id), 'asignatura_id': str(asig), 'profesor_id': str(prof),
        'dia': 'Lunes', 'hora_inicio': '12:00', 'hora_fin': '12:45', 'tipo_bloque': 'clase',
    }, headers=auth(tok))
    print(f"  status={r.status_code} body={r.text[:300]}")

    # === ESCENARIO 7: tipo_bloque inválido ===
    print("\n=== ESCENARIO 7: tipo_bloque inválido ===")
    r = client.post('/api/horarios', json={
        'curso_id': curso_id, 'asignatura_id': asig, 'profesor_id': prof,
        'dia': 'Lunes', 'hora_inicio': '13:00', 'hora_fin': '13:45', 'tipo_bloque': 'invalido',
    }, headers=auth(tok))
    print(f"  status={r.status_code} body={r.text[:300]}")
    
    # === Listar todos ===
    print("\n=== TODOS LOS HORARIOS CREADOS ===")
    r = client.get('/api/horarios', headers=auth(tok))
    for h in r.json():
        print(f"  ID={h['id']} dia='{h.get('dia')}' hora={h.get('hora_inicio')}-{h.get('hora_fin')} tipo={h.get('tipo_bloque')}")
