# -*- coding: utf-8 -*-
"""
EducaOne S1 — SESION NO IMPARTIDA (backend).

QUE SE AGREGA
    El profesor puede declarar que una sesion PROGRAMADA no se impartio, con un
    motivo del catalogo. La fecha conserva su columna en el Registro; la sesion
    no cuenta como asistencia de nadie.

LA GRANULARIDAD
    ASIGNATURA + FECHA. "No hubo clase" significa que esa materia no se impartio
    ese dia para ese curso, no que un bloque suelto no se dio. Es la misma
    granularidad de la asistencia de Secundaria y del Registro. Con varios
    bloques el mismo dia —20 de 49 grupos en produccion— no se pregunta cual:
    `horario_id` queda NULL, como procedencia que no existe.

LAS DOS REGLAS QUE ESTA SUITE PROTEGE
    §5  La sesion tiene que existir y ser suya: colegio, profesor, curso,
        asignatura, asignacion activa, nivel, y al menos un bloque de esa materia
        en el dia de la semana de la fecha.
    §7  Exclusividad en AMBAS direcciones. No se declara no impartida una clase
        que ya tiene asistencia, y no se pasa lista de una clase declarada no
        impartida. La salida del conflicto es retirar la justificacion.

Y LA QUE PROTEGE POR OMISION
    §3  `DiaNoLaborable` NO se conecta solo. Un feriado del calendario del centro
        no impide pasar lista ni obliga a justificar nada. Los feriados
        precargados pueden no corresponder con lo que paso de verdad.

Uso:
    cd backend
    python tools/test_sesion_no_impartida_s1.py
"""
import os
import sys
import atexit
import tempfile
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TMPDIR = tempfile.mkdtemp(prefix="eo_s1_")
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
#
# Colegio A, Secundaria. MARTES tiene clase de Matematica (un bloque) y de
# Lengua (DOS bloques, para el caso ambiguo). El curso de Primaria y el colegio
# B existen para medir los limites.
# --------------------------------------------------------------------------
PWD = "Prueba2026x"
COL_A, COL_B = 1, 2
ANO_A, ANO_B = 1, 2
GRA_SEC, GRA_PRI, GRA_B = 1, 2, 99
CUR_SEC, CUR_PRI, CUR_B = 10, 11, 20        # 3ro Sec | 4to Pri | curso del colegio B
MAT, LEN, ING, SOC = 1, 2, 3, 4              # asignaturas del colegio A
MAT_B = 90                                   # asignatura del colegio B
U_PROF, U_PROF2, U_DIR, U_COORD = 31, 32, 34, 35
U_PROF_B = 81
E1, E2, E3 = 50, 51, 52                      # estudiantes de CUR_SEC
E_PRI = 55                                   # estudiante de CUR_PRI
H_MAT, H_LEN_1, H_LEN_2, H_ING = 701, 702, 703, 704
H_SOC_1, H_SOC_2 = 705, 706                  # duplicado EXACTO, como en produccion

# Una fecha pasada y MARTES, para que el bloque programado exista de verdad.
# Se calcula desde hoy para que la suite no caduque.
def _martes_pasado():
    d = date.today() - timedelta(days=7)
    while d.weekday() != 1:                  # 1 = martes
        d -= timedelta(days=1)
    return d


def _lunes_pasado():
    d = _martes_pasado()
    while d.weekday() != 0:
        d -= timedelta(days=1)
    return d


MARTES = _martes_pasado()
LUNES = _lunes_pasado()                      # ningun bloque programado


