# -*- coding: utf-8 -*-
"""REG-SH · Registro oficial con asignaturas SIN horario en el sistema.

En algunos centros el docente de ciertas materias maneja su horario aparte. Esa
falta de configuración ya no impide imprimir el Registro: es un AVISO (no pide
`?force=true`), y el generador imprime solo las marcas reales en sus fechas,
sin inventar sesiones, ausencias ni porcentajes.

Datos SINTÉTICOS (semilla de REG-43: notas completas, un día de horario por
asignatura y asistencia en todas sus fechas) en una base SQLite aislada.

  Curso B · horarios MIXTOS: Educación Artística y FIHR sin horario; el resto
            con horario. Con vacaciones (rango), feriado, «No hubo clase»,
            un retiro y un traslado de entrada.
  Curso A · TODOS sus horarios: debe seguir igual (sin avisos, porcentajes
            como siempre). La comparación byte a byte del texto con `main`
            la hace el script de auditoría con `instantanea()`.

  V  validador: aviso y no error; demás validaciones intactas
  M  matriz del Registro: columnas = fechas con marca real; sin porcentaje
  P  PDF oficial: se emite sin force; % solo donde hay horario
  A  curso completo: igual que siempre
  R  vacaciones, feriado, «No hubo clase», retiro y traslado respetados

Uso (desde backend/):  python tools/test_registro_sin_horario.py [dir_pdfs]
"""
import datetime as dt
import os
import sys

BK = os.environ.get('EO_BACKEND_DIR') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(BK, 'tools'))
from test_utils import aislar_base_de_datos, verificar_engine_aislado  # noqa: E402

TMP = aislar_base_de_datos('registro_sin_horario')
from database import engine, SessionLocal  # noqa: E402
verificar_engine_aislado(engine, TMP)
import models as M  # noqa: E402
import app as APP  # noqa: E402
import registro_escolar as RE  # noqa: E402
import registro_validator as RV  # noqa: E402
from registro_asistencia import build_asistencia_registro  # noqa: E402
import registro_43_semilla as S  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from auth import create_token  # noqa: E402

D = dt.date
SIN_HORARIO = ('Educación Artística', 'Formación Integral Humana y Religiosa')
VAC = (D(2026, 3, 30), D(2026, 4, 3))          # vacaciones (rango)
FERIADO = D(2026, 2, 27)
RETIRO = D(2026, 4, 20)
TRASLADO = D(2026, 2, 2)
S1_MAT = D(2026, 1, 15)                         # jueves: Matemática (con horario)
S1_EA = D(2026, 1, 13)                          # martes: Ed. Artística (sin horario)
EXTRA_EA = (D(2025, 10, 9), D(2026, 5, 7))      # jueves: EA también se dio fuera de su día habitual
PAG = {'Educación Artística': 47, 'Educación Física': 50, 'Formación Integral Humana y Religiosa': 53}


