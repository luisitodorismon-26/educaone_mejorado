# -*- coding: utf-8 -*-
"""
EducaOne R2.1C — mapeo curricular + API de selección de Indicadores de Logro.

Bloques:

  A. MAPEO  — `Asignatura.area_curricular_codigo`: columna nullable, migración
     aditiva sin backfill, validación contra el catálogo, RBAC y la protección
     histórica que impide cambiar el área de una asignatura que ya tiene
     indicadores registrados.

  B. MATERIAS FUERA DEL REGISTRO — una asignatura con el área en NULL (Música)
     sigue siendo normal en todo el sistema y recibe una respuesta CONTROLADA
     del catálogo, no un 500 ni una heurística por nombre.

  C. CATÁLOGO — derivado en servidor desde (curso, asignatura); nunca del
     cliente. Grado por `Grado.orden` con guardas.

  D. GUARDADO — atómico, múltiples IL/CE/CF, contenidos claves con orden
     exacto, estados, limpieza por período y convivencia con el legacy R2.

SEGURIDAD: SQLite temporal aislada. NUNCA toca sge.db ni INITIAL_CREDENTIALS.txt.

Uso:
    cd backend
    python tools/test_indicadores_ui_r21c.py
"""
import os
import sys
import atexit
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TMPDIR = tempfile.mkdtemp(prefix="eo_ind_ui_r21c_")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_TMPDIR, "u.db").replace("\\", "/")
os.environ.setdefault("ENVIRONMENT", "development")


@atexit.register
def _cleanup():
    try:
        import shutil
        shutil.rmtree(_TMPDIR, ignore_errors=True)
    except Exception:
        pass


from sqlalchemy import event, inspect as sa_inspect, text   # noqa: E402
from database import engine, SessionLocal                   # noqa: E402
import models as M                                          # noqa: E402
import catalogo_indicadores as CAT                          # noqa: E402

_eu = str(engine.url).replace("\\", "/")
assert _TMPDIR.replace("\\", "/") in _eu and "sge.db" not in _eu, _eu

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_SGE = os.path.join(_BACKEND, "sge.db")
_REPO_CRED = os.path.join(_BACKEND, "INITIAL_CREDENTIALS.txt")
_JSON = os.path.join(_BACKEND, "catalogos", "indicadores_secundaria_2023.json")
_sge_mtime = os.path.getmtime(_REPO_SGE) if os.path.exists(_REPO_SGE) else None
_cred_mtime = os.path.getmtime(_REPO_CRED) if os.path.exists(_REPO_CRED) else None
_json_mtime = os.path.getmtime(_JSON)


@event.listens_for(engine, "connect")
def _relax_fk(dbapi_conn, rec):
    try:
        dbapi_conn.execute("PRAGMA foreign_keys=OFF")
    except Exception:
        pass


engine.dispose()
M.Base.metadata.create_all(bind=engine)

from fastapi.testclient import TestClient                   # noqa: E402
from app import app                                         # noqa: E402

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


# ── IDs fijos ───────────────────────────────────────────────────────────
COL_A, COL_B = 1, 2
ANO_A, ANO_B = 1, 2
G4, G1, G_PRIM, G_MALO = 4, 1, 90, 91      # grados
C4, C1, C_PRIM, C_MALO, C_B = 40, 10, 70, 80, 30
LEF, LEI, MUSICA, MAT1, LEF_B = 101, 102, 103, 104, 201
U_DIR_A, U_PROF_A, U_COORD, U_DIR_B, U_PROF_B = 10, 11, 12, 13, 14
PWD = "Prueba2026x"

# Claves reales del catálogo
K_LEF4_A = "SEC-2023|4|LEF|CE01|IL01"
K_LEF4_B = "SEC-2023|4|LEF|CE01|IL02"
K_LEF4_C = "SEC-2023|4|LEF|CE03|IL01"     # otra CE -> otra Competencia Fundamental
K_LEF4_D = "SEC-2023|4|LEF|CE05|IL02"
K_LEF1 = "SEC-2023|1|LEF|CE01|IL01"       # otro GRADO
K_LEI4 = "SEC-2023|4|LEI|CE01|IL01"       # otra ÁREA
K_FALSA = "SEC-2023|4|LEF|CE99|IL99"


