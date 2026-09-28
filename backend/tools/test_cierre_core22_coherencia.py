# -*- coding: utf-8 -*-
"""CIERRE DE ANO CORE-2.2 — estado, resumen y preview hablan del mismo año.

El paquete de evidencia de CORE-2 encontro que, terminada una transicion,
`/cierre-ano/estado` decia correctamente «no hay transicion, el año en curso
es B» mientras `/cierre-ano/resumen` —pedido sin `ano_id`— seguia devolviendo
la cohorte de A, porque resolvia por su cuenta con «el cerrado mas reciente».
La pantalla mostraba los numeros del año pasado bajo un encabezado sobre el
actual.

Estos tests son CRUZADOS a proposito: comparan las tres respuestas entre si.
Probar cada endpoint por separado era justamente lo que dejo pasar el
defecto.

Base temporal aislada. Nunca produccion.
"""
import asyncio
import os
import sys

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(BK, "tools"))

from test_utils import aislar_base_de_datos  # noqa: E402

TMP = aislar_base_de_datos('c_core22')

from database import engine, SessionLocal  # noqa: E402
from test_utils import verificar_engine_aislado  # noqa: E402

verificar_engine_aislado(engine, TMP)

import models as M  # noqa: E402
import promocion_academica as PA  # noqa: E402
import resultado_academico as RA  # noqa: E402
import resultado_academico_consumidores as AD  # noqa: E402
import app as APP  # noqa: E402

M.Base.metadata.create_all(bind=engine)

AREAS = list(AD.curriculo_oficial_esperado(RA.NIVEL_SECUNDARIA, 3)[0])
DIAS = {'ago': 20, 'sep': 20, 'oct': 20, 'nov': 20, 'dic': 15, 'ene': 20,
        'feb': 18, 'mar': 20, 'abr': 18, 'may': 20, 'jun': 15}

PASARON, FALLARON = [], []


def check(nombre, cond, detalle=''):
    if cond:
        PASARON.append(nombre)
        print("  PASA   %-58s %s" % (nombre, detalle))
    else:
        FALLARON.append(nombre)
        print("  FALLA  %-58s %s" % (nombre, detalle))


def cuerpo(r):
    import json
    return json.loads(bytes(r.body).decode('utf-8'))


db = SessionLocal()
_seq = [0]


def montar(codigo, anos):
    """Un colegio con los años que se pidan.

    `anos` es una lista de (nombre, cerrado, activo, con_alumno_pendiente).
    Devuelve (col, usuario, {nombre: AnoEscolar}).
    """
    _seq[0] += 1
    col = M.Colegio(nombre=codigo, codigo=codigo, activo=True)
    db.add(col)
    db.flush()
    g = M.Grado(colegio_id=col.id, nombre='3ro Secundaria',
                nivel='secundaria', orden=3, activo=True)
    db.add(g)
    db.flush()
    prof = M.Usuario(colegio_id=col.id, username='p-%s' % codigo,
                     password_hash='x', nombre='P', role='profesor',
                     activo=True, must_change_password=False, token_version=0)
    usr = M.Usuario(colegio_id=col.id, username='d-%s' % codigo,
                    password_hash='x', nombre='D', role='direccion',
                    activo=True, must_change_password=False, token_version=0)
    db.add_all([prof, usr])
    db.flush()
    asigs = {}
    for cod in AREAS:
        a = M.Asignatura(colegio_id=col.id, nombre=cod, codigo=cod[:10],
                         area='X', area_curricular_codigo=cod, activo=True)
        db.add(a)
        db.flush()
        asigs[cod] = a

    creados = {}
    for nombre, cerrado, activo, con_alumno in anos:
        ano = M.AnoEscolar(colegio_id=col.id, nombre=nombre,
                           activo=activo, cerrado=cerrado)
        ano.set_dias_trabajados(DIAS)
        db.add(ano)
        db.flush()
        curso = M.Curso(colegio_id=col.id, nombre='A', grado_id=g.id,
                        ano_escolar_id=ano.id, activo=True)
        db.add(curso)
        db.flush()
        creados[nombre] = ano
        if not con_alumno:
            continue
        for cod in AREAS:
            db.add(M.AsignacionProfesor(
                colegio_id=col.id, profesor_id=prof.id, curso_id=curso.id,
                asignatura_id=asigs[cod].id, ano_escolar_id=ano.id,
                activo=True))
        est = M.Estudiante(colegio_id=col.id,
                           matricula='%s-%s' % (codigo, nombre[:4]),
                           nombre='E', apellido='S', curso_id=curso.id,
                           activo=True, condicion='activo')
        db.add(est)
        db.flush()
        for cod in AREAS:
            for k in range(1, 5):
                db.add(M.CalificacionSecundaria(
                    colegio_id=col.id, estudiante_id=est.id,
                    asignatura_id=asigs[cod].id, ano_escolar_id=ano.id,
                    competencia_numero=k, p1=90, p2=90, p3=90, p4=90))
    db.commit()
    return col, usr, creados


