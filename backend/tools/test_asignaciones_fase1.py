# -*- coding: utf-8 -*-
"""
EducaOne FASE 1 — guardado de Asignaciones: RECONCILIA, no reemplaza.

Hasta main=5733ec6, POST /api/cursos/{id}/asignaciones desactivaba TODAS las
asignaciones activas del curso y creaba filas nuevas. Como la pantalla envia la
tabla completa, guardar sin cambiar nada desactivaba N filas y creaba otras N
equivalentes: en produccion eso dejo 85 filas inactivas de 147.

Esta suite fija el comportamiento nuevo y, sobre todo, lo que NO debe cambiar:
la pantalla, el contrato del endpoint y la historia academica.

Uso:
    cd backend
    python tools/test_asignaciones_fase1.py
"""
import os
import sys
import atexit
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TMPDIR = tempfile.mkdtemp(prefix="eo_fase1_asig_")
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
ANO_A, ANO_B = 1, 2
G_SEC, G_PRI, G_B = 1, 2, 99
# CUR_SEC: curso de Secundaria con varias materias
# CUR_PRI: curso de Primaria (mismo profesor puede trabajar en ambos)
# CUR_OPT: curso con Salida Optativa configurada
CUR_SEC, CUR_PRI, CUR_OPT, CUR_B = 10, 11, 12, 20
# asignaturas: troncales + una optativa dedicada + una troncal mapeada (legacy)
A_LENGUA, A_SOCIALES, A_INGLES, A_FRANCES, A_MUSICA = 1, 3, 5, 17, 18
A_OPTATIVA = 21          # identidad independiente (area_curricular_codigo NULL)
A_B = 77
U_P1, U_P2, U_P4, U_PRI = 31, 32, 40, 41
U_DIR, U_SEC_ROL, U_PSI = 34, 37, 36
U_DIR_B, U_P_B = 38, 39
EST_SEC, EST_B = 50, 52


