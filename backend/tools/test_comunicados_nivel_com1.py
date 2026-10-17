# -*- coding: utf-8 -*-
"""
EducaOne — COM1: comunicados por nivel (Todo el colegio / Primaria / Secundaria).

Reutiliza `Comunicado.tipo`: 'general' | 'primaria' | 'secundaria'; NULL o un
valor legacy desconocido = 'general'. La autoridad es el backend con
`nivel_asignado`; Dirección es global. El filtro de nivel va ENCIMA de los
flags por rol (para_profesores, ...). Editar no vuelve a notificar.

Base temporal aislada. Nunca producción.

Uso:
    cd backend
    python tools/test_comunicados_nivel_com1.py
"""
import os
import sys

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(BK, "tools"))

from test_utils import aislar_base_de_datos  # noqa: E402

TMP = aislar_base_de_datos('com1_comunicados')

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


def colegio(nombre):
    c = M.Colegio(nombre=nombre, codigo=nombre.lower(), activo=True)
    db.add(c)
    db.flush()
    return c


def usuario(col, username, role, nivel=None):
    u = M.Usuario(colegio_id=col.id, username=username, password_hash='x', nombre=username,
                  apellido='T', role=role, activo=True, must_change_password=False,
                  token_version=0, nivel_asignado=nivel)
    db.add(u)
    db.flush()
    return u


COL = colegio('C1')
OTRO = colegio('C2')
DIR = usuario(COL, 'c1_dir', 'direccion')
CP = usuario(COL, 'c1_cp', 'coordinador', 'primaria')
CS = usuario(COL, 'c1_cs', 'coordinador', 'secundaria')
CN = usuario(COL, 'c1_cn', 'coordinador')                 # sin división fija
PP = usuario(COL, 'c1_pp', 'profesor', 'primaria')
PS = usuario(COL, 'c1_ps', 'profesor', 'secundaria')
PN = usuario(COL, 'c1_pn', 'profesor')                    # sin división
SECP = usuario(COL, 'c1_secp', 'secretaria', 'primaria')
PSIS = usuario(COL, 'c1_psis', 'psicologia', 'secundaria')
DIR2 = usuario(OTRO, 'c2_dir', 'direccion')
# Comunicados LEGACY, escritos directo en la base como los de producción.
LEG_GEN = M.Comunicado(colegio_id=COL.id, autor_id=DIR.id, titulo='Legacy general', contenido='x',
                       tipo='general')
LEG_NULL = M.Comunicado(colegio_id=COL.id, autor_id=DIR.id, titulo='Legacy nulo', contenido='x', tipo=None)
LEG_RARO = M.Comunicado(colegio_id=COL.id, autor_id=DIR.id, titulo='Legacy raro', contenido='x', tipo='urgente')
db.add_all([LEG_GEN, LEG_NULL, LEG_RARO])
db.commit()


def h(u):
    return {'Authorization': 'Bearer ' + create_token(u)}


def crear(u, tipo, **extra):
    body = dict({'titulo': 'C-%s-%s' % (u.username, tipo), 'contenido': 'contenido'}, **extra)
    if tipo is not None:
        body['tipo'] = tipo
    return client.post('/api/comunicados', json=body, headers=h(u))


def titulos(u):
    return {c['titulo'] for c in client.get('/api/comunicados', headers=h(u)).json()}


def notifs(u):
    db.expire_all()
    return db.query(M.Notificacion).filter_by(usuario_id=u.id, tipo='comunicado').count()


print("\n=== PUBLICAR ===")
r_gen = crear(DIR, 'general')
r_pri = crear(DIR, 'primaria')
r_sec = crear(DIR, 'secundaria')
check('CO-00 Dirección publica en los tres alcances',
      (r_gen.status_code, r_pri.status_code, r_sec.status_code) == (201, 201, 201),
      (r_gen.text, r_pri.text, r_sec.text))
