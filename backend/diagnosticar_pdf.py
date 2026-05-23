"""
Script de diagnóstico del PDF de conducta.
Corré esto en la carpeta backend con tu base de datos real:

    cd C:\Users\owner\OneDrive\Desktop\educaone_v2.13.22\backend
    $env:DATABASE_URL = "sqlite:///./educaone.db"
    python diagnosticar_pdf.py

Te dice EXACTAMENTE qué falla al generar el PDF del reporte.
"""
import os, sys, traceback
os.environ.setdefault('DATABASE_URL', 'sqlite:///./educaone.db')
os.environ.setdefault('SECRET_KEY', 'dev-secret-cambiar')
os.environ.setdefault('JWT_SECRET_KEY', 'dev-jwt-cambiar')

from database import SessionLocal
from models import (Estudiante, Curso, Grado, Tanda, Usuario, ConfiguracionColegio,
                    Colegio, AnoEscolar, ReporteConducta)
from reporte_conducta_pdf import generar_reporte_conducta_pdf

db = SessionLocal()
reportes = db.query(ReporteConducta).all()
print(f"\n{'='*60}")
print(f"Reportes de conducta en la base: {len(reportes)}")
print(f"{'='*60}\n")

for rep in reportes:
    print(f"--- Reporte id={rep.id} '{rep.titulo}' ---")
    try:
        est = db.get(Estudiante, rep.estudiante_id)
        curso = db.get(Curso, est.curso_id) if est and est.curso_id else None
        grado = db.get(Grado, curso.grado_id) if curso and curso.grado_id else None
        tanda = db.get(Tanda, curso.tanda_id) if curso and curso.tanda_id else None
        reportador = db.get(Usuario, rep.reportado_por) if rep.reportado_por else None
        respondedor = db.get(Usuario, rep.respondido_por) if rep.respondido_por else None
        config = db.query(ConfiguracionColegio).filter_by(colegio_id=rep.colegio_id).first()
        colegio = db.get(Colegio, rep.colegio_id)
        ano = db.query(AnoEscolar).filter_by(colegio_id=rep.colegio_id, activo=True).first()
        if not ano:
            ano = db.query(AnoEscolar).filter_by(colegio_id=rep.colegio_id).order_by(AnoEscolar.id.desc()).first()
        ano_str = ano.nombre if ano else None

        if not est:
            print(f"  ❌ PROBLEMA: el estudiante id={rep.estudiante_id} NO existe en la base")
            continue

        pdf = generar_reporte_conducta_pdf(
            reporte=rep, estudiante=est, curso=curso, grado=grado, tanda=tanda,
            reportador=reportador, respondedor=respondedor,
            config=config, colegio=colegio, ano_escolar=ano_str)
        print(f"  ✅ PDF OK: {len(pdf)} bytes")
    except Exception as e:
        print(f"  ❌ CRASH: {type(e).__name__}: {e}")
        print("  --- traceback ---")
        traceback.print_exc()
        print()

db.close()
print("\nDiagnóstico terminado.")