def _seed():
    M.Base.metadata.drop_all(bind=engine)
    M.Base.metadata.create_all(bind=engine)
    d = SessionLocal()
    try:
        for cid, nom, ano in ((COL_A, "Colegio A", ANO_A), (COL_B, "Colegio B", ANO_B)):
            d.add(M.Colegio(id=cid, nombre=nom, codigo=nom[-1].lower(),
                            plan_primaria=True, plan_secundaria=True))
            d.add(M.AnoEscolar(id=ano, colegio_id=cid, nombre="2025-2026",
                               activo=True, dias_trabajados="{}"))
        d.add(M.Grado(id=G_SEC, colegio_id=COL_A, nombre="4to Secundaria",
                      nivel="secundaria", orden=4))
        d.add(M.Grado(id=G_PRI, colegio_id=COL_A, nombre="5to Primaria",
                      nivel="primaria", orden=50))
        d.add(M.Grado(id=G_B, colegio_id=COL_B, nombre="1ro Secundaria",
                      nivel="secundaria", orden=1))
        for cur, col, gr, ano in ((CUR_SEC, COL_A, G_SEC, ANO_A),
                                  (CUR_PRI, COL_A, G_PRI, ANO_A),
                                  (CUR_OPT, COL_A, G_SEC, ANO_A),
                                  (CUR_B, COL_B, G_B, ANO_B)):
            d.add(M.Curso(id=cur, colegio_id=col, nombre="A", grado_id=gr,
                          ano_escolar_id=ano, activo=True))
        # troncales: llevan area_curricular_codigo
        for aid, nom, cod, area in ((A_LENGUA, "Lengua Española", "LE", "LE"),
                                    (A_SOCIALES, "Ciencias Sociales", "CS", "CS"),
                                    (A_INGLES, "Inglés", "IN", "LEI"),
                                    (A_FRANCES, "Francés", "FR", "LEF"),
                                    (A_MUSICA, "Musica", "MU", "EA")):
            d.add(M.Asignatura(id=aid, colegio_id=COL_A, nombre=nom, codigo=cod,
                               area="X", area_curricular_codigo=area, activo=True))
        # optativa dedicada: identidad independiente
        d.add(M.Asignatura(id=A_OPTATIVA, colegio_id=COL_A,
                           nombre="Apreciación y Producción Literarias",
                           codigo="HCS-LE-4", area="X",
                           area_curricular_codigo=None, activo=True))
        d.add(M.Asignatura(id=A_B, colegio_id=COL_B, nombre="LenguaB", codigo="LE",
                           area="X", activo=True))
        for uid, un, rol, col in ((U_P1, "p1", "profesor", COL_A),
                                  (U_P2, "p2", "profesor", COL_A),
                                  (U_P4, "p4", "profesor", COL_A),
                                  (U_PRI, "ppri", "profesor", COL_A),
                                  (U_DIR, "dir", "direccion", COL_A),
                                  (U_SEC_ROL, "sec", "secretaria", COL_A),
                                  (U_PSI, "psi", "psicologia", COL_A),
                                  (U_DIR_B, "dir_b", "direccion", COL_B),
                                  (U_P_B, "p_b", "profesor", COL_B)):
            u = M.Usuario(id=uid, username=un, nombre=un.upper(), apellido="T",
                          role=rol, colegio_id=col, activo=True)
            u.set_password(PWD)
            d.add(u)
        d.add(M.Estudiante(id=EST_SEC, colegio_id=COL_A, nombre="Est", apellido="T",
                           curso_id=CUR_SEC, activo=True, no_lista=1))
        d.add(M.Estudiante(id=EST_B, colegio_id=COL_B, nombre="EstB", apellido="T",
                           curso_id=CUR_B, activo=True, no_lista=1))
        # Estado inicial de CUR_SEC: 4 relaciones activas.
        # P4 imparte DOS asignaturas en el MISMO curso (caso real de produccion).
        for aid, prof, cur, asig, act, tit in (
                (1, U_P1, CUR_SEC, A_LENGUA, True, True),
                (2, U_P2, CUR_SEC, A_SOCIALES, True, False),
                (3, U_P4, CUR_SEC, A_INGLES, True, False),
                (4, U_P4, CUR_SEC, A_FRANCES, True, False),
                # fila INACTIVA equivalente: debe reactivarse, no duplicarse
                (5, U_P1, CUR_SEC, A_MUSICA, False, False),
                # Primaria: el mismo profesor trabaja en los dos niveles
                (6, U_P1, CUR_PRI, A_LENGUA, True, True),
                (7, U_PRI, CUR_PRI, A_SOCIALES, True, False),
                # curso con Salida Optativa: troncal + componente dedicado
                (8, U_P1, CUR_OPT, A_LENGUA, True, True),
                (9, U_P1, CUR_OPT, A_OPTATIVA, True, False)):
            d.add(M.AsignacionProfesor(id=aid, colegio_id=COL_A, profesor_id=prof,
                                       curso_id=cur, asignatura_id=asig,
                                       ano_escolar_id=ANO_A, activo=act,
                                       es_titular=tit))
        d.add(M.AsignacionProfesor(id=20, colegio_id=COL_B, profesor_id=U_P_B,
                                   curso_id=CUR_B, asignatura_id=A_B,
                                   ano_escolar_id=ANO_B, activo=True))
        # Mapeo de Salida Optativa: (CUR_OPT, A_OPTATIVA) lo administra R3.4
        d.add(M.CursoComponenteOptativo(
            id=1, colegio_id=COL_A, curso_id=CUR_OPT, ano_escolar_id=ANO_A,
            componente_codigo="HCS-LE-4", asignatura_id=A_OPTATIVA, activo=True))
        # Mapeo LEGACY que apunta a una TRONCAL: NO debe proteger a Lengua
        d.add(M.CursoComponenteOptativo(
            id=2, colegio_id=COL_A, curso_id=CUR_OPT, ano_escolar_id=ANO_A,
            componente_codigo="HCS-CS-4", asignatura_id=A_LENGUA, activo=True))
        d.commit()
    finally:
        d.close()


def login(u):
    r = client.post("/api/auth/login", json={"username": u, "password": PWD})
    assert r.status_code == 200, f"login {u}: {r.status_code} {r.text[:160]}"
    return {"Authorization": "Bearer " + r.json()["token"]}


