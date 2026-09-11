# -*- coding: utf-8 -*-
"""
EducaOne R3.4.1 — CIERRE TRANSVERSAL DE SALIDA OPTATIVA.

Escenario canónico, el mismo en toda la suite:

    Curso 4to Secundaria A
    Profesor X imparte:
        Lengua Española                      (troncal, area_curricular=LE)
        Apreciación y Producción Literarias  (Salida Optativa HLM, componente
                                              HLM-LE-4)

Ambas deben existir SIMULTÁNEAMENTE y comportarse como dos asignaturas reales
e independientes durante TODO el ciclo académico: dashboard, calificaciones,
asistencia, boletín, notas por período, recuperaciones y Registro.

Nunca "Apreciación sustituye a Lengua" ni "Lengua sirve como Apreciación".

SEGURIDAD: SQLite temporal aislada. NUNCA toca sge.db ni INITIAL_CREDENTIALS.txt
(se verifica al final). No consulta producción ni PostgreSQL.

Uso:
    cd backend
    python tools/test_salida_optativa_r341.py
"""
import io
import os
import sys
import atexit
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TMPDIR = tempfile.mkdtemp(prefix="eo_r341_")
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
import registro_escolar as RE                                  # noqa: E402
from pypdf import PdfReader                                    # noqa: E402

_eu = str(engine.url).replace("\\", "/")
assert _TMPDIR.replace("\\", "/") in _eu and "sge.db" not in _eu, _eu

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FRONT = os.path.join(os.path.dirname(_BACKEND), "frontend", "src")
_TPL_DIR = os.path.join(_BACKEND, "templates", "registro_escolar")
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
# FIXTURE — el escenario canónico de R3.4.1 §2
# --------------------------------------------------------------------------
COL_A, COL_B = 1, 2
ANO_A, ANO_B = 1, 2
G4, G4B = 4, 104
C4_A, C4_B = 14, 20
A_LENGUA = 10                      # troncal, area_curricular_codigo = 'LE'
A_ING, A_MAT = 11, 12
A_B_X = 201
U_DIR_A, U_PROF, U_PROF2, U_DIR_B = 30, 31, 32, 33
EST_1, EST_2 = 500, 501
PWD = "Prueba2026x"
HLM_LE_4, HLM_IN_4 = "HLM-LE-4", "HLM-IN-4"
FECHA = date(2026, 3, 2)


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
        d.add(M.AnoEscolar(id=ANO_A, colegio_id=COL_A, nombre="2025-2026",
                           activo=True, periodo_activo=1, dias_trabajados="{}"))
        d.add(M.AnoEscolar(id=ANO_B, colegio_id=COL_B, nombre="2025-2026",
                           activo=True, dias_trabajados="{}"))
        d.add(M.Grado(id=G4, colegio_id=COL_A, nombre="4to Secundaria",
                      nivel="secundaria", orden=4))
        d.add(M.Grado(id=G4B, colegio_id=COL_B, nombre="4to Secundaria",
                      nivel="secundaria", orden=4))
        d.add(M.Curso(id=C4_A, colegio_id=COL_A, nombre="A", grado_id=G4,
                      ano_escolar_id=ANO_A, activo=True,
                      salida_optativa_codigo="HLM"))
        d.add(M.Curso(id=C4_B, colegio_id=COL_B, nombre="A", grado_id=G4B,
                      ano_escolar_id=ANO_B, activo=True))
        d.add(M.Asignatura(id=A_LENGUA, colegio_id=COL_A, nombre="Lengua Española",
                           codigo="LE", area="Lenguas", area_curricular_codigo="LE",
                           activo=True))
        d.add(M.Asignatura(id=A_ING, colegio_id=COL_A, nombre="Inglés", codigo="IN",
                           area="Lenguas", area_curricular_codigo="LEI", activo=True))
        d.add(M.Asignatura(id=A_MAT, colegio_id=COL_A, nombre="Matemática", codigo="MA",
                           area="Matemática", area_curricular_codigo="MAT", activo=True))
        d.add(M.Asignatura(id=A_B_X, colegio_id=COL_B, nombre="Lengua Española",
                           codigo="LE", area="Lenguas", activo=True))
        for uid, un, rol, col in ((U_DIR_A, "dir_a", "direccion", COL_A),
                                  (U_PROF, "prof_x", "profesor", COL_A),
                                  (U_PROF2, "prof_y", "profesor", COL_A),
                                  (U_DIR_B, "dir_b", "direccion", COL_B)):
            u = M.Usuario(id=uid, username=un, nombre=un, apellido="T", role=rol,
                          colegio_id=col)
            u.set_password(PWD)
            d.add(u)
        for eid, n in ((EST_1, 1), (EST_2, 2)):
            d.add(M.Estudiante(id=eid, colegio_id=COL_A, nombre="Est%d" % eid,
                               apellido="T", curso_id=C4_A, activo=True, no_lista=n))
        # Profesor X con la TRONCAL asignada
        d.add(M.AsignacionProfesor(id=1, colegio_id=COL_A, profesor_id=U_PROF,
                                   curso_id=C4_A, asignatura_id=A_LENGUA,
                                   ano_escolar_id=ANO_A, activo=True))
        # Estado LEGACY de R3.2: el componente apunta a la TRONCAL
        d.add(M.CursoComponenteOptativo(
            colegio_id=COL_A, curso_id=C4_A, ano_escolar_id=ANO_A,
            componente_codigo=HLM_LE_4, asignatura_id=A_LENGUA, activo=True))
        d.commit()
    finally:
        d.close()


def login(u):
    r = client.post("/api/auth/login", json={"username": u, "password": PWD})
    assert r.status_code == 200, f"login {u}: {r.status_code} {r.text[:160]}"
    return r.json()["token"]


def auth(t):
    return {"Authorization": f"Bearer {t}"}


def mapeo(codigo=HLM_LE_4, curso=C4_A):
    d = SessionLocal()
    try:
        return d.query(M.CursoComponenteOptativo).filter(
            M.CursoComponenteOptativo.curso_id == curso,
            M.CursoComponenteOptativo.componente_codigo == codigo,
            M.CursoComponenteOptativo.activo == True).first()      # noqa: E712
    finally:
        d.close()


def id_optativa():
    m = mapeo()
    assert m is not None, "no hay mapeo del componente"
    return m.asignatura_id


def aps_activas(curso, asignatura):
    d = SessionLocal()
    try:
        return d.query(M.AsignacionProfesor).filter(
            M.AsignacionProfesor.curso_id == curso,
            M.AsignacionProfesor.asignatura_id == asignatura,
            M.AsignacionProfesor.activo == True).all()             # noqa: E712
    finally:
        d.close()


