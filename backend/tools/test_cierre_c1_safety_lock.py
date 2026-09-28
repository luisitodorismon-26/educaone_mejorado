# -*- coding: utf-8 -*-
"""CIERRE DE ANO C1 — safety lock, ya en su contrato de PRODUCCION.

QUE CAMBIO EN EL RELEASE
========================
C1 afirmaba que los CUATRO writers devolvian 409. Era cierto y era lo
correcto mientras el flujo se reconstruia: no habia nada que habilitar.
Ahora si lo hay, y los cuatro dejaron de ser lo mismo:

  CANONICOS — `/api/ano-escolar/{id}/cerrar` y `/api/cierre-ano/promover`.
  Son el flujo que CORE-1 y CORE-2 construyeron. Estan HABILITADOS. Lo que
  se prueba de ellos aqui ya no es que rechacen, sino que el candado dejo de
  interponerse, que siguen sin escribir cuando rechazan por una razon de
  negocio, y que el interruptor de emergencia los vuelve a cerrar entero.

  LEGACY — `/api/promocion/ejecutar` y `/api/ano-escolar/promover`. Mueven
  estudiantes sin mirar su situacion academica ni el ano de destino. Siguen
  devolviendo 409, antes de leer el cuerpo y sin tocar la base, y ahora de
  forma PERMANENTE: su guarda no consulta ninguna bandera, asi que habilitar
  el Cierre no puede resucitarlos.

No se quito ni una comprobacion. Las que afirmaban el bloqueo de los
canonicos se convirtieron en su contrario —que ya NO se bloquean— y se
anadio el candado de emergencia y la prueba de mutacion del legacy.

Que se prueba aqui:

  · que los dos LEGACY rechazan con 409 y contrato estable;
  · que rechazan SIN ESCRIBIR: cero INSERT, cero UPDATE, cero DELETE;
  · que rechazan ANTES de leer el cuerpo de la peticion;
  · que siguen rechazando aunque se ponga `PROMOCION_LEGACY_BLOQUEADA` en
    False: la politica no depende de una constante que alguien pueda voltear;
  · que los dos CANONICOS ya NO devuelven el 409 del candado;
  · que el interruptor de emergencia sigue funcionando;
  · que activar un ano cerrado se rechaza ANTES de desactivar los demas;
  · que las lecturas siguen funcionando;
  · y que los guards estan VIVOS: si se apagan, los tests que afirman el
    bloqueo fallan. Un guard que no se puede romper no se esta probando.

Base temporal aislada. Nunca produccion.
"""
import asyncio
import io
import os
import sys

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(BK, "tools"))

from test_utils import aislar_base_de_datos  # noqa: E402

TMP = aislar_base_de_datos('c1_safety_lock')

from sqlalchemy import event  # noqa: E402
from database import engine, SessionLocal  # noqa: E402
from test_utils import verificar_engine_aislado  # noqa: E402

verificar_engine_aislado(engine, TMP)

import models as M  # noqa: E402
import app as APP  # noqa: E402

M.Base.metadata.create_all(bind=engine)

ORD = {1: '1ro', 2: '2do', 3: '3ro', 4: '4to', 5: '5to', 6: '6to'}

PASARON = []
FALLARON = []


def check(nombre, cond, detalle=''):
    if cond:
        PASARON.append(nombre)
        print("  PASA   %-52s %s" % (nombre, detalle))
    else:
        FALLARON.append(nombre)
        print("  FALLA  %-52s %s" % (nombre, detalle))


# ───────────────────────── infraestructura ─────────────────────────

class Req:
    """Request minimo. `leido` delata si el endpoint llego a mirar el body."""

    def __init__(self, body=None, path='/api/test'):
        self._b = body if body is not None else {}
        self.leido = False
        self.client = type('C', (), {'host': '127.0.0.1'})()
        self.headers = {}
        self.url = type('U', (), {'path': path})()
        self.method = 'POST'

    async def json(self):
        self.leido = True
        return self._b


class ReqQueExplota(Req):
    """Si el guard rechaza antes del body, este json() nunca se ejecuta."""

    async def json(self):
        self.leido = True
        raise AssertionError('el endpoint leyo el cuerpo antes de rechazar')