_seed()
TOK = {u: login(u) for u in ("dir", "sec", "psi", "dir_b", "p1")}


def guardar(curso, filas, quien="dir"):
    return client.post(f"/api/cursos/{curso}/asignaciones",
                       json={"asignaciones": filas}, headers=TOK[quien])


def foto(curso=None):
    """Retrato del estado: (id, profesor, asignatura, activo, titular)."""
    d = SessionLocal()
    try:
        q = d.query(M.AsignacionProfesor)
        if curso is not None:
            q = q.filter_by(curso_id=curso)
        return sorted((a.id, a.profesor_id, a.asignatura_id, a.activo, bool(a.es_titular))
                      for a in q.all())
    finally:
        d.close()


def total_filas():
    d = SessionLocal()
    try:
        return d.query(M.AsignacionProfesor).count()
    finally:
        d.close()


PAYLOAD_SEC = [
    {"profesor_id": U_P1, "asignatura_id": A_LENGUA, "es_titular": True},
    {"profesor_id": U_P2, "asignatura_id": A_SOCIALES, "es_titular": False},
    {"profesor_id": U_P4, "asignatura_id": A_INGLES, "es_titular": False},
    {"profesor_id": U_P4, "asignatura_id": A_FRANCES, "es_titular": False},
    {"profesor_id": None, "asignatura_id": A_MUSICA, "es_titular": False},
]


# ===========================================================================
# 1 · 2 · 6 — IDEMPOTENCIA
# ===========================================================================

@test("§1 Guardar SIN cambios -> cero cambios de datos")
def _():
    antes, antes_tot = foto(CUR_SEC), total_filas()
    r = guardar(CUR_SEC, PAYLOAD_SEC)
    assert r.status_code == 200, (r.status_code, r.text[:250])
    j = r.json()
    assert j["creadas"] == 0 and j["reactivadas"] == 0 and j["retiradas"] == 0, j
    assert j["sin_cambio"] == 4, j
    assert foto(CUR_SEC) == antes, "la foto del curso cambio"
    assert total_filas() == antes_tot, "aparecieron filas nuevas"


@test("§2 ...y los IDs son EXACTAMENTE los mismos")
def _():
    antes = foto(CUR_SEC)
    for _ in range(3):
        assert guardar(CUR_SEC, PAYLOAD_SEC).status_code == 200
    despues = foto(CUR_SEC)
    assert despues == antes, ("tres guardados seguidos movieron algo",
                              antes, despues)
    ids_activos = {f[0] for f in despues if f[3]}
    assert ids_activos == {1, 2, 3, 4}, ids_activos


@test("§3 Agregar UNA asignacion crea solo esa relacion")
def _():
    antes_tot = total_filas()
    payload = PAYLOAD_SEC[:4] + [
        {"profesor_id": U_P2, "asignatura_id": A_MUSICA, "es_titular": False}]
    r = guardar(CUR_SEC, payload)
    assert r.status_code == 200, r.text[:250]
    j = r.json()
    assert j["creadas"] == 1 and j["reactivadas"] == 0 and j["retiradas"] == 0, j
    assert total_filas() == antes_tot + 1, "creo mas de una fila"
    # las cuatro originales intactas
    d = SessionLocal()
    try:
        for i in (1, 2, 3, 4):
            assert d.query(M.AsignacionProfesor).get(i).activo is True
    finally:
        d.close()


@test("§4 Cambiar el profesor de una materia: alta + baja, sin destruir historia")
def _():
    payload = [
        {"profesor_id": U_P2, "asignatura_id": A_LENGUA, "es_titular": True},
        {"profesor_id": U_P2, "asignatura_id": A_SOCIALES, "es_titular": False},
        {"profesor_id": U_P4, "asignatura_id": A_INGLES, "es_titular": False},
        {"profesor_id": U_P4, "asignatura_id": A_FRANCES, "es_titular": False},
        {"profesor_id": U_P2, "asignatura_id": A_MUSICA, "es_titular": False},
    ]
    r = guardar(CUR_SEC, payload)
    assert r.status_code == 200, r.text[:250]
    j = r.json()
    assert j["creadas"] == 1 and j["retiradas"] == 1, j
    d = SessionLocal()
    try:
        vieja = d.query(M.AsignacionProfesor).get(1)   # P1 / Lengua
        assert vieja is not None, "la fila del profesor saliente se BORRO"
        assert vieja.activo is False, "deberia quedar desactivada"
        assert vieja.profesor_id == U_P1, "se falsifico el autor historico"
        nueva = d.query(M.AsignacionProfesor).filter_by(
            curso_id=CUR_SEC, asignatura_id=A_LENGUA, activo=True).one()
        assert nueva.profesor_id == U_P2
    finally:
        d.close()