def _seed():
    M.Base.metadata.drop_all(bind=engine)
    M.Base.metadata.create_all(bind=engine)
    d = SessionLocal()
    try:
        for cid, nom, cod in ((COL_A, "Colegio A", "a"), (COL_B, "Colegio B", "b")):
            d.add(M.Colegio(id=cid, nombre=nom, codigo=cod))
            d.add(M.ConfiguracionColegio(colegio_id=cid, nombre=nom, regional="10",
                                         distrito="03", codigo_centro="0000%d" % cid,
                                         usa_secundaria=True))
        d.add(M.AnoEscolar(id=ANO_A, colegio_id=COL_A, nombre="2025-2026", activo=True, dias_trabajados="{}"))
        d.add(M.AnoEscolar(id=ANO_B, colegio_id=COL_B, nombre="2025-2026", activo=True, dias_trabajados="{}"))
        # Grados: orden es la fuente del número; primaria usa el rango 7-12.
        d.add(M.Grado(id=G4, colegio_id=COL_A, nombre="4to Secundaria", nivel="secundaria", orden=4))
        d.add(M.Grado(id=G1, colegio_id=COL_A, nombre="1ro Secundaria", nivel="secundaria", orden=1))
        d.add(M.Grado(id=G_PRIM, colegio_id=COL_A, nombre="4to Primaria", nivel="primaria", orden=10))
        # Grado incoherente: el nombre dice 5to pero el orden dice 2.
        d.add(M.Grado(id=G_MALO, colegio_id=COL_A, nombre="5to Secundaria", nivel="secundaria", orden=2))
        d.add(M.Grado(id=99, colegio_id=COL_B, nombre="4to Secundaria", nivel="secundaria", orden=4))

        d.add(M.Curso(id=C4, colegio_id=COL_A, nombre="A", grado_id=G4, ano_escolar_id=ANO_A))
        d.add(M.Curso(id=C1, colegio_id=COL_A, nombre="A", grado_id=G1, ano_escolar_id=ANO_A))
        d.add(M.Curso(id=C_PRIM, colegio_id=COL_A, nombre="P", grado_id=G_PRIM, ano_escolar_id=ANO_A))
        d.add(M.Curso(id=C_MALO, colegio_id=COL_A, nombre="X", grado_id=G_MALO, ano_escolar_id=ANO_A))
        d.add(M.Curso(id=C_B, colegio_id=COL_B, nombre="A", grado_id=99, ano_escolar_id=ANO_B))

        # Nombres y códigos DELIBERADAMENTE engañosos: si algo resolviera por
        # nombre/codigo/area, estos tests lo delatarían.
        d.add(M.Asignatura(id=LEF, colegio_id=COL_A, nombre="Frances", codigo="LE",
                           area="Lenguas", area_curricular_codigo="LEF"))
        d.add(M.Asignatura(id=LEI, colegio_id=COL_A, nombre="Inglés", codigo="LE",
                           area="Lenguas", area_curricular_codigo=None))
        d.add(M.Asignatura(id=MUSICA, colegio_id=COL_A, nombre="Musica", codigo="MS",
                           area="", area_curricular_codigo=None))
        d.add(M.Asignatura(id=MAT1, colegio_id=COL_A, nombre="Matemática", codigo="MA",
                           area="Matemática", area_curricular_codigo="MAT"))
        d.add(M.Asignatura(id=LEF_B, colegio_id=COL_B, nombre="Frances", codigo="LE",
                           area="Lenguas", area_curricular_codigo="LEF"))

        for uid, uname, rol, col in (
            (U_DIR_A, "dir_a", "direccion", COL_A),
            (U_PROF_A, "prof_a", "profesor", COL_A),
            (U_COORD, "coord_a", "coordinador", COL_A),
            (U_DIR_B, "dir_b", "direccion", COL_B),
            (U_PROF_B, "prof_b", "profesor", COL_A),
        ):
            u = M.Usuario(id=uid, username=uname, nombre=uname, apellido="T", role=rol, colegio_id=col)
            u.set_password(PWD)
            d.add(u)

        # prof_a: (C4, LEF), (C4, MUSICA), (C1, LEF), (C_PRIM, MAT1), (C_MALO, LEF)
        for i, (cu, asig) in enumerate(
            ((C4, LEF), (C4, MUSICA), (C1, LEF), (C_PRIM, MAT1), (C_MALO, LEF), (C4, LEI)), start=1
        ):
            d.add(M.AsignacionProfesor(id=i, colegio_id=COL_A, profesor_id=U_PROF_A,
                                       curso_id=cu, asignatura_id=asig, activo=True))
        # prof_b NO tiene ninguna asignación.
        d.add(M.AsignacionProfesor(id=20, colegio_id=COL_B, profesor_id=U_DIR_B,
                                   curso_id=C_B, asignatura_id=LEF_B, activo=True))
        d.commit()
    finally:
        d.close()


def login(u):
    r = client.post("/api/auth/login", json={"username": u, "password": PWD})
    assert r.status_code == 200, f"login {u}: {r.status_code} {r.text[:160]}"
    return r.json()["token"]


def auth(t):
    return {"Authorization": f"Bearer {t}"}


def cat(tok, curso_id, asignatura_id, **extra):
    p = {"curso_id": curso_id, "asignatura_id": asignatura_id}
    p.update(extra)
    return client.get("/api/indicadores-logro/catalogo", params=p, headers=auth(tok))


def guardar(tok, curso_id, asignatura_id, periodo, claves, contenidos=None):
    body = {"curso_id": curso_id, "asignatura_id": asignatura_id, "periodo": periodo,
            "catalogo_claves": claves}
    if contenidos is not None:
        body["contenidos_claves"] = contenidos
    return client.post("/api/indicadores-logro/periodo", json=body, headers=auth(tok))


def estado(tok, curso_id, asignatura_id):
    return client.get("/api/indicadores-logro",
                      params={"curso_id": curso_id, "asignatura_id": asignatura_id},
                      headers=auth(tok))


def n_selecciones():
    d = SessionLocal()
    try:
        return d.query(M.IndicadorLogroSeleccion).count()
    finally:
        d.close()


_seed()
DIR_A = login("dir_a")
PROF_A = login("prof_a")
COORD = login("coord_a")
DIR_B = login("dir_b")
PROF_B = login("prof_b")


# ===========================================================================
# BLOQUE A — MAPEO CURRICULAR
# ===========================================================================

@test("§A1 columna area_curricular_codigo: nullable, sin backfill")
def _():
    col = sa_inspect(M.Asignatura).columns["area_curricular_codigo"]
    assert col.nullable and col.type.length == 8, col
    fisico = {c["name"]: c for c in sa_inspect(engine).get_columns("asignaturas")}
    assert fisico["area_curricular_codigo"]["nullable"] is True
    # los campos legacy siguen intactos
    for legacy in ("nombre", "codigo", "area"):
        assert legacy in fisico


