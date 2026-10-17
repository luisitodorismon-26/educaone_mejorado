# -*- coding: utf-8 -*-
"""
EducaOne — REP1: división Primaria/Secundaria en Reportes de conducta.

El nivel de un reporte se deriva del ESTUDIANTE (curso -> grado -> nivel).
  - Dirección: todo el colegio.
  - Coordinación / Psicología con nivel_asignado fijo: solo su división;
    sin división fija, como siempre.
  - Profesor: solo los suyos (sin cambios). Secretaría y Psicología: sin
    listado general. Secretaría tampoco imprime PDF por ID.
  - Acceso directo al otro nivel: 404 y sin escribir nada.
  - Aviso de reporte nuevo: Dirección siempre; coordinación según el nivel.

Base temporal aislada. Nunca producción.

Uso:
    cd backend
    python tools/test_reportes_nivel_rep1.py
"""
import os
import sys

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(BK, "tools"))

from test_utils import aislar_base_de_datos  # noqa: E402

TMP = aislar_base_de_datos('rep1_reportes_nivel')

from database import engine, SessionLocal  # noqa: E402
from test_utils import verificar_engine_aislado  # noqa: E402

verificar_engine_aislado(engine, TMP)

from datetime import date  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

import models as M  # noqa: E402
import app as APP  # noqa: E402
from auth import create_token  # noqa: E402

M.Base.metadata.create_all(bind=engine)
client = TestClient(APP.app)
RES = []


def check(nombre, ok, detalle=''):
    RES.append((nombre, bool(ok)))
    print(('  OK  ' if ok else '  FALLA ') + nombre + ('' if ok else '  -> ' + str(detalle)[:300]))


db = SessionLocal()


def add(obj):
    db.add(obj)
    db.flush()
    return obj


def colegio(nombre):
    return add(M.Colegio(nombre=nombre, codigo=nombre.lower(), activo=True))


def usuario(col, username, role, nivel=None):
    return add(M.Usuario(colegio_id=col.id, username=username, password_hash='x', nombre=username,
                         apellido='T', role=role, activo=True, must_change_password=False,
                         token_version=0, nivel_asignado=nivel))


def estudiante_en(col, nivel, nombre):
    ano = add(M.AnoEscolar(colegio_id=col.id, nombre='2026-2027-' + nombre, activo=True))
    g = add(M.Grado(colegio_id=col.id, nombre='1ro ' + nivel, nivel=nivel, orden=1))
    c = add(M.Curso(colegio_id=col.id, nombre='A', grado_id=g.id, ano_escolar_id=ano.id, activo=True))
    return add(M.Estudiante(colegio_id=col.id, nombre=nombre, apellido='T', curso_id=c.id, activo=True))


def reporte(col, est, autor, titulo):
    return add(M.ReporteConducta(colegio_id=col.id, estudiante_id=est.id, reportado_por=autor.id,
                                 titulo=titulo, descripcion='desc ' + titulo, tipo='conducta',
                                 gravedad='leve', estado='pendiente', fecha=date(2026, 9, 1)))


COL = colegio('C1')
OTRO = colegio('C2')
DIR = usuario(COL, 'dir', 'direccion')
DIR2 = usuario(COL, 'dir2', 'direccion')
CN = usuario(COL, 'coord_null', 'coordinador')
CP = usuario(COL, 'coord_pri', 'coordinador', 'primaria')
CS = usuario(COL, 'coord_sec', 'coordinador', 'secundaria')
PSN = usuario(COL, 'psi_null', 'psicologia')
PSP = usuario(COL, 'psi_pri', 'psicologia', 'primaria')
SEC = usuario(COL, 'secre', 'secretaria')
PROF_P = usuario(COL, 'prof_p', 'profesor')
PROF_S = usuario(COL, 'prof_s', 'profesor')
DIR_O = usuario(OTRO, 'dir_otro', 'direccion')
EST_P = estudiante_en(COL, 'primaria', 'EstPri')
EST_S = estudiante_en(COL, 'secundaria', 'EstSec')
EST_O = estudiante_en(OTRO, 'secundaria', 'EstOtro')
R_P = reporte(COL, EST_P, PROF_P, 'REP_PRIMARIA')
R_S = reporte(COL, EST_S, PROF_S, 'REP_SECUNDARIA')
R_S2 = reporte(COL, EST_S, PROF_S, 'REP_SECUNDARIA_2')
R_O = reporte(OTRO, EST_O, DIR_O, 'REP_OTRO_COLEGIO')
db.commit()


