# -*- coding: utf-8 -*-
"""
¿Tiene historia académica real la asignatura que implementa un componente?

R3.2 §7-§8 — LA GUARDA QUE HACE IRREVERSIBLE LO IRREVERSIBLE
============================================================

Cambiar la Salida Optativa de un curso (HLM -> HCS) cambia el juego de
componentes, y por tanto invalida los mapeos anteriores. Eso está bien mientras
esos mapeos no tengan NADA colgando. En cuanto un profesor puso una sola nota,
deja de estarlo: la nota vive en `calificaciones_secundaria.asignatura_id`, y si
el mapeo desaparece el Registro ya no sabe a qué página llevarla. El dato no se
borraría —seguiría en su tabla— pero quedaría huérfano de significado oficial.

Por eso aquí NO se borra, NO se cascadea y NO se mueve nada a otra asignatura.
Solo se responde a una pregunta, y el llamador convierte un "sí" en 409.

QUÉ CUENTA COMO HISTORIA
------------------------
Cuenta el rastro de un hecho ACADÉMICO sobre esa asignatura en ese curso y año:
notas, evaluaciones extra, indicadores, ítems completivos, evaluación interna y
la asistencia TOMADA POR ASIGNATURA.

QUÉ NO CUENTA (y por qué)
-------------------------
  * `asistencias` con `asignatura_id IS NULL` — es la asistencia GENERAL del
    curso, no de una materia. R3.2 §7 lo excluye explícitamente: bloquear por
    ella impediría reconfigurar cursos que solo pasan lista.
  * `asignaciones_profesor`, `horarios`, `permisos_temporales_calificacion`,
    `config_eval_interna` — son CONFIGURACIÓN, no hechos académicos. Un curso
    con profesor asignado y horario puesto, pero sin una sola nota, todavía
    puede corregir su Salida Optativa; es justo el caso de "me equivoqué al
    configurar" que debe seguir siendo reparable.
  * `calificaciones_primaria` y `recuperaciones_primaria` — la Salida Optativa
    solo existe en 4to-6to de Secundaria.

ALCANCE DE LA BÚSQUEDA
----------------------
Siempre acotado al CURSO y, cuando la tabla lo permite, al AÑO ESCOLAR. Dos
tablas de Secundaria (`calificaciones_secundaria`, `evaluaciones_extra_
secundaria`) no llevan `curso_id`: se acotan por los estudiantes del curso, que
es como las lee el propio Registro. Ante la duda el sesgo es CONSERVADOR —
preferimos bloquear de más que permitir que una nota pierda su página.
"""

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


def _ids_estudiantes(db, curso):
    from models import Estudiante
    return [r[0] for r in db.query(Estudiante.id).filter(
        Estudiante.curso_id == curso.id).all()]


def historia_academica(db, curso, asignatura_id: Optional[int]) -> List[dict]:
    """
    Evidencias de actividad académica sobre `asignatura_id` en este curso.

    Devuelve una lista de `{'tabla': str, 'filas': int}`. Lista VACÍA significa
    "no hay historia": recién ahí es seguro remapear o desvincular.

    No escribe, no borra y no modifica nada. Solo cuenta.
    """
    if asignatura_id is None:
        return []

    from models import (Asistencia, Calificacion, CalificacionSecundaria,
                        EvalInternaEstudiante, EvaluacionExtraSecundaria,
                        IndicadorLogro, ItemCompletivo)

    ano_id = getattr(curso, 'ano_escolar_id', None)
    encontrado: List[dict] = []

    def _añadir(nombre, q):
        n = q.count()
        if n:
            encontrado.append({'tabla': nombre, 'filas': n})

    # --- por estudiante del curso (estas tablas no llevan curso_id) ---
    est_ids = _ids_estudiantes(db, curso)
    if est_ids:
        q = db.query(CalificacionSecundaria.id).filter(
            CalificacionSecundaria.asignatura_id == asignatura_id,
            CalificacionSecundaria.estudiante_id.in_(est_ids))
        if ano_id is not None:
            q = q.filter(CalificacionSecundaria.ano_escolar_id == ano_id)
        _añadir('calificaciones_secundaria', q)

        q = db.query(EvaluacionExtraSecundaria.id).filter(
            EvaluacionExtraSecundaria.asignatura_id == asignatura_id,
            EvaluacionExtraSecundaria.estudiante_id.in_(est_ids))
        if ano_id is not None:
            q = q.filter(EvaluacionExtraSecundaria.ano_escolar_id == ano_id)
        _añadir('evaluaciones_extra_secundaria', q)

        q = db.query(Calificacion.id).filter(
            Calificacion.asignatura_id == asignatura_id,
            Calificacion.estudiante_id.in_(est_ids))
        if ano_id is not None:
            q = q.filter(Calificacion.ano_escolar_id == ano_id)
        _añadir('calificaciones', q)

    # --- por curso ---
    q = db.query(IndicadorLogro.id).filter(
        IndicadorLogro.curso_id == curso.id,
        IndicadorLogro.asignatura_id == asignatura_id)
    if ano_id is not None:
        q = q.filter(IndicadorLogro.ano_escolar_id == ano_id)
    _añadir('indicadores_logro', q)

    _añadir('items_completivos', db.query(ItemCompletivo.id).filter(
        ItemCompletivo.curso_id == curso.id,
        ItemCompletivo.asignatura_id == asignatura_id))

    _añadir('eval_interna_estudiante', db.query(EvalInternaEstudiante.id).filter(
        EvalInternaEstudiante.curso_id == curso.id,
        EvalInternaEstudiante.asignatura_id == asignatura_id))

    # Asistencia POR ASIGNATURA. El `isnot(None)` es la regla de §7: la
    # asistencia general del curso (asignatura_id NULL) no es historia de
    # ninguna materia y no debe bloquear nada.
    _añadir('asistencias', db.query(Asistencia.id).filter(
        Asistencia.curso_id == curso.id,
        Asistencia.asignatura_id == asignatura_id,
        Asistencia.asignatura_id.isnot(None)))

    return encontrado


def resumen_historia(evidencias: List[dict]) -> str:
    """Texto corto para el 409: qué se encontró y cuánto."""
    return ", ".join(f"{e['tabla']} ({e['filas']})" for e in evidencias)


def mapeos_con_historia(db, curso, mapeos) -> List[dict]:
    """
    De un conjunto de `CursoComponenteOptativo`, cuáles NO se pueden tocar.

    Devuelve `[{'mapeo': fila, 'componente_codigo': str, 'asignatura_id': int,
    'evidencias': [...]}, ...]`; vacío si ninguno tiene historia.
    """
    bloqueados = []
    for m in mapeos:
        ev = historia_academica(db, curso, m.asignatura_id)
        if ev:
            bloqueados.append({
                'mapeo': m,
                'componente_codigo': m.componente_codigo,
                'asignatura_id': m.asignatura_id,
                'evidencias': ev,
            })
    return bloqueados


MENSAJE_BLOQUEO = (
    "No se puede cambiar la Salida Optativa porque existen datos académicos "
    "asociados a sus componentes."
)

MENSAJE_BLOQUEO_MAPEO = (
    "No se puede quitar este componente porque existen datos académicos "
    "asociados a la asignatura que lo imparte."
)
