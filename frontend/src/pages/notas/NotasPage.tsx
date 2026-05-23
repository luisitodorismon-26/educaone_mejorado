import { useState, useEffect } from 'react';
import api from '../../services/api';
import { StickyNote, Plus, X, Save, Pin, Edit3, Trash2, Search } from 'lucide-react';

interface NotaPersonal {
  id: number; titulo: string; contenido: string; color: string;
  fijada: boolean; fecha_creacion: string; fecha_actualizacion: string;
}

export const NotasPage = () => {
  const [notas, setNotas] = useState<NotaPersonal[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [viewingNota, setViewingNota] = useState<NotaPersonal | null>(null);
  const [form, setForm] = useState({ titulo: '', contenido: '', color: 'yellow' });
  const [buscar, setBuscar] = useState('');

  const colores: Record<string, { bg: string; border: string; header: string; dot: string }> = {
    yellow: { bg: 'bg-yellow-50', border: 'border-yellow-200', header: 'bg-yellow-100', dot: 'bg-yellow-400' },
    blue: { bg: 'bg-blue-50', border: 'border-blue-200', header: 'bg-blue-100', dot: 'bg-blue-400' },
    green: { bg: 'bg-emerald-50', border: 'border-emerald-200', header: 'bg-emerald-100', dot: 'bg-emerald-400' },
    pink: { bg: 'bg-pink-50', border: 'border-pink-200', header: 'bg-pink-100', dot: 'bg-pink-400' },
    purple: { bg: 'bg-purple-50', border: 'border-purple-200', header: 'bg-purple-100', dot: 'bg-purple-400' },
  };

  useEffect(() => { cargarNotas(); }, []);

  const cargarNotas = async () => {
    try {
      const res = await api.get('/notas-personales');
      setNotas(res.data || []);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  };

  const guardar = async () => {
    if (!form.titulo.trim() && !form.contenido.trim()) return;
    try {
      if (editingId) {
        const res = await api.put(`/notas-personales/${editingId}`, form);
        setNotas(notas.map(n => n.id === editingId ? res.data : n));
      } else {
        const res = await api.post('/notas-personales', form);
        setNotas([res.data, ...notas]);
      }
      setShowForm(false); setEditingId(null); setForm({ titulo: '', contenido: '', color: 'yellow' });
    } catch (e) { console.error(e); }
  };

  const eliminar = async (id: number) => {
    if (!confirm('¿Eliminar esta nota?')) return;
    try { await api.delete(`/notas-personales/${id}`); setNotas(notas.filter(n => n.id !== id)); } catch (e) {}
  };

  const fijar = async (nota: NotaPersonal) => {
    try {
      const res = await api.put(`/notas-personales/${nota.id}`, { fijada: !nota.fijada });
      setNotas(notas.map(n => n.id === nota.id ? res.data : n).sort((a, b) => (a.fijada === b.fijada ? 0 : a.fijada ? -1 : 1)));
    } catch (e) {}
  };

  const editar = (nota: NotaPersonal) => {
    setForm({ titulo: nota.titulo, contenido: nota.contenido, color: nota.color });
    setEditingId(nota.id);
    setShowForm(true);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const notasFiltradas = notas.filter(n => {
    if (!buscar) return true;
    const q = buscar.toLowerCase();
    return (n.titulo || '').toLowerCase().includes(q) || (n.contenido || '').toLowerCase().includes(q);
  });

  if (loading) return <div className="flex justify-center py-12"><div className="animate-spin rounded-full h-12 w-12 border-b-2 border-yellow-500"></div></div>;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div className="flex items-center gap-3">
          <StickyNote className="text-yellow-500" size={28} />
          <div>
            <h1 className="text-2xl font-bold text-slate-800">Mis Notas</h1>
            <p className="text-sm text-gray-500">{notas.length} nota{notas.length !== 1 ? 's' : ''} • {notas.filter(n => n.fijada).length} fijada{notas.filter(n => n.fijada).length !== 1 ? 's' : ''}</p>
          </div>
        </div>
        <button
          onClick={() => { setShowForm(true); setEditingId(null); setForm({ titulo: '', contenido: '', color: 'yellow' }); }}
          className="flex items-center gap-2 px-4 py-2 bg-yellow-500 text-white rounded-lg hover:bg-yellow-600 font-medium text-sm shadow-sm"
        >
          <Plus size={18} /> Nueva Nota
        </button>
      </div>

      {/* Buscador */}
      {notas.length > 3 && (
        <div className="relative">
          <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text" placeholder="Buscar en mis notas..." value={buscar}
            onChange={e => setBuscar(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 border rounded-xl text-sm focus:ring-2 focus:ring-yellow-400 focus:border-yellow-400"
          />
        </div>
      )}

      {/* Formulario */}
      {showForm && (
        <div className="bg-white rounded-xl shadow-sm border p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-bold text-gray-800">{editingId ? 'Editar Nota' : 'Nueva Nota'}</h2>
            <button onClick={() => { setShowForm(false); setEditingId(null); }} className="text-gray-400 hover:text-gray-600"><X size={22} /></button>
          </div>
          <input
            type="text" placeholder="Título de la nota..." value={form.titulo}
            onChange={e => setForm({ ...form, titulo: e.target.value })}
            className="w-full px-4 py-2.5 border rounded-lg text-sm focus:ring-2 focus:ring-yellow-400 mb-3 font-medium"
          />
          <textarea
            placeholder="Escribe el contenido aquí..." value={form.contenido}
            onChange={e => setForm({ ...form, contenido: e.target.value })}
            rows={5} className="w-full px-4 py-2.5 border rounded-lg text-sm focus:ring-2 focus:ring-yellow-400 mb-4"
          />
          <div className="flex items-center justify-between">
            <div className="flex gap-2 items-center">
              <span className="text-xs text-gray-500 mr-1">Color:</span>
              {Object.entries(colores).map(([key, c]) => (
                <button key={key} onClick={() => setForm({ ...form, color: key })}
                  className={`w-7 h-7 rounded-full border-2 ${c.dot} ${form.color === key ? 'border-gray-600 ring-2 ring-offset-1 ring-gray-400 scale-110' : 'border-transparent'} transition-transform`}
                />
              ))}
            </div>
            <div className="flex gap-2">
              <button onClick={() => { setShowForm(false); setEditingId(null); }} className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg">Cancelar</button>
              <button onClick={guardar} className="flex items-center gap-1 px-5 py-2 bg-yellow-500 text-white text-sm rounded-lg hover:bg-yellow-600 font-medium">
                <Save size={16} /> {editingId ? 'Actualizar' : 'Guardar'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Notas Grid */}
      {notasFiltradas.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {notasFiltradas.map(nota => {
            const c = colores[nota.color] || colores.yellow;
            return (
              <div key={nota.id} className={`${c.bg} ${c.border} border rounded-xl overflow-hidden hover:shadow-md transition-shadow`}>
                <div className={`${c.header} px-4 py-2.5 flex items-center justify-between`}>
                  <div className="flex items-center gap-2 min-w-0 flex-1">
                    {nota.fijada && <Pin size={13} className="text-blue-600 flex-shrink-0" fill="currentColor" />}
                    <p className="font-semibold text-sm text-gray-800 truncate">{nota.titulo || 'Sin título'}</p>
                  </div>
                  <div className="flex items-center gap-0.5 flex-shrink-0 ml-2">
                    <button onClick={() => fijar(nota)} className={`p-1.5 rounded-lg hover:bg-white/60 ${nota.fijada ? 'text-blue-600' : 'text-gray-400'}`} title={nota.fijada ? 'Desfijar' : 'Fijar'}><Pin size={14} /></button>
                    <button onClick={() => editar(nota)} className="p-1.5 rounded-lg hover:bg-white/60 text-gray-400 hover:text-blue-600" title="Editar"><Edit3 size={14} /></button>
                    <button onClick={() => eliminar(nota.id)} className="p-1.5 rounded-lg hover:bg-white/60 text-gray-400 hover:text-red-600" title="Eliminar"><Trash2 size={14} /></button>
                  </div>
                </div>
                <div className="px-4 py-3 cursor-pointer" onClick={() => setViewingNota(nota)}>
                  <p className="text-sm text-gray-700 whitespace-pre-wrap line-clamp-6">{nota.contenido}</p>
                  <p className="text-xs text-gray-400 mt-3">
                    {new Date(nota.fecha_actualizacion).toLocaleDateString('es-DO', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      ) : buscar ? (
        <div className="text-center py-12 bg-gray-50 rounded-xl border-2 border-dashed">
          <Search size={40} className="mx-auto mb-3 text-gray-300" />
          <p className="text-gray-500">No se encontraron notas con "{buscar}"</p>
        </div>
      ) : !showForm && (
        <div className="text-center py-12 bg-yellow-50 rounded-xl border-2 border-dashed border-yellow-200">
          <StickyNote size={48} className="mx-auto mb-3 text-yellow-300" />
          <p className="text-gray-600 font-medium">No tienes notas aún</p>
          <p className="text-sm text-gray-400 mt-1">Crea una nota para recordar algo importante</p>
          <button onClick={() => setShowForm(true)} className="mt-4 px-4 py-2 bg-yellow-500 text-white rounded-lg text-sm hover:bg-yellow-600">
            <Plus size={16} className="inline mr-1" /> Crear primera nota
          </button>
        </div>
      )}
      {/* Modal de Vista de Nota */}
      {viewingNota && (() => {
        const vc = colores[viewingNota.color] || colores.yellow;
        return (
          <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setViewingNota(null)}>
            <div className={`${vc.bg} ${vc.border} border rounded-2xl w-full max-w-lg max-h-[80vh] overflow-y-auto shadow-xl`} onClick={e => e.stopPropagation()}>
              <div className={`${vc.header} px-5 py-4 flex items-center justify-between border-b ${vc.border}`}>
                <div className="flex items-center gap-2">
                  {viewingNota.fijada && <Pin size={14} className="text-blue-600" fill="currentColor" />}
                  <h2 className="font-bold text-gray-800">{viewingNota.titulo || 'Sin título'}</h2>
                </div>
                <div className="flex items-center gap-1">
                  <button onClick={() => { editar(viewingNota); setViewingNota(null); }} className="p-1.5 rounded-lg hover:bg-white/60 text-gray-500 hover:text-blue-600" title="Editar"><Edit3 size={16} /></button>
                  <button onClick={() => setViewingNota(null)} className="p-1.5 rounded-lg hover:bg-white/60 text-gray-500 hover:text-gray-700"><X size={18} /></button>
                </div>
              </div>
              <div className="px-5 py-4">
                <p className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">{viewingNota.contenido}</p>
              </div>
              <div className={`px-5 py-3 border-t ${vc.border} text-xs text-gray-400`}>
                {new Date(viewingNota.fecha_actualizacion).toLocaleDateString('es-DO', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit' })}
              </div>
            </div>
          </div>
        );
      })()}
    </div>
  );
};

export default NotasPage;
