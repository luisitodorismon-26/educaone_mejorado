# -*- coding: utf-8 -*-
"""CIERRE DE ANO C2 — contexto explicito origen->destino y cohorte del origen.

Que se prueba aqui:

  · que la transicion se DECLARA y no se adivina: dos años explicitos,
    validados, tenant-safe, y un rechazo fail-closed para cada estado que
    no permite promover;
  · que la cohorte son los alumnos cuyo CURSO pertenece al año origen, y
    nadie mas: ni el ya movido, ni el matriculado directamente en el año
    nuevo, ni el de un tercer año;
  · que de ese filtro sale la idempotencia secuencial, sin ninguna columna
    ni marca nueva;
  · y que el safety lock de C1 sigue puesto: los cuatro writers responden
    409 y el RBAC no cambio.

Los helpers de C2 son PUROS: consultan y validan, no escriben. Por eso
estas pruebas no necesitan apagar la bandera en ningun momento — y se
comprueba al final que sigue en True.

Base temporal aislada. Nunca produccion.
"""
import ast
import asyncio
import inspect
import io
import os
import sys

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(BK, "tools"))

from test_utils import aislar_base_de_datos  # noqa: E402

TMP = aislar_base_de_datos('c2_contexto_anos')

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import event  # noqa: E402
from database import engine, SessionLocal  # noqa: E402
from test_utils import verificar_engine_aislado  # noqa: E402

verificar_engine_aislado(engine, TMP)

import models as M  # noqa: E402
import app as APP  # noqa: E402
from auth import create_token  # noqa: E402

M.Base.metadata.create_all(bind=engine)

ORD = {1: '1ro', 2: '2do', 3: '3ro', 4: '4to', 5: '5to', 6: '6to'}

PASARON = []
FALLARON = []


def check(nombre, cond, detalle=''):
    if cond:
        PASARON.append(nombre)
        print("  PASA   %-56s %s" % (nombre, detalle))
    else:
        FALLARON.append(nombre)
        print("  FALLA  %-56s %s" % (nombre, detalle))


# ───────────────────────── infraestructura ─────────────────────────

class Req:
    def __init__(self, body=None, path='/api/test'):
        self._b = body if body is not None else {}
        self.client = type('C', (), {'host': '127.0.0.1'})()
        self.headers = {}
        self.url = type('U', (), {'path': path})()
        self.method = 'POST'

    async def json(self):
        return self._b


class Vigilante:
    """Cuenta escrituras reales. Los helpers de C2 no pueden producir ninguna."""

    def __init__(self, db):
        self.db = db
        self.total = 0

    def _on_flush(self, session, ctx, instances):
        self.total += len(session.new) + len(session.dirty) + len(session.deleted)

    def __enter__(self):
        event.listen(self.db, 'before_flush', self._on_flush)
        return self

    def __exit__(self, *a):
        event.remove(self.db, 'before_flush', self._on_flush)


def usuario_real(db, col, role='direccion', sufijo=''):
    u = M.Usuario(colegio_id=col.id, username='%s-%s%s' % (role, col.codigo, sufijo),
                  password_hash='x', nombre='U', role=role, activo=True,
                  must_change_password=False, token_version=0)
    db.add(u)
    db.commit()
    return u


