# -*- coding: utf-8 -*-
"""
EducaOne PRIMARIA P2A-R1 — recuperacion pedagogica del periodo por grado.

POR QUE EXISTE
    El Registro oficial del Nivel Primario trae, SOLO en 1ro y 2do, un
    formulario de recuperacion pedagogica con cuatro columnas —area, aspectos
    no logrados y periodo, estrategias y evidencias, competencia lograda o no
    lograda— porque en esos dos grados la norma la registra de manera
    CUALITATIVA. En 3ro-6to se registra de manera cuantitativa, y para eso ya
    estaban las columnas rpN.

    EducaOne ofrecia rpN numerica en los seis grados. En 1ro y 2do esa nota
    cambiaba la calificacion del periodo y no aparecia en ningun documento
    oficial, porque ni el Informe de Aprendizaje ni el Registro de esos grados
    traen columnas RP: era un cambio de nota invisible.

    Esta suite fija las dos modalidades, la frontera entre ellas, y que la
    cualitativa no toca ni un numero.

LO QUE NO SE TOCA
    P1 (calificaciones), P3 (asistencia), Horarios, Registro, boletin y la
    Recuperacion FINAL del area siguen exactamente igual: hay casos de
    regresion para cada uno.

Uso:
    cd backend
    python tools/test_primaria_recuperacion_cualitativa.py
"""
import os
import sys
import atexit
import tempfile
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TMPDIR = tempfile.mkdtemp(prefix="eo_reccual_")
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
#   1ro A y 2do A: cualitativos.  4to A: cuantitativo.  SEC1: secundaria.
#   LENGUA es area oficial; MUSICA es materia INTERNA del colegio, y tiene
#   que poder registrar recuperacion cualitativa igual que cualquier otra.
# --------------------------------------------------------------------------
PWD = "Prueba2026x"
COL_A, COL_B = 1, 2
ANO_A, ANO_B = 1, 2

G_1RO, G_2DO, G_4TO, G_SEC = 11, 12, 14, 19
CUR_1A, CUR_2A, CUR_4A, CUR_SEC = 21, 22, 24, 29
CUR_B = 90
G_B = 91

LENGUA, MUSICA, MATE = 1, 2, 3
ASIG_B = 9

E_1A, E_1A2, E_2A, E_4A, E_RET = 101, 102, 103, 104, 105
E_B = 190

PROF, PROF_OTRA, PROF_SIN, PROF_MULTI = 301, 302, 303, 304
DIR, COORD, SECRE, PSICO = 310, 311, 312, 313
PROF_B = 390


def _u(uid, col, user, rol):
    x = M.Usuario(id=uid, colegio_id=col, username=user, nombre=user.title(),
                  apellido="X", role=rol, activo=True)
    x.set_password(PWD)
    return x


def _asig(col, prof, curso, asignatura, ano, titular=False, activo=True):
    return M.AsignacionProfesor(colegio_id=col, profesor_id=prof, curso_id=curso,
                                asignatura_id=asignatura, ano_escolar_id=ano,
                                activo=activo, es_titular=titular)


