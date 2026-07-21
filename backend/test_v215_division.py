# -*- coding: utf-8 -*-
"""
Suite de integración v2.15 — DIVISIÓN POR NIVEL + MULTITENANT
==============================================================
Ejecuta los endpoints REALES (FastAPI TestClient + SQLite) y verifica:

  1. Multitenant: un colegio jamás ve datos de otro.
  2. Lente de LECTURA: coordinador con división fija solo ve su nivel.
  3. El lente fijo NO se puede saltar con el header X-Nivel.
  4. Switch de dirección: X-Nivel filtra; valores inventados se ignoran.
  5. Candado de ESCRITURA (F2): coordinador no crea/edita en el otro nivel.
  6. Bug 11: profesor sin asignación no puede calificar (primaria y secundaria).
  7. Alertas: atender es idempotente y solo para dirección/coordinación.
  8. Guards: eval extra vacía bajo lente primaria; recuperaciones vacías bajo secundaria.
  9. Stats y gráficos respetan el lente (números por división).
 10. Cuadro de honor: primaria ENTRA y el lente lo filtra.

Correr:  pytest test_v215_division.py -v
"""
import os

DB_FILE = 'test_division.db'
if os.path.exists(DB_FILE):
    os.remove(DB_FILE)
os.environ['DATABASE_URL'] = f'sqlite:///{DB_FILE}'

import pytest
from fastapi.testclient import TestClient

import app as app_module
from database import SessionLocal
from models import (
    Colegio, ConfiguracionColegio, Usuario, Grado, Tanda, Curso, Estudiante,
    AnoEscolar, Asignatura, AsignacionProfesor, CalificacionPrimaria,
)

client = TestClient(app_module.app)

# ────────────────────────── SEED ──────────────────────────
TOKENS = {}


def _mk_user(db, username, role, colegio_id, nivel=None):
    u = Usuario(username=username, nombre=username.title(), apellido='Test',
                email=f'{username}@test.do', role=role, colegio_id=colegio_id,
                activo=True, nivel_asignado=nivel, must_change_password=False)
    u.set_password('clave123')
    db.add(u)
    return u


