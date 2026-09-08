# -*- coding: utf-8 -*-
"""
EducaOne R2 — migración de `indicadores_logro` a identidad INSTITUCIONAL.

Arranca la aplicación REAL (lifespan → bloque de migración) contra una SQLite
temporal que tiene el esquema LEGACY:
  - sin columna ano_escolar_id
  - con el índice único legacy unique_indicador_logro
    (profesor_id, asignatura_id, curso_id, periodo, colegio_id)
y una fila previa cargada.

Verifica:
  1. la columna ano_escolar_id se agrega (aditivo, nullable);
  2. la fila previa se conserva ÍNTEGRA y se asocia al año ACTIVO de su colegio
     (si no, quedaría invisible: el listado filtra por año) — CERO PÉRDIDA;
  3. queda la clave institucional
     uq_indicador_logro_institucional(colegio_id, ano_escolar_id, curso_id,
                                      asignatura_id, periodo);
  4. la migración es IDEMPOTENTE: un segundo arranque no cambia nada.

SEGURIDAD: SQLite temporal aislada. NUNCA toca sge.db ni archivos reales.

Uso:
    cd backend
    python tools/test_indicadores_migracion_r2.py
"""
import os
import sys
import atexit
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TMPDIR = tempfile.mkdtemp(prefix="eo_ind_migra_r2_")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_TMPDIR, "m.db").replace("\\", "/")
os.environ.setdefault("ENVIRONMENT", "development")


@atexit.register
def _cleanup():
    try:
        import shutil
        shutil.rmtree(_TMPDIR, ignore_errors=True)
    except Exception:
        pass


from sqlalchemy import event, text          # noqa: E402
from database import engine, SessionLocal   # noqa: E402
import models as M                          # noqa: E402

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


COL, ANO, CURSO, ASIG, PROF = 1, 1, 1, 1, 1
CURSO_SIN_ANO = 2      # curso legacy sin ano_escolar_id
COL_AJENO, CURSO_AJENO, ANO_AJENO = 2, 3, 2   # colegio B: curso CON año, pero ajeno
CONTENIDO = "IL-1 texto histórico que NO se puede perder"

# ── 1. esquema LEGACY + fila previa ──────────────────────────────────────
M.Base.metadata.create_all(bind=engine)

# Colegio B (para la anomalía cross-tenant) vía ORM: aplica los defaults del modelo.
_dcol = SessionLocal()
try:
    _dcol.add(M.Colegio(id=COL_AJENO, nombre="Colegio B", codigo="b"))
    _dcol.commit()
finally:
    _dcol.close()

with engine.connect() as conn:
    conn.execute(text("DROP TABLE IF EXISTS indicadores_logro"))
    conn.execute(text(
        "CREATE TABLE indicadores_logro ("
        "  id INTEGER NOT NULL PRIMARY KEY,"
        "  colegio_id INTEGER REFERENCES colegios(id),"
        "  profesor_id INTEGER NOT NULL REFERENCES usuarios(id),"
        "  asignatura_id INTEGER NOT NULL REFERENCES asignaturas(id),"
        "  curso_id INTEGER NOT NULL REFERENCES cursos(id),"
        "  periodo INTEGER NOT NULL,"
        "  contenido TEXT,"
        "  fecha_creacion DATETIME,"
        "  fecha_actualizacion DATETIME"
        ")"
    ))
    conn.execute(text(
        "CREATE UNIQUE INDEX unique_indicador_logro ON indicadores_logro "
        "(profesor_id, asignatura_id, curso_id, periodo, colegio_id)"
    ))
    conn.execute(text("CREATE INDEX ix_indicadores_logro_colegio_id ON indicadores_logro (colegio_id)"))
    # año escolar ACTIVO + un curso CON año y otro SIN año (legacy)
    conn.execute(text(
        "INSERT INTO ano_escolar (id, colegio_id, nombre, activo, cerrado, periodo_activo, dias_trabajados) "
        "VALUES (:i, :c, '2025-2026', 1, 0, 1, '{}')"), {"i": ANO, "c": COL})
    conn.execute(text(
        "INSERT INTO grados (id, colegio_id, nombre, nivel) VALUES (1, :c, '1ro Secundaria', 'secundaria')"),
        {"c": COL})
    conn.execute(text(
        "INSERT INTO cursos (id, colegio_id, nombre, grado_id, ano_escolar_id) "
        "VALUES (:k, :c, 'A', 1, :y)"), {"k": CURSO, "c": COL, "y": ANO})
    conn.execute(text(
        "INSERT INTO cursos (id, colegio_id, nombre, grado_id, ano_escolar_id) "
        "VALUES (:k, :c, 'B', 1, NULL)"), {"k": CURSO_SIN_ANO, "c": COL})
    # Colegio B con su propio año y curso (para la anomalía cross-tenant)
    conn.execute(text(
        "INSERT INTO ano_escolar (id, colegio_id, nombre, activo, cerrado, periodo_activo, dias_trabajados) "
        "VALUES (:i, :c, '2025-2026', 1, 0, 1, '{}')"), {"i": ANO_AJENO, "c": COL_AJENO})
    conn.execute(text(
        "INSERT INTO cursos (id, colegio_id, nombre, grado_id, ano_escolar_id) "
        "VALUES (:k, :c, 'X', 1, :y)"), {"k": CURSO_AJENO, "c": COL_AJENO, "y": ANO_AJENO})
    # (1) indicador de un curso CON año -> debe heredar el año del CURSO
    conn.execute(text(
        "INSERT INTO indicadores_logro (id, colegio_id, profesor_id, asignatura_id, curso_id, periodo, contenido) "
        "VALUES (1, :c, :p, :a, :k, 2, :t)"),
        {"c": COL, "p": PROF, "a": ASIG, "k": CURSO, "t": CONTENIDO})
    # (2) indicador de un curso SIN año -> debe quedarse en NULL, sin inventar
    conn.execute(text(
        "INSERT INTO indicadores_logro (id, colegio_id, profesor_id, asignatura_id, curso_id, periodo, contenido) "
        "VALUES (2, :c, :p, :a, :k, 3, 'sin año determinable')"),
        {"c": COL, "p": PROF, "a": ASIG, "k": CURSO_SIN_ANO})
    # (3) ANOMALÍA cross-tenant: indicador del colegio A apuntando a un curso
    #     del colegio B (que SÍ tiene año). El backfill NO debe completarlo.
    conn.execute(text(
        "INSERT INTO indicadores_logro (id, colegio_id, profesor_id, asignatura_id, curso_id, periodo, contenido) "
        "VALUES (3, :c, :p, :a, :k, 4, 'curso de otro colegio')"),
        {"c": COL, "p": PROF, "a": ASIG, "k": CURSO_AJENO})
    conn.commit()

