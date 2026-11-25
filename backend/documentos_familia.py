"""
FAM-DOC-1 · Documentos para las familias: enlace privado, contactos y página.

Piezas sin dependencias de la app (se prueban solas):

  - Enlace secreto: `token_de(nonce)` = HMAC-SHA256(secreto, semilla), 256 bits
    en base64url (43 caracteres). La base guarda la semilla y el SHA-256 del
    enlace, nunca el enlace. Con la semilla y el secreto el colegio puede
    volver a compartir el MISMO enlace; con una copia de la base sin el
    secreto no se reconstruye ninguno.
  - Contactos: padre, madre y tutor del estudiante, con su teléfono en formato
    de WhatsApp (wa.me) solo si es utilizable. Un contacto con nombre pero
    sin teléfono válido NO se sugiere.
  - Página pública: HTML sin scripts, sin datos del estudiante en las
    etiquetas de vista previa (tarjeta genérica: colegio y «Reporte de notas
    disponible»).
"""
import base64
import hashlib
import hmac
import html
import json
import os
import re
import secrets

TIPO_REPORTE_PERIODO = 'reporte_periodo'
ORDEN_CONTACTOS = ('tutor', 'padre', 'madre')
_RE_TOKEN = re.compile(r'^[A-Za-z0-9_-]{43}$')
_DOMINIO_HMAC = b'educaone/documento-familia/v1:'

ORDINAL_PERIODO = {1: 'primer', 2: 'segundo', 3: 'tercer', 4: 'cuarto'}
ORDINAL_PERIODO_TITULO = {1: 'Primer', 2: 'Segundo', 3: 'Tercer', 4: 'Cuarto'}


# ─────────────────────────── Enlace secreto ───────────────────────────

def secreto_enlaces():
    """Secreto de los enlaces. `ENLACE_FAMILIA_SECRET` si está definido (se
    recomienda: así rotar SECRET_KEY no invalida los enlaces ya enviados);
    si no, SECRET_KEY."""
    s = os.environ.get('ENLACE_FAMILIA_SECRET') or os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    return s.encode('utf-8')


def nueva_semilla():
    return secrets.token_urlsafe(32)


