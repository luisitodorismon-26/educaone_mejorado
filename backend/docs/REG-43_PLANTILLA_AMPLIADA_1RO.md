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

Base SQLite aislada y datos sintéticos (`tools/registro_43_semilla.py`):
números de lista con huecos y altas en otro orden. Comprueba lo siguiente:

- en cada página, todos los estudiantes, una sola vez y en orden;
- en cada fila, los datos de su estudiante;
- las filas sobrantes, vacías;
- la plantilla elegida;
- los rechazos con su motivo;
- las generaciones simultáneas.
