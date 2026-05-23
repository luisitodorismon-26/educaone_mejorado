"""
test_registro_completo.py
=========================
Test E2E que crea un colegio completo con datos reales y prueba todo el
flujo del Registro Escolar MINERD: estudiantes, asistencia, calificaciones,
y generación de PDF (vista previa + oficial).

Uso:
    cd backend
    python tools/test_registro_completo.py
    
    # Para escenarios específicos:
    python tools/test_registro_completo.py --escenario completo
    python tools/test_registro_completo.py --escenario parcial
    python tools/test_registro_completo.py --escenario vacio

Salida:
    backend/artifacts/test_registro/
        ├── registro_oficial_completo.pdf       (si pasó validación)
        ├── borrador_completo.pdf               (con marca de agua)
        ├── borrador_parcial.pdf                (datos parciales, marca BORRADOR)
        ├── pag1_portada.png                    (render de página clave)
        ├── pag8_centro.png
        ├── pag17_asistencia.png
        ├── pag131_calif_izq.png
        ├── pag132_calif_der.png
        └── reporte.json                        (resumen de validaciones)
"""

import sys
import os
import json
import argparse
import random
from datetime import date, timedelta
from pathlib import Path

# CRÍTICO: setear DATABASE_URL ANTES de cualquier import que use database.py
if os.environ.get('USE_TMP_DB') == '1':
    os.environ['DATABASE_URL'] = 'sqlite:////tmp/sge_test.db'
    DB_PATH = Path('/tmp/sge_test.db')
    OUT_DIR = Path('/tmp/test_registro')
else:
    DB_PATH = Path(__file__).parent.parent / 'sge.db'
    OUT_DIR = Path(__file__).parent.parent / 'artifacts' / 'test_registro'

# Directorio base del backend (parent de tools/)
BASE_DIR = str(Path(__file__).parent.parent)

# Limpiar DB previa antes de importar app
if DB_PATH.exists():
    DB_PATH.unlink()

# Limpiar INITIAL_CREDENTIALS.txt previo si existe (pruebas idempotentes)
_init_creds_file = Path(BASE_DIR) / 'INITIAL_CREDENTIALS.txt'
if _init_creds_file.exists():
    _init_creds_file.unlink()

# Agregar parent dir al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))
os.chdir(str(Path(__file__).parent.parent))

# Inicializar via lifespan
from fastapi.testclient import TestClient
from app import app

# Output directory
OUT_DIR.mkdir(parents=True, exist_ok=True)
# Limpiar archivos previos
for f in OUT_DIR.glob('*'):
    if f.is_file():
        f.unlink()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def color(txt, c='cyan'):
    """Color simple para terminal"""
    codes = {'cyan': 36, 'green': 32, 'red': 31, 'yellow': 33, 'gray': 90}
    return f"\033[{codes.get(c, 0)}m{txt}\033[0m"

def ok(msg):
    print(f"  {color('✓', 'green')} {msg}")

def warn(msg):
    print(f"  {color('⚠', 'yellow')} {msg}")

def fail(msg):
    print(f"  {color('✗', 'red')} {msg}")

def step(msg):
    print(f"\n{color('▶', 'cyan')} {msg}")


# ─────────────────────────────────────────────────────────────────────────────
# Escenarios
# ─────────────────────────────────────────────────────────────────────────────

