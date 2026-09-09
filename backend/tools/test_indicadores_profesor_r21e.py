# -*- coding: utf-8 -*-
"""
EducaOne R2.1E — Indicadores solo-profesor + autovinculación curricular.

Bloques:

  A. ROLES    — los seis endpoints de Indicadores son professor-only; dirección
     y coordinación reciben 403. El dato sigue siendo institucional: un profesor
     de reemplazo con asignación activa continúa el historial.

  B. ALIAS    — la inferencia es EXACTA tras normalizar. Los 10 nombres
     oficiales se vinculan; los ambiguos se quedan en NULL.

  C. ALTA     — POST /api/asignaturas infiere solo si no se indicó área.

  D. BACKFILL — idempotente, solo sobre NULL, sin tocar mappings existentes,
     nombres, códigos legacy, selecciones ni contenidos, y sin autovincular
     cuando provocaría una colisión de bloque en un curso.

  E. FRONTEND — sidebar y router restringidos a profesor.

SEGURIDAD: SQLite temporal aislada. NUNCA toca sge.db ni INITIAL_CREDENTIALS.txt.

Uso:
    cd backend
    python tools/test_indicadores_profesor_r21e.py
"""
import os
import re
import sys
import atexit
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TMPDIR = tempfile.mkdtemp(prefix="eo_r21e_")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_TMPDIR, "e.db").replace("\\", "/")
os.environ.setdefault("ENVIRONMENT", "development")


@atexit.register
def _cleanup():
    try:
        import shutil
        shutil.rmtree(_TMPDIR, ignore_errors=True)
    except Exception:
        pass


from sqlalchemy import event                                   # noqa: E402
from database import engine, SessionLocal                      # noqa: E402
import models as M                                             # noqa: E402
from area_curricular_autovinculo import (                      # noqa: E402
    ALIAS, autovincular_existentes, inferir_area, normalizar,
)

_eu = str(engine.url).replace("\\", "/")
assert _TMPDIR.replace("\\", "/") in _eu and "sge.db" not in _eu, _eu

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FRONT = os.path.join(os.path.dirname(_BACKEND), "frontend", "src")
_REPO_SGE = os.path.join(_BACKEND, "sge.db")
_REPO_CRED = os.path.join(_BACKEND, "INITIAL_CREDENTIALS.txt")
_sge = os.path.getmtime(_REPO_SGE) if os.path.exists(_REPO_SGE) else None
_cred = os.path.getmtime(_REPO_CRED) if os.path.exists(_REPO_CRED) else None


@event.listens_for(engine, "connect")
def _relax_fk(dbapi_conn, rec):
    try:
        dbapi_conn.execute("PRAGMA foreign_keys=OFF")
    except Exception:
        pass


engine.dispose()
M.Base.metadata.create_all(bind=engine)

from fastapi.testclient import TestClient                      # noqa: E402
from app import app                                            # noqa: E402

client = TestClient(app)

G, R, B, C, X = "\033[92m", "\033[91m", "\033[1m", "\033[96m", "\033[0m"
_fail, _ok, _total = [], 0, 0


def test(nombre):
    def deco(fn):
        global _total, _ok
        _total += 1
        print(f"\n{C}▶ {nombre}{X}")
        try:
            fn()
            _ok += 1
            print(f"  {G}✓ PASÓ{X}")
        except Exception as e:
            import traceback
            _fail.append((nombre, str(e)))
            print(f"  {R}✗ FALLÓ: {e}{X}")
            traceback.print_exc()
        return fn
    return deco


COL, ANO, G4, C4, C5 = 1, 1, 4, 40, 41
LEF, ING, MUSICA, ING2, MAT = 101, 102, 103, 104, 105
U_DIR, U_PROF, U_PROF2, U_COORD = 10, 11, 12, 13
PWD = "Prueba2026x"
K1 = "SEC-2023|4|LEF|CE01|IL01"


