# -*- coding: utf-8 -*-
"""
EducaOne R2 — Indicadores de Logro institucionales → Registro Escolar Secundaria.

Cubre de extremo a extremo:
  API   : identidad institucional (colegio+año+curso+asignatura+período),
          continuidad al cambiar de profesor, RBAC por pareja EXACTA,
          aislamiento por año y por tenant.
  PDF   : se escriben en la columna "Indicadores de Logro" de la tabla
          "ESPECIFICACIÓN CURRICULAR APLICADA POR PERÍODO" (una página por
          asignatura y período), sin invadir la grilla, sin inventar texto.

SEGURIDAD DE DATOS: SQLite temporal aislada creada ANTES de importar
database/models/app. NUNCA toca sge.db, INITIAL_CREDENTIALS.txt ni archivos reales.

Uso:
    cd backend
    python tools/test_indicadores_logro_r2.py
"""
import io
import os
import sys
import atexit
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TMPDIR = tempfile.mkdtemp(prefix="eo_indicadores_r2_")
_TEST_DB_URL = "sqlite:///" + os.path.join(_TMPDIR, "r2.db").replace("\\", "/")
os.environ["DATABASE_URL"] = _TEST_DB_URL
os.environ.setdefault("ENVIRONMENT", "development")


@atexit.register
def _cleanup():
    try:
        import shutil
        shutil.rmtree(_TMPDIR, ignore_errors=True)
    except Exception:
        pass


from pypdf import PdfReader                                    # noqa: E402
from reportlab.pdfbase.pdfmetrics import stringWidth           # noqa: E402
from sqlalchemy import event                                   # noqa: E402
from database import engine, SessionLocal                      # noqa: E402
import models as M                                             # noqa: E402

from registro_escolar import (                                 # noqa: E402
    generar_registro_desde_sistema, draw_indicadores, _create_overlay_page,
    _wrap_texto, pagina_indicador, INDICADOR_BOX,
    INDICADORES_P1_CICLO_1, INDICADORES_P1_CICLO_2,
    ASIGNATURAS_CICLO_1, ASIGNATURAS_CICLO_2, FONT_NORMAL,
)

_eu = str(engine.url).replace("\\", "/")
assert _TMPDIR.replace("\\", "/") in _eu and "sge.db" not in _eu, _eu
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_SGE = os.path.join(_BACKEND, "sge.db")
_REPO_CREDS = os.path.join(_BACKEND, "INITIAL_CREDENTIALS.txt")
_sge_mtime = os.path.getmtime(_REPO_SGE) if os.path.exists(_REPO_SGE) else None
_creds_mtime = os.path.getmtime(_REPO_CREDS) if os.path.exists(_REPO_CREDS) else None


@event.listens_for(engine, "connect")
def _relax_fk(dbapi_conn, rec):
    try:
        dbapi_conn.execute("PRAGMA foreign_keys=OFF")
    except Exception:
        pass


engine.dispose()
M.Base.metadata.create_all(bind=engine)

from fastapi.testclient import TestClient                       # noqa: E402
from app import app                                             # noqa: E402

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


# ── IDs fijos ────────────────────────────────────────────────────────────
COL_A, COL_B = 1, 2
ANO_A, ANO_A_PREV, ANO_B = 1, 2, 3
GRADO_A, GRADO_B = 1, 2
C1, C2, C3 = 1, 2, 3                     # C1/C2 -> colegio A ; C3 -> colegio B
C4_PRIM, C5_PREV = 4, 5                  # C4 = primaria (colegio A) ; C5 = año anterior
GRADO_PRIM = 3
U_COORD_SEC, U_PROF_X = 14, 15
MAT, LEN, MAT_B = 101, 102, 201
U_DIR_A, U_PROF_A, U_PROF_B, U_DIR_B = 10, 11, 12, 13
PWD = "Prueba2026x"


