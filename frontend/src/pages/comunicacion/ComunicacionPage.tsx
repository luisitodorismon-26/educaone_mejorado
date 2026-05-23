import { useState, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';

interface Usuario {
  id: number;
  nombre_completo: string;
  role: string;
}

interface Mensaje {
  id: number;
  asunto: string;
  contenido: string;
  remitente: string;
  remitente_id: number;
  destinatario?: string;
  fecha: string;
  leido: boolean;
  tipo: 'recibido' | 'enviado';
}

interface Comunicado {
  id: number;
  titulo: string;
  contenido: string;
  imagen?: string;
  autor: string;
  autor_id: number;
  fecha: string;
  leido_por_mi?: boolean;
}

export const ComunicacionPage = () => {
  const { user } = useAuth();
  const [tab, setTab] = useState<'mensajes' | 'enviados' | 'comunicados'>('mensajes');
  const [mensajes, setMensajes] = useState<Mensaje[]>([]);
  const [comunicados, setComunicados] = useState<Comunicado[]>([]);
  const [usuarios, setUsuarios] = useState<Usuario[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  
  // Modal
  const [showModal, setShowModal] = useState(false);
  const [modalType, setModalType] = useState<'mensaje' | 'comunicado' | 'ver' | 'responder' | 'editarComunicado'>('mensaje');
  const [selectedItem, setSelectedItem] = useState<any>(null);
  const [saving, setSaving] = useState(false);
  
  // Form mensaje
  const [tipoDestinatario, setTipoDestinatario] = useState<'individual' | 'rol'>('individual');
  const [destinatarioId, setDestinatarioId] = useState<number>(0);
  const [rolDestino, setRolDestino] = useState<string>('');
  const [asunto, setAsunto] = useState('');
  const [contenido, setContenido] = useState('');
  const [titulo, setTitulo] = useState('');
  const [imagen, setImagen] = useState('');

  useEffect(() => {
    cargarDatos();
  }, []);

  const cargarDatos = async () => {
    setLoading(true);
    try {
      const [mensajesRes, comunicadosRes, usuariosRes] = await Promise.all([
        api.get('/mensajes').catch(() => ({ data: [] })),
        api.get('/comunicados').catch(() => ({ data: [] })),
        api.get('/usuarios').catch(() => ({ data: [] }))
      ]);
      setMensajes(Array.isArray(mensajesRes.data) ? mensajesRes.data : []);
      setComunicados(Array.isArray(comunicadosRes.data) ? comunicadosRes.data : []);
      setUsuarios(Array.isArray(usuariosRes.data) ? usuariosRes.data : []);
    } catch (err) {
      console.error('Error cargando datos:', err);
    } finally {
      setLoading(false);
    }
  };

  const resetForm = () => {
    setTipoDestinatario('individual');
    setDestinatarioId(0);
    setRolDestino('');
    setAsunto('');
    setContenido('');
    setTitulo('');
    setImagen('');
    setSelectedItem(null);
  };

  const enviarMensaje = async () => {
    if (!asunto.trim() || !contenido.trim()) {
      setError('Asunto y contenido son requeridos');
      return;
    }

    if (tipoDestinatario === 'individual' && !destinatarioId) {
      setError('Seleccione un destinatario');
      return;
    }

    if (tipoDestinatario === 'rol' && !rolDestino) {
      setError('Seleccione un rol de destino');
      return;
    }

    setSaving(true);
    setError('');

    try {
      if (tipoDestinatario === 'individual') {
        await api.post('/mensajes', {
          destinatario_id: destinatarioId,
          asunto,
          contenido
        });
        setSuccess('Mensaje enviado');
      } else {
        const res = await api.post('/mensajes/masivo', {
          rol: rolDestino,
          asunto,
          contenido
        });
        setSuccess(`Mensaje enviado a ${res.data.enviados || 0} usuarios`);
      }
      
      setShowModal(false);
      resetForm();
      cargarDatos();
      setTimeout(() => setSuccess(''), 3000);
    } catch (err: any) {
      setError(err.response?.data?.error || 'Error al enviar');
    } finally {
      setSaving(false);
    }
  };

  const responderMensaje = async () => {
    if (!contenido.trim()) {
      setError('Escriba una respuesta');
      return;
    }

    setSaving(true);
    setError('');

    try {
      await api.post('/mensajes', {
        destinatario_id: selectedItem.remitente_id,
        asunto: `RE: ${selectedItem.asunto}`,
        contenido
      });
      
      setSuccess('Respuesta enviada');
      setShowModal(false);
      resetForm();
      cargarDatos();
      setTimeout(() => setSuccess(''), 3000);
    } catch (err: any) {
      setError(err.response?.data?.error || 'Error al enviar');
    } finally {
      setSaving(false);
    }
  };

  const guardarComunicado = async () => {
    if (!titulo.trim() || !contenido.trim()) {
      setError('Título y contenido son requeridos');
      return;
    }

    setSaving(true);
    setError('');

    try {
      if (modalType === 'editarComunicado' && selectedItem) {
        await api.put(`/comunicados/${selectedItem.id}`, { titulo, contenido, imagen });
        setSuccess('Comunicado actualizado');
      } else {
        await api.post('/comunicados', { titulo, contenido, imagen });
        setSuccess('Comunicado publicado');
      }
      
      setShowModal(false);
      resetForm();
      cargarDatos();
      setTimeout(() => setSuccess(''), 3000);
    } catch (err: any) {
      setError(err.response?.data?.error || 'Error al guardar');
    } finally {
      setSaving(false);
    }
  };

  const eliminarComunicado = async (id: number) => {
    if (!confirm('¿Eliminar este comunicado?')) return;
    
    try {
      await api.delete(`/comunicados/${id}`);
      setSuccess('Comunicado eliminado');
      cargarDatos();
      setTimeout(() => setSuccess(''), 3000);
    } catch (err: any) {
      setError(err.response?.data?.error || 'Error al eliminar');
    }
  };

  const eliminarMensaje = async (id: number) => {
    if (!confirm('¿Eliminar este mensaje?')) return;
    
    try {
      await api.delete(`/mensajes/${id}`);
      setSuccess('Mensaje eliminado');
      cargarDatos();
      setTimeout(() => setSuccess(''), 3000);
    } catch (err: any) {
      setError(err.response?.data?.error || 'Error al eliminar');
    }
  };

  const abrirEditarComunicado = (c: Comunicado) => {
    setSelectedItem(c);
    setTitulo(c.titulo);
    setContenido(c.contenido);
    setImagen(c.imagen || '');
    setModalType('editarComunicado');
    setShowModal(true);
  };

  const verMensaje = async (m: Mensaje) => {
    setSelectedItem(m);
    setModalType('ver');
    setShowModal(true);
    
    // Marcar como leído si es recibido y no leído
    if (m.tipo === 'recibido' && !m.leido) {
      try {
        await api.post(`/mensajes/${m.id}/marcar-leido`);
        // Actualizar localmente
        setMensajes(prev => prev.map(msg => 
          msg.id === m.id ? { ...msg, leido: true } : msg
        ));
      } catch (e) {
        console.error('Error marcando leído:', e);
      }
    }
  };

  const abrirResponder = (m: Mensaje) => {
    setSelectedItem(m);
    setContenido('');
    setModalType('responder');
    setShowModal(true);
  };

  const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      if (file.size > 2 * 1024 * 1024) {
        setError('La imagen no puede ser mayor a 2MB');
        return;
      }
      const reader = new FileReader();
      reader.onload = () => {
        setImagen(reader.result as string);
      };
      reader.readAsDataURL(file);
    }
  };

  const formatFecha = (f: string) => {
    if (!f) return '';
    try {
      return new Date(f).toLocaleDateString('es-DO', { 
        day: 'numeric', 
        month: 'short', 
        hour: '2-digit', 
        minute: '2-digit' 
      });
    } catch {
      return f;
    }
  };

  const canComunicado = user?.role === 'direccion' || user?.role === 'coordinador';
  
  // Filtrar mensajes
  const mensajesRecibidos = mensajes.filter(m => m.tipo === 'recibido');
  const mensajesEnviados = mensajes.filter(m => m.tipo === 'enviado');
  const mensajesNoLeidos = mensajesRecibidos.filter(m => !m.leido).length;

  // Roles disponibles para envío masivo
  const rolesDisponibles = [
    { value: 'profesor', label: '👨‍🏫 Todos los Profesores' },
    { value: 'coordinador', label: '👔 Todos los Coordinadores' },
    { value: 'psicologia', label: '🧠 Psicología' },
    { value: 'direccion', label: '👑 Dirección' }
  ].filter(r => r.value !== user?.role);

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <div className="animate-spin h-8 w-8 border-4 border-blue-500 border-t-transparent rounded-full"></div>
      </div>
    );
  }

  return (
    <div className="p-4 space-y-4">
      {/* Header */}
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold">💬 Comunicación</h1>
        <div className="flex gap-2">
          <button 
            onClick={() => { 
              setModalType('mensaje'); 
              resetForm(); 
              setShowModal(true); 
            }}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 flex items-center gap-2"
          >
            ✉️ Nuevo Mensaje
          </button>
          {canComunicado && (
            <button 
              onClick={() => { 
                setModalType('comunicado'); 
                resetForm(); 
                setShowModal(true); 
              }}
              className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 flex items-center gap-2"
            >
              📢 Publicar Comunicado
            </button>
          )}
        </div>
      </div>

      {/* Alertas */}
      {error && (
        <div className="p-3 bg-red-100 border border-red-300 text-red-700 rounded-lg flex justify-between">
          <span>{error}</span>
          <button onClick={() => setError('')} className="font-bold">×</button>
        </div>
      )}
      {success && (
        <div className="p-3 bg-green-100 border border-green-300 text-green-700 rounded-lg">
          {success}
        </div>
      )}

      {/* Tabs */}
      <div className="flex border-b overflow-x-auto">
        <button 
          onClick={() => setTab('mensajes')}
          className={`px-4 py-3 font-medium border-b-2 transition-colors ${
            tab === 'mensajes' 
              ? 'border-blue-600 text-blue-600' 
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          📬 Recibidos
          {mensajesNoLeidos > 0 && (
            <span className="ml-2 bg-red-500 text-white text-xs px-2 py-0.5 rounded-full">
              {mensajesNoLeidos}
            </span>
          )}
        </button>
        <button 
          onClick={() => setTab('enviados')}
          className={`px-4 py-3 font-medium border-b-2 transition-colors ${
            tab === 'enviados' 
              ? 'border-blue-600 text-blue-600' 
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          📤 Enviados ({mensajesEnviados.length})
        </button>
        <button 
          onClick={() => setTab('comunicados')}
          className={`px-4 py-3 font-medium border-b-2 transition-colors ${
            tab === 'comunicados' 
              ? 'border-blue-600 text-blue-600' 
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          📢 Comunicados ({comunicados.length})
        </button>
      </div>

      {/* Lista de Mensajes Recibidos */}
      {tab === 'mensajes' && (
        <div className="bg-white rounded-lg border shadow-sm">
          {mensajesRecibidos.length === 0 ? (
            <div className="p-12 text-center">
              <div className="text-5xl mb-4">📭</div>
              <p className="text-gray-500">No hay mensajes en tu bandeja</p>
            </div>
          ) : (
            <div className="divide-y">
              {mensajesRecibidos.map(m => (
                <div 
                  key={m.id} 
                  className={`p-4 hover:bg-gray-50 transition-colors ${
                    !m.leido ? 'bg-blue-50 border-l-4 border-l-blue-500' : ''
                  }`}
                >
                  <div className="flex justify-between items-start">
                    <div className="flex-1 cursor-pointer" onClick={() => verMensaje(m)}>
                      <div className="flex items-center gap-2">
                        <span className={`font-medium ${!m.leido ? 'text-blue-800' : 'text-gray-800'}`}>
                          {m.remitente}
                        </span>
                        {!m.leido && (
                          <span className="bg-blue-500 text-white text-xs px-2 py-0.5 rounded-full">Nuevo</span>
                        )}
                      </div>
                      <p className={`text-sm ${!m.leido ? 'font-semibold text-blue-700' : 'text-gray-600'}`}>
                        {m.asunto}
                      </p>
                      <p className="text-xs text-gray-400 mt-1">{formatFecha(m.fecha)}</p>
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => abrirResponder(m)}
                        className="px-3 py-1 bg-green-100 text-green-700 rounded-lg hover:bg-green-200 text-sm"
                      >
                        ↩️ Responder
                      </button>
                      <button
                        onClick={() => eliminarMensaje(m.id)}
                        className="px-3 py-1 bg-red-100 text-red-700 rounded-lg hover:bg-red-200 text-sm"
                      >
                        🗑️
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Lista de Mensajes Enviados */}
      {tab === 'enviados' && (
        <div className="bg-white rounded-lg border shadow-sm">
          {mensajesEnviados.length === 0 ? (
            <div className="p-12 text-center">
              <div className="text-5xl mb-4">📤</div>
              <p className="text-gray-500">No has enviado mensajes</p>
            </div>
          ) : (
            <div className="divide-y">
              {mensajesEnviados.map(m => (
                <div 
                  key={m.id} 
                  className="p-4 hover:bg-gray-50 transition-colors"
                >
                  <div className="flex justify-between items-start">
                    <div className="flex-1 cursor-pointer" onClick={() => verMensaje(m)}>
                      <span className="text-gray-500 text-sm">Para: </span>
                      <span className="font-medium text-gray-800">{m.destinatario}</span>
                      <p className="text-sm text-gray-600">{m.asunto}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-gray-400">{formatFecha(m.fecha)}</span>
                      <button
                        onClick={(e) => { e.stopPropagation(); eliminarMensaje(m.id); }}
                        className="px-2 py-1 bg-red-100 text-red-700 rounded hover:bg-red-200 text-sm"
                      >
                        🗑️
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Lista de Comunicados */}
      {tab === 'comunicados' && (
        <div className="space-y-4">
          {comunicados.length === 0 ? (
            <div className="bg-white rounded-lg border p-12 text-center">
              <div className="text-5xl mb-4">📢</div>
              <p className="text-gray-500">No hay comunicados</p>
            </div>
          ) : (
            comunicados.map(c => (
              <div key={c.id} className="bg-white rounded-lg border shadow-sm overflow-hidden">
                <div className="p-4">
                  <div className="flex justify-between items-start">
                    <div>
                      <h3 className="font-bold text-lg text-gray-800">{c.titulo}</h3>
                      <p className="text-xs text-gray-500">
                        Por {c.autor} • {formatFecha(c.fecha)}
                      </p>
                    </div>
                    {canComunicado && c.autor_id === user?.id && (
                      <div className="flex gap-2">
                        <button
                          onClick={() => abrirEditarComunicado(c)}
                          className="text-blue-600 hover:text-blue-800 text-sm"
                        >
                          ✏️ Editar
                        </button>
                        <button
                          onClick={() => eliminarComunicado(c.id)}
                          className="text-red-600 hover:text-red-800 text-sm"
                        >
                          🗑️ Eliminar
                        </button>
                      </div>
                    )}
                  </div>
                  {c.imagen && (
                    <img 
                      src={c.imagen} 
                      alt="Imagen del comunicado" 
                      className="mt-3 rounded-lg max-h-64 object-cover"
                    />
                  )}
                  <p className="mt-3 text-gray-700 whitespace-pre-wrap">{c.contenido}</p>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
            <div className="p-4 border-b flex justify-between items-center">
              <h2 className="text-lg font-bold">
                {modalType === 'mensaje' && '✉️ Nuevo Mensaje'}
                {modalType === 'responder' && '↩️ Responder Mensaje'}
                {modalType === 'comunicado' && '📢 Nuevo Comunicado'}
                {modalType === 'editarComunicado' && '✏️ Editar Comunicado'}
                {modalType === 'ver' && '📨 Mensaje'}
              </h2>
              <button onClick={() => { setShowModal(false); resetForm(); }} className="text-2xl text-gray-400 hover:text-gray-600">×</button>
            </div>
            
            <div className="p-4 space-y-4">
              {/* Ver mensaje */}
              {modalType === 'ver' && selectedItem && (
                <div className="space-y-3">
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">
                      {selectedItem.tipo === 'recibido' ? 'De:' : 'Para:'}
                    </span>
                    <span className="font-medium">
                      {selectedItem.tipo === 'recibido' ? selectedItem.remitente : selectedItem.destinatario}
                    </span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">Fecha:</span>
                    <span>{formatFecha(selectedItem.fecha)}</span>
                  </div>
                  <div className="border-t pt-3">
                    <p className="font-semibold text-gray-800">{selectedItem.asunto}</p>
                    <p className="mt-2 text-gray-700 whitespace-pre-wrap">{selectedItem.contenido}</p>
                  </div>
                  {selectedItem.tipo === 'recibido' && (
                    <button
                      onClick={() => {
                        setModalType('responder');
                        setContenido('');
                      }}
                      className="w-full py-2 bg-green-600 text-white rounded-lg hover:bg-green-700"
                    >
                      ↩️ Responder
                    </button>
                  )}
                </div>
              )}

              {/* Responder mensaje */}
              {modalType === 'responder' && selectedItem && (
                <div className="space-y-3">
                  <div className="bg-gray-50 p-3 rounded-lg text-sm">
                    <p className="text-gray-500">Respondiendo a:</p>
                    <p className="font-medium">{selectedItem.remitente}</p>
                    <p className="text-gray-600 mt-1">RE: {selectedItem.asunto}</p>
                  </div>
                  <textarea
                    value={contenido}
                    onChange={e => setContenido(e.target.value)}
                    placeholder="Escribe tu respuesta..."
                    className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                    rows={5}
                  />
                  <button
                    onClick={responderMensaje}
                    disabled={saving}
                    className="w-full py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
                  >
                    {saving ? 'Enviando...' : '📤 Enviar Respuesta'}
                  </button>
                </div>
              )}

              {/* Nuevo mensaje */}
              {modalType === 'mensaje' && (
                <div className="space-y-4">
                  {/* Tipo de destinatario */}
                  <div className="flex gap-4">
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="radio"
                        checked={tipoDestinatario === 'individual'}
                        onChange={() => setTipoDestinatario('individual')}
                        className="w-4 h-4"
                      />
                      <span>Usuario específico</span>
                    </label>
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="radio"
                        checked={tipoDestinatario === 'rol'}
                        onChange={() => setTipoDestinatario('rol')}
                        className="w-4 h-4"
                      />
                      <span>Todos de un rol</span>
                    </label>
                  </div>

                  {tipoDestinatario === 'individual' ? (
                    <select
                      value={destinatarioId}
                      onChange={e => setDestinatarioId(Number(e.target.value))}
                      className="w-full px-3 py-2 border rounded-lg"
                    >
                      <option value={0}>-- Seleccionar destinatario --</option>
                      {usuarios.filter(u => u.id !== user?.id).map(u => (
                        <option key={u.id} value={u.id}>{u.nombre_completo} ({u.role})</option>
                      ))}
                    </select>
                  ) : (
                    <select
                      value={rolDestino}
                      onChange={e => setRolDestino(e.target.value)}
                      className="w-full px-3 py-2 border rounded-lg"
                    >
                      <option value="">-- Seleccionar rol --</option>
                      {rolesDisponibles.map(r => (
                        <option key={r.value} value={r.value}>{r.label}</option>
                      ))}
                    </select>
                  )}

                  <input
                    type="text"
                    value={asunto}
                    onChange={e => setAsunto(e.target.value)}
                    placeholder="Asunto"
                    className="w-full px-3 py-2 border rounded-lg"
                  />
                  <textarea
                    value={contenido}
                    onChange={e => setContenido(e.target.value)}
                    placeholder="Mensaje..."
                    className="w-full px-3 py-2 border rounded-lg"
                    rows={5}
                  />
                  <button
                    onClick={enviarMensaje}
                    disabled={saving}
                    className="w-full py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
                  >
                    {saving ? 'Enviando...' : '📤 Enviar'}
                  </button>
                </div>
              )}

              {/* Comunicado */}
              {(modalType === 'comunicado' || modalType === 'editarComunicado') && (
                <div className="space-y-4">
                  <input
                    type="text"
                    value={titulo}
                    onChange={e => setTitulo(e.target.value)}
                    placeholder="Título del comunicado"
                    className="w-full px-3 py-2 border rounded-lg"
                  />
                  <textarea
                    value={contenido}
                    onChange={e => setContenido(e.target.value)}
                    placeholder="Contenido del comunicado..."
                    className="w-full px-3 py-2 border rounded-lg"
                    rows={5}
                  />
                  
                  {/* Subir imagen */}
                  <div>
                    <label className="block text-sm font-medium mb-1">📷 Imagen (opcional)</label>
                    <input
                      type="file"
                      accept="image/*"
                      onChange={handleImageUpload}
                      className="w-full px-3 py-2 border rounded-lg"
                    />
                    {imagen && (
                      <div className="mt-2 relative">
                        <img src={imagen} alt="Preview" className="max-h-32 rounded-lg" />
                        <button
                          onClick={() => setImagen('')}
                          className="absolute top-1 right-1 bg-red-500 text-white rounded-full w-6 h-6"
                        >
                          ×
                        </button>
                      </div>
                    )}
                  </div>

                  <button
                    onClick={guardarComunicado}
                    disabled={saving}
                    className="w-full py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50"
                  >
                    {saving ? 'Guardando...' : modalType === 'editarComunicado' ? '💾 Actualizar' : '📢 Publicar'}
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ComunicacionPage;
