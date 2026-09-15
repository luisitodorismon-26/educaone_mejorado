# -*- coding: utf-8 -*-
"""
EducaOne H2-B2 — retirar un horario en vez de borrarlo.

DE DONDE SALE
    `DELETE /api/horarios/{id}` hacia `db.delete(horario)`. La fila desaparecia y
    con ella el dia, la hora, el profesor, el curso y la asignatura: la auditoria
    solo conservaba «DELETE /api/horarios/19». La reconstruccion forense de H2-A
    se topo justo con eso — de los cuatro horarios borrados en produccion no se
    puede saber que clase eran.

QUE SUSTITUYE
    Retirar pone `activo=False` y deja la fila entera. El bloque sale del horario
    actual, deja de bloquear conflictos, y puede volver. Reactivar pasa por las
    MISMAS validaciones que crear, porque el mundo pudo cambiar mientras estaba
    retirado.

LO QUE ESTA SUITE PROTEGE SOBRE TODO
    Que nada academico se mueva. Retirar un bloque de la agenda de hoy no puede
    reescribir lo que paso ayer: ni asignaciones, ni notas, ni asistencia, ni
    reportes, ni las sesiones S1 que apuntan al horario.

Uso:
    cd backend
    python tools/test_horarios_retirar_reactivar.py
"""
import os
import sys
import atexit
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TMPDIR = tempfile.mkdtemp(prefix="eo_h2b2_")
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
#   PROF da clase en Secundaria Y en Primaria: es el caso que no puede romperse.
#   Cada nivel tiene su bloque y su hueco libre para probar reactivacion.
# --------------------------------------------------------------------------
PWD = "Prueba2026x"
COL_A, COL_B = 1, 2
ANO_A, ANO_B = 1, 2
CUR_SEC, CUR_PRI, CUR_B = 10, 11, 20
MAT, LEN, MAT_B = 1, 2, 90
PROF, OTRO_PROF, DIR_A, COORD_PRI, DIR_B = 31, 32, 34, 35, 81
E_SEC = 50

H_SEC, H_PRI = 601, 602          # clases activas, una por nivel
H_LIBRE, H_RECREO = 603, 604     # bloques sin curso
H_SEC_2 = 605                    # otra clase de Secundaria, para chocar
H_B = 690                        # del colegio B

DIA = "Lunes"


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
                                       (OTRO_PROF, COL_A, "prof2", "profesor", None),
                                       (DIR_A, COL_A, "dir", "direccion", None),
                                       (COORD_PRI, COL_A, "coord", "coordinador", "primaria"),
                                       (DIR_B, COL_B, "dirb", "direccion", None)):
            u = M.Usuario(id=uid, colegio_id=col, username=un, nombre=un,
                          apellido="T", role=rol, activo=True)
            u.set_password(PWD)
            if niv:
                u.nivel_asignado = niv
            d.add(u)
        # el mismo profesor en los DOS niveles
        for apid, cur, asig in ((100, CUR_SEC, MAT), (101, CUR_PRI, MAT),
                                (102, CUR_SEC, LEN)):
            d.add(M.AsignacionProfesor(id=apid, colegio_id=COL_A, profesor_id=PROF,
                                       curso_id=cur, asignatura_id=asig,
                                       ano_escolar_id=ANO_A, activo=True))
        d.add(M.AsignacionProfesor(id=180, colegio_id=COL_B, profesor_id=DIR_B,
                                   curso_id=CUR_B, asignatura_id=MAT_B,
                                   ano_escolar_id=ANO_B, activo=True))
        d.add(M.Estudiante(id=E_SEC, colegio_id=COL_A, nombre="Est", apellido="T",
                           curso_id=CUR_SEC, activo=True, no_lista=1))

        def H(hid, col, prof, cur, asig, ini, fin, tipo="clase", act=True):
            d.add(M.Horario(id=hid, colegio_id=col, profesor_id=prof, curso_id=cur,
                            asignatura_id=asig, dia=DIA, hora_inicio=ini,
                            hora_fin=fin, tipo_bloque=tipo, activo=act, aula="A1"))

        H(H_SEC, COL_A, PROF, CUR_SEC, MAT, "08:00", "08:45")
        H(H_PRI, COL_A, PROF, CUR_PRI, MAT, "10:00", "10:45")
        H(H_SEC_2, COL_A, PROF, CUR_SEC, LEN, "14:00", "14:45")
        H(H_LIBRE, COL_A, PROF, None, None, "11:00", "11:45", "libre")
        H(H_RECREO, COL_A, PROF, None, None, "09:00", "09:15", "recreo")
        H(H_B, COL_B, DIR_B, CUR_B, MAT_B, "08:00", "08:45")

        # historia academica que NO puede moverse al retirar
        d.add(M.Asistencia(colegio_id=COL_A, estudiante_id=E_SEC, curso_id=CUR_SEC,
                           asignatura_id=MAT, fecha=date(2026, 9, 7),
                           estado="presente", registrado_por=PROF))
        d.add(M.CalificacionSecundaria(colegio_id=COL_A, estudiante_id=E_SEC,
                                       asignatura_id=MAT, ano_escolar_id=ANO_A,
                                       competencia_numero=1, p1=88.0))
        d.add(M.ReporteConducta(colegio_id=COL_A, estudiante_id=E_SEC,
                                reportado_por=PROF, tipo="leve", titulo="R",
                                descripcion="x", fecha=date(2026, 9, 7)))
        # una sesion S1 que APUNTA al horario de Secundaria
        d.add(M.SesionNoImpartida(
            id=1, colegio_id=COL_A, fecha=date(2026, 9, 7), curso_id=CUR_SEC,
            asignatura_id=MAT, profesor_id=PROF, horario_id=H_SEC,
            dia_semana_snapshot=DIA, hora_inicio_snapshot="08:00",
            hora_fin_snapshot="08:45", motivo_codigo="REUNION",
            registrado_por=PROF, activo=True))
        d.commit()
    finally:
        d.close()


