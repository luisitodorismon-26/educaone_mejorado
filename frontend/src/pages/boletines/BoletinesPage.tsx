import { useState, useEffect, useRef } from 'react';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';
import { FileText, Download, Printer, Search, Users, GraduationCap, Calendar } from 'lucide-react';
import { Select, Button, Spinner, Alert } from '../../components/ui';

interface Curso {
  id: number;
  nombre_completo: string;
  nombre?: string;
  grado?: string;
  tanda?: string;
  nivel?: string;   // 'primaria' | 'secundaria'
}

interface Estudiante {
  id: number;
  nombre_completo: string;
  no_lista: number;
  matricula: string;
}

interface CompetenciaDetalle {
  numero: number;
  p1: number | null; p2: number | null; p3: number | null; p4: number | null;
  pc: number | null;
}

interface EvExtraResumen {
  cf_original: number | null;
  cec: number | null; completiva_final: number | null;
  ceex: number | null; extraordinaria_final: number | null;
  ce: number | null; especial_final: number | null;
  fase_pendiente: string | null;
  nota_final: number | null;
  condicion_final: string | null;
}

interface CalificacionBoletin {
  asignatura: string;
  asignatura_id: number;
  pc1: number | null;
  rp1: number | null;
  pc2: number | null;
  rp2: number | null;
  pc3: number | null;
  rp3: number | null;
  pc4: number | null;
  rp4: number | null;
  cf: number | null;
  literal: string | null;
  competencias_detalle?: CompetenciaDetalle[];
  nota_final?: number | null;
  condicion_final?: string | null;
  evaluacion_extra?: EvExtraResumen | null;
}

interface Boletin {
  estudiante: {
    id: number;
    nombre: string;
    matricula: string;
    curso: string;
    grado: string;
  };
  asignaturas: CalificacionBoletin[];
  asistencia: {
    presentes: number;
    total: number;
    porcentaje: number;
  };
  promedio_general: number;
}

interface Colegio {
  nombre: string;
  logo: string | null;
  direccion: string;
  telefono: string;
  distrito: string;
  regional: string;
}

