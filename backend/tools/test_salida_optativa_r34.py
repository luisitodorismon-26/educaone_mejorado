# -*- coding: utf-8 -*-
"""
EducaOne R3.4 — CALIFICACIÓN DOCENTE DE SALIDA OPTATIVA + NIVELES DEL PROFESOR.

Tres bloques, según R3.4 §20:

  A. OPTATIVAS CALIFICABLES — el componente obtiene una identidad calificable
     PROPIA, sus notas son independientes de la troncal, y el caso legacy de
     R3.2 (componente apuntando a "Lengua Española") se corrige repuntando SOLO
     la referencia, sin tocar una sola nota de la troncal.
  B. NIVELES DEL PROFESOR — `niveles_asignados` sale de las asignaciones activas
     reales (asignación -> curso -> Grado.nivel), no de `Usuario.nivel_asignado`.
  C. SELECTOR DE CALIFICACIONES — el frontend filtra las materias POR CURSO y
     muestra la optativa con su nombre oficial y su badge.

SEGURIDAD: SQLite temporal aislada. NUNCA toca sge.db ni INITIAL_CREDENTIALS.txt
(se verifica al final). No consulta producción ni PostgreSQL.

Uso:
    cd backend
    python tools/test_salida_optativa_r34.py
"""
import os
import re
import sys
import atexit
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TMPDIR = tempfile.mkdtemp(prefix="eo_salida_opt_r34_")
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
import salida_optativa_docente as DOC                          # noqa: E402

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


# --------------------------------------------------------------------------
# FIXTURE
# --------------------------------------------------------------------------
COL_A, COL_B = 1, 2
ANO_A, ANO_B = 1, 2
G4, G4PRIM, G4B = 4, 40, 104
C4_A, C4_OTRO, CPRIM, C4_B = 14, 15, 16, 20

A_LENGUA, A_MUSICA, A_MAT = 101, 102, 103          # colegio A
A_B_LENGUA = 201                                    # colegio B
U_DIR_A, U_PROF, U_PROF2, U_PROF_PRIM, U_PROF_MIXTO = 30, 31, 32, 33, 34
U_PROF_SIN, U_DIR_B, U_PROF_B = 35, 36, 37
EST_1, EST_2 = 500, 501
PWD = "Prueba2026x"

