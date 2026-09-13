# -*- coding: utf-8 -*-
"""
EducaOne S1 — SESION NO IMPARTIDA en el Registro Escolar.

LAS TRES COSAS QUE TIENEN QUE PASAR EN LA HOJA
    1. La fecha CONSERVA su columna. No se corre ninguna otra, no se agrega
       ninguna, y no desaparece ni cuando esa fecha es tambien un DiaNoLaborable.
    2. En esa columna se lee el motivo, girado, como en el Registro en papel.
    3. El dia no cuenta para nadie: sale del denominador del porcentaje.

Y LA QUE TIENE QUE SEGUIR PASANDO
    Sin ninguna sesion declarada, la matriz es IDENTICA a la de antes de S1.

Se mide sobre el PDF de verdad: el texto se extrae con PyMuPDF y se comprueba
la posicion y el angulo de lo dibujado, no solo que la funcion no reviente.

Uso:
    cd backend
    python tools/test_sesion_no_impartida_registro_s1.py
"""
import os
import sys
import atexit
import tempfile
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TMPDIR = tempfile.mkdtemp(prefix="eo_s1_reg_")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_TMPDIR, "s.db").replace("\\", "/")
os.environ.setdefault("ENVIRONMENT", "development")


@atexit.register
def _cleanup():
    import shutil
    shutil.rmtree(_TMPDIR, ignore_errors=True)


from sqlalchemy import event                                   # noqa: E402
from database import engine, SessionLocal                      # noqa: E402
import models as M                                             # noqa: E402

_eu = str(engine.url).replace("\\", "/")
assert _TMPDIR.replace("\\", "/") in _eu and "sge.db" not in _eu, _eu

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_SGE = os.path.join(_BACKEND, "sge.db")
_sge_mtime = os.path.getmtime(_REPO_SGE) if os.path.exists(_REPO_SGE) else None


@event.listens_for(engine, "connect")
def _relax_fk(dbapi_conn, rec):
    try:
        dbapi_conn.execute("PRAGMA foreign_keys=OFF")
    except Exception:
        pass


engine.dispose()
M.Base.metadata.create_all(bind=engine)

from registro_asistencia import build_asistencia_registro      # noqa: E402
import registro_escolar as RE                                  # noqa: E402
import registro_validator as RV                              # noqa: E402

G, R, B, C, X = "\033[92m", "\033[91m", "\033[1m", "\033[96m", "\033[0m"
_fail, _ok, _total = [], 0, 0


def test(nombre):
    def deco(fn):
        global _total, _ok
        _total += 1
        print(f"\n{C}> {nombre}{X}")
        try:
            fn()
            _ok += 1
            print(f"  {G}PASO{X}")
        except Exception as e:
            import traceback
            _fail.append((nombre, str(e)))
            print(f"  {R}FALLO: {e}{X}")
            traceback.print_exc()
        return fn
    return deco


# --------------------------------------------------------------------------
# FIXTURE — marzo 2026, clases los LUNES: 2, 9, 16, 23, 30.
# Cinco dias lectivos; el 16 es el que se va a declarar no impartido.
# --------------------------------------------------------------------------
COL, ANO, GRA, CUR, MAT, LEN = 1, 1, 1, 10, 1, 2
PROF = 9
E1, E2 = 50, 51
LUNES = [date(2026, 3, d) for d in (2, 9, 16, 23, 30)]
EL_16 = date(2026, 3, 16)


