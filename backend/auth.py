"""
Educa One - Dependencias de Autenticación para FastAPI
=====================================================
Multi-tenant: JWT incluye colegio_id, filtrado automático por colegio.
"""
import jwt
import os
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from database import get_db
from models import Usuario

security = HTTPBearer(auto_error=False)
current_user_ctx: ContextVar[Usuario | None] = ContextVar('current_user_ctx', default=None)

SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', SECRET_KEY)
JWT_EXPIRATION_HOURS = int(os.environ.get('JWT_EXPIRATION_HOURS', 8))

# ===========================================
# RATE LIMITING (Control de intentos)
# ===========================================
# Cache en memoria como pre-filtro rápido (evita ir a BD en cada request).
# La fuente de verdad sigue siendo LogAcceso en BD — sobrevive reinicios y
# se comparte entre workers. La memoria es solo aceleración.
login_attempts = {}

TZ_RD = timezone(timedelta(hours=-4))


def _now_rd_naive():
    """Misma convención temporal usada por models._now_dr (AST, sin tzinfo)."""
    return datetime.now(TZ_RD).replace(tzinfo=None)

def check_rate_limit(identifier, max_attempts=5, window_minutes=15, db=None):
    """Verifica límite de intentos. Si se pasa db, consulta LogAcceso (multi-worker safe).
    Si no, usa solo memoria (más rápido pero por-worker)."""
    # Memoria usa UTC porque register_attempt guarda datetime.utcnow().
    cutoff_mem = datetime.utcnow() - timedelta(minutes=window_minutes)
    
    # 1. Pre-filtro rápido en memoria
    if identifier in login_attempts:
        attempts_mem = [a for a in login_attempts[identifier] if a > cutoff_mem]
        login_attempts[identifier] = attempts_mem
        if len(attempts_mem) >= max_attempts:
            return False, 0
    
    # 2. Verificación contra BD (sobrevive reinicios y multi-worker)
    if db is not None:
        try:
            from models import LogAcceso
            # LogAcceso.fecha se guarda como hora RD naive (_now_dr). Usar UTC
            # aquí hacía que los intentos de las últimas ~4h parecieran viejos.
            cutoff_db = _now_rd_naive() - timedelta(minutes=window_minutes)
            count_db = db.query(LogAcceso).filter(
                LogAcceso.ip == identifier,
                LogAcceso.tipo == 'login_failed',
                LogAcceso.fecha > cutoff_db,
            ).count()
            if count_db >= max_attempts:
                return False, 0
            return True, max_attempts - count_db
        except Exception:
            pass
    
    return True, max_attempts - len(login_attempts.get(identifier, []))


def check_account_rate_limit(username, max_attempts=5, window_minutes=15, db=None):
    """Límite por cuenta usando el historial de auditoría persistente.

    Evita que cinco errores de cualquier persona detrás del mismo router/NAT
    bloqueen a todos los maestros de una escuela. Se combina con un límite IP
    más amplio en el endpoint de login para conservar protección anti-fuerza-bruta.
    """
    username = (username or '').strip().lower()
    if not username or db is None:
        return True, max_attempts
    try:
        from models import LogAuditoria
        cutoff_db = _now_rd_naive() - timedelta(minutes=window_minutes)
        count_db = db.query(LogAuditoria).filter(
            LogAuditoria.accion == 'login_fallido',
            LogAuditoria.detalles == f'username: {username}',
            LogAuditoria.fecha > cutoff_db,
        ).count()
        if count_db >= max_attempts:
            return False, 0
        return True, max_attempts - count_db
    except Exception:
        # El límite IP sigue activo como fallback si la auditoría no está
        # disponible durante un incidente de BD.
        return True, max_attempts

def register_attempt(identifier, success=False, db=None, user_id=None, user_agent=None):
    """Registra intento de login (en memoria + opcionalmente en BD)."""
    if success:
        if identifier in login_attempts:
            del login_attempts[identifier]
        # Limpiar también los failed de BD para esta IP
        if db is not None:
            try:
                from models import LogAcceso
                cutoff = _now_rd_naive() - timedelta(minutes=15)
                db.query(LogAcceso).filter(
                    LogAcceso.ip == identifier,
                    LogAcceso.tipo == 'login_failed',
                    LogAcceso.fecha > cutoff,
                ).delete(synchronize_session=False)
                db.commit()
            except Exception:
                pass
        return
    
    # Failed: registrar en ambos
    if identifier not in login_attempts:
        login_attempts[identifier] = []
    login_attempts[identifier].append(datetime.utcnow())
    
    if db is not None:
        try:
            from models import LogAcceso
            log = LogAcceso(
                usuario_id=user_id,
                tipo='login_failed',
                ip=identifier,
                user_agent=(user_agent or '')[:300],
            )
            db.add(log)
            db.commit()
        except Exception:
            db.rollback()


