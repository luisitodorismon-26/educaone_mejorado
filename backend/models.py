"""
Educa One - Sistema de Gestión Escolar
Modelos de Base de Datos (SQLAlchemy puro para FastAPI)
"""
import os as _os
from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, Date, DateTime,
    ForeignKey, Table, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date

def _now_dr():
    """Hora actual de República Dominicana (AST, UTC-4)"""
    from datetime import timezone, timedelta
    return datetime.now(timezone(timedelta(hours=-4))).replace(tzinfo=None)

from database import Base

# ============== COLEGIO (MULTI-TENANT) ==============

class Colegio(Base):
    __tablename__ = 'colegios'
    id = Column(Integer, primary_key=True)
    nombre = Column(String(200), nullable=False)
    codigo = Column(String(50), unique=True, nullable=False)  # slug/subdominio
    dominio = Column(String(200))  # dominio personalizado opcional
    activo = Column(Boolean, default=True)
    plan = Column(String(20), default='basico')  # basico, premium, enterprise (etiqueta comercial)
    max_estudiantes = Column(Integer, default=500)
    max_usuarios = Column(Integer, default=50)
    fecha_creacion = Column(DateTime, default=_now_dr)
    fecha_expiracion = Column(Date)
    contacto_nombre = Column(String(100))
    contacto_email = Column(String(100))
    contacto_telefono = Column(String(20))
    notas = Column(Text)
    
    # ═══════════════════════════════════════════════════════════════
    # MÓDULOS DEL PLAN (lo que el contrato comercial PERMITE).
    # Solo el superadmin puede modificar estos campos.
    # Define qué módulos están DISPONIBLES para el colegio.
    # 
    # Para que un módulo esté EFECTIVAMENTE activo se requiere:
    #     plan_X = True (superadmin lo permitió por contrato)
    # Y además que en ConfiguracionColegio:
    #     usa_X = True  (director decidió usarlo)
    # 
    # Esto separa decisiones comerciales (qué se vendió) de las
    # operacionales (qué se usa hoy).
    # ═══════════════════════════════════════════════════════════════
    
    # Niveles educativos
    plan_secundaria = Column(Boolean, default=True, nullable=False)
    plan_primaria = Column(Boolean, default=True, nullable=False)
    plan_inicial = Column(Boolean, default=False, nullable=False)
    
    # Módulos funcionales
    plan_whatsapp = Column(Boolean, default=False, nullable=False)
    plan_psicologia = Column(Boolean, default=False, nullable=False)
    plan_eval_profesores = Column(Boolean, default=True, nullable=False)
    plan_eval_interna = Column(Boolean, default=False, nullable=False)
    plan_comunicacion_padres = Column(Boolean, default=True, nullable=False)
    plan_registro_escolar = Column(Boolean, default=True, nullable=False)
    plan_reportes_conducta = Column(Boolean, default=True, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'nombre': self.nombre,
            'codigo': self.codigo,
            'dominio': self.dominio,
            'activo': self.activo,
            'plan': self.plan,
            'max_estudiantes': self.max_estudiantes,
            'max_usuarios': self.max_usuarios,
            'fecha_creacion': self.fecha_creacion.isoformat() if self.fecha_creacion else None,
            'fecha_expiracion': self.fecha_expiracion.isoformat() if self.fecha_expiracion else None,
            'contacto_nombre': self.contacto_nombre,
            'contacto_email': self.contacto_email,
            'contacto_telefono': self.contacto_telefono,
            # Módulos del plan (superadmin)
            'plan_secundaria': bool(self.plan_secundaria),
            'plan_primaria': bool(self.plan_primaria),
            'plan_inicial': bool(self.plan_inicial),
            'plan_whatsapp': bool(self.plan_whatsapp),
            'plan_psicologia': bool(self.plan_psicologia),
            'plan_eval_profesores': bool(self.plan_eval_profesores),
            'plan_eval_interna': bool(self.plan_eval_interna),
            'plan_comunicacion_padres': bool(self.plan_comunicacion_padres),
            'plan_registro_escolar': bool(self.plan_registro_escolar),
            'plan_reportes_conducta': bool(self.plan_reportes_conducta),
        }


# ============== CONFIGURACIÓN ==============

class ConfiguracionColegio(Base):
    __tablename__ = 'configuracion_colegio'
    id = Column(Integer, primary_key=True)
    colegio_id = Column(Integer, ForeignKey('colegios.id'), nullable=True, index=True)
    nombre = Column(String(200), default='Mi Colegio')
    logo = Column(Text)  # Base64
    rnc = Column(String(20))  # RNC del colegio (para encabezados de PDFs)
    telefono = Column(String(20))
    email = Column(String(100))
    direccion = Column(String(300))
    distrito = Column(String(10))
    regional = Column(String(10))
    lema = Column(String(200))
    director = Column(String(100))
    # Umbrales de alerta
    umbral_calificacion_baja = Column(Integer, default=80)
    umbral_calificacion_critica = Column(Integer, default=70)
    umbral_asistencia_baja = Column(Integer, default=80)
    dias_ausencia_alerta = Column(Integer, default=3)
    dias_ausencia_critica = Column(Integer, default=5)
    
    # Nombres de competencias por período (según MINERD)
    nombre_p1 = Column(String(100), default='Comunicativa')
    nombre_p2 = Column(String(100), default='Pensamiento Lógico, Creativo y Crítico')
    nombre_p3 = Column(String(100), default='Científica y Tecnológica')
    nombre_p4 = Column(String(100), default='Desarrollo Personal')
    
    # ═══════════════════════════════════════════════════════════════
    # USO DE MÓDULOS (lo que el director DECIDE usar día a día).
    # Solo el director puede modificar estos campos (dentro de los
    # límites de su plan: si plan_X=False, no puede encender usa_X).
    # 
    # Para que un módulo esté EFECTIVAMENTE activo se requiere:
    #     Colegio.plan_X = True  (superadmin lo permitió por contrato)
    # Y además:
    #     ConfiguracionColegio.usa_X = True  (director lo encendió)
    # 
    # IMPORTANTE: defaults son False. Ningún módulo se enciende solo —
    # el director debe activarlo explícitamente. Esto evita que módulos
    # aparezcan "activos" en colegios recién creados sin intervención
    # del usuario.
    #
    # TODOS los usa_X tienen default=False. La auto-activación de niveles
    # (cuando plan_X=True, setear usa_X=True) la hace explícitamente
    # crear_colegio en app.py. Esto evita el bug histórico donde un colegio
    # sin primaria arrancaba con usa_primaria=True por culpa de default=True.
    # ═══════════════════════════════════════════════════════════════
    
    # Módulos funcionales — defaults False (el director decide encender)
    usa_whatsapp = Column(Boolean, default=False, nullable=False)
    whatsapp_solo_direccion = Column(Boolean, default=False, nullable=False)  # sub-política, no módulo
    usa_psicologia = Column(Boolean, default=False, nullable=False)
    usa_comunicacion_padres = Column(Boolean, default=False, nullable=False)
    usa_eval_profesores = Column(Boolean, default=False, nullable=False)
    usa_eval_interna = Column(Boolean, default=False, nullable=False)
    usa_registro_escolar = Column(Boolean, default=False, nullable=False)
    usa_reportes_conducta = Column(Boolean, default=False, nullable=False)
    permitir_profesor_reportes = Column(Boolean, default=False, nullable=False)  # sub-política
    
    # Niveles educativos — default=False para evitar inconsistencias con el
    # plan del colegio. El endpoint crear_colegio se encarga de setear usa_X=True
    # solo cuando plan_X=True. Tener default=True acá causaba un bug: un colegio
    # sin primaria en el plan arrancaba con usa_primaria=True, y al intentar
    # cualquier cambio el sistema rechazaba con "no puede activar primaria".
    usa_secundaria = Column(Boolean, default=False, nullable=False)
    usa_primaria = Column(Boolean, default=False, nullable=False)
    usa_inicial = Column(Boolean, default=False, nullable=False)
    
    # ===== DATOS MINERD PARA REGISTRO ESCOLAR =====
    codigo_centro = Column(String(20))                        # Código SIGERD del centro
    codigo_cartografia = Column(String(20))                   # Código cartográfico
    sector = Column(String(20))                               # publico/privado/semioficial
    zona = Column(String(30))                                 # urbana/rural/urbana_marginal/etc
    tanda_operacion = Column(String(30))                      # jee/matutina/vespertina/nocturna
    nivel = Column(String(30), default='Secundario')          # Nivel educativo
    modalidad = Column(String(30), default='General')         # General/Académica/Técnica
    correo_centro = Column(String(100))                       # Email institucional
    nombre_director = Column(String(100))                     # Nombre completo director(a)
    cedula_director = Column(String(20))                      # Cédula del director(a)
    correo_director = Column(String(100))                     # Email del director
    telefono_director = Column(String(20))                    # Tel. director
    nombre_coordinador = Column(String(100))                  # Coordinador académico
    
    # v2.13.1: Días hábiles del colegio para registro de asistencia.
    # Defaults: lunes-viernes activos, sábado y domingo deshabilitados.
    # Un colegio que tiene clases los sábados puede activar permite_sabado=True
    # desde Configuración.
    permite_sabado = Column(Boolean, default=False, nullable=False)
    permite_domingo = Column(Boolean, default=False, nullable=False)

class AnoEscolar(Base):
    __tablename__ = 'ano_escolar'
    id = Column(Integer, primary_key=True)
    colegio_id = Column(Integer, ForeignKey('colegios.id'), nullable=True, index=True)
    nombre = Column(String(20), nullable=False)
    fecha_inicio = Column(Date)
    fecha_fin = Column(Date)
    activo = Column(Boolean, default=False)
    cerrado = Column(Boolean, default=False)
    
    periodo_activo = Column(Integer, default=1)
    
    p1_inicio = Column(Date)
    p1_fin = Column(Date)
    p1_cerrado = Column(Boolean, default=False)
    
    p2_inicio = Column(Date)
    p2_fin = Column(Date)
    p2_cerrado = Column(Boolean, default=False)
    
    p3_inicio = Column(Date)
    p3_fin = Column(Date)
    p3_cerrado = Column(Boolean, default=False)
    
    p4_inicio = Column(Date)
    p4_fin = Column(Date)
    p4_cerrado = Column(Boolean, default=False)
    
    # Días trabajados por mes (JSON): ej {"ago": 8, "sep": 22, "oct": 22, ...}
    # Usado para el Registro Escolar MINERD
    dias_trabajados = Column(Text, default='{}')

    def get_periodo_estado(self, periodo):
        return getattr(self, f'p{periodo}_cerrado', False)
    
    def puede_editar_periodo(self, periodo):
        return self.periodo_activo == periodo and not getattr(self, f'p{periodo}_cerrado', True)
    
    def get_dias_trabajados(self) -> dict:
        """Devuelve el dict de días trabajados por mes."""
        import json
        try:
            return json.loads(self.dias_trabajados or '{}')
        except Exception:
            return {}
    
    def set_dias_trabajados(self, data: dict):
        import json
        self.dias_trabajados = json.dumps(data or {})


class SolicitudEdicionNota(Base):
    __tablename__ = 'solicitudes_edicion_nota'
    id = Column(Integer, primary_key=True)
    colegio_id = Column(Integer, ForeignKey('colegios.id'), nullable=True, index=True)
    calificacion_id = Column(Integer, ForeignKey('calificaciones.id'), nullable=False)
    profesor_id = Column(Integer, ForeignKey('usuarios.id'), nullable=False, index=True)
    periodo = Column(Integer, nullable=False)
    campo = Column(String(20), nullable=False)
    valor_actual = Column(Float)
    valor_nuevo = Column(Float)
    motivo = Column(Text, nullable=False)
    fecha_solicitud = Column(DateTime, default=_now_dr)
    estado = Column(String(20), default='pendiente')
    revisado_por = Column(Integer, ForeignKey('usuarios.id'))
    fecha_revision = Column(DateTime)
    comentario_revision = Column(Text)
    
    calificacion = relationship('Calificacion', backref='solicitudes_edicion')
    profesor = relationship('Usuario', foreign_keys=[profesor_id], backref='solicitudes_edicion_creadas')
    revisor = relationship('Usuario', foreign_keys=[revisado_por], backref='solicitudes_edicion_revisadas')

