# -*- coding: utf-8 -*-
"""
EducaOne — REG-3: calibración del Registro Escolar de Primaria (1ro-6to).

Datos SINTÉTICOS marcadores; la verificación es por POSICIÓN de la tinta azul
del overlay (pymupdf) dentro de las celdas medidas en las plantillas reales:

    · portada 1ro y 2do-6to (+32 pt);
    · datos del centro: sobre su línea, zona/sector, maestro titular;
    · datos generales: hoja doble, nacionalidad/sexo/fecha/edad y dirección y
      condición inicial en sus tres variantes;
    · asistencia SEMANAL: cada fecha en su semana y su día; resumen del mes;
      meses cronológicos y backfill (REG-1 intacto);
    · calificaciones 1ro-2do (P1-P4) y 3ro-6to (P y RP), C3, promedios,
      final del área y recuperaciones dentro de la hoja;
    · Acta: cuatro variantes, situación canónica, % de asistencia;
    · capacidad: >45 estudiantes o una fecha sin casilla → error (422).

Base temporal aislada para la parte de app.py. Nunca producción.

Uso:
    cd backend
    python tools/test_registro_primaria_reg3.py
"""
import os
import sys
from datetime import date, timedelta

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(BK, "tools"))

from test_utils import aislar_base_de_datos  # noqa: E402

TMP = aislar_base_de_datos('reg3_primaria')

from database import engine, SessionLocal  # noqa: E402
from test_utils import verificar_engine_aislado  # noqa: E402

verificar_engine_aislado(engine, TMP)

import pymupdf  # noqa: E402

import models as M  # noqa: E402
import registro_primaria as RP  # noqa: E402
import registro_escolar as RE  # noqa: E402

AZUL = 0x0000b3
RESULTADOS = []


def check(nombre, ok, detalle=''):
    RESULTADOS.append((nombre, bool(ok)))
    print(('  OK  ' if ok else '  FALLA ') + nombre + ('' if ok else '  -> ' + str(detalle)[:300]))


MESES = [(2026, 9, 'septiembre'), (2026, 10, 'octubre'), (2026, 11, 'noviembre'),
         (2026, 12, 'diciembre'), (2027, 1, 'enero'), (2027, 2, 'febrero'), (2027, 3, 'marzo'),
         (2027, 4, 'abril'), (2027, 5, 'mayo'), (2027, 6, 'junio')]
COD = ['P', 'A', 'T', 'E', 'P']
AREAS = ['Lengua Española', 'Matemática', 'Ciencias Sociales', 'Ciencias de la Naturaleza',
         'Educación Física', 'Educación Artística', 'Formación Integral Humana y Religiosa',
         'Lenguas Extranjeras (Inglés)']
CONDS = ['promovido', 'repitente', 'reingreso', 'aplazado', 'nuevo']
SITS = ['PROMOVIDO', 'APLAZADO', 'REPROBADO', 'EN_PROCESO']


def habiles(y, m, desde=1):
    d, out = date(y, m, desde), []
    while d.month == m:
        if d.weekday() < 5:
            out.append(d.day)
        d += timedelta(days=1)
    return out


def matriz(n, extra_dia=None):
    out = []
    for pos, (y, m, nombre) in enumerate(MESES):
        dias = habiles(y, m, 7 if (y, m) == (2026, 9) else 1)
        if extra_dia and (y, m) == extra_dia[:2]:
            dias = sorted(set(dias) | {extra_dia[2]})
        filas = []
        for e in range(n):
            vals = [COD[(e + d) % 5] for d in range(len(dias))]
            filas.append({'valores': vals, 'presentes': vals.count('P'), 'tardanzas': vals.count('T'),
                          'ausentes': vals.count('A'), 'con_dato': len(vals)})
        out.append({'mes': nombre, 'mes_num': m, 'anio': y, 'posicion': pos, 'dias': dias,
                    'filas': filas, 'dias_trabajados_configurados': None})
    return out


