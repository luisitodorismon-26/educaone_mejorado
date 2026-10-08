# -*- coding: utf-8 -*-
"""
EducaOne — UN BOLETÍN COMPLETO DE PUNTA A PUNTA, con asistencia canónica.

El caso es el de producción que motivó este bloque (1ro de Secundaria, nueve
áreas aprobadas, Inglés aprobado por Extraordinaria con 70), con las MISMAS
notas competencia por competencia, pero anónimo y en una base temporal.

    ESCENARIO A · asistencia incompleta (6 días con lista de 26 lectivos)
        → el motor no certifica: PENDIENTE; el PDF dice N/D y la cobertura.
    ESCENARIO B · asistencia completa
        → el motor calcula solo: PROMOVIDO; el PDF imprime el % real y la
          misma condición que el motor.
    ESCENARIO C · asistencia completa con más del 20 % de faltas
        → el motor NO reprueba: pide la revisión humana que ya tenía (A2).

El año escolar es el del colegio de prueba, con SU fecha de inicio: nada de
este archivo está en el motor.

Uso:
    cd backend
    python tools/test_boletin_completo_asistencia.py
"""
import asyncio
import datetime as dt
import io
import os
import sys

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(BK, "tools"))

from test_utils import aislar_base_de_datos  # noqa: E402

TMP = aislar_base_de_datos('bol_completo')

from database import engine, SessionLocal  # noqa: E402
from test_utils import verificar_engine_aislado  # noqa: E402

verificar_engine_aislado(engine, TMP)

import models as M  # noqa: E402
import promocion_academica as PA  # noqa: E402
import resultado_academico as RA  # noqa: E402
import resultado_academico_consumidores as RAC  # noqa: E402
import asistencia_canonica as ASIS  # noqa: E402
import app as APP  # noqa: E402

M.Base.metadata.create_all(bind=engine)

from fastapi.testclient import TestClient  # noqa: E402
from auth import create_token  # noqa: E402
from pypdf import PdfReader  # noqa: E402

PASARON, FALLARON = [], []


def check(nombre, cond, detalle=''):
    if cond:
        PASARON.append(nombre)
        print("  PASA   %-66s %s" % (nombre, detalle))
    else:
        FALLARON.append(nombre)
        print("  FALLA  %-66s %s" % (nombre, detalle))


db = SessionLocal()
INICIO = dt.date(2026, 9, 1)          # inicio de clases DE ESTE colegio
HOY = APP.today_rd()

col = M.Colegio(nombre='Colegio Prueba', codigo='BOLCOMP', activo=True)
db.add(col)
db.flush()
ano = M.AnoEscolar(colegio_id=col.id, nombre='2026-2027', activo=True,
                   cerrado=False, fecha_inicio=INICIO,
                   fecha_fin=dt.date(2027, 6, 30))
grado = M.Grado(colegio_id=col.id, nombre='1ro Secundaria',
                nivel='secundaria', orden=1, activo=True)
db.add_all([ano, grado])
db.flush()
# El feriado del colegio cuenta: el 24 de septiembre no es lectivo.
db.add(M.DiaNoLaborable(colegio_id=col.id, fecha=dt.date(2026, 9, 24),
                        nombre='Las Mercedes', recurrente=True, activo=True))
curso = M.Curso(colegio_id=col.id, nombre='A', grado_id=grado.id,
                ano_escolar_id=ano.id, activo=True)
dire = M.Usuario(colegio_id=col.id, username='bc_dir', password_hash='x',
                 nombre='D', role='direccion', activo=True,
                 must_change_password=False, token_version=0)
db.add_all([curso, dire])
db.flush()

# Las notas del caso real, competencia por competencia (p1..p4).
NOTAS = {
    'CS':   [(85, 80, 80, 75), (78, 88, 78, 72), (80, 85, 79, 73), (87, 81, 75, 79)],
    'LEI':  [(65, 60, 65, 60), (67, 78, 68, 89), (56, 50, 71, 95), (66, 63, 56, 94)],
    'LE':   [(75, 76, 72, 71), (75, 73, 80, 77), (75, 80, 85, 79), (77, 74, 79, 77)],
    'LEF':  [(75, 77, 80, 82), (79, 78, 84, 85), (71, 79, 82, 88), (77, 82, 83, 80)],
    'CN':   [(80, 82, 80, 88), (85, 81, 85, 85), (86, 89, 88, 81), (88, 88, 83, 89)],
    'EF':   [(85, 91, 80, 90), (89, 90, 89, 98), (90, 85, 85, 85), (92, 87, 88, 88)],
    'EA':   [(85, 85, 82, 85), (85, 88, 88, 89), (95, 90, 89, 86), (87, 89, 88, 85)],
    'FIHR': [(85, 85, 86, 84), (89, 90, 91, 78), (85, 80, 81, 83), (89, 88, 81, 80)],
    'MAT':  [(88, 89, 85, 89), (89, 85, 89, 89), (85, 86, 88, 85), (88, 80, 87, 81)],
}
CF_EXTRA = {'LE': 76.575, 'LEF': 80.125, 'CS': 79.675, 'CN': 84.875,
            'EF': 88.25, 'EA': 87.225, 'FIHR': 84.675, 'MAT': 86.45}
