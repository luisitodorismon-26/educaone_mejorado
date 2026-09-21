# -*- coding: utf-8 -*-
"""
EducaOne PRIMARIA P2A-R2 — motor academico de calificaciones.

POR QUE EXISTE
    R2 corrige cuatro cosas que estaban enredadas entre si:

      1. RP no es "el mayor entre P y RP": es LA calificacion del periodo una
         vez hecha la recuperacion. La norma dice que se asienta en su columna
         "siendo esta ultima la calificacion final del periodo".

      2. Un periodo tiene TRES estados, no dos. Un NULL significaba a la vez
         "no evaluado por causa justificada" y "todavia nadie lo cargo", y el
         sistema aplicaba siempre la regla de excepcion de NE. De ahi que en
         marzo, con tres periodos cargados, saliera una calificacion final.

      3. La CF oficial exige los CUATRO periodos resueltos. NE sale del
         divisor; PENDIENTE lo bloquea.

      4. Una recuperacion final se decide sobre la CF del area, y esa no
         existe mientras alguna competencia siga a medio evaluar.

    Cada bloque de esta suite fija una de esas cuatro y, sobre todo, la
    frontera entre NE y PENDIENTE, que es lo que hacia falta separar.

LO QUE NO ENTRA
    Secundaria, promocion, repitencia y el numero esperado de competencias
    del area (bloqueado: requiere R3). Hay casos que comprueban justamente
    que R2 no los toco.

Uso:
    cd backend
    python tools/test_primaria_motor_calculo.py
"""
import os
import sys
import atexit
import tempfile
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TMPDIR = tempfile.mkdtemp(prefix="eo_motor_")
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
def _relax_fk(c, r):
    try:
        c.execute("PRAGMA foreign_keys=OFF")
    except Exception:
        pass


engine.dispose()
M.Base.metadata.create_all(bind=engine)

from fastapi.testclient import TestClient                      # noqa: E402
import app as APP                                              # noqa: E402
from calculo_primaria import (                                 # noqa: E402
    valor_periodo_primaria, estado_periodo_primaria, cf_area,
    PERIODO_EVALUADO, PERIODO_NE, PERIODO_PENDIENTE)

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


def _modelo(**campos):
    """CalificacionPrimaria suelta, sin sesion: para probar el motor puro."""
    c = M.CalificacionPrimaria(estudiante_id=1, asignatura_id=1, competencia_numero=1)
    for k, v in campos.items():
        setattr(c, k, v)
    return c


# ══════════════════════ FIXTURE ══════════════════════
PWD = "Prueba2026x"
COL_A, COL_B = 1, 2
ANO_A, ANO_B = 1, 2
G_4TO, G_B = 14, 91
CUR_4A, CUR_B = 24, 90
LENGUA, MATE = 1, 2
ASIG_B = 9
E_1, E_2, E_B = 101, 102, 190
PROF, PROF_SIN, DIR, COORD, SECRE, PSICO, PROF_B = 301, 302, 310, 311, 312, 313, 390


def _u(uid, col, user, rol):
    x = M.Usuario(id=uid, colegio_id=col, username=user, nombre=user.title(),
                  apellido="X", role=rol, activo=True)
    x.set_password(PWD)
    return x