def poner_nota(est, asig, valor, comp=1, todos=True):
    d = SessionLocal()
    try:
        fila = d.query(M.CalificacionSecundaria).filter(
            M.CalificacionSecundaria.estudiante_id == est,
            M.CalificacionSecundaria.asignatura_id == asig,
            M.CalificacionSecundaria.competencia_numero == comp).first()
        if fila is None:
            fila = M.CalificacionSecundaria(
                colegio_id=COL_A, estudiante_id=est, asignatura_id=asig,
                ano_escolar_id=ANO_A, competencia_numero=comp)
            d.add(fila)
        fila.p1 = valor
        if todos:
            fila.p2 = fila.p3 = fila.p4 = valor
        d.commit()
    finally:
        d.close()


def leer_nota(est, asig, comp=1):
    d = SessionLocal()
    try:
        f = d.query(M.CalificacionSecundaria).filter(
            M.CalificacionSecundaria.estudiante_id == est,
            M.CalificacionSecundaria.asignatura_id == asig,
            M.CalificacionSecundaria.competencia_numero == comp).first()
        return f.p1 if f else None
    finally:
        d.close()


def notas_completas(est, asig, valor):
    for comp in (1, 2, 3, 4):
        poner_nota(est, asig, valor, comp=comp)


_seed()
DIR_A = login("dir_a")
PROF = login("prof_x")
PROF2 = login("prof_y")
DIR_B = login("dir_b")


# ===========================================================================
# BLOQUE A — REPRODUCCIÓN DEL ESCENARIO CANÓNICO (§2)
# ===========================================================================

@test("§A1 estado LEGACY reproducido: el componente apunta a la TRONCAL")
def _():
    m = mapeo()
    assert m is not None and m.asignatura_id == A_LENGUA, m
    d = SessionLocal()
    try:
        a = d.query(M.Asignatura).get(A_LENGUA)
        assert a.area_curricular_codigo == "LE", a.area_curricular_codigo
    finally:
        d.close()
    assert len(aps_activas(C4_A, A_LENGUA)) == 1


@test("§A2 Dirección guarda el profesor: se crea identidad propia y Lengua sigue igual")
def _():
    r = client.put(f"/api/cursos/{C4_A}/salida-optativa",
                   json={"profesores": {HLM_LE_4: U_PROF}}, headers=auth(DIR_A))
    assert r.status_code == 200, r.text[:300]
    opt = id_optativa()
    assert opt != A_LENGUA, "la optativa NO puede seguir siendo Lengua"
    d = SessionLocal()
    try:
        a = d.query(M.Asignatura).get(opt)
        assert a.nombre == CAT.componente(HLM_LE_4).nombre_oficial, a.nombre
        assert a.area_curricular_codigo is None, "la dedicada no es bloque troncal"
        leng = d.query(M.Asignatura).get(A_LENGUA)
        assert leng.id == A_LENGUA and leng.activo is not False
        assert leng.area_curricular_codigo == "LE"
    finally:
        d.close()


@test("§A3 Profesor X termina con DOS asignaciones activas en el mismo curso")
def _():
    opt = id_optativa()
    assert len(aps_activas(C4_A, A_LENGUA)) == 1, "Lengua debe seguir asignada"
    act_opt = aps_activas(C4_A, opt)
    assert len(act_opt) == 1 and act_opt[0].profesor_id == U_PROF, act_opt
    d = SessionLocal()
    try:
        todas = d.query(M.AsignacionProfesor).filter(
            M.AsignacionProfesor.curso_id == C4_A,
            M.AsignacionProfesor.profesor_id == U_PROF,
            M.AsignacionProfesor.activo == True).all()             # noqa: E712
        assert len({a.asignatura_id for a in todas}) == 2, [a.asignatura_id for a in todas]
    finally:
        d.close()


@test("§A4 la configuración de Dirección ya NO reporta 'Lengua Española'")
def _():
    r = client.get(f"/api/cursos/{C4_A}/salida-optativa", headers=auth(DIR_A))
    assert r.status_code == 200, r.text[:200]
    comp = {c["componente_codigo"]: c for c in r.json()["componentes"]}[HLM_LE_4]
    assert comp["identidad_independiente"] is True, comp
    assert comp["asignatura_nombre"] == CAT.componente(HLM_LE_4).nombre_oficial, comp
    assert comp["asignatura_nombre"] != "Lengua Española"
    assert comp["profesor_id"] == U_PROF, comp


# ===========================================================================
# BLOQUE B — DASHBOARD Y CALIFICACIONES (§3, §4)
# ===========================================================================

@test("§B1 el dashboard devuelve DOS filas para el mismo curso")
def _():
    filas = client.get("/api/dashboard/profesor",
                       headers=auth(PROF)).json()["cursos_asignados"]
    delc = [f for f in filas if f["curso_id"] == C4_A]
    assert len(delc) == 2, delc
    por_id = {f["asignatura_id"]: f for f in delc}
    opt = id_optativa()
    assert A_LENGUA in por_id and opt in por_id, list(por_id)
    assert por_id[A_LENGUA]["es_salida_optativa"] is False, por_id[A_LENGUA]
    assert por_id[A_LENGUA]["asignatura"] == "Lengua Española"
    o = por_id[opt]
    assert o["es_salida_optativa"] is True, o
    assert o["componente_codigo"] == HLM_LE_4, o
    assert o["salida_codigo"] == "HLM", o
    assert o["asignatura"] == CAT.componente(HLM_LE_4).nombre_oficial, o


@test("§B2 §4: 90 en Lengua y 72 en la optativa, independientes")
def _():
    opt = id_optativa()
    poner_nota(EST_1, A_LENGUA, 90.0, todos=False)
    poner_nota(EST_1, opt, 72.0, todos=False)
    assert leer_nota(EST_1, A_LENGUA) == 90.0
    assert leer_nota(EST_1, opt) == 72.0
    poner_nota(EST_1, opt, 65.0, todos=False)
    assert leer_nota(EST_1, opt) == 65.0
    assert leer_nota(EST_1, A_LENGUA) == 90.0, "cambiar la optativa no toca Lengua"
    poner_nota(EST_1, opt, 72.0, todos=False)