def _seed():
    M.Base.metadata.drop_all(bind=engine)
    M.Base.metadata.create_all(bind=engine)
    d = SessionLocal()
    try:
        d.add(M.Colegio(id=COL_A, nombre="Colegio A", codigo="a"))
        d.add(M.Colegio(id=COL_B, nombre="Colegio B", codigo="b"))
        d.add(M.ConfiguracionColegio(colegio_id=COL_A, nombre="Colegio A", regional="10",
                                     distrito="03", codigo_centro="00001", usa_secundaria=True))
        d.add(M.ConfiguracionColegio(colegio_id=COL_B, nombre="Colegio B", regional="10",
                                     distrito="03", codigo_centro="00002", usa_secundaria=True))
        d.add(M.AnoEscolar(id=ANO_A, colegio_id=COL_A, nombre="2025-2026", activo=True, dias_trabajados="{}"))
        d.add(M.AnoEscolar(id=ANO_A_PREV, colegio_id=COL_A, nombre="2024-2025", activo=False, dias_trabajados="{}"))
        d.add(M.AnoEscolar(id=ANO_B, colegio_id=COL_B, nombre="2025-2026", activo=True, dias_trabajados="{}"))
        d.add(M.Grado(id=GRADO_A, colegio_id=COL_A, nombre="1ro Secundaria", nivel="secundaria"))
        d.add(M.Grado(id=GRADO_B, colegio_id=COL_B, nombre="1ro Secundaria", nivel="secundaria"))
        d.add(M.Grado(id=GRADO_PRIM, colegio_id=COL_A, nombre="4to Primaria", nivel="primaria"))
        # Los cursos SÍ pertenecen a un año escolar (así es en producción).
        d.add(M.Curso(id=C1, colegio_id=COL_A, nombre="A", grado_id=GRADO_A, ano_escolar_id=ANO_A))
        d.add(M.Curso(id=C2, colegio_id=COL_A, nombre="B", grado_id=GRADO_A, ano_escolar_id=ANO_A))
        d.add(M.Curso(id=C3, colegio_id=COL_B, nombre="A", grado_id=GRADO_B, ano_escolar_id=ANO_B))
        d.add(M.Curso(id=C4_PRIM, colegio_id=COL_A, nombre="P", grado_id=GRADO_PRIM, ano_escolar_id=ANO_A))
        d.add(M.Curso(id=C5_PREV, colegio_id=COL_A, nombre="C", grado_id=GRADO_A, ano_escolar_id=ANO_A_PREV))
        d.add(M.Asignatura(id=MAT, colegio_id=COL_A, nombre="Matemática"))
        d.add(M.Asignatura(id=LEN, colegio_id=COL_A, nombre="Lengua Española"))
        d.add(M.Asignatura(id=MAT_B, colegio_id=COL_B, nombre="Matemática"))
        for uid, uname, rol, col in (
            (U_DIR_A, "dir_a", "direccion", COL_A),
            (U_PROF_A, "prof_a", "profesor", COL_A),
            (U_PROF_B, "prof_b", "profesor", COL_A),
            (U_DIR_B, "dir_b", "direccion", COL_B),
            (U_COORD_SEC, "coord_sec", "coordinador", COL_A),
            (U_PROF_X, "prof_x", "profesor", COL_A),
        ):
            u = M.Usuario(id=uid, username=uname, nombre=uname, apellido="T", role=rol, colegio_id=col)
            if uname == "coord_sec":
                u.nivel_asignado = "secundaria"      # lente FIJO
            u.set_password(PWD)
            d.add(u)
        # Profesor A: asignación ACTIVA a (C1, MAT). Nada más.
        d.add(M.AsignacionProfesor(id=1, colegio_id=COL_A, profesor_id=U_PROF_A,
                                   curso_id=C1, asignatura_id=MAT, activo=True, es_titular=True))
        # prof_x: asignación REAL cruzando niveles (secundaria C1/LEN + primaria C4/MAT)
        d.add(M.AsignacionProfesor(id=3, colegio_id=COL_A, profesor_id=U_PROF_X,
                                   curso_id=C1, asignatura_id=LEN, activo=True))
        d.add(M.AsignacionProfesor(id=4, colegio_id=COL_A, profesor_id=U_PROF_X,
                                   curso_id=C4_PRIM, asignatura_id=MAT, activo=True))
        d.commit()
    finally:
        d.close()


def login(u):
    r = client.post("/api/auth/login", json={"username": u, "password": PWD})
    assert r.status_code == 200, f"login {u}: {r.status_code} {r.text[:160]}"
    return r.json()["token"]


def auth(t):
    return {"Authorization": f"Bearer {t}"}


def get_ind(tok, **params):
    return client.get("/api/indicadores-logro", params=params, headers=auth(tok))


def post_ind(tok, curso_id, asignatura_id, periodo, contenido, **extra):
    body = {"curso_id": curso_id, "asignatura_id": asignatura_id,
            "periodo": periodo, "contenido": contenido}
    body.update(extra)
    return client.post("/api/indicadores-logro", json=body, headers=auth(tok))


def _filas(db_filter=None):
    d = SessionLocal()
    try:
        q = d.query(M.IndicadorLogro)
        return q.all() if db_filter is None else q.filter_by(**db_filter).all()
    finally:
        d.close()


_seed()
DIR_A = login("dir_a")
PROF_A = login("prof_a")
PROF_B = login("prof_b")
DIR_B = login("dir_b")
COORD_SEC = login("coord_sec")
PROF_X = login("prof_x")
print(f"{G}✓ DB de test AISLADA:{X} {_eu}")


