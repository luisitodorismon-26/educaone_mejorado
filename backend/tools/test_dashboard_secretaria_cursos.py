# -*- coding: utf-8 -*-
"""
EducaOne — Secretaría: dashboard con ambos niveles y Horarios con selector local.

EL DEFECTO
    /api/dashboard/secretaria enviaba solo `Curso.nombre` (la SECCIÓN: "A" o
    vacía). El frontend lo completaba cruzando con /api/cursos, que aplica el
    lente de nivel de la cabecera X-Nivel; con un valor residual en el
    navegador, los cursos del otro nivel quedaban como "A".

LA CORRECCIÓN (alcance mínimo)
    · El dashboard compone el rótulo en el backend desde Curso -> Grado ->
      Tanda, en UNA consulta con el conteo agrupado, y no aplica lente:
      Secretaría ve Primaria y Secundaria a la vez.
    · `nivel_efectivo` NO cambia (sigue igual que en main para los 15
      endpoints que lo usan).
    · Horarios: Secretaría elige Primaria | Secundaria con un selector LOCAL
      de esa página; sus peticiones llevan ese X-Nivel y el interceptor no lo
      pisa con el valor global. Ninguna otra pantalla cambia.

Base temporal aislada. Nunca producción.

Uso:
    cd backend
    python tools/test_dashboard_secretaria_cursos.py
"""
import asyncio
import os
import sys

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(BK, "tools"))

from test_utils import aislar_base_de_datos  # noqa: E402

TMP = aislar_base_de_datos('dash_sec')

from database import engine, SessionLocal  # noqa: E402
from test_utils import verificar_engine_aislado  # noqa: E402

verificar_engine_aislado(engine, TMP)

import models as M  # noqa: E402
import app as APP  # noqa: E402

M.Base.metadata.create_all(bind=engine)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import event  # noqa: E402
from auth import create_token  # noqa: E402

PASARON, FALLARON = [], []


def check(nombre, cond, detalle=''):
    if cond:
        PASARON.append(nombre)
        print("  PASA   %-70s %s" % (nombre, detalle))
    else:
        FALLARON.append(nombre)
        print("  FALLA  %-70s %s" % (nombre, detalle))


db = SessionLocal()


def colegio(codigo):
    c = M.Colegio(nombre='C-' + codigo, codigo=codigo, activo=True,
                  plan_primaria=True, plan_secundaria=True)
    db.add(c)
    db.flush()
    ano = M.AnoEscolar(colegio_id=c.id, nombre='2026-2027', activo=True, cerrado=False)
    db.add(ano)
    db.flush()
    return c, ano


def usuario(col, username, rol, nivel=None):
    u = M.Usuario(colegio_id=col.id if col else None, username=username, password_hash='x',
                  nombre=rol, role=rol, activo=True, nivel_asignado=nivel,
                  must_change_password=False, token_version=0)
    db.add(u)
    db.flush()
    return u


COL, ANO = colegio('DSEC1')
TANDAS = {}
for nombre in ('Matutina', 'Vespertina'):
    t = M.Tanda(colegio_id=COL.id, nombre=nombre, hora_inicio='07:30', hora_fin='12:30')
    db.add(t)
    db.flush()
    TANDAS[nombre] = t
GRADOS = {}
for i, (nombre, nivel) in enumerate((('1ro Primaria', 'primaria'), ('6to Primaria', 'primaria'),
                                     ('2do Secundaria', 'secundaria'),
                                     ('4to Secundaria', 'secundaria')), start=1):
    g = M.Grado(colegio_id=COL.id, nombre=nombre, nivel=nivel, orden=i, activo=True)
    db.add(g)
    db.flush()
    GRADOS[nombre] = g
ASIG = M.Asignatura(colegio_id=COL.id, nombre='Matemática', codigo='MAT', activo=True)
PROF = usuario(COL, 'ds_prof', 'profesor')
db.add(ASIG)
db.flush()

