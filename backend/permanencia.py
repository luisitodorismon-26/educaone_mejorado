# -*- coding: utf-8 -*-
"""
permanencia.py — en qué curso estuvo un estudiante, con qué número y desde/hasta
qué día, dentro de UN año escolar (TRAS-1).

UNA SOLA FICHA, VARIOS TRAMOS
    El estudiante tiene una sola ficha. Un traslado o un retiro no crean otra:
    se guardan como `MovimientoEstudiante` y de ellos se deducen los TRAMOS:

        5to A Vespertina, n.º 15, del inicio del año al 20/10  (sale por traslado)
        5to A Matutina,   n.º 31, desde el 21/10                (entra por traslado)

    Cada curso ve solo su tramo: el origen conserva al estudiante en su
    historia y en su Registro; el destino lo tiene desde el día efectivo.

SIN MOVIMIENTOS NO CAMBIA NADA
    Un estudiante sin movimientos tiene un único tramo implícito, el de su
    ficha: su curso y su número actuales, desde que le aplica la asistencia
    (inicio del año o alta) hasta `fecha_retiro`. Es exactamente lo que hacía
    el sistema antes de esta tabla. No se rellena nada ni se inventa ninguna
    fecha para los estudiantes ya existentes.

EL DÍA EFECTIVO («desde qué día»)
    · traslado: destino DESDE ese día; origen HASTA el día anterior;
    · retiro: retirado desde ese día; su último día es el anterior;
    · reactivación: vuelve a pertenecer al curso desde ese día. Entre el retiro
      y la reactivación no pertenece a ningún curso: esos días NO APLICAN.

Este módulo solo LEE. Las operaciones que escriben viven en app.py.
"""
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional

TRASLADO = 'traslado'
RETIRO = 'retiro'
REACTIVACION = 'reactivacion'
TIPOS = (TRASLADO, RETIRO, REACTIVACION)

INICIO = 'inicio'


@dataclass
class Tramo:
    """La pertenencia del estudiante a UN curso, sin huecos dentro."""
    curso_id: Optional[int]
    no_lista: Optional[int]
    # None = desde que le aplica normalmente (inicio del año o su alta), igual
    # que antes de que existieran los tramos.
    desde: Optional[date]
    # None = vigente (hasta el fin del año).
    hasta: Optional[date]
    motivo_inicio: str = INICIO               # 'inicio' | 'traslado' | 'reactivacion'
    motivo_fin: Optional[str] = None          # None | 'traslado' | 'retiro'
    curso_origen_id: Optional[int] = None     # de dónde vino (entrada por traslado)
    curso_destino_id: Optional[int] = None    # a dónde fue (salida por traslado)

    def contiene(self, fecha: date) -> bool:
        if self.desde is not None and fecha < self.desde:
            return False
        if self.hasta is not None and fecha > self.hasta:
            return False
        return True

    @property
    def fecha_salida(self) -> Optional[date]:
        """El día desde el que ya NO pertenece a este curso."""
        return self.hasta + timedelta(days=1) if self.hasta is not None else None

    @property
    def vigente(self) -> bool:
        return self.hasta is None


def _fecha(valor) -> Optional[date]:
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor)[:10]) if valor else None
    except ValueError:
        return None


