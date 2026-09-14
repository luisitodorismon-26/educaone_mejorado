# -*- coding: utf-8 -*-
"""
EducaOne — no se cargan recuperaciones a un estudiante RETIRADO.

DE DONDE SALE
    La auditoria de esta ronda recorrio las escrituras academicas y midio cual
    comprueba que el estudiante siga activo:

      POST /api/calificaciones                          SI
      POST /api/calificaciones-primaria                 SI
      POST /api/calificaciones-secundaria               SI
      POST /api/calificaciones-secundaria/evaluacion-extra   SI
      POST /api/asistencia  y  /api/asistencia/masivo   SI
      POST /api/recuperaciones-primaria                 NO   <-- la unica

    El expediente de un retirado se conserva —eso es lo que protege P0.1— pero
    no recibe notas nuevas. Si Direccion necesita modificarlo, primero reactiva
    al estudiante, igual que en las otras cinco rutas.

Uso:
    cd backend
    python tools/test_recuperacion_estudiante_retirado.py
"""
import os
import sys
import atexit
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TMPDIR = tempfile.mkdtemp(prefix="eo_rec_ret_")
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
# D — RECUPERACION DE PRIMARIA SOBRE ESTUDIANTE RETIRADO
# ==========================================================================
def _rec(est_id, hdr=None):
    return client.post("/api/recuperaciones-primaria",
                       headers=hdr or H["profpri"],
                       json={"estudiante_id": est_id, "asignatura_id": MAT,
                             "tipo": "final", "puntos": 5})


def _foto_rec(est_id):
    d = SessionLocal()
    try:
        f = d.query(M.RecuperacionPrimaria).filter_by(estudiante_id=est_id).first()
        return (f.puntos_final, f.recuperacion_final, f.nota_final, f.condicion_final)
    finally:
        d.close()


@test("D1 no se carga recuperacion a un estudiante RETIRADO, y no se escribe nada")
def _():
    _seed()
    antes = _foto_rec(E_PRI_RET)
    r = _rec(E_PRI_RET)
    assert r.status_code == 403, (r.status_code, r.text[:250])
    assert "retirado" in r.json()["error"].lower()
    assert _foto_rec(E_PRI_RET) == antes, "escribio pese al 403"


@test("D2 el estudiante ACTIVO sigue funcionando exactamente igual")
def _():
    _seed()
    r = _rec(E_PRI)
    assert r.status_code == 200, (r.status_code, r.text[:250])
    puntos, rec_final, nota, cond = _foto_rec(E_PRI)
    assert puntos == 5.0 and rec_final == 65.0, (puntos, rec_final)
    assert r.json()["aprobado"] is True, r.json()


@test("D3 reactivado el estudiante, la recuperacion vuelve a entrar")
def _():
    _seed()
    assert _rec(E_PRI_RET).status_code == 403
    d = SessionLocal()
    try:
        d.query(M.Estudiante).get(E_PRI_RET).activo = True
        d.commit()
    finally:
        d.close()
    assert _rec(E_PRI_RET).status_code == 200


@test("D4 el repo no fue tocado: sge.db intacto")
def _():
    a = os.path.getmtime(_REPO_SGE) if os.path.exists(_REPO_SGE) else None
    assert a == _sge_mtime, "sge.db fue modificado"


print("\n" + "=" * 70)
print(f"{B}RECUPERACION SOBRE ESTUDIANTE RETIRADO: {_ok}/{_total} pruebas{X}")
if _fail:
    print(f"{R}FALLARON:{X}")
    for n, e in _fail:
        print(f"  - {n}: {e}")
    sys.exit(1)
print(f"{G}TODO VERDE{X}")
