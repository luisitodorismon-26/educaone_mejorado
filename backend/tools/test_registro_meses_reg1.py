# -*- coding: utf-8 -*-
"""
EducaOne — REG-1: el Registro Escolar organiza la asistencia por (año, mes),
desde `AnoEscolar.fecha_inicio` hasta `AnoEscolar.fecha_fin`.

    · cada mes conserva su hueco aunque esté vacío (no se adelanta octubre);
    · una marca se imprime en el mes de su FECHA REAL, no cuando se digitó;
    · diciembre 2026 → enero 2027 sin colisiones de número de mes;
    · Primaria: el formulario 1 es el mes de fecha_inicio;
    · asistencia fuera del año o más meses que huecos → FAIL CLOSED (422);
    · construir el Registro no escribe, no mueve ni duplica asistencia.

Base temporal aislada. Nunca producción.

Uso:
    cd backend
    python tools/test_registro_meses_reg1.py
"""
import datetime as dt
import os
import sys

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(BK, "tools"))

from test_utils import aislar_base_de_datos  # noqa: E402

TMP = aislar_base_de_datos('reg1_meses')

from database import engine, SessionLocal  # noqa: E402
from test_utils import verificar_engine_aislado  # noqa: E402

verificar_engine_aislado(engine, TMP)

import io  # noqa: E402

import models as M  # noqa: E402
from pypdf import PdfReader  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

import registro_asistencia as RA  # noqa: E402
import registro_escolar as RE  # noqa: E402
import registro_primaria as RP  # noqa: E402

M.Base.metadata.create_all(bind=engine)

D = dt.date
RESULTADOS = []


def check(nombre, ok, detalle=''):
    RESULTADOS.append((nombre, bool(ok)))
    print(('  OK  ' if ok else '  FALLA ') + nombre + ('' if ok else '  -> ' + str(detalle)))


db = SessionLocal()
_n = [0]


def escenario(inicio, fin, nivel='secundaria', n_est=3, horario=('Lunes', 'Martes', 'Miércoles',
                                                                    'Jueves', 'Viernes')):
    """Colegio + año + curso + 3 estudiantes + Matemática con horario L-V."""
    _n[0] += 1
    k = _n[0]
    col = M.Colegio(nombre='REG1-%d' % k, codigo='reg1%d' % k, activo=True)
    db.add(col)
    db.flush()
    ano = M.AnoEscolar(colegio_id=col.id, nombre='%d-%d' % (inicio.year, fin.year),
                       activo=True, cerrado=False, fecha_inicio=inicio, fecha_fin=fin)
    grd = M.Grado(colegio_id=col.id, nombre='4to ' + nivel.title(), nivel=nivel,
                  orden=4, activo=True)
    db.add_all([ano, grd])
    db.flush()
    curso = M.Curso(colegio_id=col.id, nombre='A', grado_id=grd.id,
                    ano_escolar_id=ano.id, activo=True)
    prof = M.Usuario(colegio_id=col.id, username='reg1_p%d' % k, password_hash='x',
                     nombre='Pro', apellido='Fesor', role='profesor', activo=True,
                     must_change_password=False, token_version=0)
    mat = M.Asignatura(colegio_id=col.id, nombre='Matemática', codigo='MAT',
                       area='X', area_curricular_codigo='MAT', activo=True)
    db.add_all([curso, prof, mat])
    db.flush()
    ests = []
    for i in range(n_est):
        e = M.Estudiante(colegio_id=col.id, matricula='R%d-%d' % (k, i + 1),
                         nombre='Est%d' % (i + 1), apellido='Reg', curso_id=curso.id,
                         activo=True, no_lista=i + 1, sexo='F' if i % 2 else 'M',
                         fecha_nacimiento=D(2012, 1, i + 1))
        ests.append(e)
    db.add_all(ests)
    for dia in horario:
        db.add(M.Horario(colegio_id=col.id, profesor_id=prof.id, curso_id=curso.id,
                         asignatura_id=mat.id if nivel == 'secundaria' else None,
                         dia=dia, hora_inicio='08:00', hora_fin='09:00',
                         tipo_bloque='clase', activo=True))
    db.commit()
    return col, ano, curso, mat, ests