# (grado, sección, tanda, estudiantes, activo)
PLAN = [
    ('1ro Primaria', 'A', 'Matutina', 2, True),
    ('1ro Primaria', 'A', 'Vespertina', 0, True),     # 0 estudiantes
    ('6to Primaria', 'A', 'Vespertina', 3, True),
    ('2do Secundaria', 'A', 'Matutina', 0, True),     # 0 estudiantes
    ('2do Secundaria', 'A', 'Vespertina', 4, True),
    ('4to Secundaria', '', 'Matutina', 1, True),      # sección vacía
    ('4to Secundaria', 'B', 'Vespertina', 0, False),  # INACTIVO: fuera (igual que antes)
]
ESPERADO = {}
NIVEL_CURSO = {}
EST_NIVEL = {'primaria': set(), 'secundaria': set()}
_n = [0]
for grado, seccion, tanda, n_est, activo in PLAN:
    c = M.Curso(colegio_id=COL.id, nombre=seccion, grado_id=GRADOS[grado].id,
                tanda_id=TANDAS[tanda].id, ano_escolar_id=ANO.id, activo=activo)
    db.add(c)
    db.flush()
    niv = GRADOS[grado].nivel
    NIVEL_CURSO[c.id] = niv
    for _ in range(n_est):
        _n[0] += 1
        e = M.Estudiante(colegio_id=COL.id, matricula='DS-%d' % _n[0], nombre='E',
                         apellido=str(_n[0]), curso_id=c.id, no_lista=_n[0],
                         activo=True, condicion='activo')
        db.add(e)
        db.flush()
        if activo:
            EST_NIVEL[niv].add(e.id)
    if activo:
        base = ' '.join(p for p in (grado, seccion) if p)
        ESPERADO[c.id] = (base + ' · ' + tanda, n_est)
        # Un bloque de horario por curso activo, para /api/horarios.
        db.add(M.Horario(colegio_id=COL.id, profesor_id=PROF.id, curso_id=c.id,
                         asignatura_id=ASIG.id, dia='Lunes', hora_inicio='08:00',
                         hora_fin='08:45', activo=True))
CURSOS_PRI = {cid for cid in ESPERADO if NIVEL_CURSO[cid] == 'primaria'}
CURSOS_SEC = {cid for cid in ESPERADO if NIVEL_CURSO[cid] == 'secundaria'}
# El profesor imparte SOLO en 1ro Primaria A Matutina.
_c_prof = next(cid for cid, (r, _) in ESPERADO.items() if r == '1ro Primaria A · Matutina')
db.add(M.AsignacionProfesor(colegio_id=COL.id, profesor_id=PROF.id, curso_id=_c_prof,
                            asignatura_id=ASIG.id, ano_escolar_id=ANO.id, activo=True))

U = {
    'secretaria': usuario(COL, 'ds_sec', 'secretaria'),
    'direccion': usuario(COL, 'ds_dir', 'direccion'),
    'coordinador': usuario(COL, 'ds_coord', 'coordinador'),
    'psicologia': usuario(COL, 'ds_psi', 'psicologia'),
    'coord_pri_fijo': usuario(COL, 'ds_coord_p', 'coordinador', 'primaria'),
    'sec_sec_fija': usuario(COL, 'ds_sec_s', 'secretaria', 'secundaria'),
    'superadmin': usuario(None, 'ds_sa', 'superadmin'),
}

# Otro colegio con un curso de Primaria: nunca debe aparecer en el de arriba.
COL2, ANO2 = colegio('DSEC2')
t2 = M.Tanda(colegio_id=COL2.id, nombre='Matutina', hora_inicio='07:30', hora_fin='12:30')
g2 = M.Grado(colegio_id=COL2.id, nombre='3ro Primaria', nivel='primaria', orden=1, activo=True)
db.add_all([t2, g2])
db.flush()
C_AJENO = M.Curso(colegio_id=COL2.id, nombre='A', grado_id=g2.id, tanda_id=t2.id,
                  ano_escolar_id=ANO2.id, activo=True)
db.add(C_AJENO)
db.commit()

client = TestClient(APP.app)


def hdr(u, nivel=None):
    h = {'Authorization': 'Bearer ' + create_token(u)}
    if nivel:
        h['X-Nivel'] = nivel
    return h


def ids_cursos(u, nivel=None):
    APP.cache_clear('cursos:')
    r = client.get('/api/cursos', headers=hdr(u, nivel))
    return {c['id'] for c in r.json() if c['id'] in ESPERADO} if r.status_code == 200 else None