@test("§A2 migración idempotente y sin inferir valores desde nombre/codigo/area")
def _():
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS asignaturas_bak"))
        conn.execute(text(
            "CREATE TABLE asignaturas_bak AS SELECT id, colegio_id, nombre, codigo, area, activo "
            "FROM asignaturas"))
        conn.execute(text("DROP TABLE asignaturas"))
        conn.execute(text(
            "CREATE TABLE asignaturas (id INTEGER NOT NULL PRIMARY KEY, "
            "colegio_id INTEGER REFERENCES colegios(id), nombre VARCHAR(100) NOT NULL, "
            "codigo VARCHAR(10), area VARCHAR(50), activo BOOLEAN)"))
        conn.execute(text(
            "INSERT INTO asignaturas (id, colegio_id, nombre, codigo, area, activo) "
            "SELECT id, colegio_id, nombre, codigo, area, activo FROM asignaturas_bak"))
        conn.commit()
    antes = {c["name"] for c in sa_inspect(engine).get_columns("asignaturas")}
    assert "area_curricular_codigo" not in antes

    with TestClient(app):
        pass
    with TestClient(app):          # segundo arranque: idempotente
        pass

    with engine.connect() as conn:
        cols = {c["name"] for c in sa_inspect(engine).get_columns("asignaturas")}
        filas = list(conn.execute(text(
            "SELECT id, nombre, codigo, area, area_curricular_codigo FROM asignaturas ORDER BY id")))
    assert "area_curricular_codigo" in cols
    assert len(filas) == 5, filas
    # NINGÚN backfill: "Frances"/codigo LE/area "Lenguas" no produjo un valor
    assert all(f[4] is None for f in filas), filas
    # y los campos legacy no se tocaron
    assert [f[1] for f in filas] == ["Frances", "Inglés", "Musica", "Matemática", "Frances"]

    with engine.connect() as conn:   # restaurar el escenario de los tests
        conn.execute(text("DROP TABLE asignaturas_bak"))
        conn.commit()
    _seed()


@test("§A3 GET /api/asignaturas expone el área curricular y su nombre oficial")
def _():
    r = client.get("/api/asignaturas", headers=auth(DIR_A))
    assert r.status_code == 200, r.text
    por_id = {a["id"]: a for a in r.json()}
    assert por_id[LEF]["area_curricular_codigo"] == "LEF"
    assert por_id[LEF]["area_curricular_nombre"] == CAT.nombre_area("LEF")
    assert por_id[MUSICA]["area_curricular_codigo"] is None
    assert por_id[MUSICA]["area_curricular_nombre"] is None
    # los campos legacy siguen ahí
    assert por_id[LEF]["area"] == "Lenguas" and por_id[LEF]["codigo"] == "LE"


@test("§A4 las 9 áreas del selector salen del catálogo, no de una lista aparte")
def _():
    r = client.get("/api/asignaturas/areas-curriculares", headers=auth(DIR_A))
    assert r.status_code == 200, r.text
    codigos = [a["codigo"] for a in r.json()["areas"]]
    assert codigos == CAT.codigos_area_validos() == [
        "LE", "LEI", "LEF", "MAT", "CS", "CN", "EA", "EF", "FIHR"], codigos
    assert r.json()["version_curricular"] == "SEC-2023"


@test("§A5 Dirección configura el área; NULL y los 9 códigos son válidos")
def _():
    for codigo in CAT.codigos_area_validos():
        r = client.put(f"/api/asignaturas/{LEI}", json={"area_curricular_codigo": codigo},
                       headers=auth(DIR_A))
        assert r.status_code == 200, (codigo, r.text)
    r = client.put(f"/api/asignaturas/{LEI}", json={"area_curricular_codigo": None},
                   headers=auth(DIR_A))
    assert r.status_code == 200, r.text
    d = SessionLocal()
    try:
        assert d.query(M.Asignatura).get(LEI).area_curricular_codigo is None
    finally:
        d.close()


@test("§A6 un código desconocido —o un nombre— se rechaza con 400")
def _():
    for malo in ("Lenguas", "Inglés", "Francés", "XX", "le", "lef "):
        r = client.put(f"/api/asignaturas/{LEI}", json={"area_curricular_codigo": malo},
                       headers=auth(DIR_A))
        assert r.status_code == 400, (malo, r.status_code, r.text[:120])
        assert "desconocida" in r.json()["error"]


@test("§A7 RBAC: el profesor NO puede configurar el área; otro tenant tampoco")
def _():
    r = client.put(f"/api/asignaturas/{LEF}", json={"area_curricular_codigo": "LEI"},
                   headers=auth(PROF_A))
    assert r.status_code == 403, r.status_code
    r = client.put(f"/api/asignaturas/{LEF}", json={"area_curricular_codigo": "LEI"},
                   headers=auth(COORD))
    assert r.status_code == 403, r.status_code
    # IDOR: dirección del colegio B no ve ni toca una asignatura del colegio A
    r = client.put(f"/api/asignaturas/{LEF}", json={"area_curricular_codigo": "LEI"},
                   headers=auth(DIR_B))
    assert r.status_code == 404, r.status_code
    d = SessionLocal()
    try:
        assert d.query(M.Asignatura).get(LEF).area_curricular_codigo == "LEF"
    finally:
        d.close()


@test("§A8 NULL -> LEI permitido, y LEI -> LEF permitido SIN selecciones")
def _():
    r = client.put(f"/api/asignaturas/{LEI}", json={"area_curricular_codigo": "LEI"},
                   headers=auth(DIR_A))
    assert r.status_code == 200, r.text
    r = client.put(f"/api/asignaturas/{LEI}", json={"area_curricular_codigo": "LEF"},
                   headers=auth(DIR_A))
    assert r.status_code == 200, r.text
    r = client.put(f"/api/asignaturas/{LEI}", json={"area_curricular_codigo": None},
                   headers=auth(DIR_A))
    assert r.status_code == 200, r.text


# ===========================================================================
# BLOQUE C — CATÁLOGO (antes que la protección histórica: crea selecciones)
# ===========================================================================

@test("§C1 el catálogo se deriva del par curso+asignatura, filtrado a grado y área")
def _():
    r = cat(PROF_A, C4, LEF)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["grado_numero"] == 4 and d["area_codigo"] == "LEF"
    assert d["area_nombre"] == CAT.nombre_area("LEF")
    assert d["version"] == "SEC-2023"
    total = sum(len(ce["indicadores"]) for cf in d["competencias"]
                for ce in cf["competencias_especificas"])
    assert total == 21, total
    assert len(d["competencias"]) == 7, len(d["competencias"])
    # todas las claves son del grado y área correctos
    for cf in d["competencias"]:
        for ce in cf["competencias_especificas"]:
            for il in ce["indicadores"]:
                assert il["catalogo_clave"].startswith("SEC-2023|4|LEF|"), il


