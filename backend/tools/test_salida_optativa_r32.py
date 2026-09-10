# -*- coding: utf-8 -*-
"""
EducaOne R3.2 — CONFIGURACIÓN DE SALIDA OPTATIVA POR CURSO.

Cubre los 22 puntos de R3.2 §16 en cuatro bloques:

  A. PERMISOS Y ALCANCE — quién configura, y sobre qué cursos existe siquiera
     la Salida Optativa (solo 4to-6to de Secundaria).
  B. VALIDACIÓN — catálogo, pertenencia del componente a la salida, tenant de
     la asignatura.
  C. PERSISTENCIA — el mapeo se guarda, es idempotente, y es independiente por
     curso y por año escolar.
  D. ZERO DATA LOSS — la guarda de historia académica: sin historia se puede
     remapear, con historia se bloquea con 409 y NO se borra ni un dato.

SEGURIDAD: SQLite temporal aislada. NUNCA toca sge.db ni INITIAL_CREDENTIALS.txt
(se verifica al final). No consulta producción ni PostgreSQL.

Uso:
    cd backend
    python tools/test_salida_optativa_r32.py
"""
import os
import sys
import atexit
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TMPDIR = tempfile.mkdtemp(prefix="eo_salida_opt_r32_")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_TMPDIR, "s.db").replace("\\", "/")
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
import salidas_optativas as CAT                                # noqa: E402

_eu = str(engine.url).replace("\\", "/")
assert _TMPDIR.replace("\\", "/") in _eu and "sge.db" not in _eu, _eu

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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


# --------------------------------------------------------------------------
# FIXTURE
# --------------------------------------------------------------------------
COL_A, COL_B = 1, 2
ANO_A1, ANO_B, ANO_A2 = 1, 2, 3

G1RO, G4TO, G5TO, G6TO, G4PRIM = 1, 4, 5, 6, 40
# cursos del colegio A, año 1
C1RO, C4_A, C4_A2SEC, C5, C6, CPRIM = 10, 14, 15, 16, 17, 18
# mismo grado 4to del colegio A pero en OTRO año escolar
C4_ANO2 = 19
# curso del colegio B
C4_B = 20

# asignaturas del colegio A (las que Dirección puede elegir como componentes)
A_LIT, A_ING, A_MATFIN, A_FILO, A_BIOCOMP, A_MUSICA = 101, 102, 103, 104, 105, 106
A_B_LIT = 201                    # asignatura del colegio B (tenant ajeno)
A_INACTIVA = 107

U_DIR_A, U_PROF_A, U_COORD_A, U_DIR_B = 30, 31, 32, 33
EST_1, EST_2 = 500, 501
PWD = "Prueba2026x"

# Componentes reales del catálogo R3.1 para 4to (NO se inventan)
HLM_LE_4, HLM_IN_4 = "HLM-LE-4", "HLM-IN-4"
HCS_LE_4, HCS_CS_4 = "HCS-LE-4", "HCS-CS-4"
MYT_MA_4, CYT_CN_4 = "MYT-MA-4", "CYT-CN-4"


