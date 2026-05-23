import { useState, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';
import {
  Building2, Plus, Edit3, RefreshCw, Users, GraduationCap,
  BookOpen, Search, X, Check, AlertTriangle, BarChart3, Power,
  Globe, Mail, Phone, Calendar, Shield, ChevronDown, ChevronUp,
  Copy, Eye, EyeOff, Key, UserPlus, Activity,
  LogIn, LogOut as LogOutIcon, Bell, Download, Settings,
  ArrowRightLeft, Lock, Zap
} from 'lucide-react';

// ===== TYPES =====
interface Colegio { id:number;nombre:string;codigo:string;dominio:string|null;activo:boolean;plan:string;max_estudiantes:number;max_usuarios:number;fecha_creacion:string;fecha_expiracion:string|null;contacto_nombre:string|null;contacto_email:string|null;contacto_telefono:string|null;total_estudiantes?:number;total_usuarios?:number;total_cursos?:number; }
interface Stats { total_colegios:number;total_colegios_inactivos:number;total_estudiantes:number;total_usuarios:number;total_profesores:number; }
interface UsuarioColegio { id:number;username:string;nombre:string;apellido:string;nombre_completo:string;role:string;email:string;activo:boolean;colegio_id:number; }
interface LogEntry { id:number;usuario:string;accion:string;entidad:string;detalles:string;ip:string;fecha:string;colegio:string; }
interface AccesoEntry { id:number;usuario:string;tipo:string;ip:string;fecha:string;colegio:string; }
interface StatsDetalle { id:number;nombre:string;codigo:string;plan:string;estudiantes:number;profesores:number;usuarios:number;cursos:number;max_estudiantes:number;max_usuarios:number; }
interface Alerta { tipo:string;prioridad:string;colegio:string;colegio_id:number|null;mensaje:string; }
interface NuevoColegio {
  nombre:string;codigo:string;dominio:string;plan:string;
  max_estudiantes:number;max_usuarios:number;
  contacto_nombre:string;contacto_email:string;contacto_telefono:string;
  admin_username:string;admin_password:string;notas:string;
  plan_secundaria:boolean;plan_primaria:boolean;plan_inicial:boolean;
  plan_whatsapp:boolean;plan_psicologia:boolean;
  plan_eval_profesores:boolean;plan_eval_interna:boolean;
  plan_comunicacion_padres:boolean;plan_registro_escolar:boolean;plan_reportes_conducta:boolean;
}
const initNuevo:NuevoColegio={
  nombre:'',codigo:'',dominio:'',plan:'basico',
  max_estudiantes:500,max_usuarios:50,
  contacto_nombre:'',contacto_email:'',contacto_telefono:'',
  admin_username:'',admin_password:'',notas:'',
  plan_secundaria:true,plan_primaria:false,plan_inicial:false,
  plan_whatsapp:false,plan_psicologia:false,
  plan_eval_profesores:true,plan_eval_interna:false,
  plan_comunicacion_padres:true,plan_registro_escolar:true,plan_reportes_conducta:true,
};
const planC:Record<string,string>={basico:'bg-slate-100 text-slate-700',premium:'bg-blue-100 text-blue-700',enterprise:'bg-purple-100 text-purple-700'};
const roleC:Record<string,string>={direccion:'bg-blue-100 text-blue-700',coordinador:'bg-emerald-100 text-emerald-700',profesor:'bg-amber-100 text-amber-700',psicologia:'bg-pink-100 text-pink-700',secretaria:'bg-slate-200 text-slate-700'};

// ===== SHARED =====
const Loading=()=>(<div className="flex justify-center py-16"><div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600"/></div>);
const Empty=({icon:I,text}:{icon:any;text:string})=>(<div className="text-center py-16 bg-white rounded-xl border border-slate-200"><I size={48} className="mx-auto text-slate-300 mb-3"/><p className="text-slate-500">{text}</p></div>);
const Alerts=({error,success,onCE,onCS}:{error:string;success:string;onCE:()=>void;onCS:()=>void})=>(<>{error&&<div className="flex items-center gap-3 p-4 bg-red-50 border border-red-200 rounded-xl text-red-700"><AlertTriangle size={18}/><span className="flex-1 text-sm">{error}</span><button onClick={onCE}><X size={16}/></button></div>}{success&&<div className="flex items-center gap-3 p-4 bg-green-50 border border-green-200 rounded-xl text-green-700"><Check size={18}/><span className="flex-1 text-sm">{success}</span><button onClick={onCS}><X size={16}/></button></div>}</>);
const Modal=({children,onClose,title,small}:{children:React.ReactNode;onClose:()=>void;title:string;small?:boolean})=>(<div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4 backdrop-blur-sm" onClick={onClose}><div className={`bg-white rounded-2xl shadow-xl w-full ${small?'max-w-md':'max-w-2xl'} max-h-[90vh] overflow-y-auto`} onClick={e=>e.stopPropagation()}><div className="p-5 border-b border-slate-200 flex items-center justify-between sticky top-0 bg-white z-10 rounded-t-2xl"><h2 className="text-lg font-bold text-slate-800">{title}</h2><button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-lg"><X size={18}/></button></div><div className="p-5">{children}</div></div></div>);
const FF=({label,value,onChange,placeholder,type='text',disabled,mono}:{label?:string;value:string;onChange:(v:string)=>void;placeholder?:string;type?:string;disabled?:boolean;mono?:boolean})=>(<div>{label&&<label className="block text-sm font-medium text-slate-700 mb-1">{label}</label>}<input type={type} value={value} onChange={e=>onChange(e.target.value)} placeholder={placeholder} disabled={disabled} className={`w-full px-3 py-2.5 border border-slate-200 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none disabled:bg-slate-100 ${mono?'font-mono text-sm':''}`}/></div>);
const CopyRow=({label,value}:{label:string;value:string})=>(<div className="flex items-center justify-between"><span><strong>{label}:</strong> {value}</span><button onClick={()=>navigator.clipboard.writeText(value)} className="p-1 hover:bg-slate-100 rounded" title="Copiar"><Copy size={14}/></button></div>);
const PBar=({label,current,max}:{label:string;current:number;max:number})=>{const p=max?Math.min(Math.round(current/max*100),100):0;return(<div className="mb-2"><div className="flex justify-between text-xs text-slate-600 mb-1"><span>{label}</span><span>{current}/{max}</span></div><div className="h-2 bg-slate-200 rounded-full overflow-hidden"><div className={`h-full rounded-full ${p>90?'bg-red-500':p>70?'bg-amber-500':'bg-blue-500'}`} style={{width:`${p}%`}}/></div></div>);};
const MBar=({pct}:{pct:number})=>(<div className="flex items-center gap-2"><div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden"><div className={`h-full rounded-full ${pct>90?'bg-red-500':pct>70?'bg-amber-500':'bg-blue-500'}`} style={{width:`${pct}%`}}/></div><span className={`text-xs font-medium min-w-[32px] text-right ${pct>90?'text-red-600':'text-slate-500'}`}>{pct}%</span></div>);

// ===== MAIN =====
export const SuperAdminPage=()=>{
  const {user}=useAuth();
  const [tab,setTab]=useState<'colegios'|'usuarios'|'logs'|'alertas'|'stats'|'config'>('colegios');
  if(user?.role!=='superadmin')return(<div className="flex items-center justify-center min-h-[60vh]"><div className="text-center"><Shield size={64} className="mx-auto text-red-300 mb-4"/><h2 className="text-2xl font-bold text-slate-800">Acceso Restringido</h2></div></div>);
  return(
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div><h1 className="text-2xl font-bold text-slate-800 flex items-center gap-3"><Building2 className="text-blue-600" size={28}/>Panel Super Administrador</h1><p className="text-slate-500 mt-1">Control total de EducaOne</p></div>
      </div>
      <div className="flex bg-white rounded-xl border border-slate-200 p-1 shadow-sm overflow-x-auto gap-1">
        {([['colegios','Colegios',Building2],['usuarios','Usuarios',Users],['alertas','Alertas',Bell],['logs','Actividad',Activity],['stats','Estadísticas',BarChart3],['config','Mi Cuenta',Lock]] as const).map(([k,l,I])=>(
          <button key={k} onClick={()=>setTab(k)} className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-all whitespace-nowrap ${tab===k?'bg-blue-600 text-white shadow-md':'text-slate-600 hover:bg-slate-50'}`}><I size={18}/>{l}</button>
        ))}
      </div>
      {tab==='colegios'&&<ColegiosTab/>}
      {tab==='usuarios'&&<UsuariosTab/>}
      {tab==='alertas'&&<AlertasTab/>}
      {tab==='logs'&&<LogsTab/>}
      {tab==='stats'&&<StatsTab/>}
      {tab==='config'&&<ConfigTab/>}
    </div>
  );
};

// ===== COLEGIOS =====
const ColegiosTab=()=>{
  const [colegios,setColegios]=useState<Colegio[]>([]);const [stats,setStats]=useState<Stats|null>(null);const [loading,setLoading]=useState(true);const [search,setSearch]=useState('');const [showModal,setShowModal]=useState(false);const [edit,setEdit]=useState<Colegio|null>(null);const [nuevo,setNuevo]=useState<NuevoColegio>(initNuevo);const [error,setError]=useState('');const [success,setSuccess]=useState('');const [showPw,setShowPw]=useState(false);const [creds,setCreds]=useState<{username:string;password:string}|null>(null);const [expId,setExpId]=useState<number|null>(null);const [confDel,setConfDel]=useState<number|null>(null);const [sub,setSub]=useState<'activos'|'inactivos'>('activos');
  const [modulosColegio,setModulosColegio]=useState<{id:number,plan:Record<string,boolean>}|null>(null);
  useEffect(()=>{load();},[]);useEffect(()=>{if(success){const t=setTimeout(()=>setSuccess(''),4000);return()=>clearTimeout(t);}},[success]);
  const load=async()=>{setLoading(true);try{const[c,s]=await Promise.all([api.get('/superadmin/colegios'),api.get('/superadmin/stats')]);setColegios(c.data);setStats(s.data);}catch(e:any){setError(e.response?.data?.error||e.message);}finally{setLoading(false);}};
  const crear=async()=>{
    setError('');
    if(!nuevo.nombre.trim()||!nuevo.codigo.trim()){setError('Nombre y código requeridos');return;}
    if(!/^[a-z0-9_-]+$/.test(nuevo.codigo)){setError('Código: solo minúsculas, números, guiones');return;}
    // Validar al menos un nivel marcado
    if(!nuevo.plan_secundaria && !nuevo.plan_primaria && !nuevo.plan_inicial){
      setError('Debe activar al menos un nivel educativo (Secundaria, Primaria o Inicial)');return;
    }
    try{
      const r=await api.post('/superadmin/colegios',{
        ...nuevo,
        admin_username:nuevo.admin_username||`direccion_${nuevo.codigo}`,
        admin_password:nuevo.admin_password||'Cambiar123',
      });
      setCreds({username:r.data.admin_username,password:r.data.admin_password});
      // Si el backend ajustó el username para evitar colisión, avisar al superadmin
      if(r.data.username_ajustado && r.data.username_solicitado){
        setSuccess(`Colegio "${nuevo.nombre}" creado. NOTA: el username "${r.data.username_solicitado}" ya estaba en uso, se asignó "${r.data.admin_username}" en su lugar.`);
      } else {
        setSuccess(`Colegio "${nuevo.nombre}" creado`);
      }
      setNuevo(initNuevo);
      load();
    }catch(e:any){setError(e.response?.data?.error||'Error');}
  };
  const editar=async()=>{if(!edit)return;try{await api.put(`/superadmin/colegios/${edit.id}`,edit);setSuccess('Colegio actualizado');setEdit(null);setShowModal(false);load();}catch(e:any){setError(e.response?.data?.error||'Error');}};
  const desactivar=async(id:number)=>{try{await api.delete(`/superadmin/colegios/${id}`);setSuccess('Colegio desactivado');setConfDel(null);load();}catch(e:any){setError(e.response?.data?.error||'Error');}};
  const reactivar=async(id:number)=>{try{await api.post(`/superadmin/colegios/${id}/reactivar`);setSuccess('Colegio reactivado');load();}catch(e:any){setError(e.response?.data?.error||'Error');}};
  const aplicarPlan=async(id:number)=>{try{await api.post(`/superadmin/colegios/${id}/aplicar-plan`);setSuccess('Plan aplicado');load();}catch(e:any){setError(e.response?.data?.error||'Error');}};
  const abrirModulos=async(id:number)=>{
    try{
      const r=await api.get(`/superadmin/colegios/${id}/modulos`);
      // Backend devuelve { modulos: { whatsapp: {plan,usa,activo}, ... } }
      // Extraemos solo el plan (lo que el superadmin controla)
      const plan:Record<string,boolean>={};
      const data=r.data?.modulos||{};
      Object.keys(data).forEach(k=>{plan[k]=Boolean(data[k]?.plan);});
      setModulosColegio({id,plan});
    }catch(e:any){setError(e.response?.data?.error||'Error cargando modulos');}
  };
  const toggleModulo=(key:string)=>{
    if(!modulosColegio)return;
    setModulosColegio({...modulosColegio,plan:{...modulosColegio.plan,[key]:!modulosColegio.plan[key]}});
  };
  const guardarModulos=async()=>{
    if(!modulosColegio)return;
    // Validar al menos un nivel
    const algunNivel=modulosColegio.plan.secundaria||modulosColegio.plan.primaria||modulosColegio.plan.inicial;
    if(!algunNivel){setError('Debe activar al menos un nivel (Secundaria, Primaria o Inicial)');return;}
    try{
      // Backend acepta { modulos: { whatsapp: true, ... } } y lo aplica como plan_X
      await api.put(`/superadmin/colegios/${modulosColegio.id}/modulos`,{modulos:modulosColegio.plan});
      setSuccess('Módulos del plan actualizados');
      setModulosColegio(null);
    }catch(e:any){setError(e.response?.data?.error||'Error');}
  };
  const impersonar=async(id:number)=>{try{const r=await api.post(`/superadmin/impersonar/${id}`);localStorage.setItem('superadmin_token',localStorage.getItem('token')||'');localStorage.setItem('superadmin_user',localStorage.getItem('user')||'');localStorage.setItem('token',r.data.token);localStorage.setItem('user',JSON.stringify(r.data.user));window.location.href='/dashboard';}catch(e:any){setError(e.response?.data?.error||'Error');}};
  const exportCSV=async()=>{try{const r=await api.get('/superadmin/export/colegios',{responseType:'blob'});const url=URL.createObjectURL(new Blob([r.data]));const a=document.createElement('a');a.href=url;a.download='colegios_educaone.csv';a.click();}catch(e:any){setError('Error exportando');}};
  const filtered=colegios.filter(c=>{const m=c.nombre.toLowerCase().includes(search.toLowerCase())||c.codigo.toLowerCase().includes(search.toLowerCase());return m&&(sub==='activos'?c.activo:!c.activo);});

  return(
    <div className="space-y-4">
      <Alerts error={error} success={success} onCE={()=>setError('')} onCS={()=>setSuccess('')}/>
      {stats&&(<div className="grid grid-cols-2 md:grid-cols-5 gap-3">{[{l:'Activos',v:stats.total_colegios,I:Building2,c:'text-blue-600 bg-blue-50'},{l:'Inactivos',v:stats.total_colegios_inactivos,I:Power,c:'text-slate-500 bg-slate-50'},{l:'Estudiantes',v:stats.total_estudiantes,I:GraduationCap,c:'text-emerald-600 bg-emerald-50'},{l:'Usuarios',v:stats.total_usuarios,I:Users,c:'text-amber-600 bg-amber-50'},{l:'Profesores',v:stats.total_profesores,I:BookOpen,c:'text-purple-600 bg-purple-50'}].map((s,i)=>(<div key={i} className="bg-white rounded-xl border border-slate-200 p-4"><div className={`w-9 h-9 rounded-lg flex items-center justify-center mb-2 ${s.c}`}><s.I size={18}/></div><p className="text-xl font-bold text-slate-800">{s.v.toLocaleString()}</p><p className="text-xs text-slate-500">{s.l}</p></div>))}</div>)}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1"><Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"/><input type="text" placeholder="Buscar colegio..." value={search} onChange={e=>setSearch(e.target.value)} className="w-full pl-10 pr-4 py-2.5 border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-500 outline-none"/></div>
        <div className="flex bg-slate-100 rounded-xl p-1"><button onClick={()=>setSub('activos')} className={`px-4 py-2 rounded-lg text-sm font-medium ${sub==='activos'?'bg-white text-blue-600 shadow-sm':'text-slate-600'}`}>Activos ({colegios.filter(c=>c.activo).length})</button><button onClick={()=>setSub('inactivos')} className={`px-4 py-2 rounded-lg text-sm font-medium ${sub==='inactivos'?'bg-white text-red-600 shadow-sm':'text-slate-600'}`}>Inactivos ({colegios.filter(c=>!c.activo).length})</button></div>
        <button onClick={exportCSV} className="flex items-center gap-2 px-4 py-2.5 border border-slate-300 rounded-xl hover:bg-slate-50 text-sm font-medium whitespace-nowrap"><Download size={16}/>Exportar</button>
        <button onClick={()=>{setShowModal(true);setEdit(null);setNuevo(initNuevo);setCreds(null);setError('');}} className="flex items-center gap-2 px-5 py-2.5 bg-blue-600 text-white rounded-xl hover:bg-blue-700 font-medium shadow-lg shadow-blue-600/20 whitespace-nowrap"><Plus size={18}/>Nuevo Colegio</button>
      </div>
      {loading?<Loading/>:filtered.length===0?<Empty icon={Building2} text="No hay colegios"/>:(
        <div className="space-y-3">{filtered.map(c=>(
          <div key={c.id} className={`bg-white rounded-xl border shadow-sm overflow-hidden ${c.activo?'border-slate-200':'border-red-200 bg-red-50/30'}`}>
            <div className="flex items-center gap-4 p-4 cursor-pointer" onClick={()=>setExpId(expId===c.id?null:c.id)}>
              <div className={`w-12 h-12 rounded-xl flex items-center justify-center font-bold text-lg shrink-0 ${c.activo?'bg-blue-100 text-blue-700':'bg-red-100 text-red-600'}`}>{c.nombre.charAt(0)}</div>
              <div className="flex-1 min-w-0"><div className="flex items-center gap-2 flex-wrap"><h3 className="font-semibold text-slate-800 truncate">{c.nombre}</h3><span className={`text-xs px-2 py-0.5 rounded-full font-medium ${planC[c.plan]||planC.basico}`}>{c.plan}</span>{!c.activo&&<span className="text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-600 font-medium">Inactivo</span>}</div><p className="text-sm text-slate-500"><span className="font-mono text-xs bg-slate-100 px-1.5 py-0.5 rounded">{c.codigo}</span></p></div>
              <div className="hidden md:flex items-center gap-6 text-sm"><div className="text-center"><p className="font-bold text-slate-800">{c.total_estudiantes??0}</p><p className="text-xs text-slate-400">Est.</p></div><div className="text-center"><p className="font-bold text-slate-800">{c.total_usuarios??0}</p><p className="text-xs text-slate-400">Usr.</p></div></div>
              <div className="flex items-center gap-1">
                {c.activo&&<button onClick={e=>{e.stopPropagation();impersonar(c.id);}} className="p-2 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg" title="Entrar como director"><ArrowRightLeft size={16}/></button>}
                <button onClick={e=>{e.stopPropagation();setEdit({...c});setShowModal(true);setError('');}} className="p-2 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg" title="Editar"><Edit3 size={16}/></button>
                {c.activo?<button onClick={e=>{e.stopPropagation();setConfDel(c.id);}} className="p-2 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg" title="Desactivar"><Power size={16}/></button>:<button onClick={e=>{e.stopPropagation();reactivar(c.id);}} className="p-2 text-slate-400 hover:text-green-600 hover:bg-green-50 rounded-lg" title="Reactivar"><RefreshCw size={16}/></button>}
                {expId===c.id?<ChevronUp size={16} className="text-slate-400"/>:<ChevronDown size={16} className="text-slate-400"/>}
              </div>
            </div>
            {expId===c.id&&(<div className="border-t border-slate-100 p-4 bg-slate-50/50">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
                <div><p className="text-slate-400 text-xs uppercase font-semibold mb-2">Contacto</p>{c.contacto_nombre&&<p className="flex items-center gap-2 text-slate-600"><Users size={14}/>{c.contacto_nombre}</p>}{c.contacto_email&&<p className="flex items-center gap-2 text-slate-600 mt-1"><Mail size={14}/>{c.contacto_email}</p>}{c.contacto_telefono&&<p className="flex items-center gap-2 text-slate-600 mt-1"><Phone size={14}/>{c.contacto_telefono}</p>}{!c.contacto_nombre&&!c.contacto_email&&<p className="text-slate-400 italic">Sin contacto</p>}</div>
                <div><p className="text-slate-400 text-xs uppercase font-semibold mb-2">Límites</p><PBar label="Estudiantes" current={c.total_estudiantes??0} max={c.max_estudiantes}/><PBar label="Usuarios" current={c.total_usuarios??0} max={c.max_usuarios}/></div>
                <div><p className="text-slate-400 text-xs uppercase font-semibold mb-2">Info</p><p className="text-slate-600 text-xs"><Calendar size={14} className="inline mr-1"/>Creado: {c.fecha_creacion?new Date(c.fecha_creacion).toLocaleDateString():'N/A'}</p>{c.fecha_expiracion&&<p className="text-slate-600 text-xs mt-1">Expira: {new Date(c.fecha_expiracion).toLocaleDateString()}</p>}<p className="font-mono text-xs bg-slate-200 px-2 py-1 rounded mt-2 inline-block">Login: direccion_{c.codigo}</p></div>
              </div>
              <div className="flex gap-2 mt-3 pt-3 border-t border-slate-200">
                <button onClick={()=>aplicarPlan(c.id)} className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-purple-50 text-purple-700 border border-purple-200 rounded-lg hover:bg-purple-100 font-medium"><Zap size={14}/>Aplicar restricciones del plan "{c.plan}"</button>
                <button onClick={()=>abrirModulos(c.id)} className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-indigo-50 text-indigo-700 border border-indigo-200 rounded-lg hover:bg-indigo-100 font-medium"><Settings size={14}/>Módulos</button>
                <button onClick={()=>impersonar(c.id)} className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-indigo-50 text-indigo-700 border border-indigo-200 rounded-lg hover:bg-indigo-100 font-medium"><ArrowRightLeft size={14}/>Entrar como director</button>
              </div>
            </div>)}
            {confDel===c.id&&(<div className="border-t border-red-200 p-4 bg-red-50 flex items-center justify-between flex-wrap gap-2"><p className="text-red-700 text-sm font-medium">¿Desactivar "{c.nombre}"?</p><div className="flex gap-2"><button onClick={()=>setConfDel(null)} className="px-3 py-1.5 text-sm border border-slate-300 rounded-lg hover:bg-white">Cancelar</button><button onClick={()=>desactivar(c.id)} className="px-3 py-1.5 text-sm bg-red-600 text-white rounded-lg hover:bg-red-700">Desactivar</button></div></div>)}
          </div>
        ))}</div>
      )}
      {showModal&&(<Modal onClose={()=>{setShowModal(false);setCreds(null);}} title={edit?'Editar Colegio':'Crear Nuevo Colegio'}>
        {creds&&(<div className="mb-4 p-4 bg-green-50 border border-green-200 rounded-xl"><h3 className="font-bold text-green-800 mb-2 flex items-center gap-2"><Check size={20}/>Credenciales</h3><div className="bg-white rounded-lg p-3 space-y-2 font-mono text-sm"><CopyRow label="Usuario" value={creds.username}/><CopyRow label="Password" value={creds.password}/></div></div>)}
        {error&&<div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm flex items-center gap-2"><AlertTriangle size={16}/>{error}</div>}
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4"><FF label="Nombre *" value={edit?edit.nombre:nuevo.nombre} onChange={v=>edit?setEdit({...edit,nombre:v}):setNuevo({...nuevo,nombre:v})} placeholder="Colegio San Juan"/><FF label={`Código *${edit?' (no editable)':''}`} value={edit?edit.codigo:nuevo.codigo} onChange={v=>!edit&&setNuevo({...nuevo,codigo:v.toLowerCase().replace(/[^a-z0-9_-]/g,'')})} placeholder="sanjuan01" disabled={!!edit} mono/></div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4"><div><label className="block text-sm font-medium text-slate-700 mb-1">Plan</label><select value={edit?edit.plan:nuevo.plan} onChange={e=>edit?setEdit({...edit,plan:e.target.value}):setNuevo({...nuevo,plan:e.target.value})} className="w-full px-3 py-2.5 border border-slate-200 rounded-lg outline-none"><option value="basico">Básico</option><option value="premium">Premium</option><option value="enterprise">Enterprise</option></select></div><FF label="Máx Estudiantes" type="number" value={String(edit?edit.max_estudiantes:nuevo.max_estudiantes)} onChange={v=>edit?setEdit({...edit,max_estudiantes:+v}):setNuevo({...nuevo,max_estudiantes:+v})}/><FF label="Máx Usuarios" type="number" value={String(edit?edit.max_usuarios:nuevo.max_usuarios)} onChange={v=>edit?setEdit({...edit,max_usuarios:+v}):setNuevo({...nuevo,max_usuarios:+v})}/></div>
          <p className="text-sm font-medium text-slate-700">Contacto</p>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4"><FF value={edit?(edit.contacto_nombre||''):nuevo.contacto_nombre} onChange={v=>edit?setEdit({...edit,contacto_nombre:v}):setNuevo({...nuevo,contacto_nombre:v})} placeholder="Nombre"/><FF value={edit?(edit.contacto_email||''):nuevo.contacto_email} onChange={v=>edit?setEdit({...edit,contacto_email:v}):setNuevo({...nuevo,contacto_email:v})} placeholder="Email" type="email"/><FF value={edit?(edit.contacto_telefono||''):nuevo.contacto_telefono} onChange={v=>edit?setEdit({...edit,contacto_telefono:v}):setNuevo({...nuevo,contacto_telefono:v})} placeholder="Teléfono" type="tel"/></div>

          {!edit&&(<>
            <div className="border-t pt-4 mt-2">
              <p className="text-sm font-bold text-slate-700 mb-1">Módulos del plan</p>
              <p className="text-xs text-slate-500 mb-3">Active los módulos que el colegio tiene incluidos en su contrato. Solo verá estos en su panel. (Después puede ajustarlos en "Módulos".)</p>

              <p className="text-xs uppercase font-semibold text-slate-500 mb-2">Niveles educativos *</p>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-2 mb-4">
                {[
                  {key:'plan_secundaria' as const, label:'Secundaria', disabled:false},
                  {key:'plan_primaria' as const, label:'Primaria', disabled:false},
                  {key:'plan_inicial' as const, label:'Inicial (próximamente)', disabled:true},
                ].map(m=>(
                  <label key={m.key} className={`flex items-center gap-2 p-2 border border-slate-200 rounded-lg ${m.disabled ? 'opacity-50 cursor-not-allowed bg-slate-50' : 'cursor-pointer hover:bg-slate-50'}`}>
                    <input type="checkbox" checked={!m.disabled && nuevo[m.key]} disabled={m.disabled} onChange={e=>!m.disabled && setNuevo({...nuevo,[m.key]:e.target.checked})}/>
                    <span className="text-sm text-slate-700">{m.label}</span>
                  </label>
                ))}
              </div>

              <p className="text-xs uppercase font-semibold text-slate-500 mb-2">Módulos funcionales</p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {[
                  {key:'plan_whatsapp' as const,label:'WhatsApp'},
                  {key:'plan_psicologia' as const,label:'Psicología'},
                  {key:'plan_comunicacion_padres' as const,label:'Comunicación padres'},
                  {key:'plan_eval_profesores' as const,label:'Evaluación profesores'},
                  {key:'plan_eval_interna' as const,label:'Evaluación interna'},
                  {key:'plan_registro_escolar' as const,label:'Registro escolar MINERD'},
                  {key:'plan_reportes_conducta' as const,label:'Reportes de conducta'},
                ].map(m=>(
                  <label key={m.key} className="flex items-center gap-2 p-2 border border-slate-200 rounded-lg cursor-pointer hover:bg-slate-50">
                    <input type="checkbox" checked={nuevo[m.key]} onChange={e=>setNuevo({...nuevo,[m.key]:e.target.checked})}/>
                    <span className="text-sm text-slate-700">{m.label}</span>
                  </label>
                ))}
              </div>
            </div>
          </>)}
          {!edit&&!creds&&(<><p className="text-sm font-medium text-slate-700">Credenciales del Director</p><div className="grid grid-cols-1 md:grid-cols-2 gap-4"><FF value={nuevo.admin_username} onChange={v=>setNuevo({...nuevo,admin_username:v})} placeholder={`direccion_${nuevo.codigo||'codigo'}`} mono/><div className="relative"><input type={showPw?'text':'password'} value={nuevo.admin_password} onChange={e=>setNuevo({...nuevo,admin_password:e.target.value})} placeholder="(default: Cambiar123)" className="w-full px-3 py-2.5 pr-10 border border-slate-200 rounded-lg outline-none font-mono text-sm"/><button type="button" onClick={()=>setShowPw(!showPw)} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400">{showPw?<EyeOff size={16}/>:<Eye size={16}/>}</button></div></div></>)}
          {edit&&(<div className="grid grid-cols-1 md:grid-cols-2 gap-4"><FF label="Dominio" value={edit.dominio||''} onChange={v=>setEdit({...edit,dominio:v})} placeholder="colegio.edu.do"/><FF label="Expiración" type="date" value={edit.fecha_expiracion||''} onChange={v=>setEdit({...edit,fecha_expiracion:v})}/></div>)}
        </div>
        {!creds&&<div className="flex justify-end gap-3 mt-6 pt-4 border-t"><button onClick={()=>setShowModal(false)} className="px-5 py-2.5 border border-slate-300 rounded-xl hover:bg-slate-50 font-medium">Cancelar</button><button onClick={edit?editar:crear} className="px-5 py-2.5 bg-blue-600 text-white rounded-xl hover:bg-blue-700 font-medium">{edit?'Guardar':'Crear Colegio'}</button></div>}
      </Modal>)}
      {modulosColegio&&(<Modal onClose={()=>setModulosColegio(null)} title="Módulos del colegio (PLAN)">
        <p className="text-sm text-slate-600 mb-4">Active los módulos que este colegio tiene incluidos en su plan. El director sólo verá los módulos que active acá.</p>
        <div className="space-y-4">
          <div>
            <h3 className="text-sm font-bold text-slate-700 mb-3 uppercase tracking-wide">Niveles educativos</h3>
            <div className="space-y-2">
              {[
                {key:'secundaria',label:'Secundaria',desc:'6 grados secundarios con calificaciones por parcial', disabled:false},
                {key:'primaria',label:'Primaria',desc:'6 grados primarios con calificaciones por competencia (MINERD)', disabled:false},
                {key:'inicial',label:'Inicial',desc:'Preprimario (próximamente disponible)', disabled:true},
              ].map(m=>(
                <label key={m.key} className={`flex items-start gap-3 p-3 border border-slate-200 rounded-lg ${m.disabled ? 'opacity-50 cursor-not-allowed bg-slate-50' : 'hover:bg-slate-50 cursor-pointer'}`}>
                  <input type="checkbox" checked={!m.disabled && !!modulosColegio.plan[m.key]} onChange={()=>!m.disabled && toggleModulo(m.key)} disabled={m.disabled} className="mt-1"/>
                  <div><p className="font-medium text-slate-800">{m.label}</p><p className="text-xs text-slate-500">{m.desc}</p></div>
                </label>
              ))}
            </div>
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-700 mb-3 uppercase tracking-wide">Módulos funcionales</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {[
                {key:'whatsapp',label:'WhatsApp'},
                {key:'psicologia',label:'Psicología'},
                {key:'comunicacion_padres',label:'Comunicación padres'},
                {key:'eval_profesores',label:'Evaluación profesores'},
                {key:'eval_interna',label:'Evaluación interna'},
                {key:'registro_escolar',label:'Registro escolar MINERD'},
                {key:'reportes_conducta',label:'Reportes de conducta'},
              ].map(m=>(
                <label key={m.key} className="flex items-center gap-2 p-2 border border-slate-200 rounded-lg cursor-pointer hover:bg-slate-50">
                  <input type="checkbox" checked={!!modulosColegio.plan[m.key]} onChange={()=>toggleModulo(m.key)}/>
                  <span className="text-sm text-slate-700">{m.label}</span>
                </label>
              ))}
            </div>
          </div>
        </div>
        <div className="flex justify-end gap-3 mt-6 pt-4 border-t">
          <button onClick={()=>setModulosColegio(null)} className="px-5 py-2.5 border border-slate-300 rounded-xl hover:bg-slate-50 font-medium">Cancelar</button>
          <button onClick={guardarModulos} className="px-5 py-2.5 bg-indigo-600 text-white rounded-xl hover:bg-indigo-700 font-medium">Guardar módulos</button>
        </div>
      </Modal>)}
    </div>
  );
};

// ===== USUARIOS =====
const UsuariosTab=()=>{
  const [colegios,setColegios]=useState<Colegio[]>([]);const [sel,setSel]=useState<number|null>(null);const [usuarios,setUsuarios]=useState<UsuarioColegio[]>([]);const [loading,setLoading]=useState(false);const [error,setError]=useState('');const [success,setSuccess]=useState('');const [resetM,setResetM]=useState<UsuarioColegio|null>(null);const [newPw,setNewPw]=useState('Cambiar123');const [crearM,setCrearM]=useState(false);const [nu,setNu]=useState({username:'',nombre:'',apellido:'',role:'profesor',email:'',password:'Cambiar123'});
  useEffect(()=>{api.get('/superadmin/colegios').then(r=>setColegios(r.data.filter((c:Colegio)=>c.activo)));},[]);useEffect(()=>{if(success){const t=setTimeout(()=>setSuccess(''),4000);return()=>clearTimeout(t);}},[success]);
  const load=async(id:number)=>{setLoading(true);setSel(id);try{const r=await api.get(`/superadmin/colegios/${id}/usuarios`);setUsuarios(r.data);}catch(e:any){setError(e.response?.data?.error||'Error');}finally{setLoading(false);}};
  const resetPw=async()=>{if(!resetM||!sel)return;try{await api.post(`/superadmin/colegios/${sel}/reset-password`,{usuario_id:resetM.id,password:newPw});setSuccess(`Password reseteado para ${resetM.nombre_completo}`);setResetM(null);}catch(e:any){setError(e.response?.data?.error||'Error');}};
  const toggle=async(u:UsuarioColegio)=>{if(!sel)return;try{const r=await api.post(`/superadmin/colegios/${sel}/toggle-usuario`,{usuario_id:u.id});setSuccess(r.data.message);load(sel);}catch(e:any){setError(e.response?.data?.error||'Error');}};
  const crearUsr=async()=>{if(!sel||!nu.username||!nu.nombre){setError('Username y nombre requeridos');return;}try{const r=await api.post(`/superadmin/colegios/${sel}/crear-usuario`,nu);setSuccess(`Usuario ${r.data.username} creado (pw: ${r.data.password})`);setCrearM(false);setNu({username:'',nombre:'',apellido:'',role:'profesor',email:'',password:'Cambiar123'});load(sel);}catch(e:any){setError(e.response?.data?.error||'Error');}};
  return(
    <div className="space-y-4">
      <Alerts error={error} success={success} onCE={()=>setError('')} onCS={()=>setSuccess('')}/>
      <div className="bg-white rounded-xl border border-slate-200 p-4 flex flex-col sm:flex-row gap-3 items-start sm:items-center">
        <label className="text-sm font-medium text-slate-700 whitespace-nowrap">Colegio:</label>
        <select value={sel||''} onChange={e=>e.target.value&&load(+e.target.value)} className="flex-1 px-3 py-2.5 border border-slate-200 rounded-lg outline-none"><option value="">-- Seleccione --</option>{colegios.map(c=><option key={c.id} value={c.id}>{c.nombre} ({c.codigo})</option>)}</select>
        {sel&&<button onClick={()=>setCrearM(true)} className="flex items-center gap-2 px-4 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium whitespace-nowrap"><UserPlus size={16}/>Crear Usuario</button>}
      </div>
      {!sel?<Empty icon={Users} text="Seleccione un colegio"/>:loading?<Loading/>:usuarios.length===0?<Empty icon={Users} text="Sin usuarios"/>:(
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden"><div className="overflow-x-auto"><table className="w-full text-sm"><thead className="bg-slate-50 border-b border-slate-200"><tr><th className="text-left px-4 py-3 font-medium text-slate-600">Usuario</th><th className="text-left px-4 py-3 font-medium text-slate-600">Nombre</th><th className="text-left px-4 py-3 font-medium text-slate-600">Rol</th><th className="text-left px-4 py-3 font-medium text-slate-600">Email</th><th className="text-left px-4 py-3 font-medium text-slate-600">Estado</th><th className="text-right px-4 py-3 font-medium text-slate-600">Acciones</th></tr></thead>
        <tbody>{usuarios.map(u=>(<tr key={u.id} className="border-b border-slate-100 hover:bg-slate-50"><td className="px-4 py-3 font-mono text-xs">{u.username}</td><td className="px-4 py-3 font-medium text-slate-800">{u.nombre_completo}</td><td className="px-4 py-3"><span className={`text-xs px-2 py-0.5 rounded-full font-medium ${roleC[u.role]||'bg-slate-100'}`}>{u.role}</span></td><td className="px-4 py-3 text-slate-500">{u.email||'—'}</td><td className="px-4 py-3"><span className={`text-xs px-2 py-0.5 rounded-full font-medium ${u.activo?'bg-green-100 text-green-700':'bg-red-100 text-red-600'}`}>{u.activo?'Activo':'Inactivo'}</span></td><td className="px-4 py-3 text-right"><button onClick={()=>{setResetM(u);setNewPw('Cambiar123');}} className="p-1.5 text-slate-400 hover:text-amber-600 hover:bg-amber-50 rounded-lg" title="Reset password"><Key size={16}/></button><button onClick={()=>toggle(u)} className={`p-1.5 rounded-lg ml-1 ${u.activo?'text-slate-400 hover:text-red-600 hover:bg-red-50':'text-slate-400 hover:text-green-600 hover:bg-green-50'}`} title={u.activo?'Desactivar':'Activar'}><Power size={16}/></button></td></tr>))}</tbody></table></div></div>
      )}
      {resetM&&(<Modal onClose={()=>setResetM(null)} title={`Reset Password — ${resetM.nombre_completo}`} small><p className="text-sm text-slate-600 mb-4">Usuario: <strong className="font-mono">{resetM.username}</strong></p><FF label="Nueva contraseña" value={newPw} onChange={setNewPw}/><div className="flex justify-end gap-3 mt-4"><button onClick={()=>setResetM(null)} className="px-4 py-2 border border-slate-300 rounded-lg text-sm">Cancelar</button><button onClick={resetPw} className="px-4 py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 text-sm font-medium flex items-center gap-2"><Key size={16}/>Resetear</button></div></Modal>)}
      {crearM&&(<Modal onClose={()=>setCrearM(false)} title="Crear Usuario" small><div className="space-y-3"><FF label="Username *" value={nu.username} onChange={v=>setNu({...nu,username:v})} mono/><div className="grid grid-cols-2 gap-3"><FF label="Nombre *" value={nu.nombre} onChange={v=>setNu({...nu,nombre:v})}/><FF label="Apellido" value={nu.apellido} onChange={v=>setNu({...nu,apellido:v})}/></div><div className="grid grid-cols-2 gap-3"><div><label className="block text-sm font-medium text-slate-700 mb-1">Rol</label><select value={nu.role} onChange={e=>setNu({...nu,role:e.target.value})} className="w-full px-3 py-2.5 border border-slate-200 rounded-lg outline-none"><option value="direccion">Dirección</option><option value="coordinador">Coordinador</option><option value="profesor">Profesor</option><option value="psicologia">Psicología</option><option value="secretaria">Secretaria</option></select></div><FF label="Password" value={nu.password} onChange={v=>setNu({...nu,password:v})} mono/></div><FF label="Email" value={nu.email} onChange={v=>setNu({...nu,email:v})} type="email"/></div>{error&&<div className="mt-3 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">{error}</div>}<div className="flex justify-end gap-3 mt-4"><button onClick={()=>setCrearM(false)} className="px-4 py-2 border border-slate-300 rounded-lg text-sm">Cancelar</button><button onClick={crearUsr} className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium">Crear</button></div></Modal>)}
    </div>
  );
};

// ===== ALERTAS =====
const AlertasTab=()=>{
  const [alertas,setAlertas]=useState<Alerta[]>([]);const [loading,setLoading]=useState(true);
  useEffect(()=>{api.get('/superadmin/alertas').then(r=>{setAlertas(r.data);setLoading(false);}).catch(()=>setLoading(false));},[]);
  const prioColor:Record<string,string>={alta:'bg-red-50 border-red-200 text-red-700',media:'bg-amber-50 border-amber-200 text-amber-700',baja:'bg-slate-50 border-slate-200 text-slate-600'};
  const prioIcon:Record<string,any>={alta:AlertTriangle,media:Bell,baja:Activity};
  if(loading)return <Loading/>;
  return(
    <div className="space-y-4">
      <div className="flex items-center justify-between"><h2 className="text-lg font-semibold text-slate-800">Alertas y Notificaciones</h2><button onClick={()=>{setLoading(true);api.get('/superadmin/alertas').then(r=>{setAlertas(r.data);setLoading(false);});}} className="p-2 text-slate-500 hover:text-blue-600 rounded-lg"><RefreshCw size={18}/></button></div>
      {alertas.length===0?<Empty icon={Check} text="Sin alertas — todo está bien"/>:(
        <div className="space-y-2">{alertas.map((a,i)=>{const I=prioIcon[a.prioridad]||Activity;return(
          <div key={i} className={`flex items-start gap-3 p-4 rounded-xl border ${prioColor[a.prioridad]||prioColor.baja}`}>
            <I size={20} className="shrink-0 mt-0.5"/><div className="flex-1"><p className="text-sm font-medium">{a.mensaje}</p><p className="text-xs mt-1 opacity-70">{a.colegio} · {a.tipo.replace(/_/g,' ')}</p></div>
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${a.prioridad==='alta'?'bg-red-200 text-red-800':a.prioridad==='media'?'bg-amber-200 text-amber-800':'bg-slate-200 text-slate-700'}`}>{a.prioridad}</span>
          </div>
        );})}</div>
      )}
    </div>
  );
};