def preparar():
    """Siembra y aplica los cambios de los cursos. Devuelve el contexto."""
    M.Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    sem = S.sembrar(db, M, [(1, 'A', 12), (1, 'B', 12), (1, 'C', 12)], codigo='RSH')
    col, A, B, C = sem['colegio'], sem['cursos']['A'], sem['cursos']['B'], sem['cursos']['C']
    asig = {a.nombre: a for a in sem['asignaturas']}
    c = TestClient(APP.app)
    H = {'Authorization': 'Bearer ' + create_token(sem['director'])}

    def marcas(**f):
        return db.query(M.Asistencia).filter_by(**f)

    # Curso B: sin horario en el sistema para EA y FIHR (su docente lo maneja aparte).
    for nom in SIN_HORARIO:
        db.query(M.Horario).filter_by(curso_id=B.id, asignatura_id=asig[nom].id).delete()
    # EA se dio además dos jueves (fuera de su martes habitual): marcas reales.
    ests_b = db.query(M.Estudiante).filter_by(curso_id=B.id).all()
    prof_ea = db.query(M.AsignacionProfesor).filter_by(curso_id=B.id, asignatura_id=asig['Educación Artística'].id).one().profesor_id
    for f in EXTRA_EA:
        for e in ests_b:
            db.add(M.Asistencia(colegio_id=col.id, estudiante_id=e.id, curso_id=B.id,
                                asignatura_id=asig['Educación Artística'].id, fecha=f,
                                estado=S.estado(e.no_lista, f), registrado_por=prof_ea))
    db.flush()
    # Vacaciones y feriado: ese día no hubo clase en el centro (no hay marcas).
    q = db.query(M.Asistencia).filter(M.Asistencia.fecha >= VAC[0], M.Asistencia.fecha <= VAC[1])
    q.delete(synchronize_session=False)
    db.query(M.Asistencia).filter(M.Asistencia.fecha == FERIADO).delete(synchronize_session=False)
    db.add(M.DiaNoLaborable(colegio_id=col.id, fecha=FERIADO, nombre='Independencia', tipo='feriado',
                            recurrente=False, ano_escolar_id=sem['ano'].id, activo=True))
    # «No hubo clase» en B: Matemática (con horario) y Ed. Artística (sin horario:
    # se declaró cuando aún tenía horario y se conserva).
    for f, nom in ((S1_MAT, 'Matemática'), (S1_EA, 'Educación Artística')):
        marcas(curso_id=B.id, asignatura_id=asig[nom].id, fecha=f).delete(synchronize_session=False)
        pid = db.query(M.AsignacionProfesor).filter_by(curso_id=B.id, asignatura_id=asig[nom].id).one().profesor_id
        db.add(M.SesionNoImpartida(colegio_id=col.id, fecha=f, curso_id=B.id, asignatura_id=asig[nom].id,
                                   profesor_id=pid, dia_semana_snapshot=S.DIAS[f.weekday()],
                                   motivo_codigo='SUSP_CURSO', registrado_por=pid, activo=True))
    # Retiro en B (no_lista 2): sus marcas después del retiro no existen.
    ret = next(e for e in ests_b if e.no_lista == 2)
    db.query(M.Asistencia).filter(M.Asistencia.estudiante_id == ret.id, M.Asistencia.fecha >= RETIRO).delete(
        synchronize_session=False)
    # Traslado de C (no_lista 3) a B: en C deja de tener marcas desde el traslado
    # y en B tiene las de las mismas clases que el resto de B desde ese día.
    tra = next(e for e in db.query(M.Estudiante).filter_by(curso_id=C.id).all() if e.no_lista == 3)
    db.query(M.Asistencia).filter(M.Asistencia.estudiante_id == tra.id, M.Asistencia.fecha >= TRASLADO).delete(
        synchronize_session=False)
    ref = next(e for e in ests_b if e.no_lista == 1)
    for m in db.query(M.Asistencia).filter(M.Asistencia.estudiante_id == ref.id, M.Asistencia.fecha >= TRASLADO).all():
        db.add(M.Asistencia(colegio_id=col.id, estudiante_id=tra.id, curso_id=B.id, asignatura_id=m.asignatura_id,
                            fecha=m.fecha, estado=S.estado(3, m.fecha), registrado_por=m.registrado_por))
    db.commit()
    st_v = c.post('/api/vacaciones', headers=H, json={'nombre': 'Semana Santa', 'fecha_inicio': VAC[0].isoformat(),
                                                       'fecha_fin': VAC[1].isoformat()})
    st_r = c.post('/api/estudiantes/%d/retiro' % ret.id, headers=H, json={'desde': RETIRO.isoformat(), 'motivo': 'sintético'})
    st_t = c.post('/api/estudiantes/%d/traslado' % tra.id, headers=H,
                  json={'curso_destino_id': B.id, 'desde': TRASLADO.isoformat(), 'no_lista': 30})
    db.expire_all()
    return dict(db=db, c=c, H=H, col=col, A=A, B=B, C=C, asig=asig, ret=ret, tra=tra,
                movimientos=(st_v.status_code, st_r.status_code, st_t.status_code),
                movimientos_js=(st_v.json(), st_r.json(), st_t.json()))