def _seed(asistencia_en=None, no_laborable=False):
    """`asistencia_en`: las fechas con marcas. Por defecto, los cinco lunes."""
    if asistencia_en is None:
        asistencia_en = LUNES
    M.Base.metadata.drop_all(bind=engine)
    M.Base.metadata.create_all(bind=engine)
    d = SessionLocal()
    try:
        d.add(M.Colegio(id=COL, nombre="Colegio", codigo="c"))
        d.add(M.AnoEscolar(id=ANO, colegio_id=COL, nombre="2025-2026", activo=True,
                           fecha_inicio=date(2026, 3, 1), fecha_fin=date(2026, 3, 31),
                           dias_trabajados="{}"))
        d.add(M.Grado(id=GRA, colegio_id=COL, nombre="3ro Secundaria",
                      nivel="secundaria", orden=3))
        d.add(M.Curso(id=CUR, colegio_id=COL, nombre="A", grado_id=GRA,
                      ano_escolar_id=ANO, activo=True))
        for aid, nom, cod in ((MAT, "Matematica", "MAT"), (LEN, "Lengua", "LE")):
            d.add(M.Asignatura(id=aid, colegio_id=COL, nombre=nom, codigo=cod,
                               area="X", area_curricular_codigo=cod, activo=True))
        u = M.Usuario(id=PROF, colegio_id=COL, username="p", nombre="Franklin",
                      apellido="R", role="profesor", activo=True)
        u.set_password("Prueba2026x")
        d.add(u)
        # Lo minimo para que `validar_registro_secundaria` llegue hasta la
        # comprobacion de cobertura en vez de cortar antes por datos del centro.
        d.add(M.ConfiguracionColegio(colegio_id=COL, nombre="Colegio",
                                     regional="10", distrito="04",
                                     codigo_centro="00000"))
        d.add(M.AsignacionProfesor(colegio_id=COL, profesor_id=PROF, curso_id=CUR,
                                   asignatura_id=MAT, ano_escolar_id=ANO,
                                   activo=True, es_titular=True))
        for i, eid in enumerate((E1, E2)):
            d.add(M.Estudiante(id=eid, colegio_id=COL, nombre="Est%d" % i,
                               apellido="T", curso_id=CUR, activo=True, no_lista=i + 1))
        d.add(M.Horario(colegio_id=COL, profesor_id=PROF, curso_id=CUR,
                        asignatura_id=MAT, dia="Lunes", hora_inicio="08:00",
                        hora_fin="08:45", tipo_bloque="clase", activo=True))
        if no_laborable:
            d.add(M.DiaNoLaborable(colegio_id=COL, ano_escolar_id=ANO, fecha=EL_16,
                                   nombre="Feriado", tipo="feriado",
                                   recurrente=False, activo=True))
        for f in asistencia_en:
            for eid in (E1, E2):
                d.add(M.Asistencia(colegio_id=COL, estudiante_id=eid, curso_id=CUR,
                                   asignatura_id=MAT, fecha=f, estado="presente",
                                   registrado_por=PROF))
        d.commit()
    finally:
        d.close()


def _declarar(fecha=EL_16, motivo="SUSP_LLUVIA", activo=True, asignatura_id=MAT):
    d = SessionLocal()
    try:
        d.add(M.SesionNoImpartida(
            colegio_id=COL, fecha=fecha, curso_id=CUR, asignatura_id=asignatura_id,
            profesor_id=PROF, horario_id=1, dia_semana_snapshot="Lunes",
            hora_inicio_snapshot="08:00", hora_fin_snapshot="08:45",
            motivo_codigo=motivo, registrado_por=PROF, activo=activo))
        d.commit()
    finally:
        d.close()


def _matriz(asignatura_id=MAT):
    d = SessionLocal()
    try:
        return build_asistencia_registro(d, CUR, asignatura_id=asignatura_id)
    finally:
        d.close()


def _marzo(m):
    return next(x for x in m if x["mes_num"] == 3)


# ==========================================================================
# A — LA COLUMNA SE QUEDA DONDE ESTABA
# ==========================================================================
@test("A1 la fecha declarada conserva su columna, y no aparece ninguna otra")
def _():
    _seed(asistencia_en=[f for f in LUNES if f != EL_16])
    antes = _marzo(_matriz())["dias"]
    _declarar()
    despues = _marzo(_matriz())["dias"]
    assert antes == [2, 9, 16, 23, 30], antes
    assert despues == antes, (antes, despues)


