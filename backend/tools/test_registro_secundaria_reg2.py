# -*- coding: utf-8 -*-
"""
EducaOne — REG-2: calibración del Registro Escolar de Secundaria (1ro-6to).

Comprueba con datos SINTÉTICOS marcadores que cada dato cae en su página, fila
y casilla del template oficial. La verificación es por POSICIÓN de la tinta
azul del overlay (pymupdf), no solo por "el texto está en el PDF":

    · portada 1ro-3ro intacta; portada 4to-6to (pág 1 y 2) en sus líneas;
    · datos del estudiante: cédula / RNE / residencia dentro de su celda;
    · condición inicial: tabla de 1ro y tabla distinta de 2do-6to;
    · calificaciones: mapa 1ro-3ro y mapa EXPLÍCITO 4to-6to (Salida Optativa
      intercalada), con un marcador distinto por asignatura;
    · Salida Optativa: spreads por slot, asistencia traducida, rótulo, docente;
    · asistencia por materia y docente en cada hoja;
    · más días que columnas / más estudiantes que filas → error (422);
    · Acta final por ciclo; Completiva; profesor de la asignatura.

Base temporal aislada para la parte que toca app.py. Nunca producción.

Uso:
    cd backend
    python tools/test_registro_secundaria_reg2.py
"""
import os
import sys
from datetime import date

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(BK, "tools"))

from test_utils import aislar_base_de_datos  # noqa: E402

TMP = aislar_base_de_datos('reg2_secundaria')

from database import engine, SessionLocal  # noqa: E402
from test_utils import verificar_engine_aislado  # noqa: E402

verificar_engine_aislado(engine, TMP)

import pymupdf  # noqa: E402

import models as M  # noqa: E402
import registro_escolar as RE  # noqa: E402

AZUL = 0x0000b3
RESULTADOS = []


def check(nombre, ok, detalle=''):
    RESULTADOS.append((nombre, bool(ok)))
    print(('  OK  ' if ok else '  FALLA ') + nombre + ('' if ok else '  -> ' + str(detalle)[:300]))


# ─────────────────────────── datos marcadores ───────────────────────────
MESES = [(2026, 9, 'septiembre'), (2026, 10, 'octubre'), (2026, 11, 'noviembre'),
         (2026, 12, 'diciembre'), (2027, 1, 'enero'), (2027, 2, 'febrero'), (2027, 3, 'marzo'),
         (2027, 4, 'abril'), (2027, 5, 'mayo'), (2027, 6, 'junio')]
COD = ['P', 'A', 'T', 'E', 'P']
CONDS = ['promovido', 'repitente', 'reingreso', 'aplazado', 'nuevo']


def matriz(n_est, n_dias):
    out = []
    for pos, (y, m, nombre) in enumerate(MESES):
        filas = []
        for e in range(n_est):
            vals = [COD[(e + d) % 5] for d in range(n_dias)]
            filas.append({'valores': vals, 'presentes': vals.count('P'), 'porcentaje': 90.0})
        out.append({'mes': nombre, 'mes_num': m, 'anio': y, 'posicion': pos,
                    'dias': list(range(1, n_dias + 1)), 'filas': filas, 'no_impartidas': {}})
    return out


def califs(n_est, base, decimal=False, con_extra=True):
    """Marcador: la competencia c vale base + c (+0.5 en Salida Optativa)."""
    d = {}
    for e in range(n_est):
        v = {c: base + c + (0.5 if decimal else 0) for c in (1, 2, 3, 4)}
        comp = {c: {'p1': v[c], 'p2': v[c], 'p3': v[c], 'p4': v[c]} for c in (1, 2, 3, 4)}
        cf = 60 + e if e < 2 else 80
        ev = None
        if con_extra and e < 2:
            ev = {'cf_original': cf, 'cec': 80, 'completiva_final': 66 + e,
                  'ceex': 75, 'extraordinaria_final': 72, 'ce': None, 'especial_final': None,
                  'condicion_final': 'aprobado_extraordinaria', 'nota_final': 72,
                  'fase_pendiente': None}
        d[e] = {'competencias': comp, 'promedios_competencia': v, 'cf': cf, 'cf_exacto': cf,
                'evaluacion_extra': ev}
    return d