def _seed():
    M.Base.metadata.drop_all(bind=engine)
    M.Base.metadata.create_all(bind=engine)
    d = SessionLocal()
    try:
        for col, ano, nom in ((COL_A, ANO_A, "A"), (COL_B, ANO_B, "B")):
            d.add(M.Colegio(id=col, nombre="Colegio " + nom, codigo=nom.lower(),
                            plan_primaria=True, plan_secundaria=True))
            d.add(M.AnoEscolar(id=ano, colegio_id=col, nombre="2025-2026",
                               activo=True, dias_trabajados="{}"))
        d.add(M.Grado(id=GRA_SEC, colegio_id=COL_A, nombre="3ro Secundaria",
                      nivel="secundaria", orden=3))
        d.add(M.Grado(id=GRA_PRI, colegio_id=COL_A, nombre="4to Primaria",
                      nivel="primaria", orden=40))
        d.add(M.Grado(id=GRA_B, colegio_id=COL_B, nombre="3ro Secundaria",
                      nivel="secundaria", orden=3))
        d.add(M.Curso(id=CUR_SEC, colegio_id=COL_A, nombre="A", grado_id=GRA_SEC,
                      ano_escolar_id=ANO_A, activo=True))
        d.add(M.Curso(id=CUR_PRI, colegio_id=COL_A, nombre="A", grado_id=GRA_PRI,
                      ano_escolar_id=ANO_A, activo=True))
        d.add(M.Curso(id=CUR_B, colegio_id=COL_B, nombre="A", grado_id=GRA_B,
                      ano_escolar_id=ANO_B, activo=True))
        for aid, nom, cod in ((MAT, "Matematica", "MAT"), (LEN, "Lengua Espanola", "LE"),
                              (ING, "Ingles", "LEI"), (SOC, "Ciencias Sociales", "CS")):
            d.add(M.Asignatura(id=aid, colegio_id=COL_A, nombre=nom, codigo=cod,
                               area="X", area_curricular_codigo=cod, activo=True))
        d.add(M.Asignatura(id=MAT_B, colegio_id=COL_B, nombre="Matematica",
                           codigo="MAT", area="X", area_curricular_codigo="MAT",
                           activo=True))

        for uid, col, un, rol in ((U_PROF, COL_A, "prof", "profesor"),
                                  (U_PROF2, COL_A, "prof2", "profesor"),
                                  (U_DIR, COL_A, "dir", "direccion"),
                                  (U_COORD, COL_A, "coord", "coordinador"),
                                  (U_PROF_B, COL_B, "profb", "profesor")):
            u = M.Usuario(id=uid, colegio_id=col, username=un, nombre=un,
                          apellido="T", role=rol, activo=True)
            u.set_password(PWD)
            d.add(u)

        for eid, cur in ((E1, CUR_SEC), (E2, CUR_SEC), (E3, CUR_SEC), (E_PRI, CUR_PRI)):
            d.add(M.Estudiante(id=eid, colegio_id=COL_A, nombre="Est%d" % eid,
                               apellido="T", curso_id=cur, activo=True,
                               no_lista=eid - 49))

        # asignaciones: PROF da Matematica y Lengua en Secundaria y el curso de
        # Primaria; PROF2 solo da Ingles en el mismo curso de Secundaria.
        for apid, prof, cur, asig in ((100, U_PROF, CUR_SEC, MAT),
                                      (101, U_PROF, CUR_SEC, LEN),
                                      (102, U_PROF2, CUR_SEC, ING),
                                      (104, U_PROF, CUR_SEC, SOC),
                                      (103, U_PROF, CUR_PRI, MAT)):
            d.add(M.AsignacionProfesor(id=apid, colegio_id=COL_A, profesor_id=prof,
                                       curso_id=cur, asignatura_id=asig,
                                       ano_escolar_id=ANO_A, activo=True))
        d.add(M.AsignacionProfesor(id=180, colegio_id=COL_B, profesor_id=U_PROF_B,
                                   curso_id=CUR_B, asignatura_id=MAT_B,
                                   ano_escolar_id=ANO_B, activo=True))

        # horarios: MARTES. Lengua tiene DOS bloques ese dia.
        d.add(M.Horario(id=H_MAT, colegio_id=COL_A, profesor_id=U_PROF,
                        curso_id=CUR_SEC, asignatura_id=MAT, dia="Martes",
                        hora_inicio="08:00", hora_fin="08:45",
                        tipo_bloque="clase", activo=True))
        d.add(M.Horario(id=H_LEN_1, colegio_id=COL_A, profesor_id=U_PROF,
                        curso_id=CUR_SEC, asignatura_id=LEN, dia="Martes",
                        hora_inicio="09:00", hora_fin="09:45",
                        tipo_bloque="clase", activo=True))
        d.add(M.Horario(id=H_LEN_2, colegio_id=COL_A, profesor_id=U_PROF,
                        curso_id=CUR_SEC, asignatura_id=LEN, dia="Martes",
                        hora_inicio="11:00", hora_fin="11:45",
                        tipo_bloque="clase", activo=True))
        # Sociales: DOS filas con la MISMA hora. En produccion hay tres grupos asi
        # (34/35, 55/72, 74/75): preguntar "cual de los dos" no tiene respuesta
        # distinguible, y es el caso que obliga a no preguntar.
        for _hid in (H_SOC_1, H_SOC_2):
            d.add(M.Horario(id=_hid, colegio_id=COL_A, profesor_id=U_PROF,
                            curso_id=CUR_SEC, asignatura_id=SOC, dia="Martes",
                            hora_inicio="13:00", hora_fin="13:45",
                            tipo_bloque="clase", activo=True))
        d.add(M.Horario(id=H_ING, colegio_id=COL_A, profesor_id=U_PROF2,
                        curso_id=CUR_SEC, asignatura_id=ING, dia="Martes",
                        hora_inicio="10:00", hora_fin="10:45",
                        tipo_bloque="clase", activo=True))
        d.commit()
    finally:
        d.close()


def _tok(user, pwd=PWD):
    r = client.post("/api/auth/login", json={"username": user, "password": pwd})
    assert r.status_code == 200, (user, r.status_code, r.text[:200])
    return {"Authorization": "Bearer " + r.json()["token"]}