def fixture():
    d = SessionLocal()
    for col, cod in ((COL_A, "a"), (COL_B, "b")):
        d.add(M.Colegio(id=col, nombre=f"Col {cod}", codigo=cod, activo=True,
                        plan="premium", plan_primaria=True, plan_secundaria=True))
        d.add(M.ConfiguracionColegio(id=col, colegio_id=col, nombre=f"Col {cod}",
                                     usa_primaria=True, usa_secundaria=True))
    for ano, col in ((ANO_A, COL_A), (ANO_B, COL_B)):
        d.add(M.AnoEscolar(id=ano, colegio_id=col, nombre="2025-2026", activo=True,
                           fecha_inicio=date(2025, 9, 1), fecha_fin=date(2026, 6, 30),
                           periodo_activo=1, cerrado=False, p1_cerrado=False,
                           p2_cerrado=False, p3_cerrado=False, p4_cerrado=False))
    d.add(M.Grado(id=G_4TO, colegio_id=COL_A, nombre="4to Primaria", nivel="primaria",
                  ciclo="segundo_ciclo", orden=10))
    d.add(M.Grado(id=G_B, colegio_id=COL_B, nombre="4to Primaria", nivel="primaria",
                  ciclo="segundo_ciclo", orden=10))
    d.add(M.Curso(id=CUR_4A, colegio_id=COL_A, nombre="A", grado_id=G_4TO, ano_escolar_id=ANO_A))
    d.add(M.Curso(id=CUR_B, colegio_id=COL_B, nombre="A", grado_id=G_B, ano_escolar_id=ANO_B))
    d.add(M.Asignatura(id=LENGUA, colegio_id=COL_A, nombre="Lengua Española", codigo="LE"))
    d.add(M.Asignatura(id=MATE, colegio_id=COL_A, nombre="Matemática", codigo="MA"))
    d.add(M.Asignatura(id=ASIG_B, colegio_id=COL_B, nombre="Lengua Española", codigo="LE"))
    for eid, cur, col in ((E_1, CUR_4A, COL_A), (E_2, CUR_4A, COL_A), (E_B, CUR_B, COL_B)):
        d.add(M.Estudiante(id=eid, colegio_id=col, nombre=f"Est{eid}", apellido="P",
                           curso_id=cur, activo=True, no_lista=eid - 100))
    for uid, user, rol in ((PROF, "prof", "profesor"), (PROF_SIN, "profsin", "profesor"),
                           (DIR, "dir", "direccion"), (COORD, "coord", "coordinador"),
                           (SECRE, "secre", "secretaria"), (PSICO, "psico", "psicologia")):
        d.add(_u(uid, COL_A, user, rol))
    d.add(_u(PROF_B, COL_B, "profb", "profesor"))
    for asig in (LENGUA, MATE):
        d.add(M.AsignacionProfesor(colegio_id=COL_A, profesor_id=PROF, curso_id=CUR_4A,
                                   asignatura_id=asig, ano_escolar_id=ANO_A,
                                   activo=True, es_titular=(asig == LENGUA)))
    d.add(M.AsignacionProfesor(colegio_id=COL_B, profesor_id=PROF_B, curso_id=CUR_B,
                               asignatura_id=ASIG_B, ano_escolar_id=ANO_B, activo=True))
    d.commit()
    d.close()


fixture()


def _tok(u):
    r = client.post("/api/auth/login", json={"username": u, "password": PWD})
    assert r.status_code == 200, (u, r.text[:200])
    return {"Authorization": "Bearer " + r.json()["token"]}


H_PROF, H_SIN = _tok("prof"), _tok("profsin")
H_DIR, H_COORD = _tok("dir"), _tok("coord")
H_SECRE, H_PSICO, H_B = _tok("secre"), _tok("psico"), _tok("profb")


def guardar(hdr, est, asig, comp=1, **campos):
    cuerpo = {"estudiante_id": est, "asignatura_id": asig, "competencia_numero": comp}
    cuerpo.update(campos)
    return client.post("/api/calificaciones-primaria", headers=hdr, json=cuerpo)


def fila(est, asig, comp=1):
    d = SessionLocal()
    try:
        return d.query(M.CalificacionPrimaria).filter_by(
            estudiante_id=est, asignatura_id=asig, competencia_numero=comp).first()
    finally:
        d.close()


def set_ano(**campos):
    d = SessionLocal()
    try:
        a = d.get(M.AnoEscolar, ANO_A)
        for k, v in campos.items():
            setattr(a, k, v)
        d.commit()
    finally:
        d.close()


def limpiar_calificaciones(est=None):
    d = SessionLocal()
    try:
        q = d.query(M.CalificacionPrimaria)
        if est:
            q = q.filter_by(estudiante_id=est)
        for c in q.all():
            d.delete(c)
        for f in d.query(M.RecuperacionPrimaria).all():
            d.delete(f)
        d.commit()
    finally:
        d.close()


