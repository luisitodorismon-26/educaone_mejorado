# -*- coding: utf-8 -*-
"""
EducaOne — PSI-COM-1 (mínimo): Psicología publica comunicados y envía "Por rol".

Reutiliza los flujos de Coordinación sin su excepción global. El alcance es la
DIVISIÓN de la cuenta (nivel_asignado; vacío = ambos niveles). Los
destinatarios siguen las reglas actuales de Comunicación
(usuarios_autorizados_para_nivel: nivel igual o vacío). Sin restricción por
tanda y sin reglas por asignaciones docentes.

Base temporal aislada. Nunca producción.

Uso:
    cd backend
    python tools/test_psi_com1.py
"""
import os
import sys

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(BK, "tools"))

from test_utils import aislar_base_de_datos  # noqa: E402

TMP = aislar_base_de_datos('psi_com1_min')

from database import engine, SessionLocal  # noqa: E402
from test_utils import verificar_engine_aislado  # noqa: E402

verificar_engine_aislado(engine, TMP)

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


def add(o):
    db.add(o)
    db.flush()
    return o


COL, OTRO = (add(M.Colegio(nombre=n, codigo=n.lower(), activo=True)) for n in ('C1', 'C2'))
T_V = add(M.Tanda(colegio_id=COL.id, nombre='Vespertina', hora_inicio='14:00', hora_fin='18:00', activo=True))


def usuario(col, username, role, nivel=None, tanda=None):
    return add(M.Usuario(colegio_id=col.id, username=username, password_hash='x', nombre=username,
                         apellido='T', role=role, activo=True, must_change_password=False, token_version=0,
                         nivel_asignado=nivel, tanda_id=tanda.id if tanda else None))


DIR = usuario(COL, 'dir', 'direccion')
COORD = usuario(COL, 'coord', 'coordinador')
COORD_S = usuario(COL, 'coord_s', 'coordinador', 'secundaria')
SECRE = usuario(COL, 'secre', 'secretaria')
PSI_AMB = usuario(COL, 'psi_ambos', 'psicologia')               # "Ambos niveles"
PSI_P = usuario(COL, 'psi_p', 'psicologia', 'primaria')
PSI_S = usuario(COL, 'psi_s', 'psicologia', 'secundaria')
PSI_TANDA = usuario(COL, 'psi_tanda', 'psicologia', 'primaria', T_V)  # tanda fija: NO se restringe aún
PROF_P = usuario(COL, 'prof_p', 'profesor', 'primaria')
PROF_S = usuario(COL, 'prof_s', 'profesor', 'secundaria')
PROF_N = usuario(COL, 'prof_n', 'profesor')                     # nivel vacío = ambos (regla actual)
DIR_O = usuario(OTRO, 'dir_o', 'direccion')
PROF_O = usuario(OTRO, 'prof_o', 'profesor', 'primaria')
PSI_O = usuario(OTRO, 'psi_o', 'psicologia')
db.commit()


def h(u, nivel=None):
    hd = {'Authorization': 'Bearer ' + create_token(u)}
    if nivel:
        hd['X-Nivel'] = nivel
    return hd


def ids(*us):
    return {u.id for u in us}


def conteos():
    db.expire_all()
    return db.query(M.Mensaje).count(), db.query(M.Notificacion).count()


_n = [0]


def masivo(u, rol, nivel=None, **extra):
    """Envía "Por rol"; devuelve (status, json, [destinatarios], [notificados])."""
    _n[0] += 1
    asunto = 'Aviso %d' % _n[0]
    r = client.post('/api/mensajes/masivo', json=dict({'rol': rol, 'asunto': asunto, 'contenido': 'Texto'}, **extra),
                    headers=h(u, nivel))
    db.expire_all()
    msgs = db.query(M.Mensaje).filter_by(remitente_id=u.id, asunto=asunto).order_by(M.Mensaje.id).all()
    dest = [m.destinatario_id for m in msgs]
    notif = []
    if msgs:
        notif = [n.usuario_id for n in db.query(M.Notificacion).filter_by(evento_key='mensaje_masivo:%d' % msgs[0].id)]
    return r.status_code, r.json(), dest, notif


print("\n=== MENSAJE 'POR ROL' ===")
_c, _j, d_coord, _ = masivo(COORD, 'profesor')
cod, _j, d_amb, _ = masivo(PSI_AMB, 'profesor')
check('M-01 "Ambos niveles" llega a los mismos docentes que Coordinación',
      cod == 201 and set(d_amb) == set(d_coord) == ids(PROF_P, PROF_S, PROF_N), (cod, d_amb, d_coord))
cod, _j, d, _ = masivo(PSI_P, 'profesor')
check('M-02 Psicología Primaria: docentes de Primaria y de nivel vacío (regla actual), no de Secundaria',
      cod == 201 and set(d) == ids(PROF_P, PROF_N), d)
