"""
registro_validator.py
=====================
Valida que los datos de un curso estén COMPLETOS Y CONSISTENTES
antes de generar un Registro Escolar PDF.

Ninguna validación aquí modifica datos — solo devuelve problemas encontrados.
"""

from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
import re

from models import (
    Curso, Grado, Estudiante, Usuario, Asignatura,
    AsignacionProfesor, Calificacion, CalificacionPrimaria,
    CalificacionSecundaria,
    Asistencia, AnoEscolar, ConfiguracionColegio, Horario
)


class ValidationResult:
    """Resultado de validación: lista de problemas encontrados y nivel de severidad."""
    
    def __init__(self):
        self.errors: List[str] = []        # Bloquean generación
        self.warnings: List[str] = []       # No bloquean, pero se reportan
        self.info: Dict[str, Any] = {}      # Datos auxiliares (ej: profesor titular encontrado)
    
    def add_error(self, msg: str):
        self.errors.append(msg)
    
    def add_warning(self, msg: str):
        self.warnings.append(msg)
    
    @property
    def is_valid(self) -> bool:
        """True si NO hay errores que bloqueen la generación."""
        return len(self.errors) == 0
    
    def to_dict(self) -> dict:
        return {
            'valid': self.is_valid,
            'errors': self.errors,
            'warnings': self.warnings,
            'info': self.info,
        }


def _normalizar_nivel(nivel_raw) -> str:
    """Normaliza valores legados ('Secundario', 'Primario', NULL) a canónicos."""
    if not nivel_raw:
        return 'secundaria'
    low = str(nivel_raw).lower().strip()
    if low.startswith('prim'):
        return 'primaria'
    if low.startswith('sec'):
        return 'secundaria'
    if low.startswith('ini') or low.startswith('prees') or low.startswith('pre-'):
        return 'inicial'
    return 'secundaria'


def _extraer_grado_numero(nombre_grado: str) -> int:
    """Extrae el número del grado: '1ro Sec' -> 1, '5to Primaria' -> 5."""
    if not nombre_grado:
        return 1
    m = re.search(r'(\d+)', nombre_grado)
    return int(m.group(1)) if m else 1


def _normalizar_mes_clave(mes_raw: str) -> str:
    mapa = {
        'agosto': 'ago', 'ago': 'ago',
        'septiembre': 'sep', 'sep': 'sep',
        'octubre': 'oct', 'oct': 'oct',
        'noviembre': 'nov', 'nov': 'nov',
        'diciembre': 'dic', 'dic': 'dic',
        'enero': 'ene', 'ene': 'ene',
        'febrero': 'feb', 'feb': 'feb',
        'marzo': 'mar', 'mar': 'mar',
        'abril': 'abr', 'abr': 'abr',
        'mayo': 'may', 'may': 'may',
        'junio': 'jun', 'jun': 'jun',
        'julio': 'jul', 'jul': 'jul',
    }
    return mapa.get(str(mes_raw or '').strip().lower(), str(mes_raw or '').strip().lower())


def _sumar_dias_trabajados(ano: AnoEscolar) -> int:
    if not ano:
        return 0
    try:
        dias = ano.get_dias_trabajados()
    except Exception:
        dias = {}
    total = 0
    for _, valor in (dias or {}).items():
        try:
            total += max(int(valor), 0)
        except (TypeError, ValueError):
            continue
    return total