def fixture():
    d = SessionLocal()
    for col, cod in ((COL_A, "a"), (COL_B, "b")):
        d.add(M.Colegio(id=col, nombre=f"Colegio {cod}", codigo=cod, activo=True,
                        plan="premium", plan_primaria=True, plan_secundaria=True))
        d.add(M.ConfiguracionColegio(id=col, colegio_id=col, nombre=f"Colegio {cod}",
                                     usa_primaria=True, usa_secundaria=True))
    for ano, col in ((ANO_A, COL_A), (ANO_B, COL_B)):
        d.add(M.AnoEscolar(id=ano, colegio_id=col, nombre="2025-2026", activo=True,
                           fecha_inicio=date(2025, 9, 1), fecha_fin=date(2026, 6, 30),
                           periodo_activo=1, cerrado=False, p1_cerrado=False,
                           p2_cerrado=False, p3_cerrado=False, p4_cerrado=False))

    d.add(M.Grado(id=G_1RO, colegio_id=COL_A, nombre="1ro Primaria", nivel="primaria",
                  ciclo="primer_ciclo", orden=7))
    d.add(M.Grado(id=G_2DO, colegio_id=COL_A, nombre="2do Primaria", nivel="primaria",
                  ciclo="primer_ciclo", orden=8))
    d.add(M.Grado(id=G_4TO, colegio_id=COL_A, nombre="4to Primaria", nivel="primaria",
                  ciclo="segundo_ciclo", orden=10))
    d.add(M.Grado(id=G_SEC, colegio_id=COL_A, nombre="1ro Secundaria", nivel="secundaria",
                  orden=1))
    d.add(M.Grado(id=G_B, colegio_id=COL_B, nombre="1ro Primaria", nivel="primaria",
                  ciclo="primer_ciclo", orden=7))

    for cur, gra, col, ano in ((CUR_1A, G_1RO, COL_A, ANO_A), (CUR_2A, G_2DO, COL_A, ANO_A),
                               (CUR_4A, G_4TO, COL_A, ANO_A), (CUR_SEC, G_SEC, COL_A, ANO_A),
                               (CUR_B, G_B, COL_B, ANO_B)):
        d.add(M.Curso(id=cur, colegio_id=col, nombre="A", grado_id=gra, ano_escolar_id=ano))

    d.add(M.Asignatura(id=LENGUA, colegio_id=COL_A, nombre="Lengua Española", codigo="LE"))
    d.add(M.Asignatura(id=MUSICA, colegio_id=COL_A, nombre="Musica", codigo="MS"))
    d.add(M.Asignatura(id=MATE, colegio_id=COL_A, nombre="Matemática", codigo="MA"))
    d.add(M.Asignatura(id=ASIG_B, colegio_id=COL_B, nombre="Lengua Española", codigo="LE"))

    for eid, cur, col, act in ((E_1A, CUR_1A, COL_A, True), (E_1A2, CUR_1A, COL_A, True),
                               (E_2A, CUR_2A, COL_A, True), (E_4A, CUR_4A, COL_A, True),
                               (E_RET, CUR_1A, COL_A, False), (E_B, CUR_B, COL_B, True)):
        d.add(M.Estudiante(id=eid, colegio_id=col, nombre=f"Est{eid}", apellido="P",
                           curso_id=cur, activo=act, no_lista=eid - 100))

    d.add(_u(PROF, COL_A, "prof", "profesor"))
    d.add(_u(PROF_OTRA, COL_A, "profotra", "profesor"))
    d.add(_u(PROF_SIN, COL_A, "profsin", "profesor"))
    d.add(_u(PROF_MULTI, COL_A, "profmulti", "profesor"))
    d.add(_u(DIR, COL_A, "dir", "direccion"))
    d.add(_u(COORD, COL_A, "coord", "coordinador"))
    d.add(_u(SECRE, COL_A, "secre", "secretaria"))
    d.add(_u(PSICO, COL_A, "psico", "psicologia"))
    d.add(_u(PROF_B, COL_B, "profb", "profesor"))

    # PROF: Lengua y Musica en 1ro A, Lengua en 2do A y en 4to A.
    d.add(_asig(COL_A, PROF, CUR_1A, LENGUA, ANO_A, titular=True))
    d.add(_asig(COL_A, PROF, CUR_1A, MUSICA, ANO_A))
    d.add(_asig(COL_A, PROF, CUR_2A, LENGUA, ANO_A, titular=True))
    d.add(_asig(COL_A, PROF, CUR_4A, LENGUA, ANO_A, titular=True))
    # PROF_OTRA da Matematica en 1ro A: mismo curso, otra asignatura.
    d.add(_asig(COL_A, PROF_OTRA, CUR_1A, MATE, ANO_A))
    # PROF_MULTI da Lengua en 1ro A y ademas en Secundaria.
    d.add(_asig(COL_A, PROF_MULTI, CUR_1A, LENGUA, ANO_A))
    d.add(_asig(COL_A, PROF_MULTI, CUR_SEC, LENGUA, ANO_A))
    d.add(_asig(COL_B, PROF_B, CUR_B, ASIG_B, ANO_B, titular=True))
    d.commit()
    d.close()


fixture()


def _tok(u):
    r = client.post("/api/auth/login", json={"username": u, "password": PWD})
    assert r.status_code == 200, (u, r.text[:200])
    return {"Authorization": "Bearer " + r.json()["token"]}


H_PROF = _tok("prof")
H_OTRA = _tok("profotra")
H_SIN = _tok("profsin")
H_MULTI = _tok("profmulti")
H_DIR = _tok("dir")
H_COORD = _tok("coord")
H_SECRE = _tok("secre")
H_PSICO = _tok("psico")
H_B = _tok("profb")


# ---------------------------- helpers ----------------------------
def contexto(hdr, curso):
    return client.get(f"/api/recuperacion-primaria/contexto/{curso}", headers=hdr)


def listar(hdr, curso, asig, periodo=None):
    url = f"/api/recuperacion-primaria/cualitativa/{curso}/{asig}"
    if periodo:
        url += f"?periodo={periodo}"
    return client.get(url, headers=hdr)


def crear(hdr, est, asig, periodo=1, resultado="no_lograda",
          aspectos="No identifica las vocales", **extra):
    cuerpo = {"estudiante_id": est, "asignatura_id": asig, "periodo": periodo,
              "resultado": resultado, "aspectos_no_logrados": aspectos}
    cuerpo.update(extra)
    return client.post("/api/recuperacion-primaria/cualitativa", headers=hdr, json=cuerpo)