def _tok(u):
    r = client.post("/api/auth/login", json={"username": u, "password": PWD})
    assert r.status_code == 200, (u, r.text[:200])
    return {"Authorization": "Bearer " + r.json()["token"]}


def _fila(hid):
    d = SessionLocal()
    try:
        h = d.get(M.Horario, hid)
        return None if h is None else {
            'id': h.id, 'profesor_id': h.profesor_id, 'curso_id': h.curso_id,
            'asignatura_id': h.asignatura_id, 'dia': h.dia,
            'hora_inicio': h.hora_inicio, 'hora_fin': h.hora_fin,
            'aula': h.aula, 'tipo_bloque': h.tipo_bloque, 'activo': bool(h.activo),
        }
    finally:
        d.close()


def _ids(r):
    assert r.status_code == 200, (r.status_code, r.text[:250])
    return {h["id"] for h in r.json()}


def _foto_academica():
    d = SessionLocal()
    try:
        return {n: d.query(m).count() for n, m in (
            ("asignaciones", M.AsignacionProfesor), ("asistencias", M.Asistencia),
            ("calif_sec", M.CalificacionSecundaria), ("reportes", M.ReporteConducta),
            ("estudiantes", M.Estudiante), ("sesiones_s1", M.SesionNoImpartida),
            ("horarios", M.Horario))}
    finally:
        d.close()


def _n_auditoria(accion):
    d = SessionLocal()
    try:
        return d.query(M.LogAuditoria).filter_by(accion=accion).count()
    finally:
        d.close()


_seed()
H_DIR, H_PROF_T, H_COORD, H_DIRB = (_tok("dir"), _tok("prof"),
                                    _tok("coord"), _tok("dirb"))
retirar = lambda hid, hdr=None: client.post(f"/api/horarios/{hid}/retirar", headers=hdr or H_DIR)
reactivar = lambda hid, hdr=None: client.post(f"/api/horarios/{hid}/reactivar", headers=hdr or H_DIR)


# ==========================================================================
# A–D — RETIRAR Y LISTAR
# ==========================================================================
@test("A  retirar: activo pasa a False y la FILA SIGUE EXISTIENDO entera")
def _():
    _seed()
    antes = _fila(H_SEC)
    r = retirar(H_SEC)
    assert r.status_code == 200, (r.status_code, r.text[:250])
    d = _fila(H_SEC)
    assert d is not None, "la fila desaparecio: eso es un borrado"
    assert d["activo"] is False
    # todo lo demas intacto: dia, horas, profesor, curso, asignatura, aula
    for k in ("profesor_id", "curso_id", "asignatura_id", "dia",
              "hora_inicio", "hora_fin", "aula", "tipo_bloque"):
        assert d[k] == antes[k], (k, antes[k], d[k])