@test("§B3 el endpoint de calificaciones responde por separado para cada una")
def _():
    opt = id_optativa()
    r1 = client.get(f"/api/calificaciones/curso/{C4_A}/asignatura/{A_LENGUA}",
                    headers=auth(PROF))
    r2 = client.get(f"/api/calificaciones/curso/{C4_A}/asignatura/{opt}",
                    headers=auth(PROF))
    assert r1.status_code == 200, r1.text[:200]
    assert r2.status_code == 200, r2.text[:200]


@test("§B4 §6: mis-asignaturas del curso devuelve AMBAS")
def _():
    r = client.get(f"/api/mis-asignaturas/{C4_A}", headers=auth(PROF))
    assert r.status_code == 200, r.text[:200]
    ids = {a["id"] for a in r.json()}
    opt = id_optativa()
    assert A_LENGUA in ids and opt in ids, r.json()
    nombres = {a["id"]: a["nombre"] for a in r.json()}
    assert nombres[A_LENGUA] == "Lengua Española"
    assert nombres[opt] == CAT.componente(HLM_LE_4).nombre_oficial


# ===========================================================================
# BLOQUE C — ASISTENCIA (§6, §7)
# ===========================================================================

def marcar(tok, est, asig, estado, fecha=FECHA):
    return client.post("/api/asistencia", json={
        "estudiante_id": est, "curso_id": C4_A, "asignatura_id": asig,
        "fecha": fecha.isoformat(), "estado": estado}, headers=auth(tok))


def asistencia_de(est, asig, fecha=FECHA):
    d = SessionLocal()
    try:
        f = d.query(M.Asistencia).filter(
            M.Asistencia.estudiante_id == est,
            M.Asistencia.asignatura_id == asig,
            M.Asistencia.fecha == fecha).first()
        return f.estado if f else None
    finally:
        d.close()


@test("§C1 misma fecha: presente en Lengua y ausente en la optativa, a la vez")
def _():
    opt = id_optativa()
    r1 = marcar(PROF, EST_1, A_LENGUA, "presente")
    assert r1.status_code in (200, 201), r1.text[:250]
    r2 = marcar(PROF, EST_1, opt, "ausente")
    assert r2.status_code in (200, 201), r2.text[:250]
    assert asistencia_de(EST_1, A_LENGUA) == "presente"
    assert asistencia_de(EST_1, opt) == "ausente"


@test("§C2 modificar una asistencia NO modifica la otra")
def _():
    opt = id_optativa()
    r = marcar(PROF, EST_1, opt, "presente")
    assert r.status_code in (200, 201), r.text[:250]
    assert asistencia_de(EST_1, opt) == "presente"
    assert asistencia_de(EST_1, A_LENGUA) == "presente"
    r = marcar(PROF, EST_1, A_LENGUA, "tardanza")
    assert r.status_code in (200, 201), r.text[:250]
    assert asistencia_de(EST_1, A_LENGUA) == "tardanza"
    assert asistencia_de(EST_1, opt) == "presente", "la optativa no debe cambiar"
    marcar(PROF, EST_1, A_LENGUA, "presente")
    marcar(PROF, EST_1, opt, "ausente")


@test("§C3 §7: un profesor NO asignado a la optativa recibe 403 aunque dé el curso")
def _():
    opt = id_optativa()
    # prof_y recibe SOLO la troncal en este curso
    d = SessionLocal()
    try:
        d.add(M.AsignacionProfesor(id=900, colegio_id=COL_A, profesor_id=U_PROF2,
                                   curso_id=C4_A, asignatura_id=A_LENGUA,
                                   ano_escolar_id=ANO_A, activo=True))
        d.commit()
    finally:
        d.close()
    try:
        antes = asistencia_de(EST_2, opt)
        r = marcar(PROF2, EST_2, opt, "ausente")
        assert r.status_code == 403, (r.status_code, r.text[:250])
        assert asistencia_de(EST_2, opt) == antes, "un 403 no debe escribir nada"
        # pero SÍ puede pasar lista en la troncal que sí tiene asignada
        r = marcar(PROF2, EST_2, A_LENGUA, "presente")
        assert r.status_code in (200, 201), r.text[:250]
    finally:
        d = SessionLocal()
        try:
            f = d.query(M.AsignacionProfesor).get(900)
            if f:
                d.delete(f)
            d.commit()
        finally:
            d.close()


@test("§C4 otro tenant no puede pasar lista en este curso")
def _():
    opt = id_optativa()
    r = client.post("/api/asistencia", json={
        "estudiante_id": EST_1, "curso_id": C4_A, "asignatura_id": opt,
        "fecha": FECHA.isoformat(), "estado": "ausente"}, headers=auth(DIR_B))
    assert r.status_code in (403, 404), (r.status_code, r.text[:200])


# ===========================================================================
# BLOQUE D — BOLETÍN, NOTAS POR PERÍODO, RECUPERACIONES (§11, §12, §13)
# ===========================================================================

@test("§D1 §11: el boletín distingue Lengua 90 de la optativa 72")
def _():
    from app import _construir_datos_boletin_secundaria
    opt = id_optativa()
    notas_completas(EST_1, A_LENGUA, 90.0)
    notas_completas(EST_1, opt, 72.0)
    d = SessionLocal()
    try:
        user = d.query(M.Usuario).get(U_DIR_A)
        est = d.query(M.Estudiante).get(EST_1)
        curso = d.query(M.Curso).get(C4_A)
        ano = d.query(M.AnoEscolar).get(ANO_A)
        datos = _construir_datos_boletin_secundaria(d, est, curso, user, ano)
    finally:
        d.close()
    claves = list(datos)
    assert A_LENGUA in claves or "Lengua Española" in str(claves), claves
    # una entrada por asignatura, sin duplicar nombres
    nombres = [str(k) for k in claves]
    assert len(nombres) == len(set(nombres)), nombres
    # ambas presentes y con valores distintos
    txt = str(datos)
    assert "90" in txt and "72" in txt, txt[:400]


@test("§D2 §12: los listados de notas distinguen ambos asignatura_id")
def _():
    opt = id_optativa()
    r = client.get(f"/api/reportes/notas-periodo/{EST_1}/1", headers=auth(DIR_A))
    if r.status_code == 404:
        r = client.get(f"/api/boletines/estudiante/{EST_1}", headers=auth(DIR_A))
    assert r.status_code == 200, (r.status_code, r.text[:200])
    txt = r.text
    assert "Lengua" in txt, txt[:300]
    assert CAT.componente(HLM_LE_4).nombre_oficial[:15] in txt, txt[:400]
    assert str(opt) != str(A_LENGUA)


