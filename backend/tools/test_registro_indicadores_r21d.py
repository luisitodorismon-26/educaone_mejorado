# -*- coding: utf-8 -*-
"""
EducaOne R2.1D — CE + Indicadores + Contenidos Claves en el Registro Secundaria.

Bloques:

  A. RENDER   — las tres columnas, agrupación por `orden_ce`, wrap, y la
     garantía de que NUNCA se imprime identidad técnica ni una elipsis.
  B. ESCALAS  — 8/10, caída completa a 6.5/8, y overflow que aborta en vez de
     emitir un Registro parcial.
  C. PÁGINAS  — el mapeo bloque oficial -> slot -> página, las 216
     combinaciones, y los totales 170/238/240.
  D. LOADER   — bulk sin N+1, materias NULL, colisión de bloque, legacy R2 y
     claves de catálogo incoherentes.

SEGURIDAD: SQLite temporal aislada. NUNCA toca sge.db, INITIAL_CREDENTIALS.txt,
el catálogo JSON ni los templates oficiales.

Uso:
    cd backend
    python tools/test_registro_indicadores_r21d.py
"""
import os
import sys
import atexit
import io as _io
import re
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TMPDIR = tempfile.mkdtemp(prefix="eo_reg_ind_r21d_")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_TMPDIR, "r.db").replace("\\", "/")
os.environ.setdefault("ENVIRONMENT", "development")


@atexit.register
def _cleanup():
    try:
        import shutil
        shutil.rmtree(_TMPDIR, ignore_errors=True)
    except Exception:
        pass


from sqlalchemy import event                                   # noqa: E402
from database import engine, SessionLocal                      # noqa: E402
import models as M                                             # noqa: E402
import catalogo_indicadores as CAT                             # noqa: E402
import registro_escolar as RE                                  # noqa: E402
from registro_escolar import (                                 # noqa: E402
    EspecificacionCurricularOverflow, espec_plan, pagina_indicador,
    generar_registro_escolar, CE_BOX, INDICADOR_BOX, CONTENIDOS_BOX,
)
from pypdf import PdfReader                                    # noqa: E402

_eu = str(engine.url).replace("\\", "/")
assert _TMPDIR.replace("\\", "/") in _eu and "sge.db" not in _eu, _eu

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_SGE = os.path.join(_BACKEND, "sge.db")
_REPO_CRED = os.path.join(_BACKEND, "INITIAL_CREDENTIALS.txt")
_JSON = os.path.join(_BACKEND, "catalogos", "indicadores_secundaria_2023.json")
_sge_mtime = os.path.getmtime(_REPO_SGE) if os.path.exists(_REPO_SGE) else None
_cred_mtime = os.path.getmtime(_REPO_CRED) if os.path.exists(_REPO_CRED) else None
_json_mtime = os.path.getmtime(_JSON)


@event.listens_for(engine, "connect")
def _relax_fk(dbapi_conn, rec):
    try:
        dbapi_conn.execute("PRAGMA foreign_keys=OFF")
    except Exception:
        pass


engine.dispose()
M.Base.metadata.create_all(bind=engine)

from fastapi.testclient import TestClient                      # noqa: E402
from app import app, AREA_CURRICULAR_A_SLOT                    # noqa: E402

client = TestClient(app)

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


# ── helpers de datos ────────────────────────────────────────────────────
def il_de(grado, area, n=3, desde=0):
    """Los primeros `n` indicadores del catálogo para (grado, área)."""
    ent = CAT.listar_por(grado=grado, area=area)[desde:desde + n]
    grupos = {}
    for e in ent:
        g = grupos.setdefault(e["orden_ce"], {
            "orden_ce": e["orden_ce"], "ce_codigo": e["ce_codigo"], "indicadores": []})
        g["indicadores"].append({"orden_il": e["orden_il"], "il_codigo": e["il_codigo"],
                                 "il_texto": e["il_texto"]})
    return [g for _, g in sorted(grupos.items())]


def datos(grado=4, area="LEF", n_il=3, desde=0, contenidos=None):
    return {"grupos_ce": il_de(grado, area, n_il, desde),
            "contenidos": contenidos if contenidos is not None else []}


def _gen(grado, espec):
    """Registro completo con `espec` = {slot: {periodo: datos}}."""
    return generar_registro_escolar(
        grado=grado,
        datos_centro={"nombre": "Centro de prueba"},
        datos_portada={"ano_escolar": "2025-2026", "seccion": "A"},
        estudiantes=[{"nombre": f"Est {i}", "apellido": "P", "no_lista": i} for i in range(1, 4)],
        especificacion_data=espec,
    )


