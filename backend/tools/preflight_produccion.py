"""EducaOne — preflight de producción (SOLO LECTURA).

Uso recomendado antes de un deploy real:

    cd backend
    python tools/preflight_produccion.py

No modifica datos ni esquema. Devuelve exit code 0 si no encuentra bloqueos
críticos; 2 si detecta una condición que debe corregirse antes de desplegar.
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict
from pathlib import Path

# Permitir ejecutar desde backend/ o desde la raíz del repo.
BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from sqlalchemy import inspect, text  # noqa: E402
from database import engine  # noqa: E402
from models import Base, Usuario  # noqa: E402

CRITICAL = []
WARNINGS = []
OK = []


def critical(msg: str):
    CRITICAL.append(msg)


def warning(msg: str):
    WARNINGS.append(msg)


def ok(msg: str):
    OK.append(msg)


def scalar(conn, sql: str, params=None) -> int:
    return int(conn.execute(text(sql), params or {}).scalar() or 0)


def main() -> int:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    # 1) Configuración de runtime.
    db_url = os.environ.get('DATABASE_URL', '')
    if not db_url:
        critical('DATABASE_URL no está definido. Producción requiere PostgreSQL explícito.')
    elif not db_url.lower().startswith(('postgresql://', 'postgres://', 'postgresql+')):
        critical('DATABASE_URL no apunta a PostgreSQL. Producción real de EducaOne exige PostgreSQL.')
    else:
        ok('DATABASE_URL apunta a PostgreSQL.')

    debug = os.environ.get('DEBUG', 'false').lower() == 'true'
    if debug:
        critical('DEBUG=true en un preflight de producción.')

    default_secret = 'dev-secret-key-change-in-production'
    if os.environ.get('SECRET_KEY', default_secret) == default_secret:
        critical('SECRET_KEY sigue usando el valor de desarrollo.')
    if os.environ.get('JWT_SECRET_KEY', os.environ.get('SECRET_KEY', default_secret)) == default_secret:
        critical('JWT_SECRET_KEY sigue usando el valor de desarrollo.')
    origins = [o.strip().rstrip('/') for o in os.environ.get('ALLOWED_ORIGINS', '*').split(',') if o.strip()]
    if not origins or '*' in origins:
        critical("ALLOWED_ORIGINS debe contener solo orígenes explícitos; '*' no es aceptable en producción.")
    if len(os.environ.get('SECRET_KEY', '')) < 32:
        critical('SECRET_KEY debe tener al menos 32 caracteres en producción.')
    if len(os.environ.get('JWT_SECRET_KEY', os.environ.get('SECRET_KEY', ''))) < 32:
        critical('JWT_SECRET_KEY debe tener al menos 32 caracteres en producción.')

    # 2) Esquema físico vs modelos SQLAlchemy actuales.
    missing = []
    for table_name, table_model in Base.metadata.tables.items():
        if table_name not in tables:
            missing.append(f'tabla:{table_name}')
            continue
        physical_cols = {c['name'] for c in inspector.get_columns(table_name)}
        for col in table_model.columns:
            if col.name not in physical_cols:
                missing.append(f'columna:{table_name}.{col.name}')
    if missing:
        critical('Esquema incompleto respecto a los modelos: ' + ', '.join(missing[:25]))
    else:
        ok('Todas las tablas/columnas de los modelos existen físicamente.')

    if not tables:
        critical('La base no contiene tablas.')
        return render()

    q = engine.dialect.identifier_preparer.quote

    with engine.connect() as conn:
        # 3) Roles/tenancy de usuarios.
        if 'usuarios' in tables:
            bad_roles = scalar(conn, """
                SELECT COUNT(*) FROM usuarios
                WHERE role NOT IN ('superadmin','direccion','coordinador','profesor','psicologia','secretaria')
                   OR role IS NULL
            """)
            if bad_roles:
                critical(f'{bad_roles} usuario(s) tienen rol inválido.')

            tenant_superadmins = scalar(conn, "SELECT COUNT(*) FROM usuarios WHERE role='superadmin' AND colegio_id IS NOT NULL")
            if tenant_superadmins:
                critical(f'{tenant_superadmins} usuario(s) superadmin están ligados a un colegio (escalada potencial).')

            orphan_users = scalar(conn, "SELECT COUNT(*) FROM usuarios WHERE role<>'superadmin' AND colegio_id IS NULL")
            if orphan_users:
                critical(f'{orphan_users} usuario(s) no-superadmin no tienen colegio_id.')

            inactive_school_active_users = scalar(conn, """
                SELECT COUNT(*)
                FROM usuarios u JOIN colegios c ON c.id=u.colegio_id
                WHERE u.activo=TRUE AND c.activo=FALSE
            """)
            if inactive_school_active_users:
                warning(f'{inactive_school_active_users} usuario(s) figuran activos dentro de colegios desactivados; el auth nuevo los bloqueará.')

            # Contraseñas conocidas/default. Solo lectura; no imprime hashes.
            known = ['admin123', 'superadmin123', 'Cambiar123', 'password123', '12345678']
            users = conn.execute(text("SELECT id FROM usuarios WHERE activo=TRUE")).fetchall()
            # Cargar por ORM para reutilizar el verificador de Werkzeug.
            from sqlalchemy.orm import Session
            with Session(engine) as session:
                weak_ids = []
                for row in users:
                    user = session.get(Usuario, row[0])
                    if user and any(user.check_password(pw) for pw in known):
                        weak_ids.append(user.id)
                if weak_ids:
                    critical('Usuarios activos con contraseña conocida/default: IDs ' + ','.join(map(str, weak_ids[:20])))
                else:
                    ok('No se detectaron contraseñas conocidas/default en usuarios activos.')

        # 4) Tenant NULL en entidades académicas que nunca deben ser globales.
        tenant_tables = [
            'estudiantes', 'cursos', 'grados', 'tandas', 'asignaturas',
            'asignaciones_profesor', 'calificaciones', 'calificaciones_primaria',
            'calificaciones_secundaria', 'asistencias', 'casos_psicologia',
            'horarios', 'ano_escolar', 'configuracion_colegio',
        ]
        for t in tenant_tables:
            if t in tables and 'colegio_id' in {c['name'] for c in inspector.get_columns(t)}:
                n = scalar(conn, f'SELECT COUNT(*) FROM {q(t)} WHERE colegio_id IS NULL')
                if n:
                    critical(f'{t}: {n} registro(s) con colegio_id=NULL.')

        # 5) Relaciones cross-tenant genéricas basadas en FKs físicas.
        cross = []
        columns_by_table = {
            t: {c['name'] for c in inspector.get_columns(t)} for t in tables
        }
        for t in tables:
            if 'colegio_id' not in columns_by_table.get(t, set()):
                continue
            for fk in inspector.get_foreign_keys(t):
                target = fk.get('referred_table')
                src_cols = fk.get('constrained_columns') or []
                dst_cols = fk.get('referred_columns') or []
                if not target or target not in tables or 'colegio_id' not in columns_by_table.get(target, set()):
                    continue
                if len(src_cols) != 1 or len(dst_cols) != 1 or src_cols[0] == 'colegio_id':
                    continue
                src, dst = src_cols[0], dst_cols[0]
                sql = f'''SELECT COUNT(*) FROM {q(t)} a JOIN {q(target)} b
                          ON a.{q(src)}=b.{q(dst)}
                          WHERE a.colegio_id IS NOT NULL AND b.colegio_id IS NOT NULL
                            AND a.colegio_id<>b.colegio_id'''
                n = scalar(conn, sql)
                if n:
                    cross.append(f'{t}.{src}->{target}.{dst}: {n}')
        if cross:
            critical('Relaciones cross-tenant detectadas: ' + '; '.join(cross[:20]))
        else:
            ok('No se detectaron relaciones FK cross-tenant.')

        # 6) Duplicados críticos.
        if 'estudiantes' in tables:
            dmat = scalar(conn, """
                SELECT COUNT(*) FROM (
                    SELECT colegio_id, LOWER(TRIM(matricula)), COUNT(*) c
                    FROM estudiantes
                    WHERE matricula IS NOT NULL AND TRIM(matricula)<>''
                    GROUP BY colegio_id, LOWER(TRIM(matricula)) HAVING COUNT(*)>1
                ) x
            """)
            dlist = scalar(conn, """
                SELECT COUNT(*) FROM (
                    SELECT colegio_id, curso_id, no_lista, COUNT(*) c
                    FROM estudiantes
                    WHERE curso_id IS NOT NULL AND no_lista IS NOT NULL AND activo=TRUE
                    GROUP BY colegio_id, curso_id, no_lista HAVING COUNT(*)>1
                ) x
            """)
            if dmat: critical(f'{dmat} grupo(s) de matrícula duplicada por colegio.')
            else: ok('Matrículas sin duplicados por colegio.')
            if dlist: critical(f'{dlist} número(s) de lista duplicados dentro de curso.')
            else: ok('Números de lista activos sin duplicados dentro de curso.')

        if 'ano_escolar' in tables:
            dyear = scalar(conn, """
                SELECT COUNT(*) FROM (
                    SELECT colegio_id, COUNT(*) c FROM ano_escolar
                    WHERE activo=TRUE AND colegio_id IS NOT NULL
                    GROUP BY colegio_id HAVING COUNT(*)>1
                ) x
            """)
            if dyear: critical(f'{dyear} colegio(s) tienen más de un año escolar activo.')
            else: ok('Máximo un año escolar activo por colegio.')

        if 'asistencias' in tables:
            datt = scalar(conn, """
                SELECT COUNT(*) FROM (
                    SELECT estudiante_id, fecha, COUNT(*) c FROM asistencias
                    WHERE asignatura_id IS NULL
                    GROUP BY estudiante_id, fecha HAVING COUNT(*)>1
                ) x
            """)
            if datt: critical(f'{datt} grupo(s) de asistencia general duplicada estudiante/fecha.')
            else: ok('Asistencia general sin duplicados estudiante/fecha.')

        if 'eval_interna_estudiante' in tables:
            # v2.19: la identidad institucional de una evaluación interna es
            # estudiante + curso + asignatura + período. Antes del arreglo, un
            # cambio de profesor a mitad de período creaba una fila paralela y
            # el estudiante quedaba con dos notas internas para el mismo período.
            # SOLO LECTURA: se reporta y se BLOQUEA el deploy. No se borra ni se
            # fusiona nada automáticamente — cuál de las dos filas es la buena
            # lo decide el colegio, no un script.
            dev = scalar(conn, """
                SELECT COUNT(*) FROM (
                    SELECT colegio_id, estudiante_id, curso_id, asignatura_id, periodo,
                           COUNT(*) c
                    FROM eval_interna_estudiante
                    WHERE curso_id IS NOT NULL AND asignatura_id IS NOT NULL
                    GROUP BY colegio_id, estudiante_id, curso_id, asignatura_id, periodo
                    HAVING COUNT(*)>1
                ) x
            """)
            if dev:
                critical(
                    f'{dev} grupo(s) de evaluación interna duplicada '
                    f'(estudiante+curso+asignatura+período). Revíselos y decida cuál conservar '
                    f'ANTES de desplegar: el índice único uq_eval_interna_identidad no se podrá crear.'
                )
            else:
                ok('Evaluación interna sin duplicados estudiante/curso/asignatura/período.')

        if 'grados' in tables:
            invalid_levels = scalar(conn, """
                SELECT COUNT(*) FROM grados
                WHERE nivel IS NULL OR TRIM(nivel)=''
                   OR LOWER(nivel) NOT IN ('primaria','secundaria','inicial')
            """)
            if invalid_levels: critical(f'{invalid_levels} grado(s) tienen nivel no canónico.')
            else: ok('Niveles de grados canónicos.')

    return render()


def render() -> int:
    print('\n=== EducaOne · Preflight de producción (solo lectura) ===')
    for msg in OK:
        print(f'[OK] {msg}')
    for msg in WARNINGS:
        print(f'[WARN] {msg}')
    for msg in CRITICAL:
        print(f'[BLOQUEO] {msg}')
    print(f'\nResumen: {len(OK)} OK · {len(WARNINGS)} warning(s) · {len(CRITICAL)} bloqueo(s)')
    if CRITICAL:
        print('RESULTADO: NO DESPLEGAR hasta corregir los bloqueos.')
        return 2
    print('RESULTADO: preflight sin bloqueos críticos.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
