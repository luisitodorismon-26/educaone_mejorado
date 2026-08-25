"""
EducaOne — Tests de Fase A del sistema unificado de notificaciones (v2.19).

Valida, sobre dos colegios reales creados en caliente:
  N1. Aislamiento: Colegio A jamás notifica a usuarios de Colegio B.
  N2. Destinatarios correctos por evento.
  N3. Deduplicación: el mismo evento no notifica dos veces al mismo usuario.
  N4. Privacidad: los avisos de Psicología no exponen datos del menor.
  N5. Contrato: si notify() falla, la operación académica igual queda guardada.
  N6. El autor del evento no se auto-notifica.

Uso:
    cd backend
    python tools/test_notificaciones_faseA.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
db_path = os.path.join(_BASE, 'sge.db')
for ext in ['', '-shm', '-wal']:
    if os.path.exists(db_path + ext):
        os.remove(db_path + ext)
init_creds = os.path.join(_BASE, 'INITIAL_CREDENTIALS.txt')
if os.path.exists(init_creds):
    os.remove(init_creds)

from database import engine, SessionLocal
from models import Base, Notificacion, Usuario
Base.metadata.create_all(bind=engine)

from fastapi.testclient import TestClient
from app import app

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

GREEN = "\033[92m"; RED = "\033[91m"; BOLD = "\033[1m"; CYAN = "\033[96m"; RESET = "\033[0m"


def auth(t):
    return {'Authorization': f'Bearer {t}'}


def test(nombre):
    def decorator(fn):
        global total, pasados, fallos
        total += 1
        print(f"\n{CYAN}▶ {nombre}{RESET}")
        try:
            fn()
            pasados += 1
            print(f"  {GREEN}✓ PASÓ{RESET}")
        except Exception as e:
            fallos.append((nombre, str(e)))
            print(f"  {RED}✗ FALLÓ: {e}{RESET}")
        return fn
    return decorator


def notifs_de(username):
    """Notificaciones de un usuario, leídas directo de la BD."""
    db = SessionLocal()
    try:
        u = db.query(Usuario).filter_by(username=username).first()
        if not u:
            return []
        return [
            {'titulo': n.titulo, 'mensaje': n.mensaje, 'evento_key': n.evento_key,
             'prioridad': n.prioridad, 'link': n.link}
            for n in db.query(Notificacion).filter_by(usuario_id=u.id).all()
        ]
    finally:
        db.close()


with client:
    SA = _login_prueba(
                     json={'username': 'superadmin', 'password': 'superadmin123'}).json()['token']

    client.post('/api/superadmin/colegios', json={
        'nombre': 'Colegio B', 'codigo': 'b', 'plan': 'enterprise',
        'admin_username': 'dir_b', 'admin_password': 'admin123b',
        'plan_secundaria': True, 'plan_primaria': True,
    }, headers=auth(SA))

    DIR_A = _login_prueba(
                        json={'username': 'direccion', 'password': 'admin123'}).json()['token']
    DIR_B = _login_prueba(
                        json={'username': 'dir_b', 'password': 'admin123b'}).json()['token']

    def montar(tok, sfx):
        grados = client.get('/api/grados', headers=auth(tok)).json()
        tandas = client.get('/api/tandas', headers=auth(tok)).json()
        curso = client.post('/api/cursos', json={
            'grado_id': grados[0]['id'], 'tanda_id': tandas[0]['id'], 'nombre': 'A'
        }, headers=auth(tok)).json()['id']
        asig = client.post('/api/asignaturas',
                           json={'nombre': 'Matemática', 'codigo': 'M'},
                           headers=auth(tok)).json()['id']
        prof = client.post('/api/usuarios', json={
            'username': f'profe_{sfx}', 'password': 'profesor123',
            'nombre': 'Prof', 'apellido': 'Test', 'email': f'p_{sfx}@x.com', 'role': 'profesor',
        }, headers=auth(tok)).json()['id']
        coord = client.post('/api/usuarios', json={
            'username': f'coord_{sfx}', 'password': 'coordinador123',
            'nombre': 'Coord', 'apellido': 'Test', 'email': f'c_{sfx}@x.com', 'role': 'coordinador',
        }, headers=auth(tok)).json()['id']
        psico = client.post('/api/usuarios', json={
            'username': f'psico_{sfx}', 'password': 'psicologia123',
            'nombre': 'Psico', 'apellido': 'Test', 'email': f'ps_{sfx}@x.com', 'role': 'psicologia',
        }, headers=auth(tok)).json()['id']
        est = client.post('/api/estudiantes', json={
            'nombre': 'Juanito', 'apellido': 'Secreto', 'sexo': 'M',
            'fecha_nacimiento': '2010-01-01', 'curso_id': curso,
            'no_lista': 1, 'matricula': f'M001-{sfx}',
        }, headers=auth(tok)).json()['id']
        # El profesor necesita asignación al curso para poder reportar/calificar.
        client.post('/api/asignaciones', json={
            'profesor_id': prof, 'curso_id': curso, 'asignatura_id': asig,
        }, headers=auth(tok))
        return dict(curso=curso, asig=asig, prof=prof, coord=coord, psico=psico, est=est)

    A = montar(DIR_A, 'a')
    B = montar(DIR_B, 'b')
    PROF_A = _login_prueba(
                         json={'username': 'profe_a', 'password': 'profesor123'}).json()['token']
    PSICO_A = _login_prueba(
                          json={'username': 'psico_a', 'password': 'psicologia123'}).json()['token']
    print(f"  {GREEN}✓{RESET} 2 colegios montados con profesor, coordinador y psicología")

    # ---------------------------------------------------------------- N1 + N2
    @test("N1/N2 — Reporte del Colegio A notifica a dirección y coordinación de A, y a NADIE de B")
    def _():
        r = client.post('/api/reportes', json={
            'estudiante_id': A['est'], 'tipo': 'conducta', 'gravedad': 'grave',
            'titulo': 'Incidente en el aula', 'descripcion': 'Detalle del incidente',
        }, headers=auth(PROF_A))
        assert r.status_code == 201, r.text

        assert any('reporte' in (n['evento_key'] or '') for n in notifs_de('coord_a')), \
            "coordinador de A no recibió el reporte"
        assert any('reporte' in (n['evento_key'] or '') for n in notifs_de('direccion')), \
            "dirección de A no recibió el reporte"

        for user_b in ('dir_b', 'coord_b', 'profe_b', 'psico_b'):
            assert not [n for n in notifs_de(user_b) if 'reporte' in (n['evento_key'] or '')], \
                f"FUGA MULTI-TENANT: {user_b} del Colegio B recibió un reporte del Colegio A"

    @test("N2 — Gravedad 'grave' produce prioridad urgente")
    def _():
        ns = [n for n in notifs_de('coord_a') if 'creado' in (n['evento_key'] or '')]
        assert ns, "sin notificación de reporte"
        assert ns[0]['prioridad'] == 'urgente', f"prioridad fue {ns[0]['prioridad']}"

    # --------------------------------------------------------------------- N6
    @test("N6 — El profesor que creó el reporte NO se auto-notifica")
    def _():
        assert not [n for n in notifs_de('profe_a') if 'creado' in (n['evento_key'] or '')], \
            "el autor se notificó a sí mismo"

    # --------------------------------------------------------------------- N3
    @test("N3 — Deduplicación: notify() dos veces con el mismo evento_key crea UNA sola")
    def _():
        from app import notify
        db = SessionLocal()
        try:
            u = db.query(Usuario).filter_by(username='coord_a').first()
            antes = db.query(Notificacion).filter_by(
                usuario_id=u.id, evento_key='test:dedup:1').count()
            assert antes == 0
            for _i in range(3):
                notify(db, colegio_id=u.colegio_id, usuario_ids=[u.id],
                       titulo='Prueba', evento_key='test:dedup:1')
                db.commit()
            despues = db.query(Notificacion).filter_by(
                usuario_id=u.id, evento_key='test:dedup:1').count()
            assert despues == 1, f"se crearon {despues} notificaciones, se esperaba 1"
        finally:
            db.close()

    @test("N1 — notify() con colegio_id de A jamás alcanza un usuario de B aunque se pase su ID")
    def _():
        from app import notify
        db = SessionLocal()
        try:
            coord_a = db.query(Usuario).filter_by(username='coord_a').first()
            coord_b = db.query(Usuario).filter_by(username='coord_b').first()
            antes = db.query(Notificacion).filter_by(usuario_id=coord_b.id).count()
            notify(db, colegio_id=coord_a.colegio_id,
                   usuario_ids=[coord_b.id],
                   titulo='Intento cross-tenant', evento_key='test:fuga:1')
            db.commit()
            despues = db.query(Notificacion).filter_by(usuario_id=coord_b.id).count()
            assert despues == antes, "FUGA: se notificó a un usuario de otro colegio por ID"
        finally:
            db.close()

    @test("N1 — notify() sin colegio_id no notifica a nadie")
    def _():
        from app import notify
        db = SessionLocal()
        try:
            antes = db.query(Notificacion).count()
            notify(db, colegio_id=None, roles=['direccion'],
                   titulo='Sin tenant', evento_key='test:sin_tenant:1')
            db.commit()
            assert db.query(Notificacion).count() == antes, \
                "notify() sin colegio_id creó notificaciones globales"
        finally:
            db.close()

    # --------------------------------------------------------------------- N4
    @test("N4 — Privacidad: el aviso de Psicología no menciona al estudiante")
    def _():
        r = client.post('/api/psicologia/solicitar', json={
            'estudiante_id': A['est'], 'tipo': 'emocional',
            'urgencia': 'urgente', 'motivo': 'Situación familiar delicada',
        }, headers=auth(PROF_A))
        assert r.status_code == 201, r.text

        ns = [n for n in notifs_de('psico_a') if 'psicologia' in (n['evento_key'] or '')]
        assert ns, "psicología no recibió la solicitud"
        texto = (ns[0]['titulo'] + ' ' + ns[0]['mensaje']).lower()
        for prohibido in ('juanito', 'secreto', 'familiar', 'delicada'):
            assert prohibido not in texto, \
                f"el aviso expone '{prohibido}' — llegaría a la pantalla bloqueada"

    @test("N2 — Caso tomado notifica a quien lo solicitó, no a otros")
    def _():
        casos = client.get('/api/psicologia/casos', headers=auth(PSICO_A)).json()
        assert casos, "no hay casos"
        cid = casos[0]['id']
        r = client.post(f'/api/psicologia/casos/{cid}/tomar', headers=auth(PSICO_A))
        assert r.status_code == 200, r.text
        assert any('tomado' in (n['evento_key'] or '') for n in notifs_de('profe_a')), \
            "el profesor solicitante no fue avisado"
        assert not [n for n in notifs_de('coord_a') if 'tomado' in (n['evento_key'] or '')], \
            "se avisó a alguien que no solicitó el caso"

    # --------------------------------------------------------------------- N2
    @test("N2 — Asignar profesor lo notifica a él y a nadie más")
    def _():
        asig2 = client.post('/api/asignaturas',
                            json={'nombre': 'Lengua', 'codigo': 'L'},
                            headers=auth(DIR_A)).json()['id']
        r = client.post('/api/asignaciones', json={
            'profesor_id': A['prof'], 'curso_id': A['curso'], 'asignatura_id': asig2,
        }, headers=auth(DIR_A))
        assert r.status_code in (200, 201), r.text
        # Comparar por el evento_key EXACTO de esta asignación: cada colegio crea
        # las suyas en el setup, así que buscar 'asignacion' a secas daría un
        # falso positivo de fuga.
        clave = f"asignacion:{r.json()['id']}:creada"
        assert any(n['evento_key'] == clave for n in notifs_de('profe_a')), \
            "el profesor asignado no fue notificado"
        for user_b in ('profe_b', 'dir_b', 'coord_b'):
            assert not [n for n in notifs_de(user_b) if n['evento_key'] == clave], \
                f"FUGA: {user_b} del Colegio B recibió una asignación del Colegio A"

    @test("N2 — Cambio de aula notifica al profesor del bloque")
    def _():
        h = client.post('/api/horarios', json={
            'profesor_id': A['prof'], 'curso_id': A['curso'], 'asignatura_id': A['asig'],
            'dia': 'Lunes', 'hora_inicio': '08:00', 'hora_fin': '09:00',
            'aula': '101', 'tipo_bloque': 'clase',
        }, headers=auth(DIR_A))
        assert h.status_code in (200, 201), h.text
        hid = h.json()['id']
        r = client.put(f'/api/horarios/{hid}', json={'aula': '205'}, headers=auth(DIR_A))
        assert r.status_code == 200, r.text
        ns = [n for n in notifs_de('profe_a') if 'modificado' in (n['evento_key'] or '')]
        assert ns, "el profesor no fue avisado del cambio de aula"
        assert '205' in ns[-1]['mensaje'], f"el aviso no dice el aula nueva: {ns[-1]['mensaje']}"

    # --------------------------------------------------------------------- N5
    @test("N5 — Si notify() explota, la operación académica igual queda guardada")
    def _():
        import app as appmod
        original = appmod.resolver_destinatarios
        appmod.resolver_destinatarios = lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError('fallo simulado de notificaciones'))
        try:
            r = client.post('/api/reportes', json={
                'estudiante_id': A['est'], 'tipo': 'conducta', 'gravedad': 'leve',
                'titulo': 'Reporte con notify roto', 'descripcion': 'debe guardarse igual',
            }, headers=auth(PROF_A))
            assert r.status_code == 201, \
                f"el reporte falló por culpa de las notificaciones: {r.text}"
        finally:
            appmod.resolver_destinatarios = original

        reportes = client.get('/api/reportes', headers=auth(DIR_A)).json()
        items = reportes.get('items', reportes) if isinstance(reportes, dict) else reportes
        assert any(x.get('titulo') == 'Reporte con notify roto' for x in items), \
            "el reporte no quedó persistido"

    @test("N3 — El índice único (usuario_id, evento_key) permite múltiples NULL")
    def _():
        db = SessionLocal()
        try:
            u = db.query(Usuario).filter_by(username='coord_a').first()
            for i in range(3):
                db.add(Notificacion(usuario_id=u.id, colegio_id=u.colegio_id,
                                    titulo=f'Legacy {i}', evento_key=None))
            db.commit()
        finally:
            db.close()


print(f"\n{BOLD}{'=' * 60}{RESET}")
print(f"{BOLD}  RESUMEN: {pasados}/{total} tests pasaron{RESET}")
print(f"{BOLD}{'=' * 60}{RESET}\n")
if fallos:
    for nombre, err in fallos:
        print(f"{RED}✗ {nombre}{RESET}\n    {err}")
    sys.exit(1)
print(f"{GREEN}{BOLD}🎉 FASE A VERDE{RESET}\n")