HLM_LE_4, HLM_IN_4 = "HLM-LE-4", "HLM-IN-4"


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
                           activo=True, dias_trabajados="{}"))
        d.add(M.AnoEscolar(id=ANO_B, colegio_id=COL_B, nombre="2025-2026",
                           activo=True, dias_trabajados="{}"))
        d.add(M.Grado(id=G4, colegio_id=COL_A, nombre="4to Secundaria",
                      nivel="secundaria", orden=4))
        d.add(M.Grado(id=G4PRIM, colegio_id=COL_A, nombre="4to Primaria",
                      nivel="primaria", orden=4))
        d.add(M.Grado(id=G4B, colegio_id=COL_B, nombre="4to Secundaria",
                      nivel="secundaria", orden=4))
        d.add(M.Curso(id=C4_A, colegio_id=COL_A, nombre="A", grado_id=G4,
                      ano_escolar_id=ANO_A, activo=True))
        d.add(M.Curso(id=C4_OTRO, colegio_id=COL_A, nombre="B", grado_id=G4,
                      ano_escolar_id=ANO_A, activo=True))
        d.add(M.Curso(id=CPRIM, colegio_id=COL_A, nombre="A", grado_id=G4PRIM,
                      ano_escolar_id=ANO_A, activo=True))
        d.add(M.Curso(id=C4_B, colegio_id=COL_B, nombre="A", grado_id=G4B,
                      ano_escolar_id=ANO_B, activo=True))
        # TRONCAL: tiene area_curricular_codigo -> NO puede representar un componente
        d.add(M.Asignatura(id=A_LENGUA, colegio_id=COL_A, nombre="Lengua Española",
                           codigo="LE", area="Lenguas", area_curricular_codigo="LE",
                           activo=True))
        # Materia propia del colegio, independiente (area_curricular_codigo NULL)
        d.add(M.Asignatura(id=A_MUSICA, colegio_id=COL_A, nombre="Música",
                           codigo="MS", area="", activo=True))
        d.add(M.Asignatura(id=A_MAT, colegio_id=COL_A, nombre="Matemática",
                           codigo="MA", area="Matemática", area_curricular_codigo="MAT",
                           activo=True))
        d.add(M.Asignatura(id=A_B_LENGUA, colegio_id=COL_B, nombre="Lengua Española",
                           codigo="LE", area="Lenguas", activo=True))
        for uid, un, rol, col in ((U_DIR_A, "dir_a", "direccion", COL_A),
                                  (U_PROF, "prof_a", "profesor", COL_A),
                                  (U_PROF2, "prof_b", "profesor", COL_A),
                                  (U_PROF_PRIM, "prof_prim", "profesor", COL_A),
                                  (U_PROF_MIXTO, "prof_mix", "profesor", COL_A),
                                  (U_PROF_SIN, "prof_sin", "profesor", COL_A),
                                  (U_DIR_B, "dir_b", "direccion", COL_B),
                                  (U_PROF_B, "prof_colb", "profesor", COL_B)):
            u = M.Usuario(id=uid, username=un, nombre=un, apellido="T", role=rol,
                          colegio_id=col)
            u.set_password(PWD)
            d.add(u)
        for eid in (EST_1, EST_2):
            d.add(M.Estudiante(id=eid, colegio_id=COL_A, nombre="Est%d" % eid,
                               apellido="T", curso_id=C4_A, activo=True))
        # prof_a da Lengua Española en 4to A (troncal)
        d.add(M.AsignacionProfesor(id=1, colegio_id=COL_A, profesor_id=U_PROF,
                                   curso_id=C4_A, asignatura_id=A_LENGUA,
                                   ano_escolar_id=ANO_A, activo=True))
        # prof_a también da Matemática, pero en OTRO curso (para el §C1)
        d.add(M.AsignacionProfesor(id=2, colegio_id=COL_A, profesor_id=U_PROF,
                                   curso_id=C4_OTRO, asignatura_id=A_MAT,
                                   ano_escolar_id=ANO_A, activo=True))
        # prof_prim solo primaria
        d.add(M.AsignacionProfesor(id=3, colegio_id=COL_A, profesor_id=U_PROF_PRIM,
                                   curso_id=CPRIM, asignatura_id=A_MUSICA,
                                   ano_escolar_id=ANO_A, activo=True))
        # prof_mix: primaria + secundaria
        d.add(M.AsignacionProfesor(id=4, colegio_id=COL_A, profesor_id=U_PROF_MIXTO,
                                   curso_id=CPRIM, asignatura_id=A_MUSICA,
                                   ano_escolar_id=ANO_A, activo=True))
        d.add(M.AsignacionProfesor(id=5, colegio_id=COL_A, profesor_id=U_PROF_MIXTO,
                                   curso_id=C4_A, asignatura_id=A_MAT,
                                   ano_escolar_id=ANO_A, activo=True))
        # prof_b: asignación INACTIVA (no debe contar para niveles)
        d.add(M.AsignacionProfesor(id=6, colegio_id=COL_A, profesor_id=U_PROF2,
                                   curso_id=C4_A, asignatura_id=A_MAT,
                                   ano_escolar_id=ANO_A, activo=False))
        d.commit()
    finally:
        d.close()


def login(u):
    r = client.post("/api/auth/login", json={"username": u, "password": PWD})
    assert r.status_code == 200, f"login {u}: {r.status_code} {r.text[:160]}"
    return r.json()["token"]


