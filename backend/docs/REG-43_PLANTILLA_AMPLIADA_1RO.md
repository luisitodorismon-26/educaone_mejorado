# REG-43 · Registro de 1ro de Secundaria con 41–43 estudiantes

Adaptación excepcional y acotada: un curso de **1ro de Secundaria** con 41, 42 o
43 estudiantes se imprime sobre una versión de la plantilla oficial con **43
filas en el mismo alto** que las 40 originales. La aceptación del formulario
modificado para entrega oficial está **pendiente de confirmación por el centro**.

## Cuándo se usa cada plantilla

La decisión está en un único punto, `registro_escolar.seleccionar_plantilla(grado, n)`,
y la comparten el generador y el validador:

| Curso | Plantilla | Resultado |
|---|---|---|
| Hasta 40 estudiantes, cualquier grado | Oficial (`TEMPLATE_FILES[grado]`) | Sin cambios: mismo PDF que antes |
| 1ro con 41–43 | `Registro-1er-Grado-Sec-General-43-filas.pdf` | 43 filas en todas las tablas |
| 1ro con más de 43 | — | Error `ESTUDIANTES_EXCEDEN_PLANTILLA` |
| 2do–6to con más de 40 | — | Error `ESTUDIANTES_EXCEDEN_PLANTILLA` |

- **El error no recorta a nadie.** El validador lo da como error bloqueante, y el generador responde 422 con `mensaje` y `error` legibles.
- **No se extiende sola a otros grados.** Hay que medir su plantilla y añadirla a `PLANTILLAS_AMPLIADAS`.

## Qué cambia en la plantilla ampliada

En las 78 páginas con tabla de 40 filas se redibuja solo la rejilla del cuerpo
de la tabla. Cada fila pasa de 14,17 a 13,18 pt.

**Lo que no cambia:**
- tamaño de página, número de páginas (170) y columnas de fechas;
- tamaños de letra;
- encabezados, fila TOTALES, pies y números de página.

**Lo que se conserva dentro de la tabla:** líneas, sombreados por celda y
números de fila 1..43, estos con la fuente original de la plantilla.

Tablas afectadas:

| Tabla | Páginas |
|---|---|
| Datos generales | 11 |
| Condición inicial | 12 |
| Emergencias y parentesco | 13–14 |
| Asistencia | 17–55 |
| Asistencia a evaluaciones completivas y extraordinarias | 56–61 |
| Calificaciones | 131–148 |
| Completivas | 150–158 |
| Acta | 159–160 |

La plantilla se fabrica **una sola vez, fuera del servidor**, con:

```
python tools/generar_plantilla_43_filas.py \
    templates/registro_escolar/Registro-1er-Grado-Sec-General-1-1.pdf \
    templates/registro_escolar/Registro-1er-Grado-Sec-General-43-filas.pdf \
    informe.json
```

La herramienta requiere PyMuPDF, que **no** está en `requirements.txt`: el
servidor solo lee el PDF ya fabricado. Verificaciones hechas sobre la plantilla
resultante:

- **Fuera de las tablas:** 169 de las 170 páginas son idénticas píxel a píxel a la original. En la página 140 hay 38 píxeles de antialias en una palabra, por la reescritura del contenido que hace la herramienta; el texto y su posición son idénticos.
- **Dentro de las tablas:** el sombreado de las columnas se conserva en las 78 páginas.

## Geometría durante la generación

`generar_registro_escolar` activa la geometría de 43 filas en una `ContextVar`
solo durante esa generación.

- **Qué leen las funciones de dibujo:** la tabla, con `_geo(TABLA)`, y el máximo de filas, con `_filas_max()`.
- **Sin plantilla activa:** devuelven exactamente lo de siempre.
- **Varias generaciones a la vez** (el borrador corre en un threadpool): no se pisan. Esto se prueba con hilos simultáneos.

## Orden y número de lista

**El registro no renumera nada.** Los estudiantes se imprimen en el orden de su
`no_lista` (el mismo `order_by` de siempre en `app.py`). Cada fila lleva los
datos de ese estudiante: cédula, notas, asistencia, apellidos y nombre.

