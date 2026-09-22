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
BLOQUEO_GRADO_INVALIDO = 'GRADO_INVALIDO'
BLOQUEO_CURRICULO_INVALIDO = 'CURRICULO_OFICIAL_INVALIDO'
BLOQUEO_ASISTENCIA_INVALIDA = 'PORCENTAJE_ASISTENCIA_INVALIDO'
BLOQUEO_ANTECEDENTE_EXCEPCION_2DO = (
    'ANTECEDENTE_REPETICION_EXCEPCIONAL_2DO_NO_INFORMADO')
BLOQUEO_REPETIR_NO_APLICA_1RO = 'DECISION_ASISTENCIA_REPETIR_NO_APLICA_1RO'
BLOQUEO_REPETIR_2DO_REQUIERE_EXCEPCION = (
    'DECISION_ASISTENCIA_REPETIR_2DO_REQUIERE_EXCEPCION_COLEGIADA')

# ═══════════════════ INCONSISTENCIAS ═══════════════════
# Datos que no encajan. Se informan; no se corrigen ni se borran.

INC_ESPECIAL_NO_ELEGIBLE_PRIMARIA = 'RECUPERACION_ESPECIAL_NO_ELEGIBLE_4_MAS'
INC_ESPECIAL_NO_ELEGIBLE_SECUNDARIA = 'EVALUACION_ESPECIAL_NO_ELEGIBLE_3_MAS'
INC_EXCEPCION_SEGUNDO_FUERA_DE_LUGAR = 'EXCEPCION_SEGUNDO_NO_APLICA_A_ESTE_GRADO'
INC_ALFABETIZACION_FUERA_DE_TERCERO = 'ALFABETIZACION_SOLO_APLICA_EN_3RO'
INC_AREAS_OFICIALES_NO_ESPERADAS = 'AREAS_OFICIALES_NO_ESPERADAS'
INC_NIVEL_INCOMPATIBLE = 'RESULTADO_A1_NIVEL_INCOMPATIBLE'
INC_ESTADO_A1_DESCONOCIDO = 'ESTADO_A1_DESCONOCIDO'
INC_ALFABETIZACION_VALOR_INVALIDO = 'ALFABETIZACION_3RO_VALOR_INVALIDO'
INC_EXCEPCION_SEGUNDO_INVALIDA = 'DECISION_EXCEPCIONAL_SEGUNDO_INVALIDA'
INC_EXCEPCION_SEGUNDO_YA_UTILIZADA = (
    'REPETICION_EXCEPCIONAL_SEGUNDO_YA_UTILIZADA')

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
# El proceso academico sigue abierto: la revision de asistencia todavia no
# toca. Se anota para que no se olvide, no para frenar el aplazamiento.
ADV_ASISTENCIA_PENDIENTE_DE_REVISION = 'ASISTENCIA_PENDIENTE_DE_REVISION'

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

GRADOS_VALIDOS = (1, 2, 3, 4, 5, 6)

# Lo unico que el caller puede pasar para la repeticion excepcional de 2.o.
#
# A2 NO determina si el equipo de gestion, psicologia, el docente, el
# tecnico distrital y la familia cumplieron el procedimiento colegiado: eso
# pertenece al flujo que capture la decision. A2 solo comprueba tres cosas
# —que el grado sea 2.o, que la decision venga declarada, y que la
# excepcion no se haya usado antes— y se niega si falta cualquiera.
DECISION_EXCEPCIONAL_REPETIR = 'repetir'

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


def _es_entero_real(valor):
    """int de verdad. `True` es un int en Python y aqui no puede pasar por 1."""
    return isinstance(valor, int) and not isinstance(valor, bool)


def _es_numero_real(valor):
    """int o float utilizables. Sin bool, sin NaN, sin infinitos, sin strings.

    `"20"` no se convierte: convertir en silencio es como se cuelan los datos
    que nadie valido.
    """
    if isinstance(valor, bool):
        return False
    if not isinstance(valor, (int, float)):
        return False
    return valor == valor and valor not in (float('inf'), float('-inf'))


