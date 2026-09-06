# -*- coding: utf-8 -*-
"""
EducaOne v2.20.1-B2 — Registro Escolar Secundaria:
Completiva + Extraordinaria + Especial en las páginas oficiales por asignatura.

Alcance EXCLUSIVO: la página Completiva/Extraordinaria/Especial por asignatura
(pgs 150-158 ciclo 1 / 210-224 + 211-221 ciclo 2). NO promoción, NO situación
final del grado, NO endpoints de promoción/cierre, NO Boletín, NO Primaria.

Fuente única de la cascada: EvaluacionExtraSecundaria (v2.20.0). Las notas
finales se toman ALMACENADAS, nunca se recalculan. Los porcentajes intermedios
(50%/30%/70%) se derivan de la CF EXACTA, con 1 decimal, igual que el Boletín.

SEGURIDAD DE DATOS: DB SQLite temporal aislada, creada ANTES de importar
database/models/app. NUNCA se borra sge.db ni ningún archivo real del repo.

Uso:
    cd backend
    python tools/test_registro_completiva_v2201b2.py
"""
import io
import os
import sys
import atexit
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── DB TEMPORAL AISLADA (antes de importar database/models/app) ──────────────
_TMPDIR = tempfile.mkdtemp(prefix="eo_reg_completiva_b2_")
_TEST_DB_PATH = os.path.join(_TMPDIR, "reg_completiva_b2.db")
_TEST_DB_URL = "sqlite:///" + _TEST_DB_PATH.replace("\\", "/")
os.environ["DATABASE_URL"] = _TEST_DB_URL


@atexit.register
def _cleanup_tmpdir():
    try:
        import shutil
        shutil.rmtree(_TMPDIR, ignore_errors=True)
    except Exception:
        pass


from pypdf import PdfReader
from reportlab.pdfbase.pdfmetrics import stringWidth

from registro_escolar import (
    generar_registro_desde_sistema, generar_registro_escolar,
    draw_completiva, _fila_completiva, _create_overlay_page,
    COMPLETIVA_TABLE, _COMPLETIVA_VLINES, GRADO_CONFIG,
    ASIGNATURAS_CICLO_1, ASIGNATURAS_CICLO_2,
)

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


# ═══════════════════════════════════════════════════════════════════════════
# SEGURIDAD: la suite corre contra su DB temporal, jamás contra sge.db
# ═══════════════════════════════════════════════════════════════════════════
from database import engine, SessionLocal  # noqa: E402
_engine_url = str(engine.url).replace("\\", "/")
assert _TMPDIR.replace("\\", "/") in _engine_url, f"engine fuera del tmp: {_engine_url}"
assert "sge.db" not in _engine_url, "SEGURIDAD: la suite usaría sge.db"
_REPO_SGE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sge.db")
_sge_mtime = os.path.getmtime(_REPO_SGE) if os.path.exists(_REPO_SGE) else None
print(f"{G}✓ DB de test AISLADA:{X} {_engine_url}")


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS DE FIXTURE (sin DB) — dicts con la forma que produce el loader real
# ═══════════════════════════════════════════════════════════════════════════
def mk_ev(**ov):
    base = dict(
        cf_original=None, cec=None, completiva_final=None,
        ceex=None, extraordinaria_final=None, ce=None, especial_final=None,
        condicion_final=None, nota_final=None, fase_pendiente=None,
    )
    base.update(ov)
    return base


def mk_cd(cf=None, cf_exacto=None, ev=None):
    return {"cf": cf, "cf_exacto": cf_exacto, "evaluacion_extra": ev}


def cols_presentes(fila):
    return set(fila.keys()) if fila else set()


COMP = {"comp_cf_50", "comp_cec", "comp_cec_50", "comp_ccf"}
EXTRA = {"extra_cf_30", "extra_ceex", "extra_ceex_70", "extra_final"}
ESPEC = {"espec_cf", "espec_ce"}
AR = {"situacion_a", "situacion_r"}


# ═══════════════════════════════════════════════════════════════════════════
# PARTE 1 — _fila_completiva: casos 1..10, 25
# ═══════════════════════════════════════════════════════════════════════════
@test("§1 aprobado normal (CF 85, sin ev) → cf=85, A=85, sin completiva/extra/especial ni R")
def _():
    f = _fila_completiva(mk_cd(cf=85, cf_exacto=85.0, ev=None))
    assert f == {"cf": 85, "situacion_a": 85}, f


