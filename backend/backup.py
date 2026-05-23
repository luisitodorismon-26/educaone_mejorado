#!/usr/bin/env python3
"""
Script de Backup Automático para Educa One
=====================================
Uso:
    python backup.py                    # Backup completo
    python backup.py --restore FILE     # Restaurar desde archivo
    python backup.py --list             # Listar backups disponibles
    python backup.py --clean            # Limpiar backups antiguos

Configurar en cron para backups automáticos:
    0 2 * * * cd /ruta/al/proyecto && python backup.py >> /var/log/sge-backup.log 2>&1
"""

import os
import sys
import gzip
import shutil
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# Configuración
BACKUP_DIR = os.environ.get('BACKUP_DIR', './backups')
RETENTION_DAYS = int(os.environ.get('BACKUP_RETENTION_DAYS', 30))
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///sge.db')

def ensure_backup_dir():
    """Asegura que el directorio de backups existe."""
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)

def get_timestamp():
    """Genera timestamp para nombre de archivo."""
    return datetime.now().strftime('%Y%m%d_%H%M%S')

def backup_sqlite(db_path):
    """Realiza backup de base de datos SQLite."""
    if not os.path.exists(db_path):
        print(f"Error: No se encontró la base de datos: {db_path}")
        return None
    
    timestamp = get_timestamp()
    backup_name = f"sge_backup_{timestamp}.db.gz"
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    
    # Comprimir y copiar
    with open(db_path, 'rb') as f_in:
        with gzip.open(backup_path, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)
    
    size = os.path.getsize(backup_path)
    print(f"✅ Backup creado: {backup_name} ({size / 1024:.1f} KB)")
    return backup_path