def editar(hdr, rid, **campos):
    base = {"periodo": 1, "resultado": "lograda", "aspectos_no_logrados": "Corregido"}
    base.update(campos)
    return client.put(f"/api/recuperacion-primaria/cualitativa/{rid}", headers=hdr, json=base)


def retirar(hdr, rid, motivo=None):
    return client.post(f"/api/recuperacion-primaria/cualitativa/{rid}/retirar",
                       headers=hdr, json={"motivo_retiro": motivo} if motivo else {})


def calificar(hdr, est, asig, comp=1, **campos):
    cuerpo = {"estudiante_id": est, "asignatura_id": asig, "competencia_numero": comp}
    cuerpo.update(campos)
    return client.post("/api/calificaciones-primaria", headers=hdr, json=cuerpo)


def fila(rid):
    d = SessionLocal()
    try:
        return d.get(M.RecuperacionPedagogicaPrimaria, rid)
    finally:
        d.close()


def calif_fila(est, asig, comp=1):
    d = SessionLocal()
    try:
        return d.query(M.CalificacionPrimaria).filter_by(
            estudiante_id=est, asignatura_id=asig, competencia_numero=comp).first()
    finally:
        d.close()


def set_asignacion(prof, curso, asig, activo):
    d = SessionLocal()
    try:
        a = d.query(M.AsignacionProfesor).filter_by(
            profesor_id=prof, curso_id=curso, asignatura_id=asig).first()
        a.activo = activo
        d.commit()
    finally:
        d.close()


def set_periodo_cerrado(n, cerrado):
    d = SessionLocal()
    try:
        a = d.get(M.AnoEscolar, ANO_A)
        setattr(a, f"p{n}_cerrado", cerrado)
        d.commit()
    finally:
        d.close()


# ═══════════════════ A · MODALIDAD SEGUN EL GRADO ═══════════════════

@test("A1 1ro -> cualitativa")
def _():
    r = contexto(H_PROF, CUR_1A)
    assert r.status_code == 200, r.text[:200]
    assert r.json()["modalidad"] == "cualitativa", r.json()


@test("A2 2do -> cualitativa")
def _():
    assert contexto(H_PROF, CUR_2A).json()["modalidad"] == "cualitativa"


@test("A3 4to -> cuantitativa (3ro-6to no cambian)")
def _():
    assert contexto(H_PROF, CUR_4A).json()["modalidad"] == "cuantitativa"


@test("A4 la modalidad NO depende de lo que mande el cliente")
def _():
    # Aunque el cuerpo pida 'cualitativa', el curso de 4to manda.
    r = crear(H_PROF, E_4A, LENGUA, modalidad="cualitativa")
    assert r.status_code == 409, (r.status_code, r.text[:200])
    # Y el contexto tampoco se deja influir por query params.
    r2 = client.get(f"/api/recuperacion-primaria/contexto/{CUR_4A}?modalidad=cualitativa",
                    headers=H_PROF)
    assert r2.json()["modalidad"] == "cuantitativa", r2.json()


@test("A5 recuperacion cualitativa en 4to -> rechazo 409")
def _():
    r = crear(H_PROF, E_4A, LENGUA)
    assert r.status_code == 409, (r.status_code, r.text[:250])
    assert "cuantitativa" in r.json()["error"].lower()
    assert listar(H_PROF, CUR_4A, LENGUA).status_code == 409


@test("A6 un curso de Secundaria no entra por aqui")
def _():
    r = contexto(H_MULTI, CUR_SEC)
    assert r.status_code == 400, (r.status_code, r.text[:200])


# ═══════════════════ B · RP NUMERICA RECHAZADA EN 1ro/2do ═══════════════════

@test("B1 rp1 numerico en 1ro -> rechazo 400, no se guarda nada")
def _():
    r = calificar(H_PROF, E_1A, LENGUA, p1=50, rp1=70)
    assert r.status_code == 400, (r.status_code, r.text[:250])
    assert "cualitativa" in r.json()["error"].lower()
    assert r.json()["campos_rechazados"] == ["rp1"], r.json()
    assert calif_fila(E_1A, LENGUA) is None, "no debio crearse la calificacion"


@test("B2 rp numerico en 2do -> rechazo 400")
def _():
    r = calificar(H_PROF, E_2A, LENGUA, p2=40, rp2=65)
    assert r.status_code == 400, (r.status_code, r.text[:250])


@test("B3 el rechazo es explicito, no un silencio")
def _():
    r = calificar(H_PROF, E_1A, LENGUA, rp3=80)
    assert r.status_code == 400
    j = r.json()
    assert "error" in j and "campos_rechazados" in j, j