def h(u):
    return {'Authorization': 'Bearer ' + create_token(u)}


def listado(u):
    r = client.get('/api/reportes', headers=h(u))
    return r.status_code, ({x['id'] for x in r.json()} if r.status_code == 200 else None)


def huella(rep_id):
    """Estado observable de un reporte: si cambia, hubo escritura."""
    db.expire_all()
    r = db.get(M.ReporteConducta, rep_id)
    return (r.estado, r.respuesta, r.acciones_centro, bool(r.confirmado_padre), bool(r.enviado_padres),
            db.query(M.HistorialReportePadres).filter_by(reporte_id=rep_id).count())


TODOS = {R_P.id, R_S.id, R_S2.id}

print("\n=== LISTADO ===")
check('R-01 Dirección ve Primaria + Secundaria', listado(DIR) == (200, TODOS), listado(DIR))
check('R-02 coordinador sin nivel ve ambas', listado(CN) == (200, TODOS), listado(CN))
check('R-03 coordinador Primaria solo ve Primaria', listado(CP) == (200, {R_P.id}), listado(CP))
check('R-04 coordinador Secundaria solo ve Secundaria', listado(CS) == (200, {R_S.id, R_S2.id}), listado(CS))
check('R-05 profesor sigue viendo solo sus propios reportes',
      listado(PROF_P) == (200, {R_P.id}) and listado(PROF_S) == (200, {R_S.id, R_S2.id}), '')
check('R-06 Secretaría y Psicología siguen sin listado general (403)',
      listado(SEC)[0] == 403 and listado(PSN)[0] == 403 and listado(PSP)[0] == 403, '')
check('R-07 otro colegio: no ve los reportes del C1', R_O.id not in listado(DIR)[1]
      and listado(DIR_O) == (200, {R_O.id}), '')
check('R-08 X-Nivel no amplía al coordinador fijo',
      {x['id'] for x in client.get('/api/reportes', headers={**h(CP), 'X-Nivel': 'secundaria'}).json()} == {R_P.id},
      '')

print("\n=== ACCESO DIRECTO AL OTRO NIVEL (coordinador Primaria -> reporte Secundaria) ===")
antes = huella(R_S.id)
r1 = client.post('/api/reportes/%d/responder' % R_S.id, json={'acciones_centro': 'x'}, headers=h(CP))
r2 = client.post('/api/reportes/%d/confirmar-padre' % R_S.id, headers=h(CP))
r3 = client.post('/api/reportes/%d/enviar-padres' % R_S.id, json={'telefono': '8090000000'}, headers=h(CP))
r4 = client.get('/api/reportes/%d/historial-envios' % R_S.id, headers=h(CP))
r5 = client.get('/api/reportes/%d/pdf' % R_S.id, headers=h(CP))
check('R-09 no puede responder (404)', r1.status_code == 404, r1.text)
check('R-10 no puede confirmar firma del padre (404)', r2.status_code == 404, r2.text)
check('R-11 no puede enviarlo a padres (404)', r3.status_code == 404, r3.text)
check('R-12 no puede ver el historial de envíos (404)', r4.status_code == 404, r4.text)
check('R-13 no puede imprimir el PDF (404)', r5.status_code == 404, r5.text[:200])
check('R-14 ...y nada se escribió en el reporte ni en el historial', huella(R_S.id) == antes, (antes, huella(R_S.id)))
check('R-15 la respuesta 404 no revela que el reporte existe',
      r1.json() == client.post('/api/reportes/999999/responder', json={'acciones_centro': 'x'},
                               headers=h(CP)).json(), (r1.json(),))
