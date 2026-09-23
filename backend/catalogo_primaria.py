# -*- coding: utf-8 -*-
"""
Áreas curriculares oficiales del Nivel Primario (R4-A3.3).

POR QUÉ UNA CONSTANTE Y NO UNA TABLA
    Las áreas del Nivel Primario son del sistema educativo dominicano, no de
    ningún colegio: las mismas siete en el primer ciclo y las mismas ocho en
    el segundo, en todos los centros del país. Por eso viven aquí y no en
    PostgreSQL, por las mismas razones que el catálogo de Indicadores
    (`catalogo_indicadores`) y el de Salidas Optativas (`salidas_optativas`):

      * no pertenecen a ningún tenant;
      * quedan versionadas junto al código que las consume;
      * son deterministas en tests, sin fixtures;
      * `VERSION_ACTUAL` permite que una futura adecuación conviva con ésta.

    Ya existía un intento de esto en la tabla `AreaCurricular`, y R3 lo
    descartó: es por colegio, es editable desde una pantalla y usa otro
    vocabulario (`MA`, `LEX`). Una matriz curricular oficial no puede
    depender de que nadie renombre una fila.

QUÉ NO ESTÁ AQUÍ
    · Lenguas Extranjeras Francés (LEF) — tiene currículo propio en los seis
      grados de SECUNDARIA, no en Primaria. Un colegio puede enseñar francés
      en Primaria; simplemente no es un área oficial de promoción de ese
      nivel.
    · Talleres Optativos — no hay evidencia normativa de que participen en la
      decisión de promoción, y sin ella no entran.

IDENTIDAD NO ES PARTICIPACIÓN
    Este módulo responde «qué áreas oficiales espera el grado N», que es una
    pregunta distinta de «qué área oficial representa esta asignatura».

    La segunda la responde `Asignatura.area_curricular_codigo`, y vale para
    los dos niveles. Un colegio privado que enseñe Inglés en 1.º tiene una
    asignatura con identidad LEI perfectamente correcta: LEI simplemente no
    está en el currículo oficial de 1.º, así que esa materia no participa en
    la promoción de ese grado. No es un error de datos ni una inconsistencia:
    es una materia adicional del centro, y conserva profesor, horario, notas,
    boletín y reportes con total normalidad.

Uso:
    import catalogo_primaria as CPRI
    CPRI.codigos_por_grado(2)   -> ('LE', 'MAT', 'CS', 'CN', 'EF', 'FIHR', 'EA')
    CPRI.codigos_por_grado(5)   -> (…, 'LEI', …)
"""

VERSION_ACTUAL = "PRI-2023"

FUENTE_DOCUMENTAL = (
    "Adecuación Curricular del Nivel Primario, MINERD 2023"
)

# Los códigos son los MISMOS que usa `catalogo_indicadores` para Secundaria, y
# eso no es una coincidencia que convenga: es lo que permite que
# `Asignatura.area_curricular_codigo` sirva de identidad única en los dos
# niveles sin un segundo campo. Se verificó área por área que el código y el
# nombre oficial coinciden; la única diferencia es tipográfica —Primaria
# escribe «Lenguas Extranjeras (Inglés)» con paréntesis—.
_NOMBRES = {
    "LE": "Lengua Española",
    "MAT": "Matemática",
    "CS": "Ciencias Sociales",
    "CN": "Ciencias de la Naturaleza",
    "LEI": "Lenguas Extranjeras (Inglés)",
    "EF": "Educación Física",
    "FIHR": "Formación Integral Humana y Religiosa",
    "EA": "Educación Artística",
}

# Orden del documento oficial. Se conserva porque es el que siguen los
# Registros de Grado, y así una lista impresa no necesita reordenarse.
_PRIMER_CICLO = ("LE", "MAT", "CS", "CN", "EF", "FIHR", "EA")
_SEGUNDO_CICLO = ("LE", "MAT", "CS", "CN", "LEI", "EF", "FIHR", "EA")