@test("B4 P sin RP se guarda normal en 1ro (la nota del periodo SI es numerica)")
def _():
    r = calificar(H_PROF, E_1A, LENGUA, p1=72)
    assert r.status_code == 200, (r.status_code, r.text[:250])
    assert calif_fila(E_1A, LENGUA).p1 == 72


@test("B5 mandar rp=null LIMPIA, no se rechaza")
def _():
    r = calificar(H_PROF, E_1A, LENGUA, p2=80, rp2=None)
    assert r.status_code == 200, (r.status_code, r.text[:250])
    assert calif_fila(E_1A, LENGUA).p2 == 80


@test("B6 en 4to la RP numerica sigue funcionando igual que siempre")
def _():
    r = calificar(H_PROF, E_4A, LENGUA, p1=50, rp1=70)
    assert r.status_code == 200, (r.status_code, r.text[:250])
    f = calif_fila(E_4A, LENGUA)
    assert f.p1 == 50 and f.rp1 == 70, (f.p1, f.rp1)


# ═══════════════════ C · PERMISOS ═══════════════════

_ID_BASE = {}


@test("C1 profesor con asignacion exacta activa -> crea")
def _():
    r = crear(H_PROF, E_1A, LENGUA, periodo=1, resultado="no_lograda")
    assert r.status_code == 200, (r.status_code, r.text[:250])
    _ID_BASE["primera"] = r.json()["id"]
    f = fila(_ID_BASE["primera"])
    assert f.registrado_por == PROF and f.curso_id == CUR_1A and f.activo is True


@test("C2 profesor SIN asignacion -> 403")
def _():
    r = crear(H_SIN, E_1A, LENGUA)
    assert r.status_code == 403, (r.status_code, r.text[:200])


@test("C3 profesor de OTRA asignatura del mismo curso -> 403")
def _():
    r = crear(H_OTRA, E_1A, LENGUA)
    assert r.status_code == 403, (r.status_code, r.text[:200])


@test("C4 direccion no crea intervenciones")
def _():
    assert crear(H_DIR, E_1A, LENGUA).status_code == 403


@test("C5 secretaria y psicologia no reciben escrituras nuevas")
def _():
    assert crear(H_SECRE, E_1A, LENGUA).status_code == 403
    assert crear(H_PSICO, E_1A, LENGUA).status_code == 403
    rid = _ID_BASE["primera"]
    assert retirar(H_SECRE, rid, "x").status_code == 403
    assert retirar(H_PSICO, rid, "x").status_code == 403
    assert editar(H_SECRE, rid).status_code == 403


@test("C6 la lectura conserva EXACTAMENTE los roles del modulo existente")
def _():
    # El modulo ya daba lectura a direccion, coordinacion, secretaria y profesor.
    for h in (H_DIR, H_COORD, H_SECRE, H_PROF):
        assert listar(h, CUR_1A, LENGUA).status_code == 200
    # Psicologia no estaba y no se le abre ahora.
    assert listar(H_PSICO, CUR_1A, LENGUA).status_code == 403
    assert contexto(H_PSICO, CUR_1A).status_code == 403


@test("C7 el profesor solo lee SUS cursos/asignaturas")
def _():
    assert listar(H_OTRA, CUR_1A, LENGUA).status_code == 403
    assert listar(H_SIN, CUR_1A, LENGUA).status_code == 403


@test("C8 autor con asignacion RETIRADA no puede editar")
def _():
    r = crear(H_MULTI, E_1A, LENGUA, aspectos="De multi")
    assert r.status_code == 200, r.text[:200]
    rid = r.json()["id"]
    set_asignacion(PROF_MULTI, CUR_1A, LENGUA, False)
    try:
        e = editar(H_MULTI, rid)
        assert e.status_code == 403, (e.status_code, e.text[:250])
        assert "asignación activa" in e.json()["error"]
    finally:
        set_asignacion(PROF_MULTI, CUR_1A, LENGUA, True)


@test("C9 autor con asignacion RETIRADA no puede retirar")
def _():
    r = crear(H_MULTI, E_1A, LENGUA, aspectos="De multi 2")
    rid = r.json()["id"]
    set_asignacion(PROF_MULTI, CUR_1A, LENGUA, False)
    try:
        q = retirar(H_MULTI, rid)
        assert q.status_code == 403, (q.status_code, q.text[:250])
        assert fila(rid).activo is True, "no debio retirarse"
    finally:
        set_asignacion(PROF_MULTI, CUR_1A, LENGUA, True)


@test("C10 un profesor no edita la intervencion de otro")
def _():
    rid = _ID_BASE["primera"]
    r = editar(H_MULTI, rid)
    assert r.status_code == 403, (r.status_code, r.text[:200])


@test("C11 estudiante retirado no recibe intervenciones nuevas")
def _():
    assert crear(H_PROF, E_RET, LENGUA).status_code == 403