@pytest.fixture(scope='session', autouse=True)
def seed():
    # El create_all de la app vive en su evento de startup; aquí lo corremos
    # directo para el sqlite de prueba (BD fresca ya trae la columna nueva).
    from database import engine
    from models import Base
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    col_a = Colegio(nombre='Colegio A', codigo='TEST-A', activo=True)
    col_b = Colegio(nombre='Colegio B', codigo='TEST-B', activo=True)
    db.add_all([col_a, col_b]); db.flush()

    db.add_all([ConfiguracionColegio(colegio_id=col_a.id),
                ConfiguracionColegio(colegio_id=col_b.id)])

    ano_a = AnoEscolar(nombre='2025-2026', activo=True, colegio_id=col_a.id)
    ano_b = AnoEscolar(nombre='2025-2026', activo=True, colegio_id=col_b.id)
    db.add_all([ano_a, ano_b]); db.flush()

    tanda = Tanda(nombre='Matutina', colegio_id=col_a.id)
    db.add(tanda); db.flush()

    g_pri = Grado(nombre='1ro de Primaria', nivel='primaria', orden=1, colegio_id=col_a.id)
    g_sec = Grado(nombre='1ro de Secundaria', nivel='secundaria', orden=7, colegio_id=col_a.id)
    g_b = Grado(nombre='2do de Secundaria', nivel='secundaria', orden=8, colegio_id=col_b.id)
    db.add_all([g_pri, g_sec, g_b]); db.flush()

    c_pri = Curso(nombre='A', grado_id=g_pri.id, tanda_id=tanda.id, colegio_id=col_a.id, activo=True)
    c_sec = Curso(nombre='A', grado_id=g_sec.id, tanda_id=tanda.id, colegio_id=col_a.id, activo=True)
    c_b = Curso(nombre='B', grado_id=g_b.id, colegio_id=col_b.id, activo=True)
    db.add_all([c_pri, c_sec, c_b]); db.flush()

    e1 = Estudiante(nombre='Pedro', apellido='Primaria', curso_id=c_pri.id, colegio_id=col_a.id, activo=True)
    e2 = Estudiante(nombre='Paula', apellido='Primaria', curso_id=c_pri.id, colegio_id=col_a.id, activo=True)
    e3 = Estudiante(nombre='Saul', apellido='Secundaria', curso_id=c_sec.id, colegio_id=col_a.id, activo=True)
    e4 = Estudiante(nombre='Sara', apellido='Secundaria', curso_id=c_sec.id, colegio_id=col_a.id, activo=True)
    eb = Estudiante(nombre='Beto', apellido='ColegioB', curso_id=c_b.id, colegio_id=col_b.id, activo=True)
    db.add_all([e1, e2, e3, e4, eb]); db.flush()

    asig = Asignatura(nombre='Lengua Española', colegio_id=col_a.id, activo=True)
    db.add(asig); db.flush()

    _mk_user(db, 'dir_a', 'direccion', col_a.id)
    _mk_user(db, 'coord_pri', 'coordinador', col_a.id, nivel='primaria')
    _mk_user(db, 'coord_sec', 'coordinador', col_a.id, nivel='secundaria')
    _mk_user(db, 'profe_a', 'profesor', col_a.id)
    _mk_user(db, 'dir_b', 'direccion', col_b.id)

    # Calificaciones de primaria de Pedro: 3 competencias completas con 95
    # (para el cuadro de honor)
    for comp in (1, 2, 3):
        db.add(CalificacionPrimaria(
            estudiante_id=e1.id, asignatura_id=asig.id, competencia_numero=comp,
            final_competencia=95, colegio_id=col_a.id, ano_escolar_id=ano_a.id,
        ))

    db.commit()

    seed.ids = dict(
        col_a=col_a.id, col_b=col_b.id,
        c_pri=c_pri.id, c_sec=c_sec.id, c_b=c_b.id,
        e_pri=e1.id, e_sec=e3.id, asig=asig.id, ano_a=ano_a.id,
        profe_a=db.query(Usuario).filter_by(username='profe_a').first().id,
    )
    db.close()

    # Login de todos (una sola vez, para no rozar el rate limit)
    for u in ('dir_a', 'coord_pri', 'coord_sec', 'profe_a', 'dir_b'):
        r = client.post('/api/auth/login', json={'username': u, 'password': 'clave123'})
        assert r.status_code == 200, f'login {u} falló: {r.text}'
        TOKENS[u] = r.json()['access_token' if 'access_token' in r.json() else 'token']
    yield


def H(user, nivel=None):
    h = {'Authorization': f'Bearer {TOKENS[user]}'}
    if nivel:
        h['X-Nivel'] = nivel
    return h


def _ids(lista, campo='id'):
    return {x[campo] for x in lista}


# ────────────────────── 1. MULTITENANT ──────────────────────
def test_multitenant_cursos():
    a = client.get('/api/cursos', headers=H('dir_a')).json()
    b = client.get('/api/cursos', headers=H('dir_b')).json()
    assert _ids(a) == {seed.ids['c_pri'], seed.ids['c_sec']}
    assert _ids(b) == {seed.ids['c_b']}
    assert _ids(a).isdisjoint(_ids(b)), 'FUGA MULTITENANT en cursos'


def test_multitenant_estudiantes():
    a = client.get('/api/estudiantes', headers=H('dir_a')).json()
    b = client.get('/api/estudiantes', headers=H('dir_b')).json()
    la = a if isinstance(a, list) else a.get('estudiantes', a.get('data', []))
    lb = b if isinstance(b, list) else b.get('estudiantes', b.get('data', []))
    assert len(la) == 4 and len(lb) == 1
    assert _ids(la).isdisjoint(_ids(lb)), 'FUGA MULTITENANT en estudiantes'


