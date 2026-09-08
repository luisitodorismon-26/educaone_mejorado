# -*- coding: utf-8 -*-
"""
EducaOne R2.1B — extractor OFFLINE del catálogo oficial de Competencias
Específicas (CE) e Indicadores de Logro (IL) del Nivel Secundario.

QUÉ HACE
--------
Lee las páginas de referencia "Competencias e indicadores: ‹ÁREA›" que el
MINERD imprime dentro de los propios templates del Registro Escolar y produce
un JSON determinista:

    backend/catalogos/indicadores_secundaria_2023.json

ESTE SCRIPT NO CORRE EN PRODUCCIÓN. Es una herramienta de desarrollo: se
ejecuta a mano, su salida se revisa y se versiona en Git. La aplicación jamás
lo importa — solo lee el JSON (ver `catalogo_indicadores.py`).

FIDELIDAD (R2.1B §3)
--------------------
El texto sale ÍNTEGRO del documento oficial. No hay IA generativa, ni resumen,
ni corrección de estilo, ni palabras completadas por intuición. Las únicas
transformaciones permitidas son tipográficas y están enumeradas y auditadas:

  1. Ligaduras: ﬁ→fi, ﬂ→fl, ﬀ→ff, ﬃ→ffi, ﬄ→ffl. No altera contenido.
  2. Códigos partidos por salto de línea ('IL-' + '19-') se reconocen con un
     regex tolerante; se NORMALIZA el CÓDIGO, nunca el texto.
  3. Guion compuesto partido por salto de línea ('expositivo-' + 'explicativa').
     Al unir palabras con espacio se introduciría un espacio que no está en el
     documento. Se reúnen SOLO si la parte izquierda es alfabética y la derecha
     empieza en minúscula. Se verificó que el documento NO usa silabeo de fin
     de línea (los cortes caen entre palabras), así que esta regla no puede
     fusionar dos palabras distintas. Cada aplicación se enumera en el informe.

DEPENDENCIA
-----------
Requiere `pymupdf`, que NO está en requirements.txt a propósito: es una
herramienta de medición offline, igual que las que se usaron para calibrar el
Registro en fases anteriores. La app y las suites de tests usan solo pypdf.

USO
---
    cd backend
    python tools/extraer_catalogo_indicadores.py            # escribe el JSON
    python tools/extraer_catalogo_indicadores.py --informe  # solo el informe
"""
import argparse
import hashlib
import io
import json
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(BACKEND, "templates", "registro_escolar")
DESTINO = os.path.join(BACKEND, "catalogos", "indicadores_secundaria_2023.json")

VERSION_CURRICULAR = "SEC-2023"
NIVEL = "secundaria"

TEMPLATE_POR_GRADO = {
    1: "Registro-1er-Grado-Sec-General-1-1.pdf",
    2: "Registro-2do-Grado-Sec-General-1-1.pdf",
    3: "Registro-3er-Grado-Sec-General-1-1.pdf",
    4: "Registro-4to-Grado-Sec-Academica-1-1.pdf",
    5: "Registro-5to-Grado-Sec-Academica-1-1.pdf",
    6: "Registro-6to-Grado-Sec-Academica-1-1.pdf",
}

# Página del PERÍODO 1 de cada asignatura base. Las DOS páginas anteriores son
# las de referencia. Estas listas son las mismas que usa registro_escolar.py
# (INDICADORES_P1_CICLO_1 / _2), verificadas página por página en R2.
P1_CICLO_1 = [65, 71, 77, 83, 89, 95, 101, 107, 113]
P1_CICLO_2 = [77, 95, 107, 113, 125, 137, 149, 155, 161]

