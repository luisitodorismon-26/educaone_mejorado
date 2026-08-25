"""
EducaOne — Tests de Fase B: PushSubscription y VAPID (v2.19).

Valida:
  P1. Suscripción de un dispositivo y consulta de clave pública.
  P2. Multi-dispositivo: un usuario con teléfono + laptop.
  P3. Re-suscripción del mismo navegador ACTUALIZA, no duplica.
  P4. PC compartida: otro usuario en el mismo navegador se queda el dispositivo.
  P5. Logout da de baja SOLO el dispositivo actual.
  P6. Aislamiento multi-tenant en las suscripciones.
  P7. Sin VAPID configurado, el sistema sigue funcionando (campana intacta).
  P8. Una suscripción muerta (410) se elimina sin afectar la notificación interna.

Uso:
    cd backend
    python tools/test_push_faseB.py
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
from models import Base, PushSubscription, Notificacion, Usuario
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


def sub_falsa(nombre):
    """Una suscripción con la forma que entrega el navegador."""
    return {
        'endpoint': f'https://fcm.googleapis.com/fcm/send/{nombre}',
        'keys': {'p256dh': f'clave-publica-{nombre}', 'auth': f'auth-{nombre}'},
    }


def subs_de(username):
    db = SessionLocal()
    try:
        u = db.query(Usuario).filter_by(username=username).first()
        if not u:
            return []
        return [s.endpoint for s in db.query(PushSubscription).filter_by(usuario_id=u.id).all()]
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

    for tok, sfx in ((DIR_A, 'a'), (DIR_B, 'b')):
        client.post('/api/usuarios', json={
            'username': f'profe_{sfx}', 'password': 'profesor123',
            'nombre': 'Prof', 'apellido': 'T', 'email': f'p_{sfx}@x.com', 'role': 'profesor',
        }, headers=auth(tok))

    PROF_A = _login_prueba(
                         json={'username': 'profe_a', 'password': 'profesor123'}).json()['token']
    PROF_B = _login_prueba(
                         json={'username': 'profe_b', 'password': 'profesor123'}).json()['token']
    print(f"  {GREEN}✓{RESET} 2 colegios con profesores listos")

    # ---------------------------------------------------------------------- P1
    @test("P1 — /api/push/clave-publica responde y declara si el push está disponible")
    def _():
        r = client.get('/api/push/clave-publica', headers=auth(PROF_A))
        assert r.status_code == 200, r.text
        d = r.json()
        assert 'disponible' in d and 'clave_publica' in d
        # Sin VAPID en el entorno de test, debe declararse NO disponible.
        assert d['disponible'] is False, "sin VAPID debería reportar disponible=False"

    @test("P1 — Suscribir un dispositivo guarda la fila")
    def _():
        r = client.post('/api/push/suscribir', json=sub_falsa('telefono-a'),
                        headers=auth(PROF_A))
        assert r.status_code == 200, r.text
        assert any('telefono-a' in e for e in subs_de('profe_a')), "no se guardó la suscripción"

    @test("P1 — Suscripción incompleta se rechaza con 400")
    def _():
        r = client.post('/api/push/suscribir',
                        json={'endpoint': 'https://x/y', 'keys': {}},
                        headers=auth(PROF_A))
        assert r.status_code == 400, f"se aceptó una suscripción sin claves: {r.text}"

    # ---------------------------------------------------------------------- P2
    @test("P2 — Multi-dispositivo: el mismo usuario suma teléfono + laptop")
    def _():
        client.post('/api/push/suscribir', json=sub_falsa('laptop-a'), headers=auth(PROF_A))
        eps = subs_de('profe_a')
        assert len(eps) == 2, f"se esperaban 2 dispositivos, hay {len(eps)}"

    # ---------------------------------------------------------------------- P3
    @test("P3 — Re-suscribir el mismo navegador ACTUALIZA, no duplica")
    def _():
        antes = len(subs_de('profe_a'))
        for _i in range(3):
            client.post('/api/push/suscribir', json=sub_falsa('telefono-a'),
                        headers=auth(PROF_A))
        despues = len(subs_de('profe_a'))
        assert despues == antes, f"se duplicó la suscripción: {antes} → {despues}"

    # ---------------------------------------------------------------------- P4
    @test("P4 — PC compartida: si otro usuario se suscribe en el mismo navegador, el dispositivo cambia de dueño")
    def _():
        compartida = sub_falsa('pc-aula')
        client.post('/api/push/suscribir', json=compartida, headers=auth(PROF_A))
        assert any('pc-aula' in e for e in subs_de('profe_a'))

        # Ahora entra dirección en la misma máquina.
        client.post('/api/push/suscribir', json=compartida, headers=auth(DIR_A))
        assert not any('pc-aula' in e for e in subs_de('profe_a')), \
            "el profesor seguiría recibiendo pushes en una PC que ya no usa"
        assert any('pc-aula' in e for e in subs_de('direccion')), \
            "dirección no quedó registrada en la PC compartida"

        db = SessionLocal()
        try:
            n = db.query(PushSubscription).filter(
                PushSubscription.endpoint.like('%pc-aula%')).count()
            assert n == 1, f"el endpoint quedó duplicado ({n} filas)"
        finally:
            db.close()

    # ---------------------------------------------------------------------- P5
    @test("P5 — Logout da de baja SOLO el dispositivo actual, no el teléfono personal")
    def _():
        antes = subs_de('profe_a')
        assert len(antes) >= 2, "hacen falta 2 dispositivos para esta prueba"
        objetivo = [e for e in antes if 'laptop-a' in e][0]

        r = client.post('/api/auth/logout',
                        json={'push_endpoint': objetivo}, headers=auth(PROF_A))
        assert r.status_code == 200, r.text

        despues = subs_de('profe_a')
        assert objetivo not in despues, "no se dio de baja la laptop"
        assert any('telefono-a' in e for e in despues), \
            "se borró el teléfono personal: el logout fue demasiado agresivo"

    @test("P5 — Logout sin push_endpoint no borra ningún dispositivo")
    def _():
        tok = _login_prueba(
                          json={'username': 'profe_a', 'password': 'profesor123'}).json()['token']
        antes = len(subs_de('profe_a'))
        r = client.post('/api/auth/logout', headers=auth(tok))
        assert r.status_code == 200, r.text
        assert len(subs_de('profe_a')) == antes, \
            "un logout normal borró dispositivos que no debía"

    @test("P5 — Desuscribir requiere endpoint y solo afecta al usuario dueño")
    def _():
        tok_a = _login_prueba(
                            json={'username': 'profe_a', 'password': 'profesor123'}).json()['token']
        r = client.post('/api/push/desuscribir', json={}, headers=auth(tok_a))
        assert r.status_code == 400, "aceptó desuscribir sin endpoint"

        client.post('/api/push/suscribir', json=sub_falsa('telefono-b'), headers=auth(PROF_B))
        ep_b = [e for e in subs_de('profe_b') if 'telefono-b' in e][0]
        r = client.post('/api/push/desuscribir', json={'endpoint': ep_b}, headers=auth(tok_a))
        assert r.json().get('eliminadas') == 0, \
            "FUGA: un usuario dio de baja el dispositivo de otro"
        assert any('telefono-b' in e for e in subs_de('profe_b')), \
            "el dispositivo ajeno fue eliminado"

    # ---------------------------------------------------------------------- P6
    @test("P6 — Las suscripciones guardan el colegio_id correcto")
    def _():
        db = SessionLocal()
        try:
            pa = db.query(Usuario).filter_by(username='profe_a').first()
            pb = db.query(Usuario).filter_by(username='profe_b').first()
            for s in db.query(PushSubscription).filter_by(usuario_id=pa.id).all():
                assert s.colegio_id == pa.colegio_id, "colegio_id incorrecto en Colegio A"
            for s in db.query(PushSubscription).filter_by(usuario_id=pb.id).all():
                assert s.colegio_id == pb.colegio_id, "colegio_id incorrecto en Colegio B"
                assert s.colegio_id != pa.colegio_id, "FUGA: mismo colegio para ambos"
        finally:
            db.close()

    # ---------------------------------------------------------------------- P7
    @test("P7 — Sin VAPID, despachar_push no hace nada y no rompe")
    def _():
        from app import despachar_push
        from push_service import push_configurado
        assert push_configurado() is False, "el test asume entorno sin VAPID"

        class _BT:
            def __init__(self):
                self.tareas = []

            def add_task(self, fn, *a, **k):
                self.tareas.append(fn)

        bt = _BT()
        db = SessionLocal()
        try:
            n = db.query(Notificacion).first()
            despachar_push(bt, [n] if n else [])
        finally:
            db.close()
        assert bt.tareas == [], "programó un envío push sin VAPID configurado"

    @test("P7 — despachar_push con basura no lanza excepción")
    def _():
        from app import despachar_push
        despachar_push(None, None)
        despachar_push(None, ['no soy una notificación'])

    # ---------------------------------------------------------------------- P8
    @test("P8 — Una suscripción muerta (410) se elimina y la notificación interna sobrevive")
    def _():
        import push_service

        db = SessionLocal()
        try:
            u = db.query(Usuario).filter_by(username='profe_b').first()
            n = Notificacion(usuario_id=u.id, colegio_id=u.colegio_id,
                             titulo='Prueba push', mensaje='x',
                             evento_key='test:push:410')
            db.add(n)
            db.commit()
            notif_id = n.id
            subs_antes = db.query(PushSubscription).filter_by(usuario_id=u.id).count()
            assert subs_antes >= 1, "hace falta al menos una suscripción"
        finally:
            db.close()

        class _Resp:
            status_code = 410

        class _Muerta(Exception):
            response = _Resp()

        orig_webpush = push_service.webpush
        orig_exc = push_service.WebPushException
        orig_pub, orig_priv = push_service.VAPID_PUBLIC_KEY, push_service.VAPID_PRIVATE_KEY
        orig_disp = push_service._PYWEBPUSH_DISPONIBLE

        def _falla(*a, **k):
            raise _Muerta()

        push_service.webpush = _falla
        push_service.WebPushException = _Muerta
        push_service.VAPID_PUBLIC_KEY = 'clave-publica-test'
        push_service.VAPID_PRIVATE_KEY = 'clave-privada-test'
        push_service._PYWEBPUSH_DISPONIBLE = True
        try:
            push_service.enviar_push_para_notificaciones([notif_id])
        finally:
            push_service.webpush = orig_webpush
            push_service.WebPushException = orig_exc
            push_service.VAPID_PUBLIC_KEY = orig_pub
            push_service.VAPID_PRIVATE_KEY = orig_priv
            push_service._PYWEBPUSH_DISPONIBLE = orig_disp

        db = SessionLocal()
        try:
            u = db.query(Usuario).filter_by(username='profe_b').first()
            assert db.query(PushSubscription).filter_by(usuario_id=u.id).count() == 0, \
                "la suscripción muerta no fue eliminada"
            n = db.get(Notificacion, notif_id)
            assert n is not None, "se perdió la notificación interna por un push fallido"
            assert n.push_enviado_at is None, \
                "marcó push_enviado_at pese a que ninguna entrega fue aceptada"
        finally:
            db.close()


print(f"\n{BOLD}{'=' * 60}{RESET}")
print(f"{BOLD}  RESUMEN: {pasados}/{total} tests pasaron{RESET}")
print(f"{BOLD}{'=' * 60}{RESET}\n")
if fallos:
    for nombre, err in fallos:
        print(f"{RED}✗ {nombre}{RESET}\n    {err}")
    sys.exit(1)
print(f"{GREEN}{BOLD}🎉 FASE B VERDE{RESET}\n")