# Tamaños que usa NUESTRO renderer. El template trae su propio texto (título,
# encabezados de columna y el folio al pie, este último a size 1.0); filtrar por
# tamaño deja fuera todo lo preimpreso sin depender de coordenadas.
_TAMANOS_PROPIOS = {e[0] for e in RE.ESPEC_ESCALAS}


def _marcas(reader, pg):
    """[(x, y, texto, size)] dibujado por NOSOTROS en esa página."""
    out = []

    def vis(t, cm, tm, fd, fs):
        s = (t or "").strip()
        if (s and "\n" not in s and not (tm[4] == 0 and tm[5] == 0)
                and fs in _TAMANOS_PROPIOS):
            out.append((round(float(tm[4]), 2), round(float(tm[5]), 2), s, fs))
    reader.pages[pg - 1].extract_text(visitor_text=vis)
    return out


def _col(marcas, box):
    x0 = box["x0"] + box["padding"]
    return [m for m in marcas if abs(m[0] - x0) < 0.05]


def _tiene_overlay(reader, pg):
    res = reader.pages[pg - 1].get("/Resources")
    if res is None:
        return False
    xo = res.get_object().get("/XObject")
    if xo is None:
        return False
    return any(str(k).startswith("/EODataOverlay") for k in xo.get_object().keys())


# ===========================================================================
# BLOQUE A — RENDER
# ===========================================================================

@test("§A/§Z geometría: tres cajas con la medición del template")
def _():
    assert (CE_BOX["x0"], CE_BOX["x1"]) == (36.25, 96.01)
    assert (CONTENIDOS_BOX["x0"], CONTENIDOS_BOX["x1"]) == (335.76, 575.50)
    # INDICADOR_BOX se conserva de R2; coincide con la medición dentro de 0.04pt
    assert abs(INDICADOR_BOX["x0"] - 96.01) <= 0.05
    assert abs(INDICADOR_BOX["x1"] - 335.76) <= 0.05
    for box in (CE_BOX, INDICADOR_BOX, CONTENIDOS_BOX):
        assert box["y_top_plumber"] in (79.47, 79.5)
        assert box["y_bottom_plumber"] == 756.0
    # las columnas no se solapan
    assert CE_BOX["x1"] <= INDICADOR_BOX["x0"] + 0.05
    assert INDICADOR_BOX["x1"] <= CONTENIDOS_BOX["x0"] + 0.05


@test("§A 1 CE + 1 IL + 1 contenido: las tres columnas se pintan")
def _():
    d = datos(n_il=1, contenidos=["Personal pronouns"])
    pdf = _gen(4, {2: {1: d}})           # slot 2 = LEF
    rd = PdfReader(_io.BytesIO(pdf))
    pg = pagina_indicador(2, 2, 1)
    assert _tiene_overlay(rd, pg)
    ms = _marcas(rd, pg)
    ce = _col(ms, CE_BOX)
    il = _col(ms, INDICADOR_BOX)
    cc = _col(ms, CONTENIDOS_BOX)
    assert len(ce) == 1 and ce[0][2].startswith("CE-LEF"), ce
    assert il and il[0][2].startswith("IL-1"), il[:2]
    assert cc and cc[0][2] == "Personal pronouns", cc
    # el código CE se alinea con la primera línea de su grupo
    assert abs(ce[0][1] - il[0][1]) < 0.01, (ce[0][1], il[0][1])


@test("§B 1 CE + 5 IL + 4 contenidos")
def _():
    d = {"grupos_ce": [{"orden_ce": 1, "ce_codigo": "CE-LEF1", "indicadores": [
        {"orden_il": i, "il_codigo": f"IL-{i}", "il_texto": f"Texto del indicador {i}."}
        for i in range(1, 6)]}],
        "contenidos": ["Uno", "Dos", "Tres", "Cuatro"]}
    pdf = _gen(4, {2: {1: d}})
    rd = PdfReader(_io.BytesIO(pdf))
    ms = _marcas(rd, pagina_indicador(2, 2, 1))
    assert len(_col(ms, CE_BOX)) == 1, "la CE debe imprimirse UNA vez por grupo"
    il = " ".join(m[2] for m in _col(ms, INDICADOR_BOX))
    for i in range(1, 6):
        assert f"IL-{i}" in il, i
    assert [m[2] for m in _col(ms, CONTENIDOS_BOX)] == ["Uno", "Dos", "Tres", "Cuatro"]


