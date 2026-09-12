# -*- coding: utf-8 -*-
"""
EducaOne P0.1 — el borrado FISICO de expedientes queda deshabilitado.

QUE SE CONSERVA
    Retirar   -> soft-delete con condicion, fecha, motivo, autor y auditoria
    Reactivar -> devuelve al estudiante a activo

QUE SE CIERRA
    DELETE /api/estudiantes/retirados/{id}
    DELETE /api/estudiantes/retirados/eliminar-todos
    -> 403 sin tocar una sola fila.

POR QUE IMPORTA
    12 modelos referencian estudiante_id; el purgado contemplaba 6. Cuando la
    historia de un retirado vivia SOLO en esos 6, el borrado TENIA EXITO: en la
    auditoria de P0 destruyo 40 registros de asistencia, un caso de psicologia,
    el historial academico y la evaluacion interna. Permanente e irreversible.

Cada prueba compara la foto de las TRECE tablas antes y despues.

Uso:
    cd backend
    python tools/test_purgado_estudiantes_p0.py
"""
import os
import sys
import atexit
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TMPDIR = tempfile.mkdtemp(prefix="eo_purga_p0_")
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
    # El fixture siembra historia cruzada; las FK se relajan solo para poder
    # construirla. Lo que se mide —que el purgado no escribe— no depende de ellas.
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
# --------------------------------------------------------------------------
COL_A, COL_B = 1, 2
PWD = "Prueba2026x"
ANO_A, ANO_B = 1, 2
GRA_A, GRA_B = 1, 99
CUR_A, CUR_B = 10, 20
MAT = 1
U_DIR, U_DIR_B, U_PROF = 34, 38, 31
# retirados de distinto perfil
E_VACIO = 50        # sin ninguna historia
E_LEGACY = 51       # solo en las 6 tablas que el purgado SI contemplaba
E_COMPLETO = 52     # en las 13
E_ACTIVO = 53       # activo: no debe verse afectado por nada
E_OTRO_COL = 54     # de otro colegio

# Las TRECE tablas que cuelgan del estudiante (12 modelos + la ficha).
TABLAS = [
    ("Estudiante", M.Estudiante),
    ("Calificacion", M.Calificacion),
    ("CalificacionPrimaria", M.CalificacionPrimaria),
    ("CalificacionSecundaria", M.CalificacionSecundaria),
    ("RecuperacionPrimaria", M.RecuperacionPrimaria),
    ("EvaluacionExtraSecundaria", M.EvaluacionExtraSecundaria),
    ("Asistencia", M.Asistencia),
    ("ReporteConducta", M.ReporteConducta),
    ("CasoPsicologia", M.CasoPsicologia),
    ("HistorialAcademico", M.HistorialAcademico),
    ("EvalInternaEstudiante", M.EvalInternaEstudiante),
    ("HistorialComunicacionPadres", M.HistorialComunicacionPadres),
    ("HistorialReportePadres", M.HistorialReportePadres),
]