# ═══════════════════ D · TENANT ═══════════════════

@test("D1 estudiante de otro colegio -> 404, sin fuga")
def _():
    r = crear(H_PROF, E_B, LENGUA)
    assert r.status_code == 404, (r.status_code, r.text[:200])


@test("D2 el colegio B no ve ni toca nada del colegio A")
def _():
    assert contexto(H_B, CUR_1A).status_code == 404
    assert listar(H_B, CUR_1A, LENGUA).status_code == 404
    assert editar(H_B, _ID_BASE["primera"]).status_code == 404
    assert retirar(H_B, _ID_BASE["primera"]).status_code == 404


# ═══════════════════ E · HISTORIAL ═══════════════════

@test("E1 varias intervenciones del mismo estudiante/asignatura/periodo conviven")
def _():
    a = crear(H_PROF, E_1A2, LENGUA, periodo=2, resultado="no_lograda", aspectos="Noviembre")
    b = crear(H_PROF, E_1A2, LENGUA, periodo=2, resultado="lograda", aspectos="Diciembre")
    assert a.status_code == 200 and b.status_code == 200, (a.text[:150], b.text[:150])
    assert a.json()["id"] != b.json()["id"]
    r = listar(H_PROF, CUR_1A, LENGUA, periodo=2)
    mias = [i for i in r.json()["intervenciones"] if i["estudiante_id"] == E_1A2]
    assert len(mias) == 2, mias
    assert {i["resultado"] for i in mias} == {"no_lograda", "lograda"}
    assert fila(a.json()["id"]).aspectos_no_logrados == "Noviembre", "se sobrescribio la primera"


@test("E2 retirar conserva la fila y el autor original")
def _():
    r = crear(H_PROF, E_1A, LENGUA, periodo=3, aspectos="Para retirar")
    rid = r.json()["id"]
    q = retirar(H_PROF, rid)
    assert q.status_code == 200, q.text[:200]
    f = fila(rid)
    assert f is not None, "se borro la fila"
    assert f.activo is False and f.registrado_por == PROF and f.retirado_por == PROF
    assert f.aspectos_no_logrados == "Para retirar", "se perdio el texto"


@test("E3 editar NO cambia el autor ni la fecha de registro")
def _():
    r = crear(H_PROF, E_1A, LENGUA, periodo=4, aspectos="Original")
    rid = r.json()["id"]
    antes = fila(rid)
    autor, fecha = antes.registrado_por, antes.fecha_registro
    e = editar(H_PROF, rid, periodo=4, aspectos_no_logrados="Corregido")
    assert e.status_code == 200, e.text[:200]
    d = fila(rid)
    assert d.aspectos_no_logrados == "Corregido"
    assert d.registrado_por == autor and d.fecha_registro == fecha


@test("E4 una intervencion retirada no se edita")
def _():
    r = crear(H_PROF, E_1A, LENGUA, aspectos="Doble retiro")
    rid = r.json()["id"]
    retirar(H_PROF, rid)
    assert editar(H_PROF, rid).status_code == 400
    assert retirar(H_PROF, rid).status_code == 400


@test("E5 direccion retira administrativamente con motivo obligatorio")
def _():
    r = crear(H_PROF, E_1A, LENGUA, aspectos="Retiro admin")
    rid = r.json()["id"]
    assert retirar(H_DIR, rid).status_code == 400, "sin motivo no deberia dejar"
    q = retirar(H_DIR, rid, "Texto cargado en el curso equivocado")
    assert q.status_code == 200, q.text[:200]
    f = fila(rid)
    assert f.activo is False and f.retirado_por == DIR
    assert f.motivo_retiro == "Texto cargado en el curso equivocado"
    assert f.registrado_por == PROF, "el autor original cambio"


@test("E6 el historial devuelve tambien las retiradas, marcadas")
def _():
    r = listar(H_PROF, CUR_1A, LENGUA)
    assert r.status_code == 200
    estados = {i["activo"] for i in r.json()["intervenciones"]}
    assert estados == {True, False}, estados


# ═══════════════════ F · NO TOCA NINGUN NUMERO ═══════════════════

@test("F1 'lograda' no modifica P, ni final_competencia, ni la CF del area")
def _():
    # Notas completas de las 3 competencias en 1ro A / Lengua.
    for comp, notas in ((1, dict(p1=60, p2=60, p3=60, p4=60)),
                        (2, dict(p1=70, p2=70, p3=70, p4=70)),
                        (3, dict(p1=80, p2=80, p3=80, p4=80))):
        assert calificar(H_PROF, E_1A2, LENGUA, comp=comp, **notas).status_code == 200

    from calculo_primaria import cf_area

    def foto():
        d = SessionLocal()
        try:
            comps = d.query(M.CalificacionPrimaria).filter_by(
                estudiante_id=E_1A2, asignatura_id=LENGUA).all()
            return ([(c.competencia_numero, c.p1, c.p2, c.p3, c.p4, c.rp1,
                      c.final_competencia, c.literal) for c in sorted(
                          comps, key=lambda x: x.competencia_numero)],
                    cf_area(comps))
        finally:
            d.close()

    antes = foto()
    assert crear(H_PROF, E_1A2, LENGUA, periodo=1, resultado="lograda",
                 aspectos="Ya lo logro").status_code == 200
    despues = foto()
    assert antes == despues, f"la cualitativa movio numeros:\n{antes}\n{despues}"