// ===== LOGS =====
const LogsTab=()=>{
  const [sub,setSub]=useState<'accesos'|'auditoria'>('accesos');const [logs,setLogs]=useState<LogEntry[]>([]);const [accesos,setAccesos]=useState<AccesoEntry[]>([]);const [colegios,setColegios]=useState<Colegio[]>([]);const [fc,setFc]=useState('');const [loading,setLoading]=useState(true);
  useEffect(()=>{api.get('/superadmin/colegios').then(r=>setColegios(r.data));},[]);useEffect(()=>{loadD();},[sub,fc]);
  const loadD=async()=>{setLoading(true);try{const p=new URLSearchParams({limit:'100'});if(fc)p.set('colegio_id',fc);if(sub==='auditoria'){setLogs((await api.get(`/superadmin/logs?${p}`)).data);}else{const p2=new URLSearchParams({limit:'50'});if(fc)p2.set('colegio_id',fc);setAccesos((await api.get(`/superadmin/accesos?${p2}`)).data);}}catch{}finally{setLoading(false);}};
  const tIcon=(t:string)=>{if(t==='login')return <LogIn size={14} className="text-green-500"/>;if(t==='logout')return <LogOutIcon size={14} className="text-slate-400"/>;if(t==='login_fallido')return <AlertTriangle size={14} className="text-red-500"/>;return <Activity size={14} className="text-blue-500"/>;};
  return(
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="flex bg-slate-100 rounded-xl p-1"><button onClick={()=>setSub('accesos')} className={`px-4 py-2 rounded-lg text-sm font-medium ${sub==='accesos'?'bg-white text-blue-600 shadow-sm':'text-slate-600'}`}>Accesos</button><button onClick={()=>setSub('auditoria')} className={`px-4 py-2 rounded-lg text-sm font-medium ${sub==='auditoria'?'bg-white text-blue-600 shadow-sm':'text-slate-600'}`}>Auditoría</button></div>
        <select value={fc} onChange={e=>setFc(e.target.value)} className="px-3 py-2 border border-slate-200 rounded-lg outline-none text-sm"><option value="">Todos los colegios</option>{colegios.map(c=><option key={c.id} value={c.id}>{c.nombre}</option>)}</select>
        <button onClick={loadD} className="p-2 text-slate-500 hover:text-blue-600 hover:bg-blue-50 rounded-lg"><RefreshCw size={18}/></button>
      </div>
      {loading?<Loading/>:(
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden"><div className="overflow-x-auto"><table className="w-full text-sm"><thead className="bg-slate-50 border-b border-slate-200"><tr>{sub==='accesos'?<><th className="text-left px-4 py-3 font-medium text-slate-600">Tipo</th><th className="text-left px-4 py-3 font-medium text-slate-600">Usuario</th><th className="text-left px-4 py-3 font-medium text-slate-600">Colegio</th><th className="text-left px-4 py-3 font-medium text-slate-600">IP</th><th className="text-left px-4 py-3 font-medium text-slate-600">Fecha</th></>:<><th className="text-left px-4 py-3 font-medium text-slate-600">Acción</th><th className="text-left px-4 py-3 font-medium text-slate-600">Usuario</th><th className="text-left px-4 py-3 font-medium text-slate-600">Colegio</th><th className="text-left px-4 py-3 font-medium text-slate-600">Entidad</th><th className="text-left px-4 py-3 font-medium text-slate-600">Fecha</th></>}</tr></thead>
        <tbody>{sub==='accesos'?accesos.map(a=>(<tr key={a.id} className="border-b border-slate-100 hover:bg-slate-50"><td className="px-4 py-3 flex items-center gap-2">{tIcon(a.tipo)}<span className="capitalize">{a.tipo?.replace('_',' ')}</span></td><td className="px-4 py-3 font-medium">{a.usuario||'—'}</td><td className="px-4 py-3 text-slate-500">{a.colegio||'—'}</td><td className="px-4 py-3 font-mono text-xs text-slate-400">{a.ip}</td><td className="px-4 py-3 text-slate-500 text-xs">{a.fecha?new Date(a.fecha).toLocaleString():'—'}</td></tr>)):logs.map(l=>(<tr key={l.id} className="border-b border-slate-100 hover:bg-slate-50"><td className="px-4 py-3"><span className="text-xs font-mono bg-slate-100 px-2 py-0.5 rounded">{l.accion}</span></td><td className="px-4 py-3 font-medium">{l.usuario||'—'}</td><td className="px-4 py-3 text-slate-500">{l.colegio||'—'}</td><td className="px-4 py-3 text-slate-500">{l.entidad}</td><td className="px-4 py-3 text-slate-500 text-xs">{l.fecha?new Date(l.fecha).toLocaleString():'—'}</td></tr>))}</tbody>
        </table></div>{(sub==='accesos'?accesos:logs).length===0&&<div className="text-center py-10 text-slate-400">No hay registros</div>}</div>
      )}
    </div>
  );
};

