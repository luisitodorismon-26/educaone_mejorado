# -*- coding: utf-8 -*-
"""TRAS-1 · Retiros y traslados de curso/tanda sin perder historial.

Base SQLite AISLADA (tools/test_utils.aislar_base_de_datos) con datos
SINTÉTICOS. Nunca sge.db ni producción. Los nombres «Ricardo», «Abraham» e
«Hillary» son fichas sintéticas que reproducen los casos de referencia; ningún
estudiante real se toca.

Uso (desde backend/):  python tools/test_retiros_traslados.py [carpeta_salida]
"""
import datetime as dt
import hashlib
import io
import json
import os
import sys
import tempfile
import threading

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(BK, 'tools'))
OUT = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix='retiros_traslados_')
os.makedirs(OUT, exist_ok=True)
from test_utils import aislar_base_de_datos, verificar_engine_aislado  # noqa: E402

# Con EO_PG_TEST_SERVER (conexión de ADMINISTRACIÓN a un PostgreSQL local) la
# prueba crea y elimina su PROPIA base temporal (tools/pg_base_temporal.py):
# nombre único, token propio, comprobada vacía. Nunca se usa una base indicada
# por variable de entorno. Sin ella: SQLite temporal aislada.
if os.environ.get('EO_TEST_PG_URL'):
    raise SystemExit('EO_TEST_PG_URL no se acepta: use EO_PG_TEST_SERVER.')
PG_SERVER = os.environ.get('EO_PG_TEST_SERVER')
if PG_SERVER:
    import pg_base_temporal as PGT
    PG = PGT.BaseTemporal(PG_SERVER, prefijo='eo_tmp_tras_')
    os.environ['DATABASE_URL'] = PG.crear()
    TMP = None
else:
    PG = None
    TMP = aislar_base_de_datos('retiros_traslados')
from database import engine, SessionLocal  # noqa: E402
if PG:
    assert engine.dialect.name == 'postgresql' and engine.url.database == PG.nombre         and engine.url.host in ('127.0.0.1', 'localhost'), engine.url
    PG.engines.append(engine)
    print('Motor: PostgreSQL, base temporal %s' % engine.url.database)
else:
    verificar_engine_aislado(engine, TMP)
    print('Motor: SQLite temporal')
import models as M  # noqa: E402
import app as APP  # noqa: E402
import permanencia as PERM  # noqa: E402
import registro_asistencia as RA  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from auth import create_token  # noqa: E402
import pymupdf  # noqa: E402

M.Base.metadata.create_all(bind=engine)
db = SessionLocal()
c = TestClient(APP.app)
HOY = APP.today_rd()
F_TRAS = dt.date(2026, 10, 21)          # SINTÉTICA: el traslado de «Ricardo» (miércoles)
RESULTADOS = []
DATOS = {'hoy': HOY.isoformat()}


def check(nombre, cond, detalle=''):
    RESULTADOS.append((nombre, bool(cond), detalle))
    print(('  PASA  ' if cond else '  FALLA ') + nombre + ('' if cond else '  -> ' + str(detalle)[:600]))


def add(o):
    db.add(o)
    db.flush()
    return o


def H(u):
    return {'Authorization': 'Bearer ' + create_token(u)}


def dias(desde, hasta, wd):
    d, out = desde, []
    while d <= hasta:
        if d.weekday() in wd:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


# ───────────────────────────── MONTAJE ─────────────────────────────
def montar_colegio(nombre, codigo):
    col = add(M.Colegio(nombre=nombre, codigo=codigo, activo=True))
    add(M.ConfiguracionColegio(colegio_id=col.id, nombre=col.nombre, regional='10', distrito='10-01',
                               codigo_centro=codigo))
    ano = add(M.AnoEscolar(colegio_id=col.id, nombre='2026-2027', activo=True, cerrado=False,
                           fecha_inicio=dt.date(2026, 9, 1), fecha_fin=dt.date(2027, 6, 30), periodo_activo=1,
                           p1_inicio=dt.date(2026, 9, 1), p1_fin=dt.date(2026, 11, 13),
                           p2_inicio=dt.date(2026, 11, 16), p2_fin=dt.date(2027, 1, 29),
                           p3_inicio=dt.date(2027, 2, 1), p3_fin=dt.date(2027, 4, 16),
                           p4_inicio=dt.date(2027, 4, 19), p4_fin=dt.date(2027, 6, 30)))
    return col, ano


col, ano = montar_colegio('Colegio Sintético TRAS', 'STRAS')
g5 = add(M.Grado(colegio_id=col.id, nombre='5to Secundaria', nivel='secundaria', orden=5, activo=True))
g2 = add(M.Grado(colegio_id=col.id, nombre='2do Secundaria', nivel='secundaria', orden=2, activo=True))
g4 = add(M.Grado(colegio_id=col.id, nombre='4to Secundaria', nivel='secundaria', orden=4, activo=True))
tm = add(M.Tanda(colegio_id=col.id, nombre='Matutina', hora_inicio='07:30', hora_fin='12:30', activo=True))
tv = add(M.Tanda(colegio_id=col.id, nombre='Vespertina', hora_inicio='13:00', hora_fin='18:00', activo=True))
V = add(M.Curso(colegio_id=col.id, nombre='A', grado_id=g5.id, tanda_id=tv.id, ano_escolar_id=ano.id, activo=True))
MA = add(M.Curso(colegio_id=col.id, nombre='A', grado_id=g5.id, tanda_id=tm.id, ano_escolar_id=ano.id, activo=True))
D2 = add(M.Curso(colegio_id=col.id, nombre='A', grado_id=g2.id, tanda_id=tm.id, ano_escolar_id=ano.id, activo=True))
C4 = add(M.Curso(colegio_id=col.id, nombre='A', grado_id=g4.id, tanda_id=tm.id, ano_escolar_id=ano.id, activo=True))


def usuario(u, rol, nombre, colegio=None):
    colegio = colegio or col
    return add(M.Usuario(colegio_id=colegio.id, username=u, password_hash='x', nombre=nombre, apellido='Sint',
                         role=rol, activo=True, must_change_password=False, token_version=0))


dire, coord, secre = usuario('dir', 'direccion', 'Dir'), usuario('coord', 'coordinador', 'Coord'), usuario('sec', 'secretaria', 'Sec')
art = add(M.Asignatura(colegio_id=col.id, nombre='Educación Artística', codigo='EA', area_curricular_codigo='EA'))
fihr = add(M.Asignatura(colegio_id=col.id, nombre='Formación Integral Humana y Religiosa', codigo='FIHR',
                        area_curricular_codigo='FIHR'))
mus = add(M.Asignatura(colegio_id=col.id, nombre='Música', codigo='MUS'))                    # solo en la tarde
optV = add(M.Asignatura(colegio_id=col.id, nombre='Optativa HLM (Vespertina)', codigo='OPV'))
optM = add(M.Asignatura(colegio_id=col.id, nombre='Optativa HCS (Matutina)', codigo='OPM'))
PROF = {}
HORARIO = {  # (curso, asignatura): días (0=lunes) — horarios DIFERENTES por tanda
    (V.id, art.id): (0, 2), (V.id, fihr.id): (1, 3), (V.id, mus.id): (4,), (V.id, optV.id): (4,),
    (MA.id, art.id): (1, 3), (MA.id, fihr.id): (0, 2), (MA.id, optM.id): (4,),
    (D2.id, art.id): (0, 2), (D2.id, fihr.id): (1, 3),
    (C4.id, art.id): (0,),
}
NDIA = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes']
NOMBRE = {V.id: '5to A Vespertina', MA.id: '5to A Matutina', D2.id: '2do A Matutina', C4.id: '4to A Matutina'}
for (cid, aid), wds in HORARIO.items():
    p = usuario('p_%d_%d' % (cid, aid), 'profesor', 'Prof %s %s' % (aid, NOMBRE[cid]))
    PROF[(cid, aid)] = p
    add(M.AsignacionProfesor(colegio_id=col.id, profesor_id=p.id, curso_id=cid, asignatura_id=aid,
                             ano_escolar_id=ano.id, activo=True, es_titular=(aid == art.id)))
    for k, wd in enumerate(wds):
        add(M.Horario(colegio_id=col.id, profesor_id=p.id, curso_id=cid, asignatura_id=aid, dia=NDIA[wd],
                      hora_inicio='%02d:00' % (8 + (5 if cid == V.id else 0) + k),
                      hora_fin='%02d:00' % (9 + (5 if cid == V.id else 0) + k), tipo_bloque='clase', activo=True))


def estudiante(nombre, apellido, curso, n, colegio=None):
    colegio = colegio or col
    return add(M.Estudiante(colegio_id=colegio.id, nombre=nombre, apellido=apellido,
                            matricula='%s-%d-%02d' % (colegio.codigo, curso.id, n),
                            curso_id=curso.id, no_lista=n, activo=True, condicion='activo', sexo='M',
                            fecha_nacimiento=dt.date(2010, 3, 3), fecha_ingreso=dt.date(2026, 8, 20)))


EV = [estudiante('Ricardo' if n == 15 else 'Vesp%02d' % n, 'Sintético' if n == 15 else 'Tarde', V, n) for n in range(1, 21)]
EM = [estudiante('Abraham' if n == 20 else 'Mat%02d' % n, 'Sintético' if n == 20 else 'Mañana', MA, n) for n in range(1, 21)]
E2 = [estudiante('Hillary' if n == 3 else 'Seg%02d' % n, 'Sintética' if n == 3 else 'Segundo', D2, n) for n in range(1, 6)]
E4 = [estudiante('Cuarto%02d' % n, 'Curso', C4, n) for n in range(1, 3)]
RIC, ABR, HIL = EV[14], EM[19], E2[2]
# Retirados ANTERIORES a esta entrega (solo `fecha_retiro` en la ficha, sin
# movimiento), cada uno con una marca posterior a su retiro: un conflicto
# heredado que debe verse y explicarse, nunca esconderse.
M21 = estudiante('Mat21', 'Retirado', MA, 21)
M21.activo, M21.condicion, M21.fecha_retiro = False, 'retirado', dt.date(2026, 9, 9)
S6 = estudiante('Seg06', 'Retirado', D2, 6)
S6.activo, S6.condicion, S6.fecha_retiro = False, 'retirado', dt.date(2026, 10, 1)
EM_TODOS = EM + [M21]
E2_TODOS = E2 + [S6]
ASIGS = {V.id: [art, fihr, mus, optV], MA.id: [art, fihr, optM], D2.id: [art, fihr], C4.id: [art]}

