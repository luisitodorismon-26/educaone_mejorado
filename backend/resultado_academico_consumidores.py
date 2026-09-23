# -*- coding: utf-8 -*-
"""
R4-A3 — el puente entre la base de datos y los motores canónicos.

POR QUÉ EXISTE
    A1 (`resultado_academico`) sabe resolver UN área. A2
    (`promocion_academica`) sabe resolver UN estudiante. Ninguno de los dos
    toca la base, y así debe seguir siendo: son motores puros y auditables.

    Pero los documentos —el boletín de Secundaria, el de Primaria, las actas—
    salen de filas ORM, y hasta R4-A3 cada uno se armaba su propia respuesta a
    «¿este estudiante promueve?». Eran CUATRO reglas distintas:

      · boletín Secundaria individual   `reprobadas > 2` sobre una cadena
                                        `nota_final or especial_final or …`
      · boletín Secundaria por lote     `(cf or 0) >= 70`, y luego
                                        `PENDIENTE/REPITENTE`
      · `calculo_primaria.condicion_final_estudiante`
                                        0 / 1-3 / 4+ áreas, sin saber en qué
                                        grado está el estudiante
      · `boletin_minerd.get_situacion_final`  (muerta, sin llamadores)

    Dos de ellas daban respuestas DISTINTAS para el mismo estudiante. Este
    módulo es el único sitio desde el que un documento pregunta, y todos
    preguntan lo mismo.

QUÉ NO HACE
    No decide nada. No hay aquí ni un corte de 65, ni uno de 70, ni un
    contador de áreas, ni una cascada. Traduce filas a las entradas que A1 y
    A2 esperan, y devuelve lo que ellos contesten.

    Tampoco escribe: ni `add`, ni `flush`, ni `commit`, ni `delete`. Solo
    SELECT. `test_r4_a3_consumidores_canonicos` lo comprueba por AST y con una
    sesión falsa que revienta si alguien intenta escribir.

CÓMO SE USA
    Un consumidor documental llama a `construir_situacion_estudiante(...)` y
    recibe los resultados por área, el currículo esperado, el contexto que
    realmente existía y la salida completa de A2. Para imprimir usa
    `texto_situacion()` o `situacion_boletin_secundaria()`, que traducen la
    condición canónica al vocabulario del documento SIN cambiarla.
"""
import re

import catalogo_indicadores as CAT
import catalogo_primaria as CPRI
import promocion_academica as PA
import resultado_academico as RA

# ══════════════════════════ DIAGNÓSTICOS ══════════════════════════
# Por qué el contexto salió incompleto. No son bloqueos —los bloqueos los
# pone A2—: son la explicación para quien mire el documento y se pregunte por
# qué no dice «Promovido».

DIAG_GRADO_NO_ASIGNADO = 'CURSO_SIN_GRADO_ASIGNADO'
DIAG_GRADO_SIN_NUMERO = 'GRADO_SIN_NUMERO_LEGIBLE_EN_EL_NOMBRE'
DIAG_GRADO_FUERA_DE_RANGO = 'GRADO_FUERA_DEL_RANGO_1_6'
DIAG_GRADO_INCOHERENTE = 'GRADO_CON_NOMBRE_Y_ORDEN_CONTRADICTORIOS'
DIAG_CURRICULO_SIN_ASIGNACIONES = 'CURSO_SIN_ASIGNACIONES_ACTIVAS'
DIAG_CURRICULO_SIN_AREAS = 'NINGUNA_ASIGNATURA_DEL_CURSO_TIENE_AREA_CURRICULAR'
DIAG_GAP_CURRICULO_ESPERADO = 'GAP_CURRICULO_ESPERADO_POR_CURSO'
DIAG_CATALOGO_SIN_GRADO = 'CATALOGO_CURRICULAR_SIN_ENTRADAS_PARA_EL_GRADO'
DIAG_NIVEL_DESCONOCIDO = 'NIVEL_NO_RECONOCIDO'
DIAG_AREAS_ESPERADAS_SIN_ASIGNATURA = 'AREAS_OFICIALES_SIN_ASIGNATURA_CONFIGURADA'
# INFORMATIVO, nunca bloqueo: una materia con identidad curricular valida que
# no pertenece al curriculo de ESTE grado. El caso real es el colegio privado
# que ensena Ingles en 1.o: la identidad LEI es correcta y la materia sigue
# con su profesor, su horario, sus notas y su boletin; solo no participa en la
# promocion de un grado donde el curriculo oficial no la contempla.
DIAG_AREAS_ADICIONALES = 'AREAS_ADICIONALES_NO_PARTICIPAN_EN_PROMOCION'

