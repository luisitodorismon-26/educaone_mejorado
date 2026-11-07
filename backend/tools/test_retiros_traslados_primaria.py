# -*- coding: utf-8 -*-
"""TRAS-1 · Registro de PRIMARIA con retiros, traslados y huecos de numeración.

Prueba del GENERADOR (registro_primaria) con datos sintéticos en memoria: no
abre ninguna base. Comprueba que:

  * la marca de permanencia ([RET …], [TRAS a …], [INC de …]) va en la casilla
    de dirección y quien salió no lleva X de condición;
  * la leyenda de marcas (hoja de datos) y la de «-» = No aplica (asistencia)
    aparecen en el margen superior SOLO si hay movimientos;
  * una fila de hueco de numeración queda en blanco;
  * sin movimientos, el documento no cambia (sin leyendas).

Uso (desde backend/):  python tools/test_retiros_traslados_primaria.py [carpeta_salida]
"""
import os
import sys
import tempfile
from datetime import date, timedelta

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
OUT = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix='tras_primaria_')
os.makedirs(OUT, exist_ok=True)
import pymupdf  # noqa: E402
import registro_primaria as RP  # noqa: E402
import registro_escolar as RE  # noqa: E402

RES = []


def check(nombre, ok, detalle=''):
    RES.append((nombre, bool(ok)))
    print(('  PASA  ' if ok else '  FALLA ') + nombre + ('' if ok else '  -> ' + str(detalle)[:400]))


MESES = [(2026, 9, 'Septiembre'), (2026, 10, 'Octubre'), (2026, 11, 'Noviembre')]
AREAS = ['Lengua Española', 'Matemática']


def habiles(y, m, desde=1):
    d, out = date(y, m, desde), []
    while d.month == m:
        if d.weekday() < 5:
            out.append(d.day)
        d += timedelta(days=1)
    return out


def matriz(filas_por_est):
    """`filas_por_est[i](fecha) -> código` para cada estudiante."""
    out = []
    for pos, (y, m, nombre) in enumerate(MESES):
        dias = habiles(y, m, 7 if (y, m) == (2026, 9) else 1)
        filas = []
        for f in filas_por_est:
            if f is None:                         # hueco de numeración
                filas.append({'valores': [''] * len(dias), 'presentes': 0, 'tardanzas': 0, 'ausentes': 0,
                              'con_dato': 0, 'fila_vacia': True})
                continue
            vals = [f(date(y, m, d)) for d in dias]
            filas.append({'valores': vals, 'presentes': vals.count('P'), 'tardanzas': 0,
                          'ausentes': vals.count('A'), 'con_dato': sum(1 for v in vals if v in ('P', 'A'))})
        out.append({'mes': nombre, 'mes_num': m, 'anio': y, 'posicion': pos, 'dias': dias,
                    'filas': filas, 'dias_trabajados_configurados': None})
    return out


