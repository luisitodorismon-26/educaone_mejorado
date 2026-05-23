"""
Módulo de Validaciones para Educa One (FastAPI)
"""
import re
from datetime import datetime

# ============== VALIDADORES ==============

def validar_email(email):
    if not email:
        return True
    patron = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(patron, email))

def validar_telefono(telefono):
    if not telefono:
        return True
    limpio = re.sub(r'[\s\-\(\)]', '', telefono)
    return bool(re.match(r'^(1)?(809|829|849)\d{7}$', limpio))

def validar_cedula(cedula):
    if not cedula:
        return True
    limpio = re.sub(r'[\s\-]', '', cedula)
    return bool(re.match(r'^\d{11}$', limpio))

def validar_matricula(matricula):
    if not matricula:
        return True
    return bool(re.match(r'^[A-Z0-9\-]{4,20}$', matricula.upper()))

def validar_fecha(fecha_str):
    if not fecha_str:
        return True
    try:
        datetime.strptime(fecha_str, '%Y-%m-%d')
        return True
    except ValueError:
        return False

def validar_hora(hora_str):
    if not hora_str:
        return True
    return bool(re.match(r'^([01]?[0-9]|2[0-3]):[0-5][0-9]$', hora_str))

def validar_nota(nota):
    if nota is None:
        return True
    try:
        n = float(nota)
        return 0 <= n <= 100
    except (ValueError, TypeError):
        return False

def validar_nombre(nombre):
    if not nombre:
        return False
    return bool(re.match(r'^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s]{2,50}$', nombre))

def sanitizar_texto(texto):
    if not texto:
        return texto
    texto = re.sub(r'<[^>]*>', '', texto)
    texto = texto.replace("'", "''")
    return texto.strip()

def sanitizar_html(texto):
    if not texto:
        return texto
    tags_permitidos = ['b', 'i', 'u', 'br', 'p', 'strong', 'em']
    for tag in re.findall(r'</?(\w+)[^>]*>', texto):
        if tag.lower() not in tags_permitidos:
            texto = re.sub(f'</?{tag}[^>]*>', '', texto, flags=re.IGNORECASE)
    return texto

# ============== VALIDADORES DE ENTIDADES ==============

def validar_estudiante(data):
    errores = []
    if not validar_nombre(data.get('nombre')):
        errores.append('Nombre inválido (solo letras, 2-50 caracteres)')
    if not validar_nombre(data.get('apellido')):
        errores.append('Apellido inválido (solo letras, 2-50 caracteres)')
    if not validar_matricula(data.get('matricula')):
        errores.append('Formato de matrícula inválido')
    if not validar_fecha(data.get('fecha_nacimiento')):
        errores.append('Fecha de nacimiento inválida (formato: YYYY-MM-DD)')
    if data.get('sexo') and data['sexo'] not in ['M', 'F']:
        errores.append('Sexo debe ser M o F')
    if not validar_telefono(data.get('telefono_padre')):
        errores.append('Teléfono del padre inválido')
    if not validar_telefono(data.get('telefono_madre')):
        errores.append('Teléfono de la madre inválido')
    if not validar_email(data.get('email')):
        errores.append('Formato de email inválido')
    return errores

def validar_usuario(data, es_edicion=False):
    errores = []
    if not es_edicion:
        if not data.get('username') or len(data['username']) < 3:
            errores.append('Username debe tener al menos 3 caracteres')
        if not re.match(r'^[a-zA-Z0-9_]+$', data.get('username', '')):
            errores.append('Username solo puede contener letras, números y guión bajo')
    if not validar_nombre(data.get('nombre')):
        errores.append('Nombre inválido')
    if not validar_email(data.get('email')):
        errores.append('Email inválido')
    if not validar_telefono(data.get('telefono')):
        errores.append('Teléfono inválido')
    if not validar_cedula(data.get('cedula')):
        errores.append('Cédula inválida')
    roles_validos = ['direccion', 'coordinador', 'profesor', 'psicologia']
    if data.get('role') and data['role'] not in roles_validos:
        errores.append(f'Rol debe ser uno de: {", ".join(roles_validos)}')
    return errores

def validar_password_fuerte(password):
    errores = []
    if len(password) < 8:
        errores.append('Mínimo 8 caracteres')
    if not re.search(r'[A-Z]', password):
        errores.append('Debe contener al menos una mayúscula')
    if not re.search(r'[a-z]', password):
        errores.append('Debe contener al menos una minúscula')
    if not re.search(r'\d', password):
        errores.append('Debe contener al menos un número')
    return errores