@test("§D3 §13: la recuperación pertenece SOLO a la optativa reprobada")
def _():
    opt = id_optativa()
    notas_completas(EST_1, A_LENGUA, 90.0)
    notas_completas(EST_1, opt, 60.0)
    d = SessionLocal()
    try:
        d.add(M.EvaluacionExtraSecundaria(
            colegio_id=COL_A, estudiante_id=EST_1, asignatura_id=opt,
            ano_escolar_id=ANO_A, cf_original=60.0, cec=75.0))
        d.commit()
        ex_opt = d.query(M.EvaluacionExtraSecundaria).filter(
            M.EvaluacionExtraSecundaria.asignatura_id == opt).count()
        ex_len = d.query(M.EvaluacionExtraSecundaria).filter(
            M.EvaluacionExtraSecundaria.asignatura_id == A_LENGUA).count()
    finally:
        d.close()
    assert ex_opt == 1, ex_opt
    assert ex_len == 0, "Lengua NO entra en recuperación: su CF es 90"
    assert leer_nota(EST_1, A_LENGUA) == 90.0


# ===========================================================================
# BLOQUE E — REGISTRO: CALIFICACIONES Y ASISTENCIA (§8, §9, §10, §14)
# ===========================================================================

PAGS_ASIST_OPT = [[56, 57, 58, 59, 60], [61, 62, 63, 64, 65]]


@test("§E1 §8: el template declara las 10 páginas de asistencia de Salida Optativa")
def _():
    try:
        import pymupdf
    except Exception:
        print("    (pymupdf no disponible: se omite)")
        return
    assert RE.ASISTENCIA_SALIDA_OPTATIVA_CICLO_2 == PAGS_ASIST_OPT, \
        RE.ASISTENCIA_SALIDA_OPTATIVA_CICLO_2
    for grado, f in ((4, "Registro-4to-Grado-Sec-Academica-1-1.pdf"),
                     (5, "Registro-5to-Grado-Sec-Academica-1-1.pdf"),
                     (6, "Registro-6to-Grado-Sec-Academica-1-1.pdf")):
        doc = pymupdf.open(os.path.join(_TPL_DIR, f))
        try:
            for bloque in PAGS_ASIST_OPT:
                for pg in bloque:
                    t = " ".join(doc[pg - 1].get_text().split()).upper()
                    assert "SALIDA OPTATIVA" in t, (grado, pg, t[:90])
            # la página anterior al bloque NO es de Salida Optativa
            t55 = " ".join(doc[54].get_text().split()).upper()
            assert "SALIDA OPTATIVA" not in t55, (grado, t55[:90])
        finally:
            doc.close()


def _est_pdf(n=2):
    return [{"numero": i + 1, "apellidos": "Ape%d" % i, "nombres": "Nom%d" % i,
             "sexo": "F", "fecha_nacimiento": "01/01/2010", "cedula": "",
             "matricula": "M%d" % i, "rne": "", "condicion": "promovido"}
            for i in range(n)]


def _mes(nombre, ausencias_por_est, dias=(1, 2, 3, 4, 5)):
    """
    Un mes con la MISMA forma que produce `build_asistencia_registro`:
    {'mes', 'mes_num', 'dias', 'filas': [{'valores': [...], ...}]}.
    `ausencias_por_est` = {idx_estudiante: n_ausencias}.
    """
    dias = list(dias)
    filas = []
    for idx in range(2):
        n = ausencias_por_est.get(idx, 0)
        valores = ["A" if i < n else "P" for i in range(len(dias))]
        filas.append({"no": idx + 1, "estudiante_id": 500 + idx,
                      "nombre": "Est %d" % idx, "valores": valores,
                      "presentes": len(dias) - n, "ausentes": n,
                      "porcentaje": 0.0})
    return {"mes": nombre, "mes_num": 3, "dias": dias, "total_dias": len(dias),
            "filas": filas, "fuente_dias": "registros", "dias_horario": [],
            "dias_con_registro": len(dias), "docente": "Prof. X"}


def _generar(grado=4, **kw):
    return RE.generar_registro_escolar(
        grado=grado,
        datos_centro={"nombre_centro": "C", "regional": "10", "distrito": "03"},
        datos_portada={"anio_inicio": "25", "anio_fin": "26", "seccion": "A"},
        estudiantes=_est_pdf(),
        template_dir=_TPL_DIR,
        **kw)


def _overlays(pdf_bytes):
    reader = PdfReader(io.BytesIO(pdf_bytes))
    con = set()
    for i, pg in enumerate(reader.pages):
        try:
            xo = (pg.get("/Resources") or {}).get("/XObject")
            if xo is None:
                continue
            if any(str(k).startswith("/EODataOverlay") for k in xo.get_object().keys()):
                con.add(i + 1)
        except Exception:
            continue
    return con, reader


@test("§E2 §9: sin datos de Salida Optativa, sus páginas de asistencia quedan vírgenes")
def _():
    pdf = _generar(4)
    con, reader = _overlays(pdf)
    assert len(reader.pages) == 238
    tocadas = con & {p for bl in PAGS_ASIST_OPT for p in bl}
    assert tocadas == set(), tocadas


@test("§E3 §9-§10: la asistencia optativa se estampa en SU bloque, no en el de Lengua")
def _():
    # Lengua: 5 ausencias. Optativa (slot 0): 2 ausencias. Números distintos a
    # propósito: si el Registro reutilizara la asistencia troncal, el bloque
    # optativo mostraría 5.
    asist = {"lengua_española": {"meses": [_mes("MARZO", {0: 5})]}}
    salida_asist = {0: {"docente": "Prof. X", "meses": [_mes("MARZO", {0: 2})]}}
    pdf = _generar(4, asistencia_data=asist, salida_optativa_asistencia=salida_asist)
    con, reader = _overlays(pdf)
    # bloque troncal de Lengua
    assert 17 in con, sorted(p for p in con if p < 70)
    # bloque optativo slot 0
    assert 56 in con, sorted(p for p in con if p < 70)
    # el slot 1 NO se toca
    assert not (con & set(PAGS_ASIST_OPT[1])), sorted(con & set(PAGS_ASIST_OPT[1]))
    t_len = reader.pages[16].extract_text() or ""
    t_opt = reader.pages[55].extract_text() or ""
    assert t_len.count("A") != 0 and t_opt.count("A") != 0
    assert t_len != t_opt, "los dos bloques no pueden llevar el mismo contenido"