def estudiantes(n):
    return [{'no_lista': i + 1, 'nombre': 'N%d A%d' % (i + 1, i + 1),
             'apellidos': 'Apellidoextralargo%d Segundoapellido' % (i + 1),
             'nombres': 'Nombre%d Compuesto' % (i + 1),
             'sexo': 'F' if i % 2 else 'M', 'fecha_nacimiento': date(2011, 1, 1),
             'cedula': '402-%07d-1' % i, 'rne': 'RNE%010d' % i,
             'direccion': 'Calle %d No. 25, Residencial Los Jardines del Norte, Santo Domingo Este' % i,
             'email': 'estudiante%d@correo-largo-ejemplo.edu.do' % (i + 1),
             'condicion_entrada': CONDS[i % 5],
             'situacion_final': ({'promovido': True, 'reprobado': False} if i % 3 == 0 else
                                 {'promovido': False, 'reprobado': True} if i % 3 == 1 else None),
             'activo': True} for i in range(n)]


def generar(grado, n_est=8, n_dias=20, dias_4m=10, sin_finales=False):
    asigs = RE.ASIGNATURAS_CICLO_2 if grado >= 4 else RE.ASIGNATURAS_CICLO_1
    data = {}
    for a_idx, a in enumerate(asigs):
        if a == 'Salida Optativa':
            continue
        data[a] = {'docente': 'Prof %d' % a_idx,
                   'asistencia_matriz': matriz(n_est, dias_4m if a_idx >= 6 else n_dias),
                   'calificaciones': {} if sin_finales else califs(n_est, 10 * (a_idx + 1))}
    curso = {'seccion': 'B', 'tanda': 'matutina', 'grado': '%d Secundaria' % grado}
    so_data = so_asis = None
    if grado >= 4:
        curso.update(salida_optativa='Humanidades y Lenguas Modernas', salida_optativa_codigo='HLM')
        so_data = {0: {'docente': 'Prof SO-LE', 'calificaciones': califs(n_est, 70, True)},
                   2: {'docente': 'Prof SO-IN', 'calificaciones': califs(n_est, 80, True)}}
        so_asis = {0: {'meses': matriz(n_est, n_dias), 'docente': 'Prof SO-LE', 'slot': 0,
                       'salida_nombre': 'Humanidades y Lenguas Modernas',
                       'componente_nombre': 'Apreciación y Producción Literarias'},
                   1: {'meses': matriz(n_est, n_dias), 'docente': 'Prof SO-IN', 'slot': 2,
                       'salida_nombre': 'Humanidades y Lenguas Modernas',
                       'componente_nombre': 'Manejo de la Información en Inglés'}}
    colegio = {'nombre': 'Colegio REG2', 'codigo_centro': '12345', 'regional': '10',
               'distrito': '10-01', 'director': 'Directora REG2', 'coordinador': 'Titular REG2',
               'sector': 'privado', 'zona': 'urbana', 'tanda_operacion': 'matutina'}
    pdf = RE.generar_registro_desde_sistema(colegio, curso, '2026-2027', estudiantes(n_est), data,
                                            grado, salida_optativa_data=so_data,
                                            salida_optativa_asistencia=so_asis)
    return pymupdf.open(stream=pdf, filetype='pdf')


def tinta(doc, pagina):
    """[(x0, y0, x1, y1, texto)] de los spans azules de la página (1-based)."""
    out = []
    for b in doc[pagina - 1].get_text('dict')['blocks']:
        for l in b.get('lines', []):
            for s in l['spans']:
                if s['color'] == AZUL and s['text'].strip():
                    out.append(tuple(round(v, 1) for v in s['bbox']) + (s['text'].strip(),))
    return out


def dentro(span, x0, x1, holgura=0.6):
    return span[0] >= x0 - holgura and span[2] <= x1 + holgura


DOCS = {g: generar(g) for g in range(1, 7)}