# ═══════════════════════════════════════════════════════════════════════════
# PARTE 1 — API: identidad institucional, RBAC, tenant, año
# ═══════════════════════════════════════════════════════════════════════════
@test("§3 profesor SIN asignación exacta (curso, asignatura) → 403 al guardar")
def _():
    # prof_a solo tiene (C1, MAT). (C1, LEN) y (C2, MAT) NO.
    assert post_ind(PROF_A, C1, LEN, 1, "x").status_code == 403
    assert post_ind(PROF_A, C2, MAT, 1, "x").status_code == 403


@test("§4 profesor CON asignación exacta → guarda (201) y lo ve en el listado")
def _():
    r = post_ind(PROF_A, C1, MAT, 1, "IL-1 Expresa sus ideas por escrito.")
    assert r.status_code == 201, r.text
    lst = get_ind(PROF_A, curso_id=C1, asignatura_id=MAT).json()
    assert len(lst) == 1 and lst[0]["periodo"] == 1, lst
    assert lst[0]["contenido"].startswith("IL-1"), lst
    assert lst[0]["ano_escolar_id"] == ANO_A, lst


@test("§7 P1 y P2 coexisten como filas distintas")
def _():
    assert post_ind(PROF_A, C1, MAT, 2, "IL-5 Comprende textos expositivos.").status_code == 201
    lst = get_ind(PROF_A, curso_id=C1, asignatura_id=MAT).json()
    assert {i["periodo"] for i in lst} == {1, 2}, lst
    assert len(_filas({"curso_id": C1, "asignatura_id": MAT, "ano_escolar_id": ANO_A})) == 2


@test("§5 cambio de docente: Profesor B recibe la asignación y VE el indicador de A")
def _():
    d = SessionLocal()
    try:
        vieja = d.query(M.AsignacionProfesor).filter_by(profesor_id=U_PROF_A, curso_id=C1,
                                                        asignatura_id=MAT).first()
        vieja.activo = False
        d.add(M.AsignacionProfesor(id=2, colegio_id=COL_A, profesor_id=U_PROF_B,
                                   curso_id=C1, asignatura_id=MAT, activo=True))
        d.commit()
    finally:
        d.close()
    lst = get_ind(PROF_B, curso_id=C1, asignatura_id=MAT).json()
    assert {i["periodo"] for i in lst} == {1, 2}, lst
    assert lst[0]["contenido"].startswith("IL-1"), lst
    # y el profesor A, ya sin asignación activa, deja de verlo
    assert get_ind(PROF_A, curso_id=C1, asignatura_id=MAT).json() == []


@test("§6 Profesor B guarda P1: ACTUALIZA el registro institucional, NO duplica")
def _():
    antes = _filas({"curso_id": C1, "asignatura_id": MAT, "ano_escolar_id": ANO_A, "periodo": 1})
    assert len(antes) == 1
    id_antes, autor_antes = antes[0].id, antes[0].profesor_id
    r = post_ind(PROF_B, C1, MAT, 1, "IL-1 (continuado por el nuevo docente)")
    assert r.status_code == 200, r.text
    despues = _filas({"curso_id": C1, "asignatura_id": MAT, "ano_escolar_id": ANO_A, "periodo": 1})
    assert len(despues) == 1, f"se duplicó el indicador institucional: {len(despues)} filas"
    assert despues[0].id == id_antes, "cambió el id: se creó otra fila"
    assert despues[0].contenido.endswith("nuevo docente)")
    assert autor_antes == U_PROF_A and despues[0].profesor_id == U_PROF_B, "no se registró el último editor"


@test("§8 un curso de OTRO año escolar tiene su propio indicador, sin colisionar")
def _():
    # C5 pertenece al año anterior. El default sigue siendo el año ACTIVO, así
    # que escribir en un año histórico exige pedirlo EXPLÍCITAMENTE.
    r = post_ind(DIR_A, C5_PREV, MAT, 1, "Indicador del año anterior")
    assert r.status_code == 400, "sin ano_escolar_id explícito debe rechazarse"
    r = post_ind(DIR_A, C5_PREV, MAT, 1, "Indicador del año anterior",
                 ano_escolar_id=ANO_A_PREV)
    assert r.status_code == 201, r.text
    filas = _filas({"asignatura_id": MAT, "periodo": 1})
    anios = {f.ano_escolar_id for f in filas}
    assert {ANO_A, ANO_A_PREV}.issubset(anios), anios
    assert len(_filas({"curso_id": C5_PREV, "asignatura_id": MAT, "periodo": 1})) == 1


