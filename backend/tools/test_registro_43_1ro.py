# -*- coding: utf-8 -*-
"""
EducaOne REG-43 — Registro de 1ro de Secundaria con 41-43 estudiantes.

CUÁNDO SE USA CADA PLANTILLA
    · hasta 40 estudiantes (cualquier grado) -> plantilla oficial, sin cambios;
    · 1ro con 41-43                          -> plantilla ampliada de 43 filas;
    · más de 43 en 1ro, o más de 40 en otro grado -> no se emite: error claro,
      ningún estudiante recortado.

LO QUE SE COMPRUEBA, en 1ro con 40, 41, 42 y 43, por los dos recorridos de
descarga de la interfaz (oficial: GET /api/registros/secundaria/{id};
borrador: .../preview-pdf). "Su estudiante" = el i-ésimo por número de lista
(con huecos y alta en otro orden); los valores esperados salen de la semilla,
no del generador:
    · pág 17 (asistencia de Lengua, sep-oct): 40 o 43 números de fila
      impresos y, en cada fila, la secuencia de marcas de su estudiante;
    · pág 11 (datos generales): cédulas = todos, en orden, una vez;
    · pág 131 (calificaciones de Lengua): todas las notas de la fila;
    · págs 47, 50 y 53 (asistencia compacta de Ed. Artística, Ed. Física y FIHR,
      sep-dic): la secuencia completa de marcas de la fila;
    · págs 150-158 (completivas de las 9 asignaturas): la secuencia exacta de
      columnas con dato (CF, 50 % CF, CEC, 50 % CEC, CF completiva, 30 % CF,
      CEEX, 70 % CEEX, CF extraordinaria, nota A);
    · págs 159 y 160 (acta): apellido y nombre, y final/completivo/extraordinario
      de cada asignatura;
    · en todas esas páginas: filas sobrantes vacías, nada fuera de la tabla y,
      con 41-43, las filas 41-n por separado (con contenido y de sus estudiantes).
    · 44 en 1ro y 41 en 2do: validador, endpoints y generador lo rechazan con
      el motivo, y la vista previa de la interfaz lo muestra.
    · Contexto: generaciones simultáneas de 43, 40 y 41 en hilos distintos usan
      cada una su plantilla; tras una excepción durante la generación (error real
      del dibujo, excepción arbitraria, y en un hilo reutilizado) no queda
      plantilla activa y la siguiente generación de 40 usa la de 40.
NO se comprueban fila a fila: condición inicial (12), emergencias y parentesco
(13-14), asistencia a evaluaciones (56-61, la plantilla las deja en blanco), el
resto de páginas de asistencia (18-46, 48-49, 51-52, 54-55) y de calificaciones
(132-148); su plantilla sí se verificó píxel a píxel al fabricarla.

Base SQLite temporal (test_utils), datos sintéticos (registro_43_semilla).

Uso:
    cd backend
    python tools/test_registro_43_1ro.py [dir_pdfs]
"""
import datetime as dt
import os
import sys
import threading

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(BK, "tools"))

from test_utils import aislar_base_de_datos, verificar_engine_aislado  # noqa: E402

TMP = aislar_base_de_datos('reg43_1ro')

from database import engine, SessionLocal  # noqa: E402
verificar_engine_aislado(engine, TMP)

import models as M  # noqa: E402
import app as APP  # noqa: E402
import registro_escolar as RE  # noqa: E402
import registro_validator as RV  # noqa: E402
import registro_43_semilla as S  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from auth import create_token  # noqa: E402
import pymupdf  # noqa: E402

M.Base.metadata.create_all(bind=engine)
SALIDA = sys.argv[1] if len(sys.argv) > 1 else None
PASARON, FALLARON = [], []
AZUL, GRIS = 0x0000b3, 0x231f20
LETRA = {'presente': 'P', 'ausente': 'A', 'tardanza': 'T'}
# Franja de filas (y de la primera y la última línea) medida en la plantilla:
# es la misma en la oficial y en la ampliada; cambia el número de filas.
FRANJA = {11: (180.2, 746.7), 17: (180.1, 747.0), 131: (180.7, 747.5), 159: (179.9, 746.5),
          160: (179.9, 746.5)}
