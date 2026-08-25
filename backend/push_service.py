"""
EducaOne — Servicio de Web Push (v2.19, Fase B).

Alcance deliberadamente estrecho: entregar al dispositivo una notificación que
YA existe en la tabla `notificaciones`. Este módulo nunca crea notificaciones,
nunca decide destinatarios y nunca toca lógica académica.

Reglas que sostienen el diseño:

1. NUNCA lanza excepción hacia arriba. El push es best-effort; la notificación
   interna es la fuente de verdad. Si esto falla, el usuario igual ve la
   campana al recargar o a los 30 segundos.

2. Se ejecuta en BackgroundTask, después de que la respuesta HTTP ya salió.
   Por eso abre su PROPIA sesión de base de datos: la del request ya está
   cerrada cuando esto corre, y reutilizar objetos ORM de esa sesión daría
   DetachedInstanceError.

3. Sin VAPID configurado, se desactiva solo y en silencio. Un colegio que no
   configuró las claves sigue funcionando con la campana interna.

4. PRIVACIDAD: el texto que llega al dispositivo es el que ya se guardó en la
   notificación, que en el caso de Psicología está redactado a propósito para
   no exponer datos del menor en la pantalla bloqueada. Este módulo no
   enriquece ni completa ese texto con datos de la base.
"""
import os
import json
import logging

logger = logging.getLogger('educaone.push')

VAPID_PUBLIC_KEY = os.environ.get('VAPID_PUBLIC_KEY', '').strip()
VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY', '').strip()
# mailto: de contacto que exige el estándar Web Push para identificar al emisor.
VAPID_SUBJECT = os.environ.get('VAPID_SUBJECT', 'mailto:soporte@educaone.app').strip()

try:
    from pywebpush import webpush, WebPushException
    _PYWEBPUSH_DISPONIBLE = True
except ImportError:  # pragma: no cover
    webpush = None
    WebPushException = Exception
    _PYWEBPUSH_DISPONIBLE = False


def push_configurado() -> bool:
    """True solo si se puede enviar de verdad. El frontend usa esto para decidir
    si muestra el botón 'Activar notificaciones en este dispositivo'."""
    return bool(_PYWEBPUSH_DISPONIBLE and VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY)


def clave_publica() -> str:
    """Clave pública VAPID que el navegador necesita para suscribirse."""
    return VAPID_PUBLIC_KEY if push_configurado() else ''


def _payload(notificacion) -> str:
    return json.dumps({
        'titulo': notificacion.titulo or 'EducaOne',
        'mensaje': notificacion.mensaje or '',
        'link': notificacion.link or '/',
        'prioridad': notificacion.prioridad or 'normal',
        'notificacion_id': notificacion.id,
    }, ensure_ascii=False)


def enviar_push_para_notificaciones(notificacion_ids):
    """
    Enviar Web Push para notificaciones ya persistidas.

    Se invoca desde BackgroundTasks con una lista de IDs — nunca con objetos
    ORM, que pertenecerían a una sesión ya cerrada.

    Nunca propaga excepciones.
    """
    if not notificacion_ids or not push_configurado():
        return

    from database import SessionLocal
    from models import Notificacion, PushSubscription
    from datetime import datetime

    db = SessionLocal()
    try:
        notifs = db.query(Notificacion).filter(
            Notificacion.id.in_(list(notificacion_ids))
        ).all()
        if not notifs:
            return

        # Agrupar por usuario para no repetir la consulta de dispositivos.
        por_usuario = {}
        for n in notifs:
            por_usuario.setdefault(n.usuario_id, []).append(n)

        muertas = []
        for usuario_id, lista in por_usuario.items():
            subs = db.query(PushSubscription).filter_by(usuario_id=usuario_id).all()
            if not subs:
                continue
            for n in lista:
                entregado_alguna = False
                for sub in subs:
                    # Barrera multi-tenant final: la notificación y el dispositivo
                    # deben pertenecer al mismo colegio. Si un usuario cambió de
                    # colegio y quedó una suscripción vieja, no recibe nada.
                    if n.colegio_id and sub.colegio_id and n.colegio_id != sub.colegio_id:
                        continue
                    try:
                        webpush(
                            subscription_info={
                                'endpoint': sub.endpoint,
                                'keys': {'p256dh': sub.p256dh, 'auth': sub.auth},
                            },
                            data=_payload(n),
                            vapid_private_key=VAPID_PRIVATE_KEY,
                            vapid_claims={'sub': VAPID_SUBJECT},
                            timeout=10,
                        )
                        entregado_alguna = True
                    except WebPushException as e:
                        codigo = getattr(getattr(e, 'response', None), 'status_code', None)
                        if codigo in (404, 410):
                            # El navegador desinstaló la PWA o revocó el permiso.
                            # La suscripción ya no existe: se borra.
                            muertas.append(sub.id)
                        else:
                            sub.ultimo_error = datetime.now()
                            logger.warning(
                                f'push falló (usuario {usuario_id}, código {codigo}): {e}'
                            )
                    except Exception as e:
                        sub.ultimo_error = datetime.now()
                        logger.warning(f'push error inesperado (usuario {usuario_id}): {e}')

                if entregado_alguna and not n.push_enviado_at:
                    # Solo significa que al menos una suscripción aceptó el envío.
                    # No es confirmación de entrega ni de lectura.
                    n.push_enviado_at = datetime.now()

        if muertas:
            db.query(PushSubscription).filter(
                PushSubscription.id.in_(muertas)
            ).delete(synchronize_session=False)
            logger.info(f'{len(muertas)} suscripción(es) push muerta(s) eliminada(s)')

        db.commit()
    except Exception as e:
        logger.warning(f'enviar_push_para_notificaciones falló por completo: {e}')
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()
