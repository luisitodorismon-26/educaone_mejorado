"""Reproducir bug: horarios primaria funciona, secundaria no."""
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
from database import SessionLocal
from models import Grado, Tanda, Usuario

client = TestClient(app)
def auth(t): return {'Authorization': f'Bearer {t}'}

with client:
    # Login director (creado por init_db con admin123)
    r = client.post('/api/auth/login', json={'username':'direccion','password':'admin123'})
    print(f"Login director: {r.status_code}")
    if r.status_code != 200:
        print(r.text)
        sys.exit(1)
    tok = r.json()['token']
    
    # Ver grados disponibles
    r = client.get('/api/grados', headers=auth(tok))
    print(f"\nGrados disponibles: {r.status_code}")
    grados = r.json() if r.status_code == 200 else []
    for g in grados[:6]:
        print(f"  ID={g.get('id')} nombre='{g.get('nombre')}' nivel='{g.get('nivel')}'")
    
    # Crear un grado de PRIMARIA y uno de SECUNDARIA explícitamente
    print("\n=== Creando grados ===")
    r = client.post('/api/grados', json={'nombre': 'Test Primaria 1ro', 'nivel': 'primaria', 'orden': 100}, headers=auth(tok))
    print(f"Crear grado primaria: {r.status_code} {r.text[:200]}")
    grado_prim_id = r.json().get('id') if r.status_code in (200,201) else None
    
    r = client.post('/api/grados', json={'nombre': 'Test Secundaria 1ro', 'nivel': 'secundaria', 'orden': 101}, headers=auth(tok))
    print(f"Crear grado secundaria: {r.status_code} {r.text[:200]}")
    grado_sec_id = r.json().get('id') if r.status_code in (200,201) else None
    
    # Tanda
    r = client.get('/api/tandas', headers=auth(tok))
    tanda_id = r.json()[0]['id'] if r.json() else None
    print(f"\nTanda a usar: {tanda_id}")
    
    # Crear cursos
    r = client.post('/api/cursos', json={'grado_id': grado_prim_id, 'tanda_id': tanda_id, 'nombre':'A', 'seccion':'A'}, headers=auth(tok))
    curso_prim = r.json().get('id') if r.status_code in (200,201) else None
    print(f"Curso primaria: {r.status_code} ID={curso_prim}")
    
    r = client.post('/api/cursos', json={'grado_id': grado_sec_id, 'tanda_id': tanda_id, 'nombre':'A', 'seccion':'A'}, headers=auth(tok))
    curso_sec = r.json().get('id') if r.status_code in (200,201) else None
    print(f"Curso secundaria: {r.status_code} ID={curso_sec}")
    
    # Asignaturas
    r = client.post('/api/asignaturas', json={'nombre':'Lengua Test', 'codigo':'LEN'}, headers=auth(tok))
    asig_id = r.json().get('id')
    print(f"\nAsignatura: {r.status_code} ID={asig_id}")
    
    # Profesor
    r = client.post('/api/usuarios', json={
        'username':'profe_test','password':'profesor123','nombre':'Test','apellido':'Prof',
        'email':'p@x.com','role':'profesor',
    }, headers=auth(tok))
    prof_id = r.json().get('id')
    print(f"Profesor: {r.status_code} ID={prof_id}")
    
    # === AHORA: CREAR HORARIO PRIMARIA ===
    print("\n=== CREAR HORARIO PRIMARIA ===")
    payload_prim = {
        'curso_id': curso_prim, 'asignatura_id': asig_id, 'profesor_id': prof_id,
        'dia': 'lunes', 'hora_inicio': '08:00', 'hora_fin': '08:45',
        'tipo_bloque': 'clase',
    }
    print(f"payload: {payload_prim}")
    r = client.post('/api/horarios', json=payload_prim, headers=auth(tok))
    print(f"  → status={r.status_code}")
    print(f"  → body={r.text[:300]}")
    
    # === CREAR HORARIO SECUNDARIA ===
    print("\n=== CREAR HORARIO SECUNDARIA ===")
    payload_sec = {
        'curso_id': curso_sec, 'asignatura_id': asig_id, 'profesor_id': prof_id,
        'dia': 'lunes', 'hora_inicio': '08:00', 'hora_fin': '08:45',
        'tipo_bloque': 'clase',
    }
    print(f"payload: {payload_sec}")
    r = client.post('/api/horarios', json=payload_sec, headers=auth(tok))
    print(f"  → status={r.status_code}")
    print(f"  → body={r.text[:300]}")
    
    # Listar horarios para ver si se crearon
    print("\n=== LISTAR HORARIOS ===")
    r = client.get('/api/horarios', headers=auth(tok))
    print(f"  status={r.status_code}, count={len(r.json()) if r.status_code == 200 else '?'}")
    if r.status_code == 200:
        for h in r.json():
            print(f"  H ID={h.get('id')} curso={h.get('curso_id')} asig={h.get('asignatura_id')} dia={h.get('dia')} hora={h.get('hora_inicio')}")