def n_fichas():
    d = SessionLocal()
    try:
        return d.query(M.RecuperacionPrimaria).count()
    finally:
        d.close()


# ══════════════ A · P / RP — RP REEMPLAZA A P ══════════════

@test("A1 la tabla exigida de P/RP, sobre el helper canonico")
def _():
    casos = [
        ((60, 75), 75), ((80, 50), 50), ((None, 75), 75),
        ((80, None), 80), ((None, None), None), ((0, 0), 0), ((100, 90), 90),
    ]
    for (p, rp), esperado in casos:
        obtenido = valor_periodo_primaria(p, rp)
        assert obtenido == esperado, (p, rp, obtenido, esperado)


@test("A2 el 0 es una nota, no una ausencia")
def _():
    assert valor_periodo_primaria(0, None) == 0
    assert valor_periodo_primaria(None, 0) == 0
    assert valor_periodo_primaria(90, 0) == 0, "RP=0 reemplaza igual que cualquier otra"
    assert estado_periodo_primaria(0, None) == PERIODO_EVALUADO


@test("A3 el modelo usa el mismo helper, no una copia")
def _():
    assert _modelo(p1=80, rp1=50).valor_periodo(1) == 50
    assert _modelo(p1=50, rp1=70).valor_periodo(1) == 70
    import ast, inspect, textwrap
    src = ast.unparse(ast.parse(textwrap.dedent(
        inspect.getsource(M.CalificacionPrimaria.valor_periodo))))
    assert "valor_periodo_primaria" in src, "el modelo reimplementa la regla"
    assert "max(" not in src, "queda un max() en el modelo"


@test("A4 Secundaria NO cambia: conserva su max(P, RP)")
def _():
    import ast, inspect, textwrap
    src = ast.unparse(ast.parse(textwrap.dedent(
        inspect.getsource(M.CalificacionSecundaria.valor_periodo))))
    assert "max(" in src, "R2 no debe tocar Secundaria"
    s = M.CalificacionSecundaria(estudiante_id=1, asignatura_id=1, competencia_numero=1)
    s.p1, s.rp1 = 80, 50
    assert s.valor_periodo(1) == 80, "Secundaria cambio de semantica"


# ══════════════ B · LOS TRES ESTADOS ══════════════

@test("B1 evaluado / ne / pendiente son tres cosas distintas")
def _():
    assert estado_periodo_primaria(80, None, False) == PERIODO_EVALUADO
    assert estado_periodo_primaria(None, None, True) == PERIODO_NE
    assert estado_periodo_primaria(None, None, False) == PERIODO_PENDIENTE
    assert PERIODO_NE != PERIODO_PENDIENTE


@test("B2 NULL por si solo NO es NE")
def _():
    c = _modelo()
    assert c.estado_periodo(1) == PERIODO_PENDIENTE
    assert c.es_ne(1) is False


@test("B3 una fila anterior a la migracion (NE en NULL) se lee como pendiente")
def _():
    c = _modelo()
    c.ne1 = None          # asi quedan las filas previas a R2
    assert c.es_ne(1) is False, "NULL en la columna NE no puede significar NE"
    assert c.estado_periodo(1) == PERIODO_PENDIENTE


# ══════════════ C · NE EN EL ENDPOINT ══════════════

@test("C1 marcar NE sobre una nota existente la deja en NULL")
def _():
    limpiar_calificaciones(E_1)
    assert guardar(H_PROF, E_1, LENGUA, p1=80, rp1=85).status_code == 200
    r = guardar(H_PROF, E_1, LENGUA, ne1=True)
    assert r.status_code == 200, r.text[:250]
    f = fila(E_1, LENGUA)
    assert f.es_ne(1) is True
    assert f.p1 is None and f.rp1 is None, (f.p1, f.rp1)
    assert "ajustes_ne" in r.json(), "el ajuste deberia informarse"


