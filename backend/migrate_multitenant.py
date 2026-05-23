#!/usr/bin/env python3
"""
EducaOne - Script de Migración Multi-Tenant
============================================
Ejecutar UNA VEZ para migrar una base de datos existente (single-tenant)
al nuevo esquema multi-tenant.

Uso:
    python migrate_multitenant.py

Lo que hace:
1. Crea la tabla 'colegios'
2. Agrega columna 'colegio_id' a todas las tablas existentes
3. Crea el colegio por defecto y asigna todos los datos existentes
4. Crea el usuario superadmin
"""
import os
import sys

# Agregar el directorio actual al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text, inspect
from database import engine, SessionLocal
from models import Base, Colegio, Usuario, ConfiguracionColegio

def migrate():
    db = SessionLocal()
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    print("=" * 60)
    print("  EducaOne - Migración Multi-Tenant")
    print("=" * 60)

    # ──────────────────────────────────────────
    # Paso 1: Crear tabla colegios si no existe
    # ──────────────────────────────────────────
    if 'colegios' not in existing_tables:
        print("\n📦 Paso 1: Creando tabla 'colegios'...")
        Base.metadata.tables['colegios'].create(engine)
        print("   ✅ Tabla 'colegios' creada")
    else:
        print("\n📦 Paso 1: Tabla 'colegios' ya existe ✅")

    # ──────────────────────────────────────────
    # Paso 2: Crear colegio por defecto
    # ──────────────────────────────────────────
    print("\n🏫 Paso 2: Creando colegio por defecto...")
    colegio = db.query(Colegio).filter_by(codigo='default').first()
    if not colegio:
        # Intentar obtener el nombre del colegio desde la configuración existente
        nombre_colegio = 'Mi Colegio'
        try:
            result = db.execute(text("SELECT nombre FROM configuracion_colegio LIMIT 1")).first()
            if result and result[0]:
                nombre_colegio = result[0]
        except:
            pass

        colegio = Colegio(
            nombre=nombre_colegio,
            codigo='default',
            activo=True,
            plan='premium',
            max_estudiantes=9999,
            max_usuarios=999
        )
        db.add(colegio)
        db.commit()
        print(f"   ✅ Colegio '{nombre_colegio}' creado (id={colegio.id})")
    else:
        print(f"   ✅ Colegio '{colegio.nombre}' ya existe (id={colegio.id})")

    colegio_id = colegio.id

    # ──────────────────────────────────────────
    # Paso 3: Agregar colegio_id a todas las tablas
    # ──────────────────────────────────────────
    print("\n🔧 Paso 3: Agregando columna colegio_id a tablas existentes...")

    tables_to_migrate = [
        'configuracion_colegio', 'ano_escolar', 'solicitudes_edicion_nota',
        'usuarios', 'grados', 'tandas', 'recreos', 'bloques_horario',
        'asignaturas', 'cursos', 'estudiantes', 'asignaciones_profesor',
        'horarios', 'calificaciones', 'asistencias', 'reportes_conducta',
        'casos_psicologia', 'mensajes', 'comunicados', 'comunicados_leidos',
        'historial_reportes_padres', 'plantillas_mensaje', 'historial_academico',
        'dias_no_laborables', 'log_accesos', 'log_auditoria',
        'permisos_temporales_calificacion', 'historial_comunicacion_padres',
        'notas_personales', 'evaluaciones_profesor', 'config_eval_interna',
        'eval_interna_estudiante',
    ]

    for table_name in tables_to_migrate:
        if table_name not in existing_tables:
            print(f"   ⏭️  Tabla '{table_name}' no existe, se creará automáticamente")
            continue

        # Verificar si la columna ya existe
        columns = [c['name'] for c in inspector.get_columns(table_name)]
        if 'colegio_id' in columns:
            print(f"   ✅ '{table_name}' ya tiene colegio_id")
            continue

        # Agregar columna
        try:
            db.execute(text(f"ALTER TABLE {table_name} ADD COLUMN colegio_id INTEGER REFERENCES colegios(id)"))
            db.commit()
            print(f"   ✅ '{table_name}' → colegio_id agregado")
        except Exception as e:
            db.rollback()
            print(f"   ⚠️  '{table_name}' → Error: {e}")

    # ──────────────────────────────────────────
    # Paso 4: Asignar todos los datos al colegio por defecto
    # ──────────────────────────────────────────
    print(f"\n📝 Paso 4: Asignando datos existentes al colegio (id={colegio_id})...")

    for table_name in tables_to_migrate:
        if table_name not in existing_tables:
            continue
        try:
            result = db.execute(text(
                f"UPDATE {table_name} SET colegio_id = :cid WHERE colegio_id IS NULL"
            ), {'cid': colegio_id})
            if result.rowcount > 0:
                print(f"   ✅ '{table_name}' → {result.rowcount} registros actualizados")
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"   ⚠️  '{table_name}' → Error: {e}")

    # ──────────────────────────────────────────
    # Paso 5: Crear usuario superadmin
    # ──────────────────────────────────────────
    print("\n👤 Paso 5: Creando usuario superadmin...")
    superadmin = db.query(Usuario).filter_by(username='superadmin').first()
    if not superadmin:
        superadmin = Usuario(
            username='superadmin',
            nombre='Super',
            apellido='Administrador',
            role='superadmin',
            colegio_id=None  # superadmin no pertenece a ningún colegio
        )
        superadmin.set_password('superadmin123')
        db.add(superadmin)
        db.commit()
        print("   ✅ Superadmin creado (username: superadmin, password: superadmin123)")
        print("   ⚠️  CAMBIAR PASSWORD EN PRODUCCIÓN!")
    else:
        print("   ✅ Superadmin ya existe")

    # ──────────────────────────────────────────
    # Paso 6: Crear tablas nuevas que no existan
    # ──────────────────────────────────────────
    print("\n🔨 Paso 6: Creando tablas faltantes...")
    Base.metadata.create_all(bind=engine)
    print("   ✅ Esquema completo verificado")

    # ──────────────────────────────────────────
    # Resumen
    # ──────────────────────────────────────────
    total_usuarios = db.query(Usuario).filter_by(colegio_id=colegio_id).count()
    total_estudiantes = db.execute(text(
        "SELECT COUNT(*) FROM estudiantes WHERE colegio_id = :cid"
    ), {'cid': colegio_id}).scalar() if 'estudiantes' in existing_tables else 0

    print("\n" + "=" * 60)
    print("  ✅ MIGRACIÓN COMPLETADA")
    print("=" * 60)
    print(f"  Colegio: {colegio.nombre} (código: {colegio.codigo})")
    print(f"  Usuarios migrados: {total_usuarios}")
    print(f"  Estudiantes migrados: {total_estudiantes}")
    print(f"  Superadmin: superadmin / superadmin123")
    print("=" * 60)
    print("\n📌 Próximos pasos:")
    print("   1. Cambiar password del superadmin en producción")
    print("   2. Acceder como superadmin para crear nuevos colegios")
    print("   3. Los usuarios existentes ya están asignados al colegio por defecto")
    print()

    db.close()


if __name__ == '__main__':
    migrate()