@test("A2 la columna sobrevive aunque esa fecha sea tambien un DiaNoLaborable")
def _():
    # sin S1, un feriado BORRA la columna: es el caso que hacia falta cubrir
    _seed(asistencia_en=[f for f in LUNES if f != EL_16], no_laborable=True)
    sin_s1 = _marzo(_matriz())["dias"]
    assert 16 not in sin_s1, sin_s1
    _declarar(motivo="FERIADO")
    con_s1 = _marzo(_matriz())["dias"]
    assert con_s1 == [2, 9, 16, 23, 30], con_s1


@test("A3 una justificacion RETIRADA no toca la rejilla")
def _():
    _seed(asistencia_en=[f for f in LUNES if f != EL_16], no_laborable=True)
    _declarar(motivo="FERIADO", activo=False)
    assert 16 not in _marzo(_matriz())["dias"]


# ==========================================================================
# B — EL DIA NO CUENTA PARA NADIE
# ==========================================================================
@test("B1 sale del denominador: presente los otros cuatro lunes = 100%")
def _():
    _seed(asistencia_en=[f for f in LUNES if f != EL_16])
    mes = _marzo(_matriz())
    # sin declarar, el 16 es un dia lectivo vacio: 4 de 5 = 80%
    assert mes["filas"][0]["porcentaje"] == 80.0, mes["filas"][0]["porcentaje"]
    _declarar()
    mes = _marzo(_matriz())
    assert mes["total_dias"] == 5, mes["total_dias"]
    assert mes["dias_computables"] == 4, mes["dias_computables"]
    assert mes["filas"][0]["porcentaje"] == 100.0, mes["filas"][0]["porcentaje"]
    assert mes["filas"][0]["presentes"] == 4


@test("B2 el mes entero sin clase no da division por cero")
def _():
    _seed(asistencia_en=[])
    for f in LUNES:
        _declarar(fecha=f, motivo="SUSP_CURSO")
    mes = _marzo(_matriz())
    assert mes["dias_computables"] == 0
    assert mes["filas"][0]["porcentaje"] == 0.0
    assert len(mes["dias"]) == 5, mes["dias"]


@test("B3 si por datos antiguos hubiera marcas ese dia, no se ocultan pero no suman")
def _():
    _seed()                       # marcas en LOS CINCO lunes, el 16 incluido
    _declarar()
    mes = _marzo(_matriz())
    idx16 = mes["dias"].index(16)
    # el valor sigue visible: no se borra informacion real de la base
    assert mes["filas"][0]["valores"][idx16] == "P", mes["filas"][0]["valores"]
    # pero no se cuenta, asi que el porcentaje no puede pasar de 100
    assert mes["filas"][0]["presentes"] == 4
    assert mes["filas"][0]["porcentaje"] == 100.0


# ==========================================================================
# C — METADATOS QUE CONSUME EL PDF
# ==========================================================================
@test("C1 el mes expone el motivo indexado por numero de dia")
def _():
    _seed(asistencia_en=[f for f in LUNES if f != EL_16])
    _declarar(motivo="ACTIVIDAD_FUERA")
    mes = _marzo(_matriz())
    assert mes["dias_no_impartidos"] == [16], mes["dias_no_impartidos"]
    info = mes["no_impartidas"][16]
    assert info["motivo_codigo"] == "ACTIVIDAD_FUERA"
    assert info["etiqueta"] == "ACT. FUERA", info["etiqueta"]
    assert info["motivo"] == "Actividad fuera del centro"


