"""
Test v2.13.6: Notas por Período lee CalificacionSecundaria
"""
import os, sys, asyncio
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import (
    Base, Colegio, Usuario, AnoEscolar, Grado, Curso, Asignatura,
    Estudiante, AsignacionProfesor, CalificacionSecundaria,
    ConfiguracionColegio,
)

engine = create_engine('sqlite:///:memory:', echo=False)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
db = Session()

# Setup
db.add(Colegio(id=1, nombre="Test", codigo="test"))
db.add(ConfiguracionColegio(id=1, colegio_id=1, nombre="Test"))
db.add(AnoEscolar(id=1, colegio_id=1, nombre="2025-2026", activo=True,
                   fecha_inicio=date(2025,8,1), fecha_fin=date(2026,6,30),
                   periodo_activo=4))
db.add(Grado(id=1, colegio_id=1, nombre="1ro", nivel="secundaria",
             ciclo="primer_ciclo", orden=1))
db.commit()
db.add(Curso(id=1, colegio_id=1, nombre="A", grado_id=1))
db.add(Asignatura(id=1, colegio_id=1, nombre="Inglés", activo=True))
db.add(Asignatura(id=2, colegio_id=1, nombre="Matemática", activo=True))
prof = Usuario(id=10, colegio_id=1, username="prof", password_hash="x",
                role="profesor", nombre="P", apellido="X",
                activo=True, must_change_password=False)
director = Usuario(id=20, colegio_id=1, username="dir", password_hash="x",
                    role="direccion", nombre="D", apellido="Y",
                    activo=True, must_change_password=False)
db.add(prof); db.add(director)
db.add(AsignacionProfesor(id=1, colegio_id=1, profesor_id=10, curso_id=1,
                           asignatura_id=1, ano_escolar_id=1, activo=True))
db.add(AsignacionProfesor(id=2, colegio_id=1, profesor_id=10, curso_id=1,
                           asignatura_id=2, ano_escolar_id=1, activo=True))
db.commit()

# 3 estudiantes
for i in range(1, 4):
    db.add(Estudiante(id=i, colegio_id=1, curso_id=1, nombre=f"E{i}",
                       apellido=f"X{i}", activo=True, no_lista=i))
db.commit()

# Cargar notas en CalificacionSecundaria (4 competencias × 4 períodos)
# Estudiante 1, Inglés: notas altas
for comp_n in range(1, 5):
    db.add(CalificacionSecundaria(
        colegio_id=1, estudiante_id=1, asignatura_id=1, ano_escolar_id=1,
        competencia_numero=comp_n, p1=85, p2=90, p3=88, p4=92
    ))
# Estudiante 1, Matemática: notas medias
for comp_n in range(1, 5):
    db.add(CalificacionSecundaria(
        colegio_id=1, estudiante_id=1, asignatura_id=2, ano_escolar_id=1,
        competencia_numero=comp_n, p1=75, p2=78, p3=72, p4=80
    ))
# Estudiante 2, Inglés: notas bajas
for comp_n in range(1, 5):
    db.add(CalificacionSecundaria(
        colegio_id=1, estudiante_id=2, asignatura_id=1, ano_escolar_id=1,
        competencia_numero=comp_n, p1=60, p2=65, p3=68, p4=72
    ))
db.commit()

# Test: get_calificaciones_periodo lee CalificacionSecundaria
print("\n=== Test: Notas por Período lee CalificacionSecundaria ===")
from services.stats_service import get_calificaciones_periodo

# Período 1
r = get_calificaciones_periodo(db, director, curso_id=1, periodo=1)
print(f"Período 1: {r['estudiantes']}")
e1 = next(e for e in r['estudiantes'] if e['estudiante_id'] == 1)
e2 = next(e for e in r['estudiantes'] if e['estudiante_id'] == 2)

# E1: Inglés P1 = 85 (PC = AVG de las 4 competencias)
# E1: Mate P1 = 75
# Promedio E1 P1 = (85+75)/2 = 80
print(f"\nE1 P1 Inglés: {e1['asignaturas'].get('Inglés')} (esperado 85)")
print(f"E1 P1 Mate: {e1['asignaturas'].get('Matemática')} (esperado 75)")
print(f"E1 promedio P1: {e1['promedio']} (esperado 80)")
assert e1['asignaturas']['Inglés'] == 85, f"Esperaba 85 dio {e1['asignaturas']['Inglés']}"
assert e1['asignaturas']['Matemática'] == 75
assert e1['promedio'] == 80

# E2: Inglés P1 = 60, Mate P1 = sin notas
print(f"\nE2 P1 Inglés: {e2['asignaturas'].get('Inglés')} (esperado 60)")
print(f"E2 P1 Mate: {e2['asignaturas'].get('Matemática')} (esperado None)")
assert e2['asignaturas']['Inglés'] == 60
assert e2['asignaturas']['Matemática'] is None

# E3: sin notas en nada
e3 = next(e for e in r['estudiantes'] if e['estudiante_id'] == 3)
print(f"E3 promedio: {e3['promedio']} (esperado None)")
assert e3['promedio'] is None
assert e3['asignaturas']['Inglés'] is None
assert e3['asignaturas']['Matemática'] is None

# Período 4 (último)
r4 = get_calificaciones_periodo(db, director, curso_id=1, periodo=4)
e1_p4 = next(e for e in r4['estudiantes'] if e['estudiante_id'] == 1)
print(f"\nE1 P4 Inglés: {e1_p4['asignaturas'].get('Inglés')} (esperado 92)")
print(f"E1 P4 Mate: {e1_p4['asignaturas'].get('Matemática')} (esperado 80)")
assert e1_p4['asignaturas']['Inglés'] == 92
assert e1_p4['asignaturas']['Matemática'] == 80

print("\n🎉 TEST v2.13.6 PASA — Notas por Período ahora lee CalificacionSecundaria correctamente")