def _seed():
    M.Base.metadata.drop_all(bind=engine)
    M.Base.metadata.create_all(bind=engine)
    d = SessionLocal()
    try:
        for cid, nom in ((COL_A, "Colegio A"), (COL_B, "Colegio B")):
            d.add(M.Colegio(id=cid, nombre=nom, codigo=nom[-1].lower()))
            d.add(M.ConfiguracionColegio(colegio_id=cid, nombre=nom, regional="10",
                                         distrito="03", codigo_centro="0000%d" % cid,
                                         usa_secundaria=True))
        d.add(M.AnoEscolar(id=ANO_A1, colegio_id=COL_A, nombre="2025-2026",
                           activo=True, dias_trabajados="{}"))
        d.add(M.AnoEscolar(id=ANO_A2, colegio_id=COL_A, nombre="2026-2027",
                           activo=False, dias_trabajados="{}"))
        d.add(M.AnoEscolar(id=ANO_B, colegio_id=COL_B, nombre="2025-2026",
                           activo=True, dias_trabajados="{}"))

        for gid, nom, niv, orden, col in (
                (G1RO, "1ro Secundaria", "secundaria", 1, COL_A),
                (G4TO, "4to Secundaria", "secundaria", 4, COL_A),
                (G5TO, "5to Secundaria", "secundaria", 5, COL_A),
                (G6TO, "6to Secundaria", "secundaria", 6, COL_A),
                (G4PRIM, "4to Primaria", "primaria", 4, COL_A),
                (G4TO + 100, "4to Secundaria", "secundaria", 4, COL_B)):
            d.add(M.Grado(id=gid, colegio_id=col, nombre=nom, nivel=niv, orden=orden))

        for cid, nom, gid, ano, col in (
                (C1RO, "A", G1RO, ANO_A1, COL_A),
                (C4_A, "A", G4TO, ANO_A1, COL_A),
                (C4_A2SEC, "B", G4TO, ANO_A1, COL_A),     # otra sección de 4to
                (C5, "A", G5TO, ANO_A1, COL_A),
                (C6, "A", G6TO, ANO_A1, COL_A),
                (CPRIM, "A", G4PRIM, ANO_A1, COL_A),
                (C4_ANO2, "A", G4TO, ANO_A2, COL_A),      # mismo grado, otro año
                (C4_B, "A", G4TO + 100, ANO_B, COL_B)):
            d.add(M.Curso(id=cid, colegio_id=col, nombre=nom, grado_id=gid,
                          ano_escolar_id=ano, activo=True))

        for aid, nom in ((A_LIT, "Apreciación Literaria"), (A_ING, "Inglés Optativo"),
                         (A_MATFIN, "Matemática Financiera"), (A_FILO, "Filosofía Social"),
                         (A_BIOCOMP, "Biología y Computación"), (A_MUSICA, "Música")):
            d.add(M.Asignatura(id=aid, colegio_id=COL_A, nombre=nom, codigo="X",
                               area="", activo=True))
        d.add(M.Asignatura(id=A_INACTIVA, colegio_id=COL_A, nombre="Retirada",
                           codigo="X", area="", activo=False))
        d.add(M.Asignatura(id=A_B_LIT, colegio_id=COL_B, nombre="Apreciación Literaria",
                           codigo="X", area="", activo=True))

        for uid, un, rol, col in ((U_DIR_A, "dir_a", "direccion", COL_A),
                                  (U_PROF_A, "prof_a", "profesor", COL_A),
                                  (U_COORD_A, "coord_a", "coordinador", COL_A),
                                  (U_DIR_B, "dir_b", "direccion", COL_B)):
            u = M.Usuario(id=uid, username=un, nombre=un, apellido="T", role=rol,
                          colegio_id=col)
            u.set_password(PWD)
            d.add(u)

        for eid in (EST_1, EST_2):
            d.add(M.Estudiante(id=eid, colegio_id=COL_A, nombre="Est%d" % eid,
                               apellido="T", curso_id=C4_A, activo=True))
        d.commit()
    finally:
        d.close()


def login(u):
    r = client.post("/api/auth/login", json={"username": u, "password": PWD})
    assert r.status_code == 200, f"login {u}: {r.status_code} {r.text[:160]}"
    return r.json()["token"]


def auth(t):
    return {"Authorization": f"Bearer {t}"}


def get(curso, tok):
    return client.get(f"/api/cursos/{curso}/salida-optativa", headers=auth(tok))


def put(curso, tok, **body):
    return client.put(f"/api/cursos/{curso}/salida-optativa", json=body, headers=auth(tok))


def borrar(curso, codigo, tok):
    return client.delete(f"/api/cursos/{curso}/salida-optativa/componentes/{codigo}",
                         headers=auth(tok))


def mapeos(curso):
    d = SessionLocal()
    try:
        return {m.componente_codigo: m.asignatura_id
                for m in d.query(M.CursoComponenteOptativo).filter(
                    M.CursoComponenteOptativo.curso_id == curso,
                    M.CursoComponenteOptativo.activo == True).all()}    # noqa: E712
    finally:
        d.close()


_seed()
DIR_A = login("dir_a")
PROF_A = login("prof_a")
COORD_A = login("coord_a")
DIR_B = login("dir_b")


# ===========================================================================
# BLOQUE A — PERMISOS Y ALCANCE
# ===========================================================================