# ============== USUARIOS ==============

usuario_tandas = Table('usuario_tandas', Base.metadata,
    Column('usuario_id', Integer, ForeignKey('usuarios.id'), primary_key=True),
    Column('tanda_id', Integer, ForeignKey('tandas.id'), primary_key=True)
)

class Usuario(Base):
    __tablename__ = 'usuarios'
    id = Column(Integer, primary_key=True)
    colegio_id = Column(Integer, ForeignKey('colegios.id'), nullable=True, index=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(256), nullable=False)
    nombre = Column(String(50), nullable=False)
    apellido = Column(String(50))
    email = Column(String(100))
    telefono = Column(String(20))
    cedula = Column(String(15))
    role = Column(String(20), nullable=False)
    tanda_id = Column(Integer, ForeignKey('tandas.id'))
    activo = Column(Boolean, default=True)
    # Si es True, el usuario no puede usar el sistema hasta que cambie su password.
    # Se setea en True cuando: (a) init_db crea credenciales por defecto, o (b) un admin
    # resetea la password de otro usuario. Se limpia al cambiar password vía /api/auth/cambiar-password.
    must_change_password = Column(Boolean, default=False, nullable=False)
    # Versión del token. Cada vez que se incrementa, los tokens previamente
    # emitidos quedan invalidados (en decode_token se valida que coincida).
    # Se incrementa al hacer logout, al cambiar password, y cuando un admin
    # resetea credenciales. Esto da invalidación real de sesiones.
    token_version = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=_now_dr)
    last_login = Column(DateTime)

    colegio = relationship('Colegio', backref='usuarios')
    tanda = relationship('Tanda', backref='usuarios_principal', foreign_keys=[tanda_id])
    tandas = relationship('Tanda', secondary=usuario_tandas, backref='profesores')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_authenticated(self):
        return True

    @property
    def nombre_completo(self):
        return f"{self.nombre} {self.apellido or ''}".strip()

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'nombre': self.nombre,
            'apellido': self.apellido,
            'nombre_completo': self.nombre_completo,
            'email': self.email,
            'telefono': self.telefono,
            'role': self.role,
            'tanda_id': self.tanda_id,
            'tanda': self.tanda.nombre if self.tanda else None,
            'tandas': [{'id': t.id, 'nombre': t.nombre} for t in self.tandas] if self.tandas else [],
            'activo': self.activo,
            'must_change_password': bool(self.must_change_password),
            'colegio_id': self.colegio_id
        }

# ============== ESTRUCTURA ACADÉMICA ==============

class Grado(Base):
    __tablename__ = 'grados'
    id = Column(Integer, primary_key=True)
    colegio_id = Column(Integer, ForeignKey('colegios.id'), nullable=True, index=True)
    nombre = Column(String(50), nullable=False)
    nivel = Column(String(20), default='secundaria')  # 'primaria' o 'secundaria'
    ciclo = Column(String(20))  # 'primer_ciclo' (1-3) o 'segundo_ciclo' (4-6)
    orden = Column(Integer, default=0)
    activo = Column(Boolean, default=True)

class Tanda(Base):
    __tablename__ = 'tandas'
    id = Column(Integer, primary_key=True)
    colegio_id = Column(Integer, ForeignKey('colegios.id'), nullable=True, index=True)
    nombre = Column(String(50), nullable=False)
    hora_inicio = Column(String(5))
    hora_fin = Column(String(5))
    activo = Column(Boolean, default=True)

class Recreo(Base):
    __tablename__ = 'recreos'
    id = Column(Integer, primary_key=True)
    colegio_id = Column(Integer, ForeignKey('colegios.id'), nullable=True, index=True)
    tanda_id = Column(Integer, ForeignKey('tandas.id'), nullable=False)
    nombre = Column(String(50), default='Recreo')
    hora_inicio = Column(String(5), nullable=False)
    hora_fin = Column(String(5), nullable=False)
    activo = Column(Boolean, default=True)
    
    tanda = relationship('Tanda', backref='recreos')

class BloqueHorario(Base):
    __tablename__ = 'bloques_horario'
    id = Column(Integer, primary_key=True)
    colegio_id = Column(Integer, ForeignKey('colegios.id'), nullable=True, index=True)
    tanda_id = Column(Integer, ForeignKey('tandas.id'), nullable=False)
    numero = Column(Integer, nullable=False)
    hora_inicio = Column(String(5), nullable=False)
    hora_fin = Column(String(5), nullable=False)
    duracion_minutos = Column(Integer, default=45)
    es_recreo = Column(Boolean, default=False)
    nombre = Column(String(50))
    activo = Column(Boolean, default=True)
    
    tanda = relationship('Tanda', backref='bloques')
    
    def to_dict(self):
        return {
            'id': self.id,
            'tanda_id': self.tanda_id,
            'numero': self.numero,
            'hora_inicio': self.hora_inicio,
            'hora_fin': self.hora_fin,
            'duracion_minutos': self.duracion_minutos,
            'es_recreo': self.es_recreo,
            'nombre': self.nombre or f'Bloque {self.numero}'
        }

class Asignatura(Base):
    __tablename__ = 'asignaturas'
    id = Column(Integer, primary_key=True)
    colegio_id = Column(Integer, ForeignKey('colegios.id'), nullable=True, index=True)
    nombre = Column(String(100), nullable=False)
    codigo = Column(String(10))
    area = Column(String(50))
    activo = Column(Boolean, default=True)

class Curso(Base):
    __tablename__ = 'cursos'
    id = Column(Integer, primary_key=True)
    colegio_id = Column(Integer, ForeignKey('colegios.id'), nullable=True, index=True)
    nombre = Column(String(10), nullable=False)
    grado_id = Column(Integer, ForeignKey('grados.id'), nullable=False, index=True)
    tanda_id = Column(Integer, ForeignKey('tandas.id'), nullable=True)
    ano_escolar_id = Column(Integer, ForeignKey('ano_escolar.id'))
    capacidad = Column(Integer, default=35)
    aula = Column(String(20))
    activo = Column(Boolean, default=True)

    grado = relationship('Grado', backref='cursos')
    tanda = relationship('Tanda', backref='cursos')
    ano_escolar = relationship('AnoEscolar', backref='cursos')

    @property
    def nombre_completo(self):
        if self.grado and self.tanda:
            return f"{self.grado.nombre} {self.nombre} - {self.tanda.nombre}"
        elif self.grado:
            return f"{self.grado.nombre} {self.nombre}"
        return self.nombre
    
    @property
    def seccion(self):
        return self.nombre
    
    def to_dict(self):
        return {
            'id': self.id,
            'nombre': self.nombre,
            'seccion': self.nombre,
            'grado_id': self.grado_id,
            'grado': self.grado.nombre if self.grado else None,
            'tanda_id': self.tanda_id,
            'tanda': self.tanda.nombre if self.tanda else None,
            'nombre_completo': self.nombre_completo,
            'capacidad': self.capacidad,
            'aula': self.aula,
            'estudiantes_count': len([e for e in self.estudiantes if e.activo]) if hasattr(self, 'estudiantes') else 0
        }

# ============== ESTUDIANTES ==============

class Estudiante(Base):
    __tablename__ = 'estudiantes'
    id = Column(Integer, primary_key=True)
    colegio_id = Column(Integer, ForeignKey('colegios.id'), nullable=True, index=True)
    matricula = Column(String(20))
    nombre = Column(String(50), nullable=False)
    apellido = Column(String(50), nullable=False)
    fecha_nacimiento = Column(Date)
    sexo = Column(String(1))
    lugar_nacimiento = Column(String(100))
    nacionalidad = Column(String(50), default='Dominicana')
    direccion = Column(String(300))
    telefono = Column(String(20))
    email = Column(String(100))
    foto = Column(Text)
    curso_id = Column(Integer, ForeignKey('cursos.id'), index=True)
    no_lista = Column(Integer)
    condicion = Column(String(20), default='activo')
    fecha_ingreso = Column(Date, default=date.today)
    activo = Column(Boolean, default=True)
    
    fecha_retiro = Column(Date)
    motivo_retiro = Column(String(300))
    retirado_por = Column(Integer, ForeignKey('usuarios.id'))
    
    nombre_padre = Column(String(100))
    cedula_padre = Column(String(15))
    telefono_padre = Column(String(20))
    trabajo_padre = Column(String(100))
    nombre_madre = Column(String(100))
    cedula_madre = Column(String(15))
    telefono_madre = Column(String(20))
    trabajo_madre = Column(String(100))
    tutor = Column(String(100))
    telefono_tutor = Column(String(20))
    parentesco_tutor = Column(String(50))               # Parentesco del tutor con el estudiante
    
    # Datos MINERD adicionales para registro escolar
    cedula = Column(String(20))                          # Cédula o documento del estudiante
    condicion_entrada = Column(String(30), default='nuevo')  # nuevo/repitente/transferido
    escuela_procedencia = Column(String(200))            # Escuela anterior
    contacto_emergencia = Column(String(100))            # Nombre contacto de emergencia
    telefono_emergencia = Column(String(20))             # Tel. emergencia
    nee = Column(Text)                                   # Necesidades educativas especiales
    
    tipo_sangre = Column(String(5))
    alergias = Column(Text)
    condiciones_medicas = Column(Text)
    seguro_medico = Column(String(100))

    curso = relationship('Curso', backref='estudiantes')

    @property
    def nombre_completo(self):
        return f"{self.nombre} {self.apellido}"

    @property
    def edad(self):
        if self.fecha_nacimiento:
            today = date.today()
            return today.year - self.fecha_nacimiento.year - ((today.month, today.day) < (self.fecha_nacimiento.month, self.fecha_nacimiento.day))
        return None

    def to_dict(self):
        # Normalizar nivel a valor canónico ('primaria' | 'secundaria' | 'inicial')
        # Datos viejos pueden tener 'Secundario', 'Primario', NULL, etc.
        raw_nivel = (self.curso.grado.nivel if self.curso and self.curso.grado else None)
        if raw_nivel:
            low = str(raw_nivel).lower().strip()
            if low.startswith('prim'):
                nivel_canonico = 'primaria'
            elif low.startswith('sec'):
                nivel_canonico = 'secundaria'
            elif low.startswith('ini') or low.startswith('prees') or low.startswith('pre-'):
                nivel_canonico = 'inicial'
            else:
                nivel_canonico = 'secundaria'
        else:
            nivel_canonico = 'secundaria' if self.curso else None
        
        return {
            'id': self.id,
            'matricula': self.matricula,
            'nombre': self.nombre,
            'apellido': self.apellido,
            'nombre_completo': self.nombre_completo,
            'fecha_nacimiento': self.fecha_nacimiento.isoformat() if self.fecha_nacimiento else None,
            'edad': self.edad,
            'sexo': self.sexo,
            'lugar_nacimiento': self.lugar_nacimiento,
            'nacionalidad': self.nacionalidad,
            'cedula': self.cedula,
            'direccion': self.direccion,
            'telefono': self.telefono,
            'email': self.email,
            'foto': self.foto,
            'curso_id': self.curso_id,
            'curso': self.curso.nombre_completo if self.curso else None,
            'grado': self.curso.grado.nombre if self.curso and self.curso.grado else None,
            'nivel': nivel_canonico,
            'ciclo': self.curso.grado.ciclo if self.curso and self.curso.grado else None,
            'tanda': self.curso.tanda.nombre if self.curso and self.curso.tanda else None,
            'no_lista': self.no_lista,
            'condicion': self.condicion,
            'condicion_entrada': self.condicion_entrada,
            'escuela_procedencia': self.escuela_procedencia,
            'fecha_ingreso': self.fecha_ingreso.isoformat() if self.fecha_ingreso else None,
            'activo': self.activo,
            # Retiro
            'fecha_retiro': self.fecha_retiro.isoformat() if self.fecha_retiro else None,
            'motivo_retiro': self.motivo_retiro,
            # Padre
            'nombre_padre': self.nombre_padre,
            'cedula_padre': self.cedula_padre,
            'telefono_padre': self.telefono_padre,
            'trabajo_padre': self.trabajo_padre,
            # Madre
            'nombre_madre': self.nombre_madre,
            'cedula_madre': self.cedula_madre,
            'telefono_madre': self.telefono_madre,
            'trabajo_madre': self.trabajo_madre,
            # Tutor
            'tutor': self.tutor,
            'telefono_tutor': self.telefono_tutor,
            'parentesco_tutor': self.parentesco_tutor,
            # Salud y emergencia
            'contacto_emergencia': self.contacto_emergencia,
            'telefono_emergencia': self.telefono_emergencia,
            'nee': self.nee,
            'tipo_sangre': self.tipo_sangre,
            'alergias': self.alergias,
            'condiciones_medicas': self.condiciones_medicas,
            'seguro_medico': self.seguro_medico,
        }

