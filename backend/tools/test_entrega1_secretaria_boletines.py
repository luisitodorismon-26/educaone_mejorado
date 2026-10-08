# -*- coding: utf-8 -*-
"""ENTREGA-1 — Secretaría, de punta a punta, por HTTP real.

POR QUÉ HTTP Y NO LLAMADAS DIRECTAS
===================================
Los permisos de EducaOne viven en `Depends(RolesRequired(...))`, que es una
dependencia de FastAPI: llamar a la función de Python por dentro se la salta
entera y el test daría verde sobre un endpoint abierto de par en par. Aquí
todo pasa por TestClient, con token, y lo que se comprueba son códigos de
estado reales.

LO QUE PROTEGE
==============
Dos cosas opuestas, y las dos importan:

  · que Secretaría PUEDA hacer su trabajo. El menú la llevaba al Registro
    Escolar desde siempre mientras el backend le devolvía 403 en las tres
    llamadas que llenan la página: un botón que siempre falla;
  · que NO pueda hacer el de nadie más. Ninguna escritura académica —notas,
    asistencia, recuperaciones, evaluaciones extra, Cierre de Año— ni
    administración de usuarios, años escolares o configuración.

Y que un colegio no vea al otro.

Base temporal aislada. Nunca producción.
"""
import datetime as dt
import os
import sys
import tempfile

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)
sys.path.insert(0, os.path.join(_BACKEND, "tools"))

_TMPDIR = tempfile.mkdtemp(prefix="eo_entrega1_sec_")
_TEST_DB = os.path.join(_TMPDIR, "entrega1.db").replace("\\", "/")
os.environ["DATABASE_URL"] = "sqlite:///" + _TEST_DB
os.environ.setdefault("ENVIRONMENT", "development")

assert "sge.db" not in os.environ["DATABASE_URL"], \
    "SEGURIDAD: el test usaria la base del repo"

from database import engine, SessionLocal  # noqa: E402
import models as M  # noqa: E402

M.Base.metadata.create_all(bind=engine)

from fastapi.testclient import TestClient  # noqa: E402
from app import app  # noqa: E402

client = TestClient(app)

PASARON, FALLARON = [], []


def check(nombre, cond, detalle=''):
    if cond:
        PASARON.append(nombre)
        print("  PASA   %-64s %s" % (nombre, detalle))
    else:
        FALLARON.append(nombre)
        print("  FALLA  %-64s %s" % (nombre, detalle))


def auth(tok):
    return {'Authorization': 'Bearer ' + tok}


def _limpiar_must_change(username):
    """Toda cuenta nueva nace con must_change_password=True y devuelve 423.

    Esta suite prueba ROLES, no la política de contraseñas —que tiene su
    propio archivo—, así que se limpia la marca antes de cada login. Es un
    atajo de prueba: no toca código de producción.
    """
    d = SessionLocal()
    try:
        u = d.query(M.Usuario).filter_by(username=username).first()
        if u is not None and u.must_change_password:
            u.must_change_password = False
            d.commit()
    finally:
        d.close()


def login(username, password):
    _limpiar_must_change(username)
    r = client.post('/api/auth/login',
                    json={'username': username, 'password': password})
    assert r.status_code == 200, '%s: %s' % (username, r.text)
    return r.json()['token']


# ═══════════════════════════════════════════════════════════════════════
# SETUP
# ═══════════════════════════════════════════════════════════════════════
print("\n=== SETUP ===")

