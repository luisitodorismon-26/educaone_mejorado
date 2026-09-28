# -*- coding: utf-8 -*-
"""RELEASE — el Cierre canónico habilitado, el legacy cerrado para siempre.

QUÉ CAMBIA EN ESTE RELEASE
==========================
C1 puso UNA bandera delante de cuatro POST. Fue lo correcto mientras el flujo
se reconstruía: no había nada que habilitar. Ahora sí lo hay, y los cuatro
dejaron de ser lo mismo.

  CANÓNICOS — `/api/ano-escolar/{id}/cerrar` y `/api/cierre-ano/promover`.
  El flujo que CORE-1 y CORE-2 construyeron. Se habilitan.

  LEGACY — `/api/promocion/ejecutar` y `/api/ano-escolar/promover`. Mueven
  estudiantes sin mirar su situación académica ni el año de destino. Quedan
  fuera de servicio de forma permanente.

Si compartieran bandera, habilitar el Cierre resucitaría los dos writers que
todo este trabajo existía para retirar.

QUÉ SE PRUEBA AQUÍ
==================
Por HTTP real, porque `RolesRequired` es una dependencia de FastAPI y llamar
a la función por dentro se la salta entera:

  · que los dos canónicos ya no chocan contra el candado y completan;
  · que los dos legacy devuelven 409 SIEMPRE, incluso poniendo la constante
    en False, y sin escribir una sola fila;
  · el flujo entero de un año: cerrar, crear el siguiente, clonar cursos,
    promover, y que cada situación académica acabe donde le toca;
  · que reintentar no mueve a nadie dos veces;
  · y que la tabla nueva del release se crea de forma puramente aditiva.

Base temporal aislada. Nunca producción.
"""
import datetime as dt
import os
import sys
import tempfile

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)
sys.path.insert(0, os.path.join(_BACKEND, "tools"))

_TMPDIR = tempfile.mkdtemp(prefix="eo_release_")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(
    _TMPDIR, "release.db").replace("\\", "/")
os.environ.setdefault("ENVIRONMENT", "development")
assert "sge.db" not in os.environ["DATABASE_URL"]

from database import engine, SessionLocal  # noqa: E402
import models as M  # noqa: E402
import promocion_academica as PA  # noqa: E402
import resultado_academico as RA  # noqa: E402
import resultado_academico_consumidores as AD  # noqa: E402

M.Base.metadata.create_all(bind=engine)

from fastapi.testclient import TestClient  # noqa: E402
import app as APP  # noqa: E402
from app import app  # noqa: E402

client = TestClient(app)

PASARON, FALLARON = [], []


def check(nombre, cond, detalle=''):
    if cond:
        PASARON.append(nombre)
        print("  PASA   %-66s %s" % (nombre, detalle))
    else:
        FALLARON.append(nombre)
        print("  FALLA  %-66s %s" % (nombre, detalle))


def auth(tok):
    return {'Authorization': 'Bearer ' + tok}


def login(usuario, clave):
    d = SessionLocal()
    try:
        u = d.query(M.Usuario).filter_by(username=usuario).first()
        if u is not None and u.must_change_password:
            u.must_change_password = False
            d.commit()
    finally:
        d.close()
    r = client.post('/api/auth/login',
                    json={'username': usuario, 'password': clave})
    assert r.status_code == 200, '%s: %s' % (usuario, r.text)
    return r.json()['token']


def foto():
    """El estado que ningún rechazo puede cambiar."""
    d = SessionLocal()
    try:
        return {
            'estudiantes': sorted(
                (e.id, e.curso_id, e.condicion, e.activo)
                for e in d.query(M.Estudiante).all()),
            'anos': sorted((a.id, a.activo, a.cerrado)
                           for a in d.query(M.AnoEscolar).all()),
            'historial': d.query(M.HistorialAcademico).count(),
        }
    finally:
        d.close()


# ═══════════════════════════════════════════════════════════════════════
print("\n=== 1 · LOS DOS CANDADOS ===")

check('REL-01 el Cierre canónico está HABILITADO',
      APP.CIERRE_ANO_BLOQUEADO is False, str(APP.CIERRE_ANO_BLOQUEADO))