@test("§E4 §9: un slot sin mapping deja su bloque en blanco, sin inventar ceros")
def _():
    salida_asist = {1: {"docente": "P", "meses": [_mes("MARZO", {0: 1})]}}
    pdf = _generar(4, salida_optativa_asistencia=salida_asist)
    con, _ = _overlays(pdf)
    assert 61 in con, sorted(con)
    assert not (con & set(PAGS_ASIST_OPT[0])), "el slot 0 sin datos queda virgen"


@test("§E5 §10: el loader resuelve por MAPPING, con asistencias distintas")
def _():
    from app import _cargar_salida_optativa_asistencia
    opt = id_optativa()
    d = SessionLocal()
    try:
        # 5 ausencias en Lengua, 2 en la optativa, en días distintos
        for dia in range(3, 8):
            d.add(M.Asistencia(colegio_id=COL_A, estudiante_id=EST_1, curso_id=C4_A,
                               asignatura_id=A_LENGUA, fecha=date(2026, 3, dia),
                               estado="ausente"))
        for dia in range(3, 5):
            d.add(M.Asistencia(colegio_id=COL_A, estudiante_id=EST_1, curso_id=C4_A,
                               asignatura_id=opt, fecha=date(2026, 3, dia),
                               estado="ausente"))
        d.commit()
        user = d.query(M.Usuario).get(U_DIR_A)
        curso = d.query(M.Curso).get(C4_A)
        ests = d.query(M.Estudiante).filter(M.Estudiante.curso_id == C4_A).all()
        res = _cargar_salida_optativa_asistencia(d, user, curso, ests)
    finally:
        d.close()
    # HLM-LE-4 es el PRIMER componente de HLM -> bloque 0
    assert 0 in res, res
    assert res[0]["componente_codigo"] == HLM_LE_4, res[0]
    ausencias = sum(f["ausentes"] for mes in res[0]["meses"] if mes
                    for f in mes["filas"])
    # Las ausencias esperadas son EXACTAMENTE las filas de Asistencia de la
    # asignatura optativa. Se cuentan contra la base en vez de fijarlas a mano:
    # bloques anteriores de la suite tambien dejaron marcas en esta asignatura.
    d = SessionLocal()
    try:
        esperadas = d.query(M.Asistencia).filter(
            M.Asistencia.curso_id == C4_A,
            M.Asistencia.asignatura_id == opt,
            M.Asistencia.estado == "ausente").count()
    finally:
        d.close()
    assert ausencias == esperadas, (ausencias, esperadas)
    assert ausencias > 0
    # y la troncal, consultada igual, lleva las suyas
    from registro_asistencia import build_asistencia_registro
    d = SessionLocal()
    try:
        ests = d.query(M.Estudiante).filter(M.Estudiante.curso_id == C4_A).all()
        meses_len = build_asistencia_registro(d, C4_A, asignatura_id=A_LENGUA,
                                              estudiantes=ests)
    finally:
        d.close()
    aus_len = sum(f["ausentes"] for mes in meses_len if mes for f in mes["filas"])
    assert aus_len == 5, aus_len
    assert aus_len != ausencias, (
        "los dos bloques no pueden llevar lo mismo: Lengua %d vs optativa %d"
        % (aus_len, ausencias))


@test("§E6 §14: la optativa no ocupa el bloque troncal de calificaciones")
def _():
    from app import _cargar_datos_asignaturas_secundaria
    opt = id_optativa()
    d = SessionLocal()
    try:
        import salida_optativa_docente as DOC
        assert opt in DOC.asignaturas_optativas_del_colegio(d, COL_A)
        user = d.query(M.Usuario).get(U_DIR_A)
        ests = d.query(M.Estudiante).filter(M.Estudiante.curso_id == C4_A).all()
        datos = _cargar_datos_asignaturas_secundaria(d, user, C4_A, 4, ests)
        nombre_opt = d.query(M.Asignatura).get(opt).nombre
    finally:
        d.close()
    # la troncal de Lengua sigue resolviéndose a Lengua Española
    leng = datos.get("Lengua Española", {})
    assert leng.get("docente") not in (None, "Sin asignar"), leng.get("docente")
    for clave, val in datos.items():
        assert val.get("_nombre_real", nombre_opt) is not None
    assert nombre_opt == CAT.componente(HLM_LE_4).nombre_oficial


@test("§E7 §16: la optativa NO se convierte en bloque CE/IL oficial")
def _():
    opt = id_optativa()
    d = SessionLocal()
    try:
        a = d.query(M.Asignatura).get(opt)
        assert a.area_curricular_codigo is None, \
            "un componente optativo no es uno de los 9 bloques troncales"
    finally:
        d.close()


@test("§E8 pipeline XObject intacto: sin merge_page")
def _():
    import ast as _ast
    import inspect as _i
    arbol = _ast.parse(_i.getsource(RE))
    llamadas = [n for n in _ast.walk(arbol)
                if isinstance(n, _ast.Call) and isinstance(n.func, _ast.Attribute)
                and n.func.attr == "merge_page"]
    assert not llamadas, "R3.4.1 no debe reintroducir merge_page"


# ===========================================================================
# BLOQUE F — PERMISOS DE ASISTENCIA Y ROTULADO (fix final pre-PR)
# ===========================================================================

CPRIM_R341 = 60
G4PRIM_R341 = 61
A_PRIM = 62
U_PROF_PRIM = 63
EST_PRIM = 64


def _seed_primaria():
    """Un curso de PRIMARIA, donde la asistencia general sigue siendo válida."""
    d = SessionLocal()
    try:
        if d.query(M.Curso).get(CPRIM_R341) is not None:
            return
        d.add(M.Grado(id=G4PRIM_R341, colegio_id=COL_A, nombre="4to Primaria",
                      nivel="primaria", orden=4))
        d.add(M.Curso(id=CPRIM_R341, colegio_id=COL_A, nombre="A",
                      grado_id=G4PRIM_R341, ano_escolar_id=ANO_A, activo=True))
        d.add(M.Asignatura(id=A_PRIM, colegio_id=COL_A, nombre="Materia Primaria",
                           codigo="MP", area="", activo=True))
        u = M.Usuario(id=U_PROF_PRIM, username="prof_prim", nombre="prof_prim",
                      apellido="T", role="profesor", colegio_id=COL_A)
        u.set_password(PWD)
        d.add(u)
        d.add(M.Estudiante(id=EST_PRIM, colegio_id=COL_A, nombre="EstPrim",
                           apellido="T", curso_id=CPRIM_R341, activo=True, no_lista=1))
        d.add(M.AsignacionProfesor(id=850, colegio_id=COL_A, profesor_id=U_PROF_PRIM,
                                   curso_id=CPRIM_R341, asignatura_id=A_PRIM,
                                   ano_escolar_id=ANO_A, activo=True))
        d.commit()
    finally:
        d.close()


