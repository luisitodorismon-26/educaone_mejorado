import { useState, useEffect, useMemo, Fragment } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import api from '../../services/api';
import { ArrowLeft, BookOpen, AlertTriangle, CheckCircle, FileText, Download, Save, CalendarCheck } from 'lucide-react';
import { Button, Alert, Spinner } from '../../components/ui';
import { useAuth } from '../../context/AuthContext';
import {
  EstudianteData, CampoEditable, CAMPOS_PERIODOS, NOMBRES_COMPETENCIAS,
  getLiteral, getNotaClass,
} from './secundaria/tipos';

// ════════════════════════════════════════════════════════════════════
// FichaEstudianteAsignatura v2.13 — Opción B
// Ruta: /academico/estudiante/:estudianteId/asignatura/:asignaturaId
//
// Vista 360° de UN estudiante × UNA materia. Todo lo del boletín
// MINERD en una sola pantalla:
//   - Datos básicos del estudiante
//   - Las 4 competencias × 4 períodos (editables si profesor)
//   - PCs por período + CF + literal + estado
//   - Evaluaciones extra (cascada con formulario solo de fase_pendiente)
//   - Asistencia P1-P4
//   - Botón descargar boletín PDF
//
// Útil para:
//   - Reuniones con padres ("vamos a ver cómo va Juan")
//   - Revisión rápida antes de firmar boletín
//   - Dirección consultando un estudiante puntual
// ════════════════════════════════════════════════════════════════════

interface CursoInfo {
  id: number;
  nombre: string;
  nombre_completo: string;
  grado?: string;
  nivel?: string;
}

interface AsignaturaInfo {
  id: number;
  nombre: string;
}

interface EstudianteInfo {
  id: number;
  nombre: string;
  apellido: string;
  nombre_completo: string;
  sigerd?: string;
  matricula?: string;
  numero_orden?: number | null;
  curso_id?: number;
  curso?: CursoInfo;
}

interface AsistenciaPeriodo {
  asistencia: number;
  ausencia: number;
  pct_asistencia_anual: number | null;
  pct_ausencia_anual: number | null;
}

