# -*- coding: utf-8 -*-
"""
EducaOne — Direccion puede editar de verdad las fechas de SU ano escolar.

EL BUG
    La pantalla Configuracion -> Ano Escolar muestra "Fecha Inicio" y "Fecha Fin"
    y los envia en PUT /api/ano-escolar/{id}. El endpoint recorria una lista fija
    de campos donde esos dos NO estaban: se descartaban en silencio y la respuesta
    decia "Ano escolar actualizado". Direccion corregia las fechas, veia el
    mensaje verde, y no habia cambiado nada.

MULTI-COLEGIO
    Cada centro pone sus propias fechas: uno publico puede seguir el calendario
    del Ministerio y uno privado tener el suyo. Aqui no se impone ningun
    calendario. Lo unico que se exige es coherencia interna —que el ano no
    termine antes de empezar— y que un colegio no alcance el ano de otro.

Uso:
    cd backend
    python tools/test_ano_escolar_fechas.py
"""
import os
import sys
import atexit
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TMPDIR = tempfile.mkdtemp(prefix="eo_ano_put_")
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
# FIXTURE — dos colegios con calendarios DISTINTOS, como en la realidad.
#   Colegio A (publico): agosto a junio.
#   Colegio B (privado): septiembre a julio.
# Ninguno es "el correcto": son suyos.
# --------------------------------------------------------------------------
PWD = "Prueba2026x"
COL_A, COL_B = 1, 2
ANO_A, ANO_B = 1, 2
DIR_A, DIR_B, PROF_A, COORD_A = 31, 32, 33, 34
CUR_A, GRA_A, MAT = 10, 1, 1
E1 = 50

A_INI, A_FIN = date(2026, 8, 17), date(2027, 6, 25)
B_INI, B_FIN = date(2026, 9, 7), date(2027, 7, 9)

TABLAS = [
    ("estudiantes", M.Estudiante), ("cursos", M.Curso),
    ("asignaciones", M.AsignacionProfesor), ("horarios", M.Horario),
    ("asistencias", M.Asistencia),
    ("calif_secundaria", M.CalificacionSecundaria),
    ("calif_primaria", M.CalificacionPrimaria),
    ("reportes", M.ReporteConducta),
    ("historial_academico", M.HistorialAcademico),
]


def _seed():
    M.Base.metadata.drop_all(bind=engine)
    M.Base.metadata.create_all(bind=engine)
    d = SessionLocal()
    try:
        for col, nom in ((COL_A, "Publico"), (COL_B, "Privado")):
            d.add(M.Colegio(id=col, nombre="Colegio " + nom, codigo=nom.lower(),
                            plan_primaria=True, plan_secundaria=True))
        d.add(M.AnoEscolar(id=ANO_A, colegio_id=COL_A, nombre="2026-2027", activo=True,
                           fecha_inicio=A_INI, fecha_fin=A_FIN, periodo_activo=1,
                           p1_inicio=date(2026, 8, 17), p1_fin=date(2026, 10, 30),
                           dias_trabajados="{}"))
        d.add(M.AnoEscolar(id=ANO_B, colegio_id=COL_B, nombre="2026-2027", activo=True,
                           fecha_inicio=B_INI, fecha_fin=B_FIN, periodo_activo=1,
                           dias_trabajados="{}"))
        d.add(M.Grado(id=GRA_A, colegio_id=COL_A, nombre="3ro Secundaria",
                      nivel="secundaria", orden=3))
        d.add(M.Curso(id=CUR_A, colegio_id=COL_A, nombre="A", grado_id=GRA_A,
                      ano_escolar_id=ANO_A, activo=True))
        d.add(M.Asignatura(id=MAT, colegio_id=COL_A, nombre="Matematica", codigo="MAT",
                           area="X", area_curricular_codigo="MAT", activo=True))
        for uid, col, un, rol in ((DIR_A, COL_A, "dir_a", "direccion"),
                                  (DIR_B, COL_B, "dir_b", "direccion"),
                                  (PROF_A, COL_A, "prof_a", "profesor"),
                                  (COORD_A, COL_A, "coord_a", "coordinador")):
            u = M.Usuario(id=uid, colegio_id=col, username=un, nombre=un,
                          apellido="T", role=rol, activo=True)
            u.set_password(PWD)
            d.add(u)
        # datos academicos que NO deben moverse
        d.add(M.Estudiante(id=E1, colegio_id=COL_A, nombre="Alumno", apellido="T",
                           curso_id=CUR_A, activo=True, no_lista=1))
        d.add(M.AsignacionProfesor(colegio_id=COL_A, profesor_id=PROF_A, curso_id=CUR_A,
                                   asignatura_id=MAT, ano_escolar_id=ANO_A, activo=True))
        d.add(M.Horario(colegio_id=COL_A, profesor_id=PROF_A, curso_id=CUR_A,
                        asignatura_id=MAT, dia="Lunes", hora_inicio="08:00",
                        hora_fin="08:45", tipo_bloque="clase", activo=True))
        d.add(M.Asistencia(colegio_id=COL_A, estudiante_id=E1, curso_id=CUR_A,
                           asignatura_id=MAT, fecha=date(2026, 9, 7),
                           estado="presente", registrado_por=PROF_A))
        d.add(M.CalificacionSecundaria(colegio_id=COL_A, estudiante_id=E1,
                                       asignatura_id=MAT, ano_escolar_id=ANO_A,
                                       competencia_numero=1, p1=85.0))
        d.add(M.ReporteConducta(colegio_id=COL_A, estudiante_id=E1,
                                reportado_por=PROF_A, tipo="leve",
                                titulo="Reporte de prueba", descripcion="x",
                                fecha=date(2026, 9, 7)))
        d.commit()
    finally:
        d.close()