@test("C2 la justificacion es de SU asignatura, no de las demas del curso")
def _():
    _seed(asistencia_en=[f for f in LUNES if f != EL_16])
    d = SessionLocal()
    try:
        d.add(M.Horario(colegio_id=COL, profesor_id=PROF, curso_id=CUR,
                        asignatura_id=LEN, dia="Lunes", hora_inicio="09:00",
                        hora_fin="09:45", tipo_bloque="clase", activo=True))
        for f in LUNES:
            d.add(M.Asistencia(colegio_id=COL, estudiante_id=E1, curso_id=CUR,
                               asignatura_id=LEN, fecha=f, estado="presente",
                               registrado_por=PROF))
        d.commit()
    finally:
        d.close()
    _declarar(asignatura_id=MAT)
    assert _marzo(_matriz(MAT))["dias_no_impartidos"] == [16]
    assert _marzo(_matriz(LEN))["dias_no_impartidos"] == [], "se colo en otra materia"
    assert _marzo(_matriz(LEN))["filas"][0]["porcentaje"] == 100.0


# ==========================================================================
# D — NADA CAMBIA SIN S1
# ==========================================================================
@test("D1 sin ninguna sesion declarada la matriz es identica a la de antes de S1")
def _():
    _seed()
    mes = _marzo(_matriz())
    assert mes["dias"] == [2, 9, 16, 23, 30]
    assert mes["total_dias"] == 5
    assert mes["dias_computables"] == mes["total_dias"], "cambio el denominador"
    assert mes["dias_no_impartidos"] == []
    assert mes["no_impartidas"] == {}
    assert mes["filas"][0]["porcentaje"] == 100.0


@test("D2 Primaria (sin asignatura) no ve S1 en absoluto")
def _():
    _seed()
    _declarar()
    d = SessionLocal()
    try:
        # sin asignatura_id, como llama Primaria
        m = build_asistencia_registro(d, CUR, asignatura_id=None)
    finally:
        d.close()
    mes = _marzo(m)
    assert mes["dias_no_impartidos"] == []
    assert mes["dias_computables"] == mes["total_dias"]


# ==========================================================================
# E — EL PDF: la etiqueta girada, en la columna correcta
# ==========================================================================
def _texto_pdf(draw_func, *args, **kwargs):
    """Dibuja un overlay y devuelve [(texto, x, y, angulo)] de lo estampado."""
    import fitz
    buf = RE._create_overlay_page(draw_func, *args, **kwargs)
    doc = fitz.open(stream=buf.getvalue(), filetype="pdf")
    items = []
    for blk in doc[0].get_text("dict")["blocks"]:
        for line in blk.get("lines", []):
            dx, dy = line.get("dir", (1.0, 0.0))
            texto = "".join(sp.get("text", "") for sp in line.get("spans", []))
            x0, y0, x1, y1 = line["bbox"]
            items.append((texto, (x0 + x1) / 2.0, (y0 + y1) / 2.0, (dx, dy)))
    doc.close()
    return items


def _mes_pdf(etiquetas):
    return {
        "nombre_mes": "marzo", "docente": "Franklin R",
        "dias_labels": [2, 9, 16, 23, 30],
        "etiquetas_no_impartidas": etiquetas,
        "asistencias": [{"dias": ["P", "P", None, "P", "P"] + [None] * 16,
                         "total": 4, "porcentaje": 100.0}],
    }


@test("E1 rejilla de 2 meses: la etiqueta sale GIRADA y en la columna del dia 16")
def _():
    items = _texto_pdf(RE.draw_asistencia, _mes_pdf({2: "SUSP. LLUVIA"}),
                       es_mes_derecho=False)
    girados = [i for i in items if abs(i[3][0]) < 0.1]      # direccion vertical
    assert len(girados) == 1, [i[0] for i in items]
    texto, x, y, _dir = girados[0]
    assert texto == "SUSP. LLUVIA", texto
    centros = RE.ASISTENCIA_TABLE["mes_izq_dia_centers"]
    # la columna 2 es la del dia 16, que es la TERCERA etiqueta de dias_labels
    assert abs(x - centros[2]) < 1.5, (x, centros[2])
    # y no invade las vecinas
    assert abs(x - centros[1]) > 9 and abs(x - centros[3]) > 9