# ===========================================
# JWT
# ===========================================

def create_token(user: Usuario) -> str:
    """Genera un token JWT para el usuario (incluye colegio_id y token_version)."""
    payload = {
        'user_id': user.id,
        'username': user.username,
        'role': user.role,
        'colegio_id': user.colegio_id,
        'token_version': getattr(user, 'token_version', 0) or 0,
        'iat': datetime.utcnow(),
        'exp': datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm='HS256')


def decode_token(token: str) -> dict | None:
    """Decodifica un token JWT."""
    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def _attach_token_context(user: Usuario, payload: dict) -> Usuario:
    """Adjunta contexto transitorio del token al objeto ORM del request.

    No se persiste en la tabla usuarios. Permite que la auditoría distinga al
    actor real (Superadmin) del usuario efectivo durante impersonación.
    """
    impersonator = payload.get('impersonator_user_id') if payload.get('impersonating') else None
    try:
        impersonator = int(impersonator) if impersonator is not None else None
    except (TypeError, ValueError):
        impersonator = None
    setattr(user, '_impersonator_user_id', impersonator)
    setattr(user, '_is_impersonating', bool(impersonator))
    return user


# ===========================================
# DEPENDENCIAS FASTAPI
# ===========================================

def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> Usuario | None:
    """Obtiene el usuario actual si hay token, None si no.
    
    ESTA VERSIÓN TAMBIÉN VALIDA token_version. Antes no lo hacía, lo cual
    creaba un agujero de seguridad: cualquier endpoint que dependía de
    get_current_user_optional (como /api/auth/me) seguía aceptando tokens
    revocados por cambio de password, logout, o reset admin.
    """
    if not credentials:
        current_user_ctx.set(None)
        db.info['current_user'] = None
        return None
    
    payload = decode_token(credentials.credentials)
    if not payload:
        current_user_ctx.set(None)
        db.info['current_user'] = None
        return None
    
    # Validar token_version con query SQL directa (bypassing ORM cache)
    from sqlalchemy import text
    user_id_to_check = payload.get('user_id')
    if not user_id_to_check:
        current_user_ctx.set(None)
        return None
    
    fresh = db.execute(
        text("""
            SELECT u.id, u.activo, u.token_version, u.role, u.colegio_id, c.activo AS colegio_activo
            FROM usuarios u
            LEFT JOIN colegios c ON c.id = u.colegio_id
            WHERE u.id = :id
        """),
        {"id": user_id_to_check}
    ).fetchone()
    if not fresh or not fresh[1]:
        current_user_ctx.set(None)
        db.info['current_user'] = None
        return None
    # Un usuario tenant solo es válido si su colegio existe y está activo.
    # Esto corta sesiones ya emitidas cuando Superadmin desactiva el colegio.
    if fresh[3] != 'superadmin' and (fresh[4] is None or not fresh[5]):
        current_user_ctx.set(None)
        db.info['current_user'] = None
        return None
    
    token_ver_payload = payload.get('token_version', 0)
    token_ver_db = fresh[2] or 0
    if token_ver_payload != token_ver_db:
        current_user_ctx.set(None)
        db.info['current_user'] = None
        return None
    
    db.expire_all()
    user = db.query(Usuario).get(user_id_to_check)
    if user and user.activo:
        user = _attach_token_context(user, payload)
        current_user_ctx.set(user)
        db.info['current_user'] = user
        return user
    current_user_ctx.set(None)
    db.info['current_user'] = None
    return None


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> Usuario:
    """Equivalente a @login_required: requiere usuario autenticado.
    
    Si el usuario tiene must_change_password=True, sólo se le permite acceder
    a /api/auth/me, /api/auth/logout y /api/auth/cambiar-password. Cualquier
    otra ruta retorna 423 Locked con instrucción de cambiar password.
    """
    if not credentials:
        current_user_ctx.set(None)
        db.info['current_user'] = None
        raise HTTPException(status_code=401, detail='No autorizado')
    
    payload = decode_token(credentials.credentials)
    if not payload:
        current_user_ctx.set(None)
        db.info['current_user'] = None
        raise HTTPException(status_code=401, detail='Token inválido o expirado')
    
    # CRÍTICO DE SEGURIDAD: validar token_version con query SQL directa,
    # bypaseando el ORM cache de SQLAlchemy. Con el ORM cache podía pasar
    # que user.token_version devolviera un valor stale, permitiendo que
    # tokens revocados (por cambio de password, logout, o reset admin)
    # siguieran funcionando hasta que expiraran naturalmente.
    # Esta query directa va a BD cada vez, garantizando freshness.
    from sqlalchemy import text
    user_id_to_check = payload.get('user_id')
    if not user_id_to_check:
        current_user_ctx.set(None)
        db.info['current_user'] = None
        raise HTTPException(status_code=401, detail='Token inválido')
    
    fresh = db.execute(
        text("""
            SELECT u.id, u.activo, u.token_version, u.role, u.colegio_id, c.activo AS colegio_activo
            FROM usuarios u
            LEFT JOIN colegios c ON c.id = u.colegio_id
            WHERE u.id = :id
        """),
        {"id": user_id_to_check}
    ).fetchone()
    if not fresh or not fresh[1]:  # no existe o inactivo
        current_user_ctx.set(None)
        db.info['current_user'] = None
        raise HTTPException(status_code=401, detail='Token inválido o expirado')
    if fresh[3] != 'superadmin' and (fresh[4] is None or not fresh[5]):
        current_user_ctx.set(None)
        db.info['current_user'] = None
        raise HTTPException(status_code=403, detail='El colegio está desactivado')
    
    token_ver_payload = payload.get('token_version', 0)
    token_ver_db = fresh[2] or 0
    if token_ver_payload != token_ver_db:
        current_user_ctx.set(None)
        db.info['current_user'] = None
        raise HTTPException(status_code=401, detail='Sesión expirada — vuelva a iniciar sesión')
    
    # Ahora sí, cargar el objeto ORM completo
    db.expire_all()
    user = db.query(Usuario).get(user_id_to_check)
    if not user or not user.activo:
        current_user_ctx.set(None)
        db.info['current_user'] = None
        raise HTTPException(status_code=401, detail='Token inválido o expirado')
    user = _attach_token_context(user, payload)
    
    # (validación de token_version ya hecha arriba con query SQL directa)
    
    # Si el usuario tiene must_change_password, sólo permitir endpoints
    # mínimos que necesita para cambiar la password. El frontend debe
    # interpretar el 423 y redirigir al formulario de cambio.
    if getattr(user, 'must_change_password', False):
        ruta = request.url.path
        rutas_permitidas = {
            '/api/auth/me',
            '/api/auth/logout',
            '/api/auth/cambiar-password',
        }
        if ruta not in rutas_permitidas:
            raise HTTPException(
                status_code=423,
                detail='Debe cambiar su contraseña antes de continuar. '
                       'Use POST /api/auth/cambiar-password con password_actual '
                       'y password_nuevo.'
            )
    
    current_user_ctx.set(user)
    db.info['current_user'] = user
    return user


