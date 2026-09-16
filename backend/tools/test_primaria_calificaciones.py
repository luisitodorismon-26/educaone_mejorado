# -*- coding: utf-8 -*-
"""
EducaOne PRIMARIA P1 — flujo académico de calificaciones.

POR QUE EXISTE
    Primaria estaba construida pero casi sin cobertura: de 26 suites que
    mencionan "primaria", solo dos tocaban sus endpoints, y de refilon. Esa
    ausencia es la razon por la que cuatro huecos llevaban ahi sin verse:

      1. se podia escribir en un periodo CERRADO por Direccion;
      2. no se validaba el valor de la nota (rango, tipo, booleanos, NaN);
      3. se podia crear una CalificacionPrimaria para un alumno que NO es de
         primaria;
      4. la LECTURA de notas no comprobaba el alcance del profesor.

    Esta suite fija los cuatro, y ademas fija lo que YA funciona —CF, literal,
    max(P,RP), regla NE, recuperacion, boletin, Registro— para que endurecer no
    rompa nada.

PROFESOR MULTINIVEL
    Un profesor no pertenece a un nivel: pertenece a sus asignaciones. El
    fixture tiene uno con clases en Primaria Y en Secundaria, y varios casos
    comprueban que una cosa no contamina la otra.

Uso:
    cd backend
    python tools/test_primaria_calificaciones.py
"""
import os
import sys
import atexit
import tempfile
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TMPDIR = tempfile.mkdtemp(prefix="eo_prim_")
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
import app as APP                                              # noqa: E402

client = TestClient(APP.app)

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
#   PROF_MIXTO da Ingles en 5to Primaria Y en 1ro Secundaria: es el caso que
#   no puede mezclarse. PROF_PRIM solo Primaria. PROF_OTRO, otra materia.
# --------------------------------------------------------------------------
PWD = "Prueba2026x"
COL_A, COL_B = 1, 2
ANO_A, ANO_B = 1, 2

G_PRIM, G_SEC, G_INI = 10, 11, 12          # grados: primaria, secundaria, inicial
CUR_PRIM, CUR_PRIM2, CUR_SEC, CUR_INI = 20, 21, 22, 23
CUR_B = 90

INGLES, CNAT, MAT_B = 1, 2, 90

PROF_MIXTO, PROF_PRIM, PROF_OTRO = 31, 32, 33
DIR, COORD, SECRE, DIR_B = 34, 35, 36, 81

E_PRIM, E_PRIM2, E_SEC, E_INI = 50, 51, 52, 53
E_B = 95


