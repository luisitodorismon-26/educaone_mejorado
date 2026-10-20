# -*- coding: utf-8 -*-
"""
EducaOne — PSI-COM-1: Psicología publica comunicados y envía mensajes "Por rol".

Reutiliza los flujos de Coordinación sin su excepción global: el alcance es
la configuración de la cuenta (nivel_asignado / tanda_id; vacío = ambos /
todas). Docentes: por asignaciones activas del año vigente.

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

TMP = aislar_base_de_datos('psi_com1')

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


def colegio(nombre):
    return add(M.Colegio(nombre=nombre, codigo=nombre.lower(), activo=True))


def usuario(col, username, role, nivel=None, tanda=None):
    return add(M.Usuario(colegio_id=col.id, username=username, password_hash='x', nombre=username,
                         apellido='T', role=role, activo=True, must_change_password=False, token_version=0,
                         nivel_asignado=nivel, tanda_id=tanda.id if tanda else None))


COL, OTRO = colegio('C1'), colegio('C2')
ANO = add(M.AnoEscolar(colegio_id=COL.id, nombre='2026-2027', activo=True))
T_M = add(M.Tanda(colegio_id=COL.id, nombre='Matutina', hora_inicio='07:30', hora_fin='12:30', activo=True))
T_V = add(M.Tanda(colegio_id=COL.id, nombre='Vespertina', hora_inicio='14:00', hora_fin='18:00', activo=True))
G_P = add(M.Grado(colegio_id=COL.id, nombre='1ro Primaria', nivel='primaria', orden=7))
G_S = add(M.Grado(colegio_id=COL.id, nombre='1ro Secundaria', nivel='secundaria', orden=1))
ASIG = add(M.Asignatura(colegio_id=COL.id, nombre='Lengua', codigo='LE', area='X', activo=True))


def curso(g, t):
    return add(M.Curso(colegio_id=COL.id, nombre='A', grado_id=g.id, tanda_id=t.id, ano_escolar_id=ANO.id, activo=True))


C_PM, C_PV, C_SM, C_SV = curso(G_P, T_M), curso(G_P, T_V), curso(G_S, T_M), curso(G_S, T_V)

DIR = usuario(COL, 'dir', 'direccion')
COORD = usuario(COL, 'coord', 'coordinador')
COORD_S = usuario(COL, 'coord_s', 'coordinador', 'secundaria')
SECRE = usuario(COL, 'secre', 'secretaria')
SECRE_V = usuario(COL, 'secre_v', 'secretaria', None, T_V)
PSI_AMB = usuario(COL, 'psi_ambos', 'psicologia')                 # Ambos niveles + todas las tandas
PSI_P = usuario(COL, 'psi_p', 'psicologia', 'primaria')
PSI_PM = usuario(COL, 'psi_pm', 'psicologia', 'primaria', T_M)    # división + tanda fijas
PSI_S = usuario(COL, 'psi_s', 'psicologia', 'secundaria')
PROF_PM = usuario(COL, 'prof_pm', 'profesor')                     # nivel vacío, asignado en Primaria-Matutina
PROF_SV = usuario(COL, 'prof_sv', 'profesor', 'secundaria')
PROF_MIX = usuario(COL, 'prof_mix', 'profesor')                   # Primaria-Vespertina + Secundaria-Matutina
PROF_NULL = usuario(COL, 'prof_null', 'profesor')                 # sin asignaciones ni nivel
PROF_PSIN = usuario(COL, 'prof_psin', 'profesor', 'primaria')     # sin asignaciones, perfil Primaria
DIR_O = usuario(OTRO, 'dir_o', 'direccion')
PROF_O = usuario(OTRO, 'prof_o', 'profesor', 'primaria')
PSI_O = usuario(OTRO, 'psi_o', 'psicologia')
for prof, cur in ((PROF_PM, C_PM), (PROF_SV, C_SV), (PROF_MIX, C_PV), (PROF_MIX, C_SM)):
    add(M.AsignacionProfesor(colegio_id=COL.id, profesor_id=prof.id, curso_id=cur.id,
                             asignatura_id=ASIG.id, ano_escolar_id=ANO.id, activo=True))
db.commit()


def h(u, nivel=None):
    hd = {'Authorization': 'Bearer ' + create_token(u)}
    if nivel:
        hd['X-Nivel'] = nivel
    return hd


_n = [0]


def masivo(u, rol, nivel=None, **extra):
    """Envía "Por rol" y devuelve (status, {destinatarios}, asunto)."""
    _n[0] += 1
    asunto = 'Aviso %d' % _n[0]
    r = client.post('/api/mensajes/masivo', json=dict({'rol': rol, 'asunto': asunto, 'contenido': 'Texto'}, **extra),
                    headers=h(u, nivel))
    db.expire_all()
    dest = [m.destinatario_id for m in db.query(M.Mensaje).filter_by(remitente_id=u.id, asunto=asunto)]
    return r.status_code, dest, asunto


def ids(*us):
    return {u.id for u in us}


print("\n=== MENSAJE 'POR ROL' ===")
cod, d_coord, _ = masivo(COORD, 'profesor')
cod2, d_amb, _ = masivo(PSI_AMB, 'profesor')
check('M-01 Psicología "Ambos niveles + todas las tandas" llega a los mismos docentes que Coordinación',
      cod2 == 201 and set(d_amb) == set(d_coord) == ids(PROF_PM, PROF_SV, PROF_MIX, PROF_NULL, PROF_PSIN),
      (cod2, d_amb, d_coord))
cod, d, _ = masivo(PSI_P, 'profesor')
check('M-02 Psicología Primaria: docentes con asignación en Primaria (+ perfil Primaria sin asignaciones)',
      cod == 201 and set(d) == ids(PROF_PM, PROF_MIX, PROF_PSIN), d)
check('M-03 ...un docente con nivel vacío y sin asignaciones NO cuenta como global', PROF_NULL.id not in d, d)
cod, d, _ = masivo(PSI_PM, 'profesor')
check('M-04 Psicología Primaria + Matutina: solo docentes con un curso Primaria-Matutina', cod == 201
      and set(d) == ids(PROF_PM), d)
cod, d, _ = masivo(PSI_S, 'profesor')
check('M-05 Psicología Secundaria: docentes con asignación en Secundaria', set(d) == ids(PROF_SV, PROF_MIX), d)
cod, d, _ = masivo(PSI_S, 'coordinador')
check('M-06 roles no docentes: su división o "Ambos niveles"', set(d) == ids(COORD, COORD_S), d)
cod, d, _ = masivo(PSI_P, 'coordinador')
check('M-07 ...un coordinador fijo en la otra división queda fuera', set(d) == ids(COORD), d)
cod, d, _ = masivo(PSI_PM, 'secretaria')
check('M-08 tanda fija: "Todas las tandas" entra, otra tanda no', set(d) == ids(SECRE), d)
cod, d, _ = masivo(PSI_P, 'direccion')
check('M-09 Dirección (ambos niveles, todas las tandas) recibe', set(d) == ids(DIR), d)
cod, d, _ = masivo(PSI_P, 'profesor', nivel='secundaria', nivel_asignado='secundaria', tanda_id=None)
check('M-10 X-Nivel y campos extra del formulario no amplían el alcance', set(d) == ids(PROF_PM, PROF_MIX, PROF_PSIN), d)
cod, d, _ = masivo(PSI_P, 'psicologia')
check('M-11 sin autoenvío; psicología de la otra división fuera', PSI_P.id not in d
      and set(d) == ids(PSI_AMB, PSI_PM), d)
cod, d, asunto = masivo(PSI_AMB, 'profesor')
db.expire_all()
_notif = [n.usuario_id for n in db.query(M.Notificacion).filter(M.Notificacion.tipo == 'mensaje',
                                                                M.Notificacion.usuario_id.in_(d)).all()]
check('M-12 sin duplicados: un mensaje por destinatario', len(d) == len(set(d)) == 5, d)
check('M-13 nunca sale del colegio', not (set(d_amb) | set(d)) & ids(DIR_O, PROF_O, PSI_O), '')
cod, d, _ = masivo(PSI_PM, 'coordinador')
check('M-14 sin destinatarios en su alcance: 404 y nada enviado', cod in (201, 404) and (cod == 201) == bool(d), (cod, d))
check('M-15 rol inválido sigue en 400', masivo(PSI_AMB, 'superadmin')[0] == 400, '')
check('M-16 profesor y secretaría siguen sin "Por rol" (403)',
      masivo(PROF_PM, 'profesor')[0] == 403 and masivo(SECRE, 'profesor')[0] == 403, '')
check('M-17 mensaje individual de Psicología sin cambios (a cualquiera del colegio)',
      client.post('/api/mensajes', json={'destinatario_id': PROF_SV.id, 'asunto': 'A', 'contenido': 'B'},
                  headers=h(PSI_P)).status_code == 201, '')
check('M-18 Psicología de otro colegio no alcanza a este colegio',
      not (set(masivo(PSI_O, 'profesor')[1]) & ids(PROF_PM, PROF_SV, PROF_MIX, PROF_NULL, PROF_PSIN)), '')

print("\n=== COMUNICADOS ===")


def publicar(u, tipo, nivel=None):
    return client.post('/api/comunicados', json={'titulo': 'Com %s %s' % (u.username, tipo), 'contenido': 'x',
                                                 'tipo': tipo}, headers=h(u, nivel))


def n_comunicados():
    db.expire_all()
    return db.query(M.Comunicado).count()


r_amb = {t: publicar(PSI_AMB, t) for t in ('general', 'primaria', 'secundaria')}
check('C-01 "Ambos niveles" publica en los tres alcances', all(r.status_code == 201 for r in r_amb.values()),
      {t: r.text for t, r in r_amb.items()})
r_p = publicar(PSI_P, 'primaria')
check('C-02 división fija publica en su división', r_p.status_code == 201, r_p.text)
antes = n_comunicados()
check('C-03 división fija: la otra división y "Todo el colegio" → 403 (también con X-Nivel)',
      publicar(PSI_P, 'secundaria').status_code == 403 and publicar(PSI_P, 'general').status_code == 403
      and publicar(PSI_P, 'secundaria', nivel='secundaria').status_code == 403
      and n_comunicados() == antes, '')
check('C-04 tanda fija: no publica (403) y no crea nada',
      publicar(PSI_PM, 'primaria').status_code == 403 and n_comunicados() == antes, '')
ID_P = r_p.json()['id']
ok_edit = client.put('/api/comunicados/%d' % ID_P, json={'titulo': 'Editado'}, headers=h(PSI_P)).status_code
check('C-05 edita su propio comunicado', ok_edit == 200, ok_edit)
check('C-06 no puede cambiarlo a otra división ni a "Todo el colegio" (403)',
      client.put('/api/comunicados/%d' % ID_P, json={'tipo': 'secundaria'}, headers=h(PSI_P)).status_code == 403
      and client.put('/api/comunicados/%d' % ID_P, json={'tipo': 'general'}, headers=h(PSI_P)).status_code == 403, '')
id_dir = publicar(DIR, 'primaria').json()['id']
id_amb_p = r_amb['primaria'].json()['id']
check('C-07 no edita ni elimina comunicados ajenos, aunque sean de su división (404)',
      client.put('/api/comunicados/%d' % id_dir, json={'titulo': 'x'}, headers=h(PSI_P)).status_code == 404
      and client.delete('/api/comunicados/%d' % id_dir, headers=h(PSI_P)).status_code == 404
      and client.put('/api/comunicados/%d' % id_amb_p, json={'titulo': 'x'}, headers=h(PSI_P)).status_code == 404, '')
db.expire_all()
check('C-08 ...y el comunicado ajeno queda intacto',
      db.get(M.Comunicado, id_dir).titulo == 'Com dir primaria' and db.get(M.Comunicado, id_dir).activo, '')
check('C-09 Psicología de la otra división no ve ni toca el comunicado (404)',
      client.delete('/api/comunicados/%d' % ID_P, headers=h(PSI_S)).status_code == 404, '')
# Cambio de configuración: el permiso se evalúa con el alcance ACTUAL.
PSI_CAMBIO = usuario(COL, 'psi_cambio', 'psicologia', 'primaria')
db.commit()
id_cambio = publicar(PSI_CAMBIO, 'primaria').json()['id']
PSI_CAMBIO.nivel_asignado = 'secundaria'
db.commit()
check('C-10 si su división cambia, ya no edita lo publicado en la anterior (404)',
      client.put('/api/comunicados/%d' % id_cambio, json={'titulo': 'x'}, headers=h(PSI_CAMBIO)).status_code == 404, '')
check('C-11 elimina su propio comunicado', client.delete('/api/comunicados/%d' % id_amb_p,
                                                         headers=h(PSI_AMB)).status_code == 200, '')
check('C-12 otro colegio: 404 al editar o eliminar',
      client.put('/api/comunicados/%d' % ID_P, json={'titulo': 'x'}, headers=h(PSI_O)).status_code == 404
      and client.delete('/api/comunicados/%d' % ID_P, headers=h(PSI_O)).status_code == 404, '')


def titulos(u):
    return {c['titulo'] for c in client.get('/api/comunicados', headers=h(u)).json()}


check('C-13 lectura: el comunicado de Primaria no lo ve un usuario fijo de Secundaria',
      'Editado' in titulos(PSI_AMB) and 'Editado' not in titulos(PSI_S) and 'Editado' not in titulos(PROF_SV)
      and 'Editado' in titulos(COORD_S), '')  # Coordinación es global en Comunicación (COM1)
check('C-14 otro colegio no lo ve', 'Editado' not in titulos(DIR_O), '')
db.expire_all()
_avisos = {n.usuario_id for n in db.query(M.Notificacion).filter_by(titulo='📢 Com psi_p primaria')}
check('C-15 aviso del comunicado de Primaria: no llega a quien está fijo en Secundaria',
      not (_avisos & ids(COORD_S, PROF_SV, PSI_S)) and PSI_AMB.id in _avisos, _avisos)

print("\n=== DIRECCIÓN Y COORDINACIÓN SIN CAMBIOS ===")
check('R-01 Dirección y Coordinación publican los tres alcances',
      all(publicar(u, t).status_code == 201 for u in (DIR, COORD_S) for t in ('general', 'primaria', 'secundaria')), '')
check('R-02 Coordinación sigue editando un comunicado de otro autor (comportamiento previo)',
      client.put('/api/comunicados/%d' % ID_P, json={'titulo': 'Editado'}, headers=h(COORD)).status_code == 200, '')
cod, d, _ = masivo(COORD_S, 'profesor')
check('R-03 "Por rol" de Coordinación con división fija sigue llegando a todo el colegio (sin cambios)',
      cod == 201 and set(d) == ids(PROF_PM, PROF_SV, PROF_MIX, PROF_NULL, PROF_PSIN), d)
db.close()

ok = sum(1 for _, r in RES if r)
print('\nRESULTADO PSI-COM-1: %d PASARON / %d FALLARON' % (ok, len(RES) - ok))
sys.exit(0 if ok == len(RES) else 1)