def generar(con_movimientos):
    est = []
    for i in range(1, 5):
        e = {'no_lista': i, 'nombre': 'Estudiante%d Sintético' % i, 'sexo': 'F', 'nacionalidad': 'Dominicana',
             'fecha_nacimiento': date(2018, 1, i), 'direccion': 'Calle %d' % i, 'condicion_entrada': 'promovido'}
        est.append(e)
    filas = [lambda f: 'P'] * 4
    if con_movimientos:
        # n.º 2 retirado desde 16/10; n.º 3 trasladado a otra sección desde 21/10;
        # n.º 4 hueco (nadie lo tiene) y n.º 5 incorporado desde 21/10.
        est[1].update({'retirado': True, 'marca_movimiento': '[RET 16/10/26]',
                       'direccion': '[RET 16/10/26] Calle 2', 'condicion_entrada': ''})
        est[2].update({'retirado': True, 'marca_movimiento': '[TRAS a 2do Primaria B MAT 21/10/26]',
                       'direccion': '[TRAS a 2do Primaria B MAT 21/10/26] Calle 3', 'condicion_entrada': ''})
        est[3] = {'no_lista': 4, 'nombre': '', 'sexo': '', 'direccion': '', 'condicion_entrada': '',
                  'fila_vacia': True, 'nacionalidad': ''}
        est.append({'no_lista': 5, 'nombre': 'Estudiante5 Sintético', 'sexo': 'M', 'nacionalidad': 'Dominicana',
                    'fecha_nacimiento': date(2018, 2, 5), 'condicion_entrada': 'promovido',
                    'marca_movimiento': '[INC de 2do Primaria B MAT 21/10/26]',
                    'direccion': '[INC de 2do Primaria B MAT 21/10/26] Calle 5'})
        filas = [lambda f: 'P',
                 lambda f: 'P' if f < date(2026, 10, 16) else '-',
                 lambda f: 'P' if f < date(2026, 10, 21) else '-',
                 None,
                 lambda f: '-' if f < date(2026, 10, 21) else 'P']
    cal = {a: {} for a in AREAS}
    colegio = {'nombre': 'Colegio Primaria TRAS', 'regional': '10', 'distrito': '10-01', 'codigo_centro': '1',
               'docente_titular': 'Maestra Sintética'}
    pdf = RP.generar_registro_primaria_desde_sistema(colegio, {'seccion': 'A', 'tanda': 'Matutina'}, '2026-2027',
                                                     est, cal, matriz(filas), {}, 2, {}, {})
    return pdf, pymupdf.open(stream=pdf, filetype='pdf')


pdf_mov, doc_mov = generar(True)
pdf_sin, doc_sin = generar(False)
open(os.path.join(OUT, 'registro_primaria_con_movimientos.pdf'), 'wb').write(pdf_mov)
txt_mov = [p.get_text() for p in doc_mov]
txt_sin = [p.get_text() for p in doc_sin]
pag_marcas = [i for i, t in enumerate(txt_mov) if '[RET 16/10/26]' in t]
pag_leyenda_marcas = [i for i, t in enumerate(txt_mov) if 'Marcas: [RET dd/mm/aa]' in t]
pag_leyenda_na = [i for i, t in enumerate(txt_mov) if 'No aplica: el estudiante no pertenecía' in t]
check('P1 las marcas [RET], [TRAS a] e [INC de] aparecen en la hoja de datos (casilla de dirección)',
      pag_marcas and all(m in txt_mov[pag_marcas[0]] for m in
                         ('[RET 16/10/26]', '[TRAS a 2do Primaria B MAT 21/10/26]', '[INC de 2do Primaria B MAT 21/10/26]')),
      pag_marcas)
check('P2 la hoja de datos lleva la leyenda de marcas en el margen superior', pag_leyenda_marcas == pag_marcas,
      (pag_leyenda_marcas, pag_marcas))
check('P3 las hojas de asistencia con «-» llevan la leyenda de No aplica', len(pag_leyenda_na) >= 2, pag_leyenda_na)
check('P4 sin movimientos no hay ninguna leyenda nueva (el documento queda como siempre)',
      not any('Marcas: [RET' in t or 'No aplica: el estudiante' in t for t in txt_sin))
check('P5 la fila del hueco (n.º 4) no tiene datos: su nombre no aparece', 'Estudiante4' not in ''.join(txt_mov))
for i in sorted(set(pag_marcas + pag_leyenda_na[:1])):
    doc_mov[i].get_pixmap(dpi=120).save(os.path.join(OUT, 'REG_PRIMARIA_p%d.png' % (i + 1)))

ok = sum(1 for _, c in RES if c)
print('\nRESULTADO REGISTRO PRIMARIA TRAS-1: %d PASARON / %d FALLARON' % (ok, len(RES) - ok))
print('Salida:', OUT)
sys.exit(0 if ok == len(RES) else 1)