print("\n=== 1 · PORTADA ===")
for g in (1, 2, 3):
    t = tinta(DOCS[g], 1)
    anio = [s for s in t if s[4] in ('26', '27')]
    sec = [s for s in t if s[4] == 'B']
    check('REG2-01 %d: portada pág 1 — año sobre "20____" (línea base 670) y sección en su línea'
          % g, len(anio) == 2 and all(650 < s[3] < 676 for s in anio)
          and sec and 690 < sec[0][3] < 716 and not any('Humanidades' in s[4] for s in t), t)
for g in (4, 5, 6):
    t = tinta(DOCS[g], 1)
    anio = [s for s in t if s[4] in ('26', '27')]
    sec = [s for s in t if s[4] == 'B']
    sal = [s for s in t if 'Humanidades' in s[4]]
    check('REG2-02 %d: portada pág 1 — año (631-650), sección (670-691), salida en su línea' % g,
          len(anio) == 2 and all(630 < s[1] and s[3] < 650 for s in anio)
          and sec and 670 < sec[0][1] and sec[0][3] < 691
          and sal and dentro(sal[0], 208.1, 360.8) and 710 < sal[0][1] and sal[0][3] < 731, t)
    t2 = tinta(DOCS[g], 2)
    check('REG2-03 %d: portadilla pág 2 — año, sección y salida dentro de sus líneas' % g,
          any(s[4] == 'B' and dentro(s, 137.7, 271.8) for s in t2)
          and any('Humanidades' in s[4] and dentro(s, 185.8, 540.0) for s in t2)
          and len([s for s in t2 if s[4] in ('26', '27')]) == 2, t2)

print("\n=== 2 · DATOS DEL ESTUDIANTE (pág 11) ===")
for g in (1, 4):
    t = [s for s in tinta(DOCS[g], 11) if s[1] > 180]
    ced = [s for s in t if s[4].startswith('402-')]
    rne = [s for s in t if s[4].startswith('RNE')]
    res = [s for s in t if s[4].startswith('Calle')]
    check('REG2-04 %d: cédula, RNE y residencia dentro de SU celda (sin invadir la vecina)' % g,
          ced and rne and res and all(dentro(s, 239.0, 318.6) for s in ced)
          and all(dentro(s, 318.6, 398.3) for s in rne)
          and all(dentro(s, 398.3, 575.5) for s in res), (ced[:1], rne[:1], res[:1]))

print("\n=== 3 · CONDICIÓN INICIAL (pág 12) ===")
x1 = [s for s in tinta(DOCS[1], 12) if s[4] == 'X']
check('REG2-05 1ro: X en Promovido / Repitente / Reingreso de su tabla (sin Aplazado)',
      any(dentro(s, 351.5, 427.0) for s in x1) and any(dentro(s, 427.0, 502.7) for s in x1)
      and any(dentro(s, 502.7, 578.4) for s in x1) and len(x1) == 7, x1)
COLS_2A6 = {'promovido': (241.2, 262.4), 'repitente': (262.4, 283.7),
            'reingreso': (283.7, 304.9), 'aplazado': (304.9, 326.2)}
for g in (2, 3, 4, 5, 6):
    xs = sorted((s for s in tinta(DOCS[g], 12) if s[4] == 'X'), key=lambda s: s[1])
    esperado = ['promovido', 'repitente', 'reingreso', 'aplazado', 'promovido',
                'promovido', 'repitente', 'reingreso']
    ok = len(xs) == 8 and all(dentro(s, *COLS_2A6[c]) for s, c in zip(xs, esperado))
    check('REG2-06 %d: X en su columna de la tabla 2do-6to (incluye Aplazado), nunca en las '
          'de asignaturas pendientes' % g, ok and all(s[2] < 326.2 for s in xs), xs)

print("\n=== 4 · CALIFICACIONES: MAPA DE PÁGINAS ===")


def marcadores(doc, pagina):
    return {s[4] for s in tinta(doc, pagina) if s[1] > 180}


