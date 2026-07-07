import { useState, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';
import { FileBarChart, Download, Search, ChevronDown, ChevronUp, LayoutGrid, List, Users, User } from 'lucide-react';
import { Select, Button, Alert } from '../../components/ui';

interface Curso { id: number; nombre_completo: string; grado?: string; nombre?: string; tanda?: string; }

interface NotaPeriodo {
  estudiante_id: number; nombre: string; no_lista: number;
  asignaturas: Record<string, number | null>; promedio: number | null;
}
interface ReporteData {
  curso: string; periodo: number;
  asignaturas_nombres: string[]; estudiantes: NotaPeriodo[];
}

interface CompetenciaValor { competencia: number; valor: number | null; }
interface AsigCompetencias {
  asignatura_id: number; asignatura: string;
  competencias: CompetenciaValor[]; pc: number | null; ultimo_p: number | null; completo: boolean;
}
interface EstCompetencias {
  estudiante_id: number; no_lista: number; nombre: string;
  asignaturas: AsigCompetencias[];
}
interface CompetenciasData {
  curso: string; periodo: number; ano_escolar: string;
  asignaturas_nombres: string[]; estudiantes: EstCompetencias[];
}

type Vista = 'pc' | 'competencias';

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

  useEffect(() => { cargarCursos(); }, []);

  const cargarCursos = async () => {
    try { const res = await api.get('/cursos'); setCursos(res.data || []); }
    catch { setError('Error al cargar cursos'); }
  };

  const cargar = async () => {
    if (!cursoId) return;
    setLoading(true); setError(''); setData(null); setCompData(null);
    try {
      if (vista === 'pc') {
        const res = await api.get(`/calificaciones/por-periodo?curso_id=${cursoId}&periodo=${periodo}`);
        setData(res.data);
      } else {
        const res = await api.get(`/calificaciones-secundaria/curso/${cursoId}/periodo/${periodo}/competencias`);
        setCompData(res.data);
        if (res.data.asignaturas_nombres?.length && !asignaturaSel) {
          setAsignaturaSel(res.data.asignaturas_nombres[0]);
        }
      }
    } catch (err: any) { setError(err.response?.data?.error || 'Error al cargar notas'); }
    finally { setLoading(false); }
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
    try { await descargarBlob(`/calificaciones/por-periodo/pdf?curso_id=${cursoId}&periodo=${periodo}`, `Notas_P${periodo}_${nombreCurso()}.pdf`); }
    catch (e: any) { setError(e.message || 'Error al descargar PDF'); }
  };

  const descargarReportePadresCurso = async () => {
    if (!cursoId) return;
    setDescargandoPadres(true); setError('');
    try {
      await descargarBlob(
        `/calificaciones-secundaria/reporte-padres/curso/${cursoId}/pdf?periodo=${periodo}`,
        `Reporte_Periodo${periodo}_Curso_${nombreCurso()}.pdf`
      );
    } catch (e: any) { setError(e.message || 'Error al generar reporte'); }
    finally { setDescargandoPadres(false); }
  };

  const descargarReportePadresIndividual = async (estId: number, nombre: string) => {
    if (!cursoId) return;
    try {
      await descargarBlob(
        `/calificaciones-secundaria/reporte-padres/curso/${cursoId}/pdf?periodo=${periodo}&estudiante_id=${estId}`,
        `Reporte_Periodo${periodo}_${nombre.replace(/\s+/g, '_')}.pdf`
      );
    } catch (e: any) { setError(e.message || 'Error al generar reporte individual'); }
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

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2"><FileBarChart className="text-blue-600" /> Notas por Periodo</h1>
        <p className="text-gray-500 mt-1">Reporte de calificaciones por periodo. Vista por PC o desglose por competencia.</p>
      </div>

      {error && <Alert variant="error" onClose={() => setError('')}>{error}</Alert>}

      <div className="flex items-center gap-1 bg-gray-100 rounded-lg p-1 w-fit">
        <button onClick={() => { setVista('pc'); setData(null); setCompData(null); }}
          className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${vista === 'pc' ? 'bg-white text-blue-700 shadow-sm' : 'text-gray-600 hover:text-gray-800'}`}>
          <List size={16} /> Vista Promedios (resumen)
        </button>
        <button onClick={() => { setVista('competencias'); setData(null); setCompData(null); }}
          className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${vista === 'competencias' ? 'bg-white text-blue-700 shadow-sm' : 'text-gray-600 hover:text-gray-800'}`}>
          <LayoutGrid size={16} /> Vista por Competencia
        </button>
      </div>

      <div className="bg-white rounded-xl border shadow-sm p-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <Select label="Curso" value={cursoId.toString()} onChange={e => setCursoId(Number(e.target.value))} options={cursos.map(c => ({ value: c.id, label: c.grado ? `${c.grado} ${c.nombre}` : c.nombre_completo, group: c.tanda || 'Sin tanda' }))} placeholder="Seleccionar curso" />
          <Select label="Periodo" value={periodo.toString()} onChange={e => setPeriodo(Number(e.target.value))} options={periodoOpts} />
          <div className="flex items-end"><Button onClick={cargar} disabled={!cursoId} loading={loading} icon={<Search size={18} />} className="w-full">Ver Notas</Button></div>
        </div>

        {vista === 'pc' && data && (
          <div className="mt-3 pt-3 border-t border-gray-100">
            <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
              <div>
                <p className="text-[11px] font-medium text-gray-600 mb-1.5">Descargar tabla completa</p>
                <Button onClick={descargarPDF} variant="secondary" icon={<Download size={16} />} className="text-xs">Tabla general (PDF)</Button>
                <p className="text-[9px] text-gray-400 mt-0.5">Todas las asignaturas del periodo</p>
              </div>
              <div className="border-l border-gray-200 pl-6">
                <p className="text-[11px] font-medium text-gray-600 mb-1.5">Reporte del Período para padres</p>
                <Button onClick={descargarReportePadresCurso} variant="primary" loading={descargandoPadres} icon={<Users size={16} />} className="text-xs">Reporte del Período {periodo} (curso)</Button>
                <p className="text-[9px] text-gray-400 mt-0.5">Un reporte por estudiante con la nota del período (último P registrado) por asignatura</p>
              </div>
            </div>
          </div>
        )}
      </div>

      {vista === 'pc' && data && (
        <div className="bg-gray-50 border border-gray-200 rounded-lg px-4 py-2.5 text-xs text-gray-600 flex items-center gap-2">
          <span className="text-base">ℹ️</span>
          Todo en esta pantalla corresponde al <strong>Periodo {periodo}</strong>: la tabla, las estadisticas y el reporte que descargas.
        </div>
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
          <div className="p-4 bg-gradient-to-r from-blue-600 to-blue-700 text-white">
            <h2 className="text-lg font-bold">{data.curso} - Periodo {data.periodo}</h2>
            <p className="text-blue-100 text-sm">{data.estudiantes.length} estudiantes - {data.asignaturas_nombres.length} {data.asignaturas_nombres.length === 1 ? 'asignatura' : 'asignaturas'} - cada celda = promedio del periodo (promedio de las 4 competencias en ese periodo)</p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b">
                  <th className="text-left p-2 font-medium text-gray-600 cursor-pointer hover:bg-gray-100 whitespace-nowrap" onClick={() => toggleOrden('no_lista')}><span className="flex items-center gap-1"># <SortIcon col="no_lista" /></span></th>
                  <th className="text-left p-2 font-medium text-gray-600 cursor-pointer hover:bg-gray-100 whitespace-nowrap min-w-[160px]" onClick={() => toggleOrden('nombre')}><span className="flex items-center gap-1">Estudiante <SortIcon col="nombre" /></span></th>
                  {data.asignaturas_nombres.map(asig => (
                    <th key={asig} className="text-center p-2 font-medium text-gray-600 cursor-pointer hover:bg-gray-100 whitespace-nowrap" onClick={() => toggleOrden(asig)}>
                      <span className="flex items-center justify-center gap-1 text-xs">{asig.length > 12 ? asig.substring(0, 12) + '.' : asig}<SortIcon col={asig} /></span>
                    </th>
                  ))}
                  {data.asignaturas_nombres.length > 1 && (
                    <th className="text-center p-2 font-bold text-gray-700 cursor-pointer hover:bg-gray-100 whitespace-nowrap bg-blue-50" onClick={() => toggleOrden('promedio')}><span className="flex items-center justify-center gap-1">Prom.<SortIcon col="promedio" /></span></th>
                  )}
                  <th className="text-center p-2 font-medium text-gray-600 whitespace-nowrap">Reporte</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {estudiantesOrdenados.map((est) => (
                  <tr key={est.estudiante_id} className="hover:bg-gray-50">
                    <td className="p-2 text-gray-500 text-center">{est.no_lista}</td>
                    <td className="p-2 font-medium text-gray-800 truncate max-w-[200px]">{est.nombre}</td>
                    {data.asignaturas_nombres.map(asig => {
                      const nota = est.asignaturas[asig];
                      return (<td key={asig} className={`p-2 text-center ${getBgNota(nota)}`}><span className={`text-sm ${getColorNota(nota)}`}>{nota !== null && nota !== undefined ? Math.round(nota) : '-'}</span></td>);
                    })}
                    {data.asignaturas_nombres.length > 1 && (
                      <td className="p-2 text-center bg-blue-50"><span className={`text-sm font-bold ${getColorNota(est.promedio)}`}>{est.promedio !== null ? est.promedio.toFixed(1) : '-'}</span></td>
                    )}
                    <td className="p-2 text-center">
                      <button onClick={() => descargarReportePadresIndividual(est.estudiante_id, est.nombre)} title={`Reporte del Período ${periodo} de este estudiante`} className="inline-flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 hover:underline">
                        <User size={12} /> PDF
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
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
              <p className="text-indigo-100 text-sm">Desglose de las 4 competencias y el PC resultante (PC = promedio de las competencias)</p>
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
                        <td className="p-2 font-medium text-gray-800 truncate max-w-[200px]">{est.nombre}</td>
                        {asig.competencias.map(cv => (
                          <td key={cv.competencia} className={`p-2 text-center ${getBgNota(cv.valor)}`}>
                            <span className={`text-sm ${getColorNota(cv.valor)}`}>{cv.valor !== null ? Math.round(cv.valor) : '-'}</span>
                          </td>
                        ))}
                        <td className="p-2 text-center bg-indigo-50">
                          <span className={`text-sm font-bold ${getColorNota(asig.ultimo_p)}`}>{asig.ultimo_p !== null ? Math.round(asig.ultimo_p) : '-'}</span>
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
              "parcial" indica que aun no estan las 4 competencias cargadas (el PC mostrado es provisional).
            </div>
          </div>
        </>
      )}

      {!data && !compData && !loading && (
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-6">
          <h3 className="font-semibold text-blue-800 mb-2">Sobre esta vista</h3>
          <p className="text-blue-700 text-sm mb-2">Selecciona un curso y periodo, luego "Ver Notas".</p>
          <ul className="text-blue-700 text-sm list-disc list-inside space-y-1">
            <li><strong>Vista Promedios (resumen):</strong> el promedio de cada asignatura en el periodo elegido (promedio de sus 4 competencias) + promedio general. Aca descargas el reporte de calificaciones, individual o de todo el curso.</li>
            <li><strong>Vista por Competencia:</strong> eliges una asignatura y ves como se forma el PC - el valor de cada una de las 4 competencias en el periodo.</li>
            <li><strong>Reporte por competencia:</strong> eleg\u00ed la <strong>Competencia</strong> que se trabaja (1-4) y la nota a usar: "PC" (promedio de los 4 P de esa competencia) o "\u00daltimo P" (el P4). Sirve para reportar antes del cierre y dar tiempo de recuperaci\u00f3n. El PDF dice solo "Competencia N" \u2014 el padre no ve si es PC o P4. Sale con el logo del colegio.</li>
          </ul>
        </div>
      )}
    </div>
  );
};

export default CalificacionesGeneralPage;