def _seed():
    M.Base.metadata.drop_all(bind=engine)
    M.Base.metadata.create_all(bind=engine)
    d = SessionLocal()
    try:
        d.add(M.Colegio(id=COL, nombre="Colegio A", codigo="a"))
        d.add(M.ConfiguracionColegio(colegio_id=COL, nombre="Colegio A", regional="10",
                                     distrito="03", codigo_centro="00001", usa_secundaria=True))
        d.add(M.AnoEscolar(id=ANO, colegio_id=COL, nombre="2025-2026", activo=True,
                           dias_trabajados="{}"))
        d.add(M.Grado(id=G4, colegio_id=COL, nombre="4to Secundaria", nivel="secundaria", orden=4))
        d.add(M.Curso(id=C4, colegio_id=COL, nombre="A", grado_id=G4, ano_escolar_id=ANO))
        d.add(M.Curso(id=C5, colegio_id=COL, nombre="B", grado_id=G4, ano_escolar_id=ANO))
        # LEF ya vinculada a mano: el backfill NO debe tocarla.
        d.add(M.Asignatura(id=LEF, colegio_id=COL, nombre="Frances", codigo="LE",
                           area="Lenguas", area_curricular_codigo="LEF"))
        # Oficiales sin vincular: candidatas al autovínculo.
        d.add(M.Asignatura(id=ING, colegio_id=COL, nombre="Inglés", codigo="IN",
                           area="Lenguas", area_curricular_codigo=None))
        d.add(M.Asignatura(id=MAT, colegio_id=COL, nombre="Matemática", codigo="MA",
                           area="Matemática", area_curricular_codigo=None))
        # Ambiguas: deben quedarse en NULL.
        d.add(M.Asignatura(id=MUSICA, colegio_id=COL, nombre="Música", codigo="MS",
                           area="", area_curricular_codigo=None))
        d.add(M.Asignatura(id=ING2, colegio_id=COL, nombre="Inglés Conversacional",
                           codigo="INC", area="Lenguas", area_curricular_codigo=None))
        for uid, un, rol in ((U_DIR, "dir_a", "direccion"), (U_PROF, "prof_a", "profesor"),
                             (U_PROF2, "prof_b", "profesor"), (U_COORD, "coord_a", "coordinador")):
            u = M.Usuario(id=uid, username=un, nombre=un, apellido="T", role=rol, colegio_id=COL)
            u.set_password(PWD)
            d.add(u)
        i = 1
        for cu, asig in ((C4, LEF), (C4, ING), (C4, MUSICA), (C4, ING2), (C4, MAT)):
            d.add(M.AsignacionProfesor(id=i, colegio_id=COL, profesor_id=U_PROF,
                                       curso_id=cu, asignatura_id=asig, activo=True))
            i += 1
        d.commit()
    finally:
        d.close()


def login(u):
    r = client.post("/api/auth/login", json={"username": u, "password": PWD})
    assert r.status_code == 200, f"login {u}: {r.status_code} {r.text[:160]}"
    return r.json()["token"]


def auth(t):
    return {"Authorization": f"Bearer {t}"}


_seed()
DIR = login("dir_a")
PROF = login("prof_a")
PROF2 = login("prof_b")
COORD = login("coord_a")


# ===========================================================================
# BLOQUE A — ROLES
# ===========================================================================

def _peticiones(tok):
    """Las seis operaciones interactivas de Indicadores."""
    a = auth(tok)
    return [
        ("GET catálogo", client.get("/api/indicadores-logro/catalogo",
                                    params={"curso_id": C4, "asignatura_id": LEF}, headers=a)),
        ("GET estado", client.get("/api/indicadores-logro",
                                  params={"curso_id": C4, "asignatura_id": LEF}, headers=a)),
        ("POST legacy", client.post("/api/indicadores-logro",
                                    json={"curso_id": C4, "asignatura_id": LEF,
                                          "periodo": 1, "contenido": "x"}, headers=a)),
        ("POST período", client.post("/api/indicadores-logro/periodo",
                                     json={"curso_id": C4, "asignatura_id": LEF, "periodo": 1,
                                           "catalogo_claves": [K1]}, headers=a)),
        ("DELETE período", client.delete("/api/indicadores-logro/periodo",
                                         params={"curso_id": C4, "asignatura_id": LEF,
                                                 "periodo": 1}, headers=a)),
        ("DELETE legacy", client.delete("/api/indicadores-logro/1", headers=a)),
    ]


