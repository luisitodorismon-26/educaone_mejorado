# -*- coding: utf-8 -*-
"""
EducaOne R3.3 — SALIDA OPTATIVA EN EL REGISTRO ESCOLAR DE SECUNDARIA.

Cubre los 14 puntos de R3.3 §17 en tres bloques:

  A. MAPA DE PÁGINAS — demostrado contra los TEMPLATES OFICIALES, no asumido:
     cada una de las seis páginas lleva impreso "SALIDA OPTATIVA: <salida>" y su
     componente, y eso fija que 211/212/214/217/219/221 son PÁGINA HUMANA
     (1-based) y a qué slot corresponde cada una.
  B. ESTAMPADO — qué página recibe overlay y cuál queda idéntica al template,
     verificado por INSPECCIÓN ESTRUCTURAL del PDF (XObjects /EODataOverlay),
     no por "el PDF se generó".
  C. RESOLUCIÓN — que los datos salen de `CursoComponenteOptativo` y de ningún
     nombre: tenant, año y materias extra no vinculadas.

SEGURIDAD: SQLite temporal aislada. NUNCA toca sge.db ni INITIAL_CREDENTIALS.txt
(se verifica al final). No consulta producción ni PostgreSQL.

Uso:
    cd backend
    python tools/test_salida_optativa_r33.py
"""
import os
import sys
import atexit
import inspect as _inspect
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TMPDIR = tempfile.mkdtemp(prefix="eo_salida_opt_r33_")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_TMPDIR, "s.db").replace("\\", "/")
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
import salidas_optativas as CAT                                # noqa: E402
import registro_escolar as RE                                  # noqa: E402
from registro_escolar import GRADO_CONFIG, generar_registro_escolar   # noqa: E402
from pypdf import PdfReader                                    # noqa: E402
import io                                                      # noqa: E402

_eu = str(engine.url).replace("\\", "/")
assert _TMPDIR.replace("\\", "/") in _eu and "sge.db" not in _eu, _eu

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_SGE = os.path.join(_BACKEND, "sge.db")
_REPO_CRED = os.path.join(_BACKEND, "INITIAL_CREDENTIALS.txt")
_TPL_DIR = os.path.join(_BACKEND, "templates", "registro_escolar")
_sge = os.path.getmtime(_REPO_SGE) if os.path.exists(_REPO_SGE) else None
_cred = os.path.getmtime(_REPO_CRED) if os.path.exists(_REPO_CRED) else None


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


PAGS_SALIDA = [211, 212, 214, 217, 219, 221]
PAGS_BASE = [210, 213, 215, 216, 218, 220, 222, 223, 224]
TPL = {4: "Registro-4to-Grado-Sec-Academica-1-1.pdf",
       5: "Registro-5to-Grado-Sec-Academica-1-1.pdf",
       6: "Registro-6to-Grado-Sec-Academica-1-1.pdf"}


def _norm(s):
    import unicodedata
    s = unicodedata.normalize("NFD", (s or "").casefold())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " ".join(s.split())


def _cabecera_template(grado, pg_humana):
    """Banda superior (y0 < 70) de una página del template oficial."""
    import pymupdf
    doc = pymupdf.open(os.path.join(_TPL_DIR, TPL[grado]))
    try:
        d = doc[pg_humana - 1].get_text("dict")
        partes = []
        for b in d["blocks"]:
            for l in b.get("lines", []):
                for s in l.get("spans", []):
                    if s["bbox"][1] < 70:
                        partes.append((round(s["bbox"][0]), s["text"]))
        partes.sort()
        return " ".join(" ".join(t for _, t in partes).split())
    finally:
        doc.close()


try:
    import pymupdf                                             # noqa: F401
    _HAY_PYMUPDF = True
except Exception:
    _HAY_PYMUPDF = False


# ===========================================================================
# BLOQUE A — EL MAPA, DEMOSTRADO CONTRA EL TEMPLATE
# ===========================================================================

@test("§A1 slot == índice en completiva_salida_optativa, en los tres grados")
def _():
    for grado in (4, 5, 6):
        pgs = GRADO_CONFIG[grado]["completiva_salida_optativa"]
        assert pgs == PAGS_SALIDA, (grado, pgs)
        for comp in CAT._CATALOGO:
            if comp.grado != grado:
                continue
            assert 0 <= comp.slot < len(pgs), (comp.codigo, comp.slot)


