# -*- coding: utf-8 -*-
"""
EducaOne v2.20.0-A .. A4 — RED DE SEGURIDAD + CARACTERIZACIÓN
Completiva + Extraordinaria + Especial de Secundaria.

Fase A  : caracterizó el comportamiento y detectó bugs.
Fase A1 : corrige redondeo académico (helper ROUND_HALF_UP), la decisión de
          entrada a Completiva y el RBAC del GET de pendientes. Esta suite se
          actualizó SOLO donde el comportamiento productivo cambió legítimamente.

Cubre:
  - reglas_academicas.redondear_calificacion_final  (== ROUND_HALF_UP)
  - EvaluacionExtraSecundaria (modelo + cascada MINERD)
  - _calcular_cf_secundaria
  - POST /api/calificaciones-secundaria/evaluacion-extra
  - GET  /api/calificaciones-secundaria/pendientes-evaluacion-extra
  - RBAC + tenant isolation

Categorías:
  [INV]  invariante que DEBE cumplirse (si falla → exit 1)
  [CAR]  caracterización / bug DIFERIDO a propósito (se reporta, NO fuerza exit 1)

SEGURIDAD DE DATOS: esta suite NUNCA borra sge.db ni ninguna DB del repo.
Usa una SQLite temporal aislada, propia de este proceso, creada ANTES de
importar database/models/app.

Uso:
    cd backend
    python tools/test_eval_extra_caracterizacion_v2200a.py
"""
import os
import sys
import atexit
import tempfile
from decimal import Decimal, ROUND_HALF_UP

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── DB TEMPORAL AISLADA (antes de cualquier import de database/models/app) ──
_TMPDIR = tempfile.mkdtemp(prefix="eo_eval_extra_test_")
_TEST_DB_PATH = os.path.join(_TMPDIR, "eval_extra_test.db")
_TEST_DB_URL = "sqlite:///" + _TEST_DB_PATH.replace("\\", "/")
os.environ["DATABASE_URL"] = _TEST_DB_URL


@atexit.register
def _cleanup_tmpdir():
    try:
        import shutil
        shutil.rmtree(_TMPDIR, ignore_errors=True)
    except Exception:
        pass


from database import engine, SessionLocal
from reglas_academicas import redondear_calificacion_final, ponderar_y_redondear
from models import (
    Base, Usuario, Grado, Curso, Asignatura, Estudiante, AnoEscolar,
    AsignacionProfesor, CalificacionSecundaria, EvaluacionExtraSecundaria,
)
Base.metadata.create_all(bind=engine)
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)

# ── ASSERT DE SEGURIDAD: el test corre contra su DB temporal, no la del repo ──
_engine_url = str(engine.url)
_tmpdir_fs = _TMPDIR.replace("\\", "/")
assert _tmpdir_fs in _engine_url.replace("\\", "/"), (
    f"SEGURIDAD: el engine NO apunta al directorio temporal del test.\n"
    f"  engine.url = {_engine_url}\n  esperado dentro de {_tmpdir_fs}"
)
assert "sge.db" not in _engine_url, "SEGURIDAD: el test estaría usando sge.db del repo"
assert os.environ["DATABASE_URL"] == _TEST_DB_URL, "SEGURIDAD: DATABASE_URL fue sobrescrito"
print(f"\033[92m✓ DB de test AISLADA:\033[0m {_engine_url}")
_REPO_SGE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sge.db")
_sge_mtime_inicial = os.path.getmtime(_REPO_SGE) if os.path.exists(_REPO_SGE) else None

G, R, Y, B, C, X = "\033[92m", "\033[91m", "\033[93m", "\033[1m", "\033[96m", "\033[0m"

inv_ok, inv_fail = [], []       # invariantes
car_ok, car_bug = [], []        # caracterización
errores = []                    # excepciones inesperadas (no AssertionError)


def check(nombre):
    """Invariante: si falla, es un problema serio → cuenta para exit 1."""
    def deco(fn):
        print(f"\n{C}▶ [INV] {nombre}{X}")
        try:
            fn(); inv_ok.append(nombre); print(f"  {G}✓ PASÓ{X}")
        except AssertionError as e:
            inv_fail.append((nombre, str(e))); print(f"  {R}✗ FALLÓ: {e}{X}")
        except Exception as e:
            errores.append((nombre, repr(e))); print(f"  {R}✗ EXCEPCIÓN: {e!r}{X}")
        return fn
    return deco


def caracteriza(nombre):
    """Caracterización contra la regla académica: si falla → BUG PREEXISTENTE."""
    def deco(fn):
        print(f"\n{C}▶ [CAR] {nombre}{X}")
        try:
            fn(); car_ok.append(nombre); print(f"  {G}✓ coincide con la regla académica{X}")
        except AssertionError as e:
            car_bug.append((nombre, str(e))); print(f"  {Y}✗ BUG CONFIRMADO: {e}{X}")
        except Exception as e:
            errores.append((nombre, repr(e))); print(f"  {R}✗ EXCEPCIÓN: {e!r}{X}")
        return fn
    return deco