def tres_respuestas(usr, ano_id=None):
    """Las tres llamadas que hace la pantalla, con el mismo criterio."""
    estado = asyncio.run(APP.get_estado_cierre_ano(db=db, current_user=usr))
    resumen = asyncio.run(APP.get_resumen_cierre_ano(
        ano_id=ano_id, db=db, current_user=usr))
    preview = asyncio.run(APP.get_datos_promocion(
        ano_id=ano_id, db=db, current_user=usr))
    return estado, resumen, preview


def ano_visible(estado):
    """Lo que el frontend calcula como año visible."""
    if estado.get('origen_ambiguo'):
        return None
    origen = (estado.get('ano_origen') or {}).get('id')
    return origen if origen is not None else estado.get('ano_activo_id')


print()
print("=" * 96)
print("CORE-2.2 — coherencia cruzada entre estado, resumen y preview")
print("=" * 96)

# ── CORE2.2-1: transicion TERMINADA ───────────────────────────────
col, usr, anos = montar('CH1', [('2025-2026', True, False, False),
                                ('2026-2027', False, True, True)])
A, B = anos['2025-2026'], anos['2026-2027']
# Un alumno ya procesado en A: historial canonico, curso en B.
est_b = db.query(M.Estudiante).filter_by(colegio_id=col.id).first()
db.add(M.HistorialAcademico(
    colegio_id=col.id, estudiante_id=est_b.id, ano_escolar_id=A.id,
    condicion=PA.PROMOVIDO))
db.commit()

estado, resumen, preview = tres_respuestas(usr)
visible = ano_visible(estado)
check('CORE2.2-1  transicion terminada: estado y resumen dicen B',
      estado['ano_origen'] is None and estado['ano_activo_id'] == B.id
      and resumen['ano_escolar_id'] == B.id,
      'estado.activo=%s resumen=%s' % (estado['ano_activo_id'],
                                       resumen['ano_escolar_id']))
check('CORE2.2-1b y la preview tambien',
      preview['ano_escolar_id'] == B.id, str(preview['ano_escolar_id']))
check('CORE2.2-1c el año visible que calcula la pantalla es B',
      visible == B.id, str(visible))

# ── CORE2.2-2: transicion PARCIAL ─────────────────────────────────
col, usr, anos = montar('CH2', [('2025-2026', True, False, True),
                                ('2026-2027', False, True, False)])
A, B = anos['2025-2026'], anos['2026-2027']
estado, resumen, preview = tres_respuestas(usr)
visible = ano_visible(estado)
check('CORE2.2-2  transicion parcial: los tres dicen A',
      (estado['ano_origen'] or {}).get('id') == A.id
      and resumen['ano_escolar_id'] == A.id
      and preview['ano_escolar_id'] == A.id,
      'estado=%s resumen=%s preview=%s' % (
          (estado['ano_origen'] or {}).get('id'),
          resumen['ano_escolar_id'], preview['ano_escolar_id']))
check('CORE2.2-2b y el destino es B',
      (estado['ano_destino'] or {}).get('id') == B.id, '')
