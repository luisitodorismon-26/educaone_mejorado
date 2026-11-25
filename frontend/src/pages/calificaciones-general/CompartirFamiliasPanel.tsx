import { useEffect, useRef, useState } from 'react';
import { X, Users, Mail, MessageCircle, User, ArrowRight, Info, AlertTriangle, RefreshCw, Ban, Loader2, ExternalLink } from 'lucide-react';
import api from '../../services/api';
import { mensajeDeError } from '../../utils/errorServidor';
import {
  FamiliaEstado, RolContacto, contactoElegido, etiquetaContacto, mensajeFamilia, enlaceWhatsApp,
  estadoFamilia, siguienteFamilia, primerNombre, textoVisitas, ETIQUETA_ROL,
} from '../../utils/compartirFamilias';

interface Props {
  cursoId: number;
  periodo: number;
  estudianteIds: number[];
  onCerrar: () => void;
}

// Lotes cortos: cada petición dura pocos segundos y se ve el avance.
const LOTE = 10;

const IconoWhatsApp = ({ size = 20 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d="M12.04 2C6.58 2 2.13 6.45 2.13 11.91c0 1.75.46 3.45 1.32 4.95L2.05 22l5.25-1.38a9.9 9.9 0 0 0 4.74 1.21h.01c5.46 0 9.91-4.45 9.91-9.91C21.96 6.45 17.5 2 12.04 2Zm0 18.15h-.01a8.2 8.2 0 0 1-4.19-1.15l-.3-.18-3.12.82.83-3.04-.2-.31a8.2 8.2 0 0 1-1.26-4.38c0-4.54 3.7-8.23 8.25-8.23 2.2 0 4.27.86 5.83 2.42a8.18 8.18 0 0 1 2.41 5.82c0 4.54-3.7 8.23-8.24 8.23Zm4.52-6.16c-.25-.12-1.47-.72-1.69-.81-.23-.08-.39-.12-.56.13-.16.25-.64.81-.79.97-.14.17-.29.19-.54.06-.25-.12-1.05-.39-1.99-1.23-.74-.66-1.23-1.47-1.38-1.72-.14-.25-.02-.38.11-.51.11-.11.25-.29.37-.43.13-.15.17-.25.25-.42.08-.17.04-.31-.02-.43-.06-.13-.56-1.35-.77-1.85-.2-.48-.41-.42-.56-.43h-.48c-.17 0-.43.06-.66.31-.23.25-.87.85-.87 2.07 0 1.22.89 2.4 1.01 2.56.12.17 1.75 2.67 4.24 3.74.59.26 1.05.41 1.41.52.59.19 1.13.16 1.56.1.48-.07 1.47-.6 1.67-1.18.21-.58.21-1.07.14-1.18-.06-.1-.22-.16-.47-.29Z" />
  </svg>
);

export const CompartirFamiliasPanel = ({ cursoId, periodo, estudianteIds, onCerrar }: Props) => {
  const [familias, setFamilias] = useState<FamiliaEstado[]>([]);
  const [meta, setMeta] = useState<{ colegio: string; ano: string } | null>(null);
  const [preparando, setPreparando] = useState(true);
  const [progreso, setProgreso] = useState({ hechos: 0, total: estudianteIds.length });
  const [error, setError] = useState('');
  const [ocupado, setOcupado] = useState(false);
  const [actual, setActual] = useState(0);
  const [eleccion, setEleccion] = useState<Record<number, RolContacto>>({});
  const [cambiando, setCambiando] = useState<number | null>(null);
  const [accion, setAccion] = useState<string | null>(null);
  const enCurso = useRef(false);
  const listaRef = useRef<HTMLUListElement>(null);

  const reemplazar = (nuevas: FamiliaEstado[]) =>
    setFamilias(prev => prev.map(f => nuevas.find(n => n.estudiante_id === f.estudiante_id) || f));

  const preparar = async (ids: number[], inicial: boolean) => {
    if (enCurso.current) return;
    enCurso.current = true;
    setError(''); setOcupado(false);
    if (inicial) { setPreparando(true); setProgreso({ hechos: 0, total: ids.length }); }
    try {
      const todas: FamiliaEstado[] = [];
      for (let i = 0; i < ids.length; i += LOTE) {
        const lote = ids.slice(i, i + LOTE);
        const res = await api.post('/documentos-familia/preparar',
          { curso_id: cursoId, periodo, estudiante_ids: lote });
        setMeta({ colegio: res.data.colegio, ano: res.data.ano });
        todas.push(...(res.data.estudiantes || []));
        if (inicial) setProgreso({ hechos: Math.min(i + LOTE, ids.length), total: ids.length });
      }
      if (inicial) {
        setFamilias(todas);
        const primera = todas.findIndex(f => f.documento?.url && f.contactos.some(c => c.valido));
        setActual(primera >= 0 ? primera : 0);
      } else {
        reemplazar(todas);
      }
    } catch (e: any) {
      if (e?.response?.status === 503) setOcupado(true);
      setError(await mensajeDeError(e, { porDefecto: 'No se pudieron preparar los reportes.' }));
    } finally {
      enCurso.current = false;
      setPreparando(false);
    }
  };

  useEffect(() => { preparar(estudianteIds, true); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);

  // La familia actual siempre visible dentro de la lista (que tiene altura limitada).
  useEffect(() => {
    const li = listaRef.current?.querySelector<HTMLElement>(`[data-familia-indice="${actual}"]`);
    li?.scrollIntoView({ block: 'nearest' });
  }, [actual, familias.length]);

  const familia = familias[actual];
  const contacto = familia ? contactoElegido(familia, eleccion[familia.estudiante_id]) : null;
  const url = familia?.documento?.estado === 'activo' ? familia.documento.url : null;
  const mensaje = familia && url && meta
    ? mensajeFamilia({ colegio: meta.colegio, periodo, ano: meta.ano, estudiante: familia.nombre, url })
    : '';
  const hrefWhatsApp = contacto?.telefono_whatsapp && mensaje ? enlaceWhatsApp(contacto.telefono_whatsapp, mensaje) : null;

  const anotarWhatsApp = () => {
    if (!familia?.documento || !contacto) return;
    const docId = familia.documento.id;
    // Abrir WhatsApp NO es enviar: solo se anota que se abrió el chat.
    api.post(`/documentos-familia/${docId}/whatsapp`, { contacto_rol: contacto.rol })
      .then(res => setFamilias(prev => prev.map(f => f.documento?.id === docId
        ? { ...f, documento: { ...f.documento!, whatsapp_abierto: res.data.whatsapp_abierto,
            ultimo_whatsapp: { fecha: new Date().toISOString(), contacto_rol: contacto.rol, telefono_final: contacto.telefono_final } } }
        : f)))
      .catch(() => { /* la anotación es informativa: no bloquea abrir WhatsApp */ });
  };

  const nuevaVersion = async () => {
    if (!familia?.documento || enCurso.current) return;
    setAccion('version');
    try {
      enCurso.current = true;
      await api.post(`/documentos-familia/${familia.documento.id}/version`);
      enCurso.current = false;
      await preparar([familia.estudiante_id], false);
    } catch (e: any) {
      if (e?.response?.status === 503) setOcupado(true);
      setError(await mensajeDeError(e, { porDefecto: 'No se pudo preparar la versión nueva.', operacion: 'guardado' }));
    } finally { enCurso.current = false; setAccion(null); }
  };

  const anular = async () => {
    if (!familia?.documento || enCurso.current) return;
    if (!window.confirm(`¿Anular el enlace del reporte de ${familia.nombre}?\n\nQuien lo tenga dejará de poder abrirlo. Después puedes preparar uno nuevo.`)) return;
    setAccion('anular');
    try {
      enCurso.current = true;
      await api.post(`/documentos-familia/${familia.documento.id}/anular`, { motivo: 'Anulado desde Notas por período' });
      setFamilias(prev => prev.map(f => f.estudiante_id === familia.estudiante_id ? { ...f, documento: null, desactualizado: null } : f));
    } catch (e: any) {
      setError(await mensajeDeError(e, { porDefecto: 'No se pudo anular el enlace.', operacion: 'guardado' }));
    } finally { enCurso.current = false; setAccion(null); }
  };

  const irSiguiente = () => {
    const i = siguienteFamilia(familias, actual);
    if (i >= 0) { setActual(i); setCambiando(null); }
  };

  const conEnlace = familias.filter(f => f.documento?.url && f.contactos.some(c => c.valido)).length;
  const abiertos = familias.filter(f => (f.documento?.whatsapp_abierto || 0) > 0).length;

  return (
    <>
      <div className="fixed inset-0 bg-black/30 z-40 xl:hidden" onClick={onCerrar} aria-hidden="true" />
      <aside role="dialog" aria-label="Compartir reportes" data-panel-compartir
        className="fixed inset-y-0 right-0 z-50 w-full sm:w-[440px] bg-white shadow-2xl border-l border-gray-200 flex flex-col">
        <div className="flex items-center justify-between px-4 sm:px-5 py-4 border-b">
          <h2 className="text-xl font-bold text-gray-900">Compartir reportes</h2>
          <button onClick={onCerrar} className="p-2 -mr-2 rounded-lg hover:bg-gray-100" aria-label="Cerrar"><X size={22} /></button>
        </div>

        <div className="flex-1 overflow-y-auto px-4 sm:px-5 py-4 space-y-4">
          <div className="flex items-center gap-2 bg-blue-50 text-blue-900 rounded-lg px-3 py-2.5 font-semibold">
            <Users size={18} /> {estudianteIds.length} {estudianteIds.length === 1 ? 'estudiante seleccionado' : 'estudiantes seleccionados'}
          </div>

          <div className="grid grid-cols-2 gap-2">
            <button className="flex items-center justify-center gap-2 rounded-lg border-2 border-green-600 bg-green-50 text-green-800 font-semibold py-2.5" aria-pressed="true">
              <IconoWhatsApp /> WhatsApp
            </button>
            <button disabled className="flex items-center justify-center gap-2 rounded-lg border border-gray-200 bg-gray-50 text-gray-400 py-2.5 text-sm cursor-not-allowed" title="El envío por correo llegará en una entrega posterior">
              <Mail size={18} /> Correo · Próximamente
            </button>
          </div>

          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 text-red-800 text-sm px-3 py-2.5" role="alert">
              <p className="whitespace-pre-line">{error}</p>
              {ocupado && (
                <button onClick={() => preparar(familias.length ? familias.filter(f => !f.documento).map(f => f.estudiante_id) : estudianteIds, !familias.length)}
                  className="mt-2 inline-flex items-center gap-1 font-semibold underline"><RefreshCw size={14} /> Reintentar</button>
              )}
            </div>
          )}

          {preparando ? (
            <div className="flex items-center gap-3 text-gray-700 py-6 justify-center">
              <Loader2 className="animate-spin" size={20} />
              Preparando reportes… {progreso.hechos} de {progreso.total}
            </div>
          ) : (
            <>
              <ul ref={listaRef} className="space-y-2 max-h-[34vh] overflow-y-auto pr-1 -mr-1" aria-label="Familias">
                {familias.map((f, i) => {
                  const c = contactoElegido(f, eleccion[f.estudiante_id]);
                  const est = estadoFamilia(f);
                  const activa = i === actual;
                  return (
                    <li key={f.estudiante_id} data-familia-indice={i}
                      className={`rounded-lg border px-3 py-2.5 ${activa ? 'border-green-600 ring-1 ring-green-600 bg-green-50/40' : 'border-gray-200'}`}>
                      <div className="flex items-start gap-3">
                        <User size={20} className="mt-0.5 text-gray-500 shrink-0" />
                        <button className="flex-1 min-w-0 text-left" onClick={() => { setActual(i); setCambiando(null); }}>
                          <p className="font-semibold text-gray-900 break-words">{f.nombre}</p>
                          <p className="text-sm text-gray-700 break-words">
                            {c ? <>{c.nombre || ETIQUETA_ROL[c.rol]} · <span className="text-gray-500">{etiquetaContacto(c)}</span></>
                              : <span className="text-amber-700">Sin teléfono utilizable</span>}
                          </p>
                          <p className={`text-xs mt-0.5 ${est.tipo === 'desactualizado' || est.tipo === 'sin_contacto' ? 'text-amber-700' : est.tipo === 'whatsapp_abierto' ? 'text-green-700' : 'text-gray-500'}`}>
                            {est.texto}{f.documento && f.documento.version > 1 ? ` · versión ${f.documento.version}` : ''}
                          </p>
                        </button>
                        {f.contactos.length > 0 && (
                          <button onClick={() => { setActual(i); setCambiando(cambiando === f.estudiante_id ? null : f.estudiante_id); }}
                            className="text-sm font-semibold text-blue-700 hover:underline shrink-0">Cambiar contacto</button>
                        )}
                      </div>
                      {cambiando === f.estudiante_id && (
                        <fieldset className="mt-2 ml-8 space-y-1.5">
                          <legend className="sr-only">Contacto de {f.nombre}</legend>
                          {f.contactos.map(ct => (
                            <label key={ct.rol} className={`flex items-start gap-2 text-sm ${ct.valido ? 'cursor-pointer' : 'opacity-60 cursor-not-allowed'}`}>
                              <input type="radio" name={`contacto-${f.estudiante_id}`} disabled={!ct.valido}
                                checked={c?.rol === ct.rol}
                                onChange={() => { setEleccion(prev => ({ ...prev, [f.estudiante_id]: ct.rol })); setCambiando(null); }}
                                className="mt-1" />
                              <span className="break-words"><strong>{ct.nombre || ETIQUETA_ROL[ct.rol]}</strong> · {etiquetaContacto(ct)}</span>
                            </label>
                          ))}
                          <p className="text-xs text-gray-500">Para corregir un teléfono, edita la ficha del estudiante.</p>
                        </fieldset>
                      )}
                    </li>
                  );
                })}
              </ul>

              {familia && (
                <div className="space-y-3">
                  {familia.notas_pendientes > 0 && (
                    <p className="flex gap-2 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                      <AlertTriangle size={16} className="shrink-0 mt-0.5" />
                      {familia.nombre} tiene {familia.notas_pendientes} {familia.notas_pendientes === 1 ? 'materia' : 'materias'} sin nota en este período: el reporte las muestra como «Sin nota».
                    </p>
                  )}
                  {familia.desactualizado && familia.documento && (
                    <div className="text-sm text-amber-900 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                      <p>Las calificaciones cambiaron después de preparar este reporte. El enlace sigue mostrando lo que se preparó el {familia.documento.fecha_preparado ? new Date(familia.documento.fecha_preparado).toLocaleDateString('es-DO') : '—'}.</p>
                      <button onClick={nuevaVersion} disabled={accion !== null}
                        className="mt-2 inline-flex items-center gap-1 font-semibold text-amber-900 underline disabled:opacity-50">
                        <RefreshCw size={14} className={accion === 'version' ? 'animate-spin' : ''} /> Preparar nueva versión
                      </button>
                    </div>
                  )}
                  {!familia.documento && familia.contactos.some(c => c.valido) && (
                    <button onClick={() => preparar([familia.estudiante_id], false)}
                      className="w-full rounded-lg border border-blue-600 text-blue-700 font-semibold py-2.5">Preparar reporte de {primerNombre(familia.nombre)}</button>
                  )}

                  <div>
                    <p className="font-semibold text-gray-900 mb-1.5">Mensaje preparado automáticamente</p>
                    <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-3 text-sm text-gray-800 whitespace-pre-line break-words" data-mensaje-preparado>
                      {mensaje
                        // Vista previa legible: sin los asteriscos de negrita de WhatsApp y sin el enlace largo.
                        ? mensaje.replace(url || '', '[Enlace individual incluido automáticamente]').replace(/^\*(.+)\*$/m, '$1')
                        : 'Se preparará cuando el reporte y el contacto estén listos.'}
                    </div>
                  </div>
                  <p className="flex gap-2 text-sm text-gray-600"><Info size={16} className="shrink-0 mt-0.5" />Cada familia recibe únicamente el reporte de su estudiante.</p>

                  {hrefWhatsApp ? (
                    <a href={hrefWhatsApp} target="_blank" rel="noopener noreferrer" onClick={anotarWhatsApp} data-abrir-whatsapp
                      className="flex items-center justify-center gap-2 w-full rounded-lg bg-green-700 hover:bg-green-800 text-white font-bold text-lg py-3.5 px-3 text-center">
                      <IconoWhatsApp size={24} /> <span className="break-words">Abrir WhatsApp de {primerNombre(contacto?.nombre) || ETIQUETA_ROL[contacto!.rol]}</span>
                    </a>
                  ) : (
                    <div className="w-full rounded-lg bg-gray-100 text-gray-500 font-semibold py-3.5 text-center">
                      {!contacto ? 'Esta familia no tiene un teléfono utilizable' : 'Reporte sin preparar'}
                    </div>
                  )}
                  <button onClick={irSiguiente} disabled={siguienteFamilia(familias, actual) < 0 || familias.length < 2}
                    className="flex items-center justify-center gap-2 w-full text-blue-700 font-semibold text-lg py-2 disabled:text-gray-400">
                    Siguiente familia <ArrowRight size={20} />
                  </button>
                  <p className="text-center text-xs text-gray-500">Familia {actual + 1} de {familias.length} · {abiertos} de {conEnlace} con WhatsApp abierto</p>

                  {familia.documento && (
                    <div className="text-xs text-gray-500 border-t pt-3 space-y-1">
                      <p>{textoVisitas(familia.documento)}</p>
                      <div className="flex flex-wrap gap-x-4 gap-y-1">
                        {url && <a href={url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-blue-700 hover:underline"><ExternalLink size={12} /> Ver lo que recibe la familia</a>}
                        <button onClick={anular} disabled={accion !== null} className="inline-flex items-center gap-1 text-red-700 hover:underline disabled:opacity-50"><Ban size={12} /> Anular enlace</button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>

        <div className="border-t bg-blue-50/60 px-4 sm:px-5 py-3 text-sm text-gray-700">
          <p className="flex gap-2 font-semibold"><MessageCircle size={16} className="shrink-0 mt-0.5" />Solo pulsa Enviar en WhatsApp. No necesitas copiar ni pegar el enlace.</p>
          <p className="text-xs text-gray-600 mt-1 ml-6">Abrir WhatsApp no confirma que el mensaje se envió. Enlaces sin vencimiento automático · PDF descargable · Quien reciba el enlace reenviado también podrá abrirlo.</p>
        </div>
      </aside>
    </>
  );
};

export default CompartirFamiliasPanel;