# ============== ASIGNACIONES Y HORARIOS ==============

class AsignacionProfesor(Base):
    __tablename__ = 'asignaciones_profesor'
    id = Column(Integer, primary_key=True)
    colegio_id = Column(Integer, ForeignKey('colegios.id'), nullable=True, index=True)
    profesor_id = Column(Integer, ForeignKey('usuarios.id'), nullable=False, index=True)
    curso_id = Column(Integer, ForeignKey('cursos.id'), nullable=False, index=True)
    asignatura_id = Column(Integer, ForeignKey('asignaturas.id'), nullable=False)
    ano_escolar_id = Column(Integer, ForeignKey('ano_escolar.id'))
    es_titular = Column(Boolean, default=False)
    activo = Column(Boolean, default=True)

    profesor = relationship('Usuario', backref='asignaciones')
    curso = relationship('Curso', backref='asignaciones')
    asignatura = relationship('Asignatura', backref='asignaciones')

    def to_dict(self):
        return {
            'id': self.id,
            'profesor_id': self.profesor_id,
            'profesor': self.profesor.nombre_completo if self.profesor else None,
            'curso_id': self.curso_id,
            'curso': self.curso.nombre_completo if self.curso else None,
            'asignatura_id': self.asignatura_id,
            'asignatura': self.asignatura.nombre if self.asignatura else None,
            'es_titular': self.es_titular,
            'activo': self.activo
        }

class Horario(Base):
    __tablename__ = 'horarios'
    id = Column(Integer, primary_key=True)
    colegio_id = Column(Integer, ForeignKey('colegios.id'), nullable=True, index=True)
    profesor_id = Column(Integer, ForeignKey('usuarios.id'), nullable=False, index=True)
    curso_id = Column(Integer, ForeignKey('cursos.id'), index=True)
    asignatura_id = Column(Integer, ForeignKey('asignaturas.id'), index=True)
    dia = Column(String(15), nullable=False, index=True)
    hora_inicio = Column(String(5), nullable=False)
    hora_fin = Column(String(5), nullable=False)
    aula = Column(String(20))
    tipo_bloque = Column(String(20), default='clase')
    activo = Column(Boolean, default=True)
    
    __table_args__ = (
        # GET /api/horarios/profesor/{id} ordena por (dia, hora_inicio)
        Index('ix_horario_profesor_dia', 'profesor_id', 'dia'),
        # GET /api/horarios/curso/{id} ordena por (dia, hora_inicio)
        Index('ix_horario_curso_dia', 'curso_id', 'dia'),
    )

    profesor = relationship('Usuario', backref='horarios')
    curso = relationship('Curso', backref='horarios')
    asignatura = relationship('Asignatura', backref='horarios')
    
    @property
    def es_libre(self):
        return self.tipo_bloque == 'libre'
    
    @property
    def es_recreo(self):
        return self.tipo_bloque == 'recreo'

    def to_dict(self):
        return {
            'id': self.id,
            'profesor_id': self.profesor_id,
            'curso_id': self.curso_id,
            'curso': self.curso.nombre_completo if self.curso else None,
            'tanda': self.curso.tanda.nombre if self.curso and self.curso.tanda else None,
            'asignatura_id': self.asignatura_id,
            'asignatura': self.asignatura.nombre if self.asignatura else None,
            'dia': self.dia,
            'hora_inicio': self.hora_inicio,
            'hora_fin': self.hora_fin,
            'aula': self.aula,
            'tipo_bloque': self.tipo_bloque or 'clase'
        }

# ============== CALIFICACIONES ==============

class Calificacion(Base):
    __tablename__ = 'calificaciones'
    id = Column(Integer, primary_key=True)
    colegio_id = Column(Integer, ForeignKey('colegios.id'), nullable=True, index=True)
    estudiante_id = Column(Integer, ForeignKey('estudiantes.id'), nullable=False, index=True)
    asignatura_id = Column(Integer, ForeignKey('asignaturas.id'), nullable=False, index=True)
    ano_escolar_id = Column(Integer, ForeignKey('ano_escolar.id'))
    
    p1_p1 = Column(Float); p1_p2 = Column(Float); p1_p3 = Column(Float); p1_p4 = Column(Float)
    rp1_p1 = Column(Float); rp1_p2 = Column(Float); rp1_p3 = Column(Float); rp1_p4 = Column(Float)
    pc1 = Column(Float); rp1 = Column(Float)
    
    p2_p1 = Column(Float); p2_p2 = Column(Float); p2_p3 = Column(Float); p2_p4 = Column(Float)
    rp2_p1 = Column(Float); rp2_p2 = Column(Float); rp2_p3 = Column(Float); rp2_p4 = Column(Float)
    pc2 = Column(Float); rp2 = Column(Float)
    
    p3_p1 = Column(Float); p3_p2 = Column(Float); p3_p3 = Column(Float); p3_p4 = Column(Float)
    rp3_p1 = Column(Float); rp3_p2 = Column(Float); rp3_p3 = Column(Float); rp3_p4 = Column(Float)
    pc3 = Column(Float); rp3 = Column(Float)
    
    p4_p1 = Column(Float); p4_p2 = Column(Float); p4_p3 = Column(Float); p4_p4 = Column(Float)
    rp4_p1 = Column(Float); rp4_p2 = Column(Float); rp4_p3 = Column(Float); rp4_p4 = Column(Float)
    pc4 = Column(Float); rp4 = Column(Float)
    
    cf = Column(Float)
    literal = Column(String(2))

    __table_args__ = (
        # Índice compuesto: lookups (estudiante_id, asignatura_id) son muy frecuentes
        # (cada vez que se consulta o guarda una calificación)
        Index('ix_calificacion_est_asig', 'estudiante_id', 'asignatura_id'),
        # Para reportes por colegio + asignatura
        Index('ix_calificacion_colegio_asig', 'colegio_id', 'asignatura_id'),
    )

    estudiante = relationship('Estudiante', backref='calificaciones')
    asignatura = relationship('Asignatura', backref='calificaciones')

    def calcular_pc(self, periodo):
        """Promedio del período MINERD: por cada parcial usa max(P, RP) si ambos existen.
        
        Si hay RP (recuperación) se asume que reemplaza al P original solo si es mejor.
        La nota final del parcial es siempre la más alta entre P y RP.
        """
        valores = []
        for i in range(1, 5):
            p = getattr(self, f'p{periodo}_p{i}')
            rp = getattr(self, f'rp{periodo}_p{i}')
            # Si hay RP se toma el mayor entre P y RP (RP nunca baja la nota)
            if rp is not None and p is not None:
                val = max(p, rp)
            elif rp is not None:
                val = rp
            elif p is not None:
                val = p
            else:
                val = None
            if val is not None:
                valores.append(val)
        # Solo calcular si hay los 4 parciales
        if len(valores) == 4:
            return round(sum(valores) / 4, 2)
        return None

    def calcular_cf(self):
        """Calificación final: promedio de PC1-PC4 (cada PC ya incluye sus RP por parcial)"""
        notas = []
        for p in range(1, 5):
            pc = getattr(self, f'pc{p}')
            if pc is not None:
                notas.append(pc)
        if len(notas) == 4:
            return round(sum(notas) / 4, 2)
        return None

    def get_literal(self, nota=None):
        if nota is None:
            nota = self.cf
        if nota is None:
            return None
        if nota >= 90: return 'A'
        elif nota >= 80: return 'B'
        elif nota >= 70: return 'C'
        else: return 'F'
    
    def to_dict(self):
        return {
            'id': self.id,
            'estudiante_id': self.estudiante_id,
            'estudiante': self.estudiante.nombre_completo if self.estudiante else None,
            'asignatura_id': self.asignatura_id,
            'asignatura': self.asignatura.nombre if self.asignatura else None,
            'p1_p1': self.p1_p1, 'p1_p2': self.p1_p2, 'p1_p3': self.p1_p3, 'p1_p4': self.p1_p4,
            'rp1_p1': self.rp1_p1, 'rp1_p2': self.rp1_p2, 'rp1_p3': self.rp1_p3, 'rp1_p4': self.rp1_p4,
            'pc1': self.pc1, 'rp1': self.rp1,
            'p2_p1': self.p2_p1, 'p2_p2': self.p2_p2, 'p2_p3': self.p2_p3, 'p2_p4': self.p2_p4,
            'rp2_p1': self.rp2_p1, 'rp2_p2': self.rp2_p2, 'rp2_p3': self.rp2_p3, 'rp2_p4': self.rp2_p4,
            'pc2': self.pc2, 'rp2': self.rp2,
            'p3_p1': self.p3_p1, 'p3_p2': self.p3_p2, 'p3_p3': self.p3_p3, 'p3_p4': self.p3_p4,
            'rp3_p1': self.rp3_p1, 'rp3_p2': self.rp3_p2, 'rp3_p3': self.rp3_p3, 'rp3_p4': self.rp3_p4,
            'pc3': self.pc3, 'rp3': self.rp3,
            'p4_p1': self.p4_p1, 'p4_p2': self.p4_p2, 'p4_p3': self.p4_p3, 'p4_p4': self.p4_p4,
            'rp4_p1': self.rp4_p1, 'rp4_p2': self.rp4_p2, 'rp4_p3': self.rp4_p3, 'rp4_p4': self.rp4_p4,
            'pc4': self.pc4, 'rp4': self.rp4,
            'cf': self.cf, 'literal': self.literal
        }

# ============== CALIFICACIONES PRIMARIA (nueva estructura MINERD) ==============

class AreaCurricular(Base):
    """Catálogo de áreas curriculares por nivel y ciclo (MINERD)
    
    Ejemplo: 'Lengua Española' (primaria 1er ciclo, 3 competencias)
             'Lenguas Extranjeras' (primaria 2do ciclo, 2 competencias)
    """
    __tablename__ = 'areas_curriculares'
    id = Column(Integer, primary_key=True)
    colegio_id = Column(Integer, ForeignKey('colegios.id'), nullable=True, index=True)
    nombre = Column(String(100), nullable=False)                    # 'Lengua Española'
    codigo = Column(String(20))                                     # 'LE', 'MA', 'CS', etc
    nivel = Column(String(20), default='primaria')                  # 'primaria' | 'secundaria'
    ciclo = Column(String(20))                                      # 'primer_ciclo' | 'segundo_ciclo'
    numero_competencias = Column(Integer, default=3)                # Primaria: 3, Inglés: 2
    orden = Column(Integer, default=0)
    activo = Column(Boolean, default=True)