@test("§1 Dirección puede configurar la Salida Optativa de un 4to")
def _():
    r = put(C4_A, DIR_A, salida_optativa_codigo="HLM")
    assert r.status_code == 200, r.text[:250]
    d = r.json()
    assert d["salida_optativa_codigo"] == "HLM", d
    assert d["aplica"] is True and d["grado_numero"] == 4, d
    # los componentes ofrecidos son EXACTAMENTE los del catálogo oficial
    esperados = [c.codigo for c in CAT.componentes_de("HLM", 4)]
    assert [c["componente_codigo"] for c in d["componentes"]] == esperados, d["componentes"]


@test("§2 el profesor recibe 403 al leer y al configurar")
def _():
    assert get(C4_A, PROF_A).status_code == 403
    assert put(C4_A, PROF_A, salida_optativa_codigo="HCS").status_code == 403
    assert borrar(C4_A, HLM_LE_4, PROF_A).status_code == 403
    assert mapeos(C4_A) == {}, "un 403 no debe haber tocado nada"


@test("§3 el coordinador recibe 403 (no tiene Configuración)")
def _():
    assert get(C4_A, COORD_A).status_code == 403
    assert put(C4_A, COORD_A, salida_optativa_codigo="HCS").status_code == 403
    assert borrar(C4_A, HLM_LE_4, COORD_A).status_code == 403


@test("§4 otro tenant no ve ni configura el curso ajeno")
def _():
    assert get(C4_A, DIR_B).status_code == 404
    assert put(C4_A, DIR_B, salida_optativa_codigo="CYT").status_code == 404
    assert borrar(C4_A, HLM_LE_4, DIR_B).status_code == 404
    d = SessionLocal()
    try:
        assert d.query(M.Curso).get(C4_A).salida_optativa_codigo == "HLM", \
            "el tenant ajeno no debe haber cambiado la salida"
    finally:
        d.close()


@test("§5 un curso de PRIMARIA no tiene Salida Optativa")
def _():
    d = get(CPRIM, DIR_A).json()
    assert d["aplica"] is False and d["grado_numero"] is None, d
    r = put(CPRIM, DIR_A, salida_optativa_codigo="HLM")
    assert r.status_code == 400, r.text[:200]
    assert "4to a 6to" in r.json()["error"], r.json()


@test("§6 1ro-3ro de Secundaria tampoco la tienen")
def _():
    d = get(C1RO, DIR_A).json()
    assert d["aplica"] is False and d["grado_numero"] == 1, d
    r = put(C1RO, DIR_A, salida_optativa_codigo="HLM")
    assert r.status_code == 400, r.text[:200]


@test("§7 §8 §9 4to, 5to y 6to sí la admiten, cada uno con SU componente")
def _():
    for curso, grado in ((C4_A, 4), (C5, 5), (C6, 6)):
        r = put(curso, DIR_A, salida_optativa_codigo="CYT")
        assert r.status_code == 200, (curso, r.text[:200])
        d = r.json()
        assert d["grado_numero"] == grado and d["aplica"] is True, d
        # el componente CYT de cada grado es distinto y sale del catálogo
        codigos = [c["componente_codigo"] for c in d["componentes"]]
        assert codigos == ["CYT-CN-%d" % grado], (grado, codigos)


# ===========================================================================
# BLOQUE B — VALIDACIÓN
# ===========================================================================

@test("§10 una salida que no existe en el catálogo se rechaza")
def _():
    r = put(C4_A, DIR_A, salida_optativa_codigo="ZZZ")
    assert r.status_code == 400, r.text[:200]
    assert "desconocida" in r.json()["error"].lower(), r.json()
    # y el nombre oficial tampoco vale como código
    assert put(C4_A, DIR_A, salida_optativa_codigo="Ciencias y Tecnología").status_code == 400


@test("§11 un componente que no pertenece a la salida se rechaza")
def _():
    put(C4_A, DIR_A, salida_optativa_codigo="HLM")
    # HCS-CS-4 existe, pero es de la salida HCS
    r = put(C4_A, DIR_A, componentes={HCS_CS_4: A_FILO})
    assert r.status_code == 400, r.text[:250]
    assert "HCS" in r.json()["error"], r.json()
    # y uno de OTRO GRADO tampoco (CYT-CN-5 en un 4to)
    r = put(C4_A, DIR_A, salida_optativa_codigo="CYT", componentes={"CYT-CN-5": A_BIOCOMP})
    assert r.status_code == 400, r.text[:250]
    # un código inventado tampoco
    r = put(C4_A, DIR_A, componentes={"XXX-YY-4": A_LIT})
    assert r.status_code == 400, r.text[:250]
    assert mapeos(C4_A) == {}, "ninguna validación fallida debe haber escrito"