def _curriculo_utilizable(codigos):
    """Una coleccion de codigos, no una cadena.

    `'LE'` es iterable y se desharia en 'L' y 'E': un currículo de dos áreas
    inexistentes. Por eso se rechazan str y bytes explícitamente.
    """
    if isinstance(codigos, (str, bytes)):
        return False
    try:
        elementos = list(codigos)
    except TypeError:
        return False
    for c in elementos:
        if not isinstance(c, str) or not c.strip():
            return False
    return True


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
    `grado_numero` — un entero de 1 a 6. Hace falta siempre y tiene que ser
                     válido: la norma cambia por grado y no hay regla
                     aplicable a un 0, a un 7 ni a la cadena '3'.
    `resultados`   — las salidas de `resolver_nota_primaria` /
                     `resolver_nota_secundaria`, una por asignatura.
    `codigos_oficiales_esperados` — los bloques curriculares que el grado DEBE
                     tener, como colección (no como cadena). Se compara y se
                     SELECCIONA como multiconjunto.
    `contexto`     — lo que no sale de las notas y nadie puede inferir:
                     alfabetización inicial, ausencias no justificadas,
                     decisiones del equipo de gestión.

    Nada de lo recibido se modifica.
    """
    contexto = dict(contexto) if contexto else {}
    resultados = list(resultados) if resultados else []

    bloqueos, advertencias, inconsistencias = [], [], []
    conteos, codigos = _vacio()

    def cortar(*bloqueos_nuevos):
        return _resultado(nivel, grado_numero, EN_PROCESO,
                          MOTIVO_PROCESO_ABIERTO, conteos, codigos,
                          bloqueos=list(bloqueos_nuevos))

    # ── GATE 1 · nivel ──
    if nivel not in (NIVEL_PRIMARIA, NIVEL_SECUNDARIA):
        return cortar(BLOQUEO_NIVEL_NO_RECONOCIDO)

    # ── GATE 2 · grado ──
    if grado_numero is None:
        return cortar(BLOQUEO_GRADO_NO_DECLARADO)
    if not _es_entero_real(grado_numero) or grado_numero not in GRADOS_VALIDOS:
        # 0, 7, -1, '3', True y 3.5 no son grados. Sin un grado real no se
        # puede aplicar ninguna regla, y adivinar sería peor que parar.
        return cortar(BLOQUEO_GRADO_INVALIDO)

    # ── GATE 3 · el currículo esperado, declarado y utilizable ──
    if codigos_oficiales_esperados is None:
        return cortar(BLOQUEO_CURRICULO_NO_DECLARADO)
    if not _curriculo_utilizable(codigos_oficiales_esperados):
        return cortar(BLOQUEO_CURRICULO_INVALIDO)

    esperados = Counter(codigos_oficiales_esperados)
    if not esperados:
        return cortar(BLOQUEO_SIN_CURRICULO_OFICIAL)

    # ── GATE 4 · separar currículo oficial del interno ──
    oficiales = [r for r in resultados if _codigo(r) is not None]
    internas = [r for r in resultados if _codigo(r) is None]
    codigos_no_oficiales = tuple(['(sin codigo oficial)'] * len(internas))

    # ── GATE 5 · SELECCIÓN EXACTA del multiconjunto esperado ──
    #
    # No basta con «está en los esperados»: si el grado declara LE dos veces y
    # llegan tres LE, solo dos participan. Se va consumiendo el Counter.
    #
    # Lo que sobra NO entra en ningún conteo ni en ninguna regla. Antes sí
    # entraba, y una materia oficial no esperada podía subir el total, contar
    # como reprobada y convertir un PROMOVIDO en APLAZADO.
    restante = Counter(esperados)
    oficiales_esperadas, sobrantes = [], []
    for r in oficiales:
        cod = _codigo(r)
        if restante.get(cod, 0) > 0:
            restante[cod] -= 1
            oficiales_esperadas.append(r)
        else:
            sobrantes.append(r)

    faltan = {c: n for c, n in restante.items() if n > 0}
    if faltan:
        bloqueos.append(BLOQUEO_CURRICULO_INCOMPLETO)
    if sobrantes:
        # Tampoco se ignora en silencio: la configuración curricular o los
        # datos tienen que revisarse antes de certificar nada.
        inconsistencias.append(INC_AREAS_OFICIALES_NO_ESPERADAS)
        bloqueos.append(BLOQUEO_DATOS_INCONSISTENTES)

    # ── GATE 6 · cada área esperada, validada ──
    for r in oficiales_esperadas:
        if r.get('nivel') != nivel:
            # Un resultado de Secundaria no puede decidir un grado de
            # Primaria: los cortes y las fases son otros.
            if INC_NIVEL_INCOMPATIBLE not in inconsistencias:
                inconsistencias.append(INC_NIVEL_INCOMPATIBLE)
        if r.get('estado') not in RA.ESTADOS:
            # Un estado que A2 no conoce NO es una reprobación. Antes caía en
            # `no_aprobados` y podía hacer repetir a alguien.
            if INC_ESTADO_A1_DESCONOCIDO not in inconsistencias:
                inconsistencias.append(INC_ESTADO_A1_DESCONOCIDO)

    # ── GATE 7 · clasificar SOLO las esperadas ──
    aprobados, pendientes_cod, no_aprobados = [], [], []
    hubo_inconsistencia_de_area = False
    for r in oficiales_esperadas:
        cod = _codigo(r)
        if r.get('inconsistencias'):
            hubo_inconsistencia_de_area = True
            for inc in r['inconsistencias']:
                if inc not in inconsistencias:
                    inconsistencias.append(inc)
        estado = r.get('estado')
        if estado in ESTADOS_APROBADOS:
            aprobados.append(cod)
        elif estado in ESTADOS_PENDIENTES:
            pendientes_cod.append(cod)
        elif estado in RA.ESTADOS:
            no_aprobados.append(cod)
        # Un estado desconocido no se clasifica en ninguna parte: ya generó
        # su inconsistencia en el gate 6.

    conteos = {
        'total': len(oficiales_esperadas),
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

    # ── GATE 8 · inconsistencias heredadas o detectadas ──
    if hubo_inconsistencia_de_area or INC_NIVEL_INCOMPATIBLE in inconsistencias \
            or INC_ESTADO_A1_DESCONOCIDO in inconsistencias:
        if BLOQUEO_DATOS_INCONSISTENTES not in bloqueos:
            bloqueos.append(BLOQUEO_DATOS_INCONSISTENTES)

    # ── GATE 9 · áreas sin resolver ──
    if pendientes_cod:
        bloqueos.append(BLOQUEO_AREAS_PENDIENTES)

    # ── GATE 10 · el contexto, validado antes de usarlo ──
    _validar_contexto(nivel, grado_numero, contexto, bloqueos, inconsistencias)

    if bloqueos:
        return salida(EN_PROCESO, MOTIVO_PROCESO_ABIERTO)

    # ── GATE 11 · reglas por nivel y grado ──
    _inc_antes = len(inconsistencias)
    if nivel == NIVEL_PRIMARIA:
        condicion, motivo, extra = _situacion_primaria(
            grado_numero, oficiales_esperadas, no_aprobados, contexto,
            advertencias, inconsistencias, bloqueos)
    else:
        condicion, motivo, extra = _situacion_secundaria(
            grado_numero, oficiales_esperadas, no_aprobados, contexto,
            advertencias, inconsistencias)

    nuevas = [i for i in inconsistencias[_inc_antes:]
              if i not in INCONSISTENCIAS_INFORMATIVAS]
    if nuevas and BLOQUEO_DATOS_INCONSISTENTES not in bloqueos:
        bloqueos.append(BLOQUEO_DATOS_INCONSISTENTES)

    # ── GATE 12 · alfabetización de 3.º sin declarar ──
    if (nivel == NIVEL_PRIMARIA and grado_numero == GRADO_ALFABETIZACION_INICIAL
            and condicion != REPROBADO
            and contexto.get('alfabetizacion_inicial') is None):
        bloqueos.append(BLOQUEO_ALFABETIZACION_NO_INFORMADA)

    # ── GATE 13 · asistencia, en su momento normativo ──
    #
    # La Ordenanza 04-2023 plantea el análisis del exceso de ausencias para el
    # estudiante que YA logró las competencias esperadas. Por eso el gate solo
    # corre cuando el candidato académico es PROMOVIDO:
    #
    #   · APLAZADO significa que el proceso académico NO ha terminado. Frenar
    #     ahí por una revisión de asistencia que todavía no toca convertiría
    #     un aplazamiento legítimo en un limbo y escondería que al estudiante
    #     le queda una Especial por hacer.
    #   · REPROBADO ya tiene causa suficiente; la revisión no la revertiría.
    if condicion == PROMOVIDO:
        freno = _gate_asistencia(grado_numero, contexto, bloqueos,
                                 advertencias, inconsistencias)
        if freno is not None:
            condicion, motivo, extra = freno
    else:
        _anotar_asistencia_pendiente(condicion, contexto, advertencias)

    if bloqueos:
        return salida(EN_PROCESO, MOTIVO_PROCESO_ABIERTO)

    # ── GATE 14 · 6.º de Secundaria: la titulación es otra fase ──
    if (nivel == NIVEL_SECUNDARIA and grado_numero == 6
            and condicion == PROMOVIDO):
        if ADV_TITULACION_PENDIENTE not in advertencias:
            advertencias.append(ADV_TITULACION_PENDIENTE)

    return salida(condicion, motivo, **extra)


def _validar_contexto(nivel, grado_numero, contexto, bloqueos, inconsistencias):
    """El contexto no se interpreta: se valida o se rechaza.

    Un `"NO"` de alfabetización no es `False` ni es `None`, y sin esta
    comprobación un 3.º podía salir PROMOVIDO con la alfabetización marcada
    como no lograda en la cabeza de quien la escribió.
    """
    # Alfabetización: solo True, False o None.
    if 'alfabetizacion_inicial' in contexto:
        valor = contexto['alfabetizacion_inicial']
        if valor is not None and not isinstance(valor, bool):
            if grado_numero == GRADO_ALFABETIZACION_INICIAL:
                inconsistencias.append(INC_ALFABETIZACION_VALOR_INVALIDO)
                bloqueos.append(BLOQUEO_DATOS_INCONSISTENTES)

    # Excepción de 2.º: solo None o 'repetir'.
    decision = contexto.get('decision_excepcional_segundo')
    if decision is not None and decision != DECISION_EXCEPCIONAL_REPETIR:
        inconsistencias.append(INC_EXCEPCION_SEGUNDO_INVALIDA)
        bloqueos.append(BLOQUEO_DATOS_INCONSISTENTES)

    # Porcentaje de ausencias: número real entre 0 y 100.
    if 'porcentaje_ausencias_no_justificadas' in contexto:
        p = contexto['porcentaje_ausencias_no_justificadas']
        if p is not None and (not _es_numero_real(p) or p < 0 or p > 100):
            bloqueos.append(BLOQUEO_ASISTENCIA_INVALIDA)


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
                        advertencias, inconsistencias, bloqueos):
    caidas = [r for r in oficiales if _fallo_tras_recuperacion_final(r)]
    en_especial = [r for r in caidas
                   if r.get('fase') == RA.FASE_RECUPERACION_ESPECIAL]

    # ── 1.º y 2.º: la norma no contempla repitencia ──
    if grado_numero in GRADOS_SIN_REPITENCIA:
        decision = contexto.get('decision_excepcional_segundo')
        if decision == DECISION_EXCEPCIONAL_REPETIR:
            if grado_numero != GRADO_EXCEPCION_COLEGIADA:
                inconsistencias.append(INC_EXCEPCION_SEGUNDO_FUERA_DE_LUGAR)
            else:
                # La repetición excepcional de 2.º es una decisión colegiada,
                # no un cálculo, y la norma la permite UNA SOLA VEZ. A2 no
                # tiene historial y no lo va a inventar: si no le dicen si ya
                # se usó, no certifica.
                ya_usada = contexto.get(
                    'repeticion_excepcional_segundo_ya_utilizada')
                if ya_usada is True:
                    inconsistencias.append(INC_EXCEPCION_SEGUNDO_YA_UTILIZADA)
                elif ya_usada is None:
                    bloqueos.append(BLOQUEO_ANTECEDENTE_EXCEPCION_2DO)
                else:
                    return (REPROBADO, MOTIVO_EXCEPCION_SEGUNDO, {})

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
    if alfabetizacion is not None and not isinstance(alfabetizacion, bool):
        # Un valor que no es booleano ya genero su bloqueo en la validacion
        # del contexto. Aqui no se interpreta de ninguna manera.
        return (condicion, motivo)

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

def _anotar_asistencia_pendiente(condicion, contexto, advertencias):
    """El proceso no ha terminado o ya hay causa suficiente: se anota y se sigue."""
    porcentaje = contexto.get('porcentaje_ausencias_no_justificadas')
    pendiente = (porcentaje is None
                 or not _es_numero_real(porcentaje)
                 or porcentaje > MAX_AUSENCIAS_NO_JUSTIFICADAS)
    if not pendiente:
        return
    aviso = (ADV_ASISTENCIA_NO_REVISADA if condicion == REPROBADO
             else ADV_ASISTENCIA_PENDIENTE_DE_REVISION)
    if aviso not in advertencias:
        advertencias.append(aviso)


def _gate_asistencia(grado_numero, contexto, bloqueos, advertencias,
                     inconsistencias):
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
        # 1.º no contempla repitencia: ninguna vía, tampoco esta, puede
        # producirla. Se para y se dice.
        if grado_numero == 1:
            bloqueos.append(BLOQUEO_REPETIR_NO_APLICA_1RO)
            return None
        # En 2.º la única repetición posible es la excepcional, colegiada y
        # por una sola vez. La vía genérica de asistencia no puede saltársela:
        # hay que formalizarla por el contexto de la excepción.
        if grado_numero == GRADO_EXCEPCION_COLEGIADA:
            bloqueos.append(BLOQUEO_REPETIR_2DO_REQUIERE_EXCEPCION)
            return None
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