@test("§1 el indicador de un año NO aparece en el listado de otro año")
def _():
    actual = get_ind(DIR_A, curso_id=C1, asignatura_id=MAT).json()          # año activo
    previo = get_ind(DIR_A, curso_id=C5_PREV, asignatura_id=MAT,
                     ano_escolar_id=ANO_A_PREV).json()
    assert all(i["ano_escolar_id"] == ANO_A for i in actual), actual
    assert all(i["ano_escolar_id"] == ANO_A_PREV for i in previo), previo
    assert not any(i["contenido"] == "Indicador del año anterior" for i in actual)
    assert len(previo) == 1 and previo[0]["contenido"] == "Indicador del año anterior"
    # el listado del año ACTIVO no muestra el curso del año anterior
    assert get_ind(DIR_A, curso_id=C5_PREV, asignatura_id=MAT).json() == []


@test("§2 tenant: Colegio B no lee NADA del Colegio A (ni por id directo)")
def _():
    assert get_ind(DIR_B, curso_id=C1, asignatura_id=MAT).json() == []
    assert get_ind(DIR_B).json() == []
    ajeno = _filas({"curso_id": C1, "asignatura_id": MAT, "ano_escolar_id": ANO_A, "periodo": 1})[0]
    r = client.delete(f"/api/indicadores-logro/{ajeno.id}", headers=auth(DIR_B))
    assert r.status_code == 404, f"IDOR: {r.status_code}"
    assert _filas({"curso_id": C1, "asignatura_id": MAT, "ano_escolar_id": ANO_A, "periodo": 1}), "se borró un dato ajeno"


VACIO_MIXTO = " " + chr(10) + chr(9) + " "


@test("§H1 POST vacío JAMÁS borra: sin fila = no-op; con fila = 400 y dato intacto")
def _():
    # (a) vacío sobre par sin indicador -> no crea basura
    n0 = len(_filas())
    r = post_ind(DIR_A, C1, LEN, 3, "   ")
    assert r.status_code == 200 and r.json().get("id") is None, r.text
    assert len(_filas()) == n0, "se creó una fila con contenido vacío"

    # (b) vacío sobre uno EXISTENTE -> 400, y la fila queda INTACTA
    assert post_ind(DIR_A, C1, LEN, 3, "contenido original").status_code == 201
    antes = _filas({"curso_id": C1, "asignatura_id": LEN, "periodo": 3})
    assert len(antes) == 1
    id_antes, texto_antes = antes[0].id, antes[0].contenido
    for vacio in ("", "   ", VACIO_MIXTO):
        r = post_ind(DIR_A, C1, LEN, 3, vacio)
        assert r.status_code == 400, f"POST vacío devolvió {r.status_code}: {r.text[:120]}"
        assert "Eliminar" in r.json().get("error", ""), r.json()
    despues = _filas({"curso_id": C1, "asignatura_id": LEN, "periodo": 3})
    assert len(despues) == 1, "el POST vacío borró la fila"
    assert despues[0].id == id_antes and despues[0].contenido == texto_antes, "se alteró el contenido"

    # (c) la ÚNICA vía de borrado es DELETE explícito
    r = client.delete(f"/api/indicadores-logro/{id_antes}", headers=auth(DIR_A))
    assert r.status_code == 200, r.text
    assert _filas({"curso_id": C1, "asignatura_id": LEN, "periodo": 3}) == []


@test("§R2-extra DELETE: profesor sin asignación activa exacta → 403; con ella → 200")
def _():
    assert post_ind(DIR_A, C1, LEN, 4, "para borrar").status_code == 201
    fila = _filas({"curso_id": C1, "asignatura_id": LEN, "periodo": 4})[0]
    # prof_b solo tiene (C1, MAT), no (C1, LEN)
    assert client.delete(f"/api/indicadores-logro/{fila.id}", headers=auth(PROF_B)).status_code == 403
    assert _filas({"curso_id": C1, "asignatura_id": LEN, "periodo": 4}), "se borró pese al 403"
    assert client.delete(f"/api/indicadores-logro/{fila.id}", headers=auth(DIR_A)).status_code == 200
    assert _filas({"curso_id": C1, "asignatura_id": LEN, "periodo": 4}) == []


@test("§R2-extra validaciones: período fuera de 1-4 → 400; texto > límite → 400")
def _():
    assert post_ind(DIR_A, C1, MAT, 5, "x").status_code == 400
    assert post_ind(DIR_A, C1, MAT, 0, "x").status_code == 400
    from app import INDICADOR_LOGRO_MAX_CHARS as LIM
    assert post_ind(DIR_A, C1, MAT, 4, "a" * (LIM + 1)).status_code == 400
    assert post_ind(DIR_A, C1, MAT, 4, "a" * LIM).status_code == 201


