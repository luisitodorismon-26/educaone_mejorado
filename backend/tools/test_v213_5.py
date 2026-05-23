"""
Tests v2.13.5:
1. get_graficos lee CalificacionSecundaria (estadísticas por grado funciona)
2. Estado de estudiantes con datos de CalificacionSecundaria
3. Endpoint asistencia con dias_trabajados como denominador
4. Endpoint asistencia con fallback cuando NO hay dias_trabajados
"""
import os, sys, asyncio
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import (
    Base, Colegio, Usuario, AnoEscolar, Grado, Curso, Asignatura,
    Estudiante, CalificacionSecundaria, ConfiguracionColegio, Asistencia
)

engine = create_engine('sqlite:///:memory:', echo=False)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
db = Session()

# Setup
colegio = Colegio(id=1, nombre="Test", codigo="test")
db.add(colegio)
config = ConfiguracionColegio(id=1, colegio_id=1, nombre="Test")
db.add(config)
ano = AnoEscolar(id=1, colegio_id=1, nombre="2025-2026", activo=True,
                  fecha_inicio=date(2025, 8, 1), fecha_fin=date(2026, 6, 30),
                  periodo_activo=4)
db.add(ano)
grado = Grado(id=1, colegio_id=1, nombre="1ro", nivel="secundaria",
              ciclo="primer_ciclo", orden=1)
db.add(grado)
db.commit()
curso = Curso(id=1, colegio_id=1, nombre="A", grado_id=1)
db.add(curso)
asig = Asignatura(id=1, colegio_id=1, nombre="Inglés", activo=True)
db.add(asig)
director = Usuario(id=10, colegio_id=1, username="dir", password_hash="x",
                    role="direccion", nombre="Dir", apellido="A",
                    activo=True, must_change_password=False)
db.add(director)
db.commit()

# 3 estudiantes en el mismo grado
for i in range(1, 4):
    e = Estudiante(id=i, colegio_id=1, curso_id=1, nombre=f"E{i}", apellido=f"X{i}", activo=True)
    db.add(e)
db.commit()

# Notas para los 3: comp1-4 con p1-p4
for est_id in range(1, 4):
    for comp in range(1, 5):
        c = CalificacionSecundaria(
            colegio_id=1, estudiante_id=est_id, asignatura_id=1, ano_escolar_id=1,
            competencia_numero=comp, p1=80+est_id, p2=85, p3=90, p4=88
        )
        db.add(c)
db.commit()

# ─── Test 1: get_graficos lee CalificacionSecundaria ───
print("\n=== Test 1: get_graficos lee CalificacionSecundaria ===")
from services.stats_service import get_graficos
r = get_graficos(db, director)
print(f"promedios_por_grado: {r.get('promedios_por_grado')}")
assert r.get('promedios_por_grado'), "❌ Sin promedios por grado"
assert r['promedios_por_grado'][0]['promedio'] > 0, "❌ Promedio en 0"
print(f"✅ Promedio del grado 1ro: {r['promedios_por_grado'][0]['promedio']}")

# ─── Test 2: estado_estudiantes ───
print("\n=== Test 2: estado_estudiantes lee CalificacionSecundaria ===")
print(f"estado: {r.get('estado_estudiantes')}")
estado = {e['nombre']: e['cantidad'] for e in r['estado_estudiantes']}
assert estado.get('Aprobados', 0) > 0, f"❌ Sin aprobados, estado: {estado}"
print(f"✅ Aprobados: {estado.get('Aprobados')}, Reprobados: {estado.get('Reprobados')}, En Proceso: {estado.get('En Proceso')}")

# ─── Test 3: asistencia con dias_trabajados ───
print("\n=== Test 3: asistencia con dias_trabajados configurados ===")
# Configurar dias_trabajados: mayo = 20 días hábiles
ano.set_dias_trabajados({'may': 20})
db.commit()

# Estudiante 1: 18 presentes en mayo, 2 ausentes
import calendar
mes_actual = 5
ano_actual = 2026
for dia in range(1, 19):
    a = Asistencia(colegio_id=1, estudiante_id=1, curso_id=1,
                   fecha=date(ano_actual, mes_actual, dia), estado='presente')
    db.add(a)
for dia in [19, 20]:
    a = Asistencia(colegio_id=1, estudiante_id=1, curso_id=1,
                   fecha=date(ano_actual, mes_actual, dia), estado='ausente')
    db.add(a)
