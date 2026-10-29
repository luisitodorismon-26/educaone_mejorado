"""SALIDAS-MIXTAS — un curso de 4to con dos componentes de salidas distintas.

Caso real del centro: 4to imparte HLM-LE-4 (Apreciación y Producción
Literarias, Julio) y HCS-CS-4 (Filosofía Social y Pensamiento Dominicano,
Rosana). Julio da también Lengua Española y Rosana Ciencias Sociales.

Comprueba, con endpoints reales sobre una base SQLite AISLADA y datos
sintéticos:

  A. añadir un componente no sustituye al otro ni toca las troncales; el
     tercero se rechaza ANTES de guardar, nombrándolo; otros cursos no cambian;
  B. ya no se crean asignaturas duplicadas: con candidatas (el caso de las
     asignaturas 25 y 27 de producción) se responde 409 con la lista y no se
     crea, reactiva ni borra nada; la elección explícita sí se aplica;
  C. cada maestro conserva su materia normal y su optativa, con notas y
     asistencias separadas;
  D. Registro (oficial y borrador) y boletín (individual y por lote): mismo
     orden en asistencia, acta y boletín; el acta tiene las dos columnas; una
     materia extra no desplaza a una optativa; con 3 componentes no se emite
     ningún documento;
  E. un curso de una sola salida sigue igual (orden y rótulos de siempre).

Uso (desde backend/):  python tools/test_salidas_mixtas_4to.py [carpeta_pdfs]
"""
import datetime as dt
import os
import sys

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(BK, 'tools'))
from test_utils import aislar_base_de_datos, verificar_engine_aislado

TMP = aislar_base_de_datos('salidas_mixtas_4to')
from database import engine, SessionLocal
verificar_engine_aislado(engine, TMP)
import models as M
import app as APP
from fastapi.testclient import TestClient
from auth import create_token
import pymupdf

OUT = sys.argv[1] if len(sys.argv) > 1 else None
if OUT:
    os.makedirs(OUT, exist_ok=True)

M.Base.metadata.create_all(bind=engine)
db = SessionLocal()
OK, MAL = [], []


def check(nombre, cond, detalle=''):
    (OK if cond else MAL).append(nombre)
    print('  %s %s %s' % ('PASA ' if cond else 'FALLA', nombre, '' if cond else str(detalle)[:400]))


def add(o):
    db.add(o)
    db.flush()
    return o


HOY = APP.today_rd()
col = add(M.Colegio(nombre='Colegio Sintético', codigo='SALMIX', activo=True))
add(M.ConfiguracionColegio(colegio_id=col.id, nombre=col.nombre, regional='10', distrito='10-01',
                           codigo_centro='1'))
ano = add(M.AnoEscolar(colegio_id=col.id, nombre='2026-2027', activo=True, cerrado=False,
                       fecha_inicio=dt.date(2026, 9, 1), fecha_fin=dt.date(2027, 6, 30)))
g4 = add(M.Grado(colegio_id=col.id, nombre='4to Secundaria', nivel='secundaria', orden=4, activo=True))
tanda = add(M.Tanda(colegio_id=col.id, nombre='Matutina', hora_inicio='07:30', hora_fin='13:00', activo=True))


def curso(nombre, salida=None):
    return add(M.Curso(colegio_id=col.id, nombre=nombre, grado_id=g4.id, tanda_id=tanda.id,
                       ano_escolar_id=ano.id, activo=True, salida_optativa_codigo=salida))


def usuario(u, rol, nombre):
    return add(M.Usuario(colegio_id=col.id, username=u, password_hash='x', nombre=nombre, apellido='Sint',
                         role=rol, activo=True, must_change_password=False, token_version=0))


dire = usuario('sm_dir', 'direccion', 'Dir')
julio = usuario('sm_julio', 'profesor', 'Julio')
rosana = usuario('sm_rosana', 'profesor', 'Rosana')
otro = usuario('sm_otro', 'profesor', 'Otro')
lengua = add(M.Asignatura(colegio_id=col.id, nombre='Lengua Española', codigo='LE', area_curricular_codigo='LE'))
sociales = add(M.Asignatura(colegio_id=col.id, nombre='Ciencias Sociales', codigo='CS', area_curricular_codigo='CS'))
musica = add(M.Asignatura(colegio_id=col.id, nombre='Música', codigo='MUS'))

