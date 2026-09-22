# -*- coding: utf-8 -*-
"""
R4-A1 — LA NOTA FINAL DE UN ÁREA O ASIGNATURA, EN UN SOLO SITIO.

QUÉ RESPONDE
    Una sola pregunta: ¿en qué situación está ESTA área de ESTE estudiante,
    ahora mismo? Devuelve la nota, la fase que la produjo y el estado.

QUÉ NO RESPONDE
    Nada sobre el estudiante. Ni promovido, ni aplazado, ni repitente, ni
    cambio de curso, ni cierre de año. Tampoco si le corresponde una
    Recuperación Especial o una Evaluación Especial: eso depende de CUÁNTAS
    áreas le quedan, y el número de áreas no se ve desde una sola área. Esos
    casos salen marcados con `requiere_contexto_promocion=True` y los
    resolverá R4-A2.

POR QUÉ EXISTE
    La auditoría R4-A0 encontró seis implementaciones independientes de
    «aprobado/reprobado/promovido», con tres cortes distintos y dos bugs del
    mismo tipo: un `0` legítimo tratado como ausencia de nota. Dos boletines
    del mismo estudiante podían imprimir condiciones distintas.

    Este módulo no añade una séptima. Es una capa de LECTURA que delega:

      · Primaria  -> `calculo_primaria.cf_area()` (motor R2/R3, congelado) y
                     los campos ya calculados de `RecuperacionPrimaria`;
      · Secundaria -> `EvaluacionExtraSecundaria.calcular_*_final()` y
                     `reglas_academicas.redondear_calificacion_final`.

    Aquí NO se reimplementa 50/50, ni 30/70, ni CF+CE, ni el promedio de
    competencias. Si alguien cambia una de esas fórmulas, este módulo
    devuelve el resultado nuevo sin tocarse — y hay pruebas que lo exigen.

PUREZA
    Funciones puras: no tocan la base de datos, no escriben nada, no importan
    `models` ni `app`. Reciben los objetos ya cargados. Solo dependen de dos
    módulos que tampoco importan nada del ORM.

EL CERO
    `nota_final = 0` es una nota válida. En todo el módulo se compara con
    `is not None`, nunca con `or` ni con la verdad/falsedad del valor. Ese
    fue exactamente el bug de `boletin_minerd.get_situacion_final` y de la
    cadena `or` del boletín individual.
"""
from calculo_primaria import cf_area, MINIMO_APROBATORIO_PRIMARIA
from reglas_academicas import redondear_calificacion_final

NIVEL_PRIMARIA = 'primaria'
NIVEL_SECUNDARIA = 'secundaria'

# El corte de Secundaria. NO es una fórmula duplicada: es el mismo umbral que
# usa `EvaluacionExtraSecundaria` en su cascada, escrito aquí con nombre para
# no repetir un 70 suelto. Una prueba comprueba que el modelo cambia de
# decisión exactamente en este valor, así que no pueden separarse en silencio.
MINIMO_APROBATORIO_SECUNDARIA = 70


# ═══════════════════ ESTADOS DE UN ÁREA ═══════════════════
#
# PENDIENTE y REPROBADA no se colapsan nunca. Esa distinción es el motivo de
# la fase: hoy `EvaluacionExtraSecundaria.condicion_final` dice 'reprobado'
# aunque todavía falte cargar la completiva, y los consumidores lo imprimen
# como si fuera definitivo.

SIN_CALIFICAR = 'SIN_CALIFICAR'
APROBADA = 'APROBADA'

# Primaria
PENDIENTE_RECUPERACION_FINAL = 'PENDIENTE_RECUPERACION_FINAL'
APROBADA_RECUPERACION_FINAL = 'APROBADA_RECUPERACION_FINAL'
NO_APROBADA_TRAS_RECUPERACION_FINAL = 'NO_APROBADA_TRAS_RECUPERACION_FINAL'
APROBADA_RECUPERACION_ESPECIAL = 'APROBADA_RECUPERACION_ESPECIAL'