class CalificacionPrimaria(Base):
    """Calificaciones para nivel primario (estructura MINERD real)
    
    Cada área tiene 3 competencias (C1, C2, C3), excepto Inglés que tiene 2.
    Cada competencia se evalúa con UNA nota por período (P1, P2, P3, P4) y su recuperación.
    El promedio de los 4 períodos = nota de la competencia (C1/C2/C3).
    La CF del área es el promedio de las competencias (se calcula a nivel asignatura).
    """
    __tablename__ = 'calificaciones_primaria'
    id = Column(Integer, primary_key=True)
    colegio_id = Column(Integer, ForeignKey('colegios.id'), nullable=True, index=True)
    estudiante_id = Column(Integer, ForeignKey('estudiantes.id'), nullable=False, index=True)
    asignatura_id = Column(Integer, ForeignKey('asignaturas.id'), nullable=False, index=True)
    ano_escolar_id = Column(Integer, ForeignKey('ano_escolar.id'))
    
    # Qué competencia es (1, 2 o 3)
    competencia_numero = Column(Integer, nullable=False)            # 1, 2, o 3
    competencia_nombre = Column(String(100))                        # 'Comunicativa', etc.
    
    # Una nota por período + su recuperación (estructura MINERD primaria)
    p1 = Column(Float); rp1 = Column(Float)
    p2 = Column(Float); rp2 = Column(Float)
    p3 = Column(Float); rp3 = Column(Float)
    p4 = Column(Float); rp4 = Column(Float)
    
    # Nota final de la competencia (promedio de los 4 períodos)
    final_competencia = Column(Float)                               # Esto es C1, C2 o C3
    literal = Column(String(2))
    
    __table_args__ = (
        UniqueConstraint('estudiante_id', 'asignatura_id', 'competencia_numero', 'ano_escolar_id', 
                        name='uq_calif_primaria'),
    )
    
    estudiante = relationship('Estudiante', backref='calificaciones_primaria')
    asignatura = relationship('Asignatura', backref='calificaciones_primaria')
    
    def valor_periodo(self, periodo):
        """Valor final del período: max(P, RP) si hay RP, si no P"""
        p = getattr(self, f'p{periodo}')
        rp = getattr(self, f'rp{periodo}')
        if rp is not None and p is not None:
            return max(p, rp)
        elif rp is not None:
            return rp
        elif p is not None:
            return p
        return None
    
    def calcular_final(self, minimo_periodos=1):
        """Final de la competencia = promedio de los períodos EVALUADOS.

        Regla oficial MINERD primaria (Registro, pág. 85): "En caso de que un
        estudiante tenga indicado (NE) en algún período, la calificación final
        de la competencia se obtiene del promedio de los períodos evaluados."
        Un período NE = valor None (no cargado). Se promedian los que sí tienen
        valor. Requiere al menos `minimo_periodos` evaluado(s).
        """
        valores = []
        for p in range(1, 5):
            v = self.valor_periodo(p)
            if v is not None:
                valores.append(v)
        if len(valores) >= minimo_periodos and valores:
            return round(sum(valores) / len(valores), 2)
        return None
    
    def get_literal(self, nota=None):
        if nota is None:
            nota = self.final_competencia
        if nota is None:
            return None
        if nota >= 90: return 'A'
        elif nota >= 80: return 'B'
        elif nota >= 70: return 'C'
        else: return 'F'
    
    def to_dict(self):
        return {
            'id': self.id,
            'estudiante_id': self.estudiante_id,
            'asignatura_id': self.asignatura_id,
            'asignatura': self.asignatura.nombre if self.asignatura else None,
            'competencia_numero': self.competencia_numero,
            'competencia_nombre': self.competencia_nombre,
            'p1': self.p1, 'rp1': self.rp1,
            'p2': self.p2, 'rp2': self.rp2,
            'p3': self.p3, 'rp3': self.rp3,
            'p4': self.p4, 'rp4': self.rp4,
            'final_competencia': self.final_competencia,
            'literal': self.literal
        }


# ============== CALIFICACIONES SECUNDARIA v2.12 (estructura MINERD oficial) ==============
#
# Estructura MINERD oficial de SECUNDARIA:
# - 4 Competencias Específicas por materia (vs 3 en primaria)
# - Cada competencia tiene 4 períodos (P1-P4) + recuperación (RP) por período
# - El Promedio del Período (PC) = MAX(P, RP) promediado entre las 4 competencias
# - Cálculo Final del Área (CF) = promedio de PC1-PC4
# - Si CF < 70 → evaluación completiva (50% CF + 50% examen)
# - Si completiva < 70 → extraordinaria (30% CF + 70% examen)
# - Si extraordinaria < 70 → evaluación especial (suma simple)
#
# Una fila = un estudiante + una asignatura + una competencia.
# Para una materia completa = 4 filas (una por competencia).
#
# Las evaluaciones extra (completiva/extra/especial) NO van acá — están en
# EvaluacionExtraSecundaria porque son a nivel materia, no a nivel competencia.

class CalificacionSecundaria(Base):
    """Calificaciones secundaria v2.12 con estructura oficial MINERD por competencia."""
    __tablename__ = 'calificaciones_secundaria'
    id = Column(Integer, primary_key=True)
    colegio_id = Column(Integer, ForeignKey('colegios.id'), nullable=True, index=True)
    estudiante_id = Column(Integer, ForeignKey('estudiantes.id'), nullable=False, index=True)
    asignatura_id = Column(Integer, ForeignKey('asignaturas.id'), nullable=False, index=True)
    ano_escolar_id = Column(Integer, ForeignKey('ano_escolar.id'))
    
    # Número de competencia (1-4 en secundaria)
    # Sin nombre — el boletín oficial solo dice "Competencia 1, 2, 3, 4"
    competencia_numero = Column(Integer, nullable=False)
    
    # Una nota por período + recuperación
    p1 = Column(Float); rp1 = Column(Float)
    p2 = Column(Float); rp2 = Column(Float)
    p3 = Column(Float); rp3 = Column(Float)
    p4 = Column(Float); rp4 = Column(Float)
    
    # Cache del promedio de la competencia (se recalcula al guardar)
    promedio_competencia = Column(Float)
    
    __table_args__ = (
        UniqueConstraint('estudiante_id', 'asignatura_id', 'competencia_numero', 'ano_escolar_id',
                        name='uq_calif_secundaria'),
    )
    
    estudiante = relationship('Estudiante', backref='calificaciones_secundaria')
    asignatura = relationship('Asignatura', backref='calificaciones_secundaria')
    
    def valor_periodo(self, periodo):
        """Valor efectivo del período: max(P, RP) si hay RP, sino P solo."""
        p = getattr(self, f'p{periodo}')
        rp = getattr(self, f'rp{periodo}')
        if rp is not None and p is not None:
            return max(p, rp)
        if rp is not None:
            return rp
        if p is not None:
            return p
        return None
    
    def calcular_promedio_competencia(self):
        """Promedio de la competencia = AVG(MAX(P,RP) de los 4 períodos).
        
        Solo se calcula si están los 4 períodos cargados. Redondeado a 1 decimal.
        """
        valores = []
        for p in range(1, 5):
            v = self.valor_periodo(p)
            if v is not None:
                valores.append(v)
        if len(valores) == 4:
            return round(sum(valores) / 4, 1)
        return None
    
    @staticmethod
    def calcular_pc_periodo(competencias_lista, periodo):
        """Calcula PC del período: promedio de las 4 competencias en ese período.
        
        Args:
            competencias_lista: lista de CalificacionSecundaria de la materia (idealmente 4)
            periodo: 1, 2, 3 o 4
        
        Returns:
            float redondeado a 1 decimal, o None si falta alguna competencia en ese período.
        """
        if not competencias_lista:
            return None
        valores = []
        for comp in competencias_lista:
            v = comp.valor_periodo(periodo)
            if v is not None:
                valores.append(v)
        # Necesitamos las 4 competencias evaluadas en ese período
        if len(valores) < 4:
            return None
        return round(sum(valores) / 4, 1)
    
    @staticmethod
    def calcular_a_r_periodo(competencias_lista, periodo):
        """Cuenta A (aprobadas) y R (reprobadas) en un período.
        
        Una competencia se cuenta como aprobada si valor_periodo >= 70.
        Solo cuenta las que tienen nota cargada.
        
        Returns:
            dict con {'a': int, 'r': int, 'pendientes': int}
        """
        a = 0
        r = 0
        pendientes = 0
        for comp in competencias_lista:
            v = comp.valor_periodo(periodo)
            if v is None:
                pendientes += 1
            elif v >= 70:
                a += 1
            else:
                r += 1
        return {'a': a, 'r': r, 'pendientes': pendientes}
    
    def to_dict(self):
        return {
            'id': self.id,
            'estudiante_id': self.estudiante_id,
            'asignatura_id': self.asignatura_id,
            'asignatura': self.asignatura.nombre if self.asignatura else None,
            'competencia_numero': self.competencia_numero,
            'p1': self.p1, 'rp1': self.rp1,
            'p2': self.p2, 'rp2': self.rp2,
            'p3': self.p3, 'rp3': self.rp3,
            'p4': self.p4, 'rp4': self.rp4,
            'promedio_competencia': self.promedio_competencia,
        }


class EvaluacionExtraSecundaria(Base):
    """Evaluaciones extra (Completiva/Extraordinaria/Especial) por estudiante + materia.
    
    Solo aplica si CF < 70 (estudiante reprobó el año normal en esa materia).
    Una fila por estudiante + asignatura. El sistema decide automáticamente qué
    fase está activa según la cascada MINERD oficial.
    
    Fórmulas oficiales (verificadas en Excel MINERD):
      Completiva final = ROUND(50% × CF + 50% × C.E.C., 0)
      Extraordinaria final = ROUND(30% × CF + 70% × C.E.EX, 0)
      Especial final = CF original + C.E.  (≥70 aprueba)
    
    Quién entra qué:
      - Profesor → SOLO C.E.C., C.E.EX, C.E. (las notas que él evalúa)
      - Sistema → calcula todo lo derivado automáticamente
      - Coordinador/Director → gestionan, no entran notas de evaluación
    """
    __tablename__ = 'evaluaciones_extra_secundaria'
    id = Column(Integer, primary_key=True)
    colegio_id = Column(Integer, ForeignKey('colegios.id'), nullable=True, index=True)
    estudiante_id = Column(Integer, ForeignKey('estudiantes.id'), nullable=False, index=True)
    asignatura_id = Column(Integer, ForeignKey('asignaturas.id'), nullable=False, index=True)
    ano_escolar_id = Column(Integer, ForeignKey('ano_escolar.id'))
    
    # CF original (cache de calcular_cf_secundaria)
    cf_original = Column(Float)
    
    # COMPLETIVA — fase 1
    cec = Column(Float)                  # C.E.C. = nota examen completivo (manual)
    completiva_final = Column(Float)     # = ROUND(50%*CF + 50%*CEC, 0) auto
    
    # EXTRAORDINARIA — fase 2 (si completiva_final < 70)
    ceex = Column(Float)                 # C.E.EX = nota examen extraordinario (manual)
    extraordinaria_final = Column(Float) # = ROUND(30%*CF + 70%*CEEX, 0) auto
    
    # ESPECIAL — fase 3 (si extraordinaria_final < 70)
    ce = Column(Float)                   # C.E. = trabajo especial (manual)
    especial_final = Column(Float)       # = CF + CE auto
    
    # CONDICIÓN FINAL (calculada automáticamente)
    # Valores: 'aprobado_normal', 'aprobado_completiva',
    #          'aprobado_extraordinaria', 'aprobado_especial', 'reprobado'
    condicion_final = Column(String(30))
    nota_final = Column(Float)           # la nota que se usa en el boletín
    
    # Auditoría
    actualizado_en = Column(DateTime, default=_now_dr, onupdate=_now_dr)
    
    __table_args__ = (
        UniqueConstraint('estudiante_id', 'asignatura_id', 'ano_escolar_id',
                        name='uq_eval_extra_sec'),
    )
    
    estudiante = relationship('Estudiante', backref='evaluaciones_extra')
    asignatura = relationship('Asignatura', backref='evaluaciones_extra')
    
    def calcular_completiva_final(self):
        """50% C.F. + 50% C.E.C. redondeado entero (fórmula MINERD oficial)."""
        if self.cf_original is None or self.cec is None:
            return None
        return round(0.5 * self.cf_original + 0.5 * self.cec, 0)
    
    def calcular_extraordinaria_final(self):
        """30% C.F. + 70% C.E.EX redondeado entero."""
        if self.cf_original is None or self.ceex is None:
            return None
        return round(0.3 * self.cf_original + 0.7 * self.ceex, 0)
    
    def calcular_especial_final(self):
        """C.F. (redondeado) + C.E. — suma simple sin ponderación.
        La tabla oficial MINERD usa el CF redondeado en la Especial (64+10=74)."""
        if self.cf_original is None or self.ce is None:
            return None
        return round(self.cf_original, 0) + self.ce
    
    def calcular_condicion_final(self):
        """Cascada oficial MINERD para determinar condición final.
        
        Devuelve tupla (condicion_str, nota_efectiva).
        nota_efectiva es la nota que aparece en el boletín como "Situación Final".
        """
        if self.cf_original is None:
            return (None, None)
        
        # El corte de 70 y la nota mostrada usan el CF redondeado (boletín oficial)
        cf_redondeado = round(self.cf_original, 0)
        if cf_redondeado >= 70:
            return ('aprobado_normal', cf_redondeado)
        
        # Si entra acá es porque CF < 70, evalúa completiva
        cf_comp = self.calcular_completiva_final()
        if cf_comp is not None and cf_comp >= 70:
            return ('aprobado_completiva', cf_comp)
        
        # Completiva reprobó o no se cargó, evalúa extraordinaria
        cf_extra = self.calcular_extraordinaria_final()
        if cf_extra is not None and cf_extra >= 70:
            return ('aprobado_extraordinaria', cf_extra)
        
        # Extraordinaria reprobó o no se cargó, evalúa especial
        cf_esp = self.calcular_especial_final()
        if cf_esp is not None and cf_esp >= 70:
            return ('aprobado_especial', cf_esp)
        
        # Reprobó todas las fases, o aún no se cargaron las pendientes
        # La "nota efectiva" en este caso es la última calculada (la peor)
        # para mostrar en el boletín. Si nada se cargó aún, usar CF.
        nota_a_mostrar = (cf_esp or cf_extra or cf_comp or self.cf_original)
        return ('reprobado', nota_a_mostrar)
    
    def fase_pendiente(self):
        """Qué evaluación extra necesita el estudiante para terminar la cascada.
        
        Devuelve: 'completiva' | 'extraordinaria' | 'especial' | None
        None = ya terminó (aprobado o reprobado en especial).
        """
        if self.cf_original is None:
            return None  # aún no termina el año
        if self.cf_original >= 70:
            return None  # aprobó normal, no necesita nada
        
        if self.cec is None:
            return 'completiva'
        if self.completiva_final is not None and self.completiva_final >= 70:
            return None  # aprobó en completiva
        
        if self.ceex is None:
            return 'extraordinaria'
        if self.extraordinaria_final is not None and self.extraordinaria_final >= 70:
            return None  # aprobó en extraordinaria
        
        if self.ce is None:
            return 'especial'
        return None  # ya hizo especial, condición final ya está decidida
    
    def recalcular_todo(self):
        """Recalcula todos los campos derivados y actualiza condicion_final.
        Se llama en cada save."""
        self.completiva_final = self.calcular_completiva_final()
        self.extraordinaria_final = self.calcular_extraordinaria_final()
        self.especial_final = self.calcular_especial_final()
        cond, nota = self.calcular_condicion_final()
        self.condicion_final = cond
        self.nota_final = nota
    
    def to_dict(self):
        return {
            'id': self.id,
            'estudiante_id': self.estudiante_id,
            'asignatura_id': self.asignatura_id,
            'cf_original': self.cf_original,
            'cec': self.cec,
            'completiva_final': self.completiva_final,
            'ceex': self.ceex,
            'extraordinaria_final': self.extraordinaria_final,
            'ce': self.ce,
            'especial_final': self.especial_final,
            'condicion_final': self.condicion_final,
            'nota_final': self.nota_final,
            'fase_pendiente': self.fase_pendiente(),
        }


