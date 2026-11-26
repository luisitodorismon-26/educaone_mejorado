# -*- coding: utf-8 -*-
"""
MEM-REG · Huella del Registro de Secundaria para comparar dos versiones del código.

Siembra una base SINTÉTICA temporal (REG-43: 1ro A con 40 estudiantes, 1ro B con
43 -plantilla ampliada-, 1ro C con 44 -excede-), genera el Registro oficial y el
borrador con varios roles y escribe en JSON, por caso: estado HTTP, tipo, nº de
páginas, huella normalizada de cada página (contenido y recursos, sin fechas ni
ids internos) y el cuerpo de los rechazos. Ejecutándolo con `main` y con la rama
se comprueba que contenido, páginas, validaciones y permisos quedan iguales.

    cd <carpeta temporal>
    python <repo>/backend/tools/huella_registro_secundaria.py <salida.json> [<carpeta backend>]
"""
import hashlib
import json
import os
import re
import sys

SALIDA = os.path.abspath(sys.argv[1])
BK = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(BK, 'tools'))
os.environ.setdefault('DISABLE_GLOBAL_RATE_LIMIT', 'true')
os.environ.setdefault('ENLACE_FAMILIA_SECRET', 'clave-enlaces-sintetica-huella-registro-0123456789')
os.environ.setdefault('ENLACE_FAMILIA_BASE_URL', 'https://educaone.ejemplo.invalid')

from test_utils import aislar_base_de_datos  # noqa: E402
TMP = aislar_base_de_datos('mem_reg_huella')
from database import engine, SessionLocal  # noqa: E402
from test_utils import verificar_engine_aislado  # noqa: E402
verificar_engine_aislado(engine, TMP)
import logging  # noqa: E402
logging.disable(logging.WARNING)
from fastapi.testclient import TestClient  # noqa: E402
import io  # noqa: E402
from pypdf import PdfReader  # noqa: E402
import models as M  # noqa: E402
import app as APP  # noqa: E402
from auth import create_token  # noqa: E402
import registro_43_semilla as S  # noqa: E402

M.Base.metadata.create_all(bind=engine)
with TestClient(APP.app):
    pass
db = SessionLocal()
sem = S.sembrar(db, M, [(1, 'A', 40), (1, 'B', 43), (1, 'C', 44)])
col = sem['colegio']


def usuario(colegio_id, username, role):
    u = M.Usuario(colegio_id=colegio_id, username=username, password_hash='x', nombre=username, apellido='T',
                  role=role, activo=True, must_change_password=False, token_version=0)
    db.add(u); db.flush()
    return u


COORD = usuario(col.id, 'mem_coord', 'coordinador')
SECRE = usuario(col.id, 'mem_secre', 'secretaria')
PROF_SIN = usuario(col.id, 'mem_prof_sin', 'profesor')        # sin asignación en esos cursos
OTRO = M.Colegio(nombre='Otro colegio sintético', codigo='MEMOTRO', activo=True)
db.add(OTRO); db.flush()
DIR_OTRO = usuario(OTRO.id, 'mem_dir_otro', 'direccion')
PROF_TIT = db.query(M.Usuario).filter_by(username='reg43_prof0').first()  # titular, asignado
db.commit()
client = TestClient(APP.app)


def huella_pdf(datos):
    r = PdfReader(io.BytesIO(datos))
    paginas = []
    for p in r.pages:
        cont = p.get_contents()
        bruto = cont.get_data() if cont is not None else b''
        rec = p.get('/Resources')
        recursos = sorted(str(k) for k in (rec.get_object().keys() if rec is not None else []))
        xo = rec.get_object().get('/XObject') if rec is not None else None
        xobjs = []
        if xo is not None:
            for k, v in sorted(xo.get_object().items()):
                o = v.get_object()
                xobjs.append((str(k), hashlib.sha256(o.get_data()).hexdigest()[:16]))
        paginas.append(hashlib.sha256(repr((bruto, recursos, xobjs, [float(x) for x in p.mediabox])).encode()).hexdigest()[:16])
    return {'paginas': len(r.pages), 'huellas': paginas,
            'documento': hashlib.sha256(''.join(paginas).encode()).hexdigest()[:16]}


def pedir(usr, ruta):
    resp = client.get(ruta, headers={'Authorization': 'Bearer ' + create_token(usr)})
    out = {'estado': resp.status_code, 'tipo': resp.headers.get('content-type', '').split(';')[0]}
    if resp.status_code == 200 and out['tipo'] == 'application/pdf':
        out.update(huella_pdf(resp.content))
        out['disposicion'] = re.sub(r'\d{4}-\d{4}', 'AAAA', resp.headers.get('content-disposition', ''))
    else:
        try:
            cuerpo = resp.json()
        except Exception:
            cuerpo = resp.text[:300]
        out['cuerpo'] = cuerpo
    return out


cursos = {k: v.id for k, v in sem['cursos'].items()}
casos = {}
for etiqueta_u, usr in (('direccion', sem['director']), ('coordinador', COORD), ('secretaria', SECRE),
                        ('profesor_titular', PROF_TIT), ('profesor_sin_asignar', PROF_SIN), ('otro_colegio', DIR_OTRO)):
    for sec, cid in cursos.items():
        for tipo, ruta in (('oficial', '/api/registros/secundaria/%d' % cid),
                           ('oficial_force', '/api/registros/secundaria/%d?force=true' % cid),
                           ('borrador', '/api/registros/secundaria/%d/preview-pdf' % cid)):
            casos['%s|%s|%s' % (etiqueta_u, sec, tipo)] = pedir(usr, ruta)
casos['direccion|inexistente|oficial'] = pedir(sem['director'], '/api/registros/secundaria/999999')
casos['direccion|inexistente|borrador'] = pedir(sem['director'], '/api/registros/secundaria/999999/preview-pdf')
casos['sin_sesion|A|oficial'] = {'estado': client.get('/api/registros/secundaria/%d' % cursos['A']).status_code}
json.dump(casos, open(SALIDA, 'w', encoding='utf-8'), indent=1, ensure_ascii=False, sort_keys=True)
resumen = {}
for k, v in casos.items():
    resumen.setdefault(v['estado'], 0)
    resumen[v['estado']] += 1
print('casos:', len(casos), 'por estado:', resumen)
