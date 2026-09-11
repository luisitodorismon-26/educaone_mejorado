# -*- coding: utf-8 -*-
"""
EducaOne P0 — HOTFIX: aislamiento de reportes + integridad de horarios.

BLOQUE A — REPORTES
    profesor      -> SOLO los reportes que el mismo creo
    direccion     -> todos los del colegio
    coordinacion  -> todos los del colegio
    secretaria    -> SIN listado general
    psicologia    -> SIN listado general (opera desde sus casos)
    Se conservan: PDF propio del profesor, POST /api/reportes, acciones de
    gestion de Direccion/Coordinacion/Psicologia, aislamiento por colegio.

BLOQUE B — HORARIOS
    Un bloque `tipo_bloque='clase'` exige una AsignacionProfesor ACTIVA que
    coincida en colegio_id + profesor_id + curso_id + asignatura_id.
    No basta profesor + curso: un docente puede impartir varias asignaturas en
    el mismo curso (en produccion: Ingles Y Frances en 1ro Secundaria A).

Cada bloque incluye una prueba que DEBE fallar si se revierte el arreglo.

Uso:
    cd backend
    python tools/test_p0_reportes_horarios.py
"""
import os
import sys
import atexit
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TMPDIR = tempfile.mkdtemp(prefix="eo_p0_hotfix_")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_TMPDIR, "s.db").replace("\\", "/")
os.environ.setdefault("ENVIRONMENT", "development")


@atexit.register
def _cleanup():
    import shutil
    shutil.rmtree(_TMPDIR, ignore_errors=True)


from sqlalchemy import event                                   # noqa: E402
from database import engine, SessionLocal                      # noqa: E402
import models as M                                             # noqa: E402

_eu = str(engine.url).replace("\\", "/")
assert _TMPDIR.replace("\\", "/") in _eu and "sge.db" not in _eu, _eu

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_SGE = os.path.join(_BACKEND, "sge.db")
_sge_mtime = os.path.getmtime(_REPO_SGE) if os.path.exists(_REPO_SGE) else None


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
        print(f"\n{C}> {nombre}{X}")
        try:
            fn()
            _ok += 1
            print(f"  {G}PASO{X}")
        except Exception as e:
            import traceback
            _fail.append((nombre, str(e)))
            print(f"  {R}FALLO: {e}{X}")
            traceback.print_exc()
        return fn
    return deco


# --------------------------------------------------------------------------
# FIXTURE — reproduce la forma de produccion
# --------------------------------------------------------------------------
COL_A, COL_B = 1, 2
PWD = "Prueba2026x"
GRADO_A, GRADO_B = 1, 99
# P1 y P2 comparten curso; P4 imparte DOS asignaturas en el mismo curso
C_COMP, C_OTRO, C_B = 10, 11, 20
A_LENGUA, A_SOCIALES, A_INGLES, A_FRANCES = 1, 3, 5, 17
U_P1, U_P2, U_P3, U_P4 = 31, 32, 33, 40
U_DIR, U_COORD, U_PSI, U_SEC = 34, 35, 36, 37
U_DIR_B, U_P_B = 38, 39
EST_COMP, EST_OTRO, EST_B = 50, 51, 52
CURSO_B_ASIG = 77


