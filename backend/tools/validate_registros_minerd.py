import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database import SessionLocal
from models import (
    AnoEscolar,
    AsignacionProfesor,
    Asignatura,
    Asistencia,
    Calificacion,
    CalificacionPrimaria,
    Colegio,
    ConfiguracionColegio,
    Curso,
    DiaNoLaborable,
    Estudiante,
    Grado,
    Horario,
    Tanda,
    Usuario,
)
from registro_asistencia import build_asistencia_registro
from registro_escolar import generar_registro_desde_sistema
from registro_primaria import generar_registro_primaria_desde_sistema
from registro_validator import validar_registro_primaria, validar_registro_secundaria


ARTIFACTS_DIR = ROOT / "artifacts" / "registro_minerd"


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def get_or_create(model, db, defaults=None, **filters):
    instance = db.query(model).filter_by(**filters).first()
    if instance:
        return instance
    params = dict(filters)
    params.update(defaults or {})
    instance = model(**params)
    db.add(instance)
    db.flush()
    return instance


def get_or_create_user(db, username: str, **defaults):
    instance = db.query(Usuario).filter_by(username=username).first()
    if instance:
        return instance
    password = defaults.pop("password", "Cambiar123")
    instance = Usuario(username=username, **defaults)
    instance.set_password(password)
    db.add(instance)
    db.flush()
    return instance


def month_key(month: int) -> str:
    return {
        1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
        7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic",
    }[month]


def school_days_between(start: date, end: date, allowed_day_names):
    day_map = {
        0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves",
        4: "Viernes", 5: "Sábado", 6: "Domingo",
    }
    current = start
    result = []
    while current <= end:
        if day_map[current.weekday()] in allowed_day_names:
            result.append(current)
        current += timedelta(days=1)
    return result


def upsert_asistencia(db, colegio_id, estudiante_id, curso_id, fecha, estado, asignatura_id=None, registrado_por=None):
    instance = db.query(Asistencia).filter_by(
        estudiante_id=estudiante_id,
        fecha=fecha,
        asignatura_id=asignatura_id,
    ).first()
    if not instance:
        instance = Asistencia(
            colegio_id=colegio_id,
            estudiante_id=estudiante_id,
            curso_id=curso_id,
            asignatura_id=asignatura_id,
            fecha=fecha,
            estado=estado,
            registrado_por=registrado_por,
        )
        db.add(instance)
    else:
        instance.estado = estado
        instance.curso_id = curso_id
        instance.colegio_id = colegio_id
        instance.registrado_por = registrado_por


