"""Simulación REAL de UI para reproducir el bug del usuario."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import engine
db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'sge.db')
for ext in ['', '-shm', '-wal']:
    if os.path.exists(db_path + ext): os.remove(db_path + ext)

from models import Base
Base.metadata.create_all(bind=engine)

from fastapi.testclient import TestClient
from app import app
from database import SessionLocal
from models import (Calificacion, Asistencia, Estudiante, Usuario, AnoEscolar,
                    Asignatura, Curso, Grado, Tanda)

GREEN, RED, YELLOW, BOLD, RESET = "\033[92m", "\033[91m", "\033[93m", "\033[1m", "\033[0m"
def step(n,t): print(f"\n{BOLD}▶ {n}. {t}{RESET}")
def ok(t): print(f"  {GREEN}✓{RESET} {t}")
def err(t): print(f"  {RED}✗{RESET} {t}")
def warn(t): print(f"  {YELLOW}⚠{RESET} {t}")
def info(t): print(f"    {t}")
def auth(tok): return {'Authorization': f'Bearer {tok}'}

client = TestClient(app)

with client:
    # 1. SUPERADMIN — leer credenciales de INITIAL_CREDENTIALS.txt
    import re as _re
    cred_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'INITIAL_CREDENTIALS.txt')
    super_pw_inicial = None
    if os.path.exists(cred_path):
        with open(cred_path) as f:
            txt = f.read()
        m = _re.search(r'Usuario:\s+superadmin\s*\n\s+Contraseña:\s+(\S+)', txt)
        if m:
            super_pw_inicial = m.group(1)
    
    if not super_pw_inicial:
        print("ERROR: no se encontró password inicial del superadmin en INITIAL_CREDENTIALS.txt")
        sys.exit(1)
    
    r = client.post('/api/auth/login', json={'username':'superadmin','password': super_pw_inicial})
    assert r.status_code == 200, f"login superadmin: {r.text}"
    super_token = r.json()['token']
    
    # Como must_change_password=True, todo endpoint protegido devuelve 423.
    # Verificamos eso y luego cambiamos password.
    r_test = client.get('/api/superadmin/colegios', headers=auth(super_token))
    assert r_test.status_code == 423, f"esperaba 423, obtuvo {r_test.status_code}: {r_test.text}"
    
    # Cambiar password (como sería el primer login del admin real)
    nueva_super = 'NuevaPassword2024!'
    r = client.post('/api/auth/cambiar-password', json={
        'password_actual': super_pw_inicial,
        'password_nuevo': nueva_super,
    }, headers=auth(super_token))
    assert r.status_code == 200, f"cambiar-password superadmin: {r.text}"
    
    # Ahora sí podemos usar el sistema con esa cuenta
    r_test2 = client.get('/api/superadmin/colegios', headers=auth(super_token))
    assert r_test2.status_code == 200, f"esperaba 200, obtuvo {r_test2.status_code}: {r_test2.text}"
    
    # 2. CREAR COLEGIO sin admin_password (forzar generación automática + must_change)
    r = client.post('/api/superadmin/colegios', json={
        'nombre':'Liceo Pruebas','codigo':'pruebas','plan':'enterprise',
        'admin_username':'director',
        'admin_nombre':'Dir','admin_apellido':'Test',
    }, headers=auth(super_token))
    assert r.status_code in (200,201), r.text
    body = r.json()
    assert body.get('must_change_password') is True, f"esperaba must_change True: {body}"
    pw_dir_inicial = body['admin_password']
    
    # Login con la password generada
    r = client.post('/api/auth/login', json={'username':'director','password': pw_dir_inicial})
    assert r.status_code == 200, r.text
    dir_token = r.json()['token']
    
    # Como tiene must_change_password, debe rechazar otros endpoints
    r_test = client.get('/api/cursos', headers=auth(dir_token))
    assert r_test.status_code == 423, f"esperaba 423: {r_test.status_code}"
    
    # Cambiar password
    nueva_dir = 'DirectorNueva2024!'
    r = client.post('/api/auth/cambiar-password', json={
        'password_actual': pw_dir_inicial,
        'password_nuevo': nueva_dir,
    }, headers=auth(dir_token))
    assert r.status_code == 200, f"cambiar-password director: {r.text}"
    
    # Ahora puede operar
    ok("setup superadmin + colegio + director con flujo de seguridad OK")
    
    # 3. ESTADO INICIAL
    step(3, "Estado inicial creado por /api/superadmin/colegios")
    db = SessionLocal()
    director = db.query(Usuario).filter_by(username='director').first()
    cid = director.colegio_id
    ano = db.query(AnoEscolar).filter_by(colegio_id=cid).first()
    info(f"colegio_id={cid}, año='{ano.nombre}' activo={ano.activo} fechas={ano.fecha_inicio}→{ano.fecha_fin}")
    grado1ro = db.query(Grado).filter_by(colegio_id=cid).order_by(Grado.orden).first()
    info(f"grado1ro: ID={grado1ro.id} '{grado1ro.nombre}' nivel='{grado1ro.nivel}'")
    tanda = db.query(Tanda).filter_by(colegio_id=cid).first()
    info(f"tanda: ID={tanda.id} '{tanda.nombre}'")
    grado1_id, tanda_id = grado1ro.id, tanda.id
    db.close()
    
    # 4. CURSO
    step(4, "Crear curso")
    r = client.post('/api/cursos', json={
        'grado_id':grado1_id,'tanda_id':tanda_id,'nombre':'A','seccion':'A',
    }, headers=auth(dir_token))
    info(f"  status={r.status_code} body={r.text[:300]}")
    if r.status_code not in (200,201):
        err("no se pudo crear curso, abortando")
        sys.exit(1)
    curso_id = r.json().get('id')
    ok(f"curso_id={curso_id}")
    
    # 5. ASIGNATURAS
    step(5, "Crear asignaturas")
    asig_ids = {}
    for nombre in ['Lengua Española','Matemática','Ciencias Sociales','Ciencias de la Naturaleza',
                   'Lenguas Extranjeras - Inglés','Lenguas Extranjeras - Francés',
                   'Educación Física','Educación Artística','Formación Integral Humana y Religiosa']:
        r = client.post('/api/asignaturas', json={'nombre':nombre,'codigo':nombre[:5]}, headers=auth(dir_token))
        if r.status_code in (200,201):
            asig_ids[nombre] = r.json().get('id')
        else:
            warn(f"'{nombre}' NO creada: {r.status_code} - {r.text[:120]}")
    ok(f"{len(asig_ids)} asignaturas creadas")
    info(f"IDs: {asig_ids}")
    
    if 'Lengua Española' not in asig_ids:
        err("Lengua Española no se creó")
        sys.exit(1)
    lengua_id = asig_ids['Lengua Española']
    
    # 6. PROFESOR
    step(6, "Crear profesor")
    r = client.post('/api/usuarios', json={
        'username':'profe','password':'profesor123','nombre':'Ana','apellido':'P',
        'email':'a@x.com','role':'profesor',
    }, headers=auth(dir_token))
    info(f"  status={r.status_code} body={r.text[:200]}")
    if r.status_code not in (200,201):
        err("no se pudo crear profesor")
        sys.exit(1)
    prof_id = r.json().get('id')
    ok(f"prof_id={prof_id}")
    
    # 7. ASIGNACIONES
    step(7, "Asignaciones del profesor")
    for nombre, aid in asig_ids.items():
        r = client.post('/api/asignaciones', json={
            'profesor_id':prof_id,'curso_id':curso_id,'asignatura_id':aid,
            'es_titular': nombre == 'Lengua Española',
        }, headers=auth(dir_token))
        if r.status_code not in (200,201):
            warn(f"asignación '{nombre}': {r.status_code} - {r.text[:100]}")
    ok("asignaciones OK")
    
    # 8. ESTUDIANTES
    step(8, "20 estudiantes")
    est_ids = []
    for i in range(1, 21):
        r = client.post('/api/estudiantes', json={
            'nombre':f'Est{i:02d}','apellido':'Demo',
            'sexo':'F' if i%2 else 'M','fecha_nacimiento':'2010-05-15',
            'curso_id':curso_id,'no_lista':i,'matricula':f'M{i:03d}',
        }, headers=auth(dir_token))
        if r.status_code in (200,201):
            est_ids.append(r.json().get('id'))
    ok(f"{len(est_ids)} estudiantes")
    
    # 9. HORARIOS
    step(9, "Horarios Lengua Española (lun, mar, mier)")
    for d in ['lunes','martes','miercoles']:
        r = client.post('/api/horarios', json={
            'curso_id':curso_id,'asignatura_id':lengua_id,'profesor_id':prof_id,
            'dia':d,'hora_inicio':'07:00','hora_fin':'07:45','tipo_bloque':'clase',
        }, headers=auth(dir_token))
        info(f"  {d}: {r.status_code}")
    
    # 10. LOGIN PROFESOR
    r = client.post('/api/auth/login', json={'username':'profe','password':'profesor123'})
    prof_token = r.json()['token']
    
    # 11. CALIFICAR — REPLICANDO ESCENARIO REAL DEL USUARIO
    step(11, "Calificar 10 estudiantes en Lengua Española (POST /api/calificaciones)")
    info("Escenario realista: usuario solo metió 2 parciales del P1 (lo común a mitad de período)")
    califs_creadas = 0
    for eid in est_ids[:10]:
        r = client.post('/api/calificaciones', json={
            'estudiante_id': eid, 'asignatura_id': lengua_id,
            'p1_p1': 80, 'p1_p2': 75,
        }, headers=auth(prof_token))
        if r.status_code in (200,201):
            califs_creadas += 1
        else:
            warn(f"  est {eid}: {r.status_code} - {r.text[:200]}")
    ok(f"{califs_creadas} calificaciones POST")
    
    # 12. ASISTENCIA
    step(12, "Registrar asistencia")
    asist_creadas = 0
    for eid in est_ids[:10]:
        for fecha in ['2024-09-02','2024-09-03','2024-09-04']:
            r = client.post('/api/asistencia', json={
                'estudiante_id': eid, 'asignatura_id': lengua_id,
                'fecha': fecha, 'estado': 'presente',
            }, headers=auth(prof_token))
            if r.status_code in (200,201):
                asist_creadas += 1
            else:
                warn(f"  est={eid} f={fecha}: {r.status_code} - {r.text[:120]}")
    ok(f"{asist_creadas} asistencias POST")
    
    # 13. INSPECCIÓN BD
    step(13, "INSPECCIÓN BD post-POST")
    db = SessionLocal()
    califs = db.query(Calificacion).filter(
        Calificacion.estudiante_id.in_(est_ids[:10]),
        Calificacion.asignatura_id == lengua_id,
    ).all()
    info(f"Calificaciones BD: {len(califs)}")
    if califs:
        c = califs[0]
        info(f"  est={c.estudiante_id}, p1_p1={c.p1_p1}, p1_p2={c.p1_p2}, p1_p3={c.p1_p3}, p1_p4={c.p1_p4}")
        info(f"  pc1_persistido={c.pc1}, calcular_pc(1)={c.calcular_pc(1)}")
    
    asists = db.query(Asistencia).filter(Asistencia.estudiante_id.in_(est_ids[:10])).all()
    null_asig = sum(1 for a in asists if a.asignatura_id is None)
    info(f"Asistencias BD: {len(asists)} (NULL asignatura_id: {null_asig})")
    if asists:
        a = asists[0]
        info(f"  ejemplo: est={a.estudiante_id} asig={a.asignatura_id} curso={a.curso_id} fecha={a.fecha} estado='{a.estado}'")
    db.close()
    
    # 14. PREVIEW PDF (lo que la UI llama)
    step(14, "Generar preview-pdf (endpoint real de la UI)")
    sys.stdout.flush()
    r = client.get(f'/api/registros/secundaria/{curso_id}/preview-pdf', headers=auth(dir_token))
    info(f"status={r.status_code} bytes={len(r.content)}")
    sys.stdout.flush()
    if r.status_code != 200:
        err(f"falló: {r.text[:400]}")
    else:
        with open('/tmp/preview.pdf','wb') as f: f.write(r.content)
        ok("PDF generado")
    
    # 15. ¿QUÉ RECIBE EL RENDER?
    step(15, "Datos efectivos que llegan al render")
    sys.stdout.flush()
    db = SessionLocal()
    from app import _cargar_datos_asignaturas_secundaria
    estudiantes_db = db.query(Estudiante).filter_by(curso_id=curso_id, activo=True).order_by(Estudiante.no_lista).all()
    director2 = db.query(Usuario).filter_by(username='director').first()
    print(f"    [DEBUG] director2={director2}, estudiantes_db={len(estudiantes_db)}")
    sys.stdout.flush()
    
    asig_data = _cargar_datos_asignaturas_secundaria(db, director2, curso_id, 1, estudiantes_db)
    print(f"    [DEBUG] asig_data keys: {list(asig_data.keys())}")
    sys.stdout.flush()
    
    for nombre, data in asig_data.items():
        cdict = data['calificaciones']
        no_vacio = sum(1 for c in cdict.values() if any(v is not None for v in c.values()))
        matriz = data.get('asistencia_matriz', [])
        adir = data.get('asistencias', {})
        no_vacio_adir = sum(1 for a in adir.values() if a)
        
        marker = ""
        if nombre == 'Lengua Española':
            marker = "  <-- BUG REPORTADO"
        
        print(f"\n  '{nombre}':{marker}")
        print(f"    calificaciones: {len(cdict)} en dict, {no_vacio} con valores no-None")
        print(f"    asist_raw: {len(adir)} con marcas no vacías: {no_vacio_adir}")
        print(f"    asistencia_matriz: {len(matriz)} meses")
        sys.stdout.flush()
        
        if nombre == 'Lengua Española':
            print(f"    DETALLE:")
            for idx, c in sorted(cdict.items())[:5]:
                en = estudiantes_db[idx].nombre_completo if idx < len(estudiantes_db) else "?"
                print(f"      idx={idx} {en}: {c}")
            if matriz:
                for m_idx, m in enumerate(matriz[:3]):
                    print(f"    matriz[{m_idx}]: '{m.get('mes')}' días={m.get('total_dias')} fuente={m.get('fuente_dias')} dias_lista={m.get('dias',[])[:10]}")
                    if m.get('filas'):
                        f0 = m['filas'][0]
                        print(f"      fila[0]: presentes={f0.get('presentes')} valores={f0.get('valores',[])[:10]}")
            else:
                print(f"    !!! matriz_asistencia VACÍA — bug")
            sys.stdout.flush()
    db.close()

print(f"\n{BOLD}=== fin ==={RESET}\n")
