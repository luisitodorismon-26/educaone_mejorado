import { useState, useEffect, useRef } from 'react';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';
import { mensajeDeErrorDescarga } from '../../utils/errorServidor';
import { FileText, Search, ChevronDown, ChevronUp, LayoutGrid, List, Users, CheckCircle2, AlertCircle, Info } from 'lucide-react';
import { Select, Button, Alert } from '../../components/ui';
import { labelCurso } from '../../utils/labelCurso';
import { CompartirFamiliasPanel } from './CompartirFamiliasPanel';

interface Curso { id: number; nombre_completo: string; grado?: string; nombre?: string; tanda?: string; }

interface NotaPeriodo {
  estudiante_id: number; nombre: string; no_lista: number;
  asignaturas: Record<string, number | null>; promedio: number | null;
  // TRAS-1 · «Trasladado a…», «Retirado desde…», «Incorporado desde…».
  avisos?: string[];
}
interface ReporteData {
  curso: string; periodo: number;
  asignaturas_nombres: string[]; estudiantes: NotaPeriodo[];
  nivel?: 'primaria' | 'secundaria';
}

// Cómo se forma la nota del período en cada nivel. Solo describe el cálculo
// que hace el backend para ese nivel; no lo cambia.
const REGLA_NOTA_PERIODO = {
  secundaria: 'nota del período: el último P registrado (competencia más alta con valor; con recuperación, el mayor entre P y RP), no el promedio',
  primaria: 'nota del período: el promedio de sus competencias en ese período (si hubo recuperación, cuenta la RP en lugar de la P)',
};

interface CompetenciaValor { competencia: number; valor: number | null; }
interface AsigCompetencias {
  asignatura_id: number; asignatura: string;
  competencias: CompetenciaValor[]; pc: number | null; ultimo_p: number | null; completo: boolean;
}
interface EstCompetencias {
  estudiante_id: number; no_lista: number; nombre: string;
  avisos?: string[];
  asignaturas: AsigCompetencias[];
}
interface CompetenciasData {
  curso: string; periodo: number; ano_escolar: string;
  asignaturas_nombres: string[]; estudiantes: EstCompetencias[];
}

type Vista = 'pc' | 'competencias';

// La nota se escribe igual que en los PDF del período: entera si lo es, si no
// con un decimal. No se redondea a entero ni se trunca (84.5 se ve 84.5).
const fmtNota = (nota: number | null | undefined) => {
  if (nota === null || nota === undefined) return '-';
  return Math.abs(nota - Math.round(nota)) < 0.05 ? String(Math.round(nota)) : nota.toFixed(1);
};