def montar(db, nombre, codigo):
    """Colegio con TRES años: A cerrado, B en curso, C un tercero.

    A = 2025-2026  cerrado, inactivo   -> el año que se promueve
    B = 2026-2027  abierto, activo     -> el año destino
    C = 2024-2025  cerrado, inactivo   -> un año anterior cualquiera
    """
    col = M.Colegio(nombre=nombre, codigo=codigo, activo=True)
    db.add(col)
    db.flush()

    grados = {}
    for n in range(1, 7):
        g = M.Grado(colegio_id=col.id, nombre='%s Secundaria' % ORD[n],
                    nivel='secundaria', orden=n, activo=True)
        db.add(g)
        grados[n] = g
    db.flush()

    A = M.AnoEscolar(colegio_id=col.id, nombre='2025-2026', activo=False, cerrado=True)
    B = M.AnoEscolar(colegio_id=col.id, nombre='2026-2027', activo=True, cerrado=False)
    C = M.AnoEscolar(colegio_id=col.id, nombre='2024-2025', activo=False, cerrado=True)
    db.add_all([A, B, C])
    db.flush()

    tanda = M.Tanda(colegio_id=col.id, nombre='Matutina',
                    hora_inicio='07:30', hora_fin='12:30')
    db.add(tanda)
    db.flush()

    cursos = {}
    for ano, etiqueta in ((A, 'A'), (B, 'B'), (C, 'C')):
        for n in (1, 2, 3):
            c = M.Curso(colegio_id=col.id, nombre='%s%d' % (etiqueta, n),
                        grado_id=grados[n].id, tanda_id=tanda.id,
                        ano_escolar_id=ano.id, activo=True)
            db.add(c)
            db.flush()
            cursos[(etiqueta, n)] = c
    db.commit()
    return col, A, B, C, grados, tanda, cursos


_seq = [0]


def alumno(db, col, curso=None, activo=True):
    _seq[0] += 1
    e = M.Estudiante(colegio_id=col.id, matricula='%s-%04d' % (col.codigo, _seq[0]),
                     nombre='E%d' % _seq[0], apellido='S',
                     curso_id=curso.id if curso else None,
                     activo=activo, condicion='Inscrito')
    db.add(e)
    db.commit()
    return e


def cuerpo(resp):
    import json
    return json.loads(bytes(resp.body).decode('utf-8'))


db = SessionLocal()

check('C2-0  el safety lock de C1 esta puesto al empezar',
      APP.CIERRE_ANO_BLOQUEADO is True, '')

col, A, B, C, grados, tanda, cursos = montar(db, 'C2', 'C2A')
DIR = usuario_real(db, col)

# Un segundo colegio, para las pruebas cross-tenant.
colX, AX, BX, CX, gradosX, tandaX, cursosX = montar(db, 'Otro', 'C2X')
DIRX = usuario_real(db, colX)


print()
print("=" * 94)
print("BLOQUE 1 — la transicion se declara, no se adivina")
print("=" * 94)

# ── C2-1 ──────────────────────────────────────────────────────────
with Vigilante(db) as v:
    origen, destino = APP._resolver_transicion_cierre(db, DIR, A.id, B.id)
check('C2-1  origen y destino explicitos validos -> contexto correcto',
      origen.id == A.id and destino.id == B.id and v.total == 0,
      '%s -> %s (escrituras=%d)' % (origen.nombre, destino.nombre, v.total))


def rechaza(etiqueta, ano_origen_id, ano_destino_id, codigo_esperado,
            usuario=None, status_esperado=409):
    """Ejecuta la resolucion y comprueba el rechazo fail-closed."""
    u = usuario or DIR
    with Vigilante(db) as vig:
        try:
            APP._resolver_transicion_cierre(db, u, ano_origen_id, ano_destino_id)
            check(etiqueta, False, 'NO rechazo: devolvio un contexto')
            return None
        except APP.TransicionCierreInvalida as ex:
            ok = ex.codigo == codigo_esperado and ex.status == status_esperado
            check(etiqueta, ok and vig.total == 0,
                  'codigo=%s status=%s escrituras=%d' % (ex.codigo, ex.status, vig.total))
            return ex
        except HTTPException as ex:
            check(etiqueta, False, 'HTTP %s: %s' % (ex.status_code, ex.detail))
            return None


# ── C2-2 ──────────────────────────────────────────────────────────
rechaza('C2-2  origen == destino -> rechazo', A.id, A.id,
        APP.ERROR_TRANSICION_ANOS_IGUALES)