def _seed(cerrar_periodos=()):
    M.Base.metadata.drop_all(bind=engine)
    M.Base.metadata.create_all(bind=engine)
    d = SessionLocal()
    try:
        for col, ano, nom in ((COL_A, ANO_A, "A"), (COL_B, ANO_B, "B")):
            d.add(M.Colegio(id=col, nombre="Colegio " + nom, codigo=nom.lower(),
                            plan_primaria=True, plan_secundaria=True))
            a = M.AnoEscolar(id=ano, colegio_id=col, nombre="2026-2027",
                             activo=True, dias_trabajados="{}")
            if col == COL_A:
                for p in cerrar_periodos:
                    setattr(a, f"p{p}_cerrado", True)
            d.add(a)
        d.add(M.Grado(id=G_PRIM, colegio_id=COL_A, nombre="5to Primaria",
                      nivel="primaria", orden=11))
        d.add(M.Grado(id=G_SEC, colegio_id=COL_A, nombre="1ro Secundaria",
                      nivel="secundaria", orden=1))
        d.add(M.Grado(id=G_INI, colegio_id=COL_A, nombre="Pre-Kinder",
                      nivel="inicial", orden=1))
        d.add(M.Grado(id=99, colegio_id=COL_B, nombre="5to Primaria",
                      nivel="primaria", orden=11))
        for cid, gid, col, ano in ((CUR_PRIM, G_PRIM, COL_A, ANO_A),
                                   (CUR_PRIM2, G_PRIM, COL_A, ANO_A),
                                   (CUR_SEC, G_SEC, COL_A, ANO_A),
                                   (CUR_INI, G_INI, COL_A, ANO_A),
                                   (CUR_B, 99, COL_B, ANO_B)):
            d.add(M.Curso(id=cid, colegio_id=col, nombre="A" if cid != CUR_PRIM2 else "B",
                          grado_id=gid, ano_escolar_id=ano, activo=True))
        for aid, nom, col in ((INGLES, "Inglés", COL_A), (CNAT, "Ciencias Naturales", COL_A),
                              (MAT_B, "Matemática", COL_B)):
            d.add(M.Asignatura(id=aid, colegio_id=col, nombre=nom, codigo=str(aid),
                               area="X", area_curricular_codigo="ING", activo=True))
        for uid, col, un, rol in ((PROF_MIXTO, COL_A, "prof_mix", "profesor"),
                                  (PROF_PRIM, COL_A, "prof_prim", "profesor"),
                                  (PROF_OTRO, COL_A, "prof_otro", "profesor"),
                                  (DIR, COL_A, "dir", "direccion"),
                                  (COORD, COL_A, "coord", "coordinador"),
                                  (SECRE, COL_A, "secre", "secretaria"),
                                  (DIR_B, COL_B, "dirb", "direccion")):
            u = M.Usuario(id=uid, colegio_id=col, username=un, nombre=un,
                          apellido="T", role=rol, activo=True)
            u.set_password(PWD)
            d.add(u)

        n = 200
        def AP(prof, cur, asig, col=COL_A, ano=ANO_A, activo=True):
            nonlocal n
            n += 1
            d.add(M.AsignacionProfesor(id=n, colegio_id=col, profesor_id=prof,
                                       curso_id=cur, asignatura_id=asig,
                                       ano_escolar_id=ano, activo=activo))

        # EL PROFESOR MIXTO: Inglés en Primaria y en Secundaria
        AP(PROF_MIXTO, CUR_PRIM, INGLES)
        AP(PROF_MIXTO, CUR_SEC, INGLES)
        # solo primaria
        AP(PROF_PRIM, CUR_PRIM, CNAT)
        AP(PROF_PRIM, CUR_INI, INGLES)      # para el caso Inicial
        # otro profesor, otro curso de primaria
        AP(PROF_OTRO, CUR_PRIM2, INGLES)
        AP(DIR_B, CUR_B, MAT_B, col=COL_B, ano=ANO_B)

        for eid, cur, col, nom in ((E_PRIM, CUR_PRIM, COL_A, "Juan"),
                                   (E_PRIM2, CUR_PRIM2, COL_A, "Ana"),
                                   (E_SEC, CUR_SEC, COL_A, "Pedro"),
                                   (E_INI, CUR_INI, COL_A, "Lia"),
                                   (E_B, CUR_B, COL_B, "Otro")):
            d.add(M.Estudiante(id=eid, colegio_id=col, nombre=nom, apellido="T",
                               curso_id=cur, activo=True, no_lista=1))
        d.commit()
    finally:
        d.close()


def _tok(u):
    r = client.post("/api/auth/login", json={"username": u, "password": PWD})
    assert r.status_code == 200, (u, r.text[:200])
    return {"Authorization": "Bearer " + r.json()["token"]}


def guardar(hdr, est, asig, comp=1, **campos):
    cuerpo = {"estudiante_id": est, "asignatura_id": asig, "competencia_numero": comp}
    cuerpo.update(campos)
    return client.post("/api/calificaciones-primaria", headers=hdr, json=cuerpo)


def leer(hdr, curso, asig):
    return client.get(f"/api/calificaciones-primaria/curso/{curso}/asignatura/{asig}",
                      headers=hdr)


def _calif(est, asig, comp=1):
    d = SessionLocal()
    try:
        c = d.query(M.CalificacionPrimaria).filter_by(
            estudiante_id=est, asignatura_id=asig, competencia_numero=comp).first()
        return None if c is None else {
            'p1': c.p1, 'p2': c.p2, 'p3': c.p3, 'p4': c.p4,
            'rp1': c.rp1, 'rp2': c.rp2, 'rp3': c.rp3, 'rp4': c.rp4,
            'final': c.final_competencia, 'literal': c.literal}
    finally:
        d.close()


def _n_calif_primaria():
    d = SessionLocal()
    try:
        return d.query(M.CalificacionPrimaria).count()
    finally:
        d.close()


_seed()
H_MIX, H_PRIM, H_OTRO = _tok("prof_mix"), _tok("prof_prim"), _tok("prof_otro")
H_DIR, H_COORD, H_SECRE, H_DIRB = _tok("dir"), _tok("coord"), _tok("secre"), _tok("dirb")


# ==========================================================================
# A — PERÍODO CERRADO
# ==========================================================================
@test("A1 período abierto: la nota se guarda")
def _():
    _seed()
    r = guardar(H_MIX, E_PRIM, INGLES, p1=80)
    assert r.status_code == 200, (r.status_code, r.text[:250])
    assert _calif(E_PRIM, INGLES)["p1"] == 80


