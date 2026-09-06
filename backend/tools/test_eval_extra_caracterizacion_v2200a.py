# -*- coding: utf-8 -*-
"""
EducaOne v2.20.0-A — RED DE SEGURIDAD / TESTS DE CARACTERIZACIÓN
Completiva + Extraordinaria + Especial de Secundaria.

NO modifica lógica productiva. Caracteriza el comportamiento ACTUAL de:
  - EvaluacionExtraSecundaria (modelo + cascada MINERD)
  - _calcular_cf_secundaria / redondeo académico
  - POST /api/calificaciones-secundaria/evaluacion-extra
  - GET  /api/calificaciones-secundaria/pendientes-evaluacion-extra
  - RBAC + tenant isolation

Categorías:
  [INV]  invariante que DEBE cumplirse (si falla → exit 1)
  [CAR]  caracterización contra la regla académica esperada; si falla es un
         BUG PREEXISTENTE (se reporta, NO se corrige, NO fuerza exit 1)

Uso:
    cd backend
    python tools/test_eval_extra_caracterizacion_v2200a.py
"""
import os
import sys
from decimal import Decimal, ROUND_HALF_UP

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for ext in ['', '-shm', '-wal']:
    p = os.path.join(_BASE, 'sge.db' + ext)
    if os.path.exists(p):
        os.remove(p)
if os.path.exists(os.path.join(_BASE, 'INITIAL_CREDENTIALS.txt')):
    os.remove(os.path.join(_BASE, 'INITIAL_CREDENTIALS.txt'))

from database import engine, SessionLocal
from models import (
    Base, Usuario, Grado, Curso, Asignatura, Estudiante, AnoEscolar,
    AsignacionProfesor, CalificacionSecundaria, EvaluacionExtraSecundaria,
)
Base.metadata.create_all(bind=engine)
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)

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

# ---- §11: Python round() vs redondeo académico (bankers rounding) ----
BANKERS = [66.5, 67.5, 68.5, 69.5, 70.5, 71.5]
TABLA_BANKERS = []
for v in BANKERS:
    py = round(v)                    # lo que usa producción (round builtin)
    py0 = round(v, 0)               # round(x, 0) → float, como en models.py
    aca = redondeo_academico(v)
    TABLA_BANKERS.append((v, py, py0, aca, py == aca))

@caracteriza("§11 round() de producción == ROUND_HALF_UP académico en .5 (66.5/67.5/68.5/69.5/70.5/71.5)")
def _():
    difs = [f"{v}: round()={py} vs académico={aca}" for (v, py, _p0, aca, ok) in TABLA_BANKERS if not ok]
    assert not difs, "bankers rounding divergente → " + " | ".join(difs)

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

@caracteriza("§10-b fase_pendiente() coincide con CF oficial (CF>=70 ⇒ fase None) en toda la tabla 69.00–70.01")
def _():
    malas = [f"cf_original={f['cf_original']} (CF oficial {f['cf_academica']}) → fase_pendiente()={f['fase_pendiente']!r} "
             f"(esperado {f['esperado_fase']!r})" for f in FILAS_CF if not f['fase_ok']]
    assert not malas, "inconsistencia CF-oficial vs fase_pendiente → " + " || ".join(malas)

# ---- §12: invariante duro CF oficial >= 70 ⇒ aprobado_normal + fase None ----
@caracteriza("§12 invariante: CF oficial >= 70 ⇒ condicion_final=='aprobado_normal' Y fase_pendiente()==None")
def _():
    for v in [69.5, 69.6, 69.8, 69.99, 70.0]:
        e = _recalc(_ev(cf=v))
        assert e.condicion_final == 'aprobado_normal', f"cf_original={v}: condicion_final={e.condicion_final!r}"
        assert e.fase_pendiente() is None, f"cf_original={v}: fase_pendiente()={e.fase_pendiente()!r} (CF oficial {cf_oficial(v)} ≥ 70)"