# ── C2-5 ──────────────────────────────────────────────────────────
# B esta abierto: usarlo como origen debe rechazarse por NO CERRADO.
rechaza('C2-5  origen no cerrado -> rechazo', B.id, A.id,
        APP.ERROR_ORIGEN_NO_CERRADO)

# ── C2-6 ──────────────────────────────────────────────────────────
# Un año cerrado Y activo a la vez (la contradiccion que C1 impide crear
# por la via normal, pero que puede existir en datos historicos).
raro = M.AnoEscolar(colegio_id=col.id, nombre='2023-2024', activo=True, cerrado=True)
db.add(raro)
db.commit()
rechaza('C2-6  origen todavia activo -> rechazo', raro.id, B.id,
        APP.ERROR_ORIGEN_TODAVIA_ACTIVO)

# ── C2-7 ──────────────────────────────────────────────────────────
rechaza('C2-7  destino no activo -> rechazo', A.id, C.id,
        APP.ERROR_DESTINO_NO_ACTIVO)

# ── C2-8 ──────────────────────────────────────────────────────────
# Un destino cerrado pero activo: llega al chequeo de `cerrado`.
rechaza('C2-8  destino cerrado -> rechazo', A.id, raro.id,
        APP.ERROR_DESTINO_CERRADO)

db.delete(raro)
db.commit()

# ── falta alguno de los dos ────────────────────────────────────────
rechaza('C2-2b sin ano_origen_id -> rechazo 400', None, B.id,
        APP.ERROR_TRANSICION_INCOMPLETA, status_esperado=400)
rechaza('C2-2c sin ano_destino_id -> rechazo 400', A.id, None,
        APP.ERROR_TRANSICION_INCOMPLETA, status_esperado=400)


print()
print("=" * 94)
print("BLOQUE 2 — tenant-safe, sin fuga")
print("=" * 94)


def cross_tenant(etiqueta, oid, did):
    with Vigilante(db) as vig:
        try:
            APP._resolver_transicion_cierre(db, DIR, oid, did)
            check(etiqueta, False, 'NO rechazo: resolvio un año ajeno')
            return None
        except HTTPException as ex:
            ok = ex.status_code == 404 and vig.total == 0
            check(etiqueta, ok, 'HTTP %s detail=%r' % (ex.status_code, ex.detail))
            return ex
        except APP.TransicionCierreInvalida as ex:
            check(etiqueta, False, 'rechazo por estado, no por tenant: %s' % ex.codigo)
            return None


# ── C2-3 / C2-4 ───────────────────────────────────────────────────
ex_origen = cross_tenant('C2-3  origen de otro tenant -> 404', AX.id, B.id)
ex_destino = cross_tenant('C2-4  destino de otro tenant -> 404', A.id, BX.id)

# El 404 de un año ajeno tiene que ser identico al de uno inexistente: si
# difiriese, el error diria si el recurso existe en otro colegio.
with Vigilante(db):
    try:
        APP._resolver_transicion_cierre(db, DIR, 987654, B.id)
        ex_inexistente = None
    except HTTPException as ex:
        ex_inexistente = ex

check('C2-3b ajeno e inexistente dan el MISMO 404',
      ex_origen is not None and ex_inexistente is not None
      and (ex_origen.status_code, ex_origen.detail)
      == (ex_inexistente.status_code, ex_inexistente.detail),
      repr(getattr(ex_inexistente, 'detail', None)))

check('C2-3c el 404 no filtra el nombre del año ajeno',
      ex_origen is not None and AX.nombre not in str(ex_origen.detail)
      and 'C2X' not in str(ex_origen.detail),
      '')


print()
print("=" * 94)
print("BLOQUE 3 — la cohorte es la del año origen, y nadie mas")
print("=" * 94)

