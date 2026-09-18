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


# ==========================================================================
# C — PRIMARIA NO LLEVA ASIGNATURA · SECUNDARIA SÍ
# ==========================================================================
@test("C1 en Primaria se RECHAZA asignatura_id, no se ignora")
def _():
    _seed()
    r = marcar(H_ROSA, E_5A, CUR_5A, "presente", asignatura_id=LENGUA)
    assert r.status_code == 400, (r.status_code, r.text[:250])
    assert "no lleva asignatura" in r.json()["error"]
    assert _filas(E_5A, FECHA) == [], "creo la fila igualmente"


@test("C2 sin asignatura, la asistencia de Primaria entra con normalidad")
def _():
    _seed()
    assert marcar(H_ROSA, E_5A, CUR_5A, "presente").status_code == 200
    assert _filas(E_5A, FECHA)[0]["asignatura_id"] is None


@test("C3 así no puede existir una SEGUNDA asistencia oficial el mismo día")
def _():
    _seed()
    assert marcar(H_ROSA, E_5A, CUR_5A, "presente").status_code == 200
    # el de Inglés intenta la suya "por su materia": rechazada dos veces, por
    # no ser titular y por llevar asignatura
    r = marcar(H_LUIS, E_5A, CUR_5A, "ausente", asignatura_id=INGLES)
    assert r.status_code in (400, 403), (r.status_code, r.text[:250])
    f = _filas(E_5A, FECHA)
    assert len(f) == 1 and f[0]["estado"] == "presente", f


@test("C4 en SECUNDARIA la asignatura sigue siendo obligatoria")
def _():
    _seed()
    r = marcar(H_LUIS, E_SEC, CUR_SEC1, "presente")
    assert r.status_code == 400, (r.status_code, r.text[:250])
    assert "Secundaria" in r.json()["error"]


# ==========================================================================
# D — EL AUTOR ES QUIEN DEJÓ EL ESTADO ACTUAL
# ==========================================================================
@test("D1 al corregirse a sí mismo, el titular sigue siendo el autor")
def _():
    _seed()
    assert marcar(H_ROSA, E_5A, CUR_5A, "presente").status_code == 200
    assert _filas(E_5A, FECHA)[0]["registrado_por"] == ROSA
    assert marcar(H_ROSA, E_5A, CUR_5A, "ausente").status_code == 200
    f = _filas(E_5A, FECHA)
    assert len(f) == 1 and f[0]["estado"] == "ausente"
    assert f[0]["registrado_por"] == ROSA


@test("D2 tras un cambio de titular, el autor pasa a ser el nuevo")
def _():
    _seed()
    assert marcar(H_ROSA, E_5A, CUR_5A, "presente").status_code == 200
    d = SessionLocal()
    try:
        d.query(M.AsignacionProfesor).filter_by(curso_id=CUR_5A, profesor_id=ROSA)\
            .update({"es_titular": False}, synchronize_session=False)
        d.query(M.AsignacionProfesor).filter_by(curso_id=CUR_5A, profesor_id=LUIS)\
            .update({"es_titular": True}, synchronize_session=False)
        d.commit()
    finally:
        d.close()
    assert marcar(H_LUIS, E_5A, CUR_5A, "excusa").status_code == 200
    f = _filas(E_5A, FECHA)
    assert len(f) == 1, ("se creo una fila nueva en vez de actualizar", f)
    assert f[0]["estado"] == "excusa" and f[0]["registrado_por"] == LUIS, f


@test("D3 el masivo también actualiza el autor")
def _():
    _seed()
    assert marcar(H_ROSA, E_5A, CUR_5A, "presente").status_code == 200
    d = SessionLocal()
    try:
        d.query(M.AsignacionProfesor).filter_by(curso_id=CUR_5A, profesor_id=ROSA)\
            .update({"es_titular": False}, synchronize_session=False)
        d.query(M.AsignacionProfesor).filter_by(curso_id=CUR_5A, profesor_id=LUIS)\
            .update({"es_titular": True}, synchronize_session=False)
        d.commit()
    finally:
        d.close()
    r = client.post("/api/asistencia/masivo", headers=H_LUIS, json={
        "fecha": FECHA, "curso_id": CUR_5A,
        "asistencias": [{"estudiante_id": E_5A, "estado": "ausente"}]})
    assert r.status_code == 200, (r.status_code, r.text[:250])
    f = _filas(E_5A, FECHA)
    assert len(f) == 1 and f[0]["registrado_por"] == LUIS, f


