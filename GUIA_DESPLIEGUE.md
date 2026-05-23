# Guía de Despliegue EducaOne — Render + Vercel

Esta guía te lleva paso a paso para publicar EducaOne. Arquitectura:

```
Frontend (React)  → Vercel   (gratis)
Backend (FastAPI) → Render    (web service)
Base de datos     → Render    (PostgreSQL con backups)
```

Tiempo estimado: 1-2 horas la primera vez.

---

## ANTES DE EMPEZAR

Necesitás:
- [x] Código en GitHub (ya lo tenés)
- [ ] Cuenta en Render (render.com)
- [ ] Cuenta en Vercel (vercel.com) — podés entrar con tu GitHub

Asegurate de que en tu repo de GitHub estén:
- Carpeta `backend/` con `Procfile`, `requirements.txt`, `app.py`
- Carpeta `frontend/` con `package.json`

---

## PARTE 1 — BASE DE DATOS (PostgreSQL en Render)

**Hacé esto PRIMERO**, porque el backend la necesita.

1. Entrá a render.com → **New** → **PostgreSQL**
2. Configurá:
   - **Name:** `educaone-db`
   - **Database:** `educaone`
   - **Region:** Ohio o Oregon (los más cercanos a RD)
   - **Plan:** ⚠️ NO uses Free. El free se BORRA a los 30 días y no tiene backups.
     Elegí **Basic** (~$7-20/mes) para tener backups diarios.
3. Click **Create Database**
4. Esperá a que diga "Available"
5. Copiá el **Internal Database URL** (lo vas a necesitar). Se ve así:
   `postgresql://educaone:xxxxx@dpg-xxxxx/educaone`

---

## PARTE 2 — BACKEND (Web Service en Render)

1. En Render → **New** → **Web Service**
2. Conectá tu repo de GitHub (elegí el repo de EducaOne)
3. Configurá:
   - **Name:** `educaone-api`
   - **Region:** la MISMA que la base de datos
   - **Branch:** `main` (o la que uses)
   - **Root Directory:** `backend`  ← IMPORTANTE: que apunte a la carpeta backend
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** (dejalo vacío, usa el Procfile automáticamente)
     Si pide uno: `uvicorn app:app --host 0.0.0.0 --port $PORT --workers 4`
   - **Plan:** Starter ($7/mes) para arrancar; Standard ($25) al crecer

4. **Variables de entorno** (Environment → Add Environment Variable):

```
DATABASE_URL      = (pegá el Internal Database URL de la Parte 1)
SECRET_KEY        = (generá uno, ver abajo)
JWT_SECRET_KEY    = (generá OTRO distinto)
ALLOWED_ORIGINS   = https://tu-app.vercel.app
DEBUG             = False
WEB_CONCURRENCY   = 4
```

   **Para generar SECRET_KEY y JWT_SECRET_KEY**, en tu PC corré:
   ```
   python -c "import secrets; print(secrets.token_urlsafe(64))"
   ```
   Corrélo DOS veces (uno para cada clave). Son largos y aleatorios.

   ⚠️ El `ALLOWED_ORIGINS` lo vas a ajustar en la Parte 3 cuando tengas
   la URL real de Vercel. Por ahora poné algo temporal.

5. Click **Create Web Service**. Render va a:
   - Instalar dependencias
   - Arrancar el backend
   - Darte una URL como `https://educaone-api.onrender.com`

6. **Verificá** que arrancó: abrí `https://educaone-api.onrender.com/api/health`
   Debe responder algo (no error de conexión).

   ⚠️ Si NO arranca y ves un error sobre ALLOWED_ORIGINS o SECRET_KEY:
   es la protección de seguridad. Revisá que esas 3 variables estén bien.
   El sistema se niega a arrancar inseguro a propósito.

---

## PARTE 3 — FRONTEND (Vercel)

1. Entrá a vercel.com → **Add New** → **Project**
2. Importá tu repo de GitHub
3. Configurá:
   - **Framework Preset:** Vite
   - **Root Directory:** `frontend`  ← que apunte a la carpeta frontend
   - **Build Command:** `npm run build` (ya viene por defecto)
   - **Output Directory:** `dist` (por defecto en Vite)

