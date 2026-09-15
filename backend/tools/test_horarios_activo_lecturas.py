# -*- coding: utf-8 -*-
"""
EducaOne H2-B1 — un horario RETIRADO deja de aparecer en las lecturas.

DE DONDE SALE
    La auditoria forense H2-A midio las 13 consultas a `Horario` de app.py: nueve
    respetaban `activo` —el guard de conflictos, S1, el dashboard del profesor,
    Reemplazar Profesor, el Registro— y cuatro no. Y esas cuatro eran justo las
    lecturas principales:

        GET /api/horarios
        GET /api/horarios/profesor/{id}
        GET /api/horarios/curso/{id}
        GET /api/horarios/mi-horario-hoy

    Es decir: poner una fila en `activo=False` no la habria quitado de la
    cuadricula. El campo existia, pero retirar no significaba nada.

QUE NO CAMBIA
    Solo eso. El tenant, los roles, el lente Primaria/Secundaria, el guard de
    nivel por curso, el orden, Libre y Recreo se comportan igual que antes; esta
    suite lo fija caso por caso para que el filtro nuevo no se lleve nada por
    delante.

Uso:
    cd backend
    python tools/test_horarios_activo_lecturas.py
"""
import os
import sys
import atexit
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TMPDIR = tempfile.mkdtemp(prefix="eo_h2b1_")
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
from app import app, _conflicto_clase                          # noqa: E402

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
#   Colegio A: un curso de Secundaria y otro de Primaria.
#   PROF da clase en LOS DOS niveles (el caso que no se puede romper).
#   Cada situacion tiene su par activo/inactivo para medir el filtro.
#   Colegio B existe solo para comprobar que no se filtra nada entre tenants.
# --------------------------------------------------------------------------
PWD = "Prueba2026x"
COL_A, COL_B = 1, 2
ANO_A, ANO_B = 1, 2
CUR_SEC, CUR_PRI, CUR_B = 10, 11, 20
MAT, LEN = 1, 2
MAT_B = 90
PROF, DIR_A, COORD_PRI, DIR_B = 31, 34, 35, 81

# ids de horario: pares (activo, inactivo) por situacion
H_SEC_OK, H_SEC_NO = 501, 502          # Secundaria, clase
H_PRI_OK, H_PRI_NO = 503, 504          # Primaria, clase (mismo profesor)
H_LIBRE_OK, H_LIBRE_NO = 505, 506      # bloque libre, sin curso
H_RECREO_OK, H_RECREO_NO = 507, 508    # bloque recreo, sin curso
H_B = 590                              # del colegio B

# "hoy" en hora RD, para mi-horario-hoy
from app import today_rd                                        # noqa: E402
_DIAS = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
DIA_HOY = _DIAS[today_rd().weekday()]
DIA_OTRO = _DIAS[(today_rd().weekday() + 2) % 7]


