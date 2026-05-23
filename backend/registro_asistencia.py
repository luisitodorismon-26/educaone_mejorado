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
from datetime import timedelta
from typing import Dict, List, Optional, Set

from sqlalchemy.orm import Session

from models import (
    AnoEscolar,
    Asistencia,
    Curso,
    DiaNoLaborable,
    Estudiante,
    Horario,
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


def _orden_mes(mes_num: int) -> int:
    orden_meses = [8, 9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7]
    return orden_meses.index(mes_num) if mes_num in orden_meses else 99


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


def _construir_fechas_esperadas(
    ano: Optional[AnoEscolar],
    dias_horario: Set[str],
    dias_no_laborables: Set,
) -> Dict[int, List]:
    if not ano or not ano.fecha_inicio or not ano.fecha_fin or not dias_horario:
        return {}

    fechas_por_mes: Dict[int, List] = defaultdict(list)
    actual = ano.fecha_inicio

    while actual <= ano.fecha_fin:
        dia_nombre = DIA_NUM_A_NOMBRE.get(actual.weekday())
        es_no_laborable = actual in dias_no_laborables or (actual.month, actual.day) in dias_no_laborables

        if dia_nombre in dias_horario and not es_no_laborable:
            fechas_por_mes[actual.month].append(actual)

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

    q = db.query(Asistencia).filter(
        Asistencia.estudiante_id.in_(est_ids),
        Asistencia.curso_id == curso_id,
    )
    if asignatura_id is not None:
        q = q.filter(Asistencia.asignatura_id == asignatura_id)

    registros = q.all()
    if not registros and not fechas_esperadas_por_mes:
        return []

    prioridad = {'A': 4, 'T': 3, 'E': 2, 'P': 1, '': 0}
    por_mes: Dict[int, Dict[int, Dict[int, str]]] = defaultdict(lambda: defaultdict(dict))

    for r in registros:
        codigo = ESTADO_A_CODIGO.get((r.estado or '').lower(), '')
        if not codigo:
            continue
        existente = por_mes[r.fecha.month][r.fecha.day].get(r.estudiante_id, '')
        if prioridad.get(codigo, 0) > prioridad.get(existente, 0):
            por_mes[r.fecha.month][r.fecha.day][r.estudiante_id] = codigo

    if not fechas_esperadas_por_mes:
        for mes_num, dias_dict in por_mes.items():
            fechas_esperadas_por_mes[mes_num] = []
            for dia in sorted(dias_dict.keys()):
                if ano and ano.fecha_inicio and ano.fecha_fin:
                    year = ano.fecha_inicio.year if mes_num >= 8 else ano.fecha_fin.year
                else:
                    sample = next(iter(dias_dict[dia].keys()), None)
                    year = registros[0].fecha.year if registros else 2000
                    if sample:
                        year = next((r.fecha.year for r in registros if r.estudiante_id == sample and r.fecha.month == mes_num and r.fecha.day == dia), year)
                from datetime import date
                fechas_esperadas_por_mes[mes_num].append(date(year, mes_num, dia))

    meses_presentes = sorted(fechas_esperadas_por_mes.keys(), key=_orden_mes)
    dias_trabajados_cfg = ano.get_dias_trabajados() if ano else {}

    resultado = []
    for mes_num in meses_presentes:
        fechas_mes = sorted(fechas_esperadas_por_mes.get(mes_num, []))
        dias = [f.day for f in fechas_mes]
        dias_unicos = list(dict.fromkeys(dias))
        dias_con_registro = sorted(por_mes.get(mes_num, {}).keys())
        cfg_mes = dias_trabajados_cfg.get(MES_CLAVE_CORTA.get(mes_num, ''), 0) if dias_trabajados_cfg else 0

        filas = []
        celdas_esperadas = len(dias_unicos) * len(estudiantes)
        celdas_con_registro = 0

        for est in estudiantes:
            valores = []
            presentes = 0
            ausentes = 0

            for dia in dias_unicos:
                codigo = por_mes.get(mes_num, {}).get(dia, {}).get(est.id, '')
                valores.append(codigo)
                if codigo:
                    celdas_con_registro += 1
                if codigo == 'P':
                    presentes += 1
                elif codigo == 'A':
                    ausentes += 1

            porcentaje = round((presentes / len(dias_unicos)) * 100, 1) if dias_unicos else 0.0
            filas.append({
                'no': est_index[est.id],
                'estudiante_id': est.id,
                'nombre': est.nombre_completo,
                'valores': valores,
                'presentes': presentes,
                'ausentes': ausentes,
                'porcentaje': porcentaje,
            })

        fuente = 'horario' if dias_horario else 'registros'
        resultado.append({
            'mes': MES_NUM_A_NOMBRE.get(mes_num, str(mes_num)),
            'mes_num': mes_num,
            'dias': dias_unicos,
            'total_dias': len(dias_unicos),
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