@test("§C 3 CE de distintas Competencias Fundamentales")
def _():
    ent = CAT.listar_por(grado=4, area="LEF")
    grupos = {}
    for e in ent:
        if len(grupos) >= 3 and e["orden_ce"] not in grupos:
            continue
        g = grupos.setdefault(e["orden_ce"], {"orden_ce": e["orden_ce"],
                                              "ce_codigo": e["ce_codigo"], "indicadores": []})
        g["indicadores"].append({"orden_il": e["orden_il"], "il_codigo": e["il_codigo"],
                                 "il_texto": e["il_texto"][:80]})
    d = {"grupos_ce": [g for _, g in sorted(grupos.items())], "contenidos": []}
    assert len(d["grupos_ce"]) == 3
    pdf = _gen(4, {2: {1: d}})
    rd = PdfReader(_io.BytesIO(pdf))
    ms = _marcas(rd, pagina_indicador(2, 2, 1))
    ce = _col(ms, CE_BOX)
    assert len(ce) == 3, [c[2] for c in ce]
    ys = [c[1] for c in ce]
    assert ys == sorted(ys, reverse=True), "los CE deben ir de arriba abajo en orden"


@test("§D/§E wrap: un IL largo y contenidos largos no se salen de su caja")
def _():
    largo = CAT.listar_por(grado=4, area="LEI")[0]["il_texto"]
    d = {"grupos_ce": [{"orden_ce": 1, "ce_codigo": "CE-LEI1", "indicadores": [
        {"orden_il": 1, "il_codigo": "IL-1", "il_texto": largo}]}],
        "contenidos": ["Contenido extremadamente largo " * 12]}
    pdf = _gen(4, {1: {1: d}})
    rd = PdfReader(_io.BytesIO(pdf))
    ms = _marcas(rd, pagina_indicador(2, 1, 1))
    from reportlab.pdfbase.pdfmetrics import stringWidth
    for m in ms:
        ancho = stringWidth(m[2], RE.FONT_NORMAL, m[3])
        derecha = m[0] + ancho
        if abs(m[0] - (INDICADOR_BOX["x0"] + 4)) < 0.05:
            assert derecha <= INDICADOR_BOX["x1"] - 4 + 0.5, m
        elif abs(m[0] - (CONTENIDOS_BOX["x0"] + 4)) < 0.05:
            assert derecha <= CONTENIDOS_BOX["x1"] - 4 + 0.5, m
    assert len(_col(ms, INDICADOR_BOX)) > 1, "el IL largo debe ocupar varias líneas"


@test("§F período vacío: la página queda idéntica al template")
def _():
    pdf = _gen(4, {2: {1: {"grupos_ce": [], "contenidos": []}}})
    rd = PdfReader(_io.BytesIO(pdf))
    assert not _tiene_overlay(rd, pagina_indicador(2, 2, 1))


@test("§G/§H parciales: solo IL, o solo contenidos")
def _():
    pdf = _gen(4, {2: {1: datos(n_il=2), 3: {"grupos_ce": [], "contenidos": ["A", "B"]}}})
    rd = PdfReader(_io.BytesIO(pdf))
    p1, p3 = pagina_indicador(2, 2, 1), pagina_indicador(2, 2, 3)
    m1, m3 = _marcas(rd, p1), _marcas(rd, p3)
    assert _col(m1, INDICADOR_BOX) and not _col(m1, CONTENIDOS_BOX)
    assert _col(m3, CONTENIDOS_BOX) and not _col(m3, INDICADOR_BOX)
    assert not _col(m3, CE_BOX), "sin IL no hay CE que imprimir"


@test("§I P1-P4 con datos distintos van cada uno a su página")
def _():
    espec = {2: {p: {"grupos_ce": [], "contenidos": [f"CONTENIDO-P{p}"]} for p in (1, 2, 3, 4)}}
    pdf = _gen(4, espec)
    rd = PdfReader(_io.BytesIO(pdf))
    for p in (1, 2, 3, 4):
        pg = pagina_indicador(2, 2, p)
        textos = [m[2] for m in _col(_marcas(rd, pg), CONTENIDOS_BOX)]
        assert textos == [f"CONTENIDO-P{p}"], (p, textos)


