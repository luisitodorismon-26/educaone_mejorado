# -*- coding: utf-8 -*-
"""ADMIN — eliminar una ficha creada por error.

DOS OPERACIONES QUE NO SON LA MISMA
===================================
RETIRAR es para el estudiante que existió y se fue: su expediente es parte
de la historia del centro, el maestro lo ve como RETIRADO en la asistencia
de aquel mes, y puede volver. No se borra nada, nunca.

ELIMINAR POR ERROR es para la ficha que nunca debió existir: un duplicado,
una lista equivocada, alguien que no es de este centro. Dejarla como
«Retirada» para siempre ensucia listados, estadísticas y Cierre con alguien
que no es nadie.

ESTO NO RESUCITA EL PURGADO ANTIGUO
===================================
`DELETE /api/estudiantes/retirados/{id}` sigue respondiendo 403 sin tocar la
base, y se comprueba aquí. Aquel endpoint contemplaba 6 de las 14 tablas que
referencian a un estudiante: ante un expediente real fallaba con
IntegrityError, y cuando la historia vivía solo en esas 6 tenía ÉXITO y
borraba notas vigentes en silencio.

Esta ruta es nueva, se llama por su nombre, exige el id exacto y un motivo,
y borra las CATORCE tablas o ninguna.

Base temporal aislada. Nunca producción.
"""
import datetime as dt
import os
import sys
import tempfile

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)
sys.path.insert(0, os.path.join(_BACKEND, "tools"))

_TMPDIR = tempfile.mkdtemp(prefix="eo_eliminar_error_")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(
    _TMPDIR, "el.db").replace("\\", "/")
os.environ.setdefault("ENVIRONMENT", "development")
assert "sge.db" not in os.environ["DATABASE_URL"]

from database import engine, SessionLocal  # noqa: E402
import models as M  # noqa: E402

M.Base.metadata.create_all(bind=engine)

from fastapi.testclient import TestClient  # noqa: E402
import app as APP  # noqa: E402
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


def filas_de(estudiante_id):
    """Cuántas filas quedan de ese estudiante, tabla por tabla."""
    d = SessionLocal()
    try:
        fuera = {}
        for nombre in APP._MODELOS_DEL_ESTUDIANTE:
            modelo = getattr(M, nombre, None)
            if modelo is None:
                continue
            n = d.query(modelo).filter(
                modelo.estudiante_id == estudiante_id).count()
            if n:
                fuera[modelo.__tablename__] = n
        fuera['estudiantes'] = d.query(M.Estudiante).filter_by(
            id=estudiante_id).count()
        return fuera
    finally:
        d.close()


print("\n=== SETUP ===")

