# -*- coding: utf-8 -*-
"""
EducaOne R2.1B — catálogo oficial versionado + modelo mínimo.

Tres bloques:

  A. CATÁLOGO (§11.1-10): los 54 bloques, unicidad de claves, textos no vacíos,
     que IL-7 de un contexto NO es el de otro, y que cada anomalía del documento
     oficial quedó resuelta SIN alterar el contenido lingüístico.

  B. MODELO (§11.11-18): `contenidos_claves` nullable, el campo legacy
     `contenido` intacto, la tabla de selección colgando del padre, unicidad,
     varios IL por período, el mismo IL en P1 y P3, y continuidad al cambiar de
     profesor.

  C. MIGRACIÓN (§11.19-20): arranca la app REAL contra una SQLite temporal con
     el esquema LEGACY y verifica que es aditiva, idempotente y que no borra ni
     convierte nada.

SEGURIDAD: SQLite temporal aislada. NUNCA toca sge.db ni INITIAL_CREDENTIALS.txt
(se verifica al final). No se conecta a producción.

Uso:
    cd backend
    python tools/test_indicadores_oficiales_r21b.py
"""
import os
import sys
import atexit
import hashlib
import io
import json
import re
import tempfile
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TMPDIR = tempfile.mkdtemp(prefix="eo_ind_oficiales_r21b_")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_TMPDIR, "i.db").replace("\\", "/")
os.environ.setdefault("ENVIRONMENT", "development")


@atexit.register
def _cleanup():
    try:
        import shutil
        shutil.rmtree(_TMPDIR, ignore_errors=True)
    except Exception:
        pass


from sqlalchemy import event, inspect as sa_inspect, text   # noqa: E402
from sqlalchemy.exc import IntegrityError                   # noqa: E402
from database import engine, SessionLocal                   # noqa: E402
import models as M                                          # noqa: E402
import catalogo_indicadores as CAT                          # noqa: E402

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
# BLOQUE C — MIGRACIÓN (primero: reconstruye el esquema legacy)
# ===========================================================================

COL, ANO, CURSO, ASIG, PROF, PROF2 = 1, 1, 1, 1, 1, 2
TEXTO_LEGACY = "TEXTO LIBRE R2 QUE NO SE PUEDE PERDER  \n  con espacios raros"

M.Base.metadata.create_all(bind=engine)

_dcol = SessionLocal()
try:
    _dcol.add(M.Colegio(id=COL, nombre="Colegio A", codigo="c1"))
    _dcol.commit()
finally:
    _dcol.close()

with engine.connect() as conn:
    conn.execute(text("DROP TABLE IF EXISTS indicador_logro_selecciones"))
    conn.execute(text("DROP TABLE IF EXISTS indicadores_logro"))
    conn.execute(text(
        "CREATE TABLE indicadores_logro ("
        "  id INTEGER NOT NULL PRIMARY KEY,"
        "  colegio_id INTEGER REFERENCES colegios(id),"
        "  profesor_id INTEGER NOT NULL REFERENCES usuarios(id),"
        "  asignatura_id INTEGER NOT NULL REFERENCES asignaturas(id),"
        "  curso_id INTEGER NOT NULL REFERENCES cursos(id),"
        "  ano_escolar_id INTEGER REFERENCES ano_escolar(id),"
        "  periodo INTEGER NOT NULL,"
        "  contenido TEXT,"
        "  fecha_creacion DATETIME,"
        "  fecha_actualizacion DATETIME"
        ")"
    ))
    conn.execute(text(
        "CREATE UNIQUE INDEX uq_indicador_logro_institucional ON indicadores_logro "
        "(colegio_id, ano_escolar_id, curso_id, asignatura_id, periodo)"))
    conn.execute(text(
        "INSERT INTO ano_escolar (id, colegio_id, nombre, activo, cerrado, "
        "periodo_activo, dias_trabajados) VALUES (:i, :c, '2025-2026', 1, 0, 1, '{}')"),
        {"i": ANO, "c": COL})
    conn.execute(text(
        "INSERT INTO grados (id, colegio_id, nombre, nivel) "
        "VALUES (1, :c, '4to Secundaria', 'secundaria')"), {"c": COL})
    conn.execute(text(
        "INSERT INTO cursos (id, colegio_id, nombre, grado_id, ano_escolar_id, activo) "
        "VALUES (:k, :c, 'A', 1, :y, 1)"), {"k": CURSO, "c": COL, "y": ANO})
    conn.execute(text(
        "INSERT INTO asignaturas (id, colegio_id, nombre, codigo, activo) "
        "VALUES (:a, :c, 'Lenguas Extranjeras - Francés', 'LEF', 1)"),
        {"a": ASIG, "c": COL})
    conn.execute(text(
        "INSERT INTO indicadores_logro (id, colegio_id, profesor_id, asignatura_id, "
        "curso_id, ano_escolar_id, periodo, contenido) "
        "VALUES (1, :c, :p, :a, :k, :y, 1, :t)"),
        {"c": COL, "p": PROF, "a": ASIG, "k": CURSO, "y": ANO, "t": TEXTO_LEGACY})
    conn.commit()

