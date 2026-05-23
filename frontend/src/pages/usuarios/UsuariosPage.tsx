import { useState, useEffect } from 'react';
import api from '../../services/api';
import { DataTable, Modal, Input, Select, Button, Badge, Alert } from '../../components/ui';

interface Usuario {
  id: number;
  username: string;
  nombre: string;
  apellido: string;
  nombre_completo: string;
  email: string;
  telefono: string;
  role: string;
  tanda_id: number;
  tanda: string;
  activo: boolean;
}

interface Tanda {
  id: number;
  nombre: string;
}

const initialForm = {
  username: '', nombre: '', apellido: '', email: '', telefono: '',
  role: 'profesor', tanda_id: 0, password: ''
};

export const UsuariosPage = () => {
  const [usuarios, setUsuarios] = useState<Usuario[]>([]);
  const [tandas, setTandas] = useState<Tanda[]>([]);
  const [showModal, setShowModal] = useState(false);
  const [editando, setEditando] = useState<Usuario | null>(null);
  const [form, setForm] = useState(initialForm);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    try {
      const [u, t] = await Promise.all([api.get('/usuarios'), api.get('/tandas')]);
      setUsuarios(u.data);
      setTandas(t.data);
    } catch (e) {
      setMessage({ type: 'error', text: 'Error al cargar datos' });
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    // Validaciones
    if (!form.username.trim()) {
      setMessage({ type: 'error', text: 'El nombre de usuario es requerido' });
      return;
    }
    if (!form.nombre.trim()) {
      setMessage({ type: 'error', text: 'El nombre es requerido' });
      return;
    }
    if (!form.role) {
      setMessage({ type: 'error', text: 'Debe seleccionar un rol' });
      return;
    }
    if (!editando && !form.password) {
      setMessage({ type: 'error', text: 'La contraseña es requerida para nuevos usuarios' });
      return;
    }
    
    try {
      if (editando) {
        await api.put(`/usuarios/${editando.id}`, form);
        setMessage({ type: 'success', text: 'Usuario actualizado correctamente' });
      } else {
        await api.post('/usuarios', { ...form, password: form.password || '123456' });
        setMessage({ type: 'success', text: 'Usuario creado correctamente' });
      }
      loadData();
      closeModal();
    } catch (e: any) {
      setMessage({ type: 'error', text: e.response?.data?.error || 'Error al guardar' });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('¿Desactivar este usuario?')) return;
    try {
      await api.delete(`/usuarios/${id}`);
      setMessage({ type: 'success', text: 'Usuario desactivado' });
      loadData();
    } catch (e) {
      setMessage({ type: 'error', text: 'Error al desactivar usuario' });
    }
  };

  const openEdit = (u: Usuario) => {
    setEditando(u);
    setForm({
      username: u.username,
      nombre: u.nombre,
      apellido: u.apellido || '',
      email: u.email || '',
      telefono: u.telefono || '',
      role: u.role,
      tanda_id: u.tanda_id || 0,
      password: ''
    });
    setShowModal(true);
  };

  const closeModal = () => {
    setShowModal(false);
    setEditando(null);
    setForm(initialForm);
  };

  const getRoleVariant = (role: string): 'default' | 'success' | 'warning' | 'danger' | 'info' => {
    const variants: Record<string, 'default' | 'success' | 'warning' | 'danger' | 'info'> = {
      direccion: 'info',
      coordinador: 'warning',
      profesor: 'success',
      psicologia: 'default'
    };
    return variants[role] || 'default';
  };

  const columns = [
    {
      key: 'username',
      label: 'Usuario',
      render: (u: Usuario) => <span className="font-mono text-sm">{u.username}</span>
    },
    {
      key: 'nombre_completo',
      label: 'Nombre',
      render: (u: Usuario) => (
        <div>
          <p className="font-medium">{u.nombre_completo}</p>
          {u.email && <p className="text-sm text-gray-500">{u.email}</p>}
        </div>
      )
    },
    {
      key: 'role',
      label: 'Rol',
      render: (u: Usuario) => (
        <Badge variant={getRoleVariant(u.role)}>
          {u.role === 'direccion' ? 'Dirección' :
           u.role === 'coordinador' ? 'Coordinador' :
           u.role === 'profesor' ? 'Profesor' :
           u.role === 'psicologia' ? 'Psicología' : u.role}
        </Badge>
      )
    },
    {
      key: 'tanda',
      label: 'Tanda',
      render: (u: Usuario) => u.tanda || <span className="text-gray-400">-</span>
    },
    {
      key: 'telefono',
      label: 'Teléfono',
      render: (u: Usuario) => u.telefono || <span className="text-gray-400">-</span>
    }
  ];

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">👥 Usuarios</h1>
          <p className="text-gray-500">{usuarios.length} usuarios registrados</p>
        </div>
        <Button onClick={() => setShowModal(true)} icon={<span>+</span>}>
          Nuevo Usuario
        </Button>
      </div>

      {/* Mensajes */}
      {message && (
        <Alert variant={message.type === 'success' ? 'success' : 'error'} onClose={() => setMessage(null)}>
          {message.text}
        </Alert>
      )}

      {/* Tabla */}
      <DataTable
        data={usuarios}
        columns={columns}
        searchKeys={['nombre_completo', 'username', 'email']}
        exportFilename="usuarios"
        emptyMessage="No hay usuarios registrados"
        actions={(u) => (
          <div className="flex gap-2 justify-end">
            <button onClick={() => openEdit(u)} className="text-blue-600 hover:text-blue-800 text-sm">
              Editar
            </button>
            <button onClick={() => handleDelete(u.id)} className="text-red-600 hover:text-red-800 text-sm">
              Desactivar
            </button>
          </div>
        )}
      />

      {/* Modal */}
      <Modal
        isOpen={showModal}
        onClose={closeModal}
        title={editando ? 'Editar Usuario' : 'Nuevo Usuario'}
        size="lg"
        footer={
          <>
            <Button variant="secondary" onClick={closeModal}>Cancelar</Button>
            <Button onClick={handleSave} loading={saving}>
              {editando ? 'Guardar Cambios' : 'Crear Usuario'}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Input
            label="Usuario"
            value={form.username}
            onChange={e => setForm({ ...form, username: e.target.value })}
            disabled={!!editando}
            required
          />
          <div className="grid grid-cols-2 gap-4">
            <Input
              label="Nombre"
              value={form.nombre}
              onChange={e => setForm({ ...form, nombre: e.target.value })}
              required
            />
            <Input
              label="Apellido"
              value={form.apellido}
              onChange={e => setForm({ ...form, apellido: e.target.value })}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Input
              label="Email"
              type="email"
              value={form.email}
              onChange={e => setForm({ ...form, email: e.target.value })}
            />
            <Input
              label="Teléfono"
              value={form.telefono}
              onChange={e => setForm({ ...form, telefono: e.target.value })}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Select
              label="Rol"
              value={form.role}
              onChange={e => setForm({ ...form, role: e.target.value })}
              options={[
                { value: 'profesor', label: '👨‍🏫 Profesor' },
                { value: 'coordinador', label: '👔 Coordinador' },
                { value: 'psicologia', label: '🧠 Psicología' },
                { value: 'direccion', label: '🏫 Dirección' }
              ]}
            />
            {/* Tanda solo para Coordinador y Psicología */}
            {(form.role === 'coordinador' || form.role === 'psicologia') && (
              <Select
                label="Tanda Asignada"
                value={form.tanda_id}
                onChange={e => setForm({ ...form, tanda_id: parseInt(e.target.value) })}
                options={[
                  { value: 0, label: '-- Todas las tandas --' },
                  ...tandas.map(t => ({ value: t.id, label: t.nombre }))
                ]}
              />
            )}
            {(form.role === 'coordinador' || form.role === 'psicologia') && (
              <p className="text-xs text-gray-500 -mt-2">
                Limita su acceso a esa tanda. "Todas" = acceso completo.
              </p>
            )}
          </div>
          <Input
            label={editando ? "Nueva Contraseña (dejar vacío para mantener)" : "Contraseña"}
            type="password"
            value={form.password}
            onChange={e => setForm({ ...form, password: e.target.value })}
            placeholder={editando ? "••••••••" : ""}
          />
          {!editando && (
            <p className="text-sm text-gray-500">
              Si no especifica una contraseña, se asignará "123456" por defecto.
            </p>
          )}
        </div>
      </Modal>
    </div>
  );
};

export default UsuariosPage;