def token_de(nonce):
    mac = hmac.new(secreto_enlaces(), _DOMINIO_HMAC + nonce.encode('utf-8'), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode('ascii').rstrip('=')


def hash_token(token):
    return hashlib.sha256(token.encode('ascii')).hexdigest()


def token_con_formato_valido(token):
    return bool(token) and bool(_RE_TOKEN.match(token))


def ruta_publica(token):
    return f'/doc/{token}'


# ─────────────────────────── Contactos ───────────────────────────

def telefono_whatsapp(raw):
    """Teléfono en el formato de wa.me (solo dígitos, con código de país) o
    None si no es utilizable. Misma regla que el envío de reportes de
    conducta: 10 dígitos que empiezan por 809/829/849 → se antepone el 1 de
    República Dominicana. Se exige el código de país: 11 a 15 dígitos."""
    if not raw:
        return None
    dig = re.sub(r'\D', '', str(raw))
    if dig.startswith('00'):
        dig = dig[2:]
    if len(dig) == 10 and dig[:3] in ('809', '829', '849'):
        dig = '1' + dig
    if 11 <= len(dig) <= 15:
        return dig
    return None


def contactos_de(est):
    """Padre, madre y tutor del estudiante (los que tengan nombre o teléfono)."""
    datos = {
        'tutor': (getattr(est, 'tutor', None), getattr(est, 'telefono_tutor', None),
                  getattr(est, 'parentesco_tutor', None)),
        'padre': (getattr(est, 'nombre_padre', None), getattr(est, 'telefono_padre', None), None),
        'madre': (getattr(est, 'nombre_madre', None), getattr(est, 'telefono_madre', None), None),
    }
    salida = []
    for rol in ORDEN_CONTACTOS:
        nombre, tel, parentesco = datos[rol]
        nombre = (nombre or '').strip()
        tel_raw = (tel or '').strip()
        if not nombre and not tel_raw:
            continue
        wa = telefono_whatsapp(tel_raw)
        salida.append({
            'rol': rol,
            'nombre': nombre or None,
            'parentesco': (parentesco or '').strip() or None,
            'telefono_whatsapp': wa,
            'telefono_final': (wa or re.sub(r'\D', '', tel_raw))[-4:] or None,
            'tiene_telefono': bool(tel_raw),
            'valido': wa is not None,
        })
    return salida


def contacto_sugerido(contactos):
    """El primero (tutor, padre, madre) con teléfono UTILIZABLE. Nunca uno que
    solo tenga nombre."""
    for c in contactos:
        if c['valido']:
            return c['rol']
    return None


# ─────────────────────────── Datos fijos ───────────────────────────

def huella_datos(vista):
    """Huella de lo que muestra el documento (sin la fecha de preparación):
    si coincide, volver a prepararlo daría el mismo contenido."""
    base = {k: v for k, v in vista.items() if k not in ('preparado',)}
    return hashlib.sha256(json.dumps(base, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def nombre_archivo(vista):
    nombre = re.sub(r'[^A-Za-z0-9]+', '_', _sin_tildes(vista.get('estudiante') or 'Estudiante')).strip('_')[:60]
    return f"Reporte_Periodo{vista.get('periodo')}_{nombre or 'Estudiante'}.pdf"


def _sin_tildes(s):
    import unicodedata
    return ''.join(ch for ch in unicodedata.normalize('NFKD', s) if not unicodedata.combining(ch))


# ─────────────────────────── Visitas ───────────────────────────

# Lectores de vista previa conocidos (agentes específicos: un «bot» genérico
# confundiría modelos de teléfono cuyo nombre lo contiene).
_UA_VISTA_PREVIA = ('whatsapp', 'facebookexternalhit', 'facebot', 'telegrambot', 'slackbot',
                    'twitterbot', 'discordbot', 'linkedinbot', 'skypeuripreview', 'googlebot', 'bingbot',
                    'applebot')


def es_vista_previa(user_agent):
    ua = (user_agent or '').lower()
    return any(p in ua for p in _UA_VISTA_PREVIA)


# ─────────────────────────── Página pública ───────────────────────────

CABECERAS_PRIVADAS = {
    'Cache-Control': 'no-store, private',
    'Pragma': 'no-cache',
    'X-Robots-Tag': 'noindex, nofollow, noarchive',
    'Referrer-Policy': 'no-referrer',
}

_CSS = """
:root{--azul:#1d4ed8;--azul-osc:#1e3a8a;--txt:#0f172a;--sub:#475569;--borde:#e2e8f0;--fondo:#f8fafc}
*{box-sizing:border-box}body{margin:0;font-family:system-ui,-apple-system,'Segoe UI',Roboto,Arial,sans-serif;color:var(--txt);background:var(--fondo)}
.barra{background:var(--azul-osc);color:#fff;padding:14px 16px;display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.barra b{font-size:18px}.barra .sep{opacity:.5}.barra span{font-weight:600}
main{max-width:640px;margin:0 auto;padding:20px 16px 40px}
h1{font-size:24px;margin:0 0 4px}.sub{color:var(--sub);margin:0 0 10px;font-size:16px}
.chip{display:inline-block;background:#dbeafe;color:var(--azul-osc);font-weight:600;border-radius:999px;padding:4px 12px;font-size:14px}
.fecha{color:var(--sub);font-size:14px;margin:8px 0 16px}
.doc{background:#fff;border:1px solid var(--borde);border-radius:10px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.doc h2{font-size:17px;margin:0}.doc .tit{color:var(--sub);font-size:13px;margin:2px 0 10px;padding-bottom:8px;border-bottom:2px solid var(--azul)}
.dato{font-size:14px;margin:3px 0}.dato b{font-weight:600}
table{width:100%;border-collapse:collapse;margin-top:12px;font-size:14px}
th,td{border:1px solid #cbd5e1;padding:6px 8px;text-align:left}th{background:#e2e8f0}td.n{text-align:center;width:72px}
.btn{display:block;text-align:center;background:var(--azul);color:#fff;text-decoration:none;font-weight:700;font-size:18px;border-radius:10px;padding:14px;margin-top:18px}
.btn2{display:block;text-align:center;color:var(--azul);text-decoration:none;font-weight:600;margin-top:10px;padding:8px}
.nota{color:var(--sub);font-size:13px;text-align:center;margin:10px 0 0}
.aviso{background:#fef3c7;border:1px solid #fcd34d;color:#78350f;border-radius:8px;padding:10px 12px;font-size:14px;margin-bottom:14px}
.info{border-top:1px solid var(--borde);margin-top:16px;padding-top:12px;color:var(--sub);font-size:13px;text-align:center}
"""


def _e(s):
    return html.escape(str(s if s is not None else ''), quote=True)


def _head(titulo, colegio):
    """Etiquetas de vista previa GENÉRICAS: ni nombre ni notas del estudiante."""
    desc = (f'{colegio} · Consulta y descarga el documento.' if colegio
            else 'Consulta y descarga el documento.')
    return (
        '<!doctype html><html lang="es"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta name="robots" content="noindex, nofollow, noarchive">'
        '<meta name="referrer" content="no-referrer">'
        f'<title>{_e(titulo)}</title>'
        '<meta property="og:site_name" content="EducaOne">'
        f'<meta property="og:title" content="{_e(titulo)}">'
        f'<meta property="og:description" content="{_e(desc)}">'
        '<meta property="og:type" content="website">'
        f'<style>{_CSS}</style></head><body>'
    )


def pagina_documento(vista, token, estado, preparado_txt):
    colegio = vista.get('colegio') or 'Centro Educativo'
    periodo = vista.get('periodo')
    filas = ''.join(
        f"<tr><td>{_e(f.get('asignatura'))}</td><td class='n'>{_e(f.get('nota') or 'Sin nota')}</td></tr>"
        for f in (vista.get('filas') or []))
    aviso = ''
    if estado == 'reemplazado':
        aviso = ('<div class="aviso">El colegio preparó una versión más reciente de este reporte. '
                 'Pida el enlace nuevo al colegio.</div>')
    ruta = ruta_publica(token)
    return (
        _head('Reporte de notas disponible', colegio)
        + f'<div class="barra"><b>EducaOne</b><span class="sep">|</span><span>{_e(colegio)}</span></div>'
        + '<main>'
        + aviso
        + '<h1>Reporte de notas</h1>'
        + f"<p class='sub'>{_e(vista.get('estudiante'))} · {_e(vista.get('curso'))}</p>"
        + f"<span class='chip'>{_e(ORDINAL_PERIODO_TITULO.get(periodo, ''))} período · {_e(vista.get('ano'))}</span>"
        + f"<p class='fecha'>Documento preparado el {_e(preparado_txt)}</p>"
        + '<div class="doc">'
        + f'<h2>{_e(colegio)}</h2><p class="tit">Reporte de calificaciones</p>'
        + f"<p class='dato'><b>Estudiante:</b> {_e(vista.get('estudiante'))}</p>"
        + f"<p class='dato'><b>Curso:</b> {_e(vista.get('curso'))}</p>"
        + f"<p class='dato'><b>Período:</b> {_e(ORDINAL_PERIODO_TITULO.get(periodo, ''))} período · {_e(vista.get('ano'))}</p>"
        + f'<table><thead><tr><th>Materia</th><th>Nota</th></tr></thead><tbody>{filas}</tbody></table>'
        + '</div>'
        + f'<a class="btn" href="{_e(ruta)}/pdf?descargar=1">Descargar PDF</a>'
        + f'<a class="btn2" href="{_e(ruta)}/pdf" target="_blank" rel="noopener noreferrer">Ver el PDF</a>'
        + '<p class="nota">Enlace sin vencimiento automático. El colegio puede anularlo.</p>'
        + '<p class="info">Este enlace es personal: cualquier persona que lo reciba podrá abrir este documento. '
          'No lo reenvíe si no desea compartirlo.</p>'
        + '</main></body></html>'
    )


def pagina_no_disponible(motivo):
    if motivo == 'anulado':
        cuerpo = ('<h1>Enlace anulado</h1><p class="sub">El colegio anuló este enlace. '
                  'Si necesita el reporte, solicítelo al colegio.</p>')
    else:
        cuerpo = ('<h1>Enlace no disponible</h1><p class="sub">Revise que el enlace esté completo '
                  'o solicítelo de nuevo al colegio.</p>')
    return (_head('Reporte de notas', None)
            + '<div class="barra"><b>EducaOne</b></div><main>' + cuerpo + '</main></body></html>')
