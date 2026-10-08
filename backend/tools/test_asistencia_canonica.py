# -*- coding: utf-8 -*-
"""
EducaOne — ASISTENCIA CANÓNICA: una sola fuente para A2, boletín, Registro y
Cierre, y los principios que la gobiernan.

    · sin fila = SIN DATO (ni presente ni ausente);
    · la excusa cubre el día pero no es ausencia injustificada;
    · antes del inicio del año (o del ALTA, si la ficha se creó después) y
      después del retiro: NO APLICA;
    · trasladado sin fecha de ingreso: FAIL CLOSED;
    · más del 20 % sigue al gate humano de A2; nada se reprueba por traslado.

Base temporal aislada. Nunca producción.

Uso:
    cd backend
    python tools/test_asistencia_canonica.py
"""
import datetime as dt
import os
import sys
from types import SimpleNamespace as NS

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(BK, "tools"))

from test_utils import aislar_base_de_datos  # noqa: E402

TMP = aislar_base_de_datos('asis_canonica')

from database import engine, SessionLocal  # noqa: E402
from test_utils import verificar_engine_aislado  # noqa: E402

verificar_engine_aislado(engine, TMP)

import models as M  # noqa: E402
import promocion_academica as PA  # noqa: E402
import asistencia_canonica as ASIS  # noqa: E402
import app as APP  # noqa: E402

M.Base.metadata.create_all(bind=engine)

PASARON, FALLARON = [], []


def check(nombre, cond, detalle=''):
    if cond:
        PASARON.append(nombre)
        print("  PASA   %-66s %s" % (nombre, detalle))
    else:
        FALLARON.append(nombre)
        print("  FALLA  %-66s %s" % (nombre, detalle))


def habiles(ini, fin):
    out, d = [], ini
    while d <= fin:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def fila(fecha, estado, asig=None):
    return NS(fecha=fecha, estado=estado, asignatura_id=asig)


# Un año corto y ya pasado: 2026-03-02 (lunes) .. 2026-03-27 (viernes) = 20 días
# hábiles, con P1..P4 de una semana cada uno.
INI, FIN = dt.date(2026, 3, 2), dt.date(2026, 3, 27)
HOY = dt.date(2026, 10, 7)
ANO = NS(fecha_inicio=INI, fecha_fin=FIN,
         p1_inicio=INI, p1_fin=dt.date(2026, 3, 6),
         p2_inicio=dt.date(2026, 3, 9), p2_fin=dt.date(2026, 3, 13),
         p3_inicio=dt.date(2026, 3, 16), p3_fin=dt.date(2026, 3, 20),
         p4_inicio=dt.date(2026, 3, 23), p4_fin=FIN)
DIAS = habiles(INI, FIN)
REG = NS(fecha_ingreso=dt.date(2026, 2, 1), fecha_retiro=None)   # alta antes del año
CAL = ASIS.calendario()

print("\n=== 1 · SIN FILA ES SIN DATO ===")
r = ASIS.resolver([], ANO, REG, HOY, CAL)
check('AC-01 sin ninguna lista: 20 días lectivos, 20 sin dato',
      r['dias_lectivos'] == 20 and r['sin_dato'] == 20 and r['con_dato'] == 0,
      '%s/%s' % (r['dias_lectivos'], r['sin_dato']))
check('AC-02 y A2 NO recibe número: cobertura incompleta',
      r['porcentaje_a2'] is None
      and r['diagnostico'] == ASIS.DIAG_COBERTURA_INCOMPLETA, str(r['diagnostico']))
check('AC-03 ningún porcentaje inventado para el boletín',
      r['pct_asistencia'] is None and r['pct_ausencia'] is None, '')

completo = [fila(d, 'presente') for d in DIAS]
r = ASIS.resolver(completo, ANO, REG, HOY, CAL)
check('AC-04 lista completa, todo presente: 0 % y A2 sigue',
      r['porcentaje_a2'] == 0.0 and r['cobertura_pct'] == 100.0, str(r['porcentaje_a2']))