def usuario_real(db, col):
    """Un Usuario persistido de verdad.

    `log_auditoria` inserta `usuario_id` con FK: un stub con id=1 inventado
    revienta el flush del camino legitimo y contaminaria el resultado.
    """
    u = M.Usuario(colegio_id=col.id, username='dir-%s' % col.codigo,
                  password_hash='x', nombre='Dir', role='direccion',
                  activo=True, must_change_password=False, token_version=0)
    db.add(u)
    db.commit()
    return u


class Vigilante:
    """Cuenta escrituras reales a nivel de sesion SQLAlchemy.

    `before_flush` ve lo que la sesion esta a punto de mandar; con esto un
    `db.commit()` que no tenga nada pendiente no cuenta, y cualquier
    add/modificacion/borrado si.
    """

    def __init__(self, db):
        self.db = db
        self.nuevos = 0
        self.sucios = 0
        self.borrados = 0

    def _on_flush(self, session, flush_context, instances):
        self.nuevos += len(session.new)
        self.sucios += len(session.dirty)
        self.borrados += len(session.deleted)

    def __enter__(self):
        event.listen(self.db, 'before_flush', self._on_flush)
        return self

    def __exit__(self, *a):
        event.remove(self.db, 'before_flush', self._on_flush)

    @property
    def total(self):
        return self.nuevos + self.sucios + self.borrados

    def __repr__(self):
        return 'new=%d dirty=%d del=%d' % (self.nuevos, self.sucios, self.borrados)


def montar(db, nombre, codigo):
    """Colegio MIXTO: Secundaria orden 1-6, Primaria orden 7-12."""
    col = M.Colegio(nombre=nombre, codigo=codigo, activo=True)
    db.add(col)
    db.flush()
    grados = {}
    for n in range(1, 7):
        g = M.Grado(colegio_id=col.id, nombre='%s Secundaria' % ORD[n],
                    nivel='secundaria', orden=n, activo=True)
        db.add(g)
        grados[('sec', n)] = g
    for n in range(1, 7):
        g = M.Grado(colegio_id=col.id, nombre='%s Primaria' % ORD[n],
                    nivel='primaria', orden=n + 6, activo=True)
        db.add(g)
        grados[('pri', n)] = g
    db.flush()
    viejo = M.AnoEscolar(colegio_id=col.id, nombre='2025-2026',
                         activo=False, cerrado=True)
    nuevo = M.AnoEscolar(colegio_id=col.id, nombre='2026-2027',
                         activo=True, cerrado=False)
    db.add_all([viejo, nuevo])
    db.flush()
    tanda = M.Tanda(colegio_id=col.id, nombre='Matutina',
                    hora_inicio='07:30', hora_fin='12:30')
    db.add(tanda)
    db.flush()
    ests = {}
    for clave, g in grados.items():
        c = M.Curso(colegio_id=col.id, nombre='A', grado_id=g.id,
                    tanda_id=tanda.id, ano_escolar_id=viejo.id, activo=True)
        db.add(c)
        db.flush()
        e = M.Estudiante(colegio_id=col.id,
                         matricula='%s-%s%d' % (codigo, clave[0], clave[1]),
                         nombre='E', apellido='%s%d' % (clave[0], clave[1]),
                         curso_id=c.id, activo=True, condicion='Inscrito')
        db.add(e)
        db.flush()
        ests[clave] = e
    db.commit()
    return col, viejo, nuevo, grados, ests


def foto(db, col):
    """Estado observable del colegio: si el guard funciona, no cambia."""
    anos = db.query(M.AnoEscolar).filter_by(colegio_id=col.id).all()
    ests = db.query(M.Estudiante).filter_by(colegio_id=col.id).all()
    return {
        'anos': sorted((a.id, a.activo, a.cerrado) for a in anos),
        'ests': sorted((e.id, e.curso_id, e.activo, e.condicion) for e in ests),
        'hist': db.query(M.HistorialAcademico).count(),
        'cursos': sorted((c.id, c.ano_escolar_id, c.activo)
                         for c in db.query(M.Curso).filter_by(colegio_id=col.id)),
    }


def cuerpo(resp):
    """Extrae el JSON de una JSONResponse sin depender de su serializador."""
    import json
    return json.loads(bytes(resp.body).decode('utf-8'))


MENSAJE_ESPERADO = ('El Cierre de Año está temporalmente bloqueado mientras se '
                    'completa el flujo académico seguro.')


db = SessionLocal()