@test("§C2 el cliente NO puede imponer grado, área ni versión")
def _():
    r = cat(PROF_A, C4, LEF, grado=1, grado_numero=1, area="LEI",
            area_codigo="LEI", version="SEC-2099")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["grado_numero"] == 4 and d["area_codigo"] == "LEF" and d["version"] == "SEC-2023"


@test("§C3 el grado sale de Grado.orden; discrepancia orden/nombre = error explícito")
def _():
    r = cat(PROF_A, C_MALO, LEF)
    assert r.status_code == 400, r.status_code
    assert "incoherente" in r.json()["error"], r.json()


@test("§C4 primaria no puede consumir el catálogo de Secundaria")
def _():
    r = cat(PROF_A, C_PRIM, MAT1)
    assert r.status_code == 400, r.status_code
    assert "Secundario" in r.json()["error"] or "primaria" in r.json()["error"], r.json()


@test("§C5 RBAC/IDOR del catálogo")
def _():
    # profesor sin asignación al par
    assert cat(PROF_B, C4, LEF).status_code == 403
    # par no académico (C1, MAT1) -> 400
    assert cat(DIR_A, C1, MAT1).status_code == 400
    # otro tenant: el curso del colegio B no existe para el colegio A
    assert cat(DIR_A, C_B, LEF_B).status_code == 404
    assert cat(DIR_B, C4, LEF).status_code == 404
    # dirección y coordinación sí pueden ver el par académico
    assert cat(DIR_A, C4, LEF).status_code == 200
    assert cat(COORD, C4, LEF).status_code == 200


@test("§C6 el buscador acepta código y texto, y devuelve el contexto CF/CE")
def _():
    r = cat(PROF_A, C4, LEF, q="IL-19")
    assert r.status_code == 200, r.text
    d = r.json()
    encontrados = [(cf["competencia_fundamental_nombre"], ce["ce_codigo"], il["il_codigo"])
                   for cf in d["competencias"] for ce in cf["competencias_especificas"]
                   for il in ce["indicadores"]]
    assert encontrados and all(x[2] == "IL-19" for x in encontrados), encontrados
    assert all(x[0] and x[1] for x in encontrados), "falta el contexto CF/CE"
    # búsqueda por texto
    r2 = cat(PROF_A, C4, LEF, q="francés")
    assert r2.status_code == 200 and r2.json()["competencias"], r2.text
    # búsqueda sin coincidencias: 200 con lista vacía, no error
    r3 = cat(PROF_A, C4, LEF, q="zzzzzzzz")
    assert r3.status_code == 200 and r3.json()["competencias"] == []


@test("§C7 un il_codigo repetido devuelve VARIAS entradas con contexto distinto")
def _():
    # 6to Educación Física repite IL-7 en dos bandas (defecto del documento).
    varios = CAT.buscar_por_codigo("IL-7", grado=6, area="EF")
    assert len(varios) == 2, len(varios)
    assert {v["ce_codigo"] for v in varios} == {"CE-EF3", "CE-EF7"}
    assert len({v["catalogo_clave"] for v in varios}) == 2


# ===========================================================================
# BLOQUE D — GUARDADO
# ===========================================================================

@test("§D1 guarda varios IL de varias CE y Competencias Fundamentales")
def _():
    r = guardar(PROF_A, C4, LEF, 1, [K_LEF4_A, K_LEF4_B, K_LEF4_C, K_LEF4_D],
                "Personal pronouns\nPossessive pronouns")
    assert r.status_code == 200, r.text
    d = r.json()
    assert len(d["selecciones"]) == 4, d["selecciones"]
    assert d["estado"] == "completo", d["estado"]
    ces = {s["ce_codigo"] for s in d["selecciones"]}
    cfs = {s["competencia_fundamental_codigo"] for s in d["selecciones"]}
    assert len(ces) == 3, ces
    assert len(cfs) == 3, cfs
    # el texto oficial se resuelve desde el catálogo, no se guarda copia
    for s in d["selecciones"]:
        assert s["il_texto"] == CAT.resolver(s["catalogo_clave"])["il_texto"]


@test("§D2 una clave de otro grado, de otra área o inexistente se rechaza")
def _():
    for mala in (K_LEF1, K_LEI4, K_FALSA, "IL-19", ""):
        antes = n_selecciones()
        r = guardar(PROF_A, C4, LEF, 2, [K_LEF4_A, mala], "algo")
        assert r.status_code == 400, (mala, r.status_code, r.text[:120])
        assert n_selecciones() == antes, f"{mala!r} dejó residuo"


@test("§D3 ROLLBACK: si una clave falla no se guarda NADA del período")
def _():
    d = SessionLocal()
    try:
        antes = d.query(M.IndicadorLogro).filter_by(periodo=2, curso_id=C4).count()
    finally:
        d.close()
    r = guardar(PROF_A, C4, LEF, 2, [K_LEF4_A, K_LEI4], "no debe quedar")
    assert r.status_code == 400, r.text
    d = SessionLocal()
    try:
        assert d.query(M.IndicadorLogro).filter_by(periodo=2, curso_id=C4).count() == antes
    finally:
        d.close()


@test("§D4 el mismo IL puede usarse en P1 y P3; en el mismo período no se duplica")
def _():
    r = guardar(PROF_A, C4, LEF, 3, [K_LEF4_A], "Contenido P3")
    assert r.status_code == 200, r.text
    assert len(r.json()["selecciones"]) == 1
    # duplicado dentro del MISMO request: se ignora, no falla
    r2 = guardar(PROF_A, C4, LEF, 3, [K_LEF4_A, K_LEF4_A], "Contenido P3")
    assert r2.status_code == 200, r2.text
    assert len(r2.json()["selecciones"]) == 1, r2.json()["selecciones"]
    d = SessionLocal()
    try:
        n = (d.query(M.IndicadorLogroSeleccion)
             .filter_by(catalogo_clave=K_LEF4_A).count())
        assert n == 2, f"{n} filas de {K_LEF4_A} (P1 y P3)"
    finally:
        d.close()


