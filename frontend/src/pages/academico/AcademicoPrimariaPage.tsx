import { useState, useEffect, useCallback } from 'react';
import api from '../../services/api';
import { BookOpen, Save, CheckCircle } from 'lucide-react';
import { Button, Alert, Spinner } from '../../components/ui';
import { useAuth } from '../../context/AuthContext';

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

// Modelo MINERD primaria: por cada (estudiante, asignatura, competencia) hay
// 4 períodos (p1..p4) y sus 4 recuperaciones (rp1..rp4). final_competencia
// es la nota final de esa competencia (promedio de los 4 períodos efectivos).
interface CompetenciaPrimaria {
  id: number | null;
  estudiante_id: number;
  asignatura_id: number;
  competencia_numero: number;
  competencia_nombre: string | null;
  p1: number | null; rp1: number | null;
  p2: number | null; rp2: number | null;
  p3: number | null; rp3: number | null;
  p4: number | null; rp4: number | null;
  final_competencia: number | null;
  literal: string | null;
}

interface EstudianteData {
  estudiante: {
    id: number;
    nombre_completo: string;
    no_lista: number | null;
    // Flags de retiro (vienen del backend)
    retirado?: boolean;
    fecha_retiro?: string | null;
    motivo_retiro?: string | null;
  };
  competencias: CompetenciaPrimaria[];
}

interface Props {
  cursoId: number;
  asignaturaId: number;
  curso: Curso | null;
  asignatura: Asignatura | null;
  onVolver: () => void;
}

// Nombres oficiales MINERD de las competencias
const NOMBRES_COMPETENCIAS: Record<number, string> = {
  1: 'Comunicativa',
  2: 'Pensamiento Lógico, Creativo y Crítico; Científica y Tecnológica',
  3: 'Ética y Ciudadana; Desarrollo Personal; Ambiental y de la Salud'
};

// ───────────────────────────────────────────────────────────────────────
// ESTADO DE EDICIONES
// ───────────────────────────────────────────────────────────────────────
// Estructura del estado:
//
//   editadas: {
//     "37-1": { p1: 80, rp2: 75 },     // estudiante 37, competencia 1: editó p1 y rp2
//     "37-2": { p3: 90 },               // estudiante 37, competencia 2: editó p3
//     "42-1": { p1: 65, rp1: 70 },      // estudiante 42, competencia 1: editó p1 y rp1
//   }
//
// Cada celda (estudiante × competencia × campo P/RP) es independiente:
// - Modificar p1 NO toca p2/rp1/rp2/p3/etc del mismo estudiante.
// - Modificar competencia 1 de estudiante A NO afecta competencia 2 de A.
// - Modificar estudiante A NO afecta a otros estudiantes.
//
// El estado SOLO guarda diffs respecto a lo cargado del backend; el render
// combina diff + datos cargados vía getValor(). Esto permite que el botón
// "Guardar (N)" muestre exactamente cuántas competencias cambiaron, y al
// guardar mandamos solo lo modificado al backend (que aplica UPDATE parcial).
type DiffPorCompetencia = Partial<Pick<CompetenciaPrimaria,
  'p1' | 'rp1' | 'p2' | 'rp2' | 'p3' | 'rp3' | 'p4' | 'rp4'
>>;

type EditadasState = Record<string, DiffPorCompetencia>;

// Campos editables (los 8 P/RP). Centralizados para que el render y el
// guardado usen la misma lista — evita inconsistencias.
type CampoEditable = 'p1' | 'rp1' | 'p2' | 'rp2' | 'p3' | 'rp3' | 'p4' | 'rp4';