print("=" * 86)
print("BLOQUE 1 — legacy bloqueado, canonico habilitado")
print("=" * 86)

col, viejo, nuevo, grados, ests = montar(db, 'Lock', 'LCK1')
usr = usuario_real(db, col)
antes = foto(db, col)

# ── C1-1 · RELEASE: el canonico ya no choca contra el candado ──────
#
# `viejo` ya esta cerrado en el banco de pruebas, asi que el cierre canonico
# lo rechaza por ESO. Lo que se comprueba es de QUE se le rechaza: si
# siguiera saliendo `CIERRE_ANO_TEMPORALMENTE_BLOQUEADO`, el candado seguiria
# interponiendose y el Cierre no estaria habilitado.
with Vigilante(db) as v:
    r = asyncio.run(APP.cerrar_ano_escolar(
        id=viejo.id, request=Req({}), db=db, current_user=usr))
c = cuerpo(r)
check('C1-1  cerrar_ano_escolar YA NO devuelve el 409 del candado',
      c.get('error') != 'CIERRE_ANO_TEMPORALMENTE_BLOQUEADO',
      'status=%s error=%s' % (r.status_code, c.get('error')))
check('C1-1b y llega al camino canonico, que lo rechaza por su estado real',
      c.get('error') == 'ANO_ESCOLAR_YA_CERRADO', str(c.get('error')))
check('C1-2  y aun rechazando no escribe nada',
      v.total == 0 and foto(db, col) == antes, repr(v))

# ── C1-3 · RELEASE: lo mismo para la promocion canonica ────────────
with Vigilante(db) as v:
    r = asyncio.run(APP.ejecutar_promocion_cierre_ano(
        request=Req({'nuevo_ano_id': nuevo.id}), db=db, current_user=usr))
c = cuerpo(r)
check('C1-3  cierre-ano/promover YA NO devuelve el 409 del candado',
      c.get('error') != 'CIERRE_ANO_TEMPORALMENTE_BLOQUEADO',
      'status=%s error=%s' % (r.status_code, c.get('error')))
check('C1-3b y llega al writer canonico, que exige contexto explicito',
      c.get('error') == 'CIERRE_TRANSICION_INCOMPLETA', str(c.get('error')))
check('C1-4  y aun rechazando no mueve a nadie',
      v.total == 0 and foto(db, col) == antes, repr(v))

# ── C1-3c · El interruptor de emergencia sigue existiendo ──────────
#
# Poner la bandera en True vuelve a cerrar el Cierre entero sin tocar nada
# mas. Es el unico camino de vuelta, y tiene que seguir funcionando.
_antes_flag = APP.CIERRE_ANO_BLOQUEADO
APP.CIERRE_ANO_BLOQUEADO = True
try:
    with Vigilante(db) as v:
        r_em = asyncio.run(APP.cerrar_ano_escolar(
            id=nuevo.id, request=Req({}), db=db, current_user=usr))
        r_em2 = asyncio.run(APP.ejecutar_promocion_cierre_ano(
            request=Req({'nuevo_ano_id': nuevo.id}), db=db, current_user=usr))
    c_em, c_em2 = cuerpo(r_em), cuerpo(r_em2)
    check('C1-3c el interruptor de emergencia vuelve a cerrar el Cierre',
          r_em.status_code == 409
          and c_em['error'] == 'CIERRE_ANO_TEMPORALMENTE_BLOQUEADO'
          and r_em2.status_code == 409
          and c_em2['error'] == 'CIERRE_ANO_TEMPORALMENTE_BLOQUEADO',
          '%s / %s' % (c_em.get('error'), c_em2.get('error')))
    check('C1-3d y cerrado de emergencia tampoco escribe',
          v.total == 0 and foto(db, col) == antes, repr(v))
finally:
    APP.CIERRE_ANO_BLOQUEADO = _antes_flag
check('C1-3e la bandera queda como estaba: el Cierre habilitado',
      APP.CIERRE_ANO_BLOQUEADO is False, str(APP.CIERRE_ANO_BLOQUEADO))

# ── C1-5 ──────────────────────────────────────────────────────────
ids = [e.id for e in ests.values()]
with Vigilante(db) as v:
    r = asyncio.run(APP.ejecutar_promocion(
        request=Req({'estudiantes': ids}), db=db, current_user=usr))