export const CalificacionesGeneralPage = () => {
  const { user } = useAuth();
  const [cursos, setCursos] = useState<Curso[]>([]);
  const [cursoId, setCursoId] = useState<number>(0);
  const [periodo, setPeriodo] = useState<number>(1);
  const [vista, setVista] = useState<Vista>('pc');

  const [data, setData] = useState<ReporteData | null>(null);
  const [compData, setCompData] = useState<CompetenciasData | null>(null);
  const [asignaturaSel, setAsignaturaSel] = useState<string>('');

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [ordenarPor, setOrdenarPor] = useState<string>('no_lista');
  const [ordenDesc, setOrdenDesc] = useState(false);

  const [descargandoPadres, setDescargandoPadres] = useState(false);
  const [descargandoTabla, setDescargandoTabla] = useState(false);
  const [descargandoEst, setDescargandoEst] = useState<number | null>(null);
  const [anoNombre, setAnoNombre] = useState<string>('');
  // FAM-DOC-1 · selección para compartir (individual o por curso).
  const [seleccion, setSeleccion] = useState<Set<number>>(new Set());
  const [panel, setPanel] = useState<{ ids: number[] } | null>(null);
  // Curso y período de la tabla que se ve (no los de los selectores, que pueden cambiar antes de «Ver notas»).
  const [consulta, setConsulta] = useState<{ cursoId: number; periodo: number } | null>(null);

  useEffect(() => { cargarCursos(); cargarAno(); }, []);

  const cargarAno = async () => {
    try { const res = await api.get('/ano-escolar'); setAnoNombre(res.data?.nombre || ''); }
    catch { setAnoNombre(''); }
  };

  const cargarCursos = async () => {
    try { const res = await api.get('/cursos'); setCursos(res.data || []); }
    catch { setError('Error al cargar cursos'); }
  };

  // FAM-DOC-1 · lo que se ve, se descarga y se comparte es SIEMPRE el curso y
  // período de la última «Ver notas». Cambiar un filtro limpia la tabla y
  // cierra el panel; una respuesta que llegue después de cambiarlo se descarta.
  const consultaVigente = useRef(0);
  const limpiarConsulta = () => {
    consultaVigente.current += 1;
    setData(null); setCompData(null); setSeleccion(new Set()); setPanel(null); setConsulta(null); setLoading(false);
  };

  const cargar = async () => {
    if (!cursoId) return;
    const id = ++consultaVigente.current;
    setLoading(true); setError(''); setData(null); setCompData(null); setSeleccion(new Set()); setPanel(null); setConsulta(null);
    try {
      if (vista === 'pc') {
        const res = await api.get(`/calificaciones/por-periodo?curso_id=${cursoId}&periodo=${periodo}`);
        if (id !== consultaVigente.current) return;
        setData(res.data);
        setConsulta({ cursoId, periodo });
      } else {
        const res = await api.get(`/calificaciones-secundaria/curso/${cursoId}/periodo/${periodo}/competencias`);
        if (id !== consultaVigente.current) return;
        setCompData(res.data);
        if (res.data.asignaturas_nombres?.length && !asignaturaSel) {
          setAsignaturaSel(res.data.asignaturas_nombres[0]);
        }
      }
    } catch (err: any) { if (id === consultaVigente.current) setError(err.response?.data?.error || 'Error al cargar notas'); }
    finally { if (id === consultaVigente.current) setLoading(false); }
  };

  const descargarBlob = async (url: string, filename: string) => {
    const response = await api.get(url, { responseType: 'blob' });
    if (response.data.type === 'application/json' || response.data.size < 300) {
      const texto = await response.data.text();
      try { const j = JSON.parse(texto); throw new Error(j.error || 'Error'); }
      catch (e: any) { throw new Error(e?.message || 'El servidor no devolvio un PDF'); }
    }
    const dlUrl = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement('a');
    link.href = dlUrl;
    link.setAttribute('download', filename);
    document.body.appendChild(link); link.click(); link.remove();
    window.URL.revokeObjectURL(dlUrl);
  };

  const nombreCurso = () => cursos.find(c => c.id === cursoId)?.nombre_completo?.replace(/ /g, '_') || 'Curso';

  const descargarPDF = async () => {
    if (!cursoId) return;
    setDescargandoTabla(true); setError('');
    try { await descargarBlob(`/calificaciones/por-periodo/pdf?curso_id=${cursoId}&periodo=${periodo}`, `Notas_P${periodo}_${nombreCurso()}.pdf`); }
    catch (e: any) { setError(await mensajeDeErrorDescarga(e, { porDefecto: 'Error al descargar PDF' })); }
    finally { setDescargandoTabla(false); }
  };

  const descargarReportePadresCurso = async () => {
    if (!cursoId) return;
    setDescargandoPadres(true); setError('');
    try {
      await descargarBlob(
        `/calificaciones-secundaria/reporte-padres/curso/${cursoId}/pdf?periodo=${periodo}`,
        `Reporte_Periodo${periodo}_Curso_${nombreCurso()}.pdf`
      );
    } catch (e: any) { setError(await mensajeDeErrorDescarga(e, { porDefecto: 'Error al generar reporte' })); }
    finally { setDescargandoPadres(false); }
  };

  const descargarReportePadresIndividual = async (estId: number, nombre: string) => {
    if (!cursoId) return;
    setDescargandoEst(estId); setError('');
    try {
      await descargarBlob(
        `/calificaciones-secundaria/reporte-padres/curso/${cursoId}/pdf?periodo=${periodo}&estudiante_id=${estId}`,
        `Reporte_Periodo${periodo}_${nombre.replace(/\s+/g, '_')}.pdf`
      );
    } catch (e: any) { setError(await mensajeDeErrorDescarga(e, { porDefecto: 'Error al generar reporte individual' })); }
    finally { setDescargandoEst(null); }
  };

  const getColorNota = (nota: number | null) => {
    if (nota === null || nota === undefined) return 'text-gray-400';
    if (nota >= 90) return 'text-emerald-700 font-bold';
    if (nota >= 80) return 'text-blue-700';
    if (nota >= 70) return 'text-amber-700';
    return 'text-red-700 font-bold';
  };
  const getBgNota = (nota: number | null) => (nota !== null && nota !== undefined && nota < 70) ? 'bg-red-50' : '';

  const estudiantesOrdenados = data ? [...data.estudiantes].sort((a, b) => {
    let valA: any, valB: any;
    if (ordenarPor === 'no_lista') { valA = a.no_lista; valB = b.no_lista; }
    else if (ordenarPor === 'nombre') { valA = a.nombre; valB = b.nombre; }
    else if (ordenarPor === 'promedio') { valA = a.promedio ?? -1; valB = b.promedio ?? -1; }
    else { valA = a.asignaturas[ordenarPor] ?? -1; valB = b.asignaturas[ordenarPor] ?? -1; }
    return ordenDesc ? (valA < valB ? 1 : -1) : (valA < valB ? -1 : 1);
  }) : [];

  const toggleOrden = (col: string) => {
    if (ordenarPor === col) setOrdenDesc(!ordenDesc);
    else { setOrdenarPor(col); setOrdenDesc(false); }
  };
  const SortIcon = ({ col }: { col: string }) => ordenarPor === col ? (ordenDesc ? <ChevronDown size={12} /> : <ChevronUp size={12} />) : null;

  const stats = (() => {
    if (!data?.estudiantes.length) return null;
    const proms = data.estudiantes.map(e => e.promedio).filter(p => p !== null) as number[];
    if (!proms.length) return null;
    const avg = proms.reduce((a, b) => a + b, 0) / proms.length;
    return { avg: avg.toFixed(1), aprobados: proms.filter(p => p >= 70).length, reprobados: proms.filter(p => p < 70).length, max: Math.max(...proms).toFixed(1), min: Math.min(...proms).toFixed(1) };
  })();

  if (user?.role !== 'direccion' && user?.role !== 'coordinador') {
    return (<div className="p-8 text-center"><div className="text-6xl mb-4">🔒</div><h2 className="text-xl font-bold text-gray-800">Acceso Restringido</h2></div>);
  }

  const periodoOpts = [{ value: 1, label: 'Periodo 1' }, { value: 2, label: 'Periodo 2' }, { value: 3, label: 'Periodo 3' }, { value: 4, label: 'Periodo 4' }];

  // Indicadores informativos (no bloquean nada): materias sin nota en el período.
  const pendientesDe = (est: NotaPeriodo) => data ? data.asignaturas_nombres.filter(a => est.asignaturas[a] === null || est.asignaturas[a] === undefined).length : 0;
  const totalEst = data?.estudiantes.length || 0;
  const conPendientes = data ? data.estudiantes.filter(e => pendientesDe(e) > 0).length : 0;
  const esPrimaria = data?.nivel === 'primaria';
  const motivoSinCompartir = esPrimaria ? 'El Reporte del Período todavía no incluye las calificaciones de Primaria' : '';

  const todosMarcados = totalEst > 0 && seleccion.size === totalEst;
  const alternarTodos = () => setSeleccion(todosMarcados ? new Set() : new Set(data!.estudiantes.map(e => e.estudiante_id)));
  const alternar = (id: number) => setSeleccion(prev => { const n = new Set(prev); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  // Orden de la lista del curso (n.º de lista) para recorrer las familias.
  const idsEnOrden = (ids: Set<number> | null) => data ? [...data.estudiantes]
    .sort((a, b) => (a.no_lista ?? 9999) - (b.no_lista ?? 9999))
    .map(e => e.estudiante_id).filter(id => !ids || ids.has(id)) : [];
  const abrirCompartir = (soloId?: number) => {
    if (esPrimaria || !data || !consulta) return;
    const ids = soloId ? [soloId] : idsEnOrden(seleccion.size ? seleccion : null);
    if (ids.length) setPanel({ ids });
  };

  const BtnAccion = ({ children, ...p }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...p} className={`inline-flex items-center justify-center gap-2 rounded-lg border-2 border-gray-300 bg-white px-4 py-2.5 font-semibold text-gray-800 shadow-sm hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed ${p.className || ''}`}>{children}</button>
  );
  const IconoWA = ({ size = 18 }: { size?: number }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12.04 2C6.58 2 2.13 6.45 2.13 11.91c0 1.75.46 3.45 1.32 4.95L2.05 22l5.25-1.38a9.9 9.9 0 0 0 4.74 1.21c5.46 0 9.91-4.45 9.91-9.91C21.96 6.45 17.5 2 12.04 2Zm0 18.15a8.2 8.2 0 0 1-4.19-1.15l-.3-.18-3.12.82.83-3.04-.2-.31a8.2 8.2 0 0 1-1.26-4.38c0-4.54 3.7-8.23 8.25-8.23 4.54 0 8.24 3.69 8.24 8.24 0 4.54-3.7 8.23-8.24 8.23Zm4.52-6.16c-.25-.12-1.47-.72-1.69-.81-.23-.08-.39-.12-.56.13-.16.25-.64.81-.79.97-.14.17-.29.19-.54.06-.25-.12-1.05-.39-1.99-1.23-.74-.66-1.23-1.47-1.38-1.72-.14-.25-.02-.38.11-.51.11-.11.25-.29.37-.43.13-.15.17-.25.25-.42.08-.17.04-.31-.02-.43-.06-.13-.56-1.35-.77-1.85-.2-.48-.41-.42-.56-.43h-.48c-.17 0-.43.06-.66.31-.23.25-.87.85-.87 2.07 0 1.22.89 2.4 1.01 2.56.12.17 1.75 2.67 4.24 3.74 2.07.9 2.49.72 2.94.68.48-.07 1.47-.6 1.67-1.18.21-.58.21-1.07.14-1.18-.06-.1-.22-.16-.47-.29Z" /></svg>
  );
  const ChipEstado = ({ pendientes }: { pendientes: number }) => pendientes === 0
    ? <span className="inline-flex items-center gap-1 rounded-full bg-green-100 text-green-800 px-2.5 py-1 text-xs font-semibold whitespace-nowrap"><CheckCircle2 size={14} /> Completo</span>
    : <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 text-amber-800 px-2.5 py-1 text-xs font-semibold whitespace-nowrap" title={`${pendientes} ${pendientes === 1 ? 'materia' : 'materias'} sin nota (informativo)`}><AlertCircle size={14} /> Nota pendiente</span>;

  return (
    <div className={`space-y-5 ${panel ? 'xl:pr-[440px]' : ''}`}>
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold text-gray-900">Notas por período</h1>
        <p className="text-gray-600 mt-1">Consulta las calificaciones y prepara los reportes para las familias.</p>
      </div>

      {error && <Alert variant="error" onClose={() => setError('')}><span className="whitespace-pre-line" data-error-descarga>{error}</span></Alert>}

      <div className="flex items-center gap-1 bg-gray-100 rounded-lg p-1 w-full sm:w-fit overflow-x-auto">
        <button onClick={() => { setVista('pc'); limpiarConsulta(); }}
          className={`flex items-center gap-2 px-3 sm:px-4 py-2 rounded-md text-sm font-medium transition-colors whitespace-nowrap ${vista === 'pc' ? 'bg-white text-blue-700 shadow-sm' : 'text-gray-600 hover:text-gray-800'}`}>
          <List size={16} /> Nota del período
        </button>
        <button onClick={() => { setVista('competencias'); limpiarConsulta(); }}
          className={`flex items-center gap-2 px-3 sm:px-4 py-2 rounded-md text-sm font-medium transition-colors whitespace-nowrap ${vista === 'competencias' ? 'bg-white text-blue-700 shadow-sm' : 'text-gray-600 hover:text-gray-800'}`}>
          <LayoutGrid size={16} /> Por competencia
        </button>
      </div>

      <div className="bg-white rounded-xl border shadow-sm p-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)_auto] gap-3 items-end">
          <Select label="Curso" value={cursoId.toString()} onChange={e => { setCursoId(Number(e.target.value)); limpiarConsulta(); }} options={cursos.map(c => ({ value: c.id, label: labelCurso(c), group: c.tanda || 'Sin tanda' }))} placeholder="Seleccionar curso" />
          <div className="w-full">
            <label className="block text-sm font-medium text-gray-700 mb-1">Año</label>
            <div className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-gray-50 text-gray-800" title="Las notas y los reportes son del año escolar activo">{anoNombre || 'Año escolar activo'}</div>
          </div>
          <Select label="Período" value={periodo.toString()} onChange={e => { setPeriodo(Number(e.target.value)); limpiarConsulta(); }} options={periodoOpts} />
          <Button onClick={cargar} disabled={!cursoId} loading={loading} icon={<Search size={18} />} className="w-full xl:w-auto whitespace-nowrap">Ver notas</Button>
        </div>
      </div>

      {vista === 'pc' && data && (
        <>
          <div className="flex flex-col sm:flex-row sm:flex-wrap gap-3">
            <BtnAccion onClick={descargarPDF} disabled={descargandoTabla} title="Todas las asignaturas del período en una tabla">
              <FileText size={18} /> {descargandoTabla ? 'Generando…' : 'Tabla general PDF'}
            </BtnAccion>
            <BtnAccion onClick={descargarReportePadresCurso} disabled={descargandoPadres} title="Un reporte por estudiante, todo el curso en un PDF">
              <FileText size={18} /> {descargandoPadres ? 'Generando…' : 'Reportes del curso PDF'}
            </BtnAccion>
            <button onClick={() => abrirCompartir()} disabled={esPrimaria || totalEst === 0} title={motivoSinCompartir || 'Compartir el reporte de cada estudiante con su familia'}
              data-compartir-familias
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-green-700 hover:bg-green-800 px-4 py-2.5 font-semibold text-white shadow-sm disabled:opacity-50 disabled:cursor-not-allowed sm:ml-auto">
              <IconoWA /> Compartir con familias{seleccion.size ? ` (${seleccion.size})` : ''}
            </button>
          </div>
          {esPrimaria && <p className="text-sm text-amber-800 -mt-2">{motivoSinCompartir}: la tabla general y el reporte del curso leen calificaciones de Secundaria.</p>}
          {!esPrimaria && !seleccion.size && totalEst > 0 && <p className="text-xs text-gray-500 -mt-2">Sin selección, «Compartir con familias» recorre todo el curso, una familia por vez.</p>}

          <div className="bg-white rounded-xl border shadow-sm grid grid-cols-1 sm:grid-cols-3 divide-y sm:divide-y-0 sm:divide-x">
            <div className="flex items-center gap-3 px-4 py-3"><Users className="text-blue-600" size={22} /><span><strong className="text-xl">{totalEst}</strong> estudiantes</span></div>
            <div className="flex items-center gap-3 px-4 py-3"><CheckCircle2 className="text-green-600" size={22} /><span><strong className="text-xl">{totalEst - conPendientes}</strong> reportes completos</span></div>
            <div className="flex items-center gap-3 px-4 py-3"><AlertCircle className="text-amber-500" size={22} /><span><strong className="text-xl">{conPendientes}</strong> con notas pendientes</span></div>
          </div>

          <div className="bg-gray-50 border border-gray-200 rounded-lg px-4 py-2.5 text-xs text-gray-600 flex items-start gap-2">
            <Info size={16} className="shrink-0" />
            <span>Todo en esta pantalla corresponde al <strong>Periodo {periodo}</strong>: la tabla, las estadísticas y los reportes. «Nota pendiente» es informativo: el reporte se puede descargar o compartir igual y muestra «Sin nota» en esas materias.</span>
          </div>
        </>
      )}

      {vista === 'pc' && stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <div className="bg-white rounded-lg border p-3 text-center"><p className="text-2xl font-bold text-blue-600">{stats.avg}</p><p className="text-xs text-gray-500">Promedio General</p></div>
          <div className="bg-white rounded-lg border p-3 text-center"><p className="text-2xl font-bold text-emerald-600">{stats.aprobados}</p><p className="text-xs text-gray-500">Aprobados (&ge;70)</p></div>
          <div className="bg-white rounded-lg border p-3 text-center"><p className="text-2xl font-bold text-red-600">{stats.reprobados}</p><p className="text-xs text-gray-500">Reprobados (&lt;70)</p></div>
          <div className="bg-white rounded-lg border p-3 text-center"><p className="text-2xl font-bold text-gray-700">{stats.max}</p><p className="text-xs text-gray-500">Nota Mas Alta</p></div>
          <div className="bg-white rounded-lg border p-3 text-center"><p className="text-2xl font-bold text-gray-700">{stats.min}</p><p className="text-xs text-gray-500">Nota Mas Baja</p></div>
        </div>
      )}

      {vista === 'pc' && data && (
        <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
          <div className="px-4 py-3 border-b bg-gray-50">
            <h2 className="text-base font-bold text-gray-900">{data.curso} — Periodo {data.periodo}</h2>
            <p className="text-gray-600 text-xs">{data.estudiantes.length} estudiantes · {data.asignaturas_nombres.length} {data.asignaturas_nombres.length === 1 ? 'asignatura' : 'asignaturas'} · cada celda = {REGLA_NOTA_PERIODO[data.nivel === 'primaria' ? 'primaria' : 'secundaria']} · Prom. = promedio de esas notas</p>
          </div>

          {/* Escritorio y tableta: tabla */}
          <div className="hidden md:block overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b">
                  <th className="p-2 pl-4 w-10"><input type="checkbox" aria-label="Seleccionar todo el curso" checked={todosMarcados} onChange={alternarTodos} disabled={esPrimaria} className="w-4 h-4" /></th>
                  <th className="text-left p-2 font-medium text-gray-600 cursor-pointer hover:bg-gray-100 whitespace-nowrap" onClick={() => toggleOrden('no_lista')}><span className="flex items-center gap-1">Nº <SortIcon col="no_lista" /></span></th>
                  <th className="text-left p-2 font-medium text-gray-600 cursor-pointer hover:bg-gray-100 whitespace-nowrap min-w-[180px]" onClick={() => toggleOrden('nombre')}><span className="flex items-center gap-1">Estudiante <SortIcon col="nombre" /></span></th>
                  {data.asignaturas_nombres.map(asig => (
                    <th key={asig} title={asig} className="text-center p-2 font-medium text-gray-600 cursor-pointer hover:bg-gray-100 whitespace-nowrap" onClick={() => toggleOrden(asig)}>
                      <span className="flex items-center justify-center gap-1 text-xs">{asig.length > 12 ? asig.substring(0, 12) + '.' : asig}<SortIcon col={asig} /></span>
                    </th>
                  ))}
                  {data.asignaturas_nombres.length > 1 && (
                    <th className="text-center p-2 font-bold text-gray-700 cursor-pointer hover:bg-gray-100 whitespace-nowrap bg-blue-50" onClick={() => toggleOrden('promedio')}><span className="flex items-center justify-center gap-1">Prom.<SortIcon col="promedio" /></span></th>
                  )}
                  <th className="text-left p-2 font-medium text-gray-600 whitespace-nowrap">Estado</th>
                  <th className="text-center p-2 pr-4 font-medium text-gray-600 whitespace-nowrap sticky right-0 bg-gray-50 shadow-[-6px_0_6px_-6px_rgba(0,0,0,0.25)]">Acciones</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {estudiantesOrdenados.map((est) => (
                  <tr key={est.estudiante_id} className={`hover:bg-gray-50 ${seleccion.has(est.estudiante_id) ? 'bg-blue-50/40' : ''}`}>
                    <td className="p-2 pl-4"><input type="checkbox" aria-label={`Seleccionar a ${est.nombre}`} checked={seleccion.has(est.estudiante_id)} onChange={() => alternar(est.estudiante_id)} disabled={esPrimaria} className="w-4 h-4" /></td>
                    <td className="p-2 text-gray-500 text-center">{est.no_lista}</td>
                    <td className="p-2 font-medium text-gray-800 min-w-[180px]"><span className="block">{est.nombre}</span>{(est.avisos || []).length > 0 && (<span className="block text-[10px] font-normal text-indigo-700 whitespace-normal">{(est.avisos || []).join(' · ')}</span>)}</td>
                    {data.asignaturas_nombres.map(asig => {
                      const nota = est.asignaturas[asig];
                      return (<td key={asig} className={`p-2 text-center ${getBgNota(nota)}`}><span className={`text-sm ${getColorNota(nota)}`}>{nota === null || nota === undefined ? <span className="text-amber-500">—</span> : fmtNota(nota)}</span></td>);
                    })}
                    {data.asignaturas_nombres.length > 1 && (
                      <td className="p-2 text-center bg-blue-50"><span className={`text-sm font-bold ${getColorNota(est.promedio)}`}>{est.promedio !== null ? est.promedio.toFixed(1) : '-'}</span></td>
                    )}
                    <td className="p-2"><ChipEstado pendientes={pendientesDe(est)} /></td>
                    <td className={`p-2 pr-4 sticky right-0 shadow-[-6px_0_6px_-6px_rgba(0,0,0,0.25)] ${seleccion.has(est.estudiante_id) ? 'bg-blue-50' : 'bg-white'}`}>
                      <div className="flex items-center justify-center gap-2">
                        <button onClick={() => descargarReportePadresIndividual(est.estudiante_id, est.nombre)} disabled={descargandoEst === est.estudiante_id}
                          title={`Reporte del Período ${periodo} de ${est.nombre} (PDF)`}
                          className="inline-flex items-center gap-1 rounded-md border border-blue-600 text-blue-700 px-2 py-1 text-xs font-semibold hover:bg-blue-50 disabled:opacity-50">
                          <FileText size={14} /> {descargandoEst === est.estudiante_id ? '…' : 'PDF'}
                        </button>
                        <button onClick={() => abrirCompartir(est.estudiante_id)} disabled={esPrimaria}
                          title={motivoSinCompartir || `Compartir el reporte de ${est.nombre} por WhatsApp`} aria-label={`Compartir el reporte de ${est.nombre} por WhatsApp`}
                          className="inline-flex items-center justify-center rounded-md border border-green-700 text-green-700 p-1.5 hover:bg-green-50 disabled:opacity-40">
                          <IconoWA size={16} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Teléfono: tarjetas, sin cortar nombres ni botones */}
          <div className="md:hidden">
            <label className="flex items-center gap-3 px-4 py-3 border-b bg-gray-50 text-sm font-medium text-gray-700">
              <input type="checkbox" checked={todosMarcados} onChange={alternarTodos} disabled={esPrimaria} className="w-5 h-5" /> Seleccionar todo el curso
            </label>
            <ul className="divide-y">
              {estudiantesOrdenados.map(est => (
                <li key={est.estudiante_id} className={`px-4 py-3 ${seleccion.has(est.estudiante_id) ? 'bg-blue-50/40' : ''}`}>
                  <div className="flex items-start gap-3">
                    <input type="checkbox" aria-label={`Seleccionar a ${est.nombre}`} checked={seleccion.has(est.estudiante_id)} onChange={() => alternar(est.estudiante_id)} disabled={esPrimaria} className="w-5 h-5 mt-0.5" />
                    <div className="flex-1 min-w-0">
                      <p className="font-semibold text-gray-900 break-words"><span className="text-gray-500 font-normal mr-1">{est.no_lista}.</span>{est.nombre}</p>
                      {(est.avisos || []).length > 0 && <p className="text-[11px] text-indigo-700">{(est.avisos || []).join(' · ')}</p>}
                      <div className="mt-1"><ChipEstado pendientes={pendientesDe(est)} /></div>
                      <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-sm">
                        {data.asignaturas_nombres.map(asig => (
                          <div key={asig} className="flex justify-between gap-2 min-w-0">
                            <dt className="text-gray-600 break-words">{asig}</dt>
                            <dd className={`shrink-0 ${getColorNota(est.asignaturas[asig])}`}>{est.asignaturas[asig] === null || est.asignaturas[asig] === undefined ? '—' : fmtNota(est.asignaturas[asig])}</dd>
                          </div>
                        ))}
                        {data.asignaturas_nombres.length > 1 && (
                          <div className="flex justify-between gap-2 font-bold"><dt>Prom.</dt><dd className={getColorNota(est.promedio)}>{est.promedio !== null ? est.promedio.toFixed(1) : '-'}</dd></div>
                        )}
                      </dl>
                      <div className="mt-3 grid grid-cols-2 gap-2">
                        <button onClick={() => descargarReportePadresIndividual(est.estudiante_id, est.nombre)} disabled={descargandoEst === est.estudiante_id}
                          className="inline-flex items-center justify-center gap-1 rounded-lg border border-blue-600 text-blue-700 py-2 text-sm font-semibold disabled:opacity-50">
                          <FileText size={16} /> {descargandoEst === est.estudiante_id ? 'Generando…' : 'PDF'}
                        </button>
                        <button onClick={() => abrirCompartir(est.estudiante_id)} disabled={esPrimaria}
                          className="inline-flex items-center justify-center gap-1 rounded-lg border border-green-700 text-green-700 py-2 text-sm font-semibold disabled:opacity-40">
                          <IconoWA size={16} /> WhatsApp
                        </button>
                      </div>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </div>
          <p className="flex items-center gap-2 px-4 py-3 border-t text-sm text-gray-600"><Info size={16} /> Las descargas actuales se mantienen.</p>
        </div>
      )}

      {panel && consulta && (
        <CompartirFamiliasPanel key={panel.ids.join(',')} cursoId={consulta.cursoId} periodo={consulta.periodo}
          estudianteIds={panel.ids} onCerrar={() => setPanel(null)} />
      )}

      {vista === 'competencias' && compData && (
        <>
          <div className="bg-white rounded-xl border shadow-sm p-4">
            <label className="block text-sm font-medium text-gray-700 mb-2">Asignatura a desglosar:</label>
            <div className="flex flex-wrap gap-2">
              {compData.asignaturas_nombres.map(asig => (
                <button key={asig} onClick={() => setAsignaturaSel(asig)}
                  className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${asignaturaSel === asig ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}>
                  {asig}
                </button>
              ))}
            </div>
          </div>

          <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
            <div className="p-4 bg-gradient-to-r from-indigo-600 to-indigo-700 text-white">
              <h2 className="text-lg font-bold">{compData.curso} - {asignaturaSel} - Periodo {compData.periodo}</h2>
              <p className="text-indigo-100 text-sm">Desglose de las 4 competencias y la nota del período (último P registrado)</p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 border-b">
                    <th className="text-left p-2 font-medium text-gray-600 whitespace-nowrap">#</th>
                    <th className="text-left p-2 font-medium text-gray-600 whitespace-nowrap min-w-[160px]">Estudiante</th>
                    <th className="text-center p-2 font-medium text-gray-600 whitespace-nowrap">Comp. 1</th>
                    <th className="text-center p-2 font-medium text-gray-600 whitespace-nowrap">Comp. 2</th>
                    <th className="text-center p-2 font-medium text-gray-600 whitespace-nowrap">Comp. 3</th>
                    <th className="text-center p-2 font-medium text-gray-600 whitespace-nowrap">Comp. 4</th>
                    <th className="text-center p-2 font-bold text-gray-700 whitespace-nowrap bg-indigo-50">Nota P{compData.periodo}<span className="block text-[9px] font-normal text-gray-500">(último P)</span></th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {compData.estudiantes.map((est) => {
                    const asig = est.asignaturas.find(a => a.asignatura === asignaturaSel);
                    if (!asig) return null;
                    return (
                      <tr key={est.estudiante_id} className="hover:bg-gray-50">
                        <td className="p-2 text-gray-500 text-center">{est.no_lista}</td>
                        <td className="p-2 font-medium text-gray-800 max-w-[200px]"><span className="block truncate">{est.nombre}</span>{(est.avisos || []).length > 0 && (<span className="block text-[10px] font-normal text-indigo-700 whitespace-normal">{(est.avisos || []).join(' · ')}</span>)}</td>
                        {asig.competencias.map(cv => (
                          <td key={cv.competencia} className={`p-2 text-center ${getBgNota(cv.valor)}`}>
                            <span className={`text-sm ${getColorNota(cv.valor)}`}>{fmtNota(cv.valor)}</span>
                          </td>
                        ))}
                        <td className="p-2 text-center bg-indigo-50">
                          <span className={`text-sm font-bold ${getColorNota(asig.ultimo_p)}`}>{fmtNota(asig.ultimo_p)}</span>
                          {asig.pc !== null && <span className="block text-[9px] text-gray-500">prom {asig.pc.toFixed(1)}</span>}
                          {!asig.completo && asig.ultimo_p !== null && <span className="block text-[9px] text-amber-500">parcial</span>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="p-3 bg-gray-50 border-t text-xs text-gray-500">
              <strong>Nota P{compData.periodo}</strong> = último P registrado del periodo (competencia más alta con valor) — la nota que se entrega a los padres. <em>prom</em> = promedio de las 4 competencias, como referencia.
              "parcial" indica que aún no están las 4 competencias cargadas: la nota del período es la de la última competencia con dato.
            </div>
          </div>
        </>
      )}

      {!data && !compData && !loading && (
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-6">
          <h3 className="font-semibold text-blue-800 mb-2">Sobre esta vista</h3>
          <p className="text-blue-700 text-sm mb-2">Selecciona un curso y periodo, luego "Ver Notas".</p>
          <ul className="text-blue-700 text-sm list-disc list-inside space-y-1">
            <li><strong>Vista Nota del Período (resumen):</strong> la nota del período elegido en cada asignatura. «Prom.» es el promedio de esas notas.
              <ul className="list-[circle] list-inside ml-5">
                <li><strong>Secundaria:</strong> el último P registrado (la competencia más alta con valor; un 0 cuenta como nota; con recuperación, el mayor entre P y RP). Aquí descargas la tabla general y el Reporte del Período para padres, individual o de todo el curso: los tres muestran las mismas notas.</li>
                <li><strong>Primaria:</strong> el promedio de sus competencias en el período (si hubo recuperación, cuenta la RP en lugar de la P).</li>
              </ul>
            </li>
            <li><strong>Vista por Competencia (Secundaria):</strong> eliges una asignatura y ves el valor de cada una de las 4 competencias en el período y de cuál sale la nota del período.</li>
          </ul>
        </div>
      )}
    </div>
  );
};

export default CalificacionesGeneralPage;
