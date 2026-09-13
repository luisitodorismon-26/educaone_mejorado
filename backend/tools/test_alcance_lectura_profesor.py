# -*- coding: utf-8 -*-
"""
EducaOne — un profesor solo lee el expediente de SUS cursos.

DE DONDE SALE
    `guard_profesor_curso` existe desde v2.19.3-A y ya protegia el boletin. La
    auditoria de esta ronda midio cinco endpoints hermanos que exponen la misma
    clase de dato y NO la llevaban. Con un profesor que solo imparte Matematica
    en el curso A, un estudiante del curso B devolvia:

      /api/reportes/notas/estudiante/{id}/periodo/{p}  -> sus TRES asignaturas
      /api/estudiantes/{id}/historial                  -> datos personales,
                                                          telefonos de los padres
                                                          y expediente academico
      /api/calificaciones/por-materia?curso_id=B       -> el curso B entero
      /api/calificaciones/por-periodo?curso_id=B       -> el curso B entero
      /api/comunicacion-padres/estudiante/{id}         -> lo que el centro le
                                                          dijo a esa familia

    Es la misma forma del incidente P0 de reportes de conducta.

LO QUE NO CAMBIA
    Direccion, coordinacion, secretaria y psicologia leen igual que antes: la
    guarda solo mira a los profesores. Y un profesor sigue viendo entero lo de
    sus propios cursos, incluidas las materias que no imparte de esos cursos.

Uso:
    cd backend
    python tools/test_alcance_lectura_profesor.py
"""
import os
import sys
import atexit
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TMPDIR = tempfile.mkdtemp(prefix="eo_alcance_")
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
# FIXTURE
#   PROF imparte SOLO Matematica en CUR_A (secundaria).
#   PROF_PRI imparte Matematica en CUR_P (primaria).
#   CUR_B es de otro profesor: es el limite que se mide.
# --------------------------------------------------------------------------
PWD = "Prueba2026x"
COL, ANO = 1, 1
CUR_A, CUR_B, CUR_P = 10, 11, 12
MAT, LEN, ING = 1, 2, 3
PROF, PROF_PRI, DIR, COORD, PSICO, SECRE = 31, 33, 34, 35, 36, 37
E_SUYO, E_AJENO = 50, 60
E_PRI, E_PRI_RET = 70, 71