def _seed():
    M.Base.metadata.drop_all(bind=engine)
    M.Base.metadata.create_all(bind=engine)
    d = SessionLocal()
    try:
        for col, ano, nom in ((COL_A, ANO_A, "A"), (COL_B, ANO_B, "B")):
            d.add(M.Colegio(id=col, nombre="Colegio " + nom, codigo=nom.lower(),
                            plan_primaria=True, plan_secundaria=True))
            d.add(M.AnoEscolar(id=ano, colegio_id=col, nombre="2026-2027",
                               activo=True, dias_trabajados="{}"))
        d.add(M.Grado(id=1, colegio_id=COL_A, nombre="3ro Secundaria",
                      nivel="secundaria", orden=3))
        d.add(M.Grado(id=2, colegio_id=COL_A, nombre="4to Primaria",
                      nivel="primaria", orden=40))
        d.add(M.Grado(id=99, colegio_id=COL_B, nombre="3ro Secundaria",
                      nivel="secundaria", orden=3))
        d.add(M.Curso(id=CUR_SEC, colegio_id=COL_A, nombre="A", grado_id=1,
                      ano_escolar_id=ANO_A, activo=True))
        d.add(M.Curso(id=CUR_PRI, colegio_id=COL_A, nombre="A", grado_id=2,
                      ano_escolar_id=ANO_A, activo=True))
        d.add(M.Curso(id=CUR_B, colegio_id=COL_B, nombre="A", grado_id=99,
                      ano_escolar_id=ANO_B, activo=True))
        for aid, nom, col in ((MAT, "Matematica", COL_A), (LEN, "Lengua", COL_A),
                              (MAT_B, "Matematica", COL_B)):
            d.add(M.Asignatura(id=aid, colegio_id=col, nombre=nom, codigo=str(aid),
                               area="X", area_curricular_codigo="MAT", activo=True))
        for uid, col, un, rol, niv in ((PROF, COL_A, "prof", "profesor", None),
                                       (DIR_A, COL_A, "dir", "direccion", None),
                                       (COORD_PRI, COL_A, "coord", "coordinador", "primaria"),
                                       (DIR_B, COL_B, "dirb", "direccion", None)):
            u = M.Usuario(id=uid, colegio_id=col, username=un, nombre=un,
                          apellido="T", role=rol, activo=True)
            u.set_password(PWD)
            if niv:
                u.nivel_asignado = niv
            d.add(u)
        for cur, asig in ((CUR_SEC, MAT), (CUR_PRI, MAT)):
            d.add(M.AsignacionProfesor(colegio_id=COL_A, profesor_id=PROF,
                                       curso_id=cur, asignatura_id=asig,
                                       ano_escolar_id=ANO_A, activo=True))

        def H(hid, col, prof, cur, asig, dia, ini, fin, tipo, act):
            d.add(M.Horario(id=hid, colegio_id=col, profesor_id=prof, curso_id=cur,
                            asignatura_id=asig, dia=dia, hora_inicio=ini,
                            hora_fin=fin, tipo_bloque=tipo, activo=act))

        # clase de Secundaria: par activo / retirado, MISMO dia y hora
        H(H_SEC_OK, COL_A, PROF, CUR_SEC, MAT, DIA_HOY, "08:00", "08:45", "clase", True)
        H(H_SEC_NO, COL_A, PROF, CUR_SEC, MAT, DIA_HOY, "08:00", "08:45", "clase", False)
        # clase de Primaria del MISMO profesor
        H(H_PRI_OK, COL_A, PROF, CUR_PRI, MAT, DIA_HOY, "10:00", "10:45", "clase", True)
        H(H_PRI_NO, COL_A, PROF, CUR_PRI, MAT, DIA_HOY, "10:00", "10:45", "clase", False)
        # libre y recreo: sin curso, pertenecen al profesor
        H(H_LIBRE_OK, COL_A, PROF, None, None, DIA_HOY, "11:00", "11:45", "libre", True)
        H(H_LIBRE_NO, COL_A, PROF, None, None, DIA_HOY, "12:00", "12:45", "libre", False)
        H(H_RECREO_OK, COL_A, PROF, None, None, DIA_HOY, "09:00", "09:15", "recreo", True)
        H(H_RECREO_NO, COL_A, PROF, None, None, DIA_HOY, "09:30", "09:45", "recreo", False)
        # del otro colegio
        H(H_B, COL_B, DIR_B, CUR_B, MAT_B, DIA_HOY, "08:00", "08:45", "clase", True)
        d.commit()
    finally:
        d.close()


def _tok(u):
    r = client.post("/api/auth/login", json={"username": u, "password": PWD})
    assert r.status_code == 200, (u, r.text[:200])
    return {"Authorization": "Bearer " + r.json()["token"]}


def _ids(resp):
    assert resp.status_code == 200, (resp.status_code, resp.text[:250])
    return {h["id"] for h in resp.json()}


_seed()
H_PROF, H_DIR, H_COORD, H_DIRB = (_tok("prof"), _tok("dir"),
                                  _tok("coord"), _tok("dirb"))

ACTIVOS_A = {H_SEC_OK, H_PRI_OK, H_LIBRE_OK, H_RECREO_OK}
RETIRADOS_A = {H_SEC_NO, H_PRI_NO, H_LIBRE_NO, H_RECREO_NO}


# ==========================================================================
# A–D — LAS CUATRO LECTURAS
# ==========================================================================
@test("A  GET /api/horarios: aparecen los activos, no los retirados")
def _():
    _seed()
    vistos = _ids(client.get("/api/horarios", headers=H_DIR))
    assert ACTIVOS_A <= vistos, ("faltan activos", sorted(ACTIVOS_A - vistos))
    assert not (RETIRADOS_A & vistos), ("se colo un retirado", sorted(RETIRADOS_A & vistos))