c = cuerpo(r)
check('C1-5  promocion/ejecutar -> 409 con codigo legacy propio',
      r.status_code == 409 and c['error'] == 'PROMOCION_LEGACY_BLOQUEADA',
      'status=%s error=%s' % (r.status_code, c.get('error')))
check('C1-6  promocion/ejecutar no mueve a nadie',
      v.total == 0 and foto(db, col) == antes, repr(v))

# ── C1-7 ──────────────────────────────────────────────────────────
with Vigilante(db) as v:
    r = asyncio.run(APP.promover_estudiantes(
        request=Req({}), db=db, current_user=usr))
c = cuerpo(r)
check('C1-7  ano-escolar/promover -> 409 (ya no dice "promovidos")',
      r.status_code == 409 and c['error'] == 'PROMOCION_LEGACY_BLOQUEADA'
      and 'promovidos' not in str(c).lower(),
      'status=%s error=%s' % (r.status_code, c.get('error')))
check('C1-8  ano-escolar/promover no escribe nada',
      v.total == 0 and foto(db, col) == antes, repr(v))

print()
print("=" * 86)
print("BLOQUE 2 — el rechazo ocurre ANTES de leer el cuerpo")
print("=" * 86)

# Si el guard estuviera despues del `await request.json()`, este json()
# levantaria AssertionError y el test fallaria con excepcion, no con 409.
#
# RELEASE · Esto vale ahora solo para los LEGACY. Los canonicos estan
# habilitados y leen el cuerpo a proposito: ahi viven `ano_origen_id` y
# `ano_destino_id`, que es el contexto explicito que C2 les exigio. Lo que
# de ellos sigue importando —que no escriban cuando rechazan— se comprueba
# en C1-2 y C1-4.
for nombre, fn, kw in [
    ('ejecutar_promocion', APP.ejecutar_promocion, {}),
    ('promover_estudiantes', APP.promover_estudiantes, {}),
]:
    req = ReqQueExplota(path='/api/x')
    try:
        r = asyncio.run(fn(request=req, db=db, current_user=usr, **kw))
        ok = r.status_code == 409 and not req.leido
        det = 'body_leido=%s' % req.leido
    except AssertionError as ex:
        ok, det = False, str(ex)
    check('C1-9  %s rechaza sin leer el body' % nombre, ok, det)

# ── C1-9c · MUTACION: la politica legacy no depende de una constante ──
#
# Esta es la comprobacion que impide reactivarlos por accidente. Se pone
# `PROMOCION_LEGACY_BLOQUEADA` en False —lo que haria alguien que creyera
# que es el interruptor— y los dos endpoints tienen que seguir rechazando,
# porque sus guardas no la consultan.
_antes_legacy = APP.PROMOCION_LEGACY_BLOQUEADA
APP.PROMOCION_LEGACY_BLOQUEADA = False
try:
    with Vigilante(db) as v:
        r_l1 = asyncio.run(APP.ejecutar_promocion(
            request=Req({'estudiantes': [e.id for e in ests.values()]}),
            db=db, current_user=usr))
        r_l2 = asyncio.run(APP.promover_estudiantes(
            request=Req({}), db=db, current_user=usr))
    c_l1, c_l2 = cuerpo(r_l1), cuerpo(r_l2)
    check('C1-9c poner la constante en False NO reactiva promocion/ejecutar',
          r_l1.status_code == 409
          and c_l1['error'] == 'PROMOCION_LEGACY_BLOQUEADA',
          'status=%s error=%s' % (r_l1.status_code, c_l1.get('error')))
    check('C1-9d ni ano-escolar/promover',
          r_l2.status_code == 409
          and c_l2['error'] == 'PROMOCION_LEGACY_BLOQUEADA',
          'status=%s error=%s' % (r_l2.status_code, c_l2.get('error')))
    check('C1-9e y con la constante apagada tampoco escriben',
          v.total == 0 and foto(db, col) == antes, repr(v))
finally:
    APP.PROMOCION_LEGACY_BLOQUEADA = _antes_legacy

# Y el codigo lo dice. Por AST y no por texto: `ERROR_PROMOCION_LEGACY_
# BLOQUEADA` —el codigo de error que SI se usa— contiene como subcadena el
# nombre de la constante, y una comparacion literal lo confundiria con una
# lectura de la bandera.
import ast as _ast  # noqa: E402
import inspect as _insp  # noqa: E402
import textwrap as _tw  # noqa: E402