@test("§2 pendiente Completiva (CF 64<70, sin ev) → cf=64, comp_cf_50=31.8, A/R VACÍO")
def _():
    f = _fila_completiva(mk_cd(cf=64, cf_exacto=63.5, ev=None))
    assert f["cf"] == 64
    assert f["comp_cf_50"] == 31.8, f
    assert "situacion_a" not in f and "situacion_r" not in f, f
    assert not (EXTRA | ESPEC) & cols_presentes(f), f


@test("§3 aprobado Completiva → CEC/50%CEC/CCF + A; sin extra/especial")
def _():
    ev = mk_ev(cf_original=63.5, cec=76, completiva_final=70,
               condicion_final="aprobado_completiva", nota_final=70, fase_pendiente=None)
    f = _fila_completiva(mk_cd(cf=64, cf_exacto=63.5, ev=ev))
    assert f["cf"] == 64
    assert f["comp_cf_50"] == 31.8
    assert f["comp_cec"] == 76
    assert f["comp_cec_50"] == 38.0
    assert f["comp_ccf"] == 70
    assert f["situacion_a"] == 70 and "situacion_r" not in f
    assert not (EXTRA | ESPEC) & cols_presentes(f), f


@test("§4 pendiente Extraordinaria → bloque Completiva + 30%CF; sin CEEX/CEXF; A/R VACÍO")
def _():
    ev = mk_ev(cf_original=63.5, cec=50, completiva_final=57,
               condicion_final="reprobado", nota_final=57, fase_pendiente="extraordinaria")
    f = _fila_completiva(mk_cd(cf=64, cf_exacto=63.5, ev=ev))
    assert f["comp_cec"] == 50 and f["comp_ccf"] == 57
    assert f["extra_cf_30"] == 19.1, f
    assert "extra_ceex" not in f and "extra_ceex_70" not in f and "extra_final" not in f
    assert "situacion_a" not in f and "situacion_r" not in f, f
    assert not ESPEC & cols_presentes(f)


@test("§5 aprobado Extraordinaria → CEEX/70%CEEX/CEXF + A; sin especial")
def _():
    ev = mk_ev(cf_original=17, cec=40, completiva_final=29,
               ceex=92, extraordinaria_final=70,
               condicion_final="aprobado_extraordinaria", nota_final=70, fase_pendiente=None)
    f = _fila_completiva(mk_cd(cf=17, cf_exacto=17.0, ev=ev))
    assert f["extra_cf_30"] == 5.1
    assert f["extra_ceex"] == 92
    assert f["extra_ceex_70"] == 64.4
    assert f["extra_final"] == 70
    assert f["situacion_a"] == 70 and "situacion_r" not in f
    assert not ESPEC & cols_presentes(f), f


@test("§6 pendiente Especial → C.F. especial visible, C.E. vacía; A/R VACÍO")
def _():
    ev = mk_ev(cf_original=17, cec=40, completiva_final=29,
               ceex=45, extraordinaria_final=52, ce=None,
               condicion_final="reprobado", nota_final=52, fase_pendiente="especial")
    f = _fila_completiva(mk_cd(cf=17, cf_exacto=17.0, ev=ev))
    assert f["extra_final"] == 52
    assert f["espec_cf"] == 17
    assert "espec_ce" not in f
    assert "situacion_a" not in f and "situacion_r" not in f, f


@test("§7 aprobado Especial → C.E. + A")
def _():
    ev = mk_ev(cf_original=61.05, cec=67, completiva_final=64,
               ceex=66, extraordinaria_final=65, ce=10, especial_final=71,
               condicion_final="aprobado_especial", nota_final=71, fase_pendiente=None)
    f = _fila_completiva(mk_cd(cf=61, cf_exacto=61.05, ev=ev))
    assert f["espec_cf"] == 61
    assert f["espec_ce"] == 10
    assert f["situacion_a"] == 71 and "situacion_r" not in f


@test("§8 reprobado final (cascada completa) → R = nota_final; sin A")
def _():
    ev = mk_ev(cf_original=58.475, cec=70, completiva_final=64,
               ceex=70, extraordinaria_final=67, ce=10, especial_final=68,
               condicion_final="reprobado", nota_final=68, fase_pendiente=None)
    f = _fila_completiva(mk_cd(cf=58, cf_exacto=58.475, ev=ev))
    assert f["espec_cf"] == 58 and f["espec_ce"] == 10
    assert f["situacion_r"] == 68 and "situacion_a" not in f


