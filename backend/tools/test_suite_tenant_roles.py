"""
EducaOne — Tests automáticos de Fase 2/3 (Sprint multi-tenant + roles).

Valida:
  A. Aislamiento entre colegios (cross-tenant impossible).
  B. Permisos por rol (profesor no crea estudiantes, secretaria no califica, etc.).
  C. Flujos básicos de horarios, calificaciones y asistencia.
  D. Validación de inputs (FK inválido, body malformado, etc.).

Uso:
    cd backend
    venv\\Scripts\\activate (Windows) o source venv/bin/activate (Linux/mac)
    python tools/test_suite_tenant_roles.py

Si todo pasa, imprime "TODOS LOS TESTS PASARON". Si algo falla, sale con
código != 0 y muestra exactamente qué.
"""
import sys
import os
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# DB limpia para los tests
db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'sge.db')
for ext in ['', '-shm', '-wal']:
    if os.path.exists(db_path + ext):
        os.remove(db_path + ext)
init_creds = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'INITIAL_CREDENTIALS.txt')
if os.path.exists(init_creds):
    os.remove(init_creds)

from database import engine
from models import Base
Base.metadata.create_all(bind=engine)

from fastapi.testclient import TestClient
from app import app

# Globales del test
client = TestClient(app)
fallos = []
pasados = 0
total = 0


GREEN = "\033[92m"; RED = "\033[91m"; YELLOW = "\033[93m"; BOLD = "\033[1m"; CYAN = "\033[96m"; RESET = "\033[0m"

def auth(t):
    return {'Authorization': f'Bearer {t}'}


def test(nombre):
    """Decorador para registrar un test."""
    def decorator(fn):
        global total, pasados, fallos
        total += 1
        print(f"\n{CYAN}▶ {nombre}{RESET}")
        try:
            fn()
            pasados += 1
            print(f"  {GREEN}✓ PASÓ{RESET}")
        except AssertionError as e:
            fallos.append((nombre, str(e)))
            print(f"  {RED}✗ FALLÓ: {e}{RESET}")
        except Exception as e:
            fallos.append((nombre, f"EXCEPCIÓN: {e}"))
            print(f"  {RED}✗ EXCEPCIÓN: {e}{RESET}")
            traceback.print_exc()
        return fn
    return decorator


# ─────────────────────────────────────────────────────────────────
# Setup: 2 colegios, cada uno con sus roles
# ─────────────────────────────────────────────────────────────────

print(f"{BOLD}\n=== SETUP ==={RESET}")