NOTA_FINAL = {'LE': 77, 'LEF': 80, 'CS': 80, 'CN': 85, 'EF': 88, 'EA': 87,
              'FIHR': 85, 'MAT': 86}


def alumno(etiqueta, no_lista):
    e = M.Estudiante(colegio_id=col.id, matricula='BC-%s' % etiqueta,
                     nombre='Estudiante', apellido=etiqueta, curso_id=curso.id,
                     no_lista=no_lista, activo=True, condicion='activo',
                     fecha_ingreso=dt.date(2026, 8, 20))   # alta antes del año
    db.add(e)
    db.flush()
    for cod, comps in NOTAS.items():
        asig = asignaturas[cod]
        for n, (p1, p2, p3, p4) in enumerate(comps, start=1):
            db.add(M.CalificacionSecundaria(
                colegio_id=col.id, estudiante_id=e.id, asignatura_id=asig.id,
                ano_escolar_id=ano.id, competencia_numero=n,
                p1=p1, p2=p2, p3=p3, p4=p4))
        if cod == 'LEI':
            db.add(M.EvaluacionExtraSecundaria(
                colegio_id=col.id, estudiante_id=e.id, asignatura_id=asig.id,
                ano_escolar_id=ano.id, cf_original=68.95, cec=70,
                completiva_final=69, ceex=70, extraordinaria_final=70,
                condicion_final='aprobado_extraordinaria', nota_final=70))
        else:
            db.add(M.EvaluacionExtraSecundaria(
                colegio_id=col.id, estudiante_id=e.id, asignatura_id=asig.id,
                ano_escolar_id=ano.id, cf_original=CF_EXTRA[cod],
                condicion_final='aprobado_normal', nota_final=NOTA_FINAL[cod]))
    return e


asignaturas = {}
for cod in NOTAS:
    a = M.Asignatura(colegio_id=col.id, nombre=cod, codigo=cod, area='X',
                     area_curricular_codigo=cod, activo=True)
    db.add(a)
    db.flush()
    asignaturas[cod] = a

lectivos = []
d = INICIO
while d <= HOY:
    if d.weekday() < 5 and (d.month, d.day) != (9, 24):
        lectivos.append(d)
    d += dt.timedelta(days=1)


def marcar(est, dias, estado='presente'):
    for f in dias:
        db.add(M.Asistencia(colegio_id=col.id, estudiante_id=est.id,
                            curso_id=curso.id, asignatura_id=asignaturas['LEI'].id,
                            fecha=f, estado=estado))


# A · las listas reales del caso: seis días, con una falta a una materia el
# 2 de septiembre que NO hace ausente el día (vino a otras dos).
E_A = alumno('A', 1)
for f in (dt.date(2026, 9, 2), dt.date(2026, 9, 25), dt.date(2026, 9, 30),
          dt.date(2026, 10, 1), dt.date(2026, 10, 2), dt.date(2026, 10, 7)):
    if f <= HOY:
        marcar(E_A, [f])
db.add(M.Asistencia(colegio_id=col.id, estudiante_id=E_A.id, curso_id=curso.id,
                    asignatura_id=asignaturas['MAT'].id, fecha=dt.date(2026, 9, 2),
                    estado='ausente'))
# B · lista completa, todo presente.
E_B = alumno('B', 2)
marcar(E_B, lectivos)
# C · lista completa, con más del 20 % de faltas.
E_C = alumno('C', 3)
_n_faltas = len(lectivos) // 4 + 1
marcar(E_C, lectivos[:_n_faltas], 'ausente')
marcar(E_C, lectivos[_n_faltas:])
db.commit()

client = TestClient(APP.app)
TOK = create_token(dire)
HDR = {'Authorization': 'Bearer ' + TOK}


def paquete(est):
    pre = APP._precarga_curso_canonica(db, dire, curso, ano, estudiante_ids=[est.id])
    return APP._situacion_canonica_secundaria(db, dire, est, ano, pre)


# Lo que el endpoint le ENTREGA a la plantilla: así se comprueba que el PDF
# marca exactamente lo que dijo el motor (la casilla es una X sin texto).
import boletin_minerd_secundaria as _BMS  # noqa: E402
_real = _BMS.generar_boletin_secundaria_minerd
_ENTREGADO = {}


def _espia(*a, **k):
    _ENTREGADO.clear()
    _ENTREGADO.update(k)
    return _real(*a, **k)


_BMS.generar_boletin_secundaria_minerd = _espia


def pdf_texto(est):
    r = client.get('/api/boletines/estudiante/%d/pdf-minerd-v2' % est.id, headers=HDR)
    if r.status_code != 200:
        return None, r.status_code
    return "".join((p.extract_text() or '') for p in PdfReader(io.BytesIO(r.content)).pages), 200