def _evaluar_cobertura_asistencia(
    db: Session,
    curso_id: int,
    estudiantes: List[Estudiante],
    asignatura_ids: Optional[List[int]] = None,
    ventanas_por_est: Optional[Dict[int, list]] = None,
) -> Dict[str, Any]:
    """TRAS-1 · Con `ventanas_por_est` (curso con traslados o retiros), lo
    esperado se cuenta celda a celda: solo los días en que cada estudiante
    PERTENECÍA al curso. Sin ese parámetro, la cuenta de siempre."""
    from registro_asistencia import build_asistencia_registro

    resultado = {
        'total_esperado': 0,
        'total_cubierto': 0,
        'faltantes': [],
    }

    objetivos = asignatura_ids if asignatura_ids else [None]
    for asig_id in objetivos:
        matriz = build_asistencia_registro(db, curso_id, asignatura_id=asig_id, estudiantes=estudiantes,
                                           ventanas_por_est=ventanas_por_est)
        if not matriz:
            continue

        for mes in matriz:
            # S1 — solo se espera asistencia de las sesiones que SI se impartieron.
            # `dias_computables` son las columnas visibles menos las declaradas no
            # impartidas; sin este descuento, una suspension correctamente
            # registrada se reportaba como "Asistencia incompleta". El fallback a
            # `dias` cubre las matrices anteriores a S1, que no traen el campo.
            dias_computables = mes.get('dias_computables')
            if dias_computables is None:
                dias_computables = len(mes.get('dias', []))
            esperado = dias_computables * len(estudiantes)
            cobertura_pct = mes.get('cobertura_registro_pct', 0.0)
            cubierto = round((esperado * cobertura_pct) / 100) if esperado else 0
            if ventanas_por_est:
                filas = mes.get('filas') or []
                esperado = sum(f.get('dias_aplicables', 0) for f in filas)
                cubierto = sum(f.get('con_dato', 0) for f in filas)
            faltante = max(esperado - cubierto, 0)

            resultado['total_esperado'] += esperado
            resultado['total_cubierto'] += cubierto
            if faltante > 0:
                resultado['faltantes'].append({
                    'asignatura_id': asig_id,
                    'mes': mes.get('mes'),
                    'faltante': faltante,
                    'esperado': esperado,
                    'cobertura_pct': cobertura_pct,
                })

    return resultado


def _permanencia_registro(db: Session, curso, colegio_id: int):
    """TRAS-1 · Quiénes entran en el Registro del curso y en qué días.

    Devuelve `(miembros, ventanas, hay_movimientos)`:
      · `miembros`: los activos del curso, sus retirados y quienes entraron o
        salieron por traslado (ver `permanencia.miembros_curso`), por número;
      · `ventanas`: `{estudiante_id: [(desde, hasta)]}` de cada uno EN ESTE curso;
      · `hay_movimientos`: si alguno tiene retiro o traslado. Si nadie lo tiene
        el Registro se valida exactamente como antes.
    """
    import permanencia as P
    miembros = P.miembros_curso(db, curso, colegio_id)
    ventanas = {m.estudiante.id: m.ventanas for m in miembros}
    hay = any(m.salio or m.primero.motivo_inicio != P.INICIO or len(m.en_curso) > 1
              for m in miembros)
    return miembros, ventanas, hay


def _marcas_fuera_de_permanencia(db: Session, curso_id: int, miembros) -> Dict[str, Any]:
    """TRAS-1 · Marcas que contradicen la permanencia, SIN tocarlas.

    · `inconsistentes`: marcas de OTRO curso en un día en que el estudiante
      pertenecía a ESTE (eso sí es un error de datos);
    · `fuera`: marcas de ESTE curso en días en que el estudiante no le
      pertenecía (después de trasladarse o retirarse, antes de incorporarse).
      Se ven en el Registro pero no cuentan; aquí se explican.
    Las marcas válidas del curso anterior no son ni lo uno ni lo otro.
    """
    ids = [m.estudiante.id for m in miembros]
    out = {'inconsistentes': 0, 'fuera': []}
    if not ids:
        return out
    por_id = {m.estudiante.id: m for m in miembros}
    for a in db.query(Asistencia).filter(Asistencia.estudiante_id.in_(ids)).all():
        m = por_id[a.estudiante_id]
        if a.curso_id is None:
            continue
        if a.curso_id == curso_id:
            if not m.aplica(a.fecha):
                out['fuera'].append(a)
        elif m.aplica(a.fecha):
            out['inconsistentes'] += 1
    return out