def auth(t):
    return {"Authorization": f"Bearer {t}"}


def put(curso, tok, **body):
    return client.put(f"/api/cursos/{curso}/salida-optativa", json=body, headers=auth(tok))


def get_estado(curso, tok):
    return client.get(f"/api/cursos/{curso}/salida-optativa", headers=auth(tok))


def mapeo_de(curso, codigo):
    d = SessionLocal()
    try:
        return d.query(M.CursoComponenteOptativo).filter(
            M.CursoComponenteOptativo.curso_id == curso,
            M.CursoComponenteOptativo.componente_codigo == codigo,
            M.CursoComponenteOptativo.activo == True).first()      # noqa: E712
    finally:
        d.close()


def nota(estudiante_id, asignatura_id, comp=1):
    d = SessionLocal()
    try:
        c = d.query(M.CalificacionSecundaria).filter(
            M.CalificacionSecundaria.estudiante_id == estudiante_id,
            M.CalificacionSecundaria.asignatura_id == asignatura_id,
            M.CalificacionSecundaria.competencia_numero == comp).first()
        return c.p1 if c else None
    finally:
        d.close()


def poner_nota(estudiante_id, asignatura_id, valor, comp=1):
    d = SessionLocal()
    try:
        d.add(M.CalificacionSecundaria(
            colegio_id=COL_A, estudiante_id=estudiante_id,
            asignatura_id=asignatura_id, ano_escolar_id=ANO_A,
            competencia_numero=comp, p1=valor))
        d.commit()
    finally:
        d.close()


_seed()
DIR_A = login("dir_a")
PROF = login("prof_a")
PROF2 = login("prof_b")
DIR_B = login("dir_b")


# ===========================================================================
# BLOQUE A — OPTATIVA CALIFICABLE INDEPENDIENTE
# ===========================================================================

@test("§A1 asignar profesor a un componente genera una identidad calificable propia")
def _():
    r = put(C4_A, DIR_A, salida_optativa_codigo="HLM",
            profesores={HLM_LE_4: U_PROF})
    assert r.status_code == 200, r.text[:300]
    m = mapeo_de(C4_A, HLM_LE_4)
    assert m is not None, "debe existir el mapeo"
    assert m.asignatura_id != A_LENGUA, "no puede apuntar a la troncal"
    d = SessionLocal()
    try:
        a = d.query(M.Asignatura).get(m.asignatura_id)
        assert a.nombre == CAT.componente(HLM_LE_4).nombre_oficial, a.nombre
        assert a.area_curricular_codigo is None, "la dedicada NO es un bloque troncal"
        assert a.colegio_id == COL_A
    finally:
        d.close()


@test("§A2 guardar dos veces es IDEMPOTENTE: no duplica Asignatura ni asignación")
def _():
    m0 = mapeo_de(C4_A, HLM_LE_4)
    d = SessionLocal()
    try:
        n_asig = d.query(M.Asignatura).count()
        n_ap = d.query(M.AsignacionProfesor).filter(
            M.AsignacionProfesor.asignatura_id == m0.asignatura_id,
            M.AsignacionProfesor.activo == True).count()           # noqa: E712
    finally:
        d.close()
    for _ in range(3):
        r = put(C4_A, DIR_A, salida_optativa_codigo="HLM", profesores={HLM_LE_4: U_PROF})
        assert r.status_code == 200, r.text[:250]
    m1 = mapeo_de(C4_A, HLM_LE_4)
    assert m1.asignatura_id == m0.asignatura_id, "debe REUTILIZAR la dedicada"
    d = SessionLocal()
    try:
        assert d.query(M.Asignatura).count() == n_asig, "no debe crear otra Asignatura"
        assert d.query(M.AsignacionProfesor).filter(
            M.AsignacionProfesor.asignatura_id == m1.asignatura_id,
            M.AsignacionProfesor.activo == True).count() == n_ap   # noqa: E712
    finally:
        d.close()