# ============== ASISTENCIA ==============

class Asistencia(Base):
    __tablename__ = 'asistencias'
    id = Column(Integer, primary_key=True)
    colegio_id = Column(Integer, ForeignKey('colegios.id'), nullable=True, index=True)
    estudiante_id = Column(Integer, ForeignKey('estudiantes.id'), nullable=False, index=True)
    curso_id = Column(Integer, ForeignKey('cursos.id'), nullable=False, index=True)
    asignatura_id = Column(Integer, ForeignKey('asignaturas.id'), nullable=True, index=True)
    fecha = Column(Date, nullable=False, default=date.today, index=True)
    estado = Column(String(10), nullable=False)
    observacion = Column(String(200))
    registrado_por = Column(Integer, ForeignKey('usuarios.id'))
    
    __table_args__ = (
        UniqueConstraint('estudiante_id', 'fecha', 'asignatura_id', name='unique_asistencia_por_dia_materia'),
        # Índices compuestos para queries frecuentes:
        # - Resumen mensual de asistencia por estudiante (filtra por estudiante + rango de fecha)
        # - Listado por curso + fecha (Index sobre curso_id + fecha)
        # - Bulk fetch por colegio en reportes (colegio_id + fecha)
        Index('ix_asistencia_est_fecha', 'estudiante_id', 'fecha'),
        Index('ix_asistencia_curso_fecha', 'curso_id', 'fecha'),
        Index('ix_asistencia_colegio_fecha', 'colegio_id', 'fecha'),
    )

    estudiante = relationship('Estudiante', backref='asistencias')
    curso = relationship('Curso', backref='asistencias')
    asignatura = relationship('Asignatura', backref='asistencias')

# ============== REPORTES Y PSICOLOGÍA ==============

class ReporteConducta(Base):
    __tablename__ = 'reportes_conducta'
    id = Column(Integer, primary_key=True)
    colegio_id = Column(Integer, ForeignKey('colegios.id'), nullable=True, index=True)
    estudiante_id = Column(Integer, ForeignKey('estudiantes.id'), nullable=False, index=True)
    reportado_por = Column(Integer, ForeignKey('usuarios.id'), nullable=False)
    tipo = Column(String(20))
    gravedad = Column(String(20))
    titulo = Column(String(200), nullable=False)
    descripcion = Column(Text, nullable=False)
    fecha = Column(DateTime, default=_now_dr)
    estado = Column(String(20), default='pendiente')
    
    # === RESPUESTA DE DIRECCIÓN/COORDINACIÓN (v2.11) ===
    # En v2.11 separamos la respuesta en 3 campos guiados para PDF profesional.
    # Antes había solo `respuesta` (que se mantiene como comentario adicional).
    acciones_centro = Column(Text)       # Acciones tomadas por el centro
    acciones_hogar = Column(Text)        # Acciones esperadas en el hogar
    respuesta = Column(Text)             # Comentario adicional libre (legacy)
    respondido_por = Column(Integer, ForeignKey('usuarios.id'))
    fecha_respuesta = Column(DateTime)
    
    # === ENVÍO Y CONFIRMACIÓN DEL PADRE ===
    enviado_padres = Column(Boolean, default=False)
    # Cuando el padre devuelve el reporte firmado, dirección lo marca acá
    confirmado_padre = Column(Boolean, default=False)
    fecha_confirmacion_padre = Column(DateTime)
    confirmado_por_usuario_id = Column(Integer, ForeignKey('usuarios.id'))
    
    # === NÚMERO DE REPORTE ===
    # Formato: "YYYY-NNNN" autogenerado por colegio (ej: "2026-0023")
    numero_reporte = Column(String(20), index=True)

    estudiante = relationship('Estudiante', backref='reportes')
    reportador = relationship('Usuario', foreign_keys=[reportado_por], backref='reportes_creados')
    respondedor = relationship('Usuario', foreign_keys=[respondido_por], backref='reportes_respondidos')
    confirmador_padre = relationship('Usuario', foreign_keys=[confirmado_por_usuario_id])

class CasoPsicologia(Base):
    __tablename__ = 'casos_psicologia'
    id = Column(Integer, primary_key=True)
    colegio_id = Column(Integer, ForeignKey('colegios.id'), nullable=True, index=True)
    estudiante_id = Column(Integer, ForeignKey('estudiantes.id'), nullable=False, index=True)
    solicitado_por = Column(Integer, ForeignKey('usuarios.id'), nullable=False)
    tipo = Column(String(30))
    urgencia = Column(String(20), default='normal')
    motivo = Column(Text, nullable=False)
    fecha_solicitud = Column(DateTime, default=_now_dr)
    estado = Column(String(20), default='pendiente')
    asignado_a = Column(Integer, ForeignKey('usuarios.id'))
    fecha_atencion = Column(DateTime)
    diagnostico = Column(Text)
    seguimiento = Column(Text)
    notas_atencion = Column(Text)
    recomendacion_profesor = Column(Text)
    fecha_actualizacion = Column(DateTime)

    estudiante = relationship('Estudiante', backref='casos_psicologia')
    solicitante = relationship('Usuario', foreign_keys=[solicitado_por])
    psicologo = relationship('Usuario', foreign_keys=[asignado_a])

# ============== COMUNICACIÓN ==============

class Mensaje(Base):
    __tablename__ = 'mensajes'
    id = Column(Integer, primary_key=True)
    colegio_id = Column(Integer, ForeignKey('colegios.id'), nullable=True, index=True)
    remitente_id = Column(Integer, ForeignKey('usuarios.id'), nullable=False)
    destinatario_id = Column(Integer, ForeignKey('usuarios.id'))
    para_direccion = Column(Boolean, default=False)
    asunto = Column(String(200), nullable=False)
    contenido = Column(Text, nullable=False)
    fecha = Column(DateTime, default=_now_dr)
    leido = Column(Boolean, default=False)
    fecha_lectura = Column(DateTime)

    remitente = relationship('Usuario', foreign_keys=[remitente_id], backref='mensajes_enviados')
    destinatario = relationship('Usuario', foreign_keys=[destinatario_id], backref='mensajes_recibidos')

class Comunicado(Base):
    __tablename__ = 'comunicados'
    id = Column(Integer, primary_key=True)
    colegio_id = Column(Integer, ForeignKey('colegios.id'), nullable=True, index=True)
    autor_id = Column(Integer, ForeignKey('usuarios.id'), nullable=False)
    titulo = Column(String(200), nullable=False)
    contenido = Column(Text, nullable=False)
    imagen = Column(Text)
    fecha = Column(DateTime, default=_now_dr)
    fecha_expiracion = Column(DateTime)
    tipo = Column(String(20), default='general')
    para_profesores = Column(Boolean, default=True)
    para_coordinadores = Column(Boolean, default=True)
    para_psicologia = Column(Boolean, default=True)
    activo = Column(Boolean, default=True)

    autor = relationship('Usuario', backref='comunicados')

class ComunicadoLeido(Base):
    __tablename__ = 'comunicados_leidos'
    id = Column(Integer, primary_key=True)
    colegio_id = Column(Integer, ForeignKey('colegios.id'), nullable=True, index=True)
    comunicado_id = Column(Integer, ForeignKey('comunicados.id'), nullable=False)
    usuario_id = Column(Integer, ForeignKey('usuarios.id'), nullable=False)
    fecha_lectura = Column(DateTime, default=_now_dr)
    
    __table_args__ = (
        UniqueConstraint('comunicado_id', 'usuario_id', name='unique_comunicado_leido'),
    )
    
    comunicado = relationship('Comunicado', backref='lecturas')
    usuario = relationship('Usuario', backref='comunicados_leidos')

class HistorialReportePadres(Base):
    __tablename__ = 'historial_reportes_padres'
    id = Column(Integer, primary_key=True)
    colegio_id = Column(Integer, ForeignKey('colegios.id'), nullable=True, index=True)
    reporte_id = Column(Integer, ForeignKey('reportes_conducta.id'), nullable=False)
    estudiante_id = Column(Integer, ForeignKey('estudiantes.id'), nullable=False, index=True)
    enviado_por = Column(Integer, ForeignKey('usuarios.id'), nullable=False)
    telefono_destino = Column(String(20))
    mensaje_enviado = Column(Text, nullable=False)
    fecha_envio = Column(DateTime, default=_now_dr)
    metodo = Column(String(20), default='whatsapp')
    
    reporte = relationship('ReporteConducta', backref='historial_envios')
    estudiante = relationship('Estudiante', backref='reportes_enviados_padres')
    usuario = relationship('Usuario', backref='reportes_enviados')

class PlantillaMensaje(Base):
    __tablename__ = 'plantillas_mensaje'
    id = Column(Integer, primary_key=True)
    colegio_id = Column(Integer, ForeignKey('colegios.id'), nullable=True, index=True)
    nombre = Column(String(100), nullable=False)
    categoria = Column(String(30))
    asunto = Column(String(200))
    contenido = Column(Text, nullable=False)
    creado_por = Column(Integer, ForeignKey('usuarios.id'))
    fecha_creacion = Column(DateTime, default=_now_dr)

# ============== HISTORIAL ==============