ESCENARIOS = {
    'completo': {
        'descripcion': '20 estudiantes, todas las calificaciones (4 parciales por período), asistencia completa',
        'num_estudiantes': 20,
        'parciales_por_periodo': 4,  # P1, P2, P3, P4 todos
        'periodos_completos': [1, 2, 3, 4],  # Los 4 períodos llenos
        'dias_asistencia': 15,
    },
    'parcial': {
        'descripcion': '10 estudiantes, solo 2 parciales del P1 (para probar fallback de PC)',
        'num_estudiantes': 10,
        'parciales_por_periodo': 2,  # Solo P1, P2
        'periodos_completos': [1],  # Solo período 1
        'dias_asistencia': 5,
    },
    'vacio': {
        'descripcion': '5 estudiantes sin calificaciones ni asistencia (debe bloquear oficial)',
        'num_estudiantes': 5,
        'parciales_por_periodo': 0,
        'periodos_completos': [],
        'dias_asistencia': 0,
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Test runner
# ─────────────────────────────────────────────────────────────────────────────

def correr_test(escenario_nombre: str = 'completo'):
    cfg = ESCENARIOS[escenario_nombre]
    print(f"\n{color('═' * 72, 'cyan')}")
    print(f"{color(f'  TEST E2E — Escenario: {escenario_nombre.upper()}', 'cyan')}")
    print(f"{color('  ' + cfg['descripcion'], 'gray')}")
    print(f"{color('═' * 72, 'cyan')}\n")

    reporte = {'escenario': escenario_nombre, 'config': cfg, 'resultados': {}}
    
    with TestClient(app) as client:
        # ─── 1. Login superadmin y crear colegio ──────────────────────────
        step("1. Setup: superadmin → colegio → admin → login")
        
        # NUEVO (Sprint 1 seguridad): superadmin se crea con password aleatoria
        # en INITIAL_CREDENTIALS.txt al primer arranque. Tras login, está
        # forzado a cambiar password antes de poder operar.
        import re as _re
        cred_path = os.path.join(BASE_DIR, 'INITIAL_CREDENTIALS.txt')
        super_pw = 'superadmin123'  # fallback para BDs viejas
        if os.path.exists(cred_path):
            with open(cred_path) as f:
                txt = f.read()
            m = _re.search(r'Usuario:\s+superadmin\s*\n\s+Contraseña:\s+(\S+)', txt)
            if m:
                super_pw = m.group(1)
        
        sa_token = client.post('/api/auth/login', json={
            'username': 'superadmin', 'password': super_pw
        }).json()['token']
        ok(f"Superadmin logueado")
        
        # Si tiene must_change, cambiar password (lo necesario para poder operar)
        h_sa = {'Authorization': f'Bearer {sa_token}'}
        test_resp = client.get('/api/superadmin/colegios', headers=h_sa)
        if test_resp.status_code == 423:
            client.post('/api/auth/cambiar-password', headers=h_sa, json={
                'password_actual': super_pw,
                'password_nuevo': 'TestSuper123Pass',
            })
        
        client.post('/api/superadmin/colegios',
            headers={'Authorization': f'Bearer {sa_token}'},
            json={
                'nombre': f'Colegio Test {escenario_nombre}',
                'codigo': f'test_{escenario_nombre}',
                'admin_username': 'director',
                'admin_password': 'TestAdmin123Pass',
            })
        ok("Colegio creado")
        
        dir_token = client.post('/api/auth/login', json={
            'username': 'director', 'password': 'TestAdmin123Pass'
        }).json()['token']
        h_dir = {'Authorization': f'Bearer {dir_token}'}
        # admin_password fue provista, así que NO requiere cambio
        ok("Director logueado")
        
        # ─── 2. Configurar centro ─────────────────────────────────────────
        step("2. Configurar centro educativo")
        client.put('/api/configuracion/colegio', headers=h_dir, json={
            'nombre': 'Colegio Demo MINERD',
            'codigo_centro': 'DEM-1503',
            'codigo_cartografia': 'CART-001',
            'regional': '15',
            'distrito': '03',
            'direccion': 'Santo Domingo, RD',
            'telefono': '809-555-1000',
            'email': 'demo@educaone.test',
            'nombre_director': 'Directora Demo',
            'sector': 'privado',
            'zona': 'urbana',
            'tanda_operacion': 'matutina',
        })
        ok("Centro configurado: sector=privado, zona=urbana, jornada=matutina")
        
        # ─── 3. Año escolar ──────────────────────────────────────────────
        step("3. Crear año escolar 2024-2025 y abrir P1")
        ano = client.post('/api/ano-escolar', headers=h_dir, json={
            'nombre': '2024-2025',
            'fecha_inicio': '2024-08-19',
            'fecha_fin': '2025-06-30',
        }).json()
        ano_id = ano['id']
        client.put(f'/api/ano-escolar/{ano_id}/activar', headers=h_dir)
        # Abrir todos los períodos para que el profesor pueda calificar
        client.put(f'/api/ano-escolar/{ano_id}', headers=h_dir, json={
            'p1_cerrado': False, 'p2_cerrado': False,
            'p3_cerrado': False, 'p4_cerrado': False,
        })
        ok("Año escolar 2024-2025 activo, períodos abiertos")
        
        # ─── 4. Grados, tandas, cursos ──────────────────────────────────
        step("4. Crear grados, tandas y curso")
        grado = client.post('/api/grados', headers=h_dir, json={
            'nombre': '1ro de Secundaria',
            'nivel': 'secundaria',
            'orden': 1,
        }).json()
        grado_id = grado['id']
        ok(f"Grado creado: 1ro de Secundaria")
        
        tanda = client.post('/api/tandas', headers=h_dir, json={
            'nombre': 'Matutina',
        }).json()
        tanda_id = tanda['id']
        ok("Tanda Matutina creada")
        
        curso = client.post('/api/cursos', headers=h_dir, json={
            'nombre': 'A',
            'grado_id': grado_id,
            'tanda_id': tanda_id,
        }).json()
        curso_id = curso['id']
        ok(f"Curso A del 1ro creado (ID={curso_id})")
        
        # ─── 5. Asignaturas ──────────────────────────────────────────────
        step("5. Crear asignaturas del primer ciclo de secundaria")
        asignaturas_data = [
            ('Lengua Española', 'LE'),
            ('Matemática', 'MAT'),
            ('Ciencias Sociales', 'CS'),
            ('Ciencias de la Naturaleza', 'CN'),
            ('Inglés', 'ING'),
            ('Francés', 'FR'),
            ('Educación Física', 'EF'),
            ('Educación Artística', 'EA'),
            ('Formación Integral Humana y Religiosa', 'FIHR'),
        ]
        asignatura_ids = []
        for nombre, codigo in asignaturas_data:
            res = client.post('/api/asignaturas', headers=h_dir, json={
                'nombre': nombre,
                'codigo': codigo,
                'grado_id': grado_id,
            })
            if res.status_code == 200 or res.status_code == 201:
                asignatura_ids.append((nombre, res.json()['id']))
        ok(f"{len(asignatura_ids)} asignaturas creadas")
        
        # ─── 6. Profesores ───────────────────────────────────────────────
        step("6. Crear profesor titular y asignar a todas las asignaturas")
        profesor_resp = client.post('/api/usuarios', headers=h_dir, json={
            'username': 'profesor1',
            'password': 'profesor123',
            'nombre': 'Ana',
            'apellido': 'Secundaria',
            'role': 'profesor',
            'email': 'profesor1@demo.test',
        })
        if profesor_resp.status_code not in (200, 201):
            fail(f"Error creando profesor: {profesor_resp.status_code} {profesor_resp.text[:200]}")
            return
        profesor = profesor_resp.json()
        profesor_id = profesor.get('id') or profesor.get('usuario', {}).get('id')
        ok(f"Profesor 'Ana Secundaria' creado (ID={profesor_id})")
        
        # Asignar profesor a todas las materias del curso
        for nombre, asig_id in asignatura_ids:
            res = client.post('/api/asignaciones', headers=h_dir, json={
                'profesor_id': profesor_id,
                'curso_id': curso_id,
                'asignatura_id': asig_id,
            })
        # Marcar como titular en una de ellas (la primera)
        # Buscar la asignación creada y marcarla titular
        from database import SessionLocal
        from models import AsignacionProfesor
        with SessionLocal() as db:
            asignacion_titular = db.query(AsignacionProfesor).filter_by(
                profesor_id=profesor_id, curso_id=curso_id
            ).first()
            if asignacion_titular:
                asignacion_titular.es_titular = True
                db.commit()
                ok(f"Profesor titular marcado en asignación ID={asignacion_titular.id}")
        
        # ─── 7. Estudiantes ──────────────────────────────────────────────
        step(f"7. Crear {cfg['num_estudiantes']} estudiantes")
        estudiante_ids = []
        for i in range(cfg['num_estudiantes']):
            sexo = 'F' if i % 2 == 0 else 'M'
            est = client.post('/api/estudiantes', headers=h_dir, json={
                'nombre': f'Est{i+1:02d}',
                'apellido': 'Demo',
                'sexo': sexo,
                'no_lista': i + 1,
                'curso_id': curso_id,
                'fecha_nacimiento': f'2010-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}',
                'matricula': f'MAT{1000 + i}',
                'direccion': 'Santo Domingo',
            }).json()
            estudiante_ids.append(est['id'])
        ok(f"{len(estudiante_ids)} estudiantes creados")
        
        # ─── 7b. Horarios para cada asignatura (validador los exige) ────
        step("7b. Crear horarios para cada asignatura del curso")
        dias_semana = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes']
        horarios_count = 0
        for idx, (nombre, asig_id) in enumerate(asignatura_ids):
            # Cada asignatura en un día/hora distinto para evitar solapamientos
            dia = dias_semana[idx % 5]
            hora_inicio = f"{8 + (idx // 5):02d}:00"
            hora_fin = f"{9 + (idx // 5):02d}:00"
            res = client.post('/api/horarios', headers=h_dir, json={
                'profesor_id': profesor_id,
                'curso_id': curso_id,
                'asignatura_id': asig_id,
                'dia': dia,
                'hora_inicio': hora_inicio,
                'hora_fin': hora_fin,
                'tipo_bloque': 'clase',
            })
            if res.status_code in (200, 201):
                horarios_count += 1
            else:
                warn(f"Horario {nombre}: {res.status_code} {res.text[:100]}")
        ok(f"{horarios_count} horarios creados")
        
        # ─── 8. Login profesor para registrar calificaciones y asistencia ─
        step("8. Login profesor")
        prof_token = client.post('/api/auth/login', json={
            'username': 'profesor1', 'password': 'profesor123'
        }).json()['token']
        h_prof = {'Authorization': f'Bearer {prof_token}'}
        ok("Profesor logueado")
        
        # ─── 9. Calificaciones ───────────────────────────────────────────
        if cfg['parciales_por_periodo'] > 0:
            step(f"9. Cargar calificaciones (períodos: {cfg['periodos_completos']}, parciales: {cfg['parciales_por_periodo']})")
            calif_count = 0
            for nombre_asig, asig_id in asignatura_ids:
                for est_idx, est_id in enumerate(estudiante_ids):
                    payload = {
                        'estudiante_id': est_id,
                        'asignatura_id': asig_id,
                    }
                    # Llenar parciales según escenario
                    for periodo in cfg['periodos_completos']:
                        payload['periodo'] = periodo
                        # Notas variadas pero realistas (70-95)
                        base = 70 + (est_idx % 25)
                        for p in range(1, cfg['parciales_por_periodo'] + 1):
                            payload[f'p{periodo}_p{p}'] = min(95, base + p)
                    
                    res = client.post('/api/calificaciones', headers=h_prof, json=payload)
                    if res.status_code == 200:
                        calif_count += 1
                    elif res.status_code != 403:  # 403 = período cerrado, ignorar
                        warn(f"Calif {nombre_asig} est{est_idx+1}: {res.status_code} {res.text[:80]}")
            ok(f"{calif_count} registros de calificación creados")
        else:
            warn("Escenario sin calificaciones (esperado para 'vacio')")
        
        # ─── 10. Asistencia ──────────────────────────────────────────────
        if cfg['dias_asistencia'] > 0:
            step(f"10. Registrar asistencia ({cfg['dias_asistencia']} días por estudiante por asignatura)")
            asist_count = 0
            fecha_inicio = date(2024, 8, 19)  # Inicio año escolar
            for nombre_asig, asig_id in asignatura_ids[:4]:  # Solo 4 primeras para no saturar
                for est_id in estudiante_ids:
                    for d in range(cfg['dias_asistencia']):
                        fecha = fecha_inicio + timedelta(days=d * 7)  # Cada semana
                        # 90% presente, 10% ausente
                        estado = 'presente' if random.random() > 0.1 else 'ausente'
                        res = client.post('/api/asistencia', headers=h_prof, json={
                            'estudiante_id': est_id,
                            'asignatura_id': asig_id,
                            'fecha': fecha.isoformat(),
                            'estado': estado,
                        })
                        if res.status_code == 200:
                            asist_count += 1
            ok(f"{asist_count} registros de asistencia creados")
        else:
            warn("Escenario sin asistencia (esperado para 'vacio')")
        
        # ─── 11. Días trabajados del año ────────────────────────────────
        step("11. Configurar días trabajados del año escolar")
        # Generar lista de días: lunes a viernes desde inicio
        dias_trabajados = {}
        meses_es = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
                    'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
        d = date(2024, 8, 19)
        end = date(2025, 6, 30)
        while d <= end:
            if d.weekday() < 5:  # lunes-viernes
                mes = meses_es[d.month - 1]
                dias_trabajados.setdefault(mes, []).append(d.day)
            d += timedelta(days=1)
        
        # Asegurar que se guarden bien (algunas implementaciones esperan campo distinto)
        with SessionLocal() as db:
            from models import AnoEscolar
            ano_obj = db.query(AnoEscolar).filter_by(id=ano_id).first()
            if ano_obj:
                ano_obj.set_dias_trabajados(dias_trabajados)
                db.commit()
                ok(f"Días trabajados configurados: {sum(len(v) for v in dias_trabajados.values())} días totales")
        
        # ─── 12. PROBAR ENDPOINTS DE REGISTRO ────────────────────────────
        step("12. Probar endpoints de Registro Escolar")
        
        # 12a. Validación
        res_val = client.get(f'/api/registros/validar/{curso_id}', headers=h_dir)
        if res_val.status_code == 200:
            val = res_val.json()
            valido = val.get('valid', False)
            errors = val.get('errors', [])
            warnings = val.get('warnings', [])
            if valido:
                ok(f"Validación: VÁLIDA ({len(warnings)} warnings)")
            else:
                warn(f"Validación: INVÁLIDA ({len(errors)} errores, {len(warnings)} warnings)")
                for e in errors[:5]:
                    print(f"      ↳ {color(e[:120], 'red')}")
                for w in warnings[:3]:
                    print(f"      ↳ {color(w[:120], 'yellow')}")
            reporte['resultados']['validacion'] = val
        else:
            fail(f"Endpoint validar falló: {res_val.status_code}")
        
        # 12b. Vista previa (debe funcionar SIEMPRE)
        res_prev = client.get(
            f'/api/registros/secundaria/{curso_id}/preview-pdf', headers=h_dir
        )
        if res_prev.status_code == 200 and res_prev.headers.get('content-type', '').startswith('application/pdf'):
            out_path = OUT_DIR / f'borrador_{escenario_nombre}.pdf'
            out_path.write_bytes(res_prev.content)
            ok(f"Vista Previa BORRADOR generada: {out_path.name} ({len(res_prev.content):,} bytes)")
            reporte['resultados']['preview_pdf'] = {'ok': True, 'bytes': len(res_prev.content)}
        else:
            fail(f"Preview falló: {res_prev.status_code} {res_prev.text[:200]}")
            reporte['resultados']['preview_pdf'] = {'ok': False, 'status': res_prev.status_code}
        
        # 12c. Registro oficial
        res_ofi = client.get(f'/api/registros/secundaria/{curso_id}', headers=h_dir)
        if res_ofi.status_code == 200 and res_ofi.headers.get('content-type', '').startswith('application/pdf'):
            out_path = OUT_DIR / f'oficial_{escenario_nombre}.pdf'
            out_path.write_bytes(res_ofi.content)
            ok(f"Registro OFICIAL generado: {out_path.name} ({len(res_ofi.content):,} bytes)")
            reporte['resultados']['oficial_pdf'] = {'ok': True, 'bytes': len(res_ofi.content)}
        elif res_ofi.status_code == 400:
            warn(f"Oficial bloqueado (esperado si datos incompletos): 400")
            try:
                detalle = res_ofi.json().get('detalle', [])
                for d in detalle[:3]:
                    print(f"      ↳ {color(d[:100], 'yellow')}")
                reporte['resultados']['oficial_pdf'] = {'ok': False, 'status': 400, 'errores': detalle[:5]}
            except:
                pass
        elif res_ofi.status_code == 409:
            warn(f"Oficial: warnings detectados (409). Reintentando con ?force=true")
            res_ofi2 = client.get(f'/api/registros/secundaria/{curso_id}?force=true', headers=h_dir)
            if res_ofi2.status_code == 200:
                out_path = OUT_DIR / f'oficial_{escenario_nombre}_forzado.pdf'
                out_path.write_bytes(res_ofi2.content)
                ok(f"Oficial generado con force=true: {out_path.name}")
                reporte['resultados']['oficial_pdf'] = {'ok': True, 'forzado': True, 'bytes': len(res_ofi2.content)}
        else:
            fail(f"Oficial falló: {res_ofi.status_code} {res_ofi.text[:200]}")
        
        # ─── 13. Renderizar páginas clave ────────────────────────────────
        if os.environ.get('SKIP_RENDER') == '1':
            warn("13. Render visual saltado (SKIP_RENDER=1)")
        else:
            step("13. Renderizar páginas clave para inspección visual")
            try:
                from pdf2image import convert_from_path
                
                # Usar el PDF que tengamos disponible
                pdf_to_render = OUT_DIR / f'oficial_{escenario_nombre}.pdf'
                if not pdf_to_render.exists():
                    pdf_to_render = OUT_DIR / f'oficial_{escenario_nombre}_forzado.pdf'
                if not pdf_to_render.exists():
                    pdf_to_render = OUT_DIR / f'borrador_{escenario_nombre}.pdf'
                
                if pdf_to_render.exists():
                    paginas_clave = {
                        1: 'pag1_portada',
                        8: 'pag8_centro_educativo',
                        17: 'pag17_asistencia_lengua',
                        131: 'pag131_calif_lengua_izq',
                        132: 'pag132_calif_lengua_der',
                    }
                    for pg, nombre in paginas_clave.items():
                        try:
                            imgs = convert_from_path(
                                str(pdf_to_render), dpi=110,
                                first_page=pg, last_page=pg
                            )
                            if imgs:
                                out_img = OUT_DIR / f'{nombre}_{escenario_nombre}.png'
                                imgs[0].save(out_img)
                                ok(f"Pag {pg}: {out_img.name}")
                        except Exception as e:
                            warn(f"Pag {pg} no pudo renderizarse: {e}")
                else:
                    warn("No hay PDF disponible para renderizar")
            except ImportError:
                warn("pdf2image no instalado, saltando render visual")
        
        # ─── 14. Reporte ─────────────────────────────────────────────────
        reporte_path = OUT_DIR / f'reporte_{escenario_nombre}.json'
        reporte_path.write_text(json.dumps(reporte, indent=2, default=str))
        ok(f"Reporte JSON guardado: {reporte_path.name}")
    
    print(f"\n{color('═' * 72, 'green')}")
    print(f"{color(f'  Test {escenario_nombre} completado', 'green')}")
    print(f"{color(f'  Salidas en: {OUT_DIR}/', 'green')}")
    print(f"{color('═' * 72, 'green')}\n")
    
    return reporte


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Test E2E del Registro Escolar MINERD')
    parser.add_argument(
        '--escenario',
        choices=['completo', 'parcial', 'vacio', 'todos'],
        default='completo',
        help='Escenario a probar'
    )
    args = parser.parse_args()
    
    if args.escenario == 'todos':
        for esc in ['vacio', 'parcial', 'completo']:
            # Resetear DB entre escenarios
            if DB_PATH.exists():
                DB_PATH.unlink()
            correr_test(esc)
    else:
        correr_test(args.escenario)