def _tok(u):
    r = client.post("/api/auth/login", json={"username": u, "password": PWD})
    assert r.status_code == 200, (u, r.text[:200])
    return {"Authorization": "Bearer " + r.json()["token"]}


def _foto_ano(ano_id):
    """Todos los campos editables del ano, para comparar antes/despues."""
    d = SessionLocal()
    try:
        a = d.get(M.AnoEscolar, ano_id)
        campos = ['nombre', 'fecha_inicio', 'fecha_fin', 'activo', 'cerrado',
                  'periodo_activo', 'dias_trabajados']
        for p in range(1, 5):
            campos += ['p%d_inicio' % p, 'p%d_fin' % p, 'p%d_cerrado' % p]
        return {c: getattr(a, c, None) for c in campos}
    finally:
        d.close()


def _foto_academica():
    d = SessionLocal()
    try:
        return {n: d.query(m).count() for n, m in TABLAS}
    finally:
        d.close()


def _n_auditoria(accion='ACTUALIZAR_ANO_ESCOLAR'):
    d = SessionLocal()
    try:
        return d.query(M.LogAuditoria).filter_by(accion=accion).count()
    finally:
        d.close()


def _put(hdr, ano_id, cuerpo):
    return client.put("/api/ano-escolar/%d" % ano_id, json=cuerpo, headers=hdr)


_seed()
H_DIR_A, H_DIR_B = _tok("dir_a"), _tok("dir_b")
H_PROF, H_COORD = _tok("prof_a"), _tok("coord_a")


# ==========================================================================
# A — LO QUE ANTES SE PERDIA EN SILENCIO
# ==========================================================================
@test("A Direccion actualiza fecha_inicio y fecha_fin, y de verdad cambian")
def _():
    _seed()
    r = _put(H_DIR_A, ANO_A, {"fecha_inicio": "2026-08-10", "fecha_fin": "2027-07-03"})
    assert r.status_code == 200, (r.status_code, r.text[:300])
    assert sorted(r.json()["campos_modificados"]) == ["fecha_fin", "fecha_inicio"]
    # el GET devuelve EXACTAMENTE lo enviado
    g = client.get("/api/ano-escolar", headers=H_DIR_A).json()
    assert g["fecha_inicio"] == "2026-08-10", g["fecha_inicio"]
    assert g["fecha_fin"] == "2027-07-03", g["fecha_fin"]
    f = _foto_ano(ANO_A)
    assert f["fecha_inicio"] == date(2026, 8, 10) and f["fecha_fin"] == date(2027, 7, 3)


@test("A2 cada colegio conserva SU calendario: tocar el de A no roza el de B")
def _():
    _seed()
    antes_b = _foto_ano(ANO_B)
    assert _put(H_DIR_A, ANO_A, {"fecha_inicio": "2026-08-10"}).status_code == 200
    assert _foto_ano(ANO_B) == antes_b, "se movio el ano del otro colegio"
    # y B pone fechas distintas sin que A se entere
    antes_a = _foto_ano(ANO_A)
    assert _put(H_DIR_B, ANO_B, {"fecha_inicio": "2026-09-01",
                                 "fecha_fin": "2027-07-15"}).status_code == 200
    assert _foto_ano(ANO_A) == antes_a


