"""
EducaOne — Tests de Fase C: circuito completo de Web Push (v2.19).

El navegador no existe en el entorno de pruebas, así que se simula el contrato
EXACTO que cumple `frontend/src/services/push.ts`:

    GET  /api/push/clave-publica     → ¿hay VAPID? ¿cuál es la clave?
    pushManager.getSubscription()    → ¿ya está suscrito este navegador?
    pushManager.subscribe(...)       → crear suscripción
    POST /api/push/suscribir         → mandarla al backend autenticado
    POST /api/auth/logout {endpoint} → baja SOLO de este dispositivo
    subscription.unsubscribe()       → soltarla en el navegador

Además se valida el payload que consume `sw.js` y el link que abre
`notificationclick`.

Cubre los 8 escenarios pedidos:
  C1. Activar notificaciones.
  C2. Reactivar sin crear duplicados.
  C3. Notificación visible (payload correcto para showNotification).
  C4. Click abre el link correcto.
  C5. Logout elimina SOLO este dispositivo.
  C6. Login de otro usuario en la misma PC.
  C7. Permisos denegados: EducaOne sigue funcionando.
  C8. Push fallido: la campana no se ve afectada.

Uso:
    cd backend
    python tools/test_push_faseC.py
"""
import sys
import os
import json

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


# ---------------------------------------------------------------------------
# Simulación del navegador
# ---------------------------------------------------------------------------
class NavegadorFalso:
    """
    Reproduce PushManager + Notification.permission.

    Cada instancia es un dispositivo distinto (teléfono, laptop, PC del aula).
    El `endpoint` lo asigna el navegador y es estable por dispositivo — es
    justamente lo que hace que reactivar no duplique.
    """

    def __init__(self, nombre, permiso='default'):
        self.nombre = nombre
        self.permiso = permiso          # default | granted | denied
        self._suscripcion = None

    def request_permission(self):
        if self.permiso == 'default':
            self.permiso = 'granted'
        return self.permiso

    def get_subscription(self):
        return self._suscripcion

    def subscribe(self, user_visible_only, application_server_key):
        # Chrome rechaza la suscripción sin userVisibleOnly: true.
        assert user_visible_only is True, 'userVisibleOnly debe ser True'
        assert application_server_key, 'falta la VAPID public key'
        if self._suscripcion is None:
            self._suscripcion = {
                'endpoint': f'https://fcm.googleapis.com/fcm/send/{self.nombre}',
                'keys': {'p256dh': f'p256dh-{self.nombre}', 'auth': f'auth-{self.nombre}'},
            }
        return self._suscripcion

    def unsubscribe(self):
        self._suscripcion = None
        return True


def activar_push(navegador, token):
    """Réplica de activarPush() de frontend/src/services/push.ts."""
    r = client.get('/api/push/clave-publica', headers=auth(token))
    if r.status_code != 200:
        return {'ok': False, 'estado': 'no-disponible'}
    data = r.json()
    if not data.get('disponible') or not data.get('clave_publica'):
        return {'ok': False, 'estado': 'no-disponible'}

    if navegador.permiso == 'denied':
        return {'ok': False, 'estado': 'denegado'}
    if navegador.request_permission() != 'granted':
        return {'ok': False, 'estado': 'denegado'}

    # Reutilizar la existente antes de crear otra: esto es lo que evita duplicar.
    sub = navegador.get_subscription()
    if not sub:
        sub = navegador.subscribe(user_visible_only=True,
                                  application_server_key=data['clave_publica'])

    r = client.post('/api/push/suscribir', json=sub, headers=auth(token))
    if r.status_code != 200:
        return {'ok': False, 'estado': 'no-activadas'}
    return {'ok': True, 'estado': 'activadas'}


def logout_con_push(navegador, token):
    """Réplica del logout de AuthContext.tsx."""
    sub = navegador.get_subscription()
    cuerpo = {'push_endpoint': sub['endpoint']} if sub else {}
    r = client.post('/api/auth/logout', json=cuerpo, headers=auth(token))
    if sub:
        navegador.unsubscribe()
    return r


def subs_de(username):
    db = SessionLocal()
    try:
        u = db.query(Usuario).filter_by(username=username).first()
        if not u:
            return []
        return [s.endpoint for s in db.query(PushSubscription).filter_by(usuario_id=u.id).all()]
    finally:
        db.close()