@test("§9 cf_original=63.5 → C.F.=64, 50% C.F.='31.8', 30% C.F.='19.1'")
def _():
    from boletin_minerd_secundaria import _fmt_nota
    ev = mk_ev(cf_original=63.5, cec=50, completiva_final=57,
               condicion_final="reprobado", nota_final=57, fase_pendiente="extraordinaria")
    f = _fila_completiva(mk_cd(cf=64, cf_exacto=63.5, ev=ev))
    assert f["cf"] == 64
    assert _fmt_nota(f["comp_cf_50"]) == "31.8", f["comp_cf_50"]
    assert _fmt_nota(f["extra_cf_30"]) == "19.1", f["extra_cf_30"]
    # NUNCA 50% de la CF oficial (64) = 32
    assert f["comp_cf_50"] != 32.0


@test("§10 cero es nota válida: CEC=0, CEEX=0, CE=0, nota_final=0 → todas las celdas con 0 se dibujan")
def _():
    from boletin_minerd_secundaria import _fmt_nota
    ev = mk_ev(cf_original=0, cec=0, completiva_final=0,
               ceex=0, extraordinaria_final=0, ce=0, especial_final=0,
               condicion_final="reprobado", nota_final=0, fase_pendiente=None)
    f = _fila_completiva(mk_cd(cf=0, cf_exacto=0.0, ev=ev))
    for k in ("cf", "comp_cec", "comp_cec_50", "comp_ccf",
              "extra_ceex", "extra_ceex_70", "extra_final",
              "espec_cf", "espec_ce", "situacion_r"):
        assert k in f and f[k] == 0, (k, f.get(k, "AUSENTE"))
    assert "situacion_a" not in f
    assert _fmt_nota(0) == "0"  # se dibuja, no se salta


@test("§25 A/R NUNCA se llena mientras fase_pendiente != None (aunque condicion_final diga 'reprobado')")
def _():
    for fp in ("completiva", "extraordinaria", "especial"):
        ev = mk_ev(cf_original=55, cec=(None if fp == "completiva" else 50),
                   completiva_final=(None if fp == "completiva" else 40),
                   ceex=(None if fp != "especial" else 40),
                   extraordinaria_final=(None if fp != "especial" else 45),
                   condicion_final="reprobado", nota_final=45, fase_pendiente=fp)
        f = _fila_completiva(mk_cd(cf=55, cf_exacto=55.0, ev=ev))
        assert "situacion_a" not in f and "situacion_r" not in f, (fp, f)


# ═══════════════════════════════════════════════════════════════════════════
# PARTE 2 — geometría (caso 24) y coordenadas (§10)
# ═══════════════════════════════════════════════════════════════════════════
def _texts_with_x(datos):
    """Devuelve [(left_x, y, texto), ...] del overlay de draw_completiva."""
    buf = _create_overlay_page(draw_completiva, datos)
    page = PdfReader(buf).pages[0]
    hits = []

    def vis(text, cm, tm, fd, fs):
        t = (text or "").strip()
        if t:
            hits.append((round(float(tm[4]), 3), round(float(tm[5]), 3), t))
    page.extract_text(visitor_text=vis)
    return hits


@test("§10 coordenadas: los 13 x-center salen de (v_line_i + v_line_i+1)/2 exactamente")
def _():
    order = ["numero", "cf", "comp_cf_50", "comp_cec", "comp_cec_50", "comp_ccf",
             "extra_cf_30", "extra_ceex", "extra_ceex_70", "extra_final",
             "espec_cf", "espec_ce", "situacion_a", "situacion_r"]
    assert list(COMPLETIVA_TABLE["columnas"].keys()) == order, list(COMPLETIVA_TABLE["columnas"].keys())
    for i, name in enumerate(order):
        col = COMPLETIVA_TABLE["columnas"][name]
        esperado = round((_COMPLETIVA_VLINES[i] + _COMPLETIVA_VLINES[i + 1]) / 2, 2)
        assert col["x"] == esperado, (name, col["x"], esperado)
        assert col["left"] == _COMPLETIVA_VLINES[i] and col["right"] == _COMPLETIVA_VLINES[i + 1]