print("\n=== NOTAS: EL CASO REAL, SIN TOCAR ===")
pa = paquete(E_A)
_lei = [x for x in pa['resultados'] if x['area_curricular_codigo'] == 'LEI'][0]
check('BC-01 las nueve áreas oficiales están, y aprobadas',
      len(pa['resultados']) == 9
      and all(x['estado'] in (RA.APROBADA, RA.APROBADA_EXTRAORDINARIA) for x in pa['resultados']),
      str(sorted(x['area_curricular_codigo'] for x in pa['resultados'])))
check('BC-02 Inglés: 70, aprobado por Extraordinaria',
      _lei['estado'] == RA.APROBADA_EXTRAORDINARIA and _lei['nota_final'] == 70.0,
      '%s %s' % (_lei['estado'], _lei['nota_final']))

print("\n=== ESCENARIO A · ASISTENCIA INCOMPLETA ===")
asis = pa['asistencia']
check('BC-03 la ventana empieza en la fecha de inicio DEL COLEGIO',
      asis['inicio'] == INICIO, str(asis['inicio']))
check('BC-04 el feriado del colegio no es día lectivo',
      dt.date(2026, 9, 24) not in asis['dias'], '')
check('BC-05 cobertura incompleta: %d de %d días con lista'
      % (asis['con_dato'], asis['dias_lectivos']),
      asis['con_dato'] < asis['dias_lectivos'] and not asis['cobertura_completa'], '')
check('BC-06 faltar a UNA materia no hizo ausente el día',
      asis['ausencias'] == 0, str(asis['ausencias']))
check('BC-07 el motor no certifica: PENDIENTE por asistencia no evaluada',
      pa['situacion']['condicion'] == PA.EN_PROCESO
      and PA.BLOQUEO_ASISTENCIA_NO_EVALUADA in pa['situacion']['bloqueos'],
      str(pa['situacion']['bloqueos']))
txt, st = pdf_texto(E_A)
check('BC-08 el PDF MINERD se genera', st == 200, str(st))
if txt:
    check('BC-09 el PDF no inventa 100 %: dice N/D y la cobertura',
          'N/D' in txt and ('Cobertura: %d de %d' % (asis['con_dato'], asis['dias_lectivos'])) in txt
          and '100%' not in txt, '')
    _sf = _ENTREGADO.get('situacion_final') or {}
    check('BC-10 la plantilla NO recibe casilla marcada: ni promovido ni repitente',
          _sf.get('promovido') is False and _sf.get('repitente') is False
          and 'PENDIENTE' in (_sf.get('condicion') or ''), str(_sf))
    check('BC-10b y recibe la MISMA asistencia que el motor',
          _ENTREGADO.get('asistencia_anual') == ASIS.anual_boletin(asis), '')

print("\n=== ESCENARIO B · ASISTENCIA COMPLETA ===")
pb = paquete(E_B)
check('BC-11 cobertura completa', pb['asistencia']['cobertura_completa'],
      '%d de %d' % (pb['asistencia']['con_dato'], pb['asistencia']['dias_lectivos']))
check('BC-12 el motor calcula SOLO la condición: PROMOVIDO',
      pb['situacion']['condicion'] == PA.PROMOVIDO, str(pb['situacion']['bloqueos']))
check('BC-13 con las mismas notas que el caso A (Inglés 70 Extraordinaria)',
      [x for x in pb['resultados'] if x['area_curricular_codigo'] == 'LEI'][0]['nota_final'] == 70.0, '')
txt, st = pdf_texto(E_B)
check('BC-14 el PDF MINERD se genera', st == 200, str(st))
if txt:
    check('BC-15 el PDF imprime el porcentaje REAL: 100 %',
          '100%' in txt and 'N/D' not in txt, '')
    _sf = _ENTREGADO.get('situacion_final') or {}
    check('BC-16 la plantilla marca PROMOVIDO, igual que el motor',
          _sf.get('promovido') is True and _sf.get('repitente') is False
          and _sf.get('condicion') == RAC.texto_situacion(pb['situacion']), str(_sf))
_an = APP._asistencia_anual_boletin(db, E_B.id, dire, ano)
check('BC-17 el boletín y el motor leen la MISMA asistencia',
      _an == ASIS.anual_boletin(pb['asistencia']), '')

print("\n=== ESCENARIO C · MÁS DEL 20 % DE FALTAS ===")
pc = paquete(E_C)
check('BC-18 cobertura completa y porcentaje real de faltas',
      pc['asistencia']['cobertura_completa']
      and pc['asistencia']['porcentaje_a2'] > PA.MAX_AUSENCIAS_NO_JUSTIFICADAS,
      '%.1f%%' % pc['asistencia']['porcentaje_a2'])
check('BC-19 el motor NO reprueba: pide la revisión humana que ya existía',
      pc['situacion']['condicion'] == PA.EN_PROCESO
      and PA.BLOQUEO_REVISION_ASISTENCIA in pc['situacion']['bloqueos'],
      str(pc['situacion']['bloqueos']))

print()
print("=" * 98)
print("RESULTADO: %d PASARON / %d FALLARON" % (len(PASARON), len(FALLARON)))
print("=" * 98)
for f in FALLARON:
    print("  FALLA:", f)

db.close()
sys.exit(1 if FALLARON else 0)
