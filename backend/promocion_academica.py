# -*- coding: utf-8 -*-
"""
R4-A2 — LA SITUACIÓN ACADÉMICA DE UN ESTUDIANTE, EN UN SOLO SITIO.

QUÉ RESPONDE
    Una sola pregunta: con estas áreas ya resueltas por R4-A1, ¿en qué
    situación queda el estudiante? Promovido, aplazado, reprobado, o todavía
    en proceso.

QUÉ NO HACE
    No mueve a nadie de curso, no toca `Estudiante`, no escribe historial, no
    cierra el año y no recalcula ninguna nota. Consume los resultados de
    `resultado_academico` y no vuelve a mirar CF, recuperaciones, completivas
    ni extraordinarias.

POR QUÉ EXISTE
    La auditoría R4-A0 encontró seis reglas de promoción independientes, con
    tres cortes distintos, y ninguna miraba el grado: podían declarar «repite»
    a un alumno de 1.º, donde la norma dice que la repitencia no se contempla.
    Cuatro de las seis ni siquiera leían las calificaciones de Primaria.

    Este módulo no añade una séptima: es la única, y es pura.

LO QUE A1 NO PODÍA SABER
    A1 mira UN área. Al llegar a una Recuperación Especial ya cargada, la lee
    —no tiene forma de saber cuántas áreas más fallaron—. A2 sí lo sabe, y
    por eso aquí vive la elegibilidad: con cuatro o más áreas caídas tras la
    Recuperación Final, una Especial cargada NO rescata a nadie, por mucho
    que A1 la haya leído. La regla agregada manda sobre la individual.

FAIL-CLOSED
    Ante una duda, `EN_PROCESO`. Nunca se promueve por omisión: un área que
    falta no es un área aprobada, y un dato que no llegó no es un dato
    favorable. Los motivos concretos salen en `bloqueos`.
"""
from collections import Counter

import resultado_academico as RA

NIVEL_PRIMARIA = RA.NIVEL_PRIMARIA
NIVEL_SECUNDARIA = RA.NIVEL_SECUNDARIA

# ═══════════════════ CONDICIONES ═══════════════════
#
# Vocabulario único. Los textos que vea el usuario se traducirán después;
# aquí no hay «repitente condicional» ni «promovido condicional» como fuentes
# paralelas, que es como empezaron las seis reglas de A0.

EN_PROCESO = 'EN_PROCESO'
PROMOVIDO = 'PROMOVIDO'
APLAZADO = 'APLAZADO'          # queda un proceso especial normativo por delante
REPROBADO = 'REPROBADO'

CONDICIONES = (EN_PROCESO, PROMOVIDO, APLAZADO, REPROBADO)
CONDICIONES_DEFINITIVAS = (PROMOVIDO, REPROBADO)

# ═══════════════════ BLOQUEOS ═══════════════════
# Impiden certificar. Cada uno dice exactamente qué falta.

BLOQUEO_NIVEL_NO_RECONOCIDO = 'NIVEL_NO_RECONOCIDO'
BLOQUEO_GRADO_NO_DECLARADO = 'GRADO_NO_DECLARADO'
BLOQUEO_CURRICULO_NO_DECLARADO = 'CURRICULO_OFICIAL_NO_DECLARADO'
BLOQUEO_CURRICULO_INCOMPLETO = 'CURRICULO_OFICIAL_INCOMPLETO'
BLOQUEO_SIN_CURRICULO_OFICIAL = 'SIN_MATERIAS_OFICIALES_ESPERADAS'
BLOQUEO_DATOS_INCONSISTENTES = 'DATOS_ACADEMICOS_INCONSISTENTES'
BLOQUEO_AREAS_PENDIENTES = 'AREAS_OFICIALES_PENDIENTES'
BLOQUEO_ALFABETIZACION_NO_INFORMADA = 'ALFABETIZACION_3RO_NO_INFORMADA'
BLOQUEO_ASISTENCIA_NO_EVALUADA = 'ASISTENCIA_NO_EVALUADA'
BLOQUEO_REVISION_ASISTENCIA = 'REVISION_ASISTENCIA_REQUERIDA'
BLOQUEO_REPROBAR_ASIGNATURAS_SIN_NORMA = (
    'DECISION_REPROBAR_ASIGNATURAS_SIN_SOPORTE_NORMATIVO')

