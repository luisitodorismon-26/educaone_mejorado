"""
backup_db.py — Respaldo de base de datos EducaOne
====================================================
Corre esto ANTES de cualquier migración o cambio importante.

USO:
    python backup_db.py                    # Backup automático
    python backup_db.py --restore ultimo   # Restaurar último backup
    python backup_db.py --list             # Ver backups disponibles

FUNCIONA CON:
    - SQLite: copia el archivo .db
    - PostgreSQL: usa pg_dump (necesita pg_dump instalado)
"""
import os
import sys
import shutil
import subprocess
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///sge.db')
BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backups')


def ensure_backup_dir():
    os.makedirs(BACKUP_DIR, exist_ok=True)


def get_timestamp():
    return datetime.now().strftime('%Y%m%d_%H%M%S')


def backup_sqlite(db_path: str):
    """Copiar archivo SQLite"""
    if not os.path.exists(db_path):
        print(f"❌ Base de datos no encontrada: {db_path}")
        return None
    
    ensure_backup_dir()
    timestamp = get_timestamp()
    backup_name = f"backup_{timestamp}.db"
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    
    shutil.copy2(db_path, backup_path)
    size_mb = os.path.getsize(backup_path) / (1024 * 1024)
    print(f"✅ Backup creado: {backup_path} ({size_mb:.2f} MB)")
    return backup_path


def backup_postgresql(url: str):
    """Usar pg_dump para PostgreSQL"""
    ensure_backup_dir()
    timestamp = get_timestamp()
    backup_name = f"backup_{timestamp}.sql"
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    
    try:
        result = subprocess.run(
            ['pg_dump', url, '-f', backup_path, '--no-owner', '--no-acl'],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            size_mb = os.path.getsize(backup_path) / (1024 * 1024)
            print(f"✅ Backup creado: {backup_path} ({size_mb:.2f} MB)")
            return backup_path
        else:
            print(f"❌ Error en pg_dump: {result.stderr}")
            return None
    except FileNotFoundError:
        print("❌ pg_dump no encontrado. Instala PostgreSQL client tools.")
        return None


def restore_sqlite(backup_path: str, db_path: str):
    """Restaurar backup SQLite"""
    if not os.path.exists(backup_path):
        print(f"❌ Backup no encontrado: {backup_path}")
        return False
    
    # Hacer backup del estado actual antes de restaurar
    if os.path.exists(db_path):
        pre_restore = os.path.join(BACKUP_DIR, f"pre_restore_{get_timestamp()}.db")
        shutil.copy2(db_path, pre_restore)
        print(f"📋 Backup pre-restauración: {pre_restore}")
    
    shutil.copy2(backup_path, db_path)
    print(f"✅ Base de datos restaurada desde: {backup_path}")
    print("⚠️  Reinicia uvicorn para que tome efecto")
    return True


def list_backups():
    """Listar backups disponibles"""
    ensure_backup_dir()
    backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith('backup_')])
    
    if not backups:
        print("No hay backups disponibles.")
        return []
    
    print(f"\n📁 Backups en {BACKUP_DIR}:\n")
    for i, b in enumerate(backups, 1):
        path = os.path.join(BACKUP_DIR, b)
        size = os.path.getsize(path) / (1024 * 1024)
        # Extraer fecha del nombre
        parts = b.replace('backup_', '').replace('.db', '').replace('.sql', '')
        try:
            dt = datetime.strptime(parts, '%Y%m%d_%H%M%S')
            fecha = dt.strftime('%d/%m/%Y %H:%M:%S')
        except ValueError:
            fecha = parts
        print(f"  {i}. {b} — {fecha} — {size:.2f} MB")
    
    return backups


def main():
    args = sys.argv[1:]
    
    if '--list' in args:
        list_backups()
        return
    
    if '--restore' in args:
        idx = args.index('--restore')
        target = args[idx + 1] if idx + 1 < len(args) else 'ultimo'
        
        backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith('backup_')]) if os.path.exists(BACKUP_DIR) else []
        if not backups:
            print("❌ No hay backups disponibles")
            return
        
        if target == 'ultimo':
            backup_file = backups[-1]
        else:
            try:
                backup_file = backups[int(target) - 1]
            except (ValueError, IndexError):
                print(f"❌ Backup '{target}' no encontrado. Usa --list para ver disponibles.")
                return
        
        backup_path = os.path.join(BACKUP_DIR, backup_file)
        
        if DATABASE_URL.startswith('sqlite'):
            db_path = DATABASE_URL.replace('sqlite:///', '')
            restore_sqlite(backup_path, db_path)
        else:
            print("⚠️  Para restaurar PostgreSQL, usa:")
            print(f"    psql {DATABASE_URL} < {backup_path}")
        return
    
    # Backup por defecto
    print(f"🔄 Creando backup de la base de datos...")
    print(f"   URL: {DATABASE_URL[:50]}...")
    
    if DATABASE_URL.startswith('sqlite'):
        db_path = DATABASE_URL.replace('sqlite:///', '')
        backup_sqlite(db_path)
    else:
        backup_postgresql(DATABASE_URL)
    
    # Limpiar backups viejos (mantener últimos 10)
    if os.path.exists(BACKUP_DIR):
        backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith('backup_')])
        while len(backups) > 10:
            old = backups.pop(0)
            os.remove(os.path.join(BACKUP_DIR, old))
            print(f"🗑️  Eliminado backup viejo: {old}")


if __name__ == '__main__':
    main()
