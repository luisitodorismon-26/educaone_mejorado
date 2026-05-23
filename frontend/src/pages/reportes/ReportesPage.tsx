import { useState, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';
import { 
  FileBarChart, 
  TrendingUp, 
  Users, 
  AlertCircle, 
  Download, 
  Filter, 
  Send,
  Plus,
  Eye,
  MessageSquare
} from 'lucide-react';
import { Modal, Button, Select, Input, Alert } from '../../components/ui';

interface Reporte {
  id: number;
  numero_reporte?: string;
  titulo: string;
  descripcion: string;
  tipo: string;
  gravedad: string;
  estado: string;
  estudiante: string;
  estudiante_id: number;
  estudiante_curso: string;
  reportado_por: string;
  reportado_por_id?: number;
  fecha: string;
  // v2.11: 3 campos guiados
  acciones_centro?: string;
  acciones_hogar?: string;
  respuesta?: string;
  respondido_por?: string;
  fecha_respuesta?: string;
  // Envío y confirmación padre
  enviado_padres?: boolean;
  confirmado_padre?: boolean;
  fecha_confirmacion_padre?: string;
  // v2.11.1: contacto del padre para WhatsApp
  contacto_principal_nombre?: string | null;
  contacto_principal_telefono?: string | null;
}

// Plantillas hardcodeadas para chips en "Acciones del centro"
const PLANTILLAS_CENTRO = [
  'Llamado de atención verbal',
  'Retención de celular u objeto',
  'Reflexión guiada con coordinador',
  'Reflexión guiada con psicología',
  'Citación a padre/tutor',
  'Suspensión interna 1 día',
  'Suspensión interna 3 días',
  'Anotación en expediente',
];

// Plantillas para "Acciones esperadas en el hogar"
const PLANTILLAS_HOGAR = [
  'Conversar con el estudiante sobre las normas del centro',
  'Reunión presencial con coordinación',
  'Firmar el reporte y devolverlo',
  'Acompañamiento académico en casa',
  'Apoyo emocional/psicológico',
];

export const ReportesPage = () => {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState('conducta');
  const [reportes, setReportes] = useState<Reporte[]>([]);
  const [estudiantes, setEstudiantes] = useState<any[]>([]);
  const [cursos, setCursos] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Modales
  const [showModal, setShowModal] = useState(false);
  const [showDetalleModal, setShowDetalleModal] = useState(false);
  const [selectedReporte, setSelectedReporte] = useState<Reporte | null>(null);
  // v2.11: 3 campos guiados al responder
  const [accionesCentro, setAccionesCentro] = useState('');
  const [accionesHogar, setAccionesHogar] = useState('');
  const [respuesta, setRespuesta] = useState('');

  // Form
  const [form, setForm] = useState({
    estudiante_id: 0,
    tipo: 'conducta',
    gravedad: 'leve',
    titulo: '',
    descripcion: '',
    curso_filter: ''
  });

  // Filtros
  const [filtroEstado, setFiltroEstado] = useState('');
  const [filtroCurso, setFiltroCurso] = useState(0);

  const canCreate = user?.role === 'profesor' || user?.role === 'coordinador';
  const canRespond = user?.role === 'direccion' || user?.role === 'coordinador' || user?.role === 'psicologia';
  const canSendToParents = user?.role === 'direccion' || user?.role === 'coordinador';

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    try {
      const [r, e, c] = await Promise.all([
        api.get('/reportes'),
        api.get('/estudiantes'),
        api.get('/cursos')
      ]);
      setReportes(r.data);
      setEstudiantes(e.data);
      setCursos(c.data);
    } catch (e) {
      console.error('Error cargando datos:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    if (!form.estudiante_id || !form.titulo) {
      setMessage({ type: 'error', text: 'Complete los campos requeridos' });
      return;
    }
    try {
      await api.post('/reportes', form);
      setMessage({ type: 'success', text: 'Reporte creado correctamente' });
      loadData();
      setShowModal(false);
      setForm({ estudiante_id: 0, tipo: 'conducta', gravedad: 'leve', titulo: '', descripcion: '', curso_filter: '' });
    } catch (e: any) {
      setMessage({ type: 'error', text: e.response?.data?.error || 'Error al crear' });
    }
  };

  const handleResponder = async () => {
    if (!selectedReporte) return;
    if (!accionesCentro && !respuesta) {
      setMessage({ type: 'error', text: 'Debe completar al menos "Acciones del centro" o "Comentario"' });
      return;
    }
    try {
      await api.post(`/reportes/${selectedReporte.id}/responder`, {
        acciones_centro: accionesCentro,
        acciones_hogar: accionesHogar,
        respuesta,
        estado: 'resuelto'
      });
      setMessage({ type: 'success', text: 'Reporte respondido' });
      loadData();
      setShowDetalleModal(false);
      setSelectedReporte(null);
      setAccionesCentro('');
      setAccionesHogar('');
      setRespuesta('');
    } catch (e: any) {
      setMessage({ type: 'error', text: e.response?.data?.error || 'Error al responder' });
    }
  };

  const handleAgregarChip = (texto: string, target: 'centro' | 'hogar') => {
    const bullet = `• ${texto}`;
    if (target === 'centro') {
      setAccionesCentro(prev => prev ? `${prev}\n${bullet}` : bullet);
    } else {
      setAccionesHogar(prev => prev ? `${prev}\n${bullet}` : bullet);
    }
  };

  const handleImprimirPDF = (reporteId: number) => {
    const token = localStorage.getItem('token');
    const url = `${(import.meta as any).env.VITE_API_URL || ''}/api/reportes/${reporteId}/pdf`;
    fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      .then(async r => {
        if (r.ok) return r.blob();
        // Leer el detalle real del error (el backend manda JSON con 'error')
        let detalle = `Error ${r.status}`;
        try {
          const texto = await r.text();
          const j = JSON.parse(texto);
          detalle = j.error || detalle;
        } catch { /* no era JSON */ }
        return Promise.reject(new Error(detalle));
      })
      .then(blob => {
        const u = URL.createObjectURL(blob);
        window.open(u, '_blank');
      })
      .catch((e: any) => setMessage({ type: 'error', text: e?.message || 'No se pudo generar el PDF' }));
  };

  const handleConfirmarPadre = async (reporteId: number) => {
    try {
      await api.post(`/reportes/${reporteId}/confirmar-padre`);
      setMessage({ type: 'success', text: 'Reporte marcado como firmado por el padre' });
      loadData();
    } catch (e: any) {
      setMessage({ type: 'error', text: e.response?.data?.error || 'Error' });
    }
  };

  const handleEnviarPadres = async (reporteId: number) => {
    // v2.11.1: en lugar de solo marcar en BD, abre WhatsApp directamente.
    // Es la misma lógica del botón del modal, pero accesible desde la lista.
    const reporte = reportes.find(r => r.id === reporteId);
    if (!reporte) return;
    
    // Limpiar teléfono al formato wa.me (mismos pasos que en el modal)
    const limpiarTelefono = (raw: string | null | undefined): string | null => {
      if (!raw) return null;
      let solo_digitos = raw.replace(/\D/g, '');
      if (solo_digitos.length === 10 && /^(809|829|849)/.test(solo_digitos)) {
        solo_digitos = '1' + solo_digitos;
      }
      if (solo_digitos.length >= 10 && solo_digitos.length <= 15) {
        return solo_digitos;
      }
      return null;
    };
    
    const telefonoLimpio = limpiarTelefono(reporte.contacto_principal_telefono);
    const nombreContacto = reporte.contacto_principal_nombre;
    
    if (!telefonoLimpio) {
      setMessage({
        type: 'error',
        text: `❌ ${reporte.estudiante} no tiene teléfono del padre/tutor registrado. Agregalo en el perfil del estudiante.`
      });
      setTimeout(() => setMessage(null), 6000);
      return;
    }
    
    // Armar mensaje
    const fecha = new Date(reporte.fecha).toLocaleDateString('es-DO', {
      weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'
    });
    const mensajeTexto =
      `Estimado padre/madre/tutor,\n\n` +
      `Le saludamos cordialmente desde la Dirección del Centro Educativo.\n\n` +
      `Le informamos que el día ${fecha}, ${reporte.reportado_por} ` +
      `nos ha comunicado una situación respecto a su hijo/a ` +
      `${reporte.estudiante} de ${reporte.estudiante_curso}.\n\n` +
      `Situación reportada:\n${reporte.descripcion?.substring(0, 300)}\n\n` +
      (reporte.acciones_centro
        ? `Acciones tomadas por el centro:\n${reporte.acciones_centro}\n\n`
        : '') +
      (reporte.acciones_hogar
        ? `Le pedimos por favor:\n${reporte.acciones_hogar}\n\n`
        : '') +
      `Le adjuntamos el reporte oficial impreso (PDF). Agradecemos su atención.\n\n` +
      `Atentamente,\nDirección del Centro Educativo`;
    
    // PASO 1: descargar PDF
    try {
      const token = localStorage.getItem('token');
      const pdfUrl = `${(import.meta as any).env.VITE_API_URL || ''}/api/reportes/${reporteId}/pdf`;
      const pdfRes = await fetch(pdfUrl, { headers: { Authorization: `Bearer ${token}` } });
      if (pdfRes.ok) {
        const blob = await pdfRes.blob();
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = `reporte_${reporte.numero_reporte || reporteId}.pdf`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
      }
    } catch (e) {
      // Si falla la descarga, igual seguimos con WhatsApp
    }
    
    // PASO 2: registrar en historial + marcar enviado
    try {
      await api.post('/comunicacion-padres', {
        estudiante_id: reporte.estudiante_id,
        tipo: 'reporte_conducta',
        referencia_id: reporteId,
        mensaje: mensajeTexto,
        medio: 'whatsapp'
      });
      await api.post(`/reportes/${reporteId}/enviar-padres`, {
        telefono: telefonoLimpio,
        mensaje: mensajeTexto,
      });
    } catch (e) {
      // No bloquear
    }
    
    // PASO 3: abrir WhatsApp con el chat correcto
    window.open(`https://wa.me/${telefonoLimpio}?text=${encodeURIComponent(mensajeTexto)}`, '_blank');
    
    setMessage({
      type: 'success',
      text: `✅ PDF descargado y WhatsApp abierto con ${nombreContacto}. Adjunta el PDF al chat.`
    });
    setTimeout(() => setMessage(null), 6000);
    loadData();
  };

  const reportesFiltrados = reportes.filter(r => {
    if (activeTab === 'conducta' && r.tipo !== 'conducta') return false;
    if (activeTab === 'academico' && r.tipo !== 'academico') return false;
    if (activeTab === 'asistencia' && r.tipo !== 'asistencia') return false;
    if (filtroEstado && r.estado !== filtroEstado) return false;
    if (filtroCurso && r.estudiante_curso !== cursos.find(c => c.id === filtroCurso)?.nombre) return false;
    return true;
  });

  // Estadísticas
  const stats = {
    total: reportes.length,
    pendientes: reportes.filter(r => r.estado === 'pendiente').length,
    resueltos: reportes.filter(r => r.estado === 'resuelto').length,
    graves: reportes.filter(r => r.gravedad === 'grave').length
  };

  const getEstadoColor = (estado: string) => {
    if (estado === 'pendiente') return 'bg-amber-100 text-amber-700';
    if (estado === 'resuelto') return 'bg-emerald-100 text-emerald-700';
    return 'bg-slate-100 text-slate-700';
  };

  const getGravedadColor = (gravedad: string) => {
    if (gravedad === 'grave') return 'bg-red-100 text-red-700';
    if (gravedad === 'moderado') return 'bg-amber-100 text-amber-700';
    return 'bg-blue-100 text-blue-700';
  };

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap justify-between items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-800 flex items-center gap-2">
            <FileBarChart className="text-blue-600" size={28} />
            Reportes y Gestión
          </h1>
          <p className="text-sm text-slate-500">Reportes de conducta, rendimiento y asistencia</p>
        </div>
        <div className="flex gap-3">
          {canCreate && (
            <Button onClick={() => setShowModal(true)} icon={<Plus size={16} />}>
              Nuevo Reporte
            </Button>
          )}
          <button className="flex items-center px-4 py-2 bg-white border border-slate-200 rounded-lg text-sm font-medium text-slate-600 hover:bg-slate-50">
            <Download size={16} className="mr-2" /> Exportar
          </button>
        </div>
      </div>

      {message && (
        <Alert variant={message.type} onClose={() => setMessage(null)}>{message.text}</Alert>
      )}

      {/* Stats Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard title="Total Reportes" value={stats.total} icon={FileBarChart} color="blue" />
        <StatCard title="Pendientes" value={stats.pendientes} icon={AlertCircle} color="amber" />
        <StatCard title="Resueltos" value={stats.resueltos} icon={TrendingUp} color="emerald" />
        <StatCard title="Casos Graves" value={stats.graves} icon={AlertCircle} color="red" />
      </div>

      {/* Tabs y Filtros */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <div className="flex border-b border-slate-200 overflow-x-auto">
          <button
            onClick={() => setActiveTab('conducta')}
            className={`flex-shrink-0 px-4 py-3 text-sm font-medium transition-colors whitespace-nowrap ${
              activeTab === 'conducta' ? 'bg-blue-50 text-blue-600 border-b-2 border-blue-600' : 'text-slate-500 hover:bg-slate-50'
            }`}
          >
            🚨 Conducta
          </button>
          <button
            onClick={() => setActiveTab('academico')}
            className={`flex-shrink-0 px-4 py-3 text-sm font-medium transition-colors whitespace-nowrap ${
              activeTab === 'academico' ? 'bg-blue-50 text-blue-600 border-b-2 border-blue-600' : 'text-slate-500 hover:bg-slate-50'
            }`}
          >
            📚 Académico
          </button>
          <button
            onClick={() => setActiveTab('asistencia')}
            className={`flex-shrink-0 px-4 py-3 text-sm font-medium transition-colors whitespace-nowrap ${
              activeTab === 'asistencia' ? 'bg-blue-50 text-blue-600 border-b-2 border-blue-600' : 'text-slate-500 hover:bg-slate-50'
            }`}
          >
            📅 Asistencia
          </button>
          <button
            onClick={() => setActiveTab('todos')}
            className={`flex-shrink-0 px-4 py-3 text-sm font-medium transition-colors whitespace-nowrap ${
              activeTab === 'todos' ? 'bg-blue-50 text-blue-600 border-b-2 border-blue-600' : 'text-slate-500 hover:bg-slate-50'
            }`}
          >
            📋 Todos
          </button>
        </div>

        {/* Filtros */}
        <div className="p-4 bg-slate-50 border-b border-slate-200 flex gap-4 flex-wrap">
          <div className="flex items-center gap-2">
            <Filter size={16} className="text-slate-400" />
            <select
              value={filtroEstado}
              onChange={e => setFiltroEstado(e.target.value)}
              className="px-3 py-1.5 bg-white border border-slate-200 rounded-lg text-sm"
            >
              <option value="">Todos los estados</option>
              <option value="pendiente">Pendientes</option>
              <option value="resuelto">Resueltos</option>
            </select>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={filtroCurso}
              onChange={e => setFiltroCurso(Number(e.target.value))}
              className="px-3 py-1.5 bg-white border border-slate-200 rounded-lg text-sm"
            >
              <option value={0}>Todos los cursos</option>
              {cursos.map(c => <option key={c.id} value={c.id}>{c.nombre}</option>)}
            </select>
          </div>
        </div>

        {/* Lista de reportes */}
        <div className="divide-y divide-slate-100">
          {reportesFiltrados.map(reporte => (
            <div 
              key={reporte.id} 
              className="p-4 hover:bg-slate-50 transition-colors"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <h4 className="font-semibold text-slate-800">{reporte.titulo}</h4>
                    <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${getGravedadColor(reporte.gravedad)}`}>
                      {reporte.gravedad.toUpperCase()}
                    </span>
                  </div>
                  <p className="text-sm text-slate-500 mb-2">
                    {reporte.estudiante} • {reporte.estudiante_curso}
                  </p>
                  <p className="text-xs text-slate-400">
                    Reportado por: {reporte.reportado_por} • {new Date(reporte.fecha).toLocaleDateString('es-DO')}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`text-xs px-2 py-1 rounded-full font-medium ${getEstadoColor(reporte.estado)}`}>
                    {reporte.estado}
                  </span>
                  <button
                    onClick={() => {
                      setSelectedReporte(reporte);
                      // Si ya tiene respuesta, precargarla en los textareas para edición
                      setAccionesCentro(reporte.acciones_centro || '');
                      setAccionesHogar(reporte.acciones_hogar || '');
                      setRespuesta(reporte.respuesta || '');
                      setShowDetalleModal(true);
                    }}
                    className="p-2 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                  >
                    <Eye size={18} />
                  </button>
                  {canSendToParents && reporte.estado === 'resuelto' && (
                    <button
                      onClick={() => handleEnviarPadres(reporte.id)}
                      className="p-2 text-slate-400 hover:text-emerald-600 hover:bg-emerald-50 rounded-lg transition-colors"
                      title="Enviar a padres"
                    >
                      <Send size={18} />
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
          {reportesFiltrados.length === 0 && (
            <div className="p-12 text-center text-slate-500">
              No hay reportes en esta categoría
            </div>
          )}
        </div>
      </div>

      {/* Modal Crear Reporte */}
      <Modal
        isOpen={showModal}
        onClose={() => setShowModal(false)}
        title="Nuevo Reporte"
        size="lg"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowModal(false)}>Cancelar</Button>
            <Button onClick={handleCreate}>Crear Reporte</Button>
          </>
        }
      >
        <div className="space-y-4">
          <Select
            label="Curso"
            value={form.curso_filter || ''}
            onChange={e => setForm({ ...form, curso_filter: e.target.value, estudiante_id: 0 })}
            options={cursos.map(c => ({ value: c.id, label: c.grado ? `${c.grado} ${c.nombre}` : c.nombre_completo, group: c.tanda || 'Sin tanda' }))}
            placeholder="Filtrar por curso"
          />
          <Select
            label="Estudiante *"
            value={form.estudiante_id}
            onChange={e => setForm({ ...form, estudiante_id: parseInt(e.target.value) })}
            options={estudiantes
              .filter(e => !form.curso_filter || e.curso_id === parseInt(form.curso_filter))
              .map(e => ({ value: e.id, label: `${e.nombre_completo}${!form.curso_filter ? ` - ${e.curso}` : ''}` }))}
            placeholder="Seleccionar estudiante"
          />
          <Input
            label="Título *"
            value={form.titulo}
            onChange={e => setForm({ ...form, titulo: e.target.value })}
            placeholder="Resumen breve del reporte"
          />
          <div className="grid grid-cols-2 gap-4">
            <Select
              label="Tipo"
              value={form.tipo}
              onChange={e => setForm({ ...form, tipo: e.target.value })}
              options={[
                { value: 'conducta', label: '🚨 Conducta' },
                { value: 'academico', label: '📚 Académico' },
                { value: 'asistencia', label: '📅 Asistencia' }
              ]}
            />
            <Select
              label="Gravedad"
              value={form.gravedad}
              onChange={e => setForm({ ...form, gravedad: e.target.value })}
              options={[
                { value: 'leve', label: 'Leve' },
                { value: 'moderado', label: 'Moderado' },
                { value: 'grave', label: 'Grave' }
              ]}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Descripción</label>
            <textarea
              value={form.descripcion}
              onChange={e => setForm({ ...form, descripcion: e.target.value })}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              rows={4}
              placeholder="Detalle del incidente o situación..."
            />
          </div>
          <p className="text-xs text-slate-400">
            * El reporte será enviado a la dirección para su revisión y seguimiento.
          </p>
        </div>
      </Modal>

      {/* Modal Detalle */}
      <Modal
        isOpen={showDetalleModal}
        onClose={() => { setShowDetalleModal(false); setSelectedReporte(null); setAccionesCentro(''); setAccionesHogar(''); setRespuesta(''); }}
        title={selectedReporte?.numero_reporte ? `Reporte Nº ${selectedReporte.numero_reporte}` : "Detalle del Reporte"}
        size="lg"
        footer={
          <>
            <Button variant="secondary" onClick={() => { setShowDetalleModal(false); setSelectedReporte(null); setAccionesCentro(''); setAccionesHogar(''); setRespuesta(''); }}>
              Cerrar
            </Button>
            {/* Botón Imprimir PDF — disponible cuando hay reporte cargado */}
            {selectedReporte && (
              <Button
                variant="secondary"
                onClick={() => handleImprimirPDF(selectedReporte.id)}
                icon={<span>🖨️</span>}
              >
                Imprimir PDF
              </Button>
            )}
            {/* Botón Marcar firmado por padre — dirección/coordinador/psicología, solo si no está confirmado aún */}
            {canRespond && selectedReporte && !selectedReporte.confirmado_padre && selectedReporte.estado !== 'pendiente' && (
              <Button
                variant="secondary"
                onClick={() => handleConfirmarPadre(selectedReporte.id)}
                icon={<span>✓</span>}
              >
                Marcar firmado por padre
              </Button>
            )}
            {/* Botón Responder — solo si pendiente y tiene permiso */}
            {canRespond && selectedReporte?.estado === 'pendiente' && (
              <Button onClick={handleResponder} icon={<MessageSquare size={16} />}>
                Aprobar y enviar a padre
              </Button>
            )}
          </>
        }
      >
        {selectedReporte && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-bold text-slate-800">{selectedReporte.titulo}</h3>
              <span className={`text-xs px-2 py-1 rounded-full font-medium ${getEstadoColor(selectedReporte.estado)}`}>
                {selectedReporte.estado}
              </span>
            </div>

            {/* Grid datos */}
            <div className="grid grid-cols-2 gap-4 text-sm bg-slate-50 p-3 rounded-lg">
              <div>
                <p className="text-slate-500 text-xs">Estudiante</p>
                <p className="font-medium">{selectedReporte.estudiante}</p>
              </div>
              <div>
                <p className="text-slate-500 text-xs">Curso</p>
                <p className="font-medium">{selectedReporte.estudiante_curso}</p>
              </div>
              <div>
                <p className="text-slate-500 text-xs">Reportado por</p>
                <p className="font-medium">{selectedReporte.reportado_por}</p>
              </div>
              <div>
                <p className="text-slate-500 text-xs">Fecha</p>
                <p className="font-medium">{new Date(selectedReporte.fecha).toLocaleString('es-DO')}</p>
              </div>
              <div>
                <p className="text-slate-500 text-xs">Gravedad</p>
                <p className="font-medium capitalize">{selectedReporte.gravedad}</p>
              </div>
              <div>
                <p className="text-slate-500 text-xs">Estado padre</p>
                <p className="font-medium">
                  {selectedReporte.confirmado_padre
                    ? <span className="text-emerald-700">✓ Firmado el {new Date(selectedReporte.fecha_confirmacion_padre!).toLocaleDateString('es-DO')}</span>
                    : selectedReporte.enviado_padres
                      ? <span className="text-blue-700">Enviado, pendiente firma</span>
                      : <span className="text-slate-500">No enviado</span>}
                </p>
              </div>
            </div>

            {/* Descripción del incidente (lo del profesor) */}
            <div>
              <p className="text-xs font-medium text-blue-700 uppercase tracking-wide mb-1">
                Descripción del incidente (lo que reportó el profesor)
              </p>
              <div className="p-3 border-l-4 border-blue-400 bg-blue-50/30 rounded">
                <p className="text-sm text-slate-700 whitespace-pre-wrap">{selectedReporte.descripcion}</p>
              </div>
            </div>

            {/* Si ya está respondido: mostrar los 3 campos como vista */}
            {selectedReporte.estado !== 'pendiente' && (
              <>
                {selectedReporte.acciones_centro && (
                  <div>
                    <p className="text-xs font-medium text-emerald-700 uppercase tracking-wide mb-1">
                      Acciones tomadas por el centro
                    </p>
                    <div className="p-3 border-l-4 border-emerald-400 bg-emerald-50/30 rounded">
                      <p className="text-sm text-slate-700 whitespace-pre-wrap">{selectedReporte.acciones_centro}</p>
                    </div>
                  </div>
                )}
                {selectedReporte.acciones_hogar && (
                  <div>
                    <p className="text-xs font-medium text-amber-700 uppercase tracking-wide mb-1">
                      Acciones esperadas en el hogar
                    </p>
                    <div className="p-3 border-l-4 border-amber-400 bg-amber-50/30 rounded">
                      <p className="text-sm text-slate-700 whitespace-pre-wrap">{selectedReporte.acciones_hogar}</p>
                    </div>
                  </div>
                )}
                {selectedReporte.respuesta && (
                  <div>
                    <p className="text-xs font-medium text-slate-600 uppercase tracking-wide mb-1">
                      Comentario adicional
                    </p>
                    <div className="p-3 border-l-4 border-slate-400 bg-slate-50/30 rounded">
                      <p className="text-sm text-slate-700 whitespace-pre-wrap">{selectedReporte.respuesta}</p>
                    </div>
                  </div>
                )}
              </>
            )}

            {/* Si está pendiente y el usuario puede responder: formulario con chips */}
            {canRespond && selectedReporte.estado === 'pendiente' && (
              <>
                <div className="border-t pt-4">
                  <p className="text-sm font-semibold text-slate-800 mb-3">Completar respuesta</p>
                </div>

                {/* Sección 1: Acciones del centro */}
                <div>
                  <label className="block text-xs font-medium text-blue-700 uppercase tracking-wide mb-2">
                    Acciones tomadas por el centro <span className="text-red-500 normal-case">(obligatorio)</span>
                  </label>
                  <div className="flex flex-wrap gap-1.5 mb-2">
                    {PLANTILLAS_CENTRO.map(p => (
                      <button
                        key={p}
                        type="button"
                        onClick={() => handleAgregarChip(p, 'centro')}
                        className="px-2.5 py-1 text-xs bg-blue-50 text-blue-700 border border-blue-200 rounded-full hover:bg-blue-100 transition-colors"
                      >
                        + {p}
                      </button>
                    ))}
                  </div>
                  <textarea
                    value={accionesCentro}
                    onChange={e => setAccionesCentro(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 text-sm"
                    rows={3}
                    placeholder="Clic en los chips arriba o escribir manualmente las acciones tomadas..."
                  />
                </div>

                {/* Sección 2: Acciones esperadas en el hogar */}
                <div>
                  <label className="block text-xs font-medium text-emerald-700 uppercase tracking-wide mb-2">
                    Acciones esperadas en el hogar <span className="text-slate-500 normal-case">(opcional)</span>
                  </label>
                  <div className="flex flex-wrap gap-1.5 mb-2">
                    {PLANTILLAS_HOGAR.map(p => (
                      <button
                        key={p}
                        type="button"
                        onClick={() => handleAgregarChip(p, 'hogar')}
                        className="px-2.5 py-1 text-xs bg-emerald-50 text-emerald-700 border border-emerald-200 rounded-full hover:bg-emerald-100 transition-colors"
                      >
                        + {p}
                      </button>
                    ))}
                  </div>
                  <textarea
                    value={accionesHogar}
                    onChange={e => setAccionesHogar(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 text-sm"
                    rows={2}
                    placeholder="Lo que se le pedirá al padre/tutor..."
                  />
                </div>

                {/* Sección 3: Comentario adicional */}
                <div>
                  <label className="block text-xs font-medium text-slate-600 uppercase tracking-wide mb-2">
                    Comentario adicional <span className="text-slate-500 normal-case">(opcional)</span>
                  </label>
                  <textarea
                    value={respuesta}
                    onChange={e => setRespuesta(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 text-sm"
                    rows={2}
                    placeholder="Información adicional para el padre..."
                  />
                </div>
              </>
            )}

            {/* Botón enviar a padres por WhatsApp — solo si respondido y no enviado */}
            {selectedReporte.estado !== 'pendiente' && !selectedReporte.enviado_padres && (() => {
              // v2.11.1: validar teléfono del contacto principal
              const telefonoRaw = selectedReporte.contacto_principal_telefono;
              const nombreContacto = selectedReporte.contacto_principal_nombre;
              
              // Limpiar teléfono: dejar solo dígitos, agregar prefijo DR (1) si falta
              // Ejemplos:
              //   "809-555-1234" → "18095551234"
              //   "(809) 555-1234" → "18095551234"
              //   "8095551234" → "18095551234"
              //   "+18095551234" → "18095551234"
              const limpiarTelefono = (raw: string | null | undefined): string | null => {
                if (!raw) return null;
                let solo_digitos = raw.replace(/\D/g, '');
                // Si tiene 10 dígitos y arranca con 809/829/849 (códigos DR), agregar 1
                if (solo_digitos.length === 10 && /^(809|829|849)/.test(solo_digitos)) {
                  solo_digitos = '1' + solo_digitos;
                }
                // Si tiene 11 dígitos y arranca con 1, es válido para wa.me
                if (solo_digitos.length >= 10 && solo_digitos.length <= 15) {
                  return solo_digitos;
                }
                return null;
              };
              
              const telefonoLimpio = limpiarTelefono(telefonoRaw);
              const sinTelefono = !telefonoLimpio;
              
              const fecha = new Date(selectedReporte.fecha).toLocaleDateString('es-DO', {
                weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'
              });
              const mensajeTexto =
                `Estimado padre/madre/tutor,\n\n` +
                `Le saludamos cordialmente desde la Dirección del Centro Educativo.\n\n` +
                `Le informamos que el día ${fecha}, ${selectedReporte.reportado_por} ` +
                `nos ha comunicado una situación respecto a su hijo/a ` +
                `${selectedReporte.estudiante} de ${selectedReporte.estudiante_curso}.\n\n` +
                `Situación reportada:\n${selectedReporte.descripcion?.substring(0, 300)}\n\n` +
                (selectedReporte.acciones_centro
                  ? `Acciones tomadas por el centro:\n${selectedReporte.acciones_centro}\n\n`
                  : '') +
                (selectedReporte.acciones_hogar
                  ? `Le pedimos por favor:\n${selectedReporte.acciones_hogar}\n\n`
                  : '') +
                `Le adjuntamos el reporte oficial impreso (PDF). Agradecemos su atención.\n\n` +
                `Atentamente,\nDirección del Centro Educativo`;
              
              const enviar = async () => {
                if (sinTelefono) return;
                
                // PASO 1: descargar el PDF automáticamente para que el director lo arrastre al chat
                try {
                  const token = localStorage.getItem('token');
                  const pdfUrl = `${(import.meta as any).env.VITE_API_URL || ''}/api/reportes/${selectedReporte.id}/pdf`;
                  const pdfRes = await fetch(pdfUrl, { headers: { Authorization: `Bearer ${token}` } });
                  if (pdfRes.ok) {
                    const blob = await pdfRes.blob();
                    const link = document.createElement('a');
                    link.href = URL.createObjectURL(blob);
                    link.download = `reporte_${selectedReporte.numero_reporte || selectedReporte.id}.pdf`;
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);
                  }
                } catch (e) {
                  // Si falla la descarga, continuamos con el envío de WhatsApp igual
                }
                
                // PASO 2: registrar la comunicación en el historial
                try {
                  await api.post('/comunicacion-padres', {
                    estudiante_id: selectedReporte.estudiante_id,
                    tipo: 'reporte_conducta',
                    referencia_id: selectedReporte.id,
                    mensaje: mensajeTexto,
                    medio: 'whatsapp'
                  });
                  await api.post(`/reportes/${selectedReporte.id}/enviar-padres`, {
                    telefono: telefonoLimpio,
                    mensaje: mensajeTexto,
                  });
                } catch (e) {
                  // No bloquear el envío si falla el log
                }
                
                // PASO 3: abrir WhatsApp con el chat correcto y mensaje pre-cargado
                window.open(`https://wa.me/${telefonoLimpio}?text=${encodeURIComponent(mensajeTexto)}`, '_blank');
                
                setMessage({
                  type: 'success',
                  text: `✅ PDF descargado y WhatsApp abierto con ${nombreContacto}. Adjunta el PDF al chat.`
                });
                setTimeout(() => setMessage(null), 6000);
                loadData();
              };
              
              return (
                <div className="pt-2">
                  {sinTelefono ? (
                    <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 flex items-start gap-3">
                      <span className="text-2xl">⚠️</span>
                      <div className="flex-1">
                        <p className="text-sm font-medium text-amber-900">
                          No se puede enviar por WhatsApp
                        </p>
                        <p className="text-xs text-amber-700 mt-0.5">
                          Este estudiante no tiene teléfono de contacto registrado (tutor, padre o madre).
                          Agregalo desde el perfil del estudiante para poder enviarle el reporte por WhatsApp.
                        </p>
                      </div>
                      <button
                        disabled
                        className="px-4 py-2 bg-gray-300 text-gray-500 rounded-lg flex items-center gap-2 cursor-not-allowed whitespace-nowrap"
                        title="Sin teléfono del padre/tutor"
                      >
                        📱 Enviar por WhatsApp
                      </button>
                    </div>
                  ) : (
                    <div className="flex flex-col items-center gap-2">
                      <button
                        onClick={enviar}
                        className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 flex items-center gap-2 shadow"
                      >
                        📱 Enviar a {nombreContacto} por WhatsApp
                      </button>
                      <p className="text-xs text-slate-500 text-center">
                        Tel: {telefonoRaw}. Descargará el PDF + abrirá WhatsApp con el mensaje pre-cargado.
                      </p>
                    </div>
                  )}
                </div>
              );
            })()}
          </div>
        )}
      </Modal>
    </div>
  );
};

// Stat Card Component
const StatCard = ({ title, value, icon: Icon, color }: { title: string; value: number; icon: any; color: string }) => {
  const colors: Record<string, string> = {
    blue: 'bg-blue-50 text-blue-600',
    amber: 'bg-amber-50 text-amber-600',
    emerald: 'bg-emerald-50 text-emerald-600',
    red: 'bg-red-50 text-red-600',
  };

  return (
    <div className="bg-white p-4 rounded-xl border border-slate-200">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs text-slate-500 font-medium">{title}</p>
          <p className="text-2xl font-bold text-slate-800">{value}</p>
        </div>
        <div className={`p-2 rounded-lg ${colors[color]}`}>
          <Icon size={20} />
        </div>
      </div>
    </div>
  );
};

export default ReportesPage;
