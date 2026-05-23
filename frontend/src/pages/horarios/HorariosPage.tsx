import { useState, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';
import { Printer, Plus, Trash2, Clock, Settings, Coffee, Sun, Moon, Edit2 } from 'lucide-react';
import { Modal, Button, Select, Input, Alert } from '../../components/ui';

interface Horario {
  id: number;
  dia: string;
  hora_inicio: string;
  hora_fin: string;
  asignatura: string | null;
  asignatura_id: number | null;
  curso: string | null;
  curso_id: number | null;
  profesor: string;
  aula?: string;
  tipo_bloque: 'clase' | 'libre' | 'recreo';
  tanda?: string;
}

interface Recreo {
  id: number;
  tanda_id: number;
  tanda: string;
  nombre: string;
  hora_inicio: string;
  hora_fin: string;
}

interface Tanda {
  id: number;
  nombre: string;
  hora_inicio: string;
  hora_fin: string;
}

const DIAS = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes'];
const TIPOS_BLOQUE = [
  { value: 'clase', label: '📚 Clase (con asignatura)' },
  { value: 'libre', label: '🕐 Hora Libre' },
  { value: 'recreo', label: '☕ Recreo' }
];

// Función para formatear hora de 24h a AM/PM
const formatHora = (hora: string): string => {
  if (!hora) return '';
  const [h, m] = hora.split(':').map(Number);
  const ampm = h >= 12 ? 'PM' : 'AM';
  const hora12 = h % 12 || 12;
  return `${hora12}:${m.toString().padStart(2, '0')} ${ampm}`;
};

// Generar bloques de horario para una tanda
const generarBloquesHorario = (tandaInicio: string, tandaFin: string, recreos: Recreo[], duracionBloque: number = 50) => {
  const bloques: { inicio: string; fin: string; recreo?: boolean; nombreRecreo?: string }[] = [];
  
  let [hInicio, mInicio] = tandaInicio.split(':').map(Number);
  const [hFin, mFin] = tandaFin.split(':').map(Number);
  const finMinutos = hFin * 60 + mFin;
  
  while (hInicio * 60 + mInicio < finMinutos) {
    const inicioStr = `${hInicio.toString().padStart(2, '0')}:${mInicio.toString().padStart(2, '0')}`;
    
    // Verificar si es hora de recreo
    const recreo = recreos.find(r => r.hora_inicio === inicioStr);
    
    if (recreo) {
      bloques.push({
        inicio: recreo.hora_inicio,
        fin: recreo.hora_fin,
        recreo: true,
        nombreRecreo: recreo.nombre
      });
      [hInicio, mInicio] = recreo.hora_fin.split(':').map(Number);
    } else {
      // Bloque normal de clase
      let nuevoMin = mInicio + duracionBloque;
      let nuevoH = hInicio;
      if (nuevoMin >= 60) {
        nuevoH += Math.floor(nuevoMin / 60);
        nuevoMin = nuevoMin % 60;
      }
      
      // No pasar el fin de la tanda
      if (nuevoH * 60 + nuevoMin > finMinutos) {
        nuevoH = hFin;
        nuevoMin = mFin;
      }
      
      const finStr = `${nuevoH.toString().padStart(2, '0')}:${nuevoMin.toString().padStart(2, '0')}`;
      bloques.push({ inicio: inicioStr, fin: finStr });
      
      hInicio = nuevoH;
      mInicio = nuevoMin;
    }
  }
  
  return bloques;
};

export const HorariosPage = () => {
  const { user } = useAuth();
  const [profesores, setProfesores] = useState<any[]>([]);
  const [cursos, setCursos] = useState<any[]>([]);
  const [asignaturas, setAsignaturas] = useState<any[]>([]);
  const [tandas, setTandas] = useState<Tanda[]>([]);
  const [recreos, setRecreos] = useState<Recreo[]>([]);
  const [profesorId, setProfesorId] = useState(0);
  const [cursoId, setCursoId] = useState(0);
  const [tandaId, setTandaId] = useState(0);
  const [vistaActual, setVistaActual] = useState<'profesor' | 'curso'>('profesor');
  const [horarios, setHorarios] = useState<Horario[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [showRecreoModal, setShowRecreoModal] = useState(false);
  const [editingHorario, setEditingHorario] = useState<Horario | null>(null);
  const [message, setMessage] = useState<{type: 'success' | 'error'; text: string} | null>(null);
  
  const [form, setForm] = useState({
    dia: 'Lunes',
    hora_inicio: '07:30',
    hora_fin: '08:20',
    curso_id: 0,
    asignatura_id: 0,
    aula: '',
    tipo_bloque: 'clase' as 'clase' | 'libre' | 'recreo'
  });

  const [recreoForm, setRecreoForm] = useState({
    id: 0,
    tanda_id: 0,
    nombre: 'Recreo',
    hora_inicio: '10:00',
    hora_fin: '10:30'
  });

  const canEdit = user?.role === 'direccion';

  useEffect(() => { loadInicial(); }, []);
  useEffect(() => { 
    if (vistaActual === 'profesor' && profesorId) loadHorariosProfesor();
    else if (vistaActual === 'curso' && cursoId) loadHorariosCurso();
  }, [profesorId, cursoId, vistaActual]);

  const loadInicial = async () => {
    try {
      const [p, c, a, t, r] = await Promise.all([
        api.get('/profesores'),
        api.get('/cursos'),
        api.get('/asignaturas'),
        api.get('/tandas'),
        api.get('/recreos')
      ]);
      setProfesores(p.data);
      setCursos(c.data);
      setAsignaturas(a.data);
      setTandas(t.data);
      setRecreos(r.data);
      
      if (t.data.length > 0) {
        setTandaId(t.data[0].id);
      }
      
      if (user?.role === 'profesor') {
        setProfesorId(user.id);
        setVistaActual('profesor');
      }
    } catch (e) {
      console.error('Error cargando datos:', e);
    } finally {
      setLoading(false);
    }
  };

  const loadHorariosProfesor = async () => {
    setLoading(true);
    try {
      const res = await api.get(`/horarios/profesor/${profesorId}`);
      setHorarios(res.data);
    } catch (e) {
      console.error('Error cargando horarios:', e);
    } finally {
      setLoading(false);
    }
  };

  const loadHorariosCurso = async () => {
    setLoading(true);
    try {
      const res = await api.get(`/horarios/curso/${cursoId}`);
      setHorarios(res.data);
    } catch (e) {
      console.error('Error cargando horarios:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    // Validaciones
    if (!form.hora_inicio || !form.hora_fin) {
      setMessage({ type: 'error', text: 'Las horas de inicio y fin son requeridas' });
      return;
    }
    if (form.hora_inicio >= form.hora_fin) {
      setMessage({ type: 'error', text: 'La hora de fin debe ser mayor que la hora de inicio' });
      return;
    }
    if (form.tipo_bloque === 'clase' && (!form.curso_id || !form.asignatura_id)) {
      setMessage({ type: 'error', text: 'Debe seleccionar curso y asignatura para una clase' });
      return;
    }
    
    try {
      const dataToSend = {
        profesor_id: profesorId,
        dia: form.dia,
        hora_inicio: form.hora_inicio,
        hora_fin: form.hora_fin,
        tipo_bloque: form.tipo_bloque,
        aula: form.aula,
        // Solo enviar curso/asignatura si es tipo 'clase'
        ...(form.tipo_bloque === 'clase' ? {
          curso_id: form.curso_id,
          asignatura_id: form.asignatura_id
        } : {})
      };
      
      if (editingHorario) {
        await api.put(`/horarios/${editingHorario.id}`, dataToSend);
        setMessage({ type: 'success', text: 'Horario actualizado' });
      } else {
        await api.post('/horarios', dataToSend);
        setMessage({ type: 'success', text: 'Horario creado' });
      }
      loadHorariosProfesor();
      setShowModal(false);
      setEditingHorario(null);
      setForm({ dia: 'Lunes', hora_inicio: '07:30', hora_fin: '08:20', curso_id: 0, asignatura_id: 0, aula: '', tipo_bloque: 'clase' });
    } catch (e: any) {
      setMessage({ type: 'error', text: e.response?.data?.error || 'Error al guardar' });
    }
  };

  const handleEditHorario = (horario: Horario) => {
    setEditingHorario(horario);
    setForm({
      dia: horario.dia,
      hora_inicio: horario.hora_inicio,
      hora_fin: horario.hora_fin,
      curso_id: horario.curso_id || 0,
      asignatura_id: horario.asignatura_id || 0,
      aula: horario.aula || '',
      tipo_bloque: horario.tipo_bloque || 'clase'
    });
    setShowModal(true);
  };

  const handleDelete = async (id: number) => {
    if (!confirm('¿Eliminar este bloque de horario?')) return;
    try {
      await api.delete(`/horarios/${id}`);
      if (vistaActual === 'profesor') loadHorariosProfesor();
      else loadHorariosCurso();
    } catch (e) {
      console.error('Error eliminando:', e);
    }
  };

  const handleSaveRecreo = async () => {
    try {
      if (recreoForm.id) {
        await api.put(`/recreos/${recreoForm.id}`, recreoForm);
      } else {
        await api.post('/recreos', recreoForm);
      }
      const r = await api.get('/recreos');
      setRecreos(r.data);
      setShowRecreoModal(false);
      setRecreoForm({ id: 0, tanda_id: 0, nombre: 'Recreo', hora_inicio: '10:00', hora_fin: '10:30' });
      setMessage({ type: 'success', text: 'Recreo guardado' });
    } catch (e) {
      setMessage({ type: 'error', text: 'Error al guardar recreo' });
    }
  };

  const handleDeleteRecreo = async (id: number) => {
    if (!confirm('¿Eliminar este recreo?')) return;
    try {
      await api.delete(`/recreos/${id}`);
      const r = await api.get('/recreos');
      setRecreos(r.data);
      setMessage({ type: 'success', text: 'Recreo eliminado' });
    } catch (e) {
      setMessage({ type: 'error', text: 'Error al eliminar recreo' });
    }
  };

  const openRecreoModal = (recreo?: Recreo) => {
    if (recreo) {
      setRecreoForm({
        id: recreo.id,
        tanda_id: recreo.tanda_id,
        nombre: recreo.nombre,
        hora_inicio: recreo.hora_inicio,
        hora_fin: recreo.hora_fin
      });
    } else {
      setRecreoForm({ id: 0, tanda_id: tandaId || (tandas[0]?.id || 0), nombre: 'Recreo', hora_inicio: '10:00', hora_fin: '10:30' });
    }
    setShowRecreoModal(true);
  };

  const getHorarioEnCelda = (dia: string, hora: { inicio: string; fin: string }) => {
    return horarios.find(h => 
      h.dia === dia && 
      h.hora_inicio === hora.inicio
    );
  };

  const getColorAsignatura = (asignatura: string) => {
    const colores: Record<string, string> = {
      'Matemática': 'bg-blue-50 border-blue-200 text-blue-700',
      'Lengua Española': 'bg-emerald-50 border-emerald-200 text-emerald-700',
      'Ciencias Sociales': 'bg-amber-50 border-amber-200 text-amber-700',
      'Ciencias de la Naturaleza': 'bg-purple-50 border-purple-200 text-purple-700',
      'Inglés': 'bg-pink-50 border-pink-200 text-pink-700',
      'Educación Física': 'bg-orange-50 border-orange-200 text-orange-700',
      'Formación Humana': 'bg-cyan-50 border-cyan-200 text-cyan-700',
    };
    return colores[asignatura] || 'bg-slate-50 border-slate-200 text-slate-700';
  };

  // Obtener tanda actual seleccionada
  const tandaActual = tandas.find(t => t.id === tandaId);
  const recreosTanda = recreos.filter(r => r.tanda_id === tandaId);
  
  // Generar bloques basados en los horarios REALES del profesor/curso
  // Si hay horarios, usar sus horas únicas; si no, usar tanda como fallback
  const generarBloquesDesdeHorarios = () => {
    if (horarios.length === 0 && tandaActual) {
      return generarBloquesHorario(tandaActual.hora_inicio, tandaActual.hora_fin, recreosTanda);
    }
    
    // Obtener todas las horas únicas de los horarios
    const horasUnicas = new Set<string>();
    horarios.forEach(h => {
      horasUnicas.add(h.hora_inicio);
    });
    
    // Agregar también los recreos si existen
    recreosTanda.forEach(r => {
      horasUnicas.add(r.hora_inicio);
    });
    
    // Convertir a array y ordenar
    const horasOrdenadas = Array.from(horasUnicas).sort((a, b) => {
      const [ha, ma] = a.split(':').map(Number);
      const [hb, mb] = b.split(':').map(Number);
      return (ha * 60 + ma) - (hb * 60 + mb);
    });
    
    // Crear bloques con las horas de los horarios
    return horasOrdenadas.map(inicio => {
      const horarioEjemplo = horarios.find(h => h.hora_inicio === inicio);
      const recreo = recreosTanda.find(r => r.hora_inicio === inicio);
      
      if (recreo) {
        return { inicio: recreo.hora_inicio, fin: recreo.hora_fin, recreo: true, nombreRecreo: recreo.nombre };
      }
      
      return { 
        inicio, 
        fin: horarioEjemplo?.hora_fin || inicio 
      };
    });
  };
  
  const HORAS = generarBloquesDesdeHorarios();

  const titulo = vistaActual === 'profesor' 
    ? profesores.find(p => p.id === profesorId)?.nombre_completo || 'Seleccionar profesor'
    : cursos.find(c => c.id === cursoId)?.nombre_completo || 'Seleccionar curso';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <Clock className="text-slate-400" size={24} />
          <h1 className="text-2xl font-bold text-slate-800">Horarios</h1>
        </div>
        <div className="flex items-center gap-3">
          {canEdit && (
            <Button onClick={() => openRecreoModal()} variant="secondary" icon={<Coffee size={16} />}>
              Gestionar Recreos
            </Button>
          )}
          {canEdit && profesorId > 0 && vistaActual === 'profesor' && (
            <Button onClick={() => setShowModal(true)} icon={<Plus size={16} />}>
              Agregar Bloque
            </Button>
          )}
          <button className="flex items-center px-4 py-2 text-sm font-medium text-slate-600 bg-white border border-slate-200 rounded-lg hover:bg-slate-50">
            <Printer size={16} className="mr-2" /> Imprimir
          </button>
        </div>
      </div>

      {message && (
        <Alert variant={message.type} onClose={() => setMessage(null)}>{message.text}</Alert>
      )}

      {/* Recreos configurados */}
      {canEdit && recreos.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
          <h4 className="font-medium text-amber-800 mb-2 flex items-center gap-2">
            <Coffee size={16} /> Recreos Configurados
          </h4>
          <div className="flex flex-wrap gap-2">
            {recreos.map(r => (
              <div key={r.id} className="flex items-center gap-2 px-3 py-1 bg-white rounded-full border border-amber-200 text-sm">
                <span className="text-amber-700">{r.tanda}: {r.nombre}</span>
                <span className="text-amber-600">{formatHora(r.hora_inicio)} - {formatHora(r.hora_fin)}</span>
                <button onClick={() => openRecreoModal(r)} className="text-blue-500 hover:text-blue-700">
                  <Settings size={14} />
                </button>
                <button onClick={() => handleDeleteRecreo(r.id)} className="text-red-500 hover:text-red-700">
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Filtros */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 flex flex-wrap items-center gap-4">
        <div className="flex bg-slate-100 rounded-lg p-1">
          <button
            onClick={() => setVistaActual('profesor')}
            className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${
              vistaActual === 'profesor' ? 'bg-white shadow-sm text-slate-800' : 'text-slate-500'
            }`}
          >
            Por Profesor
          </button>
          <button
            onClick={() => setVistaActual('curso')}
            className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${
              vistaActual === 'curso' ? 'bg-white shadow-sm text-slate-800' : 'text-slate-500'
            }`}
          >
            Por Curso
          </button>
        </div>

        <Select
          value={tandaId}
          onChange={e => setTandaId(parseInt(e.target.value))}
          options={tandas.map(t => ({ value: t.id, label: `${t.nombre === 'Matutina' ? '☀️' : '🌙'} ${t.nombre}` }))}
          placeholder="Seleccionar tanda"
        />

        {vistaActual === 'profesor' && user?.role !== 'profesor' && (
          <select
            value={profesorId}
            onChange={e => setProfesorId(parseInt(e.target.value))}
            className="px-4 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm"
          >
            <option value={0}>Seleccionar profesor</option>
            {profesores.map(p => (
              <option key={p.id} value={p.id}>{p.nombre_completo}</option>
            ))}
          </select>
        )}

        {vistaActual === 'curso' && (
          <select
            value={cursoId}
            onChange={e => setCursoId(parseInt(e.target.value))}
            className="px-4 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm"
          >
            <option value={0}>Seleccionar curso</option>
            {(() => {
              const filtrados = cursos.filter(c => !tandaId || c.tanda_id === tandaId);
              const tandas = [...new Set(filtrados.map(c => c.tanda || 'Sin tanda'))];
              return tandas.map(tanda => (
                <optgroup key={tanda} label={tanda}>
                  {filtrados.filter(c => (c.tanda || 'Sin tanda') === tanda).map(c => (
                    <option key={c.id} value={c.id}>{c.grado ? `${c.grado} ${c.nombre}` : c.nombre_completo}</option>
                  ))}
                </optgroup>
              ));
            })()}
          </select>
        )}
      </div>

      {/* Tabla de horario */}
      {((vistaActual === 'profesor' && profesorId > 0) || (vistaActual === 'curso' && cursoId > 0)) && HORAS.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="p-4 border-b border-slate-100 flex justify-between items-center">
            <h3 className="font-bold text-slate-800">
              Horario de {vistaActual === 'profesor' ? 'Clases' : ''} - {titulo}
            </h3>
            <span className="text-sm text-slate-500">{tandaActual?.nombre}</span>
          </div>
          
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse min-w-[800px]">
              <thead>
                <tr className="bg-slate-50">
                  <th className="p-4 text-xs font-bold text-slate-400 uppercase border-r border-slate-100 w-32">Hora</th>
                  {DIAS.map(dia => (
                    <th key={dia} className="p-4 text-xs font-bold text-slate-500 uppercase text-center">{dia}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {HORAS.map((hora, idx) => (
                  <tr key={idx} className={hora.recreo ? 'bg-amber-50' : 'hover:bg-slate-50/50'}>
                    <td className="p-3 text-xs text-slate-500 border-r border-slate-100">
                      <div className="font-medium">{formatHora(hora.inicio)}</div>
                      <div className="text-slate-400">{formatHora(hora.fin)}</div>
                    </td>
                    {DIAS.map(dia => {
                      if (hora.recreo) {
                        return (
                          <td key={`${dia}-${idx}`} className="p-3 text-center">
                            <div className="bg-amber-200 text-amber-700 text-xs font-bold py-2 px-3 rounded flex items-center justify-center gap-1">
                              <Coffee size={12} />
                              {hora.nombreRecreo || 'RECREO'}
                            </div>
                          </td>
                        );
                      }
                      
                      const horario = getHorarioEnCelda(dia, hora);
                      
                      return (
                        <td key={`${dia}-${idx}`} className="p-2">
                          {horario ? (
                            <div className={`p-2 rounded border relative group ${
                              horario.tipo_bloque === 'libre' 
                                ? 'bg-gray-100 border-gray-300 text-gray-600' 
                                : horario.tipo_bloque === 'recreo'
                                  ? 'bg-green-50 border-green-300 text-green-700'
                                  : getColorAsignatura(horario.asignatura || '')
                            }`}>
                              {horario.tipo_bloque === 'libre' ? (
                                <>
                                  <p className="text-[11px] font-bold">🕐 Libre</p>
                                  <p className="text-[9px] opacity-75">Hora libre</p>
                                </>
                              ) : horario.tipo_bloque === 'recreo' ? (
                                <>
                                  <p className="text-[11px] font-bold">☕ Recreo</p>
                                  <p className="text-[9px] opacity-75">Descanso</p>
                                </>
                              ) : (
                                <>
                                  <p className="text-[11px] font-bold">{horario.asignatura}</p>
                                  <p className="text-[9px] uppercase opacity-75">
                                    {vistaActual === 'profesor' ? horario.curso : horario.profesor}
                                  </p>
                                  {horario.aula && (
                                    <p className="text-[8px] opacity-60">Aula: {horario.aula}</p>
                                  )}
                                </>
                              )}
                              {canEdit && (
                                <div className="absolute top-1 right-1 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                  <button
                                    onClick={() => handleEditHorario(horario)}
                                    className="p-1 bg-blue-100 text-blue-600 rounded hover:bg-blue-200"
                                    title="Editar"
                                  >
                                    <Settings size={12} />
                                  </button>
                                  <button
                                    onClick={() => handleDelete(horario.id)}
                                    className="p-1 bg-red-100 text-red-600 rounded hover:bg-red-200"
                                    title="Eliminar"
                                  >
                                    <Trash2 size={12} />
                                  </button>
                                </div>
                              )}
                            </div>
                          ) : (
                            <div className="h-12"></div>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Mensaje inicial */}
      {((vistaActual === 'profesor' && profesorId === 0) || (vistaActual === 'curso' && cursoId === 0)) && !loading && (
        <div className="bg-white rounded-xl border border-slate-200 p-12 text-center">
          <Clock size={48} className="mx-auto text-slate-300 mb-4" />
          <h3 className="text-lg font-semibold text-slate-600">
            Seleccione un {vistaActual === 'profesor' ? 'profesor' : 'curso'} y una tanda
          </h3>
          <p className="text-sm text-slate-400 mt-2">Para ver el horario de clases</p>
        </div>
      )}

      {/* Modal agregar/editar horario */}
      <Modal
        isOpen={showModal}
        onClose={() => { setShowModal(false); setEditingHorario(null); setForm({ dia: 'Lunes', hora_inicio: '07:30', hora_fin: '08:20', curso_id: 0, asignatura_id: 0, aula: '', tipo_bloque: 'clase' }); }}
        title={editingHorario ? "Editar Bloque de Horario" : "Agregar Bloque de Horario"}
        size="md"
        footer={
          <>
            <Button variant="secondary" onClick={() => { setShowModal(false); setEditingHorario(null); }}>Cancelar</Button>
            <Button onClick={handleSave}>{editingHorario ? 'Actualizar' : 'Guardar'}</Button>
          </>
        }
      >
        <div className="space-y-4">
          {/* Tipo de Bloque */}
          <Select
            label="Tipo de Bloque"
            value={form.tipo_bloque}
            onChange={e => setForm({ ...form, tipo_bloque: e.target.value as 'clase' | 'libre' | 'recreo' })}
            options={TIPOS_BLOQUE}
          />
          
          <Select
            label="Día"
            value={form.dia}
            onChange={e => setForm({ ...form, dia: e.target.value })}
            options={DIAS.map(d => ({ value: d, label: d }))}
          />
          <div className="grid grid-cols-2 gap-4">
            <Input
              label="Hora Inicio"
              type="time"
              value={form.hora_inicio}
              onChange={e => setForm({ ...form, hora_inicio: e.target.value })}
            />
            <Input
              label="Hora Fin"
              type="time"
              value={form.hora_fin}
              onChange={e => setForm({ ...form, hora_fin: e.target.value })}
            />
          </div>
          
          {/* Solo mostrar curso/asignatura si es tipo 'clase' */}
          {form.tipo_bloque === 'clase' && (
            <>
              <Select
                label="Curso"
                value={form.curso_id}
                onChange={e => setForm({ ...form, curso_id: parseInt(e.target.value) })}
                options={[
                  { value: 0, label: '-- Seleccionar curso --' },
                  ...cursos.map(c => ({ value: c.id, label: c.grado ? `${c.grado} ${c.nombre}` : c.nombre_completo, group: c.tanda || 'Sin tanda' }))
                ]}
              />
              <Select
                label="Asignatura"
                value={form.asignatura_id}
                onChange={e => setForm({ ...form, asignatura_id: parseInt(e.target.value) })}
                options={[
                  { value: 0, label: '-- Seleccionar asignatura --' },
                  ...asignaturas.map(a => ({ value: a.id, label: a.nombre }))
                ]}
              />
              <Input
                label="Aula (opcional)"
                value={form.aula}
                onChange={e => setForm({ ...form, aula: e.target.value })}
                placeholder="Ej: A-101"
              />
            </>
          )}
          
          {form.tipo_bloque !== 'clase' && (
            <div className="p-3 bg-gray-50 rounded-lg text-sm text-gray-600">
              {form.tipo_bloque === 'libre' && '🕐 Hora libre del profesor - no requiere curso ni asignatura'}
              {form.tipo_bloque === 'recreo' && '☕ Recreo - no requiere curso ni asignatura'}
            </div>
          )}
        </div>
      </Modal>

      {/* Modal recreo */}
      <Modal
        isOpen={showRecreoModal}
        onClose={() => setShowRecreoModal(false)}
        title={recreoForm.id ? 'Editar Recreo' : 'Nuevo Recreo'}
        size="md"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowRecreoModal(false)}>Cancelar</Button>
            <Button onClick={handleSaveRecreo}>Guardar</Button>
          </>
        }
      >
        <div className="space-y-4">
          <Select
            label="Tanda"
            value={recreoForm.tanda_id}
            onChange={e => setRecreoForm({ ...recreoForm, tanda_id: parseInt(e.target.value) })}
            options={tandas.map(t => ({ value: t.id, label: t.nombre }))}
            placeholder="Seleccionar tanda"
          />
          <Input
            label="Nombre"
            value={recreoForm.nombre}
            onChange={e => setRecreoForm({ ...recreoForm, nombre: e.target.value })}
            placeholder="Ej: Recreo, Merienda"
          />
          <div className="grid grid-cols-2 gap-4">
            <Input
              label="Hora Inicio"
              type="time"
              value={recreoForm.hora_inicio}
              onChange={e => setRecreoForm({ ...recreoForm, hora_inicio: e.target.value })}
            />
            <Input
              label="Hora Fin"
              type="time"
              value={recreoForm.hora_fin}
              onChange={e => setRecreoForm({ ...recreoForm, hora_fin: e.target.value })}
            />
          </div>
        </div>
      </Modal>

      {loading && (
        <div className="flex justify-center py-12">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
        </div>
      )}
    </div>
  );
};

export default HorariosPage;