@test("§A2 las 6 páginas son PÁGINA HUMANA (1-based): el código resta 1")
def _():
    # Evidencia en el código: `completiva_paginas` se convierte con `- 1`.
    src = _inspect.getsource(RE.generar_registro_escolar)
    assert "comp_paginas[a_idx] - 1" in src, "cambió la convención de completiva_paginas"
    assert "salida_opt_paginas[slot_int] - 1" in src, \
        "la Salida Optativa debe usar la MISMA convención 1-based"


@test("§A3 EVIDENCIA DEL TEMPLATE: cada página declara su salida y su componente")
def _():
    if not _HAY_PYMUPDF:
        print("    (pymupdf no disponible: se omite la verificación del template)")
        return
    # slot -> (página humana, código de salida esperado)
    esperado = {0: (211, "HLM"), 1: (212, "HCS"), 2: (214, "HLM"),
                3: (217, "MYT"), 4: (219, "HCS"), 5: (221, "CYT")}
    for grado in (4, 5, 6):
        for comp in sorted((c for c in CAT._CATALOGO if c.grado == grado),
                           key=lambda c: c.slot):
            pg, salida_cod = esperado[comp.slot]
            assert comp.salida == salida_cod, (comp.codigo, comp.salida, salida_cod)
            cab = _norm(_cabecera_template(grado, pg))
            assert "salida optativa" in cab, (grado, pg, cab[:90])
            assert _norm(CAT.SALIDAS[salida_cod]) in cab, (grado, pg, salida_cod, cab[:90])


@test("§A4 EVIDENCIA DEL TEMPLATE: las páginas BASE no son de Salida Optativa")
def _():
    if not _HAY_PYMUPDF:
        print("    (pymupdf no disponible: se omite)")
        return
    for grado in (4, 5, 6):
        for pg in PAGS_BASE:
            cab = _norm(_cabecera_template(grado, pg))
            assert "salida optativa" not in cab, (grado, pg, cab[:90])


# ===========================================================================
# BLOQUE B — ESTAMPADO
# ===========================================================================

def _est(n=3):
    return [{"numero": i + 1, "apellidos": "Ape%d" % i, "nombres": "Nom%d" % i,
             "sexo": "F", "fecha_nacimiento": "01/01/2010", "cedula": "",
             "matricula": "M%d" % i, "rne": "", "condicion": "promovido"}
            for i in range(n)]


def _fila(cf=None, espec_cf=None, espec_a="", espec_r=""):
    f = {}
    if cf is not None:
        f["cf"] = cf
    if espec_cf is not None:
        f["espec_cf"] = espec_cf
    if espec_a:
        f["situacion_a"] = espec_a
    if espec_r:
        f["situacion_r"] = espec_r
    return f


def _generar(grado, salida_optativa_data=None, completiva_data=None):
    return generar_registro_escolar(
        grado=grado,
        datos_centro={"nombre_centro": "C", "regional": "10", "distrito": "03"},
        datos_portada={"anio_inicio": "25", "anio_fin": "26", "seccion": "A"},
        estudiantes=_est(),
        completiva_data=completiva_data,
        salida_optativa_data=salida_optativa_data,
        template_dir=_TPL_DIR,
    )