def _agregar_aviso_fuera_de_permanencia(r, fuera, miembros) -> None:
    """Explica (advertencia) las marcas de este curso fuera de la permanencia.
    No se borran, no se mueven y no se cuentan."""
    if not fuera:
        return
    import permanencia as P
    nombres = {m.estudiante.id: m.estudiante.nombre_completo for m in miembros}
    por_est: Dict[int, list] = {}
    for a in fuera:
        por_est.setdefault(a.estudiante_id, []).append(a.fecha)
    partes = []
    for eid, fs in list(por_est.items())[:5]:
        fs = sorted(fs)
        txt = ', '.join(P.fmt_fecha(f) for f in fs[:3]) + ('…' if len(fs) > 3 else '')
        partes.append('%s: %d marca(s) (%s)' % (nombres.get(eid, eid), len(fs), txt))
    r.add_warning(
        "Hay %d marca(s) de asistencia de este curso en días en que el estudiante "
        "no le pertenecía (después de su traslado o retiro, o antes de "
        "incorporarse). Se conservan y se ven en el Registro, pero no cuentan. "
        "Revise la fecha del movimiento. %s" % (len(fuera), '; '.join(partes)))
    r.info['marcas_fuera_de_permanencia'] = len(fuera)


def validar_registro_secundaria(db: Session, curso_id: int, colegio_id: int) -> ValidationResult:
    """
    Valida que un curso de secundaria tenga todos los datos necesarios
    para generar su Registro Escolar MINERD.
    """
    r = ValidationResult()
    
    # === 1. CURSO EXISTE Y ES DE SECUNDARIA ===
    curso = db.query(Curso).filter_by(id=curso_id).first()
    if not curso:
        r.add_error(f"El curso con id={curso_id} no existe")
        return r
    
    if curso.colegio_id != colegio_id:
        r.add_error("El curso no pertenece a este colegio")
        return r
    
    grado = curso.grado
    if not grado:
        r.add_error("El curso no tiene grado asignado")
        return r
    
    nivel_canonico = _normalizar_nivel(grado.nivel)
    if nivel_canonico != 'secundaria':
        r.add_error(
            f"Este curso es de '{nivel_canonico}', no de secundaria. "
            f"Use el endpoint de {nivel_canonico} en su lugar."
        )
        return r
    
    grado_numero = _extraer_grado_numero(grado.nombre)
    if grado_numero < 1 or grado_numero > 6:
        r.add_error(
            f"No se pudo determinar el número de grado de '{grado.nombre}'. "
            f"El registro solo soporta 1ro-6to de secundaria."
        )
        return r
    
    r.info['grado_numero'] = grado_numero
    r.info['nivel'] = nivel_canonico
    
    # === 2. COLEGIO TIENE CONFIGURACIÓN BÁSICA ===
    config = db.query(ConfiguracionColegio).filter_by(colegio_id=colegio_id).first()
    if not config:
        r.add_error("El colegio no tiene configuración registrada. Complete los datos en Configuración.")
        return r
    
    if not config.nombre:
        r.add_error("El colegio no tiene nombre configurado")
    if not getattr(config, 'regional', None):
        r.add_error("Falta código de Regional del colegio")
    if not getattr(config, 'distrito', None):
        r.add_error("Falta código de Distrito del colegio")
    if not getattr(config, 'codigo_centro', None):
        r.add_error("Falta código del centro (SIGERD)")
    
    # === 3. AÑO ESCOLAR ACTIVO ===
    ano = db.query(AnoEscolar).filter_by(colegio_id=colegio_id, activo=True).first()
    if not ano:
        r.add_error("No hay año escolar activo. Active uno en Configuración → Año Escolar.")
        return r
    r.info['ano_escolar_id'] = ano.id
    r.info['ano_escolar_nombre'] = ano.nombre
    r.info['dias_trabajados_configurados_total'] = _sumar_dias_trabajados(ano)
    
    # === 4. ESTUDIANTES DEL CURSO ===
    # TRAS-1 · los del curso en su año: activos, retirados y quienes entraron
    # o salieron por traslado, cada uno con su número en el curso.
    miembros, ventanas, hay_movimientos = _permanencia_registro(db, curso, colegio_id)
    estudiantes = [m.estudiante for m in miembros]
    salieron = {m.estudiante.id for m in miembros if m.salio}

    if not any(m.estudiante.activo for m in miembros):
        r.add_error(f"El curso '{curso.nombre_completo}' no tiene estudiantes activos")
        return r

    # REG-43: la plantilla y su capacidad las decide el generador
    # (`seleccionar_plantilla`); aquí se adelanta su respuesta con el MISMO
    # mensaje. Antes se avisaba de que "se tomarán los primeros 40", pero el
    # generador no recorta: rechaza. 1ro con 41-43 usa la plantilla ampliada.
    from registro_escolar import seleccionar_plantilla, RegistroExcedePlantilla
    try:
        _ampliada = seleccionar_plantilla(grado_numero, len(estudiantes))
    except RegistroExcedePlantilla as exc:
        r.add_error(exc.detalle['mensaje'])
    else:
        if _ampliada:
            r.info['plantilla_ampliada'] = _ampliada['archivo']
    
    r.info['total_estudiantes'] = len(estudiantes)
    r.info['estudiante_ids'] = [e.id for e in estudiantes]
    
    # Validar que todos los estudiantes tengan curso_id correcto (consistencia).
    # TRAS-1 · quien se trasladó tiene la ficha en su nuevo curso: es correcto.
    for m in miembros:
        e = m.estudiante
        if e.curso_id != curso_id and m.ultimo.motivo_fin != 'traslado':
            r.add_error(f"INCONSISTENCIA: estudiante {e.nombre_completo} (id={e.id}) tiene curso_id={e.curso_id} pero lo encontramos filtrando por curso_id={curso_id}")
    
    # === 5. PROFESOR TITULAR DEL CURSO ===
    titular = db.query(AsignacionProfesor).filter_by(
        curso_id=curso_id,
        es_titular=True,
        activo=True,
        colegio_id=colegio_id
    ).first()
    
    if not titular:
        r.add_error(
            f"El curso '{curso.nombre_completo}' no tiene PROFESOR TITULAR asignado. "
            f"Vaya a Asignaciones → edite el curso → marque 'Es titular' en uno de los profesores."
        )
    else:
        profesor = db.query(Usuario).filter_by(id=titular.profesor_id).first()
        if not profesor:
            r.add_error("El profesor titular asignado no existe en el sistema")
        else:
            r.info['titular_id'] = profesor.id
            r.info['titular_nombre'] = profesor.nombre_completo
    
    # === 6. ASIGNATURAS DEL CURSO (tienen profesor asignado) ===
    asignaciones = db.query(AsignacionProfesor).filter_by(
        curso_id=curso_id, activo=True, colegio_id=colegio_id
    ).all()
    
    if not asignaciones:
        r.add_error(f"El curso '{curso.nombre_completo}' no tiene asignaciones de profesores por asignatura")
        return r
    
    asignatura_ids = list({a.asignatura_id for a in asignaciones})
    r.info['asignatura_ids'] = asignatura_ids
    r.info['total_asignaturas'] = len(asignatura_ids)

    asignaturas = db.query(Asignatura).filter(Asignatura.id.in_(asignatura_ids)).all()

    horarios = db.query(Horario).filter_by(
        curso_id=curso_id,
        activo=True,
        tipo_bloque='clase',
    ).all()
    horarios_por_asig = {h.asignatura_id for h in horarios if h.asignatura_id}
    for asig_id in asignatura_ids:
        if asig_id not in horarios_por_asig:
            nom = next((a.nombre for a in asignaturas if a.id == asig_id), f"Asignatura id={asig_id}")
            r.add_error(f"La asignatura '{nom}' no tiene horario configurado para este curso")
    
    # === 7. CALIFICACIONES por asignatura (modelo académico REAL: CalificacionSecundaria) ===
    #
    # R1.5: el Registro OFICIAL de Secundaria se genera desde CalificacionSecundaria
    # (una fila por competencia 1-4) y su CF sale de _calcular_cf_secundaria(), que
    # exige:
    #   1. las 4 competencias DISTINTAS {1,2,3,4} cargadas para (estudiante, asignatura,
    #      año escolar ACTIVO, colegio actual);
    #   2. para CADA período p∈{1,2,3,4}: las 4 competencias con valor_periodo(p) != None
    #      (o sea CalificacionSecundaria.calcular_pc_periodo(comps4, p) != None).
    # Se valida EXACTAMENTE esa condición — la misma puerta que usa el generador —,
    # NO "existe alguna fila". La tabla legacy `Calificacion` NO participa aquí:
    # un curso moderno no puede pasar la validación por notas legacy.
    asig_nombre_by_id = {a.id: a.nombre for a in asignaturas}
    _est_ids = [e.id for e in estudiantes]
    # TRAS-1 · contexto para el mensaje de notas faltantes de quien llegó por
    # traslado: sus notas anteriores pueden estar en otra asignatura, y no se
    # trasladan ni se dan por equivalentes automáticamente.
    import permanencia as _P
    _incorporados = {m.estudiante.id: m.primero.desde for m in miembros
                     if m.primero.motivo_inicio == _P.TRASLADO}
    REQ = (1, 2, 3, 4)
    REQ_SET = set(REQ)

    # Una sola consulta, acotada por: colegio actual (tolerando colegio_id NULL de
    # datos antiguos — el filtro por estudiante_id ya garantiza el tenant), año
    # ACTIVO, asignaturas asignadas al curso y estudiantes del curso. Una fila de
    # otro año / otro colegio / otro estudiante NO entra.
    _cs_rows = db.query(CalificacionSecundaria).filter(
        CalificacionSecundaria.ano_escolar_id == ano.id,
        CalificacionSecundaria.asignatura_id.in_(asignatura_ids),
        CalificacionSecundaria.estudiante_id.in_(_est_ids),
        or_(CalificacionSecundaria.colegio_id == colegio_id,
            CalificacionSecundaria.colegio_id.is_(None)),
    ).all()

    # Consistencia de tenant: alguna fila de estos estudiantes/asignaturas/año con
    # colegio_id de OTRO colegio es una anomalía de datos.
    _cs_ajenas = db.query(CalificacionSecundaria).filter(
        CalificacionSecundaria.ano_escolar_id == ano.id,
        CalificacionSecundaria.asignatura_id.in_(asignatura_ids),
        CalificacionSecundaria.estudiante_id.in_(_est_ids),
        CalificacionSecundaria.colegio_id != None,  # noqa: E711
        CalificacionSecundaria.colegio_id != colegio_id,
    ).count()
    if _cs_ajenas:
        r.add_error(
            f"INCONSISTENCIA: {_cs_ajenas} calificación(es) de secundaria de este "
            f"curso tienen colegio_id de otro colegio. Contacte soporte técnico."
        )

    # Index: (estudiante_id, asignatura_id) -> {competencia_numero: fila}
    _por_par: Dict[tuple, Dict[int, Any]] = {}
    for cs in _cs_rows:
        if cs.competencia_numero in REQ_SET:
            _por_par.setdefault((cs.estudiante_id, cs.asignatura_id), {})[cs.competencia_numero] = cs

    r.info['total_calificaciones_registradas'] = len(_cs_rows)
    _pares_completos = 0
    _pares_incompletos = 0

    for asig_id in asignatura_ids:
        asig_nom = asig_nombre_by_id.get(asig_id, f"Asignatura id={asig_id}")
        incompletos: List[str] = []
        for est in estudiantes:
            # TRAS-1 · quien salió del curso (trasladado o retirado) no recibe
            # aquí calificación final: no se le exigen los períodos que no
            # cursó en él. Su nota final la emite el curso donde termina.
            if est.id in salieron:
                continue
            by_num = _por_par.get((est.id, asig_id), {})
            faltan_comp = sorted(REQ_SET - set(by_num))
            _ctx_tras = ((" (incorporado por traslado desde %s: sus notas anteriores "
                          "no se trasladan ni se dan por equivalentes; requiere "
                          "decisión de Dirección)" % _P.fmt_fecha(_incorporados[est.id]))
                         if est.id in _incorporados else "")
            if faltan_comp:
                _pares_incompletos += 1
                incompletos.append(
                    f"{est.nombre_completo}: falta(n) la(s) competencia(s) "
                    f"{', '.join(map(str, faltan_comp))}{_ctx_tras}"
                )
                continue
            # Las 4 competencias distintas existen: validar cada período.
            comps4 = [by_num[n] for n in REQ]
            periodos_incompletos = [
                p for p in REQ if CalificacionSecundaria.calcular_pc_periodo(comps4, p) is None
            ]
            if periodos_incompletos:
                _pares_incompletos += 1
                incompletos.append(
                    f"{est.nombre_completo}: tiene las 4 competencias pero falta(n) "
                    f"nota(s) del/los período(s) {', '.join(map(str, periodos_incompletos))}{_ctx_tras}"
                )
                continue
            _pares_completos += 1

        if incompletos:
            n = len(incompletos)
            ejemplos = "; ".join(incompletos[:5])
            extra = f" (y {n - 5} más)" if n > 5 else ""
            r.add_error(
                f"Faltan competencias/notas de secundaria en '{asig_nom}' para "
                f"{n} estudiante(s). Ejemplos — {ejemplos}{extra}"
            )

    r.info['pares_completos_secundaria'] = _pares_completos
    r.info['pares_incompletos_secundaria'] = _pares_incompletos
    
    # === 8. ASISTENCIA registrada ===
    total_asistencia = db.query(Asistencia).filter(
        Asistencia.estudiante_id.in_([e.id for e in estudiantes])
    ).count()
    
    r.info['total_asistencias'] = total_asistencia
    
    if total_asistencia == 0:
        r.add_error("El curso no tiene asistencia registrada")
    elif r.info['dias_trabajados_configurados_total'] > 0 and total_asistencia < len(estudiantes):
        r.add_warning(
            "La asistencia existe, pero el volumen registrado parece insuficiente para cubrir "
            "todos los estudiantes al menos una vez. Revise captura diaria antes de imprimir."
        )
    
    # Consistencia: asistencia apunta al curso correcto.
    # TRAS-1 · con traslados o retiros, una marca de otro curso solo es
    # inconsistente si cae en un día en que el estudiante pertenecía a ESTE;
    # las del curso anterior, dentro de su tramo allí, son válidas. Y las de
    # este curso fuera de la permanencia se explican sin tocarlas.
    if hay_movimientos:
        _fp = _marcas_fuera_de_permanencia(db, curso_id, miembros)
        asist_inconsistentes = _fp['inconsistentes']
        _agregar_aviso_fuera_de_permanencia(r, _fp['fuera'], miembros)
    else:
        asist_inconsistentes = db.query(Asistencia).filter(
            Asistencia.estudiante_id.in_([e.id for e in estudiantes]),
            Asistencia.curso_id != None,
            Asistencia.curso_id != curso_id
        ).count()
    if asist_inconsistentes > 0:
        r.add_error(
            f"INCONSISTENCIA: {asist_inconsistentes} registros de asistencia "
            f"de estudiantes del curso {curso_id} apuntan a otro curso_id. "
            f"Contacte soporte técnico."
        )

    # TRAS-1 · la cobertura de quienes siguen en el curso bloquea, como
    # siempre; la de quienes ya salieron (días sin lista antes de su traslado
    # o retiro) se avisa sin bloquear: no se convierte en falta ni en
    # presencia, y no impide emitir el Registro del resto.
    _siguen = [e for e in estudiantes if e.id not in salieron]
    _salidos = [e for e in estudiantes if e.id in salieron]
    cobertura = _evaluar_cobertura_asistencia(
        db, curso_id, _siguen, asignatura_ids=asignatura_ids,
        ventanas_por_est=ventanas if hay_movimientos else None)
    r.info['asistencia_esperada_total'] = cobertura['total_esperado']
    r.info['asistencia_cubierta_total'] = cobertura['total_cubierto']
    if cobertura['total_esperado'] > 0 and cobertura['faltantes']:
        for item in cobertura['faltantes'][:12]:
            asig_nom = asig_nombre_by_id.get(item['asignatura_id'], f"Asignatura id={item['asignatura_id']}")
            r.add_error(
                f"Asistencia incompleta en '{asig_nom}' para {item['mes']}: "
                f"faltan {item['faltante']} de {item['esperado']} celdas esperadas"
            )
    if _salidos:
        _cob_s = _evaluar_cobertura_asistencia(
            db, curso_id, _salidos, asignatura_ids=asignatura_ids, ventanas_por_est=ventanas)
        for item in _cob_s['faltantes'][:12]:
            asig_nom = asig_nombre_by_id.get(item['asignatura_id'], f"Asignatura id={item['asignatura_id']}")
            r.add_warning(
                f"Días sin lista de estudiantes trasladados o retirados en '{asig_nom}' "
                f"para {item['mes']}: {item['faltante']} de {item['esperado']} celdas de "
                f"su permanencia (quedan en blanco; no cuentan como falta)"
            )
    
    return r