class HistorialAcademico(Base):
    __tablename__ = 'historial_academico'
    id = Column(Integer, primary_key=True)
    colegio_id = Column(Integer, ForeignKey('colegios.id'), nullable=True, index=True)
    estudiante_id = Column(Integer, ForeignKey('estudiantes.id'), nullable=False)
    ano_escolar_id = Column(Integer, ForeignKey('ano_escolar.id'), nullable=False)
    grado_id = Column(Integer, ForeignKey('grados.id'))
    curso_id = Column(Integer, ForeignKey('cursos.id'))
    promedio_final = Column(Float)
    asistencia_porcentaje = Column(Float)
    condicion = Column(String(20))
    observaciones = Column(Text)

# ============== DÍAS NO LABORABLES ==============

class DiaNoLaborable(Base):
    __tablename__ = 'dias_no_laborables'
    id = Column(Integer, primary_key=True)
    colegio_id = Column(Integer, ForeignKey('colegios.id'), nullable=True, index=True)
    fecha = Column(Date, nullable=False)
    nombre = Column(String(100), nullable=False)
    tipo = Column(String(20), default='feriado')
    ano_escolar_id = Column(Integer, ForeignKey('ano_escolar.id'))
    recurrente = Column(Boolean, default=False)
    activo = Column(Boolean, default=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'fecha': self.fecha.isoformat() if self.fecha else None,
            'nombre': self.nombre,
            'tipo': self.tipo,
            'recurrente': self.recurrente
        }

# ============== AUDITORÍA ==============

class LogAcceso(Base):
    __tablename__ = 'log_accesos'
    id = Column(Integer, primary_key=True)
    colegio_id = Column(Integer, ForeignKey('colegios.id'), nullable=True, index=True)
    usuario_id = Column(Integer, ForeignKey('usuarios.id'))
    tipo = Column(String(20))
    ip = Column(String(45))
    user_agent = Column(String(300))
    fecha = Column(DateTime, default=_now_dr)

    usuario = relationship('Usuario', backref='accesos')

class LogAuditoria(Base):
    __tablename__ = 'log_auditoria'
    id = Column(Integer, primary_key=True)
    colegio_id = Column(Integer, ForeignKey('colegios.id'), nullable=True, index=True)
    usuario_id = Column(Integer, ForeignKey('usuarios.id'))
    accion = Column(String(50))
    entidad = Column(String(50))
    entidad_id = Column(Integer)
    detalles = Column(Text)
    ip = Column(String(45))
    user_agent = Column(String(200))
    fecha = Column(DateTime, default=_now_dr, index=True)
    
    tabla = Column(String(50))
    registro_id = Column(Integer)
    datos_anteriores = Column(Text)
    datos_nuevos = Column(Text)

    usuario = relationship('Usuario', backref='auditorias')
    
    def to_dict(self):
        return {
            'id': self.id,
            'usuario_id': self.usuario_id,
            'usuario': self.usuario.nombre_completo if self.usuario else 'Sistema',
            'accion': self.accion,
            'entidad': self.entidad,
            'entidad_id': self.entidad_id,
            'detalles': self.detalles,
            'ip': self.ip,
            'fecha': self.fecha.isoformat() if self.fecha else None
        }

# ============== NOTIFICACIONES ==============

class Notificacion(Base):
    __tablename__ = 'notificaciones'
    id = Column(Integer, primary_key=True)
    colegio_id = Column(Integer, ForeignKey('colegios.id'), nullable=True, index=True)
    usuario_id = Column(Integer, ForeignKey('usuarios.id'), nullable=False, index=True)
    titulo = Column(String(200), nullable=False)
    mensaje = Column(Text)
    tipo = Column(String(30), default='info')  # info, alerta, comunicado, sistema
    link = Column(String(200))
    leida = Column(Boolean, default=False)
    fecha = Column(DateTime, default=_now_dr, index=True)
    
    usuario = relationship('Usuario', backref='notificaciones')
    
    def to_dict(self):
        return {
            'id': self.id,
            'titulo': self.titulo,
            'mensaje': self.mensaje,
            'tipo': self.tipo,
            'link': self.link,
            'leida': self.leida,
            'fecha': self.fecha.strftime('%d/%m/%Y %H:%M') if self.fecha else None,
            'tiempo_relativo': self._tiempo_relativo()
        }
    
    def _tiempo_relativo(self):
        if not self.fecha: return ''
        from datetime import timezone, timedelta
        ahora = _now_dr()
        diff = ahora - self.fecha
        if diff.days > 0: return f'Hace {diff.days}d'
        hours = diff.seconds // 3600
        if hours > 0: return f'Hace {hours}h'
        mins = diff.seconds // 60
        if mins > 0: return f'Hace {mins}m'
        return 'Ahora'

# ============== PERMISOS TEMPORALES ==============

class PermisoTemporalCalificacion(Base):
    __tablename__ = 'permisos_temporales_calificacion'
    id = Column(Integer, primary_key=True)
    colegio_id = Column(Integer, ForeignKey('colegios.id'), nullable=True, index=True)
    profesor_id = Column(Integer, ForeignKey('usuarios.id'), nullable=False)
    curso_id = Column(Integer, ForeignKey('cursos.id'))
    asignatura_id = Column(Integer, ForeignKey('asignaturas.id'))
    periodo = Column(Integer)
    fecha_inicio = Column(DateTime, default=_now_dr)
    fecha_fin = Column(DateTime, nullable=False)
    motivo = Column(String(300))
    otorgado_por = Column(Integer, ForeignKey('usuarios.id'))
    activo = Column(Boolean, default=True)
    
    profesor = relationship('Usuario', foreign_keys=[profesor_id], backref='permisos_temporales')
    curso = relationship('Curso', backref='permisos_temporales')
    asignatura = relationship('Asignatura', backref='permisos_temporales')

# ============== HISTORIAL DE COMUNICACIONES ==============

class HistorialComunicacionPadres(Base):
    __tablename__ = 'historial_comunicacion_padres'
    id = Column(Integer, primary_key=True)
    colegio_id = Column(Integer, ForeignKey('colegios.id'), nullable=True, index=True)
    estudiante_id = Column(Integer, ForeignKey('estudiantes.id'), nullable=False)
    tipo_comunicacion = Column(String(50))
    referencia_id = Column(Integer)
    mensaje_enviado = Column(Text, nullable=False)
    medio = Column(String(20), default='whatsapp')
    telefono_destino = Column(String(20))
    enviado_por = Column(Integer, ForeignKey('usuarios.id'), nullable=False)
    fecha_envio = Column(DateTime, default=_now_dr)
    
    estudiante = relationship('Estudiante', backref='comunicaciones_padres')
    usuario = relationship('Usuario', backref='comunicaciones_enviadas')

# ============== BLOC DE NOTAS PERSONAL ==============

class NotaPersonal(Base):
    __tablename__ = 'notas_personales'
    id = Column(Integer, primary_key=True)
    colegio_id = Column(Integer, ForeignKey('colegios.id'), nullable=True, index=True)
    usuario_id = Column(Integer, ForeignKey('usuarios.id'), nullable=False)
    titulo = Column(String(200), default='Sin título')
    contenido = Column(Text)
    color = Column(String(20), default='yellow')
    fijada = Column(Boolean, default=False)
    fecha_creacion = Column(DateTime, default=_now_dr)
    fecha_actualizacion = Column(DateTime, default=_now_dr, onupdate=_now_dr)
    activo = Column(Boolean, default=True)
    
    usuario = relationship('Usuario', backref='notas_personales')
    
    def to_dict(self):
        return {
            'id': self.id,
            'titulo': self.titulo,
            'contenido': self.contenido,
            'color': self.color,
            'fijada': self.fijada,
            'fecha_creacion': self.fecha_creacion.isoformat() if self.fecha_creacion else None,
            'fecha_actualizacion': self.fecha_actualizacion.isoformat() if self.fecha_actualizacion else None
        }

# ============== EVALUACIÓN INTERNA DE PROFESORES ==============

class EvaluacionProfesor(Base):
    __tablename__ = 'evaluaciones_profesor'
    id = Column(Integer, primary_key=True)
    colegio_id = Column(Integer, ForeignKey('colegios.id'), nullable=True, index=True)
    profesor_id = Column(Integer, ForeignKey('usuarios.id'), nullable=False)
    evaluador_id = Column(Integer, ForeignKey('usuarios.id'), nullable=False)
    ano_escolar_id = Column(Integer, ForeignKey('ano_escolar.id'))
    periodo = Column(Integer)
    fecha = Column(DateTime, default=_now_dr)
    
    puntualidad = Column(Integer)
    planificacion = Column(Integer)
    dominio_tema = Column(Integer)
    metodologia = Column(Integer)
    manejo_aula = Column(Integer)
    uso_recursos = Column(Integer)
    evaluacion_estudiantes = Column(Integer)
    relacion_estudiantes = Column(Integer)
    relacion_colegas = Column(Integer)
    compromiso = Column(Integer)
    
    promedio = Column(Float)
    fortalezas = Column(Text)
    areas_mejora = Column(Text)
    observaciones = Column(Text)
    plan_accion = Column(Text)
    
    profesor = relationship('Usuario', foreign_keys=[profesor_id], backref='evaluaciones_recibidas')
    evaluador = relationship('Usuario', foreign_keys=[evaluador_id], backref='evaluaciones_realizadas')
    
    def calcular_promedio(self):
        criterios = [self.puntualidad, self.planificacion, self.dominio_tema,
                     self.metodologia, self.manejo_aula, self.uso_recursos,
                     self.evaluacion_estudiantes, self.relacion_estudiantes,
                     self.relacion_colegas, self.compromiso]
        valores = [c for c in criterios if c is not None]
        if valores:
            return round(sum(valores) / len(valores), 2)
        return None
    
    def get_nivel(self):
        p = self.promedio
        if p is None: return None
        if p >= 4.5: return 'Excelente'
        elif p >= 3.5: return 'Bueno'
        elif p >= 2.5: return 'Aceptable'
        elif p >= 1.5: return 'En Mejora'
        else: return 'Deficiente'
    
    def to_dict(self):
        return {
            'id': self.id,
            'profesor_id': self.profesor_id,
            'profesor': self.profesor.nombre_completo if self.profesor else None,
            'evaluador_id': self.evaluador_id,
            'evaluador': self.evaluador.nombre_completo if self.evaluador else None,
            'periodo': self.periodo,
            'fecha': self.fecha.isoformat() if self.fecha else None,
            'puntualidad': self.puntualidad,
            'planificacion': self.planificacion,
            'dominio_tema': self.dominio_tema,
            'metodologia': self.metodologia,
            'manejo_aula': self.manejo_aula,
            'uso_recursos': self.uso_recursos,
            'evaluacion_estudiantes': self.evaluacion_estudiantes,
            'relacion_estudiantes': self.relacion_estudiantes,
            'relacion_colegas': self.relacion_colegas,
            'compromiso': self.compromiso,
            'promedio': self.promedio,
            'nivel': self.get_nivel(),
            'fortalezas': self.fortalezas,
            'areas_mejora': self.areas_mejora,
            'observaciones': self.observaciones,
            'plan_accion': self.plan_accion
        }

# ============== EVALUACIÓN INTERNA DE ESTUDIANTES ==============

class ConfigEvalInterna(Base):
    __tablename__ = 'config_eval_interna'
    id = Column(Integer, primary_key=True)
    colegio_id = Column(Integer, ForeignKey('colegios.id'), nullable=True, index=True)
    profesor_id = Column(Integer, ForeignKey('usuarios.id'), nullable=False)
    asignatura_id = Column(Integer, ForeignKey('asignaturas.id'), nullable=False)
    peso_conducta = Column(Float, default=15)
    peso_cuaderno = Column(Float, default=15)
    peso_participacion = Column(Float, default=20)
    peso_trabajo = Column(Float, default=20)
    peso_asistencia = Column(Float, default=15)
    peso_exposicion = Column(Float, default=15)
    
    profesor = relationship('Usuario', backref='configs_eval_interna')
    asignatura = relationship('Asignatura', backref='configs_eval_interna')
    
    __table_args__ = (
        UniqueConstraint('profesor_id', 'asignatura_id', name='unique_config_eval_prof_asig'),
    )
    
    def total_pesos(self):
        return (self.peso_conducta + self.peso_cuaderno + self.peso_participacion +
                self.peso_trabajo + self.peso_asistencia + self.peso_exposicion)
    
    def to_dict(self):
        return {
            'id': self.id,
            'profesor_id': self.profesor_id,
            'asignatura_id': self.asignatura_id,
            'asignatura': self.asignatura.nombre if self.asignatura else None,
            'peso_conducta': self.peso_conducta,
            'peso_cuaderno': self.peso_cuaderno,
            'peso_participacion': self.peso_participacion,
            'peso_trabajo': self.peso_trabajo,
            'peso_asistencia': self.peso_asistencia,
            'peso_exposicion': self.peso_exposicion,
            'total_pesos': self.total_pesos()
        }