check('CORE2.2-2c el año visible es A', visible == A.id, str(visible))

# ── CORE2.2-3: A cerrado, B no existe ─────────────────────────────
col, usr, anos = montar('CH3', [('2025-2026', True, False, True)])
A = anos['2025-2026']
estado, resumen, preview = tres_respuestas(usr)
check('CORE2.2-3  A cerrado sin B: estado, resumen y preview dicen A',
      (estado['ano_origen'] or {}).get('id') == A.id
      and estado['ano_destino'] is None
      and resumen['ano_escolar_id'] == A.id
      and preview['ano_escolar_id'] == A.id,
      'destino=%s' % estado['ano_destino'])
check('CORE2.2-3b y no busca otro año cerrado',
      ano_visible(estado) == A.id, '')

# ── CORE2.2-4: año abierto normal ─────────────────────────────────
col, usr, anos = montar('CH4', [('2025-2026', False, True, True)])
A = anos['2025-2026']
estado, resumen, preview = tres_respuestas(usr)
check('CORE2.2-4  año abierto normal: activo=A y resumen=A',
      estado['ano_activo_id'] == A.id
      and estado['transicion_en_progreso'] is False
      and resumen['ano_escolar_id'] == A.id
      and preview['ano_escolar_id'] == A.id,
      'activo=%s resumen=%s' % (estado['ano_activo_id'],
                                resumen['ano_escolar_id']))

# ── CORE2.2-5 y 6: origen AMBIGUO ─────────────────────────────────
col, usr, anos = montar('CH5', [('2024-2025', True, False, True),
                                ('2025-2026', True, False, True),
                                ('2026-2027', False, True, False)])
C, A = anos['2024-2025'], anos['2025-2026']
estado = asyncio.run(APP.get_estado_cierre_ano(db=db, current_user=usr))
check('CORE2.2-5  origen ambiguo: el estado no elige ninguno',
      estado['ano_origen'] is None and len(estado['origen_ambiguo']) == 2,
      str([a['nombre'] for a in estado['origen_ambiguo']]))

_r = asyncio.run(APP.get_resumen_cierre_ano(db=db, current_user=usr))
check('CORE2.2-5b el resumen SIN ano_id tampoco elige',
      hasattr(_r, 'status_code') and _r.status_code == 409
      and cuerpo(_r)['error'] == APP.ERROR_CIERRE_ORIGEN_AMBIGUO,
      cuerpo(_r).get('error') if hasattr(_r, 'body') else type(_r).__name__)
_p = asyncio.run(APP.get_datos_promocion(db=db, current_user=usr))
check('CORE2.2-5c y la preview tampoco',
      hasattr(_p, 'status_code') and _p.status_code == 409, '')
check('CORE2.2-5d el año visible que calcula la pantalla es NINGUNO',
      ano_visible(estado) is None, str(ano_visible(estado)))

for etiqueta, elegido in (('el mas antiguo', C), ('el mas reciente', A)):
    estado_e = asyncio.run(APP.get_estado_cierre_ano(
        ano_origen_id=elegido.id, db=db, current_user=usr))
    resumen_e = asyncio.run(APP.get_resumen_cierre_ano(
        ano_id=elegido.id, db=db, current_user=usr))
    preview_e = asyncio.run(APP.get_datos_promocion(
        ano_id=elegido.id, db=db, current_user=usr))
    check('CORE2.2-6  al elegir %s, los tres usan ESE' % etiqueta,
          (estado_e['ano_origen'] or {}).get('id') == elegido.id
          and resumen_e['ano_escolar_id'] == elegido.id
          and preview_e['ano_escolar_id'] == elegido.id,
          '%s (id=%s)' % (elegido.nombre, elegido.id))

# ── CORE2.2-7 y 8 ─────────────────────────────────────────────────
col, usr, anos = montar('CH7', [('2025-2026', True, False, True),
                                ('2026-2027', False, True, False)])