def construir_tramos(estudiante, movimientos) -> List[Tramo]:
    """Los tramos de UN estudiante en UN año, en orden.

    `movimientos` son los de ese estudiante y ese año. Sin ninguno, el tramo
    implícito de la ficha.
    """
    movs = sorted(movimientos or (), key=lambda m: (m.secuencia, m.id or 0))
    if not movs:
        # Solo cuenta para quien está realmente INACTIVO: una ficha activa con
        # una `fecha_retiro` antigua (dato heredado) sigue perteneciendo a su
        # curso, como antes de los tramos.
        hasta = getattr(estudiante, 'fecha_retiro', None) if not getattr(estudiante, 'activo', True) else None
        return [Tramo(getattr(estudiante, 'curso_id', None),
                      getattr(estudiante, 'no_lista', None), None, hasta,
                      INICIO, RETIRO if hasta is not None else None)]

    tramos: List[Tramo] = []
    primero = movs[0]
    actual: Optional[Tramo] = Tramo(primero.curso_origen_id, primero.no_lista_origen,
                                    None, None, INICIO, None)
    if primero.tipo == REACTIVACION:
        # El retiro es anterior a esta tabla: su fecha se guardó en el detalle
        # de la reactivación (antes, reactivar la borraba).
        previo = primero.get_detalle().get('retiro_previo') or {}
        actual.hasta = _fecha(previo.get('fecha_retiro'))
        actual.motivo_fin = RETIRO
        tramos.append(actual)
        actual = None

    for m in movs:
        if m.tipo == TRASLADO:
            if actual is not None:
                actual.hasta = m.fecha_efectiva - timedelta(days=1)
                actual.motivo_fin = TRASLADO
                actual.curso_destino_id = m.curso_destino_id
                tramos.append(actual)
            actual = Tramo(m.curso_destino_id, m.no_lista_destino, m.fecha_efectiva,
                           None, TRASLADO, None, curso_origen_id=m.curso_origen_id)
        elif m.tipo == RETIRO:
            if actual is not None:
                actual.hasta = m.fecha_efectiva - timedelta(days=1)
                actual.motivo_fin = RETIRO
                tramos.append(actual)
            actual = None
        elif m.tipo == REACTIVACION:
            if actual is not None:          # no debería pasar: ya pertenecía
                tramos.append(actual)
            actual = Tramo(m.curso_destino_id, m.no_lista_destino, m.fecha_efectiva,
                           None, REACTIVACION, None)
    if actual is not None:
        tramos.append(actual)
    return tramos


def tramos_en_curso(tramos: List[Tramo], curso_id) -> List[Tramo]:
    return [t for t in tramos if t.curso_id == curso_id]


def tramo_en_fecha(tramos: List[Tramo], fecha: date) -> Optional[Tramo]:
    for t in tramos:
        if t.contiene(fecha):
            return t
    return None


def tramo_vigente(tramos: List[Tramo]) -> Optional[Tramo]:
    for t in reversed(tramos):
        if t.vigente:
            return t
    return None


def intervalos_sin_permanencia(tramos: List[Tramo]):
    """Huecos ENTRE tramos (de un retiro a una reactivación): no aplican.

    El final tras el último retiro ya lo cubre `fecha_retiro`.
    """
    huecos = []
    for previo, siguiente in zip(tramos, tramos[1:]):
        if previo.hasta is None or siguiente.desde is None:
            continue
        ini = previo.hasta + timedelta(days=1)
        fin = siguiente.desde - timedelta(days=1)
        if ini <= fin:
            huecos.append((ini, fin))
    return huecos


# ── Consultas ────────────────────────────────────────────────────────────

def _models():
    import models as M
    return M


def movimientos_por_estudiante(db, colegio_id, ano_escolar_id, estudiante_ids=None) -> Dict[int, list]:
    M = _models()
    q = db.query(M.MovimientoEstudiante).filter(
        M.MovimientoEstudiante.colegio_id == colegio_id,
        M.MovimientoEstudiante.ano_escolar_id == ano_escolar_id)
    if estudiante_ids is not None:
        ids = list(estudiante_ids)
        if not ids:
            return {}
        q = q.filter(M.MovimientoEstudiante.estudiante_id.in_(ids))
    out: Dict[int, list] = {}
    for m in q.order_by(M.MovimientoEstudiante.secuencia).all():
        out.setdefault(m.estudiante_id, []).append(m)
    return out


