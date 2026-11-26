"""Banco Linux de memoria y respuesta del Registro de Secundaria (SOLO datos sintéticos).

  python3 banco_linux.py <etiqueta> <contenedor> <dir_salida> <semilla.json> <token.txt>

Corre en el runner, FUERA del contenedor medido (no suma memoria). El servidor
(uvicorn, 2 workers) está en un contenedor con --memory=512m --memory-swap=512m.
Muestrea cada 50 ms, desde el cgroup v2 del contenedor:
  memory.current (todo lo que cuenta para el límite), memory.stat:anon (memoria
  de los procesos, sin caché de archivos), memory.events (oom, oom_kill) y el RSS
  de cada proceso (cgroup.procs + /proc/<pid>/status). Detecta reinicios de
  workers (pids nuevos) y del contenedor.
Escenarios (mismos que el banco de Windows): sucesivas 1ro/4to-6to, oficiales y
borradores simultáneos de 4to-6to, espera de turno, errores dentro del turno y
muerte del worker que genera. Sondas cada 200 ms durante los simultáneos y la
espera (/api/health y /api/ano-escolar con sesión).
"""
import json, os, statistics, subprocess, sys, threading, time, urllib.request, urllib.error

ETIQ, CONT, SALIDA, SEMILLA, TOKEN_F = sys.argv[1:6]
os.makedirs(SALIDA, exist_ok=False)
BASE = 'http://127.0.0.1:8000'
SEM = json.load(open(SEMILLA))
CUR = {'1A': SEM['cursos']['A'], '1B': SEM['cursos']['B'], '1C': SEM['cursos']['C'],
       '4D': SEM['cursos']['D'], '5E': SEM['cursos']['E'], '6F': SEM['cursos']['F']}
TOKEN = open(TOKEN_F).read().strip()
MiB = 2 ** 20


def docker_inspect():
    out = subprocess.run(['docker', 'inspect', CONT], capture_output=True, text=True).stdout
    return json.loads(out)[0] if out.strip() else {}


def cgroup_dir():
    cid = docker_inspect()['Id']
    for d in ('/sys/fs/cgroup/system.slice/docker-%s.scope' % cid, '/sys/fs/cgroup/docker/%s' % cid):
        if os.path.isdir(d):
            return d
    r = subprocess.run(['find', '/sys/fs/cgroup', '-maxdepth', '4', '-type', 'd', '-name', '*%s*' % cid],
                       capture_output=True, text=True).stdout.split()
    if r:
        return r[0]
    raise SystemExit('no encuentro el cgroup del contenedor')


CG = cgroup_dir()


def leer(nombre):
    try:
        return open(os.path.join(CG, nombre)).read()
    except OSError:
        return ''


def clave(texto, k):
    for l in texto.splitlines():
        p = l.split()
        if len(p) == 2 and p[0] == k:
            return int(p[1])
    return 0


def rss(pid):
    try:
        for l in open('/proc/%d/status' % pid):
            if l.startswith('VmRSS:'):
                return int(l.split()[1]) * 1024
    except OSError:
        pass
    return 0


T0 = time.perf_counter()
ahora = lambda: round(time.perf_counter() - T0, 2)  # noqa: E731
linea, sondas, pids_vistos = [], [], {}
parar = threading.Event(); sondear = threading.Event()


def muestrear():
    while not parar.is_set():
        cur = clave('memory_current ' + leer('memory.current').strip(), 'memory_current')
        stat = leer('memory.stat')
        pids = [int(x) for x in leer('cgroup.procs').split()]
        rs = {p: rss(p) for p in pids}
        t = ahora()
        for p in pids:
            pids_vistos.setdefault(p, t)
        ev = leer('memory.events')
        linea.append({'t': t, 'actual': cur, 'anon': clave(stat, 'anon'), 'file': clave(stat, 'file'),
                      'rss_total': sum(rs.values()), 'rss': rs, 'oom_kill': clave(ev, 'oom_kill'), 'oom': clave(ev, 'oom')})
        time.sleep(0.05)


def pedir(ruta, token=TOKEN, timeout=180):
    req = urllib.request.Request(BASE + ruta, headers={'Authorization': 'Bearer ' + token} if token else {})
    t0 = time.perf_counter(); ini = ahora()
    try:
        r = urllib.request.urlopen(req, timeout=timeout); cuerpo = r.read(); estado = r.status
    except urllib.error.HTTPError as e:
        cuerpo = e.read(); estado = e.code
    except Exception as e:
        return {'ruta': ruta, 'estado': 'sin respuesta: %s' % type(e).__name__, 'ini': ini, 'seg': round(time.perf_counter() - t0, 2)}
    return {'ruta': ruta, 'estado': estado, 'bytes': len(cuerpo), 'ini': ini, 'seg': round(time.perf_counter() - t0, 2),
            'detalle': cuerpo[:200].decode('utf-8', 'replace') if estado != 200 else None}


