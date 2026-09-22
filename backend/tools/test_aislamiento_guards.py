# -*- coding: utf-8 -*-
"""
INFRA-2 — los guards de `test_utils` comprobados disparando de verdad.

POR QUE EXISTE
    `test_utils` es lo que impide que seis suites legacy vuelvan a borrar la
    base de datos local. Un mecanismo de seguridad que nadie prueba es una
    creencia, no una proteccion: esta suite intenta romperlo a proposito y
    exige que se defienda.

    Cada caso se ejecuta en un PROCESO APARTE porque varios terminan en
    `SystemExit` o en un import que fija el engine, y eso no se puede
    deshacer dentro del mismo interprete.

QUE CUBRE
    A. el aislador se niega si llega tarde (el engine ya esta construido);
    B. el engine sobre una base real se rechaza;
    C. el engine en un temporal ajeno se rechaza;
    D. el caso bueno sigue adelante;
    E. el cleanup se niega con el repositorio;
    F. el cleanup se niega con la raiz del TEMP;
    G. el cleanup se niega con el temporal de OTRO programa  (A1);
    H. un temporal con el mismo PREFIJO no cuenta como dentro (A1).

    G y H son los dos que la revision independiente echo en falta, y ambos
    fallaban antes del hardening.

Uso:
    cd backend
    python tools/test_aislamiento_guards.py
"""
import os
import shutil
import subprocess
import sys
import tempfile

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)

G, R, B, C, X = "\033[92m", "\033[91m", "\033[1m", "\033[96m", "\033[0m"
_ok, _fallos = 0, []

CABECERA = (
    "import sys, os, tempfile, shutil\n"
    "sys.path.insert(0, r'%s')\n"
    "sys.path.insert(0, r'%s')\n" % (_BACKEND, _AQUI)
)


def caso(nombre, cuerpo, exit_esperado, texto_esperado=None):
    """Ejecuta `cuerpo` en un proceso nuevo y comprueba como termina."""
    global _ok
    tmp = tempfile.mkdtemp(prefix="guardcaso_")
    ruta = os.path.join(tmp, "caso.py")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(CABECERA + cuerpo)
    try:
        r = subprocess.run([sys.executable, ruta], capture_output=True,
                           text=True, cwd=_BACKEND, timeout=300,
                           env=dict(os.environ, PYTHONUTF8="1",
                                    PYTHONIOENCODING="utf-8"))
        salida = (r.stdout or "") + (r.stderr or "")
        problemas = []
        if r.returncode != exit_esperado:
            problemas.append("exit %s (esperado %s)" % (r.returncode, exit_esperado))
        if texto_esperado and texto_esperado not in salida:
            problemas.append("falta el texto %r" % texto_esperado)
        if problemas:
            _fallos.append((nombre, "; ".join(problemas)))
            print("  %sFALLA%s %s\n        %s\n        %s"
                  % (R, X, nombre, "; ".join(problemas), salida[:400]))
        else:
            _ok += 1
            print("  %sPASA%s  %s" % (G, X, nombre))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


print("\n%sGUARDS DE test_utils%s" % (B, X))

# ── A. llegar tarde ──────────────────────────────────────────────────
caso("A  aislar despues de importar database -> RuntimeError",
     "import database\n"
     "from test_utils import aislar_base_de_datos\n"
     "aislar_base_de_datos('tarde')\n",
     exit_esperado=1, texto_esperado="DESPUES de importar")

# ── B. base real ─────────────────────────────────────────────────────
caso("B  engine sobre sge.db -> exit 9",
     "from test_utils import aislar_base_de_datos, verificar_engine_aislado\n"
     "from sqlalchemy import create_engine\n"
     "t = aislar_base_de_datos('b')\n"
     "verificar_engine_aislado(create_engine('sqlite:///sge.db'), t)\n",
     exit_esperado=9, texto_esperado="AISLAMIENTO ROTO")

# ── C. temporal ajeno ────────────────────────────────────────────────
caso("C  engine en un temporal ajeno -> exit 9",
     "from test_utils import aislar_base_de_datos, verificar_engine_aislado\n"
     "from sqlalchemy import create_engine\n"
     "t = aislar_base_de_datos('c')\n"
     "ajeno = tempfile.mkdtemp(prefix='ajeno_')\n"
     "url = 'sqlite:///' + os.path.join(ajeno, 'x.db').replace(os.sep, '/')\n"
     "try:\n"
     "    verificar_engine_aislado(create_engine(url), t)\n"
     "finally:\n"
     "    shutil.rmtree(ajeno, ignore_errors=True)\n",
     exit_esperado=9, texto_esperado="AISLAMIENTO ROTO")