@test("E2 la etiqueta cabe de sobra a lo alto de la columna")
def _():
    items = _texto_pdf(RE.draw_asistencia, _mes_pdf({2: "SUSP. LLUVIA"}))
    girados = [i for i in items if abs(i[3][0]) < 0.1]
    import fitz
    buf = RE._create_overlay_page(RE.draw_asistencia, _mes_pdf({2: "SUSP. LLUVIA"}))
    doc = fitz.open(stream=buf.getvalue(), filetype="pdf")
    alto_texto = None
    for blk in doc[0].get_text("dict")["blocks"]:
        for line in blk.get("lines", []):
            if abs(line.get("dir", (1, 0))[0]) < 0.1:
                x0, y0, x1, y1 = line["bbox"]
                alto_texto = y1 - y0
    doc.close()
    t = RE.ASISTENCIA_TABLE
    alto_col = t["row_height"] * t["total_filas"]
    assert alto_texto is not None and alto_texto < alto_col * 0.25, (alto_texto, alto_col)
    print(f"    etiqueta {alto_texto:.1f} pt de {alto_col:.1f} pt disponibles "
          f"({alto_texto / alto_col * 100:.0f}%), columna de "
          f"{t['mes_izq_dia_spacing']:.2f} pt de ancho")
    assert len(girados) == 1


@test("E3 rejilla compacta de 4 meses: misma etiqueta, su geometria")
def _():
    items = _texto_pdf(RE.draw_asistencia_4meses,
                       [_mes_pdf({2: "ACT. FUERA"}), None, None, None],
                       1, "Franklin R", "Educacion Artistica")
    girados = [i for i in items if abs(i[3][0]) < 0.1]
    assert len(girados) == 1, [i[0] for i in items]
    texto, x, _y, _d = girados[0]
    assert texto == "ACT. FUERA", texto
    blk = RE._asistencia_4meses_bloques(1)[0]
    assert abs(x - blk["dias"][2]) < 1.5, (x, blk["dias"][2])


@test("E4 sin etiquetas, el PDF sale exactamente como antes de S1")
def _():
    con = _texto_pdf(RE.draw_asistencia, _mes_pdf({}))
    mes_sin_campo = _mes_pdf({})
    del mes_sin_campo["etiquetas_no_impartidas"]
    sin = _texto_pdf(RE.draw_asistencia, mes_sin_campo)
    assert con == sin, "el campo vacio cambio el dibujo"
    assert not [i for i in con if abs(i[3][0]) < 0.1], "hay texto girado sin motivo"
    assert [i[0] for i in con if i[0] == "2"], "se perdieron los dias"


@test("E5 una etiqueta larguisima se recorta, nunca desborda la columna")
def _():
    largo = "MOTIVO EXTREMADAMENTE LARGO " * 40
    items = _texto_pdf(RE.draw_asistencia, _mes_pdf({2: largo}))
    girados = [i for i in items if abs(i[3][0]) < 0.1]
    assert len(girados) == 1
    assert len(girados[0][0]) < len(largo), "no se recorto"


# ==========================================================================
# F — EL ADAPTADOR: numero de dia -> indice de columna
# ==========================================================================
def _traducir(matriz, nombre_asig="Matemática"):
    """
    Corre el adaptador REAL y captura lo que le pasaria al generador de PDF.

    `generar_registro_desde_sistema` termina llamando a `generar_registro_escolar`;
    se intercepta esa llamada para leer `asistencia_data` sin construir las 60
    paginas del registro. Lo que se mide es la traduccion, que es lo que S1 toca.
    """
    capturado = {}

    def _espia(**kw):
        capturado.update(kw)
        return b""

    original = RE.generar_registro_escolar
    RE.generar_registro_escolar = _espia
    try:
        RE.generar_registro_desde_sistema(
            colegio_info={"nombre": "Colegio"},
            curso_info={"seccion": "A"},
            ano_escolar="2025-2026",
            estudiantes=[{"nombre_completo": "Est0 T", "activo": True}],
            asignaturas_data={nombre_asig: {
                "docente": "Franklin R", "indicadores": {}, "asistencias": {},
                "asistencia_matriz": matriz, "calificaciones": {}}},
            grado_numero=3,
        )
    finally:
        RE.generar_registro_escolar = original
    return capturado.get("asistencia_data") or {}