check('R-16 coordinador Secundaria tampoco opera un reporte de Primaria',
      client.post('/api/reportes/%d/responder' % R_P.id, json={'acciones_centro': 'x'}, headers=h(CS)).status_code == 404
      and client.get('/api/reportes/%d/pdf' % R_P.id, headers=h(CS)).status_code == 404, '')

print("\n=== PSICOLOGÍA ===")
antes = huella(R_S.id)
check('R-17 Psicología Primaria no opera un reporte de Secundaria (404 en las 4 acciones)',
      [client.post('/api/reportes/%d/responder' % R_S.id, json={'acciones_centro': 'x'}, headers=h(PSP)).status_code,
       client.post('/api/reportes/%d/confirmar-padre' % R_S.id, headers=h(PSP)).status_code,
       client.post('/api/reportes/%d/enviar-padres' % R_S.id, json={}, headers=h(PSP)).status_code,
       client.get('/api/reportes/%d/pdf' % R_S.id, headers=h(PSP)).status_code] == [404] * 4, '')
check('R-17b ...sin escribir nada', huella(R_S.id) == antes, '')
check('R-18 Psicología sin nivel conserva sus acciones (comportamiento actual)',
      client.post('/api/reportes/%d/responder' % R_S2.id, json={'acciones_centro': 'Intervención'},
                  headers=h(PSN)).status_code == 200
      and client.get('/api/reportes/%d/pdf' % R_S2.id, headers=h(PSN)).status_code == 200, '')

print("\n=== SU PROPIA DIVISIÓN SIGUE FUNCIONANDO ===")
check('R-19 coordinador Primaria opera su reporte de Primaria',
      [client.post('/api/reportes/%d/responder' % R_P.id, json={'acciones_centro': 'Citación'}, headers=h(CP)).status_code,
       client.post('/api/reportes/%d/confirmar-padre' % R_P.id, headers=h(CP)).status_code,
       client.post('/api/reportes/%d/enviar-padres' % R_P.id, json={'telefono': '8091111111'}, headers=h(CP)).status_code,
       client.get('/api/reportes/%d/historial-envios' % R_P.id, headers=h(CP)).status_code,
       client.get('/api/reportes/%d/pdf' % R_P.id, headers=h(CP)).status_code] == [200] * 5, '')
check('R-20 Dirección opera cualquier división',
      client.get('/api/reportes/%d/pdf' % R_S.id, headers=h(DIR)).status_code == 200
      and client.get('/api/reportes/%d/historial-envios' % R_S.id, headers=h(DIR)).status_code == 200, '')
check('R-21 coordinador sin nivel opera ambas',
      client.get('/api/reportes/%d/pdf' % R_P.id, headers=h(CN)).status_code == 200
      and client.get('/api/reportes/%d/pdf' % R_S.id, headers=h(CN)).status_code == 200, '')

print("\n=== PDF ===")
check('R-22 Secretaría no puede imprimir un reporte por ID', client.get('/api/reportes/%d/pdf' % R_P.id,
                                                                        headers=h(SEC)).status_code in (403, 404), '')
check('R-23 profesor: su PDF sí (200), el ajeno no (403), como hoy',
      client.get('/api/reportes/%d/pdf' % R_P.id, headers=h(PROF_P)).status_code == 200
      and client.get('/api/reportes/%d/pdf' % R_S.id, headers=h(PROF_P)).status_code == 403, '')

print("\n=== OTRO COLEGIO ===")
check('R-24 otro colegio sigue 404 en todas las acciones',
      [client.get('/api/reportes/%d/pdf' % R_O.id, headers=h(DIR)).status_code,
       client.post('/api/reportes/%d/responder' % R_O.id, json={'acciones_centro': 'x'}, headers=h(DIR)).status_code,
       client.post('/api/reportes/%d/confirmar-padre' % R_O.id, headers=h(CN)).status_code,
       client.post('/api/reportes/%d/enviar-padres' % R_O.id, json={}, headers=h(DIR)).status_code,
       client.get('/api/reportes/%d/historial-envios' % R_O.id, headers=h(DIR)).status_code] == [404] * 5, '')