@test("B  GET /api/horarios/profesor/{id}: idem")
def _():
    _seed()
    vistos = _ids(client.get(f"/api/horarios/profesor/{PROF}", headers=H_DIR))
    assert ACTIVOS_A <= vistos, sorted(ACTIVOS_A - vistos)
    assert not (RETIRADOS_A & vistos), sorted(RETIRADOS_A & vistos)
    # y el propio profesor ve lo mismo
    suyos = _ids(client.get(f"/api/horarios/profesor/{PROF}", headers=H_PROF))
    assert ACTIVOS_A <= suyos and not (RETIRADOS_A & suyos), sorted(suyos)


@test("C  GET /api/horarios/curso/{id}: idem")
def _():
    _seed()
    vistos = _ids(client.get(f"/api/horarios/curso/{CUR_SEC}", headers=H_DIR))
    assert H_SEC_OK in vistos, "falta el activo del curso"
    assert H_SEC_NO not in vistos, "se colo el retirado del curso"


@test("D  GET /api/horarios/mi-horario-hoy: solo el dia de hoy y solo activos")
def _():
    _seed()
    vistos = _ids(client.get("/api/horarios/mi-horario-hoy", headers=H_PROF))
    assert ACTIVOS_A <= vistos, sorted(ACTIVOS_A - vistos)
    assert not (RETIRADOS_A & vistos), sorted(RETIRADOS_A & vistos)
    # un bloque activo en OTRO dia sigue sin salir: el filtro de dia no cambio
    d = SessionLocal()
    try:
        d.add(M.Horario(id=599, colegio_id=COL_A, profesor_id=PROF, curso_id=CUR_SEC,
                        asignatura_id=MAT, dia=DIA_OTRO, hora_inicio="07:00",
                        hora_fin="07:45", tipo_bloque="clase", activo=True))
        d.commit()
    finally:
        d.close()
    assert 599 not in _ids(client.get("/api/horarios/mi-horario-hoy", headers=H_PROF))


# ==========================================================================
# E–H — LO QUE NO PUEDE ROMPERSE
# ==========================================================================
@test("E  cero fuga entre colegios, en las cuatro lecturas")
def _():
    _seed()
    for url in ("/api/horarios", f"/api/horarios/profesor/{PROF}",
                f"/api/horarios/curso/{CUR_SEC}", "/api/horarios/mi-horario-hoy"):
        r = client.get(url, headers=H_DIRB)
        if r.status_code == 200:
            assert H_B not in (ACTIVOS_A | RETIRADOS_A), "sanidad del fixture"
            assert not (_ids(r) & (ACTIVOS_A | RETIRADOS_A)), (url, "fuga hacia el colegio B")
    # y el colegio A no ve el horario del B
    assert H_B not in _ids(client.get("/api/horarios", headers=H_DIR))
    r = client.get(f"/api/horarios/curso/{CUR_B}", headers=H_DIR)
    assert r.status_code == 404, (r.status_code, "un curso ajeno deberia ser 404")


@test("F  el profesor que da Primaria Y Secundaria conserva ambas")
def _():
    _seed()
    suyos = _ids(client.get(f"/api/horarios/profesor/{PROF}", headers=H_PROF))
    assert H_SEC_OK in suyos and H_PRI_OK in suyos, \
        ("el profesor perdio uno de sus niveles", sorted(suyos))
    assert H_LIBRE_OK in suyos and H_RECREO_OK in suyos, "perdio libre/recreo"


@test("G  el lente de nivel de Direccion sigue recortando igual")
def _():
    _seed()
    sec = _ids(client.get("/api/horarios", headers={**H_DIR, "X-Nivel": "secundaria"}))
    assert H_SEC_OK in sec, "falta la clase de secundaria"
    assert H_PRI_OK not in sec, "el lente secundaria no recorto primaria"
    # los bloques SIN curso se conservan siempre: pertenecen al profesor
    assert H_LIBRE_OK in sec and H_RECREO_OK in sec, "el lente se llevo libre/recreo"
    pri = _ids(client.get("/api/horarios", headers={**H_DIR, "X-Nivel": "primaria"}))
    assert H_PRI_OK in pri and H_SEC_OK not in pri, sorted(pri)
    # y en ninguno de los dos lentes entra un retirado
    assert not (RETIRADOS_A & (sec | pri)), sorted(RETIRADOS_A & (sec | pri))