# 17 de 20 con dato, todo presente: sigue sin haber porcentaje OFICIAL.
r = ASIS.resolver(completo[:17], ANO, REG, HOY, CAL)
check('AC-05 un solo hueco basta: FAIL CLOSED para A2',
      r['porcentaje_a2'] is None
      and r['diagnostico'] == ASIS.DIAG_COBERTURA_INCOMPLETA, str(r['porcentaje_a2']))
check('AC-06 y el boletín NO muestra 100 %: oficial N/D, cobertura 17 de 20',
      r['pct_asistencia'] is None and r['con_dato'] == 17
      and r['dias_lectivos'] == 20 and r['pct_asistencia_registrado'] == 100.0, '')

# Cobertura completa con 5 ausencias de 20 = 25 %: A2 recibe 25 y aplica su
# propia regla (revisión humana). Aquí no se reprueba a nadie.
r = ASIS.resolver([fila(d, 'ausente') for d in DIAS[:5]]
                  + [fila(d, 'presente') for d in DIAS[5:]], ANO, REG, HOY, CAL)
check('AC-07 cobertura completa con 25 %: A2 recibe el porcentaje real',
      r['porcentaje_a2'] == 25.0 and r['pct_asistencia'] == 75.0, str(r['porcentaje_a2']))

print("\n=== 2 · LA EXCUSA CUBRE, NO ES INJUSTIFICADA ===")
r = ASIS.resolver([fila(d, 'excusa') for d in DIAS[:10]]
                  + [fila(d, 'presente') for d in DIAS[10:]], ANO, REG, HOY, CAL)
check('AC-08 diez excusas: 0 % injustificado y cobertura completa',
      r['porcentaje_a2'] == 0.0 and r['sin_dato'] == 0 and r['excusas'] == 10, '')
check('AC-09 pero en el boletín la excusa SÍ es ausencia (justificada)',
      r['pct_ausencia'] == 50.0, str(r['pct_ausencia']))

print("\n=== 3 · UN DÍA ES UN DÍA (lista por asignatura) ===")
r = ASIS.resolver([fila(DIAS[0], 'ausente', 1), fila(DIAS[0], 'presente', 2)]
                  + completo[1:], ANO, REG, HOY, CAL)
check('AC-10 faltar a UNA materia no hace ausente el día',
      r['ausencias'] == 0 and r['dias'][DIAS[0]] == 'presente', '')

print("\n=== 4 · ALTA DESPUÉS DE INICIADO EL AÑO: ANTES DEL ALTA NO APLICA ===")
ingreso = dt.date(2026, 3, 16)   # se da de alta en EducaOne en P3 (traslado)
TR = NS(fecha_ingreso=ingreso, fecha_retiro=None)
solo_desde = [fila(d, 'presente') for d in DIAS if d >= ingreso]
r = ASIS.resolver(solo_desde, ANO, TR, HOY, CAL)
check('AC-11 los días anteriores al alta no existen para él',
      r['dias_lectivos'] == 10 and min(r['dias']) == ingreso, str(r['dias_lectivos']))
check('AC-12 ni presentes ni ausentes antes del alta',
      r['periodos']['p1']['dias_lectivos'] == 0
      and r['periodos']['p2']['dias_lectivos'] == 0, '')
check('AC-13 con su asistencia local completa, A2 sigue: 0 %',
      r['porcentaje_a2'] == 0.0, str(r['porcentaje_a2']))
check('AC-14 y queda una advertencia informativa, sin bloquear',
      ASIS.ADV_ALTA_POSTERIOR in r['advertencias'] and r['diagnostico'] is None, '')

# Ficha creada el 16, pero con listas reales desde el 9 (ficha recreada o
# importada tarde): manda la primera lista, no se descarta ninguna marca.
r = ASIS.resolver([fila(d, 'presente') for d in DIAS if d >= dt.date(2026, 3, 9)],
                  ANO, TR, HOY, CAL)
check('AC-15 listas anteriores al alta: la asistencia empieza en la primera lista',
      min(r['dias']) == dt.date(2026, 3, 9) and r['dias_lectivos'] == 15
      and r['porcentaje_a2'] == 0.0, str(min(r['dias'])))