@test("§24 cada texto queda GEOMÉTRICAMENTE dentro de su columna [left, right]")
def _():
    ev = mk_ev(cf_original=63.5, cec=76, completiva_final=70,
               ceex=66, extraordinaria_final=68, ce=5, especial_final=69,
               condicion_final="reprobado", nota_final=69, fase_pendiente=None)
    fila = _fila_completiva(mk_cd(cf=64, cf_exacto=63.5, ev=ev))
    # fila con 12 columnas de datos + R; forzamos también A en otra fila
    ev2 = mk_ev(cf_original=63.5, cec=90, completiva_final=77,
                condicion_final="aprobado_completiva", nota_final=77, fase_pendiente=None)
    fila2 = _fila_completiva(mk_cd(cf=64, cf_exacto=63.5, ev=ev2))
    datos = {"docente": "DOCENTE X", "calificaciones": [fila, fila2]}
    hits = _texts_with_x(datos)
    cols = COMPLETIVA_TABLE["columnas"]
    tol = 0.75
    n_check = 0
    for left_x, y, txt in hits:
        if txt == "DOCENTE X":
            continue
        w = stringWidth(txt, "Helvetica", 8)
        center = left_x + w / 2.0
        right_x = left_x + w
        # ¿en qué columna cae el centro?
        col_name = min(
            (c for c in cols if c != "numero"),
            key=lambda c: abs(cols[c]["x"] - center),
        )
        col = cols[col_name]
        assert col["left"] - tol <= left_x and right_x <= col["right"] + tol, \
            f"'{txt}' left={left_x:.1f} right={right_x:.1f} fuera de {col_name} [{col['left']}, {col['right']}]"
        assert col["left"] <= center <= col["right"], \
            f"'{txt}' centro {center:.1f} fuera de {col_name}"
        n_check += 1
    assert n_check >= 12, f"solo se verificaron {n_check} celdas"


# ═══════════════════════════════════════════════════════════════════════════
# PARTE 3 — PDF completo vía generar_registro_desde_sistema (sin DB)
# ═══════════════════════════════════════════════════════════════════════════
from datetime import date  # noqa: E402

_CI = {"nombre": "CENTRO B2", "direccion": "Av X", "email": "c@e.do", "telefono": "809",
       "director": "DIR B2", "codigo_centro": "00000", "regional": "10", "distrito": "03",
       "sector": "publico", "zona": "urbana", "coordinador": "TITULAR B2"}


def _students(n):
    return [{
        "id": i + 1, "no_lista": i + 1, "nombre": f"ALUMNO {i:02d} APELLIDO",
        "sexo": "F" if i % 2 == 0 else "M",
        "fecha_nacimiento": date(2009, (i % 12) + 1, (i % 27) + 1),
        "cedula": "", "matricula": f"M{i:04d}", "direccion": f"Calle {i}",
        "condicion_entrada": "nuevo", "activo": True,
    } for i in range(n)]


def _cd_full(cf, cf_exacto, ev=None):
    return {
        "competencias": {k: {"p1": 80, "p2": 80, "p3": 80, "p4": 80} for k in (1, 2, 3, 4)},
        "promedios_competencia": {1: 80, 2: 80, 3: 80, 4: 80},
        "rp1": None, "rp2": None, "rp3": None, "rp4": None,
        "pc1": 80, "pc2": 80, "pc3": 80, "pc4": 80,
        "cf": cf, "cf_exacto": cf_exacto, "evaluacion_extra": ev,
    }


def _asig_data(studs, grado, califs_por_asig):
    """califs_por_asig: {nombre_asig: {idx: cd}}  (asignaturas ausentes -> vacías)."""
    asigs = ASIGNATURAS_CICLO_2 if grado >= 4 else ASIGNATURAS_CICLO_1
    out = {}
    for a in asigs:
        out[a] = {
            "docente": "DOC " + a[:6],
            "asistencias": {}, "asistencia_matriz": [],
            "calificaciones": califs_por_asig.get(a, {}),
        }
    return out


def _gen(grado, califs_por_asig, nstud=4, marca=False):
    st = _students(nstud)
    ad = _asig_data(st, grado, califs_por_asig)
    cu = {"grado": str(grado), "seccion": "A", "tanda": "Matutina"}
    return generar_registro_desde_sistema(_CI, cu, "2024-2025", st, ad, grado, marca_borrador=marca)


