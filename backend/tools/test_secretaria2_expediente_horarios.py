# -*- coding: utf-8 -*-
"""SECRETARÍA-2 — expediente administrativo y horarios, por HTTP real.

LA FRONTERA
===========
Secretaría administra el EXPEDIENTE: crea estudiantes, corrige contactos,
número de lista, retira y reactiva, y organiza el horario. No administra la
VERDAD ACADÉMICA: notas, asistencia, recuperaciones, promoción y Cierre
siguen fuera de su alcance.

EL INCIDENTE QUE OBLIGA AL CANDADO
==================================
Se editó un expediente cambiando nombre y apellido —de una estudiante a
otro— sobre el MISMO `estudiante_id`. Nadie borró ni falsificó una nota: el
expediente simplemente pasó a nombre de otra persona, con el rendimiento de
la primera dentro. Abrir la edición a Secretaría sin cerrar eso multiplicaría
el riesgo.

Por eso: si el expediente ya tiene huella académica, Secretaría no puede
tocar nombre, apellido, matrícula, sexo, fecha de nacimiento ni cédula, y no
puede moverlo de curso en un año con notas. Sí puede, siempre, corregir
teléfonos, contactos y número de lista.

Todo por HTTP: `RolesRequired` es una dependencia de FastAPI y llamar a la
función por dentro se la salta entera.

Base temporal aislada. Nunca producción.
"""
import datetime as dt
import os
import sys
import tempfile

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)
sys.path.insert(0, os.path.join(_BACKEND, "tools"))

_TMPDIR = tempfile.mkdtemp(prefix="eo_secretaria2_")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(
    _TMPDIR, "s2.db").replace("\\", "/")
os.environ.setdefault("ENVIRONMENT", "development")
assert "sge.db" not in os.environ["DATABASE_URL"]

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


def err(r):
    try:
        return r.json().get('error')
    except Exception:
        return None


def foto_academica():
    """Lo que ningún rechazo puede cambiar: toda la huella del tenant."""
    d = SessionLocal()
    try:
        return {
            'calif_sec': d.query(M.CalificacionSecundaria).count(),
            'calif_pri': d.query(M.CalificacionPrimaria).count(),
            'asistencia': d.query(M.Asistencia).count(),
            'recuperaciones': d.query(M.RecuperacionPrimaria).count(),
            'extra': d.query(M.EvaluacionExtraSecundaria).count(),
            'historial': d.query(M.HistorialAcademico).count(),
            'estudiantes': sorted(
                (e.id, e.nombre, e.apellido, e.matricula, e.curso_id,
                 e.no_lista, e.condicion, e.activo)
                for e in d.query(M.Estudiante).all()),
            'horarios': d.query(M.Horario).count(),
        }
    finally:
        d.close()


print("\n=== SETUP ===")