@test("§D5 reemplazo ATÓMICO del conjunto de selecciones")
def _():
    r = guardar(PROF_A, C4, LEF, 1, [K_LEF4_C], "Personal pronouns\nPossessive pronouns")
    assert r.status_code == 200, r.text
    claves = {s["catalogo_clave"] for s in r.json()["selecciones"]}
    assert claves == {K_LEF4_C}, claves
    # restaurar el escenario de P1
    guardar(PROF_A, C4, LEF, 1, [K_LEF4_A, K_LEF4_B, K_LEF4_C, K_LEF4_D],
            "Personal pronouns\nPossessive pronouns")


@test("§D6 contenidos claves: orden exacto, unicode y espacios internos intactos")
def _():
    texto = ("Personal pronouns\n"
             "Possessive pronouns\n"
             "  Adjetivos   posesivos  \n"
             "\n"
             "Ñandú, café, señalización · 中文\n"
             "Sentences with possessive adjectives")
    r = guardar(PROF_A, C4, LEF, 4, [K_LEF4_A], texto)
    assert r.status_code == 200, r.text
    assert r.json()["contenidos_claves"] == texto, "se alteró el texto"
    d = SessionLocal()
    try:
        il = d.query(M.IndicadorLogro).filter_by(curso_id=C4, asignatura_id=LEF, periodo=4).first()
        assert il.lineas_contenidos_claves() == [
            "Personal pronouns", "Possessive pronouns", "  Adjetivos   posesivos  ",
            "Ñandú, café, señalización · 中文", "Sentences with possessive adjectives"]
    finally:
        d.close()


@test("§D7 guardado PARCIAL permitido y estados pendiente/parcial/completo")
def _():
    # solo indicadores
    r = guardar(DIR_A, C4, MAT1, 1, [], "")   # par no académico -> 400, no cuenta
    assert r.status_code == 400
    r = guardar(PROF_A, C1, LEF, 1, [K_LEF1], "")
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "parcial", r.json()["estado"]
    # solo contenidos
    r = guardar(PROF_A, C1, LEF, 2, [], "Solo contenidos")
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "parcial", r.json()["estado"]
    # ambos
    r = guardar(PROF_A, C1, LEF, 3, [K_LEF1], "Ambos")
    assert r.status_code == 200 and r.json()["estado"] == "completo"
    # ninguno
    r = guardar(PROF_A, C1, LEF, 4, [], "")
    assert r.status_code == 200 and r.json()["estado"] == "pendiente"


@test("§D8 GET de estado devuelve selecciones resueltas, contenidos y estado")
def _():
    r = estado(PROF_A, C4, LEF)
    assert r.status_code == 200, r.text
    por_periodo = {p["periodo"]: p for p in r.json()}
    assert set(por_periodo) >= {1, 3, 4}, list(por_periodo)
    p1 = por_periodo[1]
    assert len(p1["selecciones"]) == 4 and p1["estado"] == "completo"
    s = p1["selecciones"][0]
    for campo in ("catalogo_clave", "il_codigo", "il_texto", "ce_codigo", "ce_texto",
                  "competencia_fundamental_codigo", "competencia_fundamental_nombre"):
        assert campo in s, campo
    assert "contenido" in p1, "el campo legacy debe seguir presente por compatibilidad"


@test("§D9 'usado en otros períodos' es informativo y no bloquea")
def _():
    r = cat(PROF_A, C4, LEF)
    usados = r.json()["usado_en_periodos"]
    assert sorted(usados.get(K_LEF4_A, [])) == [1, 3, 4], usados.get(K_LEF4_A)
    # y se puede volver a seleccionar
    r2 = guardar(PROF_A, C4, LEF, 3, [K_LEF4_A, K_LEF4_B], "Contenido P3")
    assert r2.status_code == 200, r2.text


@test("§D10 cambiar de profesor NO borra las selecciones (continuidad institucional)")
def _():
    d = SessionLocal()
    try:
        il = d.query(M.IndicadorLogro).filter_by(curso_id=C4, asignatura_id=LEF, periodo=1).first()
        antes = sorted(s.catalogo_clave for s in il.selecciones)
        contenidos_antes = il.contenidos_claves
    finally:
        d.close()
    # dirección edita el mismo período: pasa a ser el último editor
    r = guardar(DIR_A, C4, LEF, 1, antes, contenidos_antes)
    assert r.status_code == 200, r.text
    d = SessionLocal()
    try:
        il = d.query(M.IndicadorLogro).filter_by(curso_id=C4, asignatura_id=LEF, periodo=1).first()
        assert il.profesor_id == U_DIR_A
        assert sorted(s.catalogo_clave for s in il.selecciones) == antes
        assert il.contenidos_claves == contenidos_antes
    finally:
        d.close()


@test("§D11 limpiar P3 no toca P1, P4 ni otras asignaturas")
def _():
    def foto():
        d = SessionLocal()
        try:
            return {(i.periodo, i.asignatura_id): (
                sorted(s.catalogo_clave for s in i.selecciones), i.contenidos_claves)
                for i in d.query(M.IndicadorLogro).filter_by(curso_id=C4).all()}
        finally:
            d.close()

    antes = foto()
    r = client.delete("/api/indicadores-logro/periodo",
                      params={"curso_id": C4, "asignatura_id": LEF, "periodo": 3},
                      headers=auth(PROF_A))
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "pendiente", r.json()
    despues = foto()
    assert despues[(3, LEF)] == ([], None), despues[(3, LEF)]
    for k, v in antes.items():
        if k != (3, LEF):
            assert despues[k] == v, f"limpiar P3 alteró {k}"