@test("§A1 dirección recibe 403 en las SEIS operaciones")
def _():
    for nombre, r in _peticiones(DIR):
        assert r.status_code == 403, f"{nombre}: {r.status_code} {r.text[:110]}"


@test("§A2 coordinación recibe 403 en las SEIS operaciones")
def _():
    for nombre, r in _peticiones(COORD):
        assert r.status_code == 403, f"{nombre}: {r.status_code} {r.text[:110]}"


@test("§A3 el profesor con asignación activa SÍ puede trabajar")
def _():
    r = client.get("/api/indicadores-logro/catalogo",
                   params={"curso_id": C4, "asignatura_id": LEF}, headers=auth(PROF))
    assert r.status_code == 200, r.text[:160]
    r = client.post("/api/indicadores-logro/periodo",
                    json={"curso_id": C4, "asignatura_id": LEF, "periodo": 1,
                          "catalogo_claves": [K1], "contenidos_claves": "Uno"},
                    headers=auth(PROF))
    assert r.status_code == 200, r.text[:200]
    assert len(r.json()["selecciones"]) == 1


@test("§A4 un profesor SIN asignación al par no puede escribir ni ve datos ajenos")
def _():
    por_nombre = dict(_peticiones(PROF2))
    # Escrituras y el catálogo del par: 403 explícito.
    for nombre in ("GET catálogo", "POST legacy", "POST período", "DELETE período"):
        r = por_nombre[nombre]
        assert r.status_code == 403, f"{nombre}: {r.status_code} {r.text[:110]}"
    # El GET de estado es un LISTADO acotado por `filtrar_por_asignacion_activa`:
    # devuelve 200 con lista vacía en vez de 403. No es una fuga —no se ve ni un
    # dato del par ajeno— y es la semántica que ya tenía en R2.
    r = por_nombre["GET estado"]
    assert r.status_code == 200 and r.json() == [], (r.status_code, r.text[:120])


@test("§A5 profesor de reemplazo con asignación activa CONTINÚA el historial")
def _():
    d = SessionLocal()
    try:
        # el titular sale, entra prof_b sobre el mismo par
        d.query(M.AsignacionProfesor).filter_by(curso_id=C4, asignatura_id=LEF).update(
            {"activo": False})
        d.add(M.AsignacionProfesor(id=90, colegio_id=COL, profesor_id=U_PROF2,
                                   curso_id=C4, asignatura_id=LEF, activo=True))
        d.commit()
    finally:
        d.close()
    r = client.get("/api/indicadores-logro",
                   params={"curso_id": C4, "asignatura_id": LEF}, headers=auth(PROF2))
    assert r.status_code == 200, r.text[:160]
    p1 = [p for p in r.json() if p["periodo"] == 1]
    assert p1 and len(p1[0]["selecciones"]) == 1, "el reemplazo no ve el historial"
    # y puede continuarlo
    r = client.post("/api/indicadores-logro/periodo",
                    json={"curso_id": C4, "asignatura_id": LEF, "periodo": 1,
                          "catalogo_claves": [K1], "contenidos_claves": "Uno\nDos"},
                    headers=auth(PROF2))
    assert r.status_code == 200, r.text[:200]
    # el titular saliente ya no puede
    assert client.get("/api/indicadores-logro/catalogo",
                      params={"curso_id": C4, "asignatura_id": LEF},
                      headers=auth(PROF)).status_code == 403
    d = SessionLocal()
    try:                                   # restaurar el escenario
        d.query(M.AsignacionProfesor).filter_by(id=90).update({"activo": False})
        d.query(M.AsignacionProfesor).filter_by(
            curso_id=C4, asignatura_id=LEF, profesor_id=U_PROF).update({"activo": True})
        d.commit()
    finally:
        d.close()


# ===========================================================================
# BLOQUE B — ALIAS
# ===========================================================================