for g in (1, 2, 3, 4, 5, 6):
    paginas = RE.GRADO_CONFIG[g]['calificaciones_paginas']
    malos = []
    for a_idx, pg in enumerate(paginas):
        esperado = {str(10 * (a_idx + 1) + c) for c in (1, 2)}
        ajenos = {str(10 * (b + 1) + 1) for b in range(9) if b != a_idx}
        m = marcadores(DOCS[g], pg)
        if not esperado <= m or m & ajenos:
            malos.append((a_idx, pg, sorted(m)[:6]))
    check('REG2-07 %d: cada asignatura en SU spread y ninguna nota ajena' % g, not malos, malos)
check('REG2-08 mapa 1ro-3ro = el de siempre (131 + 2·i)',
      all(RE.GRADO_CONFIG[g]['calificaciones_paginas'] == [131 + 2 * i for i in range(9)]
          for g in (1, 2, 3)), '')
check('REG2-09 mapa 4to-6to explícito: Inglés 185 (no 181), FIHR 207',
      all(RE.GRADO_CONFIG[g]['calificaciones_paginas'] ==
          [179, 185, 189, 191, 195, 199, 203, 205, 207] for g in (4, 5, 6)), '')
for g in (4, 5, 6):
    d = DOCS[g]
    check('REG2-10 %d: Salida Optativa slot 0 → pág 181, slot 2 → pág 187 (marcadores .5)' % g,
          '71.5' in marcadores(d, 181) and '81.5' in marcadores(d, 187)
          and '81.5' not in marcadores(d, 181), '')
    check('REG2-11 %d: spreads de Salida Optativa sin componente quedan vírgenes' % g,
          all(not tinta(d, p) for p in (183, 184, 193, 194, 197, 198, 201, 202)), '')

print("\n=== 5 · ASISTENCIA ===")
for g in (1, 4):
    d = DOCS[g]
    t17 = tinta(d, 17)
    t18 = tinta(d, 18)
    check('REG2-12 %d: Lengua hoja 1 = septiembre + octubre, con docente' % g,
          {'septiembre', 'octubre'} <= {s[4] for s in t17} and any(s[4] == 'Prof 0' for s in t17), '')
    check('REG2-13 %d: el docente también en la hoja 2 (cada hoja tiene su campo DOCENTE)' % g,
          any(s[4] == 'Prof 0' for s in t18), '')
    fila1 = sorted((s for s in t17 if 180 < s[1] < 192 and s[0] < 290 and s[4] in 'PATE'),
                   key=lambda s: s[0])
    check('REG2-14 %d: fila 1 de septiembre = P A T E P… en orden' % g,
          ''.join(s[4] for s in fila1[:5]) == 'PATEP', [s[4] for s in fila1[:6]])
for g in (4, 5, 6):
    d = DOCS[g]
    t56, t61 = tinta(d, 56), tinta(d, 61)
    check('REG2-15 %d: Salida Optativa (pág 56): rótulo, docente, meses y FILAS impresas' % g,
          any('Apreciación' in s[4] for s in t56) and any(s[4] == 'Prof SO-LE' for s in t56)
          and 'septiembre' in {s[4] for s in t56} and sum(1 for s in t56 if s[4] in 'PATE') > 100, '')
    check('REG2-16 %d: 2do componente (pág 61) con su docente y su asistencia' % g,
          any(s[4] == 'Prof SO-IN' for s in t61) and sum(1 for s in t61 if s[4] in 'PATE') > 100, '')

print("\n=== 6 · CAPACIDAD: FAIL CLOSED ===")
for etiqueta, kw, motivo in (('22 días en hoja de 21', {'n_dias': 22}, 'DIAS_EXCEDEN_PLANTILLA'),
                             ('11 días en hoja compacta de 10', {'dias_4m': 11}, 'DIAS_EXCEDEN_PLANTILLA'),
                             # REG-43: 1ro admite 41-43 con su plantilla ampliada; el
                             # límite que no se puede pasar sin recortar es 44.
                             ('44 estudiantes en 1ro (máximo 43)', {'n_est': 44}, 'ESTUDIANTES_EXCEDEN_PLANTILLA')):
    try:
        generar(1, **kw)
        check('REG2-17 %s → error explícito' % etiqueta, False, 'generó el PDF')
    except RE.RegistroExcedePlantilla as e:
        check('REG2-17 %s → error explícito' % etiqueta, e.detalle['motivo'] == motivo, e.detalle)
