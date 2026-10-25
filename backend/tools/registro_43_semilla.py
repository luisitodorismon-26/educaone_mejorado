# -*- coding: utf-8 -*-
"""
REG-43 · Datos SINTÉTICOS para probar el Registro de 1ro de Secundaria con
40-44 estudiantes. Solo para bases aisladas (tests y prueba local de la
interfaz); nunca producción.

Un año escolar YA TERMINADO (2025-2026), para que el validador del Registro
oficial pase sin errores ni advertencias: notas completas (4 competencias × 4
períodos), un día de horario por asignatura y asistencia en todas las fechas
previstas.

Cada estudiante es reconocible en el PDF por datos derivados de SU número de
lista, que además NO es consecutivo (hay huecos) y no coincide con el orden de
alta:
    cédula      001-<curso>-<no_lista con 4 cifras>-1
    nota        100 - no_lista       (la misma en las 4 competencias y períodos)
    completiva  con nota < 70 (no_lista > 30, es decir, las últimas filas):
                CEC = 131 - no_lista; si la completiva no llega a 70, también
                extraordinaria con CEEX = 30 + no_lista. Valores propios de
                cada estudiante, para verlos en Completivas y en el Acta.
    asistencia  A, T o P según un hash de (no_lista, fecha): cada estudiante tiene
                su propia secuencia de marcas, distinta de la de sus vecinos
"""
import datetime as dt
import hashlib

INICIO, FIN = dt.date(2025, 9, 1), dt.date(2026, 6, 19)   # 10 meses: los huecos de la hoja
# Nombre MINERD (ASIGNATURAS_CICLO_1) y bloque oficial, en el orden del Registro
ASIGNATURAS = [
    ('Lengua Española', 'LE'), ('Lenguas Extranjeras - Inglés', 'LEI'),
    ('Lenguas Extranjeras - Francés', 'LEF'), ('Matemática', 'MAT'),
    ('Ciencias Sociales', 'CS'), ('Ciencias de la Naturaleza', 'CN'),
    ('Educación Artística', 'EA'), ('Educación Física', 'EF'),
    ('Formación Integral Humana y Religiosa', 'FIHR'),
]
DIAS = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes']