class RolesRequired:
    """
    Equivalente a @roles_required('direccion', 'coordinador')
    Acepta 'superadmin' como rol especial que siempre pasa.
    
    Uso en FastAPI:
        @router.get('/ruta')
        def mi_endpoint(user: Usuario = Depends(RolesRequired('direccion', 'coordinador'))):
            ...
    """
    def __init__(self, *roles):
        self.roles = roles
    
    def __call__(
        self,
        request: Request,
        credentials: HTTPAuthorizationCredentials = Depends(security),
        db: Session = Depends(get_db)
    ) -> Usuario:
        if not credentials:
            current_user_ctx.set(None)
            db.info['current_user'] = None
            raise HTTPException(status_code=401, detail='No autorizado')
        
        payload = decode_token(credentials.credentials)
        if not payload:
            current_user_ctx.set(None)
            db.info['current_user'] = None
            raise HTTPException(status_code=401, detail='Token inválido o expirado')
        
        user = db.query(Usuario).get(payload.get('user_id'))
        if not user or not user.activo:
            current_user_ctx.set(None)
            db.info['current_user'] = None
            raise HTTPException(status_code=401, detail='Token inválido o expirado')
        user = _attach_token_context(user, payload)
        
        # Validar token_version (logout / cambio de password invalida sesión)
        token_ver = payload.get('token_version', 0)
        if token_ver != (user.token_version or 0):
            current_user_ctx.set(None)
            db.info['current_user'] = None
            raise HTTPException(status_code=401, detail='Sesión expirada — vuelva a iniciar sesión')
        
        # Bloquear must_change_password (mismo patrón que get_current_user).
        # Esto aplica a superadmin también — el primer arranque del sistema
        # entrega credenciales temporales y debe forzarse cambio incluso al
        # superadmin antes de operar.
        if getattr(user, 'must_change_password', False):
            ruta = request.url.path
            rutas_permitidas = {
                '/api/auth/me',
                '/api/auth/logout',
                '/api/auth/cambiar-password',
            }
            if ruta not in rutas_permitidas:
                raise HTTPException(
                    status_code=423,
                    detail='Debe cambiar su contraseña antes de continuar. '
                           'Use POST /api/auth/cambiar-password.'
                )
        
        # superadmin siempre tiene acceso (pasada la verificación anterior)
        if user.role == 'superadmin':
            current_user_ctx.set(user)
            db.info['current_user'] = user
            return user
        
        if user.role not in self.roles:
            current_user_ctx.set(None)
            db.info['current_user'] = None
            raise HTTPException(status_code=403, detail='No tiene permisos para esta acción')
        
        current_user_ctx.set(user)
        db.info['current_user'] = user
        return user


