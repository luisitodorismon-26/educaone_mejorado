"""
Educa One - Configuración de Base de Datos
SQLAlchemy para FastAPI - Compatible SQLite (dev) y PostgreSQL (prod)
"""
import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///sge.db')
# Render/Heroku usa postgres:// pero SQLAlchemy necesita postgresql://
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

# Configurar engine según el tipo de DB
is_sqlite = DATABASE_URL.startswith('sqlite')

engine_kwargs = {
    'pool_pre_ping': True,
    'echo': False,
}

if is_sqlite:
    # SQLite: sin pool, con check_same_thread=False
    engine_kwargs['connect_args'] = {'check_same_thread': False}
else:
    # PostgreSQL: pool dimensionado para Render con 2 workers gunicorn.
    # Cada worker tiene su propio pool. Con pool_size=5 + max_overflow=10
    # = 15 conexiones por worker = 30 total. Render Postgres Free permite
    # 97 conexiones, así que tenemos margen. Si pasás a Starter o superior,
    # esto se puede subir.
    # pool_recycle 280s: por debajo del timeout de Render (300s) para evitar
    # conexiones zombie.
    engine_kwargs['pool_size'] = 5
    engine_kwargs['max_overflow'] = 10
    engine_kwargs['pool_recycle'] = 280
    engine_kwargs['pool_timeout'] = 30  # esperar hasta 30s antes de fallar

engine = create_engine(DATABASE_URL, **engine_kwargs)

# Habilitar WAL mode en SQLite para mejor concurrencia
if is_sqlite:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        # cursor.execute("PRAGMA journal_mode=WAL")  # disabled in sandbox
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """Dependency para obtener sesión de DB en FastAPI"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