# De donde salio el curriculo. Viaja en el paquete para que una auditoria
# posterior no tenga que adivinarlo.
FUENTE_CATALOGO_SECUNDARIA = 'CATALOGO_INDICADORES_' + CAT.VERSION_ACTUAL
FUENTE_CATALOGO_PRIMARIA = 'CATALOGO_PRIMARIA_' + CPRI.VERSION_ACTUAL
DIAG_DIAS_TRABAJADOS_NO_DECLARADOS = 'DIAS_TRABAJADOS_NO_DECLARADOS'
DIAG_ASISTENCIA_INCOHERENTE = 'AUSENCIAS_SUPERAN_LOS_DIAS_TRABAJADOS'
DIAG_ALFABETIZACION_SIN_FUENTE = 'ALFABETIZACION_3RO_SIN_FUENTE_PERSISTIDA'
DIAG_DECISION_ASISTENCIA_SIN_FUENTE = 'DECISION_ASISTENCIA_SIN_FUENTE_PERSISTIDA'
DIAG_EXCEPCION_2DO_SIN_FUENTE = 'EXCEPCION_2DO_SIN_FUENTE_PERSISTIDA'

GRADO_ALFABETIZACION = 3
GRADOS_VALIDOS = (1, 2, 3, 4, 5, 6)

# Estados de `Asistencia` y qué significan. La semántica ya existía en el
# sistema; aquí solo se declara cuál de ellos es una ausencia NO justificada,
# que es lo único que A2 pide.
#
#   presente  el estudiante vino
#   tardanza  vino tarde, pero vino
#   excusa    ausencia JUSTIFICADA — no entra en el numerador
#   ausente   ausencia NO justificada — la única que cuenta
AUSENCIA_NO_JUSTIFICADA = 'ausente'

# Un día con varias filas (colegios que pasan lista por asignatura) es UN día.
# La prioridad es la que ya usaba `_construir_asistencias_boletin`.
_PRIORIDAD_ESTADO = {'presente': 4, 'tardanza': 3, 'excusa': 2, 'ausente': 1}


# ══════════════════════════ GRADO NUMÉRICO ══════════════════════════

def numero_de_grado(grado):
    """El número 1..6 DENTRO del nivel, o `(None, motivo)`.

    `Grado.orden` NO sirve solo. Es un contador global que se reparte entre
    los planes que tenga contratados el colegio (`app.py`, creación del
    colegio): en uno con Secundaria y Primaria, Secundaria queda 1-6 y
    Primaria 7-12; en uno que solo tenga Primaria, Primaria queda 1-6. El
    mismo `orden=3` significa dos cosas distintas en dos colegios.

    Por eso el número sale del NOMBRE, con la lectura estricta de
    `app._numero_grado_estricto` —sin el default de 1 que tiene
    `registro_validator._extraer_grado_numero`, que convertiría un grado con
    nombre raro en un 1.º—, y `orden` se usa solo para CONTRADECIR.

    Si los dos datos del propio colegio se contradicen no se elige ninguno:
    se devuelve None, A2 bloquea y el documento no certifica. Es la misma
    política que `indicadores_curriculares.grado_numero_de_curso`.
    """
    if grado is None:
        return None, DIAG_GRADO_NO_ASIGNADO

    m = re.search(r'(\d+)', getattr(grado, 'nombre', None) or '')
    if not m:
        return None, DIAG_GRADO_SIN_NUMERO
    numero = int(m.group(1))
    if numero not in GRADOS_VALIDOS:
        return None, DIAG_GRADO_FUERA_DE_RANGO

    orden = getattr(grado, 'orden', None)
    if isinstance(orden, int) and not isinstance(orden, bool):
        # El orden es interpretable de dos maneras según el plan del colegio.
        # Si CUALQUIERA de las dos coincide con el nombre, no hay conflicto.
        candidatos = set()
        if 1 <= orden <= 6:
            candidatos.add(orden)
        if 7 <= orden <= 12:
            candidatos.add(orden - 6)
        if candidatos and numero not in candidatos:
            return None, DIAG_GRADO_INCOHERENTE

    return numero, None


