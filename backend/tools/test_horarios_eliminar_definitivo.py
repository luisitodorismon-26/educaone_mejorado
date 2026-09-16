# -*- coding: utf-8 -*-
"""
EducaOne H2-B3 — eliminar definitivamente un horario retirado.

POR QUE EXISTE
    H2-B2 quito el borrado fisico porque de los cuatro horarios borrados en
    produccion no se puede saber que clase eran. Pero un bloque que Direccion
    sabe que no volvera no tiene por que quedarse para siempre en la lista de
    retirados. Esta ruta lo borra de verdad — y solo ella.

QUE PROTEGE ESTA SUITE
    Que el borrado no pueda ocurrir por accidente ni llevarse historia por
    delante. Cuatro cosas tienen que pasar antes: mismo colegio, ya retirado, el
    id confirmado a proposito, y nada ya registrado que apunte al bloque. Si
    falta una, no se borra y la fila sigue entera.

    La auditoria de referencias midio el esquema completo: cero foreign keys
    hacia `horarios`, y una sola columna en toda la base que guarda un id de
    horario — `sesiones_no_impartidas.horario_id`. Esa es la que bloquea.

Uso:
    cd backend
    python tools/test_horarios_eliminar_definitivo.py
"""
import os
import sys
import atexit
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TMPDIR = tempfile.mkdtemp(prefix="eo_h2b3_")
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
#   Los ids imitan el grupo legacy real 62-69: borrar el 64 no puede rozar al
#   63 ni al 65.
# --------------------------------------------------------------------------
PWD = "Prueba2026x"
COL_A, COL_B = 1, 2
ANO_A, ANO_B = 1, 2
CUR_SEC, CUR_PRI, CUR_B = 10, 11, 20
MAT, LEN, MAT_B = 1, 2, 90
PROF, DIR_A, COORD, DIR_B = 31, 34, 35, 81
E_SEC = 50