# ==========================================================================
# E — UNICIDAD DE LA ASISTENCIA GENERAL
# ==========================================================================
@test("E1 el índice parcial existe en una base creada con create_all()")
def _():
    # Esta DB temporal se creo con Base.metadata.create_all(). Antes el indice
    # solo lo creaba app.py al arrancar, asi que una base nueva se quedaba sin
    # la garantia que si tiene produccion.
    from sqlalchemy import inspect as _inspect
    idx = _inspect(engine).get_indexes('asistencias')
    nombres = {i['name'] for i in idx}
    assert 'uq_asistencia_general_est_fecha' in nombres, sorted(nombres)
    el = [i for i in idx if i['name'] == 'uq_asistencia_general_est_fecha'][0]
    assert el.get('unique'), el
    assert list(el['column_names']) == ['estudiante_id', 'fecha'], el


@test("E2 un segundo POST legítimo ACTUALIZA, no inserta otra fila")
def _():
    _seed()
    assert marcar(H_ROSA, E_5A, CUR_5A, "presente").status_code == 200
    assert marcar(H_ROSA, E_5A, CUR_5A, "ausente").status_code == 200
    assert marcar(H_ROSA, E_5A, CUR_5A, "tardanza").status_code == 200
    f = _filas(E_5A, FECHA)
    assert len(f) == 1, ("se insertaron filas de mas", f)
    assert f[0]["estado"] == "tardanza" and f[0]["asignatura_id"] is None


@test("E3 la base RECHAZA a nivel de índice una segunda asistencia general")
def _():
    _seed()
    assert marcar(H_ROSA, E_5A, CUR_5A, "presente").status_code == 200
    d = SessionLocal()
    try:   # salteandose el endpoint, directo contra la tabla
        d.add(M.Asistencia(colegio_id=COL_A, estudiante_id=E_5A, curso_id=CUR_5A,
                           asignatura_id=None, fecha=date.fromisoformat(FECHA),
                           estado="ausente", registrado_por=LUIS))
        try:
            d.commit()
            raise AssertionError("la base acepto una segunda asistencia general")
        except AssertionError:
            raise
        except Exception:
            d.rollback()   # lo esperado: el indice lo impide
    finally:
        d.close()
    assert len(_filas(E_5A, FECHA)) == 1


@test("E4 en SECUNDARIA el mismo día con materias distintas SÍ convive")
def _():
    _seed()
    r1 = marcar(H_LUIS, E_SEC, CUR_SEC1, "presente", asignatura_id=INGLES)
    assert r1.status_code == 200, (r1.status_code, r1.text[:250])
    r2 = marcar(H_ROSA, E_SEC, CUR_SEC1, "ausente", asignatura_id=LENGUA)
    assert r2.status_code == 200, (r2.status_code, r2.text[:250])
    f = _filas(E_SEC, FECHA)
    assert len(f) == 2, ("secundaria perdio una de sus dos marcas", f)
    assert {x["asignatura_id"] for x in f} == {INGLES, LENGUA}, f


# ==========================================================================
# F — EL SERVIDOR DICE SI SE PUEDE EDITAR
#   La pantalla no deduce la titularidad: la lee de aqui.
# ==========================================================================
@test("F1 al titular se le responde puede_editar = true")
def _():
    _seed()
    r = leer_curso(H_ROSA, CUR_5A)
    assert r.status_code == 200
    assert r.json()["puede_editar"] is True, r.json()
    assert r.json()["motivo_solo_lectura"] is None


@test("F2 al profesor del curso que no es titular, false y el motivo")
def _():
    _seed()
    for hdr, quien in ((H_LUIS, "ingles"), (H_PEDRO, "ef"), (H_CARLA, "arte")):
        c = leer_curso(hdr, CUR_5A).json()
        assert c["puede_editar"] is False, (quien, c)
        assert c["motivo_solo_lectura"] == "no_titular", (quien, c)