def generar(grado, n=6, extra_dia=None):
    est = [{'no_lista': i + 1, 'nombre': 'Nombreextralargo%d Apellidocompuesto Segundo' % (i + 1),
            'sexo': 'F' if i % 2 else 'M', 'fecha_nacimiento': date(2019 - grado, i % 12 + 1, i % 28 + 1),
            'nacionalidad': 'Dominicana',
            'direccion': 'Calle %d No. 25, Residencial Los Jardines del Norte, Santo Domingo Este' % (i + 1),
            'condicion_entrada': CONDS[i % 5]} for i in range(n)]
    cal = {}
    for a_idx, a in enumerate(AREAS):
        if 'Extranjeras' in a and grado < 4:
            continue
        datos = {}
        for e in range(n):
            comps = {c: {'p1': 10 * (a_idx + 1) + c,
                         'rp1': (10 * (a_idx + 1) + c + 0.5) if grado >= 3 else None,
                         'p2': 10 * (a_idx + 1) + c, 'p3': 10 * (a_idx + 1) + c,
                         'p4': 10 * (a_idx + 1) + c, 'cf_oficial': 70 + c} for c in (1, 2, 3)}
            comps['_area'] = {'cf': 80 + a_idx}
            datos[e] = comps
        cal[a] = datos
    rec = {0: {'lengua espanola': {'final': 66, 'especial': 67 if grado >= 3 else None}}}
    cond = {e: {'condicion': SITS[e % 4], 'etiqueta': 'Promovido(a)' if e % 4 == 0 else '',
                'asistencia': {'cobertura_completa': True, 'pct_asistencia': 90.0,
                               'pct_ausencia': 6.0, 'pct_excusa': 4.0}} for e in range(n)}
    colegio = {'nombre': 'Colegio REG3', 'regional': '10', 'distrito': '10-01', 'codigo_centro': '54321',
               'email': 'centro@reg3.edu.do', 'telefono': '809-555-0303', 'direccion': 'Av. REG3 #3',
               'director': 'Directora REG3', 'docente_titular': 'Maestra Titular REG3',
               'zona': 'urbana_marginal', 'sector': 'privado'}
    pdf = RP.generar_registro_primaria_desde_sistema(colegio, {'seccion': 'B', 'tanda': 'Vespertina'},
                                                     '2026-2027', est, cal, matriz(n, extra_dia), {},
                                                     grado, rec, cond)
    return pymupdf.open(stream=pdf, filetype='pdf')


def tinta(doc, pagina):
    out = []
    for b in doc[pagina - 1].get_text('dict')['blocks']:
        for l in b.get('lines', []):
            for s in l['spans']:
                if s['color'] == AZUL and s['text'].strip():
                    out.append(tuple(round(v, 1) for v in s['bbox']) + (s['text'].strip(),))
    return out


def dentro(span, celda, holgura=0.6):
    return span[0] >= celda[0] - holgura and span[2] <= celda[1] + holgura


def pag(grado, seccion, i=0):
    """Página (1-based) de una sección según el índice dinámico."""
    v = RP._construir_indice(grado)[seccion]
    return (v[i] if isinstance(v, list) else v) + 1


DOCS = {g: generar(g) for g in range(1, 7)}

print("\n=== 1 · PORTADA ===")
for g in range(1, 7):
    t = tinta(DOCS[g], pag(g, 'portada'))
    dy = 0 if g == 1 else 32
    sec = [s for s in t if s[4] == 'B']
    cen = [s for s in t if s[4] == 'Colegio REG3']
    check('REG3-01 %d: portada — centro y sección sobre SUS líneas (530.7 / 601.5 %+d)' % (g, dy),
          cen and 520 + dy < cen[0][3] < 530.7 + 2.6 + dy and sec and 590 + dy < sec[0][3] < 601.5 + 2.6 + dy,
          (cen, sec))

print("\n=== 2 · DATOS DEL CENTRO ===")
t = tinta(DOCS[1], pag(1, 'centro'))
textos = {s[4]: s for s in t}
check('REG3-02 centro: el texto queda SOBRE su línea (no tachado): correo, director, titular',
      textos['centro@reg3.edu.do'][3] < 119.3 + 2.6 and textos['Directora REG3'][3] < 339.0 + 2.6
      and textos['Maestra Titular REG3'][3] < 504.3 + 2.6, t[:3])
xs = [s for s in t if s[4] == 'X']
check('REG3-03 centro: X en "Urbana marginal" y "Privado" (círculos medidos)',
      any(abs((s[0] + s[2]) / 2 - 232.5) < 2 and abs((s[1] + s[3]) / 2 - 198.2) < 4 for s in xs)
      and any(abs((s[0] + s[2]) / 2 - 232.5) < 2 and abs((s[1] + s[3]) / 2 - 239.6) < 4 for s in xs), xs)

