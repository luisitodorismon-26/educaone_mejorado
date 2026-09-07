# -*- coding: utf-8 -*-
"""
EducaOne R1.5 — El validador del Registro OFICIAL de Secundaria valida el
modelo académico REAL (CalificacionSecundaria), no la tabla legacy Calificacion.

Regla de completitud verificada (idéntica a la puerta de _calcular_cf_secundaria):
para cada (estudiante del curso, asignatura asignada al curso):
  1. existen las 4 competencias DISTINTAS {1,2,3,4} para el AÑO ACTIVO y el
     COLEGIO actual;
  2. para cada período p∈{1,2,3,4}, las 4 competencias tienen valor_periodo(p)
     no nulo (CalificacionSecundaria.calcular_pc_periodo(comps4, p) != None).
`0` es un valor legítimo (se usa `is not None`, nunca truthiness).

SEGURIDAD DE DATOS: SQLite temporal aislada creada ANTES de importar
database/models. NUNCA toca sge.db ni ningún archivo real.

Uso:
    cd backend
    python tools/test_registro_validator_r15.py
"""
import os
import sys
import atexit
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TMPDIR = tempfile.mkdtemp(prefix="eo_reg_validator_r15_")
_TEST_DB_URL = "sqlite:///" + os.path.join(_TMPDIR, "r15.db").replace("\\", "/")
os.environ["DATABASE_URL"] = _TEST_DB_URL


@atexit.register
def _cleanup():
    try:
        import shutil
        shutil.rmtree(_TMPDIR, ignore_errors=True)
    except Exception:
        pass


from sqlalchemy import event  # noqa: E402
from database import engine, SessionLocal  # noqa: E402
import models as M  # noqa: E402
from registro_validator import validar_registro_secundaria  # noqa: E402

_eu = str(engine.url).replace("\\", "/")
assert _TMPDIR.replace("\\", "/") in _eu and "sge.db" not in _eu, _eu
_REPO_SGE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sge.db")
_sge_mtime = os.path.getmtime(_REPO_SGE) if os.path.exists(_REPO_SGE) else None


@event.listens_for(engine, "connect")
def _relax_fk(dbapi_conn, rec):
    try:
        dbapi_conn.execute("PRAGMA foreign_keys=OFF")
    except Exception:
        pass


engine.dispose()
M.Base.metadata.create_all(bind=engine)

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


# ── IDs fijos ────────────────────────────────────────────────────────────
COL_A, COL_B = 1, 2
ANO_ACT, ANO_PREV, ANO_B = 1, 2, 3        # ANO_PREV = mismo colegio A, NO activo
CURSO, GRADO = 1, 1
PROF = 9
MAT, LEN = 101, 102                       # asignaturas asignadas al curso
E1, E2 = 1001, 1002


def _reset_db():
    M.Base.metadata.drop_all(bind=engine)
    M.Base.metadata.create_all(bind=engine)


def _seed_base():
    """Curso de secundaria VÁLIDO en todo salvo las calificaciones."""
    _reset_db()
    d = SessionLocal()
    try:
        d.add(M.Colegio(id=COL_A, nombre="Colegio A", codigo="a"))
        d.add(M.Colegio(id=COL_B, nombre="Colegio B", codigo="b"))
        d.add(M.ConfiguracionColegio(colegio_id=COL_A, nombre="Colegio A",
                                     regional="10", distrito="03", codigo_centro="00001"))
        d.add(M.AnoEscolar(id=ANO_ACT, colegio_id=COL_A, nombre="2025-2026", activo=True,
                           dias_trabajados="{}"))
        d.add(M.AnoEscolar(id=ANO_PREV, colegio_id=COL_A, nombre="2024-2025", activo=False,
                           dias_trabajados="{}"))
        d.add(M.AnoEscolar(id=ANO_B, colegio_id=COL_B, nombre="2025-2026", activo=True,
                           dias_trabajados="{}"))
        d.add(M.Grado(id=GRADO, colegio_id=COL_A, nombre="1ro Secundaria", nivel="secundaria"))
        d.add(M.Curso(id=CURSO, colegio_id=COL_A, nombre="A", grado_id=GRADO))
        d.add(M.Usuario(id=PROF, username="prof", password_hash="x", nombre="Prof Titular",
                        role="profesor", colegio_id=COL_A))
        d.add(M.Asignatura(id=MAT, colegio_id=COL_A, nombre="Matemática"))
        d.add(M.Asignatura(id=LEN, colegio_id=COL_A, nombre="Lengua Española"))
        # titular + asignaciones por asignatura
        d.add(M.AsignacionProfesor(id=1, colegio_id=COL_A, profesor_id=PROF, curso_id=CURSO,
                                   asignatura_id=MAT, es_titular=True, activo=True))
        d.add(M.AsignacionProfesor(id=2, colegio_id=COL_A, profesor_id=PROF, curso_id=CURSO,
                                   asignatura_id=LEN, es_titular=False, activo=True))
        # horario de clase para cada asignatura asignada
        for i, aid in enumerate((MAT, LEN)):
            d.add(M.Horario(colegio_id=COL_A, profesor_id=PROF, curso_id=CURSO, asignatura_id=aid,
                            dia="lunes", hora_inicio="08:00", hora_fin="09:00",
                            tipo_bloque="clase", activo=True))
        # estudiantes activos del curso
        d.add(M.Estudiante(id=E1, colegio_id=COL_A, nombre="Ana", apellido="Uno",
                           curso_id=CURSO, activo=True, no_lista=1))
        d.add(M.Estudiante(id=E2, colegio_id=COL_A, nombre="Beto", apellido="Dos",
                           curso_id=CURSO, activo=True, no_lista=2))
        # asistencia mínima (>0) para que §8 no dispare "sin asistencia"
        for eid in (E1, E2):
            d.add(M.Asistencia(colegio_id=COL_A, estudiante_id=eid, curso_id=CURSO,
                               asignatura_id=MAT, fecha=date(2025, 9, 1), estado="presente"))
        d.commit()
    finally:
        d.close()