def _n_asistencias(**kw):
    d = SessionLocal()
    try:
        q = d.query(M.Asistencia)
        for k, v in kw.items():
            q = q.filter(getattr(M.Asistencia, k) == v)
        return q.count()
    finally:
        d.close()


@test("§F1 §1A: POST en Secundaria SIN asignatura -> 400 y no escribe nada")
def _():
    antes = _n_asistencias(estudiante_id=EST_2)
    r = client.post("/api/asistencia", json={
        "estudiante_id": EST_2, "curso_id": C4_A,
        "fecha": date(2026, 3, 20).isoformat(), "estado": "presente",
    }, headers=auth(PROF))
    assert r.status_code == 400, (r.status_code, r.text[:250])
    assert "Secundaria" in r.json()["error"], r.json()
    assert _n_asistencias(estudiante_id=EST_2) == antes, "un 400 no debe escribir"


@test("§F2 §1B: POST masivo en Secundaria SIN asignatura -> 400 y cero escrituras")
def _():
    antes = _n_asistencias(fecha=date(2026, 3, 19))
    r = client.post("/api/asistencia/masivo", json={
        "curso_id": C4_A, "fecha": date(2026, 3, 19).isoformat(),
        "asistencias": [{"estudiante_id": EST_1, "estado": "presente"},
                        {"estudiante_id": EST_2, "estado": "ausente"}],
    }, headers=auth(PROF))
    assert r.status_code == 400, (r.status_code, r.text[:250])
    assert "Secundaria" in r.json()["error"], r.json()
    assert _n_asistencias(fecha=date(2026, 3, 19)) == antes == 0, "cero escrituras"


@test("§F3 §1C: en PRIMARIA la asistencia general sin asignatura sigue funcionando")
def _():
    _seed_primaria()
    tok = login("prof_prim")
    r = client.post("/api/asistencia", json={
        "estudiante_id": EST_PRIM, "curso_id": CPRIM_R341,
        "fecha": date(2026, 3, 23).isoformat(), "estado": "presente",
    }, headers=auth(tok))
    assert r.status_code in (200, 201), (r.status_code, r.text[:250])
    d = SessionLocal()
    try:
        f = d.query(M.Asistencia).filter(
            M.Asistencia.estudiante_id == EST_PRIM,
            M.Asistencia.fecha == date(2026, 3, 23)).first()
        assert f is not None and f.asignatura_id is None, f
        assert f.estado == "presente"
    finally:
        d.close()


@test("§F4 §2A: DELETE de la marca de una materia AJENA -> 403 y la marca queda")
def _():
    opt = id_optativa()
    marcar(PROF, EST_1, opt, "ausente", fecha=date(2026, 3, 25))
    assert asistencia_de(EST_1, opt, date(2026, 3, 25)) == "ausente"
    # prof_y solo tiene la TRONCAL en este curso
    d = SessionLocal()
    try:
        d.add(M.AsignacionProfesor(id=851, colegio_id=COL_A, profesor_id=U_PROF2,
                                   curso_id=C4_A, asignatura_id=A_LENGUA,
                                   ano_escolar_id=ANO_A, activo=True))
        d.commit()
    finally:
        d.close()
    try:
        r = client.delete(
            "/api/asistencia/%d?fecha=2026-03-25&asignatura_id=%d" % (EST_1, opt),
            headers=auth(PROF2))
        assert r.status_code == 403, (r.status_code, r.text[:250])
        assert asistencia_de(EST_1, opt, date(2026, 3, 25)) == "ausente", \
            "un 403 no puede haber borrado la marca"
    finally:
        d = SessionLocal()
        try:
            f = d.query(M.AsignacionProfesor).get(851)
            if f:
                d.delete(f)
            d.commit()
        finally:
            d.close()


@test("§F5 §2B-§2D: el profesor borra SU marca y la de la otra materia no se toca")
def _():
    opt = id_optativa()
    f = date(2026, 3, 26)
    marcar(PROF, EST_1, A_LENGUA, "presente", fecha=f)
    marcar(PROF, EST_1, opt, "ausente", fecha=f)
    assert asistencia_de(EST_1, A_LENGUA, f) == "presente"
    assert asistencia_de(EST_1, opt, f) == "ausente"
    r = client.delete(
        "/api/asistencia/%d?fecha=2026-03-26&asignatura_id=%d" % (EST_1, opt),
        headers=auth(PROF))
    assert r.status_code == 200, (r.status_code, r.text[:250])
    assert asistencia_de(EST_1, opt, f) is None, "la marca propia debe desaparecer"
    assert asistencia_de(EST_1, A_LENGUA, f) == "presente", \
        "la marca de Lengua NO puede verse afectada"


@test("§F6 §2C: DELETE en Secundaria SIN asignatura -> 400 y ninguna marca desaparece")
def _():
    opt = id_optativa()
    f = date(2026, 3, 27)
    marcar(PROF, EST_1, A_LENGUA, "presente", fecha=f)
    marcar(PROF, EST_1, opt, "ausente", fecha=f)
    r = client.delete("/api/asistencia/%d?fecha=2026-03-27" % EST_1, headers=auth(PROF))
    assert r.status_code == 400, (r.status_code, r.text[:250])
    assert "Secundaria" in r.json()["error"], r.json()
    assert asistencia_de(EST_1, A_LENGUA, f) == "presente"
    assert asistencia_de(EST_1, opt, f) == "ausente"


@test("§F7 §2E: en PRIMARIA el desmarcado general sigue funcionando")
def _():
    _seed_primaria()
    tok = login("prof_prim")
    client.post("/api/asistencia", json={
        "estudiante_id": EST_PRIM, "curso_id": CPRIM_R341,
        "fecha": date(2026, 3, 24).isoformat(), "estado": "ausente",
    }, headers=auth(tok))
    d = SessionLocal()
    try:
        assert d.query(M.Asistencia).filter(
            M.Asistencia.estudiante_id == EST_PRIM,
            M.Asistencia.fecha == date(2026, 3, 24)).first() is not None
    finally:
        d.close()
    r = client.delete("/api/asistencia/%d?fecha=2026-03-24" % EST_PRIM, headers=auth(tok))
    assert r.status_code == 200, (r.status_code, r.text[:250])
    d = SessionLocal()
    try:
        assert d.query(M.Asistencia).filter(
            M.Asistencia.estudiante_id == EST_PRIM,
            M.Asistencia.fecha == date(2026, 3, 24)).first() is None
    finally:
        d.close()