BANDERAS = {'PROMOCION_LEGACY_BLOQUEADA', 'CIERRE_ANO_BLOQUEADO'}


def _lee_bandera(fn):
    arbol = _ast.parse(_tw.dedent(_insp.getsource(fn)))
    return {n.id for n in _ast.walk(arbol)
            if isinstance(n, _ast.Name) and n.id in BANDERAS}


def _tiene_condicion(fn):
    arbol = _ast.parse(_tw.dedent(_insp.getsource(fn)))
    cuerpo = arbol.body[0].body
    cuerpo = [x for x in cuerpo
              if not (isinstance(x, _ast.Expr)
                      and isinstance(x.value, _ast.Constant))]
    return not isinstance(cuerpo[0], _ast.Return)


check('C1-9f la guarda legacy no LEE ninguna bandera',
      _lee_bandera(APP._bloqueo_promocion_legacy) == set(),
      str(_lee_bandera(APP._bloqueo_promocion_legacy)))
for _fn in (APP.ejecutar_promocion, APP.promover_estudiantes):
    check('C1-9g %s no LEE ninguna bandera' % _fn.__name__,
          _lee_bandera(_fn) == set(), str(_lee_bandera(_fn)))
    check('C1-9h %s rechaza en su PRIMERA sentencia, sin condicion'
          % _fn.__name__,
          not _tiene_condicion(_fn)
          and 'return _bloqueo_promocion_legacy()' in _insp.getsource(_fn), '')

print()
print("=" * 86)
print("BLOQUE 3 — activar un ano cerrado")
print("=" * 86)

col2, viejo2, nuevo2, grados2, ests2 = montar(db, 'Activar', 'ACT1')
usr2 = usuario_real(db, col2)
antes2 = foto(db, col2)

with Vigilante(db) as v:
    r = asyncio.run(APP.activar_ano_escolar(
        id=viejo2.id, request=Req({}), db=db, current_user=usr2))
c = cuerpo(r)
check('C1-10 activar ano CERRADO -> 409 ANO_ESCOLAR_CERRADO_NO_ACTIVABLE',
      r.status_code == 409 and c['error'] == 'ANO_ESCOLAR_CERRADO_NO_ACTIVABLE',
      'status=%s error=%s' % (r.status_code, c.get('error')))

db.expire_all()
ahora2 = foto(db, col2)
check('C1-11 el rechazo NO desactivo los demas anos',
      ahora2 == antes2 and any(a[1] for a in ahora2['anos']),
      'anos=%s' % (ahora2['anos'],))

nuevo2b = db.get(M.AnoEscolar, nuevo2.id)
check('C1-12 el ano en curso sigue activo tras el rechazo',
      nuevo2b.activo is True and nuevo2b.cerrado is False,
      'activo=%s cerrado=%s' % (nuevo2b.activo, nuevo2b.cerrado))

# El camino legitimo sigue abierto: un ano NO cerrado se activa igual que antes.
r = asyncio.run(APP.activar_ano_escolar(
    id=nuevo2.id, request=Req({}), db=db, current_user=usr2))
db.expire_all()
nuevo2c = db.get(M.AnoEscolar, nuevo2.id)
viejo2c = db.get(M.AnoEscolar, viejo2.id)
check('C1-13 activar un ano ABIERTO sigue funcionando',
      not hasattr(r, 'status_code') and nuevo2c.activo is True,
      'resp=%s activo=%s' % (type(r).__name__, nuevo2c.activo))
check('C1-13b nunca coexisten cerrado=True y activo=True',
      not (viejo2c.cerrado and viejo2c.activo),
      'viejo: cerrado=%s activo=%s' % (viejo2c.cerrado, viejo2c.activo))

print()
print("=" * 86)
print("BLOQUE 4 — lo que NO se bloqueo")
print("=" * 86)

# Las lecturas de R4 son justo lo que Direccion necesita para revisar el ano.
r = asyncio.run(APP.get_estudiantes_promocion(
    request=Req({}, path='/api/promocion/estudiantes'), ano_id=None,
    db=db, current_user=usr))
check('C1-14 GET /api/promocion/estudiantes sigue respondiendo',
      not hasattr(r, 'status_code') and 'estudiantes' in r,
      'claves=%s' % (sorted(r.keys())[:5] if isinstance(r, dict) else type(r).__name__))