print("\n=== 3 · DATOS GENERALES DEL ESTUDIANTE (hoja doble) ===")
for g in (1, 2, 4):
    izq = [s for s in tinta(DOCS[g], pag(g, 'estudiantes', 0)) if s[1] > 162]
    der = [s for s in tinta(DOCS[g], pag(g, 'estudiantes', 1)) if s[1] > 162]
    fila1 = [s for s in izq if s[1] < 175.6]
    check('REG3-04 %d: izq — nacionalidad, X de Masculino, día/mes/año y edad en sus celdas' % g,
          any(s[4] == 'Dominicana' and dentro(s, RP.EST_IZQ['nacionalidad']) for s in fila1)
          and any(s[4] == 'X' and dentro(s, RP.EST_IZQ['masculino']) for s in fila1)
          and any(s[4] == '2018' or s[4] == str(2019 - g) for s in fila1 if dentro(s, RP.EST_IZQ['anio']))
          and any(dentro(s, RP.EST_IZQ['edad']) for s in fila1)
          and not any(s[4].startswith('Nombreextralargo') for s in izq), fila1)
    var = 1 if g == 1 else 2 if g == 2 else 3
    cols = RP.EST_DER[var]
    check('REG3-05 %d: der — la dirección no sale de su celda' % g,
          all(dentro(s, cols['direccion']) for s in der if s[4].startswith('Calle')), '')
    xs = sorted((s for s in der if s[4] == 'X'), key=lambda s: s[1])
    esperado = {1: ['promovido', 'reentrante', 'nuevo_ingreso', 'promovido'],
                2: ['promovido', 'repitente', 'reentrante', 'promovido'],
                3: ['promovido', 'repitente', 'reentrante', 'aplazado', 'promovido']}[var]
    check('REG3-06 %d: der — condición inicial en la columna de SU variante' % g,
          len(xs) == len(esperado) and all(dentro(s, cols[c]) for s, c in zip(xs, esperado)), xs)

print("\n=== 4 · ASISTENCIA SEMANAL ===")
pags_as = [p + 1 for p in RP._construir_indice(1)['asistencia']]
sep, octb = tinta(DOCS[1], pags_as[0]), tinta(DOCS[1], pags_as[1])
V = RP.ASIST_VERTICALES


def celda_de(fecha):
    semana, dia = RP._semana_y_dia(fecha)
    k = semana * 5 + dia
    return (V[k], V[k + 1])


fecha_row = [s for s in sep if 148 < s[1] < 162.7]
check('REG3-07 sep-2026: el 7 (lunes) en Lunes de la 2da semana; la 1ra semana vacía',
      any(s[4] == '7' and dentro(s, celda_de(date(2026, 9, 7))) for s in fecha_row)
      and not any(dentro(s, (67.0, 152.2)) for s in fecha_row), fecha_row[:3])
fr_oct = [s for s in octb if 148 < s[1] < 162.7]
check('REG3-08 oct-2026: el 1 (jueves) en Jueves de la 1ra semana y el 30 en Viernes de la 5ta',
      any(s[4] == '1' and dentro(s, celda_de(date(2026, 10, 1))) for s in fr_oct)
      and any(s[4] == '30' and dentro(s, celda_de(date(2026, 10, 30))) for s in fr_oct), fr_oct[:3])
fila1 = sorted((s for s in octb if 162.7 < s[1] < 175 and s[4] in 'PATE' and s[0] < 492), key=lambda s: s[0])
check('REG3-09 oct-2026: fila 1 = P A T E P… cada marca en la columna de su fecha',
      ''.join(s[4] for s in fila1[:5]) == 'PATEP' and dentro(fila1[0], celda_de(date(2026, 10, 1))), fila1[:5])
res = [s for s in octb if 162.7 < s[1] < 175 and s[0] > 492]
check('REG3-10 resumen del mes: Presente/Tardanza/Ausente/Excusa en sus 4 columnas',
      len(res) == 4 and all(dentro(s, c) for s, c in zip(sorted(res, key=lambda s: s[0]),
                                                         RP.ASIST_RESUMEN.values())), res)
tot = [s for s in octb if s[1] > 743]
check('REG3-11 fila "Total de asistencia" (P+T por día) dentro de su banda', tot and all(s[3] < 757 for s in tot), tot[:2])
check('REG3-12 meses cronológicos: formulario 1 = SEPTIEMBRE 2026, 10 = JUNIO 2027, 11-12 vírgenes',
      any('SEPTIEMBRE 2026' in s[4] for s in sep)
      and any('JUNIO 2027' in s[4] for s in tinta(DOCS[1], pags_as[9]))
      and not tinta(DOCS[1], pags_as[10]) and not tinta(DOCS[1], pags_as[11]), '')

