"""
Tests v2.13.3 — Bugs de asistencia y estadísticas

Valida:
1. _construir_asistencias_boletin con AnoEscolar SIN rangos p1_inicio/p1_fin
   → fallback a dividir fecha_inicio/fecha_fin en 4 trimestres
2. _construir_asistencias_boletin con asistencias fuera de todos los rangos
   → mapeo al período más cercano (no descartar)
3. get_stats_cursos lee CalificacionSecundaria
4. /api/estadisticas/asignaturas lee CalificacionSecundaria
"""
import os
import sys
import asyncio
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import (
    Base, Colegio, Usuario, AnoEscolar, Grado, Curso, Asignatura,
    Estudiante, AsignacionProfesor, CalificacionSecundaria,
    ConfiguracionColegio, Asistencia
)

engine = create_engine('sqlite:///:memory:', echo=False)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
db = Session()

# Setup
colegio = Colegio(id=1, nombre="Test", codigo="test")
db.add(colegio)
config = ConfiguracionColegio(id=1, colegio_id=1, nombre="Test",
                                permite_sabado=False, permite_domingo=False)
db.add(config)

# Año escolar SIN p1_inicio (caso bug)
ano = AnoEscolar(
    id=1, colegio_id=1, nombre="2025-2026",
    fecha_inicio=date(2025, 8, 1),
    fecha_fin=date(2026, 6, 30),
    activo=True, cerrado=False,
)
db.add(ano)

grado = Grado(id=1, colegio_id=1, nombre="1ro", nivel="secundaria", ciclo="primer_ciclo", orden=1)
db.add(grado)
db.commit()

curso = Curso(id=1, colegio_id=1, nombre="A", grado_id=1)
db.add(curso)
asig = Asignatura(id=1, colegio_id=1, nombre="Inglés", activo=True)
db.add(asig)
director = Usuario(id=10, colegio_id=1, username="dir", password_hash="x",
                    role="direccion", nombre="Test", apellido="D", activo=True, must_change_password=False)
db.add(director)
db.commit()

est = Estudiante(id=1, colegio_id=1, curso_id=1, nombre="Juan", apellido="Pérez", activo=True)
db.add(est)
db.commit()

# Cargar asistencias en mayo 2026 (cae en P4 si se divide bien)
for dia in [10, 11, 12, 13, 14]:
    a = Asistencia(colegio_id=1, estudiante_id=1, curso_id=1, fecha=date(2026, 5, dia), estado='presente')
    db.add(a)
a = Asistencia(colegio_id=1, estudiante_id=1, curso_id=1, fecha=date(2026, 5, 15), estado='ausente')
db.add(a)
db.commit()

# Test 1: _construir_asistencias_boletin con fallback de períodos
print("\n=== Test 1: asistencias caen en algún período (fallback) ===")
from app import _construir_asistencias_boletin
result = _construir_asistencias_boletin(db, 1, director, ano)
print(f"Resultado: {result}")

total_asis = sum((result.get(f'p{p}') or {}).get('asistencia', 0) for p in range(1, 5))
total_aus = sum((result.get(f'p{p}') or {}).get('ausencia', 0) for p in range(1, 5))
print(f"Total presencias contadas: {total_asis} (esperado 5)")
print(f"Total ausencias contadas: {total_aus} (esperado 1)")
assert total_asis == 5, f"❌ Esperaba 5 presencias, dio {total_asis}"
assert total_aus == 1, f"❌ Esperaba 1 ausencia, dio {total_aus}"
print("✅ Test 1 OK — el fallback de períodos funciona")

# Test 2: con período fuera de rango (asistencia en julio cuando solo hay p1-p4 hasta junio)
print("\n=== Test 2: asistencia con fecha fuera de rango → período más cercano ===")
# Reset
db.query(Asistencia).delete()
db.commit()

ano.p1_inicio = date(2025, 9, 1); ano.p1_fin = date(2025, 10, 31)
ano.p2_inicio = date(2025, 11, 1); ano.p2_fin = date(2025, 12, 31)
ano.p3_inicio = date(2026, 1, 1); ano.p3_fin = date(2026, 2, 28)
ano.p4_inicio = date(2026, 3, 1); ano.p4_fin = date(2026, 4, 30)  # fin abril
db.commit()

# Asistencia en mayo (después de P4)
a = Asistencia(colegio_id=1, estudiante_id=1, curso_id=1, fecha=date(2026, 5, 15), estado='presente')
db.add(a)
db.commit()

result = _construir_asistencias_boletin(db, 1, director, ano)
total_asis = sum((result.get(f'p{p}') or {}).get('asistencia', 0) for p in range(1, 5))
print(f"Total presencias (esperado 1, mapeada al período más cercano): {total_asis}")
assert total_asis == 1, f"❌ Asistencia perdida, esperaba 1 dio {total_asis}"
# Debería caer en P4 (el más cercano)
p4_asis = (result.get('p4') or {}).get('asistencia', 0)
print(f"En P4 (esperado 1): {p4_asis}")
assert p4_asis == 1, f"❌ No cayó en P4, dio {result}"
print("✅ Test 2 OK — fechas fuera de rango se mapean al período más cercano")

# Test 3: stats_service lee CalificacionSecundaria
print("\n=== Test 3: get_stats_cursos lee CalificacionSecundaria ===")
# Cargar las 4 competencias para juan
for comp_n in range(1, 5):
    c = CalificacionSecundaria(
        colegio_id=1, estudiante_id=1, asignatura_id=1, ano_escolar_id=1,
        competencia_numero=comp_n, p1=85, p2=90, p3=80, p4=88,
    )
    db.add(c)
db.commit()

from services.stats_service import get_stats_cursos

stats = get_stats_cursos(db, director, periodo=0, nivel=None)
print(f"Stats: {stats}")
assert stats, "❌ Stats vacío"
curso0 = stats[0]
assert curso0['promedio'] > 0, f"❌ Promedio sigue en 0: {curso0}"
print(f"✅ Test 3 OK — promedio {curso0['promedio']} > 0")

# Test 4: /api/estadisticas/asignaturas
print("\n=== Test 4: /api/estadisticas/asignaturas lee CalificacionSecundaria ===")
import app
from unittest.mock import MagicMock

req = MagicMock()
req.query_params = {'periodo': '0'}
r = asyncio.run(app.get_estadisticas_asignaturas(req, db=db, current_user=director))
print(f"Resultado: {r}")
assert isinstance(r, list)
assert len(r) > 0, "❌ Lista vacía"
asig0 = r[0]
assert asig0['promedio'] > 0, f"❌ Promedio asignatura en 0: {asig0}"
print(f"✅ Test 4 OK — asignatura {asig0['nombre']} con promedio {asig0['promedio']}")

print("\n🎉 TODOS LOS TESTS v2.13.3 PASARON")
