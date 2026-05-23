import { useState, useEffect, useRef } from 'react';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';
import { FileText, Download, Printer, Search, Users, GraduationCap, Calendar } from 'lucide-react';
import { Select, Button, Spinner, Alert } from '../../components/ui';

interface Curso {
  id: number;
  nombre_completo: string;
}

interface Estudiante {
  id: number;
  nombre_completo: string;
  no_lista: number;
  matricula: string;
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
      setBoletin(res.data);
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
          <div className="mt-3 pt-3 border-t flex justify-end">
            <Button 
              variant="secondary"
              icon={<Download size={16} />}
              onClick={async () => {
                try {
                  const response = await api.get(`/boletines/curso/${cursoId}/pdf`, { responseType: 'blob' });
                  const url = window.URL.createObjectURL(new Blob([response.data]));
                  const link = document.createElement('a');
                  link.href = url;
                  const cursoNombre = cursos.find(c => c.id === cursoId)?.nombre_completo || 'Curso';
                  link.setAttribute('download', `Boletines_MINERD_${cursoNombre.replace(/ /g, '_')}.pdf`);
                  document.body.appendChild(link);
                  link.click();
                  link.remove();
                } catch (err) {
                  console.error('Error:', err);
                  alert('Error al generar boletines del curso');
                }
              }}
            >
              📄 Descargar Boletines del Curso (PDF MINERD)
            </Button>
          </div>
        )}
      </div>

      {boletin && (
        <div className="bg-white rounded-xl shadow-sm border overflow-hidden">
          <div className="p-4 bg-gray-50 border-b flex justify-end gap-2 print:hidden">
            <Button onClick={() => window.print()} variant="secondary" icon={<Printer size={18} />}>Imprimir</Button>
            <Button 
              onClick={async () => {
                try {
                  const response = await api.get(`/boletines/estudiante/${estudianteId}/pdf`, {
                    responseType: 'blob'
                  });
                  // v2.13.9: validar que sí es PDF antes de descargar
                  if (response.data.type === 'application/json' || response.data.size < 500) {
                    const texto = await response.data.text();
                    try {
                      const json = JSON.parse(texto);
                      throw new Error(json.error || json.detail || 'Error en respuesta');
                    } catch (e: any) {
                      throw new Error(e?.message || 'El servidor no devolvió un PDF válido');
                    }
                  }
                  const url = window.URL.createObjectURL(new Blob([response.data]));
                  const link = document.createElement('a');
                  link.href = url;
                  link.setAttribute('download', `Boletin_${boletin.estudiante.nombre.replace(/ /g, '_')}.pdf`);
                  document.body.appendChild(link);
                  link.click();
                  link.remove();
                } catch (err: any) {
                  // v2.13.9: extraer mensaje real del blob si aplica
                  let mensajeError = err?.message || 'Error al descargar el PDF';
                  if (err?.response?.data instanceof Blob) {
                    try {
                      const texto = await err.response.data.text();
                      const json = JSON.parse(texto);
                      mensajeError = json.error || json.detail || texto;
                    } catch { /* no era JSON */ }
                  }
                  console.error('Error descargando PDF:', mensajeError);
                  alert(mensajeError);
                }
              }} 
              variant="primary" 
              icon={<Download size={18} />}
            >
              📥 Descargar PDF
            </Button>
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

            {/* Tabla MINERD */}
            <div className="overflow-x-auto">
              <table className="w-full text-xs border-collapse">
                <thead>
                  <tr className="bg-blue-900 text-white">
                    <th className="border border-blue-800 p-1.5 text-left" rowSpan={2}>Áreas Curriculares</th>
                    <th className="border border-blue-800 p-1 text-center" colSpan={4}>PC por Período</th>
                    <th className="border border-blue-800 p-1 text-center bg-yellow-700" rowSpan={2}>CF</th>
                    <th className="border border-blue-800 p-1 text-center bg-orange-700" colSpan={2}>Completiva</th>
                    <th className="border border-blue-800 p-1 text-center bg-green-800" colSpan={2}>Situación</th>
                  </tr>
                  <tr className="bg-blue-800 text-white text-[10px]">
                    <th className="border border-blue-700 p-1">PC1</th>
                    <th className="border border-blue-700 p-1">PC2</th>
                    <th className="border border-blue-700 p-1">PC3</th>
                    <th className="border border-blue-700 p-1">PC4</th>
                    <th className="border border-blue-700 p-1 bg-orange-600">RP</th>
                    <th className="border border-blue-700 p-1 bg-orange-600">CCF</th>
                    <th className="border border-blue-700 p-1 bg-green-700">A</th>
                    <th className="border border-blue-700 p-1 bg-red-700">R</th>
                  </tr>
                </thead>
                <tbody>
                  {boletin.asignaturas.map((asig, idx) => {
                    const aprobada = asig.cf !== null && asig.cf >= 70;
                    const reprobada = asig.cf !== null && asig.cf < 70;
                    const tieneRP = asig.rp1 || asig.rp2 || asig.rp3 || asig.rp4;
                    const rpMayor = Math.max(asig.rp1 || 0, asig.rp2 || 0, asig.rp3 || 0, asig.rp4 || 0) || null;
                    return (
                      <tr key={asig.asignatura_id || idx} className={idx % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                        <td className="border border-gray-300 p-1.5 font-medium bg-blue-50">{asig.asignatura}</td>
                        <td className={`border border-gray-300 p-1 text-center ${getNotaClass(asig.pc1)}`}>{asig.pc1?.toFixed(0) ?? ''}</td>
                        <td className={`border border-gray-300 p-1 text-center ${getNotaClass(asig.pc2)}`}>{asig.pc2?.toFixed(0) ?? ''}</td>
                        <td className={`border border-gray-300 p-1 text-center ${getNotaClass(asig.pc3)}`}>{asig.pc3?.toFixed(0) ?? ''}</td>
                        <td className={`border border-gray-300 p-1 text-center ${getNotaClass(asig.pc4)}`}>{asig.pc4?.toFixed(0) ?? ''}</td>
                        <td className={`border border-gray-300 p-1 text-center font-bold bg-yellow-50 ${getNotaClass(asig.cf)}`}>{asig.cf?.toFixed(0) ?? ''}</td>
                        <td className="border border-gray-300 p-1 text-center text-orange-600 bg-orange-50">{tieneRP ? rpMayor?.toFixed(0) : ''}</td>
                        <td className="border border-gray-300 p-1 text-center text-orange-600 bg-orange-50">{tieneRP && asig.cf ? Math.round((asig.cf * 0.5 + (rpMayor || 0) * 0.5)) : ''}</td>
                        <td className="border border-gray-300 p-1 text-center bg-green-50 font-bold text-green-700">{aprobada ? '✓' : ''}</td>
                        <td className="border border-gray-300 p-1 text-center bg-red-50 font-bold text-red-600">{reprobada ? '✗' : ''}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

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
              <div className={`rounded-lg p-3 text-center border ${boletin.promedio_general >= 70 ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'}`}>
                <p className="text-xs uppercase">Situación</p>
                <p className={`text-lg font-bold ${boletin.promedio_general >= 70 ? 'text-green-600' : 'text-red-600'}`}>
                  {boletin.promedio_general >= 70 ? '✓ APROBADO' : '✗ REPROBADO'}
                </p>
              </div>
            </div>

            {/* Leyenda */}
            <div className="mt-3 text-[10px] text-gray-500 border-t pt-2 grid grid-cols-2 gap-1">
              <p><strong>PC</strong> = Promedio Grupo Competencias Específicas</p>
              <p><strong>CF</strong> = Calificación Final del Área</p>
              <p><strong>RP</strong> = Recuperación Pedagógica</p>
              <p><strong>CCF</strong> = Calificación Completiva Final</p>
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