# ═══════════════════════════════════════════════════════════════════════════
# PARTE 1-b — R2 HARDENING: coherencia curso↔año, lente de nivel, duplicados
# ═══════════════════════════════════════════════════════════════════════════
@test("§H2 coherencia curso↔año: curso del año A + año A → OK; + año B → 400 sin escribir")
def _():
    n0 = len(_filas())
    # (a) coherente: C1 pertenece a ANO_A
    assert post_ind(DIR_A, C1, LEN, 2, "coherente", ano_escolar_id=ANO_A).status_code == 201
    # (b) incoherente: C1 es de ANO_A, se pide ANO_A_PREV
    r = post_ind(DIR_A, C1, LEN, 1, "año equivocado", ano_escolar_id=ANO_A_PREV)
    assert r.status_code == 400, r.text
    assert "año escolar" in r.json().get("error", "").lower(), r.json()
    assert not _filas({"curso_id": C1, "asignatura_id": LEN, "periodo": 1}), "creó la fila pese al 400"
    # (c) al revés: curso del año anterior con el año activo
    r = post_ind(DIR_A, C5_PREV, LEN, 1, "otra vez mal", ano_escolar_id=ANO_A)
    assert r.status_code == 400, r.text
    assert not _filas({"curso_id": C5_PREV, "asignatura_id": LEN, "periodo": 1})
    # nada más se creó salvo (a)
    assert len(_filas()) == n0 + 1, "hubo escrituras inesperadas"


@test("§H2-b una actualización con año incoherente NO modifica la fila existente")
def _():
    fila = _filas({"curso_id": C1, "asignatura_id": LEN, "periodo": 2})[0]
    original = fila.contenido
    r = post_ind(DIR_A, C1, LEN, 2, "intento de pisar", ano_escolar_id=ANO_A_PREV)
    assert r.status_code == 400, r.text
    assert _filas({"curso_id": C1, "asignatura_id": LEN, "periodo": 2})[0].contenido == original


@test("§H3 lente de nivel: coordinador de secundaria NO escribe ni borra en primaria")
def _():
    # (a) curso de SECUNDARIA -> permitido
    r = post_ind(COORD_SEC, C2, MAT, 1, "coord en secundaria")
    assert r.status_code == 201, r.text
    # (b) curso de PRIMARIA -> bloqueado, sin escribir
    r = post_ind(COORD_SEC, C4_PRIM, MAT, 1, "coord en primaria")
    assert r.status_code == 403, r.text
    assert not _filas({"curso_id": C4_PRIM}), "escribió fuera de su nivel"
    # (c) DELETE de un indicador de primaria -> bloqueado
    assert post_ind(DIR_A, C4_PRIM, MAT, 1, "creado por dirección").status_code == 201
    prim = _filas({"curso_id": C4_PRIM, "asignatura_id": MAT, "periodo": 1})[0]
    r = client.delete(f"/api/indicadores-logro/{prim.id}", headers=auth(COORD_SEC))
    assert r.status_code == 403, r.text
    assert _filas({"curso_id": C4_PRIM, "asignatura_id": MAT, "periodo": 1}), "borró fuera de su nivel"
    # (d) el GET tampoco se lo muestra
    vistos = get_ind(COORD_SEC, curso_id=C4_PRIM).json()
    assert vistos == [], vistos


@test("§H3-b profesor con asignación REAL cross-level: permitido en ambos niveles")
def _():
    # prof_x tiene (C1=secundaria, LEN) y (C4=primaria, MAT) activas
    assert post_ind(PROF_X, C1, LEN, 4, "prof_x en secundaria").status_code == 201
    assert post_ind(PROF_X, C4_PRIM, MAT, 2, "prof_x en primaria").status_code == 201
    # y sin la pareja exacta -> 403 (su límite real es la asignación)
    assert post_ind(PROF_X, C1, MAT, 4, "sin pareja").status_code == 403
    assert post_ind(PROF_X, C2, LEN, 1, "sin pareja").status_code == 403