# ═══════════════════ INCONSISTENCIAS ═══════════════════
# Datos que no encajan. Se informan; no se corrigen ni se borran.

INC_ESPECIAL_NO_ELEGIBLE_PRIMARIA = 'RECUPERACION_ESPECIAL_NO_ELEGIBLE_4_MAS'
INC_ESPECIAL_NO_ELEGIBLE_SECUNDARIA = 'EVALUACION_ESPECIAL_NO_ELEGIBLE_3_MAS'
INC_EXCEPCION_SEGUNDO_FUERA_DE_LUGAR = 'EXCEPCION_SEGUNDO_NO_APLICA_A_ESTE_GRADO'
INC_ALFABETIZACION_FUERA_DE_TERCERO = 'ALFABETIZACION_SOLO_APLICA_EN_3RO'

# Estas dos NO frenan la certificacion. Acompanan a un REPROBADO que ya
# es definitivo por el numero de areas caidas: describen que en la base
# hay notas de un proceso especial al que el estudiante no tenia derecho.
# Bloquear aqui dejaria sin certificar una decision que esos datos no
# pueden cambiar; lo que corresponde es decidir y decirlo.
INCONSISTENCIAS_INFORMATIVAS = (INC_ESPECIAL_NO_ELEGIBLE_PRIMARIA,
                                INC_ESPECIAL_NO_ELEGIBLE_SECUNDARIA)

# ═══════════════════ ADVERTENCIAS ═══════════════════
# No impiden decidir; acompañan a la decisión.

ADV_PROMOCION_ASISTIDA = 'PROMOCION_ASISTIDA'
ADV_TITULACION_PENDIENTE = 'REQUIERE_PROCESO_DE_TITULACION_PRUEBAS_NACIONALES'
ADV_ASISTENCIA_NO_REVISADA = 'ASISTENCIA_NO_REVISADA_CAUSA_ACADEMICA_SUFICIENTE'
ADV_ALFABETIZACION_NO_INFORMADA = 'ALFABETIZACION_NO_INFORMADA_CAUSA_SUFICIENTE'

# ═══════════════════ MOTIVOS ═══════════════════

MOTIVO_TODAS_APROBADAS = 'TODAS_LAS_AREAS_OFICIALES_APROBADAS'
MOTIVO_SIN_REPITENCIA_PRIMER_CICLO = 'PRIMER_CICLO_SIN_REPITENCIA'
MOTIVO_ELEGIBLE_ESPECIAL = 'ELEGIBLE_PARA_PROCESO_ESPECIAL'
MOTIVO_ESPECIAL_SUPERADA = 'PROCESO_ESPECIAL_SUPERADO'
MOTIVO_ESPECIAL_NO_SUPERADA = 'PROCESO_ESPECIAL_NO_SUPERADO'
MOTIVO_DEMASIADAS_NO_APROBADAS = 'DEMASIADAS_AREAS_NO_APROBADAS'
MOTIVO_ALFABETIZACION_NO_LOGRADA = 'ALFABETIZACION_INICIAL_NO_LOGRADA'
MOTIVO_EXCEPCION_SEGUNDO = 'REPETICION_EXCEPCIONAL_SEGUNDO_DECISION_COLEGIADA'
MOTIVO_DECISION_ASISTENCIA = 'DECISION_DEL_EQUIPO_DE_GESTION_POR_ASISTENCIA'
MOTIVO_PROCESO_ABIERTO = 'PROCESO_ACADEMICO_ABIERTO'

# ═══════════════════ UMBRALES NORMATIVOS ═══════════════════

# Primaria (Registro de Grado, Ordenanza 04-2023): «El estudiante que luego
# de la recuperación final no apruebe cuatro o más asignaturas, repite el
# grado»; «hasta tres áreas curriculares, podrá participar en la recuperación
# especial».
MAX_AREAS_PARA_ESPECIAL_PRIMARIA = 3

# Secundaria: hasta dos asignaturas pendientes tras la Extraordinaria son
# elegibles para Evaluación Especial; tres o más, repitencia.
MAX_ASIGNATURAS_PARA_ESPECIAL_SECUNDARIA = 2

# Grados sin repitencia automática (Registro 1.º y 2.º, hoja 38: «En los
# grados de 1º y 2º del Nivel Primario, no se contempla la repitencia»).
GRADOS_SIN_REPITENCIA = (1, 2)