# ══════════════════════════════════════════════════════════════════════════
# ORÁCULO ACADÉMICO (solo dentro del test)
# ══════════════════════════════════════════════════════════════════════════
def redondeo_academico(v):
    """Redondeo tradicional: .5 SIEMPRE sube (ROUND_HALF_UP)."""
    if v is None:
        return None
    return int(Decimal(str(v)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def cf_oficial(cf_exacta):
    """CF visible/oficial = redondeo académico de la CF exacta interna."""
    return redondeo_academico(cf_exacta)


def _ev(cf=None, cec=None, ceex=None, ce=None):
    """EvaluacionExtraSecundaria en memoria (los métodos no tocan DB)."""
    e = EvaluacionExtraSecundaria(cf_original=cf, cec=cec, ceex=ceex, ce=ce)
    return e


def _recalc(e):
    e.recalcular_todo()
    return e


# ══════════════════════════════════════════════════════════════════════════
# PARTE 1 — MODELO / FÓRMULAS / REDONDEO  (sin HTTP)
# ══════════════════════════════════════════════════════════════════════════
print(f"{B}\n=== PARTE 1: MODELO EvaluacionExtraSecundaria ==={X}")

# ---- §11: Python round() (half-to-even) vs redondeo académico (HALF_UP) ----
# Python round() NO cambia; lo que cambió (A1) es que PRODUCCIÓN ya no lo usa
# para calificaciones finales — usa reglas_academicas.redondear_calificacion_final().
BANKERS = [66.5, 67.5, 68.5, 69.5, 70.5, 71.5]
TABLA_BANKERS = []
for v in BANKERS:
    py = round(v)                              # builtin (half-to-even)
    aca = redondeo_academico(v)                # oráculo del test (HALF_UP)
    prod = redondear_calificacion_final(v)     # helper productivo A1
    TABLA_BANKERS.append((v, py, prod, aca, py == aca, prod == aca))

@check("§11-a INFORMATIVO: Python round() difiere de HALF_UP en 66.5/68.5/70.5 (por eso producción ya no lo usa)")
def _():
    difs = [f"{v}: round()={py} vs HALF_UP={aca}" for (v, py, _pr, aca, ok, _o2) in TABLA_BANKERS if not ok]
    assert difs, "se esperaba que round() divergiera (documentado); si NO diverge, revisar el oráculo"

@check("§11-b redondear_calificacion_final() == ROUND_HALF_UP para 66.5/67.5/68.5/69.5/70.5/71.5")
def _():
    difs = [f"{v}: helper={pr} vs HALF_UP={aca}" for (v, _py, pr, aca, _o, ok) in TABLA_BANKERS if not ok]
    assert not difs, "el helper productivo NO coincide con HALF_UP → " + " | ".join(difs)

# ---- §2/§10: CF exacta vs CF oficial y decisión de aprobación normal ----
CF_TABLA = [69.00, 69.49, 69.50, 69.51, 69.60, 69.80, 69.99, 70.00, 70.01]
FILAS_CF = []
for v in CF_TABLA:
    e = _recalc(_ev(cf=v))
    cf_of = cf_oficial(v)
    esperado_cond = 'aprobado_normal' if cf_of >= 70 else 'reprobado'
    esperado_fase = None if cf_of >= 70 else 'completiva'
    FILAS_CF.append({
        'cf_original': v,
        'cf_academica': cf_of,
        'condicion_final': e.condicion_final,
        'fase_pendiente': e.fase_pendiente(),
        'esperado_condicion': esperado_cond,
        'esperado_fase': esperado_fase,
        'cond_ok': e.condicion_final == esperado_cond,
        'fase_ok': e.fase_pendiente() == esperado_fase,
    })

@check("§10-a condicion_final coincide con CF oficial (>=70 → aprobado_normal) en toda la tabla 69.00–70.01")
def _():
    malas = [f"{f['cf_original']}→{f['condicion_final']} (esperado {f['esperado_condicion']})"
             for f in FILAS_CF if not f['cond_ok']]
    assert not malas, " | ".join(malas)

@check("§10-b [A1 corregido] fase_pendiente() coincide con la CF oficial (CF>=70 ⇒ None) en toda la tabla 69.00–70.01")
def _():
    malas = [f"cf_original={f['cf_original']} (CF oficial {f['cf_academica']}) → fase_pendiente()={f['fase_pendiente']!r} "
             f"(esperado {f['esperado_fase']!r})" for f in FILAS_CF if not f['fase_ok']]
    assert not malas, "inconsistencia CF-oficial vs fase_pendiente → " + " || ".join(malas)

# ---- §12: invariante duro CF oficial >= 70 ⇒ aprobado_normal + fase None ----
@check("§12 [A1 corregido] CF oficial >= 70 ⇒ condicion_final=='aprobado_normal' Y fase_pendiente()==None (69.5/69.6/69.8/69.99/70.0)")
def _():
    for v in [69.5, 69.6, 69.8, 69.99, 70.0]:
        e = _recalc(_ev(cf=v))
        assert e.condicion_final == 'aprobado_normal', f"cf_original={v}: condicion_final={e.condicion_final!r}"
        assert e.fase_pendiente() is None, f"cf_original={v}: fase_pendiente()={e.fase_pendiente()!r} (CF oficial {cf_oficial(v)} ≥ 70)"

# ---- §14 A/B/C: redondeo académico de la CF ----
@check("§14-A redondear_calificacion_final(68.5) == 69")
def _():
    assert redondear_calificacion_final(68.5) == 69

@check("§14-B redondear_calificacion_final(69.5) == 70")
def _():
    assert redondear_calificacion_final(69.5) == 70

@check("§14-C redondear_calificacion_final(69.8) == 70")
def _():
    assert redondear_calificacion_final(69.8) == 70

@check("§14-D/E/F fase_pendiente: 69.5→None, 69.8→None, 69.49→'completiva'")
def _():
    assert _recalc(_ev(cf=69.5)).fase_pendiente() is None
    assert _recalc(_ev(cf=69.8)).fase_pendiente() is None
    assert _recalc(_ev(cf=69.49)).fase_pendiente() == 'completiva'

@check("§14-G condicion_final(69.5) == 'aprobado_normal'")
def _():
    assert _recalc(_ev(cf=69.5)).condicion_final == 'aprobado_normal'

@check("§14-O Completiva/Extraordinaria conservan la BASE EXACTA para 50%/30% (no redondean cf_original antes)")
def _():
    # cf exacta 63.5: 0.5·63.5 = 31.75 (no 32); 0.3·63.5 = 19.05 (no 19.2)
    e = _ev(cf=63.5, cec=70)   # 31.75 + 35 = 66.75 → 67 ; si redondeara CF antes: 32+35=67 (coincide) → usar otro
    # Caso que distingue: cf 63.5, cec 77 → exacto 31.75+38.5 = 70.25 → 70 ; con CF pre-redondeada 64: 32+38.5 = 70.5 → 71
    e2 = _ev(cf=63.5, cec=77)
    assert e2.calcular_completiva_final() == 70, \
        f"completiva_final={e2.calcular_completiva_final()} — ¿se redondeó cf_original antes del 50%?"
    # extraordinaria: cf 63.5, ceex 90 → 0.3·63.5 + 0.7·90 = 19.05 + 63 = 82.05 → 82 ;
    #                 con CF pre-redondeada 64: 19.2 + 63 = 82.2 → 82 (no distingue) — usar ceex 85:
    #   exacto: 19.05 + 59.5 = 78.55 → 79 ; pre-redondeado: 19.2 + 59.5 = 78.7 → 79 (tampoco)
    #   probamos cf 63.5, ceex 65: exacto 19.05 + 45.5 = 64.55 → 65 ; pre: 19.2+45.5 = 64.7 → 65
    # La ponderación con .05 rara vez cruza un .5; basta con verificar que el número
    # es el de la CF EXACTA y no el de una CF entera:
    exacto = redondear_calificacion_final(0.3 * 63.5 + 0.7 * 90)
    pre_red = redondear_calificacion_final(0.3 * 64 + 0.7 * 90)
    assert _ev(cf=63.5, ceex=90).calcular_extraordinaria_final() == exacto

# ---- §5: Completiva ----
@check("§5-a Completiva Final = round(0.5·CF + 0.5·CEC) (fórmula actual, entera)")
def _():
    e = _ev(cf=63.5, cec=76)   # 31.75 + 38 = 69.75 → 70 (HALF_UP)
    assert e.calcular_completiva_final() == redondear_calificacion_final(0.5*63.5 + 0.5*76) == 70
    e2 = _ev(cf=60.0, cec=80)  # 30 + 40 = 70
    assert e2.calcular_completiva_final() == 70

@check("§5-b Completiva >= 70 ⇒ aprobado_completiva y FIN de cascada")
def _():
    e = _recalc(_ev(cf=60.0, cec=80))          # completiva_final 70
    assert e.condicion_final == 'aprobado_completiva'
    assert e.nota_final == 70
    assert e.fase_pendiente() is None

@check("§5-c Completiva < 70 ⇒ pasa a Extraordinaria")
def _():
    e = _recalc(_ev(cf=50.0, cec=60))          # 25 + 30 = 55
    assert e.completiva_final == 55
    assert e.condicion_final == 'reprobado'    # aún sin ceex
    assert e.fase_pendiente() == 'extraordinaria'

# ---- §6: Extraordinaria ----
@check("§6-a Extraordinaria Final = redondeo académico de (0.3·CF + 0.7·CEEX)")
def _():
    e = _ev(cf=50.0, ceex=80)   # 15 + 56 = 71
    assert e.calcular_extraordinaria_final() == redondear_calificacion_final(0.3*50.0 + 0.7*80) == 71

@check("§6-b Extraordinaria >= 70 ⇒ aprobado_extraordinaria y FIN")
def _():
    e = _recalc(_ev(cf=50.0, cec=40, ceex=85))  # comp 45<70 ; extra 15+59.5=74.5→74/75
    assert e.condicion_final == 'aprobado_extraordinaria'
    assert e.fase_pendiente() is None

@check("§6-c Extraordinaria < 70 ⇒ pasa a Especial")
def _():
    e = _recalc(_ev(cf=40.0, cec=30, ceex=50))  # comp 35 ; extra 12+35=47
    assert e.extraordinaria_final == 47
    assert e.fase_pendiente() == 'especial'

# ---- §7: Especial ----
@check("§7-a Especial Final = CF_oficial + CE")
def _():
    e = _ev(cf=64.0, ce=10)
    assert e.calcular_especial_final() == redondear_calificacion_final(64.0) + 10 == 74

@check("§7-b Especial >= 70 ⇒ aprobado_especial ; < 70 ⇒ reprobado")
def _():
    ap = _recalc(_ev(cf=64.0, cec=40, ceex=50, ce=6))   # 64+6=70
    assert ap.condicion_final == 'aprobado_especial'
    rp = _recalc(_ev(cf=40.0, cec=30, ceex=40, ce=10))  # 40+10=50
    assert rp.condicion_final == 'reprobado'
    assert rp.fase_pendiente() is None

@check("§7-c [A1 corregido] Especial: la base usa CF oficial HALF_UP (CF exacta 68.5 ⇒ base 69, no 68)")
def _():
    e = _ev(cf=68.5, ce=1)   # 69 + 1 = 70 (aprobado). Antes: 68 + 1 = 69 (reprobado)
    esperado = redondeo_academico(68.5) + 1
    assert e.calcular_especial_final() == esperado == 70, \
        f"especial_final={e.calcular_especial_final()} vs académico {esperado}"

# ---- §9: cascada completa, sin saltos ----
@check("§9-1 aprobado normal (CF oficial 85)")
def _():
    e = _recalc(_ev(cf=85.0))
    assert (e.condicion_final, e.nota_final, e.fase_pendiente()) == ('aprobado_normal', 85, None)

@check("§9-2 reprobado normal (CF 55) ⇒ fase 'completiva'")
def _():
    e = _recalc(_ev(cf=55.0))
    assert e.condicion_final == 'reprobado' and e.fase_pendiente() == 'completiva'

@check("§9-8 reprobado tras Especial ⇒ fase None, condicion 'reprobado'")
def _():
    e = _recalc(_ev(cf=30.0, cec=20, ceex=25, ce=5))
    assert e.condicion_final == 'reprobado' and e.fase_pendiente() is None

@check("§9 NO se puede saltar normal→extraordinaria (con CF reprobada, fase sigue siendo 'completiva' aunque ceex exista sin cec)")
def _():
    # Si por algún camino se setea ceex sin cec: fase_pendiente prioriza completiva
    e = _ev(cf=50.0, ceex=90)
    assert e.fase_pendiente() == 'completiva', f"fase_pendiente()={e.fase_pendiente()!r}"

@check("§9 NO se puede saltar completiva→especial (completiva<70 y ce seteado sin ceex ⇒ fase 'extraordinaria')")
def _():
    e = _ev(cf=50.0, cec=40, ce=30)   # comp 45<70, no hay ceex
    assert e.fase_pendiente() == 'extraordinaria', f"fase_pendiente()={e.fase_pendiente()!r}"

# ---- §13: recalcular_todo sincroniza todo ----
@check("§13 recalcular_todo() deja *_final / condicion_final / nota_final sincronizados en límites 0/69/70/100 y decimales 68.5/69.49/69.5/69.8/69.99")
def _():
    for v in [0, 69, 70, 100, 68.5, 69.49, 69.5, 69.8, 69.99]:
        e = _recalc(_ev(cf=float(v)))
        # invariantes internas de recalcular_todo
        assert e.completiva_final == e.calcular_completiva_final()
        assert e.extraordinaria_final == e.calcular_extraordinaria_final()
        assert e.especial_final == e.calcular_especial_final()
        cond, nota = e.calcular_condicion_final()
        assert (e.condicion_final, e.nota_final) == (cond, nota), f"cf={v}"

# ---- §4: cf_original conserva los decimales ----
@check("§4 cf_original NO se convierte a entero al recalcular (63.5 sigue siendo 63.5)")
def _():
    e = _recalc(_ev(cf=63.5))
    assert e.cf_original == 63.5, f"cf_original mutó a {e.cf_original}"


# ══════════════════════════════════════════════════════════════════════════
# v2.20.0-A2 — nota_final SIEMPRE entera + resultados cero no se saltan
# calcular_condicion_final(): nota_a_mostrar usa `is not None` (no `or`) y,
# cuando aún no hay ninguna evaluación extra, muestra la CF OFICIAL entera
# (cf_redondeado), nunca la CF exacta decimal. cf_original NO se toca.
# ══════════════════════════════════════════════════════════════════════════
@check("§A2-A cf=68.975 sin evaluaciones extra → cf_original==68.975, nota_final==69, fase_pendiente=='completiva'")
def _():
    e = _recalc(_ev(cf=68.975))
    assert e.cf_original == 68.975, f"cf_original mutó a {e.cf_original}"
    assert e.nota_final == 69, f"nota_final={e.nota_final!r} (esperado 69, no el decimal 68.975)"
    assert e.fase_pendiente() == 'completiva', f"fase={e.fase_pendiente()!r}"

@check("§A2-B cf=59.175 sin evaluaciones extra → nota_final==59 (CF oficial entera, no 59.175)")
def _():
    e = _recalc(_ev(cf=59.175))
    assert e.nota_final == 59, f"nota_final={e.nota_final!r} (esperado 59)"

@check("§A2-C cf=0, cec=50, ceex=50, ce=0 → especial_final==0 y nota_final==0 (NO 35: el `or` ya no salta el 0)")
def _():
    e = _recalc(_ev(cf=0, cec=50, ceex=50, ce=0))
    assert e.especial_final == 0, f"especial_final={e.especial_final!r} (esperado 0)"
    assert e.nota_final == 0, f"nota_final={e.nota_final!r} (esperado 0, NO 35)"

@check("§A2-D extraordinaria_final==0 y especial aún None → nota_final==0")
def _():
    e = _recalc(_ev(cf=0, cec=0, ceex=0, ce=None))
    assert e.especial_final is None, f"especial_final={e.especial_final!r} (esperado None)"
    assert e.extraordinaria_final == 0, f"extraordinaria_final={e.extraordinaria_final!r} (esperado 0)"
    assert e.nota_final == 0, f"nota_final={e.nota_final!r} (esperado 0)"

@check("§A2-E completiva_final==0 y fases posteriores None → nota_final==0")
def _():
    e = _recalc(_ev(cf=0, cec=0, ceex=None, ce=None))
    assert e.extraordinaria_final is None and e.especial_final is None
    assert e.completiva_final == 0, f"completiva_final={e.completiva_final!r} (esperado 0)"
    assert e.nota_final == 0, f"nota_final={e.nota_final!r} (esperado 0)"

@check("§A2-F cf=69.5 aprobado normal → nota_final==70, condicion_final=='aprobado_normal', fase_pendiente()==None")
def _():
    e = _recalc(_ev(cf=69.5))
    assert e.nota_final == 70, f"nota_final={e.nota_final!r}"
    assert e.condicion_final == 'aprobado_normal', f"condicion_final={e.condicion_final!r}"
    assert e.fase_pendiente() is None, f"fase={e.fase_pendiente()!r}"


# ══════════════════════════════════════════════════════════════════════════
# v2.20.0-A3 — PRECISIÓN DECIMAL EN LAS PONDERACIONES 50/50 y 30/70
# La ponderación se hace ENTERAMENTE en Decimal desde los operandos
# (ponderar_y_redondear), no en float antes de envolver en Decimal. Un
# resultado matemático exacto de 69.5 debe subir a 70 (HALF_UP), sin que
# un artefacto float 69.49999999999999 lo tumbe a 69.
# ══════════════════════════════════════════════════════════════════════════

def _extra_float_viejo(cf, ceex):
    """Ruta A2 (float primero, Decimal después) — para contraste en los tests."""
    return redondear_calificacion_final(0.3 * cf + 0.7 * ceex)

def _comp_float_viejo(cf, cec):
    return redondear_calificacion_final(0.5 * cf + 0.5 * cec)

@check("§A3-1 helper ponderar_y_redondear: 0.3·17 + 0.7·92 = 69.5 → 70 (la ruta float vieja daba 69)")
def _():
    assert ponderar_y_redondear(17, "0.3", 92, "0.7") == 70, ponderar_y_redondear(17, "0.3", 92, "0.7")
    assert _extra_float_viejo(17, 92) == 69, "se esperaba que la ruta float vieja fallara con 69"
    # exactitud de la aritmética Decimal
    assert (Decimal("0.3") * Decimal("17") + Decimal("0.7") * Decimal("92")) == Decimal("69.5")

@check("§A3-2 BLOCKER CF=17, CEEX=92 → extraordinaria_final==70, condicion=='aprobado_extraordinaria', fase_pendiente()==None")
def _():
    # cec se incluye porque en la cascada real un estudiante que rinde
    # Extraordinaria ya pasó por Completiva; con cec<... la completiva queda <70
    # y la decisión depende de la Extraordinaria (que es el objeto del blocker).
    e = _recalc(_ev(cf=17, cec=40, ceex=92))
    assert e.completiva_final == 29 and e.completiva_final < 70, f"completiva_final={e.completiva_final!r}"
    assert e.extraordinaria_final == 70, f"extraordinaria_final={e.extraordinaria_final!r} (esperado 70)"
    assert e.condicion_final == 'aprobado_extraordinaria', f"condicion_final={e.condicion_final!r}"
    assert e.fase_pendiente() is None, f"fase={e.fase_pendiente()!r}"
    assert e.nota_final == 70, f"nota_final={e.nota_final!r}"
    assert e.cf_original == 17, f"cf_original mutó a {e.cf_original!r}"
    # el resultado exacto es 0.3·17 + 0.7·92 = 69.5 (la ruta float vieja daba 69)
    assert _extra_float_viejo(17, 92) == 69

@check("§A3-3 BLOCKER CF=64.6, CEEX=71.6 → 0.3·64.6 + 0.7·71.6 = 19.38 + 50.12 = 69.5 → extraordinaria_final==70")
def _():
    e = _recalc(_ev(cf=64.6, cec=60, ceex=71.6))
    assert e.completiva_final == 62 and e.completiva_final < 70, f"completiva_final={e.completiva_final!r}"
    assert e.extraordinaria_final == 70, f"extraordinaria_final={e.extraordinaria_final!r} (esperado 70, no 69)"
    assert e.condicion_final == 'aprobado_extraordinaria', f"condicion_final={e.condicion_final!r}"
    assert e.fase_pendiente() is None, f"fase={e.fase_pendiente()!r}"
    assert e.cf_original == 64.6, f"cf_original mutó a {e.cf_original!r}"
    assert _extra_float_viejo(64.6, 71.6) == 69

@check("§A3-4 NO inflar: CF=17, CEC=40, CEEX=91.9 → 0.3·17 + 0.7·91.9 = 69.43 (< 69.5) → extraordinaria_final==69, sigue reprobado")
def _():
    e = _recalc(_ev(cf=17, cec=40, ceex=91.9))
    assert e.extraordinaria_final == 69, f"extraordinaria_final={e.extraordinaria_final!r} (esperado 69)"
    assert e.condicion_final == 'reprobado', f"condicion_final={e.condicion_final!r}"
    assert e.fase_pendiente() == 'especial', f"fase={e.fase_pendiente()!r}"

@check("§A3-5 Completiva conserva 50/50 sobre CF EXACTA con redondeo HALF_UP: cf=69,cec=70 → 69.5 → 70 ; cf=68.975,cec=70.025 → 69.5 → 70")
def _():
    assert _recalc(_ev(cf=69, cec=70)).completiva_final == 70
    e = _recalc(_ev(cf=68.975, cec=70.025))
    assert (Decimal("0.5") * Decimal("68.975") + Decimal("0.5") * Decimal("70.025")) == Decimal("69.500000")
    assert e.completiva_final == 70, f"completiva_final={e.completiva_final!r} (esperado 70 por HALF_UP)"
    # y no usa la CF oficial como base (68.975 → base exacta, no 69)
    e2 = _recalc(_ev(cf=63.5, cec=77))   # exacto 31.75 + 38.5 = 70.25 → 70 ; con CF pre-red 64: 71
    assert e2.completiva_final == 70

@check("§A3-6 Completiva 50/50: Decimal-desde-operandos == valor matemático exacto en toda la rejilla cf∈{0..69.9/.1}, cec∈{0..100}")
def _():
    cf = 0.0
    peor = None
    while cf <= 69.9 + 1e-9:
        cfr = round(cf, 1)
        for cec in range(0, 101):
            got = ponderar_y_redondear(cfr, "0.5", cec, "0.5")
            exact = int((Decimal(str(cfr)) * Decimal("0.5") + Decimal(str(cec)) * Decimal("0.5"))
                        .quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            if got != exact:
                peor = (cfr, cec, got, exact)
        cf = round(cf + 0.1, 1)
    assert peor is None, f"divergencia Decimal vs exacto en {peor}"

@check("§A3-7 Extraordinaria 30/70: ponderar_y_redondear NUNCA queda por debajo del valor matemático exacto (no baja notas) — rejilla cf∈{0..69.9/.1}, ceex∈{0..100}")
def _():
    cf = 0.0
    bajas = []
    while cf <= 69.9 + 1e-9:
        cfr = round(cf, 1)
        for ceex in range(0, 101):
            got = ponderar_y_redondear(cfr, "0.3", ceex, "0.7")
            exact = int((Decimal(str(cfr)) * Decimal("0.3") + Decimal(str(ceex)) * Decimal("0.7"))
                        .quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            if got < exact:
                bajas.append((cfr, ceex, got, exact))
        cf = round(cf + 0.1, 1)
    assert not bajas, f"A3 quedó por debajo del exacto en {bajas[:5]}"

@check("§A3-8 ponderar_y_redondear acepta int/float/Decimal indistintamente y da el mismo entero")
def _():
    from decimal import Decimal as D
    r_int = ponderar_y_redondear(17, "0.3", 92, "0.7")
    r_float = ponderar_y_redondear(17.0, "0.3", 92.0, "0.7")
    r_dec = ponderar_y_redondear(D("17"), D("0.3"), D("92"), D("0.7"))
    assert r_int == r_float == r_dec == 70, (r_int, r_float, r_dec)
    assert ponderar_y_redondear(None, "0.5", 70, "0.5") is None
    assert ponderar_y_redondear(50, "0.5", None, "0.5") is None


# ══════════════════════════════════════════════════════════════════════════
# PARTE 2 — ENDPOINTS (RBAC / tenant / cascada / backfill)
# ══════════════════════════════════════════════════════════════════════════
print(f"{B}\n=== PARTE 2: ENDPOINTS ==={X}")


def auth(t):
    return {'Authorization': f'Bearer {t}'}


def _limpiar(u):
    d = SessionLocal()
    try:
        x = d.query(Usuario).filter_by(username=u).first()
        if x and x.must_change_password:
            x.must_change_password = False
            d.commit()
    finally:
        d.close()


def login(u, p):
    _limpiar(u)
    return client.post('/api/auth/login', json={'username': u, 'password': p}).json().get('token')


def set_nivel(username, nivel):
    d = SessionLocal()
    try:
        u = d.query(Usuario).filter_by(username=username).first()
        u.nivel_asignado = nivel
        d.commit()
    finally:
        d.close()


def _set_cf(estudiante_id, asignatura_id, ano_id, cf, colegio_id):
    """Crea/actualiza la fila EvaluacionExtraSecundaria a estado 'CF recién
    calculado, ninguna fase extra cargada' (simula el cache del POST de notas).
    Limpia cec/ceex/ce para que cada test parta de cero — es un HELPER DE TEST,
    no toca producción."""
    d = SessionLocal()
    try:
        ev = d.query(EvaluacionExtraSecundaria).filter_by(
            estudiante_id=estudiante_id, asignatura_id=asignatura_id, ano_escolar_id=ano_id
        ).first()
        if not ev:
            ev = EvaluacionExtraSecundaria(estudiante_id=estudiante_id, asignatura_id=asignatura_id,
                                           ano_escolar_id=ano_id, colegio_id=colegio_id)
            d.add(ev)
        ev.cf_original = cf
        ev.cec = None
        ev.ceex = None
        ev.ce = None
        ev.recalcular_todo()
        d.commit()
        return ev.id
    finally:
        d.close()


def _ev_row(estudiante_id, asignatura_id, ano_id):
    d = SessionLocal()
    try:
        ev = d.query(EvaluacionExtraSecundaria).filter_by(
            estudiante_id=estudiante_id, asignatura_id=asignatura_id, ano_escolar_id=ano_id
        ).first()
        if not ev:
            return None
        return {'cec': ev.cec, 'ceex': ev.ceex, 'ce': ev.ce,
                'completiva_final': ev.completiva_final, 'extraordinaria_final': ev.extraordinaria_final,
                'especial_final': ev.especial_final, 'condicion_final': ev.condicion_final,
                'nota_final': ev.nota_final}
    finally:
        d.close()


with client:
    SA = login('superadmin', 'superadmin123')
    client.post('/api/superadmin/colegios', json={
        'nombre': 'Colegio B', 'codigo': 'b', 'plan': 'enterprise',
        'admin_username': 'dir_b', 'admin_password': 'AdminB2026x',
        'plan_secundaria': True, 'plan_primaria': True,
    }, headers=auth(SA))
    DIR_A = login('direccion', 'admin123')
    DIR_B = login('dir_b', 'AdminB2026x')

    def montar(tok, sfx, dir_username):
        d = SessionLocal()
        try:
            cid = d.query(Usuario).filter_by(username=dir_username).first().colegio_id
        finally:
            d.close()
        grados = client.get('/api/grados', headers=auth(tok)).json()
        tandas = client.get('/api/tandas', headers=auth(tok)).json()
        asigs = client.get('/api/asignaturas', headers=auth(tok)).json()
        if not asigs:
            asigs = [client.post('/api/asignaturas', json={'nombre': 'Matemática', 'codigo': 'MAT'},
                                 headers=auth(tok)).json()]
        gs = next(g for g in grados if g['nivel'] == 'secundaria')
        matutina = next((t for t in tandas if t['nombre'] == 'Matutina'), tandas[0])
        asig = asigs[0]['id']
        asig2 = asigs[1]['id'] if len(asigs) > 1 else client.post(
            '/api/asignaturas', json={'nombre': f'Otra {sfx}', 'codigo': f'O{sfx}'}, headers=auth(tok)).json()['id']
        cs = client.post('/api/cursos', json={'grado_id': gs['id'], 'tanda_id': matutina['id'], 'nombre': 'A'},
                         headers=auth(tok)).json()['id']

        def _prof(u):
            client.post('/api/usuarios', json={'username': u, 'password': 'Temporal2026x',
                'nombre': u, 'apellido': sfx.upper(), 'email': f'{u}@x.com', 'role': 'profesor'}, headers=auth(tok))
            dd = SessionLocal()
            try:
                return dd.query(Usuario).filter_by(username=u).first().id
            finally:
                dd.close()

        prof = _prof(f'prof_ee_{sfx}')       # asignación ACTIVA a (cs, asig)
        prof_inact = _prof(f'prof_inact_{sfx}')  # asignación que luego se desactiva
        client.post('/api/usuarios', json={'username': f'coord_ee_{sfx}', 'password': 'Temporal2026x',
            'nombre': 'Coord', 'apellido': sfx.upper(), 'email': f'coord_{sfx}@x.com', 'role': 'coordinador'}, headers=auth(tok))
        client.post('/api/usuarios', json={'username': f'sec_ee_{sfx}', 'password': 'Temporal2026x',
            'nombre': 'Sec', 'apellido': sfx.upper(), 'email': f'sec_{sfx}@x.com', 'role': 'secretaria'}, headers=auth(tok))

        client.post('/api/asignaciones', json={'profesor_id': prof, 'curso_id': cs, 'asignatura_id': asig}, headers=auth(tok))
        asg_inact = client.post('/api/asignaciones', json={'profesor_id': prof_inact, 'curso_id': cs, 'asignatura_id': asig}, headers=auth(tok)).json()
        # desactivar la asignación de prof_inact
        d = SessionLocal()
        try:
            row = d.query(AsignacionProfesor).filter_by(profesor_id=prof_inact, curso_id=cs, asignatura_id=asig).first()
            if row:
                row.activo = False
                d.commit()
        finally:
            d.close()

        est = client.post('/api/estudiantes', json={'nombre': 'Est', 'apellido': sfx.upper(), 'sexo': 'M',
            'fecha_nacimiento': '2010-01-01', 'curso_id': cs, 'no_lista': 1, 'matricula': f'M-{sfx}'}, headers=auth(tok)).json()['id']
        est2 = client.post('/api/estudiantes', json={'nombre': 'Est2', 'apellido': sfx.upper(), 'sexo': 'F',
            'fecha_nacimiento': '2010-02-02', 'curso_id': cs, 'no_lista': 2, 'matricula': f'M2-{sfx}'}, headers=auth(tok)).json()['id']

        ano = client.get('/api/ano-escolar', headers=auth(tok)).json()
        ano_id = (ano[0]['id'] if isinstance(ano, list) and ano else
                  (ano.get('id') if isinstance(ano, dict) else None))
        if ano_id is None:
            dd = SessionLocal()
            try:
                a = dd.query(AnoEscolar).filter_by(colegio_id=cid, activo=True).first()
                ano_id = a.id if a else None
            finally:
                dd.close()

        return dict(colegio_id=cid, cs=cs, asig=asig, asig2=asig2, prof=prof, prof_inact=prof_inact,
                    est=est, est2=est2, ano_id=ano_id, sfx=sfx)

    A = montar(DIR_A, 'a', 'direccion')
    Bc = montar(DIR_B, 'b', 'dir_b')
    set_nivel(f'coord_ee_a', 'secundaria')
    print(f"  {G}✓{X} 2 colegios de secundaria montados (prof activo, prof inactivo, coord, secretaria)")

    PROF_A = login('prof_ee_a', 'Temporal2026x')
    PROF_INACT_A = login('prof_inact_a', 'Temporal2026x')
    COORD_A = login('coord_ee_a', 'Temporal2026x')
    SEC_A = login('sec_ee_a', 'Temporal2026x')
    PROF_B = login('prof_ee_b', 'Temporal2026x')

    def post_extra(tok, est, asig, tipo, nota):
        return client.post('/api/calificaciones-secundaria/evaluacion-extra',
                           json={'estudiante_id': est, 'asignatura_id': asig, 'tipo': tipo, 'nota': nota},
                           headers=auth(tok))

    def get_pend(tok, **params):
        return client.get('/api/calificaciones-secundaria/pendientes-evaluacion-extra',
                          params=params, headers=auth(tok))

    # ── §14: RBAC del POST ──────────────────────────────────────────────
    @check("§14-A profesor con asignación ACTIVA + CF reprobada puede guardar Completiva (200)")
    def _():
        _set_cf(A['est'], A['asig'], A['ano_id'], 55.0, A['colegio_id'])
        r = post_extra(PROF_A, A['est'], A['asig'], 'completiva', 40)
        assert r.status_code == 200, f"{r.status_code}: {r.text}"

    @check("§14-B profesor SIN asignación a esa asignatura → 403")
    def _():
        _set_cf(A['est'], A['asig2'], A['ano_id'], 55.0, A['colegio_id'])
        r = post_extra(PROF_A, A['est'], A['asig2'], 'completiva', 40)   # asig2 no asignada
        assert r.status_code == 403, f"{r.status_code}: {r.text}"

    @check("§14-C profesor con asignación INACTIVA → 403")
    def _():
        _set_cf(A['est'], A['asig'], A['ano_id'], 55.0, A['colegio_id'])
        r = post_extra(PROF_INACT_A, A['est'], A['asig'], 'completiva', 40)
        assert r.status_code == 403, f"{r.status_code}: {r.text}"

    @check("§14-D dirección → 403")
    def _():
        r = post_extra(DIR_A, A['est'], A['asig'], 'completiva', 40)
        assert r.status_code == 403, f"{r.status_code}: {r.text}"

    @check("§14-E coordinador → 403")
    def _():
        r = post_extra(COORD_A, A['est'], A['asig'], 'completiva', 40)
        assert r.status_code == 403, f"{r.status_code}: {r.text}"

    @check("§14-F secretaría → 403")
    def _():
        r = post_extra(SEC_A, A['est'], A['asig'], 'completiva', 40)
        assert r.status_code == 403, f"{r.status_code}: {r.text}"

    @check("§14-G profesor de otro colegio NO puede escribir en estudiante ajeno (403/404)")
    def _():
        _set_cf(A['est'], A['asig'], A['ano_id'], 55.0, A['colegio_id'])
        r = post_extra(PROF_B, A['est'], A['asig'], 'completiva', 40)
        assert r.status_code in (403, 404), f"{r.status_code}: {r.text}"
        # y no se creó/tocó nada en tenant A por esa vía
        row = _ev_row(A['est'], A['asig'], A['ano_id'])
        assert row is not None  # ya existía por _set_cf

    # ── §15: aprobado normal NO entra a Completiva (corte con CF oficial) ──
    @check("§15/§14-I cf_original=69.49 (CF oficial 69) → el endpoint PERMITE Completiva (200)")
    def _():
        _set_cf(A['est2'], A['asig'], A['ano_id'], 69.49, A['colegio_id'])
        r = post_extra(PROF_A, A['est2'], A['asig'], 'completiva', 50)
        assert r.status_code == 200, f"{r.status_code}: {r.text}"

    @check("§15/§14-H cf_original=69.50 (CF oficial 70) → el endpoint RECHAZA Completiva (400)")
    def _():
        _set_cf(A['est2'], A['asig'], A['ano_id'], 69.50, A['colegio_id'])
        r = post_extra(PROF_A, A['est2'], A['asig'], 'completiva', 50)
        assert r.status_code == 400, f"esperado 400 (aprobó normal), obtuvo {r.status_code}: {r.text}"

    @check("§15 cf_original=69.80 (CF oficial 70) → el endpoint RECHAZA Completiva (400)")
    def _():
        _set_cf(A['est2'], A['asig'], A['ano_id'], 69.80, A['colegio_id'])
        r = post_extra(PROF_A, A['est2'], A['asig'], 'completiva', 50)
        assert r.status_code == 400, f"esperado 400, obtuvo {r.status_code}: {r.text}"

    @check("§15 cf_original=69.99 (CF oficial 70) → el endpoint RECHAZA Completiva (400)")
    def _():
        _set_cf(A['est2'], A['asig'], A['ano_id'], 69.99, A['colegio_id'])
        r = post_extra(PROF_A, A['est2'], A['asig'], 'completiva', 50)
        assert r.status_code == 400, f"esperado 400, obtuvo {r.status_code}: {r.text}"

    # ── §16: corrección de fases ────────────────────────────────────────
    @check("§16-A se puede corregir Completiva cuando es la última fase cargada")
    def _():
        _set_cf(A['est'], A['asig'], A['ano_id'], 55.0, A['colegio_id'])
        assert post_extra(PROF_A, A['est'], A['asig'], 'completiva', 40).status_code == 200
        r = post_extra(PROF_A, A['est'], A['asig'], 'completiva', 88)  # corrección
        assert r.status_code == 200, f"{r.status_code}: {r.text}"
        row = _ev_row(A['est'], A['asig'], A['ano_id'])
        assert row['cec'] == 88

    @caracteriza("§16-B [DIFERIDO] corregir Completiva con Extraordinaria ya cargada — bloqueado (400). Política académica pendiente.")
    def _():
        _set_cf(A['est'], A['asig'], A['ano_id'], 40.0, A['colegio_id'])
        assert post_extra(PROF_A, A['est'], A['asig'], 'completiva', 30).status_code == 200      # comp 35<70
        assert post_extra(PROF_A, A['est'], A['asig'], 'extraordinaria', 50).status_code == 200  # extra 47<70
        r = post_extra(PROF_A, A['est'], A['asig'], 'completiva', 95)   # corrección de completiva
        assert r.status_code == 200, f"esperado 200 (corrección con limpieza), obtuvo {r.status_code}: {r.text}"
        row = _ev_row(A['est'], A['asig'], A['ano_id'])
        assert row['cec'] == 95 and row['ceex'] is None and row['ce'] is None, \
            f"esperado ceex/ce limpiados; row={row}"

    @caracteriza("§16-C [DIFERIDO] corregir Extraordinaria con Especial ya cargada — bloqueado (400). Política académica pendiente.")
    def _():
        _set_cf(A['est'], A['asig'], A['ano_id'], 40.0, A['colegio_id'])
        assert post_extra(PROF_A, A['est'], A['asig'], 'completiva', 30).status_code == 200
        assert post_extra(PROF_A, A['est'], A['asig'], 'extraordinaria', 40).status_code == 200  # extra 40<70
        assert post_extra(PROF_A, A['est'], A['asig'], 'especial', 5).status_code == 200
        r = post_extra(PROF_A, A['est'], A['asig'], 'extraordinaria', 95)  # corrección
        assert r.status_code == 200, f"esperado 200, obtuvo {r.status_code}: {r.text}"
        row = _ev_row(A['est'], A['asig'], A['ano_id'])
        assert row['ceex'] == 95 and row['ce'] is None, f"esperado ce limpiado; row={row}"

    @check("§16-D corregir Especial: no toca fases anteriores")
    def _():
        _set_cf(A['est'], A['asig'], A['ano_id'], 40.0, A['colegio_id'])
        assert post_extra(PROF_A, A['est'], A['asig'], 'completiva', 30).status_code == 200
        assert post_extra(PROF_A, A['est'], A['asig'], 'extraordinaria', 40).status_code == 200
        assert post_extra(PROF_A, A['est'], A['asig'], 'especial', 5).status_code == 200
        r = post_extra(PROF_A, A['est'], A['asig'], 'especial', 8)
        assert r.status_code == 200, f"{r.status_code}: {r.text}"
        row = _ev_row(A['est'], A['asig'], A['ano_id'])
        assert row['cec'] == 30 and row['ceex'] == 40 and row['ce'] == 8

    @check("§9-endpoint NO se puede saltar completiva→especial vía endpoint (400)")
    def _():
        _set_cf(A['est'], A['asig'], A['ano_id'], 40.0, A['colegio_id'])
        # sin cargar completiva, intentar especial
        d = SessionLocal()
        try:
            ev = d.query(EvaluacionExtraSecundaria).filter_by(
                estudiante_id=A['est'], asignatura_id=A['asig'], ano_escolar_id=A['ano_id']).first()
            ev.cec = None; ev.ceex = None; ev.ce = None; ev.recalcular_todo(); d.commit()
        finally:
            d.close()
        r = post_extra(PROF_A, A['est'], A['asig'], 'especial', 10)
        assert r.status_code == 400, f"{r.status_code}: {r.text}"

    # ── §17: RBAC del GET pendientes ───────────────────────────────────
    @check("§17-a dirección ve pendientes de su colegio (200)")
    def _():
        r = get_pend(DIR_A)
        assert r.status_code == 200 and 'pendientes' in r.json()

    @check("§17-b coordinador de secundaria ve pendientes (200)")
    def _():
        r = get_pend(COORD_A)
        assert r.status_code == 200 and 'pendientes' in r.json()

    @check("§17-c profesor con asignación ACTIVA ve solo sus cursos/asignaturas (200)")
    def _():
        _set_cf(A['est'], A['asig'], A['ano_id'], 55.0, A['colegio_id'])
        r = get_pend(PROF_A)
        assert r.status_code == 200
        for p in r.json().get('pendientes', []):
            assert p['asignatura_id'] == A['asig']

    @check("§17-d [A1 corregido] §14-K profesor con asignación INACTIVA NO ve pendientes de ese curso/asignatura")
    def _():
        _set_cf(A['est'], A['asig'], A['ano_id'], 55.0, A['colegio_id'])
        r = get_pend(PROF_INACT_A)
        assert r.status_code == 200, r.text
        pend = r.json().get('pendientes', [])
        assert not any(p['asignatura_id'] == A['asig'] and p['estudiante_id'] == A['est'] for p in pend), \
            f"profesor con asignación INACTIVA ve pendientes: {pend}"

    @check("§17-e [A1 corregido] §14-J secretaría NO accede al GET de pendientes (403)")
    def _():
        r = get_pend(SEC_A)
        assert r.status_code == 403, f"esperado 403, obtuvo {r.status_code} (body: {r.text[:120]})"

    @check("§14-L profesor con asignación ACTIVA solo ve pendientes de SUS asignaciones")
    def _():
        _set_cf(A['est'], A['asig'], A['ano_id'], 55.0, A['colegio_id'])
        _set_cf(A['est'], A['asig2'], A['ano_id'], 55.0, A['colegio_id'])  # asig2 NO asignada a PROF_A
        r = get_pend(PROF_A)
        assert r.status_code == 200
        for p in r.json().get('pendientes', []):
            assert p['asignatura_id'] == A['asig'], f"ve pendiente de asignatura ajena: {p}"

    @check("§17-f profesor de otro colegio jamás ve pendientes del colegio A")
    def _():
        _set_cf(A['est'], A['asig'], A['ano_id'], 55.0, A['colegio_id'])
        r = get_pend(PROF_B)
        assert r.status_code == 200
        for p in r.json().get('pendientes', []):
            assert p['estudiante_id'] != A['est']

    # ── §A4: RBAC por PAREJA EXACTA (curso_id, asignatura_id) ───────────
    # Bug objetivo: el filtro del profesor separaba set(cursos) y
    # set(asignaturas) y filtraba `curso IN cursos AND asignatura IN asigs`
    # → producto cartesiano. Con asignaciones (C1,MAT) y (C2,CIE) autorizaba
    # también (C1,CIE) y (C2,MAT).
    def _montar_a4():
        grados = client.get('/api/grados', headers=auth(DIR_A)).json()
        tandas = client.get('/api/tandas', headers=auth(DIR_A)).json()
        gs = next(g for g in grados if g['nivel'] == 'secundaria')
        mat_tanda = next((t for t in tandas if t['nombre'] == 'Matutina'), tandas[0])
        C1 = A['cs']                      # curso ya existente ("A")
        C2 = client.post('/api/cursos', json={'grado_id': gs['id'], 'tanda_id': mat_tanda['id'],
                                              'nombre': 'A4-C2'}, headers=auth(DIR_A)).json()['id']
        MAT = A['asig']                   # "Matemática"
        CIE = A['asig2']                  # otra asignatura
        client.post('/api/usuarios', json={'username': 'prof_a4', 'password': 'Temporal2026x',
            'nombre': 'ProfA4', 'apellido': 'A', 'email': 'prof_a4@x.com', 'role': 'profesor'},
            headers=auth(DIR_A))
        d = SessionLocal()
        try:
            p4 = d.query(Usuario).filter_by(username='prof_a4').first().id
        finally:
            d.close()
        # SOLO estas dos parejas, ambas activas
        client.post('/api/asignaciones', json={'profesor_id': p4, 'curso_id': C1, 'asignatura_id': MAT}, headers=auth(DIR_A))
        client.post('/api/asignaciones', json={'profesor_id': p4, 'curso_id': C2, 'asignatura_id': CIE}, headers=auth(DIR_A))
        est_c1 = A['est']                 # estudiante ya existente en C1
        est_c2 = client.post('/api/estudiantes', json={'nombre': 'EstC2', 'apellido': 'A', 'sexo': 'M',
            'fecha_nacimiento': '2010-03-03', 'curso_id': C2, 'no_lista': 1, 'matricula': 'M-A4C2'},
            headers=auth(DIR_A)).json()['id']
        # CF<70 en las 4 combinaciones (est, asig)
        for (e_id, a_id) in [(est_c1, MAT), (est_c1, CIE), (est_c2, MAT), (est_c2, CIE)]:
            _set_cf(e_id, a_id, A['ano_id'], 55.0, A['colegio_id'])
        return dict(C1=C1, C2=C2, MAT=MAT, CIE=CIE, p4=p4, est_c1=est_c1, est_c2=est_c2)

    A4 = _montar_a4()
    PROF_A4 = login('prof_a4', 'Temporal2026x')

    def _pares_vistos(resp):
        """{(estudiante_id, asignatura_id)} de los pendientes devueltos."""
        return {(p['estudiante_id'], p['asignatura_id']) for p in resp.json().get('pendientes', [])}

    @check("§A4-1 profesor con (C1,MAT)+(C2,CIE): ve exactamente esas parejas, NO las cruzadas (C1,CIE)/(C2,MAT)")
    def _():
        r = get_pend(PROF_A4)
        assert r.status_code == 200, r.text
        vistos = _pares_vistos(r)
        assert (A4['est_c1'], A4['MAT']) in vistos, f"C1+MAT debería ser visible; vistos={vistos}"
        assert (A4['est_c2'], A4['CIE']) in vistos, f"C2+CIE debería ser visible; vistos={vistos}"
        assert (A4['est_c1'], A4['CIE']) not in vistos, f"CRUCE C1+CIE visible (no autorizado); vistos={vistos}"
        assert (A4['est_c2'], A4['MAT']) not in vistos, f"CRUCE C2+MAT visible (no autorizado); vistos={vistos}"

    @check("§A4-2 query param ?curso_id=C2 no revela (C2,MAT) ni ninguna pareja no asignada")
    def _():
        r = get_pend(PROF_A4, curso_id=A4['C2'])
        assert r.status_code == 200, r.text
        vistos = _pares_vistos(r)
        assert vistos <= {(A4['est_c2'], A4['CIE'])}, f"con ?curso_id=C2 el profesor ve {vistos}"

    @check("§A4-3 query param ?asignatura_id=MAT solo devuelve (C1,MAT); ?asignatura_id=CIE solo (C2,CIE)")
    def _():
        r_mat = get_pend(PROF_A4, asignatura_id=A4['MAT'])
        r_cie = get_pend(PROF_A4, asignatura_id=A4['CIE'])
        assert r_mat.status_code == 200 and r_cie.status_code == 200
        assert _pares_vistos(r_mat) <= {(A4['est_c1'], A4['MAT'])}, _pares_vistos(r_mat)
        assert _pares_vistos(r_cie) <= {(A4['est_c2'], A4['CIE'])}, _pares_vistos(r_cie)

    @check("§A4-4 desactivar (C2,CIE) → deja de verse; (C1,MAT) sigue visible; reactivar")
    def _():
        d = SessionLocal()
        try:
            row = d.query(AsignacionProfesor).filter_by(
                profesor_id=A4['p4'], curso_id=A4['C2'], asignatura_id=A4['CIE']).first()
            row.activo = False
            d.commit()
        finally:
            d.close()
        try:
            vistos = _pares_vistos(get_pend(PROF_A4))
            assert (A4['est_c2'], A4['CIE']) not in vistos, f"asignación inactiva sigue autorizando: {vistos}"
            assert (A4['est_c1'], A4['MAT']) in vistos, f"la pareja activa desapareció: {vistos}"
        finally:
            d = SessionLocal()
            try:
                row = d.query(AsignacionProfesor).filter_by(
                    profesor_id=A4['p4'], curso_id=A4['C2'], asignatura_id=A4['CIE']).first()
                row.activo = True
                d.commit()
            finally:
                d.close()

    @check("§A4-5 secretaría 403 y profesor de otro colegio no ve nada de las parejas A4")
    def _():
        assert get_pend(SEC_A).status_code == 403
        r = get_pend(PROF_B)
        assert r.status_code == 200
        vistos = _pares_vistos(r)
        ids_a4 = {A4['est_c1'], A4['est_c2']}
        assert not any(e in ids_a4 for (e, _a) in vistos), f"PROF_B ve estudiantes de A4: {vistos}"

    # ── §18: tenant isolation ──────────────────────────────────────────
    @check("§18 dirección B no ve pendientes con estudiantes de A")
    def _():
        _set_cf(A['est'], A['asig'], A['ano_id'], 55.0, A['colegio_id'])
        r = get_pend(DIR_B)
        assert r.status_code == 200
        ids_a = {A['est'], A['est2']}
        assert not any(p['estudiante_id'] in ids_a for p in r.json().get('pendientes', []))

    @check("§18 profesor A no puede escribir evaluación extra de estudiante de B (403/404)")
    def _():
        _set_cf(Bc['est'], Bc['asig'], Bc['ano_id'], 55.0, Bc['colegio_id'])
        r = post_extra(PROF_A, Bc['est'], Bc['asig'], 'completiva', 40)
        assert r.status_code in (403, 404), f"{r.status_code}: {r.text}"

    # ── §19: GET con side-effect de escritura (backfill) — DIFERIDO ────
    @caracteriza("§19 [DIFERIDO] GET /pendientes ejecuta backfill+commit — refactor separado (datos existentes pueden depender)")
    def _():
        # estudiante est2 de A con 4 competencias completas y CF<70, SIN fila EvaluacionExtra
        d = SessionLocal()
        try:
            d.query(EvaluacionExtraSecundaria).filter_by(
                estudiante_id=A['est2'], asignatura_id=A['asig2'], ano_escolar_id=A['ano_id']).delete()
            for comp_n in range(1, 5):
                d.add(CalificacionSecundaria(colegio_id=A['colegio_id'], estudiante_id=A['est2'],
                    asignatura_id=A['asig2'], ano_escolar_id=A['ano_id'], competencia_numero=comp_n,
                    p1=50, p2=50, p3=50, p4=50, promedio_competencia=50.0))
            d.commit()
            antes = d.query(EvaluacionExtraSecundaria).count()
        finally:
            d.close()
        get_pend(DIR_A)  # este GET dispara el backfill
        d = SessionLocal()
        try:
            despues = d.query(EvaluacionExtraSecundaria).count()
            creada = d.query(EvaluacionExtraSecundaria).filter_by(
                estudiante_id=A['est2'], asignatura_id=A['asig2'], ano_escolar_id=A['ano_id']).first()
        finally:
            d.close()
        assert despues == antes and creada is None, \
            f"un GET creó {despues - antes} fila(s) EvaluacionExtraSecundaria (backfill dentro de un verbo GET)"

    @check("§19-idempotencia: segundo GET no duplica filas ni viola el unique constraint")
    def _():
        c1 = get_pend(DIR_A)
        d = SessionLocal()
        try:
            n1 = d.query(EvaluacionExtraSecundaria).count()
        finally:
            d.close()
        c2 = get_pend(DIR_A)
        d = SessionLocal()
        try:
            n2 = d.query(EvaluacionExtraSecundaria).count()
            # sin duplicados de la clave única
            from sqlalchemy import func
            dups = d.query(EvaluacionExtraSecundaria.estudiante_id, EvaluacionExtraSecundaria.asignatura_id,
                           EvaluacionExtraSecundaria.ano_escolar_id, func.count('*')).group_by(
                EvaluacionExtraSecundaria.estudiante_id, EvaluacionExtraSecundaria.asignatura_id,
                EvaluacionExtraSecundaria.ano_escolar_id).having(func.count('*') > 1).all()
        finally:
            d.close()
        assert c1.status_code == 200 and c2.status_code == 200
        assert n1 == n2, f"segundo GET cambió el conteo {n1}→{n2}"
        assert not dups, f"filas duplicadas por clave única: {dups}"


# ══════════════════════════════════════════════════════════════════════════
# RESUMEN + TABLAS DE DIAGNÓSTICO
# ══════════════════════════════════════════════════════════════════════════
print(f"\n{B}{'=' * 74}{X}")
print(f"{B}  TABLA §8/§10 — CF exacta vs CF oficial vs comportamiento actual{X}")
print(f"{B}{'=' * 74}{X}")
print(f"  {'cf_original':>11} | {'CF acad.':>8} | {'condicion_final':>22} | {'fase_pend()':>12} | ok?")
for f in FILAS_CF:
    ok = "OK" if (f['cond_ok'] and f['fase_ok']) else ("cond✗" if not f['cond_ok'] else "fase✗")
    color = G if ok == "OK" else Y
    print(f"  {f['cf_original']:>11.2f} | {f['cf_academica']:>8} | {str(f['condicion_final']):>22} | "
          f"{str(f['fase_pendiente']):>12} | {color}{ok}{X}")

print(f"\n{B}{'=' * 74}{X}")
print(f"{B}  TABLA §11 — Python round() (half-to-even) vs helper A1 vs HALF_UP{X}")
print(f"{B}{'=' * 74}{X}")
print(f"  {'valor':>7} | {'round()':>8} | {'helper A1':>10} | {'HALF_UP':>8} | round()==HALF_UP | helper==HALF_UP")
for (v, py, prod, aca, py_ok, prod_ok) in TABLA_BANKERS:
    c1 = (G if py_ok else Y); c2 = (G if prod_ok else R)
    print(f"  {v:>7.1f} | {py:>8} | {prod:>10} | {aca:>8} | "
          f"{c1}{'sí' if py_ok else 'NO':>15}{X} | {c2}{'sí' if prod_ok else 'NO':>14}{X}")

print(f"\n{B}{'=' * 74}{X}")
print(f"{B}  RESUMEN v2.20.0-A4{X}")
print(f"{B}{'=' * 74}{X}")
print(f"  [INV] invariantes         : {G}{len(inv_ok)} OK{X} / {R}{len(inv_fail)} FALLAN{X}")
print(f"  [CAR] caracteriz./diferido : {G}{len(car_ok)} coinciden{X} / {Y}{len(car_bug)} pendiente{X}")
print(f"  errores inesperados: {len(errores)}")

if inv_fail:
    print(f"\n{R}{B}INVARIANTES QUE FALLAN (requieren atención):{X}")
    for n, e in inv_fail:
        print(f"{R}  ✗ {n}{X}\n      {e}")

if car_bug:
    print(f"\n{Y}{B}CARACTERIZACIONES / BUGS DIFERIDOS A PROPÓSITO (política académica o refactor aparte):{X}")
    for n, e in car_bug:
        print(f"{Y}  ✗ {n}{X}\n      {e}")

if errores:
    print(f"\n{R}{B}EXCEPCIONES INESPERADAS:{X}")
    for n, e in errores:
        print(f"{R}  ! {n}{X}\n      {e}")

# ── SEGURIDAD DE DATOS: confirmar que la suite NO tocó sge.db del repo ──
if _sge_mtime_inicial is not None:
    _now = os.path.getmtime(_REPO_SGE) if os.path.exists(_REPO_SGE) else None
    if _now != _sge_mtime_inicial or not os.path.exists(_REPO_SGE):
        print(f"{R}{B}✗ SEGURIDAD: sge.db del repo cambió/desapareció durante la suite{X}")
        sys.exit(2)
print(f"{G}✓ SEGURIDAD: sge.db del repo intacto (no leído ni escrito por la suite){X}")

# exit 1 SOLO si falla un invariante o hay una excepción inesperada.
# Las caracterizaciones [CAR] son bugs DIFERIDOS a propósito (documentados).
if inv_fail or errores:
    sys.exit(1)
print(f"\n{G}{B}✔ v2.20.0-A4: {len(inv_ok)} invariantes verdes. "
      f"{len(car_bug)} caracterización(es) diferida(s) a propósito.{X}\n")