@test("C2 poner nota sobre un NE existente lo retira")
def _():
    f = fila(E_1, LENGUA)
    assert f.es_ne(1) is True, "precondicion de C1"
    r = guardar(H_PROF, E_1, LENGUA, p1=70)
    assert r.status_code == 200, r.text[:250]
    f = fila(E_1, LENGUA)
    assert f.es_ne(1) is False, "el NE deberia haberse retirado"
    assert f.p1 == 70


@test("C3 nota y NE en el MISMO envio no dejan un estado contradictorio")
def _():
    limpiar_calificaciones(E_1)
    r = guardar(H_PROF, E_1, LENGUA, p2=90, ne2=True)
    assert r.status_code == 200, r.text[:250]
    f = fila(E_1, LENGUA)
    # Gana la nota: NE no es un valor, es la ausencia justificada de uno.
    assert f.p2 == 90 and f.es_ne(2) is False, (f.p2, f.es_ne(2))
    assert f.estado_periodo(2) == PERIODO_EVALUADO


@test("C4 nunca persiste nota + NE a la vez, se mande como se mande")
def _():
    limpiar_calificaciones(E_1)
    for campos in ({"p3": 60, "ne3": True}, {"ne3": True, "p3": 60},
                   {"rp3": 70, "ne3": True}):
        guardar(H_PROF, E_1, LENGUA, **campos)
        f = fila(E_1, LENGUA)
        contradictorio = f.es_ne(3) and (f.p3 is not None or f.rp3 is not None)
        assert not contradictorio, (campos, f.p3, f.rp3, f.es_ne(3))


@test("C5 NE tiene que ser booleano, no una nota disfrazada")
def _():
    assert guardar(H_PROF, E_1, LENGUA, ne1="si").status_code == 400
    assert guardar(H_PROF, E_1, LENGUA, ne1=1).status_code == 400
    assert guardar(H_PROF, E_1, LENGUA, ne1=65).status_code == 400


@test("C6 periodo cerrado bloquea el NE del profesor sin permiso")
def _():
    limpiar_calificaciones(E_1)
    guardar(H_PROF, E_1, LENGUA, p4=50)
    set_ano(p4_cerrado=True)
    try:
        r = guardar(H_PROF, E_1, LENGUA, ne4=True)
        assert r.status_code == 200, r.text[:200]
        assert "periodos_cerrados_ignorados" in r.json(), r.json()
        f = fila(E_1, LENGUA)
        assert f.es_ne(4) is False and f.p4 == 50, "el NE entro en un periodo cerrado"
    finally:
        set_ano(p4_cerrado=False)


@test("C7 con permiso temporal valido el NE si entra")
def _():
    set_ano(p4_cerrado=True)
    d = SessionLocal()
    try:
        d.add(M.PermisoTemporalCalificacion(
            colegio_id=COL_A, profesor_id=PROF, periodo=4, asignatura_id=LENGUA,
            activo=True, fecha_fin=APP.now_rd() + timedelta(days=1), otorgado_por=DIR))
        d.commit()
    finally:
        d.close()
    try:
        r = guardar(H_PROF, E_1, LENGUA, ne4=True)
        assert r.status_code == 200, r.text[:250]
        f = fila(E_1, LENGUA)
        assert f.es_ne(4) is True and f.p4 is None
    finally:
        set_ano(p4_cerrado=False)
        d = SessionLocal()
        try:
            for x in d.query(M.PermisoTemporalCalificacion).all():
                d.delete(x)
            d.commit()
        finally:
            d.close()


@test("C8 un profesor sin asignacion no marca NE")
def _():
    assert guardar(H_SIN, E_1, LENGUA, ne1=True).status_code == 403


@test("C9 tenant cruzado: el NE respeta la politica de siempre")
def _():
    assert guardar(H_PROF, E_B, ASIG_B, ne1=True).status_code == 404
    assert guardar(H_B, E_1, LENGUA, ne1=True).status_code == 404


@test("C10 NE no da escritura nueva a direccion, coordinacion, secretaria ni psicologia")
def _():
    for h, quien in ((H_DIR, "direccion"), (H_COORD, "coordinacion"),
                     (H_SECRE, "secretaria"), (H_PSICO, "psicologia")):
        r = guardar(h, E_1, LENGUA, ne1=True)
        assert r.status_code == 403, (quien, r.status_code, r.text[:150])


