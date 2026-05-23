"""Test v2.13.13 — Vista B competencias por período + reporte padres PDF."""
import os, sys, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import (Base, Colegio, Usuario, AnoEscolar, Grado, Curso, Asignatura,
    Estudiante, AsignacionProfesor, CalificacionSecundaria, ConfiguracionColegio, Tanda)
from datetime import date, timedelta

e = create_engine('sqlite:///:memory:'); Base.metadata.create_all(e)
db = sessionmaker(bind=e)()
db.add(Colegio(id=1, nombre="Test", codigo="t"))
db.add(ConfiguracionColegio(id=1, colegio_id=1, nombre="Centro Test"))
hoy = date.today()
db.add(AnoEscolar(id=1, colegio_id=1, nombre="2025-2026", activo=True,
    fecha_inicio=hoy-timedelta(days=60), fecha_fin=hoy+timedelta(days=180), periodo_activo=4))
db.add(Grado(id=1, colegio_id=1, nombre="1ro", nivel="secundaria", ciclo="primer_ciclo", orden=1))
db.commit()
db.add(Curso(id=1, colegio_id=1, nombre="A", grado_id=1, activo=True))
db.add(Asignatura(id=1, colegio_id=1, nombre="Inglés", activo=True))
db.add(Asignatura(id=2, colegio_id=1, nombre="Matemática", activo=True))
director = Usuario(id=20, colegio_id=1, username="dir", password_hash="x",
    role="direccion", nombre="D", apellido="Y", activo=True, must_change_password=False)
db.add(director)
db.add(AsignacionProfesor(id=1, colegio_id=1, profesor_id=20, curso_id=1, asignatura_id=1, ano_escolar_id=1, activo=True))
db.add(AsignacionProfesor(id=2, colegio_id=1, profesor_id=20, curso_id=1, asignatura_id=2, ano_escolar_id=1, activo=True))
db.commit()
db.add(Estudiante(id=1, colegio_id=1, curso_id=1, nombre="Nelson", apellido="Acosta",
    activo=True, no_lista=1, matricula="11866902"))
db.commit()

# Inglés: 4 competencias con valores distintos por período
valores_ing = {
    1: {'p1':75,'p2':80,'p3':78,'p4':76},
    2: {'p1':77,'p2':82,'p3':80,'p4':75},
    3: {'p1':74,'p2':79,'p3':81,'p4':77},
    4: {'p1':76,'p2':80,'p3':79,'p4':78},
}
for num, vals in valores_ing.items():
    db.add(CalificacionSecundaria(colegio_id=1, estudiante_id=1, asignatura_id=1, ano_escolar_id=1,
        competencia_numero=num, **vals))
# Mate: solo 2 competencias cargadas (incompleto)
for num in [1, 2]:
    db.add(CalificacionSecundaria(colegio_id=1, estudiante_id=1, asignatura_id=2, ano_escolar_id=1,
        competencia_numero=num, p1=85, p2=88, p3=82, p4=90))
db.commit()

import app
from unittest.mock import MagicMock

# Test 1: Vista B - competencias por período
print("\n=== Test 1: competencias por período P4 ===")
req = MagicMock(); req.query_params = {}
r = asyncio.run(app.get_competencias_periodo_curso(1, 4, req, db=db, current_user=director))
print(f"Período: {r['periodo']}, asignaturas: {r['asignaturas_nombres']}")
est = r['estudiantes'][0]
ingles = next(a for a in est['asignaturas'] if a['asignatura'] == 'Inglés')
print(f"Inglés P4 competencias: {[(cv['competencia'], cv['valor']) for cv in ingles['competencias']]}")
print(f"Inglés PC4: {ingles['pc']} (esperado AVG(76,75,77,78)=76.5)")
assert ingles['pc'] == 76.5, f"PC4 esperado 76.5, dio {ingles['pc']}"
assert ingles['completo'] is True
# Mate incompleto (solo 2 competencias)
mate = next(a for a in est['asignaturas'] if a['asignatura'] == 'Matemática')
print(f"Mate PC4: {mate['pc']}, completo: {mate['completo']} (esperado incompleto)")
assert mate['completo'] is False
print("✅ Test 1 OK — desglose por competencia + PC calculado")

# Test 2: PC por período P1
print("\n=== Test 2: P1 ===")
r1 = asyncio.run(app.get_competencias_periodo_curso(1, 1, req, db=db, current_user=director))
ing1 = next(a for a in r1['estudiantes'][0]['asignaturas'] if a['asignatura'] == 'Inglés')
print(f"Inglés PC1: {ing1['pc']} (esperado AVG(75,77,74,76)=75.5)")
assert ing1['pc'] == 75.5
print("✅ Test 2 OK")

# Test 3: reporte padres curso completo
print("\n=== Test 3: reporte padres curso completo (P4) ===")
req3 = MagicMock(); req3.query_params = {'periodo': '4'}
res3 = asyncio.run(app.reporte_padres_curso_pdf(1, req3, db=db, current_user=director))
print(f"Respuesta tipo: {type(res3).__name__}")
print("✅ Test 3 OK — PDF curso generado")

# Test 4: reporte padres individual
print("\n=== Test 4: reporte padres individual ===")
req4 = MagicMock(); req4.query_params = {'periodo': '4', 'estudiante_id': '1'}
res4 = asyncio.run(app.reporte_padres_curso_pdf(1, req4, db=db, current_user=director))
print("✅ Test 4 OK — PDF individual generado")

# Guardar muestra
import io
req5 = MagicMock(); req5.query_params = {'periodo': '4'}
res5 = asyncio.run(app.reporte_padres_curso_pdf(1, req5, db=db, current_user=director))
body = b''
async def collect():
    chunks = []
    async for chunk in res5.body_iterator:
        chunks.append(chunk if isinstance(chunk, bytes) else chunk.encode())
    return b''.join(chunks)
body = asyncio.run(collect())
with open('/tmp/reporte_padres_muestra.pdf', 'wb') as f:
    f.write(body)
print(f"\n💾 Muestra guardada: {len(body)} bytes")

print("\n🎉 TODOS LOS TESTS v2.13.13 PASARON")