# Códigos de área en el orden de las 9 asignaturas base del Registro. El
# significado se CONFIRMA leyendo el rótulo "Área:" de cada bloque (ver
# `_verificar_area`), no se asume.
AREAS = ["LE", "LEI", "LEF", "MAT", "CS", "CN", "EA", "EF", "FIHR"]
AREA_NOMBRE_ESPERADO = {
    "LE": "Lengua Española",
    "LEI": "Lenguas Extranjeras Inglés",
    "LEF": "Lenguas Extranjeras Francés",
    "MAT": "Matemática",
    "CS": "Ciencias Sociales",
    "CN": "Ciencias de la Naturaleza",
    "EA": "Educación Artística",
    "EF": "Educación Física",
    "FIHR": "Formación Integral Humana y Religiosa",
}

# Las 7 Competencias Fundamentales del currículo dominicano, en el orden en que
# el template las imprime. El código es de EducaOne (el documento no los trae).
COMPETENCIAS_FUNDAMENTALES = [
    ("CF-COM", "Comunicativa"),
    ("CF-PLC", "Pensamiento Lógico, Creativo y Crítico"),
    ("CF-RP", "Resolución de Problemas"),
    ("CF-EC", "Ética y Ciudadana"),
    ("CF-CT", "Científica y Tecnológica"),
    ("CF-AS", "Ambiental y de la Salud"),
    ("CF-DPE", "Desarrollo Personal y Espiritual"),
]

# Columnas de la tabla de referencia (medidas del template).
COL_CF = (36.4, 122.3)
COL_CE = (122.3, 267.8)
COL_IL = (267.8, 575.5)

LIGADURAS = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl",
             "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st"}

# Marcadores tolerantes: absorben 'IIL-16-', 'IL 19-', 'IL- 20', 'IL7-',
# 'IL -4-' y los códigos partidos por salto de línea.
RE_IL = re.compile(r"\bI{1,2}\s*L\s*-?\s*(\d{1,3})\s*-?\s*")
RE_CE = re.compile(r"\bC\s*E\s*-?\s*([A-ZÑ]{2,5})\s*(\d{1,2})\s*-?\s*")
# Forma invertida encontrada una sola vez en el corpus: 'CE3-LEI-'.
RE_CE_INVERTIDA = re.compile(r"\bC\s*E\s*(\d{1,2})\s*-\s*([A-ZÑ]{2,5})\s*-?\s*")
RE_GUION_COMPUESTO = re.compile(r"([A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{2,})-\s+([a-záéíóúüñ])")

anomalias = []


def clave_tecnica(grado: int, area: str, orden_ce: int, orden_il: int) -> str:
    """
    Identidad TÉCNICA de una entrada del catálogo:

        SEC-2023|2|EF|CE05|IL02
        versión | grado | área | banda | posición dentro de la banda

    Usa la POSICIÓN ESTRUCTURAL del documento, no los códigos académicos,
    porque el documento oficial los repite:

      * 6to Educación Física reinicia la numeración de IL en su 2ª página de
        referencia, así que `il_codigo` no es único dentro del bloque;
      * 2do Educación Física rotula DOS bandas distintas como `CE-EF4` (falta
        `CE-EF5`), así que `ce_codigo` tampoco lo es.

    `orden_ce`/`orden_il` son identidad técnica de EducaOne, NO códigos
    académicos inventados: no se imprimen nunca. Para mostrar y para el
    Registro se usan siempre los valores oficiales `ce_codigo`, `il_codigo`,
    `ce_texto` e `il_texto`, tal como los imprime el MINERD.
    """
    return f"{VERSION_CURRICULAR}|{grado}|{area}|CE{orden_ce:02d}|IL{orden_il:02d}"


def _anota(tipo, grado, area, detalle):
    anomalias.append({"tipo": tipo, "grado": grado, "area": area, "detalle": detalle})


def normalizar_tipografia(texto: str) -> str:
    """Ligaduras -> letras. NO toca palabras ni puntuación."""
    for lig, rep in LIGADURAS.items():
        texto = texto.replace(lig, rep)
    # NFC deja los acentos en su forma compuesta canónica; no cambia letras.
    return unicodedata.normalize("NFC", texto)