@test("F3 curso sin titular y con dos titulares: motivos distintos")
def _():
    _seed()
    c = leer_curso(H_PEDRO, CUR_SIN_TIT).json()
    assert c["puede_editar"] is False and c["motivo_solo_lectura"] == "sin_titular", c
    c = leer_curso(H_ROSA, CUR_DOS_TIT).json()
    assert c["puede_editar"] is False, c
    assert c["motivo_solo_lectura"] == "titularidad_inconsistente", c


@test("F4 Dirección y coordinación: false con motivo 'solo_profesor'")
def _():
    _seed()
    for hdr, quien in ((H_DIR, "direccion"), (H_COORD, "coordinador")):
        c = leer_curso(hdr, CUR_5A).json()
        assert c["puede_editar"] is False, (quien, c)
        assert c["motivo_solo_lectura"] == "solo_profesor", (quien, c)


@test("F5 en SECUNDARIA no se insinúa una regla que allí no existe")
def _():
    _seed()
    c = leer_curso(H_LUIS, CUR_SEC1, asignatura_id=INGLES).json()
    assert c["puede_editar"] is None, c
    assert c["motivo_solo_lectura"] is None, c
    # y sigue pudiendo escribir por su via
    assert marcar(H_LUIS, E_SEC, CUR_SEC1, "presente",
                  asignatura_id=INGLES).status_code == 200


@test("F6 el servidor y el endpoint de escritura dicen lo mismo")
def _():
    _seed()
    for hdr, est, curso in ((H_ROSA, E_5A, CUR_5A), (H_LUIS, E_5A, CUR_5A),
                            (H_PEDRO, E_5A, CUR_5A), (H_CARLA, E_5A, CUR_5A)):
        anuncia = leer_curso(hdr, curso).json()["puede_editar"]
        escribe = marcar(hdr, est, curso, "presente").status_code == 200
        assert anuncia == escribe, (
            "la pantalla anuncia %s pero la escritura da %s" % (anuncia, escribe))


# ==========================================================================
# G — LAS TRES RESPONSABILIDADES NO SE MEZCLAN
#   asistencia -> curso/dia -> titular
#   calificaciones -> asignatura -> quien la tiene asignada
#   recuperacion -> asignatura -> igual, sin cambios
# ==========================================================================
def calificar(hdr, est, asig, comp=1, **campos):
    cuerpo = {"estudiante_id": est, "asignatura_id": asig, "competencia_numero": comp}
    cuerpo.update(campos)
    return client.post("/api/calificaciones-primaria", headers=hdr, json=cuerpo)


def recuperar(hdr, est, asig, **campos):
    cuerpo = {"estudiante_id": est, "asignatura_id": asig}
    cuerpo.update(campos)
    return client.post("/api/recuperaciones-primaria", headers=hdr, json=cuerpo)


@test("G1 Rosa, titular, califica SUS materias")
def _():
    _seed()
    for asig in (LENGUA, MATE, NAT):
        r = calificar(H_ROSA, E_5A, asig, p1=80)
        assert r.status_code == 200, (asig, r.status_code, r.text[:200])


@test("G2 ser titular NO da derecho a calificar Inglés")
def _():
    _seed()
    r = calificar(H_ROSA, E_5A, INGLES, p1=80)
    assert r.status_code == 403, (r.status_code, r.text[:250])
    assert "asignada" in r.json()["error"].lower()


@test("G3 Luis califica Inglés, pero no Matemática")
def _():
    _seed()
    assert calificar(H_LUIS, E_5A, INGLES, p1=90).status_code == 200
    r = calificar(H_LUIS, E_5A, MATE, p1=90)
    assert r.status_code == 403, (r.status_code, r.text[:250])