@test("§A3 la asignación docente queda activa sobre la asignatura dedicada")
def _():
    m = mapeo_de(C4_A, HLM_LE_4)
    d = SessionLocal()
    try:
        ap = d.query(M.AsignacionProfesor).filter(
            M.AsignacionProfesor.curso_id == C4_A,
            M.AsignacionProfesor.asignatura_id == m.asignatura_id,
            M.AsignacionProfesor.activo == True).first()           # noqa: E712
        assert ap is not None and ap.profesor_id == U_PROF, ap
        assert ap.ano_escolar_id == ANO_A, ap.ano_escolar_id
    finally:
        d.close()
    est = get_estado(C4_A, DIR_A).json()
    comp = {c["componente_codigo"]: c for c in est["componentes"]}[HLM_LE_4]
    assert comp["profesor_id"] == U_PROF, comp
    assert comp["identidad_independiente"] is True, comp


@test("§A4 LEGACY R3.2: un componente que apuntaba a la troncal se repunta")
def _():
    # Se reproduce el estado que R3.2 permitía: el componente apunta a Lengua.
    d = SessionLocal()
    try:
        m = d.query(M.CursoComponenteOptativo).filter(
            M.CursoComponenteOptativo.curso_id == C4_A,
            M.CursoComponenteOptativo.componente_codigo == HLM_IN_4).first()
        assert m is None
        d.add(M.CursoComponenteOptativo(
            colegio_id=COL_A, curso_id=C4_A, ano_escolar_id=ANO_A,
            componente_codigo=HLM_IN_4, asignatura_id=A_LENGUA, activo=True))
        d.commit()
    finally:
        d.close()
    # Lengua ya tiene notas reales de la troncal
    poner_nota(EST_1, A_LENGUA, 90.0)
    assert nota(EST_1, A_LENGUA) == 90.0

    r = put(C4_A, DIR_A, profesores={HLM_IN_4: U_PROF})
    assert r.status_code == 200, r.text[:300]
    m = mapeo_de(C4_A, HLM_IN_4)
    assert m.asignatura_id != A_LENGUA, "debe dejar de consumir la troncal"
    d = SessionLocal()
    try:
        nueva = d.query(M.Asignatura).get(m.asignatura_id)
        assert nueva.nombre == CAT.componente(HLM_IN_4).nombre_oficial
        assert nueva.area_curricular_codigo is None
        # LA TRONCAL SIGUE INTACTA
        leng = d.query(M.Asignatura).get(A_LENGUA)
        assert leng is not None and leng.activo is not False
        assert leng.nombre == "Lengua Española"
        assert leng.area_curricular_codigo == "LE"
    finally:
        d.close()
    assert nota(EST_1, A_LENGUA) == 90.0, "la nota de la troncal NO se toca"


@test("§A5 el repunte legacy queda en AUDITORÍA")
def _():
    d = SessionLocal()
    try:
        filas = d.query(M.LogAuditoria).filter(
            M.LogAuditoria.tabla == 'cursos',
            M.LogAuditoria.registro_id == C4_A).all()
        textos = " ".join((f.datos_nuevos or "") for f in filas)
    finally:
        d.close()
    assert "correcciones_identidad" in textos, "el repunte debe auditarse"
    assert "asignatura_anterior_id" in textos, textos[:300]


@test("§A6 NOTAS INDEPENDIENTES: 90 en la troncal, 72 en la optativa")
def _():
    m = mapeo_de(C4_A, HLM_LE_4)
    poner_nota(EST_1, m.asignatura_id, 72.0)
    assert nota(EST_1, A_LENGUA) == 90.0, "Lengua debe seguir en 90"
    assert nota(EST_1, m.asignatura_id) == 72.0, "la optativa debe valer 72"
    # modificar una NO modifica la otra
    d = SessionLocal()
    try:
        c = d.query(M.CalificacionSecundaria).filter(
            M.CalificacionSecundaria.estudiante_id == EST_1,
            M.CalificacionSecundaria.asignatura_id == m.asignatura_id).first()
        c.p1 = 65.0
        d.commit()
    finally:
        d.close()
    assert nota(EST_1, m.asignatura_id) == 65.0
    assert nota(EST_1, A_LENGUA) == 90.0, "cambiar la optativa no toca la troncal"