# ---- §5: Completiva ----
@check("§5-a Completiva Final = round(0.5·CF + 0.5·CEC) (fórmula actual, entera)")
def _():
    e = _ev(cf=63.5, cec=76)   # 31.75 + 38 = 69.75 → 70
    assert e.calcular_completiva_final() == round(0.5*63.5 + 0.5*76, 0)
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
@check("§6-a Extraordinaria Final = round(0.3·CF + 0.7·CEEX) (entera)")
def _():
    e = _ev(cf=50.0, ceex=80)   # 15 + 56 = 71
    assert e.calcular_extraordinaria_final() == round(0.3*50.0 + 0.7*80, 0) == 71

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
@check("§7-a Especial Final = round(CF) + CE (fórmula actual)")
def _():
    e = _ev(cf=64.0, ce=10)
    assert e.calcular_especial_final() == round(64.0, 0) + 10 == 74

@check("§7-b Especial >= 70 ⇒ aprobado_especial ; < 70 ⇒ reprobado")
def _():
    ap = _recalc(_ev(cf=64.0, cec=40, ceex=50, ce=6))   # 64+6=70
    assert ap.condicion_final == 'aprobado_especial'
    rp = _recalc(_ev(cf=40.0, cec=30, ceex=40, ce=10))  # 40+10=50
    assert rp.condicion_final == 'reprobado'
    assert rp.fase_pendiente() is None

@caracteriza("§7-c Especial: round(CF) usa redondeo académico (CF exacta 68.5 ⇒ base 69, no 68)")
def _():
    e = _ev(cf=68.5, ce=1)   # académico: 69 + 1 = 70 (aprobado). round() banker: 68 + 1 = 69
    esperado = redondeo_academico(68.5) + 1
    assert e.calcular_especial_final() == esperado, \
        f"especial_final={e.calcular_especial_final()} (round() banker) vs académico {esperado}"

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
    @caracteriza("§15 cf_original=69.49 → CF oficial 69 → el endpoint PERMITE Completiva (200)")
    def _():
        _set_cf(A['est2'], A['asig'], A['ano_id'], 69.49, A['colegio_id'])
        r = post_extra(PROF_A, A['est2'], A['asig'], 'completiva', 50)
        assert r.status_code == 200, f"{r.status_code}: {r.text}"

    @caracteriza("§15 cf_original=69.50 → CF oficial 70 → el endpoint RECHAZA Completiva (400)")
    def _():
        _set_cf(A['est2'], A['asig'], A['ano_id'], 69.50, A['colegio_id'])
        r = post_extra(PROF_A, A['est2'], A['asig'], 'completiva', 50)
        assert r.status_code == 400, f"esperado 400 (aprobó normal), obtuvo {r.status_code}: {r.text}"

    @caracteriza("§15 cf_original=69.80 → CF oficial 70 → el endpoint RECHAZA Completiva (400)")
    def _():
        _set_cf(A['est2'], A['asig'], A['ano_id'], 69.80, A['colegio_id'])
        r = post_extra(PROF_A, A['est2'], A['asig'], 'completiva', 50)
        assert r.status_code == 400, f"esperado 400, obtuvo {r.status_code}: {r.text}"

    @caracteriza("§15 cf_original=69.99 → CF oficial 70 → el endpoint RECHAZA Completiva (400)")
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

    @caracteriza("§16-B corregir Completiva cuando YA existe Extraordinaria: limpia Extraordinaria y Especial")
    def _():
        _set_cf(A['est'], A['asig'], A['ano_id'], 40.0, A['colegio_id'])
        assert post_extra(PROF_A, A['est'], A['asig'], 'completiva', 30).status_code == 200      # comp 35<70
        assert post_extra(PROF_A, A['est'], A['asig'], 'extraordinaria', 50).status_code == 200  # extra 47<70
        r = post_extra(PROF_A, A['est'], A['asig'], 'completiva', 95)   # corrección de completiva
        assert r.status_code == 200, f"esperado 200 (corrección con limpieza), obtuvo {r.status_code}: {r.text}"
        row = _ev_row(A['est'], A['asig'], A['ano_id'])
        assert row['cec'] == 95 and row['ceex'] is None and row['ce'] is None, \
            f"esperado ceex/ce limpiados; row={row}"

    @caracteriza("§16-C corregir Extraordinaria cuando YA existe Especial: limpia Especial")
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

    @caracteriza("§17-d profesor con asignación INACTIVA NO debe ver pendientes de ese curso/asignatura")
    def _():
        _set_cf(A['est'], A['asig'], A['ano_id'], 55.0, A['colegio_id'])
        r = get_pend(PROF_INACT_A)
        assert r.status_code == 200, r.text
        pend = r.json().get('pendientes', [])
        assert not any(p['asignatura_id'] == A['asig'] and p['estudiante_id'] == A['est'] for p in pend), \
            f"profesor con asignación INACTIVA ve pendientes: {pend}"

    @caracteriza("§17-e secretaría NO debe poder acceder al módulo de evaluaciones extra (403)")
    def _():
        r = get_pend(SEC_A)
        assert r.status_code == 403, f"esperado 403, obtuvo {r.status_code} (body: {r.text[:120]})"

    @check("§17-f profesor de otro colegio jamás ve pendientes del colegio A")
    def _():
        _set_cf(A['est'], A['asig'], A['ano_id'], 55.0, A['colegio_id'])
        r = get_pend(PROF_B)
        assert r.status_code == 200
        for p in r.json().get('pendientes', []):
            assert p['estudiante_id'] != A['est']

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

    # ── §19: GET con side-effect de escritura (backfill) ───────────────
    @caracteriza("§19 GET /pendientes NO debería escribir; hoy hace backfill (documentado, no se corrige)")
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
print(f"{B}  TABLA §11 — Python round() vs ROUND_HALF_UP académico{X}")
print(f"{B}{'=' * 74}{X}")
print(f"  {'valor':>7} | {'round()':>8} | {'round(x,0)':>10} | {'académico':>9} | coincide?")
for (v, py, py0, aca, ok) in TABLA_BANKERS:
    color = G if ok else Y
    print(f"  {v:>7.1f} | {py:>8} | {py0:>10} | {aca:>9} | {color}{'sí' if ok else 'NO — divergen'}{X}")

