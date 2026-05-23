import { useState, useEffect } from 'react';
import api from '../../services/api';

interface Acceso {
  id: number;
  usuario: string;
  usuario_role: string;
  accion: string;
  detalle: string;
  ip: string;
  fecha: string;
}

interface Auditoria {
  id: number;
  usuario: string;
  accion: string;
  tabla: string;
  registro_id: number;
  ip: string;
  fecha: string;
}

export const AuditoriaPage = () => {
  const [activeTab, setActiveTab] = useState('accesos');
  const [accesos, setAccesos] = useState<Acceso[]>([]);
  const [auditoria, setAuditoria] = useState<Auditoria[]>([]);
  const [loading, setLoading] = useState(true);
  const [filtro, setFiltro] = useState({ accion: '', tabla: '' });

  useEffect(() => {
    loadData();
  }, [activeTab, filtro]);

  const loadData = async () => {
    setLoading(true);
    try {
      if (activeTab === 'accesos') {
        const res = await api.get('/auditoria/accesos');
        setAccesos(res.data);
      } else {
        let url = '/auditoria';
        const params = new URLSearchParams();
        if (filtro.accion) params.append('accion', filtro.accion);
        if (filtro.tabla) params.append('tabla', filtro.tabla);
        if (params.toString()) url += '?' + params.toString();
        const res = await api.get(url);
        setAuditoria(res.data);
      }
    } catch (e) {
      console.error('Error:', e);
    } finally {
      setLoading(false);
    }
  };

  const formatFecha = (fecha: string) => {
    return new Date(fecha).toLocaleString('es-DO', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit', hour12: true
    });
  };

  const getAccionColor = (accion: string) => {
    if (accion.includes('login')) return 'bg-green-100 text-green-800';
    if (accion.includes('logout')) return 'bg-gray-100 text-gray-800';
    if (accion.includes('crear')) return 'bg-blue-100 text-blue-800';
    if (accion.includes('editar')) return 'bg-yellow-100 text-yellow-800';
    if (accion.includes('eliminar')) return 'bg-red-100 text-red-800';
    return 'bg-gray-100 text-gray-800';
  };

  const getRoleColor = (role: string) => {
    const colors: Record<string, string> = {
      'direccion': 'text-purple-600',
      'coordinador': 'text-blue-600',
      'profesor': 'text-green-600',
      'psicologia': 'text-pink-600'
    };
    return colors[role] || 'text-gray-600';
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">📜 Auditoría del Sistema</h1>
        <p className="text-gray-500">Registro de accesos y acciones del sistema</p>
      </div>

      <div className="flex gap-2 border-b border-gray-200">
        <button
          onClick={() => setActiveTab('accesos')}
          className={`px-4 py-3 font-medium border-b-2 transition-colors ${
            activeTab === 'accesos' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500'
          }`}
        >
          🔐 Accesos
        </button>
        <button
          onClick={() => setActiveTab('acciones')}
          className={`px-4 py-3 font-medium border-b-2 transition-colors ${
            activeTab === 'acciones' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500'
          }`}
        >
          📋 Acciones
        </button>
      </div>

      {activeTab === 'acciones' && (
        <div className="flex gap-4 bg-white p-4 rounded-lg border border-gray-200">
          <select
            value={filtro.accion}
            onChange={e => setFiltro({...filtro, accion: e.target.value})}
            className="px-3 py-2 border border-gray-300 rounded-lg"
          >
            <option value="">Todas las acciones</option>
            <option value="crear">Crear</option>
            <option value="editar">Editar</option>
            <option value="eliminar">Eliminar</option>
          </select>
          <select
            value={filtro.tabla}
            onChange={e => setFiltro({...filtro, tabla: e.target.value})}
            className="px-3 py-2 border border-gray-300 rounded-lg"
          >
            <option value="">Todas las tablas</option>
            <option value="estudiantes">Estudiantes</option>
            <option value="users">Usuarios</option>
            <option value="cursos">Cursos</option>
          </select>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
        </div>
      ) : (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
          {activeTab === 'accesos' ? (
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-600">Fecha</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-600">Usuario</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-600">Acción</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-600">Detalle</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-600">IP</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {accesos.map(a => (
                  <tr key={a.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-sm text-gray-500">{formatFecha(a.fecha)}</td>
                    <td className="px-4 py-3">
                      <span className={`font-medium ${getRoleColor(a.usuario_role)}`}>{a.usuario}</span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-1 rounded-full text-xs font-medium ${getAccionColor(a.accion)}`}>
                        {a.accion}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600 max-w-xs truncate">{a.detalle}</td>
                    <td className="px-4 py-3 text-sm text-gray-400 font-mono">{a.ip}</td>
                  </tr>
                ))}
                {accesos.length === 0 && (
                  <tr><td colSpan={5} className="px-4 py-12 text-center text-gray-500">No hay registros</td></tr>
                )}
              </tbody>
            </table>
          ) : (
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-600">Fecha</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-600">Usuario</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-600">Acción</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-600">Tabla</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-600">ID</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {auditoria.map(a => (
                  <tr key={a.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-sm text-gray-500">{formatFecha(a.fecha)}</td>
                    <td className="px-4 py-3 font-medium">{a.usuario}</td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-1 rounded-full text-xs font-medium ${getAccionColor(a.accion)}`}>
                        {a.accion}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm">{a.tabla}</td>
                    <td className="px-4 py-3 text-sm text-gray-400">#{a.registro_id}</td>
                  </tr>
                ))}
                {auditoria.length === 0 && (
                  <tr><td colSpan={5} className="px-4 py-12 text-center text-gray-500">No hay registros</td></tr>
                )}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
};

export default AuditoriaPage;