# Alumno 1: curso de A                  -> candidato
# Alumno 2: ya movido a un curso de B   -> fuera
# Alumno 3: matriculado nuevo en B      -> fuera
# Alumno 4: curso del tercer año C      -> fuera
# Alumno 5: activo pero SIN curso       -> fuera del movimiento, diagnosticado
# Alumno 6: curso de A pero INACTIVO    -> fuera
e1 = alumno(db, col, cursos[('A', 1)])
e2 = alumno(db, col, cursos[('B', 2)])
e3 = alumno(db, col, cursos[('B', 1)])
e4 = alumno(db, col, cursos[('C', 3)])
e5 = alumno(db, col, None)
e6 = alumno(db, col, cursos[('A', 2)], activo=False)
# Y un alumno del OTRO colegio en un curso de su propio año A.
eX = alumno(db, colX, cursosX[('A', 1)])

origen, destino = APP._resolver_transicion_cierre(db, DIR, A.id, B.id)
with Vigilante(db) as v:
    candidatos, diag = APP._candidatos_pendientes_del_ano_origen(db, DIR, origen)
ids = [e.id for e in candidatos]

check('C2-9  alumno en curso de A -> incluido', e1.id in ids, 'ids=%s' % ids)
check('C2-10 alumno ya movido a B -> excluido', e2.id not in ids, '')
check('C2-11 alumno matriculado nuevo en B -> excluido', e3.id not in ids, '')
check('C2-12 alumno en el tercer año C -> excluido', e4.id not in ids, '')
check('C2-13 alumno sin curso -> no es candidato, pero se reporta',
      e5.id not in ids and e5.id in diag['activos_sin_curso'],
      'activos_sin_curso=%s' % diag['activos_sin_curso'])
check('C2-13b un alumno inactivo de A tampoco entra', e6.id not in ids, '')
check('C2-13c ningun alumno de otro colegio entra', eX.id not in ids, '')
check('C2-14 solo los candidatos de A son procesables',
      ids == [e1.id] and diag['total_candidatos'] == 1,
      'candidatos=%s total=%s' % (ids, diag['total_candidatos']))
check('C2-14b seleccionar la cohorte no escribe nada', v.total == 0, '')

# ── C2-16 ─────────────────────────────────────────────────────────
# Prueba de comportamiento: «todos los activos» serian 5 (e1..e5 menos el
# inactivo). La cohorte es 1. Si alguien volviese a filtrar solo por
# `Estudiante.activo`, este numero saltaria.
activos = (db.query(M.Estudiante)
           .filter_by(colegio_id=col.id, activo=True).count())
check('C2-16 la seleccion NO es "todos los activos del colegio"',
      activos > len(ids) and len(ids) == 1,
      'activos del colegio=%d, cohorte de A=%d' % (activos, len(ids)))


print()
print("=" * 94)
print("BLOQUE 4 — idempotencia secuencial, sin columnas nuevas")
print("=" * 94)

# ── C2-15 ─────────────────────────────────────────────────────────
# Se simula el efecto de una promocion: el alumno pasa a un curso del año
# destino. No se llama al writer —sigue bloqueado—; se mueve el curso a
# mano, que es exactamente el estado en que lo dejaria.
e1.curso_id = cursos[('B', 2)].id
db.commit()

candidatos2, diag2 = APP._candidatos_pendientes_del_ano_origen(db, DIR, origen)
check('C2-15 tras pasar A->B, la segunda seleccion ya no lo incluye',
      e1.id not in [e.id for e in candidatos2] and diag2['total_candidatos'] == 0,
      'cohorte de A ahora=%d' % diag2['total_candidatos'])

check('C2-15b la idempotencia no necesita ninguna marca por estudiante',
      not any(c.name in ('promovido', 'cierre_procesado', 'promocion_procesada')
              for c in M.Estudiante.__table__.columns),
      'columnas de Estudiante sin marcas de cierre')
check('C2-15c ni ninguna marca por año',
      not any(c.name in ('promocion_ejecutada', 'cierre_procesado')
              for c in M.AnoEscolar.__table__.columns),
      '')