def _seed():
    M.Base.metadata.drop_all(bind=engine)
    M.Base.metadata.create_all(bind=engine)
    d = SessionLocal()
    try:
        d.add(M.Colegio(id=COL, nombre="Colegio", codigo="c",
                        plan_primaria=True, plan_secundaria=True))
        d.add(M.AnoEscolar(id=ANO, colegio_id=COL, nombre="2025-2026", activo=True,
                           fecha_inicio=date(2025, 8, 1), fecha_fin=date(2026, 6, 30),
                           dias_trabajados="{}"))
        d.add(M.Grado(id=1, colegio_id=COL, nombre="3ro Secundaria",
                      nivel="secundaria", orden=3))
        d.add(M.Grado(id=2, colegio_id=COL, nombre="4to Primaria",
                      nivel="primaria", orden=40))
        for cid, gid, nom in ((CUR_A, 1, "A"), (CUR_B, 1, "B"), (CUR_P, 2, "A")):
            d.add(M.Curso(id=cid, colegio_id=COL, nombre=nom, grado_id=gid,
                          ano_escolar_id=ANO, activo=True))
        for aid, nom, cod in ((MAT, "Matematica", "MAT"), (LEN, "Lengua", "LE"),
                              (ING, "Ingles", "LEI")):
            d.add(M.Asignatura(id=aid, colegio_id=COL, nombre=nom, codigo=cod,
                               area="X", area_curricular_codigo=cod, activo=True))
        for uid, un, rol in ((PROF, "prof", "profesor"), (PROF_PRI, "profpri", "profesor"),
                             (DIR, "dir", "direccion"), (COORD, "coord", "coordinador"),
                             (PSICO, "psico", "psicologia"), (SECRE, "secre", "secretaria")):
            u = M.Usuario(id=uid, colegio_id=COL, username=un, nombre=un,
                          apellido="T", role=rol, activo=True)
            u.set_password(PWD)
            d.add(u)
        d.add(M.Estudiante(id=E_SUYO, colegio_id=COL, nombre="Alumno",
                           apellido="DelProfe", curso_id=CUR_A, activo=True, no_lista=1))
        d.add(M.Estudiante(id=E_AJENO, colegio_id=COL, nombre="Alumno",
                           apellido="DeOtroCurso", curso_id=CUR_B, activo=True, no_lista=1))
        d.add(M.Estudiante(id=E_PRI, colegio_id=COL, nombre="Nino",
                           apellido="Activo", curso_id=CUR_P, activo=True, no_lista=1))
        d.add(M.Estudiante(id=E_PRI_RET, colegio_id=COL, nombre="Nino",
                           apellido="Retirado", curso_id=CUR_P, activo=False,
                           condicion="retirado", no_lista=2, fecha_retiro=date(2026, 1, 15)))
        # PROF solo Matematica en CUR_A; PROF_PRI Matematica en CUR_P
        d.add(M.AsignacionProfesor(id=100, colegio_id=COL, profesor_id=PROF,
                                   curso_id=CUR_A, asignatura_id=MAT,
                                   ano_escolar_id=ANO, activo=True))
        d.add(M.AsignacionProfesor(id=101, colegio_id=COL, profesor_id=PROF_PRI,
                                   curso_id=CUR_P, asignatura_id=MAT,
                                   ano_escolar_id=ANO, activo=True))
        for est in (E_SUYO, E_AJENO):
            for aid in (MAT, LEN, ING):
                for comp in (1, 2, 3, 4):
                    d.add(M.CalificacionSecundaria(
                        colegio_id=COL, estudiante_id=est, asignatura_id=aid,
                        ano_escolar_id=ANO, competencia_numero=comp,
                        p1=80.0, p2=80.0, p3=80.0, p4=80.0,
                        promedio_competencia=80.0))
        for est in (E_SUYO, E_AJENO):
            d.add(M.HistorialComunicacionPadres(
                colegio_id=COL, estudiante_id=est, enviado_por=DIR,
                tipo_comunicacion="conducta", medio="whatsapp",
                mensaje_enviado="Conversacion privada con la familia"))
        # fichas de recuperacion de primaria para las dos ninas
        for est in (E_PRI, E_PRI_RET):
            d.add(M.RecuperacionPrimaria(
                colegio_id=COL, estudiante_id=est, asignatura_id=MAT,
                ano_escolar_id=ANO, cf_area=60.0))
        d.commit()
    finally:
        d.close()


def _tok(u):
    r = client.post("/api/auth/login", json={"username": u, "password": PWD})
    assert r.status_code == 200, (u, r.text[:200])
    return {"Authorization": "Bearer " + r.json()["token"]}


_seed()
H = {u: _tok(u) for u in ("prof", "profpri", "dir", "coord", "psico", "secre")}

# Los cinco endpoints medidos, sobre el estudiante/curso AJENO y sobre el PROPIO.
RUTAS = [
    ("reporte de notas por periodo",
     f"/api/reportes/notas/estudiante/{E_AJENO}/periodo/1",
     f"/api/reportes/notas/estudiante/{E_SUYO}/periodo/1"),
    ("historial del estudiante",
     f"/api/estudiantes/{E_AJENO}/historial",
     f"/api/estudiantes/{E_SUYO}/historial"),
    ("calificaciones por materia",
     f"/api/calificaciones/por-materia?curso_id={CUR_B}",
     f"/api/calificaciones/por-materia?curso_id={CUR_A}"),
    ("calificaciones por periodo",
     f"/api/calificaciones/por-periodo?periodo=1&curso_id={CUR_B}",
     f"/api/calificaciones/por-periodo?periodo=1&curso_id={CUR_A}"),
    ("comunicaciones con la familia",
     f"/api/comunicacion-padres/estudiante/{E_AJENO}",
     f"/api/comunicacion-padres/estudiante/{E_SUYO}"),
    ("boletin (control: ya estaba protegido desde v2.19.3-A)",
     f"/api/boletines/estudiante/{E_AJENO}",
     f"/api/boletines/estudiante/{E_SUYO}"),
]


