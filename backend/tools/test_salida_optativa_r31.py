# -*- coding: utf-8 -*-
"""
EducaOne R3.1 — SALIDA OPTATIVA: modelo institucional + catálogo oficial.

Cubre los 20 puntos exigidos por R3.1 §7, en tres bloques:

  A. MIGRACIÓN (§12-14): arranca la app REAL contra una SQLite temporal con el
     esquema LEGACY (cursos SIN salida_optativa_codigo, sin la tabla de
     componentes) y verifica que la migración es aditiva, idempotente, que no
     borra nada y que NO inventa ninguna salida.

  B. CATÁLOGO Y MODELO (§1-11): las reglas de identidad y tenant, incluida la
     prueba de que ni el nombre duplicado ni `Asignatura.codigo` duplicado
     (ambos reales en producción) pueden desviar la resolución.

  C. REGISTRO ESCOLAR (§15-19): el mapa REAL de asistencia verificado contra
     los templates oficiales, la no invasión de las páginas de Salida Optativa,
     los totales de páginas y la integridad del pipeline XObject.

SEGURIDAD: SQLite temporal aislada. NUNCA toca sge.db ni INITIAL_CREDENTIALS.txt
(se verifica al final). No se conecta a producción. No hace escrituras reales.

Uso:
    cd backend
    python tools/test_salida_optativa_r31.py
"""
import os
import sys
import atexit
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TMPDIR = tempfile.mkdtemp(prefix="eo_salida_opt_r31_")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_TMPDIR, "s.db").replace("\\", "/")
os.environ.setdefault("ENVIRONMENT", "development")


@atexit.register
def _cleanup():
    try:
        import shutil
        shutil.rmtree(_TMPDIR, ignore_errors=True)
    except Exception:
        pass


from sqlalchemy import event, text            # noqa: E402
from sqlalchemy.exc import IntegrityError     # noqa: E402
from database import engine, SessionLocal     # noqa: E402
import models as M                            # noqa: E402

_eu = str(engine.url).replace("\\", "/")
assert _TMPDIR.replace("\\", "/") in _eu and "sge.db" not in _eu, _eu

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_SGE = os.path.join(_BACKEND, "sge.db")
_REPO_CRED = os.path.join(_BACKEND, "INITIAL_CREDENTIALS.txt")
_sge_mtime = os.path.getmtime(_REPO_SGE) if os.path.exists(_REPO_SGE) else None
_cred_mtime = os.path.getmtime(_REPO_CRED) if os.path.exists(_REPO_CRED) else None


@event.listens_for(engine, "connect")
def _relax_fk(dbapi_conn, rec):
    try:
        dbapi_conn.execute("PRAGMA foreign_keys=OFF")
    except Exception:
        pass


engine.dispose()

G, R, B, C, X = "\033[92m", "\033[91m", "\033[1m", "\033[96m", "\033[0m"
_fail, _ok, _total = [], 0, 0


def test(nombre):
    def deco(fn):
        global _total, _ok
        _total += 1
        print(f"\n{C}▶ {nombre}{X}")
        try:
            fn()
            _ok += 1
            print(f"  {G}✓ PASÓ{X}")
        except Exception as e:
            import traceback
            _fail.append((nombre, str(e)))
            print(f"  {R}✗ FALLÓ: {e}{X}")
            traceback.print_exc()
        return fn
    return deco


# ===========================================================================
# BLOQUE A — MIGRACIÓN
# ===========================================================================

COL_A, COL_B = 1, 2
ANO_A, ANO_B = 1, 2
GRADO_1RO, GRADO_4TO, GRADO_5TO, GRADO_4TO_PRIM = 1, 4, 5, 40
CURSO_1RO, CURSO_4TO, CURSO_5TO, CURSO_4TO_PRIM = 10, 14, 15, 19
CURSO_B = 20                     # curso del colegio B (tenant ajeno)
CURSO_SIN_ANO = 21               # 4to del colegio A SIN año escolar
CURSO_ANO_AJENO = 22             # 4to del colegio A apuntando al año del B

AULA_LEGACY = "A-201"            # dato previo que NO se puede perder

M.Base.metadata.create_all(bind=engine)

# Los colegios se insertan por ORM (no por SQL crudo): `colegios` tiene
# columnas NOT NULL cuyo valor lo pone el default del modelo, no la BD.
# Va ANTES del bloque engine.connect() para no chocar con el lock de SQLite.
_dcol = SessionLocal()
try:
    _dcol.add_all([M.Colegio(id=COL_A, nombre="Colegio A", codigo="c1"),
                   M.Colegio(id=COL_B, nombre="Colegio B", codigo="c2")])
    _dcol.commit()
finally:
    _dcol.close()

# --- reconstruir el esquema LEGACY: cursos SIN la columna nueva, y sin la
#     tabla de componentes. Es el estado exacto de producción hoy.
with engine.connect() as conn:
    conn.execute(text("DROP TABLE IF EXISTS curso_componentes_optativos"))
    conn.execute(text("DROP TABLE IF EXISTS cursos"))
    conn.execute(text(
        "CREATE TABLE cursos ("
        "  id INTEGER NOT NULL PRIMARY KEY,"
        "  colegio_id INTEGER REFERENCES colegios(id),"
        "  nombre VARCHAR(10) NOT NULL,"
        "  grado_id INTEGER NOT NULL REFERENCES grados(id),"
        "  tanda_id INTEGER REFERENCES tandas(id),"
        "  ano_escolar_id INTEGER REFERENCES ano_escolar(id),"
        "  capacidad INTEGER,"
        "  aula VARCHAR(20),"
        "  activo BOOLEAN"
        ")"
    ))
    for aid, col in ((ANO_A, COL_A), (ANO_B, COL_B)):
        conn.execute(text(
            "INSERT INTO ano_escolar (id, colegio_id, nombre, activo, cerrado, "
            "periodo_activo, dias_trabajados) VALUES (:i, :c, '2025-2026', 1, 0, 1, '{}')"),
            {"i": aid, "c": col})
    for gid, nom, niv in (
        (GRADO_1RO, "1ro Secundaria", "secundaria"),
        (GRADO_4TO, "4to Secundaria", "secundaria"),
        (GRADO_5TO, "5to Secundaria", "secundaria"),
        (GRADO_4TO_PRIM, "4to Primaria", "primaria"),
    ):
        conn.execute(text(
            "INSERT INTO grados (id, colegio_id, nombre, nivel) VALUES (:i, :c, :n, :v)"),
            {"i": gid, "c": COL_A, "n": nom, "v": niv})
    for kid, gid, col, ano in (
        (CURSO_1RO, GRADO_1RO, COL_A, ANO_A),
        (CURSO_4TO, GRADO_4TO, COL_A, ANO_A),
        (CURSO_5TO, GRADO_5TO, COL_A, ANO_A),
        (CURSO_4TO_PRIM, GRADO_4TO_PRIM, COL_A, ANO_A),
        (CURSO_B, GRADO_4TO, COL_B, ANO_B),
        (CURSO_SIN_ANO, GRADO_4TO, COL_A, None),
        (CURSO_ANO_AJENO, GRADO_4TO, COL_A, ANO_B),
    ):
        conn.execute(text(
            "INSERT INTO cursos (id, colegio_id, nombre, grado_id, ano_escolar_id, "
            "capacidad, aula, activo) VALUES (:k, :c, 'A', :g, :y, 35, :au, 1)"),
            {"k": kid, "c": col, "g": gid, "y": ano, "au": AULA_LEGACY})
    conn.commit()

