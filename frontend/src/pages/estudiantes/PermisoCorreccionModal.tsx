import { useEffect, useState } from 'react';
import api from '../../services/api';
import { Modal, Button, Alert } from '../../components/ui';

/**
 * ENT-A · Permiso temporal de corrección para completar o corregir notas de
 * un estudiante RETIRADO sin reactivarlo.
 *
 * Usa el permiso temporal existente de Dirección (POST /periodos/permiso-temporal),
 * siempre acotado al CURSO del estudiante, a una asignatura y a un período. Quien
 * decide qué casillas se pueden escribir es el servidor; esta pantalla solo pide
 * el permiso. Consultar o imprimir sus boletines no lo necesita.
 */
interface Props {
  estudiante: { id: number; nombre_completo: string; curso_id: number; curso: string } | null;
  onClose: () => void;
}

interface FilaAsignacion { asignatura_id: number; asignatura: string; profesor_id: number | null; profesor: string | null; }

export const PermisoCorreccionModal = ({ estudiante, onClose }: Props) => {
  const [filas, setFilas] = useState<FilaAsignacion[]>([]);
  const [asignaturaId, setAsignaturaId] = useState<number>(0);
  const [periodo, setPeriodo] = useState<number>(1);
  const [horas, setHoras] = useState<number>(24);
  const [motivo, setMotivo] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [resultado, setResultado] = useState<{ tipo: 'success' | 'error'; texto: string } | null>(null);

  useEffect(() => {
    setFilas([]); setAsignaturaId(0); setResultado(null); setMotivo('');
    if (!estudiante?.curso_id) return;
    api.get(`/cursos/${estudiante.curso_id}/asignaciones`)
      .then(r => setFilas((r.data?.asignaciones || []).filter((f: FilaAsignacion) => f.profesor_id)))
      .catch(() => setResultado({ tipo: 'error', texto: 'No se pudieron cargar las asignaturas del curso.' }));
  }, [estudiante?.id]);

  const fila = filas.find(f => f.asignatura_id === asignaturaId);

  const conceder = async () => {
    if (!estudiante || !fila || !motivo.trim()) return;
    setEnviando(true);
    setResultado(null);
    try {
      const r = await api.post('/periodos/permiso-temporal', {
        profesor_id: fila.profesor_id,
        curso_id: estudiante.curso_id,
        asignatura_id: fila.asignatura_id,
        periodo,
        horas,
        motivo: `${motivo.trim()} — ${estudiante.nombre_completo} (retirado)`,
      });
      setResultado({ tipo: 'success', texto: `${r.data?.message || 'Permiso otorgado'}. ${fila.profesor} podrá completar o corregir P${periodo} de ${fila.asignatura} en ${estudiante.curso}. El estudiante sigue retirado.` });
    } catch (e: any) {
      setResultado({ tipo: 'error', texto: e?.response?.data?.error || 'No se pudo conceder el permiso.' });
    } finally {
      setEnviando(false);
    }
  };

  return (
    <Modal isOpen={!!estudiante} onClose={onClose} title="Permiso de corrección de notas" size="md"
           footer={
             <div className="flex justify-end gap-2">
               <Button variant="secondary" onClick={onClose}>Cerrar</Button>
               <Button onClick={conceder} loading={enviando} disabled={!fila || !motivo.trim()}>Conceder permiso</Button>
             </div>
           }>
      {estudiante && (
        <div className="space-y-3 text-sm">
          <p>
            <strong>{estudiante.nombre_completo}</strong> · {estudiante.curso}. El estudiante <strong>sigue retirado</strong>:
            el permiso solo deja al docente completar o corregir las notas de esa asignatura y período, en este curso.
            Para ver o imprimir sus boletines no hace falta ningún permiso.
          </p>
          {resultado && <Alert variant={resultado.tipo}>{resultado.texto}</Alert>}
          <label className="block">
            <span className="text-gray-700">Asignatura (docente asignado)</span>
            <select value={asignaturaId} onChange={e => setAsignaturaId(Number(e.target.value))}
                    className="mt-1 w-full px-3 py-2 border rounded-lg">
              <option value={0}>— Seleccione —</option>
              {filas.map(f => <option key={f.asignatura_id} value={f.asignatura_id}>{f.asignatura} — {f.profesor}</option>)}
            </select>
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="text-gray-700">Período</span>
              <select value={periodo} onChange={e => setPeriodo(Number(e.target.value))} className="mt-1 w-full px-3 py-2 border rounded-lg">
                {[1, 2, 3, 4].map(p => <option key={p} value={p}>P{p}</option>)}
              </select>
            </label>
            <label className="block">
              <span className="text-gray-700">Vigencia</span>
              <select value={horas} onChange={e => setHoras(Number(e.target.value))} className="mt-1 w-full px-3 py-2 border rounded-lg">
                {[24, 48, 72].map(h => <option key={h} value={h}>{h} horas</option>)}
              </select>
            </label>
          </div>
          <label className="block">
            <span className="text-gray-700">Motivo</span>
            <input value={motivo} onChange={e => setMotivo(e.target.value)} placeholder="Ej.: completar la nota faltante para el boletín"
                   className="mt-1 w-full px-3 py-2 border rounded-lg" />
          </label>
        </div>
      )}
    </Modal>
  );
};

export default PermisoCorreccionModal;
