import { useState, useEffect, useRef } from 'react';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';
import { DataTable, Modal, Input, Select, Button, Badge, Alert } from '../../components/ui';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar } from 'recharts';
import { NivelTabs } from '../../components/NivelTabs';
import { useNivelesActivos, Nivel } from '../../hooks/useNivelesActivos';
import { filterByNivel } from '../../hooks/useFiltroCascada';
import { EstudianteKPIs } from './EstudianteKPIs';

interface Estudiante {
  id: number;
  matricula: string;
  nombre: string;
  apellido: string;
  nombre_completo: string;
  fecha_nacimiento: string;
  edad: number;
  sexo: string;
  curso_id: number;
  curso: string;
  grado: string;
  nivel?: string;
  ciclo?: string;
  tanda: string;
  no_lista: number;
  activo: boolean;
  condicion: string;
  // Datos personales extra
  lugar_nacimiento?: string;
  nacionalidad?: string;
  cedula?: string;
  email?: string;
  foto?: string;
  // Académico
  condicion_entrada?: string;
  escuela_procedencia?: string;
  fecha_ingreso?: string;
  // Retiro
  fecha_retiro?: string;
  motivo_retiro?: string;
  // Contacto del estudiante
  telefono?: string;
  direccion?: string;
  // Padre
  nombre_padre?: string;
  cedula_padre?: string;
  telefono_padre?: string;
  trabajo_padre?: string;
  // Madre
  nombre_madre?: string;
  cedula_madre?: string;
  telefono_madre?: string;
  trabajo_madre?: string;
  // Tutor
  tutor?: string;
  telefono_tutor?: string;
  parentesco_tutor?: string;
  // Salud y emergencia
  contacto_emergencia?: string;
  telefono_emergencia?: string;
  nee?: string;
  tipo_sangre?: string;
  alergias?: string;
  condiciones_medicas?: string;
  seguro_medico?: string;
}

interface Curso {
  id: number;
  nombre_completo: string;
  grado_id: number;
  tanda_id: number;
  nivel?: string;
  ciclo?: string;
  grado?: string;
  nombre?: string;
  tanda?: string;
}

const initialForm = {
  // Sección 1 — Personales
  nombre: '', apellido: '', matricula: '', sexo: 'M', fecha_nacimiento: '',
  lugar_nacimiento: '', nacionalidad: 'Dominicana', cedula: '',
  // Sección 2 — Académico
  curso_id: 0, no_lista: 0, condicion: 'activo',
  condicion_entrada: 'nuevo', escuela_procedencia: '',
  // Contacto del estudiante
  direccion: '', telefono: '', email: '',
  // Sección 3 — Padre
  nombre_padre: '', cedula_padre: '', telefono_padre: '', trabajo_padre: '',
  // Sección 3 — Madre
  nombre_madre: '', cedula_madre: '', telefono_madre: '', trabajo_madre: '',
  // Sección 3 — Tutor
  tutor: '', telefono_tutor: '', parentesco_tutor: '',
  // Sección 4 — Salud y emergencia
  contacto_emergencia: '', telefono_emergencia: '', nee: '',
  tipo_sangre: '', alergias: '', condiciones_medicas: '', seguro_medico: '',
};