# ==========================================================================
# A — EL LIMITE
# ==========================================================================
@test("A1 el profesor NO alcanza el curso ajeno por ninguna de las seis rutas")
def _():
    _seed()
    for nombre, ajena, _propia in RUTAS:
        r = client.get(ajena, headers=H["prof"])
        assert r.status_code == 403, (nombre, r.status_code, r.text[:200])
        print(f"    {nombre:<52} 403")


@test("A2 y SI alcanza lo suyo: la guarda no le quita nada de sus cursos")
def _():
    _seed()
    for nombre, _ajena, propia in RUTAS:
        r = client.get(propia, headers=H["prof"])
        assert r.status_code == 200, (nombre, r.status_code, r.text[:250])


@test("A3 de SU curso ve TODAS las materias, no solo la que imparte")
def _():
    _seed()
    r = client.get(f"/api/reportes/notas/estudiante/{E_SUYO}/periodo/1", headers=H["prof"])
    assert r.status_code == 200, r.text[:250]
    nombres = {a.get("asignatura") or a.get("nombre") for a in r.json()["asignaturas"]}
    assert nombres == {"Matematica", "Lengua", "Ingles"}, nombres


@test("A4 el mensaje de rechazo no filtra nada del estudiante ni del curso")
def _():
    _seed()
    r = client.get(f"/api/estudiantes/{E_AJENO}/historial", headers=H["prof"])
    cuerpo = r.text
    for fuga in ("DeOtroCurso", "Secundaria B", str(CUR_B)):
        assert fuga not in cuerpo, (fuga, cuerpo[:200])


# ==========================================================================
# B — LOS DEMAS ROLES NO PIERDEN NADA
# ==========================================================================
@test("B1 direccion, coordinacion, psicologia y secretaria leen igual que antes")
def _():
    _seed()
    for rol in ("dir", "coord", "psico", "secre"):
        for nombre, ajena, _p in RUTAS:
            r = client.get(ajena, headers=H[rol])
            # la guarda solo mira a los profesores: ninguno de estos recibe 403
            assert r.status_code != 403, (rol, nombre, r.status_code, r.text[:200])


@test("B2 direccion sigue viendo el expediente completo del curso ajeno")
def _():
    _seed()
    r = client.get(f"/api/reportes/notas/estudiante/{E_AJENO}/periodo/1", headers=H["dir"])
    assert r.status_code == 200, r.text[:250]
    assert len(r.json()["asignaturas"]) == 3, r.json()["asignaturas"]


# ==========================================================================
# C — UNA ASIGNACION DESACTIVADA YA NO DA ACCESO
# ==========================================================================
@test("C1 si Direccion le retira la asignacion, deja de alcanzar ese curso")
def _():
    _seed()
    r = client.get(f"/api/estudiantes/{E_SUYO}/historial", headers=H["prof"])
    assert r.status_code == 200
    d = SessionLocal()
    try:
        d.query(M.AsignacionProfesor).get(100).activo = False
        d.commit()
    finally:
        d.close()
    r = client.get(f"/api/estudiantes/{E_SUYO}/historial", headers=H["prof"])
    assert r.status_code == 403, (r.status_code, r.text[:200])


@test("C2 el repo no fue tocado: sge.db intacto")
def _():
    a = os.path.getmtime(_REPO_SGE) if os.path.exists(_REPO_SGE) else None
    assert a == _sge_mtime, "sge.db fue modificado"


print(chr(10) + "=" * 70)
print(f"{B}ALCANCE DE LECTURA DEL PROFESOR: {_ok}/{_total} pruebas{X}")
if _fail:
    print(f"{R}FALLARON:{X}")
    for n, e in _fail:
        print(f"  - {n}: {e}")
    sys.exit(1)
print(f"{G}TODO VERDE{X}")