# ==========================================================================
# B-E — RANGO Y FORMATO: 400 Y CERO CAMBIOS
# ==========================================================================
@test("B fecha_inicio posterior a fecha_fin -> 400, sin tocar la fila")
def _():
    _seed()
    antes = _foto_ano(ANO_A)
    r = _put(H_DIR_A, ANO_A, {"fecha_inicio": "2027-06-01", "fecha_fin": "2026-09-01"})
    assert r.status_code == 400, (r.status_code, r.text[:300])
    assert "anterior" in r.json()["error"]
    assert _foto_ano(ANO_A) == antes


@test("C fecha_inicio igual a fecha_fin -> 400 (un ano no dura cero dias)")
def _():
    _seed()
    antes = _foto_ano(ANO_A)
    r = _put(H_DIR_A, ANO_A, {"fecha_inicio": "2026-10-05", "fecha_fin": "2026-10-05"})
    assert r.status_code == 400, (r.status_code, r.text[:300])
    assert _foto_ano(ANO_A) == antes


@test("D fecha_inicio con formato invalido -> 400, nunca 500")
def _():
    _seed()
    antes = _foto_ano(ANO_A)
    for basura in ("fecha-invalida", "17/08/2026", "2026-13-45", "0", "2026-08"):
        r = _put(H_DIR_A, ANO_A, {"fecha_inicio": basura})
        assert r.status_code == 400, (basura, r.status_code, r.text[:200])
        assert "YYYY-MM-DD" in r.json()["error"], basura
    assert _foto_ano(ANO_A) == antes


@test("E fecha_fin con formato invalido -> 400, sin cambios")
def _():
    _seed()
    antes = _foto_ano(ANO_A)
    r = _put(H_DIR_A, ANO_A, {"fecha_fin": "31-06-2027"})
    assert r.status_code == 400, (r.status_code, r.text[:300])
    assert _foto_ano(ANO_A) == antes


# ==========================================================================
# F-H — UNA SOLA FECHA, Y VACIOS
# ==========================================================================
@test("F solo fecha_inicio: se valida contra la fecha_fin GUARDADA")
def _():
    _seed()
    # A_FIN es 2027-06-25; un inicio posterior tiene que cortar
    antes = _foto_ano(ANO_A)
    r = _put(H_DIR_A, ANO_A, {"fecha_inicio": "2027-08-01"})
    assert r.status_code == 400, (r.status_code, r.text[:300])
    assert _foto_ano(ANO_A) == antes
    # uno anterior entra, y no toca fecha_fin
    r = _put(H_DIR_A, ANO_A, {"fecha_inicio": "2026-08-03"})
    assert r.status_code == 200, (r.status_code, r.text[:300])
    f = _foto_ano(ANO_A)
    assert f["fecha_inicio"] == date(2026, 8, 3) and f["fecha_fin"] == A_FIN


@test("G solo fecha_fin: se valida contra la fecha_inicio GUARDADA")
def _():
    _seed()
    antes = _foto_ano(ANO_A)
    r = _put(H_DIR_A, ANO_A, {"fecha_fin": "2026-01-01"})   # antes del inicio
    assert r.status_code == 400, (r.status_code, r.text[:300])
    assert _foto_ano(ANO_A) == antes
    r = _put(H_DIR_A, ANO_A, {"fecha_fin": "2027-07-31"})
    assert r.status_code == 200, (r.status_code, r.text[:300])
    f = _foto_ano(ANO_A)
    assert f["fecha_fin"] == date(2027, 7, 31) and f["fecha_inicio"] == A_INI


@test("H null y cadena vacia vacian la fecha, como permite el modelo")
def _():
    # No se inventa ninguna obligatoriedad institucional: un colegio puede tener
    # el ano a medio configurar. Y sin una de las dos, no hay rango que validar.
    _seed()
    r = _put(H_DIR_A, ANO_A, {"fecha_fin": None})
    assert r.status_code == 200, (r.status_code, r.text[:300])
    assert _foto_ano(ANO_A)["fecha_fin"] is None
    r = _put(H_DIR_A, ANO_A, {"fecha_inicio": ""})
    assert r.status_code == 200, (r.status_code, r.text[:300])
    assert _foto_ano(ANO_A)["fecha_inicio"] is None
    # con una sola fecha puesta y la otra vacia, sigue sin haber conflicto
    r = _put(H_DIR_A, ANO_A, {"fecha_inicio": "2026-08-17"})
    assert r.status_code == 200, (r.status_code, r.text[:300])


