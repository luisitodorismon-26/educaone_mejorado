"""
Migración BD v2.12 → v2.13.1

Agrega columnas nuevas a ConfiguracionColegio:
  - permite_sabado (Boolean, default False)
  - permite_domingo (Boolean, default False)

Para BDs nuevas (sqlite o postgres recién creadas) esto NO es necesario,
porque models.py ya tiene las columnas y Base.metadata.create_all las crea
automáticamente.

Para BDs EXISTENTES (con datos de v2.12 ya cargados) sí hay que correr esto
UNA VEZ después de actualizar el código:

    cd backend
    python tools/migrar_v213_1.py

Si las columnas ya existen, el script lo detecta y termina sin error.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect, text
from database import engine

def main():
    insp = inspect(engine)
    
    if 'configuracion_colegio' not in insp.get_table_names():
        print("⚠️  La tabla configuracion_colegio no existe todavía.")
        print("    Eso significa que tu BD no fue inicializada.")
        print("    Ejecutá primero: python -c 'from database import init_db; init_db()'")
        return
    
    cols = {c['name'] for c in insp.get_columns('configuracion_colegio')}
    
    cambios = []
    if 'permite_sabado' not in cols:
        cambios.append(('permite_sabado', 'BOOLEAN DEFAULT FALSE NOT NULL'))
    if 'permite_domingo' not in cols:
        cambios.append(('permite_domingo', 'BOOLEAN DEFAULT FALSE NOT NULL'))
    
    if not cambios:
        print("✅ Las columnas ya existen. No hay migración pendiente.")
        return
    
    print(f"Aplicando {len(cambios)} cambio(s) a configuracion_colegio:")
    with engine.begin() as conn:
        for col, definicion in cambios:
            sql = f"ALTER TABLE configuracion_colegio ADD COLUMN {col} {definicion}"
            print(f"  → {sql}")
            try:
                conn.execute(text(sql))
            except Exception as e:
                # En sqlite, ADD COLUMN no soporta NOT NULL sin DEFAULT, hagamos fallback
                print(f"    ⚠️  Reintentando sin NOT NULL: {e}")
                sql2 = f"ALTER TABLE configuracion_colegio ADD COLUMN {col} BOOLEAN DEFAULT 0"
                conn.execute(text(sql2))
                print(f"    ✅ Aplicado: {sql2}")
    
    print()
    print("✅ Migración completada.")
    print("   Las nuevas columnas tienen default FALSE (sábado/domingo deshabilitados).")
    print("   Si tu colegio tiene clases los sábados, activá permite_sabado=True desde Configuración.")


if __name__ == '__main__':
    main()
