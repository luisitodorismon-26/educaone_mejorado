"""
EducaOne — v2.19.8: Horarios separados por nivel (Primaria / Secundaria).

Verifica la separación de nivel en Horarios reutilizando la infraestructura
existente (una sola tabla Horario; el nivel se deriva de Horario -> Curso ->
Grado -> nivel) y la evolución ADITIVA de Recreo (columna `nivel` nullable con
fallback legacy).

Cubre A–L del encargo:
  A  Primaria y Secundaria pueden tener recreos distintos en la MISMA tanda.
  B  Consultar Primaria NO devuelve el recreo específico de Secundaria.
  C  Consultar Secundaria NO devuelve el recreo específico de Primaria.
  D  Un recreo legacy (nivel=NULL) sigue sirviendo de fallback.
  E  Si existe recreo específico, gana sobre el legacy.
  F  Dirección en Primaria solo obtiene cursos de Primaria.
  G  Dirección en Secundaria solo obtiene cursos de Secundaria.
  H  Coordinador nivel_asignado=primaria no cruza a Secundaria.
  I  Coordinador nivel_asignado=secundaria no cruza a Primaria.
  J  Profesor con clases en AMBOS niveles ve su horario personal completo.
  K  Aislamiento multi-tenant intacto.
  L  Los horarios existentes NO cambian ni se eliminan; los recreos legacy
     tampoco.

Uso:
    cd backend
    python tools/test_horarios_por_nivel_v2198.py
"""
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for ext in ['', '-shm', '-wal']:
    if os.path.exists(os.path.join(_BASE, 'sge.db' + ext)):
        os.remove(os.path.join(_BASE, 'sge.db' + ext))
if os.path.exists(os.path.join(_BASE, 'INITIAL_CREDENTIALS.txt')):
    os.remove(os.path.join(_BASE, 'INITIAL_CREDENTIALS.txt'))

from sqlalchemy import inspect as _sa_inspect
from database import engine, SessionLocal
from models import Base, Usuario, Grado, Recreo, Horario
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


def set_nivel(username, nivel):
    d = SessionLocal()
    try:
        u = d.query(Usuario).filter_by(username=username).first()
        u.nivel_asignado = nivel
        d.commit()
    finally:
        d.close()


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