# Notas: completas P1-P4 para todos, salvo Ricardo, que lleva solo P1 (hay P2-P4
# por completar en el destino) y una recuperación en Artística (P1=60, RP1=75).
for cur, ests in ((V, EV), (MA, EM_TODOS), (D2, E2_TODOS), (C4, E4)):
    for i, e in enumerate(ests):
        for a in ASIGS[cur.id]:
            for comp in (1, 2, 3, 4):
                v = 70 + (i * 3 + comp + a.id) % 25
                if e is RIC:
                    p1 = 60 if (a is art and comp == 1) else v
                    add(M.CalificacionSecundaria(colegio_id=col.id, estudiante_id=e.id, asignatura_id=a.id,
                                                 ano_escolar_id=ano.id, competencia_numero=comp, p1=p1,
                                                 rp1=75 if (a is art and comp == 1) else None))
                else:
                    add(M.CalificacionSecundaria(colegio_id=col.id, estudiante_id=e.id, asignatura_id=a.id,
                                                 ano_escolar_id=ano.id, competencia_numero=comp,
                                                 p1=v, p2=v, p3=v, p4=v))

# Asistencia de cada curso según SU horario, del 1-sep a hoy. Ricardo y Abraham solo
# hasta el 20-oct; Hillary hasta el 15-oct (dejó de asistir); los dos retirados
# heredados, hasta su retiro.
for cur, ests in ((V, EV), (MA, EM_TODOS), (D2, E2_TODOS), (C4, E4)):
    for a in ASIGS[cur.id]:
        for d in dias(dt.date(2026, 9, 1), HOY, HORARIO[(cur.id, a.id)]):
            for e in ests:
                if e in (RIC, ABR) and d > dt.date(2026, 10, 20):
                    continue
                if e in (M21, S6) and d > e.fecha_retiro:
                    continue
                if e is HIL and d > dt.date(2026, 10, 15):
                    continue
                est = 'ausente' if (e is RIC and d.day % 9 == 0) else 'presente'
                add(M.Asistencia(colegio_id=col.id, estudiante_id=e.id, curso_id=cur.id, asignatura_id=a.id,
                                 fecha=d, estado=est, registrado_por=PROF[(cur.id, a.id)].id))

# Otro colegio con NOMBRES IGUALES: «Ricardo Sintético» en «5to A Vespertina» y «Matutina».
col2, ano2 = montar_colegio('Colegio Sintético TRAS', 'SOTRO')
g5b = add(M.Grado(colegio_id=col2.id, nombre='5to Secundaria', nivel='secundaria', orden=5, activo=True))
tmb = add(M.Tanda(colegio_id=col2.id, nombre='Matutina', activo=True))
tvb = add(M.Tanda(colegio_id=col2.id, nombre='Vespertina', activo=True))
VB = add(M.Curso(colegio_id=col2.id, nombre='A', grado_id=g5b.id, tanda_id=tvb.id, ano_escolar_id=ano2.id, activo=True))
MB = add(M.Curso(colegio_id=col2.id, nombre='A', grado_id=g5b.id, tanda_id=tmb.id, ano_escolar_id=ano2.id, activo=True))
dir2 = usuario('dir2', 'direccion', 'Dir2', colegio=col2)
# Conflictos heredados: una marca DESPUÉS del retiro de cada retirado antiguo.
for e, cur, d in ((M21, MA, dt.date(2026, 9, 15)), (S6, D2, dt.date(2026, 10, 5))):
    add(M.Asistencia(colegio_id=col.id, estudiante_id=e.id, curso_id=cur.id, asignatura_id=art.id,
                     fecha=d, estado='presente', registrado_por=PROF[(cur.id, art.id)].id))
RIC2 = estudiante('Ricardo', 'Sintético', VB, 15, colegio=col2)
CONC = [estudiante('Conc%02d' % n, 'Sintético', VB, n, colegio=col2) for n in (1, 2, 3)]
for n in range(1, 4):
    estudiante('Mb%02d' % n, 'Sintético', MB, n, colegio=col2)
db.commit()
NC = {cid: db.get(M.Curso, cid).nombre_completo for cid in (V.id, MA.id, D2.id)}
CORTO = {cid: APP._nombre_corto_curso(db.get(M.Curso, cid)) for cid in (V.id, MA.id, D2.id)}


# ─────────────────────────── MEDICIONES ───────────────────────────
def huella_global():
    """Identificadores y valores de TODAS las notas y asistencias existentes."""
    db.expire_all()
    asis = {a.id: (a.estudiante_id, a.curso_id, a.asignatura_id, a.fecha.isoformat(), a.estado,
                   a.registrado_por, a.observacion) for a in db.query(M.Asistencia)}
    cal = {x.id: (x.estudiante_id, x.asignatura_id, x.competencia_numero, x.ano_escolar_id,
                  x.p1, x.p2, x.p3, x.p4, x.rp1, x.rp2, x.rp3, x.rp4) for x in db.query(M.CalificacionSecundaria)}
    return {'asistencias': asis, 'calificaciones': cal}


def comparar_originales(antes, despues):
    """(cambiadas, desaparecidas) entre las filas que ya existían.

    En una nota, completar un campo que estaba VACÍO (el destino sigue
    evaluando: P2-P4) no es cambiar lo existente; cambiar o borrar un valor
    que ya había, sí.
    """
    cambios, faltan = [], []
    for tabla in ('asistencias', 'calificaciones'):
        for k, v in antes[tabla].items():
            if k not in despues[tabla]:
                faltan.append((tabla, k))
            elif despues[tabla][k] != v:
                d = despues[tabla][k]
                if tabla == 'calificaciones' and all(a_ is None or a_ == b_ for a_, b_ in zip(v, d)):
                    continue
                cambios.append((tabla, k, v, d))
    return cambios, faltan


def h(x):
    return hashlib.sha256(json.dumps(x, default=str, sort_keys=True).encode()).hexdigest()[:12]


def resultados_sin_movimiento(estudiantes):
    """Asistencia canónica y boletín (JSON) de estudiantes SIN movimientos."""
    out = {}
    for e in estudiantes:
        js = c.get('/api/boletines/estudiante/%d' % e.id, headers=H(dire)).json()
        out[e.id] = h({'asistencia_anual': js.get('asistencia_anual'),
                       'asistencias': js.get('asistencias'),
                       'asignaturas': js.get('asignaturas'),
                       'situacion': js.get('situacion') or js.get('condicion_final')})
    return out


def lista(curso, fecha, asig):
    js = c.get('/api/asistencia/curso/%d?fecha=%s&asignatura_id=%d' % (curso.id, fecha, asig.id),
               headers=H(dire)).json()
    return {x['estudiante']['id']: x for x in js.get('asistencias', [])}


def _get_crudo(url, headers):
    import asyncio
    import httpx

    async def _g():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=APP.app), base_url='http://t',
                                     timeout=600) as cl:
            return await cl.get(url, headers=headers)
    return asyncio.run(_g())


def pdf(url, nombre=None, usuario=None):
    r = _get_crudo(url, H(usuario or dire))
    if r.status_code != 200 or r.content[:4] != b'%PDF':
        return r.status_code, None, r.text[:1500]
    if nombre:
        open(os.path.join(OUT, nombre), 'wb').write(r.content)
    doc = pymupdf.open(stream=r.content, filetype='pdf')
    return 200, r.content, '\n'.join(p.get_text() for p in doc)


def post(url, usuario, body):
    r = c.post(url, headers=H(usuario), json=body)
    try:
        js = r.json()
    except Exception:
        js = {'_texto': r.text[:300]}
    return r.status_code, js


BASE = huella_global()
SIN_MOV = [e for e in EV + EM + E2 if e not in (RIC, ABR, HIL)]
RES_SIN_MOV_ANTES = resultados_sin_movimiento(SIN_MOV[:6] + [EV[0], EM[0]])
DATOS['filas_iniciales'] = {'asistencias': len(BASE['asistencias']), 'calificaciones': len(BASE['calificaciones'])}

# ═══════════════════ A. PREPARAR EL TRASLADO (solo lectura) ═══════════════════
print('\n== A. Preparar el traslado ==')
r = c.get('/api/estudiantes/%d/movimiento/preparar?tipo=traslado&curso_destino_id=%d&desde=2026-10-21'
          % (RIC.id, MA.id), headers=H(dire))
prep = r.json()
DATOS['A_preparar'] = prep
check('A1 preparar responde 200 y no escribe nada', r.status_code == 200 and huella_global() == BASE, r.text[:300])
check('A2 número propuesto = siguiente al mayor ocupado, contando retirados (20 activos + n.º 21 retirado -> 22)',
      (prep.get('destino') or {}).get('numero_propuesto') == 22, prep.get('destino'))
check('A3 referencias de asistencia: última marca en origen 20/10, sin deducir fecha',
      (prep.get('referencias_asistencia') or {}).get('origen', {}).get('ultima') == '2026-10-20'
      and 'no deduce' in (prep.get('referencias_asistencia') or {}).get('nota', ''), prep.get('referencias_asistencia'))
asig_cmp = prep.get('asignaturas') or {}
check('A4 asignaturas distintas detectadas sin equivalencias (Música y optativa V solo origen; optativa M solo destino)',
      {a['nombre'] for a in asig_cmp.get('solo_origen', [])} == {'Música', 'Optativa HLM (Vespertina)'}
      and {a['nombre'] for a in asig_cmp.get('solo_destino', [])} == {'Optativa HCS (Matutina)'}, asig_cmp)
check('A5 sin conflictos con la fecha 21/10 (su última marca es el 20/10)', prep.get('conflictos') == [], prep.get('conflictos'))
r = c.get('/api/estudiantes/%d/movimiento/preparar?tipo=traslado&curso_destino_id=%d&desde=2026-10-14'
          % (RIC.id, MA.id), headers=H(dire)).json()
check('A6 con una fecha anterior (14/10) lista las marcas del origen que la contradicen',
      len(r.get('conflictos') or []) > 0 and all(x['curso_id'] == V.id for x in r['conflictos']), r.get('conflictos'))