def get_client_ip(request: Request) -> str:
    """Obtiene la IP real del cliente (considerando proxies)."""
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.client.host if request.client else '0.0.0.0'


# ===========================================
# MULTI-TENANT HELPERS
# ===========================================

def tenant_filter(query, model, user):
    """
    Filtra un query por colegio_id del usuario.
    Si es superadmin, no filtra (ve todo).
    El modelo debe tener columna colegio_id.
    """
    if user.role == 'superadmin':
        return query
    if hasattr(model, 'colegio_id'):
        return query.filter(model.colegio_id == user.colegio_id)
    return query


def set_tenant(obj, user):
    """Asigna colegio_id a un objeto nuevo basado en el usuario actual."""
    if hasattr(obj, 'colegio_id') and user.colegio_id is not None:
        obj.colegio_id = user.colegio_id


def get_tenant_or_404(db, model, obj_id, user, *, name: str = None):
    """
    Carga un objeto por ID y valida que pertenezca al colegio del usuario.
    
    - Si el objeto no existe → HTTPException 404.
    - Si existe pero pertenece a otro colegio → HTTPException 404 (no 403, para no
      revelar que el objeto existe en otro tenant).
    - Si el usuario es superadmin, ve todo.
    
    Uso típico:
        curso = get_tenant_or_404(db, Curso, payload['curso_id'], current_user, name='curso')
    
    Levanta HTTPException — no retorna None.
    """
    from fastapi import HTTPException
    
    if obj_id is None:
        raise HTTPException(status_code=400, detail=f"{name or model.__name__} requerido")
    
    try:
        obj_id_int = int(obj_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"{name or model.__name__}_id inválido")
    
    obj = db.get(model, obj_id_int)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{name or model.__name__} no encontrado")
    
    # Verificar tenant. Superadmin pasa.
    #
    # IMPORTANTE: un registro con colegio_id=NULL NO es "global" para los
    # usuarios normales. Es un registro huérfano/legacy y debe quedar oculto
    # hasta que una migración explícita lo asigne a un colegio. Aceptar NULL
    # aquí abría un bypass por acceso directo mediante ID aunque tenant_filter()
    # sí lo excluyera de los listados.
    if user.role != 'superadmin' and hasattr(model, 'colegio_id'):
        if user.colegio_id is None or obj.colegio_id is None or obj.colegio_id != user.colegio_id:
            # 404 (no 403) para no revelar existencia en otro tenant/legacy
            raise HTTPException(status_code=404, detail=f"{name or model.__name__} no encontrado")

    return obj


def assert_same_tenant(db, user, **fk_map):
    """
    Valida que múltiples FK referencien objetos del mismo colegio que el user.
    
    Uso:
        assert_same_tenant(db, current_user,
            curso=(Curso, payload.get('curso_id')),
            asignatura=(Asignatura, payload.get('asignatura_id')),
            profesor=(Usuario, payload.get('profesor_id')),
        )
    
    Cada par (Modelo, id) se carga y valida vía get_tenant_or_404.
    Retorna un dict {nombre: instancia_cargada} para que el caller no haga
    la query dos veces.
    """
    resultados = {}
    for nombre, par in fk_map.items():
        if par is None:
            continue
        modelo, valor_id = par
        if valor_id is None:
            continue
        resultados[nombre] = get_tenant_or_404(db, modelo, valor_id, user, name=nombre)
    return resultados