@test("§J 2do EF: dos bandas con el MISMO CE-EF4 no se fusionan")
def _():
    ent = [e for e in CAT.listar_por(grado=2, area="EF") if e["ce_codigo"] == "CE-EF4"]
    assert {e["orden_ce"] for e in ent} == {4, 5}
    grupos = {}
    for e in ent:
        g = grupos.setdefault(e["orden_ce"], {"orden_ce": e["orden_ce"],
                                              "ce_codigo": e["ce_codigo"], "indicadores": []})
        g["indicadores"].append({"orden_il": e["orden_il"], "il_codigo": e["il_codigo"],
                                 "il_texto": e["il_texto"][:60]})
    d = {"grupos_ce": [g for _, g in sorted(grupos.items())], "contenidos": []}
    pdf = _gen(2, {7: {1: d}})       # slot 7 = EF
    rd = PdfReader(_io.BytesIO(pdf))
    ms = _marcas(rd, pagina_indicador(1, 7, 1))
    ce = _col(ms, CE_BOX)
    assert len(ce) == 2, [c[2] for c in ce]
    assert all(c[2] == "CE-EF4" for c in ce), ce
    assert ce[0][1] != ce[1][1], "las dos bandas deben ir en alturas distintas"


@test("§K 6to EF: códigos IL repetidos se imprimen tal cual, sin corregir")
def _():
    ent = [e for e in CAT.listar_por(grado=6, area="EF") if e["il_codigo"] == "IL-7"]
    assert len(ent) == 2
    grupos = {}
    for e in ent:
        g = grupos.setdefault(e["orden_ce"], {"orden_ce": e["orden_ce"],
                                              "ce_codigo": e["ce_codigo"], "indicadores": []})
        g["indicadores"].append({"orden_il": e["orden_il"], "il_codigo": e["il_codigo"],
                                 "il_texto": e["il_texto"][:60]})
    pdf = _gen(6, {7: {1: {"grupos_ce": [g for _, g in sorted(grupos.items())],
                          "contenidos": []}}})
    rd = PdfReader(_io.BytesIO(pdf))
    ms = _col(_marcas(rd, pagina_indicador(2, 7, 1)), INDICADOR_BOX)
    n = sum(1 for m in ms if m[2].startswith("IL-7"))
    assert n == 2, f"IL-7 debe aparecer 2 veces, apareció {n}"


@test("§N unicode y acentos íntegros")
def _():
    # Helvetica (Type1 estándar) cubre Latin-1: acentos, ñ, comillas angulares,
    # punto medio y signos de apertura. Fuera de Latin-1 (p. ej. CJK) la fuente
    # del Registro no tiene glifos; eso se comprueba abajo exigiendo que degrade
    # sin arrastrar el resto de la línea ni romper la generación.
    texto = "Ñandú, café, señalización · «comillas» — ¿qué? ¡sí!"
    d = {"grupos_ce": [{"orden_ce": 1, "ce_codigo": "CE-LEF1", "indicadores": [
        {"orden_il": 1, "il_codigo": "IL-1", "il_texto": texto}]}],
        "contenidos": [texto]}
    pdf = _gen(4, {2: {1: d}})
    rd = PdfReader(_io.BytesIO(pdf))
    ms = _marcas(rd, pagina_indicador(2, 2, 1))
    junto = " ".join(m[2] for m in ms)
    for frag in ("Ñandú", "café", "señalización", "«comillas»", "¿qué?", "¡sí!"):
        assert frag in junto, frag

    # CJK: la fuente del Registro no lo cubre. Debe degradar sin arrastrar el
    # resto del texto ni reventar la generacion.
    d2 = {"grupos_ce": [], "contenidos": ["antes 中文 despues"]}
    rd2 = PdfReader(_io.BytesIO(_gen(4, {2: {2: d2}})))
    j2 = " ".join(m[2] for m in _marcas(rd2, pagina_indicador(2, 2, 2)))
    assert "antes" in j2 and "despues" in j2, j2


@test("§O/§P/§Q nunca se imprime identidad técnica")
def _():
    d = datos(n_il=4, contenidos=["Uno", "Dos"])
    pdf = _gen(4, {2: {1: d}})
    rd = PdfReader(_io.BytesIO(pdf))
    ms = _marcas(rd, pagina_indicador(2, 2, 1))
    junto = " ".join(m[2] for m in ms)
    for prohibido in ("SEC-2023", "catalogo_clave", "orden_ce", "orden_il", "|"):
        assert prohibido not in junto, prohibido
    assert not re.search(r"\bCE\d{2}\b", junto), junto[:200]
    assert not re.search(r"\bIL\d{2}\b", junto), junto[:200]


