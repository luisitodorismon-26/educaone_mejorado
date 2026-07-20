"""
════════════════════════════════════════════════════════════════════════
MOTOR DE CÁLCULO — NIVEL PRIMARIO (v2.13.44)
════════════════════════════════════════════════════════════════════════

Carril SEPARADO de secundaria. No importa ni depende de la lógica de
CalificacionSecundaria / EvaluacionExtraSecundaria.

Reglas oficiales (Registro de Grado, Nivel Primario, MINERD 2023-2024):
 - 3 competencias por área (C1, C2, C3); Inglés puede tener 2.
 - Cada competencia: P1-P4 con RP1-RP4. Valor del período = max(P, RP).
 - CF de competencia = promedio de los períodos EVALUADOS (regla NE, pág. 85).
 - CF del área = promedio de las competencias evaluadas del área.
 - Aprobar un área = 65 puntos o más (pág. 39).
 - Recuperación Final (área < 65): suma complementaria sobre la CF del área,
   máx = 100 - CF; aprueba con >= 65 (pág. 39 y 85).
 - Fin de año (pág. 39):
     * 4+ áreas reprobadas tras recuperación final -> repite el grado.
     * 1 a 3 áreas -> repitente condicional -> Recuperación Especial
       (primeros 15 días del año siguiente).
 - Cuantitativo solo para 3ro-6to.

Corte oficial: 65.
"""

MINIMO_APROBATORIO_PRIMARIA = 65


def cf_competencia(calif, minimo_periodos=1):
    """CF de UNA competencia (objeto CalificacionPrimaria).
    Promedio de los períodos evaluados (NE = período sin valor)."""
    if calif is None:
        return None
    return calif.calcular_final(minimo_periodos=minimo_periodos)


def cf_area(competencias):
    """CF del área = promedio de las CF de sus competencias evaluadas.

    `competencias` = lista de objetos CalificacionPrimaria (1 por cada C1/C2/C3
    del área). Se promedian las que tengan CF (al menos un período evaluado).
    Devuelve (cf_exacto, cf_redondeado) o (None, None) si no hay ninguna.
    """
    finales = []
    for c in competencias:
        f = cf_competencia(c)
        if f is not None:
            finales.append(f)
    if not finales:
        return None, None
    cf_exacto = sum(finales) / len(finales)
    return round(cf_exacto, 2), round(cf_exacto)


def calcular_recuperacion_final(cf_area_redondeado, puntos_recuperacion):
    """Recuperación final del área: suma complementaria.

    puntos_recuperacion es COMPLEMENTARIO (se suma a la CF del área). El máximo
    permitido es 100 - CF, para que el total no pase de 100.
    Devuelve dict con validación y resultado.
    """
    if cf_area_redondeado is None:
        return {'valido': False, 'error': 'El área no tiene CF calculada aún.'}
    maximo = 100 - cf_area_redondeado
    if puntos_recuperacion is None:
        return {'valido': False, 'error': 'Indique los puntos de recuperación.'}
    if puntos_recuperacion < 0 or puntos_recuperacion > maximo:
        return {
            'valido': False,
            'error': (f'Puntos inválidos: la recuperación es COMPLEMENTARIA y se suma '
                      f'a la CF del área ({cf_area_redondeado}). Máximo permitido: '
                      f'{maximo} (para no pasar de 100).'),
            'maximo': maximo,
        }
    resultado = cf_area_redondeado + puntos_recuperacion
    return {
        'valido': True,
        'recuperacion_final': resultado,
        'aprobado': resultado >= MINIMO_APROBATORIO_PRIMARIA,
        'maximo': maximo,
    }


def situacion_area(cf_area_redondeado, recuperacion_final=None, recuperacion_especial=None):
    """Situación de UN área: aprobado / recuperacion_pendiente / reprobado.

    - CF >= 65 -> aprobado directo.
    - CF < 65 sin recuperación cargada -> recuperacion_pendiente.
    - CF < 65 con recuperación final -> aprobado o sigue el flujo.
    - v2.14.1: si tras la final sigue < 65 y hay recuperación ESPECIAL cargada,
      la especial decide (aprobado_recuperacion o reprobado definitivo).
      Parámetro opcional: las llamadas existentes no cambian.
    """
    if cf_area_redondeado is None:
        return {'estado': 'sin_notas', 'nota_final': None}
    if cf_area_redondeado >= MINIMO_APROBATORIO_PRIMARIA:
        return {'estado': 'aprobado', 'nota_final': cf_area_redondeado}
    if recuperacion_final is None:
        return {'estado': 'recuperacion_pendiente', 'nota_final': cf_area_redondeado}
    if recuperacion_final >= MINIMO_APROBATORIO_PRIMARIA:
        return {'estado': 'aprobado_recuperacion', 'nota_final': recuperacion_final}
    # Reprobó la final: si hay especial cargada, ella decide
    if recuperacion_especial is not None:
        if recuperacion_especial >= MINIMO_APROBATORIO_PRIMARIA:
            return {'estado': 'aprobado_recuperacion', 'nota_final': recuperacion_especial}
        return {'estado': 'reprobado', 'nota_final': recuperacion_especial}
    return {'estado': 'reprobado', 'nota_final': recuperacion_final}


def condicion_final_estudiante(situaciones_areas):
    """Decisión de fin de año del estudiante según sus áreas (pág. 39).

    `situaciones_areas` = lista de resultados de situacion_area() (una por área).
    Cuenta las áreas reprobadas DESPUÉS de la recuperación final:
      - 0 reprobadas -> promovido.
      - 1 a 3 reprobadas -> repitente condicional (va a recuperación especial).
      - 4 o más -> repite el grado.
    Si hay áreas con recuperación pendiente, la condición aún no es definitiva.
    """
    pendientes = [s for s in situaciones_areas if s['estado'] == 'recuperacion_pendiente']
    reprobadas = [s for s in situaciones_areas if s['estado'] == 'reprobado']
    n_rep = len(reprobadas)

    if pendientes:
        return {
            'condicion': 'en_proceso',
            'detalle': f'{len(pendientes)} área(s) en recuperación final pendiente.',
            'areas_reprobadas': n_rep,
            'areas_pendientes': len(pendientes),
        }
    if n_rep == 0:
        return {'condicion': 'promovido', 'detalle': 'Promovido/a.', 'areas_reprobadas': 0, 'areas_pendientes': 0}
    if n_rep <= 3:
        return {
            'condicion': 'repitente_condicional',
            'detalle': f'Repite condicional: {n_rep} área(s) aplazada(s). Va a recuperación especial.',
            'areas_reprobadas': n_rep,
            'areas_pendientes': 0,
        }
    return {
        'condicion': 'repite',
        'detalle': f'Repite el grado: {n_rep} áreas reprobadas (4 o más).',
        'areas_reprobadas': n_rep,
        'areas_pendientes': 0,
    }
