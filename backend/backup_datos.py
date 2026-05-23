"""
====================================================================
 BACKUP DE DATOS — EducaOne
====================================================================
Genera una copia de seguridad COMPLETA de todos los datos en formato
JSON, que podés guardar fuera de Render (Google Drive, tu PC, etc.).

Esto es un backup ADICIONAL. El backup principal lo hace Render
automáticamente (PostgreSQL con backups diarios en planes de pago).
Este script es tu red de seguridad extra.

CÓMO USAR:
  # En local:
  $env:DATABASE_URL = "sqlite:///./educaone.db"
  python backup_datos.py

  # En Render (Shell del servicio):
  python backup_datos.py

Genera: backup_educaone_YYYYMMDD_HHMMSS.json
Para programarlo diario, usá un Cron Job de Render que ejecute este script.
====================================================================
"""
import os, json, sys
from datetime import datetime, date

os.environ.setdefault('DATABASE_URL', 'sqlite:///./educaone.db')
os.environ.setdefault('SECRET_KEY', 'backup')
os.environ.setdefault('JWT_SECRET_KEY', 'backup')

from database import SessionLocal
import models

def serializar(obj):
    """Convierte un objeto SQLAlchemy a dict serializable."""
    d = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.name)
        if isinstance(val, (datetime, date)):
            val = val.isoformat()
        d[col.name] = val
    return d

db = SessionLocal()

# Todos los modelos con tabla
modelos = []
for nombre in dir(models):
    m = getattr(models, nombre)
    if hasattr(m, '__table__') and hasattr(m, '__tablename__'):
        modelos.append((nombre, m))

backup = {
    '_meta': {
        'fecha': datetime.now().isoformat(),
        'version': 'educaone_v2.13.31',
    }
}
total = 0
print("Respaldando datos...")
for nombre, modelo in modelos:
    try:
        registros = db.query(modelo).all()
        backup[modelo.__tablename__] = [serializar(r) for r in registros]
        n = len(registros)
        total += n
        if n > 0:
            print(f"  {modelo.__tablename__}: {n} registros")
    except Exception as e:
        print(f"  (aviso: no se pudo respaldar {nombre}: {e})")

archivo = f"backup_educaone_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
with open(archivo, 'w', encoding='utf-8') as f:
    json.dump(backup, f, ensure_ascii=False, indent=2, default=str)

db.close()
tam = os.path.getsize(archivo) / 1024
print(f"\nBackup completado: {archivo}")
print(f"  Total registros: {total}")
print(f"  Tamaño: {tam:.1f} KB")
print(f"\nGuardá este archivo en un lugar seguro (Google Drive, etc.).")
print("Para restaurar, necesitarías un script de importación (consultá si lo necesitás).")