FRANJA.update({p: (180.5, 747.4) for p in range(47, 56)})     # asistencia compacta (4 meses x 10)
FRANJA.update({p: (179.6, 746.5) for p in range(150, 159)})   # completivas, una página por asignatura
from boletin_minerd_secundaria import _fmt_nota  # noqa: E402  (solo el formato del número impreso)


def esperado_completiva(nl):
    """Las columnas con dato de la fila de Completivas, en orden, calculadas desde la
    semilla (no desde el generador): CF, 50% CF, CEC, 50% CEC, CF completiva,
    30% CF, CEEX, 70% CEEX, CF extraordinaria y la nota de la columna A."""
    v, ev = S.nota(nl), S.evaluacion_extra(nl)
    out = [v]
    if v < 70:
        out.append(round(v * 0.5, 1))
    if ev:
        out += [ev['cec'], round(ev['cec'] * 0.5, 1), ev['completiva_final']]
        if 'ceex' in ev:
            out += [round(v * 0.3, 1), ev['ceex'], round(ev['ceex'] * 0.7, 1), ev['extraordinaria_final']]
        out.append(ev['nota_final'])
    else:
        out.append(v)                           # aprobado: la CF va también en la columna A
    return [_fmt_nota(x) for x in out]


def esperado_acta(nl, asignaturas):
    """Por asignatura: final (CF), completivo, extraordinario (las que tengan dato)."""
    v, ev = S.nota(nl), S.evaluacion_extra(nl) or {}
    una = [_fmt_nota(x) for x in (v, ev.get('completiva_final'), ev.get('extraordinaria_final')) if x is not None]
    return una * asignaturas


def letras_mes(nl, idx_asig, meses):
    return ''.join(LETRA[S.estado(nl, f)] for f in S.fechas_asignatura(idx_asig) if (f.year, f.month) in meses)


SEP_DIC = ((2025, 9), (2025, 10), (2025, 11), (2025, 12))


def check(nombre, cond, detalle=''):
    (PASARON if cond else FALLARON).append(nombre)
    print("  %s  %-78s %s" % ('PASA ' if cond else 'FALLA', nombre, '' if cond else str(detalle)[:400]))


def spans(page):
    for b in page.get_text('dict')['blocks']:
        for ln in b.get('lines', []):
            for sp in ln['spans']:
                t = sp['text'].strip()
                if t:
                    x0, y0, x1, y1 = sp['bbox']
                    yield t, x0, (y0 + y1) / 2, sp['color']


