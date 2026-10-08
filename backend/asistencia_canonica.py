# -*- coding: utf-8 -*-
"""
asistencia_canonica.py — LA asistencia de un estudiante en un año escolar.

UNA SOLA FUENTE
    Antes había tres lecturas distintas del mismo dato:

      · A2 (vía RAC) dividía las ausencias entre `dias_trabajados` y trataba
        el día sin lista como «no consta que faltara», es decir, PRESENTE;
      · el boletín hacía lo mismo para el anual y otra cuenta por período;
      · el Registro Escolar dividía los presentes entre los días del horario
        y trataba la celda vacía como AUSENTE.

    Este módulo es el único que clasifica días. Motor, boletín, Registro y
    Cierre consumen su resultado; ninguno vuelve a contar por su cuenta.

UNA LÓGICA PARA TODOS LOS COLEGIOS
    No hay ninguna fecha, colegio ni calendario fijo aquí. Todo sale de los
    datos del colegio que se le pasan: su `AnoEscolar` (fecha_inicio,
    fecha_fin, P1-P4), su calendario (`DiaNoLaborable`, sábado/domingo) y,
    de cada estudiante, su fecha de alta y su fecha de retiro. No hay ninguna
    columna nueva: todo eso ya existía.

DESDE CUÁNDO CUENTA LA ASISTENCIA DE UN ESTUDIANTE
    · Normalmente, desde `AnoEscolar.fecha_inicio` del colegio.
    · Si la ficha se dio de alta DESPUÉS de iniciado el año (alumno nuevo o
      trasladado), desde su alta en EducaOne (`Estudiante.fecha_ingreso`).
      Los días anteriores NO APLICAN: ni presentes ni ausentes.
    · Pero si ya tiene listas pasadas ANTES de esa alta (fichas recreadas o
      importadas tarde: en el piloto hay 187 marcas así), manda la primera
      lista: una marca real nunca se descarta por la fecha de la ficha.
    · Hasta `fecha_retiro` si se retiró, y nunca más allá de hoy.

PRINCIPIOS (decididos por el usuario, no por este código)
    · Sin fila NO es presente y NO es ausente: es SIN DATO.
    · La excusa CUBRE el día, pero no es ausencia injustificada.
    · Más del 20 % sigue yendo al gate humano de A2; nada se reprueba aquí.

PORCENTAJE vs. COBERTURA
    Son dos cosas distintas y se informan por separado:

      · COBERTURA = días con dato / días lectivos que le aplican.
      · PORCENTAJE OFICIAL (asistencia, ausencia, ausencia injustificada para
        A2) SOLO existe con cobertura COMPLETA. Con un solo día lectivo sin
        dato, el porcentaje oficial es None (N/D) y A2 no certifica.

    Lo registrado se sigue contando y mostrando —asistencias, ausencias,
    excusas, tardanzas— porque son hechos; lo que no se hace es convertir
    6 días de 26 en un «100 %».

DÍAS LECTIVOS
    Días hábiles del calendario DEL COLEGIO (lunes a viernes, más sábado o
    domingo si los habilita) dentro de la ventana del estudiante, menos sus
    `DiaNoLaborable` activos, más cualquier día que tenga una marca (si alguien
    pasó lista, hubo clase). La ventana termina hoy: los días futuros no son
    huecos.

Este módulo no toca la base de datos. Recibe filas ya cargadas.
"""
from datetime import timedelta

# ── Estados de un día ────────────────────────────────────────────────
PRESENTE = 'presente'
TARDANZA = 'tardanza'
EXCUSA = 'excusa'
AUSENTE = 'ausente'

# Un día con varias filas (lista por asignatura) es UN día. La prioridad es
# la que EducaOne ya usaba: si vino a una clase, vino ese día.
PRIORIDAD_ESTADO = {PRESENTE: 4, TARDANZA: 3, EXCUSA: 2, AUSENTE: 1}