@test("B  retirar dos veces es idempotente y no audita de mas")
def _():
    _seed()
    assert retirar(H_SEC).status_code == 200
    n = _n_auditoria('RETIRAR_HORARIO')
    r = retirar(H_SEC)
    assert r.status_code == 200, (r.status_code, r.text[:250])
    assert "ya estaba retirado" in r.json()["message"]
    assert _n_auditoria('RETIRAR_HORARIO') == n, "audito un cambio que no ocurrio"


@test("C  las lecturas de horario activo lo ocultan")
def _():
    _seed()
    retirar(H_SEC)
    for url, hdr in (("/api/horarios", H_DIR),
                     (f"/api/horarios/profesor/{PROF}", H_DIR),
                     (f"/api/horarios/curso/{CUR_SEC}", H_DIR)):
        assert H_SEC not in _ids(client.get(url, headers=hdr)), url


@test("D  GET /api/horarios/retirados lo muestra, y solo a Direccion")
def _():
    _seed()
    assert _ids(client.get("/api/horarios/retirados", headers=H_DIR)) == set()
    retirar(H_SEC)
    assert _ids(client.get("/api/horarios/retirados", headers=H_DIR)) == {H_SEC}
    for hdr, quien in ((H_PROF_T, "profesor"), (H_COORD, "coordinador")):
        assert client.get("/api/horarios/retirados", headers=hdr).status_code == 403, quien


# ==========================================================================
# E–F — REACTIVAR
# ==========================================================================
@test("E  reactivar sin conflicto devuelve el bloque al horario")
def _():
    _seed()
    retirar(H_SEC)
    r = reactivar(H_SEC)
    assert r.status_code == 200, (r.status_code, r.text[:250])
    assert _fila(H_SEC)["activo"] is True
    assert H_SEC in _ids(client.get(f"/api/horarios/profesor/{PROF}", headers=H_DIR))
    # y ya no esta en la lista de retirados
    assert _ids(client.get("/api/horarios/retirados", headers=H_DIR)) == set()


@test("F  reactivar con la franja ya ocupada -> 409 y sigue retirado")
def _():
    _seed()
    retirar(H_SEC)                       # libera las 08:00 del profesor
    # alguien ocupa ese hueco con otra clase suya
    d = SessionLocal()
    try:
        d.add(M.Horario(id=700, colegio_id=COL_A, profesor_id=PROF, curso_id=CUR_SEC,
                        asignatura_id=LEN, dia=DIA, hora_inicio="08:15",
                        hora_fin="09:00", tipo_bloque="clase", activo=True))
        d.commit()
    finally:
        d.close()
    r = reactivar(H_SEC)
    assert r.status_code == 409, (r.status_code, r.text[:250])
    assert "onflicto" in r.json()["error"]
    assert _fila(H_SEC)["activo"] is False, "se reactivo pese al conflicto"


@test("F2 reactivar sin asignacion vigente -> 409 y sigue retirado")
def _():
    _seed()
    retirar(H_SEC)
    d = SessionLocal()
    try:
        d.query(M.AsignacionProfesor).filter_by(id=100).update({"activo": False})
        d.commit()
    finally:
        d.close()
    r = reactivar(H_SEC)
    assert r.status_code == 409, (r.status_code, r.text[:250])
    assert _fila(H_SEC)["activo"] is False


@test("F3 reactivar dos veces es idempotente")
def _():
    _seed()
    retirar(H_SEC)
    assert reactivar(H_SEC).status_code == 200
    n = _n_auditoria('REACTIVAR_HORARIO')
    r = reactivar(H_SEC)
    assert r.status_code == 200 and "ya estaba activo" in r.json()["message"]
    assert _n_auditoria('REACTIVAR_HORARIO') == n


