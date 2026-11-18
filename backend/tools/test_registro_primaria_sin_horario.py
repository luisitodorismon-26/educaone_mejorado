# -*- coding: utf-8 -*-
"""REG-SH · Registro oficial de PRIMARIA sin horario configurado, de punta a punta.

Datos SINTÉTICOS en una base SQLite aislada: 3ro de Primaria, año 2025-2026 ya
terminado, titular con dos áreas (C1-C3 en P1-P4) y NINGÚN horario del curso.
La asistencia de Primaria es diaria (sin asignatura).

  Curso A · el titular pasó lista solo lunes y miércoles.
  Curso B · el titular pasó lista todos los días hábiles (sin vacaciones).

  E  endpoint oficial: imprime sin ?force; el aviso viaja en la vista previa
  M  hoja mensual del PDF: solo las fechas con marca real, las marcas tal cual
     y los conteos de la base; ningún día ni ausencia inventados
  P  porcentajes: ninguno mensual; el anual del Acta solo con cobertura completa
     según el calendario del centro (ver nota en el informe)

Uso (desde backend/):  python tools/test_registro_primaria_sin_horario.py [dir_pdfs]
"""
import datetime as dt
import hashlib
import os
import sys

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(BK, 'tools'))
from test_utils import aislar_base_de_datos, verificar_engine_aislado  # noqa: E402

TMP = aislar_base_de_datos('registro_primaria_sin_horario')
from database import engine, SessionLocal  # noqa: E402
verificar_engine_aislado(engine, TMP)
import models as M  # noqa: E402
import app as APP  # noqa: E402
import registro_primaria as RP  # noqa: E402
import registro_validator as RV  # noqa: E402
from registro_asistencia import build_asistencia_registro  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from auth import create_token  # noqa: E402
import pymupdf  # noqa: E402

D = dt.date
INICIO, FIN = D(2025, 9, 1), D(2026, 6, 19)
SALIDA = sys.argv[1] if len(sys.argv) > 1 else None
RES = []


def check(nombre, ok, detalle=''):
    RES.append((nombre, bool(ok)))
    print(('  PASA  ' if ok else '  FALLA ') + nombre + ('' if ok else '  -> ' + str(detalle)[:500]))


def estado(nl, f):
    r = int(hashlib.md5(('%d|%s' % (nl, f.isoformat())).encode()).hexdigest(), 16) % 7
    return 'ausente' if r == 0 else ('tardanza' if r == 3 else 'presente')


M.Base.metadata.create_all(bind=engine)
db = SessionLocal()


def add(o):
    db.add(o)
    db.flush()
    return o


col = add(M.Colegio(nombre='Colegio Sintetico RSHP', codigo='RSHP', activo=True))
add(M.ConfiguracionColegio(colegio_id=col.id, nombre=col.nombre, regional='10', distrito='10-01',
                           codigo_centro='99998', director='Directora Sintetica'))
ano = add(M.AnoEscolar(colegio_id=col.id, nombre='2025-2026', activo=True, cerrado=False,
                       fecha_inicio=INICIO, fecha_fin=FIN))
grado = add(M.Grado(colegio_id=col.id, nombre='3ro Primaria', nivel='primaria', orden=3, activo=True))
dire = add(M.Usuario(colegio_id=col.id, username='rshp_dir', password_hash='x', nombre='Dir', apellido='Sint',
                     role='direccion', activo=True, must_change_password=False, token_version=0))
areas = [add(M.Asignatura(colegio_id=col.id, nombre=n, area_curricular_codigo=c))
         for n, c in (('Lengua Española', 'LE'), ('Matemática', 'MAT'))]