H_ACTIVO = 60            # activo: no se puede borrar sin retirar antes
H_CON_S1 = 61            # retirado pero con una sesion S1 que lo nombra
H_62, H_63, H_64, H_65 = 62, 63, 64, 65   # grupo retirado, sin referencias
H_LIBRE = 66             # bloque sin curso, retirado
H_B = 690                # del colegio B, retirado

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
        d.add(M.Grado(id=99, colegio_id=COL_B, nombre="3ro", nivel="secundaria", orden=3))
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
                                       (COORD, COL_A, "coord", "coordinador", "primaria"),
                                       (DIR_B, COL_B, "dirb", "direccion", None)):
            u = M.Usuario(id=uid, colegio_id=col, username=un, nombre=un,
                          apellido="T", role=rol, activo=True)
            u.set_password(PWD)
            if niv:
                u.nivel_asignado = niv
            d.add(u)
        for apid, cur, asig in ((100, CUR_SEC, MAT), (101, CUR_PRI, MAT),
                                (102, CUR_SEC, LEN)):
            d.add(M.AsignacionProfesor(id=apid, colegio_id=COL_A, profesor_id=PROF,
                                       curso_id=cur, asignatura_id=asig,
                                       ano_escolar_id=ANO_A, activo=True))
        d.add(M.Estudiante(id=E_SEC, colegio_id=COL_A, nombre="Est", apellido="T",
                           curso_id=CUR_SEC, activo=True, no_lista=1))

        def H(hid, col, cur, asig, ini, fin, act, tipo="clase"):
            d.add(M.Horario(id=hid, colegio_id=col, profesor_id=PROF if col == COL_A else DIR_B,
                            curso_id=cur, asignatura_id=asig, dia=DIA, hora_inicio=ini,
                            hora_fin=fin, tipo_bloque=tipo, activo=act, aula="A1"))

        H(H_ACTIVO, COL_A, CUR_SEC, MAT, "08:00", "08:45", True)
        H(H_CON_S1, COL_A, CUR_SEC, LEN, "09:00", "09:45", False)
        for hid in (H_62, H_63, H_64, H_65):
            H(hid, COL_A, CUR_SEC, MAT, "10:00", "10:45", False)
        H(H_LIBRE, COL_A, None, None, "11:00", "11:45", False, "libre")
        H(H_B, COL_B, CUR_B, MAT_B, "08:00", "08:45", False)

        # historia academica que el borrado no puede rozar
        d.add(M.Asistencia(colegio_id=COL_A, estudiante_id=E_SEC, curso_id=CUR_SEC,
                           asignatura_id=MAT, fecha=date(2026, 9, 7),
                           estado="presente", registrado_por=PROF))
        d.add(M.CalificacionSecundaria(colegio_id=COL_A, estudiante_id=E_SEC,
                                       asignatura_id=MAT, ano_escolar_id=ANO_A,
                                       competencia_numero=1, p1=88.0))
        d.add(M.ReporteConducta(colegio_id=COL_A, estudiante_id=E_SEC,
                                reportado_por=PROF, tipo="leve", titulo="R",
                                descripcion="x", fecha=date(2026, 9, 7)))
        # la UNICA referencia persistida a un horario en todo el esquema
        d.add(M.SesionNoImpartida(
            id=1, colegio_id=COL_A, fecha=date(2026, 9, 7), curso_id=CUR_SEC,
            asignatura_id=LEN, profesor_id=PROF, horario_id=H_CON_S1,
            dia_semana_snapshot=DIA, hora_inicio_snapshot="09:00",
            hora_fin_snapshot="09:45", motivo_codigo="REUNION",
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
            'id': h.id, 'colegio_id': h.colegio_id, 'profesor_id': h.profesor_id,
            'curso_id': h.curso_id, 'asignatura_id': h.asignatura_id, 'dia': h.dia,
            'hora_inicio': h.hora_inicio, 'hora_fin': h.hora_fin, 'aula': h.aula,
            'tipo_bloque': h.tipo_bloque, 'activo': bool(h.activo),
        }
    finally:
        d.close()


def _ids_horarios():
    d = SessionLocal()
    try:
        return sorted(h.id for h in d.query(M.Horario).all())
    finally:
        d.close()


def _foto_academica():
    d = SessionLocal()
    try:
        return {n: d.query(m).count() for n, m in (
            ("asignaciones", M.AsignacionProfesor), ("asistencias", M.Asistencia),
            ("calif_sec", M.CalificacionSecundaria), ("reportes", M.ReporteConducta),
            ("estudiantes", M.Estudiante), ("sesiones_s1", M.SesionNoImpartida))}
    finally:
        d.close()


def _n_aud(accion):
    d = SessionLocal()
    try:
        return d.query(M.LogAuditoria).filter_by(accion=accion).count()
    finally:
        d.close()


_seed()
H_DIR, H_PROF_T, H_COORD, H_DIRB = (_tok("dir"), _tok("prof"),
                                    _tok("coord"), _tok("dirb"))
ACC = 'ELIMINAR_HORARIO_DEFINITIVO'


def borrar(hid, confirmar="mismo", hdr=None):
    cuerpo = {"confirmar_id": hid if confirmar == "mismo" else confirmar}
    return client.post(f"/api/horarios/{hid}/eliminar-definitivo",
                       headers=hdr or H_DIR, json=cuerpo)


# ==========================================================================
# A–C — LAS CONDICIONES
# ==========================================================================
@test("A  un horario ACTIVO no se elimina: primero hay que retirarlo")
def _():
    _seed()
    antes = _fila(H_ACTIVO)
    r = borrar(H_ACTIVO)
    assert r.status_code == 409, (r.status_code, r.text[:250])
    assert r.json()["error"] == "Retire primero el horario."
    assert _fila(H_ACTIVO) == antes, "la fila activa fue tocada"
    assert _n_aud(ACC) == 0, "audito un borrado que no ocurrio"


@test("B  un retirado sin referencias se elimina de verdad")
def _():
    _seed()
    n = _n_aud(ACC)
    r = borrar(H_64)
    assert r.status_code == 200, (r.status_code, r.text[:250])
    assert _fila(H_64) is None, "la fila sigue ahi: no se borro"
    assert H_64 not in _ids_horarios()
    assert _n_aud(ACC) == n + 1
    # ya no aparece entre los retirados
    rr = client.get("/api/horarios/retirados", headers=H_DIR)
    assert H_64 not in {h["id"] for h in rr.json()}


@test("C  confirmar el ID equivocado no elimina nada")
def _():
    _seed()
    antes = _fila(H_64)
    # Otro id, un id inventado, nada, un cero, un decimal que al truncarse
    # acertaria, y un booleano (que en Python vale 1).
    for malo in (H_63, 999999, None, 0, 64.9, "64.0", "", True):
        r = borrar(H_64, confirmar=malo)
        assert r.status_code == 400, (malo, r.status_code, r.text[:200])
        assert "Confirme el ID" in r.json()["error"], malo
        assert _fila(H_64) == antes, ("se borro con confirmacion", malo)
    # y el 63, cuyo id se uso como confirmacion equivocada, tampoco se tocó
    assert _fila(H_63) is not None
    assert _n_aud(ACC) == 0


@test("C3 el id correcto como cadena SÍ vale: un formulario manda texto")
def _():
    _seed()
    # Decision deliberada: "64" es el id correcto dicho en otro tipo, no una
    # confirmacion equivocada. Rechazarlo seria un 400 incomprensible.
    r = borrar(H_64, confirmar="64")
    assert r.status_code == 200, (r.status_code, r.text[:200])
    assert _fila(H_64) is None


@test("C2 sin cuerpo, o con cuerpo vacío, tampoco elimina")
def _():
    _seed()
    antes = _fila(H_64)
    for kw in ({}, {"json": {}}, {"json": {"confirmar_id": None}}):
        r = client.post(f"/api/horarios/{H_64}/eliminar-definitivo",
                        headers=H_DIR, **kw)
        assert r.status_code == 400, (kw, r.status_code, r.text[:200])
    assert _fila(H_64) == antes
    assert _n_aud(ACC) == 0


# ==========================================================================
# D–F — QUIEN PUEDE
# ==========================================================================
@test("D  otro colegio recibe 404 y no toca nada")
def _():
    _seed()
    antes = _fila(H_64)
    r = borrar(H_64, hdr=H_DIRB)
    assert r.status_code == 404, (r.status_code, r.text[:200])
    assert _fila(H_64) == antes
    # y el de B tampoco se borra desde A
    assert borrar(H_B, hdr=H_DIR).status_code == 404
    assert _fila(H_B) is not None
    assert _n_aud(ACC) == 0


@test("E  un profesor no puede eliminar")
def _():
    _seed()
    antes = _fila(H_64)
    r = borrar(H_64, hdr=H_PROF_T)
    assert r.status_code == 403, (r.status_code, r.text[:200])
    assert _fila(H_64) == antes
    assert _n_aud(ACC) == 0


@test("F  un coordinador tampoco: sigue siendo solo Direccion")
def _():
    _seed()
    antes = _fila(H_64)
    r = borrar(H_64, hdr=H_COORD)
    assert r.status_code == 403, (r.status_code, r.text[:200])
    assert _fila(H_64) == antes
    assert _n_aud(ACC) == 0


# ==========================================================================
# G — LA HISTORIA MANDA
# ==========================================================================
@test("G  un horario con una sesión S1 queda retirado, no se borra")
def _():
    _seed()
    antes = _fila(H_CON_S1)
    r = borrar(H_CON_S1)
    assert r.status_code == 409, (r.status_code, r.text[:300])
    assert r.json()["error"] == ('Este horario está vinculado a información '
                                 'histórica y debe permanecer retirado.')
    assert "sesión" in " ".join(r.json().get("referencias", [])).lower()
    assert _fila(H_CON_S1) == antes, "se borro pese a la historia"
    assert _n_aud(ACC) == 0

    # la sesion S1 sigue intacta, con su puntero
    d = SessionLocal()
    try:
        s = d.get(M.SesionNoImpartida, 1)
        assert s is not None and s.horario_id == H_CON_S1
        assert s.activo is True and s.hora_inicio_snapshot == "09:00"
    finally:
        d.close()


@test("G2 NO se pone el puntero a NULL para poder borrar")
def _():
    _seed()
    borrar(H_CON_S1)
    d = SessionLocal()
    try:
        assert d.get(M.SesionNoImpartida, 1).horario_id == H_CON_S1, (
            "el endpoint desató el puntero en vez de rechazar")
    finally:
        d.close()


@test("G3 el bloqueo cae en cuanto la sesión S1 deja de apuntarlo")
def _():
    _seed()
    assert borrar(H_CON_S1).status_code == 409
    d = SessionLocal()
    try:   # Dirección borra la sesión S1 por su propia vía, no esta
        d.query(M.SesionNoImpartida).filter_by(id=1).delete()
        d.commit()
    finally:
        d.close()
    assert borrar(H_CON_S1).status_code == 200
    assert _fila(H_CON_S1) is None


# ==========================================================================
# H–I — AUDITORÍA
# ==========================================================================
@test("H  la auditoría guarda la ficha completa del bloque que desaparece")
def _():
    _seed()
    foto = _fila(H_64)
    assert borrar(H_64).status_code == 200
    d = SessionLocal()
    try:
        log = d.query(M.LogAuditoria).filter_by(accion=ACC).order_by(
            M.LogAuditoria.id.desc()).first()
        assert log is not None, "no se audito"
        assert log.usuario_id == DIR_A and log.colegio_id == COL_A
        assert log.registro_id == H_64 and log.tabla == 'horarios'
        assert log.fecha is not None
        det = log.detalles or ''
        for esperado in ("'id': %d" % H_64, "'colegio_id': %d" % COL_A,
                         "'profesor_id': %d" % PROF, "'curso_id': %d" % CUR_SEC,
                         "'asignatura_id': %d" % MAT, "'dia': 'Lunes'",
                         "'hora_inicio': '10:00'", "'hora_fin': '10:45'",
                         "'aula': 'A1'", "'tipo_bloque': 'clase'",
                         "'activo': False"):
            assert esperado in det, (esperado, det[:500])
        # el log sobrevive al borrado: es lo unico que queda del bloque
        assert d.get(M.Horario, H_64) is None
    finally:
        d.close()
    assert foto is not None


@test("I  si el delete falla, NO queda una auditoría falsa")
def _():
    _seed()
    n = _n_aud(ACC)
    orig = APP.Session.delete if hasattr(APP, 'Session') else None
    import sqlalchemy.orm as _orm
    real = _orm.Session.delete

    def revienta(self, obj):
        raise RuntimeError("fallo simulado del delete")

    _orm.Session.delete = revienta
    try:
        try:
            borrar(H_64)
        except Exception:
            pass   # el endpoint relanza; lo que importa es el estado
    finally:
        _orm.Session.delete = real
        if orig is not None:
            pass

    assert _fila(H_64) is not None, "la fila se borro pese al fallo"
    assert _n_aud(ACC) == n, "quedo una auditoria de un borrado que no ocurrio"


# ==========================================================================
# J–N — NADA MÁS SE MUEVE
# ==========================================================================
@test("J  las asignaciones quedan intactas")
def _():
    _seed()
    d = SessionLocal()
    try:
        antes = sorted((a.id, a.profesor_id, a.curso_id, a.asignatura_id,
                        bool(a.activo)) for a in d.query(M.AsignacionProfesor).all())
    finally:
        d.close()
    assert borrar(H_64).status_code == 200
    assert borrar(H_LIBRE).status_code == 200
    d = SessionLocal()
    try:
        despues = sorted((a.id, a.profesor_id, a.curso_id, a.asignatura_id,
                          bool(a.activo)) for a in d.query(M.AsignacionProfesor).all())
    finally:
        d.close()
    assert despues == antes


@test("K/L/M  notas, asistencias, reportes y estudiantes no cambian")
def _():
    _seed()
    antes = _foto_academica()
    assert borrar(H_64).status_code == 200
    assert borrar(H_65).status_code == 200
    despues = _foto_academica()
    assert despues == antes, {k: (antes[k], despues[k])
                              for k in antes if antes[k] != despues[k]}


@test("N  eliminar el 64 no roza al 62, 63 ni 65")
def _():
    _seed()
    vecinos = {h: _fila(h) for h in (H_62, H_63, H_65)}
    assert borrar(H_64).status_code == 200
    assert _fila(H_64) is None
    for h, foto in vecinos.items():
        assert _fila(h) == foto, ("se movio el vecino", h)
    assert _ids_horarios() == sorted([H_ACTIVO, H_CON_S1, H_62, H_63, H_65,
                                      H_LIBRE, H_B])


@test("N2 borrar dos veces el mismo id: el segundo es 404, no un borrado raro")
def _():
    _seed()
    assert borrar(H_64).status_code == 200
    r = borrar(H_64)
    assert r.status_code == 404, (r.status_code, r.text[:200])
    assert _ids_horarios() == sorted([H_ACTIVO, H_CON_S1, H_62, H_63, H_65,
                                      H_LIBRE, H_B])


# ==========================================================================
# O–P — EL RESTO DEL CONTRATO
# ==========================================================================
@test("O  el DELETE antiguo sigue deshabilitado")
def _():
    _seed()
    for hid, esperado in ((H_ACTIVO, 403), (H_64, 403), (H_B, 404), (999999, 404)):
        r = client.request("DELETE", f"/api/horarios/{hid}", headers=H_DIR)
        assert r.status_code == esperado, (hid, r.status_code, r.text[:200])
    assert _fila(H_64) is not None and _fila(H_ACTIVO) is not None
    # y no se cuela como via de borrado definitivo
    assert _n_aud(ACC) == 0


@test("P  tras borrar, se puede crear un horario equivalente por el flujo normal")
def _():
    _seed()
    viejo = _fila(H_64)
    assert borrar(H_64).status_code == 200
    r = client.post("/api/horarios", headers=H_DIR, json={
        "profesor_id": viejo["profesor_id"], "curso_id": viejo["curso_id"],
        "asignatura_id": viejo["asignatura_id"], "dia": viejo["dia"],
        "hora_inicio": viejo["hora_inicio"], "hora_fin": viejo["hora_fin"],
        "tipo_bloque": "clase", "aula": viejo["aula"]})
    # 409 seria legitimo si 62/63/65 siguieran activos; estan retirados, asi
    # que la franja esta libre y el alta tiene que salir.
    assert r.status_code == 201, (r.status_code, r.text[:250])
    nuevo = r.json()["horario"]
    assert nuevo["id"] != H_64, "reutilizo el id borrado"
    assert nuevo["dia"] == viejo["dia"] and nuevo["hora_inicio"] == viejo["hora_inicio"]
    assert nuevo["profesor_id"] == viejo["profesor_id"]
    assert nuevo["curso_id"] == viejo["curso_id"]
    assert nuevo["asignatura_id"] == viejo["asignatura_id"]
    assert _fila(nuevo["id"])["activo"] is True


@test("P2 el bloque borrado desaparece de las lecturas, no queda fantasma")
def _():
    _seed()
    assert borrar(H_64).status_code == 200
    for url in ("/api/horarios", f"/api/horarios/profesor/{PROF}",
                f"/api/horarios/curso/{CUR_SEC}", "/api/horarios/retirados"):
        r = client.get(url, headers=H_DIR)
        assert r.status_code == 200, url
        assert H_64 not in {h["id"] for h in r.json()}, url


# ==========================================================================
# Q–S — CONCURRENCIA
#   Un borrado no tiene vuelta atras, asi que no puede decidirse con un estado
#   leido hace un instante. Estas pruebas meten un cambio JUSTO entre la
#   comprobacion de tenant y la decision, que es la ventana que preocupa.
#
#   SQLite no implementa FOR UPDATE, asi que aqui no se prueba el candado: se
#   prueba que la decision se toma sobre la fila releida. El candado en si se
#   comprueba en Q compilando el SQL real contra el dialecto de PostgreSQL.
# ==========================================================================
def _interferir(accion):
    """Ejecuta `accion(sesion)` justo despues del chequeo de tenant."""
    real = APP.get_tenant_or_404

    def envuelto(*a, **k):
        r = real(*a, **k)
        otra = SessionLocal()
        try:
            accion(otra)
            otra.commit()
        finally:
            otra.close()
        return r
    return real, envuelto


@test("Q  la consulta destructiva pide bloqueo de fila y respeta el tenant")
def _():
    _seed()
    from sqlalchemy.dialects import postgresql, sqlite as _sqlite
    d = SessionLocal()
    try:
        director = d.get(M.Usuario, DIR_A)
        q = APP._horario_bloqueado(d, H_64, director)
        sql_pg = str(q.statement.compile(dialect=postgresql.dialect()))
        assert "FOR UPDATE" in sql_pg.upper(), sql_pg[-200:]
        # el bloqueo no puede alcanzar la fila de otro colegio
        assert "colegio_id" in sql_pg, sql_pg
        # y en SQLite simplemente no se emite: por eso la suite corre igual
        sql_lite = str(q.statement.compile(dialect=_sqlite.dialect()))
        assert "FOR UPDATE" not in sql_lite.upper()
    finally:
        d.close()
    # y el endpoint usa esa consulta, no una suya
    import inspect
    fuente = inspect.getsource(APP.eliminar_horario_definitivo)
    assert "_horario_bloqueado(db, id, current_user).first()" in fuente, fuente[:400]


@test("Q2 el estado se revalida DESPUÉS del bloqueo, no antes")
def _():
    _seed()
    # populate_existing() es lo que obliga a releer: sin ella SQLAlchemy
    # devolveria el objeto que ya tenia en memoria y se decidiria con el
    # estado viejo. Se comprueba sobre la funcion real.
    import inspect
    fuente = inspect.getsource(APP._horario_bloqueado)
    assert "populate_existing()" in fuente, "se tomaria el lock y se leeria en frio"
    assert "with_for_update()" in fuente
    assert "tenant_filter" in fuente


@test("Q3 el bloqueo RELEE la fila: no devuelve el estado que tenía en memoria")
def _():
    _seed()
    # Esta es la prueba que decide si `populate_existing()` sirve de algo. Con
    # dos sesiones de verdad: una lee, la otra reactiva y commitea, y la
    # primera vuelve a pedir la fila bloqueada. Sin populate_existing()
    # SQLAlchemy devolveria el objeto que ya tenia en el mapa de identidad, con
    # el activo viejo, y se borraria un bloque que acaban de reactivar.
    s1 = SessionLocal()
    try:
        director = s1.get(M.Usuario, DIR_A)
        h = s1.query(M.Horario).filter(M.Horario.id == H_64).first()
        assert h.activo is False, "punto de partida"

        s2 = SessionLocal()
        try:
            s2.query(M.Horario).filter_by(id=H_64).update({"activo": True})
            s2.commit()
        finally:
            s2.close()

        vuelto = APP._horario_bloqueado(s1, H_64, director).first()
        assert vuelto is not None
        assert vuelto.activo is True, (
            "el bloqueo devolvio el estado viejo que ya tenia en memoria")
    finally:
        s1.close()


@test("Q4 el bloqueo no alcanza la fila de otro colegio")
def _():
    _seed()
    s = SessionLocal()
    try:
        dir_a = s.get(M.Usuario, DIR_A)
        dir_b = s.get(M.Usuario, DIR_B)
        assert APP._horario_bloqueado(s, H_B, dir_a).first() is None, (
            "A puede bloquear una fila de B")
        assert APP._horario_bloqueado(s, H_64, dir_b).first() is None, (
            "B puede bloquear una fila de A")
        assert APP._horario_bloqueado(s, H_64, dir_a).first() is not None, (
            "A no puede bloquear su propia fila")
    finally:
        s.close()


@test("R  si Reactivar gana la carrera, Eliminar ve activo=True y da 409")
def _():
    _seed()
    n = _n_aud(ACC)

    def reactiva(s):
        s.query(M.Horario).filter_by(id=H_64).update({"activo": True})

    real, envuelto = _interferir(reactiva)
    APP.get_tenant_or_404 = envuelto
    try:
        r = borrar(H_64)
    finally:
        APP.get_tenant_or_404 = real

    assert r.status_code == 409, (r.status_code, r.text[:250])
    assert r.json()["error"] == "Retire primero el horario."
    f = _fila(H_64)
    assert f is not None, "borro una fila que acababan de reactivar"
    assert f["activo"] is True, "ademas la dejo en un estado raro"
    assert _n_aud(ACC) == n, "audito un borrado que no ocurrio"


@test("S  dos eliminaciones del mismo id: una gana, la otra 404 sin auditar")
def _():
    _seed()
    n = _n_aud(ACC)

    def borra_antes(s):
        s.query(M.Horario).filter_by(id=H_64).delete()

    real, envuelto = _interferir(borra_antes)
    APP.get_tenant_or_404 = envuelto
    try:
        r = borrar(H_64)     # la segunda peticion, que llega tarde
    finally:
        APP.get_tenant_or_404 = real

    assert r.status_code == 404, (r.status_code, r.text[:250])
    assert _fila(H_64) is None
    assert _n_aud(ACC) == n, "la segunda dejo una auditoria de mas"
    # y no se llevo por delante a los vecinos
    assert _ids_horarios() == sorted([H_ACTIVO, H_CON_S1, H_62, H_63, H_65,
                                      H_LIBRE, H_B])


@test("S2 si aparece historia entre la lectura y el bloqueo, tampoco borra")
def _():
    _seed()
    n = _n_aud(ACC)

    def anota_sesion(s):
        s.add(M.SesionNoImpartida(
            id=99, colegio_id=COL_A, fecha=date(2026, 9, 8), curso_id=CUR_SEC,
            asignatura_id=MAT, profesor_id=PROF, horario_id=H_64,
            dia_semana_snapshot=DIA, hora_inicio_snapshot="10:00",
            hora_fin_snapshot="10:45", motivo_codigo="REUNION",
            registrado_por=PROF, activo=True))

    real, envuelto = _interferir(anota_sesion)
    APP.get_tenant_or_404 = envuelto
    try:
        r = borrar(H_64)
    finally:
        APP.get_tenant_or_404 = real

    assert r.status_code == 409, (r.status_code, r.text[:250])
    assert _fila(H_64) is not None, "borro un bloque que acababa de recibir historia"
    assert _n_aud(ACC) == n


@test("S3 el camino feliz sigue igual tras meter el bloqueo")
def _():
    _seed()
    r = borrar(H_64)
    assert r.status_code == 200, (r.status_code, r.text[:250])
    assert _fila(H_64) is None
    assert _n_aud(ACC) == 1
    # y la sesion no queda con la transaccion abierta: otra escritura pasa
    assert borrar(H_65).status_code == 200
    assert _fila(H_65) is None


@test("P3 el repo no fue tocado: sge.db intacto")
def _():
    a = os.path.getmtime(_REPO_SGE) if os.path.exists(_REPO_SGE) else None
    assert a == _sge_mtime, "sge.db fue modificado"


print("\n" + "=" * 70)
print(f"{B}HORARIOS — ELIMINAR DEFINITIVO: {_ok}/{_total} pruebas{X}")
if _fail:
    print(f"{R}FALLARON:{X}")
    for n, e in _fail:
        print(f"  - {n}: {e}")
    sys.exit(1)
print(f"{G}TODO VERDE{X}")