def sonda():
    i = 0
    while not parar.is_set():
        if sondear.is_set():
            ruta, tok = ('/api/health', None) if i % 2 == 0 else ('/api/ano-escolar', TOKEN)
            r = pedir(ruta, tok, timeout=60)
            sondas.append({'t': r['ini'], 'ruta': ruta, 'estado': r['estado'], 'seg': r['seg']})
            i += 1
            time.sleep(0.2)
        else:
            time.sleep(0.05)


def resumen_sondas(lista):
    lat = sorted(s['seg'] for s in lista if s['estado'] == 200)
    fallos = sum(1 for s in lista if s['estado'] != 200)
    if not lat:
        return {'n': len(lista), 'fallos': fallos}
    return {'n': len(lista), 'fallos': fallos, 'p50_seg': round(statistics.median(lat), 3),
            'p95_seg': round(lat[int(0.95 * (len(lat) - 1))], 3), 'max_seg': round(lat[-1], 3),
            'mas_de_1s': sum(1 for x in lat if x > 1.0)}


def esperar_listo(limite=120):
    fin = time.time() + limite
    while time.time() < fin:
        try:
            if urllib.request.urlopen(BASE + '/api/health', timeout=5).status == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


threading.Thread(target=muestrear, daemon=True).start()
threading.Thread(target=sonda, daemon=True).start()
resumen = {'etiqueta': ETIQ, 'limite_MiB': 512, 'workers': 2, 'cgroup': CG}
ins0 = docker_inspect()
PID_MAESTRO = ins0['State']['Pid']
try:
    assert esperar_listo(), 'el servidor no arrancó'
    time.sleep(3)
    m = linea[-1]
    resumen['reposo'] = {'actual_MiB': round(m['actual'] / MiB, 1), 'anon_MiB': round(m['anon'] / MiB, 1),
                         'rss_total_MiB': round(m['rss_total'] / MiB, 1), 'procesos': len(m['rss'])}
    pids_iniciales = set(m['rss'])
    oom0 = m['oom_kill']

    def tramo(nombre, fn, con_sondas=False):
        i0, s0 = len(linea), len(sondas)
        t_ini = ahora()
        if con_sondas:
            sondear.set()
        try:
            res = fn()
        finally:
            sondear.clear()
        time.sleep(2)
        tr = linea[i0:]
        resumen[nombre] = {
            'desde_seg': t_ini, 'hasta_seg': ahora(),
            'pico_actual_MiB': round(max(x['actual'] for x in tr) / MiB, 1),
            'pico_anon_MiB': round(max(x['anon'] for x in tr) / MiB, 1),
            'pico_rss_total_MiB': round(max(x['rss_total'] for x in tr) / MiB, 1),
            'final_actual_MiB': round(tr[-1]['actual'] / MiB, 1),
            'final_anon_MiB': round(tr[-1]['anon'] / MiB, 1),
            'oom_kill_en_tramo': tr[-1]['oom_kill'] - tr[0]['oom_kill'],
            'peticiones': res,
        }
        if con_sondas:
            resumen[nombre]['sondas'] = resumen_sondas(sondas[s0:])
        print(nombre, {k: v for k, v in resumen[nombre].items() if k != 'peticiones'}, flush=True)

    def oficial(c):
        return '/api/registros/secundaria/%d?force=true' % CUR[c]

    def borrador(c):
        return '/api/registros/secundaria/%d/preview-pdf' % CUR[c]

    def en_paralelo(rutas, desfase=0.0):
        res = [None] * len(rutas); hs = []
        for i, r in enumerate(rutas):
            h = threading.Thread(target=lambda i=i, r=r: res.__setitem__(i, pedir(r)))
            h.start(); hs.append(h)
            if desfase:
                time.sleep(desfase)
        [h.join() for h in hs]
        return res

    def sucesivas():
        out = []
        for c in ('1A', '4D', '5E', '6F', '1A', '4D', '5E', '6F'):
            r = pedir(oficial(c)); time.sleep(1.5)
            r['tras_actual_MiB'] = round(linea[-1]['actual'] / MiB, 1)
            r['tras_anon_MiB'] = round(linea[-1]['anon'] / MiB, 1)
            out.append(r)
        return out

    tramo('sucesivas_1ro_y_4to_6to', sucesivas)
    tramo('simultaneas_oficial_4to_6to', lambda: [en_paralelo([oficial('4D'), oficial('6F')]),
                                                  en_paralelo([oficial('5E'), oficial('1B')]),
                                                  en_paralelo([oficial('6F'), oficial('4D')])], con_sondas=True)
    tramo('simultaneas_borrador_4to_6to', lambda: [en_paralelo([borrador('4D'), borrador('6F')]),
                                                   en_paralelo([borrador('5E'), borrador('6F')]),
                                                   en_paralelo([borrador('4D'), borrador('5E')])], con_sondas=True)
    tramo('espera_de_turno', lambda: [en_paralelo([oficial('6F'), oficial('4D')], desfase=0.7),
                                      en_paralelo([borrador('6F'), borrador('4D')], desfase=0.7)], con_sondas=True)

    def errores():
        out = {'validacion_44': pedir(oficial('1C')), 'dibujo_44_borrador': pedir(borrador('1C'))}
        out['normal_justo_despues'] = pedir(oficial('1A'))
        return out
    tramo('errores_dentro_del_turno', errores)

    def muerte():
        out = {}
        h = threading.Thread(target=lambda: out.__setitem__('en_curso', pedir(oficial('6F'))))
        h.start()
        time.sleep(2.5)
        a, b = linea[-21]['rss'], linea[-1]['rss']
        gan = {p: b[p] - a.get(p, 0) for p in b if p != PID_MAESTRO}
        if gan:
            victima = max(gan, key=gan.get)
            subprocess.run(['sudo', 'kill', '-9', str(victima)])
            out['worker_terminado'] = {'pid': victima, 'ganancia_MiB': round(gan[victima] / MiB, 1), 't': ahora()}
        h.join()
        time.sleep(3)
        out['procesos_tras_morir'] = len(linea[-1]['rss'])
        out['siguiente'] = pedir(oficial('1A'), timeout=120)
        out['procesos_al_final'] = len(linea[-1]['rss'])
        return out
    tramo('muerte_de_un_worker', muerte)

    fin = linea[-1]
    pico_cg = leer('memory.peak').strip()
    resumen['global'] = {
        'pico_actual_MiB': round(max(x['actual'] for x in linea) / MiB, 1),
        'pico_anon_MiB': round(max(x['anon'] for x in linea) / MiB, 1),
        'pico_rss_total_MiB': round(max(x['rss_total'] for x in linea) / MiB, 1),
        'memory_peak_cgroup_MiB': round(int(pico_cg) / MiB, 1) if pico_cg.isdigit() else None,
        'oom_kill_total': fin['oom_kill'] - oom0,
        'pids_de_worker_nuevos': sorted(p for p in pids_vistos if p not in pids_iniciales),
        'peticiones_registro_no_200': None,
    }