4. **Variable de entorno** (Environment Variables):
```
VITE_API_URL = https://educaone-api.onrender.com
```
   (la URL de tu backend de la Parte 2, SIN barra al final)

5. Click **Deploy**. Vercel te da una URL como `https://educaone.vercel.app`

6. **AHORA volvé a Render** (Parte 2) y actualizá la variable:
```
ALLOWED_ORIGINS = https://educaone.vercel.app
```
   (la URL real que te dio Vercel). Guardá → Render reinicia el backend solo.

---

## PARTE 4 — PRIMER ARRANQUE Y DATOS

Cuando el backend arranca con una base vacía, necesita crear las tablas
y el primer usuario. Según cómo tengas configurado el arranque:

- Si el sistema crea las tablas solo al arrancar → ya están
- El primer superadmin: si no se crea solo, usá la Shell de Render
  (en el servicio backend → Shell) y corré tu script de seed/creación
  de usuario inicial.

Después:
1. Entrá a `https://educaone.vercel.app`
2. Login con el superadmin
3. Creá el primer colegio, su director, configurá módulos
4. Probá el flujo completo (ver Parte 5)

---

## PARTE 5 — VALIDACIÓN END-TO-END (CRÍTICO antes de dar acceso a un cliente)

Probá TODO el flujo en producción con un colegio de prueba:

- [ ] Login funciona
- [ ] Crear colegio + director
- [ ] Configurar módulos (primaria/secundaria)
- [ ] Crear grados y asignaturas (o que vengan cargados)
- [ ] Crear cursos
- [ ] Inscribir estudiantes
- [ ] Cargar calificaciones (profesor)
- [ ] Generar un boletín PDF
- [ ] Generar un reporte de conducta PDF
- [ ] Cerrar año → crear año nuevo → promover
- [ ] Verificar que un colegio NO ve datos de otro (seguridad multitenant)

Si TODO esto funciona en producción, estás listo para tu primer cliente real.

---

## PARTE 6 — BACKUPS (protección de datos)

1. **Backups automáticos de Render** (ya activos con plan de pago):
   - Render hace backup diario de PostgreSQL
   - Para restaurar: dashboard de la BD → Recovery → restaurar

2. **Backup adicional manual** (recomendado, tu red de seguridad extra):
   - En la Shell del backend de Render, corré: `python backup_datos.py`
   - Descargá el JSON generado y guardalo en Google Drive
   - Para automatizarlo: creá un **Cron Job** en Render (~$1/mes) que
     ejecute `python backup_datos.py` cada día

---

## COSTOS ESTIMADOS (2026)

| Etapa | Componentes | Costo aprox/mes |
|-------|-------------|-----------------|
| Arranque (1-20 colegios) | Vercel gratis + Render Starter + Postgres Basic | ~$27 |
| Crecimiento (20-50) | + Redis + Standard | ~$120 |
| 100 colegios | Pro + Postgres Standard + Redis | ~$200-300 |

Para 100 escuelas pagando, el costo de infraestructura es mínimo.

---

## ESCALADO (a medida que crezcas)

Cuando pases ~20 colegios:
1. Agregá **Redis** en Render (New → Redis) y poné la variable `REDIS_URL`
   en el backend → la caché pasa a ser compartida entre workers
2. Subí `WEB_CONCURRENCY` (4 → 8) según el plan
3. Subí el plan del backend (Starter → Standard → Pro)
4. Subí el plan de Postgres para point-in-time recovery

---

## PROBLEMAS COMUNES

**El backend no arranca / error 503:**
- Revisá los logs en Render (pestaña Logs)
- Causa común: falta una variable de entorno (SECRET_KEY, etc.)

**El frontend carga pero no conecta al backend (errores de red):**
- Revisá que `VITE_API_URL` en Vercel apunte a la URL correcta de Render
- Revisá que `ALLOWED_ORIGINS` en Render incluya la URL de Vercel
- Las dos tienen que coincidir

**"CORS error" en el navegador:**
- `ALLOWED_ORIGINS` en Render no incluye tu dominio de Vercel
- Agregalo exactamente como aparece (con https://, sin barra final)

**El backend tarda en responder la primera vez:**
- En plan Starter, el servicio "duerme" tras inactividad y tarda en
  despertar (~30s). Con plan de pago superior o tráfico constante, no pasa.