ID_GEN, ID_PRI, ID_SEC = r_gen.json()['id'], r_pri.json()['id'], r_sec.json()['id']
T_GEN, T_PRI, T_SEC = 'C-c1_dir-general', 'C-c1_dir-primaria', 'C-c1_dir-secundaria'
check('CO-07 coordinador Primaria puede crear Primaria', crear(CP, 'primaria').status_code == 201, '')
check('CO-08 coordinador Primaria NO puede crear Secundaria (API directa)',
      crear(CP, 'secundaria').status_code == 403, '')
check('CO-09 coordinador Primaria NO puede crear "Todo el colegio"',
      crear(CP, 'general').status_code == 403 and crear(CP, None).status_code == 403, '')
check('CO-10 coordinador sin división crea cualquiera',
      all(crear(CN, t).status_code == 201 for t in ('general', 'primaria', 'secundaria')), '')
check('CO-10b alcance inválido → 400', crear(DIR, 'todos').status_code == 400, '')
check('CO-10c profesor no publica (regla de siempre)', crear(PP, 'primaria').status_code == 403, '')

print("\n=== VER ===")
tp, ts, tn, td = titulos(PP), titulos(PS), titulos(PN), titulos(DIR)
check('CO-01 general visible para Primaria y Secundaria', T_GEN in tp and T_GEN in ts, '')
check('CO-02 Primaria visible para usuario Primaria', T_PRI in tp, '')
check('CO-03 Primaria invisible para usuario fijo Secundaria', T_PRI not in ts, ts)
check('CO-04 Secundaria invisible para usuario fijo Primaria', T_SEC not in tp, tp)
check('CO-05 usuario sin nivel ve los tres', {T_GEN, T_PRI, T_SEC} <= tn, tn)
check('CO-06 Dirección ve los tres', {T_GEN, T_PRI, T_SEC} <= td, td)
check('CO-06b secretaría y psicología fijas respetan su nivel',
      T_SEC not in titulos(SECP) and T_PRI in titulos(SECP)
      and T_PRI not in titulos(PSIS) and T_SEC in titulos(PSIS), '')
check('CO-16 legacy "general" sigue visible para todos', all('Legacy general' in titulos(u) for u in (PP, PS, CP, CS)), '')
check('CO-17 legacy NULL y valor desconocido NO desaparecen (= general)',
      all({'Legacy nulo', 'Legacy raro'} <= titulos(u) for u in (PP, PS, CP, CS)), '')
alc = {c['titulo']: c.get('alcance') for c in client.get('/api/comunicados', headers=h(DIR)).json()}
check('CO-17b el GET informa el alcance (legacy → general)',
      alc[T_PRI] == 'primaria' and alc['Legacy nulo'] == 'general' and alc['Legacy raro'] == 'general', alc)

# Flags por rol: siguen mandando por debajo del nivel.
r = crear(DIR, 'primaria', para_profesores=False)
check('CO-11 flags por rol intactos: para_profesores=False no llega a profesores',
      'C-c1_dir-primaria' in titulos(CP) and
      sum(1 for c in client.get('/api/comunicados', headers=h(PP)).json() if c['id'] == r.json()['id']) == 0, '')

print("\n=== OTRO COLEGIO Y ACCESO DIRECTO ===")
check('CO-12 otro colegio no ve ni marca los comunicados',
      not ({T_GEN, T_PRI, T_SEC} & titulos(DIR2))
      and client.post('/api/comunicados/%d/marcar-leido' % ID_GEN, headers=h(DIR2)).status_code == 404, '')
r13 = client.post('/api/comunicados/%d/marcar-leido' % ID_SEC, headers=h(PP))
check('CO-13 marcar leído un comunicado del nivel contrario falla (404)', r13.status_code == 404, r13.text)
check('CO-13b ...y no deja rastro de lectura',
      db.query(M.ComunicadoLeido).filter_by(usuario_id=PP.id, comunicado_id=ID_SEC).count() == 0, '')