def _crear(hdr, **kw):
    cuerpo = {"curso_id": CUR_SEC, "asignatura_id": MAT,
              "fecha": MARTES.isoformat(), "motivo_codigo": "SUSP_LLUVIA"}
    cuerpo.update(kw)
    return client.post("/api/sesiones-no-impartidas", json=cuerpo, headers=hdr)


def _sesiones(**filtros):
    d = SessionLocal()
    try:
        return d.query(M.SesionNoImpartida).filter_by(**filtros).all()
    finally:
        d.close()


def _n_sesiones():
    d = SessionLocal()
    try:
        return d.query(M.SesionNoImpartida).count()
    finally:
        d.close()


def _n_asistencias(**filtros):
    d = SessionLocal()
    try:
        return d.query(M.Asistencia).filter_by(**filtros).count()
    finally:
        d.close()


_seed()
H_PROF = _tok("prof")
H_PROF2 = _tok("prof2")
H_DIR = _tok("dir")
H_COORD = _tok("coord")
H_PROF_B = _tok("profb")


# ==========================================================================
# A — CATALOGO
# ==========================================================================
@test("A1 el catalogo expone los siete motivos, con etiqueta corta para el Registro")
def _():
    r = client.get("/api/sesiones-no-impartidas/motivos", headers=H_PROF)
    assert r.status_code == 200, r.text[:200]
    cat = {m["codigo"]: m for m in r.json()}
    assert set(cat) == {"SUSP_LLUVIA", "REUNION", "ACTIVIDAD", "ACTIVIDAD_FUERA",
                        "SUSP_CURSO", "FERIADO", "OTRO"}, sorted(cat)
    # la etiqueta es lo que se dibuja en una columna de ~11 pt: corta.
    for cod, m in cat.items():
        assert m["etiqueta"] and len(m["etiqueta"]) <= 12, (cod, m["etiqueta"])
    assert cat["OTRO"]["requiere_detalle"] is True
    assert cat["FERIADO"]["requiere_detalle"] is False


# ==========================================================================
# B — ALTA FELIZ Y SNAPSHOTS (§5)
# ==========================================================================
@test("B1 el profesor declara su sesion y el backend resuelve solo el bloque")
def _():
    _seed()
    r = _crear(H_PROF)
    assert r.status_code == 200, (r.status_code, r.text[:300])
    s = r.json()["sesion"]
    assert r.json()["reactivada"] is False
    assert s["horario_id"] == H_MAT, s
    assert s["dia"] == "Martes" and s["hora_inicio"] == "08:00" and s["hora_fin"] == "08:45"
    assert s["motivo_codigo"] == "SUSP_LLUVIA"
    assert s["etiqueta"] == "SUSP. LLUVIA", s["etiqueta"]
    assert s["profesor_id"] == U_PROF and s["activo"] is True
    assert _n_sesiones() == 1


@test("B2 los snapshots sobreviven al borrado del bloque de horario")
def _():
    _seed()
    assert _crear(H_PROF).status_code == 200
    d = SessionLocal()
    try:
        d.delete(d.query(M.Horario).get(H_MAT))
        d.commit()
        s = d.query(M.SesionNoImpartida).first()
        # el puntero queda colgando a proposito; la historia NO se pierde
        assert s.horario_id == H_MAT
        assert s.dia_semana_snapshot == "Martes"
        assert s.hora_inicio_snapshot == "08:00"
        assert s.hora_fin_snapshot == "08:45"
    finally:
        d.close()


@test("B3 queda registro de auditoria de quien la puso")
def _():
    _seed()
    assert _crear(H_PROF).status_code == 200
    d = SessionLocal()
    try:
        log = d.query(M.LogAuditoria).filter_by(
            accion="sesion_no_impartida_registrada").all()
        assert len(log) == 1, len(log)
        assert log[0].usuario_id == U_PROF and log[0].colegio_id == COL_A
    finally:
        d.close()


# ==========================================================================
# C — LA SESION TIENE QUE EXISTIR (§5)
# ==========================================================================
@test("C1 un dia sin bloque programado no se justifica (409)")
def _():
    _seed()
    r = _crear(H_PROF, fecha=LUNES.isoformat())
    assert r.status_code == 409, (r.status_code, r.text[:300])
    assert "no tiene sesion programada" in r.json()["error"].lower().replace("ó", "o")
    assert _n_sesiones() == 0


@test("C2 A - UN bloque: se crea con horario_id y horas de procedencia")
def _():
    _seed()
    r = _crear(H_PROF)                          # Matematica: un solo bloque el martes
    assert r.status_code == 200, (r.status_code, r.text[:300])
    s = r.json()["sesion"]
    assert s["horario_id"] == H_MAT, s
    assert s["dia"] == "Martes"
    assert s["hora_inicio"] == "08:00" and s["hora_fin"] == "08:45"
    assert _n_sesiones() == 1


@test("C3 el profesor sin asignacion sigue sin poder, con bloque o sin el")
def _():
    _seed()
    r = _crear(H_PROF, asignatura_id=ING)
    # prof no tiene asignacion de Ingles: se corta en la autorizacion
    assert r.status_code == 403, (r.status_code, r.text[:300])
    assert _n_sesiones() == 0