print("\n=== NOTIFICACIONES AL CREAR ===")


def avisados(rep_id):
    db.expire_all()
    return {n.usuario_id for n in db.query(M.Notificacion).filter_by(evento_key='reporte:%d:creado' % rep_id)}


rp = client.post('/api/reportes', json={'estudiante_id': EST_P.id, 'titulo': 'Nuevo P'}, headers=h(DIR))
rs = client.post('/api/reportes', json={'estudiante_id': EST_S.id, 'titulo': 'Nuevo S'}, headers=h(DIR))
check('R-25 crear reportes sigue funcionando', rp.status_code == 201 and rs.status_code == 201, (rp.text, rs.text))
ap, as_ = avisados(rp.json()['id']), avisados(rs.json()['id'])
check('R-26 reporte de Primaria no llega al coordinador fijo de Secundaria', CS.id not in ap and CP.id in ap, ap)
check('R-27 reporte de Secundaria no llega al coordinador fijo de Primaria', CP.id not in as_ and CS.id in as_, as_)
check('R-28 coordinador sin nivel recibe ambos', CN.id in ap and CN.id in as_, (ap, as_))
check('R-29 Dirección sigue recibiendo ambos (el autor no se auto-notifica)',
      DIR2.id in ap and DIR2.id in as_ and DIR.id not in ap, (ap, as_))
check('R-30 nadie de otro rol ni de otro colegio recibe el aviso',
      not ({PSN.id, PSP.id, SEC.id, PROF_P.id, PROF_S.id, DIR_O.id} & (ap | as_)), (ap, as_))
check('R-31 el aviso respeta lo que cada coordinador puede abrir',
      rp.json()['id'] in listado(CP)[1] and rp.json()['id'] not in listado(CS)[1], '')
rcs = client.post('/api/reportes', json={'estudiante_id': EST_S.id, 'titulo': 'De CS'}, headers=h(CS))
check('R-32 coordinador Secundaria crea en su nivel; no se auto-notifica',
      rcs.status_code == 201 and CS.id not in avisados(rcs.json()['id'])
      and {DIR.id, DIR2.id, CN.id} <= avisados(rcs.json()['id']), rcs.text)
check('R-33 coordinador Primaria no crea un reporte de Secundaria (candado existente)',
      client.post('/api/reportes', json={'estudiante_id': EST_S.id, 'titulo': 'X'}, headers=h(CP)).status_code == 403, '')

print("\n=== DASHBOARD: ACTIVIDAD RECIENTE Y CONTEOS ===")


def titulos_actividad(u):
    r = client.get('/api/dashboard/actividad-reciente', headers=h(u))
    return {a['titulo'] for a in r.json() if a.get('tipo') == 'reporte'}


T_PRI = {'REP_PRIMARIA', 'Nuevo P'}
T_SEC = {'REP_SECUNDARIA', 'REP_SECUNDARIA_2', 'Nuevo S', 'De CS'}
a_pp, a_sec, a_psi = titulos_actividad(PROF_P), titulos_actividad(SEC), titulos_actividad(PSN)
a_cp, a_cs, a_dir = titulos_actividad(CP), titulos_actividad(CS), titulos_actividad(DIR)
check('R-34 actividad: profesor solo ve títulos de sus reportes', a_pp == {'REP_PRIMARIA'}, a_pp)
check('R-35 actividad: Secretaría y Psicología no reciben títulos de reportes', a_sec == set() and a_psi == set(),
      (a_sec, a_psi))
check('R-36 actividad: coordinador Primaria no ve títulos de Secundaria', a_cp and not (a_cp & T_SEC), a_cp)
check('R-37 actividad: coordinador Secundaria no ve títulos de Primaria', a_cs and not (a_cs & T_PRI), a_cs)
check('R-38 actividad: Dirección ve ambos niveles', (a_dir & T_PRI) and (a_dir & T_SEC), a_dir)

