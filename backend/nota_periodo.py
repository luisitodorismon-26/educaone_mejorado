# -*- coding: utf-8 -*-
"""
nota_periodo.py — LA nota del período de una asignatura, para reportar.

Es la nota que se entrega al estudiante y a sus padres al cierre de cada
período, y la que muestran la pantalla «Notas por Período», su tabla general
en PDF y el Reporte del Período para padres. Las tres la toman de aquí.

    Nota del período = el valor del período en la competencia MÁS ALTA que lo
    tenga registrado, buscando de la 4 a la 1.

    70, 75, 80, 85      -> 85   (no 77.5: no es un promedio)
    70, 90, —,  —       -> 90   (incompleta: la última con dato)
    70, 75, 80, 0       -> 0    (un 0 es una nota, no un vacío)
    —,  —,  —,  —       -> None

No es la última nota EDITADA ni el P4 del año: es la del período elegido. El
valor de cada competencia lo da su propio modelo (`valor_periodo`), con la
regla vigente de su nivel: en Secundaria, el mayor entre P y RP. Este módulo
no calcula promedios oficiales ni toca ningún motor académico.
"""


def nota_del_periodo(competencias, periodo):
    """Nota del período (o None) a partir de las competencias de UNA asignatura.

    `competencias`: dict {numero: fila} o lista de filas con `competencia_numero`.
    Cada fila debe tener `valor_periodo(periodo)`.
    """
    if not competencias:
        return None
    if isinstance(competencias, dict):
        por_numero = competencias
    else:
        por_numero = {getattr(c, 'competencia_numero', None): c for c in competencias}
    for numero in (4, 3, 2, 1):
        fila = por_numero.get(numero)
        if fila is None:
            continue
        valor = fila.valor_periodo(periodo)
        if valor is not None:
            return valor
    return None


def promedio_de_notas(notas):
    """«Prom.» de la vista: promedio de las notas del período de un estudiante
    entre sus asignaturas, con un decimal y redondeo HALF-UP (81.25 -> 81.3).
    Es una cifra de consulta, no un promedio oficial. Pantalla y PDF la toman
    de aquí para no diferir por la regla de redondeo."""
    from decimal import Decimal, ROUND_HALF_UP
    vals = [float(n) for n in notas if n is not None]
    if not vals:
        return None
    media = Decimal(repr(sum(vals))) / Decimal(len(vals))
    return float(media.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP))


def formatear_nota(valor):
    """Cómo se ESCRIBE la nota en pantalla y en los PDF del período: entera si
    lo es, si no con un decimal (el mismo criterio del boletín oficial). No
    redondea hacia una entera ni trunca: 84.5 se ve 84.5, no 85 ni 84. None ->
    None (cada documento pone su propio vacío)."""
    if valor is None:
        return None
    v = float(valor)
    if abs(v - round(v)) < 0.05:
        return str(int(round(v)))
    return '%.1f' % v