@test("§A7 R3.3 imprime la nota de la OPTATIVA, no la de la troncal")
def _():
    from app import _cargar_salida_optativa_registro
    m = mapeo_de(C4_A, HLM_LE_4)
    # 4 competencias completas en la optativa para que haya CF
    for comp_n in (2, 3, 4):
        poner_nota(EST_1, m.asignatura_id, 65.0, comp=comp_n)
    d = SessionLocal()
    try:
        for c in d.query(M.CalificacionSecundaria).filter(
                M.CalificacionSecundaria.asignatura_id == m.asignatura_id).all():
            c.p2 = c.p3 = c.p4 = c.p1
        d.commit()
        user = d.query(M.Usuario).get(U_DIR_A)
        curso = d.query(M.Curso).get(C4_A)
        ests = d.query(M.Estudiante).filter(M.Estudiante.curso_id == C4_A).all()
        res = _cargar_salida_optativa_registro(d, user, curso, ests)
    finally:
        d.close()
    slot = CAT.componente(HLM_LE_4).slot
    assert slot in res, res
    califs = res[slot]["calificaciones"]
    cf = califs[0].get("cf")
    assert cf is not None, califs[0]
    assert abs(cf - 65.0) < 0.01, ("R3.3 debe leer la optativa (65), no la troncal "
                                   "(90); leyó %r" % cf)


@test("§A8 §14: la asignatura dedicada NO puede sustituir a una troncal del Registro")
def _():
    # "Manejo de la Información en Inglés" contiene "Inglés": sin la guarda,
    # podría ocupar la página troncal de Inglés en un colegio sin match exacto.
    from app import _cargar_datos_asignaturas_secundaria
    m = mapeo_de(C4_A, HLM_IN_4)
    d = SessionLocal()
    try:
        nombre_dedicada = d.query(M.Asignatura).get(m.asignatura_id).nombre
        excluidas = DOC.asignaturas_optativas_del_colegio(d, COL_A)
        assert m.asignatura_id in excluidas, excluidas
        user = d.query(M.Usuario).get(U_DIR_A)
        ests = d.query(M.Estudiante).filter(M.Estudiante.curso_id == C4_A).all()
        datos = _cargar_datos_asignaturas_secundaria(d, user, C4_A, 4, ests)
    finally:
        d.close()
    assert "Inglés" in nombre_dedicada, nombre_dedicada
    ing = datos.get("Lenguas Extranjeras - Inglés", {})
    assert ing.get("docente", "Sin asignar") == "Sin asignar", (
        "la optativa no debe hacer de troncal de Inglés: %r" % ing.get("docente"))


@test("§A9 una identidad INDEPENDIENTE ya elegida por Dirección se reutiliza")
def _():
    # Música tiene area_curricular_codigo NULL: es una identidad válida.
    r = put(C4_OTRO, DIR_A, salida_optativa_codigo="HLM",
            componentes={HLM_LE_4: A_MUSICA})
    assert r.status_code == 200, r.text[:250]
    assert mapeo_de(C4_OTRO, HLM_LE_4).asignatura_id == A_MUSICA
    d = SessionLocal()
    try:
        n_antes = d.query(M.Asignatura).count()
    finally:
        d.close()
    r = put(C4_OTRO, DIR_A, profesores={HLM_LE_4: U_PROF2})
    assert r.status_code == 200, r.text[:250]
    assert mapeo_de(C4_OTRO, HLM_LE_4).asignatura_id == A_MUSICA, \
        "no debe sustituir una identidad independiente ya elegida"
    d = SessionLocal()
    try:
        assert d.query(M.Asignatura).count() == n_antes, "no debe crear otra"
    finally:
        d.close()


