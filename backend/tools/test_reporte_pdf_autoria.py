"""PDF del reporte de conducta para padres: «Reportado por» y «Asignatura del reporte».

  A. Generador (sin base):
     * «Reportado por: <nombre del autor>» (sin el rol);
     * sin asignatura identificada NO hay línea de asignatura;
     * con asignatura identificada, la línea aparece; nombres largos caben;
     * el contenido del reporte (descripción, acciones, firmas) sigue igual.
  B. Endpoint real, base SQLite AISLADA y datos sintéticos:
     * un profesor que da DOS materias en el curso crea un reporte: el PDF lo
       nombra como autor y NO le atribuye ninguna materia (no se deduce de sus
       asignaciones);
     * permisos y aislamiento: otro profesor no lo imprime (403), la Dirección
       de otro colegio tampoco (404);
     * doble envío con la misma clave: un solo reporte;
     * no se envía nada a los padres.

Uso (desde backend/):  python tools/test_reporte_pdf_autoria.py [carpeta_pdfs]
"""
import datetime as dt
import os
import sys
import tempfile
import uuid

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(BK, 'tools'))
OUT = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix='reporte_pdf_')
os.makedirs(OUT, exist_ok=True)
from test_utils import aislar_base_de_datos, verificar_engine_aislado

TMP = aislar_base_de_datos('reporte_pdf_autoria')
from database import engine, SessionLocal
verificar_engine_aislado(engine, TMP)
import models as M
import app as APP
import pymupdf
from fastapi.testclient import TestClient
from auth import create_token
from reporte_conducta_pdf import generar_reporte_conducta_pdf

M.Base.metadata.create_all(bind=engine)
OK, MAL = [], []


def check(nombre, cond, detalle=''):
    (OK if cond else MAL).append(nombre)
    print('  %s %s %s' % ('PASA ' if cond else 'FALLA', nombre, '' if cond else str(detalle)[:300]))


class Obj:
    def __init__(self, **k):
        self.__dict__.update(k)


def texto(pdf):
    return pymupdf.open(stream=pdf, filetype='pdf')[0].get_text()


def palabras(pdf):
    return pymupdf.open(stream=pdf, filetype='pdf')[0].get_text('words')


# ===================================================================== A
print('\n=== A. Generador ===')
rep = Obj(id=7, numero_reporte='REP-2026-0007', fecha=dt.datetime(2026, 10, 20, 10, 30), gravedad='moderada',
          descripcion='El estudiante interrumpió la clase en varias ocasiones.', acciones_centro='Conversación con el estudiante.',
          acciones_hogar='Conversar en casa sobre el respeto en clase.', respuesta=None, estado='respondido',
          confirmado_padre=False, enviado_padres=False, fecha_respuesta=dt.datetime(2026, 10, 21, 9, 0))
est = Obj(nombre='María', apellido='Rodríguez Peña', matricula='2026-0101', padre_nombre='Ana Peña',
          padre_telefono='', madre_nombre='', tutor_nombre='')
autor = Obj(nombre='Julio Alberto', apellido='Sena', role='profesor')
comunes = dict(reporte=rep, estudiante=est, curso=Obj(nombre='A'), grado=Obj(nombre='4to Secundaria'),
               tanda=Obj(nombre='Matutina'), reportador=autor, respondedor=None, config=None,
               colegio=Obj(nombre='Colegio Sintético'), ano_escolar='2026-2027')
pdf_sin = generar_reporte_conducta_pdf(**comunes)
pdf_con = generar_reporte_conducta_pdf(**comunes, asignatura_nombre='Lengua Española')
pdf_largo = generar_reporte_conducta_pdf(**dict(comunes, reportador=Obj(
    nombre='María de los Ángeles Altagracia', apellido='Fernández de la Rosa Santos', role='profesor')),
    asignatura_nombre='Formación Integral Humana y Religiosa')
for n, d in (('reporte_sin_asignatura_identificada.pdf', pdf_sin), ('reporte_con_asignatura_identificada.pdf', pdf_con),
             ('reporte_nombres_largos.pdf', pdf_largo)):
    open(os.path.join(OUT, n), 'wb').write(d)
t_sin, t_con = texto(pdf_sin), texto(pdf_con)
check('A1 «Reportado por» con el nombre del autor', 'REPORTADO POR:' in t_sin and 'Julio Alberto Sena' in t_sin, t_sin[-600:])
check('A2 el nombre va sin el rol', '(Profesor)' not in t_sin, '')
check('A3 sin asignatura identificada no hay línea de asignatura', 'ASIGNATURA DEL REPORTE' not in t_sin, '')
check('A4 con asignatura identificada: «Asignatura del reporte: Lengua Española»',
      'ASIGNATURA DEL REPORTE:' in t_con and 'Lengua Española' in t_con, '')
ancho = pymupdf.open(stream=pdf_largo, filetype='pdf')[0].rect.width
check('A5 nombres largos caben dentro de los márgenes',
      all(w[2] <= ancho - 0.5 * 72 + 0.5 for w in palabras(pdf_largo)), max(w[2] for w in palabras(pdf_largo)))
check('A6 el contenido del reporte sigue: descripción, acciones, estado y firmas',
      all(s in t_con for s in ('interrumpió la clase', 'Conversación con el estudiante', 'Conversar en casa',
                               'ESTADO:', 'Padre / Tutor', 'Coordinación / Dirección')), '')
