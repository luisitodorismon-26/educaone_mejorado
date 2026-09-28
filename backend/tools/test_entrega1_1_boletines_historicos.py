# -*- coding: utf-8 -*-
"""ENTREGA-1.1 — el boletín de un año cerrado, después de promover.

EL PROBLEMA
===========
Terminada una transición A -> B, un estudiante promovido tiene `curso_id` de
B. Hasta ENTREGA-1.1 los ocho caminos de boletín resolvían el año con
`AnoEscolar.activo == True`, así que en cuanto se promovía ya no había forma
de volver a emitir el documento de A: se pedía «el boletín de Ana de
2025-2026» y salía el de 2026-2027, o no salía nada.

Y el lote era peor. Un PDF de curso filtraba por `Estudiante.curso_id ==
curso_A.id`, que después de promover devuelve exactamente a los que NO fueron
promovidos: el registro del curso perdía a la mayoría de su cohorte.

LO QUE SE PROTEGE AQUÍ
======================
Que con `ano_id` explícito TODO venga de ese año —notas, asistencia, curso,
grado y situación—, que la cohorte histórica se reconstruya sin perder a los
promovidos ni inventar miembros, y que las tres vistas del mismo estudiante
—web, PDF suelto y su página dentro del PDF del curso— coincidan.

Base temporal aislada. Nunca producción.
"""
import datetime as dt
import os
import sys
import tempfile

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)
sys.path.insert(0, os.path.join(_BACKEND, "tools"))

_TMPDIR = tempfile.mkdtemp(prefix="eo_entrega11_")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(
    _TMPDIR, "e11.db").replace("\\", "/")
os.environ.setdefault("ENVIRONMENT", "development")
assert "sge.db" not in os.environ["DATABASE_URL"]

from database import engine, SessionLocal  # noqa: E402
import models as M  # noqa: E402
import promocion_academica as PA  # noqa: E402

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