def unir_guion_compuesto(texto: str, grado, area, donde):
    """'expositivo- explicativa' -> 'expositivo-explicativa'. Ver docstring."""
    def _rep(m):
        _anota("guion_compuesto", grado, area,
               f"{donde}: '{m.group(1)}- {m.group(2)}…' -> '{m.group(1)}-{m.group(2)}…'")
        return f"{m.group(1)}-{m.group(2)}"
    return RE_GUION_COMPUESTO.sub(_rep, texto)


def _bandas(page):
    """Y de las líneas horizontales que delimitan las filas de la tabla."""
    ys = set()
    for d in page.get_drawings():
        for it in d["items"]:
            if it[0] == "l":
                a, b = it[1], it[2]
                if abs(a.y - b.y) < 0.6 and abs(a.x - b.x) > 100:
                    ys.add(round((a.y + b.y) / 2, 1))
            elif it[0] == "re":
                r = it[1]
                if r.height < 0.6 and r.width > 100:
                    ys.add(round((r.y0 + r.y1) / 2, 1))
    return sorted(ys)


def _celda(page, y0, y1, col):
    """Texto de una celda, uniendo las palabras en orden de lectura."""
    x0, x1 = col
    palabras = [w for w in page.get_text("words")
                if y0 < (w[1] + w[3]) / 2 < y1 and x0 < (w[0] + w[2]) / 2 < x1]
    palabras.sort(key=lambda w: (round(w[1], 1), w[0]))
    return " ".join(w[4] for w in palabras).strip()


def _trocear(texto, regex, formatear_codigo):
    """
    Parte una celda en (codigo, texto) usando `regex` como marcador.
    El texto de cada entrada es TODO lo que va del final de su marcador al
    comienzo del siguiente, verbatim.
    """
    marcas = list(regex.finditer(texto))
    salida = []
    for i, m in enumerate(marcas):
        fin = marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)
        cuerpo = texto[m.end():fin].strip()
        salida.append((formatear_codigo(m), cuerpo, m.group(0)))
    return salida


def _verificar_area(page, y0, y1, grado, area):
    """Confirma el rótulo 'Área: …' del encabezado del bloque."""
    encabezado = " ".join(
        w[4] for w in sorted(page.get_text("words"), key=lambda w: (round(w[1], 1), w[0]))
        if y0 < (w[1] + w[3]) / 2 < y1)
    encabezado = normalizar_tipografia(encabezado)
    esperado = AREA_NOMBRE_ESPERADO[area]
    clave = esperado.split()[0].lower()
    if clave not in encabezado.lower():
        _anota("area_no_confirmada", grado, area,
               f"encabezado={encabezado[:120]!r} esperado≈{esperado!r}")
    return encabezado


