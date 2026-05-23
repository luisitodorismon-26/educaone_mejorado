import { useState, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';
import { BookOpen, Filter, Save, AlertCircle, CheckCircle, ChevronDown, ChevronUp } from 'lucide-react';
import { Modal, Button, Select, Alert, Spinner } from '../../components/ui';
import { AcademicoPrimariaPage } from './AcademicoPrimariaPage';
import { AcademicoSecundariaPage } from './AcademicoSecundariaPage';
import { NivelTabs } from '../../components/NivelTabs';
import { useNivelesActivos, Nivel } from '../../hooks/useNivelesActivos';

interface Curso {
  id: number;
  nombre_completo: string;
  grado?: string;
  nivel?: string;
  ciclo?: string;
  tanda?: string;
  tanda_id?: number;
  nombre?: string;
}

interface Asignatura {
  id: number;
  nombre: string;
}

interface Calificacion {
  id?: number;
  estudiante_id: number;
  estudiante: string;
  no_lista: number | null;
  asignatura_id: number;
  // Período 1
  p1_p1: number | null;
  p1_p2: number | null;
  p1_p3: number | null;
  p1_p4: number | null;
  rp1_p1: number | null;
  rp1_p2: number | null;
  rp1_p3: number | null;
  rp1_p4: number | null;
  pc1: number | null;
  rp1: number | null;
  // Período 2
  p2_p1: number | null;
  p2_p2: number | null;
  p2_p3: number | null;
  p2_p4: number | null;
  rp2_p1: number | null;
  rp2_p2: number | null;
  rp2_p3: number | null;
  rp2_p4: number | null;
  pc2: number | null;
  rp2: number | null;
  // Período 3
  p3_p1: number | null;
  p3_p2: number | null;
  p3_p3: number | null;
  p3_p4: number | null;
  rp3_p1: number | null;
  rp3_p2: number | null;
  rp3_p3: number | null;
  rp3_p4: number | null;
  pc3: number | null;
  rp3: number | null;
  // Período 4
  p4_p1: number | null;
  p4_p2: number | null;
  p4_p3: number | null;
  p4_p4: number | null;
  rp4_p1: number | null;
  rp4_p2: number | null;
  rp4_p3: number | null;
  rp4_p4: number | null;
  pc4: number | null;
  rp4: number | null;
  // Final
  cf: number | null;
  literal: string | null;
  // Flags de retiro (vienen del backend)
  retirado?: boolean;
  fecha_retiro?: string | null;
  motivo_retiro?: string | null;
}

interface PeriodoInfo {
  activo: number;
  p1_cerrado: boolean;
  p2_cerrado: boolean;
  p3_cerrado: boolean;
  p4_cerrado: boolean;
}

export const AcademicoPage = () => {
  const { user } = useAuth();
  const [cursos, setCursos] = useState<Curso[]>([]);
  const [asignaturas, setAsignaturas] = useState<Asignatura[]>([]);
  const [cursoId, setCursoId] = useState<number | null>(null);
  const [asignaturaId, setAsignaturaId] = useState<number | null>(null);
  const [calificaciones, setCalificaciones] = useState<Calificacion[]>([]);
  const [editadas, setEditadas] = useState<Record<number, Partial<Calificacion>>>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [mensaje, setMensaje] = useState<{ tipo: 'success' | 'error'; texto: string } | null>(null);
  const [periodoInfo, setPeriodoInfo] = useState<PeriodoInfo | null>(null);
  const [periodosExpandidos, setPeriodosExpandidos] = useState<Record<number, boolean>>({ 1: true, 2: true, 3: true, 4: true });
  const niveles = useNivelesActivos();
  const [nivelFiltro, setNivelFiltro] = useState<Nivel | 'todos'>('todos');
  
  // Nombres de competencias por período
  const NOMBRES_PERIODOS: Record<number, string> = {
    1: 'Comunicativa',
    2: 'Pensamiento Lógico, Creativo y Crítico',
    3: 'Científica y Tecnológica',
    4: 'Desarrollo Personal'
  };

  const esProfesor = user?.role === 'profesor';
  const esDireccion = user?.role === 'direccion';
  const esCoordinador = user?.role === 'coordinador';

  useEffect(() => {
    cargarDatos();
  }, []);

  useEffect(() => {
    if (cursoId && asignaturaId) {
      cargarCalificaciones();
    }
  }, [cursoId, asignaturaId]);

  const cargarDatos = async () => {
    try {
      // Siempre cargar cursos completos para tener grado y tanda
      const cursosRes = await api.get('/cursos');
      
      if (esProfesor) {
        const res = await api.get('/dashboard/profesor');
        // Filtrar cursos completos por los asignados al profesor
        const cursosAsignadosIds = new Set(res.data.cursos_asignados.map((c: any) => c.curso_id));
        const cursosProfesor = cursosRes.data.filter((c: any) => cursosAsignadosIds.has(c.id));
        setCursos(cursosProfesor);
        
        const asignaturasUnicas = res.data.cursos_asignados.reduce((acc: Asignatura[], curr: any) => {
          if (!acc.find(a => a.id === curr.asignatura_id)) {
            acc.push({ id: curr.asignatura_id, nombre: curr.asignatura });
          }
          return acc;
        }, []);
        setAsignaturas(asignaturasUnicas);
      } else {
        setCursos(cursosRes.data);
        const asignaturasRes = await api.get('/asignaturas');
        setAsignaturas(asignaturasRes.data);
      }

      // Cargar info de períodos
      const anoRes = await api.get('/ano-escolar');
      if (anoRes.data) {
        setPeriodoInfo({
          activo: anoRes.data.periodo_activo || 1,
          p1_cerrado: anoRes.data.p1_cerrado || false,
          p2_cerrado: anoRes.data.p2_cerrado || false,
          p3_cerrado: anoRes.data.p3_cerrado || false,
          p4_cerrado: anoRes.data.p4_cerrado || false,
        });
      }
    } catch (error) {
      console.error('Error cargando datos:', error);
    }
  };

  const cargarCalificaciones = async () => {
    if (!cursoId || !asignaturaId) return;
    setLoading(true);
    try {
      const res = await api.get(`/calificaciones/curso/${cursoId}/asignatura/${asignaturaId}`);
      
      // Procesar la respuesta del backend
      const { calificaciones: califs, periodo_info } = res.data;
      
      // Convertir la estructura del backend a la esperada por el frontend
      const calificacionesProcesadas: Calificacion[] = califs.map((item: any) => {
        const cal = item.calificacion || {};
        return {
          estudiante_id: item.estudiante.id,
          estudiante: item.estudiante.nombre_completo,
          no_lista: item.estudiante.no_lista,
          asignatura_id: asignaturaId,
          // Período 1
          p1_p1: cal.p1_p1 ?? null,
          p1_p2: cal.p1_p2 ?? null,
          p1_p3: cal.p1_p3 ?? null,
          p1_p4: cal.p1_p4 ?? null,
          rp1_p1: cal.rp1_p1 ?? null,
          rp1_p2: cal.rp1_p2 ?? null,
          rp1_p3: cal.rp1_p3 ?? null,
          rp1_p4: cal.rp1_p4 ?? null,
          pc1: cal.pc1 ?? null,
          rp1: cal.rp1 ?? null,
          // Período 2
          p2_p1: cal.p2_p1 ?? null,
          p2_p2: cal.p2_p2 ?? null,
          p2_p3: cal.p2_p3 ?? null,
          p2_p4: cal.p2_p4 ?? null,
          rp2_p1: cal.rp2_p1 ?? null,
          rp2_p2: cal.rp2_p2 ?? null,
          rp2_p3: cal.rp2_p3 ?? null,
          rp2_p4: cal.rp2_p4 ?? null,
          pc2: cal.pc2 ?? null,
          rp2: cal.rp2 ?? null,
          // Período 3
          p3_p1: cal.p3_p1 ?? null,
          p3_p2: cal.p3_p2 ?? null,
          p3_p3: cal.p3_p3 ?? null,
          p3_p4: cal.p3_p4 ?? null,
          rp3_p1: cal.rp3_p1 ?? null,
          rp3_p2: cal.rp3_p2 ?? null,
          rp3_p3: cal.rp3_p3 ?? null,
          rp3_p4: cal.rp3_p4 ?? null,
          pc3: cal.pc3 ?? null,
          rp3: cal.rp3 ?? null,
          // Período 4
          p4_p1: cal.p4_p1 ?? null,
          p4_p2: cal.p4_p2 ?? null,
          p4_p3: cal.p4_p3 ?? null,
          p4_p4: cal.p4_p4 ?? null,
          rp4_p1: cal.rp4_p1 ?? null,
          rp4_p2: cal.rp4_p2 ?? null,
          rp4_p3: cal.rp4_p3 ?? null,
          rp4_p4: cal.rp4_p4 ?? null,
          pc4: cal.pc4 ?? null,
          rp4: cal.rp4 ?? null,
          // Final
          cf: cal.cf ?? null,
          literal: cal.literal ?? null,
          // Flags retiro
          retirado: !!item.estudiante.retirado,
          fecha_retiro: item.estudiante.fecha_retiro || null,
          motivo_retiro: item.estudiante.motivo_retiro || null,
        };
      });
      
      setCalificaciones(calificacionesProcesadas);
      
      // Actualizar info de períodos
      if (periodo_info) {
        setPeriodoInfo({
          activo: periodo_info.periodo_activo || 1,
          p1_cerrado: periodo_info.p1_cerrado || false,
          p2_cerrado: periodo_info.p2_cerrado || false,
          p3_cerrado: periodo_info.p3_cerrado || false,
          p4_cerrado: periodo_info.p4_cerrado || false,
        });
      }
      
      setEditadas({});
    } catch (error) {
      console.error('Error cargando calificaciones:', error);
      setMensaje({ tipo: 'error', texto: 'Error al cargar calificaciones' });
    } finally {
      setLoading(false);
    }
  };

  const handleNotaChange = (estudianteId: number, campo: string, valor: string) => {
    const numValue = valor === '' ? null : parseFloat(valor);
    
    // Validar rango 0-100
    if (numValue !== null && (numValue < 0 || numValue > 100)) return;

    setEditadas(prev => ({
      ...prev,
      [estudianteId]: {
        ...prev[estudianteId],
        [campo]: numValue
      }
    }));
  };

  const calcularPC = (cal: Calificacion, periodo: number, editada?: Partial<Calificacion>): number | null => {
    const datos = { ...cal, ...editada };
    // Lógica MINERD: por cada parcial, si hay RP se usa max(P, RP). RP nunca baja la nota.
    const valores: number[] = [];
    for (let i = 1; i <= 4; i++) {
      const p = datos[`p${periodo}_p${i}` as keyof Calificacion] as number | null;
      const rp = datos[`rp${periodo}_p${i}` as keyof Calificacion] as number | null;
      let val: number | null = null;
      if (rp !== null && rp !== undefined && p !== null && p !== undefined) {
        val = Math.max(p, rp);
      } else if (rp !== null && rp !== undefined) {
        val = rp;
      } else if (p !== null && p !== undefined) {
        val = p;
      }
      if (val === null) return null;
      valores.push(val);
    }
    if (valores.length === 4) {
      return Math.round((valores.reduce((a, b) => a + b, 0) / 4) * 100) / 100;
    }
    return null;
  };

  const calcularCF = (cal: Calificacion, editada?: Partial<Calificacion>): number | null => {
    const datos = { ...cal, ...editada };
    const notas: number[] = [];

    for (let p = 1; p <= 4; p++) {
      // PC ya incluye la recuperación por parcial
      const pc = datos[`pc${p}` as keyof Calificacion] as number | null ?? calcularPC(cal, p, editada);
      if (pc !== null && pc !== undefined) {
        notas.push(pc as number);
      }
    }

    if (notas.length === 4) {
      return Math.round((notas.reduce((a, b) => a + b, 0) / 4) * 100) / 100;
    }
    return null;
  };

  const getLiteral = (nota: number | null): string => {
    if (nota === null) return '-';
    if (nota >= 90) return 'A';
    if (nota >= 80) return 'B';
    if (nota >= 70) return 'C';
    return 'F';
  };

  const getNotaClass = (nota: number | null): string => {
    if (nota === null) return '';
    if (nota >= 90) return 'bg-emerald-100 text-emerald-800';
    if (nota >= 80) return 'bg-blue-100 text-blue-800';
    if (nota >= 70) return 'bg-amber-100 text-amber-800';
    return 'bg-red-100 text-red-800';
  };

  const puedeEditar = (periodo: number): boolean => {
    // SOLO profesores pueden registrar calificaciones
    // Dirección y coordinador solo pueden VER
    if (!periodoInfo) return false;
    if (esProfesor) {
      // Profesor solo puede editar período activo y no cerrado
      return periodoInfo.activo === periodo && !periodoInfo[`p${periodo}_cerrado` as keyof PeriodoInfo];
    }
    // Dirección, Coordinador y otros NO pueden editar
    return false;
  };

  const guardarCalificaciones = async () => {
    if (Object.keys(editadas).length === 0) {
      setMensaje({ tipo: 'error', texto: 'No hay cambios para guardar' });
      return;
    }

    setSaving(true);
    try {
      // Determinar qué período está activo para enviarlo
      const periodoActivo = periodoInfo?.activo || 1;
      
      for (const [estudianteId, cambios] of Object.entries(editadas)) {
        const calExistente = calificaciones.find(c => c.estudiante_id === parseInt(estudianteId));
        
        // Calcular PCs y CF
        const datosCompletos: any = {
          estudiante_id: parseInt(estudianteId),
          asignatura_id: asignaturaId,
          periodo: periodoActivo,  // ENVIAR EL PERÍODO
          ...(cambios as Record<string, any>)
        };

        // Calcular PC para cada período si tiene los 4 parciales
        for (let p = 1; p <= 4; p++) {
          const pc = calcularPC(calExistente || {} as Calificacion, p, cambios as Partial<Calificacion>);
          if (pc !== null) {
            datosCompletos[`pc${p}`] = pc;
          }
        }

        // Calcular CF
        const cf = calcularCF(calExistente || {} as Calificacion, datosCompletos);
        if (cf !== null) {
          datosCompletos.cf = cf;
          datosCompletos.literal = getLiteral(cf);
        }

        await api.post('/calificaciones', datosCompletos);
      }

      setMensaje({ tipo: 'success', texto: 'Calificaciones guardadas correctamente' });
      setEditadas({});
      cargarCalificaciones();
    } catch (error) {
      console.error('Error guardando:', error);
      setMensaje({ tipo: 'error', texto: 'Error al guardar calificaciones' });
    } finally {
      setSaving(false);
    }
  };

  const togglePeriodo = (periodo: number) => {
    setPeriodosExpandidos(prev => ({ ...prev, [periodo]: !prev[periodo] }));
  };

  const getValor = (cal: Calificacion, campo: string): number | null => {
    const editada = editadas[cal.estudiante_id];
    if (editada && campo in editada) {
      return editada[campo as keyof Calificacion] as number | null;
    }
    return cal[campo as keyof Calificacion] as number | null;
  };

  const renderInputNota = (cal: Calificacion, campo: string, periodo: number) => {
    const valor = getValor(cal, campo);
    const esRetirado = !!cal.retirado;
    // Si está retirado: NO editable. Las notas previas se muestran en gris.
    const editable = !esRetirado && puedeEditar(periodo);
    const estaEditado = editadas[cal.estudiante_id] && campo in editadas[cal.estudiante_id];

    if (esRetirado) {
      // Display readonly con notas previas en gris
      return (
        <span className={`inline-block w-14 text-center text-sm py-0.5 ${valor !== null ? 'text-gray-500' : 'text-gray-300'}`}>
          {valor !== null ? valor : '—'}
        </span>
      );
    }

    return (
      <input
        type="number"
        min="0"
        max="100"
        step="0.01"
        value={valor ?? ''}
        onChange={(e) => handleNotaChange(cal.estudiante_id, campo, e.target.value)}
        disabled={!editable}
        className={`w-14 px-1 py-0.5 text-center text-sm border rounded
          ${!editable ? 'bg-gray-100 cursor-not-allowed' : 'bg-white'}
          ${estaEditado ? 'border-blue-500 bg-blue-50' : 'border-gray-300'}
          focus:outline-none focus:ring-1 focus:ring-blue-500`}
      />
    );
  };

  const renderPeriodo = (periodo: number) => {
    const expandido = periodosExpandidos[periodo];
    const cerrado = periodoInfo?.[`p${periodo}_cerrado` as keyof PeriodoInfo];
    const esActivo = periodoInfo?.activo === periodo;

    return (
      <div key={periodo} className="mb-4">
        <button
          onClick={() => togglePeriodo(periodo)}
          className={`w-full flex items-center justify-between px-4 py-2 rounded-lg font-medium
            ${esActivo ? 'bg-blue-600 text-white' : cerrado ? 'bg-gray-200 text-gray-600' : 'bg-gray-100 text-gray-800'}
          `}
        >
          <span className="flex items-center gap-2">
            <span className="font-bold">P{periodo}</span>
            <span className="text-xs opacity-80">- {NOMBRES_PERIODOS[periodo]}</span>
            {cerrado && <span className="text-xs bg-red-500 text-white px-2 py-0.5 rounded">CERRADO</span>}
            {esActivo && !cerrado && <span className="text-xs bg-green-500 text-white px-2 py-0.5 rounded">ACTIVO</span>}
          </span>
          {expandido ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
        </button>

        {expandido && (
          <div className="mt-2 overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="bg-gray-50">
                  <th className="px-2 py-2 text-left font-medium text-gray-600 sticky left-0 bg-gray-50">No.</th>
                  <th className="px-2 py-2 text-left font-medium text-gray-600 sticky left-8 bg-gray-50 min-w-[150px]">Estudiante</th>
                  <th className="px-1 py-2 text-center font-medium text-gray-600">P1</th>
                  <th className="px-1 py-2 text-center font-medium text-amber-600 bg-amber-50">RP1</th>
                  <th className="px-1 py-2 text-center font-medium text-gray-600">P2</th>
                  <th className="px-1 py-2 text-center font-medium text-amber-600 bg-amber-50">RP2</th>
                  <th className="px-1 py-2 text-center font-medium text-gray-600">P3</th>
                  <th className="px-1 py-2 text-center font-medium text-amber-600 bg-amber-50">RP3</th>
                  <th className="px-1 py-2 text-center font-medium text-gray-600">P4</th>
                  <th className="px-1 py-2 text-center font-medium text-amber-600 bg-amber-50">RP4</th>
                  <th className="px-2 py-2 text-center font-medium text-blue-600 bg-blue-50">PC</th>
                </tr>
              </thead>
              <tbody>
                {calificaciones.map((cal, idx) => {
                  const pcCalculado = calcularPC(cal, periodo, editadas[cal.estudiante_id]);
                  const pcActual = getValor(cal, `pc${periodo}`) ?? pcCalculado;

                  return (
                    <tr key={cal.estudiante_id} className={`border-b ${cal.retirado ? 'bg-gray-50' : 'hover:bg-gray-50'}`}>
                      <td className={`px-2 py-1 sticky left-0 bg-white ${cal.retirado ? 'text-gray-400 line-through' : 'text-gray-500'}`}>
                        {cal.no_lista || idx + 1}
                      </td>
                      <td className={`px-2 py-1 sticky left-8 bg-white ${cal.retirado ? 'bg-gray-50' : ''}`}>
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className={`font-medium ${cal.retirado ? 'text-gray-400 line-through' : ''}`}>{cal.estudiante}</span>
                          {cal.retirado && (
                            <span
                              title={cal.motivo_retiro || 'Estudiante retirado'}
                              className="inline-block px-2 py-0.5 bg-gray-700 text-white text-[10px] font-medium rounded uppercase tracking-wide"
                            >
                              RETIRADO {cal.fecha_retiro ? cal.fecha_retiro.slice(5).replace('-','/') : ''}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-1 py-1 text-center">{renderInputNota(cal, `p${periodo}_p1`, periodo)}</td>
                      <td className="px-1 py-1 text-center bg-amber-50">{renderInputNota(cal, `rp${periodo}_p1`, periodo)}</td>
                      <td className="px-1 py-1 text-center">{renderInputNota(cal, `p${periodo}_p2`, periodo)}</td>
                      <td className="px-1 py-1 text-center bg-amber-50">{renderInputNota(cal, `rp${periodo}_p2`, periodo)}</td>
                      <td className="px-1 py-1 text-center">{renderInputNota(cal, `p${periodo}_p3`, periodo)}</td>
                      <td className="px-1 py-1 text-center bg-amber-50">{renderInputNota(cal, `rp${periodo}_p3`, periodo)}</td>
                      <td className="px-1 py-1 text-center">{renderInputNota(cal, `p${periodo}_p4`, periodo)}</td>
                      <td className="px-1 py-1 text-center bg-amber-50">{renderInputNota(cal, `rp${periodo}_p4`, periodo)}</td>
                      <td className={`px-2 py-1 text-center font-bold ${cal.retirado ? 'text-gray-400' : getNotaClass(pcActual)}`}>
                        {pcActual?.toFixed(2) ?? '-'}{cal.retirado && pcActual !== null ? <sup className="text-[8px] ml-0.5">parc</sup> : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="space-y-6">
      {(() => {
        // Detectar si el curso seleccionado es de primaria
        const cursoActual = cursos.find(c => c.id === cursoId);
        const esPrimaria = cursoActual?.nivel === 'primaria';
        const asigActual = asignaturas.find(a => a.id === asignaturaId);
        
        if (esPrimaria && cursoId && asignaturaId) {
          return (
            <AcademicoPrimariaPage
              cursoId={cursoId}
              asignaturaId={asignaturaId}
              curso={cursoActual || null}
              asignatura={asigActual || null}
              onVolver={() => { setCursoId(null); setAsignaturaId(null); }}
            />
          );
        }
        return null;
      })()}
      {(() => {
        // Detectar si el curso seleccionado es de secundaria (modelo nuevo v2.12)
        // Si el curso es secundaria explícito → usamos pantalla nueva con
        // CalificacionSecundaria + EvaluacionExtra (cascada MINERD oficial).
        // Si el nivel no está seteado, cae a la vista legacy (modelo `Calificacion`)
        // para no romper datos viejos del año anterior.
        const cursoActual = cursos.find(c => c.id === cursoId);
        const esSecundaria = cursoActual?.nivel === 'secundaria';
        const asigActual = asignaturas.find(a => a.id === asignaturaId);
        
        if (esSecundaria && cursoId && asignaturaId) {
          return (
            <AcademicoSecundariaPage
              cursoId={cursoId}
              asignaturaId={asignaturaId}
              curso={cursoActual || null}
              asignatura={asigActual || null}
              onVolver={() => { setCursoId(null); setAsignaturaId(null); }}
            />
          );
        }
        return null;
      })()}
      {(() => {
        const cursoActual = cursos.find(c => c.id === cursoId);
        const esPrimaria = cursoActual?.nivel === 'primaria';
        const esSecundaria = cursoActual?.nivel === 'secundaria';
        // Si ya enrutamos a primaria o secundaria nueva, ocultar el legacy view
        if ((esPrimaria || esSecundaria) && cursoId && asignaturaId) return null;
        return (
          <>
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <BookOpen className="text-blue-600" />
            Calificaciones
          </h1>
          <p className="text-gray-500 mt-1">Registro de calificaciones por período</p>
        </div>
        
        <div className="flex gap-2">
          {/* Botón Imprimir — disponible si hay curso y asignatura seleccionados */}
          {cursoId && asignaturaId && (
            <Button
              variant="secondary"
              onClick={() => {
                const periodo = periodoInfo?.activo || 1;
                const token = localStorage.getItem('token');
                const url = `${(import.meta as any).env.VITE_API_URL || ''}/api/imprimir/calificaciones/${cursoId}/${asignaturaId}?periodo=${periodo}`;
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
              Imprimir período
            </Button>
          )}
          {Object.keys(editadas).length > 0 && (
            <Button
              onClick={guardarCalificaciones}
              loading={saving}
              icon={<Save size={18} />}
              variant="success"
            >
              Guardar Cambios ({Object.keys(editadas).length})
            </Button>
          )}
        </div>
      </div>

      {/* Mensaje */}
      {mensaje && (
        <Alert
          variant={mensaje.tipo}
          onClose={() => setMensaje(null)}
        >
          {mensaje.texto}
        </Alert>
      )}

      {/* Tabs por nivel educativo */}
      <NivelTabs value={nivelFiltro} onChange={(n) => { setNivelFiltro(n); setCursoId(null); setAsignaturaId(null); }} showAll />

      {/* Filtros */}
      <div className="bg-white rounded-xl shadow-sm border p-4">
        <div className="flex items-center gap-2 mb-4">
          <Filter size={18} className="text-gray-400" />
          <span className="font-medium text-gray-700">Filtros</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Select
            label="Curso"
            value={cursoId?.toString() || ''}
            onChange={(e) => setCursoId(e.target.value ? parseInt(e.target.value) : null)}
            options={(nivelFiltro === 'todos' ? cursos : cursos.filter(c => (c.nivel || 'secundaria') === nivelFiltro)).map(c => ({ value: c.id, label: c.grado ? `${c.grado} ${c.nombre}` : c.nombre_completo, group: c.tanda || 'Sin tanda' }))}
            placeholder="Seleccione un curso"
          />
          <Select
            label="Asignatura"
            value={asignaturaId?.toString() || ''}
            onChange={(e) => setAsignaturaId(e.target.value ? parseInt(e.target.value) : null)}
            options={asignaturas.map(a => ({ value: a.id, label: a.nombre }))}
            placeholder="Seleccione una asignatura"
          />
        </div>
      </div>

      {/* Contenido */}
      {loading ? (
        <div className="flex justify-center py-12">
          <Spinner size="lg" />
        </div>
      ) : cursoId && asignaturaId ? (
        calificaciones.length > 0 ? (
          <div className="bg-white rounded-xl shadow-sm border p-4">
            {/* Info del período */}
            {periodoInfo && (
              <div className="mb-4 p-3 bg-blue-50 rounded-lg flex items-center gap-2">
                <AlertCircle size={18} className="text-blue-600" />
                <span className="text-sm text-blue-800">
                  Período activo: <strong>P{periodoInfo.activo}</strong>
                  {esProfesor && ' - Solo puede editar el período activo'}
                  {(esDireccion || user?.role === 'coordinador') && ' - Solo visualización'}
                </span>
              </div>
            )}

            {/* Períodos */}
            {[1, 2, 3, 4].map(p => renderPeriodo(p))}

            {/* Resumen Final */}
            <div className="mt-6 pt-4 border-t">
              <h3 className="font-bold text-lg mb-4 flex items-center gap-2">
                <CheckCircle className="text-green-600" />
                Calificación Final
              </h3>
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="bg-gray-50">
                      <th className="px-3 py-2 text-left">No.</th>
                      <th className="px-3 py-2 text-left">Estudiante</th>
                      <th className="px-3 py-2 text-center">PC1/RP1</th>
                      <th className="px-3 py-2 text-center">PC2/RP2</th>
                      <th className="px-3 py-2 text-center">PC3/RP3</th>
                      <th className="px-3 py-2 text-center">PC4/RP4</th>
                      <th className="px-3 py-2 text-center bg-blue-100 font-bold">CF</th>
                      <th className="px-3 py-2 text-center bg-blue-100 font-bold">Lit.</th>
                      <th className="px-3 py-2 text-center">Estado</th>
                    </tr>
                  </thead>
                  <tbody>
                    {calificaciones.map((cal, idx) => {
                      const cfCalculado = calcularCF(cal, editadas[cal.estudiante_id]);
                      const cfActual = cfCalculado ?? cal.cf;
                      const literal = getLiteral(cfActual);
                      const aprobado = cfActual !== null && cfActual >= 70;

                      const getNotaFinal = (periodo: number) => {
                        // PC ya tiene la lógica de RP por parcial aplicada
                        const pc = getValor(cal, `pc${periodo}`) ?? calcularPC(cal, periodo, editadas[cal.estudiante_id]);
                        // Marca como "recuperado" si algún RP del período está en uso
                        const editada = editadas[cal.estudiante_id];
                        const datos = { ...cal, ...editada };
                        let tieneRP = false;
                        for (let i = 1; i <= 4; i++) {
                          const rp = datos[`rp${periodo}_p${i}` as keyof Calificacion];
                          if (rp !== null && rp !== undefined) { tieneRP = true; break; }
                        }
                        return { nota: pc, esRP: tieneRP };
                      };

                      return (
                        <tr key={cal.estudiante_id} className={`border-b ${cal.retirado ? 'bg-gray-50' : ''}`}>
                          <td className={`px-3 py-2 ${cal.retirado ? 'text-gray-400 line-through' : ''}`}>
                            {cal.no_lista || idx + 1}
                          </td>
                          <td className="px-3 py-2">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className={`font-medium ${cal.retirado ? 'text-gray-400 line-through' : ''}`}>{cal.estudiante}</span>
                              {cal.retirado && (
                                <span
                                  title={cal.motivo_retiro || 'Estudiante retirado'}
                                  className="inline-block px-2 py-0.5 bg-gray-700 text-white text-[10px] font-medium rounded uppercase tracking-wide"
                                >
                                  RETIRADO {cal.fecha_retiro ? cal.fecha_retiro.slice(5).replace('-','/') : ''}
                                </span>
                              )}
                            </div>
                          </td>
                          {[1, 2, 3, 4].map(p => {
                            const { nota, esRP } = getNotaFinal(p);
                            return (
                              <td key={p} className={`px-3 py-2 text-center ${cal.retirado ? 'text-gray-400' : esRP ? 'text-amber-600 font-medium' : ''}`}>
                                {nota?.toFixed(2) ?? '-'}
                                {esRP && !cal.retirado && <span className="text-xs ml-1">(R)</span>}
                              </td>
                            );
                          })}
                          <td className={`px-3 py-2 text-center font-bold ${cal.retirado ? 'text-gray-400' : getNotaClass(cfActual)}`}>
                            {cfActual?.toFixed(2) ?? '-'}
                          </td>
                          <td className={`px-3 py-2 text-center font-bold ${cal.retirado ? 'text-gray-400' : getNotaClass(cfActual)}`}>
                            {cal.retirado ? '—' : literal}
                          </td>
                          <td className="px-3 py-2 text-center">
                            {cal.retirado ? (
                              <span className="px-2 py-1 rounded-full text-xs font-medium bg-gray-200 text-gray-600">
                                Retirado
                              </span>
                            ) : cfActual !== null && (
                              <span className={`px-2 py-1 rounded-full text-xs font-medium
                                ${aprobado ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                                {aprobado ? 'Aprobado' : 'Reprobado'}
                              </span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* Resumen estadístico */}
              <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-4">
                {(() => {
                  const conCF = calificaciones.filter(c => {
                    const cf = calcularCF(c, editadas[c.estudiante_id]) ?? c.cf;
                    return cf !== null;
                  });
                  const aprobados = conCF.filter(c => {
                    const cf = calcularCF(c, editadas[c.estudiante_id]) ?? c.cf;
                    return cf !== null && cf >= 70;
                  }).length;
                  const reprobados = conCF.length - aprobados;
                  const promedio = conCF.length > 0
                    ? conCF.reduce((acc, c) => acc + (calcularCF(c, editadas[c.estudiante_id]) ?? c.cf ?? 0), 0) / conCF.length
                    : 0;

                  return (
                    <>
                      <div className="bg-gray-50 rounded-lg p-3 text-center">
                        <p className="text-2xl font-bold text-gray-800">{calificaciones.length}</p>
                        <p className="text-xs text-gray-500">Total Estudiantes</p>
                      </div>
                      <div className="bg-green-50 rounded-lg p-3 text-center">
                        <p className="text-2xl font-bold text-green-600">{aprobados}</p>
                        <p className="text-xs text-green-600">Aprobados</p>
                      </div>
                      <div className="bg-red-50 rounded-lg p-3 text-center">
                        <p className="text-2xl font-bold text-red-600">{reprobados}</p>
                        <p className="text-xs text-red-600">Reprobados</p>
                      </div>
                      <div className="bg-blue-50 rounded-lg p-3 text-center">
                        <p className="text-2xl font-bold text-blue-600">{promedio.toFixed(1)}</p>
                        <p className="text-xs text-blue-600">Promedio</p>
                      </div>
                    </>
                  );
                })()}
              </div>
            </div>
          </div>
        ) : (
          <div className="bg-white rounded-xl shadow-sm border p-12 text-center">
            <BookOpen size={48} className="mx-auto text-gray-300 mb-4" />
            <p className="text-gray-500">No hay estudiantes en este curso</p>
          </div>
        )
      ) : (
        <div className="bg-white rounded-xl shadow-sm border p-12 text-center">
          <Filter size={48} className="mx-auto text-gray-300 mb-4" />
          <p className="text-gray-500">Seleccione un curso y una asignatura para ver las calificaciones</p>
        </div>
      )}
          </>
        );
      })()}
    </div>
  );
};

export default AcademicoPage;