# ==========================================================================
# G–I — QUIEN PUEDE
# ==========================================================================
@test("G  un colegio no retira ni reactiva horarios del otro")
def _():
    _seed()
    antes = _fila(H_SEC)
    assert retirar(H_SEC, H_DIRB).status_code == 404
    assert reactivar(H_SEC, H_DIRB).status_code == 404
    assert _fila(H_SEC) == antes, "un colegio movio el horario de otro"
    # y el de B tampoco se toca desde A
    assert retirar(H_B, H_DIR).status_code == 404


@test("H  un profesor no puede retirar ni reactivar")
def _():
    _seed()
    antes = _fila(H_SEC)
    assert retirar(H_SEC, H_PROF_T).status_code == 403
    assert reactivar(H_SEC, H_PROF_T).status_code == 403
    assert _fila(H_SEC) == antes


@test("I  un coordinador tampoco: la politica sigue siendo solo Direccion")
def _():
    _seed()
    antes = _fila(H_SEC)
    assert retirar(H_SEC, H_COORD).status_code == 403
    assert reactivar(H_SEC, H_COORD).status_code == 403
    assert _fila(H_SEC) == antes


# ==========================================================================
# J–L — HISTORIA Y AUDITORIA
# ==========================================================================
@test("J  la sesion S1 conserva su horario_id y no queda puntero roto")
def _():
    _seed()
    retirar(H_SEC)
    d = SessionLocal()
    try:
        s = d.get(M.SesionNoImpartida, 1)
        assert s is not None, "la sesion S1 desaparecio"
        assert s.horario_id == H_SEC, "se perdio el horario_id"
        assert s.activo is True, "se toco la sesion"
        assert s.hora_inicio_snapshot == "08:00", "se toco el snapshot"
        # el horario al que apunta SIGUE existiendo: el puntero no cuelga
        assert d.get(M.Horario, s.horario_id) is not None
    finally:
        d.close()


@test("K  auditoria de RETIRAR con la ficha completa antes y despues")
def _():
    _seed()
    n = _n_auditoria('RETIRAR_HORARIO')
    assert retirar(H_SEC).status_code == 200
    assert _n_auditoria('RETIRAR_HORARIO') == n + 1
    d = SessionLocal()
    try:
        log = d.query(M.LogAuditoria).filter_by(
            accion='RETIRAR_HORARIO').order_by(M.LogAuditoria.id.desc()).first()
        assert log.usuario_id == DIR_A and log.colegio_id == COL_A
        det = log.detalles or ''
        # la ficha tiene que decir QUE clase era: eso es lo que el DELETE perdia
        for esperado in ("'dia': 'Lunes'", "'hora_inicio': '08:00'",
                         "'profesor_id': %d" % PROF, "'curso_id': %d" % CUR_SEC,
                         "'asignatura_id': %d" % MAT, "'aula': 'A1'"):
            assert esperado in det, (esperado, det[:400])
        assert "'activo': True" in det and "'activo': False" in det, det[:400]
    finally:
        d.close()


@test("L  auditoria de REACTIVAR con antes y despues")
def _():
    _seed()
    retirar(H_SEC)
    n = _n_auditoria('REACTIVAR_HORARIO')
    assert reactivar(H_SEC).status_code == 200
    assert _n_auditoria('REACTIVAR_HORARIO') == n + 1
    d = SessionLocal()
    try:
        log = d.query(M.LogAuditoria).filter_by(
            accion='REACTIVAR_HORARIO').order_by(M.LogAuditoria.id.desc()).first()
        det = log.detalles or ''
        assert "'activo': False" in det and "'activo': True" in det, det[:300]
    finally:
        d.close()


# ==========================================================================
# M–N — BORRADO FISICO Y CACHE
# ==========================================================================
@test("M  DELETE deja de borrar: 403 y la fila sigue ahi")
def _():
    _seed()
    antes = _fila(H_SEC)
    r = client.request("DELETE", f"/api/horarios/{H_SEC}", headers=H_DIR)
    assert r.status_code == 403, (r.status_code, r.text[:250])
    assert "Retirar" in r.json()["error"]
    assert _fila(H_SEC) == antes, "el DELETE toco la fila"
    # tampoco borra uno ya retirado
    retirar(H_SEC)
    assert client.request("DELETE", f"/api/horarios/{H_SEC}", headers=H_DIR).status_code == 403
    assert _fila(H_SEC) is not None


