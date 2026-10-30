# SALIDAS-MIXTAS · Componentes optativos por curso (4to–6to)

## Qué resuelve

El centro decide qué componentes de Salida Optativa imparte cada curso. En 4to imparte dos de salidas
distintas: Apreciación y Producción Literarias (HLM-LE-4) y Filosofía Social y Pensamiento Dominicano
(HCS-CS-4). Hasta ahora EducaOne tenía dos limitaciones:
- solo admitía los componentes de **una** salida;
- cambiar de salida **retiraba** los componentes anteriores, y al volver **creaba otra asignatura**. Así
  se produjo el duplicado que hay en producción: dos HLM-LE-4 con el profesor inactivo.

## Cómo se guarda

- **Sin cambio de esquema ni migración.** Cada componente es una fila de `curso_componentes_optativos`
  con su asignatura dedicada; el profesor es una `AsignacionProfesor` normal.
- **`POST /api/cursos/{id}/salida-optativa/componentes`** añade o actualiza **un** componente de
  cualquier salida del grado. No toca los demás componentes, las troncales ni otros cursos.
- **Componentes del curso** (`salida_optativa_service._componentes_de_curso`):
  - si todos los vinculados son de la salida del curso, los de esa salida, vinculados o pendientes, igual
    que antes;
  - si alguno es de otra salida, exactamente los vinculados.
- **`Curso.salida_optativa_codigo`** se conserva como rótulo de la portada y de la cabecera del acta.
- **Sin duplicados.** Si el curso ya tiene asignaturas dedicadas sin vincular para ese componente
  (`candidatas_identidad`), el `POST` y el `PUT` responden **409 `identidad_por_elegir`** con la lista y
  sus datos. Dirección elige con `asignatura_id` o pide expresamente `crear_identidad_nueva`. Nunca se
  crea, reactiva, elige ni borra nada automáticamente.
- **`asignatura_id` solo admite esas candidatas.** Cualquier otra asignatura —otro componente, otro curso,
  una materia propia del colegio, una troncal— responde **400 `identidad_no_valida`**, aunque sea del
  mismo colegio. Una de otro colegio o inexistente da 404. Una candidata inactiva no se reactiva sola.
- **Concurrencia.** El `PUT`, el `POST` y el `DELETE` bloquean la fila del curso (`SELECT … FOR UPDATE`)
  hasta el commit, así que dos peticiones simultáneas sobre el mismo curso se ejecutan una tras otra y la
  capacidad se comprueba sobre lo ya confirmado. Si aun así salta una unicidad, se responde
  **409 `conflicto_concurrente`** sin guardar nada.
- **Capacidad.** Si el curso quedaría con más de 2 componentes, **409 `capacidad_registro`** antes de
  guardar. El mensaje nombra todos los componentes.

## Cómo se imprime

El orden es el **slot del catálogo** en todos los espacios:

| Documento | Regla |
|---|---|
| Calificaciones y completivas | Página propia de cada componente (sin cambios) |
| Asistencia, bloques 1 y 2 (págs. 56–65) | Mismo orden; el rótulo «SALIDA OPTATIVA» es la salida **del componente**; los nombres largos se achican, ya no se cortan |
| Acta, págs. 225–226 | SO1/SO2 en el mismo orden (`curso_info['salida_optativa_slots']`); antes un componente de otra salida no aparecía |
| Boletín, filas SO1/SO2 | Mismo orden, con el nombre completo ajustado a la celda; las optativas van antes que las materias extra del colegio, que solo ocupan filas libres |
| Boletín, Música (u otra materia del colegio) con las dos optativas | **Fila compacta propia** bajo la tabla (416.9–432.4, 15.5 pt), con sus 16 notas, PC1–PC4, CF y la condición A/R de siempre. Las dos filas optativas no cambian y el boletín sigue teniendo dos páginas. Se dibuja con la cuadrícula y el color de la plantilla de cada grado, porque las columnas de 5to van ~3.6 pt a la derecha y su plantilla es rosa. No tapa ni desplaza asistencia, leyenda, situación ni firmas, que empiezan en 434.2. Solo se usa en ese caso: los boletines que ya cabían no cambian |
| Boletín, materias con notas que aun así no caben | Ya no se descartan: el boletín individual y el lote responden **409 `boletin_sin_fila`** con las materias y los estudiantes afectados. Pasa en 4to–6to con dos o más materias del colegio y las dos optativas, y en 1ro–3ro con una segunda materia extra. No se recortan datos ni se añaden páginas |

**Más de 2 componentes:** el registro oficial, el borrador, el boletín individual y el lote responden
409 y nombran los componentes. Ningún documento los omite en silencio. Su soporte completo queda
pendiente de una solución para los documentos.

## Pendiente (fuera de este cambio)

- **Dos o más materias del colegio junto a las dos optativas** en 4to–6to. Bajo la tabla solo cabe una
  fila compacta. Para más haría falta otra solución (por ejemplo, la hoja adicional que se presentó como
  alternativa B); mientras tanto se rechaza con un mensaje que nombra las materias.

- El rótulo «SALIDA OPTATIVA» de la portada y de la cabecera del acta sigue siendo la salida del curso.
  Cuando hay dos salidas, Dirección debe decidir qué figura ahí. Opciones, generadas con el código real
  para HLM + HCS:

  | Opción | Portada (146 pt) | Acta (258 pt) |
  |---|---|---|
  | A · salida del curso, «Humanidades y Lenguas Modernas» (actual) | Cabe | Cabe |
  | B · ambas completas, «Humanidades y Lenguas Modernas / Humanidades y Ciencias Sociales» | **No cabe** ni a 6 pt: se sale de la línea | Cabe |
  | C · códigos, «HLM / HCS» | Cabe | Cabe |
  | D · en blanco, a mano | — | — |

  La B en la portada necesitaría escribirse en dos líneas, lo que exige un cambio de código que no está
  hecho.
- Las págs. 69 y 73 (asistencia a evaluaciones completivas y extraordinarias) no se rellenan para
  ninguna asignatura: el sistema no guarda ese dato.
- La identidad de HLM-LE-4 del curso 29 de producción (asignaturas 25 y 27) se resolverá por separado,
  después de la auditoría. Este cambio solo impide que se cree una tercera.

## Pruebas

- `tools/test_salidas_mixtas_4to.py`: configuración, duplicados, mismo maestro, documentos completos,
  3 componentes y un curso de una sola salida.
- `tools/test_boletin_fila_compacta.py`: fila compacta en 4to, 5to y 6to con el generador real. Fuera de
  la fila, el boletín es idéntico píxel a píxel al mismo sin Música. Comprueba las notas, PC, CF y A/R,
  la cuadrícula y el color de cada plantilla.
- `tools/test_salidas_concurrencia_pg.py`: concurrencia real en PostgreSQL. Recibe solo la conexión de
  administración a un servidor local (`EO_PG_TEST_SERVER`) y trabaja en una base temporal que crea ella
  misma, con nombre único y un token propio. Antes de crear tablas verifica que la base conectada es esa
  y que está vacía; además comprueba que una base ordinaria se rechaza sin modificarla. Al terminar
  elimina solo esa base. Se ejecuta primero sin bloqueo, como control que debe mostrar la carrera, y
  después con el código real.
- `tools/test_salida_optativa_r34.py` §D3: ahora elige explícitamente la asignatura existente en vez de
  crear otra.