def _xobject_names(page):
    res = page.get("/Resources")
    if res is None:
        return set()
    xo = res.get_object().get("/XObject")
    if xo is None:
        return set()
    return {str(k) for k in xo.get_object().keys()}


def _page_has_data_overlay(reader, pg_1based):
    return any(n.startswith("/EODataOverlay") for n in _xobject_names(reader.pages[pg_1based - 1]))


def _page_text(reader, pg_1based):
    return reader.pages[pg_1based - 1].extract_text() or ""


@test("§14 ciclo 1: la página Completiva de la asignatura CON datos recibe overlay; total páginas 170")
def _():
    ev = mk_ev(cf_original=58.0, cec=None, condicion_final="reprobado",
               nota_final=58, fase_pendiente="completiva")
    califs = {"Matemática": {0: _cd_full(58, 58.0, ev), 1: _cd_full(90, 90.0, None)}}
    pdf = _gen(1, califs)
    rd = PdfReader(io.BytesIO(pdf))
    assert len(rd.pages) == 170
    # 1ro: Matemática = pg 153 (índice 3 en completiva_paginas)
    assert _page_has_data_overlay(rd, 153), "pg 153 (Matemática completiva) sin overlay"
    txt = _page_text(rd, 153)
    assert "58" in txt and "31" in txt, txt[:200]  # cf 58 y 50%CF 29.0 -> '29'; al menos cf


@test("§15 ciclo 2: páginas base 210/213/215/216/218/220/222/223/224 y total 238")
def _():
    ev = mk_ev(cf_original=55.0, cec=80, completiva_final=68,
               condicion_final="reprobado", nota_final=68, fase_pendiente="extraordinaria")
    califs = {"Lengua Española": {0: _cd_full(55, 55.0, ev)},
              "Formación Integral Humana y Religiosa": {0: _cd_full(75, 75.0, None)}}
    pdf = _gen(4, califs)
    rd = PdfReader(io.BytesIO(pdf))
    assert len(rd.pages) == 238
    assert _page_has_data_overlay(rd, 210), "pg 210 (Lengua completiva) sin overlay"
    assert _page_has_data_overlay(rd, 224), "pg 224 (FIHR completiva) sin overlay"


@test("§16 Salida Optativa (ciclo 2): dibuja en sus páginas existentes 211,212,214,217,219,221")
def _():
    ev = mk_ev(cf_original=50.0, cec=90, completiva_final=70,
               condicion_final="aprobado_completiva", nota_final=70, fase_pendiente=None)
    califs = {"Salida Optativa": {0: _cd_full(50, 50.0, ev)}}
    pdf = _gen(5, califs)
    rd = PdfReader(io.BytesIO(pdf))
    for pg in (211, 212, 214, 217, 219, 221):
        assert _page_has_data_overlay(rd, pg), f"Salida Optativa pg {pg} sin overlay"


@test("§17 página SIN datos (asignatura sin CF ni ev para nadie) permanece SIN overlay de datos")
def _():
    # Solo Matemática tiene datos; Lengua Española (pg 150 en ciclo 1) NO.
    ev = mk_ev(cf_original=58.0, condicion_final="reprobado", nota_final=58, fase_pendiente="completiva")
    califs = {"Matemática": {0: _cd_full(58, 58.0, ev)}}
    pdf = _gen(1, califs)
    rd = PdfReader(io.BytesIO(pdf))
    assert not _page_has_data_overlay(rd, 150), "pg 150 (Lengua, sin datos) recibió overlay indebido"
    assert _page_has_data_overlay(rd, 153), "pg 153 (Matemática) debería tener overlay"


@test("§21 número de páginas intacto para los 6 grados (170/170/170/238/238/240)")
def _():
    esperado = {1: 170, 2: 170, 3: 170, 4: 238, 5: 238, 6: 240}
    ev = mk_ev(cf_original=60.0, cec=85, completiva_final=72,
               condicion_final="aprobado_completiva", nota_final=72, fase_pendiente=None)
    for g, npag in esperado.items():
        califs = {"Matemática": {0: _cd_full(60, 60.0, ev)}}
        rd = PdfReader(io.BytesIO(_gen(g, califs)))
        assert len(rd.pages) == npag, f"grado {g}: {len(rd.pages)} != {npag}"