@test("§B1 los 10 nombres oficiales se infieren correctamente")
def _():
    esperado = {
        "Lengua Española": "LE",
        "Inglés": "LEI", "Ingles": "LEI",
        "Francés": "LEF", "Frances": "LEF",
        "Matemática": "MAT", "Matematica": "MAT",
        "Matemáticas": "MAT", "Matematicas": "MAT",
        "Ciencias Sociales": "CS",
        "Ciencias Naturales": "CN",
        "Educación Artística": "EA", "Educacion Artistica": "EA",
        "Educación Física": "EF", "Educacion Fisica": "EF",
        "Formación Integral Humana y Religiosa": "FIHR",
        "Formacion Integral Humana y Religiosa": "FIHR",
        "Formación Humana": "FIHR", "Formacion Humana": "FIHR",
    }
    for nombre, codigo in esperado.items():
        assert inferir_area(nombre) == codigo, (nombre, inferir_area(nombre))
    assert len(set(esperado.values())) == 9, "deben cubrirse los 9 bloques"


@test("§B2 la normalización tolera mayúsculas, acentos y espacios; nada más")
def _():
    for variante in ("INGLES", "inglés", "  Inglés  ", "InGlEs", "Inglés"):
        assert inferir_area(variante) == "LEI", variante
    assert normalizar("  Educación   Física ") == "educacion fisica"


@test("§B3 NEGATIVOS: los nombres ambiguos NO se autovinculan")
def _():
    for nombre in ("Inglés Conversacional", "Taller de Inglés", "Matemática Financiera",
                   "Música", "Musica", "Arte", "English", "Science", "Religión",
                   "Ingles I", "Lengua", "Ciencias", "", "   ", None):
        assert inferir_area(nombre) is None, nombre


@test("§B4 no hay fuzzy: solo coincidencia exacta tras normalizar")
def _():
    import ast
    # Se compara el CÓDIGO, no la documentación: el docstring del módulo
    # menciona `startswith` precisamente para prohibirlo.
    ruta = os.path.join(_BACKEND, "area_curricular_autovinculo.py")
    arbol = ast.parse(open(ruta, encoding="utf-8").read())
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.Module, ast.ClassDef, ast.FunctionDef)):
            cuerpo = nodo.body
            if (cuerpo and isinstance(cuerpo[0], ast.Expr)
                    and isinstance(cuerpo[0].value, ast.Constant)
                    and isinstance(cuerpo[0].value.value, str)):
                nodo.body = cuerpo[1:] or [ast.Pass()]
    codigo = ast.dump(arbol).lower()
    for prohibido in ("startswith", "endswith", "difflib", "sequencematcher",
                      "fuzz", "levenshtein", "re.search", "re.match"):
        assert prohibido not in codigo, prohibido
    # ninguna importación de librerías de similitud
    importados = {n.names[0].name for n in ast.walk(arbol)
                  if isinstance(n, ast.Import)}
    assert not (importados & {"difflib", "rapidfuzz", "fuzzywuzzy", "re"}), importados
    # El lookup es un dict de coincidencia exacta. Son 11 claves y no 19 alias
    # porque las variantes con y sin acento colapsan al normalizar —"Inglés" e
    # "Ingles" son la misma clave—, que es exactamente el objetivo.
    assert isinstance(ALIAS, dict) and len(ALIAS) == 11, len(ALIAS)
    assert set(ALIAS.values()) == {"LE", "LEI", "LEF", "MAT", "CS",
                                   "CN", "EA", "EF", "FIHR"}, set(ALIAS.values())
    assert ALIAS[normalizar("Inglés")] == ALIAS[normalizar("Ingles")] == "LEI"


# ===========================================================================
# BLOQUE C — ALTA DE ASIGNATURAS
# ===========================================================================

@test("§C1 crear 'Inglés' sin área la vincula sola a LEI")
def _():
    r = client.post("/api/asignaturas", json={"nombre": "Inglés"}, headers=auth(DIR))
    assert r.status_code == 201, r.text[:160]
    nueva = r.json()["id"]
    d = SessionLocal()
    try:
        assert d.query(M.Asignatura).get(nueva).area_curricular_codigo == "LEI"
    finally:
        d.close()


@test("§C2 crear 'Inglés Conversacional' la deja en NULL")
def _():
    r = client.post("/api/asignaturas", json={"nombre": "Inglés Conversacional"},
                    headers=auth(DIR))
    assert r.status_code == 201, r.text[:160]
    d = SessionLocal()
    try:
        assert d.query(M.Asignatura).get(r.json()["id"]).area_curricular_codigo is None
    finally:
        d.close()