# ==========================================================================
# I-J — QUIEN PUEDE
# ==========================================================================
@test("I un profesor o coordinador no edita el ano escolar")
def _():
    _seed()
    antes = _foto_ano(ANO_A)
    for hdr, quien in ((H_PROF, "profesor"), (H_COORD, "coordinador")):
        r = _put(hdr, ANO_A, {"fecha_inicio": "2026-08-10"})
        assert r.status_code == 403, (quien, r.status_code, r.text[:200])
    assert _foto_ano(ANO_A) == antes


@test("J Direccion de otro colegio no alcanza el ano ajeno (404, no 403)")
def _():
    _seed()
    antes_a = _foto_ano(ANO_A)
    r = _put(H_DIR_B, ANO_A, {"fecha_inicio": "2026-01-01", "fecha_fin": "2026-12-31"})
    assert r.status_code == 404, (r.status_code, r.text[:300])
    assert _foto_ano(ANO_A) == antes_a, "un colegio movio el ano de otro"
    # el 404 no revela nada del ano ajeno
    for fuga in ("2026-2027", A_INI.isoformat(), "Publico"):
        assert fuga not in r.text, fuga


# ==========================================================================
# K-M — LO QUE YA FUNCIONABA, Y LA ATOMICIDAD
# ==========================================================================
@test("K editar el nombre sigue funcionando")
def _():
    _seed()
    r = _put(H_DIR_A, ANO_A, {"nombre": "2027-2028"})
    assert r.status_code == 200, (r.status_code, r.text[:300])
    assert _foto_ano(ANO_A)["nombre"] == "2027-2028"
    assert _foto_ano(ANO_A)["fecha_inicio"] == A_INI, "cambio una fecha sin pedirlo"


@test("L editar P1-P4 sigue funcionando, y no toca las del ano")
def _():
    _seed()
    r = _put(H_DIR_A, ANO_A, {
        "p1_inicio": "2026-08-17", "p1_fin": "2026-10-30",
        "p2_inicio": "2026-11-02", "p2_fin": "2027-01-22",
        "p3_inicio": "2027-01-25", "p3_fin": "2027-04-09",
        "p4_inicio": "2027-04-12", "p4_fin": "2027-06-25"})
    assert r.status_code == 200, (r.status_code, r.text[:300])
    f = _foto_ano(ANO_A)
    assert f["p1_inicio"] == date(2026, 8, 17) and f["p4_fin"] == date(2027, 6, 25)
    assert f["fecha_inicio"] == A_INI and f["fecha_fin"] == A_FIN


@test("M ATOMICIDAD: una fecha invalida deja SIN aplicar el nombre valido")
def _():
    _seed()
    antes = _foto_ano(ANO_A)
    r = _put(H_DIR_A, ANO_A, {"nombre": "2026-2027 CORREGIDO",
                              "fecha_inicio": "fecha-invalida",
                              "p1_fin": "2026-11-15"})
    assert r.status_code == 400, (r.status_code, r.text[:300])
    despues = _foto_ano(ANO_A)
    assert despues == antes, [k for k in antes if antes[k] != despues[k]]


@test("M2 ATOMICIDAD: un rango incoherente tampoco aplica los P1-P4 validos")
def _():
    _seed()
    antes = _foto_ano(ANO_A)
    r = _put(H_DIR_A, ANO_A, {"fecha_inicio": "2027-12-01",
                              "p2_inicio": "2026-11-02"})
    assert r.status_code == 400, (r.status_code, r.text[:300])
    assert _foto_ano(ANO_A) == antes