def _seed():
    M.Base.metadata.drop_all(bind=engine)
    M.Base.metadata.create_all(bind=engine)
    d = SessionLocal()
    try:
        for cid, nom in ((COL_A, "Colegio A"), (COL_B, "Colegio B")):
            d.add(M.Colegio(id=cid, nombre=nom, codigo=nom[-1].lower()))
            d.add(M.AnoEscolar(id=cid, colegio_id=cid, nombre="2025-2026",
                               activo=True, dias_trabajados="{}"))
        d.add(M.Grado(id=GRADO_A, colegio_id=COL_A, nombre="1ro Secundaria",
                      nivel="secundaria", orden=1))
        d.add(M.Grado(id=GRADO_B, colegio_id=COL_B, nombre="1ro Secundaria",
                      nivel="secundaria", orden=1))
        for cur, col, gr in ((C_COMP, COL_A, GRADO_A), (C_OTRO, COL_A, GRADO_A),
                             (C_B, COL_B, GRADO_B)):
            d.add(M.Curso(id=cur, colegio_id=col, nombre="A", grado_id=gr,
                          ano_escolar_id=col, activo=True))
        for aid, nom, cod in ((A_LENGUA, "Lengua Española", "LE"),
                              (A_SOCIALES, "Ciencias Sociales", "CS"),
                              (A_INGLES, "Inglés", "IN"),
                              (A_FRANCES, "Francés", "FR")):
            d.add(M.Asignatura(id=aid, colegio_id=COL_A, nombre=nom, codigo=cod,
                               area="X", activo=True))
        d.add(M.Asignatura(id=CURSO_B_ASIG, colegio_id=COL_B, nombre="Lengua",
                           codigo="LE", area="X", activo=True))
        for uid, un, rol, col in ((U_P1, "p1", "profesor", COL_A),
                                  (U_P2, "p2", "profesor", COL_A),
                                  (U_P3, "p3", "profesor", COL_A),
                                  (U_P4, "p4", "profesor", COL_A),
                                  (U_DIR, "dir", "direccion", COL_A),
                                  (U_COORD, "coord", "coordinador", COL_A),
                                  (U_PSI, "psi", "psicologia", COL_A),
                                  (U_SEC, "sec", "secretaria", COL_A),
                                  (U_DIR_B, "dir_b", "direccion", COL_B),
                                  (U_P_B, "p_b", "profesor", COL_B)):
            u = M.Usuario(id=uid, username=un, nombre=un.upper(), apellido="T",
                          role=rol, colegio_id=col, activo=True)
            u.set_password(PWD)
            d.add(u)
        for eid, col, cur, nom in ((EST_COMP, COL_A, C_COMP, "EstComp"),
                                   (EST_OTRO, COL_A, C_OTRO, "EstOtro"),
                                   (EST_B, COL_B, C_B, "EstB")):
            d.add(M.Estudiante(id=eid, colegio_id=col, nombre=nom, apellido="T",
                               curso_id=cur, activo=True, no_lista=1))
        asigs = (
            (1, U_P1, C_COMP, A_LENGUA, True),
            (2, U_P2, C_COMP, A_SOCIALES, True),
            (3, U_P3, C_OTRO, A_LENGUA, True),
            # el caso de produccion: MISMO profesor, MISMO curso, DOS asignaturas
            (4, U_P4, C_COMP, A_INGLES, True),
            (5, U_P4, C_COMP, A_FRANCES, True),
            # asignacion retirada: no debe habilitar nada
            (6, U_P4, C_OTRO, A_INGLES, False),
        )
        for aid, prof, cur, asig, act in asigs:
            d.add(M.AsignacionProfesor(id=aid, colegio_id=COL_A, profesor_id=prof,
                                       curso_id=cur, asignatura_id=asig,
                                       ano_escolar_id=COL_A, activo=act))
        d.add(M.AsignacionProfesor(id=20, colegio_id=COL_B, profesor_id=U_P_B,
                                   curso_id=C_B, asignatura_id=CURSO_B_ASIG,
                                   ano_escolar_id=COL_B, activo=True))
        reportes = (
            (100, COL_A, EST_COMP, U_P1, "DE_P1", "SECRETO_DE_P1"),
            (101, COL_A, EST_COMP, U_P2, "DE_P2", "SECRETO_DE_P2"),
            (102, COL_A, EST_OTRO, U_P3, "DE_P3", "SECRETO_DE_P3"),
            (103, COL_B, EST_B, U_P_B, "DE_B", "SECRETO_DE_COLEGIO_B"),
        )
        for rid, col, est, autor, tit, desc in reportes:
            d.add(M.ReporteConducta(id=rid, colegio_id=col, estudiante_id=est,
                                    reportado_por=autor, titulo=tit,
                                    descripcion=desc, tipo="conducta",
                                    gravedad="leve", estado="pendiente",
                                    fecha=date(2026, 3, 2)))
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
TOK = {u: login(u) for u in ("p1", "p2", "p3", "p4", "dir", "coord", "psi",
                             "sec", "dir_b", "p_b")}