print("\n=== 5 · CALIFICACIONES ===")
for g in (1, 2):
    izq = pag(g, 'calificaciones', 0) if False else RP._construir_indice(g)['calificaciones']['lengua espanola'][0] + 1
    der = izq + 1
    ti = [s for s in tinta(DOCS[g], izq) if 163 < s[1] < 176]
    td = [s for s in tinta(DOCS[g], der) if 163 < s[1] < 176]
    geo = RP.CAL_GEOMETRIA['A']
    check('REG3-13 %d (1ro-2do): C1 = 11 en P1..P4 y C2 = 12, cada uno en su columna' % g,
          all(any(s[4] == '11' and dentro(s, (x0, x1)) for s in ti) for _, x0, x1 in geo['izq'][1])
          and all(any(s[4] == '12' and dentro(s, (x0, x1)) for s in ti) for _, x0, x1 in geo['izq'][2]), ti)
    check('REG3-14 %d: C3, promedios 71/72/73, final del área 80 y recuperación 66 en la hoja DERECHA' % g,
          all(any(s[4] == '13' and dentro(s, (x0, x1)) for s in td) for _, x0, x1 in geo['der'][3])
          and any(s[4] == '80' and dentro(s, geo['final']) for s in td)
          and any(s[4] == '66' and dentro(s, geo['rec_final']) for s in td)
          and [s[4] for s in sorted((s for s in td if 316 < s[0] < 474), key=lambda s: s[0])] == ['71', '72', '73'],
          td)
for g in (3, 4, 5, 6):
    idx = RP._construir_indice(g)['calificaciones']['lengua espanola']
    ti = [s for s in tinta(DOCS[g], idx[0] + 1) if 163 < s[1] < 176]
    td = [s for s in tinta(DOCS[g], idx[1] + 1) if 163 < s[1] < 176]
    geo = RP.CAL_GEOMETRIA['B']
    rp1 = dict((k, (a, b)) for k, a, b in geo['izq'][1])['rp1']
    check('REG3-15 %d (3ro-6to): P1=11 y RP1=11.5 en columnas SEPARADAS' % g,
          any(s[4] == '11' and dentro(s, dict((k, (a, b)) for k, a, b in geo['izq'][1])['p1']) for s in ti)
          and any(s[4] == '11.5' and dentro(s, rp1) for s in ti), ti[:4])
    check('REG3-16 %d: C3 visible, final 80, rec. final 66 y especial 67; nada fuera de la hoja' % g,
          any(s[4] == '13' for s in td) and any(s[4] == '80' and dentro(s, geo['final']) for s in td)
          and any(s[4] == '67' and dentro(s, geo['rec_especial']) for s in td)
          and all(s[2] <= 612 for s in tinta(DOCS[g], idx[0] + 1) + tinta(DOCS[g], idx[1] + 1)), td)