_cols_antes = {r[1] for r in engine.connect().execute(text("PRAGMA table_info(indicadores_logro)"))}
_idx_antes = {r[1] for r in engine.connect().execute(text("PRAGMA index_list(indicadores_logro)"))}
print(f"  ANTES  columnas: {sorted(_cols_antes)}")
print(f"  ANTES  índices : {sorted(_idx_antes)}")
assert "ano_escolar_id" not in _cols_antes
assert "unique_indicador_logro" in _idx_antes


def _arrancar_app():
    """Entra al lifespan real de la app → ejecuta el bloque de migración."""
    from fastapi.testclient import TestClient
    import app as _app
    with TestClient(_app.app):
        pass


def _estado():
    with engine.connect() as conn:
        cols = {r[1] for r in conn.execute(text("PRAGMA table_info(indicadores_logro)"))}
        idx = {r[1] for r in conn.execute(text("PRAGMA index_list(indicadores_logro)"))}
        filas = list(conn.execute(text(
            "SELECT id, colegio_id, profesor_id, asignatura_id, curso_id, periodo, "
            "contenido, ano_escolar_id FROM indicadores_logro ORDER BY id"
        )))
    return cols, idx, filas


# ── 2. primer arranque: migra ────────────────────────────────────────────
_arrancar_app()
_cols1, _idx1, _filas1 = _estado()
print(f"  DESPUÉS columnas: {sorted(_cols1)}")
print(f"  DESPUÉS índices : {sorted(_idx1)}")


@test("§C1 la columna ano_escolar_id se agrega (aditiva, nullable)")
def _():
    assert "ano_escolar_id" in _cols1, _cols1
    # ninguna columna previa desapareció
    assert _cols_antes.issubset(_cols1), _cols_antes - _cols1


@test("§C2 CERO PÉRDIDA: la fila legacy se conserva íntegra y hereda el año del CURSO")
def _():
    assert len(_filas1) == 3, _filas1
    f = next(x for x in _filas1 if x[0] == 1)
    assert f[1] == COL and f[2] == PROF and f[3] == ASIG and f[4] == CURSO
    assert f[5] == 2, "cambió el período"
    assert f[6] == CONTENIDO, "se perdió o alteró el contenido"
    assert f[7] == ANO, f"backfill incorrecto: ano_escolar_id={f[7]}"


@test("§C2-b backfill CONSERVADOR: sin año determinable NO se inventa — queda NULL y se conserva")
def _():
    g = next(x for x in _filas1 if x[0] == 2)
    assert g[6] == "sin año determinable", "se perdió o alteró el contenido"
    assert g[7] is None, f"se inventó un año: ano_escolar_id={g[7]}"