def extraer():
    import pymupdf  # solo en tiempo de extracción, nunca en la app

    entradas = []
    matriz = []

    for grado in sorted(TEMPLATE_POR_GRADO):
        fn = TEMPLATE_POR_GRADO[grado]
        doc = pymupdf.open(os.path.join(TEMPLATES, fn))
        p1s = P1_CICLO_2 if grado >= 4 else P1_CICLO_1

        for a_idx, p1 in enumerate(p1s):
            area = AREAS[a_idx]
            paginas_ref = [p1 - 2, p1 - 1]
            orden_ce = 0
            ces_bloque = []
            ils_bloque = []

            for pagina in paginas_ref:
                page = doc[pagina - 1]
                bs = _bandas(page)
                if len(bs) < 3:
                    _anota("sin_bandas", grado, area, f"pg {pagina}: {len(bs)} líneas")
                    continue
                # Banda 0 = encabezado Área/Nivel/Grado; banda 1 = títulos de columna.
                _verificar_area(page, bs[0], bs[1], grado, area)

                for k in range(len(bs) - 1):
                    y0, y1 = bs[k], bs[k + 1]
                    if y1 - y0 < 40:      # encabezados: no son filas de contenido
                        continue
                    orden_ce += 1

                    cf_txt = normalizar_tipografia(_celda(page, y0, y1, COL_CF))
                    ce_txt = normalizar_tipografia(_celda(page, y0, y1, COL_CE))
                    il_txt = normalizar_tipografia(_celda(page, y0, y1, COL_IL))
                    ce_txt = unir_guion_compuesto(ce_txt, grado, area, f"CE pg{pagina}")
                    il_txt = unir_guion_compuesto(il_txt, grado, area, f"IL pg{pagina}")

                    # --- Competencia Fundamental (col 0) ---
                    cf_codigo, cf_nombre = _resolver_cf(cf_txt, orden_ce, grado, area)

                    # --- Competencia Específica (col 1) ---
                    ce_items = _trocear(ce_txt, RE_CE,
                                        lambda m: f"CE-{m.group(1)}{int(m.group(2))}")
                    if not ce_items:
                        inv = _trocear(ce_txt, RE_CE_INVERTIDA,
                                       lambda m: f"CE-{m.group(2)}{int(m.group(1))}")
                        if inv:
                            _anota("ce_codigo_invertido", grado, area,
                                   f"pg{pagina} banda {orden_ce}: {inv[0][2]!r} -> {inv[0][0]}")
                            ce_items = inv
                    if not ce_items:
                        _anota("ce_ausente", grado, area,
                               f"pg{pagina} banda {orden_ce}: {ce_txt[:90]!r}")
                        continue
                    if len(ce_items) > 1:
                        _anota("ce_multiple_en_banda", grado, area,
                               f"pg{pagina} banda {orden_ce}: {[c[0] for c in ce_items]}")
                    ce_codigo, ce_texto, ce_crudo = ce_items[0]
                    if ce_crudo.strip() != f"{ce_codigo}-":
                        _anota("ce_forma_irregular", grado, area,
                               f"pg{pagina}: {ce_crudo!r} -> {ce_codigo}")
                    if ce_codigo in ces_bloque:
                        # Defecto del documento oficial: dos bandas distintas
                        # rotuladas con el MISMO código de CE (ver 2do/EF, donde
                        # falta CE-EF5). NO se renumera —sería inventar un
                        # código— ni se descarta la banda: se conserva tal cual
                        # y se reporta. La clave sigue siendo única porque los
                        # códigos IL de cada banda son distintos.
                        _anota("ce_codigo_repetido", grado, area,
                               f"pg{pagina} banda {orden_ce}: {ce_codigo} ya aparecía en el "
                               f"bloque con otro texto ({ce_texto[:60]!r})")
                    ces_bloque.append(ce_codigo)

                    # --- Indicadores de Logro (col 2) ---
                    il_items = _trocear(il_txt, RE_IL, lambda m: f"IL-{int(m.group(1))}")
                    if not il_items:
                        _anota("il_ausente", grado, area,
                               f"pg{pagina} banda {orden_ce} ({ce_codigo})")
                    for orden_il, (il_codigo, il_texto, il_crudo) in enumerate(il_items, 1):
                        if il_crudo.strip() != f"{il_codigo}-":
                            _anota("il_forma_irregular", grado, area,
                                   f"pg{pagina}: {il_crudo!r} -> {il_codigo}")
                        if not il_texto:
                            _anota("il_texto_vacio", grado, area,
                                   f"pg{pagina}: {il_codigo}")
                        if il_codigo in ils_bloque:
                            # El documento oficial reinicia la numeración en la
                            # segunda página de referencia de algún bloque (ver
                            # 6to/EF). NO se renumera —sería inventar códigos— ni
                            # se descarta la fila: la identidad técnica usa la
                            # POSICIÓN (orden_ce, orden_il), no el código.
                            _anota("il_codigo_reiniciado", grado, area,
                                   f"pg{pagina} {ce_codigo}: {il_codigo} ya existía en el "
                                   f"bloque; la clave lo distingue por posición")
                        ils_bloque.append(il_codigo)
                        entradas.append({
                            "catalogo_clave": clave_tecnica(grado, area, orden_ce, orden_il),
                            "version_curricular": VERSION_CURRICULAR,
                            "nivel": NIVEL,
                            "grado_numero": grado,
                            "area_codigo": area,
                            "area_nombre": AREA_NOMBRE_ESPERADO[area],
                            "competencia_fundamental_codigo": cf_codigo,
                            "competencia_fundamental_nombre": cf_nombre,
                            "ce_codigo": ce_codigo,
                            "ce_texto": ce_texto,
                            "il_codigo": il_codigo,
                            "il_texto": il_texto,
                            # Identidad técnica (posición estructural). NO se
                            # imprime: existe solo para desambiguar.
                            "orden_ce": orden_ce,
                            "orden_il": orden_il,
                            # Trazabilidad al documento físico. `banda_fuente`
                            # es la banda dentro del bloque, es decir el mismo
                            # valor que `orden_ce`; se guarda con nombre propio
                            # para que la procedencia se lea sin conocer el
                            # esquema de la clave.
                            "fuente": fn,
                            "pagina_fuente": pagina,
                            "banda_fuente": orden_ce,
                        })

            matriz.append({
                "grado": grado, "area": area,
                "paginas_fuente": paginas_ref,
                "ce": len(ces_bloque), "il": len(ils_bloque),
                "primer_il": ils_bloque[0] if ils_bloque else None,
                "ultimo_il": ils_bloque[-1] if ils_bloque else None,
                "il_distintos": len(set(ils_bloque)),
                "ce_codigos": ces_bloque,
            })
        doc.close()

    return entradas, matriz