# Se devuelve al estado anterior para no arrastrar el efecto.
e1.curso_id = cursos[('A', 1)].id
db.commit()


print()
print("=" * 94)
print("BLOQUE 5 — lo que el camino de C2 NO hace (fail-closed por omision)")
print("=" * 94)

_FUENTE_C2 = {
    nombre: inspect.getsource(getattr(APP, nombre))
    for nombre in ('_resolver_transicion_cierre',
                   '_candidatos_pendientes_del_ano_origen')
}


def _arbol(nombre):
    import textwrap
    return ast.parse(textwrap.dedent(_FUENTE_C2[nombre]))


def _comparaciones_curso(arbol):
    """Toda comparacion cuyo lado izquierdo sea un atributo de `Curso`."""
    fuera = []
    for n in ast.walk(arbol):
        if isinstance(n, ast.Compare) and isinstance(n.left, ast.Attribute):
            izq = n.left
            if isinstance(izq.value, ast.Name) and izq.value.id == 'Curso':
                fuera.append((izq.attr, ast.dump(n.comparators[0],
                                                 include_attributes=False)))
    return fuera


comparaciones = _comparaciones_curso(_arbol('_candidatos_pendientes_del_ano_origen'))
_atributos = [a for a, _ in comparaciones]
# CORE-1 §2 endurecio el filtro: sobre `Curso` se comprueba el AÑO y el
# COLEGIO, y nada mas. El colegio hace falta porque `tenant_filter` solo mira
# al estudiante, y una fila corrupta —alumno de A con curso de B— entraria
# por la puerta del curso. Grado y tanda siguen prohibidos aqui: elegir por
# ellos es resolver un destino, y C2 no resuelve destinos.
check('C2-17 sobre Curso solo se filtra AÑO y COLEGIO, nunca grado+tanda',
      comparaciones and set(_atributos) == {'ano_escolar_id', 'colegio_id'},
      '%s' % _atributos)
check('C2-17b y ese año es el ORIGEN, no otro',
      all('ano_origen' in dump for attr, dump in comparaciones
          if attr == 'ano_escolar_id'),
      '')
check('C2-17d el filtro de colegio ata el curso al MISMO tenant',
      all(('Estudiante' in dump or 'ano_origen' in dump)
          for attr, dump in comparaciones if attr == 'colegio_id'),
      '')

# C2 se detiene antes de decidir grado destino: no hay resolucion de curso
# destino en el camino nuevo, asi que no puede elegir uno del año
# equivocado. Preferimos parar a reutilizar el resolver antiguo.
texto_c2 = ''.join(_FUENTE_C2.values())
for prohibido in ('grado_id=', 'tanda_id=', 'orden + 1', "'promueve'", 'overrides'):
    check('C2-17c el camino de C2 no contiene %r' % prohibido,
          prohibido not in texto_c2, '')

# Y no escribe: ni commit, ni flush, ni add, ni delete.
for prohibido in ('db.commit(', 'db.flush(', 'db.add(', 'db.delete('):
    check('C2-10b los helpers no llaman a %s)' % prohibido,
          prohibido not in texto_c2, '')

# El N+1: la misma transicion con 3 alumnos y con 9 debe costar lo mismo.
def _contar_consultas(fn):
    caja = []

    def _antes(conn, cur, stmt, params, ctx, many):
        caja.append(stmt)

    event.listen(engine, 'before_cursor_execute', _antes)
    try:
        fn()
    finally:
        event.remove(engine, 'before_cursor_execute', _antes)
    return len(caja)


db.expire_all()
n3 = _contar_consultas(lambda: [
    (e.curso.grado.nombre if e.curso and e.curso.grado else None)
    for e in APP._candidatos_pendientes_del_ano_origen(db, DIR, origen)[0]])
for _ in range(8):
    alumno(db, col, cursos[('A', 3)])