def por_fila(page, pag, filas):
    """{fila: [(x, texto)]} con el texto del generador, y los números de fila impresos."""
    y0, y1 = FRANJA[pag]
    h = (y1 - y0) / filas
    datos, numeros, fuera = {}, {}, []
    for t, x, cy, color in spans(page):
        if not (y0 - 0.5 <= cy <= y1 + 0.5):
            continue
        r = int((cy - y0) // h)
        if color == GRIS and t.isdigit() and x < 70:
            numeros[r] = t
        elif color == AZUL:
            if 0 <= r < filas:
                datos.setdefault(r, []).append((x, t))
            else:
                fuera.append(t)
    return {r: [t for _, t in sorted(v)] for r, v in datos.items()}, numeros, fuera


print("\n=== Semilla: 1ro con 40, 41, 42, 43 y 44; 2do con 41 (números de lista con huecos) ===")
db = SessionLocal()
CASOS = [(1, 'A', 40), (1, 'B', 41), (1, 'C', 42), (1, 'D', 43), (1, 'E', 44), (2, 'F', 41)]
sem = S.sembrar(db, M, CASOS)
client = TestClient(APP.app)
H = {'Authorization': 'Bearer ' + create_token(sem['director'])}
check('semilla: los números de lista tienen huecos (1..4, 6..9, ...)', S.no_listas(9) == [1, 2, 3, 4, 6, 7, 8, 9, 11])

print("\n=== Selección de plantilla (unidad) ===")
check('1ro con 40 -> plantilla oficial', RE.seleccionar_plantilla(1, 40) is None)
check('1ro con 41 y con 43 -> plantilla ampliada',
      RE.seleccionar_plantilla(1, 41)['filas'] == 43 and RE.seleccionar_plantilla(1, 43)['filas'] == 43)
for g, n in ((1, 44), (2, 41), (3, 41), (4, 41), (6, 41)):
    try:
        RE.seleccionar_plantilla(g, n)
        check('%d° con %d -> rechazado' % (g, n), False, 'no rechazó')
    except RE.RegistroExcedePlantilla as e:
        check('%d° con %d -> rechazado con mensaje' % (g, n),
              e.detalle['motivo'] == 'ESTUDIANTES_EXCEDEN_PLANTILLA' and str(n) in e.detalle['error'],
              e.detalle)

def solo_letras(toks):
    return ''.join(t for t in toks if t in ('P', 'A', 'T', 'E'))


def filas_por_estudiante(tag, doc, pag, filas, ests, n, que, esperado, extraer):
    """Cada fila 1..n = lo de SU estudiante (orden por número de lista); filas
    sobrantes vacías; y, si el curso pasa de 40, las filas 41..n por separado:
    con contenido y con los valores de sus estudiantes."""
    d, _, fuera = por_fila(doc[pag - 1], pag, filas)
    mal = []
    for i, e in enumerate(ests):
        got, exp = extraer(d.get(i, [])), esperado(e)
        if got != exp:
            mal.append((i + 1, e.no_lista, got, exp))
    check('%s: pág %d %s: cada fila = SU estudiante' % (tag, pag, que), not mal, mal[:2])
    check('%s: pág %d filas sobrantes vacías y nada fuera de la tabla' % (tag, pag),
          not [i for i in range(n, filas) if d.get(i)] and not fuera, fuera[:3])
    if n > 40:
        sin_dato = [i + 1 for i in range(40, n) if not d.get(i)]
        mal41 = [m for m in mal if m[0] > 40]
        check('%s: pág %d filas 41-%d con contenido y de SUS estudiantes' % (tag, pag, n),
              not sin_dato and not mal41, (sin_dato, mal41[:2]))


ESPERADA = {40: 40, 41: 43, 42: 43, 43: 43}
for g, sec, n in CASOS:
    curso = sem['cursos'][sec]
    ests = sorted(db.query(M.Estudiante).filter_by(curso_id=curso.id, activo=True).all(), key=lambda e: e.no_lista)
    v = RV.validar_registro_secundaria(db, curso.id, sem['colegio'].id)
    if g == 1 and n <= 43:
        print("\n=== 1ro sección %s: %d estudiantes (plantilla de %d filas) ===" % (sec, n, ESPERADA[n]))
        check('%s: validador sin errores ni advertencias' % sec, not v.errors and not v.warnings,
              (v.errors[:2], v.warnings[:2]))
        check('%s: el validador anuncia la plantilla ampliada solo si hace falta' % sec,
              bool(v.info.get('plantilla_ampliada')) == (n > 40), v.info.get('plantilla_ampliada'))
        filas = ESPERADA[n]
        for recorrido, url in (('oficial', '/api/registros/secundaria/%d' % curso.id),
                               ('borrador', '/api/registros/secundaria/%d/preview-pdf' % curso.id)):
            r = client.get(url, headers=H)
            ok = r.status_code == 200 and r.headers.get('content-type') == 'application/pdf'
            check('%s %s: descarga 200 application/pdf' % (sec, recorrido), ok, (r.status_code, r.text[:300]))
            if not ok:
                continue
            if SALIDA:
                open(os.path.join(SALIDA, '%s_1ro_%d_estudiantes_%s.pdf' % (recorrido.upper(), n, sec)), 'wb').write(r.content)
            doc = pymupdf.open(stream=r.content, filetype='pdf')
            check('%s %s: 170 páginas (ninguna añadida)' % (sec, recorrido), len(doc) == 170, len(doc))
            tag = '%s %s' % (sec, recorrido)
            # Datos generales (pág 11): cédulas en orden de número de lista, sin faltantes ni duplicados
            d11, _, fuera = por_fila(doc[10], 11, filas)
            ced = [next((t for t in d11.get(i, []) if t.startswith('001-')), None) for i in range(filas)]
            esperado = [S.cedula(sec, e.no_lista) for e in ests] + [None] * (filas - n)
            check('%s: pág 11 cédulas = todos los estudiantes, en orden, una vez' % tag, ced == esperado,
                  [(i + 1, a, b) for i, (a, b) in enumerate(zip(ced, esperado)) if a != b][:4])
            check('%s: pág 11 nada fuera de las %d filas' % (tag, filas), not fuera, fuera[:5])
            # Asistencia (pág 17): Lengua Española, septiembre y octubre
            d17, nums17, _ = por_fila(doc[16], 17, filas)
            check('%s: pág 17 plantilla de %d filas (números 1..%d)' % (tag, filas, filas),
                  sorted(int(x) for x in nums17.values()) == list(range(1, filas + 1)), len(nums17))
            fechas = [f for f in S.fechas_asignatura(0) if (f.year, f.month) in ((2025, 9), (2025, 10))]
            mal = []
            for i, e in enumerate(ests):
                letras = ''.join(t for t in d17.get(i, []) if t in ('P', 'A', 'T', 'E'))
                esp = ''.join(LETRA[S.estado(e.no_lista, f)] for f in fechas)
                if letras != esp:
                    mal.append((i + 1, e.no_lista, letras, esp))
            vacias = [i + 1 for i in range(n, filas) if d17.get(i)]
            check('%s: pág 17 cada fila con la asistencia de SU estudiante' % tag, not mal, mal[:3])
            check('%s: pág 17 filas sobrantes vacías' % tag, not vacias, vacias)
            # Calificaciones (pág 131): todas las notas de la fila = 100 - no_lista
            d131, _, _ = por_fila(doc[130], 131, filas)
            mal = []
            for i, e in enumerate(ests):
                nums = [float(t) for t in d131.get(i, []) if t.replace('.', '', 1).isdigit()]
                if not nums or any(abs(x - S.nota(e.no_lista)) > 0.01 for x in nums):
                    mal.append((i + 1, e.no_lista, nums[:6]))
            check('%s: pág 131 cada fila con las notas de SU estudiante' % tag, not mal, mal[:3])
            # Acta (pág 159): apellido y nombre en orden, cada uno una vez
            d159, _, _ = por_fila(doc[158], 159, filas)
            ap = [next((t for t in d159.get(i, []) if t.startswith('Apellido')), None) for i in range(filas)]
            esp_ap = ['Apellido%d%s' % (e.no_lista, sec) for e in ests] + [None] * (filas - n)
            check('%s: pág 159 acta = todos, en orden, una vez' % tag, ap == esp_ap,
                  [(i + 1, a, b) for i, (a, b) in enumerate(zip(ap, esp_ap)) if a != b][:4])
            # Correspondencia fila a fila, con las filas 41-43 explícitas
            for pag, idx_asig, nom in ((47, 6, 'Ed. Artística'), (50, 7, 'Ed. Física'), (53, 8, 'FIHR')):
                filas_por_estudiante(tag, doc, pag, filas, ests, n, 'asistencia compacta (%s, sep-dic)' % nom,
                                     lambda e, k=idx_asig: letras_mes(e.no_lista, k, SEP_DIC), solo_letras)
            for pag in range(150, 159):
                filas_por_estudiante(tag, doc, pag, filas, ests, n, 'completivas (%s)' % S.ASIGNATURAS[pag - 150][1],
                                     lambda e: esperado_completiva(e.no_lista), lambda t: t)
            filas_por_estudiante(tag, doc, 159, filas, ests, n, 'acta izquierda (apellido, nombre, 3 asignaturas)',
                                 lambda e: ['Apellido%d%s' % (e.no_lista, sec), 'Nombre%d' % e.no_lista]
                                 + esperado_acta(e.no_lista, 3), lambda t: [x for x in t if x != 'X'])
            filas_por_estudiante(tag, doc, 160, filas, ests, n, 'acta derecha (6 asignaturas)',
                                 lambda e: esperado_acta(e.no_lista, 6), lambda t: [x for x in t if x != 'X'])
    else:
        print("\n=== %d° sección %s: %d estudiantes (no cabe) ===" % (g, sec, n))
        msg = 'admite como máximo 43' if g == 1 else 'solo tiene 40 filas'
        check('%s: el validador lo rechaza con el motivo' % sec, any(msg in x for x in v.errors), v.errors[:2])
        check('%s: el validador ya no promete "los primeros 40"' % sec,
              not any('primeros 40' in x for x in v.errors + v.warnings))
        r = client.get('/api/registros/secundaria/%d' % curso.id, headers=H)
        check('%s oficial: 400 con el motivo en "detalle"' % sec,
              r.status_code == 400 and any(msg in x for x in r.json().get('detalle', [])), (r.status_code, r.text[:300]))
        r = client.get('/api/registros/secundaria/%d/preview-pdf' % curso.id, headers=H)
        js = r.json() if r.headers.get('content-type', '').startswith('application/json') else {}
        check('%s borrador: 422 con "error" legible para la interfaz' % sec,
              r.status_code == 422 and msg in (js.get('error') or ''), (r.status_code, r.text[:300]))
        r = client.get('/api/registros/preview/%d' % curso.id, headers=H)
        check('%s vista previa de la interfaz: muestra el motivo' % sec, r.status_code == 200 and msg in r.text,
              (r.status_code, r.text[:300]))
        if SALIDA:
            open(os.path.join(SALIDA, 'RESPUESTAS_%d_%s_%d_estudiantes.txt' % (g, sec, n)), 'w', encoding='utf-8').write(
                '\n\n'.join('%s\n%s' % (u, client.get(u, headers=H).text) for u in (
                    '/api/registros/secundaria/%d' % curso.id, '/api/registros/secundaria/%d/preview-pdf' % curso.id)))

print("\n=== Generaciones simultáneas: la plantilla ampliada no se queda activa ===")


def _gen(n, out):
    est = [{'no_lista': i + 1, 'nombre': 'E%d' % i, 'sexo': 'M', 'fecha_nacimiento': dt.date(2013, 1, 1),
            'cedula': '', 'activo': True} for i in range(n)]
    pdf = RE.generar_registro_desde_sistema({'nombre': 'X'}, {'seccion': 'A', 'tanda': 'vespertina', 'grado': '1'},
                                            '2025-2026', est, {}, 1)
    p = pymupdf.open(stream=pdf, filetype='pdf')[16]
    y0, y1 = FRANJA[17]          # solo la franja de filas: el número de página también es gris
    out[n] = sum(1 for t, x, cy, c in spans(p) if c == GRIS and t.isdigit() and x < 70 and y0 < cy < y1)


res = {}
hilos = [threading.Thread(target=_gen, args=(n, res)) for n in (43, 40, 41)]
for h in hilos:
    h.start()
for h in hilos:
    h.join()
check('43, 40 y 41 a la vez: 43, 40 y 43 filas respectivamente', res == {43: 43, 40: 40, 41: 43}, res)
check('fuera de una generación no queda ninguna plantilla activa', RE._PLANTILLA_ACTIVA.get() is None)

print("\n=== Excepción durante la generación: el contexto se restaura ===")


def _filas_impresas(pdf):
    y0, y1 = FRANJA[17]
    p = pymupdf.open(stream=pdf, filetype='pdf')[16]
    return sum(1 for t, x, cy, c in spans(p) if c == GRIS and t.isdigit() and x < 70 and y0 < cy < y1)


def _est(n):
    return [{'no_lista': i + 1, 'nombre': 'E%d' % i, 'sexo': 'M', 'fecha_nacimiento': dt.date(2013, 1, 1),
             'cedula': '', 'activo': True} for i in range(n)]


CURSO = {'seccion': 'A', 'tanda': 'vespertina', 'grado': '1'}


def _gen_simple(n):
    return RE.generar_registro_desde_sistema({'nombre': 'X'}, CURSO, '2025-2026', _est(n), {}, 1)


# A · error real del dibujo con la plantilla ampliada activa: un mes de 22 días en
#     una rejilla de 21 (Lengua) -> RegistroExcedePlantilla a mitad de la generación.
_MES22 = [{'mes': 'septiembre', 'mes_num': 9, 'anio': 2025, 'posicion': 0, 'dias': list(range(1, 23)),
           'filas': [{'valores': ['P'] * 22, 'presentes': 22, 'porcentaje': 100.0} for _ in range(43)],
           'no_impartidas': {}}]
_DATOS22 = {'Lengua Española': {'docente': 'D', 'asistencia_matriz': _MES22}}
try:
    RE.generar_registro_desde_sistema({'nombre': 'X'}, CURSO, '2025-2026', _est(43), _DATOS22, 1)
    check('A: 43 estudiantes y un mes de 22 días -> error durante el dibujo', False, 'no falló')
except RE.RegistroExcedePlantilla as e:
    check('A: 43 estudiantes y un mes de 22 días -> error durante el dibujo',
          e.detalle.get('motivo') == 'DIAS_EXCEDEN_PLANTILLA', e.detalle)
check('A: tras la excepción no queda plantilla activa', RE._PLANTILLA_ACTIVA.get() is None)
check('A: la siguiente generación de 40 usa la plantilla de 40', _filas_impresas(_gen_simple(40)) == 40)

# B · excepción cualquiera dentro de la generación (no prevista por el generador)
_original = RE._generar_registro_escolar
_vio = {}


def _falla(*a, **k):
    _vio['filas'] = RE._filas_max()
    _vio['archivo'] = (RE._PLANTILLA_ACTIVA.get() or {}).get('archivo')
    raise RuntimeError('fallo provocado por la prueba')


RE._generar_registro_escolar = _falla
try:
    RE.generar_registro_desde_sistema({'nombre': 'X'}, CURSO, '2025-2026', _est(43), {}, 1)
    check('B: la excepción se propaga', False)
except RuntimeError:
    check('B: la excepción se propaga', True)
finally:
    RE._generar_registro_escolar = _original
check('B: durante la generación estaba activa la plantilla de 43',
      _vio == {'filas': 43, 'archivo': 'Registro-1er-Grado-Sec-General-43-filas.pdf'}, _vio)
check('B: tras la excepción no queda plantilla activa', RE._PLANTILLA_ACTIVA.get() is None)
check('B: la siguiente generación de 40 usa la plantilla de 40', _filas_impresas(_gen_simple(40)) == 40)

# C · lo mismo en un hilo del pool reutilizado (como el threadpool del borrador)
from concurrent.futures import ThreadPoolExecutor  # noqa: E402


def _en_hilo():
    try:
        RE.generar_registro_desde_sistema({'nombre': 'X'}, CURSO, '2025-2026', _est(43), _DATOS22, 1)
    except RE.RegistroExcedePlantilla:
        pass
    return RE._PLANTILLA_ACTIVA.get(), _filas_impresas(_gen_simple(40))


with ThreadPoolExecutor(max_workers=1) as pool:
    activa, filas40 = pool.submit(_en_hilo).result()
check('C: en el mismo hilo, tras la excepción no queda plantilla activa y 40 usa la de 40',
      activa is None and filas40 == 40, (activa, filas40))

db.close()
engine.dispose()
print("\n%d PASARON / %d FALLARON" % (len(PASARON), len(FALLARON)))
sys.exit(1 if FALLARON else 0)