# ═══════════════════ B. VALIDACIONES QUE NO ESCRIBEN ═══════════════════
print('\n== B. Validaciones ==')
st, js = post('/api/estudiantes/%d/traslado' % RIC.id, dire, {'curso_destino_id': MA.id, 'desde': '2026-10-21', 'no_lista': 20})
check('B1 número ocupado (20 de Abraham) -> 409 con propuesta', st == 409 and js.get('error') == 'NUMERO_OCUPADO'
      and js.get('numero_propuesto') == 22, js)
st, js = post('/api/estudiantes/%d/traslado' % RIC.id, dire, {'curso_destino_id': MA.id, 'desde': '2026-10-21', 'no_lista': 21})
check('B2 número de un retirado (21) -> 409', st == 409 and js.get('error') == 'NUMERO_OCUPADO', js)
st, js = post('/api/estudiantes/%d/traslado' % RIC.id, dire, {'curso_destino_id': MA.id, 'desde': '2026-10-14'})
check('B3 fecha contradicha por marcas -> 409 con la lista y una fecha coherente (21/10), sin borrar ni corregir',
      st == 409 and js.get('error') == 'CONFLICTOS_CON_LA_FECHA' and len(js.get('conflictos') or []) > 0
      and js.get('fecha_sugerida') == '2026-10-21', (js.get('error'), js.get('fecha_sugerida')))
st, js = post('/api/estudiantes/%d/traslado' % RIC.id, dire, {'curso_destino_id': MA.id, 'desde': '2026-10-14',
                                                              'confirmar_conflictos': True})
check('B3b no existe forma de «confirmar» una fecha contradictoria (el parámetro antiguo no la fuerza)',
      st == 409 and js.get('error') == 'CONFLICTOS_CON_LA_FECHA', js.get('error'))
st, js = post('/api/estudiantes/%d/traslado' % RIC.id, dire, {'curso_destino_id': C4.id, 'desde': '2026-10-21'})
check('B4 cambio de grado -> 409 (decisión académica)', st == 409 and js.get('error') == 'CAMBIO_DE_GRADO_NO_DISPONIBLE', js)
st, js = post('/api/estudiantes/%d/traslado' % RIC.id, dire, {'curso_destino_id': MA.id, 'desde': '2027-08-01'})
check('B5 fecha fuera del año -> 400', st == 400 and js.get('error') == 'FECHA_FUERA_DEL_ANO', js)
st, js = post('/api/estudiantes/%d/traslado' % RIC.id, secre, {'curso_destino_id': MA.id, 'desde': '2026-10-21'})
check('B6 Secretaría con historia -> 409 (lo registra Dirección)', st == 409 and js.get('error') == 'CAMBIO_CURSO_REQUIERE_DIRECCION', js)
st, js = post('/api/estudiantes/%d/traslado' % RIC.id, dir2, {'curso_destino_id': MA.id, 'desde': '2026-10-21'})
check('B7 Dirección de OTRO colegio -> 404', st == 404, (st, js))
st, js = post('/api/estudiantes/%d/traslado' % RIC2.id, dir2, {'curso_destino_id': MA.id, 'desde': '2026-10-21'})
check('B8 mezclar colegios (destino de otro colegio) -> 404', st == 404, (st, js))
r = c.put('/api/estudiantes/%d' % RIC.id, headers=H(dire), json={'curso_id': MA.id, 'no_lista': 22})
check('B9 editar la ficha no cambia de curso a quien tiene historia -> 409', r.status_code == 409
      and r.json().get('error') == 'CAMBIO_DE_CURSO_REQUIERE_TRASLADO', r.text[:200])
r = c.put('/api/estudiantes/%d' % RIC.id, headers=H(dire), json={'condicion': 'retirado'})
check('B10 editar la ficha no retira -> 409', r.status_code == 409 and r.json().get('error') == 'RETIRO_REQUIERE_ACCION', r.text[:200])
check('B11 ninguna validación escribió nada', huella_global() == BASE
      and db.query(M.MovimientoEstudiante).count() == 0)

# ═══════════════════ C. TRASLADO V -> M ═══════════════════
print('\n== C. Traslado de Ricardo (5to A Vespertina -> 5to A Matutina) desde 21/10 ==')
st, js = post('/api/estudiantes/%d/traslado' % RIC.id, dire,
              {'curso_destino_id': MA.id, 'desde': '2026-10-21', 'motivo': 'Cambio de tanda (sintético)',
               'client_request_id': 'tras-ric-1'})
DATOS['C_traslado'] = js
db.expire_all()
ric = db.get(M.Estudiante, RIC.id)
check('C1 traslado 200: misma ficha, curso destino y n.º 22', st == 200 and ric.curso_id == MA.id and ric.no_lista == 22
      and ric.id == RIC.id, (st, js))
mov = db.query(M.MovimientoEstudiante).filter_by(estudiante_id=RIC.id).one()
check('C2 movimiento con autor, momento, fecha efectiva, origen y destino', mov.registrado_por == dire.id
      and mov.registrado_en is not None and mov.fecha_efectiva == F_TRAS and mov.curso_origen_id == V.id
      and mov.no_lista_origen == 15 and mov.curso_destino_id == MA.id and mov.no_lista_destino == 22)
res = {(r_.curso_id, r_.no_lista) for r_ in db.query(M.ReservaNumeroLista).filter_by(estudiante_id=RIC.id)}
check('C3 número de origen (V, 15) reservado y destino (M, 22) reservado', res == {(V.id, 15), (MA.id, 22)}, res)
cambios, faltan = comparar_originales(BASE, huella_global())
check('C4 ninguna nota ni asistencia original cambió ni desapareció', not cambios and not faltan, (cambios[:3], faltan[:3]))
check('C5 no se creó ninguna ficha nueva', db.query(M.Estudiante).filter_by(nombre='Ricardo', colegio_id=col.id).count() == 1)
aud = [a for a in db.query(M.LogAuditoria).filter_by(registro_id=RIC.id) if a.accion == 'trasladar']
check('C6 auditoría «trasladar» con el movimiento', len(aud) == 1 and 'movimiento_id' in (aud[0].datos_nuevos or ''), len(aud))
snap = mov.get_detalle().get('notas_previas', {}).get('secundaria', {})
check('C7 instantánea de las notas existentes (incluida la RP de Artística)', any(
    v['asignatura_id'] == art.id and v['competencia'] == 1 and v['valores'].get('rp1') == 75 for v in snap.values()), len(snap))

# Reintento, doble clic y concurrencia.
# Un reintento (doble clic, red) reenvía EXACTAMENTE el mismo cuerpo; con
# otro contenido es 409 SOLICITUD_REPETIDA_DISTINTA (test_retiros_traslados_auditoria R1).
st2, js2 = post('/api/estudiantes/%d/traslado' % RIC.id, dire,
                {'curso_destino_id': MA.id, 'desde': '2026-10-21', 'motivo': 'Cambio de tanda (sintético)',
                 'client_request_id': 'tras-ric-1'})
check('C8 reintento con la misma solicitud -> mismo movimiento, sin duplicar', st2 == 200 and js2.get('reintento')
      and js2['movimiento']['id'] == mov.id and db.query(M.MovimientoEstudiante).count() == 1, js2)
st3, js3 = post('/api/estudiantes/%d/traslado' % RIC.id, dire, {'curso_destino_id': MA.id, 'desde': '2026-10-21'})
check('C9 segundo envío (otra solicitud) -> 409 ya está en ese curso', st3 == 409 and js3.get('error') == 'YA_EN_ESE_CURSO', js3)
# Concurrencia (en el OTRO colegio, para no alterar los cursos de las muestras):
# dos traslados simultáneos de DOS estudiantes al mismo curso sin número elegido,
# y dos simultáneos del MISMO estudiante.
codigos = []
HD2 = H(dir2)          # el token se arma en el hilo principal (la sesión no se comparte)
ID_MB = MB.id


def _tras(est_id, crid):
    try:
        cl = TestClient(APP.app)
        r_ = cl.post('/api/estudiantes/%d/traslado' % est_id, headers=HD2,
                     json={'curso_destino_id': ID_MB, 'desde': '2026-10-28', 'client_request_id': crid})
        codigos.append((est_id, r_.status_code, (r_.json() or {}).get('error')))
    except Exception as exc:     # se registra: un hilo que falla no puede pasar por éxito
        codigos.append((est_id, 'excepcion', repr(exc)[:300]))


ID_CONC = [e.id for e in CONC]
hs = [threading.Thread(target=_tras, args=(ID_CONC[0], 'conc-a')), threading.Thread(target=_tras, args=(ID_CONC[1], 'conc-b'))]
[t.start() for t in hs]
[t.join() for t in hs]
db.expire_all()
nums = [e.no_lista for e in db.query(M.Estudiante).filter_by(curso_id=MB.id)]
check('C10 dos traslados simultáneos al mismo curso: nunca el mismo número a dos estudiantes',
      len(nums) == len(set(nums)) and any(c_[1] == 200 for c_ in codigos), (codigos, sorted(nums)))
DATOS['C10_concurrencia'] = list(codigos)
codigos.clear()
hs = [threading.Thread(target=_tras, args=(ID_CONC[2], 'mismo-1')), threading.Thread(target=_tras, args=(ID_CONC[2], 'mismo-2'))]
[t.start() for t in hs]
[t.join() for t in hs]
db.expire_all()
check('C11 dos movimientos simultáneos del MISMO estudiante: entra uno solo',
      db.query(M.MovimientoEstudiante).filter_by(estudiante_id=ID_CONC[2]).count() == 1
      and all(c_[1] in (200, 409) for c_ in codigos), codigos)
DATOS['C11_concurrencia'] = list(codigos)
# CARRERA FORZADA: una barrera obliga a las DOS peticiones a terminar la
# validación (números ocupados) antes de que ninguna escriba. Así se prueba la
# barrera física de la base (reserva única por curso y número; secuencia única
# por estudiante y relectura tras el bloqueo), no la suerte del planificador.
_orig_ocupados = PERM.numeros_ocupados
_barrera = threading.Barrier(2, timeout=20)


def _ocupados_con_barrera(*a, **k):
    r_ = _orig_ocupados(*a, **k)
    try:
        _barrera.wait()
    except threading.BrokenBarrierError:
        pass
    return r_