def ids_estudiantes(u, nivel=None):
    r = client.get('/api/estudiantes', headers=hdr(u, nivel))
    if r.status_code != 200:
        return None
    datos = r.json()
    datos = datos.get('estudiantes', datos) if isinstance(datos, dict) else datos
    return {e['id'] for e in datos}


def cursos_horarios(u, nivel=None):
    r = client.get('/api/horarios', headers=hdr(u, nivel))
    return {h['curso_id'] for h in r.json()} if r.status_code == 200 else None


TODOS_EST = EST_NIVEL['primaria'] | EST_NIVEL['secundaria']
TODOS_CUR = CURSOS_PRI | CURSOS_SEC

# Recreos por nivel en la tanda Matutina, y uno general (legacy) en Vespertina.
REC = {}
for clave, tanda, nivel, hora in (('pri', 'Matutina', 'primaria', '10:00'),
                                  ('sec', 'Matutina', 'secundaria', '10:30'),
                                  ('legacy_v', 'Vespertina', None, '15:00')):
    r_ = M.Recreo(colegio_id=COL.id, tanda_id=TANDAS[tanda].id, nombre='Recreo ' + clave,
                  hora_inicio=hora, hora_fin=hora[:3] + '20', nivel=nivel, activo=True)
    db.add(r_)
    db.flush()
    REC[clave] = r_.id
db.commit()


def ids_recreos(u, nivel=None):
    r = client.get('/api/recreos', headers=hdr(u, nivel))
    return {x['id'] for x in r.json()} if r.status_code == 200 else None


def cursos_horarios_prof(u, nivel=None):
    r = client.get('/api/horarios/profesor/%d' % PROF.id, headers=hdr(u, nivel))
    return {h['curso_id'] for h in r.json()} if r.status_code == 200 else None


print("\n=== HORARIOS · SECRETARÍA CON SU SELECTOR LOCAL ===")
s_ = U['secretaria']
check('HS-01 [Primaria] cursos: solo Primaria', ids_cursos(s_, 'primaria') == CURSOS_PRI, '')
check('HS-02 [Primaria] horarios del profesor: solo de cursos de Primaria',
      cursos_horarios_prof(s_, 'primaria') == CURSOS_PRI, '')
check('HS-03 [Primaria] recreos: los de Primaria (+ el general de la tanda que no tiene propio)',
      ids_recreos(s_, 'primaria') == {REC['pri'], REC['legacy_v']},
      str(ids_recreos(s_, 'primaria')))
check('HS-04 [Secundaria] cursos: solo Secundaria', ids_cursos(s_, 'secundaria') == CURSOS_SEC, '')
check('HS-05 [Secundaria] horarios del profesor: solo de cursos de Secundaria',
      cursos_horarios_prof(s_, 'secundaria') == CURSOS_SEC, '')
check('HS-06 [Secundaria] recreos: los de Secundaria (+ el general sin propio)',
      ids_recreos(s_, 'secundaria') == {REC['sec'], REC['legacy_v']},
      str(ids_recreos(s_, 'secundaria')))
check('HS-07 el cambio de nivel en Horarios no toca el dashboard: sigue con ambos niveles',
      {c['curso_id'] for c in client.get('/api/dashboard/secretaria',
                                          headers=hdr(s_, 'primaria')).json()['estudiantes_por_curso']}
      == TODOS_CUR, '')

print("\n=== HORARIOS · SECRETARÍA CREA Y EDITA, CON LAS VALIDACIONES DE SIEMPRE ===")
_bloque = {'profesor_id': PROF.id, 'curso_id': _c_prof, 'asignatura_id': ASIG.id,
           'dia': 'Martes', 'hora_inicio': '08:00', 'hora_fin': '08:45', 'tipo_bloque': 'clase'}
r = client.post('/api/horarios', json=_bloque, headers=hdr(s_, 'primaria'))
check('HS-08 Secretaría crea un bloque válido', r.status_code in (200, 201), '%d %s' % (r.status_code, r.text[:80]))
_hid = (r.json() or {}).get('id') if r.status_code in (200, 201) else None
if _hid is None:
    _h = db.query(M.Horario).filter_by(curso_id=_c_prof, dia='Martes', hora_inicio='08:00').first()
    _hid = _h.id if _h else None