check('REL-02 la promoción legacy sigue declarada como bloqueada',
      APP.PROMOCION_LEGACY_BLOQUEADA is True,
      str(APP.PROMOCION_LEGACY_BLOQUEADA))
check('REL-03 y son dos constantes distintas, no la misma',
      APP.CIERRE_ANO_BLOQUEADO is not APP.PROMOCION_LEGACY_BLOQUEADA, '')


# ═══════════════════════════════════════════════════════════════════════
print("\n=== SETUP DEL AÑO ===")

with client:
    SA = login('superadmin', 'superadmin123')
    r = client.post('/api/superadmin/colegios', json={
        'nombre': 'Centro Release', 'codigo': 'rel', 'plan': 'enterprise',
        'admin_username': 'dir_rel', 'admin_password': 'admin123rel',
        'plan_secundaria': True, 'plan_primaria': True,
    }, headers=auth(SA))
    assert r.status_code in (200, 201), r.text
    DIR = login('dir_rel', 'admin123rel')

    for rol, usuario in (('profesor', 'prof_rel'),):
        r = client.post('/api/usuarios', json={
            'username': usuario, 'password': 'prof123456', 'nombre': 'P',
            'apellido': 'R', 'email': usuario + '@r.com', 'role': rol,
        }, headers=auth(DIR))
        assert r.status_code in (200, 201), r.text
    PROF = login('prof_rel', 'prof123456')

    # ── El año A, con gente en situaciones distintas ────────────────────
    d = SessionLocal()
    col = d.query(M.Colegio).filter_by(codigo='rel').first()
    for viejo in d.query(M.AnoEscolar).filter_by(colegio_id=col.id).all():
        viejo.activo = False
    _ini = dt.date(2025, 8, 18)
    A = M.AnoEscolar(colegio_id=col.id, nombre='2025-2026', activo=True,
                     cerrado=False, fecha_inicio=_ini,
                     fecha_fin=dt.date(2026, 6, 12),
                     p1_inicio=_ini, p1_fin=_ini + dt.timedelta(days=74),
                     p2_inicio=_ini + dt.timedelta(days=75),
                     p2_fin=_ini + dt.timedelta(days=164),
                     p3_inicio=_ini + dt.timedelta(days=165),
                     p3_fin=_ini + dt.timedelta(days=242),
                     p4_inicio=_ini + dt.timedelta(days=243),
                     p4_fin=dt.date(2026, 6, 12))
    # Sin dias habiles declarados, A3 no puede dar un porcentaje de ausencia
    # y A2 se niega a certificar. Es su politica, no un detalle del test.
    A.set_dias_trabajados({'ago': 10, 'sep': 21, 'oct': 22, 'nov': 20,
                           'dic': 14, 'ene': 20, 'feb': 19, 'mar': 22,
                           'abr': 18, 'may': 21, 'jun': 8})
    d.add(A)
    d.flush()

    # Los grados YA existen: `init_db` los siembra al crear el colegio.
    # Crear otros con el mismo nivel y numero dejaria DOS candidatos para el
    # mismo destino, y el motor —con razon— se negaria a elegir.
    import re as _re

    def _numero(nombre):
        m = _re.search(r'(\d+)', nombre or '')
        return int(m.group(1)) if m else None

    G = {}
    for g in d.query(M.Grado).filter_by(colegio_id=col.id, activo=True).all():
        nivel = (g.nivel or '').strip().lower()
        n = _numero(g.nombre)
        if nivel in ('primaria', 'secundaria') and n:
            G.setdefault((nivel, n), g)
    assert ('secundaria', 3) in G and ('primaria', 6) in G, sorted(G)

    def curso(g):
        c = M.Curso(colegio_id=col.id, nombre='A', grado_id=g.id,
                    ano_escolar_id=A.id, activo=True)
        d.add(c)
        d.flush()
        return c

    C_SEC3 = curso(G[('secundaria', 3)])
    C_SEC6 = curso(G[('secundaria', 6)])
    C_PRI6 = curso(G[('primaria', 6)])

    AREAS_SEC3 = list(AD.curriculo_oficial_esperado(RA.NIVEL_SECUNDARIA, 3)[0])
    AREAS_SEC6 = list(AD.curriculo_oficial_esperado(RA.NIVEL_SECUNDARIA, 6)[0])
    AREAS_PRI6 = list(AD.curriculo_oficial_esperado(RA.NIVEL_PRIMARIA, 6)[0])

    ASIG = {}
    for cod in set(AREAS_SEC3) | set(AREAS_SEC6) | set(AREAS_PRI6):
        # `area_curricular_codigo` es lo que el motor mira para saber que
        # area oficial cubre esta asignatura. Sin el, el curriculo sale
        # INCOMPLETO y A2 no certifica a nadie.
        a = M.Asignatura(colegio_id=col.id, nombre=cod, codigo=cod[:10],
                         area='X', area_curricular_codigo=cod, activo=True)
        d.add(a)
        d.flush()
        ASIG[cod] = a

    _prof = d.query(M.Usuario).filter_by(username='prof_rel').first()

    def asignar(c, codigos):
        # La asignatura llega al curso por la ASIGNACION del profesor: es lo
        # que el motor lee para saber que areas se imparten ahi.
        for cod in codigos:
            d.add(M.AsignacionProfesor(
                colegio_id=col.id, profesor_id=_prof.id, curso_id=c.id,
                asignatura_id=ASIG[cod].id, ano_escolar_id=A.id, activo=True))
        d.flush()

    _n = [0]

    def alumno(c, etiqueta):
        _n[0] += 1
        e = M.Estudiante(colegio_id=col.id, matricula='R-%03d' % _n[0],
                         nombre=etiqueta, apellido='Rel', curso_id=c.id,
                         no_lista=_n[0], activo=True, condicion='activo')
        d.add(e)
        d.flush()
        return e

    def notas_sec(e, codigos, nota):
        for cod in codigos:
            for n in range(1, 5):
                d.add(M.CalificacionSecundaria(
                    colegio_id=col.id, estudiante_id=e.id,
                    asignatura_id=ASIG[cod].id, ano_escolar_id=A.id,
                    competencia_numero=n, p1=nota, p2=nota, p3=nota, p4=nota))
        d.flush()

    def notas_pri(e, codigos, nota):
        for cod in codigos:
            for n in (1, 2, 3):
                d.add(M.CalificacionPrimaria(
                    colegio_id=col.id, estudiante_id=e.id,
                    asignatura_id=ASIG[cod].id, ano_escolar_id=A.id,
                    competencia_numero=n, p1=nota, p2=nota, p3=nota, p4=nota,
                    final_competencia=nota))
        d.flush()

    asignar(C_SEC3, AREAS_SEC3)
    asignar(C_SEC6, AREAS_SEC6)
    asignar(C_PRI6, AREAS_PRI6)

    def caidas(e, n):
        """`n` areas caidas DESPUES de agotar la Extraordinaria.

        Suspender un area no basta para un veredicto: queda pendiente de
        recuperacion y A2 dice EN_PROCESO, que es lo correcto. Para que haya
        resultado hay que agotar el camino. Con 1-2 areas caidas A2 da
        APLAZADO; con 3 o mas, REPROBADO.
        """
        for cod in AREAS_SEC3[:n]:
            for k in range(1, 5):
                d.add(M.CalificacionSecundaria(
                    colegio_id=col.id, estudiante_id=e.id,
                    asignatura_id=ASIG[cod].id, ano_escolar_id=A.id,
                    competencia_numero=k, p1=50, p2=50, p3=50, p4=50))
            d.add(M.EvaluacionExtraSecundaria(
                colegio_id=col.id, estudiante_id=e.id,
                asignatura_id=ASIG[cod].id, ano_escolar_id=A.id,
                cf_original=50.0, cec=40.0, completiva_final=55.0,
                ceex=40.0, extraordinaria_final=60.0))
        notas_sec(e, AREAS_SEC3[n:], 95)
        d.flush()

    E = {}
    E['prom'] = alumno(C_SEC3, 'PROM')
    notas_sec(E['prom'], AREAS_SEC3, 95)
    E['repr'] = alumno(C_SEC3, 'REPR')
    caidas(E['repr'], 3)                          # 3 areas caidas: REPROBADO
    E['mixto'] = alumno(C_SEC3, 'MIXTO')
    caidas(E['mixto'], 1)                         # 1 area caida: APLAZADO
    E['proceso'] = alumno(C_SEC3, 'PROCESO')      # sin notas: EN_PROCESO
    E['sexto_sec'] = alumno(C_SEC6, 'SEXTOSEC')
    notas_sec(E['sexto_sec'], AREAS_SEC6, 95)
    E['sexto_pri'] = alumno(C_PRI6, 'SEXTOPRI')
    notas_pri(E['sexto_pri'], AREAS_PRI6, 95)

    d.commit()
    IDS = {k: v.id for k, v in E.items()}
    ID_GRADO = {k: g.id for k, g in G.items()}
    ID_COL = col.id
    ID_A, ID_C3 = A.id, C_SEC3.id
    d.close()
    print("  año A=%d, 6 estudiantes en 3 cursos" % ID_A)

    # ═══════════════════════════════════════════════════════════════════
    print("\n=== 2 · LOS DOS LEGACY, BLOQUEADOS PARA SIEMPRE ===")

    LEGACY = [('REL-10 /api/promocion/ejecutar', '/api/promocion/ejecutar',
               {'estudiantes': list(IDS.values())}),
              ('REL-11 /api/ano-escolar/promover', '/api/ano-escolar/promover',
               {})]

    antes = foto()
    for et, ruta, cuerpo in LEGACY:
        r = client.post(ruta, json=cuerpo, headers=auth(DIR))
        j = r.json() if r.headers.get('content-type', '').startswith(
            'application/json') else {}
        check(et + ' -> 409 PROMOCION_LEGACY_BLOQUEADA',
              r.status_code == 409 and j.get('error') == 'PROMOCION_LEGACY_BLOQUEADA',
              '-> %d %s' % (r.status_code, j.get('error')))
    check('REL-12 y no escribieron una sola fila', foto() == antes, '')

    for et, ruta, cuerpo in LEGACY:
        r = client.post(ruta, json=cuerpo, headers=auth(PROF))
        check(et.replace('REL-1', 'REL-13') + ': profesor -> 403',
              r.status_code == 403, '-> %d' % r.status_code)
        r = client.post(ruta, json=cuerpo)
        check(et.replace('REL-1', 'REL-14') + ': sin token -> 401',
              r.status_code == 401, '-> %d' % r.status_code)

    # ── La mutación: la constante NO es el interruptor ──────────────────
    _antes = APP.PROMOCION_LEGACY_BLOQUEADA
    APP.PROMOCION_LEGACY_BLOQUEADA = False
    try:
        for et, ruta, cuerpo in LEGACY:
            r = client.post(ruta, json=cuerpo, headers=auth(DIR))
            j = r.json() if r.status_code == 409 else {}
            check(et.replace('REL-1', 'REL-15')
                  + ': con la constante en False SIGUE bloqueado',
                  r.status_code == 409
                  and j.get('error') == 'PROMOCION_LEGACY_BLOQUEADA',
                  '-> %d' % r.status_code)
        check('REL-16 y con la constante apagada tampoco escriben',
              foto() == antes, '')
    finally:
        APP.PROMOCION_LEGACY_BLOQUEADA = _antes
    check('REL-17 la constante vuelve a su valor',
          APP.PROMOCION_LEGACY_BLOQUEADA is True, '')

    # ═══════════════════════════════════════════════════════════════════
    print("\n=== 3 · RBAC DE LOS CANÓNICOS ===")

    for et, ruta, cuerpo in (
            ('REL-20 cerrar año', '/api/ano-escolar/%d/cerrar' % ID_A, {}),
            ('REL-21 promover', '/api/cierre-ano/promover', {})):
        r = client.post(ruta, json=cuerpo, headers=auth(PROF))
        check(et + ': profesor -> 403', r.status_code == 403,
              '-> %d' % r.status_code)
        r = client.post(ruta, json=cuerpo)
        check(et + ': sin token -> 401', r.status_code == 401,
              '-> %d' % r.status_code)
    check('REL-22 y ninguno de esos rechazos tocó la base', foto() == antes, '')

    # ═══════════════════════════════════════════════════════════════════
    print("\n=== 4 · EL FLUJO COMPLETO, POR HTTP ===")

    # 4.1 · EN_PROCESO bloquea el cierre. Esta es la garantía de fondo: el
    # año no se cierra sobre una cuenta que todavía no cuadra.
    r = client.post('/api/ano-escolar/%d/cerrar' % ID_A, json={},
                    headers=auth(DIR))
    j = r.json()
    check('REL-30 el cierre NO pasa el candado y llega al motor canónico',
          j.get('error') != 'CIERRE_ANO_TEMPORALMENTE_BLOQUEADO',
          str(j.get('error')))
    check('REL-31 y un EN_PROCESO lo bloquea, con nombres',
          r.status_code in (400, 409)
          and j.get('error') == 'CIERRE_ANO_TIENE_EN_PROCESO',
          '-> %d %s' % (r.status_code, j.get('error')))
    check('REL-32 el año sigue abierto tras el rechazo', foto() == antes, '')

    # 4.2 · Se resuelve al que faltaba y el cierre completa.
    d = SessionLocal()
    try:
        est = d.get(M.Estudiante, IDS['proceso'])
        for cod in AREAS_SEC3:
            asig = d.query(M.Asignatura).filter_by(
                colegio_id=est.colegio_id, nombre=cod).first()
            for n in range(1, 5):
                d.add(M.CalificacionSecundaria(
                    colegio_id=est.colegio_id, estudiante_id=est.id,
                    asignatura_id=asig.id, ano_escolar_id=ID_A,
                    competencia_numero=n, p1=88, p2=88, p3=88, p4=88))
        d.commit()
    finally:
        d.close()

    # Qué dice A2 de cada uno, ANTES de mover a nadie. El writer tiene que
    # respetar esto; no se codifica aquí ningún veredicto a mano.
    r_prev = client.get('/api/cierre-ano/promocion',
                        params={'ano_id': ID_A}, headers=auth(DIR))
    check('REL-33 la previsualización responde', r_prev.status_code == 200,
          '-> %d' % r_prev.status_code)
    SITUACION = {}
    if r_prev.status_code == 200:
        for fila in (r_prev.json().get('estudiantes') or []):
            SITUACION[fila['id']] = fila.get('condicion_canonica') or fila.get(
                'condicion')
        print("     A2 dice: %s" % {
            k: SITUACION.get(v) for k, v in IDS.items() if v in SITUACION})

    r = client.post('/api/ano-escolar/%d/cerrar' % ID_A, json={},
                    headers=auth(DIR))
    check('REL-34 con la cuenta cuadrada, el año CIERRA',
          r.status_code == 200, '-> %d %s' % (r.status_code, r.text[:90]))

    d = SessionLocal()
    try:
        _a = d.get(M.AnoEscolar, ID_A)
        check('REL-35 queda cerrado=True y activo=False',
              _a.cerrado is True and _a.activo is False,
              'cerrado=%s activo=%s' % (_a.cerrado, _a.activo))
        check('REL-36 y el cierre NO creó historial prematuro',
              d.query(M.HistorialAcademico).count() == 0,
              str(d.query(M.HistorialAcademico).count()))
    finally:
        d.close()

    # 4.3 · Un año cerrado no se puede activar directamente.
    r = client.post('/api/ano-escolar/%d/activar' % ID_A, json={},
                    headers=auth(DIR))
    check('REL-37 un año cerrado NO se activa directamente',
          r.status_code == 409
          and r.json().get('error') == 'ANO_ESCOLAR_CERRADO_NO_ACTIVABLE',
          '-> %d %s' % (r.status_code, r.json().get('error')))

    # 4.4 · Crear el año destino y clonar cursos.
    r = client.post('/api/ano-escolar', json={
        'nombre': '2026-2027', 'fecha_inicio': '2026-08-17',
        'fecha_fin': '2027-06-11',
    }, headers=auth(DIR))
    check('REL-38 se crea el año destino', r.status_code in (200, 201),
          '-> %d %s' % (r.status_code, r.text[:80]))
    ID_B = r.json().get('id')

    r = client.post('/api/ano-escolar/%d/clonar-cursos' % ID_B, json={},
                    headers=auth(DIR))
    check('REL-39 se clonan los cursos al año nuevo',
          r.status_code in (200, 201), '-> %d' % r.status_code)

    # Clonar replica los cursos que EXISTIAN en A. Los grados a los que va a
    # llegar la cohorte —4.º de Secundaria para los de 3.º, 1.º de Secundaria
    # para los de 6.º de Primaria— no existian, asi que hay que crearlos.
    # Esto es trabajo de Direccion, y el writer NO lo hace por su cuenta:
    # sin estructura de destino se NIEGA a mover a nadie.
    _antes_prom = foto()
    r_falta = client.post('/api/cierre-ano/promover',
                          json={'ano_origen_id': ID_A, 'ano_destino_id': ID_B},
                          headers=auth(DIR))
    check('REL-39b sin curso de destino, la promocion se NIEGA',
          r_falta.status_code == 409
          and r_falta.json().get('error') == 'CIERRE_ESTRUCTURA_DESTINO_INCOMPLETA',
          '-> %d %s' % (r_falta.status_code, r_falta.json().get('error')))
    check('REL-39c y esa negativa no movio a nadie', foto() == _antes_prom, '')

    d = SessionLocal()
    try:
        for _clave in (('secundaria', 4), ('secundaria', 1)):
            _gid = ID_GRADO[_clave]
            if not d.query(M.Curso).filter_by(
                    grado_id=_gid, ano_escolar_id=ID_B).first():
                d.add(M.Curso(colegio_id=ID_COL, nombre='A', grado_id=_gid,
                              ano_escolar_id=ID_B, activo=True))
        d.commit()
    finally:
        d.close()

    # 4.5 · La promoción canónica.
    r = client.post('/api/cierre-ano/promover',
                    json={'ano_origen_id': ID_A, 'ano_destino_id': ID_B},
                    headers=auth(DIR))
    check('REL-40 la promoción canónica se ejecuta',
          r.status_code == 200, '-> %d %s' % (r.status_code, r.text[:140]))
    RESULTADO = r.json() if r.status_code == 200 else {}

    # 4.6 · Cada situación, donde le toca.
    d = SessionLocal()
    try:
        def ctx(clave):
            e = d.get(M.Estudiante, IDS[clave])
            c = d.get(M.Curso, e.curso_id) if e.curso_id else None
            g = d.get(M.Grado, c.grado_id) if c else None
            return e, c, g

        e_p, c_p, g_p = ctx('prom')
        check('REL-41 el PROMOVIDO está en el año destino...',
              c_p is not None and c_p.ano_escolar_id == ID_B,
              'ano=%s' % (c_p.ano_escolar_id if c_p else None))
        check('REL-42 ...y en el grado SIGUIENTE',
              g_p is not None and '4' in g_p.nombre, g_p.nombre if g_p else '')

        e_r, c_r, g_r = ctx('repr')
        check('REL-43 el REPROBADO también pasa al año destino...',
              c_r is not None and c_r.ano_escolar_id == ID_B,
              'ano=%s' % (c_r.ano_escolar_id if c_r else None))
        check('REL-44 ...pero al MISMO grado',
              g_r is not None and '3' in g_r.nombre, g_r.nombre if g_r else '')

        e_sp, c_sp, g_sp = ctx('sexto_pri')
        check('REL-45 6.º de Primaria pasa a 1.º de Secundaria',
              g_sp is not None and g_sp.nivel == 'secundaria'
              and '1' in g_sp.nombre,
              '%s / %s' % (g_sp.nivel if g_sp else '', g_sp.nombre if g_sp else ''))

        e_ss, c_ss, g_ss = ctx('sexto_sec')
        check('REL-46 6.º de Secundaria NO egresa automáticamente',
              e_ss.condicion != 'egresado' and e_ss.activo is True,
              'condicion=%s activo=%s' % (e_ss.condicion, e_ss.activo))
        check('REL-47 y se queda en su curso del año origen',
              c_ss is not None and c_ss.ano_escolar_id == ID_A,
              'ano=%s' % (c_ss.ano_escolar_id if c_ss else None))

        # El mixto: lo que A2 dijera, el writer lo respeta.
        e_m, c_m, g_m = ctx('mixto')
        cond_m = SITUACION.get(IDS['mixto'])
        check('REL-48 A2 declara APLAZADO al que dejo un area caida',
              cond_m == PA.APLAZADO, str(cond_m))
        check('REL-48b y el APLAZADO PERMANECE en el año origen',
              c_m is not None and c_m.ano_escolar_id == ID_A,
              'ano=%s' % (c_m.ano_escolar_id if c_m else None))
        check('REL-48c sin historial: su proceso no ha terminado',
              not d.query(M.HistorialAcademico).filter_by(
                  estudiante_id=IDS['mixto']).count(), '')

        e_pr, c_pr, _ = ctx('proceso')
        check('REL-48d y el que resolvio su cuenta salio del año origen',
              c_pr is not None and c_pr.ano_escolar_id == ID_B,
              'ano=%s' % (c_pr.ano_escolar_id if c_pr else None))

        # Historial: solo para resultados DEFINITIVOS.
        hist = d.query(M.HistorialAcademico).all()
        condiciones = {h.condicion for h in hist}
        check('REL-49 el historial solo lleva resultados definitivos',
              condiciones <= set(PA.CONDICIONES_DEFINITIVAS),
              str(sorted(condiciones)))
        check('REL-50 y una fila como mucho por estudiante y año',
              len({(h.estudiante_id, h.ano_escolar_id) for h in hist})
              == len(hist), '%d filas' % len(hist))
        HIST_1 = len(hist)
    finally:
        d.close()

    # 4.7 · Reintentar no mueve a nadie dos veces.
    despues_1 = foto()
    r2 = client.post('/api/cierre-ano/promover',
                     json={'ano_origen_id': ID_A, 'ano_destino_id': ID_B},
                     headers=auth(DIR))
    check('REL-51 reintentar responde sin romperse',
          r2.status_code in (200, 400, 409), '-> %d' % r2.status_code)
    check('REL-52 y es IDEMPOTENTE: nadie se movió dos veces',
          foto() == despues_1, '')
    d = SessionLocal()
    try:
        check('REL-53 ni se duplicó el historial',
              d.query(M.HistorialAcademico).count() == HIST_1,
              '%d vs %d' % (d.query(M.HistorialAcademico).count(), HIST_1))
    finally:
        d.close()

    # 4.8 · El estado queda coherente tras un refresco.
    r_est = client.get('/api/cierre-ano/estado', headers=auth(DIR))
    check('REL-54 el estado responde tras la transición',
          r_est.status_code == 200, '-> %d' % r_est.status_code)
    if r_est.status_code == 200:
        je = r_est.json()
        check('REL-55 y ya no dice que el Cierre esté bloqueado',
              je.get('bloqueado_por_safety_lock') is False,
              str(je.get('bloqueado_por_safety_lock')))

    # ═══════════════════════════════════════════════════════════════════
    print("\n=== 5 · LA TABLA NUEVA SE CREA DE FORMA ADITIVA ===")

    from sqlalchemy import inspect as _inspect  # noqa: E402
    NUEVA = 'decision_academica_estudiante'
    _insp = _inspect(engine)
    check('REL-60 la tabla está registrada en Base.metadata',
          NUEVA in M.Base.metadata.tables, '')
    check('REL-61 y existe en la base tras create_all',
          NUEVA in _insp.get_table_names(), '')
    check('REL-62 con su unicidad por (estudiante, año)',
          any(tuple(c.name for c in u.columns)
              == ('estudiante_id', 'ano_escolar_id')
              for u in M.Base.metadata.tables[NUEVA].constraints
              if u.__class__.__name__ == 'UniqueConstraint'), '')

    # La prueba de que es ADITIVO: una base con TODO menos esa tabla, y
    # `create_all` encima. Nada se altera, nada se pierde.
    import tempfile as _tf  # noqa: E402
    from sqlalchemy import create_engine as _ce  # noqa: E402
    _t2 = _tf.mkdtemp(prefix='aditiva_')
    _e2 = _ce('sqlite:///' + os.path.join(_t2, 'prev.db').replace('\\', '/'))
    M.Base.metadata.create_all(
        bind=_e2,
        tables=[t for n, t in M.Base.metadata.tables.items() if n != NUEVA])
    _i2 = _inspect(_e2)
    _antes_t = {t: sorted(c['name'] for c in _i2.get_columns(t))
                for t in _i2.get_table_names()}
    M.Base.metadata.create_all(bind=_e2)
    _i3 = _inspect(_e2)
    _despues_t = {t: sorted(c['name'] for c in _i3.get_columns(t))
                  for t in _i3.get_table_names()}
    check('REL-63 sobre una base sin ella, create_all la CREA',
          set(_despues_t) - set(_antes_t) == {NUEVA},
          str(sorted(set(_despues_t) - set(_antes_t))))
    check('REL-64 sin perder ninguna tabla existente',
          not (set(_antes_t) - set(_despues_t)), '')
    check('REL-65 y sin alterar ninguna columna de las que había',
          not {t for t in _antes_t if _antes_t[t] != _despues_t.get(t)}, '')
    _e2.dispose()

    # ═══════════════════════════════════════════════════════════════════
    print("\n=== 6 · EL FRONTEND NO OFRECE NINGÚN WRITER LEGACY ===")

    _FE = os.path.join(os.path.dirname(_BACKEND), 'frontend', 'src')
    _todo = []
    for raiz, _, ficheros in os.walk(_FE):
        for f in ficheros:
            if f.endswith(('.ts', '.tsx')):
                _todo.append(open(os.path.join(raiz, f),
                                  encoding='utf-8').read())
    _junto = "\n".join(_todo)
    check('REL-70 ningún componente llama a /promocion/ejecutar',
          'promocion/ejecutar' not in _junto, '')
    check('REL-71 ni a /ano-escolar/promover',
          'ano-escolar/promover' not in _junto, '')

    _cierre = open(os.path.join(_FE, 'pages', 'cierre-ano',
                                'CierreAnoPage.tsx'), encoding='utf-8').read()
    check('REL-72 el aviso «mientras se reconstruye» desapareció',
          'reconstruye' not in _cierre
          and 'temporalmente deshabilitado' not in _cierre.lower(), '')
    check('REL-73 y el bloqueo de la pantalla SALE DEL BACKEND',
          'const CIERRE_BLOQUEADO = true' not in _cierre
          and "estado?.bloqueado_por_safety_lock === true" in _cierre, '')
    check('REL-74 los botones de cerrar y promover se atan a esa bandera',
          _cierre.count('disabled={cierreBloqueado') == 2,
          str(_cierre.count('disabled={cierreBloqueado')))

    # Las decisiones humanas siguen operativas: Dirección aporta el dato,
    # A2 decide el resultado. Nunca se escribe PROMOVIDO/REPROBADO a mano.
    for campo in ('alfabetizacion_inicial', 'decision_asistencia',
                  'repeticion_excepcional_segundo_ya_utilizada'):
        check('REL-75 la pantalla sigue registrando %s' % campo,
              campo in _cierre, '')
    check('REL-76 y no ofrece escribir el resultado académico directamente',
          "'PROMOVIDO'" not in _cierre and "'REPROBADO'" not in _cierre, '')

print()
print("=" * 98)
print("RESULTADO: %d PASARON / %d FALLARON" % (len(PASARON), len(FALLARON)))
print("=" * 98)
for f in FALLARON:
    print("  FALLA:", f)

sys.exit(1 if FALLARON else 0)
