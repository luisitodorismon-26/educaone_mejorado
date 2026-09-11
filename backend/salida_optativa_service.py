# -*- coding: utf-8 -*-
"""
Resolución y validación de la Salida Optativa de un curso.

R3.1 — CAPA DE REGLAS, SIN ENDPOINTS
====================================

Este módulo traduce entre el catálogo oficial (`salidas_optativas.py`, una
constante MINERD) y los datos del colegio (`Curso.salida_optativa_codigo` y
`CursoComponenteOptativo`). Es la ÚNICA vía admitida para responder:

    curso 4to A -> salida 'CYT' -> componente 'CYT-CN-4' -> asignatura_id 123

Nada aquí resuelve por nombre textual ni por `Asignatura.codigo`: en producción
ese código está duplicado (ids 1-8 y 9-16 comparten LE/MA/CS/CN/IN/EF/EA/FH) y
por tanto no identifica nada.

R3.1 deliberadamente NO expone endpoints ni UI (eso es R3.2) y NO estampa nada
en el Registro (eso es R3.3). Aquí solo viven el modelo y sus reglas, para que
ambas fases posteriores consuman las MISMAS validaciones en vez de reescribirlas.
"""

import logging
from typing import List, Optional, Tuple

from salidas_optativas import (
    SALIDAS,
    componente as _componente,
    componente_pertenece,
    componentes_de,
    grado_admite_salida,
    salida_valida,
)

logger = logging.getLogger(__name__)

# Resultado uniforme de validación: (ok, mensaje_de_error_o_None)
Resultado = Tuple[bool, Optional[str]]


def grado_numero_de_curso(curso) -> Optional[int]:
    """
    Número de grado de un curso (4, 5, 6...), o None si no es de secundaria.

    Reutiliza los mismos helpers que el Registro Escolar para no introducir una
    segunda interpretación del nombre del grado. Devuelve None para primaria e
    inicial: un "4to Primaria" también contiene un 4, y sin este filtro podría
    configurarse una Salida Optativa que no existe en ese nivel.
    """
    from registro_validator import _extraer_grado_numero, _normalizar_nivel

    grado = getattr(curso, 'grado', None)
    if grado is None:
        return None
    if _normalizar_nivel(getattr(grado, 'nivel', None)) != 'secundaria':
        return None
    return _extraer_grado_numero(getattr(grado, 'nombre', '') or '')


def curso_admite_salida(curso) -> bool:
    """True solo para 4to-6to de Secundaria (Modalidad Académica)."""
    return grado_admite_salida(grado_numero_de_curso(curso))


def validar_salida_para_curso(curso, codigo: Optional[str]) -> Resultado:
    """
    ¿Puede este curso quedar configurado con la salida `codigo`?

    `codigo` None significa "sin configurar" y SIEMPRE es válido: es el estado
    de todos los cursos tras la migración y la forma de desconfigurar uno.
    """
    if codigo is None:
        return True, None

    if not salida_valida(codigo):
        return False, (
            f"Salida optativa desconocida: {codigo!r}. "
            f"Las válidas son: {', '.join(sorted(SALIDAS))}."
        )

    grado_numero = grado_numero_de_curso(curso)
    if grado_numero is None:
        return False, "Solo los cursos de Secundaria tienen Salida Optativa."
    if not grado_admite_salida(grado_numero):
        return False, (
            f"{grado_numero}to de Secundaria no tiene Salida Optativa: "
            "solo existe en la Modalidad Académica de 4to a 6to."
        )
    return True, None


def ano_de_curso(curso) -> Optional[int]:
    """
    Año escolar al que pertenece el curso: la ÚNICA fuente de verdad del año
    para su configuración optativa.

    EducaOne crea una fila `Curso` NUEVA por año escolar —`clonar-cursos` y
    `cierre-ano/promover` hacen `db.add(Curso(..., ano_escolar_id=destino))` y
    mueven `estudiante.curso_id`; en todo el backend no existe una sola
    escritura a `Curso.ano_escolar_id` fuera de la creación—. Por eso el año del
    curso ES el año de su salida optativa, y no hace falta una segunda fuente.
    """
    return getattr(curso, 'ano_escolar_id', None)


def colegio_de_curso(curso) -> Optional[int]:
    """Colegio dueño del curso: la única fuente de tenant para su configuración."""
    return getattr(curso, 'colegio_id', None)