y_aut = min(w[1] for w in palabras(pdf_con) if w[4] == 'REPORTADO')
y_firma = min(w[1] for w in palabras(pdf_con) if w[4] == 'Coordinación')
check('A7 la franja de autoría queda por encima de las firmas', y_aut < y_firma, (y_aut, y_firma))

# ===================================================================== B
print('\n=== B. Endpoint real ===')
db = SessionLocal()


def add(o):
    db.add(o)
    db.flush()
    return o


def colegio(cod):
    col = add(M.Colegio(nombre='Colegio %s' % cod, codigo=cod, activo=True))
    ano = add(M.AnoEscolar(colegio_id=col.id, nombre='2026-2027', activo=True, cerrado=False,
                           fecha_inicio=dt.date(2026, 9, 1), fecha_fin=dt.date(2027, 6, 30)))
    g = add(M.Grado(colegio_id=col.id, nombre='4to Secundaria', nivel='secundaria', orden=4, activo=True))
    cur = add(M.Curso(colegio_id=col.id, nombre='A', grado_id=g.id, ano_escolar_id=ano.id, activo=True))
    return col, ano, cur


def usuario(col, u, n, a, r):
    return add(M.Usuario(colegio_id=col.id, username=u, password_hash='x', nombre=n, apellido=a, role=r, activo=True,
                         must_change_password=False, token_version=0))


colA, anoA, curA = colegio('REPA')
colB, anoB, curB = colegio('REPB')
dirA = usuario(colA, 'repa_dir', 'Dir', 'A', 'direccion')
dirB = usuario(colB, 'repb_dir', 'Dir', 'B', 'direccion')
julio = usuario(colA, 'repa_julio', 'Julio Alberto', 'Sena', 'profesor')
otro = usuario(colA, 'repa_otro', 'Ana', 'Mejía', 'profesor')
for nombre in ('Lengua Española', 'Música'):        # Julio da DOS materias en el curso
    a = add(M.Asignatura(colegio_id=colA.id, nombre=nombre, codigo=nombre[:3].upper()))
    add(M.AsignacionProfesor(colegio_id=colA.id, profesor_id=julio.id, curso_id=curA.id, asignatura_id=a.id,
                             ano_escolar_id=anoA.id, activo=True))
aO = add(M.Asignatura(colegio_id=colA.id, nombre='Matemática', codigo='MAT'))
add(M.AsignacionProfesor(colegio_id=colA.id, profesor_id=otro.id, curso_id=curA.id, asignatura_id=aO.id,
                         ano_escolar_id=anoA.id, activo=True))
estA = add(M.Estudiante(colegio_id=colA.id, nombre='María', apellido='Rodríguez', curso_id=curA.id, activo=True,
                        no_lista=1, fecha_ingreso=dt.date(2026, 8, 20)))
db.commit()
c = TestClient(APP.app)
H = lambda u: {'Authorization': 'Bearer ' + create_token(u)}
clave = uuid.uuid4().hex
cuerpo = {'estudiante_id': estA.id, 'titulo': 'Interrupción en clase', 'descripcion': 'Interrumpió varias veces.',
          'tipo': 'conducta', 'gravedad': 'leve', 'client_request_id': clave}
r1 = c.post('/api/reportes', headers=H(julio), json=cuerpo)
r2 = c.post('/api/reportes', headers=H(julio), json=cuerpo)
db.expire_all()
reps = db.query(M.ReporteConducta).filter_by(estudiante_id=estA.id).all()
check('B1 el profesor crea el reporte (200/201)', r1.status_code in (200, 201), r1.text[:200])
check('B2 doble envío con la misma clave: un solo reporte', len(reps) == 1 and r2.status_code in (200, 201),
      (len(reps), r2.status_code))
rid = reps[0].id
r = c.get('/api/reportes/%d/pdf' % rid, headers=H(julio))
check('B3 el autor descarga el PDF', r.status_code == 200 and r.content[:4] == b'%PDF', r.text[:200])
if r.status_code == 200:
    open(os.path.join(OUT, 'reporte_endpoint_real.pdf'), 'wb').write(r.content)
    t = texto(r.content)
    check('B4 el PDF dice «Reportado por: Julio Alberto Sena»', 'REPORTADO POR:' in t and 'Julio Alberto Sena' in t, '')
    check('B5 NO atribuye materia aunque el autor dé Lengua y Música en ese curso',
          'ASIGNATURA DEL REPORTE' not in t and 'Lengua Española' not in t and 'Música' not in t, '')
r = c.get('/api/reportes/%d/pdf' % rid, headers=H(otro))
check('B6 otro profesor del curso no imprime un reporte ajeno (403)', r.status_code == 403, r.status_code)
r = c.get('/api/reportes/%d/pdf' % rid, headers=H(dirB))
check('B7 la Dirección de otro colegio no lo ve (404)', r.status_code == 404, r.status_code)
r = c.get('/api/reportes/%d/pdf' % rid, headers=H(dirA))
check('B8 la Dirección del colegio sí lo imprime', r.status_code == 200, r.status_code)
db.expire_all()
rep_db = db.get(M.ReporteConducta, rid)
check('B9 no se envió nada a los padres', not rep_db.enviado_padres
      and db.query(M.HistorialReportePadres).count() == 0, (rep_db.enviado_padres,))

db.close()
engine.dispose()
print('\n%d PASARON / %d FALLARON' % (len(OK), len(MAL)))
sys.exit(1 if MAL else 0)
