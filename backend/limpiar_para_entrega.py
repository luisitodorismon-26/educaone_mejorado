"""
====================================================================
 LIMPIAR PARA ENTREGA — EducaOne
====================================================================
Deja el sistema LIMPIO para entregar a un colegio nuevo.

QUÉ BORRA:
  - Estudiantes y todos sus datos (notas, asistencia, reportes,
    historial académico, casos de psicología, comunicaciones)
  - Cursos (1ro A, 1ro B, etc.)
  - Asignaciones de profesores a cursos
  - Horarios, indicadores de logro, permisos temporales

QUÉ MANTIENE (estructura MINERD estándar + acceso):
  - Grados (1ro a 6to) y sus ciclos
  - Asignaturas MINERD (Lengua, Matemática, etc.)
  - Tandas (Matutina, Vespertina)
  - Usuarios (direccion, profesores, etc.) y sus logins
  - Configuración del colegio (nombre, logo, código, etc.)
  - Año(s) escolar(es)

CÓMO USAR:
  cd backend
  $env:DATABASE_URL = "sqlite:///./educaone.db"
  python limpiar_para_entrega.py

Pide confirmación escribiendo SI antes de borrar. Hace respaldo
automático de la base antes de tocar nada.
====================================================================
"""
import os, sys, shutil
from datetime import datetime

os.environ.setdefault('DATABASE_URL', 'sqlite:///./educaone.db')
os.environ.setdefault('SECRET_KEY', 'dev-secret-cambiar')
os.environ.setdefault('JWT_SECRET_KEY', 'dev-jwt-cambiar')

from database import SessionLocal, engine
import models

# --- Respaldo de la base SQLite antes de tocar nada ---
db_url = os.environ.get('DATABASE_URL', '')
if db_url.startswith('sqlite'):
    ruta = db_url.replace('sqlite:///', '').replace('./', '')
    if os.path.exists(ruta):
        backup = f"{ruta}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(ruta, backup)
        print(f"Respaldo creado: {backup}")

db = SessionLocal()

# Conteo actual
def contar(nombre):
    m = getattr(models, nombre, None)
    if m is None or not hasattr(m, '__table__'):
        return None
    try:
        return db.query(m).count()
    except Exception:
        return None

print("\n" + "="*60)
print(" ESTADO ACTUAL DE LA BASE")
print("="*60)
est = contar('Estudiante')
print(f"  Estudiantes:  {est}")
print(f"  Cursos:       {contar('Curso')}")
print(f"  Grados:       {contar('Grado')}  (se MANTIENEN)")
print(f"  Asignaturas:  {contar('Asignatura')}  (se MANTIENEN)")
print(f"  Usuarios:     {contar('Usuario')}  (se MANTIENEN)")
print("="*60)

print("\nEsto va a BORRAR estudiantes, cursos y todos sus datos.")
print("Va a MANTENER grados, asignaturas, tandas, usuarios y configuración.")
resp = input("\n¿Continuar? Escribí SI (en mayúsculas) para confirmar: ").strip()
if resp != 'SI':
    print("Cancelado. No se borró nada.")
    db.close()
    sys.exit(0)

# Orden de borrado: primero los hijos (dependen de estudiante/curso), luego padres.
# Modelos que dependen de estudiante_id:
dependientes_estudiante = [
    'Asistencia', 'Calificacion', 'CalificacionPrimaria', 'CalificacionSecundaria',
    'CasoPsicologia', 'EvalInternaEstudiante', 'EvaluacionExtraSecundaria',
    'HistorialAcademico', 'HistorialComunicacionPadres', 'HistorialReportePadres',
    'ReporteConducta',
]
# Modelos que dependen de curso_id (sin estudiante):
dependientes_curso = [
    'AsignacionProfesor', 'Horario', 'IndicadorLogro', 'ItemCompletivo',
    'PermisoTemporalCalificacion',
]

borrados = {}
def borrar_todos(nombre):
    m = getattr(models, nombre, None)
    if m is None or not hasattr(m, '__table__'):
        return
    try:
        n = db.query(m).delete()
        borrados[nombre] = n
    except Exception as e:
        print(f"  (aviso: no se pudo borrar {nombre}: {e})")
        db.rollback()

print("\nBorrando...")
# 1. Todo lo que cuelga de estudiante
for nombre in dependientes_estudiante:
    borrar_todos(nombre)
# 2. Estudiantes
borrar_todos('Estudiante')
# 3. Lo que cuelga de curso
for nombre in dependientes_curso:
    borrar_todos(nombre)
# 4. Cursos
borrar_todos('Curso')

db.commit()

print("\n" + "="*60)
print(" LIMPIEZA COMPLETADA")
print("="*60)
for nombre, n in borrados.items():
    if n:
        print(f"  {nombre}: {n} borrados")
print("\nSE MANTUVO:")
print(f"  Grados:       {contar('Grado')}")
print(f"  Asignaturas:  {contar('Asignatura')}")
print(f"  Tandas:       {contar('Tanda')}")
print(f"  Usuarios:     {contar('Usuario')}")
print(f"  Estudiantes:  {contar('Estudiante')}  (debe ser 0)")
print(f"  Cursos:       {contar('Curso')}  (debe ser 0)")
print("="*60)
print("\nEl sistema está listo para entregar. El cliente solo debe:")
print("  1. Crear sus cursos (1ro A, 1ro B, etc.) en el año escolar")
print("  2. Inscribir sus estudiantes")
print("Los grados y asignaturas MINERD ya están cargados.")

db.close()