print("\n=== 6 · ACTA ===")
for g in range(1, 7):
    a0, a1 = [p + 1 for p in RP._construir_indice(g)['acta'][:2]]
    cal = RP.ACTA_CAL[g]
    t0 = [s for s in tinta(DOCS[g], a0) if s[1] > 150]
    t1 = [s for s in tinta(DOCS[g], a1) if s[1] > 150]
    y0 = cal['filas'][0]
    f1 = [s for s in t0 if y0 < s[1] < y0 + cal['filas'][1]]
    le = cal['areas']['lengua espanola']
    check('REG3-17 %d: Acta — nombre en su columna (sin duplicar el Nº) y LE: final 80, rec 66' % g,
          any(s[4].startswith('Nombreextralargo1') and dentro(s, cal['nombre']) for s in f1)
          and any(s[4] == '80' and dentro(s, le['final']) for s in f1)
          and any(s[4] == '66' and dentro(s, le['rec_final']) for s in f1)
          and not any(s[4] == '1' and s[0] < 51 for s in f1), f1[:4])
    ex = cal['extras']
    g1 = [s for s in t1 if y0 < s[1] < y0 + cal['filas'][1]]
    check('REG3-18 %d: Acta — %% asistencia 90 | ausencia 6 | excusa 4 en sus columnas' % g,
          any(s[4] == '90' and dentro(s, ex['pct_asistencia']) for s in g1)
          and any(s[4] == '6' and dentro(s, ex['pct_ausencia']) for s in g1)
          and any(s[4] == '4' and dentro(s, ex['pct_excusa']) for s in g1), g1)
    xs = [s for s in t1 if s[4] == 'X']
    if cal['situacion']:
        filas_x = {int((((s[1] + s[3]) / 2) - y0) // cal['filas'][1]): s for s in xs}
        sit = cal['situacion']
        check('REG3-19 %d: Acta — situación CANÓNICA: Promovido / Aplazado / Reprobado; En proceso sin X' % g,
              dentro(filas_x.get(0, (0, 0, 0)), sit['promovido']) and dentro(filas_x.get(1, (0, 0, 0)), sit['aplazado'])
              and dentro(filas_x.get(2, (0, 0, 0)), sit['reprobado']) and 3 not in filas_x, filas_x)
    else:
        obs = [s for s in t1 if 'Promovido' in s[4]]
        check('REG3-19 %d: Acta 1ro-2do — la condición definitiva va en Observaciones (sin columnas)' % g,
              len(obs) == 2 and all(dentro(s, ex['observaciones']) for s in obs) and not xs, obs)
    cab = {s[4] for s in tinta(DOCS[g], a0) if s[1] < 75}
    check('REG3-20 %d: Acta — cabecera (centro, regional, distrito, grado, sección, año)' % g,
          {'Colegio REG3', '10', '10-01', '%d°' % g, 'B', '26', '27'} <= cab, cab)

print("\n=== 7 · CAPACIDAD: FAIL CLOSED ===")
try:
    generar(1, n=46)
    check('REG3-21 46 estudiantes en 45 filas → error explícito', False, 'generó el PDF')
except RE.RegistroExcedePlantilla as e:
    check('REG3-21 46 estudiantes en 45 filas → error explícito',
          e.detalle['motivo'] == 'ESTUDIANTES_EXCEDEN_PLANTILLA', e.detalle)
try:
    generar(1, extra_dia=(2026, 10, 3))         # sábado
    check('REG3-22 una asistencia en sábado (sin casilla) → error, no se esconde', False, 'generó')
except RE.RegistroExcedePlantilla as e:
    check('REG3-22 una asistencia en sábado (sin casilla) → error, no se esconde',
          e.detalle['motivo'] == 'DIA_FUERA_DEL_FORMULARIO' and e.detalle['fecha'] == '2026-10-03', e.detalle)
try:
    generar(1, n=45)
    check('REG3-23 45 estudiantes caben: se imprime', True)
except Exception as e:  # noqa: BLE001
    check('REG3-23 45 estudiantes caben: se imprime', False, e)

print("\n=== 8 · app.py: DATOS CANÓNICOS (base aislada) ===")
import app as APP  # noqa: E402
import calculo_primaria as CP  # noqa: E402
import registro_asistencia as RA  # noqa: E402

M.Base.metadata.create_all(bind=engine)
db = SessionLocal()
col = M.Colegio(nombre='REG3', codigo='reg3', activo=True)
db.add(col)
db.flush()
ano = M.AnoEscolar(colegio_id=col.id, nombre='2026-2027', activo=True, cerrado=False,
                   fecha_inicio=date(2026, 9, 7), fecha_fin=date(2027, 6, 25))
grd = M.Grado(colegio_id=col.id, nombre='4to Primaria', nivel='primaria', orden=4, activo=True)
cfg = M.ConfiguracionColegio(colegio_id=col.id, nombre='REG3', zona='rural', sector='publico')
db.add_all([ano, grd, cfg])
db.flush()
curso = M.Curso(colegio_id=col.id, nombre='A', grado_id=grd.id, ano_escolar_id=ano.id, activo=True)
prof = M.Usuario(colegio_id=col.id, username='reg3_p', password_hash='x', nombre='Ma', apellido='Estra',
                 role='profesor', activo=True, must_change_password=False, token_version=0)
usr = M.Usuario(colegio_id=col.id, username='reg3_d', password_hash='x', nombre='Di', apellido='R',
                role='direccion', activo=True, must_change_password=False, token_version=0)
le = M.Asignatura(colegio_id=col.id, nombre='Lengua Española', codigo='LE', area='X', activo=True)
db.add_all([curso, prof, usr, le])
db.flush()
e1 = M.Estudiante(colegio_id=col.id, matricula='P3-1', nombre='Ana', apellido='Pérez', curso_id=curso.id,
                  activo=True, no_lista=1, nacionalidad='Haitiana', direccion='Calle Uno',
                  condicion_entrada='reingreso')
db.add_all([e1, M.AsignacionProfesor(colegio_id=col.id, profesor_id=prof.id, curso_id=curso.id,
                                     asignatura_id=le.id, ano_escolar_id=ano.id, activo=True)])
db.flush()
for n_c, v in ((1, 80), (2, 90), (3, 70)):
    db.add(M.CalificacionPrimaria(colegio_id=col.id, estudiante_id=e1.id, asignatura_id=le.id,
                                  ano_escolar_id=ano.id, competencia_numero=n_c, p1=v, p2=v, p3=v, p4=v))
db.add(M.Asistencia(colegio_id=col.id, estudiante_id=e1.id, curso_id=curso.id, fecha=date(2026, 10, 14),
                    estado='presente'))
db.commit()
antes = (db.query(M.Estudiante).count(), db.query(M.Asistencia).count(),
         db.query(M.CalificacionPrimaria).count())
info, filas = {}, [{'id': e1.id}]
cpa = {'Lengua Española': {0: {c: {'p1': v} for c, v in ((1, 80), (2, 90), (3, 70))}}}
APP._enriquecer_registro_primaria(db, usr, curso, cfg, [e1], filas, info, cpa)
objs = db.query(M.CalificacionPrimaria).filter_by(estudiante_id=e1.id).order_by(
    M.CalificacionPrimaria.competencia_numero).all()
check('REG3-24 app.py envía nacionalidad, dirección, condición, zona y sector',
      filas[0]['nacionalidad'] == 'Haitiana' and filas[0]['direccion'] == 'Calle Uno'
      and filas[0]['condicion_entrada'] == 'reingreso' and info == {'zona': 'rural', 'sector': 'publico'},
      (filas, info))
check('REG3-25 promedio por competencia y final del área = funciones del motor (cf_competencia / cf_area)',
      cpa['Lengua Española'][0][1]['cf_oficial'] == CP.cf_competencia(objs[0])
      and cpa['Lengua Española'][0]['_area']['cf'] == CP.cf_area(objs)[1] == 80, cpa)
rec, conds = APP._datos_acta_primaria(db, usr, [e1], cpa)
c0 = conds.get(0) or {}
check('REG3-26 el Acta recibe la condición CANÓNICA (código) y la asistencia anual canónica',
      c0.get('condicion') in ('PROMOVIDO', 'APLAZADO', 'REPROBADO', 'EN_PROCESO')
      and 'asistencia' in c0 and c0['asistencia'].get('cobertura_completa') is False
      and c0['asistencia'].get('pct_asistencia') is None, c0)
check('REG3-27 todo es SOLO LECTURA (estudiantes, asistencias y notas sin cambios)',
      antes == (db.query(M.Estudiante).count(), db.query(M.Asistencia).count(),
                db.query(M.CalificacionPrimaria).count()), '')

print("\n=== 9 · BACKFILL: SEPTIEMBRE DIGITADO DESPUÉS (REG-1 intacto) ===")
db.add(M.Asistencia(colegio_id=col.id, estudiante_id=e1.id, curso_id=curso.id, fecha=date(2026, 9, 15),
                    estado='ausente'))
db.commit()
mz = RA.build_asistencia_registro(db, curso.id, estudiantes=[e1])
pdf = RP.generar_registro_primaria_desde_sistema(
    {'nombre': 'REG3'}, {'seccion': 'A'}, '2026-2027',
    [{'no_lista': 1, 'nombre': 'Ana Pérez', 'sexo': 'F', 'fecha_nacimiento': date(2017, 1, 1)}],
    {}, mz, {}, 4)
d = pymupdf.open(stream=pdf, filetype='pdf')
pags4 = [p + 1 for p in RP._construir_indice(4)['asistencia']]
s4 = tinta(d, pags4[0])
a15 = [s for s in s4 if s[4] == 'A' and 162.7 < s[1] < 175.6]
check('REG3-28 el 15-sep (martes) digitado después aparece en SEPTIEMBRE, en Martes de la 3ra semana',
      any('SEPTIEMBRE 2026' in s[4] for s in s4) and a15 and dentro(a15[0], celda_de(date(2026, 9, 15))), a15)
check('REG3-29 octubre no se desplaza: su marca del 14 (miércoles) sigue en el formulario 2',
      any(s[4] == 'P' and dentro(s, celda_de(date(2026, 10, 14))) for s in tinta(d, pags4[1])), '')
db.close()

ok = sum(1 for _, r in RESULTADOS if r)
print('\nRESULTADO REG-3: %d PASARON / %d FALLARON' % (ok, len(RESULTADOS) - ok))
sys.exit(0 if ok == len(RESULTADOS) else 1)