# Secundaria
PENDIENTE_COMPLETIVA = 'PENDIENTE_COMPLETIVA'
APROBADA_COMPLETIVA = 'APROBADA_COMPLETIVA'
PENDIENTE_EXTRAORDINARIA = 'PENDIENTE_EXTRAORDINARIA'
APROBADA_EXTRAORDINARIA = 'APROBADA_EXTRAORDINARIA'
NO_APROBADA_TRAS_EXTRAORDINARIA = 'NO_APROBADA_TRAS_EXTRAORDINARIA'
APROBADA_ESPECIAL = 'APROBADA_ESPECIAL'

# Común: solo cuando una fase final concluida permite afirmarlo.
REPROBADA_DEFINITIVA = 'REPROBADA_DEFINITIVA'

ESTADOS = (
    SIN_CALIFICAR, APROBADA,
    PENDIENTE_RECUPERACION_FINAL, APROBADA_RECUPERACION_FINAL,
    NO_APROBADA_TRAS_RECUPERACION_FINAL, APROBADA_RECUPERACION_ESPECIAL,
    PENDIENTE_COMPLETIVA, APROBADA_COMPLETIVA,
    PENDIENTE_EXTRAORDINARIA, APROBADA_EXTRAORDINARIA,
    NO_APROBADA_TRAS_EXTRAORDINARIA, APROBADA_ESPECIAL,
    REPROBADA_DEFINITIVA,
)

# Fases que pueden producir la nota.
FASE_NORMAL = 'normal'
FASE_RECUPERACION_FINAL = 'recuperacion_final'
FASE_RECUPERACION_ESPECIAL = 'recuperacion_especial'
FASE_COMPLETIVA = 'completiva'
FASE_EXTRAORDINARIA = 'extraordinaria'
FASE_ESPECIAL = 'especial'

# Inconsistencias de DATOS que el resolver encuentra pero NO corrige. Se
# informan; no se borra ni se modifica ninguna fila.
INCONSISTENCIA_ESPECIAL_EN_PRIMER_CICLO = 'ESPECIAL_NO_APLICA_EN_1RO_2DO'
INCONSISTENCIA_GRADO_DESCONOCIDO = 'GRADO_DESCONOCIDO_NO_SE_VALIDO_LA_ESPECIAL'

# Grados de Primaria sin Recuperación Especial. En 1.º y 2.º el Registro no
# contempla repitencia académica automática, y la Recuperación Especial es el
# mecanismo ligado a la repitencia condicionada de 3.º-6.º.
GRADOS_SIN_RECUPERACION_ESPECIAL = (1, 2)


def _resultado(nivel, estado, nota_base=None, nota_final=None, fase=None,
               pendiente=False, requiere_contexto_promocion=False,
               area_curricular_codigo=None, inconsistencias=()):
    """El contrato, en un dict plano.

    `nota_base`  — la CF del área antes de cualquier recuperación.
    `nota_final` — la nota que YA decidió una fase concluida. Es `None`
                   mientras el área siga pendiente: un área a la espera de su
                   recuperación no tiene nota final todavía, y devolver el
                   provisional aquí es justo lo que llevó a imprimir «Final»
                   en marzo (R2-A5).
    `requiere_contexto_promocion` — este módulo llegó hasta donde puede
                   llegar mirando UNA sola área; lo que falta depende del
                   conjunto y lo decide R4-A2.
    """
    return {
        'nivel': nivel,
        'nota_base': nota_base,
        'fase': fase,
        'nota_final': nota_final,
        'estado': estado,
        'pendiente': pendiente,
        'requiere_contexto_promocion': requiere_contexto_promocion,
        # Identidad curricular oficial (LE|LEI|LEF|MAT|CS|CN|EA|EF|FIHR) o
        # None si la asignatura no es un bloque del Registro (Música es el
        # caso real). A1 solo la transporta; A2 decidirá con ella qué
        # materias entran en la promoción. Nunca por `nombre` ni `codigo`.
        'area_curricular_codigo': area_curricular_codigo,
        'inconsistencias': tuple(inconsistencias),
    }