A = curso('A')                 # el curso del caso real
B = curso('B')                 # una sola salida (HLM), no debe cambiar
for c_ in (A, B):
    add(M.AsignacionProfesor(colegio_id=col.id, profesor_id=julio.id, curso_id=c_.id,
                             asignatura_id=lengua.id, ano_escolar_id=ano.id, activo=True, es_titular=True))
    add(M.AsignacionProfesor(colegio_id=col.id, profesor_id=rosana.id, curso_id=c_.id,
                             asignatura_id=sociales.id, ano_escolar_id=ano.id, activo=True))


def estudiantes(c_, pref):
    return [add(M.Estudiante(colegio_id=col.id, nombre='%s%d' % (pref, i), apellido='Apellido%s%d' % (pref, i),
                             curso_id=c_.id, no_lista=i, activo=True, condicion='activo', sexo='F',
                             fecha_ingreso=dt.date(2026, 8, 1))) for i in (1, 2, 3)]


EA, EB = estudiantes(A, 'A'), estudiantes(B, 'B')
db.commit()

c = TestClient(APP.app)
HD = {'Authorization': 'Bearer ' + create_token(dire)}
HJ = {'Authorization': 'Bearer ' + create_token(julio)}
HR = {'Authorization': 'Bearer ' + create_token(rosana)}


def mapeos(c_):
    db.expire_all()
    return {m.componente_codigo: m.asignatura_id for m in
            db.query(M.CursoComponenteOptativo).filter_by(curso_id=c_.id, activo=True)}


def asignaciones(c_):
    db.expire_all()
    return sorted((a.id, a.profesor_id, a.asignatura_id, bool(a.activo)) for a in
                  db.query(M.AsignacionProfesor).filter_by(curso_id=c_.id))


def n_asignaturas():
    db.expire_all()
    return db.query(M.Asignatura).count()


def put(c_, body):
    return c.put('/api/cursos/%d/salida-optativa' % c_.id, headers=HD, json=body)


def post(c_, body):
    return c.post('/api/cursos/%d/salida-optativa/componentes' % c_.id, headers=HD, json=body)


# =====================================================================
print('\n=== A. Configuración: añadir un componente no sustituye al otro ===')
r = put(A, {'salida_optativa_codigo': 'HLM', 'profesores': {'HLM-LE-4': julio.id}})
check('A1 PUT salida HLM con Julio en HLM-LE-4', r.status_code == 200, r.text)
m1 = mapeos(A)
hlm_le = m1.get('HLM-LE-4')
asig_antes = asignaciones(A)
r = put(B, {'salida_optativa_codigo': 'HLM', 'profesores': {'HLM-LE-4': julio.id, 'HLM-IN-4': otro.id}})
check('A2 curso B (una sola salida, dos componentes) configurado', r.status_code == 200, r.text)
mB, asigB, estB = mapeos(B), asignaciones(B), r.json()

r = post(A, {'componente_codigo': 'HCS-CS-4', 'profesor_id': rosana.id})
check('A3 POST HCS-CS-4 con Rosana en un curso HLM', r.status_code == 200, r.text)
est = r.json()
m2 = mapeos(A)
hcs_cs = m2.get('HCS-CS-4')
check('A4 HLM-LE-4 conserva su asignatura y HCS-CS-4 tiene la suya',
      m2.get('HLM-LE-4') == hlm_le and hcs_cs not in (None, hlm_le) and set(m2) == {'HLM-LE-4', 'HCS-CS-4'}, m2)
asig_desp = asignaciones(A)
check('A5 ninguna asignación previa cambió (troncales y Julio); se añade solo la de Rosana',
      set(asig_antes) <= set(asig_desp) and
      [x for x in asig_desp if x not in asig_antes] and
      all(x[1] == rosana.id and x[2] == hcs_cs and x[3] for x in asig_desp if x not in asig_antes),
      (asig_antes, asig_desp))
check('A6 estado: modo componentes, orden HLM-LE-4 (1) y HCS-CS-4 (2), 2 de 2 espacios',
      est['modo'] == 'componentes' and
      [(x['componente_codigo'], x['orden_impresion']) for x in est['componentes']] == [('HLM-LE-4', 1), ('HCS-CS-4', 2)]
      and est['espacios_en_uso'] == 2 and not est['excede_capacidad'], est)