class EvalInternaEstudiante(Base):
    __tablename__ = 'eval_interna_estudiante'
    id = Column(Integer, primary_key=True)
    colegio_id = Column(Integer, ForeignKey('colegios.id'), nullable=True, index=True)
    estudiante_id = Column(Integer, ForeignKey('estudiantes.id'), nullable=False)
    profesor_id = Column(Integer, ForeignKey('usuarios.id'), nullable=False)
    asignatura_id = Column(Integer, ForeignKey('asignaturas.id'), nullable=False)
    curso_id = Column(Integer, ForeignKey('cursos.id'), nullable=False)
    periodo = Column(Integer, nullable=False)
    
    conducta = Column(Float)
    cuaderno = Column(Float)
    participacion = Column(Float)
    trabajo = Column(Float)
    asistencia_eval = Column(Float)
    exposicion = Column(Float)
    
    nota_final = Column(Float)
    observacion = Column(Text)
    
    fecha = Column(DateTime, default=_now_dr)
    fecha_actualizacion = Column(DateTime, default=_now_dr, onupdate=_now_dr)
    
    estudiante = relationship('Estudiante', backref='evaluaciones_internas')
    profesor = relationship('Usuario', backref='evaluaciones_internas_dadas')
    asignatura = relationship('Asignatura', backref='evaluaciones_internas')
    curso = relationship('Curso', backref='evaluaciones_internas')
    
    __table_args__ = (
        UniqueConstraint('estudiante_id', 'profesor_id', 'asignatura_id', 'periodo',
                         name='unique_eval_interna'),
    )
    
    def calcular_nota(self, config=None):
        if config is None:
            # Note: in FastAPI context, caller should pass config explicitly
            pass
        
        if not config:
            pesos = {'conducta': 15, 'cuaderno': 15, 'participacion': 20,
                     'trabajo': 20, 'asistencia_eval': 15, 'exposicion': 15}
        else:
            pesos = {
                'conducta': config.peso_conducta,
                'cuaderno': config.peso_cuaderno,
                'participacion': config.peso_participacion,
                'trabajo': config.peso_trabajo,
                'asistencia_eval': config.peso_asistencia,
                'exposicion': config.peso_exposicion
            }
        
        total_peso = sum(pesos.values())
        if total_peso == 0:
            return 0
        
        suma_ponderada = 0
        for campo, peso in pesos.items():
            valor = getattr(self, campo)
            if valor is not None:
                suma_ponderada += (valor * peso)
        
        return round(suma_ponderada / total_peso, 2)
    
    def to_dict(self):
        return {
            'id': self.id,
            'estudiante_id': self.estudiante_id,
            'estudiante': self.estudiante.nombre_completo if self.estudiante else None,
            'no_lista': self.estudiante.no_lista if self.estudiante else None,
            'profesor_id': self.profesor_id,
            'asignatura_id': self.asignatura_id,
            'asignatura': self.asignatura.nombre if self.asignatura else None,
            'curso_id': self.curso_id,
            'periodo': self.periodo,
            'conducta': self.conducta,
            'cuaderno': self.cuaderno,
            'participacion': self.participacion,
            'trabajo': self.trabajo,
            'asistencia_eval': self.asistencia_eval,
            'exposicion': self.exposicion,
            'nota_final': self.nota_final,
            'observacion': self.observacion,
            'fecha': self.fecha.isoformat() if self.fecha else None
        }


# ============== FUNCIONES AUXILIARES ==============

class ItemCompletivo(Base):
    """
    Items completivos del registro escolar MINERD.
    
    Un "ítem completivo" es una actividad evaluativa registrada por el profesor
    en un período específico para una asignatura: examen parcial, tarea,
    proyecto, exposición, etc. Se imprime en el registro escolar como
    descripción de qué evaluó el profesor en ese período.
    
    A diferencia de Calificacion que guarda el VALOR de cada parcial (P1.1, etc.),
    ItemCompletivo es la DEFINICIÓN del parcial: qué se evaluó, cuándo, cuánto pesa.
    Estos dos modelos son ortogonales — el profesor puede tener notas sin items
    (ej. legacy data) y puede tener items sin notas (ej. anota lo que va a hacer).
    """
    __tablename__ = 'items_completivos'
    id = Column(Integer, primary_key=True)
    colegio_id = Column(Integer, ForeignKey('colegios.id'), nullable=True, index=True)
    profesor_id = Column(Integer, ForeignKey('usuarios.id'), nullable=False)
    asignatura_id = Column(Integer, ForeignKey('asignaturas.id'), nullable=False)
    curso_id = Column(Integer, ForeignKey('cursos.id'), nullable=False)
    periodo = Column(Integer, nullable=False)  # 1-4
    
    # Datos del ítem
    nombre = Column(String(200), nullable=False)  # "Examen parcial", "Tarea 1", etc.
    descripcion = Column(Text)  # Detalle libre del ítem
    fecha = Column(Date)  # Fecha de la evaluación
    peso = Column(Float)  # Peso porcentual del ítem (0-100), opcional
    
    fecha_creacion = Column(DateTime, default=_now_dr)
    fecha_actualizacion = Column(DateTime, default=_now_dr, onupdate=_now_dr)
    
    profesor = relationship('Usuario', backref='items_completivos')
    asignatura = relationship('Asignatura', backref='items_completivos')
    curso = relationship('Curso', backref='items_completivos')
    
    def to_dict(self):
        return {
            'id': self.id,
            'profesor_id': self.profesor_id,
            'profesor': self.profesor.nombre_completo if self.profesor else None,
            'asignatura_id': self.asignatura_id,
            'asignatura': self.asignatura.nombre if self.asignatura else None,
            'curso_id': self.curso_id,
            'curso': self.curso.nombre_completo if self.curso else None,
            'periodo': self.periodo,
            'nombre': self.nombre,
            'descripcion': self.descripcion,
            'fecha': self.fecha.isoformat() if self.fecha else None,
            'peso': self.peso,
            'fecha_creacion': self.fecha_creacion.isoformat() if self.fecha_creacion else None,
        }


class IndicadorLogro(Base):
    """
    Indicadores de logro por asignatura y período.
    El profesor registra qué competencias/indicadores trabajó.
    Se usa en el registro escolar MINERD (páginas de competencias).
    Opcional — si no se llena, las casillas quedan vacías en el registro.
    """
    __tablename__ = 'indicadores_logro'
    id = Column(Integer, primary_key=True)
    colegio_id = Column(Integer, ForeignKey('colegios.id'), nullable=True, index=True)
    profesor_id = Column(Integer, ForeignKey('usuarios.id'), nullable=False)
    asignatura_id = Column(Integer, ForeignKey('asignaturas.id'), nullable=False)
    curso_id = Column(Integer, ForeignKey('cursos.id'), nullable=False)
    periodo = Column(Integer, nullable=False)  # 1-4
    
    # Texto libre que el profesor escribe sobre lo que trabajó
    contenido = Column(Text)
    
    fecha_creacion = Column(DateTime, default=_now_dr)
    fecha_actualizacion = Column(DateTime, default=_now_dr, onupdate=_now_dr)
    
    profesor = relationship('Usuario', backref='indicadores_logro')
    asignatura = relationship('Asignatura', backref='indicadores_logro')
    curso = relationship('Curso', backref='indicadores_logro')
    
    __table_args__ = (
        UniqueConstraint('profesor_id', 'asignatura_id', 'curso_id', 'periodo', 'colegio_id',
                         name='unique_indicador_logro'),
    )
    
    def to_dict(self):
        return {
            'id': self.id,
            'profesor_id': self.profesor_id,
            'profesor': self.profesor.nombre_completo if self.profesor else None,
            'asignatura_id': self.asignatura_id,
            'asignatura': self.asignatura.nombre if self.asignatura else None,
            'curso_id': self.curso_id,
            'periodo': self.periodo,
            'contenido': self.contenido,
        }


def _generar_password_inicial() -> str:
    """
    Genera una password aleatoria fuerte (16 chars, alfanumérica + símbolos).
    Cumple los requisitos del endpoint /api/auth/cambiar-password:
    >= 8 chars, una mayúscula, una minúscula, un dígito.
    """
    import secrets
    import string
    while True:
        # Alfabeto sin caracteres ambiguos (0/O, 1/l/I) — más fácil de transcribir
        alfa = 'ABCDEFGHJKLMNPQRSTUVWXYZ' + 'abcdefghjkmnpqrstuvwxyz' + '23456789' + '!@#$%&*+-='
        pw = ''.join(secrets.choice(alfa) for _ in range(16))
        # Garantizar que cumple los requisitos
        if (any(c.isupper() for c in pw)
                and any(c.islower() for c in pw)
                and any(c.isdigit() for c in pw)):
            return pw


def _persistir_credenciales_iniciales(creds: dict, ruta_destino: str = None):
    """
    Escribe las credenciales generadas a un archivo INITIAL_CREDENTIALS.txt
    con permisos 0600 (solo el dueño puede leer). El admin debe leerlo,
    cambiar las passwords vía /api/auth/cambiar-password, y borrar el archivo.
    Si la escritura falla (FS read-only, sin permisos, etc.) las credenciales
    se loggean para que queden en el log del servidor.
    """
    import os
    import logging
    log = logging.getLogger(__name__)
    
    if ruta_destino is None:
        # Por defecto al lado del módulo (mismo nivel que models.py)
        ruta_destino = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     'INITIAL_CREDENTIALS.txt')
    
    contenido = (
        "═══════════════════════════════════════════════════════════════════\n"
        "  EducaOne — Credenciales iniciales generadas automáticamente\n"
        "═══════════════════════════════════════════════════════════════════\n"
        "\n"
        "ESTAS CREDENCIALES SON DE UN SOLO USO. Hacé login, cambiá la\n"
        "contraseña de inmediato, y BORRÁ ESTE ARCHIVO.\n"
        "\n"
        "Cualquier persona con acceso a este archivo puede entrar como\n"
        "superadmin/director. Tratalo como un secreto.\n"
        "\n"
    )
    for username, pw in creds.items():
        contenido += f"  Usuario:    {username}\n"
        contenido += f"  Contraseña: {pw}\n\n"
    contenido += (
        "Después de cambiar las passwords:\n"
        "  rm INITIAL_CREDENTIALS.txt\n"
        "═══════════════════════════════════════════════════════════════════\n"
    )
    
    try:
        with open(ruta_destino, 'w', encoding='utf-8') as f:
            f.write(contenido)
        try:
            os.chmod(ruta_destino, 0o600)
        except (OSError, NotImplementedError):
            pass  # Windows / FS sin chmod, no es crítico
        log.warning(f"⚠️  Credenciales iniciales escritas en: {ruta_destino}")
        log.warning("⚠️  LEERLAS UNA VEZ, CAMBIAR PASSWORDS, Y BORRAR EL ARCHIVO.")
    except OSError as e:
        # FS read-only o sin permisos: caer a log
        log.error(f"⚠️  No se pudo escribir {ruta_destino}: {e}")
        log.warning("⚠️  CREDENCIALES INICIALES (cambiar inmediatamente):")
        for username, pw in creds.items():
            log.warning(f"   {username} / {pw}")