@test("§A10 cambiar de profesor CONSERVA las notas y la asignatura")
def _():
    m = mapeo_de(C4_A, HLM_LE_4)
    antes = nota(EST_1, m.asignatura_id)
    r = put(C4_A, DIR_A, profesores={HLM_LE_4: U_PROF2})
    assert r.status_code == 200, r.text[:250]
    d = SessionLocal()
    try:
        activas = d.query(M.AsignacionProfesor).filter(
            M.AsignacionProfesor.curso_id == C4_A,
            M.AsignacionProfesor.asignatura_id == m.asignatura_id,
            M.AsignacionProfesor.activo == True).all()             # noqa: E712
        assert len(activas) == 1 and activas[0].profesor_id == U_PROF2, activas
        # la anterior se DESACTIVA, no se borra
        todas = d.query(M.AsignacionProfesor).filter(
            M.AsignacionProfesor.curso_id == C4_A,
            M.AsignacionProfesor.asignatura_id == m.asignatura_id).all()
        assert any(a.profesor_id == U_PROF for a in todas), "no debe borrarse"
    finally:
        d.close()
    assert mapeo_de(C4_A, HLM_LE_4).asignatura_id == m.asignatura_id
    assert nota(EST_1, m.asignatura_id) == antes, "las notas no pertenecen al profesor"
    # se restituye para los tests siguientes
    put(C4_A, DIR_A, profesores={HLM_LE_4: U_PROF})


@test("§A11 un profesor de OTRO colegio no puede asignarse (mismo 404 que inexistente)")
def _():
    ajeno = put(C4_A, DIR_A, profesores={HLM_LE_4: U_PROF_B})
    inexistente = put(C4_A, DIR_A, profesores={HLM_LE_4: 999999})
    assert ajeno.status_code == 404, ajeno.text[:250]
    assert inexistente.status_code == ajeno.status_code
    assert inexistente.json() == ajeno.json(), (inexistente.json(), ajeno.json())
    assert mapeo_de(C4_A, HLM_LE_4).asignatura_id is not None


@test("§A12 solo Dirección configura; profesor y otro tenant no")
def _():
    assert put(C4_A, PROF, profesores={HLM_LE_4: U_PROF}).status_code == 403
    assert put(C4_A, DIR_B, profesores={HLM_LE_4: U_PROF}).status_code == 404
    assert get_estado(C4_A, PROF).status_code == 403


@test("§A13 un no-profesor no puede ser responsable de un componente")
def _():
    r = put(C4_A, DIR_A, profesores={HLM_LE_4: U_DIR_A})
    assert r.status_code == 400, r.text[:250]
    assert "profesor" in r.json()["error"].lower(), r.json()


@test("§A14 NO hay backfill de arranque: la identidad solo se crea al configurar")
def _():
    import inspect as _i
    import app as _app
    src = _i.getsource(_app.lifespan)
    assert "resolver_identidad_calificable" not in src, \
        "R3.4 no debe correr en el arranque"
    assert "asignar_profesor" not in src, "R3.4 no debe correr en el arranque"


@test("§A15 la identidad NO se resuelve por nombre ni por codigo")
def _():
    import inspect as _i
    src = _i.getsource(DOC.resolver_identidad_calificable) + _i.getsource(
        DOC.crear_asignatura_dedicada)
    for prohibido in ("ilike", "contains(", ".like(", "startswith"):
        assert prohibido not in src, prohibido
    # la resolución mira la FK del mapeo, no el nombre
    assert "mapeo_actual.asignatura_id" in src, src[:200]


# ===========================================================================
# BLOQUE B — NIVELES DEL PROFESOR
# ===========================================================================

