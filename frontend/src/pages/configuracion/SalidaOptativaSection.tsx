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
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  const aplicar = (d: SalidaEstado) => {
    setEstado(d);
    setSalida(d.salida_optativa_codigo || '');
    const m: Record<string, number | null> = {};
    d.componentes.forEach(c => { m[c.componente_codigo] = c.asignatura_id; });
    setMapeos(m);
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

  useEffect(() => { cargar(); /* eslint-disable-next-line */ }, [cursoId]);

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
      const r = await api.put(`/cursos/${cursoId}/salida-optativa`, {
        salida_optativa_codigo: salida || null,
        componentes: mapeos,
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

  const faltan = estado.componentes.filter(c => !mapeos[c.componente_codigo]).length;

  return (
    <div className="border-t pt-4 mt-2">
      <h4 className="font-semibold text-gray-800 mb-1">Salida Optativa — Modalidad Académica</h4>
      <p className="text-xs text-gray-500 mb-3">
        Solo para {estado.grado_numero}to de Secundaria. Define qué asignatura del colegio
        imparte cada componente oficial del Registro.
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
            <div key={c.componente_codigo}>
              <Select
                label={`${c.nombre_oficial} (${c.horas_semana} h/sem)`}
                value={mapeos[c.componente_codigo] || 0}
                disabled={guardando || c.tiene_historia}
                onChange={e => setMapeos({
                  ...mapeos,
                  [c.componente_codigo]: parseInt(e.target.value) || null,
                })}
                options={asignaturas.map(a => ({ value: a.id, label: a.nombre }))}
                placeholder="Sin vincular"
              />
              {c.tiene_historia && (
                <p className="text-xs text-amber-700 mt-1">
                  Ya tiene datos académicos registrados: no se puede cambiar.
                </p>
              )}
            </div>
          ))}

          <div className="flex items-center justify-between pt-2">
            {faltan === 0 ? (
              <span className="text-sm text-green-700">✅ Configurada</span>
            ) : (
              <span className="text-sm text-amber-700">
                ⚠️ Falta vincular {faltan} componente{faltan === 1 ? '' : 's'}
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
