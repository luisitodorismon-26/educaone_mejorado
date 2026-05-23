"""
cache_service.py - Cache profesional Redis-ready con fallback local
===================================================================
En producción con Redis: CACHE_URL=redis://localhost:6379/0
Sin Redis: usa dict en memoria con threading.Lock
"""
import os
import time
import json
import logging
import threading
from typing import Any, Optional

logger = logging.getLogger("educaone.cache")

CACHE_URL = os.environ.get("CACHE_URL", os.environ.get("REDIS_URL", ""))
DEFAULT_TTL = 120  # 2 minutos

# ============================================================
# BACKEND REDIS
# ============================================================
_redis_client = None

def _get_redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    if not CACHE_URL:
        return None
    try:
        import redis
        _redis_client = redis.from_url(CACHE_URL, decode_responses=True, socket_timeout=2)
        _redis_client.ping()
        logger.info("Redis conectado")
        return _redis_client
    except Exception as e:
        logger.warning(f"Redis no disponible: {e}. Usando cache local.")
        _redis_client = False  # marca como no disponible
        return None


# ============================================================
# BACKEND LOCAL (FALLBACK)
# ============================================================
_local_cache: dict = {}
_local_ttl: dict = {}
_lock = threading.Lock()


# ============================================================
# API PÚBLICA
# ============================================================

def cache_get(key: str) -> Optional[Any]:
    """Obtener valor del cache"""
    r = _get_redis()
    if r:
        try:
            val = r.get(key)
            return json.loads(val) if val else None
        except Exception:
            pass

    with _lock:
        if key in _local_cache and time.time() < _local_ttl.get(key, 0):
            return _local_cache[key]
        _local_cache.pop(key, None)
        _local_ttl.pop(key, None)
    return None


def cache_set(key: str, value: Any, ttl: int = DEFAULT_TTL):
    """Guardar en cache"""
    r = _get_redis()
    if r:
        try:
            r.setex(key, ttl, json.dumps(value, default=str))
            return
        except Exception:
            pass

    with _lock:
        _local_cache[key] = value
        _local_ttl[key] = time.time() + ttl


def cache_clear_tenant(colegio_id: int):
    """Limpiar todo el cache de un colegio"""
    pattern = f"*_col{colegio_id}*"
    r = _get_redis()
    if r:
        try:
            keys = r.keys(pattern)
            if keys:
                r.delete(*keys)
            return
        except Exception:
            pass

    with _lock:
        keys_to_del = [k for k in _local_cache if f"_col{colegio_id}" in k]
        for k in keys_to_del:
            _local_cache.pop(k, None)
            _local_ttl.pop(k, None)


def cache_clear_all():
    """Limpiar todo el cache"""
    r = _get_redis()
    if r:
        try:
            r.flushdb()
            return
        except Exception:
            pass
    with _lock:
        _local_cache.clear()
        _local_ttl.clear()


def make_cache_key(endpoint: str, user) -> str:
    """Generar cache key por tenant"""
    cid = user.colegio_id if user and hasattr(user, 'colegio_id') else 'none'
    role = user.role if user and hasattr(user, 'role') else 'anon'
    return f"{endpoint}_{role}_col{cid}"