def _area_de(asig_id):
    d = SessionLocal()
    try:
        return d.query(M.Asignatura).get(asig_id).area_curricular_codigo
    finally:
        d.close()


@test("§C3 un área explícita GANA sobre la inferencia")
def _():
    # "Inglés" inferiría LEI, pero Dirección dijo LEF: manda Dirección.
    r = client.post("/api/asignaturas",
                    json={"nombre": "Inglés", "area_curricular_codigo": "LEF"},
                    headers=auth(DIR))
    assert r.status_code == 201, r.text[:160]
    assert _area_de(r.json()["id"]) == "LEF"


@test("§C4 'Inglés' con area_curricular_codigo=null SÍ se autovincula a LEI")
def _():
    # Configuración → Asignaturas manda SIEMPRE la clave, y con `null` cuando el
    # selector quedó vacío (`asignaturaForm.area_curricular_codigo || null`).
    # Ese `null` significa "no elegí área", no "desvincular": en un alta no hay
    # nada que desvincular. Si el alta no infiriera aquí, R2.1E no serviría para
    # las asignaturas creadas desde la UI, que son todas.
    r = client.post("/api/asignaturas",
                    json={"nombre": "Inglés", "codigo": "IN", "area": "Lenguas",
                          "area_curricular_codigo": None},
                    headers=auth(DIR))
    assert r.status_code == 201, r.text[:160]
    assert _area_de(r.json()["id"]) == "LEI"


@test("§C5 'Matemática' con area_curricular_codigo=null se autovincula a MAT")
def _():
    r = client.post("/api/asignaturas",
                    json={"nombre": "Matemática", "codigo": "MA", "area": "Matemática",
                          "area_curricular_codigo": None},
                    headers=auth(DIR))
    assert r.status_code == 201, r.text[:160]
    assert _area_de(r.json()["id"]) == "MAT"


@test("§C6 'Música' con area_curricular_codigo=null sigue en NULL")
def _():
    # No hay alias oficial para Música: NULL es su estado correcto, no un fallo.
    r = client.post("/api/asignaturas",
                    json={"nombre": "Música", "codigo": "MS", "area": "",
                          "area_curricular_codigo": None},
                    headers=auth(DIR))
    assert r.status_code == 201, r.text[:160]
    assert _area_de(r.json()["id"]) is None
    # y el string vacío se comporta igual que el null
    r = client.post("/api/asignaturas",
                    json={"nombre": "Taller de Inglés", "area_curricular_codigo": ""},
                    headers=auth(DIR))
    assert r.status_code == 201, r.text[:160]
    assert _area_de(r.json()["id"]) is None


@test("§C7 el PUT NO infiere: sigue siendo la vía manual de Dirección")
def _():
    # Frontera deliberada. En el alta, `null` = "no elegí". En la edición, `null`
    # = "desvincular", y debe poder desvincularse una materia cuyo nombre sí
    # tiene alias: si el PUT infiriera, Dirección no podría sacar del Registro
    # una asignatura llamada "Inglés" —el sistema se la volvería a poner.
    r = client.post("/api/asignaturas", json={"nombre": "Inglés"}, headers=auth(DIR))
    assert r.status_code == 201, r.text[:160]
    aid = r.json()["id"]
    assert _area_de(aid) == "LEI", "el alta debería haber autovinculado"

    r = client.put(f"/api/asignaturas/{aid}",
                   json={"nombre": "Inglés", "codigo": "IN", "area": "Lenguas",
                         "area_curricular_codigo": None},
                   headers=auth(DIR))
    assert r.status_code == 200, r.text[:200]
    assert _area_de(aid) is None, "el PUT no debe reinferir desde el nombre"


# ===========================================================================
# BLOQUE D — BACKFILL
# ===========================================================================