@test("C11 NE no creo endpoint ni ruta aparte")
def _():
    rutas = [r.path for r in APP.app.routes if 'ne' in getattr(r, 'path', '').lower()]
    sospechosas = [p for p in rutas if 'no-evaluado' in p or p.endswith('/ne')]
    assert not sospechosas, sospechosas
    # Y la respuesta del endpoint de siempre expone el estado.
    limpiar_calificaciones(E_1)
    r = guardar(H_PROF, E_1, LENGUA, p1=80, ne2=True)
    cal = r.json()["calificacion"]
    for k in ("ne1", "ne2", "ne3", "ne4", "estados", "promedio_acumulado"):
        assert k in cal, (k, sorted(cal))
    assert cal["estados"]["2"] == "ne" or cal["estados"][2] == "ne", cal["estados"]


# ══════════════ D · CF OFICIAL DE COMPETENCIA ══════════════

@test("D1 cuatro periodos numericos -> CF")
def _():
    assert _modelo(p1=80, p2=80, p3=80, p4=80).calcular_final() == 80.0
    assert _modelo(p1=70, p2=80, p3=90, p4=100).calcular_final() == 85.0


@test("D2 tres numericos + uno PENDIENTE -> None")
def _():
    assert _modelo(p1=80, p2=80, p3=80).calcular_final() is None


@test("D3 uno numerico + tres PENDIENTES -> None")
def _():
    assert _modelo(p1=80).calcular_final() is None


@test("D4 tres numericos + un NE -> promedio entre 3")
def _():
    c = _modelo(p1=80, p2=80, p3=80)
    c.ne4 = True
    assert c.calcular_final() == 80.0


@test("D5 dos numericos + dos NE -> promedio entre 2")
def _():
    c = _modelo(p3=70, p4=90)
    c.ne1 = True
    c.ne2 = True
    assert c.calcular_final() == 80.0


@test("D6 un numerico + tres NE -> ese valor")
def _():
    c = _modelo(p4=77)
    c.ne1 = c.ne2 = c.ne3 = True
    assert c.calcular_final() == 77.0


@test("D7 cuatro NE -> None, porque no queda nada que promediar")
def _():
    c = _modelo()
    c.ne1 = c.ne2 = c.ne3 = c.ne4 = True
    assert c.calcular_final() is None


@test("D8 RP sustituye a P dentro del promedio")
def _():
    c = _modelo(p1=60, rp1=80, p2=80, p3=80, p4=80)
    assert c.calcular_final() == 80.0


@test("D9 una RP MENOR baja el promedio, que es lo que dice la norma")
def _():
    c = _modelo(p1=80, rp1=40, p2=80, p3=80, p4=80)
    assert c.calcular_final() == 70.0, "la RP menor no bajo el promedio"


@test("D10 el promedio acumulado existe cuando la CF todavia no")
def _():
    c = _modelo(p1=80, p2=90)
    assert c.calcular_final() is None, "no puede haber CF con dos pendientes"
    assert c.promedio_acumulado() == 85.0
    # y excluye NE igual que la CF
    c2 = _modelo(p1=80, p2=90)
    c2.ne3 = True
    assert c2.promedio_acumulado() == 85.0
    assert _modelo().promedio_acumulado() is None


# ══════════════ E · CF FANTASMA ══════════════