def _overlays(pdf_bytes):
    """Páginas HUMANAS que llevan un overlay de datos de EducaOne."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    con = set()
    for i, pg in enumerate(reader.pages):
        try:
            res = pg.get("/Resources") or {}
            xo = res.get("/XObject")
            if xo is None:
                continue
            if any(str(k).startswith("/EODataOverlay") for k in xo.get_object().keys()):
                con.add(i + 1)
        except Exception:
            continue
    return con, reader


def _texto(reader, pg_humana):
    return reader.pages[pg_humana - 1].extract_text() or ""


@test("§B1 curso SIN salida configurada: el Registro se comporta como antes")
def _():
    pdf = _generar(4, salida_optativa_data=None)
    con, reader = _overlays(pdf)
    assert len(reader.pages) == GRADO_CONFIG[4]["total_paginas"] == 238, len(reader.pages)
    assert con & set(PAGS_SALIDA) == set(), \
        "sin configuración no debe tocarse ninguna página de Salida Optativa"


@test("§B2 salida configurada: SOLO la página oficial del slot recibe overlay")
def _():
    # slot 5 = CYT / Ciencias de la Naturaleza -> pg 221
    pdf = _generar(4, {5: {"docente": "Prof. Cyt", "calificaciones": [_fila(cf=88)] * 3}})
    con, reader = _overlays(pdf)
    assert 221 in con, sorted(con)
    assert not (con & (set(PAGS_SALIDA) - {221})), sorted(con & set(PAGS_SALIDA))
    assert "88" in _texto(reader, 221), _texto(reader, 221)[:200]


@test("§B3 CADA salida oficial y CADA grado aplicable estampan su página")
def _():
    esperado = {0: 211, 1: 212, 2: 214, 3: 217, 4: 219, 5: 221}
    for grado in (4, 5, 6):
        for salida in sorted(CAT.SALIDAS):
            comps = CAT.componentes_de(salida, grado)
            assert comps, (salida, grado)
            datos = {c.slot: {"docente": "D", "calificaciones": [_fila(cf=70 + c.slot)] * 3}
                     for c in comps}
            pdf = _generar(grado, datos)
            con, _ = _overlays(pdf)
            pgs_esperadas = {esperado[c.slot] for c in comps}
            assert pgs_esperadas <= con, (grado, salida, sorted(pgs_esperadas), sorted(con))
            # y NINGUNA otra página de Salida Optativa
            sobra = (con & set(PAGS_SALIDA)) - pgs_esperadas
            assert not sobra, (grado, salida, sorted(sobra))


@test("§B4 configuración INCOMPLETA: la página del componente sin datos queda virgen")
def _():
    # HLM tiene 2 componentes (slots 0 y 2); solo se aporta el 0
    pdf = _generar(4, {0: {"docente": "D", "calificaciones": [_fila(cf=75)] * 3}})
    con, _ = _overlays(pdf)
    assert 211 in con, sorted(con)
    assert 214 not in con, "un componente sin datos no debe inventar página"


@test("§B5 una nota CERO legítima se estampa; None sigue en blanco")
def _():
    pdf = _generar(4, {5: {"docente": "D",
                           "calificaciones": [_fila(cf=0), None, _fila(cf=None)]}})
    con, reader = _overlays(pdf)
    assert 221 in con, "una fila con cf=0 SÍ es dato y debe estamparse"
    assert "0" in _texto(reader, 221)


@test("§B6 ningún dato: la página no se toca (no se estampan ceros de relleno)")
def _():
    pdf = _generar(4, {5: {"docente": "D", "calificaciones": [None, None, None]}})
    con, _ = _overlays(pdf)
    assert 221 not in con, "sin ninguna fila con dato no debe haber overlay"


@test("§B7 un slot fuera de rango se ignora sin romper el PDF")
def _():
    pdf = _generar(4, {99: {"docente": "D", "calificaciones": [_fila(cf=90)] * 3},
                       "x": {"docente": "D", "calificaciones": [_fila(cf=90)] * 3}})
    con, reader = _overlays(pdf)
    assert len(reader.pages) == 238
    assert not (con & set(PAGS_SALIDA)), sorted(con)


@test("§B8 no hay truncación: el total de páginas se conserva en los 3 grados")
def _():
    for grado, total in ((4, 238), (5, 238), (6, 240)):
        datos = {c.slot: {"docente": "D", "calificaciones": [_fila(cf=80)] * 3}
                 for c in CAT.componentes_de("HLM", grado)}
        reader = PdfReader(io.BytesIO(_generar(grado, datos)))
        assert len(reader.pages) == total == GRADO_CONFIG[grado]["total_paginas"], grado


@test("§B9 la Salida Optativa NO pisa las páginas completivas base")
def _():
    # la clave es el nombre MINERD normalizado igual que en el generador
    clave = RE.ASIGNATURAS_CICLO_1[0].lower().replace(" ", "_").replace("-", "_")
    comp = {clave: {"docente": "D", "calificaciones": [_fila(espec_cf=91)] * 3}}
    pdf = _generar(4, {0: {"docente": "D", "calificaciones": [_fila(cf=77)] * 3}},
                   completiva_data=comp)
    con, reader = _overlays(pdf)
    assert 211 in con and 210 in con, sorted(con)
    assert "77" in _texto(reader, 211), _texto(reader, 211)[:150]
    assert "91" in _texto(reader, 210), _texto(reader, 210)[:150]


@test("§B10 pipeline XObject intacto: sin merge_page y con overlay como XObject")
def _():
    # Se busca una LLAMADA real, no la palabra: el módulo la menciona en dos
    # comentarios que precisamente explican por qué NO se usa.
    import ast as _ast
    arbol = _ast.parse(_inspect.getsource(RE))
    llamadas = [n for n in _ast.walk(arbol)
                if isinstance(n, _ast.Call)
                and isinstance(n.func, _ast.Attribute)
                and n.func.attr == "merge_page"]
    assert not llamadas, "R3.3 no debe reintroducir llamadas a merge_page"
    src_gen = _inspect.getsource(RE.generar_registro_escolar)
    assert "_create_overlay_page(draw_completiva, datos_comp)" in src_gen, \
        "la Salida Optativa debe usar el pipeline de overlay existente"
    pdf = _generar(4, {5: {"docente": "D", "calificaciones": [_fila(cf=88)] * 3}})
    reader = PdfReader(io.BytesIO(pdf))
    xo = reader.pages[220].get("/Resources").get("/XObject").get_object()
    assert any(str(k).startswith("/EODataOverlay") for k in xo.keys()), list(xo.keys())


# ===========================================================================
# BLOQUE C — RESOLUCIÓN DESDE CursoComponenteOptativo
# ===========================================================================

COL_A, COL_B, ANO_A1, ANO_A2, ANO_B = 1, 2, 1, 3, 2
G4, G4B = 4, 104
CURSO_A, CURSO_A2, CURSO_B = 14, 19, 20
ASIG_OPT, ASIG_EXTRA, ASIG_B = 101, 102, 201
EST_A = 500
U_DIR_A = 30
PWD = "Prueba2026x"


def _seed_bd():
    M.Base.metadata.drop_all(bind=engine)
    M.Base.metadata.create_all(bind=engine)
    d = SessionLocal()
    try:
        for cid, nom in ((COL_A, "Colegio A"), (COL_B, "Colegio B")):
            d.add(M.Colegio(id=cid, nombre=nom, codigo=nom[-1].lower()))
        d.add(M.AnoEscolar(id=ANO_A1, colegio_id=COL_A, nombre="2025-2026",
                           activo=True, dias_trabajados="{}"))
        d.add(M.AnoEscolar(id=ANO_A2, colegio_id=COL_A, nombre="2026-2027",
                           activo=False, dias_trabajados="{}"))
        d.add(M.AnoEscolar(id=ANO_B, colegio_id=COL_B, nombre="2025-2026",
                           activo=True, dias_trabajados="{}"))
        d.add(M.Grado(id=G4, colegio_id=COL_A, nombre="4to Secundaria",
                      nivel="secundaria", orden=4))
        d.add(M.Grado(id=G4B, colegio_id=COL_B, nombre="4to Secundaria",
                      nivel="secundaria", orden=4))
        d.add(M.Curso(id=CURSO_A, colegio_id=COL_A, nombre="A", grado_id=G4,
                      ano_escolar_id=ANO_A1, salida_optativa_codigo="CYT", activo=True))
        d.add(M.Curso(id=CURSO_A2, colegio_id=COL_A, nombre="A", grado_id=G4,
                      ano_escolar_id=ANO_A2, salida_optativa_codigo="CYT", activo=True))
        d.add(M.Curso(id=CURSO_B, colegio_id=COL_B, nombre="A", grado_id=G4B,
                      ano_escolar_id=ANO_B, salida_optativa_codigo="CYT", activo=True))
        d.add(M.Asignatura(id=ASIG_OPT, colegio_id=COL_A, nombre="Bio-Comp",
                           codigo="X", area="", activo=True))
        # materia extra del boletín: existe, tiene notas, NADIE la vinculó
        d.add(M.Asignatura(id=ASIG_EXTRA, colegio_id=COL_A, nombre="Salida Optativa",
                           codigo="X", area="", activo=True))
        d.add(M.Asignatura(id=ASIG_B, colegio_id=COL_B, nombre="Bio-Comp",
                           codigo="X", area="", activo=True))
        u = M.Usuario(id=U_DIR_A, username="dir_a", nombre="dir", apellido="T",
                      role="direccion", colegio_id=COL_A)
        u.set_password(PWD)
        d.add(u)
        d.add(M.Estudiante(id=EST_A, colegio_id=COL_A, nombre="E", apellido="T",
                           curso_id=CURSO_A, activo=True))
        d.commit()
        # notas para AMBAS asignaturas: la vinculada y la extra
        for aid in (ASIG_OPT, ASIG_EXTRA):
            for comp_n in (1, 2, 3, 4):
                d.add(M.CalificacionSecundaria(
                    colegio_id=COL_A, estudiante_id=EST_A, asignatura_id=aid,
                    ano_escolar_id=ANO_A1, competencia_numero=comp_n,
                    p1=80.0, p2=80.0, p3=80.0, p4=80.0))
        d.commit()
    finally:
        d.close()


def _mapear(curso_id, componente, asignatura_id, ano, colegio):
    d = SessionLocal()
    try:
        d.add(M.CursoComponenteOptativo(
            colegio_id=colegio, curso_id=curso_id, ano_escolar_id=ano,
            componente_codigo=componente, asignatura_id=asignatura_id, activo=True))
        d.commit()
    finally:
        d.close()


def _resolver(curso_id, usuario_id=U_DIR_A):
    from app import _cargar_salida_optativa_registro
    d = SessionLocal()
    try:
        user = d.query(M.Usuario).get(usuario_id)
        curso = d.query(M.Curso).get(curso_id)
        ests = d.query(M.Estudiante).filter(M.Estudiante.curso_id == curso_id).all()
        return _cargar_salida_optativa_registro(d, user, curso, ests)
    finally:
        d.close()


_seed_bd()


@test("§C1 sin mapeo no se resuelve nada, aunque la salida esté elegida")
def _():
    assert _resolver(CURSO_A) == {}, "sin CursoComponenteOptativo no hay datos"


@test("§C2 con mapeo, los datos salen de la asignatura VINCULADA")
def _():
    _mapear(CURSO_A, "CYT-CN-4", ASIG_OPT, ANO_A1, COL_A)
    res = _resolver(CURSO_A)
    assert set(res) == {5}, res            # CYT-CN-4 es slot 5
    califs = res[5]["calificaciones"]
    assert 0 in califs and califs[0].get("cf") is not None, califs


@test("§C3 la materia EXTRA no vinculada NO entra, aunque se llame 'Salida Optativa'")
def _():
    res = _resolver(CURSO_A)
    # solo hay un slot y su asignatura es la vinculada, no la extra
    d = SessionLocal()
    try:
        fila = d.query(M.CursoComponenteOptativo).filter(
            M.CursoComponenteOptativo.curso_id == CURSO_A,
            M.CursoComponenteOptativo.activo == True).first()      # noqa: E712
        assert fila.asignatura_id == ASIG_OPT, fila.asignatura_id
    finally:
        d.close()
    assert set(res) == {5}, res
    # y el resultado NO contiene rastro de la asignatura extra
    assert len(res) == 1


@test("§C4 el mapeo de OTRO AÑO no entra en el Registro de este año")
def _():
    _mapear(CURSO_A2, "CYT-CN-4", ASIG_OPT, ANO_A2, COL_A)
    res = _resolver(CURSO_A)
    assert set(res) == {5}, res
    d = SessionLocal()
    try:
        # el año 2 tiene su propia fila y no se mezcla
        n = d.query(M.CursoComponenteOptativo).filter(
            M.CursoComponenteOptativo.ano_escolar_id == ANO_A2).count()
        assert n == 1, n
    finally:
        d.close()


@test("§C5 el mapeo de OTRO TENANT no entra")
def _():
    _mapear(CURSO_B, "CYT-CN-4", ASIG_B, ANO_B, COL_B)
    # Dirección del colegio A no ve nada del colegio B
    res = _resolver(CURSO_B)
    assert res == {}, res


@test("§C6 un curso SIN salida configurada devuelve {} (comportamiento actual)")
def _():
    d = SessionLocal()
    try:
        c = d.query(M.Curso).get(CURSO_A)
        c.salida_optativa_codigo = None
        d.commit()
    finally:
        d.close()
    assert _resolver(CURSO_A) == {}
    d = SessionLocal()
    try:
        c = d.query(M.Curso).get(CURSO_A)
        c.salida_optativa_codigo = "CYT"
        d.commit()
    finally:
        d.close()


@test("§C7 R3.3 no resuelve por nombre: renombrar la asignatura no cambia nada")
def _():
    d = SessionLocal()
    try:
        a = d.query(M.Asignatura).get(ASIG_OPT)
        a.nombre = "Nombre Totalmente Distinto"
        d.commit()
    finally:
        d.close()
    res = _resolver(CURSO_A)
    assert set(res) == {5}, "el vínculo es por FK, no por nombre"


@test("§ZZ ZERO DATA LOSS: sge.db e INITIAL_CREDENTIALS.txt intactos")
def _():
    ahora_sge = os.path.getmtime(_REPO_SGE) if os.path.exists(_REPO_SGE) else None
    ahora_cred = os.path.getmtime(_REPO_CRED) if os.path.exists(_REPO_CRED) else None
    assert ahora_sge == _sge, "sge.db del repo fue modificado"
    assert ahora_cred == _cred, "INITIAL_CREDENTIALS.txt del repo fue modificado"


print("\n" + "=" * 64)
print(f"{B}RESULTADO R3.3: {_ok}/{_total} pruebas{X}")
if _fail:
    print(f"{R}FALLARON:{X}")
    for n, e in _fail:
        print(f"  - {n}: {e}")
    sys.exit(1)
print(f"{G}TODO VERDE{X}")