# ═══════════════════════════ PRIMARIA ═══════════════════════════

def resolver_nota_primaria(competencias, recuperacion=None, grado_numero=None,
                           area_curricular_codigo=None):
    """Situación de UN área de Primaria.

    `competencias` — las filas `CalificacionPrimaria` del área (C1, C2, C3).
                     La CF sale de `cf_area()`, que ya exige el conjunto
                     oficial completo y los cuatro períodos resueltos. Aquí
                     no se recalcula nada.
    `recuperacion` — la fila `RecuperacionPrimaria` del área, si existe.
    `grado_numero` — 1..6. Solo se usa para validar que la Recuperación
                     Especial corresponde al grado; no cambia ninguna nota.
    """
    inconsistencias = []
    _, cf_red = cf_area(competencias or ())

    if cf_red is None:
        return _resultado(NIVEL_PRIMARIA, SIN_CALIFICAR, pendiente=True,
                          area_curricular_codigo=area_curricular_codigo)

    if cf_red >= MINIMO_APROBATORIO_PRIMARIA:
        return _resultado(NIVEL_PRIMARIA, APROBADA, nota_base=cf_red,
                          nota_final=cf_red, fase=FASE_NORMAL,
                          area_curricular_codigo=area_curricular_codigo)

    rec_final = getattr(recuperacion, 'recuperacion_final', None)
    rec_especial = getattr(recuperacion, 'recuperacion_especial', None)

    # GUARD: la Especial no existe en 1.º y 2.º. Si aparece un dato legacy, se
    # informa y NO se usa; la fila se deja exactamente como está.
    if rec_especial is not None:
        if grado_numero in GRADOS_SIN_RECUPERACION_ESPECIAL:
            inconsistencias.append(INCONSISTENCIA_ESPECIAL_EN_PRIMER_CICLO)
            rec_especial = None
        elif grado_numero is None:
            # Sin el grado no se puede comprobar. Se respeta el dato para no
            # cambiar decisiones, pero queda dicho que no se validó.
            inconsistencias.append(INCONSISTENCIA_GRADO_DESCONOCIDO)

    if rec_final is None:
        return _resultado(NIVEL_PRIMARIA, PENDIENTE_RECUPERACION_FINAL,
                          nota_base=cf_red, pendiente=True,
                          area_curricular_codigo=area_curricular_codigo,
                          inconsistencias=inconsistencias)

    if rec_final >= MINIMO_APROBATORIO_PRIMARIA:
        return _resultado(NIVEL_PRIMARIA, APROBADA_RECUPERACION_FINAL,
                          nota_base=cf_red, nota_final=rec_final,
                          fase=FASE_RECUPERACION_FINAL,
                          area_curricular_codigo=area_curricular_codigo,
                          inconsistencias=inconsistencias)

    # La final no alcanzó. Si la Especial YA está cargada y corresponde al
    # grado, ella decide. A1 NO juzga si debió habilitarse: eso mira el
    # conjunto de áreas y es cosa de A2.
    if rec_especial is not None:
        aprobo = rec_especial >= MINIMO_APROBATORIO_PRIMARIA
        return _resultado(
            NIVEL_PRIMARIA,
            APROBADA_RECUPERACION_ESPECIAL if aprobo else REPROBADA_DEFINITIVA,
            nota_base=cf_red, nota_final=rec_especial,
            fase=FASE_RECUPERACION_ESPECIAL,
            area_curricular_codigo=area_curricular_codigo,
            inconsistencias=inconsistencias)

    # Hasta aquí llega una sola área. Que esto acabe en Especial o en
    # repitencia depende de cuántas áreas más estén así.
    return _resultado(NIVEL_PRIMARIA, NO_APROBADA_TRAS_RECUPERACION_FINAL,
                      nota_base=cf_red, nota_final=rec_final,
                      fase=FASE_RECUPERACION_FINAL,
                      requiere_contexto_promocion=True,
                      area_curricular_codigo=area_curricular_codigo,
                      inconsistencias=inconsistencias)


