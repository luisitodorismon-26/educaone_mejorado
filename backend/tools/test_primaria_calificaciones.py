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
        def AP(prof, cur, asig, col=COL_A, ano=ANO_A, activo=True, titular=False):
            nonlocal n
            n += 1
            d.add(M.AsignacionProfesor(id=n, colegio_id=col, profesor_id=prof,
                                       curso_id=cur, asignatura_id=asig,
                                       ano_escolar_id=ano, activo=activo,
                                       es_titular=titular))

        # EL PROFESOR MIXTO: Inglés en Primaria y en Secundaria, y titular del
        # curso de primaria (el validador del Registro lo exige).
        AP(PROF_MIXTO, CUR_PRIM, INGLES, titular=True)
        AP(PROF_MIXTO, CUR_SEC, INGLES)
        # solo primaria
        AP(PROF_PRIM, CUR_PRIM, CNAT)
        AP(PROF_PRIM, CUR_INI, INGLES)      # para el caso Inicial
        # otro profesor, otro curso de primaria
        AP(PROF_OTRO, CUR_PRIM2, INGLES)
        AP(DIR_B, CUR_B, MAT_B, col=COL_B, ano=ANO_B)

        # El Registro exige la ficha del centro: sin ella su validador responde
        # 400 antes de mirar nada, y el smoke no probaria nada.
        d.add(M.ConfiguracionColegio(
            colegio_id=COL_A, nombre="Colegio A", rnc="130000000",
            codigo_centro="05123", distrito="05", regional="10",
            director="Directora", direccion="Calle 1", telefono="8090000000"))
        # En primaria un solo docente dicta todas las áreas del grado: el
        # validador exige ese titular y un horario para el curso.
        d.add(M.Horario(id=900, colegio_id=COL_A, profesor_id=PROF_MIXTO,
                        curso_id=CUR_PRIM, asignatura_id=INGLES, dia="Lunes",
                        hora_inicio="08:00", hora_fin="08:45",
                        tipo_bloque="clase", activo=True))

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


def _nota(est, asig, campo, comp=1):
    """El valor guardado del campo, o None si no se guardo (con o sin fila)."""
    c = _calif(est, asig, comp)
    return None if c is None else c[campo]


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
    assert _nota(E_PRIM, INGLES, "p1") is None, "escribio en un periodo cerrado"
    assert r.json().get("periodos_cerrados_ignorados") == [1], r.json()
    assert "cerrado" in r.json().get("aviso", "").lower()


@test("A3 P1 cerrado: tampoco se guarda rp1")
def _():
    _seed(cerrar_periodos=(1,))
    r = guardar(H_MIX, E_PRIM, INGLES, rp1=90)
    assert r.status_code == 200, (r.status_code, r.text[:250])
    assert _nota(E_PRIM, INGLES, "rp1") is None


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
    assert _nota(E_PRIM, INGLES, "p1") is None, "un permiso vencido dejo escribir"


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
    assert _nota(E_PRIM, INGLES, "p1") is None


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


# ==========================================================================
# C — EL NIVEL LO DECIDE EL CURSO
# ==========================================================================
@test("C1 un alumno de PRIMARIA se califica con normalidad")
def _():
    _seed()
    r = guardar(H_MIX, E_PRIM, INGLES, p1=80)
    assert r.status_code == 200, (r.status_code, r.text[:250])


@test("C2 un alumno de SECUNDARIA -> 400, y no se crea nada")
def _():
    _seed()
    # PROF_MIXTO tiene asignación REAL de Inglés en el curso de Secundaria:
    # el rechazo tiene que venir del nivel del curso, no de la asignación.
    r = guardar(H_MIX, E_SEC, INGLES, p1=80)
    assert r.status_code == 400, (r.status_code, r.text[:250])
    assert "Primaria" in r.json()["error"]
    assert _n_calif_primaria() == 0, "creo una CalificacionPrimaria para Secundaria"


@test("C3 un alumno de INICIAL -> 400: 'no es secundaria' no significa 'es primaria'")
def _():
    _seed()
    r = guardar(H_PRIM, E_INI, INGLES, p1=80)
    assert r.status_code == 400, (r.status_code, r.text[:250])
    assert "Primaria" in r.json()["error"]
    assert _n_calif_primaria() == 0