export const FichaEstudianteAsignatura: React.FC = () => {
  const { estudianteId, asignaturaId } = useParams<{ estudianteId: string; asignaturaId: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const esProfesor = user?.role === 'profesor';
  const puedeEditar = esProfesor;

  const estIdNum = parseInt(estudianteId || '0');
  const asigIdNum = parseInt(asignaturaId || '0');

  const [datos, setDatos] = useState<EstudianteData | null>(null);
  const [estudianteInfo, setEstudianteInfo] = useState<EstudianteInfo | null>(null);
  const [asignaturaInfo, setAsignaturaInfo] = useState<AsignaturaInfo | null>(null);
  const [cursoInfo, setCursoInfo] = useState<CursoInfo | null>(null);
  const [asistencia, setAsistencia] = useState<Record<string, AsistenciaPeriodo> | null>(null);
  const [loading, setLoading] = useState(true);
  const [editadas, setEditadas] = useState<Record<number, Partial<Record<CampoEditable, number | null>>>>({});
  const [draftExtra, setDraftExtra] = useState<string>('');
  const [saving, setSaving] = useState(false);
  const [savingExtra, setSavingExtra] = useState(false);
  const [descargandoPDF, setDescargandoPDF] = useState(false);
  const [mensaje, setMensaje] = useState<{ tipo: 'success' | 'error' | 'warning'; texto: string } | null>(null);

  useEffect(() => {
    if (estIdNum && asigIdNum) cargar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [estIdNum, asigIdNum]);

  const cargar = async () => {
    setLoading(true);
    try {
      // 1. Info del estudiante (incluye curso)
      const estRes = await api.get(`/estudiantes/${estIdNum}`);
      const est = estRes.data;
      setEstudianteInfo(est);

      // 2. Asignatura
      const asigRes = await api.get(`/asignaturas`);
      const asig = (asigRes.data || []).find((a: AsignaturaInfo) => a.id === asigIdNum);
      setAsignaturaInfo(asig);

      // 3. Curso — v2.13.38: GET /cursos/{id} no existe; usamos la lista y filtramos
      if (est.curso_id) {
        const cursosRes = await api.get('/cursos');
        const cursoEncontrado = (cursosRes.data || []).find((c: any) => c.id === est.curso_id);
        setCursoInfo(cursoEncontrado || null);

        // 4. Calificaciones del estudiante en esa materia
        const calRes = await api.get(`/calificaciones-secundaria/curso/${est.curso_id}/asignatura/${asigIdNum}`);
        const todosEst = calRes.data.calificaciones || [];
        const miData = todosEst.find((d: EstudianteData) => d.estudiante.id === estIdNum);
        setDatos(miData || null);

        // 5. Asistencia del curso (filtramos al estudiante)
        try {
          const asistRes = await api.get(`/asistencia/resumen-periodos/curso/${est.curso_id}`);
          const miAsist = (asistRes.data || []).find((a: any) => a.estudiante_id === estIdNum);
          setAsistencia(miAsist?.periodos || null);
        } catch {
          setAsistencia(null);
        }
      }
    } catch (err: any) {
      setMensaje({ tipo: 'error', texto: err.response?.data?.error || 'Error cargando ficha del estudiante' });
    } finally {
      setLoading(false);
    }
  };

  const getValor = (compNum: number, campo: CampoEditable): number | null => {
    const ed = editadas[compNum];
    if (ed && campo in ed) return ed[campo] ?? null;
    if (!datos) return null;
    const comp = datos.competencias[compNum];
    if (!comp) return null;
    return comp[campo];
  };

  const handleNotaChange = (compNum: number, campo: CampoEditable, valor: string) => {
    let num: number | null;
    if (valor === '') {
      num = null;
    } else {
      const parsed = parseFloat(valor);
      if (Number.isNaN(parsed) || parsed < 0 || parsed > 100) return;
      num = parsed;
    }
    setEditadas(prev => ({
      ...prev,
      [compNum]: { ...(prev[compNum] || {}), [campo]: num },
    }));
  };

  const guardarNotas = async () => {
    const claves = Object.keys(editadas).map(Number);
    if (claves.length === 0) {
      setMensaje({ tipo: 'error', texto: 'No hay cambios por guardar' });
      return;
    }
    setSaving(true);
    let errores = 0;
    let exitos = 0;
    try {
      for (const compNum of claves) {
        try {
          await api.post('/calificaciones-secundaria', {
            estudiante_id: estIdNum,
            asignatura_id: asigIdNum,
            competencia_numero: compNum,
            ...editadas[compNum],
          });
          exitos++;
        } catch (err) {
          errores++;
        }
      }
      if (errores === 0) {
        setMensaje({ tipo: 'success', texto: `${exitos} competencia(s) guardada(s)` });
      } else if (exitos > 0) {
        setMensaje({ tipo: 'warning', texto: `${exitos} guardadas, ${errores} fallaron` });
      } else {
        setMensaje({ tipo: 'error', texto: 'Error al guardar' });
      }
      setEditadas({});
      await cargar();
    } finally {
      setSaving(false);
    }
  };

  const guardarExtra = async () => {
    if (!datos?.evaluacion_extra?.fase_pendiente) return;
    const fase = datos.evaluacion_extra.fase_pendiente;
    if (!draftExtra) {
      setMensaje({ tipo: 'error', texto: 'Indique la nota' });
      return;
    }
    const nota = parseFloat(draftExtra);
    if (Number.isNaN(nota) || nota < 0 || nota > 100) {
      setMensaje({ tipo: 'error', texto: 'La nota debe estar entre 0 y 100' });
      return;
    }
    setSavingExtra(true);
    try {
      await api.post('/calificaciones-secundaria/evaluacion-extra', {
        estudiante_id: estIdNum,
        asignatura_id: asigIdNum,
        tipo: fase,
        nota,
      });
      setMensaje({ tipo: 'success', texto: `Evaluación ${fase} registrada` });
      setDraftExtra('');
      await cargar();
    } catch (err: any) {
      setMensaje({ tipo: 'error', texto: err.response?.data?.error || 'Error al guardar' });
    } finally {
      setSavingExtra(false);
    }
  };

  const descargarBoletin = async () => {
    setDescargandoPDF(true);
    try {
      const res = await api.get(`/boletines/estudiante/${estIdNum}/pdf-minerd-v2`, { responseType: 'blob' });
      // v2.13.9: validar que sí es PDF
      if (res.data.type === 'application/json' || res.data.size < 500) {
        const texto = await res.data.text();
        try {
          const json = JSON.parse(texto);
          throw new Error(json.error || json.detail || 'Error en respuesta');
        } catch (e: any) {
          throw new Error(e?.message || 'El servidor no devolvió un PDF válido');
        }
      }
      const blob = new Blob([res.data], { type: 'application/pdf' });
      const link = document.createElement('a');
      link.href = window.URL.createObjectURL(blob);
      link.download = `Boletin_${estudianteInfo?.nombre_completo?.replace(/\s+/g, '_') || estIdNum}.pdf`;
      link.click();
      window.URL.revokeObjectURL(link.href);
    } catch (err: any) {
      // v2.13.9: extraer mensaje real del blob si aplica
      let mensajeError = err?.message || 'Error descargando boletín';
      if (err?.response?.data instanceof Blob) {
        try {
          const texto = await err.response.data.text();
          const json = JSON.parse(texto);
          mensajeError = json.error || json.detail || texto;
        } catch { /* no era JSON */ }
      }
      setMensaje({ tipo: 'error', texto: mensajeError });
    } finally {
      setDescargandoPDF(false);
    }
  };

  // Promedio competencia (preview local con notas editadas)
  const calcularProm = (compNum: number): number | null => {
    const vals: number[] = [];
    for (const { p, rp } of CAMPOS_PERIODOS) {
      const pVal = getValor(compNum, p);
      const rpVal = getValor(compNum, rp);
      let efectivo: number | null = null;
      if (rpVal !== null && pVal !== null) efectivo = Math.max(pVal, rpVal);
      else if (rpVal !== null) efectivo = rpVal;
      else if (pVal !== null) efectivo = pVal;
      if (efectivo === null) return null;
      vals.push(efectivo);
    }
    return Math.round((vals.reduce((a, b) => a + b, 0) / 4) * 10) / 10;
  };

  // Iniciales del avatar
  const iniciales = useMemo(() => {
    if (!estudianteInfo) return '?';
    const n = (estudianteInfo.nombre || '').charAt(0);
    const a = (estudianteInfo.apellido || '').charAt(0);
    return (n + a).toUpperCase() || '?';
  }, [estudianteInfo]);

  const colorEstado = (cf: number | null): string => {
    if (cf === null) return 'text-gray-400';
    if (cf >= 70) return 'text-green-600';
    return 'text-red-600';
  };

  if (loading) return <div className="flex justify-center py-10"><Spinner /></div>;

  if (!datos || !estudianteInfo) {
    return (
      <div className="bg-white rounded-xl shadow-sm border p-10 text-center">
        <p className="text-gray-500">No se encontró información para este estudiante × asignatura</p>
        <Button variant="secondary" onClick={() => navigate(-1)} className="mt-4">Volver</Button>
      </div>
    );
  }

  const ev = datos.evaluacion_extra;
  const fasePendiente = ev?.fase_pendiente;
  const pctAsisAnual = asistencia
    ? Math.round(((asistencia.p1?.asistencia || 0) + (asistencia.p2?.asistencia || 0) +
                  (asistencia.p3?.asistencia || 0) + (asistencia.p4?.asistencia || 0)) /
                 Math.max(1,
                   (asistencia.p1?.asistencia || 0) + (asistencia.p1?.ausencia || 0) +
                   (asistencia.p2?.asistencia || 0) + (asistencia.p2?.ausencia || 0) +
                   (asistencia.p3?.asistencia || 0) + (asistencia.p3?.ausencia || 0) +
                   (asistencia.p4?.asistencia || 0) + (asistencia.p4?.ausencia || 0)
                 ) * 100)
    : null;

  return (
    <div className="space-y-4">
      {/* Breadcrumb + back */}
      <div className="flex items-center gap-2 text-sm text-gray-500">
        <Link to="/academico" className="hover:text-blue-700 hover:underline">Calificaciones</Link>
        <span>›</span>
        <span>{cursoInfo?.nombre_completo || 'Curso'}</span>
        <span>›</span>
        <span>{asignaturaInfo?.nombre || 'Asignatura'}</span>
        <span>›</span>
        <span className="text-gray-800 font-medium">{estudianteInfo.nombre_completo}</span>
      </div>

      {mensaje && <Alert variant={mensaje.tipo} onClose={() => setMensaje(null)}>{mensaje.texto}</Alert>}

      {/* Cabecera del estudiante */}
      <div className="bg-white rounded-xl shadow-sm border p-5">
        <div className="flex items-center gap-4 flex-wrap">
          <div className="w-14 h-14 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-lg font-bold">
            {iniciales}
          </div>
          <div className="flex-1 min-w-[200px]">
            <h1 className="text-xl font-bold text-gray-900">{estudianteInfo.nombre_completo}</h1>
            <p className="text-sm text-gray-500">
              {estudianteInfo.numero_orden && `#${estudianteInfo.numero_orden} · `}
              {cursoInfo?.nombre_completo} · {asignaturaInfo?.nombre}
              {estudianteInfo.sigerd && ` · SIGERD ${estudianteInfo.sigerd}`}
            </p>
          </div>
          <Button variant="secondary" onClick={() => navigate(-1)} icon={<ArrowLeft size={16} />}>
            Volver
          </Button>
          <Button variant="primary" onClick={descargarBoletin} loading={descargandoPDF} icon={<Download size={16} />}>
            Boletín PDF
          </Button>
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-white rounded-lg border p-4">
          <p className="text-xs text-gray-500 uppercase tracking-wider">CF actual</p>
          <p className={`text-3xl font-bold mt-1 ${colorEstado(datos.cf)}`}>
            {datos.cf !== null ? datos.cf.toFixed(0) : '—'}
          </p>
          <p className={`text-xs mt-1 ${colorEstado(datos.cf)}`}>
            {datos.literal || getLiteral(datos.cf)}
          </p>
        </div>
        <div className="bg-white rounded-lg border p-4">
          <p className="text-xs text-gray-500 uppercase tracking-wider">Estado</p>
          <p className={`text-lg font-bold mt-1 ${
            datos.cf === null ? 'text-gray-400' :
            datos.cf >= 70 ? 'text-green-600' :
            fasePendiente ? 'text-amber-600' :
            'text-red-600'
          }`}>
            {datos.cf === null ? 'Sin notas' :
              datos.cf >= 70 ? 'Aprobado' :
              fasePendiente ? `Cascada: ${fasePendiente}` :
              ev?.condicion_final?.replace(/_/g, ' ') || 'Pendiente'
            }
          </p>
        </div>
        <div className="bg-white rounded-lg border p-4">
          <p className="text-xs text-gray-500 uppercase tracking-wider">Asistencia anual</p>
          <p className={`text-3xl font-bold mt-1 ${
            pctAsisAnual === null ? 'text-gray-400' :
            pctAsisAnual >= 95 ? 'text-green-600' :
            pctAsisAnual >= 85 ? 'text-amber-600' :
            'text-red-600'
          }`}>
            {pctAsisAnual !== null ? `${pctAsisAnual}%` : '—'}
          </p>
        </div>
        <div className="bg-white rounded-lg border p-4">
          <p className="text-xs text-gray-500 uppercase tracking-wider">Nota final</p>
          <p className={`text-3xl font-bold mt-1 ${colorEstado(ev?.nota_final ?? datos.cf)}`}>
            {(ev?.nota_final ?? datos.cf) !== null ? (ev?.nota_final ?? datos.cf)?.toFixed(0) : '—'}
          </p>
          {ev?.condicion_final && (
            <p className="text-xs text-gray-500 mt-1 truncate" title={ev.condicion_final}>
              {ev.condicion_final.replace(/_/g, ' ')}
            </p>
          )}
        </div>
      </div>

      {/* Tabla de notas */}
      <div className="bg-white rounded-xl shadow-sm border p-4">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <h3 className="font-bold text-gray-800 flex items-center gap-2">
            <BookOpen className="text-blue-600" />
            Notas por competencia y período
          </h3>
          {Object.keys(editadas).length > 0 && puedeEditar && (
            <Button onClick={guardarNotas} loading={saving} icon={<Save size={16} />} variant="success" size="sm">
              Guardar ({Object.keys(editadas).length})
            </Button>
          )}
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="bg-gray-50 text-xs">
                <th className="px-3 py-2 text-left font-medium text-gray-600">Competencia</th>
                {CAMPOS_PERIODOS.map(({ periodo }) => (
                  <th key={`h-${periodo}`} className="px-2 py-2 text-center font-medium text-gray-600" colSpan={2}>
                    P{periodo}
                  </th>
                ))}
                <th className="px-3 py-2 text-center font-medium text-blue-700 bg-blue-50">Promedio</th>
              </tr>
              <tr className="bg-gray-50 text-xs">
                <th></th>
                {CAMPOS_PERIODOS.map(({ periodo }) => (
                  <Fragment key={`sub-${periodo}`}>
                    <th className="px-1 py-1 font-normal text-gray-500">P</th>
                    <th className="px-1 py-1 font-normal text-amber-600">RP</th>
                  </Fragment>
                ))}
                <th></th>
              </tr>
            </thead>
            <tbody>
              {[1, 2, 3, 4].map(compNum => {
                const prom = calcularProm(compNum) ?? datos.competencias[compNum]?.promedio_competencia ?? null;
                return (
                  <tr key={compNum} className="border-b">
                    <td className="px-3 py-2 font-medium text-gray-700">{NOMBRES_COMPETENCIAS[compNum]}</td>
                    {CAMPOS_PERIODOS.map(({ p, rp }) => {
                      // v2.13.1: RP solo se edita si P < 70
                      const pVal = getValor(compNum, p);
                      const rpDeshabilitado = pVal === null || pVal >= 70;
                      const tooltipRP = pVal === null
                        ? 'Cargue primero la nota P de este período'
                        : pVal >= 70
                          ? `El estudiante aprobó P con ${pVal.toFixed(1)} (≥ 70), no necesita recuperación`
                          : '';
                      return (
                        <Fragment key={`${compNum}-${p}`}>
                          <td className="px-1 py-1 text-center">
                            {puedeEditar ? (
                              <input
                                type="number" min={0} max={100} step={0.01}
                                value={getValor(compNum, p) ?? ''}
                                onChange={e => handleNotaChange(compNum, p, e.target.value)}
                                className="w-14 px-1 py-1 text-center border rounded text-sm"
                              />
                            ) : (
                              <span className={getNotaClass(getValor(compNum, p))}>
                                {getValor(compNum, p)?.toFixed(0) ?? '—'}
                              </span>
                            )}
                          </td>
                          <td className="px-1 py-1 text-center bg-amber-50">
                            {puedeEditar ? (
                              rpDeshabilitado ? (
                                <input
                                  type="text"
                                  value=""
                                  disabled
                                  title={tooltipRP}
                                  className="w-14 px-1 py-1 text-center border rounded text-sm bg-gray-100 border-gray-200 cursor-not-allowed text-gray-300"
                                />
                              ) : (
                                <input
                                  type="number" min={0} max={100} step={0.01}
                                  value={getValor(compNum, rp) ?? ''}
                                  onChange={e => handleNotaChange(compNum, rp, e.target.value)}
                                  className="w-14 px-1 py-1 text-center border rounded text-sm bg-amber-50 border-amber-200"
                                />
                              )
                            ) : (
                              <span className="text-amber-700">
                                {getValor(compNum, rp)?.toFixed(0) ?? '—'}
                              </span>
                            )}
                          </td>
                        </Fragment>
                      );
                    })}
                    <td className={`px-3 py-2 text-center font-bold bg-blue-50 ${getNotaClass(prom)}`}>
                      {prom !== null ? prom.toFixed(1) : '—'}
                    </td>
                  </tr>
                );
              })}
              {/* Fila PC + CF */}
              <tr className="bg-gray-100 font-bold border-t-2">
                <td className="px-3 py-2 text-gray-700">PC del período →</td>
                {(['pc1', 'pc2', 'pc3', 'pc4'] as const).map(pc => {
                  const v = datos.pc_por_periodo[pc];
                  return (
                    <td key={pc} colSpan={2} className="px-1 py-2 text-center text-gray-700">
                      {v !== null ? v.toFixed(1) : '—'}
                    </td>
                  );
                })}
                <td className={`px-3 py-2 text-center font-bold bg-blue-100 ${colorEstado(datos.cf)}`}>
                  CF: {datos.cf !== null ? datos.cf.toFixed(0) : '—'}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* Cascada de evaluaciones extra */}
      {ev && (
        <div className="bg-white rounded-xl shadow-sm border p-4">
          <h3 className="font-bold text-gray-800 flex items-center gap-2 mb-3">
            <AlertTriangle className={fasePendiente ? 'text-amber-600' : 'text-gray-400'} />
            Cascada MINERD
            {fasePendiente && (
              <span className="ml-auto text-xs px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 font-medium uppercase">
                Fase pendiente: {fasePendiente}
              </span>
            )}
            {!fasePendiente && ev.condicion_final && (
              <span className="ml-auto text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-800 font-medium">
                Resuelta: {ev.condicion_final.replace(/_/g, ' ')}
              </span>
            )}
          </h3>

          <div className="space-y-2 text-sm">
            {/* Completiva */}
            <div className={`p-3 rounded-lg border ${fasePendiente === 'completiva' ? 'bg-amber-50 border-amber-300' : 'bg-gray-50 border-gray-200'}`}>
              <div className="flex items-center justify-between flex-wrap gap-2">
                <span className="font-medium">Completiva</span>
                <span className="text-xs text-gray-500">50% CF + 50% C.E.C.</span>
              </div>
              <div className="mt-2 flex items-center gap-3 text-sm flex-wrap">
                <span>CF: <strong>{ev.cf_original?.toFixed(0) ?? '—'}</strong></span>
                <span>×</span>
                <span>50%</span>
                <span>+</span>
                <span>C.E.C.: <strong>{ev.cec?.toFixed(0) ?? '—'}</strong></span>
                <span>×</span>
                <span>50%</span>
                <span>=</span>
                <span className={`font-bold ${(ev.completiva_final ?? 0) >= 70 ? 'text-green-600' : 'text-red-600'}`}>
                  {ev.completiva_final?.toFixed(0) ?? '—'}
                </span>
              </div>
            </div>

            {/* Extraordinaria */}
            <div className={`p-3 rounded-lg border ${
              fasePendiente === 'extraordinaria' ? 'bg-amber-50 border-amber-300' :
              ev.ceex !== null || ev.extraordinaria_final !== null ? 'bg-gray-50 border-gray-200' :
              'bg-gray-50 border-gray-200 opacity-50'
            }`}>
              <div className="flex items-center justify-between flex-wrap gap-2">
                <span className="font-medium">Extraordinaria</span>
                <span className="text-xs text-gray-500">30% CF + 70% C.E.EX</span>
              </div>
              <div className="mt-2 flex items-center gap-3 text-sm flex-wrap">
                <span>CF: <strong>{ev.cf_original?.toFixed(0) ?? '—'}</strong></span>
                <span>×</span>
                <span>30%</span>
                <span>+</span>
                <span>C.E.EX: <strong>{ev.ceex?.toFixed(0) ?? '—'}</strong></span>
                <span>×</span>
                <span>70%</span>
                <span>=</span>
                <span className={`font-bold ${(ev.extraordinaria_final ?? 0) >= 70 ? 'text-green-600' : 'text-red-600'}`}>
                  {ev.extraordinaria_final?.toFixed(0) ?? '—'}
                </span>
              </div>
            </div>

            {/* Especial */}
            <div className={`p-3 rounded-lg border ${
              fasePendiente === 'especial' ? 'bg-amber-50 border-amber-300' :
              ev.ce !== null || ev.especial_final !== null ? 'bg-gray-50 border-gray-200' :
              'bg-gray-50 border-gray-200 opacity-50'
            }`}>
              <div className="flex items-center justify-between flex-wrap gap-2">
                <span className="font-medium">Especial</span>
                <span className="text-xs text-gray-500">CF + C.E. (suma simple)</span>
              </div>
              <div className="mt-2 flex items-center gap-3 text-sm flex-wrap">
                <span>CF: <strong>{ev.cf_original?.toFixed(0) ?? '—'}</strong></span>
                <span>+</span>
                <span>C.E.: <strong>{ev.ce?.toFixed(0) ?? '—'}</strong></span>
                <span>=</span>
                <span className={`font-bold ${(ev.especial_final ?? 0) >= 70 ? 'text-green-600' : 'text-red-600'}`}>
                  {ev.especial_final?.toFixed(0) ?? '—'}
                </span>
              </div>
            </div>

            {/* Formulario fase pendiente */}
            {puedeEditar && fasePendiente && (
              <div className="mt-3 p-3 bg-blue-50 border border-blue-300 rounded-lg">
                <p className="text-sm text-blue-900 mb-2 font-medium">
                  Cargar nota de {fasePendiente.toUpperCase()}:
                </p>
                <div className="flex gap-2 items-center">
                  <input
                    type="number" min={0} max={100} step={0.01}
                    value={draftExtra}
                    onChange={e => setDraftExtra(e.target.value)}
                    placeholder={`Nota ${fasePendiente}`}
                    className="px-3 py-2 border rounded text-sm w-32"
                  />
                  <Button
                    variant="success"
                    onClick={guardarExtra}
                    loading={savingExtra}
                    icon={<Save size={16} />}
                  >
                    Registrar
                  </Button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Asistencia */}
      <div className="bg-white rounded-xl shadow-sm border p-4">
        <h3 className="font-bold text-gray-800 flex items-center gap-2 mb-3">
          <CalendarCheck className="text-blue-600" />
          Asistencia del estudiante
        </h3>
        {!asistencia ? (
          <p className="text-sm text-gray-500">Sin datos de asistencia</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="bg-gray-50">
                  <th className="px-3 py-2 text-left">Período</th>
                  <th className="px-3 py-2 text-center text-green-600">Asistencias</th>
                  <th className="px-3 py-2 text-center text-red-600">Ausencias</th>
                  <th className="px-3 py-2 text-center">% asistencia</th>
                </tr>
              </thead>
              <tbody>
                {(['p1', 'p2', 'p3', 'p4'] as const).map(pk => {
                  const p = asistencia[pk];
                  return (
                    <tr key={pk} className="border-b">
                      <td className="px-3 py-2 font-medium">{pk.toUpperCase()}</td>
                      <td className="px-3 py-2 text-center text-green-700">{p?.asistencia ?? 0}</td>
                      <td className="px-3 py-2 text-center text-red-700">{p?.ausencia ?? 0}</td>
                      <td className="px-3 py-2 text-center font-medium">
                        {p?.pct_asistencia_anual !== null && p?.pct_asistencia_anual !== undefined
                          ? `${p.pct_asistencia_anual}%`
                          : '—'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default FichaEstudianteAsignatura;