def no_listas(n):
    """n números de lista con un hueco cada 4: 1 2 3 4 6 7 8 9 11 ..."""
    return [i + 1 + i // 4 for i in range(n)]


def nota(no_lista):
    return 100 - no_lista


def _redondeo(x):
    return int(x + 0.5)


def evaluacion_extra(no_lista):
    """Completiva (y, si hace falta, extraordinaria) de un estudiante con nota < 70."""
    v = nota(no_lista)
    if v >= 70:
        return None
    cec = 131 - no_lista
    comp = _redondeo(0.5 * v + 0.5 * cec)
    ev = {'cf_original': v, 'cec': cec, 'completiva_final': comp}
    if comp >= 70:
        ev.update(condicion_final='aprobado_completiva', nota_final=comp)
    else:
        ceex = 30 + no_lista
        ext = _redondeo(0.3 * v + 0.7 * ceex)
        ev.update(ceex=ceex, extraordinaria_final=ext, nota_final=ext,
                  condicion_final='aprobado_extraordinaria' if ext >= 70 else 'reprobado')
    return ev


def nota_final(no_lista):
    ev = evaluacion_extra(no_lista)
    return ev['nota_final'] if ev else nota(no_lista)


def estado(no_lista, fecha):
    # Un hash y no (no_lista + fecha) % k: con un día fijo de clase por semana,
    # las fechas avanzan de 7 en 7 y una fórmula modular repetiría la misma marca
    # todo el mes, sin distinguir a un estudiante de otro.
    r = int(hashlib.md5(('%d|%s' % (no_lista, fecha.isoformat())).encode()).hexdigest(), 16) % 7
    return 'ausente' if r == 0 else ('tardanza' if r == 3 else 'presente')


def cedula(curso_tag, no_lista):
    return '001-%s-%04d-1' % (curso_tag, no_lista)


def fechas_asignatura(idx):
    """Fechas de clase de la asignatura idx: un día fijo por semana."""
    out, d = [], INICIO
    while d <= FIN:
        if d.weekday() == idx % 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def sembrar(db, M, cursos, password_hash='x', codigo='REG43'):
    """Crea colegio, año, grado(s) y los cursos pedidos.

    cursos: lista de (grado_numero, seccion, n_estudiantes).
    Devuelve dict con colegio, director y {seccion: curso}.
    """
    def add(o):
        db.add(o)
        db.flush()
        return o

    col = add(M.Colegio(nombre='Colegio Sintético REG-43', codigo=codigo, activo=True))
    add(M.ConfiguracionColegio(colegio_id=col.id, nombre=col.nombre, regional='10', distrito='10-01',
                               codigo_centro='99999', director='Directora Sintética'))
    ano = add(M.AnoEscolar(colegio_id=col.id, nombre='2025-2026', activo=True, cerrado=False,
                           fecha_inicio=INICIO, fecha_fin=FIN))
    tanda = add(M.Tanda(colegio_id=col.id, nombre='Vespertina', hora_inicio='13:00', hora_fin='18:00', activo=True))
    dire = add(M.Usuario(colegio_id=col.id, username='%s_dir' % codigo.lower(), password_hash=password_hash,
                         nombre='Directora', apellido='Sintética', role='direccion', activo=True,
                         must_change_password=False, token_version=0))
    profes, asigs = [], []
    for i, (nombre, area) in enumerate(ASIGNATURAS):
        profes.append(add(M.Usuario(colegio_id=col.id, username='%s_prof%d' % (codigo.lower(), i),
                                    password_hash='x', nombre='Docente%d' % (i + 1), apellido='Sintético',
                                    role='profesor', activo=True, must_change_password=False, token_version=0)))
        asigs.append(add(M.Asignatura(colegio_id=col.id, nombre=nombre, area_curricular_codigo=area)))
    grados, salida = {}, {'colegio': col, 'director': dire, 'ano': ano, 'cursos': {}, 'asignaturas': asigs}
    for g, seccion, n in cursos:
        if g not in grados:
            grados[g] = add(M.Grado(colegio_id=col.id, nombre='%d%s Secundaria' % (g, {1: 'ro', 2: 'do', 3: 'ro'}.get(g, 'to')),
                                    nivel='secundaria', orden=g, activo=True))
        curso = add(M.Curso(colegio_id=col.id, nombre=seccion, grado_id=grados[g].id, tanda_id=tanda.id,
                            ano_escolar_id=ano.id, activo=True))
        for i, (a, p) in enumerate(zip(asigs, profes)):
            add(M.AsignacionProfesor(colegio_id=col.id, profesor_id=p.id, curso_id=curso.id, asignatura_id=a.id,
                                     ano_escolar_id=ano.id, activo=True, es_titular=(i == 0)))
            add(M.Horario(colegio_id=col.id, profesor_id=p.id, curso_id=curso.id, asignatura_id=a.id,
                          dia=DIAS[i % 5], hora_inicio='%02d:00' % (13 + i // 5), hora_fin='%02d:50' % (13 + i // 5),
                          tipo_bloque='clase', activo=True))
        nls = no_listas(n)
        # Alta en orden distinto del número de lista: el Registro tiene que ordenar por no_lista.
        orden_alta = nls[1::2] + nls[0::2]
        ests = []
        for nl in orden_alta:
            ests.append(add(M.Estudiante(
                colegio_id=col.id, matricula='%s-%s-%d' % (codigo, seccion, nl), nombre='Nombre%d' % nl,
                apellido='Apellido%d%s' % (nl, seccion), curso_id=curso.id, no_lista=nl, activo=True,
                condicion='activo', sexo='F' if nl % 2 else 'M', fecha_nacimiento=dt.date(2013, 1 + nl % 12, 1 + nl % 28),
                cedula=cedula(seccion, nl), fecha_ingreso=dt.date(2025, 8, 1))))
        filas_cal, filas_as = [], []
        for e in ests:
            v = nota(e.no_lista)
            ev = evaluacion_extra(e.no_lista)
            for a in asigs:
                for comp in (1, 2, 3, 4):
                    filas_cal.append(M.CalificacionSecundaria(
                        colegio_id=col.id, estudiante_id=e.id, asignatura_id=a.id, ano_escolar_id=ano.id,
                        competencia_numero=comp, p1=v, p2=v, p3=v, p4=v))
                if ev:
                    filas_cal.append(M.EvaluacionExtraSecundaria(
                        colegio_id=col.id, estudiante_id=e.id, asignatura_id=a.id, ano_escolar_id=ano.id, **ev))
        for i, a in enumerate(asigs):
            for f in fechas_asignatura(i):
                for e in ests:
                    filas_as.append(M.Asistencia(colegio_id=col.id, estudiante_id=e.id, curso_id=curso.id,
                                                 asignatura_id=a.id, fecha=f, estado=estado(e.no_lista, f),
                                                 registrado_por=profes[i].id))
        db.add_all(filas_cal)
        db.add_all(filas_as)
        db.flush()
        salida['cursos'][seccion] = curso
    db.commit()
    return salida