@test("F2 tampoco los mueve retirar ni editar")
def _():
    from calculo_primaria import cf_area

    def cf():
        d = SessionLocal()
        try:
            return cf_area(d.query(M.CalificacionPrimaria).filter_by(
                estudiante_id=E_1A2, asignatura_id=LENGUA).all())
        finally:
            d.close()

    antes = cf()
    r = crear(H_PROF, E_1A2, LENGUA, periodo=2, resultado="no_lograda", aspectos="Otra")
    rid = r.json()["id"]
    editar(H_PROF, rid, periodo=2, resultado="lograda", aspectos_no_logrados="Editada")
    retirar(H_PROF, rid)
    assert cf() == antes, (antes, cf())


# ═══════════════════ G · VALIDACION ═══════════════════

@test("G1 periodo y resultado se validan")
def _():
    assert crear(H_PROF, E_1A, LENGUA, periodo=5).status_code == 400
    assert crear(H_PROF, E_1A, LENGUA, periodo=0).status_code == 400
    assert crear(H_PROF, E_1A, LENGUA, resultado="mas_o_menos").status_code == 400
    assert crear(H_PROF, E_1A, LENGUA, resultado="65").status_code == 400


@test("G2 aspectos_no_logrados es obligatorio")
def _():
    assert crear(H_PROF, E_1A, LENGUA, aspectos="   ").status_code == 400


@test("G3 competencia: 1/2/3 o vacio (el formulario oficial admite varias)")
def _():
    assert crear(H_PROF, E_1A, LENGUA, competencia_numero=2).status_code == 200
    r = crear(H_PROF, E_1A, LENGUA, competencia_numero=None)
    assert r.status_code == 200
    assert fila(r.json()["id"]).competencia_numero is None
    assert crear(H_PROF, E_1A, LENGUA, competencia_numero=4).status_code == 400


# ═══════════════════ H · PERIODO CERRADO ═══════════════════

@test("H1 periodo cerrado bloquea al profesor sin permiso")
def _():
    set_periodo_cerrado(1, True)
    try:
        r = crear(H_PROF, E_1A, LENGUA, periodo=1, aspectos="Con P1 cerrado")
        assert r.status_code == 403, (r.status_code, r.text[:250])
    finally:
        set_periodo_cerrado(1, False)


@test("H2 el permiso temporal conserva la politica de P1")
def _():
    set_periodo_cerrado(1, True)
    d = SessionLocal()
    try:
        d.add(M.PermisoTemporalCalificacion(
            colegio_id=COL_A, profesor_id=PROF, periodo=1, asignatura_id=LENGUA,
            activo=True, fecha_fin=APP.now_rd() + timedelta(days=1), otorgado_por=DIR))
        d.commit()
    finally:
        d.close()
    try:
        r = crear(H_PROF, E_1A, LENGUA, periodo=1, aspectos="Con permiso")
        assert r.status_code == 200, (r.status_code, r.text[:250])
    finally:
        set_periodo_cerrado(1, False)
        d = SessionLocal()
        try:
            for p in d.query(M.PermisoTemporalCalificacion).all():
                d.delete(p)
            d.commit()
        finally:
            d.close()


# ═══════════════════ I · RECUPERACION FINAL Y ESPECIAL ═══════════════════

def _sembrar_area_reprobada(est, asig):
    """Deja las 3 competencias con CF < 65 para que nazca la ficha final."""
    for comp in (1, 2, 3):
        calificar(H_PROF, est, asig, comp=comp, p1=50, p2=50, p3=50, p4=50)
    return client.get("/api/recuperaciones-primaria/pendientes", headers=H_DIR)


@test("I1 en 1ro la Recuperacion FINAL sigue existiendo")
def _():
    r = _sembrar_area_reprobada(E_1A, MUSICA)
    assert r.status_code == 200, r.text[:200]
    mias = [p for p in r.json()["pendientes"]
            if p["estudiante_id"] == E_1A and p["asignatura_id"] == MUSICA]
    assert len(mias) == 1, r.json()["pendientes"]
    assert mias[0]["fase_pendiente"] == "final", mias[0]
    assert mias[0]["admite_especial"] is False, mias[0]
    q = client.post("/api/recuperaciones-primaria", headers=H_PROF, json={
        "estudiante_id": E_1A, "asignatura_id": MUSICA, "tipo": "final", "puntos": 5})
    assert q.status_code == 200, (q.status_code, q.text[:250])