DIAS_A = (0, 2)                                   # curso A: lunes y miércoles
CURSOS = {}
for sec, dias_lista in (('A', DIAS_A), ('B', (0, 1, 2, 3, 4))):
    curso = add(M.Curso(colegio_id=col.id, nombre=sec, grado_id=grado.id, ano_escolar_id=ano.id, activo=True))
    tit = add(M.Usuario(colegio_id=col.id, username='rshp_tit_%s' % sec, password_hash='x', nombre='Titular' + sec,
                        apellido='Sint', role='profesor', activo=True, must_change_password=False, token_version=0))
    for a in areas:
        add(M.AsignacionProfesor(colegio_id=col.id, profesor_id=tit.id, curso_id=curso.id, asignatura_id=a.id,
                                 ano_escolar_id=ano.id, es_titular=True, activo=True))
    ests = [add(M.Estudiante(colegio_id=col.id, nombre='Prim%d' % n, apellido='Sint%s' % sec,
                             matricula='RSHP-%s-%d' % (sec, n), curso_id=curso.id, no_lista=n, activo=True,
                             condicion='activo', sexo='F' if n % 2 else 'M', fecha_nacimiento=D(2017, n, 1),
                             fecha_ingreso=D(2025, 8, 1))) for n in range(1, 7)]
    for e in ests:
        for a in areas:
            for comp in (1, 2, 3):
                db.add(M.CalificacionPrimaria(colegio_id=col.id, estudiante_id=e.id, asignatura_id=a.id,
                                              ano_escolar_id=ano.id, competencia_numero=comp,
                                              p1=80, p2=82, p3=84, p4=86))
    f = INICIO
    while f <= FIN:
        if f.weekday() in dias_lista:
            for e in ests:
                db.add(M.Asistencia(colegio_id=col.id, estudiante_id=e.id, curso_id=curso.id, asignatura_id=None,
                                    fecha=f, estado=estado(e.no_lista, f), registrado_por=tit.id))
        f += dt.timedelta(days=1)
    CURSOS[sec] = (curso, ests)
db.commit()
assert db.query(M.Horario).count() == 0
c = TestClient(APP.app)
H = {'Authorization': 'Bearer ' + create_token(dire)}


def huella():
    db.expire_all()
    return sorted((a.id, a.estudiante_id, a.fecha, a.estado) for a in db.query(M.Asistencia).all())


h0 = huella()