# ── Estado del cálculo ───────────────────────────────────────────────
EVALUABLE = 'EVALUABLE'
ANO_SIN_FECHAS = 'ANO_SIN_FECHAS'
SIN_DIAS_APLICABLES = 'SIN_DIAS_APLICABLES'

# ── Diagnósticos (llegan a `diagnosticos` del paquete, no al contrato de A2)
DIAG_ANO_SIN_FECHAS = 'ANO_ESCOLAR_SIN_FECHAS'
DIAG_SIN_DIAS_APLICABLES = 'ASISTENCIA_SIN_DIAS_APLICABLES'
DIAG_COBERTURA_INCOMPLETA = 'ASISTENCIA_COBERTURA_INCOMPLETA'
# Informativo, no bloquea: el estudiante se incorporó con el año empezado.
ADV_ALTA_POSTERIOR = 'ASISTENCIA_DESDE_EL_ALTA_DEL_ESTUDIANTE'


def calendario(no_laborables=(), permite_sabado=False, permite_domingo=False):
    """El calendario lectivo de UN colegio.

    `no_laborables` son pares `(fecha, recurrente)`: un recurrente vale cada
    año en el mismo día y mes.
    """
    fechas, recurrentes = set(), set()
    for fecha, recurrente in no_laborables or ():
        if fecha is None:
            continue
        if recurrente:
            recurrentes.add((fecha.month, fecha.day))
        else:
            fechas.add(fecha)
    return {
        'no_laborables': fechas,
        'recurrentes': recurrentes,
        'permite_sabado': bool(permite_sabado),
        'permite_domingo': bool(permite_domingo),
    }


def _es_lectivo(fecha, cal):
    dow = fecha.weekday()
    if dow == 5 and not cal['permite_sabado']:
        return False
    if dow == 6 and not cal['permite_domingo']:
        return False
    if fecha in cal['no_laborables']:
        return False
    if (fecha.month, fecha.day) in cal['recurrentes']:
        return False
    return True


def primera_marca(filas, desde=None):
    """La fecha más temprana con una marca válida (desde `desde`), o None."""
    fechas = [getattr(f, 'fecha', None) for f in filas or ()
              if getattr(f, 'estado', None) in PRIORIDAD_ESTADO]
    fechas = [f for f in fechas if f is not None and (desde is None or f >= desde)]
    return min(fechas) if fechas else None


def inicio_estudiante(ano_ini, estudiante, primera):
    """Desde cuándo cuenta la asistencia de ESTE estudiante en el año.

    max(inicio del año, alta de la ficha) — salvo que haya listas anteriores
    al alta, en cuyo caso manda la primera lista (nunca antes del año).
    """
    alta = getattr(estudiante, 'fecha_ingreso', None)
    if alta is None or alta <= ano_ini:
        return ano_ini
    # Solo cuenta una lista DE ESTE AÑO: marcas de un año anterior no
    # adelantan el inicio.
    if primera is not None and ano_ini <= primera < alta:
        alta = primera
    return alta


def ventana(ano, estudiante, hoy, primera=None):
    """`(inicio, fin, estado, advertencias)` del estudiante en este año.

    inicio = ver `inicio_estudiante`
    fin    = min(fecha_fin del año del colegio, fecha_retiro, hoy)
    """
    ano_ini = getattr(ano, 'fecha_inicio', None)
    ano_fin = getattr(ano, 'fecha_fin', None)
    if ano_ini is None or ano_fin is None:
        return None, None, ANO_SIN_FECHAS, []

    advertencias = []
    inicio = inicio_estudiante(ano_ini, estudiante, primera)
    if inicio > ano_ini:
        advertencias.append(ADV_ALTA_POSTERIOR)

    fin = ano_fin
    retiro = getattr(estudiante, 'fecha_retiro', None)
    if retiro is not None and retiro < fin:
        fin = retiro
    if hoy is not None and hoy < fin:
        fin = hoy
    return inicio, fin, EVALUABLE, advertencias