def validar_registro_primaria(db: Session, curso_id: int, colegio_id: int) -> ValidationResult:
    """
    Valida datos para registro PRIMARIA. Usa CalificacionPrimaria (C1, C2, C3).
    """
    r = ValidationResult()
    
    curso = db.query(Curso).filter_by(id=curso_id).first()
    if not curso:
        r.add_error(f"El curso con id={curso_id} no existe")
        return r
    
    if curso.colegio_id != colegio_id:
        r.add_error("El curso no pertenece a este colegio")
        return r
    
    grado = curso.grado
    if not grado:
        r.add_error("El curso no tiene grado asignado")
        return r
    
    nivel_canonico = _normalizar_nivel(grado.nivel)
    if nivel_canonico != 'primaria':
        r.add_error(
            f"Este curso es de '{nivel_canonico}', no de primaria. "
            f"Use el endpoint de {nivel_canonico} en su lugar."
        )
        return r
    
    grado_numero = _extraer_grado_numero(grado.nombre)
    if grado_numero < 1 or grado_numero > 6:
        r.add_error(f"No se pudo determinar número de grado (1-6) de '{grado.nombre}'")
        return r
    
    r.info['grado_numero'] = grado_numero
    r.info['nivel'] = 'primaria'
    r.info['ciclo'] = 'primer_ciclo' if grado_numero <= 3 else 'segundo_ciclo'
    
    # Config colegio
    config = db.query(ConfiguracionColegio).filter_by(colegio_id=colegio_id).first()
    if not config:
        r.add_error("El colegio no tiene configuración registrada. Complete los datos en Configuración.")
        return r
    if not config.nombre:
        r.add_error("Falta nombre del colegio en Configuración")
    if not getattr(config, 'regional', None):
        r.add_error("Falta código de Regional del colegio")
    if not getattr(config, 'distrito', None):
        r.add_error("Falta código de Distrito del colegio")
    if not getattr(config, 'codigo_centro', None):
        r.add_error("Falta código del centro (SIGERD)")
    
    # Año escolar activo
    ano = db.query(AnoEscolar).filter_by(colegio_id=colegio_id, activo=True).first()
    if not ano:
        r.add_error("No hay año escolar activo")
        return r
    r.info['ano_escolar_id'] = ano.id
    r.info['ano_escolar_nombre'] = ano.nombre
    r.info['dias_trabajados_configurados_total'] = _sumar_dias_trabajados(ano)
    
    # Estudiantes
    # TRAS-1 · activos, retirados y quienes entraron o salieron por traslado.
    miembros, ventanas, hay_movimientos = _permanencia_registro(db, curso, colegio_id)
    estudiantes = [m.estudiante for m in miembros]
    salieron = {m.estudiante.id for m in miembros if m.salio}
    if not any(m.estudiante.activo for m in miembros):
        r.add_error(f"El curso '{curso.nombre_completo}' no tiene estudiantes activos")
        return r
    if len(estudiantes) > 40:
        r.add_warning(f"Curso con {len(estudiantes)} estudiantes (máximo MINERD 40)")
    r.info['total_estudiantes'] = len(estudiantes)
    
    # Consistencia (TRAS-1: quien se trasladó tiene la ficha en su nuevo curso)
    for m in miembros:
        e = m.estudiante
        if e.curso_id != curso_id and m.ultimo.motivo_fin != 'traslado':
            r.add_error(f"INCONSISTENCIA: estudiante {e.nombre_completo} en curso_id distinto")
    
    # Profesor titular (en primaria es el profesor de aula = 1 profesor por curso)
    titular = db.query(AsignacionProfesor).filter_by(
        curso_id=curso_id, es_titular=True, activo=True, colegio_id=colegio_id
    ).first()
    
    if not titular:
        r.add_error(
            f"El curso '{curso.nombre_completo}' no tiene PROFESOR TITULAR (profesor de aula). "
            f"En primaria, 1 profesor dicta todas las áreas del grado."
        )
    else:
        profesor = db.query(Usuario).filter_by(id=titular.profesor_id).first()
        if profesor:
            r.info['titular_id'] = profesor.id
            r.info['titular_nombre'] = profesor.nombre_completo
    
    # Asignaciones
    asignaciones = db.query(AsignacionProfesor).filter_by(
        curso_id=curso_id, activo=True, colegio_id=colegio_id
    ).all()
    if not asignaciones:
        r.add_error("El curso no tiene asignaciones de profesores por áreas")
        return r
    
    asignatura_ids = list({a.asignatura_id for a in asignaciones})
    r.info['asignatura_ids'] = asignatura_ids
    r.info['total_areas'] = len(asignatura_ids)

    horarios = db.query(Horario).filter_by(
        curso_id=curso_id,
        activo=True,
        tipo_bloque='clase',
    ).all()
    if not horarios:
        r.add_error("El curso no tiene horario configurado")
    
    # Calificaciones primaria (por competencia)
    asignaturas = db.query(Asignatura).filter(Asignatura.id.in_(asignatura_ids)).all()
    asig_nombre_by_id = {a.id: a.nombre for a in asignaturas}
    
    faltantes_por_area = {}
    total_califs = 0
    
    for asig_id in asignatura_ids:
        # En primaria se espera al menos calificaciones de C1, C2, C3 (3 competencias)
        _evaluados = [e for e in estudiantes if e.id not in salieron]
        califs = db.query(CalificacionPrimaria).filter(
            CalificacionPrimaria.asignatura_id == asig_id,
            CalificacionPrimaria.estudiante_id.in_([e.id for e in _evaluados])
        ).all()
        total_califs += len(califs)
        
        # Un estudiante debe tener 3 registros (uno por competencia) para esa área
        estudiantes_con_3_competencias = {}
        for c in califs:
            if c.estudiante_id not in estudiantes_con_3_competencias:
                estudiantes_con_3_competencias[c.estudiante_id] = set()
            estudiantes_con_3_competencias[c.estudiante_id].add(c.competencia_numero)
        
        estudiantes_completos = sum(1 for comps in estudiantes_con_3_competencias.values() if len(comps) >= 3)
        faltantes = len(_evaluados) - estudiantes_completos
        
        if faltantes > 0:
            nom = asig_nombre_by_id.get(asig_id, f"Área id={asig_id}")
            faltantes_por_area[nom] = faltantes
    
    for area, cant in faltantes_por_area.items():
        r.add_error(f"Faltan calificaciones completas (C1, C2, C3) en '{area}' para {cant} estudiante(s)")
    
    r.info['total_calificaciones_registradas'] = total_califs
    
    # Asistencia
    total_asist = db.query(Asistencia).filter(
        Asistencia.estudiante_id.in_([e.id for e in estudiantes])
    ).count()
    r.info['total_asistencias'] = total_asist
    
    if total_asist == 0:
        r.add_error("Sin asistencia registrada")
    elif r.info['dias_trabajados_configurados_total'] > 0 and total_asist < len(estudiantes):
        r.add_warning(
            "La asistencia existe, pero el volumen registrado parece insuficiente para cubrir "
            "todos los estudiantes al menos una vez. Revise captura diaria antes de imprimir."
        )

    if hay_movimientos:
        _agregar_aviso_fuera_de_permanencia(
            r, _marcas_fuera_de_permanencia(db, curso_id, miembros)['fuera'], miembros)
    _siguen = [e for e in estudiantes if e.id not in salieron]
    _salidos = [e for e in estudiantes if e.id in salieron]
    cobertura = _evaluar_cobertura_asistencia(
        db, curso_id, _siguen, ventanas_por_est=ventanas if hay_movimientos else None)
    r.info['asistencia_esperada_total'] = cobertura['total_esperado']
    r.info['asistencia_cubierta_total'] = cobertura['total_cubierto']
    if cobertura['total_esperado'] > 0 and cobertura['faltantes']:
        for item in cobertura['faltantes'][:12]:
            r.add_error(
                f"Asistencia incompleta en {item['mes']}: "
                f"faltan {item['faltante']} de {item['esperado']} celdas esperadas"
            )
    if _salidos:
        for item in _evaluar_cobertura_asistencia(
                db, curso_id, _salidos, ventanas_por_est=ventanas)['faltantes'][:12]:
            r.add_warning(
                f"Días sin lista de estudiantes trasladados o retirados en {item['mes']}: "
                f"{item['faltante']} de {item['esperado']} celdas de su permanencia "
                f"(quedan en blanco; no cuentan como falta)")

    return r