db.expire_all()
n9 = _contar_consultas(lambda: [
    (e.curso.grado.nombre if e.curso and e.curso.grado else None)
    for e in APP._candidatos_pendientes_del_ano_origen(db, DIR, origen)[0]])
check('C2-14c leer curso y grado de la cohorte no produce N+1',
      n3 == n9, 'consultas con 1 alumno=%d, con 9=%d' % (n3, n9))


print()
print("=" * 94)
print("BLOQUE 6 — el safety lock de C1 sigue intacto")
print("=" * 94)

from fastapi.testclient import TestClient  # noqa: E402

col2, A2_, B2_, C2_, grados2, tanda2, cursos2 = montar(db, 'Lock', 'C2L')
dir2 = usuario_real(db, col2)
prof2 = usuario_real(db, col2, role='profesor')
TOK_DIR = create_token(dir2)
TOK_PROF = create_token(prof2)

ENDPOINTS = [
    ('POST /api/ano-escolar/{id}/cerrar',
     '/api/ano-escolar/%d/cerrar' % A2_.id, {},
     'CIERRE_ANO_TEMPORALMENTE_BLOQUEADO'),
    ('POST /api/cierre-ano/promover',
     '/api/cierre-ano/promover',
     {'ano_origen_id': A2_.id, 'ano_destino_id': B2_.id, 'nuevo_ano_id': B2_.id},
     'CIERRE_ANO_TEMPORALMENTE_BLOQUEADO'),
    ('POST /api/promocion/ejecutar', '/api/promocion/ejecutar',
     {'estudiantes': [e1.id]}, 'PROMOCION_LEGACY_BLOQUEADA'),
    ('POST /api/ano-escolar/promover', '/api/ano-escolar/promover', {},
     'PROMOCION_LEGACY_BLOQUEADA'),
]

with TestClient(APP.app) as cli:
    for etiqueta, ruta, body, codigo in ENDPOINTS:
        r = cli.post(ruta, json=body,
                     headers={'Authorization': 'Bearer %s' % TOK_DIR})
        # C2-18 / C2-19: aunque el body traiga ya el contrato nuevo, el lock
        # rechaza antes de leerlo. C2 no desbloquea nada.
        check('C2-18 %s sigue en 409' % etiqueta,
              r.status_code == 409 and r.json().get('error') == codigo,
              'status=%s error=%s' % (r.status_code, r.json().get('error')))

        rp = cli.post(ruta, json=body,
                      headers={'Authorization': 'Bearer %s' % TOK_PROF})
        ra = cli.post(ruta, json=body)
        check('C2-20 %s · RBAC sin cambios (prof 403 / anon 401)' % etiqueta,
              rp.status_code == 403 and ra.status_code == 401
              and codigo not in rp.text and codigo not in ra.text,
              'prof=%s anon=%s' % (rp.status_code, ra.status_code))

check('C2-19 los cuatro writers de C1 siguen bloqueados',
      APP.CIERRE_ANO_BLOQUEADO is True, '')

# Y el año origen del colegio de prueba no se movio ni un poco.
db.expire_all()
check('C2-19b ninguna llamada HTTP cambio el estado de los años',
      db.get(M.AnoEscolar, A2_.id).cerrado is True
      and db.get(M.AnoEscolar, A2_.id).activo is False
      and db.get(M.AnoEscolar, B2_.id).activo is True
      and db.get(M.AnoEscolar, B2_.id).cerrado is False,
      '')

check('C2-Z  la bandera sigue en True al terminar',
      APP.CIERRE_ANO_BLOQUEADO is True,
      'ninguna prueba de C2 necesito apagarla')


print()
print("=" * 94)
print("RESULTADO: %d PASARON / %d FALLARON" % (len(PASARON), len(FALLARON)))
print("=" * 94)
for f in FALLARON:
    print("  FALLA:", f)

db.close()
sys.exit(1 if FALLARON else 0)