try:
    generar(1, n_dias=21, dias_4m=10, n_est=40)
    check('REG2-18 21 días / 10 compactos / 40 estudiantes caben: se imprime', True)
except Exception as e:  # noqa: BLE001
    check('REG2-18 21 días / 10 compactos / 40 estudiantes caben: se imprime', False, e)

print("\n=== 7 · ACTA FINAL ===")
ACTA = {1: (159, {'apellidos': (48.7, 190.7), 'nombres': (190.7, 332.7), 'le': (332.7, 413.6)},
            {'mat': (49.2, 128.7), 'prom': (526.0, 550.3), 'repr': (550.3, 574.5)}),
        4: (225, {'apellidos': (48.7, 167.3), 'nombres': (167.3, 303.8), 'le': (303.8, 371.7),
                  'mat': (507.4, 575.2)},
            {'so1': (392.3, 461.0), 'so2': (461.0, 529.7), 'prom': (529.7, 553.9),
             'repr': (553.9, 574.8)})}
for g in (1, 2, 3, 4, 5, 6):
    base = 1 if g <= 3 else 4
    pg, izq, der = ACTA[base]
    ti = [s for s in tinta(DOCS[g], pg) if s[1] > 180]
    td = [s for s in tinta(DOCS[g], pg + 1) if s[1] > 180]
    fila1_i = [s for s in ti if s[1] < 194]
    fila1_d = [s for s in td if s[1] < 194]
    ok_nombres = (any(s[4].startswith('Apellidoextralargo1') and dentro(s, *izq['apellidos'])
                      for s in fila1_i)
                  and any(s[4].startswith('Nombre1') and dentro(s, *izq['nombres']) for s in fila1_i))
    le = sorted((s for s in fila1_i if dentro(s, *izq['le'])), key=lambda s: s[0])
    check('REG2-19 %d: Acta — apellidos y nombres en su columna; LE = 60 | 66 | 72' % g,
          ok_nombres and [s[4] for s in le] == ['60', '66', '72'], (fila1_i[:4], le))
    x = [s for s in td if s[4] == 'X']
    fila2_x = [s for s in x if 194 < s[1] < 208]
    check('REG2-20 %d: Acta — X de Promovido en fila 1 y de Reprobado en fila 2' % g,
          any(dentro(s, *der['prom']) for s in x if s[1] < 194)
          and any(dentro(s, *der['repr']) for s in fila2_x), x[:4])
    if base == 4:
        so1 = sorted((s for s in fila1_d if dentro(s, *der['so1'])), key=lambda s: s[0])
        so2 = sorted((s for s in fila1_d if dentro(s, *der['so2'])), key=lambda s: s[0])
        check('REG2-21 %d: Acta — Salida Optativa 1 y 2 en sus columnas' % g,
              [s[4] for s in so1] == ['60', '66', '72'] and [s[4] for s in so2] == ['60', '66', '72'],
              (so1, so2))
cab = {s[4] for s in tinta(DOCS[4], 225) if s[1] < 105}
check('REG2-22 Acta 4to: cabecera (centro, código, grado, sección, salida, año)',
      {'Colegio REG2', '12345', 'B', '2026-2027', 'Humanidades y Lenguas Modernas'} <= cab, cab)
virgen_sin = RE.generar_registro_desde_sistema(
    {'nombre': 'C'}, {'seccion': 'A'}, '2026-2027',
    [dict(e, situacion_final=None) for e in estudiantes(3)], {}, 2)
check('REG2-24 sin notas ni situación, Acta (159-160) idéntica al template',
      not tinta(pymupdf.open(stream=virgen_sin, filetype='pdf'), 159)
      and not tinta(pymupdf.open(stream=virgen_sin, filetype='pdf'), 160), '')