# Llega tarde y falta 3 de 4 días: 75 % → gate humano, NUNCA reprobado aquí.
TARDE = NS(fecha_ingreso=dt.date(2026, 3, 24), fecha_retiro=None)
r = ASIS.resolver([fila(dt.date(2026, 3, 24), 'ausente'),
                   fila(dt.date(2026, 3, 25), 'ausente'),
                   fila(dt.date(2026, 3, 26), 'ausente'),
                   fila(dt.date(2026, 3, 27), 'presente')], ANO, TARDE, HOY, CAL)
check('AC-16 alta muy tardía con faltas: porcentaje real, al gate humano',
      r['porcentaje_a2'] == 75.0 and ASIS.ADV_ALTA_POSTERIOR in r['advertencias'], '')

print("\n=== 5 · RETIRO: DESPUÉS NO APLICA ===")
RET = NS(fecha_ingreso=dt.date(2026, 2, 1), fecha_retiro=dt.date(2026, 3, 13))
r = ASIS.resolver(completo, ANO, RET, HOY, CAL)
check('AC-17 tras el retiro no hay días lectivos para él',
      r['dias_lectivos'] == 10 and max(r['dias']) == dt.date(2026, 3, 13), '')

print("\n=== 6 · CALENDARIO ===")
cal_feriado = ASIS.calendario([(dt.date(2026, 3, 19), False)])
r = ASIS.resolver(completo[:13] + completo[14:], ANO, REG, HOY, cal_feriado)
check('AC-18 un feriado declarado no es día lectivo', r['dias_lectivos'] == 19
      and r['sin_dato'] == 0, str(r['dias_lectivos']))
r = ASIS.resolver(completo + [fila(dt.date(2026, 3, 7), 'presente')], ANO, REG, HOY, CAL)
check('AC-19 un sábado con lista pasada SÍ fue lectivo', r['dias_lectivos'] == 21, '')
r = ASIS.resolver([], NS(fecha_inicio=dt.date(2026, 9, 1), fecha_fin=dt.date(2027, 6, 30)),
                  REG, dt.date(2026, 9, 4), CAL)
check('AC-20 los días futuros no son huecos: la ventana termina hoy',
      r['dias_lectivos'] == 4, str(r['dias_lectivos']))
r = ASIS.resolver(completo, NS(fecha_inicio=None, fecha_fin=None), REG, HOY, CAL)
check('AC-21 un año sin fechas no se evalúa', r['porcentaje_a2'] is None
      and r['diagnostico'] == ASIS.DIAG_ANO_SIN_FECHAS, '')

print("\n=== 7 · PERÍODOS Y ANUAL SALEN DEL MISMO CÁLCULO ===")
mezcla = ([fila(d, 'presente') for d in DIAS[:5]]          # P1 completo
          + [fila(d, 'ausente') for d in DIAS[5:7]]         # P2 dos faltas
          + [fila(d, 'tardanza') for d in DIAS[10:15]])     # P3 tardanzas, P4 vacío
r = ASIS.resolver(mezcla, ANO, REG, HOY, CAL)
per = ASIS.periodos_boletin(r)
anual = ASIS.anual_boletin(r)
check('AC-22 P1 = 5 asistencias', per['p1']['asistencia'] == 5, str(per['p1']))
check('AC-23 P2 = 2 ausencias y 3 sin dato',
      per['p2']['ausencia'] == 2 and per['p2']['sin_dato'] == 3, str(per['p2']))
check('AC-24 P3: la tardanza es asistencia', per['p3']['asistencia'] == 5, '')
check('AC-25 P4 sin lista: sin porcentaje, no 0 %',
      per['p4']['asistencia'] == 0 and per['p4']['pct_asistencia_anual'] is None, '')
check('AC-25b P1 con cobertura completa SÍ tiene porcentaje; P2 con huecos, N/D',
      per['p1']['pct_asistencia_anual'] == 100
      and per['p2']['pct_asistencia_anual'] is None, str((per['p1'], per['p2'])))