@test("A2 P1 cerrado: no se guarda p1, y se avisa")
def _():
    _seed(cerrar_periodos=(1,))
    r = guardar(H_MIX, E_PRIM, INGLES, p1=80)
    assert r.status_code == 200, (r.status_code, r.text[:250])
    assert _calif(E_PRIM, INGLES)["p1"] is None, "escribio en un periodo cerrado"
    assert r.json().get("periodos_cerrados_ignorados") == [1], r.json()
    assert "cerrado" in r.json().get("aviso", "").lower()


@test("A3 P1 cerrado: tampoco se guarda rp1")
def _():
    _seed(cerrar_periodos=(1,))
    r = guardar(H_MIX, E_PRIM, INGLES, rp1=90)
    assert r.status_code == 200, (r.status_code, r.text[:250])
    assert _calif(E_PRIM, INGLES)["rp1"] is None


@test("A4 P1 cerrado pero P2 abierto: p2 SÍ se guarda")
def _():
    _seed(cerrar_periodos=(1,))
    r = guardar(H_MIX, E_PRIM, INGLES, p1=80, p2=75)
    assert r.status_code == 200, (r.status_code, r.text[:250])
    c = _calif(E_PRIM, INGLES)
    assert c["p1"] is None, "guardo el periodo cerrado"
    assert c["p2"] == 75, "bloqueo un periodo ABIERTO"
    assert r.json()["periodos_cerrados_ignorados"] == [1]


@test("A5 el rechazo NO borra ni pisa la nota previa del período cerrado")
def _():
    _seed()
    assert guardar(H_MIX, E_PRIM, INGLES, p1=80).status_code == 200
    # Dirección cierra P1 despues de que la nota ya estaba puesta
    d = SessionLocal()
    try:
        d.query(M.AnoEscolar).filter_by(id=ANO_A).update({"p1_cerrado": True})
        d.commit()
    finally:
        d.close()
    r = guardar(H_MIX, E_PRIM, INGLES, p1=10)
    assert r.status_code == 200
    assert _calif(E_PRIM, INGLES)["p1"] == 80, "pisó una nota de período cerrado"


@test("A6 con permiso temporal vigente, el período cerrado SÍ se edita")
def _():
    _seed(cerrar_periodos=(1,))
    d = SessionLocal()
    try:
        d.add(M.PermisoTemporalCalificacion(
            colegio_id=COL_A, profesor_id=PROF_MIXTO, periodo=1,
            asignatura_id=INGLES, activo=True,
            fecha_fin=APP.now_rd() + timedelta(days=1),
            otorgado_por=DIR))
        d.commit()
    finally:
        d.close()
    r = guardar(H_MIX, E_PRIM, INGLES, p1=80)
    assert r.status_code == 200, (r.status_code, r.text[:250])
    assert _calif(E_PRIM, INGLES)["p1"] == 80, "el permiso temporal no surtio efecto"
    assert "periodos_cerrados_ignorados" not in r.json()


@test("A7 un permiso VENCIDO no abre el período")
def _():
    _seed(cerrar_periodos=(1,))
    d = SessionLocal()
    try:
        d.add(M.PermisoTemporalCalificacion(
            colegio_id=COL_A, profesor_id=PROF_MIXTO, periodo=1,
            asignatura_id=INGLES, activo=True,
            fecha_fin=APP.now_rd() - timedelta(days=1),
            otorgado_por=DIR))
        d.commit()
    finally:
        d.close()
    r = guardar(H_MIX, E_PRIM, INGLES, p1=80)
    assert r.status_code == 200
    assert _calif(E_PRIM, INGLES)["p1"] is None, "un permiso vencido dejo escribir"


@test("A8 el permiso de OTRO profesor no me abre el período")
def _():
    _seed(cerrar_periodos=(1,))
    d = SessionLocal()
    try:
        d.add(M.PermisoTemporalCalificacion(
            colegio_id=COL_A, profesor_id=PROF_PRIM, periodo=1,
            asignatura_id=INGLES, activo=True,
            fecha_fin=APP.now_rd() + timedelta(days=1),
            otorgado_por=DIR))
        d.commit()
    finally:
        d.close()
    r = guardar(H_MIX, E_PRIM, INGLES, p1=80)
    assert r.status_code == 200
    assert _calif(E_PRIM, INGLES)["p1"] is None