@test("C4 nivel indeterminable (grado sin nivel, o con un nivel inválido) -> 400")
def _():
    # `cursos.grado_id` es NOT NULL, así que lo indeterminable en la práctica es
    # un grado cuyo `nivel` esté vacío o traiga un valor que no reconocemos.
    for valor in (None, '', '   ', 'xyz', 'Primario'):
        _seed()
        d = SessionLocal()
        try:
            d.query(M.Grado).filter_by(id=G_PRIM).update({"nivel": valor})
            d.commit()
        finally:
            d.close()
        r = guardar(H_MIX, E_PRIM, INGLES, p1=80)
        assert r.status_code == 400, (valor, r.status_code, r.text[:250])
        assert _n_calif_primaria() == 0, valor


@test("C4b 'Primaria' con mayúscula o espacios SÍ se reconoce")
def _():
    for valor in ('Primaria', 'PRIMARIA', ' primaria '):
        _seed()
        d = SessionLocal()
        try:
            d.query(M.Grado).filter_by(id=G_PRIM).update({"nivel": valor})
            d.commit()
        finally:
            d.close()
        r = guardar(H_MIX, E_PRIM, INGLES, p1=80)
        assert r.status_code == 200, (valor, r.status_code, r.text[:250])


@test("C5 el aislamiento entre colegios sigue igual")
def _():
    _seed()
    # Dirección de B no puede ni llegar: no es profesor
    r = guardar(H_DIRB, E_PRIM, INGLES, p1=80)
    assert r.status_code == 403, (r.status_code, r.text[:200])
    # y un profesor de A no alcanza a un alumno de B
    r = guardar(H_MIX, E_B, MAT_B, p1=80)
    assert r.status_code == 404, (r.status_code, r.text[:200])
    assert _n_calif_primaria() == 0


# ==========================================================================
# D — PROFESOR MULTINIVEL: UN NIVEL NO CONTAMINA AL OTRO
# ==========================================================================
@test("D1 el profesor mixto califica su materia de PRIMARIA")
def _():
    _seed()
    assert guardar(H_MIX, E_PRIM, INGLES, p1=85).status_code == 200
    assert _calif(E_PRIM, INGLES)["p1"] == 85


@test("D2 el mismo profesor califica su materia de SECUNDARIA por SU flujo")
def _():
    _seed()
    r = client.post("/api/calificaciones-secundaria", headers=H_MIX, json={
        "estudiante_id": E_SEC, "asignatura_id": INGLES,
        "competencia_numero": 1, "p1": 85})
    assert r.status_code == 200, (r.status_code, r.text[:250])
    d = SessionLocal()
    try:
        assert d.query(M.CalificacionSecundaria).filter_by(
            estudiante_id=E_SEC, asignatura_id=INGLES).first() is not None
        # y NO se creó nada en el carril de primaria
        assert d.query(M.CalificacionPrimaria).count() == 0, (
            "Secundaria escribio en CalificacionPrimaria")
    finally:
        d.close()


@test("D3 tener asignación en Primaria no da acceso a otro curso de Primaria")
def _():
    _seed()
    # PROF_MIXTO da Inglés en CUR_PRIM, no en CUR_PRIM2
    r = guardar(H_MIX, E_PRIM2, INGLES, p1=80)
    assert r.status_code == 403, (r.status_code, r.text[:250])
    assert "asignada" in r.json()["error"].lower()
    assert _n_calif_primaria() == 0


@test("D4 tener asignación en Secundaria no da acceso a la materia de Primaria")
def _():
    _seed()
    # PROF_OTRO da Inglés en CUR_PRIM2; no da Ciencias Naturales en ningún lado
    r = guardar(H_OTRO, E_PRIM, CNAT, p1=80)
    assert r.status_code == 403, (r.status_code, r.text[:250])
    assert _n_calif_primaria() == 0


# ==========================================================================
# E — ALCANCE DE LECTURA
#   Misma matriz que el GET de Secundaria: solo se restringe al profesor.
# ==========================================================================
@test("E1 profesor con la asignación exacta -> 200")
def _():
    _seed()
    r = leer(H_MIX, CUR_PRIM, INGLES)
    assert r.status_code == 200, (r.status_code, r.text[:250])