check('AC-26 el anual es la suma de los períodos',
      sum(per['p%d' % p]['asistencia'] for p in range(1, 5)) == anual['asistencias']
      and sum(per['p%d' % p]['ausencia'] for p in range(1, 5)) == anual['ausencias_totales'], '')
check('AC-27 el anual declara cobertura y sin dato',
      anual['sin_dato'] == 8 and anual['cobertura_pct'] == 60.0, str(anual['cobertura_pct']))
check('AC-27b y sin cobertura completa el anual oficial es N/D',
      anual['pct_asistencia'] is None and anual['pct_ausencia'] is None
      and anual['cobertura_completa'] is False, '')

print("\n=== 8 · INTEGRACIÓN: A2, BOLETÍN, CIERRE Y REGISTRO LEEN LO MISMO ===")
db = SessionLocal()
col = M.Colegio(nombre='AC', codigo='ac', activo=True)
db.add(col)
db.flush()
ano = M.AnoEscolar(colegio_id=col.id, nombre='2025-2026', activo=True, cerrado=False,
                   fecha_inicio=INI, fecha_fin=FIN,
                   p1_inicio=ANO.p1_inicio, p1_fin=ANO.p1_fin,
                   p2_inicio=ANO.p2_inicio, p2_fin=ANO.p2_fin,
                   p3_inicio=ANO.p3_inicio, p3_fin=ANO.p3_fin,
                   p4_inicio=ANO.p4_inicio, p4_fin=ANO.p4_fin)
grd = M.Grado(colegio_id=col.id, nombre='3ro Secundaria', nivel='secundaria',
              orden=3, activo=True)
db.add_all([ano, grd])
db.flush()
curso = M.Curso(colegio_id=col.id, nombre='A', grado_id=grd.id,
                ano_escolar_id=ano.id, activo=True)
usr = M.Usuario(colegio_id=col.id, username='ac_dir', password_hash='x', nombre='D',
                role='direccion', activo=True, must_change_password=False,
                token_version=0)
db.add_all([curso, usr])
db.flush()
reg = M.Estudiante(colegio_id=col.id, matricula='AC-1', nombre='Reg', apellido='Ular',
                   curso_id=curso.id, activo=True, no_lista=1)
tra = M.Estudiante(colegio_id=col.id, matricula='AC-2', nombre='Tras', apellido='Lado',
                   curso_id=curso.id, activo=True, no_lista=2,
                   condicion_entrada='transferido', fecha_ingreso=ingreso)
db.add_all([reg, tra])
db.flush()
# Las nueve áreas oficiales aprobadas: así el candidato académico es PROMOVIDO
# y A2 LLEGA al gate de asistencia, que es lo que aquí se prueba.
for codigo in ('LE', 'MAT', 'CS', 'CN', 'LEI', 'LEF', 'EF', 'EA', 'FIHR'):
    asig = M.Asignatura(colegio_id=col.id, nombre=codigo, codigo=codigo,
                        area='X', area_curricular_codigo=codigo, activo=True)
    db.add(asig)
    db.flush()
    for est in (reg, tra):
        for n in range(1, 5):
            db.add(M.CalificacionSecundaria(
                colegio_id=col.id, estudiante_id=est.id, asignatura_id=asig.id,
                ano_escolar_id=ano.id, competencia_numero=n,
                p1=90, p2=90, p3=90, p4=90))
for d in DIAS:
    db.add(M.Asistencia(colegio_id=col.id, estudiante_id=reg.id, curso_id=curso.id,
                        fecha=d, estado='presente'))
    if d >= ingreso:
        db.add(M.Asistencia(colegio_id=col.id, estudiante_id=tra.id, curso_id=curso.id,
                            fecha=d, estado='presente'))
db.commit()

pre = APP._precarga_curso_canonica(db, usr, curso, ano,
                                   estudiante_ids=[reg.id, tra.id])