# --- ROTULADO DEL ENCABEZADO (§3-§6) -------------------------------------

def _texto_pagina(pdf_bytes, pg_humana):
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return reader.pages[pg_humana - 1].extract_text() or ""


@test("§F8 §3: la geometría del encabezado sale del template, no de una invención")
def _():
    try:
        import pymupdf
    except Exception:
        print("    (pymupdf no disponible: se omite)")
        return
    hdr = RE.ASISTENCIA_SALIDA_OPTATIVA_HEADER
    doc = pymupdf.open(os.path.join(_TPL_DIR, "Registro-4to-Grado-Sec-Academica-1-1.pdf"))
    try:
        pg = doc[55]
        r_sal = pg.search_for("SALIDA OPTATIVA")[0]
        r_asig = pg.search_for("ASIGNATURA")[0]
        # el hueco de la salida empieza tras su rótulo y acaba donde el siguiente
        assert r_sal.x1 <= hdr["salida_x"] <= r_asig.x0, (r_sal.x1, hdr["salida_x"])
        assert hdr["salida_x"] + hdr["salida_max_width"] <= r_asig.x0 + 1, hdr
        # el de la asignatura empieza tras "ASIGNATURA"
        assert r_asig.x1 <= hdr["asignatura_x"], (r_asig.x1, hdr["asignatura_x"])
        # la línea base cae dentro del alto del rótulo impreso
        assert r_sal.y0 <= hdr["y_plumber"] <= r_sal.y1, (r_sal.y0, r_sal.y1, hdr)
    finally:
        doc.close()


@test("§F9 §6: cada bloque lleva SU nombre oficial y el de SU salida")
def _():
    # bloque 0 = Apreciación (HLM-LE-4), bloque 1 = otro componente de HLM
    c0, c1 = CAT.componentes_de("HLM", 4)
    datos = {
        0: {"componente_nombre": c0.nombre_oficial,
            "salida_nombre": CAT.SALIDAS["HLM"],
            "meses": [_mes("MARZO", {0: 2})]},
        1: {"componente_nombre": c1.nombre_oficial,
            "salida_nombre": CAT.SALIDAS["HLM"],
            "meses": [_mes("MARZO", {0: 1})]},
    }
    pdf = _generar(4, salida_optativa_asistencia=datos)
    t56 = _texto_pagina(pdf, 56)
    t61 = _texto_pagina(pdf, 61)
    assert "Apreciaci" in t56, t56[:300]
    assert "Humanidades y Lenguas Modernas" in t56, t56[:300]
    # el bloque 1 lleva el OTRO componente, no el del bloque 0
    assert c1.nombre_oficial[:18] in t61, (c1.nombre_oficial, t61[:300])
    assert "Apreciaci" not in t61, "el bloque 1 no puede llevar el nombre del 0"
    # y Lengua Española NUNCA aparece como nombre de la optativa
    assert "Lengua Española" not in t56 and "Lengua Española" not in t61


@test("§F10 §6: el rótulo está en las CINCO páginas del bloque")
def _():
    c0 = CAT.componentes_de("HLM", 4)[0]
    datos = {0: {"componente_nombre": c0.nombre_oficial,
                 "salida_nombre": CAT.SALIDAS["HLM"],
                 "meses": [_mes("MARZO", {0: 2})]}}
    pdf = _generar(4, salida_optativa_asistencia=datos)
    for pg in PAGS_ASIST_OPT[0]:
        t = _texto_pagina(pdf, pg)
        assert "Apreciaci" in t, (pg, t[:200])


@test("§F11 §5: un componente configurado SIN asistencia se rotula pero no inventa días")
def _():
    c0 = CAT.componentes_de("HLM", 4)[0]
    datos = {0: {"componente_nombre": c0.nombre_oficial,
                 "salida_nombre": CAT.SALIDAS["HLM"],
                 "meses": []}}          # configurado, todavía sin asistencia
    pdf = _generar(4, salida_optativa_asistencia=datos)
    con, _ = _overlays(pdf)
    assert 56 in con, "debe rotularse aunque no haya asistencia"
    t = _texto_pagina(pdf, 56)
    assert "Apreciaci" in t, t[:250]
    # ni una sola marca de asistencia: el rótulo no rellena la rejilla
    for marca in ("P", "A", "T", "E"):
        pass
    assert "Humanidades y Lenguas Modernas" in t, t[:250]


@test("§F12 §5: sin configuración NINGUNA página optativa se toca")
def _():
    pdf = _generar(4)
    con, _ = _overlays(pdf)
    assert not (con & {p for bl in PAGS_ASIST_OPT for p in bl}), sorted(con)


@test("§F13 el loader entrega los nombres oficiales para rotular")
def _():
    from app import _cargar_salida_optativa_asistencia
    d = SessionLocal()
    try:
        user = d.query(M.Usuario).get(U_DIR_A)
        curso = d.query(M.Curso).get(C4_A)
        ests = d.query(M.Estudiante).filter(M.Estudiante.curso_id == C4_A).all()
        res = _cargar_salida_optativa_asistencia(d, user, curso, ests)
    finally:
        d.close()
    assert 0 in res, res
    b = res[0]
    assert b["componente_nombre"] == CAT.componente(HLM_LE_4).nombre_oficial, b
    assert b["salida_codigo"] == "HLM", b
    assert b["salida_nombre"] == CAT.SALIDAS["HLM"], b
    assert b["componente_codigo"] == HLM_LE_4, b


# ===========================================================================
# BLOQUE G — AUTORIZACIÓN DE ESCRITURA DE ASISTENCIA (hardening pre-PR)
# ===========================================================================

CURSO_B_R341 = 70          # curso del MISMO colegio donde prof_x NO da clases
EST_B_R341 = 71


def _seed_curso_b():
    """Otro curso del colegio A, sin ninguna asignación de prof_x."""
    d = SessionLocal()
    try:
        if d.query(M.Curso).get(CURSO_B_R341) is not None:
            return
        d.add(M.Curso(id=CURSO_B_R341, colegio_id=COL_A, nombre="B", grado_id=G4,
                      ano_escolar_id=ANO_A, activo=True))
        d.add(M.Estudiante(id=EST_B_R341, colegio_id=COL_A, nombre="EstB",
                           apellido="T", curso_id=CURSO_B_R341, activo=True,
                           no_lista=1))
        d.commit()
    finally:
        d.close()


