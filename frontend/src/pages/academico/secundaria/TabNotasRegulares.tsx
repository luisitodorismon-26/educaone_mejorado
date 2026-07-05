import { useState, useCallback, useMemo, Fragment } from 'react';
import api from '../../../services/api';
import { Save, ChevronDown, BookOpen, CheckCircle } from 'lucide-react';
import { Button, Alert } from '../../../components/ui';
import {
  EstudianteData, CampoEditable, CAMPOS_PERIODOS, NOMBRES_COMPETENCIAS,
  getLiteral, getNotaClass,
} from './tipos';

// ════════════════════════════════════════════════════════════════════
// TAB NOTAS REGULARES
// Selector dropdown de competencia (1-4) + tabla con 8 columnas
// editables (P1, RP1, P2, RP2, P3, RP3, P4, RP4) por estudiante.
// Las notas se guardan por competencia individual al backend.
// PC1-PC4, CF, literal: calculados en backend, solo se muestran.
// ════════════════════════════════════════════════════════════════════

interface Props {
  estudiantes: EstudianteData[];
  asignaturaId: number;
  puedeEditar: boolean;
  onReload: () => Promise<void>;
  onAbrirFicha?: (estudianteId: number) => void;
  periodosCerrados?: Record<string, boolean>;
}

type EditadasState = Record<string, Partial<Record<CampoEditable, number | null>>>;