def _dedup(filas, inicio, fin):
    """`{fecha: estado}` dentro de [inicio, fin], un voto por día."""
    por_dia = {}
    for f in filas or ():
        fecha = getattr(f, 'fecha', None)
        estado = getattr(f, 'estado', None)
        if fecha is None or estado not in PRIORIDAD_ESTADO:
            continue
        if fecha < inicio or fecha > fin:
            continue
        previo = por_dia.get(fecha)
        if previo is None or PRIORIDAD_ESTADO[estado] > PRIORIDAD_ESTADO[previo]:
            por_dia[fecha] = estado
    return por_dia


def _pct(n, d):
    return round(n * 100.0 / d, 1) if d else None


def _contar(dias):
    """Conteos de un `{fecha: estado|None}` y sus porcentajes.

    Los porcentajes OFICIALES solo existen con cobertura completa. Los
    `_registrado` son sobre los días con dato y se exponen para el detalle,
    nunca como cifra oficial.
    """
    c = {PRESENTE: 0, TARDANZA: 0, EXCUSA: 0, AUSENTE: 0, None: 0}
    for estado in dias.values():
        c[estado] = c.get(estado, 0) + 1
    lectivos = len(dias)
    con_dato = lectivos - c[None]
    asistidos = c[PRESENTE] + c[TARDANZA]
    ausentados = c[AUSENTE] + c[EXCUSA]
    completa = lectivos > 0 and c[None] == 0
    return {
        'dias_lectivos': lectivos,
        'presentes': c[PRESENTE],
        'tardanzas': c[TARDANZA],
        'excusas': c[EXCUSA],
        'ausencias': c[AUSENTE],
        'sin_dato': c[None],
        'con_dato': con_dato,
        'asistencias': asistidos,
        'ausencias_totales': ausentados,
        'cobertura_pct': _pct(con_dato, lectivos),
        'cobertura_completa': completa,
        'pct_asistencia': _pct(asistidos, lectivos) if completa else None,
        'pct_ausencia': _pct(ausentados, lectivos) if completa else None,
        'pct_asistencia_registrado': _pct(asistidos, con_dato),
        'pct_ausencia_registrado': _pct(ausentados, con_dato),
    }


def rangos_periodos(ano):
    """[(p, inicio, fin)] de P1-P4 del año del colegio. Sin rangos
    configurados, el año en cuatro (el respaldo que el boletín ya usaba)."""
    rangos = []
    for p in range(1, 5):
        ini = getattr(ano, 'p%d_inicio' % p, None)
        fin = getattr(ano, 'p%d_fin' % p, None)
        if ini and fin:
            rangos.append((p, ini, fin))
    if rangos:
        return rangos
    fi = getattr(ano, 'fecha_inicio', None)
    ff = getattr(ano, 'fecha_fin', None)
    if fi and ff and ff > fi:
        paso = (ff - fi).days // 4
        for p in range(1, 5):
            ini = fi + timedelta(days=paso * (p - 1))
            fin = ff if p == 4 else fi + timedelta(days=paso * p - 1)
            rangos.append((p, ini, fin))
    return rangos


def resolver(filas, ano, estudiante, hoy, cal=None):
    """La asistencia canónica. Ver el docstring del módulo."""
    cal = cal or calendario()
    inicio, fin, estado, advertencias = ventana(
        ano, estudiante, hoy,
        primera_marca(filas, getattr(ano, 'fecha_inicio', None)))

    base = {
        'estado': estado,
        'inicio': inicio,
        'fin': fin,
        'advertencias': list(advertencias),
        'diagnostico': None,
        'porcentaje_a2': None,
        'dias': {},
        'periodos': {},
    }
    if estado == ANO_SIN_FECHAS:
        base['diagnostico'] = DIAG_ANO_SIN_FECHAS
        base.update(_contar({}))
        return base

    marcados = _dedup(filas, inicio, fin) if inicio <= fin else {}
    dias = {}
    d = inicio
    while d <= fin:
        if d in marcados:
            dias[d] = marcados[d]
        elif _es_lectivo(d, cal):
            dias[d] = None
        d += timedelta(days=1)
    base['dias'] = dias
    base.update(_contar(dias))

    for p, p_ini, p_fin in rangos_periodos(ano):
        base['periodos']['p%d' % p] = _contar(
            {f: e for f, e in dias.items() if p_ini <= f <= p_fin})

    if not base['dias_lectivos']:
        base['estado'] = SIN_DIAS_APLICABLES
        base['diagnostico'] = DIAG_SIN_DIAS_APLICABLES
        return base

    # A2 recibe el porcentaje de ausencias INJUSTIFICADAS solo con cobertura
    # completa. Con huecos, no hay número: A2 bloquea (ASISTENCIA_NO_EVALUADA)
    # y el diagnóstico dice por qué. El 20 % y la revisión humana siguen
    # siendo de A2.
    if base['cobertura_completa']:
        base['porcentaje_a2'] = base['ausencias'] * 100.0 / base['dias_lectivos']
    else:
        base['diagnostico'] = DIAG_COBERTURA_INCOMPLETA
    return base