def nivel_de_grado(grado):
    """'primaria' | 'secundaria' | None, leído de `Grado.nivel`."""
    nivel = (getattr(grado, 'nivel', None) or '').strip().lower()
    if nivel.startswith('prim'):
        return RA.NIVEL_PRIMARIA
    if nivel.startswith('sec'):
        return RA.NIVEL_SECUNDARIA
    return None


# ══════════════════════════ CURRÍCULO OFICIAL ══════════════════════════
#
# CURRÍCULO NO ES PLANTILLA DOCENTE
#
# A3 derivaba el currículo esperado de `AsignacionProfesor(activo=True)`, y
# eso estaba mal. Esa tabla dice QUIÉN imparte, no QUÉ áreas debe tener el
# grado, y cambia por motivos que no son académicos:
#
#   · la edición masiva de asignaciones pone `fila.activo = False`;
#   · `DELETE /api/asignaciones/{id}` hace `db.delete(asig)`;
#   · el reemplazo de profesor desactiva la del saliente y crea la del nuevo;
#   · `clonar-cursos` crea los cursos del año siguiente SIN asignaciones.
#
# Con la versión anterior, retirar al profesor de Matemática hacía que
# Matemática desapareciera del currículo esperado, A2 no la echaba de menos y
# el estudiante salía PROMOVIDO sin un solo bloqueo. Una vacante docente
# borraba una materia del expediente.
#
# Ahora el currículo sale de una fuente que no sabe quién da clase.


def curriculo_oficial_esperado(nivel, grado_numero, version=None):
    """Qué bloques oficiales espera este grado. `(codigos, fuente, diag)`.

    No recibe profesor, ni asignación, ni horario, ni notas: si cambiara con
    cualquiera de esas cosas, no sería un currículo.

    SECUNDARIA — el catálogo versionado
        `catalogo_indicadores` carga `catalogos/indicadores_secundaria_2023.json`,
        extraído OFFLINE de los seis Registros oficiales del MINERD (uno por
        grado) y versionado junto al código. No pertenece a ningún tenant,
        nadie lo edita desde la aplicación y ya es la fuente única que valida
        `Asignatura.area_curricular_codigo`.

        Los códigos se leen POR GRADO, no de la cabecera: que los nueve
        bloques aparezcan en los seis grados es algo que el catálogo dice, no
        algo que este módulo dé por supuesto. Si una versión futura cambiara
        el reparto, esta función cambia con ella sin tocar una línea.

    PRIMARIA — el catálogo PRI-2023, por ciclo
        `catalogo_primaria` recoge la matriz de la Adecuación Curricular del
        Nivel Primario: siete áreas en 1.º-3.º y las mismas siete más Inglés
        en 4.º-6.º. Igual que el de Secundaria, es una constante versionada
        del repositorio: no pertenece a ningún tenant y nadie la edita desde
        la aplicación.

        A3.1 devolvía aquí un GAP porque faltaba resolver la IDENTIDAD —qué
        `Asignatura` del colegio representa cada área—. A3.2 comprobó que esa
        identidad ya existe y no hacía falta inventarla: los ocho códigos de
        Primaria son los mismos que los de Secundaria, con el mismo nombre
        oficial, así que `Asignatura.area_curricular_codigo` vale para los dos
        niveles sin un segundo campo.

        Francés (LEF) no aparece: tiene currículo propio en los seis grados de
        Secundaria, no en Primaria.
    """
    if not _es_entero_de_grado(grado_numero):
        return None, None, DIAG_GRADO_FUERA_DE_RANGO

    if nivel == RA.NIVEL_SECUNDARIA:
        try:
            entradas = CAT.listar_por(version=version, grado=grado_numero)
        except Exception:
            return None, None, DIAG_CATALOGO_SIN_GRADO
        codigos = sorted({e['area_codigo'] for e in entradas
                          if e.get('area_codigo')})
        if not codigos:
            return None, None, DIAG_CATALOGO_SIN_GRADO
        fuente = 'CATALOGO_INDICADORES_' + (version or CAT.VERSION_ACTUAL)
        return tuple(codigos), fuente, None

    if nivel == RA.NIVEL_PRIMARIA:
        try:
            codigos = CPRI.codigos_por_grado(grado_numero, version=version)
        except CPRI.CatalogoPrimariaError:
            return None, None, DIAG_GAP_CURRICULO_ESPERADO
        if not codigos:
            return None, None, DIAG_GAP_CURRICULO_ESPERADO
        fuente = 'CATALOGO_PRIMARIA_' + (version or CPRI.VERSION_ACTUAL)
        return tuple(codigos), fuente, None

    return None, None, DIAG_NIVEL_DESCONOCIDO