export const TabNotasRegulares: React.FC<Props> = ({ estudiantes, asignaturaId, puedeEditar, onReload, onAbrirFicha, periodosCerrados = {} }) => {
  const [competenciaActiva, setCompetenciaActiva] = useState<number>(1);
  const [editadas, setEditadas] = useState<EditadasState>({});
  const [saving, setSaving] = useState(false);
  const [mensaje, setMensaje] = useState<{ tipo: 'success' | 'error' | 'warning'; texto: string } | null>(null);

  const keyCelda = (estId: number, compNum: number) => `${estId}-${compNum}`;

  const handleNotaChange = useCallback((estId: number, compNum: number, campo: CampoEditable, valor: string) => {
    let num: number | null;
    if (valor === '') {
      num = null;
    } else {
      const parsed = parseFloat(valor);
      if (Number.isNaN(parsed)) return;
      if (parsed < 0 || parsed > 100) return;
      num = parsed;
    }
    const k = keyCelda(estId, compNum);
    setEditadas(prev => ({
      ...prev,
      [k]: { ...(prev[k] || {}), [campo]: num },
    }));
  }, []);

  const getValor = (est: EstudianteData, compNum: number, campo: CampoEditable): number | null => {
    const k = keyCelda(est.estudiante.id, compNum);
    const ed = editadas[k];
    if (ed && campo in ed) return ed[campo] ?? null;
    const comp = est.competencias[compNum];
    if (!comp) return null;
    return comp[campo];
  };

  const calcularPromedioCompetencia = (est: EstudianteData, compNum: number): number | null => {
    const vals: number[] = [];
    for (const { p, rp } of CAMPOS_PERIODOS) {
      const pVal = getValor(est, compNum, p);
      const rpVal = getValor(est, compNum, rp);
      let efectivo: number | null = null;
      if (rpVal !== null && pVal !== null) efectivo = Math.max(pVal, rpVal);
      else if (rpVal !== null) efectivo = rpVal;
      else if (pVal !== null) efectivo = pVal;
      if (efectivo === null) return null;
      vals.push(efectivo);
    }
    return Math.round((vals.reduce((a, b) => a + b, 0) / 4) * 10) / 10;
  };

  const guardar = async () => {
    const claves = Object.keys(editadas);
    if (claves.length === 0) {
      setMensaje({ tipo: 'error', texto: 'No hay cambios por guardar' });
      return;
    }
    setSaving(true);
    let errores = 0;
    let exitos = 0;
    const mensajesError: string[] = [];
    try {
      for (const k of claves) {
        const [estIdStr, compNumStr] = k.split('-');
        const estId = parseInt(estIdStr);
        const compNum = parseInt(compNumStr);
        const cambios = editadas[k];
        try {
          await api.post('/calificaciones-secundaria', {
            estudiante_id: estId,
            asignatura_id: asignaturaId,
            competencia_numero: compNum,
            ...cambios,
          });
          exitos++;
        } catch (err: any) {
          errores++;
          const msg = err.response?.data?.error || 'Error desconocido';
          mensajesError.push(`Est ${estId} C${compNum}: ${msg}`);
        }
      }
      if (errores === 0) {
        setMensaje({ tipo: 'success', texto: `${exitos} calificación(es) guardada(s)` });
      } else if (exitos > 0) {
        setMensaje({ tipo: 'warning', texto: `${exitos} guardadas, ${errores} fallaron: ${mensajesError.slice(0, 2).join('; ')}` });
      } else {
        setMensaje({ tipo: 'error', texto: `Error al guardar: ${mensajesError.slice(0, 2).join('; ')}` });
      }
      setEditadas({});
      await onReload();
    } finally {
      setSaving(false);
    }
  };

  const renderCelda = (est: EstudianteData, compNum: number, campo: CampoEditable, isRP: boolean) => {
    const val = getValor(est, compNum, campo);
    const esRetirado = !!est.estudiante.retirado;
    const cellKey = `${est.estudiante.id}-${compNum}-${campo}`;

    // v2.13.35: ¿el período de este campo está cerrado? (p1/rp1 → 1, p2/rp2 → 2, etc.)
    const numPeriodo = campo.replace(/[^0-9]/g, '');
    const periodoCerrado = !!periodosCerrados[`p${numPeriodo}`];

    // v2.13.1: RP solo se puede editar si P del mismo período < 70 (regla MINERD oficial)
    // Calculamos el P correspondiente para saber si habilitar el RP.
    let rpDeshabilitado = false;
    if (isRP) {
      // Mapear rp1 → p1, rp2 → p2, etc.
      const pCampo = campo.replace('rp', 'p') as CampoEditable;
      const pVal = getValor(est, compNum, pCampo);
      // RP queda deshabilitado si: P no existe O P >= 70
      rpDeshabilitado = pVal === null || pVal >= 70;
    }

    // Si no puede editar, está retirado, o el período está cerrado → solo lectura
    if (!puedeEditar || esRetirado || periodoCerrado) {
      return (
        <span className={`inline-block w-16 text-center text-sm ${
          esRetirado ? (val !== null ? 'text-gray-500' : 'text-gray-300') :
          isRP ? 'text-amber-700' : 'text-gray-700'
        } ${!esRetirado ? getNotaClass(val) : ''}`}>
          {val !== null ? val.toFixed(2) : '—'}
        </span>
      );
    }
    
    // Si es RP y está deshabilitado, mostrar input gris no editable con tooltip
    if (isRP && rpDeshabilitado) {
      const pCampo = campo.replace('rp', 'p') as CampoEditable;
      const pVal = getValor(est, compNum, pCampo);
      const tooltip = pVal === null
        ? 'Cargue primero la nota P de este período'
        : `El estudiante aprobó P con ${pVal.toFixed(1)} (≥ 70), no necesita recuperación`;
      return (
        <input
          key={cellKey}
          type="text"
          value=""
          disabled
          title={tooltip}
          className="w-16 px-1 py-1 text-center border rounded text-sm bg-gray-100 border-gray-200 cursor-not-allowed text-gray-300"
        />
      );
    }
    
    return (
      <input
        key={cellKey}
        type="number"
        min={0}
        max={100}
        step={0.01}
        value={val ?? ''}
        onChange={e => handleNotaChange(est.estudiante.id, compNum, campo, e.target.value)}
        className={`w-16 px-1 py-1 text-center border rounded text-sm focus:ring-1 focus:ring-blue-400 ${
          isRP ? 'bg-amber-50 border-amber-200' : ''
        }`}
      />
    );
  };

  const conCF = useMemo(() => estudiantes.filter(e => e.cf !== null && !e.estudiante.retirado), [estudiantes]);
  const aprobados = useMemo(() => conCF.filter(e => (e.cf ?? 0) >= 70).length, [conCF]);
  const reprobados = conCF.length - aprobados;
  const promedio = useMemo(() => conCF.length > 0
    ? conCF.reduce((acc, e) => acc + (e.cf ?? 0), 0) / conCF.length
    : 0, [conCF]);

  return (
    <div className="space-y-4">
      {mensaje && <Alert variant={mensaje.tipo} onClose={() => setMensaje(null)}>{mensaje.texto}</Alert>}

      {/* Acción guardar */}
      {Object.keys(editadas).length > 0 && puedeEditar && (
        <div className="flex justify-end">
          <Button onClick={guardar} loading={saving} icon={<Save size={16} />} variant="success">
            Guardar ({Object.keys(editadas).length})
          </Button>
        </div>
      )}

      {/* Selector de competencia */}
      <div className="bg-white rounded-xl shadow-sm border p-4">
        <label className="block text-sm font-medium text-gray-700 mb-2">Competencia a editar</label>
        <div className="relative max-w-sm">
          <select
            value={competenciaActiva}
            onChange={e => setCompetenciaActiva(parseInt(e.target.value))}
            className="w-full appearance-none pl-3 pr-10 py-2 border rounded-lg focus:ring-2 focus:ring-blue-400 text-sm bg-white"
          >
            {[1, 2, 3, 4].map(n => (
              <option key={n} value={n}>{NOMBRES_COMPETENCIAS[n]}</option>
            ))}
          </select>
          <ChevronDown size={16} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
        </div>
        {!puedeEditar && (
          <p className="text-xs text-gray-500 mt-2">Vista solo lectura. Únicamente los profesores asignados pueden calificar.</p>
        )}
      </div>

      {/* Tabla principal */}
      {estudiantes.length === 0 ? (
        <div className="bg-white rounded-xl shadow-sm border p-10 text-center">
          <BookOpen size={42} className="mx-auto text-gray-300 mb-3" />
          <p className="text-gray-500">No hay estudiantes en este curso</p>
        </div>
      ) : (
        <div className="bg-white rounded-xl shadow-sm border p-4">
          <div className="mb-3 px-3 py-2 bg-blue-50 border-l-4 border-blue-500 rounded">
            <p className="font-bold text-blue-900 text-sm">
              {NOMBRES_COMPETENCIAS[competenciaActiva]}
            </p>
            <p className="text-xs text-blue-700">
              Cada período tiene P (nota) y RP (recuperación). Promedio = AVG(MAX(P, RP) de los 4 períodos).
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="bg-gray-50">
                  <th className="px-2 py-2 text-left font-medium text-gray-600">No.</th>
                  <th className="px-2 py-2 text-left font-medium text-gray-600 min-w-[180px]">Estudiante</th>
                  <th className="px-2 py-2 text-center font-medium text-gray-600">P1 {periodosCerrados['p1'] && '🔒'}</th>
                  <th className="px-2 py-2 text-center font-medium text-amber-600 bg-amber-50">RP1</th>
                  <th className="px-2 py-2 text-center font-medium text-gray-600">P2 {periodosCerrados['p2'] && '🔒'}</th>
                  <th className="px-2 py-2 text-center font-medium text-amber-600 bg-amber-50">RP2</th>
                  <th className="px-2 py-2 text-center font-medium text-gray-600">P3 {periodosCerrados['p3'] && '🔒'}</th>
                  <th className="px-2 py-2 text-center font-medium text-amber-600 bg-amber-50">RP3</th>
                  <th className="px-2 py-2 text-center font-medium text-gray-600">P4 {periodosCerrados['p4'] && '🔒'}</th>
                  <th className="px-2 py-2 text-center font-medium text-amber-600 bg-amber-50">RP4</th>
                  <th className="px-3 py-2 text-center font-bold text-blue-700 bg-blue-100">Prom C{competenciaActiva}</th>
                </tr>
              </thead>
              <tbody>
                {estudiantes.map((est, idx) => {
                  const promLocal = calcularPromedioCompetencia(est, competenciaActiva);
                  const promBackend = est.competencias[competenciaActiva]?.promedio_competencia ?? null;
                  const prom = promLocal ?? promBackend;
                  const esRetirado = !!est.estudiante.retirado;
                  return (
                    <tr key={`${est.estudiante.id}-${competenciaActiva}`} className={`border-b ${esRetirado ? 'bg-gray-50' : 'hover:bg-gray-50'}`}>
                      <td className={`px-2 py-1 ${esRetirado ? 'text-gray-400 line-through' : 'text-gray-500'}`}>{idx + 1}</td>
                      <td className="px-2 py-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          {onAbrirFicha && !esRetirado ? (
                            <button
                              type="button"
                              onClick={() => onAbrirFicha(est.estudiante.id)}
                              className="font-medium text-blue-700 hover:text-blue-900 hover:underline text-left"
                              title="Abrir ficha del estudiante"
                            >
                              {est.estudiante.nombre_completo}
                            </button>
                          ) : (
                            <span className={`font-medium ${esRetirado ? 'text-gray-400 line-through' : ''}`}>
                              {est.estudiante.nombre_completo}
                            </span>
                          )}
                          {esRetirado && (
                            <span
                              title={est.estudiante.motivo_retiro || 'Estudiante retirado'}
                              className="inline-block px-2 py-0.5 bg-gray-700 text-white text-[10px] font-medium rounded uppercase tracking-wide"
                            >
                              RETIRADO {est.estudiante.fecha_retiro ? est.estudiante.fecha_retiro.slice(5).replace('-','/') : ''}
                            </span>
                          )}
                        </div>
                      </td>
                      {CAMPOS_PERIODOS.map(({ p, rp }) => (
                        <Fragment key={`${p}-${rp}`}>
                          <td className="px-2 py-1 text-center">{renderCelda(est, competenciaActiva, p, false)}</td>
                          <td className="px-2 py-1 text-center bg-amber-50">{renderCelda(est, competenciaActiva, rp, true)}</td>
                        </Fragment>
                      ))}
                      <td className={`px-3 py-1 text-center font-bold bg-blue-50 ${esRetirado ? 'text-gray-400' : getNotaClass(prom)}`}>
                        {prom !== null ? prom.toFixed(1) : '—'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Resumen Final */}
      {estudiantes.length > 0 && (
        <div className="bg-white rounded-xl shadow-sm border p-4">
          <h3 className="font-bold text-lg mb-4 flex items-center gap-2">
            <CheckCircle className="text-green-600" />
            Calificación Final del Área
          </h3>
          <p className="text-xs text-gray-500 mb-3">
            PC[i] = promedio de las 4 competencias en período i. CF = AVG(PC1, PC2, PC3, PC4) entero.
          </p>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="bg-gray-50">
                  <th className="px-3 py-2 text-left">No.</th>
                  <th className="px-3 py-2 text-left">Estudiante</th>
                  <th className="px-3 py-2 text-center bg-blue-50 text-blue-700 font-bold">PC1</th>
                  <th className="px-3 py-2 text-center bg-blue-50 text-blue-700 font-bold">PC2</th>
                  <th className="px-3 py-2 text-center bg-blue-50 text-blue-700 font-bold">PC3</th>
                  <th className="px-3 py-2 text-center bg-blue-50 text-blue-700 font-bold">PC4</th>
                  <th className="px-3 py-2 text-center bg-blue-100 text-blue-900 font-bold">CF</th>
                  <th className="px-3 py-2 text-center bg-blue-100 text-blue-900 font-bold">Lit.</th>
                  <th className="px-3 py-2 text-center">Estado</th>
                </tr>
              </thead>
              <tbody>
                {estudiantes.map((est, idx) => {
                  const esRetirado = !!est.estudiante.retirado;
                  const aprobado = est.cf !== null && est.cf >= 70;
                  return (
                    <tr key={est.estudiante.id} className={`border-b ${esRetirado ? 'bg-gray-50' : ''}`}>
                      <td className={`px-3 py-2 ${esRetirado ? 'text-gray-400 line-through' : 'text-gray-500'}`}>{idx + 1}</td>
                      <td className="px-3 py-2">
                        <span className={`font-medium ${esRetirado ? 'text-gray-400 line-through' : ''}`}>{est.estudiante.nombre_completo}</span>
                      </td>
                      {(['pc1', 'pc2', 'pc3', 'pc4'] as const).map(k => {
                        const v = est.pc_por_periodo[k];
                        return (
                          <td key={k} className={`px-3 py-2 text-center ${esRetirado ? 'text-gray-400' : 'text-gray-700'}`}>
                            {v !== null ? v.toFixed(1) : '—'}
                          </td>
                        );
                      })}
                      <td className={`px-3 py-2 text-center font-bold ${esRetirado ? 'text-gray-400' : getNotaClass(est.cf)}`}>
                        {est.cf !== null ? est.cf.toFixed(0) : '—'}
                      </td>
                      <td className={`px-3 py-2 text-center font-bold ${esRetirado ? 'text-gray-400' : getNotaClass(est.cf)}`}>
                        {esRetirado ? '—' : (est.literal || getLiteral(est.cf))}
                      </td>
                      <td className="px-3 py-2 text-center">
                        {esRetirado ? (
                          <span className="px-2 py-1 rounded-full text-xs font-medium bg-gray-200 text-gray-600">Retirado</span>
                        ) : est.cf !== null ? (
                          <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                            aprobado ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                          }`}>
                            {aprobado ? 'Aprobado' : 'Reprobado'}
                          </span>
                        ) : (
                          <span className="px-2 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-500">Sin CF</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* KPIs */}
          <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-gray-50 rounded-lg p-3 text-center">
              <p className="text-2xl font-bold text-gray-800">{estudiantes.length}</p>
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
          </div>
        </div>
      )}
    </div>
  );
};