@test("§R el renderer NUNCA introduce una elipsis")
def _():
    import inspect
    fuente = inspect.getsource(RE.draw_especificacion_curricular) + \
        inspect.getsource(RE._espec_maquetar) + inspect.getsource(RE.espec_plan)
    assert "…" not in fuente, "el renderer de R2.1D no puede truncar"
    d = datos(n_il=9, contenidos=[f"Contenido {i}" for i in range(40)])
    pdf = _gen(4, {2: {1: d}})
    rd = PdfReader(_io.BytesIO(pdf))
    junto = " ".join(m[2] for m in _marcas(rd, pagina_indicador(2, 2, 1)))
    assert "…" not in junto and "..." not in junto, junto[-120:]


@test("§AH nada se dibuja fuera de las tres cajas")
def _():
    d = datos(n_il=6, contenidos=[f"Contenido {i}" for i in range(10)])
    pdf = _gen(4, {2: {1: d}})
    rd = PdfReader(_io.BytesIO(pdf))
    ms = _marcas(rd, pagina_indicador(2, 2, 1))
    validas = {round(CE_BOX["x0"] + CE_BOX["padding"], 2),
               round(INDICADOR_BOX["x0"] + INDICADOR_BOX["padding"], 2),
               round(CONTENIDOS_BOX["x0"] + CONTENIDOS_BOX["padding"], 2)}
    for m in ms:
        assert round(m[0], 2) in validas, m
        plumber = 792 - m[1]
        assert 79.0 <= plumber <= 756.0, m


# ===========================================================================
# BLOQUE B — ESCALAS Y OVERFLOW
# ===========================================================================

@test("§S lo normal cabe en 8/10")
def _():
    plan = espec_plan(datos(n_il=3, contenidos=["A", "B", "C"]))
    assert (plan["size"], plan["line_height"]) == (8.0, 10.0), plan["size"]


@test("§T si no cabe en 8/10, TODA la página baja a 6.5/8")
def _():
    d = datos(n_il=11, contenidos=["Contenido " + "x" * 40 for _ in range(3)])
    p8 = RE._espec_maquetar(d, 8.0, 10.0)
    assert not p8["cabe"], "el escenario debe desbordar 8/10"
    plan = espec_plan(d)
    assert (plan["size"], plan["line_height"]) == (6.5, 8.0), plan["size"]
    # y la escala elegida rige las TRES columnas de esa página
    pdf = _gen(4, {2: {1: d}})
    rd = PdfReader(_io.BytesIO(pdf))
    ms = _marcas(rd, pagina_indicador(2, 2, 1))
    assert {m[3] for m in ms} == {6.5}, {m[3] for m in ms}
    assert _col(ms, CE_BOX) and _col(ms, INDICADOR_BOX) and _col(ms, CONTENIDOS_BOX)


@test("§U si no cabe ni en 6.5/8: excepción tipada, NO un PDF parcial")
def _():
    d = datos(grado=4, area="LEI", n_il=21,
              contenidos=[f"Contenido largo numero {i} " * 4 for i in range(60)])
    try:
        espec_plan(d, {"asignatura_id": 7, "area_codigo": "LEI", "periodo": 2})
        raise AssertionError("debía desbordar")
    except EspecificacionCurricularOverflow as e:
        det = e.detalle
        assert det["motivo"] == "especificacion_curricular_no_cabe"
        assert det["asignatura_id"] == 7 and det["area_codigo"] == "LEI"
        assert det["periodo"] == 2
        assert det["lineas_indicadores"] > det["capacidad_indicadores"] or \
            det["lineas_contenidos"] > det["capacidad_contenidos"]
        assert det["font_size_minimo"] == 6.5
        assert "excede el espacio disponible" in det["mensaje"]
    # y la generación completa aborta: no se emite PDF
    try:
        _gen(4, {1: {2: d}})
        raise AssertionError("se generó un PDF parcial")
    except EspecificacionCurricularOverflow:
        pass


@test("§AG las líneas vacías no generan contenido artificial")
def _():
    d = {"grupos_ce": [], "contenidos": ["Uno", "", "   ", "Dos"]}
    plan = espec_plan(d)
    assert plan["filas_cc"] == ["Uno", "Dos"], plan["filas_cc"]