@test("§H4 identidad duplicada: POST devuelve 409 y NO modifica ninguna fila")
def _():
    # La clave única impide el duplicado por diseño. Para poder ejercitar la
    # GUARDA de la API se reconstruye la tabla SIN esa restricción (solo en esta
    # DB temporal), se inserta la anomalía y al final se restaura el esquema.
    from sqlalchemy import text as _sql
    _COLS = ("id, colegio_id, profesor_id, asignatura_id, curso_id, ano_escolar_id, "
             "periodo, contenido, fecha_creacion, fecha_actualizacion")
    with engine.connect() as conn:
        conn.execute(_sql(f"CREATE TABLE il_bak AS SELECT {_COLS} FROM indicadores_logro"))
        conn.execute(_sql("DROP TABLE indicadores_logro"))
        conn.execute(_sql(
            "CREATE TABLE indicadores_logro ("
            " id INTEGER NOT NULL PRIMARY KEY, colegio_id INTEGER, profesor_id INTEGER NOT NULL,"
            " asignatura_id INTEGER NOT NULL, curso_id INTEGER NOT NULL, ano_escolar_id INTEGER,"
            " periodo INTEGER NOT NULL, contenido TEXT, fecha_creacion DATETIME,"
            " fecha_actualizacion DATETIME)"))
        conn.execute(_sql(f"INSERT INTO indicadores_logro ({_COLS}) SELECT {_COLS} FROM il_bak"))
        conn.execute(_sql(
            "INSERT INTO indicadores_logro (colegio_id, profesor_id, asignatura_id, curso_id,"
            " ano_escolar_id, periodo, contenido) VALUES (:c, :p, :a, :k, :y, 1, 'fila duplicada')"),
            {"c": COL_A, "p": U_DIR_A, "a": MAT, "k": C2, "y": ANO_A})
        conn.commit()

    antes = sorted((f.id, f.contenido) for f in
                   _filas({"curso_id": C2, "asignatura_id": MAT, "periodo": 1}))
    assert len(antes) == 2, antes
    r = post_ind(DIR_A, C2, MAT, 1, "intento sobre duplicados")
    assert r.status_code == 409, r.text
    despues = sorted((f.id, f.contenido) for f in
                     _filas({"curso_id": C2, "asignatura_id": MAT, "periodo": 1}))
    assert despues == antes, "se modificó una fila pese al conflicto"
    # restaurar el esquema original (con la clave única) y quitar la anomalía
    with engine.connect() as conn:
        conn.execute(_sql("DELETE FROM indicadores_logro WHERE contenido = 'fila duplicada'"))
        conn.execute(_sql("DROP TABLE il_bak"))
        conn.execute(_sql(f"CREATE TABLE il_bak AS SELECT {_COLS} FROM indicadores_logro"))
        conn.execute(_sql("DROP TABLE indicadores_logro"))
        conn.commit()
    M.IndicadorLogro.__table__.create(bind=engine)
    with engine.connect() as conn:
        conn.execute(_sql(f"INSERT INTO indicadores_logro ({_COLS}) SELECT {_COLS} FROM il_bak"))
        conn.execute(_sql("DROP TABLE il_bak"))
        conn.commit()
    idx = {r[1] for r in engine.connect().execute(_sql("PRAGMA index_list(indicadores_logro)"))}
    assert any("uq_indicador_logro_institucional" in n or n.startswith("sqlite_autoindex")
               for n in idx), f"no se restauró la clave única: {idx}"


# ═══════════════════════════════════════════════════════════════════════════
# PARTE 2 — PDF
# ═══════════════════════════════════════════════════════════════════════════
_CI = {"nombre": "CENTRO R2", "direccion": "Av X", "email": "c@e.do", "telefono": "809",
       "director": "DIR", "codigo_centro": "0", "regional": "10", "distrito": "03",
       "sector": "publico", "zona": "urbana", "coordinador": "TITULAR"}


def _stud(n=2):
    return [{"id": i + 1, "no_lista": i + 1, "nombre": f"AL {i}", "sexo": "M",
             "fecha_nacimiento": date(2009, 1, 1), "cedula": "", "matricula": f"M{i}",
             "direccion": "x", "condicion_entrada": "nuevo", "activo": True} for i in range(n)]


def _gen(grado, indicadores_por_asig):
    """indicadores_por_asig: {nombre_asignatura: {periodo: texto}}"""
    asigs = ASIGNATURAS_CICLO_2 if grado >= 4 else ASIGNATURAS_CICLO_1
    ad = {a: {"docente": "DOC", "asistencias": {}, "asistencia_matriz": [],
              "calificaciones": {}, "indicadores": indicadores_por_asig.get(a, {})}
          for a in asigs}
    pdf = generar_registro_desde_sistema(
        _CI, {"grado": str(grado), "seccion": "A", "tanda": "Matutina"},
        "2025-2026", _stud(), ad, grado)
    return pdf, PdfReader(io.BytesIO(pdf))


def _xnames(page):
    res = page.get("/Resources")
    if not res:
        return set()
    xo = res.get_object().get("/XObject")
    return {str(k) for k in xo.get_object().keys()} if xo else set()


def _tiene_overlay(rd, pg1):
    return any(n.startswith("/EODataOverlay") for n in _xnames(rd.pages[pg1 - 1]))


def _textos_overlay(rd, pg1):
    """Texto dibujado por NOSOTROS en esa página (x dentro de la columna)."""
    hits = []

    def vis(t, cm, tm, fd, fs):
        s = (t or "").strip()
        if s:
            hits.append((round(float(tm[4]), 2), round(float(tm[5]), 2), s))
    rd.pages[pg1 - 1].extract_text(visitor_text=vis)
    x0 = INDICADOR_BOX["x0"] + INDICADOR_BOX["padding"]
    return [h for h in hits if abs(h[0] - x0) < 0.01]


