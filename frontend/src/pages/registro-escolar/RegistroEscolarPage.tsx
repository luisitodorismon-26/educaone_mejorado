import { useEffect, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';

interface ValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
  info: Record<string, unknown>;
}

interface CursoInfo {
  id: number;
  nombre_completo: string;
  grado: string | null;
  seccion: string;
  tanda: string | null;
}

interface AnoEscolarInfo {
  id: number | null;
  nombre: string | null;
  fecha_inicio: string | null;
  fecha_fin: string | null;
  periodo_activo: number | null;
  dias_trabajados: Record<string, number>;
}

interface CentroInfo {
  nombre: string | null;
  regional: string | null;
  distrito: string | null;
  codigo_centro: string | null;
  codigo_cartografia: string | null;
  direccion: string | null;
  telefono: string | null;
  email: string | null;
}

interface DirectorGrupoInfo {
  id: number;
  nombre_completo: string;
}

interface EstudiantePreview {
  id: number;
  no_lista: number;
  nombre_completo: string;
  sexo: string | null;
  fecha_nacimiento: string | null;
  matricula: string | null;
}

interface AsignaturaPreview {
  asignatura_id: number;
  asignatura_nombre: string;
  profesor_id: number;
  profesor_nombre: string;
  es_titular: boolean;
  calificaciones_registradas: number;
  estudiantes_del_curso: number;
  falta_por_calificar: number;
}

interface AsistenciaFila {
  no: number;
  estudiante_id: number;
  nombre: string;
  valores: string[];
  presentes: number;
  ausentes: number;
  porcentaje: number;
}

interface AsistenciaMes {
  mes: string;
  mes_num: number;
  dias: number[];
  total_dias: number;
  filas: AsistenciaFila[];
}

interface PreviewData {
  validacion: ValidationResult;
  nivel: string;
  grado_numero: number;
  curso: CursoInfo;
  ano_escolar: AnoEscolarInfo;
  centro: CentroInfo;
  director_grupo: DirectorGrupoInfo | null;
  estudiantes: {
    total: number;
    lista: EstudiantePreview[];
  };
  asignaturas: AsignaturaPreview[];
  asistencia: {
    total_registros: number;
    matriz_por_mes: AsistenciaMes[];
    debug_texto: string;
    meses_con_registro: number;
  };
  resumen: {
    curso_listo_para_generar: boolean;
    estudiantes: number;
    asignaturas_configuradas: number;
    asignaturas_con_faltantes: number;
    dias_trabajados_configurados_total: number;
    meses_asistencia_detectados: number;
  };
}

const formatMeses = (dias: Record<string, number>) =>
  Object.entries(dias || {})
    .filter(([, valor]) => typeof valor === 'number' && valor > 0)
    .map(([mes, valor]) => `${mes.toUpperCase()}: ${valor}`)
    .join(' • ');