print("\n=== 8 · COMPLETIVA Y PROFESOR ===")
for g, pg_le, so_pags in ((1, 150, ()), (4, 210, (211, 214))):
    t = tinta(DOCS[g], pg_le)
    check('REG2-25 %d: Completiva de Lengua (pág %d) con su docente y la CF 60' % (g, pg_le),
          any(s[4] == 'Prof 0' for s in t) and any(s[4] == '60' for s in t if s[1] > 175), '')
    for p in so_pags:
        t = tinta(DOCS[g], p)
        check('REG2-26 %d: Completiva de Salida Optativa (pág %d) con SU docente' % (g, p),
              any(s[4] in ('Prof SO-LE', 'Prof SO-IN') for s in t), '')
t8 = {s[4] for s in tinta(DOCS[4], 8)}
check('REG2-27 Datos del centro: docente encargado = el titular que envía app.py',
      'Titular REG2' in t8 and 'Directora REG2' in t8, t8)
t32 = {s[4] for s in tinta(DOCS[4], 32)}
check('REG2-28 cada asignatura con SU profesor (Matemática → Prof 3)', 'Prof 3' in t32, '')

print("\n=== 9 · app.py: DATOS Y 422 (base aislada) ===")
import app as APP  # noqa: E402

M.Base.metadata.create_all(bind=engine)
db = SessionLocal()
col = M.Colegio(nombre='REG2', codigo='reg2', activo=True)
db.add(col)
db.flush()
ano = M.AnoEscolar(colegio_id=col.id, nombre='2026-2027', activo=True, cerrado=False,
                   fecha_inicio=date(2026, 9, 7), fecha_fin=date(2027, 6, 25))
grd = M.Grado(colegio_id=col.id, nombre='4to Secundaria', nivel='secundaria', orden=4, activo=True)
db.add_all([ano, grd])
db.flush()
curso = M.Curso(colegio_id=col.id, nombre='A', grado_id=grd.id, ano_escolar_id=ano.id,
                activo=True, salida_optativa_codigo='HLM')
usr = M.Usuario(colegio_id=col.id, username='reg2_dir', password_hash='x', nombre='D',
                role='direccion', activo=True, must_change_password=False, token_version=0)
db.add_all([curso, usr])
db.flush()
e1 = M.Estudiante(colegio_id=col.id, matricula='R2-1', nombre='Ana María', apellido='Pérez Gómez',
                  email='ana@x.do', curso_id=curso.id, activo=True, no_lista=1)
db.add(e1)
db.commit()
antes = (db.query(M.Estudiante).count(), db.query(M.Asistencia).count(),
         db.query(M.CalificacionSecundaria).count())
info, filas = {}, [{'id': e1.id}]
APP._enriquecer_registro_secundaria(db, usr, curso, ano, info, [e1], filas)
check('REG2-29 app.py envía apellidos, nombres y correo del Estudiante',
      filas[0]['apellidos'] == 'Pérez Gómez' and filas[0]['nombres'] == 'Ana María'
      and filas[0]['email'] == 'ana@x.do', filas)
check('REG2-30 app.py envía la Salida Optativa del curso (nombre oficial del catálogo)',
      info.get('salida_optativa') == 'Humanidades y Lenguas Modernas'
      and info.get('salida_optativa_codigo') == 'HLM', info)
check('REG2-31 sin notas, la situación A2 no marca ni promovido ni reprobado',
      not (filas[0]['situacion_final'] or {}).get('promovido')
      and not (filas[0]['situacion_final'] or {}).get('reprobado'), filas[0]['situacion_final'])
check('REG2-32 enriquecer es SOLO LECTURA (estudiantes/asistencias/notas sin cambios)',
      antes == (db.query(M.Estudiante).count(), db.query(M.Asistencia).count(),
                db.query(M.CalificacionSecundaria).count()), '')
r = APP._respuesta_conflicto_espec(RE.RegistroExcedePlantilla({'motivo': 'DIAS_EXCEDEN_PLANTILLA'}))
check('REG2-33 la API responde 422 a un Registro que no cabe', r is not None and r.status_code == 422, r)

print("\n=== 10 · BORRADOR = OFICIAL EN SALIDA OPTATIVA (4to) ===")
import asyncio  # noqa: E402