@test("C4 un horario_id enviado por el cliente se IGNORA: no hay suspension por bloque")
def _():
    # La granularidad es materia + fecha. Un `horario_id` en el cuerpo —de otra
    # materia, inexistente, o de un bloque concreto— no cambia lo que se declara
    # ni puede convertirlo en la suspension de un solo bloque.
    for etiqueta, extra in (("de otra asignatura", {"horario_id": H_LEN_1}),
                            ("inexistente", {"horario_id": 999999}),
                            ("basura", {"horario_id": "no-es-id"})):
        _seed()
        r = _crear(H_PROF, **extra)
        assert r.status_code == 200, (etiqueta, r.status_code, r.text[:300])
        s = r.json()["sesion"]
        # se resuelve por la clase, no por lo que mando el cliente
        assert s["horario_id"] == H_MAT, (etiqueta, s["horario_id"])
        assert s["asignatura_id"] == MAT, etiqueta
        assert _n_sesiones() == 1, etiqueta

    # El caso que de verdad distingue: un horario_id que SI es uno de los
    # bloques candidatos de una materia con VARIOS. Si el backend lo respetara,
    # la fila pasaria a representar ese bloque concreto —una suspension parcial—
    # en vez de la materia entera, que es justo lo que S1 no representa.
    _seed()
    r = _crear(H_PROF, asignatura_id=LEN, horario_id=H_LEN_2)
    assert r.status_code == 200, (r.status_code, r.text[:300])
    s = r.json()["sesion"]
    assert s["horario_id"] is None, (
        "el horario_id del cliente convirtio esto en una suspension de bloque",
        s["horario_id"])
    assert s["hora_inicio"] is None and s["hora_fin"] is None, s
    assert _n_sesiones() == 1


@test("C5 B - DOS bloques con horas distintas: una sola fila, sin horario_id")
def _():
    _seed()
    r = _crear(H_PROF, asignatura_id=LEN)       # Lengua: 09:00 y 11:00 el martes
    assert r.status_code == 200, (r.status_code, r.text[:300])
    s = r.json()["sesion"]
    assert _n_sesiones() == 1, "se creo mas de una justificacion"
    assert s["horario_id"] is None, s["horario_id"]
    assert s["hora_inicio"] is None and s["hora_fin"] is None, s
    assert s["dia"] == "Martes", s["dia"]       # el dia SI se conserva
    assert s["asignatura_id"] == LEN
    fila = _sesiones()[0]
    assert fila.horario_id is None and fila.hora_inicio_snapshot is None
    assert fila.dia_semana_snapshot == "Martes"


@test("C5b C - duplicados EXACTOS: tampoco hay que elegir entre ids indistinguibles")
def _():
    _seed()
    r = _crear(H_PROF, asignatura_id=SOC)       # dos filas, ambas 13:00-13:45
    assert r.status_code == 200, (r.status_code, r.text[:300])
    s = r.json()["sesion"]
    assert _n_sesiones() == 1
    assert s["horario_id"] is None, s["horario_id"]
    assert s["hora_inicio"] is None and s["hora_fin"] is None, s
    assert s["dia"] == "Martes"


@test("C5c D - declarada con varios bloques, no se pasa lista de esa materia")
def _():
    _seed()
    assert _crear(H_PROF, asignatura_id=LEN).status_code == 200
    r = client.post("/api/asistencia", headers=H_PROF, json={
        "estudiante_id": E1, "curso_id": CUR_SEC, "asignatura_id": LEN,
        "fecha": MARTES.isoformat(), "estado": "presente"})
    assert r.status_code == 409, (r.status_code, r.text[:300])
    # y el lote tampoco entra a medias
    r = client.post("/api/asistencia/masivo", headers=H_PROF, json={
        "curso_id": CUR_SEC, "asignatura_id": LEN, "fecha": MARTES.isoformat(),
        "asistencias": [{"estudiante_id": E1, "estado": "presente"},
                        {"estudiante_id": E2, "estado": "ausente"}]})
    assert r.status_code == 409, (r.status_code, r.text[:300])
    assert _n_asistencias() == 0


@test("C5d E - con asistencia previa de esa materia, no se declara y nada cambia")
def _():
    _seed()
    r = client.post("/api/asistencia", headers=H_PROF, json={
        "estudiante_id": E1, "curso_id": CUR_SEC, "asignatura_id": LEN,
        "fecha": MARTES.isoformat(), "estado": "presente"})
    assert r.status_code == 200, r.text[:300]
    antes = _n_asistencias()
    r = _crear(H_PROF, asignatura_id=LEN)
    assert r.status_code == 409, (r.status_code, r.text[:300])
    assert r.json()["asistencias"] == 1
    assert _n_sesiones() == 0
    assert _n_asistencias() == antes, "se toco la asistencia existente"