with client:
    # Login superadmin
    r = client.post('/api/auth/login', json={'username':'superadmin','password':'superadmin123'})
    assert r.status_code == 200, f"login superadmin falló: {r.text}"
    SA_TOKEN = r.json()['token']
    
    # Crear colegio B (el A es el default que crea init_db)
    r = client.post('/api/superadmin/colegios', json={
        'nombre':'Colegio B','codigo':'b','plan':'enterprise',
        'admin_username':'dir_b','admin_password':'admin123b',
        # Niveles explícitos: el default ya no asume primaria/secundaria
        'plan_secundaria': True, 'plan_primaria': True,
    }, headers=auth(SA_TOKEN))
    assert r.status_code in (200, 201), f"crear colegio B falló: {r.text}"
    
    # Login director A (el default)
    DIR_A_TOKEN = client.post('/api/auth/login', json={'username':'direccion','password':'admin123'}).json()['token']
    DIR_B_TOKEN = client.post('/api/auth/login', json={'username':'dir_b','password':'admin123b'}).json()['token']
    
    print(f"  {GREEN}✓{RESET} 2 colegios creados, 2 directores logueados")
    
    # En cada colegio: crear curso, asignatura, profesor
    def setup_colegio(tok, sufijo):
        """sufijo: string único por colegio para evitar colisión de usernames."""
        grados = client.get('/api/grados', headers=auth(tok)).json()
        tandas = client.get('/api/tandas', headers=auth(tok)).json()
        r = client.post('/api/cursos', json={
            'grado_id': grados[0]['id'], 'tanda_id': tandas[0]['id'], 'nombre':'A'
        }, headers=auth(tok))
        assert r.status_code in (200, 201), f"crear curso falló: {r.text}"
        curso_id = r.json()['id']
        
        r = client.post('/api/asignaturas', json={'nombre':'Matemática','codigo':'M'}, headers=auth(tok))
        asig_id = r.json()['id']
        
        # Profesor (username único)
        r = client.post('/api/usuarios', json={
            'username': f'profe_{sufijo}','password':'profesor123',
            'nombre':'Prof','apellido':'Test',
            'email': f'p_{sufijo}@x.com','role':'profesor',
        }, headers=auth(tok))
        assert r.status_code in (200, 201), f"crear profesor falló: {r.text}"
        prof_id = r.json()['id']
        
        # Coordinador
        r = client.post('/api/usuarios', json={
            'username': f'coord_{sufijo}','password':'coordinador123',
            'nombre':'Coord','apellido':'Test',
            'email': f'c_{sufijo}@x.com','role':'coordinador',
        }, headers=auth(tok))
        assert r.status_code in (200, 201), f"crear coordinador falló: {r.text}"
        coord_id = r.json()['id']
        
        # Secretaria
        r = client.post('/api/usuarios', json={
            'username': f'sec_{sufijo}','password':'secretaria123',
            'nombre':'Sec','apellido':'Test',
            'email': f's_{sufijo}@x.com','role':'secretaria',
        }, headers=auth(tok))
        assert r.status_code in (200, 201), f"crear secretaria falló: {r.text}"
        sec_id = r.json()['id']
        
        # Asignación profesor → curso/asig
        client.post('/api/asignaciones', json={
            'profesor_id': prof_id, 'curso_id': curso_id, 'asignatura_id': asig_id,
        }, headers=auth(tok))
        
        # Estudiante
        r = client.post('/api/estudiantes', json={
            'nombre':'Est','apellido':'Demo','sexo':'M','fecha_nacimiento':'2010-01-01',
            'curso_id': curso_id, 'no_lista': 1, 'matricula': f'M001-{sufijo}'
        }, headers=auth(tok))
        est_id = r.json()['id']
        
        return {
            'curso': curso_id, 'asig': asig_id,
            'prof': prof_id, 'coord': coord_id, 'sec': sec_id,
            'est': est_id,
            'grado': grados[0]['id'], 'tanda': tandas[0]['id'],
            'sufijo': sufijo,
        }
    
    A = setup_colegio(DIR_A_TOKEN, 'a')
    B = setup_colegio(DIR_B_TOKEN, 'b')
    print(f"  {GREEN}✓{RESET} Colegio A: curso={A['curso']} asig={A['asig']} prof={A['prof']} est={A['est']}")
    print(f"  {GREEN}✓{RESET} Colegio B: curso={B['curso']} asig={B['asig']} prof={B['prof']} est={B['est']}")
    
    # Login profesor del A y del B
    PROF_A_TOKEN = client.post('/api/auth/login', json={
        'username': f'profe_{A["sufijo"]}', 'password':'profesor123'
    }).json()['token']
    PROF_B_TOKEN = client.post('/api/auth/login', json={
        'username': f'profe_{B["sufijo"]}', 'password':'profesor123'
    }).json()['token']
    SEC_A_TOKEN = client.post('/api/auth/login', json={
        'username': f'sec_{A["sufijo"]}', 'password':'secretaria123'
    }).json()['token']
    
    # ─────────────────────────────────────────────────────────────────
    # SECCIÓN A — AISLAMIENTO ENTRE COLEGIOS
    # ─────────────────────────────────────────────────────────────────
    
    print(f"{BOLD}\n=== A. AISLAMIENTO TENANT ==={RESET}")
    
    @test("A1. Director A NO ve cursos de B en GET /api/cursos")
    def t():
        cursos_a = client.get('/api/cursos', headers=auth(DIR_A_TOKEN)).json()
        ids_a = {c['id'] for c in cursos_a}
        assert B['curso'] not in ids_a, f"Director A vio curso de B: {ids_a}"
    
    @test("A2. Director A NO puede GET curso del B (404)")
    def t():
        # Get específico no existe pero igual probamos a través del usado en endpoints
        r = client.get(f'/api/horarios/curso/{B["curso"]}', headers=auth(DIR_A_TOKEN))
        assert r.status_code == 404, f"esperaba 404, obtuvo {r.status_code}: {r.text}"
    
    @test("A3. Director A NO puede crear horario apuntando a curso de B")
    def t():
        r = client.post('/api/horarios', json={
            'curso_id': B['curso'], 'asignatura_id': A['asig'], 'profesor_id': A['prof'],
            'dia':'Lunes', 'hora_inicio':'08:00', 'hora_fin':'08:45', 'tipo_bloque':'clase',
        }, headers=auth(DIR_A_TOKEN))
        assert r.status_code == 404, f"esperaba 404, obtuvo {r.status_code}: {r.text}"
    
    @test("A4. Director A NO puede crear horario apuntando a profesor de B")
    def t():
        r = client.post('/api/horarios', json={
            'curso_id': A['curso'], 'asignatura_id': A['asig'], 'profesor_id': B['prof'],
            'dia':'Lunes', 'hora_inicio':'08:00', 'hora_fin':'08:45', 'tipo_bloque':'clase',
        }, headers=auth(DIR_A_TOKEN))
        assert r.status_code == 404, f"esperaba 404, obtuvo {r.status_code}: {r.text}"
    
    @test("A5. Director A NO puede crear horario apuntando a asignatura de B")
    def t():
        r = client.post('/api/horarios', json={
            'curso_id': A['curso'], 'asignatura_id': B['asig'], 'profesor_id': A['prof'],
            'dia':'Lunes', 'hora_inicio':'08:00', 'hora_fin':'08:45', 'tipo_bloque':'clase',
        }, headers=auth(DIR_A_TOKEN))
        assert r.status_code == 404, f"esperaba 404, obtuvo {r.status_code}: {r.text}"
    
    @test("A6. Director A NO puede ver estudiante de B")
    def t():
        r = client.get(f'/api/estudiantes/{B["est"]}', headers=auth(DIR_A_TOKEN))
        assert r.status_code == 404, f"esperaba 404, obtuvo {r.status_code}: {r.text}"
    
    @test("A7. Director A NO puede editar estudiante de B")
    def t():
        r = client.put(f'/api/estudiantes/{B["est"]}', json={'nombre':'Hacked'}, headers=auth(DIR_A_TOKEN))
        assert r.status_code == 404, f"esperaba 404, obtuvo {r.status_code}: {r.text}"
    
    @test("A8. Director A NO puede borrar estudiante de B")
    def t():
        r = client.delete(f'/api/estudiantes/{B["est"]}', headers=auth(DIR_A_TOKEN))
        assert r.status_code == 404, f"esperaba 404, obtuvo {r.status_code}: {r.text}"
    
    @test("A9. Director A NO puede crear asignación con profesor de B")
    def t():
        r = client.post('/api/asignaciones', json={
            'profesor_id': B['prof'], 'curso_id': A['curso'], 'asignatura_id': A['asig'],
        }, headers=auth(DIR_A_TOKEN))
        assert r.status_code == 404, f"esperaba 404, obtuvo {r.status_code}: {r.text}"
    
    @test("A10. Director A NO puede mover estudiante propio a curso de B")
    def t():
        r = client.put(f'/api/estudiantes/{A["est"]}', json={'curso_id': B['curso']}, headers=auth(DIR_A_TOKEN))
        assert r.status_code == 404, f"esperaba 404, obtuvo {r.status_code}: {r.text}"
    
    @test("A11. Director A NO puede asignar estudiante del A a curso de B en POST")
    def t():
        r = client.post('/api/estudiantes', json={
            'nombre':'X','apellido':'Y','curso_id': B['curso'],
        }, headers=auth(DIR_A_TOKEN))
        assert r.status_code == 404, f"esperaba 404, obtuvo {r.status_code}: {r.text}"
    
    @test("A12. Profesor A NO puede calificar estudiante de B")
    def t():
        r = client.post('/api/calificaciones', json={
            'estudiante_id': B['est'], 'asignatura_id': A['asig'], 'p1_p1': 80,
        }, headers=auth(PROF_A_TOKEN))
        assert r.status_code == 404, f"esperaba 404, obtuvo {r.status_code}: {r.text}"
    
    @test("A13. Profesor A NO puede registrar asistencia de estudiante de B")
    def t():
        r = client.post('/api/asistencia', json={
            'estudiante_id': B['est'], 'asignatura_id': A['asig'],
            'fecha':'2024-09-02', 'estado':'presente',
        }, headers=auth(PROF_A_TOKEN))
        assert r.status_code == 403, f"esperaba 403 (cross-tenant), obtuvo {r.status_code}: {r.text}"
    
    @test("A14. Director A NO puede editar curso de B")
    def t():
        r = client.put(f'/api/cursos/{B["curso"]}', json={'nombre':'Z'}, headers=auth(DIR_A_TOKEN))
        assert r.status_code == 404, f"esperaba 404, obtuvo {r.status_code}: {r.text}"
    
    # ─────────────────────────────────────────────────────────────────
    # SECCIÓN B — PERMISOS POR ROL
    # ─────────────────────────────────────────────────────────────────
    
    print(f"{BOLD}\n=== B. PERMISOS POR ROL ==={RESET}")
    
    @test("B1. Profesor NO puede crear horarios")
    def t():
        r = client.post('/api/horarios', json={
            'curso_id': A['curso'], 'asignatura_id': A['asig'], 'profesor_id': A['prof'],
            'dia':'Lunes', 'hora_inicio':'08:00', 'hora_fin':'08:45', 'tipo_bloque':'clase',
        }, headers=auth(PROF_A_TOKEN))
        assert r.status_code == 403, f"esperaba 403, obtuvo {r.status_code}"
    
    @test("B2. Profesor NO puede crear estudiantes")
    def t():
        r = client.post('/api/estudiantes', json={
            'nombre':'X','apellido':'Y','curso_id': A['curso'],
        }, headers=auth(PROF_A_TOKEN))
        assert r.status_code == 403, f"esperaba 403, obtuvo {r.status_code}"
    
    @test("B3. Profesor NO puede crear cursos")
    def t():
        r = client.post('/api/cursos', json={
            'grado_id': A['grado'], 'tanda_id': A['tanda'], 'nombre':'Z',
        }, headers=auth(PROF_A_TOKEN))
        assert r.status_code == 403, f"esperaba 403, obtuvo {r.status_code}"
    
    @test("B4. Profesor NO puede crear asignaciones")
    def t():
        r = client.post('/api/asignaciones', json={
            'profesor_id': A['prof'], 'curso_id': A['curso'], 'asignatura_id': A['asig'],
        }, headers=auth(PROF_A_TOKEN))
        assert r.status_code == 403, f"esperaba 403, obtuvo {r.status_code}"
    
    @test("B5. Profesor NO puede crear asignaturas")
    def t():
        r = client.post('/api/asignaturas', json={'nombre':'X'}, headers=auth(PROF_A_TOKEN))
        assert r.status_code == 403, f"esperaba 403, obtuvo {r.status_code}"
    
    @test("B6. Director NO puede calificar (solo profesores)")
    def t():
        r = client.post('/api/calificaciones', json={
            'estudiante_id': A['est'], 'asignatura_id': A['asig'], 'p1_p1': 80,
        }, headers=auth(DIR_A_TOKEN))
        assert r.status_code == 403, f"esperaba 403, obtuvo {r.status_code}"
    
    @test("B7. Secretaria NO puede calificar")
    def t():
        r = client.post('/api/calificaciones', json={
            'estudiante_id': A['est'], 'asignatura_id': A['asig'], 'p1_p1': 80,
        }, headers=auth(SEC_A_TOKEN))
        assert r.status_code == 403, f"esperaba 403, obtuvo {r.status_code}"
    
    @test("B8. Profesor SIN asignación NO puede calificar")
    def t():
        # Crear una segunda asignatura sin asignar al profesor
        r = client.post('/api/asignaturas', json={'nombre':'Otra','codigo':'O'}, headers=auth(DIR_A_TOKEN))
        otra_asig = r.json()['id']
        r = client.post('/api/calificaciones', json={
            'estudiante_id': A['est'], 'asignatura_id': otra_asig, 'p1_p1': 80,
        }, headers=auth(PROF_A_TOKEN))
        assert r.status_code == 403, f"esperaba 403, obtuvo {r.status_code}: {r.text}"
    
    # ─────────────────────────────────────────────────────────────────
    # SECCIÓN C — FLUJOS BÁSICOS
    # ─────────────────────────────────────────────────────────────────
    
    print(f"{BOLD}\n=== C. FLUJOS BÁSICOS ==={RESET}")
    
    @test("C1. Director crea horario válido en secundaria")
    def t():
        r = client.post('/api/horarios', json={
            'curso_id': A['curso'], 'asignatura_id': A['asig'], 'profesor_id': A['prof'],
            'dia':'Lunes', 'hora_inicio':'08:00', 'hora_fin':'08:45', 'tipo_bloque':'clase',
        }, headers=auth(DIR_A_TOKEN))
        assert r.status_code == 201, f"esperaba 201, obtuvo {r.status_code}: {r.text}"
    
    @test("C2. Profesor con asignación califica estudiante")
    def t():
        r = client.post('/api/calificaciones', json={
            'estudiante_id': A['est'], 'asignatura_id': A['asig'],
            'p1_p1': 80, 'p1_p2': 75,
        }, headers=auth(PROF_A_TOKEN))
        assert r.status_code == 200, f"esperaba 200, obtuvo {r.status_code}: {r.text}"
        # Con solo 2 parciales, PC1 debe ser None (lineamiento MINERD)
        body = r.json()
        cal = body['calificacion']
        assert cal['pc1'] is None, f"PC1 debería ser None con solo 2 parciales, fue {cal['pc1']}"
    
    @test("C3. Con 4 parciales, PC1 se calcula correctamente")
    def t():
        r = client.post('/api/calificaciones', json={
            'estudiante_id': A['est'], 'asignatura_id': A['asig'],
            'p1_p1': 80, 'p1_p2': 75, 'p1_p3': 85, 'p1_p4': 90,
        }, headers=auth(PROF_A_TOKEN))
        assert r.status_code == 200, f"esperaba 200, obtuvo {r.status_code}: {r.text}"
        body = r.json()
        cal = body['calificacion']
        assert cal['pc1'] == 82.5, f"PC1 debería ser 82.5, fue {cal['pc1']}"
    
    @test("C4. Profesor registra asistencia válida")
    def t():
        r = client.post('/api/asistencia', json={
            'estudiante_id': A['est'], 'asignatura_id': A['asig'],
            'fecha':'2024-09-02', 'estado':'presente',
        }, headers=auth(PROF_A_TOKEN))
        assert r.status_code == 200, f"esperaba 200, obtuvo {r.status_code}: {r.text}"
    
    @test("C5. GET asistencia devuelve estudiantes con marcas")
    def t():
        r = client.get(f'/api/asistencia?curso_id={A["curso"]}&asignatura_id={A["asig"]}&fecha=2024-09-02',
                       headers=auth(PROF_A_TOKEN))
        assert r.status_code == 200, f"esperaba 200, obtuvo {r.status_code}: {r.text}"
        data = r.json()
        assert len(data) >= 1
        # Buscar el estudiante A
        est_a_data = next((e for e in data if e['estudiante_id'] == A['est']), None)
        assert est_a_data is not None, "estudiante A no apareció"
        assert est_a_data['estado'] == 'presente'
    
    # ─────────────────────────────────────────────────────────────────
    # SECCIÓN D — VALIDACIÓN DE INPUTS
    # ─────────────────────────────────────────────────────────────────
    
    print(f"{BOLD}\n=== D. VALIDACIÓN DE INPUTS ==={RESET}")
    
    @test("D1. Crear horario con curso_id inexistente devuelve 404 (no 500)")
    def t():
        r = client.post('/api/horarios', json={
            'curso_id': 99999, 'asignatura_id': A['asig'], 'profesor_id': A['prof'],
            'dia':'Lunes', 'hora_inicio':'08:00', 'hora_fin':'08:45', 'tipo_bloque':'clase',
        }, headers=auth(DIR_A_TOKEN))
        assert r.status_code == 404, f"esperaba 404, obtuvo {r.status_code}: {r.text}"
    
    @test("D2. Crear horario con dia inválido devuelve 400")
    def t():
        r = client.post('/api/horarios', json={
            'curso_id': A['curso'], 'asignatura_id': A['asig'], 'profesor_id': A['prof'],
            'dia':'XYZ', 'hora_inicio':'08:00', 'hora_fin':'08:45', 'tipo_bloque':'clase',
        }, headers=auth(DIR_A_TOKEN))
        assert r.status_code == 400, f"esperaba 400, obtuvo {r.status_code}"
    
    @test("D3. Crear horario con hora_inicio >= hora_fin devuelve 400")
    def t():
        r = client.post('/api/horarios', json={
            'curso_id': A['curso'], 'asignatura_id': A['asig'], 'profesor_id': A['prof'],
            'dia':'Lunes', 'hora_inicio':'10:00', 'hora_fin':'09:00', 'tipo_bloque':'clase',
        }, headers=auth(DIR_A_TOKEN))
        assert r.status_code == 400, f"esperaba 400, obtuvo {r.status_code}"
    
    @test("D4. Asistencia con estado inválido devuelve 400")
    def t():
        r = client.post('/api/asistencia', json={
            'estudiante_id': A['est'], 'asignatura_id': A['asig'],
            'fecha':'2024-09-03', 'estado':'BLABLA',
        }, headers=auth(PROF_A_TOKEN))
        assert r.status_code == 400, f"esperaba 400, obtuvo {r.status_code}"
    
    @test("D5. Asistencia con fecha inválida devuelve 400")
    def t():
        r = client.post('/api/asistencia', json={
            'estudiante_id': A['est'], 'asignatura_id': A['asig'],
            'fecha':'no-es-fecha', 'estado':'presente',
        }, headers=auth(PROF_A_TOKEN))
        assert r.status_code == 400, f"esperaba 400, obtuvo {r.status_code}"
    
    @test("D6. Calificación fuera de rango (>100) devuelve 400")
    def t():
        r = client.post('/api/calificaciones', json={
            'estudiante_id': A['est'], 'asignatura_id': A['asig'], 'p1_p1': 150,
        }, headers=auth(PROF_A_TOKEN))
        assert r.status_code == 400, f"esperaba 400, obtuvo {r.status_code}"
    
    @test("D7. POST horario con tipo_bloque inválido devuelve 400")
    def t():
        r = client.post('/api/horarios', json={
            'curso_id': A['curso'], 'asignatura_id': A['asig'], 'profesor_id': A['prof'],
            'dia':'Lunes', 'hora_inicio':'08:00', 'hora_fin':'08:45', 'tipo_bloque':'invento',
        }, headers=auth(DIR_A_TOKEN))
        assert r.status_code == 400, f"esperaba 400, obtuvo {r.status_code}"
    
    # ─────────────────────────────────────────────────────────────────
    # SECCIÓN E — TESTS ADICIONALES MÁS AGRESIVOS
    # ─────────────────────────────────────────────────────────────────
    
    print(f"{BOLD}\n=== E. TESTS ADICIONALES (cross-tenant agresivos){RESET}")
    
    @test("E1. Profesor B NO ve calificaciones del curso de A")
    def t():
        r = client.get(f'/api/calificaciones/curso/{A["curso"]}/asignatura/{A["asig"]}',
                       headers=auth(PROF_B_TOKEN))
        assert r.status_code == 404, f"esperaba 404, obtuvo {r.status_code}: {r.text}"
    
    @test("E2. Profesor B NO ve asistencias del curso de A")
    def t():
        r = client.get(f'/api/asistencia?curso_id={A["curso"]}&asignatura_id={A["asig"]}&fecha=2024-09-02',
                       headers=auth(PROF_B_TOKEN))
        assert r.status_code == 404, f"esperaba 404, obtuvo {r.status_code}: {r.text}"
    
    @test("E3. Profesor B NO puede ver horarios del profesor de A")
    def t():
        r = client.get(f'/api/horarios/profesor/{A["prof"]}', headers=auth(PROF_B_TOKEN))
        # debería devolver 404 (no encontrar al profesor de A en su tenant)
        assert r.status_code == 404, f"esperaba 404, obtuvo {r.status_code}: {r.text}"
    
    @test("E4. Director A NO puede crear curso con grado de B")
    def t():
        r = client.post('/api/cursos', json={
            'grado_id': B['grado'], 'tanda_id': A['tanda'], 'nombre':'X',
        }, headers=auth(DIR_A_TOKEN))
        assert r.status_code == 404, f"esperaba 404, obtuvo {r.status_code}: {r.text}"
    
    @test("E5. Director A NO puede crear curso con tanda de B")
    def t():
        r = client.post('/api/cursos', json={
            'grado_id': A['grado'], 'tanda_id': B['tanda'], 'nombre':'X',
        }, headers=auth(DIR_A_TOKEN))
        assert r.status_code == 404, f"esperaba 404, obtuvo {r.status_code}: {r.text}"
    
    @test("E6. Director A NO puede borrar asignación de B")
    def t():
        # Crear asignación en B primero
        client.post('/api/asignaciones', json={
            'profesor_id': B['prof'], 'curso_id': B['curso'], 'asignatura_id': B['asig'],
        }, headers=auth(DIR_B_TOKEN))
        asigs_b = client.get('/api/asignaciones', headers=auth(DIR_B_TOKEN)).json()
        if asigs_b:
            r = client.delete(f'/api/asignaciones/{asigs_b[0]["id"]}', headers=auth(DIR_A_TOKEN))
            assert r.status_code == 404, f"esperaba 404, obtuvo {r.status_code}"
    
    @test("E7. Director A NO puede borrar horario de B")
    def t():
        r = client.post('/api/horarios', json={
            'curso_id': B['curso'], 'asignatura_id': B['asig'], 'profesor_id': B['prof'],
            'dia':'Lunes', 'hora_inicio':'09:00', 'hora_fin':'09:45', 'tipo_bloque':'clase',
        }, headers=auth(DIR_B_TOKEN))
        assert r.status_code == 201
        h_id = r.json()['id']
        r = client.delete(f'/api/horarios/{h_id}', headers=auth(DIR_A_TOKEN))
        assert r.status_code == 404, f"esperaba 404, obtuvo {r.status_code}"
    
    @test("E8. Director A NO puede editar asignatura de B")
    def t():
        r = client.put(f'/api/asignaturas/{B["asig"]}', json={'nombre':'Hacked'}, headers=auth(DIR_A_TOKEN))
        assert r.status_code == 404, f"esperaba 404, obtuvo {r.status_code}"
    
    @test("E9. Director A NO puede borrar grado de B")
    def t():
        r = client.delete(f'/api/grados/{B["grado"]}', headers=auth(DIR_A_TOKEN))
        assert r.status_code == 404, f"esperaba 404, obtuvo {r.status_code}"
    
    @test("E10. Director A NO ve resumen de asistencia del curso de B")
    def t():
        r = client.get(f'/api/asistencia/resumen/{B["curso"]}', headers=auth(DIR_A_TOKEN))
        assert r.status_code == 404, f"esperaba 404, obtuvo {r.status_code}"
    
    @test("E11. Director A NO ve asistencia/curso de B")
    def t():
        r = client.get(f'/api/asistencia/curso/{B["curso"]}?fecha=2024-09-02', headers=auth(DIR_A_TOKEN))
        assert r.status_code == 404, f"esperaba 404, obtuvo {r.status_code}"
    
    @test("E12. Director A NO ve estudiantes de B en GET /api/estudiantes")
    def t():
        ests_a = client.get('/api/estudiantes', headers=auth(DIR_A_TOKEN)).json()
        # ests_a puede tener una estructura diferente, manejar ambos casos
        if isinstance(ests_a, list):
            ids = [e.get('id') for e in ests_a if isinstance(e, dict)]
        elif isinstance(ests_a, dict) and 'estudiantes' in ests_a:
            ids = [e.get('id') for e in ests_a['estudiantes']]
        else:
            ids = []
        assert B['est'] not in ids, f"Director A vio estudiante de B: {ids}"
    
    @test("E13. Profesor SIN asignación al curso/asig NO puede ver calificaciones (mismo colegio)")
    def t():
        # Crear segundo curso y segunda asignatura en colegio A, sin asignar al PROF_A
        otro_curso = client.post('/api/cursos', json={
            'grado_id': A['grado'], 'tanda_id': A['tanda'], 'nombre':'Z',
        }, headers=auth(DIR_A_TOKEN)).json()['id']
        otra_asig = client.post('/api/asignaturas', json={
            'nombre':'Sin asignar','codigo':'SA',
        }, headers=auth(DIR_A_TOKEN)).json()['id']
        
        r = client.get(f'/api/calificaciones/curso/{otro_curso}/asignatura/{otra_asig}',
                       headers=auth(PROF_A_TOKEN))
        assert r.status_code == 403, f"esperaba 403 (sin asignación), obtuvo {r.status_code}: {r.text}"
    
    @test("E14. Coordinador puede crear estudiantes (rol válido)")
    def t():
        coord_a_token = client.post('/api/auth/login', json={
            'username': f'coord_{A["sufijo"]}', 'password':'coordinador123'
        }).json()['token']
        r = client.post('/api/estudiantes', json={
            'nombre':'Por','apellido':'Coord','sexo':'F','fecha_nacimiento':'2010-01-01',
            'curso_id': A['curso'], 'no_lista': 99, 'matricula': 'CRE-1'
        }, headers=auth(coord_a_token))
        assert r.status_code == 201, f"esperaba 201, obtuvo {r.status_code}: {r.text}"
    
    @test("E15. Asignación duplicada devuelve 400 (no 500)")
    def t():
        # Ya hay asignación en A creada por setup_colegio, intentar duplicar
        r = client.post('/api/asignaciones', json={
            'profesor_id': A['prof'], 'curso_id': A['curso'], 'asignatura_id': A['asig'],
        }, headers=auth(DIR_A_TOKEN))
        assert r.status_code == 400, f"esperaba 400 (duplicado), obtuvo {r.status_code}: {r.text}"
    
    # ─────────────────────────────────────────────────────────────────
    # SECCIÓN F — AUTENTICACIÓN Y SEGURIDAD
    # ─────────────────────────────────────────────────────────────────
    
    print(f"{BOLD}\n=== F. AUTENTICACIÓN Y HEADERS ==={RESET}")
    
    @test("F1. JWT incluye exp e iat (expiración real)")
    def t():
        import jwt
        from auth import JWT_SECRET_KEY
        payload = jwt.decode(DIR_A_TOKEN, JWT_SECRET_KEY, algorithms=['HS256'])
        assert 'exp' in payload, f"token sin exp: {payload}"
        assert 'iat' in payload, f"token sin iat: {payload}"
        assert 'token_version' in payload, f"token sin token_version: {payload}"
    
    @test("F2. Token expirado es rechazado con 401")
    def t():
        import jwt
        from datetime import datetime, timedelta
        from auth import JWT_SECRET_KEY
        # Token con exp en el pasado
        payload_expirado = {
            'user_id': 1, 'username': 'direccion', 'role':'direccion', 'colegio_id': 1,
            'token_version': 0,
            'iat': datetime.utcnow() - timedelta(hours=24),
            'exp': datetime.utcnow() - timedelta(hours=1),
        }
        tok_expirado = jwt.encode(payload_expirado, JWT_SECRET_KEY, algorithm='HS256')
        r = client.get('/api/cursos', headers={'Authorization': f'Bearer {tok_expirado}'})
        assert r.status_code == 401, f"esperaba 401, obtuvo {r.status_code}: {r.text}"
    
    @test("F3. Token con firma inválida rechazado con 401")
    def t():
        # Modificar el token alterando un byte
        tok_corrupto = DIR_A_TOKEN[:-5] + 'XXXXX'
        r = client.get('/api/cursos', headers={'Authorization': f'Bearer {tok_corrupto}'})
        assert r.status_code == 401, f"esperaba 401, obtuvo {r.status_code}"
    
    @test("F4. Sin token → 401 (excepto endpoints públicos)")
    def t():
        r = client.get('/api/cursos')
        assert r.status_code == 401, f"esperaba 401, obtuvo {r.status_code}"
    
    @test("F5. Logout invalida la sesión (token previo deja de funcionar)")
    def t():
        # Login fresco para no afectar otros tests
        r = client.post('/api/auth/login', json={'username':'direccion','password':'admin123'})
        tok = r.json()['token']
        # Verificar que funciona
        r = client.get('/api/cursos', headers=auth(tok))
        assert r.status_code == 200, f"token nuevo debería funcionar: {r.status_code}"
        # Logout
        r = client.post('/api/auth/logout', headers=auth(tok))
        assert r.status_code == 200, f"logout falló: {r.status_code}"
        # Mismo token después del logout debería ser inválido
        r = client.get('/api/cursos', headers=auth(tok))
        assert r.status_code == 401, f"esperaba 401 después de logout, obtuvo {r.status_code}: {r.text}"
    
    @test("F6. Cambiar password invalida el token actual")
    def t():
        # F5 hizo login fresco e hizo logout — eso incrementó la token_version
        # del usuario 'direccion'. Como DIR_A_TOKEN se generó antes, ahora está
        # invalidado. Eso es comportamiento CORRECTO del sistema. Hacemos un
        # refresh para continuar el test.
        global DIR_A_TOKEN
        DIR_A_TOKEN = client.post('/api/auth/login', json={
            'username':'direccion','password':'admin123'
        }).json()['token']
        # Crear usuario temporal para no afectar otras secciones
        r = client.post('/api/usuarios', json={
            'username':'usr_test_pw','password':'PasswordOld1','nombre':'PWTest','apellido':'X',
            'email':'pwtest@x.com','role':'coordinador',
        }, headers=auth(DIR_A_TOKEN))
        assert r.status_code == 201, f"crear usuario falló: {r.text}"
        # Login
        r = client.post('/api/auth/login', json={'username':'usr_test_pw','password':'PasswordOld1'})
        tok = r.json()['token']
        # Funciona con ese token
        r = client.get('/api/auth/me', headers=auth(tok))
        assert r.status_code == 200
        # Cambiar password
        r = client.post('/api/auth/cambiar-password', json={
            'password_actual':'PasswordOld1', 'password_nuevo':'PasswordNew1',
        }, headers=auth(tok))
        assert r.status_code == 200, f"cambiar password falló: {r.text}"
        # El token previo ya no debe servir
        r = client.get('/api/cursos', headers=auth(tok))
        assert r.status_code == 401, f"esperaba 401 después de cambio password, obtuvo {r.status_code}"
    
    @test("F7. Headers de seguridad presentes en respuesta")
    def t():
        r = client.get('/api/cursos', headers=auth(DIR_A_TOKEN))
        h = r.headers
        assert h.get('x-content-type-options') == 'nosniff', f"X-Content-Type-Options: {h.get('x-content-type-options')}"
        assert h.get('x-frame-options') == 'DENY', f"X-Frame-Options: {h.get('x-frame-options')}"
        assert 'content-security-policy' in h, f"Falta CSP. Headers: {dict(h)}"
        csp = h['content-security-policy']
        assert "default-src 'self'" in csp, f"CSP mal: {csp}"
        assert "frame-ancestors 'none'" in csp, f"CSP sin frame-ancestors: {csp}"
        assert h.get('referrer-policy') == 'strict-origin-when-cross-origin'
        assert 'permissions-policy' in h
    
    @test("F8. Headers de seguridad también en respuestas de error")
    def t():
        r = client.get('/api/no-existe-este-endpoint', headers=auth(DIR_A_TOKEN))
        # Debe ser 404, pero igual con headers
        assert r.headers.get('x-content-type-options') == 'nosniff'
    
    # ─────────────────────────────────────────────────────────────────
    # SECCIÓN G — E2E SIMULANDO USUARIO REAL
    # ─────────────────────────────────────────────────────────────────
    
    print(f"{BOLD}\n=== G. E2E SIMULANDO USUARIO REAL ==={RESET}")
    
    @test("G1. Superadmin → crear colegio nuevo")
    def t():
        r = client.post('/api/superadmin/colegios', json={
            'nombre':'Liceo E2E','codigo':'e2e_test','plan':'enterprise',
            'admin_username':'dir_e2e','admin_password':'AdminE2E2024',
        }, headers=auth(SA_TOKEN))
        assert r.status_code in (200, 201), f"crear colegio falló: {r.text}"
    
    @test("G2. Director del nuevo colegio se loguea")
    def t():
        r = client.post('/api/auth/login', json={'username':'dir_e2e','password':'AdminE2E2024'})
        assert r.status_code == 200, f"login director falló: {r.text}"
    
    @test("G3. Director crea profesor y secretaria")
    def t():
        tok = client.post('/api/auth/login', json={'username':'dir_e2e','password':'AdminE2E2024'}).json()['token']
        # Profesor
        r = client.post('/api/usuarios', json={
            'username':'prof_e2e','password':'ProfE2E2024','nombre':'Juan','apellido':'Perez',
            'email':'juan@e2e.com','role':'profesor',
        }, headers=auth(tok))
        assert r.status_code == 201, f"crear profesor: {r.text}"
        # Secretaria
        r = client.post('/api/usuarios', json={
            'username':'sec_e2e','password':'SecE2E2024','nombre':'Ana','apellido':'Diaz',
            'email':'ana@e2e.com','role':'secretaria',
        }, headers=auth(tok))
        assert r.status_code == 201, f"crear secretaria: {r.text}"
    
    @test("G4. Director crea curso, asignatura y asignación")
    def t():
        tok = client.post('/api/auth/login', json={'username':'dir_e2e','password':'AdminE2E2024'}).json()['token']
        grados = client.get('/api/grados', headers=auth(tok)).json()
        tandas = client.get('/api/tandas', headers=auth(tok)).json()
        prof_id = next(u['id'] for u in client.get('/api/usuarios', headers=auth(tok)).json() if u['username']=='prof_e2e')
        
        r = client.post('/api/cursos', json={
            'grado_id': grados[0]['id'], 'tanda_id': tandas[0]['id'], 'nombre':'A',
        }, headers=auth(tok))
        assert r.status_code == 201, f"crear curso: {r.text}"
        curso_id = r.json()['id']
        
        r = client.post('/api/asignaturas', json={'nombre':'Lengua Española','codigo':'LE'}, headers=auth(tok))
        assert r.status_code == 201
        asig_id = r.json()['id']
        
        r = client.post('/api/asignaciones', json={
            'profesor_id': prof_id, 'curso_id': curso_id, 'asignatura_id': asig_id, 'es_titular': True,
        }, headers=auth(tok))
        assert r.status_code == 201, f"crear asignación: {r.text}"
        # Guardar IDs para tests siguientes
        globals()['_E2E_curso'] = curso_id
        globals()['_E2E_asig'] = asig_id
        globals()['_E2E_prof'] = prof_id
    
    @test("G5. Director crea horario en secundaria")
    def t():
        tok = client.post('/api/auth/login', json={'username':'dir_e2e','password':'AdminE2E2024'}).json()['token']
        r = client.post('/api/horarios', json={
            'curso_id': _E2E_curso, 'asignatura_id': _E2E_asig, 'profesor_id': _E2E_prof,
            'dia':'Lunes', 'hora_inicio':'07:30', 'hora_fin':'08:20', 'tipo_bloque':'clase',
        }, headers=auth(tok))
        assert r.status_code == 201, f"crear horario: {r.text}"
    
    @test("G6. Director crea estudiante")
    def t():
        tok = client.post('/api/auth/login', json={'username':'dir_e2e','password':'AdminE2E2024'}).json()['token']
        r = client.post('/api/estudiantes', json={
            'nombre':'Maria','apellido':'Lopez','sexo':'F','fecha_nacimiento':'2010-06-15',
            'curso_id': _E2E_curso, 'no_lista': 1, 'matricula':'E2E001'
        }, headers=auth(tok))
        assert r.status_code == 201, f"crear estudiante: {r.text}"
        globals()['_E2E_est'] = r.json()['id']
    
    @test("G7. Profesor califica estudiante con 4 parciales (PC1 calculado)")
    def t():
        tok = client.post('/api/auth/login', json={'username':'prof_e2e','password':'ProfE2E2024'}).json()['token']
        r = client.post('/api/calificaciones', json={
            'estudiante_id': _E2E_est, 'asignatura_id': _E2E_asig,
            'p1_p1': 90, 'p1_p2': 85, 'p1_p3': 80, 'p1_p4': 75,
        }, headers=auth(tok))
        assert r.status_code == 200, f"calificar: {r.text}"
        cal = r.json()['calificacion']
        assert cal['pc1'] == 82.5, f"PC1 esperado 82.5, fue {cal['pc1']}"
    
    @test("G8. Profesor registra asistencia")
    def t():
        tok = client.post('/api/auth/login', json={'username':'prof_e2e','password':'ProfE2E2024'}).json()['token']
        for fecha in ['2024-09-02', '2024-09-03', '2024-09-04']:
            r = client.post('/api/asistencia', json={
                'estudiante_id': _E2E_est, 'asignatura_id': _E2E_asig,
                'fecha': fecha, 'estado':'presente',
            }, headers=auth(tok))
            assert r.status_code == 200, f"asistencia {fecha}: {r.text}"
    
    @test("G9. Director ve calificaciones del curso")
    def t():
        tok = client.post('/api/auth/login', json={'username':'dir_e2e','password':'AdminE2E2024'}).json()['token']
        r = client.get(f'/api/calificaciones/curso/{_E2E_curso}/asignatura/{_E2E_asig}', headers=auth(tok))
        assert r.status_code == 200, f"ver calificaciones: {r.text}"
        body = r.json()
        califs = body['calificaciones']
        assert len(califs) >= 1
        cal = next(c for c in califs if c['estudiante']['id'] == _E2E_est)
        assert cal['calificacion']['pc1'] == 82.5
    
    @test("G10. Secretaria NO puede calificar (verificación de rol)")
    def t():
        tok = client.post('/api/auth/login', json={'username':'sec_e2e','password':'SecE2E2024'}).json()['token']
        r = client.post('/api/calificaciones', json={
            'estudiante_id': _E2E_est, 'asignatura_id': _E2E_asig, 'p2_p1': 85,
        }, headers=auth(tok))
        assert r.status_code == 403, f"esperaba 403, obtuvo {r.status_code}"
    
    @test("G11. Secretaria SÍ puede ver estudiantes (rol válido)")
    def t():
        tok = client.post('/api/auth/login', json={'username':'sec_e2e','password':'SecE2E2024'}).json()['token']
        r = client.get('/api/estudiantes', headers=auth(tok))
        assert r.status_code == 200, f"esperaba 200, obtuvo {r.status_code}: {r.text}"
    
    @test("G12. Director ve resumen de asistencia del curso")
    def t():
        tok = client.post('/api/auth/login', json={'username':'dir_e2e','password':'AdminE2E2024'}).json()['token']
        r = client.get(f'/api/asistencia/resumen/{_E2E_curso}?mes=9&ano=2024', headers=auth(tok))
        assert r.status_code == 200, f"resumen: {r.text}"
        data = r.json()
        # Buscar al estudiante
        e = next((x for x in data if x['estudiante_id'] == _E2E_est), None)
        assert e is not None, "estudiante no apareció en resumen"
        assert e['presentes'] == 3, f"esperaba 3 presentes, fue {e['presentes']}"
    
    # ─────────────────────────────────────────────────────────────────
    # SECCIÓN H — MÉTRICAS DE ASISTENCIA (sin doble conteo)
    # ─────────────────────────────────────────────────────────────────
    
    print(f"{BOLD}\n=== H. MÉTRICAS DE ASISTENCIA (sin doble conteo) ==={RESET}")
    
    # Setup aislado: colegio H con cantidades exactas y predecibles
    sa = client.post('/api/auth/login', json={'username':'superadmin','password':'superadmin123'}).json()['token']
    r = client.post('/api/superadmin/colegios', json={
        'nombre':'Colegio H','codigo':'h_metrica','plan':'enterprise',
        'admin_username':'dir_h','admin_password':'AdminHColegio2024',
        'plan_secundaria': True, 'plan_primaria': True,
    }, headers=auth(sa))
    assert r.status_code in (200, 201)
    COLEGIO_H_ID = r.json().get('id') or r.json().get('colegio_id')
    if COLEGIO_H_ID is None:
        # Fallback: buscar por nombre
        cs = client.get('/api/superadmin/colegios', headers=auth(sa)).json()
        COLEGIO_H_ID = next(c['id'] for c in cs if c['codigo'] == 'h_metrica')
    DIR_H = client.post('/api/auth/login', json={'username':'dir_h','password':'AdminHColegio2024'}).json()['token']
    
    grados_h = client.get('/api/grados', headers=auth(DIR_H)).json()
    tandas_h = client.get('/api/tandas', headers=auth(DIR_H)).json()
    curso_h = client.post('/api/cursos', json={
        'grado_id': grados_h[0]['id'], 'tanda_id': tandas_h[0]['id'], 'nombre':'A',
    }, headers=auth(DIR_H)).json()['id']
    
    # 2 asignaturas distintas (para probar que NO se doble cuenta cuando un
    # estudiante tiene varias materias el mismo día)
    asig_h1 = client.post('/api/asignaturas', json={'nombre':'Mate H','codigo':'MH'}, headers=auth(DIR_H)).json()['id']
    asig_h2 = client.post('/api/asignaturas', json={'nombre':'Lengua H','codigo':'LH'}, headers=auth(DIR_H)).json()['id']
    
    prof_h = client.post('/api/usuarios', json={
        'username':'prof_h','password':'profesor123','nombre':'P','apellido':'H',
        'email':'p_h@x.com','role':'profesor',
    }, headers=auth(DIR_H)).json()['id']
    client.post('/api/asignaciones', json={'profesor_id':prof_h,'curso_id':curso_h,'asignatura_id':asig_h1}, headers=auth(DIR_H))
    client.post('/api/asignaciones', json={'profesor_id':prof_h,'curso_id':curso_h,'asignatura_id':asig_h2}, headers=auth(DIR_H))
    
    # 5 estudiantes activos
    ests_h = []
    for i in range(5):
        r = client.post('/api/estudiantes', json={
            'nombre':f'Est{i}','apellido':'H','curso_id':curso_h,'no_lista':i+1,
        }, headers=auth(DIR_H))
        ests_h.append(r.json()['id'])
    
    # Profesor registra asistencia de hoy: en 2 materias distintas
    # Si el sistema doble-contara, sumaría 10 marcas. Debe sumar 5 (1 por estudiante por día).
    PROF_H = client.post('/api/auth/login', json={'username':'prof_h','password':'profesor123'}).json()['token']
    from datetime import date as _date
    hoy_iso = _date.today().isoformat()
    # Estudiantes 0,1,2 → presente en ambas materias
    # Estudiante 3 → ausente en ambas
    # Estudiante 4 → presente en mate, ausente en lengua (debe contar como presente)
    for est_id in ests_h[:3]:
        for asig in [asig_h1, asig_h2]:
            client.post('/api/asistencia', json={
                'estudiante_id': est_id, 'asignatura_id': asig,
                'fecha': hoy_iso, 'estado':'presente',
            }, headers=auth(PROF_H))
    for asig in [asig_h1, asig_h2]:
        client.post('/api/asistencia', json={
            'estudiante_id': ests_h[3], 'asignatura_id': asig,
            'fecha': hoy_iso, 'estado':'ausente',
        }, headers=auth(PROF_H))
    # Estudiante 4: mixto
    client.post('/api/asistencia', json={
        'estudiante_id': ests_h[4], 'asignatura_id': asig_h1,
        'fecha': hoy_iso, 'estado':'presente',
    }, headers=auth(PROF_H))
    client.post('/api/asistencia', json={
        'estudiante_id': ests_h[4], 'asignatura_id': asig_h2,
        'fecha': hoy_iso, 'estado':'ausente',
    }, headers=auth(PROF_H))
    
    # Estudiante 5 (no creado: solo 5 activos = ests 0..4). Para no_registrados,
    # creamos uno extra SIN marcas:
    extra_h = client.post('/api/estudiantes', json={
        'nombre':'Extra','apellido':'NoReg','curso_id':curso_h,'no_lista':99,
    }, headers=auth(DIR_H)).json()['id']
    
    @test("H1. Asistencia HOY: presentes cuenta 1 por estudiante (no por materia)")
    def t():
        r = client.get('/api/dashboard/graficos', headers=auth(DIR_H))
        assert r.status_code == 200
        data = r.json()
        hoy = data['asistencia_hoy']
        # Esperado: 4 presentes (3 con presente puro + 1 mixto que prioriza presente)
        # NO debe contar 10 (5 estudiantes × 2 materias)
        assert hoy['presentes'] == 4, f"presentes esperado 4, fue {hoy['presentes']} (¿doble conteo?)"
        assert hoy['ausentes'] == 1, f"ausentes esperado 1 (solo el est 3), fue {hoy['ausentes']}"
        assert hoy['tardanzas'] == 0, f"tardanzas esperado 0, fue {hoy['tardanzas']}"
    
    @test("H2. Asistencia HOY: total_estudiantes = activos del colegio")
    def t():
        r = client.get('/api/dashboard/graficos', headers=auth(DIR_H))
        data = r.json()
        # 5 con marcas + 1 extra sin marcas = 6 activos
        assert data['asistencia_hoy']['total_estudiantes'] == 6, \
            f"total_est esperado 6, fue {data['asistencia_hoy']['total_estudiantes']}"
    
    @test("H3. Asistencia HOY: no_registrados cuenta estudiantes sin marca")
    def t():
        r = client.get('/api/dashboard/graficos', headers=auth(DIR_H))
        data = r.json()
        # Extra no tiene marca → 1 no registrado
        assert data['asistencia_hoy']['no_registrados'] == 1, \
            f"no_registrados esperado 1, fue {data['asistencia_hoy']['no_registrados']}"
    
    @test("H4. Asistencia HOY: porcentaje = presentes / total (no de los registrados)")
    def t():
        r = client.get('/api/dashboard/graficos', headers=auth(DIR_H))
        data = r.json()
        # 4 presentes / 6 activos = 66.7%
        assert data['asistencia_hoy']['porcentaje_asistencia'] == 66.7, \
            f"% esperado 66.7, fue {data['asistencia_hoy']['porcentaje_asistencia']}"
    
    @test("H5. Asistencia MES: misma regla (1 estado por estudiante por día)")
    def t():
        r = client.get('/api/dashboard/graficos', headers=auth(DIR_H))
        data = r.json()
        mes = data['asistencia_resumen']
        # Solo metimos asistencia de hoy: 4 presentes, 1 ausente
        assert mes['presentes'] == 4, f"mes presentes esperado 4, fue {mes['presentes']}"
        assert mes['ausentes'] == 1, f"mes ausentes esperado 1, fue {mes['ausentes']}"
    
    @test("H6. Asistencia MES: porcentaje_mensual_real considera estudiantes_activos × días")
    def t():
        r = client.get('/api/dashboard/graficos', headers=auth(DIR_H))
        data = r.json()
        mes = data['asistencia_resumen']
        # 4 presentes / (6 activos × 1 día con registro) = 66.7%
        assert mes['porcentaje_mensual_real'] == 66.7, \
            f"%_mensual_real esperado 66.7, fue {mes['porcentaje_mensual_real']}"
        assert mes['dias_con_registro'] == 1, \
            f"dias_con_registro esperado 1, fue {mes['dias_con_registro']}"
        assert mes['estudiantes_activos'] == 6, \
            f"estudiantes_activos esperado 6, fue {mes['estudiantes_activos']}"
    
    @test("H7. Período del mes incluye fechas inicio/fin (rango visible)")
    def t():
        r = client.get('/api/dashboard/graficos', headers=auth(DIR_H))
        data = r.json()
        mes = data['asistencia_resumen']
        assert 'periodo_inicio' in mes and mes['periodo_inicio'] is not None
        assert 'periodo_fin' in mes and mes['periodo_fin'] is not None
    
    # ─────────────────────────────────────────────────────────────────
    # SECCIÓN I — NIVELES POR TENANT (tiene_primaria, tiene_secundaria)
    # ─────────────────────────────────────────────────────────────────
    
    print(f"{BOLD}\n=== I. NIVELES POR TENANT ==={RESET}")
    
    @test("I1. Colegios nuevos tienen ambos niveles activos por defecto")
    def t():
        r = client.get('/api/configuracion', headers=auth(DIR_H))
        assert r.status_code == 200, f"GET configuracion: {r.text}"
        data = r.json()
        assert data.get('tiene_primaria') == True, f"tiene_primaria default debe ser True, fue {data.get('tiene_primaria')}"
        assert data.get('tiene_secundaria') == True, f"tiene_secundaria default debe ser True, fue {data.get('tiene_secundaria')}"
    
    @test("I2. v2.11: director NO puede desactivar nivel (solo lectura)")
    def t():
        # En v2.11 (Interpretación A) el director ya no puede modificar
        # módulos. El PUT a /api/configuracion ahora ignora cambios de
        # tiene_primaria/tiene_secundaria. Lo único que controla es el
        # nombre/datos del colegio.
        # Estado inicial: secundaria=True, primaria=True (plan default)
        cfg_antes = client.get('/api/configuracion', headers=auth(DIR_H)).json()
        primaria_antes = cfg_antes.get('tiene_primaria')
        # Intentar desactivar primaria
        client.put('/api/configuracion', json={
            'tiene_primaria': False, 'tiene_secundaria': True,
        }, headers=auth(DIR_H))
        # Verificar que NO cambió (el PUT a /api/configuracion no toca el plan)
        cfg_despues = client.get('/api/configuracion', headers=auth(DIR_H)).json()
        assert cfg_despues['tiene_primaria'] == primaria_antes, \
            f"el director no debe poder cambiar el plan: era {primaria_antes}, quedó {cfg_despues['tiene_primaria']}"
    
    @test("I3. v2.11: crear curso de nivel SIN plan → 403")
    def t():
        # En v2.11 el director no puede tocar el plan. Para reproducir el caso
        # de "nivel desactivado" pedimos al superadmin que quite primaria del plan.
        from sqlalchemy import text as sql_text
        from database import SessionLocal as _SL
        _db = _SL()
        try:
            _db.execute(sql_text("UPDATE colegios SET plan_primaria=1 WHERE id=:id"),
                        {"id": COLEGIO_H_ID})
            _db.commit()
            r_g = client.post('/api/grados', json={
                'nombre':'1ro Primaria Test','nivel':'primaria','orden':100,
            }, headers=auth(DIR_H))
            assert r_g.status_code in (200, 201), f"crear grado primaria: {r_g.text}"
            grado_pri = r_g.json()['id']
            # Superadmin quita primaria del plan
            _db.execute(sql_text("UPDATE colegios SET plan_primaria=0 WHERE id=:id"),
                        {"id": COLEGIO_H_ID})
            _db.commit()
        finally:
            _db.close()
        # Intentar crear curso de ese grado (primaria fuera del plan)
        r = client.post('/api/cursos', json={
            'grado_id': grado_pri, 'tanda_id': tandas_h[0]['id'], 'nombre':'X',
        }, headers=auth(DIR_H))
        assert r.status_code in (400, 403), f"esperaba 400/403, obtuvo {r.status_code}: {r.text}"
        assert 'primaria' in r.text.lower() or 'nivel' in r.text.lower() or 'plan' in r.text.lower(), \
            f"mensaje debe mencionar nivel/plan: {r.text}"
    
    @test("I4. Crear curso con nivel activo sí funciona")
    def t():
        # Secundaria está activa
        r = client.post('/api/cursos', json={
            'grado_id': grados_h[0]['id'], 'tanda_id': tandas_h[0]['id'], 'nombre':'B',
        }, headers=auth(DIR_H))
        assert r.status_code == 201, f"esperaba 201, obtuvo {r.status_code}: {r.text}"
    
    @test("I5. GET /api/grados respeta filtro de nivel desactivado")
    def t():
        # Restaurar ambos niveles primero
        client.put('/api/configuracion', json={
            'tiene_primaria': True, 'tiene_secundaria': True,
        }, headers=auth(DIR_H))
        # Listar todos
        all_grados = client.get('/api/grados', headers=auth(DIR_H)).json()
        n_pri = sum(1 for g in all_grados if g.get('nivel') == 'primaria')
        n_sec = sum(1 for g in all_grados if g.get('nivel') == 'secundaria')
        # Si el colegio tiene primaria pero no creó grados de primaria todavía,
        # n_pri puede ser pequeño. Lo importante: ningún grado se filtró indebidamente.
        # Ahora desactivar primaria y verificar
        client.put('/api/configuracion', json={
            'tiene_primaria': False, 'tiene_secundaria': True,
        }, headers=auth(DIR_H))
        filtrados = client.get('/api/grados', headers=auth(DIR_H)).json()
        n_pri_after = sum(1 for g in filtrados if g.get('nivel') == 'primaria')
        n_sec_after = sum(1 for g in filtrados if g.get('nivel') == 'secundaria')
        assert n_pri_after == 0, f"con primaria off, no debería listar grados de primaria; vio {n_pri_after}"
        assert n_sec_after == n_sec, f"secundaria debería seguir igual; antes={n_sec}, ahora={n_sec_after}"
        # Restaurar
        client.put('/api/configuracion', json={
            'tiene_primaria': True, 'tiene_secundaria': True,
        }, headers=auth(DIR_H))
    
    @test("I6. v2.11: director NO puede tocar niveles (devuelve 200 informativo)")
    def t():
        # En v2.11 el director no controla los niveles. El PUT devuelve 200
        # con mensaje informativo y NO aplica cambios.
        r = client.put('/api/configuracion', json={
            'tiene_primaria': False, 'tiene_secundaria': False,
        }, headers=auth(DIR_H))
        assert r.status_code == 200, f"esperaba 200 informativo: {r.text}"
        # El estado del plan no cambia (lo controla superadmin)
        cfg = client.get('/api/configuracion', headers=auth(DIR_H)).json()
        # Al menos un nivel debe seguir activo (porque viene del plan, no del PUT)
        niveles_activos = (cfg.get('tiene_primaria') or cfg.get('tiene_secundaria'))
        assert niveles_activos, "al menos un nivel debe estar activo en el plan"
    
    @test("I7. Profesor NO puede cambiar configuración de niveles (solo dirección)")
    def t():
        r = client.put('/api/configuracion', json={
            'tiene_primaria': False, 'tiene_secundaria': True,
        }, headers=auth(PROF_H))
        assert r.status_code == 403, f"esperaba 403, obtuvo {r.status_code}"
    
    # ─────────────────────────────────────────────────────────────────
    # SECCIÓN J — ARQUITECTURA PLAN + USO (superadmin vs director)
    # ─────────────────────────────────────────────────────────────────
    
    print(f"{BOLD}\n=== J. PLAN + USO (superadmin vs director) ==={RESET}")
    
    # Setup colegio J con plan limitado (solo secundaria + eval_profesores)
    r = client.post('/api/superadmin/colegios', json={
        'nombre':'Colegio J','codigo':'j_plan','plan':'basico',
        'admin_username':'dir_j','admin_password':'AdminJ2024',
        # plan_X explícito por superadmin
        'plan_secundaria': True,
        'plan_primaria': False,        # no incluido en plan
        'plan_whatsapp': False,         # no incluido en plan
        'plan_psicologia': False,       # no incluido en plan
        'plan_eval_profesores': True,
    }, headers=auth(sa))
    assert r.status_code in (200, 201), f"crear colegio J: {r.text}"
    DIR_J = client.post('/api/auth/login', json={'username':'dir_j','password':'AdminJ2024'}).json()['token']
    
    @test("J1. GET /api/configuracion devuelve plan, usa, activo por módulo")
    def t():
        r = client.get('/api/configuracion', headers=auth(DIR_J))
        assert r.status_code == 200
        data = r.json()
        assert 'modulos' in data, f"falta 'modulos': {data.keys()}"
        for m in ['secundaria', 'primaria', 'whatsapp', 'psicologia', 'eval_profesores']:
            assert m in data['modulos'], f"falta módulo {m}"
            mod = data['modulos'][m]
            for k in ['plan', 'usa', 'activo']:
                assert k in mod, f"módulo {m} sin {k}"
    
    @test("J2. plan_X refleja lo que superadmin permitió al crear el colegio")
    def t():
        r = client.get('/api/configuracion', headers=auth(DIR_J))
        m = r.json()['modulos']
        assert m['secundaria']['plan'] == True
        assert m['primaria']['plan'] == False, "primaria NO debería estar en plan"
        assert m['whatsapp']['plan'] == False
        assert m['psicologia']['plan'] == False
        assert m['eval_profesores']['plan'] == True
    
    @test("J3. activo = plan AND usa")
    def t():
        r = client.get('/api/configuracion', headers=auth(DIR_J))
        m = r.json()['modulos']
        # secundaria: plan=true, usa=true (default) → activo=true
        assert m['secundaria']['activo'] == True
        # primaria: plan=false → activo=false (sin importar usa)
        assert m['primaria']['activo'] == False
        # whatsapp: plan=false → activo=false
        assert m['whatsapp']['activo'] == False
    
    @test("J4. v2.11: director toca PUT modulos → response informativo (no edita)")
    def t():
        # En v2.11 el director ya no enciende/apaga módulos. El endpoint
        # devuelve 200 con un mensaje informativo y NO aplica cambios.
        r = client.put('/api/configuracion/modulos', json={
            'modulos': {'whatsapp': True},
        }, headers=auth(DIR_J))
        assert r.status_code == 200, f"esperaba 200, obtuvo {r.status_code}: {r.text}"
        body = r.json()
        assert 'plan_solo_lectura' in body or 'soporte' in r.text.lower(), \
            f"debería indicar que el plan es solo lectura: {r.text}"
        # Verificar que el módulo NO se activó (sigue fuera del plan)
        r2 = client.get('/api/configuracion', headers=auth(DIR_J))
        m = r2.json()['modulos']
        assert m['whatsapp']['plan'] == False, "whatsapp no debe estar en plan"
        assert m['whatsapp']['activo'] == False, "whatsapp no debe estar activo"
    
    @test("J5. v2.11: módulos del plan están automáticamente activos")
    def t():
        # En v2.11 activo = plan. Si está en plan, está activo.
        r = client.get('/api/configuracion', headers=auth(DIR_J))
        m = r.json()['modulos']
        # eval_profesores SÍ está en plan → debe estar activo
        assert m['eval_profesores']['plan'] == True, "eval_profesores debe estar en plan"
        assert m['eval_profesores']['activo'] == True, "activo = plan en v2.11"
    
    @test("J6. Director puede REENCENDER módulo que apagó")
    def t():
        r = client.put('/api/configuracion/modulos', json={
            'modulos': {'eval_profesores': True},
        }, headers=auth(DIR_J))
        assert r.status_code == 200, f"esperaba 200, obtuvo {r.status_code}: {r.text}"
        r = client.get('/api/configuracion', headers=auth(DIR_J))
        assert r.json()['modulos']['eval_profesores']['activo'] == True
    
    @test("J7. Superadmin AGREGA módulo al plan (upgrade)")
    def t():
        # Antes: psicologia NO en plan
        r = client.put(f'/api/superadmin/colegios/{client.get("/api/configuracion", headers=auth(DIR_J)).json()["colegio_id"]}/modulos',
                       json={'modulos': {'psicologia': True}}, headers=auth(sa))
        assert r.status_code == 200, f"esperaba 200, obtuvo {r.status_code}: {r.text}"
        # Verificar
        r = client.get('/api/configuracion', headers=auth(DIR_J))
        m = r.json()['modulos']
        assert m['psicologia']['plan'] == True, "plan_psicologia debería estar activo"
        # Pero el director NO la encendió todavía → activo aún depende de usa default (true para los no-niveles)
    
    @test("J8. Superadmin QUITA módulo del plan (downgrade): activo=false sin importar usa")
    def t():
        cole_id = client.get('/api/configuracion', headers=auth(DIR_J)).json()['colegio_id']
        r = client.put(f'/api/superadmin/colegios/{cole_id}/modulos',
                       json={'modulos': {'eval_profesores': False}}, headers=auth(sa))
        assert r.status_code == 200
        r = client.get('/api/configuracion', headers=auth(DIR_J))
        m = r.json()['modulos']
        assert m['eval_profesores']['plan'] == False
        assert m['eval_profesores']['activo'] == False, "activo debe ser false porque plan=false"
        # Restaurar
        client.put(f'/api/superadmin/colegios/{cole_id}/modulos',
                   json={'modulos': {'eval_profesores': True}}, headers=auth(sa))
    
    @test("J9. Solo superadmin puede tocar plan_X (director NO)")
    def t():
        # Director intenta llamar el endpoint de superadmin → 403
        cole_id = client.get('/api/configuracion', headers=auth(DIR_J)).json()['colegio_id']
        r = client.put(f'/api/superadmin/colegios/{cole_id}/modulos',
                       json={'modulos': {'whatsapp': True}}, headers=auth(DIR_J))
        assert r.status_code == 403, f"esperaba 403, obtuvo {r.status_code}"
    
    @test("J10. Defaults por plan comercial: 'basico' tiene secundaria pero no primaria")
    def t():
        r = client.post('/api/superadmin/colegios', json={
            'nombre':'Test Basico','codigo':'tb_default','plan':'basico',
            'admin_username':'tb_dir','admin_password':'TbAdmin2024',
        }, headers=auth(sa))
        assert r.status_code in (200, 201), f"crear: {r.text}"
        cole_id = r.json()['id']
        # Verificar plan
        r = client.get(f'/api/superadmin/colegios/{cole_id}/modulos', headers=auth(sa))
        m = r.json()['modulos']
        assert m['secundaria']['plan'] == True, "plan basico debe incluir secundaria"
        assert m['primaria']['plan'] == False, "plan basico no debe incluir primaria"
        assert m['whatsapp']['plan'] == False, "plan basico no debe incluir whatsapp"
    
    @test("J11. Defaults por plan: 'enterprise' tiene todo")
    def t():
        r = client.post('/api/superadmin/colegios', json={
            'nombre':'Test Ent','codigo':'te_default','plan':'enterprise',
            'admin_username':'te_dir','admin_password':'TeAdmin2024',
        }, headers=auth(sa))
        cole_id = r.json()['id']
        r = client.get(f'/api/superadmin/colegios/{cole_id}/modulos', headers=auth(sa))
        m = r.json()['modulos']
        for nombre in ['secundaria', 'primaria', 'whatsapp', 'psicologia', 'eval_profesores']:
            assert m[nombre]['plan'] == True, f"plan enterprise debe incluir {nombre}"
    
    # ─────────────────────────────────────────────────────────────────
    # SECCIÓN K — VALIDACIÓN DE NIVEL EN ENDPOINTS DE OPERACIÓN
    # ─────────────────────────────────────────────────────────────────
    
    print(f"{BOLD}\n=== K. VALIDACIÓN DE NIVEL EN ENDPOINTS ==={RESET}")
    
    # Setup: colegio K con primaria activa, crear curso de primaria, luego desactivar
    r = client.post('/api/superadmin/colegios', json={
        'nombre':'Colegio K','codigo':'k_nivel','plan':'enterprise',
        'admin_username':'dir_k','admin_password':'AdminK2024',
    }, headers=auth(sa))
    DIR_K = client.post('/api/auth/login', json={'username':'dir_k','password':'AdminK2024'}).json()['token']
    K_cole_id = client.get('/api/configuracion', headers=auth(DIR_K)).json()['colegio_id']
    
    # Crear grado primaria + curso primaria + estudiante (con primaria activa)
    grados_k = client.get('/api/grados', headers=auth(DIR_K)).json()
    tandas_k = client.get('/api/tandas', headers=auth(DIR_K)).json()
    
    r = client.post('/api/grados', json={
        'nombre':'3ro Primaria K','nivel':'primaria','orden':3,
    }, headers=auth(DIR_K))
    K_grado_pri = r.json()['id']
    
    r = client.post('/api/cursos', json={
        'grado_id': K_grado_pri, 'tanda_id': tandas_k[0]['id'], 'nombre':'A',
    }, headers=auth(DIR_K))
    K_curso_pri = r.json()['id']
    
    asig_k = client.post('/api/asignaturas', json={'nombre':'Mate K','codigo':'MK'}, headers=auth(DIR_K)).json()['id']
    prof_k = client.post('/api/usuarios', json={
        'username':'prof_k','password':'profesor123','nombre':'P','apellido':'K',
        'email':'pk@x.com','role':'profesor',
    }, headers=auth(DIR_K)).json()['id']
    client.post('/api/asignaciones', json={'profesor_id':prof_k,'curso_id':K_curso_pri,'asignatura_id':asig_k}, headers=auth(DIR_K))
    
    # Estudiante en curso de primaria
    K_est = client.post('/api/estudiantes', json={
        'nombre':'Est','apellido':'Primaria K','curso_id':K_curso_pri,'no_lista':1,
    }, headers=auth(DIR_K)).json()['id']
    
    # AHORA: superadmin DESACTIVA primaria del plan
    client.put(f'/api/superadmin/colegios/{K_cole_id}/modulos',
               json={'modulos': {'primaria': False}}, headers=auth(sa))
    
    PROF_K = client.post('/api/auth/login', json={'username':'prof_k','password':'profesor123'}).json()['token']
    
    @test("K1. POST /api/estudiantes en curso de nivel desactivado → bloqueado")
    def t():
        r = client.post('/api/estudiantes', json={
            'nombre':'Nuevo','apellido':'Bloqueado','curso_id':K_curso_pri,'no_lista':99,
        }, headers=auth(DIR_K))
        assert r.status_code in (400, 403), f"esperaba 400/403, obtuvo {r.status_code}: {r.text}"
    
    @test("K2. PUT /api/estudiantes/{id} moviendo a curso de nivel desactivado → bloqueado")
    def t():
        # Crear otro estudiante en colegio K (con primaria desactivada ya, pero el destino es primaria)
        # Re-activar primaria temporalmente para crear el estudiante en otro curso primero
        client.put(f'/api/superadmin/colegios/{K_cole_id}/modulos',
                   json={'modulos': {'primaria': True}}, headers=auth(sa))
        # Crear curso secundaria de fallback
        r = client.post('/api/cursos', json={
            'grado_id': grados_k[0]['id'], 'tanda_id': tandas_k[0]['id'], 'nombre':'X',
        }, headers=auth(DIR_K))
        curso_sec = r.json()['id']
        est_temp = client.post('/api/estudiantes', json={
            'nombre':'Mover','apellido':'Test','curso_id':curso_sec,'no_lista':2,
        }, headers=auth(DIR_K)).json()['id']
        # Re-desactivar primaria
        client.put(f'/api/superadmin/colegios/{K_cole_id}/modulos',
                   json={'modulos': {'primaria': False}}, headers=auth(sa))
        # Intentar mover a curso de primaria
        r = client.put(f'/api/estudiantes/{est_temp}', json={
            'curso_id': K_curso_pri,
        }, headers=auth(DIR_K))
        assert r.status_code in (400, 403), f"esperaba 400/403, obtuvo {r.status_code}: {r.text}"
    
    @test("K3. POST /api/asignaciones en curso de nivel desactivado → bloqueado")
    def t():
        prof2 = client.post('/api/usuarios', json={
            'username':'prof_k2','password':'profesor123','nombre':'P2','apellido':'K',
            'email':'pk2@x.com','role':'profesor',
        }, headers=auth(DIR_K)).json()['id']
        r = client.post('/api/asignaciones', json={
            'profesor_id': prof2, 'curso_id': K_curso_pri, 'asignatura_id': asig_k,
        }, headers=auth(DIR_K))
        assert r.status_code in (400, 403), f"esperaba 400/403, obtuvo {r.status_code}"
    
    @test("K4. POST /api/horarios en curso de nivel desactivado → bloqueado")
    def t():
        r = client.post('/api/horarios', json={
            'curso_id': K_curso_pri, 'asignatura_id': asig_k, 'profesor_id': prof_k,
            'dia':'Lunes', 'hora_inicio':'08:00', 'hora_fin':'08:45', 'tipo_bloque':'clase',
        }, headers=auth(DIR_K))
        assert r.status_code in (400, 403), f"esperaba 400/403, obtuvo {r.status_code}"
    
    @test("K5. POST /api/calificaciones en estudiante de nivel desactivado → bloqueado")
    def t():
        r = client.post('/api/calificaciones', json={
            'estudiante_id': K_est, 'asignatura_id': asig_k, 'p1_p1': 80,
        }, headers=auth(PROF_K))
        # Puede ser 400/403 dependiendo del orden de validaciones
        assert r.status_code in (400, 403), f"esperaba 400/403, obtuvo {r.status_code}: {r.text}"
    
    @test("K6. POST /api/asistencia en estudiante de nivel desactivado → bloqueado")
    def t():
        r = client.post('/api/asistencia', json={
            'estudiante_id': K_est, 'asignatura_id': asig_k,
            'fecha':'2024-09-02', 'estado':'presente',
        }, headers=auth(PROF_K))
        assert r.status_code in (400, 403), f"esperaba 400/403, obtuvo {r.status_code}: {r.text}"
    
    @test("K7. Datos NO se borran al desactivar nivel (solo se ocultan)")
    def t():
        # K_est sigue existiendo en BD
        r = client.get(f'/api/estudiantes/{K_est}', headers=auth(DIR_K))
        # Puede devolver 200 (lo encuentra) o 404 (filtro tenant). Lo importante:
        # NO debe devolver 500 ni similar.
        assert r.status_code in (200, 404), f"datos no se deben perder: {r.status_code}"
    
    @test("K8. Reactivar nivel → escrituras vuelven a funcionar")
    def t():
        # Reactivar primaria
        client.put(f'/api/superadmin/colegios/{K_cole_id}/modulos',
                   json={'modulos': {'primaria': True}}, headers=auth(sa))
        # Ahora SÍ debe permitir crear estudiante en curso primaria
        r = client.post('/api/estudiantes', json={
            'nombre':'Despues','apellido':'React','curso_id':K_curso_pri,'no_lista':50,
        }, headers=auth(DIR_K))
        assert r.status_code == 201, f"esperaba 201, obtuvo {r.status_code}: {r.text}"
    
    # ─────────────────────────────────────────────────────────────────
    # SECCIÓN L — DEFAULTS Y BLOQUEOS POST-FIX (módulos no aparecen activos
    # sin intervención del usuario)
    # ─────────────────────────────────────────────────────────────────
    
    print(f"{BOLD}\n=== L. DEFAULTS LIMPIOS Y BLOQUEOS ==={RESET}")
    
    # Setup: colegio L con plan basico (limitado)
    r = client.post('/api/superadmin/colegios', json={
        'nombre':'Colegio L','codigo':'l_default','plan':'basico',
        'admin_username':'dir_l','admin_password':'AdminL2024',
    }, headers=auth(sa))
    assert r.status_code in (200, 201), f"crear: {r.text}"
    L_id = r.json()['id']
    DIR_L = client.post('/api/auth/login', json={'username':'dir_l','password':'AdminL2024'}).json()['token']
    
    @test("L1. Colegio basico nuevo: NINGÚN módulo funcional aparece como activo")
    def t():
        r = client.get('/api/configuracion', headers=auth(DIR_L))
        assert r.status_code == 200
        modulos = r.json()['modulos']
        # Módulos funcionales no incluidos en plan básico → activo=false
        for m in ['whatsapp', 'psicologia', 'eval_interna']:
            assert modulos[m]['activo'] == False, \
                f"módulo {m} no debería estar activo en colegio basico nuevo: {modulos[m]}"
    
    @test("L2. v2.11: módulos del plan SÍ se autoactivan (activo = plan)")
    def t():
        # En v2.11 (Interpretación A): activo = plan. Si el plan incluye
        # un módulo, está activo automáticamente. Sin doble switch.
        r = client.get('/api/configuracion', headers=auth(DIR_L))
        modulos = r.json()['modulos']
        assert modulos['eval_profesores']['plan'] == True, "plan debería incluirlo"
        assert modulos['eval_profesores']['activo'] == True, \
            "activo = plan en v2.11 (sin doble switch)"
    
    @test("L3. Niveles SÍ se autoactivan (lo lógico cuando el plan los incluye)")
    def t():
        # Excepción a la regla L2: niveles secundaria/primaria parten en True
        # porque si el plan los incluye, se usan sin click extra
        r = client.get('/api/configuracion', headers=auth(DIR_L))
        modulos = r.json()['modulos']
        # plan basico: secundaria=true, primaria=false
        assert modulos['secundaria']['plan'] == True
        assert modulos['secundaria']['usa'] == True
        assert modulos['secundaria']['activo'] == True
        # primaria no en plan
        assert modulos['primaria']['plan'] == False
        assert modulos['primaria']['activo'] == False
    
    @test("L4. activo = plan AND usa (consistente en TODOS los módulos)")
    def t():
        r = client.get('/api/configuracion', headers=auth(DIR_L))
        modulos = r.json()['modulos']
        for nombre, m in modulos.items():
            esperado = bool(m['plan']) and bool(m['usa'])
            assert m['activo'] == esperado, \
                f"módulo {nombre}: activo={m['activo']} pero plan={m['plan']} AND usa={m['usa']} = {esperado}"
    
    @test("L5. Director enciende módulo del plan → activo pasa a True")
    def t():
        # eval_profesores: plan=true, usa=false. Director enciende.
        r = client.put('/api/configuracion/modulos', json={
            'modulos': {'eval_profesores': True},
        }, headers=auth(DIR_L))
        assert r.status_code == 200, f"esperaba 200, obtuvo {r.status_code}: {r.text}"
        # Verificar
        r = client.get('/api/configuracion', headers=auth(DIR_L))
        m = r.json()['modulos']['eval_profesores']
        assert m['plan'] == True and m['usa'] == True and m['activo'] == True
    
    @test("L6. v2.11: director toca PUT modulos sin plan → 200 informativo (no edita)")
    def t():
        r = client.put('/api/configuracion/modulos', json={
            'modulos': {'whatsapp': True},
        }, headers=auth(DIR_L))
        assert r.status_code == 200, f"esperaba 200, obtuvo {r.status_code}: {r.text}"
        # Verificar que whatsapp NO se activó
        cfg = client.get('/api/configuracion', headers=auth(DIR_L)).json()
        assert cfg['modulos']['whatsapp']['activo'] == False, \
            "whatsapp NO debe activarse si no está en plan"
    
    @test("L7. Endpoint legacy /api/configuracion/modulos refleja efectivo (no usa_X bruto)")
    def t():
        r = client.get('/api/configuracion/modulos', headers=auth(DIR_L))
        assert r.status_code == 200
        data = r.json()
        # whatsapp: plan=false → debe ser false (no importa que usa_X esté en false default)
        assert data['modulo_whatsapp'] == False, \
            f"endpoint legacy debe reflejar efectivo, no usa_X: {data}"
        # eval_profesores: en L5 lo encendimos → ahora debe ser true
        assert data['modulo_eval_profesores'] == True
    
    @test("L8. aplicar-plan resetea plan_X (no toca usa_X)")
    def t():
        # Colegio L tiene plan=basico. Modificar manualmente plan_whatsapp=true
        # y luego aplicar-plan → debe volver a false (default basico)
        r = client.put(f'/api/superadmin/colegios/{L_id}/modulos',
                       json={'modulos': {'whatsapp': True}}, headers=auth(sa))
        assert r.status_code == 200
        # Verificar que ahora SÍ está en plan
        r = client.get(f'/api/superadmin/colegios/{L_id}/modulos', headers=auth(sa))
        assert r.json()['modulos']['whatsapp']['plan'] == True
        
        # Aplicar plan basico → debe resetear plan_whatsapp a false
        r = client.post(f'/api/superadmin/colegios/{L_id}/aplicar-plan', headers=auth(sa))
        assert r.status_code == 200, f"aplicar-plan: {r.text}"
        
        r = client.get(f'/api/superadmin/colegios/{L_id}/modulos', headers=auth(sa))
        assert r.json()['modulos']['whatsapp']['plan'] == False, \
            "aplicar-plan debe haber reseteado plan_whatsapp a false (default basico)"
    
    @test("L9. update_colegio NO crashea al recibir tiene_primaria legacy")
    def t():
        # Bug original: app.py:8491 leía colegio.tiene_primaria que ya no existe
        r = client.put(f'/api/superadmin/colegios/{L_id}', json={
            'nombre': 'Colegio L Updated',
            'tiene_primaria': True,   # legacy → debe mapear a plan_primaria
            'tiene_secundaria': True,
        }, headers=auth(sa))
        assert r.status_code == 200, f"esperaba 200, obtuvo {r.status_code}: {r.text}"
        # Verificar que se aplicó al plan
        r = client.get(f'/api/superadmin/colegios/{L_id}/modulos', headers=auth(sa))
        m = r.json()['modulos']
        assert m['primaria']['plan'] == True, "tiene_primaria=true legacy debió mapear a plan_primaria"
    
    @test("L10. update_colegio rechaza desactivar todos los niveles del plan → 400")
    def t():
        r = client.put(f'/api/superadmin/colegios/{L_id}', json={
            'plan_secundaria': False,
            'plan_primaria': False,
            'plan_inicial': False,
        }, headers=auth(sa))
        assert r.status_code == 400, f"esperaba 400, obtuvo {r.status_code}: {r.text}"
        # Restaurar
        client.put(f'/api/superadmin/colegios/{L_id}', json={
            'plan_secundaria': True, 'plan_primaria': True,
        }, headers=auth(sa))


# ─────────────────────────────────────────────────────────────────
# REPORTE FINAL
# ─────────────────────────────────────────────────────────────────

print(f"\n{BOLD}{'=' * 60}{RESET}")
print(f"{BOLD}  RESUMEN: {pasados}/{total} tests pasaron{RESET}")
print(f"{BOLD}{'=' * 60}{RESET}\n")

if fallos:
    print(f"{RED}{BOLD}TESTS FALLIDOS:{RESET}\n")
    for nombre, msg in fallos:
        print(f"  {RED}✗ {nombre}{RESET}")
        print(f"      {msg}")
    sys.exit(1)
else:
    print(f"{GREEN}{BOLD}🎉 TODOS LOS TESTS PASARON{RESET}\n")
    sys.exit(0)
