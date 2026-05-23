"""
stats_service.py - Lógica de estadísticas optimizada
=====================================================
SQL aggregates, zero N+1, cache por tenant.
"""
import time
import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, distinct

from models import (
    Estudiante, Curso, Grado, Calificacion, CalificacionPrimaria, Asistencia, Asignatura,
    AsignacionProfesor, ConfiguracionColegio, AnoEscolar, Usuario,
    ReporteConducta, CasoPsicologia, Tanda,
    # v2.13.3: modelos de secundaria MINERD (4 competencias × 4 períodos + cascada)
    CalificacionSecundaria, EvaluacionExtraSecundaria,
)
from auth import tenant_filter
from services.cache_service import cache_get, cache_set, make_cache_key

logger = logging.getLogger("educaone.stats")


def get_graficos(db: Session, user) -> dict:
    """
    Dashboard gráficos — calcula con Python puro para máxima compatibilidad.
    Usa cf si existe, sino pc del periodo activo.
    
    v2.13.5: lee AMBOS modelos de secundaria: Calificacion (legacy) y
    CalificacionSecundaria (nuevo MINERD v2.12). Si un estudiante tiene
    datos en el modelo nuevo, prevalece ese.
    """
    ck = make_cache_key("graficos", user)
    cached = cache_get(ck)
    if cached:
        return cached

    t0 = time.time()
    cid = user.colegio_id

    # Determinar período activo
    ano_activo = tenant_filter(db.query(AnoEscolar), AnoEscolar, user).filter_by(activo=True).first()
    pa = ano_activo.periodo_activo if ano_activo else 1
    pc_attr = f'pc{pa}'  # 'pc1', 'pc2', 'pc3', 'pc4'

    # 1. Traer calificaciones de SECUNDARIA LEGACY (modelo viejo Calificacion)
    q_cal = (
        db.query(
            Calificacion.estudiante_id,
            Calificacion.cf,
            getattr(Calificacion, pc_attr).label('pc_activo'),
            Grado.nombre.label('grado_nombre'),
            Grado.orden.label('grado_orden')
        )
        .join(Estudiante, Estudiante.id == Calificacion.estudiante_id)
        .join(Curso, Curso.id == Estudiante.curso_id)
        .join(Grado, Grado.id == Curso.grado_id)
        .filter(Estudiante.activo == True, Curso.activo == True)
    )
    if cid:
        q_cal = q_cal.filter(Calificacion.colegio_id == cid)
    
    calificaciones = list(q_cal.all())
    
    # 1.b — Traer calificaciones de SECUNDARIA NUEVO (CalificacionSecundaria MINERD).
    # Cada estudiante tiene N filas (una por competencia × asignatura). Hay que
    # agrupar para construir el CF/PC promedio por estudiante.
    # PC[periodo] = AVG(comp1..comp4 en ese período)
    # CF = AVG(PC1..PC4)
    if ano_activo:
        q_sec = (
            db.query(
                CalificacionSecundaria.estudiante_id,
                CalificacionSecundaria.asignatura_id,
                CalificacionSecundaria.competencia_numero,
                CalificacionSecundaria.p1, CalificacionSecundaria.rp1,
                CalificacionSecundaria.p2, CalificacionSecundaria.rp2,
                CalificacionSecundaria.p3, CalificacionSecundaria.rp3,
                CalificacionSecundaria.p4, CalificacionSecundaria.rp4,
                Grado.nombre.label('grado_nombre'),
                Grado.orden.label('grado_orden'),
            )
            .join(Estudiante, Estudiante.id == CalificacionSecundaria.estudiante_id)
            .join(Curso, Curso.id == Estudiante.curso_id)
            .join(Grado, Grado.id == Curso.grado_id)
            .filter(
                Estudiante.activo == True, Curso.activo == True,
                CalificacionSecundaria.ano_escolar_id == ano_activo.id,
            )
        )
        if cid:
            q_sec = q_sec.filter(CalificacionSecundaria.colegio_id == cid)
        
        # Agrupar por (estudiante, asignatura) → list de (comp_n, p1, rp1, p2, rp2, p3, rp3, p4, rp4)
        from collections import defaultdict as _dd_sec
        sec_por_est_asig = _dd_sec(list)
        grado_de_est: Dict[int, tuple] = {}  # est_id → (grado_nombre, grado_orden)
        for row in q_sec.all():
            eid = row.estudiante_id
            aid = row.asignatura_id
            sec_por_est_asig[(eid, aid)].append((
                row.competencia_numero,
                row.p1, row.rp1, row.p2, row.rp2,
                row.p3, row.rp3, row.p4, row.rp4
            ))
            grado_de_est[eid] = (row.grado_nombre, row.grado_orden)
        
        # Para cada (estudiante, asignatura): calcular CF del área
        # CF = AVG(PC1..PC4), donde PC[i] = AVG(competencias con valor en período i)
        def _valor_efectivo(p_val, rp_val):
            """max(P, RP) si hay RP; si no, P. Si no hay nada, None."""
            if rp_val is not None and p_val is not None:
                return max(p_val, rp_val)
            elif rp_val is not None:
                return rp_val
            elif p_val is not None:
                return p_val
            return None
        
        cf_por_est_asig: Dict[tuple, float] = {}
        pc_periodo_por_est_asig: Dict[tuple, float] = {}  # PC del período activo
        
        for (eid, aid), comps in sec_por_est_asig.items():
            # PC del período activo (para mostrar mientras no haya cf completo)
            vals_pa = []
            for c in comps:
                idx_p = (pa - 1) * 2 + 1
                idx_rp = idx_p + 1
                v = _valor_efectivo(c[idx_p], c[idx_rp])
                if v is not None:
                    vals_pa.append(v)
            if vals_pa:
                pc_periodo_por_est_asig[(eid, aid)] = sum(vals_pa) / len(vals_pa)
            
            # CF anual: promedio de los 4 PC
            pcs = []
            for p_n in range(1, 5):
                vals_p = []
                for c in comps:
                    idx_p = (p_n - 1) * 2 + 1
                    idx_rp = idx_p + 1
                    v = _valor_efectivo(c[idx_p], c[idx_rp])
                    if v is not None:
                        vals_p.append(v)
                if vals_p:
                    pcs.append(sum(vals_p) / len(vals_p))
            if pcs:
                cf_por_est_asig[(eid, aid)] = sum(pcs) / len(pcs)
        
        # Convertir a "calificaciones" estilo el formato de Calificacion legacy
        # 1 fila por (estudiante, asignatura) con CF y PC activo
        class _CalAdapterSec:
            __slots__ = ('estudiante_id', 'cf', 'pc_activo', 'grado_nombre', 'grado_orden')
            def __init__(self, **kw):
                for k, v in kw.items(): setattr(self, k, v)
        
        # Set de estudiantes que YA tienen datos en modelo nuevo (para no duplicar
        # contra modelo legacy)
        estudiantes_en_modelo_nuevo = set()
        for (eid, aid), cf in cf_por_est_asig.items():
            grado_info = grado_de_est.get(eid, (None, 0))
            pc_act = pc_periodo_por_est_asig.get((eid, aid))
            calificaciones.append(_CalAdapterSec(
                estudiante_id=eid,
                cf=cf,
                pc_activo=pc_act if pc_act is not None else cf,
                grado_nombre=grado_info[0],
                grado_orden=grado_info[1],
            ))
            estudiantes_en_modelo_nuevo.add(eid)
        
        # Filtrar calificaciones legacy de estudiantes que YA están en modelo nuevo.
        # Esto evita doble-conteo (un mismo estudiante aportando notas desde ambos modelos).
        calificaciones = [
            c for c in calificaciones
            if not (hasattr(c, 'estudiante_id') and c.estudiante_id in estudiantes_en_modelo_nuevo
                    and not isinstance(c, _CalAdapterSec))
        ]
    
    # Agregar calificaciones de PRIMARIA. Como su modelo es por competencia
    # (3 filas por estudiante×asignatura), agrupamos para construir tuplas
    # equivalentes a las de secundaria: (estudiante_id, cf, pc_activo, grado_nombre, grado_orden).
    # cf primaria = promedio de las 3 competencias finales (final_competencia).
    # pc_activo primaria = promedio del valor del período en cada competencia.
    q_pri = (
        db.query(
            CalificacionPrimaria.estudiante_id,
            CalificacionPrimaria.competencia_numero,
            CalificacionPrimaria.final_competencia,
            getattr(CalificacionPrimaria, f'p{pa}').label('p_periodo'),
            getattr(CalificacionPrimaria, f'rp{pa}').label('rp_periodo'),
            Grado.nombre.label('grado_nombre'),
            Grado.orden.label('grado_orden')
        )
        .join(Estudiante, Estudiante.id == CalificacionPrimaria.estudiante_id)
        .join(Curso, Curso.id == Estudiante.curso_id)
        .join(Grado, Grado.id == Curso.grado_id)
        .filter(Estudiante.activo == True, Curso.activo == True)
    )
    if cid:
        q_pri = q_pri.filter(CalificacionPrimaria.colegio_id == cid)
    
    # Agrupar por estudiante: { estId: {grado, orden, finals: [...], pcs: [...]} }
    from collections import defaultdict as _dd
    pri_por_est = _dd(lambda: {'grado_nombre': None, 'grado_orden': 0, 'finals': [], 'pcs': []})
    for row in q_pri.all():
        d = pri_por_est[row.estudiante_id]
        d['grado_nombre'] = row.grado_nombre
        d['grado_orden'] = row.grado_orden
        # cf de la competencia
        if row.final_competencia is not None:
            d['finals'].append(float(row.final_competencia))
        # pc del período: max(p, rp) si hay rp, sino p
        valP = row.p_periodo
        valRP = row.rp_periodo
        if valRP is not None and valP is not None:
            d['pcs'].append(float(max(valP, valRP)))
        elif valRP is not None:
            d['pcs'].append(float(valRP))
        elif valP is not None:
            d['pcs'].append(float(valP))
    
    # Construir tuplas estilo "secundaria" para reutilizar el loop de abajo
    class _CalAdapter:
        __slots__ = ('estudiante_id', 'cf', 'pc_activo', 'grado_nombre', 'grado_orden')
        def __init__(self, **kw): 
            for k, v in kw.items(): setattr(self, k, v)
    
    for est_id, d in pri_por_est.items():
        cf = round(sum(d['finals']) / len(d['finals']), 2) if d['finals'] else None
        pc = round(sum(d['pcs']) / len(d['pcs']), 2) if d['pcs'] else None
        if cf is not None or pc is not None:
            calificaciones.append(_CalAdapter(
                estudiante_id=est_id, cf=cf, pc_activo=pc,
                grado_nombre=d['grado_nombre'] or 'Primaria',
                grado_orden=d['grado_orden'] or 0
            ))

    # Calcular promedios por grado con Python
    from collections import defaultdict
    grado_notas = defaultdict(list)
    grado_estudiantes = defaultdict(set)
    grado_orden = {}
    
    estudiante_notas = defaultdict(list)  # para estado aprobado/reprobado
    
    for cal in calificaciones:
        nota = cal.cf if cal.cf is not None else cal.pc_activo
        if nota is None:
            continue
        grado_notas[cal.grado_nombre].append(float(nota))
        grado_estudiantes[cal.grado_nombre].add(cal.estudiante_id)
        grado_orden[cal.grado_nombre] = cal.grado_orden
        estudiante_notas[cal.estudiante_id].append(float(nota))

    promedios = sorted([
        {
            'grado': grado,
            'promedio': round(sum(notas) / len(notas), 1),
            'estudiantes': len(grado_estudiantes[grado])
        }
        for grado, notas in grado_notas.items()
    ], key=lambda x: grado_orden.get(x['grado'], 0))

    # 2. Estado estudiantes
    total_est = tenant_filter(db.query(func.count(Estudiante.id)), Estudiante, user).filter(Estudiante.activo == True).scalar() or 0
    
    con_notas = len(estudiante_notas)
    aprobados = sum(1 for notas in estudiante_notas.values() if min(notas) >= 70)
    reprobados = con_notas - aprobados
    en_proceso = total_est - con_notas

    # 3. Asistencia mes — 1 registro por estudiante por día (sin duplicados)
    # Si tiene al menos 1 "presente" ese día → presente. Solo ausente si faltó a TODO.
    hoy = date.today()
    p1 = date(hoy.year, hoy.month, 1)
    
    # Obtener todos los registros del mes para este colegio
    q_asist_raw = db.query(
        Asistencia.estudiante_id,
        Asistencia.fecha,
        Asistencia.estado
    ).filter(Asistencia.fecha >= p1)
    if cid:
        q_asist_raw = q_asist_raw.filter(Asistencia.colegio_id == cid)
    
    # Agrupar por estudiante+día y determinar estado del día
    from collections import defaultdict
    dias_est: Dict[tuple, set] = defaultdict(set)
    for est_id, fecha, estado in q_asist_raw.all():
        dias_est[(est_id, fecha)].add(estado)
    
    # Contar mes: si tiene "presente" en cualquier materia → presente ese día
    pr = 0
    aus = 0
    tard = 0
    for (est_id, fecha), estados in dias_est.items():
        if 'presente' in estados:
            pr += 1
        elif 'tardanza' in estados:
            tard += 1
        else:
            aus += 1
    total_a = pr + aus + tard
    
    # 3a. Porcentaje mensual REAL — fórmula:
    #   presentes_mes / (estudiantes_activos × días_con_registro)
    # Esto da el % real de asistencia considerando todos los estudiantes activos
    # como denominador, no solo los registrados. Si un día no se pasó lista a
    # nadie, ese día no cuenta (días_con_registro). Si se pasó lista a la mitad
    # del colegio, se considera el colegio entero.
    dias_con_registro = len(set(fecha for (_, fecha) in dias_est.keys()))
    denom_mensual_real = total_est * dias_con_registro
    porcentaje_mensual_real = round(pr / denom_mensual_real * 100, 1) if denom_mensual_real > 0 else 0
    
    # 3b. Asistencia HOY — para mostrar el snapshot diario del colegio
    # Misma lógica de "1 estado por estudiante por día" pero limitado a hoy.
    # Útil para ver al final del día qué profesores no pasaron lista (no_registrados).
    hoy_pr = 0
    hoy_aus = 0
    hoy_tard = 0
    hoy_excu = 0
    estudiantes_con_marca_hoy = set()
    for (est_id, fecha), estados in dias_est.items():
        if fecha != hoy:
            continue
        estudiantes_con_marca_hoy.add(est_id)
        if 'presente' in estados:
            hoy_pr += 1
        elif 'tardanza' in estados:
            hoy_tard += 1
        elif 'excusa' in estados:
            hoy_excu += 1
        else:
            hoy_aus += 1
    # No registrados: estudiantes activos sin ninguna marca en el día
    hoy_no_registrados = max(0, total_est - len(estudiantes_con_marca_hoy))
    hoy_total = total_est  # total de activos = denominador
    hoy_porcentaje = round(hoy_pr / hoy_total * 100, 1) if hoy_total > 0 else 0

    # 4. Asistencia por materia — esto SÍ cuenta por materia (es el detalle)
    q_mat = (
        db.query(Asignatura.nombre, Asistencia.estado, func.count(Asistencia.id))
        .join(Asignatura, Asignatura.id == Asistencia.asignatura_id)
        .filter(Asistencia.fecha >= p1)
    )
    if cid:
        q_mat = q_mat.filter(Asistencia.colegio_id == cid)
    mat_data: Dict[str, Dict] = {}
    for nombre, estado, cnt in q_mat.group_by(Asignatura.nombre, Asistencia.estado).all():
        if nombre not in mat_data:
            mat_data[nombre] = {'presentes': 0, 'ausentes': 0, 'tardanzas': 0, 'excusas': 0, 'total': 0}
        key = f'{estado}s' if estado != 'excusa' else 'excusas'
        mat_data[nombre][key] = cnt
        mat_data[nombre]['total'] += cnt

    # 5. Ranking mejores estudiantes y en peligro
    ranking_mejor = []
    ranking_peligro = []
    
    # Traer nombres de estudiantes
    est_ids = list(estudiante_notas.keys())
    if est_ids:
        est_info = {e.id: e for e in db.query(Estudiante).filter(Estudiante.id.in_(est_ids)).all()}
        
        est_promedios = []
        for est_id, notas in estudiante_notas.items():
            est = est_info.get(est_id)
            if not est:
                continue
            prom = round(sum(notas) / len(notas), 1)
            curso_nombre = est.curso.nombre_completo if est.curso else ''
            est_promedios.append({
                'nombre': f'{est.nombre} {est.apellido}',
                'curso': curso_nombre,
                'promedio': prom
            })
        
        est_promedios.sort(key=lambda x: x['promedio'], reverse=True)
        ranking_mejor = est_promedios[:5]
        ranking_peligro = sorted(
            [e for e in est_promedios if e['promedio'] < 70],
            key=lambda x: x['promedio']
        )[:10]

    result = {
        'promedios_por_grado': promedios,
        'estado_estudiantes': [
            {'nombre': 'Aprobados', 'cantidad': aprobados, 'color': '#10b981'},
            {'nombre': 'Reprobados', 'cantidad': reprobados, 'color': '#ef4444'},
            {'nombre': 'En Proceso', 'cantidad': en_proceso, 'color': '#f59e0b'}
        ],
        'asistencia_resumen': {
            'presentes': pr,
            'ausentes': aus,
            'tardanzas': tard,
            # Porcentaje "viejo": presentes / total con registro. Mantiene compat.
            'porcentaje_asistencia': round(pr / total_a * 100, 1) if total_a > 0 else 0,
            # Porcentaje real considerando todos los estudiantes activos:
            # presentes_mes / (estudiantes_activos × días_con_registro)
            'porcentaje_mensual_real': porcentaje_mensual_real,
            'dias_con_registro': dias_con_registro,
            'estudiantes_activos': total_est,
            'periodo_inicio': p1.isoformat(),
            'periodo_fin': hoy.isoformat(),
        },
        'asistencia_hoy': {
            'fecha': hoy.isoformat(),
            'presentes': hoy_pr,
            'ausentes': hoy_aus,
            'tardanzas': hoy_tard,
            'excusas': hoy_excu,
            'no_registrados': hoy_no_registrados,
            'total_estudiantes': total_est,
            'porcentaje_asistencia': hoy_porcentaje,
        },
        'asistencia_por_materia': [
            {
                'asignatura': n, 'presentes': d['presentes'], 'ausentes': d['ausentes'],
                'tardanzas': d['tardanzas'], 'excusas': d['excusas'], 'total': d['total'],
                'porcentaje': round(d['presentes'] / d['total'] * 100, 1) if d['total'] > 0 else 0
            }
            for n, d in mat_data.items()
        ],
        'ranking_mejor': ranking_mejor,
        'ranking_peligro': ranking_peligro,
        'periodo_activo': pa
    }

    logger.info(f"Graficos: {time.time()-t0:.3f}s colegio={cid}")
    cache_set(ck, result, ttl=120)
    return result