@test("§5 Reactivar una equivalente INACTIVA conserva su ID")
def _():
    # devolver Lengua a P1: existe la fila 1 inactiva
    r = guardar(CUR_SEC, [
        {"profesor_id": U_P1, "asignatura_id": A_LENGUA, "es_titular": True},
        {"profesor_id": U_P2, "asignatura_id": A_SOCIALES, "es_titular": False},
        {"profesor_id": U_P4, "asignatura_id": A_INGLES, "es_titular": False},
        {"profesor_id": U_P4, "asignatura_id": A_FRANCES, "es_titular": False},
        {"profesor_id": U_P2, "asignatura_id": A_MUSICA, "es_titular": False},
    ])
    assert r.status_code == 200, r.text[:250]
    j = r.json()
    assert j["reactivadas"] == 1 and j["creadas"] == 0, j
    d = SessionLocal()
    try:
        fila = d.query(M.AsignacionProfesor).get(1)
        assert fila.activo is True, "debio reactivarse la fila 1"
        assert d.query(M.AsignacionProfesor).filter_by(
            curso_id=CUR_SEC, asignatura_id=A_LENGUA, activo=True).count() == 1, \
            "hay dos activas para la misma materia"
    finally:
        d.close()


# ===========================================================================
# 6 · 7 · 8 — NIVELES
# ===========================================================================

@test("§6 Profesor de PRIMARIA: el curso de primaria se guarda con normalidad")
def _():
    r = guardar(CUR_PRI, [
        {"profesor_id": U_P1, "asignatura_id": A_LENGUA, "es_titular": True},
        {"profesor_id": U_PRI, "asignatura_id": A_SOCIALES, "es_titular": False},
    ])
    assert r.status_code == 200, r.text[:250]
    assert r.json()["sin_cambio"] == 2, r.json()


@test("§7 Profesor de SECUNDARIA: sin interferencia entre niveles")
def _():
    antes_pri = foto(CUR_PRI)
    assert guardar(CUR_SEC, PAYLOAD_SEC[:4] + [
        {"profesor_id": U_P2, "asignatura_id": A_MUSICA}]).status_code == 200
    assert foto(CUR_PRI) == antes_pri, "guardar Secundaria toco Primaria"


@test("§8 El MISMO profesor trabaja en Primaria Y Secundaria a la vez")
def _():
    d = SessionLocal()
    try:
        suyas = d.query(M.AsignacionProfesor).filter_by(
            profesor_id=U_P1, activo=True).all()
        niveles = set()
        for a in suyas:
            c = d.query(M.Curso).get(a.curso_id)
            g = d.query(M.Grado).get(c.grado_id)
            niveles.add(g.nivel)
        assert niveles == {"primaria", "secundaria"}, niveles
    finally:
        d.close()


@test("§9 Dos materias del MISMO profesor en el MISMO curso se conservan ambas")
def _():
    d = SessionLocal()
    try:
        suyas = d.query(M.AsignacionProfesor).filter_by(
            profesor_id=U_P4, curso_id=CUR_SEC, activo=True).all()
        assert {a.asignatura_id for a in suyas} == {A_INGLES, A_FRANCES}, \
            [a.asignatura_id for a in suyas]
    finally:
        d.close()


# ===========================================================================
# 10 · 11 · 12 · 13 · 14 — VALIDACION DE ENTRADA
# ===========================================================================