@test("§12 una asignatura de otro colegio se rechaza (y no filtra ids)")
def _():
    put(C4_A, DIR_A, salida_optativa_codigo="HLM")
    r = put(C4_A, DIR_A, componentes={HLM_LE_4: A_B_LIT})
    assert r.status_code == 400, r.text[:250]
    assert "otro colegio" in r.json()["error"], r.json()
    # un id inexistente da un mensaje distinto pero tampoco escribe
    assert put(C4_A, DIR_A, componentes={HLM_LE_4: 999999}).status_code == 400
    # una asignatura INACTIVA del propio colegio tampoco sirve
    r = put(C4_A, DIR_A, componentes={HLM_LE_4: A_INACTIVA})
    assert r.status_code == 400 and "inactiva" in r.json()["error"], r.text[:250]
    assert mapeos(C4_A) == {}


@test("§11b una asignatura no puede representar dos componentes del mismo curso")
def _():
    put(C4_A, DIR_A, salida_optativa_codigo="HLM")
    r = put(C4_A, DIR_A, componentes={HLM_LE_4: A_LIT, HLM_IN_4: A_LIT})
    assert r.status_code == 400, r.text[:250]
    assert mapeos(C4_A) == {}


# ===========================================================================
# BLOQUE C — PERSISTENCIA
# ===========================================================================

@test("§13 un mapeo válido persiste y se reporta como configurado")
def _():
    r = put(C4_A, DIR_A, salida_optativa_codigo="HLM",
            componentes={HLM_LE_4: A_LIT, HLM_IN_4: A_ING})
    assert r.status_code == 200, r.text[:250]
    d = r.json()
    assert mapeos(C4_A) == {HLM_LE_4: A_LIT, HLM_IN_4: A_ING}, mapeos(C4_A)
    assert d["faltantes"] == [] and d["configurada"] is True, d
    # el nombre oficial viene del catálogo, no de la asignatura del colegio
    por_cod = {c["componente_codigo"]: c for c in d["componentes"]}
    assert por_cod[HLM_LE_4]["nombre_oficial"] == \
        CAT.componente(HLM_LE_4).nombre_oficial, por_cod
    assert por_cod[HLM_LE_4]["asignatura_nombre"] == "Apreciación Literaria", por_cod


def _ids_mapeos(curso):
    d = SessionLocal()
    try:
        return sorted(m.id for m in d.query(M.CursoComponenteOptativo).filter(
            M.CursoComponenteOptativo.curso_id == curso,
            M.CursoComponenteOptativo.activo == True).all())          # noqa: E712
    finally:
        d.close()


@test("§14 el guardado es IDEMPOTENTE")
def _():
    antes = mapeos(C4_A)
    ids_antes = _ids_mapeos(C4_A)
    for _ in range(3):
        r = put(C4_A, DIR_A, salida_optativa_codigo="HLM",
                componentes={HLM_LE_4: A_LIT, HLM_IN_4: A_ING})
        assert r.status_code == 200, r.text[:200]
    assert mapeos(C4_A) == antes, (antes, mapeos(C4_A))
    assert _ids_mapeos(C4_A) == ids_antes, "no debe crear filas nuevas al repetir"


@test("§14b faltan componentes: se reportan y NO se inventa nada")
def _():
    r = put(C4_A2SEC, DIR_A, salida_optativa_codigo="HLM",
            componentes={HLM_LE_4: A_LIT})
    assert r.status_code == 200, r.text[:250]
    d = r.json()
    assert d["faltantes"] == [HLM_IN_4], d
    assert d["configurada"] is False, d
    por_cod = {c["componente_codigo"]: c for c in d["componentes"]}
    assert por_cod[HLM_IN_4]["asignatura_id"] is None, por_cod
    assert por_cod[HLM_IN_4]["asignatura_nombre"] is None, por_cod