@test("E1 la secuencia completa: CF existe, se limpia, y NE la devuelve")
def _():
    limpiar_calificaciones(E_2)
    # 1 · los cuatro periodos -> hay CF
    assert guardar(H_PROF, E_2, LENGUA, p1=80, p2=80, p3=80, p4=80).status_code == 200
    f = fila(E_2, LENGUA)
    assert f.final_competencia == 80.0 and f.literal == 'B', (f.final_competencia, f.literal)

    # 2 · limpiar P4 -> la CF y el literal desaparecen
    assert guardar(H_PROF, E_2, LENGUA, p4=None).status_code == 200
    f = fila(E_2, LENGUA)
    assert f.p4 is None
    assert f.final_competencia is None, "CF fantasma: quedo la anterior"
    assert f.literal is None, "literal fantasma"

    # 3 · marcar NE4 -> vuelve a haber CF, ahora entre 3
    assert guardar(H_PROF, E_2, LENGUA, ne4=True).status_code == 200
    f = fila(E_2, LENGUA)
    assert f.es_ne(4) is True
    assert f.final_competencia == 80.0, f.final_competencia
    assert f.literal == 'B', f.literal


@test("E2 borrar los cuatro periodos no deja CF fantasma")
def _():
    limpiar_calificaciones(E_2)
    guardar(H_PROF, E_2, MATE, p1=90, p2=90, p3=90, p4=90)
    assert fila(E_2, MATE).final_competencia == 90.0
    guardar(H_PROF, E_2, MATE, p1=None, p2=None, p3=None, p4=None)
    f = fila(E_2, MATE)
    assert f.final_competencia is None and f.literal is None, (f.final_competencia, f.literal)


# ══════════════ F · RECUPERACION FINAL ══════════════

def _cargar_area(est, asig, **notas):
    for comp in (1, 2, 3):
        r = guardar(H_PROF, est, asig, comp=comp, **notas)
        assert r.status_code == 200, r.text[:200]


@test("F1 P4 abierto -> no nace ficha")
def _():
    limpiar_calificaciones()
    set_ano(p4_cerrado=False)
    _cargar_area(E_1, LENGUA, p1=40, p2=40, p3=40, p4=40)
    client.get("/api/recuperaciones-primaria/pendientes", headers=H_DIR)
    assert n_fichas() == 0, "nacio ficha con P4 abierto"


@test("F2 P4 cerrado pero con un periodo PENDIENTE -> no nace ficha")
def _():
    limpiar_calificaciones()
    set_ano(p4_cerrado=False)
    _cargar_area(E_1, LENGUA, p1=40, p2=40, p3=40)     # P4 sin cargar
    set_ano(p4_cerrado=True)
    try:
        client.get("/api/recuperaciones-primaria/pendientes", headers=H_DIR)
        assert n_fichas() == 0, "nacio ficha con un periodo pendiente"
    finally:
        set_ano(p4_cerrado=False)


@test("F3 P4 cerrado + una competencia incompleta -> no nace ficha")
def _():
    limpiar_calificaciones()
    set_ano(p4_cerrado=False)
    # C1 y C2 completas, C3 a medias: el area no tiene CF oficial.
    for comp in (1, 2):
        guardar(H_PROF, E_1, LENGUA, comp=comp, p1=40, p2=40, p3=40, p4=40)
    guardar(H_PROF, E_1, LENGUA, comp=3, p1=40, p2=40)
    set_ano(p4_cerrado=True)
    try:
        client.get("/api/recuperaciones-primaria/pendientes", headers=H_DIR)
        assert n_fichas() == 0, "nacio ficha con una competencia a medias"
    finally:
        set_ano(p4_cerrado=False)


@test("F4 P4 cerrado + CF oficial >= 65 -> no nace ficha")
def _():
    limpiar_calificaciones()
    set_ano(p4_cerrado=False)
    _cargar_area(E_1, LENGUA, p1=80, p2=80, p3=80, p4=80)
    set_ano(p4_cerrado=True)
    try:
        client.get("/api/recuperaciones-primaria/pendientes", headers=H_DIR)
        assert n_fichas() == 0, "nacio ficha con el area aprobada"
    finally:
        set_ano(p4_cerrado=False)