prof = M.Usuario(colegio_id=col.id, username='reg2_prof', password_hash='x', nombre='Profe',
                 apellido='SO', role='profesor', activo=True, must_change_password=False,
                 token_version=0)
a_le = M.Asignatura(colegio_id=col.id, nombre='Apreciación y Producción Literarias',
                    codigo='APL', area='X', activo=True)
a_in = M.Asignatura(colegio_id=col.id, nombre='Manejo de la Información en Inglés',
                    codigo='MII', area='X', activo=True)
db.add_all([prof, a_le, a_in])
db.flush()
for codigo, asig in (('HLM-LE-4', a_le), ('HLM-IN-4', a_in)):
    db.add(M.CursoComponenteOptativo(colegio_id=col.id, curso_id=curso.id, ano_escolar_id=ano.id,
                                     componente_codigo=codigo, asignatura_id=asig.id, activo=True))
    db.add(M.AsignacionProfesor(colegio_id=col.id, profesor_id=prof.id, curso_id=curso.id,
                                asignatura_id=asig.id, ano_escolar_id=ano.id, activo=True))
    for n in (1, 2, 3, 4):
        db.add(M.CalificacionSecundaria(colegio_id=col.id, estudiante_id=e1.id,
                                        asignatura_id=asig.id, ano_escolar_id=ano.id,
                                        competencia_numero=n, p1=77, p2=77, p3=77, p4=77))
    db.add(M.Asistencia(colegio_id=col.id, estudiante_id=e1.id, curso_id=curso.id,
                        asignatura_id=asig.id, fecha=date(2026, 9, 15), estado='presente'))
db.commit()

_original = RE.generar_registro_desde_sistema
_capturado = {}


def _espia(*a, **kw):
    _capturado.update(kw)
    _capturado['pdf'] = _original(*a, **kw)
    return _capturado['pdf']


class _Req:
    query_params = {}


RE.generar_registro_desde_sistema = _espia
try:
    resp = asyncio.run(APP.preview_pdf_secundaria(curso.id, _Req(), db=db, current_user=usr))
finally:
    RE.generar_registro_desde_sistema = _original

ests_curso = db.query(M.Estudiante).filter_by(curso_id=curso.id, activo=True).order_by(
    M.Estudiante.no_lista).all()
oficial_notas = APP._cargar_salida_optativa_registro(db, usr, curso, ests_curso)
oficial_asis = APP._cargar_salida_optativa_asistencia(db, usr, curso, ests_curso)
check('REG2-34 el borrador se genera (200) con marca BORRADOR',
      getattr(resp, 'status_code', None) == 200 and _capturado.get('marca_borrador') is True,
      getattr(resp, 'status_code', None))
so_n = _capturado.get('salida_optativa_data') or {}
so_a = _capturado.get('salida_optativa_asistencia') or {}
check('REG2-35 el borrador recibe salida_optativa_data (slots 0 y 2, igual que el oficial)',
      sorted(so_n) == [0, 2] == sorted(oficial_notas)
      and so_n[0]['docente'] == oficial_notas[0]['docente'] == 'Profe SO', (sorted(so_n), so_n.get(0)))
check('REG2-36 el borrador recibe salida_optativa_asistencia (bloques 0 y 1, igual que el oficial)',
      sorted(so_a) == [0, 1] == sorted(oficial_asis)
      and so_a[0]['componente_nombre'] == oficial_asis[0]['componente_nombre'], sorted(so_a))
d_b = pymupdf.open(stream=_capturado['pdf'], filetype='pdf')
check('REG2-37 en el borrador las páginas de Salida Optativa NO quedan vacías '
      '(spread 181, Completiva 211, asistencia 56)',
      '77' in {s[4] for s in tinta(d_b, 181)} and tinta(d_b, 211)
      and any(s[4] == 'P' for s in tinta(d_b, 56))
      and any('Apreciación' in s[4] for s in tinta(d_b, 56)), '')
db.close()

ok = sum(1 for _, r in RESULTADOS if r)
print('\nRESULTADO REG-2: %d PASARON / %d FALLARON' % (ok, len(RESULTADOS) - ok))
sys.exit(0 if ok == len(RESULTADOS) else 1)
