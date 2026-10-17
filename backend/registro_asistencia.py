"""
registro_asistencia.py
======================
Construye la matriz de asistencia para el Registro Escolar MINERD.

La prioridad de esta versión es tomar como base los días lectivos esperados:
1. Año escolar activo
2. Horario real del curso / asignatura
3. Días no laborables
4. Registros de asistencia capturados

Si el sistema no tiene suficiente estructura para inferir días esperados,
cae en modo legacy usando únicamente las fechas registradas.
"""

from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, List, Optional, Set

from sqlalchemy.orm import Session

import asistencia_canonica as ASIS
from models import (
    AnoEscolar,
    Asistencia,
    Curso,
    DiaNoLaborable,
    Estudiante,
    Horario,
    SesionNoImpartida,
)


ESTADO_A_CODIGO = {
    'presente': 'P',
    'ausente': 'A',
    'tardanza': 'T',
    'excusa': 'E',
    'justificada': 'E',
}

MES_NUM_A_NOMBRE = {
    1: 'enero', 2: 'febrero', 3: 'marzo', 4: 'abril', 5: 'mayo', 6: 'junio',
    7: 'julio', 8: 'agosto', 9: 'septiembre', 10: 'octubre', 11: 'noviembre', 12: 'diciembre',
}

DIA_NUM_A_NOMBRE = {
    0: 'Lunes',
    1: 'Martes',
    2: 'Miércoles',
    3: 'Jueves',
    4: 'Viernes',
    5: 'Sábado',
    6: 'Domingo',
}

MES_CLAVE_CORTA = {
    1: 'ene', 2: 'feb', 3: 'mar', 4: 'abr', 5: 'may', 6: 'jun',
    7: 'jul', 8: 'ago', 9: 'sep', 10: 'oct', 11: 'nov', 12: 'dic',
}


# ─────────────────────────── REG-1 · TIEMPO DEL REGISTRO ───────────────────────────
#
# Un mes del Registro es la pareja (año, mes), nunca el número de mes solo, y la
# secuencia sale del año escolar DE ESE COLEGIO: de `fecha_inicio` a `fecha_fin`.
# Un centro que empieza el 7 de septiembre imprime septiembre en el primer hueco;
# uno que empieza en agosto, agosto. No hay un calendario universal agosto→julio.
#
# Cada mes conserva su POSICIÓN aunque esté vacío: si una materia no tiene marcas
# en septiembre, septiembre sigue ocupando el primer hueco y octubre el segundo.
# Dónde se imprime una marca lo decide su fecha real, no cuándo se digitó: una
# asistencia del 15-sep cargada en octubre cae en septiembre, en su columna.


class RegistroAsistenciaError(Exception):
    """El Registro no se puede emitir sin esconder o mover asistencia.

    `detalle` es un dict serializable que app.py devuelve tal cual (422).
    """

    def __init__(self, detalle: Dict):
        self.detalle = detalle
        super().__init__(detalle.get('mensaje', detalle.get('motivo', 'asistencia')))


class AsistenciaFueraDelAnoEscolar(RegistroAsistenciaError):
    """Hay asistencia registrada fuera de fecha_inicio..fecha_fin del año."""


class MesesExcedenPlantilla(RegistroAsistenciaError):
    """El año tiene más meses que huecos la hoja oficial."""


class MatrizAsistencia(list):
    """La lista de meses de siempre, más lo que el Registro necesita saber.

    Sigue siendo una `list` de dicts de mes, así que todos los consumidores
    existentes la recorren igual. Además lleva:
      · `fuera_de_rango`: asistencias cuya fecha no cae en el año escolar. NO se
        colocan en ningún mes —no se mueven ni se esconden— y el Registro se
        niega a emitirse mientras existan (ver `verificar_dentro_del_ano`).
      · `meses_del_ano`: la secuencia (año, mes) que define los huecos.
    """

    def __init__(self, meses=(), fuera_de_rango=None, meses_del_ano=None,
                 inicio=None, fin=None):
        super().__init__(meses)
        self.fuera_de_rango = list(fuera_de_rango or [])
        self.meses_del_ano = list(meses_del_ano or [])
        self.inicio = inicio.isoformat() if inicio else None
        self.fin = fin.isoformat() if fin else None