# ─────────────── 2-3. LENTE FIJO DEL COORDINADOR ───────────────
def test_lente_fijo_coordinador_primaria():
    cursos = client.get('/api/cursos', headers=H('coord_pri')).json()
    assert _ids(cursos) == {seed.ids['c_pri']}, 'coordinador primaria ve cursos de secundaria'
    r = client.get('/api/estudiantes', headers=H('coord_pri')).json()
    lst = r if isinstance(r, list) else r.get('estudiantes', r.get('data', []))
    apellidos = {e['apellido'] for e in lst}
    assert apellidos == {'Primaria'}, f'coordinador primaria ve: {apellidos}'


def test_lente_fijo_no_se_salta_con_header():
    cursos = client.get('/api/cursos', headers=H('coord_pri', nivel='secundaria')).json()
    assert _ids(cursos) == {seed.ids['c_pri']}, 'el header X-Nivel se saltó el lente fijo!'


# ─────────────── 4. SWITCH DE DIRECCIÓN ───────────────
def test_switch_direccion_filtra():
    pri = client.get('/api/cursos', headers=H('dir_a', nivel='primaria')).json()
    sec = client.get('/api/cursos', headers=H('dir_a', nivel='secundaria')).json()
    todos = client.get('/api/cursos', headers=H('dir_a')).json()
    assert _ids(pri) == {seed.ids['c_pri']}
    assert _ids(sec) == {seed.ids['c_sec']}
    assert _ids(todos) == {seed.ids['c_pri'], seed.ids['c_sec']}


def test_switch_valor_inventado_se_ignora():
    r = client.get('/api/cursos', headers=H('dir_a', nivel='hackeo')).json()
    assert _ids(r) == {seed.ids['c_pri'], seed.ids['c_sec']}, 'un X-Nivel inventado alteró la respuesta'


# ─────────────── 5. CANDADO DE ESCRITURA (F2) ───────────────
def test_candado_coordinador_no_crea_en_otro_nivel():
    r = client.post('/api/estudiantes', headers=H('coord_pri'),
                    json={'nombre': 'Intruso', 'apellido': 'Test', 'curso_id': seed.ids['c_sec']})
    assert r.status_code == 403 and 'división' in r.json()['error'].lower()


def test_candado_coordinador_si_crea_en_su_nivel():
    r = client.post('/api/estudiantes', headers=H('coord_pri'),
                    json={'nombre': 'Legal', 'apellido': 'Primaria', 'curso_id': seed.ids['c_pri']})
    assert r.status_code in (200, 201), r.text


def test_candado_no_puede_mover_al_otro_nivel():
    r = client.put(f"/api/estudiantes/{seed.ids['e_pri']}", headers=H('coord_pri'),
                   json={'curso_id': seed.ids['c_sec']})
    assert r.status_code == 403


def test_candado_no_toca_estudiante_del_otro_nivel():
    r = client.put(f"/api/estudiantes/{seed.ids['e_sec']}", headers=H('coord_pri'),
                   json={'nombre': 'Hackeado'})
    assert r.status_code == 403


def test_direccion_exenta_del_candado():
    r = client.put(f"/api/estudiantes/{seed.ids['e_sec']}", headers=H('dir_a'),
                   json={'telefono_padre': '809-555-0000'})
    assert r.status_code == 200, r.text


def test_candado_asistencia():
    r = client.post('/api/asistencia', headers=H('coord_pri'),
                    json={'estudiante_id': seed.ids['e_sec'], 'estado': 'presente'})
    assert r.status_code == 403


def test_candado_reporte_conducta():
    r = client.post('/api/reportes', headers=H('coord_pri'),
                    json={'estudiante_id': seed.ids['e_sec'], 'motivo': 'x', 'descripcion': 'x'})
    assert r.status_code == 403