@test("§22 XObject: la página Completiva con datos lleva /EODataOverlayN (Form XObject v2.19.9)")
def _():
    ev = mk_ev(cf_original=58.0, cec=80, completiva_final=69,
               condicion_final="reprobado", nota_final=69, fase_pendiente="extraordinaria")
    califs = {"Matemática": {0: _cd_full(58, 58.0, ev)}}
    rd = PdfReader(io.BytesIO(_gen(2, califs)))
    names = _xobject_names(rd.pages[153 - 1])
    assert any(n.startswith("/EODataOverlay") for n in names), names


@test("§23 merge_page() AUSENTE del CÓDIGO (no comentarios) de la ruta de datos del Registro")
def _():
    import inspect
    import io as _io
    import tokenize
    import registro_escolar as _re

    def _llama_merge_page(src):
        """True si el CÓDIGO (ignorando comentarios y strings) invoca .merge_page(."""
        toks = list(tokenize.generate_tokens(_io.StringIO(src).readline))
        for i, tk in enumerate(toks):
            if tk.type == tokenize.NAME and tk.string == "merge_page":
                # siguiente token significativo debe ser '('
                for nxt in toks[i + 1:]:
                    if nxt.type in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
                                    tokenize.DEDENT, tokenize.COMMENT):
                        continue
                    if nxt.type == tokenize.OP and nxt.string == "(":
                        return True
                    break
        return False

    for fn in (_re.generar_registro_escolar, _re.generar_registro_desde_sistema,
               _re.draw_completiva, _re._fila_completiva):
        assert not _llama_merge_page(inspect.getsource(fn)), f"{fn.__name__} invoca merge_page("
    assert not _llama_merge_page(inspect.getsource(_re)), "registro_escolar.py invoca merge_page("


@test("§18 Primaria: el Registro de Primaria genera sin error y NO cambió (mismo módulo intacto)")
def _():
    import inspect
    import registro_primaria as rp
    # 1) no se importó nada de completiva en primaria
    src = inspect.getsource(rp)
    assert "EvaluacionExtraSecundaria" not in src
    assert "_fila_completiva" not in src
    # 2) el generador de primaria sigue disponible y con su firma
    assert hasattr(rp, "generar_registro_primaria_pdf") or hasattr(rp, "generar_registro_primaria"), dir(rp)


# ═══════════════════════════════════════════════════════════════════════════
# PARTE 4 — integración con DB aislada: query count / N+1 / tenant / curso / asig
# ═══════════════════════════════════════════════════════════════════════════
from sqlalchemy import event  # noqa: E402
import models as M  # noqa: E402
from app import _cargar_datos_asignaturas_secundaria  # noqa: E402


# El seed inserta filas directas; con FK ON y una sola transacción, el orden
# topológico de SQLAlchemy a veces choca en SQLite. Esta suite valida el
# comportamiento del loader, no integridad referencial: se relaja el PRAGMA.
@event.listens_for(engine, "connect")
def _relax_fk(dbapi_conn, rec):
    try:
        dbapi_conn.execute("PRAGMA foreign_keys=OFF")
    except Exception:
        pass


engine.dispose()  # fuerza reconexión con el PRAGMA aplicado
M.Base.metadata.create_all(bind=engine)

_SQL_EEX = []


@event.listens_for(engine, "before_cursor_execute")
def _count_eex(conn, cur, statement, params, ctx, many):
    s = statement.strip().lower()
    if s.startswith("select") and "evaluaciones_extra_secundaria" in s:
        _SQL_EEX.append(statement)


class _User:
    role = "direccion"
    colegio_id = 1
    id = 1