def validar_ano_para_curso(db, curso, ano_escolar_id: Optional[int] = None,
                           colegio_id: Optional[int] = None) -> Resultado:
    """
    Coherencia CURSO ↔ COLEGIO ↔ AÑO ESCOLAR, centralizada aquí para que la use
    tanto la API de R3.2 como el Registro de R3.3 y no se reimplemente dos veces.

    Comprueba que el curso tenga colegio y año, que el año exista, que sea del
    mismo colegio y que coincidan con los valores pedidos. `ano_escolar_id` y
    `colegio_id` None significan "usar los del curso" y es la forma recomendada
    de llamarla: los valores nunca deberían venir del cliente.
    """
    from models import AnoEscolar

    colegio_curso = colegio_de_curso(curso)
    if colegio_curso is None:
        # Regla propia de la Salida Optativa. El resto del sistema tolera
        # `colegio_id` NULL por instalaciones de un solo colegio anteriores al
        # multi-tenant, pero una configuración optativa sin dueño no podría
        # aislarse por tenant. En producción los 7 cursos tienen colegio.
        return False, (
            "El curso no tiene colegio asignado. No se puede configurar su "
            "Salida Optativa."
        )
    if colegio_id is not None and colegio_id != colegio_curso:
        return False, (
            f"El colegio {colegio_id} no corresponde al curso, que pertenece al "
            f"colegio {colegio_curso}."
        )

    ano_curso = ano_de_curso(curso)
    if ano_curso is None:
        return False, (
            "El curso no tiene año escolar asignado. Asígnele uno antes de "
            "configurar su Salida Optativa."
        )

    if ano_escolar_id is not None and ano_escolar_id != ano_curso:
        return False, (
            f"El año escolar {ano_escolar_id} no corresponde al curso, que "
            f"pertenece al año {ano_curso}."
        )

    ano = db.query(AnoEscolar).filter(AnoEscolar.id == ano_curso).first()
    if ano is None:
        return False, f"El año escolar {ano_curso} no existe."
    if ano.colegio_id != colegio_curso:
        return False, "El año escolar pertenece a otro colegio."

    return True, None


def validar_coherencia_mapeo(mapeo, curso) -> Resultado:
    """
    Última línea: una fila `CursoComponenteOptativo` SOLO es coherente si su
    tenant y su año son exactamente los del curso al que cuelga.

    Se aplica a la fila ya construida —antes del commit en R3.2, y como
    aserción de lectura en R3.3—, de modo que ningún camino pueda dejar un
    mapeo apuntando a otro colegio o a otro año que su curso.
    """
    if getattr(mapeo, 'curso_id', None) != getattr(curso, 'id', None):
        return False, "El mapeo no pertenece a este curso."
    if getattr(mapeo, 'colegio_id', None) != colegio_de_curso(curso):
        return False, (
            "El colegio del mapeo no coincide con el del curso."
        )
    if getattr(mapeo, 'ano_escolar_id', None) != ano_de_curso(curso):
        return False, (
            "El año escolar del mapeo no coincide con el del curso."
        )
    return True, None