@test("§D12 el POST legacy no destruye las selecciones de R2.1")
def _():
    d = SessionLocal()
    try:
        il = d.query(M.IndicadorLogro).filter_by(curso_id=C4, asignatura_id=LEF, periodo=1).first()
        antes = sorted(s.catalogo_clave for s in il.selecciones)
    finally:
        d.close()
    r = client.post("/api/indicadores-logro",
                    json={"curso_id": C4, "asignatura_id": LEF, "periodo": 1,
                          "contenido": "texto legacy"}, headers=auth(DIR_A))
    assert r.status_code == 200, r.text
    d = SessionLocal()
    try:
        il = d.query(M.IndicadorLogro).filter_by(curso_id=C4, asignatura_id=LEF, periodo=1).first()
        assert sorted(s.catalogo_clave for s in il.selecciones) == antes, "el legacy borró selecciones"
        assert il.contenido == "texto legacy"
    finally:
        d.close()


@test("§D13 el DELETE legacy NO destruye un período con datos R2.1")
def _():
    d = SessionLocal()
    try:
        il = d.query(M.IndicadorLogro).filter_by(curso_id=C4, asignatura_id=LEF, periodo=1).first()
        il_id, antes = il.id, sorted(s.catalogo_clave for s in il.selecciones)
    finally:
        d.close()
    r = client.delete(f"/api/indicadores-logro/{il_id}", headers=auth(DIR_A))
    assert r.status_code == 409, (r.status_code, r.text[:160])
    assert r.json()["motivo"] == "periodo_con_datos_r21"
    d = SessionLocal()
    try:
        il = d.query(M.IndicadorLogro).get(il_id)
        assert il is not None, "el DELETE legacy borró el período"
        assert sorted(s.catalogo_clave for s in il.selecciones) == antes
    finally:
        d.close()


@test("§D14 limpiar un período con `contenido` legacy responde 409 y no borra")
def _():
    # P1 tiene 'texto legacy' desde §D12
    r = client.delete("/api/indicadores-logro/periodo",
                      params={"curso_id": C4, "asignatura_id": LEF, "periodo": 1},
                      headers=auth(DIR_A))
    assert r.status_code == 409, (r.status_code, r.text[:160])
    assert r.json()["motivo"] == "contenido_legacy_presente"
    d = SessionLocal()
    try:
        il = d.query(M.IndicadorLogro).filter_by(curso_id=C4, asignatura_id=LEF, periodo=1).first()
        assert il.contenido == "texto legacy" and len(il.selecciones) > 0
    finally:
        d.close()


@test("§D15 RBAC/IDOR del guardado")
def _():
    antes = n_selecciones()
    assert guardar(PROF_B, C4, LEF, 2, [K_LEF4_A]).status_code == 403
    assert guardar(DIR_B, C4, LEF, 2, [K_LEF4_A]).status_code == 404
    assert client.post("/api/indicadores-logro/periodo",
                       json={"curso_id": C4, "asignatura_id": LEF, "periodo": 2,
                             "catalogo_claves": [K_LEF4_A]}).status_code in (401, 403)
    assert n_selecciones() == antes


# ===========================================================================
# BLOQUE B — MATERIAS FUERA DEL REGISTRO (Música)
# ===========================================================================

@test("§B1 Música (área NULL) sigue siendo una asignatura normal")
def _():
    r = client.get("/api/asignaturas", headers=auth(DIR_A))
    m = [a for a in r.json() if a["id"] == MUSICA]
    assert m and m[0]["area_curricular_codigo"] is None, m
    d = SessionLocal()
    try:
        assert d.query(M.Asignatura).get(MUSICA).activo is not False
        # conserva su asignación de profesor
        n = d.query(M.AsignacionProfesor).filter_by(asignatura_id=MUSICA, activo=True).count()
        assert n == 1, n
    finally:
        d.close()


@test("§B2 el catálogo responde de forma CONTROLADA (409), no 500 ni heurística")
def _():
    r = cat(PROF_A, C4, MUSICA)
    assert r.status_code == 409, (r.status_code, r.text[:160])
    d = r.json()
    assert d["motivo"] == "sin_vinculo_curricular", d
    assert "no está vinculada a un área curricular" in d["error"], d["error"]
    assert d["puede_configurar"] is False        # prof_a no es dirección
    r2 = cat(DIR_A, C4, MUSICA)
    assert r2.status_code == 409 and r2.json()["puede_configurar"] is True


@test("§B3 una materia sin vínculo NO recibe indicadores de otra materia")
def _():
    antes = n_selecciones()
    r = guardar(PROF_A, C4, MUSICA, 1, [K_LEF4_A], "algo")
    assert r.status_code == 409, (r.status_code, r.text[:140])
    assert r.json()["motivo"] == "sin_vinculo_curricular"
    assert n_selecciones() == antes
    # y su GET de estado no falla
    assert estado(PROF_A, C4, MUSICA).status_code == 200


@test("§B4 la resolución NO usa nombre, codigo ni area")
def _():
    # LEF se llama "Frances", tiene codigo "LE" y area "Lenguas": si algo
    # resolviera por esos campos, daría LE (Lengua Española), no LEF.
    d = SessionLocal()
    try:
        a = d.query(M.Asignatura).get(LEF)
        assert (a.nombre, a.codigo, a.area) == ("Frances", "LE", "Lenguas")
    finally:
        d.close()
    assert cat(PROF_A, C4, LEF).json()["area_codigo"] == "LEF"

    # La función que resuelve el área NO lee ningún otro atributo de la
    # asignatura. (`grado.nombre` sí se lee en la resolución del GRADO, pero
    # solo como alarma de coherencia; eso se cubre en §C3.)
    import ast
    import indicadores_curriculares as IC
    fuente = open(os.path.join(_BACKEND, "indicadores_curriculares.py"), encoding="utf-8").read()
    fn = next(n for n in ast.parse(fuente).body
              if isinstance(n, ast.FunctionDef) and n.name == "area_de_asignatura")
    leidos = {a.value for a in ast.walk(fn)
              if isinstance(a, ast.Constant) and isinstance(a.value, str)}
    assert "area_curricular_codigo" in leidos, leidos
    for prohibido in ("nombre", "codigo", "area"):
        assert prohibido not in leidos, f"area_de_asignatura toca {prohibido!r}"
    assert not [a for a in ast.walk(fn) if isinstance(a, ast.Attribute)
                and a.attr in ("nombre", "codigo", "area")]

    # Y con una asignatura cuyos tres campos legacy apuntan a otra área, la
    # resolución sigue devolviendo la correcta.
    d = SessionLocal()
    try:
        ok, ctx, _ = IC.area_de_asignatura(d.query(M.Asignatura).get(LEF))
        assert ok and ctx == "LEF", ctx
    finally:
        d.close()