@test("E2 profesor del mismo curso pero OTRA materia -> 403")
def _():
    _seed()
    # PROF_MIXTO da Inglés en CUR_PRIM; Ciencias Naturales la da PROF_PRIM
    r = leer(H_MIX, CUR_PRIM, CNAT)
    assert r.status_code == 403, (r.status_code, r.text[:250])
    assert "asignación" in r.json()["error"].lower()


@test("E3 profesor de OTRO curso -> 403")
def _():
    _seed()
    # PROF_OTRO da Inglés en CUR_PRIM2, no en CUR_PRIM
    r = leer(H_OTRO, CUR_PRIM, INGLES)
    assert r.status_code == 403, (r.status_code, r.text[:250])
    # y en el suyo sí entra
    assert leer(H_OTRO, CUR_PRIM2, INGLES).status_code == 200


@test("E4 profesor de OTRO colegio -> bloqueado, sin filtrar existencia")
def _():
    _seed()
    r = leer(H_DIRB, CUR_PRIM, INGLES)
    assert r.status_code == 404, (r.status_code, r.text[:250])


@test("E5 Dirección y coordinación conservan la supervisión, igual que en Secundaria")
def _():
    _seed()
    for hdr, quien in ((H_DIR, "direccion"), (H_COORD, "coordinador"),
                       (H_SECRE, "secretaria")):
        rp = leer(hdr, CUR_PRIM, INGLES)
        rs = client.get(f"/api/calificaciones/curso/{CUR_SEC}/asignatura/{INGLES}",
                        headers=hdr)
        assert rp.status_code == rs.status_code, (
            quien, "Primaria y Secundaria difieren", rp.status_code, rs.status_code)
        assert rp.status_code == 200, (quien, rp.status_code, rp.text[:200])


@test("E6 profesor multinivel: lee su Primaria, y su Secundaria por el otro flujo")
def _():
    _seed()
    assert leer(H_MIX, CUR_PRIM, INGLES).status_code == 200
    r = client.get(f"/api/calificaciones/curso/{CUR_SEC}/asignatura/{INGLES}",
                   headers=H_MIX)
    assert r.status_code == 200, (r.status_code, r.text[:250])
    # pero el endpoint de Primaria NO le devuelve su curso de Secundaria
    r = leer(H_MIX, CUR_SEC, INGLES)
    assert r.status_code == 400, (r.status_code, r.text[:250])
    assert "primaria" in r.text.lower()


# ==========================================================================
# F — CF, LITERAL Y max(P, RP)
#   Estas reglas NO se cambian: se fijan tal como estan hoy, para que
#   endurecer el endpoint no las mueva.
# ==========================================================================
def _modelo(**campos):
    c = M.CalificacionPrimaria(estudiante_id=E_PRIM, asignatura_id=INGLES,
                               competencia_numero=1, colegio_id=COL_A)
    for k, v in campos.items():
        setattr(c, k, v)
    return c


@test("F1 valor_periodo: RP REEMPLAZA a P (R2-A2)")
def _():
    # CAMBIO DE REQUISITO ACADEMICO, no de implementacion. Hasta R2 esto era
    # max(P, RP). La norma dice que la recuperacion se asienta en su columna
    # "siendo esta ultima la calificacion final del periodo": RP no compite
    # con P, lo sustituye. Los dos primeros asserts valian igual con max();
    # los de F2 son los que cambian de resultado.
    assert _modelo(p1=60, rp1=75).valor_periodo(1) == 75
    assert _modelo(p1=60).valor_periodo(1) == 60
    assert _modelo(rp1=75).valor_periodo(1) == 75, "RP sin P deberia valer"
    assert _modelo().valor_periodo(1) is None
    # Casos exigidos por R2-A2
    assert _modelo(p1=50, rp1=70).valor_periodo(1) == 70
    assert _modelo(p1=0, rp1=0).valor_periodo(1) == 0, "0 no es ausencia"
    assert _modelo(p1=100, rp1=90).valor_periodo(1) == 90


@test("F2 una recuperación MENOR que la nota original SI baja el período")
def _():
    # Antes de R2 esto devolvia 80, por max(). Ahora manda lo que el docente
    # asento como calificacion final del periodo.
    assert _modelo(p1=80, rp1=50).valor_periodo(1) == 50
    assert _modelo(p1=80, rp1=80).valor_periodo(1) == 80