r = client.put('/api/horarios/%s' % _hid, json={'aula': 'A-12'}, headers=hdr(s_, 'primaria'))
check('HS-09 Secretaría edita su bloque', r.status_code == 200, '%d %s' % (r.status_code, r.text[:80]))
r = client.post('/api/horarios', json=_bloque, headers=hdr(s_, 'primaria'))
check('HS-10 un cruce de horario sigue bloqueado', r.status_code in (400, 409),
      '%d %s' % (r.status_code, r.text[:80]))
_sin_asig = dict(_bloque, curso_id=next(iter(CURSOS_SEC)), dia='Miércoles')
r = client.post('/api/horarios', json=_sin_asig, headers=hdr(s_, 'secundaria'))
check('HS-11 sin asignación válida del profesor, no se crea (ni se crea la asignación)',
      r.status_code in (400, 409) and db.query(M.AsignacionProfesor).filter_by(
          profesor_id=PROF.id, curso_id=_sin_asig['curso_id']).count() == 0,
      '%d %s' % (r.status_code, r.text[:80]))
r = client.post('/api/horarios', json=dict(_bloque, curso_id=C_AJENO.id, dia='Jueves'),
                headers=hdr(s_, 'primaria'))
check('HS-12 curso de otro colegio: bloqueado', r.status_code in (403, 404), str(r.status_code))
r = client.post('/api/recreos', json={'tanda_id': TANDAS['Matutina'].id, 'nombre': 'X',
                                      'hora_inicio': '11:00', 'hora_fin': '11:20'},
                headers=hdr(s_, 'primaria'))
check('HS-13 Secretaría sigue sin administrar recreos', r.status_code == 403, str(r.status_code))

print("\n=== LOS DEMÁS ROLES, EXACTAMENTE COMO EN MAIN ===")
check('RL-01 Secretaría sin cabecera (otras pantallas): ve ambos niveles',
      ids_cursos(s_) == TODOS_CUR and ids_estudiantes(s_) == TODOS_EST, '')
for rol in ('direccion', 'coordinador', 'psicologia'):
    u = U[rol]
    check('RL-02 %s sin cabecera: ve todo' % rol, ids_cursos(u) == TODOS_CUR, '')
    check('RL-03 %s + X-Nivel primaria: solo Primaria' % rol,
          ids_cursos(u, 'primaria') == CURSOS_PRI, '')
    check('RL-04 %s + X-Nivel secundaria: solo Secundaria' % rol,
          ids_cursos(u, 'secundaria') == CURSOS_SEC, '')
check('RL-05 coordinador fijo en Primaria + X-Nivel secundaria: sigue en Primaria',
      ids_cursos(U['coord_pri_fijo'], 'secundaria') == CURSOS_PRI, '')
check('RL-06 profesor: solo SUS cursos, con o sin cabecera',
      ids_cursos(PROF) == {_c_prof} and ids_cursos(PROF, 'secundaria') == {_c_prof}, '')
check('RL-07 superadmin: la cabecera no lo filtra',
      ids_cursos(U['superadmin'], 'primaria') == ids_cursos(U['superadmin']) == TODOS_CUR, '')
_src_ne = open(os.path.join(BK, 'app.py'), encoding='utf-8').read()
check('RL-08 nivel_efectivo sin cambios (no hay regla global nueva)',
      'ROLES_CON_SELECTOR_DIVISION' not in _src_ne, '')

print("\n=== FRONTEND · EL SELECTOR ES LOCAL DE HORARIOS ===")
_FE = os.path.join(os.path.dirname(BK), 'frontend', 'src')
_hor = open(os.path.join(_FE, 'pages', 'horarios', 'HorariosPage.tsx'), encoding='utf-8').read()
_api = open(os.path.join(_FE, 'services', 'api.ts'), encoding='utf-8').read()
check('FE-01 Horarios no escribe el nivel global (educaone_nivel_vista)',
      "setItem('educaone_nivel_vista'" not in _hor, '')
check('FE-02 para Secretaría el nivel sale de su selector local, no del valor guardado',
      'esSecretariaSinNivel' in _hor and '? nivelLocal' in _hor, '')