# ══════════════════════════ SECUNDARIA ══════════════════════════

def resolver_nota_secundaria(evaluacion, area_curricular_codigo=None):
    """Situación de UNA asignatura de Secundaria.

    `evaluacion` — la fila `EvaluacionExtraSecundaria`. Todas las notas salen
                   de sus propios métodos: `calcular_completiva_final()`,
                   `calcular_extraordinaria_final()` y
                   `calcular_especial_final()`. Aquí no hay ni un 0.5 ni un
                   0.3 escritos.

    NO se lee `evaluacion.condicion_final`: ese campo dice 'reprobado'
    también cuando falta cargar una fase, y ahí está precisamente la
    confusión que R4 tiene que deshacer.
    """
    cf_original = getattr(evaluacion, 'cf_original', None)
    if cf_original is None:
        return _resultado(NIVEL_SECUNDARIA, SIN_CALIFICAR, pendiente=True,
                          area_curricular_codigo=area_curricular_codigo)

    cf_oficial = redondear_calificacion_final(cf_original)
    if cf_oficial >= MINIMO_APROBATORIO_SECUNDARIA:
        return _resultado(NIVEL_SECUNDARIA, APROBADA, nota_base=cf_oficial,
                          nota_final=cf_oficial, fase=FASE_NORMAL,
                          area_curricular_codigo=area_curricular_codigo)

    # ── Completiva ──
    if getattr(evaluacion, 'cec', None) is None:
        return _resultado(NIVEL_SECUNDARIA, PENDIENTE_COMPLETIVA,
                          nota_base=cf_oficial, pendiente=True,
                          area_curricular_codigo=area_curricular_codigo)

    completiva = evaluacion.calcular_completiva_final()
    if completiva is not None and completiva >= MINIMO_APROBATORIO_SECUNDARIA:
        return _resultado(NIVEL_SECUNDARIA, APROBADA_COMPLETIVA,
                          nota_base=cf_oficial, nota_final=completiva,
                          fase=FASE_COMPLETIVA,
                          area_curricular_codigo=area_curricular_codigo)

    # ── Extraordinaria ──
    if getattr(evaluacion, 'ceex', None) is None:
        return _resultado(NIVEL_SECUNDARIA, PENDIENTE_EXTRAORDINARIA,
                          nota_base=cf_oficial, nota_final=None,
                          pendiente=True,
                          area_curricular_codigo=area_curricular_codigo)

    extraordinaria = evaluacion.calcular_extraordinaria_final()
    if (extraordinaria is not None
            and extraordinaria >= MINIMO_APROBATORIO_SECUNDARIA):
        return _resultado(NIVEL_SECUNDARIA, APROBADA_EXTRAORDINARIA,
                          nota_base=cf_oficial, nota_final=extraordinaria,
                          fase=FASE_EXTRAORDINARIA,
                          area_curricular_codigo=area_curricular_codigo)

    # ── Especial, SOLO si ya está cargada ──
    #
    # A1 no decide si al estudiante le correspondía una Especial: eso depende
    # de cuántas asignaturas no aprobó, y desde una asignatura no se ve.
    if getattr(evaluacion, 'ce', None) is not None:
        especial = evaluacion.calcular_especial_final()
        if especial is not None:
            aprobo = especial >= MINIMO_APROBATORIO_SECUNDARIA
            return _resultado(
                NIVEL_SECUNDARIA,
                APROBADA_ESPECIAL if aprobo else REPROBADA_DEFINITIVA,
                nota_base=cf_oficial, nota_final=especial,
                fase=FASE_ESPECIAL,
                area_curricular_codigo=area_curricular_codigo)

    return _resultado(NIVEL_SECUNDARIA, NO_APROBADA_TRAS_EXTRAORDINARIA,
                      nota_base=cf_oficial, nota_final=extraordinaria,
                      fase=FASE_EXTRAORDINARIA,
                      requiere_contexto_promocion=True,
                      area_curricular_codigo=area_curricular_codigo)