# El único grado donde cabe la repetición excepcional por decisión colegiada.
GRADO_EXCEPCION_COLEGIADA = 2

GRADO_ALFABETIZACION_INICIAL = 3

# Ordenanza 04-2023: mínimo 80% de asistencia. Pasar de ese 20% de ausencias
# NO justificadas no reprueba por sí solo: obliga a que el equipo de gestión
# analice el caso.
MAX_AUSENCIAS_NO_JUSTIFICADAS = 20

# Decisiones humanas posibles ante el exceso de ausencias.
ASISTENCIA_PERMITIR_APROBACION = 'PERMITIR_APROBACION'
ASISTENCIA_REPETIR_GRADO = 'REPETIR_GRADO'
ASISTENCIA_REPROBAR_ASIGNATURAS = 'REPROBAR_ASIGNATURAS'
DECISIONES_ASISTENCIA = (ASISTENCIA_PERMITIR_APROBACION,
                         ASISTENCIA_REPETIR_GRADO,
                         ASISTENCIA_REPROBAR_ASIGNATURAS)

# ── Estados de A1, agrupados por lo que significan para el estudiante ──

ESTADOS_APROBADOS = (
    RA.APROBADA,
    RA.APROBADA_RECUPERACION_FINAL, RA.APROBADA_RECUPERACION_ESPECIAL,
    RA.APROBADA_COMPLETIVA, RA.APROBADA_EXTRAORDINARIA, RA.APROBADA_ESPECIAL,
)

# Un área en cualquiera de estos estados impide decidir: falta información,
# no sobra. Una ausencia NO es una reprobación.
ESTADOS_PENDIENTES = (
    RA.SIN_CALIFICAR,
    RA.PENDIENTE_RECUPERACION_FINAL,
    RA.PENDIENTE_COMPLETIVA,
    RA.PENDIENTE_EXTRAORDINARIA,
)


def _resultado(nivel, grado_numero, condicion, motivo, conteos, codigos,
               es_definitiva=None, requiere_recuperacion_especial=False,
               requiere_evaluacion_especial=False,
               bloqueos=(), advertencias=(), inconsistencias=(),
               codigos_no_oficiales=()):
    """El contrato de salida. Mismas claves siempre."""
    if es_definitiva is None:
        es_definitiva = condicion in CONDICIONES_DEFINITIVAS
    if bloqueos:
        # Un bloqueo es exactamente eso: no se certifica nada.
        es_definitiva = False
    return {
        'nivel': nivel,
        'grado_numero': grado_numero,
        'condicion': condicion,
        'es_definitiva': es_definitiva,
        'motivo': motivo,

        'total_oficiales': conteos['total'],
        'aprobadas': conteos['aprobadas'],
        'pendientes': conteos['pendientes'],
        'no_aprobadas': conteos['no_aprobadas'],

        'codigos_aprobados': tuple(codigos['aprobados']),
        'codigos_pendientes': tuple(codigos['pendientes']),
        'codigos_no_aprobados': tuple(codigos['no_aprobados']),
        # Materias internas del colegio (Música es el caso real): se listan
        # para que se vea que existen, pero no participan en la decisión
        # oficial y jamás pueden hacer repetir a nadie.
        'codigos_no_oficiales': tuple(codigos_no_oficiales),

        'requiere_recuperacion_especial': requiere_recuperacion_especial,
        'requiere_evaluacion_especial': requiere_evaluacion_especial,

        'bloqueos': tuple(bloqueos),
        'advertencias': tuple(advertencias),
        'inconsistencias': tuple(inconsistencias),
    }


def _vacio():
    return ({'total': 0, 'aprobadas': 0, 'pendientes': 0, 'no_aprobadas': 0},
            {'aprobados': (), 'pendientes': (), 'no_aprobados': ()})


def _codigo(resultado):
    return resultado.get('area_curricular_codigo')