def listado(u):
    r = client.get("/api/reportes", headers=auth(TOK[u]))
    return r.status_code, ({x["id"] for x in r.json()} if r.status_code == 200 else None)


# ===========================================================================
# BLOQUE A — REPORTES
# ===========================================================================

@test("§A1 PROFESOR: ve SOLO los reportes que el creo (regresion del bug P0)")
def _():
    cod, v = listado("p1")
    assert cod == 200, cod
    assert v == {100}, ("P1 debe ver exclusivamente el suyo; vio %s" % v)
    cod, v = listado("p2")
    assert v == {101}, v
    cod, v = listado("p3")
    assert v == {102}, v


@test("§A2 PROFESOR sin reportes propios: listado vacio, no el de sus colegas")
def _():
    cod, v = listado("p4")
    assert cod == 200, cod
    assert v == set(), ("p4 no creo ninguno; debe ver 0, vio %s" % v)


@test("§A3 el texto del reporte ajeno ya NO viaja al profesor")
def _():
    r = client.get("/api/reportes", headers=auth(TOK["p1"]))
    cuerpo = r.text
    assert "SECRETO_DE_P2" not in cuerpo, "se filtra la descripcion ajena"
    assert "SECRETO_DE_P3" not in cuerpo
    assert "SECRETO_DE_P1" in cuerpo, "debe seguir viendo el propio"


@test("§A4 DIRECCION y COORDINACION: todos los reportes del colegio")
def _():
    for u in ("dir", "coord"):
        cod, v = listado(u)
        assert cod == 200, (u, cod)
        assert v == {100, 101, 102}, (u, v)


@test("§A5 SECRETARIA: sin listado general (403)")
def _():
    cod, _v = listado("sec")
    assert cod == 403, cod


@test("§A6 PSICOLOGIA: sin listado general automatico (403)")
def _():
    cod, _v = listado("psi")
    assert cod == 403, cod


@test("§A7 PSICOLOGIA conserva sus acciones sobre un caso concreto")
def _():
    r = client.post("/api/reportes/101/responder",
                    json={"respuesta": "Intervencion desde el caso"},
                    headers=auth(TOK["psi"]))
    assert r.status_code == 200, (r.status_code, r.text[:200])
    d = SessionLocal()
    try:
        assert d.query(M.ReporteConducta).get(101).estado != "pendiente"
    finally:
        d.close()


@test("§A8 el PDF propio del profesor sigue funcionando; el ajeno sigue en 403")
def _():
    assert client.get("/api/reportes/100/pdf",
                      headers=auth(TOK["p1"])).status_code == 200
    assert client.get("/api/reportes/101/pdf",
                      headers=auth(TOK["p1"])).status_code == 403


@test("§A9 POST /api/reportes: el profesor sigue pudiendo crear, y lo ve")
def _():
    r = client.post("/api/reportes", headers=auth(TOK["p4"]), json={
        "estudiante_id": EST_COMP, "titulo": "NUEVO_DE_P4",
        "descripcion": "creado en la prueba", "tipo": "conducta",
        "gravedad": "leve", "fecha": "2026-03-06",
    })
    assert r.status_code in (200, 201), (r.status_code, r.text[:200])
    nuevo = r.json().get("id") or r.json().get("reporte", {}).get("id")
    assert nuevo, r.text[:200]
    cod, v = listado("p4")
    assert v == {nuevo}, ("debe ver el que acaba de crear, y solo ese", v)
    cod, v = listado("p1")
    assert nuevo not in v, "y su colega NO debe verlo"


@test("§A10 aislamiento por colegio intacto")
def _():
    for u in ("p1", "dir", "coord"):
        _cod, v = listado(u)
        assert 103 not in v, (u, "ve un reporte del colegio B")
    _cod, v = listado("dir_b")
    assert v == {103}, v
    assert client.get("/api/reportes/103/pdf",
                      headers=auth(TOK["dir"])).status_code == 404