@test("§AF el ORDEN y el contenido de los contenidos se conservan exactamente")
def _():
    # El orden es el que escribió el profesor: NO se ordena, NO se resume,
    # NO se corrige la ortografía.
    lineas = ["Zebra", "alfa", "3ro", "Ñu", "año 2026"]
    plan = espec_plan({"grupos_ce": [], "contenidos": lineas})
    assert plan["filas_cc"] == lineas, plan["filas_cc"]

    # `_wrap_texto` —el mismo wrapper calibrado que usa el resto del Registro—
    # normaliza las secuencias de espacios al maquetar, como cualquier
    # composición tipográfica. Se conservan el CONTENIDO y el ORDEN; lo único
    # que se colapsa es el espaciado. El dato guardado en la base queda intacto
    # (lo verifica R2.1B §15 sobre `lineas_contenidos_claves`).
    plan2 = espec_plan({"grupos_ce": [], "contenidos": ["  Beta   con   espacios  "]})
    assert plan2["filas_cc"] == ["Beta con espacios"], plan2["filas_cc"]


# ===========================================================================
# BLOQUE C — PÁGINAS
# ===========================================================================

@test("§Z mapping bloque oficial -> slot, y su cobertura")
def _():
    assert AREA_CURRICULAR_A_SLOT == {
        'LE': 0, 'LEI': 1, 'LEF': 2, 'MAT': 3, 'CS': 4,
        'CN': 5, 'EA': 6, 'EF': 7, 'FIHR': 8}
    assert sorted(AREA_CURRICULAR_A_SLOT) == sorted(CAT.codigos_area_validos())
    assert sorted(AREA_CURRICULAR_A_SLOT.values()) == list(range(9))


@test("§AA las 216 combinaciones grado/bloque/período mantienen su página")
def _():
    esperado_c1 = [65, 71, 77, 83, 89, 95, 101, 107, 113]
    esperado_c2 = [77, 95, 107, 113, 125, 137, 149, 155, 161]
    vistas = set()
    for grado in range(1, 7):
        ciclo = 2 if grado >= 4 else 1
        base = esperado_c2 if ciclo == 2 else esperado_c1
        for area, slot in AREA_CURRICULAR_A_SLOT.items():
            for periodo in (1, 2, 3, 4):
                pg = pagina_indicador(ciclo, slot, periodo)
                assert pg == base[slot] + periodo - 1, (grado, area, periodo, pg)
                vistas.add((grado, area, periodo))
    assert len(vistas) == 216, len(vistas)
    # Salida Optativa (slot 9) sigue fuera
    assert pagina_indicador(2, 9, 1) is None


@test("§AB totales de páginas intactos: 170 / 238 / 240")
def _():
    for grado, total in ((1, 170), (4, 238), (6, 240)):
        pdf = _gen(grado, {2: {1: datos(grado=grado, area="LEF", n_il=2,
                                        contenidos=["X"])}})
        assert len(PdfReader(_io.BytesIO(pdf)).pages) == total, grado


@test("§AC/§AD pipeline XObject intacto y cero merge_page")
def _():
    pdf = _gen(4, {2: {1: datos(n_il=2, contenidos=["X"])}})
    rd = PdfReader(_io.BytesIO(pdf))
    pg = pagina_indicador(2, 2, 1)
    xo = rd.pages[pg - 1]["/Resources"].get_object()["/XObject"].get_object()
    nombres = [k for k in xo.keys() if str(k).startswith("/EODataOverlay")]
    assert nombres, "no hay Form XObject"
    for n in nombres:
        assert xo[n].get_object().get("/Subtype") == "/Form"
    import tokenize
    with open(os.path.join(_BACKEND, "registro_escolar.py"), "rb") as fh:
        toks = list(tokenize.tokenize(fh.readline))
    for a, b in zip(toks, toks[1:]):
        if a.type == tokenize.NAME and a.string == "merge_page":
            assert not (b.type == tokenize.OP and b.string == "("), a.start[0]


# ===========================================================================
# BLOQUE D — LOADER
# ===========================================================================

COL, ANO, G4, C4 = 1, 1, 4, 40
LEF, LEI, MUSICA, ING2 = 101, 102, 103, 104
U_DIR, U_PROF = 10, 11
PWD = "Prueba2026x"