A, B = anos['2025-2026'], anos['2026-2027']
estado = asyncio.run(APP.get_estado_cierre_ano(db=db, current_user=usr))
preview = asyncio.run(APP.get_datos_promocion(
    ano_id=(estado['ano_origen'] or {}).get('id'), db=db, current_user=usr))
check('CORE2.2-7  preview con origen explicito coincide con el origen',
      preview['ano_escolar_id'] == A.id, str(preview['ano_escolar_id']))

# Terminada la transicion, la preview sin ano_id NO vuelve al cerrado.
est_a = (db.query(M.Estudiante)
         .join(M.Curso, M.Estudiante.curso_id == M.Curso.id)
         .filter(M.Estudiante.colegio_id == col.id,
                 M.Curso.ano_escolar_id == A.id).first())
db.add(M.HistorialAcademico(
    colegio_id=col.id, estudiante_id=est_a.id, ano_escolar_id=A.id,
    condicion=PA.PROMOVIDO))
est_a.curso_id = db.query(M.Curso).filter_by(
    colegio_id=col.id, ano_escolar_id=B.id).first().id
db.commit()
preview2 = asyncio.run(APP.get_datos_promocion(db=db, current_user=usr))
check('CORE2.2-8  preview sin origen NO vuelve al "ultimo cerrado"',
      preview2['ano_escolar_id'] == B.id,
      'devolvio %s (A=%s B=%s)' % (preview2['ano_escolar_id'], A.id, B.id))

resumen2 = asyncio.run(APP.get_resumen_cierre_ano(db=db, current_user=usr))
check('CORE2.2-8b y el resumen tampoco',
      resumen2['ano_escolar_id'] == B.id, str(resumen2['ano_escolar_id']))


print()
print("=" * 96)
print("CORE-2.2 — el frontend no conserva años stale")
print("=" * 96)

import io as _io  # noqa: E402

FE = os.path.join(os.path.dirname(BK), 'frontend', 'src', 'pages',
                  'cierre-ano', 'CierreAnoPage.tsx')
fe = _io.open(FE, encoding='utf-8').read()

check('CORE2.2-9  limpia anoOrigenId cuando ya no hay origen',
      'setAnoOrigenId(est?.ano_origen?.id ?? null)' in fe
      and 'if (est.ano_origen) setAnoOrigenId' not in fe, '')
check('CORE2.2-10 limpia nuevoAnoId cuando ya no hay destino',
      'setNuevoAnoId(est?.ano_destino?.id ?? null)' in fe
      and 'if (est.ano_destino) setNuevoAnoId' not in fe, '')
check('CORE2.2-11 el resumen se pide con ano_id explicito',
      "api.get('/cierre-ano/resumen',\n          { params: { ano_id: visibleAnoId } })" in fe
      or "{ params: { ano_id: visibleAnoId } }" in fe,
      '')
check('CORE2.2-12 el estado se consulta ANTES que el resumen',
      fe.index("api.get('/cierre-ano/estado')")
      < fe.index("api.get('/cierre-ano/resumen'"), '')
check('CORE2.2-13 la preview nunca se pide sin año',
      "const res = await api.get('/cierre-ano/promocion',\n        { params: { ano_id: origen } });" in fe
      and 'origen ? { params: { ano_id: origen } } : undefined' not in fe, '')
check('CORE2.2-14 y el comentario del "ultimo cerrado" ya no promete eso',
      'backend resuelve por su cuenta' not in fe, '')
check('CORE2.2-15 el origen ambiguo se puede ELEGIR, no solo leer',
      'elegirAnoOrigen' in fe
      and 'ano_origen_id: id' in fe, '')

check('CORE2.2-16 los candados, en su estado de release',
      APP.CIERRE_ANO_BLOQUEADO is False
      and APP.PROMOCION_LEGACY_BLOQUEADA is True, '')


print()
print("=" * 96)
print("RESULTADO: %d PASARON / %d FALLARON" % (len(PASARON), len(FALLARON)))
print("=" * 96)
for f in FALLARON:
    print("  FALLA:", f)

db.close()
sys.exit(1 if FALLARON else 0)