print(f"\n{B}{'=' * 74}{X}")
print(f"{B}  RESUMEN{X}")
print(f"{B}{'=' * 74}{X}")
print(f"  [INV] invariantes : {G}{len(inv_ok)} OK{X} / {R}{len(inv_fail)} FALLAN{X}")
print(f"  [CAR] caracteriz. : {G}{len(car_ok)} coinciden{X} / {Y}{len(car_bug)} BUG CONFIRMADO{X}")
print(f"  errores inesperados: {len(errores)}")

if inv_fail:
    print(f"\n{R}{B}INVARIANTES QUE FALLAN (requieren atención):{X}")
    for n, e in inv_fail:
        print(f"{R}  ✗ {n}{X}\n      {e}")

if car_bug:
    print(f"\n{Y}{B}BUGS PREEXISTENTES CONFIRMADOS (NO se corrigen en esta fase):{X}")
    for n, e in car_bug:
        print(f"{Y}  ✗ {n}{X}\n      {e}")

if errores:
    print(f"\n{R}{B}EXCEPCIONES INESPERADAS:{X}")
    for n, e in errores:
        print(f"{R}  ! {n}{X}\n      {e}")

# exit 1 SOLO si falla un invariante o hay una excepción inesperada.
# Las caracterizaciones que fallan son bugs preexistentes ya documentados.
if inv_fail or errores:
    sys.exit(1)
print(f"\n{G}{B}✔ Invariantes verdes. {len(car_bug)} caracterización(es) marcan bug preexistente (ver arriba).{X}\n")