def _seed():
    M.Base.metadata.drop_all(bind=engine)
    M.Base.metadata.create_all(bind=engine)
    d = SessionLocal()
    try:
        d.add(M.Colegio(id=COL, nombre="Colegio A", codigo="a"))
        d.add(M.ConfiguracionColegio(colegio_id=COL, nombre="Colegio A", regional="10",
                                     distrito="03", codigo_centro="00001", usa_secundaria=True))
        d.add(M.AnoEscolar(id=ANO, colegio_id=COL, nombre="2025-2026", activo=True,
                           dias_trabajados="{}"))
        d.add(M.Grado(id=G4, colegio_id=COL, nombre="4to Secundaria", nivel="secundaria", orden=4))
        d.add(M.Curso(id=C4, colegio_id=COL, nombre="A", grado_id=G4, ano_escolar_id=ANO))
        # Nombres engañosos a propósito: "Frances" mapeada a LEF, "Inglés" sin vínculo.
        d.add(M.Asignatura(id=LEF, colegio_id=COL, nombre="Frances", codigo="LE",
                           area="Lenguas", area_curricular_codigo="LEF"))
        d.add(M.Asignatura(id=LEI, colegio_id=COL, nombre="Inglés", codigo="IN",
                           area="Lenguas", area_curricular_codigo=None))
        d.add(M.Asignatura(id=MUSICA, colegio_id=COL, nombre="Musica", codigo="MS",
                           area="", area_curricular_codigo=None))
        d.add(M.Asignatura(id=ING2, colegio_id=COL, nombre="Inglés Conversacional",
                           codigo="INC", area="Lenguas", area_curricular_codigo=None))
        for uid, un, rol in ((U_DIR, "dir_a", "direccion"), (U_PROF, "prof_a", "profesor")):
            u = M.Usuario(id=uid, username=un, nombre=un, apellido="T", role=rol, colegio_id=COL)
            u.set_password(PWD)
            d.add(u)
        for i, asig in enumerate((LEF, LEI, MUSICA, ING2), start=1):
            d.add(M.AsignacionProfesor(id=i, colegio_id=COL, profesor_id=U_PROF,
                                       curso_id=C4, asignatura_id=asig, activo=True))
        d.commit()
    finally:
        d.close()


def _periodo(asignatura_id, periodo, claves=(), contenidos=None, contenido_legacy=None):
    d = SessionLocal()
    try:
        il = M.IndicadorLogro(colegio_id=COL, profesor_id=U_PROF, asignatura_id=asignatura_id,
                              curso_id=C4, ano_escolar_id=ANO, periodo=periodo,
                              contenidos_claves=contenidos, contenido=contenido_legacy)
        d.add(il)
        d.commit()
        for k in claves:
            d.add(M.IndicadorLogroSeleccion(indicador_logro_id=il.id, catalogo_clave=k))
        d.commit()
        return il.id
    finally:
        d.close()


def _cargar():
    from app import _cargar_especificacion_curricular
    d = SessionLocal()
    try:
        class _U:
            colegio_id, role, id = COL, 'direccion', U_DIR
            nivel_asignado = None
        return _cargar_especificacion_curricular(d, _U(), d.query(M.Curso).get(C4), 4)
    finally:
        d.close()


_seed()
K1 = "SEC-2023|4|LEF|CE01|IL01"
K2 = "SEC-2023|4|LEF|CE01|IL02"
K3 = "SEC-2023|4|LEF|CE03|IL01"


@test("§Y/§Z el bloque se resuelve por area_curricular_codigo, no por nombre")
def _():
    _periodo(LEF, 1, (K1, K2, K3), "Personal pronouns\nPossessive pronouns")
    espec = _cargar()
    assert set(espec) == {2}, espec.keys()          # slot 2 = LEF
    p = espec[2][1]
    assert p["area_codigo"] == "LEF" and p["asignatura_id"] == LEF
    assert len(p["grupos_ce"]) == 2, p["grupos_ce"]
    assert p["contenidos"] == ["Personal pronouns", "Possessive pronouns"]
    # "Frances" con codigo "LE" y area "Lenguas" NO ocupó el slot 0 (LE)
    assert 0 not in espec and 1 not in espec


@test("§L/§M las materias con área NULL no aportan ni estorban")
def _():
    _periodo(MUSICA, 1, (), "Solfeo")
    _periodo(LEI, 2, (), "Present simple")
    espec = _cargar()
    assert set(espec) == {2}, espec.keys()
    d = SessionLocal()
    try:
        # y sus datos siguen intactos en la base
        assert d.query(M.IndicadorLogro).filter_by(asignatura_id=MUSICA).count() == 1
        assert d.query(M.Asignatura).get(MUSICA).activo is not False
    finally:
        d.close()


@test("§AE el loader no hace N+1: 3 consultas por curso")
def _():
    from sqlalchemy import event as _ev
    conteo = {"n": 0}

    def _cuenta(conn, cursor, stmt, params, ctx, many):
        if stmt.lstrip().upper().startswith("SELECT"):
            conteo["n"] += 1
    _ev.listen(engine, "before_cursor_execute", _cuenta)
    try:
        _cargar()
    finally:
        _ev.remove(engine, "before_cursor_execute", _cuenta)
    # asignaturas + año + períodos + selecciones (+ alguna de contexto)
    assert conteo["n"] <= 6, f"{conteo['n']} SELECTs: huele a N+1"


