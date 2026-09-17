# -*- coding: utf-8 -*-
"""
EducaOne PRIMARIA P3.1 — asistencia diaria, titularidad y visibilidad.

DE DONDE SALE
    La asistencia de Primaria es del CURSO y del dia: una sola por estudiante y
    fecha. La escribia cualquier profesor con asignacion activa en el curso, y
    en produccion eso ya paso — tres docentes distintos pasaron lista del mismo
    curso, uno de ellos el especialista de Ingles. No se duplico nada, porque un
    indice parcial lo impide; lo que hubo fue SOBRESCRITURA silenciosa, y encima
    `registrado_por` conservaba al autor anterior.

LAS TRES RESPONSABILIDADES, SEPARADAS
    asistencia     -> del CURSO y del dia   -> la escribe el TITULAR
    calificaciones -> de la ASIGNATURA      -> las escribe quien la tiene asignada
    recuperacion   -> de la ASIGNATURA      -> igual, sin cambios

    Ser titular NO da permiso para calificar todas las materias.
    Dar una materia NO da permiso para tocar la asistencia del curso.
    El horario NO concede permisos: aqui no se consulta ni una vez.

Uso:
    cd backend
    python tools/test_primaria_asistencia_titular.py
"""
import os
import sys
import atexit
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TMPDIR = tempfile.mkdtemp(prefix="eo_p31_")
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
# FIXTURE — el 5to A del enunciado, mas los casos que lo rodean.
#
#   ROSA   titular de 5to A · Lengua, Matematica, Naturales
#   LUIS   Ingles en 5to A  · y ademas Ingles en 1ro y 2do de SECUNDARIA
#   PEDRO  Educacion Fisica en 5to A
#   CARLA  Artistica en 5to A
#   AJENO  profesor del colegio SIN nada en 5to A
# --------------------------------------------------------------------------
PWD = "Prueba2026x"
COL_A, COL_B = 1, 2
ANO_A, ANO_B = 1, 2

G_PRIM5, G_PRIM1, G_SEC = 30, 31, 32
CUR_5A, CUR_1A, CUR_SEC1, CUR_SEC2 = 40, 41, 42, 43
CUR_SIN_TIT, CUR_DOS_TIT = 44, 45
CUR_B = 90

LENGUA, MATE, NAT, INGLES, EF, ART = 1, 2, 3, 4, 5, 6
MAT_B = 90

ROSA, LUIS, PEDRO, CARLA, AJENO, OTRA_TIT = 51, 52, 53, 54, 55, 56
DIR, COORD, DIR_B = 60, 61, 81

E_5A, E_5A_2, E_1A, E_SEC = 70, 71, 72, 73
E_B = 95

FECHA = "2026-09-14"