@test("F3 CF con los 4 períodos = promedio, redondeado a 2 decimales")
def _():
    c = _modelo(p1=80, p2=78, p3=79, p4=78)
    assert c.calcular_final() == 78.75
    c = _modelo(p1=71, p2=74, p3=88, p4=82)
    assert c.calcular_final() == 78.75
    # el redondeo es a 2 decimales
    c = _modelo(p1=80, p2=80, p3=80, p4=81)
    assert c.calcular_final() == 80.25


@test("F4 CF oficial: PENDIENTE la bloquea, NE sale del divisor (R2-A5)")
def _():
    # CAMBIO DE REQUISITO ACADEMICO. Hasta R2 este caso devolvia 85: el codigo
    # aplicaba siempre la regla de excepcion de NE porque no sabia distinguir
    # un NE de un periodo que nadie habia cargado todavia. La norma tiene DOS
    # reglas: la normal divide entre 4, y la de NE promedia "los periodos
    # evaluados". Un hueco sin marcar no es NE: es PENDIENTE, y bloquea.
    assert _modelo(p1=80, p2=90).calcular_final() is None, \
        "tres pendientes no pueden producir CF"
    assert _modelo(p1=90).calcular_final() is None
    assert _modelo().calcular_final() is None, "sin ningun periodo no hay CF"
    # Con los cuatro resueltos si existe.
    assert _modelo(p1=80, p2=90, p3=80, p4=90).calcular_final() == 85.0
    # NE sale del divisor.
    c = _modelo(p1=80, p2=90)
    c.ne3 = True
    c.ne4 = True
    assert c.calcular_final() == 85.0, "NE deberia salir del divisor"
    # Lo provisional sigue disponible, pero se llama por su nombre.
    assert _modelo(p1=80, p2=90).promedio_acumulado() == 85.0


@test("F5 la CF usa el valor recuperado del período, no la nota original")
def _():
    c = _modelo(p1=60, rp1=80, p2=80, p3=80, p4=80)
    assert c.calcular_final() == 80.0, "la CF ignoro la recuperacion"


@test("F6 literal: A>=90, B>=80, C>=70, F por debajo")
def _():
    c = _modelo()
    for nota, esperado in ((100, 'A'), (90, 'A'), (89.99, 'B'), (80, 'B'),
                           (79.99, 'C'), (70, 'C'), (69.99, 'F'), (0, 'F')):
        assert c.get_literal(nota) == esperado, (nota, c.get_literal(nota))
    assert c.get_literal(None) is None


@test("F7 el endpoint calcula CF y literal al guardar, de punta a punta")
def _():
    _seed()
    for p, v in (('p1', 80), ('p2', 78), ('p3', 79), ('p4', 78)):
        assert guardar(H_MIX, E_PRIM, INGLES, **{p: v}).status_code == 200
    c = _calif(E_PRIM, INGLES)
    assert c["final"] == 78.75, c
    assert c["literal"] == 'C', c


# ==========================================================================
# G — RECUPERACIÓN DE ÁREA (reglas EXISTENTES, no se rediseñan)
# ==========================================================================
def _rec(**campos):
    r = M.RecuperacionPrimaria(estudiante_id=E_PRIM, asignatura_id=INGLES,
                               colegio_id=COL_A)
    for k, v in campos.items():
        setattr(r, k, v)
    return r


@test("G1 es COMPLEMENTARIA: los puntos se suman a la CF")
def _():
    r = _rec(cf_area=60, puntos_final=10)
    r.recalcular()
    assert r.recuperacion_final == 70, r.recuperacion_final


@test("G2 el máximo de puntos es 100 - CF: nunca se pasa de 100")
def _():
    assert _rec(cf_area=60).maximo_puntos() == 40
    assert _rec(cf_area=95).maximo_puntos() == 5
    assert _rec(cf_area=100).maximo_puntos() == 0


@test("G3 el corte de aprobación es 65")
def _():
    assert M.RecuperacionPrimaria.MINIMO == 65
    r = _rec(cf_area=60, puntos_final=5); r.recalcular()
    assert r.condicion_final == 'aprobado_recuperacion', r.condicion_final
    r = _rec(cf_area=60, puntos_final=4); r.recalcular()
    assert r.condicion_final != 'aprobado_recuperacion', r.condicion_final