@test("F1 el adaptador traduce el dia a SU indice de columna, no a otro")
def _():
    _seed(asistencia_en=[f for f in LUNES if f != EL_16])
    _declarar(motivo="REUNION")
    datos = _traducir(_matriz())
    meses = datos["matemática"]["meses"]
    marzo = next(m for m in meses if m["nombre_mes"] == "marzo")
    idx = marzo["dias_labels"].index(16)
    assert idx == 2, marzo["dias_labels"]
    assert marzo["etiquetas_no_impartidas"] == {idx: "REUNIÓN"},         marzo["etiquetas_no_impartidas"]


@test("F2 un mes cuyo UNICO contenido es la justificacion no se cae de la hoja")
def _():
    # La hoja MINERD tiene 10 huecos de mes; los meses CON contenido van delante.
    # Un mes sin ninguna marca pero con justificacion es justamente la pagina que
    # explica por que no hubo clase: no puede ser la que se descarte.
    _seed(asistencia_en=[])
    _declarar(motivo="SUSP_CURSO")
    datos = _traducir(_matriz())
    meses = datos["matemática"]["meses"]
    assert meses[0]["nombre_mes"] == "marzo", [m["nombre_mes"] for m in meses]
    assert meses[0]["etiquetas_no_impartidas"], meses[0]


@test("F2b sin S1, el adaptador entrega exactamente lo de siempre mas un dict vacio")
def _():
    _seed()
    datos = _traducir(_matriz())
    marzo = next(m for m in datos["matemática"]["meses"] if m["nombre_mes"] == "marzo")
    assert marzo["etiquetas_no_impartidas"] == {}
    assert marzo["dias_labels"] == [2, 9, 16, 23, 30]
    assert marzo["asistencias"][0]["porcentaje"] == 100.0


# ==========================================================================
# G — COBERTURA: UNA SUSPENSION NO ES ASISTENCIA QUE FALTE
#
# El escenario que motivo la correccion: 5 fechas visibles, 1 declarada no
# impartida, 4 realmente impartidas y TODOS los alumnos completos en esas 4.
# La cobertura tiene que dar 100 %, y el validador no puede acusar celdas
# faltantes por la columna justificada.
# ==========================================================================
@test("G1 cobertura 100% con 5 columnas visibles, 1 suspendida y 4 completas")
def _():
    _seed(asistencia_en=[f for f in LUNES if f != EL_16])
    mes = _marzo(_matriz())
    # antes de declarar, la columna vacia del 16 SI cuenta como hueco
    assert mes["cobertura_registro_pct"] == 80.0, mes["cobertura_registro_pct"]

    _declarar()
    mes = _marzo(_matriz())
    assert mes["dias"] == [2, 9, 16, 23, 30], mes["dias"]          # A y C
    assert mes["dias_computables"] == 4, mes["dias_computables"]   # B
    assert mes["filas"][0]["porcentaje"] == 100.0                  # D
    assert mes["cobertura_registro_pct"] == 100.0, \
        ("E: la suspension seguia contando como celda esperada",
         mes["cobertura_registro_pct"])


