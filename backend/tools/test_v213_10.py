"""Test v2.13.10 — generación de boletín 1ro NS con la plantilla específica."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import (
    Base, Colegio, Usuario, AnoEscolar, Grado, Curso, Asignatura,
    Estudiante, CalificacionSecundaria, ConfiguracionColegio,
)
from datetime import date, timedelta

engine = create_engine('sqlite:///:memory:', echo=False)
Base.metadata.create_all(engine)
S = sessionmaker(bind=engine)
db = S()

db.add(Colegio(id=1, nombre="Test", codigo="t"))
db.add(ConfiguracionColegio(id=1, colegio_id=1, nombre="Test"))
hoy = date.today()
db.add(AnoEscolar(id=1, colegio_id=1, nombre="2025-2026", activo=True,
                   fecha_inicio=hoy-timedelta(days=60), fecha_fin=hoy+timedelta(days=180),
                   periodo_activo=4))
db.add(Grado(id=1, colegio_id=1, nombre="1ro", nivel="secundaria",
             ciclo="primer_ciclo", orden=1))
db.add(Grado(id=6, colegio_id=1, nombre="6to", nivel="secundaria",
             ciclo="segundo_ciclo", orden=6))
db.commit()
db.add(Curso(id=1, colegio_id=1, nombre="A", grado_id=1, activo=True))
db.add(Curso(id=6, colegio_id=1, nombre="A", grado_id=6, activo=True))
asigs = ['Lengua Española', 'Matemática', 'Inglés']
for i, n in enumerate(asigs, 1):
    db.add(Asignatura(id=i, colegio_id=1, nombre=n, activo=True))
db.commit()

est = Estudiante(id=1, colegio_id=1, curso_id=1, nombre="Juan",
                 apellido="Pérez", activo=True, no_lista=1, matricula="M0001")
db.add(est)
db.commit()

for asig_id in [1, 2, 3]:
    for comp_n in range(1, 5):
        db.add(CalificacionSecundaria(
            colegio_id=1, estudiante_id=1, asignatura_id=asig_id, ano_escolar_id=1,
            competencia_numero=comp_n, p1=85, p2=88, p3=90, p4=87
        ))
db.commit()

# Test 1: que use la plantilla específica de 1ro
print("\n=== Test 1: routing usa plantilla específica 1ro NS ===")
from boletin_minerd_secundaria import _get_plantilla_path

curso_1ro = db.get(Curso, 1)
curso_1ro.grado = db.get(Grado, 1)  # forzar relación
path = _get_plantilla_path(curso_1ro)
print(f"Path elegido: {path}")
assert '1ro' in path, f"❌ Debería usar plantilla 1ro pero usa {path}"
print("✅ 1ro NS usa Boletin-1ro-grado-NS.pdf")

# Test 2: 6to usa 6to
curso_6to = db.get(Curso, 6)
curso_6to.grado = db.get(Grado, 6)
path6 = _get_plantilla_path(curso_6to)
print(f"\n=== Test 2: 6to NS ===\nPath: {path6}")
assert '6to' in path6
print("✅ 6to NS usa Boletin-6to-grado-NS.pdf")

# Test 3: 3ro NS sin plantilla propia → fallback al MISMO ciclo (primer ciclo)
# v2.13.11: 3ro confirmado como Primer Ciclo (con 1ro y 2do).
print("\n=== Test 3: 3ro NS sin plantilla propia → fallback al primer ciclo ===")
db.add(Grado(id=3, colegio_id=1, nombre="3ro", nivel="secundaria",
             ciclo="primer_ciclo", orden=3))
db.add(Curso(id=3, colegio_id=1, nombre="A", grado_id=3, activo=True))
db.commit()
curso_3ro = db.get(Curso, 3)
curso_3ro.grado = db.get(Grado, 3)
path3 = _get_plantilla_path(curso_3ro)
print(f"3ro NS (sin plantilla propia) → {path3}")
# Ahora debe caer en 2do o 1ro (mismo ciclo), NO en 6to
assert '2do' in path3 or '1ro' in path3, f"❌ 3ro debe caer en primer ciclo, dio {path3}"
print("✅ 3ro NS cae correctamente en plantilla del primer ciclo")

# Test 4: generar PDF real con 1ro NS
print("\n=== Test 4: generar PDF real para 1ro NS ===")
from boletin_minerd_secundaria import generar_boletin_secundaria_minerd

califs_por_asig = {}
for asig_id in [1, 2, 3]:
    asig_obj = db.get(Asignatura, asig_id)
    comps = db.query(CalificacionSecundaria).filter_by(
        estudiante_id=1, asignatura_id=asig_id, ano_escolar_id=1
    ).order_by(CalificacionSecundaria.competencia_numero).all()
    califs_por_asig[asig_id] = {
        'asignatura_nombre': asig_obj.nombre,
        'competencias': comps,
        'pc_por_periodo': {f'pc{p}': 87.5 for p in range(1, 5)},
        'cf': 88,
        'literal': 'B',
        'evaluacion_extra': None,
    }

asistencias = {f'p{p}': {'asistencia': 20, 'ausencia': 1, 'pct_asistencia_anual': 95, 'pct_ausencia_anual': 5} for p in range(1, 5)}
situacion = {'promovido': True, 'repitente': False, 'condicion': 'APROBADO/A'}

buffer = generar_boletin_secundaria_minerd(
    estudiante=est, curso=curso_1ro,
    calificaciones_por_asig=califs_por_asig,
    asistencias_por_periodo=asistencias,
    config=db.get(ConfiguracionColegio, 1),
    ano_escolar=db.get(AnoEscolar, 1),
    observaciones="Test",
    situacion_final=situacion,
)
pdf_bytes = buffer.read()
print(f"PDF generado: {len(pdf_bytes)} bytes")
assert pdf_bytes.startswith(b'%PDF-'), "No es un PDF válido"
print("✅ PDF generado con plantilla 1ro NS correctamente")

# Guardar para inspección
output_path = '/tmp/test_boletin_1ro.pdf'
with open(output_path, 'wb') as f:
    f.write(pdf_bytes)
print(f"💾 Guardado en: {output_path}")

print("\n🎉 TODOS LOS TESTS v2.13.10 PASARON")
