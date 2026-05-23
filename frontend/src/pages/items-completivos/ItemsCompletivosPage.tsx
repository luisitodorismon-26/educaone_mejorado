import { useState, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';
import { Modal, Input, Select, Button, Alert, Spinner } from '../../components/ui';
import { ClipboardCheck, Plus, Edit2, Trash2 } from 'lucide-react';

interface ItemCompletivo {
  id: number;
  curso_id: number;
  curso: string;
  asignatura_id: number;
  asignatura: string;
  periodo: number;
  nombre: string;
  descripcion?: string | null;
  fecha?: string | null;
  peso?: number | null;
  profesor: string;
  profesor_id: number;
}

interface Curso {
  id: number;
  nombre_completo: string;
  grado?: string;
  nombre?: string;
  tanda?: string;
}

interface Asignatura {
  id: number;
  nombre: string;
}

const initialForm = {
  curso_id: 0,
  asignatura_id: 0,
  periodo: 1,
  nombre: '',
  descripcion: '',
  fecha: '',
  peso: '' as string | number,
};

export const ItemsCompletivosPage = () => {
  const { user } = useAuth();
  const esProfesor = user?.role === 'profesor';
  const esDireccion = user?.role === 'direccion' || user?.role === 'coordinador';

  const [items, setItems] = useState<ItemCompletivo[]>([]);
  const [cursos, setCursos] = useState<Curso[]>([]);
  const [asignaturas, setAsignaturas] = useState<Asignatura[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [editando, setEditando] = useState<ItemCompletivo | null>(null);
  const [form, setForm] = useState(initialForm);
  const [mensaje, setMensaje] = useState<{ tipo: 'success' | 'error'; texto: string } | null>(null);

  // Filtros
  const [filtroCurso, setFiltroCurso] = useState<number | ''>('');
  const [filtroAsignatura, setFiltroAsignatura] = useState<number | ''>('');
  const [filtroPeriodo, setFiltroPeriodo] = useState<number | ''>('');

  useEffect(() => { loadData(); }, []);
  useEffect(() => { loadItems(); /* eslint-disable-next-line */ }, [filtroCurso, filtroAsignatura, filtroPeriodo]);

  const loadData = async () => {
    try {
      const [cursosRes, asigRes] = await Promise.all([
        api.get('/cursos'),
        api.get('/asignaturas'),
      ]);
      setCursos(cursosRes.data || []);
      setAsignaturas(asigRes.data || []);
      await loadItems();
    } catch (e: any) {
      setMensaje({ tipo: 'error', texto: e.response?.data?.error || 'Error al cargar datos' });
    } finally {
      setLoading(false);
    }
  };

  const loadItems = async () => {
    try {
      const params = new URLSearchParams();
      if (filtroCurso) params.append('curso_id', String(filtroCurso));
      if (filtroAsignatura) params.append('asignatura_id', String(filtroAsignatura));
      if (filtroPeriodo) params.append('periodo', String(filtroPeriodo));
      const url = `/items-completivos${params.toString() ? '?' + params.toString() : ''}`;
      const res = await api.get(url);
      setItems(res.data || []);
    } catch (e: any) {
      setMensaje({ tipo: 'error', texto: e.response?.data?.error || 'Error al cargar items' });
    }
  };

  const openNuevo = () => {
    setEditando(null);
    setForm(initialForm);
    setShowModal(true);
  };

  const openEditar = (item: ItemCompletivo) => {
    setEditando(item);
    setForm({
      curso_id: item.curso_id,
      asignatura_id: item.asignatura_id,
      periodo: item.periodo,
      nombre: item.nombre,
      descripcion: item.descripcion || '',
      fecha: item.fecha || '',
      peso: item.peso ?? '',
    });
    setShowModal(true);
  };

  const guardar = async () => {
    if (!form.nombre.trim()) {
      setMensaje({ tipo: 'error', texto: 'El nombre del ítem es requerido' });
      return;
    }
    if (!editando && (!form.curso_id || !form.asignatura_id)) {
      setMensaje({ tipo: 'error', texto: 'Curso y asignatura son requeridos' });
      return;
    }
    setSaving(true);
    try {
      const payload: any = {
        nombre: form.nombre.trim(),
        descripcion: form.descripcion || null,
        fecha: form.fecha || null,
        peso: form.peso === '' ? null : Number(form.peso),
      };
      if (!editando) {
        payload.curso_id = form.curso_id;
        payload.asignatura_id = form.asignatura_id;
        payload.periodo = form.periodo;
        await api.post('/items-completivos', payload);
        setMensaje({ tipo: 'success', texto: 'Ítem creado' });
      } else {
        await api.put(`/items-completivos/${editando.id}`, payload);
        setMensaje({ tipo: 'success', texto: 'Ítem actualizado' });
      }
      setShowModal(false);
      loadItems();
    } catch (e: any) {
      setMensaje({ tipo: 'error', texto: e.response?.data?.error || 'Error al guardar' });
    } finally {
      setSaving(false);
    }
  };

  const eliminar = async (item: ItemCompletivo) => {
    if (!confirm(`¿Eliminar el ítem "${item.nombre}"?`)) return;
    try {
      await api.delete(`/items-completivos/${item.id}`);
      setMensaje({ tipo: 'success', texto: 'Ítem eliminado' });
      loadItems();
    } catch (e: any) {
      setMensaje({ tipo: 'error', texto: e.response?.data?.error || 'Error al eliminar' });
    }
  };

  if (loading) return <div className="flex justify-center py-12"><Spinner /></div>;

  return (
    <div className="space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
            <ClipboardCheck className="text-indigo-600" />
            Detalle de evaluaciones (Registro)
          </h2>
          <p className="text-sm text-gray-500">
            Actividades evaluativas registradas por período (exámenes, tareas, proyectos).
            Aparecen en el registro escolar MINERD.
          </p>
        </div>
        {(esProfesor || esDireccion) && (
          <Button onClick={openNuevo} icon={<Plus size={16} />}>Nuevo ítem</Button>
        )}
      </div>

      {mensaje && <Alert variant={mensaje.tipo} onClose={() => setMensaje(null)}>{mensaje.texto}</Alert>}

      {/* Filtros */}
      <div className="bg-white rounded-xl border p-4 grid grid-cols-1 sm:grid-cols-3 gap-3">
        <Select
          label="Curso"
          value={filtroCurso}
          onChange={e => setFiltroCurso(e.target.value ? parseInt(e.target.value) : '')}
          options={[{ value: '', label: 'Todos los cursos' }, ...cursos.map(c => ({
            value: c.id,
            label: c.grado ? `${c.grado} ${c.nombre}` : c.nombre_completo,
          }))]}
        />
        <Select
          label="Asignatura"
          value={filtroAsignatura}
          onChange={e => setFiltroAsignatura(e.target.value ? parseInt(e.target.value) : '')}
          options={[{ value: '', label: 'Todas' }, ...asignaturas.map(a => ({ value: a.id, label: a.nombre }))]}
        />
        <Select
          label="Período"
          value={filtroPeriodo}
          onChange={e => setFiltroPeriodo(e.target.value ? parseInt(e.target.value) : '')}
          options={[
            { value: '', label: 'Todos' },
            { value: 1, label: 'Período 1' },
            { value: 2, label: 'Período 2' },
            { value: 3, label: 'Período 3' },
            { value: 4, label: 'Período 4' },
          ]}
        />
      </div>

      {/* Tabla */}
      {items.length === 0 ? (
        <div className="bg-white rounded-xl border p-8 text-center text-gray-500">
          <ClipboardCheck size={40} className="mx-auto text-gray-300 mb-2" />
          <p>No hay ítems completivos cargados</p>
          {(esProfesor || esDireccion) && (
            <p className="text-xs mt-1">Click en "Nuevo ítem" para empezar.</p>
          )}
        </div>
      ) : (
        <div className="bg-white rounded-xl border overflow-hidden">
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="bg-gray-50 text-left">
                  <th className="px-4 py-2 text-gray-600 font-medium">Período</th>
                  <th className="px-4 py-2 text-gray-600 font-medium">Curso</th>
                  <th className="px-4 py-2 text-gray-600 font-medium">Asignatura</th>
                  <th className="px-4 py-2 text-gray-600 font-medium">Ítem</th>
                  <th className="px-4 py-2 text-gray-600 font-medium">Fecha</th>
                  <th className="px-4 py-2 text-gray-600 font-medium text-center">Peso</th>
                  {esDireccion && <th className="px-4 py-2 text-gray-600 font-medium">Profesor</th>}
                  <th className="px-4 py-2 text-gray-600 font-medium text-right">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {items.map(item => (
                  <tr key={item.id} className="border-t hover:bg-gray-50">
                    <td className="px-4 py-2">
                      <span className="inline-block px-2 py-0.5 bg-indigo-100 text-indigo-700 text-xs font-medium rounded">
                        P{item.periodo}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-gray-700">{item.curso}</td>
                    <td className="px-4 py-2 text-gray-700">{item.asignatura}</td>
                    <td className="px-4 py-2">
                      <div className="font-medium text-gray-800">{item.nombre}</div>
                      {item.descripcion && (
                        <div className="text-xs text-gray-500 mt-0.5">{item.descripcion}</div>
                      )}
                    </td>
                    <td className="px-4 py-2 text-gray-600 text-xs">{item.fecha || '—'}</td>
                    <td className="px-4 py-2 text-center">
                      {item.peso !== null && item.peso !== undefined ? (
                        <span className="text-gray-700 font-medium">{item.peso}%</span>
                      ) : '—'}
                    </td>
                    {esDireccion && <td className="px-4 py-2 text-gray-600 text-xs">{item.profesor}</td>}
                    <td className="px-4 py-2 text-right">
                      {/* Profesor solo edita los suyos; dirección puede editar todos */}
                      {(esDireccion || (esProfesor && item.profesor_id === user?.id)) && (
                        <div className="flex gap-2 justify-end">
                          <button
                            onClick={() => openEditar(item)}
                            className="text-blue-600 hover:text-blue-800 text-sm"
                          >
                            <Edit2 size={14} className="inline" />
                          </button>
                          <button
                            onClick={() => eliminar(item)}
                            className="text-red-600 hover:text-red-800 text-sm"
                          >
                            <Trash2 size={14} className="inline" />
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Modal crear/editar */}
      <Modal
        isOpen={showModal}
        onClose={() => setShowModal(false)}
        title={editando ? 'Editar ítem' : 'Nuevo ítem completivo'}
        size="md"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowModal(false)}>Cancelar</Button>
            <Button onClick={guardar} loading={saving}>
              {editando ? 'Guardar cambios' : 'Crear ítem'}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {!editando && (
            <>
              <Select
                label="Curso *"
                value={form.curso_id}
                onChange={e => setForm({ ...form, curso_id: parseInt(e.target.value) || 0 })}
                options={[
                  { value: 0, label: 'Seleccionar curso' },
                  ...cursos.map(c => ({
                    value: c.id,
                    label: c.grado ? `${c.grado} ${c.nombre}` : c.nombre_completo,
                  })),
                ]}
              />
              <Select
                label="Asignatura *"
                value={form.asignatura_id}
                onChange={e => setForm({ ...form, asignatura_id: parseInt(e.target.value) || 0 })}
                options={[
                  { value: 0, label: 'Seleccionar asignatura' },
                  ...asignaturas.map(a => ({ value: a.id, label: a.nombre })),
                ]}
              />
              <Select
                label="Período *"
                value={form.periodo}
                onChange={e => setForm({ ...form, periodo: parseInt(e.target.value) })}
                options={[
                  { value: 1, label: 'Período 1' },
                  { value: 2, label: 'Período 2' },
                  { value: 3, label: 'Período 3' },
                  { value: 4, label: 'Período 4' },
                ]}
              />
            </>
          )}
          {editando && (
            <div className="bg-gray-50 rounded-lg p-3 text-sm text-gray-600">
              <span className="font-medium">{editando.curso}</span> · {editando.asignatura} · Período {editando.periodo}
            </div>
          )}
          <Input
            label="Nombre del ítem *"
            value={form.nombre}
            onChange={e => setForm({ ...form, nombre: e.target.value })}
            placeholder="Ej. Examen parcial, Tarea 1, Proyecto final"
            required
          />
          <Input
            label="Descripción (opcional)"
            value={form.descripcion}
            onChange={e => setForm({ ...form, descripcion: e.target.value })}
            placeholder="Detalles del ítem"
          />
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Fecha (opcional)"
              type="date"
              value={form.fecha}
              onChange={e => setForm({ ...form, fecha: e.target.value })}
            />
            <Input
              label="Peso % (opcional)"
              type="number"
              min={0}
              max={100}
              value={form.peso}
              onChange={e => setForm({ ...form, peso: e.target.value })}
              placeholder="0-100"
            />
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default ItemsCompletivosPage;