def meses_del_ano(ano: Optional[AnoEscolar]) -> List[tuple]:
    """Secuencia cronológica (año, mes) de fecha_inicio a fecha_fin, ambos incluidos.

    Vacía si el año no tiene las dos fechas: entonces no hay huecos que respetar
    y los meses salen de las propias marcas, también en orden cronológico.
    """
    if not ano or not ano.fecha_inicio or not ano.fecha_fin or ano.fecha_inicio > ano.fecha_fin:
        return []
    y, m = ano.fecha_inicio.year, ano.fecha_inicio.month
    fin = (ano.fecha_fin.year, ano.fecha_fin.month)
    salida = []
    while (y, m) <= fin:
        salida.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return salida


def verificar_dentro_del_ano(matriz, contexto: str = '') -> None:
    """FAIL CLOSED: asistencia fuera del año escolar no tiene mes donde
    imprimirse sin moverla de fecha. Se rechaza con las fechas exactas, para
    que se corrijan en origen. Una matriz vieja (lista simple) pasa."""
    fuera = getattr(matriz, 'fuera_de_rango', None) or []
    if not fuera:
        return
    fechas = sorted({f['fecha'] for f in fuera})
    raise AsistenciaFueraDelAnoEscolar({
        'motivo': 'ASISTENCIA_FUERA_DEL_ANO_ESCOLAR',
        'mensaje': (f'{contexto}: hay {len(fuera)} asistencia(s) registradas fuera del '
                    f'año escolar ({getattr(matriz, "inicio", None)} a '
                    f'{getattr(matriz, "fin", None)}). No se imprimen en otro mes ni se '
                    f'ocultan: corrija su fecha o el rango del año antes de emitir el '
                    f'Registro.').lstrip(': '),
        'contexto': contexto,
        'total': len(fuera),
        'fechas': [f.isoformat() for f in fechas[:50]],
        'rango_ano': [getattr(matriz, 'inicio', None), getattr(matriz, 'fin', None)],
    })


def verificar_huecos(meses_necesarios: int, huecos: int, contexto: str = '') -> None:
    """FAIL CLOSED: más meses que huecos en la hoja. Imprimir solo los que
    caben escondería el resto, así que no se imprime."""
    if meses_necesarios > huecos:
        raise MesesExcedenPlantilla({
            'motivo': 'MESES_EXCEDEN_PLANTILLA',
            'mensaje': (f'{contexto}: el año escolar ocupa {meses_necesarios} meses y la '
                        f'hoja oficial solo tiene {huecos}. No se imprime un Registro '
                        f'recortado.').lstrip(': '),
            'contexto': contexto,
            'meses': meses_necesarios,
            'huecos': huecos,
        })


def meses_necesarios(matriz) -> int:
    """Huecos que pide la matriz: hasta el último mes con posición, inclusive."""
    posiciones = [m.get('posicion', i) for i, m in enumerate(matriz or []) if m]
    return max(posiciones) + 1 if posiciones else 0


def _dias_no_laborables_set(db: Session, colegio_id: Optional[int], ano: Optional[AnoEscolar]) -> Set:
    q = db.query(DiaNoLaborable).filter(DiaNoLaborable.activo == True)  # noqa: E712
    if colegio_id is not None:
        q = q.filter(DiaNoLaborable.colegio_id == colegio_id)

    dias = set()
    for item in q.all():
        if item.recurrente:
            if item.fecha:
                dias.add((item.fecha.month, item.fecha.day))
        elif ano and item.ano_escolar_id == ano.id and item.fecha:
            dias.add(item.fecha)
        elif item.ano_escolar_id is None and item.fecha:
            dias.add(item.fecha)
    return dias


def _obtener_ano_escolar(db: Session, curso: Optional[Curso]) -> Optional[AnoEscolar]:
    if not curso or curso.colegio_id is None:
        return None
    return db.query(AnoEscolar).filter_by(colegio_id=curso.colegio_id, activo=True).first()