def _es_entero_de_grado(valor):
    return (isinstance(valor, int) and not isinstance(valor, bool)
            and valor in GRADOS_VALIDOS)


def asignaturas_configuradas(asignaciones, asignaturas_por_id):
    """Qué Asignatura CONCRETA del colegio representa cada bloque.

    Esto sí es trabajo de `AsignacionProfesor`, y sigue siéndolo: sirve para
    saber qué filas institucionales hay que leer. Lo que ya NO hace es
    decidir qué códigos DEBEN existir.

    Devuelve `{codigo_area: [asignaturas]}` más la lista de las internas, que
    quedan fuera de la promoción oficial. Un NULL en
    `area_curricular_codigo` no es un error de configuración: es el estado
    normal de una materia complementaria como Música.
    """
    por_area, internas = {}, []
    vistas = set()
    for a in asignaciones or ():
        asig_id = getattr(a, 'asignatura_id', None)
        if asig_id is None or asig_id in vistas:
            continue
        vistas.add(asig_id)
        asignatura = asignaturas_por_id.get(asig_id)
        if asignatura is None:
            continue
        codigo = getattr(asignatura, 'area_curricular_codigo', None)
        if isinstance(codigo, str) and codigo.strip():
            por_area.setdefault(codigo.strip(), []).append(asignatura)
        else:
            internas.append(asignatura)
    return por_area, internas


# ══════════════════════════ ASISTENCIA ══════════════════════════

def dias_no_justificados(asistencias, fecha_inicio=None, fecha_fin=None):
    """Días con ausencia NO justificada, deduplicados por fecha.

    `excusa` es ausencia JUSTIFICADA y NO entra: contarla como injustificada
    castigaría al estudiante que sí avisó.
    """
    por_dia = {}
    for a in asistencias or ():
        fecha = getattr(a, 'fecha', None)
        if fecha is None:
            continue
        if fecha_inicio is not None and fecha < fecha_inicio:
            continue
        if fecha_fin is not None and fecha > fecha_fin:
            continue
        estado = getattr(a, 'estado', None)
        previo = por_dia.get(fecha)
        if previo is None or (_PRIORIDAD_ESTADO.get(estado, 0)
                              > _PRIORIDAD_ESTADO.get(previo, 0)):
            por_dia[fecha] = estado
    return sum(1 for e in por_dia.values() if e == AUSENCIA_NO_JUSTIFICADA)