def login(username, password):
    return _login_prueba(
                       json={'username': username, 'password': password}).json()['token']


# ---------------------------------------------------------------------------
import push_service

_ORIG = (push_service.VAPID_PUBLIC_KEY, push_service.VAPID_PRIVATE_KEY,
         push_service._PYWEBPUSH_DISPONIBLE)


def con_vapid(activo=True):
    """Simular una instalación CON las claves VAPID cargadas en Render."""
    if activo:
        push_service.VAPID_PUBLIC_KEY = 'BEl62iUYgUivxIkv69yViEuiBIa-Ib9-SkvMeAtA3LFgDzkrxZJjSgSnfckjBJlA'
        push_service.VAPID_PRIVATE_KEY = 'clave-privada-de-prueba'
        push_service._PYWEBPUSH_DISPONIBLE = True
    else:
        (push_service.VAPID_PUBLIC_KEY, push_service.VAPID_PRIVATE_KEY,
         push_service._PYWEBPUSH_DISPONIBLE) = _ORIG


with client:
    SA = login('superadmin', 'superadmin123')
    client.post('/api/superadmin/colegios', json={
        'nombre': 'Colegio B', 'codigo': 'b', 'plan': 'enterprise',
        'admin_username': 'dir_b', 'admin_password': 'admin123b',
        'plan_secundaria': True, 'plan_primaria': True,
    }, headers=auth(SA))

    DIR_A = login('direccion', 'admin123')
    for tok, sfx in ((DIR_A, 'a'),):
        for rol, user in (('profesor', 'profe'), ('coordinador', 'coord')):
            client.post('/api/usuarios', json={
                'username': f'{user}_{sfx}', 'password': f'{rol}123',
                'nombre': 'N', 'apellido': 'T', 'email': f'{user}_{sfx}@x.com', 'role': rol,
            }, headers=auth(tok))

    PROF_A = login('profe_a', 'profesor123')
    print(f"  {GREEN}✓{RESET} entorno listo")

    con_vapid(True)

    # ---------------------------------------------------------------------- C1
    @test("C1 — Activar notificaciones: pide permiso, suscribe y registra en el backend")
    def _():
        telefono = NavegadorFalso('telefono-profe')
        assert telefono.permiso == 'default', 'el permiso no debe pedirse antes del click'

        r = activar_push(telefono, PROF_A)
        assert r['ok'] and r['estado'] == 'activadas', f"no se activó: {r}"
        assert telefono.permiso == 'granted', 'el permiso se pide dentro del click'
        assert any('telefono-profe' in e for e in subs_de('profe_a')), \
            'la suscripción no llegó al backend'

    @test("C1 — Sin VAPID en el servidor, el botón no ofrece activar")
    def _():
        con_vapid(False)
        try:
            r = client.get('/api/push/clave-publica', headers=auth(PROF_A))
            assert r.json()['disponible'] is False
            nav = NavegadorFalso('sin-vapid')
            res = activar_push(nav, PROF_A)
            assert res['estado'] == 'no-disponible', f"debió reportar no-disponible: {res}"
            assert nav.permiso == 'default', 'pidió permiso pese a no haber VAPID'
        finally:
            con_vapid(True)

    # ---------------------------------------------------------------------- C2
    @test("C2 — Reactivar en el mismo navegador NO crea duplicados")
    def _():
        telefono = NavegadorFalso('telefono-profe', permiso='granted')
        telefono.subscribe(True, 'k')  # ya estaba suscrito de C1
        antes = len(subs_de('profe_a'))
        for _i in range(4):
            r = activar_push(telefono, PROF_A)
            assert r['ok'], r
        despues = len(subs_de('profe_a'))
        assert despues == antes, f"se duplicó: {antes} → {despues}"

    # ---------------------------------------------------------------------- C3
    @test("C3 — El payload que recibe sw.js trae título, mensaje, link y prioridad")
    def _():
        db = SessionLocal()
        try:
            u = db.query(Usuario).filter_by(username='profe_a').first()
            n = Notificacion(usuario_id=u.id, colegio_id=u.colegio_id,
                             titulo='🔴 URGENTE: nuevo reporte de conducta',
                             mensaje='Incidente en el aula', link='/reportes',
                             prioridad='urgente', evento_key='test:c3:payload')
            db.add(n)
            db.commit()
            payload = json.loads(push_service._payload(n))
        finally:
            db.close()

        for campo in ('titulo', 'mensaje', 'link', 'prioridad', 'notificacion_id'):
            assert campo in payload, f'falta {campo} en el payload'
        assert payload['titulo'], 'showNotification() necesita un título no vacío'
        assert payload['prioridad'] == 'urgente'
        # sw.js usa esto para requireInteraction: la urgente no se descarta sola.
        assert payload['prioridad'] in ('info', 'normal', 'importante', 'urgente')

    @test("C3 — Un push de Psicología no expone datos del menor en el payload")
    def _():
        db = SessionLocal()
        try:
            u = db.query(Usuario).filter_by(username='profe_a').first()
            n = db.query(Notificacion).filter(
                Notificacion.usuario_id == u.id,
                Notificacion.tipo == 'psicologia').first()
            if n is None:
                n = Notificacion(usuario_id=u.id, colegio_id=u.colegio_id,
                                 titulo='🧠 Nueva solicitud de Psicología',
                                 mensaje='Hay una solicitud de atención disponible en EducaOne.',
                                 tipo='psicologia', link='/psicologia',
                                 evento_key='test:c3:psico')
                db.add(n)
                db.commit()
            payload = json.loads(push_service._payload(n))
        finally:
            db.close()
        texto = (payload['titulo'] + ' ' + payload['mensaje']).lower()
        for prohibido in ('juanito', 'diagnóstico', 'diagnostico', 'motivo:'):
            assert prohibido not in texto, f"el payload expone '{prohibido}'"

    # ---------------------------------------------------------------------- C4
    @test("C4 — El link del payload es el que notificationclick debe abrir")
    def _():
        db = SessionLocal()
        try:
            u = db.query(Usuario).filter_by(username='profe_a').first()
            n = Notificacion(usuario_id=u.id, colegio_id=u.colegio_id,
                             titulo='Solicitud aprobada', mensaje='x',
                             link='/calificaciones', evento_key='test:c4:link')
            db.add(n)
            db.commit()
            payload = json.loads(push_service._payload(n))
        finally:
            db.close()
        assert payload['link'] == '/calificaciones', \
            f"el click abriría {payload['link']} en vez de /calificaciones"

    @test("C4 — Una notificación sin link cae en '/' y no rompe el click")
    def _():
        db = SessionLocal()
        try:
            u = db.query(Usuario).filter_by(username='profe_a').first()
            n = Notificacion(usuario_id=u.id, colegio_id=u.colegio_id,
                             titulo='Sin link', mensaje='', link='',
                             evento_key='test:c4:sinlink')
            db.add(n)
            db.commit()
            payload = json.loads(push_service._payload(n))
        finally:
            db.close()
        assert payload['link'] == '/', "sw.js abriría una URL vacía"

    # ---------------------------------------------------------------------- C5
    @test("C5 — Logout da de baja SOLO este dispositivo")
    def _():
        tok = login('profe_a', 'profesor123')
        laptop = NavegadorFalso('laptop-profe')
        activar_push(laptop, tok)
        assert len(subs_de('profe_a')) >= 2, 'hacen falta 2 dispositivos'

        tok = login('profe_a', 'profesor123')
        logout_con_push(laptop, tok)

        eps = subs_de('profe_a')
        assert not any('laptop-profe' in e for e in eps), 'la laptop no se dio de baja'
        assert any('telefono-profe' in e for e in eps), \
            'se borró el teléfono personal: el logout fue demasiado agresivo'
        assert laptop.get_subscription() is None, \
            'el navegador quedó suscrito a un servidor que ya lo dio de baja'

    # ---------------------------------------------------------------------- C6
    @test("C6 — Otro usuario en la misma PC se queda el dispositivo, sin duplicar")
    def _():
        pc_aula = NavegadorFalso('pc-aula')

        tok_prof = login('profe_a', 'profesor123')
        activar_push(pc_aula, tok_prof)
        assert any('pc-aula' in e for e in subs_de('profe_a'))

        # El profesor cierra sesión en la PC del aula.
        logout_con_push(pc_aula, login('profe_a', 'profesor123'))
        assert not any('pc-aula' in e for e in subs_de('profe_a'))

        # Entra el coordinador en la misma máquina y activa.
        tok_coord = login('coord_a', 'coordinador123')
        pc_aula2 = NavegadorFalso('pc-aula')
        activar_push(pc_aula2, tok_coord)

        assert any('pc-aula' in e for e in subs_de('coord_a')), \
            'el coordinador no quedó registrado'
        assert not any('pc-aula' in e for e in subs_de('profe_a')), \
            'FUGA: el profesor seguiría recibiendo pushes en una PC que ya no usa'
        assert any('telefono-profe' in e for e in subs_de('profe_a')), \
            'el teléfono del profesor debe seguir intacto'

        db = SessionLocal()
        try:
            n = db.query(PushSubscription).filter(
                PushSubscription.endpoint.like('%pc-aula%')).count()
            assert n == 1, f'el endpoint quedó duplicado ({n} filas)'
        finally:
            db.close()

    # ---------------------------------------------------------------------- C7
    @test("C7 — Permiso denegado: no se suscribe y la campana sigue funcionando")
    def _():
        tok = login('coord_a', 'coordinador123')
        bloqueado = NavegadorFalso('navegador-bloqueado', permiso='denied')
        r = activar_push(bloqueado, tok)
        assert r['estado'] == 'denegado', f"debió reportar denegado: {r}"
        assert not any('navegador-bloqueado' in e for e in subs_de('coord_a'))

        # Lo importante: la campana interna sigue respondiendo igual.
        r = client.get('/api/notificaciones?limit=10', headers=auth(tok))
        assert r.status_code == 200, f'la campana se rompió: {r.text}'
        assert 'notificaciones' in r.json()

    @test("C7 — Un usuario sin ningún dispositivo recibe igual sus notificaciones internas")
    def _():
        tok = login('coord_a', 'coordinador123')
        r = client.get('/api/notificaciones', headers=auth(tok))
        assert r.status_code == 200
        assert 'no_leidas' in r.json(), 'la campana debe seguir contando sin push'

    # ---------------------------------------------------------------------- C8
    @test("C8 — Push fallido: la notificación interna queda intacta en la campana")
    def _():
        tok = login('profe_a', 'profesor123')

        db = SessionLocal()
        try:
            u = db.query(Usuario).filter_by(username='profe_a').first()
            n = Notificacion(usuario_id=u.id, colegio_id=u.colegio_id,
                             titulo='Aviso con push roto', mensaje='debe verse igual',
                             link='/reportes', evento_key='test:c8:pushroto')
            db.add(n)
            db.commit()
            notif_id = n.id
        finally:
            db.close()

        def _explota(*a, **k):
            raise RuntimeError('el proveedor de push está caído')

        orig = push_service.webpush
        push_service.webpush = _explota
        try:
            push_service.enviar_push_para_notificaciones([notif_id])
        finally:
            push_service.webpush = orig

        r = client.get('/api/notificaciones?limit=50', headers=auth(tok))
        assert r.status_code == 200
        titulos = [x['titulo'] for x in r.json()['notificaciones']]
        assert 'Aviso con push roto' in titulos, \
            'la notificación desapareció de la campana por un push fallido'

        db = SessionLocal()
        try:
            n = db.get(Notificacion, notif_id)
            assert n.push_enviado_at is None, \
                'marcó push_enviado_at pese a que ninguna entrega fue aceptada'
        finally:
            db.close()

    @test("C8 — enviar_push_para_notificaciones con IDs inexistentes no lanza")
    def _():
        push_service.enviar_push_para_notificaciones([999999, 999998])
        push_service.enviar_push_para_notificaciones([])

    con_vapid(False)


print(f"\n{BOLD}{'=' * 60}{RESET}")
print(f"{BOLD}  RESUMEN: {pasados}/{total} tests pasaron{RESET}")
print(f"{BOLD}{'=' * 60}{RESET}\n")
if fallos:
    for nombre, err in fallos:
        print(f"{RED}✗ {nombre}{RESET}\n    {err}")
    sys.exit(1)
print(f"{GREEN}{BOLD}🎉 FASE C VERDE{RESET}\n")