@test("§10 Cross-tenant PROFESOR: 404 y no escribe nada")
def _():
    antes, antes_tot = foto(CUR_SEC), total_filas()
    r = guardar(CUR_SEC, PAYLOAD_SEC[:3] + [
        {"profesor_id": U_P_B, "asignatura_id": A_MUSICA}])
    assert r.status_code == 404, (r.status_code, r.text[:200])
    assert foto(CUR_SEC) == antes and total_filas() == antes_tot


@test("§11 Cross-tenant ASIGNATURA: 404 y no escribe nada")
def _():
    antes, antes_tot = foto(CUR_SEC), total_filas()
    r = guardar(CUR_SEC, PAYLOAD_SEC[:3] + [
        {"profesor_id": U_P1, "asignatura_id": A_B}])
    assert r.status_code == 404, (r.status_code, r.text[:200])
    assert foto(CUR_SEC) == antes and total_filas() == antes_tot


@test("§12 Usuario que NO es profesor en el payload: 400")
def _():
    antes = foto(CUR_SEC)
    for uid in (U_SEC_ROL, U_PSI, U_DIR):
        r = guardar(CUR_SEC, PAYLOAD_SEC[:3] + [
            {"profesor_id": uid, "asignatura_id": A_MUSICA}])
        assert r.status_code == 400, (uid, r.status_code, r.text[:200])
        assert "rol profesor" in r.json().get("error", ""), r.json()
    assert foto(CUR_SEC) == antes


@test("§13 IDs inexistentes: 404 controlado, NUNCA 500")
def _():
    antes = foto(CUR_SEC)
    r = guardar(CUR_SEC, [{"profesor_id": 999999, "asignatura_id": A_LENGUA}])
    assert r.status_code == 404, (r.status_code, r.text[:200])
    r = guardar(CUR_SEC, [{"profesor_id": U_P1, "asignatura_id": 999999}])
    assert r.status_code == 404, (r.status_code, r.text[:200])
    r = client.post("/api/cursos/999999/asignaciones",
                    json={"asignaciones": []}, headers=TOK["dir"])
    assert r.status_code == 404, r.status_code
    # falta asignatura_id -> 400, no la excepcion 500 de antes
    r = guardar(CUR_SEC, [{"profesor_id": U_P1}])
    assert r.status_code == 400, (r.status_code, r.text[:200])
    assert "asignatura_id" in r.json().get("error", ""), r.json()
    # tipos basura
    r = guardar(CUR_SEC, [{"profesor_id": "x", "asignatura_id": A_LENGUA}])
    assert r.status_code == 400, r.status_code
    r = guardar(CUR_SEC, ["no soy un objeto"])
    assert r.status_code == 400, r.status_code
    r = client.post(f"/api/cursos/{CUR_SEC}/asignaciones",
                    json={"asignaciones": "texto"}, headers=TOK["dir"])
    assert r.status_code == 400, r.status_code
    assert foto(CUR_SEC) == antes


@test("§14 Payload con duplicados: exacto se normaliza, contradictorio se rechaza")
def _():
    # mismo par repetido: se normaliza, no falla
    r = guardar(CUR_SEC, PAYLOAD_SEC + [
        {"profesor_id": U_P1, "asignatura_id": A_LENGUA, "es_titular": True}])
    assert r.status_code == 200, (r.status_code, r.text[:250])
    # ...y repetirlo es idempotente: el duplicado exacto no genera nada
    r2 = guardar(CUR_SEC, PAYLOAD_SEC + [
        {"profesor_id": U_P1, "asignatura_id": A_LENGUA, "es_titular": True}])
    assert r2.json()["creadas"] == 0 and r2.json()["retiradas"] == 0, r2.json()

    # la foto se toma AQUI: lo anterior son guardados validos que si cambian
    antes = foto(CUR_SEC)
    # dos docentes distintos para la misma materia: rechazo determinista
    r = guardar(CUR_SEC, [
        {"profesor_id": U_P1, "asignatura_id": A_LENGUA},
        {"profesor_id": U_P2, "asignatura_id": A_LENGUA},
    ])
    assert r.status_code == 400, (r.status_code, r.text[:250])
    assert "dos docentes" in r.json().get("error", ""), r.json()
    assert foto(CUR_SEC) == antes, "un rechazo dejo rastro"