def marcar(col, curso, est, fecha, estado='presente', asig=None):
    a = M.Asistencia(colegio_id=col.id, estudiante_id=est.id, curso_id=curso.id,
                     asignatura_id=asig.id if asig else None, fecha=fecha, estado=estado)
    db.add(a)
    db.commit()
    return a


def mes(matriz, clave):
    return next((m for m in matriz if m['clave'] == clave), None)


def codigo(m, est, dia):
    fila = next(f for f in m['filas'] if f['estudiante_id'] == est.id)
    return fila['valores'][m['dias'].index(dia)] if dia in m['dias'] else None


def textos_paginas(pdf_bytes, paginas_1b):
    r = PdfReader(io.BytesIO(pdf_bytes))
    return {p: (r.pages[p - 1].extract_text() or '').lower() for p in paginas_1b}


MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto',
         'septiembre', 'octubre', 'noviembre', 'diciembre']


def meses_en(texto):
    return {m for m in MESES if m in texto}


def pdf_secundaria(matriz, grado=4):
    est = [{'no_lista': i + 1, 'nombre': 'E%d' % (i + 1), 'sexo': 'M'}
           for i in range(len(matriz[0]['filas']) if matriz else 3)]
    data = {'Matemática': {'docente': 'Pro Fesor', 'asistencia_matriz': matriz,
                           'calificaciones': {}}}
    return RE.generar_registro_desde_sistema({'nombre': 'C'}, {'seccion': 'A'}, '2026-2027',
                                             est, data, grado)


def pdf_primaria(matriz, n_est=3):
    est = [{'no_lista': i + 1, 'nombre': 'E%d' % (i + 1), 'sexo': 'M',
            'fecha_nacimiento': D(2018, 1, 1)} for i in range(n_est)]
    return RP.generar_registro_primaria_desde_sistema(
        {'nombre': 'C'}, {'seccion': 'A'}, '2026-2027', est, {}, matriz, {}, 4)


print("\n=== 1 · PROFETA MOISÉS: 2026-09-07 → 2027-06-25 ===")
col, ano, curso, mat, ests = escenario(D(2026, 9, 7), D(2027, 6, 25))
check('R1-01 la secuencia del año son 10 (año, mes) de sep-2026 a jun-2027',
      RA.meses_del_ano(ano) == [(2026, 9), (2026, 10), (2026, 11), (2026, 12), (2027, 1),
                                (2027, 2), (2027, 3), (2027, 4), (2027, 5), (2027, 6)],
      RA.meses_del_ano(ano))
marcar(col, curso, ests[0], D(2026, 10, 14), asig=mat)
mz = RA.build_asistencia_registro(db, curso.id, asignatura_id=mat.id, estudiantes=ests)
check('R1-02 la matriz trae los 10 meses, en orden y con su posición 0..9',
      [m['clave'] for m in mz] == ['2026-09', '2026-10', '2026-11', '2026-12', '2027-01',
                                   '2027-02', '2027-03', '2027-04', '2027-05', '2027-06']
      and [m['posicion'] for m in mz] == list(range(10)), [m['clave'] for m in mz])
check('R1-03 septiembre empieza el 7 (fecha_inicio), no el 1',
      mz[0]['dias'][0] == 7, mz[0]['dias'][:3])
check('R1-04 junio termina el 25 (fecha_fin)', mz[-1]['dias'][-1] == 25, mz[-1]['dias'][-3:])

print("\n=== 2 · SEPTIEMBRE VACÍO + OCTUBRE CON DATOS (Secundaria) ===")
# Sin marcas, las celdas son '' o '-' (NO APLICA: la canónica toma la primera
# marca como alta mientras no haya otra), pero ningún P/A/T/E.
check('R1-05 septiembre está en el hueco 0 aunque no tenga ni una marca',
      mz[0]['clave'] == '2026-09'
      and not any(v in ('P', 'A', 'T', 'E') for f in mz[0]['filas'] for v in f['valores']),
      mz[0]['clave'])
check('R1-06 octubre está en el hueco 1, con su marca del 14',
      mz[1]['clave'] == '2026-10' and codigo(mz[1], ests[0], 14) == 'P', '')
pdf = pdf_secundaria(mz)
tx = textos_paginas(pdf, [32, 33, 34, 35, 36])
check('R1-07 PDF: la 1ra hoja de Matemática (pág 32) es septiembre + octubre',
      meses_en(tx[32]) == {'septiembre', 'octubre'}, meses_en(tx[32]))