@test("§15 la configuración es INDEPENDIENTE por curso")
def _():
    # C4_A es HLM; su curso hermano C4_A2SEC pasa a CYT sin afectarlo
    r = put(C4_A2SEC, DIR_A, salida_optativa_codigo="CYT",
            componentes={CYT_CN_4: A_BIOCOMP})
    assert r.status_code == 200, r.text[:250]
    assert mapeos(C4_A2SEC) == {CYT_CN_4: A_BIOCOMP}, mapeos(C4_A2SEC)
    assert mapeos(C4_A) == {HLM_LE_4: A_LIT, HLM_IN_4: A_ING}, mapeos(C4_A)
    d = SessionLocal()
    try:
        assert d.query(M.Curso).get(C4_A).salida_optativa_codigo == "HLM"
        assert d.query(M.Curso).get(C4_A2SEC).salida_optativa_codigo == "CYT"
    finally:
        d.close()


@test("§16 la configuración es INDEPENDIENTE por año escolar")
def _():
    # C4_ANO2 es el mismo grado del mismo colegio, pero del año siguiente
    r = put(C4_ANO2, DIR_A, salida_optativa_codigo="MYT",
            componentes={MYT_MA_4: A_MATFIN})
    assert r.status_code == 200, r.text[:250]
    assert mapeos(C4_ANO2) == {MYT_MA_4: A_MATFIN}
    # el año anterior queda EXACTAMENTE igual
    assert mapeos(C4_A) == {HLM_LE_4: A_LIT, HLM_IN_4: A_ING}, mapeos(C4_A)
    d = SessionLocal()
    try:
        f = d.query(M.CursoComponenteOptativo).filter(
            M.CursoComponenteOptativo.curso_id == C4_ANO2,
            M.CursoComponenteOptativo.activo == True).first()          # noqa: E712
        assert f.ano_escolar_id == ANO_A2, f.ano_escolar_id
        assert f.colegio_id == COL_A, f.colegio_id
    finally:
        d.close()


@test("§17 configurar NO crea asignaturas nuevas")
def _():
    d = SessionLocal()
    try:
        antes = d.query(M.Asignatura).count()
    finally:
        d.close()
    put(C5, DIR_A, salida_optativa_codigo="CYT", componentes={"CYT-CN-5": A_BIOCOMP})
    put(C6, DIR_A, salida_optativa_codigo="HCS", componentes={"HCS-LE-6": A_LIT})
    d = SessionLocal()
    try:
        assert d.query(M.Asignatura).count() == antes, "no debe crear Asignaturas"
    finally:
        d.close()


@test("§18 configurar NO toca nombre/codigo/area/area_curricular_codigo")
def _():
    d = SessionLocal()
    try:
        a = d.query(M.Asignatura).get(A_LIT)
        antes = (a.nombre, a.codigo, a.area, a.area_curricular_codigo, a.activo)
    finally:
        d.close()
    put(C4_A, DIR_A, salida_optativa_codigo="HLM",
        componentes={HLM_LE_4: A_LIT, HLM_IN_4: A_ING})
    d = SessionLocal()
    try:
        a = d.query(M.Asignatura).get(A_LIT)
        ahora = (a.nombre, a.codigo, a.area, a.area_curricular_codigo, a.activo)
    finally:
        d.close()
    assert antes == ahora, (antes, ahora)
    assert ahora[3] is None, "la relación optativa es independiente de R2.1"


# ===========================================================================
# BLOQUE D — ZERO DATA LOSS
# ===========================================================================

def _crear_historia(asignatura_id, tabla="calificaciones_secundaria"):
    """Historia académica REAL sobre una asignatura del curso C4_A."""
    d = SessionLocal()
    try:
        if tabla == "calificaciones_secundaria":
            d.add(M.CalificacionSecundaria(
                colegio_id=COL_A, estudiante_id=EST_1, asignatura_id=asignatura_id,
                ano_escolar_id=ANO_A1, competencia_numero=1, p1=85.0))
        elif tabla == "asistencias":
            from datetime import date
            d.add(M.Asistencia(colegio_id=COL_A, estudiante_id=EST_1, curso_id=C4_A,
                               asignatura_id=asignatura_id, fecha=date(2026, 3, 2),
                               estado="presente"))
        d.commit()
    finally:
        d.close()