def niveles(usuario):
    tok = login(usuario)
    r = client.get("/api/dashboard/profesor", headers=auth(tok))
    assert r.status_code == 200, r.text[:200]
    return r.json().get("niveles_asignados")


@test("§B1 profesor SOLO secundaria -> primaria False, secundaria True")
def _():
    assert niveles("prof_a") == {"primaria": False, "secundaria": True}


@test("§B2 profesor SOLO primaria -> primaria True, secundaria False")
def _():
    assert niveles("prof_prim") == {"primaria": True, "secundaria": False}


@test("§B3 profesor MIXTO -> ambos True")
def _():
    assert niveles("prof_mix") == {"primaria": True, "secundaria": True}


@test("§B4 profesor SIN asignaciones -> ambos False")
def _():
    assert niveles("prof_sin") == {"primaria": False, "secundaria": False}


@test("§B5 una asignación INACTIVA no cuenta")
def _():
    # prof_sin no tiene ninguna asignación. Se le da UNA, inactiva, sobre un
    # curso de secundaria: si contara, secundaria pasaría a True.
    d = SessionLocal()
    try:
        d.add(M.AsignacionProfesor(id=98, colegio_id=COL_A, profesor_id=U_PROF_SIN,
                                   curso_id=C4_A, asignatura_id=A_MAT,
                                   ano_escolar_id=ANO_A, activo=False))
        d.commit()
    finally:
        d.close()
    try:
        assert niveles("prof_sin") == {"primaria": False, "secundaria": False},             "una asignación inactiva no debe aportar nivel"
    finally:
        d = SessionLocal()
        try:
            f = d.query(M.AsignacionProfesor).get(98)
            if f:
                d.delete(f)
                d.commit()
        finally:
            d.close()


@test("§B6 un curso de OTRO TENANT no cuenta")
def _():
    d = SessionLocal()
    try:
        # se le cuelga a prof_a una asignación a un curso del colegio B
        d.add(M.AsignacionProfesor(id=99, colegio_id=COL_B, profesor_id=U_PROF,
                                   curso_id=C4_B, asignatura_id=A_B_LENGUA,
                                   ano_escolar_id=ANO_B, activo=True))
        d.commit()
    finally:
        d.close()
    try:
        assert niveles("prof_a") == {"primaria": False, "secundaria": True}, \
            "una asignación de otro colegio no debe aportar nivel"
    finally:
        d = SessionLocal()
        try:
            f = d.query(M.AsignacionProfesor).get(99)
            if f:
                d.delete(f)
                d.commit()
        finally:
            d.close()


@test("§B7 un curso INACTIVO no cuenta")
def _():
    d = SessionLocal()
    try:
        c = d.query(M.Curso).get(CPRIM)
        c.activo = False
        d.commit()
    finally:
        d.close()
    try:
        assert niveles("prof_prim") == {"primaria": False, "secundaria": False}
    finally:
        d = SessionLocal()
        try:
            c = d.query(M.Curso).get(CPRIM)
            c.activo = True
            d.commit()
        finally:
            d.close()


@test("§B8 el dashboard marca la optativa con su metadata oficial")
def _():
    tok = login("prof_a")
    r = client.get("/api/dashboard/profesor", headers=auth(tok))
    filas = r.json()["cursos_asignados"]
    opts = [f for f in filas if f["es_salida_optativa"]]
    normales = [f for f in filas if not f["es_salida_optativa"]]
    assert opts, filas
    assert normales, "la troncal debe seguir apareciendo"
    o = opts[0]
    assert o["componente_codigo"] == HLM_LE_4, o
    assert o["componente_nombre"] == CAT.componente(HLM_LE_4).nombre_oficial, o
    assert o["salida_codigo"] == "HLM" and o["salida_nombre"] == CAT.SALIDAS["HLM"], o
    # la identidad para calificar sigue siendo asignatura_id, como cualquier otra
    assert o["asignatura_id"] == mapeo_de(C4_A, HLM_LE_4).asignatura_id, o
    # y Lengua Española sigue ahí, independiente
    assert any(f["asignatura_id"] == A_LENGUA for f in normales), normales


