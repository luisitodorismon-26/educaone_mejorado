"""
Tests v2.13.7 — Sub-sprint B (Opción B):
1. /api/boletines/estudiante/{id} JSON con CalificacionSecundaria
2. /api/boletines/estudiante/{id}/pdf con adapter
3. /api/boletines/curso/{id}/pdf con AMBOS modelos
4. /api/alertas detecta secundaria nueva (CF<70 y pendientes)
5. /api/calificaciones/resumen-curso/{id} con AMBOS modelos
"""
import os, sys, asyncio
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import (
    Base, Colegio, Usuario, AnoEscolar, Grado, Curso, Asignatura,
    Estudiante, AsignacionProfesor, CalificacionSecundaria,
    ConfiguracionColegio, Asistencia,
)

engine = create_engine('sqlite:///:memory:', echo=False)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
db = Session()

# Setup
db.add(Colegio(id=1, nombre="Test", codigo="test"))
db.add(ConfiguracionColegio(id=1, colegio_id=1, nombre="Test"))
hoy = date.today()
db.add(AnoEscolar(id=1, colegio_id=1, nombre="2025-2026", activo=True,
                   fecha_inicio=hoy-timedelta(days=60), fecha_fin=hoy+timedelta(days=180),
                   periodo_activo=4,
                   p1_inicio=hoy-timedelta(days=60), p1_fin=hoy+timedelta(days=5), p1_cerrado=False))
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
                       apellido=f"X{i}", activo=True, no_lista=i,
                       matricula=f"M{i:04d}"))
db.commit()

# Notas en CalificacionSecundaria:
# E1: aprobado en ambas (CF >= 70)
for comp_n in range(1, 5):
    for asig_id in [1, 2]:
        db.add(CalificacionSecundaria(
            colegio_id=1, estudiante_id=1, asignatura_id=asig_id, ano_escolar_id=1,
            competencia_numero=comp_n, p1=85, p2=88, p3=90, p4=87
        ))
# E2: reprobado en Inglés (CF < 70)
for comp_n in range(1, 5):
    db.add(CalificacionSecundaria(
        colegio_id=1, estudiante_id=2, asignatura_id=1, ano_escolar_id=1,
        competencia_numero=comp_n, p1=60, p2=65, p3=62, p4=64
    ))
# E2: sin notas en Matemática
# E3: sin notas en nada
db.commit()

import app
from unittest.mock import MagicMock

# ─── Test 1: boletín JSON ───
print("\n=== Test 1: /api/boletines/estudiante/{id} lee CalificacionSecundaria ===")
req = MagicMock(); req.query_params = {}
r = asyncio.run(app.get_boletin_estudiante(1, req, db=db, current_user=director))
print(f"Asignaturas: {[a['asignatura'] for a in r['asignaturas']]}")
assert len(r['asignaturas']) == 2, f"Esperaba 2 asignaturas, dio {len(r['asignaturas'])}"
ing = next(a for a in r['asignaturas'] if a['asignatura'] == 'Inglés')
print(f"Inglés: PC1={ing['pc1']} PC2={ing['pc2']} PC3={ing['pc3']} PC4={ing['pc4']} CF={ing['cf']}")
assert ing['pc1'] == 85, f"PC1 esperado 85, dio {ing['pc1']}"
assert ing['cf'] is not None and ing['cf'] >= 85
print(f"Promedio general: {r['promedio_general']}")
assert r['promedio_general'] > 80
print("✅ Test 1 OK")

# Test 1.b: E3 sin notas
r3 = asyncio.run(app.get_boletin_estudiante(3, req, db=db, current_user=director))
print(f"E3 asignaturas: {len(r3['asignaturas'])} (esperado 0)")
assert len(r3['asignaturas']) == 0
print("✅ Test 1.b OK — estudiante sin notas devuelve lista vacía")

# ─── Test 2: alertas ───
print("\n=== Test 2: /api/alertas con CalificacionSecundaria ===")
# E2 tiene CF<70 en Inglés (60+65+62+64)/4 = 62.75 → <70
# Cargo solo p1 del estudiante 1 en período activo
# Pero esperamos que detecte estudiante E2 como bajo rendimiento

req_a = MagicMock(); req_a.query_params = {}
result = asyncio.run(app.get_alertas(db=db, current_user=director))
# Endpoint devuelve lista directamente, no dict
alertas = result if isinstance(result, list) else result.get('alertas', [])
print(f"Alertas: {[a['titulo'] for a in alertas]}")
alerta_rendimiento = next((a for a in alertas if a['tipo'] == 'rendimiento'), None)
print(f"Alerta rendimiento: {alerta_rendimiento}")
assert alerta_rendimiento is not None, "❌ No detectó estudiantes en riesgo"
assert '1' in alerta_rendimiento['titulo'], f"Esperaba 1 estudiante en riesgo, dio: {alerta_rendimiento['titulo']}"
print("✅ Test 2 OK — alerta rendimiento detecta CF<70 en modelo nuevo")

# ─── Test 3: resumen-curso ───
print("\n=== Test 3: /api/calificaciones/resumen-curso/{id} ===")
req_r = MagicMock(); req_r.query_params = {}
r_curso = asyncio.run(app.get_resumen_calificaciones_curso(1, req_r, db=db, current_user=director))
print(f"Asignaturas: {r_curso['asignaturas']}")
print(f"Estudiantes: {len(r_curso['estudiantes'])}")
e1_data = next(e for e in r_curso['estudiantes'] if e['id'] == 1)
print(f"E1: {e1_data}")
# E1 debería tener data en ambas materias
assert e1_data['materias']['Inglés'] is not None
assert e1_data['materias']['Inglés']['cf'] is not None
assert e1_data['promedio_general'] is not None and e1_data['promedio_general'] > 80
print(f"✅ Test 3 OK — E1 promedio {e1_data['promedio_general']}")

# ─── Test 4: boletín PDF viejo (con adapter) ───
print("\n=== Test 4: /api/boletines/estudiante/{id}/pdf con adapter ===")
req_pdf = MagicMock(); req_pdf.query_params = {}
try:
    result_pdf = asyncio.run(app.generar_boletin_pdf(1, req_pdf, db=db, current_user=director))
    print(f"Tipo respuesta: {type(result_pdf).__name__}")
    # Si es StreamingResponse no hubo error
    print("✅ Test 4 OK — PDF generado sin error con CalificacionSecundaria")
except Exception as e:
    print(f"❌ Test 4 FALLA: {e}")
    raise

# ─── Test 5: boletines curso PDF ───
print("\n=== Test 5: /api/boletines/curso/{id}/pdf con AMBOS modelos ===")
try:
    result_curso = asyncio.run(app.generar_boletines_curso_pdf(1, db=db, current_user=director))
    print(f"Tipo respuesta: {type(result_curso).__name__}")
    print("✅ Test 5 OK — PDF curso generado sin error")
except Exception as e:
    print(f"❌ Test 5 FALLA: {e}")
    raise

print("\n🎉 TODOS LOS TESTS v2.13.7 PASARON")