@test("N  retirar y reactivar invalidan la cache del colegio")
def _():
    _seed()
    llamadas = []
    orig = APP.cache_clear_tenant
    APP.cache_clear_tenant = lambda cid: llamadas.append(cid)
    try:
        assert retirar(H_SEC).status_code == 200
        assert llamadas == [COL_A], llamadas
        llamadas.clear()
        assert reactivar(H_SEC).status_code == 200
        assert llamadas == [COL_A], llamadas
        # un 403 no toca cache
        llamadas.clear()
        retirar(H_SEC, H_PROF_T)
        assert llamadas == [], llamadas
    finally:
        APP.cache_clear_tenant = orig


# ==========================================================================
# O–S — PRIMARIA, SECUNDARIA Y NIVELES
# ==========================================================================
@test("O  Libre y Recreo se retiran y reactivan sin exigir asignacion")
def _():
    _seed()
    for hid in (H_LIBRE, H_RECREO):
        assert retirar(hid).status_code == 200, hid
        assert _fila(hid)["activo"] is False
        assert hid not in _ids(client.get(f"/api/horarios/profesor/{PROF}", headers=H_DIR))
        # reactivar no pide asignacion: no son clase
        assert reactivar(hid).status_code == 200, hid
        assert _fila(hid)["activo"] is True


@test("P  profesor en AMBOS niveles: retirar Secundaria no toca Primaria")
def _():
    _seed()
    assert retirar(H_SEC).status_code == 200
    assert _fila(H_PRI)["activo"] is True, "se llevo por delante la clase de Primaria"
    suyos = _ids(client.get(f"/api/horarios/profesor/{PROF}", headers=H_DIR))
    assert H_PRI in suyos and H_SEC not in suyos, sorted(suyos)


@test("Q  Primaria: retirar su bloque no toca el de Secundaria")
def _():
    _seed()
    assert retirar(H_PRI).status_code == 200
    assert _fila(H_SEC)["activo"] is True, "se llevo por delante la clase de Secundaria"
    suyos = _ids(client.get(f"/api/horarios/profesor/{PROF}", headers=H_DIR))
    assert H_SEC in suyos and H_PRI not in suyos, sorted(suyos)


@test("R  Secundaria: reactivar respeta los conflictos de SU nivel")
def _():
    _seed()
    retirar(H_SEC)
    d = SessionLocal()
    try:  # ocupa la franja con otra clase de Secundaria
        d.add(M.Horario(id=701, colegio_id=COL_A, profesor_id=PROF, curso_id=CUR_SEC,
                        asignatura_id=LEN, dia=DIA, hora_inicio="08:00",
                        hora_fin="08:45", tipo_bloque="clase", activo=True))
        d.commit()
    finally:
        d.close()
    assert reactivar(H_SEC).status_code == 409
    assert _fila(H_SEC)["activo"] is False


@test("R2 Primaria: reactivar respeta los conflictos de SU nivel")
def _():
    _seed()
    retirar(H_PRI)
    d = SessionLocal()
    try:
        d.add(M.Horario(id=702, colegio_id=COL_A, profesor_id=PROF, curso_id=CUR_PRI,
                        asignatura_id=MAT, dia=DIA, hora_inicio="10:15",
                        hora_fin="11:00", tipo_bloque="clase", activo=True))
        d.commit()
    finally:
        d.close()
    assert reactivar(H_PRI).status_code == 409
    assert _fila(H_PRI)["activo"] is False


@test("S  el lente por nivel conserva su semantica con retirados de por medio")
def _():
    _seed()
    retirar(H_SEC)
    sec = _ids(client.get("/api/horarios", headers={**H_DIR, "X-Nivel": "secundaria"}))
    pri = _ids(client.get("/api/horarios", headers={**H_DIR, "X-Nivel": "primaria"}))
    assert H_SEC not in sec and H_SEC not in pri, "el retirado aparece bajo algun lente"
    assert H_SEC_2 in sec, "el lente secundaria perdio una clase activa"
    assert H_PRI in pri, "el lente primaria perdio su clase"
    # los bloques sin curso siguen en ambos: pertenecen al profesor
    assert H_LIBRE in sec and H_LIBRE in pri
    # y el coordinador de primaria sigue sin cruzar
    suyos = _ids(client.get(f"/api/horarios/profesor/{PROF}",
                            headers={**H_COORD, "X-Nivel": "secundaria"}))
    assert H_PRI in suyos and H_SEC_2 not in suyos, sorted(suyos)