check('R1-08 PDF: pág 33 noviembre+diciembre, pág 34 enero+febrero',
      meses_en(tx[33]) == {'noviembre', 'diciembre'} and meses_en(tx[34]) == {'enero', 'febrero'},
      (meses_en(tx[33]), meses_en(tx[34])))
check('R1-09 PDF: la última hoja (pág 36) es mayo + junio; septiembre NO se fue al final',
      meses_en(tx[36]) == {'mayo', 'junio'}, meses_en(tx[36]))

print("\n=== 3 · BACKFILL: SEPTIEMBRE DIGITADO DESPUÉS DE OCTUBRE ===")
id_oct = db.query(M.Asistencia).filter_by(estudiante_id=ests[0].id).one().id
tardia = marcar(col, curso, ests[1], D(2026, 9, 15), estado='ausente', asig=mat)
check('R1-10 la fila de septiembre se creó DESPUÉS que la de octubre', tardia.id > id_oct, '')
mz2 = RA.build_asistencia_registro(db, curso.id, asignatura_id=mat.id, estudiantes=ests)
check('R1-11 el 15-sep aparece en septiembre 2026, columna 15', codigo(mz2[0], ests[1], 15) == 'A',
      codigo(mz2[0], ests[1], 15))
en_otros = [m['clave'] for m in mz2[1:] if codigo(m, ests[1], 15) not in (None, '', '-')]
check('R1-12 el 15-sep NO aparece en ningún otro mes', en_otros == [], en_otros)
check('R1-13 octubre sigue igual (su marca del 14 intacta)', codigo(mz2[1], ests[0], 14) == 'P', '')
db.refresh(tardia)
check('R1-14 la fecha guardada no cambió', tardia.fecha == D(2026, 9, 15), tardia.fecha)
tx2 = textos_paginas(pdf_secundaria(mz2), [32, 36])
check('R1-15 PDF tras el backfill: mismos huecos (pág 32 sep+oct, pág 36 may+jun)',
      meses_en(tx2[32]) == {'septiembre', 'octubre'} and meses_en(tx2[36]) == {'mayo', 'junio'},
      (meses_en(tx2[32]), meses_en(tx2[36])))

print("\n=== 4 · DIGITACIÓN FUERA DE ORDEN ===")
col4, ano4, curso4, mat4, ests4 = escenario(D(2026, 9, 7), D(2027, 6, 25), horario=())
for f in (D(2026, 9, 25), D(2026, 10, 10), D(2026, 9, 8), D(2026, 10, 20), D(2026, 9, 12)):
    marcar(col4, curso4, ests4[0], f, asig=mat4)
mz4 = RA.build_asistencia_registro(db, curso4.id, asignatura_id=mat4.id, estudiantes=ests4)
check('R1-16 orden de digitación 25,10,8,20,12 → septiembre [8, 12, 25]',
      mz4[0]['dias'] == [8, 12, 25], mz4[0]['dias'])
check('R1-17 → octubre [10, 20]', mz4[1]['dias'] == [10, 20], mz4[1]['dias'])
check('R1-18 cada marca en su columna cronológica',
      all(codigo(mz4[0], ests4[0], d) == 'P' for d in (8, 12, 25))
      and all(codigo(mz4[1], ests4[0], d) == 'P' for d in (10, 20)), '')
check('R1-19 sin horario los 10 meses siguen ahí (vacíos con 0 columnas)',
      len(mz4) == 10 and mz4[2]['dias'] == [] and mz4[2]['clave'] == '2026-11', len(mz4))

print("\n=== 5 · DICIEMBRE 2026 → ENERO 2027 ===")
marcar(col4, curso4, ests4[1], D(2026, 12, 15), asig=mat4)
marcar(col4, curso4, ests4[1], D(2027, 1, 15), estado='tardanza', asig=mat4)
mz5 = RA.build_asistencia_registro(db, curso4.id, asignatura_id=mat4.id, estudiantes=ests4)
dic, ene = mes(mz5, '2026-12'), mes(mz5, '2027-01')
check('R1-20 diciembre 2026 es el hueco 3 y enero 2027 el 4',
      dic['posicion'] == 3 and ene['posicion'] == 4 and dic['anio'] == 2026 and ene['anio'] == 2027,
      (dic['posicion'], ene['posicion']))