check('CO-13c marcar leído uno visible sí funciona',
      client.post('/api/comunicados/%d/marcar-leido' % ID_PRI, headers=h(PP)).status_code == 200, '')

print("\n=== NOTIFICACIONES ===")
db.expire_all()
n_sec_pp = db.query(M.Notificacion).filter(M.Notificacion.usuario_id == PP.id,
                                           M.Notificacion.titulo == '📢 ' + T_SEC).count()
n_pri_ps = db.query(M.Notificacion).filter(M.Notificacion.usuario_id == PS.id,
                                           M.Notificacion.titulo == '📢 ' + T_PRI).count()
n_pri_pn = db.query(M.Notificacion).filter(M.Notificacion.usuario_id == PN.id,
                                           M.Notificacion.titulo.in_(['📢 ' + T_PRI, '📢 ' + T_SEC])).count()
n_pri_pp = db.query(M.Notificacion).filter(M.Notificacion.usuario_id == PP.id,
                                           M.Notificacion.titulo == '📢 ' + T_PRI).count()
check('CO-N1 Secundaria no notifica a quien está fijo en Primaria (y viceversa)',
      n_sec_pp == 0 and n_pri_ps == 0, (n_sec_pp, n_pri_ps))
check('CO-N2 Primaria notifica a Primaria; sin nivel recibe ambos', n_pri_pp == 1 and n_pri_pn == 2,
      (n_pri_pp, n_pri_pn))

print("\n=== EDITAR ===")
antes = (notifs(PP), notifs(PS), notifs(PN))
r = client.put('/api/comunicados/%d' % ID_PRI, json={'tipo': 'secundaria'}, headers=h(DIR))
check('CO-14 Dirección cambia el alcance Primaria → Secundaria', r.status_code == 200
      and T_PRI not in titulos(PP) and T_PRI in titulos(PS), r.text)
check('CO-15 editar NO crea notificaciones nuevas (ni duplicadas)',
      (notifs(PP), notifs(PS), notifs(PN)) == antes, (antes, (notifs(PP), notifs(PS), notifs(PN))))
id_cp = crear(CP, 'primaria', titulo='De coord P').json()['id']
check('CO-14b coordinador Primaria NO puede pasar su comunicado a Secundaria',
      client.put('/api/comunicados/%d' % id_cp, json={'tipo': 'secundaria'}, headers=h(CP)).status_code == 403, '')
check('CO-14c ...ni a "Todo el colegio"',
      client.put('/api/comunicados/%d' % id_cp, json={'tipo': 'general'}, headers=h(CP)).status_code == 403, '')
check('CO-14d coordinador Primaria NO edita ni borra uno de Secundaria por ID (404)',
      client.put('/api/comunicados/%d' % ID_SEC, json={'titulo': 'x'}, headers=h(CP)).status_code == 404
      and client.delete('/api/comunicados/%d' % ID_SEC, headers=h(CP)).status_code == 404, '')
check('CO-14e editar el texto sin cambiar el alcance sigue funcionando',
      client.put('/api/comunicados/%d' % id_cp, json={'titulo': 'De coord P v2', 'tipo': 'primaria'},
                 headers=h(CP)).status_code == 200, '')

print("\n=== MENSAJES (sin cambios) ===")
r = client.post('/api/mensajes', json={'destinatario_id': PS.id, 'asunto': 'Hola', 'contenido': 'Mensaje'},
                headers=h(PP))
check('CO-18 mensajes individuales siguen funcionando igual (cruzan niveles como antes)',
      r.status_code in (200, 201), r.text)
db.close()

ok = sum(1 for _, r in RES if r)
print('\nRESULTADO COM1: %d PASARON / %d FALLARON' % (ok, len(RES) - ok))
sys.exit(0 if ok == len(RES) else 1)
