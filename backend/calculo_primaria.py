"""
════════════════════════════════════════════════════════════════════════
MOTOR DE CÁLCULO — NIVEL PRIMARIO (v2.13.44)
════════════════════════════════════════════════════════════════════════

Carril SEPARADO de secundaria. No importa ni depende de la lógica de
CalificacionSecundaria / EvaluacionExtraSecundaria.

Reglas oficiales (Registro de Grado, Nivel Primario, MINERD 2023-2024):
 - 3 competencias por área (C1, C2, C3) en TODAS las áreas y los seis
   grados, inglés incluido (Registros de Grado MINERD 2026).
 - Cada competencia: P1-P4 con RP1-RP4. Valor del período = RP si existe, si
   no P (R2: la RP REEMPLAZA a la nota del período, no compite con ella).
 - Un período está EVALUADO, en NE o PENDIENTE. NULL a secas es PENDIENTE.
 - CF de competencia: solo con los CUATRO períodos resueltos. Regla normal
   (P1+P2+P3+P4)/4; con NE, promedio de los evaluados (pág. 85). Un período
   PENDIENTE la bloquea: no hay CF oficial a mitad de año.
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


# ═══ LAS COMPETENCIAS QUE UN ÁREA DEBE TENER ═══
#
# Tres. Las mismas para todas las áreas oficiales del Nivel Primario y para
# los seis grados. Comprobado hoja por hoja en los Registros de Grado 2026 del
# MINERD, los seis: cada página de área rotula su matriz «C1 Competencia 1 /
# C2 Competencia 2 / C3 Competencia 3», y eso incluye Lenguas Extranjeras
# (inglés) en 4.º, 5.º y 6.º —hojas 96 de esos tres Registros—.
#
# POR QUÉ UNA CONSTANTE Y NO EL CATÁLOGO
#     Hasta R3 esto se consultaba en `AreaCurricular.numero_competencias`,
#     cruzando `AreaCurricular.nombre` con `Asignatura.nombre`. Dos problemas
#     de distinta gravedad:
#
#       · el catálogo decía 2 para inglés, que contradice el Registro;
#       · y el cruce por nombre no acertaba nunca con inglés —la asignatura se
#         llama «Inglés» y el área «Lenguas Extranjeras (Inglés)»—, así que
#         en la práctica caía en el default 3 y el error del catálogo quedaba
#         tapado por un acierto accidental.
#
#     Lo segundo es lo que descarta el catálogo como fuente: `nombre` es un
#     campo editable desde la pantalla de Áreas. La matriz de evaluación de
#     Primaria no puede depender de que nadie renombre un área.
#
#     Si algún día un documento oficial introdujera un área de Primaria con
#     otra estructura, esto deja de ser una constante y pasa a ser un dato por
#     área. Hoy no hay ninguna: los seis Registros dicen lo mismo.
COMPETENCIAS_OFICIALES_PRIMARIA = (1, 2, 3)
TOTAL_COMPETENCIAS_PRIMARIA = len(COMPETENCIAS_OFICIALES_PRIMARIA)


# ══════════════════════════════════════════════════════════════════════
# EL PERÍODO — definición canónica
#
# Hasta R2 cada consumidor reimplementaba esto por su cuenta: el modelo, el
# Registro, el boletín a padres, las estadísticas, el cuadro de honor, la
# planilla y el frontend, cada uno con su copia. Siete definiciones del mismo
# concepto es garantía de que tarde o temprano dejan de coincidir.
#
# A partir de aquí hay UNA. Es una función pura —números, no modelos— para
# que la pueda usar tanto `models.py` como cualquier consumidor sin arrastrar
# dependencias ni crear ciclos de import.
# ══════════════════════════════════════════════════════════════════════

def valor_periodo_primaria(p, rp):
    """Valor numérico efectivo de un período de Primaria, o None.

    RP REEMPLAZA A P. No es el mayor de los dos.

    La norma dice que el resultado de la recuperación pedagógica «se sumará a
    la obtenida en el período y se asentará en la columna correspondiente,
    siendo esta última la calificación final del período». Es decir: RP no es
    una nota paralela que compita con P, es LA nota del período una vez hecha
    la recuperación. Si el docente asentó 70, el período vale 70, venga de
    donde venga P.

    Hasta R2 esto era `max(P, RP)`, que coincide mientras RP sea mayor —el
    caso habitual, porque se recupera para subir— pero se desvía en cuanto no
    lo es: con P=80 y RP=70 devolvía 80, ignorando lo que el docente asentó
    como calificación final del período.

        P=50  RP=70   -> 70          P=80  RP=None -> 80
        P=80  RP=70   -> 70          P=None RP=70  -> 70
        P=60  RP=75   -> 75          P=None RP=None -> None

    Solo PRIMARIA. Secundaria conserva su propia regla.
    """
    if rp is not None:
        return rp
    return p


# Los tres estados de un período. `PENDIENTE` y `NE` NO son lo mismo: el
# primero dice «todavía no», el segundo dice «no se evaluó, y está
# justificado». Confundirlos es lo que permitía fabricar una CF a mitad de
# año.
PERIODO_EVALUADO = 'evaluado'
PERIODO_NE = 'ne'
PERIODO_PENDIENTE = 'pendiente'


def estado_periodo_primaria(p, rp, ne=False):
    """'evaluado' | 'ne' | 'pendiente' para un período de Primaria.

    NE gana sobre la nota a propósito: si una fila quedara en el estado
    contradictorio (nota + NE), lo que se lee es NE en vez de inventar una
    tercera interpretación. La escritura impide que eso llegue a persistirse,
    pero una lectura defensiva no cuesta nada.
    """
    if ne:
        return PERIODO_NE
    if valor_periodo_primaria(p, rp) is not None:
        return PERIODO_EVALUADO
    return PERIODO_PENDIENTE


def cf_competencia(calif, minimo_periodos=1):
    """CF de UNA competencia (objeto CalificacionPrimaria).
    Promedio de los períodos evaluados (NE = período sin valor)."""
    if calif is None:
        return None
    return calif.calcular_final(minimo_periodos=minimo_periodos)


def cf_area(competencias):
    """CF del área = promedio de las CF OFICIALES de C1, C2 y C3.

    `competencias` = objetos CalificacionPrimaria del área.
    Devuelve (cf_exacto, cf_redondeado) o (None, None).

    EXIGE EL CONJUNTO COMPLETO, NO «LAS QUE HAYA»
        La norma dice (C1+C2+C3)/3. Hasta R3 esta función promediaba las
        competencias que encontrara: con solo C1 y C2 cargadas salía un
        número de aspecto válido —y con él un veredicto de área, y con él una
        ficha de recuperación— calculado sobre dos tercios del área.

        Ahora se valida por `competencia_numero` contra
        COMPETENCIAS_OFICIALES_PRIMARIA, no por `len()`: tres filas no son el
        área completa si dos de ellas son la misma competencia, y la longitud
        sola no distingue ese caso.

        Falta C3            -> (None, None)
        C1 y C3 sin C2      -> (None, None)
        Las tres, una sin CF oficial (algún período PENDIENTE) -> (None, None)
        Las tres con CF     -> promedio de las tres.

    Esto cierra el bloqueo que R2 dejó abierto a propósito
    (CF_AREA_EXPECTED_COMPETENCIES_REQUIRES_R3).
    """
    esperadas = set(COMPETENCIAS_OFICIALES_PRIMARIA)
    por_numero = {}
    for c in competencias or ():
        numero = getattr(c, 'competencia_numero', None)
        if numero in esperadas:
            por_numero[numero] = c
    if set(por_numero) != esperadas:
        return None, None

    finales = []
    for numero in sorted(esperadas):
        final = cf_competencia(por_numero[numero])
        if final is None:
            return None, None       # una competencia a medias deja el área sin CF
        finales.append(final)

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