check('A7 HLM-IN-4 ya no figura como pendiente; configurada', est['faltantes'] == [] and est['configurada'],
      (est['faltantes'], est['configurada']))
check('A8 la salida del curso (rótulo) no cambió', est['salida_optativa_codigo'] == 'HLM', est['salida_optativa_codigo'])

r = post(A, {'componente_codigo': 'HCS-CS-4', 'profesor_id': otro.id})
r = post(A, {'componente_codigo': 'HCS-CS-4', 'profesor_id': rosana.id})
check('A9 cambiar el profesor de HCS-CS-4 conserva su asignatura', r.status_code == 200 and mapeos(A) == m2,
      (r.status_code, mapeos(A)))
activos = [x for x in asignaciones(A) if x[2] == hcs_cs and x[3]]
check('A10 HCS-CS-4 queda con UN responsable activo (Rosana)', [x[1] for x in activos] == [rosana.id], activos)

n0, a0 = n_asignaturas(), asignaciones(A)
r = post(A, {'componente_codigo': 'HLM-IN-4', 'profesor_id': otro.id})
js = r.json()
check('A11 tercer componente (POST): 409 capacidad_registro antes de guardar',
      r.status_code == 409 and js.get('motivo') == 'capacidad_registro', (r.status_code, js))
check('A12 el mensaje nombra los 3 componentes, incluido el que se intentaba añadir',
      all(x in js.get('error', '') for x in ('HLM-LE-4', 'HLM-IN-4', 'HCS-CS-4')), js.get('error'))
check('A13 nada cambió: mapeos, asignaturas y asignaciones', mapeos(A) == m2 and n_asignaturas() == n0
      and asignaciones(A) == a0, (mapeos(A), n_asignaturas(), n0))
r = put(A, {'profesores': {'HLM-IN-4': otro.id}})
check('A14 tercer componente por el PUT: también 409 y nada cambia',
      r.status_code == 409 and r.json().get('motivo') == 'capacidad_registro' and mapeos(A) == m2
      and n_asignaturas() == n0 and asignaciones(A) == a0, (r.status_code, r.text[:200]))
r = post(A, {'componente_codigo': 'HCS-CS-5', 'profesor_id': otro.id})
check('A15 componente de otro grado: 400', r.status_code == 400, r.text[:200])
check('A16 el curso B no cambió (no se extiende a otros cursos)', mapeos(B) == mB and asignaciones(B) == asigB,
      (mapeos(B), mB))
estB2 = c.get('/api/cursos/%d/salida-optativa' % B.id, headers=HD).json()
check('A17 curso B sigue en modo salida, HLM-LE-4 y HLM-IN-4',
      estB2['modo'] == 'salida' and [x['componente_codigo'] for x in estB2['componentes']] == ['HLM-LE-4', 'HLM-IN-4'],
      estB2)
r = c.post('/api/cursos/%d/salida-optativa/componentes' % A.id, headers=HJ,
           json={'componente_codigo': 'HCS-LE-4', 'profesor_id': julio.id})
check('A18 un profesor no puede añadir componentes', r.status_code in (401, 403), r.status_code)

# =====================================================================
print('\n=== B. Sin duplicados: candidatas, elección explícita ===')
C = curso('C')
db.commit()
r = put(C, {'salida_optativa_codigo': 'HLM', 'profesores': {'HLM-LE-4': julio.id}})
r = put(C, {'salida_optativa_codigo': 'HCS', 'profesores': {'HCS-CS-4': rosana.id}})
check('B1 C: HLM con Julio y cambio a HCS con Rosana (como en producción)', r.status_code == 200, r.text[:200])
n0, aC = n_asignaturas(), asignaciones(C)
r = put(C, {'salida_optativa_codigo': 'HLM', 'profesores': {'HLM-LE-4': julio.id}})
js = r.json()
check('B2 volver a HLM con Julio: 409 identidad_por_elegir (antes creaba otra HLM-LE-4)',
      r.status_code == 409 and js.get('motivo') == 'identidad_por_elegir' and len(js.get('candidatas', [])) == 1,
      (r.status_code, js))
check('B3 no se creó ninguna asignatura y nada se reactivó ni se borró',
      n_asignaturas() == n0 and asignaciones(C) == aC, (n_asignaturas(), n0))