@test("C5e F - la asistencia de OTRA materia ese dia no estorba")
def _():
    _seed()
    r = client.post("/api/asistencia", headers=H_PROF, json={
        "estudiante_id": E1, "curso_id": CUR_SEC, "asignatura_id": MAT,
        "fecha": MARTES.isoformat(), "estado": "presente"})
    assert r.status_code == 200, r.text[:300]
    # Lengua (dos bloques) sigue pudiendo declararse
    assert _crear(H_PROF, asignatura_id=LEN).status_code == 200
    assert _n_asistencias(asignatura_id=MAT) == 1


@test("C5f H - retirar y volver a declarar una materia multibloque no duplica filas")
def _():
    _seed()
    sid = _crear(H_PROF, asignatura_id=LEN).json()["sesion"]["id"]
    assert client.delete(f"/api/sesiones-no-impartidas/{sid}",
                         headers=H_PROF).status_code == 200
    assert _n_sesiones() == 1 and _sesiones()[0].activo is False
    r = _crear(H_PROF, asignatura_id=LEN, motivo_codigo="REUNION")
    assert r.status_code == 200, (r.status_code, r.text[:300])
    assert r.json()["reactivada"] is True
    assert r.json()["sesion"]["id"] == sid
    assert _n_sesiones() == 1, "aparecio una segunda fila"
    assert _sesiones()[0].horario_id is None


@test("C6 un bloque inactivo ya no es una sesion programada")
def _():
    _seed()
    d = SessionLocal()
    try:
        d.query(M.Horario).get(H_MAT).activo = False
        d.commit()
    finally:
        d.close()
    r = _crear(H_PROF)
    assert r.status_code == 409, (r.status_code, r.text[:300])
    assert _n_sesiones() == 0


# ==========================================================================
# D — QUIEN PUEDE (§5)
# ==========================================================================
@test("D1 sin asignacion ACTIVA sobre (curso, asignatura) -> 403")
def _():
    _seed()
    d = SessionLocal()
    try:
        d.query(M.AsignacionProfesor).get(100).activo = False
        d.commit()
    finally:
        d.close()
    r = _crear(H_PROF)
    assert r.status_code == 403, (r.status_code, r.text[:300])
    assert _n_sesiones() == 0


@test("D2 dar clase en el curso no alcanza: tiene que ser ESA asignatura")
def _():
    _seed()
    # prof2 da Ingles en CUR_SEC; no puede justificar la Matematica de prof
    r = _crear(H_PROF2)
    assert r.status_code == 403, (r.status_code, r.text[:300])
    assert _n_sesiones() == 0


@test("D3 direccion y coordinacion NO declaran clases ajenas (403)")
def _():
    _seed()
    for hdr, quien in ((H_DIR, "direccion"), (H_COORD, "coordinador")):
        r = _crear(hdr)
        assert r.status_code == 403, (quien, r.status_code, r.text[:200])
    assert _n_sesiones() == 0


@test("D4 un profesor de otro colegio no alcanza este curso")
def _():
    _seed()
    r = _crear(H_PROF_B)
    assert r.status_code in (403, 404), (r.status_code, r.text[:300])
    assert _n_sesiones() == 0


# ==========================================================================
# E — DATOS DE ENTRADA
# ==========================================================================
@test("E1 motivo fuera del catalogo -> 400 (no se inventan motivos)")
def _():
    _seed()
    r = _crear(H_PROF, motivo_codigo="PORQUE_SI")
    assert r.status_code == 400, (r.status_code, r.text[:300])
    assert "SUSP_LLUVIA" in r.json()["validos"]
    assert _n_sesiones() == 0


@test("E2 OTRO sin detalle -> 400; con detalle -> entra")
def _():
    _seed()
    r = _crear(H_PROF, motivo_codigo="OTRO")
    assert r.status_code == 400, (r.status_code, r.text[:300])
    assert _n_sesiones() == 0
    r = _crear(H_PROF, motivo_codigo="OTRO", motivo_detalle="Falla electrica")
    assert r.status_code == 200, (r.status_code, r.text[:300])
    assert r.json()["sesion"]["motivo_detalle"] == "Falla electrica"


@test("E3 fecha futura y fecha absurda -> 400")
def _():
    _seed()
    futuro = date.today() + timedelta(days=30)
    while futuro.weekday() != 1:
        futuro += timedelta(days=1)
    assert _crear(H_PROF, fecha=futuro.isoformat()).status_code == 400
    assert _crear(H_PROF, fecha="2011-03-01").status_code == 400
    assert _crear(H_PROF, fecha="no-es-fecha").status_code == 400
    assert _n_sesiones() == 0


@test("E4 Primaria queda fuera de S1, y se dice por que")
def _():
    _seed()
    r = client.post("/api/sesiones-no-impartidas", headers=H_PROF, json={
        "curso_id": CUR_PRI, "asignatura_id": MAT, "fecha": MARTES.isoformat(),
        "motivo_codigo": "REUNION"})
    assert r.status_code == 400, (r.status_code, r.text[:300])
    assert "primaria" in r.json()["error"].lower()
    assert _n_sesiones() == 0