def _contar_historia():
    d = SessionLocal()
    try:
        return (d.query(M.CalificacionSecundaria).count(),
                d.query(M.EvaluacionExtraSecundaria).count(),
                d.query(M.Asistencia).count())
    finally:
        d.close()


@test("§19 SIN historia académica se puede cambiar de salida y remapear")
def _():
    put(C4_A, DIR_A, salida_optativa_codigo="HLM",
        componentes={HLM_LE_4: A_LIT, HLM_IN_4: A_ING})
    # cambio de salida completo
    r = put(C4_A, DIR_A, salida_optativa_codigo="HCS",
            componentes={HCS_LE_4: A_LIT, HCS_CS_4: A_FILO})
    assert r.status_code == 200, r.text[:250]
    assert mapeos(C4_A) == {HCS_LE_4: A_LIT, HCS_CS_4: A_FILO}, mapeos(C4_A)
    # Los mapeos de HLM se RETIRAN (R3.2 §8: se quita la relación, nunca la
    # Asignatura). Se borra la fila y no se marca `activo=False` porque las dos
    # UniqueConstraint de R3.1 no incluyen `activo`: una fila zombi impediría
    # volver a usar esa asignatura o ese componente en el curso.
    d = SessionLocal()
    try:
        viejos = d.query(M.CursoComponenteOptativo).filter(
            M.CursoComponenteOptativo.curso_id == C4_A,
            M.CursoComponenteOptativo.componente_codigo.in_([HLM_LE_4, HLM_IN_4])).all()
        assert viejos == [], "los mapeos de la salida anterior deben quedar retirados"
        # lo que NO puede desaparecer es la Asignatura
        for aid in (A_LIT, A_ING):
            assert d.query(M.Asignatura).get(aid) is not None, aid
    finally:
        d.close()
    # y remapear un componente a otra asignatura también se permite
    r = put(C4_A, DIR_A, componentes={HCS_CS_4: A_MUSICA})
    assert r.status_code == 200, r.text[:250]
    assert mapeos(C4_A)[HCS_CS_4] == A_MUSICA


@test("§20 CON historia académica, cambiar de salida se bloquea con 409")
def _():
    put(C4_A, DIR_A, salida_optativa_codigo="HCS",
        componentes={HCS_LE_4: A_LIT, HCS_CS_4: A_FILO})
    _crear_historia(A_LIT)                       # una nota real sobre A_LIT
    antes_map, antes_hist = mapeos(C4_A), _contar_historia()

    r = put(C4_A, DIR_A, salida_optativa_codigo="CYT")
    assert r.status_code == 409, r.text[:250]
    j = r.json()
    assert j["error"] == ("No se puede cambiar la Salida Optativa porque existen "
                          "datos académicos asociados a sus componentes."), j["error"]
    assert j["motivo"] == "historia_academica", j
    bloq = {b["componente_codigo"]: b for b in j["componentes_bloqueados"]}
    assert HCS_LE_4 in bloq, bloq
    assert "calificaciones_secundaria" in bloq[HCS_LE_4]["detalle"], bloq

    # NADA cambió
    assert mapeos(C4_A) == antes_map, (antes_map, mapeos(C4_A))
    assert _contar_historia() == antes_hist, "no se borró ni un dato"
    d = SessionLocal()
    try:
        assert d.query(M.Curso).get(C4_A).salida_optativa_codigo == "HCS", \
            "la salida no debe haber cambiado"
    finally:
        d.close()


@test("§20b CON historia, reescribir ESE mapeo también se bloquea con 409")
def _():
    antes_map, antes_hist = mapeos(C4_A), _contar_historia()
    r = put(C4_A, DIR_A, componentes={HCS_LE_4: A_MUSICA})
    assert r.status_code == 409, r.text[:250]
    assert mapeos(C4_A) == antes_map and _contar_historia() == antes_hist
    # pero un componente HERMANO sin historia sigue siendo editable
    r = put(C4_A, DIR_A, componentes={HCS_CS_4: A_MATFIN})
    assert r.status_code == 200, r.text[:250]
    assert mapeos(C4_A)[HCS_CS_4] == A_MATFIN
    assert mapeos(C4_A)[HCS_LE_4] == A_LIT, "el bloqueado sigue intacto"