def instantanea(ctx, curso):
    """Lo que debe quedar igual en un curso con todos sus horarios: validación,
    matrices de asistencia de las 9 asignaturas y texto de cada página del PDF."""
    import pymupdf
    db = ctx['db']
    v = RV.validar_registro_secundaria(db, curso.id, ctx['col'].id).to_dict()
    v.pop('avisos', None)
    mats = {}
    for nom, a in sorted(ctx['asig'].items()):
        mats[nom] = [{k: m[k] for k in ('clave', 'dias', 'total_dias', 'dias_computables', 'no_impartidas', 'filas')}
                     for m in build_asistencia_registro(db, curso.id, asignatura_id=a.id)]
    r = ctx['c'].get('/api/registros/secundaria/%d' % curso.id, headers=ctx['H'])
    texto = None
    if r.status_code == 200:
        doc = pymupdf.open(stream=r.content, filetype='pdf')
        texto = [p.get_text() for p in doc]
    return {'validacion': v, 'matrices': mats, 'pdf_status': r.status_code, 'pdf_texto': texto,
            'pdf': r.content if r.status_code == 200 else None}


def numeros_en_columna(pdf_bytes, pagina, campo):
    """Números impresos en la columna `campo` ('porcentaje_x' o 'total_x') de una
    página compacta de asistencia (47-55)."""
    import pymupdf
    doc = pymupdf.open(stream=pdf_bytes, filetype='pdf')
    p = doc[pagina - 1]
    xs = [b[campo] for b in RE._asistencia_4meses_bloques(pagina)]
    out = []
    for w in p.get_text('words'):
        cx = (w[0] + w[2]) / 2
        if w[4].isdigit() and any(abs(cx - x) < 3.5 for x in xs) and w[1] > 150:
            out.append(int(w[4]))
    return out