r = asyncio.run(APP.get_resumen_cierre_ano(db=db, current_user=usr))
check('C1-14b GET /api/cierre-ano/resumen sigue respondiendo',
      not hasattr(r, 'status_code') and isinstance(r, dict),
      type(r).__name__)

# reabrir queda intacto a proposito: su riesgo (movimientos parciales) se
# corrige junto al nuevo writer, no aqui.
col3, viejo3, nuevo3, grados3, ests3 = montar(db, 'Reabrir', 'REA1')
r = asyncio.run(APP.reabrir_ano_escolar(
    id=viejo3.id, request=Req({}), db=db, current_user=usuario_real(db, col3)))
db.expire_all()
check('C1-15 reabrir_ano_escolar NO fue bloqueado',
      not hasattr(r, 'status_code')
      and db.get(M.AnoEscolar, viejo3.id).cerrado is False,
      'cerrado=%s' % db.get(M.AnoEscolar, viejo3.id).cerrado)

# crear_ano_escolar y clonar-cursos quedan fuera del lock por encargo.
col4 = M.Colegio(nombre='Crear', codigo='CRE1', activo=True)
db.add(col4)
db.commit()
r = asyncio.run(APP.crear_ano_escolar(
    request=Req({'nombre': '2026-2027', 'fecha_inicio': '2026-08-01',
                 'fecha_fin': '2027-06-30'}),
    db=db, current_user=usuario_real(db, col4)))
check('C1-15b crear_ano_escolar NO fue bloqueado',
      r.status_code == 201
      and db.query(M.AnoEscolar).filter_by(colegio_id=col4.id).count() == 1,
      'status=%s anos=%d' % (
          r.status_code,
          db.query(M.AnoEscolar).filter_by(colegio_id=col4.id).count()))

print()
print("=" * 86)
print("BLOQUE 5 — el lock esta vivo (mutacion)")
print("=" * 86)

# Se apaga la bandera y se comprueba que los endpoints DEJAN de devolver 409.
# Si siguieran devolviendolo, el 409 vendria de otra cosa y los tests de
# arriba no estarian probando nada.
APP.CIERRE_ANO_BLOQUEADO = False
try:
    col5, viejo5, nuevo5, grados5, ests5 = montar(db, 'Mut', 'MUT1')
    usr5 = usuario_real(db, col5)

    # CORE-1: el writer ya no acepta `nuevo_ano_id` ni deduce el origen. Hay
    # que mandarle la transicion explicita, que es justamente lo que se quiere
    # comprobar: sin la bandera el camino canonico corre y escribe.
    with Vigilante(db) as v:
        r = asyncio.run(APP.ejecutar_promocion_cierre_ano(
            request=Req({'ano_origen_id': viejo5.id,
                         'ano_destino_id': nuevo5.id}),
            db=db, current_user=usr5))
    bloqueado = hasattr(r, 'status_code') and r.status_code == 409
    # Los alumnos de esta fixture no tienen ninguna nota, asi que A2 los deja
    # EN_PROCESO y el writer —correctamente— no mueve a nadie. Lo que prueba
    # que el camino corrio es que devuelve el informe canonico, no el 409.
    corrio = (not bloqueado and isinstance(r, dict)
              and r.get('ano_origen_id') == viejo5.id
              and r.get('ano_destino_id') == nuevo5.id
              and r.get('en_proceso', 0) > 0)
    check('C1-M1 sin la bandera, cierre-ano/promover vuelve a ejecutar',
          corrio, 'respuesta=%s' % (
              {k: r[k] for k in ('ano_origen_id', 'movidos', 'en_proceso')}
              if isinstance(r, dict) else type(r).__name__))

    # Y sin los dos años explicitos se rechaza con 400, no con el 409 del lock:
    # el contrato nuevo es obligatorio incluso con la bandera apagada.
    with Vigilante(db) as v2:
        r2 = asyncio.run(APP.ejecutar_promocion_cierre_ano(
            request=Req({'nuevo_ano_id': nuevo5.id}), db=db, current_user=usr5))
    check('C1-M1b sin la transicion explicita: 400, y no escribe',
          hasattr(r2, 'status_code') and r2.status_code == 400 and v2.total == 0,
          'status=%s escrituras=%s' % (getattr(r2, 'status_code', None), repr(v2)))

    r = asyncio.run(APP.activar_ano_escolar(
        id=viejo5.id, request=Req({}), db=db, current_user=usr5))
    bloq = hasattr(r, 'status_code') and r.status_code == 409
    check('C1-M2 el guard de activar NO depende de CIERRE_ANO_BLOQUEADO',
          bloq, 'sigue rechazando un ano cerrado: %s' % bloq)