def _obtener_dias_horario(
    db: Session,
    curso_id: int,
    asignatura_id: Optional[int] = None,
) -> Set[str]:
    q = db.query(Horario).filter(
        Horario.curso_id == curso_id,
        Horario.activo == True,  # noqa: E712
        Horario.tipo_bloque == 'clase',
    )
    if asignatura_id is not None:
        q = q.filter(Horario.asignatura_id == asignatura_id)
    return {str(h.dia or '').strip() for h in q.all() if str(h.dia or '').strip()}


def _sesiones_no_impartidas(
    db: Session,
    curso_id: int,
    asignatura_id: Optional[int] = None,
) -> Dict:
    """
    S1 — las sesiones PROGRAMADAS que no se impartieron, indexadas por fecha.

    Solo aplica con `asignatura_id`: en Primaria la asistencia es del curso y no
    hay una clase concreta que declarar. Sin asignatura se devuelve vacio y todo
    lo de abajo se comporta exactamente como antes de S1.
    """
    if asignatura_id is None:
        return {}
    filas = db.query(SesionNoImpartida).filter(
        SesionNoImpartida.curso_id == curso_id,
        SesionNoImpartida.asignatura_id == asignatura_id,
        SesionNoImpartida.activo == True,  # noqa: E712
    ).all()
    return {f.fecha: f for f in filas if f.fecha}


def _construir_fechas_esperadas(
    ano: Optional[AnoEscolar],
    dias_horario: Set[str],
    dias_no_laborables: Set,
) -> Dict[tuple, List]:
    """Días de clase esperados por horario, indexados por (año, mes)."""
    if not ano or not ano.fecha_inicio or not ano.fecha_fin or not dias_horario:
        return {}

    fechas_por_mes: Dict[tuple, List] = defaultdict(list)
    actual = ano.fecha_inicio

    while actual <= ano.fecha_fin:
        dia_nombre = DIA_NUM_A_NOMBRE.get(actual.weekday())
        es_no_laborable = actual in dias_no_laborables or (actual.month, actual.day) in dias_no_laborables

        if dia_nombre in dias_horario and not es_no_laborable:
            fechas_por_mes[(actual.year, actual.month)].append(actual)

        actual += timedelta(days=1)

    return dict(fechas_por_mes)