db.expire_all()
check('B4 la salida de C sigue en HCS (el PUT entero se descartó)', db.get(M.Curso, C.id).salida_optativa_codigo == 'HCS',
      db.get(M.Curso, C.id).salida_optativa_codigo)

# El caso 25/27: dos HLM-LE-4 dedicadas, ambas con la asignación de Julio inactiva.
D = curso('D', salida='HLM')
dup = [add(M.Asignatura(colegio_id=col.id, nombre='Apreciación y Producción Literarias', codigo='HLM-LE-4',
                        area='', area_curricular_codigo=None, activo=True)) for _ in range(2)]
for a_ in dup:
    add(M.AsignacionProfesor(colegio_id=col.id, profesor_id=julio.id, curso_id=D.id, asignatura_id=a_.id,
                             ano_escolar_id=ano.id, activo=False))
db.commit()
n0, aD = n_asignaturas(), asignaciones(D)
r = post(D, {'componente_codigo': 'HLM-LE-4', 'profesor_id': julio.id})
js = r.json()
check('B5 dos candidatas (como 25 y 27): 409 con AMBAS',
      r.status_code == 409 and sorted(x['asignatura_id'] for x in js.get('candidatas', [])) == sorted(a.id for a in dup),
      (r.status_code, js))
check('B6 las candidatas traen sus datos (asignaciones inactivas de Julio)',
      all(x['asignaciones'] == [{'profesor_id': julio.id, 'profesor_nombre': julio.nombre_completo, 'activo': False}]
          for x in js.get('candidatas', [])), js.get('candidatas'))
check('B7 no se creó, reactivó ni borró nada', n_asignaturas() == n0 and asignaciones(D) == aD and not mapeos(D),
      (n_asignaturas(), asignaciones(D), mapeos(D)))
estD = c.get('/api/cursos/%d/salida-optativa' % D.id, headers=HD).json()
check('B7b la pantalla muestra las 2 candidatas en el componente pendiente',
      sorted(x['asignatura_id'] for x in next(k for k in estD['componentes']
                                              if k['componente_codigo'] == 'HLM-LE-4')['candidatas'])
      == sorted(a.id for a in dup), estD['componentes'])
r = put(D, {'profesores': {'HLM-LE-4': julio.id}})
check('B8 por el PUT: el mismo 409, nada cambia',
      r.status_code == 409 and r.json().get('motivo') == 'identidad_por_elegir' and n_asignaturas() == n0
      and asignaciones(D) == aD, (r.status_code, r.text[:200]))
elegida, otra = dup[1], dup[0]
r = post(D, {'componente_codigo': 'HLM-LE-4', 'profesor_id': julio.id, 'asignatura_id': elegida.id})
check('B9 elección explícita: 200 y el componente apunta a la elegida',
      r.status_code == 200 and mapeos(D) == {'HLM-LE-4': elegida.id}, (r.status_code, r.text[:200], mapeos(D)))
aD2 = asignaciones(D)
check('B10 la otra asignatura sigue igual: existe y su asignación sigue inactiva',
      db.get(M.Asignatura, otra.id) is not None and
      [x for x in aD2 if x[2] == otra.id] == [x for x in aD if x[2] == otra.id], aD2)
check('B11 en la elegida, Julio queda activo por decisión explícita (una sola fila)',
      [(x[1], x[3]) for x in aD2 if x[2] == elegida.id] == [(julio.id, True)], aD2)
check('B12 ninguna asignatura nueva', n_asignaturas() == n0, (n_asignaturas(), n0))
E_ = curso('E', salida='HLM')
dupE = add(M.Asignatura(colegio_id=col.id, nombre='Apreciación y Producción Literarias', codigo='HLM-LE-4',
                        area='', area_curricular_codigo=None, activo=True))
add(M.AsignacionProfesor(colegio_id=col.id, profesor_id=julio.id, curso_id=E_.id, asignatura_id=dupE.id,
                         ano_escolar_id=ano.id, activo=False))
db.commit()
n0 = n_asignaturas()
r = post(E_, {'componente_codigo': 'HLM-LE-4', 'profesor_id': julio.id, 'crear_identidad_nueva': True})
check('B13 "crear una nueva" solo si se pide expresamente', r.status_code == 200 and n_asignaturas() == n0 + 1
      and mapeos(E_)['HLM-LE-4'] not in (dupE.id,), (r.status_code, r.text[:200]))