def get_stats_cursos(db: Session, user, periodo: int = 0, nivel: str = None) -> list:
    """
    Estadísticas por curso — bulk load, zero N+1.
    Filtra por nivel ('primaria', 'secundaria', 'todos') si se especifica.
    Para primaria usa tabla CalificacionPrimaria, para secundaria Calificacion.
    """
    ck = make_cache_key(f"stats_cursos_p{periodo}_n{nivel or 'all'}", user)
    cached = cache_get(ck)
    if cached:
        return cached

    t0 = time.time()
    cid = user.colegio_id

    # Cursos — filtro opcional por nivel
    q = db.query(Curso.id, Curso.nombre, Grado.nombre.label('grado'), Grado.nivel).join(
        Grado, Grado.id == Curso.grado_id
    ).filter(Curso.activo == True)
    if cid:
        q = q.filter(Curso.colegio_id == cid)
    if nivel and nivel != 'todos':
        q = q.filter(Grado.nivel == nivel)
    cursos = q.all()
    if not cursos:
        return []

    curso_ids = [c.id for c in cursos]

    # Estudiantes por curso — 1 query
    est_q = (
        db.query(Estudiante.id, Estudiante.curso_id)
        .filter(Estudiante.curso_id.in_(curso_ids), Estudiante.activo == True)
        .all()
    )
    est_por_curso: Dict[int, list] = {}
    for eid, cuid in est_q:
        est_por_curso.setdefault(cuid, []).append(eid)
    all_est_ids = [eid for eid, _ in est_q]

    if not all_est_ids:
        return [{'id': c.id, 'nombre': f'{c.grado} {c.nombre}', 'nivel': c.nivel, 'estudiantes': 0, 'promedio': 0, 'aprobados': 0, 'reprobados': 0, 'sin_calificar': 0} for c in cursos]

    # Determinar qué cursos son primaria/secundaria para decidir tabla
    cursos_primaria_ids = {c.id for c in cursos if c.nivel == 'primaria'}
    est_primaria_ids = [eid for eid, cuid in est_q if cuid in cursos_primaria_ids]
    est_secundaria_ids = [eid for eid in all_est_ids if eid not in est_primaria_ids]

    notas_por_est: Dict[int, List[float]] = {}

    # SECUNDARIA — buscar en AMBOS modelos:
    # - Calificacion (modelo legacy con p1_p1..p4_p4 + pc/cf)
    # - CalificacionSecundaria (modelo nuevo v2.12 MINERD: 4 competencias × 4 períodos)
    # Si el curso/estudiante tiene datos en ambos, prevalece el modelo nuevo.
    if est_secundaria_ids:
        # ─── Modelo NUEVO (CalificacionSecundaria) ───
        # Una nota efectiva por (estudiante, asignatura, competencia, período)
        # CF del área = AVG(PC1..PC4) donde PC[i] = AVG(comp1..comp4 en período i)
        # Promedio del estudiante = AVG(CF de todas sus asignaturas)
        try:
            ano_activo = tenant_filter(
                db.query(AnoEscolar), AnoEscolar, user
            ).filter_by(activo=True).first()
            
            if ano_activo:
                rows_sec = db.query(
                    CalificacionSecundaria.estudiante_id,
                    CalificacionSecundaria.asignatura_id,
                    CalificacionSecundaria.competencia_numero,
                    CalificacionSecundaria.p1, CalificacionSecundaria.rp1,
                    CalificacionSecundaria.p2, CalificacionSecundaria.rp2,
                    CalificacionSecundaria.p3, CalificacionSecundaria.rp3,
                    CalificacionSecundaria.p4, CalificacionSecundaria.rp4,
                ).filter(
                    CalificacionSecundaria.estudiante_id.in_(est_secundaria_ids),
                    CalificacionSecundaria.ano_escolar_id == ano_activo.id,
                ).all()
                
                # Agrupar por (estudiante, asignatura) → lista de las 4 competencias
                comps_por_est_asig: Dict[tuple, list] = {}
                for r in rows_sec:
                    eid, aid, comp_n = r[0], r[1], r[2]
                    p1, rp1, p2, rp2, p3, rp3, p4, rp4 = r[3:]
                    comps_por_est_asig.setdefault((eid, aid), []).append(
                        (comp_n, p1, rp1, p2, rp2, p3, rp3, p4, rp4)
                    )
                
                # Calcular CF por (estudiante, asignatura)
                cf_por_est_asig: Dict[tuple, float] = {}
                for (eid, aid), comps in comps_por_est_asig.items():
                    # Necesitamos las 4 competencias para CF válido (regla MINERD)
                    if len(comps) < 4:
                        # Caso incompleto: promediar lo que haya como rendimiento ACTUAL
                        pass
                    
                    if periodo and periodo > 0:
                        # Período específico: PC = promedio de las 4 competencias en ese período
                        idx_p = (periodo - 1) * 2 + 1   # p1=1, p2=3, p3=5, p4=7
                        idx_rp = idx_p + 1
                        vals_periodo = []
                        for c in comps:
                            p_val = c[idx_p]
                            rp_val = c[idx_rp]
                            efectivo = None
                            if rp_val is not None and p_val is not None:
                                efectivo = max(p_val, rp_val)
                            elif rp_val is not None:
                                efectivo = rp_val
                            elif p_val is not None:
                                efectivo = p_val
                            if efectivo is not None:
                                vals_periodo.append(efectivo)
                        if vals_periodo:
                            cf_por_est_asig[(eid, aid)] = sum(vals_periodo) / len(vals_periodo)
                    else:
                        # Sin período: PC1..PC4 disponibles → CF = AVG
                        pcs = []
                        for p_n in range(1, 5):
                            idx_p = (p_n - 1) * 2 + 1
                            idx_rp = idx_p + 1
                            vals_competencias = []
                            for c in comps:
                                p_val = c[idx_p]
                                rp_val = c[idx_rp]
                                efectivo = None
                                if rp_val is not None and p_val is not None:
                                    efectivo = max(p_val, rp_val)
                                elif rp_val is not None:
                                    efectivo = rp_val
                                elif p_val is not None:
                                    efectivo = p_val
                                if efectivo is not None:
                                    vals_competencias.append(efectivo)
                            if vals_competencias:
                                pcs.append(sum(vals_competencias) / len(vals_competencias))
                        if pcs:
                            cf_por_est_asig[(eid, aid)] = sum(pcs) / len(pcs)
                
                # Agregar al notas_por_est: cada CF de asignatura aporta al promedio del estudiante
                est_con_sec = set()
                for (eid, aid), cf in cf_por_est_asig.items():
                    notas_por_est.setdefault(eid, []).append(cf)
                    est_con_sec.add(eid)
                
                # Para estudiantes que ya tienen datos en modelo nuevo, no buscar en viejo
                est_secundaria_legacy = [e for e in est_secundaria_ids if e not in est_con_sec]
            else:
                est_secundaria_legacy = est_secundaria_ids
        except Exception as e:
            logger.warning(f"Error cargando stats CalificacionSecundaria: {e}")
            est_secundaria_legacy = est_secundaria_ids
        
        # ─── Modelo LEGACY (Calificacion) ───
        # Solo para estudiantes que no tienen datos en el modelo nuevo
        if est_secundaria_legacy:
            if periodo and periodo > 0:
                pc_col = getattr(Calificacion, f'pc{periodo}')
                rp_col = getattr(Calificacion, f'rp{periodo}')
                rows = db.query(Calificacion.estudiante_id, pc_col, rp_col).filter(
                    Calificacion.estudiante_id.in_(est_secundaria_legacy)
                ).all()
                for eid, pc, rp in rows:
                    if pc is not None:
                        nota = rp if (pc < 70 and rp is not None) else pc
                        notas_por_est.setdefault(eid, []).append(nota)
            else:
                rows = db.query(
                    Calificacion.estudiante_id,
                    Calificacion.cf,
                    Calificacion.pc1, Calificacion.pc2, Calificacion.pc3, Calificacion.pc4,
                    Calificacion.rp1, Calificacion.rp2, Calificacion.rp3, Calificacion.rp4,
                ).filter(Calificacion.estudiante_id.in_(est_secundaria_legacy)).all()
                for eid, cf, pc1, pc2, pc3, pc4, rp1, rp2, rp3, rp4 in rows:
                    if cf is not None:
                        notas_por_est.setdefault(eid, []).append(cf)
                    else:
                        pcs = []
                        for pc, rp in [(pc1, rp1), (pc2, rp2), (pc3, rp3), (pc4, rp4)]:
                            if pc is not None:
                                nota = rp if (pc < 70 and rp is not None) else pc
                                pcs.append(nota)
                        if pcs:
                            promedio_actual = sum(pcs) / len(pcs)
                            notas_por_est.setdefault(eid, []).append(promedio_actual)

    # PRIMARIA — tabla CalificacionPrimaria (una fila por competencia)
    if est_primaria_ids:
        try:
            from models import CalificacionPrimaria
            rows = db.query(
                CalificacionPrimaria.estudiante_id,
                CalificacionPrimaria.asignatura_id,
                CalificacionPrimaria.final_competencia
            ).filter(
                CalificacionPrimaria.estudiante_id.in_(est_primaria_ids),
                CalificacionPrimaria.final_competencia != None
            ).all()
            # Agrupar por estudiante+asignatura para calcular CF del área
            cf_por_area: Dict[tuple, List[float]] = {}
            for eid, aid, fc in rows:
                cf_por_area.setdefault((eid, aid), []).append(fc)
            # CF del área = promedio de las competencias; el promedio del estudiante = promedio de CFs
            for (eid, aid), vals in cf_por_area.items():
                if vals:
                    cf_area = sum(vals) / len(vals)
                    notas_por_est.setdefault(eid, []).append(cf_area)
        except Exception as e:
            logger.warning(f"Error cargando stats primaria: {e}")

    resultado = []
    for c in cursos:
        eids = est_por_curso.get(c.id, [])
        n = len(eids)
        if not n:
            continue
        proms = []
        apr = rep = 0
        for eid in eids:
            ns = notas_por_est.get(eid, [])
            if ns:
                proms.append(sum(ns) / len(ns))
                if all(x >= 70 for x in ns):
                    apr += 1
                else:
                    rep += 1
        resultado.append({
            'id': c.id, 'nombre': f'{c.grado} {c.nombre}',
            'nivel': c.nivel or 'secundaria',
            'estudiantes': n,
            'promedio': round(sum(proms) / len(proms), 1) if proms else 0,
            'aprobados': apr, 'reprobados': rep, 'sin_calificar': n - apr - rep
        })

    logger.info(f"Stats cursos ({nivel or 'all'}): {time.time()-t0:.3f}s ({len(resultado)} cursos)")
    cache_set(ck, resultado, ttl=120)
    return resultado