def seed_demo_data(db):
    colegio = get_or_create(
        Colegio,
        db,
        nombre="Colegio Demo MINERD",
        codigo="demo-minerd",
        defaults={
            "plan": "enterprise",
            "max_estudiantes": 2000,
            "max_usuarios": 200,
        },
    )

    config = get_or_create(
        ConfiguracionColegio,
        db,
        colegio_id=colegio.id,
        defaults={
            "nombre": "Colegio Demo MINERD",
            "regional": "15",
            "distrito": "03",
            "codigo_centro": "DEM-1503",
            "codigo_cartografia": "CART-001",
            "direccion": "Santo Domingo, RD",
            "telefono": "809-555-1000",
            "email": "demo@educaone.test",
            "nombre_director": "Directora Demo",
            "telefono_director": "809-555-1001",
            "correo_director": "direccion@educaone.test",
            "nombre_coordinador": "Coordinador Demo",
            "modulo_primaria": True,
            "modulo_secundaria": True,
        },
    )

    ano = get_or_create(
        AnoEscolar,
        db,
        colegio_id=colegio.id,
        nombre="2026-2027",
        defaults={
            "fecha_inicio": date(2026, 8, 24),
            "fecha_fin": date(2027, 6, 25),
            "activo": True,
            "periodo_activo": 1,
            "p1_inicio": date(2026, 8, 24),
            "p1_fin": date(2026, 10, 30),
            "p2_inicio": date(2026, 11, 2),
            "p2_fin": date(2027, 1, 29),
            "p3_inicio": date(2027, 2, 1),
            "p3_fin": date(2027, 4, 30),
            "p4_inicio": date(2027, 5, 3),
            "p4_fin": date(2027, 6, 25),
        },
    )
    ano.activo = True
    ano.set_dias_trabajados({
        "ago": 6, "sep": 20, "oct": 22, "nov": 20, "dic": 12,
        "ene": 16, "feb": 20, "mar": 22, "abr": 18, "may": 21, "jun": 15,
    })

    tanda = get_or_create(
        Tanda,
        db,
        colegio_id=colegio.id,
        nombre="Matutina",
        defaults={"hora_inicio": "08:00", "hora_fin": "13:00"},
    )

    grado_sec = get_or_create(
        Grado,
        db,
        colegio_id=colegio.id,
        nombre="1ro Secundaria",
        defaults={"nivel": "secundaria", "ciclo": "primer_ciclo", "orden": 1},
    )
    grado_prim = get_or_create(
        Grado,
        db,
        colegio_id=colegio.id,
        nombre="4to Primaria",
        defaults={"nivel": "primaria", "ciclo": "segundo_ciclo", "orden": 4},
    )

    curso_sec = get_or_create(
        Curso,
        db,
        colegio_id=colegio.id,
        nombre="A",
        grado_id=grado_sec.id,
        defaults={"tanda_id": tanda.id, "ano_escolar_id": ano.id, "capacidad": 40, "aula": "S-101"},
    )
    curso_prim = get_or_create(
        Curso,
        db,
        colegio_id=colegio.id,
        nombre="B",
        grado_id=grado_prim.id,
        defaults={"tanda_id": tanda.id, "ano_escolar_id": ano.id, "capacidad": 35, "aula": "P-401"},
    )

    prof_sec = get_or_create_user(
        db,
        "demo.prof.sec",
        colegio_id=colegio.id,
        nombre="Ana",
        apellido="Secundaria",
        role="profesor",
        activo=True,
        password="Cambiar123",
    )

    prof_prim = get_or_create_user(
        db,
        "demo.prof.prim",
        colegio_id=colegio.id,
        nombre="Luis",
        apellido="Primaria",
        role="profesor",
        activo=True,
        password="Cambiar123",
    )

    asignaturas_sec = [
        "Lengua Española",
        "Matemática",
        "Ciencias Sociales",
        "Ciencias de la Naturaleza",
    ]
    asignaturas_prim = [
        "Lengua Española",
        "Matemática",
        "Ciencias Sociales",
        "Ciencias de la Naturaleza",
    ]

    sec_models = {}
    for nombre in asignaturas_sec:
        sec_models[nombre] = get_or_create(Asignatura, db, colegio_id=colegio.id, nombre=nombre, defaults={"activo": True})

    prim_models = {}
    for nombre in asignaturas_prim:
        prim_models[nombre] = get_or_create(Asignatura, db, colegio_id=colegio.id, nombre=nombre, defaults={"activo": True})

    for nombre, asignatura in sec_models.items():
        get_or_create(
            AsignacionProfesor,
            db,
            colegio_id=colegio.id,
            profesor_id=prof_sec.id,
            curso_id=curso_sec.id,
            asignatura_id=asignatura.id,
            defaults={"es_titular": nombre == "Lengua Española", "activo": True, "ano_escolar_id": ano.id},
        )

    for nombre, asignatura in prim_models.items():
        get_or_create(
            AsignacionProfesor,
            db,
            colegio_id=colegio.id,
            profesor_id=prof_prim.id,
            curso_id=curso_prim.id,
            asignatura_id=asignatura.id,
            defaults={"es_titular": True, "activo": True, "ano_escolar_id": ano.id},
        )

    schedule_days = ["Lunes", "Martes", "Miércoles", "Jueves"]
    schedule_hours = ["08:00", "09:00", "10:00", "11:00"]

    for idx, asignatura in enumerate(sec_models.values()):
        get_or_create(
            Horario,
            db,
            colegio_id=colegio.id,
            profesor_id=prof_sec.id,
            curso_id=curso_sec.id,
            asignatura_id=asignatura.id,
            dia=schedule_days[idx],
            defaults={"hora_inicio": schedule_hours[idx], "hora_fin": f"{int(schedule_hours[idx][:2])+1:02d}:00", "tipo_bloque": "clase", "activo": True},
        )

    for idx, asignatura in enumerate(prim_models.values()):
        get_or_create(
            Horario,
            db,
            colegio_id=colegio.id,
            profesor_id=prof_prim.id,
            curso_id=curso_prim.id,
            asignatura_id=asignatura.id,
            dia=schedule_days[idx],
            defaults={"hora_inicio": schedule_hours[idx], "hora_fin": f"{int(schedule_hours[idx][:2])+1:02d}:00", "tipo_bloque": "clase", "activo": True},
        )

    get_or_create(
        DiaNoLaborable,
        db,
        colegio_id=colegio.id,
        fecha=date(2026, 9, 24),
        defaults={"nombre": "Las Mercedes", "tipo": "feriado", "ano_escolar_id": ano.id, "activo": True},
    )

    estudiantes_sec = []
    for i in range(1, 6):
        est = get_or_create(
            Estudiante,
            db,
            colegio_id=colegio.id,
            matricula=f"SEC{i:03d}",
            defaults={
                "nombre": f"Sec{i}",
                "apellido": "Demo",
                "fecha_nacimiento": date(2012, 1, min(i, 28)),
                "sexo": "M" if i % 2 else "F",
                "curso_id": curso_sec.id,
                "no_lista": i,
                "activo": True,
                "direccion": "Sector Demo",
                "cedula": f"000-000000{i}-0",
                "condicion_entrada": "nuevo",
            },
        )
        est.curso_id = curso_sec.id
        est.no_lista = i
        est.activo = True
        estudiantes_sec.append(est)

    estudiantes_prim = []
    for i in range(1, 6):
        est = get_or_create(
            Estudiante,
            db,
            colegio_id=colegio.id,
            matricula=f"PRI{i:03d}",
            defaults={
                "nombre": f"Prim{i}",
                "apellido": "Demo",
                "fecha_nacimiento": date(2016, 2, min(i, 28)),
                "sexo": "F" if i % 2 else "M",
                "curso_id": curso_prim.id,
                "no_lista": i,
                "activo": True,
                "direccion": "Sector Demo",
                "cedula": f"111-000000{i}-0",
                "condicion_entrada": "nuevo",
            },
        )
        est.curso_id = curso_prim.id
        est.no_lista = i
        est.activo = True
        estudiantes_prim.append(est)

    db.flush()

    for asignatura in sec_models.values():
        for idx, est in enumerate(estudiantes_sec, start=1):
            calif = get_or_create(
                Calificacion,
                db,
                colegio_id=colegio.id,
                estudiante_id=est.id,
                asignatura_id=asignatura.id,
                defaults={"ano_escolar_id": ano.id},
            )
            base = 72 + idx
            calif.pc1 = base
            calif.pc2 = base + 1
            calif.pc3 = base + 2
            calif.pc4 = base + 3
            calif.cf = round((calif.pc1 + calif.pc2 + calif.pc3 + calif.pc4) / 4, 2)

    for asignatura in prim_models.values():
        for idx, est in enumerate(estudiantes_prim, start=1):
            for competencia in [1, 2, 3]:
                calif = get_or_create(
                    CalificacionPrimaria,
                    db,
                    colegio_id=colegio.id,
                    estudiante_id=est.id,
                    asignatura_id=asignatura.id,
                    competencia_numero=competencia,
                    defaults={"ano_escolar_id": ano.id},
                )
                base = 3 + idx
                calif.p1 = base
                calif.p2 = base + 0.5
                calif.p3 = base + 0.5
                calif.p4 = base + 1
                calif.final_competencia = round((calif.p1 + calif.p2 + calif.p3 + calif.p4) / 4, 2)

    sec_dates = school_days_between(date(2026, 8, 24), date(2026, 9, 10), set(schedule_days))
    for asignatura in sec_models.values():
        for idx, est in enumerate(estudiantes_sec, start=1):
            for dia_idx, fecha in enumerate(sec_dates[:6], start=1):
                estado = "presente"
                if idx == 2 and dia_idx == 3:
                    estado = "ausente"
                elif idx == 3 and dia_idx == 4:
                    estado = "tardanza"
                upsert_asistencia(db, colegio.id, est.id, curso_sec.id, fecha, estado, asignatura_id=asignatura.id, registrado_por=prof_sec.id)

    prim_dates = school_days_between(date(2026, 8, 24), date(2026, 9, 10), {"Lunes", "Martes", "Miércoles", "Jueves"})
    for idx, est in enumerate(estudiantes_prim, start=1):
        for dia_idx, fecha in enumerate(prim_dates[:6], start=1):
            estado = "presente"
            if idx == 4 and dia_idx == 2:
                estado = "ausente"
            upsert_asistencia(db, colegio.id, est.id, curso_prim.id, fecha, estado, asignatura_id=None, registrado_por=prof_prim.id)

    db.commit()
    return {
        "colegio": colegio,
        "config": config,
        "ano": ano,
        "curso_sec": curso_sec,
        "curso_prim": curso_prim,
        "prof_sec": prof_sec,
        "prof_prim": prof_prim,
        "estudiantes_sec": estudiantes_sec,
        "estudiantes_prim": estudiantes_prim,
        "sec_models": sec_models,
        "prim_models": prim_models,
    }