db.commit()

import app
from unittest.mock import MagicMock

req = MagicMock()
req.query_params = {'mes': str(mes_actual), 'ano': str(ano_actual)}
result = asyncio.run(app.get_resumen_asistencia_por_periodos(
    1, req, db=db, current_user=director
))
print(f"Resultado completo del estudiante 1: {[r for r in result if r['estudiante_id']==1]}")
est1 = next(r for r in result if r['estudiante_id'] == 1)
print(f"  dias_trabajados_mes: {est1['dias_trabajados_mes']}")
print(f"  asistencia_mes: {est1['asistencia_mes']}")
print(f"  pct_asistencia_mes: {est1['pct_asistencia_mes']}")
print(f"  _usa_dias_trabajados: {est1['_usa_dias_trabajados']}")

# 18 / 20 = 90%
assert est1['_usa_dias_trabajados'] is True
assert est1['dias_trabajados_mes'] == 20
assert est1['asistencia_mes'] == 18
expected = round(18 / 20 * 100, 0)  # 90
assert est1['pct_asistencia_mes'] == expected, f"❌ Esperaba {expected}%, dio {est1['pct_asistencia_mes']}"
print(f"✅ % = 18/20 × 100 = {est1['pct_asistencia_mes']}% ✓")

# ─── Test 4: fallback cuando NO hay dias_trabajados ───
print("\n=== Test 4: fallback sin dias_trabajados ===")
# Reset asistencias estudiante 1 y cargarlas en días distintos
db.query(Asistencia).filter(Asistencia.estudiante_id == 1).delete()
db.commit()
# 18 presentes (días 1-18) y 2 ausentes (días 19, 20)
for dia in range(1, 19):
    a = Asistencia(colegio_id=1, estudiante_id=1, curso_id=1,
                   fecha=date(ano_actual, mes_actual, dia), estado='presente')
    db.add(a)
for dia in [19, 20]:
    a = Asistencia(colegio_id=1, estudiante_id=1, curso_id=1,
                   fecha=date(ano_actual, mes_actual, dia), estado='ausente')
    db.add(a)
db.commit()

ano.set_dias_trabajados({})  # vaciar
db.commit()

result2 = asyncio.run(app.get_resumen_asistencia_por_periodos(
    1, req, db=db, current_user=director
))
est1_b = next(r for r in result2 if r['estudiante_id'] == 1)
print(f"  _usa_dias_trabajados: {est1_b['_usa_dias_trabajados']}")
print(f"  asistencia_mes: {est1_b['asistencia_mes']}, ausencia_mes: {est1_b['ausencia_mes']}")
print(f"  pct_asistencia_mes: {est1_b['pct_asistencia_mes']}")
assert est1_b['_usa_dias_trabajados'] is False
# 18 / (18+2) = 90
assert est1_b['pct_asistencia_mes'] == 90, f"Esperaba 90, dio {est1_b['pct_asistencia_mes']}"
print(f"✅ Fallback: 18/(18+2) × 100 = {est1_b['pct_asistencia_mes']}% ✓")

# ─── Test 5: % no excede 100 cuando cargas más que dias_trabajados ───
print("\n=== Test 5: cap a 100% si presentes > dias_trabajados ===")
# Estudiante 2: 25 presentes (más que dias_trabajados=20)
db.query(Asistencia).filter(Asistencia.estudiante_id == 2).delete()
db.commit()
for dia in range(1, 26):
    a = Asistencia(colegio_id=1, estudiante_id=2, curso_id=1,
                   fecha=date(ano_actual, mes_actual, dia), estado='presente')
    db.add(a)
db.commit()

ano.set_dias_trabajados({'may': 20})
db.commit()

result3 = asyncio.run(app.get_resumen_asistencia_por_periodos(
    1, req, db=db, current_user=director
))
est2 = next(r for r in result3 if r['estudiante_id'] == 2)
print(f"  asistencia_mes: {est2['asistencia_mes']}, dias_trabajados: {est2['dias_trabajados_mes']}")
print(f"  pct_asistencia_mes: {est2['pct_asistencia_mes']}")
assert est2['pct_asistencia_mes'] == 100, f"❌ Debería caparse a 100, dio {est2['pct_asistencia_mes']}"
print("✅ % capado a 100 cuando presentes > dias_trabajados")

print("\n🎉 TODOS LOS TESTS v2.13.5 PASARON")