def get_calificaciones_periodo(db: Session, user, curso_id: int, periodo: int) -> dict:
    """
    Calificaciones por período. Detecta el nivel del curso y rutea a la
    tabla correcta:
      - secundaria → Calificacion (parciales p1_p1..p4_p4 + pc/cf)
      - primaria   → CalificacionPrimaria (competencias C1..C3 con p1..p4 + rp1..rp4)
    
    Ambos casos devuelven la misma estructura para que el frontend pueda
    pintar la tabla sin distinguir, usando 'pc_periodo' como nota efectiva.
    """
    curso = db.get(Curso, curso_id)
    if not curso:
        return {'error': 'Curso no encontrado'}

    # Detectar nivel del curso vía su grado
    grado = db.get(Grado, curso.grado_id) if curso.grado_id else None
    nivel = (grado.nivel or 'secundaria').lower() if grado else 'secundaria'
    es_primaria = nivel == 'primaria'

    estudiantes = (
        tenant_filter(db.query(Estudiante), Estudiante, user)
        .filter_by(curso_id=curso_id, activo=True)
        .order_by(Estudiante.no_lista).all()
    )
    est_ids = [e.id for e in estudiantes]
    if not est_ids:
        return {
            'curso': getattr(curso, 'nombre_completo', curso.nombre),
            'periodo': periodo, 'asignaturas_nombres': [], 'estudiantes': [],
            'nivel': nivel,
        }

    # Asignaturas (mismo cálculo para ambos niveles)
    asig_ids = list(set(
        a.asignatura_id for a in
        tenant_filter(db.query(AsignacionProfesor), AsignacionProfesor, user)
        .filter_by(curso_id=curso_id, activo=True).all()
    ))
    asignaturas = (
        tenant_filter(db.query(Asignatura), Asignatura, user)
        .filter(Asignatura.id.in_(asig_ids)).order_by(Asignatura.nombre).all()
    ) if asig_ids else []

    if es_primaria:
        # Primaria: traer competencias y derivar la "nota del período" como
        # promedio de los valores de período de cada competencia.
        # valor_periodo MINERD: max(P, RP) si hay RP; si no, P (o RP solo).
        califs_pri = (
            tenant_filter(db.query(CalificacionPrimaria), CalificacionPrimaria, user)
            .filter(CalificacionPrimaria.estudiante_id.in_(est_ids),
                    CalificacionPrimaria.asignatura_id.in_(asig_ids))
            .all()
        ) if asig_ids else []
        # Agrupar: {(estId, asigId): [comp1, comp2, comp3]}
        from collections import defaultdict
        comps_por_est_asig = defaultdict(list)
        for c in califs_pri:
            comps_por_est_asig[(c.estudiante_id, c.asignatura_id)].append(c)
        
        def valor_periodo_pri(comp, p):
            valP = getattr(comp, f'p{p}', None)
            valRP = getattr(comp, f'rp{p}', None)
            if valRP is not None and valP is not None:
                return float(max(valP, valRP))
            if valRP is not None: return float(valRP)
            if valP is not None: return float(valP)
            return None
        
        result_est = []
        for est in estudiantes:
            d = {'estudiante_id': est.id, 'nombre': est.nombre_completo,
                 'no_lista': est.no_lista or 0, 'asignaturas': {}, 'promedio': None}
            notas = []
            for asig in asignaturas:
                comps = comps_por_est_asig.get((est.id, asig.id), [])
                # Por cada competencia, obtener su valor del período. Promedio = nota del período en esa asignatura.
                valores = []
                for comp in comps:
                    v = valor_periodo_pri(comp, periodo)
                    if v is not None:
                        valores.append(v)
                if valores:
                    nota = round(sum(valores) / len(valores), 2)
                    d['asignaturas'][asig.nombre] = nota
                    notas.append(nota)
                else:
                    d['asignaturas'][asig.nombre] = None
            if notas:
                d['promedio'] = round(sum(notas) / len(notas), 2)
            result_est.append(d)
        
        return {
            'curso': getattr(curso, 'nombre_completo', curso.nombre),
            'periodo': periodo,
            'asignaturas_nombres': [a.nombre for a in asignaturas],
            'estudiantes': result_est,
            'nivel': 'primaria',
        }

    # Secundaria (v2.13.6: leer AMBOS modelos - Calificacion legacy + CalificacionSecundaria nuevo)
    # CalificacionSecundaria es el modelo MINERD v2.12+ (4 competencias × 4 períodos por estudiante×asignatura)
    # Calificacion es legacy (un registro por estudiante×asignatura con campos planos pc1..pc4)
    
    # 1. Modelo NUEVO: CalificacionSecundaria
    ano_activo = (
        tenant_filter(db.query(AnoEscolar), AnoEscolar, user)
        .filter_by(activo=True).first()
    )
    
    # notas_por_est_asig: dict (est_id, asig_id) → nota del período (PC)
    notas_por_est_asig: Dict[tuple, float] = {}
    
    if ano_activo and asig_ids:
        califs_sec = (
            tenant_filter(db.query(CalificacionSecundaria), CalificacionSecundaria, user)
            .filter(
                CalificacionSecundaria.estudiante_id.in_(est_ids),
                CalificacionSecundaria.asignatura_id.in_(asig_ids),
                CalificacionSecundaria.ano_escolar_id == ano_activo.id,
            ).all()
        )
        # Agrupar por (est, asig) → lista de 4 competencias
        from collections import defaultdict as _dd
        sec_grouped = _dd(list)
        for c in califs_sec:
            sec_grouped[(c.estudiante_id, c.asignatura_id)].append(c)
        
        # PC del período = AVG de las competencias (usando valor_periodo: max(P, RP))
        for (eid, aid), comps in sec_grouped.items():
            vals = []
            for comp in comps:
                v = comp.valor_periodo(periodo) if hasattr(comp, 'valor_periodo') else None
                if v is not None:
                    vals.append(v)
            if vals:
                notas_por_est_asig[(eid, aid)] = round(sum(vals) / len(vals), 2)
    
    # 2. Modelo LEGACY: Calificacion (solo para estudiantes/asignaturas SIN datos en modelo nuevo)
    califs = (
        tenant_filter(db.query(Calificacion), Calificacion, user)
        .filter(Calificacion.estudiante_id.in_(est_ids), Calificacion.asignatura_id.in_(asig_ids))
        .all()
    ) if asig_ids else []
    cm = {(c.estudiante_id, c.asignatura_id): c for c in califs}

    pc_key = f'pc{periodo}'
    result_est = []
    for est in estudiantes:
        d = {'estudiante_id': est.id, 'nombre': est.nombre_completo, 'no_lista': est.no_lista or 0, 'asignaturas': {}, 'promedio': None}
        notas = []
        for asig in asignaturas:
            # Modelo nuevo primero
            nota = notas_por_est_asig.get((est.id, asig.id))
            if nota is None:
                # Fallback al modelo legacy
                c = cm.get((est.id, asig.id))
                nota = getattr(c, pc_key, None) if c else None
            d['asignaturas'][asig.nombre] = nota
            if nota is not None:
                notas.append(nota)
        if notas:
            d['promedio'] = round(sum(notas) / len(notas), 2)
        result_est.append(d)

    return {
        'curso': getattr(curso, 'nombre_completo', curso.nombre),
        'periodo': periodo,
        'asignaturas_nombres': [a.nombre for a in asignaturas],
        'estudiantes': result_est,
        'nivel': 'secundaria',
    }