@test("G4 con la CF ya aprobada no hace falta recuperación")
def _():
    r = _rec(cf_area=70); r.recalcular()
    assert r.condicion_final == 'aprobado', r.condicion_final
    assert r.fase_pendiente() is None, r.fase_pendiente()


@test("G5 si tras la recuperación final sigue por debajo, queda la especial")
def _():
    r = _rec(cf_area=50, puntos_final=5); r.recalcular()
    assert r.recuperacion_final == 55
    assert r.condicion_final != 'aprobado_recuperacion'
    assert r.fase_pendiente() == 'especial', r.fase_pendiente()
    r.puntos_especial = 10; r.recalcular()
    assert r.recuperacion_especial == 60


# ==========================================================================
# H — BOLETÍN Y REGISTRO (smoke: que lo endurecido no los rompa)
# ==========================================================================
@test("H1 el boletín de primaria lee las notas guardadas")
def _():
    _seed()
    for p, v in (('p1', 90), ('p2', 90), ('p3', 90), ('p4', 90)):
        assert guardar(H_MIX, E_PRIM, INGLES, **{p: v}).status_code == 200
    r = client.get(f"/api/boletines-primaria/estudiante/{E_PRIM}", headers=H_DIR)
    assert r.status_code == 200, (r.status_code, r.text[:300])
    assert "90" in r.text or "A" in r.text


@test("H2 el boletín de primaria RECHAZA un estudiante de secundaria")
def _():
    _seed()
    r = client.get(f"/api/boletines-primaria/estudiante/{E_SEC}", headers=H_DIR)
    assert r.status_code in (400, 404), (r.status_code, r.text[:250])


@test("H3 el boletín respeta el alcance del profesor y el colegio")
def _():
    _seed()
    assert client.get(f"/api/boletines-primaria/estudiante/{E_PRIM}",
                      headers=H_MIX).status_code == 200
    # PROF_OTRO no da clase en CUR_PRIM
    assert client.get(f"/api/boletines-primaria/estudiante/{E_PRIM}",
                      headers=H_OTRO).status_code == 403
    # y otro colegio no llega
    assert client.get(f"/api/boletines-primaria/estudiante/{E_PRIM}",
                      headers=H_DIRB).status_code == 404


@test("H4 el Registro de primaria se genera con las notas que guarda el endpoint")
def _():
    _seed()
    # Las tres competencias completas de CADA área del curso, por la vía normal
    # y con el docente que tiene cada una asignada.
    for hdr, asig in ((H_MIX, INGLES), (H_PRIM, CNAT)):
        for comp in (1, 2, 3):
            assert guardar(hdr, E_PRIM, asig, comp=comp,
                           p1=80, p2=85, p3=90, p4=95).status_code == 200, (asig, comp)
    # El Registro exige asistencia; en primaria es del CURSO, sin asignatura.
    d = SessionLocal()
    try:
        d.add(M.Asistencia(colegio_id=COL_A, estudiante_id=E_PRIM, curso_id=CUR_PRIM,
                           asignatura_id=None, fecha=date(2026, 9, 7),
                           estado="presente", registrado_por=PROF_MIXTO))
        d.commit()
    finally:
        d.close()
    r = client.get(f"/api/registros/primaria/{CUR_PRIM}", headers=H_DIR)
    assert r.status_code == 200, (r.status_code, r.text[:400])
    # y el alcance del profesor se mantiene
    assert client.get(f"/api/registros/primaria/{CUR_PRIM}",
                      headers=H_OTRO).status_code == 403


@test("H5 el validador del Registro sigue exigiendo lo suyo: sin notas, 400")
def _():
    _seed()
    r = client.get(f"/api/registros/primaria/{CUR_PRIM}", headers=H_DIR)
    assert r.status_code == 400, (r.status_code, r.text[:250])
    assert "alificaciones" in r.text, r.text[:250]


@test("B9 con una fila YA existente, un payload mixto no pisa la nota buena previa")
def _():
    _seed()
    assert guardar(H_MIX, E_PRIM, INGLES, p1=80, p2=70).status_code == 200
    # p1 válido + p2 inválido: ni el cambio de p1 puede quedar
    r = guardar(H_MIX, E_PRIM, INGLES, p1=90, p2=500)
    assert r.status_code == 400, (r.status_code, r.text[:250])
    c = _calif(E_PRIM, INGLES)
    assert c["p1"] == 80, ("se aplico p1 pese al fallo de p2", c)
    assert c["p2"] == 70, ("se toco p2", c)
    # La CF no existe porque P3 y P4 estan PENDIENTES (R2-A5). Lo que este
    # caso comprueba es la atomicidad del guardado, no el valor de la CF.
    assert c["final"] is None, c


