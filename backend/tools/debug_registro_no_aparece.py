"""
Diagnóstico de "los datos no aparecen en el registro".

Uso:
    cd backend
    python tools/debug_registro_no_aparece.py [curso_id]

Si no pasas curso_id, usa el primero activo.

Lo que verifica:
1. Estado de asignaturas, año escolar, horarios.
2. Calificaciones reales en BD para el curso (cuántos parciales tiene cada estudiante en cada asignatura).
3. Asistencias reales en BD (con qué asignatura_id, en qué fechas, con qué estado).
4. Nombres exactos de las asignaturas (para detectar mismatch con el mapeo MINERD).
5. Simula el flujo del registro para una asignatura y dice exactamente
   por qué no encuentra los datos.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collections import defaultdict
from database import SessionLocal
from models import (
    Curso, Estudiante, Asignatura, AsignacionProfesor,
    Calificacion, Asistencia, AnoEscolar, Horario, ConfiguracionColegio
)


GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"


def header(texto):
    print(f"\n{BOLD}{BLUE}{'='*72}{RESET}")
    print(f"{BOLD}{BLUE}  {texto}{RESET}")
    print(f"{BOLD}{BLUE}{'='*72}{RESET}\n")


def ok(texto):
    print(f"  {GREEN}✓{RESET} {texto}")


def warn(texto):
    print(f"  {YELLOW}⚠{RESET} {texto}")


def err(texto):
    print(f"  {RED}✗{RESET} {texto}")


def info(texto):
    print(f"    {texto}")


def main():
    db = SessionLocal()
    
    curso_id = None
    if len(sys.argv) > 1:
        try:
            curso_id = int(sys.argv[1])
        except ValueError:
            pass
    
    # Resolver curso_id si no se pasó
    if not curso_id:
        curso = db.query(Curso).order_by(Curso.id.desc()).first()
        if not curso:
            err("No hay cursos en la BD")
            return
        curso_id = curso.id
        info(f"No se pasó curso_id, usando el último: {curso_id}")
    
    curso = db.query(Curso).filter_by(id=curso_id).first()
    if not curso:
        err(f"Curso {curso_id} no encontrado")
        return
    
    # === 1. Año escolar ===
    header("1. AÑO ESCOLAR")
    ano = db.query(AnoEscolar).filter_by(activo=True).first()
    if not ano:
        err("NO hay año escolar activo. Sin esto, build_asistencia_registro NO genera matriz.")
    else:
        ok(f"Año activo: {ano.nombre}")
        info(f"fecha_inicio: {ano.fecha_inicio}")
        info(f"fecha_fin:    {ano.fecha_fin}")
        if not ano.fecha_inicio or not ano.fecha_fin:
            err("fecha_inicio o fecha_fin están NULL — la matriz no se construye sin esto.")
    
    # === 2. Curso, estudiantes ===
    header("2. CURSO Y ESTUDIANTES")
    ok(f"Curso ID={curso.id}, nombre='{curso.nombre}', grado='{curso.grado.nombre if curso.grado else None}'")
    estudiantes = db.query(Estudiante).filter_by(
        curso_id=curso_id, activo=True
    ).order_by(Estudiante.no_lista).all()
    ok(f"{len(estudiantes)} estudiantes activos")
    if not estudiantes:
        err("No hay estudiantes — sin esto, no hay nada que pintar.")
        return
    
    # === 3. Asignaturas y nombres exactos ===
    header("3. ASIGNATURAS DEL COLEGIO")
    asignaturas = db.query(Asignatura).filter_by(colegio_id=curso.colegio_id).all()
    if not asignaturas:
        err("No hay asignaturas creadas en este colegio")
    else:
        info("Nombres exactos en BD:")
        for a in asignaturas:
            print(f"      [ID={a.id:3d}] '{a.nombre}'")
    
    # Verificar nombres MINERD esperados
    from registro_escolar import get_asignaturas_por_grado
    grado_numero = 1
    if curso.grado and curso.grado.nombre:
        import re
        m = re.search(r'(\d+)', curso.grado.nombre)
        if m:
            grado_numero = int(m.group(1))
    
    info(f"\nGrado detectado: {grado_numero}")
    asigs_minerd = get_asignaturas_por_grado(grado_numero)
    info(f"Asignaturas MINERD esperadas para grado {grado_numero}:")
    for k, n in asigs_minerd:
        print(f"      → '{n}'")
    
    # Cruzar para detectar mismatch
    info("\nCruce nombres:")
    nombres_bd = {a.nombre.lower(): a for a in asignaturas}
    
    mapeo_nombres = {
        'Lenguas Extranjeras - Inglés': ['Inglés', 'Ingles', 'English'],
        'Lenguas Extranjeras - Francés': ['Francés', 'Frances', 'French'],
        'Lengua Española': ['Lengua Española', 'Español', 'Lengua', 'Espanol'],
        'Matemática': ['Matemática', 'Matematica', 'Matemáticas', 'Matematicas'],
        'Ciencias Sociales': ['Ciencias Sociales', 'Sociales', 'Historia'],
        'Ciencias de la Naturaleza': ['Ciencias de la Naturaleza', 'Ciencias Naturales', 'Naturales'],
        'Educación Física': ['Educación Física', 'Educacion Fisica', 'Ed. Física', 'Física'],
        'Educación Artística': ['Educación Artística', 'Educacion Artistica', 'Arte', 'Artística'],
        'Formación Integral Humana y Religiosa': ['Formación Humana', 'Religión', 'FIHR', 'Valores', 'FHR'],
        'Salida Optativa': ['Salida Optativa', 'Optativa', 'Electiva'],
    }
    
    for k, asig_minerd in asigs_minerd:
        terminos = [asig_minerd] + mapeo_nombres.get(asig_minerd, [])
        encontrada = None
        for t in terminos:
            if t.lower() in nombres_bd:
                encontrada = nombres_bd[t.lower()]
                break
            for nbd, abd in nombres_bd.items():
                if t.lower() in nbd:
                    encontrada = abd
                    break
            if encontrada:
                break
        
        if encontrada:
            ok(f"'{asig_minerd}' → matchea con '{encontrada.nombre}' (ID={encontrada.id})")
        else:
            warn(f"'{asig_minerd}' → NO HAY MATCH. El registro saltará esta asignatura.")
    
    # === 4. Calificaciones ===
    header("4. CALIFICACIONES EN BD")
    califs = db.query(Calificacion).filter(
        Calificacion.estudiante_id.in_([e.id for e in estudiantes])
    ).all()
    
    info(f"Total calificaciones para estudiantes del curso: {len(califs)}")
    
    if not califs:
        err("NO HAY calificaciones para los estudiantes de este curso.")
    else:
        # Agrupar por asignatura y mostrar cuántas notas tiene cada una
        por_asig = defaultdict(list)
        for c in califs:
            por_asig[c.asignatura_id].append(c)
        
        for asig_id, lista in por_asig.items():
            asig = db.query(Asignatura).filter_by(id=asig_id).first()
            asig_nombre = asig.nombre if asig else f"(ID={asig_id} no existe)"
            info(f"\n  Asignatura '{asig_nombre}': {len(lista)} estudiantes con notas")
            
            # Mostrar primeros 3 con detalle del P1
            for c in lista[:3]:
                est = db.query(Estudiante).filter_by(id=c.estudiante_id).first()
                en = est.nombre_completo if est else "?"
                p1_parciales = [c.p1_p1, c.p1_p2, c.p1_p3, c.p1_p4]
                p1_llenos = sum(1 for p in p1_parciales if p is not None)
                pc1_real = c.calcular_pc(1)
                pc1_persistido = c.pc1
                
                tag = "✓" if pc1_real is not None else "✗"
                print(f"        {tag} {en}: P1 parciales={p1_parciales} (llenos={p1_llenos}/4)")
                print(f"            pc1 persistido={pc1_persistido}, calcular_pc(1)={pc1_real}")
                
                if p1_llenos > 0 and p1_llenos < 4:
                    warn(f"        → P1 incompleto: PC1 quedará VACÍO en el registro (lineamiento MINERD)")
    
    # === 5. Asistencias ===
    header("5. ASISTENCIAS EN BD")
    asists = db.query(Asistencia).filter(
        Asistencia.estudiante_id.in_([e.id for e in estudiantes])
    ).all()
    
    info(f"Total asistencias para estudiantes del curso: {len(asists)}")
    
    if not asists:
        err("NO HAY asistencias para los estudiantes de este curso.")
    else:
        # Por asignatura y por estado
        por_asig = defaultdict(int)
        por_estado = defaultdict(int)
        sin_asig = 0
        for a in asists:
            if a.asignatura_id is None:
                sin_asig += 1
            else:
                por_asig[a.asignatura_id] += 1
            por_estado[(a.estado or '').lower()] += 1
        
        if sin_asig:
            warn(f"{sin_asig} asistencias con asignatura_id=NULL — NO van a aparecer en el registro de secundaria (que es por materia).")
        
        info("Distribución por asignatura:")
        for asig_id, cant in por_asig.items():
            asig = db.query(Asignatura).filter_by(id=asig_id).first()
            n = asig.nombre if asig else f"ID={asig_id} (NO EXISTE)"
            print(f"      '{n}': {cant} asistencias")
        
        info("\nDistribución por estado:")
        ESTADOS_VALIDOS = {'presente', 'ausente', 'tardanza', 'excusa'}
        for estado, cant in por_estado.items():
            tag = "✓" if estado in ESTADOS_VALIDOS else "✗"
            color = GREEN if estado in ESTADOS_VALIDOS else RED
            print(f"      {color}{tag}{RESET} '{estado}': {cant} asistencias")
            if estado not in ESTADOS_VALIDOS:
                warn(f"          → estado '{estado}' NO se pinta (válidos: {ESTADOS_VALIDOS})")
        
        # Rango de fechas
        fechas = [a.fecha for a in asists if a.fecha]
        if fechas:
            info(f"\nRango de fechas asistencias: {min(fechas)} → {max(fechas)}")
            if ano and ano.fecha_inicio and ano.fecha_fin:
                fuera = [f for f in fechas if f < ano.fecha_inicio or f > ano.fecha_fin]
                if fuera:
                    warn(f"{len(fuera)} asistencias fuera del rango del año escolar ({ano.fecha_inicio} → {ano.fecha_fin})")
                    info(f"  Ejemplo: {fuera[0]}")
    
    # === 6. Horarios ===
    header("6. HORARIOS")
    horarios = db.query(Horario).filter_by(curso_id=curso_id, activo=True, tipo_bloque='clase').all()
    info(f"Horarios activos tipo 'clase' del curso: {len(horarios)}")
    
    if not horarios:
        warn("Sin horarios, build_asistencia_registro funciona en modo LEGACY (solo días con registros reales).")
    else:
        por_asig_h = defaultdict(list)
        for h in horarios:
            por_asig_h[h.asignatura_id].append(h.dia)
        info("Días de horario por asignatura:")
        for asig_id, dias in por_asig_h.items():
            asig = db.query(Asignatura).filter_by(id=asig_id).first()
            n = asig.nombre if asig else f"ID={asig_id}"
            print(f"      '{n}': {dias}")
    
    # === 7. Simular flujo real del registro para 1 asignatura ===
    header("7. SIMULACIÓN: ¿Qué vería el endpoint del registro?")
    
    # Tomar la primera asignatura que tenga datos
    asig_test = None
    for c in califs:
        if c.asignatura_id:
            asig_test = db.query(Asignatura).filter_by(id=c.asignatura_id).first()
            break
    if not asig_test and asists:
        for a in asists:
            if a.asignatura_id:
                asig_test = db.query(Asignatura).filter_by(id=a.asignatura_id).first()
                break
    
    if not asig_test:
        warn("No hay datos suficientes para simular. Mete al menos una nota o asistencia con asignatura_id.")
    else:
        info(f"Simulando para asignatura '{asig_test.nombre}' (ID={asig_test.id})")
        
        # Calificaciones que vería el endpoint
        calificaciones_dict = {}
        for idx, est in enumerate(estudiantes):
            calif = db.query(Calificacion).filter_by(
                estudiante_id=est.id, asignatura_id=asig_test.id
            ).first()
            if calif:
                pc1 = calif.pc1 if calif.pc1 is not None else calif.calcular_pc(1)
                pc2 = calif.pc2 if calif.pc2 is not None else calif.calcular_pc(2)
                pc3 = calif.pc3 if calif.pc3 is not None else calif.calcular_pc(3)
                pc4 = calif.pc4 if calif.pc4 is not None else calif.calcular_pc(4)
                cf = calif.cf if calif.cf is not None else (
                    round((pc1 + pc2 + pc3 + pc4) / 4, 2)
                    if all(p is not None for p in (pc1, pc2, pc3, pc4)) else None
                )
                calificaciones_dict[idx] = {
                    'pc1': pc1, 'pc2': pc2, 'pc3': pc3, 'pc4': pc4, 'cf': cf
                }
        
        info(f"\nCalificaciones que el endpoint pasaría al PDF para esta asignatura:")
        if not calificaciones_dict:
            err("VACÍO — el PDF saldrá sin calificaciones para esta asignatura.")
        else:
            for idx, d in calificaciones_dict.items():
                est = estudiantes[idx]
                vacios = [k for k, v in d.items() if v is None]
                tag_color = GREEN if not vacios else YELLOW
                print(f"        {tag_color}#{idx+1}{RESET} {est.nombre_completo}: {d}")
                if vacios:
                    print(f"          → vacíos en PDF: {vacios}")
        
        # Asistencias
        from registro_asistencia import build_asistencia_registro
        matriz = build_asistencia_registro(
            db, curso_id, asignatura_id=asig_test.id, estudiantes=estudiantes
        )
        
        info(f"\nMatriz de asistencia que vería el PDF para esta asignatura:")
        if not matriz:
            err("VACÍA — el PDF saldrá sin asistencia para esta asignatura.")
            info("Causas posibles:")
            info("  - Año escolar sin fecha_inicio/fecha_fin")
            info("  - Sin horario y sin registros que coincidan en rango del año")
            info("  - asignatura_id de las asistencias no es la misma que la de la asignatura")
        else:
            for mes in matriz:
                con_data = sum(1 for f in mes['filas'] if any(f['valores']))
                print(f"        Mes {mes['mes']}: {mes['total_dias']} días, fuente={mes['fuente_dias']}, {con_data} estudiantes con marcas")
                if con_data == 0:
                    warn(f"          → mes con días pero sin marcas — los datos no caen en estos días")
    
    print()
    db.close()


if __name__ == '__main__':
    main()
