"""
Script de un solo uso para limpiar must_change_password de superadmin y direccion.

Úsalo si tu BD se creó con el Sprint 1 estricto y ahora quieres pasar al modo
moderado (passwords fijas superadmin123 / admin123 sin forzar cambio).

Uso (con el venv activado):
    cd backend
    python tools/limpiar_must_change.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
from models import Usuario


def main():
    db = SessionLocal()
    try:
        # Limpiar el flag para superadmin y direccion
        afectados = []
        for username in ['superadmin', 'direccion']:
            u = db.query(Usuario).filter_by(username=username).first()
            if not u:
                print(f"  - Usuario '{username}' no existe, saltando")
                continue
            
            if u.must_change_password:
                u.must_change_password = False
                afectados.append(username)
                print(f"  ✓ {username}: flag limpiado")
            else:
                print(f"  - {username}: ya estaba sin el flag")
            
            # También resetear password al valor estándar
            if username == 'superadmin':
                u.set_password('superadmin123')
                print(f"  ✓ {username}: password reseteada a 'superadmin123'")
            elif username == 'direccion':
                u.set_password('admin123')
                print(f"  ✓ {username}: password reseteada a 'admin123'")
        
        db.commit()
        
        print()
        print("=" * 60)
        print("  Listo. Credenciales:")
        print("    superadmin / superadmin123")
        print("    direccion  / admin123")
        print("=" * 60)
        print()
        print("Eliminá INITIAL_CREDENTIALS.txt si todavía existe en la carpeta.")
    finally:
        db.close()


if __name__ == '__main__':
    main()