for sec in ('A', 'B'):
    curso, ests = CURSOS[sec]
    print('\n== Curso %s (%s) ==' % (sec, 'lista lunes y miércoles' if sec == 'A' else 'lista todos los días hábiles'))
    # ── E. Endpoint ──
    v = RV.validar_registro_primaria(db, curso.id, col.id)
    check('E %s validador: sin errores ni advertencias; un aviso de «sin horario»' % sec,
          v.is_valid and not v.warnings and len(v.avisos) == 1 and 'no tiene horario configurado' in v.avisos[0]
          and v.info.get('curso_sin_horario') is True, (v.errors, v.warnings, v.avisos))
    check('E %s el aviso explica que el porcentaje anual del Acta depende del calendario y de la asistencia completa, '
          'no del horario' % sec, v.avisos and 'no depende del horario' in v.avisos[0]
          and 'calendario escolar' in v.avisos[0] and 'asistencia está completa' in v.avisos[0]
          and 'queda sin calcular' not in v.avisos[0], v.avisos)
    rv = c.get('/api/registros/preview/%d' % curso.id, headers=H)
    check('E %s la vista previa de la pantalla trae el aviso' % sec,
          rv.status_code == 200 and len((rv.json().get('validacion') or {}).get('avisos') or []) == 1)
    r = c.get('/api/registros/primaria/%d' % curso.id, headers=H)
    check('E %s Registro oficial de Primaria: 200 PDF sin ?force' % sec,
          r.status_code == 200 and r.content[:4] == b'%PDF', (r.status_code, r.text[:300]))
    if r.status_code != 200:
        continue
    if SALIDA:
        os.makedirs(SALIDA, exist_ok=True)
        open(os.path.join(SALIDA, 'registro_primaria_sin_horario_%s.pdf' % sec), 'wb').write(r.content)
    doc = pymupdf.open(stream=r.content, filetype='pdf')

    # ── M. Matriz y hoja mensual ──
    mat = build_asistencia_registro(db, curso.id, estudiantes=ests)
    marcas = {}
    for a in db.query(M.Asistencia).filter_by(curso_id=curso.id).all():
        marcas.setdefault((a.fecha.year, a.fecha.month), {})[(a.estudiante_id, a.fecha.day)] = a.estado
    ok_cols, ok_vals, ok_cnt, det = True, True, True, []
    letra = {'presente': 'P', 'ausente': 'A', 'tardanza': 'T'}
    for m in mat:
        mm = marcas.get((m['anio'], m['mes_num']), {})
        dias_bd = sorted({d for (_e, d) in mm})
        if m['dias'] != dias_bd:
            ok_cols = False
            det.append((m['clave'], m['dias'], dias_bd))
        for fila in m['filas']:
            for d, val in zip(m['dias'], fila['valores']):
                if val != letra[mm[(fila['estudiante_id'], d)]]:
                    ok_vals = False
            n_p = sum(1 for (e, d), s in mm.items() if e == fila['estudiante_id'] and s == 'presente')
            n_a = sum(1 for (e, d), s in mm.items() if e == fila['estudiante_id'] and s == 'ausente')
            if (fila['presentes'], fila['ausentes']) != (n_p, n_a):
                ok_cnt = False
    check('M %s columnas de cada mes = exactamente las fechas con marca real (ningún día inventado)' % sec, ok_cols, det[:2])
    check('M %s cada celda es la marca real; ninguna ausencia inventada' % sec, ok_vals)
    check('M %s presentes y ausentes por fila = los de la base' % sec, ok_cnt)
    check('M %s ningún porcentaje mensual y «asistencia esperada no determinada»' % sec,
          all(f['porcentaje'] is None for m in mat for f in m['filas'])
          and all(m['asistencia_esperada_determinada'] is False for m in mat))
    # PDF: la hoja de septiembre 2025 imprime en la banda «Fecha» solo esas fechas
    # y tantas letras como marcas reales tiene el mes.
    pag = next((p for p in doc if 'SEPTIEMBRE 2025' in p.get_text()), None)
    sep = marcas.get((2025, 9), {})
    if pag is None:
        check('M %s PDF: hoja de SEPTIEMBRE 2025 presente' % sec, False)
    else:
        h = pag.rect.height
        palabras = pag.get_text('words')
        fechas_pdf = sorted(int(w[4]) for w in palabras
                            if w[4].isdigit() and abs(((w[1] + w[3]) / 2) - RP.ASIST_FECHA_Y) < 4
                            and w[0] < RP.ASIST_VERTICALES[-1])
        letras = [w[4] for w in palabras if w[4] in ('P', 'A', 'T', 'E')
                  and RP.ASIST_FILAS[0] < (w[1] + w[3]) / 2 < RP.ASIST_TOTAL_Y - 6 and w[0] < RP.ASIST_VERTICALES[-1]]
        check('M %s PDF septiembre: la banda «Fecha» imprime solo las fechas con marca' % sec,
              fechas_pdf == sorted({d for (_e, d) in sep}), (fechas_pdf, sorted({d for (_e, d) in sep})))
        check('M %s PDF septiembre: %d letras = %d marcas reales (ni una más)' % (sec, len(letras), len(sep)),
              len(letras) == len(sep))

    # ── P. Porcentaje anual del Acta ──
    db.expire_all()
    _rec, cond = APP._datos_acta_primaria(db, dire, ests, {})
    cob = [(cond.get(i) or {}).get('asistencia', {}).get('cobertura_completa') for i in range(len(ests))]
    pct = [(cond.get(i) or {}).get('asistencia', {}).get('pct_asistencia') for i in range(len(ests))]
    if sec == 'A':
        check('P A Acta: sin cobertura completa del calendario, ningún porcentaje anual', not any(cob) and
              all(p is None for p in pct), (cob, pct))
    else:
        check('P B Acta: con lista en TODOS los días hábiles del calendario, el porcentaje anual oficial sí existe '
              '(se calcula con el calendario del centro, no con el horario)', all(cob) and all(p is not None for p in pct),
              (cob, pct))

check('Ninguna marca se creó, borró ni cambió', huella() == h0)
print('\nRESULTADO REG-SH PRIMARIA SIN HORARIO: %d PASARON / %d FALLARON'
      % (sum(1 for _, ok in RES if ok), sum(1 for _, ok in RES if not ok)))
db.close()
sys.exit(0 if all(ok for _, ok in RES) else 1)
