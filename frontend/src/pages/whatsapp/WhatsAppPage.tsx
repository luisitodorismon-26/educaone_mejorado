import { useState, useEffect } from 'react';
import api from '../../services/api';
import { Card, Button, Select, Input, Textarea, Badge, Alert, Modal, Spinner } from '../../components/ui';

interface Plantilla {
  id: number;
  nombre: string;
  categoria: string;
  asunto: string;
  contenido: string;
  variables: string[];
}

interface Estudiante {
  id: number;
  nombre_completo: string;
  curso: string;
  telefono_padre: string;
  telefono_madre: string;
  nombre_padre: string;
  nombre_madre: string;
}

interface Curso {
  id: number;
  nombre_completo: string;
}

export const WhatsAppPage = () => {
  const [plantillas, setPlantillas] = useState<Plantilla[]>([]);
  const [estudiantes, setEstudiantes] = useState<Estudiante[]>([]);
  const [cursos, setCursos] = useState<Curso[]>([]);
  const [loading, setLoading] = useState(true);
  
  // Filtros y selección
  const [cursoId, setCursoId] = useState<number>(0);
  const [selectedEstudiantes, setSelectedEstudiantes] = useState<number[]>([]);
  const [selectAll, setSelectAll] = useState(false);
  
  // Mensaje
  const [plantillaId, setPlantillaId] = useState<number>(0);
  const [mensaje, setMensaje] = useState('');
  const [asunto, setAsunto] = useState('');
  
  // Variables personalizadas
  const [variables, setVariables] = useState<Record<string, string>>({});
  
  // Preview y envío
  const [showPreview, setShowPreview] = useState(false);
  const [linksGenerados, setLinksGenerados] = useState<{nombre: string; telefono: string; link: string}[]>([]);
  const [enviando, setEnviando] = useState(false);
  const [message, setMessage] = useState<{type: 'success' | 'error'; text: string} | null>(null);

  // Modal plantilla
  const [showPlantillaModal, setShowPlantillaModal] = useState(false);
  const [nuevaPlantilla, setNuevaPlantilla] = useState({ nombre: '', categoria: 'general', asunto: '', contenido: '' });

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    if (cursoId) loadEstudiantes();
  }, [cursoId]);

  useEffect(() => {
    if (plantillaId) {
      const p = plantillas.find(pl => pl.id === plantillaId);
      if (p) {
        setMensaje(p.contenido);
        setAsunto(p.asunto);
        // Extraer variables del mensaje
        const vars = p.contenido.match(/\{(\w+)\}/g)?.map(v => v.slice(1, -1)) || [];
        const varsObj: Record<string, string> = {};
        vars.forEach(v => varsObj[v] = '');
        setVariables(varsObj);
      }
    }
  }, [plantillaId]);

  const loadData = async () => {
    try {
      const [plantillasRes, cursosRes] = await Promise.all([
        api.get('/plantillas'),
        api.get('/cursos')
      ]);
      setPlantillas(plantillasRes.data);
      setCursos(cursosRes.data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const loadEstudiantes = async () => {
    try {
      const res = await api.get(`/estudiantes?curso_id=${cursoId}`);
      setEstudiantes(res.data);
      setSelectedEstudiantes([]);
      setSelectAll(false);
    } catch (e) {
      console.error(e);
    }
  };

  const handleSelectAll = () => {
    if (selectAll) {
      setSelectedEstudiantes([]);
    } else {
      setSelectedEstudiantes(estudiantes.filter(e => e.telefono_padre || e.telefono_madre).map(e => e.id));
    }
    setSelectAll(!selectAll);
  };

  const handleSelectEstudiante = (id: number) => {
    if (selectedEstudiantes.includes(id)) {
      setSelectedEstudiantes(selectedEstudiantes.filter(e => e !== id));
    } else {
      setSelectedEstudiantes([...selectedEstudiantes, id]);
    }
  };

  const procesarMensaje = (est: Estudiante) => {
    let msg = mensaje;
    // Reemplazar variables automáticas
    msg = msg.replace(/{estudiante}/g, est.nombre_completo);
    msg = msg.replace(/{curso}/g, est.curso || '');
    msg = msg.replace(/{padre}/g, est.nombre_padre || 'Padre/Madre');
    msg = msg.replace(/{madre}/g, est.nombre_madre || 'Padre/Madre');
    // Reemplazar variables personalizadas
    Object.entries(variables).forEach(([key, value]) => {
      msg = msg.replace(new RegExp(`{${key}}`, 'g'), value);
    });
    return msg;
  };

  const generarLinks = () => {
    const links: {nombre: string; telefono: string; link: string}[] = [];
    
    selectedEstudiantes.forEach(id => {
      const est = estudiantes.find(e => e.id === id);
      if (!est) return;
      
      const msg = procesarMensaje(est);
      const encoded = encodeURIComponent(msg);
      
      // Agregar link para padre si tiene teléfono
      if (est.telefono_padre) {
        const tel = est.telefono_padre.replace(/\D/g, '');
        const telFormatted = tel.startsWith('1') ? tel : (tel.startsWith('809') || tel.startsWith('829') || tel.startsWith('849')) ? `1${tel}` : tel;
        links.push({
          nombre: `${est.nombre_padre || 'Padre'} (${est.nombre_completo})`,
          telefono: est.telefono_padre,
          link: `https://wa.me/${telFormatted}?text=${encoded}`
        });
      }
      
      // Agregar link para madre si tiene teléfono diferente
      if (est.telefono_madre && est.telefono_madre !== est.telefono_padre) {
        const tel = est.telefono_madre.replace(/\D/g, '');
        const telFormatted = tel.startsWith('1') ? tel : (tel.startsWith('809') || tel.startsWith('829') || tel.startsWith('849')) ? `1${tel}` : tel;
        links.push({
          nombre: `${est.nombre_madre || 'Madre'} (${est.nombre_completo})`,
          telefono: est.telefono_madre,
          link: `https://wa.me/${telFormatted}?text=${encoded}`
        });
      }
    });
    
    setLinksGenerados(links);
    setShowPreview(true);
  };

  const handleGuardarPlantilla = async () => {
    try {
      await api.post('/plantillas', nuevaPlantilla);
      loadData();
      setShowPlantillaModal(false);
      setNuevaPlantilla({ nombre: '', categoria: 'general', asunto: '', contenido: '' });
      setMessage({ type: 'success', text: 'Plantilla guardada' });
    } catch (e) {
      setMessage({ type: 'error', text: 'Error al guardar plantilla' });
    }
  };

  const getCategoriaColor = (cat: string) => {
    const colors: Record<string, 'info' | 'warning' | 'danger' | 'success' | 'default'> = {
      conducta: 'warning',
      reunion: 'info',
      academico: 'default',
      asistencia: 'danger',
      citacion: 'warning',
      felicitacion: 'success',
      emergencia: 'danger'
    };
    return colors[cat] || 'default';
  };

  if (loading) {
    return <div className="flex justify-center py-12"><Spinner size="lg" /></div>;
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">📱 WhatsApp Masivo</h1>
          <p className="text-gray-500">Envía mensajes a padres de forma masiva</p>
        </div>
        <Button onClick={() => setShowPlantillaModal(true)} variant="secondary">
          + Nueva Plantilla
        </Button>
      </div>

      {message && (
        <Alert variant={message.type} onClose={() => setMessage(null)}>{message.text}</Alert>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Panel Izquierdo - Selección */}
        <div className="lg:col-span-1 space-y-4">
          <Card title="1️⃣ Seleccionar Destinatarios">
            <div className="space-y-4">
              <Select
                label="Curso"
                value={cursoId}
                onChange={e => setCursoId(parseInt(e.target.value))}
                options={cursos.map(c => ({ value: c.id, label: c.grado ? `${c.grado} ${c.nombre}` : c.nombre_completo, group: c.tanda || 'Sin tanda' }))}
                placeholder="Seleccionar curso"
              />

              {cursoId > 0 && estudiantes.length > 0 && (
                <>
                  <div className="flex justify-between items-center py-2 border-b">
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={selectAll}
                        onChange={handleSelectAll}
                        className="w-4 h-4 rounded border-gray-300"
                      />
                      <span className="text-sm font-medium">Seleccionar todos</span>
                    </label>
                    <Badge variant="info">{selectedEstudiantes.length} seleccionados</Badge>
                  </div>

                  <div className="max-h-64 overflow-y-auto space-y-1">
                    {estudiantes.map(est => {
                      const tieneContacto = est.telefono_padre || est.telefono_madre;
                      return (
                        <label
                          key={est.id}
                          className={`flex items-center gap-2 p-2 rounded cursor-pointer hover:bg-gray-50 ${
                            !tieneContacto ? 'opacity-50' : ''
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={selectedEstudiantes.includes(est.id)}
                            onChange={() => handleSelectEstudiante(est.id)}
                            disabled={!tieneContacto}
                            className="w-4 h-4 rounded border-gray-300"
                          />
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium truncate">{est.nombre_completo}</p>
                            <p className="text-xs text-gray-500">
                              {tieneContacto ? (
                                <>📞 {est.telefono_padre || est.telefono_madre}</>
                              ) : (
                                <span className="text-red-500">Sin teléfono</span>
                              )}
                            </p>
                          </div>
                        </label>
                      );
                    })}
                  </div>
                </>
              )}

              {cursoId > 0 && estudiantes.length === 0 && (
                <p className="text-center text-gray-500 py-4">No hay estudiantes en este curso</p>
              )}
            </div>
          </Card>
        </div>

        {/* Panel Central - Mensaje */}
        <div className="lg:col-span-2 space-y-4">
          <Card title="2️⃣ Componer Mensaje">
            <div className="space-y-4">
              <Select
                label="Usar Plantilla"
                value={plantillaId}
                onChange={e => setPlantillaId(parseInt(e.target.value))}
                options={plantillas.map(p => ({ value: p.id, label: `${p.nombre} (${p.categoria})` }))}
                placeholder="Seleccionar plantilla o escribir mensaje"
              />

              <Input
                label="Asunto (referencia interna)"
                value={asunto}
                onChange={e => setAsunto(e.target.value)}
                placeholder="Ej: Reunión de padres marzo"
              />

              <Textarea
                label="Mensaje"
                value={mensaje}
                onChange={e => setMensaje(e.target.value)}
                placeholder="Escribe tu mensaje aquí..."
                rows={6}
              />

              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                <p className="text-sm font-medium text-blue-800 mb-2">Variables disponibles:</p>
                <div className="flex flex-wrap gap-2">
                  {['{estudiante}', '{curso}', '{padre}', '{madre}', '{fecha}'].map(v => (
                    <button
                      key={v}
                      onClick={() => setMensaje(mensaje + ' ' + v)}
                      className="px-2 py-1 bg-white border border-blue-300 rounded text-xs text-blue-700 hover:bg-blue-100"
                    >
                      {v}
                    </button>
                  ))}
                </div>
              </div>

              {/* Variables personalizadas */}
              {Object.keys(variables).length > 0 && (
                <div className="border-t pt-4">
                  <p className="text-sm font-medium text-gray-700 mb-2">Variables personalizadas:</p>
                  <div className="grid grid-cols-2 gap-3">
                    {Object.entries(variables).map(([key, value]) => (
                      <Input
                        key={key}
                        label={key}
                        value={value}
                        onChange={e => setVariables({ ...variables, [key]: e.target.value })}
                        placeholder={`Valor para {${key}}`}
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>
          </Card>

          <Card title="3️⃣ Vista Previa y Envío">
            <div className="space-y-4">
              {selectedEstudiantes.length > 0 && mensaje && (
                <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                  <p className="text-sm font-medium text-green-800 mb-2">Vista previa del mensaje:</p>
                  <div className="bg-white rounded-lg p-3 shadow-sm">
                    <p className="text-sm whitespace-pre-wrap">
                      {procesarMensaje(estudiantes.find(e => e.id === selectedEstudiantes[0])!)}
                    </p>
                  </div>
                </div>
              )}

              <div className="flex justify-between items-center">
                <p className="text-sm text-gray-600">
                  {selectedEstudiantes.length} estudiantes seleccionados
                </p>
                <Button
                  onClick={generarLinks}
                  disabled={selectedEstudiantes.length === 0 || !mensaje}
                >
                  📱 Generar Links de WhatsApp
                </Button>
              </div>
            </div>
          </Card>
        </div>
      </div>

      {/* Plantillas Disponibles */}
      <Card title="📋 Plantillas Disponibles">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {plantillas.map(p => (
            <div
              key={p.id}
              className="p-4 border rounded-lg hover:border-blue-300 cursor-pointer transition-colors"
              onClick={() => setPlantillaId(p.id)}
            >
              <div className="flex justify-between items-start mb-2">
                <h4 className="font-medium">{p.nombre}</h4>
                <Badge variant={getCategoriaColor(p.categoria)}>{p.categoria}</Badge>
              </div>
              <p className="text-sm text-gray-500 line-clamp-2">{p.contenido}</p>
            </div>
          ))}
        </div>
      </Card>

      {/* Modal Links Generados */}
      <Modal
        isOpen={showPreview}
        onClose={() => setShowPreview(false)}
        title="📱 Links de WhatsApp Generados"
        size="xl"
      >
        <div className="space-y-4">
          <Alert variant="info">
            Haz clic en cada enlace para abrir WhatsApp con el mensaje pre-cargado.
            Deberás enviar cada mensaje manualmente.
          </Alert>

          <div className="max-h-96 overflow-y-auto space-y-2">
            {linksGenerados.map((link, idx) => (
              <div key={idx} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <div>
                  <p className="font-medium">{link.nombre}</p>
                  <p className="text-sm text-gray-500">{link.telefono}</p>
                </div>
                <a
                  href={link.link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 flex items-center gap-2"
                >
                  <span>📱</span> Abrir
                </a>
              </div>
            ))}
          </div>

          <div className="flex justify-between items-center pt-4 border-t">
            <p className="text-sm text-gray-500">{linksGenerados.length} contactos</p>
            <Button variant="secondary" onClick={() => setShowPreview(false)}>Cerrar</Button>
          </div>
        </div>
      </Modal>

      {/* Modal Nueva Plantilla */}
      <Modal
        isOpen={showPlantillaModal}
        onClose={() => setShowPlantillaModal(false)}
        title="Nueva Plantilla"
        size="lg"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowPlantillaModal(false)}>Cancelar</Button>
            <Button onClick={handleGuardarPlantilla}>Guardar Plantilla</Button>
          </>
        }
      >
        <div className="space-y-4">
          <Input
            label="Nombre de la plantilla"
            value={nuevaPlantilla.nombre}
            onChange={e => setNuevaPlantilla({ ...nuevaPlantilla, nombre: e.target.value })}
            placeholder="Ej: Convocatoria reunión"
          />
          <Select
            label="Categoría"
            value={nuevaPlantilla.categoria}
            onChange={e => setNuevaPlantilla({ ...nuevaPlantilla, categoria: e.target.value })}
            options={[
              { value: 'conducta', label: 'Conducta' },
              { value: 'reunion', label: 'Reunión' },
              { value: 'academico', label: 'Académico' },
              { value: 'asistencia', label: 'Asistencia' },
              { value: 'citacion', label: 'Citación' },
              { value: 'felicitacion', label: 'Felicitación' },
              { value: 'emergencia', label: 'Emergencia' },
              { value: 'general', label: 'General' },
            ]}
          />
          <Input
            label="Asunto"
            value={nuevaPlantilla.asunto}
            onChange={e => setNuevaPlantilla({ ...nuevaPlantilla, asunto: e.target.value })}
          />
          <Textarea
            label="Contenido"
            value={nuevaPlantilla.contenido}
            onChange={e => setNuevaPlantilla({ ...nuevaPlantilla, contenido: e.target.value })}
            placeholder="Usa {estudiante}, {curso}, {padre}, {madre} como variables"
            rows={6}
          />
        </div>
      </Modal>
    </div>
  );
};

export default WhatsAppPage;
