import { useState, useCallback, useMemo, useEffect, Fragment } from 'react';
import api from '../../../services/api';
import { Save, BookOpen } from 'lucide-react';
import { Button, Alert } from '../../../components/ui';
import {
  EstudianteData, NOMBRES_COMPETENCIAS, getNotaClass,
} from './tipos';

// ════════════════════════════════════════════════════════════════════
// TAB NOTAS POR PERÍODO (vista alternativa)
// Selector de período (P1-P4). Muestra las 4 competencias de ese período
// lado a lado (P y RP de cada una) para cada estudiante.
// Coincide con cómo el maestro califica: por período.
// El cálculo del PC/CF NO cambia — se hace en el backend.
// ════════════════════════════════════════════════════════════════════

interface Props {
  estudiantes: EstudianteData[];
  asignaturaId: number;
  puedeEditar: boolean;
  onReload: () => Promise<void>;
  periodosCerrados?: Record<string, boolean>;
  /** ENT-A · curso desde el que se edita: el servidor autoriza con ESTE curso. */
  cursoId?: number;
  /** ENT-A · informa al padre de lo pendiente y de si se está guardando. */
  onEstadoEdicion?: (e: { pendientes: number; guardando: boolean }) => void;
}

/** ENT-A · Quita SOLO las casillas guardadas cuyo valor sigue siendo el que se
 *  envió. Lo escrito después (o lo que no se guardó) se conserva. */
function quitarGuardadas<T extends Record<string, Record<string, number | null | undefined>>>(
  prev: T, guardadas: Record<string, Record<string, number | null | undefined>>): T {
  const out: Record<string, Record<string, number | null | undefined>> = {};
  for (const [k, campos] of Object.entries(prev)) {
    const env = guardadas[k] || {};
    const resto = Object.fromEntries(Object.entries(campos).filter(([c, v]) => !(c in env && env[c] === v)));
    if (Object.keys(resto).length) out[k] = resto;
  }
  return out as T;
}

// clave: "estudianteId-competenciaNumero" → { p?: valor, rp?: valor }
// ENT-A · La clave incluye el PERÍODO: lo escrito y no guardado se conserva, y
// no debe pasar a otro período al cambiar de pestaña.
// clave: "estudianteId-competenciaNumero-periodo"
type EditadasState = Record<string, { p?: number | null; rp?: number | null }>;