def resolver_situacion_estudiante(nivel, grado_numero, resultados,
                                  codigos_oficiales_esperados=None,
                                  contexto=None):
    """Situación académica global de UN estudiante.

    `nivel`        — 'primaria' | 'secundaria'.
    `grado_numero` — 1..6. Hace falta siempre: la norma es distinta por grado
                     y sin él no se puede decidir nada.
    `resultados`   — la lista de salidas de `resolver_nota_primaria` /
                     `resolver_nota_secundaria`, una por asignatura.
    `codigos_oficiales_esperados` — los bloques curriculares que el grado DEBE
                     tener. Se compara como multiconjunto, no como set.
    `contexto`     — datos que no salen de las notas y que nadie puede
                     inferir: alfabetización inicial, porcentaje de ausencias
                     no justificadas, decisiones del equipo de gestión.

    Nada de lo recibido se modifica.
    """
    contexto = dict(contexto) if contexto else {}
    resultados = list(resultados) if resultados else []

    bloqueos, advertencias, inconsistencias = [], [], []
    conteos, codigos = _vacio()

    # ── GATE 1 · nivel y grado ──
    if nivel not in (NIVEL_PRIMARIA, NIVEL_SECUNDARIA):
        return _resultado(nivel, grado_numero, EN_PROCESO, MOTIVO_PROCESO_ABIERTO,
                          conteos, codigos,
                          bloqueos=[BLOQUEO_NIVEL_NO_RECONOCIDO])
    if grado_numero is None:
        # Sin grado no se puede aplicar ninguna regla: 1.º y 6.º no comparten
        # ni la repitencia ni la alfabetización ni el número de áreas.
        return _resultado(nivel, grado_numero, EN_PROCESO, MOTIVO_PROCESO_ABIERTO,
                          conteos, codigos,
                          bloqueos=[BLOQUEO_GRADO_NO_DECLARADO])

    # ── GATE 2 · separar currículo oficial del interno ──
    oficiales = [r for r in resultados if _codigo(r) is not None]
    no_oficiales = tuple(
        r.get('area_curricular_codigo') for r in resultados
        if _codigo(r) is None)
    # Las internas no tienen código; se cuentan, no se nombran por texto.
    codigos_no_oficiales = tuple(['(sin codigo oficial)'] * len(no_oficiales))

    presentes = Counter(_codigo(r) for r in oficiales)

    # ── GATE 3 · el currículo esperado tiene que venir declarado ──
    if codigos_oficiales_esperados is None:
        return _resultado(nivel, grado_numero, EN_PROCESO, MOTIVO_PROCESO_ABIERTO,
                          conteos, codigos,
                          bloqueos=[BLOQUEO_CURRICULO_NO_DECLARADO],
                          codigos_no_oficiales=codigos_no_oficiales)

    esperados = Counter(codigos_oficiales_esperados)
    if not esperados:
        return _resultado(nivel, grado_numero, EN_PROCESO, MOTIVO_PROCESO_ABIERTO,
                          conteos, codigos,
                          bloqueos=[BLOQUEO_SIN_CURRICULO_OFICIAL],
                          codigos_no_oficiales=codigos_no_oficiales)

    # ── GATE 4 · completitud del currículo ──
    #
    # Evaluar «las materias que aparecieron» fue uno de los bugs originales:
    # un estudiante con dos áreas cargadas de ocho salía promovido. Falta una
    # comparación de multiconjuntos, no de conjuntos: un grado podría declarar
    # dos veces el mismo bloque y ambas tienen que estar.
    faltan = esperados - presentes
    if faltan:
        bloqueos.append(BLOQUEO_CURRICULO_INCOMPLETO)

    # A partir de aquí solo cuentan las oficiales ESPERADAS. Una oficial de
    # más no hace repetir a nadie, pero se deja ver como inconsistencia.
    sobran = presentes - esperados
    if sobran:
        inconsistencias.append('AREAS_OFICIALES_NO_ESPERADAS')

    # ── Clasificar ──
    aprobados, pendientes_cod, no_aprobados = [], [], []
    por_area_inconsistente = False
    for r in oficiales:
        cod = _codigo(r)
        if r.get('inconsistencias'):
            por_area_inconsistente = True
            for inc in r['inconsistencias']:
                if inc not in inconsistencias:
                    inconsistencias.append(inc)
        estado = r.get('estado')
        if estado in ESTADOS_APROBADOS:
            aprobados.append(cod)
        elif estado in ESTADOS_PENDIENTES:
            pendientes_cod.append(cod)
        else:
            no_aprobados.append(cod)

    conteos = {
        'total': len(oficiales),
        'aprobadas': len(aprobados),
        'pendientes': len(pendientes_cod),
        'no_aprobadas': len(no_aprobados),
    }
    codigos = {'aprobados': aprobados, 'pendientes': pendientes_cod,
               'no_aprobados': no_aprobados}

    def salida(condicion, motivo, **extra):
        return _resultado(nivel, grado_numero, condicion, motivo, conteos,
                          codigos, bloqueos=bloqueos,
                          advertencias=advertencias,
                          inconsistencias=inconsistencias,
                          codigos_no_oficiales=codigos_no_oficiales, **extra)

    # ── GATE 5 · inconsistencias de A1 ──
    #
    # Fail-closed: si un área trae un dato que no encaja —una Especial donde
    # no aplica, una fase sin CF base, dos CF distintas—, no se certifica
    # nada hasta que alguien lo mire.
    if por_area_inconsistente:
        bloqueos.append(BLOQUEO_DATOS_INCONSISTENTES)

    # ── GATE 6 · áreas sin resolver ──
    if pendientes_cod:
        bloqueos.append(BLOQUEO_AREAS_PENDIENTES)

    if bloqueos:
        return salida(EN_PROCESO, MOTIVO_PROCESO_ABIERTO)

    # ── GATE 7 · reglas por nivel y grado ──
    #
    # Las reglas de nivel pueden descubrir inconsistencias que no se veian
    # antes (una Especial no elegible, una excepcion de 2.o en otro grado).
    # Se cuentan para volver a aplicar el mismo criterio fail-closed.
    _inc_antes = len(inconsistencias)
    if nivel == NIVEL_PRIMARIA:
        condicion, motivo, extra = _situacion_primaria(
            grado_numero, oficiales, no_aprobados, contexto,
            advertencias, inconsistencias)
    else:
        condicion, motivo, extra = _situacion_secundaria(
            grado_numero, oficiales, no_aprobados, contexto,
            advertencias, inconsistencias)

    nuevas = [i for i in inconsistencias[_inc_antes:]
              if i not in INCONSISTENCIAS_INFORMATIVAS]
    if nuevas:
        bloqueos.append(BLOQUEO_DATOS_INCONSISTENTES)

    # Alfabetizacion de 3.o sin declarar: no se puede certificar.
    if (nivel == NIVEL_PRIMARIA and grado_numero == GRADO_ALFABETIZACION_INICIAL
            and condicion != REPROBADO
            and contexto.get('alfabetizacion_inicial') is None):
        bloqueos.append(BLOQUEO_ALFABETIZACION_NO_INFORMADA)

    # ── GATE 8 · asistencia ──
    #
    # Solo puede frenar una promoción o un aplazamiento. Si el estudiante ya
    # resultó REPROBADO por las áreas, la falta del dato de asistencia no
    # cambia nada: ya existe causa suficiente, y bloquear aquí solo dejaría
    # sin certificar algo que la revisión de asistencia no podría revertir.
    if condicion != REPROBADO:
        freno = _gate_asistencia(contexto, bloqueos, advertencias)
        if freno is not None:
            condicion, motivo, extra = freno
    else:
        _anotar_asistencia_pendiente(contexto, advertencias)

    if bloqueos:
        return salida(EN_PROCESO, MOTIVO_PROCESO_ABIERTO)

    # ── GATE 9 · 6.º de Secundaria: la titulación es otra fase ──
    if (nivel == NIVEL_SECUNDARIA and grado_numero == 6
            and condicion == PROMOVIDO):
        if ADV_TITULACION_PENDIENTE not in advertencias:
            advertencias.append(ADV_TITULACION_PENDIENTE)

    return salida(condicion, motivo, **extra)