@test("§11 un indicador de P1 aparece SOLO en la página de P1 de su asignatura")
def _():
    _pdf, rd = _gen(1, {"Matemática": {1: "IL-1 solo periodo uno"}})
    p1, p2, p3, p4 = [pagina_indicador(1, 3, p) for p in (1, 2, 3, 4)]   # a_idx 3 = Matemática
    assert (p1, p2, p3, p4) == (83, 84, 85, 86), (p1, p2, p3, p4)
    assert _tiene_overlay(rd, p1), "P1 sin overlay"
    for p in (p2, p3, p4):
        assert not _tiene_overlay(rd, p), f"P{p} recibió overlay indebido"
    assert any("periodo uno" in t for _x, _y, t in _textos_overlay(rd, p1))


@test("§12 P1-P4 con textos distintos: cada uno en SU bloque correcto")
def _():
    textos = {p: f"INDICADOR-DEL-PERIODO-{p}" for p in (1, 2, 3, 4)}
    _pdf, rd = _gen(1, {"Lengua Española": textos})
    for p in (1, 2, 3, 4):
        pg = pagina_indicador(1, 0, p)
        propios = " ".join(t for _x, _y, t in _textos_overlay(rd, pg))
        assert f"INDICADOR-DEL-PERIODO-{p}" in propios.replace(" ", ""), (p, pg, propios[:120])
        for otro in (1, 2, 3, 4):
            if otro != p:
                assert f"INDICADOR-DEL-PERIODO-{otro}" not in propios.replace(" ", ""), (p, otro)


@test("§10 sin indicadores: NINGUNA página de indicadores recibe overlay (template intacto)")
def _():
    _pdf, rd = _gen(1, {})
    for a_idx in range(9):
        for p in (1, 2, 3, 4):
            pg = pagina_indicador(1, a_idx, p)
            assert not _tiene_overlay(rd, pg), f"pg {pg} recibió overlay sin datos"
    # y tampoco se escribe "N/A" ni "Sin indicadores" en ninguna parte
    txt = " ".join((rd.pages[i].extract_text() or "") for i in range(64, 116))
    assert "Sin indicadores" not in txt and "N/A" not in txt


@test("§13 texto largo: se ajusta y NUNCA sale de la columna 'Indicadores de Logro'")
def _():
    largo = ("IL-9 Utiliza estrategias de comprension lectora en textos expositivos "
             "argumentativos y narrativos para construir significado. ") * 60
    _pdf, rd = _gen(1, {"Matemática": {1: largo}})
    pg = pagina_indicador(1, 3, 1)
    lineas = _textos_overlay(rd, pg)
    assert lineas, "no se dibujó nada"
    size = INDICADOR_BOX["font_size"]
    x0, x1 = INDICADOR_BOX["x0"], INDICADOR_BOX["x1"]
    y_max = 792 - INDICADOR_BOX["y_top_plumber"]
    y_min = 792 - INDICADOR_BOX["y_bottom_plumber"]
    for x, y, t in lineas:
        assert x >= x0, (x, x0)
        assert x + stringWidth(t, FONT_NORMAL, size) <= x1, f"'{t[:30]}' desborda a la derecha"
        assert y_min <= y <= y_max, f"linea fuera del cuerpo: y={y}"
    assert any(t.endswith("…") for _x, _y, t in lineas), "texto largo sin truncado determinista"


@test("§R2-extra _wrap_texto es determinista y respeta el ancho")
def _():
    ancho = INDICADOR_BOX["x1"] - INDICADOR_BOX["x0"] - 2 * INDICADOR_BOX["padding"]
    size = INDICADOR_BOX["font_size"]
    txt = "palabra " * 80 + "\n" + "Supercalifragilisticoespialidoso" * 4
    a = _wrap_texto(txt, ancho, FONT_NORMAL, size)
    b = _wrap_texto(txt, ancho, FONT_NORMAL, size)
    assert a == b, "no determinista"
    for l in a:
        assert stringWidth(l, FONT_NORMAL, size) <= ancho + 0.01, l[:40]


@test("§14 smoke 1ro Secundaria: genera y las 9 asignaturas caen en sus páginas")
def _():
    ind = {a: {1: f"P1 de {a}"} for a in ASIGNATURAS_CICLO_1}
    _pdf, rd = _gen(1, ind)
    assert len(rd.pages) == 170
    for a_idx in range(9):
        pg = pagina_indicador(1, a_idx, 1)
        assert pg == INDICADORES_P1_CICLO_1[a_idx]
        assert _tiene_overlay(rd, pg), f"1ro a_idx {a_idx} pg {pg} sin overlay"