extra = [estudiante('Carr%02d' % n, 'Sintético', VB, 10 + n, colegio=col2) for n in (1, 2, 3)]
db.commit()
ID_EXTRA = [e.id for e in extra]
PERM.numeros_ocupados = _ocupados_con_barrera
try:
    codigos.clear()
    hs = [threading.Thread(target=_tras, args=(ID_EXTRA[0], 'carr-a')),
          threading.Thread(target=_tras, args=(ID_EXTRA[1], 'carr-b'))]
    [t.start() for t in hs]
    [t.join() for t in hs]
    DATOS['C10b_carrera_forzada'] = list(codigos)
    db.expire_all()
    nums = [e.no_lista for e in db.query(M.Estudiante).filter_by(curso_id=MB.id)]
    check('C10b carrera FORZADA de dos traslados al mismo curso: entra uno, el otro 409 NUMERO_OCUPADO; '
          'ningún número repetido', sorted(c_[1] for c_ in codigos) == [200, 409]
          and any(c_[2] == 'NUMERO_OCUPADO' for c_ in codigos) and len(nums) == len(set(nums)), (codigos, sorted(nums)))
    _barrera.reset()
    codigos.clear()
    hs = [threading.Thread(target=_tras, args=(ID_EXTRA[2], 'carr-c')),
          threading.Thread(target=_tras, args=(ID_EXTRA[2], 'carr-d'))]
    [t.start() for t in hs]
    [t.join() for t in hs]
    DATOS['C11b_carrera_forzada'] = list(codigos)
    db.expire_all()
    check('C11b carrera FORZADA del MISMO estudiante: un solo movimiento; el otro 409',
          db.query(M.MovimientoEstudiante).filter_by(estudiante_id=ID_EXTRA[2]).count() == 1
          and sorted(c_[1] for c_ in codigos) == [200, 409], codigos)
finally:
    PERM.numeros_ocupados = _orig_ocupados
for e in CONC:
    db.expire_all()
    if db.get(M.Estudiante, e.id).curso_id == MB.id:
        st_, js_ = post('/api/estudiantes/%d/traslado' % e.id, dir2, {'curso_destino_id': VB.id, 'desde': '2026-10-29'})
        check('C12 regreso a su curso recupera su número (%s)' % e.nombre, st_ == 200
              and db.get(M.Estudiante, e.id).no_lista == e.no_lista, (st_, js_))

# ═══════════════════ D. PASE DE LISTA POR HORARIO ═══════════════════
print('\n== D. Pase de lista ==')
lv14 = lista(V, '2026-10-14', art)        # miércoles: EA en la tarde
lv26 = lista(V, '2026-10-26', art)        # lunes, después del traslado
lm15 = lista(MA, '2026-10-15', art)       # jueves: EA en la mañana, antes del traslado
lm22 = lista(MA, '2026-10-22', art)       # jueves, después
check('D1 origen 14/10: aparece con su n.º 15 y su marca de la tarde', RIC.id in lv14 and lv14[RIC.id]['estudiante']['no_lista'] == 15
      and lv14[RIC.id]['estudiante']['aplica'] and (lv14[RIC.id]['asistencia'] or {}).get('estado') == 'presente', lv14.get(RIC.id))
check('D2 origen 26/10: «No aplica» y aviso «Trasladado a <destino> desde 21/10/2026»',
      RIC.id in lv26 and not lv26[RIC.id]['estudiante']['aplica']
      and any('Trasladado a %s desde 21/10/2026' % NC[MA.id] in a for a in lv26[RIC.id]['estudiante']['avisos']),
      lv26.get(RIC.id))
check('D3 destino 15/10: «No aplica», aviso «Incorporado desde 21/10/2026» y SIN la marca de la tarde',
      RIC.id in lm15 and not lm15[RIC.id]['estudiante']['aplica'] and lm15[RIC.id]['asistencia'] is None
      and any('Incorporado desde 21/10/2026' in a for a in lm15[RIC.id]['estudiante']['avisos']), lm15.get(RIC.id))
check('D4 destino 22/10: aplica, con su n.º 22', RIC.id in lm22 and lm22[RIC.id]['estudiante']['aplica']
      and lm22[RIC.id]['estudiante']['no_lista'] == 22, lm22.get(RIC.id))
pm_art, pv_art = PROF[(MA.id, art.id)], PROF[(V.id, art.id)]
st, js = post('/api/asistencia', pm_art, {'estudiante_id': RIC.id, 'curso_id': MA.id, 'asignatura_id': art.id,
                                          'fecha': '2026-10-15', 'estado': 'ausente'})
check('D5 el destino no carga días anteriores al traslado -> 409 fuera de permanencia', st == 409
      and js.get('error') == 'FUERA_DE_PERMANENCIA', js)
st, js = post('/api/asistencia', pm_art, {'estudiante_id': RIC.id, 'curso_id': MA.id, 'asignatura_id': art.id,
                                          'fecha': '2026-10-14', 'estado': 'ausente'})
check('D6 el destino no sobrescribe la marca de la tarde (14/10) -> rechazado', st in (409, 403), js)
r = c.delete('/api/asistencia/%d?fecha=2026-10-14&asignatura_id=%d' % (RIC.id, art.id), headers=H(pm_art))
check('D7 el destino no puede borrar la marca de la tarde', r.status_code in (403, 409), r.text[:200])
# El destino pasa lista desde el 21-oct con SU horario (EA martes y jueves).
cods = [post('/api/asistencia', pm_art, {'estudiante_id': RIC.id, 'curso_id': MA.id, 'asignatura_id': art.id,
                                         'fecha': d.isoformat(), 'estado': 'presente'})[0]
        for d in dias(F_TRAS, HOY, HORARIO[(MA.id, art.id)])]
for a in (fihr, optM):
    for d in dias(F_TRAS, HOY, HORARIO[(MA.id, a.id)]):
        cods.append(post('/api/asistencia', PROF[(MA.id, a.id)], {'estudiante_id': RIC.id, 'curso_id': MA.id,
                         'asignatura_id': a.id, 'fecha': d.isoformat(), 'estado': 'presente'})[0])
db.expire_all()
nuevas = db.query(M.Asistencia).filter(M.Asistencia.estudiante_id == RIC.id, M.Asistencia.fecha >= F_TRAS).all()
check('D8 el destino registra desde el 21/10 con su horario y su curso', cods and all(x == 200 for x in cods)
      and nuevas and all(a.curso_id == MA.id for a in nuevas), cods)
# El origen corrige un día suyo (14/10, P -> E) aunque el estudiante ya no esté.
st, js = post('/api/asistencia', pv_art, {'estudiante_id': RIC.id, 'curso_id': V.id, 'asignatura_id': art.id,
                                          'fecha': '2026-10-14', 'estado': 'excusa'})
db.expire_all()
fila14 = db.query(M.Asistencia).filter_by(estudiante_id=RIC.id, fecha=dt.date(2026, 10, 14), asignatura_id=art.id).one()
check('D9 el origen corrige su día 14/10: conserva curso, autor original; queda auditado',
      st == 200 and fila14.curso_id == V.id and fila14.registrado_por == pv_art.id and fila14.estado == 'excusa'
      and db.query(M.LogAuditoria).filter_by(accion='corregir_asistencia_historica', registro_id=fila14.id).count() == 1, js)
st, js = post('/api/asistencia', pv_art, {'estudiante_id': RIC.id, 'curso_id': V.id, 'asignatura_id': art.id,
                                          'fecha': '2026-10-26', 'estado': 'presente'})
check('D10 el origen no carga días posteriores al traslado -> 409', st == 409 and js.get('error') == 'FUERA_DE_PERMANENCIA', js)
# Lote del destino («marcar todos») con quien no pertenece ese día.
st, js = post('/api/asistencia/masivo', pm_art, {'fecha': '2026-10-15', 'asignatura_id': art.id, 'curso_id': MA.id,
                                                 'asistencias': [{'estudiante_id': RIC.id, 'estado': 'presente'}]})
check('D11 el lote no marca a quien no pertenecía ese día -> 409', st == 409, js)
st, js = post('/api/asistencia/masivo', pm_art, {'fecha': '2026-10-22', 'asignatura_id': art.id, 'curso_id': MA.id,
                                                 'asistencias': [{'estudiante_id': RIC.id, 'estado': 'presente'},
                                                                 {'estudiante_id': EM[0].id, 'estado': 'presente'}]})
check('D12 el lote del destino el 22/10 funciona', st == 200, js)
# Restaurar la marca corregida del 14/10 al valor original para comparar originales.
post('/api/asistencia', pv_art, {'estudiante_id': RIC.id, 'curso_id': V.id, 'asignatura_id': art.id,
                                 'fecha': '2026-10-14', 'estado': 'presente'})

# ═══════════════════ E. NOTAS Y RECUPERACIONES ═══════════════════
print('\n== E. Notas ==')
st, js = post('/api/calificaciones-secundaria', pm_art, {'estudiante_id': RIC.id, 'asignatura_id': art.id,
                                                         'competencia_numero': 1, 'p1': 99})
check('E1 el destino no sobrescribe una nota previa al traslado -> 409 explicado', st == 409
      and js.get('error') == 'NOTA_PREVIA_AL_TRASLADO', js)
st, js = post('/api/calificaciones-secundaria', pm_art, {'estudiante_id': RIC.id, 'asignatura_id': art.id,
                                                         'competencia_numero': 1, 'rp1': 90})
check('E2 tampoco la recuperación previa (RP1) -> 409', st == 409, js)
st, js = post('/api/calificaciones-secundaria', pv_art, {'estudiante_id': RIC.id, 'asignatura_id': art.id,
                                                         'competencia_numero': 1, 'p1': 61})
check('E3 el origen sin permiso no corrige -> 403', st == 403 and js.get('error') == 'NOTA_DE_CURSO_ANTERIOR', js)
# Dirección concede el permiso temporal EXISTENTE (sin cerrar el período).
perm = add(M.PermisoTemporalCalificacion(colegio_id=col.id, profesor_id=pv_art.id, curso_id=V.id,
                                         asignatura_id=art.id, periodo=1, motivo='Corrección sintética',
                                         fecha_fin=dt.datetime.now() + dt.timedelta(days=2), otorgado_por=dire.id,
                                         activo=True))
db.commit()
st, js = post('/api/calificaciones-secundaria', pv_art, {'estudiante_id': RIC.id, 'asignatura_id': art.id,
                                                         'competencia_numero': 1, 'p1': 62})