def validar_mapeo_componente(db, curso, componente_codigo: str,
                             asignatura_id: Optional[int],
                             ano_escolar_id: Optional[int] = None,
                             colegio_id: Optional[int] = None) -> Resultado:
    """
    ¿Puede `asignatura_id` representar a `componente_codigo` en este curso?

    Verifica, en este orden:
      1. el curso admite Salida Optativa y tiene una configurada;
      2. el componente existe en el catálogo oficial;
      3. el componente pertenece A ESA salida y A ESE grado;
      4. el curso tiene colegio y año escolar, ese año existe, es del mismo
         colegio y ambos coinciden con los valores pedidos (si se pasaron);
      5. la asignatura existe y es DEL MISMO COLEGIO que el curso (tenant-safe).

    `ano_escolar_id` y `colegio_id` son OPCIONALES y solo sirven de verificación
    cruzada cuando el llamador cree saberlos. Lo correcto es no pasarlos: el
    valor bueno es siempre el del curso (ver `construir_mapeo`).

    Es una función PURA de validación: no escribe nada. Si algo falla, el
    llamador no debe crear la fila.

    Las dos unicidades restantes —un componente con dos asignaturas, y una
    asignatura en dos componentes del mismo curso— las garantizan las
    UniqueConstraint de `CursoComponenteOptativo`, que son la última línea de
    defensa ante dos requests simultáneos. Funcionan porque `ano_escolar_id` es
    NOT NULL: con NULL, PostgreSQL no las haría colisionar.
    """
    from models import Asignatura

    grado_numero = grado_numero_de_curso(curso)
    if not grado_admite_salida(grado_numero):
        return False, "Este curso no tiene Salida Optativa."

    salida = getattr(curso, 'salida_optativa_codigo', None)
    if not salida_valida(salida):
        return False, (
            "El curso todavía no tiene una Salida Optativa configurada. "
            "Configúrela antes de asignar sus componentes."
        )

    comp = _componente(componente_codigo)
    if comp is None:
        return False, f"Componente optativo desconocido: {componente_codigo!r}."

    if not componente_pertenece(componente_codigo, salida, grado_numero):
        return False, (
            f"El componente {componente_codigo!r} ({comp.nombre_oficial}) pertenece a la "
            f"salida {comp.salida} de {comp.grado}to y no puede usarse en un curso "
            f"de {grado_numero}to configurado como {salida}."
        )

    ok_ano, err_ano = validar_ano_para_curso(db, curso, ano_escolar_id, colegio_id)
    if not ok_ano:
        return False, err_ano

    if asignatura_id is None:
        return False, "Debe indicar la asignatura que imparte este componente."

    asig = db.query(Asignatura).filter(Asignatura.id == asignatura_id).first()
    if asig is None:
        return False, f"La asignatura {asignatura_id} no existe."

    # Tenant safety: nunca se acepta una asignatura de otro colegio, ni aunque
    # el id venga en el request. Se compara permitiendo NULL == NULL porque
    # `colegio_id` es nullable en instalaciones de un solo colegio.
    if asig.colegio_id != colegio_de_curso(curso):
        return False, "La asignatura pertenece a otro colegio."

    return True, None


def construir_mapeo(db, curso, componente_codigo: str, asignatura_id: Optional[int]):
    """
    Única vía admitida para CREAR un `CursoComponenteOptativo`.

    Devuelve `(mapeo, None)` con la fila lista para `db.add()`, o `(None, error)`
    si algo no valida — en cuyo caso NO se construye nada y no se toca la sesión.

    `colegio_id` y `ano_escolar_id` se DERIVAN de `Curso`. No se aceptan del
    cliente ni siquiera como parámetro: un request no puede colocar un
    componente en otro colegio o en otro año, porque esos valores no viajan
    hasta aquí. Es la misma razón por la que ambas columnas son NOT NULL —
    participan en las claves únicas y en PostgreSQL dos NULL no colisionarían.

    La fila resultante se comprueba además con `validar_coherencia_mapeo`, de
    modo que la invariante quede afirmada sobre el objeto real y no solo sobre
    los argumentos.
    """
    from models import CursoComponenteOptativo

    ok, err = validar_mapeo_componente(db, curso, componente_codigo, asignatura_id)
    if not ok:
        return None, err

    mapeo = CursoComponenteOptativo(
        colegio_id=colegio_de_curso(curso),      # derivado, nunca del request
        curso_id=curso.id,
        ano_escolar_id=ano_de_curso(curso),      # derivado, nunca del request
        componente_codigo=componente_codigo,
        asignatura_id=asignatura_id,
        activo=True,
    )

    ok, err = validar_coherencia_mapeo(mapeo, curso)
    if not ok:
        return None, err
    return mapeo, None


def componentes_esperados(curso):
    """
    Componentes oficiales que este curso DEBE cursar según su salida.
    Lista vacía si no tiene salida configurada o no le corresponde.
    """
    return componentes_de(getattr(curso, 'salida_optativa_codigo', None),
                          grado_numero_de_curso(curso))


