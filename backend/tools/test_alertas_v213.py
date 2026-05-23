"""
Test runtime de las alertas v2.13 secundaria.

Crea una BD sqlite en memoria con datos mínimos:
- 1 colegio, 1 año activo con período 1 activo y fecha de fin en 5 días
- 1 profesor con 1 asignación a un curso secundaria
- 3 estudiantes
- 1 con CF=58 + EvaluacionExtra fase pendiente "completiva"

Luego invoca get_dashboard_alertas() montando un current_user mock y valida:
- el profesor ve "1 evaluacion_extra_pendiente"
- el profesor ve "cierre_periodo_secundaria" porque hay competencias sin cargar
- dirección ve "1 evaluacion_extra_pendiente" + "profesores_atrasados_secundaria"

Si todas las queries corren sin excepción y las alertas aparecen, el endpoint
es válido en runtime (no solo en import-time).
"""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Forzar BD sqlite en memoria ANTES de importar modelos
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import (
    Base, Colegio, Usuario, AnoEscolar, Grado, Curso, Asignatura,
    Estudiante, AsignacionProfesor, CalificacionSecundaria,
    EvaluacionExtraSecundaria
)

# ─── Setup BD en memoria ─────────────────────────────────────────
engine = create_engine('sqlite:///:memory:', echo=False)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
db = Session()

# Colegio
colegio = Colegio(id=1, nombre="Test", codigo="test")
db.add(colegio)

# Año activo, P1 en curso, cierra en 5 días
hoy = date.today()
ano = AnoEscolar(
    id=1, colegio_id=1, nombre="2025-2026",
    fecha_inicio=hoy - timedelta(days=60),
    fecha_fin=hoy + timedelta(days=180),
    activo=True, cerrado=False,
    periodo_activo=1,
    p1_inicio=hoy - timedelta(days=60),
    p1_fin=hoy + timedelta(days=5),
    p1_cerrado=False,
)
db.add(ano)

# Grado secundaria (2do)
grado2do = Grado(id=1, colegio_id=1, nombre="2do", nivel="secundaria", ciclo="primer_ciclo", orden=2)
db.add(grado2do)
db.commit()

# Curso secundaria
curso = Curso(id=1, colegio_id=1, nombre="A", grado_id=1)
db.add(curso)

# Asignatura (no tiene nivel)
asig = Asignatura(id=1, colegio_id=1, nombre="Matemática", activo=True)
db.add(asig)

# Profesor
profesor = Usuario(
    id=10, colegio_id=1, username="prof_test",
    password_hash="x",
    role="profesor", nombre="Test", apellido="Profesor",
    activo=True, must_change_password=False
)
db.add(profesor)

# Director
director = Usuario(
    id=11, colegio_id=1, username="dir_test",
    password_hash="x",
    role="direccion", nombre="Test", apellido="Director",
    activo=True, must_change_password=False
)
db.add(director)

# Asignación profesor → curso × asignatura
asignacion = AsignacionProfesor(
    id=1, colegio_id=1, profesor_id=10, curso_id=1, asignatura_id=1,
    ano_escolar_id=1, activo=True
)
db.add(asignacion)

# 3 estudiantes
for i in range(1, 4):
    e = Estudiante(
        id=i, colegio_id=1, curso_id=1,
        nombre=f"Estudiante{i}", apellido=f"Test{i}",
        activo=True
    )
    db.add(e)

db.commit()

# Estudiante 1 tiene 4 competencias todas con CF muy bajo → cascada extra pendiente
for comp_n in range(1, 5):
    c = CalificacionSecundaria(
        colegio_id=1, estudiante_id=1, asignatura_id=1,
        ano_escolar_id=1, competencia_numero=comp_n,
        p1=50, p2=55, p3=60, p4=58,
    )
    db.add(c)
db.commit()

# Crear EvaluacionExtra con cf_original<70 y SIN nota completiva (fase_pendiente="completiva")
ev = EvaluacionExtraSecundaria(
    colegio_id=1, estudiante_id=1, asignatura_id=1, ano_escolar_id=1,
    cf_original=56,
)
db.add(ev)
db.commit()

# ─── Test: get_dashboard_alertas como PROFESOR ────────────────────
print("\n=== Como PROFESOR ===")

# Inyectar get_db
from contextlib import contextmanager
import app
@contextmanager
def _override_get_db():
    yield db
app.get_db = lambda: db

# Monkey-patch del DB session: el endpoint usa Depends(get_db), pero al llamarlo
# directamente como función vía await, le pasamos db a mano.
import asyncio

async def correr_alertas(user):
    return await app.get_dashboard_alertas(db=db, current_user=user)

alertas_prof = asyncio.run(correr_alertas(profesor))
print(f"Total alertas profesor: {len(alertas_prof)}")
for a in alertas_prof:
    print(f"  [{a['prioridad']}] {a['tipo']}: {a['mensaje']}")

# Validaciones
tipos_prof = {a['tipo'] for a in alertas_prof}
assert 'evaluacion_extra_pendiente' in tipos_prof, f"❌ Falta alerta evaluacion_extra_pendiente, tipos={tipos_prof}"
assert 'cierre_periodo_secundaria' in tipos_prof, f"❌ Falta cierre_periodo_secundaria, tipos={tipos_prof}"
print("✅ Profesor: ambas alertas presentes")

# ─── Test: get_dashboard_alertas como DIRECTOR ────────────────────
print("\n=== Como DIRECTOR ===")
alertas_dir = asyncio.run(correr_alertas(director))
print(f"Total alertas director: {len(alertas_dir)}")
for a in alertas_dir:
    print(f"  [{a['prioridad']}] {a['tipo']}: {a['mensaje']}")

tipos_dir = {a['tipo'] for a in alertas_dir}
assert 'evaluacion_extra_pendiente' in tipos_dir, f"❌ Falta evaluacion_extra_pendiente para dirección, tipos={tipos_dir}"
assert 'profesores_atrasados_secundaria' in tipos_dir, f"❌ Falta profesores_atrasados_secundaria, tipos={tipos_dir}"
print("✅ Director: ambas alertas presentes")

print("\n🎉 TODOS LOS TESTS PASARON")
