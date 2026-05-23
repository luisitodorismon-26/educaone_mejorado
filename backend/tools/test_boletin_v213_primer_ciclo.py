"""Test plantilla 2do grado (primer ciclo NS, sin Salida Optativa)"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from boletin_minerd_secundaria import generar_boletin_secundaria_minerd


class Mock:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

class MockComp:
    def __init__(self, comp_n, p1, p2, p3, p4):
        self.competencia_numero = comp_n
        self.p1, self.p2, self.p3, self.p4 = p1, p2, p3, p4
        self.rp1 = self.rp2 = self.rp3 = self.rp4 = None
    def valor_periodo(self, p):
        return getattr(self, f'p{p}')


def make_asig(nombre, notas):
    comps = [MockComp(i+1, *cuatro) for i, cuatro in enumerate(notas)]
    pcs = {f'pc{p}': round(sum(c.valor_periodo(p) for c in comps)/4, 1) for p in range(1, 5)}
    cf = int(round(sum(pcs.values())/4))
    return {
        'asignatura_nombre': nombre, 'competencias': comps,
        'pc_por_periodo': pcs, 'cf': cf,
        'literal': 'A' if cf>=90 else 'B' if cf>=80 else 'C' if cf>=70 else 'F',
        'evaluacion_extra': None,
    }


est = Mock(nombre="Ana Sofía", apellido="Ramírez Pérez", sigerd="200888777", numero_orden=8)
tutor = Mock(nombre="Carlos", apellido="Sánchez")
curso = Mock(grado="2do Secundaria", seccion="B", tanda="Matutina",
             nivel="secundaria", ciclo="primero", tutor=tutor)
config = Mock(nombre_centro="Liceo José Núñez", codigo_centro="04-110",
              telefono="809-234-5678", distrito_educativo="04-02",
              regional="04", provincia="Santiago", municipio="Santiago de los Caballeros")
ano = Mock(nombre="2025-2026")

cal = {
    1: make_asig('Lengua Española',[(82,85,88,84),(78,80,82,79),(80,82,85,81),(84,86,88,85)]),
    2: make_asig('Lenguas Extranjeras (Inglés)',[(75,78,80,77),(72,74,76,73),(78,80,82,79),(76,78,80,77)]),
    3: make_asig('Lenguas Extranjeras (Francés)',[(85,87,89,86),(82,84,86,83),(87,89,91,88),(84,86,88,85)]),
    4: make_asig('Matemática',[(70,72,75,74),(68,70,73,71),(72,75,77,74),(75,78,80,77)]),
    5: make_asig('Ciencias Sociales',[(85,87,89,86),(82,84,86,83),(87,89,91,88),(84,86,88,85)]),
    6: make_asig('Ciencias de la Naturaleza',[(78,80,82,79),(75,77,79,76),(80,82,84,81),(77,79,81,78)]),
    7: make_asig('Educación Artística',[(90,92,94,91),(88,90,92,89),(92,94,96,93),(89,91,93,90)]),
    8: make_asig('Educación Física',[(88,90,92,89),(85,87,89,86),(90,92,94,91),(87,89,91,88)]),
    9: make_asig('Formación Integral Humana y Religiosa',[(85,87,89,86),(82,84,86,83),(87,89,91,88),(84,86,88,85)]),
}

asist = {f'p{p}': {'asistencia': 45-p, 'ausencia': p, 'pct_asistencia_anual': 95-p, 'pct_ausencia_anual': 5+p} for p in range(1,5)}

buf = generar_boletin_secundaria_minerd(
    estudiante=est, curso=curso,
    calificaciones_por_asig=cal,
    asistencias_por_periodo=asist,
    config=config, ano_escolar=ano,
    observaciones="Excelente desempeño durante el año. Continúa con el plan de estudios regular.",
    situacion_final={'promovido': True, 'repitente': False,
                     'condicion': 'APROBADO/A — Promovido al 3er grado de Secundaria'},
)

with open('/home/claude/boletin_work/test_boletin_2do.pdf','wb') as f:
    f.write(buf.read())

import pypdfium2 as pdfium
pdf = pdfium.PdfDocument('/home/claude/boletin_work/test_boletin_2do.pdf')
for i, page in enumerate(pdf):
    page.render(scale=2.0).to_pil().save(f'/home/claude/boletin_work/test_boletin_2do_p{i+1}.png')
print("✅ 2do grado generado")