for et, est in (('regular', reg), ('trasladado', tra)):
    paq = APP._situacion_canonica_secundaria(db, usr, est, ano, pre)
    anual_bol = APP._asistencia_anual_boletin(db, est.id, usr, ano)
    check('AC-28 %s: A2 recibe el porcentaje canónico' % et,
          paq['contexto']['porcentaje_ausencias_no_justificadas']
          == paq['asistencia']['porcentaje_a2'] == 0.0, '')
    check('AC-29 %s: el boletín anual es el MISMO cálculo que A2' % et,
          anual_bol == ASIS.anual_boletin(paq['asistencia']), '')
    check('AC-30 %s: el Cierre guarda el mismo %% que imprime el boletín' % et,
          APP._asistencia_del_paquete(paq) == anual_bol['pct_asistencia'] == 100.0,
          str(APP._asistencia_del_paquete(paq)))
    check('AC-31 %s: con todo aprobado y asistencia completa, PROMOVIDO' % et,
          paq['situacion']['condicion'] == PA.PROMOVIDO,
          '%s %s' % (paq['situacion']['condicion'], paq['situacion']['bloqueos']))


from registro_asistencia import build_asistencia_registro  # noqa: E402
matriz = build_asistencia_registro(db, curso.id, estudiantes=[reg, tra])
marzo = [m for m in matriz if m['mes_num'] == 3][0]
f_tra = [f for f in marzo['filas'] if f['estudiante_id'] == tra.id][0]
f_reg = [f for f in marzo['filas'] if f['estudiante_id'] == reg.id][0]
_idx_antes = marzo['dias'].index(2)       # 2 de marzo: antes de su ingreso
check('AC-33 Registro: antes del ingreso la celda es «-» (NO APLICA)',
      f_tra['valores'][_idx_antes] == '-', repr(f_tra['valores'][_idx_antes]))
check('AC-34 Registro: el trasladado NO queda penalizado por esos días',
      f_tra['porcentaje'] == 100.0, str(f_tra['porcentaje']))
check('AC-35 Registro: el regular, con todo presente, 100 %', f_reg['porcentaje'] == 100.0, '')

# /academico (TabAsistencia) ya no tiene fórmula propia: dice lo mismo que el
# boletín, año y períodos.
import asyncio  # noqa: E402


class _Req:
    query_params = {'mes': '3', 'ano': '2026'}


_tab = asyncio.run(APP.get_resumen_asistencia_por_periodos(
    curso_id=curso.id, request=_Req(), db=db, current_user=usr))
for fila_tab in _tab:
    _an = APP._asistencia_anual_boletin(db, fila_tab['estudiante_id'], usr, ano)
    _per = APP._construir_asistencias_boletin(db, fila_tab['estudiante_id'], usr, ano)
    check('AC-38 /academico = boletín (estudiante %d): mismo %% anual y períodos'
          % fila_tab['estudiante_id'],
          fila_tab['pct_asistencia_anual'] == _an['pct_asistencia']
          and fila_tab['periodos'] == _per
          and fila_tab['total_asistencia'] == _an['asistencias'],
          '%s vs %s' % (fila_tab['pct_asistencia_anual'], _an['pct_asistencia']))
check('AC-39 /academico ya no usa días trabajados como denominador',
      all(f['_usa_dias_trabajados'] is False for f in _tab), '')

print("\n=== 9 · SIN COLUMNAS NUEVAS ===")
check('AC-36 el estudiante no tiene `fecha_ingreso_centro`: se usa el alta que ya existía',
      'fecha_ingreso_centro' not in M.Estudiante.__table__.columns
      and 'fecha_ingreso' in M.Estudiante.__table__.columns, '')
check('AC-37 y el motor no lee ninguna fecha fija: todo sale del año del colegio',
      not any(t in open(ASIS.__file__, encoding='utf-8').read()
              for t in ('2026-', 'date(2026', 'date(2025', 'colegio_id')), '')

print()
print("=" * 98)
print("RESULTADO: %d PASARON / %d FALLARON" % (len(PASARON), len(FALLARON)))
print("=" * 98)
for f in FALLARON:
    print("  FALLA:", f)

db.close()
sys.exit(1 if FALLARON else 0)