db.expire_all()
_pend = db.query(M.ReporteConducta).filter_by(colegio_id=COL.id, estado='pendiente').all()
N_P = sum(1 for r in _pend if r.estudiante_id == EST_P.id)
N_S = sum(1 for r in _pend if r.estudiante_id == EST_S.id)
check('R-39 precondición: pendientes distintos por nivel', N_P > 0 and N_S > 0 and N_P != N_S, (N_P, N_S))


def n_dash_alertas(u):
    al = [a for a in client.get('/api/dashboard/alertas', headers=h(u)).json() if a.get('tipo') == 'reporte']
    return al[0]['count'] if al else 0


def n_dash_all(u):
    return client.get('/api/dashboard/all', headers=h(u)).json()['stats']['reportes_pendientes']


def n_alertas(u):
    al = [a for a in client.get('/api/alertas', headers=h(u)).json() if a.get('tipo') == 'reporte']
    return int(al[0]['titulo'].split()[0]) if al else 0


for nombre, fn in (('dashboard/alertas', n_dash_alertas), ('dashboard/all', n_dash_all), ('/api/alertas', n_alertas)):
    v = {u.username: fn(u) for u in (CP, CS, CN, DIR)}
    check('R-40 %s: coordinador fijo cuenta solo su nivel' % nombre,
          v['coord_pri'] == N_P and v['coord_sec'] == N_S, (v, N_P, N_S))
    check('R-41 %s: coordinador sin nivel y Dirección cuentan ambos' % nombre,
          v['coord_null'] == N_P + N_S and v['dir'] == N_P + N_S, (v, N_P, N_S))

print("\n=== SELECTOR GLOBAL (X-Nivel): LENTE DE VISTA, NO AUTORIZACIÓN ===")
db.expire_all()
_todos = db.query(M.ReporteConducta).filter_by(colegio_id=COL.id).all()
IDS_P = {r.id for r in _todos if r.estudiante_id == EST_P.id}
IDS_S = {r.id for r in _todos if r.estudiante_id == EST_S.id}


def lista(u, nivel=None):
    hd = dict(h(u), **({'X-Nivel': nivel} if nivel else {}))
    r = client.get('/api/reportes', headers=hd)
    return {x['id'] for x in r.json()} if r.status_code == 200 else r.status_code


for u, quien in ((CN, 'coordinador sin nivel'), (DIR, 'Dirección')):
    check('L-01 %s: Todos / Primaria / Secundaria' % quien,
          (lista(u), lista(u, 'primaria'), lista(u, 'secundaria')) == (IDS_P | IDS_S, IDS_P, IDS_S),
          (lista(u), lista(u, 'primaria'), lista(u, 'secundaria')))
check('L-02 coordinador Primaria: X-Nivel secundaria no salta su nivel',
      lista(CP) == IDS_P and lista(CP, 'secundaria') == IDS_P, (lista(CP), lista(CP, 'secundaria')))
check('L-03 coordinador Secundaria: X-Nivel primaria no salta su nivel',
      lista(CS) == IDS_S and lista(CS, 'primaria') == IDS_S, (lista(CS), lista(CS, 'primaria')))


def hx(u, nivel):
    return dict(h(u), **({'X-Nivel': nivel} if nivel else {}))


def act(u, nivel=None):
    return {a['titulo'] for a in client.get('/api/dashboard/actividad-reciente', headers=hx(u, nivel)).json()
            if a.get('tipo') == 'reporte'}


def cuentas(u, nivel=None):
    hd = hx(u, nivel)
    a1 = [a for a in client.get('/api/dashboard/alertas', headers=hd).json() if a.get('tipo') == 'reporte']
    a2 = client.get('/api/dashboard/all', headers=hd).json()['stats']['reportes_pendientes']
    a3 = [a for a in client.get('/api/alertas', headers=hd).json() if a.get('tipo') == 'reporte']
    return (a1[0]['count'] if a1 else 0, a2, int(a3[0]['titulo'].split()[0]) if a3 else 0)