# ─────────────── 6. BUG 11: ASIGNACIÓN OBLIGATORIA ───────────────
def test_profesor_sin_asignacion_no_califica_primaria():
    r = client.post('/api/calificaciones-primaria', headers=H('profe_a'),
                    json={'estudiante_id': seed.ids['e_pri'], 'asignatura_id': seed.ids['asig'],
                          'competencia_numero': 1, 'p1': 90})
    assert r.status_code == 403 and 'asignada' in r.json()['error']


def test_profesor_con_asignacion_pasa_el_candado():
    db = SessionLocal()
    db.add(AsignacionProfesor(profesor_id=seed.ids['profe_a'], curso_id=seed.ids['c_pri'],
                              asignatura_id=seed.ids['asig'], activo=True, es_titular=True,
                              colegio_id=seed.ids['col_a'], ano_escolar_id=seed.ids['ano_a']))
    db.commit(); db.close()
    r = client.post('/api/calificaciones-primaria', headers=H('profe_a'),
                    json={'estudiante_id': seed.ids['e_pri'], 'asignatura_id': seed.ids['asig'],
                          'competencia_numero': 1, 'p1': 90})
    assert r.status_code != 403, f'con asignación siguió bloqueado: {r.text}'


def test_profesor_sigue_sin_poder_calificar_secundaria():
    r = client.post('/api/calificaciones-secundaria', headers=H('profe_a'),
                    json={'estudiante_id': seed.ids['e_sec'], 'asignatura_id': seed.ids['asig'],
                          'competencia_numero': 1, 'p1': 90})
    assert r.status_code == 403


# ─────────────── 7. ALERTAS: ATENDER ───────────────
def test_atender_alerta_flujo():
    clave = 'inasistencia_semana:999:2026-W29'
    r = client.post('/api/dashboard/alertas/atender', headers=H('dir_a'),
                    json={'clave': clave, 'tipo': 'inasistencia_semana', 'nota': 'se llamó a la madre'})
    assert r.status_code == 200 and r.json()['ok']
    r2 = client.post('/api/dashboard/alertas/atender', headers=H('dir_a'),
                     json={'clave': clave, 'tipo': 'inasistencia_semana'})
    assert r2.json().get('ya_atendida') is True, 'atender no es idempotente'
    r3 = client.post('/api/dashboard/alertas/atender', headers=H('profe_a'),
                     json={'clave': 'x:1:1', 'tipo': 'x'})
    assert r3.status_code == 403, 'un profesor pudo atender alertas'


def test_alertas_lente_primaria_sin_tipos_secundaria():
    r = client.get('/api/dashboard/alertas', headers=H('dir_a', nivel='primaria'))
    tipos = {a['tipo'] for a in r.json()}
    assert 'evaluacion_extra_pendiente' not in tipos
    assert 'profesores_atrasados_secundaria' not in tipos


# ─────────────── 8. GUARDS DE FLUJOS EXCLUSIVOS ───────────────
def test_eval_extra_vacia_bajo_lente_primaria():
    r = client.get('/api/calificaciones-secundaria/pendientes-evaluacion-extra',
                   headers=H('coord_pri'))
    assert r.json() == {'pendientes': [], 'total': 0}


def test_recuperaciones_vacias_bajo_lente_secundaria():
    r = client.get('/api/recuperaciones-primaria/pendientes', headers=H('coord_sec'))
    assert r.json()['pendientes'] == [] and r.json()['resueltas'] == []


# ─────────────── 9. STATS Y GRÁFICOS ───────────────
def test_stats_rol_por_division():
    todos = client.get('/api/dashboard/stats-rol', headers=H('dir_a')).json()
    pri = client.get('/api/dashboard/stats-rol', headers=H('dir_a', nivel='primaria')).json()
    sec = client.get('/api/dashboard/stats-rol', headers=H('dir_a', nivel='secundaria')).json()
    assert pri['cursos'] == 1 and sec['cursos'] == 1 and todos['cursos'] == 2
    assert pri['estudiantes'] + sec['estudiantes'] == todos['estudiantes']
    assert pri['estudiantes'] >= 2  # los 2 del seed + el creado en el test del candado


