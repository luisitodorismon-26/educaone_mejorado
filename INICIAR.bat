@echo off
REM ====================================================================
REM  EducaOne - Iniciar sistema completo (backend + frontend)
REM  Doble clic en este archivo. Abre 2 ventanas automaticamente.
REM ====================================================================
echo Iniciando EducaOne...
echo.

REM --- Backend en puerto 8080 ---
start "EducaOne BACKEND (puerto 8080)" cmd /k "cd /d %~dp0backend && set DATABASE_URL=sqlite:///./educaone.db&& set SECRET_KEY=dev-secret-cambiar&& set JWT_SECRET_KEY=dev-jwt-cambiar&& uvicorn app:app --port 8080"

REM --- Esperar 3 segundos a que el backend arranque ---
timeout /t 3 /nobreak >nul

REM --- Frontend ---
start "EducaOne FRONTEND (puerto 5173)" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo ============================================================
echo  Se abrieron 2 ventanas:
echo    1. BACKEND  (puerto 8080) - dejala abierta
echo    2. FRONTEND (puerto 5173) - dejala abierta
echo.
echo  Abri el navegador en:  http://localhost:5173
echo ============================================================
echo.
echo  Para apagar todo: cerra las 2 ventanas que se abrieron.
echo.
pause