def _seed():
    M.Base.metadata.drop_all(bind=engine)
    M.Base.metadata.create_all(bind=engine)
    d = SessionLocal()
    try:
        for col, ano, nom in ((COL_A, ANO_A, "A"), (COL_B, ANO_B, "B")):
            d.add(M.Colegio(id=col, nombre="Colegio " + nom, codigo=nom.lower(),
                            plan_primaria=True, plan_secundaria=True))
            d.add(M.AnoEscolar(id=ano, colegio_id=col, nombre="2026-2027",
                               activo=True, dias_trabajados="{}",
                               fecha_inicio=date(2026, 8, 1),
                               fecha_fin=date(2027, 6, 30)))
        d.add(M.Grado(id=G_PRIM5, colegio_id=COL_A, nombre="5to Primaria",
                      nivel="primaria", ciclo="segundo_ciclo", orden=11))
        d.add(M.Grado(id=G_PRIM1, colegio_id=COL_A, nombre="1ro Primaria",
                      nivel="primaria", ciclo="primer_ciclo", orden=7))
        d.add(M.Grado(id=G_SEC, colegio_id=COL_A, nombre="1ro Secundaria",
                      nivel="secundaria", orden=1))
        d.add(M.Grado(id=99, colegio_id=COL_B, nombre="5to Primaria",
                      nivel="primaria", ciclo="segundo_ciclo", orden=11))
        for cid, gid, col, ano, nom in (
                (CUR_5A, G_PRIM5, COL_A, ANO_A, "A"),
                (CUR_1A, G_PRIM1, COL_A, ANO_A, "A"),
                (CUR_SEC1, G_SEC, COL_A, ANO_A, "A"),
                (CUR_SEC2, G_SEC, COL_A, ANO_A, "B"),
                (CUR_SIN_TIT, G_PRIM5, COL_A, ANO_A, "C"),
                (CUR_DOS_TIT, G_PRIM5, COL_A, ANO_A, "D"),
                (CUR_B, 99, COL_B, ANO_B, "A")):
            d.add(M.Curso(id=cid, colegio_id=col, nombre=nom, grado_id=gid,
                          ano_escolar_id=ano, activo=True))
        for aid, nom, col in ((LENGUA, "Lengua Española", COL_A),
                              (MATE, "Matemática", COL_A),
                              (NAT, "Ciencias Naturales", COL_A),
                              (INGLES, "Inglés", COL_A),
                              (EF, "Educación Física", COL_A),
                              (ART, "Educación Artística", COL_A),
                              (MAT_B, "Matemática", COL_B)):
            d.add(M.Asignatura(id=aid, colegio_id=col, nombre=nom, codigo=str(aid),
                               area="X", area_curricular_codigo="XX", activo=True))
        for uid, col, un, rol in ((ROSA, COL_A, "rosa", "profesor"),
                                  (LUIS, COL_A, "luis", "profesor"),
                                  (PEDRO, COL_A, "pedro", "profesor"),
                                  (CARLA, COL_A, "carla", "profesor"),
                                  (AJENO, COL_A, "ajeno", "profesor"),
                                  (OTRA_TIT, COL_A, "otratit", "profesor"),
                                  (DIR, COL_A, "dir", "direccion"),
                                  (COORD, COL_A, "coord", "coordinador"),
                                  (DIR_B, COL_B, "dirb", "direccion")):
            u = M.Usuario(id=uid, colegio_id=col, username=un, nombre=un,
                          apellido="T", role=rol, activo=True)
            u.set_password(PWD)
            d.add(u)

        n = [300]

        def AP(prof, cur, asig, titular=False, col=COL_A, ano=ANO_A, activo=True):
            n[0] += 1
            d.add(M.AsignacionProfesor(id=n[0], colegio_id=col, profesor_id=prof,
                                       curso_id=cur, asignatura_id=asig,
                                       ano_escolar_id=ano, activo=activo,
                                       es_titular=titular))

        # 5to A: Rosa titular con TRES filas es_titular -> UN solo titular
        AP(ROSA, CUR_5A, LENGUA, titular=True)
        AP(ROSA, CUR_5A, MATE, titular=True)
        AP(ROSA, CUR_5A, NAT, titular=True)
        AP(LUIS, CUR_5A, INGLES)
        AP(PEDRO, CUR_5A, EF)
        AP(CARLA, CUR_5A, ART)
        # AJENO no tiene nada en 5to A, pero sí en otro curso
        AP(AJENO, CUR_1A, LENGUA, titular=True)
        # 1ro A: Rosa NO está; Luis da el Inglés interno de primer ciclo
        AP(LUIS, CUR_1A, INGLES)
        # cursos límite
        AP(PEDRO, CUR_SIN_TIT, EF)                      # sin ningún titular
        AP(ROSA, CUR_DOS_TIT, LENGUA, titular=True)     # dos titulares distintos
        AP(OTRA_TIT, CUR_DOS_TIT, MATE, titular=True)
        # SECUNDARIA: Luis es multinivel
        AP(LUIS, CUR_SEC1, INGLES)
        AP(LUIS, CUR_SEC2, INGLES)
        AP(ROSA, CUR_SEC1, LENGUA)
        AP(DIR_B, CUR_B, MAT_B, titular=True, col=COL_B, ano=ANO_B)

        for eid, cur, col, nom in ((E_5A, CUR_5A, COL_A, "Ana"),
                                   (E_5A_2, CUR_5A, COL_A, "Beto"),
                                   (E_1A, CUR_1A, COL_A, "Cora"),
                                   (E_SEC, CUR_SEC1, COL_A, "Dani"),
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


def marcar(hdr, est, curso, estado="presente", fecha=FECHA, **extra):
    cuerpo = {"estudiante_id": est, "curso_id": curso, "fecha": fecha,
              "estado": estado}
    cuerpo.update(extra)
    return client.post("/api/asistencia", headers=hdr, json=cuerpo)


def leer_curso(hdr, curso, fecha=FECHA, **params):
    q = f"/api/asistencia/curso/{curso}?fecha={fecha}"
    for k, v in params.items():
        q += f"&{k}={v}"
    return client.get(q, headers=hdr)


def _filas(est=None, fecha=None):
    d = SessionLocal()
    try:
        q = d.query(M.Asistencia)
        if est is not None:
            q = q.filter_by(estudiante_id=est)
        if fecha is not None:
            q = q.filter_by(fecha=date.fromisoformat(fecha))
        return [{'id': a.id, 'estado': a.estado, 'asignatura_id': a.asignatura_id,
                 'curso_id': a.curso_id, 'registrado_por': a.registrado_por}
                for a in q.order_by(M.Asistencia.id).all()]
    finally:
        d.close()


_seed()
H_ROSA, H_LUIS, H_PEDRO = _tok("rosa"), _tok("luis"), _tok("pedro")
H_CARLA, H_AJENO = _tok("carla"), _tok("ajeno")
H_DIR, H_COORD, H_DIRB = _tok("dir"), _tok("coord"), _tok("dirb")


# ==========================================================================
# A — ESCRITURA: SOLO EL TITULAR
# ==========================================================================
@test("A1 Rosa, titular, registra la asistencia diaria de 5to A")
def _():
    _seed()
    r = marcar(H_ROSA, E_5A, CUR_5A, "presente")
    assert r.status_code == 200, (r.status_code, r.text[:250])
    f = _filas(E_5A, FECHA)
    assert len(f) == 1 and f[0]["estado"] == "presente", f
    assert f[0]["asignatura_id"] is None, "la asistencia de primaria no lleva materia"


@test("A2 el especialista de Inglés NO puede modificarla")
def _():
    _seed()
    assert marcar(H_ROSA, E_5A, CUR_5A, "presente").status_code == 200
    r = marcar(H_LUIS, E_5A, CUR_5A, "ausente")
    assert r.status_code == 403, (r.status_code, r.text[:250])
    assert "titular" in r.json()["error"].lower()
    f = _filas(E_5A, FECHA)
    assert len(f) == 1 and f[0]["estado"] == "presente", ("sobrescribio al titular", f)


@test("A3 Educación Física y Artística tampoco")
def _():
    _seed()
    for hdr, quien in ((H_PEDRO, "educacion fisica"), (H_CARLA, "artistica")):
        r = marcar(hdr, E_5A, CUR_5A, "ausente")
        assert r.status_code == 403, (quien, r.status_code, r.text[:200])
    assert _filas(E_5A, FECHA) == [], "alguien escribio"


@test("A4 un profesor sin asignación en 5to A no llega ni al guard de titular")
def _():
    _seed()
    r = marcar(H_AJENO, E_5A, CUR_5A, "presente")
    assert r.status_code == 403, (r.status_code, r.text[:250])
    assert "asignados" in r.json()["error"], r.json()["error"]
    assert _filas(E_5A, FECHA) == []


@test("A5 curso SIN titular -> 409, y NO cae al primer profesor activo")
def _():
    _seed()
    d = SessionLocal()
    try:
        d.add(M.Estudiante(id=80, colegio_id=COL_A, nombre="Sin", apellido="Tit",
                           curso_id=CUR_SIN_TIT, activo=True, no_lista=1))
        d.commit()
    finally:
        d.close()
    r = marcar(H_PEDRO, 80, CUR_SIN_TIT, "presente")
    assert r.status_code == 409, (r.status_code, r.text[:250])
    assert "titular" in r.json()["error"].lower()
    assert _filas(80, FECHA) == [], "escribio pese a no haber titular"


@test("A6 curso con DOS titulares distintos -> 409, sin elegir ninguno")
def _():
    _seed()
    d = SessionLocal()
    try:
        d.add(M.Estudiante(id=81, colegio_id=COL_A, nombre="Dos", apellido="Tit",
                           curso_id=CUR_DOS_TIT, activo=True, no_lista=1))
        d.commit()
    finally:
        d.close()
    r = marcar(H_ROSA, 81, CUR_DOS_TIT, "presente")
    assert r.status_code == 409, (r.status_code, r.text[:250])
    assert "inconsistente" in r.json()["error"].lower()
    assert _filas(81, FECHA) == []


@test("A7 VARIAS filas es_titular del MISMO profesor = UN titular válido")
def _():
    _seed()
    # Rosa tiene 3 filas es_titular en 5to A. Si se contaran filas en vez de
    # profesores, seria "titularidad inconsistente" y el grado entero quedaria
    # bloqueado.
    d = SessionLocal()
    try:
        n = d.query(M.AsignacionProfesor).filter_by(
            curso_id=CUR_5A, es_titular=True, activo=True).count()
        assert n == 3, n
    finally:
        d.close()
    assert marcar(H_ROSA, E_5A, CUR_5A, "presente").status_code == 200


@test("A8 titular con UNA sola materia también manda en la asistencia")
def _():
    _seed()
    d = SessionLocal()
    try:   # Rosa se queda solo con Lengua, pero sigue siendo la titular
        d.query(M.AsignacionProfesor).filter_by(
            curso_id=CUR_5A, profesor_id=ROSA).filter(
            M.AsignacionProfesor.asignatura_id != LENGUA).update(
            {"activo": False}, synchronize_session=False)
        d.commit()
    finally:
        d.close()
    assert marcar(H_ROSA, E_5A, CUR_5A, "presente").status_code == 200
    assert marcar(H_LUIS, E_5A, CUR_5A, "ausente").status_code == 403


@test("A9 cambio permanente de titular: el nuevo escribe, el anterior ya no")
def _():
    _seed()
    assert marcar(H_ROSA, E_5A, CUR_5A, "presente").status_code == 200
    d = SessionLocal()
    try:   # Dirección mueve la titularidad a Luis
        d.query(M.AsignacionProfesor).filter_by(curso_id=CUR_5A, profesor_id=ROSA)\
            .update({"es_titular": False}, synchronize_session=False)
        d.query(M.AsignacionProfesor).filter_by(curso_id=CUR_5A, profesor_id=LUIS)\
            .update({"es_titular": True}, synchronize_session=False)
        d.commit()
    finally:
        d.close()
    assert marcar(H_LUIS, E_5A, CUR_5A, "tardanza").status_code == 200
    r = marcar(H_ROSA, E_5A, CUR_5A, "ausente")
    assert r.status_code == 403, (r.status_code, r.text[:200])
    assert _filas(E_5A, FECHA)[0]["estado"] == "tardanza"


@test("A10 el masivo respeta la misma regla")
def _():
    _seed()
    cuerpo = {"fecha": FECHA, "curso_id": CUR_5A,
              "asistencias": [{"estudiante_id": E_5A, "estado": "presente"},
                              {"estudiante_id": E_5A_2, "estado": "ausente"}]}
    r = client.post("/api/asistencia/masivo", headers=H_LUIS, json=cuerpo)
    assert r.status_code == 403, (r.status_code, r.text[:250])
    assert _filas(fecha=FECHA) == [], "el masivo escribio sin ser titular"
    r = client.post("/api/asistencia/masivo", headers=H_ROSA, json=cuerpo)
    assert r.status_code == 200, (r.status_code, r.text[:250])
    assert len(_filas(fecha=FECHA)) == 2


# ==========================================================================
# B — LECTURA: TODO PROFESOR DEL CURSO, SEA CUAL SEA SU MATERIA
# ==========================================================================
@test("B1 los cuatro profesores del curso VEN la asistencia")
def _():
    _seed()
    assert marcar(H_ROSA, E_5A, CUR_5A, "ausente").status_code == 200
    for hdr, quien in ((H_ROSA, "titular"), (H_LUIS, "ingles"),
                       (H_PEDRO, "ed. fisica"), (H_CARLA, "artistica")):
        r = leer_curso(hdr, CUR_5A)
        assert r.status_code == 200, (quien, r.status_code, r.text[:200])
        filas = r.json().get("asistencias", [])
        fila = [x for x in filas if x["estudiante"]["id"] == E_5A]
        assert fila, (quien, "no devolvio al estudiante", r.text[:250])
        assert fila[0]["asistencia"]["estado"] == "ausente", (quien, fila)


@test("B2 un profesor SIN asignación en el curso no lo ve")
def _():
    _seed()
    r = leer_curso(H_AJENO, CUR_5A)
    assert r.status_code == 403, (r.status_code, r.text[:250])
    assert "asignación" in r.json()["error"].lower()
    # y el suyo sí lo ve
    assert leer_curso(H_AJENO, CUR_1A).status_code == 200


@test("B3 leer NO da permiso para escribir")
def _():
    _seed()
    assert marcar(H_ROSA, E_5A, CUR_5A, "presente").status_code == 200
    assert leer_curso(H_LUIS, CUR_5A).status_code == 200
    assert marcar(H_LUIS, E_5A, CUR_5A, "ausente").status_code == 403
    assert _filas(E_5A, FECHA)[0]["estado"] == "presente"


@test("B4 Dirección y coordinación conservan la visibilidad que ya tenían")
def _():
    _seed()
    for hdr, quien in ((H_DIR, "direccion"), (H_COORD, "coordinador")):
        assert leer_curso(hdr, CUR_5A).status_code == 200, quien
    # y siguen SIN poder escribir, como antes de esta fase
    for hdr, quien in ((H_DIR, "direccion"), (H_COORD, "coordinador")):
        r = marcar(hdr, E_5A, CUR_5A, "presente")
        assert r.status_code == 403, (quien, r.status_code, r.text[:200])
        assert "profesores" in r.json()["error"], quien


@test("B5 el aislamiento entre colegios no se toca")
def _():
    _seed()
    assert leer_curso(H_DIRB, CUR_5A).status_code == 404
    assert marcar(H_DIRB, E_5A, CUR_5A).status_code in (403, 404)


@test("R  el repo no fue tocado: sge.db intacto")
def _():
    a = os.path.getmtime(_REPO_SGE) if os.path.exists(_REPO_SGE) else None
    assert a == _sge_mtime, "sge.db fue modificado"


print("\n" + "=" * 70)
print(f"{B}PRIMARIA — ASISTENCIA Y TITULARIDAD: {_ok}/{_total} pruebas{X}")
if _fail:
    print(f"{R}FALLARON:{X}")
    for n, e in _fail:
        print(f"  - {n}: {e}")
    sys.exit(1)
print(f"{G}TODO VERDE{X}")