def porcentaje_ausencias(ausencias, dias_trabajados):
    """El porcentaje que A2 espera, o `(None, diagnóstico)`.

    POLÍTICA: FAIL-CLOSED, Y DECLARADA
        El denominador es `AnoEscolar.dias_trabajados`, un JSON {mes: días}
        que el colegio llena a mano. Si está vacío o suma cero, NO se
        sustituye por «las filas de asistencia que existan»: un curso al que
        se le pasó lista tres días daría 33% de ausencias con una sola falta.
        Se devuelve None, A2 emite su bloqueo y el documento no certifica.

        Tampoco se acepta un resultado imposible: más ausencias que días
        trabajados significa que uno de los dos datos está mal, y adivinar
        cuál sería inventar.
    """
    if not isinstance(dias_trabajados, int) or isinstance(dias_trabajados, bool):
        return None, DIAG_DIAS_TRABAJADOS_NO_DECLARADOS
    if dias_trabajados <= 0:
        return None, DIAG_DIAS_TRABAJADOS_NO_DECLARADOS
    if ausencias > dias_trabajados:
        return None, DIAG_ASISTENCIA_INCOHERENTE
    return (ausencias / dias_trabajados) * 100.0, None


def sumar_dias_trabajados(ano):
    """Total de días trabajados declarados en el año, o None si no hay."""
    if ano is None:
        return None
    try:
        por_mes = ano.get_dias_trabajados()
    except Exception:
        return None
    if not por_mes:
        return None
    total = 0
    for valor in por_mes.values():
        try:
            entero = int(valor)
        except (TypeError, ValueError):
            continue
        if entero > 0:
            total += entero
    return total if total > 0 else None


# ══════════════════ RESULTADOS POR ÁREA / ASIGNATURA ══════════════════

def resultados_secundaria(asignaturas, competencias_por_asig, extras_por_asig,
                          cf_secundaria):
    """Un resultado de A1 por cada asignatura OFICIAL del curso.

    `cf_secundaria` es `app._calcular_cf_secundaria`, inyectado para no
    importar `app` desde aquí. Se le pasan las competencias YA cargadas, así
    que no consulta la base; la fórmula es exactamente la misma que usa el
    boletín para imprimir la CF.

    La elección entre `nota_final`, `especial_final`, `extraordinaria_final`
    y `completiva_final` la hace A1, no este módulo. Por eso desaparece la
    cadena `or` que se comía un 0 legítimo.
    """
    resultados = []
    for asignatura in asignaturas:
        codigo = getattr(asignatura, 'area_curricular_codigo', None)
        if not (isinstance(codigo, str) and codigo.strip()):
            continue    # materia interna: fuera de la promoción oficial
        comps = competencias_por_asig.get(asignatura.id) or []
        cf_oficial, _literal, cf_exacto = cf_secundaria(
            None, None, None, None, con_exacto=True, competencias=list(comps))
        resultados.append(RA.resolver_nota_secundaria(
            evaluacion=extras_por_asig.get(asignatura.id),
            cf_exacto=cf_exacto,
            cf_oficial=cf_oficial,
            area_curricular_codigo=codigo.strip(),
        ))
    return resultados


def _participa_en_promocion(codigo, codigos_esperados):
    """¿Este bloque cuenta para la promoción de ESTE grado?

    IDENTIDAD NO ES PARTICIPACIÓN, y confundirlas hace daño en las dos
    direcciones. Un colegio privado que enseña Inglés en 1.º tiene una
    asignatura con identidad LEI perfectamente correcta; lo que pasa es que
    LEI no está en el currículo oficial de 1.º. Hacerla participar reprobaría
    a un niño de primero por una materia que la norma no le exige.

    Cuando no hay currículo declarado —`None`— no se deja pasar nada: sin
    saber qué se espera, no se puede decir qué participa, y A2 bloquea de
    todos modos por currículo no declarado.
    """
    if not codigos_esperados:
        return False
    return codigo in set(codigos_esperados)