with client:
    SA = login('superadmin', 'superadmin123')
    for nombre, codigo, usuario, clave in (
            ('Uno', 'uno', 'dir_uno', 'admin123uno'),
            ('Dos', 'dos', 'dir_dos', 'admin123dos')):
        r = client.post('/api/superadmin/colegios', json={
            'nombre': nombre, 'codigo': codigo, 'plan': 'enterprise',
            'admin_username': usuario, 'admin_password': clave,
            'plan_secundaria': True, 'plan_primaria': True,
        }, headers=auth(SA))
        assert r.status_code in (200, 201), r.text

    DIR = login('dir_uno', 'admin123uno')
    DIR_B = login('dir_dos', 'admin123dos')

    for usuario, rol in (('sec_uno', 'secretaria'), ('prof_uno', 'profesor'),
                         ('psi_uno', 'psicologia'), ('coord_uno', 'coordinador')):
        r = client.post('/api/usuarios', json={
            'username': usuario, 'password': 'clave123456', 'nombre': rol,
            'apellido': 'T', 'email': usuario + '@t.com', 'role': rol,
        }, headers=auth(DIR))
        assert r.status_code in (200, 201), r.text
    SEC = login('sec_uno', 'clave123456')
    PROF = login('prof_uno', 'clave123456')
    PSI = login('psi_uno', 'clave123456')
    COORD = login('coord_uno', 'clave123456')

    d = SessionLocal()
    col = d.query(M.Colegio).filter_by(codigo='uno').first()
    col_b = d.query(M.Colegio).filter_by(codigo='dos').first()
    ano = d.query(M.AnoEscolar).filter_by(colegio_id=col.id, activo=True).first()
    ano_b = d.query(M.AnoEscolar).filter_by(colegio_id=col_b.id).first()
    grado = d.query(M.Grado).filter_by(colegio_id=col.id).first()
    grado_b = d.query(M.Grado).filter_by(colegio_id=col_b.id).first()
    curso = M.Curso(colegio_id=col.id, nombre='A', grado_id=grado.id,
                    ano_escolar_id=ano.id, activo=True)
    curso_b = M.Curso(colegio_id=col_b.id, nombre='A', grado_id=grado_b.id,
                      ano_escolar_id=ano_b.id, activo=True)
    asig = M.Asignatura(colegio_id=col.id, nombre='Lengua', codigo='LE',
                        area='X', activo=True)
    d.add_all([curso, curso_b, asig])
    d.flush()
    prof_row = d.query(M.Usuario).filter_by(username='prof_uno').first()

    _n = [0]

    def alumno(colegio, c, nombre, activo=False):
        _n[0] += 1
        e = M.Estudiante(colegio_id=colegio.id, matricula='EL-%03d' % _n[0],
                         nombre=nombre, apellido='T', curso_id=c.id,
                         no_lista=_n[0], activo=activo,
                         condicion='retirado' if not activo else 'activo')
        d.add(e)
        d.flush()
        return e

    # Una ficha por escenario.
    E_LIMPIA = alumno(col, curso, 'Limpia')
    E_CON_TODO = alumno(col, curso, 'ConTodo')
    E_ACTIVO = alumno(col, curso, 'Activo', activo=True)
    E_VECINO = alumno(col, curso, 'Vecino')
    E_AJENO = alumno(col_b, curso_b, 'Ajeno')
    E_ROLLBACK = alumno(col, curso, 'Rollback')

    def poblar(e):
        """Una fila en CADA una de las catorce tablas."""
        d.add(M.Asistencia(colegio_id=col.id, estudiante_id=e.id,
                           curso_id=curso.id, fecha=dt.date(2025, 9, 1),
                           estado='presente'))
        d.add(M.Calificacion(colegio_id=col.id, estudiante_id=e.id,
                             asignatura_id=asig.id, ano_escolar_id=ano.id,
                             pc1=80, cf=80))
        d.add(M.CalificacionPrimaria(
            colegio_id=col.id, estudiante_id=e.id, asignatura_id=asig.id,
            ano_escolar_id=ano.id, competencia_numero=1, p1=80))
        d.add(M.CalificacionSecundaria(
            colegio_id=col.id, estudiante_id=e.id, asignatura_id=asig.id,
            ano_escolar_id=ano.id, competencia_numero=1, p1=80))
        d.add(M.CasoPsicologia(colegio_id=col.id, estudiante_id=e.id,
                               solicitado_por=prof_row.id, motivo='x',
                               estado='abierto'))
        d.add(M.DecisionAcademicaEstudiante(
            colegio_id=col.id, estudiante_id=e.id, ano_escolar_id=ano.id,
            observacion='x'))
        d.add(M.EvalInternaEstudiante(
            colegio_id=col.id, estudiante_id=e.id, profesor_id=prof_row.id,
            asignatura_id=asig.id, curso_id=curso.id, periodo=1))
        d.add(M.EvaluacionExtraSecundaria(
            colegio_id=col.id, estudiante_id=e.id, asignatura_id=asig.id,
            ano_escolar_id=ano.id, cf_original=70.0))
        d.add(M.HistorialAcademico(
            colegio_id=col.id, estudiante_id=e.id, ano_escolar_id=ano.id,
            grado_id=grado.id, curso_id=curso.id, condicion='PROMOVIDO'))
        d.add(M.HistorialComunicacionPadres(
            colegio_id=col.id, estudiante_id=e.id, mensaje_enviado='x',
            enviado_por=prof_row.id))
        _rep = M.ReporteConducta(
            colegio_id=col.id, estudiante_id=e.id,
            reportado_por=prof_row.id, titulo='x', descripcion='x',
            estado='pendiente')
        d.add(_rep)
        d.flush()
        d.add(M.HistorialReportePadres(
            colegio_id=col.id, reporte_id=_rep.id, estudiante_id=e.id,
            enviado_por=prof_row.id, mensaje_enviado='x'))
        d.add(M.RecuperacionPedagogicaPrimaria(
            colegio_id=col.id, estudiante_id=e.id, curso_id=curso.id,
            asignatura_id=asig.id, ano_escolar_id=ano.id, periodo=1,
            aspectos_no_logrados='x', resultado='pendiente',
            registrado_por=prof_row.id))
        d.add(M.RecuperacionPrimaria(
            colegio_id=col.id, estudiante_id=e.id, asignatura_id=asig.id,
            ano_escolar_id=ano.id))
        d.flush()

    poblar(E_CON_TODO)
    poblar(E_VECINO)
    poblar(E_ROLLBACK)
    d.commit()
    IDS = {'limpia': E_LIMPIA.id, 'todo': E_CON_TODO.id, 'activo': E_ACTIVO.id,
           'vecino': E_VECINO.id, 'ajeno': E_AJENO.id,
           'rollback': E_ROLLBACK.id}
    d.close()
    print("  fichas: %s" % IDS)

    # ═══════════════════════════════════════════════════════════════════
    print("\n=== LA LISTA DE TABLAS NO SE QUEDA CORTA ===")

    import ast as _ast
    _src = open(os.path.join(_BACKEND, 'models.py'), encoding='utf-8').read()
    _con_fk = set()
    for _n2 in _ast.walk(_ast.parse(_src)):
        if not isinstance(_n2, _ast.ClassDef):
            continue
        for _it in _n2.body:
            if (isinstance(_it, _ast.Assign) and _it.targets
                    and isinstance(_it.value, _ast.Call)
                    and getattr(_it.value.func, 'id', None) == 'Column'):
                for _a in _it.value.args:
                    if (isinstance(_a, _ast.Call)
                            and getattr(_a.func, 'id', None) == 'ForeignKey'
                            and _a.args
                            and isinstance(_a.args[0], _ast.Constant)
                            and str(_a.args[0].value).startswith('estudiantes.')):
                        _con_fk.add(_n2.name)
    check('E00 la lista del borrado cubre TODAS las tablas con FK a estudiantes',
          set(APP._MODELOS_DEL_ESTUDIANTE) == _con_fk,
          'faltan: %s  sobran: %s'
          % (sorted(_con_fk - set(APP._MODELOS_DEL_ESTUDIANTE)),
             sorted(set(APP._MODELOS_DEL_ESTUDIANTE) - _con_fk)))
    check('E00b y son catorce', len(APP._MODELOS_DEL_ESTUDIANTE) == 14,
          str(len(APP._MODELOS_DEL_ESTUDIANTE)))

    # ═══════════════════════════════════════════════════════════════════
    print("\n=== E01-E04 · QUIÉN PUEDE ===")

    r = client.get('/api/estudiantes/%d/impacto-eliminacion-error' % IDS['todo'],
                   headers=auth(DIR))
    check('E01 Dirección obtiene el preview', r.status_code == 200,
          '-> %d' % r.status_code)
    if r.status_code == 200:
        j = r.json()
        check('E01b con nombre, matrícula, curso, nº y estado',
              all(k in j for k in ('nombre', 'matricula', 'curso', 'no_lista',
                                   'activo', 'condicion')), '')
        check('E01c y los conteos de las catorce tablas',
              j['total_referencias'] == 14 and len(j['conteos']) == 14,
              '%d referencias en %d tablas'
              % (j['total_referencias'], len(j['conteos'])))
        check('E01d el preview no escribió nada',
              filas_de(IDS['todo'])['estudiantes'] == 1, '')

    for et, tok, rol in (('E02', SEC, 'Secretaría'), ('E03', PROF, 'Profesor'),
                         ('E04', PSI, 'Psicología'),
                         ('E04b', COORD, 'Coordinación')):
        r = client.get('/api/estudiantes/%d/impacto-eliminacion-error'
                       % IDS['todo'], headers=auth(tok))
        check('%s %s no ve el preview' % (et, rol), r.status_code == 403,
              '-> %d' % r.status_code)
        r = client.post('/api/estudiantes/%d/eliminar-por-error' % IDS['todo'],
                        json={'confirmar_estudiante_id': IDS['todo'],
                              'motivo': 'x'}, headers=auth(tok))
        check('%s %s NO elimina' % (et, rol), r.status_code == 403,
              '-> %d' % r.status_code)

    r = client.post('/api/estudiantes/%d/eliminar-por-error' % IDS['todo'],
                    json={'confirmar_estudiante_id': IDS['todo'],
                          'motivo': 'x'})
    check('E04c sin token -> 401', r.status_code == 401, '-> %d' % r.status_code)
    check('E04d y nada de eso tocó la ficha',
          filas_de(IDS['todo'])['estudiantes'] == 1, '')

    # ═══════════════════════════════════════════════════════════════════
    print("\n=== E05-E08 · PRECONDICIONES ===")

    r = client.post('/api/estudiantes/%d/eliminar-por-error' % IDS['activo'],
                    json={'confirmar_estudiante_id': IDS['activo'],
                          'motivo': 'x'}, headers=auth(DIR))
    check('E05 un estudiante ACTIVO no se elimina',
          r.status_code == 409 and err(r) == 'ESTUDIANTE_ACTIVO_NO_ELIMINABLE',
          '-> %d %s' % (r.status_code, err(r)))

    for et, cuerpo in (
            ('E06 sin confirmación', {'motivo': 'x'}),
            ('E06b con un id distinto',
             {'confirmar_estudiante_id': IDS['vecino'], 'motivo': 'x'}),
            ('E06c con un booleano',
             {'confirmar_estudiante_id': True, 'motivo': 'x'}),
            ('E06d con una cadena vacía',
             {'confirmar_estudiante_id': '', 'motivo': 'x'})):
        r = client.post('/api/estudiantes/%d/eliminar-por-error' % IDS['todo'],
                        json=cuerpo, headers=auth(DIR))
        check(et + ' -> 409', r.status_code == 409
              and err(r) == 'CONFIRMACION_NO_COINCIDE',
              '-> %d %s' % (r.status_code, err(r)))

    for et, cuerpo in (
            ('E07 sin motivo', {'confirmar_estudiante_id': IDS['todo']}),
            ('E07b con el motivo en blanco',
             {'confirmar_estudiante_id': IDS['todo'], 'motivo': '   '})):
        r = client.post('/api/estudiantes/%d/eliminar-por-error' % IDS['todo'],
                        json=cuerpo, headers=auth(DIR))
        check(et + ' -> 400', r.status_code == 400
              and err(r) == 'MOTIVO_REQUERIDO',
              '-> %d %s' % (r.status_code, err(r)))

    r = client.post('/api/estudiantes/%d/eliminar-por-error' % IDS['ajeno'],
                    json={'confirmar_estudiante_id': IDS['ajeno'],
                          'motivo': 'x'}, headers=auth(DIR))
    check('E08 una ficha de otro colegio -> 404', r.status_code == 404,
          '-> %d' % r.status_code)
    r = client.get('/api/estudiantes/%d/impacto-eliminacion-error'
                   % IDS['ajeno'], headers=auth(DIR))
    check('E08b ni su preview', r.status_code == 404, '-> %d' % r.status_code)

    check('E08c ninguna precondición rechazada escribió nada',
          filas_de(IDS['todo'])['estudiantes'] == 1
          and len(filas_de(IDS['todo'])) == 15, str(len(filas_de(IDS['todo']))))

    # ═══════════════════════════════════════════════════════════════════
    print("\n=== E09-E15 · EL BORRADO COMPLETO ===")

    r = client.post('/api/estudiantes/%d/eliminar-por-error' % IDS['limpia'],
                    json={'confirmar_estudiante_id': IDS['limpia'],
                          'motivo': 'Ficha creada por error'},
                    headers=auth(DIR))
    check('E09 una ficha sin historia se elimina', r.status_code == 200,
          '-> %d %s' % (r.status_code, r.text[:70]))
    check('E09b y desaparece de `estudiantes`',
          filas_de(IDS['limpia'])['estudiantes'] == 0, '')

    _antes_todo = filas_de(IDS['todo'])
    r = client.post('/api/estudiantes/%d/eliminar-por-error' % IDS['todo'],
                    json={'confirmar_estudiante_id': IDS['todo'],
                          'motivo': 'Duplicado'}, headers=auth(DIR))
    check('E10 una ficha con historia completa se elimina',
          r.status_code == 200, '-> %d %s' % (r.status_code, r.text[:70]))
    _despues = filas_de(IDS['todo'])
    check('E10b no queda ni una fila en ninguna de las catorce tablas',
          all(v == 0 for v in _despues.values()),
          str({k: v for k, v in _despues.items() if v}))
    for et, tabla in (
            ('E10c asistencia', 'asistencias'),
            ('E11 calificaciones de secundaria', 'calificaciones_secundaria'),
            ('E12 calificaciones de primaria', 'calificaciones_primaria'),
            ('E13 recuperaciones y evaluación extra',
             'evaluaciones_extra_secundaria'),
            ('E14 psicología y conducta', 'casos_psicologia'),
            ('E15 historial y comunicaciones', 'historial_academico')):
        check(et + ' quedó en cero', _despues.get(tabla, 0) == 0,
              'antes había %d' % _antes_todo.get(tabla, 0))
    check('E15b y el reporte dice cuántas referencias se llevó',
          r.json().get('total_referencias') == 14,
          str(r.json().get('total_referencias')))

    # ═══════════════════════════════════════════════════════════════════
    print("\n=== E16 · ROLLBACK TOTAL ANTE UN FALLO ===")

    _antes_rb = filas_de(IDS['rollback'])
    _original = APP._MODELOS_DEL_ESTUDIANTE
    _original_impacto = APP._impacto_eliminacion

    # El fallo se induce AL FINAL del bucle de borrado: las catorce tablas
    # reales ya emitieron su DELETE cuando la decimoquinta revienta. Si la
    # transaccion no fuera atomica, quedaria media ficha.
    #
    # El conteo se sustituye porque recorre la misma lista y fallaria antes
    # de llegar a los deletes, que es justo lo que se quiere probar.
    class _Explota:
        __tablename__ = 'explota'

        @property
        def estudiante_id(self):
            raise RuntimeError('fallo inducido')

    setattr(M, '_ModeloQueExplota', _Explota)
    APP._MODELOS_DEL_ESTUDIANTE = _original + ('_ModeloQueExplota',)
    APP._impacto_eliminacion = lambda *a, **k: {}
    try:
        r = client.post('/api/estudiantes/%d/eliminar-por-error'
                        % IDS['rollback'],
                        json={'confirmar_estudiante_id': IDS['rollback'],
                              'motivo': 'prueba de rollback'},
                        headers=auth(DIR))
        check('E16 el fallo se convierte en 500, no en media eliminación',
              r.status_code == 500, '-> %d' % r.status_code)
    finally:
        APP._MODELOS_DEL_ESTUDIANTE = _original
        APP._impacto_eliminacion = _original_impacto
        delattr(M, '_ModeloQueExplota')

    _despues_rb = filas_de(IDS['rollback'])
    check('E16b ROLLBACK TOTAL: la ficha sigue entera',
          _despues_rb == _antes_rb,
          str({k: (_antes_rb.get(k), _despues_rb.get(k))
               for k in set(_antes_rb) | set(_despues_rb)
               if _antes_rb.get(k) != _despues_rb.get(k)}))
    check('E16c incluidas sus catorce tablas',
          _despues_rb['estudiantes'] == 1 and len(_despues_rb) == 15,
          '%d tablas con filas' % len(_despues_rb))

    # Y después del rollback, la operación legítima sigue funcionando.
    r = client.post('/api/estudiantes/%d/eliminar-por-error' % IDS['rollback'],
                    json={'confirmar_estudiante_id': IDS['rollback'],
                          'motivo': 'ahora sí'}, headers=auth(DIR))
    check('E16d y tras el rollback la eliminación real sigue funcionando',
          r.status_code == 200 and filas_de(IDS['rollback'])['estudiantes'] == 0,
          '-> %d' % r.status_code)

    # ═══════════════════════════════════════════════════════════════════
    print("\n=== E17-E20 · TRAZA, DESAPARICIÓN Y VECINDAD ===")

    d = SessionLocal()
    try:
        logs = d.query(M.LogAuditoria).filter_by(
            accion=APP.ACCION_ELIMINAR_ERROR).all()
        # Tres eliminaciones completadas: limpia, todo y rollback en su
        # segundo intento. El PRIMER intento de rollback no deja traza, y eso
        # es lo correcto: la auditoria se escribe dentro de la transaccion, y
        # si el borrado se deshace, la traza de un borrado que no ocurrio
        # tambien. Un log de algo que no paso es peor que ninguno.
        check('E17 cada eliminación COMPLETADA dejó su auditoría',
              len(logs) == 3, '%d registros' % len(logs))
        check('E17b el intento que hizo rollback NO dejó traza',
              len([l for l in logs if l.registro_id == IDS['rollback']]) == 1,
              '%d para la ficha del rollback'
              % len([l for l in logs if l.registro_id == IDS['rollback']]))
        _log = next((l for l in logs if l.registro_id == IDS['todo']), None)
        check('E17c con el id, el motivo y los conteos',
              _log is not None and 'Duplicado' in (_log.datos_anteriores or '')
              and 'conteos_eliminados' in (_log.datos_anteriores or ''),
              str((_log.datos_anteriores or '')[:70]))
        check('E17d y el actor que la ordenó',
              _log is not None and _log.usuario_id is not None, '')
        check('E18 el estudiante ya no está en `estudiantes`',
              d.query(M.Estudiante).filter_by(id=IDS['todo']).count() == 0, '')
        check('E19 ni en asistencia, ni en ninguna otra tabla',
              all(filas_de(IDS['todo']).values()) is False
              or sum(filas_de(IDS['todo']).values()) == 0, '')
    finally:
        d.close()

    r = client.get('/api/estudiantes/retirados', headers=auth(DIR))
    _ids_ret = {e['id'] for e in r.json()} if r.status_code == 200 else set()
    check('E18b ni aparece en la pestaña de Retirados',
          IDS['todo'] not in _ids_ret and IDS['limpia'] not in _ids_ret,
          str(sorted(_ids_ret)))
    r = client.get('/api/estudiantes', headers=auth(DIR))
    _ids_act = {e['id'] for e in r.json()} if r.status_code == 200 else set()
    check('E18c ni en el listado de activos', IDS['todo'] not in _ids_act, '')

    _vecino = filas_de(IDS['vecino'])
    check('E20 el estudiante de al lado conserva TODO',
          _vecino['estudiantes'] == 1 and len(_vecino) == 15,
          '%d tablas con filas' % len(_vecino))
    d = SessionLocal()
    try:
        check('E20b y el de otro colegio también',
              d.query(M.Estudiante).filter_by(id=IDS['ajeno']).count() == 1, '')
    finally:
        d.close()

    # ═══════════════════════════════════════════════════════════════════
    print("\n=== E21-E22 · NO SE ABRIÓ NADA MÁS ===")

    import inspect as _insp
    _rutas = [r.path for r in app.routes if hasattr(r, 'path')]
    _masivas = [p for p in _rutas
                if 'eliminar' in p and ('todos' in p or 'masivo' in p)
                and 'retirados' not in p]
    check('E21 no se creó ningún «eliminar todos» nuevo', not _masivas,
          str(_masivas))

    for et, metodo, ruta in (
            ('E22 el purgado antiguo', 'delete',
             '/api/estudiantes/retirados/%d' % IDS['vecino']),
            ('E22b y el masivo', 'delete',
             '/api/estudiantes/retirados/eliminar-todos')):
        r = client.request(metodo.upper(), ruta, headers=auth(DIR))
        check(et + ' SIGUE en 403, también para Dirección',
              r.status_code == 403, '-> %d' % r.status_code)
    check('E22c y ese 403 no tocó al vecino',
          filas_de(IDS['vecino'])['estudiantes'] == 1, '')

    # ═══════════════════════════════════════════════════════════════════
    print("\n=== FRONTEND ===")

    _FE = os.path.join(os.path.dirname(_BACKEND), 'frontend', 'src')
    _est = open(os.path.join(_FE, 'pages', 'estudiantes',
                             'EstudiantesPage.tsx'), encoding='utf-8').read()
    check('E-F1 el botón solo lo ve Dirección',
          "const canEliminarPorError = user?.role === 'direccion';" in _est
          and '{canEliminarPorError && (' in _est, '')
    check('E-F2 pide el impacto ANTES de ofrecer el borrado',
          'impacto-eliminacion-error' in _est
          and 'abrirEliminarPorError' in _est, '')
    check('E-F3 exige motivo y el id exacto para habilitar el botón',
          "confirmaId.trim() !== String(impacto.estudiante_id)" in _est
          and '!motivoError.trim()' in _est, '')
    check('E-F4 y explica que no es lo mismo que retirar',
          'fue creada por error' in _est
          and 'no se puede deshacer' in _est, '')
    check('E-F5 no hay ningún «eliminar todos» en la pantalla',
          'eliminar-todos' not in _est, '')

print()
print("=" * 98)
print("RESULTADO: %d PASARON / %d FALLARON" % (len(PASARON), len(FALLARON)))
print("=" * 98)
for f in FALLARON:
    print("  FALLA:", f)

sys.exit(1 if FALLARON else 0)
