# -*- coding: utf-8 -*-
"""
Autovinculación de asignaturas a su bloque curricular oficial (R2.1E).

R2.1C dejó `Asignatura.area_curricular_codigo` como la ÚNICA identidad válida
hacia los 9 bloques del Registro de Secundaria, y obliga a que la configure
Dirección. En la práctica eso pide configurar a mano materias que no tienen
ninguna ambigüedad: "Inglés" es LEI en todos los colegios del país.

Este módulo cubre solo ese caso: nombres OFICIALES INEQUÍVOCOS. Es un atajo de
alta, no una fuente de verdad.

REGLA INNEGOCIABLE
------------------
La inferencia solo ocurre en dos momentos:

  * al CREAR una asignatura sin área explícita;
  * en un backfill de arranque, y solo sobre filas con área NULL.

Una vez que `area_curricular_codigo` tiene valor, ESE valor manda. R2.1D jamás
vuelve a mirar el nombre: si alguien renombra "Inglés" a "English", el bloque
no cambia. Es exactamente la separación que R2.1C estableció.

CÓMO SE COMPARA
---------------
Coincidencia EXACTA tras normalizar: recorte, minúsculas (casefold), colapso de
espacios repetidos y eliminación de acentos SOLO para comparar. Nada más.

PROHIBIDO —y no implementado— fuzzy, `contains`, `startswith`, distancias de
edición o IA. "Inglés Conversacional" NO es "Inglés": es una materia distinta
del colegio y se queda en NULL, que es un estado válido.
"""

import logging
import unicodedata
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def normalizar(nombre: Optional[str]) -> str:
    """Clave de comparación. NO se guarda: solo sirve para el lookup exacto."""
    if not nombre:
        return ""
    texto = unicodedata.normalize("NFD", str(nombre).strip().casefold())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return " ".join(texto.split())


# Alias OFICIALES e inequívocos. Cada entrada es un nombre completo, nunca un
# fragmento. Ampliar esta tabla es una decisión académica, no técnica: un alias
# de más autovincularía en silencio una materia que no corresponde.
_ALIAS_CRUDOS: Dict[str, List[str]] = {
    "LE": [
        "Lengua Española",
    ],
    "LEI": [
        "Inglés", "Ingles",
    ],
    "LEF": [
        "Francés", "Frances",
    ],
    "MAT": [
        "Matemática", "Matematica", "Matemáticas", "Matematicas",
    ],
    "CS": [
        "Ciencias Sociales",
    ],
    "CN": [
        "Ciencias Naturales",
    ],
    "EA": [
        "Educación Artística", "Educacion Artistica",
    ],
    "EF": [
        "Educación Física", "Educacion Fisica",
    ],
    "FIHR": [
        "Formación Integral Humana y Religiosa",
        "Formacion Integral Humana y Religiosa",
        "Formación Humana", "Formacion Humana",
    ],
}

# Índice normalizado -> código. Se construye una vez; si dos alias colisionaran
# al normalizar sería un error de la tabla, así que se detecta al importar.
ALIAS: Dict[str, str] = {}
for _codigo, _nombres in _ALIAS_CRUDOS.items():
    for _n in _nombres:
        _clave = normalizar(_n)
        assert _clave, f"alias vacío para {_codigo}"
        assert _clave not in ALIAS or ALIAS[_clave] == _codigo, (
            f"alias ambiguo {_clave!r}: {ALIAS.get(_clave)} vs {_codigo}")
        ALIAS[_clave] = _codigo


def inferir_area(nombre: Optional[str]) -> Optional[str]:
    """
    Bloque oficial de un nombre de asignatura, o None.

    None NO es un error: significa "esta materia no es uno de los 9 bloques
    inequívocos". Música, Inglés Conversacional o Taller de Inglés caen aquí y
    se quedan sin vincular, que es su estado correcto.
    """
    return ALIAS.get(normalizar(nombre))


def _bloque_ocupado_en_algun_curso(db, asignatura, codigo) -> Optional[dict]:
    """
    ¿Alguna OTRA asignatura activa ya ocupa `codigo` en un curso compartido?

    Reutiliza la semántica de R2.1C: la exclusividad es POR CURSO. Dos
    asignaturas distintas pueden compartir un bloque en cursos diferentes; la
    misma asignatura con varios profesores no es colisión; una materia con área
    NULL no participa.

    Devuelve el conflicto encontrado, o None si autovincular es seguro.
    """
    from models import Asignatura, AsignacionProfesor

    # Cursos donde ESTA asignatura está activa.
    cursos = [r[0] for r in db.query(AsignacionProfesor.curso_id).filter(
        AsignacionProfesor.asignatura_id == asignatura.id,
        AsignacionProfesor.activo == True,            # noqa: E712
        AsignacionProfesor.colegio_id == asignatura.colegio_id,
    ).distinct().all()]
    if not cursos:
        return None            # sin cursos no puede colisionar con nadie

    fila = (db.query(Asignatura.id, Asignatura.nombre, AsignacionProfesor.curso_id)
            .join(AsignacionProfesor, AsignacionProfesor.asignatura_id == Asignatura.id)
            .filter(AsignacionProfesor.curso_id.in_(cursos),
                    AsignacionProfesor.activo == True,        # noqa: E712
                    AsignacionProfesor.colegio_id == asignatura.colegio_id,
                    Asignatura.colegio_id == asignatura.colegio_id,
                    Asignatura.activo == True,                # noqa: E712
                    Asignatura.area_curricular_codigo == codigo,
                    Asignatura.id != asignatura.id)
            .first())
    if fila is None:
        return None
    return {"asignatura_id": fila[0], "nombre": fila[1], "curso_id": fila[2]}


def autovincular_existentes(db) -> dict:
    """
    Backfill IDEMPOTENTE de arranque.

    Toca EXCLUSIVAMENTE filas con `area_curricular_codigo IS NULL` cuyo nombre
    coincida EXACTAMENTE con un alias oficial. No cambia nombres, ni códigos
    legacy, ni el rótulo `area`, ni ninguna selección de indicadores ni ningún
    contenido clave. Una fila ya vinculada no se vuelve a mirar, así que correrlo
    N veces da el mismo resultado que correrlo una.

    Si autovincular provocaría una colisión de bloque en un curso, la fila se
    DEJA EN NULL y se reporta: no se elige, no se mezcla, no se adivina.
    """
    from models import Asignatura

    candidatas = db.query(Asignatura).filter(
        Asignatura.area_curricular_codigo.is_(None),
        Asignatura.activo == True,                    # noqa: E712
    ).all()

    resumen = {"vinculadas": 0, "sin_alias": 0, "colisiones": 0}
    for asig in candidatas:
        codigo = inferir_area(asig.nombre)
        if codigo is None:
            resumen["sin_alias"] += 1
            continue
        conflicto = _bloque_ocupado_en_algun_curso(db, asig, codigo)
        if conflicto:
            resumen["colisiones"] += 1
            logger.warning(
                "Autovínculo omitido: la asignatura %s (%r) coincide con el bloque %s, "
                "pero en el curso %s ya lo ocupa la asignatura %s (%r). Se deja sin "
                "vincular para que Dirección decida.",
                asig.id, asig.nombre, codigo, conflicto["curso_id"],
                conflicto["asignatura_id"], conflicto["nombre"],
            )
            continue
        asig.area_curricular_codigo = codigo
        resumen["vinculadas"] += 1
        logger.info("Autovínculo: asignatura %s (%r) -> bloque %s",
                    asig.id, asig.nombre, codigo)

    if resumen["vinculadas"]:
        db.commit()
    return resumen