F_ = curso('F', salida='HLM')
db.commit()
r = post(F_, {'componente_codigo': 'HCS-CS-4', 'profesor_id': rosana.id, 'asignatura_id': lengua.id})
check('B14 una troncal no puede ser la identidad elegida', r.status_code == 400, r.text[:200])

# =====================================================================
print('\n=== C. Mismo maestro: materia normal y optativa separadas ===')
for prof, H, normal, opt, n_val, o_val in ((julio, HJ, lengua.id, hlm_le, 91, 64),
                                           (rosana, HR, sociales.id, hcs_cs, 88, 73)):
    for asig, v in ((normal, n_val), (opt, o_val)):
        r = c.post('/api/calificaciones-secundaria', headers=H,
                   json={'estudiante_id': EA[0].id, 'asignatura_id': asig, 'competencia_numero': 1, 'p1': v})
        check('C1 %s guarda nota %d en asignatura %d' % (prof.nombre, v, asig), r.status_code == 200, r.text[:200])
    db.expire_all()
    notas = {x.asignatura_id: x.p1 for x in db.query(M.CalificacionSecundaria).filter_by(
        estudiante_id=EA[0].id, competencia_numero=1) if x.asignatura_id in (normal, opt)}
    check('C2 %s: cada asignatura conserva su nota' % prof.nombre, notas == {normal: n_val, opt: o_val}, notas)
    MARCAS = {EA[0].id: ('presente', 'ausente'), EA[1].id: ('ausente', 'presente'), EA[2].id: ('tardanza', 'presente')}
    for eid, (en, eo) in MARCAS.items():
        for asig, estado in ((normal, en), (opt, eo)):
            r = c.post('/api/asistencia', headers=H, json={'estudiante_id': eid, 'curso_id': A.id,
                                                           'asignatura_id': asig, 'fecha': HOY.isoformat(),
                                                           'estado': estado})
            if r.status_code != 200:
                check('C3 asistencia %s est %d asig %d' % (prof.nombre, eid, asig), False, r.text[:200])
    for asig, idx in ((normal, 0), (opt, 1)):
        r = c.get('/api/asistencia/curso/%d?fecha=%s&asignatura_id=%d' % (A.id, HOY.isoformat(), asig), headers=H)
        js = r.json()
        lista = js if isinstance(js, list) else next((v for v in js.values() if isinstance(v, list)), [])
        got = {x['estudiante']['id']: (x.get('asistencia') or {}).get('estado') for x in lista
               if isinstance(x, dict) and 'estudiante' in x}
        check('C4 %s: la lista de la asignatura %d muestra SOLO sus marcas' % (prof.nombre, asig),
              got == {e: m[idx] for e, m in MARCAS.items()}, got)
    r = c.get('/api/dashboard/profesor', headers=H)
    filas = sorted((x['asignatura_id'], x['es_salida_optativa']) for x in r.json().get('cursos_asignados', [])
                   if x.get('curso_id') == A.id)
    check('C5 %s ve 2 entradas en 4to A: la normal y la optativa' % prof.nombre,
          filas == sorted([(normal, False), (opt, True)]), filas)
db.expire_all()
n_asis = db.query(M.Asistencia).filter_by(curso_id=A.id, fecha=HOY).count()
check('C6 12 filas de asistencia del día: 3 estudiantes x 4 asignaturas', n_asis == 12, n_asis)

# =====================================================================
print('\n=== D. Documentos completos ===')
# Notas completas (4 competencias x 4 períodos) con valores distintos por
# asignatura y por estudiante: base + índice del estudiante.
BASE = {lengua.id: 81, sociales.id: 84, hlm_le: 66, hcs_cs: 77}
for c_, ests in ((A, EA),):
    for i, e in enumerate(ests):
        for asig, base in BASE.items():
            db.query(M.CalificacionSecundaria).filter_by(estudiante_id=e.id, asignatura_id=asig).delete()
            for comp in (1, 2, 3, 4):
                v = base + i
                add(M.CalificacionSecundaria(colegio_id=col.id, estudiante_id=e.id, asignatura_id=asig,
                                             ano_escolar_id=ano.id, competencia_numero=comp,
                                             p1=v, p2=v, p3=v, p4=v))