def test_graficos_por_division():
    pri = client.get('/api/dashboard/graficos', headers=H('dir_a', nivel='primaria')).json()
    cursos_en_tabla = {c['curso_id'] for c in pri.get('asistencia_hoy_por_curso', [])}
    assert cursos_en_tabla == {seed.ids['c_pri']}, 'la tabla de asistencia por curso mezcló niveles'


# ─────────────── 10. CUADRO DE HONOR ───────────────
def test_cuadro_honor_primaria_entra():
    r = client.get('/api/estadisticas/cuadro-honor', headers=H('dir_a')).json()
    nombres = {e['nombre'] for e in r['estudiantes']}
    assert any('Pedro' in n for n in nombres), 'primaria sigue fuera del cuadro de honor'


def test_cuadro_honor_respeta_lente():
    r = client.get('/api/estadisticas/cuadro-honor', headers=H('dir_a', nivel='secundaria')).json()
    nombres = {e['nombre'] for e in r['estudiantes']}
    assert not any('Pedro' in n for n in nombres), 'el lente secundaria mostró un estudiante de primaria'


# ─────────────── 11. PLANILLA DE CALIFICACIONES (v2.16) ───────────────
def _asegurar_asignacion_profe():
    db = SessionLocal()
    existe = db.query(AsignacionProfesor).filter_by(
        profesor_id=seed.ids['profe_a'], curso_id=seed.ids['c_pri'],
        asignatura_id=seed.ids['asig'], activo=True).first()
    if not existe:
        db.add(AsignacionProfesor(profesor_id=seed.ids['profe_a'], curso_id=seed.ids['c_pri'],
                                  asignatura_id=seed.ids['asig'], activo=True, es_titular=True,
                                  colegio_id=seed.ids['col_a'], ano_escolar_id=seed.ids['ano_a']))
        db.commit()
    db.close()


def test_planilla_profesor_con_asignacion():
    _asegurar_asignacion_profe()
    r = client.get(f"/api/imprimir/planilla-calificaciones/{seed.ids['c_pri']}/{seed.ids['asig']}",
                   headers=H('profe_a'))
    assert r.status_code == 200 and r.content[:4] == b'%PDF', r.text[:200]


def test_planilla_en_blanco_curso_sin_notas():
    # c_sec no tiene calificaciones → debe salir igual (planilla en blanco)
    r = client.get(f"/api/imprimir/planilla-calificaciones/{seed.ids['c_sec']}/{seed.ids['asig']}",
                   headers=H('dir_a'))
    assert r.status_code == 200 and r.content[:4] == b'%PDF'


def test_planilla_respeta_division():
    # coordinador de secundaria no puede imprimir un curso de primaria
    r = client.get(f"/api/imprimir/planilla-calificaciones/{seed.ids['c_pri']}/{seed.ids['asig']}",
                   headers=H('coord_sec'))
    assert r.status_code == 403


# ─────────────── 12. REGISTRO DE PRIMARIA (v2.17 F1) ───────────────
def test_registro_primaria_preview_pdf():
    """El endpoint BORRADOR genera el registro con el generador F1 real."""
    r = client.get(f"/api/registros/primaria/{seed.ids['c_pri']}/preview-pdf",
                   headers=H('dir_a'))
    assert r.status_code == 200, r.text[:300]
    assert r.content[:4] == b'%PDF'


def test_registro_primaria_rechaza_secundaria():
    r = client.get(f"/api/registros/primaria/{seed.ids['c_sec']}/preview-pdf",
                   headers=H('dir_a'))
    # curso de secundaria: el validador/grado debe rechazarlo (4xx), nunca 200
    assert r.status_code != 200
