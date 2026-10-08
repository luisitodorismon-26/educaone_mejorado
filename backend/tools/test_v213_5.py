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

# ─── Test 3-5: /academico usa la ASISTENCIA CANÓNICA ───
# Antes esta pantalla dividía entre `dias_trabajados` del mes (o entre los
# días con registro). Ahora dice exactamente lo mismo que el boletín: días
# lectivos del colegio, un día sin lista es SIN DATO y el % solo existe con
# cobertura completa del mes.
import app
from unittest.mock import MagicMock

mes_actual = 5
ano_actual = 2026
req = MagicMock()
req.query_params = {'mes': str(mes_actual), 'ano': str(ano_actual)}


def fila_de(est_id):
    res = asyncio.run(app.get_resumen_asistencia_por_periodos(
        1, req, db=db, current_user=director))
    return next(r for r in res if r['estudiante_id'] == est_id)


def habiles_mayo(desde, hasta):
    return [date(ano_actual, mes_actual, d) for d in range(desde, hasta + 1)
            if date(ano_actual, mes_actual, d).weekday() < 5]


print("\n=== Test 3: mes con huecos -> N/D, aunque haya dias_trabajados ===")
ano.set_dias_trabajados({'may': 20})
db.commit()
for dia in range(1, 19):
    db.add(Asistencia(colegio_id=1, estudiante_id=1, curso_id=1,
                      fecha=date(ano_actual, mes_actual, dia), estado='presente'))
for dia in [19, 20]:
    db.add(Asistencia(colegio_id=1, estudiante_id=1, curso_id=1,
                      fecha=date(ano_actual, mes_actual, dia), estado='ausente'))
db.commit()
est1 = fila_de(1)
print(f"  asistencia_mes={est1['asistencia_mes']} sin_dato_mes={est1['sin_dato_mes']} "
      f"pct_asistencia_mes={est1['pct_asistencia_mes']}")
assert est1['_usa_dias_trabajados'] is False, 'dias_trabajados ya no es el denominador'
assert est1['asistencia_mes'] == 18
assert est1['sin_dato_mes'] > 0
assert est1['pct_asistencia_mes'] is None, f"❌ con huecos debe ser N/D, dio {est1['pct_asistencia_mes']}"
print("✅ Mes incompleto: % N/D, no un 90 % inventado")

print("\n=== Test 4: mes completo -> % real ===")
for f in habiles_mayo(21, 31):
    db.add(Asistencia(colegio_id=1, estudiante_id=1, curso_id=1, fecha=f, estado='presente'))
db.commit()
est1_b = fila_de(1)
_lect = est1_b['dias_lectivos_mes']
_esperado = round(est1_b['asistencia_mes'] * 100.0 / _lect, 1)
print(f"  {est1_b['asistencia_mes']} de {_lect} días -> {est1_b['pct_asistencia_mes']}%")
assert est1_b['sin_dato_mes'] == 0
assert est1_b['pct_asistencia_mes'] == _esperado, f"❌ Esperaba {_esperado}, dio {est1_b['pct_asistencia_mes']}"
_an = app._asistencia_anual_boletin(db, 1, director, ano)
assert est1_b['total_asistencia'] == _an['asistencias'], 'el anual es el del boletín'
print(f"✅ Mes completo: {est1_b['pct_asistencia_mes']}% (mismo cálculo que el boletín)")

print("\n=== Test 5: nunca pasa de 100 % ===")
for f in habiles_mayo(1, 31):
    db.add(Asistencia(colegio_id=1, estudiante_id=2, curso_id=1, fecha=f, estado='presente'))
db.commit()
est2 = fila_de(2)
print(f"  pct_asistencia_mes: {est2['pct_asistencia_mes']}")
assert est2['pct_asistencia_mes'] == 100.0, f"❌ Esperaba 100, dio {est2['pct_asistencia_mes']}"
print("✅ 100 % con todo presente, sin pasarse")

print("\n🎉 TODOS LOS TESTS v2.13.5 PASARON")
