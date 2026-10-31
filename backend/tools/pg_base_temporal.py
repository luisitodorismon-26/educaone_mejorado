"""Base PostgreSQL TEMPORAL y exclusiva para una prueba.

Mismo mecanismo que `test_salidas_concurrencia_pg.py`, reutilizable:

  * `EO_PG_TEST_SERVER` es solo la conexión de ADMINISTRACIÓN a un servidor
    local (127.0.0.1/localhost). En esa base no se crea ni se borra nada.
  * `crear()` crea una base con nombre único (`<prefijo><hex>`) y la marca con
    un comentario que lleva un token aleatorio de esta ejecución. Antes de
    devolver su URL exige que la base conectada sea exactamente esa, con ese
    token y vacía.
  * `verificar_identidad(cn)` vuelve a comprobar nombre y token sobre cualquier
    conexión, antes de una operación destructiva (p. ej. un DROP COLUMN).
  * `comprobar_rechazo(url)` pasa la misma verificación por una base ordinaria
    (con datos) y comprueba que se rechaza y que queda idéntica: tablas,
    filas y contenido.
  * `eliminar()` borra ÚNICAMENTE la base temporal, tras volver a verificar su
    nombre y su token. Se registra con atexit.

Nunca se trabaja sobre una base recibida directamente por una variable de
entorno.
"""
import atexit
import os
import uuid
from urllib.parse import urlparse, urlunparse

import psycopg2
from psycopg2 import sql


class BaseNoTemporal(RuntimeError):
    pass


def _es_local(url):
    u = urlparse(url or '')
    return (url or '').startswith('postgresql') and u.hostname in ('127.0.0.1', 'localhost')


def huella_base(cn):
    """Tablas, filas y contenido (md5 de las filas ordenadas) de una base."""
    cur = cn.cursor()
    cur.execute("SELECT table_schema, table_name FROM information_schema.tables "
                "WHERE table_schema NOT IN ('pg_catalog', 'information_schema') "
                "AND table_type = 'BASE TABLE' ORDER BY 1, 2")
    tablas = cur.fetchall()
    out = []
    for esq, tab in tablas:
        ident = sql.SQL('{}.{}').format(sql.Identifier(esq), sql.Identifier(tab))
        cur.execute(sql.SQL('SELECT count(*), md5(coalesce(string_agg(t::text, %s ORDER BY t::text), %s)) '
                            'FROM {} AS t').format(ident), ['\n', ''])
        out.append(((esq, tab),) + tuple(cur.fetchone()))
    cur.execute("SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema NOT IN ('pg_catalog', 'information_schema') ORDER BY 1, 2")
    return out, cur.fetchall()


class BaseTemporal:
    def __init__(self, servidor=None, prefijo='eo_tmp_'):
        self.servidor = servidor or os.environ.get('EO_PG_TEST_SERVER', '')
        if not _es_local(self.servidor):
            raise SystemExit('EO_PG_TEST_SERVER debe ser la conexión de administración a un PostgreSQL local '
                             '(127.0.0.1/localhost).')
        assert prefijo.startswith('eo_tmp_'), prefijo
        self.prefijo = prefijo
        self.nombre = prefijo + uuid.uuid4().hex[:16]
        self.token = 'eo-test-temporal:' + uuid.uuid4().hex
        self.creada = False
        self.engines = []

    def _admin(self):
        cn = psycopg2.connect(self.servidor)
        cn.autocommit = True
        return cn

    def url(self):
        return urlunparse(urlparse(self.servidor)._replace(path='/' + self.nombre))

    def verificar_identidad(self, cn):
        """Aborta si `cn` no está conectada a la base temporal de ESTA ejecución."""
        cur = cn.cursor()
        cur.execute('SELECT current_database()')
        actual = cur.fetchone()[0]
        if actual != self.nombre or not actual.startswith(self.prefijo):
            raise BaseNoTemporal('la base conectada es %r, no la temporal %r' % (actual, self.nombre))
        cur.execute("SELECT shobj_description(oid, 'pg_database') FROM pg_database "
                    "WHERE datname = current_database()")
        if cur.fetchone()[0] != self.token:
            raise BaseNoTemporal('la base %r no lleva el token de esta ejecución' % actual)

    def verificar_vacia(self, cn):
        self.verificar_identidad(cn)
        cur = cn.cursor()
        cur.execute("SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema NOT IN ('pg_catalog', 'information_schema')")
        if cur.fetchone()[0]:
            raise BaseNoTemporal('la base %r no está vacía' % self.nombre)

    def comprobar_rechazo(self, url_ordinaria):
        """(rechazada, intacta, motivo) para una base ordinaria local."""
        if not _es_local(url_ordinaria):
            raise SystemExit('La base ordinaria de control debe ser local.')
        cn = psycopg2.connect(url_ordinaria)
        try:
            antes = huella_base(cn)
            try:
                self.verificar_vacia(cn)
                rechazada, motivo = False, ''
            except BaseNoTemporal as e:
                rechazada, motivo = True, str(e)
            despues = huella_base(cn)
        finally:
            cn.close()
        return rechazada, antes == despues, motivo, len(antes[0]), sum(t[1] for t in antes[0])

    def crear(self):
        cn = self._admin()
        try:
            cur = cn.cursor()
            cur.execute('SELECT 1 FROM pg_database WHERE datname = %s', [self.nombre])
            if cur.fetchone():
                raise BaseNoTemporal('ya existe una base %r: no se toca' % self.nombre)
            cur.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(self.nombre)))
            cur.execute(sql.SQL('COMMENT ON DATABASE {} IS {}').format(sql.Identifier(self.nombre),
                                                                       sql.Literal(self.token)))
        finally:
            cn.close()
        self.creada = True
        atexit.register(self.eliminar)
        cn = psycopg2.connect(self.url())
        try:
            self.verificar_vacia(cn)
        finally:
            cn.close()
        return self.url()

    def eliminar(self):
        """Borra SOLO la base temporal, tras comprobar de nuevo nombre y token."""
        if not self.creada:
            return
        for eng in self.engines:
            try:
                eng.dispose()
            except Exception:
                pass
        cn = self._admin()
        try:
            cur = cn.cursor()
            cur.execute("SELECT shobj_description(oid, 'pg_database') FROM pg_database WHERE datname = %s",
                        [self.nombre])
            fila = cur.fetchone()
            if fila is None:
                self.creada = False
                return
            if not self.nombre.startswith(self.prefijo) or fila[0] != self.token:
                print('NO se elimina %r: su marca no coincide.' % self.nombre)
                return
            cur.execute('SELECT pg_terminate_backend(pid) FROM pg_stat_activity '
                        'WHERE datname = %s AND pid <> pg_backend_pid()', [self.nombre])
            cur.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(self.nombre)))
            cur.execute('SELECT 1 FROM pg_database WHERE datname = %s', [self.nombre])
            print('    base temporal %s %s' % (self.nombre,
                                               'ELIMINADA' if cur.fetchone() is None else 'NO SE PUDO ELIMINAR'))
            self.creada = False
        finally:
            cn.close()