# ═══════════════════════════ PRIMARIA ═══════════════════════════

def _fallo_tras_recuperacion_final(r):
    """¿Esta área no aprobó después de la Recuperación Final?

    Incluye las que ya pasaron por la Especial: si llegaron ahí es porque
    antes no aprobaron la Final. Sin esto, un estudiante con tres áreas en
    Especial parecería tener cero fallos tras la Final.
    """
    if r.get('estado') == RA.NO_APROBADA_TRAS_RECUPERACION_FINAL:
        return True
    return r.get('fase') == RA.FASE_RECUPERACION_ESPECIAL


def _situacion_primaria(grado_numero, oficiales, no_aprobados, contexto,
                        advertencias, inconsistencias):
    caidas = [r for r in oficiales if _fallo_tras_recuperacion_final(r)]
    en_especial = [r for r in caidas
                   if r.get('fase') == RA.FASE_RECUPERACION_ESPECIAL]

    # ── 1.º y 2.º: la norma no contempla repitencia ──
    if grado_numero in GRADOS_SIN_REPITENCIA:
        decision = contexto.get('decision_excepcional_segundo')
        if decision == 'repetir':
            if grado_numero == GRADO_EXCEPCION_COLEGIADA:
                # La repetición excepcional de 2.º es una decisión colegiada,
                # no un cálculo. A2 la acepta si viene declarada; no la deduce
                # jamás de una nota.
                return (REPROBADO, MOTIVO_EXCEPCION_SEGUNDO, {})
            inconsistencias.append(INC_EXCEPCION_SEGUNDO_FUERA_DE_LUGAR)

        if no_aprobados:
            # El motor numérico no puede inventar una repitencia que la norma
            # no contempla. Se promueve, y se dice que hubo áreas por debajo
            # del mínimo para que el acompañamiento no se pierda.
            advertencias.append(ADV_PROMOCION_ASISTIDA)
            return (PROMOVIDO, MOTIVO_SIN_REPITENCIA_PRIMER_CICLO, {})
        return (PROMOVIDO, MOTIVO_TODAS_APROBADAS, {})

    # ── 3.º a 6.º ──
    condicion, motivo, extra = _cascada_especial(
        caidas, en_especial, no_aprobados,
        maximo_elegible=MAX_AREAS_PARA_ESPECIAL_PRIMARIA,
        inconsistencia_no_elegible=INC_ESPECIAL_NO_ELEGIBLE_PRIMARIA,
        clave_requiere='requiere_recuperacion_especial',
        inconsistencias=inconsistencias)

    # ── Alfabetización inicial: solo 3.º, y solo declarada ──
    if grado_numero == GRADO_ALFABETIZACION_INICIAL:
        condicion, motivo = _gate_alfabetizacion(
            contexto, condicion, motivo, advertencias)
    elif contexto.get('alfabetizacion_inicial') is not None:
        inconsistencias.append(INC_ALFABETIZACION_FUERA_DE_TERCERO)

    return (condicion, motivo, extra)