check('R1-21 el 15-dic y el 15-ene no se mezclan', codigo(dic, ests4[1], 15) == 'P'
      and codigo(ene, ests4[1], 15) == 'T', (codigo(dic, ests4[1], 15), codigo(ene, ests4[1], 15)))

print("\n=== 6 · (AÑO, MES) SIN COLISIONES: UN AÑO CON DOS SEPTIEMBRES ===")
col6, ano6, curso6, mat6, ests6 = escenario(D(2026, 9, 1), D(2027, 9, 30), horario=())
marcar(col6, curso6, ests6[0], D(2026, 9, 15), asig=mat6)
marcar(col6, curso6, ests6[0], D(2027, 9, 15), estado='ausente', asig=mat6)
mz6 = RA.build_asistencia_registro(db, curso6.id, asignatura_id=mat6.id, estudiantes=ests6)
s26, s27 = mes(mz6, '2026-09'), mes(mz6, '2027-09')
check('R1-22 septiembre 2026 y septiembre 2027 son dos meses distintos',
      s26 is not None and s27 is not None and s26['posicion'] == 0 and s27['posicion'] == 12, '')
check('R1-23 cada 15-sep en su año (P en 2026, A en 2027)',
      codigo(s26, ests6[0], 15) == 'P' and codigo(s27, ests6[0], 15) == 'A', '')

print("\n=== 7 · OVERFLOW → ERROR EXPLÍCITO ===")
try:
    pdf_secundaria(mz6)
    check('R1-24 Secundaria: 13 meses en 10 huecos se rechaza', False, 'generó el PDF')
except RA.MesesExcedenPlantilla as e:
    check('R1-24 Secundaria: 13 meses en 10 huecos se rechaza',
          e.detalle['meses'] == 13 and e.detalle['huecos'] == 10, e.detalle)
try:
    pdf_primaria(mz6)
    check('R1-25 Primaria: 13 meses en 12 formularios se rechaza', False, 'generó el PDF')
except RA.MesesExcedenPlantilla as e:
    check('R1-25 Primaria: 13 meses en 12 formularios se rechaza',
          e.detalle['meses'] == 13 and e.detalle['huecos'] == 12, e.detalle)

print("\n=== 8 · FUERA DEL AÑO ESCOLAR → INCONSISTENCIA, NO SE MUEVE ===")
fuera = marcar(col, curso, ests[2], D(2026, 9, 1), asig=mat)     # antes del 7-sep
mz8 = RA.build_asistencia_registro(db, curso.id, asignatura_id=mat.id, estudiantes=ests)
check('R1-26 la marca del 1-sep queda en fuera_de_rango',
      [x['fecha'] for x in mz8.fuera_de_rango] == [D(2026, 9, 1)], mz8.fuera_de_rango)
check('R1-27 y no se coloca en ningún mes (ni en septiembre)',
      all(1 not in m['dias'] or codigo(m, ests[2], 1) in ('', '-') for m in mz8), '')
try:
    pdf_secundaria(mz8)
    check('R1-28 Secundaria se niega a emitir', False, 'generó el PDF')
except RA.AsistenciaFueraDelAnoEscolar as e:
    check('R1-28 Secundaria se niega a emitir', e.detalle['fechas'] == ['2026-09-01'], e.detalle)
try:
    pdf_primaria(mz8)
    check('R1-29 Primaria se niega a emitir', False, 'generó el PDF')
except RA.AsistenciaFueraDelAnoEscolar:
    check('R1-29 Primaria se niega a emitir', True)
db.refresh(fuera)
check('R1-30 la asistencia fuera de rango sigue en la base con su fecha', fuera.fecha == D(2026, 9, 1), '')
import app as APP  # noqa: E402
for exc in (RA.AsistenciaFueraDelAnoEscolar({'motivo': 'X'}), RA.MesesExcedenPlantilla({'motivo': 'Y'})):
    r = APP._respuesta_conflicto_espec(exc)
    check('R1-31 la API responde 422 (%s)' % type(exc).__name__,
          r is not None and r.status_code == 422, r)
db.delete(fuera)
db.commit()