# ==========================================================================
# T–U — NADA ACADEMICO SE MUEVE
# ==========================================================================
@test("T  las asignaciones quedan intactas: retirar no desactiva ni crea ninguna")
def _():
    _seed()
    d = SessionLocal()
    try:
        antes = sorted((a.id, a.profesor_id, a.curso_id, a.asignatura_id,
                        bool(a.activo), bool(a.es_titular))
                       for a in d.query(M.AsignacionProfesor).all())
    finally:
        d.close()
    retirar(H_SEC); retirar(H_PRI); reactivar(H_SEC)
    d = SessionLocal()
    try:
        despues = sorted((a.id, a.profesor_id, a.curso_id, a.asignatura_id,
                          bool(a.activo), bool(a.es_titular))
                         for a in d.query(M.AsignacionProfesor).all())
    finally:
        d.close()
    assert despues == antes, [x for x in antes if x not in despues]


@test("U  notas, asistencias, reportes y estudiantes no cambian en toda la suite")
def _():
    _seed()
    antes = _foto_academica()
    retirar(H_SEC); retirar(H_PRI); retirar(H_LIBRE)
    reactivar(H_SEC); reactivar(H_LIBRE)
    client.request("DELETE", f"/api/horarios/{H_PRI}", headers=H_DIR)
    despues = _foto_academica()
    assert despues == antes, {k: (antes[k], despues[k])
                              for k in antes if antes[k] != despues[k]}


@test("U2 un bloque retirado no se edita: primero hay que reactivarlo")
def _():
    _seed()
    retirar(H_SEC)
    r = client.put(f"/api/horarios/{H_SEC}", headers=H_DIR,
                   json={"dia": "Martes", "hora_inicio": "07:00", "hora_fin": "07:45",
                         "profesor_id": PROF, "curso_id": CUR_SEC,
                         "asignatura_id": MAT, "tipo_bloque": "clase"})
    assert r.status_code == 409, (r.status_code, r.text[:250])
    assert "Reactív" in r.json()["error"] or "eactiv" in r.json()["error"]
    d = _fila(H_SEC)
    assert d["dia"] == DIA and d["hora_inicio"] == "08:00", "el PUT toco un retirado"
    # tras reactivar, editar vuelve a funcionar EXACTAMENTE como antes
    assert reactivar(H_SEC).status_code == 200
    r = client.put(f"/api/horarios/{H_SEC}", headers=H_DIR,
                   json={"dia": "Martes", "hora_inicio": "07:00", "hora_fin": "07:45",
                         "profesor_id": PROF, "curso_id": CUR_SEC,
                         "asignatura_id": MAT, "tipo_bloque": "clase"})
    assert r.status_code == 200, (r.status_code, r.text[:250])
    assert _fila(H_SEC)["dia"] == "Martes", "la edicion normal dejo de funcionar"


# ==========================================================================
# V–W — EL NIVEL MANDA TAMBIEN EN LO RETIRADO
#   Retirar no puede convertirse en una puerta lateral por la que un nivel vea
#   o recupere lo del otro.
# ==========================================================================
@test("V  los retirados respetan el lente de nivel, igual que el listado activo")
def _():
    _seed()
    for hid in (H_SEC, H_PRI, H_LIBRE):
        assert retirar(hid).status_code == 200, hid

    sec = _ids(client.get("/api/horarios/retirados",
                          headers={**H_DIR, "X-Nivel": "secundaria"}))
    assert H_SEC in sec, "falta el retirado de Secundaria bajo su propio lente"
    assert H_PRI not in sec, "el lente Secundaria muestra un retirado de Primaria"
    assert H_LIBRE in sec, "se perdio el bloque sin curso: pertenece al profesor"

    pri = _ids(client.get("/api/horarios/retirados",
                          headers={**H_DIR, "X-Nivel": "primaria"}))
    assert H_PRI in pri, "falta el retirado de Primaria bajo su propio lente"
    assert H_SEC not in pri, "el lente Primaria muestra un retirado de Secundaria"
    assert H_LIBRE in pri, "se perdio el bloque sin curso"

    # Sin lente, Direccion los ve todos: el comportamiento institucional.
    assert _ids(client.get("/api/horarios/retirados", headers=H_DIR)) == {
        H_SEC, H_PRI, H_LIBRE}

    # Y el coordinador de Primaria tiene lente fijo: el header no se lo quita.
    # (no puede leer este endpoint, asi que se comprueba que sigue siendo 403)
    assert client.get("/api/horarios/retirados",
                      headers={**H_COORD, "X-Nivel": "secundaria"}).status_code == 403