def build_secundaria_payload(db, seeded):
    curso = seeded["curso_sec"]
    config = seeded["config"]
    ano = seeded["ano"]
    estudiantes = seeded["estudiantes_sec"]
    asignaturas = seeded["sec_models"]
    validacion = validar_registro_secundaria(db, curso.id, curso.colegio_id)

    asignaturas_data = {}
    for nombre, asignatura in asignaturas.items():
        califs = {}
        for idx, est in enumerate(estudiantes):
            c = db.query(Calificacion).filter_by(estudiante_id=est.id, asignatura_id=asignatura.id).first()
            califs[idx] = {
                "p1": c.pc1, "rp1": c.rp1, "p2": c.pc2, "rp2": c.rp2,
                "p3": c.pc3, "rp3": c.rp3, "p4": c.pc4, "rp4": c.rp4,
                "pc1": c.pc1, "pc2": c.pc2, "pc3": c.pc3, "pc4": c.pc4, "cf": c.cf,
            }
        asignaturas_data[nombre] = {
            "docente": seeded["prof_sec"].nombre_completo,
            "calificaciones": califs,
            "asistencia_matriz": build_asistencia_registro(db, curso.id, asignatura_id=asignatura.id, estudiantes=estudiantes),
            "asistencias": {},
        }

    estudiantes_raw = [{
        "id": est.id,
        "no_lista": est.no_lista,
        "nombre": est.nombre_completo,
        "sexo": est.sexo,
        "fecha_nacimiento": est.fecha_nacimiento,
        "cedula": est.cedula,
        "matricula": est.matricula,
        "direccion": est.direccion,
        "condicion_entrada": est.condicion_entrada,
    } for est in estudiantes]

    colegio_info = {
        "nombre": config.nombre,
        "regional": config.regional,
        "distrito": config.distrito,
        "direccion": config.direccion,
        "telefono": config.telefono,
        "email": config.email,
        "director": config.nombre_director,
        "codigo_centro": config.codigo_centro,
        "codigo_cartografia": config.codigo_cartografia,
        "coordinador": seeded["prof_sec"].nombre_completo,
        # Datos de identificación del centro (van a círculos del PDF)
        "sector": "privado",         # publico | privado | semioficial
        "zona": "urbana",            # urbana | urbana_marginal | urbana_turistica | rural | rural_aislada | rural_turistica
        "jornada": "matutina",       # jee | matutina | vespertina | nocturna
    }
    curso_info = {"grado": curso.grado.nombre, "seccion": curso.nombre, "tanda": curso.tanda.nombre if curso.tanda else ""}

    return {
        "validacion": validacion.to_dict(),
        "pdf_bytes": generar_registro_desde_sistema(colegio_info, curso_info, ano.nombre, estudiantes_raw, asignaturas_data, 1),
        "asistencia_muestra": build_asistencia_registro(db, curso.id, asignatura_id=next(iter(asignaturas.values())).id, estudiantes=estudiantes),
    }