# ===========================================================================
# 15 — SALIDA OPTATIVA
# ===========================================================================

@test("§15 Salida Optativa PROTEGIDA: no se puede retirar desde esta pantalla")
def _():
    # payload que OMITE el componente optativo: debe conservarse igualmente
    r = guardar(CUR_OPT, [
        {"profesor_id": U_P1, "asignatura_id": A_LENGUA, "es_titular": True}])
    assert r.status_code == 200, (r.status_code, r.text[:250])
    j = r.json()
    assert j["retiradas"] == 0, j
    assert len(j["protegidas_salida_optativa"]) == 1, j
    assert j["protegidas_salida_optativa"][0]["asignatura_id"] == A_OPTATIVA, j
    assert "Salida Optativa" in j["message"], j["message"]
    d = SessionLocal()
    try:
        fila = d.query(M.AsignacionProfesor).get(9)
        assert fila.activo is True, "se retiro la asignacion del componente"
    finally:
        d.close()


@test("§15b Un mapeo LEGACY sobre una troncal NO protege a la troncal")
def _():
    # (CUR_OPT, A_LENGUA) tiene mapeo activo HCS-CS-4, pero Lengua es troncal:
    # esa asignacion es del profesor de Lengua y Direccion debe poder moverla.
    r = guardar(CUR_OPT, [
        {"profesor_id": U_P2, "asignatura_id": A_LENGUA, "es_titular": True}])
    assert r.status_code == 200, (r.status_code, r.text[:250])
    j = r.json()
    assert j["creadas"] == 1 and j["retiradas"] == 1, j
    d = SessionLocal()
    try:
        assert d.query(M.AsignacionProfesor).get(8).activo is False
        assert d.query(M.AsignacionProfesor).get(9).activo is True, \
            "el componente real debe seguir protegido"
    finally:
        d.close()
    # restaurar
    guardar(CUR_OPT, [{"profesor_id": U_P1, "asignatura_id": A_LENGUA,
                       "es_titular": True}])


# ===========================================================================
# 16 · 17 · 18 · 19 — DEPENDENCIAS
# ===========================================================================

@test("§16 Una baja que dejaria HORARIOS huerfanos aborta el guardado entero")
def _():
    d = SessionLocal()
    try:
        h = M.Horario(colegio_id=COL_A, profesor_id=U_P4, curso_id=CUR_SEC,
                      asignatura_id=A_FRANCES, dia="Lunes", hora_inicio="07:40",
                      hora_fin="08:15", tipo_bloque="clase", activo=True)
        d.add(h)
        d.commit()
        hid = h.id
    finally:
        d.close()
    antes, antes_tot = foto(CUR_SEC), total_filas()
    # payload que omite P4/Frances
    r = guardar(CUR_SEC, [
        {"profesor_id": U_P1, "asignatura_id": A_LENGUA, "es_titular": True},
        {"profesor_id": U_P2, "asignatura_id": A_SOCIALES},
        {"profesor_id": U_P4, "asignatura_id": A_INGLES},
        {"profesor_id": U_P2, "asignatura_id": A_MUSICA},
    ])
    assert r.status_code == 409, (r.status_code, r.text[:300])
    assert hid in r.json().get("horarios", []), r.json()
    assert foto(CUR_SEC) == antes and total_filas() == antes_tot, \
        "el 409 dejo rastro en la base"


@test("§16b Un bloque YA huerfano no bloquea: solo se mira lo que se empeora")
def _():
    d = SessionLocal()
    try:
        # bloque de Musica sin ninguna asignacion que lo respalde (caso real)
        d.add(M.Horario(colegio_id=COL_A, profesor_id=U_PRI, curso_id=CUR_SEC,
                        asignatura_id=A_MUSICA, dia="Martes", hora_inicio="09:00",
                        hora_fin="09:45", tipo_bloque="clase", activo=True))
        d.commit()
    finally:
        d.close()
    r = guardar(CUR_SEC, PAYLOAD_SEC[:4] + [
        {"profesor_id": U_P2, "asignatura_id": A_MUSICA}])
    assert r.status_code == 200, (r.status_code, r.text[:300])