# ── D. el caso bueno ─────────────────────────────────────────────────
caso("D  aislamiento correcto -> sigue adelante",
     "from test_utils import aislar_base_de_datos, verificar_engine_aislado\n"
     "t = aislar_base_de_datos('bueno')\n"
     "from database import engine\n"
     "verificar_engine_aislado(engine, t)\n"
     "print('OK aislado')\n",
     exit_esperado=0, texto_esperado="OK aislado")

# ── E. el repositorio ────────────────────────────────────────────────
caso("E  cleanup apuntado al repositorio -> rechazo",
     "from test_utils import _limpiar\n"
     "repo = r'%s'\n" % _BACKEND +
     "assert os.path.isdir(repo)\n"
     "_limpiar(repo)\n"
     "assert os.path.isdir(repo), 'BORRO EL REPOSITORIO'\n"
     "assert os.path.exists(os.path.join(repo, 'app.py')), 'falta app.py'\n"
     "print('OK repositorio intacto')\n",
     exit_esperado=0, texto_esperado="OK repositorio intacto")

# ── F. la raiz del TEMP ──────────────────────────────────────────────
caso("F  cleanup apuntado a la raiz del TEMP -> rechazo",
     "from test_utils import _limpiar\n"
     "raiz = tempfile.gettempdir()\n"
     "_limpiar(raiz)\n"
     "assert os.path.isdir(raiz), 'BORRO EL TEMP ENTERO'\n"
     "print('OK temp intacto')\n",
     exit_esperado=0, texto_esperado="OK temp intacto")

# ── G. temporal HERMANO, de otro programa (A1) ───────────────────────
caso("G  cleanup sobre el temporal de otro programa -> rechazo",
     "from test_utils import aislar_base_de_datos, _limpiar\n"
     "propio = aislar_base_de_datos('educaone_propietario')\n"
     "ajeno = tempfile.mkdtemp(prefix='otro_programa_')\n"
     "testigo = os.path.join(ajeno, 'datos_de_otro.txt')\n"
     "open(testigo, 'w').write('no es mio')\n"
     "try:\n"
     "    _limpiar(ajeno)\n"
     "    assert os.path.isdir(ajeno), 'BORRO EL TEMPORAL AJENO'\n"
     "    assert os.path.exists(testigo), 'BORRO EL CONTENIDO AJENO'\n"
     "    # y el propio si puede borrarse\n"
     "    _limpiar(propio)\n"
     "    assert not os.path.isdir(propio), 'no borro el suyo'\n"
     "    print('OK ajeno intacto, propio borrado')\n"
     "finally:\n"
     "    # limpieza del hermano con la herramienta del TEST, no con el helper\n"
     "    shutil.rmtree(ajeno, ignore_errors=True)\n",
     exit_esperado=0, texto_esperado="OK ajeno intacto, propio borrado")

# ── H. prefijo enganoso (A1) ─────────────────────────────────────────
caso("H  engine en un temporal de prefijo enganoso -> exit 9",
     "from test_utils import aislar_base_de_datos, verificar_engine_aislado\n"
     "from sqlalchemy import create_engine\n"
     "t = aislar_base_de_datos('eo_test')\n"
     "hermano = t + '_otro'\n"
     "os.makedirs(hermano, exist_ok=True)\n"
     "url = 'sqlite:///' + os.path.join(hermano, 'test.db').replace(os.sep, '/')\n"
     "try:\n"
     "    verificar_engine_aislado(create_engine(url), t)\n"
     "finally:\n"
     "    shutil.rmtree(hermano, ignore_errors=True)\n",
     exit_esperado=9, texto_esperado="NO cuelga del temporal")

# ── extra: el registro de propiedad se vacia al limpiar ──────────────
caso("I  el registro de propiedad se libera tras borrar",
     "import test_utils as TU\n"
     "t = TU.aislar_base_de_datos('registro')\n"
     "assert TU._clave(t) in TU._TEMPORALES_PROPIOS, 'no quedo registrado'\n"
     "TU._limpiar(t)\n"
     "assert TU._clave(t) not in TU._TEMPORALES_PROPIOS, 'quedo registrado'\n"
     "assert not os.path.isdir(t)\n"
     "print('OK registro liberado')\n",
     exit_esperado=0, texto_esperado="OK registro liberado")

print("\n" + "=" * 66)
if _fallos:
    print("%s%sGUARDS DE AISLAMIENTO: %d fallo(s) de %d%s"
          % (R, B, len(_fallos), _ok + len(_fallos), X))
    for n, e in _fallos:
        print("  - %s: %s" % (n, e))
    sys.exit(1)
print("%sGUARDS DE AISLAMIENTO: %d/%d pruebas%s" % (B, _ok, _ok, X))
print("%s%sTODO VERDE%s" % (G, B, X))