def build_primaria_payload(db, seeded):
    curso = seeded["curso_prim"]
    config = seeded["config"]
    ano = seeded["ano"]
    estudiantes = seeded["estudiantes_prim"]
    asignaturas = seeded["prim_models"]
    validacion = validar_registro_primaria(db, curso.id, curso.colegio_id)

    calificaciones_por_area = {}
    for nombre, asignatura in asignaturas.items():
        area_data = {}
        for idx, est in enumerate(estudiantes):
            competencias = {}
            for comp_num in [1, 2, 3]:
                c = db.query(CalificacionPrimaria).filter_by(
                    estudiante_id=est.id,
                    asignatura_id=asignatura.id,
                    competencia_numero=comp_num,
                ).first()
                competencias[comp_num] = {
                    "p1": c.p1, "p2": c.p2, "p3": c.p3, "p4": c.p4,
                    "rp1": c.rp1, "rp2": c.rp2, "rp3": c.rp3, "rp4": c.rp4,
                    "final_competencia": c.final_competencia,
                }
            area_data[idx] = competencias
        calificaciones_por_area[nombre] = area_data

    estudiantes_raw = [{
        "id": est.id,
        "no_lista": est.no_lista,
        "nombre": est.nombre_completo,
        "sexo": est.sexo,
        "fecha_nacimiento": est.fecha_nacimiento,
        "matricula": est.matricula,
    } for est in estudiantes]

    colegio_info = {
        "nombre": config.nombre,
        "regional": config.regional,
        "distrito": config.distrito,
        "codigo_centro": config.codigo_centro,
        "codigo_cartografia": config.codigo_cartografia,
        "direccion": config.direccion,
        "director": config.nombre_director,
        "docente_titular": seeded["prof_prim"].nombre_completo,
    }
    curso_info = {"grado": curso.grado.nombre, "seccion": curso.nombre, "tanda": curso.tanda.nombre if curso.tanda else ""}
    asistencia = build_asistencia_registro(db, curso.id, estudiantes=estudiantes)

    return {
        "validacion": validacion.to_dict(),
        "pdf_bytes": generar_registro_primaria_desde_sistema(
            colegio_info,
            curso_info,
            ano.nombre,
            estudiantes_raw,
            calificaciones_por_area,
            asistencia,
            ano.get_dias_trabajados(),
            4,
        ),
        "asistencia_muestra": asistencia,
    }


def main():
    ensure_dir(ARTIFACTS_DIR)
    db = SessionLocal()
    try:
        seeded = seed_demo_data(db)

        secundaria = build_secundaria_payload(db, seeded)
        primaria = build_primaria_payload(db, seeded)

        sec_pdf = ARTIFACTS_DIR / "registro_secundaria_demo.pdf"
        prim_pdf = ARTIFACTS_DIR / "registro_primaria_demo.pdf"
        sec_pdf.write_bytes(secundaria["pdf_bytes"])
        prim_pdf.write_bytes(primaria["pdf_bytes"])

        summary = {
            "generated_at": date.today().isoformat(),
            "artifacts": {
                "secundaria_pdf": str(sec_pdf),
                "primaria_pdf": str(prim_pdf),
            },
            "secundaria": {
                "validacion": secundaria["validacion"],
                "asistencia_muestra": secundaria["asistencia_muestra"][:2],
            },
            "primaria": {
                "validacion": primaria["validacion"],
                "asistencia_muestra": primaria["asistencia_muestra"][:2],
            },
        }
        write_json(ARTIFACTS_DIR / "validation_summary.json", summary)
        print(json.dumps(summary, ensure_ascii=True, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