@test("F5 P4 cerrado + CF oficial < 65 -> nace la ficha, como siempre")
def _():
    limpiar_calificaciones()
    set_ano(p4_cerrado=False)
    _cargar_area(E_1, LENGUA, p1=40, p2=40, p3=40, p4=40)
    set_ano(p4_cerrado=True)
    try:
        r = client.get("/api/recuperaciones-primaria/pendientes", headers=H_DIR)
        assert r.status_code == 200, r.text[:200]
        assert n_fichas() == 1, "no nacio la ficha que si corresponde"
        mias = [p for p in r.json()["pendientes"]
                if p["estudiante_id"] == E_1 and p["asignatura_id"] == LENGUA]
        assert len(mias) == 1 and mias[0]["fase_pendiente"] == "final", mias
        assert mias[0]["cf_area"] == 40, mias[0]
    finally:
        set_ano(p4_cerrado=False)


@test("F6 con NE el area sigue pudiendo llegar a recuperacion")
def _():
    limpiar_calificaciones()
    set_ano(p4_cerrado=False)
    for comp in (1, 2, 3):
        guardar(H_PROF, E_1, MATE, comp=comp, p1=40, p2=40, p3=40)
        guardar(H_PROF, E_1, MATE, comp=comp, ne4=True)
    set_ano(p4_cerrado=True)
    try:
        client.get("/api/recuperaciones-primaria/pendientes", headers=H_DIR)
        assert n_fichas() == 1, "un area resuelta con NE deberia poder recuperar"
    finally:
        set_ano(p4_cerrado=False)


@test("F7 la sincronizacion NO borra fichas que ya existen")
def _():
    antes = n_fichas()
    assert antes >= 1, "precondicion de F6"
    set_ano(p4_cerrado=False)
    client.get("/api/recuperaciones-primaria/pendientes", headers=H_DIR)
    assert n_fichas() == antes, "se borraron fichas historicas"


# ══════════════ G · LO QUE R2 NO DEBE TOCAR ══════════════

@test("G1 promocion y situacion de area no cambiaron en R2")
def _():
    import calculo_primaria as CP
    # aprobado directo
    assert CP.situacion_area(80)['estado'] == 'aprobado'
    # sin CF no se inventa un veredicto
    assert CP.situacion_area(None)['estado'] == 'sin_notas'
    # pendiente de recuperacion
    assert CP.situacion_area(50)['estado'] == 'recuperacion_pendiente'
    # y la condicion final conserva sus cortes
    assert CP.condicion_final_estudiante(
        [{'estado': 'aprobado', 'nota_final': 80}])['condicion'] == 'promovido'
    assert CP.condicion_final_estudiante(
        [{'estado': 'reprobado', 'nota_final': 50}] * 4)['condicion'] == 'repite'


@test("G2 un area sin CF oficial no llega a promocion con un veredicto falso")
def _():
    import calculo_primaria as CP
    # cf_area de competencias incompletas es None, y situacion_area lo respeta
    incompletas = [_modelo(p1=80, p2=80), _modelo(p1=80, p2=80), _modelo(p1=80, p2=80)]
    assert cf_area(incompletas) == (None, None), cf_area(incompletas)
    assert CP.situacion_area(cf_area(incompletas)[1])['estado'] == 'sin_notas'


@test("G3 cf_area sigue SIN exigir un numero esperado de competencias (R3)")
def _():
    # Documenta el bloqueo: con solo C1 y C2 completas, cf_area promedia dos.
    # No es un descuido, es la subfase que depende de R3 (Ingles 2 -> 3).
    dos = [_modelo(p1=80, p2=80, p3=80, p4=80), _modelo(p1=60, p2=60, p3=60, p4=60)]
    assert cf_area(dos) == (70.0, 70), cf_area(dos)
    import inspect
    assert 'CF_AREA_EXPECTED_COMPETENCIES_REQUIRES_R3' in inspect.getdoc(cf_area), \
        "el bloqueo deberia estar documentado en el propio codigo"


@test("G4 la recuperacion cualitativa de P2A-R1 sigue intacta")
def _():
    assert hasattr(M, 'RecuperacionPedagogicaPrimaria')
    uqs = [c for c in M.RecuperacionPedagogicaPrimaria.__table__.constraints
           if c.__class__.__name__ == 'UniqueConstraint']
    assert uqs == [], "R2 no debe tocar la tabla cualitativa"
    assert hasattr(APP, '_modalidad_recuperacion_primaria')
    assert hasattr(APP, '_guard_division_recuperacion')