def _resolver_cf(texto, orden_ce, grado, area):
    """
    Competencia Fundamental de la banda. Se busca por texto; si no casa, se usa
    la posición (el template las imprime siempre en el mismo orden) y se anota
    la discrepancia. Nunca se inventa un nombre.
    """
    plano = " ".join(texto.split()).lower()
    for codigo, nombre in COMPETENCIAS_FUNDAMENTALES:
        if plano.startswith(nombre.split(",")[0].lower()[:14]):
            return codigo, nombre
    if 1 <= orden_ce <= len(COMPETENCIAS_FUNDAMENTALES):
        codigo, nombre = COMPETENCIAS_FUNDAMENTALES[orden_ce - 1]
        _anota("cf_por_posicion", grado, area,
               f"banda {orden_ce}: texto={texto[:60]!r} -> {codigo}")
        return codigo, nombre
    _anota("cf_desconocida", grado, area, f"banda {orden_ce}: {texto[:60]!r}")
    return None, texto or None


def serializar(entradas, matriz):
    doc = {
        "version_curricular": VERSION_CURRICULAR,
        "nivel": NIVEL,
        "descripcion": (
            "Catálogo oficial de Competencias Específicas (CE) e Indicadores de "
            "Logro (IL) del Nivel Secundario, extraído de las páginas de "
            "referencia impresas en los templates oficiales del Registro Escolar "
            "MINERD. Texto verbatim del documento oficial."
        ),
        "generado_por": "backend/tools/extraer_catalogo_indicadores.py",
        "areas": AREA_NOMBRE_ESPERADO,
        "competencias_fundamentales": [
            {"codigo": c, "nombre": n} for c, n in COMPETENCIAS_FUNDAMENTALES
        ],
        "fuentes": sorted({e["fuente"] for e in entradas}),
        "total_entradas": len(entradas),
        "entradas": sorted(entradas, key=lambda e: (
            e["grado_numero"], e["area_codigo"], e["orden_ce"], e["orden_il"])),
    }
    return json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def informe(entradas, matriz):
    print("=" * 92)
    print("MATRIZ 54/54 — grado × área")
    print("=" * 92)
    print("%-6s %-6s %-11s %-4s %-4s %-6s %-9s %-9s" %
          ("grado", "área", "pgs", "CE", "IL", "únicos", "primer IL", "último IL"))
    print("-" * 92)
    for m in matriz:
        marca = "" if m["il_distintos"] == m["il"] else "  <- códigos reiniciados"
        print("%-6d %-6s %-11s %-4d %-4d %-6d %-9s %-9s%s" % (
            m["grado"], m["area"], "%d-%d" % tuple(m["paginas_fuente"]),
            m["ce"], m["il"], m["il_distintos"],
            m["primer_il"] or "-", m["ultimo_il"] or "-", marca))
    print("-" * 92)
    print("bloques: %d | entradas IL: %d" % (len(matriz), len(entradas)))
    claves = [e["catalogo_clave"] for e in entradas]
    print("claves TÉCNICAS únicas: %d | duplicadas: %d"
          % (len(set(claves)), len(claves) - len(set(claves))))
    print("IL con texto vacío: %d" % sum(1 for e in entradas if not e["il_texto"].strip()))
    print("CE con texto vacío: %d" % sum(1 for e in entradas if not e["ce_texto"].strip()))
    print()

    # --- Colisiones de CÓDIGO OFICIAL (se conservan tal cual, no se corrigen) ---
    print("=" * 92)
    print("COLISIONES DE CÓDIGO OFICIAL dentro de un mismo grado+área")
    print("=" * 92)
    por_bloque = {}
    for e in entradas:
        por_bloque.setdefault((e["grado_numero"], e["area_codigo"]), []).append(e)

    print("\nA) ce_codigo duplicado:")
    hay_a = False
    for (g, a), es in sorted(por_bloque.items()):
        bandas = {}
        for e in es:
            bandas.setdefault(e["ce_codigo"], set()).add(e["orden_ce"])
        for cod, ordenes in sorted(bandas.items()):
            if len(ordenes) > 1:
                hay_a = True
                print("   grado %d %-5s %-9s en bandas %s" % (g, a, cod, sorted(ordenes)))
                for o in sorted(ordenes):
                    t = next(x["ce_texto"] for x in es if x["orden_ce"] == o)
                    print("        banda %d: %r" % (o, t[:88]))
    if not hay_a:
        print("   (ninguna)")

    print("\nB) il_codigo duplicado:")
    hay_b = False
    for (g, a), es in sorted(por_bloque.items()):
        cods = {}
        for e in es:
            cods.setdefault(e["il_codigo"], []).append(e)
        for cod, grupo in sorted(cods.items(), key=lambda kv: kv[0]):
            if len(grupo) > 1:
                hay_b = True
                print("   grado %d %-5s %-7s x%d -> %s" % (
                    g, a, cod, len(grupo),
                    ", ".join("banda %d (%s)" % (x["orden_ce"], x["ce_codigo"]) for x in grupo)))
    if not hay_b:
        print("   (ninguna)")

    print("\nD) unicidad de la clave técnica sobre TODOS los registros: %s"
          % ("OK" if len(set(claves)) == len(claves) else "FALLA"))
    print()
    print("=" * 92)
    print("ANOMALÍAS (%d)" % len(anomalias))
    print("=" * 92)
    por_tipo = {}
    for a in anomalias:
        por_tipo.setdefault(a["tipo"], []).append(a)
    for tipo in sorted(por_tipo):
        print("\n--- %s (%d) ---" % (tipo, len(por_tipo[tipo])))
        for a in por_tipo[tipo]:
            print("   grado %s área %-5s %s" % (a["grado"], a["area"], a["detalle"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--informe", action="store_true", help="solo informe, no escribe")
    args = ap.parse_args()

    entradas, matriz = extraer()
    informe(entradas, matriz)

    contenido = serializar(entradas, matriz)
    sha = hashlib.sha256(contenido.encode("utf-8")).hexdigest()
    print()
    print("SHA-256 del JSON: %s" % sha)
    print("bytes: %d" % len(contenido.encode("utf-8")))

    if args.informe:
        print("\n(--informe: no se escribió nada)")
        return
    os.makedirs(os.path.dirname(DESTINO), exist_ok=True)
    with io.open(DESTINO, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(contenido)
    print("escrito: %s" % DESTINO)


if __name__ == "__main__":
    main()