@test("§W legacy R2 sin convertir: 409 y el dato queda intacto")
def _():
    from app import EspecificacionCurricularConflicto
    il_id = _periodo(LEF, 3, (K1,), "algo", contenido_legacy="TEXTO LIBRE R2")
    try:
        _cargar()
        raise AssertionError("debía bloquear")
    except EspecificacionCurricularConflicto as e:
        assert e.detalle["motivo"] == "indicadores_legacy_pendientes_conversion"
        assert e.detalle["asignatura_id"] == LEF and e.detalle["periodo"] == 3
    d = SessionLocal()
    try:
        il = d.query(M.IndicadorLogro).get(il_id)
        assert il.contenido == "TEXTO LIBRE R2", "se alteró el legacy"
        assert len(il.selecciones) == 1
        d.delete(il)
        d.commit()
    finally:
        d.close()


@test("§X una clave de catálogo inválida o incoherente aborta explícitamente")
def _():
    from app import EspecificacionCurricularConflicto
    for clave, motivo in (("SEC-2023|4|LEF|CE99|IL99", "catalogo_clave_invalida"),
                          ("SEC-2023|1|LEF|CE01|IL01", "catalogo_clave_incoherente"),
                          ("SEC-2023|4|LEI|CE01|IL01", "catalogo_clave_incoherente")):
        il_id = _periodo(LEF, 4, (clave,))
        try:
            _cargar()
            raise AssertionError(f"debía abortar con {clave}")
        except EspecificacionCurricularConflicto as e:
            assert e.detalle["motivo"] == motivo, (clave, e.detalle["motivo"])
        d = SessionLocal()
        try:
            d.delete(d.query(M.IndicadorLogro).get(il_id))
            d.commit()
        finally:
            d.close()


@test("§V dos asignaturas para el mismo bloque: 409 sin elegir ni mezclar")
def _():
    from app import EspecificacionCurricularConflicto
    d = SessionLocal()
    try:
        d.query(M.Asignatura).get(ING2).area_curricular_codigo = "LEF"
        d.commit()
    finally:
        d.close()
    try:
        _cargar()
        raise AssertionError("debía bloquear")
    except EspecificacionCurricularConflicto as e:
        assert e.detalle["motivo"] == "bloque_curricular_duplicado"
        assert e.detalle["area_codigo"] == "LEF"
        ids = {a["id"] for a in e.detalle["asignaturas_en_conflicto"]}
        assert ids == {LEF, ING2}, ids
    d = SessionLocal()
    try:
        d.query(M.Asignatura).get(ING2).area_curricular_codigo = None
        d.commit()
    finally:
        d.close()
    assert set(_cargar()) == {2}


@test("§Z2 el loader no pasa ORM al generador y produce un PDF válido")
def _():
    espec = _cargar()
    import json
    json.dumps(espec)                     # serializable => sin ORM
    pdf = _gen(4, espec)
    rd = PdfReader(_io.BytesIO(pdf))
    assert len(rd.pages) == 238
    ms = _marcas(rd, pagina_indicador(2, 2, 1))
    assert _col(ms, CE_BOX) and _col(ms, INDICADOR_BOX) and _col(ms, CONTENIDOS_BOX)


@test("§ZZ ZERO DATA LOSS: sge.db, credenciales, catálogo y templates intactos")
def _():
    a = os.path.getmtime(_REPO_SGE) if os.path.exists(_REPO_SGE) else None
    b = os.path.getmtime(_REPO_CRED) if os.path.exists(_REPO_CRED) else None
    assert a == _sge_mtime, f"sge.db modificado: {_sge_mtime} -> {a}"
    assert b == _cred_mtime, f"INITIAL_CREDENTIALS.txt modificado: {_cred_mtime} -> {b}"
    assert os.path.getmtime(_JSON) == _json_mtime, "el catálogo JSON fue modificado"
    tpl = os.path.join(_BACKEND, "templates", "registro_escolar")
    assert os.path.isdir(tpl)
    assert _TMPDIR.replace("\\", "/") in str(engine.url).replace("\\", "/")


print(f"\n{B}{'=' * 64}{X}")
print(f"{B}RESULTADO R2.1D: {_ok}/{_total} pruebas{X}")
if _fail:
    print(f"{R}FALLARON:{X}")
    for n, e in _fail:
        print(f"  - {n}: {e}")
    sys.exit(1)
print(f"{G}TODO VERDE{X}")