@test("§15 smoke 4to Secundaria: mapeo irregular (Salida Optativa intercalada) correcto")
def _():
    ind = {a: {2: f"P2 de {a}"} for a in ASIGNATURAS_CICLO_1}   # solo las 9 base
    _pdf, rd = _gen(4, ind)
    assert len(rd.pages) == 238
    for a_idx in range(9):
        pg = pagina_indicador(2, a_idx, 2)
        assert pg == INDICADORES_P1_CICLO_2[a_idx] + 1
        assert _tiene_overlay(rd, pg), f"4to a_idx {a_idx} pg {pg} sin overlay"
    # Salida Optativa NO recibe indicadores (su mapeo por modalidad es R3)
    for pg in (83, 84, 85, 86, 89, 101, 119, 131, 143):
        assert not _tiene_overlay(rd, pg), f"pg {pg} (Salida Optativa) recibió overlay"


@test("§16 número de páginas intacto en los 6 grados (170/170/170/238/238/240)")
def _():
    esperado = {1: 170, 2: 170, 3: 170, 4: 238, 5: 238, 6: 240}
    for g, n in esperado.items():
        _pdf, rd = _gen(g, {"Matemática": {1: "IL-1 prueba"}})
        assert len(rd.pages) == n, f"grado {g}: {len(rd.pages)} != {n}"


@test("§17 XObject: la página de indicadores lleva /EODataOverlayN (pipeline v2.19.9)")
def _():
    _pdf, rd = _gen(2, {"Ciencias Sociales": {4: "IL-4 prueba xobject"}})
    pg = pagina_indicador(1, 4, 4)
    assert any(n.startswith("/EODataOverlay") for n in _xnames(rd.pages[pg - 1])), _xnames(rd.pages[pg - 1])


@test("§18 merge_page() sigue AUSENTE del código del generador")
def _():
    import inspect, tokenize, io as _io
    import registro_escolar as _re

    def llama(src):
        toks = list(tokenize.generate_tokens(_io.StringIO(src).readline))
        for i, tk in enumerate(toks):
            if tk.type == tokenize.NAME and tk.string == "merge_page":
                for nxt in toks[i + 1:]:
                    if nxt.type in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
                                    tokenize.DEDENT, tokenize.COMMENT):
                        continue
                    return nxt.type == tokenize.OP and nxt.string == "("
        return False
    assert not llama(inspect.getsource(_re)), "registro_escolar.py invoca merge_page("
    assert not llama(inspect.getsource(_re.draw_indicadores))


@test("§F-bulk carga de indicadores sin N+1: 1 sola consulta a indicadores_logro")
def _():
    from app import _cargar_datos_asignaturas_secundaria
    sqls = []

    @event.listens_for(engine, "before_cursor_execute")
    def _cap(conn, cur, statement, params, ctx, many):
        s = statement.strip().lower()
        if s.startswith("select") and "indicadores_logro" in s:
            sqls.append(statement)

    class _U:
        role = "direccion"; colegio_id = COL_A; id = U_DIR_A

    d = SessionLocal()
    try:
        # estudiantes del curso (para el loader)
        for i in range(3):
            d.add(M.Estudiante(id=900 + i, colegio_id=COL_A, nombre=f"E{i}", apellido="R2",
                               curso_id=C1, activo=True, no_lista=i + 1))
        d.add(M.AsignacionProfesor(id=50, colegio_id=COL_A, profesor_id=U_PROF_B,
                                   curso_id=C1, asignatura_id=LEN, activo=True))
        d.commit()
        ests = d.query(M.Estudiante).filter_by(curso_id=C1, activo=True).all()
        sqls.clear()
        data = _cargar_datos_asignaturas_secundaria(d, _U(), C1, 1, ests)
    finally:
        d.close()
        event.remove(engine, "before_cursor_execute", _cap)

    assert len(sqls) == 1, f"{len(sqls)} consultas a indicadores_logro:\n" + "\n".join(sqls)
    # y el texto llega al diccionario que consume el generador
    mate = data.get("Matemática", {}).get("indicadores", {})
    assert 1 in mate and "continuado" in mate[1], mate


# ═══════════════════════════════════════════════════════════════════════════
print(f"\n{B}{'=' * 62}{X}")
print(f"{B}  RESUMEN R2 — Indicadores de Logro{X}")
print(f"{B}{'=' * 62}{X}")
print(f"  {G}{_ok} PASARON{X} / {R}{len(_fail)} FALLARON{X}  (de {_total})")
for n, e in _fail:
    print(f"  {R}✗ {n}{X}\n      {e}")

for ruta, mt, etiqueta in ((_REPO_SGE, _sge_mtime, "sge.db"),
                           (_REPO_CREDS, _creds_mtime, "INITIAL_CREDENTIALS.txt")):
    if mt is not None:
        ahora = os.path.getmtime(ruta) if os.path.exists(ruta) else None
        if ahora != mt:
            print(f"{R}{B}✗ SEGURIDAD: {etiqueta} del repo cambió{X}")
            sys.exit(2)
print(f"{G}✓ SEGURIDAD: archivos reales del repo intactos{X}")

sys.exit(1 if _fail else 0)
