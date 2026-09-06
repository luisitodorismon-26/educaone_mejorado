"""
EducaOne — v2.19.9: Registro Escolar de Secundaria con overlays de datos como
Form XObject (sin pypdf.Page.merge_page()).

Verifica que el cambio de arquitectura NO altera el documento:
  A  el PDF se genera sin error
  B  mismo número de páginas que el template
  C  MediaBox / CropBox / Rotate conservados página a página
  D  hay texto extraíble (el overlay de datos se ve)
  E  datos de estudiantes presentes
  F  asistencia presente
  G  calificaciones / competencias presentes
  H  promoción presente
  I  caracteres á é í ó ú ñ Ñ no se pierden
  J  una página con datos lleva un Form XObject /EODataOverlayN
  K  nombre_xobject_libre() evita colisiones (/EODataOverlay1 ocupado -> /EODataOverlay2)
  L  las páginas SIN overlay no reciben ningún /EODataOverlay
  M  el sello BORRADOR queda DESPUÉS del overlay de datos (TEMPLATE -> DATOS -> BORRADOR)
  N  el registro OFICIAL (sin marca) también funciona y no lleva /EOBorrador
  O  los seis grados 1–6 generan sin error

Sin dependencias nuevas: solo pypdf (ya en requirements) + stdlib.

Uso:
    cd backend
    python tools/test_registro_xobject_v2199.py
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pypdf import PdfReader
from pypdf.generic import ArrayObject, DictionaryObject, NameObject

from registro_escolar import (
    generar_registro_desde_sistema, TEMPLATE_DIR, TEMPLATE_FILES, GRADO_CONFIG,
    ASIGNATURAS_CICLO_1, ASIGNATURAS_CICLO_2,
)
from registro_borrador import nombre_xobject_libre

G, R, B, C, X = "\033[92m", "\033[91m", "\033[1m", "\033[96m", "\033[0m"
fallos, pasados, total = [], 0, 0


def test(nombre):
    def deco(fn):
        global total, pasados
        total += 1
        print(f"\n{C}▶ {nombre}{X}")
        try:
            fn(); pasados += 1; print(f"  {G}✓ PASÓ{X}")
        except Exception as e:
            import traceback
            fallos.append((nombre, str(e)))
            print(f"  {R}✗ FALLÓ: {e}{X}")
            traceback.print_exc()
        return fn
    return deco


# ── datos sintéticos (sin DB) ────────────────────────────────────────────────
from datetime import date

# Texto con TODOS los caracteres que exige la prueba I. Va en la RESIDENCIA,
# que es un campo que la hoja 'datos del estudiante' sí imprime literalmente.
TXT_ACENTOS = "Calle áéíóú ñ Ñ"
CEDULA_0 = "402-1000000-0"
DOCENTE = "PROFESOR ASIGNATURA XYZ"
MES_MARCADOR = "septiembre"

# ReportLab (Helvetica / WinAnsi) escribe los acentos como escape octal dentro
# del string PDF: á=\341 é=\351 í=\355 ó=\363 ú=\372 ñ=\361 Ñ=\321
_OCTAL_ACENTOS = {
    "á": (0xE1, b"\\341"), "é": (0xE9, b"\\351"), "í": (0xED, b"\\355"),
    "ó": (0xF3, b"\\363"), "ú": (0xFA, b"\\372"), "ñ": (0xF1, b"\\361"),
    "Ñ": (0xD1, b"\\321"),
}


def _students(n):
    out = []
    for i in range(n):
        out.append({
            "no_lista": i + 1,
            "nombre": f"ALUMNO PRUEBA {i:02d} APELLIDO",
            "sexo": "F" if i % 2 == 0 else "M",
            "fecha_nacimiento": date(2010 + i % 4, (i % 12) + 1, (i % 27) + 1),
            "cedula": f"402-{1000000+i:07d}-{i%10}", "matricula": f"M{i:04d}",
            "direccion": TXT_ACENTOS if i == 0 else f"Calle {i}",
            "condicion_entrada": "nuevo", "activo": True,
        })
    return out


def _asig_data(studs, grado, solo_n=None):
    asigs = ASIGNATURAS_CICLO_2 if grado >= 4 else ASIGNATURAS_CICLO_1
    if solo_n is not None:
        asigs = asigs[:solo_n]
    meses = ["septiembre", "octubre", "noviembre", "diciembre", "enero",
             "febrero", "marzo", "abril", "mayo", "junio"]
    data = {}
    for a in asigs:
        matriz = []
        for m in meses:
            filas = []
            for idx, e in enumerate(studs):
                vals = [("P", "A", "T", "E", "P")[(idx + d) % 5] for d in range(20)]
                filas.append({"no": idx + 1, "estudiante_id": idx, "nombre": e["nombre"],
                              "valores": vals, "presentes": vals.count("P"),
                              "ausentes": vals.count("A"), "porcentaje": 75.0})
            matriz.append({"mes": m, "mes_num": 9, "dias": list(range(1, 21)),
                           "total_dias": 20, "filas": filas, "fuente_dias": "horario"})
        cal = {}
        for idx in range(len(studs)):
            cal[idx] = {
                "competencias": {k: {"p1": 90, "p2": 85, "p3": 88, "p4": 92} for k in (1, 2, 3, 4)},
                "promedios_competencia": {1: 89, 2: 82, 3: 77, 4: 87},
                "rp1": None, "rp2": None, "rp3": None, "rp4": None,
                "pc1": 84, "pc2": 83, "pc3": 82, "pc4": 85, "cf": 84,
            }
        data[a] = {"docente": DOCENTE, "asistencias": {},
                   "asistencia_matriz": matriz, "calificaciones": cal}
    return data


CI = {"nombre": "CENTRO EDUCATIVO PRUEBA", "direccion": "Av. X #1", "email": "c@e.do",
      "telefono": "809", "director": "DIRECTOR PRUEBA", "codigo_centro": "00000",
      "regional": "10", "distrito": "03", "sector": "publico", "zona": "urbana",
      "coordinador": "TITULAR PRUEBA"}


def gen(grado, marca, nstud=5, solo_n=None):
    st = _students(nstud)
    ad = _asig_data(st, grado, solo_n=solo_n)
    cu = {"grado": str(grado), "seccion": "A", "tanda": "Matutina"}
    return generar_registro_desde_sistema(CI, cu, "2024-2025", st, ad, grado, marca_borrador=marca)


def _xobject_names(page):
    res = page.get("/Resources")
    if res is None:
        return set()
    xo = res.get_object().get("/XObject")
    if xo is None:
        return set()
    return {str(k) for k in xo.get_object().keys()}


def _contents_bytes(page):
    cont = page.get("/Contents")
    if cont is None:
        return b""
    obj = cont.get_object()
    if isinstance(obj, ArrayObject):
        return b"\n".join(r.get_object().get_data() for r in obj)
    return obj.get_data()


# ── PDFs de trabajo (grado 1, 5 estudiantes) ────────────────────────────────
PDF_BRDR = gen(1, True)
PDF_OFIC = gen(1, False)
R_BRDR = PdfReader(io.BytesIO(PDF_BRDR))
R_OFIC = PdfReader(io.BytesIO(PDF_OFIC))
TPL1 = PdfReader(os.path.join(TEMPLATE_DIR, TEMPLATE_FILES[1]))


@test("A — el PDF se genera sin error y es un PDF válido")
def _():
    assert isinstance(PDF_BRDR, (bytes, bytearray)) and PDF_BRDR[:5] == b"%PDF-", "cabecera PDF"
    assert b"%%EOF" in PDF_BRDR[-1024:], "sin %%EOF"
    assert len(R_BRDR.pages) > 0


@test("B — mismo número de páginas que el template (borrador y oficial)")
def _():
    assert len(R_BRDR.pages) == len(TPL1.pages) == GRADO_CONFIG[1]["total_paginas"], \
        f"{len(R_BRDR.pages)} vs {len(TPL1.pages)}"
    assert len(R_OFIC.pages) == len(TPL1.pages)


@test("C — MediaBox / CropBox / Rotate conservados página a página")
def _():
    for i, (pt, po) in enumerate(zip(TPL1.pages, R_BRDR.pages)):
        mb_t = [round(float(x), 2) for x in (pt.mediabox.left, pt.mediabox.bottom, pt.mediabox.right, pt.mediabox.top)]
        mb_o = [round(float(x), 2) for x in (po.mediabox.left, po.mediabox.bottom, po.mediabox.right, po.mediabox.top)]
        cb_t = [round(float(x), 2) for x in (pt.cropbox.left, pt.cropbox.bottom, pt.cropbox.right, pt.cropbox.top)]
        cb_o = [round(float(x), 2) for x in (po.cropbox.left, po.cropbox.bottom, po.cropbox.right, po.cropbox.top)]
        assert mb_t == mb_o, f"pág {i+1} MediaBox {mb_t} -> {mb_o}"
        assert cb_t == cb_o, f"pág {i+1} CropBox {cb_t} -> {cb_o}"
        assert int(pt.get("/Rotate", 0) or 0) == int(po.get("/Rotate", 0) or 0), f"pág {i+1} Rotate"


@test("D — hay texto extraíble (el overlay de datos se ve)")
def _():
    txt = "".join((p.extract_text() or "") for p in R_BRDR.pages)
    assert len(txt) > 2000, f"texto extraído muy corto: {len(txt)}"
    assert MES_MARCADOR in txt, f"no aparece {MES_MARCADOR!r} (asistencia)"


def _overlay_stream(page):
    xo = page.get("/Resources").get_object().get("/XObject").get_object()
    nom = next(k for k in xo.keys() if str(k).startswith("/EODataOverlay"))
    return xo[nom].get_object().get_data()


@test("E — datos de estudiantes presentes")
def _():
    # La hoja 'datos del estudiante' imprime cédula, nacimiento y residencia
    # (el nombre NO: la MINERD identifica por fila — ver comentario en el código).
    stream = _overlay_stream(R_BRDR.pages[GRADO_CONFIG[1]["datos_estudiantes"] - 1])
    assert CEDULA_0.encode("latin-1") in stream, "no aparece la cédula del estudiante en el overlay"
    assert b"Calle" in stream, "no aparece la residencia del estudiante en el overlay"


@test("F — asistencia presente (mes marcador en una hoja de asistencia)")
def _():
    ini = GRADO_CONFIG[1]["asistencia_inicio"] - 1
    encontrada = False
    for i in range(ini, ini + GRADO_CONFIG[1]["asistencia_pgs_por_asignatura"] * 3):
        xo = R_BRDR.pages[i].get("/Resources").get_object().get("/XObject")
        if not xo:
            continue
        for k in xo.get_object().keys():
            if str(k).startswith("/EODataOverlay"):
                if b"septiembre" in xo.get_object()[k].get_object().get_data() or \
                   b"octubre" in xo.get_object()[k].get_object().get_data():
                    encontrada = True
    assert encontrada, "ninguna hoja de asistencia lleva el overlay con nombre de mes"


@test("G — calificaciones / competencias presentes")
def _():
    ini = GRADO_CONFIG[1]["calificaciones_inicio"] - 1
    con_overlay = [i + 1 for i in range(ini, ini + GRADO_CONFIG[1]["calificaciones_pgs_por_asignatura"] * 3)
                   if any(str(k).startswith("/EODataOverlay") for k in _xobject_names(R_BRDR.pages[i]))]
    assert con_overlay, "ninguna página de calificaciones lleva overlay de datos"


@test("H — promoción presente")
def _():
    ini = GRADO_CONFIG[1]["promocion_inicio"] - 1
    con_overlay = [i + 1 for i in range(ini, ini + GRADO_CONFIG[1]["promocion_paginas"])
                   if any(str(k).startswith("/EODataOverlay") for k in _xobject_names(R_BRDR.pages[i]))]
    assert con_overlay, "la hoja de promoción no lleva overlay de datos"


@test("I — caracteres á é í ó ú ñ Ñ no se pierden")
def _():
    # TXT_ACENTOS se dibuja en la residencia (hoja datos del estudiante).
    stream = _overlay_stream(R_BRDR.pages[GRADO_CONFIG[1]["datos_estudiantes"] - 1])
    faltan = []
    for ch in "áéíóúñÑ":
        raw_byte, octal = _OCTAL_ACENTOS[ch]
        if bytes([raw_byte]) not in stream and octal not in stream:
            faltan.append(ch)
    assert not faltan, f"caracteres perdidos en el overlay: {faltan}"


@test("J — una página con datos lleva un Form XObject /EODataOverlayN")
def _():
    pg = R_BRDR.pages[GRADO_CONFIG[1]["datos_estudiantes"] - 1]
    names = _xobject_names(pg)
    assert any(n.startswith("/EODataOverlay") for n in names), f"XObjects en la página: {sorted(names)}"


@test("K — nombre_xobject_libre() evita colisiones")
def _():
    p0 = DictionaryObject()
    assert nombre_xobject_libre(p0) == "/EODataOverlay1"
    p1 = DictionaryObject()
    res = DictionaryObject(); xo = DictionaryObject()
    xo[NameObject("/EODataOverlay1")] = NameObject("/x")
    res[NameObject("/XObject")] = xo
    p1[NameObject("/Resources")] = res
    assert nombre_xobject_libre(p1) == "/EODataOverlay2", "no evitó /EODataOverlay1 ya ocupado"
    xo[NameObject("/EODataOverlay2")] = NameObject("/x")
    assert nombre_xobject_libre(p1) == "/EODataOverlay3"


@test("L — las páginas SIN overlay no reciben ningún /EODataOverlay")
def _():
    # Solo 2 asignaturas con datos -> las hojas de asistencia de las otras 7 quedan sin overlay.
    pdf = gen(1, True, solo_n=2)
    r = PdfReader(io.BytesIO(pdf))
    con = [i + 1 for i, p in enumerate(r.pages)
           if any(n.startswith("/EODataOverlay") for n in _xobject_names(p))]
    total_pg = len(r.pages)
    assert 0 < len(con) < total_pg, f"{len(con)} de {total_pg} páginas con overlay (debería ser un subconjunto pequeño)"
    # una hoja de asistencia de una asignatura SIN datos (la 9ª, offset 8) NO debe llevar overlay
    ini = GRADO_CONFIG[1]["asistencia_inicio"] - 1
    pgs_asig = GRADO_CONFIG[1]["asistencia_pgs_por_asignatura"]
    p_sin_datos = ini + 8 * pgs_asig
    assert not any(n.startswith("/EODataOverlay") for n in _xobject_names(r.pages[p_sin_datos])), \
        f"la página {p_sin_datos+1} (asignatura sin datos) recibió un overlay innecesario"


@test("M — el sello BORRADOR queda DESPUÉS del overlay de datos")
def _():
    pg = R_BRDR.pages[GRADO_CONFIG[1]["datos_estudiantes"] - 1]
    data = _contents_bytes(pg)
    i_data = data.find(b"/EODataOverlay")
    i_brdr = data.find(b"/EOBorrador Do")
    assert i_data != -1 and i_brdr != -1, f"data={i_data} borrador={i_brdr}"
    assert i_data < i_brdr, "BORRADOR se dibuja ANTES que los datos (debería ir encima)"


@test("N — el registro OFICIAL (sin marca) funciona y no lleva /EOBorrador")
def _():
    assert PDF_OFIC[:5] == b"%PDF-" and len(R_OFIC.pages) == GRADO_CONFIG[1]["total_paginas"]
    tiene_borrador = any("/EOBorrador" in _xobject_names(p) for p in R_OFIC.pages)
    assert not tiene_borrador, "el oficial no debe llevar el sello BORRADOR"
    tiene_datos = any(any(n.startswith("/EODataOverlay") for n in _xobject_names(p)) for p in R_OFIC.pages)
    assert tiene_datos, "el oficial sí debe llevar overlays de datos"


@test("O — los seis grados 1–6 generan sin error, con el nº de páginas del template")
def _():
    for g in (1, 2, 3, 4, 5, 6):
        for marca in (True, False):
            pdf = gen(g, marca)
            r = PdfReader(io.BytesIO(pdf))
            tpl = PdfReader(os.path.join(TEMPLATE_DIR, TEMPLATE_FILES[g]))
            assert pdf[:5] == b"%PDF-", f"grado {g} marca={marca}: no es PDF"
            assert len(r.pages) == len(tpl.pages), f"grado {g} marca={marca}: {len(r.pages)} vs {len(tpl.pages)}"


print(f"\n{B}{'=' * 64}{X}")
print(f"{B}  RESUMEN: {pasados}/{total} pruebas pasaron{X}")
print(f"{B}{'=' * 64}{X}")
if fallos:
    for n, e in fallos:
        print(f"{R}✗ {n}{X}\n    {e}")
    sys.exit(1)
print(f"{G}{B}🎉 REGISTRO XOBJECT v2.19.9 — VERDE{X}\n")