def resolver_componentes(db, curso, ano_escolar_id: Optional[int] = None) -> List[dict]:
    """
    Resuelve la cadena completa para el Registro Escolar, ordenada por slot:

        [{'componente': ComponenteOptativo, 'asignatura_id': int|None,
          'slot': int, 'mapeo_id': int|None}, ...]

    `asignatura_id` None significa que el colegio configuró la salida pero
    todavía no dijo qué asignatura suya imparte ese componente. NO se adivina.

    EL AÑO SE DERIVA DEL CURSO. `ano_escolar_id` es opcional y solo sirve como
    verificación cruzada: si se pasa y NO coincide con el del curso, se lanza
    ValueError en vez de devolver en silencio la configuración de otro año.
    Un curso sin año devuelve lista vacía y deja rastro en el log: no se
    adivina a qué año pertenece su configuración.

    R3.3 usará `slot` para saber a qué página del template va cada nota:
    slot == índice en `GRADO_CONFIG[g]['completiva_salida_optativa']`.
    """
    from models import CursoComponenteOptativo

    esperados = componentes_esperados(curso)
    if not esperados:
        return []

    ano_curso = ano_de_curso(curso)
    colegio_curso = colegio_de_curso(curso)
    if ano_escolar_id is not None and ano_escolar_id != ano_curso:
        raise ValueError(
            f"ano_escolar_id={ano_escolar_id} no corresponde al curso "
            f"{getattr(curso, 'id', '?')}, que pertenece al año {ano_curso}."
        )
    if ano_curso is None or colegio_curso is None:
        logger.warning(
            "Curso %s tiene Salida Optativa configurada pero le falta colegio o año "
            "escolar (colegio=%r, año=%r); no se resuelven sus componentes.",
            getattr(curso, 'id', '?'), colegio_curso, ano_curso,
        )
        return []

    filas = db.query(CursoComponenteOptativo).filter(
        CursoComponenteOptativo.curso_id == curso.id,
        CursoComponenteOptativo.colegio_id == colegio_curso,
        CursoComponenteOptativo.ano_escolar_id == ano_curso,
        CursoComponenteOptativo.activo == True,  # noqa: E712 (SQLAlchemy)
    ).all()
    # Defensa en profundidad: aunque el filtro ya acota tenant y año, se afirma
    # sobre cada fila real. Una incoherencia se ignora y se reporta; nunca se
    # devuelve como si fuera configuración válida de este curso.
    por_codigo = {}
    for f in filas:
        ok, err = validar_coherencia_mapeo(f, curso)
        if not ok:
            logger.error("Mapeo optativo %s descartado: %s", f.id, err)
            continue
        por_codigo[f.componente_codigo] = f

    # R3.4.1-hotfix — UN MAPEO A UNA TRONCAL NO ES UNA IDENTIDAD OPTATIVA.
    #
    # R3.2 permitia vincular un componente a CUALQUIER asignatura, incluida una
    # troncal del Registro. En produccion quedaron mapeos asi: HCS-LE-4 apunta a
    # "Lengua Española" (area_curricular_codigo='LE'). Leer ese mapeo tal cual
    # hace que las notas y la asistencia de Lengua se consuman como si fueran del
    # componente optativo: acabarian impresas en la pagina 212 del Registro y en
    # el bloque de asistencia 56-60, y el dashboard reetiqueta la troncal con el
    # nombre del componente y Lengua desaparece de Calificaciones.
    #
    # Para LECTURA ese mapeo se considera PENDIENTE DE CONVERSION: se conserva el
    # componente y su slot —la geometria del Registro no cambia— pero NO se
    # expone el `asignatura_id` de la troncal como identidad optativa. El bloque
    # se queda sin datos, que es lo correcto: esas notas son de la troncal.
    #
    # Esto NO altera el mapeo ni la asignatura ni ninguna nota. Y NO afecta a la
    # conversion explicita: `resolver_identidad_calificable` lee la fila
    # `CursoComponenteOptativo` directamente, no a traves de esta funcion, asi
    # que Direccion sigue pudiendo convertirlo a identidad dedicada.
    from models import Asignatura

    salida = []
    for comp in esperados:
        fila = por_codigo.get(comp.codigo)
        asignatura_id = fila.asignatura_id if fila else None
        legacy_troncal_id = None
        if asignatura_id is not None:
            asig = db.query(Asignatura).filter(
                Asignatura.id == asignatura_id,
                Asignatura.colegio_id == colegio_curso,
            ).first()
            if asig is not None and asig.area_curricular_codigo is not None:
                logger.warning(
                    "Mapeo optativo %s del curso %s apunta a la asignatura troncal %s "
                    "(%r, bloque %s). Se trata como PENDIENTE DE CONVERSION: no se "
                    "expone como identidad optativa y su bloque queda sin datos. "
                    "Configure el profesor responsable del componente para darle "
                    "identidad propia.",
                    fila.id, curso.id, asig.id, asig.nombre,
                    asig.area_curricular_codigo)
                legacy_troncal_id = asig.id
                asignatura_id = None
        salida.append({
            'componente': comp,
            'slot': comp.slot,
            'asignatura_id': asignatura_id,
            'mapeo_id': fila.id if fila else None,
            # Para que la pantalla de Direccion pueda explicar POR QUE aparece
            # sin vincular en vez de mostrarlo como un hueco silencioso.
            'pendiente_conversion': legacy_troncal_id is not None,
            'asignatura_troncal_id': legacy_troncal_id,
        })
    return salida