def _seed():
    M.Base.metadata.drop_all(bind=engine)
    M.Base.metadata.create_all(bind=engine)
    d = SessionLocal()
    try:
        for col, ano, gra, cur, nom in ((COL_A, ANO_A, GRA_A, CUR_A, "A"),
                                        (COL_B, ANO_B, GRA_B, CUR_B, "B")):
            d.add(M.Colegio(id=col, nombre="Colegio " + nom, codigo=nom.lower(),
                            plan_primaria=True, plan_secundaria=True))
            d.add(M.AnoEscolar(id=ano, colegio_id=col, nombre="2025-2026",
                               activo=True, dias_trabajados="{}"))
            d.add(M.Grado(id=gra, colegio_id=col, nombre="3ro Secundaria",
                          nivel="secundaria", orden=3))
            d.add(M.Curso(id=cur, colegio_id=col, nombre="A", grado_id=gra,
                          ano_escolar_id=ano, activo=True))
        d.add(M.Asignatura(id=MAT, colegio_id=COL_A, nombre="Matematica",
                           codigo="MAT", area="X", area_curricular_codigo="MAT",
                           activo=True))
        for uid, un, rol, col in ((U_DIR, "dir", "direccion", COL_A),
                                  (U_PROF, "prof", "profesor", COL_A),
                                  (U_DIR_B, "dir_b", "direccion", COL_B)):
            u = M.Usuario(id=uid, username=un, nombre=un.upper(), apellido="T",
                          role=rol, colegio_id=col, activo=True)
            u.set_password(PWD)
            d.add(u)

        def _est(eid, nombre, col, cur, activo, lista):
            d.add(M.Estudiante(
                id=eid, colegio_id=col, nombre=nombre, apellido="G", curso_id=cur,
                activo=activo, no_lista=lista,
                condicion=("activo" if activo else "retirado"),
                fecha_retiro=(None if activo else date(2026, 5, 10)),
                motivo_retiro=(None if activo else "Traslado"),
                retirado_por=(None if activo else U_DIR)))

        _est(E_VACIO, "Sofia", COL_A, CUR_A, False, 1)
        _est(E_LEGACY, "Marta", COL_A, CUR_A, False, 2)
        _est(E_COMPLETO, "Pedro", COL_A, CUR_A, False, 3)
        _est(E_ACTIVO, "Ana", COL_A, CUR_A, True, 4)
        _est(E_OTRO_COL, "Luis", COL_B, CUR_B, False, 1)
        d.flush()

        # E_LEGACY: SOLO las 6 tablas que el purgado contemplaba. Es el perfil
        # en el que el borrado TENIA EXITO y destruia todo.
        d.add(M.Calificacion(colegio_id=COL_A, estudiante_id=E_LEGACY,
                             asignatura_id=MAT, ano_escolar_id=ANO_A, p1_p1=80))
        for i in range(40):
            d.add(M.Asistencia(colegio_id=COL_A, estudiante_id=E_LEGACY,
                               curso_id=CUR_A, asignatura_id=MAT,
                               fecha=date(2026, 3 + (i // 28), (i % 28) + 1),
                               estado="presente", registrado_por=U_PROF))
        d.add(M.ReporteConducta(colegio_id=COL_A, estudiante_id=E_LEGACY,
                                reportado_por=U_PROF, titulo="Incidencia",
                                descripcion="x", tipo="conducta", gravedad="leve",
                                estado="pendiente", fecha=date(2026, 3, 4)))
        d.add(M.CasoPsicologia(colegio_id=COL_A, estudiante_id=E_LEGACY,
                               solicitado_por=U_PROF, motivo="seguimiento",
                               estado="pendiente"))
        d.add(M.HistorialAcademico(colegio_id=COL_A, estudiante_id=E_LEGACY,
                                   ano_escolar_id=ANO_A, grado_id=GRA_A,
                                   curso_id=CUR_A, promedio_final=82,
                                   condicion="promovido"))
        d.add(M.EvalInternaEstudiante(colegio_id=COL_A, estudiante_id=E_LEGACY,
                                      profesor_id=U_PROF, asignatura_id=MAT,
                                      curso_id=CUR_A, periodo=1))

        # E_COMPLETO: las TRECE, incluidas las 6 que el purgado NO contemplaba.
        d.add(M.Calificacion(colegio_id=COL_A, estudiante_id=E_COMPLETO,
                             asignatura_id=MAT, ano_escolar_id=ANO_A, p1_p1=70))
        d.add(M.CalificacionPrimaria(colegio_id=COL_A, estudiante_id=E_COMPLETO,
                                     asignatura_id=MAT, ano_escolar_id=ANO_A,
                                     competencia_numero=1, p1=75))
        d.add(M.CalificacionSecundaria(colegio_id=COL_A, estudiante_id=E_COMPLETO,
                                       asignatura_id=MAT, ano_escolar_id=ANO_A,
                                       competencia_numero=1, p1=88, p2=91))
        d.add(M.RecuperacionPrimaria(colegio_id=COL_A, estudiante_id=E_COMPLETO,
                                     asignatura_id=MAT, ano_escolar_id=ANO_A,
                                     cf_area=62, puntos_final=8, nota_final=70,
                                     condicion_final="recuperado"))
        d.add(M.EvaluacionExtraSecundaria(colegio_id=COL_A, estudiante_id=E_COMPLETO,
                                          asignatura_id=MAT, ano_escolar_id=ANO_A,
                                          cf_original=65))
        d.add(M.Asistencia(colegio_id=COL_A, estudiante_id=E_COMPLETO, curso_id=CUR_A,
                           asignatura_id=MAT, fecha=date(2026, 3, 3),
                           estado="presente", registrado_por=U_PROF))
        d.add(M.ReporteConducta(colegio_id=COL_A, estudiante_id=E_COMPLETO,
                                reportado_por=U_PROF, titulo="Otra", descripcion="x",
                                tipo="conducta", gravedad="leve", estado="pendiente",
                                fecha=date(2026, 3, 5)))
        d.add(M.CasoPsicologia(colegio_id=COL_A, estudiante_id=E_COMPLETO,
                               solicitado_por=U_PROF, motivo="apoyo",
                               estado="pendiente"))
        d.add(M.HistorialAcademico(colegio_id=COL_A, estudiante_id=E_COMPLETO,
                                   ano_escolar_id=ANO_A, grado_id=GRA_A,
                                   curso_id=CUR_A, promedio_final=79,
                                   condicion="promovido"))
        d.add(M.EvalInternaEstudiante(colegio_id=COL_A, estudiante_id=E_COMPLETO,
                                      profesor_id=U_PROF, asignatura_id=MAT,
                                      curso_id=CUR_A, periodo=1))
        d.add(M.HistorialComunicacionPadres(colegio_id=COL_A, estudiante_id=E_COMPLETO,
                                            tipo_comunicacion="reporte",
                                            mensaje_enviado="aviso",
                                            enviado_por=U_DIR))
        d.add(M.HistorialReportePadres(colegio_id=COL_A, estudiante_id=E_COMPLETO,
                                       reporte_id=1, enviado_por=U_DIR,
                                       mensaje_enviado="aviso"))
        d.commit()
    finally:
        d.close()


def login(u):
    r = client.post("/api/auth/login", json={"username": u, "password": PWD})
    assert r.status_code == 200, f"login {u}: {r.status_code} {r.text[:160]}"
    return {"Authorization": "Bearer " + r.json()["token"]}


_seed()
TOK = {u: login(u) for u in ("dir", "dir_b", "prof")}


def foto():
    """Retrato COMPLETO de las trece tablas: conteos + ids."""
    d = SessionLocal()
    try:
        out = {}
        for nombre, modelo in TABLAS:
            filas = d.query(modelo).all()
            out[nombre] = (len(filas), sorted(f.id for f in filas))
        return out
    finally:
        d.close()


def resumen(f):
    return {k: v[0] for k, v in f.items() if v[0]}


# ===========================================================================
# A · B · C — DELETE INDIVIDUAL
# ===========================================================================

@test("§A Retirado SIN ninguna historia: 403 y el estudiante sigue existiendo")
def _():
    antes = foto()
    r = client.delete(f"/api/estudiantes/retirados/{E_VACIO}", headers=TOK["dir"])
    assert r.status_code == 403, (r.status_code, r.text[:250])
    assert "deshabilitado" in r.json().get("error", "").lower(), r.json()
    assert foto() == antes, "el 403 cambio algo"
    d = SessionLocal()
    try:
        e = d.query(M.Estudiante).get(E_VACIO)
        assert e is not None, "el estudiante fue BORRADO"
        assert e.activo is False and e.condicion == "retirado"
    finally:
        d.close()


@test("§B Retirado con historia LEGACY: 403 y sus 45 filas siguen idénticas")
def _():
    antes = foto()
    d = SessionLocal()
    try:
        propias = sum(
            d.query(m).filter(m.estudiante_id == E_LEGACY).count()
            for _n, m in TABLAS if _n != "Estudiante")
        assert propias == 45, ("precondicion: 1 calif + 40 asist + 1 reporte + "
                               "1 caso + 1 historial + 1 eval = 45", propias)
    finally:
        d.close()
    r = client.delete(f"/api/estudiantes/retirados/{E_LEGACY}", headers=TOK["dir"])
    assert r.status_code == 403, (r.status_code, r.text[:250])
    assert foto() == antes, "el 403 destruyo historia legacy"
    d = SessionLocal()
    try:
        assert d.query(M.Asistencia).filter_by(estudiante_id=E_LEGACY).count() == 40
        assert d.query(M.CasoPsicologia).filter_by(estudiante_id=E_LEGACY).count() == 1
        assert d.query(M.HistorialAcademico).filter_by(estudiante_id=E_LEGACY).count() == 1
    finally:
        d.close()


@test("§C Retirado con historia en las TRECE tablas: 403 y cero cambios")
def _():
    antes = foto()
    r = client.delete(f"/api/estudiantes/retirados/{E_COMPLETO}", headers=TOK["dir"])
    assert r.status_code == 403, (r.status_code, r.text[:250])
    assert foto() == antes, "el 403 cambio algo"
    d = SessionLocal()
    try:
        for nombre, modelo in TABLAS:
            if nombre == "Estudiante":
                continue
            assert d.query(modelo).filter(
                modelo.estudiante_id == E_COMPLETO).count() >= 1, \
                f"{nombre} perdio la fila del estudiante"
    finally:
        d.close()


# ===========================================================================
# D — DELETE MASIVO
# ===========================================================================

@test("§D El masivo: 403, los tres retirados siguen y nada se borró")
def _():
    antes = foto()
    d = SessionLocal()
    try:
        n_ret = d.query(M.Estudiante).filter_by(colegio_id=COL_A, activo=False).count()
        assert n_ret == 3, ("precondicion: 3 retirados en el colegio A", n_ret)
    finally:
        d.close()
    r = client.delete("/api/estudiantes/retirados/eliminar-todos", headers=TOK["dir"])
    assert r.status_code == 403, (r.status_code, r.text[:250])
    assert "deshabilitado" in r.json().get("error", "").lower(), r.json()
    despues = foto()
    assert despues == antes, "el masivo cambio algo"
    d = SessionLocal()
    try:
        for eid in (E_VACIO, E_LEGACY, E_COMPLETO):
            assert d.query(M.Estudiante).get(eid) is not None, f"{eid} fue borrado"
    finally:
        d.close()


@test("§D2 El rechazo ocurre ANTES de mirar la base: id inexistente da igual 403")
def _():
    antes = foto()
    r = client.delete("/api/estudiantes/retirados/999999", headers=TOK["dir"])
    assert r.status_code == 403, (r.status_code, r.text[:250])
    # un estudiante ACTIVO tampoco abre ninguna via
    r2 = client.delete(f"/api/estudiantes/retirados/{E_ACTIVO}", headers=TOK["dir"])
    assert r2.status_code == 403, (r2.status_code, r2.text[:250])
    assert foto() == antes


# ===========================================================================
# E · F · G — LO QUE DEBE SEGUIR FUNCIONANDO
# ===========================================================================

@test("§E Retirar sigue funcionando: soft-delete completo con auditoría")
def _():
    r = client.request("DELETE", f"/api/estudiantes/{E_ACTIVO}",
                       json={"motivo_retiro": "Cambio de colegio"},
                       headers=TOK["dir"])
    assert r.status_code == 200, (r.status_code, r.text[:250])
    d = SessionLocal()
    try:
        e = d.query(M.Estudiante).get(E_ACTIVO)
        assert e is not None, "Retirar BORRO al estudiante"
        assert e.activo is False, "no quedo inactivo"
        assert e.condicion == "retirado", e.condicion
        assert e.fecha_retiro is not None, "sin fecha de retiro"
        assert e.motivo_retiro == "Cambio de colegio", e.motivo_retiro
        assert e.retirado_por == U_DIR, e.retirado_por
    finally:
        d.close()


@test("§F Reactivar sigue funcionando y limpia los tres campos")
def _():
    r = client.post(f"/api/estudiantes/{E_ACTIVO}/reactivar", headers=TOK["dir"])
    assert r.status_code == 200, (r.status_code, r.text[:250])
    d = SessionLocal()
    try:
        e = d.query(M.Estudiante).get(E_ACTIVO)
        assert e.activo is True and e.condicion == "activo"
        assert e.fecha_retiro is None and e.motivo_retiro is None
        assert e.retirado_por is None
    finally:
        d.close()


@test("§G Un estudiante ACTIVO no se ve afectado por nada de lo anterior")
def _():
    d = SessionLocal()
    try:
        e = d.query(M.Estudiante).get(E_ACTIVO)
        assert e is not None and e.activo is True
        assert d.query(M.Estudiante).filter_by(colegio_id=COL_A, activo=True).count() == 1
    finally:
        d.close()


@test("§G2 El listado de retirados sigue devolviendo a los tres")
def _():
    r = client.get("/api/estudiantes/retirados", headers=TOK["dir"])
    assert r.status_code == 200, r.status_code
    ids = {x["id"] for x in r.json()}
    assert {E_VACIO, E_LEGACY, E_COMPLETO} <= ids, ids
    assert E_OTRO_COL not in ids, "se cuela un estudiante de otro colegio"


# ===========================================================================
# H — TENANT Y ROLES
# ===========================================================================

@test("§H Cross-tenant: el colegio B no toca al retirado del colegio A")
def _():
    antes = foto()
    r = client.delete(f"/api/estudiantes/retirados/{E_COMPLETO}", headers=TOK["dir_b"])
    assert r.status_code == 403, (r.status_code, r.text[:250])
    r2 = client.delete("/api/estudiantes/retirados/eliminar-todos", headers=TOK["dir_b"])
    assert r2.status_code == 403, (r2.status_code, r2.text[:250])
    assert foto() == antes
    # y el retiro normal sigue sin cruzar colegios
    r3 = client.delete(f"/api/estudiantes/{E_COMPLETO}", headers=TOK["dir_b"])
    assert r3.status_code == 404, (r3.status_code, r3.text[:200])
    assert foto() == antes


@test("§H2 Roles: un profesor no alcanza ninguno de los dos endpoints")
def _():
    antes = foto()
    for ruta in (f"/api/estudiantes/retirados/{E_COMPLETO}",
                 "/api/estudiantes/retirados/eliminar-todos"):
        r = client.delete(ruta, headers=TOK["prof"])
        assert r.status_code == 403, (ruta, r.status_code)
    assert client.delete(f"/api/estudiantes/retirados/{E_VACIO}").status_code in (401, 403)
    assert foto() == antes


# ===========================================================================
# I — FRONTEND
# ===========================================================================
_FRONT = os.path.join(_BACKEND, "..", "frontend", "src")


@test("§I El frontend ya no ofrece borrado físico, y conserva Reactivar")
def _():
    ruta = os.path.join(_FRONT, "pages", "estudiantes", "EstudiantesPage.tsx")
    src = open(ruta, encoding="utf-8").read()
    for prohibido in ("retirados/eliminar-todos", "Eliminar todos",
                      "Eliminar PERMANENTEMENTE", "retirados/${est.id}"):
        assert prohibido not in src, f"el frontend aun ofrece: {prohibido}"
    assert "handleReactivar" in src and "Reactivar" in src, \
        "se perdio el boton de Reactivar"
    # y no se invento ningun sustituto
    for inventado in ("Archivar", "Purgar", "Borrar definitivamente"):
        assert inventado not in src, f"se agrego una accion nueva: {inventado}"


@test("§ZZ FOTO GLOBAL: nada cambió en las trece tablas en toda la suite")
def _():
    d = SessionLocal()
    try:
        # los cuatro estudiantes del colegio A y el del B siguen existiendo
        for eid in (E_VACIO, E_LEGACY, E_COMPLETO, E_ACTIVO, E_OTRO_COL):
            assert d.query(M.Estudiante).get(eid) is not None, f"{eid} desaparecio"
        # y la historia sigue completa
        assert d.query(M.Asistencia).count() == 41, d.query(M.Asistencia).count()
        assert d.query(M.CalificacionSecundaria).count() == 1
        assert d.query(M.CalificacionPrimaria).count() == 1
        assert d.query(M.RecuperacionPrimaria).count() == 1
        assert d.query(M.EvaluacionExtraSecundaria).count() == 1
        assert d.query(M.HistorialComunicacionPadres).count() == 1
        assert d.query(M.HistorialReportePadres).count() == 1
    finally:
        d.close()
    a = os.path.getmtime(_REPO_SGE) if os.path.exists(_REPO_SGE) else None
    assert a == _sge_mtime, "sge.db fue modificado"


print("\n" + "=" * 70)
print(f"{B}P0.1 PURGADO DESHABILITADO: {_ok}/{_total} pruebas{X}")
if _fail:
    print(f"{R}FALLARON:{X}")
    for n, e in _fail:
        print(f"  - {n}: {e}")
    sys.exit(1)
print(f"{G}TODO VERDE{X}")
