# EducaOne — Guía de Datos, Backups y Migraciones

## REGLA DE ORO
**SIEMPRE haz backup antes de cualquier cambio:**
```powershell
cd C:\Users\owner\OneDrive\Desktop\educaone-multitenant\backend
python backup_db.py
```

---

## Escenario 1: Solo actualizo código (NO hay columnas nuevas)

Esto es lo más común. Solo reemplazas archivos:

```powershell
# 1. Parar backend (Ctrl+C)
# 2. Reemplazar archivos .py y .tsx del ZIP
# 3. Reiniciar
uvicorn app:app --host 0.0.0.0 --port 5000 --reload
```

**Tus datos NO se tocan.** La base de datos sigue igual.

---

## Escenario 2: Hay columnas nuevas (migración necesaria)

Esto pasa cuando yo agrego algo como `telefono_emergencia` a un modelo.

### Primera vez — Instalar Alembic:
```powershell
pip install alembic
alembic stamp head
```
El `stamp head` le dice a Alembic "la base de datos actual está al día".

### Cada vez que hay cambio en modelos:
```powershell
# 1. BACKUP PRIMERO
python backup_db.py

# 2. Generar migración automática
alembic revision --autogenerate -m "descripcion del cambio"

# 3. Revisar el archivo generado en alembic/versions/
#    (abre el .py y verifica que tiene sentido)

# 4. Aplicar la migración
alembic upgrade head

# 5. Reiniciar backend
uvicorn app:app --host 0.0.0.0 --port 5000 --reload
```

### Si algo sale mal:
```powershell
# Revertir última migración
alembic downgrade -1

# O restaurar backup
python backup_db.py --restore ultimo
```

---

## Escenario 3: Restaurar datos

### Ver backups disponibles:
```powershell
python backup_db.py --list
```

### Restaurar el último backup:
```powershell
python backup_db.py --restore ultimo
```

### Restaurar un backup específico:
```powershell
python backup_db.py --restore 3
```
(Donde 3 es el número del backup en la lista)

---

## Escenario 4: Producción con PostgreSQL (Render.com)

En producción todo es más seguro porque:
- Render hace **backups automáticos diarios**
- PostgreSQL tiene **point-in-time recovery** (restaurar a cualquier minuto)
- Las migraciones funcionan igual con `alembic upgrade head`

### Backup manual en producción:
```bash
# Desde tu PC, con la URL de Render
pg_dump "postgres://usuario:password@host/db" > backup_produccion.sql

# Restaurar
psql "postgres://usuario:password@host/db" < backup_produccion.sql
```

---

## Resumen rápido

| Situación | Qué hacer |
|-----------|-----------|
| Solo cambié código Python/React | Reemplazar archivos, reiniciar |
| Agregué columna nueva a un modelo | `python backup_db.py` → `alembic revision --autogenerate` → `alembic upgrade head` |
| Algo salió mal | `alembic downgrade -1` o `python backup_db.py --restore ultimo` |
| Quiero backup manual | `python backup_db.py` |
| Quiero ver mis backups | `python backup_db.py --list` |
| Borré algo por error | `python backup_db.py --restore ultimo` → reiniciar uvicorn |

---

## Importante

- Los backups se guardan en `backend/backups/` (máximo 10, los viejos se eliminan)
- Siempre se hace un backup "pre-restauración" antes de restaurar, por seguridad
- En SQLite (desarrollo): el backup es una copia del archivo .db
- En PostgreSQL (producción): el backup es un archivo .sql con pg_dump