db.expire_all()
c1 = db.query(M.CalificacionSecundaria).filter_by(estudiante_id=RIC.id, asignatura_id=art.id, competencia_numero=1).one()
aud = [a for a in db.query(M.LogAuditoria).filter_by(accion='GUARDAR_NOTA_SECUNDARIA', registro_id=c1.id)]
check('E4 con el permiso (curso de origen, asignatura, P1) el origen corrige; auditado con el permiso; P1 abierto',
      st == 200 and c1.p1 == 62 and c1.rp1 == 75 and aud and '_permiso_correccion' in (aud[-1].datos_nuevos or '')
      and not ano.p1_cerrado, js)
post('/api/calificaciones-secundaria', pv_art, {'estudiante_id': RIC.id, 'asignatura_id': art.id,
                                                'competencia_numero': 1, 'p1': 60})   # restaurar
# El destino COMPLETA lo vacío (P2-P4) y sigue evaluando.
cods = []
for a in (art, fihr):
    for comp in (1, 2, 3, 4):
        cods.append(post('/api/calificaciones-secundaria', PROF[(MA.id, a.id)],
                         {'estudiante_id': RIC.id, 'asignatura_id': a.id, 'competencia_numero': comp,
                          'p2': 80, 'p3': 81, 'p4': 82})[0])
check('E5 el destino completa P2-P4 vacíos sin permiso', all(x == 200 for x in cods), cods)
pl = c.get('/api/calificaciones-secundaria/curso/%d/asignatura/%d' % (MA.id, art.id), headers=H(pm_art)).json()
fr = next(x for x in pl['calificaciones'] if x['estudiante']['id'] == RIC.id)
check('E6 planilla del destino: procedencia de las notas previas (P1 y RP1 protegidas) y aviso',
      'p1' in fr['permanencia']['notas_previas_traslado'].get('1', []) and 'rp1' in fr['permanencia']['notas_previas_traslado'].get('1', [])
      and any('Incorporado' in a for a in fr['permanencia']['avisos']), fr['permanencia'])
pl = c.get('/api/calificaciones-secundaria/curso/%d/asignatura/%d' % (V.id, art.id), headers=H(pv_art)).json()
fr = next((x for x in pl['calificaciones'] if x['estudiante']['id'] == RIC.id), None)
check('E7 planilla del origen: lo conserva en solo lectura con su n.º 15 y el aviso', fr is not None
      and fr['permanencia']['solo_lectura'] and fr['estudiante']['no_lista'] == 15, fr and fr['permanencia'])
check('E7b en el ORIGEN: solo los períodos que cursó allí (P1), sin promedio ni calificación final',
      fr is not None and fr['competencias']['1']['p1'] == 60 and fr['competencias']['1']['p2'] is None
      and fr['competencias']['1']['promedio_competencia'] is None and fr['cf'] is None,
      fr and (fr['competencias'].get('1'), fr['cf']))
pl_d = c.get('/api/calificaciones-secundaria/curso/%d/asignatura/%d' % (MA.id, art.id), headers=H(pm_art)).json()
fr_d = next(x for x in pl_d['calificaciones'] if x['estudiante']['id'] == RIC.id)
check('E7c en el DESTINO sigue y obtiene su resultado: todas sus notas (P1 con RP y P2-P4) y su CF',
      not fr_d['permanencia']['solo_lectura'] and fr_d['competencias']['1']['p1'] == 60
      and fr_d['competencias']['1']['rp1'] == 75 and fr_d['competencias']['1']['p4'] == 82 and fr_d['cf'] is not None,
      (fr_d['competencias'].get('1'), fr_d['cf']))
db.expire_all()
check('E7d las notas siguen intactas en la base (P2-P4 cargadas en el destino no se pierden por ocultarse en el origen)',
      db.query(M.CalificacionSecundaria).filter_by(estudiante_id=RIC.id, asignatura_id=art.id, competencia_numero=1).one().p2 == 80)
# Asignaturas distintas: las notas de Música/optativa V siguen en su asignatura; la optativa M
# no tiene notas de Ricardo (no se asumen equivalencias).
db.expire_all()
n_opm = db.query(M.CalificacionSecundaria).filter_by(estudiante_id=RIC.id, asignatura_id=optM.id).count()
n_opv = db.query(M.CalificacionSecundaria).filter_by(estudiante_id=RIC.id, asignatura_id=optV.id).count()
check('E8 asignaturas distintas: ninguna nota movida ni copiada (optativa V: 4, optativa M: 0)', n_opv == 4 and n_opm == 0,
      (n_opv, n_opm))

# ═══════════════════ F. RETIRO DE ABRAHAM: AUDITORÍA DE FECHAS ═══════════════════
print('\n== F. Retiro de Abraham: una fecha contradictoria se rechaza ==')


def marcas_de(est_id):
    db.expire_all()
    return {a.id: (a.fecha.isoformat(), NOMBRE.get(a.curso_id, a.curso_id), a.asignatura_id, a.estado,
                   a.registrado_por) for a in db.query(M.Asistencia).filter_by(estudiante_id=est_id)}


def dias_contados(est_id):
    """Días que la asistencia canónica (boletín, A2, Registro) CUENTA para él."""
    js_ = c.get('/api/boletines/estudiante/%d' % est_id, headers=H(dire)).json()
    return js_.get('asistencia_anual') or {}


antes_abr = marcas_de(ABR.id)
cont_antes = dias_contados(ABR.id)
st, js = post('/api/estudiantes/%d/retiro' % ABR.id, dire, {'desde': '2026-10-10', 'motivo': 'Retiro sintético'})
conf = js.get('conflictos') or []
check('F1 retiro desde 10/10 contradice 7 marcas posteriores -> 409 con la lista y fecha sugerida 21/10',
      st == 409 and len(conf) == 7 and js.get('fecha_sugerida') == '2026-10-21', (st, len(conf), js.get('fecha_sugerida')))
despues_rechazo = marcas_de(ABR.id)
db.expire_all()
check('F1b el rechazo no tocó nada: ficha activa, mismas marcas, mismo conteo',
      db.get(M.Estudiante, ABR.id).activo and despues_rechazo == antes_abr and dias_contados(ABR.id) == cont_antes)
st, js = post('/api/estudiantes/%d/retiro' % ABR.id, dire, {'desde': '2026-10-21', 'motivo': 'Retiro sintético'})
db.expire_all()
abr = db.get(M.Estudiante, ABR.id)
cont_desp = dias_contados(ABR.id)
check('F2 retiro desde la fecha coherente (21/10): último día 20/10, conserva curso y n.º 20; sin fila de '
      'movimiento (primer retiro sin trayectoria: queda en la ficha, como siempre)',
      st == 200 and not abr.activo and abr.fecha_retiro == dt.date(2026, 10, 20) and abr.curso_id == MA.id
      and abr.no_lista == 20 and db.query(M.MovimientoEstudiante).filter_by(estudiante_id=ABR.id).count() == 0, js)
check('F2b todas sus marcas siguen y TODAS siguen contando (ninguna queda fuera ni se excluye en silencio)',
      marcas_de(ABR.id) == antes_abr
      and cont_desp.get('dias_computados') == len({v[0] for v in antes_abr.values()}),
      (cont_desp.get('dias_computados'), len({v[0] for v in antes_abr.values()})))
# Auditoría marca por marca de las 7 que contradecían la primera fecha.
DATOS['F_auditoria_fechas'] = [{
    'asistencia_id': x['asistencia_id'], 'fecha': x['fecha'], 'curso': x['curso'], 'asignatura': x['asignatura'],
    'estado': x['estado'],
    'antes': antes_abr[x['asistencia_id']],
    'tras_intento_rechazado_10oct': despues_rechazo.get(x['asistencia_id']),
    'tras_retiro_21oct': marcas_de(ABR.id).get(x['asistencia_id']),
    'cuenta_en_su_asistencia_tras_retiro': x['fecha'] <= (cont_desp.get('fin') or ''),
} for x in conf]
check('F2c cada una de las 7 marcas: igual antes, tras el rechazo y tras el retiro, y sigue contando',
      all(d_['antes'] == d_['tras_intento_rechazado_10oct'] == d_['tras_retiro_21oct']
          and d_['cuenta_en_su_asistencia_tras_retiro'] for d_ in DATOS['F_auditoria_fechas']))
st, js = post('/api/asistencia', pm_art, {'estudiante_id': ABR.id, 'curso_id': MA.id, 'asignatura_id': art.id,
                                          'fecha': '2026-10-27', 'estado': 'ausente'})
check('F3 no se acumulan cargas después del retiro -> 403 (el contrato de siempre para un retirado)',
      st == 403, js)
st, js = post('/api/asistencia', pm_art, {'estudiante_id': ABR.id, 'curso_id': MA.id, 'asignatura_id': art.id,
                                          'fecha': '2026-10-08', 'estado': 'presente'})
check('F4 corrección histórica dentro de su permanencia: posible y auditada', st == 200, js)
check('F5 su asistencia anual termina el 20/10', cont_desp.get('fin') == '2026-10-20', cont_desp)
r = c.post('/api/estudiantes', headers=H(dire), json={'nombre': 'Nuevo', 'apellido': 'Sintético', 'curso_id': MA.id,
                                                       'no_lista': 20})
check('F6 su número (20) no se reutiliza para un alta nueva', r.status_code == 409, r.text[:200])
csv = 'nombre,apellido,no_lista\nOtro,Sintético,20\n'
r = c.post('/api/estudiantes/importar', headers=H(dire), data={'curso_id': str(MA.id), 'modo': 'preview'},
           files={'archivo': ('x.csv', csv.encode(), 'text/csv')})
check('F7 la importación tampoco reutiliza el número reservado', r.status_code == 200 and r.json().get('errores'), r.text[:300])
r = c.request('DELETE', '/api/estudiantes/%d' % ABR.id, headers=H(dire), json={'desde': '2026-10-21'})
check('F8 reintento del mismo retiro (doble clic): 200 idempotente, sin duplicar nada',
      r.status_code == 200 and r.json().get('reintento'), r.text[:200])

# ═══════════════════ G. HILLARY: RETIRO Y REACTIVACIÓN ═══════════════════
print('\n== G. Hillary: retiro desde 16/10 y reactivación desde 03/11 ==')
r = c.request('DELETE', '/api/estudiantes/%d' % HIL.id, headers=H(secre), json={'desde': '2026-10-16',
                                                                                 'motivo_retiro': 'Sintético'})