def resultados_primaria(asignaturas, competencias_por_asig,
                        recuperaciones_por_asig, grado_numero,
                        codigos_oficiales_esperados=None):
    """`(resultados, adicionales)` — los que participan y los que no.

    Las competencias se pasan tal cual: A1 llama a `cf_area()`, que ya exige
    el conjunto oficial completo. Aquí no se recalcula CF, ni RP, ni
    Recuperación Final, ni Especial.

    NO SE DEDUPLICA. Si el curso tiene DOS asignaturas con MAT y MAT es
    esperada, las dos llegan a A2: su selección por multiconjunto es la que
    tiene que detectar el área sobrante. Silenciar una aquí escondería un
    problema de configuración real. Eso es distinto de una materia cuyo
    código no pertenece al currículo del grado, que sí se aparta.
    """
    resultados, adicionales = [], []
    for asignatura in asignaturas:
        codigo = getattr(asignatura, 'area_curricular_codigo', None)
        if not (isinstance(codigo, str) and codigo.strip()):
            continue    # materia interna: nunca tuvo identidad oficial
        codigo = codigo.strip()
        if not _participa_en_promocion(codigo, codigos_oficiales_esperados):
            adicionales.append(codigo)
            continue
        resultados.append(RA.resolver_nota_primaria(
            competencias=competencias_por_asig.get(asignatura.id) or [],
            recuperacion=recuperaciones_por_asig.get(asignatura.id),
            grado_numero=grado_numero,
            area_curricular_codigo=codigo,
        ))
    return resultados, adicionales


# ══════════════════════════ CONTEXTO ══════════════════════════

def construir_contexto(grado_numero, nivel, porcentaje, diagnosticos):
    """El contexto que A2 recibe, con lo que REALMENTE existe en la base.

    Tres datos que A2 sabe pedir y que hoy EducaOne no guarda en ninguna
    parte. A3 no los inventa ni los infiere: van en None y se anota por qué.

      · `alfabetizacion_inicial` (3.º de Primaria) — la auditoría R4-A0
        confirmó que no hay columna, ni pantalla, ni checkbox. Nunca se
        deduce de la nota de Lengua Española.
      · `decision_asistencia` — no hay decisión colegiada persistida.
      · `decision_excepcional_segundo` — una repetición excepcional de 2.º es
        un acuerdo del equipo docente, no un cálculo. Sin acta guardada, no
        existe.

    Un None aquí no es un descuido: es lo que hace que A2 bloquee en vez de
    certificar con datos que nadie cargó.
    """
    contexto = {'porcentaje_ausencias_no_justificadas': porcentaje}

    if nivel == RA.NIVEL_PRIMARIA and grado_numero == GRADO_ALFABETIZACION:
        contexto['alfabetizacion_inicial'] = None
        diagnosticos.append(DIAG_ALFABETIZACION_SIN_FUENTE)

    if porcentaje is None or porcentaje > PA.MAX_AUSENCIAS_NO_JUSTIFICADAS:
        diagnosticos.append(DIAG_DECISION_ASISTENCIA_SIN_FUENTE)

    if nivel == RA.NIVEL_PRIMARIA and grado_numero == 2:
        diagnosticos.append(DIAG_EXCEPCION_2DO_SIN_FUENTE)

    return contexto


# ══════════════════════════ SALIDA ÚNICA ══════════════════════════

def construir_situacion_estudiante(nivel, grado_numero, resultados,
                                   codigos_oficiales_esperados, contexto,
                                   diagnosticos=None, fuente_curriculo=None):
    """Lo que consume CUALQUIER documento. Una sola forma, un solo motor.

    Devuelve el paquete entero —resultados por área, currículo esperado,
    contexto realmente disponible y la salida completa de A2— para que ningún
    consumidor tenga que rearmar una parte por su cuenta.
    """
    situacion = PA.resolver_situacion_estudiante(
        nivel, grado_numero, resultados,
        codigos_oficiales_esperados=codigos_oficiales_esperados,
        contexto=contexto,
    )
    return {
        'nivel': nivel,
        'grado_numero': grado_numero,
        'resultados': tuple(resultados),
        'codigos_oficiales_esperados': codigos_oficiales_esperados,
        'fuente_curriculo': fuente_curriculo,
        'contexto': dict(contexto),
        'situacion': situacion,
        'diagnosticos': tuple(diagnosticos or ()),
    }