def generar_tarjetas_pdf(db: Session, user, curso_id: int, periodo: int, simple: bool = False, usar_p4: bool = False):
    """
    PDF tarjetas individuales — una página por estudiante.
    simple=True: reporte padres (solo nota final, sin parciales, sin asistencia)
    usar_p4=True: usa P4 como nota final en vez de PC
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    import io

    curso = db.get(Curso, curso_id)
    config = tenant_filter(db.query(ConfiguracionColegio), ConfiguracionColegio, user).first()
    ano = tenant_filter(db.query(AnoEscolar), AnoEscolar, user).filter_by(activo=True).first()

    estudiantes = tenant_filter(db.query(Estudiante), Estudiante, user).filter_by(curso_id=curso_id, activo=True).order_by(Estudiante.no_lista).all()
    est_ids = [e.id for e in estudiantes]

    asig_ids = list(set(a.asignatura_id for a in tenant_filter(db.query(AsignacionProfesor), AsignacionProfesor, user).filter_by(curso_id=curso_id, activo=True).all()))
    asignaturas = tenant_filter(db.query(Asignatura), Asignatura, user).filter(Asignatura.id.in_(asig_ids)).order_by(Asignatura.nombre).all() if asig_ids else []

    califs = tenant_filter(db.query(Calificacion), Calificacion, user).filter(Calificacion.estudiante_id.in_(est_ids), Calificacion.asignatura_id.in_(asig_ids)).all() if est_ids and asig_ids else []
    cm = {(c.estudiante_id, c.asignatura_id): c for c in califs}

    # Asistencia bulk (solo para modo completo)
    asist_pr = {}
    asist_tot = {}
    if not simple and est_ids:
        asist_pr = dict(db.query(Asistencia.estudiante_id, func.count(Asistencia.id)).filter(Asistencia.estudiante_id.in_(est_ids), Asistencia.estado == 'presente').group_by(Asistencia.estudiante_id).all())
        asist_tot = dict(db.query(Asistencia.estudiante_id, func.count(Asistencia.id)).filter(Asistencia.estudiante_id.in_(est_ids)).group_by(Asistencia.estudiante_id).all())

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=0.4*inch, bottomMargin=0.4*inch, leftMargin=0.5*inch, rightMargin=0.5*inch)
    styles = getSampleStyleSheet()
    ts = ParagraphStyle('T', parent=styles['Heading1'], fontSize=14, alignment=TA_CENTER, spaceAfter=2, textColor=colors.HexColor('#1e3a5f'))
    ss = ParagraphStyle('S', parent=styles['Normal'], fontSize=9, alignment=TA_CENTER, spaceAfter=4, textColor=colors.HexColor('#475569'))
    ns = ParagraphStyle('N', parent=styles['Heading2'], fontSize=13, alignment=TA_LEFT, spaceAfter=2, textColor=colors.HexColor('#1e40af'))
    fs = ParagraphStyle('F', parent=styles['Normal'], fontSize=7, alignment=TA_CENTER, textColor=colors.HexColor('#94a3b8'))

    col_nombre = config.nombre if config else 'Centro Educativo'
    cur_nombre = getattr(curso, 'nombre_completo', curso.nombre) if curso else ''
    ano_nombre = ano.nombre if ano else ''

    # Determinar rol del que imprime para la firma
    rol_firma = {
        'direccion': 'Dirección',
        'coordinador': 'Coordinación',
        'secretaria': 'Secretaría',
        'superadmin': 'Administración'
    }.get(user.role, 'Dirección')

    elements = []
    pc_key = f'pc{periodo}'
    rp_key = f'rp{periodo}'

    for idx, est in enumerate(estudiantes):
        if idx > 0:
            elements.append(PageBreak())

        elements.append(Paragraph(col_nombre, ts))
        elements.append(Paragraph(f'REPORTE DE CALIFICACIONES — PERÍODO {periodo}', ss))
        elements.append(Paragraph(f'{cur_nombre} | Año Escolar {ano_nombre}', ss))
        elements.append(Spacer(1, 6))

        sep = Table([['']],  colWidths=[7*inch])
        sep.setStyle(TableStyle([('LINEBELOW', (0,0), (-1,-1), 1.5, colors.HexColor('#2563eb'))]))
        elements.append(sep)
        elements.append(Spacer(1, 8))

        elements.append(Paragraph(f'<b>{est.nombre_completo}</b>', ns))
        info = []
        if est.matricula: info.append(f'Matrícula: {est.matricula}')
        if est.no_lista: info.append(f'No. Lista: {est.no_lista}')
        if info:
            elements.append(Paragraph(' | '.join(info), ParagraphStyle('I', parent=styles['Normal'], fontSize=8, textColor=colors.HexColor('#64748b'))))
        elements.append(Spacer(1, 10))

        if simple:
            # Modo padres: solo Asignatura, Nota, Literal, Estado — SIN asistencia
            nota_label = 'Nota'
            headers = ['Asignatura', nota_label, 'Literal', 'Estado']
            tdata = [headers]
            nf_list = []
            for asig in asignaturas:
                c = cm.get((est.id, asig.id))
                if c:
                    pc = getattr(c, pc_key, None)
                    p4 = getattr(c, f'p{periodo}_p4', None)
                    rp = getattr(c, rp_key, None)
                    # Elegir nota base según opción
                    nota_base = p4 if usar_p4 else pc
                    # Si reprobó y tiene recuperación, usar RP
                    nfinal = rp if (nota_base is not None and nota_base < 70 and rp is not None) else nota_base
                    lit = c.get_literal(nfinal) if nfinal else '-'
                    est_str = 'Aprobado' if nfinal and nfinal >= 70 else 'Reprobado' if nfinal else '-'
                    if nfinal is not None: nf_list.append(nfinal)
                    row = [asig.nombre, _fv(nfinal), lit, est_str]
                else:
                    row = [asig.nombre, '-', '-', '-']
                tdata.append(row)
            prom = round(sum(nf_list) / len(nf_list), 1) if nf_list else 0
            pl = 'A' if prom >= 90 else 'B' if prom >= 80 else 'C' if prom >= 70 else 'F'
            tdata.append(['PROMEDIO GENERAL', str(prom), pl, 'Aprobado' if prom >= 70 else 'Reprobado'])
            cw = [3*inch, 1*inch, 0.8*inch, 1.2*inch]
            nota_col = 1
        else:
            # Modo completo: Asignatura, P1, P2, P3, Promedio (en vez de P4), PC, RP, Lit., Estado
            headers = ['Asignatura', 'P1', 'P2', 'P3', 'Promedio', 'PC', 'RP', 'Lit.', 'Estado']
            tdata = [headers]
            nf_list = []
            for asig in asignaturas:
                c = cm.get((est.id, asig.id))
                if c:
                    p1 = getattr(c, f'p{periodo}_p1', None)
                    p2 = getattr(c, f'p{periodo}_p2', None)
                    p3 = getattr(c, f'p{periodo}_p3', None)
                    p4 = getattr(c, f'p{periodo}_p4', None)
                    pc = getattr(c, pc_key, None)
                    rp = getattr(c, rp_key, None)
                    nfinal = rp if (pc is not None and pc < 70 and rp is not None) else pc
                    lit = c.get_literal(nfinal) if nfinal else '-'
                    est_str = 'Aprobado' if nfinal and nfinal >= 70 else 'Reprobado' if nfinal else '-'
                    if nfinal is not None: nf_list.append(nfinal)
                    # P4 column shows as "Promedio" — display p4 value or pc as the promedio
                    promedio_val = p4 if p4 is not None else pc
                    row = [asig.nombre[:22], _fv(p1), _fv(p2), _fv(p3), _fv(promedio_val), _fv(pc), _fv(rp), lit, est_str]
                else:
                    row = [asig.nombre[:22]] + ['-'] * 8
                tdata.append(row)
            prom = round(sum(nf_list) / len(nf_list), 1) if nf_list else 0
            pl = 'A' if prom >= 90 else 'B' if prom >= 80 else 'C' if prom >= 70 else 'F'
            tdata.append(['PROMEDIO', '', '', '', '', str(prom), '', pl, 'Aprobado' if prom >= 70 else 'Reprobado'])
            cw = [1.5*inch, 0.5*inch, 0.5*inch, 0.5*inch, 0.5*inch, 0.45*inch, 0.45*inch, 0.4*inch, 0.7*inch]
            nota_col = 5
        t = Table(tdata, colWidths=cw, repeatRows=1)
        sc = [
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1e3a5f')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 6.5),
            ('FONTSIZE', (0,1), (-1,-1), 7),
            ('ALIGN', (1,0), (-1,-1), 'CENTER'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
            ('ROWBACKGROUNDS', (0,1), (-1,-2), [colors.white, colors.HexColor('#f8fafc')]),
            ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor('#eff6ff')),
            ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 3),
            ('TOPPADDING', (0,0), (-1,-1), 3),
        ]
        for ri in range(1, len(tdata)):
            for ci in ([nota_col] if simple else [5, 6]):
                try:
                    if tdata[ri][ci] != '-' and float(tdata[ri][ci]) < 70:
                        sc.append(('TEXTCOLOR', (ci, ri), (ci, ri), colors.red))
                        sc.append(('FONTNAME', (ci, ri), (ci, ri), 'Helvetica-Bold'))
                except (ValueError, IndexError):
                    pass
            if tdata[ri][-1] == 'Reprobado':
                sc.append(('TEXTCOLOR', (-1, ri), (-1, ri), colors.red))
        t.setStyle(TableStyle(sc))
        elements.append(t)
        elements.append(Spacer(1, 10))

        # Asistencia — solo en modo completo, NO en reporte padres
        if not simple:
            pres = asist_pr.get(est.id, 0)
            tot = asist_tot.get(est.id, 0)
            pct = round(pres / tot * 100, 1) if tot > 0 else 0
            at = Table(
                [['ASISTENCIA', f'Presentes: {pres}', f'Ausencias: {tot-pres}', f'Total: {tot}', f'{pct}%']],
                colWidths=[1.2*inch, 1.2*inch, 1.2*inch, 1*inch, 0.9*inch]
            )
            at.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (0,0), colors.HexColor('#1e3a5f')),
                ('TEXTCOLOR', (0,0), (0,0), colors.white),
                ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'),
                ('FONTSIZE', (0,0), (-1,-1), 7.5),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
                ('BACKGROUND', (1,0), (-1,-1), colors.HexColor('#f0fdf4') if pct >= 80 else colors.HexColor('#fef2f2')),
            ]))
            elements.append(at)
        elements.append(Spacer(1, 20))

        # Firma con rol del que imprime
        ft = Table(
            [['_________________________', '', '_________________________'], [rol_firma, '', 'Padre/Madre/Tutor']],
            colWidths=[2.5*inch, 1*inch, 2.5*inch]
        )
        ft.setStyle(TableStyle([('ALIGN',(0,0),(-1,-1),'CENTER'),('FONTSIZE',(0,0),(-1,-1),8),('TEXTCOLOR',(0,0),(-1,-1),colors.HexColor('#64748b')),('TOPPADDING',(0,0),(-1,0),15)]))
        elements.append(ft)
        elements.append(Spacer(1, 6))
        elements.append(Paragraph(f'Generado por EducaOne — {datetime.now().strftime("%d/%m/%Y")}', fs))

    doc.build(elements)
    buf.seek(0)
    return buf


def _fv(v) -> str:
    """Format value for PDF cell"""
    if v is None:
        return '-'
    return str(int(v)) if isinstance(v, float) and v == int(v) else str(round(v, 1))