def tramos_de(db, estudiante, ano_escolar_id) -> List[Tramo]:
    if ano_escolar_id is None or getattr(estudiante, 'colegio_id', None) is None:
        return construir_tramos(estudiante, [])
    movs = movimientos_por_estudiante(
        db, estudiante.colegio_id, ano_escolar_id, [estudiante.id]).get(estudiante.id, [])
    return construir_tramos(estudiante, movs)


def ano_del_curso(db, curso) -> Optional[int]:
    return getattr(curso, 'ano_escolar_id', None)


def _es_retirado(est) -> bool:
    return (not getattr(est, 'activo', True)
            and (getattr(est, 'condicion', None) or '').strip().lower() == 'retirado')


@dataclass
class Miembro:
    """Un estudiante que tuvo al menos un tramo en el curso durante su año."""
    estudiante: object
    tramos: List[Tramo]            # todos los suyos en el año
    en_curso: List[Tramo]          # solo los de ESTE curso

    @property
    def no_lista(self) -> Optional[int]:
        # El número que tuvo EN ESTE curso (el último tramo, si volvió).
        return self.en_curso[-1].no_lista if self.en_curso else None

    @property
    def ventanas(self):
        return [(t.desde, t.hasta) for t in self.en_curso]

    @property
    def salio(self) -> bool:
        """Ya no pertenece a este curso (trasladado o retirado)."""
        return not any(t.vigente for t in self.en_curso)

    @property
    def ultimo(self) -> Tramo:
        return self.en_curso[-1]

    @property
    def primero(self) -> Tramo:
        return self.en_curso[0]

    def aplica(self, fecha: date) -> bool:
        return any(t.contiene(fecha) for t in self.en_curso)

    def tramo_en(self, fecha: date) -> Optional[Tramo]:
        return tramo_en_fecha(self.en_curso, fecha)


def miembros_curso(db, curso, colegio_id) -> List[Miembro]:
    """Quienes pertenecieron al curso en su año, ordenados por su número en él.

    · los que hoy tienen la ficha en el curso y están activos (como siempre);
    · los RETIRADOS del curso (su ficha conserva curso y número);
    · los que salieron por traslado y los que entraron, según sus movimientos.

    Un egresado u otra ficha inactiva que no esté retirada queda como antes
    (fuera): esto no cambia nada de quien no tiene retiro ni movimientos.
    """
    M = _models()
    ano_id = ano_del_curso(db, curso)
    actuales = db.query(M.Estudiante).filter(
        M.Estudiante.colegio_id == colegio_id,
        M.Estudiante.curso_id == curso.id).all()
    candidatos = {e.id: e for e in actuales if e.activo or _es_retirado(e)}

    if ano_id is not None:
        q = db.query(M.MovimientoEstudiante.estudiante_id).filter(
            M.MovimientoEstudiante.colegio_id == colegio_id,
            M.MovimientoEstudiante.ano_escolar_id == ano_id,
            (M.MovimientoEstudiante.curso_origen_id == curso.id)
            | (M.MovimientoEstudiante.curso_destino_id == curso.id))
        faltan = {fila[0] for fila in q.distinct().all()} - set(candidatos)
        if faltan:
            for e in db.query(M.Estudiante).filter(
                    M.Estudiante.colegio_id == colegio_id,
                    M.Estudiante.id.in_(list(faltan))).all():
                candidatos[e.id] = e

    movs = (movimientos_por_estudiante(db, colegio_id, ano_id, list(candidatos))
            if ano_id is not None else {})
    miembros = []
    for est in candidatos.values():
        tramos = construir_tramos(est, movs.get(est.id, []))
        propios = tramos_en_curso(tramos, curso.id)
        if propios:
            miembros.append(Miembro(est, tramos, propios))
    miembros.sort(key=lambda m: (m.no_lista is None, m.no_lista or 0,
                                 (m.estudiante.apellido or '').lower(),
                                 (m.estudiante.nombre or '').lower(), m.estudiante.id))
    return miembros