db.expire_all()
hil = db.get(M.Estudiante, HIL.id)
check('G1 Secretaría retira (acción de siempre, DELETE) con «desde»: último día 15/10', r.status_code == 200
      and hil.fecha_retiro == dt.date(2026, 10, 15) and not hil.activo, r.text[:300])
lv = lista(D2, '2026-10-19', art)
check('G2 pase de lista: «Retirado desde 16/10/2026», no aplica, conserva n.º 3', HIL.id in lv
      and not lv[HIL.id]['estudiante']['aplica'] and lv[HIL.id]['estudiante']['no_lista'] == 3
      and any('Retirado desde 16/10/2026' in a for a in lv[HIL.id]['estudiante']['avisos']), lv.get(HIL.id))
st, js = post('/api/asistencia', PROF[(D2.id, art.id)], {'estudiante_id': HIL.id, 'curso_id': D2.id,
                                                         'asignatura_id': art.id, 'fecha': '2026-10-19', 'estado': 'ausente'})
check('G2b no se carga asistencia mientras está retirada -> 403', st == 403, js)
r = c.post('/api/estudiantes/%d/reactivar' % HIL.id, headers=H(dire), json={'desde': '2026-11-03'})
db.expire_all()
hil = db.get(M.Estudiante, HIL.id)
movs = db.query(M.MovimientoEstudiante).filter_by(estudiante_id=HIL.id).order_by(M.MovimientoEstudiante.secuencia).all()
previo = movs[0].get_detalle().get('retiro_previo') if movs else {}
check('G3 reactivar no borra la historia: el retiro (fecha, motivo, autor) queda guardado en la reactivación; '
      'recupera su n.º 3', r.status_code == 200 and hil.activo and hil.no_lista == 3
      and [m.tipo for m in movs] == ['reactivacion'] and previo.get('fecha_retiro') == '2026-10-15'
      and previo.get('motivo_retiro') == 'Sintético' and previo.get('retirado_por') == secre.id, (r.text[:300], previo))
tr_h = PERM.construir_tramos(hil, movs)
check('G4 entre el retiro y la reactivación los días no aplican (ni ausencia ni esperados)',
      PERM.intervalos_sin_permanencia(tr_h) == [(dt.date(2026, 10, 16), dt.date(2026, 11, 2))],
      [(t.desde, t.hasta) for t in tr_h])
lv = lista(D2, '2026-11-04', art)
check('G5 tras reactivar: aplica de nuevo y aviso «Reincorporado desde 03/11/2026»', HIL.id in lv
      and lv[HIL.id]['estudiante']['aplica'] and any('Reincorporado desde 03/11/2026' in a for a in lv[HIL.id]['estudiante']['avisos']),
      lv.get(HIL.id))
cods = []
for a in (art, fihr):
    for d in dias(dt.date(2026, 11, 3), HOY, HORARIO[(D2.id, a.id)]):
        cods.append(post('/api/asistencia', PROF[(D2.id, a.id)], {'estudiante_id': HIL.id, 'curso_id': D2.id,
                         'asignatura_id': a.id, 'fecha': d.isoformat(), 'estado': 'presente'})[0])
check('G6 su docente pasa lista desde la reactivación', cods and all(x == 200 for x in cods), cods)
antes_s6 = marcas_de(S6.id)
st, js = post('/api/estudiantes/%d/reactivar' % S6.id, dire, {'desde': '2026-10-20'})
db.expire_all()
check('G7 reactivar a un retirado ANTIGUO con una marca en el hueco (05/10) -> 409 con fecha sugerida 05/10; '
      'sigue retirado y la marca intacta', st == 409 and js.get('error') == 'CONFLICTOS_CON_LA_FECHA'
      and js.get('fecha_sugerida') == '2026-10-05' and not db.get(M.Estudiante, S6.id).activo
      and marcas_de(S6.id) == antes_s6, (st, js.get('error'), js.get('fecha_sugerida')))

# ═══════════════════ H. NOTAS POR PERÍODO, RESÚMENES ═══════════════════
print('\n== H. Notas por Período y resúmenes ==')
js = c.get('/api/calificaciones/por-periodo?curso_id=%d&periodo=1' % V.id, headers=H(dire)).json()
fv = next((x for x in js.get('estudiantes', []) if x['estudiante_id'] == RIC.id), None)
check('H1 Notas por Período P1 del origen: incluye a Ricardo (n.º 15) con su aviso', fv is not None and fv['no_lista'] == 15
      and any('Trasladado' in a for a in fv.get('avisos', [])), fv)
js = c.get('/api/calificaciones/por-periodo?curso_id=%d&periodo=1' % MA.id, headers=H(dire)).json()
fm = next((x for x in js.get('estudiantes', []) if x['estudiante_id'] == RIC.id), None)
fa = next((x for x in js.get('estudiantes', []) if x['estudiante_id'] == ABR.id), None)
check('H2 Notas por Período P1 del destino: Ricardo (n.º 22, incorporado) y Abraham (retirado desde 21/10)',
      fm is not None and fm['no_lista'] == 22 and fa is not None
      and any('Retirado desde 21/10/2026' in a for a in fa.get('avisos', [])), (fm, fa))
js = c.get('/api/calificaciones/por-periodo?curso_id=%d&periodo=2' % V.id, headers=H(dire)).json()
check('H3 P2 del origen (posterior al traslado): Ricardo ya no aparece',
      not any(x['estudiante_id'] == RIC.id for x in js.get('estudiantes', [])))
st, _, txt = pdf('/api/calificaciones/por-periodo/pdf?curso_id=%d&periodo=1' % V.id, 'notas_periodo_P1_5toA_Vespertina.pdf')
check('H4 la tabla en PDF coincide con la pantalla (Ricardo con asterisco y su aviso)', st == 200 and 'Ricardo' in txt
      and ('Trasladado a %s desde 21/10/2026' % NC[MA.id]) in txt, txt[-600:] if txt else st)
js = c.get('/api/calificaciones-secundaria/curso/%d/periodo/1/competencias' % V.id, headers=H(dire)).json()
fc = next((x for x in js.get('estudiantes', []) if x['estudiante_id'] == RIC.id), None)
check('H4b la vista por competencia muestra la misma lista (Ricardo con su aviso)', fc is not None
      and any('Trasladado' in a for a in fc.get('avisos', [])), fc and fc.get('avisos'))
js = c.get('/api/asistencia/resumen/%d?mes=10&ano=2026' % V.id, headers=H(dire)).json()
fv = next((x for x in js if x['estudiante_id'] == RIC.id), None)
# El resumen mensual (código previo, sin cambios aquí) cuenta los días con alguna
# marca que no sea «ausente»: un día con solo ausencias no entra en su total. Se
# compara contra esa misma regla para aislar lo que cambia esta entrega.
db.expire_all()
_dias_v = {}
for a_ in db.query(M.Asistencia).filter(M.Asistencia.estudiante_id == RIC.id, M.Asistencia.curso_id == V.id,
                                        M.Asistencia.fecha >= dt.date(2026, 10, 1), M.Asistencia.fecha <= dt.date(2026, 10, 31)):
    _dias_v.setdefault(a_.fecha, set()).add(a_.estado)
_esperado = len([d for d, e_ in _dias_v.items() if e_ - {'ausente'}])
# Con el arreglo separado del resumen mensual (commit local 2052bab, otra rama),
# los días con solo ausencias también cuentan: se aceptan las dos reglas, porque
# lo que esta prueba mide es que solo entren sus marcas de la tarde hasta el 20/10.
_esperado_2052bab = len(_dias_v)
check('H5 resumen mensual del origen (octubre): solo sus marcas de la tarde hasta el 20/10',
      fv is not None and fv['total'] in (_esperado, _esperado_2052bab) and max(_dias_v) <= dt.date(2026, 10, 20),
      (fv, _esperado, _esperado_2052bab))
js = c.get('/api/asistencia/resumen/%d?mes=10&ano=2026' % MA.id, headers=H(dire)).json()
fm = next((x for x in js if x['estudiante_id'] == RIC.id), None)
check('H6 resumen mensual del destino (octubre): solo sus marcas de la mañana desde el 21/10',
      fm is not None and 0 < fm['total'] <= 9, fm)
js = c.get('/api/asistencia/vista-rapida/%d?fecha=2026-10-15' % MA.id, headers=H(dire)).json()
ses = (js.get('secundaria') or {}).get('sesiones') or []
ea = next((s_ for s_ in ses if s_['asignatura_id'] == art.id), {})
check('H7 vista rápida del destino 15/10: Ricardo no cuenta (aún no pertenecía); Abraham sí (estaba)',
      ea.get('total_estudiantes') == 20, ea)
js = c.get('/api/asistencia/resumen-periodos/curso/%d' % MA.id, headers=H(dire)).json()
check('H8 resumen por períodos del destino responde', isinstance(js, (list, dict)), str(js)[:200])

# ═══════════════════ K. REGRESO AL CURSO ORIGINAL, NÚMERO CON HUECO ═══════════════════
print('\n== K. Regreso al curso original y número libre con hueco ==')
st, js = post('/api/estudiantes/%d/traslado' % RIC.id, coord, {'curso_destino_id': V.id, 'desde': '2026-10-21'})
check('K1 deshacer con la misma fecha no se permite (no se reescribe historia) -> 400', st == 400
      and js.get('error') == 'FECHA_ANTERIOR_AL_TRAMO', js)
st, js = post('/api/estudiantes/%d/traslado' % RIC.id, coord, {'curso_destino_id': V.id, 'desde': '2026-11-09'})
db.expire_all()
ric = db.get(M.Estudiante, RIC.id)
tr = PERM.tramos_de(db, ric, ano.id)
check('K2 Coordinación lo devuelve a la tarde desde 09/11: recupera su n.º 15; tres tramos', st == 200
      and ric.curso_id == V.id and ric.no_lista == 15 and [(t.curso_id, t.no_lista) for t in tr]
      == [(V.id, 15), (MA.id, 22), (V.id, 15)], (st, js, [(t.curso_id, t.no_lista, t.desde, t.hasta) for t in tr]))
lm = lista(MA, '2026-10-27', art)
check('K3 el destino conserva su tramo (21/10-08/11) con su n.º 22', RIC.id in lm and lm[RIC.id]['estudiante']['aplica']
      and lm[RIC.id]['estudiante']['no_lista'] == 22, lm.get(RIC.id))