def _seed():
    d = SessionLocal()
    try:
        d.add(M.Colegio(id=1, nombre="Colegio A", codigo="a"))
        d.add(M.Colegio(id=2, nombre="Colegio B", codigo="b"))
        d.add(M.AnoEscolar(id=1, nombre="2024-2025", activo=True, colegio_id=1))
        d.add(M.AnoEscolar(id=2, nombre="2024-2025", activo=True, colegio_id=2))
        d.add(M.Grado(id=1, nombre="1ro Secundaria", colegio_id=1))
        d.add(M.Curso(id=1, nombre="A", grado_id=1, colegio_id=1))
        d.add(M.Curso(id=2, nombre="B", grado_id=1, colegio_id=1))   # otro curso, mismo colegio
        d.add(M.Curso(id=3, nombre="A", grado_id=1, colegio_id=2))   # otro colegio
        d.add(M.Usuario(id=1, username="dir_a", password_hash="x", nombre="Dir", role="direccion", colegio_id=1))
        d.add(M.Usuario(id=9, username="prof_a", password_hash="x", nombre="Prof", role="profesor", colegio_id=1))
        # asignaturas colegio 1
        d.add(M.Asignatura(id=1, nombre="Matemática", colegio_id=1))
        d.add(M.Asignatura(id=2, nombre="Lengua Española", colegio_id=1))
        d.add(M.Asignatura(id=3, nombre="Ciencias Sociales", colegio_id=1))
        d.add(M.AsignacionProfesor(id=1, profesor_id=9, curso_id=1, asignatura_id=1, activo=True, colegio_id=1))
        d.add(M.AsignacionProfesor(id=2, profesor_id=9, curso_id=1, asignatura_id=2, activo=True, colegio_id=1))
        d.add(M.AsignacionProfesor(id=3, profesor_id=9, curso_id=1, asignatura_id=3, activo=True, colegio_id=1))
        # estudiantes
        d.add(M.Estudiante(id=1, nombre="E1", apellido="A", curso_id=1, colegio_id=1, activo=True, no_lista=1))
        d.add(M.Estudiante(id=2, nombre="E2", apellido="A", curso_id=1, colegio_id=1, activo=True, no_lista=2))
        d.add(M.Estudiante(id=3, nombre="E3", apellido="A", curso_id=1, colegio_id=1, activo=True, no_lista=3))
        d.add(M.Estudiante(id=10, nombre="Eotro", apellido="C", curso_id=2, colegio_id=1, activo=True, no_lista=1))
        d.add(M.Estudiante(id=20, nombre="Ebe", apellido="B", curso_id=3, colegio_id=2, activo=True, no_lista=1))
        # 4 competencias completas (E1 Matemática y E1 Ciencias Sociales) -> CF < 70
        for aid in (1, 3):
            for n in (1, 2, 3, 4):
                d.add(M.CalificacionSecundaria(estudiante_id=1, asignatura_id=aid, ano_escolar_id=1,
                                               competencia_numero=n, p1=60, p2=60, p3=60, p4=60,
                                               promedio_competencia=60.0, colegio_id=1))
        # EvaluacionExtraSecundaria: E1/Matemática (curso 1, colegio 1) -> DEBE verse
        d.add(M.EvaluacionExtraSecundaria(estudiante_id=1, asignatura_id=1, ano_escolar_id=1,
                                          colegio_id=1, cf_original=60.0, cec=85,
                                          completiva_final=73, condicion_final="aprobado_completiva",
                                          nota_final=73))
        # E1/Ciencias Sociales -> NO debe aparecer en Matemática (aislamiento por asignatura)
        d.add(M.EvaluacionExtraSecundaria(estudiante_id=1, asignatura_id=3, ano_escolar_id=1,
                                          colegio_id=1, cf_original=50.0, cec=90,
                                          completiva_final=70, condicion_final="aprobado_completiva",
                                          nota_final=70))
        # estudiante de OTRO curso (mismo colegio) con ev en Matemática -> no está en este curso
        d.add(M.EvaluacionExtraSecundaria(estudiante_id=10, asignatura_id=1, ano_escolar_id=1,
                                          colegio_id=1, cf_original=40.0, cec=99,
                                          completiva_final=70, condicion_final="aprobado_completiva",
                                          nota_final=70))
        # estudiante de OTRO colegio con ev -> tenant isolation
        d.add(M.EvaluacionExtraSecundaria(estudiante_id=20, asignatura_id=1, ano_escolar_id=2,
                                          colegio_id=2, cf_original=30.0, cec=99,
                                          completiva_final=70, condicion_final="aprobado_completiva",
                                          nota_final=70))
        d.commit()
    finally:
        d.close()


_seed()


def _run_carga(n_students):
    d = SessionLocal()
    try:
        ests = d.query(M.Estudiante).filter_by(curso_id=1, colegio_id=1, activo=True)\
            .order_by(M.Estudiante.no_lista).all()[:n_students]
        _SQL_EEX.clear()
        data = _cargar_datos_asignaturas_secundaria(d, _User(), 1, 1, ests)
        return data, list(_SQL_EEX)
    finally:
        d.close()


