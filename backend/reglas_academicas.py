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


def ponderar_y_redondear(valor_a, peso_a, valor_b, peso_b):
    """
    Pondera dos calificaciones con pesos exactos y redondea el resultado al
    entero con el criterio académico (.5 SIEMPRE sube).

    v2.20.0-A3 — PRECISIÓN DECIMAL DESDE LOS OPERANDOS
    -------------------------------------------------
    Toda la aritmética (multiplicación y suma) se hace en Decimal, con cada
    operando convertido vía `Decimal(str(v))` y cada peso como Decimal exacto.
    Así se evita el artefacto de coma flotante que ocurría al ponderar primero
    en float y recién después envolver en Decimal:

        0.3 * 17 + 0.7 * 92  →  69.49999999999999 (float)  →  69   ❌
        Decimal("0.3")*17 + Decimal("0.7")*92  →  69.5      →  70   ✅

    NO muta ninguno de los valores de entrada (en particular NO redondea ni
    convierte a entero la CF exacta / `cf_original`).

    Args:
        valor_a, valor_b: calificaciones (int/float/Decimal/str numérico) o None.
        peso_a, peso_b:   pesos exactos (str como "0.3" / "0.7" / "0.5", o Decimal).

    Returns:
        int redondeado (ROUND_HALF_UP), o None si algún valor es None.
    """
    if valor_a is None or valor_b is None:
        return None
    da = valor_a if isinstance(valor_a, Decimal) else Decimal(str(valor_a))
    db = valor_b if isinstance(valor_b, Decimal) else Decimal(str(valor_b))
    pa = peso_a if isinstance(peso_a, Decimal) else Decimal(str(peso_a))
    pb = peso_b if isinstance(peso_b, Decimal) else Decimal(str(peso_b))
    total = da * pa + db * pb
    return int(total.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