@test("§D1 el backfill vincula solo las oficiales y respeta lo demás")
def _():
    _seed()
    d = SessionLocal()
    try:
        res = autovincular_existentes(d)
        assert res["vinculadas"] == 2, res          # Inglés y Matemática
        assert d.query(M.Asignatura).get(ING).area_curricular_codigo == "LEI"
        assert d.query(M.Asignatura).get(MAT).area_curricular_codigo == "MAT"
        assert d.query(M.Asignatura).get(MUSICA).area_curricular_codigo is None
        assert d.query(M.Asignatura).get(ING2).area_curricular_codigo is None
        # mapping preexistente intacto
        assert d.query(M.Asignatura).get(LEF).area_curricular_codigo == "LEF"
        # nombres, códigos legacy y `area` sin tocar
        a = d.query(M.Asignatura).get(ING)
        assert (a.nombre, a.codigo, a.area) == ("Inglés", "IN", "Lenguas")
    finally:
        d.close()


@test("§D2 es IDEMPOTENTE: la segunda pasada no cambia nada")
def _():
    d = SessionLocal()
    try:
        antes = {a.id: a.area_curricular_codigo for a in d.query(M.Asignatura).all()}
        res = autovincular_existentes(d)
        assert res["vinculadas"] == 0, res
        despues = {a.id: a.area_curricular_codigo for a in d.query(M.Asignatura).all()}
        assert antes == despues
    finally:
        d.close()


@test("§D3 NO toca un mapping existente aunque el nombre sugiera otro bloque")
def _():
    d = SessionLocal()
    try:
        # 'Frances' está vinculada a LEF a mano; el alias diría LEF igualmente,
        # pero se fuerza a CS para comprobar que el backfill NO la reescribe.
        d.query(M.Asignatura).filter_by(id=LEF).update({"area_curricular_codigo": "CS"})
        d.commit()
        autovincular_existentes(d)
        assert d.query(M.Asignatura).get(LEF).area_curricular_codigo == "CS"
        d.query(M.Asignatura).filter_by(id=LEF).update({"area_curricular_codigo": "LEF"})
        d.commit()
    finally:
        d.close()


@test("§D4 COLISIÓN en el mismo curso: no autovincula, deja NULL")
def _():
    _seed()
    d = SessionLocal()
    try:
        # otra asignatura del MISMO curso ya ocupa LEI
        d.add(M.Asignatura(id=200, colegio_id=COL, nombre="Idioma Extranjero",
                           codigo="IE", area="Lenguas", area_curricular_codigo="LEI"))
        d.add(M.AsignacionProfesor(id=60, colegio_id=COL, profesor_id=U_PROF,
                                   curso_id=C4, asignatura_id=200, activo=True))
        d.commit()
        res = autovincular_existentes(d)
        assert res["colisiones"] >= 1, res
        assert d.query(M.Asignatura).get(ING).area_curricular_codigo is None, \
            "autovinculó pese a la colisión"
        assert d.query(M.Asignatura).get(200).area_curricular_codigo == "LEI"
        # Matemática, sin colisión, sí se vincula
        assert d.query(M.Asignatura).get(MAT).area_curricular_codigo == "MAT"
    finally:
        d.close()


@test("§D5 la misma asignatura con DOS profesores no es colisión")
def _():
    _seed()
    d = SessionLocal()
    try:
        d.add(M.AsignacionProfesor(id=61, colegio_id=COL, profesor_id=U_PROF2,
                                   curso_id=C4, asignatura_id=ING, activo=True))
        d.commit()
        res = autovincular_existentes(d)
        assert res["colisiones"] == 0, res
        assert d.query(M.Asignatura).get(ING).area_curricular_codigo == "LEI"
    finally:
        d.close()


@test("§D6 el mismo bloque en CURSOS distintos sí se permite")
def _():
    _seed()
    d = SessionLocal()
    try:
        # otra asignatura con LEI, pero en el curso C5, donde 'Inglés' no está
        d.add(M.Asignatura(id=201, colegio_id=COL, nombre="Idioma Extranjero",
                           codigo="IE", area="Lenguas", area_curricular_codigo="LEI"))
        d.add(M.AsignacionProfesor(id=62, colegio_id=COL, profesor_id=U_PROF,
                                   curso_id=C5, asignatura_id=201, activo=True))
        d.commit()
        res = autovincular_existentes(d)
        assert res["colisiones"] == 0, res
        assert d.query(M.Asignatura).get(ING).area_curricular_codigo == "LEI"
    finally:
        d.close()