@test("§G2 backfill TENANT-SAFE: curso de OTRO colegio NO se completa, fila intacta")
def _():
    g = next(x for x in _filas1 if x[0] == 3)
    assert g[1] == COL, "cambió el colegio del indicador"
    assert g[4] == CURSO_AJENO, "cambió el curso del indicador"
    assert g[5] == 4 and g[6] == "curso de otro colegio", "se alteró la fila"
    assert g[7] is None, (
        f"se completó cruzando tenant: ano_escolar_id={g[7]} (el curso {CURSO_AJENO} "
        f"es del colegio {COL_AJENO}, el indicador del colegio {COL})"
    )


@test("§C3 queda la clave institucional y se retira la legacy dependiente del profesor")
def _():
    assert "uq_indicador_logro_institucional" in _idx1, _idx1
    assert "unique_indicador_logro" not in _idx1, "la clave legacy sobrevivió"
    with engine.connect() as conn:
        cols_uq = [r[2] for r in conn.execute(
            text("PRAGMA index_info(uq_indicador_logro_institucional)"))]
    assert cols_uq == ["colegio_id", "ano_escolar_id", "curso_id", "asignatura_id", "periodo"], cols_uq


@test("§C4 la clave institucional IMPIDE duplicados y PERMITE el año siguiente")
def _():
    with engine.connect() as conn:
        # otro profesor, mismo (colegio, año, curso, asignatura, período) -> rechazado
        fallo = False
        try:
            conn.execute(text(
                "INSERT INTO indicadores_logro (colegio_id, profesor_id, asignatura_id, curso_id, "
                "periodo, contenido, ano_escolar_id) VALUES (:c, 999, :a, :k, 2, 'paralelo', :y)"),
                {"c": COL, "a": ASIG, "k": CURSO, "y": ANO})
            conn.commit()
        except Exception:
            fallo = True
            conn.rollback()
        assert fallo, "la clave institucional permitió un duplicado por cambio de profesor"

        # MISMO profesor/curso/asignatura/período en OTRO año -> permitido
        conn.execute(text(
            "INSERT INTO ano_escolar (id, colegio_id, nombre, activo, cerrado, periodo_activo, dias_trabajados) "
            "VALUES (99, :c, '2026-2027', 0, 0, 1, '{}')"), {"c": COL})
        conn.execute(text(
            "INSERT INTO indicadores_logro (colegio_id, profesor_id, asignatura_id, curso_id, "
            "periodo, contenido, ano_escolar_id) VALUES (:c, :p, :a, :k, 2, 'año siguiente', 99)"),
            {"c": COL, "p": PROF, "a": ASIG, "k": CURSO})
        conn.commit()
        n = conn.execute(text("SELECT COUNT(*) FROM indicadores_logro")).scalar()
    # 3 filas del seed + la del año siguiente
    assert n == 4, n


@test("§C5 IDEMPOTENCIA: un segundo arranque no altera esquema ni datos")
def _():
    _arrancar_app()
    cols2, idx2, filas2 = _estado()
    assert cols2 == _cols1, (cols2 ^ _cols1)
    assert idx2 == _idx1, (idx2 ^ _idx1)
    # la fila original sigue intacta (la del año 99 se agregó en §C4)
    orig = [f for f in filas2 if f[0] == 1]
    assert len(orig) == 1 and orig[0][6] == CONTENIDO and orig[0][7] == ANO, orig
    # la fila sin año determinable sigue en NULL y con su contenido intacto
    huerf = [f for f in filas2 if f[0] == 2]
    assert len(huerf) == 1 and huerf[0][7] is None and huerf[0][6] == "sin año determinable", huerf
    # la anomalía cross-tenant sigue sin año y sin alterar tras el 2do arranque
    cruz = [f for f in filas2 if f[0] == 3]
    assert len(cruz) == 1 and cruz[0][7] is None and cruz[0][6] == "curso de otro colegio", cruz


print(f"\n{B}{'=' * 62}{X}")
print(f"{B}  RESUMEN R2 — migración indicadores_logro{X}")
print(f"{B}{'=' * 62}{X}")
print(f"  {G}{_ok} PASARON{X} / {R}{len(_fail)} FALLARON{X}  (de {_total})")
for n, e in _fail:
    print(f"  {R}✗ {n}{X}\n      {e}")

if _sge_mtime is not None:
    ahora = os.path.getmtime(_REPO_SGE) if os.path.exists(_REPO_SGE) else None
    if ahora != _sge_mtime:
        print(f"{R}{B}✗ SEGURIDAD: sge.db del repo cambió{X}")
        sys.exit(2)
print(f"{G}✓ SEGURIDAD: sge.db del repo intacto{X}")

sys.exit(1 if _fail else 0)
