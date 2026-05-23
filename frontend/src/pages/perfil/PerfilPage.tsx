import { useState, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';
import { Card, Button, Input, Alert, Badge } from '../../components/ui';

export const PerfilPage = () => {
  const { user, setUser } = useAuth();
  const [form, setForm] = useState({
    nombre: user?.nombre || '',
    apellido: user?.apellido || '',
    email: user?.email || '',
    telefono: user?.telefono || ''
  });
  const [passwordForm, setPasswordForm] = useState({
    password_actual: '',
    password_nuevo: '',
    confirmar: ''
  });
  const [notas, setNotas] = useState('');
  const [saving, setSaving] = useState(false);
  const [savingNotas, setSavingNotas] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  useEffect(() => {
    // Cargar notas guardadas del localStorage
    const notasGuardadas = localStorage.getItem(`notas_usuario_${user?.id}`);
    if (notasGuardadas) {
      setNotas(notasGuardadas);
    }
  }, [user?.id]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await api.put('/perfil', form);
      setUser(res.data.user);
      setMessage({ type: 'success', text: 'Perfil actualizado' });
    } catch (e: any) {
      setMessage({ type: 'error', text: e.response?.data?.error || 'Error al guardar' });
    } finally {
      setSaving(false);
    }
  };

  const handleChangePassword = async () => {
    if (passwordForm.password_nuevo !== passwordForm.confirmar) {
      setMessage({ type: 'error', text: 'Las contraseñas no coinciden' });
      return;
    }
    if (passwordForm.password_nuevo.length < 6) {
      setMessage({ type: 'error', text: 'La contraseña debe tener al menos 6 caracteres' });
      return;
    }

    setSaving(true);
    try {
      await api.post('/auth/cambiar-password', {
        password_actual: passwordForm.password_actual,
        password_nuevo: passwordForm.password_nuevo
      });
      setMessage({ type: 'success', text: 'Contraseña actualizada' });
      setPasswordForm({ password_actual: '', password_nuevo: '', confirmar: '' });
    } catch (e: any) {
      setMessage({ type: 'error', text: e.response?.data?.error || 'Error al cambiar contraseña' });
    } finally {
      setSaving(false);
    }
  };

  const handleSaveNotas = () => {
    setSavingNotas(true);
    try {
      localStorage.setItem(`notas_usuario_${user?.id}`, notas);
      setMessage({ type: 'success', text: 'Notas guardadas' });
    } catch (e) {
      setMessage({ type: 'error', text: 'Error al guardar notas' });
    } finally {
      setSavingNotas(false);
    }
  };

  const getRoleLabel = (role: string) => {
    const labels: Record<string, string> = {
      'direccion': 'Dirección', 'coordinador': 'Coordinador',
      'profesor': 'Profesor', 'psicologia': 'Psicología'
    };
    return labels[role] || role;
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold">👤 Mi Perfil</h1>

      {message && (
        <Alert variant={message.type} onClose={() => setMessage(null)}>{message.text}</Alert>
      )}

      {/* Info del usuario */}
      <Card>
        <div className="flex items-center gap-4 mb-6">
          <div className="w-20 h-20 rounded-full bg-gradient-to-br from-blue-400 to-blue-600 flex items-center justify-center text-white text-2xl font-bold">
            {user?.nombre?.charAt(0)}{user?.apellido?.charAt(0)}
          </div>
          <div>
            <h2 className="text-xl font-bold">{user?.nombre} {user?.apellido}</h2>
            <p className="text-gray-500">@{user?.username}</p>
            <Badge variant="info">{getRoleLabel(user?.role || '')}</Badge>
          </div>
        </div>

        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <Input
              label="Nombre"
              value={form.nombre}
              onChange={e => setForm({ ...form, nombre: e.target.value })}
            />
            <Input
              label="Apellido"
              value={form.apellido}
              onChange={e => setForm({ ...form, apellido: e.target.value })}
            />
          </div>
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
          <div className="flex justify-end">
            <Button onClick={handleSave} loading={saving}>
              Guardar Cambios
            </Button>
          </div>
        </div>
      </Card>

      {/* Notas Personales */}
      <Card title="📝 Mis Notas Personales">
        <div className="space-y-4">
          <p className="text-sm text-gray-500">
            Espacio para guardar recordatorios, pendientes o información importante.
          </p>
          <textarea
            value={notas}
            onChange={e => setNotas(e.target.value)}
            placeholder="Escribe tus notas aquí... (ej: Pendientes, recordatorios, etc.)"
            className="w-full h-40 px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 resize-none"
          />
          <div className="flex justify-between items-center">
            <span className="text-xs text-gray-400">
              {notas.length} caracteres • Guardado localmente
            </span>
            <Button onClick={handleSaveNotas} loading={savingNotas} variant="secondary">
              💾 Guardar Notas
            </Button>
          </div>
        </div>
      </Card>

      {/* Cambiar contraseña */}
      <Card title="🔐 Cambiar Contraseña">
        <div className="space-y-4">
          <Input
            label="Contraseña Actual"
            type="password"
            value={passwordForm.password_actual}
            onChange={e => setPasswordForm({ ...passwordForm, password_actual: e.target.value })}
          />
          <Input
            label="Nueva Contraseña"
            type="password"
            value={passwordForm.password_nuevo}
            onChange={e => setPasswordForm({ ...passwordForm, password_nuevo: e.target.value })}
          />
          <Input
            label="Confirmar Nueva Contraseña"
            type="password"
            value={passwordForm.confirmar}
            onChange={e => setPasswordForm({ ...passwordForm, confirmar: e.target.value })}
          />
          <div className="flex justify-end">
            <Button onClick={handleChangePassword} loading={saving} variant="secondary">
              Cambiar Contraseña
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
};

export default PerfilPage;