check('FE-03 sus lecturas de nivel van marcadas para que el interceptor no las pise',
      "api.get('/cursos', cfgNivel)" in _hor and "api.get('/recreos', cfgNivel)" in _hor
      and '/horarios/profesor/${profesorId}`, cfgNivel' in _hor
      and '/horarios/curso/${cursoId}`, cfgNivel' in _hor, '')
check('FE-04 el interceptor solo respeta X-Nivel explícito con la marca `nivelLocal`',
      '(config as any).nivelLocal' in _api, '')
check('FE-05 sin nivel elegido, Horarios de Secretaría no carga nada y pide elegir',
      'esSecretariaSinNivel && !nivelLocal' in _hor
      and 'Elige Primaria o Secundaria para administrar el horario.' in _hor, '')
_rt = open(os.path.join(_FE, 'Router.tsx'), encoding='utf-8').read()
_linea_ruta = _rt[_rt.index('path="/horarios"'):][:300]
check('FE-06 la ruta /horarios admite a Secretaría (el menú ya se la ofrecía)',
      "'secretaria'" in _linea_ruta, '')

print("\n=== FRONTEND · NADIE HEREDA LA VISTA DE DIVISIÓN DE OTRA SESIÓN ===")
_auth = open(os.path.join(_FE, 'context', 'AuthContext.tsx'), encoding='utf-8').read()
_logout = _auth[_auth.index('const logout = async'):]
_login = _auth[_auth.index('const login = async'):_auth.index('const logout = async')]
_check = _auth[_auth.index('const checkAuth = async'):_auth.index('const login = async')]
check('FE-07 al cerrar sesión se borra educaone_nivel_vista (todos los roles)',
      'removeItem(CLAVE_NIVEL_VISTA)' in _logout
      and "CLAVE_NIVEL_VISTA = 'educaone_nivel_vista'" in _auth, '')
check('FE-08 al iniciar sesión como Secretaría se borra ANTES de setUser',
      _login.index('limpiarNivelVistaSiSecretaria(') < _login.index('setUser(userData)'), '')
check('FE-09 y también al restaurar una sesión de Secretaría (recarga)',
      _check.index('limpiarNivelVistaSiSecretaria(') < _check.index('setUser(res.data)'), '')
check('FE-10 la limpieza al iniciar sesión es SOLO para Secretaría',
      "if (role === 'secretaria')" in _auth, '')
check('FE-11 Horarios muestra el mensaje pedido sin nivel elegido',
      'Elige Primaria o Secundaria para administrar el horario.' in _hor, '')

print("\n=== A · DASHBOARD: RÓTULO COMPLETO, TODOS LOS CURSOS ===")
for etiqueta, nivel in (('sin cabecera', None), ('X-Nivel secundaria', 'secundaria'),
                        ('X-Nivel primaria', 'primaria')):
    r = client.get('/api/dashboard/secretaria', headers=hdr(U['secretaria'], nivel))
    check('DS-01 [%s] responde 200' % etiqueta, r.status_code == 200, str(r.status_code))
    if r.status_code != 200:
        continue
    d = r.json()
    por_id = {c['curso_id']: c for c in d['estudiantes_por_curso']}
    check('DS-02 [%s] están TODOS los cursos activos, ni uno oculto' % etiqueta,
          set(por_id) == set(ESPERADO), '%d de %d' % (len(por_id), len(ESPERADO)))
    for cid, (rotulo, n_est) in ESPERADO.items():
        c = por_id.get(cid) or {}
        check('DS-03 [%s] %-30s -> %s' % (etiqueta, rotulo, n_est),
              c.get('curso') == rotulo and c.get('estudiantes') == n_est,
              repr(c.get('curso')))
    check('DS-04 [%s] cada fila trae curso_id/grado/seccion/tanda/nivel/curso/estudiantes' % etiqueta,
          all(set(c) >= {'curso_id', 'grado', 'seccion', 'tanda', 'nivel', 'curso', 'estudiantes'}
              and c['nivel'] in ('primaria', 'secundaria') for c in d['estudiantes_por_curso']), '')
    check('DS-05 [%s] ningún rótulo es solo la sección' % etiqueta,
          all(c['curso'] not in ('A', 'B', '') for c in d['estudiantes_por_curso']), '')
    check('DS-06 [%s] curso inactivo fuera; otro colegio fuera' % etiqueta,
          all('B ·' not in c['curso'] for c in d['estudiantes_por_curso'])
          and C_AJENO.id not in por_id, '')
    check('DS-07 [%s] cursos con 0 estudiantes visibles y contados' % etiqueta,
          d['cursos_vacios'] == sum(1 for _, n in ESPERADO.values() if n == 0)
          and d['total_cursos'] == len(ESPERADO), str(d['cursos_vacios']))