def anual_boletin(r):
    """El dict que consumen las plantillas como `asistencia_anual`.

    Conserva las claves de siempre. `pct_asistencia`/`pct_ausencia` son los
    OFICIALES: None si la cobertura no es completa (la plantilla imprime N/D).
    """
    return {
        'sin_registros': r['con_dato'] == 0,
        'presentes': r['presentes'],
        'tardanzas': r['tardanzas'],
        'asistencias': r['asistencias'],
        'ausencias': r['ausencias'],
        'excusas': r['excusas'],
        'ausencias_totales': r['ausencias_totales'],
        'dias_computados': r['con_dato'],
        'dias_lectivos': r['dias_lectivos'],
        'sin_dato': r['sin_dato'],
        'cobertura_pct': r['cobertura_pct'],
        'cobertura_completa': r['cobertura_completa'],
        'base_porcentaje': 'dias_lectivos' if r['cobertura_completa'] else None,
        'pct_asistencia': r['pct_asistencia'],
        'pct_ausencia': r['pct_ausencia'],
        # Sobre los días CON dato. Para detalle y pantallas internas; nunca se
        # imprime como el porcentaje oficial.
        'pct_asistencia_registrado': r['pct_asistencia_registrado'],
        'pct_ausencia_registrado': r['pct_ausencia_registrado'],
        'estado': r['estado'],
        'diagnostico': r['diagnostico'],
        'inicio': r['inicio'].isoformat() if r['inicio'] else None,
        'fin': r['fin'].isoformat() if r['fin'] else None,
    }


def periodos_boletin(r):
    """El dict `{'p1': {asistencia, ausencia, pct_*}}` de siempre."""
    out = {}
    for p in range(1, 5):
        c = r['periodos'].get('p%d' % p) or _contar({})
        out['p%d' % p] = {
            'asistencia': c['asistencias'],
            'ausencia': c['ausencias_totales'],
            'sin_dato': c['sin_dato'],
            'dias_lectivos': c['dias_lectivos'],
            'cobertura_completa': c['cobertura_completa'],
            # Nombre histórico (v2.13.3): es el % DEL PERÍODO, oficial solo
            # con cobertura completa del período.
            'pct_asistencia_anual': round(c['pct_asistencia']) if c['pct_asistencia'] is not None else None,
            'pct_ausencia_anual': round(c['pct_ausencia']) if c['pct_ausencia'] is not None else None,
        }
    return out


def aplica_en(ano, estudiante, fecha, primera=None):
    """¿Ese día cuenta para este estudiante? Para el Registro Escolar.

    La MISMA regla que `resolver`: antes de su inicio (año o alta) y después
    del retiro, NO APLICA.
    """
    ano_ini = getattr(ano, 'fecha_inicio', None)
    if ano_ini is not None and fecha < inicio_estudiante(ano_ini, estudiante, primera):
        return False
    retiro = getattr(estudiante, 'fecha_retiro', None)
    if retiro is not None and fecha > retiro:
        return False
    return True