finally:
    APP.CIERRE_ANO_BLOQUEADO = True

# Y se confirma que el lock volvio a su sitio.
r = asyncio.run(APP.cerrar_ano_escolar(
    id=viejo.id, request=Req({}), db=db, current_user=usr))
check('C1-M3 la bandera quedo restaurada al terminar',
      hasattr(r, 'status_code') and r.status_code == 409,
      'status=%s' % getattr(r, 'status_code', None))

print()
print("=" * 86)
print("BLOQUE 6 — contrato textual y coherencia del frontend")
print("=" * 86)

c = cuerpo(r)
check('C1-C1 el mensaje contiene el texto acordado',
      MENSAJE_ESPERADO in c['message'],
      repr(c['message'][:60] + '...'))
check('C1-C2 la respuesta trae error + message + bloqueado',
      set(['error', 'message', 'bloqueado']).issubset(c.keys()) and c['bloqueado'] is True,
      sorted(c.keys()))

FE = os.path.join(os.path.dirname(BK), 'frontend', 'src', 'pages',
                  'cierre-ano', 'CierreAnoPage.tsx')
fe = io.open(FE, encoding='utf-8').read()
usos = fe.count('disabled={cierreBloqueado')
# RELEASE · La pantalla ya no lleva la bandera escrita a mano: la DERIVA de
# `bloqueado_por_safety_lock`, que es la misma que decide el 409. Si alguien
# volviera a cerrar el Cierre con el interruptor de emergencia, la pantalla
# se entera sola; con el literal habia que acordarse de tocar dos sitios.
check('C1-C3 el frontend DERIVA el bloqueo del backend, no lo escribe',
      'const CIERRE_BLOQUEADO = true;' not in fe
      and 'estado?.bloqueado_por_safety_lock === true' in fe, '')
check('C1-C4 y los dos botones siguen atados a esa bandera derivada',
      usos == 2, 'botones deshabilitados por la bandera=%d' % usos)
check('C1-C5 el aviso «mientras se reconstruye» desaparecio',
      'reconstruye' not in fe
      and 'temporalmente deshabilitado' not in fe.lower(), '')
check('C1-C6 pero sigue habiendo aviso si el candado vuelve a cerrarse',
      'Cierre de Año deshabilitado' in fe, '')

print()
print("=" * 86)
print("BLOQUE 7 — RBAC: el lock no sustituye al control de acceso")
print("=" * 86)

# El riesgo que se descarta aqui: que C1 haya convertido el guard en un
# atajo que responde 409 a cualquiera. Si el guard corriese ANTES de
# RolesRequired, un profesor —o alguien sin token— recibiria el contrato de
# C1 en vez del rechazo de autorizacion, y el dia que se levante el lock
# entraria al writer. El guard vive DENTRO de la funcion, o sea despues de
# las dependencias, y eso es lo que se comprueba.

from fastapi.testclient import TestClient      # noqa: E402
from auth import create_token                  # noqa: E402

col6, viejo6, nuevo6, grados6, ests6 = montar(db, 'RBAC', 'RBA1')
dir6 = usuario_real(db, col6)
prof6 = M.Usuario(colegio_id=col6.id, username='prof-RBA1', password_hash='x',
                  nombre='Prof', role='profesor', activo=True,
                  must_change_password=False, token_version=0)
db.add(prof6)
db.commit()

TOK_DIR = create_token(dir6)
TOK_PROF = create_token(prof6)

ENDPOINTS = [
    ('POST /api/ano-escolar/{id}/cerrar', 'post',
     '/api/ano-escolar/%d/cerrar' % viejo6.id, {},
     'CIERRE_ANO_TEMPORALMENTE_BLOQUEADO'),
    ('POST /api/cierre-ano/promover', 'post',
     '/api/cierre-ano/promover', {'nuevo_ano_id': nuevo6.id},
     'CIERRE_ANO_TEMPORALMENTE_BLOQUEADO'),
    ('POST /api/promocion/ejecutar', 'post',
     '/api/promocion/ejecutar', {'estudiantes': [e.id for e in ests6.values()]},
     'PROMOCION_LEGACY_BLOQUEADA'),
    ('POST /api/ano-escolar/promover', 'post',
     '/api/ano-escolar/promover', {},
     'PROMOCION_LEGACY_BLOQUEADA'),
]