# ==========================================================================
# F — EXCLUSIVIDAD, DIRECCION A: asistencia ya registrada (§7)
# ==========================================================================
@test("F1 si la clase ya tiene asistencia, no se puede declarar no impartida")
def _():
    _seed()
    r = client.post("/api/asistencia", headers=H_PROF, json={
        "estudiante_id": E1, "curso_id": CUR_SEC, "asignatura_id": MAT,
        "fecha": MARTES.isoformat(), "estado": "presente"})
    assert r.status_code == 200, r.text[:300]
    r = _crear(H_PROF)
    assert r.status_code == 409, (r.status_code, r.text[:300])
    assert r.json()["asistencias"] == 1
    assert _n_sesiones() == 0


@test("F2 la asistencia de OTRA materia el mismo dia no estorba")
def _():
    _seed()
    r = client.post("/api/asistencia", headers=H_PROF, json={
        "estudiante_id": E1, "curso_id": CUR_SEC, "asignatura_id": LEN,
        "fecha": MARTES.isoformat(), "estado": "presente"})
    assert r.status_code == 200, r.text[:300]
    assert _crear(H_PROF).status_code == 200        # Matematica sigue libre
    assert _n_asistencias(asignatura_id=LEN) == 1   # y la marca de Lengua sigue ahi


# ==========================================================================
# G — EXCLUSIVIDAD, DIRECCION B: no se pasa lista de lo no impartido (§7)
# ==========================================================================
@test("G1 declarada la sesion, el alta individual de asistencia da 409")
def _():
    _seed()
    assert _crear(H_PROF).status_code == 200
    r = client.post("/api/asistencia", headers=H_PROF, json={
        "estudiante_id": E1, "curso_id": CUR_SEC, "asignatura_id": MAT,
        "fecha": MARTES.isoformat(), "estado": "presente"})
    assert r.status_code == 409, (r.status_code, r.text[:300])
    assert r.json()["motivo_codigo"] == "SUSP_LLUVIA"
    assert _n_asistencias() == 0


@test("G2 el lote se rechaza ENTERO: ni una marca parcial")
def _():
    _seed()
    assert _crear(H_PROF).status_code == 200
    r = client.post("/api/asistencia/masivo", headers=H_PROF, json={
        "curso_id": CUR_SEC, "asignatura_id": MAT, "fecha": MARTES.isoformat(),
        "asistencias": [{"estudiante_id": E1, "estado": "presente"},
                        {"estudiante_id": E2, "estado": "ausente"},
                        {"estudiante_id": E3, "estado": "presente"}]})
    assert r.status_code == 409, (r.status_code, r.text[:300])
    assert _n_asistencias() == 0, "el lote escribio a medias"


@test("G3 el bloqueo es de ESA clase: otra materia y otra fecha siguen abiertas")
def _():
    _seed()
    assert _crear(H_PROF).status_code == 200
    # misma fecha, otra materia
    r = client.post("/api/asistencia", headers=H_PROF, json={
        "estudiante_id": E1, "curso_id": CUR_SEC, "asignatura_id": LEN,
        "fecha": MARTES.isoformat(), "estado": "presente"})
    assert r.status_code == 200, (r.status_code, r.text[:300])
    # misma materia, el martes anterior
    otro = MARTES - timedelta(days=7)
    r = client.post("/api/asistencia", headers=H_PROF, json={
        "estudiante_id": E1, "curso_id": CUR_SEC, "asignatura_id": MAT,
        "fecha": otro.isoformat(), "estado": "presente"})
    assert r.status_code == 200, (r.status_code, r.text[:300])
    assert _n_asistencias() == 2


# ==========================================================================
# H — DUPLICADO, RETIRO Y REACTIVACION
# ==========================================================================
@test("H1 declarar dos veces la misma clase y fecha -> 409, sin duplicar")
def _():
    _seed()
    assert _crear(H_PROF).status_code == 200
    r = _crear(H_PROF, motivo_codigo="REUNION")
    assert r.status_code == 409, (r.status_code, r.text[:300])
    assert _n_sesiones() == 1
    assert _sesiones()[0].motivo_codigo == "SUSP_LLUVIA", "el motivo cambio por detras"


@test("H2 retirar no borra: desactiva y deja quien y cuando")
def _():
    _seed()
    sid = _crear(H_PROF).json()["sesion"]["id"]
    r = client.delete(f"/api/sesiones-no-impartidas/{sid}", headers=H_PROF)
    assert r.status_code == 200, (r.status_code, r.text[:300])
    assert _n_sesiones() == 1, "la fila desaparecio"
    s = _sesiones()[0]
    assert s.activo is False
    assert s.retirado_por == U_PROF and s.fecha_retiro is not None
    assert s.registrado_por == U_PROF, "se perdio quien la habia puesto"


