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
  nivel_asignado?: string | null; // v2.15: 'primaria' | 'secundaria' | null (ambos)
  activo: boolean;
}

interface Tanda {
  id: number;
  nombre: string;
}

const initialForm = {
  username: '', nombre: '', apellido: '', email: '', telefono: '',
  role: 'profesor', tanda_id: 0, nivel_asignado: '', password: ''
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

  // v2.19: los profesores que dejan el colegio quedan INACTIVOS, nunca se
  // borran, porque su historial (reportes, asistencias, evaluaciones) sigue
  // apuntando a su cuenta. Dirección necesita poder verlos.
  const [estado, setEstado] = useState<'activos' | 'inactivos' | 'todos'>('activos');

  // Restablecer contraseña y Reemplazar profesor son acciones separadas.
  const [resetUser, setResetUser] = useState<Usuario | null>(null);
  const [resetPw, setResetPw] = useState('');
  const [reemplazarUser, setReemplazarUser] = useState<Usuario | null>(null);
  const [nuevoProf, setNuevoProf] = useState({
    username: '', password: '', nombre: '', apellido: '', email: '', telefono: '',
  });
  // v2.19: a mitad de año lo habitual es que otro profesor DEL COLEGIO asuma
  // los cursos, no que se contrate a alguien. Por eso hay dos modos.
  const [modoReemplazo, setModoReemplazo] = useState<'existente' | 'nuevo'>('existente');
  const [profesorDestino, setProfesorDestino] = useState<number>(0);

  useEffect(() => { loadData(); }, [estado]);

  const loadData = async () => {
    try {
      const [u, t] = await Promise.all([
        api.get(`/usuarios?estado=${estado}`),
        api.get('/tandas'),
      ]);
      setUsuarios(u.data);
      setTandas(t.data);
    } catch (e) {
      setMessage({ type: 'error', text: 'Error al cargar datos' });
    } finally {
      setLoading(false);
    }
  };

  const handleReactivar = async (u: Usuario) => {
    if (!confirm(`¿Reactivar a ${u.nombre_completo}?`)) return;
    try {
      await api.post(`/usuarios/${u.id}/reactivar`);
      setMessage({ type: 'success', text: `${u.nombre_completo} fue reactivado` });
      loadData();
    } catch (e: any) {
      setMessage({ type: 'error', text: e.response?.data?.error || 'Error al reactivar' });
    }
  };

  const handleReset = async () => {
    if (!resetUser) return;
    if (!resetPw.trim()) {
      setMessage({ type: 'error', text: 'Escriba la contraseña temporal.' });
      return;
    }
    setSaving(true);
    try {
      await api.post(`/usuarios/${resetUser.id}/reset-password`, { password: resetPw });
      setMessage({
        type: 'success',
        text: `Contraseña restablecida. ${resetUser.nombre_completo} deberá cambiarla en su próximo acceso.`,
      });
      setResetUser(null);
      setResetPw('');
    } catch (e: any) {
      setMessage({ type: 'error', text: e.response?.data?.error || 'Error al restablecer' });
    } finally {
      setSaving(false);
    }
  };

  const handleReemplazar = async () => {
    if (!reemplazarUser) return;
    let payload: any;
    if (modoReemplazo === 'existente') {
      if (!profesorDestino) {
        setMessage({ type: 'error', text: 'Seleccione el profesor que asumirá los cursos.' });
        return;
      }
      payload = { reemplazar_por_id: profesorDestino };
    } else {
      if (!nuevoProf.username.trim() || !nuevoProf.nombre.trim()) {
        setMessage({ type: 'error', text: 'Usuario y nombre del nuevo profesor son requeridos.' });
        return;
      }
      if (!nuevoProf.password.trim()) {
        setMessage({ type: 'error', text: 'Escriba la contraseña inicial del nuevo profesor.' });
        return;
      }
      payload = { nuevo: nuevoProf };
    }
    setSaving(true);
    try {
      const r = await api.post(`/usuarios/${reemplazarUser.id}/reemplazar`, payload);
      const t = r.data.transferido || {};
      setMessage({
        type: 'success',
        text: `${r.data.message} Se transfirieron ${t.asignaciones ?? 0} asignación(es) y ${t.horarios ?? 0} bloque(s) de horario.`,
      });
      setReemplazarUser(null);
      setNuevoProf({ username: '', password: '', nombre: '', apellido: '', email: '', telefono: '' });
      setProfesorDestino(0);
      loadData();
    } catch (e: any) {
      const d = e.response?.data;
      setMessage({
        type: 'error',
        text: d?.conflictos ? `${d.error} ${d.conflictos.join(' · ')}` : (d?.error || 'Error al reemplazar'),
      });
    } finally {
      setSaving(false);
    }
  };

  const handleSave = async () => {
    // Las validaciones van ANTES de setSaving(true): si faltaba un campo, los
    // return dejaban el botón en "cargando" para siempre y había que cerrar el
    // modal para recuperarlo.
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
    
    setSaving(true);
    try {
      if (editando) {
        // v2.19: el PUT ya no acepta `password` (devuelve 400). Se excluye del
        // payload para no mandar el campo vacío que arrastra el estado del form.
        const { password: _omitida, ...datosEdicion } = form;
        await api.put(`/usuarios/${editando.id}`, datosEdicion);
        setMessage({ type: 'success', text: 'Usuario actualizado correctamente' });
      } else {
        // v2.19: la contraseña la escribe Dirección, sin fallback. El
        // `|| '123456'` anterior era una contraseña automática encubierta: si
        // el campo llegaba vacío se creaba la cuenta con una clave conocida.
        // Hoy además el backend la rechazaría por débil, así que el usuario
        // vería un error confuso en vez de "falta la contraseña".
        await api.post('/usuarios', form);
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
    } catch (e: any) {
      // El backend devuelve 409 con el motivo exacto ("todavía tiene N
      // asignación(es) activa(s)... Reemplácelo o quítele las asignaciones").
      // Mostrar un genérico dejaba a Dirección sin saber qué hacer.
      setMessage({
        type: 'error',
        text: e.response?.data?.error || 'Error al desactivar usuario',
      });
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
      nivel_asignado: u.nivel_asignado || '',
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
      psicologia: 'default',
      secretaria: 'info'
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
           u.role === 'psicologia' ? 'Psicología' :
           u.role === 'secretaria' ? 'Secretaría' : u.role}
        </Badge>
      )
    },
    {
      key: 'nivel_asignado',
      label: 'División',
      render: (u: Usuario) => (
        u.nivel_asignado === 'primaria' ? <Badge variant="info">🎒 Primaria</Badge> :
        u.nivel_asignado === 'secundaria' ? <Badge variant="default">🏫 Secundaria</Badge> :
        <span className="text-gray-400 text-sm">Ambos</span>
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
          <p className="text-gray-500">
            {usuarios.length} {estado === 'activos' ? 'activos' : estado === 'inactivos' ? 'inactivos' : 'en total'}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex rounded-lg border border-gray-200 overflow-hidden">
            {(['activos', 'inactivos', 'todos'] as const).map(op => (
              <button
                key={op}
                onClick={() => setEstado(op)}
                className={`px-3 py-1.5 text-sm capitalize ${estado === op ? 'bg-blue-600 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'}`}
              >
                {op}
              </button>
            ))}
          </div>
          <Button onClick={() => setShowModal(true)} icon={<span>+</span>}>
            Nuevo Usuario
          </Button>
        </div>
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
          <div className="flex gap-2 justify-end flex-wrap">
            {u.activo ? (
              <>
                <button onClick={() => openEdit(u)} className="text-blue-600 hover:text-blue-800 text-sm">
                  Editar
                </button>
                <button onClick={() => { setResetUser(u); setResetPw(''); }} className="text-amber-600 hover:text-amber-800 text-sm">
                  Restablecer contraseña
                </button>
                {u.role === 'profesor' && (
                  <button onClick={() => setReemplazarUser(u)} className="text-purple-600 hover:text-purple-800 text-sm">
                    Reemplazar
                  </button>
                )}
                <button onClick={() => handleDelete(u.id)} className="text-red-600 hover:text-red-800 text-sm">
                  Desactivar
                </button>
              </>
            ) : (
              <button onClick={() => handleReactivar(u)} className="text-green-600 hover:text-green-800 text-sm">
                Reactivar
              </button>
            )}
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
                { value: 'secretaria', label: '📋 Secretaría' },
                { value: 'direccion', label: '🏫 Dirección' }
              ]}
            />
            <Select
              label="División (nivel)"
              value={form.nivel_asignado}
              onChange={e => setForm({ ...form, nivel_asignado: e.target.value })}
              options={[
                { value: '', label: 'Ambos niveles' },
                { value: 'primaria', label: '🎒 Nivel Primario' },
                { value: 'secundaria', label: '🏫 Nivel Secundario' }
              ]}
            />
            {form.role === 'profesor' ? (
              <p className="text-xs text-gray-500 -mt-2 col-span-2">
                En profesores es su división <b>principal</b> (organización): su acceso real
                lo definen las <b>asignaciones</b>, que pueden cruzar niveles (ej. el profesor
                de inglés de secundaria con cursos de 4to-6to de primaria).
              </p>
            ) : (
              <p className="text-xs text-gray-500 -mt-2 col-span-2">
                Con una división asignada, este usuario <b>solo verá</b> cursos, estudiantes y
                datos de ese nivel. "Ambos" = ve todo (como hoy).
              </p>
            )}
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
          {/* v2.19: al EDITAR no se muestra el campo de contraseña. Cambiarla
              es una acción separada y explícita ("Restablecer contraseña"), que
              además revoca las sesiones abiertas y fuerza el cambio en el
              próximo acceso. */}
          {!editando && (
            <>
              <Input
                label="Contraseña inicial *"
                type="password"
                value={form.password}
                onChange={e => setForm({ ...form, password: e.target.value })}
                placeholder="Mínimo 8 caracteres"
              />
              <p className="text-sm text-gray-500">
                La contraseña inicial es obligatoria. Escríbala y compártala con el usuario:
                el sistema le pedirá cambiarla en su primer acceso.
              </p>
            </>
          )}
          {editando && (
            <p className="text-sm text-gray-500">
              Para cambiar la contraseña use la acción <strong>Restablecer contraseña</strong>
              desde la lista de usuarios.
            </p>
          )}
        </div>
      </Modal>

      {/* Restablecer contraseña — acción SEPARADA de editar usuario */}
      <Modal
        isOpen={!!resetUser}
        onClose={() => { setResetUser(null); setResetPw(''); }}
        title={`Restablecer contraseña — ${resetUser?.nombre_completo || ''}`}
        footer={
          <>
            <Button variant="secondary" onClick={() => { setResetUser(null); setResetPw(''); }}>Cancelar</Button>
            <Button onClick={handleReset} loading={saving}>Restablecer</Button>
          </>
        }
      >
        <div className="space-y-3">
          <Input
            label="Contraseña temporal *"
            type="password"
            value={resetPw}
            onChange={e => setResetPw(e.target.value)}
            placeholder="Mínimo 8 caracteres"
          />
          <p className="text-sm text-gray-500">
            Escríbala y compártala con el usuario. Se cerrarán sus sesiones abiertas
            y el sistema le pedirá cambiarla en su próximo acceso.
          </p>
        </div>
      </Modal>

      {/* Reemplazar profesor — el saliente queda inactivo y conserva su historial */}
      <Modal
        isOpen={!!reemplazarUser}
        onClose={() => setReemplazarUser(null)}
        title={`Reemplazar a ${reemplazarUser?.nombre_completo || ''}`}
        size="lg"
        footer={
          <>
            <Button variant="secondary" onClick={() => setReemplazarUser(null)}>Cancelar</Button>
            <Button onClick={handleReemplazar} loading={saving}>Reemplazar</Button>
          </>
        }
      >
        <div className="space-y-4">
          <Alert variant="info">
            {reemplazarUser?.nombre_completo} quedará <strong>inactivo</strong> y{' '}
            {modoReemplazo === 'existente'
              ? <>el <strong>profesor seleccionado asumirá las asignaciones</strong> y horarios vigentes.</>
              : <>se creará una <strong>cuenta nueva</strong> que recibirá sus asignaciones y horarios vigentes.</>}
            {' '}Todo su historial —reportes, asistencias, evaluaciones— se conserva a su nombre
            y no cambia de autor.
          </Alert>
          <div className="flex rounded-lg border border-gray-200 overflow-hidden w-fit">
            {([['existente', 'Profesor del colegio'], ['nuevo', 'Crear cuenta nueva']] as const).map(([v, l]) => (
              <button key={v} onClick={() => setModoReemplazo(v)}
                className={`px-4 py-2 text-sm ${modoReemplazo === v ? 'bg-blue-600 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'}`}>
                {l}
              </button>
            ))}
          </div>

          {modoReemplazo === 'existente' ? (
            <Select
              label="Profesor que asumirá los cursos *"
              value={profesorDestino}
              onChange={e => setProfesorDestino(Number(e.target.value))}
              options={[
                { value: 0, label: 'Seleccione un profesor…' },
                ...usuarios
                  .filter(u => u.role === 'profesor' && u.activo && u.id !== reemplazarUser?.id)
                  .map(u => ({ value: u.id, label: u.nombre_completo })),
              ]}
            />
          ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Input label="Usuario *" value={nuevoProf.username}
              onChange={e => setNuevoProf({ ...nuevoProf, username: e.target.value })} />
            <Input label="Contraseña inicial *" type="password" value={nuevoProf.password}
              placeholder="Mínimo 8 caracteres"
              onChange={e => setNuevoProf({ ...nuevoProf, password: e.target.value })} />
            <Input label="Nombre *" value={nuevoProf.nombre}
              onChange={e => setNuevoProf({ ...nuevoProf, nombre: e.target.value })} />
            <Input label="Apellido" value={nuevoProf.apellido}
              onChange={e => setNuevoProf({ ...nuevoProf, apellido: e.target.value })} />
            <Input label="Email" type="email" value={nuevoProf.email}
              onChange={e => setNuevoProf({ ...nuevoProf, email: e.target.value })} />
            <Input label="Teléfono" value={nuevoProf.telefono}
              onChange={e => setNuevoProf({ ...nuevoProf, telefono: e.target.value })} />
          </div>
          )}
          {modoReemplazo === 'nuevo' ? (
            <p className="text-sm text-gray-500">
              La contraseña inicial es obligatoria. El nuevo profesor deberá cambiarla
              en su primer acceso.
            </p>
          ) : (
            <p className="text-sm text-gray-500">
              Si el profesor elegido ya tiene clases en los mismos horarios, el sistema
              rechazará el reemplazo y no aplicará ningún cambio.
            </p>
          )}
        </div>
      </Modal>
    </div>
  );
};

export default UsuariosPage;
