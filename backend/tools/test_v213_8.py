"""
Tests v2.13.8 — Opción A: 8 endpoints arreglados
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
    ConfiguracionColegio, Asistencia, Tanda,
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
                   fecha_inicio=hoy-timedelta(days=60),
                   fecha_fin=hoy+timedelta(days=180),
                   periodo_activo=4, cerrado=False))
db.add(Grado(id=1, colegio_id=1, nombre="1ro", nivel="secundaria",
             ciclo="primer_ciclo", orden=1))
db.add(Grado(id=2, colegio_id=1, nombre="2do", nivel="secundaria",
             ciclo="primer_ciclo", orden=2))
db.commit()
db.add(Tanda(id=1, colegio_id=1, nombre="Matutina", activo=True))
db.add(Curso(id=1, colegio_id=1, nombre="A", grado_id=1, tanda_id=1, activo=True))
db.add(Asignatura(id=1, colegio_id=1, nombre="Inglés", activo=True))
db.add(Asignatura(id=2, colegio_id=1, nombre="Mate", activo=True))
director = Usuario(id=20, colegio_id=1, username="dir", password_hash="x",
                    role="direccion", nombre="D", apellido="Y",
                    activo=True, must_change_password=False)
prof = Usuario(id=10, colegio_id=1, username="prof", password_hash="x",
                role="profesor", nombre="P", apellido="X",
                activo=True, must_change_password=False)
db.add(director); db.add(prof)
db.add(AsignacionProfesor(id=1, colegio_id=1, profesor_id=10, curso_id=1,
                           asignatura_id=1, ano_escolar_id=1, activo=True))
db.add(AsignacionProfesor(id=2, colegio_id=1, profesor_id=10, curso_id=1,
                           asignatura_id=2, ano_escolar_id=1, activo=True))
db.commit()
for i in range(1, 3):
    db.add(Estudiante(id=i, colegio_id=1, curso_id=1, nombre=f"E{i}",
                       apellido=f"X{i}", activo=True, no_lista=i,
                       matricula=f"M{i:04d}"))
db.commit()

# E1: Aprobado en Inglés Y Mate
for comp_n in range(1, 5):
    for asig_id in [1, 2]:
        db.add(CalificacionSecundaria(
            colegio_id=1, estudiante_id=1, asignatura_id=asig_id, ano_escolar_id=1,
            competencia_numero=comp_n, p1=80, p2=85, p3=88, p4=90
        ))
# E2: Reprobado en Inglés, sin Mate
for comp_n in range(1, 5):
    db.add(CalificacionSecundaria(
        colegio_id=1, estudiante_id=2, asignatura_id=1, ano_escolar_id=1,
        competencia_numero=comp_n, p1=55, p2=60, p3=62, p4=58
    ))
db.commit()

import app
from unittest.mock import MagicMock

print("\n=== Test 1: /api/estudiantes/{id}/progreso lee CalificacionSecundaria ===")
r = asyncio.run(app.get_progreso_estudiante(1, db=db, current_user=director))
print(f"Periodos: {len(r['periodos'])}")
p4 = r['periodos'][3]
print(f"P4: promedio={p4['promedio']}, aprobadas={p4['aprobadas']}, asignaturas={[a['nota'] for a in p4['asignaturas']]}")
assert p4['promedio'] is not None and p4['promedio'] >= 88
assert p4['aprobadas'] == 2
assert r['promedio_general'] is not None and r['promedio_general'] > 80
print("✅ Test 1 OK")

print("\n=== Test 2: /api/estudiantes/{id}/historial dual-modelo ===")
# Hay 2 endpoints con el mismo path → FastAPI usa el último. Llamo al segundo (L7483).
# Aquí simulo llamando directamente al primero también para verificar el patch.
r1 = asyncio.run(app.get_historial_estudiante(1, db=db, current_user=director))
print(f"Académico: {len(r1['academico'])} asignaturas")
assert len(r1['academico']) == 2
for asig in r1['academico']:
    print(f"  {asig['asignatura']}: pc1={asig['pc1']}, cf={asig['cf']}, literal={asig['literal']}")
    assert asig['pc1'] is not None
    assert asig['cf'] is not None
print("✅ Test 2 OK")

print("\n=== Test 3: /api/reportes/notas/estudiante/{id}/periodo/{p} dual-modelo ===")
r = asyncio.run(app.get_reporte_notas_periodo(1, 4, db=db, current_user=director))
print(f"Asignaturas: {[a['asignatura'] for a in r['asignaturas']]}")
print(f"Promedio P4: {r['promedio_periodo']}")
assert len(r['asignaturas']) == 2
assert r['promedio_periodo'] >= 88
print("✅ Test 3 OK")

print("\n=== Test 4: /api/reportes/notas/curso/{id}/periodo/{p} dual-modelo ===")
r = asyncio.run(app.get_reporte_notas_curso(1, 4, db=db, current_user=director))
print(f"Estudiantes en reporte: {len(r['estudiantes'])}")
e1 = next(e for e in r['estudiantes'] if e['estudiante_id'] == 1)
e2 = next(e for e in r['estudiantes'] if e['estudiante_id'] == 2)
print(f"E1: promedio={e1['promedio']}, estado={e1['estado']}")
print(f"E2: promedio={e2['promedio']}, estado={e2['estado']}")
assert e1['estado'] == 'Aprobado'
# E2 tiene solo Inglés con nota baja
assert e2['estado'] == 'Reprobado'
print("✅ Test 4 OK")

print("\n=== Test 5: /api/promocion/estudiantes dual-modelo ===")
req5 = MagicMock(); req5.query_params = {}
r_full = asyncio.run(app.get_estudiantes_promocion(req5, db=db, current_user=director))
r = r_full['estudiantes'] if isinstance(r_full, dict) else r_full
e1 = next(e for e in r if e['id'] == 1)
e2 = next(e for e in r if e['id'] == 2)
print(f"E1: promedio={e1['promedio_general']}, condicion={e1['condicion']}")
print(f"E2: promedio={e2['promedio_general']}, condicion={e2['condicion']}")
assert e1['condicion'] == 'Promovido'
assert 'Promovido' in e2['condicion'] or e2['condicion'] == 'Reprobado'  # E2 tiene 1 reprobada
print("✅ Test 5 OK")

print("\n=== Test 6: /api/cierre-ano/resumen dual-modelo ===")
r = asyncio.run(app.get_resumen_cierre_ano(db=db, current_user=director))
print(f"Cursos: {r['cursos']}")
assert len(r['cursos']) >= 1
curso_1 = next(c for c in r['cursos'] if c['id'] == 1)
print(f"Curso 1: promovidos={curso_1['promovidos']}, promedio={curso_1['promedio']}")
assert curso_1['promovidos'] >= 1
assert curso_1['promedio'] > 70
print("✅ Test 6 OK")

print("\n=== Test 7: /api/cierre-ano/promocion dual-modelo ===")
r = asyncio.run(app.get_datos_promocion(db=db, current_user=director))
e1 = next(e for e in r['estudiantes'] if e['id'] == 1)
print(f"E1: promedio={e1['promedio_general']}, condicion={e1['condicion']}")
assert e1['condicion'] == 'promovido'
print("✅ Test 7 OK")

print("\n=== Test 8: /api/calificaciones/por-materia dual-modelo ===")
req8 = MagicMock(); req8.query_params = {'curso_id': '1'}
r = asyncio.run(app.get_calificaciones_por_materia(req8, db=db, current_user=director))
print(f"Asignaturas en reporte: {len(r['asignaturas'])}")
ingles = next(a for a in r['asignaturas'] if a['nombre'] == 'Inglés')
e1_ing = next(e for e in ingles['estudiantes'] if e['id'] == 1)
print(f"E1 Inglés: p1={e1_ing['p1']}, p4={e1_ing['p4']}, cf={e1_ing['cf']}")
assert e1_ing['p1'] is not None and e1_ing['p1'] >= 80
assert e1_ing['cf'] is not None
print("✅ Test 8 OK")

print("\n🎉 TODOS LOS 8 TESTS v2.13.8 PASARON")