@test("H3 retirada la justificacion, la clase vuelve a admitir asistencia")
def _():
    _seed()
    sid = _crear(H_PROF).json()["sesion"]["id"]
    assert client.delete(f"/api/sesiones-no-impartidas/{sid}", headers=H_PROF).status_code == 200
    r = client.post("/api/asistencia", headers=H_PROF, json={
        "estudiante_id": E1, "curso_id": CUR_SEC, "asignatura_id": MAT,
        "fecha": MARTES.isoformat(), "estado": "presente"})
    assert r.status_code == 200, (r.status_code, r.text[:300])
    assert _n_asistencias() == 1


@test("H4 volver a declararla REACTIVA la misma fila (la llave unica no choca)")
def _():
    _seed()
    sid = _crear(H_PROF).json()["sesion"]["id"]
    client.delete(f"/api/sesiones-no-impartidas/{sid}", headers=H_PROF)
    r = _crear(H_PROF, motivo_codigo="ACTIVIDAD")
    assert r.status_code == 200, (r.status_code, r.text[:300])
    assert r.json()["reactivada"] is True
    assert r.json()["sesion"]["id"] == sid, "inserto una fila nueva"
    assert _n_sesiones() == 1
    s = _sesiones()[0]
    assert s.activo is True and s.motivo_codigo == "ACTIVIDAD"
    assert s.retirado_por is None and s.fecha_retiro is None


@test("H5 retirar dos veces es idempotente, no un error")
def _():
    _seed()
    sid = _crear(H_PROF).json()["sesion"]["id"]
    client.delete(f"/api/sesiones-no-impartidas/{sid}", headers=H_PROF)
    antes = _sesiones()[0].fecha_retiro
    r = client.delete(f"/api/sesiones-no-impartidas/{sid}", headers=H_PROF)
    assert r.status_code == 200, (r.status_code, r.text[:300])
    assert _sesiones()[0].fecha_retiro == antes, "se piso la fecha de retiro"


@test("H6 direccion puede retirar; un profesor ajeno no la ve (404)")
def _():
    _seed()
    sid = _crear(H_PROF).json()["sesion"]["id"]
    assert client.delete(f"/api/sesiones-no-impartidas/{sid}",
                         headers=H_PROF2).status_code == 404
    assert _sesiones()[0].activo is True
    r = client.delete(f"/api/sesiones-no-impartidas/{sid}", headers=H_DIR)
    assert r.status_code == 200, (r.status_code, r.text[:300])
    assert _sesiones()[0].retirado_por == U_DIR


@test("H7 el profesor que ya no da esa clase no la retira: se lo pide a Direccion")
def _():
    _seed()
    sid = _crear(H_PROF).json()["sesion"]["id"]
    d = SessionLocal()
    try:
        d.query(M.AsignacionProfesor).get(100).activo = False
        d.commit()
    finally:
        d.close()
    r = client.delete(f"/api/sesiones-no-impartidas/{sid}", headers=H_PROF)
    assert r.status_code == 403, (r.status_code, r.text[:300])
    assert "Direcci" in r.json()["error"]
    assert _sesiones()[0].activo is True


@test("H8 un profesor de otro colegio no retira nada de este (404)")
def _():
    _seed()
    sid = _crear(H_PROF).json()["sesion"]["id"]
    assert client.delete(f"/api/sesiones-no-impartidas/{sid}",
                         headers=H_PROF_B).status_code == 404
    assert _sesiones()[0].activo is True


# ==========================================================================
# I — LECTURA
# ==========================================================================
@test("I1 el profesor ve las suyas; no las de un colega")
def _():
    _seed()
    assert _crear(H_PROF).status_code == 200
    assert client.post("/api/sesiones-no-impartidas", headers=H_PROF2, json={
        "curso_id": CUR_SEC, "asignatura_id": ING, "fecha": MARTES.isoformat(),
        "motivo_codigo": "REUNION"}).status_code == 200
    mias = client.get("/api/sesiones-no-impartidas", headers=H_PROF).json()
    assert [s["asignatura_id"] for s in mias] == [MAT], mias
    otras = client.get("/api/sesiones-no-impartidas", headers=H_PROF2).json()
    assert [s["asignatura_id"] for s in otras] == [ING], otras
    todas = client.get("/api/sesiones-no-impartidas", headers=H_DIR).json()
    assert len(todas) == 2, todas


@test("I2 filtra por curso, asignatura y rango; las retiradas no salen por defecto")
def _():
    _seed()
    sid = _crear(H_PROF).json()["sesion"]["id"]
    q = f"?curso_id={CUR_SEC}&asignatura_id={MAT}&desde={MARTES.isoformat()}&hasta={MARTES.isoformat()}"
    assert len(client.get("/api/sesiones-no-impartidas" + q, headers=H_PROF).json()) == 1
    otra = (MARTES + timedelta(days=1)).isoformat()
    assert client.get(f"/api/sesiones-no-impartidas?desde={otra}",
                      headers=H_PROF).json() == []
    client.delete(f"/api/sesiones-no-impartidas/{sid}", headers=H_PROF)
    assert client.get("/api/sesiones-no-impartidas", headers=H_PROF).json() == []
    con = client.get("/api/sesiones-no-impartidas?incluir_retiradas=1", headers=H_PROF).json()
    assert len(con) == 1 and con[0]["activo"] is False