@test("G4 ver la asistencia no altera NINGÚN permiso de calificaciones")
def _():
    _seed()
    assert leer_curso(H_PEDRO, CUR_5A).status_code == 200      # Pedro ve
    r = calificar(H_PEDRO, E_5A, LENGUA, p1=80)                # pero no califica
    assert r.status_code == 403, (r.status_code, r.text[:200])
    r = calificar(H_PEDRO, E_5A, EF, p1=80)                    # lo suyo sí
    assert r.status_code == 200, (r.status_code, r.text[:250])


@test("G5 la recuperación sigue atada a la asignatura, no a la titularidad")
def _():
    _seed()
    # Rosa NO tiene Inglés: no puede tocar su recuperación aunque sea titular
    r = recuperar(H_ROSA, E_5A, INGLES, tipo='final', puntos=5)
    assert r.status_code == 403, (r.status_code, r.text[:250])
    assert "asignada" in r.json()["error"].lower()
    # Luis, que sí la tiene, entra por su vía (el 400/409 posterior es de la
    # regla academica, no del permiso)
    r = recuperar(H_LUIS, E_5A, INGLES, tipo='final', puntos=5)
    assert r.status_code != 403, (r.status_code, r.text[:250])


@test("G6 ver la asistencia tampoco concede recuperación")
def _():
    _seed()
    assert leer_curso(H_LUIS, CUR_5A).status_code == 200
    r = recuperar(H_LUIS, E_5A, MATE, tipo='final', puntos=5)
    assert r.status_code == 403, (r.status_code, r.text[:250])


# ==========================================================================
# H — PROFESOR MULTINIVEL
# ==========================================================================
@test("H1 Luis: ve la asistencia de 5to Primaria, NO la modifica, y califica Inglés")
def _():
    _seed()
    assert leer_curso(H_LUIS, CUR_5A).status_code == 200
    assert marcar(H_LUIS, E_5A, CUR_5A, "ausente").status_code == 403
    assert calificar(H_LUIS, E_5A, INGLES, p1=88).status_code == 200


@test("H2 el mismo Luis pasa asistencia en SUS cursos de Secundaria, sin titularidad")
def _():
    _seed()
    for cur in (CUR_SEC1, CUR_SEC2):
        d = SessionLocal()
        try:
            n = d.query(M.AsignacionProfesor).filter_by(
                curso_id=cur, es_titular=True, activo=True).count()
            assert n == 0, ("el fixture de secundaria no debe tener titulares", cur)
        finally:
            d.close()
    r = marcar(H_LUIS, E_SEC, CUR_SEC1, "presente", asignatura_id=INGLES)
    assert r.status_code == 200, (r.status_code, r.text[:250])


@test("H3 la titularidad NO interviene en Secundaria")
def _():
    _seed()
    # Rosa da Lengua en 1ro Secundaria y no es titular de nada allí: escribe igual
    r = marcar(H_ROSA, E_SEC, CUR_SEC1, "ausente", asignatura_id=LENGUA)
    assert r.status_code == 200, (r.status_code, r.text[:250])


@test("H4 el Inglés interno de 1ro–3ro: Luis lo da, lo ve, y no pasa lista")
def _():
    _seed()
    # 1ro A es primer ciclo; Luis tiene el Inglés interno, AJENO es el titular
    assert leer_curso(H_LUIS, CUR_1A).status_code == 200
    r = marcar(H_LUIS, E_1A, CUR_1A, "presente")
    assert r.status_code == 403, (r.status_code, r.text[:250])
    assert marcar(H_AJENO, E_1A, CUR_1A, "presente").status_code == 200
    # y sus notas internas de Inglés se guardan con normalidad
    assert calificar(H_LUIS, E_1A, INGLES, p1=85).status_code == 200


# ==========================================================================
# I — ESTUDIANTE RETIRADO Y MULTI-TENANT
# ==========================================================================
@test("I1 un estudiante retirado sigue protegido")
def _():
    _seed()
    d = SessionLocal()
    try:
        d.query(M.Estudiante).filter_by(id=E_5A).update(
            {"activo": False, "fecha_retiro": date(2026, 9, 1)})
        d.commit()
    finally:
        d.close()
    r = marcar(H_ROSA, E_5A, CUR_5A, "presente")
    assert r.status_code == 403, (r.status_code, r.text[:250])
    assert calificar(H_ROSA, E_5A, LENGUA, p1=80).status_code == 403
    assert _filas(E_5A, FECHA) == []


