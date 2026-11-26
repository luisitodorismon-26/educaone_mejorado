"""Resume en Markdown las ejecuciones del banco Linux (main frente al PR #81).

  python3 comparar.py <dir_resultados> > resumen.md
"""
import json, os, sys

D = sys.argv[1]
runs = sorted(x for x in os.listdir(D) if os.path.isfile(os.path.join(D, x, 'banco', 'resumen.json')))
R = {r: json.load(open(os.path.join(D, r, 'banco', 'resumen.json'))) for r in runs}
TRAMOS = [('sucesivas_1ro_y_4to_6to', 'Sucesivas 1ro y 4to-6to'), ('simultaneas_oficial_4to_6to', 'Oficiales simultáneos'),
          ('simultaneas_borrador_4to_6to', 'Borradores simultáneos'), ('espera_de_turno', 'Espera de turno'),
          ('errores_dentro_del_turno', 'Errores dentro del turno'), ('muerte_de_un_worker', 'Muerte de un worker')]


def g(d, *ks):
    for k in ks:
        if not isinstance(d, dict) or k not in d:
            return '—'
        d = d[k]
    return d


print('# Memoria del Registro de Secundaria en Linux: main (3a5a96b) frente a PR #81 (a2bfb45)\n')
print('Contenedor con `--memory=512m --memory-swap=512m`, uvicorn con 2 workers, PostgreSQL sintético aparte. '
      'MiB. «actual» = `memory.current` del cgroup (lo que cuenta para el límite, incluye caché de archivos); '
      '«anon» = memoria de los procesos.\n')
print('| Ejecución | Reposo actual/anon | Pico actual | Pico anon | `memory.peak` | OOM kills | Workers nuevos | Contenedor | Registros no 200 |')
print('|---|---|---|---|---|---|---|---|---|')
for r, x in R.items():
    gl = x.get('global', {})
    no200 = gl.get('peticiones_registro_no_200') or []
    no200_txt = ', '.join('%s %s' % (n['ruta'].split('/')[4], n['estado']) for n in no200) or '0'
    print('| %s | %s / %s | %s | %s | %s | %s | %s | %s (OOMKilled=%s, reinicios=%s) | %s |' % (
        r, g(x, 'reposo', 'actual_MiB'), g(x, 'reposo', 'anon_MiB'), gl.get('pico_actual_MiB', '—'),
        gl.get('pico_anon_MiB', '—'), gl.get('memory_peak_cgroup_MiB', '—'), gl.get('oom_kill_total', '—'),
        len(gl.get('pids_de_worker_nuevos') or []), g(x, 'contenedor', 'Status'), g(x, 'contenedor', 'OOMKilled'),
        g(x, 'contenedor', 'RestartCount'), no200_txt))

for t, nombre in TRAMOS:
    print('\n## %s\n' % nombre)
    print('| Ejecución | Pico actual | Pico anon | Final anon | OOM kills | Sondas (n / máx s / >1 s / fallos) | Tiempos (s) y estados |')
    print('|---|---|---|---|---|---|---|')
    for r, x in R.items():
        tr = x.get(t)
        if not isinstance(tr, dict):
            print('| %s | — | — | — | — | — | (no llegó a ejecutarse) |' % r)
            continue
        s = tr.get('sondas')
        st = '%s / %s / %s / %s' % (s.get('n'), s.get('max_seg', '—'), s.get('mas_de_1s', '—'), s.get('fallos')) if s else '—'
        pet = []
        cola = [tr['peticiones']]
        while cola:
            v = cola.pop(0)
            if isinstance(v, list):
                cola[0:0] = v
            elif isinstance(v, dict) and 'ruta' in v:
                pet.append('%s:%s/%s' % (v['ruta'].split('/')[4].split('?')[0], v['estado'], v['seg']))
            elif isinstance(v, dict):
                cola[0:0] = list(v.values())
        print('| %s | %s | %s | %s | %s | %s | %s |' % (r, tr['pico_actual_MiB'], tr['pico_anon_MiB'], tr['final_anon_MiB'],
                                                    tr['oom_kill_en_tramo'], st, ' '.join(pet)))