@test("§A11 sin token: 401")
def _():
    assert client.get("/api/reportes").status_code in (401, 403)


# ===========================================================================
# BLOQUE B — HORARIOS
# ===========================================================================
def _cuenta_horarios():
    d = SessionLocal()
    try:
        return d.query(M.Horario).count()
    finally:
        d.close()


def _crear(u, **campos):
    base = {"profesor_id": U_P4, "curso_id": C_COMP, "dia": "Lunes",
            "hora_inicio": "07:40", "hora_fin": "08:15", "tipo_bloque": "clase"}
    base.update(campos)
    return client.post("/api/horarios", json=base, headers=auth(TOK[u]))


@test("§B1 profesor con Ingles Y Frances en el mismo curso: crea el de INGLES")
def _():
    r = _crear("dir", asignatura_id=A_INGLES, hora_inicio="07:40", hora_fin="08:15")
    assert r.status_code == 201, (r.status_code, r.text[:250])
    d = SessionLocal()
    try:
        h = d.query(M.Horario).get(r.json()["id"])
        assert h.asignatura_id == A_INGLES, h.asignatura_id
    finally:
        d.close()


@test("§B2 ...y tambien el de FRANCES: la segunda materia no queda bloqueada")
def _():
    r = _crear("dir", asignatura_id=A_FRANCES, hora_inicio="08:15", hora_fin="09:00")
    assert r.status_code == 201, (r.status_code, r.text[:250])
    d = SessionLocal()
    try:
        h = d.query(M.Horario).get(r.json()["id"])
        assert h.asignatura_id == A_FRANCES, ("debe guardar FRANCES, no Ingles: "
                                              "la identidad es profesor+curso+asignatura")
    finally:
        d.close()


@test("§B3 NO puede crear Lengua: la tiene otro docente en ese curso (409)")
def _():
    antes = _cuenta_horarios()
    r = _crear("dir", asignatura_id=A_LENGUA, hora_inicio="09:00", hora_fin="09:45")
    assert r.status_code == 409, (r.status_code, r.text[:250])
    cuerpo = r.json().get("error", "")
    assert "no tiene asignada" in cuerpo, cuerpo
    # el mensaje debe orientar: dice que SI tiene en ese curso
    assert "Inglés" in cuerpo or "Francés" in cuerpo, cuerpo
    assert _cuenta_horarios() == antes, "un 409 no debe dejar filas"


@test("§B4 una asignacion INACTIVA no habilita el bloque (409)")
def _():
    antes = _cuenta_horarios()
    r = _crear("dir", curso_id=C_OTRO, asignatura_id=A_INGLES,
               hora_inicio="10:00", hora_fin="10:45")
    assert r.status_code == 409, (r.status_code, r.text[:250])
    assert _cuenta_horarios() == antes


@test("§B5 profesor sin ninguna asignacion en el curso: mensaje distinto")
def _():
    r = _crear("dir", profesor_id=U_P1, curso_id=C_OTRO, asignatura_id=A_LENGUA,
               hora_inicio="11:00", hora_fin="11:45")
    assert r.status_code == 409, (r.status_code, r.text[:250])
    assert "No tiene ninguna asignatura asignada" in r.json().get("error", ""), \
        r.json().get("error", "")


@test("§B6 cross-tenant: 404, sin revelar existencia y sin crear nada")
def _():
    antes = _cuenta_horarios()
    r = _crear("dir", profesor_id=U_P_B, curso_id=C_B, asignatura_id=CURSO_B_ASIG)
    assert r.status_code == 404, (r.status_code, r.text[:200])
    r2 = _crear("dir", curso_id=C_B, asignatura_id=A_INGLES)
    assert r2.status_code == 404, r2.status_code
    assert _cuenta_horarios() == antes


@test("§B7 _conflicto_clase se conserva: el solapamiento sigue dando 409")
def _():
    # mismo profesor, misma franja que §B1, otra asignatura valida
    r = _crear("dir", asignatura_id=A_FRANCES, hora_inicio="07:40", hora_fin="08:15")
    assert r.status_code == 409, (r.status_code, r.text[:250])
    assert "Conflicto de horario" in r.json().get("error", ""), r.json()


