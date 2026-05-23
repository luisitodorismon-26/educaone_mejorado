"""Test v2.13.11 — Verifica que TODAS las plantillas MINERD (1ro-6to NS)
funcionan correctamente: routing por grado específico + generación PDF + color negro."""
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
db.add(ConfiguracionColegio(id=1, colegio_id=1, nombre="Centro Educativo Test"))
hoy = date.today()
db.add(AnoEscolar(id=1, colegio_id=1, nombre="2025-2026", activo=True,
                   fecha_inicio=hoy-timedelta(days=60), fecha_fin=hoy+timedelta(days=180),
                   periodo_activo=4))

# Grados 1ro a 6to NS
grados_data = [
    (1, "1ro", "primer_ciclo"),
    (2, "2do", "primer_ciclo"),
    (3, "3ro", "primer_ciclo"),
    (4, "4to", "segundo_ciclo"),
    (5, "5to", "segundo_ciclo"),
    (6, "6to", "segundo_ciclo"),
]
for gid, nombre, ciclo in grados_data:
    db.add(Grado(id=gid, colegio_id=1, nombre=nombre, nivel="secundaria",
                 ciclo=ciclo, orden=gid))
db.commit()

# Cursos
for gid, nombre, _ in grados_data:
    db.add(Curso(id=gid, colegio_id=1, nombre="A", grado_id=gid, activo=True))

# Asignaturas
asigs_primer = ['Lengua Española', 'Matemática', 'Inglés', 'Ciencias Sociales',
                'Ciencias de la Naturaleza', 'Educación Artística', 'Educación Física',
                'Formación Integral Humana y Religiosa']
for i, n in enumerate(asigs_primer, 1):
    db.add(Asignatura(id=i, colegio_id=1, nombre=n, activo=True))
db.commit()

# Test 1: routing por grado específico
print("\n=== Test 1: routing por grado específico ===")
from boletin_minerd_secundaria import _get_plantilla_path, _es_segundo_ciclo, _identificar_grado

esperado = {
    1: 'Boletin-1ro-grado-NS.pdf',
    2: 'Boletin-2do-grado-NS.pdf',
    3: 'Boletin-3ro-grado-NS.pdf',
    4: 'Boletin-4to-grado-NS.pdf',
    5: 'Boletin-5to-grado-NS.pdf',
    6: 'Boletin-6to-grado-NS.pdf',
}
for gid, archivo_esp in esperado.items():
    curso = db.get(Curso, gid)
    curso.grado = db.get(Grado, gid)
    path = _get_plantilla_path(curso)
    es_seg = _es_segundo_ciclo(curso)
    grado_id = _identificar_grado(curso)
    print(f"  Grado {gid} ({grados_data[gid-1][1]}): {os.path.basename(path)} | identificado={grado_id} | segundo_ciclo={es_seg}")
    assert archivo_esp in path, f"❌ Esperaba {archivo_esp}, dio {path}"
    # 1, 2, 3 = primer ciclo (no segundo); 4, 5, 6 = segundo ciclo
    if gid <= 3:
        assert es_seg is False, f"❌ Grado {gid} debe ser primer ciclo"
    else:
        assert es_seg is True, f"❌ Grado {gid} debe ser segundo ciclo"
print("✅ Routing por grado específico correcto para los 6 grados")

# Test 2: color es negro
print("\n=== Test 2: color de escritura es NEGRO ===")
from boletin_minerd_secundaria import COLOR_DATOS, COLOR_NEGRO
print(f"COLOR_DATOS={COLOR_DATOS}, COLOR_NEGRO={COLOR_NEGRO}")
# Color object con _ks atributo o str
assert str(COLOR_DATOS) == str(COLOR_NEGRO), f"❌ Color no es negro: {COLOR_DATOS}"
print("✅ COLOR_DATOS == COLOR_NEGRO (escritura en negro)")

# Test 3: generar PDF de cada grado
print("\n=== Test 3: generar PDFs reales para los 6 grados ===")
from boletin_minerd_secundaria import generar_boletin_secundaria_minerd

# Crear un estudiante para cada grado y notas
for gid, nombre_g, _ in grados_data:
    est_id = 100 + gid
    db.add(Estudiante(id=est_id, colegio_id=1, curso_id=gid,
                      nombre=f"Estudiante", apellido=f"{nombre_g}",
                      activo=True, no_lista=1, matricula=f"M{est_id:04d}"))
db.commit()

for gid, nombre_g, ciclo in grados_data:
    est_id = 100 + gid
    # Cargar 4 competencias × 8 asignaturas (las 8 del primer ciclo)
    for asig_id in range(1, 9):
        for comp_n in range(1, 5):
            db.add(CalificacionSecundaria(
                colegio_id=1, estudiante_id=est_id, asignatura_id=asig_id, ano_escolar_id=1,
                competencia_numero=comp_n, p1=80+gid, p2=85, p3=82, p4=88
            ))
db.commit()

asigs_legacy = {asig_id: db.get(Asignatura, asig_id) for asig_id in range(1, 9)}
generados = []
for gid, nombre_g, ciclo in grados_data:
    est_id = 100 + gid
    est = db.get(Estudiante, est_id)
    curso = db.get(Curso, gid)
    curso.grado = db.get(Grado, gid)
    
    # Construir datos por asignatura
    califs_por_asig = {}
    for asig_id, asig_obj in asigs_legacy.items():
        comps = db.query(CalificacionSecundaria).filter_by(
            estudiante_id=est_id, asignatura_id=asig_id, ano_escolar_id=1
        ).order_by(CalificacionSecundaria.competencia_numero).all()
        califs_por_asig[asig_id] = {
            'asignatura_nombre': asig_obj.nombre,
            'competencias': comps,
            'pc_por_periodo': {f'pc{p}': 85.0 for p in range(1, 5)},
            'cf': 85,
            'literal': 'B',
            'evaluacion_extra': None,
        }
    
    asistencias = {f'p{p}': {'asistencia': 22, 'ausencia': 0, 'pct_asistencia_anual': 100, 'pct_ausencia_anual': 0} for p in range(1, 5)}
    situacion = {'promovido': True, 'repitente': False, 'condicion': 'APROBADO/A — Promovido'}
    
    buffer = generar_boletin_secundaria_minerd(
        estudiante=est, curso=curso,
        calificaciones_por_asig=califs_por_asig,
        asistencias_por_periodo=asistencias,
        config=db.get(ConfiguracionColegio, 1),
        ano_escolar=db.get(AnoEscolar, 1),
        observaciones=f"Boletín de prueba — {nombre_g} NS",
        situacion_final=situacion,
    )
    pdf_bytes = buffer.read()
    assert pdf_bytes.startswith(b'%PDF-')
    
    out_path = f'/tmp/test_boletin_{nombre_g}_NS.pdf'
    with open(out_path, 'wb') as f:
        f.write(pdf_bytes)
    print(f"  ✅ {nombre_g} NS: {len(pdf_bytes)} bytes → {out_path}")
    generados.append(out_path)

print(f"\n🎉 TODOS los 6 grados generan PDF correctamente con plantilla específica + color negro")
print(f"PDFs generados: {len(generados)}")