_cols_antes = {r[1] for r in engine.connect().execute(text("PRAGMA table_info(cursos)"))}
_tablas_antes = set(engine.connect().execute(text(
    "SELECT name FROM sqlite_master WHERE type='table'")).scalars())
print(f"  ANTES  cursos: {sorted(_cols_antes)}")
assert "salida_optativa_codigo" not in _cols_antes
assert "curso_componentes_optativos" not in _tablas_antes


def _arrancar_app():
    """Entra al lifespan real de la app → ejecuta el bloque de migración 6e."""
    from fastapi.testclient import TestClient
    import app as _app
    with TestClient(_app.app):
        pass


def _estado():
    with engine.connect() as conn:
        cols = {r[1] for r in conn.execute(text("PRAGMA table_info(cursos)"))}
        tablas = set(conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table'")).scalars())
        filas = list(conn.execute(text(
            "SELECT id, colegio_id, nombre, grado_id, ano_escolar_id, capacidad, aula, "
            "activo, salida_optativa_codigo FROM cursos ORDER BY id"
        )))
    return cols, tablas, filas


_arrancar_app()
_cols1, _tablas1, _filas1 = _estado()
print(f"  DESPUÉS cursos: {sorted(_cols1)}")

_arrancar_app()          # segundo arranque
_cols2, _tablas2, _filas2 = _estado()


@test("§14 cursos existentes quedan con salida NULL (sin backfill especulativo)")
def _():
    assert "salida_optativa_codigo" in _cols1, "la columna no se agregó"
    salidas = {f[0]: f[8] for f in _filas1}
    assert salidas == {CURSO_1RO: None, CURSO_4TO: None, CURSO_5TO: None,
                       CURSO_4TO_PRIM: None, CURSO_B: None,
                       CURSO_SIN_ANO: None, CURSO_ANO_AJENO: None}, salidas
    print(f"    los {len(salidas)} cursos previos quedaron en NULL")


@test("§13 ningún dato legacy borrado: filas y columnas previas intactas")
def _():
    assert len(_filas1) == 7, f"se perdieron cursos: {len(_filas1)}"
    for f in _filas1:
        assert f[6] == AULA_LEGACY, f"aula alterada en curso {f[0]}: {f[6]!r}"
        assert f[5] == 35 and f[7] in (1, True), f
    faltantes = _cols_antes - _cols1
    assert not faltantes, f"columnas desaparecidas: {faltantes}"
    perdidas = _tablas_antes - _tablas1
    assert not perdidas, f"tablas desaparecidas: {perdidas}"
    assert "curso_componentes_optativos" in _tablas1, "la tabla nueva no se creó"


@test("§12 migración idempotente: el segundo arranque no cambia nada")
def _():
    assert _cols1 == _cols2, (_cols1 ^ _cols2)
    assert _tablas1 == _tablas2, (_tablas1 ^ _tablas2)
    assert _filas1 == _filas2, "las filas cambiaron en el segundo arranque"


# ===========================================================================
# BLOQUE B — CATÁLOGO, IDENTIDAD Y TENANT
# ===========================================================================

import salidas_optativas as SO                    # noqa: E402
import salida_optativa_service as SVC             # noqa: E402

ASIG_CYT, ASIG_CYT_GEMELA, ASIG_HLM, ASIG_B = 101, 102, 103, 104
NOMBRE_CHOCADO = "Biología y Computación"
CODIGO_CHOCADO = "CN"        # `asignaturas.codigo` duplicado, como en producción

_s = SessionLocal()
try:
    # Dos asignaturas del MISMO colegio con nombre Y código IDÉNTICOS: la
    # anomalía real de producción (ids 1-8 y 9-16 comparten código).
    _s.add_all([
        M.Asignatura(id=ASIG_CYT, colegio_id=COL_A, nombre=NOMBRE_CHOCADO, codigo=CODIGO_CHOCADO),
        M.Asignatura(id=ASIG_CYT_GEMELA, colegio_id=COL_A, nombre=NOMBRE_CHOCADO, codigo=CODIGO_CHOCADO),
        M.Asignatura(id=ASIG_HLM, colegio_id=COL_A, nombre="Apreciación y Producción Literarias", codigo="LE"),
        M.Asignatura(id=ASIG_B, colegio_id=COL_B, nombre=NOMBRE_CHOCADO, codigo=CODIGO_CHOCADO),
    ])
    _s.commit()
finally:
    _s.close()


def _curso(db, cid):
    return db.query(M.Curso).filter(M.Curso.id == cid).first()


@test("§0 catálogo oficial: 4 salidas, 18 componentes, 6 slots, 4 h/semana cada salida")
def _():
    assert set(SO.SALIDAS) == {"HLM", "HCS", "MYT", "CYT"}, SO.SALIDAS
    assert len(SO.COMPONENTES_POR_CODIGO) == 18, len(SO.COMPONENTES_POR_CODIGO)
    for g in (4, 5, 6):
        slots = sorted(c.slot for c in SO._CATALOGO if c.grado == g)
        assert slots == [0, 1, 2, 3, 4, 5], (g, slots)
        for sal in SO.SALIDAS:
            assert SO.horas_totales(sal, g) == 4, (sal, g, SO.horas_totales(sal, g))
    # un estudiante cursa como máximo 2 componentes
    for sal in SO.SALIDAS:
        for g in (4, 5, 6):
            assert len(SO.componentes_de(sal, g)) <= 2, (sal, g)


@test("§0b slot ↔ página: el slot indexa completiva_salida_optativa del template")
def _():
    from registro_escolar import GRADO_CONFIG
    for g in (4, 5, 6):
        pgs = GRADO_CONFIG[g]["completiva_salida_optativa"]
        assert pgs == [211, 212, 214, 217, 219, 221], (g, pgs)
        for comp in (c for c in SO._CATALOGO if c.grado == g):
            assert 0 <= comp.slot < len(pgs), comp
    # el orden de slots reproduce el orden impreso del template
    esperado = [("HLM", SO.AREA_LENGUA), ("HCS", SO.AREA_LENGUA),
                ("HLM", SO.AREA_INGLES), ("MYT", SO.AREA_MATEMATICA),
                ("HCS", SO.AREA_SOCIALES), ("CYT", SO.AREA_NATURALEZA)]
    for g in (4, 5, 6):
        real = [(c.salida, c.area_base)
                for c in sorted((x for x in SO._CATALOGO if x.grado == g), key=lambda x: x.slot)]
        assert real == esperado, (g, real)


@test("§1 curso sin salida configurada → válido (NULL es un estado legítimo)")
def _():
    db = SessionLocal()
    try:
        c = _curso(db, CURSO_4TO)
        assert c.salida_optativa_codigo is None
        ok, err = SVC.validar_salida_para_curso(c, None)
        assert ok and err is None, err
        assert SVC.componentes_esperados(c) == []
        assert SVC.resolver_componentes(db, c, ANO_A) == []
    finally:
        db.close()


@test("§2 curso de 1ro-3ro NO puede configurar Salida Optativa (tampoco 4to Primaria)")
def _():
    db = SessionLocal()
    try:
        c1 = _curso(db, CURSO_1RO)
        assert not SVC.curso_admite_salida(c1)
        ok, err = SVC.validar_salida_para_curso(c1, "CYT")
        assert not ok and "4to a 6to" in err, err

        cp = _curso(db, CURSO_4TO_PRIM)
        assert SVC.grado_numero_de_curso(cp) is None, "4to Primaria no es Secundaria"
        ok, err = SVC.validar_salida_para_curso(cp, "CYT")
        assert not ok and "Secundaria" in err, err
    finally:
        db.close()


@test("§3 curso de 4to puede configurar CYT y obtiene sus componentes oficiales")
def _():
    db = SessionLocal()
    try:
        c = _curso(db, CURSO_4TO)
        ok, err = SVC.validar_salida_para_curso(c, "CYT")
        assert ok, err
        c.salida_optativa_codigo = "CYT"
        db.commit()
        comps = SVC.componentes_esperados(_curso(db, CURSO_4TO))
        assert [x.codigo for x in comps] == ["CYT-CN-4"], comps
        assert comps[0].nombre_oficial == "Biología y Computación"
        assert comps[0].horas_semana == 4 and comps[0].slot == 5
    finally:
        db.close()


@test("§4 un curso no puede tener dos salidas simultáneas (columna escalar)")
def _():
    from sqlalchemy import inspect as _sa_inspect
    col = _sa_inspect(M.Curso).columns["salida_optativa_codigo"]
    assert col.type.length == 8 and col.nullable, col
    # no existe ninguna colección de salidas colgando del curso
    rels = {r.key for r in _sa_inspect(M.Curso).relationships}
    assert not any("salida" in r for r in rels), rels

    db = SessionLocal()
    try:
        c = _curso(db, CURSO_4TO)
        assert c.salida_optativa_codigo == "CYT"
        c.salida_optativa_codigo = "MYT"      # reconfigurar REEMPLAZA
        db.commit()
        fila = list(db.execute(text(
            "SELECT salida_optativa_codigo FROM cursos WHERE id = :k"), {"k": CURSO_4TO}))
        assert len(fila) == 1 and fila[0][0] == "MYT", fila
        c = _curso(db, CURSO_4TO)
        c.salida_optativa_codigo = "CYT"      # restaurar para los tests siguientes
        db.commit()
    finally:
        db.close()


@test("§5 tenant: una asignatura del colegio B no puede mapearse en un curso del A")
def _():
    db = SessionLocal()
    try:
        c = _curso(db, CURSO_4TO)
        ok, err = SVC.validar_mapeo_componente(db, c, "CYT-CN-4", ASIG_B)
        assert not ok and "otro colegio" in err, err
    finally:
        db.close()


@test("§6 un componente de 4to no se puede asignar a un curso de 5to")
def _():
    db = SessionLocal()
    try:
        c5 = _curso(db, CURSO_5TO)
        c5.salida_optativa_codigo = "CYT"
        db.commit()
        c5 = _curso(db, CURSO_5TO)
        ok, err = SVC.validar_mapeo_componente(db, c5, "CYT-CN-4", ASIG_CYT)
        assert not ok and "4to" in err, err
        ok, err = SVC.validar_mapeo_componente(db, c5, "CYT-CN-5", ASIG_CYT)
        assert ok, err
        assert not SO.componente_pertenece("CYT-CN-4", "CYT", 5)
    finally:
        db.close()


@test("§7 un componente de HLM no se puede asignar a un curso configurado CYT")
def _():
    db = SessionLocal()
    try:
        c = _curso(db, CURSO_4TO)
        assert c.salida_optativa_codigo == "CYT"
        ok, err = SVC.validar_mapeo_componente(db, c, "HLM-LE-4", ASIG_HLM)
        assert not ok and "HLM" in err, err
        assert not SO.componente_pertenece("HLM-LE-4", "CYT", 4)
    finally:
        db.close()


@test("§8 el mapeo usa asignatura_id real y resuelve la cadena completa")
def _():
    db = SessionLocal()
    try:
        c = _curso(db, CURSO_4TO)
        ok, err = SVC.validar_mapeo_componente(db, c, "CYT-CN-4", ASIG_CYT)
        assert ok, err
        db.add(M.CursoComponenteOptativo(
            colegio_id=COL_A, curso_id=CURSO_4TO, ano_escolar_id=ANO_A,
            componente_codigo="CYT-CN-4", asignatura_id=ASIG_CYT, activo=True))
        db.commit()

        res = SVC.resolver_componentes(db, _curso(db, CURSO_4TO), ANO_A)
        assert len(res) == 1, res
        assert res[0]["componente"].codigo == "CYT-CN-4"
        assert res[0]["asignatura_id"] == ASIG_CYT
        assert res[0]["slot"] == 5
        # curso 4to A -> CYT -> CYT-CN-4 -> asignatura real -> página 221
        from registro_escolar import GRADO_CONFIG
        assert GRADO_CONFIG[4]["completiva_salida_optativa"][res[0]["slot"]] == 221
    finally:
        db.close()


@test("§9 nombres duplicados NO afectan la identidad (dos asignaturas iguales)")
def _():
    db = SessionLocal()
    try:
        gemelas = db.query(M.Asignatura).filter(
            M.Asignatura.colegio_id == COL_A,
            M.Asignatura.nombre == NOMBRE_CHOCADO).all()
        assert len(gemelas) == 2, "el escenario de nombres duplicados no se armó"
        res = SVC.resolver_componentes(db, _curso(db, CURSO_4TO), ANO_A)
        assert res[0]["asignatura_id"] == ASIG_CYT, res[0]
        assert res[0]["asignatura_id"] != ASIG_CYT_GEMELA
    finally:
        db.close()


@test("§10 `Asignatura.codigo` duplicado NO afecta la identidad")
def _():
    db = SessionLocal()
    try:
        mismos = db.query(M.Asignatura).filter(
            M.Asignatura.codigo == CODIGO_CHOCADO).all()
        assert len(mismos) >= 3, "el escenario de códigos duplicados no se armó"
        # el catálogo jamás expone ni consume `Asignatura.codigo`
        fuente = open(os.path.join(_BACKEND, "salidas_optativas.py"), encoding="utf-8").read()
        assert "Asignatura" not in fuente.replace("`Asignatura.codigo`", "")\
            .replace("Asignatura.codigo", ""), "el catálogo no debe depender de Asignatura"
        res = SVC.resolver_componentes(db, _curso(db, CURSO_4TO), ANO_A)
        assert res[0]["asignatura_id"] == ASIG_CYT
    finally:
        db.close()


@test("§11 una misma asignatura no puede mapearse a dos componentes del mismo curso")
def _():
    db = SessionLocal()
    try:
        # (a) el mismo componente dos veces -> uq_curso_componente_optativo
        db.add(M.CursoComponenteOptativo(
            colegio_id=COL_A, curso_id=CURSO_4TO, ano_escolar_id=ANO_A,
            componente_codigo="CYT-CN-4", asignatura_id=ASIG_CYT_GEMELA, activo=True))
        try:
            db.commit()
            raise AssertionError("se aceptaron dos asignaturas para el mismo componente")
        except IntegrityError:
            db.rollback()

        # (b) la misma asignatura en otro componente -> uq_curso_componente_asignatura
        db.add(M.CursoComponenteOptativo(
            colegio_id=COL_A, curso_id=CURSO_4TO, ano_escolar_id=ANO_A,
            componente_codigo="HLM-LE-4", asignatura_id=ASIG_CYT, activo=True))
        try:
            db.commit()
            raise AssertionError("la misma asignatura se mapeó a dos componentes")
        except IntegrityError:
            db.rollback()

        # y de todos modos la validación de aplicación lo habría rechazado antes
        ok, err = SVC.validar_mapeo_componente(db, _curso(db, CURSO_4TO), "HLM-LE-4", ASIG_CYT)
        assert not ok, err
    finally:
        db.close()


# ===========================================================================
# BLOQUE E — IDENTIDAD ANUAL DE LOS COMPONENTES (R3.1 final guard)
# ===========================================================================

def _n_mapeos(db):
    return db.query(M.CursoComponenteOptativo).count()


@test("§E1 ano_escolar_id es NOT NULL: sin año no se puede crear el mapeo")
def _():
    from sqlalchemy import inspect as _sa_inspect
    col = _sa_inspect(M.CursoComponenteOptativo).columns["ano_escolar_id"]
    assert not col.nullable, "ano_escolar_id sigue siendo nullable en el modelo"
    # y el esquema FÍSICO creado por la migración también lo exige
    fisico = {c["name"]: c for c in
              __import__("sqlalchemy").inspect(engine).get_columns("curso_componentes_optativos")}
    assert fisico["ano_escolar_id"]["nullable"] is False, fisico["ano_escolar_id"]

    db = SessionLocal()
    try:
        antes = _n_mapeos(db)
        db.add(M.CursoComponenteOptativo(
            colegio_id=COL_A, curso_id=CURSO_4TO, ano_escolar_id=None,
            componente_codigo="HLM-LE-4", asignatura_id=ASIG_HLM, activo=True))
        try:
            db.commit()
            raise AssertionError("se aceptó un mapeo sin año escolar")
        except IntegrityError:
            db.rollback()
        assert _n_mapeos(db) == antes, "se creó una fila pese al fallo"
    finally:
        db.close()


@test("§E2 dos mapeos idénticos no pueden coexistir (la clave única muerde)")
def _():
    db = SessionLocal()
    try:
        antes = _n_mapeos(db)
        # ya existe (CURSO_4TO, ANO_A, 'CYT-CN-4', ASIG_CYT) creado en §8
        db.add(M.CursoComponenteOptativo(
            colegio_id=COL_A, curso_id=CURSO_4TO, ano_escolar_id=ANO_A,
            componente_codigo="CYT-CN-4", asignatura_id=ASIG_CYT, activo=True))
        try:
            db.commit()
            raise AssertionError("se aceptó un mapeo duplicado")
        except IntegrityError:
            db.rollback()
        assert _n_mapeos(db) == antes
    finally:
        db.close()


@test("§E3 curso año A + mapeo año A -> permitido")
def _():
    db = SessionLocal()
    try:
        c = _curso(db, CURSO_4TO)
        assert SVC.ano_de_curso(c) == ANO_A
        ok, err = SVC.validar_ano_para_curso(db, c, ANO_A)
        assert ok, err
        ok, err = SVC.validar_ano_para_curso(db, c, None)   # derivado del curso
        assert ok, err
        ok, err = SVC.validar_mapeo_componente(db, c, "CYT-CN-4", ASIG_CYT, ANO_A)
        assert ok, err
    finally:
        db.close()


@test("§E4 curso año A + mapeo año B -> rechazado, y sin escribir nada")
def _():
    db = SessionLocal()
    try:
        antes = _n_mapeos(db)
        c = _curso(db, CURSO_4TO)
        ok, err = SVC.validar_ano_para_curso(db, c, ANO_B)
        assert not ok and "no corresponde al curso" in err, err
        ok, err = SVC.validar_mapeo_componente(db, c, "CYT-CN-4", ASIG_CYT, ANO_B)
        assert not ok and "no corresponde al curso" in err, err
        # resolver_componentes NO acepta un año ajeno en silencio
        try:
            SVC.resolver_componentes(db, c, ANO_B)
            raise AssertionError("resolver_componentes aceptó un año ajeno")
        except ValueError as e:
            assert "no corresponde al curso" in str(e), e
        assert _n_mapeos(db) == antes, "la validación escribió en la BD"
    finally:
        db.close()


@test("§E5 curso SIN año -> rechazado (y resolver no adivina)")
def _():
    db = SessionLocal()
    try:
        antes = _n_mapeos(db)
        c = _curso(db, CURSO_SIN_ANO)
        assert SVC.ano_de_curso(c) is None
        c.salida_optativa_codigo = "CYT"
        db.commit()
        c = _curso(db, CURSO_SIN_ANO)

        ok, err = SVC.validar_ano_para_curso(db, c, None)
        assert not ok and "no tiene año escolar" in err, err
        ok, err = SVC.validar_mapeo_componente(db, c, "CYT-CN-4", ASIG_CYT)
        assert not ok and "no tiene año escolar" in err, err
        # el catálogo sí resuelve, pero sin año no se devuelve configuración
        assert SVC.componentes_esperados(c), "el curso sí es 4to CYT"
        assert SVC.resolver_componentes(db, c) == []
        assert _n_mapeos(db) == antes
    finally:
        db.close()


@test("§E6 año escolar de otro colegio -> rechazado")
def _():
    db = SessionLocal()
    try:
        antes = _n_mapeos(db)
        c = _curso(db, CURSO_ANO_AJENO)          # curso del colegio A, año del B
        c.salida_optativa_codigo = "CYT"
        db.commit()
        c = _curso(db, CURSO_ANO_AJENO)
        ok, err = SVC.validar_ano_para_curso(db, c, None)
        assert not ok and "otro colegio" in err, err
        ok, err = SVC.validar_mapeo_componente(db, c, "CYT-CN-4", ASIG_CYT)
        assert not ok and "otro colegio" in err, err
        assert _n_mapeos(db) == antes
    finally:
        db.close()


@test("§E7 resolver_componentes deriva el año del curso, no de un parámetro")
def _():
    import inspect as _pyinspect
    firma = _pyinspect.signature(SVC.resolver_componentes)
    assert firma.parameters["ano_escolar_id"].default is None, firma
    db = SessionLocal()
    try:
        c = _curso(db, CURSO_4TO)
        sin_param = SVC.resolver_componentes(db, c)
        con_param = SVC.resolver_componentes(db, c, ANO_A)
        assert sin_param == con_param and sin_param, sin_param
        assert sin_param[0]["asignatura_id"] == ASIG_CYT
    finally:
        db.close()


@test("§E8 la configuración de un año NO se ve desde otro año")
def _():
    db = SessionLocal()
    try:
        # mismo curso_id no puede existir en dos años (EducaOne crea un Curso
        # nuevo por año), pero sí comprobamos que el filtro por año aísla:
        filas_a = db.query(M.CursoComponenteOptativo).filter_by(
            curso_id=CURSO_4TO, ano_escolar_id=ANO_A).count()
        filas_b = db.query(M.CursoComponenteOptativo).filter_by(
            curso_id=CURSO_4TO, ano_escolar_id=ANO_B).count()
        assert filas_a == 1 and filas_b == 0, (filas_a, filas_b)
    finally:
        db.close()


# ===========================================================================
# BLOQUE C — REGISTRO ESCOLAR
# ===========================================================================

from pypdf import PdfReader                                       # noqa: E402
import io as _io                                                  # noqa: E402
import registro_escolar as RE                                     # noqa: E402

# Mapa verificado PÁGINA POR PÁGINA leyendo el rótulo impreso en cada hoja de
# los seis templates oficiales. Es la referencia independiente del código.
MAPA_TEMPLATE = {
    0: [17, 18, 19, 20, 21],   # Lengua Española
    1: [22, 23, 24, 25, 26],   # Lenguas Extranjeras - Inglés
    2: [27, 28, 29, 30, 31],   # Lenguas Extranjeras - Francés
    3: [32, 33, 34, 35, 36],   # Matemática
    4: [37, 38, 39, 40, 41],   # Ciencias Sociales
    5: [42, 43, 44, 45, 46],   # Ciencias de la Naturaleza
    6: [47, 48, 49],           # Educación Artística
    7: [50, 51, 52],           # Educación Física
    8: [53, 54, 55],           # FIHR
}
PAGINAS_SALIDA_OPTATIVA = set(range(56, 66))   # 4to-6to: hojas en blanco
PAGINAS_EVAL_CICLO_1 = set(range(56, 62))      # 1ro-3ro: completivas/extraordinarias


def _mes(nombre):
    return {
        "nombre_mes": nombre,
        "docente": "Docente X",
        "dias_labels": list(range(1, 22)),
        "asistencias": [{"dias": ["P"] * 21, "total": 21, "porcentaje": 100.0}
                        for _ in range(4)],
    }


def _asistencia_todas(asignaturas):
    meses = [_mes(m) for m in ("Ago", "Sep", "Oct", "Nov", "Dic",
                               "Ene", "Feb", "Mar", "Abr", "May")]
    out = {}
    for a in asignaturas:
        out[a.lower().replace(" ", "_").replace("-", "_")] = {"meses": meses}
    return out


def _generar(grado):
    asigs = RE.ASIGNATURAS_CICLO_2 if grado >= 4 else RE.ASIGNATURAS_CICLO_1
    return RE.generar_registro_escolar(
        grado=grado,
        datos_centro={"nombre": "Centro de prueba"},
        datos_portada={"ano_escolar": "2025-2026", "seccion": "A"},
        estudiantes=[{"nombre": f"Est {i}", "apellido": "Prueba", "no_lista": i}
                     for i in range(1, 5)],
        asistencia_data=_asistencia_todas(asigs),
    )


def _xobject_names(page):
    res = page.get("/Resources")
    if res is None:
        return set()
    xo = res.get_object().get("/XObject")
    if xo is None:
        return set()
    return {str(k) for k in xo.get_object().keys()}


def _paginas_estampadas(reader):
    return {i + 1 for i, p in enumerate(reader.pages)
            if any(n.startswith("/EODataOverlay") for n in _xobject_names(p))}


_PDF = {g: PdfReader(_io.BytesIO(_generar(g))) for g in (1, 4, 6)}
_EST = {g: _paginas_estampadas(_PDF[g]) for g in _PDF}
for g in sorted(_EST):
    print(f"    grado {g}: páginas estampadas = {sorted(_EST[g])}")


@test("§15 el mapa de asistencia coincide EXACTAMENTE con el template oficial")
def _():
    real = {i: e["paginas"] for i, e in enumerate(RE.ASISTENCIA_MAPA_SECUNDARIA)}
    assert real == MAPA_TEMPLATE, f"mapa ≠ template:\n  código={real}\n  template={MAPA_TEMPLATE}"
    # y la fórmula vieja NO reproduce este mapa (regresión del bug corregido)
    formula = {i: [17 + i * 5 + k for k in range(5)] for i in range(9)}
    assert formula != real, "la fórmula lineal no puede reproducir el mapa real"
    for i in (6, 7, 8):
        assert formula[i] != real[i], i


@test("§15b las 9 materias base de ciclo 2 se estampan SOLO en sus páginas reales")
def _():
    permitidas = {p for pgs in MAPA_TEMPLATE.values() for p in pgs}
    # Banda del bloque de asistencia: desde su primera página hasta el final del
    # bloque de Salida Optativa. Fuera de ella hay secciones legítimas de otras
    # partes del Registro (portada, centro educativo, datos, condición inicial).
    banda = set(range(17, 66))
    for g in (4, 6):
        fuera = (_EST[g] & banda) - permitidas
        assert not fuera, f"grado {g} estampó fuera del mapa de asistencia: {sorted(fuera)}"
    # las 9 asignaturas reciben TODAS sus páginas (las 6 de 5 pgs y las 3 de 3)
    for g in (1, 4, 6):
        for i in range(9):
            faltan = set(MAPA_TEMPLATE[i]) - _EST[g]
            assert not faltan, f"grado {g}, asignatura {i}: sin estampar {sorted(faltan)}"


@test("§16 NINGUNA materia base invade las páginas de Salida Optativa (56-65)")
def _():
    for g in (4, 6):
        invadidas = _EST[g] & PAGINAS_SALIDA_OPTATIVA
        assert not invadidas, f"grado {g} invadió páginas optativas: {sorted(invadidas)}"
    # ciclo 1: esas mismas páginas son las de evaluaciones completivas
    invadidas1 = _EST[1] & PAGINAS_EVAL_CICLO_1
    assert not invadidas1, f"ciclo 1 invadió páginas de evaluaciones: {sorted(invadidas1)}"
    # y tras el hardening ya no queda ninguna rejilla sin calibrar
    assert RE.ASISTENCIA_LAYOUT_SIN_CALIBRAR == set(), RE.ASISTENCIA_LAYOUT_SIN_CALIBRAR


@test("§17 totales de páginas intactos: 170 / 238 / 240")
def _():
    esperado = {1: 170, 4: 238, 6: 240}
    for g, n in esperado.items():
        assert len(_PDF[g].pages) == n, f"grado {g}: {len(_PDF[g].pages)} != {n}"
        assert RE.GRADO_CONFIG[g]["total_paginas"] == n
    for g in (2, 3):
        assert RE.GRADO_CONFIG[g]["total_paginas"] == 170
    assert RE.GRADO_CONFIG[5]["total_paginas"] == 238


@test("§18 pipeline XObject intacto: los overlays son Form XObject /EODataOverlayN")
def _():
    for g in (1, 4, 6):
        assert _EST[g], f"grado {g} no estampó ninguna página"
        for pg in sorted(_EST[g]):
            page = _PDF[g].pages[pg - 1]
            nombres = [n for n in _xobject_names(page) if n.startswith("/EODataOverlay")]
            assert nombres, (g, pg)
            xo = page["/Resources"].get_object()["/XObject"].get_object()
            for n in nombres:
                obj = xo[n[1:] if not n.startswith("/") else n].get_object()
                assert obj.get("/Subtype") == "/Form", (g, pg, n, obj.get("/Subtype"))


@test("§19 el generador NO reintroduce merge_page()")
def _():
    import tokenize
    ruta = os.path.join(_BACKEND, "registro_escolar.py")
    with open(ruta, "rb") as fh:
        toks = list(tokenize.tokenize(fh.readline))
    for a, b in zip(toks, toks[1:]):
        if a.type == tokenize.NAME and a.string == "merge_page":
            assert not (b.type == tokenize.OP and b.string == "("), \
                f"merge_page() invocado en línea {a.start[0]}"


@test("§20 compileall del backend termina en 0")
def _():
    import subprocess
    r = subprocess.run([sys.executable, "-m", "compileall", "-q", _BACKEND],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


@test("§21 ZERO DATA LOSS: sge.db e INITIAL_CREDENTIALS.txt intactos")
def _():
    ahora_sge = os.path.getmtime(_REPO_SGE) if os.path.exists(_REPO_SGE) else None
    ahora_cred = os.path.getmtime(_REPO_CRED) if os.path.exists(_REPO_CRED) else None
    assert ahora_sge == _sge_mtime, "sge.db fue modificado"
    assert ahora_cred == _cred_mtime, "INITIAL_CREDENTIALS.txt fue modificado"
    assert _TMPDIR.replace("\\", "/") in str(engine.url).replace("\\", "/")


# ===========================================================================
# BLOQUE D — GEOMETRÍA DE LA REJILLA COMPACTA 4 MESES × 10 DÍAS (pgs 47-55)
# ===========================================================================
#
# Referencia INDEPENDIENTE del código: líneas medidas sobre los templates
# oficiales (6 grados × 9 páginas 47-55; dispersión 0.0000 pt dentro de cada
# paridad, y +0.4364 pt constante en las páginas pares). Los tests comparan el
# PDF realmente generado contra ESTOS números, no contra la tabla del módulo.

VLINES_IMPAR_TPL = [
    47.43, 58.47, 69.50, 80.53, 91.57, 102.60, 113.64, 124.67, 135.71, 146.74,
    157.77, 168.81, 179.84, 190.88, 201.91, 212.95, 223.98, 235.01, 246.05,
    257.08, 268.12, 279.15, 290.19, 301.22, 312.25, 323.29, 334.32, 345.36,
    356.39, 367.43, 378.46, 389.49, 400.53, 411.56, 422.60, 433.63, 444.67,
    455.70, 466.73, 477.77, 488.80, 499.84, 510.87, 521.90, 532.94, 543.97,
    555.01, 566.04, 577.08,
]
DX_PAR_TPL = 0.4364
FILA0_TPL = 180.485          # y_plumber de la 1ª línea horizontal de datos
ROW_H_TPL = 14.1719
FILAS_TPL = 40
TOL = 0.15                   # margen: la validación contra los dígitos
                             # impresos del template dio 0.13 pt máx.

from reportlab.pdfbase.pdfmetrics import stringWidth      # noqa: E402

IDX_ARTISTICA, IDX_FISICA, IDX_FIHR = 6, 7, 8


def _celda(pagina, bloque, col):
    """(x0, x1) de la columna `col` (0-9 días, 10=T, 11=%) del bloque."""
    dx = DX_PAR_TPL if pagina % 2 == 0 else 0.0
    i = bloque * 12 + col
    return VLINES_IMPAR_TPL[i] + dx, VLINES_IMPAR_TPL[i + 1] + dx


def _banda_fila(i):
    """(y_top, y_bottom) en coordenadas plumber de la fila del estudiante i."""
    top = FILA0_TPL + i * ROW_H_TPL
    return top, top + ROW_H_TPL


def _mes_compacto(nombre, ndias=10, nest=40):
    return {
        "nombre_mes": nombre,
        "docente": "Prof. Prueba",
        "dias_labels": list(range(1, ndias + 1)),
        "asistencias": [{"dias": ["P"] * ndias, "total": ndias, "porcentaje": 100.0}
                        for _ in range(nest)],
    }


def _generar_una(grado, asig_idx, nmeses=10, nest=40):
    """Registro con asistencia SOLO para esa asignatura: atribución inequívoca."""
    asigs = RE.ASIGNATURAS_CICLO_2 if grado >= 4 else RE.ASIGNATURAS_CICLO_1
    nombre = asigs[asig_idx]
    key = nombre.lower().replace(" ", "_").replace("-", "_")
    return RE.generar_registro_escolar(
        grado=grado,
        datos_centro={"nombre": "Centro de prueba"},
        datos_portada={"ano_escolar": "2025-2026", "seccion": "A"},
        estudiantes=[{"nombre": f"Est {i}", "apellido": "Prueba", "no_lista": i}
                     for i in range(1, nest + 1)],
        asistencia_data={key: {"meses": [_mes_compacto(f"MES{i}", nest=nest)
                                         for i in range(nmeses)]}},
    )


def _marcas(reader, pg_1based):
    """[(x, y_reportlab, texto, size)] del texto dibujado por EducaOne."""
    out = []

    def visitor(text, cm, tm, fd, fs):
        t = (text or "").strip()
        # Se descartan los agregados multilinea que pypdf emite al reagrupar y
        # el texto pre-impreso del template (que llega sin matriz propia).
        if not t or "\n" in t or (tm[4] == 0 and tm[5] == 0):
            return
        out.append((round(tm[4], 3), round(tm[5], 3), t, fs))

    reader.pages[pg_1based - 1].extract_text(visitor_text=visitor)
    return out


_PDF_ART = PdfReader(_io.BytesIO(_generar_una(4, IDX_ARTISTICA)))
_PDF_EF = PdfReader(_io.BytesIO(_generar_una(4, IDX_FISICA)))
_PDF_FIHR = PdfReader(_io.BytesIO(_generar_una(4, IDX_FIHR)))
_EST_ART = _paginas_estampadas(_PDF_ART) & set(range(17, 66))
_EST_EF = _paginas_estampadas(_PDF_EF) & set(range(17, 66))
_EST_FIHR = _paginas_estampadas(_PDF_FIHR) & set(range(17, 66))
print(f"    Ed. Artística sola -> {sorted(_EST_ART)}")
print(f"    Ed. Física sola    -> {sorted(_EST_EF)}")
print(f"    FIHR sola          -> {sorted(_EST_FIHR)}")


@test("§D0 la tabla del módulo reproduce la geometría medida del template")
def _():
    t = RE.ASISTENCIA_TABLE_4MESES
    assert t["vlines_impar"] == VLINES_IMPAR_TPL, "v-lines ≠ template"
    assert abs(t["dx_pagina_par"] - DX_PAR_TPL) < 1e-9
    assert abs(t["primera_fila_y_plumber"] - FILA0_TPL) < 1e-9
    assert abs(t["row_height"] - ROW_H_TPL) < 1e-9
    assert t["total_filas"] == FILAS_TPL
    assert t["bloques"] == 4 and t["dias_por_bloque"] == 10
    # ASISTENCIA_TABLE (2 meses) NO fue tocada por el hardening
    assert RE.ASISTENCIA_TABLE["primera_fila_y_plumber"] == 179.88
    assert RE.ASISTENCIA_TABLE["row_height"] == 14.21
    assert len(RE.ASISTENCIA_TABLE["mes_izq_dia_centers"]) == 21


@test("§D1 Educación Artística escribe SOLO en 47-49")
def _():
    assert _EST_ART == {47, 48, 49}, sorted(_EST_ART)


@test("§D2 Educación Física escribe SOLO en 50-52")
def _():
    assert _EST_EF == {50, 51, 52}, sorted(_EST_EF)


@test("§D3 FIHR escribe SOLO en 53-55")
def _():
    assert _EST_FIHR == {53, 54, 55}, sorted(_EST_FIHR)


@test("§D4 ninguna de las tres invade las páginas 56-65 (Salida Optativa)")
def _():
    for nombre, est in (("Artística", _EST_ART), ("Ed. Física", _EST_EF), ("FIHR", _EST_FIHR)):
        inv = est & PAGINAS_SALIDA_OPTATIVA
        assert not inv, f"{nombre} invadió {sorted(inv)}"


@test("§D5 ninguna invade las páginas de otra asignatura")
def _():
    assert _EST_ART & _EST_EF == set()
    assert _EST_ART & _EST_FIHR == set()
    assert _EST_EF & _EST_FIHR == set()
    otras = {p for i, pgs in MAPA_TEMPLATE.items() if i < 6 for p in pgs}
    for nombre, est in (("Artística", _EST_ART), ("Ed. Física", _EST_EF), ("FIHR", _EST_FIHR)):
        assert not (est & otras), f"{nombre} invadió páginas troncales: {sorted(est & otras)}"


@test("§D6 día 1 y día 10 caen DENTRO de su celda, en página impar y par")
def _():
    # 10 meses en 3 páginas de 4 huecos: la 3ª página solo lleva 2 bloques.
    for reader, paginas in ((_PDF_ART, (47, 48, 49)), (_PDF_EF, (50, 51, 52)),
                            (_PDF_FIHR, (53, 54, 55))):
        for p_idx, pg in enumerate(paginas):
            marcas = [m for m in _marcas(reader, pg) if m[2] == "P"]
            assert marcas, f"pg {pg} sin marcas"
            ocupados = max(0, min(4, 10 - 4 * p_idx))
            assert ocupados == (4 if p_idx < 2 else 2), (pg, ocupados)
            for bloque in range(ocupados):
                for col in (0, 9):          # día 1 y día 10
                    x0, x1 = _celda(pg, bloque, col)
                    dentro = [m for m in marcas if x0 - TOL <= m[0]
                              and m[0] + stringWidth(m[2], RE.FONT_NORMAL, m[3]) <= x1 + TOL]
                    en_celda = [m for m in dentro if x0 <= m[0] <= x1]
                    assert len(en_celda) == FILAS_TPL, (
                        f"pg {pg} bloque {bloque} col {col}: {len(en_celda)} marcas "
                        f"dentro de [{x0:.2f}, {x1:.2f}], esperadas {FILAS_TPL}")
            # y NINGUNA marca fuera de la rejilla completa
            izq, _ = _celda(pg, 0, 0)
            _, der = _celda(pg, 3, 11)
            for m in marcas:
                ancho = stringWidth(m[2], RE.FONT_NORMAL, m[3])
                assert izq - TOL <= m[0] and m[0] + ancho <= der + TOL, (pg, m)


@test("§D7 el nombre del mes 1 y del mes 4 cae dentro de su bloque")
def _():
    for reader, paginas in ((_PDF_ART, (47, 48, 49)), (_PDF_EF, (50, 51, 52)),
                            (_PDF_FIHR, (53, 54, 55))):
        for pg in paginas:
            meses = sorted((m for m in _marcas(reader, pg) if m[2].startswith("MES")),
                           key=lambda m: m[0])
            if not meses:
                continue                    # pg 3: solo quedan 2 meses de 10
            for m in meses:
                bloque = next(b for b in range(4)
                              if _celda(pg, b, 0)[0] - TOL <= m[0] < _celda(pg, b, 11)[1])
                bx0, _ = _celda(pg, bloque, 0)
                _, bx1 = _celda(pg, bloque, 11)
                ancho = stringWidth(m[2], RE.FONT_NORMAL, m[3])
                assert bx0 <= m[0] and m[0] + ancho <= bx1 + TOL, (pg, bloque, m)
            # en las dos primeras páginas los 4 bloques están ocupados
            if pg in (47, 48, 50, 51, 53, 54):
                assert len(meses) == 4, (pg, meses)


@test("§D8 estudiante 1 y estudiante 40 quedan dentro de la tabla")
def _():
    y_top_tabla = FILA0_TPL
    y_bot_tabla = FILA0_TPL + FILAS_TPL * ROW_H_TPL
    for reader, pg in ((_PDF_ART, 47), (_PDF_EF, 51), (_PDF_FIHR, 55)):
        marcas = [m for m in _marcas(reader, pg) if m[2] == "P"]
        ys = sorted({round(792 - m[1], 3) for m in marcas})   # a plumber
        assert len(ys) == FILAS_TPL, f"pg {pg}: {len(ys)} filas distintas"
        for i, y in enumerate(ys):
            top, bot = _banda_fila(i)
            assert top <= y <= bot, f"pg {pg} fila {i}: baseline {y:.2f} fuera de [{top:.2f}, {bot:.2f}]"
        assert y_top_tabla <= ys[0] and ys[-1] <= y_bot_tabla, (pg, ys[0], ys[-1])


@test("§D9/§D10/§D11 smoke 1ro / 4to / 6to: las 9 asignaturas dentro de su mapa")
def _():
    permitidas = {p for pgs in MAPA_TEMPLATE.values() for p in pgs}
    banda = set(range(17, 66))
    for g in (1, 4, 6):
        est = _EST[g] & banda
        assert est == permitidas, f"grado {g}: {sorted(est ^ permitidas)}"


@test("§D12 la rejilla compacta respeta el límite de 10 días de la hoja oficial")
def _():
    # 21 días capturados (lo que trae el constructor de datos) -> se imprimen 10
    # y ninguna marca se sale de la rejilla.
    pdf = RE.generar_registro_escolar(
        grado=4, datos_centro={"nombre": "X"},
        datos_portada={"ano_escolar": "2025-2026"},
        estudiantes=[{"nombre": f"E{i}", "apellido": "P", "no_lista": i} for i in range(1, 41)],
        asistencia_data={"educación_artística": {"meses": [{
            "nombre_mes": "AGO", "docente": "D",
            "dias_labels": list(range(1, 22)),
            "asistencias": [{"dias": ["P"] * 21, "total": 21, "porcentaje": 100.0}
                            for _ in range(40)],
        }]}})
    r = PdfReader(_io.BytesIO(pdf))
    assert len(r.pages) == 238
    marcas = [m for m in _marcas(r, 47) if m[2] == "P"]
    assert len(marcas) == 40 * 10, f"se imprimieron {len(marcas)} marcas, esperadas 400"
    _, der = _celda(47, 0, 11)
    for m in marcas:
        assert m[0] + stringWidth(m[2], RE.FONT_NORMAL, m[3]) <= der + TOL, m


# ===========================================================================
# BLOQUE F — RUTA DEGRADADA DE LA MIGRACIÓN (va al final: toca el esquema)
# ===========================================================================
#
# Un entorno que hubiera creado la tabla con la versión laxa (ano_escolar_id
# nullable) y tuviera filas con NULL. La migración NO debe inventarles un año
# ni borrarlas: debe dejarlas intactas y reportar.

@test("§F1 migración con filas ano_escolar_id NULL: no borra, no inventa, reporta")
def _():
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS curso_componentes_optativos"))
        conn.execute(text(
            "CREATE TABLE curso_componentes_optativos ("
            "  id INTEGER NOT NULL PRIMARY KEY,"
            "  colegio_id INTEGER REFERENCES colegios(id),"
            "  curso_id INTEGER NOT NULL REFERENCES cursos(id),"
            "  ano_escolar_id INTEGER REFERENCES ano_escolar(id),"   # laxa
            "  componente_codigo VARCHAR(16) NOT NULL,"
            "  asignatura_id INTEGER NOT NULL REFERENCES asignaturas(id),"
            "  activo BOOLEAN,"
            "  fecha_creacion DATETIME,"
            "  fecha_actualizacion DATETIME"
            ")"
        ))
        conn.execute(text(
            "INSERT INTO curso_componentes_optativos "
            "(id, colegio_id, curso_id, ano_escolar_id, componente_codigo, asignatura_id, activo) "
            "VALUES (1, :c, :k, NULL, 'CYT-CN-4', :a, 1)"),
            {"c": COL_A, "k": CURSO_4TO, "a": ASIG_CYT})
        conn.execute(text(
            "INSERT INTO curso_componentes_optativos "
            "(id, colegio_id, curso_id, ano_escolar_id, componente_codigo, asignatura_id, activo) "
            "VALUES (2, :c, :k, :y, 'HLM-LE-4', :a, 1)"),
            {"c": COL_A, "k": CURSO_4TO, "y": ANO_A, "a": ASIG_HLM})
        conn.commit()

    _arrancar_app()

    with engine.connect() as conn:
        filas = list(conn.execute(text(
            "SELECT id, colegio_id, curso_id, ano_escolar_id, componente_codigo, "
            "asignatura_id FROM curso_componentes_optativos ORDER BY id")))
        nullable = {c["name"]: c["nullable"] for c in
                    __import__("sqlalchemy").inspect(engine).get_columns(
                        "curso_componentes_optativos")}

    assert len(filas) == 2, f"la migración perdió filas: {filas}"
    assert filas[0][3] is None, "la migración INVENTÓ un año para la fila NULL"
    assert filas[1][3] == ANO_A, filas[1]
    assert filas[0][4] == "CYT-CN-4" and filas[1][4] == "HLM-LE-4"
    # con filas NULL presentes NO se promueve la columna: se reporta y se deja
    assert nullable["ano_escolar_id"] is True, nullable

    # restaurar el esquema correcto para no dejar la BD temporal degradada
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE curso_componentes_optativos"))
        conn.commit()
    M.Base.metadata.create_all(bind=engine)
    restaurado = {c["name"]: c["nullable"] for c in
                  __import__("sqlalchemy").inspect(engine).get_columns(
                      "curso_componentes_optativos")}
    assert restaurado["ano_escolar_id"] is False, restaurado


print(f"\n{B}{'=' * 62}{X}")
print(f"{B}RESULTADO R3.1: {_ok}/{_total} pruebas{X}")
if _fail:
    print(f"{R}FALLARON:{X}")
    for n, e in _fail:
        print(f"  - {n}: {e}")
    sys.exit(1)
print(f"{G}TODO VERDE{X}")
