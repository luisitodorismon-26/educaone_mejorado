# -*- coding: utf-8 -*-
"""CIERRE DE ANO C1 — safety lock / fail-closed de los writers antiguos.

Que se prueba aqui:

  · que los cuatro POST rechazan con 409 y contrato estable;
  · que rechazan SIN ESCRIBIR: cero INSERT, cero UPDATE, cero DELETE;
  · que rechazan ANTES de leer el cuerpo de la peticion;
  · que activar un ano cerrado se rechaza ANTES de desactivar los demas;
  · que las lecturas siguen funcionando;
  · y que el lock esta VIVO: si se apaga la bandera, los tests que afirman
    el bloqueo fallan. Un guard que no se puede romper no se esta probando.

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
print("BLOQUE 1 — los cuatro writers rechazan con 409 y sin tocar la base")
print("=" * 86)

col, viejo, nuevo, grados, ests = montar(db, 'Lock', 'LCK1')
usr = usuario_real(db, col)
antes = foto(db, col)

# ── C1-1 ──────────────────────────────────────────────────────────
with Vigilante(db) as v:
    r = asyncio.run(APP.cerrar_ano_escolar(
        id=viejo.id, request=Req({}), db=db, current_user=usr))
c = cuerpo(r)
check('C1-1  cerrar_ano_escolar -> 409 CIERRE_ANO_TEMPORALMENTE_BLOQUEADO',
      r.status_code == 409 and c['error'] == 'CIERRE_ANO_TEMPORALMENTE_BLOQUEADO',
      'status=%s error=%s' % (r.status_code, c.get('error')))
check('C1-2  cerrar_ano_escolar no escribe nada',
      v.total == 0 and foto(db, col) == antes, repr(v))

# ── C1-3 ──────────────────────────────────────────────────────────
with Vigilante(db) as v:
    r = asyncio.run(APP.ejecutar_promocion_cierre_ano(
        request=Req({'nuevo_ano_id': nuevo.id}), db=db, current_user=usr))
c = cuerpo(r)
check('C1-3  cierre-ano/promover -> 409 con el mismo contrato',
      r.status_code == 409 and c['error'] == 'CIERRE_ANO_TEMPORALMENTE_BLOQUEADO',
      'status=%s error=%s' % (r.status_code, c.get('error')))
check('C1-4  cierre-ano/promover no mueve a nadie',
      v.total == 0 and foto(db, col) == antes, repr(v))

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
for nombre, fn, kw in [
    ('cerrar_ano_escolar', APP.cerrar_ano_escolar, {'id': viejo.id}),
    ('ejecutar_promocion_cierre_ano', APP.ejecutar_promocion_cierre_ano, {}),
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

    with Vigilante(db) as v:
        r = asyncio.run(APP.ejecutar_promocion_cierre_ano(
            request=Req({'nuevo_ano_id': nuevo5.id}), db=db, current_user=usr5))
    bloqueado = hasattr(r, 'status_code') and r.status_code == 409
    check('C1-M1 sin la bandera, cierre-ano/promover vuelve a ejecutar',
          not bloqueado and v.total > 0,
          'escrituras=%s' % repr(v))

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
usos = fe.count('disabled={CIERRE_BLOQUEADO')
check('C1-C3 el frontend declara la bandera y deshabilita ambos botones',
      'const CIERRE_BLOQUEADO = true;' in fe and usos == 2,
      'botones deshabilitados por la bandera=%d' % usos)
check('C1-C4 el frontend muestra el aviso informativo',
      'Cierre de Año temporalmente deshabilitado' in fe,
      '')

print()
print("=" * 86)
print("RESULTADO: %d PASARON / %d FALLARON" % (len(PASARON), len(FALLARON)))
print("=" * 86)
for f in FALLARON:
    print("  FALLA:", f)

db.close()
sys.exit(1 if FALLARON else 0)
