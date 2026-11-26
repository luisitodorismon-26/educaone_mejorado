"""Token de sesión del director SINTÉTICO, firmado con la clave sintética de la
prueba (la misma que recibe el servidor). Corre en un contenedor aparte, fuera
del contenedor limitado, para no sumar memoria al servidor medido."""
import json, os, sys
sys.path.insert(0, '/app')
os.chdir('/tmp')
import logging; logging.disable(logging.WARNING)
from database import SessionLocal
import models as M
from auth import create_token
sem = json.load(open('/out/semilla.json'))
s = SessionLocal()
open('/out/token.txt', 'w').write(create_token(s.get(M.Usuario, sem['director_id'])))
print('token sintético escrito')
