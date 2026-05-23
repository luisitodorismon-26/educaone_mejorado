"""
Test end-to-end del boletín MINERD secundaria pixel-exacto v2.13.

Simula un estudiante con notas en las 9 asignaturas + 1 asig reprobada
con evaluación completiva aprobada, y genera el PDF para validación visual.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from boletin_minerd_secundaria import generar_boletin_secundaria_minerd


# ────────────────────────────────────────────────────────────────
# Mocks ligeros (no toca la BD)
# ────────────────────────────────────────────────────────────────

class Mock:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

# Estudiante
estudiante = Mock(
    nombre="Justin Daniel",
    apellido="Peñaló Martínez",
    sigerd="100245678",
    numero_orden=15,
)

# Curso
tutor = Mock(nombre="María", apellido="González")
curso = Mock(
    grado="6to Secundaria",
    seccion="A",
    tanda="Vespertina",
    nivel="secundaria",
    ciclo="segundo",
    tutor=tutor,
    nombre="6to A Vespertino",
)

# Config del colegio
config = Mock(
    nombre_centro="Colegio San Pedro Apóstol",
    nombre_colegio="Colegio San Pedro Apóstol",
    codigo_centro="08-456",
    telefono="809-555-1234",
    distrito_educativo="10-05",
    regional="10",
    provincia="Santo Domingo",
    municipio="Distrito Nacional",
)

# Año escolar
ano_escolar = Mock(nombre="2024-2025")


# Simular CalificacionSecundaria (con método valor_periodo)
class MockComp:
    def __init__(self, comp_n, p1, p2, p3, p4, rp1=None, rp2=None, rp3=None, rp4=None):
        self.competencia_numero = comp_n
        self.p1, self.p2, self.p3, self.p4 = p1, p2, p3, p4
        self.rp1, self.rp2, self.rp3, self.rp4 = rp1, rp2, rp3, rp4
    
    def valor_periodo(self, periodo):
        p = getattr(self, f'p{periodo}')
        rp = getattr(self, f'rp{periodo}')
        if rp is not None and p is not None:
            return max(p, rp)
        if rp is not None: return rp
        if p is not None: return p
        return None


def make_asig(nombre, notas_4x4):
    """Crea un dict de asignatura. notas_4x4 = 4 competencias × 4 periodos."""
    comps = []
    for i, cuatro in enumerate(notas_4x4):
        comps.append(MockComp(i+1, *cuatro))
    
    # Calcular PC1-PC4
    pcs = {}
    for p in range(1, 5):
        vals = [c.valor_periodo(p) for c in comps]
        pcs[f'pc{p}'] = round(sum(vals)/4, 1)
    
    cf = int(round(sum(pcs.values())/4))
    literal = 'A' if cf>=90 else 'B' if cf>=80 else 'C' if cf>=70 else 'F'
    
    return {
        'asignatura_nombre': nombre,
        'competencias': comps,
        'pc_por_periodo': pcs,
        'cf': cf,
        'literal': literal,
        'evaluacion_extra': None,
    }


# Construir datos: 9 asignaturas, una con cascada extra
calificaciones = {}

# Asignaturas normales
calificaciones[1] = make_asig('Lengua Española', [
    (85, 88, 90, 82),  # Comp 1
    (78, 80, 85, 79),  # Comp 2
    (82, 85, 87, 80),  # Comp 3
    (88, 90, 92, 85),  # Comp 4
])

calificaciones[2] = make_asig('Lenguas Extranjeras (Inglés)', [
    (75, 78, 82, 80),
    (72, 74, 78, 76),
    (80, 82, 84, 81),
    (78, 80, 82, 79),
])

calificaciones[3] = make_asig('Lenguas Extranjeras (Francés)', [
    (88, 90, 87, 89),
    (85, 87, 84, 86),
    (90, 92, 88, 91),
    (87, 89, 86, 88),
])

calificaciones[4] = make_asig('Matemática', [
    (70, 72, 75, 74),
    (68, 70, 73, 71),
    (72, 75, 77, 74),
    (75, 78, 80, 77),
])

calificaciones[5] = make_asig('Ciencias Sociales', [
    (88, 90, 87, 89),
    (85, 87, 84, 86),
    (90, 92, 88, 91),
    (87, 89, 86, 88),
])

calificaciones[6] = make_asig('Ciencias de la Naturaleza', [
    (82, 84, 86, 83),
    (78, 80, 82, 79),
    (85, 87, 84, 86),
    (80, 82, 85, 81),
])

calificaciones[7] = make_asig('Educación Artística', [
    (92, 94, 90, 93),
    (90, 92, 88, 91),
    (94, 95, 92, 94),
    (91, 93, 89, 92),
])

calificaciones[8] = make_asig('Educación Física', [
    (90, 92, 88, 91),
    (88, 90, 86, 89),
    (92, 94, 90, 93),
    (89, 91, 87, 90),
])

calificaciones[9] = make_asig('Formación Integral Humana y Religiosa', [
    (88, 90, 87, 89),
    (85, 87, 84, 86),
    (90, 92, 88, 91),
    (87, 89, 86, 88),
])

# Asignatura REPROBADA con completiva aprobada (caso extra)
ev_extra = Mock(
    cf_original=58, cec=85, completiva_final=72,
    ceex=None, extraordinaria_final=None,
    ce=None, especial_final=None,
    nota_final=72, condicion_final='aprobado_completiva',
    fase_pendiente=None,
)
asig_reprobada = make_asig('Lengua Española', [
    (50, 55, 60, 65, None, None, 62, None),
    (55, 60, 58, 62),
    (50, 55, 60, 58),
    (55, 60, 58, 62),
])
asig_reprobada['cf'] = 58
asig_reprobada['evaluacion_extra'] = ev_extra
# Sobreescribo la primera materia con esta versión reprobada para mostrar bloques completivos
calificaciones[1] = asig_reprobada


# Asistencia
asistencias = {
    'p1': {'asistencia': 46, 'ausencia': 1, 'pct_asistencia_anual': 98, 'pct_ausencia_anual': 2},
    'p2': {'asistencia': 43, 'ausencia': 4, 'pct_asistencia_anual': 91, 'pct_ausencia_anual': 9},
    'p3': {'asistencia': 50, 'ausencia': 0, 'pct_asistencia_anual': 100, 'pct_ausencia_anual': 0},
    'p4': {'asistencia': 41, 'ausencia': 2, 'pct_asistencia_anual': 95, 'pct_ausencia_anual': 5},
}

situacion = {
    'promovido': True,
    'repitente': False,
    'condicion': 'APROBADO/A — Promovido a estudios universitarios. Se recomienda profundización en Matemática y Lengua Española.',
}

observaciones = (
    "Estudiante destacado en participación y compromiso. "
    "Se observa progreso significativo en el último trimestre. "
    "Se recomienda continuar con el plan de refuerzo en Matemática durante el verano."
)

# Generar
buf = generar_boletin_secundaria_minerd(
    estudiante=estudiante,
    curso=curso,
    calificaciones_por_asig=calificaciones,
    asistencias_por_periodo=asistencias,
    config=config,
    ano_escolar=ano_escolar,
    observaciones=observaciones,
    situacion_final=situacion,
)

out_path = '/home/claude/boletin_work/test_boletin_v213.pdf'
with open(out_path, 'wb') as f:
    f.write(buf.read())

print(f"✅ Generado: {out_path}")

# Renderizar PNGs para revisión
import pypdfium2 as pdfium
pdf = pdfium.PdfDocument(out_path)
for i, page in enumerate(pdf):
    img = page.render(scale=2.0).to_pil()
    img.save(f'/home/claude/boletin_work/test_boletin_v213_p{i+1}.png')
print(f"✅ PNGs: test_boletin_v213_p1.png, test_boletin_v213_p2.png")