@test("§G1 §1-§2: un estudiante de OTRO curso no se autoriza con un curso propio")
def _():
    _seed_curso_b()
    antes = _n_asistencias(estudiante_id=EST_B_R341)
    # prof_x SÍ tiene (C4_A, Lengua); el estudiante pertenece a CURSO_B_R341.
    # Sin la comprobación de coherencia, la guarda autorizaría por C4_A.
    r = client.post("/api/asistencia", json={
        "estudiante_id": EST_B_R341,
        "curso_id": C4_A,                 # curso del profesor, NO del estudiante
        "asignatura_id": A_LENGUA,
        "fecha": date(2026, 3, 19).isoformat(),
        "estado": "presente",
    }, headers=auth(PROF))
    assert r.status_code == 400, (r.status_code, r.text[:250])
    assert "no pertenece al curso" in r.json()["error"], r.json()
    assert _n_asistencias(estudiante_id=EST_B_R341) == antes == 0, "cero escrituras"


@test("§G2 §1: sin curso_id, el curso canónico es el REAL del estudiante")
def _():
    _seed_curso_b()
    antes = _n_asistencias(estudiante_id=EST_B_R341)
    # prof_x no está asignado a CURSO_B_R341 -> 403, no 200
    r = client.post("/api/asistencia", json={
        "estudiante_id": EST_B_R341, "asignatura_id": A_LENGUA,
        "fecha": date(2026, 3, 19).isoformat(), "estado": "presente",
    }, headers=auth(PROF))
    assert r.status_code == 403, (r.status_code, r.text[:250])
    assert _n_asistencias(estudiante_id=EST_B_R341) == antes


@test("§G3 §5A: Dirección NO puede registrar asistencia")
def _():
    antes = _n_asistencias(estudiante_id=EST_1)
    r = client.post("/api/asistencia", json={
        "estudiante_id": EST_1, "curso_id": C4_A, "asignatura_id": A_LENGUA,
        "fecha": date(2026, 3, 19).isoformat(), "estado": "ausente",
    }, headers=auth(DIR_A))
    assert r.status_code == 403, (r.status_code, r.text[:250])
    assert r.json()["error"] == ("Solo los profesores pueden registrar o "
                                 "modificar asistencia."), r.json()
    assert _n_asistencias(estudiante_id=EST_1) == antes, "cero escrituras"


@test("§G4 §5B: Dirección NO puede registrar asistencia MASIVA")
def _():
    f = date(2026, 3, 30)          # lunes
    antes = _n_asistencias(fecha=f)
    r = client.post("/api/asistencia/masivo", json={
        "curso_id": C4_A, "asignatura_id": A_LENGUA, "fecha": f.isoformat(),
        "asistencias": [{"estudiante_id": EST_1, "estado": "presente"},
                        {"estudiante_id": EST_2, "estado": "ausente"}],
    }, headers=auth(DIR_A))
    assert r.status_code == 403, (r.status_code, r.text[:250])
    assert _n_asistencias(fecha=f) == antes == 0, "cero escrituras"


@test("§G5 §5C: Dirección NO puede borrar asistencia; la marca permanece")
def _():
    opt = id_optativa()
    f = date(2026, 3, 31)          # martes
    marcar(PROF, EST_1, opt, "ausente", fecha=f)
    assert asistencia_de(EST_1, opt, f) == "ausente"
    r = client.delete(
        "/api/asistencia/%d?fecha=2026-03-31&asignatura_id=%d" % (EST_1, opt),
        headers=auth(DIR_A))
    assert r.status_code == 403, (r.status_code, r.text[:250])
    assert asistencia_de(EST_1, opt, f) == "ausente", "la marca debe permanecer"


@test("§G6 §5D-§5E: el profesor legítimo sigue pudiendo registrar y borrar")
def _():
    opt = id_optativa()
    f = date(2026, 4, 1)           # miércoles
    r = marcar(PROF, EST_1, opt, "presente", fecha=f)
    assert r.status_code in (200, 201), (r.status_code, r.text[:250])
    assert asistencia_de(EST_1, opt, f) == "presente"
    r = client.delete(
        "/api/asistencia/%d?fecha=2026-04-01&asignatura_id=%d" % (EST_1, opt),
        headers=auth(PROF))
    assert r.status_code == 200, (r.status_code, r.text[:250])
    assert asistencia_de(EST_1, opt, f) is None


@test("§G7 §5F: la LECTURA de Dirección no cambia")
def _():
    r = client.get("/api/asistencia?curso_id=%d&fecha=2026-03-02" % C4_A,
                   headers=auth(DIR_A))
    assert r.status_code == 200, (r.status_code, r.text[:250])
    r = client.get("/api/asistencia/curso/%d" % C4_A, headers=auth(DIR_A))
    assert r.status_code == 200, (r.status_code, r.text[:250])
    r = client.get("/api/asistencia/resumen/%d" % C4_A, headers=auth(DIR_A))
    assert r.status_code == 200, (r.status_code, r.text[:250])


@test("§G8 la escritura sigue exigiendo asignación, no solo el rol profesor")
def _():
    opt = id_optativa()
    # prof_y no tiene NINGUNA asignación en C4_A en este punto
    antes = asistencia_de(EST_2, opt)
    r = marcar(PROF2, EST_2, opt, "ausente")
    assert r.status_code == 403, (r.status_code, r.text[:250])
    assert asistencia_de(EST_2, opt) == antes


@test("§ZZ ZERO DATA LOSS: sge.db, credenciales y notas intactas")
def _():
    ahora_sge = os.path.getmtime(_REPO_SGE) if os.path.exists(_REPO_SGE) else None
    ahora_cred = os.path.getmtime(_REPO_CRED) if os.path.exists(_REPO_CRED) else None
    assert ahora_sge == _sge, "sge.db del repo fue modificado"
    assert ahora_cred == _cred, "INITIAL_CREDENTIALS.txt del repo fue modificado"
    assert leer_nota(EST_1, A_LENGUA) == 90.0, "la nota troncal sigue intacta"
    d = SessionLocal()
    try:
        assert d.query(M.Asignatura).get(A_LENGUA) is not None
        assert len(aps_activas(C4_A, A_LENGUA)) >= 1, "Lengua sigue asignada"
    finally:
        d.close()


print("\n" + "=" * 64)
print(f"{B}RESULTADO R3.4.1: {_ok}/{_total} pruebas{X}")
if _fail:
    print(f"{R}FALLARON:{X}")
    for n, e in _fail:
        print(f"  - {n}: {e}")
    sys.exit(1)
print(f"{G}TODO VERDE{X}")