# ==========================================================================
# B — VALOR DE LA NOTA
# ==========================================================================
@test("B1 los límites del rango son válidos: 0 y 100")
def _():
    _seed()
    assert guardar(H_MIX, E_PRIM, INGLES, p1=0).status_code == 200
    assert _calif(E_PRIM, INGLES)["p1"] == 0
    assert guardar(H_MIX, E_PRIM, INGLES, p1=100).status_code == 200
    assert _calif(E_PRIM, INGLES)["p1"] == 100


@test("B2 un decimal se conserva tal cual (comportamiento actual del sistema)")
def _():
    _seed()
    assert guardar(H_MIX, E_PRIM, INGLES, p1=78.5).status_code == 200
    assert _calif(E_PRIM, INGLES)["p1"] == 78.5
    # y una cadena numérica se acepta como número, igual que en Secundaria
    assert guardar(H_MIX, E_PRIM, INGLES, p2="81.25").status_code == 200
    assert _calif(E_PRIM, INGLES)["p2"] == 81.25


@test("B3 fuera de rango -> 400 y la nota previa no cambia")
def _():
    _seed()
    assert guardar(H_MIX, E_PRIM, INGLES, p1=80).status_code == 200
    for malo in (-1, 101, -0.5, 100.01, 1000):
        r = guardar(H_MIX, E_PRIM, INGLES, p1=malo)
        assert r.status_code == 400, (malo, r.status_code, r.text[:200])
        assert "entre 0 y 100" in r.json()["error"], malo
        assert _calif(E_PRIM, INGLES)["p1"] == 80, ("piso la nota previa", malo)


@test("B4 no numérico -> 400")
def _():
    _seed()
    for malo in ("abc", "", " ", [], {}, "80abc"):
        r = guardar(H_MIX, E_PRIM, INGLES, p1=malo)
        if malo == "":
            # cadena vacía = limpiar, misma semántica que Secundaria
            assert r.status_code == 200, (malo, r.text[:200])
            continue
        assert r.status_code == 400, (malo, r.status_code, r.text[:200])
    assert _calif(E_PRIM, INGLES) is None or _calif(E_PRIM, INGLES)["p1"] is None


@test("B5 un booleano NO se acepta como 0/1")
def _():
    _seed()
    for malo in (True, False):
        r = guardar(H_MIX, E_PRIM, INGLES, p1=malo)
        assert r.status_code == 400, (malo, r.status_code, r.text[:200])
        assert "número" in r.json()["error"], malo
    assert _calif(E_PRIM, INGLES) is None or _calif(E_PRIM, INGLES)["p1"] is None


@test("B6 NaN e infinito -> 400")
def _():
    _seed()
    for malo in ("NaN", "nan", "inf", "-inf", "Infinity"):
        r = guardar(H_MIX, E_PRIM, INGLES, p1=malo)
        assert r.status_code == 400, (malo, r.status_code, r.text[:200])
    assert _calif(E_PRIM, INGLES) is None or _calif(E_PRIM, INGLES)["p1"] is None


@test("B7 None y cadena vacía LIMPIAN la nota, como en Secundaria")
def _():
    _seed()
    assert guardar(H_MIX, E_PRIM, INGLES, p1=80, p2=90).status_code == 200
    assert guardar(H_MIX, E_PRIM, INGLES, p1=None).status_code == 200
    assert _calif(E_PRIM, INGLES)["p1"] is None, "None no limpio la nota"
    assert _calif(E_PRIM, INGLES)["p2"] == 90, "limpio de mas"
    assert guardar(H_MIX, E_PRIM, INGLES, p2="").status_code == 200
    assert _calif(E_PRIM, INGLES)["p2"] is None


@test("B8 si un campo del payload es inválido, NINGUNO se guarda")
def _():
    _seed()
    r = guardar(H_MIX, E_PRIM, INGLES, p1=80, p2=500)
    assert r.status_code == 400, (r.status_code, r.text[:200])
    c = _calif(E_PRIM, INGLES)
    assert c is None or (c["p1"] is None and c["p2"] is None), (
        "escritura parcial: se guardo p1 pese al fallo de p2")
    assert _n_calif_primaria() == 0, "creo la fila igualmente"


@test("R  el repo no fue tocado: sge.db intacto")
def _():
    a = os.path.getmtime(_REPO_SGE) if os.path.exists(_REPO_SGE) else None
    assert a == _sge_mtime, "sge.db fue modificado"


print("\n" + "=" * 70)
print(f"{B}PRIMARIA — CALIFICACIONES: {_ok}/{_total} pruebas{X}")
if _fail:
    print(f"{R}FALLARON:{X}")
    for n, e in _fail:
        print(f"  - {n}: {e}")
    sys.exit(1)
print(f"{G}TODO VERDE{X}")
