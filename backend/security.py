"""
Módulo de Seguridad Educa One (FastAPI)
=======================
Contiene funciones de seguridad, validaciones y sanitización.
Las funciones JWT y rate-limiting están en auth.py
"""

import re
import html
import hashlib
import secrets
from datetime import datetime, timedelta
import bleach


# ===========================================
# VALIDACIÓN DE CONTRASEÑAS
# ===========================================

def validate_password(password):
    """Valida una contraseña según las reglas mínimas del sistema.
    
    Política aplicada: mínimo 8 caracteres. Es la regla consistente con todos
    los endpoints que ya validan password en app.py. Mantenerla simple evita
    rechazar passwords legítimas en escuelas pequeñas con usuarios poco técnicos.
    
    Si querés política más estricta (mayús, minús, números), descomentá las
    líneas de abajo. NO se aplica por default para no romper retrocompatibilidad
    con usuarios ya creados.
    """
    min_length = 8
    if len(password) < min_length:
        return False, f'La contraseña debe tener al menos {min_length} caracteres'
    # Política estricta opcional (deshabilitada por defecto):
    # if not re.search(r'[A-Z]', password):
    #     return False, 'La contraseña debe tener al menos una letra mayúscula'
    # if not re.search(r'[a-z]', password):
    #     return False, 'La contraseña debe tener al menos una letra minúscula'
    # if not re.search(r'\d', password):
    #     return False, 'La contraseña debe tener al menos un número'
    return True, 'Contraseña válida'


def generate_secure_password(length=12):
    import string
    characters = string.ascii_letters + string.digits + "!@#$%"
    password = ''.join(secrets.choice(characters) for _ in range(length))
    password = (
        secrets.choice(string.ascii_uppercase) +
        secrets.choice(string.ascii_lowercase) +
        secrets.choice(string.digits) +
        password[3:]
    )
    return password


# ===========================================
# SANITIZACIÓN DE INPUTS
# ===========================================

def sanitize_string(value, max_length=500):
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    value = value[:max_length]
    value = bleach.clean(value, tags=[], strip=True)
    value = html.escape(value)
    return value.strip()


def sanitize_html(value, allowed_tags=None):
    if value is None:
        return None
    if allowed_tags is None:
        allowed_tags = ['b', 'i', 'u', 'p', 'br', 'ul', 'ol', 'li', 'strong', 'em']
    return bleach.clean(value, tags=allowed_tags, strip=True)


def validate_email(email):
    if not email:
        return True
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def validate_phone(phone):
    if not phone:
        return True
    clean = re.sub(r'\D', '', phone)
    return len(clean) in [10, 11]


# ===========================================
# UTILIDADES DE SEGURIDAD
# ===========================================

def generate_csrf_token():
    return secrets.token_hex(32)


def hash_sensitive_data(data):
    return hashlib.sha256(data.encode()).hexdigest()