cod, _j, d, _ = masivo(PSI_S, 'profesor')
check('M-03 Psicología Secundaria: docentes de Secundaria y de nivel vacío', set(d) == ids(PROF_S, PROF_N), d)
cod, _j, d, _ = masivo(PSI_P, 'coordinador')
check('M-04 coordinador fijo en la otra división queda fuera', set(d) == ids(COORD), d)
cod, _j, d, _ = masivo(PSI_P, 'direccion')
check('M-05 solo recibe el rol elegido (Dirección al elegir Dirección)', set(d) == ids(DIR), d)
cod, _j, d, _ = masivo(PSI_P, 'profesor', nivel='secundaria', nivel_asignado='secundaria', tipo='general')
check('M-06 X-Nivel y campos extra del formulario no amplían el alcance', set(d) == ids(PROF_P, PROF_N), d)
cod, _j, d, _ = masivo(PSI_P, 'psicologia')
check('M-07 sin autoenvío; Psicología de la otra división fuera', PSI_P.id not in d
      and set(d) == ids(PSI_AMB, PSI_TANDA), d)
cod, _j, d, notif = masivo(PSI_AMB, 'profesor')
check('M-08 un mensaje por destinatario, sin duplicados', len(d) == len(set(d)) == 3, d)
check('M-09 una notificación por destinatario de ESTE envío (mismo conjunto)',
      sorted(notif) == sorted(d) and len(notif) == len(set(notif)), (notif, d))
antes = conteos()
cod, j, d, _ = masivo(PSI_S, 'secretaria')   # SECRE tiene nivel vacío -> SÍ entra
check('M-10 secretaría de nivel vacío entra (regla actual)', cod == 201 and set(d) == ids(SECRE), (cod, j, d))
# Escenario realmente sin destinatarios: Psicología Primaria -> rol psicologia en un colegio donde la
# única otra psicóloga es de Secundaria.
COL3 = add(M.Colegio(nombre='C3', codigo='c3', activo=True))
P3 = usuario(COL3, 'psi3_p', 'psicologia', 'primaria')
usuario(COL3, 'psi3_s', 'psicologia', 'secundaria')
db.commit()
antes = conteos()
cod, j, d, _ = masivo(P3, 'psicologia')
check('M-11 sin destinatarios en su división: 404 con mensaje claro y exacto',
      cod == 404 and j == {'error': 'No hay destinatarios del rol psicologia dentro de su división.'}, (cod, j))
check('M-12 ...y no crea mensajes ni notificaciones', conteos() == antes and d == [], (antes, conteos()))
check('M-13 nunca sale del colegio', not (set(d_amb) | set(d_coord)) & ids(DIR_O, PROF_O, PSI_O), '')
check('M-14 Psicología de otro colegio no alcanza a este colegio',
      not (set(masivo(PSI_O, 'profesor')[2]) & ids(PROF_P, PROF_S, PROF_N)), '')
cod, _j, d, _ = masivo(PSI_TANDA, 'profesor')
check('M-15 tanda fija: NO se restringe por tanda (pendiente); solo por división', cod == 201
      and set(d) == ids(PROF_P, PROF_N), d)
check('M-16 rol inválido sigue en 400', masivo(PSI_AMB, 'superadmin')[0] == 400, '')
check('M-17 profesor y secretaría siguen sin "Por rol" (403)',
      masivo(PROF_P, 'profesor')[0] == 403 and masivo(SECRE, 'profesor')[0] == 403, '')
check('M-18 mensaje individual de Psicología sin cambios (a cualquiera del colegio)',
      client.post('/api/mensajes', json={'destinatario_id': PROF_S.id, 'asunto': 'A', 'contenido': 'B'},
                  headers=h(PSI_P)).status_code == 201, '')

print("\n=== COMUNICADOS ===")


def publicar(u, tipo, nivel=None, titulo=None):
    return client.post('/api/comunicados', json={'titulo': titulo or 'Com %s %s' % (u.username, tipo),
                                                 'contenido': 'x', 'tipo': tipo}, headers=h(u, nivel))


def n_com():
    db.expire_all()
    return db.query(M.Comunicado).count()


def titulos(u):
    return {c['titulo'] for c in client.get('/api/comunicados', headers=h(u)).json()}


r_amb = {t: publicar(PSI_AMB, t) for t in ('general', 'primaria', 'secundaria')}
check('C-01 "Ambos niveles" publica en los tres alcances', all(r.status_code == 201 for r in r_amb.values()), '')
r_p = publicar(PSI_P, 'primaria')
check('C-02 división fija publica en su división', r_p.status_code == 201, r_p.text)
antes = n_com()
check('C-03 división fija: otra división y "Todo el colegio" → 403, también con X-Nivel, sin crear nada',
      publicar(PSI_P, 'secundaria').status_code == 403 and publicar(PSI_P, 'general').status_code == 403
      and publicar(PSI_P, 'secundaria', nivel='secundaria').status_code == 403 and n_com() == antes, '')
check('C-04 tanda fija: publica igual que sin tanda (sin bloqueo por tanda)',
      publicar(PSI_TANDA, 'primaria', titulo='De psi con tanda').status_code == 201, '')
check('C-05 ...y su comunicado no se restringe por tanda al leerlo',
      'De psi con tanda' in titulos(PROF_P) and 'De psi con tanda' in titulos(PROF_N), '')
