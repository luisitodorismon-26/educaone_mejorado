import { useState, useEffect } from 'react';
import api from '../../services/api';
import { Button, Select, Alert } from '../../components/ui';

/**
 * R3.2 — Salida Optativa de un curso de 4to-6to de Secundaria.
 *
 * Vive DENTRO del modal de edición del curso (Configuración → Cursos), no en
 * un item nuevo del menú: la salida es un atributo del curso, como su tanda.
 *
 * Todo lo que se pinta sale del backend —las 4 salidas y los nombres oficiales
 * de los componentes llegan en la respuesta—, así que el frontend NO tiene
 * ninguna copia del catálogo MINERD que pueda quedar desincronizada.
 */

interface ComponenteEstado {
  componente_codigo: string;
  nombre_oficial: string;
  slot: number;
  horas_semana: number;
  asignatura_id: number | null;
  asignatura_nombre: string | null;
  tiene_historia: boolean;
  // R3.4
  identidad_independiente: boolean;
  profesor_id: number | null;
  profesor_nombre: string | null;
}

interface Profesor {
  id: number;
  nombre_completo?: string;
  nombre?: string;
  apellido?: string;
  role?: string;
  activo?: boolean;
}

interface SalidaEstado {
  curso_id: number;
  aplica: boolean;
  grado_numero: number | null;
  salida_optativa_codigo: string | null;
  salida_optativa_nombre: string | null;
  salidas_disponibles: { codigo: string; nombre: string }[];
  componentes: ComponenteEstado[];
  faltantes: string[];
  configurada: boolean;
}

interface Asignatura {
  id: number;
  nombre: string;
}