@test("§17 Una baja NO borra las calificaciones y las informa")
def _():
    d = SessionLocal()
    try:
        d.add(M.CalificacionSecundaria(colegio_id=COL_A, estudiante_id=EST_SEC,
                                       asignatura_id=A_SOCIALES,
                                       competencia_numero=1, ano_escolar_id=ANO_A,
                                       p1=85))
        d.commit()
        n_antes = d.query(M.CalificacionSecundaria).filter_by(
            asignatura_id=A_SOCIALES).count()
    finally:
        d.close()
    r = guardar(CUR_SEC, [
        {"profesor_id": U_P1, "asignatura_id": A_LENGUA, "es_titular": True},
        {"profesor_id": U_P4, "asignatura_id": A_INGLES},
        {"profesor_id": U_P4, "asignatura_id": A_FRANCES},
        {"profesor_id": U_P2, "asignatura_id": A_MUSICA},
    ])
    assert r.status_code == 200, (r.status_code, r.text[:300])
    assert r.json()["retiradas"] == 1, r.json()
    assert r.json()["historico_conservado"]["calificaciones"] == n_antes, r.json()
    d = SessionLocal()
    try:
        assert d.query(M.CalificacionSecundaria).filter_by(
            asignatura_id=A_SOCIALES).count() == n_antes, "SE BORRARON NOTAS"
    finally:
        d.close()


@test("§18 Una baja NO borra la asistencia y la informa")
def _():
    d = SessionLocal()
    try:
        d.add(M.Asistencia(colegio_id=COL_A, estudiante_id=EST_SEC, curso_id=CUR_SEC,
                           asignatura_id=A_MUSICA, fecha=date(2026, 3, 3),
                           estado="presente"))
        d.commit()
        n_antes = d.query(M.Asistencia).filter_by(asignatura_id=A_MUSICA).count()
    finally:
        d.close()
    r = guardar(CUR_SEC, [
        {"profesor_id": U_P1, "asignatura_id": A_LENGUA, "es_titular": True},
        {"profesor_id": U_P4, "asignatura_id": A_INGLES},
        {"profesor_id": U_P4, "asignatura_id": A_FRANCES},
    ])
    assert r.status_code == 200, (r.status_code, r.text[:300])
    assert r.json()["historico_conservado"]["asistencias"] == n_antes, r.json()
    d = SessionLocal()
    try:
        assert d.query(M.Asistencia).filter_by(
            asignatura_id=A_MUSICA).count() == n_antes, "SE BORRO ASISTENCIA"
    finally:
        d.close()


@test("§19 Una baja SIN dependencias se desactiva limpiamente, sin borrarse")
def _():
    d = SessionLocal()
    try:
        antes_tot = d.query(M.AsignacionProfesor).count()
        fila = d.query(M.AsignacionProfesor).filter_by(
            curso_id=CUR_SEC, asignatura_id=A_INGLES, activo=True).one()
        fid = fila.id
    finally:
        d.close()
    r = guardar(CUR_SEC, [
        {"profesor_id": U_P1, "asignatura_id": A_LENGUA, "es_titular": True},
        {"profesor_id": U_P4, "asignatura_id": A_FRANCES},
    ])
    assert r.status_code == 200, (r.status_code, r.text[:300])
    d = SessionLocal()
    try:
        f = d.query(M.AsignacionProfesor).get(fid)
        assert f is not None, "la fila se BORRO en vez de desactivarse"
        assert f.activo is False
        assert d.query(M.AsignacionProfesor).count() == antes_tot, \
            "la baja creo filas"
    finally:
        d.close()


@test("§20 Atomicidad: un fallo a mitad no deja NADA escrito")
def _():
    antes, antes_tot = foto(CUR_SEC), total_filas()
    # payload con altas validas y un profesor de otro colegio al final
    r = guardar(CUR_SEC, [
        {"profesor_id": U_P1, "asignatura_id": A_LENGUA, "es_titular": True},
        {"profesor_id": U_P2, "asignatura_id": A_SOCIALES},
        {"profesor_id": U_P2, "asignatura_id": A_MUSICA},
        {"profesor_id": U_P_B, "asignatura_id": A_INGLES},
    ])
    assert r.status_code == 404, (r.status_code, r.text[:250])
    assert foto(CUR_SEC) == antes, "se aplico parte del payload"
    assert total_filas() == antes_tot


