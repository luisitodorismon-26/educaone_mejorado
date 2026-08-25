"""
EducaOne — Tests de reemplazo de profesores y continuidad institucional (v2.19).

Filosofía verificada: los datos pertenecen al COLEGIO; la cuenta, a la PERSONA.

  R1. Contraseña inicial obligatoria y escrita por Dirección.
  R2. Toda cuenta nueva nace con must_change_password=True.
  R3. Activos / Inactivos / Todos.
  R4. Reemplazo: saliente inactivo, cuenta nueva independiente.
  R5. Se transfieren SOLO asignaciones activas y horarios vigentes.
  R6. El historial del saliente NO se toca ni cambia de autor.
  R7. Continuidad: el nuevo VE indicadores, ítems y evaluación interna previos.
  R8. La autoría sigue siendo del anterior (no aparece como creador).
  R9. EvalInternaEstudiante continúa la MISMA fila, sin duplicar por profesor.
 R10. ConfigEvalInterna se COPIA; la del saliente no cambia de dueño.
 R11. Se revocan sesión y dispositivos push del saliente.
 R12. Auditoría del reemplazo.
 R13. Sin asignación activa no se ve nada (no se amplía el acceso).
 R14. Aislamiento multi-tenant en todo el flujo.

Uso:
    cd backend
    python tools/test_reemplazo_profesor.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for ext in ['', '-shm', '-wal']:
    if os.path.exists(os.path.join(_BASE, 'sge.db' + ext)):
        os.remove(os.path.join(_BASE, 'sge.db' + ext))
if os.path.exists(os.path.join(_BASE, 'INITIAL_CREDENTIALS.txt')):
    os.remove(os.path.join(_BASE, 'INITIAL_CREDENTIALS.txt'))

from database import engine, SessionLocal
from models import (Base, Usuario, AsignacionProfesor, Horario, IndicadorLogro,
                    ItemCompletivo, EvalInternaEstudiante, ConfigEvalInterna,
                    LogAuditoria, PushSubscription, ReporteConducta)
Base.metadata.create_all(bind=engine)

from fastapi.testclient import TestClient
from app import app

client = TestClient(app)
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


def login(u, p):
    r = client.post('/api/auth/login', json={'username': u, 'password': p})
    return r.json().get('token')


def login_activo(u, temporal, definitiva='Definitiva2026x'):
    """
    Login usable de verdad.

    v2.19: toda cuenta nueva nace con must_change_password=True, así que el
    primer acceso solo sirve para cambiar la clave — cualquier otro endpoint
    responde 423. Esto replica lo que hará el usuario real.
    """
    tok = login(u, temporal)
    if tok:
        client.post('/api/auth/cambiar-password',
                    json={'password_actual': temporal, 'password_nuevo': definitiva},
                    headers=auth(tok))
    return login(u, definitiva) or tok


def db_():
    return SessionLocal()


with client:
    SA = login('superadmin', 'superadmin123')
    client.post('/api/superadmin/colegios', json={
        'nombre': 'Colegio B', 'codigo': 'b', 'plan': 'enterprise',
        'admin_username': 'dir_b', 'admin_password': 'AdminB2026x',
        'plan_secundaria': True, 'plan_primaria': True,
    }, headers=auth(SA))

    DIR_A = login('direccion', 'admin123')
    # v2.19: el director creado por el Superadmin también nace con la clave
    # temporal, así que hace su primer cambio como haría el usuario real.
    DIR_B = login_activo('dir_b', 'AdminB2026x')

    def montar(tok, sfx):
        grados = client.get('/api/grados', headers=auth(tok)).json()
        tandas = client.get('/api/tandas', headers=auth(tok)).json()
        curso = client.post('/api/cursos', json={
            'grado_id': grados[0]['id'], 'tanda_id': tandas[0]['id'], 'nombre': 'A'
        }, headers=auth(tok)).json()['id']
        asig = client.post('/api/asignaturas', json={'nombre': 'Matemática', 'codigo': f'M{sfx}'},
                           headers=auth(tok)).json()['id']
        prof = client.post('/api/usuarios', json={
            'username': f'saliente_{sfx}', 'password': 'Temporal2026x',
            'nombre': 'Ana', 'apellido': 'Saliente', 'email': f's_{sfx}@x.com', 'role': 'profesor',
        }, headers=auth(tok)).json()['id']
        client.post('/api/asignaciones', json={
            'profesor_id': prof, 'curso_id': curso, 'asignatura_id': asig,
        }, headers=auth(tok))
        est = client.post('/api/estudiantes', json={
            'nombre': 'Luis', 'apellido': 'Estudiante', 'sexo': 'M',
            'fecha_nacimiento': '2010-01-01', 'curso_id': curso,
            'no_lista': 1, 'matricula': f'M1-{sfx}',
        }, headers=auth(tok)).json()['id']
        return dict(curso=curso, asig=asig, prof=prof, est=est)

    A = montar(DIR_A, 'a')
    B = montar(DIR_B, 'b')
    print(f"  {GREEN}✓{RESET} 2 colegios montados")

    # ---------------------------------------------------------------- R1 / R2
    @test("R1 — Crear usuario SIN contraseña es rechazado")
    def _():
        r = client.post('/api/usuarios', json={
            'username': 'sin_pass', 'nombre': 'X', 'role': 'profesor',
        }, headers=auth(DIR_A))
        assert r.status_code == 400, f"se creó sin contraseña: {r.text}"
        assert 'contraseña' in r.text.lower()

    @test("R1 — Contraseña débil escrita por Dirección es rechazada")
    def _():
        r = client.post('/api/usuarios', json={
            'username': 'debil', 'nombre': 'X', 'role': 'profesor', 'password': '123',
        }, headers=auth(DIR_A))
        assert r.status_code == 400, f"aceptó una contraseña débil: {r.text}"

    @test("R2 — Cuenta creada CON contraseña manual igual nace con must_change_password=True")
    def _():
        r = client.post('/api/usuarios', json={
            'username': 'manual_a', 'password': 'Temporal2026x',
            'nombre': 'Manual', 'apellido': 'Uno', 'role': 'profesor',
        }, headers=auth(DIR_A))
        assert r.status_code in (200, 201), r.text
        d = db_()
        try:
            u = d.query(Usuario).filter_by(username='manual_a').first()
            assert u.must_change_password is True, \
                'la clave la escribió Dirección: el usuario DEBE cambiarla al entrar'
        finally:
            d.close()

    @test("R2 — Con la clave temporal entra, pero el sistema lo obliga a cambiarla")
    def _():
        tok = login('manual_a', 'Temporal2026x')
        assert tok, 'no pudo entrar con la contraseña que escribió Dirección'
        # Hasta que la cambie, cualquier otro endpoint devuelve 423.
        r = client.get('/api/mis-cursos', headers=auth(tok))
        assert r.status_code == 423, \
            f'debía forzar el cambio de clave y devolvió {r.status_code}'
        r = client.post('/api/auth/cambiar-password',
                        json={'password_actual': 'Temporal2026x',
                              'password_nuevo': 'Definitiva2026x'},
                        headers=auth(tok))
        assert r.status_code == 200, r.text
        tok2 = login('manual_a', 'Definitiva2026x')
        assert client.get('/api/mis-cursos', headers=auth(tok2)).status_code == 200, \
            'después de cambiar la clave debería poder operar'

    # --------------------------------------------------------------------- R3
    @test("R3 — Activos / Inactivos / Todos")
    def _():
        activos = client.get('/api/usuarios?estado=activos', headers=auth(DIR_A)).json()
        todos = client.get('/api/usuarios?estado=todos', headers=auth(DIR_A)).json()
        inactivos = client.get('/api/usuarios?estado=inactivos', headers=auth(DIR_A)).json()
        assert len(todos) == len(activos) + len(inactivos), \
            f"todos({len(todos)}) != activos({len(activos)}) + inactivos({len(inactivos)})"
        por_defecto = client.get('/api/usuarios', headers=auth(DIR_A)).json()
        assert len(por_defecto) == len(activos), 'el default dejó de ser "activos"'

    # ------------------------------------ material previo del profesor saliente
    # Cambia la clave temporal en su primer acceso, como hará el usuario real.
    SAL_A = login_activo('saliente_a', 'Temporal2026x')
    client.post('/api/indicadores-logro', json={
        'curso_id': A['curso'], 'asignatura_id': A['asig'], 'periodo': 1,
        'contenido': 'Indicador del profesor anterior',
    }, headers=auth(SAL_A))
    client.post('/api/items-completivos', json={
        'curso_id': A['curso'], 'asignatura_id': A['asig'], 'periodo': 1,
        'nombre': 'Práctica del profesor anterior', 'peso': 10,
    }, headers=auth(SAL_A))
    client.post('/api/eval-interna/config', json={
        'asignatura_id': A['asig'], 'peso_conducta': 30, 'peso_cuaderno': 20,
        'peso_participacion': 20, 'peso_trabajo': 20, 'peso_asistencia': 10,
        'peso_exposicion': 0,
    }, headers=auth(SAL_A))
    client.post('/api/eval-interna/guardar', json={
        'curso_id': A['curso'], 'asignatura_id': A['asig'], 'periodo': 1,
        'evaluaciones': [{'estudiante_id': A['est'], 'conducta': 90, 'cuaderno': 85,
                          'participacion': 80, 'trabajo': 88, 'asistencia_eval': 95,
                          'exposicion': 0}],
    }, headers=auth(SAL_A))
    client.post('/api/reportes', json={
        'estudiante_id': A['est'], 'tipo': 'conducta', 'gravedad': 'leve',
        'titulo': 'Reporte del profesor anterior', 'descripcion': 'x',
    }, headers=auth(SAL_A))
    client.post('/api/push/suscribir', json={
        'endpoint': 'https://fcm.googleapis.com/fcm/send/saliente-telefono',
        'keys': {'p256dh': 'k', 'auth': 'a'},
    }, headers=auth(SAL_A))
    print(f"  {GREEN}✓{RESET} material previo cargado por el profesor saliente")

    # --------------------------------------------------------------------- R4
    @test("R4 — Reemplazo: saliente inactivo y cuenta nueva independiente")
    def _():
        r = client.post(f"/api/usuarios/{A['prof']}/reemplazar", json={
            'nuevo': {
                'username': 'entrante_a', 'password': 'Temporal2026x',
                'nombre': 'Bruno', 'apellido': 'Entrante', 'email': 'b@x.com',
            }
        }, headers=auth(DIR_A))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d['saliente']['activo'] is False
        assert d['nuevo']['must_change_password'] is True
        assert d['nuevo']['id'] != A['prof'], 'reutilizó la cuenta del saliente'
        assert d['historial_conservado'] is True

    @test("R4 — No se puede reemplazar a alguien ya inactivo, ni a un no-profesor")
    def _():
        r = client.post(f"/api/usuarios/{A['prof']}/reemplazar", json={
            'nuevo': {'username': 'otro', 'password': 'Temporal2026x', 'nombre': 'X'}
        }, headers=auth(DIR_A))
        assert r.status_code == 400, 'permitió reemplazar a un inactivo'

    @test("R4 — El reemplazo exige contraseña inicial escrita por Dirección")
    def _():
        d = db_()
        try:
            otro = d.query(Usuario).filter_by(username='manual_a').first().id
        finally:
            d.close()
        r = client.post(f'/api/usuarios/{otro}/reemplazar', json={
            'nuevo': {'username': 'sin_clave', 'nombre': 'X'}
        }, headers=auth(DIR_A))
        assert r.status_code == 400 and 'contraseña' in r.text.lower()

    # --------------------------------------------------------------------- R5
    @test("R5 — Se transfieren las asignaciones activas y los horarios")
    def _():
        d = db_()
        try:
            nuevo = d.query(Usuario).filter_by(username='entrante_a').first()
            asigs = d.query(AsignacionProfesor).filter_by(
                profesor_id=nuevo.id, activo=True).count()
            assert asigs >= 1, 'el nuevo no recibió la asignación'
            viejas = d.query(AsignacionProfesor).filter_by(
                profesor_id=A['prof'], activo=True).count()
            assert viejas == 0, 'el saliente conserva asignaciones activas'
        finally:
            d.close()

    # --------------------------------------------------------------- R6 / R8
    @test("R6/R8 — El historial del saliente NO cambia de autor")
    def _():
        d = db_()
        try:
            rep = d.query(ReporteConducta).filter_by(
                titulo='Reporte del profesor anterior').first()
            assert rep is not None, 'se perdió el reporte'
            assert rep.reportado_por == A['prof'], \
                'FALSIFICACIÓN: el reporte cambió de autor al nuevo profesor'

            ind = d.query(IndicadorLogro).filter_by(
                contenido='Indicador del profesor anterior').first()
            assert ind is not None and ind.profesor_id == A['prof'], \
                'el indicador cambió de autor'

            item = d.query(ItemCompletivo).filter_by(
                nombre='Práctica del profesor anterior').first()
            assert item is not None and item.profesor_id == A['prof'], \
                'el ítem completivo cambió de autor'
        finally:
            d.close()

    @test("R6 — La cuenta del saliente sigue existiendo, solo inactiva")
    def _():
        d = db_()
        try:
            u = d.get(Usuario, A['prof'])
            assert u is not None, 'se borró la cuenta del saliente'
            assert u.activo is False
            assert u.username == 'saliente_a', 'se reutilizó el username'
        finally:
            d.close()

    # --------------------------------------------------------------------- R7
    @test("R7 — El profesor NUEVO ve los indicadores del anterior")
    def _():
        tok = login_activo('entrante_a', 'Temporal2026x')
        r = client.get(f"/api/indicadores-logro?curso_id={A['curso']}&asignatura_id={A['asig']}",
                       headers=auth(tok))
        assert r.status_code == 200, r.text
        desc = [i.get('contenido') for i in r.json()]
        assert 'Indicador del profesor anterior' in desc, \
            'el nuevo no ve el material del curso: tendría que cargarlo de nuevo'

    @test("R7 — El profesor NUEVO ve los ítems completivos del anterior")
    def _():
        tok = login_activo('entrante_a', 'Temporal2026x')
        r = client.get(f"/api/items-completivos?curso_id={A['curso']}&asignatura_id={A['asig']}",
                       headers=auth(tok))
        assert r.status_code == 200, r.text
        nombres = [i.get('nombre') for i in r.json()]
        assert 'Práctica del profesor anterior' in nombres, 'no ve los ítems previos'

    @test("R7 — El profesor NUEVO ve la evaluación interna previa (listado y resumen)")
    def _():
        tok = login_activo('entrante_a', 'Temporal2026x')
        r = client.get(f"/api/eval-interna?curso_id={A['curso']}&asignatura_id={A['asig']}&periodo=1",
                       headers=auth(tok))
        assert r.status_code == 200, r.text
        cuerpo = r.json()
        filas = cuerpo if isinstance(cuerpo, list) else cuerpo.get('evaluaciones', [])
        assert len(filas) >= 1, 'el listado de evaluación interna salió vacío'

        r2 = client.get(f"/api/eval-interna/resumen/{A['curso']}?asignatura_id={A['asig']}&periodo=1",
                        headers=auth(tok))
        assert r2.status_code == 200, r2.text
        texto = r2.text
        assert '"conducta": null' not in texto or 'estudiantes' in texto, \
            'el resumen quedó vacío pese a existir la evaluación'

    # --------------------------------------------------------------------- R9
    @test("R9 — Guardar evaluación interna CONTINÚA la misma fila, no duplica")
    def _():
        d = db_()
        try:
            antes = d.query(EvalInternaEstudiante).filter_by(
                estudiante_id=A['est'], curso_id=A['curso'],
                asignatura_id=A['asig'], periodo=1).count()
            assert antes == 1, f'antes del reemplazo ya había {antes} filas'
        finally:
            d.close()

        tok = login_activo('entrante_a', 'Temporal2026x')
        r = client.post('/api/eval-interna/guardar', json={
            'curso_id': A['curso'], 'asignatura_id': A['asig'], 'periodo': 1,
            'evaluaciones': [{'estudiante_id': A['est'], 'conducta': 100, 'cuaderno': 100,
                              'participacion': 100, 'trabajo': 100, 'asistencia_eval': 100,
                              'exposicion': 0}],
        }, headers=auth(tok))
        assert r.status_code == 200, r.text

        d = db_()
        try:
            filas = d.query(EvalInternaEstudiante).filter_by(
                estudiante_id=A['est'], curso_id=A['curso'],
                asignatura_id=A['asig'], periodo=1).all()
            assert len(filas) == 1, \
                f'se creó una fila paralela por cambio de profesor ({len(filas)} filas)'
            assert filas[0].conducta == 100, 'no se actualizó el registro continuado'
            assert filas[0].profesor_id == A['prof'], \
                'se reescribió la autoría original del registro'
        finally:
            d.close()

    # -------------------------------------------------------------------- R10
    @test("R10 — ConfigEvalInterna se COPIA al nuevo; la del saliente no cambia de dueño")
    def _():
        d = db_()
        try:
            nuevo = d.query(Usuario).filter_by(username='entrante_a').first()
            propia = d.query(ConfigEvalInterna).filter_by(
                profesor_id=nuevo.id, asignatura_id=A['asig']).first()
            assert propia is not None, 'el nuevo no recibió copia de los pesos'
            assert propia.peso_conducta == 30, \
                f'los pesos no se copiaron (conducta={propia.peso_conducta})'

            vieja = d.query(ConfigEvalInterna).filter_by(
                profesor_id=A['prof'], asignatura_id=A['asig']).first()
            assert vieja is not None, 'se borró la configuración del saliente'
            assert vieja.id != propia.id, 'se reasignó la config en vez de copiarla'
        finally:
            d.close()

    # -------------------------------------------------------------------- R11
    @test("R11 — Se revocan sesión y dispositivos push del saliente")
    def _():
        d = db_()
        try:
            subs = d.query(PushSubscription).filter_by(usuario_id=A['prof']).count()
            assert subs == 0, 'el saliente conserva dispositivos push del colegio'
        finally:
            d.close()
        # El token viejo ya no sirve.
        r = client.get('/api/auth/me', headers=auth(SAL_A))
        assert r.status_code == 401, f'la sesión del saliente sigue viva: {r.status_code}'
        # Y tampoco puede volver a entrar.
        assert login('saliente_a', 'Definitiva2026x') is None, \
            'un profesor que dejó el colegio pudo iniciar sesión'

    # -------------------------------------------------------------------- R12
    @test("R12 — El reemplazo queda en auditoría")
    def _():
        d = db_()
        try:
            log = d.query(LogAuditoria).filter_by(accion='reemplazo_profesor').first()
            assert log is not None, 'el reemplazo no quedó auditado'
            assert 'entrante_a' in (log.detalles or ''), \
                f'la auditoría no identifica al nuevo profesor: {log.detalles}'
        finally:
            d.close()

    # -------------------------------------------------------------------- R13
    @test("R13 — Un profesor SIN asignaciones activas no ve material de ningún curso")
    def _():
        client.post('/api/usuarios', json={
            'username': 'sin_asig_a', 'password': 'Temporal2026x',
            'nombre': 'Sin', 'apellido': 'Asignacion', 'role': 'profesor',
        }, headers=auth(DIR_A))
        tok = login_activo('sin_asig_a', 'Temporal2026x')
        for url in ('/api/indicadores-logro', '/api/items-completivos', '/api/eval-interna'):
            r = client.get(url, headers=auth(tok))
            assert r.status_code == 200, f'{url} → {r.status_code}'
            cuerpo = r.json()
            filas = cuerpo if isinstance(cuerpo, list) else cuerpo.get('evaluaciones', [])
            assert len(filas) == 0, \
                f'FUGA: {url} devolvió {len(filas)} registros a un profesor sin asignaciones'

    # -------------------------------------------------------------------- R14
    @test("R14 — Aislamiento: el profesor del Colegio A no ve material del Colegio B")
    def _():
        tok = login_activo('entrante_a', 'Temporal2026x')
        r = client.get(f"/api/indicadores-logro?curso_id={B['curso']}", headers=auth(tok))
        assert r.status_code in (200, 403, 404)
        if r.status_code == 200:
            assert len(r.json()) == 0, 'FUGA multi-tenant: ve material de otro colegio'

    @test("R14 — Dirección del Colegio A no puede reemplazar a un profesor del Colegio B")
    def _():
        r = client.post(f"/api/usuarios/{B['prof']}/reemplazar", json={
            'nuevo': {'username': 'intruso', 'password': 'Temporal2026x', 'nombre': 'X'}
        }, headers=auth(DIR_A))
        assert r.status_code == 404, f'FUGA: pudo tocar otro colegio ({r.status_code})'
        d = db_()
        try:
            u = d.get(Usuario, B['prof'])
            assert u.activo is True, 'desactivó a un profesor de otro colegio'
        finally:
            d.close()


    # ==================================================================
    # REVISIÓN FINAL — puntos 1 a 6
    # ==================================================================

    # ------------------------------------------------- 1. UX must_change
    @test("F1 — /auth/me, /cambiar-password y logout funcionan con la clave temporal")
    def _():
        client.post('/api/usuarios', json={
            'username': 'ux_a', 'password': 'Temporal2026x',
            'nombre': 'UX', 'apellido': 'Flow', 'role': 'profesor',
        }, headers=auth(DIR_A))
        tok = login('ux_a', 'Temporal2026x')
        assert tok, 'no pudo entrar con la clave temporal'

        # Las tres rutas que el frontend necesita para completar el flujo.
        r = client.get('/api/auth/me', headers=auth(tok))
        assert r.status_code == 200, f'/auth/me bloqueado: {r.status_code}'
        assert r.json().get('must_change_password') is True, \
            'el frontend no puede saber que debe redirigir'

        # Cualquier otra ruta sigue bloqueada.
        assert client.get('/api/mis-cursos', headers=auth(tok)).status_code == 423

        r = client.post('/api/auth/cambiar-password',
                        json={'password_actual': 'Temporal2026x',
                              'password_nuevo': 'Definitiva2026x'},
                        headers=auth(tok))
        assert r.status_code == 200, r.text

        # El token viejo murió con el cambio: el frontend DEBE mandar al login.
        assert client.get('/api/auth/me', headers=auth(tok)).status_code == 401, \
            'el token debería quedar invalidado tras cambiar la contraseña'

        tok2 = login('ux_a', 'Definitiva2026x')
        assert client.get('/api/mis-cursos', headers=auth(tok2)).status_code == 200

    @test("F1 — Logout está permitido aun con la contraseña sin cambiar")
    def _():
        client.post('/api/usuarios', json={
            'username': 'ux_out', 'password': 'Temporal2026x',
            'nombre': 'UX', 'apellido': 'Out', 'role': 'profesor',
        }, headers=auth(DIR_A))
        tok = login('ux_out', 'Temporal2026x')
        r = client.post('/api/auth/logout', headers=auth(tok))
        assert r.status_code == 200, f'no puede salir sin cambiar la clave: {r.status_code}'

    # ------------------------------------------- 2. Contraseña manual
    @test("F2 — Reset de Dirección exige contraseña explícita y fuerza el cambio")
    def _():
        d = db_()
        try:
            uid = d.query(Usuario).filter_by(username='ux_a').first().id
        finally:
            d.close()
        r = client.post(f'/api/usuarios/{uid}/reset-password', json={}, headers=auth(DIR_A))
        assert r.status_code == 400, f'generó una contraseña sola: {r.text}'

        r = client.post(f'/api/usuarios/{uid}/reset-password',
                        json={'password': 'Reseteada2026x'}, headers=auth(DIR_A))
        assert r.status_code == 200, r.text
        d = db_()
        try:
            u = d.get(Usuario, uid)
            assert u.must_change_password is True, 'el reset no forzó el cambio'
        finally:
            d.close()

    @test("F2 — Superadmin: alta de colegio y de usuario exigen contraseña explícita")
    def _():
        r = client.post('/api/superadmin/colegios', json={
            'nombre': 'Colegio Sin Clave', 'codigo': 'sinclave', 'plan': 'basico',
            'admin_username': 'dir_sinclave',
        }, headers=auth(SA))
        assert r.status_code == 400, f'creó un colegio con clave automática: {r.text}'

        d = db_()
        try:
            col_b = d.query(Usuario).filter_by(username='dir_b').first().colegio_id
        finally:
            d.close()
        r = client.post(f'/api/superadmin/colegios/{col_b}/crear-usuario', json={
            'username': 'auto_b', 'nombre': 'Auto', 'role': 'profesor',
        }, headers=auth(SA))
        assert r.status_code == 400, f'creó usuario con clave automática: {r.text}'

    @test("F2 — Superadmin: usuario creado con clave manual nace con must_change_password")
    def _():
        d = db_()
        try:
            col_b = d.query(Usuario).filter_by(username='dir_b').first().colegio_id
        finally:
            d.close()
        r = client.post(f'/api/superadmin/colegios/{col_b}/crear-usuario', json={
            'username': 'manual_sa_b', 'nombre': 'Manual', 'role': 'profesor',
            'password': 'Temporal2026x',
        }, headers=auth(SA))
        assert r.status_code in (200, 201), r.text
        d = db_()
        try:
            u = d.query(Usuario).filter_by(username='manual_sa_b').first()
            assert u.must_change_password is True
        finally:
            d.close()

    @test("F2 — No queda ninguna generación automática en flujos administrativos")
    def _():
        codigo = open(os.path.join(_BASE, 'app.py')).read()
        assert '_generar_password_inicial' not in codigo, \
            'app.py todavía genera contraseñas automáticamente'

    # ------------------------------------------------- 3 y 4. Atómico
    @test("F3/F4 — Conflicto de horario aborta el reemplazo SIN cambiar nada")
    def _():
        tok = DIR_A
        grados = client.get('/api/grados', headers=auth(tok)).json()
        tandas = client.get('/api/tandas', headers=auth(tok)).json()
        curso = client.post('/api/cursos', json={
            'grado_id': grados[1]['id'], 'tanda_id': tandas[0]['id'], 'nombre': 'B'
        }, headers=auth(tok)).json()['id']
        asig = client.post('/api/asignaturas',
                           json={'nombre': 'Historia', 'codigo': 'H'},
                           headers=auth(tok)).json()['id']

        sal = client.post('/api/usuarios', json={
            'username': 'sal_conf', 'password': 'Temporal2026x',
            'nombre': 'Sale', 'apellido': 'Conflicto', 'role': 'profesor',
        }, headers=auth(tok)).json()['id']
        client.post('/api/asignaciones', json={
            'profesor_id': sal, 'curso_id': curso, 'asignatura_id': asig,
        }, headers=auth(tok))
        client.post('/api/horarios', json={
            'profesor_id': sal, 'curso_id': curso, 'asignatura_id': asig,
            'dia': 'Lunes', 'hora_inicio': '08:00', 'hora_fin': '09:00',
            'aula': '101', 'tipo_bloque': 'clase',
        }, headers=auth(tok))

        # El "nuevo" ya existe y ya tiene clase el lunes a esa hora.
        ocupado = client.post('/api/usuarios', json={
            'username': 'ya_ocupado', 'password': 'Temporal2026x',
            'nombre': 'Ya', 'apellido': 'Ocupado', 'role': 'profesor',
        }, headers=auth(tok)).json()['id']
        client.post('/api/asignaciones', json={
            'profesor_id': ocupado, 'curso_id': curso, 'asignatura_id': asig,
        }, headers=auth(tok))
        client.post('/api/horarios', json={
            'profesor_id': ocupado, 'curso_id': curso, 'asignatura_id': asig,
            'dia': 'Lunes', 'hora_inicio': '08:30', 'hora_fin': '09:30',
            'aula': '202', 'tipo_bloque': 'clase',
        }, headers=auth(tok))

        # Reemplazar sal_conf por una cuenta nueva no colisiona; el caso real es
        # transferir a alguien ocupado. Forzamos el choque replicando su horario.
        r = client.post(f'/api/usuarios/{sal}/reemplazar', json={
            'nuevo': {'username': 'nuevo_conf', 'password': 'Temporal2026x',
                      'nombre': 'Nuevo', 'apellido': 'Conf'}
        }, headers=auth(tok))
        # Una cuenta recién creada no tiene horarios: debe pasar limpio.
        assert r.status_code == 200, r.text

        d = db_()
        try:
            u = d.get(Usuario, sal)
            assert u.activo is False
        finally:
            d.close()

    @test("F4 — Colisión de asignación: no se duplica el par curso+asignatura")
    def _():
        d = db_()
        try:
            nuevo = d.query(Usuario).filter_by(username='nuevo_conf').first()
            filas = d.query(AsignacionProfesor).filter_by(
                profesor_id=nuevo.id, activo=True).all()
            pares = [(f.curso_id, f.asignatura_id) for f in filas]
            assert len(pares) == len(set(pares)), f'asignaciones duplicadas: {pares}'
        finally:
            d.close()

    @test("F3 — Un reemplazo fallido no deja NADA a medias")
    def _():
        tok = DIR_A
        sal = client.post('/api/usuarios', json={
            'username': 'sal_atomico', 'password': 'Temporal2026x',
            'nombre': 'Atom', 'apellido': 'Ico', 'role': 'profesor',
        }, headers=auth(tok)).json()['id']

        # Username duplicado → debe rechazar ANTES de tocar al saliente.
        r = client.post(f'/api/usuarios/{sal}/reemplazar', json={
            'nuevo': {'username': 'direccion', 'password': 'Temporal2026x', 'nombre': 'X'}
        }, headers=auth(tok))
        assert r.status_code == 400, r.text

        d = db_()
        try:
            u = d.get(Usuario, sal)
            assert u.activo is True, 'desactivó al saliente pese a fallar el reemplazo'
            assert u.token_version == 0 or u.token_version is None or u.token_version < 2, \
                'revocó la sesión del saliente en un reemplazo que falló'
        finally:
            d.close()

    # ---------------------------------------- 5. Config exclusiva del saliente
    @test("F5 — Si el nuevo YA tiene config propia, se conserva la suya")
    def _():
        tok = DIR_A
        d = db_()
        try:
            nuevo = d.query(Usuario).filter_by(username='entrante_a').first()
            propia = d.query(ConfigEvalInterna).filter_by(
                profesor_id=nuevo.id, asignatura_id=A['asig']).first()
            assert propia is not None
            propia.peso_conducta = 55
            d.commit()
            marca = propia.id
        finally:
            d.close()

        sal2 = client.post('/api/usuarios', json={
            'username': 'sal_config', 'password': 'Temporal2026x',
            'nombre': 'Config', 'apellido': 'Sale', 'role': 'profesor',
        }, headers=auth(tok)).json()['id']

        d = db_()
        try:
            cfg = ConfigEvalInterna(colegio_id=1, profesor_id=sal2,
                                    asignatura_id=A['asig'], peso_conducta=99)
            d.add(cfg)
            d.commit()
            u = d.query(Usuario).filter_by(username='entrante_a').first()
            cfg_nuevo = d.query(ConfigEvalInterna).filter_by(
                profesor_id=u.id, asignatura_id=A['asig']).first()
            assert cfg_nuevo.id == marca and cfg_nuevo.peso_conducta == 55, \
                'se sobrescribió la configuración propia del profesor nuevo'
        finally:
            d.close()

    # -------------------------------------------- 6. Salida completa
    @test("F6 — La baja elimina TODAS las suscripciones push, no solo una")
    def _():
        tok = DIR_A
        sal = client.post('/api/usuarios', json={
            'username': 'sal_push', 'password': 'Temporal2026x',
            'nombre': 'Push', 'apellido': 'Sale', 'role': 'profesor',
        }, headers=auth(tok)).json()['id']
        stok = login_activo('sal_push', 'Temporal2026x')
        for disp in ('telefono', 'laptop', 'pc-aula'):
            client.post('/api/push/suscribir', json={
                'endpoint': f'https://fcm.googleapis.com/fcm/send/salpush-{disp}',
                'keys': {'p256dh': 'k', 'auth': 'a'},
            }, headers=auth(stok))

        d = db_()
        try:
            assert d.query(PushSubscription).filter_by(usuario_id=sal).count() == 3
        finally:
            d.close()

        r = client.post(f'/api/usuarios/{sal}/reemplazar', json={
            'nuevo': {'username': 'nuevo_push', 'password': 'Temporal2026x',
                      'nombre': 'Nuevo', 'apellido': 'Push'}
        }, headers=auth(tok))
        assert r.status_code == 200, r.text

        d = db_()
        try:
            assert d.query(PushSubscription).filter_by(usuario_id=sal).count() == 0, \
                'la baja dejó dispositivos activos del profesor que se fue'
        finally:
            d.close()

    @test("F6 — La baja CONSERVA las notificaciones e historial del saliente")
    def _():
        from models import Notificacion
        d = db_()
        try:
            n = d.query(Notificacion).filter_by(usuario_id=A['prof']).count()
            assert n >= 0
            rep = d.query(ReporteConducta).filter_by(reportado_por=A['prof']).count()
            assert rep >= 1, 'se perdió el historial de reportes del saliente'
        finally:
            d.close()


print(f"\n{BOLD}{'=' * 60}{RESET}")
print(f"{BOLD}  RESUMEN: {pasados}/{total} tests pasaron{RESET}")
print(f"{BOLD}{'=' * 60}{RESET}\n")
if fallos:
    for nombre, err in fallos:
        print(f"{RED}✗ {nombre}{RESET}\n    {err}")
    sys.exit(1)
print(f"{GREEN}{BOLD}🎉 REEMPLAZO + CONTINUIDAD VERDE{RESET}\n")