@test("W  reactivar exige el nivel activo, igual que crear")
def _():
    _seed()
    assert retirar(H_SEC).status_code == 200

    # El colegio deja de tener Secundaria contratada. Es la misma configuracion
    # real de modulos que mira `assert_modulo_activo`.
    d = SessionLocal()
    try:
        d.query(M.Colegio).filter_by(id=COL_A).update({"plan_secundaria": False})
        d.commit()
    finally:
        d.close()

    n_aud = _n_auditoria('REACTIVAR_HORARIO')
    asig_antes = _foto_academica()

    # Crear rechazaria hoy este curso; reactivar tiene que rechazarlo igual.
    r_crear = client.post("/api/horarios", headers=H_DIR, json={
        "profesor_id": PROF, "curso_id": CUR_SEC, "asignatura_id": LEN,
        "dia": "Martes", "hora_inicio": "07:00", "hora_fin": "07:45",
        "tipo_bloque": "clase"})
    r_react = reactivar(H_SEC)
    assert r_crear.status_code == 403, (r_crear.status_code, r_crear.text[:200])
    assert r_react.status_code == r_crear.status_code, (
        "crear da %s y reactivar %s" % (r_crear.status_code, r_react.status_code))

    assert _fila(H_SEC)["activo"] is False, "volvio a un nivel que ya no esta activo"
    assert _n_auditoria('REACTIVAR_HORARIO') == n_aud, "audito una reactivacion que no ocurrio"
    assert _foto_academica() == asig_antes, "algo academico se movio"

    # Primaria sigue contratada: su retirado SI puede volver.
    assert retirar(H_PRI).status_code == 200
    assert reactivar(H_PRI).status_code == 200
    assert _fila(H_PRI)["activo"] is True

    # Y al recontratar Secundaria, el bloque vuelve sin haber perdido nada.
    d = SessionLocal()
    try:
        d.query(M.Colegio).filter_by(id=COL_A).update({"plan_secundaria": True})
        d.commit()
    finally:
        d.close()
    assert reactivar(H_SEC).status_code == 200
    f = _fila(H_SEC)
    assert f["activo"] is True and f["dia"] == DIA and f["hora_inicio"] == "08:00"


@test("W2 retirar NO exige el nivel activo: un nivel caido no atrapa bloques")
def _():
    _seed()
    d = SessionLocal()
    try:
        d.query(M.Colegio).filter_by(id=COL_A).update({"plan_secundaria": False})
        d.commit()
    finally:
        d.close()
    # Retirar solo saca del horario vigente; bloquearlo dejaria filas
    # imposibles de retirar mientras el modulo esté dado de baja.
    assert retirar(H_SEC).status_code == 200
    assert _fila(H_SEC)["activo"] is False


@test("U3 el repo no fue tocado: sge.db intacto")
def _():
    a = os.path.getmtime(_REPO_SGE) if os.path.exists(_REPO_SGE) else None
    assert a == _sge_mtime, "sge.db fue modificado"


print("\n" + "=" * 70)
print(f"{B}HORARIOS — RETIRAR / REACTIVAR: {_ok}/{_total} pruebas{X}")
if _fail:
    print(f"{R}FALLARON:{X}")
    for n, e in _fail:
        print(f"  - {n}: {e}")
    sys.exit(1)
print(f"{G}TODO VERDE{X}")