def horas(recreos):
    return sorted((r['hora_inicio'], r['hora_fin']) for r in recreos)


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
        """Colegio con 1 curso de primaria + 1 de secundaria en la MISMA tanda
        (Matutina), un profesor MIXTO con clase en ambos, y coordinadores."""
        _d = SessionLocal()
        try:
            _cid = _d.query(Usuario).filter_by(
                username=('direccion' if sfx == 'a' else 'dir_b')).first().colegio_id
            if not _d.query(Grado).filter_by(colegio_id=_cid, nivel='primaria').first():
                _d.add(Grado(colegio_id=_cid, nombre=f'5to Primaria {sfx}',
                             nivel='primaria', ciclo='segundo_ciclo', orden=50))
                _d.commit()
        finally:
            _d.close()

        grados = client.get('/api/grados', headers=auth(tok)).json()
        tandas = client.get('/api/tandas', headers=auth(tok)).json()
        asigs = client.get('/api/asignaturas', headers=auth(tok)).json()
        matutina = next(t for t in tandas if t['nombre'] == 'Matutina')
        vespertina = next(t for t in tandas if t['nombre'] == 'Vespertina')
        gp = next(g for g in grados if g['nivel'] == 'primaria')
        gs = next(g for g in grados if g['nivel'] == 'secundaria')
        asig_id = asigs[0]['id']

        cp = client.post('/api/cursos', json={'grado_id': gp['id'], 'tanda_id': matutina['id'], 'nombre': 'A'}, headers=auth(tok)).json()['id']
        cs = client.post('/api/cursos', json={'grado_id': gs['id'], 'tanda_id': matutina['id'], 'nombre': 'A'}, headers=auth(tok)).json()['id']

        client.post('/api/usuarios', json={'username': f'prof_mix_{sfx}', 'password': 'Temporal2026x',
            'nombre': 'ProfMix', 'apellido': sfx.upper(), 'email': f'pm_{sfx}@x.com', 'role': 'profesor'}, headers=auth(tok))
        pm = SessionLocal()
        try:
            prof_id = pm.query(Usuario).filter_by(username=f'prof_mix_{sfx}').first().id
        finally:
            pm.close()

        client.post('/api/asignaciones', json={'profesor_id': prof_id, 'curso_id': cp, 'asignatura_id': asig_id}, headers=auth(tok))
        client.post('/api/asignaciones', json={'profesor_id': prof_id, 'curso_id': cs, 'asignatura_id': asig_id}, headers=auth(tok))

        h_prim = client.post('/api/horarios', json={'curso_id': cp, 'asignatura_id': asig_id, 'profesor_id': prof_id,
            'dia': 'Lunes', 'hora_inicio': '08:00', 'hora_fin': '08:45', 'tipo_bloque': 'clase'}, headers=auth(tok)).json()['id']
        h_sec = client.post('/api/horarios', json={'curso_id': cs, 'asignatura_id': asig_id, 'profesor_id': prof_id,
            'dia': 'Martes', 'hora_inicio': '09:00', 'hora_fin': '09:45', 'tipo_bloque': 'clase'}, headers=auth(tok)).json()['id']

        for rol in ('coordinador',):
            for niv in ('prim', 'sec'):
                client.post('/api/usuarios', json={'username': f'coord_{niv}_{sfx}', 'password': 'Temporal2026x',
                    'nombre': f'Coord{niv}', 'apellido': sfx.upper(), 'email': f'c{niv}_{sfx}@x.com', 'role': rol}, headers=auth(tok))
        set_nivel(f'coord_prim_{sfx}', 'primaria')
        set_nivel(f'coord_sec_{sfx}', 'secundaria')

        return dict(cp=cp, cs=cs, prof=prof_id, h_prim=h_prim, h_sec=h_sec,
                    matutina=matutina['id'], vespertina=vespertina['id'], asig=asig_id)

    A = montar(DIR_A, 'a')
    Bc = montar(DIR_B, 'b')
    print(f"  {G}✓{X} 2 colegios montados (curso primaria + secundaria en Matutina, profesor mixto)")

    # Snapshot de los horarios existentes ANTES de tocar recreos (para L).
    def snap_horarios(tok, prof):
        r = client.get(f'/api/horarios/profesor/{prof}', headers=auth(tok))
        return sorted(((h['id'], h['curso_id'], h['dia'], h['hora_inicio'], h['hora_fin'],
                        h['tipo_bloque']) for h in r.json()))
    SNAP_A = snap_horarios(DIR_A, A['prof'])

    def recreos(tok, nivel=None, tanda_id=None):
        url = '/api/recreos' + (f'?tanda_id={tanda_id}' if tanda_id else '')
        r = client.get(url, headers=auth(tok, nivel))
        assert r.status_code == 200, r.text
        return r.json()

    # ══════════════════════════════════════ SCHEMA
    @test("SCHEMA — recreos.nivel existe y es nullable (evolución aditiva)")
    def _():
        cols = {c['name']: c for c in _sa_inspect(engine).get_columns('recreos')}
        assert 'nivel' in cols, 'falta la columna recreos.nivel'
        assert cols['nivel']['nullable'], 'recreos.nivel debe ser nullable (fallback legacy)'

    # ══════════════════════════════════════ A / B / C
    @test("A — Matutina puede tener recreo de Primaria (09:30–10:00) y de Secundaria (10:20–10:40) a la vez")
    def _():
        r1 = client.post('/api/recreos', json={'tanda_id': A['matutina'], 'nombre': 'Recreo',
            'hora_inicio': '09:30', 'hora_fin': '10:00'}, headers=auth(DIR_A, 'primaria'))
        r2 = client.post('/api/recreos', json={'tanda_id': A['matutina'], 'nombre': 'Recreo',
            'hora_inicio': '10:20', 'hora_fin': '10:40'}, headers=auth(DIR_A, 'secundaria'))
        assert r1.status_code == 201 and r2.status_code == 201, (r1.text, r2.text)
        assert r1.json()['nivel'] == 'primaria' and r2.json()['nivel'] == 'secundaria'
        # Sin lente ("Todos") se ven ambos.
        todos = horas(recreos(DIR_A, None, A['matutina']))
        assert ('09:30', '10:00') in todos and ('10:20', '10:40') in todos, todos

    @test("B — Dirección en Primaria SOLO obtiene el recreo de Primaria de esa tanda")
    def _():
        h = horas(recreos(DIR_A, 'primaria', A['matutina']))
        assert h == [('09:30', '10:00')], h

    @test("C — Dirección en Secundaria SOLO obtiene el recreo de Secundaria de esa tanda")
    def _():
        h = horas(recreos(DIR_A, 'secundaria', A['matutina']))
        assert h == [('10:20', '10:40')], h

    # ══════════════════════════════════════ D / E (fallback legacy por tanda)
    @test("D — Recreo legacy (nivel=NULL) funciona como fallback para AMBOS niveles mientras no haya específico")
    def _():
        r = client.post('/api/recreos', json={'tanda_id': A['vespertina'], 'nombre': 'Recreo',
            'hora_inicio': '15:00', 'hora_fin': '15:30'}, headers=auth(DIR_A))  # sin X-Nivel => legacy
        assert r.status_code == 201 and r.json()['nivel'] is None, r.text
        assert horas(recreos(DIR_A, 'primaria', A['vespertina'])) == [('15:00', '15:30')]
        assert horas(recreos(DIR_A, 'secundaria', A['vespertina'])) == [('15:00', '15:30')]

    @test("E — Al crear el recreo específico de Primaria, ESE gana sobre el legacy; Secundaria sigue con el legacy")
    def _():
        r = client.post('/api/recreos', json={'tanda_id': A['vespertina'], 'nombre': 'Recreo',
            'hora_inicio': '15:45', 'hora_fin': '16:00'}, headers=auth(DIR_A, 'primaria'))
        assert r.status_code == 201, r.text
        assert horas(recreos(DIR_A, 'primaria', A['vespertina'])) == [('15:45', '16:00')], 'específico no ganó'
        assert horas(recreos(DIR_A, 'secundaria', A['vespertina'])) == [('15:00', '15:30')], 'secundaria perdió el fallback'

    # ══════════════════════════════════════ F / G (cursos por nivel)
    @test("F — Dirección en Primaria solo ve cursos de Primaria")
    def _():
        cs = client.get('/api/cursos', headers=auth(DIR_A, 'primaria')).json()
        niveles = {c['nivel'] for c in cs}
        assert niveles == {'primaria'}, niveles
        assert A['cp'] in {c['id'] for c in cs} and A['cs'] not in {c['id'] for c in cs}

    @test("G — Dirección en Secundaria solo ve cursos de Secundaria")
    def _():
        cs = client.get('/api/cursos', headers=auth(DIR_A, 'secundaria')).json()
        niveles = {c['nivel'] for c in cs}
        assert niveles == {'secundaria'}, niveles
        assert A['cs'] in {c['id'] for c in cs} and A['cp'] not in {c['id'] for c in cs}

    @test("F/G — GET /api/horarios (lista institucional) también respeta el lente")
    def _():
        prim = client.get('/api/horarios', headers=auth(DIR_A, 'primaria')).json()
        sec = client.get('/api/horarios', headers=auth(DIR_A, 'secundaria')).json()
        assert {h['id'] for h in prim if h['curso_id']} == {A['h_prim']}, prim
        assert {h['id'] for h in sec if h['curso_id']} == {A['h_sec']}, sec

    # ══════════════════════════════════════ H / I (coordinador con nivel fijo)
    @test("H — Coordinador FIJO Primaria: no cruza a Secundaria (cursos, horario de curso, recreos)")
    def _():
        tok = login('coord_prim_a', 'Temporal2026x')
        cs = client.get('/api/cursos', headers=auth(tok)).json()
        assert {c['nivel'] for c in cs} == {'primaria'}, cs
        # X-Nivel=secundaria NO puede sacarlo de su división fija.
        r = client.get(f'/api/horarios/curso/{A["cs"]}', headers=auth(tok, 'secundaria'))
        assert r.status_code == 403, f'vio horario de curso de Secundaria: {r.status_code}'
        assert client.get(f'/api/horarios/curso/{A["cp"]}', headers=auth(tok)).status_code == 200
        rec = recreos(tok, 'secundaria', A['matutina'])
        assert horas(rec) == [('09:30', '10:00')], f'coordinador de primaria vio recreo de secundaria: {horas(rec)}'

    @test("I — Coordinador FIJO Secundaria: no cruza a Primaria")
    def _():
        tok = login('coord_sec_a', 'Temporal2026x')
        cs = client.get('/api/cursos', headers=auth(tok)).json()
        assert {c['nivel'] for c in cs} == {'secundaria'}, cs
        r = client.get(f'/api/horarios/curso/{A["cp"]}', headers=auth(tok, 'primaria'))
        assert r.status_code == 403, f'vio horario de curso de Primaria: {r.status_code}'
        rec = recreos(tok, 'primaria', A['matutina'])
        assert horas(rec) == [('10:20', '10:40')], f'coordinador de secundaria vio recreo de primaria: {horas(rec)}'

    # ══════════════════════════════════════ J (profesor mixto)
    @test("J — Profesor con clases en Primaria Y Secundaria ve su horario personal COMPLETO (con o sin X-Nivel)")
    def _():
        tok = login('prof_mix_a', 'Temporal2026x')
        for nivel in (None, 'primaria', 'secundaria'):
            r = client.get(f'/api/horarios/profesor/{A["prof"]}', headers=auth(tok, nivel))
            ids = {h['id'] for h in r.json()}
            assert ids == {A['h_prim'], A['h_sec']}, f'X-Nivel={nivel}: perdió una clase válida -> {ids}'
        # "mi-horario" personal tampoco se recorta
        mine = client.get('/api/horarios/profesor/%d' % A['prof'], headers=auth(tok, 'primaria')).json()
        assert any(h['id'] == A['h_sec'] for h in mine), 'a un profesor de primaria se le ocultó su clase de secundaria'

    # ══════════════════════════════════════ K (multi-tenant)
    @test("K — Aislamiento multi-tenant: Dirección B no ve horarios ni recreos de A")
    def _():
        assert client.get(f'/api/horarios/curso/{A["cp"]}', headers=auth(DIR_B)).status_code == 404
        assert client.get(f'/api/horarios/curso/{A["cs"]}', headers=auth(DIR_B)).status_code == 404
        rb_ids = {r['id'] for r in recreos(DIR_B, None)}
        ra_ids = {r['id'] for r in recreos(DIR_A, None)}
        assert rb_ids.isdisjoint(ra_ids), f'fuga de recreos entre colegios: {rb_ids & ra_ids}'
        # El profesor mixto de B es independiente del de A.
        hb = client.get('/api/horarios', headers=auth(DIR_B)).json()
        assert {A['h_prim'], A['h_sec']}.isdisjoint({h['id'] for h in hb})

    # ══════════════════════════════════════ L (nada existente cambia)
    @test("L — Los horarios existentes NO cambiaron ni se eliminaron tras toda la operación de recreos")
    def _():
        assert snap_horarios(DIR_A, A['prof']) == SNAP_A, 'un horario existente cambió'
        d = SessionLocal()
        try:
            for hid in (A['h_prim'], A['h_sec'], Bc['h_prim'], Bc['h_sec']):
                assert d.get(Horario, hid) is not None, f'horario {hid} desapareció'
            # El recreo legacy conserva nivel=NULL y sigue activo.
            legacy = [r for r in d.query(Recreo).filter_by(tanda_id=A['vespertina']).all() if r.nivel is None]
            assert legacy and all(r.activo for r in legacy), 'el recreo legacy se perdió o se desactivó'
            assert all(r.nivel is None for r in legacy), 'a un recreo legacy se le adivinó el nivel'
        finally:
            d.close()

    @test("L — Editar un recreo sin mandar `nivel` no re-etiqueta un legacy")
    def _():
        d = SessionLocal()
        try:
            legacy_id = [r for r in d.query(Recreo).filter_by(tanda_id=A['vespertina']).all() if r.nivel is None][0].id
        finally:
            d.close()
        r = client.put(f'/api/recreos/{legacy_id}', json={'nombre': 'Merienda'}, headers=auth(DIR_A, 'primaria'))
        assert r.status_code == 200, r.text
        d = SessionLocal()
        try:
            assert d.get(Recreo, legacy_id).nivel is None, 'un PUT sin `nivel` re-etiquetó el recreo legacy'
        finally:
            d.close()

print(f"\n{B}{'=' * 60}{X}")
print(f"{B}  RESUMEN: {pasados}/{total} tests pasaron{X}")
print(f"{B}{'=' * 60}{X}\n")
if fallos:
    for n, e in fallos:
        print(f"{R}✗ {n}{X}\n    {e}")
    sys.exit(1)
print(f"{G}{B}🎉 HORARIOS POR NIVEL — VERDE{X}\n")