_cols_antes = {r[1] for r in engine.connect().execute(text("PRAGMA table_info(indicadores_logro)"))}
assert "contenidos_claves" not in _cols_antes


def _arrancar_app():
    from fastapi.testclient import TestClient
    import app as _app
    with TestClient(_app.app):
        pass


def _estado():
    with engine.connect() as conn:
        cols = {r[1] for r in conn.execute(text("PRAGMA table_info(indicadores_logro)"))}
        tablas = set(conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table'")).scalars())
        filas = list(conn.execute(text(
            "SELECT id, colegio_id, profesor_id, asignatura_id, curso_id, "
            "ano_escolar_id, periodo, contenido, contenidos_claves "
            "FROM indicadores_logro ORDER BY id")))
    return cols, tablas, filas


_arrancar_app()
_c1, _t1, _f1 = _estado()
_arrancar_app()
_c2, _t2, _f2 = _estado()


@test("§20 ningún dato legacy borrado ni convertido")
def _():
    assert len(_f1) == 1, f"se perdió la fila legacy: {_f1}"
    fila = _f1[0]
    assert fila[7] == TEXTO_LEGACY, f"`contenido` fue alterado: {fila[7]!r}"
    assert fila[8] is None, "la migración rellenó contenidos_claves (debía quedar NULL)"
    faltan = _cols_antes - _c1
    assert not faltan, f"columnas desaparecidas: {faltan}"


@test("§12 el campo legacy `contenido` sigue existiendo en el modelo y el esquema")
def _():
    assert "contenido" in _c1
    assert "contenido" in {c.name for c in sa_inspect(M.IndicadorLogro).columns}


@test("§11 `contenidos_claves` se agrega y es nullable")
def _():
    assert "contenidos_claves" in _c1, "la columna no se agregó"
    col = sa_inspect(M.IndicadorLogro).columns["contenidos_claves"]
    assert col.nullable, "contenidos_claves debería ser nullable"
    fisico = {c["name"]: c for c in sa_inspect(engine).get_columns("indicadores_logro")}
    assert fisico["contenidos_claves"]["nullable"] is True


@test("§19 migración idempotente: el segundo arranque no cambia nada")
def _():
    assert _c1 == _c2, _c1 ^ _c2
    assert _t1 == _t2, _t1 ^ _t2
    assert _f1 == _f2, "las filas cambiaron en el segundo arranque"
    assert "indicador_logro_selecciones" in _t1, "no se creó la tabla de selección"


@test("§X1 la migración NO insertó el catálogo en la base de datos")
def _():
    with engine.connect() as conn:
        n = conn.execute(text("SELECT COUNT(*) FROM indicador_logro_selecciones")).scalar()
    assert n == 0, f"hay {n} filas de selección tras migrar"
    tablas = {t.lower() for t in _t1}
    assert not any("catalog" in t for t in tablas), \
        f"se creó una tabla de catálogo en la BD: {sorted(t for t in tablas if 'catalog' in t)}"


# ===========================================================================
# BLOQUE A — CATÁLOGO
# ===========================================================================

_DOC = json.load(io.open(_JSON, encoding="utf-8"))
_E = _DOC["entradas"]
AREAS = ["LE", "LEI", "LEF", "MAT", "CS", "CN", "EA", "EF", "FIHR"]


def _sel(**kw):
    return [e for e in _E if all(e[k] == v for k, v in kw.items())]


@test("§1 el catálogo cubre 54/54 bloques (6 grados × 9 áreas), 7 bandas cada uno")
def _():
    bloques = {(e["grado_numero"], e["area_codigo"]) for e in _E}
    esperados = {(g, a) for g in range(1, 7) for a in AREAS}
    assert bloques == esperados, f"faltan/sobran: {esperados ^ bloques}"
    assert len(bloques) == 54, len(bloques)
    for g, a in sorted(esperados):
        bandas = {e["orden_ce"] for e in _sel(grado_numero=g, area_codigo=a)}
        assert bandas == {1, 2, 3, 4, 5, 6, 7}, f"{g}/{a}: bandas {sorted(bandas)}"


@test("§1b códigos CE por bloque: 7 distintos salvo el defecto conocido de 2do/EF")
def _():
    # El template imprime 7 competencias específicas por bloque. En 2do
    # Educación Física dos bandas comparten el rótulo CE-EF4 (falta CE-EF5):
    # es un defecto del documento oficial. NO se renumeró.
    irregulares = {}
    for g in range(1, 7):
        for a in AREAS:
            ces = {e["ce_codigo"] for e in _sel(grado_numero=g, area_codigo=a)}
            if len(ces) != 7:
                irregulares[(g, a)] = sorted(ces)
    assert set(irregulares) == {(2, "EF")}, irregulares
    assert irregulares[(2, "EF")] == ["CE-EF1", "CE-EF2", "CE-EF3", "CE-EF4",
                                      "CE-EF6", "CE-EF7"], irregulares
    # las dos bandas con el mismo código tienen TEXTOS distintos y sus propios IL
    ef4 = [e for e in _sel(grado_numero=2, area_codigo="EF", ce_codigo="CE-EF4")]
    textos = {e["ce_texto"] for e in ef4}
    assert len(textos) == 2, "deberían ser dos competencias distintas mal rotuladas"
    assert {e["orden_ce"] for e in ef4} == {4, 5}
    # y aun así ninguna clave colisiona
    assert len({e["catalogo_clave"] for e in ef4}) == len(ef4)


@test("§2 cero claves duplicadas")
def _():
    claves = [e["catalogo_clave"] for e in _E]
    assert len(claves) == len(set(claves)), "hay claves duplicadas"
    assert len(claves) == _DOC["total_entradas"] == 1134, len(claves)


@test("§3 cero indicadores con texto vacío")
def _():
    vacios = [e["catalogo_clave"] for e in _E if not (e["il_texto"] or "").strip()]
    assert not vacios, vacios[:5]


@test("§4 cero competencias específicas con texto vacío")
def _():
    vacios = [e["catalogo_clave"] for e in _E if not (e["ce_texto"] or "").strip()]
    assert not vacios, vacios[:5]


@test("§5 IL-7 de distintos grados/áreas son entradas DISTINTAS")
def _():
    a = _sel(grado_numero=1, area_codigo="LE", il_codigo="IL-7")[0]
    b = _sel(grado_numero=3, area_codigo="LE", il_codigo="IL-7")[0]
    c = _sel(grado_numero=1, area_codigo="MAT", il_codigo="IL-7")[0]
    assert a["catalogo_clave"] != b["catalogo_clave"] != c["catalogo_clave"]
    assert a["il_texto"] != b["il_texto"], "1ro y 3ro comparten texto: sospechoso"
    assert a["il_texto"] != c["il_texto"], "LE y MAT comparten texto: sospechoso"
    # y ninguna clave es solo el código
    assert all(e["catalogo_clave"].count("|") == 4 for e in _E)


@test("§6 6to Educación Física: 15 códigos distintos, tal como los imprime el template")
def _():
    ef = _sel(grado_numero=6, area_codigo="EF")
    codigos = {e["il_codigo"] for e in ef}
    assert len(codigos) == 15, f"{len(codigos)} códigos distintos"
    assert len(ef) == 21, f"{len(ef)} entradas"
    # el documento REINICIA la numeración en la 2ª página: no se renumeró ni se
    # descartó nada; la CE distingue las repeticiones.
    repetidos = {c for c in codigos if len([e for e in ef if e["il_codigo"] == c]) > 1}
    assert repetidos == {"IL-4", "IL-5", "IL-6", "IL-7", "IL-8", "IL-9"}, repetidos
    for c in repetidos:
        ces = {e["ce_codigo"] for e in ef if e["il_codigo"] == c}
        assert len(ces) == 2, (c, ces)
    # ningún grado/área más tiene códigos repetidos
    for g in range(1, 7):
        for a in AREAS:
            blo = _sel(grado_numero=g, area_codigo=a)
            if (g, a) == (6, "EF"):
                continue
            cods = [e["il_codigo"] for e in blo]
            assert len(cods) == len(set(cods)), f"{g}/{a} repite códigos"


@test("§7 anomalías de código normalizadas SIN alterar el texto (IL7-, IIL-16-, CE3-LEI-)")
def _():
    # 1ro Lengua imprimía 'IL7-' (sin guion) y 'IIL-16-' (doble I)
    il7 = _sel(grado_numero=1, area_codigo="LE", il_codigo="IL-7")[0]
    assert il7["il_texto"].startswith("Identifica problemas o conflictos"), il7["il_texto"][:60]
    assert not il7["il_texto"].startswith("-"), "quedó un guion pegado al texto"
    il16 = _sel(grado_numero=1, area_codigo="LE", il_codigo="IL-16")[0]
    assert il16["il_texto"].startswith("Caracteriza problemáticas"), il16["il_texto"][:60]
    assert "IIL" not in il16["il_texto"]
    # 1ro Inglés imprimía el código invertido 'CE3-LEI-'
    ce3 = _sel(grado_numero=1, area_codigo="LEI", ce_codigo="CE-LEI3")
    assert ce3, "no se recuperó CE-LEI3"
    assert ce3[0]["ce_texto"].startswith("Se comunica en inglés"), ce3[0]["ce_texto"][:60]
    # ningún texto arrastra su propio marcador
    for e in _E:
        assert not re.match(r"^\s*I{1,2}\s*L\s*-?\s*\d", e["il_texto"]), e["catalogo_clave"]
        assert not re.match(r"^\s*C\s*E\s*[-\d]", e["ce_texto"]), e["catalogo_clave"]


@test("§8 la CE multilínea de 2do Lengua se reconstruyó completa")
def _():
    ces = _sel(grado_numero=2, area_codigo="LE")
    codigos = sorted({e["ce_codigo"] for e in ces})
    assert codigos == [f"CE-LE{i}" for i in range(1, 8)], codigos
    ce1 = [e for e in ces if e["ce_codigo"] == "CE-LE1"][0]["ce_texto"]
    assert ce1.startswith("Comunica sus ideas y experiencias"), ce1[:70]
    assert len(ce1) > 100 and ce1.rstrip().endswith("."), repr(ce1[-60:])


@test("§9 unicode y ligaduras: cero ﬁ/ﬂ, acentos en forma NFC")
def _():
    for e in _E:
        for campo in ("il_texto", "ce_texto"):
            t = e[campo]
            assert not any(l in t for l in "ﬀﬁﬂﬃﬄﬅﬆ"), (e["catalogo_clave"], campo)
            assert t == unicodedata.normalize("NFC", t), (e["catalogo_clave"], campo)
    # el guion compuesto partido por salto de línea quedó reunido
    ce5 = _sel(grado_numero=1, area_codigo="LE", ce_codigo="CE-LE5")[0]["ce_texto"]
    assert "expositivo-explicativa" in ce5, ce5[-80:]
    assert "expositivo- explicativa" not in ce5


@test("§10 cada entrada conserva su procedencia (fuente + página)")
def _():
    for e in _E:
        assert e["fuente"].endswith(".pdf"), e["catalogo_clave"]
        assert isinstance(e["pagina_fuente"], int) and e["pagina_fuente"] > 0, e
        assert e["version_curricular"] == "SEC-2023"
        assert e["nivel"] == "secundaria"
        assert e["competencia_fundamental_codigo"], e["catalogo_clave"]
    assert len(_DOC["fuentes"]) == 6, _DOC["fuentes"]
    assert len(_DOC["competencias_fundamentales"]) == 7


@test("§H1 2do EF: dos bandas DISTINTAS aunque ambas muestren CE-EF4")
def _():
    ef = _sel(grado_numero=2, area_codigo="EF")
    ef4 = [e for e in ef if e["ce_codigo"] == "CE-EF4"]
    bandas = {e["orden_ce"] for e in ef4}
    assert bandas == {4, 5}, bandas
    textos = {e["ce_texto"] for e in ef4}
    assert len(textos) == 2, "las dos bandas deberían tener textos distintos"
    b4 = next(e["ce_texto"] for e in ef4 if e["orden_ce"] == 4)
    b5 = next(e["ce_texto"] for e in ef4 if e["orden_ce"] == 5)
    assert b4.startswith("Muestra dominio"), b4[:60]
    assert b5.startswith("Descubre mediante análisis"), b5[:60]
    # el código oficial NO se tocó para ganar unicidad
    assert all(e["ce_codigo"] == "CE-EF4" for e in ef4)
    assert "CE-EF5" not in {e["ce_codigo"] for e in ef}


@test("§H2 la agrupación de UI NO fusiona esas dos bandas")
def _():
    grupos = CAT.agrupar(grado=2, area="EF")
    ces = [ce for g in grupos for ce in g["competencias_especificas"]]
    assert len(ces) == 7, f"{len(ces)} bandas tras agrupar (deberían ser 7)"
    ef4 = [ce for ce in ces if ce["ce_codigo"] == "CE-EF4"]
    assert len(ef4) == 2, "se fusionaron las bandas CE-EF4"
    assert {ce["orden_ce"] for ce in ef4} == {4, 5}
    assert all(len(ce["indicadores"]) == 3 for ce in ef4), \
        [len(ce["indicadores"]) for ce in ef4]
    # ninguna banda del catálogo se pierde en ningún bloque
    for g in range(1, 7):
        for a in AREAS:
            n = sum(len(x["competencias_especificas"]) for x in CAT.agrupar(grado=g, area=a))
            assert n == 7, f"{g}/{a}: {n} bandas"


@test("§H3 6to EF conserva la numeración IL exactamente como la fuente")
def _():
    ef = _sel(grado_numero=6, area_codigo="EF")
    por_banda = {}
    for e in ef:
        por_banda.setdefault(e["orden_ce"], []).append(e["il_codigo"])
    # Lo que imprime el documento: la numeración avanza hasta IL-15 en la banda
    # 5 y REINICIA en la banda 6 (primera de la 2ª página de referencia).
    esperado = {
        1: ["IL-1", "IL-2", "IL-3"], 2: ["IL-4", "IL-5", "IL-6"],
        3: ["IL-7", "IL-8", "IL-9"], 4: ["IL-10", "IL-11", "IL-12"],
        5: ["IL-13", "IL-14", "IL-15"],
        6: ["IL-4", "IL-5", "IL-6"], 7: ["IL-7", "IL-8", "IL-9"],
    }
    assert por_banda == esperado, por_banda
    # 15 códigos distintos; nada fue renumerado a IL-16..IL-21 para forzar unicidad
    assert len({x["il_codigo"] for x in ef}) == 15
    assert max(int(x["il_codigo"].split("-")[1]) for x in ef) == 15
    # El reinicio NO coincide con el salto de página: el bloque cambia de hoja
    # entre las bandas 4 y 5, pero la numeración sigue avanzando hasta IL-15 en
    # la banda 5 y solo reinicia en la banda 6, ya dentro de la misma página.
    pgs = {o: {x["pagina_fuente"] for x in ef if x["orden_ce"] == o} for o in por_banda}
    assert pgs == {1: {153}, 2: {153}, 3: {153}, 4: {153},
                   5: {154}, 6: {154}, 7: {154}}, pgs


@test("§H4 un IL repetido NO provoca colisión de clave técnica")
def _():
    for g, a in ((6, "EF"), (2, "EF")):
        bloque = _sel(grado_numero=g, area_codigo=a)
        claves = [e["catalogo_clave"] for e in bloque]
        assert len(claves) == len(set(claves)), f"{g}/{a} colisiona"
    # y globalmente
    todas = [e["catalogo_clave"] for e in _E]
    assert len(todas) == len(set(todas)) == 1134, (len(todas), len(set(todas)))
    # la clave usa POSICIÓN, no códigos académicos
    for e in _E:
        esperada = "SEC-2023|%d|%s|CE%02d|IL%02d" % (
            e["grado_numero"], e["area_codigo"], e["orden_ce"], e["orden_il"])
        assert e["catalogo_clave"] == esperada, e["catalogo_clave"]


@test("§H5 buscar por il_codigo puede devolver VARIOS resultados")
def _():
    varios = CAT.buscar_por_codigo("IL-7", grado=6, area="EF")
    assert len(varios) == 2, len(varios)
    assert {x["orden_ce"] for x in varios} == {3, 7}
    assert len({x["catalogo_clave"] for x in varios}) == 2
    assert varios[0]["il_texto"] != varios[1]["il_texto"]
    # donde no hay reinicio, devuelve uno solo
    assert len(CAT.buscar_por_codigo("IL-7", grado=1, area="LE")) == 1
    # y sin filtros abarca todos los grados/áreas
    assert len(CAT.buscar_por_codigo("IL-7")) >= 54


@test("§H6 resolver(catalogo_clave) devuelve EXACTAMENTE una entrada")
def _():
    a = CAT.resolver("SEC-2023|6|EF|CE03|IL01")
    b = CAT.resolver("SEC-2023|6|EF|CE07|IL01")
    assert a["il_codigo"] == b["il_codigo"] == "IL-7", (a["il_codigo"], b["il_codigo"])
    assert a["ce_codigo"] == "CE-EF3" and b["ce_codigo"] == "CE-EF7"
    assert a["il_texto"] != b["il_texto"]
    for e in _E:
        r = CAT.resolver(e["catalogo_clave"])
        assert r["catalogo_clave"] == e["catalogo_clave"]


@test("§H7 ningún código oficial fue alterado para ganar unicidad")
def _():
    # Todos los códigos siguen el formato que imprime el documento y, dentro de
    # cada bloque, los IL arrancan en IL-1 y son consecutivos por banda.
    for e in _E:
        assert re.fullmatch(r"IL-\d{1,3}", e["il_codigo"]), e["il_codigo"]
        assert re.fullmatch(r"CE-[A-ZÑ]{2,5}\d{1,2}", e["ce_codigo"]), e["ce_codigo"]
        assert e["ce_codigo"].startswith(f"CE-{e['area_codigo']}"), e
    # la identidad técnica jamás aparece en un campo de display
    for e in _E:
        for campo in ("il_codigo", "ce_codigo", "il_texto", "ce_texto"):
            assert "CE%02d" % e["orden_ce"] not in e[campo], (campo, e["catalogo_clave"])


@test("§H8 matriz exacta por grado y área: la suma es 1 134")
def _():
    total = 0
    filas = []
    for g in range(1, 7):
        fila = []
        for a in AREAS:
            n = len(_sel(grado_numero=g, area_codigo=a))
            fila.append(n)
            total += n
        filas.append((g, fila, sum(fila)))
    for g, fila, sub in filas:
        print("    grado %d: %s = %d" % (g, " ".join("%s=%d" % (a, n)
                                                     for a, n in zip(AREAS, fila)), sub))
    print(f"    TOTAL = {total}")
    assert total == 1134 == len(_E) == _DOC["total_entradas"], total


@test("§X2 el JSON del repo es exactamente el que produce el extractor")
def _():
    # Se normalizan los finales de línea antes de hashear para que el valor sea
    # el mismo en Linux y en Windows aunque git convierta CRLF al hacer
    # checkout. (.gitattributes además fija eol=lf para este archivo.)
    crudo = io.open(_JSON, "rb").read().replace(b"\r\n", b"\n")
    sha = hashlib.sha256(crudo).hexdigest()
    print(f"    SHA-256 (LF) = {sha}")
    assert sha == "566cc4d60ec1d571c5162b177879dc34117f6907e88440e6012895cba02138e7", sha


@test("§X3 servicio de catálogo: listar, agrupar, buscar y resolver")
def _():
    assert CAT.versiones_disponibles() == ["SEC-2023"]
    assert len(CAT.listar_por(grado=4, area="LEF")) == 21
    grupos = CAT.agrupar(grado=4, area="LEF")
    assert len(grupos) == 7, len(grupos)
    assert sum(len(ce["indicadores"]) for g in grupos for ce in g["competencias_especificas"]) == 21
    # orden oficial preservado
    ordenes = [ce["orden_ce"] for g in grupos for ce in g["competencias_especificas"]]
    assert ordenes == sorted(ordenes), ordenes
    assert len(CAT.buscar("IL-19", grado=4, area="LEF")) == 1
    assert CAT.buscar("ARGUMENTATIVAS", grado=1), "la búsqueda debe ignorar mayúsculas/acentos"
    e = CAT.resolver("SEC-2023|1|LE|CE03|IL01")
    assert e["il_codigo"] == "IL-7" and e["grado_numero"] == 1


@test("§X4 una clave desconocida es un ERROR explícito, nunca un fallback")
def _():
    for mala in ("SEC-2023|1|LE|CE03|IL99", "IL-7", "", "SEC-2099|1|LE|CE01|IL01"):
        try:
            CAT.resolver(mala)
            raise AssertionError(f"resolver aceptó {mala!r}")
        except CAT.CatalogoError:
            pass
    assert not CAT.existe("SEC-2023|9|ZZ|CE01|IL01")


# ===========================================================================
# BLOQUE B — MODELO
# ===========================================================================

CLAVE_A = "SEC-2023|4|LEF|CE01|IL01"
CLAVE_B = "SEC-2023|4|LEF|CE01|IL02"
CLAVE_C = "SEC-2023|4|LEF|CE03|IL01"
CONTENIDOS = ("Personal pronouns\n"
              "Possessive pronouns\n"
              "  Possessive   adjectives  \n"
              "\n"
              "Sentences using possessive adjectives")


def _padre(db, periodo, profesor_id=PROF):
    il = M.IndicadorLogro(colegio_id=COL, profesor_id=profesor_id, asignatura_id=ASIG,
                          curso_id=CURSO, ano_escolar_id=ANO, periodo=periodo)
    db.add(il)
    db.commit()
    return il


@test("§13 la selección cuelga del padre y hereda de él tenant y año")
def _():
    cols = {c.name for c in sa_inspect(M.IndicadorLogroSeleccion).columns}
    assert cols == {"id", "indicador_logro_id", "catalogo_clave", "fecha_creacion"}, cols
    for prohibida in ("colegio_id", "ano_escolar_id", "curso_id", "asignatura_id", "periodo"):
        assert prohibida not in cols, f"{prohibida} no debe duplicarse en la selección"
    fk = list(sa_inspect(M.IndicadorLogroSeleccion).columns["indicador_logro_id"].foreign_keys)
    assert fk and fk[0].target_fullname == "indicadores_logro.id", fk
    assert not sa_inspect(M.IndicadorLogroSeleccion).columns["indicador_logro_id"].nullable
    assert not sa_inspect(M.IndicadorLogroSeleccion).columns["catalogo_clave"].nullable
    # el texto oficial NO se copia en la selección
    assert "il_texto" not in cols and "ce_texto" not in cols


@test("§15 varios IL en el mismo período, y los contenidos claves en orden")
def _():
    db = SessionLocal()
    try:
        il = _padre(db, 2)
        for clave in (CLAVE_A, CLAVE_B, CLAVE_C):
            db.add(M.IndicadorLogroSeleccion(indicador_logro_id=il.id, catalogo_clave=clave))
        il.contenidos_claves = CONTENIDOS
        db.commit()

        il = db.query(M.IndicadorLogro).get(il.id)
        assert len(il.selecciones) == 3, len(il.selecciones)
        d = [s.to_dict() for s in il.selecciones]
        assert [x["il_codigo"] for x in d] == ["IL-1", "IL-2", "IL-7"], d
        assert all("error_catalogo" not in x for x in d)
        assert d[0]["ce_codigo"] == "CE-LEF1" and d[2]["ce_codigo"] == "CE-LEF3"
        assert d[0]["il_texto"] == CAT.resolver(CLAVE_A)["il_texto"]

        # Contenidos Claves: orden exacto, líneas en blanco fuera, espacios internos intactos
        lineas = il.lineas_contenidos_claves()
        assert lineas == ["Personal pronouns", "Possessive pronouns",
                          "  Possessive   adjectives  ",
                          "Sentences using possessive adjectives"], lineas
        assert il.contenidos_claves == CONTENIDOS, "se alteró el texto guardado"
    finally:
        db.close()


@test("§14/§16 el mismo IL no se puede marcar dos veces en el mismo período")
def _():
    db = SessionLocal()
    try:
        il = db.query(M.IndicadorLogro).filter_by(periodo=2).first()
        antes = db.query(M.IndicadorLogroSeleccion).count()
        db.add(M.IndicadorLogroSeleccion(indicador_logro_id=il.id, catalogo_clave=CLAVE_A))
        try:
            db.commit()
            raise AssertionError("se aceptó un IL duplicado en el mismo período")
        except IntegrityError:
            db.rollback()
        assert db.query(M.IndicadorLogroSeleccion).count() == antes
    finally:
        db.close()


@test("§17 el mismo IL SÍ puede usarse en P1 y P3 (padres distintos)")
def _():
    db = SessionLocal()
    try:
        p1 = _padre(db, 1) if not db.query(M.IndicadorLogro).filter_by(periodo=1).first() \
            else db.query(M.IndicadorLogro).filter_by(periodo=1).first()
        p3 = _padre(db, 3)
        db.add(M.IndicadorLogroSeleccion(indicador_logro_id=p1.id, catalogo_clave=CLAVE_A))
        db.add(M.IndicadorLogroSeleccion(indicador_logro_id=p3.id, catalogo_clave=CLAVE_A))
        db.commit()
        n = db.query(M.IndicadorLogroSeleccion).filter_by(catalogo_clave=CLAVE_A).count()
        assert n == 3, f"{n} selecciones de {CLAVE_A} (P1, P2 y P3)"
        assert p1.id != p3.id
    finally:
        db.close()


@test("§18 cambiar de profesor NO elimina las selecciones (continuidad institucional)")
def _():
    db = SessionLocal()
    try:
        il = db.query(M.IndicadorLogro).filter_by(periodo=2).first()
        antes = sorted(s.catalogo_clave for s in il.selecciones)
        assert antes, "el fixture debería tener selecciones"
        il.profesor_id = PROF2          # el docente entrante continúa el registro
        db.commit()
        il = db.query(M.IndicadorLogro).get(il.id)
        assert il.profesor_id == PROF2
        assert sorted(s.catalogo_clave for s in il.selecciones) == antes
        assert il.contenidos_claves == CONTENIDOS, "se perdieron los contenidos claves"
    finally:
        db.close()


@test("§X5 una selección con clave inválida se REPORTA, no se inventa texto")
def _():
    db = SessionLocal()
    try:
        il = _padre(db, 4)
        db.add(M.IndicadorLogroSeleccion(indicador_logro_id=il.id,
                                         catalogo_clave="SEC-2023|4|LEF|CE01|IL99"))
        db.commit()
        d = db.query(M.IndicadorLogro).get(il.id).selecciones[0].to_dict()
        assert "error_catalogo" in d, d
        assert "il_texto" not in d, "no debe fabricarse un texto"
    finally:
        db.close()


@test("§X6 ZERO DATA LOSS: sge.db, credenciales y el JSON del catálogo intactos")
def _():
    a = os.path.getmtime(_REPO_SGE) if os.path.exists(_REPO_SGE) else None
    b = os.path.getmtime(_REPO_CRED) if os.path.exists(_REPO_CRED) else None
    assert a == _sge_mtime, "sge.db fue modificado"
    assert b == _cred_mtime, "INITIAL_CREDENTIALS.txt fue modificado"
    assert os.path.getmtime(_JSON) == _json_mtime, "la suite modificó el catálogo"
    assert _TMPDIR.replace("\\", "/") in str(engine.url).replace("\\", "/")


print(f"\n{B}{'=' * 64}{X}")
print(f"{B}RESULTADO R2.1B: {_ok}/{_total} pruebas{X}")
if _fail:
    print(f"{R}FALLARON:{X}")
    for n, e in _fail:
        print(f"  - {n}: {e}")
    sys.exit(1)
print(f"{G}TODO VERDE{X}")