def horarios(c_):
    # El Registro oficial exige horario para cada asignatura asignada al curso.
    db.expire_all()
    dias = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes']
    for k, ap in enumerate(db.query(M.AsignacionProfesor).filter_by(curso_id=c_.id, activo=True)):
        if db.query(M.Horario).filter_by(curso_id=c_.id, asignatura_id=ap.asignatura_id, activo=True).first():
            continue
        add(M.Horario(colegio_id=col.id, profesor_id=ap.profesor_id, curso_id=c_.id,
                      asignatura_id=ap.asignatura_id, dia=dias[k % 5], hora_inicio='%02d:00' % (7 + k // 5),
                      hora_fin='%02d:00' % (8 + k // 5), tipo_bloque='clase', activo=True))


horarios(A)
# Asistencia de septiembre en las dos optativas, distinta por componente.
for d in (1, 2, 3):
    for e in EA:
        add(M.Asistencia(colegio_id=col.id, estudiante_id=e.id, curso_id=A.id, asignatura_id=hlm_le,
                         fecha=dt.date(2026, 9, d), estado='presente'))
        add(M.Asistencia(colegio_id=col.id, estudiante_id=e.id, curso_id=A.id, asignatura_id=hcs_cs,
                         fecha=dt.date(2026, 9, d), estado='ausente' if d == 2 else 'presente'))
db.commit()

import registro_escolar as RE
G = RE.GRADO_CONFIG[4]
AZUL = 0xb3


def spans(p, color=AZUL):
    return [(s['text'].strip(), s['bbox']) for b in p.get_text('dict')['blocks'] for l in b.get('lines', [])
            for s in l['spans'] if s['text'].strip() and (color is None or s['color'] == color)]


def guardar(nombre, data):
    if OUT:
        open(os.path.join(OUT, nombre), 'wb').write(data)


def revisar_registro(pdf, etiqueta, ests, so_esperado):
    """so_esperado: [(componente, base, salida_nombre, nombre_componente), ...] en orden."""
    doc = pymupdf.open(stream=pdf, filetype='pdf')
    for comp_cod, base, sal_nom, comp_nom in so_esperado:
        slot = __import__('salidas_optativas').componente(comp_cod).slot
        pc = doc[G['calificaciones_salida_optativa'][slot] - 1]
        nums = {t for t, _ in spans(pc)}
        check('%s calificaciones de %s (pág %d) con sus notas' % (etiqueta, comp_cod, pc.number + 1),
              {str(base), str(base + 1), str(base + 2)} <= nums, sorted(nums)[:20])
        pcomp = doc[G['completiva_salida_optativa'][slot] - 1]
        check('%s completiva de %s (pág %d) con datos' % (etiqueta, comp_cod, pcomp.number + 1),
              str(base) in {t for t, _ in spans(pcomp)}, spans(pcomp)[:6])
    for i, (comp_cod, base, sal_nom, comp_nom) in enumerate(so_esperado):
        for pag in RE.ASISTENCIA_SALIDA_OPTATIVA_CICLO_2[i]:
            txt = ' '.join(t for t, _ in spans(doc[pag - 1]))
            if not (sal_nom in txt and comp_nom in txt):
                check('%s asistencia bloque %d pág %d rotulada %s / %s' % (etiqueta, i + 1, pag, sal_nom, comp_nom),
                      False, txt[:200])
                break
        else:
            check('%s asistencia bloque %d (págs %d-%d): %s / %s' % (
                etiqueta, i + 1, RE.ASISTENCIA_SALIDA_OPTATIVA_CICLO_2[i][0],
                RE.ASISTENCIA_SALIDA_OPTATIVA_CICLO_2[i][-1], sal_nom, comp_nom), True)
    p = doc[225]
    todos = spans(doc[224])          # apellidos y nombres van en la pág 225
    for k, e in enumerate(ests):
        fila = [bb for t, bb in todos if t == e.apellido]
        if not fila:
            check('%s acta: fila de %s' % (etiqueta, e.apellido), False, 'apellido no encontrado')
            continue
        yc = (fila[0][1] + fila[0][3]) / 2
        so = {}
        for col_n, (x0, x1) in ((1, (390, 461)), (2, (461, 532))):
            so[col_n] = sorted(t for t, bb in spans(p) if x0 <= (bb[0] + bb[2]) / 2 < x1
                               and abs((bb[1] + bb[3]) / 2 - yc) < 4)
        esperado = {n + 1: [str(b + k)] for n, (_, b, _, _) in enumerate(so_esperado)}
        check('%s acta fila %d (%s): SO1=%s SO2=%s' % (etiqueta, k + 1, e.apellido, so.get(1), so.get(2)),
              all(esperado[n][0] in so[n] for n in esperado), (so, esperado))
    return doc


SO_A = [('HLM-LE-4', 66, 'Humanidades y Lenguas Modernas', 'Apreciación y Producción Literarias'),
        ('HCS-CS-4', 77, 'Humanidades y Ciencias Sociales', 'Filosofía Social y Pensamiento Dominicano')]
r = c.get('/api/registros/secundaria/%d?force=true' % A.id, headers=HD)
check('D1 Registro oficial de 4to A: 200 PDF', r.status_code == 200 and r.content[:4] == b'%PDF', r.text[:200])
if r.status_code == 200:
    guardar('registro_4toA_HLM-LE_HCS-CS_oficial.pdf', r.content)
    doc = revisar_registro(r.content, 'D2 oficial:', EA, SO_A)
    troncal = doc[G['calificaciones_paginas'][0] - 1]
    check('D3 la troncal Lengua Española conserva sus notas (81) en su página',
          '81' in {t for t, _ in spans(troncal)}, spans(troncal)[:8])
r = c.get('/api/registros/secundaria/%d/preview-pdf' % A.id, headers=HD)
check('D4 Borrador de 4to A: 200 PDF', r.status_code == 200 and r.content[:4] == b'%PDF', r.text[:200])
if r.status_code == 200:
    guardar('registro_4toA_HLM-LE_HCS-CS_borrador.pdf', r.content)
    revisar_registro(r.content, 'D5 borrador:', EA, SO_A)


def filas_boletin(pdf_bytes, pagina=1):
    doc = pymupdf.open(stream=pdf_bytes, filetype='pdf')
    p = doc[pagina]
    out = {}
    for etiqueta, (y0, y1) in (('SO1', (366.3, 391.6)), ('SO2', (391.6, 416.9))):
        palabras = [w for w in p.get_text('words') if y0 <= (w[1] + w[3]) / 2 <= y1 and w[0] >= 63]
        out[etiqueta] = (' '.join(w[4] for w in palabras if w[0] < 163),
                         ' '.join(w[4] for w in palabras if 660 < w[0] < 690))
    return doc, out


# Música (materia extra del colegio) con notas para el estudiante 1.
for comp in (1, 2, 3, 4):
    add(M.CalificacionSecundaria(colegio_id=col.id, estudiante_id=EA[0].id, asignatura_id=musica.id,
                                 ano_escolar_id=ano.id, competencia_numero=comp, p1=95, p2=95, p3=95, p4=95))
db.commit()
r = c.get('/api/boletines/estudiante/%d/pdf-minerd-v2' % EA[0].id, headers=HD)
check('D6 Boletín individual de 4to A: 200 PDF', r.status_code == 200 and r.content[:4] == b'%PDF', r.text[:200])
if r.status_code == 200:
    guardar('boletin_4toA_estudiante1_con_musica.pdf', r.content)
    _, f = filas_boletin(r.content)
    check('D7 boletín SO1 = Apreciación y Producción Literarias (completo), CF 66',
          f['SO1'][0] == 'Apreciación y Producción Literarias' and f['SO1'][1] == '66', f)
    check('D8 boletín SO2 = Filosofía Social y Pensamiento Dominicano (completo), CF 77',
          f['SO2'][0] == 'Filosofía Social y Pensamiento Dominicano' and f['SO2'][1] == '77', f)
    check('D9 Música no desplaza a ninguna optativa', 'Música' not in f['SO1'][0] + f['SO2'][0], f)
r = c.get('/api/boletines/curso/%d/pdf-minerd-v2' % A.id, headers=HD)
check('D10 Boletines por lote de 4to A: 200 PDF', r.status_code == 200 and r.content[:4] == b'%PDF', r.text[:200])
if r.status_code == 200:
    guardar('boletines_4toA_lote.pdf', r.content)
    doc = pymupdf.open(stream=r.content, filetype='pdf')
    for k in range(len(EA)):
        _, f = filas_boletin(r.content, 2 * k + 1)
        check('D11 lote, estudiante %d: SO1 CF %d y SO2 CF %d en el mismo orden' % (k + 1, 66 + k, 77 + k),
              f['SO1'][0].startswith('Apreciación') and f['SO1'][1] == str(66 + k)
              and f['SO2'][0].startswith('Filosofía') and f['SO2'][1] == str(77 + k), f)

# Tres componentes escritos por otra vía (no por la API): ningún documento.
import salida_optativa_service as SVC
H_ = curso('H', salida='HLM')
add(M.AsignacionProfesor(colegio_id=col.id, profesor_id=julio.id, curso_id=H_.id, asignatura_id=lengua.id,
                         ano_escolar_id=ano.id, activo=True, es_titular=True))
db.commit()
EH = estudiantes(H_, 'H')
extra = []
for cod in ('HLM-LE-4', 'HLM-IN-4', 'HCS-CS-4'):
    a_ = add(M.Asignatura(colegio_id=col.id, nombre=cod, codigo=cod, area='', area_curricular_codigo=None, activo=True))
    add(M.CursoComponenteOptativo(colegio_id=col.id, curso_id=H_.id, ano_escolar_id=ano.id, componente_codigo=cod,
                                  asignatura_id=a_.id, activo=True))
    for comp in (1, 2, 3, 4):
        add(M.CalificacionSecundaria(colegio_id=col.id, estudiante_id=EH[0].id, asignatura_id=a_.id,
                                     ano_escolar_id=ano.id, competencia_numero=comp, p1=70, p2=70, p3=70, p4=70))
db.commit()
for nombre, url in (('Registro oficial', '/api/registros/secundaria/%d' % H_.id),
                    ('Borrador', '/api/registros/secundaria/%d/preview-pdf' % H_.id),
                    ('Boletín individual', '/api/boletines/estudiante/%d/pdf-minerd-v2' % EH[0].id),
                    ('Boletines por lote', '/api/boletines/curso/%d/pdf-minerd-v2' % H_.id)):
    r = c.get(url, headers=HD)
    js = r.json() if r.headers.get('content-type', '').startswith('application/json') else {}
    check('D12 3 componentes -> %s: 409 que nombra HCS-CS-4, sin PDF' % nombre,
          r.status_code == 409 and js.get('motivo') == 'capacidad_registro' and 'HCS-CS-4' in js.get('error', ''),
          (r.status_code, r.text[:200]))
estH = c.get('/api/cursos/%d/salida-optativa' % H_.id, headers=HD).json()
check('D13 la pantalla avisa del exceso (3 de 2) sin ocultar ninguno',
      estH['excede_capacidad'] and estH['espacios_en_uso'] == 3 and len(estH['componentes']) == 3, estH)

# =====================================================================
print('\n=== E. Curso de una sola salida: igual que antes ===')
BASE_B = {lengua.id: 81, sociales.id: 84, mB['HLM-LE-4']: 61, mB['HLM-IN-4']: 71}
for i, e in enumerate(EB):
    for asig, base in BASE_B.items():
        for comp in (1, 2, 3, 4):
            v = base + i
            add(M.CalificacionSecundaria(colegio_id=col.id, estudiante_id=e.id, asignatura_id=asig,
                                         ano_escolar_id=ano.id, competencia_numero=comp, p1=v, p2=v, p3=v, p4=v))
for d in (1, 2, 3):
    for e in EB:
        for asig in (mB['HLM-LE-4'], mB['HLM-IN-4']):
            add(M.Asistencia(colegio_id=col.id, estudiante_id=e.id, curso_id=B.id, asignatura_id=asig,
                             fecha=dt.date(2026, 9, d), estado='presente'))
horarios(B)
db.commit()
r = c.get('/api/registros/secundaria/%d?force=true' % B.id, headers=HD)
check('E1 Registro de 4to B (solo HLM): 200 PDF', r.status_code == 200 and r.content[:4] == b'%PDF', r.text[:200])
if r.status_code == 200:
    guardar('registro_4toB_solo_HLM.pdf', r.content)
    revisar_registro(r.content, 'E2 4to B:', EB, [
        ('HLM-LE-4', 61, 'Humanidades y Lenguas Modernas', 'Apreciación y Producción Literarias'),
        ('HLM-IN-4', 71, 'Humanidades y Lenguas Modernas', 'Manejo de la Información en Inglés')])

db.close()
engine.dispose()
print('\n%d PASARON / %d FALLARON' % (len(OK), len(MAL)))
sys.exit(1 if MAL else 0)