# ==========================================================================
# I — UN PERIODO CERRADO NO DEJA FILAS VACIAS
#   El `db.add()` iba antes de mirar los periodos, asi que un intento sobre un
#   periodo cerrado creaba igualmente la fila y la commiteaba SIN ninguna nota.
# ==========================================================================
@test("I1 calificación NUEVA + solo P1 cerrado: no se crea fila vacía")
def _():
    _seed(cerrar_periodos=(1,))
    assert _n_calif_primaria() == 0
    r = guardar(H_MIX, E_PRIM, INGLES, p1=80)
    assert r.status_code == 200, (r.status_code, r.text[:250])
    assert _n_calif_primaria() == 0, "creo una CalificacionPrimaria sin ninguna nota"
    cuerpo = r.json()
    assert cuerpo["periodos_cerrados_ignorados"] == [1], cuerpo
    assert "cerrado" in cuerpo.get("aviso", "").lower(), cuerpo
    assert cuerpo["id"] is None and cuerpo["calificacion"] is None, cuerpo


@test("I2 fila EXISTENTE + P1 cerrado: la nota previa queda intacta, sin fila extra")
def _():
    _seed()
    assert guardar(H_MIX, E_PRIM, INGLES, p1=80).status_code == 200
    assert _n_calif_primaria() == 1
    d = SessionLocal()
    try:
        d.query(M.AnoEscolar).filter_by(id=ANO_A).update({"p1_cerrado": True})
        d.commit()
    finally:
        d.close()
    r = guardar(H_MIX, E_PRIM, INGLES, p1=10)
    assert r.status_code == 200, (r.status_code, r.text[:250])
    assert _n_calif_primaria() == 1, "creo una fila adicional"
    assert _calif(E_PRIM, INGLES)["p1"] == 80, "piso la nota previa"
    assert r.json()["periodos_cerrados_ignorados"] == [1]


@test("I3 NUEVA + P1 cerrado y P2 abierto: se crea UNA fila, solo con P2")
def _():
    _seed(cerrar_periodos=(1,))
    r = guardar(H_MIX, E_PRIM, INGLES, p1=80, p2=75)
    assert r.status_code == 200, (r.status_code, r.text[:250])
    assert _n_calif_primaria() == 1, "no creo la fila que si tocaba crear"
    c = _calif(E_PRIM, INGLES)
    assert c["p1"] is None and c["p2"] == 75, c
    assert r.json()["periodos_cerrados_ignorados"] == [1]
    assert r.json()["id"] is not None


@test("I4 NUEVA + P1 cerrado CON permiso temporal: sí se crea y se guarda")
def _():
    _seed(cerrar_periodos=(1,))
    d = SessionLocal()
    try:
        d.add(M.PermisoTemporalCalificacion(
            colegio_id=COL_A, profesor_id=PROF_MIXTO, periodo=1,
            asignatura_id=INGLES, activo=True,
            fecha_fin=APP.now_rd() + timedelta(days=1), otorgado_por=DIR))
        d.commit()
    finally:
        d.close()
    r = guardar(H_MIX, E_PRIM, INGLES, p1=80)
    assert r.status_code == 200, (r.status_code, r.text[:250])
    assert _n_calif_primaria() == 1
    assert _calif(E_PRIM, INGLES)["p1"] == 80
    assert "periodos_cerrados_ignorados" not in r.json()


@test("I5 los cuatro períodos cerrados: ni fila ni notas, y se avisa de todos")
def _():
    _seed(cerrar_periodos=(1, 2, 3, 4))
    r = guardar(H_MIX, E_PRIM, INGLES, p1=80, p2=81, rp3=90, p4=70)
    assert r.status_code == 200, (r.status_code, r.text[:250])
    assert _n_calif_primaria() == 0
    assert sorted(r.json()["periodos_cerrados_ignorados"]) == [1, 2, 3, 4], r.json()


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