export const RegistroEscolarPage = () => {
  const { user } = useAuth();
  const [cursos, setCursos] = useState<any[]>([]);
  const [cursoId, setCursoId] = useState<number>(0);
  const [preview, setPreview] = useState<PreviewData | null>(null);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  useEffect(() => {
    cargarCursos();
  }, []);

  const cargarCursos = async () => {
    try {
      const res = await api.get('/cursos');
      setCursos(res.data || []);
    } catch {
      setError('Error al cargar cursos');
    }
  };

  const cargarPreview = async () => {
    if (!cursoId) return;

    setLoading(true);
    setError('');
    setSuccess('');
    setPreview(null);

    try {
      const res = await api.get(`/registros/preview/${cursoId}`);
      setPreview(res.data);
    } catch (err: any) {
      setError(err.response?.data?.error || 'Error al cargar vista previa del registro');
    } finally {
      setLoading(false);
    }
  };

  const generarPDF = async () => {
    if (!cursoId || !preview) return;

    setGenerating(true);
    setError('');
    setSuccess('');

    try {
      const response = await api.get(`/registros/${preview.nivel}/${cursoId}`, {
        responseType: 'blob'
      });

      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `Registro_${preview.curso.nombre_completo}.pdf`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);

      setSuccess('Registro generado exitosamente');
    } catch (err: any) {
      const blob = err?.response?.data;
      if (blob instanceof Blob) {
        const text = await blob.text();
        try {
          const parsed = JSON.parse(text);
          const detalle = parsed.detalle?.join?.(' | ');
          setError(parsed.error ? `${parsed.error}${detalle ? `: ${detalle}` : ''}` : 'Error al generar el PDF');
        } catch {
          setError('Error al generar el PDF');
        }
      } else {
        setError(err.response?.data?.error || 'Error al generar el PDF');
      }
    } finally {
      setGenerating(false);
    }
  };

  const generarVistaPrevia = async () => {
    if (!cursoId || !preview) return;

    setGenerating(true);
    setError('');
    setSuccess('');

    try {
      const response = await api.get(`/registros/${preview.nivel}/${cursoId}/preview-pdf`, {
        responseType: 'blob'
      });

      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `BORRADOR_${preview.curso.nombre_completo}.pdf`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);

      setSuccess('Vista previa (BORRADOR) generada — no apta para entrega oficial');
    } catch (err: any) {
      const blob = err?.response?.data;
      if (blob instanceof Blob) {
        const text = await blob.text();
        try {
          const parsed = JSON.parse(text);
          setError(parsed.error || 'Error al generar la vista previa');
        } catch {
          setError('Error al generar la vista previa');
        }
      } else {
        setError(err.response?.data?.error || 'Error al generar la vista previa');
      }
    } finally {
      setGenerating(false);
    }
  };

  // v2.17 FIX: el SUPERADMIN quedaba fuera y no veía ningún botón (el backend
  // sí lo acepta: RolesRequired trata 'superadmin' como rol que siempre pasa).
  // Además se separa la VISTA PREVIA (borrador, para revisar avance — también
  // el profesor de sus cursos) del REGISTRO OFICIAL (lo firma la dirección).
  const canPreview = ['direccion', 'coordinador', 'superadmin', 'profesor'].includes(user?.role || '');
  const canGenerate = ['direccion', 'coordinador', 'superadmin'].includes(user?.role || '');
  const isBlocked = preview ? !preview.validacion.valid : false;

  return (
    <div className="p-4 space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">Registro Escolar MINERD</h1>
        <p className="text-gray-500 mt-1">
          Diagnostica, valida y genera el registro oficial usando el flujo productivo del sistema.
        </p>
      </div>

      {error && (
        <div className="p-3 bg-red-100 border border-red-300 text-red-700 rounded-lg flex justify-between gap-3">
          <span>{error}</span>
          <button onClick={() => setError('')} className="font-bold">×</button>
        </div>
      )}

      {success && (
        <div className="p-3 bg-green-100 border border-green-300 text-green-700 rounded-lg">
          {success}
        </div>
      )}

      <div className="bg-white rounded-xl border shadow-sm p-6">
        <h2 className="text-lg font-semibold mb-4">Seleccionar Curso</h2>

        <div className="flex gap-4 items-end">
          <div className="flex-1">
            <label className="block text-sm font-medium mb-1">Curso</label>
            <select
              value={cursoId}
              onChange={(e) => setCursoId(Number(e.target.value))}
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
            >
              <option value={0}>-- Seleccionar curso --</option>
              {(() => {
                const tandas = [...new Set(cursos.map((c) => c.tanda || 'Sin tanda'))];
                return tandas.map((t) => (
                  <optgroup key={t} label={t}>
                    {cursos
                      .filter((c) => (c.tanda || 'Sin tanda') === t)
                      .map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.grado ? `${c.grado} ${c.nombre}` : c.nombre_completo}
                        </option>
                      ))}
                  </optgroup>
                ));
              })()}
            </select>
          </div>

          <button
            onClick={cargarPreview}
            disabled={!cursoId || loading}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? 'Cargando...' : 'Diagnosticar'}
          </button>
        </div>
      </div>

      {preview && (
        <div className="space-y-4">
          <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
            <div className="p-6 bg-gradient-to-r from-blue-700 to-slate-800 text-white">
              <h2 className="text-xl font-bold">{preview.curso.nombre_completo}</h2>
              <p className="text-blue-100 mt-1">
                {preview.curso.grado || 'Sin grado'} • {preview.nivel.toUpperCase()} • Año escolar: {preview.ano_escolar.nombre || 'No definido'}
              </p>
            </div>

            <div className="p-6 border-b space-y-4">
              <h3 className="font-semibold text-gray-700">Estado de Generación</h3>

              <div className="grid md:grid-cols-5 gap-4">
                <div className="bg-slate-50 p-4 rounded-lg">
                  <div className="text-xs uppercase text-slate-500">Estado</div>
                  <div className={`text-xl font-bold mt-1 ${isBlocked ? 'text-red-600' : 'text-green-600'}`}>
                    {isBlocked ? 'Bloqueado' : 'Listo'}
                  </div>
                </div>
                <div className="bg-slate-50 p-4 rounded-lg">
                  <div className="text-xs uppercase text-slate-500">Errores</div>
                  <div className="text-xl font-bold mt-1 text-red-600">{preview.validacion.errors.length}</div>
                </div>
                <div className="bg-slate-50 p-4 rounded-lg">
                  <div className="text-xs uppercase text-slate-500">Warnings</div>
                  <div className="text-xl font-bold mt-1 text-amber-600">{preview.validacion.warnings.length}</div>
                </div>
                <div className="bg-slate-50 p-4 rounded-lg">
                  <div className="text-xs uppercase text-slate-500">Asignaturas</div>
                  <div className="text-xl font-bold mt-1 text-slate-800">{preview.resumen.asignaturas_configuradas}</div>
                </div>
                <div className="bg-slate-50 p-4 rounded-lg">
                  <div className="text-xs uppercase text-slate-500">Asistencia</div>
                  <div className="text-xl font-bold mt-1 text-slate-800">{preview.asistencia.total_registros}</div>
                </div>
              </div>

              {preview.validacion.errors.length > 0 && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                  <h4 className="font-medium text-red-800 mb-2">Errores bloqueantes</h4>
                  <ul className="space-y-1 text-sm text-red-700">
                    {preview.validacion.errors.map((item, index) => (
                      <li key={index}>• {item}</li>
                    ))}
                  </ul>
                </div>
              )}

              {preview.validacion.warnings.length > 0 && (
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
                  <h4 className="font-medium text-amber-800 mb-2">Advertencias</h4>
                  <ul className="space-y-1 text-sm text-amber-700">
                    {preview.validacion.warnings.map((item, index) => (
                      <li key={index}>• {item}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            <div className="p-6 border-b space-y-4">
              <h3 className="font-semibold text-gray-700">Contexto del Registro</h3>

              <div className="grid md:grid-cols-2 gap-4 text-sm">
                <div className="bg-gray-50 rounded-lg p-4 space-y-2">
                  <div><span className="font-medium">Centro:</span> {preview.centro.nombre || 'No configurado'}</div>
                  <div><span className="font-medium">Regional / Distrito:</span> {preview.centro.regional || '-'} / {preview.centro.distrito || '-'}</div>
                  <div><span className="font-medium">Codigo SIGERD:</span> {preview.centro.codigo_centro || '-'}</div>
                  <div><span className="font-medium">Director de grupo:</span> {preview.director_grupo?.nombre_completo || 'No asignado'}</div>
                </div>
                <div className="bg-gray-50 rounded-lg p-4 space-y-2">
                  <div><span className="font-medium">Estudiantes:</span> {preview.estudiantes.total}</div>
                  <div><span className="font-medium">Meses con asistencia:</span> {preview.resumen.meses_asistencia_detectados}</div>
                  <div><span className="font-medium">Dias trabajados configurados:</span> {preview.resumen.dias_trabajados_configurados_total}</div>
                  <div><span className="font-medium">Detalle por mes:</span> {formatMeses(preview.ano_escolar.dias_trabajados) || 'Sin configurar'}</div>
                </div>
              </div>
            </div>

            <div className="p-6 border-b space-y-4">
              <h3 className="font-semibold text-gray-700">Asignaturas y Cobertura</h3>

              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-gray-50">
                      <th className="text-left py-3 px-4 font-medium text-gray-600">Asignatura</th>
                      <th className="text-left py-3 px-4 font-medium text-gray-600">Profesor</th>
                      <th className="text-center py-3 px-4 font-medium text-gray-600">Registradas</th>
                      <th className="text-center py-3 px-4 font-medium text-gray-600">Faltantes</th>
                      <th className="text-center py-3 px-4 font-medium text-gray-600">Titular</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {preview.asignaturas.map((asig) => (
                      <tr key={asig.asignatura_id} className={asig.falta_por_calificar > 0 ? 'bg-red-50' : 'hover:bg-gray-50'}>
                        <td className="py-3 px-4 font-medium">{asig.asignatura_nombre}</td>
                        <td className="py-3 px-4">{asig.profesor_nombre || 'Sin asignar'}</td>
                        <td className="py-3 px-4 text-center">{asig.calificaciones_registradas}</td>
                        <td className={`py-3 px-4 text-center font-medium ${asig.falta_por_calificar > 0 ? 'text-red-600' : 'text-green-600'}`}>
                          {asig.falta_por_calificar}
                        </td>
                        <td className="py-3 px-4 text-center">{asig.es_titular ? 'Si' : 'No'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="p-6 border-b space-y-4">
              <h3 className="font-semibold text-gray-700">Debug de Asistencia</h3>

              <div className="grid lg:grid-cols-2 gap-4">
                <div className="bg-slate-950 text-slate-100 rounded-lg p-4 overflow-auto">
                  <pre className="text-xs whitespace-pre-wrap">{preview.asistencia.debug_texto || '(sin asistencia registrada)'}</pre>
                </div>
                <div className="space-y-3">
                  {preview.asistencia.matriz_por_mes.map((mes) => (
                    <div key={mes.mes_num} className="border rounded-lg p-4 bg-gray-50">
                      <div className="font-medium text-gray-800">{mes.mes}</div>
                      <div className="text-sm text-gray-600 mt-1">
                        Dias detectados: {mes.dias.join(', ') || 'ninguno'}
                      </div>
                      <div className="text-sm text-gray-600">
                        Filas: {mes.filas.length} estudiantes
                      </div>
                    </div>
                  ))}
                  {preview.asistencia.matriz_por_mes.length === 0 && (
                    <div className="border rounded-lg p-4 bg-red-50 text-red-700">
                      No hay matriz de asistencia util para construir el registro.
                    </div>
                  )}
                </div>
              </div>
            </div>

            <div className="p-6 bg-gray-50 flex flex-col gap-4">
              <div className="text-sm text-gray-600">
                {isBlocked
                  ? '⚠ La impresión oficial está bloqueada hasta corregir los errores. Mientras tanto, puede descargar la VISTA PREVIA para revisar avance.'
                  : '✓ El curso superó las validaciones. Puede descargar el registro oficial.'}
              </div>

              {(canPreview || canGenerate) && (
                <div className="flex flex-col md:flex-row gap-3">
                  {/* Vista previa (BORRADOR) — disponible aunque haya errores:
                      su propósito es justamente ver el avance del año */}
                  {canPreview && (
                    <button
                      onClick={generarVistaPrevia}
                      disabled={generating}
                      className="flex-1 px-6 py-3 bg-amber-100 text-amber-800 border-2 border-amber-300 rounded-lg hover:bg-amber-200 disabled:opacity-50 font-medium flex items-center justify-center gap-2"
                    >
                      {generating ? 'Generando...' : `📋 Vista Previa (BORRADOR)`}
                    </button>
                  )}

                  {/* Registro oficial - solo si validación pasó */}
                  {canGenerate && (
                    <button
                      onClick={generarPDF}
                      disabled={generating || isBlocked}
                      className="flex-1 px-6 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-40 disabled:cursor-not-allowed font-medium flex items-center justify-center gap-2"
                      title={isBlocked ? 'Corrija los errores antes de imprimir el oficial' : 'Imprimir el registro oficial MINERD'}
                    >
                      {generating ? 'Generando...' : `🖨️ Imprimir Registro Oficial`}
                    </button>
                  )}
                </div>
              )}

              {!canPreview && !canGenerate && (
                <div className="text-sm text-gray-500 italic">
                  Tu rol no tiene permiso para generar el registro escolar. Puedes revisar
                  el diagnóstico de arriba; la impresión la realiza dirección o coordinación.
                </div>
              )}
              
              <div className="text-xs text-gray-500 italic">
                <strong>Vista Previa</strong>: PDF con marca de agua "BORRADOR", útil para revisar avance del año. NO usar para entrega oficial.<br/>
                <strong>Registro Oficial</strong>: PDF limpio, listo para impresión y entrega al MINERD. Solo disponible cuando todos los datos estén completos.
              </div>
            </div>
          </div>
        </div>
      )}

      {!preview && !loading && (
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-6 text-sm text-blue-800">
          Este modulo ahora usa la vista previa estructurada del registro oficial. La idea es diagnosticar primero y bloquear cualquier generacion incompleta antes de imprimir.
        </div>
      )}
    </div>
  );
};

export default RegistroEscolarPage;
