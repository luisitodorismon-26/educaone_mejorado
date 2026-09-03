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

# ---------------------------------------------------------------------------
# v2.19: toda cuenta nueva nace con must_change_password=True y cualquier
# endpoint responde 423 hasta que el usuario cambie la clave. Estas suites
# prueban roles, aislamiento y notificaciones — NO la política de contraseñas,
# que tiene su propio archivo (test_reemplazo_profesor.py).
#
# Para no reescribir decenas de fixtures, limpiamos la marca directamente en la
# base antes de cada login. Es un atajo de PRUEBA: no toca código de producción
# y el 423 se sigue verificando donde corresponde.
def _limpiar_must_change(username):
    from database import SessionLocal as _SL
    from models import Usuario as _U
    _d = _SL()
    try:
        _u = _d.query(_U).filter_by(username=username).first()
        if _u is not None and _u.must_change_password:
            _u.must_change_password = False
            _d.commit()
    finally:
        _d.close()


def _login_prueba(**kwargs):
    """Sustituye a las llamadas directas de login en las fixtures."""
    payload = kwargs.get('json') or {}
    if payload.get('username'):
        _limpiar_must_change(payload['username'])
    return client.post('/api/auth/login', **kwargs)


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
    r = _login_prueba( json={'username':'superadmin','password':'superadmin123'})
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
    DIR_A_TOKEN = _login_prueba( json={'username':'direccion','password':'admin123'}).json()['token']
    DIR_B_TOKEN = _login_prueba( json={'username':'dir_b','password':'admin123b'}).json()['token']
    
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
    PROF_A_TOKEN = _login_prueba( json={
        'username': f'profe_{A["sufijo"]}', 'password':'profesor123'
    }).json()['token']
    PROF_B_TOKEN = _login_prueba( json={
        'username': f'profe_{B["sufijo"]}', 'password':'profesor123'
    }).json()['token']
    SEC_A_TOKEN = _login_prueba( json={
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
        coord_a_token = _login_prueba( json={
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
        r = _login_prueba( json={'username':'direccion','password':'admin123'})
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
        DIR_A_TOKEN = _login_prueba( json={
            'username':'direccion','password':'admin123'
        }).json()['token']
        # Crear usuario temporal para no afectar otras secciones
        r = client.post('/api/usuarios', json={
            'username':'usr_test_pw','password':'PasswordOld1','nombre':'PWTest','apellido':'X',
            'email':'pwtest@x.com','role':'coordinador',
        }, headers=auth(DIR_A_TOKEN))
        assert r.status_code == 201, f"crear usuario falló: {r.text}"
        # Login
        r = _login_prueba( json={'username':'usr_test_pw','password':'PasswordOld1'})
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
        r = _login_prueba( json={'username':'dir_e2e','password':'AdminE2E2024'})
        assert r.status_code == 200, f"login director falló: {r.text}"
    
    @test("G3. Director crea profesor y secretaria")
    def t():
        tok = _login_prueba( json={'username':'dir_e2e','password':'AdminE2E2024'}).json()['token']
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
        tok = _login_prueba( json={'username':'dir_e2e','password':'AdminE2E2024'}).json()['token']
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
        tok = _login_prueba( json={'username':'dir_e2e','password':'AdminE2E2024'}).json()['token']
        r = client.post('/api/horarios', json={
            'curso_id': _E2E_curso, 'asignatura_id': _E2E_asig, 'profesor_id': _E2E_prof,
            'dia':'Lunes', 'hora_inicio':'07:30', 'hora_fin':'08:20', 'tipo_bloque':'clase',
        }, headers=auth(tok))
        assert r.status_code == 201, f"crear horario: {r.text}"
    
    @test("G6. Director crea estudiante")
    def t():
        tok = _login_prueba( json={'username':'dir_e2e','password':'AdminE2E2024'}).json()['token']
        r = client.post('/api/estudiantes', json={
            'nombre':'Maria','apellido':'Lopez','sexo':'F','fecha_nacimiento':'2010-06-15',
            'curso_id': _E2E_curso, 'no_lista': 1, 'matricula':'E2E001'
        }, headers=auth(tok))
        assert r.status_code == 201, f"crear estudiante: {r.text}"
        globals()['_E2E_est'] = r.json()['id']
    
    @test("G7. Profesor califica estudiante con 4 parciales (PC1 calculado)")
    def t():
        tok = _login_prueba( json={'username':'prof_e2e','password':'ProfE2E2024'}).json()['token']
        r = client.post('/api/calificaciones', json={
            'estudiante_id': _E2E_est, 'asignatura_id': _E2E_asig,
            'p1_p1': 90, 'p1_p2': 85, 'p1_p3': 80, 'p1_p4': 75,
        }, headers=auth(tok))
        assert r.status_code == 200, f"calificar: {r.text}"
        cal = r.json()['calificacion']
        assert cal['pc1'] == 82.5, f"PC1 esperado 82.5, fue {cal['pc1']}"
    
    @test("G8. Profesor registra asistencia")
    def t():
        tok = _login_prueba( json={'username':'prof_e2e','password':'ProfE2E2024'}).json()['token']
        for fecha in ['2024-09-02', '2024-09-03', '2024-09-04']:
            r = client.post('/api/asistencia', json={
                'estudiante_id': _E2E_est, 'asignatura_id': _E2E_asig,
                'fecha': fecha, 'estado':'presente',
            }, headers=auth(tok))
            assert r.status_code == 200, f"asistencia {fecha}: {r.text}"
    
    @test("G9. Director ve calificaciones del curso")
    def t():
        tok = _login_prueba( json={'username':'dir_e2e','password':'AdminE2E2024'}).json()['token']
        r = client.get(f'/api/calificaciones/curso/{_E2E_curso}/asignatura/{_E2E_asig}', headers=auth(tok))
        assert r.status_code == 200, f"ver calificaciones: {r.text}"
        body = r.json()
        califs = body['calificaciones']
        assert len(califs) >= 1
        cal = next(c for c in califs if c['estudiante']['id'] == _E2E_est)
        assert cal['calificacion']['pc1'] == 82.5
    
    @test("G10. Secretaria NO puede calificar (verificación de rol)")
    def t():
        tok = _login_prueba( json={'username':'sec_e2e','password':'SecE2E2024'}).json()['token']
        r = client.post('/api/calificaciones', json={
            'estudiante_id': _E2E_est, 'asignatura_id': _E2E_asig, 'p2_p1': 85,
        }, headers=auth(tok))
        assert r.status_code == 403, f"esperaba 403, obtuvo {r.status_code}"
    
    @test("G11. Secretaria SÍ puede ver estudiantes (rol válido)")
    def t():
        tok = _login_prueba( json={'username':'sec_e2e','password':'SecE2E2024'}).json()['token']
        r = client.get('/api/estudiantes', headers=auth(tok))
        assert r.status_code == 200, f"esperaba 200, obtuvo {r.status_code}: {r.text}"
    
    @test("G12. Director ve resumen de asistencia del curso")
    def t():
        tok = _login_prueba( json={'username':'dir_e2e','password':'AdminE2E2024'}).json()['token']
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
    sa = _login_prueba( json={'username':'superadmin','password':'superadmin123'}).json()['token']
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
    DIR_H = _login_prueba( json={'username':'dir_h','password':'AdminHColegio2024'}).json()['token']
    
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
    PROF_H = _login_prueba( json={'username':'prof_h','password':'profesor123'}).json()['token']
    from datetime import date as _date
    hoy_iso = _date.today().isoformat()

    # v2.19: estas pruebas miden la asistencia de HOY contra /api/dashboard/graficos,
    # así que la fecha no se puede fijar a un lunes cualquiera. Pero por defecto el
    # sistema RECHAZA asistencia en sábado y domingo (app.py, validación de
    # permite_sabado/permite_domingo), y eso hacía fallar H1/H3/H4/H5/H6 solo
    # los fines de semana.
    # Solución: habilitar fin de semana ÚNICAMENTE en este colegio de prueba,
    # como haría un colegio con clases los sábados. No se toca la lógica de
    # producción ni el default (lunes-viernes) de ningún otro colegio.
    from database import SessionLocal as _SessionLocal
    from models import ConfiguracionColegio as _ConfigColegio
    _db_cfg = _SessionLocal()
    try:
        _cfg_h = _db_cfg.query(_ConfigColegio).filter_by(colegio_id=COLEGIO_H_ID).first()
        if _cfg_h is not None:
            _cfg_h.permite_sabado = True
            _cfg_h.permite_domingo = True
            _db_cfg.commit()
    finally:
        _db_cfg.close()

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
    DIR_J = _login_prueba( json={'username':'dir_j','password':'AdminJ2024'}).json()['token']
    
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
    DIR_K = _login_prueba( json={'username':'dir_k','password':'AdminK2024'}).json()['token']
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
    
    PROF_K = _login_prueba( json={'username':'prof_k','password':'profesor123'}).json()['token']
    
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
    DIR_L = _login_prueba( json={'username':'dir_l','password':'AdminL2024'}).json()['token']
    
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
    # SECCIÓN M — REGRESIONES DE SEGURIDAD P0 (v2.18 hardening)
    # ─────────────────────────────────────────────────────────────────

    print(f"{BOLD}\n=== M. HARDENING MULTI-TENANT / BACKUPS ==={RESET}")

    @test("M1. Dirección NO puede generar un backup global")
    def t():
        r = client.get('/api/backup', headers=auth(DIR_A_TOKEN))
        assert r.status_code == 403, f"esperaba 403, obtuvo {r.status_code}: {r.text}"

    @test("M2. Dirección NO puede listar backups globales")
    def t():
        r = client.get('/api/backup/lista', headers=auth(DIR_A_TOKEN))
        assert r.status_code == 403, f"esperaba 403, obtuvo {r.status_code}: {r.text}"

    @test("M3. Dirección NO puede descargar backups globales")
    def t():
        r = client.get('/api/backup/descargar/backup_20260101_010101.sql', headers=auth(DIR_A_TOKEN))
        assert r.status_code == 403, f"esperaba 403, obtuvo {r.status_code}: {r.text}"

    @test("M4. Superadmin sí atraviesa RBAC del backup global")
    def t():
        # En la suite se usa SQLite, por eso el handler responde 400
        # ('solo PostgreSQL'). Lo que validamos aquí es que NO sea 403.
        r = client.get('/api/backup', headers=auth(SA_TOKEN))
        assert r.status_code != 403, f"superadmin no debe quedar bloqueado: {r.text}"

    @test("M5. Registro legacy con colegio_id=NULL queda oculto a Dirección")
    def t():
        from database import SessionLocal
        from models import Estudiante
        db_t = SessionLocal()
        try:
            est = db_t.get(Estudiante, A['est'])
            colegio_original = est.colegio_id
            est.colegio_id = None
            db_t.commit()

            r = client.get(f'/api/estudiantes/{A["est"]}', headers=auth(DIR_A_TOKEN))
            assert r.status_code == 404, \
                f"registro huérfano no debe ser visible por tenant: {r.status_code}: {r.text}"

            # Superadmin conserva capacidad de saneamiento/diagnóstico.
            r_sa = client.get(f'/api/estudiantes/{A["est"]}', headers=auth(SA_TOKEN))
            assert r_sa.status_code == 200, \
                f"superadmin debe poder acceder al registro legacy: {r_sa.status_code}: {r_sa.text}"
        finally:
            est = db_t.get(Estudiante, A['est'])
            if est is not None:
                est.colegio_id = colegio_original
                db_t.commit()
            db_t.close()


    @test("M6. Matrícula duplicada se bloquea dentro del mismo colegio")
    def t():
        r = client.post('/api/estudiantes', json={
            'nombre':'Duplicado','apellido':'Matricula', 'curso_id': A['curso'],
            'matricula':'M001-a', 'no_lista': 90,
        }, headers=auth(DIR_A_TOKEN))
        assert r.status_code == 409, f"esperaba 409, obtuvo {r.status_code}: {r.text}"

    @test("M7. La misma matrícula puede existir en otro colegio")
    def t():
        r = client.post('/api/estudiantes', json={
            'nombre':'Otro','apellido':'Tenant', 'curso_id': B['curso'],
            'matricula':'M001-a', 'no_lista': 90,
        }, headers=auth(DIR_B_TOKEN))
        assert r.status_code == 201, f"la unicidad debe ser por colegio: {r.status_code}: {r.text}"

    @test("M8. Número de lista duplicado se bloquea dentro del mismo curso")
    def t():
        r = client.post('/api/estudiantes', json={
            'nombre':'Duplicado','apellido':'Lista', 'curso_id': A['curso'],
            'matricula':'UNICA-M8', 'no_lista': 1,
        }, headers=auth(DIR_A_TOKEN))
        assert r.status_code == 409, f"esperaba 409, obtuvo {r.status_code}: {r.text}"


    @test("M9. Impersonación audita al Superadmin como actor real")
    def t():
        from database import SessionLocal
        from models import Usuario, LogAuditoria

        db_t = SessionLocal()
        try:
            sa_user = db_t.query(Usuario).filter_by(username='superadmin').first()
            dir_a = db_t.query(Usuario).filter_by(username='direccion').first()
            assert sa_user is not None and dir_a is not None
            colegio_a_id = dir_a.colegio_id
        finally:
            db_t.close()

        r = client.post(f'/api/superadmin/impersonar/{colegio_a_id}', headers=auth(SA_TOKEN))
        assert r.status_code == 200, f"impersonación falló: {r.status_code}: {r.text}"
        imp_token = r.json()['token']

        # Una escritura efectuada con el token del director impersonado debe
        # quedar atribuida al Superadmin, sin perder la identidad efectiva.
        r = client.put(f'/api/estudiantes/{A["est"]}', json={
            'telefono': '809-555-0009',
        }, headers=auth(imp_token))
        assert r.status_code == 200, f"escritura impersonada falló: {r.status_code}: {r.text}"

        db_t = SessionLocal()
        try:
            fino = (db_t.query(LogAuditoria)
                    .filter(LogAuditoria.accion == 'editar',
                            LogAuditoria.entidad == 'estudiantes',
                            LogAuditoria.entidad_id == A['est'])
                    .order_by(LogAuditoria.id.desc()).first())
            assert fino is not None, "no se creó auditoría fina de la edición"
            assert fino.usuario_id == sa_user.id, \
                f"actor debe ser Superadmin {sa_user.id}, quedó {fino.usuario_id}"
            assert fino.colegio_id == dir_a.colegio_id, \
                "la auditoría debe conservar el tenant efectivo"
            assert str(dir_a.id) in (fino.detalles or ''), \
                "el detalle debe conservar el usuario efectivo impersonado"
        finally:
            db_t.close()


    @test("M10. Psicología NO acepta estudiante de otro colegio")
    def t():
        # Dirección del colegio A no puede crear un caso apuntando al estudiante B.
        r = client.post('/api/psicologia/solicitar', json={
            'estudiante_id': B['est'],
            'tipo': 'emocional',
            'urgencia': 'media',
            'motivo': 'Prueba cross-tenant',
        }, headers=auth(DIR_A_TOKEN))
        assert r.status_code == 404, \
            f"esperaba 404 cross-tenant, obtuvo {r.status_code}: {r.text}"

        # Confirmar que no se persistió ningún caso A -> estudiante B.
        from database import SessionLocal
        from models import CasoPsicologia, Usuario
        db_t = SessionLocal()
        try:
            dir_a = db_t.query(Usuario).filter_by(username='direccion').first()
            assert dir_a is not None
            count = (db_t.query(CasoPsicologia)
                     .filter(CasoPsicologia.colegio_id == dir_a.colegio_id,
                             CasoPsicologia.estudiante_id == B['est'])
                     .count())
            assert count == 0, f"se persistieron {count} casos cross-tenant"
        finally:
            db_t.close()


    @test("M11. Superadmin NO puede crear otro superadmin ligado a un colegio")
    def t():
        from database import SessionLocal
        from models import Usuario
        db_t = SessionLocal()
        try:
            dir_a = db_t.query(Usuario).filter_by(username='direccion').first()
            colegio_a_id = dir_a.colegio_id
        finally:
            db_t.close()
        r = client.post(f'/api/superadmin/colegios/{colegio_a_id}/crear-usuario', json={
            'username': 'sa_tenant_m11', 'nombre': 'No', 'role': 'superadmin',
            'password': 'TemporalM11!'
        }, headers=auth(SA_TOKEN))
        assert r.status_code == 400, f"esperaba 400, obtuvo {r.status_code}: {r.text}"


    @test("M12. Editar usuario NO acepta tanda de otro colegio")
    def t():
        r = client.put(f'/api/usuarios/{A["prof"]}', json={
            'tanda_id': B['tanda']
        }, headers=auth(DIR_A_TOKEN))
        assert r.status_code == 404, f"esperaba 404, obtuvo {r.status_code}: {r.text}"


    @test("M13. Marcar comunicado de otro colegio NO crea relación cross-tenant")
    def t():
        r = client.post('/api/comunicados', json={
            'titulo':'Comunicado B M13','contenido':'Solo B'
        }, headers=auth(DIR_B_TOKEN))
        assert r.status_code == 201, r.text
        comunicado_b = r.json()['id']
        r = client.post(f'/api/comunicados/{comunicado_b}/marcar-leido', headers=auth(DIR_A_TOKEN))
        assert r.status_code == 404, f"esperaba 404, obtuvo {r.status_code}: {r.text}"


    @test("M14. Notas internas de Psicología NO se exponen al profesor")
    def t():
        # Crear usuario psicología en A.
        r = client.post('/api/usuarios', json={
            'username':'psi_m14','password':'PsicologiaM14!','nombre':'Psi','apellido':'M14','role':'psicologia'
        }, headers=auth(DIR_A_TOKEN))
        assert r.status_code in (201, 400), r.text
        psi_token = _login_prueba( json={'username':'psi_m14','password':'PsicologiaM14!'}).json().get('token')
        assert psi_token, 'no se pudo loguear psicología M14'

        r = client.post('/api/psicologia/solicitar', json={
            'estudiante_id': A['est'], 'tipo':'emocional','urgencia':'normal','motivo':'M14'
        }, headers=auth(PROF_A_TOKEN))
        assert r.status_code == 201, r.text
        caso_id = r.json()['id']
        client.post(f'/api/psicologia/casos/{caso_id}/tomar', headers=auth(psi_token))
        r = client.post(f'/api/psicologia/casos/{caso_id}/actualizar', json={
            'notas_atencion':'nota interna secreta',
            'diagnostico':'diagnóstico interno',
            'recomendacion_profesor':'dar seguimiento académico'
        }, headers=auth(psi_token))
        assert r.status_code == 200, r.text

        casos = client.get('/api/psicologia/casos', headers=auth(PROF_A_TOKEN)).json()
        caso = next((x for x in casos if x['id'] == caso_id), None)
        assert caso is not None, 'profesor solicitante debe ver el estado de su caso'
        assert caso.get('notas_atencion') is None, 'profesor no debe ver notas internas'
        assert caso.get('diagnostico') is None, 'profesor no debe ver diagnóstico interno'
        assert caso.get('recomendacion_profesor') == 'dar seguimiento académico'


    @test("M15. Restablecer password por Dirección revoca tokens anteriores")
    def t():
        r = client.post('/api/usuarios', json={
            'username':'tok_m15','password':'InicialM15!','nombre':'Token','apellido':'M15','role':'profesor'
        }, headers=auth(DIR_A_TOKEN))
        assert r.status_code == 201, r.text
        uid = r.json()['id']
        tok = _login_prueba( json={'username':'tok_m15','password':'InicialM15!'}).json()['token']
        assert client.get('/api/auth/me', headers=auth(tok)).status_code == 200
        # v2.19: el PUT ya NO cambia contraseñas — es una vía paralela al flujo
        # oficial, sin must_change_password ni rastro de "reset" en auditoría.
        r = client.put(f'/api/usuarios/{uid}', json={'password':'NuevaM15!'}, headers=auth(DIR_A_TOKEN))
        assert r.status_code == 400, 'el PUT no debe aceptar contraseñas'
        assert client.get('/api/auth/me', headers=auth(tok)).status_code == 200, \
            'un PUT rechazado no puede revocar la sesión'
        # La acción correcta y separada:
        r = client.post(f'/api/usuarios/{uid}/reset-password',
                        json={'password':'NuevaM15!'}, headers=auth(DIR_A_TOKEN))
        assert r.status_code == 200, r.text
        assert client.get('/api/auth/me', headers=auth(tok)).status_code == 401, 'token viejo debe quedar revocado'


    @test("M16. Rate-limit por cuenta NO bloquea a toda la escuela por IP compartida")
    def t():
        for username in ('rl_a_m16','rl_b_m16'):
            r = client.post('/api/usuarios', json={
                'username':username,'password':'RateM16!','nombre':'Rate','apellido':username,'role':'profesor'
            }, headers=auth(DIR_A_TOKEN))
            assert r.status_code == 201, r.text
        for _ in range(5):
            _login_prueba( json={'username':'rl_a_m16','password':'incorrecta'})
        blocked = _login_prueba( json={'username':'rl_a_m16','password':'RateM16!'})
        assert blocked.status_code == 429, f"cuenta atacada debe bloquearse: {blocked.status_code} {blocked.text}"
        other = _login_prueba( json={'username':'rl_b_m16','password':'RateM16!'})
        assert other.status_code == 200 and other.json().get('token'), \
            f"otra cuenta en la misma IP debe seguir entrando: {other.status_code} {other.text}"


    @test("M17. Desactivar colegio corta inmediatamente una sesión ya emitida")
    def t():
        r = client.post('/api/superadmin/colegios', json={
            'nombre':'Colegio M17','codigo':'m17','plan':'enterprise',
            'admin_username':'dir_m17','admin_password':'AdminM17!'
        }, headers=auth(SA_TOKEN))
        assert r.status_code == 201, r.text
        cid = r.json()['id']
        tok = _login_prueba( json={'username':'dir_m17','password':'AdminM17!'}).json()['token']
        assert client.get('/api/auth/me', headers=auth(tok)).status_code == 200
        r = client.put(f'/api/superadmin/colegios/{cid}', json={'activo':False}, headers=auth(SA_TOKEN))
        assert r.status_code == 200, r.text
        assert client.get('/api/auth/me', headers=auth(tok)).status_code == 401, \
            'sesión de colegio desactivado no debe seguir válida'


    @test("M18. Editar username normaliza a minúsculas y mantiene el login usable")
    def t():
        r = client.post('/api/usuarios', json={
            'username':'user_m18','password':'UsuarioM18!','nombre':'User','apellido':'M18','role':'profesor'
        }, headers=auth(DIR_A_TOKEN))
        assert r.status_code == 201, r.text
        uid = r.json()['id']
        r = client.put(f'/api/usuarios/{uid}', json={'username':'USER_M18'}, headers=auth(DIR_A_TOKEN))
        assert r.status_code == 200, r.text
        login = _login_prueba( json={'username':'USER_M18','password':'UsuarioM18!'})
        assert login.status_code == 200 and login.json().get('token'), \
            f"username editado debe seguir autenticando: {login.status_code} {login.text}"

    # ─────────────────────────────────────────────────────────────
    # SECCIÓN S — v2.19.3-A (seguridad y comunicación)
    # ─────────────────────────────────────────────────────────────

    print(f"{BOLD}\n=== S. v2.19.3-A — SEGURIDAD Y COMUNICACIÓN ==={RESET}")

    @test("S1. Promoción NO toca ni revela estudiantes de otro colegio")
    def t():
        # Estado de B ANTES: nombre y curso del estudiante del otro colegio.
        ests_b = client.get('/api/estudiantes', headers=auth(DIR_B_TOKEN)).json()
        est_b = next((e for e in ests_b if e['id'] == B['est']), None)
        assert est_b is not None, 'setup: el estudiante de B debe existir'
        nombre_b = est_b['nombre_completo']
        curso_b_antes = est_b['curso_id']

        # Director A intenta promover a un estudiante del colegio B.
        r = client.post('/api/promocion/ejecutar',
                        json={'estudiantes': [B['est']]},
                        headers=auth(DIR_A_TOKEN))
        assert r.status_code == 200, r.text
        body = r.json()

        # 1. No se promovió nada.
        assert body['promocionados'] == 0, \
            f"no debe promover estudiantes de otro colegio: {body}"

        # 2. No se filtra el nombre del menor ajeno en los errores.
        errores_txt = ' '.join(body.get('errores', []))
        assert nombre_b not in errores_txt, \
            f"el nombre del estudiante de otro colegio se filtró en errores: {errores_txt!r}"

        # 3. El estudiante de B sigue intacto: activo y en su curso original.
        ests_b2 = client.get('/api/estudiantes', headers=auth(DIR_B_TOKEN)).json()
        est_b2 = next((e for e in ests_b2 if e['id'] == B['est']), None)
        assert est_b2 is not None, \
            'el estudiante de B fue desactivado por una promoción de otro colegio'
        assert est_b2['curso_id'] == curso_b_antes, \
            'el estudiante de B fue movido de curso por otro colegio'

    @test("S2. Colegio desactivado también corta endpoints con RolesRequired")
    def t():
        # Colegio propio para no afectar al resto de la suite.
        r = client.post('/api/superadmin/colegios', json={
            'nombre': 'Colegio S2', 'codigo': 'S2',
            'admin_username': 'dir_s2', 'admin_password': 'AdminS2!clave',
            'admin_nombre': 'Dir', 'admin_apellido': 'S2',
        }, headers=auth(SA_TOKEN))
        assert r.status_code in (200, 201), r.text
        cid = r.json()['id']
        tok = _login_prueba(json={'username': 'dir_s2', 'password': 'AdminS2!clave'}).json()['token']

        # Con el colegio activo, /api/usuarios (RolesRequired) responde normal.
        assert client.get('/api/usuarios', headers=auth(tok)).status_code == 200, \
            'setup: con el colegio activo el director debe poder listar usuarios'

        r = client.put(f'/api/superadmin/colegios/{cid}', json={'activo': False},
                       headers=auth(SA_TOKEN))
        assert r.status_code == 200, r.text

        # get_current_user ya cortaba (M17). Lo nuevo: RolesRequired también.
        assert client.get('/api/auth/me', headers=auth(tok)).status_code == 401
        r = client.get('/api/usuarios', headers=auth(tok))
        assert r.status_code == 403, \
            f'endpoint con RolesRequired debe rechazar colegio desactivado, dio {r.status_code}'

    @test("S3. Profesor NO puede enviar mensaje masivo")
    def t():
        r = client.post('/api/mensajes/masivo', json={
            'rol': 'profesor', 'asunto': 'Prueba S3', 'contenido': 'Cuerpo S3'
        }, headers=auth(PROF_A_TOKEN))
        assert r.status_code == 403, \
            f'profesor no debe poder difundir a todo el colegio, dio {r.status_code}: {r.text}'

    @test("S3b. Secretaría NO puede enviar mensaje masivo")
    def t():
        r = client.post('/api/mensajes/masivo', json={
            'rol': 'profesor', 'asunto': 'Prueba S3b', 'contenido': 'Cuerpo S3b'
        }, headers=auth(SEC_A_TOKEN))
        assert r.status_code == 403, \
            f'secretaría no debe poder difundir, dio {r.status_code}: {r.text}'

    @test("S4. Dirección y Coordinación SÍ pueden enviar mensaje masivo")
    def t():
        r = client.post('/api/mensajes/masivo', json={
            'rol': 'profesor', 'asunto': 'Aviso S4 dirección', 'contenido': 'Cuerpo S4'
        }, headers=auth(DIR_A_TOKEN))
        assert r.status_code == 201, f'dirección debe poder difundir: {r.text}'
        assert r.json().get('enviados', 0) >= 1, \
            f"la respuesta debe traer 'enviados' con el conteo real: {r.json()}"
        assert r.json().get('count') == r.json().get('enviados'), \
            "'count' y 'enviados' deben coincidir (retrocompatibilidad)"

        coord_token = _login_prueba(json={
            'username': f'coord_{A["sufijo"]}', 'password': 'coordinador123'
        }).json()['token']
        r = client.post('/api/mensajes/masivo', json={
            'rol': 'profesor', 'asunto': 'Aviso S4 coordinación', 'contenido': 'Cuerpo S4c'
        }, headers=auth(coord_token))
        assert r.status_code == 201, f'coordinación debe poder difundir: {r.text}'

    @test("S5. El mensaje masivo se sanitiza igual que el individual")
    def t():
        asunto = 'Sanitiza S5 <script>alert(1)</script>'
        r = client.post('/api/mensajes/masivo', json={
            'rol': 'profesor',
            'asunto': asunto,
            'contenido': '<script>alert("xss")</script><b>negrita</b> texto',
        }, headers=auth(DIR_A_TOKEN))
        assert r.status_code == 201, r.text

        recibidos = client.get('/api/mensajes', headers=auth(PROF_A_TOKEN)).json()
        msg = next((m for m in recibidos
                    if m['tipo'] == 'recibido' and 'Sanitiza S5' in (m.get('asunto') or '')), None)
        assert msg is not None, 'el profesor debe haber recibido el mensaje masivo'
        assert '<script>' not in (msg.get('asunto') or ''), \
            f"asunto sin sanitizar: {msg.get('asunto')!r}"
        assert '<script>' not in (msg.get('contenido') or ''), \
            f"contenido sin sanitizar: {msg.get('contenido')!r}"
        assert 'negrita' in (msg.get('contenido') or ''), \
            'las etiquetas permitidas (b/i/u/br/p) no deben perder el texto'

    @test("S5b. El rol destino del masivo se valida contra lista blanca")
    def t():
        r = client.post('/api/mensajes/masivo', json={
            'rol': 'rol_inventado', 'asunto': 'S5b', 'contenido': 'x'
        }, headers=auth(DIR_A_TOKEN))
        assert r.status_code == 400, \
            f'un rol destino inválido debe dar 400, dio {r.status_code}: {r.text}'

    @test("S6. El directorio no expone usuarios de otro colegio")
    def t():
        r = client.get('/api/usuarios/directorio', headers=auth(PROF_A_TOKEN))
        assert r.status_code == 200, \
            f'todo rol autenticado debe poder leer el directorio: {r.status_code} {r.text}'
        ids = {u['id'] for u in r.json()}
        assert B['prof'] not in ids, 'el directorio filtró un usuario del colegio B'
        assert A['prof'] not in ids, 'el directorio no debe incluirse a uno mismo'
        assert A['coord'] in ids, 'el directorio debe traer a los compañeros del colegio'

    @test("S7. El directorio no expone información administrativa")
    def t():
        r = client.get('/api/usuarios/directorio', headers=auth(PROF_A_TOKEN))
        assert r.status_code == 200, r.text
        filas = r.json()
        assert filas, 'setup: el directorio no debería venir vacío'
        permitidas = {'id', 'nombre_completo', 'role'}
        for u in filas:
            extra = set(u.keys()) - permitidas
            assert not extra, f'el directorio expone campos de más: {sorted(extra)}'
        # Verificación explícita de los campos sensibles que sí trae /api/usuarios.
        crudo = r.text
        for prohibido in ('email', 'telefono', 'username',
                          'must_change_password', 'last_login', 'nivel_asignado'):
            assert f'"{prohibido}"' not in crudo, \
                f'el directorio no debe incluir {prohibido}'

    @test("S8. Secretaría NO puede leer casos de Psicología por API")
    def t():
        r = client.get('/api/psicologia/casos', headers=auth(SEC_A_TOKEN))
        assert r.status_code == 403, \
            f'secretaría no debe leer casos de psicología, dio {r.status_code}'

    @test("S8b. Los roles del circuito de Psicología siguen entrando")
    def t():
        for nombre, tok in (('dirección', DIR_A_TOKEN), ('profesor', PROF_A_TOKEN)):
            r = client.get('/api/psicologia/casos', headers=auth(tok))
            assert r.status_code == 200, \
                f'{nombre} debe seguir accediendo a psicología, dio {r.status_code}'

    @test("S9. Profesor NO obtiene boletín de un estudiante que no tiene asignado")
    def t():
        # Segundo curso del colegio A, SIN asignación para PROF_A.
        grados = client.get('/api/grados', headers=auth(DIR_A_TOKEN)).json()
        tandas = client.get('/api/tandas', headers=auth(DIR_A_TOKEN)).json()
        r = client.post('/api/cursos', json={
            'nombre': 'Z', 'grado_id': grados[0]['id'], 'tanda_id': tandas[0]['id']
        }, headers=auth(DIR_A_TOKEN))
        assert r.status_code in (200, 201), r.text
        curso_ajeno = r.json()['id']

        r = client.post('/api/estudiantes', json={
            'nombre': 'NoAsignado', 'apellido': 'S9',
            'curso_id': curso_ajeno, 'no_lista': 1, 'matricula': 'M-S9'
        }, headers=auth(DIR_A_TOKEN))
        assert r.status_code in (200, 201), r.text
        est_ajeno = r.json()['id']

        # Mismo colegio, pero fuera de las asignaciones del profesor.
        # Los SIETE endpoints documentales que protege guard_profesor_curso.
        for ruta in (f'/api/boletines/estudiante/{est_ajeno}',
                     f'/api/boletines/estudiante/{est_ajeno}/pdf',
                     f'/api/boletines/estudiante/{est_ajeno}/pdf-minerd-v2',
                     f'/api/boletines-primaria/estudiante/{est_ajeno}',
                     f'/api/boletines-primaria/estudiante/{est_ajeno}/pdf',
                     f'/api/boletines-primaria/curso/{curso_ajeno}/pdf',
                     f'/api/calificaciones-secundaria/reporte-padres/curso/{curso_ajeno}/pdf'):
            r = client.get(ruta, headers=auth(PROF_A_TOKEN))
            assert r.status_code == 403, \
                f'{ruta} debe dar 403 para un profesor sin asignación, dio {r.status_code}'

        # Dirección y secretaría conservan su alcance de colegio completo.
        # En estos endpoints el ÚNICO 403 posible es el candado de profesor:
        # el resto de los caminos de error devuelven 404. Por eso basta con
        # comprobar que no aparece un 403.
        for nombre, tok in (('dirección', DIR_A_TOKEN), ('secretaría', SEC_A_TOKEN)):
            for ruta in (f'/api/boletines/estudiante/{est_ajeno}',
                         f'/api/calificaciones-secundaria/reporte-padres/curso/{curso_ajeno}/pdf'):
                r = client.get(ruta, headers=auth(tok))
                assert r.status_code != 403, \
                    (f'{nombre} no debe verse afectada por el candado de profesor '
                     f'en {ruta} (dio {r.status_code})')

    @test("S10. Profesor SÍ obtiene el boletín de un estudiante de su curso")
    def t():
        # A['est'] está en A['curso'], donde PROF_A tiene asignación activa.
        # El único 403 posible en estos endpoints es guard_profesor_curso, así
        # que "no bloqueado por autorización" == "no dio 403". El PDF puede
        # devolver 404/400 por falta de notas o de año escolar: eso no es un
        # problema de permisos y no debe hacer fallar este test.
        for ruta in (f'/api/boletines/estudiante/{A["est"]}',
                     f'/api/boletines/estudiante/{A["est"]}/pdf-minerd-v2',
                     f'/api/calificaciones-secundaria/reporte-padres/curso/{A["curso"]}/pdf'):
            r = client.get(ruta, headers=auth(PROF_A_TOKEN))
            assert r.status_code != 403, \
                (f'{ruta}: el profesor asignado NO debe ser bloqueado '
                 f'(dio {r.status_code}: {r.text[:200]})')

    # ─────────────────────────────────────────────────────────────
    # SECCIÓN U — v2.19.3-B (identidad de curso en los filtros de Reportes)
    # ─────────────────────────────────────────────────────────────

    print(f"{BOLD}\n=== U. v2.19.3-B — FILTROS DE REPORTES ==={RESET}")

    @test("U1. GET /api/reportes expone estudiante_curso_id con el curso real")
    def t():
        r = client.post('/api/reportes', json={
            'estudiante_id': A['est'],
            'titulo': 'Reporte U1',
            'descripcion': 'Situación de prueba U1',
            'tipo': 'conducta',
            'gravedad': 'leve',
        }, headers=auth(PROF_A_TOKEN))
        assert r.status_code == 201, f'el profesor asignado debe poder reportar: {r.text}'
        rep_id = r.json()['id']

        reportes = client.get('/api/reportes', headers=auth(DIR_A_TOKEN)).json()
        rep = next((x for x in reportes if x['id'] == rep_id), None)
        assert rep is not None, 'Dirección debe ver el reporte de su colegio'

        # El campo nuevo existe y trae la IDENTIDAD del curso del estudiante.
        assert 'estudiante_curso_id' in rep, \
            "la respuesta debe incluir 'estudiante_curso_id'"
        assert rep['estudiante_curso_id'] == A['curso'], \
            (f"estudiante_curso_id debe ser el curso_id real del estudiante "
             f"({A['curso']}), vino {rep['estudiante_curso_id']!r}")

    @test("U2. estudiante_curso (nombre para mostrar) sigue existiendo")
    def t():
        # No-regresión: el modal de detalle y el mensaje de WhatsApp a los
        # padres siguen usando el nombre completo del curso.
        reportes = client.get('/api/reportes', headers=auth(DIR_A_TOKEN)).json()
        assert reportes, 'setup: debería haber al menos un reporte'
        rep = reportes[0]
        assert 'estudiante_curso' in rep, \
            "'estudiante_curso' no debe desaparecer: lo usan el detalle y WhatsApp"
        assert rep['estudiante_curso'], 'estudiante_curso no debería venir vacío'
        # Y es un NOMBRE, no un número: es justamente por eso que no sirve
        # como identidad y se agregó estudiante_curso_id.
        assert isinstance(rep['estudiante_curso'], str), \
            'estudiante_curso debe seguir siendo el nombre para mostrar'

    @test("U3. El curso expuesto permite filtrar de verdad (ID contra ID)")
    def t():
        # Reproduce lo que hace ReportesPage: quedarse con los reportes cuyo
        # estudiante_curso_id coincide con el curso elegido. Antes del arreglo
        # el frontend comparaba el nombre completo contra Curso.nombre (solo la
        # sección) y el resultado era SIEMPRE vacío.
        reportes = client.get('/api/reportes', headers=auth(DIR_A_TOKEN)).json()
        del_curso = [x for x in reportes if x.get('estudiante_curso_id') == A['curso']]
        assert del_curso, \
            'filtrar por el curso del estudiante no puede devolver una lista vacía'

        # Y el nombre NO sirve como identidad: es la causa raíz del bug.
        cursos = client.get('/api/cursos', headers=auth(DIR_A_TOKEN)).json()
        curso = next(c for c in cursos if c['id'] == A['curso'])
        assert curso['nombre'] != del_curso[0]['estudiante_curso'], \
            ('Curso.nombre debería ser solo la sección y distinto del nombre '
             'completo: si dejaran de diferir, el bug original sería invisible')

    @test("U4. Separación por tenant intacta en /api/reportes")
    def t():
        reportes_a = client.get('/api/reportes', headers=auth(DIR_A_TOKEN)).json()
        ids_a = {x['id'] for x in reportes_a}
        cursos_a = {x.get('estudiante_curso_id') for x in reportes_a}
        assert ids_a, 'setup: colegio A debe tener reportes'

        reportes_b = client.get('/api/reportes', headers=auth(DIR_B_TOKEN)).json()
        ids_b = {x['id'] for x in reportes_b}
        assert not (ids_a & ids_b), \
            'el colegio B no debe ver ningún reporte del colegio A'
        # El campo nuevo tampoco puede filtrar cursos de otro colegio.
        for x in reportes_b:
            assert x.get('estudiante_curso_id') not in cursos_a, \
                'estudiante_curso_id expuso un curso del otro colegio'

    @test("U5. El alcance por rol de /api/reportes no cambió")
    def t():
        reportes_dir = client.get('/api/reportes', headers=auth(DIR_A_TOKEN)).json()
        ids_dir = {x['id'] for x in reportes_dir}

        # Profesor: ve el reporte que él creó sobre un estudiante de su curso.
        reportes_prof = client.get('/api/reportes', headers=auth(PROF_A_TOKEN)).json()
        ids_prof = {x['id'] for x in reportes_prof}
        assert ids_prof, 'el profesor debe ver los reportes que él levantó'
        assert ids_prof <= ids_dir, \
            'el profesor nunca debe ver más reportes que Dirección'
        for x in reportes_prof:
            assert 'estudiante_curso_id' in x, \
                'el campo nuevo debe estar también para el profesor'

        # Profesor del OTRO colegio: nada.
        reportes_prof_b = client.get('/api/reportes', headers=auth(PROF_B_TOKEN)).json()
        assert not ({x['id'] for x in reportes_prof_b} & ids_dir), \
            'el profesor del colegio B no debe ver reportes del colegio A'

        # Secretaría de A: conserva su lectura de colegio (comportamiento previo).
        r = client.get('/api/reportes', headers=auth(SEC_A_TOKEN))
        assert r.status_code == 200, \
            f'secretaría debe seguir leyendo reportes: {r.status_code}'

    # ─────────────────────────────────────────────────────────────
    # SECCIÓN T — v2.19.3-C (mensajes internos con Notificacion + Push)
    # ─────────────────────────────────────────────────────────────

    print(f"{BOLD}\n=== T. v2.19.3-C — MENSAJES CON NOTIFICACIÓN ==={RESET}")

    # El director del colegio A es el usuario 'direccion' que crea init_db;
    # su id no está en el dict del setup, así que se resuelve por /auth/me.
    DIR_A_ID = client.get('/api/auth/me', headers=auth(DIR_A_TOKEN)).json()['id']

    def _notifs_de_mensaje(tok):
        """Notificaciones de mensajería de ese usuario (las que apuntan a /comunicacion)."""
        r = client.get('/api/notificaciones?limit=100', headers=auth(tok))
        assert r.status_code == 200, f'no se pudo leer notificaciones: {r.text}'
        return [n for n in r.json().get('notificaciones', [])
                if n.get('link') == '/comunicacion' and n.get('tipo') == 'mensaje']

    @test("T1. Un mensaje individual crea una Notificacion para el destinatario")
    def t():
        antes = len(_notifs_de_mensaje(DIR_A_TOKEN))
        r = client.post('/api/mensajes', json={
            'destinatario_id': DIR_A_ID,
            'asunto': 'Asunto secreto T1',
            'contenido': 'Contenido confidencial T1',
        }, headers=auth(PROF_A_TOKEN))
        assert r.status_code == 201, f'el mensaje debe enviarse: {r.text}'

        despues = _notifs_de_mensaje(DIR_A_TOKEN)
        assert len(despues) == antes + 1, \
            f'el destinatario debe recibir exactamente 1 notificación nueva ({antes} → {len(despues)})'

    @test("T2. El remitente NO se notifica a sí mismo")
    def t():
        antes = len(_notifs_de_mensaje(PROF_A_TOKEN))
        r = client.post('/api/mensajes', json={
            'destinatario_id': DIR_A_ID,
            'asunto': 'Asunto T2',
            'contenido': 'Contenido T2',
        }, headers=auth(PROF_A_TOKEN))
        assert r.status_code == 201, r.text
        despues = len(_notifs_de_mensaje(PROF_A_TOKEN))
        assert despues == antes, \
            f'quien envía no debe recibir notificación de su propio mensaje ({antes} → {despues})'

    @test("T3. La notificación de mensaje no cruza al otro colegio")
    def t():
        antes_b = len(_notifs_de_mensaje(DIR_B_TOKEN))
        r = client.post('/api/mensajes', json={
            'destinatario_id': DIR_A_ID,
            'asunto': 'Asunto T3',
            'contenido': 'Contenido T3',
        }, headers=auth(PROF_A_TOKEN))
        assert r.status_code == 201, r.text
        assert len(_notifs_de_mensaje(DIR_B_TOKEN)) == antes_b, \
            'el colegio B no debe recibir notificaciones de mensajes del colegio A'

        # Y el destinatario de otro colegio sigue siendo inalcanzable.
        r = client.post('/api/mensajes', json={
            'destinatario_id': B['prof'],
            'asunto': 'Cross-tenant T3',
            'contenido': 'No debería llegar',
        }, headers=auth(PROF_A_TOKEN))
        assert r.status_code == 404, \
            f'no se puede escribir a un usuario de otro colegio, dio {r.status_code}'

    @test("T4. El título lleva el nombre del remitente")
    def t():
        r = client.post('/api/mensajes', json={
            'destinatario_id': DIR_A_ID,
            'asunto': 'Asunto T4',
            'contenido': 'Contenido T4',
        }, headers=auth(PROF_A_TOKEN))
        assert r.status_code == 201, r.text

        notif = _notifs_de_mensaje(DIR_A_TOKEN)[0]
        titulo = notif.get('titulo') or ''
        assert 'Nuevo mensaje' in titulo, f'título inesperado: {titulo!r}'

        # Se compara contra el nombre REAL del remitente, no contra una cadena
        # adivinada: así el test sigue valiendo si cambian los datos del setup.
        yo = client.get('/api/auth/me', headers=auth(PROF_A_TOKEN)).json()
        assert yo['nombre_completo'] in titulo, \
            (f"el título debe identificar a quien escribe "
             f"({yo['nombre_completo']!r}), vino {titulo!r}")

    @test("T5. Ni el asunto ni el contenido llegan a la pantalla bloqueada")
    def t():
        secreto_asunto = 'ASUNTOCONFIDENCIALT5'
        secreto_cuerpo = 'CONTENIDOCONFIDENCIALT5'
        r = client.post('/api/mensajes', json={
            'destinatario_id': DIR_A_ID,
            'asunto': secreto_asunto,
            'contenido': secreto_cuerpo,
        }, headers=auth(PROF_A_TOKEN))
        assert r.status_code == 201, r.text

        notif = _notifs_de_mensaje(DIR_A_TOKEN)[0]
        texto = f"{notif.get('titulo') or ''} {notif.get('mensaje') or ''}"
        assert secreto_asunto not in texto, \
            f'el asunto no debe viajar en la notificación: {texto!r}'
        assert secreto_cuerpo not in texto, \
            f'el contenido no debe viajar en la notificación: {texto!r}'
        assert 'Tienes un nuevo mensaje' in (notif.get('mensaje') or ''), \
            f'el cuerpo debe ser el texto genérico, vino {notif.get("mensaje")!r}'

    @test("T6. La notificación enlaza a /comunicacion")
    def t():
        notif = _notifs_de_mensaje(DIR_A_TOKEN)[0]
        assert notif.get('link') == '/comunicacion', \
            f"link debe ser '/comunicacion', vino {notif.get('link')!r}"
        assert notif.get('tipo') == 'mensaje', \
            f"tipo debe ser 'mensaje', vino {notif.get('tipo')!r}"

    @test("T7. Un mensaje genera UNA sola notificación (dedup por evento_key)")
    def t():
        antes = len(_notifs_de_mensaje(DIR_A_TOKEN))
        r = client.post('/api/mensajes', json={
            'destinatario_id': DIR_A_ID,
            'asunto': 'Asunto T7',
            'contenido': 'Contenido T7',
        }, headers=auth(PROF_A_TOKEN))
        assert r.status_code == 201, r.text
        despues = len(_notifs_de_mensaje(DIR_A_TOKEN))
        assert despues == antes + 1, \
            f'un mensaje = una notificación, no {despues - antes}'

    @test("T8. El masivo notifica a cada destinatario real y no al emisor")
    def t():
        antes_prof = len(_notifs_de_mensaje(PROF_A_TOKEN))
        antes_dir = len(_notifs_de_mensaje(DIR_A_TOKEN))

        r = client.post('/api/mensajes/masivo', json={
            'rol': 'profesor',
            'asunto': 'Difusión T8',
            'contenido': 'Cuerpo de la difusión T8',
        }, headers=auth(DIR_A_TOKEN))
        assert r.status_code == 201, r.text
        enviados = r.json().get('enviados', 0)
        assert enviados >= 1, f'la difusión debe alcanzar al menos un profesor: {r.json()}'

        # Cada destinatario real recibe exactamente una notificación.
        despues_prof = len(_notifs_de_mensaje(PROF_A_TOKEN))
        assert despues_prof == antes_prof + 1, \
            f'el profesor destinatario debe recibir 1 notificación ({antes_prof} → {despues_prof})'

        # El emisor no se notifica a sí mismo.
        assert len(_notifs_de_mensaje(DIR_A_TOKEN)) == antes_dir, \
            'quien difunde no debe recibir su propia notificación'

        # Y nunca sale del colegio.
        assert not [n for n in _notifs_de_mensaje(PROF_B_TOKEN)
                    if 'Difusión T8' in (n.get('titulo') or '')], \
            'la difusión del colegio A no puede notificar al colegio B'

    @test("T9. No-regresión: el mensaje se sigue guardando y entregando")
    def t():
        r = client.post('/api/mensajes', json={
            'destinatario_id': DIR_A_ID,
            'asunto': 'Asunto T9 visible',
            'contenido': 'Contenido T9 visible',
        }, headers=auth(PROF_A_TOKEN))
        assert r.status_code == 201, r.text
        mid = r.json()['id']

        # El destinatario lo ve en su bandeja, con asunto y contenido completos:
        # la notificación es genérica, el mensaje NO.
        recibidos = client.get('/api/mensajes', headers=auth(DIR_A_TOKEN)).json()
        msg = next((m for m in recibidos if m['id'] == mid and m['tipo'] == 'recibido'), None)
        assert msg is not None, 'el mensaje debe llegar a la bandeja del destinatario'
        assert msg['asunto'] == 'Asunto T9 visible'
        assert 'Contenido T9 visible' in msg['contenido']

        # Y el contador de no leídos lo cuenta.
        no_leidos = client.get('/api/mensajes/no-leidos', headers=auth(DIR_A_TOKEN)).json()
        assert no_leidos.get('count', 0) >= 1, \
            f'el contador de no leídos debe reflejarlo: {no_leidos}'

    # ─────────────────────────────────────────────────────────────
    # SECCIÓN V — v2.19.5 (nivel correcto en el borrador del Registro Escolar)
    # ─────────────────────────────────────────────────────────────

    print(f"{BOLD}\n=== V. v2.19.5 — BORRADOR DEL REGISTRO ESCOLAR ==={RESET}")

    # El borrador de secundaria llevaba copiada la guarda del de primaria y
    # exigía nivel 'primaria' dentro del endpoint de secundaria: rechazaba con
    # 400 justo los cursos que debe atender, y el mensaje se contradecía solo
    # ("use el registro de secundaria" estando ya en él). En producción eso
    # dejaba sin borrador a TODOS los cursos de secundaria.
    #
    # El curso de la sección A ya es de secundaria (los grados que crea init_db
    # son todos de secundaria); acá agregamos uno de primaria para poder probar
    # los dos lados de la guarda.
    _r = client.post('/api/grados', json={
        'nombre': '1ro Primaria V', 'nivel': 'primaria', 'orden': 120,
    }, headers=auth(DIR_A_TOKEN))
    assert _r.status_code in (200, 201), f'setup V: crear grado primaria: {_r.text}'
    V_GRADO_PRI = _r.json()['id']
    _r = client.post('/api/cursos', json={
        'grado_id': V_GRADO_PRI, 'tanda_id': A['tanda'], 'nombre': 'V',
    }, headers=auth(DIR_A_TOKEN))
    assert _r.status_code in (200, 201), f'setup V: crear curso primaria: {_r.text}'
    V_CURSO_PRI = _r.json()['id']

    # Marca inequívoca del rechazo por NIVEL, para no confundirlo con los
    # rechazos legítimos por datos incompletos o por permisos.
    def _rechazado_por_nivel(resp):
        if resp.status_code != 400:
            return False
        return 'solo para cursos de' in (resp.text or '').lower()

    @test("V1. Curso de SECUNDARIA: el borrador de secundaria ya no lo rechaza por nivel")
    def t():
        r = client.get(f'/api/registros/secundaria/{A["curso"]}/preview-pdf',
                       headers=auth(DIR_A_TOKEN))
        assert not _rechazado_por_nivel(r), \
            (f'un curso de secundaria no puede ser rechazado por nivel en SU '
             f'propio borrador: {r.status_code} {r.text[:200]}')
        # Y de hecho genera el PDF: el borrador es tolerante a datos incompletos
        # (este curso no tiene calificaciones ni horarios cargados).
        assert r.status_code == 200, \
            f'el borrador de secundaria debe generarse: {r.status_code} {r.text[:200]}'
        assert 'pdf' in r.headers.get('content-type', ''), \
            f"esperaba un PDF, vino {r.headers.get('content-type')!r}"
        assert r.content[:4] == b'%PDF', 'el cuerpo debe ser un PDF real'

    @test("V2. Curso de PRIMARIA: el borrador de secundaria lo rechaza con 400")
    def t():
        r = client.get(f'/api/registros/secundaria/{V_CURSO_PRI}/preview-pdf',
                       headers=auth(DIR_A_TOKEN))
        assert r.status_code == 400, \
            f'un curso de primaria no puede sacar el borrador de secundaria: {r.status_code}'
        assert 'SECUNDARIA' in r.text, \
            f'el mensaje debe decir que este registro es solo de secundaria: {r.text[:200]}'
        assert 'pdf' not in r.headers.get('content-type', ''), \
            'no debe devolver el documento equivocado'

    @test("V3. El borrador de PRIMARIA sigue aceptando primaria (no-regresión)")
    def t():
        r = client.get(f'/api/registros/primaria/{V_CURSO_PRI}/preview-pdf',
                       headers=auth(DIR_A_TOKEN))
        assert r.status_code == 200, \
            f'el borrador de primaria no debe haberse tocado: {r.status_code} {r.text[:200]}'
        assert r.content[:4] == b'%PDF', 'el borrador de primaria debe seguir siendo un PDF'

    @test("V4. El borrador de PRIMARIA sigue rechazando secundaria (no-regresión)")
    def t():
        r = client.get(f'/api/registros/primaria/{A["curso"]}/preview-pdf',
                       headers=auth(DIR_A_TOKEN))
        assert r.status_code == 400, \
            f'un curso de secundaria no debe sacar el borrador de primaria: {r.status_code}'
        assert 'PRIMARIA' in r.text, f'el mensaje de primaria no cambió: {r.text[:200]}'

    @test("V5. El validador oficial y force=true no cambiaron")
    def t():
        # El arreglo toca SOLO el borrador. El registro oficial debe seguir
        # bloqueando por datos incompletos, y force=true debe seguir sin
        # saltarse los errores (solo omite advertencias).
        r = client.get(f'/api/registros/secundaria/{A["curso"]}',
                       headers=auth(DIR_A_TOKEN))
        assert r.status_code == 400, \
            f'el oficial debe seguir exigiendo datos completos: {r.status_code}'
        cuerpo = r.json()
        assert cuerpo.get('detalle'), 'debe seguir listando qué falta'

        r_force = client.get(f'/api/registros/secundaria/{A["curso"]}?force=true',
                             headers=auth(DIR_A_TOKEN))
        assert r_force.status_code == 400, \
            f'force=true no puede saltarse los ERRORES de datos: {r_force.status_code}'
        assert 'pdf' not in r_force.headers.get('content-type', ''), \
            'force=true no debe generar un registro oficial incompleto'

    @test("V6. Aislamiento por tenant intacto en los borradores")
    def t():
        # El director del colegio B no puede sacar el borrador de un curso de A,
        # ni por el endpoint de secundaria ni por el de primaria.
        for nivel, curso_id in (('secundaria', A['curso']), ('primaria', V_CURSO_PRI)):
            r = client.get(f'/api/registros/{nivel}/{curso_id}/preview-pdf',
                           headers=auth(DIR_B_TOKEN))
            assert r.status_code in (403, 404), \
                (f'B no debe alcanzar el curso {curso_id} de A por {nivel}: '
                 f'{r.status_code} {r.text[:150]}')
            assert 'pdf' not in r.headers.get('content-type', ''), \
                f'B recibió un PDF de un curso del colegio A ({nivel})'

    @test("V7. Alcance por rol intacto en el borrador de secundaria")
    def t():
        # Profesor CON asignación en el curso: pasa la guarda de rol y la de
        # nivel (es justo el caso que el bug rompía para todo secundaria).
        r = client.get(f'/api/registros/secundaria/{A["curso"]}/preview-pdf',
                       headers=auth(PROF_A_TOKEN))
        assert r.status_code == 200, \
            f'el profesor asignado debe poder ver el borrador: {r.status_code} {r.text[:200]}'

        # Profesor del colegio B: no tiene asignación ahí; nunca 200.
        r_b = client.get(f'/api/registros/secundaria/{A["curso"]}/preview-pdf',
                         headers=auth(PROF_B_TOKEN))
        assert r_b.status_code in (403, 404), \
            f'el profesor de B no debe ver el borrador de A: {r_b.status_code}'

        # Secretaría no está en los roles del endpoint.
        r_s = client.get(f'/api/registros/secundaria/{A["curso"]}/preview-pdf',
                         headers=auth(SEC_A_TOKEN))
        assert r_s.status_code == 403, \
            f'secretaría no debe entrar al borrador: {r_s.status_code}'

        # Sin token: 401/403, nunca un PDF.
        r_anon = client.get(f'/api/registros/secundaria/{A["curso"]}/preview-pdf')
        assert r_anon.status_code in (401, 403), \
            f'sin autenticar no puede salir un registro: {r_anon.status_code}'

    # ─────────────────────────────────────────────────────────────
    # SECCIÓN W — v2.19.6 (rendimiento del borrador, sin cambiar el documento)
    # ─────────────────────────────────────────────────────────────

    print(f"{BOLD}\n=== W. v2.19.6 — SELLO BORRADOR EN UNA PASADA ==={RESET}")

    # v2.19.6 dejó de generar el PDF y volver a recorrerlo para sellarlo: el
    # sello se estampa durante la única pasada de generación, como Form XObject
    # reutilizado. Lo que NO puede cambiar es el documento: mismo número de
    # páginas, sello en todas, y el registro OFICIAL sin sello alguno.

    def _pdf_registro(marca):
        from registro_escolar import generar_registro_desde_sistema
        colegio_info = {
            'nombre': 'Centro W', 'regional': '15', 'distrito': '15-05',
            'direccion': '', 'telefono': '', 'email': '', 'director': '',
            'codigo_centro': '08-01-0123', 'codigo_cartografia': '',
            'sector': '', 'zona': '', 'jornada': '', 'coordinador': 'Titular W',
        }
        curso_info = {'grado': '1ro Secundaria', 'seccion': 'A', 'tanda': 'Matutina'}
        estudiantes = [{
            'id': 1, 'no_lista': 1, 'nombre': 'Estudiante W', 'sexo': 'F',
            'fecha_nacimiento': None, 'cedula': '', 'matricula': 'W001',
            'lugar_nacimiento': '', 'nacionalidad': '', 'direccion': '',
            'condicion_entrada': 'nuevo',
        }]
        asignaturas_data = {'Matemática': {
            'docente': 'Prof W', 'asistencias': {}, 'asistencia_matriz': [],
            'calificaciones': {},
        }}
        return generar_registro_desde_sistema(
            colegio_info, curso_info, '2025-2026', estudiantes,
            asignaturas_data, 1, marca_borrador=marca)

    def _paginas_con_sello(pdf_bytes):
        """Cuenta páginas cuyo contenido referencia el XObject del sello."""
        from pypdf import PdfReader
        from registro_borrador import NOMBRE_XOBJECT
        import io as _io
        lector = PdfReader(_io.BytesIO(pdf_bytes))
        total = 0
        for pagina in lector.pages:
            recursos = pagina.get('/Resources')
            if recursos is None:
                continue
            xobjs = recursos.get_object().get('/XObject')
            if xobjs is not None and NOMBRE_XOBJECT in xobjs.get_object():
                total += 1
        return total, len(lector.pages)

    @test("W1. El borrador lleva el sello en TODAS las páginas")
    def t():
        pdf = _pdf_registro(True)
        assert pdf[:4] == b'%PDF', 'debe ser un PDF válido'
        con_sello, total = _paginas_con_sello(pdf)
        assert total > 100, f'el registro de 1ro secundaria tiene 170 páginas, vinieron {total}'
        assert con_sello == total, \
            f'el sello debe estar en las {total} páginas, está en {con_sello}'

    @test("W2. El registro OFICIAL no lleva sello, y tiene las mismas páginas")
    def t():
        oficial = _pdf_registro(False)
        borrador = _pdf_registro(True)
        assert oficial[:4] == b'%PDF'
        con_sello_of, total_of = _paginas_con_sello(oficial)
        con_sello_bo, total_bo = _paginas_con_sello(borrador)
        assert con_sello_of == 0, \
            f'el registro oficial NO puede llevar sello (lo lleva en {con_sello_of} páginas)'
        assert total_of == total_bo, \
            f'sellar no puede cambiar el número de páginas: {total_of} vs {total_bo}'

    @test("W3. aplicar_marca_borrador sigue sellando todas las páginas")
    def t():
        # Sigue en uso para el borrador de PRIMARIA, que arma el PDF por otro
        # camino. Se verifica sobre el registro oficial ya generado.
        from registro_borrador import aplicar_marca_borrador
        oficial = _pdf_registro(False)
        sellado = aplicar_marca_borrador(oficial)
        assert sellado[:4] == b'%PDF'
        con_sello, total = _paginas_con_sello(sellado)
        _, total_original = _paginas_con_sello(oficial)
        assert total == total_original, 'no puede cambiar el número de páginas'
        assert con_sello == total, \
            f'el sello debe estar en las {total} páginas, está en {con_sello}'

    @test("W4. El borrador de secundaria del endpoint sigue siendo un PDF sellado")
    def t():
        r = client.get(f'/api/registros/secundaria/{A["curso"]}/preview-pdf',
                       headers=auth(DIR_A_TOKEN))
        assert r.status_code == 200, f'{r.status_code} {r.text[:200]}'
        assert r.content[:4] == b'%PDF'
        con_sello, total = _paginas_con_sello(r.content)
        assert total > 100, f'esperaba el registro completo, vinieron {total} páginas'
        assert con_sello == total, \
            f'el endpoint debe entregar el sello en las {total} páginas, vino en {con_sello}'

    # ─────────────────────────────────────────────────────────────
    # SECCIÓN X — v2.19.7 (los datos que YA existen llegan al Registro)
    # ─────────────────────────────────────────────────────────────

    print(f"{BOLD}\n=== X. v2.19.7 — DATOS EN VIVO EN EL REGISTRO ==={RESET}")

    # Se siembra el MISMO escenario que tiene el colegio en producción:
    # el año escolar declara un rango (2024-09-01 → 2025-06-30) que NO cubre
    # las fechas en las que realmente se tomó asistencia. Con eso, la rejilla
    # de días se construía solo con los días esperados del año escolar y las
    # marcas reales caían fuera: la hoja salía vacía teniendo cientos de
    # registros. Y las notas de secundaria viven en CalificacionSecundaria,
    # que el Registro ni siquiera consultaba.
    from datetime import date as _date
    from database import SessionLocal as _SL
    from models import (Asistencia as _Asist, CalificacionSecundaria as _CS,
                        Horario as _Hor, AnoEscolar as _Ano, Estudiante as _Est,
                        Usuario as _Usr)

    X_FECHAS = {  # fecha → estado, uno por cada código del registro
        _date(2026, 7, 15): 'presente',
        _date(2026, 8, 5): 'ausente',
        _date(2026, 8, 12): 'tardanza',
        _date(2026, 9, 2): 'excusa',
    }
    X_COMPETENCIAS = [(1, 65, 60, 65, 60), (2, 67, 78, 68, 89),
                      (3, 56, 50, 71, 95), (4, 66, 63, 56, 94)]

    _db = _SL()
    try:
        A_COLEGIO_ID = _db.query(_Usr).filter_by(username='direccion').first().colegio_id
        _ano = _db.query(_Ano).filter_by(colegio_id=A_COLEGIO_ID, activo=True).first()
        assert _ano is not None, 'setup X: hace falta un año escolar activo'
        _ano.fecha_inicio = _date(2024, 9, 1)
        _ano.fecha_fin = _date(2025, 6, 30)

        # Horario de la asignatura: sin él no hay días esperados y el flujo
        # caería al modo legacy, que no es el que falla en producción.
        _db.add(_Hor(colegio_id=A_COLEGIO_ID, profesor_id=A['prof'], curso_id=A['curso'],
                     asignatura_id=A['asig'], dia='Miércoles', hora_inicio='08:15',
                     hora_fin='09:00', tipo_bloque='clase', activo=True))

        X_EST = A['est']
        for _f, _estado in X_FECHAS.items():
            _db.add(_Asist(colegio_id=A_COLEGIO_ID, estudiante_id=X_EST,
                           curso_id=A['curso'], asignatura_id=A['asig'],
                           fecha=_f, estado=_estado))

        for _num, _p1, _p2, _p3, _p4 in X_COMPETENCIAS:
            _db.add(_CS(colegio_id=A_COLEGIO_ID, estudiante_id=X_EST,
                        asignatura_id=A['asig'], ano_escolar_id=_ano.id,
                        competencia_numero=_num, p1=_p1, p2=_p2, p3=_p3, p4=_p4))

        # Segundo estudiante: 4 competencias pero SOLO P1 → PC1 sí, CF no.
        _r = client.post('/api/estudiantes', json={
            'nombre': 'Parcial', 'apellido': 'Equis', 'sexo': 'F',
            'fecha_nacimiento': '2011-05-05', 'curso_id': A['curso'],
            'no_lista': 30, 'matricula': 'X-PARCIAL',
        }, headers=auth(DIR_A_TOKEN))
        assert _r.status_code in (200, 201), f'setup X: crear estudiante: {_r.text}'
        X_EST_PARCIAL = _r.json()['id']
        for _num, _p1, _, _, _ in X_COMPETENCIAS:
            _db.add(_CS(colegio_id=A_COLEGIO_ID, estudiante_id=X_EST_PARCIAL,
                        asignatura_id=A['asig'], ano_escolar_id=_ano.id,
                        competencia_numero=_num, p1=_p1))

        # Tercer estudiante: una sola competencia → nada calculable.
        _r = client.post('/api/estudiantes', json={
            'nombre': 'Incompleto', 'apellido': 'Equis', 'sexo': 'M',
            'fecha_nacimiento': '2011-06-06', 'curso_id': A['curso'],
            'no_lista': 31, 'matricula': 'X-INCOMPLETO',
        }, headers=auth(DIR_A_TOKEN))
        assert _r.status_code in (200, 201), f'setup X: crear estudiante: {_r.text}'
        X_EST_INCOMPLETO = _r.json()['id']
        _db.add(_CS(colegio_id=A_COLEGIO_ID, estudiante_id=X_EST_INCOMPLETO,
                    asignatura_id=A['asig'], ano_escolar_id=_ano.id,
                    competencia_numero=1, p1=90, p2=90, p3=90, p4=90))
        _db.commit()
    finally:
        _db.close()

    def _datos_asignatura():
        """asignaturas_data tal como lo arma el Registro, con la sesión real."""
        import app as _app
        _s = _SL()
        try:
            _u = _s.query(_Usr).filter_by(username='direccion').first()
            _ests = _s.query(_Est).filter_by(curso_id=A['curso'], activo=True).order_by(
                _Est.no_lista).all()
            _data = _app._cargar_datos_asignaturas_secundaria(_s, _u, A['curso'], 1, _ests)
            _orden = {e.id: i for i, e in enumerate(_ests)}
            return _data, _orden
        finally:
            _s.close()

    @test("X1. La asistencia real (P/A/T/E) llega a su día y mes del Registro")
    def t():
        data, orden = _datos_asignatura()
        clave = next((k for k in data if 'atem' in k), None)
        assert clave, f'no se resolvió Matemática en el registro: {list(data)[:4]}'
        matriz = data[clave].get('asistencia_matriz') or []
        assert matriz, 'la matriz de asistencia no puede venir vacía habiendo registros'

        fila_idx = orden[A['est']]
        encontrados = {}
        for mes in matriz:
            dias = mes['dias']
            fila = next((f for f in mes['filas'] if f['estudiante_id'] == A['est']), None)
            if not fila:
                continue
            for i, dia in enumerate(dias):
                if fila['valores'][i]:
                    encontrados[(mes['mes_num'], dia)] = fila['valores'][i]

        esperado = {(f.month, f.day): {'presente': 'P', 'ausente': 'A',
                                       'tardanza': 'T', 'excusa': 'E'}[e]
                    for f, e in X_FECHAS.items()}
        for clave_fecha, codigo in esperado.items():
            assert clave_fecha in encontrados, \
                (f'la marca del {clave_fecha[1]}/{clave_fecha[0]} no llegó a la hoja. '
                 f'Días con marca: {sorted(encontrados)}')
            assert encontrados[clave_fecha] == codigo, \
                f'{clave_fecha}: se esperaba {codigo} y llegó {encontrados[clave_fecha]!r}'
        assert fila_idx >= 0

    @test("X2. Las fechas fuera del rango del año escolar NO se pierden")
    def t():
        # Es exactamente el caso de producción: el año escolar declara
        # 2024-2025 y la asistencia se tomó en 2026. Antes de v2.19.7 la
        # rejilla no tenía ni julio ni agosto y septiembre no tenía el día 2.
        data, _ = _datos_asignatura()
        clave = next(k for k in data if 'atem' in k)
        matriz = data[clave]['asistencia_matriz']
        meses_con_marca = {m['mes_num'] for m in matriz
                           for f in m['filas'] for v in f['valores'] if v}
        assert {7, 8, 9} <= meses_con_marca, \
            f'faltan meses con marcas; llegaron {sorted(meses_con_marca)}'
        sept = next(m for m in matriz if m['mes_num'] == 9)
        assert 2 in sept['dias'], \
            f"el día 2 de septiembre tiene registro y no está en la rejilla: {sept['dias']}"

    @test("X3. Las notas de CalificacionSecundaria producen PC y CF en el Registro")
    def t():
        data, orden = _datos_asignatura()
        clave = next(k for k in data if 'atem' in k)
        califs = data[clave]['calificaciones']
        fila = califs.get(orden[A['est']])
        assert fila is not None, 'el estudiante con notas debe tener fila de calificaciones'
        # Mismos números que calcula el boletín con estas competencias.
        assert fila['pc1'] == 63.5, f"PC1 esperado 63.5, vino {fila['pc1']}"
        assert fila['pc2'] == 62.8, f"PC2 esperado 62.8, vino {fila['pc2']}"
        assert fila['pc3'] == 65.0, f"PC3 esperado 65.0, vino {fila['pc3']}"
        assert fila['pc4'] == 84.5, f"PC4 esperado 84.5, vino {fila['pc4']}"
        assert fila['cf'] == 69, f"CF esperado 69, vino {fila['cf']}"

    @test("X4. Un estudiante incompleto NO recibe un promedio inventado")
    def t():
        data, orden = _datos_asignatura()
        clave = next(k for k in data if 'atem' in k)
        califs = data[clave]['calificaciones']

        parcial = califs.get(orden[X_EST_PARCIAL])
        assert parcial is not None, 'el estudiante con P1 debe tener fila'
        assert parcial['pc1'] == 63.5, f"con las 4 competencias en P1 debe salir PC1: {parcial}"
        for campo in ('pc2', 'pc3', 'pc4', 'cf'):
            assert parcial[campo] is None, \
                f'{campo} debe quedar vacío sin datos, vino {parcial[campo]!r}'

        incompleto = califs.get(orden[X_EST_INCOMPLETO])
        if incompleto is not None:
            for campo in ('pc1', 'pc2', 'pc3', 'pc4', 'cf'):
                assert incompleto[campo] is None, \
                    (f'con UNA sola competencia no se puede calcular {campo}; '
                     f"vino {incompleto[campo]!r}")

    @test("X5. RP se deja vacío mientras no haya regla confirmada")
    def t():
        data, orden = _datos_asignatura()
        clave = next(k for k in data if 'atem' in k)
        fila = data[clave]['calificaciones'][orden[A['est']]]
        for campo in ('rp1', 'rp2', 'rp3', 'rp4'):
            assert fila[campo] is None, \
                f'{campo} no debe inventarse desde las competencias: {fila[campo]!r}'

    @test("X6. Sin cédula real, la casilla de cédula y la de RNE quedan vacías")
    def t():
        # La matrícula identifica al estudiante DENTRO del colegio; la cédula y
        # el RNE son documentos externos que EducaOne no guarda. Antes la
        # matrícula se copiaba a las dos casillas y el registro terminaba
        # afirmando documentos que nadie había cargado.
        from pypdf import PdfReader
        import io as _io

        _s = _SL()
        try:
            sin_doc = _s.query(_Est).filter_by(id=X_EST_INCOMPLETO).first()
            assert not (getattr(sin_doc, 'cedula', None) or ''), 'setup: debe estar sin cédula'
            matricula = sin_doc.matricula
        finally:
            _s.close()
        assert matricula, 'setup: el estudiante debe tener matrícula'

        r = client.get(f'/api/registros/secundaria/{A["curso"]}/preview-pdf',
                       headers=auth(DIR_A_TOKEN))
        assert r.status_code == 200, f'{r.status_code} {r.text[:200]}'
        assert r.content[:4] == b'%PDF'

        # Página 11 = "Datos generales del estudiante". Sus únicas casillas de
        # identificación son Cédula/Pasaporte y RNE: si la matrícula aparece
        # ahí, es que se coló en una de las dos.
        texto = PdfReader(_io.BytesIO(r.content)).pages[10].extract_text() or ''
        assert matricula not in texto, \
            (f'la matrícula {matricula!r} no debe imprimirse en la casilla de '
             f'cédula ni en la de RNE del Registro')

    # ─────────────────────────────────────────────────────────────
    # SECCIÓN Y — v2.19.7 (2): detalle por COMPETENCIA en el spread
    # ─────────────────────────────────────────────────────────────

    print(f"{BOLD}\n=== Y. v2.19.7 — DETALLE POR COMPETENCIA ==={RESET}")

    # El spread de calificaciones tiene CUATRO bloques P1/RP1..P4/RP4 —uno por
    # competencia— y además el bloque resumen. Antes solo se llenaba el resumen
    # (y con el PC del período escrito dentro del bloque de la competencia 1),
    # así que los cuatro bloques de detalle salían vacíos teniendo el dato.
    #
    # Los valores son DISTINTOS en cada competencia y período a propósito: si
    # hubiera un cruce de bloques o de columnas, el número aparecería en la
    # celda equivocada y el test lo detecta.
    Y_NOTAS = {
        1: {'p1': 65, 'p2': 60, 'p3': 65, 'p4': 60},
        2: {'p1': 67, 'p2': 78, 'p3': 68, 'p4': 89},
        3: {'p1': 56, 'p2': 50, 'p3': 71, 'p4': 95},
        4: {'p1': 66, 'p2': 63, 'p3': 56, 'p4': 94},
    }
    Y_RP = (3, 'rp2', 72)   # una sola recuperación: competencia 3, período 2

    _r = client.post('/api/estudiantes', json={
        'nombre': 'Detalle', 'apellido': 'Ye', 'sexo': 'F',
        'fecha_nacimiento': '2011-07-07', 'curso_id': A['curso'],
        'no_lista': 33, 'matricula': 'Y-DETALLE',
    }, headers=auth(DIR_A_TOKEN))
    assert _r.status_code in (200, 201), f'setup Y: crear estudiante: {_r.text}'
    Y_EST = _r.json()['id']

    _db = _SL()
    try:
        _ano_y = _db.query(_Ano).filter_by(colegio_id=A_COLEGIO_ID, activo=True).first()
        for _num, _notas in Y_NOTAS.items():
            _fila = _CS(colegio_id=A_COLEGIO_ID, estudiante_id=Y_EST,
                        asignatura_id=A['asig'], ano_escolar_id=_ano_y.id,
                        competencia_numero=_num, **_notas)
            if _num == Y_RP[0]:
                setattr(_fila, Y_RP[1], Y_RP[2])
            _db.add(_fila)
        _db.commit()
    finally:
        _db.close()

    def _celdas_del_spread():
        """Genera el borrador y devuelve, por página del spread de la
        asignatura, la lista de (x, texto) de la FILA de Y_EST."""
        from pypdf import PdfReader
        from registro_escolar import (GRADO_CONFIG, ASIGNATURAS_CICLO_1,
                                      CALIF_SPREAD, _y as _plumber_a_pdf)
        import io as _io

        _s = _SL()
        try:
            orden = [e.id for e in _s.query(_Est).filter_by(
                curso_id=A['curso'], activo=True).order_by(_Est.no_lista).all()]
        finally:
            _s.close()
        fila = orden.index(Y_EST)
        assert fila < 40, f'el estudiante de prueba quedó en la fila {fila}, fuera de la tabla'

        r = client.get(f'/api/registros/secundaria/{A["curso"]}/preview-pdf',
                       headers=auth(DIR_A_TOKEN))
        assert r.status_code == 200, f'{r.status_code} {r.text[:200]}'
        lector = PdfReader(_io.BytesIO(r.content))

        cfg = GRADO_CONFIG[1]
        a_idx = ASIGNATURAS_CICLO_1.index('Matemática')
        pg_izq = cfg['calificaciones_inicio'] - 1 + a_idx * cfg['calificaciones_pgs_por_asignatura']

        # Y de la fila, en coordenadas del PDF (igual que el generador).
        y_fila = _plumber_a_pdf(CALIF_SPREAD['centro_fila1_plumber']
                                + 8 * 0.35) - fila * CALIF_SPREAD['row_height']

        paginas = {}
        for lado, pg in (('izq', pg_izq), ('der', pg_izq + 1)):
            capturado = []

            def visitante(texto, cm, tm, fuente, tam, _c=capturado):
                limpio = (texto or '').strip()
                if limpio:
                    _c.append((round(tm[4], 1), round(tm[5], 1), limpio))

            lector.pages[pg].extract_text(visitor_text=visitante)
            paginas[lado] = [(x, t) for x, y, t in capturado
                             if abs(y - y_fila) < 3 and x > 0]
        return paginas

    def _valor_en(celdas, x_centro, tolerancia=6.0):
        """Texto dibujado centrado en x_centro, o None si la celda está vacía.

        El visitor devuelve el borde IZQUIERDO del texto; como se dibuja
        centrado, se busca el que caiga más cerca del centro de la columna.
        """
        candidatos = [(abs(x + len(t) * 2.3 - x_centro), t) for x, t in celdas]
        candidatos = [(d, t) for d, t in candidatos if d < tolerancia]
        if not candidatos:
            return None
        return min(candidatos)[1]

    Y_CELDAS = _celdas_del_spread()

    def _bloque(lado, num_comp):
        return CALIF_SPREAD_TEST[lado][num_comp], Y_CELDAS[lado]

    from registro_escolar import CALIF_SPREAD as CALIF_SPREAD_TEST

    @test("Y1. Competencia 1: P1/P2/P3/P4 en SUS celdas del bloque 1")
    def t():
        cols, celdas = _bloque('izq', 1)
        for periodo, esperado in (('p1', '65'), ('p2', '60'), ('p3', '65'), ('p4', '60')):
            visto = _valor_en(celdas, cols[periodo])
            assert visto == esperado, \
                (f'competencia 1 {periodo.upper()}: se esperaba {esperado} en x={cols[periodo]}, '
                 f'vino {visto!r}. Celdas de la fila: {sorted(celdas)}')

    @test("Y2. Competencia 2: P1/P2/P3/P4 en SUS celdas del bloque 2")
    def t():
        cols, celdas = _bloque('izq', 2)
        for periodo, esperado in (('p1', '67'), ('p2', '78'), ('p3', '68'), ('p4', '89')):
            visto = _valor_en(celdas, cols[periodo])
            assert visto == esperado, \
                f'competencia 2 {periodo.upper()}: se esperaba {esperado}, vino {visto!r}'

    @test("Y3. Competencias 3 y 4 en la página derecha, sin cruzarse")
    def t():
        cols3, celdas = _bloque('der', 3)
        for periodo, esperado in (('p1', '56'), ('p2', '50'), ('p3', '71'), ('p4', '95')):
            visto = _valor_en(celdas, cols3[periodo])
            assert visto == esperado, \
                f'competencia 3 {periodo.upper()}: se esperaba {esperado}, vino {visto!r}'
        cols4, _ = _bloque('der', 4)
        for periodo, esperado in (('p1', '66'), ('p2', '63'), ('p3', '56'), ('p4', '94')):
            visto = _valor_en(celdas, cols4[periodo])
            assert visto == esperado, \
                f'competencia 4 {periodo.upper()}: se esperaba {esperado}, vino {visto!r}'

    @test("Y4. La RP aparece SOLO en su competencia y su período")
    def t():
        num_rp, celda_rp, valor_rp = Y_RP
        cols, celdas = _bloque('der', num_rp)
        visto = _valor_en(celdas, cols[celda_rp])
        assert visto == str(valor_rp), \
            f'la recuperación debe estar en competencia {num_rp} {celda_rp.upper()}, vino {visto!r}'

        # Todas las demás casillas RP del spread quedan vacías: no se inventa.
        for lado in ('izq', 'der'):
            for comp, columnas in CALIF_SPREAD_TEST[lado].items():
                for columna, x in columnas.items():
                    if not columna.startswith('rp'):
                        continue
                    if lado == 'der' and comp == num_rp and columna == celda_rp:
                        continue
                    otro = _valor_en(Y_CELDAS[lado], x)
                    assert otro is None, \
                        (f'{lado} competencia {comp} {columna.upper()} debía quedar '
                         f'vacía y trae {otro!r}')

    @test("Y5. El resumen es el promedio POR COMPETENCIA, no por período")
    def t():
        # El template rotula estas columnas "PC1: Competencia 1" …
        # "PC4: Competencia 4": cada una es el promedio FINAL de esa
        # competencia a lo largo de P1-P4.
        #
        #   C1: 65, 60, 65, 60                 -> 62.5
        #   C2: 67, 78, 68, 89                 -> 75.5
        #   C3: 56, max(50,72)=72, 71, 95      -> 73.5   (valor_periodo con RP)
        #   C4: 66, 63, 56, 94                 -> 69.75 -> 69.8
        #
        # El otro eje —promedio de las 4 competencias en cada período— da
        # números completamente distintos (63.5 / 68.2 / 65 / 84.5). Se
        # comprueban los dos lados: que estén los correctos Y que NO estén
        # los del eje equivocado.
        POR_COMPETENCIA = {'pc1': '62.5', 'pc2': '75.5', 'pc3': '73.5', 'pc4': '69.8'}
        POR_PERIODO = {'pc1': '63.5', 'pc2': '68.2', 'pc3': '65', 'pc4': '84.5'}

        resumen = CALIF_SPREAD_TEST['resumen']
        celdas = Y_CELDAS['der']
        for clave, esperado in POR_COMPETENCIA.items():
            visto = _valor_en(celdas, resumen[clave])
            assert visto == esperado, \
                (f'{clave.upper()} debe ser el promedio de la Competencia '
                 f'{clave[-1]} ({esperado}); vino {visto!r}. '
                 f'Si vino {POR_PERIODO[clave]!r} se está usando el eje de '
                 f'PERÍODO en vez del de COMPETENCIA.')
            assert visto != POR_PERIODO[clave], \
                f'{clave.upper()} trae el promedio del período, no el de la competencia'

    @test("Y5b. CF entero redondeado, y el PC conserva su decimal")
    def t():
        resumen = CALIF_SPREAD_TEST['resumen']
        celdas = Y_CELDAS['der']

        # CF = promedio de los PC, redondeado a entero (regla del boletín).
        #   (62.5 + 75.5 + 73.5 + 69.75) / 4 = 70.3125 -> 70
        cf = _valor_en(celdas, resumen['cf'])
        assert cf == '70', f'la calificación final debe ser 70 entero, vino {cf!r}'
        assert '.' not in (cf or ''), f'la calificación final no lleva decimal: {cf!r}'

        # Un PC con decimal lo conserva…
        assert _valor_en(celdas, resumen['pc1']) == '62.5', 'el PC debe conservar su decimal'
        # …y uno redondo se escribe sin ".0" (regla de _fmt_nota).
        from registro_escolar import _fmt_nota
        assert _fmt_nota(65.0) == '65', f'65.0 debe mostrarse como 65, vino {_fmt_nota(65.0)!r}'
        assert _fmt_nota(62.5) == '62.5'
        assert _fmt_nota(69.5, ints_only=True) == '70', 'CF: 69.5 debe redondear a 70'
        assert _fmt_nota(None) == ''

    @test("Y6. Competencias ausentes: bloques vacíos, PC solo donde hay dato")
    def t():
        # X_EST_INCOMPLETO tiene UNA sola competencia: su bloque 1 se llena y
        # los otros tres quedan en blanco. Nunca se copia el mismo valor a los
        # cuatro bloques ni se inventa un promedio.
        from pypdf import PdfReader
        from registro_escolar import (GRADO_CONFIG, ASIGNATURAS_CICLO_1,
                                      CALIF_SPREAD, _y as _plumber_a_pdf)
        import io as _io
        _s = _SL()
        try:
            orden = [e.id for e in _s.query(_Est).filter_by(
                curso_id=A['curso'], activo=True).order_by(_Est.no_lista).all()]
        finally:
            _s.close()
        fila = orden.index(X_EST_INCOMPLETO)
        r = client.get(f'/api/registros/secundaria/{A["curso"]}/preview-pdf',
                       headers=auth(DIR_A_TOKEN))
        assert r.status_code == 200
        lector = PdfReader(_io.BytesIO(r.content))
        cfg = GRADO_CONFIG[1]
        a_idx = ASIGNATURAS_CICLO_1.index('Matemática')
        pg_der = cfg['calificaciones_inicio'] + a_idx * cfg['calificaciones_pgs_por_asignatura']
        y_fila = _plumber_a_pdf(CALIF_SPREAD['centro_fila1_plumber']
                                + 8 * 0.35) - fila * CALIF_SPREAD['row_height']
        capturado = []

        def visitante(texto, cm, tm, fuente, tam, _c=capturado):
            limpio = (texto or '').strip()
            if limpio:
                _c.append((round(tm[4], 1), round(tm[5], 1), limpio))

        lector.pages[pg_der].extract_text(visitor_text=visitante)
        celdas = [(x, t) for x, y, t in capturado if abs(y - y_fila) < 3 and x > 0]
        for comp in (3, 4):
            for columna, x in CALIF_SPREAD['der'][comp].items():
                visto = _valor_en(celdas, x)
                assert visto is None, \
                    (f'un estudiante con una sola competencia no puede tener nada '
                     f'en competencia {comp} {columna.upper()}; vino {visto!r}')
        # v2.19.7 (3): con el eje POR COMPETENCIA, este estudiante SÍ tiene un
        # promedio legítimo en PC1 —su competencia 1 tiene los cuatro períodos
        # cargados (90 en todos)—, y nada en PC2/PC3/PC4, que no existen. Eso
        # no es un invento: es exactamente lo que hay en la base. Lo que sigue
        # sin poder calcularse es la calificación final, que exige las cuatro.
        assert _valor_en(celdas, CALIF_SPREAD['resumen']['pc1']) == '90', \
            'la competencia 1 tiene sus cuatro períodos: su promedio es 90'
        for clave in ('pc2', 'pc3', 'pc4'):
            visto = _valor_en(celdas, CALIF_SPREAD['resumen'][clave])
            assert visto is None, \
                f'{clave.upper()} corresponde a una competencia que no existe; vino {visto!r}'
        cf = _valor_en(celdas, CALIF_SPREAD['resumen']['cf'])
        assert cf is None, \
            f'la calificación final exige las cuatro competencias; vino {cf!r}'


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