# ===========================================================================
# BLOQUE A (cont.) — PROTECCIÓN HISTÓRICA (requiere selecciones ya creadas)
# ===========================================================================

@test("§A9 con selecciones: LEF -> otra área se bloquea con 409 y no borra nada")
def _():
    antes = n_selecciones()
    assert antes > 0, "el escenario necesita selecciones"
    r = client.put(f"/api/asignaturas/{LEF}", json={"area_curricular_codigo": "LEI"},
                   headers=auth(DIR_A))
    assert r.status_code == 409, (r.status_code, r.text[:160])
    d = r.json()
    assert d["area_curricular_actual"] == "LEF" and d["area_curricular_solicitada"] == "LEI"
    assert d["selecciones_existentes"] > 0
    assert n_selecciones() == antes, "el 409 borró selecciones"
    dd = SessionLocal()
    try:
        assert dd.query(M.Asignatura).get(LEF).area_curricular_codigo == "LEF"
    finally:
        dd.close()


@test("§A10 con selecciones: LEF -> NULL también se bloquea con 409")
def _():
    antes = n_selecciones()
    r = client.put(f"/api/asignaturas/{LEF}", json={"area_curricular_codigo": None},
                   headers=auth(DIR_A))
    assert r.status_code == 409, (r.status_code, r.text[:160])
    assert n_selecciones() == antes
    d = SessionLocal()
    try:
        assert d.query(M.Asignatura).get(LEF).area_curricular_codigo == "LEF"
    finally:
        d.close()


@test("§A11 editar otros campos de una asignatura con selecciones sigue permitido")
def _():
    r = client.put(f"/api/asignaturas/{LEF}",
                   json={"nombre": "Francés", "area": "Idiomas modernos"},
                   headers=auth(DIR_A))
    assert r.status_code == 200, r.text
    d = SessionLocal()
    try:
        a = d.query(M.Asignatura).get(LEF)
        assert a.nombre == "Francés" and a.area == "Idiomas modernos"
        assert a.area_curricular_codigo == "LEF", "no debía cambiar"
    finally:
        d.close()
    # y el catálogo sigue resolviendo por el código, no por el nombre nuevo
    assert cat(PROF_A, C4, LEF).json()["area_codigo"] == "LEF"


# ===========================================================================
# BLOQUE E — UN SOLO BLOQUE OFICIAL POR CURSO
# ===========================================================================
#
# Dos asignaturas institucionales DISTINTAS activas en el mismo curso no pueden
# representar el mismo bloque del Registro: R2.1D no sabría cuál imprimir.

ING_CONV = 105          # "Inglés Conversacional": segunda asignatura mapeada a LEI
EXTRA_NULL = 106        # materia adicional sin vínculo
PROF_C = 15


def _preparar_colision():
    """LEI en dos asignaturas distintas del curso C4; LEF solo en una."""
    d = SessionLocal()
    try:
        if d.query(M.Asignatura).get(ING_CONV) is None:
            d.add(M.Asignatura(id=ING_CONV, colegio_id=COL_A, nombre="Inglés Conversacional",
                               codigo="INC", area="Lenguas", area_curricular_codigo="LEI"))
            d.add(M.Asignatura(id=EXTRA_NULL, colegio_id=COL_A, nombre="Robótica",
                               codigo="RB", area="", area_curricular_codigo=None))
            u = M.Usuario(id=PROF_C, username="prof_c", nombre="prof_c", apellido="T",
                          role="profesor", colegio_id=COL_A)
            u.set_password(PWD)
            d.add(u)
            # LEI original queda vinculada, para provocar la colisión en C4
            d.query(M.Asignatura).get(LEI).area_curricular_codigo = "LEI"
            # ambas activas en C4, y también un segundo profesor sobre LEI
            d.add(M.AsignacionProfesor(id=30, colegio_id=COL_A, profesor_id=U_PROF_A,
                                       curso_id=C4, asignatura_id=ING_CONV, activo=True))
            d.add(M.AsignacionProfesor(id=31, colegio_id=COL_A, profesor_id=PROF_C,
                                       curso_id=C4, asignatura_id=LEI, activo=True))
            d.add(M.AsignacionProfesor(id=32, colegio_id=COL_A, profesor_id=U_PROF_A,
                                       curso_id=C4, asignatura_id=EXTRA_NULL, activo=True))
            # En C1 solo hay UNA asignatura LEI: el mismo código, otro curso.
            d.add(M.AsignacionProfesor(id=33, colegio_id=COL_A, profesor_id=U_PROF_A,
                                       curso_id=C1, asignatura_id=ING_CONV, activo=True))
            d.commit()
    finally:
        d.close()


_preparar_colision()
PROF_C_TOK = login("prof_c")


@test("§E1 dos asignaturas LEI en el mismo curso: el catálogo responde 409")
def _():
    r = cat(PROF_A, C4, LEI)
    assert r.status_code == 409, (r.status_code, r.text[:180])
    d = r.json()
    assert d["motivo"] == "bloque_curricular_duplicado", d
    assert d["area_codigo"] == "LEI"
    ids = {a["id"] for a in d["asignaturas_en_conflicto"]}
    assert ids == {LEI, ING_CONV}, ids
    assert "más de una asignatura vinculada al bloque" in d["error"]
    # simétrico: da igual por cuál de las dos se pregunte
    r2 = cat(PROF_A, C4, ING_CONV)
    assert r2.status_code == 409 and r2.json()["motivo"] == "bloque_curricular_duplicado"