# ==========================================================================
# N-O — AUDITORIA
# ==========================================================================
@test("N el exito deja auditoria con antes y despues")
def _():
    _seed()
    n0 = _n_auditoria()
    r = _put(H_DIR_A, ANO_A, {"fecha_inicio": "2026-08-10", "fecha_fin": "2027-07-03"})
    assert r.status_code == 200
    assert _n_auditoria() == n0 + 1, "no se registro la auditoria"
    d = SessionLocal()
    try:
        log = d.query(M.LogAuditoria).filter_by(
            accion='ACTUALIZAR_ANO_ESCOLAR').order_by(M.LogAuditoria.id.desc()).first()
        assert log.usuario_id == DIR_A, log.usuario_id
        assert log.colegio_id == COL_A, log.colegio_id
        assert log.entidad_id == ANO_A or log.registro_id == ANO_A, (log.entidad_id, log.registro_id)
        detalle = log.detalles or ''
        for esperado in (A_INI.isoformat(), A_FIN.isoformat(),   # antes
                         "2026-08-10", "2027-07-03"):            # despues
            assert esperado in detalle, (esperado, detalle[:300])
    finally:
        d.close()


@test("O un 400 no deja ninguna auditoria de cambio")
def _():
    _seed()
    n0 = _n_auditoria()
    assert _put(H_DIR_A, ANO_A, {"fecha_inicio": "no-es-fecha"}).status_code == 400
    assert _put(H_DIR_A, ANO_A, {"fecha_inicio": "2027-12-01"}).status_code == 400
    assert _put(H_PROF, ANO_A, {"fecha_inicio": "2026-08-10"}).status_code == 403
    assert _n_auditoria() == n0, "se audito un cambio que no ocurrio"


@test("O2 guardar lo mismo que ya estaba no genera auditoria ni ruido")
def _():
    _seed()
    n0 = _n_auditoria()
    r = _put(H_DIR_A, ANO_A, {"fecha_inicio": A_INI.isoformat(),
                              "fecha_fin": A_FIN.isoformat()})
    assert r.status_code == 200, (r.status_code, r.text[:300])
    assert r.json()["message"] == "Sin cambios", r.json()
    assert _n_auditoria() == n0


# ==========================================================================
# P — CACHE
# ==========================================================================
@test("P el exito invalida la cache del colegio; el 400 no la toca")
def _():
    _seed()
    llamadas = []
    orig_tenant, orig_clear = APP.cache_clear_tenant, APP.cache_clear
    APP.cache_clear_tenant = lambda cid: llamadas.append(("tenant", cid))
    APP.cache_clear = lambda pref='': llamadas.append(("clear", pref))
    try:
        assert _put(H_DIR_A, ANO_A, {"fecha_inicio": "2026-08-10"}).status_code == 200
        assert ("tenant", COL_A) in llamadas, llamadas
        assert ("clear", "stats:%d" % COL_A) in llamadas, llamadas
        llamadas.clear()
        assert _put(H_DIR_A, ANO_A, {"fecha_inicio": "no-es-fecha"}).status_code == 400
        assert llamadas == [], llamadas
    finally:
        APP.cache_clear_tenant, APP.cache_clear = orig_tenant, orig_clear


# ==========================================================================
# Q — NADA ACADEMICO SE MUEVE
# ==========================================================================
@test("Q ninguna tabla academica cambia en toda la suite")
def _():
    _seed()
    antes = _foto_academica()
    _put(H_DIR_A, ANO_A, {"fecha_inicio": "2026-08-10", "fecha_fin": "2027-07-03"})
    _put(H_DIR_A, ANO_A, {"nombre": "otro"})
    _put(H_DIR_A, ANO_A, {"fecha_inicio": "mal"})
    _put(H_DIR_B, ANO_A, {"fecha_inicio": "2026-01-01"})
    despues = _foto_academica()
    assert despues == antes, {k: (antes[k], despues[k]) for k in antes if antes[k] != despues[k]}
    # y el ano del OTRO colegio sigue intacto
    f = _foto_ano(ANO_B)
    assert f["fecha_inicio"] == B_INI and f["fecha_fin"] == B_FIN


@test("Q2 el repo no fue tocado: sge.db intacto")
def _():
    a = os.path.getmtime(_REPO_SGE) if os.path.exists(_REPO_SGE) else None
    assert a == _sge_mtime, "sge.db fue modificado"


print("\n" + "=" * 70)
print(f"{B}ANO ESCOLAR — EDICION DE FECHAS: {_ok}/{_total} pruebas{X}")
if _fail:
    print(f"{R}FALLARON:{X}")
    for n, e in _fail:
        print(f"  - {n}: {e}")
    sys.exit(1)
print(f"{G}TODO VERDE{X}")
