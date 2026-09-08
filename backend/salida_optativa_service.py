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

from typing import List, Optional, Tuple

from salidas_optativas import (
    SALIDAS,
    componente as _componente,
    componente_pertenece,
    componentes_de,
    grado_admite_salida,
    salida_valida,
)

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


def validar_mapeo_componente(db, curso, componente_codigo: str,
                             asignatura_id: Optional[int]) -> Resultado:
    """
    ¿Puede `asignatura_id` representar a `componente_codigo` en este curso?

    Verifica, en este orden:
      1. el curso admite Salida Optativa y tiene una configurada;
      2. el componente existe en el catálogo oficial;
      3. el componente pertenece A ESA salida y A ESE grado;
      4. la asignatura existe y es DEL MISMO COLEGIO que el curso (tenant-safe).

    Las dos unicidades restantes —un componente con dos asignaturas, y una
    asignatura en dos componentes del mismo curso— las garantizan las
    UniqueConstraint de `CursoComponenteOptativo`, que son la última línea de
    defensa ante dos requests simultáneos.
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

    if asignatura_id is None:
        return False, "Debe indicar la asignatura que imparte este componente."

    asig = db.query(Asignatura).filter(Asignatura.id == asignatura_id).first()
    if asig is None:
        return False, f"La asignatura {asignatura_id} no existe."

    # Tenant safety: nunca se acepta una asignatura de otro colegio, ni aunque
    # el id venga en el request. Se compara permitiendo NULL == NULL porque
    # `colegio_id` es nullable en instalaciones de un solo colegio.
    if asig.colegio_id != getattr(curso, 'colegio_id', None):
        return False, "La asignatura pertenece a otro colegio."

    return True, None


def componentes_esperados(curso):
    """
    Componentes oficiales que este curso DEBE cursar según su salida.
    Lista vacía si no tiene salida configurada o no le corresponde.
    """
    return componentes_de(getattr(curso, 'salida_optativa_codigo', None),
                          grado_numero_de_curso(curso))


def resolver_componentes(db, curso, ano_escolar_id: Optional[int]) -> List[dict]:
    """
    Resuelve la cadena completa para el Registro Escolar, ordenada por slot:

        [{'componente': ComponenteOptativo, 'asignatura_id': int|None,
          'slot': int, 'mapeo_id': int|None}, ...]

    `asignatura_id` None significa que el colegio configuró la salida pero
    todavía no dijo qué asignatura suya imparte ese componente. NO se adivina.

    R3.3 usará `slot` para saber a qué página del template va cada nota:
    slot == índice en `GRADO_CONFIG[g]['completiva_salida_optativa']`.
    """
    from models import CursoComponenteOptativo

    esperados = componentes_esperados(curso)
    if not esperados:
        return []

    filas = db.query(CursoComponenteOptativo).filter(
        CursoComponenteOptativo.curso_id == curso.id,
        CursoComponenteOptativo.colegio_id == getattr(curso, 'colegio_id', None),
        CursoComponenteOptativo.ano_escolar_id == ano_escolar_id,
        CursoComponenteOptativo.activo == True,  # noqa: E712 (SQLAlchemy)
    ).all()
    por_codigo = {f.componente_codigo: f for f in filas}

    salida = []
    for comp in esperados:
        fila = por_codigo.get(comp.codigo)
        salida.append({
            'componente': comp,
            'slot': comp.slot,
            'asignatura_id': fila.asignatura_id if fila else None,
            'mapeo_id': fila.id if fila else None,
        })
    return salida