@test("§B8 bloques sin curso (recreo/libre) no exigen asignacion")
def _():
    r = client.post("/api/horarios", headers=auth(TOK["dir"]), json={
        "profesor_id": U_P1, "dia": "Martes", "hora_inicio": "09:45",
        "hora_fin": "10:15", "tipo_bloque": "recreo"})
    assert r.status_code == 201, (r.status_code, r.text[:250])


@test("§B9 PUT: no se puede mover un bloque a una asignatura no asignada")
def _():
    r = _crear("dir", asignatura_id=A_INGLES, hora_inicio="13:00", hora_fin="13:45")
    assert r.status_code == 201, r.text[:200]
    hid = r.json()["id"]
    p = client.put(f"/api/horarios/{hid}", json={"asignatura_id": A_LENGUA},
                   headers=auth(TOK["dir"]))
    assert p.status_code == 409, (p.status_code, p.text[:250])
    d = SessionLocal()
    try:
        assert d.query(M.Horario).get(hid).asignatura_id == A_INGLES, \
            "el 409 debe dejar la fila EXACTAMENTE como estaba"
    finally:
        d.close()


@test("§B10 PUT: cambiar de profesor a uno sin la asignatura tambien falla")
def _():
    r = _crear("dir", asignatura_id=A_FRANCES, hora_inicio="14:00", hora_fin="14:45")
    hid = r.json()["id"]
    p = client.put(f"/api/horarios/{hid}", json={"profesor_id": U_P1},
                   headers=auth(TOK["dir"]))
    assert p.status_code == 409, (p.status_code, p.text[:250])
    d = SessionLocal()
    try:
        assert d.query(M.Horario).get(hid).profesor_id == U_P4
    finally:
        d.close()


@test("§B11 PUT valido entre las DOS asignaturas del mismo profesor y curso")
def _():
    r = _crear("dir", asignatura_id=A_INGLES, hora_inicio="15:00", hora_fin="15:45")
    hid = r.json()["id"]
    p = client.put(f"/api/horarios/{hid}", json={"asignatura_id": A_FRANCES},
                   headers=auth(TOK["dir"]))
    assert p.status_code == 200, (p.status_code, p.text[:250])
    d = SessionLocal()
    try:
        assert d.query(M.Horario).get(hid).asignatura_id == A_FRANCES
    finally:
        d.close()


@test("§B12 el guard no cambia quien puede escribir: sigue siendo Direccion")
def _():
    for u in ("p4", "coord", "sec", "psi"):
        r = _crear(u, asignatura_id=A_INGLES, hora_inicio="16:00", hora_fin="16:45")
        assert r.status_code == 403, (u, r.status_code)


@test("§B13 ESTE PR NO TOCA DATOS: ninguna fila preexistente fue modificada")
def _():
    d = SessionLocal()
    try:
        # las 4 filas de reportes del seed siguen ahi (101 solo cambio de estado
        # por la accion legitima de psicologia en §A7)
        assert d.query(M.ReporteConducta).filter(
            M.ReporteConducta.id.in_([100, 101, 102, 103])).count() == 4
        # las asignaciones del seed intactas, incluida la inactiva
        assert d.query(M.AsignacionProfesor).count() == 7
        assert d.query(M.AsignacionProfesor).get(6).activo is False
    finally:
        d.close()


@test("§ZZ sge.db del repo intacto")
def _():
    a = os.path.getmtime(_REPO_SGE) if os.path.exists(_REPO_SGE) else None
    assert a == _sge_mtime, "sge.db fue modificado"


print("\n" + "=" * 70)
print(f"{B}P0 HOTFIX: {_ok}/{_total} pruebas{X}")
if _fail:
    print(f"{R}FALLARON:{X}")
    for n, e in _fail:
        print(f"  - {n}: {e}")
    sys.exit(1)
print(f"{G}TODO VERDE{X}")
