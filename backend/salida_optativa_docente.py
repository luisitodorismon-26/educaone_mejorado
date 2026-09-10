# -*- coding: utf-8 -*-
"""
Identidad calificable y profesor responsable de un componente de Salida Optativa.

R3.4 — POR QUÉ HACE FALTA
=========================

R3.2 dejaba que Dirección vinculara un componente a CUALQUIER Asignatura del
colegio, incluida una troncal. Si "Apreciación y Producción Literarias" apuntaba
a "Lengua Española", R3.3 leía las notas de Lengua y las imprimía como si fueran
del componente optativo. Son dos contextos calificables distintos aunque los dé
el mismo profesor en el mismo curso, así que eso no puede seguir.

La solución NO añade tablas ni fórmulas. `CalificacionSecundaria` se identifica
por (estudiante, asignatura, competencia, año), así que basta con que el
componente tenga su PROPIO `asignatura_id` para que sus notas sean
independientes por construcción, reutilizando `Asignatura`, `AsignacionProfesor`
y `CalificacionSecundaria` tal como están: mismas competencias, mismos P1-P4,
misma recuperación, mismo PC, mismo CF, misma cascada y el mismo Registro R3.3.

QUÉ CUENTA COMO IDENTIDAD INDEPENDIENTE
---------------------------------------
Una Asignatura con `area_curricular_codigo IS NULL`. Ese campo es, desde R2.1C,
la identidad hacia los 9 bloques troncales del Registro: si tiene valor, la
asignatura ES una troncal y sus notas pertenecen a la troncal. Si es NULL, es
una materia propia del colegio y puede representar al componente.

IDENTIDAD, NO NOMBRE
--------------------
La fuente de verdad sigue siendo `CursoComponenteOptativo(componente_codigo,
asignatura_id)`. El `nombre` y el `codigo` de la asignatura dedicada son
display; NUNCA se busca por ellos. Guardar dos veces reutiliza la fila existente
porque se consulta la RELACIÓN, no un nombre.
"""

import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def es_identidad_independiente(asignatura) -> bool:
    """
    ¿Puede esta Asignatura representar a un componente optativo?

    Solo si NO es una troncal del Registro. `area_curricular_codigo` con valor
    significa que la asignatura ocupa uno de los 9 bloques oficiales y que sus
    notas son las de esa troncal.
    """
    if asignatura is None:
        return False
    return getattr(asignatura, 'area_curricular_codigo', None) is None


def crear_asignatura_dedicada(db, curso, componente):
    """
    Asignatura nueva, propia del componente. NO se busca ninguna por nombre.

    `codigo` lleva el código oficial del componente como METADATO de display.
    En producción `asignaturas.codigo` está duplicado y no identifica nada, así
    que nunca se usa para resolver: la identidad es la FK del mapeo.
    """
    from models import Asignatura

    asig = Asignatura(
        colegio_id=curso.colegio_id,
        nombre=componente.nombre_oficial,
        codigo=componente.codigo,
        area='',
        # Un componente optativo NO es uno de los 9 bloques troncales. Dejarlo
        # en NULL es lo que lo mantiene fuera de la resolución de R2.1D y lo que
        # lo marca como identidad independiente.
        area_curricular_codigo=None,
        activo=True,
    )
    db.add(asig)
    db.flush()
    logger.info("R3.4: asignatura dedicada %s creada para el componente %s del curso %s",
                asig.id, componente.codigo, curso.id)
    return asig


def resolver_identidad_calificable(db, curso, componente, mapeo_actual
                                   ) -> Tuple[object, bool, Optional[dict]]:
    """
    Identidad calificable del componente. Devuelve `(asignatura, creada, correccion)`.

    Tres casos, y ninguno toca una sola nota:

      1. No hay mapeo -> se crea la asignatura dedicada.
      2. El mapeo ya apunta a una identidad INDEPENDIENTE -> se REUTILIZA tal
         cual (R3.4 §8), aunque la haya elegido Dirección a mano.
      3. El mapeo apunta a una TRONCAL (legacy de R3.2) -> se crea la identidad
         dedicada y se repunta SOLO `CursoComponenteOptativo`. Las notas de la
         troncal se quedan donde están, con su asignatura de siempre: no se
         mueven, no se copian y no se borran. Lo que se corrige es la REFERENCIA
         del componente, que estaba consumiendo historia ajena. `correccion`
         describe el cambio para dejarlo en auditoría.
    """
    from models import Asignatura

    if mapeo_actual is not None:
        actual = db.query(Asignatura).filter(
            Asignatura.id == mapeo_actual.asignatura_id,
            Asignatura.colegio_id == curso.colegio_id,
        ).first()
        if es_identidad_independiente(actual) and actual.activo is not False:
            return actual, False, None
        if actual is not None:
            nueva = crear_asignatura_dedicada(db, curso, componente)
            correccion = {
                'componente_codigo': componente.codigo,
                'asignatura_anterior_id': actual.id,
                'asignatura_anterior_nombre': actual.nombre,
                'asignatura_anterior_area_curricular': actual.area_curricular_codigo,
                'asignatura_nueva_id': nueva.id,
                'motivo': ('el componente apuntaba a una asignatura troncal del '
                           'Registro; sus calificaciones pertenecen a esa troncal '
                           'y permanecen intactas'),
            }
            logger.warning(
                "R3.4: el componente %s del curso %s apuntaba a la troncal %s (%r, bloque "
                "%s). Se repunta a la asignatura dedicada %s. Las calificaciones de la "
                "troncal NO se tocan.",
                componente.codigo, curso.id, actual.id, actual.nombre,
                actual.area_curricular_codigo, nueva.id)
            return nueva, True, correccion

    return crear_asignatura_dedicada(db, curso, componente), True, None