export const TabNotasPorPeriodo: React.FC<Props> = ({ estudiantes, asignaturaId, puedeEditar, onReload, periodosCerrados = {}, cursoId, onEstadoEdicion }) => {
  const [periodoActivo, setPeriodoActivo] = useState<number>(1);
  const [editadas, setEditadas] = useState<EditadasState>({});
  const [saving, setSaving] = useState(false);
  const [mensaje, setMensaje] = useState<{ tipo: 'success' | 'error' | 'warning'; texto: string } | null>(null);

  // ENT-A · el padre sabe si hay cambios sin guardar o un guardado en curso.
  const nPendientes = Object.values(editadas).reduce((n, c) => n + Object.keys(c).length, 0);
  useEffect(() => { onEstadoEdicion?.({ pendientes: nPendientes, guardando: saving }); }, [nPendientes, saving]);
  useEffect(() => () => onEstadoEdicion?.({ pendientes: 0, guardando: false }), []);

  // ¿El período activo está cerrado? → bloquea las casillas
  const periodoActivoCerrado = !!periodosCerrados[`p${periodoActivo}`];

  // Nombre del campo P/RP para el período activo (ej. periodo 1 → 'p1' / 'rp1')
  const campoP = `p${periodoActivo}` as 'p1' | 'p2' | 'p3' | 'p4';
  const campoRP = `rp${periodoActivo}` as 'rp1' | 'rp2' | 'rp3' | 'rp4';

  // Obtener valor actual (editado o del backend) de un estudiante/competencia
  const getValor = useCallback((est: EstudianteData, compNum: number, tipo: 'p' | 'rp'): number | null => {
    const key = `${est.estudiante.id}-${compNum}-${periodoActivo}`;
    const ed = editadas[key];
    if (ed && tipo in ed) return (tipo === 'p' ? ed.p : ed.rp) ?? null;
    const comp = est.competencias[compNum];
    if (!comp) return null;
    return (comp[tipo === 'p' ? campoP : campoRP]) ?? null;
  }, [editadas, campoP, campoRP, periodoActivo]);

  // Registrar un cambio en una celda
  const onChangeCelda = useCallback((estId: number, compNum: number, tipo: 'p' | 'rp', valorStr: string) => {
    const key = `${estId}-${compNum}-${periodoActivo}`;
    let valor: number | null = null;
    if (valorStr !== '') {
      const parsed = parseFloat(valorStr);
      if (Number.isNaN(parsed)) return;
      if (parsed < 0 || parsed > 100) return;
      valor = parsed;
    }
    setEditadas(prev => ({
      ...prev,
      [key]: { ...prev[key], [tipo]: valor },
    }));
  }, [periodoActivo]);

  // Guardar todos los cambios
  const guardar = async () => {
    const keys = Object.keys(editadas);
    if (keys.length === 0) {
      setMensaje({ tipo: 'error', texto: 'No hay cambios por guardar' });
      return;
    }
    setSaving(true);
    setMensaje(null);
    // ENT-A · Cada casilla queda GUARDADA, IGNORADA (período cerrado sin
    // permiso vigente) o RECHAZADA (error del servidor). Solo se limpian las
    // guardadas; las demás se conservan en pantalla, en SU período.
    const enviadasGuardadas: EditadasState = {};
    let guardadas = 0;
    const ignoradas: string[] = [];
    const rechazadas: string[] = [];
    const nombreDe = (id: number) => estudiantes.find(e => e.estudiante.id === id)?.estudiante.nombre_completo || `#${id}`;

    try {
      for (const key of keys) {
        const [estIdStr, compNumStr, perStr] = key.split('-');
        const estId = parseInt(estIdStr);
        const compNum = parseInt(compNumStr);
        const per = parseInt(perStr);
        const cambios = editadas[key];

        const payload: Record<string, unknown> = {
          estudiante_id: estId,
          asignatura_id: asignaturaId,
          competencia_numero: compNum,
        };
        if (cursoId) payload.curso_id = cursoId;
        // El P/RP del período en que se escribió (no el de la pestaña actual)
        if ('p' in cambios) payload[`p${per}`] = cambios.p;
        if ('rp' in cambios) payload[`rp${per}`] = cambios.rp;
        const n = Object.keys(cambios).length;

        try {
          const res = await api.post('/calificaciones-secundaria', payload);
          const ign: number[] = res.data?.periodos_cerrados_ignorados || [];
          if (ign.includes(per)) {
            ignoradas.push(`${nombreDe(estId)} C${compNum} P${per}`);
          } else {
            guardadas += n;
            enviadasGuardadas[key] = { ...cambios };
          }
        } catch (err: unknown) {
          const d = (err as { response?: { data?: { error?: string; message?: string } } })?.response?.data;
          rechazadas.push(`${nombreDe(estId)} C${compNum} P${per}: ${String(d?.message || d?.error || 'sin respuesta del servidor').replace(/\.$/, '')}`);
        }
      }

      const partes = [`${guardadas} nota(s) guardada(s).`];
      if (ignoradas.length) partes.push(`No se guardaron (período cerrado sin permiso vigente): ${ignoradas.join('; ')}.`);
      if (rechazadas.length) partes.push(`Rechazadas por el servidor: ${rechazadas.join('; ')}.`);
      if (ignoradas.length || rechazadas.length) partes.push('Lo escrito se conserva en pantalla, marcado «sin guardar».');
      setMensaje({ tipo: rechazadas.length ? 'error' : ignoradas.length ? 'warning' : 'success', texto: partes.join(' ') });

      // Solo se limpia lo guardado (y si no se tocó después de enviarlo).
      setEditadas(prev => quitarGuardadas(prev, enviadasGuardadas));
      await onReload();
    } catch {
      setMensaje({ tipo: 'error', texto: 'Error al guardar las notas' });
    } finally {
      setSaving(false);
    }
  };

  // Renderizar una celda editable (input)
  const renderCelda = (est: EstudianteData, compNum: number, tipo: 'p' | 'rp') => {
    const valor = getValor(est, compNum, tipo);
    // TRAS-1 · quien salió del curso (trasladado o retirado), en solo lectura.
    const esRetirado = !!est.estudiante.retirado || !!est.permanencia?.solo_lectura;
    // TRAS-1 · nota registrada antes del traslado: protegida (permiso de Dirección).
    const protegida = (est.permanencia?.notas_previas_traslado?.[String(compNum)] || [])
      .includes(tipo === 'p' ? campoP : campoRP);
    // ENT-A · quien salió del curso queda en solo lectura SALVO las casillas que
    // el servidor autoriza a este docente (permiso de corrección de Dirección).
    // (también un período CERRADO con permiso temporal: el período sigue cerrado
    // y solo se abren estas casillas, mientras el permiso esté vigente).
    const autorizada = puedeEditar
      && (est.permanencia?.campos_autorizados || []).includes(tipo === 'p' ? campoP : campoRP);
    // ENT-A · lo escrito que aún no se guardó (ignorado, rechazado o sin enviar).
    const sinGuardar = tipo in (editadas[`${est.estudiante.id}-${compNum}-${periodoActivo}`] || {});
    if (protegida && !esRetirado && !autorizada) {
      return (
        <span className={getNotaClass(valor)}
              title="Registrada antes del traslado. Para corregirla hace falta el permiso temporal de corrección de Dirección.">
          {valor ?? '—'} <span aria-hidden>🔒</span>
        </span>
      );
    }
    // Si no puede editar, está retirado, o el período está cerrado → solo lectura
    // (salvo una casilla autorizada por el servidor para corrección).
    if (!autorizada && (!puedeEditar || esRetirado || periodoActivoCerrado)) {
      if (sinGuardar) {
        const guardado = est.competencias[compNum]?.[tipo === 'p' ? campoP : campoRP] ?? null;
        return (
          <span data-sin-guardar="si"
                title={`Escrito sin guardar: ${valor ?? '—'}. En el servidor: ${guardado ?? '—'}. Esta casilla ya no admite cambios.`}
                className="inline-block px-1 border border-dashed border-amber-500 rounded bg-amber-50 text-amber-900">
            {valor ?? '—'} ✎
          </span>
        );
      }
      return <span className={getNotaClass(valor)}>{valor ?? '—'}</span>;
    }
    // Regla MINERD: RP solo se habilita si el P del mismo período existe y es < 70
    if (tipo === 'rp') {
      const pVal = getValor(est, compNum, 'p');
      const rpDeshabilitado = pVal === null || pVal >= 70;
      if (rpDeshabilitado) {
        return (
          <input
            type="number"
            value={valor ?? ''}
            disabled
            title="RP solo aplica si el estudiante reprobó P (< 70)"
            className="w-14 px-1 py-1 text-center border rounded text-sm bg-gray-100 text-gray-400 cursor-not-allowed"
          />
        );
      }
    }
    return (
      <input
        type="number"
        min={0}
        max={100}
        value={valor ?? ''}
        onChange={e => onChangeCelda(est.estudiante.id, compNum, tipo, e.target.value)}
        disabled={saving}
        title={sinGuardar ? 'Escrito sin guardar' : autorizada ? 'Corrección autorizada por Dirección (permiso temporal)' : undefined}
        data-autorizada={autorizada ? 'si' : undefined}
        data-sin-guardar={sinGuardar ? 'si' : undefined}
        className={`w-14 px-1 py-1 text-center border rounded text-sm ${
          sinGuardar ? 'border-dashed border-amber-500 bg-amber-50'
            : autorizada ? 'border-indigo-400 ring-1 ring-indigo-200' : tipo === 'rp' ? 'bg-amber-50' : ''}`}
      />
    );
  };

  const totalEditados = useMemo(() => Object.keys(editadas).length, [editadas]);

  return (
    <div className="space-y-4">
      {mensaje && <Alert variant={mensaje.tipo} onClose={() => setMensaje(null)}>{mensaje.texto}</Alert>}

      {/* Acción guardar */}
      {totalEditados > 0 && puedeEditar && (
        <div className="flex justify-end gap-2">
          <Button variant="secondary" disabled={saving} onClick={() => {
            if (window.confirm(`¿Descartar ${nPendientes} cambio(s) sin guardar? No se puede deshacer.`)) { setEditadas({}); setMensaje(null); }
          }}>
            Descartar lo no guardado
          </Button>
          <Button onClick={guardar} loading={saving} icon={<Save size={16} />} variant="success">
            Guardar ({totalEditados})
          </Button>
        </div>
      )}

      {/* Selector de período (pestañas) */}
      <div className="bg-white rounded-xl shadow-sm border p-4">
        <label className="block text-sm font-medium text-gray-700 mb-2">Período a calificar</label>
        <div className="flex gap-2">
          {[1, 2, 3, 4].map(n => {
            const cerrado = !!periodosCerrados[`p${n}`];
            return (
              <button
                key={n}
                onClick={() => setPeriodoActivo(n)}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition ${
                  periodoActivo === n
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                Período {n} {cerrado && '🔒'}
              </button>
            );
          })}
        </div>
        {!puedeEditar && (
          <p className="text-xs text-gray-500 mt-2">Vista solo lectura. Únicamente los profesores asignados pueden calificar.</p>
        )}
      </div>

      {/* Tabla: 4 competencias del período activo */}
      {estudiantes.length === 0 ? (
        <div className="bg-white rounded-xl shadow-sm border p-10 text-center">
          <BookOpen size={42} className="mx-auto text-gray-300 mb-3" />
          <p className="text-gray-500">No hay estudiantes en este curso</p>
        </div>
      ) : (
        <div className="bg-white rounded-xl shadow-sm border p-4">
          {periodoActivoCerrado ? (
            <div className="mb-3 px-3 py-2 bg-red-50 border-l-4 border-red-500 rounded">
              <p className="font-bold text-red-900 text-sm">🔒 Período {periodoActivo} cerrado</p>
              <p className="text-xs text-red-700">
                Este período está cerrado y no se puede editar. Use "Solicitar Corrección" si necesita cambiar una nota.
              </p>
              {estudiantes.some(e => (e.permanencia?.campos_autorizados || []).includes(campoP)) && puedeEditar && (
                <p className="text-xs text-indigo-800 font-medium mt-1">
                  ✏️ Tiene un permiso temporal de corrección de Dirección: solo las casillas marcadas pueden
                  corregirse mientras el permiso esté vigente. El período sigue cerrado.
                </p>
              )}
            </div>
          ) : (
            <div className="mb-3 px-3 py-2 bg-blue-50 border-l-4 border-blue-500 rounded">
              <p className="font-bold text-blue-900 text-sm">Período {periodoActivo}</p>
              <p className="text-xs text-blue-700">
                Llená el P{periodoActivo} de las 4 competencias. RP = recuperación (solo si P &lt; 70).
              </p>
            </div>
          )}
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="bg-gray-50">
                  <th className="px-2 py-2 text-left font-medium text-gray-600">No.</th>
                  <th className="px-2 py-2 text-left font-medium text-gray-600 min-w-[160px]">Estudiante</th>
                  {[1, 2, 3, 4].map(c => (
                    <th key={c} colSpan={2} className="px-2 py-2 text-center font-medium text-teal-700 bg-teal-50 border-l">
                      Comp. {c}
                    </th>
                  ))}
                </tr>
                <tr className="bg-gray-50 text-xs">
                  <th></th>
                  <th></th>
                  {[1, 2, 3, 4].map(c => (
                    <Fragment key={c}>
                      <th className="px-1 py-1 text-center font-medium text-gray-600 border-l">P{periodoActivo}</th>
                      <th className="px-1 py-1 text-center font-medium text-amber-600 bg-amber-50">RP</th>
                    </Fragment>
                  ))}
                </tr>
              </thead>
              <tbody>
                {estudiantes.map((est, idx) => {
                  const esRetirado = !!est.estudiante.retirado || !!est.permanencia?.solo_lectura;
                  const avisos = est.permanencia?.avisos || [];
                  return (
                    <tr key={est.estudiante.id} className={`border-b ${esRetirado ? 'bg-gray-50' : 'hover:bg-gray-50'}`}>
                      <td className="px-2 py-1 text-center text-gray-500">{est.estudiante.no_lista ?? '—'}</td>
                      <td className="px-2 py-1">
                        <span className={esRetirado ? 'text-gray-400' : ''}>{est.estudiante.nombre_completo}</span>
                        {esRetirado && !avisos.length && <span className="ml-1 text-xs text-red-500">(retirado)</span>}
                        {esRetirado && (est.permanencia?.campos_autorizados || []).length > 0 && puedeEditar && (
                          <div className="text-[10px] text-indigo-800 font-medium">
                            ✏️ Corrección autorizada por Dirección:{' '}
                            {[...new Set((est.permanencia!.campos_autorizados || []).map(c => 'P' + c.replace(/[^0-9]/g, '')))].join(', ')}
                            {' '}· sigue {avisos.some(a => a.startsWith('Retirado')) || est.estudiante.retirado ? 'retirado' : 'fuera del curso'}
                          </div>
                        )}
                        {avisos.length > 0 && (
                          <div className="text-[10px] text-indigo-700">
                            {avisos.join(' · ')}
                            {Object.keys(est.permanencia?.notas_previas_traslado || {}).length > 0
                              && ' · 🔒 notas registradas antes del traslado'}
                          </div>
                        )}
                      </td>
                      {[1, 2, 3, 4].map(c => (
                        <Fragment key={c}>
                          <td className="px-1 py-1 text-center border-l">{renderCelda(est, c, 'p')}</td>
                          <td className="px-1 py-1 text-center bg-amber-50">{renderCelda(est, c, 'rp')}</td>
                        </Fragment>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