# ══════════════════════════ PRESENTACIÓN ══════════════════════════
#
# La condición canónica NUNCA se toca para que quepa en un PDF. Lo que se
# traduce es el TEXTO. Vocabulario del acta oficial: «promovido/a,
# aplazado/a, reprobado/a».

TEXTO_SITUACION = {
    PA.PROMOVIDO: 'PROMOVIDO/A',
    PA.APLAZADO: 'APLAZADO/A — pendiente del proceso de recuperación',
    PA.REPROBADO: 'REPROBADO/A — repite el grado',
    PA.EN_PROCESO: 'PENDIENTE — no puede certificarse todavía',
}

# Códigos del Registro Escolar para la columna de situación final.
SIGLA_SITUACION = {
    PA.PROMOVIDO: 'AP',
    PA.APLAZADO: 'AZ',
    PA.REPROBADO: 'RP',
    PA.EN_PROCESO: '',
}

# La portada del boletín de Primaria tiene tres casillas —Promovido,
# Repitente, Aplazado— y `boletin_primaria` marca la X buscando estas palabras
# en el texto. EN_PROCESO no aparece: no marca ninguna, que es lo correcto
# cuando A2 no certifica.
MARCA_BOLETIN_PRIMARIA = {
    PA.PROMOVIDO: 'promovido',
    PA.APLAZADO: 'aplazado',
    PA.REPROBADO: 'repitente',
    PA.EN_PROCESO: None,
}

# Vocabulario que ya consume el frontend de Primaria. Se conserva para no
# romperlo; lo que cambia es QUIÉN decide el valor, no cómo se llama.
CONDICION_LEGACY_PRIMARIA = {
    PA.PROMOVIDO: 'promovido',
    PA.APLAZADO: 'repitente_condicional',
    PA.REPROBADO: 'repite',
    PA.EN_PROCESO: 'en_proceso',
}


def texto_situacion(situacion):
    """El texto que se imprime, derivado de la condición canónica."""
    return TEXTO_SITUACION.get(situacion.get('condicion'),
                               TEXTO_SITUACION[PA.EN_PROCESO])


def detalle_situacion(situacion, diagnosticos=()):
    """Una línea corta con el motivo, para el documento que tenga hueco.

    Cuando A2 se niega a certificar, lo que importa es POR QUÉ: el bloqueo
    principal, y si no hay, el motivo.
    """
    bloqueos = situacion.get('bloqueos') or ()
    if bloqueos:
        return str(bloqueos[0]).replace('_', ' ').capitalize()
    faltantes = tuple(d for d in diagnosticos or ())
    if situacion.get('condicion') == PA.EN_PROCESO and faltantes:
        return str(faltantes[0]).replace('_', ' ').capitalize()
    motivo = situacion.get('motivo')
    return str(motivo).replace('_', ' ').capitalize() if motivo else ''


def situacion_boletin_secundaria(situacion, diagnosticos=()):
    """El dict `{promovido, repitente, condicion}` que espera la plantilla.

    Las dos casillas del boletín son «Promovido/a» y «Repitente». No hay una
    para «Aplazado» ni para «Pendiente», así que en esos casos NO se marca
    ninguna: marcar una equivaldría a certificar una decisión que A2 se negó
    a tomar. El texto de la condición sí lo dice.

    SEXTO DE SECUNDARIA: A2 puede devolver PROMOVIDO con la advertencia
    `REQUIERE_PROCESO_DE_TITULACION_PRUEBAS_NACIONALES`. Eso se marca como
    promovido —porque lo está— y NUNCA como «Graduado», «Egresado» ni
    «Titulado»: la titulación es otra fase y depende de las Pruebas
    Nacionales, que EducaOne no conoce.
    """
    condicion = situacion.get('condicion')
    texto = texto_situacion(situacion)
    detalle = detalle_situacion(situacion, diagnosticos)
    if detalle and condicion != PA.PROMOVIDO:
        texto = '%s (%s)' % (texto, detalle)
    return {
        'promovido': condicion == PA.PROMOVIDO,
        'repitente': condicion == PA.REPROBADO,
        'condicion': texto,
    }