// ===== STATS =====
const StatsTab=()=>{
  const [data,setData]=useState<StatsDetalle[]>([]);const [loading,setLoading]=useState(true);
  useEffect(()=>{api.get('/superadmin/stats/detalle').then(r=>{setData(r.data);setLoading(false);}).catch(()=>setLoading(false));},[]);
  if(loading)return <Loading/>;
  const t=data.reduce((a,c)=>({e:a.e+c.estudiantes,p:a.p+c.profesores,u:a.u+c.usuarios,c:a.c+c.cursos}),{e:0,p:0,u:0,c:0});
  return(
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">{[{l:'Total Estudiantes',v:t.e,c:'text-emerald-600'},{l:'Total Profesores',v:t.p,c:'text-blue-600'},{l:'Total Usuarios',v:t.u,c:'text-amber-600'},{l:'Total Cursos',v:t.c,c:'text-purple-600'}].map((s,i)=>(<div key={i} className="bg-white rounded-xl border border-slate-200 p-4 text-center"><p className={`text-3xl font-bold ${s.c}`}>{s.v.toLocaleString()}</p><p className="text-xs text-slate-500 mt-1">{s.l}</p></div>))}</div>
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden"><div className="overflow-x-auto"><table className="w-full text-sm"><thead className="bg-slate-50 border-b border-slate-200"><tr><th className="text-left px-4 py-3 font-medium text-slate-600">Colegio</th><th className="text-left px-4 py-3 font-medium text-slate-600">Plan</th><th className="text-center px-4 py-3 font-medium text-slate-600">Est.</th><th className="text-center px-4 py-3 font-medium text-slate-600">Prof.</th><th className="text-center px-4 py-3 font-medium text-slate-600">Usr.</th><th className="text-center px-4 py-3 font-medium text-slate-600">Cursos</th><th className="px-4 py-3 font-medium text-slate-600">Uso Est.</th><th className="px-4 py-3 font-medium text-slate-600">Uso Usr.</th></tr></thead>
      <tbody>{data.map(c=>{const pe=c.max_estudiantes?Math.round(c.estudiantes/c.max_estudiantes*100):0;const pu=c.max_usuarios?Math.round(c.usuarios/c.max_usuarios*100):0;return(<tr key={c.id} className="border-b border-slate-100 hover:bg-slate-50"><td className="px-4 py-3"><p className="font-medium text-slate-800">{c.nombre}</p><p className="font-mono text-xs text-slate-400">{c.codigo}</p></td><td className="px-4 py-3"><span className={`text-xs px-2 py-0.5 rounded-full font-medium ${planC[c.plan]}`}>{c.plan}</span></td><td className="px-4 py-3 text-center font-bold">{c.estudiantes}</td><td className="px-4 py-3 text-center">{c.profesores}</td><td className="px-4 py-3 text-center">{c.usuarios}</td><td className="px-4 py-3 text-center">{c.cursos}</td><td className="px-4 py-3 w-32"><MBar pct={pe}/></td><td className="px-4 py-3 w-32"><MBar pct={pu}/></td></tr>);})}</tbody></table></div></div>
    </div>
  );
};