lv = lista(V, '2026-11-09', art)
check('K3b el origen lo tiene de nuevo desde el 09/11, con su horario de la tarde (lunes) y aviso de incorporación',
      RIC.id in lv and lv[RIC.id]['estudiante']['aplica']
      and any('Incorporado desde 09/11/2026' in a for a in lv[RIC.id]['estudiante']['avisos']), lv.get(RIC.id))
VESP06 = EV[5]
st, js = post('/api/estudiantes/%d/traslado' % VESP06.id, dire, {'curso_destino_id': MA.id, 'desde': '2026-11-09',
                                                                 'no_lista': 25})
db.expire_all()
check('K4 otro número disponible aunque deje hueco (25): se permite; nadie se renumera',
      st == 200 and db.get(M.Estudiante, VESP06.id).no_lista == 25
      and sorted(e.no_lista for e in db.query(M.Estudiante).filter_by(curso_id=MA.id, activo=True))
      == list(range(1, 20)) + [25], js)
st, js = post('/api/estudiantes/%d/traslado' % EV[6].id, dire, {'curso_destino_id': MA.id, 'desde': '2026-11-09',
                                                                'no_lista': 22})
check('K5 el n.º 22 sigue reservado a Ricardo en la mañana aunque se fue -> 409', st == 409
      and js.get('error') == 'NUMERO_OCUPADO', js)

RES_SIN_MOV_J3 = resultados_sin_movimiento(SIN_MOV[:6] + [EV[0], EM[0]])

# ═══════════════════ I. REGISTROS DE AMBOS CURSOS ═══════════════════
print('\n== I. Registro oficial y borrador ==')
# Decisión de Dirección (simulada) para la optativa del destino: su docente califica
# a Ricardo en esa asignatura (estaba vacía; no se copia nada de la optativa V).
# Ricardo ya volvió a la tarde (K2), así que su calificación en la optativa de la
# mañana la cargaría su docente con permiso de curso anterior; se simula el
# resultado de esa decisión directamente en la base sintética. Vesp06 sigue en la
# mañana y su docente lo califica por la vía normal.
for comp in (1, 2, 3, 4):
    db.add(M.CalificacionSecundaria(colegio_id=col.id, estudiante_id=RIC.id, asignatura_id=optM.id,
                                    ano_escolar_id=ano.id, competencia_numero=comp, p1=78, p2=79, p3=80, p4=81))
db.commit()
_cods_opt = [post('/api/calificaciones-secundaria', PROF[(MA.id, optM.id)], {'estudiante_id': VESP06.id,
             'asignatura_id': optM.id, 'competencia_numero': comp, 'p1': 77, 'p2': 78, 'p3': 79, 'p4': 80})[0]
             for comp in (1, 2, 3, 4)]
check('I0 decisión simulada de Dirección: la optativa del destino se califica en su asignatura (sin copiar notas)',
      all(x == 200 for x in _cods_opt), _cods_opt)
# De vuelta en la tarde, sus docentes de Música y de la optativa completan los
# períodos que quedaron vacíos (P1 sigue protegido; no se toca).
_cods_v = [post('/api/calificaciones-secundaria', PROF[(V.id, a_.id)], {'estudiante_id': RIC.id, 'asignatura_id': a_.id,
           'competencia_numero': comp, 'p2': 83, 'p3': 84, 'p4': 85})[0] for a_ in (mus, optV) for comp in (1, 2, 3, 4)]
check('I0b de vuelta en su curso, sus docentes completan P2-P4 vacíos de Música y optativa sin permiso',
      all(x == 200 for x in _cods_v), _cods_v)
# El Registro oficial espera la asistencia de TODO el año según el horario: se
# simula el estado de fin de curso sembrando (solo en esta base sintética) los
# días posteriores a hoy para quienes pertenecen a cada curso en cada fecha.
db.expire_all()
for cur in (V, MA, D2):
    for m in PERM.miembros_curso(db, cur, col.id):
        for a in ASIGS[cur.id]:
            for d in dias(HOY + dt.timedelta(days=1), ano.fecha_fin, HORARIO[(cur.id, a.id)]):
                if m.aplica(d):
                    db.add(M.Asistencia(colegio_id=col.id, estudiante_id=m.estudiante.id, curso_id=cur.id,
                                        asignatura_id=a.id, fecha=d, estado='presente',
                                        registrado_por=PROF[(cur.id, a.id)].id))
db.commit()
val_v = c.get('/api/registros/validar/%d' % V.id, headers=H(dire)).json()
val_m = c.get('/api/registros/validar/%d' % MA.id, headers=H(dire)).json()
val_2 = c.get('/api/registros/validar/%d' % D2.id, headers=H(dire)).json()
DATOS['I_validacion'] = {'V': val_v, 'M': val_m, '2do': val_2}
txt_v, txt_m, txt_2 = (json.dumps(x, ensure_ascii=False) for x in (val_v, val_m, val_2))
check('I1 validador del origen: sin INCONSISTENCIA por el traslado ni por el regreso', 'INCONSISTENCIA' not in txt_v, txt_v[:600])
check('I2 validador del destino: sin INCONSISTENCIA por las marcas válidas de la tarde', 'INCONSISTENCIA' not in txt_m, txt_m[:600])
check('I3 conflicto HEREDADO (marca de Mat21 después de su retiro antiguo): se ve y se explica como advertencia',
      'no le pertenecía' in txt_m and 'Mat21' in txt_m and 'no le pertenecía' in txt_2 and 'Seg06' in txt_2, txt_m[:600])
CV, CM = CORTO[V.id], CORTO[MA.id]
st_v, pdf_v, txt_pv = pdf('/api/registros/secundaria/%d?force=true' % V.id, 'registro_oficial_5toA_Vespertina.pdf')
st_m, pdf_m, txt_pm = pdf('/api/registros/secundaria/%d?force=true' % MA.id, 'registro_oficial_5toA_Matutina.pdf')
check('I4 Registro oficial del ORIGEN: Ricardo de vuelta [INC de %s 09/11/26]; Vesp06 [TRAS a %s 09/11/26]' % (CM, CM),
      st_v == 200 and ('[INC de %s 09/11/26]' % CM) in txt_pv and ('[TRAS a %s 09/11/26]' % CM) in txt_pv,
      txt_pv[:800] if st_v != 200 else '')
check('I5 Registro oficial del DESTINO: Ricardo [TRAS a %s 09/11/26], Abraham [RET 21/10/26], Mat21 [RET 10/09/26], '
      'Vesp06 [INC de %s 09/11/26]' % (CV, CV),
      st_m == 200 and ('[TRAS a %s 09/11/26]' % CV) in txt_pm and '[RET 21/10/26]' in txt_pm
      and '[RET 10/09/26]' in txt_pm and ('[INC de %s 09/11/26]' % CV) in txt_pm, txt_pm[:800] if st_m != 200 else '')
check('I5c leyendas de permanencia en el margen (marcas y «-» = No aplica)',
      'Marcas: [RET dd/mm/aa]' in (txt_pv or '') and 'No aplica: el estudiante no pertenecía' in (txt_pm or ''))
st_b, _, txt_b = pdf('/api/registros/secundaria/%d/preview-pdf' % V.id, 'registro_borrador_5toA_Vespertina.pdf')
st_b2, _, txt_b2 = pdf('/api/registros/secundaria/%d/preview-pdf' % MA.id, 'registro_borrador_5toA_Matutina.pdf')
check('I6 borradores de ambos cursos', st_b == 200 and st_b2 == 200)
st_2, _, txt_2p = pdf('/api/registros/secundaria/%d?force=true' % D2.id, 'registro_oficial_2doA_Matutina.pdf')
check('I7 Registro de 2do: Hillary [REINC 03/11/26] en su fila 3 y Seg06 [RET 02/10/26]',
      st_2 == 200 and '[REINC 03/11/26]' in txt_2p and '[RET 02/10/26]' in txt_2p, txt_2p[:600] if st_2 != 200 else '')
db.expire_all()


def matriz_est(curso, est_id):
    miembros = PERM.miembros_curso(db, curso, col.id)
    ests = [m.estudiante for m in miembros]
    vent = {m.estudiante.id: m.ventanas for m in miembros}
    t = {'P': 0, 'A': 0, 'E': 0, '-': 0, '': 0}
    for mes in RA.build_asistencia_registro(db, curso.id, asignatura_id=art.id, estudiantes=ests, ventanas_por_est=vent):
        for fl in mes['filas']:
            if fl['estudiante_id'] == est_id:
                for v_ in fl['valores']:
                    t[v_ if v_ in t else ''] += 1
    return t


mv, mm = matriz_est(V, RIC.id), matriz_est(MA, RIC.id)
DATOS['I_matriz_EA'] = {'origen': mv, 'destino': mm}
check('I8 origen: marcas de la tarde, «-» del 21/10 al 08/11 y marcas otra vez desde el 09/11; ninguna celda vacía',
      mv['P'] + mv['A'] + mv['E'] > 0 and 0 < mv['-'] <= 6 and mv[''] == 0, mv)
check('I9 destino: «-» antes del 21/10 y después del 08/11; sus marcas de la mañana entre medias; ninguna vacía',
      mm['-'] > 0 and 0 < mm['P'] <= 6 and mm[''] == 0, mm)
filas_m, _info_m = APP._estudiantes_registro(db, dire, db.get(M.Curso, MA.id))
check('I10 fila = número: en la mañana las filas 23 y 24 son huecos y la 25 es Vesp06',
      len(filas_m) == 25 and getattr(filas_m[22], '_fila_vacia', False) and getattr(filas_m[23], '_fila_vacia', False)
      and filas_m[24].id == VESP06.id and filas_m[21].id == RIC.id, [getattr(f, 'id', None) for f in filas_m[19:]])