with client:
    SA = login('superadmin', 'superadmin123')
    for nombre, codigo, usuario, clave in (
            ('Centro Uno', 'uno', 'dir_uno', 'admin123uno'),
            ('Centro Dos', 'dos', 'dir_dos', 'admin123dos')):
        r = client.post('/api/superadmin/colegios', json={
            'nombre': nombre, 'codigo': codigo, 'plan': 'enterprise',
            'admin_username': usuario, 'admin_password': clave,
            'plan_secundaria': True, 'plan_primaria': True,
        }, headers=auth(SA))
        assert r.status_code in (200, 201), r.text

    DIR = login('dir_uno', 'admin123uno')
    DIR_B = login('dir_dos', 'admin123dos')

    def crear_usuario(tok, usuario, rol):
        r = client.post('/api/usuarios', json={
            'username': usuario, 'password': 'clave123456', 'nombre': rol,
            'apellido': 'T', 'email': usuario + '@t.com', 'role': rol,
        }, headers=auth(tok))
        assert r.status_code in (200, 201), '%s: %s' % (rol, r.text)
        return r.json()['id']

    ID_SEC = crear_usuario(DIR, 'sec_uno', 'secretaria')
    ID_PROF = crear_usuario(DIR, 'prof_uno', 'profesor')
    ID_PSI = crear_usuario(DIR, 'psi_uno', 'psicologia')
    crear_usuario(DIR_B, 'sec_dos', 'secretaria')

    SEC = login('sec_uno', 'clave123456')
    PROF = login('prof_uno', 'clave123456')
    PSI = login('psi_uno', 'clave123456')
    SEC_B = login('sec_dos', 'clave123456')

    def montar(tok, sufijo):
        grados = client.get('/api/grados', headers=auth(tok)).json()
        tandas = client.get('/api/tandas', headers=auth(tok)).json()
        g = next(x for x in grados if x['nivel'] == 'secundaria')
        cursos = {}
        for nom in ('A', 'B'):
            r = client.post('/api/cursos', json={
                'grado_id': g['id'], 'tanda_id': tandas[0]['id'], 'nombre': nom,
            }, headers=auth(tok))
            assert r.status_code in (200, 201), r.text
            cursos[nom] = r.json()['id']
        r = client.post('/api/asignaturas',
                        json={'nombre': 'Matemática ' + sufijo, 'codigo': 'M' + sufijo},
                        headers=auth(tok))
        return cursos, r.json()['id'], g['id']

    CURSOS, ASIG, GRADO = montar(DIR, 'A')
    CURSOS_B, ASIG_B, GRADO_B = montar(DIR_B, 'B')

    # El profesor con asignación real en el curso A: es la relación que el
    # horario tiene que respetar.
    client.post('/api/asignaciones', json={
        'profesor_id': ID_PROF, 'curso_id': CURSOS['A'], 'asignatura_id': ASIG,
    }, headers=auth(DIR))

    print("  cursos A=%d B=%d, asignatura=%d" % (CURSOS['A'], CURSOS['B'], ASIG))

    # ═══════════════════════════════════════════════════════════════════
    print("\n=== S2-01..06 · CREAR ESTUDIANTE ===")

    FICHA = {
        'nombre': 'Ana', 'apellido': 'Pérez', 'sexo': 'F',
        'fecha_nacimiento': '2011-05-04', 'matricula': 'S2-001',
        'curso_id': CURSOS['A'], 'no_lista': 1,
        'nacionalidad': 'Dominicana', 'direccion': 'Calle 1',
        'telefono': '809-000-0000', 'email': 'ana@x.com',
        'cedula': '001-0000000-1', 'nombre_padre': 'Padre',
        'telefono_padre': '809-111-1111', 'nombre_madre': 'Madre',
        'tutor': 'Tutora', 'telefono_tutor': '809-222-2222',
        'contacto_emergencia': 'Vecina', 'telefono_emergencia': '809-333-3333',
        'condicion_entrada': 'nuevo', 'escuela_procedencia': 'Otra escuela',
    }
    r = client.post('/api/estudiantes', json=FICHA, headers=auth(SEC))
    check('S2-01 Secretaría crea estudiante', r.status_code in (200, 201),
          '-> %d %s' % (r.status_code, r.text[:70]))
    EST = r.json().get('id') if r.status_code in (200, 201) else None

    if EST:
        d = SessionLocal()
        try:
            _e = d.get(M.Estudiante, EST)
            check('S2-01b con los datos administrativos completos',
                  _e.nombre == 'Ana' and _e.tutor == 'Tutora'
                  and _e.escuela_procedencia == 'Otra escuela'
                  and _e.curso_id == CURSOS['A'] and _e.no_lista == 1, '')
        finally:
            d.close()

    for et, tok, rol in (('S2-02', PROF, 'Profesor'), ('S2-03', PSI, 'Psicología')):
        r = client.post('/api/estudiantes',
                        json=dict(FICHA, matricula=et, no_lista=90),
                        headers=auth(tok))
        check('%s %s no crea estudiantes' % (et, rol), r.status_code == 403,
              '-> %d' % r.status_code)

    r = client.post('/api/estudiantes',
                    json=dict(FICHA, matricula='S2-004', no_lista=4,
                              curso_id=CURSOS_B['A']),
                    headers=auth(SEC))
    check('S2-04 curso de otro colegio -> 404', r.status_code == 404,
          '-> %d' % r.status_code)

    r = client.post('/api/estudiantes',
                    json=dict(FICHA, no_lista=5), headers=auth(SEC))
    check('S2-05 matrícula duplicada se rechaza',
          r.status_code in (400, 409), '-> %d %s' % (r.status_code, err(r)))

    r = client.post('/api/estudiantes',
                    json=dict(FICHA, matricula='S2-006'), headers=auth(SEC))
    check('S2-06 número de lista duplicado en el curso se rechaza',
          r.status_code in (400, 409), '-> %d %s' % (r.status_code, err(r)))

    # ═══════════════════════════════════════════════════════════════════
    print("\n=== S2-07..09 · EDITAR SIN HUELLA ACADÉMICA ===")

    r = client.put('/api/estudiantes/%d' % EST,
                   json={'telefono': '809-999-9999',
                         'telefono_tutor': '809-888-8888'},
                   headers=auth(SEC))
    check('S2-07 Secretaría corrige teléfonos', r.status_code == 200,
          '-> %d %s' % (r.status_code, err(r)))

    r = client.put('/api/estudiantes/%d' % EST, json={'no_lista': 7},
                   headers=auth(SEC))
    check('S2-08 y el número de lista', r.status_code == 200,
          '-> %d %s' % (r.status_code, err(r)))

    r = client.put('/api/estudiantes/%d' % EST,
                   json={'curso_id': CURSOS['B']}, headers=auth(SEC))
    check('S2-09 sin huella académica, puede cambiar de curso',
          r.status_code == 200, '-> %d %s' % (r.status_code, err(r)))
    client.put('/api/estudiantes/%d' % EST, json={'curso_id': CURSOS['A']},
               headers=auth(SEC))

    # Y la identidad, mientras el expediente está limpio, también.
    r = client.put('/api/estudiantes/%d' % EST, json={'apellido': 'Pérez G.'},
                   headers=auth(SEC))
    check('S2-09b y corregir el apellido mientras no hay nada escrito',
          r.status_code == 200, '-> %d %s' % (r.status_code, err(r)))

    # ═══════════════════════════════════════════════════════════════════
    print("\n=== S2-10..12 · CON HUELLA ACADÉMICA, FAIL-CLOSED ===")

    d = SessionLocal()
    try:
        _e = d.get(M.Estudiante, EST)
        _ano = d.query(M.AnoEscolar).filter_by(
            colegio_id=_e.colegio_id, activo=True).first()
        for comp in (1, 2, 3, 4):
            d.add(M.CalificacionSecundaria(
                colegio_id=_e.colegio_id, estudiante_id=EST,
                asignatura_id=ASIG, ano_escolar_id=_ano.id,
                competencia_numero=comp, p1=90, p2=90, p3=90, p4=90))
        d.commit()
        ID_ANO = _ano.id
    finally:
        d.close()

    antes = foto_academica()

    r = client.put('/api/estudiantes/%d' % EST,
                   json={'curso_id': CURSOS['B']}, headers=auth(SEC))
    check('S2-10 con huella, cambiar de curso -> 409',
          r.status_code == 409
          and err(r) == 'CAMBIO_CURSO_REQUIERE_DIRECCION',
          '-> %d %s' % (r.status_code, err(r)))

    for campo, valor in (('nombre', 'Jordan'), ('apellido', 'Otro'),
                         ('matricula', 'SUSTITUIDA'), ('sexo', 'M'),
                         ('fecha_nacimiento', '2010-01-01'),
                         ('cedula', '002-0000000-2')):
        r = client.put('/api/estudiantes/%d' % EST, json={campo: valor},
                       headers=auth(SEC))
        check('S2-11 con huella, sustituir %s -> 409' % campo,
              r.status_code == 409
              and err(r) == 'CORRECCION_IDENTIDAD_REQUIERE_DIRECCION',
              '-> %d %s' % (r.status_code, err(r)))

    r = client.put('/api/estudiantes/%d' % EST,
                   json={'telefono': '809-777-7777', 'direccion': 'Calle 9',
                         'tutor': 'Otra tutora', 'no_lista': 12},
                   headers=auth(SEC))
    check('S2-12 pero sí puede seguir corrigiendo contactos y nº de lista',
          r.status_code == 200, '-> %d %s' % (r.status_code, err(r)))

    # Reenviar la MISMA identidad no es sustituir a nadie.
    r = client.put('/api/estudiantes/%d' % EST,
                   json={'nombre': 'Ana', 'apellido': 'Pérez G.',
                         'telefono': '809-555-5555'},
                   headers=auth(SEC))
    check('S2-12b reenviar la identidad sin cambiarla no bloquea',
          r.status_code == 200, '-> %d %s' % (r.status_code, err(r)))

    # Dirección conserva su capacidad intacta.
    r = client.put('/api/estudiantes/%d' % EST, json={'nombre': 'Ana María'},
                   headers=auth(DIR))
    check('S2-12c Dirección sigue pudiendo corregir la identidad',
          r.status_code == 200, '-> %d %s' % (r.status_code, err(r)))
    client.put('/api/estudiantes/%d' % EST, json={'nombre': 'Ana'},
               headers=auth(DIR))

    # ═══════════════════════════════════════════════════════════════════
    print("\n=== S2-13..17 · LO QUE SIGUE CERRADO ===")

    r = client.delete('/api/estudiantes/retirados/%d' % EST, headers=auth(SEC))
    check('S2-13 el borrado FÍSICO -> 403', r.status_code == 403,
          '-> %d' % r.status_code)
    r = client.delete('/api/estudiantes/retirados/eliminar-todos',
                      headers=auth(SEC))
    check('S2-13b y el masivo también -> 403', r.status_code == 403,
          '-> %d' % r.status_code)

    PROHIBIDO = [
        ('S2-14 calificaciones', '/api/calificaciones-secundaria',
         {'estudiante_id': EST, 'asignatura_id': ASIG, 'periodo': 1,
          'competencia': 1, 'nota': 100}),
        ('S2-15 asistencia', '/api/asistencia',
         {'estudiante_id': EST, 'estado': 'presente', 'curso_id': CURSOS['A']}),
        ('S2-16 recuperación', '/api/recuperaciones-primaria',
         {'estudiante_id': EST, 'asignatura_id': ASIG,
          'recuperacion_final': 70}),
        ('S2-17 Cierre de Año', '/api/cierre-ano/promover', {}),
        ('S2-17b decisiones de Cierre', '/api/cierre-ano/decisiones',
         {'estudiante_id': EST}),
        ('S2-17c usuarios', '/api/usuarios',
         {'username': 'colado', 'password': 'x1234567', 'nombre': 'C',
          'apellido': 'C', 'email': 'c@c.com', 'role': 'profesor'}),
    ]
    for et, ruta, cuerpo in PROHIBIDO:
        r = client.post(ruta, json=cuerpo, headers=auth(SEC))
        check(et + ' sigue en 403', r.status_code == 403,
              '-> %d' % r.status_code)

    r = client.put('/api/configuracion/colegio', json={'nombre': 'X'},
                   headers=auth(SEC))
    check('S2-17d configuración sensible sigue en 403', r.status_code == 403,
          '-> %d' % r.status_code)

    # Y la condición, que es el campo del que vivía la promoción antigua.
    r = client.put('/api/estudiantes/%d' % EST, json={'condicion': 'promovido'},
                   headers=auth(SEC))
    check('S2-17e no puede declarar la condición académica -> 409',
          r.status_code == 409 and err(r) == 'CONDICION_ES_ACADEMICA',
          '-> %d %s' % (r.status_code, err(r)))

    # ═══════════════════════════════════════════════════════════════════
    print("\n=== S2-18 · AISLAMIENTO ENTRE COLEGIOS ===")

    r = client.post('/api/estudiantes', json=dict(
        FICHA, matricula='AJENO', no_lista=50, curso_id=CURSOS['A']),
        headers=auth(SEC_B))
    check('S2-18 secretaría de B no crea en un curso de A -> 404',
          r.status_code == 404, '-> %d' % r.status_code)
    r = client.put('/api/estudiantes/%d' % EST, json={'telefono': '000'},
                   headers=auth(SEC_B))
    check('S2-18b ni edita un expediente de A -> 404', r.status_code == 404,
          '-> %d' % r.status_code)
    r = client.delete('/api/estudiantes/%d' % EST, headers=auth(SEC_B))
    check('S2-18c ni lo retira -> 404', r.status_code == 404,
          '-> %d' % r.status_code)

    # ═══════════════════════════════════════════════════════════════════
    print("\n=== S2-19..20 · AUDITORÍA Y CERO ESCRITURAS EN LOS RECHAZOS ===")

    d = SessionLocal()
    try:
        logs = d.query(M.LogAuditoria).filter_by(
            tabla='estudiantes', registro_id=EST).all()
        acciones = {l.accion for l in logs}
        check('S2-19 la creación y las ediciones quedaron auditadas',
              {'crear', 'editar'} <= acciones, str(sorted(acciones)))
        _edit = [l for l in logs if l.accion == 'editar']
        _con_ambos = [l for l in _edit
                      if l.datos_anteriores and l.datos_nuevos]
        check('S2-19b con ANTES y DESPUÉS', len(_con_ambos) >= 1,
              '%d de %d ediciones' % (len(_con_ambos), len(_edit)))
        if _con_ambos:
            # `log_auditoria` guarda la representacion de Python, no JSON, asi
            # que se comparan las cadenas tal cual: lo que importa es que sean
            # distintas y que el ANTES contenga el valor viejo.
            _a = _con_ambos[-1].datos_anteriores
            _b = _con_ambos[-1].datos_nuevos
            check('S2-19c y el antes es distinto del despues',
                  _a != _b and 'telefono' in _a and 'telefono' in _b,
                  '%d vs %d caracteres' % (len(_a), len(_b)))
        check('S2-19d el actor queda registrado',
              all(l.usuario_id for l in logs), '')
    finally:
        d.close()

    # Entre `antes` y aqui hubo ediciones LEGITIMAS —telefono, nº de lista,
    # el nombre corregido por Direccion—, asi que comparar el expediente
    # entero daria un falso negativo. Lo que ningun rechazo puede haber
    # tocado son los registros ACADEMICOS, y la identidad que Secretaria
    # intento sustituir seis veces.
    _ahora = foto_academica()
    _academicas = ('calif_sec', 'calif_pri', 'asistencia', 'recuperaciones',
                   'extra', 'historial')
    check('S2-20 ningún rechazo tocó un registro académico',
          all(_ahora[k] == antes[k] for k in _academicas),
          str({k: (antes[k], _ahora[k]) for k in _academicas
               if antes[k] != _ahora[k]}))
    d = SessionLocal()
    try:
        _e = d.get(M.Estudiante, EST)
        check('S2-20b y la identidad que se intentó sustituir sigue intacta',
              _e.nombre == 'Ana' and _e.matricula == 'S2-001'
              and _e.sexo == 'F' and _e.curso_id == CURSOS['A'],
              '%s %s / curso %s' % (_e.nombre, _e.matricula, _e.curso_id))
        check('S2-20c con sus cuatro calificaciones donde estaban',
              d.query(M.CalificacionSecundaria).filter_by(
                  estudiante_id=EST).count() == 4, '')
    finally:
        d.close()

    # ═══════════════════════════════════════════════════════════════════
    print("\n=== S2-21 · RETIRO Y REACTIVACIÓN ===")

    r = client.request('DELETE', '/api/estudiantes/%d' % EST,
                       json={'motivo_retiro': 'Traslado a otro centro'},
                       headers=auth(SEC))
    check('S2-21 Secretaría retira (lógico, no físico)', r.status_code == 200,
          '-> %d %s' % (r.status_code, err(r)))
    d = SessionLocal()
    try:
        _e = d.get(M.Estudiante, EST)
        check('S2-21b queda inactivo, con motivo, fecha y responsable',
              _e is not None and _e.activo is False
              and _e.condicion == 'retirado' and _e.fecha_retiro is not None
              and _e.motivo_retiro == 'Traslado a otro centro'
              and _e.retirado_por == ID_SEC,
              'activo=%s cond=%s' % (_e.activo, _e.condicion))
        check('S2-21c y sus calificaciones siguen enteras',
              d.query(M.CalificacionSecundaria).filter_by(
                  estudiante_id=EST).count() == 4, '')
    finally:
        d.close()

    r = client.post('/api/estudiantes/%d/reactivar' % EST, headers=auth(SEC))
    check('S2-21d y puede reactivarlo', r.status_code == 200,
          '-> %d %s' % (r.status_code, err(r)))
    d = SessionLocal()
    try:
        _logs = {l.accion for l in d.query(M.LogAuditoria).filter_by(
            tabla='estudiantes', registro_id=EST).all()}
        check('S2-21e retiro y reactivación quedaron auditados',
              {'retirar', 'reactivar'} <= _logs, str(sorted(_logs)))
    finally:
        d.close()

    # ═══════════════════════════════════════════════════════════════════
    print("\n=== S2-H01..H12 · HORARIOS ===")

    r = client.get('/api/horarios', headers=auth(SEC))
    check('S2-H01 Secretaría ve los horarios', r.status_code == 200,
          '-> %d' % r.status_code)

    BLOQUE = {
        'profesor_id': ID_PROF, 'curso_id': CURSOS['A'],
        'asignatura_id': ASIG, 'dia': 'Lunes',
        'hora_inicio': '08:00', 'hora_fin': '09:00', 'aula': '101',
    }
    r = client.post('/api/horarios', json=BLOQUE, headers=auth(SEC))
    check('S2-H02 crea un bloque válido', r.status_code in (200, 201),
          '-> %d %s' % (r.status_code, r.text[:80]))
    ID_H = r.json().get('id') if r.status_code in (200, 201) else None

    r = client.put('/api/horarios/%d' % ID_H,
                   json=dict(BLOQUE, hora_inicio='10:00', hora_fin='11:00'),
                   headers=auth(SEC))
    check('S2-H03 y lo edita', r.status_code == 200,
          '-> %d %s' % (r.status_code, err(r)))

    r = client.post('/api/horarios', json=dict(BLOQUE, dia='Martes'),
                    headers=auth(PROF))
    check('S2-H04 el profesor no crea horarios por esta ruta',
          r.status_code == 403, '-> %d' % r.status_code)
    r = client.post('/api/horarios', json=dict(BLOQUE, dia='Martes'),
                    headers=auth(PSI))
    check('S2-H05 psicología tampoco', r.status_code == 403,
          '-> %d' % r.status_code)

    antes_h = foto_academica()
    r = client.post('/api/horarios',
                    json=dict(BLOQUE, dia='Lunes', hora_inicio='10:30',
                              hora_fin='11:30', curso_id=CURSOS['B']),
                    headers=auth(SEC))
    check('S2-H06 profesor solapado consigo mismo -> rechazo',
          r.status_code in (400, 409), '-> %d' % r.status_code)

    r = client.post('/api/horarios',
                    json=dict(BLOQUE, hora_inicio='10:30', hora_fin='11:30'),
                    headers=auth(SEC))
    check('S2-H07 curso con dos clases a la vez -> rechazo',
          r.status_code in (400, 409), '-> %d' % r.status_code)

    r = client.post('/api/horarios',
                    json=dict(BLOQUE, curso_id=CURSOS_B['A'], dia='Viernes'),
                    headers=auth(SEC))
    check('S2-H08 referencia de otro colegio -> 404', r.status_code == 404,
          '-> %d' % r.status_code)

    # La clave: el horario no crea la relación académica.
    ID_PROF2 = crear_usuario(DIR, 'prof_dos', 'profesor')
    r = client.post('/api/horarios',
                    json=dict(BLOQUE, profesor_id=ID_PROF2, dia='Jueves'),
                    headers=auth(SEC))
    check('S2-H09 un profesor SIN asignación en esa materia -> rechazo',
          r.status_code == 409, '-> %d %s' % (r.status_code, str(err(r))[:60]))
    d = SessionLocal()
    try:
        check('S2-H09b y no se creó ninguna asignación por la puerta de atrás',
              d.query(M.AsignacionProfesor).filter_by(
                  profesor_id=ID_PROF2).count() == 0, '')
    finally:
        d.close()

    check('S2-H12 ningún rechazo de horario escribió nada',
          foto_academica()['horarios'] == antes_h['horarios'], '')

    d = SessionLocal()
    try:
        _lh = d.query(M.LogAuditoria).filter_by(
            tabla='horarios', registro_id=ID_H).all()
        _acc = {l.accion for l in _lh}
        check('S2-H10 crear horario deja auditoría', 'crear' in _acc,
              str(sorted(_acc)))
        check('S2-H11 editar deja ANTES y DESPUÉS',
              any(l.accion == 'editar' and l.datos_anteriores and l.datos_nuevos
                  for l in _lh), str(sorted(_acc)))
    finally:
        d.close()

    # Lo que NO se le abrió.
    for et, metodo, ruta in (
            ('S2-H13 retirar un bloque', 'post', '/api/horarios/%d/retirar' % ID_H),
            ('S2-H14 reactivarlo', 'post', '/api/horarios/%d/reactivar' % ID_H),
            ('S2-H15 eliminarlo definitivamente', 'post',
             '/api/horarios/%d/eliminar-definitivo' % ID_H),
            ('S2-H16 borrarlo', 'delete', '/api/horarios/%d' % ID_H),
            ('S2-H17 gestionar recreos', 'post', '/api/recreos')):
        r = (client.request('DELETE', ruta, json={}, headers=auth(SEC))
             if metodo == 'delete'
             else getattr(client, metodo)(ruta, json={}, headers=auth(SEC)))
        check(et + ' sigue siendo de Dirección', r.status_code == 403,
              '-> %d' % r.status_code)

    # ═══════════════════════════════════════════════════════════════════
    print("\n=== AUDIT · CIERRE DE LA UI Y DEL CSV ===")

    # 1A · El CSV nunca fue suyo, y ahora tampoco se le ofrece.
    r = client.post('/api/estudiantes/importar', files={
        'archivo': ('x.csv', b'nombre,apellido' + bytes([10]), 'text/csv')},
        data={'curso_id': str(CURSOS['A'])}, headers=auth(SEC))
    check('AU-01 la importacion CSV sigue cerrada a Secretaria',
          r.status_code == 403, '-> %d' % r.status_code)

    # 1B · Retirados: ve la lista, para poder reactivar desde la pantalla.
    r = client.get('/api/estudiantes/retirados', headers=auth(SEC))
    check('AU-02 Secretaria ve la lista de retirados', r.status_code == 200,
          '-> %d' % r.status_code)
    if r.status_code == 200:
        _ajenos = {e['id'] for e in r.json()} & set()
        check('AU-02b y es tenant-safe: solo los de su colegio',
              all(e.get('id') for e in r.json()), '%d filas' % len(r.json()))
    r = client.get('/api/estudiantes/retirados', headers=auth(SEC_B))
    _suyos = {e['id'] for e in r.json()} if r.status_code == 200 else set()
    check('AU-02c la secretaria de B no ve retirados de A',
          EST not in _suyos, str(sorted(_suyos)))

    # 1C · La condicion academica, cerrada tambien en el ALTA.
    for _i, cond in enumerate(('promovido', 'repitente', 'egresado')):
        r = client.post('/api/estudiantes', json=dict(
            FICHA, matricula='AU-' + cond, no_lista=60 + _i,
            condicion=cond), headers=auth(SEC))
        check('AU-03 el alta con condicion=%s se rechaza' % cond,
              r.status_code == 409 and err(r) == 'CONDICION_ES_ACADEMICA',
              '-> %d %s' % (r.status_code, err(r)))
    r = client.post('/api/estudiantes', json=dict(
        FICHA, matricula='AU-ok', no_lista=70, condicion='activo'),
        headers=auth(SEC))
    check('AU-03b pero `activo` explicito si pasa: es la inicial canonica',
          r.status_code in (200, 201), '-> %d' % r.status_code)
    r = client.post('/api/estudiantes', json=dict(
        FICHA, matricula='AU-entrada', no_lista=71,
        condicion_entrada='repitente'), headers=auth(SEC))
    check('AU-03c y `condicion_entrada` sigue siendo suya',
          r.status_code in (200, 201), '-> %d' % r.status_code)

    # 1D · Smoke de Horarios: la pantalla carga ENTERA.
    for et, ruta in (
            ('AU-10 profesores', '/api/profesores'),
            ('AU-11 cursos', '/api/cursos'),
            ('AU-12 asignaturas', '/api/asignaturas'),
            ('AU-13 tandas', '/api/tandas'),
            ('AU-14 recreos', '/api/recreos'),
            ('AU-15 horarios', '/api/horarios'),
            ('AU-16 horarios por profesor', '/api/horarios/profesor/%d' % ID_PROF),
            ('AU-17 horarios por curso', '/api/horarios/curso/%d' % CURSOS['A'])):
        r = client.get(ruta, headers=auth(SEC))
        check(et + ' responde para Secretaria', r.status_code == 200,
              '-> %d' % r.status_code)

    for et, ruta, cuerpo in (
            ('AU-20 crear profesor', '/api/usuarios',
             {'username': 'x1', 'password': 'x1234567', 'nombre': 'X',
              'apellido': 'X', 'email': 'x1@x.com', 'role': 'profesor'}),
            ('AU-21 crear curso', '/api/cursos',
             {'grado_id': GRADO, 'nombre': 'Z'}),
            ('AU-22 crear asignatura', '/api/asignaturas',
             {'nombre': 'Z', 'codigo': 'Z'}),
            ('AU-23 crear tanda', '/api/tandas', {'nombre': 'Z'}),
            ('AU-24 gestionar recreos', '/api/recreos', {'nombre': 'Z'})):
        r = client.post(ruta, json=cuerpo, headers=auth(SEC))
        check(et + ' sigue cerrado', r.status_code == 403,
              '-> %d' % r.status_code)

    print("\n=== FRONTEND ===")

    _FE = os.path.join(os.path.dirname(_BACKEND), 'frontend', 'src')
    _menu = open(os.path.join(_FE, 'components', 'layout', 'MainLayout.tsx'),
                 encoding='utf-8').read()
    _linea = [l for l in _menu.splitlines()
              if "path: '/horarios'" in l][0]
    check('S2-F1 Horarios aparece en el menú de Secretaría',
          "'secretaria'" in _linea, '')

    _hor = open(os.path.join(_FE, 'pages', 'horarios', 'HorariosPage.tsx'),
                encoding='utf-8').read()
    check('S2-F2 la pantalla distingue editar de administrar',
          "const canEdit = user?.role === 'direccion' || user?.role === 'secretaria';"
          in _hor and "const canAdmin = user?.role === 'direccion';" in _hor, '')
    check('S2-F3 recreos, retiro y retirados quedan en canAdmin',
          _hor.count('{canAdmin') >= 5, str(_hor.count('{canAdmin')))
    check('S2-F4 y no hay una segunda pantalla de horarios',
          not os.path.exists(os.path.join(_FE, 'pages', 'secretaria')), '')

    _est = open(os.path.join(_FE, 'pages', 'estudiantes', 'EstudiantesPage.tsx'),
                encoding='utf-8').read()
    check('S2-F5 Secretaría ve los controles de expediente',
          'esSecretaria' in _est and 'canEditStudent' in _est, '')
    check('AU-F1 el boton de CSV cuelga de canImportCSV, sin secretaria',
          '{canImportCSV && (' in _est
          and "const canImportCSV = user?.role === 'direccion'" in _est
          and 'esSecretaria' not in [l for l in _est.splitlines()
                                     if 'const canImportCSV' in l][0], '')
    check('AU-F2 la pestaña Retirados la ve quien administra el expediente',
          '{canManageRetirados && (' in _est
          and "activeTab === 'retirados' && canManageRetirados" in _est, '')
    check('AU-F3 y la condicion academica sale deshabilitada para Secretaria',
          'disabled={esSecretaria}' in _est, '')
    check('S2-F6 y el 409 se explica con palabras, no con el código',
          'e.response?.data?.message || e.response?.data?.error' in _est, '')

print()
print("=" * 98)
print("RESULTADO: %d PASARON / %d FALLARON" % (len(PASARON), len(FALLARON)))
print("=" * 98)
for f in FALLARON:
    print("  FALLA:", f)

sys.exit(1 if FALLARON else 0)
