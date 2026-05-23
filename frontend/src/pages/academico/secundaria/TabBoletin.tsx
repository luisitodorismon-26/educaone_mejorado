import { useState } from 'react';
import api from '../../../services/api';
import { FileText, Download, FileStack, AlertCircle } from 'lucide-react';
import { Button, Alert } from '../../../components/ui';
import { EstudianteData } from './tipos';

// ════════════════════════════════════════════════════════════════════
// TAB VER BOLETÍN
// Acceso rápido al PDF MINERD pixel-exacto desde la misma pantalla.
// Dos modos:
//   1. Boletín individual de un estudiante (PDF de 2 páginas)
//   2. Todos los boletines del curso combinados (PDF de N×2 páginas)
// ════════════════════════════════════════════════════════════════════

interface Props {
  estudiantes: EstudianteData[];
  cursoId: number;
  nombreCurso: string;
}

export const TabBoletin: React.FC<Props> = ({ estudiantes, cursoId, nombreCurso }) => {
  const [generandoId, setGenerandoId] = useState<number | null>(null);
  const [generandoCurso, setGenerandoCurso] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // v2.13.9: helper que extrae el mensaje de error real cuando el response es blob.
  // Sin esto, los errores 400/500 del backend se mostraban como "Error generando
  // boletín" genérico porque axios trataba el blob como Blob sin parsear JSON.
  const extraerErrorDeBlob = async (err: any): Promise<string> => {
    const blob = err?.response?.data;
    if (blob instanceof Blob) {
      try {
        const texto = await blob.text();
        const json = JSON.parse(texto);
        return json.error || json.detail || texto;
      } catch {
        // No era JSON
        return 'Error generando boletín. Verificá que el estudiante tenga las 4 competencias completas.';
      }
    }
    return err?.response?.data?.error || err?.message || 'Error generando boletín';
  };

  const descargarPDF = async (url: string, nombre: string) => {
    const res = await api.get(url, { responseType: 'blob' });
    // v2.13.9: verificar que sí es PDF antes de descargar (puede venir error como blob)
    if (res.data.type === 'application/json' || res.data.size < 500) {
      const texto = await res.data.text();
      try {
        const json = JSON.parse(texto);
        throw new Error(json.error || json.detail || 'Error en la respuesta');
      } catch (e: any) {
        throw new Error(e?.message || 'El servidor no devolvió un PDF válido');
      }
    }
    const blob = new Blob([res.data], { type: 'application/pdf' });
    const link = document.createElement('a');
    link.href = window.URL.createObjectURL(blob);
    link.download = nombre;
    link.click();
    window.URL.revokeObjectURL(link.href);
  };

  const generarIndividual = async (estId: number, nombre: string) => {
    setGenerandoId(estId);
    setError(null);
    try {
      await descargarPDF(
        `/boletines/estudiante/${estId}/pdf-minerd-v2`,
        `Boletin_${nombre.replace(/\s+/g, '_')}.pdf`
      );
    } catch (err: any) {
      // v2.13.9: extraer mensaje real del blob si aplica
      const mensaje = await extraerErrorDeBlob(err);
      setError(mensaje);
    } finally {
      setGenerandoId(null);
    }
  };

  const generarCurso = async () => {
    setGenerandoCurso(true);
    setError(null);
    try {
      await descargarPDF(
        `/boletines/curso/${cursoId}/pdf-minerd-v2`,
        `Boletines_${nombreCurso.replace(/\s+/g, '_')}.pdf`
      );
    } catch (err: any) {
      const mensaje = await extraerErrorDeBlob(err);
      setError(mensaje);
    } finally {
      setGenerandoCurso(false);
    }
  };

  const conNotas = estudiantes.filter(e => e.cf !== null && !e.estudiante.retirado);

  return (
    <div className="space-y-4">
      {error && <Alert variant="error" onClose={() => setError(null)}>{error}</Alert>}

      {/* Generación masiva */}
      <div className="bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-xl p-5">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div className="flex items-start gap-3">
            <FileStack className="text-blue-600 mt-1" size={28} />
            <div>
              <h3 className="font-bold text-blue-900">Boletines del curso completo</h3>
              <p className="text-sm text-blue-700 mt-1">
                Genera un PDF único con los boletines MINERD de los {conNotas.length} estudiantes con notas cargadas.
              </p>
            </div>
          </div>
          <Button
            variant="primary"
            loading={generandoCurso}
            disabled={conNotas.length === 0}
            onClick={generarCurso}
            icon={<Download size={16} />}
          >
            Descargar todos
          </Button>
        </div>
      </div>

      {/* Lista de estudiantes con botón individual */}
      {estudiantes.length === 0 ? (
        <div className="bg-white rounded-xl shadow-sm border p-10 text-center">
          <FileText size={48} className="mx-auto text-gray-300 mb-3" />
          <p className="text-gray-500">No hay estudiantes en este curso</p>
        </div>
      ) : (
        <div className="bg-white rounded-xl shadow-sm border overflow-hidden">
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="bg-gray-50">
                  <th className="px-3 py-2 text-left font-medium text-gray-600">No.</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Estudiante</th>
                  <th className="px-3 py-2 text-center font-medium text-gray-600">CF</th>
                  <th className="px-3 py-2 text-center font-medium text-gray-600">Estado</th>
                  <th className="px-3 py-2 text-center font-medium text-gray-600">Boletín</th>
                </tr>
              </thead>
              <tbody>
                {estudiantes.map((est, idx) => {
                  const esRetirado = !!est.estudiante.retirado;
                  const tieneCF = est.cf !== null;
                  const aprobado = tieneCF && est.cf! >= 70;
                  return (
                    <tr key={est.estudiante.id} className={`border-b ${esRetirado ? 'bg-gray-50' : 'hover:bg-gray-50'}`}>
                      <td className={`px-3 py-2 ${esRetirado ? 'text-gray-400 line-through' : 'text-gray-500'}`}>{idx + 1}</td>
                      <td className="px-3 py-2">
                        <span className={`font-medium ${esRetirado ? 'text-gray-400 line-through' : ''}`}>
                          {est.estudiante.nombre_completo}
                        </span>
                      </td>
                      <td className={`px-3 py-2 text-center font-bold ${
                        esRetirado ? 'text-gray-400' :
                        !tieneCF ? 'text-gray-300' :
                        aprobado ? 'text-green-600' : 'text-red-600'
                      }`}>
                        {tieneCF ? est.cf!.toFixed(0) : '—'}
                      </td>
                      <td className="px-3 py-2 text-center">
                        {esRetirado ? (
                          <span className="px-2 py-1 rounded-full text-xs bg-gray-200 text-gray-600">Retirado</span>
                        ) : !tieneCF ? (
                          <span className="px-2 py-1 rounded-full text-xs bg-gray-100 text-gray-500">Sin notas</span>
                        ) : (
                          <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                            aprobado ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                          }`}>
                            {aprobado ? 'Aprobado' : 'Pendiente'}
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-center">
                        <Button
                          variant="secondary"
                          size="sm"
                          loading={generandoId === est.estudiante.id}
                          disabled={esRetirado || !tieneCF}
                          onClick={() => generarIndividual(est.estudiante.id, est.estudiante.nombre_completo)}
                          icon={<Download size={14} />}
                        >
                          PDF
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Nota informativa */}
      <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 flex items-start gap-2">
        <AlertCircle size={16} className="text-amber-600 mt-0.5 flex-shrink-0" />
        <p className="text-xs text-amber-800">
          El boletín se genera con las notas que TENGAS cargadas actualmente. Si un estudiante no tiene CF (las 4 competencias completas),
          el botón quedará deshabilitado. Asegúrate de tener todas las materias cargadas antes de imprimir oficialmente.
        </p>
      </div>
    </div>
  );
};