@test("H  el coordinador con nivel fijo no cruza de nivel, como antes")
def _():
    _seed()
    # nivel_asignado='primaria': el header NO puede quitarle el lente
    vistos = _ids(client.get(f"/api/horarios/profesor/{PROF}",
                             headers={**H_COORD, "X-Nivel": "secundaria"}))
    assert H_PRI_OK in vistos, "perdio su propio nivel"
    assert H_SEC_OK not in vistos, "el coordinador de primaria cruzo a secundaria"
    # y el guard por curso sigue cortando el curso de otro nivel
    r = client.get(f"/api/horarios/curso/{CUR_SEC}", headers=H_COORD)
    assert r.status_code in (403, 404), (r.status_code, r.text[:200])
    # su propio curso si
    assert client.get(f"/api/horarios/curso/{CUR_PRI}", headers=H_COORD).status_code == 200


# ==========================================================================
# I–J — LIBRE Y RECREO
# ==========================================================================
@test("I  Libre y Recreo ACTIVOS se comportan igual que antes")
def _():
    _seed()
    for hdr in (H_DIR, H_PROF):
        vistos = _ids(client.get(f"/api/horarios/profesor/{PROF}", headers=hdr))
        assert H_LIBRE_OK in vistos and H_RECREO_OK in vistos, sorted(vistos)
    # conservan su tipo_bloque en la respuesta
    tipos = {h["id"]: h["tipo_bloque"]
             for h in client.get(f"/api/horarios/profesor/{PROF}", headers=H_DIR).json()}
    assert tipos[H_LIBRE_OK] == "libre" and tipos[H_RECREO_OK] == "recreo", tipos


@test("J  Libre y Recreo RETIRADOS no aparecen")
def _():
    _seed()
    for url in ("/api/horarios", f"/api/horarios/profesor/{PROF}",
                "/api/horarios/mi-horario-hoy"):
        hdr = H_PROF if "mi-horario" in url else H_DIR
        vistos = _ids(client.get(url, headers=hdr))
        assert H_LIBRE_NO not in vistos, (url, "libre retirado visible")
        assert H_RECREO_NO not in vistos, (url, "recreo retirado visible")


# ==========================================================================
# K — EL GUARD DE CONFLICTOS NO SE TOCA
# ==========================================================================
@test("K  un horario ACTIVO bloquea; uno RETIRADO no")
def _():
    _seed()
    d = SessionLocal()
    try:
        # contra el activo de las 08:00 -> choque
        choca = _conflicto_clase(d, colegio_id=COL_A, dia=DIA_HOY,
                                 hora_inicio="08:15", hora_fin="09:00",
                                 profesor_id=PROF, curso_id=CUR_SEC)
        assert choca is not None, "el guard dejo de detectar un solape real"
        assert choca.status_code == 409

        # ahora se retira el activo: el retirado NO debe bloquear nada
        d.query(M.Horario).filter_by(id=H_SEC_OK).update({"activo": False})
        d.commit()
        libre = _conflicto_clase(d, colegio_id=COL_A, dia=DIA_HOY,
                                 hora_inicio="08:15", hora_fin="09:00",
                                 profesor_id=PROF, curso_id=CUR_SEC)
        assert libre is None, "una clase retirada sigue bloqueando el horario"
    finally:
        d.close()


@test("K2 el repo no fue tocado: sge.db intacto")
def _():
    a = os.path.getmtime(_REPO_SGE) if os.path.exists(_REPO_SGE) else None
    assert a == _sge_mtime, "sge.db fue modificado"


print("\n" + "=" * 70)
print(f"{B}HORARIOS — `activo` EN LAS LECTURAS: {_ok}/{_total} pruebas{X}")
if _fail:
    print(f"{R}FALLARON:{X}")
    for n, e in _fail:
        print(f"  - {n}: {e}")
    sys.exit(1)
print(f"{G}TODO VERDE{X}")