def init_db():
    """Inicializa la base de datos con datos por defecto.
    
    Para superadmin y direccion: si no existen, se crean con password
    aleatoria, marcados con must_change_password=True. Las credenciales
    se persisten en INITIAL_CREDENTIALS.txt al lado de models.py
    (permisos 0600). El admin debe leerlas, hacer login, cambiar las
    passwords y borrar el archivo. Esto evita el patrón inseguro
    anterior (passwords hardcodeadas en el código fuente).
    """
    from database import engine, SessionLocal
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        # Crear colegio por defecto si no existe.
        # Plan completo (primaria + secundaria) para que el colegio default
        # pueda usar ambos niveles sin que el admin tenga que tocar nada.
        colegio = db.query(Colegio).first()
        if not colegio:
            colegio = Colegio(
                nombre='Mi Colegio',
                codigo='default',
                activo=True,
                plan='premium',
                plan_secundaria=True,
                plan_primaria=True,
                plan_inicial=False,
                plan_whatsapp=True,
                plan_psicologia=True,
                plan_eval_profesores=True,
                plan_eval_interna=True,
                plan_comunicacion_padres=True,
                plan_registro_escolar=True,
                plan_reportes_conducta=True,
            )
            db.add(colegio)
            db.flush()
        
        # ConfiguracionColegio: niveles activos por consistencia con plan,
        # módulos opcionales en False (director decide).
        if not db.query(ConfiguracionColegio).first():
            config = ConfiguracionColegio(
                nombre='Mi Colegio',
                colegio_id=colegio.id,
                usa_secundaria=True,
                usa_primaria=True,
                usa_inicial=False,
            )
            db.add(config)
        
        # Credenciales generadas en este arranque (para persistir al archivo).
        creds_a_persistir = {}
        
        # Superadmin: en DEV usa password fija 'superadmin123' para conveniencia.
        # En PROD genera password aleatoria y la imprime UNA vez al log + escribe a archivo.
        # must_change_password=True para forzar cambio en primer login en PROD.
        if not db.query(Usuario).filter_by(username='superadmin').first():
            es_dev = _os.environ.get('DEBUG', 'True').lower() == 'true' or _os.environ.get('ENVIRONMENT', 'development') == 'development'
            
            if es_dev:
                sa_password = 'superadmin123'
                must_change = False
            else:
                # En producción: password fuerte aleatoria, escrita a archivo y forzar cambio
                import secrets, string
                alphabet = string.ascii_letters + string.digits + '!@#$%^&*'
                sa_password = ''.join(secrets.choice(alphabet) for _ in range(16))
                must_change = True
                
                creds_path = _os.path.join(_os.path.dirname(__file__), 'INITIAL_CREDENTIALS.txt')
                try:
                    with open(creds_path, 'w') as f:
                        f.write(f"superadmin\n{sa_password}\n")
                    _os.chmod(creds_path, 0o600)
                    print("=" * 70)
                    print("SUPERADMIN INICIAL CREADO")
                    print(f"Username: superadmin")
                    print(f"Password: {sa_password}")
                    print(f"También guardado en: {creds_path}")
                    print("CAMBIA ESTA PASSWORD EN EL PRIMER LOGIN.")
                    print("=" * 70)
                except Exception as e:
                    print(f"WARNING: No se pudo escribir INITIAL_CREDENTIALS.txt: {e}")
                    print(f"superadmin password inicial: {sa_password}")
            
            superadmin = Usuario(
                username='superadmin',
                nombre='Super',
                apellido='Administrador',
                role='superadmin',
                colegio_id=None,
                must_change_password=must_change,
            )
            superadmin.set_password(sa_password)
            db.add(superadmin)
        
        # Direccion default: en DEV usamos must_change_password=False para
        # que puedas loguear directo con admin123 mientras desarrollás. En
        # PRODUCCIÓN forzamos must_change_password=True — esto cierra la
        # ventana de exposición entre el deploy inicial y el primer login del
        # admin. Sin este flag, si un bot escanea tu dominio justo después
        # del deploy y prueba admin/admin123, entra. Con el flag, aunque
        # entre, no puede hacer nada sin cambiar la password primero.
        es_dev = _os.environ.get('DEBUG', 'True').lower() == 'true'
        if not db.query(Usuario).filter_by(username='direccion').first():
            admin = Usuario(
                username='direccion',
                nombre='Administrador',
                apellido='Sistema',
                role='direccion',
                colegio_id=colegio.id,
                must_change_password=not es_dev,
            )
            admin.set_password('admin123')
            db.add(admin)
        
        if not db.query(AnoEscolar).first():
            ano = AnoEscolar(
                nombre='2024-2025',
                fecha_inicio=date(2024, 9, 1),
                fecha_fin=date(2025, 6, 30),
                activo=True,
                colegio_id=colegio.id
            )
            db.add(ano)
        
        if not db.query(Grado).first():
            grados = [
                Grado(nombre='1ro Secundaria', nivel='secundaria', orden=1, colegio_id=colegio.id),
                Grado(nombre='2do Secundaria', nivel='secundaria', orden=2, colegio_id=colegio.id),
                Grado(nombre='3ro Secundaria', nivel='secundaria', orden=3, colegio_id=colegio.id),
                Grado(nombre='4to Secundaria', nivel='secundaria', orden=4, colegio_id=colegio.id),
                Grado(nombre='5to Secundaria', nivel='secundaria', orden=5, colegio_id=colegio.id),
                Grado(nombre='6to Secundaria', nivel='secundaria', orden=6, colegio_id=colegio.id),
            ]
            db.add_all(grados)
        
        if not db.query(Tanda).first():
            tandas = [
                Tanda(nombre='Matutina', hora_inicio='07:30', hora_fin='12:30', colegio_id=colegio.id),
                Tanda(nombre='Vespertina', hora_inicio='14:00', hora_fin='18:00', colegio_id=colegio.id),
            ]
            db.add_all(tandas)
        
        if not db.query(Asignatura).first():
            asignaturas = [
                Asignatura(nombre='Lengua Española', codigo='LE', area='Lenguas', colegio_id=colegio.id),
                Asignatura(nombre='Matemática', codigo='MA', area='Matemática', colegio_id=colegio.id),
                Asignatura(nombre='Ciencias Sociales', codigo='CS', area='Ciencias Sociales', colegio_id=colegio.id),
                Asignatura(nombre='Ciencias Naturales', codigo='CN', area='Ciencias Naturales', colegio_id=colegio.id),
                Asignatura(nombre='Inglés', codigo='IN', area='Lenguas', colegio_id=colegio.id),
                Asignatura(nombre='Educación Física', codigo='EF', area='Educación Física', colegio_id=colegio.id),
                Asignatura(nombre='Educación Artística', codigo='EA', area='Educación Artística', colegio_id=colegio.id),
                Asignatura(nombre='Formación Humana', codigo='FH', area='Formación Humana', colegio_id=colegio.id),
            ]
            db.add_all(asignaturas)
        
        # Seed de áreas curriculares MINERD de primaria (catálogo base)
        if not db.query(AreaCurricular).filter_by(nivel='primaria').first():
            areas_primaria = [
                # Primer ciclo primaria (1ro-3ro): 7 áreas, 3 competencias cada una
                AreaCurricular(nombre='Lengua Española', codigo='LE', nivel='primaria', ciclo='primer_ciclo', numero_competencias=3, orden=1, colegio_id=colegio.id),
                AreaCurricular(nombre='Matemática', codigo='MA', nivel='primaria', ciclo='primer_ciclo', numero_competencias=3, orden=2, colegio_id=colegio.id),
                AreaCurricular(nombre='Ciencias Sociales', codigo='CS', nivel='primaria', ciclo='primer_ciclo', numero_competencias=3, orden=3, colegio_id=colegio.id),
                AreaCurricular(nombre='Ciencias de la Naturaleza', codigo='CN', nivel='primaria', ciclo='primer_ciclo', numero_competencias=3, orden=4, colegio_id=colegio.id),
                AreaCurricular(nombre='Educación Artística', codigo='EA', nivel='primaria', ciclo='primer_ciclo', numero_competencias=3, orden=5, colegio_id=colegio.id),
                AreaCurricular(nombre='Educación Física', codigo='EF', nivel='primaria', ciclo='primer_ciclo', numero_competencias=3, orden=6, colegio_id=colegio.id),
                AreaCurricular(nombre='Formación Integral Humana y Religiosa', codigo='FIHR', nivel='primaria', ciclo='primer_ciclo', numero_competencias=3, orden=7, colegio_id=colegio.id),
                # Segundo ciclo primaria (4to-6to): mismas 7 + Inglés (2 competencias)
                AreaCurricular(nombre='Lengua Española', codigo='LE', nivel='primaria', ciclo='segundo_ciclo', numero_competencias=3, orden=1, colegio_id=colegio.id),
                AreaCurricular(nombre='Matemática', codigo='MA', nivel='primaria', ciclo='segundo_ciclo', numero_competencias=3, orden=2, colegio_id=colegio.id),
                AreaCurricular(nombre='Ciencias Sociales', codigo='CS', nivel='primaria', ciclo='segundo_ciclo', numero_competencias=3, orden=3, colegio_id=colegio.id),
                AreaCurricular(nombre='Ciencias de la Naturaleza', codigo='CN', nivel='primaria', ciclo='segundo_ciclo', numero_competencias=3, orden=4, colegio_id=colegio.id),
                AreaCurricular(nombre='Educación Artística', codigo='EA', nivel='primaria', ciclo='segundo_ciclo', numero_competencias=3, orden=5, colegio_id=colegio.id),
                AreaCurricular(nombre='Educación Física', codigo='EF', nivel='primaria', ciclo='segundo_ciclo', numero_competencias=3, orden=6, colegio_id=colegio.id),
                AreaCurricular(nombre='Formación Integral Humana y Religiosa', codigo='FIHR', nivel='primaria', ciclo='segundo_ciclo', numero_competencias=3, orden=7, colegio_id=colegio.id),
                AreaCurricular(nombre='Lenguas Extranjeras (Inglés)', codigo='LEX', nivel='primaria', ciclo='segundo_ciclo', numero_competencias=2, orden=8, colegio_id=colegio.id),
            ]
            db.add_all(areas_primaria)
        
        db.commit()
        
        # === MIGRACIÓN v2.11 (auto-corrección de estado heredado) ===
        # En versiones anteriores (pre-v2.11) algunos colegios quedaron con
        # usa_X = False aunque plan_X = True. Con el refactor a Interpretación A
        # ya no chequeamos usa_X en runtime, pero queremos que la BD quede
        # consistente para evitar confusión si alguien mira los datos directo.
        #
        # Regla: si plan_X = True → forzar usa_X = True (consistencia).
        # Esto NO daña nada porque el código ya ignora usa_X en v2.11.
        try:
            # Usar el ORM (Colegio.activo == True) en vez de SQL crudo.
            # SQL crudo con "activo=1" funciona en SQLite pero PostgreSQL lo
            # rechaza (activo es BOOLEAN, no acepta comparar con el entero 1).
            # El ORM traduce el booleano correctamente para cada motor de BD.
            for _colegio in db.query(Colegio).filter(Colegio.activo == True).all():
                col_id = _colegio.id
                _config = db.query(ConfiguracionColegio).filter_by(colegio_id=col_id).first()
                if not _colegio or not _config:
                    continue
                cambios = False
                for _modulo in ('secundaria', 'primaria', 'inicial', 'whatsapp', 'psicologia',
                                 'eval_profesores', 'eval_interna', 'comunicacion_padres',
                                 'registro_escolar', 'reportes_conducta'):
                    plan_val = bool(getattr(_colegio, f'plan_{_modulo}', False))
                    usa_val = bool(getattr(_config, f'usa_{_modulo}', False))
                    # Si está en el plan pero usa_X está en False (estado heredado), corregir
                    if plan_val and not usa_val:
                        setattr(_config, f'usa_{_modulo}', True)
                        cambios = True
                    # Inversamente: si NO está en el plan pero usa_X=True, también limpiar
                    if not plan_val and usa_val:
                        setattr(_config, f'usa_{_modulo}', False)
                        cambios = True
            db.commit()
        except Exception as _e:
            # No bloquear el arranque si la migración falla por alguna razón;
            # el refactor v2.11 ya hace que el código funcione correctamente
            # sin que esta migración sea estrictamente necesaria.
            db.rollback()
            import logging
            logging.getLogger(__name__).warning(f"Migración v2.11 usa_X: {_e}")
        
        # Si en este arranque generamos credenciales nuevas, las persistimos
        # al archivo INITIAL_CREDENTIALS.txt para que el admin pueda leerlas.
        # Esto solo pasa la primera vez que arranca el sistema (BD vacía).
        if creds_a_persistir:
            _persistir_credenciales_iniciales(creds_a_persistir)
    finally:
        db.close()
