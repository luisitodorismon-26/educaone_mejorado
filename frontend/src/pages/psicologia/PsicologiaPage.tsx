import { useState, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';
import { Brain, AlertCircle, Eye, Clock, CheckCircle, MessageSquare } from 'lucide-react';
import { Modal, Button, Select, Textarea, Alert, Spinner } from '../../components/ui';

interface Caso {
  id: number;
  estudiante: string;
  estudiante_id: number;
  tipo: string;
  urgencia: string;
  motivo: string;
  estado: string;
  solicitante: string;
  solicitante_id: number;
  psicologo: string | null;
  fecha_solicitud: string;
  notas_atencion: string | null;
  recomendacion_profesor: string | null;
  diagnostico: string | null;
  fecha_actualizacion: string | null;
}

interface Estudiante {
  id: number;
  nombre_completo: string;
  curso?: string;
}

export const PsicologiaPage = () => {
  const { user } = useAuth();
  const [casos, setCasos] = useState<Caso[]>([]);
  const [estudiantes, setEstudiantes] = useState<Estudiante[]>([]);
  const [showModal, setShowModal] = useState(false);
  const [showDetalleModal, setShowDetalleModal] = useState(false);
  const [form, setForm] = useState({ estudiante_id: 0, tipo: 'emocional', urgencia: 'normal', motivo: '', curso_filter: '' });
  const [selected, setSelected] = useState<Caso | null>(null);
  const [loading, setLoading] = useState(true);
  const [notasForm, setNotasForm] = useState({ notas_atencion: '', recomendacion_profesor: '', estado: '' });
  const [message, setMessage] = useState<{type: 'success' | 'error'; text: string} | null>(null);
  const [filtroCurso, setFiltroCurso] = useState('');
  const [filtroEstado, setFiltroEstado] = useState('');
  const [cursos, setCursos] = useState<any[]>([]);

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    try {
      const [c, cur] = await Promise.all([
        api.get('/psicologia/casos'),
        api.get('/cursos')
      ]);
      setCasos(c.data || []);
      setCursos(cur.data || []);
      
      // Cargar estudiantes si el usuario puede solicitar
      if (user?.role === 'profesor' || user?.role === 'coordinador' || user?.role === 'direccion' || user?.role === 'psicologia') {
        const e = await api.get('/estudiantes');
        setEstudiantes(e.data || []);
      }
    } catch (err) {
      console.error('Error cargando datos:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleSolicitar = async () => {
    if (!form.estudiante_id || !form.motivo) {
      setMessage({ type: 'error', text: 'Complete todos los campos' });
      return;
    }
    try {
      await api.post('/psicologia/solicitar', form);
      loadData();
      setShowModal(false);
      setForm({ estudiante_id: 0, tipo: 'emocional', urgencia: 'normal', motivo: '', curso_filter: '' });
      setMessage({ type: 'success', text: 'Solicitud enviada correctamente' });
    } catch (err: any) {
      setMessage({ type: 'error', text: err.response?.data?.error || 'Error al enviar solicitud' });
    }
  };

  const handleTomar = async (id: number) => {
    try {
      await api.post(`/psicologia/casos/${id}/tomar`);
      loadData();
    } catch (err) {
      console.error('Error tomando caso:', err);
    }
  };

  const handleActualizarCaso = async () => {
    if (!selected) return;
    try {
      await api.post(`/psicologia/casos/${selected.id}/actualizar`, notasForm);
      loadData();
      setShowDetalleModal(false);
      setSelected(null);
      setMessage({ type: 'success', text: 'Caso actualizado' });
    } catch (err) {
      setMessage({ type: 'error', text: 'Error al actualizar caso' });
    }
  };

  const openDetalle = (caso: Caso) => {
    setSelected(caso);
    setNotasForm({
      notas_atencion: caso.notas_atencion || '',
      recomendacion_profesor: caso.recomendacion_profesor || '',
      estado: caso.estado
    });
    setShowDetalleModal(true);
  };

  const formatFecha = (fecha: string) => {
    return new Date(fecha).toLocaleDateString('es-DO', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: true
    });
  };

  // Permisos
  const isPsico = user?.role === 'psicologia';
  const isReadOnly = user?.role === 'direccion' && !isPsico;
  const canSolicitar = user?.role === 'profesor' || user?.role === 'coordinador' || user?.role === 'direccion';
  const canAtender = isPsico;

  const getEstadoColor = (e: string) => {
    if (e === 'pendiente') return 'bg-amber-100 text-amber-700 border-amber-200';
    if (e === 'en_proceso') return 'bg-blue-100 text-blue-700 border-blue-200';
    if (e === 'atendido') return 'bg-emerald-100 text-emerald-700 border-emerald-200';
    return 'bg-slate-100 text-slate-700';
  };

  const getEstadoIcon = (e: string) => {
    if (e === 'pendiente') return <Clock size={14} />;
    if (e === 'en_proceso') return <Brain size={14} />;
    if (e === 'atendido') return <CheckCircle size={14} />;
    return null;
  };

  if (loading) return <div className="flex justify-center py-12"><Spinner size="lg" /></div>;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div className="flex items-center gap-2">
          <Brain className="text-purple-600" size={28} />
          <div>
            <h1 className="text-2xl font-bold text-slate-800">Psicología</h1>
            {isReadOnly && !isPsico && (
              <p className="text-xs text-amber-600 flex items-center gap-1">
                <Eye size={12} /> Modo solo lectura
              </p>
            )}
          </div>
        </div>
        {canSolicitar && (
          <Button onClick={() => setShowModal(true)} className="bg-purple-600 hover:bg-purple-700">
            + Solicitar Atención
          </Button>
        )}
      </div>

      {message && (
        <Alert variant={message.type} onClose={() => setMessage(null)}>{message.text}</Alert>
      )}

      {/* Aviso para dirección */}
      {isReadOnly && !isPsico && (
        <div className="bg-amber-50 border border-amber-200 p-4 rounded-xl flex items-start gap-3">
          <AlertCircle className="text-amber-500 shrink-0" size={20} />
          <div>
            <p className="text-sm font-medium text-amber-800">Vista de supervisión</p>
            <p className="text-xs text-amber-700">Puede ver los casos para supervisión, pero solo el departamento de psicología puede modificarlos.</p>
          </div>
        </div>
      )}

      {/* Stats para psicología */}
      {isPsico && (
        <div className="grid grid-cols-3 gap-4">
          <div className="bg-amber-50 p-4 rounded-lg border border-amber-200">
            <p className="text-2xl font-bold text-amber-700">{casos.filter(c => c.estado === 'pendiente').length}</p>
            <p className="text-sm text-amber-600">Pendientes</p>
          </div>
          <div className="bg-blue-50 p-4 rounded-lg border border-blue-200">
            <p className="text-2xl font-bold text-blue-700">{casos.filter(c => c.estado === 'en_proceso').length}</p>
            <p className="text-sm text-blue-600">En Proceso</p>
          </div>
          <div className="bg-emerald-50 p-4 rounded-lg border border-emerald-200">
            <p className="text-2xl font-bold text-emerald-700">{casos.filter(c => c.estado === 'atendido').length}</p>
            <p className="text-sm text-emerald-600">Atendidos</p>
          </div>
        </div>
      )}

      {/* Lista de casos */}
      <div className="bg-white rounded-xl shadow-sm border overflow-hidden">
        {/* Filtros */}
        <div className="p-3 bg-slate-50 border-b flex gap-3 flex-wrap">
          <select value={filtroCurso} onChange={e => setFiltroCurso(e.target.value)}
            className="px-3 py-1.5 bg-white border border-slate-200 rounded-lg text-sm">
            <option value="">Todos los cursos</option>
            {[...new Set(casos.map(c => c.curso).filter(Boolean))].sort().map(curso => (
              <option key={curso} value={curso}>{curso}</option>
            ))}
          </select>
          <select value={filtroEstado} onChange={e => setFiltroEstado(e.target.value)}
            className="px-3 py-1.5 bg-white border border-slate-200 rounded-lg text-sm">
            <option value="">Todos los estados</option>
            <option value="pendiente">Pendientes</option>
            <option value="en_proceso">En Proceso</option>
            <option value="atendido">Atendidos</option>
          </select>
        </div>
        <div className="divide-y">
        {casos.filter(c => {
          if (filtroCurso && c.curso !== filtroCurso) return false;
          if (filtroEstado && c.estado !== filtroEstado) return false;
          return true;
        }).map(c => (
          <div key={c.id} onClick={() => openDetalle(c)} className="p-4 hover:bg-gray-50 cursor-pointer">
            <div className="flex justify-between items-start">
              <div className="flex-1">
                <h3 className="font-semibold text-slate-800">{c.estudiante}</h3>
                <p className="text-sm text-gray-500 mt-1">
                  <span className="capitalize">{c.tipo}</span> • Solicitado por: {c.solicitante}
                </p>
                <p className="text-xs text-gray-400 mt-1">{formatFecha(c.fecha_solicitud)}</p>
                
                {/* Mostrar recomendación si existe (para el solicitante) */}
                {c.recomendacion_profesor && c.solicitante_id === user?.id && (
                  <div className="mt-2 p-2 bg-blue-50 rounded-lg border border-blue-100">
                    <p className="text-xs font-medium text-blue-700 flex items-center gap-1">
                      <MessageSquare size={12} /> Recomendación de Psicología:
                    </p>
                    <p className="text-sm text-blue-800 mt-1">{c.recomendacion_profesor}</p>
                  </div>
                )}
              </div>
              <div className="flex items-center gap-2 ml-4">
                {c.urgencia === 'urgente' && (
                  <span className="px-2 py-0.5 bg-red-100 text-red-700 text-xs rounded-full border border-red-200">
                    🔴 Urgente
                  </span>
                )}
                <span className={`px-2 py-1 rounded-full text-xs font-medium flex items-center gap-1 border ${getEstadoColor(c.estado)}`}>
                  {getEstadoIcon(c.estado)}
                  <span className="capitalize">{c.estado.replace('_', ' ')}</span>
                </span>
                {isPsico && c.estado === 'pendiente' && (
                  <button 
                    onClick={e => { e.stopPropagation(); handleTomar(c.id); }} 
                    className="px-3 py-1 bg-purple-600 text-white text-xs rounded-lg hover:bg-purple-700"
                  >
                    Tomar
                  </button>
                )}
              </div>
            </div>
          </div>
        ))}
        </div>
        {casos.length === 0 && (
          <div className="p-12 text-center">
            <Brain size={48} className="mx-auto text-gray-300 mb-4" />
            <p className="text-gray-500">No hay casos registrados</p>
          </div>
        )}
      </div>

      {/* Modal Solicitar */}
      <Modal
        isOpen={showModal}
        onClose={() => setShowModal(false)}
        title="Solicitar Atención Psicológica"
        size="md"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowModal(false)}>Cancelar</Button>
            <Button onClick={handleSolicitar} className="bg-purple-600 hover:bg-purple-700">Solicitar</Button>
          </>
        }
      >
        <div className="space-y-4">
          <Select
            label="Curso"
            value={form.curso_filter || ''}
            onChange={e => setForm({...form, curso_filter: e.target.value, estudiante_id: 0})}
            options={cursos.map(c => ({ value: c.id, label: c.grado ? `${c.grado} ${c.nombre}` : c.nombre_completo, group: c.tanda || 'Sin tanda' }))}
            placeholder="Filtrar por curso"
          />
          <Select
            label="Estudiante"
            value={form.estudiante_id}
            onChange={e => setForm({...form, estudiante_id: parseInt(e.target.value)})}
            options={estudiantes
              .filter(e => !form.curso_filter || e.curso_id === parseInt(form.curso_filter))
              .map(e => ({ value: e.id, label: e.nombre_completo }))}
            placeholder="Seleccionar estudiante"
          />
          <div className="grid grid-cols-2 gap-4">
            <Select
              label="Tipo"
              value={form.tipo}
              onChange={e => setForm({...form, tipo: e.target.value})}
              options={[
                { value: 'emocional', label: 'Emocional' },
                { value: 'conductual', label: 'Conductual' },
                { value: 'academico', label: 'Académico' },
                { value: 'familiar', label: 'Familiar' },
              ]}
            />
            <Select
              label="Urgencia"
              value={form.urgencia}
              onChange={e => setForm({...form, urgencia: e.target.value})}
              options={[
                { value: 'normal', label: 'Normal' },
                { value: 'urgente', label: 'Urgente' },
              ]}
            />
          </div>
          <Textarea
            label="Motivo de la solicitud"
            value={form.motivo}
            onChange={e => setForm({...form, motivo: e.target.value})}
            placeholder="Describa el motivo por el cual solicita atención psicológica para este estudiante..."
            rows={4}
          />
        </div>
      </Modal>

      {/* Modal Detalle */}
      <Modal
        isOpen={showDetalleModal}
        onClose={() => { setShowDetalleModal(false); setSelected(null); }}
        title={selected?.estudiante || 'Detalle del Caso'}
        size="lg"
        footer={
          isPsico && selected?.estado !== 'atendido' ? (
            <>
              <Button variant="secondary" onClick={() => { setShowDetalleModal(false); setSelected(null); }}>
                Cerrar
              </Button>
              <Button onClick={handleActualizarCaso} className="bg-purple-600 hover:bg-purple-700">
                Guardar Cambios
              </Button>
            </>
          ) : (
            <Button variant="secondary" onClick={() => { setShowDetalleModal(false); setSelected(null); }}>
              Cerrar
            </Button>
          )
        }
      >
        {selected && (
          <div className="space-y-4">
            {/* Info del caso */}
            <div className="grid grid-cols-2 gap-4 p-4 bg-gray-50 rounded-lg">
              <div>
                <p className="text-xs text-gray-500">Tipo</p>
                <p className="font-medium capitalize">{selected.tipo}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500">Urgencia</p>
                <p className="font-medium capitalize">{selected.urgencia}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500">Solicitante</p>
                <p className="font-medium">{selected.solicitante}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500">Estado</p>
                <span className={`px-2 py-1 rounded-full text-xs font-medium ${getEstadoColor(selected.estado)}`}>
                  {selected.estado.replace('_', ' ')}
                </span>
              </div>
            </div>

            {/* Motivo */}
            <div>
              <p className="text-sm font-medium text-gray-700 mb-1">Motivo de la solicitud</p>
              <p className="p-3 bg-gray-50 rounded-lg text-sm">{selected.motivo}</p>
            </div>

            {/* Campos editables para psicología */}
            {isPsico && selected.estado !== 'atendido' && (
              <>
                <Select
                  label="Estado del caso"
                  value={notasForm.estado}
                  onChange={e => setNotasForm({...notasForm, estado: e.target.value})}
                  options={[
                    { value: 'pendiente', label: 'Pendiente' },
                    { value: 'en_proceso', label: 'En Proceso' },
                    { value: 'atendido', label: 'Atendido' },
                  ]}
                />
                <Textarea
                  label="Notas de atención (privadas)"
                  value={notasForm.notas_atencion}
                  onChange={e => setNotasForm({...notasForm, notas_atencion: e.target.value})}
                  placeholder="Notas sobre la atención brindada al estudiante..."
                  rows={3}
                />
                <Textarea
                  label="Recomendación para el profesor/solicitante"
                  value={notasForm.recomendacion_profesor}
                  onChange={e => setNotasForm({...notasForm, recomendacion_profesor: e.target.value})}
                  placeholder="Escriba una recomendación o sugerencia que será visible para quien hizo la solicitud..."
                  rows={3}
                />
              </>
            )}

            {/* Mostrar notas y recomendaciones si ya existen */}
            {(selected.notas_atencion || selected.recomendacion_profesor) && !isPsico && (
              <>
                {selected.recomendacion_profesor && (
                  <div>
                    <p className="text-sm font-medium text-blue-700 mb-1">Recomendación de Psicología</p>
                    <p className="p-3 bg-blue-50 rounded-lg text-sm border border-blue-100">{selected.recomendacion_profesor}</p>
                  </div>
                )}
              </>
            )}

            {isPsico && selected.estado === 'atendido' && (
              <>
                {selected.notas_atencion && (
                  <div>
                    <p className="text-sm font-medium text-gray-700 mb-1">Notas de atención</p>
                    <p className="p-3 bg-gray-50 rounded-lg text-sm">{selected.notas_atencion}</p>
                  </div>
                )}
                {selected.recomendacion_profesor && (
                  <div>
                    <p className="text-sm font-medium text-blue-700 mb-1">Recomendación enviada</p>
                    <p className="p-3 bg-blue-50 rounded-lg text-sm border border-blue-100">{selected.recomendacion_profesor}</p>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
};

export default PsicologiaPage;