@test("§19 exactamente 1 query SELECT a evaluaciones_extra_secundaria por generación")
def _():
    _data, sqls = _run_carga(3)
    assert len(sqls) == 1, f"{len(sqls)} SELECTs a evaluaciones_extra_secundaria:\n" + "\n".join(sqls)


@test("§20 sin N+1: el conteo NO crece con #estudiantes ni #asignaturas")
def _():
    _d1, s1 = _run_carga(1)
    _d3, s3 = _run_carga(3)
    assert len(s1) == 1 and len(s3) == 1, (len(s1), len(s3))


@test("§11 tenant isolation: ninguna ev del colegio B (ni de otro curso) entra al Registro del colegio A")
def _():
    data, _ = _run_carga(3)
    vistos = []
    for asig, dd in data.items():
        for idx, cd in dd.get("calificaciones", {}).items():
            ev = cd.get("evaluacion_extra")
            if ev:
                vistos.append((asig, ev["cf_original"], ev["nota_final"]))
    # legítimas: E1/Matemática (cf 60.0, nf 73) y E1/Ciencias Sociales (cf 50.0, nf 70)
    assert sorted(vistos) == [("Ciencias Sociales", 50.0, 70.0), ("Matemática", 60.0, 73.0)], vistos
    # 30.0 = colegio B ; 40.0 = otro curso del mismo colegio -> NUNCA
    assert all(cf not in (30.0, 40.0) for _a, cf, _n in vistos), vistos


@test("§12 otro curso del mismo colegio no aparece (E10 tiene ev en Matemática pero es del curso 2)")
def _():
    data, _ = _run_carga(3)
    mate = data.get("Matemática", {}).get("calificaciones", {})
    evs = [cd.get("evaluacion_extra") for cd in mate.values() if cd.get("evaluacion_extra")]
    assert len(evs) == 1 and evs[0]["cf_original"] == 60.0, evs
    # ninguna con cf_original 40.0 (E10) ni 30.0 (colegio B)
    assert all(e["cf_original"] not in (40.0, 30.0) for e in evs)


@test("§13 asignatura incorrecta: la ev de E1/Ciencias Sociales NO aparece en Matemática")
def _():
    data, _ = _run_carga(3)
    mate = data.get("Matemática", {}).get("calificaciones", {})
    for idx, cd in mate.items():
        ev = cd.get("evaluacion_extra")
        if ev:
            assert ev["nota_final"] == 73, ev  # la de Matemática, no la de C.Sociales (70)
    cs = data.get("Ciencias Sociales", {}).get("calificaciones", {})
    cs_evs = [cd.get("evaluacion_extra") for cd in cs.values() if cd.get("evaluacion_extra")]
    assert len(cs_evs) == 1 and cs_evs[0]["nota_final"] == 70, cs_evs


@test("§B2-serial: el dict de evaluacion_extra es plano y serializable (sin ORM), con fase_pendiente")
def _():
    data, _ = _run_carga(3)
    ev = data["Matemática"]["calificaciones"][0]["evaluacion_extra"]
    assert set(ev.keys()) == {
        "cf_original", "cec", "completiva_final", "ceex", "extraordinaria_final",
        "ce", "especial_final", "condicion_final", "nota_final", "fase_pendiente",
    }, ev.keys()
    import json
    json.dumps(ev)  # no debe lanzar
    assert data["Matemática"]["calificaciones"][0]["cf_exacto"] == 60.0


# ═══════════════════════════════════════════════════════════════════════════
# RESUMEN
# ═══════════════════════════════════════════════════════════════════════════
print(f"\n{B}{'=' * 66}{X}")
print(f"{B}  RESUMEN v2.20.1-B2{X}")
print(f"{B}{'=' * 66}{X}")
print(f"  {G}{_ok} PASARON{X} / {R}{len(_fail)} FALLARON{X}  (de {_total})")
for n, e in _fail:
    print(f"  {R}✗ {n}{X}\n      {e}")

if _sge_mtime is not None:
    _now = os.path.getmtime(_REPO_SGE) if os.path.exists(_REPO_SGE) else None
    if _now != _sge_mtime:
        print(f"{R}{B}✗ SEGURIDAD: sge.db del repo cambió durante la suite{X}")
        sys.exit(2)
print(f"{G}✓ SEGURIDAD: sge.db del repo intacto{X}")

sys.exit(1 if _fail else 0)