export const AcademicoPrimariaPage: React.FC<Props> = ({ cursoId, asignaturaId, curso, asignatura, onVolver }) => {
  const { user } = useAuth();
  const esProfesor = user?.role === 'profesor';
  const puedeEditar = esProfesor;

  const [estudiantes, setEstudiantes] = useState<EstudianteData[]>([]);
  const [numCompetencias, setNumCompetencias] = useState(3);
  const [editadas, setEditadas] = useState<EditadasState>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [mensaje, setMensaje] = useState<{ tipo: 'success' | 'error'; texto: string } | null>(null);

  useEffect(() => {
    if (cursoId && asignaturaId) cargar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cursoId, asignaturaId]);

  const cargar = async () => {
    setLoading(true);
    try {
      const res = await api.get(`/calificaciones-primaria/curso/${cursoId}/asignatura/${asignaturaId}`);
      setEstudiantes(res.data.calificaciones || []);
      setNumCompetencias(res.data.num_competencias || 3);
      // Al recargar, descarto cualquier edición pendiente — los datos vienen frescos del backend.
      setEditadas({});
    } catch (err: any) {
      setMensaje({ tipo: 'error', texto: err.response?.data?.error || 'Error cargando calificaciones' });
    } finally {
      setLoading(false);
    }
  };

  // Clave determinista que identifica la celda (estudiante × competencia)
  const keyCelda = (estId: number, compNum: number) => `${estId}-${compNum}`;

  // Modifica UNA celda. Solo cambia el campo indicado.
  // useCallback con deps vacías porque solo usa setState con función updater.
  const handleNotaChange = useCallback((estId: number, compNum: number, campo: CampoEditable, valor: string) => {
    // Vacío → null (intencional: el profesor borró la nota).
    // Si no es vacío, parseamos. Si parsea NaN o fuera de rango, ignoramos el cambio.
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

  // Devuelve el valor mostrado para una celda: si hay edit pendiente, lo de edit; si no, lo del backend.
  const getValor = (comp: CompetenciaPrimaria, campo: CampoEditable): number | null => {
    const k = keyCelda(comp.estudiante_id, comp.competencia_numero);
    const ed = editadas[k];
    if (ed && campo in ed) return ed[campo] ?? null;
    return comp[campo];
  };

  // valor_periodo MINERD: max(P, RP) cuando hay RP; si no hay RP, usa P; si no hay P pero sí RP, usa RP.
  // Si ambos null, el período no aporta a la competencia.
  const valorPeriodo = (comp: CompetenciaPrimaria, periodo: 1 | 2 | 3 | 4): number | null => {
    const p = getValor(comp, `p${periodo}` as CampoEditable);
    const rp = getValor(comp, `rp${periodo}` as CampoEditable);
    if (rp !== null && p !== null) return Math.max(p, rp);
    if (rp !== null) return rp;
    if (p !== null) return p;
    return null;
  };

  // Promedio de los 4 períodos. Solo se calcula si los 4 tienen valor.
  // Si falta uno, devuelve null para no engañar — el backend sí persiste lo que haya.
  const calcularCompetencia = (comp: CompetenciaPrimaria): number | null => {
    const vals: number[] = [];
    for (const p of [1, 2, 3, 4] as const) {
      const v = valorPeriodo(comp, p);
      if (v === null) return null;
      vals.push(v);
    }
    return Math.round((vals.reduce((a, b) => a + b, 0) / 4) * 100) / 100;
  };

  // CF = promedio de las competencias. Usa cálculo local primero; si una
  // competencia no se puede calcular (faltan períodos), cae a final_competencia
  // del backend (que puede estar persistido aunque el cálculo local no esté completo).
  const calcularCF = (est: EstudianteData): number | null => {
    const valores: number[] = [];
    for (const comp of est.competencias) {
      const c = calcularCompetencia(comp) ?? comp.final_competencia;
      if (c === null) return null;
      valores.push(c);
    }
    if (valores.length === 0) return null;
    return Math.round((valores.reduce((a, b) => a + b, 0) / valores.length) * 100) / 100;
  };

  const getLiteral = (nota: number | null): string => {
    if (nota === null) return '-';
    if (nota >= 90) return 'A';
    if (nota >= 80) return 'B';
    if (nota >= 70) return 'C';
    return 'F';
  };

  const getNotaClass = (n: number | null) => {
    if (n === null) return '';
    if (n >= 90) return 'text-green-600';
    if (n >= 80) return 'text-blue-600';
    if (n >= 70) return 'text-amber-600';
    return 'text-red-600';
  };

  // Persiste todas las ediciones. Una llamada al backend por (estudiante, competencia).
  // El payload solo incluye los campos modificados — el backend los aplica como UPDATE
  // parcial sin tocar otros campos (verificado: tests del backend confirman este comportamiento).
  const guardar = async () => {
    if (Object.keys(editadas).length === 0) {
      setMensaje({ tipo: 'error', texto: 'No hay cambios por guardar' });
      return;
    }
    setSaving(true);
    try {
      for (const [k, cambios] of Object.entries(editadas)) {
        const [estIdStr, compNumStr] = k.split('-');
        const estId = parseInt(estIdStr);
        const compNum = parseInt(compNumStr);
        await api.post('/calificaciones-primaria', {
          estudiante_id: estId,
          asignatura_id: asignaturaId,
          competencia_numero: compNum,
          competencia_nombre: NOMBRES_COMPETENCIAS[compNum],
          ...(cambios as Record<string, any>),
        });
      }
      setMensaje({ tipo: 'success', texto: 'Calificaciones guardadas' });
      // Recargar limpia editadas y trae datos frescos
      await cargar();
    } catch (err: any) {
      setMensaje({ tipo: 'error', texto: err.response?.data?.error || 'Error al guardar' });
    } finally {
      setSaving(false);
    }
  };

  // Render de una celda. Un input por (estudiante, competencia, campo).
  // El key del input incluye los 3 identificadores → React no confunde celdas
  // entre re-renders, incluso si los estudiantes se reordenaran.
  // Si el estudiante está retirado, la celda es siempre readonly (incluso
  // si el rol puede editar) y muestra el valor en gris.
  const renderCelda = (comp: CompetenciaPrimaria, campo: CampoEditable, isRP: boolean, esRetirado: boolean = false) => {
    const val = getValor(comp, campo);
    const cellKey = `${comp.estudiante_id}-${comp.competencia_numero}-${campo}`;
    if (!puedeEditar || esRetirado) {
      // Display read-only — usa mismo ancho que el input para alineación con header
      return (
        <span className={`inline-block w-16 text-center text-sm ${
          esRetirado ? (val !== null ? 'text-gray-500' : 'text-gray-300') :
          isRP ? 'text-amber-700' : 'text-gray-700'
        } ${!esRetirado ? getNotaClass(val) : ''}`}>
          {val !== null ? val.toFixed(2) : '—'}
        </span>
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
        onChange={e => handleNotaChange(comp.estudiante_id, comp.competencia_numero, campo, e.target.value)}
        className={`w-16 px-1 py-1 text-center border rounded text-sm focus:ring-1 focus:ring-blue-400 ${
          isRP ? 'bg-amber-50 border-amber-200' : ''
        }`}
      />
    );
  };

  const renderCompetenciaTabla = (compNum: number) => {
    const nombre = NOMBRES_COMPETENCIAS[compNum] || `Competencia ${compNum}`;
    return (
      <div key={`comp-${compNum}`} className="mb-6">
        <div className="mb-2 px-4 py-3 bg-indigo-50 border-l-4 border-indigo-500 rounded">
          <p className="font-bold text-indigo-900">
            Competencia {compNum} (C{compNum}): {nombre}
          </p>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="bg-gray-50">
                <th className="px-2 py-2 text-left font-medium text-gray-600 sticky left-0 bg-gray-50">No.</th>
                <th className="px-2 py-2 text-left font-medium text-gray-600 sticky left-8 bg-gray-50 min-w-[180px]">Estudiante</th>
                <th className="px-2 py-2 text-center font-medium text-gray-600">P1</th>
                <th className="px-2 py-2 text-center font-medium text-amber-600 bg-amber-50">RP1</th>
                <th className="px-2 py-2 text-center font-medium text-gray-600">P2</th>
                <th className="px-2 py-2 text-center font-medium text-amber-600 bg-amber-50">RP2</th>
                <th className="px-2 py-2 text-center font-medium text-gray-600">P3</th>
                <th className="px-2 py-2 text-center font-medium text-amber-600 bg-amber-50">RP3</th>
                <th className="px-2 py-2 text-center font-medium text-gray-600">P4</th>
                <th className="px-2 py-2 text-center font-medium text-amber-600 bg-amber-50">RP4</th>
                <th className="px-3 py-2 text-center font-bold text-indigo-700 bg-indigo-100">C{compNum}</th>
              </tr>
            </thead>
            <tbody>
              {estudiantes.map((est, idx) => {
                const comp = est.competencias.find(c => c.competencia_numero === compNum);
                if (!comp) return null;
                const c = calcularCompetencia(comp);
                const esRetirado = !!est.estudiante.retirado;
                return (
                  // key incluye estudiante + competencia → React no confunde filas
                  <tr key={`${est.estudiante.id}-${compNum}`} className={`border-b ${esRetirado ? 'bg-gray-50' : 'hover:bg-gray-50'}`}>
                    <td className={`px-2 py-1 sticky left-0 bg-white ${esRetirado ? 'text-gray-400 line-through' : 'text-gray-500'}`}>
                      {est.estudiante.no_lista || idx + 1}
                    </td>
                    <td className={`px-2 py-1 sticky left-8 ${esRetirado ? 'bg-gray-50' : 'bg-white'}`}>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={`font-medium ${esRetirado ? 'text-gray-400 line-through' : ''}`}>
                          {est.estudiante.nombre_completo}
                        </span>
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
                    <td className="px-2 py-1 text-center">{renderCelda(comp, 'p1', false, esRetirado)}</td>
                    <td className="px-2 py-1 text-center bg-amber-50">{renderCelda(comp, 'rp1', true, esRetirado)}</td>
                    <td className="px-2 py-1 text-center">{renderCelda(comp, 'p2', false, esRetirado)}</td>
                    <td className="px-2 py-1 text-center bg-amber-50">{renderCelda(comp, 'rp2', true, esRetirado)}</td>
                    <td className="px-2 py-1 text-center">{renderCelda(comp, 'p3', false, esRetirado)}</td>
                    <td className="px-2 py-1 text-center bg-amber-50">{renderCelda(comp, 'rp3', true, esRetirado)}</td>
                    <td className="px-2 py-1 text-center">{renderCelda(comp, 'p4', false, esRetirado)}</td>
                    <td className="px-2 py-1 text-center bg-amber-50">{renderCelda(comp, 'rp4', true, esRetirado)}</td>
                    <td className={`px-3 py-1 text-center font-bold bg-indigo-50 ${esRetirado ? 'text-gray-400' : getNotaClass(c)}`}>
                      {c?.toFixed(2) ?? '—'}{esRetirado && c !== null ? <sup className="text-[8px] ml-0.5">parc</sup> : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  if (loading) return <div className="flex justify-center py-10"><Spinner /></div>;

  return (
    <div className="space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
            <BookOpen className="text-indigo-600" />
            Calificaciones Primaria
          </h2>
          <p className="text-sm text-gray-500">{curso?.nombre_completo} — {asignatura?.nombre}</p>
          <p className="text-xs text-indigo-600 mt-1">
            Cada competencia: una nota por período (P1-P4) + recuperación (RP). Final = promedio de las {numCompetencias} competencias.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={onVolver}>Volver</Button>
          {Object.keys(editadas).length > 0 && (
            <Button onClick={guardar} loading={saving} icon={<Save size={16} />} variant="success">
              Guardar ({Object.keys(editadas).length})
            </Button>
          )}
        </div>
      </div>

      {mensaje && <Alert variant={mensaje.tipo} onClose={() => setMensaje(null)}>{mensaje.texto}</Alert>}

      {/* Tablas de las {numCompetencias} competencias — todas visibles, estilo secundaria.
          Cada una muestra los 4 períodos + sus 4 RP + final de competencia. */}
      {Array.from({ length: numCompetencias }, (_, i) => i + 1).map(n => renderCompetenciaTabla(n))}

      {/* Resumen de calificación final del área */}
      <div className="mt-8 pt-4 border-t-2 border-indigo-200">
        <h3 className="font-bold text-lg mb-4 flex items-center gap-2">
          <CheckCircle className="text-green-600" />
          Calificación Final del Área
        </h3>
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="bg-gray-50">
                <th className="px-3 py-2 text-left">No.</th>
                <th className="px-3 py-2 text-left">Estudiante</th>
                {Array.from({ length: numCompetencias }, (_, i) => i + 1).map(n => (
                  <th key={n} className="px-3 py-2 text-center bg-indigo-50 text-indigo-700 font-bold">C{n}</th>
                ))}
                <th className="px-3 py-2 text-center bg-green-100 font-bold text-green-800">CF</th>
                <th className="px-3 py-2 text-center bg-green-100 font-bold text-green-800">Lit.</th>
                <th className="px-3 py-2 text-center">Estado</th>
              </tr>
            </thead>
            <tbody>
              {estudiantes.map((est, idx) => {
                const cf = calcularCF(est);
                const literal = getLiteral(cf);
                const aprobado = cf !== null && cf >= 70;
                const esRetirado = !!est.estudiante.retirado;
                return (
                  <tr key={`final-${est.estudiante.id}`} className={`border-b ${esRetirado ? 'bg-gray-50' : ''}`}>
                    <td className={`px-3 py-2 ${esRetirado ? 'text-gray-400 line-through' : ''}`}>
                      {est.estudiante.no_lista || idx + 1}
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={`font-medium ${esRetirado ? 'text-gray-400 line-through' : ''}`}>
                          {est.estudiante.nombre_completo}
                        </span>
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
                    {Array.from({ length: numCompetencias }, (_, i) => i + 1).map(n => {
                      const comp = est.competencias.find(c => c.competencia_numero === n);
                      const c = comp ? (calcularCompetencia(comp) ?? comp.final_competencia) : null;
                      return (
                        <td key={n} className={`px-3 py-2 text-center font-medium bg-indigo-50 ${esRetirado ? 'text-gray-400' : getNotaClass(c)}`}>
                          {c?.toFixed(2) ?? '—'}
                        </td>
                      );
                    })}
                    <td className={`px-3 py-2 text-center font-bold bg-green-50 ${esRetirado ? 'text-gray-400' : getNotaClass(cf)}`}>
                      {cf?.toFixed(2) ?? '—'}
                    </td>
                    <td className={`px-3 py-2 text-center font-bold bg-green-50 ${esRetirado ? 'text-gray-400' : getNotaClass(cf)}`}>
                      {esRetirado ? '—' : literal}
                    </td>
                    <td className="px-3 py-2 text-center">
                      {esRetirado ? (
                        <span className="px-2 py-1 rounded-full text-xs font-medium bg-gray-200 text-gray-600">
                          Retirado
                        </span>
                      ) : cf !== null && (
                        <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                          aprobado ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                        }`}>
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
      </div>
    </div>
  );
};

export default AcademicoPrimariaPage;
