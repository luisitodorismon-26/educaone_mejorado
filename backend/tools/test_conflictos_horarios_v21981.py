"""
EducaOne — v2.19.8.1: Prevención de conflictos de horario.

Protección mínima contra horarios imposibles por error humano. SOLO afecta a
bloques tipo_bloque='clase':

  - un mismo PROFESOR no puede tener dos clases superpuestas el mismo día
    (aunque una sea de Primaria y otra de Secundaria: físicamente no puede
    estar en dos aulas a la vez);
  - un mismo CURSO no puede tener dos clases superpuestas el mismo día
    (aunque las den profesores distintos).

Solapamiento:  nuevo_inicio < existente_fin  AND  nuevo_fin > existente_inicio.

NO se agrega ninguna restricción por nivel al profesor. Un profesor mixto
Primaria + Secundaria sigue siendo válido mientras las clases no se pisen.

Cubre A–O del encargo. Uso:
    cd backend
    python tools/test_conflictos_horarios_v21981.py
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
from models import Base, Usuario, Grado, Horario, AsignacionProfesor
Base.metadata.create_all(bind=engine)
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)
fallos, pasados, total = [], 0, 0
G, R, B, C, X = "\033[92m", "\033[91m", "\033[1m", "\033[96m", "\033[0m"

CREADOS = {}  # id -> (profesor_id, curso_id, dia, hora_inicio, hora_fin, tipo_bloque)


def auth(t):
    return {'Authorization': f'Bearer {t}'}


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


def _count_horarios():
    d = SessionLocal()
    try:
        return d.query(Horario).count()
    finally:
        d.close()


def _fila(hid):
    d = SessionLocal()
    try:
        h = d.get(Horario, hid)
        if h is None:
            return None
        return (h.profesor_id, h.curso_id, h.dia, h.hora_inicio, h.hora_fin, h.tipo_bloque, h.activo)
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

    def montar(tok, sfx, dir_username):
        """1 curso de Primaria + 1 de Secundaria (Matutina), un profesor MIXTO
        asignado a AMBOS niveles, y dos profesores extra para los conflictos de
        curso."""
        d = SessionLocal()
        try:
            cid = d.query(Usuario).filter_by(username=dir_username).first().colegio_id
            if not d.query(Grado).filter_by(colegio_id=cid, nivel='primaria').first():
                d.add(Grado(colegio_id=cid, nombre=f'5to Primaria {sfx}',
                            nivel='primaria', ciclo='segundo_ciclo', orden=50))
                d.commit()
        finally:
            d.close()

        grados = client.get('/api/grados', headers=auth(tok)).json()
        tandas = client.get('/api/tandas', headers=auth(tok)).json()
        asigs = client.get('/api/asignaturas', headers=auth(tok)).json()
        if not asigs:
            asigs = [client.post('/api/asignaturas', json={'nombre': 'Matemática', 'codigo': 'MAT'},
                                 headers=auth(tok)).json()]
        matutina = next(t for t in tandas if t['nombre'] == 'Matutina')
        gp = next(g for g in grados if g['nivel'] == 'primaria')
        gs = next(g for g in grados if g['nivel'] == 'secundaria')
        asig = asigs[0]['id']

        cp = client.post('/api/cursos', json={'grado_id': gp['id'], 'tanda_id': matutina['id'], 'nombre': 'A'}, headers=auth(tok)).json()['id']
        cs = client.post('/api/cursos', json={'grado_id': gs['id'], 'tanda_id': matutina['id'], 'nombre': 'A'}, headers=auth(tok)).json()['id']
        cpH = client.post('/api/cursos', json={'grado_id': gp['id'], 'tanda_id': matutina['id'], 'nombre': 'H'}, headers=auth(tok)).json()['id']

        def _prof(u):
            client.post('/api/usuarios', json={'username': u, 'password': 'Temporal2026x',
                'nombre': u, 'apellido': sfx.upper(), 'email': f'{u}@x.com', 'role': 'profesor'}, headers=auth(tok))
            dd = SessionLocal()
            try:
                return dd.query(Usuario).filter_by(username=u).first().id
            finally:
                dd.close()

        prof = _prof(f'prof_mix_{sfx}')
        profX = _prof(f'prof_x_{sfx}')
        profY = _prof(f'prof_y_{sfx}')

        # El profesor MIXTO queda asignado a Primaria Y Secundaria (una prueba lo
        # necesita: F/G demuestran que eso es válido y no lo limita ningún nivel).
        client.post('/api/asignaciones', json={'profesor_id': prof, 'curso_id': cp, 'asignatura_id': asig}, headers=auth(tok))
        client.post('/api/asignaciones', json={'profesor_id': prof, 'curso_id': cs, 'asignatura_id': asig}, headers=auth(tok))

        return dict(cp=cp, cs=cs, cpH=cpH, prof=prof, profX=profX, profY=profY, asig=asig, tok=tok)

    A = montar(DIR_A, 'a', 'direccion')
    Bc = montar(DIR_B, 'b', 'dir_b')
    print(f"  {G}✓{X} 2 colegios montados (Primaria + Secundaria en Matutina, profesor mixto asignado a ambos)")

    def crear(curso, prof, dia, hi, hf, tok=None, asig=None):
        return client.post('/api/horarios', json={
            'curso_id': curso, 'asignatura_id': asig or A['asig'], 'profesor_id': prof,
            'dia': dia, 'hora_inicio': hi, 'hora_fin': hf, 'tipo_bloque': 'clase',
        }, headers=auth(tok or DIR_A))

    def crear_ok(curso, prof, dia, hi, hf, tok=None, asig=None):
        n = _count_horarios()
        r = crear(curso, prof, dia, hi, hf, tok, asig)
        assert r.status_code == 201, f'esperaba 201, obtuvo {r.status_code}: {r.text}'
        hid = r.json()['id']
        CREADOS[hid] = (prof, curso, dia, hi, hf, 'clase')
        assert _count_horarios() == n + 1, 'no se creó exactamente una fila'
        return hid

    def crear_409(curso, prof, dia, hi, hf, tok=None, asig=None, quien='profesor'):
        n = _count_horarios()
        r = crear(curso, prof, dia, hi, hf, tok, asig)
        assert r.status_code == 409, f'esperaba 409, obtuvo {r.status_code}: {r.text}'
        msg = (r.json() or {}).get('error') or ''
        assert 'Conflicto de horario' in msg, f'mensaje poco claro: {msg!r}'
        assert (f'este {quien}' in msg), f'el mensaje no distingue {quien}: {msg!r}'
        assert _count_horarios() == n, 'un 409 creó una fila'
        return msg

    # ════════════════════════════════ A
    @test("A — mismo profesor + mismo día + misma hora -> 409")
    def _():
        A['hA'] = crear_ok(A['cp'], A['prof'], 'Lunes', '08:00', '08:45')
        crear_409(A['cp'], A['prof'], 'Lunes', '08:00', '08:45')

    # ════════════════════════════════ B
    @test("B — mismo profesor: 08:00–08:45 y 08:30–09:15 -> 409 (solape parcial)")
    def _():
        crear_ok(A['cp'], A['prof'], 'Martes', '08:00', '08:45')
        crear_409(A['cp'], A['prof'], 'Martes', '08:30', '09:15')

    # ════════════════════════════════ C
    @test("C — mismo profesor: 08:00–09:00 y 08:15–08:45 -> 409 (contenida)")
    def _():
        crear_ok(A['cp'], A['prof'], 'Miércoles', '08:00', '09:00')
        crear_409(A['cp'], A['prof'], 'Miércoles', '08:15', '08:45')

    # ════════════════════════════════ D
    @test("D — mismo profesor: 08:00–08:45 y 08:45–09:30 -> permitido (adyacentes)")
    def _():
        crear_ok(A['cp'], A['prof'], 'Jueves', '08:00', '08:45')
        crear_ok(A['cp'], A['prof'], 'Jueves', '08:45', '09:30')

    # ════════════════════════════════ E
    @test("E — mismo profesor + misma hora pero OTRO día -> permitido")
    def _():
        crear_ok(A['cp'], A['prof'], 'Viernes', '08:00', '08:45')

    # ════════════════════════════════ F
    @test("F — mismo profesor: Primaria Lun 08:00–08:45 + Secundaria Lun 09:00–09:45 -> permitido")
    def _():
        A['hF'] = crear_ok(A['cs'], A['prof'], 'Lunes', '09:00', '09:45')

    # ════════════════════════════════ G
    @test("G — mismo profesor: Primaria Lun 08:00–08:45 + Secundaria Lun 08:30–09:15 -> 409")
    def _():
        crear_409(A['cs'], A['prof'], 'Lunes', '08:30', '09:15')

    # ════════════════════════════════ H
    @test("H — mismo curso + mismo horario + profesor DIFERENTE -> 409 (conflicto de curso)")
    def _():
        A['hH'] = crear_ok(A['cpH'], A['profX'], 'Lunes', '10:00', '10:45')
        crear_409(A['cpH'], A['profY'], 'Lunes', '10:00', '10:45', quien='curso')

    # ════════════════════════════════ I
    @test("I — mismo curso + solape parcial (profes distintos) -> 409")
    def _():
        A['hI'] = crear_ok(A['cpH'], A['profX'], 'Martes', '10:00', '10:45')
        crear_409(A['cpH'], A['profY'], 'Martes', '10:30', '11:15', quien='curso')

    # ════════════════════════════════ J
    @test("J — cursos distintos + profesores distintos + misma hora -> permitido")
    def _():
        crear_ok(A['cs'], A['prof'], 'Sábado', '07:00', '07:45')
        crear_ok(A['cpH'], A['profX'], 'Sábado', '07:00', '07:45')

    # ════════════════════════════════ K
    @test("K — PUT que NO cambia el horario (solo aula) -> 200, sin conflicto consigo mismo")
    def _():
        antes = _fila(A['hA'])
        r = client.put(f"/api/horarios/{A['hA']}", json={'aula': 'K-1'}, headers=auth(DIR_A))
        assert r.status_code == 200, f'esperaba 200, obtuvo {r.status_code}: {r.text}'
        d = _fila(A['hA'])
        assert d[:6] == antes[:6], f'cambió algo más que el aula: {antes} -> {d}'

    # ════════════════════════════════ L
    @test("L — PUT que mueve una clase ENCIMA de otra del mismo profesor -> 409 y no cambia nada")
    def _():
        antes = _fila(A['hF'])
        n = _count_horarios()
        r = client.put(f"/api/horarios/{A['hF']}", json={'dia': 'Lunes', 'hora_inicio': '08:15', 'hora_fin': '09:00'}, headers=auth(DIR_A))
        assert r.status_code == 409, f'esperaba 409, obtuvo {r.status_code}: {r.text}'
        assert 'Conflicto de horario' in ((r.json() or {}).get('error') or '')
        assert _fila(A['hF']) == antes, f'el horario cambió pese al 409: {antes} -> {_fila(A["hF"])}'
        assert _count_horarios() == n, 'cambió el número de filas'

    # ════════════════════════════════ M
    @test("M — PUT que mueve una clase ENCIMA de otra del MISMO CURSO (otro profesor) -> 409 y no cambia nada")
    def _():
        # hM: misma cpH pero profesor distinto (profY) y día libre, para que el
        # choque sea SOLO de curso, no de profesor.
        hM = crear_ok(A['cpH'], A['profY'], 'Viernes', '10:00', '10:45')
        antes = _fila(hM)
        r = client.put(f"/api/horarios/{hM}", json={'dia': 'Lunes', 'hora_inicio': '10:15', 'hora_fin': '11:00'}, headers=auth(DIR_A))
        assert r.status_code == 409, f'esperaba 409, obtuvo {r.status_code}: {r.text}'
        assert 'este curso' in ((r.json() or {}).get('error') or ''), r.text
        assert _fila(hM) == antes, f'el horario cambió pese al 409: {antes} -> {_fila(hM)}'

    # ════════════════════════════════ N
    @test("N — aislamiento multi-tenant: un horario de OTRO colegio nunca cuenta como conflicto")
    def _():
        # Colegio B crea una clase idéntica en día/hora.
        rb = crear(Bc['cp'], Bc['prof'], 'Lunes', '08:00', '08:45', tok=DIR_B, asig=Bc['asig'])
        assert rb.status_code == 201, rb.text
        CREADOS[rb.json()['id']] = (Bc['prof'], Bc['cp'], 'Lunes', '08:00', '08:45', 'clase')
        # Colegio A crea la MISMA (día/hora) con su propio profesor Y libre en A:
        # debe pasar. Si B se colara, esto daría 409.
        n = _count_horarios()
        r = crear(A['cs'], A['profY'], 'Lunes', '08:00', '08:45')
        assert r.status_code == 201, f'un horario de otro colegio bloqueó la creación: {r.status_code} {r.text}'
        CREADOS[r.json()['id']] = (A['profY'], A['cs'], 'Lunes', '08:00', '08:45', 'clase')
        assert _count_horarios() == n + 1

    # ════════════════════════════════ O
    @test("O — ninguna validación eliminó ni modificó un horario existente")
    def _():
        d = SessionLocal()
        try:
            total_db = d.query(Horario).count()
        finally:
            d.close()
        assert total_db == len(CREADOS), f'filas en BD ({total_db}) != creadas con 201 ({len(CREADOS)})'
        for hid, esperado in CREADOS.items():
            f = _fila(hid)
            assert f is not None, f'el horario {hid} desapareció'
            assert f[:6] == esperado, f'el horario {hid} cambió: {esperado} -> {f[:6]}'
            assert f[6] is True or f[6] == 1, f'el horario {hid} quedó inactivo'

    # ════════════════════════════════ Profesor mixto (sección IMPORTANTE del encargo)
    @test("MIXTO — el mismo profesor asignado a Primaria Y Secundaria puede guardar clases en ambos niveles el mismo día si no se pisan; se pisa -> 409")
    def _():
        d = SessionLocal()
        try:
            asigns = {a.curso_id for a in d.query(AsignacionProfesor)
                      .filter_by(profesor_id=A['prof'], activo=True).all()}
        finally:
            d.close()
        assert {A['cp'], A['cs']}.issubset(asigns), f'el profesor mixto no está asignado a ambos niveles: {asigns}'
        # Día limpio para este profesor.
        crear_ok(A['cp'], A['prof'], 'Domingo', '08:00', '08:45')   # Primaria
        crear_ok(A['cs'], A['prof'], 'Domingo', '09:00', '09:45')   # Secundaria, sin solape -> OK
        crear_409(A['cs'], A['prof'], 'Domingo', '08:30', '09:15')  # Secundaria encima de Primaria -> 409


print(f"\n{B}{'=' * 64}{X}")
print(f"{B}  RESUMEN: {pasados}/{total} pruebas pasaron{X}")
print(f"{B}{'=' * 64}{X}")
if fallos:
    for n, e in fallos:
        print(f"{R}✗ {n}{X}\n    {e}")
    sys.exit(1)
print(f"{G}{B}🎉 CONFLICTOS DE HORARIO — VERDE{X}\n")