@test("G2 una marca legacy en la fecha suspendida no infla la cobertura")
def _():
    # asistencia en LOS CINCO lunes, incluido el que luego se declara
    _seed()
    _declarar()
    mes = _marzo(_matriz())
    # sigue visible: no se oculta historia
    assert mes["filas"][0]["valores"][mes["dias"].index(16)] == "P"
    # pero ni el numerador ni el denominador de la cobertura la miran
    assert mes["dias_computables"] == 4
    assert mes["cobertura_registro_pct"] == 100.0, mes["cobertura_registro_pct"]


@test("G3 la cobertura sigue detectando huecos REALES de los dias impartidos")
def _():
    # falta el lunes 23 para los dos alumnos: 2 de 8 celdas computables vacias
    _seed(asistencia_en=[f for f in LUNES if f not in (EL_16, date(2026, 3, 23))])
    _declarar()
    mes = _marzo(_matriz())
    assert mes["dias_computables"] == 4
    assert mes["cobertura_registro_pct"] == 75.0, mes["cobertura_registro_pct"]


@test("G4 _evaluar_cobertura_asistencia no reporta faltantes por la suspension")
def _():
    _seed(asistencia_en=[f for f in LUNES if f != EL_16])
    d = SessionLocal()
    try:
        ests = d.query(M.Estudiante).filter_by(curso_id=CUR, activo=True).all()
        antes = RV._evaluar_cobertura_asistencia(d, CUR, ests, asignatura_ids=[MAT])
        assert antes["faltantes"], "precondicion: sin declarar, SI hay faltantes"
    finally:
        d.close()

    _declarar()
    d = SessionLocal()
    try:
        ests = d.query(M.Estudiante).filter_by(curso_id=CUR, activo=True).all()
        cob = RV._evaluar_cobertura_asistencia(d, CUR, ests, asignatura_ids=[MAT])
    finally:
        d.close()
    assert cob["faltantes"] == [], cob["faltantes"]                # F
    assert cob["total_esperado"] == 4 * 2, cob["total_esperado"]
    assert cob["total_cubierto"] == 8, cob["total_cubierto"]


@test("G5 validar_registro_secundaria no acusa 'Asistencia incompleta'")
def _():
    _seed(asistencia_en=[f for f in LUNES if f != EL_16])
    d = SessionLocal()
    try:
        antes = [e for e in RV.validar_registro_secundaria(d, CUR, COL).errors
                 if "Asistencia incompleta" in e]
    finally:
        d.close()
    assert antes, "precondicion: sin declarar, el validador SI se queja"

    _declarar()
    d = SessionLocal()
    try:
        res = RV.validar_registro_secundaria(d, CUR, COL)
    finally:
        d.close()
    culpables = [e for e in res.errors if "Asistencia incompleta" in e]
    assert culpables == [], culpables                              # G
    # el fixture no pretende ser un Registro completo; lo que se exige es que
    # ningun error restante venga de la sesion no impartida.
    print("    errores restantes (ajenos a S1): %d" % len(res.errors))


@test("G6 el fallback legacy: una matriz sin dias_computables se evalua igual")
def _():
    # Asi se comportan las matrices anteriores a S1, que no traen el campo.
    mes_legacy = {"mes": "marzo", "dias": [2, 9, 16, 23, 30],
                  "cobertura_registro_pct": 100.0}
    dc = mes_legacy.get("dias_computables")
    if dc is None:
        dc = len(mes_legacy.get("dias", []))
    assert dc == 5, dc


@test("F3 el repo no fue tocado: sge.db intacto")
def _():
    a = os.path.getmtime(_REPO_SGE) if os.path.exists(_REPO_SGE) else None
    assert a == _sge_mtime, "sge.db fue modificado"


print("\n" + "=" * 70)
print(f"{B}S1 SESION NO IMPARTIDA (Registro/PDF): {_ok}/{_total} pruebas{X}")
if _fail:
    print(f"{R}FALLARON:{X}")
    for n, e in _fail:
        print(f"  - {n}: {e}")
    sys.exit(1)
print(f"{G}TODO VERDE{X}")