# ===========================================================================
# CONTRATO Y ROLES — lo que NO debe cambiar
# ===========================================================================

@test("§21 Roles: sigue siendo Direccion quien guarda")
def _():
    for u in ("sec", "psi", "p1"):
        r = guardar(CUR_SEC, PAYLOAD_SEC, quien=u)
        assert r.status_code == 403, (u, r.status_code)


@test("§22 Cross-tenant de CURSO: 404 sin revelar existencia")
def _():
    r = guardar(CUR_B, [{"profesor_id": U_P1, "asignatura_id": A_LENGUA}])
    assert r.status_code == 404, (r.status_code, r.text[:200])
    r2 = client.post("/api/cursos/999999/asignaciones",
                     json={"asignaciones": []}, headers=TOK["dir"])
    assert r.status_code == r2.status_code
    d = SessionLocal()
    try:
        assert d.query(M.AsignacionProfesor).get(20).activo is True
    finally:
        d.close()


@test("§23 es_titular se puede ajustar sin recrear la fila")
def _():
    d = SessionLocal()
    try:
        fila = d.query(M.AsignacionProfesor).filter_by(
            curso_id=CUR_SEC, asignatura_id=A_LENGUA, activo=True).one()
        fid, tit_antes = fila.id, bool(fila.es_titular)
    finally:
        d.close()
    r = guardar(CUR_SEC, [
        {"profesor_id": U_P1, "asignatura_id": A_LENGUA, "es_titular": not tit_antes},
        {"profesor_id": U_P4, "asignatura_id": A_FRANCES},
    ])
    assert r.status_code == 200, r.text[:250]
    assert r.json()["titular_ajustado"] == 1, r.json()
    d = SessionLocal()
    try:
        f = d.query(M.AsignacionProfesor).get(fid)
        assert bool(f.es_titular) == (not tit_antes)
        assert f.id == fid, "cambiar titular recreo la fila"
    finally:
        d.close()


@test("§24 El GET del formulario sigue devolviendo el mismo contrato")
def _():
    r = client.get(f"/api/cursos/{CUR_SEC}/asignaciones", headers=TOK["dir"])
    assert r.status_code == 200, r.status_code
    j = r.json()
    assert set(j) >= {"curso", "curso_id", "asignaciones"}, list(j)
    assert j["asignaciones"], "no devolvio filas"
    fila = j["asignaciones"][0]
    assert set(fila) >= {"asignatura_id", "asignatura", "profesor_id",
                         "profesor", "es_titular"}, list(fila)


@test("§25 NINGUNA generacion inactiva nueva tras muchos guardados")
def _():
    d = SessionLocal()
    try:
        antes = d.query(M.AsignacionProfesor).filter_by(
            curso_id=CUR_PRI).count()
    finally:
        d.close()
    payload = [
        {"profesor_id": U_P1, "asignatura_id": A_LENGUA, "es_titular": True},
        {"profesor_id": U_PRI, "asignatura_id": A_SOCIALES, "es_titular": False},
    ]
    for _ in range(6):
        assert guardar(CUR_PRI, payload).status_code == 200
    d = SessionLocal()
    try:
        despues = d.query(M.AsignacionProfesor).filter_by(curso_id=CUR_PRI).count()
        assert despues == antes, (
            "seis guardados crearon %d filas nuevas" % (despues - antes))
    finally:
        d.close()


@test("§ZZ sge.db del repo intacto")
def _():
    a = os.path.getmtime(_REPO_SGE) if os.path.exists(_REPO_SGE) else None
    assert a == _sge_mtime, "sge.db fue modificado"


print("\n" + "=" * 70)
print(f"{B}FASE 1 ASIGNACIONES: {_ok}/{_total} pruebas{X}")
if _fail:
    print(f"{R}FALLARON:{X}")
    for n, e in _fail:
        print(f"  - {n}: {e}")
    sys.exit(1)
print(f"{G}TODO VERDE{X}")