export const SalidaOptativaSection = ({ cursoId, asignaturas }: {
  cursoId: number;
  asignaturas: Asignatura[];
}) => {
  const [estado, setEstado] = useState<SalidaEstado | null>(null);
  const [salida, setSalida] = useState<string>('');
  const [mapeos, setMapeos] = useState<Record<string, number | null>>({});
  // R3.4: profesor responsable por componente. Es LO ÚNICO que Dirección
  // necesita elegir: el backend garantiza la identidad calificable del
  // componente y deja la asignación docente activa.
  const [profes, setProfes] = useState<Record<string, number | null>>({});
  const [profesores, setProfesores] = useState<Profesor[]>([]);
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  const aplicar = (d: SalidaEstado) => {
    setEstado(d);
    setSalida(d.salida_optativa_codigo || '');
    const m: Record<string, number | null> = {};
    const p: Record<string, number | null> = {};
    d.componentes.forEach(c => {
      m[c.componente_codigo] = c.asignatura_id;
      p[c.componente_codigo] = c.profesor_id;
    });
    setMapeos(m);
    setProfes(p);
  };

  const cargar = async () => {
    setCargando(true);
    setError(null);
    try {
      const r = await api.get(`/cursos/${cursoId}/salida-optativa`);
      aplicar(r.data);
    } catch (e: any) {
      setError(e.response?.data?.error || 'No se pudo cargar la Salida Optativa');
    } finally {
      setCargando(false);
    }
  };

  const cargarProfesores = async () => {
    try {
      const r = await api.get('/usuarios');
      setProfesores((r.data || []).filter((u: Profesor) => u.role === 'profesor'));
    } catch {
      setProfesores([]);
    }
  };

  useEffect(() => { cargar(); cargarProfesores(); /* eslint-disable-next-line */ }, [cursoId]);

  // Cambiar de salida cambia el juego de componentes: se piden al backend
  // guardando solo la salida, y él responde con los componentes que tocan.
  const cambiarSalida = async (codigo: string) => {
    setSalida(codigo);
    setError(null);
    setOk(null);
    setGuardando(true);
    try {
      const r = await api.put(`/cursos/${cursoId}/salida-optativa`, {
        salida_optativa_codigo: codigo || null,
      });
      aplicar(r.data);
    } catch (e: any) {
      // 409 = hay datos académicos. Se revierte el selector para que la
      // pantalla no muestre un estado que el servidor no aceptó.
      setError(e.response?.data?.error || 'No se pudo cambiar la Salida Optativa');
      setSalida(estado?.salida_optativa_codigo || '');
    } finally {
      setGuardando(false);
    }
  };

  const guardar = async () => {
    setError(null);
    setOk(null);
    setGuardando(true);
    try {
      // Se manda SOLO lo que Dirección eligió. `profesores` es la vía normal:
      // el backend crea o reutiliza la identidad calificable del componente y
      // deja la asignación docente activa, sin pasos manuales.
      const soloProfes: Record<string, number | null> = {};
      Object.entries(profes).forEach(([cod, pid]) => {
        if (pid) soloProfes[cod] = pid;
      });
      const r = await api.put(`/cursos/${cursoId}/salida-optativa`, {
        salida_optativa_codigo: salida || null,
        componentes: mapeos,
        ...(Object.keys(soloProfes).length ? { profesores: soloProfes } : {}),
      });
      aplicar(r.data);
      setOk('Configuración guardada');
    } catch (e: any) {
      setError(e.response?.data?.error || 'No se pudo guardar la configuración');
    } finally {
      setGuardando(false);
    }
  };

  if (cargando) return <div className="text-sm text-gray-500 py-2">Cargando Salida Optativa…</div>;
  // 1ro-3ro de Secundaria y toda Primaria: la sección NO existe.
  if (!estado || !estado.aplica) return null;

  const faltan = estado.componentes.filter(
    c => !mapeos[c.componente_codigo] && !profes[c.componente_codigo]).length;
  const sinProfesor = estado.componentes.filter(c => !profes[c.componente_codigo]).length;

  return (
    <div className="border-t pt-4 mt-2">
      <h4 className="font-semibold text-gray-800 mb-1">Salida Optativa — Modalidad Académica</h4>
      <p className="text-xs text-gray-500 mb-3">
        Solo para {estado.grado_numero}to de Secundaria. Elige el profesor responsable de
        cada componente oficial: se califica aparte de la materia troncal.
      </p>

      {error && <div className="mb-3"><Alert variant="error">{error}</Alert></div>}
      {ok && <div className="mb-3"><Alert variant="success">{ok}</Alert></div>}

      <Select
        label="Salida Optativa"
        value={salida}
        disabled={guardando}
        onChange={e => cambiarSalida(e.target.value)}
        options={estado.salidas_disponibles.map(s => ({
          value: s.codigo, label: `${s.nombre} (${s.codigo})`,
        }))}
        placeholder="Sin Salida Optativa"
      />

      {salida && estado.componentes.length > 0 && (
        <div className="mt-4 space-y-3">
          <p className="text-xs font-semibold text-gray-500 uppercase">Componentes oficiales</p>
          {estado.componentes.map(c => (
            <div key={c.componente_codigo} className="border rounded-md p-3 bg-gray-50">
              <p className="font-medium text-gray-800 text-sm">{c.nombre_oficial}</p>
              <p className="text-xs text-gray-500 mb-2">
                {c.componente_codigo} · {c.horas_semana} h/semana
              </p>

              {/* R3.4: elegir el profesor es TODO lo que Dirección tiene que
                  hacer. EducaOne se encarga de darle al componente su propia
                  identidad calificable y de dejar la asignación activa. */}
              <Select
                label="Profesor responsable"
                value={profes[c.componente_codigo] || 0}
                disabled={guardando}
                onChange={e => setProfes({
                  ...profes,
                  [c.componente_codigo]: parseInt(e.target.value) || null,
                })}
                options={profesores.map(p => ({
                  value: p.id,
                  label: p.nombre_completo || `${p.nombre || ''} ${p.apellido || ''}`.trim(),
                }))}
                placeholder="Sin asignar"
              />

              {c.asignatura_id && (
                <p className="text-xs text-gray-500 mt-2">
                  Se califica como <strong>{c.asignatura_nombre}</strong>, aparte de la
                  materia troncal.
                  {!c.identidad_independiente && (
                    <span className="text-amber-700">
                      {' '}Hoy apunta a una materia del Registro; al guardar se le dará
                      identidad propia y las notas de esa materia no se tocan.
                    </span>
                  )}
                </p>
              )}

              {/* Vía manual de R3.2, como respaldo: Dirección puede elegir una
                  materia suya en vez de dejar que EducaOne cree la dedicada. */}
              <details className="mt-2">
                <summary className="text-xs text-gray-500 cursor-pointer">
                  Vincular a una asignatura existente (opcional)
                </summary>
                <div className="mt-2">
                  <Select
                    label=""
                    value={mapeos[c.componente_codigo] || 0}
                    disabled={guardando || c.tiene_historia}
                    onChange={e => setMapeos({
                      ...mapeos,
                      [c.componente_codigo]: parseInt(e.target.value) || null,
                    })}
                    options={asignaturas.map(a => ({ value: a.id, label: a.nombre }))}
                    placeholder="Sin vincular"
                  />
                </div>
              </details>

              {c.tiene_historia && (
                <p className="text-xs text-amber-700 mt-1">
                  Ya tiene datos académicos registrados: no se puede cambiar la
                  asignatura vinculada.
                </p>
              )}
            </div>
          ))}

          <div className="flex items-center justify-between pt-2">
            {faltan === 0 && sinProfesor === 0 ? (
              <span className="text-sm text-green-700">✅ Configurada</span>
            ) : faltan > 0 ? (
              <span className="text-sm text-amber-700">
                ⚠️ Falta vincular {faltan} componente{faltan === 1 ? '' : 's'}
              </span>
            ) : (
              <span className="text-sm text-amber-700">
                ⚠️ Falta el profesor de {sinProfesor} componente{sinProfesor === 1 ? '' : 's'}
              </span>
            )}
            <Button onClick={guardar} loading={guardando} size="sm">
              Guardar configuración
            </Button>
          </div>
        </div>
      )}
    </div>
  );
};