def asignar_profesor(db, curso, asignatura, profesor_id) -> Optional[str]:
    """
    Deja a `profesor_id` como responsable de (curso, asignatura). Devuelve error o None.

    Reutiliza `AsignacionProfesor`: no hay un sistema paralelo de profesores
    optativos. Al cambiar de profesor se desactiva la asignación anterior y se
    activa la nueva; las calificaciones NO se tocan, porque pertenecen al
    colegio/curso/asignatura/año y no al docente que las cargó.

    `profesor_id` None retira al responsable sin borrar nada.
    """
    from models import AsignacionProfesor, Usuario

    vigentes = db.query(AsignacionProfesor).filter(
        AsignacionProfesor.curso_id == curso.id,
        AsignacionProfesor.asignatura_id == asignatura.id,
        AsignacionProfesor.colegio_id == curso.colegio_id,
        AsignacionProfesor.activo == True,          # noqa: E712
    ).all()

    if profesor_id is None:
        for v in vigentes:
            v.activo = False
        return None

    profe = db.query(Usuario).filter(
        Usuario.id == profesor_id,
        Usuario.colegio_id == curso.colegio_id,
    ).first()
    # Mismo mensaje para inexistente y para otro colegio: no se enumeran
    # usuarios de otros tenants (mismo criterio que R3.3 con las asignaturas).
    if profe is None:
        return 'Profesor no encontrado'
    if profe.role != 'profesor':
        return 'El responsable de un componente optativo debe ser un profesor.'
    if profe.activo is False:
        return 'Ese profesor esta inactivo.'

    for v in vigentes:
        if v.profesor_id == profesor_id:
            return None                  # ya estaba: idempotente
    for v in vigentes:
        v.activo = False                 # se desactiva, nunca se borra

    # Reactivar una asignación previa del mismo profesor si existía, en vez de
    # acumular filas equivalentes.
    previa = db.query(AsignacionProfesor).filter(
        AsignacionProfesor.curso_id == curso.id,
        AsignacionProfesor.asignatura_id == asignatura.id,
        AsignacionProfesor.colegio_id == curso.colegio_id,
        AsignacionProfesor.profesor_id == profesor_id,
    ).first()
    if previa is not None:
        previa.activo = True
        return None

    db.add(AsignacionProfesor(
        colegio_id=curso.colegio_id,
        profesor_id=profesor_id,
        curso_id=curso.id,
        asignatura_id=asignatura.id,
        ano_escolar_id=curso.ano_escolar_id,
        activo=True,
    ))
    return None


def asignaturas_optativas_del_colegio(db, colegio_id) -> set:
    """
    Ids de Asignatura que representan un componente optativo en algún curso.

    R3.4 §14 — GUARDA DE EFECTO COLATERAL. El Registro de Secundaria resuelve
    sus 9 materias troncales por nombre, con un segundo pase por SUBCADENA.
    Cuatro nombres oficiales del catálogo caen dentro de ese pase: "Manejo de la
    Información en Inglés" contiene "Inglés", "Matemática Financiera y
    Tecnología" contiene "Matemática", "Física y Computación" contiene "Física".
    Sin este filtro, una asignatura dedicada creada por R3.4 podría ocupar la
    página troncal de un colegio que no tenga una materia con nombre exacto.

    Una asignatura mapeada como componente NUNCA puede sustituir a una troncal,
    así que se excluye del universo de candidatas. Es la única forma de que
    crear la identidad dedicada no altere en silencio un flujo ajeno.
    """
    from models import CursoComponenteOptativo

    return {r[0] for r in db.query(CursoComponenteOptativo.asignatura_id).filter(
        CursoComponenteOptativo.colegio_id == colegio_id,
        CursoComponenteOptativo.activo == True,      # noqa: E712
    ).distinct().all() if r[0] is not None}


def niveles_asignados_de_profesor(db, profesor_id, colegio_id) -> dict:
    """
    ¿En qué niveles da clases realmente este profesor? -> {'primaria', 'secundaria'}.

    R3.4 §15-§17. El sidebar mostraba a cualquier profesor los items de Primaria
    y de Secundaria a la vez, porque `Usuario.nivel_asignado` está vacío para la
    mayoría y eso se interpretaba como "ambos". Ese campo es a lo sumo su
    división principal, no lo que imparte: un profesor de Secundaria veía
    "Recuperaciones (Primaria)", que no puede usar.

    La verdad son sus ASIGNACIONES ACTIVAS: asignación activa -> curso activo ->
    `Grado.nivel`. Se calcula en el servidor para que el frontend no reimplemente
    ninguna heurística de grados ni adivine por el texto del nombre.
    """
    from models import AsignacionProfesor, Curso, Grado

    niveles = {'primaria': False, 'secundaria': False}
    filas = (db.query(Grado.nivel)
             .select_from(AsignacionProfesor)
             .join(Curso, Curso.id == AsignacionProfesor.curso_id)
             .join(Grado, Grado.id == Curso.grado_id)
             .filter(AsignacionProfesor.profesor_id == profesor_id,
                     AsignacionProfesor.activo == True,          # noqa: E712
                     AsignacionProfesor.colegio_id == colegio_id,
                     Curso.colegio_id == colegio_id,
                     Curso.activo == True)                       # noqa: E712
             .distinct().all())
    for (nivel,) in filas:
        n = (nivel or '').strip().lower()
        if n.startswith('prim'):
            niveles['primaria'] = True
        elif n.startswith('sec'):
            niveles['secundaria'] = True
    return niveles