# Inglés aparece en los Registros de 4.º, 5.º y 6.º —hoja 96 de cada uno— y no
# en los de 1.º a 3.º. Ese es el corte entre ciclos, comprobado en fase R3
# contra los seis Registros de Grado 2026.
_CICLOS = {
    VERSION_ACTUAL: {
        "primer_ciclo": {"grados": (1, 2, 3), "codigos": _PRIMER_CICLO},
        "segundo_ciclo": {"grados": (4, 5, 6), "codigos": _SEGUNDO_CICLO},
    },
}

GRADOS_VALIDOS = (1, 2, 3, 4, 5, 6)


class CatalogoPrimariaError(ValueError):
    """Versión o grado que este catálogo no puede responder."""


def versiones_disponibles():
    return sorted(_CICLOS)


def _es_grado_real(valor):
    """Un entero de 1 a 6. `True` NO es 1.

    En Python `isinstance(True, int)` es cierto, así que sin esta comprobación
    `codigos_por_grado(True)` devolvería el currículo de 1.º. Un booleano
    donde se espera un grado es un error de quien llama, no un 1.º.
    """
    return (isinstance(valor, int) and not isinstance(valor, bool)
            and valor in GRADOS_VALIDOS)


def _ciclos(version=None):
    version = version or VERSION_ACTUAL
    try:
        return _CICLOS[version]
    except (KeyError, TypeError):
        raise CatalogoPrimariaError(
            "Versión curricular de Primaria desconocida: %r. Disponibles: %s"
            % (version, ", ".join(versiones_disponibles())))


def ciclo_de_grado(grado_numero, version=None):
    """'primer_ciclo' | 'segundo_ciclo'. Lanza si el grado no es 1..6."""
    if not _es_grado_real(grado_numero):
        raise CatalogoPrimariaError(
            "Grado de Primaria inválido: %r. Debe ser un entero de 1 a 6."
            % (grado_numero,))
    for nombre, datos in _ciclos(version).items():
        if grado_numero in datos["grados"]:
            return nombre
    raise CatalogoPrimariaError(
        "El grado %r no pertenece a ningún ciclo de la versión %r"
        % (grado_numero, version or VERSION_ACTUAL))


def codigos_por_grado(grado_numero, version=None):
    """Los códigos de área oficiales que ESPERA este grado.

    No recibe profesor, ni asignatura, ni notas, ni nombre: si cambiara con
    cualquiera de esas cosas no sería un currículo. Devuelve una tupla en el
    orden del documento oficial.
    """
    ciclo = ciclo_de_grado(grado_numero, version)
    return tuple(_ciclos(version)[ciclo]["codigos"])


def areas_por_grado(grado_numero, version=None):
    """Igual que `codigos_por_grado`, con el nombre oficial de cada área."""
    return tuple({"codigo": c, "nombre": _NOMBRES[c]}
                 for c in codigos_por_grado(grado_numero, version))


def nombre_area(codigo, version=None):
    """Nombre oficial del área, o None si el código no es de Primaria."""
    _ciclos(version)
    return _NOMBRES.get(codigo)


def codigos_validos(version=None):
    """Todos los códigos que aparecen en algún ciclo de esta versión."""
    datos = _ciclos(version)
    vistos = []
    for ciclo in ("primer_ciclo", "segundo_ciclo"):
        for codigo in datos[ciclo]["codigos"]:
            if codigo not in vistos:
                vistos.append(codigo)
    return tuple(vistos)


def area_valida(codigo, version=None):
    """¿Es `codigo` un área oficial del Nivel Primario en ALGÚN grado?

    Ojo: esto es identidad, no participación. LEI es válida como área de
    Primaria y aun así no se espera en 1.º.
    """
    return bool(codigo) and codigo in codigos_validos(version)


def metadatos(version=None):
    """Cabecera del catálogo, para diagnóstico y para el informe."""
    version = version or VERSION_ACTUAL
    datos = _ciclos(version)
    return {
        "version_curricular": version,
        "nivel": "primaria",
        "fuente": FUENTE_DOCUMENTAL,
        "areas": dict(_NOMBRES),
        "ciclos": {
            nombre: {"grados": tuple(d["grados"]),
                     "codigos": tuple(d["codigos"])}
            for nombre, d in datos.items()
        },
    }