def numeros_ocupados(db, curso_id, colegio_id) -> Dict[int, int]:
    """`{número: estudiante_id}` ocupados o reservados en el curso.

    Cuenta las fichas del curso EN CUALQUIER ESTADO (activas, retiradas,
    egresadas), las reservas y los números de origen/destino de los
    movimientos. Un número de quien se fue sigue siendo suyo durante el año.
    """
    M = _models()
    ocupados: Dict[int, int] = {}
    for e in db.query(M.Estudiante).filter(
            M.Estudiante.colegio_id == colegio_id,
            M.Estudiante.curso_id == curso_id,
            M.Estudiante.no_lista.isnot(None)).all():
        ocupados.setdefault(int(e.no_lista), e.id)
    for r in db.query(M.ReservaNumeroLista).filter(
            M.ReservaNumeroLista.colegio_id == colegio_id,
            M.ReservaNumeroLista.curso_id == curso_id).all():
        ocupados.setdefault(int(r.no_lista), r.estudiante_id)
    for m in db.query(M.MovimientoEstudiante).filter(
            M.MovimientoEstudiante.colegio_id == colegio_id,
            (M.MovimientoEstudiante.curso_origen_id == curso_id)
            | (M.MovimientoEstudiante.curso_destino_id == curso_id)).all():
        if m.curso_origen_id == curso_id and m.no_lista_origen is not None:
            ocupados.setdefault(int(m.no_lista_origen), m.estudiante_id)
        if m.curso_destino_id == curso_id and m.no_lista_destino is not None:
            ocupados.setdefault(int(m.no_lista_destino), m.estudiante_id)
    return ocupados


def numero_propuesto(ocupados: Dict[int, int], estudiante_id=None) -> int:
    """El suyo si ya tenía uno reservado en el curso; si no, el siguiente al
    mayor ocupado o reservado. No renumera a nadie."""
    if estudiante_id is not None:
        propios = sorted(n for n, eid in ocupados.items() if eid == estudiante_id)
        if propios:
            return propios[-1]
    return (max(ocupados) + 1) if ocupados else 1


def numero_libre_para(ocupados: Dict[int, int], numero: int, estudiante_id) -> bool:
    duenio = ocupados.get(int(numero))
    return duenio is None or duenio == estudiante_id


# ── Avisos ───────────────────────────────────────────────────────────────

def fmt_fecha(d: Optional[date]) -> str:
    return d.strftime('%d/%m/%Y') if d else ''


def aviso_salida(tramo: Tramo, nombre_curso) -> Optional[str]:
    """«Trasladado a …» o «Retirado desde …» para el tramo que se cerró."""
    if tramo.motivo_fin == TRASLADO:
        destino = nombre_curso(tramo.curso_destino_id) if tramo.curso_destino_id else ''
        return 'Trasladado a %s desde %s' % (destino, fmt_fecha(tramo.fecha_salida))
    if tramo.motivo_fin == RETIRO:
        return 'Retirado desde %s' % fmt_fecha(tramo.fecha_salida)
    return None


def aviso_entrada(tramo: Tramo, nombre_curso) -> Optional[str]:
    """«Incorporado desde …» para el tramo que empezó a mitad de año."""
    if tramo.motivo_inicio == TRASLADO:
        origen = nombre_curso(tramo.curso_origen_id) if tramo.curso_origen_id else ''
        return 'Incorporado desde %s (trasladado desde %s)' % (fmt_fecha(tramo.desde), origen)
    if tramo.motivo_inicio == REACTIVACION:
        return 'Reincorporado desde %s' % fmt_fecha(tramo.desde)
    return None


def avisos_miembro(miembro: Miembro, nombre_curso) -> List[str]:
    out = []
    for t in miembro.en_curso:
        a = aviso_entrada(t, nombre_curso)
        if a:
            out.append(a)
        a = aviso_salida(t, nombre_curso)
        if a:
            out.append(a)
    return out