@test("§D7 el backfill NO toca selecciones ni contenidos existentes")
def _():
    _seed()
    d = SessionLocal()
    try:
        il = M.IndicadorLogro(colegio_id=COL, profesor_id=U_PROF, asignatura_id=LEF,
                              curso_id=C4, ano_escolar_id=ANO, periodo=1,
                              contenidos_claves="Uno\nDos")
        d.add(il)
        d.commit()
        d.add(M.IndicadorLogroSeleccion(indicador_logro_id=il.id, catalogo_clave=K1))
        d.commit()
        il_id = il.id
        autovincular_existentes(d)
        il = d.query(M.IndicadorLogro).get(il_id)
        assert il.contenidos_claves == "Uno\nDos"
        assert [s.catalogo_clave for s in il.selecciones] == [K1]
    finally:
        d.close()


@test("§D8 una materia que queda NULL sigue fuera del Registro")
def _():
    from app import _cargar_especificacion_curricular
    d = SessionLocal()
    try:
        autovincular_existentes(d)

        class _U:
            colegio_id, role, id = COL, 'direccion', U_DIR
            nivel_asignado = None
        espec = _cargar_especificacion_curricular(d, _U(), d.query(M.Curso).get(C4), 4)
        # Música e Inglés Conversacional siguen sin bloque
        assert d.query(M.Asignatura).get(MUSICA).area_curricular_codigo is None
        assert d.query(M.Asignatura).get(ING2).area_curricular_codigo is None
        # y el Registro resuelve por area_curricular_codigo, no por nombre
        for slot, periodos in espec.items():
            for datos in periodos.values():
                assert datos["asignatura_id"] not in (MUSICA, ING2), datos
    finally:
        d.close()


# ===========================================================================
# BLOQUE E — FRONTEND
# ===========================================================================

@test("§E1 sidebar y router restringen /indicadores-logro a profesor")
def _():
    layout = open(os.path.join(_FRONT, "components", "layout", "MainLayout.tsx"),
                  encoding="utf-8").read()
    linea = [l for l in layout.splitlines() if "'/indicadores-logro'" in l]
    assert len(linea) == 1, linea
    assert "roles: ['profesor']" in linea[0], linea[0]

    router = open(os.path.join(_FRONT, "Router.tsx"), encoding="utf-8").read()
    m = re.search(r'path="/indicadores-logro"\s+element=\{\s*(?:\{/\*.*?\*/\}\s*)?'
                  r'<ProtectedRoute roles=\{\[([^\]]*)\]\}', router, re.S)
    assert m, "no se encontró la ruta protegida"
    assert m.group(1).strip() == "'profesor'", m.group(1)
    # el Registro Escolar sigue disponible para dirección
    reg = [l for l in layout.splitlines() if "'/registro-escolar'" in l]
    assert reg and "direccion" in reg[0], reg


@test("§E2 el mensaje al profesor no lo manda a Configuración")
def _():
    pagina = open(os.path.join(_FRONT, "pages", "indicadores-logro",
                               "IndicadoresLogroPage.tsx"), encoding="utf-8").read()
    assert "comunícalo a Dirección" in pagina
    assert "Configuración → Asignaturas" not in pagina
    # el selector manual de Dirección se conserva como respaldo
    config = open(os.path.join(_FRONT, "pages", "configuracion",
                               "ConfiguracionPage.tsx"), encoding="utf-8").read()
    assert "Área curricular MINERD" in config


@test("§Z ZERO DATA LOSS: sge.db e INITIAL_CREDENTIALS.txt intactos")
def _():
    a = os.path.getmtime(_REPO_SGE) if os.path.exists(_REPO_SGE) else None
    b = os.path.getmtime(_REPO_CRED) if os.path.exists(_REPO_CRED) else None
    assert a == _sge, "sge.db fue modificado"
    assert b == _cred, "INITIAL_CREDENTIALS.txt fue modificado"
    assert _TMPDIR.replace("\\", "/") in str(engine.url).replace("\\", "/")


print(f"\n{B}{'=' * 64}{X}")
print(f"{B}RESULTADO R2.1E: {_ok}/{_total} pruebas{X}")
if _fail:
    print(f"{R}FALLARON:{X}")
    for n, e in _fail:
        print(f"  - {n}: {e}")
    sys.exit(1)
print(f"{G}TODO VERDE{X}")