with client:
    SA = login('superadmin', 'superadmin123')

    # Los DOS colegios se crean explícitamente con primaria y secundaria. El
    # colegio por defecto de `init_db` no trae primaria activa, y `/api/grados`
    # oculta los niveles que el plan no incluye: sin esto no habría curso de
    # primaria que probar.
    for nombre, codigo, usuario, clave in (
            ('Colegio Uno', 'uno', 'dir_uno', 'admin123uno'),
            ('Colegio Dos', 'dos', 'dir_dos', 'admin123dos')):
        r = client.post('/api/superadmin/colegios', json={
            'nombre': nombre, 'codigo': codigo, 'plan': 'enterprise',
            'admin_username': usuario, 'admin_password': clave,
            'plan_secundaria': True, 'plan_primaria': True,
        }, headers=auth(SA))
        assert r.status_code in (200, 201), r.text

    DIR_A = login('dir_uno', 'admin123uno')
    DIR_B = login('dir_dos', 'admin123dos')

    def montar(tok, sufijo):
        """Un colegio con curso de primaria, de secundaria y su gente."""
        grados = client.get('/api/grados', headers=auth(tok)).json()
        tandas = client.get('/api/tandas', headers=auth(tok)).json()
        g_pri = next(g for g in grados if g['nivel'] == 'primaria')
        g_sec = next(g for g in grados if g['nivel'] == 'secundaria')

        cursos = {}
        for clave, g in (('pri', g_pri), ('sec', g_sec)):
            r = client.post('/api/cursos', json={
                'grado_id': g['id'], 'tanda_id': tandas[0]['id'], 'nombre': 'A',
            }, headers=auth(tok))
            assert r.status_code in (200, 201), r.text
            cursos[clave] = r.json()['id']

        r = client.post('/api/asignaturas',
                        json={'nombre': 'Matemática', 'codigo': 'MAT'},
                        headers=auth(tok))
        asig = r.json()['id']

        ids = {}
        for rol, clave in (('profesor', 'prof'), ('coordinador', 'coord'),
                           ('secretaria', 'sec')):
            r = client.post('/api/usuarios', json={
                'username': '%s_%s' % (clave, sufijo),
                'password': '%s123456' % clave,
                'nombre': clave.title(), 'apellido': 'E1',
                'email': '%s_%s@e1.com' % (clave, sufijo), 'role': rol,
            }, headers=auth(tok))
            assert r.status_code in (200, 201), '%s: %s' % (rol, r.text)
            ids[clave] = r.json()['id']

        client.post('/api/asignaciones', json={
            'profesor_id': ids['prof'], 'curso_id': cursos['pri'],
            'asignatura_id': asig,
        }, headers=auth(tok))

        ests = {}
        for clave in ('pri', 'sec'):
            r = client.post('/api/estudiantes', json={
                'nombre': 'Est', 'apellido': clave.title(), 'sexo': 'M',
                'fecha_nacimiento': '2012-03-04',
                'curso_id': cursos[clave], 'no_lista': 1,
                'matricula': 'E1-%s-%s' % (clave, sufijo),
            }, headers=auth(tok))
            assert r.status_code in (200, 201), r.text
            ests[clave] = r.json()['id']

        return {'cursos': cursos, 'asig': asig, 'ests': ests,
                'sufijo': sufijo, **ids}

    A = montar(DIR_A, 'a')
    B = montar(DIR_B, 'b')

    SEC_A = login('sec_a', 'sec123456')
    SEC_B = login('sec_b', 'sec123456')
    PROF_A = login('prof_a', 'prof123456')
    COORD_A = login('coord_a', 'coord123456')

    # Asistencia y días hábiles, directo en la base: el objetivo de esta
    # suite son los PERMISOS, y el alta de asistencia es profesor-only por
    # diseño (eso se comprueba abajo, como debe ser: por HTTP).
    d = SessionLocal()
    try:
        est0 = d.get(M.Estudiante, A["ests"]["pri"])
        ano = d.query(M.AnoEscolar).filter_by(
            activo=True, colegio_id=est0.colegio_id).first()
        ano.set_dias_trabajados({'sep': 20, 'oct': 20, 'nov': 20})

        # Notas del alumno de secundaria: sin ellas los boletines se niegan a
        # generarse —con razón—, y entonces la prueba de descarga no probaría
        # nada. Cuatro competencias completas, que es lo que el MINERD pide.
        for comp in range(1, 5):
            d.add(M.CalificacionSecundaria(
                colegio_id=est0.colegio_id, estudiante_id=A['ests']['sec'],
                asignatura_id=A['asig'], ano_escolar_id=ano.id,
                competencia_numero=comp,
                p1=85.0, p2=90.0, p3=88.0, p4=92.0,
                promedio_competencia=88.75))
        est = d.get(M.Estudiante, A['ests']['pri'])
        for i, estado in enumerate(['presente'] * 6 + ['tardanza', 'ausente',
                                                       'excusa']):
            d.add(M.Asistencia(
                colegio_id=est.colegio_id, estudiante_id=est.id,
                curso_id=est.curso_id,
                fecha=(ano.fecha_inicio or dt.date(2025, 9, 1))
                + dt.timedelta(days=i + 5),
                estado=estado))
        d.commit()
        ANO_A_ID = ano.id
    finally:
        d.close()

    print("  2 colegios montados, secretaría de cada uno lista")

    # ═══════════════════════════════════════════════════════════════════
    # 1. LO QUE SECRETARÍA SÍ PUEDE
    # ═══════════════════════════════════════════════════════════════════
    print("\n=== 1 · LECTURAS PERMITIDAS ===")

    PERMITIDO = [
        ('E1S-01 panel de secretaría',
         '/api/dashboard/secretaria'),
        ('E1S-02 estadísticas del panel',
         '/api/dashboard/stats-rol'),
        ('E1S-03 listado de estudiantes',
         '/api/estudiantes'),
        ('E1S-04 ficha de un estudiante',
         '/api/estudiantes/%d' % A['ests']['pri']),
        ('E1S-05 cursos del colegio', '/api/cursos'),
        ('E1S-06 boletín web de secundaria',
         '/api/boletines/estudiante/%d' % A['ests']['sec']),
        ('E1S-07 boletín web de primaria',
         '/api/boletines-primaria/estudiante/%d' % A['ests']['pri']),
        ('E1S-08 cuadro de honor', '/api/estadisticas/cuadro-honor'),
        ('E1S-09 mensajes internos', '/api/mensajes'),
        ('E1S-10 recuperaciones de primaria (consulta)',
         '/api/recuperaciones-primaria/pendientes'),
    ]
    for nombre, ruta in PERMITIDO:
        r = client.get(ruta, headers=auth(SEC_A))
        check(nombre, r.status_code == 200, '%s -> %d' % (ruta, r.status_code))

    # ── Registro Escolar: el defecto que ENTREGA-1 corrige ─────────────
    print("\n=== 2 · REGISTRO ESCOLAR (la ruta que estaba muerta) ===")

    # La página pide ESTO al montar, y solo esto. Devolvía 403, así que la
    # entrada del menú llevaba a una pantalla vacía con un error.
    r = client.get('/api/registros/preview/%d' % A['cursos']['pri'],
                   headers=auth(SEC_A))
    check('E1S-11 la página del Registro Escolar carga para secretaría',
          r.status_code == 200, '-> %d' % r.status_code)
    if r.status_code == 200:
        check('E1S-11b y trae el curso y su nivel, que es lo que necesita',
              'nivel' in r.json() and 'curso' in r.json(),
              str(sorted(r.json().keys()))[:70])

    # ENTREGA-1.1 · El documento OFICIAL sí lo emite. Es lo que se entrega al
    # MINERD y entregarlo es trabajo de secretaría; el endpoint solo lee y
    # compone un PDF.
    for nombre, ruta in (
            ('E1S-12 registro oficial de primaria',
             '/api/registros/primaria/%d' % A['cursos']['pri']),
            ('E1S-14 registro oficial de secundaria',
             '/api/registros/secundaria/%d' % A['cursos']['sec'])):
        r = client.get(ruta, headers=auth(SEC_A))
        check(nombre + ' lo puede emitir', r.status_code != 403,
              '-> %d' % r.status_code)

    # El BORRADOR no. Es el documento de trabajo de quien LLENA el registro,
    # con su marca de agua y su «no apto para entrega oficial», y la suite de
    # tenant/roles lo exige desde v2.19.3-A. No son dos niveles del mismo
    # permiso: son dos documentos con dos destinatarios.
    for nombre, ruta in (
            ('E1S-13 borrador de primaria',
             '/api/registros/primaria/%d/preview-pdf' % A['cursos']['pri']),
            ('E1S-15 borrador de secundaria',
             '/api/registros/secundaria/%d/preview-pdf' % A['cursos']['sec'])):
        r = client.get(ruta, headers=auth(SEC_A))
        check(nombre + ' sigue fuera de su alcance', r.status_code == 403,
              '-> %d' % r.status_code)

    # Y el frontend dice lo mismo que el backend, en los dos sentidos.
    _pag = open(os.path.join(os.path.dirname(_BACKEND), 'frontend', 'src',
                             'pages', 'registro-escolar',
                             'RegistroEscolarPage.tsx'), encoding='utf-8').read()
    _linea_p = [l for l in _pag.splitlines() if 'const canPreview' in l][0]
    _linea_g = [l for l in _pag.splitlines() if 'const canGenerate' in l][0]
    check('E1S-15b canPreview NO ofrece el borrador a secretaría',
          "'secretaria'" not in _linea_p, _linea_p.strip()[:76])
    check('E1S-15c canGenerate SÍ le ofrece el oficial',
          "'secretaria'" in _linea_g, _linea_g.strip()[:76])

    # Y sin regresión para quienes ya entraban.
    for et, tok in (('dirección', DIR_A), ('coordinación', COORD_A),
                    ('profesor', PROF_A)):
        r = client.get('/api/registros/preview/%d' % A['cursos']['pri'],
                       headers=auth(tok))
        check('E1S-16 %s sigue entrando al registro' % et,
              r.status_code != 403, str(r.status_code))

    # ── Descargas ──────────────────────────────────────────────────────
    print("\n=== 3 · DESCARGAS DE BOLETINES ===")

    DESCARGAS = [
        ('E1S-20 boletín de padres, individual',
         '/api/boletines/estudiante/%d/pdf' % A['ests']['sec']),
        ('E1S-21 boletín de padres, curso completo',
         '/api/boletines/curso/%d/pdf' % A['cursos']['sec']),
        ('E1S-22 MINERD secundaria, individual',
         '/api/boletines/estudiante/%d/pdf-minerd-v2' % A['ests']['sec']),
        ('E1S-23 MINERD secundaria, curso completo',
         '/api/boletines/curso/%d/pdf-minerd-v2' % A['cursos']['sec']),
        ('E1S-24 Informe de Aprendizaje, individual',
         '/api/boletines-primaria/estudiante/%d/pdf' % A['ests']['pri']),
        ('E1S-25 Informe de Aprendizaje, curso completo',
         '/api/boletines-primaria/curso/%d/pdf' % A['cursos']['pri']),
        ('E1S-26 cuadro de honor en PDF',
         '/api/estadisticas/cuadro-honor/pdf'),
    ]
    # Se exige 200 Y un PDF de verdad. Un `!= 403` habría dado verde sobre un
    # 500, que es exactamente lo que pasaría si el nuevo desglose anual se
    # calculara con una variable fuera de alcance.
    for nombre, ruta in DESCARGAS:
        r = client.get(ruta, headers=auth(SEC_A))
        check(nombre, r.status_code == 200 and r.content[:4] == b'%PDF',
              '-> %d %s' % (r.status_code, r.content[:4]))

    # Un PDF de verdad, con su cabecera de descarga y nombre seguro.
    r = client.get('/api/boletines-primaria/estudiante/%d/pdf'
                   % A['ests']['pri'], headers=auth(SEC_A))
    disp = r.headers.get('content-disposition', '')
    check('E1S-27 el PDF llega como PDF',
          r.status_code == 200
          and r.headers.get('content-type', '').startswith('application/pdf')
          and r.content[:4] == b'%PDF',
          r.headers.get('content-type', ''))
    check('E1S-28 con nombre de archivo seguro',
          'attachment' in disp and '..' not in disp and '/' not in
          disp.split('filename=')[-1], disp[:60])

    # ═══════════════════════════════════════════════════════════════════
    # 4. LO QUE SECRETARÍA NO PUEDE
    # ═══════════════════════════════════════════════════════════════════
    print("\n=== 4 · ESCRITURA ACADÉMICA: CERRADA ===")

    PROHIBIDO_POST = [
        ('E1S-30 calificar (genérico)', '/api/calificaciones',
         {'estudiante_id': A['ests']['sec'], 'asignatura_id': A['asig'],
          'periodo': 1, 'nota': 100}),
        ('E1S-31 calificar primaria', '/api/calificaciones-primaria',
         {'estudiante_id': A['ests']['pri'], 'asignatura_id': A['asig'],
          'periodo': 1, 'competencia': 1, 'nota': 100}),
        ('E1S-32 calificar secundaria', '/api/calificaciones-secundaria',
         {'estudiante_id': A['ests']['sec'], 'asignatura_id': A['asig'],
          'periodo': 1, 'competencia': 1, 'nota': 100}),
        ('E1S-33 evaluación extra',
         '/api/calificaciones-secundaria/evaluacion-extra',
         {'estudiante_id': A['ests']['sec'], 'asignatura_id': A['asig'],
          'nota': 100}),
        ('E1S-34 registrar asistencia', '/api/asistencia',
         {'estudiante_id': A['ests']['pri'], 'estado': 'presente',
          'curso_id': A['cursos']['pri']}),
        ('E1S-35 asistencia masiva', '/api/asistencia/masivo',
         {'curso_id': A['cursos']['pri'], 'fecha': '2025-09-10',
          'asistencias': []}),
        ('E1S-36 recuperación de primaria', '/api/recuperaciones-primaria',
         {'estudiante_id': A['ests']['pri'], 'asignatura_id': A['asig'],
          'recuperacion_final': 70}),
        ('E1S-37 recuperación cualitativa',
         '/api/recuperacion-primaria/cualitativa',
         {'estudiante_id': A['ests']['pri'], 'asignatura_id': A['asig']}),
        ('E1S-38 decisiones de Cierre de Año', '/api/cierre-ano/decisiones',
         {'estudiante_id': A['ests']['pri']}),
        ('E1S-39 promover en Cierre de Año', '/api/cierre-ano/promover', {}),
        ('E1S-40 crear usuario', '/api/usuarios',
         {'username': 'colado', 'password': 'x1234567', 'nombre': 'C',
          'apellido': 'C', 'email': 'c@c.com', 'role': 'profesor'}),
        ('E1S-42 crear año escolar', '/api/ano-escolar',
         {'nombre': '2099-2100'}),
        ('E1S-43 cerrar el año', '/api/ano-escolar/%d/cerrar' % ANO_A_ID, {}),
        ('E1S-44 activar un año', '/api/ano-escolar/%d/activar' % ANO_A_ID, {}),
        ('E1S-45 promoción legacy', '/api/ano-escolar/promover', {}),
        ('E1S-46 declarar días hábiles',
         '/api/registros/dias-trabajados/%d' % ANO_A_ID, {'dias': {}}),
    ]
    for nombre, ruta, cuerpo in PROHIBIDO_POST:
        r = client.post(ruta, json=cuerpo, headers=auth(SEC_A))
        check(nombre, r.status_code == 403, '-> %d' % r.status_code)

    # SECRETARIA-2 · Crear, editar y retirar estudiantes PASARON a ser
    # trabajo de Secretaria: administra el expediente administrativo. Lo que
    # sigue cerrado —y es lo que ENTREGA-1 protegia de verdad— es la verdad
    # academica. Esas tres comprobaciones no se borran: se invierten aqui, y
    # su cobertura completa vive en `test_secretaria2_expediente_horarios`.
    r = client.post('/api/estudiantes', json={
        'nombre': 'Nueva', 'apellido': 'Alumna', 'sexo': 'F',
        'fecha_nacimiento': '2012-01-01', 'curso_id': A['cursos']['pri'],
        'matricula': 'E1S-NUEVA', 'no_lista': 40,
    }, headers=auth(SEC_A))
    check('E1S-41 SECRETARIA-2: ahora SI crea estudiantes',
          r.status_code in (200, 201), '-> %d' % r.status_code)
    _NUEVO = r.json().get('id') if r.status_code in (200, 201) else None

    if _NUEVO:
        r = client.put('/api/estudiantes/%d' % _NUEVO,
                       json={'telefono': '809-444-4444'}, headers=auth(SEC_A))
        check('E1S-50 y corrige datos administrativos', r.status_code == 200,
              '-> %d' % r.status_code)
        r = client.request('DELETE', '/api/estudiantes/%d' % _NUEVO,
                           json={'motivo_retiro': 'Prueba'},
                           headers=auth(SEC_A))
        check('E1S-52 y retira (logico, reversible)', r.status_code == 200,
              '-> %d' % r.status_code)

    # Pero NO sobre un expediente con huella academica: ese estudiante tiene
    # asistencia cargada, asi que su identidad queda fuera de su alcance.
    r = client.put('/api/estudiantes/%d' % A['ests']['pri'],
                   json={'nombre': 'Sustituido'}, headers=auth(SEC_A))
    check('E1S-52b y NO puede sustituir la identidad de uno con historia',
          r.status_code == 409
          and r.json().get('error') == 'CORRECCION_IDENTIDAD_REQUIERE_DIRECCION',
          '-> %d' % r.status_code)

    PROHIBIDO_OTROS = [
        ('E1S-51 desmarcar asistencia', 'delete',
         '/api/asistencia/%d' % A['ests']['pri'], None),
        ('E1S-53 configuración del colegio', 'put',
         '/api/configuracion/colegio', {'nombre': 'Otro'}),
        ('E1S-54 editar año escolar', 'put',
         '/api/ano-escolar/%d' % ANO_A_ID, {'nombre': 'X'}),
    ]
    for nombre, metodo, ruta, cuerpo in PROHIBIDO_OTROS:
        fn = getattr(client, metodo)
        r = fn(ruta, json=cuerpo, headers=auth(SEC_A)) if cuerpo is not None \
            else fn(ruta, headers=auth(SEC_A))
        check(nombre, r.status_code == 403, '-> %d' % r.status_code)

    PROHIBIDO_GET = [
        ('E1S-55 cohorte de promoción', '/api/promocion/estudiantes'),
        ('E1S-57 notas de un curso completo',
         '/api/reportes/notas/curso/%d/periodo/1' % A['cursos']['sec']),
    ]
    for nombre, ruta in PROHIBIDO_GET:
        r = client.get(ruta, headers=auth(SEC_A))
        check(nombre, r.status_code == 403, '-> %d' % r.status_code)

    # SECRETARIA-2 / AUDIT · La lista de retirados SI es suya, en lectura: ya
    # podia retirar y reactivar, y sin la lista la pestaña salia vacia y la
    # reactivacion era inalcanzable desde la pantalla. Lo que sigue cerrado es
    # el borrado fisico de esa misma pestaña, comprobado en E1S-13.
    r = client.get('/api/estudiantes/retirados', headers=auth(SEC_A))
    check('E1S-56 la lista de retirados SI la ve, en lectura',
          r.status_code == 200, '-> %d' % r.status_code)

    # Y que la negativa sea real: la base no cambió.
    d = SessionLocal()
    try:
        est = d.get(M.Estudiante, A['ests']['pri'])
        check('E1S-58 el expediente CON huella academica sigue intacto',
              est is not None and est.nombre == 'Est'
              and est.activo is True, est.nombre if est else 'BORRADO')
        check('E1S-59 y no se coló ninguna asistencia nueva',
              d.query(M.Asistencia).filter_by(
                  estudiante_id=A['ests']['pri']).count() == 9,
              str(d.query(M.Asistencia).filter_by(
                  estudiante_id=A['ests']['pri']).count()))
        # Las 4 del banco de pruebas, ni una mas: los intentos de la
        # secretaria no dejaron rastro.
        check('E1S-60 ni ninguna calificación nueva',
              d.query(M.CalificacionSecundaria).count() == 4,
              str(d.query(M.CalificacionSecundaria).count()))
    finally:
        d.close()

    # ═══════════════════════════════════════════════════════════════════
    # 5. SIN TOKEN Y ENTRE COLEGIOS
    # ═══════════════════════════════════════════════════════════════════
    print("\n=== 5 · SIN TOKEN Y AISLAMIENTO ENTRE COLEGIOS ===")

    for nombre, ruta in (('E1S-61 panel', '/api/dashboard/secretaria'),
                         ('E1S-62 estudiantes', '/api/estudiantes'),
                         ('E1S-63 registro escolar',
                          '/api/registros/preview/%d' % A['cursos']['pri'])):
        r = client.get(ruta)
        check(nombre + ' sin token = 401', r.status_code == 401,
              '-> %d' % r.status_code)

    CRUZADO = [
        ('E1S-64 ficha de estudiante ajeno',
         '/api/estudiantes/%d' % B['ests']['pri']),
        ('E1S-65 boletín de estudiante ajeno',
         '/api/boletines-primaria/estudiante/%d' % B['ests']['pri']),
        ('E1S-66 PDF de estudiante ajeno',
         '/api/boletines-primaria/estudiante/%d/pdf' % B['ests']['pri']),
        ('E1S-67 registro escolar de curso ajeno',
         '/api/registros/preview/%d' % B['cursos']['pri']),
        ('E1S-68 PDF del registro de curso ajeno',
         '/api/registros/primaria/%d' % B['cursos']['pri']),
        ('E1S-69 boletines del curso ajeno',
         '/api/boletines-primaria/curso/%d/pdf' % B['cursos']['pri']),
    ]
    for nombre, ruta in CRUZADO:
        r = client.get(ruta, headers=auth(SEC_A))
        check(nombre + ' no devuelve datos',
              r.status_code in (403, 404), '-> %d' % r.status_code)

    r = client.get('/api/estudiantes', headers=auth(SEC_A))
    ids_vistos = {e['id'] for e in r.json()} if r.status_code == 200 else set()
    check('E1S-70 el listado de A no contiene a nadie de B',
          not (ids_vistos & set(B['ests'].values())),
          '%d estudiantes' % len(ids_vistos))

    # Indistinguibilidad: un curso AJENO y uno INEXISTENTE tienen que dar la
    # misma respuesta. Antes daban 400 con textos distintos —«no pertenece a
    # este colegio» frente a «no existe»— y esa diferencia, sin filtrar ni un
    # dato, deja enumerar qué ids existen en otros colegios.
    # Cada ruta se prueba con un token que SÍ la alcanza: con uno que recibe
    # 403 por rol, la comprobación no diría nada sobre el tenant.
    for et, ruta, tok in (
            ('E1S-70b vista previa', '/api/registros/preview/%d', SEC_A),
            ('E1S-70c PDF de primaria', '/api/registros/primaria/%d', DIR_A),
            ('E1S-70d PDF de secundaria', '/api/registros/secundaria/%d', DIR_A),
            ('E1S-70d2 borrador de primaria',
             '/api/registros/primaria/%d/preview-pdf', DIR_A)):
        r_aj = client.get(ruta % B['cursos']['pri'], headers=auth(tok))
        r_no = client.get(ruta % 99999, headers=auth(tok))
        check(et + ': ajeno e inexistente son indistinguibles',
              r_aj.status_code == r_no.status_code == 404
              and r_aj.text == r_no.text,
              '%d / %d' % (r_aj.status_code, r_no.status_code))

    # Un lote VACÍO tampoco es una puerta: el permiso se mira antes que el
    # atajo de «sin cambios».
    r = client.post('/api/asistencia/masivo',
                    json={'curso_id': A['cursos']['pri'],
                          'fecha': '2025-09-10', 'asistencias': []},
                    headers=auth(SEC_A))
    check('E1S-70e un lote de asistencia vacío tampoco pasa',
          r.status_code == 403, '-> %d' % r.status_code)
    # Y el profesor sigue pudiendo mandar el suyo.
    r = client.post('/api/asistencia/masivo',
                    json={'curso_id': A['cursos']['pri'],
                          'fecha': '2025-09-10', 'asistencias': []},
                    headers=auth(PROF_A))
    check('E1S-70f pero el profesor no pierde el suyo', r.status_code == 200,
          '-> %d' % r.status_code)

    # ═══════════════════════════════════════════════════════════════════
    # 6. INDIVIDUAL Y LOTE, POR HTTP
    # ═══════════════════════════════════════════════════════════════════
    print("\n=== 6 · EL MISMO ESTUDIANTE, SUELTO Y EN EL LOTE ===")

    r_ind = client.get('/api/boletines-primaria/estudiante/%d/pdf'
                       % A['ests']['pri'], headers=auth(SEC_A))
    r_lote = client.get('/api/boletines-primaria/curso/%d/pdf'
                        % A['cursos']['pri'], headers=auth(SEC_A))
    check('E1S-71 los dos PDF se generan', r_ind.status_code == 200
          and r_lote.status_code == 200,
          '%d / %d' % (r_ind.status_code, r_lote.status_code))

    if r_ind.status_code == 200 and r_lote.status_code == 200:
        import io as _io
        from pypdf import PdfReader as _PR
        t_ind = "".join((p.extract_text() or '')
                        for p in _PR(_io.BytesIO(r_ind.content)).pages)
        t_lote = "".join((p.extract_text() or '')
                         for p in _PR(_io.BytesIO(r_lote.content)).pages)
        # El curso tiene un solo estudiante: el lote debe decir lo mismo.
        web = client.get('/api/boletines-primaria/estudiante/%d'
                         % A['ests']['pri'], headers=auth(SEC_A)).json()
        pa = web['asistencia_anual']['pct_asistencia']
        # ASISTENCIA CANÓNICA · la lista de este fixture no cubre todos los
        # días lectivos: el % oficial es N/D y se imprime la cobertura.
        _an = web['asistencia_anual']
        _cob = '%d de %d días' % (_an['dias_computados'], _an['dias_lectivos'])
        check('E1S-72 el PDF individual imprime N/D y la cobertura',
              pa is None and 'N/D' in t_ind and _cob in t_ind, _cob)
        check('E1S-73 y exactamente lo mismo en la página del lote',
              'N/D' in t_lote and _cob in t_lote, _cob)
        check('E1S-74 la vista web coincide con los dos',
              web['asistencia']['porcentaje'] == pa, str(pa))
        check('E1S-75 el desglose web distingue tardanzas y excusas',
              web['asistencia_anual']['tardanzas'] == 1
              and web['asistencia_anual']['excusas'] == 1
              and web['asistencia_anual']['ausencias'] == 1,
              str(web['asistencia_anual']))
        check('E1S-76 y cuenta 9 días, que son los que hay',
              web['asistencia_anual']['dias_computados'] == 9,
              str(web['asistencia_anual']['dias_computados']))

    # ═══════════════════════════════════════════════════════════════════
    # 7. SIN RUTAS MUERTAS EN EL MENÚ
    # ═══════════════════════════════════════════════════════════════════
    print("\n=== 7 · EL MENÚ NO OFRECE NADA QUE DEVUELVA 403 ===")

    _FE = os.path.join(os.path.dirname(_BACKEND), 'frontend', 'src')
    _layout = open(os.path.join(_FE, 'components', 'layout',
                                'MainLayout.tsx'), encoding='utf-8').read()
    _rutas_sec = []
    for linea in _layout.splitlines():
        if "'secretaria'" in linea and "path:" in linea:
            _rutas_sec.append(linea.split("path: '")[1].split("'")[0])
    check('E1S-80 el menú de secretaría tiene entradas', len(_rutas_sec) >= 6,
          str(_rutas_sec))
    check('E1S-81 y Registro Escolar es una de ellas',
          '/registro-escolar' in _rutas_sec, '')

    # Cada entrada del menú tiene que tener detrás, al menos, una lectura
    # que Secretaría pueda hacer.
    SONDA = {
        '/dashboard': '/api/dashboard/secretaria',
        '/estudiantes': '/api/estudiantes',
        '/boletines': '/api/cursos',
        '/registro-escolar': '/api/registros/preview/%d' % A['cursos']['pri'],
        '/cuadro-honor': '/api/estadisticas/cuadro-honor',
        '/comunicacion': '/api/mensajes',
        '/notas': '/api/notas-personales',
        '/recuperaciones-primaria': '/api/recuperaciones-primaria/pendientes',
    }
    for ruta in _rutas_sec:
        sonda = SONDA.get(ruta)
        if not sonda:
            continue
        r = client.get(sonda, headers=auth(SEC_A))
        check('E1S-82 %s no es una ruta muerta' % ruta, r.status_code != 403,
              '%s -> %d' % (sonda, r.status_code))

print()
print("=" * 96)
print("RESULTADO: %d PASARON / %d FALLARON" % (len(PASARON), len(FALLARON)))
print("=" * 96)
for f in FALLARON:
    print("  FALLA:", f)

sys.exit(1 if FALLARON else 0)