# ══════ H · NO NACEN FILAS VACIAS (R2-A8.3) ══════

def _existe_fila(est, asig, comp=1):
    d = SessionLocal()
    try:
        return d.query(M.CalificacionPrimaria).filter_by(
            estudiante_id=est, asignatura_id=asig, competencia_numero=comp).count()
    finally:
        d.close()


@test("H1 fila inexistente + ne1=false -> no se crea nada")
def _():
    limpiar_calificaciones(E_2)
    assert _existe_fila(E_2, MATE, 2) == 0, "precondicion"
    r = guardar(H_PROF, E_2, MATE, comp=2, ne1=False)
    assert r.status_code == 200, r.text[:250]
    assert _existe_fila(E_2, MATE, 2) == 0, "nacio una calificacion fantasma"
    assert r.json().get("sin_cambios") is True, r.json()
    assert r.json().get("id") is None


@test("H2 fila inexistente + p1=null + rp1=null + ne1=false -> no se crea nada")
def _():
    limpiar_calificaciones(E_2)
    r = guardar(H_PROF, E_2, MATE, comp=3, p1=None, rp1=None, ne1=False)
    assert r.status_code == 200, r.text[:250]
    assert _existe_fila(E_2, MATE, 3) == 0, "nacio una calificacion fantasma"
    assert r.json().get("sin_cambios") is True


@test("H3 fila inexistente + ne1=true -> SI se crea, es un dato academico")
def _():
    limpiar_calificaciones(E_2)
    r = guardar(H_PROF, E_2, MATE, comp=2, ne1=True)
    assert r.status_code == 200, r.text[:250]
    assert _existe_fila(E_2, MATE, 2) == 1, "un NE es informacion: deberia guardarse"
    f = fila(E_2, MATE, 2)
    assert f.es_ne(1) is True
    assert f.p1 is None and f.rp1 is None


@test("H4 el 0 es contenido: crea fila aunque sea falsy en Python")
def _():
    limpiar_calificaciones(E_2)
    r = guardar(H_PROF, E_2, MATE, comp=3, p1=0)
    assert r.status_code == 200, r.text[:250]
    assert _existe_fila(E_2, MATE, 3) == 1, "un 0 es una nota, no una ausencia"
    assert fila(E_2, MATE, 3).p1 == 0


@test("H5 una fila EXISTENTE no se borra ni se toca con un envio vacio")
def _():
    limpiar_calificaciones(E_2)
    guardar(H_PROF, E_2, MATE, comp=1, p1=70, p2=80)
    assert _existe_fila(E_2, MATE, 1) == 1
    r = guardar(H_PROF, E_2, MATE, comp=1, ne3=False)
    assert r.status_code == 200, r.text[:250]
    assert _existe_fila(E_2, MATE, 1) == 1, "se borro una fila existente"
    f = fila(E_2, MATE, 1)
    assert (f.p1, f.p2) == (70, 80), (f.p1, f.p2)


@test("H6 el docente SI puede vaciar una fila existente (corregir no es crear)")
def _():
    # El candado de A8.3 es solo para filas NUEVAS. Sobre una existente el
    # docente manda, incluso para dejarla sin notas mientras corrige.
    r = guardar(H_PROF, E_2, MATE, comp=1, p1=None, p2=None)
    assert r.status_code == 200, r.text[:250]
    f = fila(E_2, MATE, 1)
    assert f is not None, "la fila existente no debe desaparecer"
    assert f.p1 is None and f.p2 is None
    assert f.final_competencia is None and f.literal is None, "CF fantasma"


print(f"\n{B}{'=' * 62}{X}")
if _fail:
    print(f"{R}{B}  {len(_fail)} FALLO(S) de {_total}{X}")
    for n, e in _fail:
        print(f"{R}   - {n}: {e}{X}")
    sys.exit(1)
print(f"{G}{B}  {_ok}/{_total} pruebas pasaron{X}")
print(f"{B}{'=' * 62}{X}")