@test("I2 en 1ro NO se ofrece recuperacion especial aunque la final no alcance")
def _():
    # La final dejo el area en 55: en 3ro-6to eso abriria la especial.
    r = client.get("/api/recuperaciones-primaria/pendientes", headers=H_DIR)
    mias = [p for p in (r.json()["pendientes"] + r.json()["resueltas"])
            if p["estudiante_id"] == E_1A and p["asignatura_id"] == MUSICA]
    assert len(mias) == 1, mias
    assert mias[0]["fase_pendiente"] is None, mias[0]
    assert mias[0]["admite_especial"] is False, mias[0]


@test("I3 POST manipulado con tipo='especial' en 1ro -> rechazo")
def _():
    q = client.post("/api/recuperaciones-primaria", headers=H_PROF, json={
        "estudiante_id": E_1A, "asignatura_id": MUSICA, "tipo": "especial", "puntos": 5})
    assert q.status_code == 400, (q.status_code, q.text[:250])
    assert "especial" in q.json()["error"].lower()
    d = SessionLocal()
    try:
        f = d.query(M.RecuperacionPrimaria).filter_by(
            estudiante_id=E_1A, asignatura_id=MUSICA).first()
        assert f.puntos_especial is None, "se guardo una especial que no existe"
    finally:
        d.close()


@test("I4 en 4to la recuperacion especial sigue igual que antes")
def _():
    for comp in (1, 2, 3):
        calificar(H_PROF, E_4A, MATE, comp=comp, p1=40, p2=40, p3=40, p4=40)
    d = SessionLocal()
    try:
        d.add(_asig(COL_A, PROF, CUR_4A, MATE, ANO_A))
        d.commit()
    finally:
        d.close()
    for comp in (1, 2, 3):
        calificar(H_PROF, E_4A, MATE, comp=comp, p1=40, p2=40, p3=40, p4=40)
    client.get("/api/recuperaciones-primaria/pendientes", headers=H_DIR)
    q = client.post("/api/recuperaciones-primaria", headers=H_PROF, json={
        "estudiante_id": E_4A, "asignatura_id": MATE, "tipo": "final", "puntos": 10})
    assert q.status_code == 200, (q.status_code, q.text[:250])
    r = client.get("/api/recuperaciones-primaria/pendientes", headers=H_DIR)
    mias = [p for p in r.json()["pendientes"]
            if p["estudiante_id"] == E_4A and p["asignatura_id"] == MATE]
    assert len(mias) == 1 and mias[0]["fase_pendiente"] == "especial", mias
    assert mias[0]["admite_especial"] is True, mias[0]
    e = client.post("/api/recuperaciones-primaria", headers=H_PROF, json={
        "estudiante_id": E_4A, "asignatura_id": MATE, "tipo": "especial", "puntos": 15})
    assert e.status_code == 200, (e.status_code, e.text[:250])


# ═══════════════════ J · MATERIAS INTERNAS ═══════════════════

@test("J1 una materia interna de 1ro puede registrar cualitativa")
def _():
    # Musica no es area oficial MINERD y aun asi el colegio la evalua.
    r = crear(H_PROF, E_1A, MUSICA, periodo=1, aspectos="No sigue el pulso")
    assert r.status_code == 200, (r.status_code, r.text[:250])
    assert fila(r.json()["id"]).asignatura_id == MUSICA


@test("J2 la regla es generica, no una excepcion por nombre de materia")
def _():
    import inspect
    src = inspect.getsource(APP._modalidad_recuperacion_primaria)
    src += inspect.getsource(APP.crear_recuperacion_cualitativa)
    for palabra in ("ingl", "musica", "música", "frances", "francés", "informatica"):
        assert palabra not in src.lower(), f"la lógica nombra '{palabra}'"


@test("J3 esta fase NO mete la materia interna en el Registro MINERD")
def _():
    from registro_primaria import area_canonica
    assert area_canonica("Musica") is None, "Musica no es area oficial"
    import inspect
    src = inspect.getsource(APP._construir_areas_primaria)
    assert "RecuperacionPedagogicaPrimaria" not in src, \
        "el boletin no debe consumir la tabla cualitativa en esta fase"
    import registro_primaria as RP
    assert "RecuperacionPedagogicaPrimaria" not in inspect.getsource(RP), \
        "el Registro no debe consumir la tabla cualitativa en esta fase"


# ═══════════════════ K · MULTINIVEL ═══════════════════