def filas_con_texto(pdf_bytes, pagina, geo):
    """Filas (1..n) de la rejilla de asistencia que tienen alguna marca impresa."""
    doc = pymupdf.open(stream=pdf_bytes, filetype='pdf')
    p_ = doc[pagina - 1]
    y0, alto = geo['primera_fila_y_plumber'], geo['row_height']
    filas = set()
    for w in p_.get_text('words'):
        if w[4] in ('P', 'A', 'E', 'T', '-') and w[0] > 60:
            f = int((w[1] - y0) // alto) + 1
            if 1 <= f <= 40:
                filas.add(f)
    return filas


import registro_escolar as RE  # noqa: E402
fm_pdf = filas_con_texto(pdf_m, 47, RE._geo(RE.ASISTENCIA_TABLE_4MESES))
check('I11 PDF del destino (hoja de Artística): marcas en las filas 1-22 y 25; las filas 23 y 24 en blanco',
      set(range(1, 23)) <= fm_pdf and 25 in fm_pdf and 23 not in fm_pdf and 24 not in fm_pdf, sorted(fm_pdf))

# ═══════════════════ J. CONSERVACIÓN ═══════════════════
print('\n== J. Conservación de lo existente ==')
FIN = huella_global()
# Las dos únicas marcas originales que el test corrige A PROPÓSITO, como docente
# de su curso dentro de la permanencia (D9 y F4). Se comparan aparte.
db.expire_all()
EDITADAS = {db.query(M.Asistencia).filter_by(estudiante_id=RIC.id, fecha=dt.date(2026, 10, 14), asignatura_id=art.id).one().id,
            db.query(M.Asistencia).filter_by(estudiante_id=ABR.id, fecha=dt.date(2026, 10, 8), asignatura_id=art.id).one().id}
DATOS['J_editadas_a_proposito'] = {k: (BASE['asistencias'][k], FIN['asistencias'][k]) for k in EDITADAS}
cambios, faltan = comparar_originales(BASE, FIN)
cambios = [x for x in cambios if not (x[0] == 'asistencias' and x[1] in EDITADAS)]
check('J1 todas las notas, RP y asistencias ORIGINALES conservan id, valores, fechas, cursos y autores',
      not cambios and not faltan, (cambios[:5], faltan[:5]))
check('J1b las dos marcas corregidas a propósito conservan id, curso, fecha, asignatura y autor',
      all(BASE['asistencias'][k][:4] == FIN['asistencias'][k][:4] and BASE['asistencias'][k][5] == FIN['asistencias'][k][5]
          for k in EDITADAS), DATOS['J_editadas_a_proposito'])
nuevas = {k for k in set(FIN['asistencias']) - set(BASE['asistencias']) if FIN['asistencias'][k][3] <= HOY.isoformat()}
check('J2 lo nuevo (hasta hoy) es solo lo cargado después: destino de Ricardo, corrección de Abraham, lote, Hillary',
      nuevas and all(FIN['asistencias'][k][0] in (RIC.id, ABR.id, EM[0].id, HIL.id) for k in nuevas),
      sorted({FIN['asistencias'][k][0] for k in nuevas}))
check('J3 estudiantes SIN movimientos mantienen boletín, asistencia y resultados',
      RES_SIN_MOV_J3 == RES_SIN_MOV_ANTES, [k for k in RES_SIN_MOV_ANTES if RES_SIN_MOV_ANTES[k] != RES_SIN_MOV_J3.get(k)])
_movs2 = db.query(M.MovimientoEstudiante).filter_by(colegio_id=col2.id).all()
_cursos1 = {V.id, MA.id, D2.id, C4.id}
check('J4 el otro colegio (mismos nombres): sus movimientos nunca tocan cursos ni estudiantes del primero',
      all(m.curso_origen_id not in _cursos1 and m.curso_destino_id not in _cursos1 for m in _movs2)
      and not any(m.estudiante_id in {e.id for e in EV + EM + E2} for m in _movs2)
      and db.get(M.Estudiante, RIC2.id).curso_id == VB.id)
st, js = post('/api/estudiantes/%d/traslado' % RIC2.id, dir2, {'curso_destino_id': MB.id, 'desde': '2026-10-21'})
db.expire_all()
_m2 = db.query(M.MovimientoEstudiante).filter_by(estudiante_id=RIC2.id).all()
check('J5 en el otro colegio su propio traslado queda en su colegio, con sus cursos', st == 200
      and len(_m2) == 1 and _m2[0].colegio_id == col2.id and _m2[0].curso_destino_id == MB.id, js)
res = {(r_.curso_id, r_.no_lista, r_.estudiante_id) for r_ in db.query(M.ReservaNumeroLista).filter_by(colegio_id=col.id)}
check('J6 números: Ricardo conserva 15 (tarde) y 22 reservado (mañana); ninguna reserva repetida',
      (V.id, 15, RIC.id) in res and (MA.id, 22, RIC.id) in res
      and len({(c_, n_) for c_, n_, _ in res}) == len(res), sorted(res))
_otro_ano = add(M.AnoEscolar(colegio_id=col.id, nombre='2027-2028', activo=False, fecha_inicio=dt.date(2027, 8, 20),
                             fecha_fin=dt.date(2028, 6, 30)))
_curso_otro_ano = add(M.Curso(colegio_id=col.id, nombre='A', grado_id=g5.id, tanda_id=tm.id,
                              ano_escolar_id=_otro_ano.id, activo=True))
db.commit()
st, js = post('/api/estudiantes/%d/traslado' % EV[7].id, dire, {'curso_destino_id': _curso_otro_ano.id,
                                                                'desde': '2026-11-09'})
check('J7 no se traslada a un curso de OTRO año escolar', st == 409 and js.get('error') == 'DESTINO_NO_DISPONIBLE', js)

# ═══════════════════ L. ELIMINAR POR ERROR ═══════════════════
print('\n== L. Eliminar una ficha por error ==')
err = estudiante('Error', 'Sintético', C4, 8)
db.commit()
ERR_ID = err.id
r1 = c.request('DELETE', '/api/estudiantes/%d' % ERR_ID, headers=H(dire), json={'desde': '2026-11-09'})
r2 = c.post('/api/estudiantes/%d/eliminar-por-error' % ERR_ID, headers=H(dire),
            json={'motivo': 'Ficha duplicada (sintético)', 'confirmar_estudiante_id': ERR_ID})
db.expire_all()
check('L1 una ficha SIN historia, retirada, sigue pudiéndose eliminar por error (no deja movimientos huérfanos)',
      r1.status_code == 200 and r2.status_code == 200 and db.get(M.Estudiante, ERR_ID) is None, (r1.text[:200], r2.text[:200]))
# El «Ricardo» del otro colegio siempre tiene trayectoria (su traslado de J5).
# (Conc01 no sirve: según cómo se reparta la carrera natural de C10 puede no
# tener ningún movimiento, y entonces su eliminación sería correcta.)
conc = RIC2
r1 = c.request('DELETE', '/api/estudiantes/%d' % conc.id, headers=H(dir2), json={'desde': '2026-11-09'})
h_conc = (db.query(M.MovimientoEstudiante).filter_by(estudiante_id=conc.id).count(),
          db.query(M.ReservaNumeroLista).filter_by(estudiante_id=conc.id).count())
r2 = c.post('/api/estudiantes/%d/eliminar-por-error' % conc.id, headers=H(dir2),
            json={'motivo': 'Prueba', 'confirmar_estudiante_id': conc.id})
r3 = c.get('/api/estudiantes/%d/impacto-eliminacion-error' % conc.id, headers=H(dir2)).json()
db.expire_all()
check('L2 una ficha CON trayectoria (traslados) queda protegida: 409 con mensaje claro, nada borrado',
      r1.status_code == 200 and r2.status_code == 409 and r2.json().get('error') == 'FICHA_CON_TRAYECTORIA'
      and db.get(M.Estudiante, conc.id) is not None
      and (db.query(M.MovimientoEstudiante).filter_by(estudiante_id=conc.id).count(),
           db.query(M.ReservaNumeroLista).filter_by(estudiante_id=conc.id).count()) == h_conc
      and r3.get('eliminable') is False, (r1.text[:200], r2.text[:300], h_conc))

sinh = estudiante('SinHistoria', 'Sintético', C4, 7)
db.commit()
SINH_ID = sinh.id
r1 = c.request('DELETE', '/api/estudiantes/%d' % SINH_ID, headers=H(secre),
               json={'desde': '2026-11-09', 'motivo_retiro': 'Mudanza (sintético)'})
r2 = c.post('/api/estudiantes/%d/reactivar' % SINH_ID, headers=H(dire), json={})
db.expire_all()
_ms = db.query(M.MovimientoEstudiante).filter_by(estudiante_id=SINH_ID).all()
_pv = (_ms[0].get_detalle().get('retiro_previo') or {}) if _ms else {}
check('L3 ficha SIN notas ni asistencia: reactivar conserva el retiro previo (fecha 08/11, motivo y autor)',
      r1.status_code == 200 and r2.status_code == 200 and [m.tipo for m in _ms] == ['reactivacion']
      and _pv.get('fecha_retiro') == '2026-11-08' and _pv.get('motivo_retiro') == 'Mudanza (sintético)'
      and _pv.get('retirado_por') == secre.id and _ms[0].registrado_por == dire.id, (r1.text[:150], r2.text[:150], _pv))
r3 = c.request('DELETE', '/api/estudiantes/%d' % SINH_ID, headers=H(dire), json={'desde': '2026-11-16'})
r4 = c.post('/api/estudiantes/%d/eliminar-por-error' % SINH_ID, headers=H(dire),
            json={'motivo': 'Prueba', 'confirmar_estudiante_id': SINH_ID})
db.expire_all()
check('L4 esa trazabilidad no se borra para poder eliminarla: 409 y todo intacto',
      r3.status_code == 200 and r4.status_code == 409 and r4.json().get('error') == 'FICHA_CON_TRAYECTORIA'
      and db.get(M.Estudiante, SINH_ID) is not None
      and db.query(M.MovimientoEstudiante).filter_by(estudiante_id=SINH_ID).count() == 2, (r3.text[:150], r4.text[:200]))

# ─────────────────────────── SALIDA ───────────────────────────
ok = sum(1 for _, c_, _ in RESULTADOS if c_)
mal = len(RESULTADOS) - ok
json.dump({'resultados': [{'prueba': n, 'pasa': c_, 'detalle': str(d)[:800]} for n, c_, d in RESULTADOS],
           'datos': DATOS}, open(os.path.join(OUT, 'resultados_retiros_traslados.json'), 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1, default=str)
print('\nRESULTADO RETIROS Y TRASLADOS: %d PASARON / %d FALLARON' % (ok, mal))
print('Salida:', OUT)
db.close()
sys.exit(1 if mal else 0)