DIAS = {'ago': 10, 'sep': 21, 'oct': 22, 'nov': 20, 'dic': 14, 'ene': 20,
        'feb': 19, 'mar': 22, 'abr': 18, 'may': 21, 'jun': 8}

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

    r = client.post('/api/usuarios', json={
        'username': 'sec_uno', 'password': 'sec123456', 'nombre': 'Sec',
        'apellido': 'Uno', 'email': 's@uno.com', 'role': 'secretaria',
    }, headers=auth(DIR))
    assert r.status_code in (200, 201), r.text
    SEC = login('sec_uno', 'sec123456')

    # ── El escenario, directo en la base ────────────────────────────────
    d = SessionLocal()
    col = d.query(M.Colegio).filter_by(codigo='uno').first()
    col_b = d.query(M.Colegio).filter_by(codigo='dos').first()

    def ano(colegio, nombre, ini, fin, activo, cerrado):
        a = M.AnoEscolar(colegio_id=colegio.id, nombre=nombre, activo=activo,
                         cerrado=cerrado, fecha_inicio=ini, fecha_fin=fin,
                         p1_inicio=ini, p1_fin=ini + dt.timedelta(days=74),
                         p2_inicio=ini + dt.timedelta(days=75),
                         p2_fin=ini + dt.timedelta(days=164),
                         p3_inicio=ini + dt.timedelta(days=165),
                         p3_fin=ini + dt.timedelta(days=242),
                         p4_inicio=ini + dt.timedelta(days=243), p4_fin=fin)
        a.set_dias_trabajados(dict(DIAS))
        d.add(a)
        d.flush()
        return a

    # El año activo que creó `init_db` para este colegio estorba: aquí se
    # monta la pareja A cerrado / B activo a mano.
    for viejo in d.query(M.AnoEscolar).filter_by(colegio_id=col.id).all():
        viejo.activo = False
    A = ano(col, '2025-2026', dt.date(2025, 8, 18), dt.date(2026, 6, 12),
            False, True)
    B = ano(col, '2026-2027', dt.date(2026, 8, 17), dt.date(2027, 6, 11),
            True, False)

    def grado(colegio, nombre, nivel, orden):
        g = M.Grado(colegio_id=colegio.id, nombre=nombre, nivel=nivel,
                    orden=orden, activo=True)
        d.add(g)
        d.flush()
        return g

    def curso(colegio, g, a, nombre='A'):
        c = M.Curso(colegio_id=colegio.id, nombre=nombre, grado_id=g.id,
                    ano_escolar_id=a.id, activo=True)
        d.add(c)
        d.flush()
        return c

    G5 = grado(col, '5to Grado', 'primaria', 5)
    G6 = grado(col, '6to Grado', 'primaria', 6)
    G6S = grado(col, '6to Secundaria', 'secundaria', 12)

    CA = curso(col, G5, A)        # 5to de primaria, año A
    CA2 = curso(col, G5, A, 'B')  # otro curso de A, para el caso ambiguo
    CB = curso(col, G6, B)        # 6to de primaria, año B
    CA_SEC = curso(col, G6S, A)   # 6to de secundaria, año A

    asig = M.Asignatura(colegio_id=col.id, nombre='Lengua Española',
                        codigo='LEN', activo=True)
    d.add(asig)
    d.flush()

    def estudiante(colegio, c, matricula, no_lista=1):
        e = M.Estudiante(colegio_id=colegio.id, matricula=matricula,
                         nombre=matricula, apellido='Test', curso_id=c.id,
                         activo=True, condicion='activo', no_lista=no_lista)
        d.add(e)
        d.flush()
        return e

    def historial(e, a, c, g, condicion):
        d.add(M.HistorialAcademico(
            colegio_id=e.colegio_id, estudiante_id=e.id, ano_escolar_id=a.id,
            grado_id=g.id, curso_id=c.id, condicion=condicion))

    def notas(e, a, valor):
        for comp in (1, 2, 3):
            d.add(M.CalificacionPrimaria(
                colegio_id=e.colegio_id, estudiante_id=e.id,
                asignatura_id=asig.id, ano_escolar_id=a.id,
                competencia_numero=comp, p1=valor, p2=valor, p3=valor,
                p4=valor, final_competencia=valor))

    def marcar(e, c, a, fechas_estados):
        for delta, estado in fechas_estados:
            d.add(M.Asistencia(
                colegio_id=e.colegio_id, estudiante_id=e.id, curso_id=c.id,
                fecha=a.fecha_inicio + dt.timedelta(days=delta),
                estado=estado))

    # PROMOVIDO: cursó A en CA y ahora está físicamente en CB.
    PROM = estudiante(col, CB, 'PROM', 1)
    historial(PROM, A, CA, G5, PA.PROMOVIDO)
    notas(PROM, A, 95.0)
    notas(PROM, B, 60.0)            # notas DISTINTAS en B
    marcar(PROM, CA, A, [(i, 'presente') for i in range(5, 13)]
           + [(13, 'tardanza'), (14, 'ausente'), (15, 'excusa')])
    marcar(PROM, CB, B, [(i, 'ausente') for i in range(5, 25)])

    # APLAZADO: sigue físicamente en CA, sin historial canónico.
    APLA = estudiante(col, CA, 'APLA', 2)
    notas(APLA, A, 55.0)
    marcar(APLA, CA, A, [(i, 'presente') for i in range(5, 10)])

    # LEGACY: solo una fila legacy de A. No demuestra pertenencia.
    LEG = estudiante(col, CB, 'LEG', 3)
    historial(LEG, A, CA, G5, 'activo')
    notas(LEG, A, 80.0)

    # AMBIGUO: dos canónicos de A, en su propio curso para no contaminar.
    AMB = estudiante(col, CB, 'AMB', 2)
    historial(AMB, A, CA2, G5, PA.PROMOVIDO)
    historial(AMB, A, CA2, G5, PA.REPROBADO)
    notas(AMB, A, 70.0)

    # 6.º de Secundaria terminado: NO se mueve, se queda en A.
    SEXTO = estudiante(col, CA_SEC, 'SEXTO', 1)
    historial(SEXTO, A, CA_SEC, G6S, PA.PROMOVIDO)

    # -- El carril de SECUNDARIA: un promovido de 3.deg a 4.deg ----------
    G3S = grado(col, '3ro Secundaria', 'secundaria', 9)
    G4S = grado(col, '4to Secundaria', 'secundaria', 10)
    CA_S3 = curso(col, G3S, A)
    CB_S4 = curso(col, G4S, B)

    def notas_sec(e, a, valor):
        for comp in (1, 2, 3, 4):
            d.add(M.CalificacionSecundaria(
                colegio_id=e.colegio_id, estudiante_id=e.id,
                asignatura_id=asig.id, ano_escolar_id=a.id,
                competencia_numero=comp, p1=valor, p2=valor, p3=valor,
                p4=valor, promedio_competencia=valor))

    PROM_S = estudiante(col, CB_S4, 'PROMS', 1)
    historial(PROM_S, A, CA_S3, G3S, PA.PROMOVIDO)
    notas_sec(PROM_S, A, 92.0)
    notas_sec(PROM_S, B, 71.0)
    marcar(PROM_S, CA_S3, A, [(i, 'presente') for i in range(5, 11)]
           + [(11, 'excusa')])
    marcar(PROM_S, CB_S4, B, [(i, 'ausente') for i in range(5, 18)])

    # Colegio B, para el aislamiento.
    ano_b = d.query(M.AnoEscolar).filter_by(colegio_id=col_b.id).first()
    g_b = grado(col_b, '5to Grado', 'primaria', 5)
    c_b = curso(col_b, g_b, ano_b)
    e_b = estudiante(col_b, c_b, 'AJENO', 1)

    d.commit()
    IDS = {'A': A.id, 'B': B.id, 'CA': CA.id, 'CA2': CA2.id, 'CB': CB.id,
           'CA_S3': CA_S3.id, 'CB_S4': CB_S4.id, 'PROM_S': PROM_S.id,
           'CA_SEC': CA_SEC.id, 'PROM': PROM.id, 'APLA': APLA.id,
           'LEG': LEG.id, 'AMB': AMB.id, 'SEXTO': SEXTO.id,
           'ANO_B_TENANT': ano_b.id, 'CURSO_B_TENANT': c_b.id,
           'EST_B_TENANT': e_b.id}
    d.close()
    print("  A=%d (cerrado)  B=%d (activo)  curso A=%d  curso B=%d"
          % (IDS['A'], IDS['B'], IDS['CA'], IDS['CB']))


    def web_prim(est, ano_id=None, tok=None):
        return client.get('/api/boletines-primaria/estudiante/%d' % est,
                          params={'ano_id': ano_id} if ano_id else None,
                          headers=auth(tok or DIR))

    # ═══════════════════════════════════════════════════════════════════
    print("\n=== H1 · SIN `ano_id` NADA CAMBIA ===")

    r_sin = web_prim(IDS['APLA'])
    check('E11-H1a el boletín sin año sigue respondiendo',
          r_sin.status_code == 200, '-> %d' % r_sin.status_code)
    # APLA está en A, que NO es el activo: sin `ano_id` se resuelve como
    # siempre (el activo), así que no tiene notas ahí. Lo que importa es que
    # el comportamiento es el de antes, no que sea el deseable.
    r_con = web_prim(IDS['APLA'], IDS['A'])
    check('E11-H1b con `ano_id` de A sí trae su año',
          r_con.status_code == 200
          and r_con.json()['asistencia_anual']['dias_computados'] == 5,
          str(r_con.json().get('asistencia_anual', {}).get('dias_computados')))

    # ═══════════════════════════════════════════════════════════════════
    print("\n=== H2 · EL PROMOVIDO YA ESTÁ EN B Y SU BOLETÍN DE A ES DE A ===")

    ra = web_prim(IDS['PROM'], IDS['A'])
    rb = web_prim(IDS['PROM'], IDS['B'])
    check('E11-H2a el boletín de A se emite', ra.status_code == 200,
          '-> %d' % ra.status_code)
    check('E11-H2b y el de B también', rb.status_code == 200,
          '-> %d' % rb.status_code)

    ja, jb = ra.json(), rb.json()
    check('E11-H5 el curso del boletín de A es el de A, no el actual',
          ja['estudiante']['curso'].startswith('5to')
          and jb['estudiante']['curso'].startswith('6to'),
          'A=%s  B=%s' % (ja['estudiante']['curso'], jb['estudiante']['curso']))

    print("\n=== H3 · LAS NOTAS DE A NUNCA SON LAS DE B ===")
    check('E11-H3a el promedio de A es el de A',
          ja['promedio_general'] == 95.0, str(ja['promedio_general']))
    check('E11-H3b el de B es el de B', jb['promedio_general'] == 60.0,
          str(jb['promedio_general']))
    check('E11-H3c y no se parecen',
          ja['promedio_general'] != jb['promedio_general'], '')

    print("\n=== H4 · LA ASISTENCIA DE A NUNCA ES LA DE B ===")
    aa, ab = ja['asistencia_anual'], jb['asistencia_anual']
    check('E11-H4a en A: 8 presentes, 1 tardanza, 1 ausencia, 1 excusa',
          (aa['presentes'], aa['tardanzas'], aa['ausencias'], aa['excusas'])
          == (8, 1, 1, 1), str((aa['presentes'], aa['tardanzas'],
                                aa['ausencias'], aa['excusas'])))
    check('E11-H4b en B: 20 ausencias y ningún presente',
          (ab['presentes'], ab['ausencias']) == (0, 20),
          str((ab['presentes'], ab['ausencias'])))
    check('E11-H4c los porcentajes son distintos',
          aa['pct_asistencia'] != ab['pct_asistencia'],
          '%s vs %s' % (aa['pct_asistencia'], ab['pct_asistencia']))

    # ═══════════════════════════════════════════════════════════════════
    print("\n=== H6 · INDIVIDUAL HISTÓRICO == LOTE HISTÓRICO ===")

    import io as _io  # noqa: E402
    from pypdf import PdfReader as _PR  # noqa: E402

    r_ind = client.get('/api/boletines-primaria/estudiante/%d/pdf'
                       % IDS['PROM'], params={'ano_id': IDS['A']},
                       headers=auth(DIR))
    r_lote = client.get('/api/boletines-primaria/curso/%d/pdf' % IDS['CA'],
                        params={'ano_id': IDS['A']}, headers=auth(DIR))
    check('E11-H6a el PDF individual histórico se genera',
          r_ind.status_code == 200 and r_ind.content[:4] == b'%PDF',
          '-> %d' % r_ind.status_code)
    check('E11-H6b el PDF del curso histórico se genera',
          r_lote.status_code == 200 and r_lote.content[:4] == b'%PDF',
          '-> %d' % r_lote.status_code)

    if r_ind.status_code == 200 and r_lote.status_code == 200:
        t_ind = "".join((p.extract_text() or '')
                        for p in _PR(_io.BytesIO(r_ind.content)).pages)
        t_lote = "".join((p.extract_text() or '')
                         for p in _PR(_io.BytesIO(r_lote.content)).pages)
        _pa = aa['pct_asistencia']
        check('E11-H6c el porcentaje anual de A sale en el individual',
              ('%d%%' % round(_pa)) in t_ind, '%d%%' % round(_pa))
        check('E11-H6d y el mismo en el lote', ('%d%%' % round(_pa)) in t_lote,
              '%d%%' % round(_pa))
        check('E11-H6e el lote nombra al promovido', 'PROM' in t_lote, '')
        check('E11-H6f y también al aplazado', 'APLA' in t_lote, '')
        check('E11-H6g el grado impreso es el de A, no el de B',
              '5to' in t_ind or '5to' in t_lote, '')

    # ═══════════════════════════════════════════════════════════════════
    print("\n=== H7-H9 · QUIÉN FORMA LA COHORTE HISTÓRICA ===")

    r_coh = client.get('/api/estudiantes',
                       params={'curso_id': IDS['CA'], 'ano_id': IDS['A']},
                       headers=auth(DIR))
    ids_coh = {e['id'] for e in r_coh.json()} if r_coh.status_code == 200 else set()
    check('E11-H7 el APLAZADO, que sigue en A, entra por pertenencia actual',
          IDS['APLA'] in ids_coh, str(sorted(ids_coh)))
    check('E11-H2c el PROMOVIDO, que ya está en B, entra por su historial',
          IDS['PROM'] in ids_coh, str(sorted(ids_coh)))
    check('E11-H9 el LEGACY no entra: su fila no afirma ningún resultado',
          IDS['LEG'] not in ids_coh, str(sorted(ids_coh)))
    check('E11-H9b una fila por estudiante, sin duplicados',
          len(ids_coh) == len({e['id'] for e in r_coh.json()}), '')

    # Sin `ano_id`, la lista es la de siempre: solo quien está físicamente.
    r_hoy = client.get('/api/estudiantes', params={'curso_id': IDS['CA']},
                       headers=auth(DIR))
    ids_hoy = {e['id'] for e in r_hoy.json()}
    check('E11-H9c sin año, el comportamiento anterior intacto',
          ids_hoy == {IDS['APLA']}, str(sorted(ids_hoy)))

    print("\n=== H8 · 6.º DE SECUNDARIA TERMINADO ===")
    r_sexto = client.get('/api/estudiantes',
                         params={'curso_id': IDS['CA_SEC'], 'ano_id': IDS['A']},
                         headers=auth(DIR))
    ids_sexto = {e['id'] for e in r_sexto.json()}
    check('E11-H8a sigue en su curso de A y forma parte de la cohorte',
          IDS['SEXTO'] in ids_sexto, str(sorted(ids_sexto)))
    d = SessionLocal()
    try:
        _s = d.get(M.Estudiante, IDS['SEXTO'])
        check('E11-H8b y nada de esto le cambió la condición ni el curso',
              _s.condicion == 'activo' and _s.curso_id == IDS['CA_SEC']
              and _s.activo is True,
              '%s / curso %s' % (_s.condicion, _s.curso_id))
    finally:
        d.close()

    # ═══════════════════════════════════════════════════════════════════
    print("\n=== H10 · DOS HISTORIALES CANÓNICOS: FAIL-CLOSED ===")

    r_amb = web_prim(IDS['AMB'], IDS['A'])
    check('E11-H10a el individual se niega, no elige uno',
          r_amb.status_code == 409
          and r_amb.json().get('error') == 'HISTORIAL_AMBIGUO',
          '-> %d %s' % (r_amb.status_code, r_amb.json().get('error')))
    r_amb_l = client.get('/api/boletines-primaria/curso/%d/pdf' % IDS['CA2'],
                         params={'ano_id': IDS['A']}, headers=auth(DIR))
    check('E11-H10b y el lote de ese curso también',
          r_amb_l.status_code == 409, '-> %d' % r_amb_l.status_code)
    check('E11-H10c pero la ambigüedad de un curso no rompe el de al lado',
          client.get('/api/boletines-primaria/curso/%d/pdf' % IDS['CA'],
                     params={'ano_id': IDS['A']},
                     headers=auth(DIR)).status_code == 200, '')

    # Y un estudiante sin contexto en ese año tampoco se inventa uno.
    r_sin_ctx = web_prim(IDS['LEG'], IDS['A'])
    check('E11-H10d sin historial canónico y fuera del año: fail-closed',
          r_sin_ctx.status_code == 404
          and r_sin_ctx.json().get('error') == 'SIN_CONTEXTO_ACADEMICO',
          '-> %d %s' % (r_sin_ctx.status_code, r_sin_ctx.json().get('error')))

    # ═══════════════════════════════════════════════════════════════════
    print("\n=== H11-H12 · AISLAMIENTO ENTRE COLEGIOS ===")

    r_ano_ajeno = web_prim(IDS['PROM'], IDS['ANO_B_TENANT'])
    check('E11-H11 un `ano_id` de otro colegio da 404',
          r_ano_ajeno.status_code == 404, '-> %d' % r_ano_ajeno.status_code)
    r_ano_no = web_prim(IDS['PROM'], 999999)
    check('E11-H11b e indistinguible de uno inexistente',
          r_ano_no.status_code == 404
          and r_ano_no.text == r_ano_ajeno.text,
          '-> %d' % r_ano_no.status_code)

    r_curso_ajeno = client.get(
        '/api/boletines-primaria/curso/%d/pdf' % IDS['CURSO_B_TENANT'],
        params={'ano_id': IDS['A']}, headers=auth(DIR))
    check('E11-H12 un curso de otro colegio da 404',
          r_curso_ajeno.status_code == 404,
          '-> %d' % r_curso_ajeno.status_code)
    r_est_ajeno = web_prim(IDS['EST_B_TENANT'], IDS['A'])
    check('E11-H12b y un estudiante ajeno también',
          r_est_ajeno.status_code == 404, '-> %d' % r_est_ajeno.status_code)
    r_cursos_ajeno = client.get('/api/cursos',
                                params={'ano_id': IDS['ANO_B_TENANT']},
                                headers=auth(DIR))
    check('E11-H12c pedir cursos de un año ajeno no devuelve ninguno',
          r_cursos_ajeno.status_code == 200 and r_cursos_ajeno.json() == [],
          str(r_cursos_ajeno.json())[:60])

    # ═══════════════════════════════════════════════════════════════════
    print("\n=== H13 · SIN AÑO ACTIVO, EL HISTÓRICO SIGUE SALIENDO ===")

    d = SessionLocal()
    try:
        _b = d.get(M.AnoEscolar, IDS['B'])
        _b.activo = False
        d.commit()
    finally:
        d.close()
    r_h13 = web_prim(IDS['PROM'], IDS['A'])
    check('E11-H13a sin ningún año activo, el boletín de A se emite igual',
          r_h13.status_code == 200, '-> %d' % r_h13.status_code)
    check('E11-H13b y sigue siendo el de A',
          r_h13.status_code == 200
          and r_h13.json()['promedio_general'] == 95.0,
          str(r_h13.json().get('promedio_general')))
    r_h13_pdf = client.get('/api/boletines-primaria/curso/%d/pdf' % IDS['CA'],
                           params={'ano_id': IDS['A']}, headers=auth(DIR))
    check('E11-H13c y el lote del curso histórico también',
          r_h13_pdf.status_code == 200, '-> %d' % r_h13_pdf.status_code)
    d = SessionLocal()
    try:
        _b = d.get(M.AnoEscolar, IDS['B'])
        _b.activo = True
        d.commit()
    finally:
        d.close()

    # ═══════════════════════════════════════════════════════════════════
    print("\n=== LISTA DE CURSOS POR AÑO ===")

    ca = client.get('/api/cursos', params={'ano_id': IDS['A']},
                    headers=auth(DIR)).json()
    cb = client.get('/api/cursos', params={'ano_id': IDS['B']},
                    headers=auth(DIR)).json()
    ids_a = {c['id'] for c in ca}
    ids_b = {c['id'] for c in cb}
    check('E11-C1 los cursos de A son los de A',
          ids_a == {IDS['CA'], IDS['CA2'], IDS['CA_SEC'], IDS['CA_S3']},
          str(sorted(ids_a)))
    check('E11-C2 y no se cuela ninguno de B', not (ids_a & ids_b),
          str(sorted(ids_b)))
    check('E11-C3 cada curso declara su año',
          all(c.get('ano_escolar_id') == IDS['A'] for c in ca), '')
    todos = client.get('/api/cursos', headers=auth(DIR)).json()
    check('E11-C4 sin filtro, la lista completa de siempre',
          {c['id'] for c in todos} >= ids_a | ids_b, str(len(todos)))

    # ═══════════════════════════════════════════════════════════════════
    print("\n=== SECRETARÍA: REGISTRO OFICIAL SÍ, BORRADOR NO ===")

    for et, ruta, espera_403 in (
            ('E11-S1 registro oficial de primaria',
             '/api/registros/primaria/%d' % IDS['CA'], False),
            ('E11-S2 registro oficial de secundaria',
             '/api/registros/secundaria/%d' % IDS['CA_SEC'], False),
            ('E11-S3 borrador de primaria',
             '/api/registros/primaria/%d/preview-pdf' % IDS['CA'], True),
            ('E11-S4 borrador de secundaria',
             '/api/registros/secundaria/%d/preview-pdf' % IDS['CA_SEC'], True)):
        r_s = client.get(ruta, headers=auth(SEC))
        r_d = client.get(ruta, headers=auth(DIR))
        if espera_403:
            check(et + ': cerrado a secretaría', r_s.status_code == 403,
                  '-> %d' % r_s.status_code)
            check(et + ': y abierto a dirección', r_d.status_code != 403,
                  '-> %d' % r_d.status_code)
        else:
            # La prueba de fondo: secretaría recibe EXACTAMENTE lo mismo que
            # dirección. Si el registro está incompleto las dos ven el mismo
            # bloqueo de integridad; si está completo, las dos el mismo PDF.
            check(et + ': secretaría recibe lo mismo que dirección',
                  r_s.status_code == r_d.status_code
                  and r_s.status_code != 403,
                  'sec=%d dir=%d' % (r_s.status_code, r_d.status_code))

    r_dias = client.post('/api/registros/dias-trabajados/%d' % IDS['A'],
                         json={'dias': {}}, headers=auth(SEC))
    check('E11-S5 pero no puede declarar días trabajados',
          r_dias.status_code == 403, '-> %d' % r_dias.status_code)
    r_prev = client.get('/api/registros/preview/%d' % IDS['CA'],
                        headers=auth(SEC))
    check('E11-S6 y sigue viendo la vista estructurada',
          r_prev.status_code == 200, '-> %d' % r_prev.status_code)

    # Secretaría emite el boletín histórico, que es el objetivo del parche.
    r_sec_hist = web_prim(IDS['PROM'], IDS['A'], tok=SEC)
    check('E11-S7 secretaría emite el boletín histórico',
          r_sec_hist.status_code == 200
          and r_sec_hist.json()['promedio_general'] == 95.0,
          '-> %d' % r_sec_hist.status_code)

    # ═══════════════════════════════════════════════════════════════════
    print("\n=== SECUNDARIA: MINERD Y BOLETIN DE PADRES, HISTORICOS ===")

    rs_a = client.get('/api/boletines/estudiante/%d' % IDS['PROM_S'],
                      params={'ano_id': IDS['A']}, headers=auth(DIR))
    rs_b = client.get('/api/boletines/estudiante/%d' % IDS['PROM_S'],
                      params={'ano_id': IDS['B']}, headers=auth(DIR))
    check('E11-SEC1 la vista web de A y la de B se emiten',
          rs_a.status_code == 200 and rs_b.status_code == 200,
          '%d / %d' % (rs_a.status_code, rs_b.status_code))
    ja_s, jb_s = rs_a.json(), rs_b.json()
    check('E11-SEC2 el grado de A es 3ro, no el 4to en el que esta ahora',
          (ja_s['estudiante']['grado'] or '').startswith('3ro')
          and (jb_s['estudiante']['grado'] or '').startswith('4to'),
          'A=%s B=%s' % (ja_s['estudiante']['grado'],
                         jb_s['estudiante']['grado']))
    check('E11-SEC3 las notas de A no son las de B',
          ja_s['promedio_general'] != jb_s['promedio_general'],
          '%s vs %s' % (ja_s['promedio_general'], jb_s['promedio_general']))
    check('E11-SEC4 la asistencia de A no es la de B',
          ja_s['asistencia_anual']['excusas'] == 1
          and jb_s['asistencia_anual']['ausencias'] == 13,
          'A excusas=%s  B ausencias=%s'
          % (ja_s['asistencia_anual']['excusas'],
             jb_s['asistencia_anual']['ausencias']))

    PDFS = [
        ('E11-SEC5 MINERD individual',
         '/api/boletines/estudiante/%d/pdf-minerd-v2' % IDS['PROM_S']),
        ('E11-SEC6 MINERD del curso',
         '/api/boletines/curso/%d/pdf-minerd-v2' % IDS['CA_S3']),
        ('E11-SEC7 padres individual',
         '/api/boletines/estudiante/%d/pdf' % IDS['PROM_S']),
        ('E11-SEC8 padres del curso',
         '/api/boletines/curso/%d/pdf' % IDS['CA_S3']),
    ]
    textos = {}
    for et, ruta in PDFS:
        r_p = client.get(ruta, params={'ano_id': IDS['A']}, headers=auth(DIR))
        ok = r_p.status_code == 200 and r_p.content[:4] == b'%PDF'
        check(et + ' se genera para el ano A', ok, '-> %d' % r_p.status_code)
        if ok:
            textos[et] = "".join(
                (p.extract_text() or '')
                for p in _PR(_io.BytesIO(r_p.content)).pages)

    _pa_s = ja_s['asistencia_anual']['pct_asistencia']
    _exc = 'Excusas: %d' % ja_s['asistencia_anual']['excusas']
    if len(textos) == 4:
        check('E11-SEC9 el MINERD individual y el del curso dicen lo mismo',
              _exc in textos['E11-SEC5 MINERD individual']
              and _exc in textos['E11-SEC6 MINERD del curso'], _exc)
        check('E11-SEC10 y el lote incluye al promovido que ya esta en B',
              'PROMS' in textos['E11-SEC6 MINERD del curso'], '')
        check('E11-SEC11 el de padres lleva el mismo porcentaje de A',
              ('%.1f%%' % _pa_s) in textos['E11-SEC7 padres individual']
              and ('%.1f%%' % _pa_s) in textos['E11-SEC8 padres del curso'],
              '%.1f%%' % _pa_s)

    print("\n=== EL FRONTEND MANDA EL ANO EN TODAS PARTES ===")

    _FE = os.path.join(os.path.dirname(_BACKEND), 'frontend', 'src')
    _bol = open(os.path.join(_FE, 'pages', 'boletines', 'BoletinesPage.tsx'),
                encoding='utf-8').read()

    check('E11-FE1 hay selector de ano escolar',
          "label=\"Ano escolar\"".replace('Ano', 'A' + chr(0xF1) + 'o') in _bol
          and 'elegirAno' in _bol, '')
    check('E11-FE2 los cursos se piden POR ano',
          "api.get('/cursos', anoInicial" in _bol
          and "params: { ano_id: nuevo }" in _bol, '')
    check('E11-FE3 los estudiantes tambien',
          "{ curso_id: cursoId, ano_id: anoId }" in _bol, '')
    check('E11-FE4 los dos boletines web llevan el ano',
          _bol.count("params: { ano_id: anoId }") >= 2, '')

    # La parte que importa: NINGUNA descarga puede quedarse sin ano. Se
    # centraliza en `descargarPDF`, asi que no hace falta recordarlo seis
    # veces; y esto comprueba que sigue siendo asi.
    _ini = _bol.index('const descargarPDF')
    _cuerpo = _bol[_ini:_bol.index(chr(10) + '  };', _ini)]
    check('E11-FE5 descargarPDF anade el ano por su cuenta',
          'ano_id=${anoId}' in _cuerpo, '')
    check('E11-FE6 y es la unica puerta: ningun boton arma su propia URL con ano',
          'ano_id=' not in _bol.replace(_cuerpo, ''), '')

    # Al cambiar de ano se limpia lo que colgaba del anterior.
    _ie = _bol.index('const elegirAno')
    _ce = _bol[_ie:_bol.index(chr(10) + '  };', _ie)]
    for _set in ('setCursoId(null)', 'setEstudianteId(null)',
                 'setEstudiantes([])', 'setBoletin(null)',
                 'setBoletinPrim(null)'):
        check('E11-FE7 cambiar de ano limpia %s' % _set, _set in _ce, '')

    _reg = open(os.path.join(_FE, 'pages', 'registro-escolar',
                             'RegistroEscolarPage.tsx'), encoding='utf-8').read()
    _lp = [l for l in _reg.splitlines() if 'const canPreview' in l][0]
    _lg = [l for l in _reg.splitlines() if 'const canGenerate' in l][0]
    check('E11-FE8 el borrador no se le ofrece a secretaria',
          "'secretaria'" not in _lp, '')
    check('E11-FE9 el oficial si', "'secretaria'" in _lg, '')

    print("\n=== LO QUE NO SE TOCÓ ===")

    import app as APP  # noqa: E402
    import inspect  # noqa: E402

    check('E11-Z1 los candados de Cierre, en su estado de release',
          APP.CIERRE_ANO_BLOQUEADO is False
          and APP.PROMOCION_LEGACY_BLOQUEADA is True,
          'ENTREGA-1 no los movio')
    for fn in ('_dias_asistencia_del_ano', '_dias_asistencia_de_filas',
               '_resumen_anual_asistencia', '_asistencia_anual_boletin'):
        check('E11-Z2 %s sigue existiendo, sin duplicar' % fn,
              callable(getattr(APP, fn, None)), '')
    check('E11-Z3 el boletín histórico usa ESOS helpers, no otra fórmula',
          '_asistencia_anual_boletin' in inspect.getsource(
              APP.boletin_primaria_estudiante_json), '')
    check('E11-Z4 el contexto histórico exige condición canónica',
          'CONDICIONES_DEFINITIVAS' in inspect.getsource(
              APP._historial_canonico_de), '')
    check('E11-Z5 y nunca elige entre dos: no hay `.first()` arbitrario',
          '.first()' not in inspect.getsource(APP._historial_canonico_de), '')

    d = SessionLocal()
    try:
        check('E11-Z6 ZERO DATA LOSS: el historial no se tocó',
              d.query(M.HistorialAcademico).count() == 6,
              str(d.query(M.HistorialAcademico).count()))
        check('E11-Z7 ni las condiciones de los estudiantes',
              {e.condicion for e in d.query(M.Estudiante).all()} == {'activo'},
              '')
    finally:
        d.close()

print()
print("=" * 96)
print("RESULTADO: %d PASARON / %d FALLARON" % (len(PASARON), len(FALLARON)))
print("=" * 96)
for f in FALLARON:
    print("  FALLA:", f)

sys.exit(1 if FALLARON else 0)