@test("I2 ninguna autorización cruza de colegio")
def _():
    _seed()
    assert marcar(H_ROSA, E_B, CUR_B, "presente").status_code == 404
    assert leer_curso(H_ROSA, CUR_B).status_code == 404
    assert calificar(H_ROSA, E_B, MAT_B, p1=80).status_code == 404
    assert marcar(H_DIRB, E_5A, CUR_5A).status_code in (403, 404)


@test("I3 el guard de asistencia NO consulta Horario ni una vez")
def _():
    import inspect
    for fn in (APP._guard_asistencia, APP._guard_titular_primaria,
               APP._titulares_del_curso, APP._respuesta_asistencia_curso):
        fuente = inspect.getsource(fn)
        assert "Horario" not in fuente, (fn.__name__, "consulta el horario")
        assert "nivel_asignado" not in fuente, (fn.__name__, "usa nivel_asignado")


# ==========================================================================
# J — EL ALCANCE DE LECTURA ES SOLO DE PRIMARIA
#   La primera version del guard corria para TODOS los cursos y con eso
#   cambiaba la politica de lectura de Secundaria, que en esta fase tiene que
#   quedar intacta. Estos casos lo fijan.
# ==========================================================================
@test("J1 SECUNDARIA: un profesor SIN asignación en el curso lee igual que en la base")
def _():
    _seed()
    # En fc44ada el endpoint no tenia NINGUN control de alcance: cualquier
    # usuario autenticado del colegio recibia 200. Ese es el comportamiento que
    # P3.1 debe conservar, guste o no — cambiarlo es otra fase.
    BASE_SECUNDARIA = 200
    r = leer_curso(H_PEDRO, CUR_SEC1, asignatura_id=INGLES)
    assert r.status_code == BASE_SECUNDARIA, (
        "P3.1 cambio la politica de LECTURA de Secundaria: la base daba %s y ahora da %s"
        % (BASE_SECUNDARIA, r.status_code))
    # y Carla, que tampoco tiene nada en Secundaria
    assert leer_curso(H_CARLA, CUR_SEC2, asignatura_id=INGLES).status_code == BASE_SECUNDARIA


@test("J2 SECUNDARIA: el profesor asignado sigue igual, y su flujo completo también")
def _():
    _seed()
    assert leer_curso(H_LUIS, CUR_SEC1, asignatura_id=INGLES).status_code == 200
    # asistencia por materia
    assert marcar(H_LUIS, E_SEC, CUR_SEC1, "presente",
                  asignatura_id=INGLES).status_code == 200
    # varias materias el mismo dia
    assert marcar(H_ROSA, E_SEC, CUR_SEC1, "ausente",
                  asignatura_id=LENGUA).status_code == 200
    f = _filas(E_SEC, FECHA)
    assert len(f) == 2 and {x["asignatura_id"] for x in f} == {INGLES, LENGUA}, f
    # y la asignatura sigue siendo obligatoria
    assert marcar(H_LUIS, E_SEC, CUR_SEC1, "presente").status_code == 400


@test("J3 PRIMARIA: el profesor del curso lee, el ajeno no")
def _():
    _seed()
    for hdr, quien in ((H_ROSA, "titular"), (H_LUIS, "ingles"),
                       (H_PEDRO, "ed. fisica"), (H_CARLA, "artistica")):
        assert leer_curso(hdr, CUR_5A).status_code == 200, quien
    r = leer_curso(H_AJENO, CUR_5A)
    assert r.status_code == 403, (r.status_code, r.text[:250])


@test("J4 el MISMO profesor: 403 en el curso de Primaria ajeno, 200 en el de Secundaria")
def _():
    _seed()
    # Pedro no tiene nada ni en 1ro Primaria ni en 1ro Secundaria. La diferencia
    # de respuesta prueba que el guard depende del NIVEL DEL CURSO y no del
    # profesor: si corriera para todo, las dos darian 403.
    assert leer_curso(H_PEDRO, CUR_1A).status_code == 403, "primaria ajena deberia cerrarse"
    assert leer_curso(H_PEDRO, CUR_SEC1, asignatura_id=INGLES).status_code == 200, \
        "secundaria no debe verse afectada"


