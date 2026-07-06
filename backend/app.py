"""
Educa One - Sistema de Gestión Escolar
API Backend FastAPI
================================
Versión: 2.0 (Producción) - Migrado de Flask a FastAPI
Incluye: JWT, Rate Limiting, Auditoría, Validaciones
"""
from fastapi import FastAPI, Request, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import JSONResponse, StreamingResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from datetime import datetime, date, timedelta, timezone

# Zona horaria República Dominicana (AST = UTC-4)
TZ_RD = timezone(timedelta(hours=-4))

def now_rd():
    """Retorna datetime actual en zona horaria RD."""
    return datetime.now(TZ_RD)

def today_rd():
    """Retorna date actual en zona horaria RD."""
    return datetime.now(TZ_RD).date()
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy import func, extract, or_, and_
import os
import re
import jwt
try:
    from reportlab.lib import colors
except ImportError:
    colors = None
import logging
import io
import csv
import base64
import random
from io import BytesIO
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv
load_dotenv()

from database import engine, SessionLocal, get_db, Base
from models import (
    Colegio, ConfiguracionColegio, AnoEscolar, Grado, Tanda, Recreo,
    Asignatura, Curso, Estudiante, AsignacionProfesor, Horario, Calificacion,
    Asistencia, ReporteConducta, CasoPsicologia, Mensaje, Comunicado,
    PlantillaMensaje, HistorialAcademico, LogAcceso, LogAuditoria,
    SolicitudEdicionNota, BloqueHorario, DiaNoLaborable, Usuario,
    NotaPersonal, EvaluacionProfesor, ConfigEvalInterna, EvalInternaEstudiante,
    PermisoTemporalCalificacion, ComunicadoLeido, HistorialReportePadres,
    HistorialComunicacionPadres, IndicadorLogro, ItemCompletivo, Notificacion,
    AreaCurricular, CalificacionPrimaria, CalificacionSecundaria, EvaluacionExtraSecundaria, init_db
)
from auth import (
    get_current_user, get_current_user_optional, RolesRequired,
    create_token, check_rate_limit, register_attempt, get_client_ip,
    JWT_SECRET_KEY, tenant_filter, set_tenant, current_user_ctx,
    get_tenant_or_404, assert_same_tenant,
)
from services import (
    get_graficos, get_stats_cursos, get_calificaciones_periodo,
    generar_tarjetas_pdf, cache_clear_tenant
)

# ===========================================
# CONFIGURACIÓN
# ===========================================
SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
DEBUG = os.environ.get('DEBUG', 'True' if os.environ.get('ENVIRONMENT', 'development') == 'development' else 'False').lower() == 'true'


# ===========================================
# OBSERVABILIDAD (Sentry — opcional)
# ===========================================
# Si SENTRY_DSN está configurado, los errores 5xx se envían a Sentry para
# alertarnos cuando algo se rompe en producción. Free tier (5k errores/mes)
# alcanza para piloto con 5-20 colegios. En desarrollo NO se inicializa.
SENTRY_DSN = os.environ.get('SENTRY_DSN', '').strip()
if SENTRY_DSN and not DEBUG:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        sentry_sdk.init(
            dsn=SENTRY_DSN,
            integrations=[FastApiIntegration(), SqlalchemyIntegration()],
            traces_sample_rate=0.0,  # desactivado por costo; subir a 0.1 para profiling
            send_default_pii=False,  # no enviar IPs ni cookies por privacidad
            environment=os.environ.get('ENVIRONMENT', 'production'),
        )
        logging.getLogger('educaone.startup').info('Sentry inicializado')
    except ImportError:
        logging.getLogger('educaone.startup').warning(
            'SENTRY_DSN configurado pero sentry-sdk no está instalado. '
            'Agregalo con: pip install sentry-sdk[fastapi]'
        )


def _validar_config_produccion():
    """
    Valida la configuración crítica al arrancar.
    
    En producción (DEBUG=False), exige:
    - SECRET_KEY distinto al default.
    - JWT_SECRET_KEY distinto al default (si se configura por separado).
    - ALLOWED_ORIGINS NO sea '*'.
    
    Si algo falla, levanta RuntimeError con instrucciones claras para
    el operador. El sistema NO arranca en estado inseguro.
    
    En desarrollo (DEBUG=True), solo emite warnings.
    """
    log = logging.getLogger("educaone.startup")
    
    DEFAULT_SECRET = 'dev-secret-key-change-in-production'
    
    errores = []
    
    if SECRET_KEY == DEFAULT_SECRET:
        errores.append(
            "SECRET_KEY no está configurada (usando el default de desarrollo). "
            "En Render: Settings → Environment → Add SECRET_KEY con un string "
            "aleatorio largo (ej: `python -c \"import secrets; print(secrets.token_urlsafe(64))\"`)."
        )
    
    jwt_sk = os.environ.get('JWT_SECRET_KEY', SECRET_KEY)
    if jwt_sk == DEFAULT_SECRET:
        errores.append(
            "JWT_SECRET_KEY no está configurada (usando el default de desarrollo). "
            "Idealmente distinto a SECRET_KEY. Generá uno con `python -c "
            "\"import secrets; print(secrets.token_urlsafe(64))\"` y agregalo "
            "como variable de entorno."
        )
    
    allowed = os.environ.get('ALLOWED_ORIGINS', '*')
    if allowed.strip() == '*':
        errores.append(
            "ALLOWED_ORIGINS='*' permite que cualquier sitio web haga requests "
            "a la API desde el browser de tus usuarios. En Render configurá "
            "ALLOWED_ORIGINS con la lista de dominios reales separados por coma "
            "(ej: 'https://educaone1.onrender.com,https://miColegio.educaone.com')."
        )
    
    if errores:
        if DEBUG:
            log.warning("⚠️  Configuración insegura detectada (DEBUG=True, no se bloquea):")
            for e in errores:
                log.warning(f"   - {e}")
        else:
            mensaje = (
                "═══════════════════════════════════════════════════════════════\n"
                "  ❌ EducaOne se rehúsa a arrancar en producción con esta config\n"
                "═══════════════════════════════════════════════════════════════\n"
                "\n"
                + "\n\n".join(f"• {e}" for e in errores)
                + "\n\n"
                "Si estás en desarrollo local, exportá DEBUG=true (no recomendado\n"
                "fuera de localhost). En producción configurá las variables de\n"
                "entorno indicadas arriba.\n"
                "═══════════════════════════════════════════════════════════════\n"
            )
            raise RuntimeError(mensaje)


_validar_config_produccion()

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app):
    # Startup: crear tablas si no existen (incluye nuevas de primaria)
    Base.metadata.create_all(bind=engine)
    
    # Migración automática: agregar columnas nuevas si no existen
    try:
        from sqlalchemy import text, inspect
        inspector = inspect(engine)
        
        # === 1. Calificaciones secundaria: 16 campos rp*_p* ===
        if 'calificaciones' in inspector.get_table_names():
            existing_cols = {c['name'] for c in inspector.get_columns('calificaciones')}
            nuevas_cols_calif = []
            for periodo in range(1, 5):
                for parcial in range(1, 5):
                    col = f'rp{periodo}_p{parcial}'
                    if col not in existing_cols:
                        nuevas_cols_calif.append(col)
            if nuevas_cols_calif:
                with engine.connect() as conn:
                    for col in nuevas_cols_calif:
                        try:
                            conn.execute(text(f'ALTER TABLE calificaciones ADD COLUMN {col} FLOAT'))
                            conn.commit()
                        except Exception as e:
                            logger.warning(f"No se pudo agregar {col}: {e}")
                logger.info(f"✅ Migración: agregadas {len(nuevas_cols_calif)} columnas RP por parcial")
        
        # === 2. Grado: agregar campo ciclo ===
        if 'grados' in inspector.get_table_names():
            grado_cols = {c['name'] for c in inspector.get_columns('grados')}
            if 'ciclo' not in grado_cols:
                with engine.connect() as conn:
                    try:
                        conn.execute(text('ALTER TABLE grados ADD COLUMN ciclo VARCHAR(20)'))
                        conn.commit()
                        logger.info("✅ Migración: agregado campo ciclo a grados")
                    except Exception as e:
                        logger.warning(f"No se pudo agregar ciclo: {e}")
        
        # === 3. ConfiguracionColegio: módulos de niveles ===
        if 'configuracion_colegio' in inspector.get_table_names():
            config_cols = {c['name'] for c in inspector.get_columns('configuracion_colegio')}
            nuevas_config = []
            if 'modulo_secundaria' not in config_cols:
                nuevas_config.append(('modulo_secundaria', 'BOOLEAN DEFAULT TRUE'))
            if 'modulo_primaria' not in config_cols:
                nuevas_config.append(('modulo_primaria', 'BOOLEAN DEFAULT FALSE'))
            if 'modulo_inicial' not in config_cols:
                nuevas_config.append(('modulo_inicial', 'BOOLEAN DEFAULT FALSE'))
            if nuevas_config:
                with engine.connect() as conn:
                    for col_name, col_def in nuevas_config:
                        try:
                            conn.execute(text(f'ALTER TABLE configuracion_colegio ADD COLUMN {col_name} {col_def}'))
                            conn.commit()
                        except Exception as e:
                            logger.warning(f"No se pudo agregar {col_name}: {e}")
                logger.info(f"✅ Migración: agregados {len(nuevas_config)} módulos de nivel")
        
        # === 4. Normalizar nivel de grados a valores canónicos ('primaria'|'secundaria'|'inicial') ===
        if 'grados' in inspector.get_table_names():
            with engine.connect() as conn:
                try:
                    r1 = conn.execute(text("UPDATE grados SET nivel='secundaria' WHERE nivel IS NULL OR nivel=''"))
                    r2 = conn.execute(text("UPDATE grados SET nivel='secundaria' WHERE LOWER(nivel) LIKE 'sec%'"))
                    r3 = conn.execute(text("UPDATE grados SET nivel='primaria' WHERE LOWER(nivel) LIKE 'prim%'"))
                    r4 = conn.execute(text("UPDATE grados SET nivel='inicial' WHERE LOWER(nivel) LIKE 'ini%' OR LOWER(nivel) LIKE 'prees%' OR LOWER(nivel) LIKE 'pre-%'"))
                    conn.commit()
                    total = r1.rowcount + r2.rowcount + r3.rowcount + r4.rowcount
                    if total > 0:
                        logger.info(f"✅ Migración: {total} grados normalizados (nivel canónico)")
                except Exception as e:
                    logger.warning(f"No se pudo normalizar nivel: {e}")
        
        # === 5. Agregar columna dias_trabajados si falta ===
        if 'ano_escolar' in inspector.get_table_names():
            cols = [c['name'] for c in inspector.get_columns('ano_escolar')]
            if 'dias_trabajados' not in cols:
                with engine.connect() as conn:
                    try:
                        conn.execute(text("ALTER TABLE ano_escolar ADD COLUMN dias_trabajados TEXT DEFAULT '{}'"))
                        conn.commit()
                        logger.info("✅ Migración: columna dias_trabajados agregada a ano_escolar")
                    except Exception as e:
                        logger.warning(f"No se pudo agregar dias_trabajados: {e}")
        
        # === 6. Agregar must_change_password a usuarios (Sprint 1 seguridad) ===
        if 'usuarios' in inspector.get_table_names():
            user_cols = {c['name'] for c in inspector.get_columns('usuarios')}
            if 'must_change_password' not in user_cols:
                # Sintaxis compatible con SQLite y Postgres:
                # SQLite acepta tanto "DEFAULT 0" como "DEFAULT FALSE" para BOOLEAN.
                # Postgres exige FALSE/TRUE (o 'f'/'t'). Usamos FALSE que es estándar SQL.
                with engine.connect() as conn:
                    try:
                        conn.execute(text(
                            "ALTER TABLE usuarios ADD COLUMN must_change_password "
                            "BOOLEAN NOT NULL DEFAULT FALSE"
                        ))
                        conn.commit()
                        logger.info("✅ Migración: must_change_password agregada a usuarios")
                    except Exception as e:
                        logger.warning(f"No se pudo agregar must_change_password: {e}")
            
            # token_version (Sprint 4: logout real)
            if 'token_version' not in user_cols:
                with engine.connect() as conn:
                    try:
                        conn.execute(text(
                            "ALTER TABLE usuarios ADD COLUMN token_version "
                            "INTEGER NOT NULL DEFAULT 0"
                        ))
                        conn.commit()
                        logger.info("✅ Migración: token_version agregada a usuarios")
                    except Exception as e:
                        logger.warning(f"No se pudo agregar token_version: {e}")
        
        # === Migración Plan + Uso (módulos del SaaS) ===
        # Agrega columnas plan_X a colegios y usa_X a configuracion_colegio.
        # Si existían las columnas legacy (tiene_primaria/tiene_secundaria,
        # modulo_X), copia sus valores a las nuevas para no perder configuración.
        # Las columnas legacy NO se borran: quedan obsoletas pero leíbles, para
        # que un rollback rápido sea posible.
        if 'colegios' in inspector.get_table_names():
            cole_cols = {c['name'] for c in inspector.get_columns('colegios')}
            
            # Columnas plan_X con sus defaults canónicos
            plan_cols = [
                ('plan_secundaria',       'TRUE'),
                ('plan_primaria',         'TRUE'),
                ('plan_inicial',          'FALSE'),
                ('plan_whatsapp',         'FALSE'),
                ('plan_psicologia',       'FALSE'),
                ('plan_eval_profesores',  'TRUE'),
                ('plan_eval_interna',     'FALSE'),
                ('plan_comunicacion_padres', 'TRUE'),
                ('plan_registro_escolar', 'TRUE'),
                ('plan_reportes_conducta','TRUE'),
            ]
            with engine.connect() as conn:
                for col, default in plan_cols:
                    if col not in cole_cols:
                        try:
                            conn.execute(text(
                                f"ALTER TABLE colegios ADD COLUMN {col} "
                                f"BOOLEAN NOT NULL DEFAULT {default}"
                            ))
                            conn.commit()
                            logger.info(f"✅ Migración: {col} agregada a colegios")
                        except Exception as e:
                            logger.warning(f"No se pudo agregar {col}: {e}")
                
                # Si las columnas legacy tiene_primaria/tiene_secundaria existían,
                # copiar sus valores a plan_primaria/plan_secundaria. Esto preserva
                # la configuración que el director tenía antes.
                if 'tiene_primaria' in cole_cols:
                    try:
                        conn.execute(text(
                            "UPDATE colegios SET plan_primaria = tiene_primaria "
                            "WHERE tiene_primaria IS NOT NULL"
                        ))
                        conn.commit()
                        logger.info("✅ Migración: plan_primaria copiada desde tiene_primaria legacy")
                    except Exception as e:
                        logger.warning(f"No se pudo copiar tiene_primaria: {e}")
                if 'tiene_secundaria' in cole_cols:
                    try:
                        conn.execute(text(
                            "UPDATE colegios SET plan_secundaria = tiene_secundaria "
                            "WHERE tiene_secundaria IS NOT NULL"
                        ))
                        conn.commit()
                        logger.info("✅ Migración: plan_secundaria copiada desde tiene_secundaria legacy")
                    except Exception as e:
                        logger.warning(f"No se pudo copiar tiene_secundaria: {e}")
        
        if 'configuracion_colegio' in inspector.get_table_names():
            cfg_cols = {c['name'] for c in inspector.get_columns('configuracion_colegio')}
            
            usa_cols = [
                # Niveles: TRUE por default (si el plan los incluye, se usan)
                ('usa_secundaria',         'TRUE'),
                ('usa_primaria',           'TRUE'),
                ('usa_inicial',            'FALSE'),
                # Módulos funcionales: FALSE por default (el director decide
                # encender). Esto evita que un colegio recién creado tenga
                # módulos "activos" sin intervención del usuario.
                ('usa_whatsapp',           'FALSE'),
                ('usa_psicologia',         'FALSE'),
                ('usa_eval_profesores',    'FALSE'),
                ('usa_eval_interna',       'FALSE'),
                ('usa_comunicacion_padres','FALSE'),
                ('usa_registro_escolar',   'FALSE'),
                ('usa_reportes_conducta',  'FALSE'),
            ]
            with engine.connect() as conn:
                for col, default in usa_cols:
                    if col not in cfg_cols:
                        try:
                            conn.execute(text(
                                f"ALTER TABLE configuracion_colegio ADD COLUMN {col} "
                                f"BOOLEAN NOT NULL DEFAULT {default}"
                            ))
                            conn.commit()
                            logger.info(f"✅ Migración: {col} agregada a configuracion_colegio")
                        except Exception as e:
                            logger.warning(f"No se pudo agregar {col}: {e}")
                
                # Copiar valores legacy modulo_X → usa_X cuando existan
                legacy_to_new = [
                    ('modulo_whatsapp',          'usa_whatsapp'),
                    ('modulo_psicologia',        'usa_psicologia'),
                    ('modulo_comunicacion_padres','usa_comunicacion_padres'),
                    ('modulo_eval_profesores',   'usa_eval_profesores'),
                    ('modulo_eval_interna',      'usa_eval_interna'),
                    ('modulo_registro_escolar',  'usa_registro_escolar'),
                    ('modulo_secundaria',        'usa_secundaria'),
                    ('modulo_primaria',          'usa_primaria'),
                    ('modulo_inicial',           'usa_inicial'),
                ]
                for old, new in legacy_to_new:
                    if old in cfg_cols:
                        try:
                            conn.execute(text(
                                f"UPDATE configuracion_colegio SET {new} = {old} "
                                f"WHERE {old} IS NOT NULL"
                            ))
                            conn.commit()
                        except Exception as e:
                            logger.warning(f"No se pudo copiar {old} → {new}: {e}")
        
        # === 7. Crear índices compuestos faltantes (idempotente, IF NOT EXISTS) ===
        # Compatible con SQLite (3.8.0+) y Postgres (9.5+).
        # Acelera queries frecuentes:
        #   - Asistencia por estudiante en rango de fechas
        #   - Asistencia por curso en una fecha
        #   - Calificaciones por (estudiante, asignatura)
        #   - Horarios por profesor/curso ordenados por día
        indices_compuestos = [
            ('ix_asistencia_est_fecha', 'asistencias', '(estudiante_id, fecha)'),
            ('ix_asistencia_curso_fecha', 'asistencias', '(curso_id, fecha)'),
            ('ix_asistencia_colegio_fecha', 'asistencias', '(colegio_id, fecha)'),
            ('ix_calificacion_est_asig', 'calificaciones', '(estudiante_id, asignatura_id)'),
            ('ix_calificacion_colegio_asig', 'calificaciones', '(colegio_id, asignatura_id)'),
            ('ix_horario_profesor_dia', 'horarios', '(profesor_id, dia)'),
            ('ix_horario_curso_dia', 'horarios', '(curso_id, dia)'),
        ]
        with engine.connect() as conn:
            for nombre, tabla, cols in indices_compuestos:
                try:
                    conn.execute(text(f"CREATE INDEX IF NOT EXISTS {nombre} ON {tabla} {cols}"))
                except Exception as e:
                    logger.warning(f"No se pudo crear índice {nombre}: {e}")
            conn.commit()
        
    except Exception as e:
        logger.warning(f"Error en migración: {e}")
    
    init_db()
    
    # Iniciar backup automático programado
    import asyncio
    async def backup_scheduler():
        """Ejecuta backup automático cada 24 horas a las 2:00 AM RD"""
        while True:
            try:
                ahora = now_rd()
                # Calcular segundos hasta las 2:00 AM
                target = ahora.replace(hour=2, minute=0, second=0, microsecond=0)
                if ahora.hour >= 2:
                    target += timedelta(days=1)
                wait_seconds = (target - ahora).total_seconds()
                logger.info(f"Backup programado para {target.strftime('%Y-%m-%d %H:%M')} ({int(wait_seconds/3600)}h)")
                await asyncio.sleep(wait_seconds)
                
                # Ejecutar backup
                import subprocess
                database_url = os.environ.get('DATABASE_URL', '')
                if database_url and 'postgresql' in database_url:
                    backup_dir = os.path.join(os.path.dirname(__file__), 'backups')
                    os.makedirs(backup_dir, exist_ok=True)
                    filename = f'backup_auto_{now_rd().strftime("%Y%m%d_%H%M%S")}.sql'
                    filepath = os.path.join(backup_dir, filename)
                    result = subprocess.run(
                        ['pg_dump', database_url, '-f', filepath, '--no-owner', '--no-acl'],
                        capture_output=True, text=True, timeout=120
                    )
                    if result.returncode == 0:
                        size_mb = round(os.path.getsize(filepath) / 1024 / 1024, 2)
                        logger.info(f"✅ Backup automático: {filename} ({size_mb}MB)")
                        # Limpiar backups auto antiguos (mantener últimos 30)
                        all_backups = sorted([f for f in os.listdir(backup_dir) if f.startswith('backup_')], reverse=True)
                        for old in all_backups[30:]:
                            os.remove(os.path.join(backup_dir, old))
                    else:
                        logger.error(f"❌ Backup automático falló: {result.stderr[:200]}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error en backup scheduler: {e}")
                await asyncio.sleep(3600)  # Reintentar en 1 hora
    
    # v2.13.31: backup_scheduler DESACTIVADO a propósito.
    # Los backups que generaba se guardaban en el disco del servidor, que en
    # Render es EFÍMERO (se borra en cada redeploy/reinicio) → daba falsa
    # sensación de seguridad. La estrategia correcta de backups es:
    #   1. Backups automáticos de Render PostgreSQL (plan de pago) — confiables
    #   2. Opcional: Cron Job de Render con backup_datos.py subiendo a Drive/S3
    # Para reactivarlo (solo si guarda en almacenamiento externo persistente),
    # descomentá la línea de abajo.
    # task = asyncio.create_task(backup_scheduler())
    yield
    # Shutdown
    # task.cancel()  # desactivado junto con el scheduler

app = FastAPI(title="Educa One API", version="2.0", lifespan=lifespan)

# CORS — configurable por variable de entorno
ALLOWED_ORIGINS = os.environ.get('ALLOWED_ORIGINS', '*').split(',')
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===========================================
# CACHE EN MEMORIA (TTL-based)
# ===========================================
import time as _time

# ===========================================
# PAGINACIÓN (v2.13.30) — para escalar a 100 escuelas
# ===========================================
def paginar_query(query, request, default_per_page=50, max_per_page=200):
    """Paginación opcional y RETROCOMPATIBLE.

    - Si NO viene 'page' en el query string → devuelve None (el caller
      sigue con .all() como siempre; no rompe nada existente).
    - Si viene 'page' → devuelve un dict con items, total, page, per_page,
      total_pages. per_page se limita a max_per_page para proteger memoria.

    Uso:
        pag = paginar_query(query, request)
        if pag is None:
            items = query.all()            # comportamiento clásico
            return [x.to_dict() for x in items]
        return {
            **pag, 'items': [x.to_dict() for x in pag['items']]
        }
    """
    page_raw = request.query_params.get('page')
    if page_raw is None:
        return None
    try:
        page = max(1, int(page_raw))
    except (ValueError, TypeError):
        page = 1
    try:
        per_page = int(request.query_params.get('per_page', default_per_page))
    except (ValueError, TypeError):
        per_page = default_per_page
    per_page = max(1, min(per_page, max_per_page))

    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = (total + per_page - 1) // per_page
    return {
        'items': items,
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': total_pages,
    }


_cache = {}

# ===========================================
# CACHÉ: Redis si está disponible, sino memoria (v2.13.30)
# ===========================================
# Con múltiples workers, la caché en memoria NO se comparte (cada worker
# tiene la suya → posibles inconsistencias). Si configurás REDIS_URL en
# el entorno, la caché usa Redis (compartida entre todos los workers).
# Sin REDIS_URL, cae a memoria local (suficiente para pocos colegios).
_redis_client = None
_REDIS_URL = os.environ.get('REDIS_URL', '').strip()
if _REDIS_URL:
    try:
        import redis as _redis_lib
        _redis_client = _redis_lib.from_url(_REDIS_URL, decode_responses=True, socket_timeout=2)
        _redis_client.ping()
        logging.getLogger('educaone.startup').info('Caché Redis conectada')
    except Exception as _e:
        logging.getLogger('educaone.startup').warning(
            f'REDIS_URL configurado pero no se pudo conectar ({_e}); usando caché en memoria.')
        _redis_client = None

import json as _cache_json

def cache_get(key: str):
    """Obtener valor del cache (Redis o memoria) si no ha expirado."""
    if _redis_client is not None:
        try:
            val = _redis_client.get(key)
            return _cache_json.loads(val) if val is not None else None
        except Exception:
            pass  # si Redis falla, caer a memoria
    if key in _cache:
        val, exp = _cache[key]
        if _time.time() < exp:
            return val
        del _cache[key]
    return None

def cache_set(key: str, value, ttl: int = 60):
    """Guardar valor en cache (Redis o memoria) con TTL en segundos."""
    if _redis_client is not None:
        try:
            _redis_client.setex(key, ttl, _cache_json.dumps(value))
            return
        except Exception:
            pass
    _cache[key] = (value, _time.time() + ttl)

def cache_clear(prefix: str = ''):
    """Limpiar cache por prefijo o todo (Redis o memoria)."""
    if _redis_client is not None:
        try:
            if not prefix:
                _redis_client.flushdb()
            else:
                for k in _redis_client.scan_iter(match=f'{prefix}*'):
                    _redis_client.delete(k)
            return
        except Exception:
            pass
    if not prefix:
        _cache.clear()
    else:
        keys = [k for k in _cache if k.startswith(prefix)]
        for k in keys:
            del _cache[k]

# Error handler global — evita mostrar tracebacks en producción
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger_err = logging.getLogger("educaone.error")
    logger_err.error(f"{request.method} {request.url.path}: {exc}", exc_info=True)
    if DEBUG:
        return JSONResponse({'error': str(exc), 'type': type(exc).__name__}, status_code=500)
    return JSONResponse({'error': 'Error interno del servidor'}, status_code=500)


# Handler específico para JSON malformado / body inválido.
# Sin este handler, un POST con body vacío o JSON corrupto devuelve 500,
# que es engañoso (es culpa del cliente, no del servidor). Con esto se
# devuelve 400 con mensaje útil.
import json as _json
@app.exception_handler(_json.JSONDecodeError)
async def json_decode_error_handler(request: Request, exc):
    return JSONResponse(
        {'error': 'Body JSON inválido o malformado. Verificá la estructura del request.'},
        status_code=400
    )


# Handler para errores de validación de FastAPI (campos faltantes, tipos
# incorrectos en query params, etc.). Sin esto, FastAPI devuelve 422 con
# estructura compleja que el frontend no siempre maneja bien.
from fastapi.exceptions import RequestValidationError
@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    # Extraer primer error legible
    errores = exc.errors()
    if errores:
        e = errores[0]
        campo = '.'.join(str(x) for x in e.get('loc', [])[1:]) or 'campo'
        msg = e.get('msg', 'inválido')
        return JSONResponse(
            {'error': f'Validación falló en {campo}: {msg}', 'detalles': errores},
            status_code=400
        )
    return JSONResponse({'error': 'Datos inválidos en el request'}, status_code=400)

# ===========================================
# LOGGING
# ===========================================
logger = logging.getLogger("educaone")
if not DEBUG:
    log_dir = os.environ.get('LOG_DIR', 'logs')
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, 'sge.log'), maxBytes=10240000, backupCount=10
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.setLevel(logging.INFO)
    logger.info('Educa One Backend iniciado (FastAPI)')

# ===========================================
# MIDDLEWARE DE SEGURIDAD
# ===========================================
# ===========================================
# RATE LIMITING GLOBAL (v2.13.30) — protege toda la API
# ===========================================
# Ventana deslizante en memoria por IP. Límite GENEROSO para no molestar
# el uso normal (un usuario activo hace ~20-40 req/min), pero frena abusos
# o bugs de cliente que disparen miles de requests.
# NOTA: con múltiples workers, cada worker tiene su propio contador. Con
# Redis (REDIS_URL configurado) esto sería compartido; por ahora en memoria
# es suficiente como red de seguridad básica.
from collections import deque as _deque
_rate_global = {}  # ip -> deque de timestamps
_RATE_MAX = 200    # requests
_RATE_WINDOW = 60  # segundos

@app.middleware("http")
async def global_rate_limit(request: Request, call_next):
    # No limitar el healthcheck (Render lo llama seguido)
    if request.url.path in ('/api/health', '/health', '/'):
        return await call_next(request)
    try:
        ip = request.client.host if request.client else 'unknown'
    except Exception:
        ip = 'unknown'
    ahora = _time.time()
    dq = _rate_global.get(ip)
    if dq is None:
        dq = _deque()
        _rate_global[ip] = dq
    # Quitar timestamps fuera de la ventana
    while dq and dq[0] < ahora - _RATE_WINDOW:
        dq.popleft()
    if len(dq) >= _RATE_MAX:
        from fastapi.responses import JSONResponse as _JR
        return _JR(
            {'error': 'Demasiadas solicitudes. Esperá un momento e intentá de nuevo.'},
            status_code=429,
            headers={'Retry-After': '30'}
        )
    dq.append(ahora)
    # Limpieza periódica para no acumular IPs viejas (cada ~1000 IPs)
    if len(_rate_global) > 5000:
        viejos = [k for k, d in _rate_global.items() if not d or d[-1] < ahora - _RATE_WINDOW]
        for k in viejos:
            _rate_global.pop(k, None)
    return await call_next(request)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """
    Middleware que agrega headers de seguridad HTTP a TODAS las respuestas.

    Headers aplicados:
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - X-XSS-Protection: 1; mode=block
    - Referrer-Policy: strict-origin-when-cross-origin
    - Content-Security-Policy
    - Strict-Transport-Security (solo prod)
    - Permissions-Policy
    """
    # v2.13.31: AUDITORÍA AUTOMÁTICA de escrituras (capa de cobertura total).
    # Registra toda operación POST/PUT/DELETE/PATCH exitosa, sin tener que
    # tocar cada endpoint. El detalle fino (antes/después) lo agregan los
    # endpoints críticos con log_auditoria(). Esta capa garantiza que NINGUNA
    # escritura quede sin rastro de quién/cuándo/desde qué IP.
    _audit_metodo = request.method
    _audit_path = request.url.path
    _audit_debe = (_audit_metodo in ('POST', 'PUT', 'DELETE', 'PATCH')
                   and _audit_path.startswith('/api/')
                   and not _audit_path.startswith('/api/auth/'))  # login se audita aparte

    response = await call_next(request)

    if _audit_debe and 200 <= response.status_code < 400:
        try:
            _auditar_escritura_automatica(request, _audit_metodo, _audit_path, response.status_code)
        except Exception as _e:
            # La auditoría NUNCA debe romper la respuesta al usuario
            logging.getLogger('educaone.audit').warning(f'auditoría automática falló: {_e}')

    try:
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        # Permissions-Policy: bloquear acceso a APIs sensibles del browser
        # que el sistema no necesita.
        response.headers['Permissions-Policy'] = (
            'camera=(), microphone=(), geolocation=(), '
            'payment=(), usb=(), accelerometer=(), gyroscope=()'
        )
        # CSP: en este sistema el frontend (React) hace fetch al mismo origen
        # de la API. Permitimos: self para todo, data: para imágenes (PDFs/avatares),
        # 'unsafe-inline' en estilos para Tailwind/inline styles del bundle.
        # En producción se podría endurecer más con nonces.
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "img-src 'self' data: blob: https:; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; "
            "connect-src 'self' https:; "
            "font-src 'self' data:; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        if not DEBUG:
            # Solo en producción: HSTS (fuerza HTTPS por 1 año)
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
        return response
    except Exception as e:
        import traceback
        logger_err = logging.getLogger("educaone.error")
        logger_err.error(f"{request.method} {request.url.path}: {e}\n{traceback.format_exc()}")
        from fastapi.responses import JSONResponse as JR
        resp = JR({'error': str(e) if DEBUG else 'Error interno del servidor'}, status_code=500)
        resp.headers['X-Content-Type-Options'] = 'nosniff'
        resp.headers['X-Frame-Options'] = 'DENY'
        return resp

# ===========================================
# HELPERS
# ===========================================
# Cache simple en memoria para endpoints frecuentes
_app_cache: dict = {}
_app_cache_ts: dict = {}

def app_cache_get(key: str, ttl: int = 60):
    """Obtener valor del cache si no ha expirado"""
    import time
    if key in _app_cache and (time.time() - _app_cache_ts.get(key, 0)) < ttl:
        return _app_cache[key]
    return None

def app_cache_set(key: str, value):
    """Guardar valor en cache"""
    import time
    _app_cache[key] = value
    _app_cache_ts[key] = time.time()

def crear_notificacion(db: Session, usuario_id: int, titulo: str, mensaje: str = '', tipo: str = 'info', link: str = '', colegio_id: int = None):
    """Crear notificación para un usuario"""
    n = Notificacion(usuario_id=usuario_id, titulo=titulo, mensaje=mensaje, tipo=tipo, link=link, colegio_id=colegio_id)
    db.add(n)
    return n

def notificar_rol(db: Session, colegio_id: int, role: str, titulo: str, mensaje: str = '', tipo: str = 'info', link: str = ''):
    """Crear notificación para todos los usuarios de un rol en un colegio"""
    usuarios = db.query(Usuario).filter_by(colegio_id=colegio_id, role=role, activo=True).all()
    for u in usuarios:
        crear_notificacion(db, u.id, titulo, mensaje, tipo, link, colegio_id)

def log_auditoria(db: Session, accion, tabla, registro_id=None, datos_anteriores=None,
                   datos_nuevos=None, user=None, request: Request = None):
    """Registra acción en auditoría.
    
    v2.13.5: ahora hace flush automático para que el log quede listo para
    commit en el mismo request, incluso si el endpoint hizo commit antes
    de loguear. Si el endpoint no hace ningún commit después, el log SE PIERDE
    en rollback (lo cual es correcto: una operación fallida no debe loguearse
    como exitosa).
    
    Si necesitás garantizar persistencia incluso en endpoints raros que ya
    comitearon, llamá db.commit() después de log_auditoria.
    """
    client_ip = get_client_ip(request) if request else None
    user_agent = request.headers.get('User-Agent', '')[:200] if request else ''
    log = LogAuditoria(
        usuario_id=user.id if user else None,
        colegio_id=user.colegio_id if user and hasattr(user, 'colegio_id') else None,
        accion=accion, entidad=tabla, entidad_id=registro_id,
        detalles=str({'antes': datos_anteriores, 'despues': datos_nuevos}) if datos_anteriores or datos_nuevos else None,
        ip=client_ip, user_agent=user_agent,
        tabla=tabla, registro_id=registro_id,
        datos_anteriores=str(datos_anteriores) if datos_anteriores else None,
        datos_nuevos=str(datos_nuevos) if datos_nuevos else None
    )
    db.add(log)
    # Flush para que el log esté en la transacción pendiente. El commit
    # final lo decide el endpoint según su flujo.
    try:
        db.flush()
    except Exception as e:
        logger.warning(f"log_auditoria flush falló: {e}")


def _auditar_escritura_automatica(request: Request, metodo: str, path: str, status: int):
    """v2.13.31: auditoría automática de escrituras (llamada desde el middleware).

    Registra QUIÉN hizo QUÉ operación, DESDE DÓNDE y CUÁNDO, para toda
    escritura exitosa. Usa una sesión de BD PROPIA (no la del endpoint) para
    no interferir con la transacción del request. Decodifica el JWT para
    obtener usuario_id y colegio_id. Todo envuelto en try/except: la
    auditoría jamás debe afectar la respuesta al usuario.

    Esta es la capa de COBERTURA TOTAL. El detalle fino (antes/después) lo
    agregan los endpoints críticos con log_auditoria().
    """
    from database import SessionLocal as _SL
    from auth import decode_token as _decode, get_client_ip as _gcip

    usuario_id = None
    colegio_id = None
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        payload = _decode(auth_header.split(' ', 1)[1])
        if payload:
            usuario_id = payload.get('user_id') or payload.get('sub') or payload.get('id')
            colegio_id = payload.get('colegio_id')
            try:
                usuario_id = int(usuario_id) if usuario_id is not None else None
            except (ValueError, TypeError):
                usuario_id = None

    # Si no hay usuario identificable, no auditamos (endpoints públicos raros)
    if usuario_id is None:
        return

    try:
        ip = _gcip(request)
    except Exception:
        ip = None
    user_agent = request.headers.get('User-Agent', '')[:200]

    _db = _SL()
    try:
        log = LogAuditoria(
            usuario_id=usuario_id,
            colegio_id=colegio_id,
            accion=f'{metodo} {path}',
            entidad=path,
            ip=ip,
            user_agent=user_agent,
            tabla='_auto',
            detalles=f'{{"auto": true, "status": {status}}}',
        )
        _db.add(log)
        _db.commit()
    except Exception as e:
        _db.rollback()
        logging.getLogger('educaone.audit').warning(f'auditoría auto commit falló: {e}')
    finally:
        _db.close()


def normalize_nivel(value: str | None, default: str = 'secundaria') -> str:
    """Normaliza niveles a los valores canónicos usados en filtros y UI."""
    nivel = (value or default).strip().lower()
    if nivel.startswith('sec'):
        return 'secundaria'
    if nivel.startswith('prim'):
        return 'primaria'
    if nivel.startswith('ini') or nivel.startswith('prees') or nivel.startswith('pre-'):
        return 'inicial'
    return default


# ═══════════════════════════════════════════════════════════════════
# HELPERS DE MÓDULOS (Plan + Uso)
# ═══════════════════════════════════════════════════════════════════
#
# Un módulo está EFECTIVAMENTE activo solo si:
#   colegio.plan_X = True       (superadmin lo permitió por contrato)
# Y además:
#   config.usa_X = True         (director lo encendió)
#
# Esto separa decisiones comerciales de operacionales.

# Lista oficial de módulos. Centralizada para que cualquier cambio se
# refleje en todos los endpoints automáticamente.
MODULOS_DISPONIBLES = [
    # Niveles
    'secundaria', 'primaria', 'inicial',
    # Módulos funcionales
    'whatsapp', 'psicologia', 'eval_profesores', 'eval_interna',
    'comunicacion_padres', 'registro_escolar', 'reportes_conducta',
]
NIVELES = ('secundaria', 'primaria', 'inicial')
MODULOS_FUNCIONALES = tuple(m for m in MODULOS_DISPONIBLES if m not in NIVELES)


def is_modulo_activo(db: Session, user: Usuario, modulo: str) -> bool:
    """
    Devuelve True si el módulo está activo para el colegio del usuario.
    
    REFACTOR v2.11 (Interpretación A): solo se chequea PLAN (lo contratado
    con superadmin). Antes había un doble switch plan+uso que causaba bugs
    sutiles: grados de un nivel desaparecían si usa_X quedaba en False por
    estado heredado, aunque el plan los incluyera.
    
    Superadmin: siempre True. Usuario sin colegio: True. Módulo desconocido: True
    (no rompe endpoints que pasen módulos nuevos no listados aún).
    """
    if user is None or getattr(user, 'role', None) == 'superadmin':
        return True
    if not getattr(user, 'colegio_id', None):
        return True
    if modulo not in MODULOS_DISPONIBLES:
        return True
    
    colegio = db.get(Colegio, user.colegio_id)
    if not colegio:
        return True
    
    plan_attr = f'plan_{modulo}'
    return bool(getattr(colegio, plan_attr, True))


def assert_modulo_activo(db: Session, user: Usuario, modulo: str):
    """
    Levanta HTTPException 403 si el módulo no está contratado en el plan.
    
    REFACTOR v2.11 (Interpretación A): solo chequea plan_X (lo que contrató
    el superadmin). El doble switch plan+uso fue eliminado para simplificar.
    """
    if user is None or getattr(user, 'role', None) == 'superadmin':
        return
    if not getattr(user, 'colegio_id', None) or modulo not in MODULOS_DISPONIBLES:
        return
    
    colegio = db.get(Colegio, user.colegio_id)
    if not colegio:
        return
    
    plan_attr = f'plan_{modulo}'
    plan_ok = bool(getattr(colegio, plan_attr, True))
    if not plan_ok:
        raise HTTPException(
            status_code=403,
            detail=f'El módulo "{modulo}" no está incluido en su plan. '
                   f'Contacte a soporte para habilitarlo.'
        )


def assert_nivel_activo(db: Session, user: Usuario, nivel: str):
    """
    Valida que el colegio del usuario tenga el nivel activado (delegando a
    assert_modulo_activo). Mantiene la firma original para no romper los
    endpoints que ya lo usan.
    
    Niveles fuera de {primaria, secundaria, inicial} no se validan.
    """
    nivel_norm = normalize_nivel(nivel) if nivel else ''
    if nivel_norm not in NIVELES:
        return
    assert_modulo_activo(db, user, nivel_norm)


def assert_nivel_curso_activo(db: Session, user: Usuario, curso_id: int):
    """
    Dado un curso_id, valida que el nivel del grado del curso esté activo
    para el colegio del usuario. Útil en endpoints que reciben curso_id
    pero no nivel directamente (estudiantes, asistencia, calificaciones).
    
    Si el curso no existe o no tiene grado, no valida (ese error lo agarra
    otro path).
    """
    if user is None or getattr(user, 'role', None) == 'superadmin':
        return
    if not curso_id:
        return
    curso = db.get(Curso, curso_id)
    if not curso or not curso.grado_id:
        return
    grado = db.get(Grado, curso.grado_id)
    if not grado or not grado.nivel:
        return
    assert_nivel_activo(db, user, grado.nivel)


def assert_modulo_activo(db: Session, user: Usuario, modulo: str):
    """
    Valida que un módulo esté contratado (plan_X = True) para el colegio del usuario.
    Levanta HTTPException(403) si no.
    
    Módulo: nombre canónico sin prefijo (ej: 'comunicacion_padres', 'reportes_conducta',
    'whatsapp', 'psicologia', 'eval_profesores', 'eval_interna', 'registro_escolar').
    
    REFACTOR v2.11 (Interpretación A): solo chequea PLAN, no USO.
    Antes había un doble switch "plan + uso" que confundía al director:
    contrataba un módulo y tenía que ir a configuración a "activarlo" otra vez.
    Ahora si superadmin contrató el módulo, está prendido para todo el colegio.
    Los campos usa_X y sub-políticas se mantienen en la BD por compatibilidad
    pero ya no se chequean en este flujo.
    
    Superadmin omite validación.
    """
    from fastapi import HTTPException
    
    if user is None or getattr(user, 'role', None) == 'superadmin':
        return
    if not user.colegio_id:
        return
    
    colegio = db.get(Colegio, user.colegio_id)
    if not colegio:
        raise HTTPException(status_code=403, detail='Colegio no encontrado')
    
    plan_attr = f'plan_{modulo}'
    if not getattr(colegio, plan_attr, False):
        raise HTTPException(
            status_code=403,
            detail=f'El módulo "{modulo}" no está incluido en el plan de tu colegio. Contactá a soporte.'
        )
    # Ya no se chequea usa_X — si el colegio contrató el módulo, está activo.



def get_or_404(db: Session, model, id):
    """Equivalente a Flask get_or_404 con validación tenant automática."""
    obj = db.get(model, id)
    if not obj:
        raise HTTPException(status_code=404, detail="No encontrado")
    current_user = db.info.get('current_user') or current_user_ctx.get()
    if current_user and current_user.role != 'superadmin' and hasattr(obj, 'colegio_id'):
        if obj.colegio_id != current_user.colegio_id:
            raise HTTPException(status_code=404, detail="No encontrado")
    return obj

def get_or_404_tenant(db: Session, model, id, user):
    """get_or_404 con validación de tenant - evita acceso cross-tenant"""
    return get_or_404(db, model, id)

def paginate(query, request: Request, default_per_page=50, max_per_page=200):
    """Paginación estándar. Retorna {items, total, page, pages, per_page}"""
    page = int(request.query_params.get('page', 1))
    per_page = min(int(request.query_params.get('per_page', default_per_page)), max_per_page)
    if page < 1: page = 1
    
    total = query.count()
    pages = max((total + per_page - 1) // per_page, 1)
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    
    return {
        'items': items,
        'total': total,
        'page': page,
        'pages': pages,
        'per_page': per_page
    }

@app.post("/api/auth/login")
async def login(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    if not data or not data.get('username') or not data.get('password'):
        return JSONResponse({'error': 'Usuario y contraseña requeridos'}, status_code=400)
    
    # Obtener IP para rate limiting
    client_ip = get_client_ip(request)
    if client_ip and ',' in client_ip:
        client_ip = client_ip.split(',')[0].strip()
    
    # Verificar rate limiting (consulta BD para multi-worker / sobrevivir reinicios)
    allowed, remaining = check_rate_limit(client_ip, db=db)
    if not allowed:
        logger.warning(f'Rate limit excedido para IP: {client_ip}')
        return JSONResponse({
            'error': 'Demasiados intentos de login. Espere 15 minutos.',
            'retry_after': 900
        }, status_code=429)
    
    user = db.query(Usuario).filter_by(username=data['username'], activo=True).first()
    
    if user and user.check_password(data['password']):
        # Verificar que el colegio esté activo (excepto superadmin)
        if user.role != 'superadmin' and user.colegio_id:
            colegio = db.query(Colegio).get(user.colegio_id)
            if not colegio or not colegio.activo:
                return JSONResponse({'error': 'El colegio está desactivado. Contacte al administrador.'}, status_code=403)
        
        user.last_login = now_rd()
        
        # Limpiar intentos fallidos (memoria + BD)
        register_attempt(client_ip, success=True, db=db)
        
        # Generar token JWT — usar create_token para que incluya
        # token_version e iat (necesarios para validación e invalidación de sesión)
        token = create_token(user)
        
        # Log de acceso exitoso
        log = LogAcceso(
            usuario_id=user.id,
            colegio_id=user.colegio_id,
            tipo='login',
            ip=client_ip,
            user_agent=request.headers.get('User-Agent', '')[:300]
        )
        db.add(log)
        
        # Log de auditoría
        audit = LogAuditoria(
            usuario_id=user.id,
            colegio_id=user.colegio_id,
            accion='login_exitoso',
            entidad='sesion',
            entidad_id=user.id,
            ip=client_ip,
            user_agent=request.headers.get('User-Agent', '')[:200]
        )
        db.add(audit)
        db.commit()
        
        logger.info(f'Login exitoso: {user.username} desde {client_ip}')
        
        # Obtener info del colegio para el frontend
        colegio_info = None
        if user.colegio_id:
            colegio_obj = db.query(Colegio).get(user.colegio_id)
            if colegio_obj:
                colegio_info = {'id': colegio_obj.id, 'nombre': colegio_obj.nombre, 'codigo': colegio_obj.codigo}
        
        return {
            'message': 'Login exitoso',
            'user': user.to_dict(),
            'token': token,
            'colegio': colegio_info
        }
    
    # Registrar intento fallido (memoria + BD para multi-worker)
    register_attempt(
        client_ip,
        success=False,
        db=db,
        user_agent=request.headers.get('User-Agent', '')[:300],
    )
    
    # Log de intento fallido
    log = LogAcceso(
        tipo='login_fallido',
        ip=client_ip,
        user_agent=request.headers.get('User-Agent', '')[:300],
        colegio_id=None
    )
    db.add(log)
    
    # Log de auditoría
    audit = LogAuditoria(
        accion='login_fallido',
        entidad='sesion',
        detalles=f'username: {data.get("username", "?")}',
        ip=client_ip,
        colegio_id=None
    )
    db.add(audit)
    db.commit()
    
    logger.warning(f'Login fallido para usuario: {data.get("username")} desde {client_ip}')
    
    return JSONResponse({'error': 'Credenciales inválidas'}, status_code=401)

@app.post("/api/auth/logout")
async def logout(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Logout: incrementa token_version del usuario para invalidar el token actual.
    
    Cualquier petición posterior con ese token devolverá 401, incluso si aún
    no ha expirado por tiempo. Esto da invalidación real de sesión sin
    necesidad de blacklist en BD/Redis.
    """
    client_ip = get_client_ip(request)
    
    # Invalidar el token actual (y todos los tokens previos del usuario)
    current_user.token_version = (current_user.token_version or 0) + 1
    
    log = LogAcceso(
        usuario_id=current_user.id,
        tipo='logout',
        ip=client_ip,
        colegio_id=current_user.colegio_id
    )
    db.add(log)
    
    audit = LogAuditoria(
        usuario_id=current_user.id,
        accion='logout',
        entidad='sesion',
        entidad_id=current_user.id,
        ip=client_ip,
        colegio_id=current_user.colegio_id
    )
    db.add(audit)
    db.commit()
    return {'message': 'Logout exitoso'}

@app.get("/api/auth/me")
async def get_me_endpoint(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user_optional)):
    """Obtener usuario actual desde token JWT"""
    if current_user:
        return current_user.to_dict()
    return JSONResponse({'error': 'No autorizado'}, status_code=401)

@app.post("/api/auth/cambiar-password")
async def cambiar_password(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    data = await request.json()
    if not data.get('password_actual') or not data.get('password_nuevo'):
        return JSONResponse({'error': 'Contraseñas requeridas'}, status_code=400)
    
    if not current_user.check_password(data['password_actual']):
        # Log de intento fallido
        log_auditoria(db, 'cambio_password_fallido', 'usuarios', current_user.id, user=current_user, request=request)
        db.commit()
        return JSONResponse({'error': 'Contraseña actual incorrecta'}, status_code=400)
    
    password_nuevo = data['password_nuevo']
    
    # Validaciones de contraseña fuerte
    if len(password_nuevo) < 8:
        return JSONResponse({'error': 'La nueva contraseña debe tener al menos 8 caracteres'}, status_code=400)
    
    if not re.search(r'[A-Z]', password_nuevo):
        return JSONResponse({'error': 'La contraseña debe tener al menos una letra mayúscula'}, status_code=400)
    
    if not re.search(r'[a-z]', password_nuevo):
        return JSONResponse({'error': 'La contraseña debe tener al menos una letra minúscula'}, status_code=400)
    
    if not re.search(r'\d', password_nuevo):
        return JSONResponse({'error': 'La contraseña debe tener al menos un número'}, status_code=400)
    
    current_user.set_password(password_nuevo)
    # Si el usuario estaba forzado a cambiar password (init_db, reset por admin),
    # ya cumplió el requisito — limpiar el flag para que pueda usar el sistema.
    current_user.must_change_password = False
    # Invalidar sesiones previas (incluyendo la actual): el cliente debe
    # re-autenticarse con la nueva password. Esto es importante por seguridad:
    # si la password vieja se filtró, los tokens emitidos con ella quedan
    # también invalidados.
    current_user.token_version = (current_user.token_version or 0) + 1
    log_auditoria(db, 'cambio_password', 'usuarios', current_user.id, user=current_user, request=request)
    db.commit()
    
    logger.info(f'Contraseña cambiada para usuario: {current_user.username}')
    
    return {'message': 'Contraseña actualizada'}

# ============== CONFIGURACIÓN ==============

@app.get("/api/configuracion/colegio")
async def get_config_colegio(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    config = tenant_filter(db.query(ConfiguracionColegio), ConfiguracionColegio, current_user).first()
    if not config:
        config = ConfiguracionColegio(colegio_id=current_user.colegio_id)
        db.add(config)
        db.commit()
    
    # Niveles activos (multi-tenant). Si no hay colegio (superadmin sin contexto)
    # asumimos ambos activos.
    tiene_primaria = True
    tiene_secundaria = True
    if current_user.colegio_id:
        colegio = db.get(Colegio, current_user.colegio_id)
        if colegio:
            tiene_primaria = bool(getattr(colegio, 'tiene_primaria', True))
            tiene_secundaria = bool(getattr(colegio, 'tiene_secundaria', True))
    
    return {
        'id': config.id,
        'nombre': config.nombre,
        'logo': config.logo,
        'telefono': config.telefono,
        'email': config.email,
        'direccion': config.direccion,
        'distrito': config.distrito,
        'regional': config.regional,
        'lema': config.lema,
        'director': config.director,
        'umbral_calificacion_baja': config.umbral_calificacion_baja,
        'umbral_calificacion_critica': config.umbral_calificacion_critica,
        'umbral_asistencia_baja': config.umbral_asistencia_baja,
        'dias_ausencia_alerta': config.dias_ausencia_alerta,
        'dias_ausencia_critica': config.dias_ausencia_critica,
        # Niveles activos (tenant)
        'tiene_primaria': tiene_primaria,
        'tiene_secundaria': tiene_secundaria,
        # Nombres de competencias por período
        'nombre_p1': getattr(config, 'nombre_p1', 'Comunicativa'),
        'nombre_p2': getattr(config, 'nombre_p2', 'Pensamiento Lógico, Creativo y Crítico'),
        'nombre_p3': getattr(config, 'nombre_p3', 'Científica y Tecnológica'),
        'nombre_p4': getattr(config, 'nombre_p4', 'Desarrollo Personal'),
        # Datos MINERD para registro escolar
        'codigo_centro': getattr(config, 'codigo_centro', None),
        'codigo_cartografia': getattr(config, 'codigo_cartografia', None),
        'sector': getattr(config, 'sector', None),
        'zona': getattr(config, 'zona', None),
        'tanda_operacion': getattr(config, 'tanda_operacion', None),
        'nivel': getattr(config, 'nivel', 'Secundario'),
        'modalidad': getattr(config, 'modalidad', 'General'),
        'correo_centro': getattr(config, 'correo_centro', None),
        'nombre_director': getattr(config, 'nombre_director', None),
        'cedula_director': getattr(config, 'cedula_director', None),
        'correo_director': getattr(config, 'correo_director', None),
        'telefono_director': getattr(config, 'telefono_director', None),
        'nombre_coordinador': getattr(config, 'nombre_coordinador', None),
    }

@app.put("/api/configuracion/colegio")
async def update_config_colegio(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    config = tenant_filter(db.query(ConfiguracionColegio), ConfiguracionColegio, current_user).first()
    data = await request.json()
    
    for campo in ['nombre', 'telefono', 'email', 'direccion', 'distrito', 'regional',
                  'lema', 'director', 'umbral_calificacion_baja',
                  'umbral_calificacion_critica', 'umbral_asistencia_baja',
                  'dias_ausencia_alerta', 'dias_ausencia_critica',
                  'nombre_p1', 'nombre_p2', 'nombre_p3', 'nombre_p4',
                  'codigo_centro', 'codigo_cartografia', 'sector', 'zona',
                  'tanda_operacion', 'nivel', 'modalidad', 'correo_centro',
                  'nombre_director', 'cedula_director', 'correo_director',
                  'telefono_director', 'nombre_coordinador']:
        if campo in data:
            setattr(config, campo, data[campo])
    
    db.commit()
    return {'message': 'Configuración actualizada'}

@app.post("/api/configuracion/colegio/logo")
async def upload_logo(logo: UploadFile = File(...), db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    if not logo or logo.filename == '':
        return JSONResponse({'error': 'No se envió archivo'}, status_code=400)
    
    # Validar tipo de archivo
    allowed_types = ['image/png', 'image/jpeg', 'image/jpg', 'image/gif', 'image/webp']
    if logo.content_type not in allowed_types:
        return JSONResponse({'error': 'Tipo de archivo no permitido. Use PNG, JPG o GIF'}, status_code=400)
    
    config = tenant_filter(db.query(ConfiguracionColegio), ConfiguracionColegio, current_user).first()
    if not config:
        config = ConfiguracionColegio(nombre='Mi Colegio', colegio_id=current_user.colegio_id)
        db.add(config)
    
    try:
        file_data = await logo.read()
        
        # Validar tamaño (máximo 2MB)
        if len(file_data) > 2 * 1024 * 1024:
            return JSONResponse({'error': 'El archivo es muy grande. Máximo 2MB'}, status_code=400)
        
        # Intentar comprimir si es muy grande (más de 500KB)
        if len(file_data) > 500 * 1024:
            try:
                from PIL import Image
                img = Image.open(BytesIO(file_data))
                
                # Redimensionar si es muy grande
                max_size = (400, 400)
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
                
                # Guardar comprimido
                buffer = BytesIO()
                formato = 'PNG' if logo.content_type == 'image/png' else 'JPEG'
                img.save(buffer, format=formato, quality=85, optimize=True)
                file_data = buffer.getvalue()
            except ImportError:
                # Si no tiene PIL, usar el archivo original
                pass
        
        config.logo = f"data:{logo.content_type};base64,{base64.b64encode(file_data).decode()}"
        db.commit()
        return {'message': 'Logo actualizado', 'logo': config.logo}
    except Exception as e:
        db.rollback()
        return JSONResponse({'error': f'Error al procesar imagen: {str(e)}'}, status_code=500)

# ============== PERMISOS DE MÓDULOS ==============

@app.get("/api/configuracion")
async def get_configuracion(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """
    Configuración del colegio actual con módulos en formato Plan + Uso.
    
    Para cada módulo devuelve:
      plan:   bool — si el contrato lo permite (lo controla superadmin)
      usa:    bool — si el director lo encendió
      activo: bool — plan AND usa, lo que el frontend usa para mostrar/ocultar
    
    Cualquier usuario autenticado puede leer esto (necesario para el menú).
    """
    if not current_user.colegio_id and current_user.role != 'superadmin':
        return JSONResponse({'error': 'Usuario sin colegio asociado'}, status_code=400)
    
    if not current_user.colegio_id:
        # Superadmin sin colegio context → devolver vacío
        return {'colegio_id': None, 'modulos': {}}
    
    colegio = db.get(Colegio, current_user.colegio_id)
    if not colegio:
        return JSONResponse({'error': 'Colegio no encontrado'}, status_code=404)
    
    # Asegurar que existe ConfiguracionColegio para este tenant
    config = db.query(ConfiguracionColegio).filter_by(colegio_id=colegio.id).first()
    if not config:
        config = ConfiguracionColegio(nombre=colegio.nombre, colegio_id=colegio.id)
        db.add(config)
        db.commit()
        db.refresh(config)
    
    modulos = {}
    for m in MODULOS_DISPONIBLES:
        plan_val = bool(getattr(colegio, f'plan_{m}', True))
        # REFACTOR v2.11: activo = plan. Sin doble switch.
        # Conservamos 'usa' en la respuesta por retrocompatibilidad con
        # frontend viejo, pero ahora siempre vale lo mismo que 'plan'.
        modulos[m] = {
            'plan': plan_val,
            'usa': plan_val,
            'activo': plan_val,
        }
    
    return {
        'colegio_id': colegio.id,
        'nombre': colegio.nombre,
        'codigo': colegio.codigo,
        'plan': colegio.plan,
        'modulos': modulos,
        # Aliases legacy (frontend viejo)
        'tiene_primaria': modulos['primaria']['activo'],
        'tiene_secundaria': modulos['secundaria']['activo'],
    }


@app.put("/api/configuracion/modulos")
async def update_modulos_director(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """
    REFACTOR v2.11 (Interpretación A): el director ya NO puede activar/desactivar
    módulos. El plan lo controla únicamente el superadmin.
    
    Este endpoint se mantiene para no romper el frontend viejo, pero ahora
    solo devuelve un mensaje informativo. Acepta el PUT con cualquier body,
    no aplica ningún cambio, y responde 200 con la configuración actual.
    
    Si el director quiere modificar su plan, debe contactar a soporte.
    """
    if not current_user.colegio_id:
        return JSONResponse({'error': 'Usuario sin colegio asociado'}, status_code=400)
    
    colegio = db.get(Colegio, current_user.colegio_id)
    if not colegio:
        return JSONResponse({'error': 'Colegio no encontrado'}, status_code=404)
    
    # No aplicamos cambios. Devolvemos el plan actual.
    modulos = {}
    for m in MODULOS_DISPONIBLES:
        plan_val = bool(getattr(colegio, f'plan_{m}', True))
        modulos[m] = {'plan': plan_val, 'usa': plan_val, 'activo': plan_val}
    
    return {
        'message': 'Los módulos del colegio están definidos por su plan. '
                   'Para modificarlos, contacte a soporte.',
        'modulos': modulos,
        'plan_solo_lectura': True,
    }


# Alias legacy: /api/configuracion/modulos GET → mismo formato viejo (modulo_X)
# para no romper el frontend actual mientras migra al nuevo formato.
@app.get("/api/configuracion/modulos")
async def get_modulos_config_legacy(db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """[LEGACY] Endpoint antiguo. Devuelve módulos en formato modulo_X.
    
    REFACTOR v2.11: 'efectivo' ahora es solo plan (sin uso). Sub-políticas
    devuelven False siempre (se eliminaron del flujo). Se mantiene la forma
    del response para no romper el frontend hasta que migre.
    """
    if not current_user.colegio_id:
        return JSONResponse({'error': 'Usuario sin colegio asociado'}, status_code=400)
    colegio = db.get(Colegio, current_user.colegio_id)
    if not colegio:
        return JSONResponse({'error': 'Colegio no encontrado'}, status_code=404)
    
    def efectivo(m):
        # v2.11: efectivo = plan_X (sin AND con usa_X)
        return bool(getattr(colegio, f'plan_{m}', True))
    
    return {
        'modulo_whatsapp': efectivo('whatsapp'),
        'whatsapp_solo_direccion': False,  # sub-política eliminada
        'modulo_psicologia': efectivo('psicologia'),
        'modulo_comunicacion_padres': efectivo('comunicacion_padres'),
        'modulo_eval_profesores': efectivo('eval_profesores'),
        'modulo_eval_interna': efectivo('eval_interna'),
        'modulo_registro_escolar': efectivo('registro_escolar'),
        'modulo_reportes_conducta': efectivo('reportes_conducta'),
        'permitir_profesor_reportes': True,  # v2.11: profesores siempre crean reportes
        'modulo_secundaria': efectivo('secundaria'),
        'modulo_primaria': efectivo('primaria'),
        'modulo_inicial': efectivo('inicial'),
    }


@app.put("/api/configuracion")
async def update_configuracion_legacy(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """[LEGACY] Antes aceptaba {tiene_primaria, tiene_secundaria} para cambiar
    el uso. En v2.11 (Interpretación A) el director no puede modificar el plan.
    
    Se mantiene por compatibilidad con frontend viejo. Acepta el PUT pero NO
    aplica cambios al plan. Devuelve la configuración actual.
    """
    if not current_user.colegio_id:
        return JSONResponse({'error': 'Usuario sin colegio asociado'}, status_code=400)
    
    colegio = db.get(Colegio, current_user.colegio_id)
    if not colegio:
        return JSONResponse({'error': 'Colegio no encontrado'}, status_code=404)
    
    return {
        'message': 'Los niveles del colegio están definidos por su plan. '
                   'Para modificarlos, contacte a soporte.',
        'tiene_primaria': bool(colegio.plan_primaria),
        'tiene_secundaria': bool(colegio.plan_secundaria),
        'plan_solo_lectura': True,
    }


# ============== AÑO ESCOLAR ==============

@app.get("/api/ano-escolar")
async def get_ano_escolar_activo(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    ano = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    if not ano:
        return JSONResponse({'error': 'No hay año escolar activo'}, status_code=404)
    
    # Si periodo_activo es None, establecer como 1 por defecto
    periodo_activo = ano.periodo_activo if ano.periodo_activo is not None else 1
    
    return {
        'id': ano.id,
        'nombre': ano.nombre,
        'fecha_inicio': ano.fecha_inicio.isoformat() if ano.fecha_inicio else None,
        'fecha_fin': ano.fecha_fin.isoformat() if ano.fecha_fin else None,
        'activo': ano.activo,
        'cerrado': ano.cerrado,
        'periodo_activo': periodo_activo,
        'p1_inicio': ano.p1_inicio.isoformat() if ano.p1_inicio else None,
        'p1_fin': ano.p1_fin.isoformat() if ano.p1_fin else None,
        'p1_cerrado': ano.p1_cerrado if ano.p1_cerrado is not None else False,
        'p2_inicio': ano.p2_inicio.isoformat() if ano.p2_inicio else None,
        'p2_fin': ano.p2_fin.isoformat() if ano.p2_fin else None,
        'p2_cerrado': ano.p2_cerrado if ano.p2_cerrado is not None else False,
        'p3_inicio': ano.p3_inicio.isoformat() if ano.p3_inicio else None,
        'p3_fin': ano.p3_fin.isoformat() if ano.p3_fin else None,
        'p3_cerrado': ano.p3_cerrado if ano.p3_cerrado is not None else False,
        'p4_inicio': ano.p4_inicio.isoformat() if ano.p4_inicio else None,
        'p4_fin': ano.p4_fin.isoformat() if ano.p4_fin else None,
        'p4_cerrado': ano.p4_cerrado if ano.p4_cerrado is not None else False,
    }

@app.get("/api/anos-escolares")
async def get_anos_escolares(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    anos = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).order_by(AnoEscolar.nombre.desc()).all()
    return [{
        'id': a.id, 'nombre': a.nombre, 'activo': a.activo, 'cerrado': a.cerrado
    } for a in anos]

@app.post("/api/ano-escolar")
async def crear_ano_escolar(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    data = await request.json()
    
    # Desactivar otros años del mismo colegio
    tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).update({AnoEscolar.activo: False})
    
    ano = AnoEscolar(
        nombre=data['nombre'],
        fecha_inicio=datetime.strptime(data['fecha_inicio'], '%Y-%m-%d').date() if data.get('fecha_inicio') else None,
        fecha_fin=datetime.strptime(data['fecha_fin'], '%Y-%m-%d').date() if data.get('fecha_fin') else None,
        activo=True,
        periodo_activo=1,  # Siempre inicia con P1 activo
        colegio_id=current_user.colegio_id
    )
    db.add(ano)
    db.commit()
    return JSONResponse({'message': 'Año escolar creado', 'id': ano.id}, status_code=201)


@app.post("/api/ano-escolar/{id}/clonar-cursos")
async def clonar_cursos_ano(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """v2.13.20 — Clonar la estructura de cursos de un año a este año destino.

    Crea, en el año {id} (destino), una copia de cada curso activo del año
    origen (mismo nombre, grado, tanda, aula, capacidad) — SIN estudiantes.
    Útil al iniciar un año nuevo para tener los cursos donde promover.

    Body: { "origen_ano_id": int }  (si no se pasa, usa el año cerrado más reciente)
    No duplica: si el curso ya existe en el destino (mismo grado+tanda+nombre), lo salta.
    """
    destino = get_tenant_or_404(db, AnoEscolar, id, current_user, name='anoescolar')
    try:
        data = await request.json()
    except Exception:
        data = {}
    origen_id = data.get('origen_ano_id')
    if origen_id:
        origen = get_tenant_or_404(db, AnoEscolar, origen_id, current_user, name='anoescolar')
    else:
        origen = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(cerrado=True).order_by(AnoEscolar.id.desc()).first()
    if not origen:
        return JSONResponse({'error': 'No se encontró un año origen para clonar los cursos.'}, status_code=400)
    if origen.id == destino.id:
        return JSONResponse({'error': 'El año origen y destino no pueden ser el mismo.'}, status_code=400)

    cursos_origen = tenant_filter(db.query(Curso), Curso, current_user).filter_by(activo=True, ano_escolar_id=origen.id).all()
    existentes = tenant_filter(db.query(Curso), Curso, current_user).filter_by(ano_escolar_id=destino.id).all()
    claves_existentes = {(c.grado_id, c.tanda_id, (c.nombre or '').strip().lower()) for c in existentes}

    creados = 0
    for c in cursos_origen:
        clave = (c.grado_id, c.tanda_id, (c.nombre or '').strip().lower())
        if clave in claves_existentes:
            continue
        db.add(Curso(
            colegio_id=current_user.colegio_id,
            nombre=c.nombre,
            grado_id=c.grado_id,
            tanda_id=c.tanda_id,
            ano_escolar_id=destino.id,
            capacidad=c.capacidad,
            aula=c.aula,
            activo=True,
        ))
        creados += 1
    db.commit()
    return {
        'message': f'{creados} curso(s) clonados al año {destino.nombre}',
        'creados': creados,
        'origen': origen.nombre,
        'destino': destino.nombre,
    }


@app.put("/api/ano-escolar/{id}")
async def update_ano_escolar(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    ano = get_tenant_or_404(db, AnoEscolar, id, current_user, name='anoescolar')
    data = await request.json()
    
    for campo in ['nombre', 'p1_inicio', 'p1_fin', 'p2_inicio', 'p2_fin',
                  'p3_inicio', 'p3_fin', 'p4_inicio', 'p4_fin']:
        if campo in data:
            if 'inicio' in campo or 'fin' in campo:
                setattr(ano, campo, datetime.strptime(data[campo], '%Y-%m-%d').date() if data[campo] else None)
            else:
                setattr(ano, campo, data[campo])
    
    db.commit()
    return {'message': 'Año escolar actualizado'}

@app.post("/api/ano-escolar/{id}/cerrar")
async def cerrar_ano_escolar(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    ano = get_tenant_or_404(db, AnoEscolar, id, current_user, name='anoescolar')
    if getattr(ano, 'cerrado', False):
        return {'message': 'El año escolar ya estaba cerrado', 'ano_id': ano.id}
    
    ano.cerrado = True
    ano.activo = False
    
    # Crear historial académico para todos los estudiantes (evitar duplicados)
    estudiantes = tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(activo=True).all()
    historiales_creados = 0
    for est in estudiantes:
        existe = db.query(HistorialAcademico).filter_by(
            estudiante_id=est.id, ano_escolar_id=ano.id
        ).first()
        if existe:
            continue
        historial = HistorialAcademico(
            estudiante_id=est.id,
            colegio_id=current_user.colegio_id,
            ano_escolar_id=ano.id,
            grado_id=est.curso.grado_id if est.curso else None,
            curso_id=est.curso_id,
            condicion=est.condicion
        )
        db.add(historial)
        historiales_creados += 1
    
    db.commit()
    
    # Avisar si quedó sin año activo (para que dirección cree/active el siguiente)
    hay_activo = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    return {
        'message': 'Año escolar cerrado correctamente',
        'ano_id': ano.id,
        'historiales_creados': historiales_creados,
        'hay_ano_activo': hay_activo is not None,
        'aviso': None if hay_activo else 'No hay un año escolar activo. Creá o activá el nuevo año en Configuración → Año Escolar para seguir trabajando y promover estudiantes.'
    }


@app.post("/api/ano-escolar/{id}/reabrir")
async def reabrir_ano_escolar(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Reabrir un año escolar cerrado"""
    ano = get_tenant_or_404(db, AnoEscolar, id, current_user, name='anoescolar')
    
    # Desactivar otros años activos del mismo colegio
    tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).update({AnoEscolar.activo: False})
    
    ano.cerrado = False
    ano.activo = True
    
    log_auditoria(db, 'REABRIR_ANO_ESCOLAR', 'ano_escolar', ano.id, None, {
        'nombre': ano.nombre
    }, user=current_user, request=request)
    
    db.commit()
    return {'message': f'Año escolar {ano.nombre} reabierto exitosamente'}


@app.post("/api/ano-escolar/{id}/activar")
async def activar_ano_escolar(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Activar un año escolar existente (sin cerrarlo)"""
    ano = get_tenant_or_404(db, AnoEscolar, id, current_user, name='anoescolar')
    
    # Desactivar otros años activos del mismo colegio
    tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).update({AnoEscolar.activo: False})
    
    ano.activo = True
    db.commit()
    
    log_auditoria(db, 'ACTIVAR_ANO_ESCOLAR', 'ano_escolar', ano.id, user=current_user, request=request)
    db.commit()  # v2.13.5: garantizar persistencia del log
    
    return {'message': f'Año escolar {ano.nombre} activado'}


@app.delete("/api/mensajes/{id}")
async def eliminar_mensaje(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Eliminar un mensaje (solo el propietario puede hacerlo)"""
    mensaje = get_tenant_or_404(db, Mensaje, id, current_user, name='mensaje')
    
    # Solo el remitente o destinatario puede eliminar
    if mensaje.remitente_id != current_user.id and mensaje.destinatario_id != current_user.id:
        return JSONResponse({'error': 'No autorizado'}, status_code=403)
    
    db.delete(mensaje)
    db.commit()
    return {'message': 'Mensaje eliminado'}


@app.put("/api/mensajes/{id}")
async def editar_mensaje(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Editar un mensaje (solo el remitente y si no ha sido leído)"""
    mensaje = get_tenant_or_404(db, Mensaje, id, current_user, name='mensaje')
    
    if mensaje.remitente_id != current_user.id:
        return JSONResponse({'error': 'Solo el remitente puede editar'}, status_code=403)
    
    if mensaje.leido:
        return JSONResponse({'error': 'No se puede editar un mensaje ya leído'}, status_code=400)
    
    data = await request.json()
    if 'asunto' in data:
        mensaje.asunto = data['asunto']
    if 'contenido' in data:
        mensaje.contenido = data['contenido']
    
    db.commit()
    return {'message': 'Mensaje actualizado'}
    
    db.commit()
    return {'message': 'Año escolar cerrado'}

@app.post("/api/ano-escolar/promover")
async def promover_estudiantes(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    grados = tenant_filter(db.query(Grado), Grado, current_user).order_by(Grado.orden).all()
    grado_siguiente = {g.id: grados[i+1].id if i+1 < len(grados) else None for i, g in enumerate(grados)}
    
    estudiantes = tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(activo=True).all()
    for est in estudiantes:
        if est.condicion == 'Promovido' and est.curso and est.curso.grado_id:
            sig_grado = grado_siguiente.get(est.curso.grado_id)
            # La asignación a nuevo curso se haría manualmente o en otro proceso
    
    db.commit()
    return {'message': 'Estudiantes promovidos'}

# ============== GRADOS, TANDAS, ASIGNATURAS ==============

@app.get("/api/grados")
async def get_grados(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    query = tenant_filter(db.query(Grado), Grado, current_user).filter_by(activo=True)
    nivel = request.query_params.get('nivel')
    if nivel and nivel != 'todos':
        query = query.filter(Grado.nivel == nivel)
    
    # Filtrar por niveles efectivamente activos (plan AND uso). Superadmin ve todo.
    if current_user.role != 'superadmin' and current_user.colegio_id:
        niveles_excluidos = [n for n in NIVELES if not is_modulo_activo(db, current_user, n)]
        if niveles_excluidos:
            query = query.filter(~Grado.nivel.in_(niveles_excluidos))
    
    grados = query.order_by(Grado.orden).all()
    return [{'id': g.id, 'nombre': g.nombre, 'nivel': g.nivel or 'secundaria', 'ciclo': g.ciclo, 'orden': g.orden} for g in grados]

@app.post("/api/grados")
async def crear_grado(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    data = await request.json()
    nivel = normalize_nivel(data.get('nivel'))
    # Validar que el nivel esté activado en el colegio
    assert_nivel_activo(db, current_user, nivel)
    
    grado = Grado(
        nombre=data['nombre'],
        nivel=nivel,
        ciclo=data.get('ciclo'),
        orden=data.get('orden', 0),
        colegio_id=current_user.colegio_id
    )
    db.add(grado)
    db.commit()
    cache_clear(f'stats:{current_user.colegio_id}')
    cache_clear(f'cursos:{current_user.colegio_id}')
    return JSONResponse({'message': 'Grado creado', 'id': grado.id}, status_code=201)

@app.put("/api/grados/{id}")
async def update_grado(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Editar grado. Valida tenant."""
    grado = get_tenant_or_404(db, Grado, id, current_user, name='grado')
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({'error': 'Body inválido'}, status_code=400)
    grado.nombre = data.get('nombre', grado.nombre)
    if 'nivel' in data:
        grado.nivel = normalize_nivel(data.get('nivel'), grado.nivel or 'secundaria')
    grado.ciclo = data.get('ciclo', grado.ciclo)
    grado.orden = data.get('orden', grado.orden)
    db.commit()
    cache_clear(f'stats:{current_user.colegio_id}')
    cache_clear(f'cursos:{current_user.colegio_id}')
    return {'message': 'Grado actualizado'}


@app.delete("/api/grados/{id}")
async def delete_grado(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Soft-delete grado. Valida tenant."""
    grado = get_tenant_or_404(db, Grado, id, current_user, name='grado')
    grado.activo = False
    db.commit()
    cache_clear(f'cursos:{current_user.colegio_id}')
    return {'message': 'Grado eliminado'}

@app.get("/api/tandas")
async def get_tandas(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    tandas = tenant_filter(db.query(Tanda), Tanda, current_user).filter_by(activo=True).all()
    return [{'id': t.id, 'nombre': t.nombre, 'hora_inicio': t.hora_inicio, 'hora_fin': t.hora_fin} for t in tandas]

@app.post("/api/tandas")
async def crear_tanda(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    data = await request.json()
    tanda = Tanda(nombre=data['nombre'], hora_inicio=data.get('hora_inicio'), hora_fin=data.get('hora_fin'), colegio_id=current_user.colegio_id)
    db.add(tanda)
    db.commit()
    return JSONResponse({'message': 'Tanda creada', 'id': tanda.id}, status_code=201)

@app.put("/api/tandas/{id}")
async def update_tanda(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Editar tanda. Valida tenant."""
    tanda = get_tenant_or_404(db, Tanda, id, current_user, name='tanda')
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({'error': 'Body inválido'}, status_code=400)
    tanda.nombre = data.get('nombre', tanda.nombre)
    tanda.hora_inicio = data.get('hora_inicio', tanda.hora_inicio)
    tanda.hora_fin = data.get('hora_fin', tanda.hora_fin)
    db.commit()
    return {'message': 'Tanda actualizada'}


@app.delete("/api/tandas/{id}")
async def delete_tanda(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Soft-delete tanda. Valida tenant."""
    tanda = get_tenant_or_404(db, Tanda, id, current_user, name='tanda')
    tanda.activo = False
    db.commit()
    return {'message': 'Tanda eliminada'}

# ============== RECREOS ==============

@app.get("/api/recreos")
async def get_recreos(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Obtener todos los recreos"""
    tanda_id = request.query_params.get('tanda_id')
    if tanda_id:
        recreos = tenant_filter(db.query(Recreo), Recreo, current_user).filter_by(tanda_id=tanda_id, activo=True).all()
    else:
        recreos = tenant_filter(db.query(Recreo), Recreo, current_user).filter_by(activo=True).all()
    
    return [{
        'id': r.id,
        'tanda_id': r.tanda_id,
        'tanda': r.tanda.nombre if r.tanda else None,
        'nombre': r.nombre,
        'hora_inicio': r.hora_inicio,
        'hora_fin': r.hora_fin
    } for r in recreos]

@app.post("/api/recreos")
async def crear_recreo(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Crear un nuevo recreo"""
    data = await request.json()
    recreo = Recreo(
        tanda_id=data['tanda_id'],
        colegio_id=current_user.colegio_id,
        nombre=data.get('nombre', 'Recreo'),
        hora_inicio=data['hora_inicio'],
        hora_fin=data['hora_fin']
    )
    db.add(recreo)
    db.commit()
    return JSONResponse({'message': 'Recreo creado', 'id': recreo.id}, status_code=201)

@app.put("/api/recreos/{id}")
async def update_recreo(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Actualizar recreo"""
    recreo = get_tenant_or_404(db, Recreo, id, current_user, name='recreo')
    data = await request.json()
    recreo.nombre = data.get('nombre', recreo.nombre)
    recreo.hora_inicio = data.get('hora_inicio', recreo.hora_inicio)
    recreo.hora_fin = data.get('hora_fin', recreo.hora_fin)
    db.commit()
    return {'message': 'Recreo actualizado'}

@app.delete("/api/recreos/{id}")
async def delete_recreo(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Eliminar recreo"""
    recreo = get_tenant_or_404(db, Recreo, id, current_user, name='recreo')
    recreo.activo = False
    db.commit()
    return {'message': 'Recreo eliminado'}

# ============== BLOQUES DE HORARIO ==============

@app.get("/api/bloques-horario")
async def get_bloques_horario(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Obtener bloques de horario por tanda"""
    tanda_id = int(request.query_params.get('tanda_id', 0) or 0)
    query = tenant_filter(db.query(BloqueHorario), BloqueHorario, current_user).filter_by(activo=True)
    if tanda_id:
        query = query.filter_by(tanda_id=tanda_id)
    bloques = query.order_by(BloqueHorario.tanda_id, BloqueHorario.numero).all()
    return [b.to_dict() for b in bloques]

@app.post("/api/bloques-horario")
async def crear_bloque_horario(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Crear un bloque de horario"""
    data = await request.json()
    bloque = BloqueHorario(
        tanda_id=data['tanda_id'],
        colegio_id=current_user.colegio_id,
        numero=data['numero'],
        hora_inicio=data['hora_inicio'],
        hora_fin=data['hora_fin'],
        duracion_minutos=data.get('duracion_minutos', 45),
        es_recreo=data.get('es_recreo', False),
        nombre=data.get('nombre')
    )
    db.add(bloque)
    db.commit()
    return JSONResponse({'message': 'Bloque creado', 'id': bloque.id}, status_code=201)

@app.put("/api/bloques-horario/{id}")
async def update_bloque_horario(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Actualizar bloque de horario"""
    bloque = get_tenant_or_404(db, BloqueHorario, id, current_user, name='bloque_horario')
    data = await request.json()
    
    for campo in ['numero', 'hora_inicio', 'hora_fin', 'duracion_minutos', 'es_recreo', 'nombre']:
        if campo in data:
            setattr(bloque, campo, data[campo])
    
    db.commit()
    return {'message': 'Bloque actualizado'}

@app.delete("/api/bloques-horario/{id}")
async def delete_bloque_horario(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Eliminar bloque de horario"""
    bloque = get_tenant_or_404(db, BloqueHorario, id, current_user, name='bloque_horario')
    bloque.activo = False
    db.commit()
    return {'message': 'Bloque eliminado'}

@app.post("/api/bloques-horario/generar/{tanda_id}")
async def generar_bloques_tanda(tanda_id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Generar bloques automáticos para una tanda"""
    tanda = get_tenant_or_404(db, Tanda, tanda_id, current_user, name='tanda')
    data = await request.json()
    
    duracion_bloque = data.get('duracion_bloque', 45)  # minutos
    duracion_recreo = data.get('duracion_recreo', 30)
    bloques_antes_recreo = data.get('bloques_antes_recreo', 3)
    
    # Eliminar bloques existentes
    tenant_filter(db.query(BloqueHorario), BloqueHorario, current_user).filter_by(tanda_id=tanda_id).delete()
    
    # Parsear hora inicio de tanda
    h, m = map(int, tanda.hora_inicio.split(':'))
    hora_actual = h * 60 + m  # en minutos
    
    h_fin, m_fin = map(int, tanda.hora_fin.split(':'))
    hora_fin = h_fin * 60 + m_fin
    
    numero = 1
    bloques_creados = 0
    
    while hora_actual + duracion_bloque <= hora_fin:
        # Crear bloque de clase
        inicio = f"{hora_actual // 60:02d}:{hora_actual % 60:02d}"
        hora_actual += duracion_bloque
        fin = f"{hora_actual // 60:02d}:{hora_actual % 60:02d}"
        
        bloque = BloqueHorario(
            tanda_id=tanda_id,
            colegio_id=current_user.colegio_id,
            numero=numero,
            hora_inicio=inicio,
            hora_fin=fin,
            duracion_minutos=duracion_bloque,
            es_recreo=False,
            nombre=f'Bloque {numero}'
        )
        db.add(bloque)
        bloques_creados += 1
        numero += 1
        
        # Agregar recreo después de X bloques
        if bloques_creados == bloques_antes_recreo and hora_actual + duracion_recreo <= hora_fin:
            inicio_recreo = fin
            hora_actual += duracion_recreo
            fin_recreo = f"{hora_actual // 60:02d}:{hora_actual % 60:02d}"
            
            recreo = BloqueHorario(
                tanda_id=tanda_id,
                colegio_id=current_user.colegio_id,
                numero=numero,
                hora_inicio=inicio_recreo,
                hora_fin=fin_recreo,
                duracion_minutos=duracion_recreo,
                es_recreo=True,
                nombre='Recreo'
            )
            db.add(recreo)
            numero += 1
    
    db.commit()
    return {'message': f'Se generaron {numero - 1} bloques para {tanda.nombre}'}

@app.get("/api/asignaturas")
async def get_asignaturas(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    asignaturas = tenant_filter(db.query(Asignatura), Asignatura, current_user).filter_by(activo=True).all()
    return [{'id': a.id, 'nombre': a.nombre, 'codigo': a.codigo, 'area': a.area} for a in asignaturas]

@app.post("/api/asignaturas")
async def crear_asignatura(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Crear asignatura. Setea colegio_id del caller."""
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({'error': 'Body inválido'}, status_code=400)
    
    if not isinstance(data, dict) or not data.get('nombre'):
        return JSONResponse({'error': 'nombre es requerido'}, status_code=400)
    
    asig = Asignatura(
        nombre=data['nombre'],
        codigo=data.get('codigo'),
        area=data.get('area'),
        colegio_id=current_user.colegio_id,
    )
    db.add(asig)
    db.commit()
    cache_clear_tenant(current_user.colegio_id)
    return JSONResponse({'message': 'Asignatura creada', 'id': asig.id}, status_code=201)


@app.put("/api/asignaturas/{id}")
async def update_asignatura(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Editar asignatura. Valida tenant."""
    asig = get_tenant_or_404(db, Asignatura, id, current_user, name='asignatura')
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({'error': 'Body inválido'}, status_code=400)
    asig.nombre = data.get('nombre', asig.nombre)
    asig.codigo = data.get('codigo', asig.codigo)
    asig.area = data.get('area', asig.area)
    db.commit()
    cache_clear_tenant(current_user.colegio_id)
    return {'message': 'Asignatura actualizada'}


@app.delete("/api/asignaturas/{id}")
async def delete_asignatura(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Soft-delete asignatura. Valida tenant."""
    asig = get_tenant_or_404(db, Asignatura, id, current_user, name='asignatura')
    asig.activo = False
    db.commit()
    cache_clear_tenant(current_user.colegio_id)
    return {'message': 'Asignatura eliminada'}

# ============== CURSOS ==============

@app.get("/api/cursos")
async def get_cursos(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    ck = f'cursos:{current_user.colegio_id}'
    cached = cache_get(ck)
    if cached: return cached
    
    cursos = tenant_filter(db.query(Curso), Curso, current_user).filter_by(activo=True).join(Grado).outerjoin(Tanda).options(
        selectinload(Curso.estudiantes), selectinload(Curso.grado), selectinload(Curso.tanda)
    ).order_by(Grado.orden, Tanda.nombre, Curso.nombre).all()
    # Normalizar nivel a valor canónico en cursos
    def _norm_nivel(raw):
        if not raw: return 'secundaria'
        low = str(raw).lower().strip()
        if low.startswith('prim'): return 'primaria'
        if low.startswith('sec'): return 'secundaria'
        if low.startswith('ini') or low.startswith('prees') or low.startswith('pre-'): return 'inicial'
        return 'secundaria'
    
    result = [{
        'id': c.id,
        'nombre': c.nombre,
        'nombre_completo': c.nombre_completo,
        'grado_id': c.grado_id,
        'grado': c.grado.nombre if c.grado else None,
        'nivel': _norm_nivel(c.grado.nivel if c.grado else None),
        'ciclo': c.grado.ciclo if c.grado else None,
        'tanda_id': c.tanda_id,
        'tanda': c.tanda.nombre if c.tanda else None,
        'capacidad': c.capacidad,
        'aula': c.aula,
        'estudiantes_count': sum(1 for e in c.estudiantes if e.activo)
    } for c in cursos]
    cache_set(ck, result, 5)
    return result

@app.post("/api/cursos")
async def crear_curso(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Crear curso. Valida que grado y tanda sean del mismo colegio."""
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({'error': 'Body inválido'}, status_code=400)
    
    if not isinstance(data, dict):
        return JSONResponse({'error': 'Body debe ser un objeto JSON'}, status_code=400)
    
    if not data.get('grado_id'):
        return JSONResponse({'error': 'Debe seleccionar un grado'}, status_code=400)
    
    # Validar tenant del grado (404 si no existe o es de otro colegio)
    grado = get_tenant_or_404(db, Grado, data['grado_id'], current_user, name='grado')
    
    # Validar que el nivel del grado esté activo en el colegio
    if grado.nivel:
        assert_nivel_activo(db, current_user, grado.nivel)
    
    # Tanda es opcional, pero si se provee debe ser del mismo colegio
    tanda = None
    if data.get('tanda_id'):
        tanda = get_tenant_or_404(db, Tanda, data['tanda_id'], current_user, name='tanda')
    
    ano_activo = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    
    # Aceptar 'nombre' o 'seccion' del frontend
    seccion = data.get('nombre') or data.get('seccion') or 'A'
    
    # Validar capacidad
    capacidad = data.get('capacidad', 35)
    try:
        capacidad = int(capacidad)
        if capacidad < 1 or capacidad > 200:
            return JSONResponse({'error': 'capacidad fuera de rango (1-200)'}, status_code=400)
    except (ValueError, TypeError):
        return JSONResponse({'error': 'capacidad inválida'}, status_code=400)
    
    curso = Curso(
        nombre=seccion,
        grado_id=grado.id,
        tanda_id=tanda.id if tanda else None,
        ano_escolar_id=ano_activo.id if ano_activo else None,
        capacidad=capacidad,
        aula=data.get('aula'),
        colegio_id=current_user.colegio_id,
    )
    db.add(curso)
    db.commit()
    log_auditoria(db, 'crear', 'cursos', curso.id, None, data, user=current_user, request=request)
    cache_clear(f'cursos:{current_user.colegio_id}')
    cache_clear(f'stats:{current_user.colegio_id}')
    return JSONResponse({'message': 'Curso creado', 'id': curso.id}, status_code=201)


@app.put("/api/cursos/{id}")
async def update_curso(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Editar curso. Valida tenant del curso y de los nuevos FK."""
    curso = get_tenant_or_404(db, Curso, id, current_user, name='curso')
    
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({'error': 'Body inválido'}, status_code=400)
    
    # Aceptar 'nombre' o 'seccion'
    if 'seccion' in data:
        curso.nombre = data['seccion']
    elif 'nombre' in data:
        curso.nombre = data['nombre']
    
    if 'grado_id' in data and data['grado_id'] is not None:
        grado = get_tenant_or_404(db, Grado, data['grado_id'], current_user, name='grado')
        curso.grado_id = grado.id
    
    if 'tanda_id' in data:
        if data['tanda_id']:
            tanda = get_tenant_or_404(db, Tanda, data['tanda_id'], current_user, name='tanda')
            curso.tanda_id = tanda.id
        else:
            curso.tanda_id = None
    
    if 'capacidad' in data:
        try:
            cap = int(data['capacidad'])
            if cap < 1 or cap > 200:
                return JSONResponse({'error': 'capacidad fuera de rango (1-200)'}, status_code=400)
            curso.capacidad = cap
        except (ValueError, TypeError):
            return JSONResponse({'error': 'capacidad inválida'}, status_code=400)
    
    if 'aula' in data:
        curso.aula = data['aula']
    
    db.commit()
    log_auditoria(db, 'actualizar', 'cursos', curso.id, None, data, user=current_user, request=request)
    cache_clear(f'cursos:{current_user.colegio_id}')
    return {'message': 'Curso actualizado'}


@app.delete("/api/cursos/{id}")
async def delete_curso(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Soft-delete del curso (marca activo=False). Valida tenant."""
    curso = get_tenant_or_404(db, Curso, id, current_user, name='curso')
    curso.activo = False
    db.commit()
    cache_clear(f'cursos:{current_user.colegio_id}')
    return {'message': 'Curso eliminado'}

# ============== USUARIOS ==============

@app.get("/api/usuarios")
async def get_usuarios(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    usuarios = tenant_filter(db.query(Usuario), Usuario, current_user).filter_by(activo=True).all()
    return [u.to_dict() for u in usuarios]

@app.get("/api/usuarios/{id}")
async def get_usuario(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    usuario = get_tenant_or_404(db, Usuario, id, current_user, name='usuario')
    return usuario.to_dict()

@app.post("/api/usuarios")
async def crear_usuario(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    data = await request.json()
    
    # Verificar límite del plan
    if current_user.colegio_id:
        colegio = db.get(Colegio, current_user.colegio_id)
        if colegio and colegio.max_usuarios:
            count = tenant_filter(db.query(func.count(Usuario.id)), Usuario, current_user).filter(Usuario.activo == True).scalar() or 0
            if count >= colegio.max_usuarios:
                return JSONResponse({
                    'error': f'Límite de usuarios alcanzado ({colegio.max_usuarios}). Actualice su plan para agregar más.'
                }, status_code=403)
    
    # Validaciones requeridas
    if not data.get('username') or not data.get('nombre') or not data.get('role'):
        return JSONResponse({'error': 'Username, nombre y rol son requeridos'}, status_code=400)
    
    # Sanitizar inputs
    username = data['username'].strip().lower()[:50]
    nombre = data['nombre'].strip()[:100]
    apellido = (data.get('apellido') or '').strip()[:100]
    email = (data.get('email') or '').strip().lower()[:100]
    telefono = (data.get('telefono') or '').strip()[:20]
    cedula = (data.get('cedula') or '').strip()[:20]
    role = data['role'].strip().lower()
    
    # Validar username (solo alfanumérico y guiones)
    if not re.match(r'^[a-z0-9_-]+$', username):
        return JSONResponse({'error': 'Username solo puede contener letras, números, guiones y guiones bajos'}, status_code=400)
    
    # Validar rol
    roles_validos = ['direccion', 'coordinador', 'profesor', 'psicologia', 'secretaria']
    if role not in roles_validos:
        return JSONResponse({'error': f'Rol inválido. Opciones: {", ".join(roles_validos)}'}, status_code=400)
    
    # Validar email si se proporciona
    if email and not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        return JSONResponse({'error': 'Formato de email inválido'}, status_code=400)
    
    # Validar contraseña.
    # Si el caller no provee password, generamos una fuerte y forzamos
    # cambio al primer login del usuario (must_change_password=True).
    # Si el caller la provee, asumimos que ya la coordinó por canal seguro
    # con el usuario; pero igualmente exigimos longitud mínima 8.
    password_provista = (data.get('password') or '').strip()
    must_change = False
    if password_provista:
        password = password_provista
        # Usa validación centralizada en security.py (mín 8, mayús, minús, número)
        from security import validate_password
        ok, msg = validate_password(password)
        if not ok:
            return JSONResponse({'error': msg}, status_code=400)
    else:
        from models import _generar_password_inicial
        password = _generar_password_inicial()
        must_change = True
    
    if db.query(Usuario).filter_by(username=username).first():
        return JSONResponse({'error': 'El usuario ya existe'}, status_code=400)
    
    usuario = Usuario(
        username=username,
        nombre=nombre,
        apellido=apellido or None,
        email=email or None,
        telefono=telefono or None,
        cedula=cedula or None,
        role=role,
        tanda_id=data.get('tanda_id') or None,
        colegio_id=current_user.colegio_id,
        must_change_password=must_change,
    )
    usuario.set_password(password)
    db.add(usuario)
    db.commit()
    
    log_auditoria(db, 'crear', 'usuarios', usuario.id, None, usuario.to_dict(), user=current_user, request=request)
    db.commit()
    
    logger.info(f'Usuario creado: {username} por {current_user.username}')
    
    response_body = {'message': 'Usuario creado', 'id': usuario.id, 'must_change_password': must_change}
    # Si la password fue generada, devolverla UNA SOLA VEZ al admin para que
    # se la pase al usuario por canal seguro. Si fue provista, no la repetimos.
    if not password_provista:
        response_body['password_temporal'] = password
    
    return JSONResponse(response_body, status_code=201)

@app.put("/api/usuarios/{id}")
async def update_usuario(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    usuario = get_tenant_or_404(db, Usuario, id, current_user, name='usuario')
    data = await request.json()
    
    datos_anteriores = usuario.to_dict()
    
    # SEGURIDAD: el campo 'role' se valida ANTES del setattr para prevenir
    # escalación de privilegios. Sin esta validación, un director podía
    # cambiar el rol de cualquier usuario a 'superadmin' simplemente enviando
    # PUT /api/usuarios/{id} con {"role": "superadmin"}, y ese usuario
    # quedaba con acceso a TODOS los colegios. CVE-style vulnerability.
    if 'role' in data:
        ROLES_PERMITIDOS_PARA_DIRECCION = {'coordinador', 'profesor', 'psicologia', 'secretaria', 'direccion'}
        if data['role'] not in ROLES_PERMITIDOS_PARA_DIRECCION:
            return JSONResponse(
                {'error': f'Rol no permitido: {data["role"]!r}. '
                          f'Roles válidos: {sorted(ROLES_PERMITIDOS_PARA_DIRECCION)}'},
                status_code=400
            )
    
    # Bloquear cambio de colegio_id desde este endpoint — solo superadmin
    # puede mover usuarios entre colegios, y para eso hay otro endpoint.
    if 'colegio_id' in data:
        data.pop('colegio_id')
    
    # Cambio de username: permitido, pero validando que sea único y no vacío.
    # El username es el identificador de login, así que no puede repetirse.
    if 'username' in data:
        nuevo_username = (data['username'] or '').strip()
        if not nuevo_username:
            return JSONResponse({'error': 'El nombre de usuario no puede estar vacío'}, status_code=400)
        # ¿Existe ya OTRO usuario con ese username? (el username es global)
        existe = db.query(Usuario).filter(
            Usuario.username == nuevo_username,
            Usuario.id != usuario.id
        ).first()
        if existe:
            return JSONResponse({'error': f'El nombre de usuario "{nuevo_username}" ya está en uso'}, status_code=400)
        usuario.username = nuevo_username

    # Lista blanca de campos editables (ya no incluye 'role' acá; se setea aparte)
    for campo in ['nombre', 'apellido', 'email', 'telefono', 'cedula', 'tanda_id']:
        if campo in data:
            setattr(usuario, campo, data[campo] if data[campo] else None)
    
    # Setear role solo si pasó la validación
    if 'role' in data:
        usuario.role = data['role']
    
    if data.get('password'):
        usuario.set_password(data['password'])
    
    log_auditoria(db, 'editar', 'usuarios', usuario.id, datos_anteriores, usuario.to_dict(), user=current_user, request=request)
    db.commit()
    
    return {'message': 'Usuario actualizado'}

@app.delete("/api/usuarios/{id}")
async def delete_usuario(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    usuario = get_tenant_or_404(db, Usuario, id, current_user, name='usuario')
    usuario.activo = False
    log_auditoria(db, 'eliminar', 'usuarios', usuario.id, usuario.to_dict(), None, user=current_user, request=request)
    db.commit()
    return {'message': 'Usuario desactivado'}


@app.post("/api/usuarios/{id}/reset-password")
async def reset_password_usuario(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Resetear contraseña de un usuario (solo dirección).
    
    El usuario reseteado queda con must_change_password=True y debe cambiar
    la password al primer login. La password temporal se devuelve al admin
    una sola vez para que se la pase al usuario por canal seguro.
    """
    usuario = get_tenant_or_404(db, Usuario, id, current_user, name='usuario')
    data = await request.json() or {}
    
    # Nueva contraseña o generar una temporal fuerte
    nueva_password = data.get('password')
    
    if not nueva_password:
        # Password aleatoria fuerte (cumple validador del endpoint /cambiar-password)
        from models import _generar_password_inicial
        nueva_password = _generar_password_inicial()
    
    usuario.set_password(nueva_password)
    usuario.must_change_password = True  # forzar cambio al primer login
    log_auditoria(db, 'reset_password', 'usuarios', usuario.id, None, {'reseteado_por': current_user.id}, user=current_user, request=request)
    db.commit()
    
    return {
        'message': f'Contraseña reseteada para {usuario.nombre_completo}',
        'password_temporal': nueva_password,
        'usuario': usuario.username,
        'must_change_password': True,
    }

@app.get("/api/profesores")
async def get_profesores(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    profesores = tenant_filter(db.query(Usuario), Usuario, current_user).filter_by(role='profesor', activo=True).all()
    return [{'id': p.id, 'nombre_completo': p.nombre_completo, 'email': p.email} for p in profesores]

# ============== PERFIL ==============

@app.put("/api/perfil")
async def update_perfil(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    data = await request.json()
    for campo in ['nombre', 'apellido', 'email', 'telefono']:
        if campo in data:
            setattr(current_user, campo, data[campo])
    db.commit()
    return {'message': 'Perfil actualizado', 'user': current_user.to_dict()}

# ============== ESTUDIANTES ==============

@app.get("/api/estudiantes")
async def get_estudiantes(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    # Por default solo activos. Si dirección/coordinador pasan ?incluir_retirados=true,
    # devuelve también los retirados (con flag fecha_retiro/motivo_retiro en to_dict).
    incluir_retirados = (request.query_params.get('incluir_retirados') or '').lower() in ('true', '1', 'yes')
    
    query = tenant_filter(db.query(Estudiante), Estudiante, current_user).options(
        joinedload(Estudiante.curso).joinedload(Curso.grado),
        joinedload(Estudiante.curso).joinedload(Curso.tanda)
    )
    
    if not incluir_retirados:
        query = query.filter_by(activo=True)
    # Si incluir_retirados=true, NO filtramos por activo. Solo direccion/coordinador
    # tienen el toggle en UI; un profesor verá retirados solo si los pide explícito.
    
    if request.query_params.get('curso_id'):
        query = query.filter_by(curso_id=int(request.query_params.get('curso_id')))
    
    # Filtrar por cursos del profesor si no es direccion/coordinador
    if current_user.role == 'profesor':
        asignaciones = tenant_filter(db.query(AsignacionProfesor), AsignacionProfesor, current_user).filter_by(profesor_id=current_user.id).all()
        cursos_ids = list(set([a.curso_id for a in asignaciones]))
        query = query.filter(Estudiante.curso_id.in_(cursos_ids))
    
    query = query.order_by(Estudiante.no_lista)
    # v2.13.30: paginación opcional. Sin ?page devuelve todo (retrocompatible).
    pag = paginar_query(query, request)
    if pag is None:
        return [e.to_dict() for e in query.all()]
    return {**pag, 'items': [e.to_dict() for e in pag['items']]}

@app.get("/api/estudiantes/retirados")
async def get_estudiantes_retirados(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    estudiantes = tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(activo=False).all()
    return [e.to_dict() for e in estudiantes]

@app.delete("/api/estudiantes/retirados/eliminar-todos")
async def eliminar_retirados(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Eliminar permanentemente TODOS los estudiantes retirados y sus datos relacionados"""
    retirados = tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(activo=False).all()
    if not retirados:
        return {'message': 'No hay estudiantes retirados', 'eliminados': 0}
    
    ids = [e.id for e in retirados]
    
    # Borrar datos relacionados
    for model in [Calificacion, Asistencia, ReporteConducta, CasoPsicologia, 
                  HistorialAcademico, EvalInternaEstudiante]:
        db.query(model).filter(model.estudiante_id.in_(ids)).delete(synchronize_session=False)
    
    # Borrar estudiantes
    count = len(ids)
    for est in retirados:
        db.delete(est)
    
    db.commit()
    
    log_auditoria(db, 'ELIMINAR_RETIRADOS', 'estudiantes', None, None,
                  {'cantidad': count, 'ids': ids}, user=current_user, request=request)
    db.commit()  # v2.13.5: persistir log
    
    return {'message': f'{count} estudiantes retirados eliminados permanentemente', 'eliminados': count}

@app.delete("/api/estudiantes/retirados/{id}")
async def eliminar_retirado(id: int, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Eliminar permanentemente UN estudiante retirado y sus datos relacionados"""
    est = tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(id=id, activo=False).first()
    if not est:
        return JSONResponse({'error': 'Estudiante retirado no encontrado'}, status_code=404)
    
    nombre = est.nombre_completo
    
    for model in [Calificacion, Asistencia, ReporteConducta, CasoPsicologia,
                  HistorialAcademico, EvalInternaEstudiante]:
        db.query(model).filter(model.estudiante_id == id).delete(synchronize_session=False)
    
    db.delete(est)
    db.commit()
    
    log_auditoria(db, 'ELIMINAR_RETIRADO', 'estudiantes', id, None,
                  {'nombre': nombre}, user=current_user, request=request)
    db.commit()  # v2.13.5: persistir log
    
    return {'message': f'Estudiante {nombre} eliminado permanentemente'}

@app.get("/api/estudiantes/{id}")
async def get_estudiante(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Obtener estudiante por ID. Valida tenant."""
    est = get_tenant_or_404(db, Estudiante, id, current_user, name='estudiante')
    return est.to_dict()


@app.post("/api/estudiantes")
async def crear_estudiante(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion', 'coordinador'))):
    """Crear estudiante. Valida que curso (si se provee) sea del mismo colegio."""
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({'error': 'Body inválido'}, status_code=400)
    
    if not isinstance(data, dict):
        return JSONResponse({'error': 'Body debe ser un objeto JSON'}, status_code=400)
    
    # Validar nombre/apellido — strip() previene "nombres" que son solo espacios
    nombre = (data.get('nombre') or '').strip()
    apellido = (data.get('apellido') or '').strip()
    if not nombre or not apellido:
        return JSONResponse({'error': 'nombre y apellido son requeridos (no pueden ser vacíos)'}, status_code=400)
    if len(nombre) > 100 or len(apellido) > 100:
        return JSONResponse({'error': 'nombre y apellido no pueden tener más de 100 caracteres'}, status_code=400)
    # Reasignar al data limpiado
    data['nombre'] = nombre
    data['apellido'] = apellido
    
    # Verificar límite del plan
    if current_user.colegio_id:
        colegio = db.get(Colegio, current_user.colegio_id)
        if colegio and colegio.max_estudiantes:
            count = tenant_filter(db.query(func.count(Estudiante.id)), Estudiante, current_user).filter(Estudiante.activo == True).scalar() or 0
            if count >= colegio.max_estudiantes:
                return JSONResponse({
                    'error': f'Límite de estudiantes alcanzado ({colegio.max_estudiantes}). Actualice su plan para agregar más.'
                }, status_code=403)
    
    # Validar tenant del curso (si se provee)
    curso_id = None
    if data.get('curso_id'):
        curso = get_tenant_or_404(db, Curso, data['curso_id'], current_user, name='curso')
        curso_id = curso.id
        # Validar que el nivel del curso esté activo (plan AND uso). Si no,
        # bloquear: no tiene sentido cargar estudiantes en un nivel que el
        # colegio no opera.
        assert_nivel_curso_activo(db, current_user, curso.id)
    
    # Parsear fecha_nacimiento con manejo de error explícito
    fecha_nac = None
    if data.get('fecha_nacimiento'):
        try:
            fecha_nac = datetime.strptime(data['fecha_nacimiento'], '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return JSONResponse(
                {'error': f"fecha_nacimiento inválida: {data.get('fecha_nacimiento')!r}. Formato esperado YYYY-MM-DD"},
                status_code=400
            )
        # Validar rango razonable: nadie tiene más de 100 años ni nace en el futuro.
        # Para colegio se espera entre 3 y 25 años, pero damos margen amplio.
        hoy = today_rd()
        edad_aprox = (hoy - fecha_nac).days / 365.25
        if edad_aprox < 0:
            return JSONResponse(
                {'error': 'fecha_nacimiento no puede ser en el futuro'},
                status_code=400
            )
        if edad_aprox > 100:
            return JSONResponse(
                {'error': 'fecha_nacimiento parece incorrecta (más de 100 años de edad)'},
                status_code=400
            )
    
    est = Estudiante(
        # Datos personales (los 13 que tenía + nuevos)
        nombre=data['nombre'],
        apellido=data['apellido'],
        matricula=data.get('matricula'),
        sexo=data.get('sexo'),
        fecha_nacimiento=fecha_nac,
        lugar_nacimiento=data.get('lugar_nacimiento'),
        nacionalidad=data.get('nacionalidad') or 'Dominicana',
        cedula=data.get('cedula'),
        # Académico
        curso_id=curso_id,
        no_lista=data.get('no_lista'),
        condicion_entrada=data.get('condicion_entrada') or 'nuevo',
        escuela_procedencia=data.get('escuela_procedencia'),
        # Contacto del estudiante
        direccion=data.get('direccion'),
        telefono=data.get('telefono'),
        email=data.get('email'),
        # Padres
        nombre_padre=data.get('nombre_padre'),
        cedula_padre=data.get('cedula_padre'),
        telefono_padre=data.get('telefono_padre'),
        trabajo_padre=data.get('trabajo_padre'),
        nombre_madre=data.get('nombre_madre'),
        cedula_madre=data.get('cedula_madre'),
        telefono_madre=data.get('telefono_madre'),
        trabajo_madre=data.get('trabajo_madre'),
        # Tutor
        tutor=data.get('tutor'),
        telefono_tutor=data.get('telefono_tutor'),
        parentesco_tutor=data.get('parentesco_tutor'),
        # Salud y emergencia
        contacto_emergencia=data.get('contacto_emergencia'),
        telefono_emergencia=data.get('telefono_emergencia'),
        nee=data.get('nee'),
        tipo_sangre=data.get('tipo_sangre'),
        alergias=data.get('alergias'),
        condiciones_medicas=data.get('condiciones_medicas'),
        seguro_medico=data.get('seguro_medico'),
        # Tenant
        colegio_id=current_user.colegio_id
    )
    db.add(est)
    db.commit()
    
    cache_clear_tenant(current_user.colegio_id)
    log_auditoria(db, 'crear', 'estudiantes', est.id, None, est.to_dict(), user=current_user, request=request)
    db.commit()
    
    cache_clear(f'cursos:{current_user.colegio_id}')
    cache_clear(f'stats:{current_user.colegio_id}')
    return JSONResponse({'message': 'Estudiante creado', 'id': est.id}, status_code=201)


@app.put("/api/estudiantes/{id}")
async def update_estudiante(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion', 'coordinador'))):
    """Editar estudiante. Valida tenant del estudiante y del nuevo curso si cambia."""
    est = get_tenant_or_404(db, Estudiante, id, current_user, name='estudiante')
    
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({'error': 'Body inválido'}, status_code=400)
    
    if not isinstance(data, dict):
        return JSONResponse({'error': 'Body debe ser un objeto JSON'}, status_code=400)
    
    datos_anteriores = est.to_dict()
    
    # Validar tenant del nuevo curso si cambia
    if 'curso_id' in data and data['curso_id'] is not None:
        curso = get_tenant_or_404(db, Curso, data['curso_id'], current_user, name='curso')
        # Validar nivel del curso destino activo
        assert_nivel_curso_activo(db, current_user, curso.id)
        est.curso_id = curso.id
    elif 'curso_id' in data and data['curso_id'] is None:
        est.curso_id = None
    
    campos = ['nombre', 'apellido', 'matricula', 'sexo', 'no_lista',
              'direccion', 'telefono', 'email', 'condicion',
              'nombre_padre', 'cedula_padre', 'telefono_padre', 'trabajo_padre',
              'nombre_madre', 'cedula_madre', 'telefono_madre', 'trabajo_madre',
              'tutor', 'telefono_tutor', 'parentesco_tutor',
              'cedula', 'condicion_entrada', 'escuela_procedencia',
              'contacto_emergencia', 'telefono_emergencia', 'nee',
              'lugar_nacimiento', 'nacionalidad',
              'tipo_sangre', 'alergias', 'condiciones_medicas', 'seguro_medico']
    
    for campo in campos:
        if campo in data:
            setattr(est, campo, data[campo])
    
    if 'fecha_nacimiento' in data and data['fecha_nacimiento']:
        try:
            est.fecha_nacimiento = datetime.strptime(data['fecha_nacimiento'], '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return JSONResponse(
                {'error': f"fecha_nacimiento inválida. Formato esperado YYYY-MM-DD"},
                status_code=400
            )
    
    log_auditoria(db, 'editar', 'estudiantes', est.id, datos_anteriores, est.to_dict(), user=current_user, request=request)
    db.commit()
    
    cache_clear(f'cursos:{current_user.colegio_id}')
    cache_clear_tenant(current_user.colegio_id)
    return {'message': 'Estudiante actualizado'}


@app.delete("/api/estudiantes/{id}")
async def delete_estudiante(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Soft-delete (retiro) del estudiante. Valida tenant.
    Acepta body opcional con {motivo_retiro: str} para registrar la razón.
    Setea fecha_retiro=hoy y retirado_por=usuario actual automáticamente."""
    est = get_tenant_or_404(db, Estudiante, id, current_user, name='estudiante')
    
    # Body opcional con motivo
    motivo = None
    try:
        data = await request.json()
        if isinstance(data, dict):
            motivo = data.get('motivo_retiro')
    except Exception:
        pass  # body vacío es OK — retiro sin motivo
    
    est.activo = False
    est.condicion = 'retirado'  # canónico minúsculas
    est.fecha_retiro = today_rd()
    est.motivo_retiro = motivo
    est.retirado_por = current_user.id
    
    log_auditoria(db, 'retirar', 'estudiantes', est.id, est.to_dict(), None, user=current_user, request=request)
    db.commit()
    cache_clear_tenant(current_user.colegio_id)
    return {'message': 'Estudiante retirado', 'fecha_retiro': est.fecha_retiro.isoformat()}


@app.post("/api/estudiantes/{id}/reactivar")
async def reactivar_estudiante(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Reactivar estudiante retirado. Limpia fecha_retiro, motivo y retirado_por.
    Valida tenant."""
    est = get_tenant_or_404(db, Estudiante, id, current_user, name='estudiante')
    est.activo = True
    est.condicion = 'activo'
    est.fecha_retiro = None
    est.motivo_retiro = None
    est.retirado_por = None
    log_auditoria(db, 'reactivar', 'estudiantes', est.id, None, est.to_dict(), user=current_user, request=request)
    db.commit()
    cache_clear_tenant(current_user.colegio_id)
    return {'message': 'Estudiante reactivado'}

@app.post("/api/estudiantes/importar")
async def importar_estudiantes(request: Request, archivo: UploadFile = File(...), curso_id: int = Form(...), db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion', 'coordinador'))):
    """Importar estudiantes desde archivo CSV"""
    
    if not archivo or not archivo.filename.endswith('.csv'):
        return JSONResponse({'error': 'El archivo debe ser CSV'}, status_code=400)
    
    if not curso_id:
        return JSONResponse({'error': 'Debe seleccionar un curso'}, status_code=400)
    
    # Verificar límite del plan
    if current_user.colegio_id:
        colegio = db.get(Colegio, current_user.colegio_id)
        if colegio and colegio.max_estudiantes:
            count_actual = tenant_filter(db.query(func.count(Estudiante.id)), Estudiante, current_user).filter(Estudiante.activo == True).scalar() or 0
            if count_actual >= colegio.max_estudiantes:
                return JSONResponse({
                    'error': f'Límite de estudiantes alcanzado ({colegio.max_estudiantes}). Actualice su plan.'
                }, status_code=403)
    
    # Verificar que el curso existe Y pertenece al colegio del usuario.
    # ANTES usaba db.get(Curso, curso_id) sin validar colegio, lo cual
    # permitía a un director importar estudiantes a un curso de OTRO colegio.
    # Bug confirmado por pentest. Fix: get_tenant_or_404 valida ambos.
    curso = get_tenant_or_404(db, Curso, curso_id, current_user, name='curso')
    
    try:
        file_content = await archivo.read()
        stream = io.StringIO(file_content.decode('utf-8-sig'))
        reader = csv.DictReader(stream)
        
        count = 0
        errores = []
        for i, row in enumerate(reader, start=2):
            if not row.get('nombre') or not row.get('apellido'):
                errores.append(f"Fila {i}: nombre y apellido son requeridos")
                continue
            
            est = Estudiante(
                matricula=row.get('matricula') or None,
                no_lista=int(row.get('no_lista')) if row.get('no_lista') else None,
                nombre=row.get('nombre').strip(),
                apellido=row.get('apellido').strip(),
                sexo=row.get('genero', 'M')[0].upper() if row.get('genero') else 'M',
                curso_id=curso_id,
                condicion=row.get('condicion') or 'Nuevo',
                activo=True,
                colegio_id=current_user.colegio_id
            )
            db.add(est)
            count += 1
        
        db.commit()
        log_auditoria(db, 'importar', 'estudiantes', None, None, {'cantidad': count, 'curso_id': curso_id}, user=current_user, request=request)
        db.commit()  # v2.13.5: persistir log
        
        return {
            'message': f'{count} estudiantes importados correctamente',
            'importados': count,
            'errores': errores
        }
    except Exception as e:
        db.rollback()
        return JSONResponse({'error': f'Error al procesar archivo: {str(e)}'}, status_code=400)

# ============== ASIGNACIONES ==============

@app.get("/api/asignaciones")
async def get_asignaciones(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    if current_user.role == 'profesor':
        asigs = tenant_filter(db.query(AsignacionProfesor), AsignacionProfesor, current_user).filter_by(profesor_id=current_user.id).all()
    else:
        asigs = tenant_filter(db.query(AsignacionProfesor), AsignacionProfesor, current_user).all()
    return [a.to_dict() for a in asigs]


@app.post("/api/asignaciones")
async def crear_asignacion(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Asignar profesor a (curso, asignatura). Valida que TODOS los FK sean del mismo colegio."""
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({'error': 'Body inválido (se espera JSON)'}, status_code=400)
    
    if not isinstance(data, dict):
        return JSONResponse({'error': 'Body debe ser un objeto JSON'}, status_code=400)
    
    # Validar tenant de los 3 FK (raises 404 si no existe o es de otro colegio)
    profesor = get_tenant_or_404(db, Usuario, data.get('profesor_id'), current_user, name='profesor')
    curso = get_tenant_or_404(db, Curso, data.get('curso_id'), current_user, name='curso')
    asignatura = get_tenant_or_404(db, Asignatura, data.get('asignatura_id'), current_user, name='asignatura')
    
    # Validar que el nivel del curso esté activo
    assert_nivel_curso_activo(db, current_user, curso.id)
    
    if profesor.role != 'profesor':
        return JSONResponse({'error': 'profesor_id no corresponde a un usuario con rol profesor'}, status_code=400)
    
    # Verificar duplicado
    existe = tenant_filter(db.query(AsignacionProfesor), AsignacionProfesor, current_user).filter_by(
        profesor_id=profesor.id,
        curso_id=curso.id,
        asignatura_id=asignatura.id,
    ).first()
    if existe:
        return JSONResponse({'error': 'Esta asignación ya existe', 'id': existe.id}, status_code=400)
    
    ano_activo = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    asig = AsignacionProfesor(
        profesor_id=profesor.id,
        curso_id=curso.id,
        asignatura_id=asignatura.id,
        ano_escolar_id=ano_activo.id if ano_activo else None,
        colegio_id=current_user.colegio_id,
        es_titular=bool(data.get('es_titular', False)),
        activo=True,
    )
    db.add(asig)
    db.commit()
    cache_clear_tenant(current_user.colegio_id)
    return JSONResponse(
        {'message': 'Asignación creada', 'id': asig.id, 'asignacion': asig.to_dict()},
        status_code=201
    )


@app.delete("/api/asignaciones/{id}")
async def delete_asignacion(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Eliminar asignación. Valida tenant antes de borrar."""
    asig = get_tenant_or_404(db, AsignacionProfesor, id, current_user, name='asignación')
    db.delete(asig)
    db.commit()
    cache_clear_tenant(current_user.colegio_id)
    return {'message': 'Asignación eliminada'}

# ============== HORARIOS ==============

@app.get("/api/horarios")
async def get_horarios(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    horarios = tenant_filter(db.query(Horario), Horario, current_user).all()
    return [h.to_dict() for h in horarios]

@app.get("/api/horarios/profesor/{id}")
async def get_horarios_profesor(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    # Validar que el profesor pertenezca al mismo colegio (404 si no)
    get_tenant_or_404(db, Usuario, id, current_user, name='profesor')
    horarios = tenant_filter(db.query(Horario), Horario, current_user).filter_by(profesor_id=id).order_by(Horario.dia, Horario.hora_inicio).all()
    return [h.to_dict() for h in horarios]

@app.get("/api/horarios/curso/{id}")
async def get_horarios_curso(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    # Validar que el curso pertenezca al mismo colegio (404 si no)
    get_tenant_or_404(db, Curso, id, current_user, name='curso')
    horarios = tenant_filter(db.query(Horario), Horario, current_user).filter_by(curso_id=id).order_by(Horario.dia, Horario.hora_inicio).all()
    return [h.to_dict() for h in horarios]

@app.get("/api/horarios/mi-horario-hoy")
async def get_mi_horario_hoy(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    dias = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
    dia_hoy = dias[today_rd().weekday()]
    
    horarios = tenant_filter(db.query(Horario), Horario, current_user).filter_by(
        profesor_id=current_user.id,
        dia=dia_hoy
    ).order_by(Horario.hora_inicio).all()
    
    return [h.to_dict() for h in horarios]


# Días válidos para horarios (acepta con/sin acento, case-insensitive en input)
_DIAS_VALIDOS = {'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'}
_DIAS_NORM = {  # mapeo de variantes → forma canónica
    'lunes': 'Lunes', 'martes': 'Martes', 'miercoles': 'Miércoles', 'miércoles': 'Miércoles',
    'jueves': 'Jueves', 'viernes': 'Viernes', 'sabado': 'Sábado', 'sábado': 'Sábado',
    'domingo': 'Domingo',
}
_TIPOS_BLOQUE_VALIDOS = {'clase', 'libre', 'recreo'}


def _validar_dia(dia: str):
    """Normaliza y valida el día. Levanta HTTPException si es inválido."""
    if not dia or not isinstance(dia, str):
        raise HTTPException(status_code=400, detail='dia es requerido')
    norm = _DIAS_NORM.get(dia.strip().lower())
    if not norm:
        raise HTTPException(
            status_code=400,
            detail=f'dia inválido: {dia!r}. Valores válidos: {sorted(_DIAS_VALIDOS)}'
        )
    return norm


def _validar_hora(valor: str, campo: str):
    """Valida formato HH:MM (24h). Levanta HTTPException si es inválido."""
    import re as _re
    if not valor or not isinstance(valor, str):
        raise HTTPException(status_code=400, detail=f'{campo} es requerido')
    # Aceptar HH:MM o HH:MM:SS, normalizar a HH:MM
    m = _re.match(r'^(\d{1,2}):(\d{2})(?::\d{2})?$', valor.strip())
    if not m:
        raise HTTPException(status_code=400, detail=f'{campo} inválido: {valor!r}. Formato esperado HH:MM')
    h, mi = int(m.group(1)), int(m.group(2))
    if not (0 <= h <= 23 and 0 <= mi <= 59):
        raise HTTPException(status_code=400, detail=f'{campo} fuera de rango: {valor!r}')
    return f"{h:02d}:{mi:02d}"


@app.post("/api/horarios")
async def crear_horario(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Crear horario. Valida que curso, asignatura y profesor pertenezcan al colegio del caller."""
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({'error': 'Body inválido (se espera JSON)'}, status_code=400)
    
    if not isinstance(data, dict):
        return JSONResponse({'error': 'Body debe ser un objeto JSON'}, status_code=400)
    
    # Validar tipo_bloque
    tipo_bloque = (data.get('tipo_bloque') or 'clase').strip().lower()
    if tipo_bloque not in _TIPOS_BLOQUE_VALIDOS:
        return JSONResponse(
            {'error': f'tipo_bloque inválido: {tipo_bloque!r}. Valores válidos: {sorted(_TIPOS_BLOQUE_VALIDOS)}'},
            status_code=400
        )
    
    # Validar dia y horas (raises HTTPException 400 si inválidos)
    dia = _validar_dia(data.get('dia'))
    hora_inicio = _validar_hora(data.get('hora_inicio'), 'hora_inicio')
    hora_fin = _validar_hora(data.get('hora_fin'), 'hora_fin')
    if hora_inicio >= hora_fin:
        return JSONResponse({'error': 'hora_fin debe ser mayor que hora_inicio'}, status_code=400)
    
    # Profesor: requerido siempre, debe ser del mismo colegio
    profesor = get_tenant_or_404(db, Usuario, data.get('profesor_id'), current_user, name='profesor')
    if profesor.role != 'profesor':
        return JSONResponse({'error': 'profesor_id no corresponde a un usuario con rol profesor'}, status_code=400)
    
    # Curso y asignatura: solo requeridos para tipo 'clase', y deben ser del mismo colegio
    curso_id = None
    asignatura_id = None
    if tipo_bloque == 'clase':
        curso = get_tenant_or_404(db, Curso, data.get('curso_id'), current_user, name='curso')
        asignatura = get_tenant_or_404(db, Asignatura, data.get('asignatura_id'), current_user, name='asignatura')
        # Validar que el nivel del curso esté activo
        assert_nivel_curso_activo(db, current_user, curso.id)
        curso_id = curso.id
        asignatura_id = asignatura.id
    
    horario = Horario(
        profesor_id=profesor.id,
        colegio_id=current_user.colegio_id,
        curso_id=curso_id,
        asignatura_id=asignatura_id,
        dia=dia,
        hora_inicio=hora_inicio,
        hora_fin=hora_fin,
        aula=(data.get('aula') or None),
        tipo_bloque=tipo_bloque,
    )
    db.add(horario)
    db.commit()
    cache_clear_tenant(current_user.colegio_id)
    return JSONResponse({'message': 'Horario creado', 'id': horario.id, 'horario': horario.to_dict()}, status_code=201)


@app.put("/api/horarios/{id}")
async def update_horario(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Editar un horario existente. Valida tenant del horario y de los nuevos FK."""
    # Validar que el horario sea del colegio del caller
    horario = get_tenant_or_404(db, Horario, id, current_user, name='horario')
    
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({'error': 'Body inválido (se espera JSON)'}, status_code=400)
    
    if not isinstance(data, dict):
        return JSONResponse({'error': 'Body debe ser un objeto JSON'}, status_code=400)
    
    # Tipo bloque
    if 'tipo_bloque' in data:
        nuevo_tipo = (data['tipo_bloque'] or '').strip().lower()
        if nuevo_tipo not in _TIPOS_BLOQUE_VALIDOS:
            return JSONResponse(
                {'error': f'tipo_bloque inválido: {nuevo_tipo!r}. Valores válidos: {sorted(_TIPOS_BLOQUE_VALIDOS)}'},
                status_code=400
            )
        horario.tipo_bloque = nuevo_tipo
        if nuevo_tipo in ('libre', 'recreo'):
            horario.curso_id = None
            horario.asignatura_id = None
    
    # Profesor (validar tenant)
    if 'profesor_id' in data and data['profesor_id'] is not None:
        profesor = get_tenant_or_404(db, Usuario, data['profesor_id'], current_user, name='profesor')
        if profesor.role != 'profesor':
            return JSONResponse({'error': 'profesor_id no corresponde a un usuario con rol profesor'}, status_code=400)
        horario.profesor_id = profesor.id
    
    # Curso (solo si tipo clase, validar tenant)
    if 'curso_id' in data and horario.tipo_bloque == 'clase':
        if data['curso_id'] is not None:
            curso = get_tenant_or_404(db, Curso, data['curso_id'], current_user, name='curso')
            assert_nivel_curso_activo(db, current_user, curso.id)
            horario.curso_id = curso.id
        else:
            horario.curso_id = None
    
    # Asignatura
    if 'asignatura_id' in data and horario.tipo_bloque == 'clase':
        if data['asignatura_id'] is not None:
            asignatura = get_tenant_or_404(db, Asignatura, data['asignatura_id'], current_user, name='asignatura')
            horario.asignatura_id = asignatura.id
        else:
            horario.asignatura_id = None
    
    if 'dia' in data:
        horario.dia = _validar_dia(data['dia'])
    if 'hora_inicio' in data:
        horario.hora_inicio = _validar_hora(data['hora_inicio'], 'hora_inicio')
    if 'hora_fin' in data:
        horario.hora_fin = _validar_hora(data['hora_fin'], 'hora_fin')
    if horario.hora_inicio >= horario.hora_fin:
        return JSONResponse({'error': 'hora_fin debe ser mayor que hora_inicio'}, status_code=400)
    
    if 'aula' in data:
        horario.aula = data['aula'] or None
    
    db.commit()
    cache_clear_tenant(current_user.colegio_id)
    return {'message': 'Horario actualizado', 'horario': horario.to_dict()}


@app.delete("/api/horarios/{id}")
async def delete_horario(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Eliminar un horario. Valida tenant antes de borrar."""
    horario = get_tenant_or_404(db, Horario, id, current_user, name='horario')
    db.delete(horario)
    db.commit()
    cache_clear_tenant(current_user.colegio_id)
    return {'message': 'Horario eliminado'}

# ============== CALIFICACIONES ==============

@app.get("/api/calificaciones/curso/{curso_id}/asignatura/{asignatura_id}")
async def get_calificaciones_curso(curso_id, asignatura_id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Listar calificaciones de un curso para una asignatura. Valida tenant + permisos."""
    # Validar tenant de curso y asignatura (404 si no existe o es de otro colegio)
    curso = get_tenant_or_404(db, Curso, curso_id, current_user, name='curso')
    asignatura = get_tenant_or_404(db, Asignatura, asignatura_id, current_user, name='asignatura')
    
    # Verificar que el profesor tiene asignación (si es profesor)
    if current_user.role == 'profesor':
        asignacion = tenant_filter(db.query(AsignacionProfesor), AsignacionProfesor, current_user).filter_by(
            profesor_id=current_user.id,
            curso_id=curso.id,
            asignatura_id=asignatura.id,
            activo=True
        ).first()
        if not asignacion:
            return JSONResponse({'error': 'No tiene asignación para este curso/asignatura'}, status_code=403)
    
    # Incluimos retirados — el profesor los ve con badge readonly. Sus notas
    # previas siguen visibles pero NO editables.
    estudiantes = tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(
        curso_id=curso.id
    ).order_by(Estudiante.no_lista).all()
    
    if not estudiantes:
        ano_activo = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
        return {
            'calificaciones': [],
            'periodo_info': {
                'periodo_activo': ano_activo.periodo_activo if ano_activo else None,
                'p1_cerrado': ano_activo.p1_cerrado if ano_activo else True,
                'p2_cerrado': ano_activo.p2_cerrado if ano_activo else True,
                'p3_cerrado': ano_activo.p3_cerrado if ano_activo else True,
                'p4_cerrado': ano_activo.p4_cerrado if ano_activo else True,
            } if ano_activo else {}
        }
    
    # Eliminar N+1: cargar TODAS las calificaciones de los estudiantes en UNA query
    est_ids = [e.id for e in estudiantes]
    califs = tenant_filter(db.query(Calificacion), Calificacion, current_user).filter(
        Calificacion.estudiante_id.in_(est_ids),
        Calificacion.asignatura_id == asignatura.id,
    ).all()
    califs_map = {c.estudiante_id: c for c in califs}
    
    ano_activo = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    
    result = []
    for est in estudiantes:
        calif = califs_map.get(est.id)
        result.append({
            'estudiante': {
                'id': est.id,
                'nombre_completo': est.nombre_completo,
                'no_lista': est.no_lista,
                'matricula': est.matricula,
                # Flags de retiro: frontend los usa para deshabilitar inputs y mostrar badge
                'retirado': not est.activo,
                'fecha_retiro': est.fecha_retiro.isoformat() if est.fecha_retiro else None,
                'motivo_retiro': est.motivo_retiro,
            },
            'calificacion': calif.to_dict() if calif else None,
        })
    
    periodo_info = {
        'periodo_activo': ano_activo.periodo_activo if ano_activo else None,
        'p1_cerrado': ano_activo.p1_cerrado if ano_activo else True,
        'p2_cerrado': ano_activo.p2_cerrado if ano_activo else True,
        'p3_cerrado': ano_activo.p3_cerrado if ano_activo else True,
        'p4_cerrado': ano_activo.p4_cerrado if ano_activo else True,
    }
    
    return {'calificaciones': result, 'periodo_info': periodo_info}

@app.post("/api/calificaciones")
async def guardar_calificacion(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Guardar calificación. Solo profesores con asignación al curso/asignatura."""
    # SOLO PROFESORES pueden registrar calificaciones
    if current_user.role != 'profesor':
        return JSONResponse({'error': 'Solo los profesores pueden registrar calificaciones'}, status_code=403)
    
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({'error': 'Body inválido'}, status_code=400)
    
    if not isinstance(data, dict):
        return JSONResponse({'error': 'Body debe ser un objeto JSON'}, status_code=400)
    
    if not data.get('estudiante_id') or not data.get('asignatura_id'):
        return JSONResponse({'error': 'estudiante_id y asignatura_id son requeridos'}, status_code=400)
    
    ano_activo = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    
    # Validar tenant del estudiante y la asignatura (404 si no existe o es de otro colegio)
    estudiante = get_tenant_or_404(db, Estudiante, data['estudiante_id'], current_user, name='estudiante')
    asignatura = get_tenant_or_404(db, Asignatura, data['asignatura_id'], current_user, name='asignatura')
    
    # Bloquear calificación de estudiante retirado. Sus notas previas son inmutables.
    if not estudiante.activo:
        return JSONResponse({
            'error': 'Estudiante retirado: no se pueden modificar sus calificaciones',
            'fecha_retiro': estudiante.fecha_retiro.isoformat() if estudiante.fecha_retiro else None,
        }, status_code=403)
    
    # Validar que el nivel del curso del estudiante esté activo en el colegio
    if estudiante.curso_id:
        assert_nivel_curso_activo(db, current_user, estudiante.curso_id)
    
    # Verificar que el profesor tiene asignación a ESE curso (el del estudiante) y a ESA asignatura
    asignacion = tenant_filter(db.query(AsignacionProfesor), AsignacionProfesor, current_user).filter_by(
        profesor_id=current_user.id,
        curso_id=estudiante.curso_id,
        asignatura_id=asignatura.id,
        activo=True
    ).first()
    if not asignacion:
        return JSONResponse({'error': 'No tiene asignación para este curso/asignatura'}, status_code=403)
    
    # Validar período si viene
    periodo_editando = None
    if data.get('periodo'):
        try:
            periodo_editando = int(data['periodo'])
            if periodo_editando not in (1, 2, 3, 4):
                return JSONResponse({'error': 'período debe ser 1, 2, 3 o 4'}, status_code=400)
        except (ValueError, TypeError):
            return JSONResponse({'error': 'período inválido'}, status_code=400)
    
    # Profesor NO puede editar período cerrado - debe solicitar
    if periodo_editando and ano_activo:
        if getattr(ano_activo, f'p{periodo_editando}_cerrado', True):
            permiso = tenant_filter(db.query(PermisoTemporalCalificacion), PermisoTemporalCalificacion, current_user).filter(
                PermisoTemporalCalificacion.profesor_id == current_user.id,
                PermisoTemporalCalificacion.activo == True,
                PermisoTemporalCalificacion.fecha_fin > now_rd(),
                (PermisoTemporalCalificacion.periodo == periodo_editando) | (PermisoTemporalCalificacion.periodo.is_(None)),
                (PermisoTemporalCalificacion.asignatura_id == asignatura.id) | (PermisoTemporalCalificacion.asignatura_id.is_(None))
            ).first()
            
            if not permiso:
                return JSONResponse({'error': f'El período {periodo_editando} está cerrado. Use Solicitar Corrección para pedir edición.'}, status_code=403)
    
    calif = tenant_filter(db.query(Calificacion), Calificacion, current_user).filter_by(
        estudiante_id=estudiante.id,
        asignatura_id=asignatura.id
    ).first()
    
    if not calif:
        calif = Calificacion(
            estudiante_id=estudiante.id,
            asignatura_id=asignatura.id,
            ano_escolar_id=ano_activo.id if ano_activo else None,
            colegio_id=current_user.colegio_id
        )
        db.add(calif)
    
    # Campos válidos
    campos_validos = [
        'p1_p1', 'p1_p2', 'p1_p3', 'p1_p4',
        'rp1_p1', 'rp1_p2', 'rp1_p3', 'rp1_p4',
        'pc1', 'rp1',
        'p2_p1', 'p2_p2', 'p2_p3', 'p2_p4',
        'rp2_p1', 'rp2_p2', 'rp2_p3', 'rp2_p4',
        'pc2', 'rp2',
        'p3_p1', 'p3_p2', 'p3_p3', 'p3_p4',
        'rp3_p1', 'rp3_p2', 'rp3_p3', 'rp3_p4',
        'pc3', 'rp3',
        'p4_p1', 'p4_p2', 'p4_p3', 'p4_p4',
        'rp4_p1', 'rp4_p2', 'rp4_p3', 'rp4_p4',
        'pc4', 'rp4',
        'cf', 'literal'
    ]
    
    # Validar rangos de notas: 0-100, o None
    for campo in campos_validos:
        if campo in data:
            valor = data[campo]
            if valor is None:
                setattr(calif, campo, None)
                continue
            if campo == 'literal':
                # Solo string corto
                if isinstance(valor, str) and len(valor) <= 2:
                    setattr(calif, campo, valor)
                continue
            # Resto son notas numéricas
            try:
                num = float(valor)
                if num < 0 or num > 100:
                    return JSONResponse(
                        {'error': f'{campo} fuera de rango (0-100): {valor}'},
                        status_code=400
                    )
                setattr(calif, campo, num)
            except (ValueError, TypeError):
                return JSONResponse(
                    {'error': f'{campo} debe ser numérico, recibido: {valor!r}'},
                    status_code=400
                )
    
    # Calcular PC automáticamente para cada período si se enviaron los parciales
    for p in range(1, 5):
        pc_calculado = calif.calcular_pc(p)
        if pc_calculado is not None:
            setattr(calif, f'pc{p}', pc_calculado)
    
    # Calcular CF automáticamente
    cf_calculado = calif.calcular_cf()
    if cf_calculado is not None:
        calif.cf = cf_calculado
        calif.literal = calif.get_literal(cf_calculado)
    
    log_auditoria(db, 'UPDATE', 'calificaciones', calif.id, user=current_user, request=request)
    
    db.commit()
    cache_clear(f'stats:{current_user.colegio_id}')
    cache_clear(f'dash_all:{current_user.id}')
    return {'message': 'Calificación guardada', 'id': calif.id, 'calificacion': calif.to_dict()}

# ============== CALIFICACIONES PRIMARIA ==============

@app.get("/api/areas-curriculares")
async def get_areas_curriculares(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Obtener catálogo de áreas curriculares (filtrado por nivel/ciclo si se indica)"""
    nivel = request.query_params.get('nivel')
    ciclo = request.query_params.get('ciclo')
    
    query = tenant_filter(db.query(AreaCurricular), AreaCurricular, current_user).filter_by(activo=True)
    if nivel:
        query = query.filter_by(nivel=nivel)
    if ciclo:
        query = query.filter_by(ciclo=ciclo)
    
    areas = query.order_by(AreaCurricular.orden).all()
    return [{
        'id': a.id,
        'nombre': a.nombre,
        'codigo': a.codigo,
        'nivel': a.nivel,
        'ciclo': a.ciclo,
        'numero_competencias': a.numero_competencias,
        'orden': a.orden
    } for a in areas]

@app.get("/api/calificaciones-primaria/curso/{curso_id}/asignatura/{asignatura_id}")
async def get_calificaciones_primaria(curso_id: int, asignatura_id: int, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Obtener calificaciones de primaria de todos los estudiantes del curso.
    
    Devuelve: por cada estudiante, hasta N filas (una por competencia: C1, C2, C3)
    """
    try:
        # Verificar que el curso existe y pertenece al colegio
        curso = tenant_filter(db.query(Curso), Curso, current_user).filter_by(id=curso_id).first()
        if not curso:
            return JSONResponse({'error': 'Curso no encontrado'}, status_code=404)
        
        # Verificar que el grado es de primaria
        grado = curso.grado
        if not grado:
            return JSONResponse({'error': 'El curso no tiene grado asignado'}, status_code=400)
        if grado.nivel != 'primaria':
            return JSONResponse({
                'error': f'Este curso no es de primaria (nivel actual: {grado.nivel or "no definido"})'
            }, status_code=400)
        
        # Año escolar activo
        ano = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
        if not ano:
            return JSONResponse({'error': 'No hay año escolar activo'}, status_code=404)
        
        # Obtener asignatura para saber cuántas competencias tiene
        asignatura = tenant_filter(db.query(Asignatura), Asignatura, current_user).filter_by(id=asignatura_id).first()
        if not asignatura:
            return JSONResponse({'error': 'Asignatura no encontrada'}, status_code=404)
        
        # Determinar número de competencias (default 3)
        num_competencias = 3
        if grado.ciclo:
            area = tenant_filter(db.query(AreaCurricular), AreaCurricular, current_user).filter_by(
                nombre=asignatura.nombre, nivel='primaria', ciclo=grado.ciclo
            ).first()
            if area:
                num_competencias = area.numero_competencias
        
        # Incluir retirados — el profesor los ve con badge readonly
        estudiantes = tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(
            curso_id=curso_id
        ).order_by(Estudiante.apellido).all()
        # Ordenar por no_lista manualmente (nulls last)
        estudiantes = sorted(estudiantes, key=lambda e: (e.no_lista is None, e.no_lista or 0, e.apellido or ''))
        
        resultado = []
        for est in estudiantes:
            califs = tenant_filter(db.query(CalificacionPrimaria), CalificacionPrimaria, current_user).filter_by(
                estudiante_id=est.id, asignatura_id=asignatura_id, ano_escolar_id=ano.id
            ).all()
            califs_por_comp = {c.competencia_numero: c for c in califs}
            
            competencias_data = []
            for comp_num in range(1, num_competencias + 1):
                cal = califs_por_comp.get(comp_num)
                if cal:
                    competencias_data.append(cal.to_dict())
                else:
                    competencias_data.append({
                        'id': None,
                        'estudiante_id': est.id,
                        'asignatura_id': asignatura_id,
                        'competencia_numero': comp_num,
                        'competencia_nombre': None,
                        'p1': None, 'rp1': None,
                        'p2': None, 'rp2': None,
                        'p3': None, 'rp3': None,
                        'p4': None, 'rp4': None,
                        'final_competencia': None,
                        'literal': None
                    })
            
            resultado.append({
                'estudiante': {
                    'id': est.id,
                    'nombre_completo': est.nombre_completo,
                    'no_lista': est.no_lista,
                    # Flags de retiro
                    'retirado': not est.activo,
                    'fecha_retiro': est.fecha_retiro.isoformat() if est.fecha_retiro else None,
                    'motivo_retiro': est.motivo_retiro,
                },
                'competencias': competencias_data
            })
        
        return {
            'calificaciones': resultado,
            'num_competencias': num_competencias,
            'asignatura': asignatura.nombre,
            'grado': grado.nombre,
            'ciclo': grado.ciclo,
            'ano_escolar': ano.nombre,
            'periodo_activo': ano.periodo_activo,
        }
    except Exception as e:
        import traceback
        logger.error(f"Error en calificaciones-primaria: {e}\n{traceback.format_exc()}")
        return JSONResponse({'error': f'Error del servidor: {str(e)}'}, status_code=500)

@app.post("/api/calificaciones-primaria")
async def save_calificacion_primaria(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Guardar/actualizar calificación primaria por competencia (estructura MINERD).
    SOLO PROFESORES pueden calificar — misma regla que secundaria.
    Dirección NUNCA puede calificar directamente.
    """
    if current_user.role != 'profesor':
        return JSONResponse({'error': 'Solo los profesores pueden registrar calificaciones'}, status_code=403)
    
    data = await request.json()
    
    estudiante_id = data.get('estudiante_id')
    asignatura_id = data.get('asignatura_id')
    competencia_numero = data.get('competencia_numero')
    
    if not all([estudiante_id, asignatura_id, competencia_numero]):
        return JSONResponse({'error': 'Faltan datos requeridos'}, status_code=400)
    
    # Validar que el nivel del curso del estudiante esté activo (siempre primaria acá)
    estudiante_obj = get_tenant_or_404(db, Estudiante, estudiante_id, current_user, name='estudiante')
    get_tenant_or_404(db, Asignatura, asignatura_id, current_user, name='asignatura')
    
    # Bloquear calificación de estudiante retirado
    if not estudiante_obj.activo:
        return JSONResponse({
            'error': 'Estudiante retirado: no se pueden modificar sus calificaciones',
            'fecha_retiro': estudiante_obj.fecha_retiro.isoformat() if estudiante_obj.fecha_retiro else None,
        }, status_code=403)
    
    if estudiante_obj.curso_id:
        assert_nivel_curso_activo(db, current_user, estudiante_obj.curso_id)
    
    # Año escolar activo
    ano = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    if not ano:
        return JSONResponse({'error': 'No hay año escolar activo'}, status_code=404)
    
    # Verificar multi-tenant
    est = tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(id=estudiante_id).first()
    if not est:
        return JSONResponse({'error': 'Estudiante no encontrado'}, status_code=404)
    
    # Buscar o crear calificación
    calif = tenant_filter(db.query(CalificacionPrimaria), CalificacionPrimaria, current_user).filter_by(
        estudiante_id=estudiante_id, asignatura_id=asignatura_id,
        competencia_numero=competencia_numero, ano_escolar_id=ano.id
    ).first()
    
    if not calif:
        calif = CalificacionPrimaria(
            estudiante_id=estudiante_id,
            asignatura_id=asignatura_id,
            competencia_numero=competencia_numero,
            competencia_nombre=data.get('competencia_nombre'),
            ano_escolar_id=ano.id,
            colegio_id=current_user.colegio_id
        )
        db.add(calif)
    
    # Campos aceptados: 4 períodos + 4 recuperaciones + nombre competencia
    campos_validos = ['p1', 'p2', 'p3', 'p4', 'rp1', 'rp2', 'rp3', 'rp4', 'competencia_nombre']
    for campo in campos_validos:
        if campo in data:
            setattr(calif, campo, data[campo])
    
    # Calcular final de la competencia (C1/C2/C3) automáticamente
    final = calif.calcular_final()
    if final is not None:
        calif.final_competencia = final
        calif.literal = calif.get_literal(final)
    
    db.commit()
    cache_clear(f'stats:{current_user.colegio_id}')
    return {'message': 'Calificación primaria guardada', 'id': calif.id, 'calificacion': calif.to_dict()}


# ============== CALIFICACIONES SECUNDARIA v2.12 (estructura MINERD por competencia) ==============

def _es_curso_secundaria(db, curso_id: int) -> bool:
    """Helper: verifica si un curso es de secundaria (no primaria)."""
    curso = db.get(Curso, curso_id)
    if not curso or not curso.grado_id:
        return False
    grado = db.get(Grado, curso.grado_id)
    return grado and (grado.nivel or '').lower() == 'secundaria'


def _calcular_cf_secundaria(db, estudiante_id: int, asignatura_id: int, ano_id: int, con_exacto: bool = False):
    """Calcular CF del área de secundaria según MINERD oficial.
    
    Fórmula MINERD: CF = AVG(PC1, PC2, PC3, PC4) redondeado a entero.
    Donde PC[i] = promedio de las 4 competencias en el período i.
    
    Equivalente matemáticamente a AVG de los 4 promedios_competencia (mismo resultado),
    pero seguimos la fórmula oficial del boletín.
    
    Devuelve (cf, literal) o (None, None) si no están las 4 competencias completas.
    """
    competencias = db.query(CalificacionSecundaria).filter_by(
        estudiante_id=estudiante_id, asignatura_id=asignatura_id, ano_escolar_id=ano_id
    ).all()
    if len(competencias) < 4:
        return (None, None)
    
    # PC por período = promedio de las 4 competencias en ese período
    pcs = []
    for p in range(1, 5):
        pc = CalificacionSecundaria.calcular_pc_periodo(competencias, p)
        if pc is None:
            return (None, None)  # falta alguna competencia en ese período
        pcs.append(pc)
    
    # CF = promedio de los 4 PC. El oficial usa el valor SIN redondear para
    # los porcentajes de completiva/extraordinaria, y el redondeado para mostrar.
    cf_exacto = sum(pcs) / 4
    cf = round(cf_exacto, 0)
    
    # Literal MINERD
    if cf >= 90: literal = 'A'
    elif cf >= 80: literal = 'B'
    elif cf >= 70: literal = 'C'
    else: literal = 'F'
    
    if con_exacto:
        return (cf, literal, cf_exacto)
    return (cf, literal)


@app.get("/api/calificaciones-secundaria/curso/{curso_id}/asignatura/{asignatura_id}")
async def get_calificaciones_secundaria(curso_id: int, asignatura_id: int,
                                          request: Request, db: Session = Depends(get_db),
                                          current_user: Usuario = Depends(get_current_user)):
    """Obtener calificaciones secundaria de un curso/asignatura.
    
    Devuelve estructura por estudiante con sus 4 competencias y el CF calculado.
    """
    curso = get_tenant_or_404(db, Curso, curso_id, current_user, name='curso')
    get_tenant_or_404(db, Asignatura, asignatura_id, current_user, name='asignatura')
    
    # Validar que sea curso de secundaria
    if not _es_curso_secundaria(db, curso_id):
        return JSONResponse(
            {'error': 'Este endpoint es solo para cursos de secundaria. Use /api/calificaciones-primaria para primaria.'},
            status_code=400
        )
    
    # Profesor: validar asignación
    if current_user.role == 'profesor':
        tiene_asig = db.query(AsignacionProfesor).filter_by(
            profesor_id=current_user.id, curso_id=curso_id, asignatura_id=asignatura_id
        ).first()
        if not tiene_asig:
            return JSONResponse({'error': 'No tiene asignación a este curso/asignatura'}, status_code=403)
    
    # Año escolar activo
    ano = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    if not ano:
        return JSONResponse({'error': 'No hay año escolar activo'}, status_code=404)
    
    # Estudiantes del curso
    estudiantes = db.query(Estudiante).filter_by(
        curso_id=curso_id, colegio_id=current_user.colegio_id, activo=True
    ).order_by(Estudiante.apellido, Estudiante.nombre).all()
    
    # Calificaciones de la asignatura
    califs = tenant_filter(db.query(CalificacionSecundaria), CalificacionSecundaria, current_user).filter_by(
        asignatura_id=asignatura_id, ano_escolar_id=ano.id
    ).filter(CalificacionSecundaria.estudiante_id.in_([e.id for e in estudiantes])).all()
    
    # Indexar: {estudiante_id: {competencia_numero: calif}}
    by_est = {}
    for c in califs:
        by_est.setdefault(c.estudiante_id, {})[c.competencia_numero] = c
    
    # Evaluaciones extra (completiva/extra/especial)
    extras = tenant_filter(db.query(EvaluacionExtraSecundaria), EvaluacionExtraSecundaria, current_user).filter_by(
        asignatura_id=asignatura_id, ano_escolar_id=ano.id
    ).filter(EvaluacionExtraSecundaria.estudiante_id.in_([e.id for e in estudiantes])).all()
    extras_by_est = {e.estudiante_id: e for e in extras}
    
    resultado = []
    for est in estudiantes:
        comps = by_est.get(est.id, {})
        competencias_data = {}
        # Lista para cálculos cruzados (PC y A/R)
        comps_para_calculo = []
        for num in range(1, 5):
            c = comps.get(num)
            if c:
                competencias_data[num] = c.to_dict()
                comps_para_calculo.append(c)
            else:
                competencias_data[num] = {
                    'competencia_numero': num,
                    'p1': None, 'rp1': None,
                    'p2': None, 'rp2': None,
                    'p3': None, 'rp3': None,
                    'p4': None, 'rp4': None,
                    'promedio_competencia': None,
                }
        
        # PC1-PC4: promedio de las 4 competencias en cada período (MINERD oficial)
        pcs = {}
        ar_periodos = {}
        if len(comps_para_calculo) == 4:
            for p in range(1, 5):
                pcs[f'pc{p}'] = CalificacionSecundaria.calcular_pc_periodo(comps_para_calculo, p)
                ar_periodos[f'p{p}'] = CalificacionSecundaria.calcular_a_r_periodo(comps_para_calculo, p)
        else:
            for p in range(1, 5):
                pcs[f'pc{p}'] = None
                ar_periodos[f'p{p}'] = {'a': 0, 'r': 0, 'pendientes': 4 - len(comps_para_calculo)}
        
        # CF del área (AVG de PC1-PC4) y literal
        cf, literal = _calcular_cf_secundaria(db, est.id, asignatura_id, ano.id)
        
        extra = extras_by_est.get(est.id)
        
        resultado.append({
            'estudiante': {
                'id': est.id,
                'nombre_completo': f"{est.apellido or ''}, {est.nombre or ''}".strip(', '),
            },
            'competencias': competencias_data,
            'pc_por_periodo': pcs,            # PC1, PC2, PC3, PC4
            'a_r_por_periodo': ar_periodos,   # {p1: {a:N, r:N}, p2: ..., ...}
            'cf': cf,
            'literal': literal,
            'evaluacion_extra': extra.to_dict() if extra else None,
        })
    
    return {
        'curso_id': curso_id,
        'asignatura_id': asignatura_id,
        'ano_escolar': ano.nombre,
        'calificaciones': resultado,
        # v2.13.35: estado de cierre de períodos (para bloquear casillas en el frontend)
        'periodos_cerrados': {
            'p1': bool(ano.p1_cerrado),
            'p2': bool(ano.p2_cerrado),
            'p3': bool(ano.p3_cerrado),
            'p4': bool(ano.p4_cerrado),
        },
        'periodo_activo': ano.periodo_activo,
    }


@app.get("/api/calificaciones-secundaria/curso/{curso_id}/periodo/{periodo}/competencias")
async def get_competencias_periodo_curso(curso_id: int, periodo: int,
                                          request: Request, db: Session = Depends(get_db),
                                          current_user: Usuario = Depends(get_current_user)):
    """v2.13.13 — Vista B de "Notas por Período": desglose por competencia.
    
    Para un curso + período, devuelve por cada estudiante y cada asignatura
    el detalle de las 4 competencias (su valor en ese período) + el PC
    resultante (promedio de las 4 competencias).
    
    Esto alimenta la vista "por competencia" donde se ve CÓMO se forma el PC
    de cada período, no solo el número final.
    """
    curso = get_tenant_or_404(db, Curso, curso_id, current_user, name='curso')
    if not (1 <= periodo <= 4):
        return JSONResponse({'error': 'Período debe ser 1-4'}, status_code=400)
    
    ano = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    if not ano:
        return JSONResponse({'error': 'No hay año escolar activo'}, status_code=404)
    
    estudiantes = tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(
        curso_id=curso_id, activo=True
    ).order_by(Estudiante.apellido, Estudiante.nombre).all()
    est_ids = [e.id for e in estudiantes]
    
    # Asignaturas del curso (vía asignaciones)
    asignaciones = tenant_filter(db.query(AsignacionProfesor), AsignacionProfesor, current_user).filter_by(
        curso_id=curso_id, activo=True
    ).all()
    asig_ids = sorted(set(a.asignatura_id for a in asignaciones))
    asignaturas = tenant_filter(db.query(Asignatura), Asignatura, current_user).filter(
        Asignatura.id.in_(asig_ids)
    ).all() if asig_ids else []
    asig_nombres = {a.id: a.nombre for a in asignaturas}
    
    # Pre-cargar todas las competencias del curso para este año (evita N+1)
    califs = tenant_filter(db.query(CalificacionSecundaria), CalificacionSecundaria, current_user).filter(
        CalificacionSecundaria.estudiante_id.in_(est_ids),
        CalificacionSecundaria.asignatura_id.in_(asig_ids),
        CalificacionSecundaria.ano_escolar_id == ano.id,
    ).all() if est_ids and asig_ids else []
    
    # Indexar: {(est_id, asig_id): {competencia_numero: calif}}
    idx = {}
    for c in califs:
        idx.setdefault((c.estudiante_id, c.asignatura_id), {})[c.competencia_numero] = c
    
    resultado = []
    for est in estudiantes:
        asignaturas_data = []
        for asig_id in asig_ids:
            comps = idx.get((est.id, asig_id), {})
            # Valor de cada competencia en ESTE período
            comp_valores = []
            for num in range(1, 5):
                c = comps.get(num)
                valor = c.valor_periodo(periodo) if c else None
                comp_valores.append({
                    'competencia': num,
                    'valor': valor,
                })
            # PC del período = promedio de las competencias con valor
            vals = [cv['valor'] for cv in comp_valores if cv['valor'] is not None]
            pc = round(sum(vals) / len(vals), 1) if vals else None
            
            asignaturas_data.append({
                'asignatura_id': asig_id,
                'asignatura': asig_nombres.get(asig_id, f'Asig {asig_id}'),
                'competencias': comp_valores,
                'pc': pc,
                'completo': len(vals) == 4,
            })
        
        resultado.append({
            'estudiante_id': est.id,
            'no_lista': est.no_lista,
            'nombre': est.nombre_completo,
            'asignaturas': asignaturas_data,
        })
    
    return {
        'curso': curso.nombre_completo,
        'curso_id': curso_id,
        'periodo': periodo,
        'ano_escolar': ano.nombre,
        'asignaturas_nombres': [asig_nombres[aid] for aid in asig_ids],
        'estudiantes': resultado,
    }


@app.get("/api/calificaciones-secundaria/reporte-padres/curso/{curso_id}/pdf")
async def reporte_padres_curso_pdf(curso_id: int, request: Request,
                                    db: Session = Depends(get_db),
                                    current_user: Usuario = Depends(RolesRequired('direccion', 'coordinador', 'profesor', 'secretaria'))):
    """v2.13.17 — Reporte de Calificaciones de UNA competencia (curso o individual).
    
    El reporte es de la competencia que se está trabajando (1, 2, 3 o 4).
    Por asignatura muestra UNA nota de esa competencia según el MODO:
    
      modo='pc' (default): PC de la competencia = promedio de sus 4 períodos
        (p1+p2+p3+p4)/4 usando los períodos cargados.
      
      modo='ultimo_p': el p4 (cuarto período) de la competencia. Se usa para
        reportar antes del cierre y dar tiempo de recuperación a quien esté
        por debajo de 70.
    
    NOTA: al padre NO se le indica si la nota es PC o último P. El PDF solo
    dice "Reporte de Calificaciones / Competencia N". El modo es interno.
    
    Query params:
      - competencia: 1-4 (default 1). Cuál competencia reportar.
      - modo: 'pc' | 'ultimo_p' (default 'pc').
      - estudiante_id: opcional → si se pasa genera solo ese estudiante.
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas as pdf_canvas
    from reportlab.lib.units import cm
    from reportlab.lib import colors as rl_colors
    from reportlab.lib.utils import ImageReader
    import base64 as _b64
    
    curso = get_tenant_or_404(db, Curso, curso_id, current_user, name='curso')
    ano = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    if not ano:
        # v2.13.19: si el año está cerrado (tras promover) no hay año activo.
        # Usar el más reciente para no romper el reporte.
        ano = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).order_by(AnoEscolar.id.desc()).first()
    if not ano:
        return JSONResponse({'error': 'No hay año escolar configurado'}, status_code=404)
    
    modo = request.query_params.get('modo', 'pc')
    if modo not in ('pc', 'ultimo_p'):
        modo = 'pc'
    try:
        competencia = int(request.query_params.get('competencia', 1))
    except (ValueError, TypeError):
        competencia = 1
    if not (1 <= competencia <= 4):
        competencia = 1
    
    estudiante_id = request.query_params.get('estudiante_id')
    config = tenant_filter(db.query(ConfiguracionColegio), ConfiguracionColegio, current_user).first()
    
    # Estudiantes a incluir
    q_est = tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(curso_id=curso_id, activo=True)
    if estudiante_id:
        q_est = q_est.filter(Estudiante.id == int(estudiante_id))
    estudiantes = q_est.order_by(Estudiante.apellido, Estudiante.nombre).all()
    if not estudiantes:
        return JSONResponse({'error': 'No hay estudiantes para el reporte'}, status_code=404)
    
    est_ids = [e.id for e in estudiantes]
    asignaciones = tenant_filter(db.query(AsignacionProfesor), AsignacionProfesor, current_user).filter_by(curso_id=curso_id, activo=True).all()
    asig_ids = sorted(set(a.asignatura_id for a in asignaciones))
    asignaturas = tenant_filter(db.query(Asignatura), Asignatura, current_user).filter(Asignatura.id.in_(asig_ids)).all() if asig_ids else []
    asig_nombres = {a.id: a.nombre for a in asignaturas}
    
    califs = tenant_filter(db.query(CalificacionSecundaria), CalificacionSecundaria, current_user).filter(
        CalificacionSecundaria.estudiante_id.in_(est_ids),
        CalificacionSecundaria.asignatura_id.in_(asig_ids),
        CalificacionSecundaria.ano_escolar_id == ano.id,
    ).all() if est_ids and asig_ids else []
    idx = {}
    for c in califs:
        idx.setdefault((c.estudiante_id, c.asignatura_id), {})[c.competencia_numero] = c
    
    centro_nombre = (getattr(config, 'nombre', None) or 'Centro Educativo') if config else 'Centro Educativo'
    
    # Logo del colegio (guardado como data:image/...;base64,... en config.logo)
    logo_img = None
    if config and getattr(config, 'logo', None):
        try:
            logo_raw = config.logo
            if ',' in logo_raw:  # quitar prefijo data:image/...;base64,
                logo_raw = logo_raw.split(',', 1)[1]
            logo_bytes = _b64.b64decode(logo_raw)
            logo_img = ImageReader(io.BytesIO(logo_bytes))
        except Exception as e:
            logger.warning(f"No se pudo decodificar el logo del colegio: {e}")
            logo_img = None
    
    # Valor de la asignatura para la COMPETENCIA elegida, según el modo.
    # comps = dict {competencia_numero: CalificacionSecundaria} de esa asignatura
    def _nota_competencia_asignatura(comps):
        c_obj = comps.get(competencia) if comps else None
        if c_obj is None:
            return None
        if modo == 'ultimo_p':
            # Último P = p4 (cuarto período) de esta competencia
            return c_obj.valor_periodo(4)
        else:
            # PC de la competencia = promedio de sus 4 períodos (p1+p2+p3+p4)/4
            vals = [c_obj.valor_periodo(p) for p in range(1, 5) if c_obj.valor_periodo(p) is not None]
            return round(sum(vals) / len(vals), 1) if vals else None
    
    # Título: el padre NO ve si es PC o último P. Solo "Competencia N".
    titulo_competencia = f"Competencia {competencia}"
    
    buffer = io.BytesIO()
    c = pdf_canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    for est in estudiantes:
        y = height - 1.5*cm
        # Logo (esquina superior izquierda) si existe
        if logo_img is not None:
            try:
                c.drawImage(logo_img, 2*cm, y-1.2*cm, width=2.2*cm, height=2.2*cm,
                            preserveAspectRatio=True, mask='auto')
            except Exception:
                pass
        # Encabezado centrado
        c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(width/2, y, centro_nombre)
        y -= 0.6*cm
        c.setFont("Helvetica-Bold", 12)
        c.drawCentredString(width/2, y, "Reporte de Calificaciones")
        y -= 0.5*cm
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(rl_colors.HexColor('#1e3a5f'))
        c.drawCentredString(width/2, y, titulo_competencia)
        c.setFillColor(rl_colors.black)
        y -= 1*cm
        
        # Datos del estudiante
        c.setFont("Helvetica", 10)
        c.drawString(2*cm, y, f"Estudiante: {est.nombre_completo}")
        c.drawString(13*cm, y, f"Curso: {curso.nombre_completo}")
        y -= 0.5*cm
        c.drawString(2*cm, y, f"Matricula: {est.matricula or '-'}")
        c.drawString(13*cm, y, f"Ano escolar: {ano.nombre}")
        y -= 1*cm
        
        # Tabla de asignaturas
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(rl_colors.HexColor('#1e3a5f'))
        c.rect(2*cm, y-0.2*cm, width-4*cm, 0.7*cm, fill=1, stroke=0)
        c.setFillColor(rl_colors.white)
        c.drawString(2.3*cm, y, "Asignatura")
        c.drawString(12*cm, y, "Calificación")
        c.drawString(15*cm, y, "Nivel")
        c.drawString(17.5*cm, y, "Estado")
        c.setFillColor(rl_colors.black)
        y -= 0.8*cm
        
        suma = 0
        count = 0
        for asig_id in asig_ids:
            comps = idx.get((est.id, asig_id), {})
            nota = _nota_competencia_asignatura(comps)
            
            def _lit(n):
                if n is None: return '-'
                if n >= 90: return 'A'
                if n >= 80: return 'B'
                if n >= 70: return 'C'
                return 'F'
            
            c.setFont("Helvetica", 10)
            c.drawString(2.3*cm, y, asig_nombres.get(asig_id, '')[:45])
            if nota is not None:
                color = rl_colors.HexColor('#16a34a') if nota >= 70 else rl_colors.HexColor('#dc2626')
                c.setFillColor(color)
                c.drawString(12.5*cm, y, str(nota))
                c.setFillColor(rl_colors.black)
                c.drawString(15.3*cm, y, _lit(nota))
                c.drawString(17.5*cm, y, "Aprobado" if nota >= 70 else "En riesgo")
                suma += nota
                count += 1
            else:
                c.setFillColor(rl_colors.grey)
                c.drawString(12.5*cm, y, "Sin nota")
                c.setFillColor(rl_colors.black)
            y -= 0.6*cm
            if y < 4*cm:
                c.showPage()
                y = height - 2*cm
        
        # Promedio general
        y -= 0.3*cm
        promedio = round(suma/count, 1) if count > 0 else None
        c.setFont("Helvetica-Bold", 11)
        if promedio is not None:
            color = rl_colors.HexColor('#16a34a') if promedio >= 70 else rl_colors.HexColor('#dc2626')
            c.setFillColor(color)
            c.drawString(2.3*cm, y, f"Promedio general: {promedio}")
            c.setFillColor(rl_colors.black)
        y -= 1.5*cm
        
        # Firma
        c.setFont("Helvetica", 9)
        c.line(2*cm, y, 8*cm, y)
        c.line(11*cm, y, 17*cm, y)
        y -= 0.4*cm
        c.drawString(3*cm, y, "Firma del docente")
        c.drawString(12.5*cm, y, "Firma del padre/madre/tutor")
        
        c.showPage()
    
    c.save()
    buffer.seek(0)
    
    tipo = 'individual' if estudiante_id else 'curso'
    modo_str = 'PC' if modo == 'pc' else 'UltimoP'
    filename = f"Reporte_Calificaciones_Competencia{competencia}_{modo_str}_{tipo}_{(curso.nombre or 'curso').replace(' ', '_')}.pdf"
    return StreamingResponse(buffer, media_type='application/pdf',
                             headers={'Content-Disposition': f'attachment; filename="{filename}"'})




@app.post("/api/calificaciones-secundaria")
async def save_calificacion_secundaria(request: Request, db: Session = Depends(get_db),
                                          current_user: Usuario = Depends(get_current_user)):
    """Guardar/actualizar calificación secundaria por competencia.
    
    Solo PROFESORES pueden calificar. El profesor entra las notas de UNA competencia
    a la vez (estructura igual a primaria pero con 4 competencias).
    
    Body esperado:
        estudiante_id: int
        asignatura_id: int
        competencia_numero: 1, 2, 3 o 4
        p1, p2, p3, p4: notas (opcional)
        rp1, rp2, rp3, rp4: recuperaciones (opcional)
    """
    if current_user.role != 'profesor':
        return JSONResponse({'error': 'Solo los profesores pueden registrar calificaciones'}, status_code=403)
    
    data = await request.json()
    estudiante_id = data.get('estudiante_id')
    asignatura_id = data.get('asignatura_id')
    competencia_numero = data.get('competencia_numero')
    
    if not all([estudiante_id, asignatura_id, competencia_numero]):
        return JSONResponse({'error': 'Faltan datos requeridos (estudiante_id, asignatura_id, competencia_numero)'}, status_code=400)
    
    if competencia_numero not in (1, 2, 3, 4):
        return JSONResponse({'error': 'competencia_numero debe ser 1, 2, 3 o 4'}, status_code=400)
    
    estudiante_obj = get_tenant_or_404(db, Estudiante, estudiante_id, current_user, name='estudiante')
    get_tenant_or_404(db, Asignatura, asignatura_id, current_user, name='asignatura')
    
    if not estudiante_obj.activo:
        return JSONResponse({'error': 'Estudiante retirado: no se pueden modificar sus calificaciones'}, status_code=403)
    
    # Validar que sea curso de secundaria
    if estudiante_obj.curso_id and not _es_curso_secundaria(db, estudiante_obj.curso_id):
        return JSONResponse({
            'error': 'El estudiante no es de secundaria. Use /api/calificaciones-primaria para primaria.'
        }, status_code=400)
    
    if estudiante_obj.curso_id:
        assert_nivel_curso_activo(db, current_user, estudiante_obj.curso_id)
    
    # Profesor: verificar asignación
    tiene_asig = db.query(AsignacionProfesor).filter_by(
        profesor_id=current_user.id, curso_id=estudiante_obj.curso_id, asignatura_id=asignatura_id
    ).first()
    if not tiene_asig:
        return JSONResponse({'error': 'No tiene asignación a este curso/asignatura'}, status_code=403)
    
    # Año escolar activo
    ano = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    if not ano:
        return JSONResponse({'error': 'No hay año escolar activo'}, status_code=404)
    
    # Buscar o crear
    calif = tenant_filter(db.query(CalificacionSecundaria), CalificacionSecundaria, current_user).filter_by(
        estudiante_id=estudiante_id, asignatura_id=asignatura_id,
        competencia_numero=competencia_numero, ano_escolar_id=ano.id
    ).first()
    
    if not calif:
        calif = CalificacionSecundaria(
            estudiante_id=estudiante_id,
            asignatura_id=asignatura_id,
            competencia_numero=competencia_numero,
            ano_escolar_id=ano.id,
            colegio_id=current_user.colegio_id
        )
        db.add(calif)
        _audit_antes = None  # era nueva
    else:
        # v2.13.31: capturar valores anteriores para auditoría de detalle fino
        _audit_antes = {c: getattr(calif, c, None) for c in ['p1','p2','p3','p4','rp1','rp2','rp3','rp4']}
    
    # v2.13.34: VALIDACIÓN DE CIERRE POR PERÍODO (Opción 2 - inteligente)
    # Al cerrar el Período N, se bloquean los PN de todas las competencias.
    # Si el profesor intenta modificar un período cerrado, se SALTA ese período
    # (no se guarda) y se guardan los abiertos. El profesor puede usar
    # "Solicitar Corrección" para editar un período cerrado con permiso temporal.
    periodos_cerrados_ignorados = []
    def _periodo_esta_cerrado(num_periodo):
        """True si el período está cerrado Y el profesor no tiene permiso temporal."""
        if not getattr(ano, f'p{num_periodo}_cerrado', False):
            return False  # abierto → se puede editar
        # ¿Tiene permiso temporal de corrección?
        permiso = tenant_filter(db.query(PermisoTemporalCalificacion), PermisoTemporalCalificacion, current_user).filter(
            PermisoTemporalCalificacion.profesor_id == current_user.id,
            PermisoTemporalCalificacion.activo == True,
            PermisoTemporalCalificacion.fecha_fin > now_rd(),
            (PermisoTemporalCalificacion.periodo == num_periodo) | (PermisoTemporalCalificacion.periodo.is_(None)),
            (PermisoTemporalCalificacion.asignatura_id == asignatura_id) | (PermisoTemporalCalificacion.asignatura_id.is_(None))
        ).first()
        return permiso is None  # cerrado y sin permiso → bloqueado

    # Aplicar campos de notas (validar rangos)
    campos_notas = ['p1', 'p2', 'p3', 'p4', 'rp1', 'rp2', 'rp3', 'rp4']
    for campo in campos_notas:
        if campo in data:
            # ¿A qué período pertenece este campo? (p1/rp1 → 1, p2/rp2 → 2, etc.)
            num_periodo = int(campo[-1])
            # Si el período está cerrado (sin permiso), saltar este campo
            if _periodo_esta_cerrado(num_periodo):
                if num_periodo not in periodos_cerrados_ignorados:
                    periodos_cerrados_ignorados.append(num_periodo)
                continue  # no modificar un período cerrado
            valor = data[campo]
            if valor is None or valor == '':
                setattr(calif, campo, None)
            else:
                try:
                    nota = float(valor)
                except (ValueError, TypeError):
                    return JSONResponse({'error': f'{campo}: debe ser número'}, status_code=400)
                if nota < 0 or nota > 100:
                    return JSONResponse({'error': f'{campo}: debe estar entre 0 y 100'}, status_code=400)
                setattr(calif, campo, nota)
    
    # v2.13.1: validar RP solo aplica si P del mismo período < 70 (regla MINERD oficial)
    # Después de aplicar todos los campos, validamos coherencia.
    # Si el profesor está intentando setear RP con valor mientras P es null o >=70 → 400.
    for periodo in [1, 2, 3, 4]:
        p_val = getattr(calif, f'p{periodo}', None)
        rp_val = getattr(calif, f'rp{periodo}', None)
        if rp_val is not None:
            if p_val is None:
                return JSONResponse({
                    'error': f'RP{periodo}: no se puede cargar recuperación sin la nota P{periodo} original',
                    'campo': f'rp{periodo}',
                    'regla': 'MINERD: RP solo aplica si el estudiante reprobó P (< 70)',
                }, status_code=400)
            if p_val >= 70:
                return JSONResponse({
                    'error': f'RP{periodo}: el estudiante aprobó P{periodo} con {p_val:.1f}, no necesita recuperación',
                    'campo': f'rp{periodo}',
                    'regla': 'MINERD: RP solo aplica si el estudiante reprobó P (< 70)',
                }, status_code=400)
    
    # Recalcular promedio de la competencia
    calif.promedio_competencia = calif.calcular_promedio_competencia()
    
    # Si las 4 competencias están completas, actualizar/crear EvaluacionExtraSecundaria con el CF
    db.flush()
    cf, _, cf_exacto = _calcular_cf_secundaria(db, estudiante_id, asignatura_id, ano.id, con_exacto=True)
    if cf is not None:
        # Buscar o crear evaluación extra (siempre se crea para tener el CF cacheado)
        ev = db.query(EvaluacionExtraSecundaria).filter_by(
            estudiante_id=estudiante_id, asignatura_id=asignatura_id, ano_escolar_id=ano.id
        ).first()
        if not ev:
            ev = EvaluacionExtraSecundaria(
                estudiante_id=estudiante_id, asignatura_id=asignatura_id,
                ano_escolar_id=ano.id, colegio_id=current_user.colegio_id
            )
            db.add(ev)
        # Se guarda el CF SIN redondear: la tabla oficial MINERD calcula
        # 50%CF y 30%CF sobre el valor exacto (ej. 63.5 → 31.8 / 19.1).
        ev.cf_original = cf_exacto
        ev.recalcular_todo()
    
    db.commit()

    # v2.13.31: auditoría con DETALLE FINO (antes/después) de la nota.
    # Esto permite rastrear exactamente qué nota cambió, de qué valor a cuál.
    try:
        _audit_despues = {c: getattr(calif, c, None) for c in ['p1','p2','p3','p4','rp1','rp2','rp3','rp4']}
        log_auditoria(
            db, accion='GUARDAR_NOTA_SECUNDARIA', tabla='calificaciones_secundaria',
            registro_id=calif.id, datos_anteriores=_audit_antes, datos_nuevos=_audit_despues,
            user=current_user, request=request,
        )
        db.commit()
    except Exception as _e:
        logging.getLogger('educaone.audit').warning(f'auditoría nota falló: {_e}')

    cache_clear(f'stats:{current_user.colegio_id}')
    respuesta = {
        'message': 'Calificación secundaria guardada',
        'id': calif.id,
        'calificacion': calif.to_dict(),
        'cf_area': cf,
    }
    # v2.13.34: si se ignoraron períodos cerrados, avisar al profesor
    if periodos_cerrados_ignorados:
        periodos_str = ', '.join(f'P{n}' for n in sorted(periodos_cerrados_ignorados))
        respuesta['message'] = f'Guardado. Nota: {periodos_str} está(n) cerrado(s) y no se modificó(aron). Use Solicitar Corrección si necesita editarlos.'
        respuesta['periodos_cerrados_ignorados'] = sorted(periodos_cerrados_ignorados)
    return respuesta


@app.post("/api/calificaciones-secundaria/evaluacion-extra")
async def save_evaluacion_extra(request: Request, db: Session = Depends(get_db),
                                  current_user: Usuario = Depends(get_current_user)):
    """Guardar nota de evaluación extra (completiva/extraordinaria/especial).
    
    SOLO PROFESORES la evalúan. Dirección/coordinación SOLO gestionan
    (ven listas, lanzan alertas), pero no ponen notas de evaluación.
    
    Body esperado:
        estudiante_id, asignatura_id
        tipo: 'completiva' | 'extraordinaria' | 'especial'
        nota: número
    """
    if current_user.role != 'profesor':
        return JSONResponse({'error': 'Solo los profesores pueden registrar evaluaciones extra'}, status_code=403)
    
    data = await request.json()
    estudiante_id = data.get('estudiante_id')
    asignatura_id = data.get('asignatura_id')
    tipo = data.get('tipo', '').strip().lower()
    nota = data.get('nota')
    
    if not all([estudiante_id, asignatura_id, tipo]):
        return JSONResponse({'error': 'Faltan datos requeridos'}, status_code=400)
    if tipo not in ('completiva', 'extraordinaria', 'especial'):
        return JSONResponse({'error': 'tipo debe ser: completiva, extraordinaria o especial'}, status_code=400)
    if nota is None:
        return JSONResponse({'error': 'nota es requerida'}, status_code=400)
    try:
        nota_f = float(nota)
    except (ValueError, TypeError):
        return JSONResponse({'error': 'nota debe ser número'}, status_code=400)
    if nota_f < 0 or nota_f > 100:
        return JSONResponse({'error': 'nota debe estar entre 0 y 100'}, status_code=400)
    
    estudiante_obj = get_tenant_or_404(db, Estudiante, estudiante_id, current_user, name='estudiante')
    get_tenant_or_404(db, Asignatura, asignatura_id, current_user, name='asignatura')
    
    if not estudiante_obj.activo:
        return JSONResponse({'error': 'Estudiante retirado'}, status_code=403)
    
    # Verificar asignación del profesor
    tiene_asig = db.query(AsignacionProfesor).filter_by(
        profesor_id=current_user.id, curso_id=estudiante_obj.curso_id, asignatura_id=asignatura_id
    ).first()
    if not tiene_asig:
        return JSONResponse({'error': 'No tiene asignación a este curso/asignatura'}, status_code=403)
    
    ano = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    if not ano:
        return JSONResponse({'error': 'No hay año escolar activo'}, status_code=404)
    
    # Buscar la evaluación extra
    ev = db.query(EvaluacionExtraSecundaria).filter_by(
        estudiante_id=estudiante_id, asignatura_id=asignatura_id, ano_escolar_id=ano.id
    ).first()
    if not ev or ev.cf_original is None:
        return JSONResponse({
            'error': 'No hay CF calculado para este estudiante en esta asignatura. Primero deben estar las 4 competencias completas.'
        }, status_code=400)
    
    # No tiene sentido cargar completiva si aprobó normal (corte con CF redondeado)
    if round(ev.cf_original, 0) >= 70:
        return JSONResponse({
            'error': f'El estudiante aprobó el año normal (CF={ev.cf_original}). No necesita {tipo}.'
        }, status_code=400)
    
    # Cascada: solo permitir la fase pendiente
    fase = ev.fase_pendiente()
    if fase != tipo:
        if fase is None:
            return JSONResponse({
                'error': f'Este estudiante no tiene fase {tipo} pendiente. Condición final: {ev.condicion_final}'
            }, status_code=400)
        return JSONResponse({
            'error': f'Este estudiante tiene fase {fase} pendiente. No puede saltar a {tipo}.'
        }, status_code=400)
    
    # Asignar nota según el tipo
    if tipo == 'completiva':
        ev.cec = nota_f
    elif tipo == 'extraordinaria':
        ev.ceex = nota_f
    elif tipo == 'especial':
        ev.ce = nota_f
    
    ev.recalcular_todo()
    
    log_auditoria(db, 'EVALUACION_EXTRA_GUARDADA', 'evaluaciones_extra_secundaria', ev.id,
                  None, {'tipo': tipo, 'nota': nota_f, 'condicion_final': ev.condicion_final,
                         'estudiante_id': estudiante_id, 'asignatura_id': asignatura_id},
                  user=current_user, request=request)
    
    db.commit()
    return {
        'message': f'Evaluación {tipo} guardada',
        'evaluacion_extra': ev.to_dict(),
    }


@app.get("/api/calificaciones-secundaria/pendientes-evaluacion-extra")
async def get_pendientes_evaluacion_extra(request: Request, db: Session = Depends(get_db),
                                             current_user: Usuario = Depends(get_current_user)):
    """Lista de estudiantes que necesitan evaluación extra agrupados por tipo.
    
    Query params (opcionales):
        curso_id: filtrar por curso
        asignatura_id: filtrar por asignatura
        tipo: completiva | extraordinaria | especial
    
    Dirección/coordinación: ven todo el colegio.
    Profesor: solo de sus cursos asignados.
    """
    ano = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    if not ano:
        return {'pendientes': []}
    
    curso_id = request.query_params.get('curso_id')
    asignatura_id = request.query_params.get('asignatura_id')
    tipo_filtro = request.query_params.get('tipo', '').strip().lower()
    
    q = tenant_filter(db.query(EvaluacionExtraSecundaria), EvaluacionExtraSecundaria, current_user).filter_by(
        ano_escolar_id=ano.id
    )
    
    # Solo los que tienen CF reprobado (< 70 tras redondeo: 69.5 redondea a 70)
    q = q.filter(EvaluacionExtraSecundaria.cf_original != None)
    q = q.filter(EvaluacionExtraSecundaria.cf_original < 69.5)
    
    if asignatura_id:
        try:
            q = q.filter(EvaluacionExtraSecundaria.asignatura_id == int(asignatura_id))
        except (ValueError, TypeError):
            return JSONResponse({'error': 'asignatura_id inválido'}, status_code=400)
    
    # Filtro por curso (vía estudiante)
    if curso_id:
        try:
            cid = int(curso_id)
            est_ids = [e.id for e in db.query(Estudiante).filter_by(curso_id=cid, colegio_id=current_user.colegio_id).all()]
            q = q.filter(EvaluacionExtraSecundaria.estudiante_id.in_(est_ids))
        except (ValueError, TypeError):
            return JSONResponse({'error': 'curso_id inválido'}, status_code=400)
    
    # Profesor: solo cursos donde está asignado
    if current_user.role == 'profesor':
        asigs = db.query(AsignacionProfesor.curso_id, AsignacionProfesor.asignatura_id).filter_by(
            profesor_id=current_user.id
        ).all()
        if not asigs:
            return {'pendientes': []}
        cursos_prof = {a[0] for a in asigs}
        asig_prof = {a[1] for a in asigs}
        est_ids_prof = [e.id for e in db.query(Estudiante).filter(
            Estudiante.curso_id.in_(cursos_prof),
            Estudiante.colegio_id == current_user.colegio_id,
        ).all()]
        q = q.filter(EvaluacionExtraSecundaria.estudiante_id.in_(est_ids_prof))
        q = q.filter(EvaluacionExtraSecundaria.asignatura_id.in_(asig_prof))
    
    pendientes = []
    for ev in q.all():
        fase = ev.fase_pendiente()
        if fase is None:
            continue  # Ya completó la cascada (aprobado o reprobado final)
        if tipo_filtro and fase != tipo_filtro:
            continue
        
        est = ev.estudiante
        asig = ev.asignatura
        curso = est.curso if est else None
        
        pendientes.append({
            'evaluacion_id': ev.id,
            'estudiante_id': ev.estudiante_id,
            'estudiante_nombre': f"{est.apellido or ''}, {est.nombre or ''}".strip(', ') if est else None,
            'curso': curso.nombre_completo if curso else None,
            'curso_id': curso.id if curso else None,
            'asignatura_id': ev.asignatura_id,
            'asignatura_nombre': asig.nombre if asig else None,
            'cf_original': ev.cf_original,
            'fase_pendiente': fase,
            'cec': ev.cec,
            'completiva_final': ev.completiva_final,
            'ceex': ev.ceex,
            'extraordinaria_final': ev.extraordinaria_final,
            'ce': ev.ce,
            'especial_final': ev.especial_final,
        })
    
    return {'pendientes': pendientes, 'total': len(pendientes)}


# ============== PERÍODOS ACADÉMICOS ==============

@app.get("/api/periodos")
async def get_periodos(db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Obtener información de períodos del año activo"""
    ano = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    if not ano:
        return JSONResponse({'error': 'No hay año escolar activo'}, status_code=404)
    
    return {
        'ano_escolar': ano.nombre,
        'periodo_activo': ano.periodo_activo,
        'periodos': [
            {
                'numero': 1,
                'inicio': ano.p1_inicio.isoformat() if ano.p1_inicio else None,
                'fin': ano.p1_fin.isoformat() if ano.p1_fin else None,
                'cerrado': ano.p1_cerrado
            },
            {
                'numero': 2,
                'inicio': ano.p2_inicio.isoformat() if ano.p2_inicio else None,
                'fin': ano.p2_fin.isoformat() if ano.p2_fin else None,
                'cerrado': ano.p2_cerrado
            },
            {
                'numero': 3,
                'inicio': ano.p3_inicio.isoformat() if ano.p3_inicio else None,
                'fin': ano.p3_fin.isoformat() if ano.p3_fin else None,
                'cerrado': ano.p3_cerrado
            },
            {
                'numero': 4,
                'inicio': ano.p4_inicio.isoformat() if ano.p4_inicio else None,
                'fin': ano.p4_fin.isoformat() if ano.p4_fin else None,
                'cerrado': ano.p4_cerrado
            }
        ]
    }

@app.post("/api/periodos/{periodo}/abrir")
async def abrir_periodo(periodo, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Abrir un período para edición"""
    periodo = int(periodo)
    if periodo < 1 or periodo > 4:
        return JSONResponse({'error': 'Período inválido'}, status_code=400)
    
    ano = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    if not ano:
        return JSONResponse({'error': 'No hay año escolar activo'}, status_code=404)
    
    setattr(ano, f'p{periodo}_cerrado', False)
    ano.periodo_activo = periodo
    
    log_auditoria(db, 'ABRIR_PERIODO', 'ano_escolar', ano.id, None, {'periodo': periodo}, user=current_user, request=request)
    db.commit()
    
    return {'message': f'Período {periodo} abierto'}

@app.post("/api/periodos/{periodo}/cerrar")
async def cerrar_periodo(periodo, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Cerrar un período"""
    periodo = int(periodo)
    if periodo < 1 or periodo > 4:
        return JSONResponse({'error': 'Período inválido'}, status_code=400)
    
    ano = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    if not ano:
        return JSONResponse({'error': 'No hay año escolar activo'}, status_code=404)
    
    setattr(ano, f'p{periodo}_cerrado', True)
    
    # Si cerramos el período activo, avanzar al siguiente
    if ano.periodo_activo == periodo and periodo < 4:
        ano.periodo_activo = periodo + 1
    elif periodo == 4:
        ano.periodo_activo = None
    
    log_auditoria(db, 'CERRAR_PERIODO', 'ano_escolar', ano.id, None, {'periodo': periodo}, user=current_user, request=request)
    db.commit()
    
    return {'message': f'Período {periodo} cerrado'}

@app.put("/api/periodos/configurar")
async def configurar_periodos(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Configurar fechas de períodos"""
    data = await request.json()
    
    ano = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    if not ano:
        return JSONResponse({'error': 'No hay año escolar activo'}, status_code=404)
    
    for p in range(1, 5):
        if f'p{p}_inicio' in data:
            val = data[f'p{p}_inicio']
            if val and isinstance(val, str):
                try:
                    val = date.fromisoformat(val)
                except (ValueError, TypeError):
                    val = None
            setattr(ano, f'p{p}_inicio', val)
        if f'p{p}_fin' in data:
            val = data[f'p{p}_fin']
            if val and isinstance(val, str):
                try:
                    val = date.fromisoformat(val)
                except (ValueError, TypeError):
                    val = None
            setattr(ano, f'p{p}_fin', val)
    
    if 'periodo_activo' in data:
        ano.periodo_activo = data['periodo_activo']
    
    db.commit()
    return {'message': 'Períodos configurados'}

@app.post("/api/periodos/permiso-temporal")
async def crear_permiso_temporal(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Crear permiso temporal para que un profesor califique en período cerrado"""
    data = await request.json()
    
    profesor_id = data.get('profesor_id')
    if not profesor_id:
        return JSONResponse({'error': 'Profesor requerido'}, status_code=400)
    
    horas = data.get('horas', 24)  # Por defecto 24 horas
    fecha_fin = now_rd() + timedelta(hours=horas)
    
    permiso = PermisoTemporalCalificacion(
        colegio_id=current_user.colegio_id,
        profesor_id=profesor_id,
        curso_id=data.get('curso_id'),
        asignatura_id=data.get('asignatura_id'),
        periodo=data.get('periodo'),
        fecha_fin=fecha_fin,
        motivo=data.get('motivo', 'Corrección de calificaciones'),
        otorgado_por=current_user.id
    )
    db.add(permiso)
    db.commit()
    
    log_auditoria(db, 'CREAR_PERMISO_TEMPORAL', 'permisos_temporales', permiso.id, None, {
        'profesor_id': profesor_id,
        'horas': horas,
        'motivo': data.get('motivo')
    }, user=current_user, request=request)
    
    return JSONResponse({
        'message': f'Permiso otorgado hasta {fecha_fin.strftime("%d/%m/%Y %H:%M")}',
        'id': permiso.id
    }, status_code=201)

@app.get("/api/periodos/permisos-temporales")
async def get_permisos_temporales(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Ver permisos temporales activos"""
    
    permisos = tenant_filter(db.query(PermisoTemporalCalificacion), PermisoTemporalCalificacion, current_user).filter(
        PermisoTemporalCalificacion.activo == True,
        PermisoTemporalCalificacion.fecha_fin > now_rd()
    ).all()
    
    return [{
        'id': p.id,
        'profesor': p.profesor.nombre_completo if p.profesor else None,
        'curso': p.curso.nombre_completo if p.curso else 'Todos',
        'asignatura': p.asignatura.nombre if p.asignatura else 'Todas',
        'periodo': p.periodo or 'Todos',
        'fecha_fin': p.fecha_fin.isoformat() if p.fecha_fin else None,
        'motivo': p.motivo
    } for p in permisos]

@app.delete("/api/periodos/permiso-temporal/{id}")
async def revocar_permiso_temporal(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Revocar permiso temporal"""
    
    permiso = get_tenant_or_404(db, PermisoTemporalCalificacion, id, current_user, name='permiso')
    permiso.activo = False
    db.commit()
    
    log_auditoria(db, 'REVOCAR_PERMISO_TEMPORAL', 'permisos_temporales', id, user=current_user, request=request)
    
    return {'message': 'Permiso revocado'}

# ============== SOLICITUDES DE EDICIÓN ==============

@app.get("/api/solicitudes-edicion")
async def get_solicitudes_edicion(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Obtener solicitudes de edición pendientes"""
    solicitudes = tenant_filter(db.query(SolicitudEdicionNota), SolicitudEdicionNota, current_user).filter_by(estado='pendiente').order_by(SolicitudEdicionNota.fecha_solicitud.desc()).all()
    
    return [{
        'id': s.id,
        'profesor': s.profesor.nombre_completo if s.profesor else None,
        'estudiante': s.calificacion.estudiante.nombre_completo if s.calificacion and s.calificacion.estudiante else None,
        'asignatura': s.calificacion.asignatura.nombre if s.calificacion and s.calificacion.asignatura else None,
        'periodo': s.periodo,
        'campo': s.campo,
        'valor_actual': s.valor_actual,
        'valor_nuevo': s.valor_nuevo,
        'motivo': s.motivo,
        'fecha_solicitud': s.fecha_solicitud.isoformat() if s.fecha_solicitud else None,
        'estado': s.estado
    } for s in solicitudes]

@app.post("/api/solicitudes-edicion")
async def crear_solicitud_edicion(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Crear solicitud de edición de nota en período cerrado"""
    data = await request.json()
    
    solicitud = SolicitudEdicionNota(
        colegio_id=current_user.colegio_id,
        calificacion_id=data['calificacion_id'],
        profesor_id=current_user.id,
        periodo=data['periodo'],
        campo=data['campo'],
        valor_actual=data.get('valor_actual'),
        valor_nuevo=data['valor_nuevo'],
        motivo=data['motivo']
    )
    db.add(solicitud)
    db.commit()
    
    return JSONResponse({'message': 'Solicitud creada', 'id': solicitud.id}, status_code=201)

@app.post("/api/solicitudes-edicion/{id}/aprobar")
async def aprobar_solicitud_edicion(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Aprobar solicitud y aplicar cambio"""
    solicitud = get_tenant_or_404(db, SolicitudEdicionNota, id, current_user, name='solicitudedicionnota')
    data = await request.json()
    
    solicitud.estado = 'aprobada'
    solicitud.revisado_por = current_user.id
    solicitud.fecha_revision = now_rd()
    solicitud.comentario_revision = data.get('comentario', '')
    
    # Aplicar el cambio
    calif = solicitud.calificacion
    setattr(calif, solicitud.campo, solicitud.valor_nuevo)
    
    # Recalcular PC y CF
    periodo = solicitud.periodo
    pc_calculado = calif.calcular_pc(periodo)
    if pc_calculado is not None:
        setattr(calif, f'pc{periodo}', pc_calculado)
    
    cf_calculado = calif.calcular_cf()
    if cf_calculado is not None:
        calif.cf = cf_calculado
        calif.literal = calif.get_literal(cf_calculado)
    
    log_auditoria(db, 'EDICION_APROBADA', 'calificaciones', calif.id, 
                  {'campo': solicitud.campo, 'valor_anterior': solicitud.valor_actual},
                  {'campo': solicitud.campo, 'valor_nuevo': solicitud.valor_nuevo}, user=current_user, request=request)
    
    db.commit()
    return {'message': 'Solicitud aprobada y cambio aplicado'}

@app.post("/api/solicitudes-edicion/{id}/rechazar")
async def rechazar_solicitud_edicion(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Rechazar solicitud de edición"""
    solicitud = get_tenant_or_404(db, SolicitudEdicionNota, id, current_user, name='solicitudedicionnota')
    data = await request.json()
    
    solicitud.estado = 'rechazada'
    solicitud.revisado_por = current_user.id
    solicitud.fecha_revision = now_rd()
    solicitud.comentario_revision = data.get('comentario', 'Rechazada sin comentario')
    
    db.commit()
    return {'message': 'Solicitud rechazada'}

# ============== PLANTILLAS ==============

@app.get("/api/plantillas")
async def get_plantillas(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    plantillas = tenant_filter(db.query(PlantillaMensaje), PlantillaMensaje, current_user).all()
    return [{
        'id': p.id,
        'nombre': p.nombre,
        'categoria': p.categoria,
        'asunto': p.asunto,
        'contenido': p.contenido
    } for p in plantillas]

@app.post("/api/plantillas")
async def crear_plantilla(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion', 'coordinador'))):
    data = await request.json()
    
    plantilla = PlantillaMensaje(
        colegio_id=current_user.colegio_id,
        nombre=data['nombre'],
        categoria=data.get('categoria', 'general'),
        asunto=data.get('asunto'),
        contenido=data['contenido'],
        creado_por=current_user.id
    )
    db.add(plantilla)
    db.commit()
    return JSONResponse({'message': 'Plantilla creada', 'id': plantilla.id}, status_code=201)

# ============== DASHBOARD ==============

@app.get("/api/dashboard/stats")
async def get_dashboard_stats(db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    config = tenant_filter(db.query(ConfiguracionColegio), ConfiguracionColegio, current_user).first()
    
    ck = f'stats:{current_user.colegio_id}'
    cached = cache_get(ck)
    if cached: return cached
    
    stats = {
        'estudiantes': tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(activo=True).count(),
        'profesores': tenant_filter(db.query(Usuario), Usuario, current_user).filter_by(role='profesor', activo=True).count(),
        'cursos': tenant_filter(db.query(Curso), Curso, current_user).filter_by(activo=True).count(),
        'reportes_pendientes': tenant_filter(db.query(ReporteConducta), ReporteConducta, current_user).filter_by(estado='pendiente').count(),
        'casos_psicologia': tenant_filter(db.query(CasoPsicologia), CasoPsicologia, current_user).filter(CasoPsicologia.estado != 'atendido').count(),
        'colegio': {
            'nombre': config.nombre if config else 'Educa One',
            'logo': config.logo if config else None
        }
    }
    cache_set(ck, stats, 30)
    return stats

@app.get("/api/dashboard/alertas")
async def get_dashboard_alertas(db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    alertas = []
    
    # ─────────────────────────────────────────────────────────────────
    # ALERTA: estudiantes con 3+ ausencias consecutivas (solo direccion/coordinador)
    # Detecta estudiantes que tienen al menos 3 días LECTIVOS seguidos marcados
    # como ausentes. Una ausencia "del día" es: el estudiante no tiene NINGUNA
    # marca de presente o tardanza ese día, pero sí tiene marca de ausente
    # (en al menos una asignatura).
    # ─────────────────────────────────────────────────────────────────
    if current_user.role in ('direccion', 'coordinador') and current_user.colegio_id:
        from datetime import timedelta as _td
        hoy = today_rd()
        # Mirar los últimos 14 días (cubre 2 semanas)
        desde = hoy - _td(days=14)
        
        # Traer todas las asistencias del período por estudiante por día
        rows = (
            tenant_filter(db.query(Asistencia), Asistencia, current_user)
            .filter(Asistencia.fecha >= desde, Asistencia.fecha <= hoy)
            .all()
        )
        # Agrupar por (estudiante, fecha) → estados de ese día
        from collections import defaultdict as _dd
        dias_est = _dd(set)
        for a in rows:
            dias_est[(a.estudiante_id, a.fecha)].add(a.estado)
        
        # Para cada estudiante, determinar el estado del día (presente/ausente/tardanza/sin_marca)
        # y buscar racha de 3+ ausencias consecutivas
        est_dias = _dd(dict)
        for (est_id, fecha), estados in dias_est.items():
            if 'presente' in estados:
                est_dias[est_id][fecha] = 'P'
            elif 'tardanza' in estados:
                est_dias[est_id][fecha] = 'T'
            elif 'ausente' in estados:
                est_dias[est_id][fecha] = 'A'
            else:
                est_dias[est_id][fecha] = '?'
        
        # Para cada estudiante, ordenar fechas y buscar 3+ ausencias seguidas
        # (consecutivas en días con marca, ignorando días sin registro)
        estudiantes_con_racha = []
        for est_id, dias_dict in est_dias.items():
            fechas_ordenadas = sorted(dias_dict.keys())
            # Construir secuencia ignorando días sin marca: solo consideramos
            # días donde HAY estado (P/T/A). Una racha de 3 A consecutivas en
            # esa secuencia → alerta.
            secuencia = [(f, dias_dict[f]) for f in fechas_ordenadas if dias_dict[f] in ('P','T','A')]
            racha = 0
            max_racha = 0
            for _, estado in secuencia:
                if estado == 'A':
                    racha += 1
                    if racha > max_racha:
                        max_racha = racha
                else:
                    racha = 0
            if max_racha >= 3:
                estudiantes_con_racha.append((est_id, max_racha))
        
        if estudiantes_con_racha:
            # Traer nombres
            est_ids = [e[0] for e in estudiantes_con_racha]
            ests = (tenant_filter(db.query(Estudiante), Estudiante, current_user)
                    .filter(Estudiante.id.in_(est_ids), Estudiante.activo == True).all())
            est_dict = {e.id: e for e in ests}
            
            count = len(estudiantes_con_racha)
            ejemplos = []
            for est_id, racha in sorted(estudiantes_con_racha, key=lambda x: -x[1])[:3]:
                est = est_dict.get(est_id)
                if est:
                    ejemplos.append(f"{est.nombre_completo} ({racha} días)")
            
            alertas.append({
                'tipo': 'inasistencia',
                'prioridad': 'alta',
                'mensaje': f'{count} estudiante(s) con 3+ ausencias consecutivas: {", ".join(ejemplos)}' + ('...' if count > 3 else ''),
                'count': count,
                'link': '/asistencia'
            })
    
    # Comunicados no leídos
    query = tenant_filter(db.query(Comunicado), Comunicado, current_user).filter_by(activo=True)
    if current_user.role == 'profesor':
        query = query.filter_by(para_profesores=True)
    elif current_user.role == 'coordinador':
        query = query.filter_by(para_coordinadores=True)
    elif current_user.role == 'psicologia':
        query = query.filter_by(para_psicologia=True)
    
    comunicados_ids = [c.id for c in query.all()]
    leidos_ids = [cl.comunicado_id for cl in tenant_filter(db.query(ComunicadoLeido), ComunicadoLeido, current_user).filter_by(usuario_id=current_user.id).all()]
    no_leidos = [cid for cid in comunicados_ids if cid not in leidos_ids]
    
    if no_leidos:
        alertas.append({
            'tipo': 'comunicado',
            'prioridad': 'alta',
            'mensaje': f'{len(no_leidos)} comunicado(s) sin leer',
            'count': len(no_leidos),
            'link': '/comunicacion'
        })
    
    # Reportes pendientes - filtrados por rol
    if current_user.role == 'profesor':
        # Profesor solo ve reportes que él creó
        reportes_count = tenant_filter(db.query(ReporteConducta), ReporteConducta, current_user).filter_by(
            reportado_por=current_user.id, estado='pendiente'
        ).count()
        if reportes_count > 0:
            alertas.append({
                'tipo': 'reporte',
                'prioridad': 'media',
                'mensaje': f'{reportes_count} reporte(s) tuyo(s) pendiente(s) de respuesta',
                'count': reportes_count,
                'link': '/reportes'
            })
    elif current_user.role in ['direccion', 'coordinador']:
        reportes_count = tenant_filter(db.query(ReporteConducta), ReporteConducta, current_user).filter_by(estado='pendiente').count()
        if reportes_count > 0:
            alertas.append({
                'tipo': 'reporte',
                'prioridad': 'alta' if reportes_count > 5 else 'media',
                'mensaje': f'{reportes_count} reportes de conducta pendientes',
                'count': reportes_count,
                'link': '/reportes'
            })
    
    # Casos de psicología - filtrados por rol
    if current_user.role == 'psicologia':
        # Psicología ve todos los pendientes
        casos_pendientes = tenant_filter(db.query(CasoPsicologia), CasoPsicologia, current_user).filter_by(estado='pendiente').count()
        casos_urgentes = tenant_filter(db.query(CasoPsicologia), CasoPsicologia, current_user).filter_by(urgencia='urgente', estado='pendiente').count()
        if casos_urgentes > 0:
            alertas.append({
                'tipo': 'psicologia',
                'prioridad': 'alta',
                'mensaje': f'🔴 {casos_urgentes} caso(s) urgente(s) pendiente(s)',
                'count': casos_urgentes,
                'link': '/psicologia'
            })
        if casos_pendientes > casos_urgentes:
            alertas.append({
                'tipo': 'psicologia',
                'prioridad': 'media',
                'mensaje': f'{casos_pendientes - casos_urgentes} caso(s) normal(es) pendiente(s)',
                'count': casos_pendientes - casos_urgentes,
                'link': '/psicologia'
            })
    elif current_user.role == 'profesor':
        # Profesor ve si sus solicitudes fueron atendidas (recomendaciones nuevas)
        mis_solicitudes_atendidas = tenant_filter(db.query(CasoPsicologia), CasoPsicologia, current_user).filter(
            CasoPsicologia.solicitado_por == current_user.id,
            CasoPsicologia.estado == 'atendido',
            CasoPsicologia.recomendacion_profesor != None
        ).count()
        if mis_solicitudes_atendidas > 0:
            alertas.append({
                'tipo': 'psicologia',
                'prioridad': 'media',
                'mensaje': f'{mis_solicitudes_atendidas} caso(s) atendido(s) con recomendación para ti',
                'count': mis_solicitudes_atendidas,
                'link': '/psicologia'
            })
    elif current_user.role in ['direccion', 'coordinador']:
        casos_urgentes = tenant_filter(db.query(CasoPsicologia), CasoPsicologia, current_user).filter_by(urgencia='urgente', estado='pendiente').count()
        if casos_urgentes > 0:
            alertas.append({
                'tipo': 'psicologia',
                'prioridad': 'alta',
                'mensaje': f'{casos_urgentes} casos urgentes de psicología',
                'count': casos_urgentes,
                'link': '/psicologia'
            })
    
    # Mensajes no leídos
    mensajes_no_leidos = tenant_filter(db.query(Mensaje), Mensaje, current_user).filter_by(destinatario_id=current_user.id, leido=False).count()
    if mensajes_no_leidos > 0:
        alertas.append({
            'tipo': 'mensaje',
            'prioridad': 'media',
            'mensaje': f'{mensajes_no_leidos} mensaje(s) sin leer',
            'count': mensajes_no_leidos,
            'link': '/comunicacion'
        })
    
    # Asistencia no registrada hoy (solo cursos del horario de HOY)
    if current_user.role == 'profesor':
        dias_semana_alert = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
        dia_hoy_alert = dias_semana_alert[today_rd().weekday()]
        
        # Solo cursos que tiene en el horario de hoy
        horarios_hoy_alert = tenant_filter(db.query(Horario), Horario, current_user).filter_by(
            profesor_id=current_user.id, dia=dia_hoy_alert, activo=True
        ).filter(Horario.tipo_bloque == 'clase').all()
        
        cursos_hoy = set()
        asig_hoy = set()
        for h in horarios_hoy_alert:
            if h.curso_id and h.asignatura_id:
                cursos_hoy.add((h.curso_id, h.asignatura_id))
        
        cursos_sin_asistencia = set()
        for curso_id, asig_id in cursos_hoy:
            asistencia_hoy = tenant_filter(db.query(Asistencia), Asistencia, current_user).filter_by(
                curso_id=curso_id,
                asignatura_id=asig_id,
                fecha=today_rd()
            ).first()
            if not asistencia_hoy:
                cursos_sin_asistencia.add(curso_id)
        
        if cursos_sin_asistencia:
            alertas.append({
                'tipo': 'asistencia',
                'prioridad': 'media',
                'mensaje': f'Asistencia pendiente en {len(cursos_sin_asistencia)} curso(s)',
                'count': len(cursos_sin_asistencia),
                'link': '/asistencia'
            })
    
    # Solicitudes de edición pendientes (solo dirección)
    if current_user.role == 'direccion':
        solicitudes = tenant_filter(db.query(SolicitudEdicionNota), SolicitudEdicionNota, current_user).filter_by(estado='pendiente').count()
        if solicitudes > 0:
            alertas.append({
                'tipo': 'solicitud_edicion',
                'prioridad': 'media',
                'mensaje': f'{solicitudes} solicitud(es) de edición de notas pendiente(s)',
                'count': solicitudes,
                'link': '/academico'
            })
    
    # ─────────────────────────────────────────────────────────────────
    # ALERTAS SECUNDARIA v2.13
    # ─────────────────────────────────────────────────────────────────
    
    # Año escolar activo (común a varias alertas)
    ano_activo = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    
    if ano_activo:
        # ALERTA: Evaluaciones extra pendientes (profesor: las suyas; dirección: todas)
        # Una evaluación extra está "pendiente" si tiene fase_pendiente != null
        # (cascada completiva/extraordinaria/especial sin nota cargada).
        # Filtramos en Python para reusar la lógica del modelo en lugar de duplicarla en SQL.
        if current_user.role in ('profesor', 'direccion', 'coordinador'):
            evals_extra = tenant_filter(
                db.query(EvaluacionExtraSecundaria), EvaluacionExtraSecundaria, current_user
            ).filter_by(ano_escolar_id=ano_activo.id).all()
            
            # Filtrar las que tienen fase pendiente
            extras_pendientes = [e for e in evals_extra if e.fase_pendiente()]
            
            # Si es profesor, filtrar solo a sus asignaciones
            if current_user.role == 'profesor':
                asignaciones = db.query(AsignacionProfesor).filter_by(
                    profesor_id=current_user.id
                ).all()
                # Set de (curso_id, asignatura_id) del profesor
                asig_set = set()
                # Para mapear EvaluacionExtra → (curso, asignatura) necesitamos el curso del estudiante
                est_ids = [e.estudiante_id for e in extras_pendientes]
                est_cursos = {}
                if est_ids:
                    rows = db.query(Estudiante.id, Estudiante.curso_id).filter(
                        Estudiante.id.in_(est_ids)
                    ).all()
                    est_cursos = {r[0]: r[1] for r in rows}
                
                for a in asignaciones:
                    asig_set.add((a.curso_id, a.asignatura_id))
                
                extras_pendientes = [
                    e for e in extras_pendientes
                    if (est_cursos.get(e.estudiante_id), e.asignatura_id) in asig_set
                ]
            
            n = len(extras_pendientes)
            if n > 0:
                # Conteo por fase para mensaje más informativo
                fases = {'completiva': 0, 'extraordinaria': 0, 'especial': 0}
                for e in extras_pendientes:
                    fase = e.fase_pendiente()
                    if fase in fases:
                        fases[fase] += 1
                
                # Construir desglose ("12 completiva, 3 extraordinaria, 1 especial")
                partes = [f"{v} {k}" for k, v in fases.items() if v > 0]
                desglose = ', '.join(partes)
                
                # Prioridad: especial > extraordinaria > completiva (más urgente = última oportunidad)
                if fases['especial'] > 0:
                    prioridad = 'alta'
                elif fases['extraordinaria'] > 0:
                    prioridad = 'alta'
                else:
                    prioridad = 'media'
                
                if current_user.role == 'profesor':
                    msg = f'{n} evaluación(es) extra pendiente(s) de cargar: {desglose}'
                else:
                    msg = f'{n} estudiante(s) con evaluación extra pendiente: {desglose}'
                
                alertas.append({
                    'tipo': 'evaluacion_extra_pendiente',
                    'prioridad': prioridad,
                    'mensaje': msg,
                    'count': n,
                    'link': '/evaluaciones-extra'
                })
        
        # ALERTA: Período activo cerca del cierre (14 días o menos) con competencias
        # secundaria sin cargar. Avisa al profesor que se le acerca la fecha límite.
        # Solo para profesores.
        if current_user.role == 'profesor':
            from datetime import timedelta as _td
            hoy = today_rd()
            periodo_activo = ano_activo.periodo_activo
            
            if periodo_activo and 1 <= periodo_activo <= 4:
                fin_periodo = getattr(ano_activo, f'p{periodo_activo}_fin', None)
                cerrado = getattr(ano_activo, f'p{periodo_activo}_cerrado', False)
                
                if fin_periodo and not cerrado:
                    dias_restantes = (fin_periodo - hoy).days
                    
                    if 0 <= dias_restantes <= 14:
                        # Buscar competencias secundaria con período activo SIN nota
                        # del profesor actual. Aproximación: contar cuántas (estudiante,
                        # asignatura, competencia) no tienen valor en este período.
                        asignaciones = db.query(AsignacionProfesor).filter_by(
                            profesor_id=current_user.id
                        ).all()
                        
                        n_pendientes_cargar = 0
                        cursos_pendientes = set()
                        for asig in asignaciones:
                            # Solo cursos de secundaria
                            if not _es_curso_secundaria(db, asig.curso_id):
                                continue
                            
                            # Estudiantes del curso
                            ests = db.query(Estudiante.id).filter_by(
                                curso_id=asig.curso_id,
                                colegio_id=current_user.colegio_id,
                                activo=True
                            ).all()
                            est_ids = [e[0] for e in ests]
                            if not est_ids:
                                continue
                            
                            # CalificacionSecundaria del período actual para esta asig
                            comps_existentes = tenant_filter(
                                db.query(CalificacionSecundaria),
                                CalificacionSecundaria, current_user
                            ).filter_by(
                                asignatura_id=asig.asignatura_id,
                                ano_escolar_id=ano_activo.id
                            ).filter(
                                CalificacionSecundaria.estudiante_id.in_(est_ids)
                            ).all()
                            
                            # Set de (estudiante_id, competencia_numero) que SÍ tienen valor del período
                            campo_p = f'p{periodo_activo}'
                            con_nota = set()
                            for c in comps_existentes:
                                if getattr(c, campo_p, None) is not None:
                                    con_nota.add((c.estudiante_id, c.competencia_numero))
                            
                            # Faltantes: cada estudiante × 4 competencias = 4 entradas que deberían existir
                            total_esperado = len(est_ids) * 4
                            n_pendientes_cargar += total_esperado - len(con_nota)
                            if total_esperado - len(con_nota) > 0:
                                cursos_pendientes.add(asig.curso_id)
                        
                        if n_pendientes_cargar > 0:
                            urg = 'alta' if dias_restantes <= 7 else 'media'
                            alertas.append({
                                'tipo': 'cierre_periodo_secundaria',
                                'prioridad': urg,
                                'mensaje': (
                                    f'Período P{periodo_activo} cierra en {dias_restantes} día(s). '
                                    f'{n_pendientes_cargar} nota(s) de competencia(s) sin cargar en '
                                    f'{len(cursos_pendientes)} curso(s).'
                                ),
                                'count': n_pendientes_cargar,
                                'link': '/academico'
                            })
        
        # ALERTA: Dirección — % de profesores que NO han cargado todas las
        # competencias del período activo (solo si el período está cerca de cerrar).
        if current_user.role in ('direccion', 'coordinador'):
            from datetime import timedelta as _td
            hoy = today_rd()
            periodo_activo = ano_activo.periodo_activo
            
            if periodo_activo and 1 <= periodo_activo <= 4:
                fin_periodo = getattr(ano_activo, f'p{periodo_activo}_fin', None)
                cerrado = getattr(ano_activo, f'p{periodo_activo}_cerrado', False)
                
                if fin_periodo and not cerrado:
                    dias_restantes = (fin_periodo - hoy).days
                    
                    if 0 <= dias_restantes <= 7:
                        # Contar profesores con cursos secundaria que tengan competencias sin cargar
                        # en el período actual. Aproximación rápida: contamos cuántos pares
                        # (curso, asignatura) de secundaria tienen alguna competencia incompleta.
                        # Nota: Curso.nivel no existe; el nivel está en Grado vía grado_id.
                        asignaciones_sec = db.query(AsignacionProfesor).join(
                            Curso, AsignacionProfesor.curso_id == Curso.id
                        ).join(
                            Grado, Curso.grado_id == Grado.id
                        ).filter(
                            Curso.colegio_id == current_user.colegio_id,
                            Grado.nivel == 'secundaria'
                        ).all()
                        
                        profesores_atrasados = set()
                        for asig in asignaciones_sec:
                            # Estudiantes del curso
                            ests = db.query(Estudiante.id).filter_by(
                                curso_id=asig.curso_id,
                                colegio_id=current_user.colegio_id,
                                activo=True
                            ).all()
                            est_ids = [e[0] for e in ests]
                            if not est_ids:
                                continue
                            
                            # Competencias del período actual cargadas
                            comps = tenant_filter(
                                db.query(CalificacionSecundaria),
                                CalificacionSecundaria, current_user
                            ).filter_by(
                                asignatura_id=asig.asignatura_id,
                                ano_escolar_id=ano_activo.id
                            ).filter(
                                CalificacionSecundaria.estudiante_id.in_(est_ids)
                            ).all()
                            
                            campo_p = f'p{periodo_activo}'
                            con_nota = sum(
                                1 for c in comps if getattr(c, campo_p, None) is not None
                            )
                            esperado = len(est_ids) * 4
                            if con_nota < esperado:
                                profesores_atrasados.add(asig.profesor_id)
                        
                        if profesores_atrasados:
                            alertas.append({
                                'tipo': 'profesores_atrasados_secundaria',
                                'prioridad': 'alta',
                                'mensaje': (
                                    f'P{periodo_activo} cierra en {dias_restantes} día(s). '
                                    f'{len(profesores_atrasados)} profesor(es) tienen competencias '
                                    f'sin cargar en secundaria.'
                                ),
                                'count': len(profesores_atrasados),
                                'link': '/academico'
                            })
    
    return alertas

@app.get("/api/dashboard/actividad-reciente")
async def get_actividad_reciente(db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    actividades = []
    
    # Últimos comunicados
    comunicados = tenant_filter(db.query(Comunicado), Comunicado, current_user).filter_by(activo=True).order_by(Comunicado.fecha.desc()).limit(3).all()
    for c in comunicados:
        actividades.append({
            'tipo': 'comunicado',
            'titulo': c.titulo,
            'fecha': c.fecha.isoformat() if c.fecha else None,
            'autor': c.autor.nombre_completo if c.autor else None
        })
    
    # Últimos reportes
    reportes = tenant_filter(db.query(ReporteConducta), ReporteConducta, current_user).order_by(ReporteConducta.fecha.desc()).limit(3).all()
    for r in reportes:
        actividades.append({
            'tipo': 'reporte',
            'titulo': r.titulo,
            'fecha': r.fecha.isoformat() if r.fecha else None,
            'estado': r.estado
        })
    
    return actividades[:5]

# ============== DASHBOARD GRÁFICOS REALES ==============

@app.get("/api/dashboard/graficos")
async def get_dashboard_graficos(db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Datos para gráficos"""
    try:
        result = get_graficos(db, current_user)
        return result
    except Exception as e:
        logger.error(f"Error en graficos: {e}", exc_info=True)
        return {
            'promedios_por_grado': [],
            'estado_estudiantes': [
                {'nombre': 'Aprobados', 'cantidad': 0, 'color': '#10b981'},
                {'nombre': 'Reprobados', 'cantidad': 0, 'color': '#ef4444'},
                {'nombre': 'En Proceso', 'cantidad': 0, 'color': '#f59e0b'}
            ],
            'asistencia_resumen': {'presentes': 0, 'ausentes': 0, 'tardanzas': 0, 'porcentaje_asistencia': 0,
                                   'periodo_inicio': None, 'periodo_fin': None},
            'asistencia_hoy': {'fecha': None, 'presentes': 0, 'ausentes': 0, 'tardanzas': 0,
                                'excusas': 0, 'no_registrados': 0, 'total_estudiantes': 0, 'porcentaje_asistencia': 0},
            'asistencia_por_materia': [],
            '_error': str(e),
            '_type': type(e).__name__
        }

@app.get("/api/dashboard/profesor")
async def get_dashboard_profesor(db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Dashboard específico para profesores. Si no es profesor devuelve vacío (no error)."""
    if current_user.role != 'profesor':
        # No es error — el frontend puede llamar este endpoint desde dashboard general
        return {'es_profesor': False, 'horarios_hoy': [], 'clases_pendientes': [], 'alertas': []}
    
    hoy = today_rd()
    ahora = now_rd()
    hora_actual = ahora.strftime('%H:%M')
    dias_semana = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
    dia_semana = dias_semana[hoy.weekday()]
    
    # Horario de hoy (incluir clases Y horas libres, excluir recreos)
    horarios_hoy = tenant_filter(db.query(Horario), Horario, current_user).options(
        joinedload(Horario.asignatura), joinedload(Horario.curso).joinedload(Curso.grado), joinedload(Horario.curso).joinedload(Curso.tanda)
    ).filter_by(
        profesor_id=current_user.id,
        dia=dia_semana,
        activo=True
    ).filter(Horario.tipo_bloque.in_(['clase', 'libre'])).order_by(Horario.hora_inicio).all()
    
    # Verificar si ya pasaron todas las clases de HOY (solo aplica al día actual)
    todas_pasaron = False
    if horarios_hoy:
        ultima_hora_fin = max(h.hora_fin for h in horarios_hoy)
        if hora_actual > ultima_hora_fin:
            todas_pasaron = True
    
    # Si no hay clases hoy, o ya pasaron todas, buscar próximo día con clases
    dia_mostrar = dia_semana
    es_proximo_dia = False
    if not horarios_hoy or todas_pasaron:
        horarios_hoy_original = horarios_hoy  # guardar por si acaso
        for i in range(1, 7):  # Buscar en los próximos 6 días
            proximo_dia = dias_semana[(hoy.weekday() + i) % 7]
            horarios_proximo = tenant_filter(db.query(Horario), Horario, current_user).options(
                joinedload(Horario.asignatura), joinedload(Horario.curso).joinedload(Curso.grado), joinedload(Horario.curso).joinedload(Curso.tanda)
            ).filter_by(
                profesor_id=current_user.id,
                dia=proximo_dia,
                activo=True
            ).filter(Horario.tipo_bloque.in_(['clase', 'libre'])).order_by(Horario.hora_inicio).all()
            if horarios_proximo:
                horarios_hoy = horarios_proximo
                dia_mostrar = proximo_dia
                es_proximo_dia = True
                break
    
    horario_dia = [{
        'id': h.id,
        'hora_inicio': h.hora_inicio,
        'hora_fin': h.hora_fin,
        'asignatura': h.asignatura.nombre if h.asignatura else None,
        'curso': h.curso.nombre_completo if h.curso else None,
        'curso_id': h.curso_id,
        'aula': h.aula,
        'tipo_bloque': h.tipo_bloque
    } for h in horarios_hoy]
    
    # Cursos asignados - mostrar TODAS las asignaciones (curso + asignatura)
    asignaciones = tenant_filter(db.query(AsignacionProfesor), AsignacionProfesor, current_user).filter_by(profesor_id=current_user.id, activo=True).all()
    # v2.13.28: contar estudiantes por curso en UNA query (en vez de una por curso)
    from sqlalchemy import func as _func
    curso_ids_asig = list({a.curso_id for a in asignaciones})
    conteo_por_curso = {}
    if curso_ids_asig:
        filas = (tenant_filter(db.query(Estudiante.curso_id, _func.count(Estudiante.id)), Estudiante, current_user)
                 .filter(Estudiante.curso_id.in_(curso_ids_asig), Estudiante.activo == True)
                 .group_by(Estudiante.curso_id).all())
        conteo_por_curso = {cid: n for cid, n in filas}
    
    cursos_asignados = []
    for a in asignaciones:
        estudiantes_count = conteo_por_curso.get(a.curso_id, 0)
        cursos_asignados.append({
            'curso_id': a.curso_id,
            'curso': a.curso.nombre_completo if a.curso else None,
            'tanda': a.curso.tanda.nombre if a.curso and a.curso.tanda else None,
            'asignatura': a.asignatura.nombre if a.asignatura else None,
            'asignatura_id': a.asignatura_id,
            'estudiantes': estudiantes_count
        })
    
    # Estudiantes pendientes de calificar (período activo)
    ano_activo = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    periodo_activo = ano_activo.periodo_activo if ano_activo else 1
    
    # v2.13.28: optimización N+1. En vez de una query por estudiante,
    # traemos en lote: (1) los estudiantes de todos los cursos del profesor,
    # y (2) todas sus calificaciones. Luego agrupamos en memoria.
    # El resultado es idéntico al cálculo anterior, solo más rápido.
    curso_ids_prof = list({a.curso_id for a in asignaciones})
    asig_ids_prof = list({a.asignatura_id for a in asignaciones})
    estudiantes_por_curso = {}
    califs_por_clave = {}  # (estudiante_id, asignatura_id) -> Calificacion
    if curso_ids_prof:
        ests_all = (tenant_filter(db.query(Estudiante), Estudiante, current_user)
                    .filter(Estudiante.curso_id.in_(curso_ids_prof), Estudiante.activo == True).all())
        for e in ests_all:
            estudiantes_por_curso.setdefault(e.curso_id, []).append(e)
        est_ids_all = [e.id for e in ests_all]
        if est_ids_all and asig_ids_prof:
            califs_all = (tenant_filter(db.query(Calificacion), Calificacion, current_user)
                          .filter(Calificacion.estudiante_id.in_(est_ids_all),
                                  Calificacion.asignatura_id.in_(asig_ids_prof)).all())
            for c in califs_all:
                califs_por_clave[(c.estudiante_id, c.asignatura_id)] = c
    
    pendientes_calificar = []
    for a in asignaciones:
        estudiantes = estudiantes_por_curso.get(a.curso_id, [])
        sin_nota = 0
        for est in estudiantes:
            calif = califs_por_clave.get((est.id, a.asignatura_id))
            if not calif:
                sin_nota += 1
            else:
                # Verificar si tiene los parciales del período activo
                tiene_parciales = all(getattr(calif, f'p{periodo_activo}_p{i}') is not None for i in range(1, 5))
                if not tiene_parciales:
                    sin_nota += 1
        
        if sin_nota > 0:
            pendientes_calificar.append({
                'curso': a.curso.nombre_completo if a.curso else None,
                'asignatura': a.asignatura.nombre if a.asignatura else None,
                'sin_nota': sin_nota,
                'curso_id': a.curso_id,
                'asignatura_id': a.asignatura_id
            })
    
    es_fin_semana = hoy.weekday() >= 5  # Sábado=5, Domingo=6
    
    return {
        'dia': dia_mostrar,
        'dia_hoy': dia_semana,
        'es_proximo_dia': es_proximo_dia,
        'es_fin_semana': es_fin_semana,
        'todas_pasaron': todas_pasaron if not es_proximo_dia else False,
        'fecha': hoy.isoformat(),
        'horario_hoy': horario_dia,
        'cursos_asignados': cursos_asignados,
        'pendientes_calificar': pendientes_calificar,
        'periodo_activo': periodo_activo
    }

@app.get("/api/dashboard/direccion")
async def get_dashboard_direccion(db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion', 'coordinador'))):
    """Dashboard específico para dirección/coordinación"""
    ano_activo = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    periodo_activo = ano_activo.periodo_activo if ano_activo else 1
    
    # Profesores con notas pendientes — SOLO mostrar si faltan ≤14 días para cierre del período
    profesores_sin_completar = []
    mostrar_pendientes = False
    dias_para_cierre = None
    
    if ano_activo and periodo_activo:
        fecha_fin_periodo = getattr(ano_activo, f'p{periodo_activo}_fin', None)
        if fecha_fin_periodo:
            hoy = today_rd()
            dias_para_cierre = (fecha_fin_periodo - hoy).days
            mostrar_pendientes = dias_para_cierre <= 14
    
    if mostrar_pendientes:
        asignaciones = tenant_filter(db.query(AsignacionProfesor), AsignacionProfesor, current_user).filter_by(activo=True).all()
    
        # v2.13.29: optimización N+1. Traemos en lote estudiantes y notas
        # de todos los cursos/asignaturas involucrados, y agrupamos en memoria.
        # La lógica de "sin_nota" queda idéntica.
        _curso_ids = list({a.curso_id for a in asignaciones})
        _asig_ids = list({a.asignatura_id for a in asignaciones})
        _ests_por_curso = {}
        if _curso_ids:
            _ests_all = (tenant_filter(db.query(Estudiante), Estudiante, current_user)
                         .filter(Estudiante.curso_id.in_(_curso_ids), Estudiante.activo == True).all())
            for _e in _ests_all:
                _ests_por_curso.setdefault(_e.curso_id, []).append(_e)
            _est_ids = [_e.id for _e in _ests_all]
            # Calificaciones secundaria: clave (estudiante_id, asignatura_id) -> {comp_num: obj}
            _sec_por_clave = {}
            if _est_ids and _asig_ids:
                _sec_all = (tenant_filter(db.query(CalificacionSecundaria), CalificacionSecundaria, current_user)
                            .filter(CalificacionSecundaria.estudiante_id.in_(_est_ids),
                                    CalificacionSecundaria.asignatura_id.in_(_asig_ids),
                                    CalificacionSecundaria.ano_escolar_id == ano_activo.id).all())
                for _c in _sec_all:
                    _sec_por_clave.setdefault((_c.estudiante_id, _c.asignatura_id), {})[_c.competencia_numero] = _c
            # Calificaciones primaria/legacy: clave (estudiante_id, asignatura_id) -> obj
            _cal_por_clave = {}
            if _est_ids and _asig_ids:
                _cal_all = (tenant_filter(db.query(Calificacion), Calificacion, current_user)
                            .filter(Calificacion.estudiante_id.in_(_est_ids),
                                    Calificacion.asignatura_id.in_(_asig_ids)).all())
                for _c in _cal_all:
                    _cal_por_clave[(_c.estudiante_id, _c.asignatura_id)] = _c
        else:
            _sec_por_clave = {}
            _cal_por_clave = {}

        for a in asignaciones:
            estudiantes = _ests_por_curso.get(a.curso_id, [])
            if not estudiantes:
                continue
            sin_nota = 0
            es_secundaria = _es_curso_secundaria(db, a.curso_id)
            
            for est in estudiantes:
                if es_secundaria:
                    por_comp = _sec_por_clave.get((est.id, a.asignatura_id), {})
                    campo_p = f'p{periodo_activo}'
                    completo = (len(por_comp) >= 4 and 
                                all(getattr(por_comp.get(n), campo_p, None) is not None for n in range(1, 5)))
                    if not completo:
                        sin_nota += 1
                else:
                    calif = _cal_por_clave.get((est.id, a.asignatura_id))
                    if not calif:
                        sin_nota += 1
                    else:
                        tiene_parciales = all(getattr(calif, f'p{periodo_activo}_p{i}') is not None for i in range(1, 5))
                        if not tiene_parciales:
                            sin_nota += 1
            
            if sin_nota > 0 and a.profesor:
                profesores_sin_completar.append({
                    'profesor': a.profesor.nombre_completo,
                    'curso': a.curso.nombre_completo if a.curso else '',
                    'asignatura': a.asignatura.nombre if a.asignatura else '',
                    'sin_nota': sin_nota
                })
    
    # Ordenar por cantidad de pendientes
    profesores_sin_completar.sort(key=lambda x: x['sin_nota'], reverse=True)
    
    # Solicitudes de edición pendientes
    solicitudes_pendientes = tenant_filter(db.query(SolicitudEdicionNota), SolicitudEdicionNota, current_user).filter_by(estado='pendiente').count()
    
    # Resumen de cursos — v2.13.1: incluir CalificacionSecundaria + asistencia real
    resumen_cursos = []
    cursos = tenant_filter(db.query(Curso), Curso, current_user).filter_by(activo=True).join(Grado).outerjoin(Tanda).order_by(Grado.orden, Tanda.nombre, Curso.nombre).all()
    
    # Pre-calcular fecha del MES actual para asistencia (mensual, no anual — petición usuario)
    from datetime import date as _date
    hoy_mes = today_rd()
    
    # v2.13.29: traer estudiantes de TODOS los cursos en una query (en vez
    # de una por curso) y agrupar. El cálculo de promedio queda igual.
    _curso_ids_resumen = [c.id for c in cursos]
    _ests_por_curso_r = {}
    if _curso_ids_resumen:
        _ests_r = (tenant_filter(db.query(Estudiante), Estudiante, current_user)
                   .filter(Estudiante.curso_id.in_(_curso_ids_resumen), Estudiante.activo == True).all())
        for _e in _ests_r:
            _ests_por_curso_r.setdefault(_e.curso_id, []).append(_e)
    
    for curso in cursos:
        estudiantes = _ests_por_curso_r.get(curso.id, [])
        if not estudiantes:
            continue
        
        es_secundaria = _es_curso_secundaria(db, curso.id)
        califs = []  # lista de CFs para promedio
        
        for est in estudiantes:
            if es_secundaria:
                # Usar el helper que ya tenemos (devuelve CF entero)
                if ano_activo:
                    # Recolectar CFs de TODAS las asignaturas que el estudiante cursa
                    asigs_est = tenant_filter(db.query(CalificacionSecundaria), CalificacionSecundaria, current_user).filter_by(
                        estudiante_id=est.id, ano_escolar_id=ano_activo.id
                    ).all()
                    asigs_ids = {c.asignatura_id for c in asigs_est}
                    for asig_id in asigs_ids:
                        try:
                            cf, _ = _calcular_cf_secundaria(db, est.id, asig_id, ano_activo.id)
                            if cf is not None:
                                califs.append(cf)
                        except Exception:
                            pass
            else:
                cals = tenant_filter(db.query(Calificacion), Calificacion, current_user).filter_by(estudiante_id=est.id).all()
                for c in cals:
                    if c.cf is not None:
                        califs.append(c.cf)
        
        promedio = sum(califs) / len(califs) if califs else 0
        
        # Asistencia MENSUAL del curso (v2.13.1: era anual hardcoded a 0)
        # % asistencia = presentes / (presentes + ausentes) en el mes actual
        est_ids = [e.id for e in estudiantes]
        from sqlalchemy import extract as _extract
        asists_mes = tenant_filter(db.query(Asistencia), Asistencia, current_user).filter(
            Asistencia.estudiante_id.in_(est_ids),
            _extract('month', Asistencia.fecha) == hoy_mes.month,
            _extract('year', Asistencia.fecha) == hoy_mes.year
        ).all()
        n_pres = sum(1 for a in asists_mes if a.estado == 'presente')
        n_aus = sum(1 for a in asists_mes if a.estado == 'ausente')
        pct_asis = round(n_pres / (n_pres + n_aus) * 100, 1) if (n_pres + n_aus) > 0 else 0
        
        resumen_cursos.append({
            'curso': curso.nombre_completo,
            'estudiantes': len(estudiantes),
            'promedio': round(promedio, 1),
            'asistencia': pct_asis  # ahora real, calculado del mes actual
        })
    
    return {
        'ano_escolar': ano_activo.nombre if ano_activo else 'Sin año escolar',
        'periodo_activo': periodo_activo,
        'periodos_cerrados': {
            'p1': ano_activo.p1_cerrado if ano_activo else True,
            'p2': ano_activo.p2_cerrado if ano_activo else True,
            'p3': ano_activo.p3_cerrado if ano_activo else True,
            'p4': ano_activo.p4_cerrado if ano_activo else True
        },
        'profesores_sin_completar': profesores_sin_completar[:10],
        'resumen_cursos': resumen_cursos,
        'solicitudes_edicion_pendientes': solicitudes_pendientes,
        'reportes_pendientes': tenant_filter(db.query(ReporteConducta), ReporteConducta, current_user).filter_by(estado='pendiente').count(),
        'casos_psicologia_pendientes': tenant_filter(db.query(CasoPsicologia), CasoPsicologia, current_user).filter_by(estado='pendiente').count()
    }

@app.get("/api/dashboard/all")
async def get_dashboard_all(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Endpoint unificado — 1 request en vez de 4. Cache 15s."""
    ck = f'dash_all:{current_user.id}'
    cached = cache_get(ck)
    if cached: return cached
    
    config = tenant_filter(db.query(ConfiguracionColegio), ConfiguracionColegio, current_user).first()
    
    # Stats (siempre)
    stats = {
        'estudiantes': tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(activo=True).count(),
        'profesores': tenant_filter(db.query(Usuario), Usuario, current_user).filter_by(role='profesor', activo=True).count(),
        'cursos': tenant_filter(db.query(Curso), Curso, current_user).filter_by(activo=True).count(),
        'reportes_pendientes': tenant_filter(db.query(ReporteConducta), ReporteConducta, current_user).filter_by(estado='pendiente').count(),
        'colegio': {'nombre': config.nombre if config else 'Educa One', 'logo': config.logo if config else None}
    }
    
    # Notificaciones count
    notif_count = tenant_filter(db.query(Notificacion), Notificacion, current_user).filter_by(
        usuario_id=current_user.id, leida=False
    ).count()
    
    result = {'stats': stats, 'notificaciones_no_leidas': notif_count}
    cache_set(ck, result, 15)
    return result

# ============== AUDITORÍA ==============

@app.get("/api/auditoria")
async def get_auditoria(request: Request, current_user: Usuario = Depends(RolesRequired('direccion')), db: Session = Depends(get_db)):
    query = tenant_filter(db.query(LogAuditoria), LogAuditoria, current_user)
    
    if request.query_params.get('accion'):
        query = query.filter_by(accion=request.query_params.get('accion'))
    if request.query_params.get('tabla'):
        query = query.filter_by(tabla=request.query_params.get('tabla'))
    
    logs = query.order_by(LogAuditoria.fecha.desc()).limit(100).all()
    
    return [{
        'id': l.id,
        'usuario': l.usuario.nombre_completo if l.usuario else None,
        'accion': l.accion,
        'tabla': l.tabla,
        'registro_id': l.registro_id,
        'fecha': l.fecha.isoformat() if l.fecha else None,
        'ip': l.ip
    } for l in logs]

@app.get("/api/auditoria/accesos")
async def get_accesos(db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    accesos = tenant_filter(db.query(LogAcceso), LogAcceso, current_user).order_by(LogAcceso.fecha.desc()).limit(100).all()
    
    return [{
        'id': a.id,
        'usuario': a.usuario.nombre_completo if a.usuario else 'Desconocido',
        'usuario_role': a.usuario.role if a.usuario else '',
        'accion': a.tipo,
        'detalle': a.user_agent[:100] if a.user_agent else '',
        'ip': a.ip,
        'fecha': a.fecha.isoformat() if a.fecha else None
    } for a in accesos]

# ============== ENDPOINTS ADICIONALES ==============

@app.get("/api/alertas")
async def get_alertas(db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Endpoint de alertas dinámicas basadas en datos reales"""
    alertas = []
    hoy = today_rd()
    ano_activo = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    
    # 1. Alerta de período próximo a cerrar (solo dirección/coordinador)
    # Solo aparece si estamos a 14 días o menos del cierre del período
    if current_user.role in ['direccion', 'coordinador'] and ano_activo:
        periodo_activo = ano_activo.periodo_activo
        if periodo_activo:
            fecha_fin_periodo = getattr(ano_activo, f'p{periodo_activo}_fin', None)
            dias_restantes = None
            if fecha_fin_periodo:
                dias_restantes = (fecha_fin_periodo - hoy).days
            
            # Solo alertar si estamos a 14 días o menos del cierre, o si ya pasó
            mostrar_alerta_periodo = (dias_restantes is not None and dias_restantes <= 14) or fecha_fin_periodo is None
            
            if mostrar_alerta_periodo:
                asignaciones = tenant_filter(db.query(AsignacionProfesor), AsignacionProfesor, current_user).filter_by(activo=True).all()
                profesores_sin_completar = set()
                # v2.13.7: detectar si el curso es secundaria nueva (CalificacionSecundaria)
                # o legacy (Calificacion). En cada caso, validar completitud según el modelo.
                ano_activo_obj = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
                
                # v2.13.29: traer estudiantes y notas en lote (en vez de una
                # query por estudiante). La lógica de completitud queda igual.
                _cids = list({a.curso_id for a in asignaciones})
                _aids = list({a.asignatura_id for a in asignaciones})
                _ests_pc = {}
                _sec_clave = {}
                _cal_clave = {}
                if _cids:
                    _ea = (tenant_filter(db.query(Estudiante), Estudiante, current_user)
                           .filter(Estudiante.curso_id.in_(_cids), Estudiante.activo == True).all())
                    for _e in _ea:
                        _ests_pc.setdefault(_e.curso_id, []).append(_e)
                    _eids = [_e.id for _e in _ea]
                    if _eids and _aids and ano_activo_obj:
                        for _c in (tenant_filter(db.query(CalificacionSecundaria), CalificacionSecundaria, current_user)
                                   .filter(CalificacionSecundaria.estudiante_id.in_(_eids),
                                           CalificacionSecundaria.asignatura_id.in_(_aids),
                                           CalificacionSecundaria.ano_escolar_id == ano_activo_obj.id).all()):
                            _sec_clave.setdefault((_c.estudiante_id, _c.asignatura_id), {})[_c.competencia_numero] = _c
                    if _eids and _aids:
                        for _c in (tenant_filter(db.query(Calificacion), Calificacion, current_user)
                                   .filter(Calificacion.estudiante_id.in_(_eids),
                                           Calificacion.asignatura_id.in_(_aids)).all()):
                            _cal_clave[(_c.estudiante_id, _c.asignatura_id)] = _c
                
                for a in asignaciones:
                    es_secundaria_nueva = _es_curso_secundaria(db, a.curso_id) if ano_activo_obj else False
                    estudiantes = _ests_pc.get(a.curso_id, [])
                    
                    for est in estudiantes:
                        falta_completar = False
                        if es_secundaria_nueva and ano_activo_obj:
                            por_comp = _sec_clave.get((est.id, a.asignatura_id), {})
                            campo_p = f'p{periodo_activo}'
                            if len(por_comp) < 4 or not all(
                                getattr(por_comp.get(n), campo_p, None) is not None for n in range(1, 5)
                            ):
                                falta_completar = True
                        else:
                            calif = _cal_clave.get((est.id, a.asignatura_id))
                            if not calif or not all(getattr(calif, f'p{periodo_activo}_p{i}') is not None for i in range(1, 5)):
                                falta_completar = True
                        
                        if falta_completar:
                            profesores_sin_completar.add(a.profesor_id)
                            break
                
                if profesores_sin_completar:
                    tiempo_msg = f'{dias_restantes} días restantes' if dias_restantes and dias_restantes > 0 else 'Fecha límite alcanzada'
                    alertas.append({
                        'id': 1,
                        'tipo': 'periodo',
                        'titulo': f'Período {periodo_activo} - Notas Pendientes',
                        'descripcion': f'{len(profesores_sin_completar)} profesores sin completar P{periodo_activo}. {tiempo_msg}.',
                        'fecha': tiempo_msg,
                        'prioridad': 'urgent' if (dias_restantes and dias_restantes <= 3) else 'warning'
                    })
    
    # 2. Reportes pendientes
    reportes_pendientes = tenant_filter(db.query(ReporteConducta), ReporteConducta, current_user).filter_by(estado='pendiente').count()
    if reportes_pendientes > 0:
        alertas.append({
            'id': 2,
            'tipo': 'reporte',
            'titulo': f'{reportes_pendientes} Reportes Pendientes',
            'descripcion': 'Hay reportes de conducta sin responder.',
            'fecha': 'Hoy',
            'prioridad': 'warning'
        })
    
    # 3. Casos psicología pendientes
    casos_pendientes = tenant_filter(db.query(CasoPsicologia), CasoPsicologia, current_user).filter_by(estado='pendiente').count()
    if casos_pendientes > 0:
        alertas.append({
            'id': 3,
            'tipo': 'psicologia',
            'titulo': f'{casos_pendientes} Casos de Psicología',
            'descripcion': 'Casos pendientes de atención psicológica.',
            'fecha': 'Hoy',
            'prioridad': 'info'
        })
    
    # 4. Estudiantes con bajo rendimiento (promedio < 70 en CF)
    # v2.13.7: contar de AMBOS modelos (Calificacion legacy + CalificacionSecundaria nuevo)
    if current_user.role in ['direccion', 'coordinador']:
        estudiantes_bajo_ids = set()
        
        # Modelo legacy
        for calif in tenant_filter(db.query(Calificacion), Calificacion, current_user).filter(Calificacion.cf != None, Calificacion.cf < 70).all():
            if calif.estudiante and calif.estudiante.activo:
                estudiantes_bajo_ids.add(calif.estudiante_id)
        
        # Modelo nuevo: calcular CF y verificar < 70
        if ano_activo:
            comps_sec = tenant_filter(
                db.query(CalificacionSecundaria), CalificacionSecundaria, current_user
            ).filter(CalificacionSecundaria.ano_escolar_id == ano_activo.id).all()
            
            # Agrupar por (estudiante, asignatura)
            from collections import defaultdict as _dd
            por_est_asig = _dd(list)
            for c in comps_sec:
                por_est_asig[(c.estudiante_id, c.asignatura_id)].append(c)
            
            # Para cada (estudiante, asignatura): calcular CF y si <70, agregar al set
            for (eid, aid), comps in por_est_asig.items():
                if len(comps) < 4:
                    continue  # CF necesita 4 competencias completas
                pcs = []
                for p in range(1, 5):
                    vals = []
                    for c in comps:
                        v = c.valor_periodo(p) if hasattr(c, 'valor_periodo') else None
                        if v is not None:
                            vals.append(v)
                    if vals:
                        pcs.append(sum(vals) / len(vals))
                if len(pcs) == 4:
                    cf = sum(pcs) / 4
                    if cf < 70:
                        estudiantes_bajo_ids.add(eid)
        
        estudiantes_bajo = len(estudiantes_bajo_ids)
        if estudiantes_bajo > 0:
            alertas.append({
                'id': 4,
                'tipo': 'rendimiento',
                'titulo': f'{estudiantes_bajo} Estudiantes en Riesgo',
                'descripcion': 'Estudiantes con calificación final por debajo de 70.',
                'fecha': 'Este período',
                'prioridad': 'warning'
            })
    
    # 5. Alertas para profesor - sus estudiantes pendientes
    if current_user.role == 'profesor' and ano_activo:
        periodo_activo = ano_activo.periodo_activo or 1
        asignaciones = tenant_filter(db.query(AsignacionProfesor), AsignacionProfesor, current_user).filter_by(profesor_id=current_user.id, activo=True).all()
        total_pendientes = 0
        
        for a in asignaciones:
            estudiantes = tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(curso_id=a.curso_id, activo=True).all()
            for est in estudiantes:
                calif = tenant_filter(db.query(Calificacion), Calificacion, current_user).filter_by(estudiante_id=est.id, asignatura_id=a.asignatura_id).first()
                if not calif or not all(getattr(calif, f'p{periodo_activo}_p{i}') is not None for i in range(1, 5)):
                    total_pendientes += 1
        
        if total_pendientes > 0:
            alertas.append({
                'id': 5,
                'tipo': 'calificaciones',
                'titulo': f'{total_pendientes} Notas Pendientes',
                'descripcion': f'Tienes estudiantes sin calificar en el período {periodo_activo}.',
                'fecha': 'Ahora',
                'prioridad': 'urgent'
            })
    
    # 6. Asistencia - estudiantes con muchas ausencias (más de 5 este mes)
    if current_user.role in ['direccion', 'coordinador']:
        primer_dia_mes = date(hoy.year, hoy.month, 1)
        ausencias_q = db.query(
            Asistencia.estudiante_id, 
            func.count(Asistencia.id).label('total')
        ).filter(
            Asistencia.fecha >= primer_dia_mes,
            Asistencia.estado == 'ausente'
        )
        if current_user.colegio_id:
            ausencias_q = ausencias_q.filter(Asistencia.colegio_id == current_user.colegio_id)
        ausencias = ausencias_q.group_by(Asistencia.estudiante_id).having(func.count(Asistencia.id) >= 5).all()
        
        if ausencias:
            alertas.append({
                'id': 6,
                'tipo': 'asistencia',
                'titulo': f'{len(ausencias)} Estudiantes con Ausencias',
                'descripcion': 'Estudiantes con 5 o más ausencias este mes.',
                'fecha': 'Este mes',
                'prioridad': 'warning'
            })
    
    # 7. Día no laborable próximo (mañana o pasado mañana)
    manana = hoy + timedelta(days=1)
    pasado = hoy + timedelta(days=2)
    
    dia_proximo = tenant_filter(db.query(DiaNoLaborable), DiaNoLaborable, current_user).filter(
        DiaNoLaborable.fecha.in_([manana, pasado]),
        DiaNoLaborable.activo == True
    ).first()
    
    if dia_proximo:
        dias_falta = (dia_proximo.fecha - hoy).days
        alertas.append({
            'id': 7,
            'tipo': 'feriado',
            'titulo': f'📅 {dia_proximo.nombre}',
            'descripcion': f'{"Mañana" if dias_falta == 1 else "Pasado mañana"} es {dia_proximo.tipo}.',
            'fecha': dia_proximo.fecha.strftime('%d/%m'),
            'prioridad': 'info'
        })
    
    return alertas

@app.get("/api/mensajes/no-leidos")
async def get_mensajes_no_leidos(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Contar mensajes no leídos del usuario actual"""
    count = tenant_filter(db.query(Mensaje), Mensaje, current_user).filter_by(
        destinatario_id=current_user.id,
        leido=False
    ).count()
    return {'count': count}

# ============== REPORTES DE CONDUCTA ==============

@app.get("/api/reportes")
async def get_reportes(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Obtener reportes de conducta con todos los campos v2.11"""
    q = tenant_filter(db.query(ReporteConducta), ReporteConducta, current_user)
    
    # Profesor: solo sus propios reportes (los que él creó)
    # + reportes de estudiantes de sus cursos asignados (puede ver para contexto)
    if current_user.role == 'profesor':
        # IDs de cursos donde está asignado
        cursos_asignados = db.query(AsignacionProfesor.curso_id).filter_by(
            profesor_id=current_user.id
        ).distinct().all()
        cursos_ids = [c[0] for c in cursos_asignados]
        if cursos_ids:
            # Estudiantes de esos cursos (usando select() en lugar de subquery()
            # para evitar warning de SQLAlchemy con .in_() y reflejar el patrón
            # moderno).
            from sqlalchemy import select, or_
            estudiantes_ids_select = select(Estudiante.id).where(
                Estudiante.curso_id.in_(cursos_ids),
                Estudiante.colegio_id == current_user.colegio_id,
            )
            q = q.filter(or_(
                ReporteConducta.reportado_por == current_user.id,
                ReporteConducta.estudiante_id.in_(estudiantes_ids_select),
            ))
        else:
            # Sin asignaciones: solo los reportes que él creó
            q = q.filter(ReporteConducta.reportado_por == current_user.id)
    
    q = q.order_by(ReporteConducta.fecha.desc())
    # v2.13.30: paginación opcional (sin ?page devuelve todo, retrocompatible)
    _pag = paginar_query(q, request)
    reportes = _pag['items'] if _pag else q.all()
    # Helper local para Opción 1 (fallback tutor → padre → madre)
    def _contacto_principal(est):
        """Devuelve (nombre, telefono) del contacto principal del estudiante."""
        if not est:
            return (None, None)
        # NOTA: el campo del modelo se llama 'tutor' (no 'nombre_tutor')
        if getattr(est, 'tutor', None):
            return (est.tutor, getattr(est, 'telefono_tutor', None))
        if getattr(est, 'nombre_padre', None):
            return (est.nombre_padre, getattr(est, 'telefono_padre', None))
        if getattr(est, 'nombre_madre', None):
            return (est.nombre_madre, getattr(est, 'telefono_madre', None))
        return (None, None)
    
    resultado = []
    for r in reportes:
        nombre_contacto, tel_contacto = _contacto_principal(r.estudiante)
        resultado.append({
            'id': r.id,
            'numero_reporte': r.numero_reporte,
            'titulo': r.titulo,
            'descripcion': r.descripcion,
            'tipo': r.tipo,
            'gravedad': r.gravedad,
            'estado': r.estado,
            'estudiante': r.estudiante.nombre_completo if r.estudiante else None,
            'estudiante_id': r.estudiante_id,
            'estudiante_curso': r.estudiante.curso.nombre_completo if r.estudiante and r.estudiante.curso else None,
            'reportado_por': r.reportador.nombre_completo if r.reportador else None,
            'reportado_por_id': r.reportado_por,
            'fecha': r.fecha.isoformat() if r.fecha else None,
            # Respuesta v2.11: 3 campos guiados
            'acciones_centro': r.acciones_centro,
            'acciones_hogar': r.acciones_hogar,
            'respuesta': r.respuesta,
            'respondido_por': r.respondedor.nombre_completo if r.respondedor else None,
            'fecha_respuesta': r.fecha_respuesta.isoformat() if r.fecha_respuesta else None,
            # Envío y confirmación
            'enviado_padres': bool(r.enviado_padres),
            'confirmado_padre': bool(r.confirmado_padre),
            'fecha_confirmacion_padre': r.fecha_confirmacion_padre.isoformat() if r.fecha_confirmacion_padre else None,
            # Contacto principal para WhatsApp (Opción 1: tutor → padre → madre)
            'contacto_principal_nombre': nombre_contacto,
            'contacto_principal_telefono': tel_contacto,
        })
    # v2.13.30: si se pidió paginación, envolver con metadata
    if _pag is not None:
        return {**_pag, 'items': resultado}
    return resultado

def _generar_numero_reporte(db: Session, colegio_id: int) -> str:
    """
    Genera un número de reporte único por colegio en formato "YYYY-NNNN".
    El contador se reinicia cada año escolar.
    
    Ejemplo: "2026-0023" = el reporte número 23 del año 2026.
    
    Nota: si dos requests concurrentes generan números al mismo tiempo,
    el COUNT puede dar el mismo valor. Es un riesgo aceptable porque
    numero_reporte no es PRIMARY KEY (el id auto-incremental sí lo es).
    Para producción muy concurrente, conviene un sequence dedicado, pero
    para el volumen de un colegio (decenas de reportes/mes) está bien.
    """
    from datetime import datetime as _dt
    año_actual = _dt.now().year
    prefijo = f"{año_actual}-"
    # Contar reportes existentes con ese prefijo en el colegio
    count = db.query(ReporteConducta).filter(
        ReporteConducta.colegio_id == colegio_id,
        ReporteConducta.numero_reporte.like(f'{prefijo}%')
    ).count()
    return f"{prefijo}{count + 1:04d}"


@app.post("/api/reportes")
async def crear_reporte(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """
    Crear nuevo reporte de conducta.
    
    v2.11 (Interpretación A):
    - Cualquier usuario autenticado puede crear reporte (profesor, dirección,
      coordinador, psicología, secretaría). El toggle "permitir_profesor_reportes"
      fue eliminado en el refactor.
    - Se autogenera numero_reporte (formato "YYYY-NNNN").
    """
    # Validar que el módulo esté en el plan del colegio
    assert_modulo_activo(db, current_user, 'reportes_conducta')
    
    data = await request.json()
    
    if not data.get('estudiante_id') or not data.get('titulo'):
        return JSONResponse(
            {'error': 'estudiante_id y titulo son requeridos'},
            status_code=400
        )
    
    # Validar tenant del estudiante (no se puede reportar a un estudiante de otro colegio)
    estudiante = get_tenant_or_404(db, Estudiante, data['estudiante_id'], current_user, name='estudiante')
    
    # Profesor: solo puede reportar a estudiantes de cursos donde tiene asignación
    if current_user.role == 'profesor':
        tiene_asig = db.query(AsignacionProfesor).filter_by(
            profesor_id=current_user.id, curso_id=estudiante.curso_id
        ).first()
        if not tiene_asig:
            return JSONResponse(
                {'error': 'Solo podés reportar estudiantes de tus cursos asignados'},
                status_code=403
            )
    
    # Sanitizar inputs textuales
    import bleach
    titulo = bleach.clean(data['titulo'], tags=[], strip=True)[:200]
    descripcion = bleach.clean(data.get('descripcion', ''), tags=[], strip=True)[:5000]
    
    reporte = ReporteConducta(
        estudiante_id=data['estudiante_id'],
        colegio_id=current_user.colegio_id,
        reportado_por=current_user.id,
        titulo=titulo,
        descripcion=descripcion,
        tipo=data.get('tipo', 'conducta'),
        gravedad=data.get('gravedad', 'leve'),
        estado='pendiente',
        numero_reporte=_generar_numero_reporte(db, current_user.colegio_id),
    )
    db.add(reporte)
    db.commit()
    
    cache_clear(f'stats:{current_user.colegio_id}')
    cache_clear(f'dash_all:{current_user.id}')
    return JSONResponse({
        'message': 'Reporte creado',
        'id': reporte.id,
        'numero_reporte': reporte.numero_reporte,
    }, status_code=201)


@app.post("/api/reportes/{id}/responder")
async def responder_reporte(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion', 'coordinador', 'psicologia'))):
    """
    Responder/completar un reporte de conducta con los 3 campos guiados v2.11:
    - acciones_centro: qué hizo el centro educativo (obligatorio)
    - acciones_hogar: qué se le pide al padre/tutor (opcional)
    - respuesta: comentario adicional libre (opcional, legacy)
    
    Permisos: dirección, coordinación, psicología (los tres roles que firman
    reportes oficiales en colegios DR).
    """
    reporte = get_tenant_or_404(db, ReporteConducta, id, current_user, name='reporte')
    data = await request.json()
    
    import bleach
    acciones_centro = bleach.clean(data.get('acciones_centro', ''), tags=[], strip=True)[:5000]
    acciones_hogar = bleach.clean(data.get('acciones_hogar', ''), tags=[], strip=True)[:5000]
    respuesta = bleach.clean(data.get('respuesta', ''), tags=[], strip=True)[:5000]
    
    if not acciones_centro and not respuesta:
        return JSONResponse(
            {'error': 'Debe completar al menos "Acciones del centro" o "Comentario"'},
            status_code=400
        )
    
    reporte.acciones_centro = acciones_centro
    reporte.acciones_hogar = acciones_hogar
    reporte.respuesta = respuesta  # legacy: comentario adicional
    reporte.estado = data.get('estado', 'resuelto')
    reporte.respondido_por = current_user.id
    reporte.fecha_respuesta = now_rd()
    
    db.commit()
    return {
        'message': 'Reporte respondido',
        'estado': reporte.estado,
    }


@app.post("/api/reportes/{id}/confirmar-padre")
async def confirmar_reporte_padre(id, request: Request, db: Session = Depends(get_db),
                                     current_user: Usuario = Depends(RolesRequired('direccion', 'coordinador', 'psicologia'))):
    """
    Marcar un reporte como firmado/confirmado por el padre/tutor.
    
    v2.11 (Opción B): registro manual sin firma digital. Cuando el padre
    devuelve el reporte físico firmado, dirección entra acá y lo marca
    como confirmado. Queda registro de quién y cuándo lo confirmó.
    
    Idempotente: marcar 2 veces no rompe nada.
    """
    reporte = get_tenant_or_404(db, ReporteConducta, id, current_user, name='reporte')
    
    if reporte.confirmado_padre:
        return {
            'message': 'El reporte ya estaba marcado como confirmado por el padre',
            'fecha_confirmacion': reporte.fecha_confirmacion_padre.isoformat() if reporte.fecha_confirmacion_padre else None,
        }
    
    reporte.confirmado_padre = True
    reporte.fecha_confirmacion_padre = now_rd()
    reporte.confirmado_por_usuario_id = current_user.id
    
    log_auditoria(db, 'CONFIRMAR_REPORTE_PADRE', 'reportes_conducta', id, None, {
        'estudiante_id': reporte.estudiante_id,
        'confirmado_por': current_user.id,
    }, user=current_user, request=request)
    
    db.commit()
    return {
        'message': 'Reporte marcado como firmado por el padre',
        'fecha_confirmacion': reporte.fecha_confirmacion_padre.isoformat(),
    }


@app.get("/api/reportes/{id}/pdf")
async def imprimir_reporte_pdf(id, request: Request, db: Session = Depends(get_db),
                                  current_user: Usuario = Depends(get_current_user)):
    """
    Genera el PDF profesional de un reporte de conducta.

    Permisos (v2.11):
    - Dirección, coordinación, psicología: cualquier reporte del colegio
    - Profesor: solo los reportes que él creó

    v2.13.22: TODO el cuerpo va dentro de try/except para que cualquier
    error devuelva el detalle real en vez de un 500 mudo.
    """
    from reporte_conducta_pdf import generar_reporte_conducta_pdf
    from fastapi.responses import Response
    from pdf_helpers import safe_filename_ascii

    reporte = get_tenant_or_404(db, ReporteConducta, id, current_user, name='reporte')

    # Profesor: solo sus propios reportes
    if current_user.role == 'profesor' and reporte.reportado_por != current_user.id:
        return JSONResponse(
            {'error': 'Solo podés imprimir los reportes que vos creaste'},
            status_code=403
        )

    try:
        estudiante = db.get(Estudiante, reporte.estudiante_id)
        if not estudiante:
            return JSONResponse({'error': 'Estudiante no encontrado'}, status_code=404)

        curso = db.get(Curso, estudiante.curso_id) if estudiante.curso_id else None
        grado = db.get(Grado, curso.grado_id) if curso and curso.grado_id else None
        tanda = db.get(Tanda, curso.tanda_id) if curso and curso.tanda_id else None

        reportador = db.get(Usuario, reporte.reportado_por) if reporte.reportado_por else None
        respondedor = db.get(Usuario, reporte.respondido_por) if reporte.respondido_por else None

        config = db.query(ConfiguracionColegio).filter_by(colegio_id=current_user.colegio_id).first()
        colegio = db.get(Colegio, current_user.colegio_id) if current_user.colegio_id else None

        ano_activo = db.query(AnoEscolar).filter_by(
            colegio_id=current_user.colegio_id, activo=True
        ).first()
        if not ano_activo:
            ano_activo = db.query(AnoEscolar).filter_by(
                colegio_id=current_user.colegio_id
            ).order_by(AnoEscolar.id.desc()).first()
        ano_str = ano_activo.nombre if ano_activo else None

        pdf_bytes = generar_reporte_conducta_pdf(
            reporte=reporte,
            estudiante=estudiante,
            curso=curso, grado=grado, tanda=tanda,
            reportador=reportador, respondedor=respondedor,
            config=config, colegio=colegio,
            ano_escolar=ano_str,
        )

        raw = f"reporte_{reporte.numero_reporte or reporte.id}.pdf"
        nombre = safe_filename_ascii(raw, default="reporte_conducta.pdf")
        return Response(
            content=pdf_bytes,
            media_type='application/pdf',
            headers={'Content-Disposition': f'inline; filename="{nombre}"'}
        )
    except Exception as e:
        logger.error(f"Error generando PDF de conducta para reporte {id}: {e}", exc_info=True)
        return JSONResponse(
            {'error': f'No se pudo generar el PDF del reporte. Detalle técnico: {type(e).__name__}: {str(e)[:250]}'},
            status_code=500
        )


@app.post("/api/reportes/{id}/enviar-padres")
async def enviar_reporte_padres(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion', 'coordinador', 'psicologia'))):
    """Registrar envío de reporte a padres con historial"""
    
    reporte = get_tenant_or_404(db, ReporteConducta, id, current_user, name='reporte')
    data = await request.json() or {}
    
    # Marcar como enviado
    reporte.enviado_padres = True
    
    # Registrar en historial
    historial = HistorialReportePadres(
        reporte_id=reporte.id,
        estudiante_id=reporte.estudiante_id,
        enviado_por=current_user.id,
        telefono_destino=data.get('telefono'),
        mensaje_enviado=data.get('mensaje', 'Mensaje enviado por WhatsApp'),
        metodo=data.get('metodo', 'whatsapp'),
        colegio_id=current_user.colegio_id
    )
    db.add(historial)
    
    log_auditoria(db, 'ENVIAR_REPORTE_PADRES', 'reportes_conducta', id, None, {
        'estudiante_id': reporte.estudiante_id,
        'metodo': data.get('metodo', 'whatsapp')
    }, user=current_user, request=request)
    
    db.commit()
    return {
        'message': 'Reporte registrado como enviado a padres',
        'historial_id': historial.id,
        'fecha': historial.fecha_envio.isoformat()
    }

@app.get("/api/reportes/{id}/historial-envios")
async def get_historial_envios_reporte(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion', 'coordinador'))):
    """Ver historial de envíos de un reporte a padres"""
    
    historial = tenant_filter(db.query(HistorialReportePadres), HistorialReportePadres, current_user).filter_by(reporte_id=id).order_by(HistorialReportePadres.fecha_envio.desc()).all()
    
    return [{
        'id': h.id,
        'fecha': h.fecha_envio.isoformat() if h.fecha_envio else None,
        'enviado_por': h.usuario.nombre_completo if h.usuario else None,
        'metodo': h.metodo,
        'telefono': h.telefono_destino,
        'mensaje': h.mensaje_enviado[:100] + '...' if len(h.mensaje_enviado or '') > 100 else h.mensaje_enviado
    } for h in historial]

# ============== PSICOLOGÍA ==============

@app.get("/api/psicologia/casos")
async def get_casos_psicologia(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Obtener casos de psicología"""
    # Si es profesor, solo ve los casos que él solicitó
    if current_user.role == 'profesor':
        casos = tenant_filter(db.query(CasoPsicologia), CasoPsicologia, current_user).filter_by(solicitado_por=current_user.id).order_by(CasoPsicologia.fecha_solicitud.desc()).all()
    else:
        casos = tenant_filter(db.query(CasoPsicologia), CasoPsicologia, current_user).order_by(CasoPsicologia.fecha_solicitud.desc()).all()
    
    return [{
        'id': c.id,
        'estudiante': c.estudiante.nombre_completo if c.estudiante else None,
        'estudiante_id': c.estudiante_id,
        'tipo': c.tipo,
        'urgencia': c.urgencia,
        'motivo': c.motivo,
        'estado': c.estado,
        'solicitante': c.solicitante.nombre_completo if c.solicitante else None,
        'solicitante_id': c.solicitado_por,
        'psicologo': c.psicologo.nombre_completo if c.psicologo else None,
        'fecha_solicitud': c.fecha_solicitud.isoformat() if c.fecha_solicitud else None,
        'notas_atencion': c.notas_atencion,
        'recomendacion_profesor': c.recomendacion_profesor,
        'diagnostico': c.diagnostico,
        'fecha_actualizacion': c.fecha_actualizacion.isoformat() if c.fecha_actualizacion else None
    } for c in casos]

@app.post("/api/psicologia/solicitar")
async def solicitar_atencion_psicologia(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Solicitar atención psicológica para un estudiante - Profesor, Coordinador pueden solicitar"""
    if current_user.role not in ['profesor', 'coordinador', 'direccion']:
        return JSONResponse({'error': 'No tiene permiso para solicitar atención'}, status_code=403)
    
    data = await request.json()
    
    caso = CasoPsicologia(
        estudiante_id=data['estudiante_id'],
        colegio_id=current_user.colegio_id,
        solicitado_por=current_user.id,
        tipo=data.get('tipo', 'emocional'),
        urgencia=data.get('urgencia', 'normal'),
        motivo=data.get('motivo', ''),
        estado='pendiente'
    )
    db.add(caso)
    db.commit()
    
    return JSONResponse({'message': 'Solicitud creada', 'id': caso.id}, status_code=201)

@app.post("/api/psicologia/casos/{id}/tomar")
async def tomar_caso_psicologia(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('psicologia'))):
    """Psicólogo toma un caso"""
    caso = get_tenant_or_404(db, CasoPsicologia, id, current_user, name='casopsicologia')
    caso.asignado_a = current_user.id
    caso.estado = 'en_proceso'
    caso.fecha_actualizacion = now_rd()
    db.commit()
    return {'message': 'Caso tomado'}

@app.post("/api/psicologia/casos/{id}/actualizar")
async def actualizar_caso_psicologia(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('psicologia'))):
    """Actualizar estado de un caso de psicología con notas y recomendaciones"""
    caso = get_tenant_or_404(db, CasoPsicologia, id, current_user, name='casopsicologia')
    data = await request.json()
    
    if 'estado' in data:
        caso.estado = data['estado']
        if data['estado'] == 'atendido':
            caso.fecha_atencion = now_rd()
    if 'notas_atencion' in data:
        caso.notas_atencion = data['notas_atencion']
    if 'recomendacion_profesor' in data:
        caso.recomendacion_profesor = data['recomendacion_profesor']
    if 'diagnostico' in data:
        caso.diagnostico = data['diagnostico']
    
    caso.fecha_actualizacion = now_rd()
    db.commit()
    return {'message': 'Caso actualizado'}

# ============== MENSAJES Y COMUNICADOS ==============

@app.get("/api/mensajes")
async def get_mensajes(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Obtener mensajes del usuario actual"""
    # Obtener mensajes donde el usuario es destinatario o es para dirección (si es dirección)
    if current_user.role == 'direccion':
        recibidos = tenant_filter(db.query(Mensaje), Mensaje, current_user).filter(
            (Mensaje.destinatario_id == current_user.id) | (Mensaje.para_direccion == True)
        ).order_by(Mensaje.fecha.desc()).all()
    else:
        recibidos = tenant_filter(db.query(Mensaje), Mensaje, current_user).filter_by(destinatario_id=current_user.id).order_by(Mensaje.fecha.desc()).all()
    
    enviados = tenant_filter(db.query(Mensaje), Mensaje, current_user).filter_by(remitente_id=current_user.id).order_by(Mensaje.fecha.desc()).all()
    
    # Combinar y formatear para el frontend
    todos_recibidos = [{
        'id': m.id,
        'remitente': m.remitente.nombre_completo if m.remitente else 'Sistema',
        'remitente_id': m.remitente_id,
        'asunto': m.asunto,
        'contenido': m.contenido,
        'fecha': m.fecha.isoformat() if m.fecha else None,
        'leido': m.leido,
        'tipo': 'recibido'
    } for m in recibidos]
    
    todos_enviados = [{
        'id': m.id,
        'remitente': 'Yo',
        'destinatario': m.destinatario.nombre_completo if m.destinatario else ('Dirección' if m.para_direccion else 'Desconocido'),
        'asunto': m.asunto,
        'contenido': m.contenido,
        'fecha': m.fecha.isoformat() if m.fecha else None,
        'leido': m.leido,
        'tipo': 'enviado'
    } for m in enviados]
    
    # Devolver lista combinada ordenada por fecha
    todos = sorted(todos_recibidos + todos_enviados, key=lambda x: x['fecha'] or '', reverse=True)
    
    return todos

@app.post("/api/mensajes")
async def enviar_mensaje(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Enviar un nuevo mensaje"""
    data = await request.json()
    
    if not data.get('asunto') or not data.get('contenido'):
        return JSONResponse({'error': 'Asunto y contenido son requeridos'}, status_code=400)
    
    if not data.get('destinatario_id'):
        return JSONResponse({'error': 'Destinatario es requerido'}, status_code=400)
    
    # Validar que el destinatario existe y pertenece al mismo colegio.
    # Sin esta validación, mandar mensaje a id=99999 causaba 500 con
    # FOREIGN KEY violation. Ahora devuelve 404 amigable.
    destinatario = get_tenant_or_404(db, Usuario, data['destinatario_id'], current_user, name='destinatario')
    if not destinatario.activo:
        return JSONResponse({'error': 'El destinatario está inactivo'}, status_code=400)
    
    # Sanitizar contenido: bleach previene XSS si el frontend olvida hacerlo
    import bleach
    asunto_limpio = bleach.clean(data['asunto'], tags=[], strip=True)[:200]
    contenido_limpio = bleach.clean(data['contenido'], tags=['b','i','u','br','p'], strip=True)[:5000]
    
    mensaje = Mensaje(
        remitente_id=current_user.id,
        destinatario_id=data.get('destinatario_id'),
        para_direccion=data.get('para_direccion', False),
        asunto=asunto_limpio,
        contenido=contenido_limpio,
        colegio_id=current_user.colegio_id
    )
    db.add(mensaje)
    db.commit()
    
    return JSONResponse({'message': 'Mensaje enviado', 'id': mensaje.id}, status_code=201)

@app.post("/api/mensajes/masivo")
async def enviar_mensaje_masivo(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Enviar mensaje a todos los usuarios de un rol"""
    data = await request.json()
    
    if not data.get('asunto') or not data.get('contenido'):
        return JSONResponse({'error': 'Asunto y contenido son requeridos'}, status_code=400)
    
    if not data.get('rol'):
        return JSONResponse({'error': 'Rol es requerido'}, status_code=400)
    
    rol = data['rol']
    usuarios_destino = tenant_filter(db.query(Usuario), Usuario, current_user).filter_by(role=rol, activo=True).all()
    
    if not usuarios_destino:
        return JSONResponse({'error': f'No hay usuarios con el rol {rol}'}, status_code=404)
    
    mensajes_enviados = 0
    for usuario in usuarios_destino:
        if usuario.id != current_user.id:  # No enviarse a sí mismo
            mensaje = Mensaje(
                remitente_id=current_user.id,
                destinatario_id=usuario.id,
                asunto=data['asunto'],
                contenido=data['contenido'],
                colegio_id=current_user.colegio_id
            )
            db.add(mensaje)
            mensajes_enviados += 1
    
    db.commit()
    
    return JSONResponse({
        'message': f'Mensaje enviado a {mensajes_enviados} usuarios',
        'count': mensajes_enviados
    }, status_code=201)

@app.post("/api/mensajes/{id}/leer")
@app.post("/api/mensajes/{id}/marcar-leido")
async def marcar_mensaje_leido(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Marcar mensaje como leído"""
    mensaje = get_tenant_or_404(db, Mensaje, id, current_user, name='mensaje')
    if mensaje.destinatario_id == current_user.id:
        mensaje.leido = True
        mensaje.fecha_lectura = now_rd()
        db.commit()
    return {'message': 'Mensaje marcado como leído'}

@app.get("/api/comunicados")
async def get_comunicados(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Obtener comunicados visibles para el usuario"""
    query = tenant_filter(db.query(Comunicado), Comunicado, current_user).filter_by(activo=True)
    
    # Filtrar según rol
    if current_user.role == 'profesor':
        query = query.filter_by(para_profesores=True)
    elif current_user.role == 'coordinador':
        query = query.filter_by(para_coordinadores=True)
    elif current_user.role == 'psicologia':
        query = query.filter_by(para_psicologia=True)
    
    # Filtrar comunicados expirados
    query = query.filter(
        (Comunicado.fecha_expiracion.is_(None)) | 
        (Comunicado.fecha_expiracion > now_rd())
    )
    
    comunicados = query.order_by(Comunicado.fecha.desc()).all()
    
    # Verificar cuáles ha leído el usuario
    leidos_ids = set(cl.comunicado_id for cl in tenant_filter(db.query(ComunicadoLeido), ComunicadoLeido, current_user).filter_by(usuario_id=current_user.id).all())
    
    return [{
        'id': c.id,
        'titulo': c.titulo,
        'contenido': c.contenido,
        'imagen': c.imagen,
        'tipo': c.tipo,
        'autor': c.autor.nombre_completo if c.autor else None,
        'autor_id': c.autor_id,
        'fecha': c.fecha.isoformat() if c.fecha else None,
        'leido_por_mi': c.id in leidos_ids
    } for c in comunicados]

@app.post("/api/comunicados")
async def crear_comunicado(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion', 'coordinador'))):
    """Crear un nuevo comunicado"""
    data = await request.json()
    
    comunicado = Comunicado(
        autor_id=current_user.id,
        colegio_id=current_user.colegio_id,
        titulo=data['titulo'],
        contenido=data['contenido'],
        imagen=data.get('imagen'),
        tipo=data.get('tipo', 'general'),
        para_profesores=data.get('para_profesores', True),
        para_coordinadores=data.get('para_coordinadores', True),
        para_psicologia=data.get('para_psicologia', True)
    )
    db.add(comunicado)
    db.commit()
    
    # Notificar a todos los destinatarios
    roles_dest = []
    if comunicado.para_profesores: roles_dest.append('profesor')
    if comunicado.para_coordinadores: roles_dest.append('coordinador')
    if comunicado.para_psicologia: roles_dest.append('psicologia')
    for role in roles_dest:
        notificar_rol(db, current_user.colegio_id, role, f'📢 {comunicado.titulo}', comunicado.contenido[:100], 'comunicado', '/comunicacion')
    db.commit()
    
    log_auditoria(db, 'CREAR_COMUNICADO', 'comunicados', comunicado.id, user=current_user, request=request)
    
    return JSONResponse({'message': 'Comunicado creado', 'id': comunicado.id}, status_code=201)

@app.delete("/api/comunicados/{id}")
async def eliminar_comunicado(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion', 'coordinador'))):
    """Eliminar comunicado"""
    comunicado = get_tenant_or_404(db, Comunicado, id, current_user, name='comunicado')
    comunicado.activo = False
    db.commit()
    log_auditoria(db, 'ELIMINAR_COMUNICADO', 'comunicados', id, user=current_user, request=request)
    return {'message': 'Comunicado eliminado'}

@app.put("/api/comunicados/{id}")
async def actualizar_comunicado(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion', 'coordinador'))):
    """Actualizar comunicado"""
    comunicado = get_tenant_or_404(db, Comunicado, id, current_user, name='comunicado')
    data = await request.json()
    
    if 'titulo' in data:
        comunicado.titulo = data['titulo']
    if 'contenido' in data:
        comunicado.contenido = data['contenido']
    if 'imagen' in data:
        comunicado.imagen = data['imagen']
    
    db.commit()
    log_auditoria(db, 'ACTUALIZAR_COMUNICADO', 'comunicados', id, user=current_user, request=request)
    return {'message': 'Comunicado actualizado'}

@app.post("/api/comunicados/{id}/marcar-leido")
async def marcar_comunicado_leido(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Marcar comunicado como leído"""
    
    existing = tenant_filter(db.query(ComunicadoLeido), ComunicadoLeido, current_user).filter_by(
        comunicado_id=id, 
        usuario_id=current_user.id
    ).first()
    
    if not existing:
        leido = ComunicadoLeido(
            comunicado_id=id,
            usuario_id=current_user.id,
            colegio_id=current_user.colegio_id
        )
        db.add(leido)
        db.commit()
    
    return {'message': 'Comunicado marcado como leído'}

# ============== ASISTENCIA ==============

@app.get("/api/asistencia")
async def get_asistencia(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Obtener registro de asistencia. Valida tenant del curso y de la asignatura."""
    try:
        curso_id = int(request.query_params.get('curso_id', 0) or 0)
        asignatura_id = int(request.query_params.get('asignatura_id', 0) or 0)
    except (ValueError, TypeError):
        return JSONResponse({'error': 'curso_id y asignatura_id deben ser enteros'}, status_code=400)
    
    fecha_str = request.query_params.get('fecha', today_rd().isoformat())
    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return JSONResponse({'error': f'fecha inválida: {fecha_str!r}. Formato esperado YYYY-MM-DD'}, status_code=400)
    
    if not curso_id:
        return JSONResponse({'error': 'curso_id requerido'}, status_code=400)
    
    # Validar tenant del curso (404 si no existe o es de otro colegio)
    curso = get_tenant_or_404(db, Curso, curso_id, current_user, name='curso')
    if asignatura_id:
        asignatura = get_tenant_or_404(db, Asignatura, asignatura_id, current_user, name='asignatura')
    
    # Si es profesor, verificar que tiene asignación al curso/asignatura
    if current_user.role == 'profesor' and asignatura_id:
        asignacion = tenant_filter(db.query(AsignacionProfesor), AsignacionProfesor, current_user).filter_by(
            profesor_id=current_user.id, curso_id=curso.id, asignatura_id=asignatura_id, activo=True
        ).first()
        if not asignacion:
            return JSONResponse({'error': 'No tiene asignación para este curso/asignatura'}, status_code=403)
    
    estudiantes = tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(
        curso_id=curso.id, activo=True
    ).order_by(Estudiante.no_lista).all()
    est_ids = [e.id for e in estudiantes]
    
    if not est_ids:
        return []
    
    # Bulk load asistencias en UNA query (sin N+1)
    asist_query = tenant_filter(db.query(Asistencia), Asistencia, current_user).filter(
        Asistencia.estudiante_id.in_(est_ids), Asistencia.fecha == fecha
    )
    if asignatura_id:
        asist_query = asist_query.filter_by(asignatura_id=asignatura_id)
    asistencias_map = {a.estudiante_id: a for a in asist_query.all()}
    
    resultado = []
    for est in estudiantes:
        asistencia = asistencias_map.get(est.id)
        resultado.append({
            'estudiante_id': est.id,
            'estudiante': est.nombre_completo,
            'no_lista': est.no_lista,
            'estado': asistencia.estado if asistencia else None,
            'asistencia_id': asistencia.id if asistencia else None
        })
    
    return resultado

@app.post("/api/asistencia")
async def registrar_asistencia(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Registrar o actualizar asistencia por materia."""
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({'error': 'Body inválido (se espera JSON)'}, status_code=400)
    
    if not isinstance(data, dict):
        return JSONResponse({'error': 'Body debe ser un objeto JSON'}, status_code=400)
    
    if 'estudiante_id' not in data or 'estado' not in data:
        return JSONResponse({'error': 'estudiante_id y estado son requeridos'}, status_code=400)
    
    # Validar estado contra valores permitidos (anteriormente: cualquier string entraba)
    ESTADOS_VALIDOS = {'presente', 'ausente', 'tardanza', 'excusa'}
    estado = (data.get('estado') or '').strip().lower()
    if estado not in ESTADOS_VALIDOS:
        return JSONResponse({
            'error': f'estado inválido (recibido: {data.get("estado")!r}). '
                     f'Valores permitidos: {sorted(ESTADOS_VALIDOS)}'
        }, status_code=400)
    
    estudiante = db.get(Estudiante, data['estudiante_id'])
    if not estudiante:
        return JSONResponse({'error': 'Estudiante no encontrado'}, status_code=404)
    
    # Verificar tenant: el estudiante debe ser del mismo colegio que el caller
    if current_user.role != 'superadmin' and estudiante.colegio_id != current_user.colegio_id:
        return JSONResponse({'error': 'Estudiante no pertenece a su colegio'}, status_code=403)
    
    # Bloquear escritura sobre estudiante retirado. Sus marcas previas se conservan,
    # pero ningún rol puede agregar nuevas marcas. Si el director quiere modificar,
    # primero debe reactivar al estudiante.
    if not estudiante.activo:
        return JSONResponse({
            'error': 'Estudiante retirado: no se puede registrar asistencia',
            'fecha_retiro': estudiante.fecha_retiro.isoformat() if estudiante.fecha_retiro else None,
        }, status_code=403)
    
    # Validar que el nivel del curso del estudiante esté activo
    if estudiante.curso_id:
        assert_nivel_curso_activo(db, current_user, estudiante.curso_id)
    
    # Parsear fecha (fallar en lugar de usar hoy silenciosamente)
    fecha_str = data.get('fecha') or today_rd().isoformat()
    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return JSONResponse(
            {'error': f"fecha inválida: {fecha_str!r}. Formato esperado: YYYY-MM-DD"},
            status_code=400
        )
    # Validar rango razonable: no se marca asistencia en el futuro,
    # ni 5+ años atrás. Esto previene errores de captura de los profesores
    # que pueden escribir mal una fecha al apurarse.
    # 
    # BUG HISTÓRICO: usábamos today_rd() (timezone DR) pero el frontend
    # manda date.today() del CLIENTE que puede estar en otra timezone.
    # Cuando Render (UTC) decía 12 de mayo pero el navegador del profesor
    # (DR, UTC-4) decía 11 de mayo, había confusión. Damos 1 día de tolerancia
    # en ambas direcciones para absorber estas diferencias.
    hoy = today_rd()
    if (fecha - hoy).days > 1:  # más de 1 día en el futuro
        return JSONResponse(
            {'error': f'No se puede registrar asistencia con fecha futura ({fecha.isoformat()})'},
            status_code=400
        )
    if (hoy - fecha).days > 365 * 5:
        return JSONResponse(
            {'error': f'La fecha es demasiado antigua ({fecha.isoformat()}). Verificá que sea correcta.'},
            status_code=400
        )
    
    # v2.13.1: Validar día de la semana según configuración del colegio.
    # Default: lunes-viernes habilitados, sábado y domingo deshabilitados.
    # Un colegio que tiene clases los sábados puede activar permite_sabado.
    dia_semana = fecha.weekday()  # 0=Lunes ... 5=Sábado, 6=Domingo
    if dia_semana >= 5:  # fin de semana
        config = tenant_filter(db.query(ConfiguracionColegio), ConfiguracionColegio, current_user).first()
        if dia_semana == 5 and (not config or not getattr(config, 'permite_sabado', False)):
            return JSONResponse({
                'error': f'No se registra asistencia los sábados en este colegio',
                'fecha': fecha.isoformat(),
                'dia': 'sábado',
                'hint': 'Si su colegio tiene clases los sábados, active "permite_sabado" en Configuración.',
            }, status_code=400)
        if dia_semana == 6 and (not config or not getattr(config, 'permite_domingo', False)):
            return JSONResponse({
                'error': f'No se registra asistencia los domingos en este colegio',
                'fecha': fecha.isoformat(),
                'dia': 'domingo',
                'hint': 'Si su colegio tiene clases los domingos, active "permite_domingo" en Configuración.',
            }, status_code=400)
    
    # Obtener asignatura_id (puede ser None para asistencia general en primaria)
    asignatura_id = data.get('asignatura_id')
    
    # Buscar asistencia existente (por estudiante, fecha Y asignatura)
    query = tenant_filter(db.query(Asistencia), Asistencia, current_user).filter_by(
        estudiante_id=data['estudiante_id'],
        fecha=fecha
    )
    if asignatura_id:
        query = query.filter_by(asignatura_id=asignatura_id)
    else:
        query = query.filter(Asistencia.asignatura_id.is_(None))
    
    asistencia = query.first()
    
    if asistencia:
        asistencia.estado = estado
        asistencia.observacion = data.get('observacion', '')
    else:
        asistencia = Asistencia(
            estudiante_id=data['estudiante_id'],
            curso_id=estudiante.curso_id,
            asignatura_id=asignatura_id,
            fecha=fecha,
            estado=estado,
            registrado_por=current_user.id,
            observacion=data.get('observacion', ''),
            colegio_id=current_user.colegio_id
        )
        db.add(asistencia)
    
    db.commit()
    cache_clear_tenant(current_user.colegio_id)
    cache_clear(f'stats:{current_user.colegio_id}')
    cache_clear(f'dash_all:{current_user.id}')
    return {'message': 'Asistencia registrada'}

@app.delete("/api/asistencia/{estudiante_id}")
async def desmarcar_asistencia(estudiante_id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Desmarcar/eliminar asistencia de un estudiante en una fecha y asignatura."""
    fecha_str = request.query_params.get('fecha', today_rd().isoformat())
    asignatura_id = request.query_params.get('asignatura_id')
    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return JSONResponse(
            {'error': f"fecha inválida: {fecha_str!r}. Formato esperado: YYYY-MM-DD"},
            status_code=400
        )
    
    query = tenant_filter(db.query(Asistencia), Asistencia, current_user).filter_by(
        estudiante_id=int(estudiante_id), fecha=fecha
    )
    if asignatura_id:
        query = query.filter_by(asignatura_id=int(asignatura_id))
    
    asistencia = query.first()
    if asistencia:
        db.delete(asistencia)
        db.commit()
        cache_clear(f'stats:{current_user.colegio_id}')
        return {'message': 'Asistencia desmarcada'}
    return JSONResponse({'error': 'No encontrada'}, status_code=404)

@app.get("/api/asistencia/resumen/{curso_id}")
async def get_resumen_asistencia(curso_id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Resumen de asistencia de un curso por mes (sin N+1, validado por tenant)."""
    # Validar tenant del curso
    curso = get_tenant_or_404(db, Curso, curso_id, current_user, name='curso')
    
    try:
        mes = int(request.query_params.get('mes', today_rd().month))
        ano = int(request.query_params.get('ano', today_rd().year))
    except (ValueError, TypeError):
        return JSONResponse({'error': 'mes/ano deben ser enteros'}, status_code=400)
    
    if not (1 <= mes <= 12):
        return JSONResponse({'error': 'mes fuera de rango (1-12)'}, status_code=400)
    
    estudiantes = tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(
        curso_id=curso.id, activo=True
    ).all()
    if not estudiantes:
        return []
    est_ids = [e.id for e in estudiantes]
    
    # Una sola query para TODAS las asistencias del mes (sin N+1)
    todas_asistencias = tenant_filter(db.query(Asistencia), Asistencia, current_user).filter(
        Asistencia.estudiante_id.in_(est_ids),
        extract('month', Asistencia.fecha) == mes,
        extract('year', Asistencia.fecha) == ano
    ).all()
    
    # Agrupar en memoria por estudiante
    from collections import defaultdict
    asist_por_est = defaultdict(list)
    for a in todas_asistencias:
        asist_por_est[a.estudiante_id].append(a)
    
    resultado = []
    for est in estudiantes:
        asist_lista = asist_por_est.get(est.id, [])
        
        # Agrupar por fecha (un estado por día — el más favorable)
        asist_por_dia = {}
        prioridad = {'presente': 4, 'tardanza': 3, 'excusa': 2, 'ausente': 1}
        for a in asist_lista:
            fecha_key = a.fecha.isoformat()
            estado_actual = asist_por_dia.get(fecha_key, 'ausente')
            if prioridad.get(a.estado, 0) > prioridad.get(estado_actual, 0):
                asist_por_dia[fecha_key] = a.estado
        
        estados = list(asist_por_dia.values())
        presentes = sum(1 for e in estados if e == 'presente')
        ausentes = sum(1 for e in estados if e == 'ausente')
        tardanzas = sum(1 for e in estados if e == 'tardanza')
        excusas = sum(1 for e in estados if e == 'excusa')
        total_dias = len(estados)
        
        resultado.append({
            'estudiante_id': est.id,
            'estudiante': est.nombre_completo,
            'presentes': presentes,
            'ausentes': ausentes,
            'tardanzas': tardanzas,
            'excusas': excusas,
            'total': total_dias,
            'porcentaje': round(presentes / total_dias * 100, 1) if total_dias > 0 else 0
        })
    
    return resultado


@app.get("/api/asistencia/curso/{curso_id}")
async def get_asistencia_curso(curso_id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Asistencia de un curso para una fecha y asignatura (sin N+1, validado por tenant)."""
    # Validar tenant del curso
    curso = get_tenant_or_404(db, Curso, curso_id, current_user, name='curso')
    
    fecha_str = request.query_params.get('fecha', today_rd().isoformat())
    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return JSONResponse({'error': f'fecha inválida: {fecha_str!r}. Formato YYYY-MM-DD'}, status_code=400)
    
    try:
        asignatura_id = int(request.query_params.get('asignatura_id', 0) or 0)
    except (ValueError, TypeError):
        return JSONResponse({'error': 'asignatura_id debe ser entero'}, status_code=400)
    
    if asignatura_id:
        get_tenant_or_404(db, Asignatura, asignatura_id, current_user, name='asignatura')
    
    # Incluimos retirados también — el profesor los ve con badge readonly.
    # Filtrar SOLO activos sería ocultar información que el profesor necesita.
    estudiantes = tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(
        curso_id=curso.id
    ).order_by(Estudiante.no_lista).all()
    if not estudiantes:
        return []
    est_ids = [e.id for e in estudiantes]
    
    # Una sola query para todas las asistencias (sin N+1)
    asist_query = tenant_filter(db.query(Asistencia), Asistencia, current_user).filter(
        Asistencia.estudiante_id.in_(est_ids),
        Asistencia.fecha == fecha,
    )
    if asignatura_id:
        asist_query = asist_query.filter_by(asignatura_id=asignatura_id)
    else:
        asist_query = asist_query.filter(Asistencia.asignatura_id.is_(None))
    asist_map = {a.estudiante_id: a for a in asist_query.all()}
    
    resultado = []
    for est in estudiantes:
        asistencia = asist_map.get(est.id)
        resultado.append({
            'estudiante': {
                'id': est.id,
                'nombre_completo': est.nombre_completo,
                'no_lista': est.no_lista,
                # Flags de retiro: el frontend los usa para deshabilitar marcas y mostrar badge
                'retirado': not est.activo,
                'fecha_retiro': est.fecha_retiro.isoformat() if est.fecha_retiro else None,
                'motivo_retiro': est.motivo_retiro,
            },
            'asistencia': {
                'estado': asistencia.estado if asistencia else None,
                'observacion': asistencia.observacion if asistencia else None,
                'registrado_por': asistencia.registrado_por if asistencia else None
            } if asistencia else None
        })
    
    return {'asistencias': resultado}

@app.post("/api/asistencia/masivo")
async def registrar_asistencia_masivo(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Registrar asistencia de múltiples estudiantes por materia"""
    data = await request.json()
    fecha_str = data.get('fecha', today_rd().isoformat())
    asignatura_id = data.get('asignatura_id')  # Puede ser None
    
    # Parsear fecha
    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        fecha = today_rd()
    
    asistencias = data.get('asistencias', [])
    if not asistencias:
        return {'message': 'Sin cambios'}
    
    # v2.13.1: Validar día de la semana según configuración del colegio
    dia_semana = fecha.weekday()
    if dia_semana >= 5:
        config = tenant_filter(db.query(ConfiguracionColegio), ConfiguracionColegio, current_user).first()
        if dia_semana == 5 and (not config or not getattr(config, 'permite_sabado', False)):
            return JSONResponse({
                'error': 'No se registra asistencia los sábados en este colegio',
                'fecha': fecha.isoformat(), 'dia': 'sábado',
                'hint': 'Active "permite_sabado" en Configuración si su colegio tiene clases sábados.',
            }, status_code=400)
        if dia_semana == 6 and (not config or not getattr(config, 'permite_domingo', False)):
            return JSONResponse({
                'error': 'No se registra asistencia los domingos en este colegio',
                'fecha': fecha.isoformat(), 'dia': 'domingo',
                'hint': 'Active "permite_domingo" en Configuración si su colegio tiene clases domingos.',
            }, status_code=400)
    
    # Validar nivel UNA VEZ usando el primer estudiante (todos deben ser del
    # mismo curso típicamente — si no, fallará por tenant individual abajo)
    primer_est_id = asistencias[0].get('estudiante_id') if asistencias else None
    if primer_est_id:
        primer_est = db.get(Estudiante, primer_est_id)
        if primer_est and primer_est.colegio_id == current_user.colegio_id and primer_est.curso_id:
            assert_nivel_curso_activo(db, current_user, primer_est.curso_id)
    
    for item in asistencias:
        estudiante = db.get(Estudiante, item['estudiante_id'])
        if not estudiante:
            continue
        # Validar tenant: skip silently estudiantes de otro colegio
        if current_user.role != 'superadmin' and estudiante.colegio_id != current_user.colegio_id:
            continue
        # Skip silently estudiantes retirados — el frontend ya los muestra
        # con botones deshabilitados, pero por seguridad backend también ignora.
        if not estudiante.activo:
            continue
        
        # Buscar asistencia existente por estudiante, fecha y asignatura
        query = tenant_filter(db.query(Asistencia), Asistencia, current_user).filter_by(
            estudiante_id=item['estudiante_id'],
            fecha=fecha
        )
        if asignatura_id:
            query = query.filter_by(asignatura_id=asignatura_id)
        else:
            query = query.filter(Asistencia.asignatura_id.is_(None))
        
        asistencia = query.first()
        
        if asistencia:
            asistencia.estado = item['estado']
        else:
            asistencia = Asistencia(
                colegio_id=current_user.colegio_id,
                estudiante_id=item['estudiante_id'],
                curso_id=estudiante.curso_id,
                asignatura_id=asignatura_id,
                fecha=fecha,
                estado=item['estado'],
                registrado_por=current_user.id
            )
            db.add(asistencia)
    
    db.commit()
    cache_clear_tenant(current_user.colegio_id)
    cache_clear(f'stats:{current_user.colegio_id}')
    cache_clear(f'dash_all:{current_user.id}')
    return {'message': 'Asistencia registrada'}


# ============== HISTORIAL DE COMUNICACIONES A PADRES ==============

@app.post("/api/comunicacion-padres")
async def registrar_comunicacion_padres(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Registrar una comunicación enviada a los padres (para evidencia)"""
    
    # Validar que el módulo esté en el plan del colegio
    assert_modulo_activo(db, current_user, 'comunicacion_padres')
    
    data = await request.json()
    
    comunicacion = HistorialComunicacionPadres(
        estudiante_id=data.get('estudiante_id'),
        tipo_comunicacion=data.get('tipo', 'reporte'),
        referencia_id=data.get('referencia_id'),
        mensaje_enviado=data.get('mensaje'),
        medio=data.get('medio', 'whatsapp'),
        telefono_destino=data.get('telefono'),
        enviado_por=current_user.id,
        colegio_id=current_user.colegio_id
    )
    
    db.add(comunicacion)
    db.commit()
    
    log_auditoria(db, 'COMUNICACION_PADRES', 'historial_comunicacion_padres', comunicacion.id, None, {
        'estudiante_id': data.get('estudiante_id'),
        'tipo': data.get('tipo')
    }, user=current_user, request=request)
    
    return JSONResponse({'message': 'Comunicación registrada', 'id': comunicacion.id}, status_code=201)


@app.get("/api/comunicacion-padres/estudiante/{estudiante_id}")
async def get_historial_comunicaciones(estudiante_id, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Obtener historial de comunicaciones de un estudiante"""
    
    comunicaciones = tenant_filter(db.query(HistorialComunicacionPadres), HistorialComunicacionPadres, current_user).filter_by(
        estudiante_id=estudiante_id
    ).order_by(HistorialComunicacionPadres.fecha_envio.desc()).all()
    
    return [{
        'id': c.id,
        'tipo': c.tipo_comunicacion,
        'mensaje': c.mensaje_enviado[:200] + '...' if len(c.mensaje_enviado or '') > 200 else c.mensaje_enviado,
        'medio': c.medio,
        'enviado_por': c.usuario.nombre_completo if c.usuario else 'Sistema',
        'fecha': c.fecha_envio.isoformat() if c.fecha_envio else None
    } for c in comunicaciones]


# ============== BOLETINES ==============

@app.get("/api/boletines/estudiante/{id}")
async def get_boletin_estudiante(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Obtener boletín de un estudiante con estructura completa de calificaciones.
    
    v2.13.7: lee AMBOS modelos (Calificacion legacy + CalificacionSecundaria
    nuevo MINERD). Para secundaria nueva, calcula PC1..PC4 como AVG de las
    4 competencias por período, y CF como AVG(PC1..PC4).
    Devuelve formato compatible con el frontend existente.
    """
    estudiante = get_tenant_or_404(db, Estudiante, id, current_user, name='estudiante')
    
    # Asistencia (sin cambios — el modelo Asistencia no fue afectado)
    asistencias = tenant_filter(db.query(Asistencia), Asistencia, current_user).filter_by(estudiante_id=id).all()
    presentes = sum(1 for a in asistencias if a.estado == 'presente')
    total_dias = len(asistencias)
    
    # ─── 1. CalificacionSecundaria (modelo nuevo MINERD) ───
    asignaturas_por_id: dict = {}  # asig_id → dict del boletín
    ano_activo = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    
    if ano_activo:
        califs_sec = tenant_filter(
            db.query(CalificacionSecundaria), CalificacionSecundaria, current_user
        ).filter_by(estudiante_id=id, ano_escolar_id=ano_activo.id).all()
        
        # Agrupar por asignatura → lista de 4 competencias
        from collections import defaultdict as _dd
        comps_por_asig = _dd(list)
        for c in califs_sec:
            comps_por_asig[c.asignatura_id].append(c)
        
        # Para cada asignatura: calcular PC[1..4] y CF
        for aid, comps in comps_por_asig.items():
            asig_obj = db.get(Asignatura, aid)
            asig_nombre = asig_obj.nombre if asig_obj else 'Sin asignatura'
            
            pcs = {}  # pc1, pc2, pc3, pc4
            rps_minimas = {}  # rp1..rp4 (la rp más baja por período — solo informativo)
            for p in range(1, 5):
                vals = []
                rps_periodo = []
                for c in comps:
                    v = c.valor_periodo(p) if hasattr(c, 'valor_periodo') else None
                    if v is not None:
                        vals.append(v)
                    rp_val = getattr(c, f'rp{p}', None)
                    if rp_val is not None:
                        rps_periodo.append(rp_val)
                pcs[f'pc{p}'] = round(sum(vals) / len(vals), 1) if vals else None
                rps_minimas[f'rp{p}'] = min(rps_periodo) if rps_periodo else None
            
            # CF anual = AVG(PC1..PC4) entero
            pcs_validos = [v for v in pcs.values() if v is not None]
            cf = int(round(sum(pcs_validos) / len(pcs_validos))) if pcs_validos else None
            
            # Buscar evaluacion extra si existe
            ev_extra = tenant_filter(
                db.query(EvaluacionExtraSecundaria), EvaluacionExtraSecundaria, current_user
            ).filter_by(
                estudiante_id=id, asignatura_id=aid, ano_escolar_id=ano_activo.id
            ).first()
            
            # Literal
            def _literal(n):
                if n is None: return ''
                if n >= 90: return 'A'
                if n >= 80: return 'B'
                if n >= 70: return 'C'
                return 'F'
            
            asignaturas_por_id[aid] = {
                'asignatura': asig_nombre,
                'asignatura_id': aid,
                'pc1': pcs['pc1'], 'rp1': rps_minimas['rp1'],
                'pc2': pcs['pc2'], 'rp2': rps_minimas['rp2'],
                'pc3': pcs['pc3'], 'rp3': rps_minimas['rp3'],
                'pc4': pcs['pc4'], 'rp4': rps_minimas['rp4'],
                'cf': cf,
                'literal': _literal(cf),
                # Bonus para el frontend: si hay evaluación extra resuelta, exponer nota_final
                'nota_final': ev_extra.nota_final if ev_extra else cf,
                'condicion_final': ev_extra.condicion_final if ev_extra else None,
            }
    
    # ─── 2. Calificacion (modelo legacy) ───
    # Solo agregamos las que NO están ya en el dict (modelo nuevo prevalece)
    calificaciones = tenant_filter(db.query(Calificacion), Calificacion, current_user).filter_by(estudiante_id=id).all()
    for cal in calificaciones:
        if cal.asignatura_id in asignaturas_por_id:
            continue  # ya cargada del modelo nuevo
        asignaturas_por_id[cal.asignatura_id] = {
            'asignatura': cal.asignatura.nombre if cal.asignatura else 'Sin asignatura',
            'asignatura_id': cal.asignatura_id,
            'pc1': cal.pc1, 'rp1': cal.rp1,
            'pc2': cal.pc2, 'rp2': cal.rp2,
            'pc3': cal.pc3, 'rp3': cal.rp3,
            'pc4': cal.pc4, 'rp4': cal.rp4,
            'cf': cal.cf,
            'literal': cal.literal or cal.get_literal(),
        }
    
    # Convertir dict → lista (orden alfabético)
    asignaturas = sorted(asignaturas_por_id.values(), key=lambda x: x['asignatura'])
    cfs_validos = [a['cf'] for a in asignaturas if a['cf'] is not None]
    promedio_general = sum(cfs_validos) / len(cfs_validos) if cfs_validos else 0
    
    return {
        'estudiante': {
            'id': estudiante.id,
            'nombre': estudiante.nombre_completo,
            'matricula': estudiante.matricula,
            'curso': estudiante.curso.nombre_completo if estudiante.curso else None,
            'grado': estudiante.curso.grado.nombre if estudiante.curso and estudiante.curso.grado else None
        },
        'asignaturas': asignaturas,
        'asistencia': {
            'presentes': presentes,
            'total': total_dias,
            'porcentaje': round(presentes / total_dias * 100, 1) if total_dias > 0 else 0
        },
        'promedio_general': round(promedio_general, 2)
    }


@app.get("/api/boletines/estudiante/{id}/pdf")
async def generar_boletin_pdf(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion', 'coordinador', 'profesor', 'secretaria'))):
    """Boletin para PADRES - reporte detallado de calificaciones (v2.13.36).

    Documento formal con el detalle completo por competencia y periodo.
    Sirve para comunicacion con padres y como constancia de traslado.
    Muestra TODAS las asignaturas del curso. El PC de cada competencia
    aparece solo si sus 4 periodos estan completos.
    """
    from boletin_padres import generar_boletin_padres

    estudiante = get_tenant_or_404(db, Estudiante, id, current_user, name='estudiante')
    config = tenant_filter(db.query(ConfiguracionColegio), ConfiguracionColegio, current_user).first()
    ano = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    if not ano:
        ano = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).order_by(AnoEscolar.id.desc()).first()
    curso = estudiante.curso
    if not curso:
        return JSONResponse({'error': 'El estudiante no tiene curso asignado.'}, status_code=400)

    # TODAS las asignaturas del curso (via asignaciones de profesores del curso)
    asignaciones = tenant_filter(db.query(AsignacionProfesor), AsignacionProfesor, current_user).filter_by(curso_id=curso.id).all()
    asig_ids = []
    for a in asignaciones:
        if a.asignatura_id not in asig_ids:
            asig_ids.append(a.asignatura_id)

    # Calificaciones del estudiante en secundaria
    califs_est = []
    if ano:
        califs_est = tenant_filter(db.query(CalificacionSecundaria), CalificacionSecundaria, current_user).filter_by(
            estudiante_id=id, ano_escolar_id=ano.id
        ).all()
    # Agregar asignaturas que tengan notas aunque no esten en asignaciones
    for cal in califs_est:
        if cal.asignatura_id not in asig_ids:
            asig_ids.append(cal.asignatura_id)

    if not asig_ids:
        return JSONResponse({
            'error': f'{estudiante.nombre_completo} no tiene asignaturas ni calificaciones en su curso.'
        }, status_code=400)

    # Construir datos por asignatura: {nombre, competencias: {1..4: comp_obj}}
    asignaturas_data = []
    for aid in asig_ids:
        asig_obj = tenant_filter(db.query(Asignatura), Asignatura, current_user).filter_by(id=aid).first()
        if not asig_obj:
            continue
        competencias = {}
        for cal in califs_est:
            if cal.asignatura_id == aid and cal.competencia_numero in (1, 2, 3, 4):
                competencias[cal.competencia_numero] = cal
        asignaturas_data.append({
            'nombre': asig_obj.nombre,
            'competencias': competencias,
        })

    asignaturas_data.sort(key=lambda a: a['nombre'])

    try:
        buffer = generar_boletin_padres(
            estudiante=estudiante,
            curso=curso,
            asignaturas_data=asignaturas_data,
            config=config,
            ano_nombre=ano.nombre if ano else '',
        )
    except Exception as e:
        logger.error(f"Error generando boletin de padres para estudiante {id}: {e}", exc_info=True)
        return JSONResponse({
            'error': f'Error generando PDF: {type(e).__name__}: {str(e)[:150]}'
        }, status_code=500)

    filename = f"Reporte_Calificaciones_{estudiante.nombre_completo.replace(' ', '_')}.pdf"
    return StreamingResponse(buffer, media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename="{filename}"'})


@app.get("/api/boletines/curso/{curso_id}/pdf")
async def generar_boletines_curso_pdf(curso_id, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion', 'coordinador', 'secretaria'))):
    """Boletines para PADRES de todo un curso en un solo PDF (v2.13.36).

    Genera el boletin de padres detallado (por competencia y periodo) de
    cada estudiante del curso, combinados en un unico PDF.
    """
    from boletin_padres import generar_boletin_padres
    from pypdf import PdfReader, PdfWriter

    curso = get_tenant_or_404(db, Curso, curso_id, current_user, name='curso')
    config = tenant_filter(db.query(ConfiguracionColegio), ConfiguracionColegio, current_user).first()
    ano = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    if not ano:
        ano = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).order_by(AnoEscolar.id.desc()).first()

    estudiantes = tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(
        curso_id=curso_id, activo=True
    ).order_by(Estudiante.apellido, Estudiante.nombre).all()

    if not estudiantes:
        return JSONResponse({'error': 'El curso no tiene estudiantes activos.'}, status_code=400)

    # Asignaturas del curso (una sola vez para todos)
    asignaciones = tenant_filter(db.query(AsignacionProfesor), AsignacionProfesor, current_user).filter_by(curso_id=curso_id).all()
    asig_ids = []
    for a in asignaciones:
        if a.asignatura_id not in asig_ids:
            asig_ids.append(a.asignatura_id)

    writer = PdfWriter()
    generados = 0
    for estudiante in estudiantes:
        califs_est = []
        if ano:
            califs_est = tenant_filter(db.query(CalificacionSecundaria), CalificacionSecundaria, current_user).filter_by(
                estudiante_id=estudiante.id, ano_escolar_id=ano.id
            ).all()
        # asignaturas de este estudiante (curso + las que tengan notas)
        est_asig_ids = list(asig_ids)
        for cal in califs_est:
            if cal.asignatura_id not in est_asig_ids:
                est_asig_ids.append(cal.asignatura_id)
        if not est_asig_ids:
            continue
        asignaturas_data = []
        for aid in est_asig_ids:
            asig_obj = tenant_filter(db.query(Asignatura), Asignatura, current_user).filter_by(id=aid).first()
            if not asig_obj:
                continue
            competencias = {}
            for cal in califs_est:
                if cal.asignatura_id == aid and cal.competencia_numero in (1, 2, 3, 4):
                    competencias[cal.competencia_numero] = cal
            asignaturas_data.append({'nombre': asig_obj.nombre, 'competencias': competencias})
        asignaturas_data.sort(key=lambda a: a['nombre'])
        try:
            buf = generar_boletin_padres(
                estudiante=estudiante, curso=curso, asignaturas_data=asignaturas_data,
                config=config, ano_nombre=ano.nombre if ano else '',
            )
            reader = PdfReader(buf)
            for page in reader.pages:
                writer.add_page(page)
            generados += 1
        except Exception as e:
            logger.error(f"Error boletin padres curso, estudiante {estudiante.id}: {e}")
            continue

    if generados == 0:
        return JSONResponse({'error': 'No se pudo generar ningun boletin (sin calificaciones).'}, status_code=400)

    out = io.BytesIO()
    writer.write(out)
    out.seek(0)
    filename = f"Boletines_Padres_{curso.nombre.replace(' ', '_')}.pdf"
    return StreamingResponse(out, media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename="{filename}"'})


def _construir_datos_boletin_secundaria(db, estudiante, curso, current_user, ano):
    """Helper que arma el dict calificaciones_por_asig esperado por
    generar_boletin_secundaria_minerd, leyendo de la BD las
    CalificacionSecundaria y EvaluacionExtraSecundaria del estudiante.
    """
    # Todas las asignaturas que cursa (vía AsignacionCurso o similar)
    # En este sistema, las asignaturas asociadas al curso vienen de Asignatura
    # filtradas por colegio_id. Tomamos solo asignaturas de secundaria.
    asignaturas = tenant_filter(db.query(Asignatura), Asignatura, current_user).all()
    
    califs_estudiante = tenant_filter(
        db.query(CalificacionSecundaria), CalificacionSecundaria, current_user
    ).filter_by(estudiante_id=estudiante.id, ano_escolar_id=ano.id).all()
    
    # Indexar califs por (asig_id, comp_num)
    califs_idx = {}
    for c in califs_estudiante:
        califs_idx.setdefault(c.asignatura_id, {})[c.competencia_numero] = c
    
    extras_estudiante = tenant_filter(
        db.query(EvaluacionExtraSecundaria), EvaluacionExtraSecundaria, current_user
    ).filter_by(estudiante_id=estudiante.id, ano_escolar_id=ano.id).all()
    extras_idx = {e.asignatura_id: e for e in extras_estudiante}
    
    resultado = {}
    for asig in asignaturas:
        comps_dict = califs_idx.get(asig.id, {})
        if not comps_dict:
            continue  # estudiante no tiene notas en esta asignatura
        
        comps_list = [comps_dict[n] for n in sorted(comps_dict.keys())]
        
        # PC1-PC4
        pcs = {}
        if len(comps_list) == 4:
            for p in range(1, 5):
                pcs[f'pc{p}'] = CalificacionSecundaria.calcular_pc_periodo(comps_list, p)
        else:
            pcs = {f'pc{p}': None for p in range(1, 5)}
        
        # CF
        cf, literal = _calcular_cf_secundaria(db, estudiante.id, asig.id, ano.id)
        
        resultado[asig.id] = {
            'asignatura_nombre': asig.nombre,
            'competencias': comps_list,
            'pc_por_periodo': pcs,
            'cf': cf,
            'literal': literal,
            'evaluacion_extra': extras_idx.get(asig.id),
        }
    
    return resultado


def _construir_asistencias_boletin(db, estudiante_id, current_user, ano):
    """Helper que arma el dict asistencias_por_periodo desde la BD.
    
    Los períodos (P1-P4) están definidos en AnoEscolar como p1_inicio/p1_fin, etc.
    
    v2.13.3: si AnoEscolar no tiene los rangos p1_inicio/p1_fin configurados,
    o si una asistencia cae FUERA de todos los rangos, ya NO se descarta
    silenciosamente. En cambio, se hace fallback inteligente:
      1. Si AnoEscolar tiene fecha_inicio y fecha_fin, dividir en 4 trimestres iguales
      2. Si una fecha cae fuera de todo rango pero está dentro del año, mapearla
         al período más cercano (no perderla)
      3. Si no hay año escolar válido, usar el año calendario actual dividido en 4
    """
    asistencias = tenant_filter(
        db.query(Asistencia), Asistencia, current_user
    ).filter_by(estudiante_id=estudiante_id).all()
    
    # Construir rangos de períodos con fallback
    rangos = []
    if ano:
        for p in range(1, 5):
            ini = getattr(ano, f'p{p}_inicio', None)
            fin = getattr(ano, f'p{p}_fin', None)
            if ini and fin:
                rangos.append((p, ini, fin))
    
    # Fallback 1: si no hay períodos configurados, dividir el rango del año en 4
    if not rangos and ano:
        fi = getattr(ano, 'fecha_inicio', None)
        ff = getattr(ano, 'fecha_fin', None)
        if fi and ff:
            from datetime import timedelta as _td
            total_dias = (ff - fi).days
            if total_dias > 0:
                paso = total_dias // 4
                for p in range(1, 5):
                    ini_p = fi + _td(days=paso * (p - 1))
                    fin_p = ff if p == 4 else fi + _td(days=paso * p - 1)
                    rangos.append((p, ini_p, fin_p))
    
    # Fallback 2: si todavía no hay rangos, usar año calendario actual
    if not rangos:
        from datetime import date as _date
        hoy = today_rd()
        year = hoy.year
        rangos = [
            (1, _date(year, 1, 1), _date(year, 3, 31)),
            (2, _date(year, 4, 1), _date(year, 6, 30)),
            (3, _date(year, 7, 1), _date(year, 9, 30)),
            (4, _date(year, 10, 1), _date(year, 12, 31)),
        ]
    
    def periodo_de_fecha(fecha):
        # Match exacto
        for p, ini, fin in rangos:
            if ini <= fecha <= fin:
                return p
        # Fallback: período más cercano por proximidad al inicio/fin
        # (en lugar de descartar la asistencia, la mapeamos al más cercano)
        mejor_p = None
        mejor_dist = None
        for p, ini, fin in rangos:
            d_ini = abs((fecha - ini).days)
            d_fin = abs((fecha - fin).days)
            dist = min(d_ini, d_fin)
            if mejor_dist is None or dist < mejor_dist:
                mejor_dist = dist
                mejor_p = p
        return mejor_p
    
    conteo = {1: {'a': 0, 'au': 0}, 2: {'a': 0, 'au': 0},
              3: {'a': 0, 'au': 0}, 4: {'a': 0, 'au': 0}}
    total_a = 0
    total_au = 0
    for a in asistencias:
        p = periodo_de_fecha(a.fecha) if a.fecha else None
        if p:
            if a.estado == 'presente':
                conteo[p]['a'] += 1
                total_a += 1
            elif a.estado in ('ausente', 'ausente_justificado'):
                conteo[p]['au'] += 1
                total_au += 1
    
    total = total_a + total_au
    
    resultado = {}
    for p in range(1, 5):
        d = conteo[p]
        sub_total = d['a'] + d['au']
        resultado[f'p{p}'] = {
            'asistencia': d['a'],
            'ausencia': d['au'],
            # v2.13.3: % POR PERÍODO (no anual). Antes confundía: el campo decía 'anual'
            # pero realmente era del período. El frontend renombra al mostrar.
            'pct_asistencia_anual': round((d['a'] / sub_total * 100), 0) if sub_total > 0 else None,
            'pct_ausencia_anual': round((d['au'] / sub_total * 100), 0) if sub_total > 0 else None,
        }
    return resultado



@app.get("/api/boletines/estudiante/{id}/pdf-minerd-v2")
async def generar_boletin_minerd_v2(
    id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(RolesRequired('direccion', 'coordinador', 'profesor', 'secretaria'))
):
    """Boletín MINERD pixel-exacto (v2.13).
    
    Usa modelo CalificacionSecundaria + EvaluacionExtraSecundaria y overlayea
    sobre plantilla PDF oficial MINERD.
    
    v2.13.9: validaciones tempranas + mensajes específicos de error.
    """
    from boletin_minerd_secundaria import generar_boletin_secundaria_minerd
    
    estudiante = get_tenant_or_404(db, Estudiante, id, current_user, name='estudiante')
    curso = estudiante.curso
    if not curso:
        return JSONResponse({'error': 'Estudiante sin curso asignado'}, status_code=400)
    if not _es_curso_secundaria(db, curso.id):
        return JSONResponse(
            {'error': 'Este boletín es solo para estudiantes de secundaria. Para primaria/legacy usá el botón "Descargar PDF" en /boletines.'},
            status_code=400
        )
    
    config = tenant_filter(db.query(ConfiguracionColegio), ConfiguracionColegio, current_user).first()
    ano = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    if not ano:
        # v2.13.19: año cerrado tras promover → usar el más reciente
        ano = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).order_by(AnoEscolar.id.desc()).first()
    if not ano:
        return JSONResponse({'error': 'No hay año escolar configurado. Configurá uno en Configuración → Año Escolar.'}, status_code=404)
    
    # v2.13.9: validar que tenga al menos algunas calificaciones cargadas ANTES de armar el PDF
    califs_count = tenant_filter(
        db.query(CalificacionSecundaria), CalificacionSecundaria, current_user
    ).filter_by(estudiante_id=estudiante.id, ano_escolar_id=ano.id).count()
    if califs_count == 0:
        return JSONResponse({
            'error': f'{estudiante.nombre_completo} no tiene calificaciones cargadas para este año escolar. Cargá notas en /academico antes de generar el boletín.'
        }, status_code=400)
    
    # Construir datos
    try:
        califs_por_asig = _construir_datos_boletin_secundaria(db, estudiante, curso, current_user, ano)
        asistencias = _construir_asistencias_boletin(db, estudiante.id, current_user, ano)
    except Exception as e:
        logger.error(f"Error construyendo datos del boletín para estudiante {id}: {e}", exc_info=True)
        return JSONResponse({'error': f'Error preparando datos del boletín: {str(e)[:120]}'}, status_code=500)
    
    if not califs_por_asig:
        return JSONResponse({
            'error': f'{estudiante.nombre_completo} no tiene calificaciones completas (las 4 competencias) en ninguna asignatura. Verificá que los profesores hayan cargado todas las competencias.'
        }, status_code=400)
    
    # Situación final (calculada a partir de notas)
    aprobadas = 0
    reprobadas = 0
    for asig_id, data in califs_por_asig.items():
        ev = data.get('evaluacion_extra')
        nota_final = None
        if ev:
            nota_final = (getattr(ev, 'nota_final', None) or
                          getattr(ev, 'especial_final', None) or
                          getattr(ev, 'extraordinaria_final', None) or
                          getattr(ev, 'completiva_final', None))
        if nota_final is None:
            nota_final = data.get('cf')
        if nota_final is not None:
            if nota_final >= 70:
                aprobadas += 1
            else:
                reprobadas += 1
    
    promovido = reprobadas == 0 and aprobadas > 0
    repitente = reprobadas > 2  # MINERD: más de 2 reprobadas → repitente
    
    situacion = {
        'promovido': promovido,
        'repitente': repitente,
        'condicion': request.query_params.get('condicion', 
            'APROBADO/A — Promovido' if promovido else
            ('REPITENTE — Debe repetir el grado' if repitente else 
             'PENDIENTE — Evaluaciones extra en curso'))
    }
    
    observaciones = request.query_params.get('observaciones', '')
    
    # v2.13.18: docente encargado del grado = profesor titular del curso
    docente_nombre = ''
    try:
        asig_titular = tenant_filter(db.query(AsignacionProfesor), AsignacionProfesor, current_user).filter_by(
            curso_id=curso.id, activo=True, es_titular=True
        ).first()
        if not asig_titular:
            asig_titular = tenant_filter(db.query(AsignacionProfesor), AsignacionProfesor, current_user).filter_by(
                curso_id=curso.id, activo=True
            ).first()
        if asig_titular:
            prof = db.get(Usuario, asig_titular.profesor_id)
            if prof:
                docente_nombre = f"{getattr(prof, 'nombre', '')} {getattr(prof, 'apellido', '')}".strip()
    except Exception as e:
        logger.warning(f"No se pudo obtener docente titular del curso {curso.id}: {e}")
    
    # v2.13.9: try/except amplio para capturar errores de plantilla, dibujado, merge PDF
    try:
        buffer = generar_boletin_secundaria_minerd(
            estudiante=estudiante,
            curso=curso,
            calificaciones_por_asig=califs_por_asig,
            asistencias_por_periodo=asistencias,
            config=config,
            ano_escolar=ano,
            observaciones=observaciones,
            situacion_final=situacion,
            docente_nombre=docente_nombre,
        )
    except FileNotFoundError as e:
        logger.error(f"Plantilla MINERD no encontrada: {e}")
        return JSONResponse({
            'error': f'Plantilla MINERD no encontrada en el servidor. Contactá soporte. Detalle: {str(e)[:100]}'
        }, status_code=500)
    except Exception as e:
        logger.error(f"Error generando boletín MINERD para estudiante {id}: {e}", exc_info=True)
        return JSONResponse({
            'error': f'Error generando el PDF del boletín. Detalle técnico: {type(e).__name__}: {str(e)[:120]}'
        }, status_code=500)
    
    nombre_archivo = f"Boletin_MINERD_{estudiante.nombre}_{estudiante.apellido}".replace(' ', '_')
    return StreamingResponse(
        buffer,
        media_type='application/pdf',
        headers={'Content-Disposition': f'attachment; filename="{nombre_archivo}.pdf"'}
    )


@app.get("/api/boletines/curso/{curso_id}/pdf-minerd-v2")
async def generar_boletines_curso_minerd_v2(
    curso_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(RolesRequired('direccion', 'coordinador', 'secretaria'))
):
    """Boletines MINERD pixel-exacto de todo un curso (en un solo PDF, v2.13)."""
    from boletin_minerd_secundaria import generar_boletin_secundaria_minerd
    
    curso = get_tenant_or_404(db, Curso, curso_id, current_user, name='curso')
    if not _es_curso_secundaria(db, curso_id):
        return JSONResponse(
            {'error': 'Este endpoint es solo para cursos de secundaria.'},
            status_code=400
        )
    
    estudiantes = tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(
        curso_id=curso_id, activo=True
    ).order_by(Estudiante.apellido, Estudiante.nombre).all()
    if not estudiantes:
        return JSONResponse({'error': 'No hay estudiantes en este curso'}, status_code=404)
    
    config = tenant_filter(db.query(ConfiguracionColegio), ConfiguracionColegio, current_user).first()
    ano = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    if not ano:
        # v2.13.19: año cerrado tras promover → usar el más reciente
        ano = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).order_by(AnoEscolar.id.desc()).first()
    if not ano:
        return JSONResponse({'error': 'No hay año escolar configurado'}, status_code=404)
    
    # Combinar PDFs por estudiante en uno solo
    # v2.13.9: try/except por estudiante para que UN error no rompa todo el curso
    from pypdf import PdfWriter, PdfReader
    combined = PdfWriter()
    errores_individuales = []
    estudiantes_incluidos = 0
    
    # v2.13.18: docente titular del curso (mismo para todos los boletines del curso)
    docente_nombre = ''
    try:
        asig_titular = tenant_filter(db.query(AsignacionProfesor), AsignacionProfesor, current_user).filter_by(
            curso_id=curso_id, activo=True, es_titular=True
        ).first()
        if not asig_titular:
            asig_titular = tenant_filter(db.query(AsignacionProfesor), AsignacionProfesor, current_user).filter_by(
                curso_id=curso_id, activo=True
            ).first()
        if asig_titular:
            prof = db.get(Usuario, asig_titular.profesor_id)
            if prof:
                docente_nombre = f"{getattr(prof, 'nombre', '')} {getattr(prof, 'apellido', '')}".strip()
    except Exception as e:
        logger.warning(f"No se pudo obtener docente titular del curso {curso_id}: {e}")
    
    for est in estudiantes:
        try:
            califs = _construir_datos_boletin_secundaria(db, est, curso, current_user, ano)
            asist = _construir_asistencias_boletin(db, est.id, current_user, ano)
            if not califs:
                continue  # skip si no tiene notas cargadas
            # Situación
            aprobadas = sum(1 for d in califs.values() 
                           if (d.get('cf') or 0) >= 70 or 
                              (d.get('evaluacion_extra') and (getattr(d['evaluacion_extra'], 'nota_final', None) or 0) >= 70))
            reprobadas = len(califs) - aprobadas
            situacion = {
                'promovido': reprobadas == 0,
                'repitente': reprobadas > 2,
                'condicion': 'APROBADO/A — Promovido' if reprobadas == 0 else 'PENDIENTE/REPITENTE',
            }
            buf = generar_boletin_secundaria_minerd(
                estudiante=est, curso=curso,
                calificaciones_por_asig=califs,
                asistencias_por_periodo=asist,
                config=config, ano_escolar=ano,
                situacion_final=situacion,
                docente_nombre=docente_nombre,
            )
            rdr = PdfReader(buf)
            for page in rdr.pages:
                combined.add_page(page)
            estudiantes_incluidos += 1
        except Exception as e:
            logger.warning(f"Error generando boletín para estudiante {est.id} ({est.nombre_completo}): {e}")
            errores_individuales.append(f"{est.nombre_completo}: {type(e).__name__}")
    
    if estudiantes_incluidos == 0:
        # No se pudo generar ningún boletín
        if errores_individuales:
            return JSONResponse({
                'error': f'No se pudo generar ningún boletín. {len(errores_individuales)} estudiantes con error. Primero: {errores_individuales[0]}'
            }, status_code=500)
        else:
            return JSONResponse({
                'error': 'Ningún estudiante del curso tiene calificaciones completas para generar boletín.'
            }, status_code=400)
    
    out = io.BytesIO()
    combined.write(out)
    out.seek(0)
    
    nombre_curso = (curso.nombre or 'Curso').replace(' ', '_')
    headers_resp = {'Content-Disposition': f'attachment; filename="Boletines_MINERD_{nombre_curso}.pdf"'}
    if errores_individuales:
        # Header informativo (visible en Network tab del navegador) — algunos pudieron generarse
        headers_resp['X-Errores'] = f'{len(errores_individuales)} estudiantes con error'
    return StreamingResponse(
        out,
        media_type='application/pdf',
        headers=headers_resp
    )


@app.get("/api/asistencia/resumen-periodos/curso/{curso_id}")
async def get_resumen_asistencia_por_periodos(
    curso_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """Resumen de asistencia agrupado por períodos P1-P4 del año activo.
    
    Usado por la tab "Asistencia" en /academico.
    
    v2.13.5 (Opción 4 — alineado con Registro Escolar MINERD):
    Cuando el AnoEscolar tiene `dias_trabajados` configurados por mes (dict
    de la forma {'ago': 8, 'sep': 22, ...}), el % se calcula así:
    
        % = presentes / dias_trabajados_del_mes × 100
    
    Esto es lo que MINERD oficialmente usa: la dirección define cuántos
    días hábiles tuvo el colegio en cada mes (descontando feriados, días
    de planificación, etc.), y el % refleja qué fracción de esos días
    asistió el estudiante.
    
    Si dias_trabajados NO está configurado, fallback al cálculo anterior
    (presentes / días_con_registro × 100), con bandera `_sin_dias_trabajados`
    para que el frontend muestre aviso.
    """
    curso = get_tenant_or_404(db, Curso, curso_id, current_user, name='curso')
    ano = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    if not ano:
        return JSONResponse({'error': 'No hay año escolar activo'}, status_code=404)
    
    estudiantes = tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(
        curso_id=curso.id, activo=True
    ).order_by(Estudiante.apellido, Estudiante.nombre).all()
    
    # Mes a calcular para % mensual (default: mes actual)
    try:
        mes_param = int(request.query_params.get('mes', today_rd().month))
        ano_param = int(request.query_params.get('ano', today_rd().year))
    except (ValueError, TypeError):
        mes_param = today_rd().month
        ano_param = today_rd().year
    if not (1 <= mes_param <= 12):
        mes_param = today_rd().month
    
    # v2.13.5: leer dias_trabajados del año (Registro MINERD)
    dias_trabajados_dict = ano.get_dias_trabajados() if hasattr(ano, 'get_dias_trabajados') else {}
    # Mapear número de mes → clave en dias_trabajados (que usa abreviaciones español)
    nombres_meses_corto = ['', 'ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
    mes_key = nombres_meses_corto[mes_param] if 1 <= mes_param <= 12 else None
    
    dias_trabajados_mes = None
    try:
        if mes_key and mes_key in dias_trabajados_dict:
            dias_trabajados_mes = int(dias_trabajados_dict[mes_key])
    except (ValueError, TypeError):
        dias_trabajados_mes = None
    
    usa_dias_trabajados = dias_trabajados_mes is not None and dias_trabajados_mes > 0
    
    # Pre-fetch asistencias del mes para TODOS los estudiantes (sin N+1)
    from sqlalchemy import extract as _extract
    est_ids = [e.id for e in estudiantes]
    asists_mes_todas = []
    if est_ids:
        asists_mes_todas = tenant_filter(db.query(Asistencia), Asistencia, current_user).filter(
            Asistencia.estudiante_id.in_(est_ids),
            _extract('month', Asistencia.fecha) == mes_param,
            _extract('year', Asistencia.fecha) == ano_param
        ).all()
    
    asists_por_est = {}
    for a in asists_mes_todas:
        asists_por_est.setdefault(a.estudiante_id, []).append(a)
    
    resultado = []
    for est in estudiantes:
        # Desglose P1-P4 (anual, para el boletín)
        periodos = _construir_asistencias_boletin(db, est.id, current_user, ano)
        total_a = sum((periodos.get(f'p{p}') or {}).get('asistencia', 0) or 0 for p in range(1, 5))
        total_au = sum((periodos.get(f'p{p}') or {}).get('ausencia', 0) or 0 for p in range(1, 5))
        total = total_a + total_au
        
        # Cálculo MENSUAL del estudiante
        # v2.13.5: bug fix — antes el default 'ausente' tenía la misma prioridad
        # que un 'ausente' real, así que NUNCA se asignaba ausencia. Por eso veías
        # "100%" en muchos estudiantes aunque tuvieran ausencias.
        # Ahora: si un día tiene MÚLTIPLES registros, gana el de prioridad mayor;
        # si solo tiene UNO, ese gana. Sin defaults artificiales.
        mis_asists_mes = asists_por_est.get(est.id, [])
        prioridad = {'presente': 4, 'tardanza': 3, 'excusa': 2, 'ausente': 1}
        por_dia = {}
        for a in mis_asists_mes:
            key = a.fecha.isoformat() if a.fecha else ''
            if not key:
                continue
            estado_nuevo = a.estado
            estado_actual = por_dia.get(key)  # None si nunca se asignó
            if estado_actual is None:
                # Primera vez que veo este día: asignar
                por_dia[key] = estado_nuevo
            elif prioridad.get(estado_nuevo, 0) > prioridad.get(estado_actual, 0):
                # Ya había un estado para este día, pero el nuevo tiene mayor prioridad
                por_dia[key] = estado_nuevo
        n_pres_mes = sum(1 for e in por_dia.values() if e == 'presente')
        n_aus_mes = sum(1 for e in por_dia.values() if e == 'ausente')
        n_tard_mes = sum(1 for e in por_dia.values() if e == 'tardanza')
        
        # v2.13.5 Opción 4: si hay dias_trabajados configurados, usar como denominador
        if usa_dias_trabajados:
            # % = presentes / dias_trabajados_del_mes
            pct_mes = round(n_pres_mes / dias_trabajados_mes * 100, 0)
            # Cap a 100 por si el profesor cargó más días que los dias_trabajados configurados
            pct_mes = min(pct_mes, 100)
            denominador_mes = dias_trabajados_mes
        else:
            # Fallback: cálculo viejo (presentes / días con registro)
            total_con_registro = n_pres_mes + n_aus_mes
            pct_mes = round(n_pres_mes / total_con_registro * 100, 0) if total_con_registro > 0 else None
            denominador_mes = total_con_registro
        
        resultado.append({
            'estudiante_id': est.id,
            'estudiante': est.nombre_completo,
            'periodos': periodos,
            'total_asistencia': total_a,
            'total_ausencia': total_au,
            'pct_asistencia_anual': round((total_a / total * 100), 0) if total > 0 else None,
            'mes': mes_param,
            'ano_calendario': ano_param,
            'asistencia_mes': n_pres_mes,
            'ausencia_mes': n_aus_mes,
            'tardanza_mes': n_tard_mes,
            'pct_asistencia_mes': pct_mes,
            # v2.13.5: campos nuevos para transparencia frontend
            'dias_trabajados_mes': dias_trabajados_mes,
            'denominador_mes': denominador_mes,
            '_usa_dias_trabajados': usa_dias_trabajados,
        })
    
    return resultado


# ============== NOTIFICACIONES ==============

@app.get("/api/notificaciones")
async def get_notificaciones(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Obtener notificaciones del usuario actual"""
    limit = int(request.query_params.get('limit', 20))
    notifs = tenant_filter(db.query(Notificacion), Notificacion, current_user).filter_by(
        usuario_id=current_user.id
    ).order_by(Notificacion.fecha.desc()).limit(limit).all()
    no_leidas = tenant_filter(db.query(Notificacion), Notificacion, current_user).filter_by(
        usuario_id=current_user.id, leida=False
    ).count()
    return {'notificaciones': [n.to_dict() for n in notifs], 'no_leidas': no_leidas}

@app.put("/api/notificaciones/{id}/leer")
async def marcar_notificacion_leida(id, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    notif = db.get(Notificacion, id)
    if notif and notif.usuario_id == current_user.id:
        notif.leida = True
        db.commit()
    return {'message': 'OK'}

@app.put("/api/notificaciones/leer-todas")
async def marcar_todas_leidas(db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    tenant_filter(db.query(Notificacion), Notificacion, current_user).filter_by(
        usuario_id=current_user.id, leida=False
    ).update({'leida': True})
    db.commit()
    return {'message': 'Todas marcadas como leídas'}

# ============== REPORTE DE PROGRESO ==============

@app.get("/api/estudiantes/{id}/progreso")
async def get_progreso_estudiante(id, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Reporte de progreso: cómo han evolucionado las notas del estudiante a lo largo de los períodos.
    
    v2.13.8: lee AMBOS modelos. Para CalificacionSecundaria (modelo nuevo MINERD),
    calcula la nota del período como AVG de las 4 competencias usando valor_periodo.
    """
    estudiante = get_tenant_or_404(db, Estudiante, id, current_user, name='estudiante')
    
    # ─── Modelo NUEVO: CalificacionSecundaria ───
    # nota_por_asig_periodo: dict (asig_id, periodo) → nota
    nota_por_asig_periodo: dict = {}
    nombre_por_asig: dict = {}
    
    ano_activo = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    if ano_activo:
        califs_sec = tenant_filter(
            db.query(CalificacionSecundaria), CalificacionSecundaria, current_user
        ).filter_by(estudiante_id=id, ano_escolar_id=ano_activo.id).all()
        
        from collections import defaultdict as _dd
        por_asig = _dd(list)
        for c in califs_sec:
            por_asig[c.asignatura_id].append(c)
        
        for aid, comps in por_asig.items():
            asig_obj = db.get(Asignatura, aid)
            nombre_por_asig[aid] = asig_obj.nombre if asig_obj else ''
            for p in range(1, 5):
                vals = []
                for comp in comps:
                    v = comp.valor_periodo(p) if hasattr(comp, 'valor_periodo') else None
                    if v is not None:
                        vals.append(v)
                if vals:
                    nota_por_asig_periodo[(aid, p)] = round(sum(vals) / len(vals), 1)
    
    # ─── Modelo LEGACY: Calificacion ───
    # Solo agregamos asignaturas que NO están ya en el modelo nuevo
    asig_ids_modelo_nuevo = set(nombre_por_asig.keys())
    calificaciones_legacy = tenant_filter(db.query(Calificacion), Calificacion, current_user).filter_by(estudiante_id=id).all()
    for cal in calificaciones_legacy:
        if cal.asignatura_id in asig_ids_modelo_nuevo:
            continue
        nombre_por_asig[cal.asignatura_id] = cal.asignatura.nombre if cal.asignatura else ''
        for p in range(1, 5):
            pc = getattr(cal, f'pc{p}', None)
            if pc is not None:
                nota_por_asig_periodo[(cal.asignatura_id, p)] = round(float(pc), 1)
    
    # Construir datos por período (unificado)
    periodos = []
    for p in range(1, 5):
        asig_notas = []
        for aid, nombre in nombre_por_asig.items():
            nota = nota_por_asig_periodo.get((aid, p))
            if nota is not None:
                asig_notas.append({'asignatura': nombre, 'nota': nota})
        
        promedio = round(sum(n['nota'] for n in asig_notas) / len(asig_notas), 1) if asig_notas else None
        periodos.append({
            'periodo': p,
            'promedio': promedio,
            'asignaturas': asig_notas,
            'aprobadas': sum(1 for n in asig_notas if n['nota'] >= 70),
            'reprobadas': sum(1 for n in asig_notas if n['nota'] < 70),
            'total': len(asig_notas)
        })
    
    # Tendencia: comparar cada período con el anterior
    tendencia = 'estable'
    promedios_validos = [p['promedio'] for p in periodos if p['promedio'] is not None]
    if len(promedios_validos) >= 2:
        if promedios_validos[-1] > promedios_validos[-2]:
            tendencia = 'subiendo'
        elif promedios_validos[-1] < promedios_validos[-2]:
            tendencia = 'bajando'
    
    # Mejor y peor asignatura (del último período con datos)
    ultimo_periodo = None
    for p in reversed(periodos):
        if p['asignaturas']:
            ultimo_periodo = p
            break
    
    mejor_asig = None
    peor_asig = None
    if ultimo_periodo and ultimo_periodo['asignaturas']:
        sorted_asig = sorted(ultimo_periodo['asignaturas'], key=lambda x: x['nota'], reverse=True)
        mejor_asig = sorted_asig[0]
        peor_asig = sorted_asig[-1]
    
    return {
        'estudiante': {
            'id': estudiante.id,
            'nombre': estudiante.nombre_completo,
            'matricula': estudiante.matricula,
            'curso': estudiante.curso.nombre_completo if estudiante.curso else None,
        },
        'periodos': periodos,
        'tendencia': tendencia,
        'mejor_asignatura': mejor_asig,
        'peor_asignatura': peor_asig,
        'promedio_general': round(sum(promedios_validos) / len(promedios_validos), 1) if promedios_validos else None
    }

@app.get("/api/estudiantes/{id}/historial")
async def get_historial_estudiante(id, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Historial completo del estudiante: académico, conducta, asistencia, psicología"""
    estudiante = get_tenant_or_404(db, Estudiante, id, current_user, name='estudiante')
    
    # === DATOS PERSONALES ===
    datos_personales = {
        'id': estudiante.id,
        'nombre': estudiante.nombre_completo,
        'nombre_padre': getattr(estudiante, 'nombre_padre', None),
        'telefono_padre': getattr(estudiante, 'telefono_padre', None),
        'nombre_madre': getattr(estudiante, 'nombre_madre', None),
        'telefono_madre': getattr(estudiante, 'telefono_madre', None),
        'matricula': estudiante.matricula,
        'sexo': estudiante.sexo,
        'fecha_nacimiento': estudiante.fecha_nacimiento.isoformat() if estudiante.fecha_nacimiento else None,
        'curso': estudiante.curso.nombre_completo if estudiante.curso else None,
        'grado': estudiante.curso.grado.nombre if estudiante.curso and estudiante.curso.grado else None,
        'condicion': getattr(estudiante, 'condicion_entrada', None) or getattr(estudiante, 'condicion', 'activo'),
        'direccion': getattr(estudiante, 'direccion', None),
        'telefono': getattr(estudiante, 'telefono', None),
        'contacto_emergencia': getattr(estudiante, 'contacto_emergencia', None),
        'telefono_emergencia': getattr(estudiante, 'telefono_emergencia', None),
        'nee': getattr(estudiante, 'nee', None),
    }
    
    # === HISTORIAL ACADÉMICO ===
    # v2.13.8: lee AMBOS modelos (Calificacion legacy + CalificacionSecundaria nuevo MINERD)
    academico = []
    asig_ids_modelo_nuevo = set()
    
    # 1. Modelo NUEVO: CalificacionSecundaria
    ano_activo = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    if ano_activo:
        califs_sec = tenant_filter(
            db.query(CalificacionSecundaria), CalificacionSecundaria, current_user
        ).filter_by(estudiante_id=id, ano_escolar_id=ano_activo.id).all()
        
        from collections import defaultdict as _dd
        por_asig = _dd(list)
        for c in califs_sec:
            por_asig[c.asignatura_id].append(c)
        
        for aid, comps in por_asig.items():
            asig_obj = db.get(Asignatura, aid)
            pcs = {}  # pc1..pc4
            rps = {}  # rp1..rp4 (mínima por período)
            for p in range(1, 5):
                vals = []
                rps_periodo = []
                for comp in comps:
                    v = comp.valor_periodo(p) if hasattr(comp, 'valor_periodo') else None
                    if v is not None:
                        vals.append(v)
                    rp_val = getattr(comp, f'rp{p}', None)
                    if rp_val is not None:
                        rps_periodo.append(rp_val)
                pcs[f'pc{p}'] = round(sum(vals) / len(vals), 1) if vals else None
                rps[f'rp{p}'] = min(rps_periodo) if rps_periodo else None
            
            pcs_validos = [v for v in pcs.values() if v is not None]
            cf = int(round(sum(pcs_validos) / len(pcs_validos))) if pcs_validos else None
            
            def _literal(n):
                if n is None: return ''
                if n >= 90: return 'A'
                if n >= 80: return 'B'
                if n >= 70: return 'C'
                return 'F'
            
            academico.append({
                'asignatura': asig_obj.nombre if asig_obj else '',
                'pc1': pcs['pc1'], 'pc2': pcs['pc2'], 'pc3': pcs['pc3'], 'pc4': pcs['pc4'],
                'rp1': rps['rp1'], 'rp2': rps['rp2'], 'rp3': rps['rp3'], 'rp4': rps['rp4'],
                'cf': cf, 'literal': _literal(cf)
            })
            asig_ids_modelo_nuevo.add(aid)
    
    # 2. Modelo LEGACY: agregar asignaturas que NO están ya en modelo nuevo
    calificaciones = tenant_filter(db.query(Calificacion), Calificacion, current_user).filter_by(estudiante_id=id).all()
    for cal in calificaciones:
        if cal.asignatura_id in asig_ids_modelo_nuevo:
            continue
        academico.append({
            'asignatura': cal.asignatura.nombre if cal.asignatura else '',
            'pc1': cal.pc1, 'pc2': cal.pc2, 'pc3': cal.pc3, 'pc4': cal.pc4,
            'rp1': cal.rp1, 'rp2': cal.rp2, 'rp3': cal.rp3, 'rp4': cal.rp4,
            'cf': cal.cf, 'literal': cal.literal or cal.get_literal()
        })
    
    # === HISTORIAL DE CONDUCTA ===
    reportes = tenant_filter(db.query(ReporteConducta), ReporteConducta, current_user).filter_by(
        estudiante_id=id
    ).order_by(ReporteConducta.fecha.desc()).all()
    conducta = [{
        'id': r.id,
        'fecha': r.fecha.strftime('%d/%m/%Y %H:%M') if r.fecha else '',
        'tipo': r.tipo,
        'descripcion': r.descripcion,
        'estado': r.estado,
        'gravedad': getattr(r, 'gravedad', None),
        'reportado_por': r.reportado.nombre_completo if r.reportado else '',
        'respuesta': getattr(r, 'respuesta', None),
    } for r in reportes]
    
    # === HISTORIAL DE ASISTENCIA ===
    asistencias = tenant_filter(db.query(Asistencia), Asistencia, current_user).filter_by(estudiante_id=id).all()
    presentes = sum(1 for a in asistencias if a.estado == 'presente')
    ausentes = sum(1 for a in asistencias if a.estado == 'ausente')
    tardanzas = sum(1 for a in asistencias if a.estado == 'tardanza')
    excusas = sum(1 for a in asistencias if a.estado == 'excusa')
    total = len(asistencias)
    
    # Asistencia por mes
    from collections import defaultdict
    asist_por_mes = defaultdict(lambda: {'presentes': 0, 'ausentes': 0, 'tardanzas': 0, 'total': 0})
    for a in asistencias:
        if a.fecha:
            mes_key = a.fecha.strftime('%Y-%m')
            mes_nombre = a.fecha.strftime('%b %Y')
            asist_por_mes[mes_key]['nombre'] = mes_nombre
            asist_por_mes[mes_key]['total'] += 1
            if a.estado == 'presente': asist_por_mes[mes_key]['presentes'] += 1
            elif a.estado == 'ausente': asist_por_mes[mes_key]['ausentes'] += 1
            elif a.estado == 'tardanza': asist_por_mes[mes_key]['tardanzas'] += 1
    
    asistencia = {
        'presentes': presentes,
        'ausentes': ausentes,
        'tardanzas': tardanzas,
        'excusas': excusas,
        'total': total,
        'porcentaje': round(presentes / total * 100, 1) if total > 0 else 0,
        'por_mes': sorted([
            {'mes': v['nombre'], 'presentes': v['presentes'], 'ausentes': v['ausentes'], 'tardanzas': v['tardanzas']}
            for k, v in asist_por_mes.items()
        ], key=lambda x: x['mes'])
    }
    
    # === HISTORIAL DE PSICOLOGÍA ===
    casos = tenant_filter(db.query(CasoPsicologia), CasoPsicologia, current_user).filter_by(
        estudiante_id=id
    ).order_by(CasoPsicologia.fecha_inicio.desc() if hasattr(CasoPsicologia, 'fecha_inicio') else CasoPsicologia.id.desc()).all()
    psicologia = [{
        'id': c.id,
        'motivo': getattr(c, 'motivo', ''),
        'estado': c.estado,
        'urgencia': getattr(c, 'urgencia', ''),
        'fecha': c.fecha_inicio.strftime('%d/%m/%Y') if hasattr(c, 'fecha_inicio') and c.fecha_inicio else '',
        'observaciones': getattr(c, 'observaciones', ''),
        'recomendacion_profesor': getattr(c, 'recomendacion_profesor', ''),
    } for c in casos]
    
    return {
        'datos_personales': datos_personales,
        'academico': academico,
        'conducta': conducta,
        'conducta_resumen': {
            'total': len(conducta),
            'pendientes': sum(1 for r in conducta if r['estado'] == 'pendiente'),
            'resueltos': sum(1 for r in conducta if r['estado'] != 'pendiente'),
            'graves': sum(1 for r in conducta if r.get('gravedad') == 'grave'),
        },
        'asistencia': asistencia,
        'psicologia': psicologia,
        'psicologia_resumen': {
            'total': len(psicologia),
            'activos': sum(1 for c in psicologia if c['estado'] != 'atendido'),
            'atendidos': sum(1 for c in psicologia if c['estado'] == 'atendido'),
        }
    }

@app.get("/api/estudiantes/{id}/historial")
async def get_historial_estudiante(id, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Historial completo de un estudiante: datos, académico, conducta, asistencia, psicología"""
    estudiante = get_tenant_or_404(db, Estudiante, id, current_user, name='estudiante')
    
    # Datos personales
    datos = {
        'nombre': estudiante.nombre_completo,
        'matricula': estudiante.matricula,
        'cedula': estudiante.cedula,
        'sexo': estudiante.sexo,
        'fecha_nacimiento': estudiante.fecha_nacimiento.isoformat() if estudiante.fecha_nacimiento else None,
        'curso': estudiante.curso.nombre_completo if estudiante.curso else None,
        'condicion': estudiante.condicion,
        'fecha_ingreso': estudiante.fecha_ingreso.isoformat() if estudiante.fecha_ingreso else None,
        'direccion': estudiante.direccion,
        'telefono': estudiante.telefono,
        'nombre_padre': estudiante.nombre_padre,
        'telefono_padre': estudiante.telefono_padre,
        'nombre_madre': estudiante.nombre_madre,
        'telefono_madre': estudiante.telefono_madre,
        'tutor': estudiante.tutor,
        'telefono_tutor': estudiante.telefono_tutor,
        'contacto_emergencia': estudiante.contacto_emergencia,
        'telefono_emergencia': estudiante.telefono_emergencia,
    }
    
    # Historial académico - todas las calificaciones
    # v2.13.8: lee AMBOS modelos (Calificacion legacy + CalificacionSecundaria nuevo MINERD)
    academico = []
    asig_ids_modelo_nuevo = set()
    
    ano_activo_h = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    if ano_activo_h:
        califs_sec = tenant_filter(
            db.query(CalificacionSecundaria), CalificacionSecundaria, current_user
        ).filter_by(estudiante_id=id, ano_escolar_id=ano_activo_h.id).all()
        
        from collections import defaultdict as _dd
        por_asig = _dd(list)
        for c in califs_sec:
            por_asig[c.asignatura_id].append(c)
        
        for aid, comps in por_asig.items():
            asig_obj = db.get(Asignatura, aid)
            pcs = {}
            rps = {}
            for p in range(1, 5):
                vals = []
                rps_periodo = []
                for comp in comps:
                    v = comp.valor_periodo(p) if hasattr(comp, 'valor_periodo') else None
                    if v is not None:
                        vals.append(v)
                    rp_val = getattr(comp, f'rp{p}', None)
                    if rp_val is not None:
                        rps_periodo.append(rp_val)
                pcs[f'pc{p}'] = round(sum(vals) / len(vals), 1) if vals else None
                rps[f'rp{p}'] = min(rps_periodo) if rps_periodo else None
            
            pcs_validos = [v for v in pcs.values() if v is not None]
            cf = int(round(sum(pcs_validos) / len(pcs_validos))) if pcs_validos else None
            
            def _literal(n):
                if n is None: return ''
                if n >= 90: return 'A'
                if n >= 80: return 'B'
                if n >= 70: return 'C'
                return 'F'
            
            academico.append({
                'asignatura': asig_obj.nombre if asig_obj else '',
                'pc1': pcs['pc1'], 'rp1': rps['rp1'],
                'pc2': pcs['pc2'], 'rp2': rps['rp2'],
                'pc3': pcs['pc3'], 'rp3': rps['rp3'],
                'pc4': pcs['pc4'], 'rp4': rps['rp4'],
                'cf': cf, 'literal': _literal(cf)
            })
            asig_ids_modelo_nuevo.add(aid)
    
    calificaciones = tenant_filter(db.query(Calificacion), Calificacion, current_user).filter_by(estudiante_id=id).all()
    for cal in calificaciones:
        if cal.asignatura_id in asig_ids_modelo_nuevo:
            continue
        academico.append({
            'asignatura': cal.asignatura.nombre if cal.asignatura else '',
            'pc1': cal.pc1, 'rp1': cal.rp1,
            'pc2': cal.pc2, 'rp2': cal.rp2,
            'pc3': cal.pc3, 'rp3': cal.rp3,
            'pc4': cal.pc4, 'rp4': cal.rp4,
            'cf': cal.cf, 'literal': cal.literal or cal.get_literal()
        })
    
    # Historial conducta - todos los reportes
    reportes = tenant_filter(db.query(ReporteConducta), ReporteConducta, current_user).filter_by(
        estudiante_id=id
    ).order_by(ReporteConducta.fecha.desc()).all()
    conducta = [{
        'id': r.id,
        'fecha': r.fecha.strftime('%d/%m/%Y %H:%M') if r.fecha else '',
        'tipo': r.tipo,
        'gravedad': r.gravedad,
        'titulo': r.titulo,
        'descripcion': r.descripcion[:100] if r.descripcion else '',
        'estado': r.estado,
        'respuesta': r.respuesta[:100] if r.respuesta else None,
        'reportado_por': r.reportador.nombre_completo if r.reportador else '',
    } for r in reportes]
    
    # Historial asistencia - resumen
    asistencias = tenant_filter(db.query(Asistencia), Asistencia, current_user).filter_by(estudiante_id=id).all()
    asist_conteo = {'presente': 0, 'ausente': 0, 'tardanza': 0, 'excusa': 0}
    meses = {}
    for a in asistencias:
        estado = a.estado or 'presente'
        asist_conteo[estado] = asist_conteo.get(estado, 0) + 1
        if a.fecha:
            mes_key = a.fecha.strftime('%Y-%m')
            if mes_key not in meses:
                meses[mes_key] = {'mes': a.fecha.strftime('%b %Y'), 'presente': 0, 'ausente': 0, 'tardanza': 0}
            if estado in meses[mes_key]:
                meses[mes_key][estado] += 1
    
    total_asist = sum(asist_conteo.values())
    asistencia = {
        'presentes': asist_conteo['presente'],
        'ausentes': asist_conteo['ausente'],
        'tardanzas': asist_conteo['tardanza'],
        'excusas': asist_conteo['excusa'],
        'total': total_asist,
        'porcentaje': round(asist_conteo['presente'] / total_asist * 100, 1) if total_asist > 0 else 0,
        'por_mes': sorted(meses.values(), key=lambda x: x['mes'])
    }
    
    # Historial psicología
    casos = tenant_filter(db.query(CasoPsicologia), CasoPsicologia, current_user).filter_by(
        estudiante_id=id
    ).order_by(CasoPsicologia.fecha_solicitud.desc()).all()
    psicologia = [{
        'id': c.id,
        'fecha': c.fecha_solicitud.strftime('%d/%m/%Y') if c.fecha_solicitud else '',
        'tipo': c.tipo,
        'urgencia': c.urgencia,
        'motivo': c.motivo[:100] if c.motivo else '',
        'estado': c.estado,
        'diagnostico': c.diagnostico[:100] if c.diagnostico else None,
        'recomendacion': c.recomendacion_profesor[:100] if c.recomendacion_profesor else None,
    } for c in casos]
    
    return {
        'datos': datos,
        'academico': academico,
        'conducta': conducta,
        'conducta_resumen': {
            'total': len(conducta),
            'pendientes': sum(1 for r in conducta if r['estado'] == 'pendiente'),
            'resueltos': sum(1 for r in conducta if r['estado'] == 'resuelto'),
            'graves': sum(1 for r in conducta if r['gravedad'] == 'grave'),
        },
        'asistencia': asistencia,
        'psicologia': psicologia,
        'psicologia_resumen': {
            'total': len(psicologia),
            'activos': sum(1 for c in psicologia if c['estado'] in ('pendiente', 'en_proceso')),
        }
    }

# ============== REPORTE DE NOTAS POR PERÍODO ==============

@app.get("/api/reportes/notas/estudiante/{estudiante_id}/periodo/{periodo}")
async def get_reporte_notas_periodo(estudiante_id, periodo, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Obtener reporte de notas de un estudiante para un período específico"""
    periodo = int(periodo)
    if periodo < 1 or periodo > 4:
        return JSONResponse({'error': 'Período inválido'}, status_code=400)
    
    estudiante = get_tenant_or_404(db, Estudiante, estudiante_id, current_user, name='estudiante')
    config = tenant_filter(db.query(ConfiguracionColegio), ConfiguracionColegio, current_user).first()
    ano_escolar = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    
    # v2.13.8: lee AMBOS modelos
    asignaturas_data = []
    asig_ids_modelo_nuevo = set()
    
    # 1. Modelo NUEVO: CalificacionSecundaria
    if ano_escolar:
        califs_sec = tenant_filter(
            db.query(CalificacionSecundaria), CalificacionSecundaria, current_user
        ).filter_by(estudiante_id=estudiante_id, ano_escolar_id=ano_escolar.id).all()
        
        from collections import defaultdict as _dd
        por_asig = _dd(list)
        for c in califs_sec:
            por_asig[c.asignatura_id].append(c)
        
        for aid, comps in por_asig.items():
            asig_obj = db.get(Asignatura, aid)
            # PC del período = AVG de las 4 competencias
            vals = []
            rps_periodo = []
            for comp in comps:
                v = comp.valor_periodo(periodo) if hasattr(comp, 'valor_periodo') else None
                if v is not None:
                    vals.append(v)
                rp_val = getattr(comp, f'rp{periodo}', None)
                if rp_val is not None:
                    rps_periodo.append(rp_val)
            pc = round(sum(vals) / len(vals), 1) if vals else None
            rp = min(rps_periodo) if rps_periodo else None
            
            # En modelo nuevo no hay parciales p1..p4; usar las notas de las 4 competencias
            # como "parciales" para mostrar (cada competencia es como un parcial)
            comps_ordenadas = sorted(comps, key=lambda c: c.competencia_numero)
            campo_p = f'p{periodo}'
            p_vals = [getattr(c, campo_p, None) for c in comps_ordenadas[:4]]
            while len(p_vals) < 4:
                p_vals.append(None)
            
            nota_final = max(pc or 0, rp or 0) if (pc is not None and pc < 70 and rp is not None) else pc
            
            def _literal(n):
                if n is None: return None
                if n >= 90: return 'A'
                if n >= 80: return 'B'
                if n >= 70: return 'C'
                return 'F'
            
            asignaturas_data.append({
                'asignatura': asig_obj.nombre if asig_obj else 'Sin asignatura',
                'p1': p_vals[0], 'p2': p_vals[1], 'p3': p_vals[2], 'p4': p_vals[3],
                'pc': pc,
                'rp': rp,
                'nota_final': nota_final,
                'literal': _literal(nota_final),
                'estado': 'Aprobado' if nota_final and nota_final >= 70 else 'Reprobado' if nota_final else 'Pendiente'
            })
            asig_ids_modelo_nuevo.add(aid)
    
    # 2. Modelo LEGACY: solo asignaturas que NO están ya en modelo nuevo
    calificaciones = tenant_filter(db.query(Calificacion), Calificacion, current_user).filter_by(estudiante_id=estudiante_id).all()
    for calif in calificaciones:
        if calif.asignatura_id in asig_ids_modelo_nuevo:
            continue
        p1 = getattr(calif, f'p{periodo}_p1')
        p2 = getattr(calif, f'p{periodo}_p2')
        p3 = getattr(calif, f'p{periodo}_p3')
        p4 = getattr(calif, f'p{periodo}_p4')
        pc = getattr(calif, f'pc{periodo}')
        rp = getattr(calif, f'rp{periodo}')
        
        nota_final = rp if (pc is not None and pc < 70 and rp is not None) else pc
        literal = calif.get_literal(nota_final) if nota_final else None
        
        asignaturas_data.append({
            'asignatura': calif.asignatura.nombre if calif.asignatura else 'Sin asignatura',
            'p1': p1, 'p2': p2, 'p3': p3, 'p4': p4,
            'pc': pc,
            'rp': rp,
            'nota_final': nota_final,
            'literal': literal,
            'estado': 'Aprobado' if nota_final and nota_final >= 70 else 'Reprobado' if nota_final else 'Pendiente'
        })
    
    # Asistencia del período
    # (simplificado - en producción filtrar por fechas del período)
    asistencias = tenant_filter(db.query(Asistencia), Asistencia, current_user).filter_by(estudiante_id=estudiante_id).all()
    presentes = sum(1 for a in asistencias if a.estado == 'presente')
    total = len(asistencias)
    
    return {
        'colegio': {
            'nombre': config.nombre if config else 'Educa One',
            'logo': config.logo if config else None,
            'direccion': config.direccion if config else None,
            'telefono': config.telefono if config else None,
            'distrito': config.distrito if config else None
        },
        'ano_escolar': ano_escolar.nombre if ano_escolar else None,
        'periodo': periodo,
        'estudiante': {
            'id': estudiante.id,
            'nombre': estudiante.nombre_completo,
            'matricula': estudiante.matricula,
            'curso': estudiante.curso.nombre_completo if estudiante.curso else None,
            'grado': estudiante.curso.grado.nombre if estudiante.curso and estudiante.curso.grado else None
        },
        'asignaturas': asignaturas_data,
        'asistencia': {
            'presentes': presentes,
            'ausentes': total - presentes,
            'total': total,
            'porcentaje': round(presentes / total * 100, 1) if total > 0 else 0
        },
        'promedio_periodo': round(sum(a['nota_final'] for a in asignaturas_data if a['nota_final']) / max(len([a for a in asignaturas_data if a['nota_final']]), 1), 1) if any(a['nota_final'] for a in asignaturas_data) else 0,
        'fecha_generacion': now_rd().isoformat()
    }

@app.get("/api/reportes/notas/curso/{curso_id}/periodo/{periodo}")
async def get_reporte_notas_curso(curso_id, periodo, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion', 'coordinador'))):
    """Obtener resumen de notas de un curso para un período"""
    periodo = int(periodo)
    if periodo < 1 or periodo > 4:
        return JSONResponse({'error': 'Período inválido'}, status_code=400)
    
    curso = get_tenant_or_404(db, Curso, curso_id, current_user, name='curso')
    estudiantes = tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(curso_id=curso_id, activo=True).order_by(Estudiante.no_lista).all()
    
    # v2.13.8: pre-cargar CalificacionSecundaria del curso completo (evita N+1)
    est_ids = [e.id for e in estudiantes]
    ano_activo_rc = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    
    sec_por_est_asig: dict = {}
    if ano_activo_rc and est_ids:
        califs_sec_curso = tenant_filter(
            db.query(CalificacionSecundaria), CalificacionSecundaria, current_user
        ).filter(
            CalificacionSecundaria.estudiante_id.in_(est_ids),
            CalificacionSecundaria.ano_escolar_id == ano_activo_rc.id,
        ).all()
        from collections import defaultdict as _dd
        sec_por_est_asig = _dd(list)
        for c in califs_sec_curso:
            sec_por_est_asig[(c.estudiante_id, c.asignatura_id)].append(c)
    
    resultado = []
    for est in estudiantes:
        notas_asignaturas = []
        promedio_total = 0
        count = 0
        asig_ids_modelo_nuevo = set()
        
        # 1. Modelo NUEVO
        for (eid, aid), comps in list(sec_por_est_asig.items()):
            if eid != est.id:
                continue
            asig_obj = db.get(Asignatura, aid)
            vals = []
            rps_periodo = []
            for comp in comps:
                v = comp.valor_periodo(periodo) if hasattr(comp, 'valor_periodo') else None
                if v is not None:
                    vals.append(v)
                rp_val = getattr(comp, f'rp{periodo}', None)
                if rp_val is not None:
                    rps_periodo.append(rp_val)
            pc = round(sum(vals) / len(vals), 1) if vals else None
            rp = min(rps_periodo) if rps_periodo else None
            nota_final = max(pc, rp) if (pc is not None and pc < 70 and rp is not None) else pc
            
            def _literal(n):
                if n is None: return None
                if n >= 90: return 'A'
                if n >= 80: return 'B'
                if n >= 70: return 'C'
                return 'F'
            
            if nota_final is not None:
                promedio_total += nota_final
                count += 1
            notas_asignaturas.append({
                'asignatura': asig_obj.nombre if asig_obj else None,
                'nota': nota_final,
                'literal': _literal(nota_final) if nota_final else None
            })
            asig_ids_modelo_nuevo.add(aid)
        
        # 2. Modelo LEGACY (asignaturas NO en modelo nuevo)
        calificaciones = tenant_filter(db.query(Calificacion), Calificacion, current_user).filter_by(estudiante_id=est.id).all()
        for calif in calificaciones:
            if calif.asignatura_id in asig_ids_modelo_nuevo:
                continue
            pc = getattr(calif, f'pc{periodo}')
            rp = getattr(calif, f'rp{periodo}')
            nota_final = rp if (pc is not None and pc < 70 and rp is not None) else pc
            
            if nota_final is not None:
                promedio_total += nota_final
                count += 1
            
            notas_asignaturas.append({
                'asignatura': calif.asignatura.nombre if calif.asignatura else None,
                'nota': nota_final,
                'literal': calif.get_literal(nota_final) if nota_final else None
            })
        
        promedio = round(promedio_total / count, 1) if count > 0 else None
        
        resultado.append({
            'estudiante_id': est.id,
            'no_lista': est.no_lista,
            'nombre': est.nombre_completo,
            'notas': notas_asignaturas,
            'promedio': promedio,
            'literal': Calificacion().get_literal(promedio) if promedio else None,
            'estado': 'Aprobado' if promedio and promedio >= 70 else 'Reprobado' if promedio else 'Pendiente'
        })
    
    return {
        'curso': curso.nombre_completo,
        'periodo': periodo,
        'estudiantes': resultado,
        'resumen': {
            'total': len(resultado),
            'aprobados': sum(1 for r in resultado if r['estado'] == 'Aprobado'),
            'reprobados': sum(1 for r in resultado if r['estado'] == 'Reprobado'),
            'pendientes': sum(1 for r in resultado if r['estado'] == 'Pendiente')
        }
    }

# ============== PROMOCIÓN REAL ==============

@app.get("/api/promocion/estudiantes")
async def get_estudiantes_promocion(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Obtener lista de estudiantes con su estado de promoción real.
    
    v2.13.8: lee AMBOS modelos. Para CalificacionSecundaria calcula CF como
    AVG(PC1..PC4) considerando evaluacion_extra si existe.
    """
    estudiantes = tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(activo=True).order_by(Estudiante.curso_id, Estudiante.no_lista).all()
    est_ids = [e.id for e in estudiantes]
    
    # Pre-cargar CalificacionSecundaria de todos los estudiantes
    ano_activo_prom = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    sec_por_est_asig: dict = {}
    extras_por_est_asig: dict = {}
    if ano_activo_prom and est_ids:
        califs_sec_prom = tenant_filter(
            db.query(CalificacionSecundaria), CalificacionSecundaria, current_user
        ).filter(
            CalificacionSecundaria.estudiante_id.in_(est_ids),
            CalificacionSecundaria.ano_escolar_id == ano_activo_prom.id,
        ).all()
        from collections import defaultdict as _dd
        sec_por_est_asig = _dd(list)
        for c in califs_sec_prom:
            sec_por_est_asig[(c.estudiante_id, c.asignatura_id)].append(c)
        
        # Pre-cargar evaluaciones extras
        extras = tenant_filter(
            db.query(EvaluacionExtraSecundaria), EvaluacionExtraSecundaria, current_user
        ).filter(
            EvaluacionExtraSecundaria.estudiante_id.in_(est_ids),
            EvaluacionExtraSecundaria.ano_escolar_id == ano_activo_prom.id,
        ).all()
        for e in extras:
            extras_por_est_asig[(e.estudiante_id, e.asignatura_id)] = e
    
    resultado = []
    for est in estudiantes:
        cfs = []
        asignaturas_reprobadas = []
        asig_ids_modelo_nuevo = set()
        
        # 1. Modelo NUEVO: CalificacionSecundaria
        for (eid, aid), comps in list(sec_por_est_asig.items()):
            if eid != est.id:
                continue
            # CF = AVG(PC1..PC4)
            pcs = []
            for p in range(1, 5):
                vals = []
                for c in comps:
                    v = c.valor_periodo(p) if hasattr(c, 'valor_periodo') else None
                    if v is not None:
                        vals.append(v)
                if vals:
                    pcs.append(sum(vals) / len(vals))
            if not pcs:
                continue
            cf = int(round(sum(pcs) / len(pcs)))
            
            # Evaluación extra (puede haber subido la nota tras cascada completiva/extra)
            ev = extras_por_est_asig.get((est.id, aid))
            nota_final = ev.nota_final if (ev and ev.nota_final is not None) else cf
            
            cfs.append(nota_final)
            if nota_final < 70:
                asig_obj = db.get(Asignatura, aid)
                asignaturas_reprobadas.append(asig_obj.nombre if asig_obj else 'Asignatura')
            asig_ids_modelo_nuevo.add(aid)
        
        # 2. Modelo LEGACY
        calificaciones = tenant_filter(db.query(Calificacion), Calificacion, current_user).filter_by(estudiante_id=est.id).all()
        for calif in calificaciones:
            if calif.asignatura_id in asig_ids_modelo_nuevo:
                continue
            if calif.cf is not None:
                cfs.append(calif.cf)
                if calif.cf < 70:
                    asignaturas_reprobadas.append(calif.asignatura.nombre if calif.asignatura else 'Asignatura')
        
        promedio_general = round(sum(cfs) / len(cfs), 1) if cfs else None
        todas_aprobadas = all(cf >= 70 for cf in cfs) if cfs else False
        
        # Determinar condición
        if not cfs:
            condicion = 'Sin calificaciones'
        elif todas_aprobadas:
            condicion = 'Promovido'
        elif len(asignaturas_reprobadas) <= 2:
            condicion = 'Promovido condicional'
        else:
            condicion = 'Reprobado'
        
        # Determinar nuevo grado
        grado_actual = est.curso.grado if est.curso else None
        if condicion in ['Promovido', 'Promovido condicional'] and grado_actual:
            siguiente_grado = tenant_filter(db.query(Grado), Grado, current_user).filter(Grado.orden == grado_actual.orden + 1).first()
            nuevo_grado = siguiente_grado.nombre if siguiente_grado else 'Egresado'
        else:
            nuevo_grado = grado_actual.nombre if grado_actual else None
        
        resultado.append({
            'id': est.id,
            'nombre': est.nombre_completo,
            'matricula': est.matricula,
            'curso': est.curso.nombre_completo if est.curso else None,
            'grado_actual': grado_actual.nombre if grado_actual else None,
            'promedio_general': promedio_general,
            'literal': Calificacion().get_literal(promedio_general) if promedio_general else None,
            'asignaturas_reprobadas': asignaturas_reprobadas,
            'condicion': condicion,
            'nuevo_grado': nuevo_grado
        })
    
    # Resumen
    resumen = {
        'total': len(resultado),
        'promovidos': sum(1 for r in resultado if r['condicion'] == 'Promovido'),
        'promovidos_condicional': sum(1 for r in resultado if r['condicion'] == 'Promovido condicional'),
        'reprobados': sum(1 for r in resultado if r['condicion'] == 'Reprobado'),
        'sin_calificaciones': sum(1 for r in resultado if r['condicion'] == 'Sin calificaciones')
    }
    
    return {
        'estudiantes': resultado,
        'resumen': resumen
    }

@app.post("/api/promocion/ejecutar")
async def ejecutar_promocion(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Ejecutar la promoción de estudiantes al siguiente grado"""
    data = await request.json()
    
    estudiantes_promover = data.get('estudiantes', [])  # Lista de IDs
    
    promocionados = 0
    errores = []
    
    for est_id in estudiantes_promover:
        estudiante = db.get(Estudiante, est_id)
        if not estudiante:
            errores.append(f'Estudiante {est_id} no encontrado')
            continue
        
        if not estudiante.curso or not estudiante.curso.grado:
            errores.append(f'{estudiante.nombre_completo}: Sin curso/grado asignado')
            continue
        
        grado_actual = estudiante.curso.grado
        siguiente_grado = tenant_filter(db.query(Grado), Grado, current_user).filter(Grado.orden == grado_actual.orden + 1).first()
        
        if not siguiente_grado:
            # Estudiante egresa
            estudiante.activo = False
            log_auditoria(db, 'EGRESO', 'estudiantes', estudiante.id, user=current_user, request=request)
        else:
            # Buscar curso del siguiente grado en la misma tanda
            nuevo_curso = tenant_filter(db.query(Curso), Curso, current_user).filter_by(
                grado_id=siguiente_grado.id,
                tanda_id=estudiante.curso.tanda_id,
                activo=True
            ).first()
            
            if nuevo_curso:
                estudiante.curso_id = nuevo_curso.id
                log_auditoria(db, 'PROMOCION', 'estudiantes', estudiante.id, 
                             {'grado_anterior': grado_actual.nombre},
                             {'grado_nuevo': siguiente_grado.nombre}, user=current_user, request=request)
                promocionados += 1
            else:
                errores.append(f'{estudiante.nombre_completo}: No hay curso disponible para {siguiente_grado.nombre}')
    
    db.commit()
    
    return {
        'message': f'{promocionados} estudiantes promovidos',
        'promocionados': promocionados,
        'errores': errores
    }

# ============== MIS CURSOS (PROFESOR) ==============

@app.get("/api/mis-cursos")
async def get_mis_cursos(db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Obtener cursos asignados al profesor actual"""
    if current_user.role != 'profesor':
        # Para otros roles, retornar todos los cursos
        cursos = tenant_filter(db.query(Curso), Curso, current_user).filter_by(activo=True).join(Grado).outerjoin(Tanda).order_by(Grado.orden, Tanda.nombre, Curso.nombre).all()
        return [{
            'id': c.id,
            'nombre': c.nombre_completo,
            'grado': c.grado.nombre if c.grado else None,
            'tanda': c.tanda.nombre if c.tanda else None,
            'estudiantes': tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(curso_id=c.id, activo=True).count()
        } for c in cursos]
    
    # Para profesores, solo sus asignaciones
    asignaciones = tenant_filter(db.query(AsignacionProfesor), AsignacionProfesor, current_user).filter_by(profesor_id=current_user.id, activo=True).all()
    
    cursos_dict = {}
    for a in asignaciones:
        if a.curso_id not in cursos_dict:
            cursos_dict[a.curso_id] = {
                'id': a.curso_id,
                'nombre': a.curso.nombre_completo if a.curso else None,
                'grado': a.curso.grado.nombre if a.curso and a.curso.grado else None,
                'tanda': a.curso.tanda.nombre if a.curso and a.curso.tanda else None,
                'estudiantes': tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(curso_id=a.curso_id, activo=True).count(),
                'asignaturas': []
            }
        cursos_dict[a.curso_id]['asignaturas'].append({
            'id': a.asignatura_id,
            'nombre': a.asignatura.nombre if a.asignatura else None
        })
    
    return list(cursos_dict.values())

@app.get("/api/mis-asignaturas/{curso_id}")
async def get_mis_asignaturas_curso(curso_id, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Obtener asignaturas que el profesor imparte en un curso"""
    if current_user.role != 'profesor':
        # Para otros roles, retornar todas las asignaturas
        asignaturas = tenant_filter(db.query(Asignatura), Asignatura, current_user).filter_by(activo=True).all()
        return [{'id': a.id, 'nombre': a.nombre} for a in asignaturas]
    
    asignaciones = tenant_filter(db.query(AsignacionProfesor), AsignacionProfesor, current_user).filter_by(
        profesor_id=current_user.id,
        curso_id=curso_id,
        activo=True
    ).all()
    
    return [{
        'id': a.asignatura_id,
        'nombre': a.asignatura.nombre if a.asignatura else None
    } for a in asignaciones]

# ============== CIERRE DE AÑO - DATOS REALES ==============

@app.get("/api/cierre-ano/resumen")
async def get_resumen_cierre_ano(db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Obtener resumen real de todos los cursos para cierre de año.
    
    v2.13.8: lee AMBOS modelos (Calificacion legacy + CalificacionSecundaria nuevo).
    """
    cursos = tenant_filter(db.query(Curso), Curso, current_user).filter_by(activo=True).join(Grado).outerjoin(Tanda).order_by(Grado.orden, Tanda.nombre, Curso.nombre).all()
    resumen_cursos = []
    
    ano_activo_cr = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    
    for curso in cursos:
        estudiantes = tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(curso_id=curso.id, activo=True).all()
        promovidos = 0
        reprobados = 0
        promedios = []
        
        for est in estudiantes:
            # CFs combinados de AMBOS modelos
            cfs = []
            asig_ids_nuevo = set()
            
            # 1. Modelo NUEVO
            if ano_activo_cr:
                califs_sec_est = tenant_filter(
                    db.query(CalificacionSecundaria), CalificacionSecundaria, current_user
                ).filter_by(estudiante_id=est.id, ano_escolar_id=ano_activo_cr.id).all()
                from collections import defaultdict as _dd
                por_asig = _dd(list)
                for c in califs_sec_est:
                    por_asig[c.asignatura_id].append(c)
                for aid, comps in por_asig.items():
                    pcs = []
                    for p in range(1, 5):
                        vals = [comp.valor_periodo(p) for comp in comps if hasattr(comp, 'valor_periodo') and comp.valor_periodo(p) is not None]
                        if vals:
                            pcs.append(sum(vals) / len(vals))
                    if pcs:
                        cf = sum(pcs) / len(pcs)
                        cfs.append(cf)
                        asig_ids_nuevo.add(aid)
            
            # 2. Modelo LEGACY (solo asignaturas no en modelo nuevo)
            calificaciones = tenant_filter(db.query(Calificacion), Calificacion, current_user).filter_by(estudiante_id=est.id).all()
            for c in calificaciones:
                if c.asignatura_id in asig_ids_nuevo:
                    continue
                if c.cf is not None:
                    cfs.append(c.cf)
            
            if cfs:
                promedio_est = sum(cfs) / len(cfs)
                promedios.append(promedio_est)
                # Promovido si CF >= 70 en TODAS
                todas_aprobadas = all(cf >= 70 for cf in cfs)
                if todas_aprobadas:
                    promovidos += 1
                else:
                    reprobados += 1
        
        promedio_curso = sum(promedios) / len(promedios) if promedios else 0
        
        resumen_cursos.append({
            'id': curso.id,
            'nombre': curso.nombre_completo,
            'estudiantes': len(estudiantes),
            'promovidos': promovidos,
            'reprobados': reprobados,
            'promedio': round(promedio_curso, 1)
        })
    
    return {'cursos': resumen_cursos}

@app.get("/api/cierre-ano/promocion")
async def get_datos_promocion(db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Obtener lista de estudiantes con su condición de promoción"""
    estudiantes = tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(activo=True).all()
    grados = {g.id: g for g in tenant_filter(db.query(Grado), Grado, current_user).all()}
    
    resultado = []
    for est in estudiantes:
        calificaciones = tenant_filter(db.query(Calificacion), Calificacion, current_user).filter_by(estudiante_id=est.id).all()
        asistencias = tenant_filter(db.query(Asistencia), Asistencia, current_user).filter_by(estudiante_id=est.id).all()
        
        # v2.13.8: CFs de AMBOS modelos
        cfs_lista = []
        asig_ids_nuevo = set()
        
        ano_activo_cp = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
        if ano_activo_cp:
            califs_sec_est = tenant_filter(
                db.query(CalificacionSecundaria), CalificacionSecundaria, current_user
            ).filter_by(estudiante_id=est.id, ano_escolar_id=ano_activo_cp.id).all()
            from collections import defaultdict as _dd
            por_asig = _dd(list)
            for c in califs_sec_est:
                por_asig[c.asignatura_id].append(c)
            for aid, comps in por_asig.items():
                pcs = []
                for p in range(1, 5):
                    vals = [comp.valor_periodo(p) for comp in comps if hasattr(comp, 'valor_periodo') and comp.valor_periodo(p) is not None]
                    if vals:
                        pcs.append(sum(vals) / len(vals))
                if pcs:
                    cfs_lista.append(sum(pcs) / len(pcs))
                    asig_ids_nuevo.add(aid)
        
        # Legacy (solo asignaturas no en modelo nuevo)
        for c in calificaciones:
            if c.asignatura_id in asig_ids_nuevo:
                continue
            if c.cf is not None:
                cfs_lista.append(c.cf)
        
        # Calcular promedio general
        promedio_general = sum(cfs_lista) / len(cfs_lista) if cfs_lista else 0
        
        # Contar asignaturas aprobadas/reprobadas
        asignaturas_aprobadas = sum(1 for cf in cfs_lista if cf >= 70)
        asignaturas_reprobadas = sum(1 for cf in cfs_lista if cf < 70)
        total_asignaturas = len(cfs_lista)
        
        # Calcular asistencia
        total_asistencias = len(asistencias)
        presentes = sum(1 for a in asistencias if a.estado == 'presente')
        porcentaje_asistencia = (presentes / total_asistencias * 100) if total_asistencias > 0 else 0
        
        # Determinar condición
        todas_aprobadas = asignaturas_reprobadas == 0 and total_asignaturas > 0
        condicion = 'promovido' if todas_aprobadas else 'reprobado'
        
        # Determinar nuevo grado
        nuevo_grado = None
        if est.curso and est.curso.grado:
            grado_actual = est.curso.grado
            if condicion == 'promovido':
                # Buscar siguiente grado
                siguiente = tenant_filter(db.query(Grado), Grado, current_user).filter(Grado.orden > grado_actual.orden).order_by(Grado.orden).first()
                nuevo_grado = siguiente.nombre if siguiente else 'Graduado'
            else:
                nuevo_grado = grado_actual.nombre  # Repite
        
        resultado.append({
            'id': est.id,
            'nombre_completo': est.nombre_completo,
            'matricula': est.matricula,
            'curso': est.curso.nombre_completo if est.curso else None,
            'curso_id': est.curso_id,
            'promedio_general': round(promedio_general, 2),
            'asignaturas_aprobadas': asignaturas_aprobadas,
            'asignaturas_reprobadas': asignaturas_reprobadas,
            'total_asignaturas': total_asignaturas,
            'asistencia_porcentaje': round(porcentaje_asistencia, 1),
            'condicion': condicion,
            'nuevo_grado': nuevo_grado
        })
    
    # Ordenar por curso y nombre
    resultado.sort(key=lambda x: (x['curso'] or '', x['nombre_completo']))
    
    return {'estudiantes': resultado}

@app.post("/api/cierre-ano/promover")
async def ejecutar_promocion_cierre_ano(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """v2.13.20 — Ejecutar la promoción de estudiantes al año nuevo.

    Lógica (automática con excepciones):
      - Todos los estudiantes activos PROMUEVEN al grado siguiente por defecto.
      - EXCEPCIONES vía body 'overrides' {estudiante_id: 'repite'|'retira'}:
          'repite' → se queda en el mismo grado
          'retira' → se marca inactivo (se va a otro colegio), no se mueve
      - Último grado sin siguiente → 'egresado' (inactivo).

    Body JSON:
      - nuevo_ano_id (int): año escolar destino. Si no se pasa, usa el activo.
      - overrides (dict): {estudiante_id: 'repite'|'retira'}

    Requiere que exista un año CERRADO (el actual) antes de promover.
    """
    try:
        data = await request.json()
    except Exception:
        data = {}
    nuevo_ano_id = data.get('nuevo_ano_id')
    overrides_raw = data.get('overrides', {}) or {}
    overrides = {}
    for k, v in overrides_raw.items():
        try:
            overrides[int(k)] = v
        except (ValueError, TypeError):
            continue

    # El año cerrado (el que se acaba de cerrar)
    ano_cerrado = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(cerrado=True).order_by(AnoEscolar.id.desc()).first()
    if not ano_cerrado:
        return JSONResponse({'error': 'No hay un año escolar cerrado. Primero cerrá el año actual.'}, status_code=400)

    # Año destino
    if nuevo_ano_id:
        nuevo_ano = get_tenant_or_404(db, AnoEscolar, nuevo_ano_id, current_user, name='anoescolar')
    else:
        nuevo_ano = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    if not nuevo_ano:
        return JSONResponse({'error': 'No hay año escolar destino. Creá y activá el nuevo año antes de promover.'}, status_code=400)
    if nuevo_ano.id == ano_cerrado.id:
        return JSONResponse({'error': 'El año destino no puede ser el mismo que cerraste. Creá el nuevo año escolar.'}, status_code=400)

    # v2.13.25: Grado siguiente y detección del grado FINAL real del colegio.
    # Regla: un estudiante solo EGRESA si está en el grado de mayor orden de
    # todo el colegio (el verdadero final). Si está en un grado intermedio y
    # falta crear el siguiente, NO se le retira: se avisa para crear el grado.
    grados = tenant_filter(db.query(Grado), Grado, current_user).order_by(Grado.orden).all()
    grado_siguiente = {}
    for i, g in enumerate(grados):
        grado_siguiente[g.id] = grados[i+1] if i+1 < len(grados) else None
    # El grado final real = el de mayor orden entre los grados del colegio.
    grado_final_id = grados[-1].id if grados else None

    # Cursos del año destino por grado
    cursos_destino = tenant_filter(db.query(Curso), Curso, current_user).filter_by(
        activo=True, ano_escolar_id=nuevo_ano.id
    ).all()
    cursos_por_grado = {}
    for c in cursos_destino:
        cursos_por_grado.setdefault(c.grado_id, []).append(c)

    estudiantes = tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(activo=True).all()

    promovidos = repitentes = retirados = egresados = 0
    sin_curso_destino = []
    grados_faltantes = {}  # {grado_destino_id: nombre} para avisar

    for est in estudiantes:
        accion = overrides.get(est.id, 'promueve')

        if accion == 'retira':
            est.activo = False
            est.fecha_retiro = today_rd()
            est.motivo_retiro = est.motivo_retiro or 'Cambio de colegio (cierre de año)'
            retirados += 1
            continue

        if not est.curso or not est.curso.grado_id:
            continue
        grado_actual_id = est.curso.grado_id

        if accion == 'repite':
            destino_grado_id = grado_actual_id
            repitentes += 1
        else:
            # ¿Está en el grado final real del colegio? → egresa
            if grado_actual_id == grado_final_id:
                est.activo = False
                est.condicion = 'Egresado'
                egresados += 1
                continue
            # Si no es el final pero no hay grado siguiente registrado,
            # falta crear ese grado: NO retirar, avisar y dejar como está.
            sig = grado_siguiente.get(grado_actual_id)
            if sig is None:
                ga = db.get(Grado, grado_actual_id)
                grados_faltantes[grado_actual_id] = ga.nombre if ga else f'grado {grado_actual_id}'
                continue
            destino_grado_id = sig.id
            promovidos += 1

        candidatos = cursos_por_grado.get(destino_grado_id, [])
        curso_destino = None
        if candidatos:
            misma_tanda = [c for c in candidatos if c.tanda_id == est.curso.tanda_id]
            curso_destino = misma_tanda[0] if misma_tanda else candidatos[0]

        # v2.13.24: si no existe el curso destino en el año nuevo, crearlo
        # automáticamente (mismo nombre/tanda que el curso de origen, en el
        # grado destino). Así nadie queda sin promover por falta de curso.
        if not curso_destino:
            grado_dest = db.get(Grado, destino_grado_id)
            nombre_curso = est.curso.nombre or (grado_dest.nombre if grado_dest else 'A')
            curso_destino = Curso(
                colegio_id=current_user.colegio_id,
                nombre=nombre_curso,
                grado_id=destino_grado_id,
                tanda_id=est.curso.tanda_id,
                ano_escolar_id=nuevo_ano.id,
                activo=True,
            )
            db.add(curso_destino)
            db.flush()  # obtener id
            cursos_por_grado.setdefault(destino_grado_id, []).append(curso_destino)

        est.curso_id = curso_destino.id
        est.condicion = 'Inscrito'

    db.commit()
    try:
        log_auditoria(db, 'PROMOCION', 'estudiantes', None, None,
                      {'promovidos': promovidos, 'repitentes': repitentes,
                       'retirados': retirados, 'egresados': egresados,
                       'ano_destino': nuevo_ano.id}, user=current_user, request=request)
        db.commit()
    except Exception as _e:
        db.rollback()  # el log no debe tumbar la promoción ya guardada
        logger.warning(f"No se pudo registrar auditoría de promoción: {_e}")

    # Construir avisos
    avisos = []
    if grados_faltantes:
        nombres = ', '.join(grados_faltantes.values())
        avisos.append(
            f'No se promovieron los estudiantes de: {nombres}, porque falta '
            f'crear el grado siguiente. Creá esos grados y volvé a promover.'
        )
    if sin_curso_destino:
        avisos.append(
            f'{len(sin_curso_destino)} estudiante(s) no se movieron por falta de '
            f'curso destino (se intentó crear automáticamente).'
        )

    return {
        'message': 'Promoción ejecutada correctamente',
        'ano_destino': nuevo_ano.nombre,
        'promovidos': promovidos,
        'repitentes': repitentes,
        'retirados': retirados,
        'egresados': egresados,
        'sin_curso_destino': sin_curso_destino,
        'grados_faltantes': list(grados_faltantes.values()),
        'aviso': ' '.join(avisos) if avisos else None
    }


# ============== CALIFICACIONES POR MATERIA (VISTA GENERAL) ==============

@app.get("/api/calificaciones/por-materia")
async def get_calificaciones_por_materia(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Ver todas las calificaciones organizadas por materia y período"""
    curso_id = int(request.query_params.get('curso_id', 0) or 0)
    
    if not curso_id:
        return JSONResponse({'error': 'Curso requerido'}, status_code=400)
    
    curso = get_tenant_or_404(db, Curso, curso_id, current_user, name='curso')
    estudiantes = tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(curso_id=curso_id, activo=True).order_by(Estudiante.no_lista).all()
    asignaturas = tenant_filter(db.query(Asignatura), Asignatura, current_user).filter_by(activo=True).all()
    
    # v2.13.8: pre-cargar dual-modelo (evita N+1)
    est_ids = [e.id for e in estudiantes]
    asig_ids = [a.id for a in asignaturas]
    
    # Modelo NUEVO
    ano_pm = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    sec_por_est_asig = {}
    if ano_pm and est_ids and asig_ids:
        califs_sec_pm = tenant_filter(
            db.query(CalificacionSecundaria), CalificacionSecundaria, current_user
        ).filter(
            CalificacionSecundaria.estudiante_id.in_(est_ids),
            CalificacionSecundaria.asignatura_id.in_(asig_ids),
            CalificacionSecundaria.ano_escolar_id == ano_pm.id,
        ).all()
        from collections import defaultdict as _dd
        sec_por_est_asig = _dd(list)
        for c in califs_sec_pm:
            sec_por_est_asig[(c.estudiante_id, c.asignatura_id)].append(c)
    
    # Modelo LEGACY
    califs_leg_pm = tenant_filter(db.query(Calificacion), Calificacion, current_user).filter(
        Calificacion.estudiante_id.in_(est_ids),
        Calificacion.asignatura_id.in_(asig_ids),
    ).all() if est_ids and asig_ids else []
    leg_por_est_asig = {(c.estudiante_id, c.asignatura_id): c for c in califs_leg_pm}
    
    resultado = {
        'curso': curso.nombre_completo,
        'asignaturas': []
    }
    
    for asig in asignaturas:
        asig_data = {
            'id': asig.id,
            'nombre': asig.nombre,
            'estudiantes': []
        }
        
        # Buscar profesor asignado
        asignacion = tenant_filter(db.query(AsignacionProfesor), AsignacionProfesor, current_user).filter_by(
            curso_id=curso_id,
            asignatura_id=asig.id,
            activo=True
        ).first()
        asig_data['profesor'] = asignacion.profesor.nombre_completo if asignacion and asignacion.profesor else 'Sin asignar'
        
        for est in estudiantes:
            # Modelo NUEVO primero
            comps = sec_por_est_asig.get((est.id, asig.id), [])
            if comps:
                pcs = {}
                for p in range(1, 5):
                    vals = [c.valor_periodo(p) for c in comps if hasattr(c, 'valor_periodo') and c.valor_periodo(p) is not None]
                    pcs[f'p{p}'] = round(sum(vals) / len(vals), 1) if vals else None
                pcs_validos = [v for v in pcs.values() if v is not None]
                cf = int(round(sum(pcs_validos) / len(pcs_validos))) if pcs_validos else None
                est_data = {
                    'id': est.id,
                    'nombre': est.nombre_completo,
                    'no_lista': est.no_lista,
                    'p1': pcs['p1'], 'p2': pcs['p2'], 'p3': pcs['p3'], 'p4': pcs['p4'],
                    'cf': cf,
                    'promedio': round(sum(pcs_validos) / len(pcs_validos), 1) if pcs_validos else None,
                }
            else:
                # Fallback LEGACY
                calif = leg_por_est_asig.get((est.id, asig.id))
                est_data = {
                    'id': est.id,
                    'nombre': est.nombre_completo,
                    'no_lista': est.no_lista,
                    'p1': calif.pc1 if calif else None,
                    'p2': calif.pc2 if calif else None,
                    'p3': calif.pc3 if calif else None,
                    'p4': calif.pc4 if calif else None,
                    'cf': calif.cf if calif else None,
                    'promedio': None
                }
                notas = [n for n in [est_data['p1'], est_data['p2'], est_data['p3'], est_data['p4']] if n is not None]
                if notas:
                    est_data['promedio'] = round(sum(notas) / len(notas), 1)
            
            asig_data['estudiantes'].append(est_data)
        
        resultado['asignaturas'].append(asig_data)
    
    return resultado


@app.get("/api/calificaciones/por-periodo")
async def get_calificaciones_por_periodo(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Ver notas de todos los estudiantes de un curso - optimizado con bulk load"""
    curso_id = int(request.query_params.get('curso_id', 0) or 0)
    periodo = int(request.query_params.get('periodo', 1))
    
    if not curso_id:
        return JSONResponse({'error': 'Curso requerido'}, status_code=400)
    if periodo < 1 or periodo > 4:
        return JSONResponse({'error': 'Período inválido'}, status_code=400)
    
    return get_calificaciones_periodo(db, current_user, curso_id, periodo)


@app.get("/api/calificaciones/por-periodo/tarjetas")
async def get_tarjetas_notas_periodo(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion', 'coordinador'))):
    """Generar PDF con tarjetas individuales de notas por estudiante (una por página)"""
    curso_id = int(request.query_params.get('curso_id', 0) or 0)
    periodo = int(request.query_params.get('periodo', 1))
    modo = request.query_params.get('modo', 'completo')  # 'completo' o 'padres'
    nota_final = request.query_params.get('nota_final', 'pc')  # 'pc' o 'p4'
    
    if not curso_id:
        return JSONResponse({'error': 'Curso requerido'}, status_code=400)
    if periodo < 1 or periodo > 4:
        return JSONResponse({'error': 'Período inválido'}, status_code=400)
    
    try:
        simple = modo == 'padres'
        usar_p4 = nota_final == 'p4'
        buffer = generar_tarjetas_pdf(db, current_user, curso_id, periodo, simple=simple, usar_p4=usar_p4)
        curso = db.get(Curso, curso_id)
        curso_nombre = curso.nombre_completo.replace(' ', '_') if curso else 'Curso'
        prefix = "Reporte_Padres" if simple else "Tarjetas_Notas"
        filename = f"{prefix}_P{periodo}_{curso_nombre}.pdf"
        
        return StreamingResponse(
            buffer,
            media_type='application/pdf',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        logger.error(f"Error generando tarjetas: {e}")
        return JSONResponse({'error': f'Error generando tarjetas: {str(e)}'}, status_code=500)


@app.get("/api/calificaciones/por-periodo/pdf")
async def get_calificaciones_por_periodo_pdf(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion', 'coordinador'))):
    """Generar PDF con notas de un período para un curso"""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    
    curso_id = int(request.query_params.get('curso_id', 0) or 0)
    periodo = int(request.query_params.get('periodo', 1))
    
    if not curso_id:
        return JSONResponse({'error': 'Curso requerido'}, status_code=400)
    
    curso = get_tenant_or_404(db, Curso, curso_id, current_user, name='curso')
    config = tenant_filter(db.query(ConfiguracionColegio), ConfiguracionColegio, current_user).first()
    ano = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    estudiantes = tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(curso_id=curso_id, activo=True).order_by(Estudiante.no_lista).all()
    
    asignaciones = tenant_filter(db.query(AsignacionProfesor), AsignacionProfesor, current_user).filter_by(curso_id=curso_id, activo=True).all()
    asignatura_ids = list(set(a.asignatura_id for a in asignaciones))
    asignaturas = tenant_filter(db.query(Asignatura), Asignatura, current_user).filter(Asignatura.id.in_(asignatura_ids)).order_by(Asignatura.nombre).all()
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), topMargin=0.4*inch, bottomMargin=0.4*inch, leftMargin=0.4*inch, rightMargin=0.4*inch)
    elements = []
    styles = getSampleStyleSheet()
    
    # Título
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=14, alignment=1, spaceAfter=4)
    subtitle_style = ParagraphStyle('Sub', parent=styles['Normal'], fontSize=9, alignment=1, spaceAfter=10)
    
    elements.append(Paragraph(config.nombre if config else 'Centro Educativo', title_style))
    curso_nombre = curso.nombre_completo if hasattr(curso, 'nombre_completo') else curso.nombre
    elements.append(Paragraph(f'NOTAS POR PERÍODO {periodo} — {curso_nombre} — {ano.nombre if ano else ""}', subtitle_style))
    elements.append(Spacer(1, 8))
    
    # Construir tabla
    headers = ['#', 'Estudiante'] + [a.nombre[:15] for a in asignaturas] + ['Prom.']
    table_data = [headers]
    
    # v2.13.8: pre-cargar dual-modelo
    est_ids = [e.id for e in estudiantes]
    asig_ids_list = [a.id for a in asignaturas]
    sec_por_est_asig_pdf = {}
    if ano and est_ids and asig_ids_list:
        califs_sec_pdf = tenant_filter(
            db.query(CalificacionSecundaria), CalificacionSecundaria, current_user
        ).filter(
            CalificacionSecundaria.estudiante_id.in_(est_ids),
            CalificacionSecundaria.asignatura_id.in_(asig_ids_list),
            CalificacionSecundaria.ano_escolar_id == ano.id,
        ).all()
        from collections import defaultdict as _dd
        sec_por_est_asig_pdf = _dd(list)
        for c in califs_sec_pdf:
            sec_por_est_asig_pdf[(c.estudiante_id, c.asignatura_id)].append(c)
    
    califs_leg_pdf = tenant_filter(db.query(Calificacion), Calificacion, current_user).filter(
        Calificacion.estudiante_id.in_(est_ids),
        Calificacion.asignatura_id.in_(asig_ids_list),
    ).all() if est_ids and asig_ids_list else []
    leg_por_est_asig_pdf = {(c.estudiante_id, c.asignatura_id): c for c in califs_leg_pdf}
    
    for est in estudiantes:
        row = [str(est.no_lista or ''), est.nombre_completo[:25]]
        notas = []
        for asig in asignaturas:
            # Modelo NUEVO primero
            comps = sec_por_est_asig_pdf.get((est.id, asig.id), [])
            pc = None
            if comps:
                vals = [c.valor_periodo(periodo) for c in comps if hasattr(c, 'valor_periodo') and c.valor_periodo(periodo) is not None]
                pc = round(sum(vals) / len(vals), 1) if vals else None
            
            # Fallback LEGACY
            if pc is None:
                calif_leg = leg_por_est_asig_pdf.get((est.id, asig.id))
                if calif_leg:
                    pc = getattr(calif_leg, f'pc{periodo}', None)
            
            row.append(str(int(pc)) if pc is not None else '-')
            if pc is not None:
                notas.append(pc)
        prom = round(sum(notas) / len(notas), 1) if notas else None
        row.append(str(prom) if prom else '-')
        table_data.append(row)
    
    # Anchos de columna
    n_asig = len(asignaturas)
    asig_width = min(0.7 * inch, (8.5 * inch) / (n_asig + 3))
    col_widths = [0.3 * inch, 1.8 * inch] + [asig_width] * n_asig + [0.5 * inch]
    
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2563eb')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 7),
        ('FONTSIZE', (0, 1), (-1, -1), 7),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (2, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
    ]))
    
    # Color rojo para notas < 70
    for row_idx in range(1, len(table_data)):
        for col_idx in range(2, len(table_data[row_idx])):
            val = table_data[row_idx][col_idx]
            try:
                if val != '-' and float(val) < 70:
                    t.setStyle(TableStyle([
                        ('TEXTCOLOR', (col_idx, row_idx), (col_idx, row_idx), colors.red),
                        ('FONTNAME', (col_idx, row_idx), (col_idx, row_idx), 'Helvetica-Bold'),
                    ]))
            except ValueError:
                pass
    
    elements.append(t)
    doc.build(elements)
    buffer.seek(0)
    
    filename = f"Notas_P{periodo}_{curso_nombre.replace(' ', '_')}.pdf"
    return StreamingResponse(buffer, media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename="{filename}"'})


@app.get("/api/calificaciones/resumen-curso/{curso_id}")
async def get_resumen_calificaciones_curso(curso_id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Resumen de calificaciones de un curso con promedios por materia.
    
    v2.13.7: lee AMBOS modelos (Calificacion legacy + CalificacionSecundaria nuevo).
    Para secundaria nueva, calcula PC1..PC4 y CF desde las 4 competencias.
    """
    curso = get_tenant_or_404(db, Curso, curso_id, current_user, name='curso')
    estudiantes = tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(curso_id=curso_id, activo=True).order_by(Estudiante.no_lista).all()
    
    # Asignaturas del curso
    asignaciones = tenant_filter(db.query(AsignacionProfesor), AsignacionProfesor, current_user).filter_by(curso_id=curso_id, activo=True).all()
    asignatura_ids = list(set([a.asignatura_id for a in asignaciones]))
    asignaturas = tenant_filter(db.query(Asignatura), Asignatura, current_user).filter(Asignatura.id.in_(asignatura_ids)).all() if asignatura_ids else []
    
    # v2.13.7: pre-cargar datos del modelo NUEVO para todo el curso
    ano_activo = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    est_ids = [e.id for e in estudiantes]
    
    # Indexar CalificacionSecundaria por (estudiante, asignatura) → lista de comps
    sec_por_est_asig: dict = {}
    if ano_activo and est_ids and asignatura_ids:
        califs_sec = tenant_filter(
            db.query(CalificacionSecundaria), CalificacionSecundaria, current_user
        ).filter(
            CalificacionSecundaria.estudiante_id.in_(est_ids),
            CalificacionSecundaria.asignatura_id.in_(asignatura_ids),
            CalificacionSecundaria.ano_escolar_id == ano_activo.id,
        ).all()
        from collections import defaultdict as _dd
        sec_por_est_asig = _dd(list)
        for c in califs_sec:
            sec_por_est_asig[(c.estudiante_id, c.asignatura_id)].append(c)
    
    resultado = []
    
    for est in estudiantes:
        est_data = {
            'id': est.id,
            'no_lista': est.no_lista,
            'nombre': est.nombre_completo,
            'materias': {},
            'promedio_general': None
        }
        
        promedios = []
        for asig in asignaturas:
            # ─── 1. Modelo NUEVO primero ───
            comps = sec_por_est_asig.get((est.id, asig.id), [])
            if comps:
                pcs = {}  # pc1..pc4
                for p in range(1, 5):
                    vals = []
                    for c in comps:
                        v = c.valor_periodo(p) if hasattr(c, 'valor_periodo') else None
                        if v is not None:
                            vals.append(v)
                    pcs[f'pc{p}'] = round(sum(vals) / len(vals), 1) if vals else None
                
                pcs_validos = [v for v in pcs.values() if v is not None]
                cf = int(round(sum(pcs_validos) / len(pcs_validos))) if pcs_validos else None
                promedio = round(sum(pcs_validos) / len(pcs_validos), 1) if pcs_validos else None
                
                est_data['materias'][asig.nombre] = {
                    'p1': pcs['pc1'], 'p2': pcs['pc2'],
                    'p3': pcs['pc3'], 'p4': pcs['pc4'],
                    'cf': cf,
                    'promedio': promedio
                }
                if promedio is not None:
                    promedios.append(promedio)
                continue
            
            # ─── 2. Fallback a modelo LEGACY ───
            calif = tenant_filter(db.query(Calificacion), Calificacion, current_user).filter_by(
                estudiante_id=est.id,
                asignatura_id=asig.id
            ).first()
            
            if calif:
                notas = [n for n in [calif.pc1, calif.pc2, calif.pc3, calif.pc4] if n is not None]
                promedio = round(sum(notas) / len(notas), 1) if notas else None
                est_data['materias'][asig.nombre] = {
                    'p1': calif.pc1, 'p2': calif.pc2,
                    'p3': calif.pc3, 'p4': calif.pc4,
                    'cf': calif.cf,
                    'promedio': promedio
                }
                if promedio:
                    promedios.append(promedio)
            else:
                est_data['materias'][asig.nombre] = None
        
        if promedios:
            est_data['promedio_general'] = round(sum(promedios) / len(promedios), 1)
        
        resultado.append(est_data)
    
    return {
        'curso': curso.nombre_completo,
        'asignaturas': [a.nombre for a in asignaturas],
        'estudiantes': resultado
    }


# ============== ESTADÍSTICAS REALES ==============

@app.get("/api/estadisticas/cursos")
async def get_estadisticas_cursos(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Estadísticas por curso - optimizado con bulk queries. Filtro opcional por nivel."""
    periodo = int(request.query_params.get('periodo', 0) or 0)
    nivel = request.query_params.get('nivel')  # 'primaria', 'secundaria', 'todos', o None
    try:
        return get_stats_cursos(db, current_user, periodo, nivel=nivel)
    except Exception as e:
        logger.error(f"Error en estadísticas cursos: {e}")
        return []

@app.get("/api/estadisticas/asignaturas")
async def get_estadisticas_asignaturas(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Estadísticas por asignatura con filtro por período.
    
    v2.13.3: lee AMBOS modelos (Calificacion legacy + CalificacionSecundaria nuevo).
    Para una asignatura dada, las notas pueden venir de cualquiera de los dos modelos
    según el curso del estudiante. Combinamos ambas fuentes en el promedio final.
    """
    periodo = int(request.query_params.get('periodo', 0) or 0)
    asignaturas = tenant_filter(db.query(Asignatura), Asignatura, current_user).filter_by(activo=True).all()
    ano_activo = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    resultado = []
    
    for asig in asignaturas:
        # Acumulador de notas finales por estudiante de esta asignatura
        # (clave: estudiante_id; valor: nota efectiva)
        notas_por_est: dict = {}
        
        # ─── Modelo NUEVO: CalificacionSecundaria ───
        # 1 fila por (estudiante, competencia). Necesitamos las 4 competencias
        # para calcular CF/PC del área. Calculamos según haya o no período.
        if ano_activo:
            try:
                comps_sec = tenant_filter(
                    db.query(CalificacionSecundaria), CalificacionSecundaria, current_user
                ).filter_by(asignatura_id=asig.id, ano_escolar_id=ano_activo.id).all()
                
                # Agrupar por estudiante → lista de competencias
                por_est: dict = {}
                for c in comps_sec:
                    por_est.setdefault(c.estudiante_id, []).append(c)
                
                for eid, comps in por_est.items():
                    if periodo and periodo > 0:
                        # PC del período: promedio de las competencias con valor en ese período
                        vals = []
                        for c in comps:
                            v = c.valor_periodo(periodo) if hasattr(c, 'valor_periodo') else None
                            if v is not None:
                                vals.append(v)
                        if vals:
                            notas_por_est[eid] = sum(vals) / len(vals)
                    else:
                        # CF del área = AVG(PC1..PC4)
                        pcs = []
                        for p in range(1, 5):
                            vals_p = []
                            for c in comps:
                                v = c.valor_periodo(p) if hasattr(c, 'valor_periodo') else None
                                if v is not None:
                                    vals_p.append(v)
                            if vals_p:
                                pcs.append(sum(vals_p) / len(vals_p))
                        if pcs:
                            notas_por_est[eid] = sum(pcs) / len(pcs)
            except Exception as e:
                logger.warning(f"Error leyendo CalificacionSecundaria de asig {asig.id}: {e}")
        
        # ─── Modelo LEGACY: Calificacion ───
        # Solo para estudiantes que NO tienen datos en modelo nuevo
        calificaciones = tenant_filter(db.query(Calificacion), Calificacion, current_user).filter_by(asignatura_id=asig.id).all()
        
        for c in calificaciones:
            if c.estudiante_id in notas_por_est:
                continue  # ya tiene del modelo nuevo
            if periodo and periodo > 0:
                pc = getattr(c, f'pc{periodo}', None)
                rp = getattr(c, f'rp{periodo}', None)
                if pc is not None:
                    nota_final = rp if (pc < 70 and rp is not None) else pc
                    notas_por_est[c.estudiante_id] = nota_final
            else:
                if c.cf is not None:
                    notas_por_est[c.estudiante_id] = c.cf
                else:
                    pcs = []
                    for p in range(1, 5):
                        pc_val = getattr(c, f'pc{p}', None)
                        rp_val = getattr(c, f'rp{p}', None)
                        if pc_val is not None:
                            pcs.append(rp_val if (pc_val < 70 and rp_val is not None) else pc_val)
                    if pcs:
                        notas_por_est[c.estudiante_id] = sum(pcs) / len(pcs)
        
        notas = list(notas_por_est.values())
        if not notas:
            continue
        
        promedio = sum(notas) / len(notas)
        aprobados = sum(1 for n in notas if n >= 70)
        reprobados = len(notas) - aprobados
        
        resultado.append({
            'id': asig.id,
            'nombre': asig.nombre,
            'promedio': round(promedio, 1),
            'aprobados': round(aprobados / len(notas) * 100),
            'reprobados': round(reprobados / len(notas) * 100)
        })
    
    resultado.sort(key=lambda x: x['promedio'], reverse=True)
    return resultado

# ============== DÍAS NO LABORABLES ==============

@app.get("/api/dias-no-laborables")
async def get_dias_no_laborables(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Obtener días no laborables del año activo"""
    ano_activo = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    dias = tenant_filter(db.query(DiaNoLaborable), DiaNoLaborable, current_user).filter_by(activo=True).all()
    
    # Filtrar por año o recurrentes
    resultado = []
    for d in dias:
        if d.recurrente or (d.ano_escolar_id == ano_activo.id if ano_activo else True):
            resultado.append(d.to_dict())
    
    return resultado

@app.post("/api/dias-no-laborables")
async def crear_dia_no_laborable(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Crear día no laborable"""
    data = await request.json()
    ano_activo = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    
    # Parsear fecha
    fecha_str = data.get('fecha')
    if not fecha_str:
        return JSONResponse({'error': 'La fecha es requerida'}, status_code=400)
    
    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return JSONResponse({'error': 'Formato de fecha inválido'}, status_code=400)
    
    dia = DiaNoLaborable(
        colegio_id=current_user.colegio_id,
        fecha=fecha,
        nombre=data['nombre'],
        tipo=data.get('tipo', 'feriado'),
        recurrente=data.get('recurrente', False),
        ano_escolar_id=ano_activo.id if ano_activo else None
    )
    db.add(dia)
    db.commit()
    
    return JSONResponse({'message': 'Día no laborable creado', 'id': dia.id}, status_code=201)

@app.delete("/api/dias-no-laborables/{id}")
async def eliminar_dia_no_laborable(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Eliminar día no laborable"""
    dia = get_tenant_or_404(db, DiaNoLaborable, id, current_user, name='dianolaborable')
    dia.activo = False
    db.commit()
    return {'message': 'Día eliminado'}

@app.post("/api/dias-no-laborables/cargar-feriados-rd")
async def cargar_feriados_rd(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Cargar feriados oficiales de República Dominicana"""
    data = await request.json()
    ano = data.get('ano', today_rd().year)
    
    feriados_rd = [
        (f'{ano}-01-01', 'Año Nuevo'),
        (f'{ano}-01-06', 'Día de los Santos Reyes'),
        (f'{ano}-01-21', 'Día de la Altagracia'),
        (f'{ano}-01-26', 'Día de Duarte'),
        (f'{ano}-02-27', 'Día de la Independencia'),
        (f'{ano}-05-01', 'Día del Trabajo'),
        (f'{ano}-06-16', 'Corpus Christi'),
        (f'{ano}-08-16', 'Día de la Restauración'),
        (f'{ano}-09-24', 'Día de las Mercedes'),
        (f'{ano}-11-06', 'Día de la Constitución'),
        (f'{ano}-12-25', 'Navidad'),
    ]
    
    agregados = 0
    for fecha_str, nombre in feriados_rd:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        existe = tenant_filter(db.query(DiaNoLaborable), DiaNoLaborable, current_user).filter_by(fecha=fecha, activo=True).first()
        if not existe:
            dia = DiaNoLaborable(fecha=fecha, nombre=nombre, tipo='feriado', recurrente=True, colegio_id=current_user.colegio_id)
            db.add(dia)
            agregados += 1
    
    db.commit()
    return {'message': f'{agregados} feriados agregados'}

# ============== ASIGNACIONES POR CURSO ==============

@app.get("/api/cursos/{curso_id}/asignaciones")
async def get_asignaciones_curso(curso_id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Obtener asignaciones de un curso (qué profesor da cada materia)"""
    curso = get_tenant_or_404(db, Curso, curso_id, current_user, name='curso')
    asignaturas = tenant_filter(db.query(Asignatura), Asignatura, current_user).filter_by(activo=True).order_by(Asignatura.nombre).all()
    asignaciones = tenant_filter(db.query(AsignacionProfesor), AsignacionProfesor, current_user).filter_by(curso_id=curso_id, activo=True).all()
    
    # Crear mapa de asignatura -> profesor
    mapa = {a.asignatura_id: a for a in asignaciones}
    
    resultado = []
    for asig in asignaturas:
        asignacion = mapa.get(asig.id)
        resultado.append({
            'asignatura_id': asig.id,
            'asignatura': asig.nombre,
            'profesor_id': asignacion.profesor_id if asignacion else None,
            'profesor': asignacion.profesor.nombre_completo if asignacion and asignacion.profesor else None,
            'es_titular': asignacion.es_titular if asignacion else False
        })
    
    return {
        'curso': curso.nombre_completo,
        'curso_id': curso_id,
        'asignaciones': resultado
    }

@app.post("/api/cursos/{curso_id}/asignaciones")
async def guardar_asignaciones_curso(curso_id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion'))):
    """Guardar todas las asignaciones de un curso de una vez"""
    curso = get_tenant_or_404(db, Curso, curso_id, current_user, name='curso')
    data = await request.json()
    asignaciones_data = data.get('asignaciones', [])
    
    # Desactivar asignaciones anteriores de este curso
    tenant_filter(db.query(AsignacionProfesor), AsignacionProfesor, current_user).filter_by(curso_id=curso_id, activo=True).update({'activo': False})
    
    creadas = 0
    for asig in asignaciones_data:
        if asig.get('profesor_id'):  # Solo si tiene profesor asignado
            nueva = AsignacionProfesor(
                profesor_id=asig['profesor_id'],
                curso_id=curso_id,
                asignatura_id=asig['asignatura_id'],
                es_titular=asig.get('es_titular', False),
                activo=True,
                colegio_id=current_user.colegio_id
            )
            db.add(nueva)
            creadas += 1
    
    db.commit()
    log_auditoria(db, 'ASIGNAR_PROFESORES', 'cursos', curso_id, user=current_user, request=request)
    
    return {'message': f'{creadas} asignaciones guardadas para {curso.nombre_completo}'}


# ============== IMPRESIONES PDF (v2.11) ==============

@app.get("/api/imprimir/lista-estudiantes/{curso_id}")
async def imprimir_lista_estudiantes(curso_id: int, request: Request,
                                       db: Session = Depends(get_db),
                                       current_user: Usuario = Depends(get_current_user)):
    """
    Genera PDF de lista de estudiantes de un curso.
    
    Permisos (v2.11):
    - Dirección, coordinador, psicología, secretaría: cualquier curso del colegio
    - Profesor: solo cursos donde tiene asignación activa
    
    El PDF incluye encabezado del colegio (logo, RNC, dirección), título con
    grado/tanda, tabla de estudiantes con estado activo/retirado, y firmas.
    """
    from lista_estudiantes_pdf import generar_lista_estudiantes_pdf
    
    # Validar tenant del curso (y existencia)
    curso = get_tenant_or_404(db, Curso, curso_id, current_user, name='curso')
    
    # Si es profesor: verificar que tenga asignación a este curso
    if current_user.role == 'profesor':
        tiene_asignacion = db.query(AsignacionProfesor).filter_by(
            profesor_id=current_user.id, curso_id=curso_id
        ).first()
        if not tiene_asignacion:
            return JSONResponse(
                {'error': 'No tiene asignaciones en este curso'},
                status_code=403
            )
    
    # Obtener datos relacionados
    grado = db.get(Grado, curso.grado_id) if curso.grado_id else None
    tanda = db.get(Tanda, curso.tanda_id) if curso.tanda_id else None
    config = db.query(ConfiguracionColegio).filter_by(colegio_id=current_user.colegio_id).first()
    colegio = db.get(Colegio, current_user.colegio_id) if current_user.colegio_id else None
    
    # Año escolar activo
    ano_activo = db.query(AnoEscolar).filter_by(
        colegio_id=current_user.colegio_id, activo=True
    ).first()
    ano_str = ano_activo.nombre if ano_activo else None
    
    # Estudiantes del curso, ordenados por apellido (incluye retirados para tener
    # la lista completa con el flag de estado)
    estudiantes = db.query(Estudiante).filter_by(
        curso_id=curso_id, colegio_id=current_user.colegio_id
    ).order_by(Estudiante.apellido, Estudiante.nombre).all()
    
    pdf_bytes = generar_lista_estudiantes_pdf(
        estudiantes=estudiantes,
        curso=curso, tanda=tanda, grado=grado,
        config=config, colegio=colegio,
        ano_escolar=ano_str,
    )
    
    from fastapi.responses import Response
    from pdf_helpers import safe_filename_ascii
    raw = f"lista_{grado.nombre if grado else 'curso'}_{curso.nombre or ''}.pdf"
    nombre_archivo = safe_filename_ascii(raw, default="lista_estudiantes.pdf")
    return Response(
        content=pdf_bytes,
        media_type='application/pdf',
        headers={'Content-Disposition': f'inline; filename="{nombre_archivo}"'}
    )


@app.get("/api/imprimir/calificaciones/{curso_id}/{asignatura_id}")
async def imprimir_calificaciones(curso_id: int, asignatura_id: int, request: Request,
                                     db: Session = Depends(get_db),
                                     current_user: Usuario = Depends(get_current_user)):
    """
    Genera PDF de calificaciones de un curso/asignatura para un período específico.
    
    Query params:
    - periodo: 1, 2, 3 o 4 (default: 1)
    
    Permisos:
    - Dirección, coordinador: cualquier curso del colegio
    - Profesor: solo cursos donde tiene asignación a esa asignatura
    """
    from calificaciones_pdf import generar_calificaciones_pdf
    
    curso = get_tenant_or_404(db, Curso, curso_id, current_user, name='curso')
    asignatura = get_tenant_or_404(db, Asignatura, asignatura_id, current_user, name='asignatura')
    
    # Periodo
    try:
        periodo = int(request.query_params.get('periodo', '1'))
    except (ValueError, TypeError):
        return JSONResponse({'error': 'periodo debe ser un número'}, status_code=400)
    if periodo not in (1, 2, 3, 4):
        return JSONResponse({'error': 'periodo debe ser 1, 2, 3 o 4'}, status_code=400)
    
    # Profesor: validar asignación
    if current_user.role == 'profesor':
        tiene_asig = db.query(AsignacionProfesor).filter_by(
            profesor_id=current_user.id, curso_id=curso_id, asignatura_id=asignatura_id
        ).first()
        if not tiene_asig:
            return JSONResponse(
                {'error': 'No tiene asignación para este curso/asignatura'},
                status_code=403
            )
    
    # Datos relacionados
    grado = db.get(Grado, curso.grado_id) if curso.grado_id else None
    tanda = db.get(Tanda, curso.tanda_id) if curso.tanda_id else None
    config = db.query(ConfiguracionColegio).filter_by(colegio_id=current_user.colegio_id).first()
    colegio = db.get(Colegio, current_user.colegio_id) if current_user.colegio_id else None
    ano_activo = db.query(AnoEscolar).filter_by(
        colegio_id=current_user.colegio_id, activo=True
    ).first()
    ano_str = ano_activo.nombre if ano_activo else None
    
    # Estudiantes del curso (activos) ordenados por apellido
    estudiantes = db.query(Estudiante).filter_by(
        curso_id=curso_id, colegio_id=current_user.colegio_id, activo=True
    ).order_by(Estudiante.apellido, Estudiante.nombre).all()
    
    # Construir lista calificaciones como espera el PDF
    calificaciones_data = []
    for est in estudiantes:
        cal = db.query(Calificacion).filter_by(
            estudiante_id=est.id, asignatura_id=asignatura_id
        ).first()
        cal_dict = {}
        if cal:
            cal_dict = {
                f'p{periodo}_p1': getattr(cal, f'p{periodo}_p1', None),
                f'p{periodo}_p2': getattr(cal, f'p{periodo}_p2', None),
                f'p{periodo}_p3': getattr(cal, f'p{periodo}_p3', None),
                f'p{periodo}_p4': getattr(cal, f'p{periodo}_p4', None),
                f'pc{periodo}': getattr(cal, f'pc{periodo}', None),
                f'rp{periodo}': getattr(cal, f'rp{periodo}', None),
            }
        calificaciones_data.append({
            'estudiante': {
                'id': est.id,
                'nombre_completo': f"{est.apellido or ''}, {est.nombre or ''}",
            },
            'calificacion': cal_dict,
        })
    
    pdf_bytes = generar_calificaciones_pdf(
        calificaciones=calificaciones_data,
        curso=curso, grado=grado, tanda=tanda, asignatura=asignatura,
        periodo=periodo,
        config=config, colegio=colegio,
        ano_escolar=ano_str,
    )
    
    from fastapi.responses import Response
    from pdf_helpers import safe_filename_ascii
    raw = f"cal_p{periodo}_{asignatura.nombre or 'asig'}.pdf"
    nombre = safe_filename_ascii(raw, default=f"calificaciones_p{periodo}.pdf")
    return Response(
        content=pdf_bytes,
        media_type='application/pdf',
        headers={'Content-Disposition': f'inline; filename="{nombre}"'}
    )


# ============== REGISTRO ESCOLAR MINERD ==============

# ============================================
# NUEVOS ENDPOINTS (v2) — con validación robusta
# ============================================

@app.get("/api/registros/validar/{curso_id}")
async def validar_registro(curso_id: int, request: Request, db: Session = Depends(get_db),
                           current_user: Usuario = Depends(RolesRequired('direccion', 'coordinador', 'profesor'))):
    """
    Valida que los datos del curso estén completos para generar un Registro Escolar.
    Detecta nivel automáticamente (primaria/secundaria) y llama al validador correcto.
    
    Devuelve: {valid: bool, errors: [], warnings: [], info: {...}}

    Permisos: cualquier docente del colegio (la seguridad multitenant
    impide validar cursos de otros colegios).
    """
    from registro_validator import validar_registro_secundaria, validar_registro_primaria, _normalizar_nivel
    
    curso = db.query(Curso).filter_by(id=curso_id, colegio_id=current_user.colegio_id).first()
    if not curso:
        return JSONResponse({'error': 'Curso no encontrado'}, status_code=404)
    
    grado = curso.grado
    nivel = _normalizar_nivel(grado.nivel if grado else None)
    
    if nivel == 'primaria':
        resultado = validar_registro_primaria(db, curso_id, current_user.colegio_id)
    else:
        resultado = validar_registro_secundaria(db, curso_id, current_user.colegio_id)
    
    return resultado.to_dict()


@app.get("/api/registros/preview/{curso_id}")
async def preview_registro_v2(curso_id: int, request: Request, db: Session = Depends(get_db),
                               current_user: Usuario = Depends(RolesRequired('direccion', 'coordinador', 'profesor'))):
    """
    Preview completo del JSON que irá al PDF.
    Usado para debugging y auditoría antes de generar el documento.

    Permisos: cualquier docente del colegio (la seguridad multitenant
    impide ver cursos de otros colegios).
    """
    from registro_validator import validar_registro_secundaria, _normalizar_nivel, _extraer_grado_numero
    
    curso = db.query(Curso).filter_by(id=curso_id, colegio_id=current_user.colegio_id).first()
    if not curso:
        return JSONResponse({'error': 'Curso no encontrado'}, status_code=404)
    
    grado = curso.grado
    nivel = _normalizar_nivel(grado.nivel if grado else None)
    
    # Correr validación para incluirla en preview
    if nivel == 'primaria':
        from registro_validator import validar_registro_primaria
        validacion = validar_registro_primaria(db, curso_id, current_user.colegio_id)
    else:
        validacion = validar_registro_secundaria(db, curso_id, current_user.colegio_id)
    
    config = tenant_filter(db.query(ConfiguracionColegio), ConfiguracionColegio, current_user).first()
    ano = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    
    grado_numero = _extraer_grado_numero(grado.nombre) if grado else 1
    
    # Profesor titular del curso
    titular_info = None
    if validacion.info.get('titular_id'):
        titular_info = {
            'id': validacion.info['titular_id'],
            'nombre_completo': validacion.info['titular_nombre']
        }
    
    # Estudiantes
    estudiantes_db = tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(
        curso_id=curso_id, activo=True
    ).order_by(Estudiante.no_lista).all()
    estudiantes = [{
        'id': e.id,
        'no_lista': e.no_lista or idx + 1,
        'nombre_completo': e.nombre_completo,
        'sexo': e.sexo,
        'fecha_nacimiento': e.fecha_nacimiento.isoformat() if e.fecha_nacimiento else None,
        'matricula': e.matricula,
    } for idx, e in enumerate(estudiantes_db)]
    
    # Asignaciones y conteo de calificaciones
    asignaciones = tenant_filter(db.query(AsignacionProfesor), AsignacionProfesor, current_user).filter_by(
        curso_id=curso_id, activo=True
    ).all()
    
    asignaturas_info = []
    for asig in asignaciones:
        asignatura_obj = db.query(Asignatura).filter_by(id=asig.asignatura_id, colegio_id=current_user.colegio_id).first()
        profesor_obj = db.query(Usuario).filter_by(id=asig.profesor_id, colegio_id=current_user.colegio_id).first()
        
        # Contar calificaciones registradas
        califs_count = 0
        if nivel == 'secundaria':
            califs_count = tenant_filter(db.query(Calificacion), Calificacion, current_user).filter(
                Calificacion.asignatura_id == asig.asignatura_id,
                Calificacion.estudiante_id.in_([e.id for e in estudiantes_db])
            ).count()
        else:
            califs_count = tenant_filter(db.query(CalificacionPrimaria), CalificacionPrimaria, current_user).filter(
                CalificacionPrimaria.asignatura_id == asig.asignatura_id,
                CalificacionPrimaria.estudiante_id.in_([e.id for e in estudiantes_db])
            ).count()
        
        asignaturas_info.append({
            'asignatura_id': asig.asignatura_id,
            'asignatura_nombre': asignatura_obj.nombre if asignatura_obj else '?',
            'profesor_id': asig.profesor_id,
            'profesor_nombre': profesor_obj.nombre_completo if profesor_obj else '?',
            'es_titular': asig.es_titular,
            'calificaciones_registradas': califs_count,
            'estudiantes_del_curso': len(estudiantes_db),
            'falta_por_calificar': len(estudiantes_db) - califs_count,
        })
    
    # Asistencia total
    total_asist = tenant_filter(db.query(Asistencia), Asistencia, current_user).filter(
        Asistencia.estudiante_id.in_([e.id for e in estudiantes_db])
    ).count()
    
    # Matriz real de asistencia por mes (estructura MINERD)
    from registro_asistencia import build_asistencia_registro, debug_render_asistencia
    matriz_asistencia = build_asistencia_registro(db, curso_id, estudiantes=estudiantes_db)
    debug_asistencia = debug_render_asistencia(matriz_asistencia)
    
    # Días trabajados configurados
    dias_trabajados = ano.get_dias_trabajados() if ano else {}
    
    return {
        'validacion': validacion.to_dict(),
        'nivel': nivel,
        'grado_numero': grado_numero,
        'curso': {
            'id': curso.id,
            'nombre_completo': curso.nombre_completo,
            'grado': grado.nombre if grado else None,
            'seccion': curso.nombre,
            'tanda': curso.tanda.nombre if curso.tanda else None,
        },
        'ano_escolar': {
            'id': ano.id if ano else None,
            'nombre': ano.nombre if ano else None,
            'fecha_inicio': ano.fecha_inicio.isoformat() if ano and ano.fecha_inicio else None,
            'fecha_fin': ano.fecha_fin.isoformat() if ano and ano.fecha_fin else None,
            'periodo_activo': ano.periodo_activo if ano else None,
            'dias_trabajados': dias_trabajados,
        },
        'centro': {
            'nombre': config.nombre if config else None,
            'regional': getattr(config, 'regional', None) if config else None,
            'distrito': getattr(config, 'distrito', None) if config else None,
            'codigo_centro': getattr(config, 'codigo_centro', None) if config else None,
            'codigo_cartografia': getattr(config, 'codigo_cartografia', None) if config else None,
            'direccion': getattr(config, 'direccion', None) if config else None,
            'telefono': getattr(config, 'telefono', None) if config else None,
            'email': getattr(config, 'email', None) if config else None,
        },
        'director_grupo': titular_info,
        'estudiantes': {
            'total': len(estudiantes),
            'lista': estudiantes,
        },
        'asignaturas': asignaturas_info,
        'asistencia': {
            'total_registros': total_asist,
            'matriz_por_mes': matriz_asistencia,
            'debug_texto': debug_asistencia,
            'meses_con_registro': len(matriz_asistencia),
        },
        'resumen': {
            'curso_listo_para_generar': validacion.is_valid and len(validacion.warnings) == 0,
            'estudiantes': len(estudiantes),
            'asignaturas_configuradas': len(asignaturas_info),
            'asignaturas_con_faltantes': sum(1 for a in asignaturas_info if a['falta_por_calificar'] > 0),
            'dias_trabajados_configurados_total': validacion.info.get('dias_trabajados_configurados_total', 0),
            'meses_asistencia_detectados': len(matriz_asistencia),
        }
    }


@app.post("/api/registros/dias-trabajados/{ano_id}")
async def guardar_dias_trabajados(ano_id: int, request: Request, db: Session = Depends(get_db),
                                   current_user: Usuario = Depends(RolesRequired('direccion'))):
    """
    Guarda los días trabajados por mes del año escolar.
    Body: {"dias": {"ago": 8, "sep": 22, "oct": 22, "nov": 20, "dic": 10, 
                    "ene": 15, "feb": 20, "mar": 22, "abr": 20, "may": 22, "jun": 15}}
    """
    ano = db.query(AnoEscolar).filter_by(id=ano_id, colegio_id=current_user.colegio_id).first()
    if not ano:
        return JSONResponse({'error': 'Año escolar no encontrado'}, status_code=404)
    
    data = await request.json()
    dias = data.get('dias') or data  # acepta ambos formatos
    
    if not isinstance(dias, dict):
        return JSONResponse({'error': 'Formato inválido. Se esperaba {"dias": {...}} o {...}'}, status_code=400)
    
    # Validar valores: solo enteros 0-31
    for mes, cnt in dias.items():
        try:
            cnt_int = int(cnt)
            if cnt_int < 0 or cnt_int > 31:
                return JSONResponse({'error': f'Días inválidos para {mes}: {cnt}. Debe ser 0-31'}, status_code=400)
        except (ValueError, TypeError):
            return JSONResponse({'error': f'Días inválidos para {mes}: {cnt}'}, status_code=400)
    
    # Normalizar (llaves en minúsculas, valores en int)
    dias_norm = {str(k).lower().strip(): int(v) for k, v in dias.items()}
    ano.set_dias_trabajados(dias_norm)
    db.commit()
    
    log_auditoria(db, 'GUARDAR_DIAS_TRABAJADOS', 'ano_escolar', ano.id,
                 datos_nuevos=dias_norm, user=current_user, request=request)
    
    return {'message': 'Días trabajados guardados', 'dias_trabajados': dias_norm}


@app.get("/api/registros/dias-trabajados/{ano_id}")
async def get_dias_trabajados(ano_id: int, db: Session = Depends(get_db),
                               current_user: Usuario = Depends(get_current_user)):
    """Obtiene los días trabajados configurados del año escolar."""
    ano = db.query(AnoEscolar).filter_by(id=ano_id, colegio_id=current_user.colegio_id).first()
    if not ano:
        return JSONResponse({'error': 'Año escolar no encontrado'}, status_code=404)
    return {'ano_id': ano.id, 'dias_trabajados': ano.get_dias_trabajados()}


@app.get("/api/registros/primaria/{curso_id}/preview-pdf")
async def preview_pdf_primaria(curso_id: int, request: Request,
                                db: Session = Depends(get_db),
                                current_user: Usuario = Depends(RolesRequired('direccion', 'coordinador'))):
    """
    Vista previa del PDF de primaria con marca de agua BORRADOR.
    Genera SIEMPRE, ignorando errores y warnings.
    """
    from registro_validator import validar_registro_primaria, _extraer_grado_numero
    from registro_primaria import generar_registro_primaria_desde_sistema
    from registro_borrador import aplicar_marca_borrador
    
    validacion = validar_registro_primaria(db, curso_id, current_user.colegio_id)
    
    curso = db.query(Curso).filter_by(id=curso_id, colegio_id=current_user.colegio_id).first()
    if not curso:
        return JSONResponse({'error': 'Curso no encontrado'}, status_code=404)
    
    grado = curso.grado
    if not grado:
        return JSONResponse({'error': 'El curso no tiene grado asignado'}, status_code=400)
    
    config = tenant_filter(db.query(ConfiguracionColegio), ConfiguracionColegio, current_user).first()
    ano = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    
    grado_numero = validacion.info.get('grado_numero') or _extraer_grado_numero(grado.nombre)
    if grado_numero < 1 or grado_numero > 6:
        return JSONResponse({'error': 'Grado fuera de rango (1-6)'}, status_code=400)
    
    titular_nombre = validacion.info.get('titular_nombre', '(SIN PROFESOR TITULAR)')
    
    colegio_info = {
        'nombre': (config.nombre if config else None) or '(SIN CENTRO)',
        'regional': getattr(config, 'regional', '') or '',
        'distrito': getattr(config, 'distrito', '') or '',
        'codigo_centro': getattr(config, 'codigo_centro', '') or '',
        'codigo_cartografia': getattr(config, 'codigo_cartografia', '') or '',
        'direccion': getattr(config, 'direccion', '') or '',
        'telefono': getattr(config, 'telefono', '') or '',
        'director': getattr(config, 'nombre_director', '') or '',
        'docente_titular': titular_nombre,
    }
    
    curso_info = {
        'grado': grado.nombre,
        'seccion': curso.nombre or 'A',
        'tanda': curso.tanda.nombre if curso.tanda else '',
    }
    
    ano_escolar = ano.nombre if ano else f"{date.today().year}-{date.today().year + 1}"
    dias_trabajados = ano.get_dias_trabajados() if ano else {}
    
    estudiantes_db = tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(
        curso_id=curso_id, activo=True
    ).order_by(Estudiante.no_lista).all()
    
    estudiantes_raw = [{
        'id': e.id,
        'no_lista': e.no_lista or idx + 1,
        'nombre': e.nombre_completo,
        'sexo': e.sexo or '',
        'fecha_nacimiento': e.fecha_nacimiento,
        'matricula': e.matricula or '',
    } for idx, e in enumerate(estudiantes_db[:40])]
    
    # Cargar calificaciones primaria por área
    asignaciones = tenant_filter(db.query(AsignacionProfesor), AsignacionProfesor, current_user).filter_by(
        curso_id=curso_id, activo=True
    ).all()
    
    calificaciones_por_area = {}
    for asig in asignaciones:
        asignatura = db.query(Asignatura).filter_by(id=asig.asignatura_id, colegio_id=current_user.colegio_id).first()
        if not asignatura:
            continue
        area_data = {}
        for idx, est in enumerate(estudiantes_db[:40]):
            competencias = {}
            for comp_num in [1, 2, 3]:
                calif = tenant_filter(db.query(CalificacionPrimaria), CalificacionPrimaria, current_user).filter_by(
                    estudiante_id=est.id, asignatura_id=asig.asignatura_id, competencia_numero=comp_num
                ).first()
                if calif:
                    fc = calif.final_competencia
                    if fc is None:
                        valores = [calif.p1, calif.p2, calif.p3, calif.p4]
                        validos = [v for v in valores if v is not None]
                        if validos:
                            fc = round(sum(validos) / len(validos), 2)
                    competencias[comp_num] = {
                        'p1': calif.p1, 'p2': calif.p2, 'p3': calif.p3, 'p4': calif.p4,
                        'rp1': calif.rp1, 'rp2': calif.rp2, 'rp3': calif.rp3, 'rp4': calif.rp4,
                        'final_competencia': fc,
                    }
            if competencias:
                area_data[idx] = competencias
        if area_data:
            calificaciones_por_area[asignatura.nombre] = area_data
    
    # Asistencia
    from registro_asistencia import build_asistencia_registro
    asistencia = build_asistencia_registro(db, curso_id, estudiantes=estudiantes_db[:40])
    
    try:
        pdf_bytes = generar_registro_primaria_desde_sistema(
            colegio_info, curso_info, ano_escolar,
            estudiantes_raw, calificaciones_por_area, asistencia,
            dias_trabajados, grado_numero
        )
        pdf_bytes = aplicar_marca_borrador(pdf_bytes)
        
        filename = f"BORRADOR_Registro_Primaria_{curso.nombre_completo.replace(' ', '_')}.pdf"
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type='application/pdf',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        import traceback
        logger.error(f"Error preview primaria: {e}\n{traceback.format_exc()}")
        return JSONResponse({'error': 'Error generando preview', 'detalle': str(e)}, status_code=500)


@app.get("/api/registros/primaria/{curso_id}")
async def generar_registro_primaria_v2(curso_id: int, request: Request,
                                        db: Session = Depends(get_db),
                                        current_user: Usuario = Depends(RolesRequired('direccion', 'coordinador'))):
    """
    Genera el PDF del Registro Escolar MINERD para un curso de PRIMARIA.
    Estructura por competencias (C1, C2, C3).
    """
    from registro_validator import validar_registro_primaria
    from registro_primaria import generar_registro_primaria_desde_sistema
    
    force = request.query_params.get('force', 'false').lower() == 'true'
    
    validacion = validar_registro_primaria(db, curso_id, current_user.colegio_id)
    
    if not validacion.is_valid:
        return JSONResponse({
            'error': 'Datos incompletos o inconsistentes',
            'detalle': validacion.errors,
            'warnings': validacion.warnings,
            'sugerencia': 'Corrija los errores antes de generar el registro.'
        }, status_code=400)
    
    if validacion.warnings and not force:
        return JSONResponse({
            'error': 'Advertencias detectadas',
            'detalle': validacion.warnings,
            'sugerencia': 'Use ?force=true para ignorar advertencias.',
            'validacion': validacion.to_dict(),
        }, status_code=409)
    
    curso = db.query(Curso).filter_by(id=curso_id).first()
    grado = curso.grado
    config = tenant_filter(db.query(ConfiguracionColegio), ConfiguracionColegio, current_user).first()
    ano = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    
    grado_numero = validacion.info['grado_numero']
    titular_nombre = validacion.info.get('titular_nombre', '')
    
    colegio_info = {
        'nombre': config.nombre if config else 'Centro Educativo',
        'regional': getattr(config, 'regional', '') or '',
        'distrito': getattr(config, 'distrito', '') or '',
        'codigo_centro': getattr(config, 'codigo_centro', '') or '',
        'codigo_cartografia': getattr(config, 'codigo_cartografia', '') or '',
        'direccion': getattr(config, 'direccion', '') or '',
        'telefono': getattr(config, 'telefono', '') or '',
        'director': getattr(config, 'nombre_director', '') or '',
        'docente_titular': titular_nombre,
    }
    
    curso_info = {
        'grado': grado.nombre,
        'seccion': curso.nombre or 'A',
        'tanda': curso.tanda.nombre if curso.tanda else '',
    }
    
    ano_escolar = ano.nombre if ano else f"{date.today().year}-{date.today().year + 1}"
    dias_trabajados = ano.get_dias_trabajados() if ano else {}
    
    estudiantes_db = tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(
        curso_id=curso_id, activo=True
    ).order_by(Estudiante.no_lista).all()
    
    estudiantes_raw = [{
        'id': e.id,
        'no_lista': e.no_lista or idx + 1,
        'nombre': e.nombre_completo,
        'sexo': e.sexo or '',
        'fecha_nacimiento': e.fecha_nacimiento,
        'matricula': e.matricula or '',
    } for idx, e in enumerate(estudiantes_db[:40])]
    
    # Cargar calificaciones por área por competencia
    asignaciones = tenant_filter(db.query(AsignacionProfesor), AsignacionProfesor, current_user).filter_by(
        curso_id=curso_id, activo=True
    ).all()
    
    calificaciones_por_area = {}
    for asig in asignaciones:
        asignatura = db.query(Asignatura).filter_by(id=asig.asignatura_id, colegio_id=current_user.colegio_id).first()
        if not asignatura:
            continue
        
        area_data = {}
        for idx, est in enumerate(estudiantes_db[:40]):
            competencias = {}
            for comp_num in [1, 2, 3]:
                calif = tenant_filter(db.query(CalificacionPrimaria), CalificacionPrimaria, current_user).filter_by(
                    estudiante_id=est.id, asignatura_id=asig.asignatura_id, competencia_numero=comp_num
                ).first()
                if calif:
                    # Calcular final_competencia si es NULL
                    fc = calif.final_competencia
                    if fc is None:
                        valores = [calif.p1, calif.p2, calif.p3, calif.p4]
                        validos = [v for v in valores if v is not None]
                        if validos:
                            fc = round(sum(validos) / len(validos), 2)
                    competencias[comp_num] = {
                        'p1': calif.p1, 'p2': calif.p2, 'p3': calif.p3, 'p4': calif.p4,
                        'rp1': calif.rp1, 'rp2': calif.rp2, 'rp3': calif.rp3, 'rp4': calif.rp4,
                        'final_competencia': fc,
                    }
            if competencias:
                area_data[idx] = competencias
        
        if area_data:
            calificaciones_por_area[asignatura.nombre] = area_data
    
    from registro_asistencia import build_asistencia_registro
    asistencia_por_mes = build_asistencia_registro(db, curso_id, estudiantes=estudiantes_db[:40])
    
    try:
        pdf_bytes = generar_registro_primaria_desde_sistema(
            colegio_info, curso_info, ano_escolar,
            estudiantes_raw, calificaciones_por_area, asistencia_por_mes,
            dias_trabajados, grado_numero
        )
        
        filename = f"Registro_Primaria_{curso.nombre_completo.replace(' ', '_')}_{ano_escolar}.pdf"
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type='application/pdf',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        import traceback
        logger.error(f"Error generando registro primaria: {e}\n{traceback.format_exc()}")
        return JSONResponse({
            'error': 'Error generando el PDF de primaria',
            'detalle': str(e),
            'validacion': validacion.to_dict(),
        }, status_code=500)


@app.get("/api/registros/secundaria/{curso_id}/preview-pdf")
async def preview_pdf_secundaria(curso_id: int, request: Request,
                                  db: Session = Depends(get_db),
                                  current_user: Usuario = Depends(RolesRequired('direccion', 'coordinador', 'profesor'))):
    """
    Vista previa del PDF de secundaria con marca de agua BORRADOR.
    Genera SIEMPRE, ignorando errores y warnings — para que el director
    pueda ir verificando avance durante el año escolar.
    
    NUNCA usar este PDF para entrega oficial.

    Permisos: dirección/coordinador/profesor del colegio. La seguridad
    multitenant (filtro por colegio_id) impide ver cursos de otros colegios.
    Los profesores ven el registro completo del curso (incluidas materias
    de otros), pero solo pueden MODIFICAR sus propias materias en los
    endpoints de carga de notas — esto refleja la práctica real del MINERD
    donde el registro es un documento compartido del curso.
    """
    from registro_validator import validar_registro_secundaria
    from registro_escolar import generar_registro_desde_sistema
    from registro_borrador import aplicar_marca_borrador

    # Validar para incluir info, pero NO bloquear
    validacion = validar_registro_secundaria(db, curso_id, current_user.colegio_id)
    
    curso = db.query(Curso).filter_by(id=curso_id, colegio_id=current_user.colegio_id).first()
    if not curso:
        return JSONResponse({'error': 'Curso no encontrado'}, status_code=404)
    
    grado = curso.grado
    if not grado:
        return JSONResponse({'error': 'El curso no tiene grado asignado'}, status_code=400)
    
    config = tenant_filter(db.query(ConfiguracionColegio), ConfiguracionColegio, current_user).first()
    ano = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    
    # Obtener grado_numero (con fallback si validación falló)
    grado_numero = validacion.info.get('grado_numero')
    if not grado_numero:
        from registro_validator import _extraer_grado_numero
        grado_numero = _extraer_grado_numero(grado.nombre)
    
    if grado_numero < 1 or grado_numero > 6:
        return JSONResponse({'error': 'Grado fuera de rango (1-6) para preview'}, status_code=400)
    
    # Cargar datos (con tolerancia a campos faltantes)
    titular_nombre = validacion.info.get('titular_nombre', '(SIN PROFESOR TITULAR)')
    
    colegio_info = {
        'nombre': (config.nombre if config else None) or '(SIN CENTRO)',
        'regional': getattr(config, 'regional', '') or '',
        'distrito': getattr(config, 'distrito', '') or '',
        'direccion': getattr(config, 'direccion', '') or '',
        'telefono': getattr(config, 'telefono', '') or '',
        'email': getattr(config, 'email', '') or '',
        'director': getattr(config, 'nombre_director', '') or getattr(config, 'director', '') or '',
        'codigo_centro': getattr(config, 'codigo_centro', '') or '',
        'codigo_cartografia': getattr(config, 'codigo_cartografia', '') or '',
        'sector': getattr(config, 'sector', '') or '',
        'zona': getattr(config, 'zona', '') or '',
        'jornada': getattr(config, 'tanda_operacion', '') or '',
        'coordinador': titular_nombre,
    }
    
    curso_info = {
        'grado': grado.nombre,
        'seccion': curso.nombre or 'A',
        'tanda': curso.tanda.nombre if curso.tanda else '',
    }
    
    ano_escolar = ano.nombre if ano else f"{date.today().year}-{date.today().year + 1}"
    
    estudiantes_db = tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(
        curso_id=curso_id, activo=True
    ).order_by(Estudiante.no_lista).all()
    
    estudiantes_raw = [{
        'id': e.id,
        'no_lista': e.no_lista or idx + 1,
        'nombre': e.nombre_completo,
        'sexo': e.sexo or '',
        'fecha_nacimiento': e.fecha_nacimiento,
        'cedula': getattr(e, 'cedula', '') or e.matricula or '',
        'matricula': e.matricula or '',
        'lugar_nacimiento': getattr(e, 'lugar_nacimiento', '') or '',
        'nacionalidad': getattr(e, 'nacionalidad', '') or '',
        'direccion': e.direccion or '',
        'condicion_entrada': getattr(e, 'condicion_entrada', 'nuevo') or 'nuevo',
    } for idx, e in enumerate(estudiantes_db[:40])]
    
    asignaturas_data = _cargar_datos_asignaturas_secundaria(
        db, current_user, curso_id, grado_numero, estudiantes_db[:40]
    )
    
    try:
        pdf_bytes = generar_registro_desde_sistema(
            colegio_info, curso_info, ano_escolar,
            estudiantes_raw, asignaturas_data, grado_numero
        )
        # Aplicar marca de agua BORRADOR
        pdf_bytes = aplicar_marca_borrador(pdf_bytes)
        
        filename = f"BORRADOR_Registro_Secundaria_{curso.nombre_completo.replace(' ', '_')}.pdf"
        
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type='application/pdf',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        import traceback
        logger.error(f"Error preview secundaria: {e}\n{traceback.format_exc()}")
        return JSONResponse({
            'error': 'Error generando vista previa',
            'detalle': str(e),
        }, status_code=500)


@app.get("/api/registros/secundaria/{curso_id}")
async def generar_registro_secundaria_v2(curso_id: int, request: Request, 
                                          db: Session = Depends(get_db),
                                          current_user: Usuario = Depends(RolesRequired('direccion', 'coordinador'))):
    """
    Genera el PDF del Registro Escolar MINERD para un curso de SECUNDARIA.
    
    Flujo:
    1. Valida datos (bloquea si hay errores críticos)
    2. Puede ignorarse advertencias con ?force=true
    3. Usa profesor titular del curso (no coordinador del colegio)
    4. Usa días trabajados configurados
    """
    from registro_validator import validar_registro_secundaria
    from registro_escolar import generar_registro_desde_sistema, get_asignaturas_por_grado
    
    force = request.query_params.get('force', 'false').lower() == 'true'
    
    # === 1. VALIDAR ===
    validacion = validar_registro_secundaria(db, curso_id, current_user.colegio_id)
    
    if not validacion.is_valid:
        return JSONResponse({
            'error': 'Datos incompletos o inconsistentes',
            'detalle': validacion.errors,
            'warnings': validacion.warnings,
            'sugerencia': 'Corrija los errores listados antes de generar el registro.'
        }, status_code=400)
    
    if validacion.warnings and not force:
        return JSONResponse({
            'error': 'Advertencias detectadas',
            'detalle': validacion.warnings,
            'sugerencia': 'Puede forzar la generación agregando ?force=true a la URL si desea ignorar estas advertencias.',
            'validacion': validacion.to_dict(),
        }, status_code=409)
    
    # === 2. CARGAR DATOS ===
    curso = db.query(Curso).filter_by(id=curso_id).first()
    grado = curso.grado
    config = tenant_filter(db.query(ConfiguracionColegio), ConfiguracionColegio, current_user).first()
    ano = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    
    grado_numero = validacion.info['grado_numero']
    
    # Profesor titular del curso (NO coordinador del colegio)
    titular_nombre = validacion.info.get('titular_nombre', '')
    
    # Info del colegio
    colegio_info = {
        'nombre': config.nombre if config else 'Centro Educativo',
        'regional': getattr(config, 'regional', '') or '',
        'distrito': getattr(config, 'distrito', '') or '',
        'direccion': getattr(config, 'direccion', '') or '',
        'telefono': getattr(config, 'telefono', '') or '',
        'email': getattr(config, 'email', '') or '',
        'director': getattr(config, 'nombre_director', '') or getattr(config, 'director', '') or '',
        'correo_director': getattr(config, 'correo_director', '') or '',
        'telefono_director': getattr(config, 'telefono_director', '') or '',
        'codigo_centro': getattr(config, 'codigo_centro', '') or '',
        'codigo_cartografia': getattr(config, 'codigo_cartografia', '') or '',
        'sector': getattr(config, 'sector', '') or '',
        'zona': getattr(config, 'zona', '') or '',
        'tanda_operacion': getattr(config, 'tanda_operacion', '') or '',
        # CLAVE: Usar profesor titular, no coordinador
        'coordinador': titular_nombre,
    }
    
    curso_info = {
        'grado': grado.nombre,
        'seccion': curso.nombre or 'A',
        'tanda': curso.tanda.nombre if curso.tanda else '',
    }
    
    ano_escolar = ano.nombre if ano else f"{date.today().year}-{date.today().year + 1}"
    
    # Estudiantes del curso (máximo 40)
    estudiantes_db = tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(
        curso_id=curso_id, activo=True
    ).order_by(Estudiante.no_lista).all()
    
    estudiantes_raw = [{
        'id': e.id,
        'no_lista': e.no_lista or idx + 1,
        'nombre': e.nombre_completo,
        'sexo': e.sexo or '',
        'fecha_nacimiento': e.fecha_nacimiento,
        'cedula': getattr(e, 'cedula', '') or e.matricula or '',
        'matricula': e.matricula or '',
        'lugar_nacimiento': getattr(e, 'lugar_nacimiento', '') or '',
        'nacionalidad': getattr(e, 'nacionalidad', '') or '',
        'direccion': e.direccion or '',
        'condicion_entrada': getattr(e, 'condicion_entrada', 'nuevo') or 'nuevo',
    } for idx, e in enumerate(estudiantes_db[:40])]
    
    # Cargar asignaturas, profesores, calificaciones, asistencias
    asignaturas_data = _cargar_datos_asignaturas_secundaria(
        db, current_user, curso_id, grado_numero, estudiantes_db[:40]
    )
    
    # === 3. GENERAR PDF ===
    try:
        pdf_bytes = generar_registro_desde_sistema(
            colegio_info, curso_info, ano_escolar,
            estudiantes_raw, asignaturas_data, grado_numero
        )
        
        filename = f"Registro_Escolar_{curso.nombre_completo.replace(' ', '_')}_{ano_escolar}.pdf"
        
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type='application/pdf',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        import traceback
        logger.error(f"Error generando registro secundaria: {e}\n{traceback.format_exc()}")
        return JSONResponse({
            'error': 'Error generando el PDF',
            'detalle': str(e),
            'validacion': validacion.to_dict(),
        }, status_code=500)


def _cargar_datos_asignaturas_secundaria(db: Session, current_user, curso_id, grado_numero, estudiantes_db):
    """
    Helper: carga asignaturas, docentes, calificaciones y asistencia
    en el formato que espera el generador PDF.
    """
    from registro_escolar import get_asignaturas_por_grado
    from registro_asistencia import build_asistencia_registro
    
    mapeo_nombres = {
        'Lenguas Extranjeras - Inglés': ['Inglés', 'Ingles', 'English'],
        'Lenguas Extranjeras - Francés': ['Francés', 'Frances', 'French'],
        'Lengua Española': ['Lengua Española', 'Español', 'Lengua', 'Espanol'],
        'Matemática': ['Matemática', 'Matematica', 'Matemáticas', 'Matematicas'],
        'Ciencias Sociales': ['Ciencias Sociales', 'Sociales', 'Historia'],
        'Ciencias de la Naturaleza': ['Ciencias de la Naturaleza', 'Ciencias Naturales', 'Naturales'],
        'Educación Física': ['Educación Física', 'Educacion Fisica', 'Ed. Física', 'Física'],
        'Educación Artística': ['Educación Artística', 'Educacion Artistica', 'Arte', 'Artística'],
        'Formación Integral Humana y Religiosa': ['Formación Humana', 'Religión', 'FIHR', 'Valores', 'FHR'],
        'Salida Optativa': ['Salida Optativa', 'Optativa', 'Electiva'],
    }
    
    meses_map = {8: 0, 9: 0, 10: 1, 11: 1, 12: 2, 1: 2, 2: 3, 3: 3, 4: 4, 5: 4, 6: 5}
    
    asignaturas_data = {}
    asignaturas_minerd = get_asignaturas_por_grado(grado_numero)
    
    # ─── Helper de normalización: ignora tildes, mayúsculas y espacios extras ───
    def _norm(s: str) -> str:
        import unicodedata, re as _re
        s = unicodedata.normalize('NFD', s or '')
        s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')  # quita tildes
        s = _re.sub(r'\s+', ' ', s).strip().lower()
        return s
    
    # ─── Pre-cargar asignaturas del colegio y las que tienen asignación al curso ───
    asigs_colegio = tenant_filter(
        db.query(Asignatura), Asignatura, current_user
    ).all()
    
    asigs_con_asignacion = set()
    for a in asigs_colegio:
        tiene = tenant_filter(
            db.query(AsignacionProfesor), AsignacionProfesor, current_user
        ).filter_by(curso_id=curso_id, asignatura_id=a.id, activo=True).first()
        if tiene:
            asigs_con_asignacion.add(a.id)
    
    def _resolver_asignatura(nombre_minerd: str):
        """
        Busca la Asignatura del colegio que mejor matchea el nombre MINERD.
        Prioriza:
          1. Match exacto (normalizado) sobre asignatura asignada al curso.
          2. Match exacto (normalizado) sobre cualquier asignatura del colegio.
          3. Match por palabra clave del mapeo, asignada al curso.
          4. Match por palabra clave del mapeo, cualquier asignatura del colegio.
        Si dos candidatas empatan, gana la que tiene asignación al curso.
        Esto evita que asignaturas huérfanas duplicadas (creadas por seed o
        migraciones viejas) sin asignaciones ganen sobre la asignatura real.
        """
        target = _norm(nombre_minerd)
        terminos = [nombre_minerd] + mapeo_nombres.get(nombre_minerd, [])
        terminos_norm = [_norm(t) for t in terminos]
        
        # Candidatas asignadas al curso primero, luego huérfanas del colegio
        ordenadas = sorted(
            asigs_colegio,
            key=lambda a: (0 if a.id in asigs_con_asignacion else 1, a.id)
        )
        
        # Pase 1: match exacto (normalizado)
        for cand in ordenadas:
            n = _norm(cand.nombre)
            if n == target or n in terminos_norm:
                return cand
        
        # Pase 2: contiene término del mapeo
        for cand in ordenadas:
            n = _norm(cand.nombre)
            for t in terminos_norm:
                if t and (t in n or n in t):
                    return cand
        
        return None
    
    for asig_key, asig_nombre in asignaturas_minerd:
        asignatura = _resolver_asignatura(asig_nombre)
        
        docente_nombre = 'Sin asignar'
        if asignatura:
            asig_prof = tenant_filter(db.query(AsignacionProfesor), AsignacionProfesor, current_user).filter_by(
                curso_id=curso_id, asignatura_id=asignatura.id, activo=True
            ).first()
            if asig_prof and asig_prof.profesor:
                docente_nombre = asig_prof.profesor.nombre_completo
        
        # Calificaciones
        # MINERD: PC del período aparece SOLO cuando los 4 parciales están completos.
        # CF aparece SOLO cuando los 4 PC están completos.
        # Confiamos en la lógica de Calificacion.calcular_pc / calcular_cf del modelo,
        # que retorna None si faltan datos (no hay fallbacks que inventen promedios).
        calificaciones = {}
        if asignatura:
            for idx, est in enumerate(estudiantes_db):
                calif = tenant_filter(db.query(Calificacion), Calificacion, current_user).filter_by(
                    estudiante_id=est.id, asignatura_id=asignatura.id
                ).first()
                if calif:
                    # PC: usar valor persistido; si está NULL, recalcular con la lógica
                    # oficial del modelo (que retorna None si faltan parciales).
                    pc1 = calif.pc1 if calif.pc1 is not None else calif.calcular_pc(1)
                    pc2 = calif.pc2 if calif.pc2 is not None else calif.calcular_pc(2)
                    pc3 = calif.pc3 if calif.pc3 is not None else calif.calcular_pc(3)
                    pc4 = calif.pc4 if calif.pc4 is not None else calif.calcular_pc(4)
                    
                    # CF: usar valor persistido; si está NULL, recalcular sólo si los
                    # 4 PC están completos (calcular_cf retorna None en caso contrario).
                    cf = calif.cf
                    if cf is None and all(p is not None for p in (pc1, pc2, pc3, pc4)):
                        cf = round((pc1 + pc2 + pc3 + pc4) / 4, 2)
                    
                    calificaciones[idx] = {
                        'rp1': calif.rp1,
                        'rp2': calif.rp2,
                        'rp3': calif.rp3,
                        'rp4': calif.rp4,
                        'pc1': pc1, 'pc2': pc2, 'pc3': pc3, 'pc4': pc4,
                        'cf': cf,
                    }
        
        # Asistencia por materia
        asistencias_por_est = {}
        if asignatura:
            for idx, est in enumerate(estudiantes_db):
                registros = tenant_filter(db.query(Asistencia), Asistencia, current_user).filter_by(
                    estudiante_id=est.id, asignatura_id=asignatura.id
                ).all()
                
                est_asist = {}
                for r in registros:
                    mes = r.fecha.month
                    dia = r.fecha.day
                    mes_idx = meses_map.get(mes, 0)
                    if mes_idx not in est_asist:
                        est_asist[mes_idx] = {}
                    estado_char = (
                        'P' if r.estado == 'presente' else
                        'A' if r.estado == 'ausente' else
                        'T' if r.estado == 'tardanza' else
                        'E' if r.estado == 'excusa' else ''
                    )
                    est_asist[mes_idx][dia] = estado_char
                
                asistencias_por_est[idx] = est_asist
        
        asignaturas_data[asig_nombre] = {
            'docente': docente_nombre,
            'asistencias': asistencias_por_est,
            'asistencia_matriz': build_asistencia_registro(
                db,
                curso_id,
                asignatura_id=asignatura.id if asignatura else None,
                estudiantes=estudiantes_db,
            ) if asignatura else [],
            'calificaciones': calificaciones,
        }
    
    return asignaturas_data




@app.get("/api/registro-escolar/generar/{curso_id}")
async def generar_registro_escolar(curso_id, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired("direccion", "coordinador", "profesor"))):
    """
    Genera el Registro Escolar MINERD para un curso.
    Incluye: Asistencia por materia, días trabajados, calificaciones.
    Profesor: solo cursos donde tiene asignación.
    """
    from registro_escolar import get_asignaturas_por_grado
    
    # Validar tenant: el curso debe ser del colegio del usuario
    curso = get_tenant_or_404(db, Curso, curso_id, current_user, name='curso')
    
    # Si es profesor: solo puede generar el registro de cursos donde tenga asignación
    if current_user.role == 'profesor':
        tiene_asignacion = (
            tenant_filter(db.query(AsignacionProfesor), AsignacionProfesor, current_user)
            .filter_by(profesor_id=current_user.id, curso_id=curso_id, activo=True)
            .first()
        )
        if not tiene_asignacion:
            return JSONResponse(
                {'error': 'No tienes asignación en este curso'},
                status_code=403
            )
    
    grado = db.get(Grado, curso.grado_id)
    config = tenant_filter(db.query(ConfiguracionColegio), ConfiguracionColegio, current_user).first()
    ano = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    
    # Info del colegio — todos los campos para el registro MINERD
    colegio_info = {
        'nombre': config.nombre if config else 'Centro Educativo',
        'regional': config.regional if config else '',
        'distrito': config.distrito if config else '',
        'direccion': config.direccion if config else '',
        'telefono': config.telefono if config else '',
        'email': config.email if config else '',
        'director': getattr(config, 'nombre_director', '') or getattr(config, 'director', '') or '',
        'cedula_director': getattr(config, 'cedula_director', '') or '',
        'correo_director': getattr(config, 'correo_director', '') or '',
        'telefono_director': getattr(config, 'telefono_director', '') or '',
        'codigo_centro': getattr(config, 'codigo_centro', '') or '',
        'codigo_cartografia': getattr(config, 'codigo_cartografia', '') or '',
        'sector': getattr(config, 'sector', '') or '',
        'zona': getattr(config, 'zona', '') or '',
        'tanda_operacion': getattr(config, 'tanda_operacion', '') or '',
        'coordinador': getattr(config, 'nombre_coordinador', '') or '',
        'correo_centro': getattr(config, 'correo_centro', '') or config.email if config else '',
    }
    
    # Info del curso
    curso_info = {
        'grado': grado.nombre if grado else curso.nombre,
        'seccion': curso.seccion or 'A',
        'tanda': curso.tanda.nombre if curso.tanda else ''
    }
    
    ano_escolar = ano.nombre if ano else f"{today_rd().year}-{today_rd().year + 1}"
    
    # Obtener estudiantes del curso — con datos completos para el registro.
    # IMPORTANTE: incluimos también los retirados. El registro escolar MINERD
    # es un documento histórico del año escolar; los estudiantes que estuvieron
    # en algún momento deben aparecer con su condición correcta.
    estudiantes_db = tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(curso_id=curso_id).order_by(Estudiante.no_lista).all()
    estudiantes = [{
        'id': e.id,
        'no_lista': e.no_lista or idx + 1,
        'nombre': e.nombre_completo,
        'sexo': e.sexo or '',
        'fecha_nacimiento': e.fecha_nacimiento,
        'cedula': getattr(e, 'cedula', '') or e.matricula or '',
        'matricula': e.matricula or '',
        'lugar_nacimiento': e.lugar_nacimiento or '',
        'nacionalidad': e.nacionalidad or '',
        'direccion': e.direccion or '',
        'condicion_entrada': getattr(e, 'condicion_entrada', 'nuevo') or 'nuevo',
        # Datos de retiro: si el estudiante está retirado, marcar en el registro
        'activo': e.activo,
        'retirado': not e.activo,
        'fecha_retiro': e.fecha_retiro.isoformat() if e.fecha_retiro else None,
        'motivo_retiro': e.motivo_retiro,
    } for idx, e in enumerate(estudiantes_db)]
    
    # Obtener número de grado
    grado_numero = 1
    if grado:
        match = re.search(r'(\d+)', grado.nombre)
        if match:
            grado_numero = int(match.group(1))
    
    # Obtener asignaturas y sus datos
    asignaturas_data = {}
    asignaturas = get_asignaturas_por_grado(grado_numero)
    
    for asig_key, asig_nombre in asignaturas:
        # Buscar asignatura en BD con múltiples estrategias mejoradas
        asignatura = None
        
        # Crear lista de términos de búsqueda
        terminos_busqueda = [asig_nombre]
        
        # Si tiene ":", agregar la parte después de los dos puntos
        if ':' in asig_nombre:
            terminos_busqueda.append(asig_nombre.split(':')[1].strip())
        
        # Agregar palabras individuales significativas (más de 4 letras)
        for palabra in asig_nombre.split():
            palabra_limpia = palabra.replace(':', '').strip()
            if len(palabra_limpia) > 4 and palabra_limpia not in ['Lenguas', 'Extranjeras']:
                terminos_busqueda.append(palabra_limpia)
        
        # Mapeo de nombres MINERD a términos de búsqueda en BD
        # Las constantes MINERD usan guión: "Lenguas Extranjeras - Inglés"
        # La BD puede tener: "Inglés", "Lengua Española", "Ciencias Naturales", etc.
        mapeo_nombres = {
            'Lenguas Extranjeras - Inglés': ['Inglés', 'Ingles', 'English', 'Lenguas Extranjeras: Inglés'],
            'Lenguas Extranjeras: Inglés': ['Inglés', 'Ingles', 'English', 'Lenguas Extranjeras - Inglés'],
            'Lenguas Extranjeras - Francés': ['Francés', 'Frances', 'French', 'Lenguas Extranjeras: Francés'],
            'Lenguas Extranjeras: Francés': ['Francés', 'Frances', 'French', 'Lenguas Extranjeras - Francés'],
            'Lengua Española': ['Lengua Española', 'Español', 'Lengua', 'Espanol'],
            'Matemática': ['Matemática', 'Matematica', 'Matemáticas', 'Matematicas', 'Math'],
            'Ciencias Sociales': ['Ciencias Sociales', 'Sociales', 'Historia'],
            'Ciencias de la Naturaleza': ['Ciencias de la Naturaleza', 'Ciencias Naturales', 'Naturales', 'Ciencias de la naturaleza'],
            'Educación Física': ['Educación Física', 'Educacion Fisica', 'Ed. Física', 'Física', 'Ed Fisica'],
            'Educación Artística': ['Educación Artística', 'Educacion Artistica', 'Arte', 'Artística', 'Ed. Artística'],
            'Formación Integral Humana y Religiosa': ['Formación Integral Humana y Religiosa', 'Formación Humana', 'Formación', 'Religión', 'FIHR', 'Valores', 'FHR'],
            'Salida Optativa': ['Salida Optativa', 'Optativa', 'Electiva'],
            'Biología': ['Biología', 'Biologia', 'Biology'],
        }
        
        if asig_nombre in mapeo_nombres:
            terminos_busqueda.extend(mapeo_nombres[asig_nombre])
        
        # Buscar con cada término hasta encontrar
        for termino in terminos_busqueda:
            if asignatura:
                break
            # Búsqueda exacta (case insensitive)
            asignatura = tenant_filter(db.query(Asignatura), Asignatura, current_user).filter(
                func.lower(Asignatura.nombre) == termino.lower()
            ).first()
            
            # Búsqueda parcial
            if not asignatura:
                asignatura = tenant_filter(db.query(Asignatura), Asignatura, current_user).filter(
                    Asignatura.nombre.ilike(f'%{termino}%')
                ).first()
        
        # Buscar asignación de profesor
        docente_nombre = 'Sin asignar'
        if asignatura:
            asignacion = tenant_filter(db.query(AsignacionProfesor), AsignacionProfesor, current_user).filter_by(
                curso_id=curso_id,
                asignatura_id=asignatura.id,
                activo=True
            ).first()
            if asignacion and asignacion.profesor:
                docente_nombre = asignacion.profesor.nombre_completo
        
        # Obtener calificaciones (MINERD: solo consolidados PC y CF; los parciales no van al registro)
        calificaciones = {}
        if asignatura:
            for idx, est in enumerate(estudiantes_db):
                calif = tenant_filter(db.query(Calificacion), Calificacion, current_user).filter_by(
                    estudiante_id=est.id,
                    asignatura_id=asignatura.id
                ).first()
                if calif:
                    calificaciones[idx] = {
                        'rp1': calif.rp1,
                        'rp2': calif.rp2,
                        'rp3': calif.rp3,
                        'rp4': calif.rp4,
                        'pc1': calif.pc1,
                        'pc2': calif.pc2,
                        'pc3': calif.pc3,
                        'pc4': calif.pc4,
                        'cf': calif.cf,
                    }
        
        # Obtener asistencia POR MATERIA
        asistencias_por_estudiante = {}
        if asignatura:
            # Meses del año escolar
            meses_map = {
                8: 0,   # Agosto -> índice 0
                9: 0,   # Septiembre -> índice 0
                10: 1,  # Octubre -> índice 1
                11: 1,  # Noviembre -> índice 1
                12: 2,  # Diciembre -> índice 2
                1: 2,   # Enero -> índice 2
                2: 3,   # Febrero -> índice 3
                3: 3,   # Marzo -> índice 3
                4: 4,   # Abril -> índice 4
                5: 4,   # Mayo -> índice 4
                6: 5,   # Junio -> índice 5
            }
            
            for idx, est in enumerate(estudiantes_db):
                asist_records = tenant_filter(db.query(Asistencia), Asistencia, current_user).filter_by(
                    estudiante_id=est.id,
                    asignatura_id=asignatura.id
                ).all()
                
                est_asist = {}
                for record in asist_records:
                    mes = record.fecha.month
                    dia = record.fecha.day
                    mes_idx = meses_map.get(mes, 0)
                    
                    if mes_idx not in est_asist:
                        est_asist[mes_idx] = {}
                    
                    estado_char = 'P' if record.estado == 'presente' else \
                                  'A' if record.estado == 'ausente' else \
                                  'T' if record.estado == 'tardanza' else \
                                  'E' if record.estado == 'excusa' else ''
                    est_asist[mes_idx][dia] = estado_char
                
                asistencias_por_estudiante[idx] = est_asist
        
        asignaturas_data[asig_nombre] = {
            'docente': docente_nombre,
            'asistencias': asistencias_por_estudiante,
            'calificaciones': calificaciones
        }
    
    # Generar PDF
    try:
        from registro_escolar import generar_registro_desde_sistema
        
        pdf_bytes = generar_registro_desde_sistema(
            colegio_info, curso_info, ano_escolar, 
            estudiantes, asignaturas_data, grado_numero
        )
        
        # Crear nombre del archivo
        filename = f"Registro_Escolar_{curso.nombre_completo.replace(' ', '_')}_{ano_escolar}.pdf"
        
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type='application/pdf',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        logger.error(f"Error generando registro: {str(e)}")
        import traceback
        traceback.print_exc()
        return JSONResponse({'error': f'Error generando registro: {str(e)}'}, status_code=500)


@app.get("/api/registro-escolar/preview/{curso_id}")
async def preview_registro_escolar(curso_id, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion', 'coordinador', 'profesor'))):
    """
    Vista previa de los datos que irían en el registro escolar.
    Útil para verificar antes de generar el PDF.
    """
    from registro_escolar import get_asignaturas_por_grado
    
    curso = get_tenant_or_404(db, Curso, curso_id, current_user, name='curso')
    grado = db.get(Grado, curso.grado_id)
    config = tenant_filter(db.query(ConfiguracionColegio), ConfiguracionColegio, current_user).first()
    ano = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    
    # Obtener número de grado
    grado_numero = 1
    if grado:
        match = re.search(r'(\d+)', grado.nombre)
        if match:
            grado_numero = int(match.group(1))
    
    # Obtener estudiantes
    estudiantes = tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(curso_id=curso_id, activo=True).order_by(Estudiante.no_lista).all()
    
    # Obtener asignaturas MINERD
    asignaturas_minerd = get_asignaturas_por_grado(grado_numero)
    
    # Obtener asignaturas en tu base de datos
    asignaturas_bd = tenant_filter(db.query(Asignatura), Asignatura, current_user).filter_by(activo=True).all()
    asignaturas_bd_nombres = [a.nombre for a in asignaturas_bd]
    
    resumen = []
    problemas = []
    
    for asig_key, asig_nombre in asignaturas_minerd:
        # Usar la misma lógica de búsqueda mejorada
        asignatura = None
        terminos_busqueda = [asig_nombre]
        
        if ':' in asig_nombre:
            terminos_busqueda.append(asig_nombre.split(':')[1].strip())
        
        mapeo_nombres = {
            'Lenguas Extranjeras - Inglés': ['Inglés', 'Ingles', 'English', 'Lenguas Extranjeras: Inglés'],
            'Lenguas Extranjeras: Inglés': ['Inglés', 'Ingles', 'English', 'Lenguas Extranjeras - Inglés'],
            'Lenguas Extranjeras - Francés': ['Francés', 'Frances', 'French', 'Lenguas Extranjeras: Francés'],
            'Lenguas Extranjeras: Francés': ['Francés', 'Frances', 'French', 'Lenguas Extranjeras - Francés'],
            'Lengua Española': ['Lengua Española', 'Español', 'Lengua', 'Espanol'],
            'Matemática': ['Matemática', 'Matematica', 'Matemáticas', 'Math'],
            'Ciencias Sociales': ['Ciencias Sociales', 'Sociales', 'Historia'],
            'Ciencias de la Naturaleza': ['Ciencias de la Naturaleza', 'Ciencias Naturales', 'Naturales'],
            'Educación Física': ['Educación Física', 'Educacion Fisica', 'Ed. Física', 'Física', 'Ed Fisica'],
            'Educación Artística': ['Educación Artística', 'Educacion Artistica', 'Arte', 'Artística', 'Ed. Artística'],
            'Formación Integral Humana y Religiosa': ['Formación Integral Humana y Religiosa', 'Formación Humana', 'Formación', 'Religión', 'FIHR', 'Valores', 'FHR'],
            'Salida Optativa': ['Salida Optativa', 'Optativa', 'Electiva'],
            'Biología': ['Biología', 'Biologia'],
        }
        
        if asig_nombre in mapeo_nombres:
            terminos_busqueda.extend(mapeo_nombres[asig_nombre])
        
        for termino in terminos_busqueda:
            if asignatura:
                break
            asignatura = tenant_filter(db.query(Asignatura), Asignatura, current_user).filter(
                func.lower(Asignatura.nombre) == termino.lower()
            ).first()
            if not asignatura:
                asignatura = tenant_filter(db.query(Asignatura), Asignatura, current_user).filter(
                    Asignatura.nombre.ilike(f'%{termino}%')
                ).first()
        
        docente = 'Sin asignar'
        total_calificados = 0
        encontrada = asignatura is not None
        asig_bd_nombre = asignatura.nombre if asignatura else None
        
        if asignatura:
            asignacion = tenant_filter(db.query(AsignacionProfesor), AsignacionProfesor, current_user).filter_by(
                curso_id=curso_id,
                asignatura_id=asignatura.id,
                activo=True
            ).first()
            if asignacion and asignacion.profesor:
                docente = asignacion.profesor.nombre_completo
            else:
                problemas.append(f"⚠️ {asig_nombre}: Sin profesor asignado a este curso")
            
            for est in estudiantes:
                calif = tenant_filter(db.query(Calificacion), Calificacion, current_user).filter_by(
                    estudiante_id=est.id,
                    asignatura_id=asignatura.id
                ).first()
                if calif and calif.cf:
                    total_calificados += 1
        else:
            problemas.append(f"❌ {asig_nombre}: No encontrada en BD. Crear asignatura con nombre similar.")
        
        resumen.append({
            'asignatura_minerd': asig_nombre,
            'asignatura_bd': asig_bd_nombre,
            'encontrada': encontrada,
            'docente': docente,
            'estudiantes_calificados': total_calificados,
            'total_estudiantes': len(estudiantes),
            'porcentaje_completado': round(total_calificados / len(estudiantes) * 100, 1) if estudiantes else 0
        })
    
    return {
        'curso': curso.nombre_completo,
        'grado': grado.nombre if grado else '',
        'ano_escolar': ano.nombre if ano else '',
        'total_estudiantes': len(estudiantes),
        'asignaturas': resumen,
        'asignaturas_en_bd': asignaturas_bd_nombres,
        'problemas': problemas,
        'diagnostico': {
            'total_minerd': len(asignaturas_minerd),
            'encontradas': sum(1 for r in resumen if r['encontrada']),
            'con_profesor': sum(1 for r in resumen if r['docente'] != 'Sin asignar'),
            'listo_para_generar': len(problemas) == 0
        }
    }


# ============== HEALTH CHECK & INFO ==============

@app.get("/api/health")
async def health_check(request: Request, db: Session = Depends(get_db)):
    """Health check para Render y monitoreo"""
    try:
        from sqlalchemy import text
        db.execute(text('SELECT 1'))
        db_status = 'ok'
    except Exception as e:
        db_status = f'error: {str(e)}'
    
    return {
        'status': 'healthy' if db_status == 'ok' else 'unhealthy',
        'database': db_status,
        'version': '5.0',
        'timestamp': now_rd().isoformat()
    }

# ============== BACKUP AUTOMÁTICO ==============

@app.get("/api/backup")
async def crear_backup(db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion', 'superadmin'))):
    """Crear backup de la base de datos (solo dirección/superadmin)"""
    import subprocess
    database_url = os.environ.get('DATABASE_URL', '')
    
    if not database_url or 'postgresql' not in database_url:
        return JSONResponse({'error': 'Backup solo disponible con PostgreSQL'}, status_code=400)
    
    try:
        backup_dir = os.path.join(os.path.dirname(__file__), 'backups')
        os.makedirs(backup_dir, exist_ok=True)
        
        timestamp = now_rd().strftime('%Y%m%d_%H%M%S')
        filename = f'backup_{timestamp}.sql'
        filepath = os.path.join(backup_dir, filename)
        
        # pg_dump usando DATABASE_URL
        result = subprocess.run(
            ['pg_dump', database_url, '-f', filepath, '--no-owner', '--no-acl'],
            capture_output=True, text=True, timeout=120
        )
        
        if result.returncode != 0:
            return JSONResponse({'error': f'Error en pg_dump: {result.stderr[:200]}'}, status_code=500)
        
        # Limpiar backups antiguos (mantener últimos 7)
        backups = sorted([f for f in os.listdir(backup_dir) if f.startswith('backup_')], reverse=True)
        for old_backup in backups[7:]:
            os.remove(os.path.join(backup_dir, old_backup))
        
        size_mb = round(os.path.getsize(filepath) / 1024 / 1024, 2)
        log_auditoria(db, 'BACKUP', 'sistema', datos_nuevos={'archivo': filename, 'tamano_mb': size_mb}, user=current_user)
        db.commit()
        
        return {
            'message': 'Backup creado exitosamente',
            'archivo': filename,
            'tamano_mb': size_mb,
            'fecha': now_rd().isoformat(),
            'backups_guardados': len(backups[:7])
        }
    except subprocess.TimeoutExpired:
        return JSONResponse({'error': 'Backup timeout (> 2 minutos)'}, status_code=500)
    except FileNotFoundError:
        return JSONResponse({'error': 'pg_dump no disponible en el servidor'}, status_code=500)
    except Exception as e:
        logger.error(f"Error backup: {e}")
        return JSONResponse({'error': str(e)}, status_code=500)

@app.get("/api/backup/descargar/{filename}")
async def descargar_backup(filename: str, current_user: Usuario = Depends(RolesRequired('direccion', 'superadmin'))):
    """Descargar un archivo de backup"""
    import re
    if not re.match(r'^backup_\d{8}_\d{6}\.sql$', filename):
        return JSONResponse({'error': 'Nombre de archivo inválido'}, status_code=400)
    
    backup_dir = os.path.join(os.path.dirname(__file__), 'backups')
    filepath = os.path.join(backup_dir, filename)
    
    if not os.path.exists(filepath):
        return JSONResponse({'error': 'Archivo no encontrado'}, status_code=404)
    
    return StreamingResponse(
        open(filepath, 'rb'),
        media_type='application/sql',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )

@app.get("/api/backup/lista")
async def listar_backups(current_user: Usuario = Depends(RolesRequired('direccion', 'superadmin'))):
    """Listar backups disponibles"""
    backup_dir = os.path.join(os.path.dirname(__file__), 'backups')
    if not os.path.exists(backup_dir):
        return {'backups': []}
    
    backups = []
    for f in sorted(os.listdir(backup_dir), reverse=True):
        if f.startswith('backup_') and f.endswith('.sql'):
            filepath = os.path.join(backup_dir, f)
            backups.append({
                'archivo': f,
                'tamano_mb': round(os.path.getsize(filepath) / 1024 / 1024, 2),
                'fecha': f.replace('backup_', '').replace('.sql', '').replace('_', ' ')
            })
    
    return {'backups': backups[:7]}

@app.get("/api/info")
async def api_info(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Información de la API"""
    return {
        'name': 'Educa One API',
        'version': '9.0',
        'description': 'Sistema de Gestión Escolar',
        'endpoints': {
            'auth': '/api/auth/*',
            'estudiantes': '/api/estudiantes',
            'calificaciones': '/api/calificaciones',
            'asistencia': '/api/asistencia',
            'comunicacion': '/api/comunicados, /api/mensajes',
            'reportes': '/api/reportes',
            'configuracion': '/api/configuracion/*'
        }
    }


# ============== INDICADORES DE LOGRO (REGISTRO ESCOLAR) ==============

@app.get("/api/indicadores-logro")
async def get_indicadores_logro(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Obtener indicadores de logro filtrados por curso/asignatura/periodo"""
    curso_id = request.query_params.get('curso_id')
    asignatura_id = request.query_params.get('asignatura_id')
    periodo = request.query_params.get('periodo')
    
    query = tenant_filter(db.query(IndicadorLogro), IndicadorLogro, current_user)
    if curso_id:
        query = query.filter_by(curso_id=int(curso_id))
    if asignatura_id:
        query = query.filter_by(asignatura_id=int(asignatura_id))
    if periodo:
        query = query.filter_by(periodo=int(periodo))
    if current_user.role == 'profesor':
        query = query.filter_by(profesor_id=current_user.id)
    
    return [i.to_dict() for i in query.all()]


@app.post("/api/indicadores-logro")
async def guardar_indicador_logro(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('profesor', 'direccion', 'coordinador'))):
    """Crear o actualizar indicador de logro"""
    data = await request.json()
    
    curso_id = data.get('curso_id')
    asignatura_id = data.get('asignatura_id')
    periodo = data.get('periodo')
    contenido = data.get('contenido', '').strip()
    
    if not all([curso_id, asignatura_id, periodo]):
        return JSONResponse({'error': 'curso_id, asignatura_id y periodo son requeridos'}, status_code=400)
    
    # Buscar existente
    existente = tenant_filter(db.query(IndicadorLogro), IndicadorLogro, current_user).filter_by(
        profesor_id=current_user.id,
        asignatura_id=asignatura_id,
        curso_id=curso_id,
        periodo=periodo
    ).first()
    
    if existente:
        existente.contenido = contenido
        db.commit()
        return {'message': 'Indicador actualizado', 'id': existente.id}
    else:
        indicador = IndicadorLogro(
            colegio_id=current_user.colegio_id,
            profesor_id=current_user.id,
            asignatura_id=asignatura_id,
            curso_id=curso_id,
            periodo=periodo,
            contenido=contenido
        )
        db.add(indicador)
        db.commit()
        return JSONResponse({'message': 'Indicador creado', 'id': indicador.id}, status_code=201)


@app.delete("/api/indicadores-logro/{id}")
async def eliminar_indicador_logro(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('profesor', 'direccion'))):
    """Eliminar indicador de logro. Valida tenant + ownership del profesor."""
    indicador = get_tenant_or_404(db, IndicadorLogro, id, current_user, name='indicador')
    if current_user.role == 'profesor' and indicador.profesor_id != current_user.id:
        return JSONResponse({'error': 'No autorizado'}, status_code=403)
    db.delete(indicador)
    db.commit()
    return {'message': 'Indicador eliminado'}


# ============== ITEMS COMPLETIVOS DEL REGISTRO ESCOLAR ==============
# Estos son las definiciones de las actividades evaluativas que el profesor
# realiza por período (examen parcial, tarea, proyecto, etc.). Se imprimen
# en el registro escolar MINERD como descripción de qué evaluó cada período.

@app.get("/api/items-completivos")
async def get_items_completivos(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """
    Lista items completivos. Filtros opcionales: curso_id, asignatura_id, periodo.
    Profesor ve solo los suyos. Dirección/coordinador ven todos del colegio.
    """
    curso_id = request.query_params.get('curso_id')
    asignatura_id = request.query_params.get('asignatura_id')
    periodo = request.query_params.get('periodo')
    
    query = tenant_filter(db.query(ItemCompletivo), ItemCompletivo, current_user)
    if curso_id:
        query = query.filter_by(curso_id=int(curso_id))
    if asignatura_id:
        query = query.filter_by(asignatura_id=int(asignatura_id))
    if periodo:
        query = query.filter_by(periodo=int(periodo))
    if current_user.role == 'profesor':
        query = query.filter_by(profesor_id=current_user.id)
    
    items = query.order_by(ItemCompletivo.periodo, ItemCompletivo.fecha.desc().nullslast()).all()
    return [i.to_dict() for i in items]


@app.post("/api/items-completivos")
async def crear_item_completivo(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('profesor', 'direccion', 'coordinador'))):
    """
    Crea un item completivo. Solo el profesor que tiene asignación en el curso
    puede crear el ítem (excepto dirección/coordinador que pueden crearlos
    para cualquier curso del colegio).
    """
    data = await request.json()
    
    curso_id = data.get('curso_id')
    asignatura_id = data.get('asignatura_id')
    periodo = data.get('periodo')
    nombre = (data.get('nombre') or '').strip()
    
    if not all([curso_id, asignatura_id, periodo, nombre]):
        return JSONResponse({'error': 'curso_id, asignatura_id, periodo y nombre son requeridos'}, status_code=400)
    
    if periodo not in (1, 2, 3, 4):
        return JSONResponse({'error': 'periodo debe ser 1-4'}, status_code=400)
    
    # Validar tenant del curso y asignatura
    get_tenant_or_404(db, Curso, curso_id, current_user, name='curso')
    get_tenant_or_404(db, Asignatura, asignatura_id, current_user, name='asignatura')
    
    # Si es profesor, debe tener asignación en ese curso+asignatura
    if current_user.role == 'profesor':
        tiene_asig = (
            tenant_filter(db.query(AsignacionProfesor), AsignacionProfesor, current_user)
            .filter_by(profesor_id=current_user.id, curso_id=curso_id, asignatura_id=asignatura_id, activo=True)
            .first()
        )
        if not tiene_asig:
            return JSONResponse({'error': 'No tienes asignación en este curso/asignatura'}, status_code=403)
    
    # Validar peso: 0-100
    peso = data.get('peso')
    if peso is not None:
        try:
            peso = float(peso)
            if peso < 0 or peso > 100:
                return JSONResponse({'error': 'peso debe estar entre 0 y 100'}, status_code=400)
        except (TypeError, ValueError):
            return JSONResponse({'error': 'peso debe ser un número'}, status_code=400)
    
    # Parsear fecha
    fecha = None
    if data.get('fecha'):
        try:
            fecha = datetime.fromisoformat(data['fecha']).date()
        except Exception:
            return JSONResponse({'error': 'fecha inválida (formato YYYY-MM-DD)'}, status_code=400)
    
    item = ItemCompletivo(
        colegio_id=current_user.colegio_id,
        profesor_id=current_user.id,
        asignatura_id=asignatura_id,
        curso_id=curso_id,
        periodo=periodo,
        nombre=nombre[:200],
        descripcion=(data.get('descripcion') or '').strip() or None,
        fecha=fecha,
        peso=peso,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    log_auditoria(db, 'crear', 'items_completivos', item.id, None, item.to_dict(), user=current_user, request=request)
    return JSONResponse(item.to_dict(), status_code=201)


@app.put("/api/items-completivos/{id}")
async def actualizar_item_completivo(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('profesor', 'direccion', 'coordinador'))):
    """Actualiza ítem. Profesor solo puede editar los suyos."""
    item = get_tenant_or_404(db, ItemCompletivo, id, current_user, name='item completivo')
    
    if current_user.role == 'profesor' and item.profesor_id != current_user.id:
        return JSONResponse({'error': 'No puedes editar ítems de otro profesor'}, status_code=403)
    
    data = await request.json()
    old_dict = item.to_dict()
    
    if 'nombre' in data:
        nombre = (data['nombre'] or '').strip()
        if not nombre:
            return JSONResponse({'error': 'nombre no puede estar vacío'}, status_code=400)
        item.nombre = nombre[:200]
    if 'descripcion' in data:
        item.descripcion = (data['descripcion'] or '').strip() or None
    if 'fecha' in data:
        if data['fecha']:
            try:
                item.fecha = datetime.fromisoformat(data['fecha']).date()
            except Exception:
                return JSONResponse({'error': 'fecha inválida (formato YYYY-MM-DD)'}, status_code=400)
        else:
            item.fecha = None
    if 'peso' in data:
        peso = data['peso']
        if peso is not None:
            try:
                peso = float(peso)
                if peso < 0 or peso > 100:
                    return JSONResponse({'error': 'peso debe estar entre 0 y 100'}, status_code=400)
            except (TypeError, ValueError):
                return JSONResponse({'error': 'peso debe ser un número'}, status_code=400)
        item.peso = peso
    
    db.commit()
    log_auditoria(db, 'actualizar', 'items_completivos', item.id, old_dict, item.to_dict(), user=current_user, request=request)
    return item.to_dict()


@app.delete("/api/items-completivos/{id}")
async def eliminar_item_completivo(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('profesor', 'direccion', 'coordinador'))):
    """Elimina ítem. Profesor solo los suyos."""
    item = get_tenant_or_404(db, ItemCompletivo, id, current_user, name='item completivo')
    if current_user.role == 'profesor' and item.profesor_id != current_user.id:
        return JSONResponse({'error': 'No puedes eliminar ítems de otro profesor'}, status_code=403)
    log_auditoria(db, 'eliminar', 'items_completivos', item.id, item.to_dict(), None, user=current_user, request=request)
    db.delete(item)
    db.commit()
    return {'message': 'Ítem eliminado'}


# ============== BLOC DE NOTAS PERSONAL ==============

@app.get("/api/notas-personales")
async def get_notas_personales(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Obtener notas personales del usuario actual"""
    notas = tenant_filter(db.query(NotaPersonal), NotaPersonal, current_user).filter_by(
        usuario_id=current_user.id, activo=True
    ).order_by(NotaPersonal.fijada.desc(), NotaPersonal.fecha_actualizacion.desc()).all()
    return [n.to_dict() for n in notas]

@app.post("/api/notas-personales")
async def crear_nota_personal(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Crear una nota personal"""
    data = await request.json()
    nota = NotaPersonal(
        usuario_id=current_user.id,
        colegio_id=current_user.colegio_id,
        titulo=data.get('titulo', 'Sin título'),
        contenido=data.get('contenido', ''),
        color=data.get('color', 'yellow')
    )
    db.add(nota)
    db.commit()
    return JSONResponse(nota.to_dict(), status_code=201)

@app.put("/api/notas-personales/{id}")
async def editar_nota_personal(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Editar una nota personal"""
    nota = get_tenant_or_404(db, NotaPersonal, id, current_user, name='notapersonal')
    if nota.usuario_id != current_user.id:
        return JSONResponse({'error': 'No autorizado'}, status_code=403)
    
    data = await request.json()
    nota.titulo = data.get('titulo', nota.titulo)
    nota.contenido = data.get('contenido', nota.contenido)
    nota.color = data.get('color', nota.color)
    nota.fijada = data.get('fijada', nota.fijada)
    nota.fecha_actualizacion = now_rd()
    db.commit()
    return nota.to_dict()

@app.delete("/api/notas-personales/{id}")
async def eliminar_nota_personal(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Eliminar una nota personal"""
    nota = get_tenant_or_404(db, NotaPersonal, id, current_user, name='notapersonal')
    if nota.usuario_id != current_user.id:
        return JSONResponse({'error': 'No autorizado'}, status_code=403)
    nota.activo = False
    db.commit()
    return {'message': 'Nota eliminada'}

# ============== EVALUACIÓN DE PROFESORES ==============

@app.get("/api/evaluaciones-profesor")
async def get_evaluaciones_profesor(request: Request, current_user: Usuario = Depends(RolesRequired('direccion', 'coordinador')), db: Session = Depends(get_db)):
    """Obtener evaluaciones de profesores"""
    profesor_id = request.query_params.get('profesor_id')
    query = tenant_filter(db.query(EvaluacionProfesor), EvaluacionProfesor, current_user)
    if profesor_id:
        query = query.filter_by(profesor_id=profesor_id)
    evaluaciones = query.order_by(EvaluacionProfesor.fecha.desc()).all()
    return [e.to_dict() for e in evaluaciones]

@app.post("/api/evaluaciones-profesor")
async def crear_evaluacion_profesor(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion', 'coordinador'))):
    """Crear evaluación de un profesor"""
    data = await request.json()
    ano_activo = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    
    eva = EvaluacionProfesor(
        profesor_id=data['profesor_id'],
        evaluador_id=current_user.id,
        ano_escolar_id=ano_activo.id if ano_activo else None,
        periodo=data.get('periodo'),
        puntualidad=data.get('puntualidad'),
        planificacion=data.get('planificacion'),
        dominio_tema=data.get('dominio_tema'),
        metodologia=data.get('metodologia'),
        manejo_aula=data.get('manejo_aula'),
        uso_recursos=data.get('uso_recursos'),
        evaluacion_estudiantes=data.get('evaluacion_estudiantes'),
        relacion_estudiantes=data.get('relacion_estudiantes'),
        relacion_colegas=data.get('relacion_colegas'),
        compromiso=data.get('compromiso'),
        fortalezas=data.get('fortalezas'),
        areas_mejora=data.get('areas_mejora'),
        observaciones=data.get('observaciones'),
        plan_accion=data.get('plan_accion'),
        colegio_id=current_user.colegio_id
    )
    eva.promedio = eva.calcular_promedio()
    db.add(eva)
    db.commit()
    
    log_auditoria(db, 'crear', 'evaluacion_profesor', eva.id, user=current_user, request=request)
    return JSONResponse(eva.to_dict(), status_code=201)

@app.put("/api/evaluaciones-profesor/{id}")
async def editar_evaluacion_profesor(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion', 'coordinador'))):
    """Editar evaluación de profesor"""
    eva = get_tenant_or_404(db, EvaluacionProfesor, id, current_user, name='evaluacionprofesor')
    data = await request.json()
    
    for campo in ['puntualidad', 'planificacion', 'dominio_tema', 'metodologia',
                  'manejo_aula', 'uso_recursos', 'evaluacion_estudiantes',
                  'relacion_estudiantes', 'relacion_colegas', 'compromiso',
                  'fortalezas', 'areas_mejora', 'observaciones', 'plan_accion']:
        if campo in data:
            setattr(eva, campo, data[campo])
    
    eva.promedio = eva.calcular_promedio()
    db.commit()
    return eva.to_dict()

@app.get("/api/evaluaciones-profesor/resumen")
async def get_resumen_evaluaciones(db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('direccion', 'coordinador'))):
    """Resumen de evaluaciones para el dashboard"""
    profesores = tenant_filter(db.query(Usuario), Usuario, current_user).filter_by(role='profesor', activo=True).all()
    resumen = []
    
    for prof in profesores:
        ultima_eval = tenant_filter(db.query(EvaluacionProfesor), EvaluacionProfesor, current_user).filter_by(
            profesor_id=prof.id
        ).order_by(EvaluacionProfesor.fecha.desc()).first()
        
        total_evals = tenant_filter(db.query(EvaluacionProfesor), EvaluacionProfesor, current_user).filter_by(profesor_id=prof.id).count()
        
        resumen.append({
            'profesor_id': prof.id,
            'profesor': prof.nombre_completo,
            'total_evaluaciones': total_evals,
            'ultima_evaluacion': ultima_eval.fecha.isoformat() if ultima_eval and ultima_eval.fecha else None,
            'promedio': ultima_eval.promedio if ultima_eval else None,
            'nivel': ultima_eval.get_nivel() if ultima_eval else 'Sin evaluar'
        })
    
    return resumen

# ============== DASHBOARD PSICOLOGÍA ==============

@app.get("/api/dashboard/psicologia")
async def get_dashboard_psicologia(db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Dashboard específico para psicología"""
    if current_user.role != 'psicologia':
        return JSONResponse({'error': 'Solo para psicología'}, status_code=403)
    
    # Casos por estado
    pendientes = tenant_filter(db.query(CasoPsicologia), CasoPsicologia, current_user).filter_by(estado='pendiente').count()
    en_proceso = tenant_filter(db.query(CasoPsicologia), CasoPsicologia, current_user).filter_by(estado='en_proceso').count()
    atendidos = tenant_filter(db.query(CasoPsicologia), CasoPsicologia, current_user).filter_by(estado='atendido').count()
    
    # Casos urgentes
    urgentes = tenant_filter(db.query(CasoPsicologia), CasoPsicologia, current_user).filter_by(urgencia='urgente', estado='pendiente').count()
    
    # Mis casos asignados
    mis_casos = tenant_filter(db.query(CasoPsicologia), CasoPsicologia, current_user).filter_by(
        asignado_a=current_user.id
    ).filter(CasoPsicologia.estado != 'atendido').order_by(
        CasoPsicologia.urgencia.desc(), CasoPsicologia.fecha_solicitud.desc()
    ).limit(10).all()
    
    # Casos por tipo
    tipos_q = db.query(
        CasoPsicologia.tipo, func.count(CasoPsicologia.id)
    ).filter(CasoPsicologia.estado != 'atendido')
    if current_user.colegio_id:
        tipos_q = tipos_q.filter(CasoPsicologia.colegio_id == current_user.colegio_id)
    tipos = tipos_q.group_by(CasoPsicologia.tipo).all()
    
    casos_por_tipo = [{'tipo': t[0] or 'sin_tipo', 'cantidad': t[1]} for t in tipos]
    
    # Casos recientes (últimos 7 días)
    hace_7_dias = now_rd() - timedelta(days=7)
    casos_recientes = tenant_filter(db.query(CasoPsicologia), CasoPsicologia, current_user).filter(
        CasoPsicologia.fecha_solicitud >= hace_7_dias
    ).count()
    
    return {
        'pendientes': pendientes,
        'en_proceso': en_proceso,
        'atendidos_total': atendidos,
        'urgentes': urgentes,
        'casos_recientes_7dias': casos_recientes,
        'mis_casos': [{
            'id': c.id,
            'estudiante': c.estudiante.nombre_completo if c.estudiante else None,
            'tipo': c.tipo,
            'urgencia': c.urgencia,
            'estado': c.estado,
            'fecha': c.fecha_solicitud.isoformat() if c.fecha_solicitud else None,
            'solicitante': c.solicitante.nombre_completo if c.solicitante else None
        } for c in mis_casos],
        'casos_por_tipo': casos_por_tipo
    }

# ============== STATS FILTRADAS POR ROL ==============

@app.get("/api/dashboard/stats-rol")
async def get_dashboard_stats_por_rol(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Stats personalizadas según el rol del usuario"""
    role = current_user.role
    
    if role == 'profesor':
        # Solo ver datos de sus cursos asignados
        asignaciones = tenant_filter(db.query(AsignacionProfesor), AsignacionProfesor, current_user).filter_by(profesor_id=current_user.id, activo=True).all()
        cursos_ids = list(set([a.curso_id for a in asignaciones]))
        mis_estudiantes = tenant_filter(db.query(Estudiante), Estudiante, current_user).filter(
            Estudiante.curso_id.in_(cursos_ids), Estudiante.activo == True
        ).count() if cursos_ids else 0
        
        mis_reportes = tenant_filter(db.query(ReporteConducta), ReporteConducta, current_user).filter_by(
            reportado_por=current_user.id, estado='pendiente'
        ).count()
        
        return {
            'estudiantes': mis_estudiantes,
            'cursos': len(cursos_ids),
            'reportes_pendientes': mis_reportes,
            'asignaturas': len(asignaciones)
        }
    
    elif role == 'psicologia':
        return {
            'casos_pendientes': tenant_filter(db.query(CasoPsicologia), CasoPsicologia, current_user).filter_by(estado='pendiente').count(),
            'casos_en_proceso': tenant_filter(db.query(CasoPsicologia), CasoPsicologia, current_user).filter_by(estado='en_proceso', asignado_a=current_user.id).count(),
            'casos_urgentes': tenant_filter(db.query(CasoPsicologia), CasoPsicologia, current_user).filter_by(urgencia='urgente', estado='pendiente').count(),
            'casos_atendidos_mes': tenant_filter(db.query(CasoPsicologia), CasoPsicologia, current_user).filter(
                CasoPsicologia.estado == 'atendido',
                CasoPsicologia.fecha_atencion >= today_rd().replace(day=1)
            ).count()
        }
    
    else:
        # Dirección, coordinador, secretaria - stats globales del colegio
        return {
            'estudiantes': tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(activo=True).count(),
            'profesores': tenant_filter(db.query(Usuario), Usuario, current_user).filter_by(role='profesor', activo=True).count(),
            'cursos': tenant_filter(db.query(Curso), Curso, current_user).filter_by(activo=True).count(),
            'reportes_pendientes': tenant_filter(db.query(ReporteConducta), ReporteConducta, current_user).filter_by(estado='pendiente').count(),
            'casos_psicologia': tenant_filter(db.query(CasoPsicologia), CasoPsicologia, current_user).filter(CasoPsicologia.estado != 'atendido').count()
        }


# ============== EVALUACIÓN INTERNA DE ESTUDIANTES ==============

@app.get("/api/eval-interna/config")
async def get_config_eval_interna(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Obtener configuración de pesos del profesor actual"""
    asignatura_id = int(request.query_params.get('asignatura_id', 0) or 0)
    query = tenant_filter(db.query(ConfigEvalInterna), ConfigEvalInterna, current_user).filter_by(profesor_id=current_user.id)
    if asignatura_id:
        query = query.filter_by(asignatura_id=asignatura_id)
    configs = query.all()
    return [c.to_dict() for c in configs]

@app.post("/api/eval-interna/config")
async def guardar_config_eval_interna(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Guardar/actualizar configuración de pesos"""
    data = await request.json()
    asignatura_id = data.get('asignatura_id')
    if not asignatura_id:
        return JSONResponse({'error': 'Asignatura requerida'}, status_code=400)
    
    # Validar que los pesos sumen 100
    pesos = ['peso_conducta', 'peso_cuaderno', 'peso_participacion', 'peso_trabajo', 'peso_asistencia', 'peso_exposicion']
    total = sum(data.get(p, 0) for p in pesos)
    if abs(total - 100) > 0.01:
        return JSONResponse({'error': f'Los pesos deben sumar 100. Actualmente suman {total}'}, status_code=400)
    
    config = tenant_filter(db.query(ConfigEvalInterna), ConfigEvalInterna, current_user).filter_by(
        profesor_id=current_user.id, asignatura_id=asignatura_id
    ).first()
    
    if not config:
        config = ConfigEvalInterna(profesor_id=current_user.id, asignatura_id=asignatura_id, colegio_id=current_user.colegio_id)
        db.add(config)
    
    for p in pesos:
        setattr(config, p, data.get(p, 0))
    
    db.commit()
    return config.to_dict()

@app.get("/api/eval-interna")
async def get_eval_interna(request: Request, current_user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    """Obtener evaluaciones internas - filtrable por curso, asignatura, periodo"""
    curso_id = int(request.query_params.get('curso_id', 0) or 0)
    asignatura_id = int(request.query_params.get('asignatura_id', 0) or 0)
    periodo = int(request.query_params.get('periodo', 0) or 0)
    
    query = tenant_filter(db.query(EvalInternaEstudiante), EvalInternaEstudiante, current_user)
    
    if current_user.role == 'profesor':
        query = query.filter_by(profesor_id=current_user.id)
    
    if curso_id:
        query = query.filter_by(curso_id=curso_id)
    if asignatura_id:
        query = query.filter_by(asignatura_id=asignatura_id)
    if periodo:
        query = query.filter_by(periodo=periodo)
    
    evals = query.order_by(EvalInternaEstudiante.periodo).all()
    return [e.to_dict() for e in evals]

@app.post("/api/eval-interna/guardar")
async def guardar_eval_interna(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Guardar evaluaciones internas de múltiples estudiantes"""
    data = await request.json()
    curso_id = data.get('curso_id')
    asignatura_id = data.get('asignatura_id')
    periodo = data.get('periodo')
    evaluaciones = data.get('evaluaciones', [])
    
    if not all([curso_id, asignatura_id, periodo]):
        return JSONResponse({'error': 'Curso, asignatura y período requeridos'}, status_code=400)
    
    # Obtener config de pesos
    config = tenant_filter(db.query(ConfigEvalInterna), ConfigEvalInterna, current_user).filter_by(
        profesor_id=current_user.id, asignatura_id=asignatura_id
    ).first()
    
    guardadas = 0
    for ev_data in evaluaciones:
        estudiante_id = ev_data.get('estudiante_id')
        if not estudiante_id:
            continue
        
        ev = tenant_filter(db.query(EvalInternaEstudiante), EvalInternaEstudiante, current_user).filter_by(
            estudiante_id=estudiante_id, profesor_id=current_user.id,
            asignatura_id=asignatura_id, periodo=periodo
        ).first()
        
        if not ev:
            ev = EvalInternaEstudiante(
                colegio_id=current_user.colegio_id,
                estudiante_id=estudiante_id, profesor_id=current_user.id,
                asignatura_id=asignatura_id, curso_id=curso_id, periodo=periodo
            )
            db.add(ev)
        
        ev.conducta = ev_data.get('conducta')
        ev.cuaderno = ev_data.get('cuaderno')
        ev.participacion = ev_data.get('participacion')
        ev.trabajo = ev_data.get('trabajo')
        ev.asistencia_eval = ev_data.get('asistencia_eval')
        ev.exposicion = ev_data.get('exposicion')
        ev.observacion = ev_data.get('observacion')
        ev.nota_final = ev.calcular_nota(config)
        guardadas += 1
    
    db.commit()
    return {'message': f'{guardadas} evaluaciones guardadas', 'guardadas': guardadas}

@app.get("/api/eval-interna/resumen/{curso_id}")
async def get_resumen_eval_interna(curso_id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Resumen de evaluaciones internas de un curso"""
    periodo = int(request.query_params.get('periodo', 0) or 0)
    
    estudiantes = tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(curso_id=curso_id, activo=True).order_by(Estudiante.no_lista).all()
    
    query = tenant_filter(db.query(EvalInternaEstudiante), EvalInternaEstudiante, current_user).filter_by(curso_id=curso_id)
    if current_user.role == 'profesor':
        query = query.filter_by(profesor_id=current_user.id)
    if periodo:
        query = query.filter_by(periodo=periodo)
    
    evals = query.all()
    
    # Agrupar por estudiante
    resumen = []
    for est in estudiantes:
        est_evals = [e for e in evals if e.estudiante_id == est.id]
        if est_evals:
            promedio = sum(e.nota_final for e in est_evals if e.nota_final) / len(est_evals) if est_evals else 0
        else:
            promedio = None
        
        resumen.append({
            'estudiante_id': est.id,
            'nombre': est.nombre_completo,
            'no_lista': est.no_lista,
            'evaluaciones': len(est_evals),
            'promedio': round(promedio, 2) if promedio else None,
            'detalle': [e.to_dict() for e in est_evals]
        })
    
    return resumen

# ============== DASHBOARD SECRETARÍA ==============

@app.get("/api/dashboard/secretaria")
async def get_dashboard_secretaria(db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Dashboard específico para secretaría"""
    from sqlalchemy import func
    
    # Estudiantes por curso
    cursos = tenant_filter(db.query(Curso), Curso, current_user).filter_by(activo=True).order_by(Curso.nombre).all()
    estudiantes_por_curso = []
    for curso in cursos:
        count = tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(curso_id=curso.id, activo=True).count()
        estudiantes_por_curso.append({
            'curso_id': curso.id,
            'curso': curso.nombre,
            'estudiantes': count
        })
    
    # Matriculados recientes (últimos 7 días)
    hace_7_dias = today_rd() - timedelta(days=7)
    matriculados_recientes = tenant_filter(db.query(Estudiante), Estudiante, current_user).filter(
        Estudiante.activo == True,
        Estudiante.fecha_ingreso >= hace_7_dias
    ).count()
    
    # Matriculados hoy
    matriculados_hoy = tenant_filter(db.query(Estudiante), Estudiante, current_user).filter(
        Estudiante.activo == True,
        Estudiante.fecha_ingreso == today_rd()
    ).count()
    
    # Total estudiantes activos
    total_estudiantes = tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(activo=True).count()
    
    # Cursos sin estudiantes
    cursos_vacios = sum(1 for c in estudiantes_por_curso if c['estudiantes'] == 0)
    
    # Año escolar activo
    ano = tenant_filter(db.query(AnoEscolar), AnoEscolar, current_user).filter_by(activo=True).first()
    
    return {
        'total_estudiantes': total_estudiantes,
        'matriculados_hoy': matriculados_hoy,
        'matriculados_semana': matriculados_recientes,
        'cursos_vacios': cursos_vacios,
        'total_cursos': len(cursos),
        'estudiantes_por_curso': estudiantes_por_curso,
        'ano_escolar': ano.nombre if ano else 'No configurado',
        'periodo_activo': ano.periodo_activo if ano else 0
    }


# ===========================================
# SERVIR FRONTEND (se registra pero se monta al final del archivo)
# ===========================================

# ============== SUPER ADMIN - MULTI-TENANT ==============

@app.get("/api/superadmin/colegios")
async def get_colegios(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('superadmin'))):
    """Listar todos los colegios (solo superadmin)"""
    if current_user.role != 'superadmin':
        return JSONResponse({'error': 'No autorizado'}, status_code=403)
    colegios = db.query(Colegio).order_by(Colegio.nombre).all()
    result = []
    for c in colegios:
        d = c.to_dict()
        d['total_estudiantes'] = tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(colegio_id=c.id, activo=True).count()
        d['total_usuarios'] = tenant_filter(db.query(Usuario), Usuario, current_user).filter_by(colegio_id=c.id, activo=True).count()
        result.append(d)
    return result

@app.get("/api/superadmin/colegios/{id}")
async def get_colegio(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('superadmin'))):
    """Detalle de un colegio"""
    if current_user.role != 'superadmin':
        return JSONResponse({'error': 'No autorizado'}, status_code=403)
    colegio = get_tenant_or_404(db, Colegio, id, current_user, name='colegio')
    d = colegio.to_dict()
    d['total_estudiantes'] = tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(colegio_id=colegio.id, activo=True).count()
    d['total_usuarios'] = tenant_filter(db.query(Usuario), Usuario, current_user).filter_by(colegio_id=colegio.id, activo=True).count()
    d['total_cursos'] = tenant_filter(db.query(Curso), Curso, current_user).filter_by(colegio_id=colegio.id, activo=True).count()
    return d

@app.post("/api/superadmin/colegios")
async def crear_colegio(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('superadmin'))):
    """Crear un nuevo colegio con su admin y datos base"""
    if current_user.role != 'superadmin':
        return JSONResponse({'error': 'No autorizado'}, status_code=403)
    
    data = await request.json()
    
    if not data.get('nombre') or not data.get('codigo'):
        return JSONResponse({'error': 'Nombre y código son requeridos'}, status_code=400)
    
    # Verificar código único
    if db.query(Colegio).filter_by(codigo=data['codigo']).first():
        return JSONResponse({'error': 'Ya existe un colegio con ese código'}, status_code=400)
    
    # Plan de módulos. Acepta: { plan_primaria: true, plan_whatsapp: false, ... }
    # o legacy { tiene_primaria, tiene_secundaria }. Defaults sensatos por plan
    # comercial (basico/profesional/enterprise).
    plan_etiqueta = data.get('plan', 'basico')
    
    # Defaults por plan comercial (el superadmin puede sobrescribir cualquiera)
    DEFAULTS_POR_PLAN = {
        'basico': {
            'plan_secundaria': True, 'plan_primaria': False, 'plan_inicial': False,
            'plan_whatsapp': False, 'plan_psicologia': False,
            'plan_eval_profesores': True, 'plan_eval_interna': False,
            'plan_comunicacion_padres': True, 'plan_registro_escolar': True,
            'plan_reportes_conducta': True,
        },
        'profesional': {
            'plan_secundaria': True, 'plan_primaria': True, 'plan_inicial': False,
            'plan_whatsapp': True, 'plan_psicologia': False,
            'plan_eval_profesores': True, 'plan_eval_interna': True,
            'plan_comunicacion_padres': True, 'plan_registro_escolar': True,
            'plan_reportes_conducta': True,
        },
        'enterprise': {
            'plan_secundaria': True, 'plan_primaria': True, 'plan_inicial': True,
            'plan_whatsapp': True, 'plan_psicologia': True,
            'plan_eval_profesores': True, 'plan_eval_interna': True,
            'plan_comunicacion_padres': True, 'plan_registro_escolar': True,
            'plan_reportes_conducta': True,
        },
    }
    plan_modulos = dict(DEFAULTS_POR_PLAN.get(plan_etiqueta, DEFAULTS_POR_PLAN['basico']))
    
    # Compatibilidad legacy: tiene_primaria/tiene_secundaria → plan_primaria/plan_secundaria
    if 'tiene_primaria' in data:
        plan_modulos['plan_primaria'] = bool(data['tiene_primaria'])
    if 'tiene_secundaria' in data:
        plan_modulos['plan_secundaria'] = bool(data['tiene_secundaria'])
    
    # Permitir override individual por superadmin: { plan_X: bool }
    for k, v in data.items():
        if k.startswith('plan_') and k[5:] in MODULOS_DISPONIBLES:
            plan_modulos[k] = bool(v)
    
    # Inicial no está completamente implementado todavía. Lo aceptamos en BD
    # pero forzamos que NO se active hasta que las pantallas estén listas.
    # Esto previene que un colegio compre "inicial" y reciba pantallas de
    # secundaria por error (era el bug reportado).
    if plan_modulos.get('plan_inicial'):
        plan_modulos['plan_inicial'] = False
    
    # Validar: al menos un nivel activo en el plan (secundaria o primaria;
    # inicial no cuenta porque aún no está implementado).
    if not (plan_modulos['plan_secundaria'] or plan_modulos['plan_primaria']):
        return JSONResponse(
            {'error': 'El plan debe incluir al menos primaria o secundaria. Inicial aún no está disponible.'},
            status_code=400
        )
    
    colegio = Colegio(
        nombre=data['nombre'],
        codigo=data['codigo'],
        dominio=data.get('dominio'),
        plan=plan_etiqueta,
        max_estudiantes=data.get('max_estudiantes', 500),
        max_usuarios=data.get('max_usuarios', 50),
        contacto_nombre=data.get('contacto_nombre'),
        contacto_email=data.get('contacto_email'),
        contacto_telefono=data.get('contacto_telefono'),
        notas=data.get('notas'),
        **plan_modulos,
    )
    db.add(colegio)
    db.flush()
    
    # Crear configuración del colegio.
    # IMPORTANTE: distinguimos dos categorías:
    # 1. NIVELES (secundaria/primaria/inicial): usa_X = plan_X. Si pagaste
    #    primaria, querés usarla — no tiene sentido pagar y no usar.
    # 2. MÓDULOS OPCIONALES (whatsapp, psicología, etc): usa_X = False aunque
    #    estén en el plan. El director los enciende cuando quiera empezar a
    #    usarlos. Tener todos prendidos por default abruma con sub-menús.
    #
    # Antes de este fix, los niveles tenían default=True ciegamente, lo cual
    # causaba el bug: colegio sin primaria en plan arrancaba con usa_primaria=True,
    # y al intentar tocar cualquier módulo el sistema rechazaba.
    config = ConfiguracionColegio(
        nombre=data['nombre'],
        colegio_id=colegio.id,
        # Niveles: usa_X = plan_X (consistencia plan-uso)
        usa_secundaria=bool(plan_modulos.get('plan_secundaria', False)),
        usa_primaria=bool(plan_modulos.get('plan_primaria', False)),
        usa_inicial=bool(plan_modulos.get('plan_inicial', False)),
        # Módulos opcionales: NO autoactivar — director decide cuándo encender
        # (mantienen los defaults del modelo, que son False)
    )
    db.add(config)
    
    # Crear usuario dirección para el colegio.
    # Si el caller no proveyó admin_password, generamos una fuerte y forzamos
    # cambio al primer login. Si sí la proveyó, el caller (superadmin) es
    # responsable de comunicarla por canal seguro al director.
    #
    # username único: si el caller no proveyó admin_username, derivamos del
    # código del colegio (que ya es único). Si el caller proveyó un username
    # que ya existe (caso del bug que reportó Luis al crear el segundo colegio
    # con username='direccion' que ya existía del primero), agregamos sufijo
    # numérico hasta encontrar uno libre. Esto previene el IntegrityError 500
    # que veía el usuario.
    admin_username_provisto = (data.get('admin_username') or '').strip()
    admin_username = admin_username_provisto or f"direccion_{data['codigo']}"
    
    # Garantizar unicidad: si ya existe ese username (en cualquier colegio),
    # agregar sufijo numérico hasta encontrar uno libre.
    base_username = admin_username
    suffix = 1
    while db.query(Usuario).filter_by(username=admin_username).first():
        suffix += 1
        admin_username = f"{base_username}_{suffix}"
        if suffix > 100:
            db.rollback()
            return JSONResponse(
                {'error': f'No se pudo generar username único para {base_username}. '
                          f'Especificá admin_username manualmente.'},
                status_code=400
            )
    
    admin_password_provista = data.get('admin_password')
    
    must_change = False
    if admin_password_provista:
        admin_password = admin_password_provista
        # El caller decide; pero validamos longitud mínima
        if len(admin_password) < 8:
            db.rollback()
            return JSONResponse(
                {'error': 'admin_password debe tener al menos 8 caracteres'},
                status_code=400
            )
    else:
        from models import _generar_password_inicial
        admin_password = _generar_password_inicial()
        must_change = True
    
    admin = Usuario(
        username=admin_username,
        nombre=data.get('admin_nombre', 'Director'),
        apellido=data.get('admin_apellido', 'Escolar'),
        role='direccion',
        colegio_id=colegio.id,
        must_change_password=must_change,
    )
    admin.set_password(admin_password)
    db.add(admin)
    
    # Crear año escolar por defecto
    from datetime import date as date_cls
    ano = AnoEscolar(
        nombre='2024-2025',
        fecha_inicio=date_cls(2024, 9, 1),
        fecha_fin=date_cls(2025, 6, 30),
        activo=True,
        periodo_activo=1,
        colegio_id=colegio.id
    )
    db.add(ano)
    
    # Crear grados por defecto SEGÚN EL PLAN del colegio.
    # Antes se creaban siempre 6 grados de secundaria sin importar el plan, lo cual
    # confundía a los colegios que solo tienen primaria. Ahora respetamos plan_X.
    orden = 1
    if colegio.plan_secundaria:
        for nombre_grado in ['1ro Secundaria', '2do Secundaria', '3ro Secundaria',
                             '4to Secundaria', '5to Secundaria', '6to Secundaria']:
            db.add(Grado(nombre=nombre_grado, nivel='secundaria', orden=orden, colegio_id=colegio.id))
            orden += 1
    if colegio.plan_primaria:
        for nombre_grado in ['1ro Primaria', '2do Primaria', '3ro Primaria',
                             '4to Primaria', '5to Primaria', '6to Primaria']:
            db.add(Grado(nombre=nombre_grado, nivel='primaria', orden=orden, colegio_id=colegio.id))
            orden += 1
    if colegio.plan_inicial:
        for nombre_grado in ['Pre-Kínder', 'Kínder', 'Pre-Primario']:
            db.add(Grado(nombre=nombre_grado, nivel='inicial', orden=orden, colegio_id=colegio.id))
            orden += 1
    
    # Crear tandas por defecto
    db.add(Tanda(nombre='Matutina', hora_inicio='07:30', hora_fin='12:30', colegio_id=colegio.id))
    db.add(Tanda(nombre='Vespertina', hora_inicio='14:00', hora_fin='18:00', colegio_id=colegio.id))
    
    # Crear asignaturas por defecto
    for nombre_asig, codigo_asig, area in [
        ('Lengua Española', 'LE', 'Lenguas'),
        ('Matemática', 'MA', 'Matemática'),
        ('Ciencias Sociales', 'CS', 'Ciencias Sociales'),
        ('Ciencias Naturales', 'CN', 'Ciencias Naturales'),
        ('Inglés', 'IN', 'Lenguas'),
        ('Educación Física', 'EF', 'Educación Física'),
        ('Educación Artística', 'EA', 'Educación Artística'),
        ('Formación Humana', 'FH', 'Formación Humana'),
    ]:
        db.add(Asignatura(nombre=nombre_asig, codigo=codigo_asig, area=area, colegio_id=colegio.id))
    
    log_auditoria(db, 'CREAR_COLEGIO', 'colegios', colegio.id, None, colegio.to_dict(), user=current_user, request=request)
    
    # Commit con manejo defensivo. Si algo falla en la integridad (ej: el
    # username del admin colisiona en una ventana de carrera, o cualquier
    # constraint inesperado), devolvemos un 409 con mensaje claro en vez
    # del 500 críptico que veía Luis en su terminal.
    from sqlalchemy.exc import IntegrityError
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        # Heurística: si el error menciona usuarios.username, es colisión
        # de username (el caso reportado). Si no, error genérico.
        err_str = str(e.orig) if hasattr(e, 'orig') else str(e)
        if 'usuarios.username' in err_str.lower() or 'username' in err_str.lower():
            return JSONResponse({
                'error': f'El username "{admin_username}" ya está en uso. '
                         f'Probá un código de colegio distinto o especificá admin_username manualmente.',
                'detalle': 'integrity_username'
            }, status_code=409)
        return JSONResponse({
            'error': 'Conflicto al crear el colegio. Verificá que el código no esté duplicado.',
            'detalle': 'integrity_other'
        }, status_code=409)
    
    return JSONResponse({
        'message': f'Colegio "{colegio.nombre}" creado exitosamente',
        'id': colegio.id,
        'admin_username': admin_username,
        'admin_password': admin_password,
        'must_change_password': must_change,
        # Flag: si tuvimos que cambiar el username pedido para evitar colisión,
        # avisamos al frontend para que lo destaque al superadmin
        'username_ajustado': admin_username != (admin_username_provisto or f"direccion_{data['codigo']}"),
        'username_solicitado': admin_username_provisto or None,
    }, status_code=201)

@app.put("/api/superadmin/colegios/{id}")
async def update_colegio(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('superadmin'))):
    """Actualizar datos de un colegio (solo superadmin).
    
    Acepta plan_X explícitos. Para compatibilidad con frontend viejo, también
    acepta tiene_primaria/tiene_secundaria y los mapea a plan_X.
    """
    if current_user.role != 'superadmin':
        return JSONResponse({'error': 'No autorizado'}, status_code=403)
    
    colegio = get_tenant_or_404(db, Colegio, id, current_user, name='colegio')
    data = await request.json()
    
    # Campos comerciales / de identidad
    for campo in ['nombre', 'dominio', 'activo', 'plan', 'max_estudiantes',
                   'max_usuarios', 'contacto_nombre', 'contacto_email',
                   'contacto_telefono', 'notas']:
        if campo in data:
            setattr(colegio, campo, data[campo])
    
    # Compatibilidad legacy: tiene_X → plan_X
    if 'tiene_primaria' in data:
        colegio.plan_primaria = bool(data['tiene_primaria'])
    if 'tiene_secundaria' in data:
        colegio.plan_secundaria = bool(data['tiene_secundaria'])
    
    # plan_X explícitos (formato moderno)
    for k, v in data.items():
        if k.startswith('plan_') and k[5:] in MODULOS_DISPONIBLES:
            setattr(colegio, k, bool(v))
    
    # Validación: al menos un nivel debe quedar permitido por el plan
    if not (colegio.plan_secundaria or colegio.plan_primaria or colegio.plan_inicial):
        return JSONResponse(
            {'error': 'El plan del colegio debe incluir al menos un nivel educativo (primaria, secundaria o inicial).'},
            status_code=400
        )
    
    if 'fecha_expiracion' in data and data['fecha_expiracion']:
        colegio.fecha_expiracion = datetime.strptime(data['fecha_expiracion'], '%Y-%m-%d').date()
    
    db.commit()
    cache_clear(f'stats:{id}')
    cache_clear(f'cursos:{id}')
    return {'message': 'Colegio actualizado'}

@app.delete("/api/superadmin/colegios/{id}")
async def delete_colegio(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('superadmin'))):
    """Desactivar un colegio (soft delete)"""
    if current_user.role != 'superadmin':
        return JSONResponse({'error': 'No autorizado'}, status_code=403)
    
    colegio = get_tenant_or_404(db, Colegio, id, current_user, name='colegio')
    colegio.activo = False
    
    # Desactivar todos los usuarios del colegio
    tenant_filter(db.query(Usuario), Usuario, current_user).filter_by(colegio_id=colegio.id).update({Usuario.activo: False})
    
    log_auditoria(db, 'DESACTIVAR_COLEGIO', 'colegios', colegio.id, user=current_user, request=request)
    db.commit()
    return {'message': f'Colegio "{colegio.nombre}" desactivado'}

@app.get("/api/superadmin/stats")
async def get_superadmin_stats(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('superadmin'))):
    """Estadísticas globales para superadmin"""
    if current_user.role != 'superadmin':
        return JSONResponse({'error': 'No autorizado'}, status_code=403)
    
    return {
        'total_colegios': db.query(Colegio).filter_by(activo=True).count(),
        'total_colegios_inactivos': db.query(Colegio).filter_by(activo=False).count(),
        'total_estudiantes': tenant_filter(db.query(Estudiante), Estudiante, current_user).filter_by(activo=True).count(),
        'total_usuarios': tenant_filter(db.query(Usuario), Usuario, current_user).filter_by(activo=True).count(),
        'total_profesores': tenant_filter(db.query(Usuario), Usuario, current_user).filter_by(role='profesor', activo=True).count(),
    }

@app.get("/api/superadmin/colegios/{id}/modulos")
async def get_modulos_colegio_superadmin(id: int, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('superadmin'))):
    """Superadmin: ver el plan completo de un colegio (qué módulos están permitidos por contrato).
    
    Devuelve para cada módulo:
      plan: bool   — lo que el superadmin permite (esto es lo que el endpoint controla)
      usa:  bool   — lo que el director encendió/apagó día a día
      activo: bool — efectivo (plan AND usa)
    """
    colegio = db.get(Colegio, id)
    if not colegio:
        return JSONResponse({'error': 'Colegio no encontrado'}, status_code=404)
    
    config = db.query(ConfiguracionColegio).filter_by(colegio_id=id).first()
    if not config:
        config = ConfiguracionColegio(colegio_id=id, nombre=colegio.nombre)
        db.add(config)
        db.commit()
        db.refresh(config)
    
    modulos = {}
    for m in MODULOS_DISPONIBLES:
        plan_val = bool(getattr(colegio, f'plan_{m}', True))
        usa_val = bool(getattr(config, f'usa_{m}', True))
        modulos[m] = {
            'plan': plan_val,
            'usa': usa_val,
            'activo': plan_val and usa_val,
        }
    
    return {
        'colegio_id': id,
        'plan': colegio.plan,
        'modulos': modulos,
    }


@app.put("/api/superadmin/colegios/{id}/modulos")
async def update_modulos_colegio_superadmin(id: int, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('superadmin'))):
    """Superadmin: cambia el PLAN del colegio (qué módulos están permitidos por contrato).
    
    Body acepta:
      { modulos: { whatsapp: true, primaria: false, ... } }
    
    Esto NO afecta lo que el director ve día a día (usa_X) — solo cambia
    qué módulos están AUTORIZADOS por contrato. Si superadmin desactiva un
    módulo que estaba activo, el director pierde acceso (efectivo=false).
    Si superadmin lo reactiva, vuelve al estado que el director tenía
    (sus datos no se borran).
    
    También acepta plan_X directo en el body por compatibilidad.
    """
    data = await request.json()
    if not isinstance(data, dict):
        return JSONResponse({'error': 'Body debe ser objeto JSON'}, status_code=400)
    
    colegio = db.get(Colegio, id)
    if not colegio:
        return JSONResponse({'error': 'Colegio no encontrado'}, status_code=404)
    
    # Asegurar config exists (para que el director pueda usar los módulos después)
    config = db.query(ConfiguracionColegio).filter_by(colegio_id=id).first()
    if not config:
        config = ConfiguracionColegio(colegio_id=id, nombre=colegio.nombre)
        db.add(config)
        db.flush()
    
    # Aceptar tres formatos:
    #   1) { modulos: { whatsapp: true, ... } }
    #   2) { plan_whatsapp: true, ... }
    #   3) { modulo_whatsapp: true, ... }    [legacy]
    modulos_in = {}
    if 'modulos' in data and isinstance(data['modulos'], dict):
        for k, v in data['modulos'].items():
            if k in MODULOS_DISPONIBLES:
                modulos_in[k] = bool(v)
    for k, v in data.items():
        if k.startswith('plan_'):
            nombre = k[5:]
            if nombre in MODULOS_DISPONIBLES:
                modulos_in[nombre] = bool(v)
        elif k.startswith('modulo_'):  # legacy
            nombre = k[7:]
            if nombre in MODULOS_DISPONIBLES:
                modulos_in[nombre] = bool(v)
    
    # Si también vino 'plan' (etiqueta comercial), actualizar
    if 'plan' in data and isinstance(data['plan'], str):
        colegio.plan = data['plan']
    
    cambios = {}
    for nombre, valor in modulos_in.items():
        plan_attr = f'plan_{nombre}'
        if bool(getattr(colegio, plan_attr, True)) != valor:
            cambios[nombre] = valor
            setattr(colegio, plan_attr, valor)
    
    if cambios:
        log_auditoria(db, 'UPDATE_PLAN_MODULOS', 'colegios', colegio.id,
                      datos_nuevos=cambios, user=current_user, request=request)
        db.commit()
        cache_clear(f'stats:{id}')
        cache_clear(f'cursos:{id}')
    
    return {'message': 'Plan de módulos actualizado', 'cambios': list(cambios.keys())}


@app.post("/api/superadmin/colegios/{id}/reactivar")
async def reactivar_colegio(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('superadmin'))):
    """Reactivar un colegio desactivado"""
    if current_user.role != 'superadmin':
        return JSONResponse({'error': 'No autorizado'}, status_code=403)
    
    colegio = get_tenant_or_404(db, Colegio, id, current_user, name='colegio')
    colegio.activo = True
    
    # Reactivar usuarios del colegio
    tenant_filter(db.query(Usuario), Usuario, current_user).filter_by(colegio_id=colegio.id).update({Usuario.activo: True})
    
    db.commit()
    return {'message': f'Colegio "{colegio.nombre}" reactivado'}


@app.get("/api/superadmin/colegios/{id}/usuarios")
async def get_usuarios_colegio(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('superadmin'))):
    """Listar usuarios de un colegio específico"""
    if current_user.role != 'superadmin':
        return JSONResponse({'error': 'No autorizado'}, status_code=403)
    colegio = get_tenant_or_404(db, Colegio, id, current_user, name='colegio')
    usuarios = db.query(Usuario).filter_by(colegio_id=colegio.id).order_by(Usuario.role, Usuario.nombre).all()
    return [u.to_dict() for u in usuarios]


@app.post("/api/superadmin/colegios/{id}/reset-password")
async def reset_password_colegio(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('superadmin'))):
    """Resetear password del director de un colegio.
    
    El usuario reseteado queda con must_change_password=True. Si el caller
    no provee 'password', se genera una password fuerte aleatoria.
    """
    if current_user.role != 'superadmin':
        return JSONResponse({'error': 'No autorizado'}, status_code=403)
    
    data = await request.json()
    usuario_id = data.get('usuario_id')
    nueva_password = data.get('password')
    
    # Si no se provee, generar una fuerte automáticamente
    if not nueva_password:
        from models import _generar_password_inicial
        nueva_password = _generar_password_inicial()
    
    # Si se provee, validar que cumpla requisitos mínimos
    if len(nueva_password) < 8:
        return JSONResponse({'error': 'La contraseña debe tener al menos 8 caracteres'}, status_code=400)
    
    usuario = db.query(Usuario).get(usuario_id)
    if not usuario or usuario.colegio_id != int(id):
        return JSONResponse({'error': 'Usuario no encontrado en este colegio'}, status_code=404)
    
    usuario.set_password(nueva_password)
    usuario.must_change_password = True
    log_auditoria(db, 'RESET_PASSWORD_SUPERADMIN', 'usuarios', usuario.id, user=current_user, request=request)
    db.commit()
    
    return {
        'message': f'Password reseteado para {usuario.nombre_completo}',
        'username': usuario.username,
        'password_temporal': nueva_password,
        'must_change_password': True,
    }


@app.post("/api/superadmin/colegios/{id}/crear-usuario")
async def crear_usuario_colegio(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('superadmin'))):
    """Crear un usuario en un colegio específico"""
    if current_user.role != 'superadmin':
        return JSONResponse({'error': 'No autorizado'}, status_code=403)
    
    colegio = get_tenant_or_404(db, Colegio, id, current_user, name='colegio')
    data = await request.json()
    
    username = data.get('username', '').strip()
    if not username or not data.get('nombre'):
        return JSONResponse({'error': 'Username y nombre son requeridos'}, status_code=400)
    
    if db.query(Usuario).filter_by(username=username).first():
        return JSONResponse({'error': 'El username ya existe'}, status_code=400)
    
    password = data.get('password', '').strip() or 'Cambiar123'
    from security import validate_password
    ok, msg = validate_password(password)
    if not ok:
        return JSONResponse({'error': msg}, status_code=400)
    
    usuario = Usuario(
        username=username,
        nombre=data['nombre'],
        apellido=data.get('apellido', ''),
        role=data.get('role', 'direccion'),
        email=data.get('email'),
        telefono=data.get('telefono'),
        colegio_id=colegio.id
    )
    usuario.set_password(password)
    db.add(usuario)
    db.commit()
    
    return JSONResponse({
        'message': f'Usuario {username} creado en {colegio.nombre}',
        'id': usuario.id,
        'username': username,
        'password': password
    }, status_code=201)


@app.get("/api/superadmin/logs")
async def get_superadmin_logs(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('superadmin'))):
    """Logs globales de auditoría para superadmin"""
    if current_user.role != 'superadmin':
        return JSONResponse({'error': 'No autorizado'}, status_code=403)
    
    limit = int(request.query_params.get('limit', 100))
    colegio_id = request.query_params.get('colegio_id')
    accion = request.query_params.get('accion')
    
    query = db.query(LogAuditoria).order_by(LogAuditoria.fecha.desc())
    
    if colegio_id:
        query = query.filter(LogAuditoria.colegio_id == int(colegio_id))
    if accion:
        query = query.filter(LogAuditoria.accion.ilike(f'%{accion}%'))
    
    logs = query.limit(limit).all()
    result = []
    for log in logs:
        d = log.to_dict()
        # Agregar nombre del colegio
        if log.colegio_id:
            col = db.query(Colegio).get(log.colegio_id)
            d['colegio'] = col.nombre if col else f'ID:{log.colegio_id}'
        else:
            d['colegio'] = 'Sistema'
        result.append(d)
    return result


@app.get("/api/superadmin/accesos")
async def get_superadmin_accesos(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('superadmin'))):
    """Últimos accesos globales"""
    if current_user.role != 'superadmin':
        return JSONResponse({'error': 'No autorizado'}, status_code=403)
    
    limit = int(request.query_params.get('limit', 50))
    colegio_id = request.query_params.get('colegio_id')
    
    query = db.query(LogAcceso).order_by(LogAcceso.fecha.desc())
    if colegio_id:
        query = query.filter(LogAcceso.colegio_id == int(colegio_id))
    
    accesos = query.limit(limit).all()
    result = []
    for a in accesos:
        usuario_nombre = ''
        colegio_nombre = ''
        if a.usuario_id:
            u = db.query(Usuario).get(a.usuario_id)
            if u:
                usuario_nombre = u.nombre_completo
        if a.colegio_id:
            col = db.query(Colegio).get(a.colegio_id)
            colegio_nombre = col.nombre if col else ''
        
        result.append({
            'id': a.id,
            'usuario': usuario_nombre,
            'tipo': a.tipo,
            'ip': a.ip,
            'colegio': colegio_nombre,
            'fecha': a.fecha.isoformat() if a.fecha else None
        })
    return result


@app.get("/api/superadmin/stats/detalle")
async def get_superadmin_stats_detalle(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('superadmin'))):
    """Estadísticas detalladas por colegio"""
    if current_user.role != 'superadmin':
        return JSONResponse({'error': 'No autorizado'}, status_code=403)
    
    colegios = db.query(Colegio).filter_by(activo=True).all()
    result = []
    for c in colegios:
        result.append({
            'id': c.id,
            'nombre': c.nombre,
            'codigo': c.codigo,
            'plan': c.plan,
            'estudiantes': db.query(Estudiante).filter_by(colegio_id=c.id, activo=True).count(),
            'profesores': db.query(Usuario).filter_by(colegio_id=c.id, role='profesor', activo=True).count(),
            'usuarios': db.query(Usuario).filter_by(colegio_id=c.id, activo=True).count(),
            'cursos': db.query(Curso).filter_by(colegio_id=c.id, activo=True).count(),
            'max_estudiantes': c.max_estudiantes,
            'max_usuarios': c.max_usuarios,
        })
    return result


@app.post("/api/superadmin/colegios/{id}/toggle-usuario")
async def toggle_usuario_colegio(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('superadmin'))):
    """Activar/desactivar un usuario de un colegio"""
    if current_user.role != 'superadmin':
        return JSONResponse({'error': 'No autorizado'}, status_code=403)
    
    data = await request.json()
    usuario_id = data.get('usuario_id')
    
    usuario = db.query(Usuario).get(usuario_id)
    if not usuario or usuario.colegio_id != int(id):
        return JSONResponse({'error': 'Usuario no encontrado en este colegio'}, status_code=404)
    
    usuario.activo = not usuario.activo
    db.commit()
    
    estado = 'activado' if usuario.activo else 'desactivado'
    return {'message': f'Usuario {usuario.nombre_completo} {estado}', 'activo': usuario.activo}


@app.post("/api/superadmin/impersonar/{colegio_id}")
async def impersonar_colegio(colegio_id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('superadmin'))):
    """Superadmin entra como director de un colegio (usa el usuario director real)"""
    if current_user.role != 'superadmin':
        return JSONResponse({'error': 'No autorizado'}, status_code=403)
    
    colegio = get_tenant_or_404(db, Colegio, colegio_id, current_user, name='colegio')
    
    # Buscar el director (usuario con role=direccion) de ese colegio
    director = db.query(Usuario).filter_by(
        colegio_id=colegio.id, role='direccion', activo=True
    ).first()
    
    if not director:
        return JSONResponse({
            'error': f'No se encontró un usuario con rol "dirección" en {colegio.nombre}. Cree uno primero desde la pestaña Usuarios.'
        }, status_code=404)
    
    # Generar token con el user_id del director real
    # Incluir token_version e iat para que el middleware lo valide igual que
    # los tokens normales (sino, get_current_user rechaza con 401).
    token_payload = {
        'user_id': director.id,
        'username': director.username,
        'role': 'direccion',
        'colegio_id': colegio.id,
        'impersonating': True,
        'original_role': 'superadmin',
        'token_version': getattr(director, 'token_version', 0) or 0,
        'iat': datetime.utcnow(),
        'exp': datetime.utcnow() + timedelta(hours=2)
    }
    token = jwt.encode(token_payload, JWT_SECRET_KEY, algorithm='HS256')
    
    log_auditoria(db, 'IMPERSONAR_COLEGIO', 'colegios', colegio.id, None, 
                  {'colegio': colegio.nombre, 'como_usuario': director.username}, user=current_user, request=request)
    db.commit()
    
    return {
        'token': token,
        'user': director.to_dict(),
        'colegio': {'id': colegio.id, 'nombre': colegio.nombre, 'codigo': colegio.codigo},
        'message': f'Accediendo como {director.nombre_completo} en {colegio.nombre}'
    }


@app.post("/api/superadmin/cambiar-password")
async def cambiar_password_superadmin(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('superadmin'))):
    """Superadmin cambia su propia contraseña"""
    if current_user.role != 'superadmin':
        return JSONResponse({'error': 'No autorizado'}, status_code=403)
    
    data = await request.json()
    password_actual = data.get('password_actual', '')
    password_nueva = data.get('password_nueva', '')
    
    if not current_user.check_password(password_actual):
        return JSONResponse({'error': 'Contraseña actual incorrecta'}, status_code=400)
    
    from security import validate_password
    ok, msg = validate_password(password_nueva)
    if not ok:
        return JSONResponse({'error': msg}, status_code=400)
    
    current_user.set_password(password_nueva)
    log_auditoria(db, 'CAMBIAR_PASSWORD_SUPERADMIN', 'usuarios', current_user.id, user=current_user, request=request)
    db.commit()
    
    return {'message': 'Contraseña actualizada exitosamente'}


@app.get("/api/superadmin/planes")
async def get_planes_config(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('superadmin'))):
    """Obtener configuración de planes y sus límites"""
    if current_user.role != 'superadmin':
        return JSONResponse({'error': 'No autorizado'}, status_code=403)
    
    return {
        'basico': {
            'nombre': 'Básico',
            'max_estudiantes': 200,
            'max_usuarios': 15,
            'modulos': {
                'calificaciones': True, 'asistencia': True, 'boletines': True,
                'horarios': True, 'reportes_conducta': True, 'comunicacion': True,
                'registro_escolar': False, 'whatsapp': False, 'psicologia': False,
                'eval_profesores': False, 'eval_interna': False, 'estadisticas': False,
                'auditoria': False
            }
        },
        'premium': {
            'nombre': 'Premium',
            'max_estudiantes': 500,
            'max_usuarios': 50,
            'modulos': {
                'calificaciones': True, 'asistencia': True, 'boletines': True,
                'horarios': True, 'reportes_conducta': True, 'comunicacion': True,
                'registro_escolar': True, 'whatsapp': True, 'psicologia': True,
                'eval_profesores': False, 'eval_interna': False, 'estadisticas': True,
                'auditoria': False
            }
        },
        'enterprise': {
            'nombre': 'Enterprise',
            'max_estudiantes': 9999,
            'max_usuarios': 999,
            'modulos': {
                'calificaciones': True, 'asistencia': True, 'boletines': True,
                'horarios': True, 'reportes_conducta': True, 'comunicacion': True,
                'registro_escolar': True, 'whatsapp': True, 'psicologia': True,
                'eval_profesores': True, 'eval_interna': True, 'estadisticas': True,
                'auditoria': True
            }
        }
    }


@app.post("/api/superadmin/colegios/{id}/aplicar-plan")
async def aplicar_plan_colegio(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('superadmin'))):
    """Aplica los defaults del plan comercial del colegio a sus plan_X.
    
    Lee colegio.plan ('basico'/'profesional'/'enterprise') y resetea plan_X
    a los defaults de ese plan. NO toca usa_X (eso es decisión del director).
    
    Ojo: si el colegio tenía plan_X custom (ej: superadmin habilitó whatsapp
    individualmente para un cliente que pagó extra), aplicar-plan los
    sobrescribe con los defaults. Por eso este endpoint es para resetear,
    no para actualización fina (esa es PUT /modulos).
    """
    if current_user.role != 'superadmin':
        return JSONResponse({'error': 'No autorizado'}, status_code=403)
    
    colegio = get_tenant_or_404(db, Colegio, id, current_user, name='colegio')
    
    # Defaults canónicos por plan comercial. Mismos que los usados en
    # POST /api/superadmin/colegios para que el comportamiento sea consistente.
    DEFAULTS_POR_PLAN = {
        'basico': {
            'max_estudiantes': 200, 'max_usuarios': 15,
            'plan_secundaria': True, 'plan_primaria': False, 'plan_inicial': False,
            'plan_whatsapp': False, 'plan_psicologia': False,
            'plan_eval_profesores': True, 'plan_eval_interna': False,
            'plan_comunicacion_padres': True, 'plan_registro_escolar': True,
            'plan_reportes_conducta': True,
        },
        'premium': {  # alias legacy de "profesional"
            'max_estudiantes': 500, 'max_usuarios': 50,
            'plan_secundaria': True, 'plan_primaria': True, 'plan_inicial': False,
            'plan_whatsapp': True, 'plan_psicologia': False,
            'plan_eval_profesores': True, 'plan_eval_interna': True,
            'plan_comunicacion_padres': True, 'plan_registro_escolar': True,
            'plan_reportes_conducta': True,
        },
        'profesional': {
            'max_estudiantes': 500, 'max_usuarios': 50,
            'plan_secundaria': True, 'plan_primaria': True, 'plan_inicial': False,
            'plan_whatsapp': True, 'plan_psicologia': False,
            'plan_eval_profesores': True, 'plan_eval_interna': True,
            'plan_comunicacion_padres': True, 'plan_registro_escolar': True,
            'plan_reportes_conducta': True,
        },
        'enterprise': {
            'max_estudiantes': 9999, 'max_usuarios': 999,
            'plan_secundaria': True, 'plan_primaria': True, 'plan_inicial': True,
            'plan_whatsapp': True, 'plan_psicologia': True,
            'plan_eval_profesores': True, 'plan_eval_interna': True,
            'plan_comunicacion_padres': True, 'plan_registro_escolar': True,
            'plan_reportes_conducta': True,
        },
    }
    
    defaults = DEFAULTS_POR_PLAN.get(colegio.plan, DEFAULTS_POR_PLAN['basico'])
    cambios = {}
    
    # Aplicar límites
    for limite in ('max_estudiantes', 'max_usuarios'):
        if getattr(colegio, limite) != defaults[limite]:
            cambios[limite] = defaults[limite]
            setattr(colegio, limite, defaults[limite])
    
    # Aplicar plan_X (NO toca usa_X — eso es del director)
    for k, v in defaults.items():
        if k.startswith('plan_') and k[5:] in MODULOS_DISPONIBLES:
            if bool(getattr(colegio, k, None)) != bool(v):
                cambios[k] = bool(v)
                setattr(colegio, k, bool(v))
    
    log_auditoria(db, 'APLICAR_PLAN', 'colegios', colegio.id, None,
                  {'plan': colegio.plan, **cambios}, user=current_user, request=request)
    db.commit()
    cache_clear(f'stats:{id}')
    cache_clear(f'cursos:{id}')
    
    return {
        'message': f'Plan "{colegio.plan}" aplicado a {colegio.nombre}',
        'cambios': cambios,
    }


@app.get("/api/superadmin/colegios/{id}/config")
async def get_config_colegio_superadmin(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('superadmin'))):
    """Ver configuración completa de un colegio. Devuelve módulos en formato moderno
    (plan + uso + efectivo) además de aliases legacy para frontend que aún no migró.
    """
    if current_user.role != 'superadmin':
        return JSONResponse({'error': 'No autorizado'}, status_code=403)
    
    colegio = get_tenant_or_404(db, Colegio, id, current_user, name='colegio')
    config = db.query(ConfiguracionColegio).filter_by(colegio_id=colegio.id).first()
    
    ano = db.query(AnoEscolar).filter_by(colegio_id=colegio.id, activo=True).first()
    
    # Construir dict de módulos en formato moderno
    modulos = {}
    for m in MODULOS_DISPONIBLES:
        plan_v = bool(getattr(colegio, f'plan_{m}', False))
        usa_v = bool(getattr(config, f'usa_{m}', False)) if config else False
        modulos[m] = {'plan': plan_v, 'usa': usa_v, 'activo': plan_v and usa_v}
    
    def efectivo(m):
        return modulos[m]['activo']
    
    return {
        'colegio': colegio.to_dict(),
        'config': {
            'nombre': config.nombre if config else colegio.nombre,
            'director': config.director if config else None,
            'telefono': config.telefono if config else None,
            'email': config.email if config else None,
            'direccion': config.direccion if config else None,
            'distrito': config.distrito if config else None,
            'regional': config.regional if config else None,
            # Módulos: formato moderno (plan + uso + efectivo)
            'modulos': modulos,
            # Aliases legacy (efectivo): para frontend que aún no migró al nuevo formato.
            # NUNCA muestran "encendido" un módulo cuyo plan no lo permite.
            'modulo_whatsapp': efectivo('whatsapp'),
            'modulo_psicologia': efectivo('psicologia'),
            'modulo_comunicacion_padres': efectivo('comunicacion_padres'),
            'modulo_eval_profesores': efectivo('eval_profesores'),
            'modulo_eval_interna': efectivo('eval_interna'),
            'modulo_registro_escolar': efectivo('registro_escolar'),
            'permitir_profesor_reportes': bool(config.permitir_profesor_reportes) if config else False,
        },
        'ano_escolar': {
            'nombre': ano.nombre if ano else None,
            'periodo_activo': ano.periodo_activo if ano else None,
            'cerrado': ano.cerrado if ano else None,
        } if ano else None,
        'stats': {
            'estudiantes': db.query(Estudiante).filter_by(colegio_id=colegio.id, activo=True).count(),
            'profesores': db.query(Usuario).filter_by(colegio_id=colegio.id, role='profesor', activo=True).count(),
            'usuarios': db.query(Usuario).filter_by(colegio_id=colegio.id, activo=True).count(),
            'cursos': db.query(Curso).filter_by(colegio_id=colegio.id, activo=True).count(),
            'grados': db.query(Grado).filter_by(colegio_id=colegio.id, activo=True).count(),
            'asignaturas': db.query(Asignatura).filter_by(colegio_id=colegio.id, activo=True).count(),
        }
    }


@app.put("/api/superadmin/colegios/{id}/config")
async def update_config_colegio_superadmin(id, request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('superadmin'))):
    """Superadmin edita la configuración de módulos de un colegio"""
    if current_user.role != 'superadmin':
        return JSONResponse({'error': 'No autorizado'}, status_code=403)
    
    colegio = get_tenant_or_404(db, Colegio, id, current_user, name='colegio')
    config = db.query(ConfiguracionColegio).filter_by(colegio_id=colegio.id).first()
    if not config:
        return JSONResponse({'error': 'Configuración no encontrada'}, status_code=404)
    
    data = await request.json()
    
    campos_modulos = [
        'modulo_whatsapp', 'whatsapp_solo_direccion', 'modulo_psicologia',
        'modulo_comunicacion_padres', 'modulo_eval_profesores', 'modulo_eval_interna',
        'modulo_registro_escolar', 'permitir_profesor_reportes'
    ]
    
    for campo in campos_modulos:
        if campo in data:
            setattr(config, campo, bool(data[campo]))
    
    log_auditoria(db, 'SUPERADMIN_UPDATE_CONFIG', 'configuracion_colegio', config.id,
                  None, data, user=current_user, request=request)
    db.commit()
    
    return {'message': f'Configuración de {colegio.nombre} actualizada'}


@app.get("/api/superadmin/alertas")
async def get_superadmin_alertas(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('superadmin'))):
    """Alertas y notificaciones para el superadmin"""
    if current_user.role != 'superadmin':
        return JSONResponse({'error': 'No autorizado'}, status_code=403)
    
    alertas = []
    hoy = today_rd()
    
    # 1. Colegios cerca del límite de estudiantes (>85%)
    colegios = db.query(Colegio).filter_by(activo=True).all()
    for c in colegios:
        est_count = db.query(Estudiante).filter_by(colegio_id=c.id, activo=True).count()
        if c.max_estudiantes and est_count > c.max_estudiantes * 0.85:
            pct = round(est_count / c.max_estudiantes * 100)
            alertas.append({
                'tipo': 'limite_estudiantes',
                'prioridad': 'alta' if pct >= 95 else 'media',
                'colegio': c.nombre,
                'colegio_id': c.id,
                'mensaje': f'{c.nombre} tiene {est_count}/{c.max_estudiantes} estudiantes ({pct}%)',
            })
        
        usr_count = db.query(Usuario).filter_by(colegio_id=c.id, activo=True).count()
        if c.max_usuarios and usr_count > c.max_usuarios * 0.85:
            pct = round(usr_count / c.max_usuarios * 100)
            alertas.append({
                'tipo': 'limite_usuarios',
                'prioridad': 'alta' if pct >= 95 else 'media',
                'colegio': c.nombre,
                'colegio_id': c.id,
                'mensaje': f'{c.nombre} tiene {usr_count}/{c.max_usuarios} usuarios ({pct}%)',
            })
    
    # 2. Licencias por vencer (próximos 30 días)
    en_30_dias = hoy + timedelta(days=30)
    for c in colegios:
        if c.fecha_expiracion:
            from datetime import date as date_type
            exp = c.fecha_expiracion if isinstance(c.fecha_expiracion, date_type) else datetime.strptime(str(c.fecha_expiracion), '%Y-%m-%d').date()
            if exp <= en_30_dias:
                dias_restantes = (exp - hoy).days
                alertas.append({
                    'tipo': 'licencia_por_vencer',
                    'prioridad': 'alta' if dias_restantes <= 7 else 'media',
                    'colegio': c.nombre,
                    'colegio_id': c.id,
                    'mensaje': f'{c.nombre} expira en {dias_restantes} días ({exp.isoformat()})',
                })
    
    # 3. Colegios sin actividad reciente (sin login en 15+ días)
    hace_15_dias = now_rd() - timedelta(days=15)
    for c in colegios:
        ultimo_acceso = db.query(LogAcceso).filter(
            LogAcceso.colegio_id == c.id,
            LogAcceso.tipo == 'login'
        ).order_by(LogAcceso.fecha.desc()).first()
        
        if ultimo_acceso and ultimo_acceso.fecha:
            if ultimo_acceso.fecha.replace(tzinfo=None) < hace_15_dias.replace(tzinfo=None):
                dias_sin = (now_rd().replace(tzinfo=None) - ultimo_acceso.fecha.replace(tzinfo=None)).days
                alertas.append({
                    'tipo': 'sin_actividad',
                    'prioridad': 'baja',
                    'colegio': c.nombre,
                    'colegio_id': c.id,
                    'mensaje': f'{c.nombre} sin actividad hace {dias_sin} días',
                })
        elif not ultimo_acceso:
            alertas.append({
                'tipo': 'sin_actividad',
                'prioridad': 'baja',
                'colegio': c.nombre,
                'colegio_id': c.id,
                'mensaje': f'{c.nombre} nunca ha tenido un login',
            })
    
    # 4. Login fallidos recientes (últimas 24h)
    hace_24h = now_rd() - timedelta(hours=24)
    login_fallidos = db.query(LogAcceso).filter(
        LogAcceso.tipo == 'login_fallido',
        LogAcceso.fecha >= hace_24h
    ).count()
    if login_fallidos > 0:
        alertas.append({
            'tipo': 'seguridad',
            'prioridad': 'media' if login_fallidos < 10 else 'alta',
            'colegio': 'Global',
            'colegio_id': None,
            'mensaje': f'{login_fallidos} intentos de login fallidos en las últimas 24 horas',
        })
    
    # Ordenar: alta primero
    prioridad_order = {'alta': 0, 'media': 1, 'baja': 2}
    alertas.sort(key=lambda a: prioridad_order.get(a['prioridad'], 3))
    
    return alertas


@app.get("/api/superadmin/export/colegios")
async def export_colegios_csv(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(RolesRequired('superadmin'))):
    """Exportar lista de colegios como CSV"""
    if current_user.role != 'superadmin':
        return JSONResponse({'error': 'No autorizado'}, status_code=403)
    
    colegios = db.query(Colegio).order_by(Colegio.nombre).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Nombre', 'Código', 'Plan', 'Activo', 'Estudiantes', 'Usuarios', 
                     'Máx Est.', 'Máx Usr.', 'Contacto', 'Email', 'Teléfono', 'Creado', 'Expira'])
    
    for c in colegios:
        est = db.query(Estudiante).filter_by(colegio_id=c.id, activo=True).count()
        usr = db.query(Usuario).filter_by(colegio_id=c.id, activo=True).count()
        writer.writerow([
            c.id, c.nombre, c.codigo, c.plan, 'Sí' if c.activo else 'No',
            est, usr, c.max_estudiantes, c.max_usuarios,
            c.contacto_nombre or '', c.contacto_email or '', c.contacto_telefono or '',
            c.fecha_creacion.strftime('%Y-%m-%d') if c.fecha_creacion else '',
            c.fecha_expiracion.isoformat() if c.fecha_expiracion else ''
        ])
    
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type='text/csv',
        headers={'Content-Disposition': 'attachment; filename=colegios_educaone.csv'}
    )

# ===========================================
# SERVIR FRONTEND (DEBE SER LO ÚLTIMO)
# ===========================================
if os.path.exists("static"):
    from fastapi.responses import FileResponse
    app.mount("/assets", StaticFiles(directory="static/assets"), name="assets")
    
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Servir frontend SPA — cualquier ruta no-API devuelve index.html"""
        file_path = os.path.join("static", full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse("static/index.html")


# ============== ARRANQUE (AL FINAL para que TODOS los endpoints estén registrados) ==============

if __name__ == "__main__":
    # IMPORTANTE: invocar uvicorn con el string "app:app" (no la instancia directa)
    # para que el lifespan corra completo. El lifespan aplica TODAS las migraciones
    # idempotentes (must_change_password, token_version, tiene_primaria,
    # tiene_secundaria, índices compuestos) ANTES de aceptar requests.
    #
    # No llamar init_db() acá manualmente: ya lo dispara el lifespan al arranque,
    # y llamarlo antes del lifespan causa crashes con BDs viejas que no tienen
    # las columnas nuevas (porque init_db hace db.query(Colegio).first() que lee
    # todas las columnas, incluida tiene_primaria que aún no existe).
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=int(os.environ.get("PORT", 5000)),
                reload=False, lifespan="on")
