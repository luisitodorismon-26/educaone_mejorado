"""
reglas_academicas.py
====================
Reglas de cálculo académico compartidas por el backend de EducaOne.

v2.20.0-A1 — REDONDEO ACADÉMICO DE CALIFICACIONES FINALES
--------------------------------------------------------
La calificación final que ve un estudiante / se usa para decidir aprobación
se redondea con el criterio tradicional dominicano: el decimal .5 SIEMPRE
sube (nunca "hacia el par").

Python `round()` aplica half-to-even (bankers rounding):
    round(66.5) == 66   round(68.5) == 68   round(70.5) == 70
Eso NO es lo que espera un boletín MINERD. Por eso las calificaciones
FINALES deben pasar por `redondear_calificacion_final()` y NO por `round()`.

IMPORTANTE: esta función NO muta el promedio exacto interno (p. ej.
`EvaluacionExtraSecundaria.cf_original`); solo produce el ENTERO visible /
de decisión a partir de él.
"""
from decimal import Decimal, ROUND_HALF_UP


def redondear_calificacion_final(valor):
    """
    Redondeo académico tradicional a entero.

        decimal <  .5  → baja
        decimal >= .5  → sube   (half-up, nunca half-to-even)

    Args:
        valor: número (int/float/Decimal/str numérico) o None.

    Returns:
        int con el valor redondeado, o None si `valor` es None.

    Ejemplos:
        66.5 → 67    67.5 → 68    68.5 → 69
        69.5 → 70    70.5 → 71    71.5 → 72
        69.49 → 69   69.50 → 70   69.80 → 70   69.99 → 70
    """
    if valor is None:
        return None
    return int(Decimal(str(valor)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