def _gate_alfabetizacion(contexto, condicion, motivo, advertencias):
    """La alfabetización inicial de 3.º: condición adicional e independiente.

    Nunca se infiere de Lengua, de Matemática, de la CF, de la edad ni de la
    asistencia. O llega declarada o no se sabe.
    """
    alfabetizacion = contexto.get('alfabetizacion_inicial')

    if condicion == REPROBADO:
        # Ya hay causa suficiente de repitencia. Que falte el dato no puede
        # convertir esto en una promoción; se anota y se sigue.
        if alfabetizacion is None:
            advertencias.append(ADV_ALFABETIZACION_NO_INFORMADA)
        return (condicion, motivo)

    if alfabetizacion is True:
        return (condicion, motivo)
    if alfabetizacion is False:
        # «El estudiante de tercer grado que no complete la alfabetización
        # inicial luego de haber participado en los procesos de recuperación
        # pedagógica oportunamente repite el grado» (Registro 3.º, hoja 40).
        return (REPROBADO, MOTIVO_ALFABETIZACION_NO_LOGRADA)
    return (condicion, motivo)     # None: lo resuelve el bloqueo del llamador


# ══════════════════════════ SECUNDARIA ══════════════════════════

def _fallo_tras_extraordinaria(r):
    """¿Esta asignatura no aprobó después de la Extraordinaria?

    Las que ya pasaron por la Evaluación Especial cuentan: haber llegado allí
    demuestra que quedaron aplazadas tras la Extraordinaria.
    """
    if r.get('estado') == RA.NO_APROBADA_TRAS_EXTRAORDINARIA:
        return True
    return r.get('fase') == RA.FASE_ESPECIAL


def _situacion_secundaria(grado_numero, oficiales, no_aprobados, contexto,
                          advertencias, inconsistencias):
    caidas = [r for r in oficiales if _fallo_tras_extraordinaria(r)]
    en_especial = [r for r in caidas if r.get('fase') == RA.FASE_ESPECIAL]
    return _cascada_especial(
        caidas, en_especial, no_aprobados,
        maximo_elegible=MAX_ASIGNATURAS_PARA_ESPECIAL_SECUNDARIA,
        inconsistencia_no_elegible=INC_ESPECIAL_NO_ELEGIBLE_SECUNDARIA,
        clave_requiere='requiere_evaluacion_especial',
        inconsistencias=inconsistencias)