@test("§B9 el profesor NO asignado no puede calificar el componente")
def _():
    m = mapeo_de(C4_A, HLM_LE_4)
    tok = login("prof_sin")
    r = client.get(f"/api/calificaciones/curso/{C4_A}/asignatura/{m.asignatura_id}",
                   headers=auth(tok))
    assert r.status_code == 403, (r.status_code, r.text[:200])


# ===========================================================================
# BLOQUE C — FRONTEND
# ===========================================================================

def _leer(rel):
    p = os.path.join(_FRONT, rel)
    assert os.path.exists(p), p
    with open(p, encoding="utf-8") as f:
        return f.read()


@test("§C1 AcademicoPage filtra las asignaturas POR CURSO seleccionado")
def _():
    src = _leer(os.path.join("pages", "academico", "AcademicoPage.tsx"))
    # la lista global deduplicada por asignatura_id ya no puede ser la fuente
    assert "asignaturasUnicas" not in src, \
        "el selector no debe construirse global para todos los cursos"
    assert "asignaturasDelCurso" in src, "debe existir un filtrado por curso"
    assert "curso_id === cursoId" in src or "c.curso_id === cursoId" in src, src[:0]


@test("§C2 la optativa se muestra con su badge oficial, sin pantalla nueva")
def _():
    src = _leer(os.path.join("pages", "academico", "AcademicoPage.tsx"))
    assert "es_salida_optativa" in src, "debe usar el metadato del backend"
    assert "Salida Optativa" in src, "debe rotularla"
    # no se resuelve por nombre
    assert "componente_nombre" in src or "salida_nombre" in src, src[:0]


@test("§C3 MainLayout usa niveles_asignados del backend, no una heurística propia")
def _():
    src = _leer(os.path.join("components", "layout", "MainLayout.tsx"))
    assert "niveles_asignados" in src, "debe consumir la fuente única del backend"
    assert "nivelesProfesor" in src, src[:0]
    # no debe inferir por texto del nombre del grado
    assert "includes('Primaria')" not in src and 'includes("Primaria")' not in src


@test("§C4 el sidebar oculta items del nivel que el profesor no imparte")
def _():
    src = _leer(os.path.join("components", "layout", "MainLayout.tsx"))
    # el filtro debe contemplar el caso profesor con niveles conocidos
    assert re.search(r"item\.nivel.*nivelesProfesor|nivelesProfesor.*item\.nivel",
                     src, re.S), "el filtro de items debe usar nivelesProfesor"


@test("§ZZ ZERO DATA LOSS: sge.db e INITIAL_CREDENTIALS.txt intactos")
def _():
    ahora_sge = os.path.getmtime(_REPO_SGE) if os.path.exists(_REPO_SGE) else None
    ahora_cred = os.path.getmtime(_REPO_CRED) if os.path.exists(_REPO_CRED) else None
    assert ahora_sge == _sge, "sge.db del repo fue modificado"
    assert ahora_cred == _cred, "INITIAL_CREDENTIALS.txt del repo fue modificado"
    # y ninguna calificación fue borrada en toda la suite
    d = SessionLocal()
    try:
        assert d.query(M.CalificacionSecundaria).count() >= 2
        assert d.query(M.Asignatura).get(A_LENGUA) is not None
    finally:
        d.close()


print("\n" + "=" * 64)
print(f"{B}RESULTADO R3.4: {_ok}/{_total} pruebas{X}")
if _fail:
    print(f"{R}FALLARON:{X}")
    for n, e in _fail:
        print(f"  - {n}: {e}")
    sys.exit(1)
print(f"{G}TODO VERDE{X}")