@test("K1 profesor de Primaria y Secundaria: sin cruces")
def _():
    # En su curso de 1ro puede; en el de Secundaria el endpoint ni aplica.
    assert crear(H_MULTI, E_1A, LENGUA, aspectos="Multinivel ok").status_code == 200
    assert contexto(H_MULTI, CUR_SEC).status_code == 400
    # Y no ve el curso de 4to, donde no tiene asignacion.
    assert listar(H_MULTI, CUR_4A, LENGUA).status_code == 409


# ═══════════════════ L · REGRESIONES ═══════════════════

@test("L1 P1: las protecciones de calificaciones siguen en pie")
def _():
    # rango, tipo y booleanos
    assert calificar(H_PROF, E_1A, LENGUA, p1=150).status_code == 400
    assert calificar(H_PROF, E_1A, LENGUA, p1="abc").status_code == 400
    assert calificar(H_PROF, E_1A, LENGUA, p1=True).status_code == 400
    # asignacion exacta
    assert calificar(H_OTRA, E_1A, LENGUA, p1=80).status_code == 403
    # nivel del curso
    assert calificar(H_MULTI, E_1A, LENGUA, p1=80).status_code == 200


@test("L2 la lectura de calificaciones-primaria sigue igual y trae la modalidad")
def _():
    r = client.get(f"/api/calificaciones-primaria/curso/{CUR_1A}/asignatura/{LENGUA}",
                   headers=H_PROF)
    assert r.status_code == 200, r.text[:200]
    j = r.json()
    for k in ("calificaciones", "num_competencias", "asignatura", "grado", "ciclo",
              "ano_escolar", "periodo_activo"):
        assert k in j, f"falta {k} en la respuesta de P1"
    assert j["modalidad_recuperacion"] == "cualitativa"
    r4 = client.get(f"/api/calificaciones-primaria/curso/{CUR_4A}/asignatura/{LENGUA}",
                    headers=H_PROF)
    assert r4.json()["modalidad_recuperacion"] == "cuantitativa"


@test("L3 RecuperacionPrimaria (final) conserva su modelo y su unicidad")
def _():
    assert M.RecuperacionPrimaria.__tablename__ == "recuperaciones_primaria"
    nombres = {c.name for c in M.RecuperacionPrimaria.__table__.constraints
               if getattr(c, "name", None)}
    assert "uq_recuperacion_primaria" in nombres, nombres
    # y la tabla nueva NO tiene unicidad: varias intervenciones son validas
    uqs = [c for c in M.RecuperacionPedagogicaPrimaria.__table__.constraints
           if c.__class__.__name__ == "UniqueConstraint"]
    assert uqs == [], uqs


@test("L4 el boletin de primaria sigue construyendose igual")
def _():
    r = client.get(f"/api/boletines-primaria/estudiante/{E_1A2}", headers=H_DIR)
    assert r.status_code == 200, r.text[:250]
    j = r.json()
    assert j["nivel"] == "primaria" and j["minimo_aprobatorio"] == 65
    assert isinstance(j.get("areas"), list)


@test("L5 el Registro de primaria no aprendio nada nuevo en esta fase")
def _():
    import registro_primaria as RP
    assert set(RP.ACTA_CAL[1]["areas"].keys()) == set(RP.ACTA_CAL[2]["areas"].keys())
    for g in (1, 2):
        una = next(iter(RP.ACTA_CAL[g]["areas"].values()))
        assert una["rec_especial"] is None, f"{g}o no debe tener recuperacion especial"
    for g in (3, 4):
        una = next(iter(RP.ACTA_CAL[g]["areas"].values()))
        assert una["rec_especial"] is not None, f"{g}o si tiene recuperacion especial"


@test("L6 Horarios y Asistencia no se tocaron")
def _():
    import inspect
    assert "RecuperacionPedagogicaPrimaria" not in inspect.getsource(APP._guard_asistencia)
    assert hasattr(APP, "_horario_bloqueado"), "H2-B3 sigue en su sitio"
    assert hasattr(APP, "_titulares_del_curso"), "P3.1 sigue en su sitio"


@test("L7 la tabla nueva nace vacia y con sus indices")
def _():
    from sqlalchemy import inspect as sa_inspect
    insp = sa_inspect(engine)
    assert "recuperaciones_pedagogicas_primaria" in insp.get_table_names()
    idx = {i["name"] for i in insp.get_indexes("recuperaciones_pedagogicas_primaria")}
    assert "ix_recped_prim_curso" in idx and "ix_recped_prim_estudiante" in idx, idx


print(f"\n{B}{'=' * 62}{X}")
if _fail:
    print(f"{R}{B}  {len(_fail)} FALLO(S) de {_total}{X}")
    for n, e in _fail:
        print(f"{R}   - {n}: {e}{X}")
    sys.exit(1)
print(f"{G}{B}  {_ok}/{_total} pruebas pasaron{X}")
print(f"{B}{'=' * 62}{X}")