// ===== MI CUENTA =====
const ConfigTab=()=>{
  const [pwActual,setPwActual]=useState('');const [pwNueva,setPwNueva]=useState('');const [pwConfirm,setPwConfirm]=useState('');const [error,setError]=useState('');const [success,setSuccess]=useState('');const [showPw,setShowPw]=useState(false);
  useEffect(()=>{if(success){const t=setTimeout(()=>setSuccess(''),4000);return()=>clearTimeout(t);}},[success]);
  const cambiarPw=async()=>{setError('');if(!pwActual){setError('Ingrese contraseña actual');return;}if(pwNueva.length<8){setError('La nueva contraseña debe tener al menos 8 caracteres');return;}if(pwNueva!==pwConfirm){setError('Las contraseñas no coinciden');return;}try{await api.post('/superadmin/cambiar-password',{password_actual:pwActual,password_nueva:pwNueva});setSuccess('Contraseña actualizada');setPwActual('');setPwNueva('');setPwConfirm('');}catch(e:any){setError(e.response?.data?.error||'Error');}};
  // Volver de impersonación
  const volverSuperadmin=()=>{const saToken=localStorage.getItem('superadmin_token');const saUser=localStorage.getItem('superadmin_user');if(saToken){localStorage.setItem('token',saToken);if(saUser)localStorage.setItem('user',saUser);localStorage.removeItem('superadmin_token');localStorage.removeItem('superadmin_user');window.location.href='/superadmin';}};
  const isImpersonating=!!localStorage.getItem('superadmin_token');

  return(
    <div className="space-y-6 max-w-xl">
      <Alerts error={error} success={success} onCE={()=>setError('')} onCS={()=>setSuccess('')}/>
      {isImpersonating&&(
        <div className="p-4 bg-indigo-50 border border-indigo-200 rounded-xl">
          <p className="text-indigo-700 text-sm font-medium mb-2">Estás viendo un colegio como director (modo impersonación)</p>
          <button onClick={volverSuperadmin} className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 text-sm font-medium"><ArrowRightLeft size={16}/>Volver a Super Admin</button>
        </div>
      )}
      <div className="bg-white rounded-xl border border-slate-200 p-6">
        <h3 className="text-lg font-semibold text-slate-800 mb-4 flex items-center gap-2"><Lock size={20}/>Cambiar Contraseña</h3>
        <div className="space-y-3">
          <div className="relative"><FF label="Contraseña actual" type={showPw?'text':'password'} value={pwActual} onChange={setPwActual}/></div>
          <FF label="Nueva contraseña (mínimo 8 caracteres)" type={showPw?'text':'password'} value={pwNueva} onChange={setPwNueva}/>
          <FF label="Confirmar nueva contraseña" type={showPw?'text':'password'} value={pwConfirm} onChange={setPwConfirm}/>
          <label className="flex items-center gap-2 text-sm text-slate-600"><input type="checkbox" checked={showPw} onChange={e=>setShowPw(e.target.checked)} className="rounded"/>Mostrar contraseñas</label>
        </div>
        <button onClick={cambiarPw} className="mt-4 px-5 py-2.5 bg-blue-600 text-white rounded-xl hover:bg-blue-700 font-medium">Cambiar Contraseña</button>
      </div>
      <div className="bg-white rounded-xl border border-slate-200 p-6">
        <h3 className="text-lg font-semibold text-slate-800 mb-2">Información</h3>
        <p className="text-sm text-slate-600">Rol: <span className="font-medium text-red-600">Super Administrador</span></p>
        <p className="text-sm text-slate-500 mt-2">El superadmin tiene acceso total a todos los colegios, puede crear/desactivar escuelas, resetear contraseñas, y entrar como director de cualquier colegio para dar soporte.</p>
      </div>
    </div>
  );
};

export default SuperAdminPage;