@test("J5 el nivel se resuelve por Curso -> Grado -> nivel, no por el usuario")
def _():
    import inspect

    def solo_codigo(fn):
        """Solo el CODIGO de la funcion: sin comentarios ni docstring.

        Buscar en la prosa da falsos positivos — el propio comentario que
        explica "nunca por nivel_asignado" contiene esa palabra.
        """
        import ast
        import textwrap
        arbol = ast.parse(textwrap.dedent(inspect.getsource(fn)))
        cuerpo = arbol.body[0]
        if (cuerpo.body and isinstance(cuerpo.body[0], ast.Expr)
                and isinstance(cuerpo.body[0].value, ast.Constant)
                and isinstance(cuerpo.body[0].value.value, str)):
            cuerpo.body = cuerpo.body[1:]      # fuera el docstring
        return ast.unparse(arbol)              # unparse ya descarta comentarios

    # El endpoint delega en el guard...
    codigo = solo_codigo(APP.get_asistencia_curso)
    assert "_guard_lectura_asistencia_primaria(db, curso, current_user)" in codigo, (
        "el endpoint no delega en el guard de lectura")
    assert "nivel_asignado" not in codigo, "usa nivel_asignado como autoridad"
    assert "Horario" not in codigo, "consulta el horario"

    # ...y el guard acota por el NIVEL DEL CURSO, resuelto via grado.
    guard = solo_codigo(APP._guard_lectura_asistencia_primaria)
    assert "_es_curso_primaria(db, curso.id)" in guard, (
        "el guard no acota por nivel del curso")
    assert "nivel_asignado" not in guard, "el guard usa nivel_asignado"
    assert "Horario" not in guard, "el guard consulta el horario"
    assert "grado.nivel" in solo_codigo(APP._es_curso_primaria)


# ==========================================================================
# K — LAS TRES RUTAS DE LECTURA, CON LA MISMA REGLA
#   Cerrar solo una dejaba puertas laterales: `/api/asistencia` unicamente
#   comprobaba la asignacion cuando venia `asignatura_id` —que en Primaria no
#   viene nunca— y `resumen` no comprobaba nada.
# ==========================================================================
def _rutas_lectura(curso, fecha=FECHA):
    return {
        'GET /api/asistencia': f"/api/asistencia?curso_id={curso}&fecha={fecha}",
        'GET /api/asistencia/curso/{id}': f"/api/asistencia/curso/{curso}?fecha={fecha}",
        'GET /api/asistencia/resumen/{id}': f"/api/asistencia/resumen/{curso}?mes=9&ano=2026",
    }


def _status_rutas(hdr, curso):
    return {n: client.get(u, headers=hdr).status_code
            for n, u in _rutas_lectura(curso).items()}


@test("K1 PRIMARIA: el titular lee por las TRES rutas")
def _():
    _seed()
    st = _status_rutas(H_ROSA, CUR_5A)
    assert set(st.values()) == {200}, st


@test("K2 PRIMARIA: el profesor del curso NO titular lee por las tres")
def _():
    _seed()
    for hdr, quien in ((H_LUIS, "ingles"), (H_PEDRO, "ed. fisica"), (H_CARLA, "arte")):
        st = _status_rutas(hdr, CUR_5A)
        assert set(st.values()) == {200}, (quien, st)


@test("K3 PRIMARIA: el profesor AJENO recibe 403 en las tres")
def _():
    _seed()
    st = _status_rutas(H_AJENO, CUR_5A)
    assert set(st.values()) == {403}, ("queda una puerta lateral abierta", st)


@test("K4 PRIMARIA: Dirección y coordinación leen por las tres, como antes")
def _():
    _seed()
    for hdr, quien in ((H_DIR, "direccion"), (H_COORD, "coordinador")):
        st = _status_rutas(hdr, CUR_5A)
        assert set(st.values()) == {200}, (quien, st)