if __name__ == '__main__':
    SALIDA = sys.argv[1] if len(sys.argv) > 1 else None
    RES = []

    def check(nombre, ok, detalle=''):
        RES.append((nombre, bool(ok)))
        print(('  PASA  ' if ok else '  FALLA ') + nombre + ('' if ok else '  -> ' + str(detalle)[:500]))

    ctx = preparar()
    db, c, H, A, B, asig = ctx['db'], ctx['c'], ctx['H'], ctx['A'], ctx['B'], ctx['asig']
    print('Preparación (vacaciones, retiro, traslado):', ctx['movimientos'])
    check('R0 preparación: vacaciones 201, retiro 200 y traslado 200 por la API',
          ctx['movimientos'] == (201, 200, 200), ctx['movimientos_js'])

    # ═════════════ V. Validador ═════════════
    print('\n== V. Validador ==')
    vb = RV.validar_registro_secundaria(db, B.id, ctx['col'].id)
    check('V curso mixto: válido, sin errores ni advertencias que pidan confirmación',
          vb.is_valid and not vb.errors and not vb.warnings, (vb.errors, vb.warnings))
    check('V un aviso por asignatura sin horario, con la limitación explícita',
          len(vb.avisos) == 2 and all('no tiene horario configurado' in x and 'no puede determinar los días de clase'
                                      in x and 'porcentaje de asistencia queda sin calcular' in x for x in vb.avisos)
          and sorted(vb.info['asignaturas_sin_horario']) == sorted(SIN_HORARIO), vb.avisos)
    va = RV.validar_registro_secundaria(db, A.id, ctx['col'].id)
    check('V curso completo: válido, sin avisos', va.is_valid and not va.avisos and not va.warnings,
          (va.errors, va.warnings, va.avisos))
    # Las demás validaciones siguen bloqueando: falta una nota en una asignatura SIN horario.
    fila = db.query(M.CalificacionSecundaria).filter_by(asignatura_id=asig['Educación Artística'].id,
                                                        estudiante_id=ctx['tra'].id, competencia_numero=1).one()
    p4 = fila.p4
    fila.p4 = None
    db.commit()
    vbx = RV.validar_registro_secundaria(db, B.id, ctx['col'].id)
    r = c.get('/api/registros/secundaria/%d' % B.id, headers=H)
    check('V las demás validaciones siguen bloqueando (nota incompleta -> error y 400)',
          not vbx.is_valid and any('Educación Artística' in e for e in vbx.errors) and r.status_code == 400,
          (vbx.errors, r.status_code))
    fila.p4 = p4
    db.commit()
    # Cobertura: un hueco real (una marca borrada en un día con lista de los demás) sigue siendo error.
    sigue = next(e for e in db.query(M.Estudiante).filter_by(curso_id=B.id).all() if e.no_lista == 1)
    otro = db.query(M.Asistencia).filter_by(curso_id=B.id, asignatura_id=asig['Educación Artística'].id,
                                            fecha=EXTRA_EA[0], estudiante_id=sigue.id).one()
    est_hueco, estado_hueco, reg_por = otro.estudiante_id, otro.estado, otro.registrado_por
    db.delete(otro)
    db.commit()
    vbx = RV.validar_registro_secundaria(db, B.id, ctx['col'].id)
    check('V sin horario, un día con lista de otros pero sin la de un estudiante sigue siendo «asistencia incompleta»',
          not vbx.is_valid and any('Asistencia incompleta' in e and 'Educación Artística' in e for e in vbx.errors),
          vbx.errors)
    db.add(M.Asistencia(colegio_id=ctx['col'].id, estudiante_id=est_hueco, curso_id=B.id,
                        asignatura_id=asig['Educación Artística'].id, fecha=EXTRA_EA[0], estado=estado_hueco,
                        registrado_por=reg_por))
    db.commit()
    db.expire_all()
    check('V restaurada la marca, vuelve a ser válido', RV.validar_registro_secundaria(db, B.id, ctx['col'].id).is_valid)

    # ═════════════ M. Matriz ═════════════
    print('\n== M. Matriz del Registro (asignatura sin horario) ==')
    # Como el Registro real: con los miembros del curso y sus ventanas de permanencia.
    miembros, ventanas, _hay = RV._permanencia_registro(db, B, ctx['col'].id)
    ests_reg = [m.estudiante for m in miembros]
    for nom in SIN_HORARIO:
        a = asig[nom]
        mat = build_asistencia_registro(db, B.id, asignatura_id=a.id, estudiantes=ests_reg, ventanas_por_est=ventanas)
        fechas_bd = {f for (f,) in db.query(M.Asistencia.fecha).filter_by(curso_id=B.id, asignatura_id=a.id).distinct()}
        s1 = {S1_EA} if nom == 'Educación Artística' else set()
        cols = {D(m['anio'], m['mes_num'], d) for m in mat for d in m['dias']}
        check('M %s: columnas = fechas con marca real (+ «No hubo clase»), ninguna inventada' % nom,
              cols == fechas_bd | s1, (sorted(cols - fechas_bd - s1), sorted(fechas_bd - cols)))
        check('M %s: ningún porcentaje y «asistencia esperada no determinada»' % nom,
              all(f['porcentaje'] is None for m in mat for f in m['filas'])
              and all(m['asistencia_esperada_determinada'] is False for m in mat))
        p_bd = db.query(M.Asistencia).filter_by(curso_id=B.id, asignatura_id=a.id, estado='presente').count()
        p_mat = sum(f['presentes'] for m in mat for f in m['filas'])
        check('M %s: los presentes impresos son exactamente los de la base (%d)' % (nom, p_bd), p_bd == p_mat, (p_bd, p_mat))
        check('M %s: ninguna columna en vacaciones ni en el feriado' % nom,
              not any(VAC[0] <= f <= VAC[1] or f == FERIADO for f in cols))
    mat_ef = build_asistencia_registro(db, B.id, asignatura_id=asig['Educación Física'].id)
    check('M Ed. Física (con horario) en el mismo curso: porcentajes como siempre',
          any(f['porcentaje'] is not None for m in mat_ef for f in m['filas'])
          and all(m['asistencia_esperada_determinada'] for m in mat_ef))

    # ═════════════ R. Calendario y movimientos ═════════════
    print('\n== R. Vacaciones, feriado, «No hubo clase», retiro y traslado ==')
    mat_ea = build_asistencia_registro(db, B.id, asignatura_id=asig['Educación Artística'].id)
    ene = next(m for m in mat_ea if m['clave'] == '2026-01')
    check('R «No hubo clase» de Ed. Artística (sin horario) conserva su columna y su motivo',
          13 in ene['dias'] and 13 in ene['no_impartidas'])
    mat_mat = build_asistencia_registro(db, B.id, asignatura_id=asig['Matemática'].id)
    ene_m = next(m for m in mat_mat if m['clave'] == '2026-01')
    check('R «No hubo clase» de Matemática (con horario) igual que siempre', 15 in ene_m['dias'] and 15 in ene_m['no_impartidas'])
    cols_mat = {D(m['anio'], m['mes_num'], d) for m in mat_mat for d in m['dias']}
    check('R con horario: vacaciones y feriado fuera de los días esperados',
          not any(VAC[0] <= f <= VAC[1] or f == FERIADO for f in cols_mat))

    def celdas(mat, est_id, cond):
        out = []
        for m in mat:
            fila = next((f for f in m['filas'] if f['estudiante_id'] == est_id), None)
            for d, v in zip(m['dias'], fila['valores'] if fila else []):
                if cond(D(m['anio'], m['mes_num'], d)):
                    out.append(v)
        return out

    for nom in ('Educación Artística', 'Matemática'):
        mat = build_asistencia_registro(db, B.id, asignatura_id=asig[nom].id, estudiantes=ests_reg,
                                        ventanas_por_est=ventanas)
        tras = celdas(mat, ctx['ret'].id, lambda f: f > RETIRO)
        check('R %s: retirado, después del retiro sus celdas son «-» (no aplican)' % nom,
              tras and set(tras) == {'-'}, tras[:10])
        antes = celdas(mat, ctx['tra'].id, lambda f: f < TRASLADO)
        despues = celdas(mat, ctx['tra'].id, lambda f: f >= TRASLADO)
        check('R %s: trasladado, antes de llegar «-»; desde el traslado, sus marcas reales' % nom,
              antes and set(antes) == {'-'} and despues and '-' not in despues and '' not in
              [v for v in despues], (antes[:5], despues[:8]))

    # ═════════════ P. PDF oficial ═════════════
    print('\n== P. PDF oficial ==')
    rb = c.get('/api/registros/secundaria/%d' % B.id, headers=H)
    check('P curso mixto: el Registro oficial se emite SIN ?force (200, PDF)',
          rb.status_code == 200 and rb.content[:4] == b'%PDF', rb.status_code)
    if rb.status_code == 200:
        for nom in SIN_HORARIO:
            pg = PAG[nom]
            pct, tot = numeros_en_columna(rb.content, pg, 'porcentaje_x'), numeros_en_columna(rb.content, pg, 'total_x')
            check('P pág. %d (%s, sin horario): marcas y totales impresos, ningún porcentaje' % (pg, nom),
                  tot and not pct, (tot[:5], pct[:5]))
        pct_ef = numeros_en_columna(rb.content, PAG['Educación Física'], 'porcentaje_x')
        check('P pág. 50 (Ed. Física, con horario) del mismo curso: porcentajes impresos', pct_ef, pct_ef)
    ra = c.get('/api/registros/secundaria/%d' % A.id, headers=H)
    check('P curso completo: 200 sin force', ra.status_code == 200 and ra.content[:4] == b'%PDF', ra.status_code)
    if ra.status_code == 200:
        check('P curso completo, pág. 47 (Ed. Artística con horario): porcentajes impresos',
              numeros_en_columna(ra.content, 47, 'porcentaje_x'))
    rv = c.get('/api/registros/preview/%d' % B.id, headers=H)
    check('P la vista previa de la pantalla trae los avisos', rv.status_code == 200
          and len((rv.json().get('validacion') or {}).get('avisos') or []) == 2, rv.json().get('validacion'))
    if SALIDA:
        os.makedirs(SALIDA, exist_ok=True)
        for nombre, r_ in (('registro_oficial_B_horarios_mixtos.pdf', rb), ('registro_oficial_A_todos_los_horarios.pdf', ra)):
            if r_.status_code == 200:
                open(os.path.join(SALIDA, nombre), 'wb').write(r_.content)

    # ═════════════ A. Curso completo ═════════════
    print('\n== A. Curso con todos sus horarios ==')
    for nom, a in sorted(asig.items()):
        mat = build_asistencia_registro(db, A.id, asignatura_id=a.id)
        ok = all(m['asistencia_esperada_determinada'] for m in mat) and any(
            f['porcentaje'] is not None for m in mat for f in m['filas'])
        check('A %s: días esperados por horario y porcentajes como siempre' % nom, ok)

    print('\nRESULTADO REG-SH REGISTRO SIN HORARIO: %d PASARON / %d FALLARON'
          % (sum(1 for _, ok in RES if ok), sum(1 for _, ok in RES if not ok)))
    db.close()
    sys.exit(0 if all(ok for _, ok in RES) else 1)
