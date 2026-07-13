import { useState, useEffect } from 'react';
import api from '../../services/api';
import { AlertTriangle, Save, CheckCircle, RefreshCw, Backpack } from 'lucide-react';
import { Button, Alert, Spinner } from '../../components/ui';
import { useAuth } from '../../context/AuthContext';

// ═══════════════════════════════════════════════════════════════
// RECUPERACIONES DE PRIMARIA — v2.13.50
// CARRIL SEPARADO de las Evaluaciones Extra de secundaria.
// Reglas: corte 65. La recuperación es COMPLEMENTARIA (se SUMA a la
// CF del área, máx = 100 - CF). Final → si sigue <65 → Especial.
// ═══════════════════════════════════════════════════════════════

interface Recuperacion {
  estudiante_id: number;
  estudiante_nombre: string;
  curso: string;
  asignatura_id: number;
  asignatura_nombre: string;
  cf_area: number | null;
  maximo_puntos: number | null;
  puntos_final: number | null;
  recuperacion_final: number | null;
  puntos_especial: number | null;
  recuperacion_especial: number | null;
  nota_final: number | null;
  condicion_final: string | null;
  fase_pendiente: 'final' | 'especial' | null;
}

export const RecuperacionesPrimariaPage: React.FC = () => {
  const { user } = useAuth();
  const puedeEditar = user?.role === 'profesor';

  const [pendientes, setPendientes] = useState<Recuperacion[]>([]);
  const [resueltas, setResueltas] = useState<Recuperacion[]>([]);
  const [minimo, setMinimo] = useState(65);
  const [loading, setLoading] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [mensaje, setMensaje] = useState<{ tipo: 'success' | 'error'; texto: string } | null>(null);

  const keyDe = (r: Recuperacion) => `${r.estudiante_id}-${r.asignatura_id}`;

  const cargar = async () => {
    setLoading(true);
    try {
      const res = await api.get('/recuperaciones-primaria/pendientes');
      setPendientes(res.data.pendientes || []);
      setResueltas(res.data.resueltas || []);
      setMinimo(res.data.minimo || 65);
    } catch (e: any) {
      setMensaje({ tipo: 'error', texto: e.response?.data?.error || 'Error al cargar las recuperaciones' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { cargar(); }, []);

  const guardar = async (r: Recuperacion) => {
    const k = keyDe(r);
    const valor = drafts[k];
    if (!valor) {
      setMensaje({ tipo: 'error', texto: 'Indique los puntos de la recuperación' });
      return;
    }
    setSavingKey(k);
    setMensaje(null);
    try {
      const res = await api.post('/recuperaciones-primaria', {
        estudiante_id: r.estudiante_id,
        asignatura_id: r.asignatura_id,
        tipo: r.fase_pendiente,
        puntos: parseFloat(valor),
      });
      setMensaje({
        tipo: 'success',
        texto: `${r.estudiante_nombre} — ${r.asignatura_nombre}: nota final ${Math.round(res.data.nota_final)} (${res.data.aprobado ? 'aprobado' : 'reprobado'})`,
      });
      setDrafts(prev => { const n = { ...prev }; delete n[k]; return n; });
      await cargar();
    } catch (e: any) {
      setMensaje({ tipo: 'error', texto: e.response?.data?.error || 'Error al guardar' });
    } finally {
      setSavingKey(null);
    }
  };

  const fmt = (v: number | null | undefined) => (v == null ? '—' : Math.round(v).toString());

  const Encabezado = ({ conAccion }: { conAccion: boolean }) => (
    <thead>
      <tr className="text-xs">
        <th rowSpan={2} className="px-2 py-1 text-left bg-gray-50 border">Estudiante</th>
        <th rowSpan={2} className="px-2 py-1 text-left bg-gray-50 border">Curso</th>
        <th rowSpan={2} className="px-2 py-1 text-left bg-gray-50 border">Área</th>
        <th rowSpan={2} className="px-2 py-1 text-center bg-gray-100 border font-bold">C.F.<br />del área</th>
        <th colSpan={2} className="px-2 py-1 text-center bg-amber-50 text-amber-800 border font-bold">RECUPERACIÓN FINAL</th>
        <th colSpan={2} className="px-2 py-1 text-center bg-red-50 text-red-800 border font-bold">RECUPERACIÓN ESPECIAL</th>
        <th rowSpan={2} className="px-2 py-1 text-center bg-gray-50 border">Situación</th>
        {conAccion && <th rowSpan={2} className="px-2 py-1 text-center bg-gray-50 border">Cargar</th>}
      </tr>
      <tr className="text-[11px] text-gray-600">
        <th className="px-1 py-1 text-center bg-amber-50 border">Puntos</th>
        <th className="px-1 py-1 text-center bg-amber-100 border font-bold">Resultado</th>
        <th className="px-1 py-1 text-center bg-red-50 border">Puntos</th>
        <th className="px-1 py-1 text-center bg-red-100 border font-bold">Resultado</th>
      </tr>
    </thead>
  );

  const Fila = ({ r, editable }: { r: Recuperacion; editable: boolean }) => {
    const k = keyDe(r);
    const draft = drafts[k] || '';
    const draftNum = draft !== '' ? parseFloat(draft) : null;
    const cf = r.cf_area != null ? Math.round(r.cf_area) : null;
    const esPreview = draftNum != null && !Number.isNaN(draftNum);
    const previewFinal = esPreview && cf != null ? cf + draftNum! : null;

    const situacion = () => {
      if (r.fase_pendiente) {
        return (
          <span className="px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-100 text-amber-800 uppercase whitespace-nowrap">
            {r.fase_pendiente === 'final' ? 'recuperación final' : 'rec. especial'} pendiente
          </span>
        );
      }
      const aprobado = (r.nota_final ?? 0) >= minimo;
      return (
        <span className={`px-2 py-0.5 rounded-full text-[11px] font-medium whitespace-nowrap ${aprobado ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
          {(r.condicion_final || '').replace(/_/g, ' ')} {r.nota_final != null ? `(${fmt(r.nota_final)})` : ''}
        </span>
      );
    };

    const celdaResultado = (fase: 'final' | 'especial', guardado: number | null) => {
      if (r.fase_pendiente === fase && esPreview) {
        return <span className="text-blue-700 font-bold italic">{previewFinal}*</span>;
      }
      return <span className="font-bold">{fmt(guardado)}</span>;
    };

    return (
      <tr className="border-b hover:bg-gray-50 text-sm">
        <td className="px-2 py-1 border font-medium text-gray-800">{r.estudiante_nombre}</td>
        <td className="px-2 py-1 border text-gray-600">{r.curso}</td>
        <td className="px-2 py-1 border text-gray-700">{r.asignatura_nombre}</td>
        <td className="px-2 py-1 border text-center font-bold text-red-600">{fmt(r.cf_area)}</td>
        {/* Recuperación final */}
        <td className="px-1 py-1 border text-center bg-amber-50/40">
          {editable && r.fase_pendiente === 'final' ? (
            <input
              type="number" min={0} max={r.maximo_puntos ?? 100}
              placeholder={`máx ${r.maximo_puntos ?? ''}`}
              value={draft}
              onChange={e => setDrafts(p => ({ ...p, [k]: e.target.value }))}
              title={`Puntos complementarios: se SUMAN al C.F. (${cf}). Máximo ${r.maximo_puntos}.`}
              className="w-20 px-1 py-1 text-center border-2 border-blue-400 rounded text-sm bg-blue-50 font-bold"
            />
          ) : fmt(r.puntos_final)}
        </td>
        <td className="px-1 py-1 border text-center bg-amber-100/50">{celdaResultado('final', r.recuperacion_final)}</td>
        {/* Recuperación especial */}
        <td className="px-1 py-1 border text-center bg-red-50/40">
          {editable && r.fase_pendiente === 'especial' ? (
            <input
              type="number" min={0} max={r.maximo_puntos ?? 100}
              placeholder={`máx ${r.maximo_puntos ?? ''}`}
              value={draft}
              onChange={e => setDrafts(p => ({ ...p, [k]: e.target.value }))}
              title={`Puntos complementarios: se SUMAN al C.F. (${cf}). Máximo ${r.maximo_puntos}.`}
              className="w-20 px-1 py-1 text-center border-2 border-blue-400 rounded text-sm bg-blue-50 font-bold"
            />
          ) : fmt(r.puntos_especial)}
        </td>
        <td className="px-1 py-1 border text-center bg-red-100/50">{celdaResultado('especial', r.recuperacion_especial)}</td>
        <td className="px-2 py-1 border text-center">{situacion()}</td>
        {editable && (
          <td className="px-2 py-1 border text-center">
            {r.fase_pendiente && (
              <Button
                variant="success"
                size="sm"
                loading={savingKey === k}
                onClick={() => guardar(r)}
                icon={<Save size={13} />}
              >
                Guardar
              </Button>
            )}
          </td>
        )}
      </tr>
    );
  };

  if (loading) return <div className="flex justify-center py-10"><Spinner /></div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <AlertTriangle className="text-amber-500" />
            Recuperaciones
            <span className="inline-flex items-center gap-1 bg-blue-100 text-blue-700 text-xs font-semibold px-2.5 py-1 rounded-full">
              <Backpack size={13} /> PRIMARIA
            </span>
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Áreas con calificación final menor de {minimo}. La recuperación es <strong>complementaria</strong>: los puntos se
            <strong> suman</strong> a la C.F. del área (máximo hasta llegar a 100). Se aprueba con {minimo}.
          </p>
        </div>
        <Button variant="secondary" onClick={cargar} icon={<RefreshCw size={16} />}>Refrescar</Button>
      </div>

      {mensaje && <Alert variant={mensaje.tipo} onClose={() => setMensaje(null)}>{mensaje.texto}</Alert>}

      {pendientes.length === 0 && resueltas.length === 0 && (
        <div className="bg-white rounded-xl shadow-sm border p-10 text-center">
          <CheckCircle size={48} className="mx-auto text-green-300 mb-3" />
          <p className="text-gray-700 font-medium">No hay áreas en recuperación</p>
          <p className="text-sm text-gray-500 mt-1">
            Aparecerán aquí automáticamente cuando un área tenga C.F. menor de {minimo}.
          </p>
        </div>
      )}

      {pendientes.length > 0 && (
        <div className="bg-white rounded-xl shadow-sm border p-4">
          <h3 className="font-bold text-lg mb-1 flex items-center gap-2">
            <AlertTriangle className="text-amber-600" size={20} />
            Pendientes ({pendientes.length})
          </h3>
          <p className="text-xs text-gray-500 mb-3">
            Escriba los puntos en la casilla azul — el resultado se calcula en vivo (valor con *) antes de guardar.
            Si tras la recuperación final el área sigue por debajo de {minimo}, pasa a recuperación especial.
          </p>
          <div className="overflow-x-auto">
            <table className="min-w-full border-collapse">
              <Encabezado conAccion={puedeEditar} />
              <tbody>
                {pendientes.map(r => <Fila key={keyDe(r)} r={r} editable={puedeEditar} />)}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {resueltas.length > 0 && (
        <div className="bg-white rounded-xl shadow-sm border p-4">
          <h3 className="font-bold text-lg mb-1 flex items-center gap-2 text-gray-600">
            <CheckCircle className="text-gray-400" size={20} />
            Resueltas ({resueltas.length})
          </h3>
          <div className="overflow-x-auto">
            <table className="min-w-full border-collapse">
              <Encabezado conAccion={false} />
              <tbody>
                {resueltas.map(r => <Fila key={keyDe(r)} r={r} editable={false} />)}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