@test("I3 el colegio B no ve nada del colegio A")
def _():
    _seed()
    assert _crear(H_PROF).status_code == 200
    assert client.get("/api/sesiones-no-impartidas", headers=H_PROF_B).json() == []


# ==========================================================================
# J — §3: LOS FERIADOS NO SE CONECTAN SOLOS
# ==========================================================================
@test("J1 un DiaNoLaborable NO impide pasar lista")
def _():
    _seed()
    d = SessionLocal()
    try:
        d.add(M.DiaNoLaborable(colegio_id=COL_A, ano_escolar_id=ANO_A, fecha=MARTES,
                               nombre="Feriado nacional", tipo="feriado",
                               recurrente=False, activo=True))
        d.commit()
    finally:
        d.close()
    r = client.post("/api/asistencia", headers=H_PROF, json={
        "estudiante_id": E1, "curso_id": CUR_SEC, "asignatura_id": MAT,
        "fecha": MARTES.isoformat(), "estado": "presente"})
    assert r.status_code == 200, (r.status_code, r.text[:300])
    assert _n_asistencias() == 1


@test("J2 un DiaNoLaborable tampoco crea sesiones no impartidas por su cuenta")
def _():
    _seed()
    d = SessionLocal()
    try:
        d.add(M.DiaNoLaborable(colegio_id=COL_A, ano_escolar_id=ANO_A, fecha=MARTES,
                               nombre="Feriado nacional", tipo="feriado",
                               recurrente=False, activo=True))
        d.commit()
    finally:
        d.close()
    assert _n_sesiones() == 0
    # y si el profesor SI quiere dejarlo asentado, lo hace a mano con FERIADO
    r = _crear(H_PROF, motivo_codigo="FERIADO")
    assert r.status_code == 200, (r.status_code, r.text[:300])
    assert r.json()["sesion"]["etiqueta"] == "FERIADO"


# ==========================================================================
# K — NADA SE ROMPIO
# ==========================================================================
@test("K1 sin ninguna sesion declarada, asistencia individual y lote siguen igual")
def _():
    _seed()
    r = client.post("/api/asistencia", headers=H_PROF, json={
        "estudiante_id": E1, "curso_id": CUR_SEC, "asignatura_id": MAT,
        "fecha": MARTES.isoformat(), "estado": "presente"})
    assert r.status_code == 200, (r.status_code, r.text[:300])
    r = client.post("/api/asistencia/masivo", headers=H_PROF, json={
        "curso_id": CUR_SEC, "asignatura_id": MAT, "fecha": MARTES.isoformat(),
        "asistencias": [{"estudiante_id": E2, "estado": "ausente"},
                        {"estudiante_id": E3, "estado": "tardanza"}]})
    assert r.status_code == 200, (r.status_code, r.text[:300])
    assert _n_asistencias() == 3


@test("K2 la asistencia de Primaria (asignatura NULL) no la toca S1")
def _():
    _seed()
    r = client.post("/api/asistencia", headers=H_PROF, json={
        "estudiante_id": E_PRI, "curso_id": CUR_PRI, "fecha": MARTES.isoformat(),
        "estado": "presente"})
    assert r.status_code == 200, (r.status_code, r.text[:300])
    assert _n_asistencias(estudiante_id=E_PRI) == 1


@test("K3 borrar una marca de asistencia nunca se bloquea (es la salida del conflicto)")
def _():
    _seed()
    client.post("/api/asistencia", headers=H_PROF, json={
        "estudiante_id": E1, "curso_id": CUR_SEC, "asignatura_id": MAT,
        "fecha": MARTES.isoformat(), "estado": "presente"})
    r = client.request("DELETE",
                       f"/api/asistencia/{E1}?fecha={MARTES.isoformat()}&asignatura_id={MAT}",
                       headers=H_PROF)
    assert r.status_code == 200, (r.status_code, r.text[:300])
    assert _n_asistencias() == 0
    # y ahora si se puede declarar
    assert _crear(H_PROF).status_code == 200


@test("K4 el repo no fue tocado: sge.db intacto")
def _():
    a = os.path.getmtime(_REPO_SGE) if os.path.exists(_REPO_SGE) else None
    assert a == _sge_mtime, "sge.db fue modificado"


print("\n" + "=" * 70)
print(f"{B}S1 SESION NO IMPARTIDA (backend): {_ok}/{_total} pruebas{X}")
if _fail:
    print(f"{R}FALLARON:{X}")
    for n, e in _fail:
        print(f"  - {n}: {e}")
    sys.exit(1)
print(f"{G}TODO VERDE{X}")
