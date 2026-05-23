import { useState, useEffect } from 'react';
import api from '../../services/api';
import { Card, Button, Badge, Alert, Modal, Spinner } from '../../components/ui';
import { Calendar, Lock, GraduationCap, CheckCircle, AlertTriangle, Users } from 'lucide-react';

interface AnoEscolar {
  id: number;
  nombre: string;
  fecha_inicio: string;
  fecha_fin: string;
  activo: boolean;
  cerrado: boolean;
  periodo_activo: number;
}

interface ResumenCurso {
  id: number;
  nombre: string;
  estudiantes: number;
  promovidos: number;
  reprobados: number;
  promedio: number;
}

interface EstudiantePromocion {
  id: number;
  nombre_completo: string;
  matricula: string;
  curso: string;
  curso_id: number;
  promedio_general: number;
  asignaturas_aprobadas: number;
  asignaturas_reprobadas: number;
  total_asignaturas: number;
  asistencia_porcentaje: number;
  condicion: 'promovido' | 'reprobado' | 'pendiente';
  nuevo_grado: string | null;
}

export const CierreAnoPage = () => {
  const [anoEscolar, setAnoEscolar] = useState<AnoEscolar | null>(null);
  const [resumenCursos, setResumenCursos] = useState<ResumenCurso[]>([]);
  const [estudiantesPromocion, setEstudiantesPromocion] = useState<EstudiantePromocion[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingPromocion, setLoadingPromocion] = useState(false);
  
  const [paso, setPaso] = useState(1);
  const [showConfirmCierre, setShowConfirmCierre] = useState(false);
  const [showConfirmPromocion, setShowConfirmPromocion] = useState(false);
  const [procesando, setProcesando] = useState(false);
  const [message, setMessage] = useState<{type: 'success' | 'error' | 'warning'; text: string} | null>(null);
  
  const [nuevoAno, setNuevoAno] = useState({
    nombre: '',
    fecha_inicio: '',
    fecha_fin: ''
  });
  const [nuevoAnoId, setNuevoAnoId] = useState<number | null>(null);
  // v2.13.26: acción por estudiante: 'promueve' (default) | 'repite' | 'retira'
  const [acciones, setAcciones] = useState<Record<number, 'promueve' | 'repite' | 'retira'>>({});

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const anoRes = await api.get('/ano-escolar');
      setAnoEscolar(anoRes.data);
      
      // Cargar resumen real de cursos
      const resumenRes = await api.get('/cierre-ano/resumen').catch(() => ({ data: { cursos: [] } }));
      setResumenCursos(resumenRes.data.cursos || []);
      
      if (anoRes.data?.cerrado) {
        setPaso(3);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const cargarDatosPromocion = async () => {
    setLoadingPromocion(true);
    try {
      const res = await api.get('/cierre-ano/promocion');
      setEstudiantesPromocion(res.data.estudiantes || []);
    } catch (e) {
      console.error(e);
      setMessage({ type: 'error', text: 'Error al cargar datos de promoción' });
    } finally {
      setLoadingPromocion(false);
    }
  };

  const handleCerrarAno = async () => {
    setProcesando(true);
    try {
      await api.post(`/ano-escolar/${anoEscolar?.id}/cerrar`);
      setMessage({ type: 'success', text: 'Año escolar cerrado. Ahora creá el nuevo año escolar.' });
      setShowConfirmCierre(false);
      setPaso(3);
      loadData();
    } catch (e: any) {
      setMessage({ type: 'error', text: e.response?.data?.error || 'Error al cerrar el año' });
    } finally {
      setProcesando(false);
    }
  };

  const handlePromoverEstudiantes = async () => {
    setProcesando(true);
    try {
      // v2.13.24: promover pasando el año destino. Sin esto, los
      // estudiantes no tienen a dónde moverse y quedan en el mismo grado.
      // v2.13.26: enviar overrides solo de los que NO son 'promueve'
      const overrides: Record<number, string> = {};
      Object.entries(acciones).forEach(([id, acc]) => {
        if (acc && acc !== 'promueve') overrides[Number(id)] = acc;
      });
      const res = await api.post('/cierre-ano/promover', {
        ...(nuevoAnoId ? { nuevo_ano_id: nuevoAnoId } : {}),
        ...(Object.keys(overrides).length ? { overrides } : {}),
      });
      const d = res.data || {};
      const partes = [];
      if (d.promovidos) partes.push(`${d.promovidos} promovidos`);
      if (d.repitentes) partes.push(`${d.repitentes} repitentes`);
      if (d.retirados) partes.push(`${d.retirados} retirados`);
      if (d.egresados) partes.push(`${d.egresados} egresados`);
      const detalle = partes.length ? ` (${partes.join(', ')})` : '';
      if (d.aviso) {
        setMessage({ type: 'warning', text: d.aviso });
      } else {
        setMessage({ type: 'success', text: `Promoción completada${detalle}.` });
      }
      setShowConfirmPromocion(false);
      setPaso(5);
    } catch (e: any) {
      setMessage({ type: 'error', text: e.response?.data?.error || 'Error al promover estudiantes' });
    } finally {
      setProcesando(false);
    }
  };

  const handleCrearNuevoAno = async () => {
    if (!nuevoAno.nombre || !nuevoAno.fecha_inicio || !nuevoAno.fecha_fin) {
      setMessage({ type: 'error', text: 'Complete todos los campos' });
      return;
    }
    setProcesando(true);
    try {
      // 1. Crear el año nuevo
      const res = await api.post('/ano-escolar', nuevoAno);
      const anoId = res.data?.id;
      setNuevoAnoId(anoId);
      // 2. Clonar la estructura de cursos del año cerrado al nuevo
      //    (necesario para tener a dónde promover)
      let avisoClonado = '';
      try {
        const clon = await api.post(`/ano-escolar/${anoId}/clonar-cursos`,
          anoEscolar?.id ? { origen_ano_id: anoEscolar.id } : {});
        avisoClonado = clon.data?.creados
          ? ` Se prepararon ${clon.data.creados} cursos.`
          : '';
      } catch {
        avisoClonado = ' (No se pudieron clonar los cursos automáticamente; revisá que existan los cursos del nuevo año antes de promover.)';
      }
      setMessage({ type: 'success', text: `Nuevo año escolar creado y activado.${avisoClonado} Ahora promové los estudiantes.` });
      setPaso(4);
      loadData();
      await cargarDatosPromocion();
    } catch (e: any) {
      setMessage({ type: 'error', text: e.response?.data?.error || 'Error al crear año escolar' });
    } finally {
      setProcesando(false);
    }
  };

  const getResumenTotales = () => {
    return resumenCursos.reduce((acc, c) => ({
      estudiantes: acc.estudiantes + c.estudiantes,
      promovidos: acc.promovidos + c.promovidos,
      reprobados: acc.reprobados + c.reprobados
    }), { estudiantes: 0, promovidos: 0, reprobados: 0 });
  };

  if (loading) {
    return <div className="flex justify-center py-12"><Spinner size="lg" /></div>;
  }

  const resumenTotales = getResumenTotales();

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <Calendar className="text-blue-600" />
          Cierre de Año Escolar
        </h1>
        <p className="text-gray-500">Proceso de cierre y promoción de estudiantes</p>
      </div>

      {message && (
        <Alert variant={message.type} onClose={() => setMessage(null)}>{message.text}</Alert>
      )}

      {/* Año Escolar Actual */}
      <div className="bg-white rounded-xl shadow-sm border p-6">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h2 className="text-xl font-bold text-gray-900">{anoEscolar?.nombre || 'Sin año escolar'}</h2>
            <p className="text-gray-500">
              {anoEscolar?.fecha_inicio} al {anoEscolar?.fecha_fin}
            </p>
            {anoEscolar && !anoEscolar.cerrado && (
              <p className="text-sm text-blue-600 mt-1">
                Período activo: P{anoEscolar.periodo_activo}
              </p>
            )}
          </div>
          <Badge variant={anoEscolar?.cerrado ? 'danger' : 'success'} className="text-lg px-4 py-2">
            {anoEscolar?.cerrado ? (
              <span className="flex items-center gap-1"><Lock size={16} /> Cerrado</span>
            ) : (
              <span className="flex items-center gap-1"><CheckCircle size={16} /> Activo</span>
            )}
          </Badge>
        </div>
      </div>

      {/* Pasos del proceso */}
      <div className="flex items-center justify-between bg-white rounded-lg border p-4 overflow-x-auto">
        {[
          { num: 1, label: 'Revisar', icon: <Users size={18} /> },
          { num: 2, label: 'Cerrar Año', icon: <Lock size={18} /> },
          { num: 3, label: 'Nuevo Año', icon: <Calendar size={18} /> },
          { num: 4, label: 'Promover', icon: <GraduationCap size={18} /> }
        ].map((p, i) => (
          <div key={p.num} className="flex items-center">
            <div className={`flex items-center justify-center w-10 h-10 rounded-full ${
              paso >= p.num ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-500'
            }`}>
              {paso > p.num ? <CheckCircle size={18} /> : p.icon}
            </div>
            <span className={`ml-2 text-sm font-medium whitespace-nowrap ${paso >= p.num ? 'text-blue-600' : 'text-gray-500'}`}>
              {p.label}
            </span>
            {i < 3 && <div className={`w-8 sm:w-16 h-1 mx-2 ${paso > p.num ? 'bg-blue-600' : 'bg-gray-200'}`} />}
          </div>
        ))}
      </div>

      {/* Paso 1: Resumen */}
      {paso === 1 && (
        <>
          {/* KPIs */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-white rounded-xl shadow-sm border p-4 text-center">
              <p className="text-3xl font-bold text-blue-600">{resumenTotales.estudiantes}</p>
              <p className="text-sm text-gray-500">Total Estudiantes</p>
            </div>
            <div className="bg-white rounded-xl shadow-sm border p-4 text-center">
              <p className="text-3xl font-bold text-emerald-600">{resumenTotales.promovidos}</p>
              <p className="text-sm text-gray-500">Promovidos</p>
            </div>
            <div className="bg-white rounded-xl shadow-sm border p-4 text-center">
              <p className="text-3xl font-bold text-red-600">{resumenTotales.reprobados}</p>
              <p className="text-sm text-gray-500">Reprobados</p>
            </div>
            <div className="bg-white rounded-xl shadow-sm border p-4 text-center">
              <p className="text-3xl font-bold text-purple-600">
                {resumenTotales.estudiantes > 0 
                  ? Math.round((resumenTotales.promovidos / resumenTotales.estudiantes) * 100) 
                  : 0}%
              </p>
              <p className="text-sm text-gray-500">Tasa Promoción</p>
            </div>
          </div>

          {/* Tabla de cursos */}
          <div className="bg-white rounded-xl shadow-sm border overflow-hidden">
            <div className="p-4 border-b">
              <h3 className="font-bold text-gray-800">Resumen por Curso</h3>
            </div>
            
            {resumenCursos.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-3 text-left text-sm font-medium text-gray-600">Curso</th>
                      <th className="px-4 py-3 text-center text-sm font-medium text-gray-600">Estudiantes</th>
                      <th className="px-4 py-3 text-center text-sm font-medium text-gray-600">Promovidos</th>
                      <th className="px-4 py-3 text-center text-sm font-medium text-gray-600">Reprobados</th>
                      <th className="px-4 py-3 text-center text-sm font-medium text-gray-600">Promedio</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {resumenCursos.map(curso => (
                      <tr key={curso.id} className="hover:bg-gray-50">
                        <td className="px-4 py-3 font-medium">{curso.nombre}</td>
                        <td className="px-4 py-3 text-center">{curso.estudiantes}</td>
                        <td className="px-4 py-3 text-center">
                          <span className="text-emerald-600 font-medium">{curso.promovidos}</span>
                        </td>
                        <td className="px-4 py-3 text-center">
                          <span className="text-red-600 font-medium">{curso.reprobados}</span>
                        </td>
                        <td className="px-4 py-3 text-center">
                          <Badge variant={curso.promedio >= 80 ? 'success' : curso.promedio >= 70 ? 'warning' : 'danger'}>
                            {curso.promedio.toFixed(1)}
                          </Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="p-8 text-center text-gray-500">
                <Users size={48} className="mx-auto mb-4 text-gray-300" />
                <p>No hay datos de cursos disponibles</p>
                <p className="text-sm mt-2">Asegúrese de que haya estudiantes con calificaciones registradas</p>
              </div>
            )}

            <div className="p-4 border-t flex justify-end">
              <Button 
                onClick={() => setShowConfirmCierre(true)} 
                variant="danger"
                icon={<Lock size={18} />}
                disabled={!anoEscolar || anoEscolar.cerrado}
              >
                Proceder al Cierre
              </Button>
            </div>
          </div>
        </>
      )}

      {/* Paso 4: Promoción */}
      {paso === 4 && (
        <div className="bg-white rounded-xl shadow-sm border overflow-hidden">
          <div className="p-4 border-b">
            <h3 className="font-bold text-gray-800 flex items-center gap-2">
              <GraduationCap className="text-blue-600" />
              Promoción de Estudiantes
            </h3>
          </div>

          <Alert variant="warning" className="m-4">
            <AlertTriangle size={18} className="inline mr-2" />
            El nuevo año escolar está creado. Al promover, los estudiantes pasan al grado siguiente en el nuevo año. Los de último grado quedan como egresados.
          </Alert>

          {loadingPromocion ? (
            <div className="p-8 text-center">
              <Spinner size="lg" />
              <p className="mt-2 text-gray-500">Cargando datos de promoción...</p>
            </div>
          ) : estudiantesPromocion.length > 0 ? (
            <>
              {/* Resumen según lo marcado */}
              <div className="grid grid-cols-4 gap-4 p-4">
                <div className="bg-emerald-50 rounded-lg p-3 text-center">
                  <p className="text-2xl font-bold text-emerald-600">
                    {estudiantesPromocion.filter(e => (acciones[e.id] || 'promueve') === 'promueve').length}
                  </p>
                  <p className="text-sm text-emerald-700">Promueven</p>
                </div>
                <div className="bg-amber-50 rounded-lg p-3 text-center">
                  <p className="text-2xl font-bold text-amber-600">
                    {estudiantesPromocion.filter(e => acciones[e.id] === 'repite').length}
                  </p>
                  <p className="text-sm text-amber-700">Repiten</p>
                </div>
                <div className="bg-red-50 rounded-lg p-3 text-center">
                  <p className="text-2xl font-bold text-red-600">
                    {estudiantesPromocion.filter(e => acciones[e.id] === 'retira').length}
                  </p>
                  <p className="text-sm text-red-700">Se retiran</p>
                </div>
                <div className="bg-blue-50 rounded-lg p-3 text-center">
                  <p className="text-2xl font-bold text-blue-600">{estudiantesPromocion.length}</p>
                  <p className="text-sm text-blue-700">Total</p>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-3 text-left font-medium text-gray-600">Estudiante</th>
                      <th className="px-4 py-3 text-center font-medium text-gray-600">Curso Actual</th>
                      <th className="px-4 py-3 text-center font-medium text-gray-600">Promedio</th>
                      <th className="px-4 py-3 text-center font-medium text-gray-600">Asignaturas</th>
                      <th className="px-4 py-3 text-center font-medium text-gray-600">Asistencia</th>
                      <th className="px-4 py-3 text-center font-medium text-gray-600">Condición</th>
                      <th className="px-4 py-3 text-center font-medium text-gray-600">Nuevo Grado</th>
                      <th className="px-4 py-3 text-center font-medium text-gray-600">Acción</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {estudiantesPromocion.map(est => (
                      <tr key={est.id} className="hover:bg-gray-50">
                        <td className="px-4 py-3">
                          <p className="font-medium">{est.nombre_completo}</p>
                          <p className="text-xs text-gray-400">{est.matricula}</p>
                        </td>
                        <td className="px-4 py-3 text-center">{est.curso}</td>
                        <td className="px-4 py-3 text-center">
                          <span className={est.promedio_general >= 70 ? 'text-emerald-600 font-bold' : 'text-red-600 font-bold'}>
                            {est.promedio_general.toFixed(1)}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-center">
                          <span className="text-emerald-600">{est.asignaturas_aprobadas}</span>
                          <span className="text-gray-400">/</span>
                          <span className="text-red-600">{est.asignaturas_reprobadas}</span>
                          <span className="text-gray-400">/{est.total_asignaturas}</span>
                        </td>
                        <td className="px-4 py-3 text-center">{est.asistencia_porcentaje.toFixed(0)}%</td>
                        <td className="px-4 py-3 text-center">
                          <Badge variant={est.condicion === 'promovido' ? 'success' : 'danger'}>
                            {est.condicion === 'promovido' ? 'Promovido' : 'Reprobado'}
                          </Badge>
                        </td>
                        <td className="px-4 py-3 text-center font-medium text-blue-600">
                          {(acciones[est.id] || 'promueve') === 'retira'
                            ? <span className="text-red-500">Se retira</span>
                            : (acciones[est.id] || 'promueve') === 'repite'
                              ? <span className="text-amber-600">Repite {est.curso}</span>
                              : (est.nuevo_grado || '-')}
                        </td>
                        <td className="px-4 py-3 text-center">
                          <select
                            value={acciones[est.id] || 'promueve'}
                            onChange={e => setAcciones(prev => ({ ...prev, [est.id]: e.target.value as any }))}
                            className="px-2 py-1.5 border border-gray-300 rounded-lg text-xs focus:ring-2 focus:ring-blue-500"
                          >
                            <option value="promueve">Promover</option>
                            <option value="repite">Repite el grado</option>
                            <option value="retira">Se retira</option>
                          </select>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <div className="p-8 text-center">
              <Button onClick={cargarDatosPromocion} loading={loadingPromocion}>
                Cargar Datos de Promoción
              </Button>
            </div>
          )}

          <div className="p-4 border-t flex justify-end gap-3">
            <Button variant="secondary" onClick={() => setPaso(3)}>← Volver</Button>
            <Button 
              onClick={() => setShowConfirmPromocion(true)}
              icon={<GraduationCap size={18} />}
            >
              Ejecutar Promoción
            </Button>
          </div>
        </div>
      )}

      {/* Paso 3: Nuevo Año */}
      {paso === 3 && (
        <div className="bg-white rounded-xl shadow-sm border p-6">
          <h3 className="font-bold text-gray-800 flex items-center gap-2 mb-4">
            <Calendar className="text-blue-600" />
            Crear Nuevo Año Escolar
          </h3>

          <Alert variant="success" className="mb-6">
            <CheckCircle size={18} className="inline mr-2" />
            El año escolar fue cerrado. Creá el nuevo año escolar: se activará y se prepararán automáticamente los cursos para promover a los estudiantes.
          </Alert>

          <div className="max-w-md space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Nombre del Año Escolar</label>
              <input
                type="text"
                value={nuevoAno.nombre}
                onChange={e => setNuevoAno({ ...nuevoAno, nombre: e.target.value })}
                placeholder="Ej: 2025-2026"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Fecha Inicio</label>
                <input
                  type="date"
                  value={nuevoAno.fecha_inicio}
                  onChange={e => setNuevoAno({ ...nuevoAno, fecha_inicio: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Fecha Fin</label>
                <input
                  type="date"
                  value={nuevoAno.fecha_fin}
                  onChange={e => setNuevoAno({ ...nuevoAno, fecha_fin: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>
          </div>

          <div className="mt-6 flex justify-end gap-3">
            <Button onClick={handleCrearNuevoAno} loading={procesando} icon={<Calendar size={18} />}>
              Crear Año y Continuar
            </Button>
          </div>
        </div>
      )}

      {/* Paso 5: Completado */}
      {paso === 5 && (
        <div className="bg-white rounded-xl shadow-sm border p-12 text-center">
          <div className="text-6xl mb-4">🎉</div>
          <h2 className="text-2xl font-bold text-gray-900 mb-2">¡Proceso Completado!</h2>
          <p className="text-gray-500 mb-6">
            El año escolar anterior ha sido cerrado, los estudiantes han sido promovidos
            y el nuevo año escolar está activo.
          </p>
          <div className="flex justify-center gap-3">
            <Button variant="secondary" onClick={() => window.location.href = '/configuracion'}>
              Ir a Configuración
            </Button>
            <Button onClick={() => window.location.href = '/dashboard'}>
              Ir al Dashboard
            </Button>
          </div>
        </div>
      )}

      {/* Modal Confirmar Cierre */}
      <Modal
        isOpen={showConfirmCierre}
        onClose={() => setShowConfirmCierre(false)}
        title="Confirmar Cierre de Año"
        size="md"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowConfirmCierre(false)}>Cancelar</Button>
            <Button variant="danger" onClick={handleCerrarAno} loading={procesando}>
              Sí, Cerrar Año
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Alert variant="warning">
            <strong>¡Atención!</strong> Esta acción es irreversible.
          </Alert>
          <p>Al cerrar el año escolar:</p>
          <ul className="list-disc list-inside space-y-1 text-gray-600 text-sm">
            <li>Se generará el historial académico de todos los estudiantes</li>
            <li>No se podrán modificar calificaciones del año actual</li>
            <li>Se bloqueará el registro de asistencia</li>
            <li>Los boletines quedarán como documentos finales</li>
          </ul>
          <p className="font-medium">¿Está seguro de que desea continuar?</p>
        </div>
      </Modal>

      {/* Modal Confirmar Promoción */}
      <Modal
        isOpen={showConfirmPromocion}
        onClose={() => setShowConfirmPromocion(false)}
        title="Confirmar Promoción"
        size="md"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowConfirmPromocion(false)}>Cancelar</Button>
            <Button onClick={handlePromoverEstudiantes} loading={procesando}>
              Ejecutar Promoción
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <p>Se realizarán las siguientes acciones:</p>
          <ul className="list-disc list-inside space-y-1 text-gray-600 text-sm">
            <li><strong className="text-emerald-600">{estudiantesPromocion.filter(e => (acciones[e.id] || 'promueve') === 'promueve').length}</strong> estudiantes pasan al grado siguiente (los de último grado egresan)</li>
            <li><strong className="text-amber-600">{estudiantesPromocion.filter(e => acciones[e.id] === 'repite').length}</strong> estudiantes repiten el grado actual</li>
            <li><strong className="text-red-600">{estudiantesPromocion.filter(e => acciones[e.id] === 'retira').length}</strong> estudiantes se retiran del colegio</li>
          </ul>
          <p className="font-medium">¿Desea continuar con la promoción?</p>
        </div>
      </Modal>
    </div>
  );
};

export default CierreAnoPage;