finally:
    parar.set()
    time.sleep(0.2)
    ins = docker_inspect()
    resumen['contenedor'] = {k: ins.get('State', {}).get(k) for k in ('Status', 'OOMKilled', 'ExitCode', 'Restarting')}
    resumen['contenedor']['RestartCount'] = ins.get('RestartCount')
    with open(os.path.join(SALIDA, 'linea_tiempo.csv'), 'w') as f:
        f.write('seg,actual_MiB,anon_MiB,file_MiB,rss_total_MiB,procesos,oom_kill\n')
        for x in linea:
            f.write('%.2f,%.1f,%.1f,%.1f,%.1f,%d,%d\n' % (x['t'], x['actual'] / MiB, x['anon'] / MiB, x['file'] / MiB,
                                                       x['rss_total'] / MiB, len(x['rss']), x['oom_kill']))
    with open(os.path.join(SALIDA, 'sondas.csv'), 'w') as f:
        f.write('seg,ruta,estado,latencia_seg\n')
        for s in sondas:
            f.write('%s,%s,%s,%s\n' % (s['t'], s['ruta'], s['estado'], s['seg']))

# Peticiones de Registro que no fueron 200 (los 400/422 de 1ro C son esperados).
no200 = []
for k, v in resumen.items():
    if isinstance(v, dict) and 'peticiones' in v:
        cola = [v['peticiones']]
        while cola:
            x = cola.pop()
            if isinstance(x, list):
                cola.extend(x)
            elif isinstance(x, dict) and 'ruta' in x:
                if x['estado'] != 200:
                    no200.append({'tramo': k, 'ruta': x['ruta'], 'estado': x['estado']})
            elif isinstance(x, dict):
                cola.extend(x.values())
if 'global' in resumen:
    resumen['global']['peticiones_registro_no_200'] = no200
json.dump(resumen, open(os.path.join(SALIDA, 'resumen.json'), 'w'), indent=1, ensure_ascii=False)
print(json.dumps({k: resumen.get(k) for k in ('reposo', 'global', 'contenedor')}, ensure_ascii=False))