def build_asistencia_registro(
    db: Session,
    curso_id: int,
    asignatura_id: Optional[int] = None,
    estudiantes: Optional[List[Estudiante]] = None,
) -> List[Dict]:
    """
    Construye la matriz de asistencia por mes para un curso.

    El resultado prioriza días esperados por horario. Si no existen
    suficientes datos estructurales, cae a modo legacy usando solo
    fechas con registros reales.
    """
    if estudiantes is None:
        estudiantes = db.query(Estudiante).filter_by(
            curso_id=curso_id, activo=True
        ).order_by(Estudiante.no_lista).all()

    if not estudiantes:
        return []

    est_ids = [e.id for e in estudiantes]
    est_index = {e.id: idx + 1 for idx, e in enumerate(estudiantes)}

    curso = db.query(Curso).filter_by(id=curso_id).first()
    ano = _obtener_ano_escolar(db, curso)
    dias_horario = _obtener_dias_horario(db, curso_id, asignatura_id=asignatura_id)
    dias_no_laborables = _dias_no_laborables_set(db, curso.colegio_id if curso else None, ano)
    fechas_esperadas_por_mes = _construir_fechas_esperadas(ano, dias_horario, dias_no_laborables)
    no_impartidas = _sesiones_no_impartidas(db, curso_id, asignatura_id=asignatura_id)

    q = db.query(Asistencia).filter(
        Asistencia.estudiante_id.in_(est_ids),
        Asistencia.curso_id == curso_id,
    )
    if asignatura_id is not None:
        q = q.filter(Asistencia.asignatura_id == asignatura_id)

    registros = q.all()

    # ASISTENCIA CANÓNICA · primera lista de cada estudiante en el año, en
    # CUALQUIER curso o materia: es lo que usa el motor para decidir desde
    # cuándo le cuenta la asistencia a quien se dio de alta tarde. Una sola
    # consulta agrupada para todo el curso.
    from sqlalchemy import func as _func
    _desde = getattr(ano, 'fecha_inicio', None) if ano else None
    _qp = db.query(Asistencia.estudiante_id, _func.min(Asistencia.fecha)).filter(
        Asistencia.estudiante_id.in_(est_ids))
    if _desde is not None:
        _qp = _qp.filter(Asistencia.fecha >= _desde)
    primera_por_est = dict(_qp.group_by(Asistencia.estudiante_id).all())
    if not registros and not fechas_esperadas_por_mes:
        return []

    # REG-1 · los huecos del Registro: (año, mes) de fecha_inicio a fecha_fin.
    secuencia = meses_del_ano(ano)
    en_ano = set(secuencia)

    # Una marca vive en el (año, mes) de su fecha REAL. Si esa fecha no cae en
    # el año escolar no se coloca en ningún mes —ni en el mismo número de mes de
    # otro año, que es lo que pasaba al indexar solo por mes—: queda anotada en
    # `fuera_de_rango` y el Registro se niega a emitirse con ella escondida.
    prioridad = {'A': 4, 'T': 3, 'E': 2, 'P': 1, '': 0}
    por_mes: Dict[tuple, Dict[int, Dict[int, str]]] = defaultdict(lambda: defaultdict(dict))
    fuera_de_rango = []

    for r in registros:
        codigo = ESTADO_A_CODIGO.get((r.estado or '').lower(), '')
        if not codigo:
            continue
        if secuencia and not (ano.fecha_inicio <= r.fecha <= ano.fecha_fin):
            fuera_de_rango.append({'fecha': r.fecha, 'estudiante_id': r.estudiante_id,
                                   'asignatura_id': r.asignatura_id})
            continue
        clave = (r.fecha.year, r.fecha.month)
        existente = por_mes[clave][r.fecha.day].get(r.estudiante_id, '')
        if prioridad.get(codigo, 0) > prioridad.get(existente, 0):
            por_mes[clave][r.fecha.day][r.estudiante_id] = codigo

    # v2.19.7: TODO día con asistencia registrada tiene que tener su columna,
    # aunque el horario no lo esperara (cambio de horario, día recuperado...).
    # Ahora se añade en SU (año, mes): con la clave completa ya no hay un mismo
    # número de mes de dos años distintos compitiendo por las mismas columnas.
    # No se inventa ninguna marca: el día agregado se llena solo con lo que
    # haya en la base.
    for clave, dias_dict in por_mes.items():
        lista = fechas_esperadas_por_mes.setdefault(clave, [])
        ya = {f.day for f in lista}
        for dia in dias_dict:
            if dia not in ya:
                lista.append(date(clave[0], clave[1], dia))

    # S1 — LA FECHA JUSTIFICADA CONSERVA SU COLUMNA.
    #
    # Esto es lo que pide el Registro en papel: el dia en que no se dio la clase
    # no desaparece de la hoja, se queda en su sitio con el motivo escrito. Sin
    # este bloque la columna podia perderse por dos vias: si la fecha cae en un
    # DiaNoLaborable, `_construir_fechas_esperadas` ya la habia descartado; y si
    # el horario cambio despues, el dia de la semana ya no coincide.
    #
    # No se inventa ninguna marca: la columna entra vacia y lo unico que lleva
    # es la etiqueta del motivo.
    for _fecha in no_impartidas:
        _clave = (_fecha.year, _fecha.month)
        if secuencia and _clave not in en_ano:
            continue   # una sesión fuera del año no abre un mes que no existe
        _lista = fechas_esperadas_por_mes.setdefault(_clave, [])
        if _fecha.day not in {f.day for f in _lista}:
            _lista.append(_fecha)

    # REG-1 · con año escolar, TODOS sus meses entran y en su orden, tengan o no
    # marcas: un mes vacío sigue ocupando su hueco. Sin fechas de año (legacy),
    # los meses salen de las marcas, igualmente en orden cronológico real.
    if secuencia:
        meses_presentes = secuencia
    else:
        meses_presentes = sorted(fechas_esperadas_por_mes.keys())
    dias_trabajados_cfg = ano.get_dias_trabajados() if ano else {}

    resultado = MatrizAsistencia(
        fuera_de_rango=fuera_de_rango, meses_del_ano=secuencia,
        inicio=getattr(ano, 'fecha_inicio', None) if secuencia else None,
        fin=getattr(ano, 'fecha_fin', None) if secuencia else None)
    for posicion, clave in enumerate(meses_presentes):
        anio_mes, mes_num = clave
        fechas_mes = fechas_esperadas_por_mes.get(clave, [])
        # Un (año, mes) tiene un solo calendario: ordenar por número de día es
        # ordenar por fecha. Una marca digitada fuera de orden (25-sep, luego
        # 8-sep) se imprime igual en su columna cronológica.
        dias_unicos = sorted({f.day for f in fechas_mes})
        dias_con_registro = sorted(por_mes.get(clave, {}).keys())
        cfg_mes = dias_trabajados_cfg.get(MES_CLAVE_CORTA.get(mes_num, ''), 0) if dias_trabajados_cfg else 0

        # S1 — los dias de este mes en que la clase no se impartio, por numero
        # de dia, que es como se indexan las columnas de la hoja.
        sesiones_mes = {f.day: sesion for f, sesion in no_impartidas.items()
                        if (f.year, f.month) == clave and f.day in set(dias_unicos)}
        dias_no_impartidos = sorted(sesiones_mes)
        dias_computables = len(dias_unicos) - len(dias_no_impartidos)

        filas = []
        # S1 — LA COBERTURA ES DE LO QUE SE IMPARTIO. Una columna justificada no
        # tiene que llenarse: contarla como celda esperada haria que el validador
        # pidiera asistencia de una clase que no se dio, que es justo lo que S1
        # viene a evitar.
        # ASISTENCIA CANÓNICA · la fecha real de cada columna, para saber si
        # ese día le APLICA al estudiante (inicio del año o alta / retiro).
        fecha_por_dia = {}
        for _f in sorted(fechas_mes):
            fecha_por_dia.setdefault(_f.day, _f)

        celdas_esperadas = 0
        celdas_con_registro = 0

        for est in estudiantes:
            valores = []
            presentes = 0
            tardanzas = 0
            ausentes = 0
            con_dato = 0
            esperadas_est = 0

            for dia in dias_unicos:
                codigo = por_mes.get(clave, {}).get(dia, {}).get(est.id, '')
                _fecha_col = fecha_por_dia.get(dia)
                # NO APLICA: antes de que el estudiante perteneciera al centro o
                # después de su retiro. La celda se marca «-» y no cuenta para
                # nada: ni numerador, ni denominador, ni cobertura. Una marca
                # que exista igual se conserva a la vista —no se oculta
                # historia— pero tampoco se suma.
                if _fecha_col is not None and not ASIS.aplica_en(
                        ano, est, _fecha_col, primera_por_est.get(est.id)):
                    valores.append(codigo or '-')
                    continue
                valores.append(codigo)
                # S1 — UN DIA NO IMPARTIDO NO CUENTA PARA NADIE. Queda fuera del
                # numerador, del denominador y de la cobertura: si no hubo clase,
                # nadie estuvo presente, nadie falto y no hay nada que capturar.
                # El valor de la celda se conserva tal cual esta en la base —no se
                # oculta historia— pero no se suma en ningun conteo. La escritura
                # de asistencia sobre una sesion declarada ya esta cerrada en
                # app.py; esto cubre lo que pudiera venir de antes.
                if dia in sesiones_mes:
                    continue
                celdas_esperadas += 1
                esperadas_est += 1
                if codigo:
                    celdas_con_registro += 1
                    con_dato += 1
                if codigo == 'P':
                    presentes += 1
                elif codigo == 'T':
                    tardanzas += 1
                elif codigo == 'A':
                    ausentes += 1

            # ASISTENCIA CANÓNICA · la celda vacía es SIN DATO, no ausencia, y
            # la tardanza es asistencia, como en el boletín y en A2. El
            # porcentaje es OFICIAL solo con cobertura completa del mes para
            # ese estudiante; con huecos no se imprime (None): ni un 0 que diga
            # «no vino nunca» ni un 100 sacado de pocos días.
            cobertura_completa = esperadas_est > 0 and con_dato == esperadas_est
            porcentaje = (round(((presentes + tardanzas) / con_dato) * 100, 1)
                          if cobertura_completa else None)
            filas.append({
                'no': est_index[est.id],
                'estudiante_id': est.id,
                'nombre': est.nombre_completo,
                'valores': valores,
                'presentes': presentes,
                'tardanzas': tardanzas,
                'ausentes': ausentes,
                'con_dato': con_dato,
                'dias_aplicables': esperadas_est,
                'cobertura_completa': cobertura_completa,
                'porcentaje': porcentaje,
            })

        fuente = 'horario' if dias_horario else 'registros'
        resultado.append({
            'mes': MES_NUM_A_NOMBRE.get(mes_num, str(mes_num)),
            'mes_num': mes_num,
            # REG-1: identidad completa del mes y su hueco en la hoja oficial
            # (0 = el mes de fecha_inicio). Los generadores colocan por esto.
            'anio': anio_mes,
            'clave': f'{anio_mes:04d}-{mes_num:02d}',
            'posicion': posicion,
            'dias': dias_unicos,
            'total_dias': len(dias_unicos),
            # S1: `total_dias` sigue siendo el numero de COLUMNAS —la geometria
            # del PDF depende de el— y `dias_computables` es el denominador del
            # porcentaje. Antes de S1 eran el mismo numero y lo siguen siendo en
            # cuanto no hay ninguna sesion declarada.
            'dias_computables': dias_computables,
            'dias_no_impartidos': dias_no_impartidos,
            'no_impartidas': {
                dia: {
                    'motivo_codigo': ses.motivo_codigo,
                    'motivo': ses.motivo_nombre,
                    'motivo_detalle': ses.motivo_detalle,
                    'etiqueta': ses.etiqueta,
                } for dia, ses in sorted(sesiones_mes.items())
            },
            'filas': filas,
            'fuente_dias': fuente,
            'dias_horario': sorted(dias_horario),
            'dias_con_registro': dias_con_registro,
            'dias_trabajados_configurados': cfg_mes,
            'dias_esperados_segun_horario': len(dias_unicos),
            'cobertura_registro_pct': round((celdas_con_registro / celdas_esperadas) * 100, 1) if celdas_esperadas else 0.0,
        })

    return resultado


def debug_render_asistencia(matriz: List[Dict]) -> str:
    if not matriz:
        return "(sin asistencia registrada)"

    salida = []
    for mes_data in matriz:
        meta = (
            f"fuente={mes_data.get('fuente_dias', 'desconocida')}, "
            f"esperados={mes_data.get('dias_esperados_segun_horario', 0)}, "
            f"cfg={mes_data.get('dias_trabajados_configurados', 0)}, "
            f"cobertura={mes_data.get('cobertura_registro_pct', 0)}%"
        )
        salida.append(f"\n=== MES: {mes_data['mes'].upper()} ({mes_data['total_dias']} días) ===")
        salida.append(meta)
        header_dias = "DÍAS: " + " | ".join(f"{d:>2}" for d in mes_data['dias'])
        salida.append(header_dias)
        salida.append("-" * len(header_dias))

        for fila in mes_data['filas']:
            valores_str = "  ".join(f"{v or '.':>1}" for v in fila['valores'])
            nombre_corto = fila['nombre'][:25]
            salida.append(
                f"{fila['no']:2}. {nombre_corto:<25} | {valores_str} "
                f"| P={fila['presentes']} A={fila['ausentes']} ({fila['porcentaje']}%)"
            )

    return "\n".join(salida)