def _cs(d, est_id, asig_id, comp, ano_id=ANO_ACT, colegio_id=COL_A,
        p1=80.0, p2=80.0, p3=80.0, p4=80.0, rp1=None, rp2=None, rp3=None, rp4=None):
    d.add(M.CalificacionSecundaria(
        colegio_id=colegio_id, estudiante_id=est_id, asignatura_id=asig_id,
        ano_escolar_id=ano_id, competencia_numero=comp,
        p1=p1, p2=p2, p3=p3, p4=p4, rp1=rp1, rp2=rp2, rp3=rp3, rp4=rp4,
    ))


def _full(d, est_id, asig_id, **ov):
    for n in (1, 2, 3, 4):
        _cs(d, est_id, asig_id, n, **ov)


def _validar():
    d = SessionLocal()
    try:
        return validar_registro_secundaria(d, CURSO, COL_A)
    finally:
        d.close()


def _errs7(r):
    return [e for e in r.errors
            if "competencias/notas de secundaria" in e or "colegio de otro colegio" in e]


def _errs_legacy_style(r):
    return [e for e in r.errors if e.startswith("Faltan calificaciones en '")]


# ═══════════════════════════════════════════════════════════════════════════
@test("§F el validador YA NO usa el mensaje/consulta legacy 'Faltan calificaciones en ...'")
def _():
    import inspect
    import registro_validator as rv
    src = inspect.getsource(rv.validar_registro_secundaria)
    assert "db.query(Calificacion)" not in src, "sigue consultando Calificacion legacy"
    assert "Faltan calificaciones en '" not in src, "sigue el texto de error legacy"
    assert "db.query(CalificacionSecundaria)" in src, "no consulta CalificacionSecundaria"
    assert "calcular_pc_periodo" in src, "no valida los 4 períodos por competencia"


@test("§A 4 competencias completas para ambos estudiantes → sin error de calificaciones (§7)")
def _():
    _seed_base()
    d = SessionLocal()
    try:
        _full(d, E1, MAT); _full(d, E1, LEN)
        _full(d, E2, MAT); _full(d, E2, LEN)
        d.commit()
    finally:
        d.close()
    r = _validar()
    assert not _errs7(r), _errs7(r)
    assert r.info.get("pares_completos_secundaria") == 4, r.info
    assert r.info.get("pares_incompletos_secundaria") == 0, r.info


@test("§B falta la competencia 4 de E2 en Matemática → error específico que la nombra")
def _():
    _seed_base()
    d = SessionLocal()
    try:
        _full(d, E1, MAT); _full(d, E1, LEN); _full(d, E2, LEN)
        for n in (1, 2, 3):
            _cs(d, E2, MAT, n)         # falta la 4
        d.commit()
    finally:
        d.close()
    r = _validar()
    e7 = _errs7(r)
    assert e7, "debería fallar por competencia faltante"
    assert any("Matemática" in e and "Beto Dos" in e and "competencia(s) 4" in e for e in e7), e7


@test("§C competencias {1,2,3} + una fila espuria comp=5 → NO cuenta como 4 (falta la 4)")
def _():
    _seed_base()
    d = SessionLocal()
    try:
        _full(d, E1, LEN); _full(d, E2, MAT); _full(d, E2, LEN)
        for n in (1, 2, 3):
            _cs(d, E1, MAT, n)
        _cs(d, E1, MAT, 5)            # fila espuria: NO debe tapar la ausencia de la 4
        d.commit()
    finally:
        d.close()
    r = _validar()
    e7 = _errs7(r)
    assert any("Matemática" in e and "Ana Uno" in e and "competencia(s) 4" in e for e in e7), e7