export const BoletinesPage = () => {
  const { user } = useAuth();
  const [cursos, setCursos] = useState<Curso[]>([]);
  const [estudiantes, setEstudiantes] = useState<Estudiante[]>([]);
  const [cursoId, setCursoId] = useState<number | null>(null);
  // v2.13.48: el boletín depende del NIVEL del curso (primaria ≠ secundaria)
  const cursoActual = cursos.find(c => c.id === cursoId);
  const esPrimaria = (cursoActual?.nivel || '').toLowerCase() === 'primaria';

  // Descarga un PDF validando que el servidor no haya devuelto un error JSON
  const descargarPDF = async (url: string, filename: string, msgError: string) => {
    try {
      const response = await api.get(url, { responseType: 'blob' });
      if (response.data.type === 'application/json' || response.data.size < 300) {
        const texto = await response.data.text();
        try {
          const j = JSON.parse(texto);
          setError(j.error || msgError);
          return;
        } catch { /* no era JSON: seguir */ }
      }
      const dlUrl = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = dlUrl;
      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(dlUrl);
    } catch (err: any) {
      console.error('Error descargando PDF:', err);
      setError(err?.response?.data?.error || msgError);
    }
  };
  const [estudianteId, setEstudianteId] = useState<number | null>(null);
  const [boletin, setBoletin] = useState<Boletin | null>(null);
  const [colegio, setColegio] = useState<Colegio | null>(null);
  const [periodo, setPeriodo] = useState<number>(0);
  const [loading, setLoading] = useState(true);
  const [loadingBoletin, setLoadingBoletin] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const boletinRef = useRef<HTMLDivElement>(null);

  const esProfesor = user?.role === 'profesor';

  useEffect(() => {
    cargarDatosIniciales();
  }, []);

  useEffect(() => {
    if (cursoId) cargarEstudiantes();
  }, [cursoId]);

  const cargarDatosIniciales = async () => {
    try {
      const [cursosRes, colegioRes] = await Promise.all([
        esProfesor ? api.get('/dashboard/profesor') : api.get('/cursos'),
        api.get('/configuracion/colegio')
      ]);

      if (esProfesor && cursosRes.data.cursos_asignados) {
        const cursosUnicos = cursosRes.data.cursos_asignados.reduce((acc: Curso[], curr: any) => {
          if (!acc.find(c => c.id === curr.curso_id)) {
            acc.push({ id: curr.curso_id, nombre_completo: curr.curso });
          }
          return acc;
        }, []);
        setCursos(cursosUnicos);
      } else {
        setCursos(cursosRes.data || []);
      }
      setColegio(colegioRes.data);
    } catch (err) {
      console.error('Error cargando datos:', err);
    } finally {
      setLoading(false);
    }
  };

  const cargarEstudiantes = async () => {
    try {
      const res = await api.get(`/estudiantes?curso_id=${cursoId}`);
      setEstudiantes(res.data);
      setEstudianteId(null);
      setBoletin(null);
    } catch (err) {
      console.error('Error cargando estudiantes:', err);
    }
  };

  const cargarBoletin = async () => {
    if (!estudianteId) return;
    setLoadingBoletin(true);
    setError(null);
    try {
      const res = await api.get(`/boletines/estudiante/${estudianteId}`);
      if (res.data?.error) {
        setError(res.data.error);
      } else {
        // Blindaje: garantizar que asignaturas siempre sea un array
        setBoletin({ ...res.data, asignaturas: Array.isArray(res.data?.asignaturas) ? res.data.asignaturas : [] });
      }
    } catch (err) {
      console.error('Error cargando boletín:', err);
      setError('Error al cargar el boletín');
    } finally {
      setLoadingBoletin(false);
    }
  };

  const getLiteral = (nota: number | null): string => {
    if (nota === null) return '-';
    if (nota >= 90) return 'A';
    if (nota >= 80) return 'B';
    if (nota >= 70) return 'C';
    return 'F';
  };

  const getNotaClass = (nota: number | null): string => {
    if (nota === null) return 'text-gray-400';
    if (nota >= 90) return 'text-emerald-600 font-bold';
    if (nota >= 80) return 'text-blue-600 font-bold';
    if (nota >= 70) return 'text-amber-600 font-bold';
    return 'text-red-600 font-bold';
  };

  if (loading) {
    return <div className="flex justify-center py-12"><Spinner size="lg" /></div>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <FileText className="text-blue-600" />
          Boletines de Calificaciones
        </h1>
        <p className="text-gray-500 mt-1">Generar reportes de calificaciones para padres</p>
      </div>

      {error && <Alert variant="error" onClose={() => setError(null)}>{error}</Alert>}

      <div className="bg-white rounded-xl shadow-sm border p-4">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Select
            label="Curso"
            value={cursoId?.toString() || ''}
            onChange={(e) => setCursoId(e.target.value ? parseInt(e.target.value) : null)}
            options={cursos.map(c => ({ value: c.id, label: c.grado ? `${c.grado} ${c.nombre}` : c.nombre_completo, group: c.tanda || 'Sin tanda' }))}
            placeholder="Seleccione curso"
          />
          <Select
            label="Estudiante"
            value={estudianteId?.toString() || ''}
            onChange={(e) => setEstudianteId(e.target.value ? parseInt(e.target.value) : null)}
            options={estudiantes.map(e => ({ value: e.id, label: `${e.no_lista}. ${e.nombre_completo}` }))}
            placeholder="Seleccione estudiante"
            disabled={!cursoId}
          />
          <div className="flex items-end gap-2">
            <Button onClick={cargarBoletin} disabled={!estudianteId} loading={loadingBoletin} icon={<Search size={18} />} className="flex-1">
              Ver Boletín
            </Button>
          </div>
        </div>
        {cursoId && (
          <div className="mt-3 pt-3 border-t">
            <p className="text-sm text-gray-600 mb-2">
              Descargar todos los boletines del curso
              {esPrimaria && <span className="ml-1 text-blue-600 font-medium">(Nivel Primario)</span>}:
            </p>
            <div className="flex flex-wrap gap-2 justify-end">
              {esPrimaria ? (
                <Button
                  variant="primary"
                  icon={<Download size={16} />}
                  onClick={() => descargarPDF(
                    `/boletines-primaria/curso/${cursoId}/pdf`,
                    `Informes_Aprendizaje_${(cursoActual?.nombre_completo || 'Curso').replace(/ /g, '_')}.pdf`,
                    'Error al generar los Informes de Aprendizaje del curso'
                  )}
                >
                  🎒 Informes de Aprendizaje (Curso)
                </Button>
              ) : (
                <>
                  <Button
                    variant="secondary"
                    icon={<Download size={16} />}
                    onClick={() => descargarPDF(
                      `/boletines/curso/${cursoId}/pdf`,
                      `Boletines_Padres_${(cursoActual?.nombre_completo || 'Curso').replace(/ /g, '_')}.pdf`,
                      'Error al generar boletines para padres del curso'
                    )}
                  >
                    📥 Boletines para Padres (Curso)
                  </Button>
                  <Button
                    variant="secondary"
                    icon={<Download size={16} />}
                    onClick={() => descargarPDF(
                      `/boletines/curso/${cursoId}/pdf-minerd-v2`,
                      `Boletines_MINERD_${(cursoActual?.nombre_completo || 'Curso').replace(/ /g, '_')}.pdf`,
                      'Error al generar boletines MINERD del curso'
                    )}
                  >
                    📄 Boletines MINERD (Curso)
                  </Button>
                </>
              )}
            </div>
          </div>
        )}
      </div>

      {boletin && (
        <div className="bg-white rounded-xl shadow-sm border overflow-hidden">
          <div className="p-4 bg-gray-50 border-b flex justify-end gap-2 print:hidden">
            <Button onClick={() => window.print()} variant="secondary" icon={<Printer size={18} />}>Imprimir</Button>
            {esPrimaria ? (
              <Button
                variant="primary"
                icon={<Download size={16} />}
                onClick={() => descargarPDF(
                  `/boletines-primaria/estudiante/${estudianteId}/pdf`,
                  `Informe_Aprendizaje_${(boletin.estudiante.nombre || 'estudiante').replace(/ /g, '_')}.pdf`,
                  'Error al generar el Informe de Aprendizaje'
                )}
              >
                🎒 Informe de Aprendizaje
              </Button>
            ) : (
              <>
                <Button
                  variant="secondary"
                  icon={<Download size={16} />}
                  onClick={() => descargarPDF(
                    `/boletines/estudiante/${estudianteId}/pdf`,
                    `Boletin_${(boletin.estudiante.nombre || 'estudiante').replace(/ /g, '_')}.pdf`,
                    'Error al generar el boletín para padres'
                  )}
                >
                  📥 Boletín para Padres
                </Button>
                <Button
                  variant="secondary"
                  icon={<Download size={16} />}
                  onClick={() => descargarPDF(
                    `/boletines/estudiante/${estudianteId}/pdf-minerd-v2`,
                    `Boletin_MINERD_${(boletin.estudiante.nombre || 'estudiante').replace(/ /g, '_')}.pdf`,
                    'Error al generar el boletín MINERD'
                  )}
                >
                  📄 Boletín MINERD Oficial
                </Button>
              </>
            )}
            <Button 
              onClick={() => {
                const est = estudiantes.find(e => e.id === estudianteId);
                const mensaje = `📋 *BOLETÍN DE CALIFICACIONES*%0A%0A` +
                  `👤 Estudiante: ${boletin.estudiante.nombre}%0A` +
                  `📚 Curso: ${boletin.estudiante.curso}%0A` +
                  `📊 Promedio General: ${boletin.promedio_general?.toFixed(1) || 'N/A'}%0A` +
                  `✅ Asistencia: ${boletin.asistencia?.porcentaje?.toFixed(1) || 0}%25%0A%0A` +
                  `Para ver el boletín completo, favor acercarse al colegio.`;
                window.open(`https://wa.me/?text=${mensaje}`, '_blank');
              }} 
              variant="secondary" 
              className="bg-green-600 hover:bg-green-700 text-white"
            >
              📱 Enviar por WhatsApp
            </Button>
          </div>

          <div ref={boletinRef} className="p-6 print:p-4" id="boletin-content">
            {/* Header MINERD */}
            <div className="text-center mb-4">
              <p className="text-xs text-gray-500">Viceministro de Servicios Técnicos y Pedagógicos</p>
              <p className="text-xs text-gray-500">Dirección General de Educación Secundaria</p>
              <h1 className="text-lg font-bold text-blue-800 mt-2">BOLETÍN DE CALIFICACIONES</h1>
              <p className="text-sm text-gray-600 font-medium">{colegio?.nombre || 'Centro Educativo'}</p>
            </div>

            {/* Info estudiante */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4 p-3 bg-blue-50 rounded-lg border border-blue-200 text-sm">
              <div><p className="text-xs text-blue-600">Estudiante</p><p className="font-semibold">{boletin.estudiante.nombre}</p></div>
              <div><p className="text-xs text-blue-600">Matrícula</p><p className="font-semibold">{boletin.estudiante.matricula || 'N/A'}</p></div>
              <div><p className="text-xs text-blue-600">Curso</p><p className="font-semibold">{boletin.estudiante.curso}</p></div>
              <div><p className="text-xs text-blue-600">Grado</p><p className="font-semibold">{boletin.estudiante.grado}</p></div>
            </div>

            {/* Tabla detallada — igual al Boletín para Padres (v2.13.38) */}
            <div className="overflow-x-auto">
              <table className="w-full text-xs border-collapse">
                <thead>
                  <tr className="bg-blue-900 text-white">
                    <th className="border border-blue-800 p-1.5 text-left" rowSpan={2}>Áreas Curriculares</th>
                    <th className="border border-blue-800 p-1 text-center" colSpan={4}>Competencia 1</th>
                    <th className="border border-blue-800 p-1 text-center" colSpan={4}>Competencia 2</th>
                    <th className="border border-blue-800 p-1 text-center" colSpan={4}>Competencia 3</th>
                    <th className="border border-blue-800 p-1 text-center" colSpan={4}>Competencia 4</th>
                    <th className="border border-blue-800 p-1 text-center bg-amber-600" rowSpan={2}>PC<br/>(1·2·3·4)</th>
                    <th className="border border-blue-800 p-1 text-center bg-yellow-700" rowSpan={2}>CF</th>
                    <th className="border border-blue-800 p-1 text-center bg-green-800" rowSpan={2}>Situación</th>
                  </tr>
                  <tr className="bg-blue-800 text-white text-[10px]">
                    {[1, 2, 3, 4].map(c => (
                      ['P1', 'P2', 'P3', 'P4'].map(p => (
                        <th key={`${c}-${p}`} className="border border-blue-700 p-1">{p}</th>
                      ))
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(boletin.asignaturas || []).map((asig, idx) => {
                    const ev = asig.evaluacion_extra;
                    const notaFinal = asig.nota_final ?? asig.cf;
                    const comps = asig.competencias_detalle || [];
                    const compPorNum = (n: number) => comps.find(c => c.numero === n);
                    const situacion = () => {
                      if (asig.cf === null) return <span className="text-gray-400">—</span>;
                      if (asig.cf >= 70) return <span className="font-bold text-green-700">A ({asig.cf.toFixed(0)})</span>;
                      if (ev?.fase_pendiente) return <span className="text-amber-700 font-medium uppercase text-[10px]">{ev.fase_pendiente} pend.</span>;
                      if (notaFinal != null && notaFinal >= 70) return <span className="font-bold text-green-700">A ({Math.round(notaFinal)})</span>;
                      return <span className="font-bold text-red-600">R ({notaFinal != null ? Math.round(notaFinal) : '—'})</span>;
                    };
                    return (
                      <tr key={asig.asignatura_id || idx} className={idx % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                        <td className="border border-gray-300 p-1.5 font-medium bg-blue-50">{asig.asignatura}</td>
                        {[1, 2, 3, 4].map(n => {
                          const comp = compPorNum(n);
                          return (['p1', 'p2', 'p3', 'p4'] as const).map(pk => {
                            const v = comp ? comp[pk] : null;
                            return (
                              <td key={`${n}-${pk}`} className={`border border-gray-300 p-1 text-center ${v == null ? 'text-gray-300' : getNotaClass(v)}`}>
                                {v != null ? Math.round(v) : '—'}
                              </td>
                            );
                          });
                        })}
                        <td className="border border-gray-300 p-1 text-center bg-amber-50 font-bold text-[10px] whitespace-nowrap">
                          {comps.length === 4 ? comps.map(c => c.pc != null ? c.pc.toFixed(1).replace(/\.0$/, '') : '—').join('·') : '—'}
                        </td>
                        <td className={`border border-gray-300 p-1 text-center font-bold bg-yellow-50 ${getNotaClass(asig.cf)}`}>{asig.cf?.toFixed(0) ?? ''}</td>
                        <td className="border border-gray-300 p-1 text-center bg-green-50 whitespace-nowrap">{situacion()}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Desglose de evaluaciones extra (si las hay) — mismo lenguaje que la pantalla de carga */}
            {(boletin.asignaturas || []).some(a => a.evaluacion_extra) && (
              <div className="mt-3 bg-amber-50 border border-amber-200 rounded-lg p-3">
                <p className="text-xs font-bold text-amber-800 mb-2">Evaluaciones extra (desglose oficial):</p>
                {(boletin.asignaturas || []).filter(a => a.evaluacion_extra).map(a => {
                  const ev = a.evaluacion_extra!;
                  const cf = ev.cf_original ?? a.cf ?? 0;
                  const partes: string[] = [];
                  if (ev.cec != null) partes.push(`Completiva: 50%CF ${(cf * 0.5).toFixed(1)} + 50%CEC ${(ev.cec * 0.5).toFixed(1)} → ${ev.completiva_final != null ? Math.round(ev.completiva_final) : '—'}`);
                  if (ev.ceex != null) partes.push(`Extraordinaria: 30%CF ${(cf * 0.3).toFixed(1)} + 70%CEEX ${(ev.ceex * 0.7).toFixed(1)} → ${ev.extraordinaria_final != null ? Math.round(ev.extraordinaria_final) : '—'}`);
                  if (ev.ce != null) partes.push(`Especial: ${Math.round(cf)} + ${Math.round(ev.ce)} → ${ev.especial_final != null ? Math.round(ev.especial_final) : '—'}`);
                  const resuelto = !ev.fase_pendiente && ev.nota_final != null;
                  return (
                    <p key={a.asignatura_id} className="text-[11px] text-gray-700 mb-1">
                      <strong>{a.asignatura}:</strong> {partes.join('  |  ')}
                      {resuelto && (
                        <span className={`ml-2 px-2 py-0.5 rounded-full text-[10px] font-medium ${ev.nota_final! >= 70 ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                          {(ev.condicion_final || '').replace(/_/g, ' ')} ({Math.round(ev.nota_final!)})
                        </span>
                      )}
                      {ev.fase_pendiente && (
                        <span className="ml-2 px-2 py-0.5 rounded-full text-[10px] font-medium bg-amber-100 text-amber-800 uppercase">{ev.fase_pendiente} pendiente</span>
                      )}
                    </p>
                  );
                })}
              </div>
            )}

            {/* Resumen */}
            <div className="mt-4 grid grid-cols-3 gap-3">
              <div className="bg-blue-50 rounded-lg p-3 text-center border border-blue-200">
                <p className="text-xs text-blue-600 uppercase">Promedio General</p>
                <p className={`text-xl font-bold ${getNotaClass(boletin.promedio_general)}`}>{boletin.promedio_general.toFixed(1)}</p>
              </div>
              <div className="bg-emerald-50 rounded-lg p-3 text-center border border-emerald-200">
                <p className="text-xs text-emerald-600 uppercase">Asistencia</p>
                <p className="text-xl font-bold text-emerald-600">{boletin.asistencia.porcentaje.toFixed(0)}%</p>
              </div>
              {(() => {
                // v2.13.38: la situación general respeta la cascada de evaluaciones extra
                const conNotas = (boletin.asignaturas || []).filter(a => a.cf !== null);
                const hayPendiente = conNotas.some(a => a.evaluacion_extra?.fase_pendiente);
                const todasResueltas = conNotas.length > 0 && conNotas.every(a => (a.nota_final ?? a.cf ?? 0) >= 70);
                const hayReprobada = conNotas.some(a => !a.evaluacion_extra?.fase_pendiente && (a.nota_final ?? a.cf ?? 0) < 70);
                let texto = '— SIN NOTAS'; let clase = 'bg-gray-50 border-gray-200 text-gray-500';
                if (conNotas.length > 0) {
                  if (hayPendiente) { texto = '⏳ EVALUACIONES EXTRA EN CURSO'; clase = 'bg-amber-50 border-amber-200 text-amber-700'; }
                  else if (todasResueltas) { texto = '✓ APROBADO'; clase = 'bg-green-50 border-green-200 text-green-600'; }
                  else if (hayReprobada) { texto = '✗ REPROBADO'; clase = 'bg-red-50 border-red-200 text-red-600'; }
                }
                return (
                  <div className={`rounded-lg p-3 text-center border ${clase}`}>
                    <p className="text-xs uppercase">Situación</p>
                    <p className="text-sm font-bold">{texto}</p>
                  </div>
                );
              })()}
            </div>

            {/* Leyenda */}
            <div className="mt-3 text-[10px] text-gray-500 border-t pt-2 grid grid-cols-2 gap-1">
              <p><strong>PC</strong> = Promedio de cada Competencia (sus 4 períodos)</p>
              <p><strong>CF</strong> = Calificación Final del Área</p>
              <p><strong>A/R</strong> = Aprobado/Reprobado con la nota final (cascada incluida)</p>
              <p><strong>P</strong> = nota del período (se usa el mayor entre P y RP)</p>
              <p><strong>A</strong> = Aprobado (≥70) | <strong>R</strong> = Reprobado (&lt;70)</p>
              <p><strong>Literales:</strong> A(90+) B(80-89) C(70-79) F(&lt;70)</p>
            </div>

            {/* Firmas */}
            <div className="mt-6 grid grid-cols-3 gap-8 pt-6">
              <div className="text-center border-t border-gray-400 pt-2"><p className="text-xs text-gray-600">Maestro(a) encargado(a)</p></div>
              <div className="text-center border-t border-gray-400 pt-2"><p className="text-xs text-gray-600">Director(a) del Centro</p></div>
              <div className="text-center border-t border-gray-400 pt-2"><p className="text-xs text-gray-600">Padre/Madre/Tutor</p></div>
            </div>

            <p className="mt-4 text-center text-[10px] text-gray-400">
              Generado el {new Date().toLocaleDateString('es-DO', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
            </p>
          </div>
        </div>
      )}

      {!boletin && cursoId && (
        <div className="bg-white rounded-xl shadow-sm border p-12 text-center">
          <FileText size={48} className="mx-auto text-gray-300 mb-4" />
          <p className="text-gray-500">Seleccione un estudiante y haga clic en "Ver Boletín"</p>
        </div>
      )}

      <style>{`
        @media print {
          body * { visibility: hidden; }
          #boletin-content, #boletin-content * { visibility: visible; }
          #boletin-content { position: absolute; left: 0; top: 0; width: 100%; }
          .print\\:hidden { display: none !important; }
        }
      `}</style>
    </div>
  );
};

export default BoletinesPage;