def backup_postgresql(db_url):
    """Realiza backup de base de datos PostgreSQL."""
    import subprocess
    
    # Parsear URL de conexión
    # postgresql://user:pass@host:port/dbname
    from urllib.parse import urlparse
    parsed = urlparse(db_url)
    
    timestamp = get_timestamp()
    backup_name = f"sge_backup_{timestamp}.sql.gz"
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    
    # Configurar variables de entorno para pg_dump
    env = os.environ.copy()
    env['PGPASSWORD'] = parsed.password or ''
    
    # Ejecutar pg_dump
    cmd = [
        'pg_dump',
        '-h', parsed.hostname or 'localhost',
        '-p', str(parsed.port or 5432),
        '-U', parsed.username or 'postgres',
        '-d', parsed.path[1:],  # Quitar el /
        '-Fc'  # Formato custom (comprimido)
    ]
    
    try:
        with open(backup_path.replace('.gz', ''), 'wb') as f:
            result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, env=env)
        
        if result.returncode != 0:
            print(f"Error en pg_dump: {result.stderr.decode()}")
            return None
        
        # Comprimir
        with open(backup_path.replace('.gz', ''), 'rb') as f_in:
            with gzip.open(backup_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        
        os.remove(backup_path.replace('.gz', ''))
        
        size = os.path.getsize(backup_path)
        print(f"✅ Backup PostgreSQL creado: {backup_name} ({size / 1024:.1f} KB)")
        return backup_path
        
    except FileNotFoundError:
        print("Error: pg_dump no encontrado. Instale postgresql-client.")
        return None

def restore_sqlite(backup_path, db_path):
    """Restaura base de datos SQLite desde backup."""
    if not os.path.exists(backup_path):
        print(f"Error: No se encontró el archivo de backup: {backup_path}")
        return False
    
    # Crear backup del actual antes de restaurar
    if os.path.exists(db_path):
        pre_restore_backup = db_path + f'.pre_restore_{get_timestamp()}'
        shutil.copy2(db_path, pre_restore_backup)
        print(f"📦 Backup pre-restauración: {pre_restore_backup}")
    
    # Descomprimir y restaurar
    if backup_path.endswith('.gz'):
        with gzip.open(backup_path, 'rb') as f_in:
            with open(db_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
    else:
        shutil.copy2(backup_path, db_path)
    
    print(f"✅ Base de datos restaurada desde: {backup_path}")
    return True

def restore_postgresql(backup_path, db_url):
    """Restaura base de datos PostgreSQL desde backup."""
    import subprocess
    from urllib.parse import urlparse
    
    parsed = urlparse(db_url)
    
    env = os.environ.copy()
    env['PGPASSWORD'] = parsed.password or ''
    
    # Descomprimir si es necesario
    if backup_path.endswith('.gz'):
        temp_path = backup_path[:-3]
        with gzip.open(backup_path, 'rb') as f_in:
            with open(temp_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        backup_path = temp_path
    
    cmd = [
        'pg_restore',
        '-h', parsed.hostname or 'localhost',
        '-p', str(parsed.port or 5432),
        '-U', parsed.username or 'postgres',
        '-d', parsed.path[1:],
        '-c',  # Limpiar antes de restaurar
        backup_path
    ]
    
    try:
        result = subprocess.run(cmd, stderr=subprocess.PIPE, env=env)
        
        if result.returncode != 0:
            print(f"Advertencia: {result.stderr.decode()}")
        
        print(f"✅ Base de datos PostgreSQL restaurada")
        return True
        
    except FileNotFoundError:
        print("Error: pg_restore no encontrado. Instale postgresql-client.")
        return False

def list_backups():
    """Lista todos los backups disponibles."""
    ensure_backup_dir()
    
    backups = []
    for f in os.listdir(BACKUP_DIR):
        if f.startswith('sge_backup_'):
            path = os.path.join(BACKUP_DIR, f)
            size = os.path.getsize(path)
            mtime = datetime.fromtimestamp(os.path.getmtime(path))
            backups.append((f, size, mtime))
    
    backups.sort(key=lambda x: x[2], reverse=True)
    
    if not backups:
        print("No hay backups disponibles.")
        return
    
    print("\n📁 Backups disponibles:")
    print("-" * 60)
    for name, size, mtime in backups:
        print(f"  {name:<40} {size/1024:>8.1f} KB  {mtime.strftime('%Y-%m-%d %H:%M')}")
    print("-" * 60)
    print(f"Total: {len(backups)} backups\n")

def clean_old_backups():
    """Elimina backups más antiguos que RETENTION_DAYS."""
    ensure_backup_dir()
    
    cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
    deleted = 0
    
    for f in os.listdir(BACKUP_DIR):
        if f.startswith('sge_backup_'):
            path = os.path.join(BACKUP_DIR, f)
            mtime = datetime.fromtimestamp(os.path.getmtime(path))
            
            if mtime < cutoff:
                os.remove(path)
                print(f"🗑️  Eliminado: {f}")
                deleted += 1
    
    if deleted:
        print(f"\n✅ {deleted} backups antiguos eliminados (>{RETENTION_DAYS} días)")
    else:
        print(f"No hay backups más antiguos que {RETENTION_DAYS} días")

def do_backup():
    """Realiza backup según el tipo de base de datos."""
    ensure_backup_dir()
    
    if DATABASE_URL.startswith('sqlite'):
        # Extraer path del SQLite
        db_path = DATABASE_URL.replace('sqlite:///', '')
        return backup_sqlite(db_path)
    elif DATABASE_URL.startswith('postgresql'):
        return backup_postgresql(DATABASE_URL)
    else:
        print(f"Tipo de base de datos no soportado: {DATABASE_URL}")
        return None

def do_restore(backup_file):
    """Restaura desde archivo de backup."""
    backup_path = os.path.join(BACKUP_DIR, backup_file) if not os.path.isabs(backup_file) else backup_file
    
    if not os.path.exists(backup_path):
        print(f"Error: Archivo no encontrado: {backup_path}")
        return False
    
    # Confirmar
    confirm = input(f"⚠️  ¿Está seguro de restaurar desde {backup_file}? (s/N): ")
    if confirm.lower() != 's':
        print("Restauración cancelada.")
        return False
    
    if DATABASE_URL.startswith('sqlite'):
        db_path = DATABASE_URL.replace('sqlite:///', '')
        return restore_sqlite(backup_path, db_path)
    elif DATABASE_URL.startswith('postgresql'):
        return restore_postgresql(backup_path, DATABASE_URL)
    else:
        print(f"Tipo de base de datos no soportado")
        return False

def main():
    parser = argparse.ArgumentParser(description='Script de backup para Educa One')
    parser.add_argument('--restore', metavar='FILE', help='Restaurar desde archivo')
    parser.add_argument('--list', action='store_true', help='Listar backups disponibles')
    parser.add_argument('--clean', action='store_true', help='Limpiar backups antiguos')
    
    args = parser.parse_args()
    
    print(f"\n🗄️  Educa One Backup Tool")
    print(f"   Base de datos: {DATABASE_URL[:50]}...")
    print(f"   Directorio: {BACKUP_DIR}")
    print()
    
    if args.list:
        list_backups()
    elif args.clean:
        clean_old_backups()
    elif args.restore:
        do_restore(args.restore)
    else:
        # Backup por defecto
        result = do_backup()
        if result:
            # Limpiar antiguos después de backup exitoso
            clean_old_backups()

if __name__ == '__main__':
    main()
