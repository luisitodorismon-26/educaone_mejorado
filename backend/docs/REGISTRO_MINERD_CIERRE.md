# Cierre del Modulo de Registro MINERD

## Estado actual

El sistema ya cuenta con:

- flujo `v2` de preview y generacion
- validacion bloqueante de datos criticos
- asistencia basada en horario + ano escolar + dias no laborables + captura real
- generacion de PDF de secundaria conectada a la nueva matriz
- generacion de primaria mejorada con resumen de asistencia y calificaciones
- script reproducible de validacion demo

## Como validar localmente

Desde `backend`:

```powershell
python tools/validate_registros_minerd.py
```

Eso genera:

- `backend/artifacts/registro_minerd/registro_secundaria_demo.pdf`
- `backend/artifacts/registro_minerd/registro_primaria_demo.pdf`
- `backend/artifacts/registro_minerd/validation_summary.json`

## Checklist de validacion visual

Comparar cada PDF contra el formulario fisico MINERD y confirmar:

1. El nombre del centro cae dentro de su caja correcta.
2. El codigo del centro coincide con su casilla.
3. La seccion, grado y ano escolar no pisan lineas.
4. Los numeros de dias del mes se imprimen en la fila correcta.
5. Los estados `P`, `A`, `T`, `E` caen en la columna correcta.
6. Totales y porcentajes no invaden columnas vecinas.
7. Los nombres de estudiantes no se desbordan.
8. Las notas finales y calificaciones por area caen en sus casillas.
9. La tinta azul y tamano de fuente se ven aceptables al imprimir.
10. No hace falta correccion manual despues de imprimir.

## Criterio de salida real

El modulo solo debe considerarse terminado cuando:

- el preview detecta faltantes reales
- el PDF solo se genera con datos completos
- el documento impreso coincide con el formulario MINERD
- una persona del colegio puede usarlo sin editarlo a mano

## Deuda tecnica restante

- calibracion fina de coordenadas en primaria
- comparacion con formularios fisicos reales del cliente
- posible eliminacion definitiva del stack legacy `/api/registro-escolar/*`
- pruebas automatizadas dedicadas al modulo de registros
