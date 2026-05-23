"""
Alembic env.py — Conecta Alembic con tu base de datos y modelos.
NO necesitas editar este archivo.
"""
import os
import sys
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

# Agregar el directorio backend al path para importar models
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Cargar .env
from dotenv import load_dotenv
load_dotenv()

# Importar Base y todos los modelos
from database import Base, DATABASE_URL
from models import *  # noqa - importa todos los modelos para que Alembic los detecte

# Config de Alembic
config = context.config

# Setear la URL de la base de datos desde .env
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata de los modelos — Alembic la usa para detectar cambios
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Genera SQL sin conectarse a la BD (para revisar antes de aplicar)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Aplica migraciones conectándose a la BD."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # render_as_batch=True es NECESARIO para SQLite
            # (SQLite no soporta ALTER TABLE DROP COLUMN directamente)
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