db.expire_all()
avisos = {n.usuario_id for n in db.query(M.Notificacion).filter_by(titulo='📢 Com psi_p primaria')}
check('C-06 lectura por división: el de Primaria lo ve Primaria/nivel vacío, no Secundaria fija',
      {'Com psi_p primaria'} <= titulos(PROF_P) & titulos(PROF_N)
      and 'Com psi_p primaria' not in titulos(PROF_S) | titulos(PSI_S), '')
check('C-07 notificación por división: llega a Primaria y nivel vacío, no a Secundaria fija',
      ids(PROF_P, PROF_N) <= avisos and not (avisos & ids(PROF_S, PSI_S)), avisos)
check('C-08 Coordinación (global en Comunicación) y Dirección lo ven',
      'Com psi_p primaria' in titulos(COORD_S) and 'Com psi_p primaria' in titulos(DIR), '')
check('C-09 otro colegio no lo ve', 'Com psi_p primaria' not in titulos(DIR_O), '')
ID_P = r_p.json()['id']
check('C-10 edita su propio comunicado',
      client.put('/api/comunicados/%d' % ID_P, json={'titulo': 'Editado'}, headers=h(PSI_P)).status_code == 200, '')
check('C-11 no lo cambia a otra división ni a "Todo el colegio" (403)',
      client.put('/api/comunicados/%d' % ID_P, json={'tipo': 'secundaria'}, headers=h(PSI_P)).status_code == 403
      and client.put('/api/comunicados/%d' % ID_P, json={'tipo': 'general'}, headers=h(PSI_P)).status_code == 403, '')
id_dir = publicar(DIR, 'primaria').json()['id']
id_amb = r_amb['primaria'].json()['id']
check('C-12 comunicados ajenos: 404 al editar o eliminar (aunque sean de su división)',
      client.put('/api/comunicados/%d' % id_dir, json={'titulo': 'x'}, headers=h(PSI_P)).status_code == 404
      and client.delete('/api/comunicados/%d' % id_dir, headers=h(PSI_P)).status_code == 404
      and client.delete('/api/comunicados/%d' % id_amb, headers=h(PSI_P)).status_code == 404, '')
db.expire_all()
check('C-13 ...y quedan intactos', db.get(M.Comunicado, id_dir).activo and db.get(M.Comunicado, id_amb).activo
      and db.get(M.Comunicado, id_dir).titulo == 'Com dir primaria', '')
PSI_CAMBIO = usuario(COL, 'psi_cambio', 'psicologia', 'primaria')
db.commit()
id_c = publicar(PSI_CAMBIO, 'primaria').json()['id']
PSI_CAMBIO.nivel_asignado = 'secundaria'
db.commit()
r_ed = client.put('/api/comunicados/%d' % id_c, json={'titulo': 'x'}, headers=h(PSI_CAMBIO))
check('C-14 si cambia su división: editar lo anterior → 403 con motivo explícito',
      r_ed.status_code == 403 and 'puede retirarlo' in r_ed.json().get('error', ''), r_ed.text)
check('C-15 ...pero puede retirarlo (no amplía permisos)',
      client.delete('/api/comunicados/%d' % id_c, headers=h(PSI_CAMBIO)).status_code == 200, '')
check('C-16 otro colegio: 404 al editar o eliminar',
      client.put('/api/comunicados/%d' % ID_P, json={'titulo': 'x'}, headers=h(PSI_O)).status_code == 404
      and client.delete('/api/comunicados/%d' % ID_P, headers=h(PSI_O)).status_code == 404, '')
check('C-17 elimina su propio comunicado',
      client.delete('/api/comunicados/%d' % id_amb, headers=h(PSI_AMB)).status_code == 200, '')

print("\n=== DIRECCIÓN Y COORDINACIÓN SIN CAMBIOS ===")
check('R-01 Dirección y Coordinación publican los tres alcances',
      all(publicar(u, t).status_code == 201 for u in (DIR, COORD_S) for t in ('general', 'primaria', 'secundaria')), '')
check('R-02 Coordinación sigue editando un comunicado de otro autor (comportamiento previo)',
      client.put('/api/comunicados/%d' % ID_P, json={'titulo': 'Editado'}, headers=h(COORD)).status_code == 200, '')
cod, _j, d, _ = masivo(COORD_S, 'profesor')
check('R-03 "Por rol" de Coordinación fija sigue llegando a todo el colegio', set(d) == ids(PROF_P, PROF_S, PROF_N), d)
DIR3 = usuario(COL3, 'dir3', 'direccion')     # colegio sin profesores
db.commit()
check('R-04 Dirección: el mensaje de "sin usuarios" no cambia',
      masivo(DIR3, 'profesor')[1] == {'error': 'No hay usuarios con el rol profesor'}, '')
db.close()

ok = sum(1 for _, r in RES if r)
print('\nRESULTADO PSI-COM-1: %d PASARON / %d FALLARON' % (ok, len(RES) - ok))
sys.exit(0 if ok == len(RES) else 1)
