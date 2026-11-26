#!/usr/bin/env bash
# Ejecuta el banco Linux para main y para el PR #81, dos rondas en orden alterno.
# Cada ejecución: base sintética NUEVA, semilla con el código de esa versión,
# servidor en un contenedor con 512 MiB y sin swap adicional, banco desde el runner.
# Requiere: imagen eo-memreg, red eo, contenedor pg, worktrees en /tmp/v/{main,rama}.
# Termina con error si alguna ejecución no produjo resultados (los artefactos se
# guardan igual: el paso de subida corre siempre).
set -uo pipefail
CI_DIR="$(cd "$(dirname "$0")" && pwd)"
RES=/tmp/res
mkdir -p "$RES"
FALLOS=0
# Claves SINTÉTICAS solo para esta prueba (no son de producción).
SK='clave-sesion-sintetica-ci-memoria-registro-0123456789abcdef'
JK='clave-jwt-sintetica-ci-memoria-registro-0123456789abcdef'

ejecutar() {
  local v="$1" ronda="$2"
  local etiq="${ronda}_${v}" db="eo_test_memreg_${v}_${ronda}"
  local out="$RES/$etiq" url="postgresql://eo_test@pg:5432/eo_test_memreg_${v}_${ronda}"
  mkdir -p "$out/io"
  echo "::group::$etiq"
  docker exec pg createdb -U eo_test "$db"
  if ! docker run --rm --network eo -v "/tmp/v/$v/backend:/app" -v "$CI_DIR:/ci:ro" -v "$out/io:/out" \
      -e DATABASE_URL="$url" -e DISABLE_GLOBAL_RATE_LIMIT=true -e LOG_DIR=/tmp/logs \
      eo-memreg python /ci/sembrar.py; then
    echo "::error::la semilla falló en $etiq"; FALLOS=$((FALLOS + 1)); echo "::endgroup::"; return
  fi
  if ! docker run --rm --network eo -v "/tmp/v/$v/backend:/app" -v "$CI_DIR:/ci:ro" -v "$out/io:/out" \
      -e DATABASE_URL="$url" -e SECRET_KEY="$SK" -e JWT_SECRET_KEY="$JK" -e LOG_DIR=/tmp/logs \
      eo-memreg python /ci/crear_token.py; then
    echo "::error::el token falló en $etiq"; FALLOS=$((FALLOS + 1)); echo "::endgroup::"; return
  fi
  docker run -d --name srv --network eo --memory=512m --memory-swap=512m -p 127.0.0.1:8000:8000 \
    -v "/tmp/v/$v/backend:/app" \
    -e DATABASE_URL="$url" -e DEBUG=true -e DISABLE_GLOBAL_RATE_LIMIT=true \
    -e SECRET_KEY="$SK" -e JWT_SECRET_KEY="$JK" -e LOG_DIR=/tmp/logs \
    eo-memreg uvicorn app:app --app-dir /app --host 0.0.0.0 --port 8000 --workers 2 --log-level warning
  python3 "$CI_DIR/banco_linux.py" "$etiq" srv "$out/banco" "$out/io/semilla.json" "$out/io/token.txt" \
    || { echo "::error::el banco terminó con error en $etiq"; FALLOS=$((FALLOS + 1)); }
  docker logs srv > "$out/servidor.log" 2>&1
  docker inspect srv > "$out/inspect.json"
  docker rm -f srv > /dev/null
  rm -f "$out/io/token.txt"   # el token sintético no se guarda en los artefactos
  echo "::endgroup::"
}

ejecutar main 1
ejecutar rama 1
ejecutar rama 2
ejecutar main 2
for r in 1_main 1_rama 2_rama 2_main; do
  [ -f "$RES/$r/banco/resumen.json" ] || { echo "::error::sin resultados en $r"; FALLOS=$((FALLOS + 1)); }
done
exit $(( FALLOS > 0 ? 1 : 0 ))