@test("§21 quitar un mapeo con historia se bloquea; sin historia se permite")
def _():
    antes_hist = _contar_historia()
    r = borrar(C4_A, HCS_LE_4, DIR_A)
    assert r.status_code == 409, r.text[:250]
    assert r.json()["error"] == ("No se puede quitar este componente porque existen "
                                 "datos académicos asociados a la asignatura que lo "
                                 "imparte."), r.json()["error"]
    assert mapeos(C4_A)[HCS_LE_4] == A_LIT, "el vínculo debe seguir ahí"
    # el hermano sin historia sí se puede retirar
    r = borrar(C4_A, HCS_CS_4, DIR_A)
    assert r.status_code == 200, r.text[:250]
    assert HCS_CS_4 not in mapeos(C4_A)
    # ...y retirar el vínculo NO borra la Asignatura
    d = SessionLocal()
    try:
        assert d.query(M.Asignatura).get(A_MATFIN) is not None, "la Asignatura sigue viva"
    finally:
        d.close()
    assert _contar_historia() == antes_hist, "quitar un mapeo no toca la historia"


@test("§21b un componente no vinculado da 404, no 409 ni un borrado silencioso")
def _():
    assert borrar(C4_A, HCS_CS_4, DIR_A).status_code == 404
    assert borrar(C4_A, "CYT-CN-4", DIR_A).status_code == 404


@test("§22 la asistencia GENERAL del curso no cuenta como historia de materia")
def _():
    from datetime import date
    d = SessionLocal()
    try:
        # asistencia SIN asignatura: es del curso, no de una materia
        d.add(M.Asistencia(colegio_id=COL_A, estudiante_id=EST_2, curso_id=C4_A2SEC,
                           asignatura_id=None, fecha=date(2026, 3, 3), estado="presente"))
        d.commit()
    finally:
        d.close()
    # C4_A2SEC está en CYT->A_BIOCOMP y no tiene historia por asignatura
    r = put(C4_A2SEC, DIR_A, salida_optativa_codigo="MYT",
            componentes={MYT_MA_4: A_MATFIN})
    assert r.status_code == 200, r.text[:250]
    assert mapeos(C4_A2SEC) == {MYT_MA_4: A_MATFIN}


@test("§22b la asistencia POR ASIGNATURA sí cuenta como historia")
def _():
    _crear_historia(A_MATFIN, tabla="asistencias")   # sobre el curso C4_A
    put(C4_A, DIR_A, componentes={HCS_CS_4: A_MATFIN})
    antes = mapeos(C4_A)
    r = put(C4_A, DIR_A, componentes={HCS_CS_4: A_MUSICA})
    assert r.status_code == 409, r.text[:250]
    assert "asistencias" in r.json()["componentes_bloqueados"][0]["detalle"], r.json()
    assert mapeos(C4_A) == antes


@test("§22c ningún dato académico se perdió en toda la suite")
def _():
    d = SessionLocal()
    try:
        assert d.query(M.CalificacionSecundaria).count() >= 1
        assert d.query(M.Asistencia).count() >= 2
        # y ninguna asignatura fue borrada ni desactivada por la configuración
        for aid in (A_LIT, A_ING, A_MATFIN, A_FILO, A_BIOCOMP, A_MUSICA):
            a = d.query(M.Asignatura).get(aid)
            assert a is not None and a.activo is not False, aid
    finally:
        d.close()


@test("§ZZ ZERO DATA LOSS: sge.db e INITIAL_CREDENTIALS.txt intactos")
def _():
    ahora_sge = os.path.getmtime(_REPO_SGE) if os.path.exists(_REPO_SGE) else None
    ahora_cred = os.path.getmtime(_REPO_CRED) if os.path.exists(_REPO_CRED) else None
    assert ahora_sge == _sge, "sge.db del repo fue modificado"
    assert ahora_cred == _cred, "INITIAL_CREDENTIALS.txt del repo fue modificado"
    _eu2 = str(engine.url).replace("\\", "/")
    assert "sge.db" not in _eu2, _eu2


print("\n" + "=" * 64)
print(f"{B}RESULTADO R3.2: {_ok}/{_total} pruebas{X}")
if _fail:
    print(f"{R}FALLARON:{X}")
    for n, e in _fail:
        print(f"  - {n}: {e}")
    sys.exit(1)
print(f"{G}TODO VERDE{X}")