@test("§D 4 competencias pero del AÑO ANTERIOR (no activo) → NO validan el año activo")
def _():
    _seed_base()
    d = SessionLocal()
    try:
        _full(d, E1, LEN); _full(d, E2, MAT); _full(d, E2, LEN)
        _full(d, E1, MAT, ano_id=ANO_PREV)     # año anterior
        d.commit()
    finally:
        d.close()
    r = _validar()
    e7 = _errs7(r)
    assert any("Matemática" in e and "Ana Uno" in e for e in e7), e7
    assert r.info.get("total_calificaciones_registradas") == 12, r.info  # solo las del año activo


@test("§E filas de OTRO colegio → no validan y además marcan INCONSISTENCIA de tenant")
def _():
    _seed_base()
    d = SessionLocal()
    try:
        _full(d, E1, LEN); _full(d, E2, MAT); _full(d, E2, LEN)
        _full(d, E1, MAT, colegio_id=COL_B)    # colegio ajeno
        d.commit()
    finally:
        d.close()
    r = _validar()
    e7 = _errs7(r)
    assert any("Matemática" in e and "Ana Uno" in e and "competencia" in e for e in e7), e7
    assert any("INCONSISTENCIA" in e and "otro colegio" in e for e in r.errors), r.errors


@test("§F' solo existen filas en Calificacion legacy → NO satisfacen el Registro moderno")
def _():
    _seed_base()
    d = SessionLocal()
    try:
        # completa de verdad solo LEN; MAT solo en legacy
        _full(d, E1, LEN); _full(d, E2, LEN)
        for eid in (E1, E2):
            d.add(M.Calificacion(colegio_id=COL_A, estudiante_id=eid, asignatura_id=MAT,
                                 ano_escolar_id=ANO_ACT))
        d.commit()
    finally:
        d.close()
    r = _validar()
    e7 = _errs7(r)
    assert any("Matemática" in e for e in e7), "legacy no debe satisfacer el registro moderno"


@test("§G curso/asignatura/estudiante correctos → sin falsos negativos (is_valid True)")
def _():
    _seed_base()
    d = SessionLocal()
    try:
        _full(d, E1, MAT); _full(d, E1, LEN)
        _full(d, E2, MAT); _full(d, E2, LEN)
        d.commit()
    finally:
        d.close()
    r = _validar()
    assert not _errs7(r), _errs7(r)
    assert r.is_valid, f"is_valid debería ser True; errores: {r.errors}"


@test("§H 0 es nota legítima: p1..p4 == 0 en las 4 competencias → VÁLIDO; un None → inválido")
def _():
    _seed_base()
    d = SessionLocal()
    try:
        _full(d, E1, LEN); _full(d, E2, LEN); _full(d, E2, MAT)
        _full(d, E1, MAT, p1=0.0, p2=0.0, p3=0.0, p4=0.0)   # todo ceros: válido
        d.commit()
    finally:
        d.close()
    r = _validar()
    assert not _errs7(r), f"ceros deberían validar: {_errs7(r)}"

    _seed_base()
    d = SessionLocal()
    try:
        _full(d, E1, LEN); _full(d, E2, LEN); _full(d, E2, MAT)
        _cs(d, E1, MAT, 1); _cs(d, E1, MAT, 2); _cs(d, E1, MAT, 3)
        _cs(d, E1, MAT, 4, p3=None)                          # falta P3 de la competencia 4
        d.commit()
    finally:
        d.close()
    r = _validar()
    e7 = _errs7(r)
    assert any("Matemática" in e and "Ana Uno" in e and "período(s) 3" in e for e in e7), e7


# ═══════════════════════════════════════════════════════════════════════════
print(f"\n{B}{'=' * 60}{X}")
print(f"{B}  RESUMEN R1.5{X}")
print(f"{B}{'=' * 60}{X}")
print(f"  {G}{_ok} PASARON{X} / {R}{len(_fail)} FALLARON{X}  (de {_total})")
for n, e in _fail:
    print(f"  {R}✗ {n}{X}\n      {e}")

if _sge_mtime is not None:
    now = os.path.getmtime(_REPO_SGE) if os.path.exists(_REPO_SGE) else None
    if now != _sge_mtime:
        print(f"{R}{B}✗ SEGURIDAD: sge.db del repo cambió{X}")
        sys.exit(2)
print(f"{G}✓ SEGURIDAD: sge.db del repo intacto{X}")

sys.exit(1 if _fail else 0)