export const EstudiantesPage = () => {
  const { user } = useAuth();
  const [estudiantes, setEstudiantes] = useState<Estudiante[]>([]);
  const [cursos, setCursos] = useState<Curso[]>([]);
  const [loading, setLoading] = useState(true);
  const [filtros, setFiltros] = useState({ curso_id: '', grado: '', tanda: '' });
  const [showModal, setShowModal] = useState(false);
  const [showDetalle, setShowDetalle] = useState<Estudiante | null>(null);
  const [editando, setEditando] = useState<Estudiante | null>(null);
  const [form, setForm] = useState(initialForm);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [showImportModal, setShowImportModal] = useState(false);
  const [importCursoId, setImportCursoId] = useState<number | ''>('');
  const [importing, setImporting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [showProgreso, setShowProgreso] = useState(false);
  const [progresoData, setProgresoData] = useState<any>(null);
  const [historialData, setHistorialData] = useState<any>(null);
  const [loadingProgreso, setLoadingProgreso] = useState(false);
  const [tabHistorial, setTabHistorial] = useState<'progreso' | 'conducta' | 'asistencia' | 'psicologia' | 'datos'>('progreso');
  const [activeTab, setActiveTab] = useState<'activos' | 'retirados'>('activos');
  const [estudiantesRetirados, setEstudiantesRetirados] = useState<Estudiante[]>([]);
  // Modal para retirar estudiante (con motivo opcional)
  const [retirando, setRetirando] = useState<Estudiante | null>(null);
  const [motivoRetiro, setMotivoRetiro] = useState('');
  const niveles = useNivelesActivos();
  const [nivelFiltro, setNivelFiltro] = useState<Nivel | 'todos'>('todos');

  // Cuando cargan los niveles activos, inicializar el filtro
  // SIEMPRE default 'todos' para no ocultar estudiantes accidentalmente
  useEffect(() => {
    if (!niveles.loading && niveles.count > 1) {
      setNivelFiltro('todos');
    }
    // Si count === 1, dejar 'todos' también; las tabs no se mostrarán igual
  }, [niveles.loading, niveles.count]);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [estRes, cursosRes] = await Promise.all([
        api.get('/estudiantes'),
        api.get('/cursos')
      ]);
      setEstudiantes(estRes.data);
      setCursos(cursosRes.data);
      
      // Cargar retirados si es dirección
      if (user?.role === 'direccion') {
        try {
          const retiradosRes = await api.get('/estudiantes/retirados');
          setEstudiantesRetirados(retiradosRes.data);
        } catch (e) {
          console.error('Error cargando retirados:', e);
        }
      }
    } catch (e) {
      console.error(e);
      setMessage({ type: 'error', text: 'Error al cargar datos' });
    } finally {
      setLoading(false);
    }
  };

  const handleReactivar = async (estudianteId: number) => {
    if (!confirm('¿Está seguro de reactivar este estudiante?')) return;
    
    try {
      await api.post(`/estudiantes/${estudianteId}/reactivar`);
      setMessage({ type: 'success', text: 'Estudiante reactivado exitosamente' });
      loadData();
    } catch (e: any) {
      setMessage({ type: 'error', text: e.response?.data?.error || 'Error al reactivar' });
    }
  };

  // Mapa curso_id -> nivel como fallback si el estudiante no trae nivel propio
  const cursoNivelMap = new Map<number, string>();
  cursos.forEach(c => {
    if (c.nivel) cursoNivelMap.set(c.id, c.nivel);
  });

  // Helper: obtener nivel del estudiante (usa el propio, si no el del curso, si no 'secundaria')
  const getNivelEst = (e: Estudiante): string => {
    if (e.nivel) return e.nivel;
    return cursoNivelMap.get(e.curso_id) || 'secundaria';
  };

  // Filtrar estudiantes
  const estudiantesFiltrados = estudiantes.filter(e => {
    if (filtros.curso_id && e.curso_id !== parseInt(filtros.curso_id)) return false;
    if (filtros.grado && e.grado !== filtros.grado) return false;
    if (filtros.tanda && e.tanda !== filtros.tanda) return false;
    if (nivelFiltro !== 'todos') {
      if (getNivelEst(e) !== nivelFiltro) return false;
    }
    return true;
  });

  // Obtener listas únicas para filtros
  // Estudiantes filtrados por el nivel (para poblar dropdowns cascadeados)
  const estudiantesPorNivel = nivelFiltro === 'todos' 
    ? estudiantes 
    : estudiantes.filter(e => getNivelEst(e) === nivelFiltro);
  
  // Dropdowns cascadean con la tab activa
  const grados = [...new Set(estudiantesPorNivel.map(e => e.grado).filter(Boolean))];
  const tandas = [...new Set(estudiantesPorNivel.map(e => e.tanda).filter(Boolean))];

  const handleSave = async () => {
    // Validaciones
    if (!form.nombre.trim()) {
      setMessage({ type: 'error', text: 'El nombre es requerido' });
      return;
    }
    if (!form.apellido.trim()) {
      setMessage({ type: 'error', text: 'El apellido es requerido' });
      return;
    }
    if (!form.curso_id || form.curso_id === 0) {
      setMessage({ type: 'error', text: 'Debe seleccionar un curso' });
      return;
    }
    
    setSaving(true);
    try {
      if (editando) {
        await api.put(`/estudiantes/${editando.id}`, form);
        setMessage({ type: 'success', text: 'Estudiante actualizado correctamente' });
      } else {
        await api.post('/estudiantes', form);
        setMessage({ type: 'success', text: 'Estudiante creado correctamente' });
      }
      loadData();
      closeModal();
    } catch (e: any) {
      setMessage({ type: 'error', text: e.response?.data?.error || 'Error al guardar' });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = (e: Estudiante) => {
    setRetirando(e);
    setMotivoRetiro('');
  };
  
  const confirmarRetiro = async () => {
    if (!retirando) return;
    try {
      // DELETE con body opcional con motivo
      await api.delete(`/estudiantes/${retirando.id}`, {
        data: motivoRetiro ? { motivo_retiro: motivoRetiro } : {},
      });
      setMessage({ type: 'success', text: `${retirando.nombre_completo} retirado` });
      setRetirando(null);
      setMotivoRetiro('');
      loadData();
    } catch (e: any) {
      setMessage({ type: 'error', text: e.response?.data?.error || 'Error al retirar estudiante' });
    }
  };

  const openEdit = (e: Estudiante) => {
    setEditando(e);
    setForm({
      // Sección 1
      nombre: e.nombre,
      apellido: e.apellido,
      matricula: e.matricula || '',
      sexo: e.sexo || 'M',
      fecha_nacimiento: e.fecha_nacimiento || '',
      lugar_nacimiento: e.lugar_nacimiento || '',
      nacionalidad: e.nacionalidad || 'Dominicana',
      cedula: e.cedula || '',
      // Sección 2
      curso_id: e.curso_id || 0,
      no_lista: e.no_lista || 0,
      condicion: e.condicion || 'activo',
      condicion_entrada: e.condicion_entrada || 'nuevo',
      escuela_procedencia: e.escuela_procedencia || '',
      direccion: e.direccion || '',
      telefono: e.telefono || '',
      email: e.email || '',
      // Sección 3 — Padre
      nombre_padre: e.nombre_padre || '',
      cedula_padre: e.cedula_padre || '',
      telefono_padre: e.telefono_padre || '',
      trabajo_padre: e.trabajo_padre || '',
      // Sección 3 — Madre
      nombre_madre: e.nombre_madre || '',
      cedula_madre: e.cedula_madre || '',
      telefono_madre: e.telefono_madre || '',
      trabajo_madre: e.trabajo_madre || '',
      // Sección 3 — Tutor
      tutor: e.tutor || '',
      telefono_tutor: e.telefono_tutor || '',
      parentesco_tutor: e.parentesco_tutor || '',
      // Sección 4
      contacto_emergencia: e.contacto_emergencia || '',
      telefono_emergencia: e.telefono_emergencia || '',
      nee: e.nee || '',
      tipo_sangre: e.tipo_sangre || '',
      alergias: e.alergias || '',
      condiciones_medicas: e.condiciones_medicas || '',
      seguro_medico: e.seguro_medico || '',
    });
    setShowModal(true);
  };

  const closeModal = () => {
    setShowModal(false);
    setEditando(null);
    setForm(initialForm);
  };

  const canEdit = user?.role === 'direccion' || user?.role === 'coordinador';

  const handleImportCSV = async () => {
    const file = fileInputRef.current?.files?.[0];
    if (!file || !importCursoId) {
      setMessage({ type: 'error', text: 'Seleccione un archivo y un curso' });
      return;
    }

    setImporting(true);
    const formData = new FormData();
    formData.append('archivo', file);
    formData.append('curso_id', String(importCursoId));

    try {
      const res = await api.post('/estudiantes/importar', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      setMessage({ type: 'success', text: res.data.message });
      setShowImportModal(false);
      setImportCursoId('');
      if (fileInputRef.current) fileInputRef.current.value = '';
      loadData();
    } catch (e: any) {
      setMessage({ type: 'error', text: e.response?.data?.error || 'Error al importar' });
    } finally {
      setImporting(false);
    }
  };

  // Columnas para DataTable
  const verProgreso = async (est: Estudiante) => {
    setLoadingProgreso(true);
    setShowProgreso(true);
    setProgresoData(null);
    setHistorialData(null);
    setTabHistorial('progreso');
    try {
      const [prog, hist] = await Promise.all([
        api.get(`/estudiantes/${est.id}/progreso`),
        api.get(`/estudiantes/${est.id}/historial`)
      ]);
      setProgresoData(prog.data);
      setHistorialData(hist.data);
    } catch { setProgresoData(null); setHistorialData(null); }
    finally { setLoadingProgreso(false); }
  };

  const columns = [
    {
      key: 'no_lista',
      label: '#',
      className: 'w-12',
      render: (e: Estudiante) => <span className="text-gray-500 text-xs">{e.no_lista || '-'}</span>
    },
    {
      key: 'nombre_completo',
      label: 'Nombre',
      render: (e: Estudiante) => (
        <div>
          <p className="font-medium text-gray-900 text-sm">{e.nombre_completo}</p>
          <p className="text-xs text-gray-500">{e.sexo === 'M' ? '👦' : '👧'} {e.edad ? `${e.edad} años` : ''}</p>
        </div>
      )
    },
    {
      key: 'matricula',
      label: 'Matrícula',
      render: (e: Estudiante) => (
        <span className="font-mono text-xs">{e.matricula || '-'}</span>
      )
    },
    {
      key: 'curso',
      label: 'Curso',
      render: (e: Estudiante) => <span className="text-sm">{e.curso || <span className="text-gray-400">Sin asignar</span>}</span>
    },
    {
      key: 'condicion',
      label: 'Condición',
      render: (e: Estudiante) => {
        const colores: Record<string, 'success' | 'danger' | 'warning' | 'info' | 'default'> = {
          'activo': 'success',
          'promovido': 'info',
          'repitente': 'warning',
          'trasladado': 'default',
          'retirado': 'danger',
          'egresado': 'info'
        };
        const variant = colores[e.condicion] || 'default';
        return <Badge variant={variant}>{e.condicion || 'activo'}</Badge>;
      }
    },
    {
      key: 'acciones',
      label: '',
      className: 'w-10',
      render: (e: Estudiante) => (
        <button onClick={(ev) => { ev.stopPropagation(); verProgreso(e); }} className="p-1.5 rounded-lg hover:bg-blue-50 text-blue-600" title="Ver progreso">
          <TrendingUp size={16} />
        </button>
      )
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
          <h1 className="text-2xl font-bold text-gray-900">👨‍🎓 Estudiantes</h1>
          <p className="text-gray-500">{estudiantesFiltrados.length} estudiantes activos</p>
        </div>
        <div className="flex gap-2">
          {/* Botón Imprimir lista — disponible para todos los roles si hay curso seleccionado */}
          {filtros.curso_id && (
            <Button
              variant="secondary"
              onClick={() => {
                // Abrir el PDF en una pestaña nueva
                const token = localStorage.getItem('token');
                const url = `${(import.meta as any).env.VITE_API_URL || ''}/api/imprimir/lista-estudiantes/${filtros.curso_id}`;
                // Como necesita Authorization header, fetcheamos y abrimos blob
                fetch(url, { headers: { Authorization: `Bearer ${token}` } })
                  .then(r => r.ok ? r.blob() : Promise.reject(r))
                  .then(blob => {
                    const u = URL.createObjectURL(blob);
                    window.open(u, '_blank');
                  })
                  .catch(() => alert('No se pudo generar el PDF'));
              }}
              icon={<span>🖨️</span>}
            >
              Imprimir lista
            </Button>
          )}
          {canEdit && (
            <>
              <Button variant="secondary" onClick={() => setShowImportModal(true)} icon={<span>📥</span>}>
                Importar CSV
              </Button>
              <Button onClick={() => setShowModal(true)} icon={<span>+</span>}>
                Nuevo Estudiante
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Tabs por nivel educativo (solo si colegio tiene más de 1 nivel activo) */}
      <NivelTabs value={nivelFiltro} onChange={(n) => { setNivelFiltro(n); setFiltros({ curso_id: '', grado: '', tanda: '' }); }} showAll />

      {/* Pestañas Activos/Retirados */}
      {user?.role === 'direccion' && (
        <div className="flex gap-2 border-b">
          <button
            onClick={() => setActiveTab('activos')}
            className={`px-4 py-2 font-medium text-sm border-b-2 transition-colors ${
              activeTab === 'activos'
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            ✅ Activos ({estudiantes.length})
          </button>
          <button
            onClick={() => setActiveTab('retirados')}
            className={`px-4 py-2 font-medium text-sm border-b-2 transition-colors ${
              activeTab === 'retirados'
                ? 'border-red-600 text-red-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            🚫 Retirados ({estudiantesRetirados.length})
          </button>
        </div>
      )}

      {/* Mensajes */}
      {message && (
        <Alert 
          variant={message.type === 'success' ? 'success' : 'error'} 
          onClose={() => setMessage(null)}
        >
          {message.text}
        </Alert>
      )}

      {/* Vista de Estudiantes Retirados */}
      {activeTab === 'retirados' && user?.role === 'direccion' ? (
        <div className="bg-white rounded-lg border shadow-sm overflow-hidden">
          <div className="p-4 bg-red-50 border-b border-red-200 flex items-center justify-between">
            <div>
              <h2 className="font-semibold text-red-800">Estudiantes Retirados</h2>
              <p className="text-sm text-red-600">Estos estudiantes han sido marcados como retirados y no aparecen en las listas de clases.</p>
            </div>
            {estudiantesRetirados.length > 0 && (
              <button
                onClick={async () => {
                  if (!confirm(`¿Eliminar PERMANENTEMENTE los ${estudiantesRetirados.length} estudiantes retirados y todos sus datos? Esta acción NO se puede deshacer.`)) return;
                  if (!confirm('¿Está completamente seguro? Se borrarán calificaciones, asistencia y todo registro de estos estudiantes.')) return;
                  try {
                    const res = await api.delete('/estudiantes/retirados/eliminar-todos');
                    setMessage({ type: 'success', text: res.data.message });
                    setEstudiantesRetirados([]);
                  } catch (e: any) {
                    setMessage({ type: 'error', text: e.response?.data?.error || 'Error al eliminar' });
                  }
                }}
                className="px-3 py-2 bg-red-700 text-white text-sm rounded hover:bg-red-800"
              >
                🗑️ Eliminar todos
              </button>
            )}
          </div>
          {estudiantesRetirados.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-sm font-medium text-gray-600">Nombre</th>
                    <th className="px-4 py-3 text-left text-sm font-medium text-gray-600">Curso</th>
                    <th className="px-4 py-3 text-left text-sm font-medium text-gray-600">Condición</th>
                    <th className="px-4 py-3 text-center text-sm font-medium text-gray-600">Acciones</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {estudiantesRetirados.map(est => (
                    <tr key={est.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-medium">{est.nombre_completo}</td>
                      <td className="px-4 py-3 text-gray-600">{est.curso || 'Sin curso'}</td>
                      <td className="px-4 py-3">
                        <span className="px-2 py-1 text-xs font-medium bg-red-100 text-red-700 rounded">
                          {est.condicion}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-center space-x-2">
                        <button
                          onClick={() => handleReactivar(est.id)}
                          className="px-3 py-1 bg-emerald-600 text-white text-sm rounded hover:bg-emerald-700"
                        >
                          🔄 Reactivar
                        </button>
                        <button
                          onClick={async () => {
                            if (!confirm(`¿Eliminar PERMANENTEMENTE a ${est.nombre_completo}? Se borrarán todas sus calificaciones y asistencia.`)) return;
                            try {
                              const res = await api.delete(`/estudiantes/retirados/${est.id}`);
                              setMessage({ type: 'success', text: res.data.message });
                              setEstudiantesRetirados(prev => prev.filter(e => e.id !== est.id));
                            } catch (e: any) {
                              setMessage({ type: 'error', text: e.response?.data?.error || 'Error al eliminar' });
                            }
                          }}
                          className="px-3 py-1 bg-red-600 text-white text-sm rounded hover:bg-red-700"
                        >
                          🗑️ Eliminar
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="p-8 text-center text-gray-500">
              No hay estudiantes retirados
            </div>
          )}
        </div>
      ) : (
        <>
          {/* Filtros - Solo para activos */}
          <div className="bg-white rounded-lg border border-gray-200 p-4">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <Select
                label="Curso"
                value={filtros.curso_id}
                onChange={e => setFiltros({ ...filtros, curso_id: e.target.value })}
                options={(nivelFiltro === 'todos' ? cursos : cursos.filter(c => (c.nivel || 'secundaria') === nivelFiltro)).map(c => ({ value: c.id, label: c.grado ? `${c.grado} ${c.nombre}` : c.nombre_completo, group: c.tanda || 'Sin tanda' }))}
                placeholder="Todos los cursos"
              />
              <Select
                label="Grado"
                value={filtros.grado}
                onChange={e => setFiltros({ ...filtros, grado: e.target.value })}
                options={grados.map(g => ({ value: g, label: g }))}
                placeholder="Todos los grados"
              />
              <Select
                label="Tanda"
                value={filtros.tanda}
                onChange={e => setFiltros({ ...filtros, tanda: e.target.value })}
                options={tandas.map(t => ({ value: t, label: t }))}
                placeholder="Todas las tandas"
              />
            </div>
            {(filtros.curso_id || filtros.grado || filtros.tanda) && (
              <button
                onClick={() => setFiltros({ curso_id: '', grado: '', tanda: '' })}
                className="mt-3 text-sm text-blue-600 hover:underline"
          >
            Limpiar filtros
          </button>
        )}
      </div>

      {/* Tabla */}
      <DataTable
        data={estudiantesFiltrados}
        columns={columns}
        searchKeys={['nombre_completo', 'matricula', 'nombre', 'apellido']}
        exportFilename="estudiantes"
        onRowClick={(e) => setShowDetalle(e)}
        emptyMessage="No hay estudiantes que coincidan con los filtros"
        actions={canEdit ? (e) => (
          <div className="flex gap-2 justify-end">
            <button
              onClick={(ev) => { ev.stopPropagation(); openEdit(e); }}
              className="text-blue-600 hover:text-blue-800 text-sm"
            >
              Editar
            </button>
            {user?.role === 'direccion' && (
              <button
                onClick={(ev) => { ev.stopPropagation(); handleDelete(e); }}
                className="text-red-600 hover:text-red-800 text-sm"
              >
                Retirar
              </button>
            )}
          </div>
        ) : undefined}
      />
        </>
      )}

      {/* Modal Crear/Editar */}
      <Modal
        isOpen={showModal}
        onClose={closeModal}
        title={editando ? 'Editar Estudiante' : 'Nuevo Estudiante'}
        size="xl"
        footer={
          <>
            <Button variant="secondary" onClick={closeModal}>Cancelar</Button>
            <Button onClick={handleSave} loading={saving}>
              {editando ? 'Guardar Cambios' : 'Crear Estudiante'}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          {/* ═══════════ SECCIÓN 1: DATOS PERSONALES ═══════════ */}
          <details open className="group border border-gray-200 rounded-lg">
            <summary className="cursor-pointer px-4 py-3 bg-gray-50 rounded-lg font-medium text-gray-800 flex items-center justify-between hover:bg-gray-100">
              <span>📋 Datos personales</span>
              <span className="text-gray-400 group-open:rotate-180 transition-transform">▾</span>
            </summary>
            <div className="p-4 grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Input label="Nombre" value={form.nombre}
                onChange={e => setForm({ ...form, nombre: e.target.value })} required />
              <Input label="Apellido" value={form.apellido}
                onChange={e => setForm({ ...form, apellido: e.target.value })} required />
              <Input label="Matrícula" value={form.matricula}
                onChange={e => setForm({ ...form, matricula: e.target.value })} />
              <Select label="Sexo" value={form.sexo}
                onChange={e => setForm({ ...form, sexo: e.target.value })}
                options={[{ value: 'M', label: 'Masculino' }, { value: 'F', label: 'Femenino' }]} />
              <Input label="Fecha de nacimiento" type="date" value={form.fecha_nacimiento}
                onChange={e => setForm({ ...form, fecha_nacimiento: e.target.value })} />
              <Input label="Lugar de nacimiento" value={form.lugar_nacimiento}
                onChange={e => setForm({ ...form, lugar_nacimiento: e.target.value })}
                placeholder="Ej. Santo Domingo" />
              <Input label="Nacionalidad" value={form.nacionalidad}
                onChange={e => setForm({ ...form, nacionalidad: e.target.value })} />
              <Input label="Cédula del estudiante" value={form.cedula}
                onChange={e => setForm({ ...form, cedula: e.target.value })}
                placeholder="000-0000000-0" />
            </div>
          </details>

          {/* ═══════════ SECCIÓN 2: ACADÉMICO Y CONTACTO ═══════════ */}
          <details open className="group border border-gray-200 rounded-lg">
            <summary className="cursor-pointer px-4 py-3 bg-gray-50 rounded-lg font-medium text-gray-800 flex items-center justify-between hover:bg-gray-100">
              <span>🎓 Académico y contacto</span>
              <span className="text-gray-400 group-open:rotate-180 transition-transform">▾</span>
            </summary>
            <div className="p-4 grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Select label="Curso" value={form.curso_id}
                onChange={e => setForm({ ...form, curso_id: parseInt(e.target.value) })}
                options={cursos.map(c => ({ value: c.id, label: c.grado ? `${c.grado} ${c.nombre}` : c.nombre_completo, group: c.tanda || 'Sin tanda' }))}
                placeholder="Seleccionar curso" />
              <Input label="No. lista" type="number" value={form.no_lista}
                onChange={e => setForm({ ...form, no_lista: parseInt(e.target.value) || 0 })} />
              <Select label="Condición actual" value={form.condicion || 'activo'}
                onChange={e => setForm({ ...form, condicion: e.target.value })}
                options={[
                  { value: 'activo', label: 'Activo' },
                  { value: 'promovido', label: 'Promovido' },
                  { value: 'repitente', label: 'Repitente' },
                  { value: 'trasladado', label: 'Trasladado' },
                  { value: 'retirado', label: 'Retirado' },
                  { value: 'egresado', label: 'Egresado' },
                ]} />
              <Select label="Condición de entrada" value={form.condicion_entrada}
                onChange={e => setForm({ ...form, condicion_entrada: e.target.value })}
                options={[
                  { value: 'nuevo', label: 'Nuevo' },
                  { value: 'repitente', label: 'Repitente' },
                  { value: 'transferido', label: 'Transferido' },
                ]} />
              <Input label="Escuela de procedencia" value={form.escuela_procedencia}
                onChange={e => setForm({ ...form, escuela_procedencia: e.target.value })} />
              <Input label="Teléfono del estudiante" value={form.telefono}
                onChange={e => setForm({ ...form, telefono: e.target.value })} />
              <Input label="Email del estudiante" type="email" value={form.email}
                onChange={e => setForm({ ...form, email: e.target.value })} />
              <div className="sm:col-span-2">
                <Input label="Dirección" value={form.direccion}
                  onChange={e => setForm({ ...form, direccion: e.target.value })} />
              </div>
            </div>
          </details>

          {/* ═══════════ SECCIÓN 3: FAMILIARES ═══════════ */}
          <details className="group border border-gray-200 rounded-lg">
            <summary className="cursor-pointer px-4 py-3 bg-gray-50 rounded-lg font-medium text-gray-800 flex items-center justify-between hover:bg-gray-100">
              <span>👨‍👩‍👧 Familiares (padre, madre, tutor)</span>
              <span className="text-gray-400 group-open:rotate-180 transition-transform">▾</span>
            </summary>
            <div className="p-4 space-y-4">
              <div>
                <p className="text-sm font-medium text-gray-600 mb-2">Padre</p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <Input label="Nombre completo" value={form.nombre_padre}
                    onChange={e => setForm({ ...form, nombre_padre: e.target.value })} />
                  <Input label="Cédula" value={form.cedula_padre}
                    onChange={e => setForm({ ...form, cedula_padre: e.target.value })}
                    placeholder="000-0000000-0" />
                  <Input label="Teléfono" value={form.telefono_padre}
                    onChange={e => setForm({ ...form, telefono_padre: e.target.value })} />
                  <Input label="Trabajo" value={form.trabajo_padre}
                    onChange={e => setForm({ ...form, trabajo_padre: e.target.value })} />
                </div>
              </div>
              <div>
                <p className="text-sm font-medium text-gray-600 mb-2">Madre</p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <Input label="Nombre completo" value={form.nombre_madre}
                    onChange={e => setForm({ ...form, nombre_madre: e.target.value })} />
                  <Input label="Cédula" value={form.cedula_madre}
                    onChange={e => setForm({ ...form, cedula_madre: e.target.value })}
                    placeholder="000-0000000-0" />
                  <Input label="Teléfono" value={form.telefono_madre}
                    onChange={e => setForm({ ...form, telefono_madre: e.target.value })} />
                  <Input label="Trabajo" value={form.trabajo_madre}
                    onChange={e => setForm({ ...form, trabajo_madre: e.target.value })} />
                </div>
              </div>
              <div>
                <p className="text-sm font-medium text-gray-600 mb-2">Tutor (si aplica)</p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <Input label="Nombre del tutor" value={form.tutor}
                    onChange={e => setForm({ ...form, tutor: e.target.value })} />
                  <Input label="Teléfono del tutor" value={form.telefono_tutor}
                    onChange={e => setForm({ ...form, telefono_tutor: e.target.value })} />
                  <Input label="Parentesco" value={form.parentesco_tutor}
                    onChange={e => setForm({ ...form, parentesco_tutor: e.target.value })}
                    placeholder="Ej. Tía, Abuelo, Hermano" />
                </div>
              </div>
            </div>
          </details>

          {/* ═══════════ SECCIÓN 4: SALUD Y EMERGENCIA ═══════════ */}
          <details className="group border border-gray-200 rounded-lg">
            <summary className="cursor-pointer px-4 py-3 bg-gray-50 rounded-lg font-medium text-gray-800 flex items-center justify-between hover:bg-gray-100">
              <span>🏥 Salud y emergencia</span>
              <span className="text-gray-400 group-open:rotate-180 transition-transform">▾</span>
            </summary>
            <div className="p-4 grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Input label="Contacto de emergencia" value={form.contacto_emergencia}
                onChange={e => setForm({ ...form, contacto_emergencia: e.target.value })}
                placeholder="Nombre completo" />
              <Input label="Teléfono de emergencia" value={form.telefono_emergencia}
                onChange={e => setForm({ ...form, telefono_emergencia: e.target.value })} />
              <Select label="Tipo de sangre" value={form.tipo_sangre}
                onChange={e => setForm({ ...form, tipo_sangre: e.target.value })}
                options={[
                  { value: '', label: 'No especificado' },
                  { value: 'O+', label: 'O+' }, { value: 'O-', label: 'O-' },
                  { value: 'A+', label: 'A+' }, { value: 'A-', label: 'A-' },
                  { value: 'B+', label: 'B+' }, { value: 'B-', label: 'B-' },
                  { value: 'AB+', label: 'AB+' }, { value: 'AB-', label: 'AB-' },
                ]} />
              <Input label="Seguro médico" value={form.seguro_medico}
                onChange={e => setForm({ ...form, seguro_medico: e.target.value })}
                placeholder="Ej. ARS Humano" />
              <div className="sm:col-span-2">
                <Input label="Necesidades educativas especiales (NEE)" value={form.nee}
                  onChange={e => setForm({ ...form, nee: e.target.value })}
                  placeholder="Ej. Dislexia, TDAH, etc." />
              </div>
              <div className="sm:col-span-2">
                <Input label="Alergias" value={form.alergias}
                  onChange={e => setForm({ ...form, alergias: e.target.value })}
                  placeholder="Separar con comas" />
              </div>
              <div className="sm:col-span-2">
                <Input label="Condiciones médicas" value={form.condiciones_medicas}
                  onChange={e => setForm({ ...form, condiciones_medicas: e.target.value })}
                  placeholder="Ej. Asma controlada, diabetes" />
              </div>
            </div>
          </details>
        </div>
      </Modal>

      {/* Modal Detalle */}
      <Modal
        isOpen={!!showDetalle}
        onClose={() => setShowDetalle(null)}
        title="Información del Estudiante"
        size="lg"
        footer={
          <Button variant="secondary" onClick={() => setShowDetalle(null)}>Cerrar</Button>
        }
      >
        {showDetalle && (
          <div className="space-y-4">
            <div className="flex items-center gap-4 pb-4 border-b">
              <div className="w-16 h-16 rounded-full bg-gradient-to-br from-blue-400 to-blue-600 flex items-center justify-center text-white text-2xl font-bold">
                {showDetalle.nombre?.charAt(0)}{showDetalle.apellido?.charAt(0)}
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <h3 className={`text-xl font-bold ${!showDetalle.activo ? 'text-gray-500 line-through' : ''}`}>
                    {showDetalle.nombre_completo}
                  </h3>
                  {!showDetalle.activo && (
                    <span className="inline-block px-2 py-0.5 bg-gray-700 text-white text-[10px] font-bold rounded uppercase tracking-wide">
                      RETIRADO
                    </span>
                  )}
                </div>
                <p className="text-gray-500">{showDetalle.curso || 'Sin curso asignado'}</p>
              </div>
            </div>
            
            {/* Banner prominente de retiro: visible al inicio del modal */}
            {!showDetalle.activo && (
              <div className="bg-gray-100 border-l-4 border-gray-700 rounded p-3">
                <p className="text-sm font-medium text-gray-800">
                  Estudiante retirado{showDetalle.fecha_retiro ? ` el ${showDetalle.fecha_retiro}` : ''}
                </p>
                {showDetalle.motivo_retiro && (
                  <p className="text-xs text-gray-600 mt-1">
                    <span className="font-medium">Motivo:</span> {showDetalle.motivo_retiro}
                  </p>
                )}
                {!showDetalle.motivo_retiro && (
                  <p className="text-xs text-gray-500 italic mt-1">Sin motivo registrado</p>
                )}
              </div>
            )}

            {/* Datos personales */}
            <div>
              <h4 className="text-sm font-semibold text-gray-700 mb-2 uppercase tracking-wide">Datos personales</h4>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div><p className="text-gray-500">Matrícula</p><p className="font-medium">{showDetalle.matricula || '-'}</p></div>
                <div><p className="text-gray-500">Cédula</p><p className="font-medium">{showDetalle.cedula || '-'}</p></div>
                <div><p className="text-gray-500">Edad</p><p className="font-medium">{showDetalle.edad ? `${showDetalle.edad} años` : '-'}</p></div>
                <div><p className="text-gray-500">Sexo</p><p className="font-medium">{showDetalle.sexo === 'M' ? 'Masculino' : showDetalle.sexo === 'F' ? 'Femenino' : '-'}</p></div>
                <div><p className="text-gray-500">Nacionalidad</p><p className="font-medium">{showDetalle.nacionalidad || '-'}</p></div>
                <div><p className="text-gray-500">Lugar de nacimiento</p><p className="font-medium">{showDetalle.lugar_nacimiento || '-'}</p></div>
              </div>
            </div>

            {/* Académico */}
            <div className="border-t pt-3">
              <h4 className="text-sm font-semibold text-gray-700 mb-2 uppercase tracking-wide">Académico</h4>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div><p className="text-gray-500">No. lista</p><p className="font-medium">{showDetalle.no_lista || '-'}</p></div>
                <div><p className="text-gray-500">Condición actual</p>
                  <Badge variant={
                    showDetalle.condicion === 'activo' ? 'success' :
                    showDetalle.condicion === 'promovido' ? 'info' :
                    showDetalle.condicion === 'repitente' ? 'warning' :
                    showDetalle.condicion === 'retirado' ? 'danger' :
                    showDetalle.condicion === 'egresado' ? 'info' : 'default'
                  }>{showDetalle.condicion || 'activo'}</Badge>
                </div>
                <div><p className="text-gray-500">Condición de entrada</p><p className="font-medium">{showDetalle.condicion_entrada || '-'}</p></div>
                <div><p className="text-gray-500">Escuela de procedencia</p><p className="font-medium">{showDetalle.escuela_procedencia || '-'}</p></div>
              </div>
            </div>

            {/* Contacto */}
            {(showDetalle.telefono || showDetalle.email || showDetalle.direccion) && (
              <div className="border-t pt-3">
                <h4 className="text-sm font-semibold text-gray-700 mb-2 uppercase tracking-wide">Contacto del estudiante</h4>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  {showDetalle.telefono && <div><p className="text-gray-500">Teléfono</p><a href={`tel:${showDetalle.telefono}`} className="font-medium text-blue-600">{showDetalle.telefono}</a></div>}
                  {showDetalle.email && <div><p className="text-gray-500">Email</p><a href={`mailto:${showDetalle.email}`} className="font-medium text-blue-600">{showDetalle.email}</a></div>}
                  {showDetalle.direccion && <div className="col-span-2"><p className="text-gray-500">Dirección</p><p className="font-medium">{showDetalle.direccion}</p></div>}
                </div>
              </div>
            )}

            {/* Padre */}
            {showDetalle.nombre_padre && (
              <div className="border-t pt-3">
                <h4 className="text-sm font-semibold text-gray-700 mb-2 uppercase tracking-wide">Padre</h4>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div><p className="text-gray-500">Nombre</p><p className="font-medium">{showDetalle.nombre_padre}</p></div>
                  {showDetalle.cedula_padre && <div><p className="text-gray-500">Cédula</p><p className="font-medium">{showDetalle.cedula_padre}</p></div>}
                  {showDetalle.telefono_padre && <div><p className="text-gray-500">Teléfono</p><a href={`tel:${showDetalle.telefono_padre}`} className="font-medium text-blue-600">{showDetalle.telefono_padre}</a></div>}
                  {showDetalle.trabajo_padre && <div><p className="text-gray-500">Trabajo</p><p className="font-medium">{showDetalle.trabajo_padre}</p></div>}
                </div>
              </div>
            )}

            {/* Madre */}
            {showDetalle.nombre_madre && (
              <div className="border-t pt-3">
                <h4 className="text-sm font-semibold text-gray-700 mb-2 uppercase tracking-wide">Madre</h4>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div><p className="text-gray-500">Nombre</p><p className="font-medium">{showDetalle.nombre_madre}</p></div>
                  {showDetalle.cedula_madre && <div><p className="text-gray-500">Cédula</p><p className="font-medium">{showDetalle.cedula_madre}</p></div>}
                  {showDetalle.telefono_madre && <div><p className="text-gray-500">Teléfono</p><a href={`tel:${showDetalle.telefono_madre}`} className="font-medium text-blue-600">{showDetalle.telefono_madre}</a></div>}
                  {showDetalle.trabajo_madre && <div><p className="text-gray-500">Trabajo</p><p className="font-medium">{showDetalle.trabajo_madre}</p></div>}
                </div>
              </div>
            )}

            {/* Tutor */}
            {showDetalle.tutor && (
              <div className="border-t pt-3">
                <h4 className="text-sm font-semibold text-gray-700 mb-2 uppercase tracking-wide">Tutor</h4>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div><p className="text-gray-500">Nombre</p><p className="font-medium">{showDetalle.tutor}</p></div>
                  {showDetalle.parentesco_tutor && <div><p className="text-gray-500">Parentesco</p><p className="font-medium">{showDetalle.parentesco_tutor}</p></div>}
                  {showDetalle.telefono_tutor && <div><p className="text-gray-500">Teléfono</p><a href={`tel:${showDetalle.telefono_tutor}`} className="font-medium text-blue-600">{showDetalle.telefono_tutor}</a></div>}
                </div>
              </div>
            )}

            {/* Salud */}
            {(showDetalle.tipo_sangre || showDetalle.alergias || showDetalle.condiciones_medicas || showDetalle.contacto_emergencia || showDetalle.nee || showDetalle.seguro_medico) && (
              <div className="border-t pt-3">
                <h4 className="text-sm font-semibold text-gray-700 mb-2 uppercase tracking-wide">Salud y emergencia</h4>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  {showDetalle.contacto_emergencia && <div><p className="text-gray-500">Contacto emergencia</p><p className="font-medium">{showDetalle.contacto_emergencia}</p></div>}
                  {showDetalle.telefono_emergencia && <div><p className="text-gray-500">Tel. emergencia</p><a href={`tel:${showDetalle.telefono_emergencia}`} className="font-medium text-red-600">{showDetalle.telefono_emergencia}</a></div>}
                  {showDetalle.tipo_sangre && <div><p className="text-gray-500">Tipo sangre</p><p className="font-medium">{showDetalle.tipo_sangre}</p></div>}
                  {showDetalle.seguro_medico && <div><p className="text-gray-500">Seguro</p><p className="font-medium">{showDetalle.seguro_medico}</p></div>}
                  {showDetalle.nee && <div className="col-span-2"><p className="text-gray-500">NEE</p><p className="font-medium">{showDetalle.nee}</p></div>}
                  {showDetalle.alergias && <div className="col-span-2"><p className="text-gray-500">Alergias</p><p className="font-medium">{showDetalle.alergias}</p></div>}
                  {showDetalle.condiciones_medicas && <div className="col-span-2"><p className="text-gray-500">Condiciones médicas</p><p className="font-medium">{showDetalle.condiciones_medicas}</p></div>}
                </div>
              </div>
            )}

            {/* v2.13.2: KPIs académicos del estudiante */}
            {showDetalle.activo && (
              <EstudianteKPIs
                estudianteId={showDetalle.id}
                cursoId={showDetalle.curso_id}
                esSecundaria={getNivelEst(showDetalle) === 'secundaria'}
              />
            )}
          </div>
        )}
      </Modal>

      {/* Modal Retirar Estudiante (con motivo opcional) */}
      <Modal
        isOpen={!!retirando}
        onClose={() => { setRetirando(null); setMotivoRetiro(''); }}
        title="Retirar estudiante"
        size="md"
        footer={
          <>
            <Button variant="secondary" onClick={() => { setRetirando(null); setMotivoRetiro(''); }}>Cancelar</Button>
            <Button variant="danger" onClick={confirmarRetiro}>Retirar estudiante</Button>
          </>
        }
      >
        {retirando && (
          <div className="space-y-4">
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-800">
              <p className="font-medium">¿Confirmás que querés retirar a <span className="font-bold">{retirando.nombre_completo}</span>?</p>
              <p className="text-xs mt-1">El estudiante deja de poder ser calificado o tener nuevas marcas de asistencia. Sus notas y asistencia previas quedan intactas. Podés reactivarlo en cualquier momento desde la pestaña "Retirados".</p>
            </div>
            <Input
              label="Motivo del retiro (opcional)"
              value={motivoRetiro}
              onChange={e => setMotivoRetiro(e.target.value)}
              placeholder="Ej. Cambio de colegio, mudanza, abandono"
            />
            <p className="text-xs text-gray-500">Fecha de retiro: hoy ({new Date().toISOString().slice(0,10)})</p>
          </div>
        )}
      </Modal>
      <Modal
        isOpen={showImportModal}
        onClose={() => setShowImportModal(false)}
        title="📥 Importar Estudiantes desde CSV"
        size="md"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowImportModal(false)}>Cancelar</Button>
            <Button onClick={handleImportCSV} loading={importing}>
              Importar
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Select
            label="Curso destino *"
            value={importCursoId}
            onChange={e => setImportCursoId(parseInt(e.target.value) || '')}
            options={cursos.map(c => ({ value: c.id, label: c.grado ? `${c.grado} ${c.nombre}` : c.nombre_completo, group: c.tanda || 'Sin tanda' }))}
            placeholder="Seleccionar curso"
          />
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Archivo CSV *
            </label>
            <input
              type="file"
              ref={fileInputRef}
              accept=".csv"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
            />
          </div>

          <div className="p-4 bg-blue-50 rounded-lg border border-blue-200">
            <div className="flex items-center justify-between mb-2">
              <p className="text-sm font-medium text-blue-800">📋 Formato del CSV:</p>
              <button
                onClick={() => {
                  const plantilla = 'nombre,apellido,matricula,no_lista,genero,condicion\nJuan,Pérez,2024001,1,M,Nuevo\nMaría,García,2024002,2,F,Promovido\nCarlos,Rodríguez,2024003,3,M,Nuevo';
                  const blob = new Blob([plantilla], { type: 'text/csv' });
                  const url = window.URL.createObjectURL(blob);
                  const a = document.createElement('a');
                  a.href = url;
                  a.download = 'plantilla_estudiantes.csv';
                  a.click();
                }}
                className="text-xs bg-blue-600 text-white px-2 py-1 rounded hover:bg-blue-700"
              >
                ⬇️ Descargar Plantilla
              </button>
            </div>
            <code className="text-xs bg-white px-2 py-1 rounded border block">
              nombre,apellido,matricula,no_lista,genero,condicion
            </code>
            <p className="text-xs text-blue-600 mt-2">
              • Solo <strong>nombre</strong> y <strong>apellido</strong> son obligatorios<br/>
              • Género: M o F<br/>
              • Condición: Nuevo, Promovido o Repitente
            </p>
          </div>
        </div>
      </Modal>

      {/* Modal Historial Completo */}
      <Modal isOpen={showProgreso} onClose={() => setShowProgreso(false)} title={progresoData ? `📋 ${progresoData.estudiante.nombre}` : 'Historial'} size="lg">
        {loadingProgreso ? (
          <div className="flex items-center justify-center py-12"><div className="animate-spin h-8 w-8 border-4 border-blue-500 border-t-transparent rounded-full"></div></div>
        ) : progresoData && historialData ? (
          <div className="space-y-3">
            {/* Info estudiante */}
            <div className="bg-blue-50 rounded-lg p-3 flex justify-between items-center">
              <div>
                <p className="font-bold text-blue-800 text-sm">{progresoData.estudiante.curso}</p>
                <p className="text-xs text-blue-600">Matrícula: {progresoData.estudiante.matricula || '-'}</p>
              </div>
              <div className="text-right">
                <p className="text-lg font-bold text-blue-700">{progresoData.promedio_general || '-'}</p>
                <p className="text-[10px] text-blue-500">Promedio</p>
              </div>
            </div>

            {/* Tabs */}
            <div className="flex border-b overflow-x-auto">
              {[
                { key: 'progreso', label: '📈 Progreso', count: null },
                { key: 'conducta', label: '🚨 Conducta', count: historialData.conducta_resumen.total },
                { key: 'asistencia', label: '📅 Asistencia', count: null },
                { key: 'psicologia', label: '🧠 Psicología', count: historialData.psicologia_resumen.total },
                { key: 'datos', label: '👤 Datos', count: null },
              ].map(tab => (
                <button key={tab.key} onClick={() => setTabHistorial(tab.key as any)}
                  className={`flex-shrink-0 px-3 py-2 text-xs font-medium border-b-2 transition-colors whitespace-nowrap ${
                    tabHistorial === tab.key ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700'
                  }`}>
                  {tab.label} {tab.count !== null && tab.count > 0 && <span className="ml-1 bg-red-100 text-red-600 px-1.5 rounded-full text-[10px]">{tab.count}</span>}
                </button>
              ))}
            </div>

            {/* TAB: Progreso */}
            {tabHistorial === 'progreso' && (
              <div className="space-y-3">
                <div className="grid grid-cols-3 gap-2">
                  <div className="bg-white rounded-lg border p-2 text-center">
                    <div className="flex items-center justify-center gap-1">
                      {progresoData.tendencia === 'subiendo' && <TrendingUp size={16} className="text-emerald-600" />}
                      {progresoData.tendencia === 'bajando' && <TrendingDown size={16} className="text-red-600" />}
                      {progresoData.tendencia === 'estable' && <Minus size={16} className="text-gray-500" />}
                      <span className={`text-xs font-bold ${progresoData.tendencia === 'subiendo' ? 'text-emerald-600' : progresoData.tendencia === 'bajando' ? 'text-red-600' : 'text-gray-500'}`}>
                        {progresoData.tendencia === 'subiendo' ? 'Subiendo' : progresoData.tendencia === 'bajando' ? 'Bajando' : 'Estable'}
                      </span>
                    </div>
                    <p className="text-[10px] text-gray-400">Tendencia</p>
                  </div>
                  <div className="bg-white rounded-lg border p-2 text-center">
                    <p className="text-xs font-bold text-emerald-600">{progresoData.mejor_asignatura?.nota || '-'}</p>
                    <p className="text-[10px] text-gray-400 truncate">{progresoData.mejor_asignatura?.asignatura || 'Mejor'}</p>
                  </div>
                  <div className="bg-white rounded-lg border p-2 text-center">
                    <p className="text-xs font-bold text-red-600">{progresoData.peor_asignatura?.nota || '-'}</p>
                    <p className="text-[10px] text-gray-400 truncate">{progresoData.peor_asignatura?.asignatura || 'Peor'}</p>
                  </div>
                </div>
                {progresoData.periodos.some((p: any) => p.promedio !== null) && (
                  <div className="bg-white rounded-lg border p-3">
                    <h3 className="text-xs font-bold text-gray-700 mb-2">Evolución del promedio</h3>
                    <ResponsiveContainer width="100%" height={180}>
                      <LineChart data={progresoData.periodos.filter((p: any) => p.promedio !== null).map((p: any) => ({ name: `P${p.periodo}`, promedio: p.promedio }))}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                        <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} />
                        <Tooltip />
                        <Line type="monotone" dataKey="promedio" stroke="#3b82f6" strokeWidth={3} dot={{ r: 5, fill: '#3b82f6' }} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                )}
                {progresoData.periodos.filter((p: any) => p.asignaturas.length > 0).slice(-1).map((p: any) => (
                  <div key={p.periodo} className="bg-white rounded-lg border p-3">
                    <h3 className="text-xs font-bold text-gray-700 mb-2">Notas por asignatura (P{p.periodo})</h3>
                    <ResponsiveContainer width="100%" height={160}>
                      <BarChart data={p.asignaturas.map((a: any) => ({ name: a.asignatura.length > 8 ? a.asignatura.substring(0, 8) + '.' : a.asignatura, nota: a.nota }))}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="name" tick={{ fontSize: 8 }} />
                        <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} />
                        <Tooltip />
                        <Bar dataKey="nota" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                ))}
                {/* Tabla académica completa */}
                {historialData.academico.length > 0 && (
                  <div className="bg-white rounded-lg border overflow-hidden">
                    <h3 className="text-xs font-bold text-gray-700 p-3 pb-1">Calificaciones por asignatura</h3>
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead><tr className="bg-gray-50 border-b">
                          <th className="p-2 text-left text-gray-600">Asignatura</th>
                          <th className="p-2 text-center text-gray-600">P1</th><th className="p-2 text-center text-gray-600">P2</th>
                          <th className="p-2 text-center text-gray-600">P3</th><th className="p-2 text-center text-gray-600">P4</th>
                          <th className="p-2 text-center text-gray-600 bg-blue-50 font-bold">CF</th><th className="p-2 text-center text-gray-600">Lit.</th>
                        </tr></thead>
                        <tbody className="divide-y">
                          {historialData.academico.map((a: any, i: number) => (
                            <tr key={i} className="hover:bg-gray-50">
                              <td className="p-2 font-medium text-gray-800">{a.asignatura}</td>
                              {[a.pc1, a.pc2, a.pc3, a.pc4].map((n: any, j: number) => (
                                <td key={j} className={`p-2 text-center ${n !== null && n < 70 ? 'text-red-600 font-bold' : ''}`}>{n !== null ? Math.round(n) : '-'}</td>
                              ))}
                              <td className={`p-2 text-center bg-blue-50 font-bold ${a.cf !== null && a.cf < 70 ? 'text-red-600' : ''}`}>{a.cf !== null ? Math.round(a.cf) : '-'}</td>
                              <td className="p-2 text-center">{a.literal || '-'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* TAB: Conducta */}
            {tabHistorial === 'conducta' && (
              <div className="space-y-3">
                <div className="grid grid-cols-3 gap-2">
                  <div className="bg-white rounded-lg border p-2 text-center">
                    <p className="text-lg font-bold text-gray-700">{historialData.conducta_resumen.total}</p>
                    <p className="text-[10px] text-gray-400">Total reportes</p>
                  </div>
                  <div className="bg-white rounded-lg border p-2 text-center">
                    <p className="text-lg font-bold text-amber-600">{historialData.conducta_resumen.pendientes}</p>
                    <p className="text-[10px] text-gray-400">Pendientes</p>
                  </div>
                  <div className="bg-white rounded-lg border p-2 text-center">
                    <p className="text-lg font-bold text-emerald-600">{historialData.conducta_resumen.resueltos}</p>
                    <p className="text-[10px] text-gray-400">Resueltos</p>
                  </div>
                </div>
                {historialData.conducta.length === 0 ? (
                  <div className="text-center py-6 text-gray-400 text-sm">Sin reportes de conducta</div>
                ) : (
                  <div className="space-y-2 max-h-[400px] overflow-y-auto">
                    {historialData.conducta.map((r: any) => (
                      <div key={r.id} className={`rounded-lg border p-3 ${r.estado === 'pendiente' ? 'bg-amber-50 border-amber-200' : 'bg-white'}`}>
                        <div className="flex justify-between items-start">
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                                r.tipo === 'conducta' ? 'bg-red-100 text-red-700' :
                                r.tipo === 'academico' ? 'bg-blue-100 text-blue-700' :
                                'bg-yellow-100 text-yellow-700'
                              }`}>{r.tipo}</span>
                              <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                                r.estado === 'pendiente' ? 'bg-amber-100 text-amber-700' : 'bg-emerald-100 text-emerald-700'
                              }`}>{r.estado}</span>
                            </div>
                            <p className="text-xs text-gray-800 mt-1">{r.descripcion}</p>
                            {r.respuesta && <p className="text-[10px] text-gray-500 mt-1 italic">Respuesta: {r.respuesta}</p>}
                          </div>
                        </div>
                        <p className="text-[10px] text-gray-400 mt-1">{r.fecha} — {r.reportado_por}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* TAB: Asistencia */}
            {tabHistorial === 'asistencia' && (
              <div className="space-y-3">
                <div className="grid grid-cols-5 gap-2">
                  {[
                    { label: 'Presentes', val: historialData.asistencia.presentes, color: 'text-emerald-600', bg: 'bg-emerald-50' },
                    { label: 'Ausentes', val: historialData.asistencia.ausentes, color: 'text-red-600', bg: 'bg-red-50' },
                    { label: 'Tardanzas', val: historialData.asistencia.tardanzas, color: 'text-amber-600', bg: 'bg-amber-50' },
                    { label: 'Excusas', val: historialData.asistencia.excusas, color: 'text-blue-600', bg: 'bg-blue-50' },
                    { label: 'Asistencia', val: `${historialData.asistencia.porcentaje}%`, color: historialData.asistencia.porcentaje >= 80 ? 'text-emerald-600' : 'text-red-600', bg: 'bg-gray-50' },
                  ].map((item, i) => (
                    <div key={i} className={`${item.bg} rounded-lg border p-2 text-center`}>
                      <p className={`text-sm font-bold ${item.color}`}>{item.val}</p>
                      <p className="text-[9px] text-gray-400">{item.label}</p>
                    </div>
                  ))}
                </div>
                {historialData.asistencia.por_mes.length > 0 && (
                  <div className="bg-white rounded-lg border p-3">
                    <h3 className="text-xs font-bold text-gray-700 mb-2">Asistencia por mes</h3>
                    <ResponsiveContainer width="100%" height={160}>
                      <BarChart data={historialData.asistencia.por_mes}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="mes" tick={{ fontSize: 9 }} />
                        <YAxis tick={{ fontSize: 10 }} />
                        <Tooltip />
                        <Bar dataKey="presentes" fill="#10b981" stackId="a" name="Presentes" />
                        <Bar dataKey="ausentes" fill="#ef4444" stackId="a" name="Ausentes" />
                        <Bar dataKey="tardanzas" fill="#f59e0b" stackId="a" name="Tardanzas" />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                )}
                {historialData.asistencia.porcentaje < 80 && (
                  <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-xs text-red-800">
                    ⚠️ Asistencia por debajo del 80% — requiere seguimiento
                  </div>
                )}
              </div>
            )}

            {/* TAB: Psicología */}
            {tabHistorial === 'psicologia' && (
              <div className="space-y-3">
                <div className="grid grid-cols-3 gap-2">
                  <div className="bg-white rounded-lg border p-2 text-center">
                    <p className="text-lg font-bold text-gray-700">{historialData.psicologia_resumen.total}</p>
                    <p className="text-[10px] text-gray-400">Total casos</p>
                  </div>
                  <div className="bg-white rounded-lg border p-2 text-center">
                    <p className="text-lg font-bold text-amber-600">{historialData.psicologia_resumen.activos}</p>
                    <p className="text-[10px] text-gray-400">Activos</p>
                  </div>
                  <div className="bg-white rounded-lg border p-2 text-center">
                    <p className="text-lg font-bold text-emerald-600">{historialData.psicologia_resumen.atendidos}</p>
                    <p className="text-[10px] text-gray-400">Atendidos</p>
                  </div>
                </div>
                {historialData.psicologia.length === 0 ? (
                  <div className="text-center py-6 text-gray-400 text-sm">Sin casos de psicología registrados</div>
                ) : (
                  <div className="space-y-2 max-h-[400px] overflow-y-auto">
                    {historialData.psicologia.map((c: any) => (
                      <div key={c.id} className="bg-white rounded-lg border p-3">
                        <div className="flex items-center gap-2 mb-1">
                          <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                            c.urgencia === 'alta' ? 'bg-red-100 text-red-700' :
                            c.urgencia === 'media' ? 'bg-amber-100 text-amber-700' :
                            'bg-green-100 text-green-700'
                          }`}>{c.urgencia || 'normal'}</span>
                          <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                            c.estado === 'atendido' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'
                          }`}>{c.estado}</span>
                        </div>
                        <p className="text-xs text-gray-800">{c.motivo}</p>
                        {c.observaciones && <p className="text-[10px] text-gray-500 mt-1">{c.observaciones}</p>}
                        {c.recomendacion_profesor && <p className="text-[10px] text-blue-600 mt-1">Recomendación: {c.recomendacion_profesor}</p>}
                        <p className="text-[10px] text-gray-400 mt-1">{c.fecha}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* TAB: Datos personales */}
            {tabHistorial === 'datos' && (
              <div className="space-y-3">
                <div className="bg-white rounded-lg border p-3">
                  <h3 className="text-xs font-bold text-gray-700 mb-2">Información personal</h3>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    {[
                      ['Nombre', historialData.datos_personales.nombre],
                      ['Matrícula', historialData.datos_personales.matricula],
                      ['Sexo', historialData.datos_personales.sexo === 'M' ? 'Masculino' : 'Femenino'],
                      ['Fecha nac.', historialData.datos_personales.fecha_nacimiento],
                      ['Curso', historialData.datos_personales.curso],
                      ['Grado', historialData.datos_personales.grado],
                      ['Condición', historialData.datos_personales.condicion],
                      ['Dirección', historialData.datos_personales.direccion],
                      ['Teléfono', historialData.datos_personales.telefono],
                      ['NEE', historialData.datos_personales.nee || 'No'],
                    ].filter(([_, v]) => v).map(([label, val], i) => (
                      <div key={i} className="py-1 border-b border-gray-50">
                        <span className="text-gray-400">{label}: </span>
                        <span className="text-gray-800 font-medium">{val}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="bg-white rounded-lg border p-3">
                  <h3 className="text-xs font-bold text-gray-700 mb-2">Contacto padres/tutores</h3>
                  <div className="grid grid-cols-1 gap-2 text-xs">
                    {historialData.datos_personales.nombre_padre && (
                      <div className="flex justify-between py-1 border-b border-gray-50">
                        <span><span className="text-gray-400">Padre:</span> <span className="font-medium">{historialData.datos_personales.nombre_padre}</span></span>
                        <span className="text-blue-600">{historialData.datos_personales.telefono_padre || '-'}</span>
                      </div>
                    )}
                    {historialData.datos_personales.nombre_madre && (
                      <div className="flex justify-between py-1 border-b border-gray-50">
                        <span><span className="text-gray-400">Madre:</span> <span className="font-medium">{historialData.datos_personales.nombre_madre}</span></span>
                        <span className="text-blue-600">{historialData.datos_personales.telefono_madre || '-'}</span>
                      </div>
                    )}
                    {historialData.datos_personales.contacto_emergencia && (
                      <div className="flex justify-between py-1 border-b border-gray-50">
                        <span><span className="text-gray-400">Emergencia:</span> <span className="font-medium">{historialData.datos_personales.contacto_emergencia}</span></span>
                        <span className="text-blue-600">{historialData.datos_personales.telefono_emergencia || '-'}</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="text-center py-8 text-gray-500">No hay datos disponibles</div>
        )}
      </Modal>
    </div>
  );
};

export default EstudiantesPage;