print("\n=== A · SIN N+1: EL NÚMERO DE CONSULTAS NO CRECE CON LOS CURSOS ===")


def montar_colegio_n(n_cursos, codigo):
    c, ano = colegio(codigo)
    t = M.Tanda(colegio_id=c.id, nombre='Matutina', hora_inicio='07:30', hora_fin='12:30')
    g = M.Grado(colegio_id=c.id, nombre='1ro Primaria', nivel='primaria', orden=1, activo=True)
    db.add_all([t, g])
    db.flush()
    for i in range(n_cursos):
        cu = M.Curso(colegio_id=c.id, nombre='S%d' % i, grado_id=g.id, tanda_id=t.id,
                     ano_escolar_id=ano.id, activo=True)
        db.add(cu)
        db.flush()
        db.add(M.Estudiante(colegio_id=c.id, matricula='%s-%d' % (codigo, i), nombre='E',
                            apellido='x', curso_id=cu.id, activo=True, no_lista=1))
    u = usuario(c, 'sec_' + codigo, 'secretaria')
    db.commit()
    return u


CONSULTAS = {}
for n in (6, 24):
    u = montar_colegio_n(n, 'NQ%d' % n)
    q = []

    def _contar(conn, cur, st, p, ctx, many):
        q.append(st)

    event.listen(engine, 'before_cursor_execute', _contar)
    d = asyncio.run(APP.get_dashboard_secretaria(db=db, current_user=u))
    event.remove(engine, 'before_cursor_execute', _contar)
    CONSULTAS[n] = len(q)
    check('DS-08 %d cursos: el dashboard los trae todos, con su conteo' % n,
          len(d['estudiantes_por_curso']) == n
          and all(c['estudiantes'] == 1 for c in d['estudiantes_por_curso']), '')
print('  INFO   consultas SQL del dashboard: 6 cursos -> %d, 24 cursos -> %d'
      % (CONSULTAS[6], CONSULTAS[24]))
check('DS-09 el número de consultas es CONSTANTE (6 cursos = 24 cursos)',
      CONSULTAS[6] == CONSULTAS[24], '%d vs %d' % (CONSULTAS[6], CONSULTAS[24]))

print("\n=== LO QUE NO CAMBIA ===")
r = client.get('/api/estadisticas/cuadro-honor', headers=hdr(U['secretaria']))
check('DS-10 Cuadro de Honor sigue disponible para Secretaría', r.status_code == 200,
      str(r.status_code))
r = client.post('/api/recuperaciones-primaria', json={}, headers=hdr(U['secretaria']))
check('DS-11 Secretaría NO puede registrar recuperaciones de Primaria', r.status_code == 403,
      str(r.status_code))
_menu = open(os.path.join(os.path.dirname(BK), 'frontend', 'src', 'components', 'layout',
                          'MainLayout.tsx'), encoding='utf-8').read()
_linea_rec = [l for l in _menu.splitlines() if "'/recuperaciones-primaria'" in l][0]
_linea_honor = [l for l in _menu.splitlines() if "'/cuadro-honor'" in l][0]
check('DS-12 menú: Cuadro de Honor con secretaria, Recuperaciones sin ella',
      "'secretaria'" in _linea_honor and "'secretaria'" not in _linea_rec, '')
_dash = open(os.path.join(os.path.dirname(BK), 'frontend', 'src', 'pages', 'dashboard',
                          'DashboardPage.tsx'), encoding='utf-8').read()
check('DS-13 el dashboard ya no cruza con /cursos',
      "api.get('/cursos')" not in _dash and 'cursosSecretaria' not in _dash, '')

print()
print("=" * 98)
print("RESULTADO: %d PASARON / %d FALLARON" % (len(PASARON), len(FALLARON)))
print("=" * 98)
for f in FALLARON:
    print("  FALLA:", f)

db.close()
sys.exit(1 if FALLARON else 0)
