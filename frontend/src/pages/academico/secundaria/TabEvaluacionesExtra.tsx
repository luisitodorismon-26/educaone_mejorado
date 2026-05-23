import { useState } from 'react';
import api from '../../../services/api';
import { AlertTriangle, Save, CheckCircle } from 'lucide-react';
import { Button, Alert } from '../../../components/ui';
import { EstudianteData } from './tipos';

// ════════════════════════════════════════════════════════════════════
// TAB EVALUACIONES EXTRA
// Estudiantes con CF < 70: cascada MINERD oficial.
// completiva (50% CF + 50% C.E.C.) →
// extraordinaria (30% CF + 70% C.E.EX) →
// especial (CF + C.E.)
// Solo se permite la fase pendiente (validado por backend).
// ════════════════════════════════════════════════════════════════════

interface Props {
  estudiantes: EstudianteData[];
  asignaturaId: number;
  puedeEditar: boolean;
  onReload: () => Promise<void>;
  onAbrirFicha?: (estudianteId: number) => void;
}

type DraftState = Record<number, string>;

export const TabEvaluacionesExtra: React.FC<Props> = ({ estudiantes, asignaturaId, puedeEditar, onReload, onAbrirFicha }) => {
  const [drafts, setDrafts] = useState<DraftState>({});
  const [savingId, setSavingId] = useState<number | null>(null);
  const [mensaje, setMensaje] = useState<{ tipo: 'success' | 'error' | 'warning'; texto: string } | null>(null);

  // Estudiantes con cascada pendiente
  const conPendiente = estudiantes.filter(
    e => e.evaluacion_extra?.fase_pendiente && !e.estudiante.retirado
  );

  // Estudiantes con cascada ya resuelta (para histórico/contexto)
  const conResuelta = estudiantes.filter(
    e => e.evaluacion_extra && !e.evaluacion_extra.fase_pendiente && !e.estudiante.retirado
  );

  const guardarExtra = async (estId: number, fase: 'completiva' | 'extraordinaria' | 'especial') => {
    const valorStr = drafts[estId];
    if (!valorStr) {
      setMensaje({ tipo: 'error', texto: 'Indique la nota para la evaluación extra' });
      return;
    }
    const notaNum = parseFloat(valorStr);
    if (Number.isNaN(notaNum) || notaNum < 0 || notaNum > 100) {
      setMensaje({ tipo: 'error', texto: 'La nota debe estar entre 0 y 100' });
      return;
    }
    setSavingId(estId);
    try {
      await api.post('/calificaciones-secundaria/evaluacion-extra', {
        estudiante_id: estId,
        asignatura_id: asignaturaId,
        tipo: fase,
        nota: notaNum,
      });
      setMensaje({ tipo: 'success', texto: `Evaluación ${fase} registrada` });
      setDrafts(prev => {
        const next = { ...prev };
        delete next[estId];
        return next;
      });
      await onReload();
    } catch (err: any) {
      setMensaje({ tipo: 'error', texto: err.response?.data?.error || 'Error al guardar evaluación extra' });
    } finally {
      setSavingId(null);
    }
  };

  if (conPendiente.length === 0 && conResuelta.length === 0) {
    return (
      <div className="bg-white rounded-xl shadow-sm border p-10 text-center">
        <CheckCircle size={48} className="mx-auto text-green-300 mb-3" />
        <p className="text-gray-700 font-medium">No hay evaluaciones extra en esta materia</p>
        <p className="text-sm text-gray-500 mt-1">
          Aparecerá aquí cuando un estudiante tenga CF &lt; 70 después de cargar las 4 competencias.
        </p>
      </div>
    );
  }

  const renderNombre = (e: EstudianteData) => onAbrirFicha ? (
    <button
      type="button"
      onClick={() => onAbrirFicha(e.estudiante.id)}
      className="font-medium text-blue-700 hover:text-blue-900 hover:underline"
    >
      {e.estudiante.nombre_completo}
    </button>
  ) : (
    <span className="font-medium">{e.estudiante.nombre_completo}</span>
  );

  return (
    <div className="space-y-4">
      {mensaje && <Alert variant={mensaje.tipo} onClose={() => setMensaje(null)}>{mensaje.texto}</Alert>}

      {/* Pendientes */}
      {conPendiente.length > 0 && (
        <div className="bg-white rounded-xl shadow-sm border p-4">
          <h3 className="font-bold text-lg mb-2 flex items-center gap-2">
            <AlertTriangle className="text-amber-600" />
            Pendientes ({conPendiente.length})
          </h3>
          <p className="text-xs text-gray-500 mb-3">
            Cascada estricta MINERD: completiva → extraordinaria → especial. Solo se permite la fase pendiente.
          </p>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="bg-gray-50">
                  <th className="px-3 py-2 text-left">Estudiante</th>
                  <th className="px-3 py-2 text-center">CF</th>
                  <th className="px-3 py-2 text-center">Fase</th>
                  <th className="px-3 py-2 text-center">C.E.C.</th>
                  <th className="px-3 py-2 text-center">Comp.</th>
                  <th className="px-3 py-2 text-center">C.E.EX</th>
                  <th className="px-3 py-2 text-center">Extra.</th>
                  <th className="px-3 py-2 text-center">C.E.</th>
                  <th className="px-3 py-2 text-center">Esp.</th>
                  {puedeEditar && <th className="px-3 py-2 text-center">Cargar</th>}
                </tr>
              </thead>
              <tbody>
                {conPendiente.map(est => {
                  const ev = est.evaluacion_extra!;
                  const fase = ev.fase_pendiente!;
                  return (
                    <tr key={est.estudiante.id} className="border-b">
                      <td className="px-3 py-2">{renderNombre(est)}</td>
                      <td className="px-3 py-2 text-center text-red-600 font-bold">{ev.cf_original?.toFixed(0) ?? '—'}</td>
                      <td className="px-3 py-2 text-center">
                        <span className="px-2 py-1 rounded-full text-xs font-medium bg-amber-100 text-amber-800 uppercase">
                          {fase}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-center">{ev.cec?.toFixed(0) ?? '—'}</td>
                      <td className="px-3 py-2 text-center font-bold">{ev.completiva_final?.toFixed(0) ?? '—'}</td>
                      <td className="px-3 py-2 text-center">{ev.ceex?.toFixed(0) ?? '—'}</td>
                      <td className="px-3 py-2 text-center font-bold">{ev.extraordinaria_final?.toFixed(0) ?? '—'}</td>
                      <td className="px-3 py-2 text-center">{ev.ce?.toFixed(0) ?? '—'}</td>
                      <td className="px-3 py-2 text-center font-bold">{ev.especial_final?.toFixed(0) ?? '—'}</td>
                      {puedeEditar && (
                        <td className="px-3 py-2">
                          <div className="flex gap-1 items-center justify-center">
                            <input
                              type="number"
                              min={0}
                              max={100}
                              step={0.01}
                              placeholder={`Nota ${fase}`}
                              value={drafts[est.estudiante.id] || ''}
                              onChange={e => setDrafts(prev => ({ ...prev, [est.estudiante.id]: e.target.value }))}
                              className="w-20 px-2 py-1 text-center border rounded text-sm"
                            />
                            <Button
                              variant="success"
                              size="sm"
                              loading={savingId === est.estudiante.id}
                              onClick={() => guardarExtra(est.estudiante.id, fase)}
                              icon={<Save size={14} />}
                            >
                              Guardar
                            </Button>
                          </div>
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Resueltas (histórico) */}
      {conResuelta.length > 0 && (
        <div className="bg-white rounded-xl shadow-sm border p-4">
          <h3 className="font-bold text-lg mb-3 flex items-center gap-2 text-gray-600">
            <CheckCircle className="text-gray-400" />
            Resueltas ({conResuelta.length})
          </h3>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="bg-gray-50">
                  <th className="px-3 py-2 text-left">Estudiante</th>
                  <th className="px-3 py-2 text-center">CF original</th>
                  <th className="px-3 py-2 text-center">Nota final</th>
                  <th className="px-3 py-2 text-center">Condición</th>
                </tr>
              </thead>
              <tbody>
                {conResuelta.map(est => {
                  const ev = est.evaluacion_extra!;
                  const aprobado = (ev.nota_final ?? 0) >= 70;
                  return (
                    <tr key={est.estudiante.id} className="border-b">
                      <td className="px-3 py-2">{renderNombre(est)}</td>
                      <td className="px-3 py-2 text-center text-red-600">{ev.cf_original?.toFixed(0) ?? '—'}</td>
                      <td className={`px-3 py-2 text-center font-bold ${aprobado ? 'text-green-600' : 'text-red-600'}`}>
                        {ev.nota_final?.toFixed(0) ?? '—'}
                      </td>
                      <td className="px-3 py-2 text-center">
                        <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                          aprobado ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                        }`}>
                          {ev.condicion_final?.replace(/_/g, ' ') ?? '—'}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
