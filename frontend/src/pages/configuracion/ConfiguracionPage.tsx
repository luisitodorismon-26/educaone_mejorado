import { useState, useEffect } from 'react';
import api from '../../services/api';
import { Modal, Button, Input, Select, Alert } from '../../components/ui';

interface ConfigColegio {
  nombre: string;
  logo: string | null;
  telefono: string;
  email: string;
  direccion: string;
  distrito: string;
  regional: string;
  lema: string;
  director: string;
  umbral_calificacion_baja: number;
  umbral_calificacion_critica: number;
  umbral_asistencia_baja: number;
  dias_ausencia_alerta: number;
  dias_ausencia_critica: number;
  // Nombres de competencias por período
  nombre_p1: string;
  nombre_p2: string;
  nombre_p3: string;
  nombre_p4: string;
}

interface AnoEscolar {
  id: number;
  nombre: string;
  fecha_inicio: string;
  fecha_fin: string;
  activo: boolean;
  periodo_activo: number | null;
  p1_cerrado: boolean;
  p2_cerrado: boolean;
  p3_cerrado: boolean;
  p4_cerrado: boolean;
}

export const ConfiguracionPage = () => {
  const [tab, setTab] = useState('colegio');
  const [config, setConfig] = useState<ConfigColegio | null>(null);
  const [grados, setGrados] = useState<any[]>([]);
  const [tandas, setTandas] = useState<any[]>([]);
  const [asignaturas, setAsignaturas] = useState<any[]>([]);
  const [cursos, setCursos] = useState<any[]>([]);
  const [anoEscolar, setAnoEscolar] = useState<AnoEscolar | null>(null);
  const [feriados, setFeriados] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  // Estado de módulos en formato moderno: { whatsapp: {plan, usa, activo}, ... }
  // Inicia VACÍO — nunca asume estado activo. Solo se llena con la respuesta real del backend.
  const [modulosState, setModulosState] = useState<Record<string, {plan:boolean, usa:boolean, activo:boolean}>>({});
  // whatsapp_solo_direccion y permitir_profesor_reportes son sub-políticas, no módulos
  const [whatsappSoloDir, setWhatsappSoloDir] = useState(false);
  const [permitirProfReportes, setPermitirProfReportes] = useState(false);

  // Modales
  const [showModal, setShowModal] = useState(false);
  const [showAnoModal, setShowAnoModal] = useState(false);
  const [editingAno, setEditingAno] = useState(false);
  const [modalType, setModalType] = useState<'grado' | 'tanda' | 'asignatura' | 'curso' | 'feriado'>('grado');
  const [editingItem, setEditingItem] = useState<any>(null);
  
  // Forms
  const [gradoForm, setGradoForm] = useState({ nombre: '', nombre_completo: '', orden: 1, ciclo: '', nivel: 'secundaria' });
  const [tandaForm, setTandaForm] = useState({ nombre: '', hora_inicio: '07:30', hora_fin: '12:30' });
  const [asignaturaForm, setAsignaturaForm] = useState({ nombre: '', codigo: '', area: '' });
  const [cursoForm, setCursoForm] = useState({ grado_id: 0, seccion: '', tanda_id: 0, capacidad: 35 });
  const [feriadoForm, setFeriadoForm] = useState({ fecha: '', nombre: '', tipo: 'feriado', recurrente: false });
  const [anoForm, setAnoForm] = useState({ nombre: '', fecha_inicio: '', fecha_fin: '' });

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    try {
      const [configRes, gradosRes, tandasRes, asigRes, cursosRes, anoRes, feriadosRes, modulosRes, configColRes] = await Promise.all([
        api.get('/configuracion/colegio'),
        api.get('/grados'),
        api.get('/tandas'),
        api.get('/asignaturas'),
        api.get('/cursos'),
        api.get('/ano-escolar').catch(() => ({ data: null })),
        api.get('/dias-no-laborables').catch(() => ({ data: [] })),
        api.get('/configuracion/modulos').catch(() => ({ data: null })),  // legacy: trae sub-políticas
        api.get('/configuracion').catch(() => ({ data: null })),           // moderno: { modulos: { x: {plan,usa,activo} } }
      ]);
      setConfig(configRes.data);
      setGrados(gradosRes.data);
      setTandas(tandasRes.data);
      setAsignaturas(asigRes.data);
      setCursos(cursosRes.data);
      setAnoEscolar(anoRes.data);
      setFeriados(feriadosRes.data);
      // Formato moderno: el SOURCE OF TRUTH para mostrar/ocultar módulos
      if (configColRes.data?.modulos) {
        setModulosState(configColRes.data.modulos);
      }
      // Legacy: solo para sub-políticas (no son módulos)
      if (modulosRes.data) {
        setWhatsappSoloDir(!!modulosRes.data.whatsapp_solo_direccion);
        setPermitirProfReportes(!!modulosRes.data.permitir_profesor_reportes);
      }
    } catch (e) {
      setMessage({ type: 'error', text: 'Error al cargar datos' });
    } finally {
      setLoading(false);
    }
  };

  const cargarAnoEscolar = async () => {
    try {
      const res = await api.get('/ano-escolar');
      setAnoEscolar(res.data);
    } catch {}
  };

  const handleSaveConfig = async () => {
    setSaving(true);
    try {
      await api.put('/configuracion/colegio', config);
      setMessage({ type: 'success', text: 'Configuración guardada' });
    } catch (e) {
      setMessage({ type: 'error', text: 'Error al guardar' });
    } finally {
      setSaving(false);
    }
  };

  const handleLogoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    
    // Validar tamaño (máx 2MB)
    if (file.size > 2 * 1024 * 1024) {
      setMessage({ type: 'error', text: 'El archivo es muy grande. Máximo 2MB' });
      return;
    }
    
    // Validar tipo
    if (!['image/png', 'image/jpeg', 'image/gif'].includes(file.type)) {
      setMessage({ type: 'error', text: 'Tipo de archivo no permitido. Use PNG, JPG o GIF' });
      return;
    }
    
    const formData = new FormData();
    formData.append('logo', file);
    
    try {
      const res = await api.post('/configuracion/colegio/logo', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      setConfig({ ...config!, logo: res.data.logo });
      setMessage({ type: 'success', text: 'Logo actualizado correctamente' });
    } catch (err: any) {
      setMessage({ type: 'error', text: err.response?.data?.error || 'Error al subir logo' });
    }
  };

  // ============== CRUD GRADOS ==============
  const openGradoModal = (grado?: any) => {
    setModalType('grado');
    setEditingItem(grado || null);
    setGradoForm(grado ? {
      nombre: grado.nombre,
      nombre_completo: grado.nombre_completo || '',
      orden: grado.orden || 1,
      ciclo: grado.ciclo || '',
      nivel: grado.nivel || 'secundaria'
    } : { nombre: '', nombre_completo: '', orden: grados.length + 1, ciclo: 'primer_ciclo', nivel: 'secundaria' });
    setShowModal(true);
  };

  const saveGrado = async () => {
    setSaving(true);
    try {
      if (editingItem) {
        await api.put(`/grados/${editingItem.id}`, gradoForm);
      } else {
        await api.post('/grados', gradoForm);
      }
      loadData();
      setShowModal(false);
      setMessage({ type: 'success', text: editingItem ? 'Grado actualizado' : 'Grado creado' });
    } catch (e: any) {
      setMessage({ type: 'error', text: e.response?.data?.error || 'Error al guardar' });
    } finally {
      setSaving(false);
    }
  };

  const deleteGrado = async (id: number) => {
    if (!confirm('¿Eliminar este grado?')) return;
    try {
      await api.delete(`/grados/${id}`);
      loadData();
      setMessage({ type: 'success', text: 'Grado eliminado' });
    } catch (e: any) {
      setMessage({ type: 'error', text: e.response?.data?.error || 'Error al eliminar' });
    }
  };

  // ============== CRUD TANDAS ==============
  const openTandaModal = (tanda?: any) => {
    setModalType('tanda');
    setEditingItem(tanda || null);
    setTandaForm(tanda ? {
      nombre: tanda.nombre,
      hora_inicio: tanda.hora_inicio || '07:30',
      hora_fin: tanda.hora_fin || '12:30'
    } : { nombre: '', hora_inicio: '07:30', hora_fin: '12:30' });
    setShowModal(true);
  };

  const saveTanda = async () => {
    setSaving(true);
    try {
      if (editingItem) {
        await api.put(`/tandas/${editingItem.id}`, tandaForm);
      } else {
        await api.post('/tandas', tandaForm);
      }
      loadData();
      setShowModal(false);
      setMessage({ type: 'success', text: editingItem ? 'Tanda actualizada' : 'Tanda creada' });
    } catch (e: any) {
      setMessage({ type: 'error', text: e.response?.data?.error || 'Error al guardar' });
    } finally {
      setSaving(false);
    }
  };

  const deleteTanda = async (id: number) => {
    if (!confirm('¿Eliminar esta tanda?')) return;
    try {
      await api.delete(`/tandas/${id}`);
      loadData();
      setMessage({ type: 'success', text: 'Tanda eliminada' });
    } catch (e: any) {
      setMessage({ type: 'error', text: e.response?.data?.error || 'Error al eliminar' });
    }
  };

  // ============== CRUD ASIGNATURAS ==============
  const openAsignaturaModal = (asig?: any) => {
    setModalType('asignatura');
    setEditingItem(asig || null);
    setAsignaturaForm(asig ? {
      nombre: asig.nombre,
      codigo: asig.codigo || '',
      area: asig.area || ''
    } : { nombre: '', codigo: '', area: '' });
    setShowModal(true);
  };

  const saveAsignatura = async () => {
    setSaving(true);
    try {
      if (editingItem) {
        await api.put(`/asignaturas/${editingItem.id}`, asignaturaForm);
      } else {
        await api.post('/asignaturas', asignaturaForm);
      }
      loadData();
      setShowModal(false);
      setMessage({ type: 'success', text: editingItem ? 'Asignatura actualizada' : 'Asignatura creada' });
    } catch (e: any) {
      setMessage({ type: 'error', text: e.response?.data?.error || 'Error al guardar' });
    } finally {
      setSaving(false);
    }
  };

  const deleteAsignatura = async (id: number) => {
    if (!confirm('¿Eliminar esta asignatura?')) return;
    try {
      await api.delete(`/asignaturas/${id}`);
      loadData();
      setMessage({ type: 'success', text: 'Asignatura eliminada' });
    } catch (e: any) {
      setMessage({ type: 'error', text: e.response?.data?.error || 'Error al eliminar' });
    }
  };

  // ============== CRUD CURSOS ==============
  const openCursoModal = (curso?: any) => {
    setModalType('curso');
    setEditingItem(curso || null);
    setCursoForm(curso ? {
      grado_id: curso.grado_id,
      seccion: curso.seccion || '',
      tanda_id: curso.tanda_id || 0,
      capacidad: curso.capacidad || 35
    } : { grado_id: 0, seccion: '', tanda_id: 0, capacidad: 35 });
    setShowModal(true);
  };

  const saveCurso = async () => {
    setSaving(true);
    try {
      const data = {
        ...cursoForm,
        tanda_id: cursoForm.tanda_id || null
      };
      if (editingItem) {
        await api.put(`/cursos/${editingItem.id}`, data);
      } else {
        await api.post('/cursos', data);
      }
      loadData();
      setShowModal(false);
      setMessage({ type: 'success', text: editingItem ? 'Curso actualizado' : 'Curso creado' });
    } catch (e: any) {
      setMessage({ type: 'error', text: e.response?.data?.error || 'Error al guardar' });
    } finally {
      setSaving(false);
    }
  };

  const deleteCurso = async (id: number) => {
    if (!confirm('¿Eliminar este curso?')) return;
    try {
      await api.delete(`/cursos/${id}`);
      loadData();
      setMessage({ type: 'success', text: 'Curso eliminado' });
    } catch (e: any) {
      setMessage({ type: 'error', text: e.response?.data?.error || 'Error al eliminar' });
    }
  };

  // ============== CRUD FERIADOS ==============
  const openFeriadoModal = () => {
    setModalType('feriado');
    setFeriadoForm({ fecha: '', nombre: '', tipo: 'feriado', recurrente: false });
    setShowModal(true);
  };

  const saveFeriado = async () => {
    if (!feriadoForm.fecha || !feriadoForm.nombre) {
      setMessage({ type: 'error', text: 'Fecha y nombre son requeridos' });
      return;
    }
    setSaving(true);
    try {
      await api.post('/dias-no-laborables', feriadoForm);
      loadData();
      setShowModal(false);
      setMessage({ type: 'success', text: 'Día no laborable agregado' });
    } catch (e: any) {
      setMessage({ type: 'error', text: e.response?.data?.error || 'Error al guardar' });
    } finally {
      setSaving(false);
    }
  };

  const deleteFeriado = async (id: number) => {
    if (!confirm('¿Eliminar este día no laborable?')) return;
    try {
      await api.delete(`/dias-no-laborables/${id}`);
      loadData();
      setMessage({ type: 'success', text: 'Eliminado' });
    } catch (e: any) {
      setMessage({ type: 'error', text: e.response?.data?.error || 'Error al eliminar' });
    }
  };

  const cargarFeriadosRD = async () => {
    setSaving(true);
    try {
      const res = await api.post('/dias-no-laborables/cargar-feriados-rd', { ano: new Date().getFullYear() });
      loadData();
      setMessage({ type: 'success', text: res.data.message });
    } catch (e: any) {
      setMessage({ type: 'error', text: e.response?.data?.error || 'Error al cargar feriados' });
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="flex justify-center py-12"><div className="animate-spin h-8 w-8 border-2 border-blue-600 rounded-full border-t-transparent"></div></div>;

  const tabs = [
    { id: 'colegio', label: '🏫 Colegio' },
    { id: 'periodos', label: '📅 Períodos' },
    { id: 'grados', label: '📚 Grados' },
    { id: 'tandas', label: '🕐 Tandas' },
    { id: 'asignaturas', label: '📖 Asignaturas' },
    { id: 'cursos', label: '🎓 Cursos' },
    { id: 'feriados', label: '🗓️ Feriados' },
    { id: 'alertas', label: '🚨 Alertas' },
    { id: 'modulos', label: '🔧 Módulos' },
  ];

  // Funciones para manejo de períodos
  const handleCerrarPeriodo = async (periodo: number) => {
    if (!confirm(`¿Está seguro de cerrar el Período ${periodo}? Los profesores ya no podrán editar calificaciones de este período.`)) return;
    setSaving(true);
    try {
      await api.post(`/periodos/${periodo}/cerrar`);
      loadData();
      setMessage({ type: 'success', text: `Período ${periodo} cerrado correctamente` });
    } catch (e: any) {
      setMessage({ type: 'error', text: e.response?.data?.error || 'Error al cerrar período' });
    } finally {
      setSaving(false);
    }
  };

  const handleAbrirPeriodo = async (periodo: number) => {
    if (!confirm(`¿Abrir el Período ${periodo} para edición?`)) return;
    setSaving(true);
    try {
      await api.post(`/periodos/${periodo}/abrir`);
      loadData();
      setMessage({ type: 'success', text: `Período ${periodo} abierto para edición` });
    } catch (e: any) {
      setMessage({ type: 'error', text: e.response?.data?.error || 'Error al abrir período' });
    } finally {
      setSaving(false);
    }
  };

  const saveAnoEscolar = async () => {
    if (!anoForm.nombre) {
      setMessage({ type: 'error', text: 'El nombre es requerido' });
      return;
    }
    setSaving(true);
    try {
      if (editingAno && anoEscolar) {
        await api.put(`/ano-escolar/${anoEscolar.id}`, anoForm);
        setMessage({ type: 'success', text: 'Año escolar actualizado correctamente' });
      } else {
        await api.post('/ano-escolar', anoForm);
        setMessage({ type: 'success', text: 'Año escolar creado correctamente' });
      }
      loadData();
      setShowAnoModal(false);
      setEditingAno(false);
      setAnoForm({ nombre: '', fecha_inicio: '', fecha_fin: '' });
    } catch (e: any) {
      setMessage({ type: 'error', text: e.response?.data?.error || 'Error al guardar año escolar' });
    } finally {
      setSaving(false);
    }
  };

  const getNombreCompetencia = (periodo: number) => {
    const nombres: Record<number, string> = {
      1: config?.nombre_p1 || 'Comunicativa',
      2: config?.nombre_p2 || 'Pensamiento Lógico, Creativo y Crítico',
      3: config?.nombre_p3 || 'Científica y Tecnológica',
      4: config?.nombre_p4 || 'Desarrollo Personal'
    };
    return nombres[periodo];
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">⚙️ Configuración</h1>

      {message && (
        <Alert variant={message.type} onClose={() => setMessage(null)}>{message.text}</Alert>
      )}

      {/* Tabs */}
      <div className="flex gap-1 border-b overflow-x-auto bg-white rounded-t-lg">
        {tabs.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-3 font-medium border-b-2 whitespace-nowrap transition-colors ${
              tab === t.id ? 'border-blue-600 text-blue-600 bg-blue-50' : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab: Colegio */}
      {tab === 'colegio' && config && (
        <div className="bg-white rounded-lg border p-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="md:col-span-2 flex items-center gap-6">
              <div className="relative">
                {config.logo ? (
                  <img src={config.logo} alt="Logo" className="w-24 h-24 object-contain border rounded-lg" />
                ) : (
                  <div className="w-24 h-24 bg-gray-100 rounded-lg flex items-center justify-center text-gray-400">
                    Sin logo
                  </div>
                )}
                <input type="file" accept="image/*" onChange={handleLogoUpload} className="absolute inset-0 opacity-0 cursor-pointer" />
              </div>
              <div>
                <p className="font-medium">Logo del Colegio</p>
                <p className="text-sm text-gray-500">Haz clic para cambiar</p>
              </div>
            </div>
            <Input label="Nombre del Colegio" value={config.nombre} onChange={e => setConfig({ ...config, nombre: e.target.value })} />
            <Input label="Director(a)" value={config.director || ''} onChange={e => setConfig({ ...config, director: e.target.value })} />
            <Input label="Teléfono" value={config.telefono || ''} onChange={e => setConfig({ ...config, telefono: e.target.value })} />
            <Input label="Email" value={config.email || ''} onChange={e => setConfig({ ...config, email: e.target.value })} />
            <div className="md:col-span-2">
              <Input label="Dirección" value={config.direccion || ''} onChange={e => setConfig({ ...config, direccion: e.target.value })} />
            </div>
            <Input label="Distrito" value={config.distrito || ''} onChange={e => setConfig({ ...config, distrito: e.target.value })} />
            <Input label="Regional" value={config.regional || ''} onChange={e => setConfig({ ...config, regional: e.target.value })} />
            <div className="md:col-span-2">
              <Input label="Lema" value={config.lema || ''} onChange={e => setConfig({ ...config, lema: e.target.value })} />
            </div>

            {/* Datos MINERD para Registro Escolar */}
            <div className="md:col-span-2 border-t pt-4 mt-2">
              <h3 className="font-medium mb-1 text-gray-800">📋 Datos MINERD (Registro Escolar)</h3>
              <p className="text-xs text-gray-500 mb-4">Estos datos aparecen en el registro escolar oficial. Son opcionales — si no los llenas, esas casillas quedan vacías en el PDF.</p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Input label="Código del Centro (SIGERD)" value={(config as any).codigo_centro || ''} onChange={e => setConfig({ ...config, codigo_centro: e.target.value })} placeholder="Ej: 08-01-0123" />
                <Input label="Código Cartográfico" value={(config as any).codigo_cartografia || ''} onChange={e => setConfig({ ...config, codigo_cartografia: e.target.value })} />
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Sector</label>
                  <select value={(config as any).sector || ''} onChange={e => setConfig({ ...config, sector: e.target.value })} className="w-full border rounded-lg px-3 py-2 text-sm">
                    <option value="">— Sin definir —</option>
                    <option value="publico">Público</option>
                    <option value="privado">Privado</option>
                    <option value="semioficial">Semioficial</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Zona</label>
                  <select value={(config as any).zona || ''} onChange={e => setConfig({ ...config, zona: e.target.value })} className="w-full border rounded-lg px-3 py-2 text-sm">
                    <option value="">— Sin definir —</option>
                    <option value="urbana">Urbana</option>
                    <option value="urbana_marginal">Urbana Marginal</option>
                    <option value="rural">Rural</option>
                    <option value="rural_aislada">Rural Aislada</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Tanda / Jornada</label>
                  <select value={(config as any).tanda_operacion || ''} onChange={e => setConfig({ ...config, tanda_operacion: e.target.value })} className="w-full border rounded-lg px-3 py-2 text-sm">
                    <option value="">— Sin definir —</option>
                    <option value="jee">Jornada Escolar Extendida</option>
                    <option value="matutina">Matutina</option>
                    <option value="vespertina">Vespertina</option>
                    <option value="nocturna">Nocturna</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Modalidad</label>
                  <select value={(config as any).modalidad || ''} onChange={e => setConfig({ ...config, modalidad: e.target.value })} className="w-full border rounded-lg px-3 py-2 text-sm">
                    <option value="">— Sin definir —</option>
                    <option value="General">General</option>
                    <option value="Académica">Académica</option>
                    <option value="Técnico Profesional">Técnico Profesional</option>
                    <option value="Artes">Artes</option>
                  </select>
                </div>
                <Input label="Nombre del Director(a)" value={(config as any).nombre_director || ''} onChange={e => setConfig({ ...config, nombre_director: e.target.value })} placeholder="Nombre completo" />
                <Input label="Cédula del Director(a)" value={(config as any).cedula_director || ''} onChange={e => setConfig({ ...config, cedula_director: e.target.value })} placeholder="000-0000000-0" />
                <Input label="Correo del Director(a)" value={(config as any).correo_director || ''} onChange={e => setConfig({ ...config, correo_director: e.target.value })} />
                <Input label="Teléfono del Director(a)" value={(config as any).telefono_director || ''} onChange={e => setConfig({ ...config, telefono_director: e.target.value })} />
                <Input label="Coordinador(a) Académico" value={(config as any).nombre_coordinador || ''} onChange={e => setConfig({ ...config, nombre_coordinador: e.target.value })} />
                <Input label="Correo Institucional" value={(config as any).correo_centro || ''} onChange={e => setConfig({ ...config, correo_centro: e.target.value })} />
              </div>
            </div>
            <div className="md:col-span-2 border-t pt-4 mt-4">
              <h3 className="font-medium mb-4">Sistema de Calificaciones</h3>
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                <p className="text-sm text-blue-800 font-medium mb-2">Estructura por Competencias (MINERD)</p>
                <ul className="text-sm text-blue-700 space-y-1">
                  <li>• <strong>P1 - Comunicativa:</strong> 4 parciales → Promedio → Recuperación si &lt; 70</li>
                  <li>• <strong>P2 - Pensamiento Lógico, Creativo y Crítico:</strong> 4 parciales → Promedio → Recuperación si &lt; 70</li>
                  <li>• <strong>P3 - Científica y Tecnológica:</strong> 4 parciales → Promedio → Recuperación si &lt; 70</li>
                  <li>• <strong>P4 - Desarrollo Personal:</strong> 4 parciales → Promedio → Recuperación si &lt; 70</li>
                </ul>
                <p className="text-xs text-blue-600 mt-2">CF = Promedio de los 4 períodos (usando RP si PC &lt; 70)</p>
              </div>
            </div>
            <div className="md:col-span-2 flex justify-end">
              <Button onClick={handleSaveConfig} loading={saving}>Guardar Configuración</Button>
            </div>
          </div>
        </div>
      )}

      {/* Tab: Períodos */}
      {tab === 'periodos' && (
        <div className="space-y-6">
          {/* Info Año Escolar */}
          <div className="bg-white rounded-lg border p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-gray-800">📅 Año Escolar Activo</h3>
              <div className="flex gap-2">
                {anoEscolar && (
                  <Button variant="secondary" onClick={() => {
                    setAnoForm({
                      nombre: anoEscolar.nombre,
                      fecha_inicio: anoEscolar.fecha_inicio || '',
                      fecha_fin: anoEscolar.fecha_fin || ''
                    });
                    setEditingAno(true);
                    setShowAnoModal(true);
                  }}>✏️ Editar</Button>
                )}
                {!anoEscolar && (
                  <Button onClick={() => { setEditingAno(false); setShowAnoModal(true); }}>+ Crear Año Escolar</Button>
                )}
              </div>
            </div>
            {anoEscolar ? (
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-2xl font-bold text-blue-600">{anoEscolar.nombre}</p>
                  <p className="text-sm text-gray-500">
                    {anoEscolar.fecha_inicio} al {anoEscolar.fecha_fin}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-sm text-gray-500">Período Activo</p>
                  <p className="text-xl font-bold text-emerald-600">
                    {anoEscolar.periodo_activo ? `P${anoEscolar.periodo_activo}` : 'Ninguno'}
                  </p>
                </div>
              </div>
            ) : (
              <div className="text-center py-6">
                <p className="text-gray-500 mb-4">No hay año escolar activo</p>
                <Button onClick={() => { setEditingAno(false); setShowAnoModal(true); }}>+ Crear Año Escolar</Button>
              </div>
            )}
          </div>

          {/* Control de Períodos */}
          <div className="bg-white rounded-lg border p-6">
            <h3 className="font-semibold text-gray-800 mb-4">🔐 Control de Períodos</h3>
            <p className="text-sm text-gray-600 mb-6">
              Aquí puede abrir o cerrar los períodos de calificación. Los profesores solo pueden registrar notas en períodos abiertos.
            </p>
            
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {[1, 2, 3, 4].map(periodo => {
                const cerrado = anoEscolar ? (anoEscolar as any)[`p${periodo}_cerrado`] : true;
                const esActivo = anoEscolar?.periodo_activo === periodo;
                const pInicio = anoEscolar ? (anoEscolar as any)[`p${periodo}_inicio`] || '' : '';
                const pFin = anoEscolar ? (anoEscolar as any)[`p${periodo}_fin`] || '' : '';
                
                return (
                  <div 
                    key={periodo}
                    className={`p-4 rounded-lg border-2 ${
                      cerrado 
                        ? 'border-red-200 bg-red-50' 
                        : esActivo 
                          ? 'border-emerald-400 bg-emerald-50' 
                          : 'border-blue-200 bg-blue-50'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-bold text-lg">P{periodo}</span>
                      <span className={`px-2 py-1 text-xs font-bold rounded ${
                        cerrado ? 'bg-red-200 text-red-800' : 'bg-emerald-200 text-emerald-800'
                      }`}>
                        {cerrado ? '🔒 Cerrado' : '🔓 Abierto'}
                      </span>
                    </div>
                    <p className="text-xs text-gray-600 mb-2">{getNombreCompetencia(periodo)}</p>
                    
                    {/* Fechas del período */}
                    <div className="space-y-1 mb-3">
                      <div>
                        <label className="text-[10px] font-medium text-gray-500 uppercase">Inicio</label>
                        <input type="date" value={pInicio} onChange={async (e) => {
                          try {
                            await api.put('/periodos/configurar', { [`p${periodo}_inicio`]: e.target.value });
                            cargarAnoEscolar();
                          } catch {}
                        }} className="w-full text-xs border rounded px-2 py-1 bg-white" />
                      </div>
                      <div>
                        <label className="text-[10px] font-medium text-gray-500 uppercase">Entrega</label>
                        <input type="date" value={pFin} onChange={async (e) => {
                          try {
                            await api.put('/periodos/configurar', { [`p${periodo}_fin`]: e.target.value });
                            cargarAnoEscolar();
                          } catch {}
                        }} className="w-full text-xs border rounded px-2 py-1 bg-white" />
                      </div>
                    </div>
                    
                    {cerrado ? (
                      <button
                        onClick={() => handleAbrirPeriodo(periodo)}
                        disabled={saving}
                        className="w-full py-2 px-3 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium rounded transition-colors disabled:opacity-50"
                      >
                        Abrir Período
                      </button>
                    ) : (
                      <button
                        onClick={() => handleCerrarPeriodo(periodo)}
                        disabled={saving}
                        className="w-full py-2 px-3 bg-red-600 hover:bg-red-700 text-white text-sm font-medium rounded transition-colors disabled:opacity-50"
                      >
                        Cerrar Período
                      </button>
                    )}
                  </div>
                );
              })}
            </div>

            <div className="mt-6 p-4 bg-amber-50 border border-amber-200 rounded-lg">
              <p className="text-sm text-amber-800">
                <strong>⚠️ Importante:</strong> Al cerrar un período, los profesores ya no podrán modificar las calificaciones de ese período. 
                Solo la dirección podrá editar notas en períodos cerrados.
              </p>
            </div>
          </div>

          {/* Nombres de Competencias */}
          {config && (
            <div className="bg-white rounded-lg border p-6">
              <h3 className="font-semibold text-gray-800 mb-4">📝 Nombres de Competencias por Período</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Input 
                  label="P1 - Competencia" 
                  value={config.nombre_p1 || ''} 
                  onChange={e => setConfig({ ...config, nombre_p1: e.target.value })}
                  placeholder="Comunicativa"
                />
                <Input 
                  label="P2 - Competencia" 
                  value={config.nombre_p2 || ''} 
                  onChange={e => setConfig({ ...config, nombre_p2: e.target.value })}
                  placeholder="Pensamiento Lógico, Creativo y Crítico"
                />
                <Input 
                  label="P3 - Competencia" 
                  value={config.nombre_p3 || ''} 
                  onChange={e => setConfig({ ...config, nombre_p3: e.target.value })}
                  placeholder="Científica y Tecnológica"
                />
                <Input 
                  label="P4 - Competencia" 
                  value={config.nombre_p4 || ''} 
                  onChange={e => setConfig({ ...config, nombre_p4: e.target.value })}
                  placeholder="Desarrollo Personal"
                />
              </div>
              <div className="mt-4 flex justify-end">
                <Button onClick={handleSaveConfig} loading={saving}>Guardar Nombres</Button>
              </div>
            </div>
          )}

          {/* Datos MINERD para Registro Escolar */}
          {config && (
            <div className="bg-white rounded-lg border p-6">
              <h3 className="font-semibold text-gray-800 mb-2">🏫 Datos MINERD — Registro Escolar</h3>
              <p className="text-xs text-gray-500 mb-4">Estos datos aparecen en el registro escolar oficial. Son opcionales — el registro se imprime aunque estén vacíos.</p>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                <Input label="Código del Centro (SIGERD)" value={config.codigo_centro || ''} onChange={e => setConfig({...config, codigo_centro: e.target.value})} placeholder="Ej: 01234" />
                <Input label="Código Cartográfico" value={config.codigo_cartografia || ''} onChange={e => setConfig({...config, codigo_cartografia: e.target.value})} placeholder="" />
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Sector</label>
                  <select className="w-full border rounded-lg px-3 py-2 text-sm" value={config.sector || ''} onChange={e => setConfig({...config, sector: e.target.value})}>
                    <option value="">— Seleccionar —</option>
                    <option value="publico">Público</option>
                    <option value="privado">Privado</option>
                    <option value="semioficial">Semioficial</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Zona</label>
                  <select className="w-full border rounded-lg px-3 py-2 text-sm" value={config.zona || ''} onChange={e => setConfig({...config, zona: e.target.value})}>
                    <option value="">— Seleccionar —</option>
                    <option value="urbana">Urbana</option>
                    <option value="urbana_marginal">Urbana Marginal</option>
                    <option value="rural">Rural</option>
                    <option value="rural_aislada">Rural Aislada</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Tanda / Jornada</label>
                  <select className="w-full border rounded-lg px-3 py-2 text-sm" value={config.tanda_operacion || ''} onChange={e => setConfig({...config, tanda_operacion: e.target.value})}>
                    <option value="">— Seleccionar —</option>
                    <option value="jee">Jornada Escolar Extendida</option>
                    <option value="matutina">Matutina</option>
                    <option value="vespertina">Vespertina</option>
                    <option value="nocturna">Nocturna</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Modalidad</label>
                  <select className="w-full border rounded-lg px-3 py-2 text-sm" value={config.modalidad || ''} onChange={e => setConfig({...config, modalidad: e.target.value})}>
                    <option value="">— Seleccionar —</option>
                    <option value="General">General</option>
                    <option value="Académica">Académica</option>
                    <option value="Técnica">Técnica</option>
                    <option value="Artes">Artes</option>
                  </select>
                </div>
                <Input label="Correo Institucional" value={config.correo_centro || ''} onChange={e => setConfig({...config, correo_centro: e.target.value})} placeholder="info@micolegio.edu.do" />
                <Input label="Nombre del Director(a)" value={config.nombre_director || ''} onChange={e => setConfig({...config, nombre_director: e.target.value})} placeholder="Lic. Juan Pérez" />
                <Input label="Cédula del Director(a)" value={config.cedula_director || ''} onChange={e => setConfig({...config, cedula_director: e.target.value})} placeholder="001-0000000-0" />
                <Input label="Correo del Director(a)" value={config.correo_director || ''} onChange={e => setConfig({...config, correo_director: e.target.value})} placeholder="" />
                <Input label="Teléfono del Director(a)" value={config.telefono_director || ''} onChange={e => setConfig({...config, telefono_director: e.target.value})} placeholder="" />
                <Input label="Coordinador(a) Académico" value={config.nombre_coordinador || ''} onChange={e => setConfig({...config, nombre_coordinador: e.target.value})} placeholder="" />
              </div>
              <div className="mt-4 flex justify-end">
                <Button onClick={handleSaveConfig} loading={saving}>Guardar Datos MINERD</Button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Tab: Grados */}
      {tab === 'grados' && (
        <div className="bg-white rounded-lg border">
          <div className="flex justify-between items-center p-4 border-b">
            <h3 className="font-semibold text-gray-800">📚 Grados ({grados.length})</h3>
            <Button onClick={() => openGradoModal()} size="sm">+ Nuevo Grado</Button>
          </div>
          <table className="w-full">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Orden</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Nombre</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Nombre Completo</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Nivel</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Ciclo</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {grados.length === 0 ? (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-gray-500">No hay grados. Crea el primero.</td></tr>
              ) : grados.map(g => (
                <tr key={g.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 text-gray-500">{g.orden}</td>
                  <td className="px-4 py-3 font-medium text-gray-900">{g.nombre}</td>
                  <td className="px-4 py-3 text-gray-600">{g.nombre_completo || '-'}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-1 text-xs rounded-full ${g.nivel === 'primaria' ? 'bg-indigo-100 text-indigo-700' : 'bg-blue-100 text-blue-700'}`}>
                      {g.nivel === 'primaria' ? 'Primaria' : 'Secundaria'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-600">{g.ciclo === 'primer_ciclo' ? '1er Ciclo' : g.ciclo === 'segundo_ciclo' ? '2do Ciclo' : '-'}</td>
                  <td className="px-4 py-3 text-right">
                    <button onClick={() => openGradoModal(g)} className="text-blue-600 hover:text-blue-800 text-sm mr-3">Editar</button>
                    <button onClick={() => deleteGrado(g.id)} className="text-red-600 hover:text-red-800 text-sm">Eliminar</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Tab: Tandas */}
      {tab === 'tandas' && (
        <div className="bg-white rounded-lg border">
          <div className="flex justify-between items-center p-4 border-b">
            <h3 className="font-semibold text-gray-800">🕐 Tandas ({tandas.length})</h3>
            <Button onClick={() => openTandaModal()} size="sm">+ Nueva Tanda</Button>
          </div>
          <table className="w-full">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Nombre</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Hora Inicio</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Hora Fin</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {tandas.length === 0 ? (
                <tr><td colSpan={4} className="px-4 py-8 text-center text-gray-500">No hay tandas. Crea la primera.</td></tr>
              ) : tandas.map(t => (
                <tr key={t.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-gray-900">{t.nombre}</td>
                  <td className="px-4 py-3 text-gray-600">{t.hora_inicio}</td>
                  <td className="px-4 py-3 text-gray-600">{t.hora_fin}</td>
                  <td className="px-4 py-3 text-right">
                    <button onClick={() => openTandaModal(t)} className="text-blue-600 hover:text-blue-800 text-sm mr-3">Editar</button>
                    <button onClick={() => deleteTanda(t.id)} className="text-red-600 hover:text-red-800 text-sm">Eliminar</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Tab: Asignaturas */}
      {tab === 'asignaturas' && (
        <div className="bg-white rounded-lg border">
          <div className="flex justify-between items-center p-4 border-b">
            <h3 className="font-semibold text-gray-800">📖 Asignaturas ({asignaturas.length})</h3>
            <Button onClick={() => openAsignaturaModal()} size="sm">+ Nueva Asignatura</Button>
          </div>
          <table className="w-full">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Nombre</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Código</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Área</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {asignaturas.length === 0 ? (
                <tr><td colSpan={4} className="px-4 py-8 text-center text-gray-500">No hay asignaturas. Crea la primera.</td></tr>
              ) : asignaturas.map(a => (
                <tr key={a.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-gray-900">{a.nombre}</td>
                  <td className="px-4 py-3 text-gray-600">{a.codigo || '-'}</td>
                  <td className="px-4 py-3 text-gray-600">{a.area || '-'}</td>
                  <td className="px-4 py-3 text-right">
                    <button onClick={() => openAsignaturaModal(a)} className="text-blue-600 hover:text-blue-800 text-sm mr-3">Editar</button>
                    <button onClick={() => deleteAsignatura(a.id)} className="text-red-600 hover:text-red-800 text-sm">Eliminar</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Tab: Cursos */}
      {tab === 'cursos' && (
        <div className="bg-white rounded-lg border">
          <div className="flex justify-between items-center p-4 border-b">
            <h3 className="font-semibold text-gray-800">🎓 Cursos ({cursos.length})</h3>
            <Button onClick={() => openCursoModal()} size="sm">+ Nuevo Curso</Button>
          </div>
          {grados.length === 0 ? (
            <div className="p-8 text-center text-gray-500">
              <p>Primero debes crear grados antes de crear cursos.</p>
              <button onClick={() => setTab('grados')} className="mt-2 text-blue-600 hover:underline">Ir a Grados</button>
            </div>
          ) : (
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Curso</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Grado</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Tanda</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Capacidad</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Estudiantes</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">Acciones</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {cursos.length === 0 ? (
                  <tr><td colSpan={6} className="px-4 py-8 text-center text-gray-500">No hay cursos. Crea el primero.</td></tr>
                ) : cursos.map(c => (
                  <tr key={c.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium text-gray-900">{c.nombre_completo}</td>
                    <td className="px-4 py-3 text-gray-600">{c.grado}</td>
                    <td className="px-4 py-3">
                      {c.tanda ? (
                        <span className={`px-2 py-1 text-xs rounded-full ${c.tanda.includes('Matutina') ? 'bg-amber-100 text-amber-700' : 'bg-purple-100 text-purple-700'}`}>
                          {c.tanda}
                        </span>
                      ) : '-'}
                    </td>
                    <td className="px-4 py-3 text-gray-600">{c.capacidad}</td>
                    <td className="px-4 py-3 text-gray-600">{c.estudiantes_count || 0}</td>
                    <td className="px-4 py-3 text-right">
                      <button onClick={() => openCursoModal(c)} className="text-blue-600 hover:text-blue-800 text-sm mr-3">Editar</button>
                      <button onClick={() => deleteCurso(c.id)} className="text-red-600 hover:text-red-800 text-sm">Eliminar</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Tab: Feriados */}
      {tab === 'feriados' && (
        <div className="bg-white rounded-lg border p-6">
          <div className="flex justify-between items-center mb-4">
            <h3 className="font-semibold text-gray-800">🗓️ Días No Laborables</h3>
            <div className="flex gap-2">
              <Button variant="secondary" onClick={cargarFeriadosRD} loading={saving}>
                🇩🇴 Cargar Feriados RD
              </Button>
              <Button onClick={openFeriadoModal}>+ Agregar</Button>
            </div>
          </div>
          
          {feriados.length === 0 ? (
            <p className="text-gray-500 text-center py-8">No hay días no laborables configurados</p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {feriados.sort((a, b) => a.fecha.localeCompare(b.fecha)).map(f => (
                <div key={f.id} className={`p-3 rounded-lg border flex justify-between items-center ${
                  f.tipo === 'feriado' ? 'bg-green-50 border-green-200' :
                  f.tipo === 'vacaciones' ? 'bg-blue-50 border-blue-200' :
                  'bg-amber-50 border-amber-200'
                }`}>
                  <div>
                    <p className="font-medium text-gray-800">{f.nombre}</p>
                    <p className="text-sm text-gray-500">
                      {new Date(f.fecha + 'T12:00:00').toLocaleDateString('es-DO', { weekday: 'short', day: 'numeric', month: 'short' })}
                      {f.recurrente && <span className="ml-2 text-xs bg-white px-1.5 py-0.5 rounded">🔄 Anual</span>}
                    </p>
                  </div>
                  <button onClick={() => deleteFeriado(f.id)} className="text-red-500 hover:text-red-700 p-1">
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clipRule="evenodd" />
                    </svg>
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Tab: Alertas */}
      {tab === 'alertas' && config && (
        <div className="bg-white rounded-lg border p-6">
          <h3 className="font-semibold text-gray-800 mb-4">🚨 Umbrales de Alertas</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Input label="Calificación Baja (amarillo)" type="number" value={config.umbral_calificacion_baja} onChange={e => setConfig({ ...config, umbral_calificacion_baja: parseInt(e.target.value) || 0 })} />
            <Input label="Calificación Crítica (rojo)" type="number" value={config.umbral_calificacion_critica} onChange={e => setConfig({ ...config, umbral_calificacion_critica: parseInt(e.target.value) || 0 })} />
            <Input label="Asistencia Baja (%)" type="number" value={config.umbral_asistencia_baja} onChange={e => setConfig({ ...config, umbral_asistencia_baja: parseInt(e.target.value) || 0 })} />
            <Input label="Días Ausencia (alerta)" type="number" value={config.dias_ausencia_alerta} onChange={e => setConfig({ ...config, dias_ausencia_alerta: parseInt(e.target.value) || 0 })} />
            <Input label="Días Ausencia (crítico)" type="number" value={config.dias_ausencia_critica} onChange={e => setConfig({ ...config, dias_ausencia_critica: parseInt(e.target.value) || 0 })} />
          </div>
          <div className="mt-4 flex justify-end">
            <Button onClick={handleSaveConfig} loading={saving}>Guardar Umbrales</Button>
          </div>
        </div>
      )}

      {tab === 'modulos' && (
        <div className="bg-white rounded-xl border p-6">
          <div className="mb-6">
            <h3 className="text-lg font-semibold text-gray-800">🔧 Módulos del Sistema</h3>
            <p className="text-sm text-gray-500 mt-1">
              Los módulos contratados están <strong>activos automáticamente</strong> para todos los usuarios del colegio según su rol.
            </p>
            <p className="text-xs text-gray-400 mt-1">
              Para modificar los módulos de su plan, contacte a soporte.
            </p>
          </div>

          {(() => {
            // v2.11: solo se muestra el plan (lo que el colegio contrató).
            // No hay toggles. La pantalla es informativa.
            const todos = [
              { key: 'secundaria', label: '🎓 Secundaria', desc: 'Permite crear cursos y plan de estudios de secundaria (MINERD)' },
              { key: 'primaria', label: '📚 Primaria', desc: 'Permite crear cursos y plan de estudios de primaria (MINERD)' },
              { key: 'whatsapp', label: '💬 WhatsApp', desc: 'Permite enviar mensajes a padres/tutores directamente por WhatsApp' },
              { key: 'psicologia', label: '🧠 Psicología', desc: 'Módulo de casos, atención psicológica y seguimiento de estudiantes' },
              { key: 'comunicacion_padres', label: '📱 Comunicación a Padres', desc: 'Registro de comunicaciones enviadas a padres como evidencia legal' },
              { key: 'eval_profesores', label: '📋 Evaluación de Profesores', desc: 'Evaluación interna de desempeño docente por la dirección' },
              { key: 'eval_interna', label: '📊 Evaluación Interna Estudiantes', desc: 'Evaluación por criterios de cada estudiante' },
              { key: 'registro_escolar', label: '📄 Registro Escolar MINERD', desc: 'Generación del registro escolar oficial en formato MINERD' },
              { key: 'reportes_conducta', label: '⚠️ Reportes de Conducta', desc: 'Sistema de reportes disciplinarios profesional para padres' },
            ];

            const incluidos = todos.filter(m => modulosState[m.key]?.plan === true);
            const noIncluidos = todos.filter(m => modulosState[m.key]?.plan === false);

            return (
              <div className="space-y-6">
                {/* Módulos incluidos en el plan */}
                <div>
                  <p className="text-sm font-medium text-gray-700 mb-3">
                    ✅ Su plan incluye {incluidos.length} módulo{incluidos.length !== 1 ? 's' : ''}:
                  </p>
                  {incluidos.length === 0 ? (
                    <p className="text-sm text-gray-500 italic">Su plan no tiene módulos activos.</p>
                  ) : (
                    <div className="space-y-2">
                      {incluidos.map(mod => (
                        <div key={mod.key} className="flex items-start p-4 rounded-xl border bg-blue-50/50 border-blue-200">
                          <div className="flex-1">
                            <p className="font-medium text-gray-800 text-sm">{mod.label}</p>
                            <p className="text-xs text-gray-500 mt-0.5">{mod.desc}</p>
                          </div>
                          <div className="ml-4 px-2 py-1 bg-green-100 text-green-800 text-xs rounded-full font-medium">
                            Activo
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Módulos no incluidos */}
                {noIncluidos.length > 0 && (
                  <div>
                    <p className="text-sm font-medium text-gray-700 mb-3">
                      ⛔ No incluidos en su plan:
                    </p>
                    <div className="space-y-2">
                      {noIncluidos.map(mod => (
                        <div key={mod.key} className="flex items-start p-4 rounded-xl border bg-gray-50 border-gray-200 opacity-70">
                          <div className="flex-1">
                            <p className="font-medium text-gray-700 text-sm">{mod.label}</p>
                            <p className="text-xs text-gray-500 mt-0.5">{mod.desc}</p>
                          </div>
                          <div className="ml-4 px-2 py-1 bg-gray-200 text-gray-700 text-xs rounded-full font-medium">
                            No contratado
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })()}

          <div className="mt-6 pt-4 border-t">
            <p className="text-xs text-gray-400">
              ¿Necesita agregar o quitar módulos? Escriba a soporte y solicite un cambio de plan.
            </p>
          </div>
        </div>
      )}

      {/* Modal Grado */}
      <Modal isOpen={showModal && modalType === 'grado'} onClose={() => setShowModal(false)} title={editingItem ? 'Editar Grado' : 'Nuevo Grado'} size="md"
        footer={<><Button variant="secondary" onClick={() => setShowModal(false)}>Cancelar</Button><Button onClick={saveGrado} loading={saving}>{editingItem ? 'Guardar' : 'Crear'}</Button></>}>
        <div className="space-y-4">
          <Input label="Nombre corto *" placeholder="Ej: 1ro, 2do, 3ro" value={gradoForm.nombre} onChange={e => setGradoForm({ ...gradoForm, nombre: e.target.value })} />
          <Input label="Nombre completo" placeholder="Ej: 1ro de Secundaria" value={gradoForm.nombre_completo} onChange={e => setGradoForm({ ...gradoForm, nombre_completo: e.target.value })} />
          <div className="grid grid-cols-2 gap-4">
            <Select label="Nivel *" value={gradoForm.nivel} onChange={e => setGradoForm({ ...gradoForm, nivel: e.target.value })} options={[
              { value: 'secundaria', label: 'Secundaria' },
              { value: 'primaria', label: 'Primaria' }
            ]} />
            <Select label="Ciclo" value={gradoForm.ciclo} onChange={e => setGradoForm({ ...gradoForm, ciclo: e.target.value })} options={[
              { value: 'primer_ciclo', label: '1er Ciclo (1ro-3ro)' },
              { value: 'segundo_ciclo', label: '2do Ciclo (4to-6to)' }
            ]} />
          </div>
          <Input label="Orden" type="number" value={gradoForm.orden} onChange={e => setGradoForm({ ...gradoForm, orden: parseInt(e.target.value) || 1 })} />
          {gradoForm.nivel === 'primaria' && (
            <div className="bg-indigo-50 border border-indigo-200 rounded-lg p-3 text-sm text-indigo-800">
              <strong>Primaria:</strong> las calificaciones se registran por competencias (C1, C2, C3). Inglés en 2do ciclo tiene 2 competencias.
            </div>
          )}
        </div>
      </Modal>

      {/* Modal Tanda */}
      <Modal isOpen={showModal && modalType === 'tanda'} onClose={() => setShowModal(false)} title={editingItem ? 'Editar Tanda' : 'Nueva Tanda'} size="md"
        footer={<><Button variant="secondary" onClick={() => setShowModal(false)}>Cancelar</Button><Button onClick={saveTanda} loading={saving}>{editingItem ? 'Guardar' : 'Crear'}</Button></>}>
        <div className="space-y-4">
          <Input label="Nombre *" placeholder="Ej: Matutina, Vespertina" value={tandaForm.nombre} onChange={e => setTandaForm({ ...tandaForm, nombre: e.target.value })} />
          <div className="grid grid-cols-2 gap-4">
            <Input label="Hora Inicio" type="time" value={tandaForm.hora_inicio} onChange={e => setTandaForm({ ...tandaForm, hora_inicio: e.target.value })} />
            <Input label="Hora Fin" type="time" value={tandaForm.hora_fin} onChange={e => setTandaForm({ ...tandaForm, hora_fin: e.target.value })} />
          </div>
        </div>
      </Modal>

      {/* Modal Asignatura */}
      <Modal isOpen={showModal && modalType === 'asignatura'} onClose={() => setShowModal(false)} title={editingItem ? 'Editar Asignatura' : 'Nueva Asignatura'} size="md"
        footer={<><Button variant="secondary" onClick={() => setShowModal(false)}>Cancelar</Button><Button onClick={saveAsignatura} loading={saving}>{editingItem ? 'Guardar' : 'Crear'}</Button></>}>
        <div className="space-y-4">
          <Input label="Nombre *" placeholder="Ej: Matemáticas" value={asignaturaForm.nombre} onChange={e => setAsignaturaForm({ ...asignaturaForm, nombre: e.target.value })} />
          <div className="grid grid-cols-2 gap-4">
            <Input label="Código" placeholder="Ej: MAT" value={asignaturaForm.codigo} onChange={e => setAsignaturaForm({ ...asignaturaForm, codigo: e.target.value })} />
            <Input label="Área" placeholder="Ej: Ciencias" value={asignaturaForm.area} onChange={e => setAsignaturaForm({ ...asignaturaForm, area: e.target.value })} />
          </div>
        </div>
      </Modal>

      {/* Modal Curso */}
      <Modal isOpen={showModal && modalType === 'curso'} onClose={() => setShowModal(false)} title={editingItem ? 'Editar Curso' : 'Nuevo Curso'} size="md"
        footer={<><Button variant="secondary" onClick={() => setShowModal(false)}>Cancelar</Button><Button onClick={saveCurso} loading={saving}>{editingItem ? 'Guardar' : 'Crear'}</Button></>}>
        <div className="space-y-4">
          <Select label="Grado *" value={cursoForm.grado_id} onChange={e => setCursoForm({ ...cursoForm, grado_id: parseInt(e.target.value) })} options={grados.map(g => ({ value: g.id, label: g.nombre }))} placeholder="Seleccionar grado" />
          <div className="grid grid-cols-2 gap-4">
            <Input label="Sección" placeholder="A, B, C..." value={cursoForm.seccion} onChange={e => setCursoForm({ ...cursoForm, seccion: e.target.value })} />
            <Input label="Capacidad" type="number" value={cursoForm.capacidad} onChange={e => setCursoForm({ ...cursoForm, capacidad: parseInt(e.target.value) || 35 })} />
          </div>
          <Select label="Tanda" value={cursoForm.tanda_id} onChange={e => setCursoForm({ ...cursoForm, tanda_id: parseInt(e.target.value) || 0 })} options={tandas.map(t => ({ value: t.id, label: t.nombre }))} placeholder="Sin tanda" />
        </div>
      </Modal>

      {/* Modal Feriado */}
      <Modal isOpen={showModal && modalType === 'feriado'} onClose={() => setShowModal(false)} title="Nuevo Día No Laborable" size="md"
        footer={<><Button variant="secondary" onClick={() => setShowModal(false)}>Cancelar</Button><Button onClick={saveFeriado} loading={saving}>Crear</Button></>}>
        <div className="space-y-4">
          <Input label="Fecha *" type="date" value={feriadoForm.fecha} onChange={e => setFeriadoForm({ ...feriadoForm, fecha: e.target.value })} />
          <Input label="Nombre *" placeholder="Ej: Día de la Independencia" value={feriadoForm.nombre} onChange={e => setFeriadoForm({ ...feriadoForm, nombre: e.target.value })} />
          <Select label="Tipo" value={feriadoForm.tipo} onChange={e => setFeriadoForm({ ...feriadoForm, tipo: e.target.value })} 
            options={[{ value: 'feriado', label: '🎉 Feriado' }, { value: 'vacaciones', label: '🏖️ Vacaciones' }, { value: 'suspension', label: '⚠️ Suspensión' }]} />
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" checked={feriadoForm.recurrente} onChange={e => setFeriadoForm({ ...feriadoForm, recurrente: e.target.checked })} className="w-4 h-4" />
            <span className="text-sm">Se repite cada año</span>
          </label>
        </div>
      </Modal>

      {/* Modal Año Escolar */}
      <Modal isOpen={showAnoModal} onClose={() => { setShowAnoModal(false); setEditingAno(false); }} title={editingAno ? "Editar Año Escolar" : "Crear Año Escolar"} size="md"
        footer={<><Button variant="secondary" onClick={() => { setShowAnoModal(false); setEditingAno(false); }}>Cancelar</Button><Button onClick={saveAnoEscolar} loading={saving}>{editingAno ? 'Guardar' : 'Crear'}</Button></>}>
        <div className="space-y-4">
          <Input label="Nombre *" placeholder="Ej: 2024-2025" value={anoForm.nombre} onChange={e => setAnoForm({ ...anoForm, nombre: e.target.value })} />
          <div className="grid grid-cols-2 gap-4">
            <Input label="Fecha Inicio" type="date" value={anoForm.fecha_inicio} onChange={e => setAnoForm({ ...anoForm, fecha_inicio: e.target.value })} />
            <Input label="Fecha Fin" type="date" value={anoForm.fecha_fin} onChange={e => setAnoForm({ ...anoForm, fecha_fin: e.target.value })} />
          </div>
          {!editingAno && (
            <p className="text-sm text-gray-500">
              Al crear un nuevo año escolar, el anterior se desactivará automáticamente.
            </p>
          )}
        </div>
      </Modal>
    </div>
  );
};

export default ConfiguracionPage;