for u, quien in ((CN, 'coordinador sin nivel'), (DIR, 'Dirección')):
    ap_, as2 = act(u, 'primaria'), act(u, 'secundaria')
    check('L-04 %s: actividad reciente sigue el lente' % quien,
          ap_ and not (ap_ & T_SEC) and as2 and not (as2 & T_PRI), (ap_, as2))
    c = (cuentas(u), cuentas(u, 'primaria'), cuentas(u, 'secundaria'))
    check('L-05 %s: alertas, dashboard/all y /api/alertas siguen el lente' % quien,
          c == ((N_P + N_S,) * 3, (N_P,) * 3, (N_S,) * 3), (c, N_P, N_S))
check('L-06 coordinador fijo: el lente no cambia sus conteos ni su actividad',
      cuentas(CP, 'secundaria') == (N_P,) * 3 and cuentas(CS, 'primaria') == (N_S,) * 3
      and not (act(CP, 'secundaria') & T_SEC) and not (act(CS, 'primaria') & T_PRI), '')

# Acciones por ID: manda la AUTORIZACIÓN (nivel_asignado), no la vista elegida.
check('L-07 coordinador sin nivel con vista Primaria sigue pudiendo operar uno de Secundaria',
      client.get('/api/reportes/%d/pdf' % R_S.id, headers=hx(CN, 'primaria')).status_code == 200
      and client.get('/api/reportes/%d/historial-envios' % R_S.id, headers=hx(CN, 'primaria')).status_code == 200, '')
check('L-08 Dirección con vista Primaria sigue pudiendo operar uno de Secundaria',
      client.get('/api/reportes/%d/pdf' % R_S.id, headers=hx(DIR, 'primaria')).status_code == 200, '')
antes = huella(R_S.id)
check('L-09 coordinador Primaria con X-Nivel secundaria sigue en 404 por ID y sin escribir',
      [client.post('/api/reportes/%d/responder' % R_S.id, json={'acciones_centro': 'x'}, headers=hx(CP, 'secundaria')).status_code,
       client.post('/api/reportes/%d/confirmar-padre' % R_S.id, headers=hx(CP, 'secundaria')).status_code,
       client.post('/api/reportes/%d/enviar-padres' % R_S.id, json={}, headers=hx(CP, 'secundaria')).status_code,
       client.get('/api/reportes/%d/historial-envios' % R_S.id, headers=hx(CP, 'secundaria')).status_code,
       client.get('/api/reportes/%d/pdf' % R_S.id, headers=hx(CP, 'secundaria')).status_code] == [404] * 5
      and huella(R_S.id) == antes, '')
check('L-10 Psicología Primaria con X-Nivel secundaria sigue en 404',
      client.get('/api/reportes/%d/pdf' % R_S.id, headers=hx(PSP, 'secundaria')).status_code == 404, '')
check('L-11 Secretaría con X-Nivel: sigue sin listado ni PDF',
      client.get('/api/reportes', headers=hx(SEC, 'primaria')).status_code == 403
      and client.get('/api/reportes/%d/pdf' % R_P.id, headers=hx(SEC, 'primaria')).status_code == 403, '')

# Avisos: los decide la autorización, no la vista del autor ni del receptor.
rv = client.post('/api/reportes', json={'estudiante_id': EST_S.id, 'titulo': 'Con vista P'}, headers=hx(DIR, 'primaria'))
av = avisados(rv.json()['id'])
check('L-12 la vista elegida no filtra avisos: coordinador sin nivel y Secundaria lo reciben; Primaria no',
      rv.status_code == 201 and CN.id in av and CS.id in av and CP.id not in av and DIR2.id in av, av)
db.close()

ok = sum(1 for _, r in RES if r)
print('\nRESULTADO REP1: %d PASARON / %d FALLARON' % (ok, len(RES) - ok))
sys.exit(0 if ok == len(RES) else 1)