# ═══════════ LA PARTE QUE A1 NO PODÍA DECIDIR ═══════════

def _cascada_especial(caidas, en_especial, no_aprobados, maximo_elegible,
                      inconsistencia_no_elegible, clave_requiere,
                      inconsistencias):
    """Elegibilidad para el proceso especial y decisión final.

    Aquí está la diferencia entre A1 y A2. A1 mira un área y, si encuentra
    una Especial cargada, la lee: no tiene forma de saber cuántas áreas más
    cayeron. A2 cuenta el conjunto, y si el estudiante no era elegible, esa
    Especial NO le rescata por mucho que exista en la base. La regla agregada
    manda sobre la individual.
    """
    if not caidas:
        return (PROMOVIDO, MOTIVO_TODAS_APROBADAS, {})

    if len(caidas) > maximo_elegible:
        if en_especial:
            # Hay notas de un proceso especial al que no tenía derecho.
            inconsistencias.append(inconsistencia_no_elegible)
        return (REPROBADO, MOTIVO_DEMASIADAS_NO_APROBADAS, {})

    # Elegible. ¿Ya hizo el proceso especial?
    faltan_por_especial = [r for r in caidas
                           if r not in en_especial]
    if faltan_por_especial:
        return (APLAZADO, MOTIVO_ELEGIBLE_ESPECIAL, {clave_requiere: True})

    # Todas pasaron por el proceso especial: basta una sin aprobar.
    reprobadas = [r for r in en_especial
                  if r.get('estado') == RA.REPROBADA_DEFINITIVA]
    if reprobadas:
        return (REPROBADO, MOTIVO_ESPECIAL_NO_SUPERADA, {})
    return (PROMOVIDO, MOTIVO_ESPECIAL_SUPERADA, {})


# ═══════════════════════ ASISTENCIA ═══════════════════════

def _anotar_asistencia_pendiente(contexto, advertencias):
    porcentaje = contexto.get('porcentaje_ausencias_no_justificadas')
    if porcentaje is None or porcentaje > MAX_AUSENCIAS_NO_JUSTIFICADAS:
        if ADV_ASISTENCIA_NO_REVISADA not in advertencias:
            advertencias.append(ADV_ASISTENCIA_NO_REVISADA)


def _gate_asistencia(contexto, bloqueos, advertencias):
    """Ordenanza 04-2023: el 80% de asistencia es requisito, pero pasarse del
    20% de ausencias NO justificadas no reprueba por sí solo.

    La norma manda que el equipo de gestión y los docentes analicen el caso y
    decidan. A2 no puede sustituir esa decisión por una resta, así que sin
    ella no certifica.

    Devuelve None para seguir, o una terna (condicion, motivo, extra).
    """
    porcentaje = contexto.get('porcentaje_ausencias_no_justificadas')

    if porcentaje is None:
        bloqueos.append(BLOQUEO_ASISTENCIA_NO_EVALUADA)
        return None

    if porcentaje <= MAX_AUSENCIAS_NO_JUSTIFICADAS:
        return None

    decision = contexto.get('decision_asistencia')
    if decision is None:
        bloqueos.append(BLOQUEO_REVISION_ASISTENCIA)
        return None

    if decision == ASISTENCIA_PERMITIR_APROBACION:
        return None

    if decision == ASISTENCIA_REPETIR_GRADO:
        return (REPROBADO, MOTIVO_DECISION_ASISTENCIA, {})

    if decision == ASISTENCIA_REPROBAR_ASIGNATURAS:
        # GAP NORMATIVO DECLARADO.
        #
        # La norma permite esta decisión, pero las fuentes disponibles no
        # dicen cómo se integran esas asignaturas con la cascada: si van a
        # Completiva, si entran directamente como no aprobadas tras la
        # Extraordinaria, o si cuentan para la elegibilidad del proceso
        # especial. Inventar una regla aquí sería peor que no decidir: se
        # bloquea y se dice por qué.
        bloqueos.append(BLOQUEO_REPROBAR_ASIGNATURAS_SIN_NORMA)
        return None

    bloqueos.append(BLOQUEO_REVISION_ASISTENCIA)
    return None
