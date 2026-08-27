"""
EducaOne — v2.19.2: divisiones en Coordinación y Psicología.

Regla verificada: nivel_asignado vacío = AMBAS divisiones (no "sin división").
Si es primaria/secundaria, ese lente es FIJO y la cabecera X-Nivel no puede
quitarlo — el backend es la autoridad, no el ocultamiento de botones.

Uso:
    cd backend
    python tools/test_division_psicologia_v2192.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for ext in ['', '-shm', '-wal']:
    if os.path.exists(os.path.join(_BASE, 'sge.db' + ext)):
        os.remove(os.path.join(_BASE, 'sge.db' + ext))
if os.path.exists(os.path.join(_BASE, 'INITIAL_CREDENTIALS.txt')):
    os.remove(os.path.join(_BASE, 'INITIAL_CREDENTIALS.txt'))

from database import engine, SessionLocal
from models import Base, Usuario, CasoPsicologia, Notificacion, Estudiante
Base.metadata.create_all(bind=engine)
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)
fallos, pasados, total = [], 0, 0
G, R, B, C, X = "\033[92m", "\033[91m", "\033[1m", "\033[96m", "\033[0m"

def auth(t, nivel=None):
    h = {'Authorization': f'Bearer {t}'}
    if nivel:
        h['X-Nivel'] = nivel
    return h

def _limpiar(u):
    d = SessionLocal()
    try:
        x = d.query(Usuario).filter_by(username=u).first()
        if x and x.must_change_password:
            x.must_change_password = False
            d.commit()
    finally:
        d.close()

def login(u, p):
    _limpiar(u)
    return client.post('/api/auth/login', json={'username': u, 'password': p}).json().get('token')

def test(nombre):
    def deco(fn):
        global total, pasados
        total += 1
        print(f"\n{C}▶ {nombre}{X}")
        try:
            fn(); pasados += 1; print(f"  {G}✓ PASÓ{X}")
        except Exception as e:
            fallos.append((nombre, str(e))); print(f"  {R}✗ FALLÓ: {e}{X}")
        return fn
    return deco

def set_nivel(username, nivel):
    d = SessionLocal()
    try:
        u = d.query(Usuario).filter_by(username=username).first()
        u.nivel_asignado = nivel
        d.commit()
    finally:
        d.close()

with client:
    SA = login('superadmin', 'superadmin123')
    client.post('/api/superadmin/colegios', json={
        'nombre': 'Colegio B', 'codigo': 'b', 'plan': 'enterprise',
        'admin_username': 'dir_b', 'admin_password': 'AdminB2026x',
        'plan_secundaria': True, 'plan_primaria': True,
    }, headers=auth(SA))
    DIR_A = login('direccion', 'admin123')
    DIR_B = login('dir_b', 'AdminB2026x')

    def montar(tok, sfx):
        # El colegio de prueba nace solo con grados de secundaria. Se agrega uno
        # de primaria directo en la base: crear grados no es parte de lo que se
        # está probando y no existe endpoint para ello.
        _d = SessionLocal()
        try:
            from models import Grado, Usuario as _U
            _cid = _d.query(_U).filter_by(username=('direccion' if sfx == 'a' else 'dir_b')).first().colegio_id
            if not _d.query(Grado).filter_by(colegio_id=_cid, nivel='primaria').first():
                _d.add(Grado(colegio_id=_cid, nombre=f'1ro Primaria {sfx}',
                             nivel='primaria', ciclo=1, orden=1))
                _d.commit()
        finally:
            _d.close()
        grados = client.get('/api/grados', headers=auth(tok)).json()
        tandas = client.get('/api/tandas', headers=auth(tok)).json()
        gp = next(g for g in grados if g['nivel'] == 'primaria')
        gs = next(g for g in grados if g['nivel'] == 'secundaria')
        cp = client.post('/api/cursos', json={'grado_id': gp['id'], 'tanda_id': tandas[0]['id'], 'nombre': 'A'}, headers=auth(tok)).json()['id']
        cs = client.post('/api/cursos', json={'grado_id': gs['id'], 'tanda_id': tandas[0]['id'], 'nombre': 'A'}, headers=auth(tok)).json()['id']
        ep = client.post('/api/estudiantes', json={'nombre': 'EstPrim', 'apellido': sfx.upper(), 'sexo': 'M',
            'fecha_nacimiento': '2015-01-01', 'curso_id': cp, 'no_lista': 1, 'matricula': f'P-{sfx}'}, headers=auth(tok)).json()['id']
        es = client.post('/api/estudiantes', json={'nombre': 'EstSec', 'apellido': sfx.upper(), 'sexo': 'F',
            'fecha_nacimiento': '2010-01-01', 'curso_id': cs, 'no_lista': 1, 'matricula': f'S-{sfx}'}, headers=auth(tok)).json()['id']
        for rol, user in (('psicologia', 'psi'), ('coordinador', 'coord')):
            client.post('/api/usuarios', json={'username': f'{user}_{sfx}', 'password': 'Temporal2026x',
                'nombre': rol.capitalize(), 'apellido': sfx.upper(), 'email': f'{user}_{sfx}@x.com', 'role': rol}, headers=auth(tok))
        # Dos casos: uno de primaria, uno de secundaria
        for eid in (ep, es):
            client.post('/api/psicologia/solicitar', json={'estudiante_id': eid, 'tipo': 'emocional',
                'urgencia': 'normal', 'motivo': 'Motivo confidencial'}, headers=auth(tok))
        return dict(cp=cp, cs=cs, ep=ep, es=es)

    A = montar(DIR_A, 'a')
    B_ = montar(DIR_B, 'b')
    print(f"  {G}✓{X} 2 colegios con primaria, secundaria y 2 casos cada uno")

    def casos_de(tok, nivel=None):
        r = client.get('/api/psicologia/casos', headers=auth(tok, nivel))
        assert r.status_code == 200, r.text
        return r.json()

    def nombres(casos):
        return {c.get('estudiante') or '' for c in casos}

    # ---------------------------------------------------- A/D: ambos niveles
    @test("A/D — Psicólogo AMBOS: X-Nivel primaria → solo Primaria; secundaria → solo Secundaria; sin header → ambas")
    def _():
        set_nivel('psi_a', None)
        tok = login('psi_a', 'Temporal2026x')
        todos = nombres(casos_de(tok))
        assert any('EstPrim' in n for n in todos) and any('EstSec' in n for n in todos), f'sin header debería ver ambas: {todos}'
        prim = nombres(casos_de(tok, 'primaria'))
        assert any('EstPrim' in n for n in prim), f'no ve primaria: {prim}'
        assert not any('EstSec' in n for n in prim), f'FUGA: con lente primaria ve secundaria: {prim}'
        sec = nombres(casos_de(tok, 'secundaria'))
        assert any('EstSec' in n for n in sec) and not any('EstPrim' in n for n in sec), f'lente secundaria mal: {sec}'

    @test("E — Psicólogo FIJO primaria: X-Nivel=secundaria NO lo saca de Primaria")
    def _():
        set_nivel('psi_a', 'primaria')
        tok = login('psi_a', 'Temporal2026x')
        for nivel in (None, 'secundaria', 'primaria'):
            n = nombres(casos_de(tok, nivel))
            assert not any('EstSec' in x for x in n), f'FUGA con X-Nivel={nivel}: {n}'

    @test("F — Psicólogo FIJO secundaria: equivalente a la inversa")
    def _():
        set_nivel('psi_a', 'secundaria')
        tok = login('psi_a', 'Temporal2026x')
        for nivel in (None, 'primaria', 'secundaria'):
            n = nombres(casos_de(tok, nivel))
            assert not any('EstPrim' in x for x in n), f'FUGA con X-Nivel={nivel}: {n}'

    # ------------------------------------------------------ B/C: coordinador
    @test("A — Coordinador AMBOS: el lente responde a X-Nivel")
    def _():
        set_nivel('coord_a', None)
        tok = login('coord_a', 'Temporal2026x')
        p = client.get('/api/dashboard/stats', headers=auth(tok, 'primaria')).json()
        s = client.get('/api/dashboard/stats', headers=auth(tok, 'secundaria')).json()
        t = client.get('/api/dashboard/stats', headers=auth(tok)).json()
        assert p['nivel_aplicado'] == 'primaria' and s['nivel_aplicado'] == 'secundaria'
        assert t['nivel_aplicado'] == 'todos'
        assert p['estudiantes'] + s['estudiantes'] <= t['estudiantes']

    @test("B — Coordinador FIJO primaria: X-Nivel=secundaria no lo mueve")
    def _():
        set_nivel('coord_a', 'primaria')
        tok = login('coord_a', 'Temporal2026x')
        for nivel in (None, 'secundaria'):
            r = client.get('/api/dashboard/stats', headers=auth(tok, nivel)).json()
            assert r['nivel_aplicado'] == 'primaria', f'X-Nivel={nivel} lo sacó de primaria: {r["nivel_aplicado"]}'

    @test("C — Coordinador FIJO secundaria: X-Nivel=primaria no lo mueve")
    def _():
        set_nivel('coord_a', 'secundaria')
        tok = login('coord_a', 'Temporal2026x')
        for nivel in (None, 'primaria'):
            r = client.get('/api/dashboard/stats', headers=auth(tok, nivel)).json()
            assert r['nivel_aplicado'] == 'secundaria', f'X-Nivel={nivel} lo sacó: {r["nivel_aplicado"]}'

    # ------------------------------------------- D: dashboard de psicología
    @test("D — /dashboard/psicologia cuenta solo la división del lente")
    def _():
        set_nivel('psi_a', None)
        tok = login('psi_a', 'Temporal2026x')
        t = client.get('/api/dashboard/psicologia', headers=auth(tok)).json()
        p = client.get('/api/dashboard/psicologia', headers=auth(tok, 'primaria')).json()
        s = client.get('/api/dashboard/psicologia', headers=auth(tok, 'secundaria')).json()
        assert t['nivel_aplicado'] == 'todos' and p['nivel_aplicado'] == 'primaria'
        assert p['pendientes'] + s['pendientes'] <= t['pendientes'], \
            f"primaria({p['pendientes']}) + secundaria({s['pendientes']}) > todos({t['pendientes']})"
        assert p['pendientes'] >= 1 and s['pendientes'] >= 1, 'cada división debe tener su caso'

    @test("E — Psicólogo FIJO: el dashboard tampoco se mueve con X-Nivel")
    def _():
        set_nivel('psi_a', 'primaria')
        tok = login('psi_a', 'Temporal2026x')
        r = client.get('/api/dashboard/psicologia', headers=auth(tok, 'secundaria')).json()
        assert r['nivel_aplicado'] == 'primaria', 'el header lo sacó de su división fija'

    # ------------------------------------------------- G/H/I: flujo de casos
    @test("G/H/I — Pendiente → Tomar → En proceso → Atendido, con Mis Casos Activos coherente")
    def _():
        set_nivel('psi_a', None)
        tok = login('psi_a', 'Temporal2026x')
        d0 = client.get('/api/dashboard/psicologia', headers=auth(tok)).json()
        assert len(d0['mis_casos']) == 0, 'un caso pendiente sin tomar NO es "mi caso activo"'
        assert d0['pendientes'] >= 1

        cid = [c['id'] for c in casos_de(tok) if c['estado'] == 'pendiente'][0]
        assert client.post(f'/api/psicologia/casos/{cid}/tomar', headers=auth(tok)).status_code == 200

        d1 = client.get('/api/dashboard/psicologia', headers=auth(tok)).json()
        assert d1['pendientes'] == d0['pendientes'] - 1, 'no salió de pendientes'
        assert any(c['id'] == cid for c in d1['mis_casos']), 'no apareció en Mis Casos Activos'
        dd = SessionLocal()
        try:
            c = dd.get(CasoPsicologia, cid)
            assert c.estado == 'en_proceso' and c.asignado_a is not None
        finally:
            dd.close()

        client.post(f'/api/psicologia/casos/{cid}/actualizar', json={'estado': 'atendido'}, headers=auth(tok))
        d2 = client.get('/api/dashboard/psicologia', headers=auth(tok)).json()
        assert not any(c['id'] == cid for c in d2['mis_casos']), 'un caso atendido sigue en Mis Casos Activos'

    @test("7 — 'Casos abiertos por tipo' = pendientes + en proceso, nunca atendidos")
    def _():
        tok = login('psi_a', 'Temporal2026x')
        d = client.get('/api/dashboard/psicologia', headers=auth(tok)).json()
        suma = sum(t['cantidad'] for t in d['casos_abiertos_por_tipo'])
        assert suma == d['pendientes'] + d['en_proceso'], \
            f"abiertos({suma}) != pendientes({d['pendientes']}) + en_proceso({d['en_proceso']})"

    # ----------------------------------------------------------- 8: orden
    @test("8 — Orden operativo: urgentes pendientes primero, atendidos al final")
    def _():
        set_nivel('psi_a', None)
        tok = login('psi_a', 'Temporal2026x')
        client.post('/api/psicologia/solicitar', json={'estudiante_id': A['es'], 'tipo': 'conductual',
            'urgencia': 'urgente', 'motivo': 'x'}, headers=auth(DIR_A))
        casos = casos_de(tok)
        rank = {'pendiente_urgente': 0, 'pendiente': 1, 'en_proceso': 2, 'atendido': 3}
        vals = [rank['pendiente_urgente'] if (c['estado'] == 'pendiente' and (c['urgencia'] or '').lower() == 'urgente')
                else rank.get(c['estado'], 3) for c in casos]
        assert vals == sorted(vals), f'orden incorrecto: {vals}'

    # ------------------------------------------------------- J: multi-tenant
    @test("J — Jamás se mezclan casos de otro colegio, con o sin lente")
    def _():
        set_nivel('psi_a', None)
        tok = login('psi_a', 'Temporal2026x')
        for nivel in (None, 'primaria', 'secundaria'):
            n = nombres(casos_de(tok, nivel))
            assert not any(x.endswith(' B') for x in n), f'FUGA multi-tenant con {nivel}: {n}'

    # ----------------------------------------------------------- K: urgente
    # ------------------------------------------- R2: stats-rol y alertas
    @test("R2-A — /dashboard/stats-rol psicología AMBOS respeta el lente")
    def _():
        set_nivel('psi_a', None)
        tok = login('psi_a', 'Temporal2026x')
        t = client.get('/api/dashboard/stats-rol', headers=auth(tok)).json()
        p = client.get('/api/dashboard/stats-rol', headers=auth(tok, 'primaria')).json()
        sx = client.get('/api/dashboard/stats-rol', headers=auth(tok, 'secundaria')).json()
        assert t['nivel_aplicado'] == 'todos'
        assert p['nivel_aplicado'] == 'primaria' and sx['nivel_aplicado'] == 'secundaria'
        assert p['casos_pendientes'] + sx['casos_pendientes'] <= t['casos_pendientes'], \
            f"prim({p['casos_pendientes']}) + sec({sx['casos_pendientes']}) > todos({t['casos_pendientes']})"
        assert p['casos_pendientes'] >= 1 and sx['casos_pendientes'] >= 1
        for k in ('casos_en_proceso', 'casos_urgentes', 'casos_atendidos_mes'):
            assert p[k] + sx[k] <= t[k], f'{k} no cuadra entre divisiones'

    @test("R2-B — Psicólogo FIJO: X-Nivel contrario no mueve los KPI de stats-rol")
    def _():
        set_nivel('psi_a', 'primaria')
        tok = login('psi_a', 'Temporal2026x')
        base = client.get('/api/dashboard/stats-rol', headers=auth(tok)).json()
        forzado = client.get('/api/dashboard/stats-rol', headers=auth(tok, 'secundaria')).json()
        assert forzado['nivel_aplicado'] == 'primaria', 'el header lo sacó de su división'
        assert forzado['casos_pendientes'] == base['casos_pendientes'], \
            'los KPI cambiaron con un header que debía ignorarse'

    @test("R2-C — /dashboard/alertas respeta el lente de división")
    def _():
        set_nivel('psi_a', None)
        tok = login('psi_a', 'Temporal2026x')
        def urg(nivel=None):
            al = client.get('/api/dashboard/alertas', headers=auth(tok, nivel)).json()
            items = al.get('alertas', al) if isinstance(al, dict) else al
            return sum(a.get('count', 0) for a in items
                       if a.get('tipo') == 'psicologia' and 'urgente' in (a.get('mensaje') or '').lower())
        t, p, sx = urg(), urg('primaria'), urg('secundaria')
        assert p + sx <= t, f'alertas urgentes: prim({p}) + sec({sx}) > todos({t})'

    # --------------------------------------- R2: candado de escritura
    @test("R2-D — Psicóloga FIJA Primaria no puede TOMAR un caso de Secundaria (403)")
    def _():
        set_nivel('psi_a', None)
        tok_amb = login('psi_a', 'Temporal2026x')
        cid = [c['id'] for c in casos_de(tok_amb, 'secundaria') if c['estado'] == 'pendiente'][0]

        set_nivel('psi_a', 'primaria')
        tok = login('psi_a', 'Temporal2026x')
        r = client.post(f'/api/psicologia/casos/{cid}/tomar', headers=auth(tok))
        assert r.status_code == 403, f'tomó un caso de otra división ({r.status_code})'
        d = SessionLocal()
        try:
            c = d.get(CasoPsicologia, cid)
            assert c.estado == 'pendiente', 'el caso cambió de estado pese al 403'
            assert c.asignado_a is None, 'quedó asignado pese al 403'
        finally:
            d.close()

    @test("R2-E — Psicóloga FIJA Primaria no puede ACTUALIZAR un caso de Secundaria (403)")
    def _():
        set_nivel('psi_a', None)
        tok_amb = login('psi_a', 'Temporal2026x')
        cid = [c['id'] for c in casos_de(tok_amb, 'secundaria') if c['estado'] == 'pendiente'][0]
        d = SessionLocal()
        try:
            antes = d.get(CasoPsicologia, cid)
            estado_antes, notas_antes = antes.estado, antes.notas_atencion
        finally:
            d.close()

        set_nivel('psi_a', 'primaria')
        tok = login('psi_a', 'Temporal2026x')
        r = client.post(f'/api/psicologia/casos/{cid}/actualizar',
                        json={'estado': 'atendido', 'notas_atencion': 'intruso'},
                        headers=auth(tok))
        assert r.status_code == 403, f'modificó un caso de otra división ({r.status_code})'
        d = SessionLocal()
        try:
            c = d.get(CasoPsicologia, cid)
            assert c.estado == estado_antes and c.notas_atencion == notas_antes, \
                'se modificó el caso pese al 403'
        finally:
            d.close()

    @test("R2-F — Coordinador FIJO Primaria no puede SOLICITAR para un estudiante de Secundaria (403)")
    def _():
        set_nivel('coord_a', 'primaria')
        tok = login('coord_a', 'Temporal2026x')
        d = SessionLocal()
        try:
            antes = d.query(CasoPsicologia).filter_by(estudiante_id=A['es']).count()
        finally:
            d.close()
        r = client.post('/api/psicologia/solicitar', json={
            'estudiante_id': A['es'], 'tipo': 'emocional',
            'urgencia': 'normal', 'motivo': 'x'}, headers=auth(tok))
        assert r.status_code == 403, f'creó un caso de otra división ({r.status_code})'
        d = SessionLocal()
        try:
            assert d.query(CasoPsicologia).filter_by(estudiante_id=A['es']).count() == antes, \
                'el caso se creó pese al 403'
        finally:
            d.close()

    @test("R2-F — Coordinador AMBOS sí puede solicitar en cualquier división")
    def _():
        set_nivel('coord_a', None)
        tok = login('coord_a', 'Temporal2026x')
        r = client.post('/api/psicologia/solicitar', json={
            'estudiante_id': A['es'], 'tipo': 'emocional',
            'urgencia': 'normal', 'motivo': 'x'}, headers=auth(tok))
        assert r.status_code == 201, f'bloqueó a un coordinador autorizado para ambas: {r.text}'

    # --------------------------------------------- R2-G/H: notificaciones
    @test("R2-G — Un caso de división NO autorizada no genera NINGUNA notificación")
    def _():
        set_nivel('psi_a', 'primaria')
        d = SessionLocal()
        try:
            u = d.query(Usuario).filter_by(username='psi_a').first()
            ids_antes = {n.id for n in d.query(Notificacion).filter_by(usuario_id=u.id).all()}
        finally:
            d.close()

        r = client.post('/api/psicologia/solicitar', json={
            'estudiante_id': A['es'], 'tipo': 'emocional',
            'urgencia': 'urgente', 'motivo': 'Confidencial'}, headers=auth(DIR_A))
        assert r.status_code == 201, r.text

        d = SessionLocal()
        try:
            u = d.query(Usuario).filter_by(username='psi_a').first()
            ids_despues = {n.id for n in d.query(Notificacion).filter_by(usuario_id=u.id).all()}
            nuevas = ids_despues - ids_antes
            assert not nuevas, \
                f'llegaron {len(nuevas)} notificación(es) de una división no autorizada'
        finally:
            d.close()

    @test("R2-H — Autorizada para ambas: SÍ recibe, con texto genérico y sin datos del menor")
    def _():
        set_nivel('psi_a', None)
        d = SessionLocal()
        try:
            u = d.query(Usuario).filter_by(username='psi_a').first()
            ids_antes = {n.id for n in d.query(Notificacion).filter_by(usuario_id=u.id).all()}
        finally:
            d.close()

        client.post('/api/psicologia/solicitar', json={
            'estudiante_id': A['es'], 'tipo': 'emocional',
            'urgencia': 'urgente', 'motivo': 'Situacion familiar delicada'}, headers=auth(DIR_A))

        d = SessionLocal()
        try:
            u = d.query(Usuario).filter_by(username='psi_a').first()
            nuevas = [n for n in d.query(Notificacion).filter_by(usuario_id=u.id).all()
                      if n.id not in ids_antes]
            assert nuevas, 'no recibió el aviso pese a estar autorizada para ambas'
            n = nuevas[-1]
            t = (n.titulo or '')
            assert 'Secundaria' in t, f'no indica la división: {t}'
            texto = (t + ' ' + (n.mensaje or '')).lower()
            for prohibido in ('estsec', 'familiar', 'delicada', 'situacion'):
                assert prohibido not in texto, f"expone '{prohibido}' en la notificación"
        finally:
            d.close()

    # ------------------------------------------ R2: política de contraseñas
    @test("R2-7 — Contraseñas sin mayúscula/número/símbolo son válidas (mín. 8)")
    def _():
        tok_dir = DIR_A
        for i, pw in enumerate(['colegio2026', 'Mipassword', '12345678', 'abcdefgh']):
            u = f'pw_test_{i}'
            r = client.post('/api/usuarios', json={
                'username': u, 'password': pw, 'nombre': 'PW', 'apellido': str(i),
                'role': 'profesor'}, headers=auth(tok_dir))
            assert r.status_code == 201, f"rechazó '{pw}': {r.text}"

    @test("R2-7 — Menos de 8 caracteres se rechaza")
    def _():
        r = client.post('/api/usuarios', json={
            'username': 'pw_corta', 'password': 'corta7', 'nombre': 'PW',
            'apellido': 'C', 'role': 'profesor'}, headers=auth(DIR_A))
        assert r.status_code == 400, 'aceptó una contraseña de menos de 8'

    @test("R2-7 — cambiar-password acepta la política simple y rechaza la igual a la actual")
    def _():
        client.post('/api/usuarios', json={
            'username': 'pw_cambio', 'password': 'inicial2026', 'nombre': 'PW',
            'apellido': 'X', 'role': 'profesor'}, headers=auth(DIR_A))
        tok = client.post('/api/auth/login',
                          json={'username': 'pw_cambio', 'password': 'inicial2026'}).json()['token']

        d = SessionLocal()
        try:
            u = d.query(Usuario).filter_by(username='pw_cambio').first()
            assert u.must_change_password is True
            tv_antes = u.token_version or 0
        finally:
            d.close()

        # Igual a la actual → rechazada
        r = client.post('/api/auth/cambiar-password',
                        json={'password_actual': 'inicial2026', 'password_nuevo': 'inicial2026'},
                        headers=auth(tok))
        assert r.status_code == 400, 'aceptó la misma contraseña como "nueva"'

        # Sin mayúscula ni número → debe ACEPTARSE
        r = client.post('/api/auth/cambiar-password',
                        json={'password_actual': 'inicial2026', 'password_nuevo': 'solominusculas'},
                        headers=auth(tok))
        assert r.status_code == 200, f'rechazó una contraseña válida de 14 minúsculas: {r.text}'

        d = SessionLocal()
        try:
            u = d.query(Usuario).filter_by(username='pw_cambio').first()
            assert u.must_change_password is False, 'no limpió must_change_password'
            assert (u.token_version or 0) > tv_antes, 'no incrementó token_version'
        finally:
            d.close()
        assert client.get('/api/auth/me', headers=auth(tok)).status_code == 401, \
            'la sesión anterior sigue viva tras cambiar la contraseña'
        assert client.post('/api/auth/login',
                           json={'username': 'pw_cambio', 'password': 'solominusculas'}
                           ).json().get('token'), 'no puede entrar con la nueva'

    @test("R2-7 — cambiar-password sigue exigiendo el mínimo de 8")
    def _():
        tok = client.post('/api/auth/login',
                          json={'username': 'pw_cambio', 'password': 'solominusculas'}).json()['token']
        r = client.post('/api/auth/cambiar-password',
                        json={'password_actual': 'solominusculas', 'password_nuevo': 'corta7'},
                        headers=auth(tok))
        assert r.status_code == 400, 'aceptó menos de 8 caracteres'

print(f"\n{B}{'=' * 60}{X}")
print(f"{B}  RESUMEN: {pasados}/{total} tests pasaron{X}")
print(f"{B}{'=' * 60}{X}\n")
if fallos:
    for n, e in fallos:
        print(f"{R}✗ {n}{X}\n    {e}")
    sys.exit(1)
print(f"{G}{B}🎉 DIVISIONES + PSICOLOGÍA VERDE{X}\n")