print("\n=== 9 · EL ESTUDIANTE CONSERVA SU FILA ===")
orden = [e.id for e in ests]
check('R1-32 en TODOS los meses las filas siguen el no_lista (1, 2, 3)',
      all([f['estudiante_id'] for f in m['filas']] == orden and
          [f['no'] for f in m['filas']] == [1, 2, 3] for m in mz2), '')
check('R1-33 el estudiante 2 —que solo tiene una marca tardía— sigue en la fila 2',
      mz2[0]['filas'][1]['estudiante_id'] == ests[1].id, '')

print("\n=== 10 · PRIMARIA: FORMULARIO 1 = MES DE INICIO ===")
colp, anop, cursop, _, estsp = escenario(D(2026, 9, 7), D(2027, 6, 25), nivel='primaria')
marcar(colp, cursop, estsp[0], D(2026, 10, 5))
marcar(colp, cursop, estsp[1], D(2026, 9, 15), estado='excusa')    # backfill
mzp = RA.build_asistencia_registro(db, cursop.id, estudiantes=estsp)
pdfp = pdf_primaria(mzp)
paginas = [p + 1 for p in RP._construir_indice(4)['asistencia']]
txp = textos_paginas(pdfp, paginas)
check('R1-34 formulario 1 = SEPTIEMBRE, formulario 2 = OCTUBRE',
      'septiembre' in txp[paginas[0]] and 'octubre' in txp[paginas[1]], '')
check('R1-35 formulario 10 = JUNIO', 'junio' in txp[paginas[9]], '')
plantilla = PdfReader(RP.get_template_path(4))
virgenes = all(txp[paginas[i]] == (plantilla.pages[paginas[i] - 1].extract_text() or '').lower()
               for i in (10, 11))
check('R1-36 formularios 11 y 12 quedan vírgenes (idénticos a la plantilla)', virgenes, '')
check('R1-37 ningún formulario dice AGOSTO', not any('agosto' in t for t in txp.values()), '')

colA, anoA, cursoA, _, estsA = escenario(D(2026, 8, 24), D(2027, 6, 25), nivel='primaria')
marcar(colA, cursoA, estsA[0], D(2026, 8, 26))
mzA = RA.build_asistencia_registro(db, cursoA.id, estudiantes=estsA)
check('R1-38 colegio que empieza en agosto: la matriz arranca en 2026-08 (11 meses)',
      mzA[0]['clave'] == '2026-08' and len(mzA) == 11, (mzA[0]['clave'], len(mzA)))
txA = textos_paginas(pdf_primaria(mzA), paginas)
check('R1-39 y su formulario 1 = AGOSTO, formulario 2 = SEPTIEMBRE',
      'agosto' in txA[paginas[0]] and 'septiembre' in txA[paginas[1]], '')

print("\n=== 11 · CERO ESCRITURA Y SIN DUPLICADOS ===")
antes = db.query(M.Asistencia).count()
fechas_antes = sorted((a.id, a.fecha) for a in db.query(M.Asistencia).all())
for c, a in ((curso, mat), (curso4, mat4), (curso6, mat6)):
    RA.build_asistencia_registro(db, c.id, asignatura_id=a.id)
RA.build_asistencia_registro(db, cursop.id)
check('R1-40 construir el Registro no crea ni borra asistencia', db.query(M.Asistencia).count() == antes, '')
check('R1-41 ni cambia ninguna fecha',
      sorted((a.id, a.fecha) for a in db.query(M.Asistencia).all()) == fechas_antes, '')
for etiqueta, kw in (('materia', {'asig': mat}), ('general', {})):
    try:
        marcar(col if kw else colp, curso if kw else cursop, ests[0] if kw else estsp[0],
               D(2026, 10, 14) if kw else D(2026, 10, 5), **kw)
        check('R1-42 la unicidad existente impide el duplicado (%s)' % etiqueta, False, 'duplicó')
    except IntegrityError:
        db.rollback()
        check('R1-42 la unicidad existente impide el duplicado (%s)' % etiqueta, True)

db.close()
ok = sum(1 for _, r in RESULTADOS if r)
print('\nRESULTADO REG-1: %d PASARON / %d FALLARON' % (ok, len(RESULTADOS) - ok))
sys.exit(0 if ok == len(RESULTADOS) else 1)