with TestClient(APP.app) as cli:
    for etiqueta, metodo, ruta, body, codigo_esperado in ENDPOINTS:
        antes6 = foto(db, col6)

        # ── DIRECCION: pasa RBAC y choca con el lock ──────────────
        r = cli.post(ruta, json=body,
                     headers={'Authorization': 'Bearer %s' % TOK_DIR})
        ok = r.status_code == 409 and r.json().get('error') == codigo_esperado
        check('C1-R1 %s · direccion -> 409 %s' % (etiqueta, codigo_esperado),
              ok, 'status=%s error=%s' % (r.status_code, r.json().get('error')))

        # ── PROFESOR: lo para RolesRequired, NO el lock ───────────
        r = cli.post(ruta, json=body,
                     headers={'Authorization': 'Bearer %s' % TOK_PROF})
        cuerpo_prof = r.text
        check('C1-R2 %s · profesor -> 403 por autorizacion' % etiqueta,
              r.status_code == 403,
              'status=%s' % r.status_code)
        check('C1-R3 %s · profesor NO recibe el contrato de C1' % etiqueta,
              codigo_esperado not in cuerpo_prof
              and 'bloqueado' not in cuerpo_prof,
              repr(cuerpo_prof[:70]))

        # ── SIN TOKEN: rechazo de autenticacion de siempre ────────
        r = cli.post(ruta, json=body)
        cuerpo_anon = r.text
        check('C1-R4 %s · sin token -> 401/403, no 409' % etiqueta,
              r.status_code in (401, 403) and r.status_code != 409,
              'status=%s' % r.status_code)
        check('C1-R5 %s · sin token NO recibe el contrato de C1' % etiqueta,
              codigo_esperado not in cuerpo_anon
              and 'bloqueado' not in cuerpo_anon,
              repr(cuerpo_anon[:70]))

        # Ninguna de las tres llamadas pudo escribir.
        db.expire_all()
        check('C1-R6 %s · ningun rol movio nada' % etiqueta,
              foto(db, col6) == antes6, '')

print()
print("=" * 86)
print("BLOQUE 8 — el 409 no revela nada sobre el recurso pedido")
print("=" * 86)

# Con el lock puesto, `cerrar` rechaza antes de resolver el año. Por tanto la
# respuesta a un ID propio, a uno de OTRO colegio y a uno inexistente tiene
# que ser identica: si difiriese, el 409 se convertiria en un oraculo de
# existencia cross-tenant. No se apaga el lock para comprobarlo.
col7, viejo7, nuevo7, grados7, ests7 = montar(db, 'Ajeno', 'AJE1')
antes7 = foto(db, col7)

with TestClient(APP.app) as cli:
    respuestas = {}
    for etiqueta_id, ident in (('propio', viejo6.id),
                               ('de otro colegio', viejo7.id),
                               ('inexistente', 987654)):
        r = cli.post('/api/ano-escolar/%d/cerrar' % ident, json={},
                     headers={'Authorization': 'Bearer %s' % TOK_DIR})
        respuestas[etiqueta_id] = (r.status_code, r.text)

distintas = set(respuestas.values())
check('C1-T1 el 409 es indistinguible sea cual sea el ID',
      len(distintas) == 1,
      ' | '.join('%s=%s' % (k, v[0]) for k, v in respuestas.items()))

for campo in ('nombre', '2025-2026', '2026-2027', 'AJE1', 'estudiante',
              'curso', 'anoescolar'):
    check('C1-T2 la respuesta no filtra %r' % campo,
          all(campo not in texto for _, texto in respuestas.values()),
          '')

db.expire_all()
check('C1-T3 el colegio ajeno quedo intacto', foto(db, col7) == antes7, '')

print()
print("=" * 86)
print("RESULTADO: %d PASARON / %d FALLARON" % (len(PASARON), len(FALLARON)))
print("=" * 86)
for f in FALLARON:
    print("  FALLA:", f)

db.close()
sys.exit(1 if FALLARON else 0)