@test("K5 otro colegio: bloqueado en las tres")
def _():
    _seed()
    st = _status_rutas(H_DIRB, CUR_5A)
    assert set(st.values()) == {404}, st


@test("K6 SECUNDARIA: las tres rutas dan lo MISMO que en la base fc44ada")
def _():
    _seed()
    # En la base ninguna de las tres tenia alcance por curso para Primaria, y en
    # Secundaria `/api/asistencia` solo pedia asignacion cuando venia
    # asignatura_id. Sin asignatura_id, un profesor ajeno leia: 200 en las tres.
    BASE = {'GET /api/asistencia': 200,
            'GET /api/asistencia/curso/{id}': 200,
            'GET /api/asistencia/resumen/{id}': 200}
    for hdr, quien in ((H_PEDRO, "sin nada en secundaria"),
                       (H_CARLA, "tampoco")):
        st = _status_rutas(hdr, CUR_SEC1)
        assert st == BASE, (
            "P3.1 cambio la lectura de Secundaria para %s: base %s, ahora %s"
            % (quien, BASE, st))


@test("K7 SECUNDARIA: con asignatura_id, el chequeo base sigue vivo")
def _():
    _seed()
    # Esta es la unica proteccion que Secundaria ya tenia, y no se toca.
    r = client.get(f"/api/asistencia?curso_id={CUR_SEC1}&fecha={FECHA}"
                   f"&asignatura_id={INGLES}", headers=H_PEDRO)
    assert r.status_code == 403, (r.status_code, r.text[:200])
    r = client.get(f"/api/asistencia?curso_id={CUR_SEC1}&fecha={FECHA}"
                   f"&asignatura_id={INGLES}", headers=H_LUIS)
    assert r.status_code == 200, (r.status_code, r.text[:200])


@test("K8 el guard de lectura vive en UN solo sitio y lo usan las tres rutas")
def _():
    import inspect
    for fn in (APP.get_asistencia, APP.get_asistencia_curso, APP.get_resumen_asistencia):
        fuente = inspect.getsource(fn)
        assert "_guard_lectura_asistencia_primaria(db, curso, current_user)" in fuente, \
            fn.__name__
    g = inspect.getsource(APP._guard_lectura_asistencia_primaria)
    assert "_es_curso_primaria" in g, "no acota por nivel del curso"
    assert "es_titular" not in g, "exige titular para LEER"
    assert "asignatura" not in g.split("\"\"\"")[-1], "exige una asignatura concreta"


# ==========================================================================
# L — DESMARCAR
# ==========================================================================
def desmarcar(hdr, est, fecha=FECHA, **params):
    q = f"/api/asistencia/{est}?fecha={fecha}"
    for k, v in params.items():
        q += f"&{k}={v}"
    return client.request("DELETE", q, headers=hdr)


@test("L1 PRIMARIA: el titular desmarca; el profesor del curso y el ajeno, no")
def _():
    _seed()
    assert marcar(H_ROSA, E_5A, CUR_5A, "presente").status_code == 200
    for hdr, quien in ((H_LUIS, "ingles"), (H_PEDRO, "ed. fisica"),
                       (H_CARLA, "arte")):
        r = desmarcar(hdr, E_5A)
        assert r.status_code == 403, (quien, r.status_code, r.text[:200])
        assert len(_filas(E_5A, FECHA)) == 1, (quien, "borro la marca")
    r = desmarcar(H_AJENO, E_5A)
    assert r.status_code == 403, (r.status_code, r.text[:200])
    # el titular sí
    r = desmarcar(H_ROSA, E_5A)
    assert r.status_code == 200, (r.status_code, r.text[:250])
    assert _filas(E_5A, FECHA) == []


@test("L2 SECUNDARIA: desmarcar sigue igual, sin titularidad de por medio")
def _():
    _seed()
    assert marcar(H_LUIS, E_SEC, CUR_SEC1, "presente",
                  asignatura_id=INGLES).status_code == 200
    r = desmarcar(H_LUIS, E_SEC, asignatura_id=INGLES)
    assert r.status_code == 200, (r.status_code, r.text[:250])
    assert _filas(E_SEC, FECHA) == []


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