**Si los números de lista no son consecutivos**, el número impreso al margen es
la posición de la fila, como en la plantilla oficial, y no el `no_lista`.
Este comportamiento es el mismo que con 40 filas.

Consecuencias, que REG-43 no cambia:
- **El PDF no muestra el número de lista real.** Una fila se identifica por su
  posición, cruzándola con el apellido y nombre del acta (págs. 159–160) o con
  la cédula de la pág. 11.
- **El orden no tiene desempate.** `order_by(Estudiante.no_lista)` no usa un
  segundo criterio. La unicidad del número de lista la comprueba solo la
  aplicación, al crear o editar un estudiante activo; la base de datos no la
  impone. Con números repetidos o vacíos, el orden entre esos estudiantes no
  está garantizado: SQLite pone los vacíos al principio y PostgreSQL, al final.

## Recorridos de descarga

| Botón de la interfaz (`RegistroEscolarPage`) | Endpoint | Probado |
|---|---|---|
| Diagnosticar | `GET /api/registros/preview/{id}` | Suite e interfaz: 44 muestra el motivo |
| Imprimir Oficial | `GET /api/registros/secundaria/{id}` | Suite (40–44 y 2do con 41) e interfaz (40 y 43 descargan; 44 queda deshabilitado) |
| Vista Previa (BORRADOR) | `GET /api/registros/secundaria/{id}/preview-pdf` | Suite (40–44 y 2do con 41) e interfaz (43 descarga; 44 da 422 con mensaje) |

`GET /api/registro-escolar/generar/{id}` (antiguo) no lo usa la interfaz.
Pasa por el mismo `generar_registro_desde_sistema`, así que hereda la selección,
pero no tiene prueba propia de extremo a extremo.

## Pruebas

```
cd backend
python tools/test_registro_43_1ro.py [carpeta_pdfs]
```

Base SQLite aislada con datos sintéticos (`tools/registro_43_semilla.py`):
- números de lista con huecos y altas en otro orden;
- nota `100 − no_lista`;
- completiva (y a veces extraordinaria) con valores propios de cada estudiante
  para los que tienen nota < 70, que son las últimas filas;
- asistencia con una secuencia de marcas propia de cada estudiante.

Para los cursos de 1ro con 40, 41, 42 y 43, por la descarga oficial y por el
borrador, se comprueba fila a fila contra la semilla (no contra el generador).
«Su estudiante» es el i-ésimo por número de lista:

| Página | Qué se comprueba en cada fila |
|---|---|
| 11, datos generales | Cédula: todos, en orden, una vez |
| 17, asistencia de Lengua (sep–oct) | Secuencia de marcas; además, 40 o 43 números de fila impresos |
| 47, 50 y 53, asistencia compacta (Ed. Artística, Ed. Física y FIHR, sep–dic) | Secuencia completa de marcas |
| 131, calificaciones de Lengua | Todas las notas |
| 150–158, completivas de las 9 asignaturas | Secuencia exacta de columnas con dato |
| 159 y 160, acta | Apellido y nombre; final, completivo y extraordinario de cada asignatura |

En esas páginas se comprueba además:
- que las filas sobrantes queden vacías y no haya nada fuera de la tabla;
- con 41–43, las filas 41 a n por separado: que tengan contenido y sean de sus estudiantes.

**Rechazos.** Para 44 en 1ro y 41 en 2do se comprueban el validador, los dos
endpoints y la vista previa de la interfaz.

**Contexto de la plantilla.**
- **Generaciones simultáneas:** 43, 40 y 41 en hilos distintos usan cada una su plantilla.
- **Tras una excepción** durante la generación (un error real del dibujo, una excepción arbitraria, y en un hilo reutilizado) no queda plantilla activa, y la siguiente generación de 40 usa la de 40.

**Sin comprobación fila a fila:**
- condición inicial (pág. 12);
- emergencias y parentesco (13–14);
- asistencia a evaluaciones (56–61), que la plantilla deja en blanco;
- el resto de páginas de asistencia (18–46, 48–49, 51–52, 54–55) y de calificaciones (132–148).

La plantilla de esas páginas sí se verificó píxel a píxel al fabricarla.
