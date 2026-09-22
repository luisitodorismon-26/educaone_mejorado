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
INCONSISTENCIA_GRADO_DESCONOCIDO = 'GRADO_DESCONOCIDO_ESPECIAL_NO_APLICADA'
INCONSISTENCIA_CF_DIVERGENTE = 'CF_SECUNDARIA_DIVERGENTE'

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
    # `or` ni siquiera aqui: esto es una lista y no una nota, asi que no
    # es el bug que persigue el modulo, pero el patron esta prohibido y
    # dejarlo obliga a cada revision a pararse a comprobar que es inocuo.
    _, cf_red = cf_area(competencias if competencias is not None else ())

    if cf_red is None:
        return _resultado(NIVEL_PRIMARIA, SIN_CALIFICAR, pendiente=True,
                          area_curricular_codigo=area_curricular_codigo)

    if cf_red >= MINIMO_APROBATORIO_PRIMARIA:
        return _resultado(NIVEL_PRIMARIA, APROBADA, nota_base=cf_red,
                          nota_final=cf_red, fase=FASE_NORMAL,
                          area_curricular_codigo=area_curricular_codigo)

    rec_final = getattr(recuperacion, 'recuperacion_final', None)
    rec_especial = getattr(recuperacion, 'recuperacion_especial', None)

    # GUARD: la Especial no existe en 1.º y 2.º, y solo se usa cuando se puede
    # DEMOSTRAR que el grado la admite. En los dos casos la fila se deja
    # exactamente como está: se informa, no se corrige.
    if rec_especial is not None:
        if grado_numero in GRADOS_SIN_RECUPERACION_ESPECIAL:
            inconsistencias.append(INCONSISTENCIA_ESPECIAL_EN_PRIMER_CICLO)
            rec_especial = None
        elif grado_numero is None:
            # FAIL-CLOSED (A1.1). Antes se usaba el dato y solo se avisaba,
            # con lo que un caller que olvidara pasar el grado podía aprobar
            # a un alumno de 1.º o 2.º mediante una fase que quizá no le
            # corresponde. Sin grado no se puede demostrar que aplique, así
            # que no se aplica. El área se queda con el resultado de la
            # Recuperación Final, que sí es válido en los seis grados.
            inconsistencias.append(INCONSISTENCIA_GRADO_DESCONOCIDO)
            rec_especial = None

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

def resolver_nota_secundaria(evaluacion=None, cf_original=None,
                             area_curricular_codigo=None):
    """Situación de UNA asignatura de Secundaria.

    `evaluacion`  — la fila `EvaluacionExtraSecundaria`, si existe.
    `cf_original` — la CF que el consumidor ya calculó por su cuenta. Puede
                    ser la exacta o la oficial redondeada; da igual, porque
                    aquí se redondea antes de decidir.

    POR QUÉ SE ACEPTAN LAS DOS FUENTES
        Que exista CF no implica que exista fila extra. El consumidor real,
        `_construir_datos_boletin_secundaria`, calcula `cf` por su cuenta y
        toma la evaluación aparte con `extras_idx.get(asig.id)`, que devuelve
        None cuando no hay fila. Datos legacy, importaciones, fixtures y
        reparaciones producen lo mismo. Un motor canónico que exigiera la
        fila diría SIN_CALIFICAR de un estudiante con 85, y no se podría
        conectar en A3.

    CUÁL MANDA SI HAY DOS
        La de `evaluacion`. No por preferencia: `calcular_completiva_final()`
        y sus hermanas leen `self.cf_original`, así que las fases extra YA
        están calculadas contra esa base. Usar otra CF para el umbral y esa
        para las fases daría un resultado mezclado de dos bases distintas, y
        forzar las fases a otra base exigiría reimplementar las fórmulas —que
        es justo lo que R4 viene a evitar—. La discrepancia no se esconde:
        sale en `inconsistencias` para que A2/A3 pueda bloquear o avisar.

    NO se lee `evaluacion.condicion_final`: ese campo dice 'reprobado'
    también cuando falta cargar una fase, y ahí está precisamente la
    confusión que R4 tiene que deshacer.
    """
    inconsistencias = []
    cf_evaluacion = getattr(evaluacion, 'cf_original', None)

    if cf_evaluacion is not None and cf_original is not None:
        # La comparación es sobre la CF OFICIAL, no sobre el float. Un
        # consumidor puede pasar legítimamente la redondeada (85) mientras la
        # fila guarda la exacta (84.6): eso es la misma CF, no una
        # divergencia. Solo se avisa cuando el número oficial difiere.
        if (redondear_calificacion_final(cf_evaluacion)
                != redondear_calificacion_final(cf_original)):
            inconsistencias.append(INCONSISTENCIA_CF_DIVERGENTE)

    cf_base = cf_evaluacion if cf_evaluacion is not None else cf_original

    if cf_base is None:
        return _resultado(NIVEL_SECUNDARIA, SIN_CALIFICAR, pendiente=True,
                          area_curricular_codigo=area_curricular_codigo,
                          inconsistencias=inconsistencias)

    cf_original = cf_base
    cf_oficial = redondear_calificacion_final(cf_original)
    if cf_oficial >= MINIMO_APROBATORIO_SECUNDARIA:
        return _resultado(NIVEL_SECUNDARIA, APROBADA, nota_base=cf_oficial,
                          nota_final=cf_oficial, fase=FASE_NORMAL,
                          area_curricular_codigo=area_curricular_codigo,
                          inconsistencias=inconsistencias)

    # ── Completiva ──
    if getattr(evaluacion, 'cec', None) is None:
        return _resultado(NIVEL_SECUNDARIA, PENDIENTE_COMPLETIVA,
                          nota_base=cf_oficial, pendiente=True,
                          area_curricular_codigo=area_curricular_codigo,
                          inconsistencias=inconsistencias)

    completiva = evaluacion.calcular_completiva_final()
    if completiva is not None and completiva >= MINIMO_APROBATORIO_SECUNDARIA:
        return _resultado(NIVEL_SECUNDARIA, APROBADA_COMPLETIVA,
                          nota_base=cf_oficial, nota_final=completiva,
                          fase=FASE_COMPLETIVA,
                          area_curricular_codigo=area_curricular_codigo,
                          inconsistencias=inconsistencias)

    # ── Extraordinaria ──
    if getattr(evaluacion, 'ceex', None) is None:
        return _resultado(NIVEL_SECUNDARIA, PENDIENTE_EXTRAORDINARIA,
                          nota_base=cf_oficial, nota_final=None,
                          pendiente=True,
                          area_curricular_codigo=area_curricular_codigo,
                          inconsistencias=inconsistencias)

    extraordinaria = evaluacion.calcular_extraordinaria_final()
    if (extraordinaria is not None
            and extraordinaria >= MINIMO_APROBATORIO_SECUNDARIA):
        return _resultado(NIVEL_SECUNDARIA, APROBADA_EXTRAORDINARIA,
                          nota_base=cf_oficial, nota_final=extraordinaria,
                          fase=FASE_EXTRAORDINARIA,
                          area_curricular_codigo=area_curricular_codigo,
                          inconsistencias=inconsistencias)

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
                area_curricular_codigo=area_curricular_codigo,
                          inconsistencias=inconsistencias)

    return _resultado(NIVEL_SECUNDARIA, NO_APROBADA_TRAS_EXTRAORDINARIA,
                      nota_base=cf_oficial, nota_final=extraordinaria,
                      fase=FASE_EXTRAORDINARIA,
                      requiere_contexto_promocion=True,
                      area_curricular_codigo=area_curricular_codigo,
                          inconsistencias=inconsistencias)