@test("§E2 con colisión el guardado también se rechaza con 409")
def _():
    antes = n_selecciones()
    r = guardar(PROF_A, C4, LEI, 1, [K_LEI4], "algo")
    assert r.status_code == 409, (r.status_code, r.text[:180])
    assert r.json()["motivo"] == "bloque_curricular_duplicado"
    assert n_selecciones() == antes


@test("§E3 varios profesores sobre la MISMA asignatura NO son colisión")
def _():
    d = SessionLocal()
    try:
        n = (d.query(M.AsignacionProfesor)
             .filter_by(curso_id=C4, asignatura_id=LEI, activo=True).count())
        assert n == 2, f"el escenario necesita 2 profesores sobre LEI, hay {n}"
    finally:
        d.close()
    # LEF sigue teniendo una sola asignatura en C4 pese a tener 1 profesor
    assert cat(PROF_A, C4, LEF).status_code == 200
    # y la colisión de LEI viene de asignatura_id distintos, no de los profesores
    d = SessionLocal()
    try:
        import indicadores_curriculares as IC
        curso = d.query(M.Curso).get(C4)
        otras = IC.colision_bloque_en_curso(d, curso, d.query(M.Asignatura).get(LEF), "LEF")
        assert otras == [], otras
    finally:
        d.close()


@test("§E4 el mismo bloque en CURSOS distintos está permitido")
def _():
    # ING_CONV (LEI) también está activa en C1, donde es la única con ese bloque
    r = cat(PROF_A, C1, ING_CONV)
    assert r.status_code == 200, (r.status_code, r.text[:180])
    assert r.json()["area_codigo"] == "LEI" and r.json()["grado_numero"] == 1
    # la guarda es POR CURSO: no hay unicidad global de Asignatura
    d = SessionLocal()
    try:
        n = (d.query(M.Asignatura)
             .filter_by(colegio_id=COL_A, area_curricular_codigo="LEI").count())
        assert n == 2, f"{n} asignaturas LEI en el colegio (deben poder coexistir)"
    finally:
        d.close()


@test("§E5 una materia adicional (NULL) no participa en la colisión")
def _():
    d = SessionLocal()
    try:
        import indicadores_curriculares as IC
        curso = d.query(M.Curso).get(C4)
        # Robótica está activa en C4 con área NULL: no colisiona con nada
        otras = IC.colision_bloque_en_curso(d, curso, d.query(M.Asignatura).get(EXTRA_NULL), None)
        assert otras == [], otras
    finally:
        d.close()
    r = cat(PROF_A, C4, EXTRA_NULL)
    assert r.status_code == 409 and r.json()["motivo"] == "sin_vinculo_curricular", r.text[:160]


@test("§E6 bloques DISTINTOS en el mismo curso conviven sin problema")
def _():
    # C4 tiene LEF (Frances) y LEI (dos asignaturas): LEF sigue funcionando
    r = cat(PROF_A, C4, LEF)
    assert r.status_code == 200, r.text[:160]
    assert r.json()["area_codigo"] == "LEF"
    assert guardar(PROF_A, C4, LEF, 2, [K_LEF4_B], "sigue funcionando").status_code == 200


@test("§E7 ante la colisión no se crea ni modifica ningún IndicadorLogro")
def _():
    def foto():
        d = SessionLocal()
        try:
            return {(i.curso_id, i.asignatura_id, i.periodo):
                    (sorted(s.catalogo_clave for s in i.selecciones), i.contenidos_claves)
                    for i in d.query(M.IndicadorLogro).all()}
        finally:
            d.close()

    antes = foto()
    for periodo in (1, 2, 3, 4):
        r = guardar(PROF_A, C4, LEI, periodo, [K_LEI4], "no debe quedar")
        assert r.status_code == 409, (periodo, r.status_code)
    assert foto() == antes, "la colisión alteró datos existentes"


@test("§E8 al desvincular una de las dos, el bloque vuelve a resolver")
def _():
    r = client.put(f"/api/asignaturas/{ING_CONV}", json={"area_curricular_codigo": None},
                   headers=auth(DIR_A))
    assert r.status_code == 200, r.text          # no tiene selecciones: se permite
    r2 = cat(PROF_A, C4, LEI)
    assert r2.status_code == 200, (r2.status_code, r2.text[:180])
    assert r2.json()["area_codigo"] == "LEI" and r2.json()["grado_numero"] == 4
    assert guardar(PROF_A, C4, LEI, 1, [K_LEI4], "ahora sí").status_code == 200
    # se restaura la colisión para no dejar el escenario alterado
    d = SessionLocal()
    try:
        d.query(M.Asignatura).get(ING_CONV).area_curricular_codigo = "LEI"
        d.commit()
    finally:
        d.close()


@test("§Z ZERO DATA LOSS: sge.db, credenciales y catálogo intactos")
def _():
    a = os.path.getmtime(_REPO_SGE) if os.path.exists(_REPO_SGE) else None
    b = os.path.getmtime(_REPO_CRED) if os.path.exists(_REPO_CRED) else None
    assert a == _sge_mtime, "sge.db fue modificado"
    assert b == _cred_mtime, "INITIAL_CREDENTIALS.txt fue modificado"
    assert os.path.getmtime(_JSON) == _json_mtime, "la suite modificó el catálogo"
    assert _TMPDIR.replace("\\", "/") in str(engine.url).replace("\\", "/")


print(f"\n{B}{'=' * 64}{X}")
print(f"{B}RESULTADO R2.1C: {_ok}/{_total} pruebas{X}")
if _fail:
    print(f"{R}FALLARON:{X}")
    for n, e in _fail:
        print(f"  - {n}: {e}")
    sys.exit(1)
print(f"{G}TODO VERDE{X}")
