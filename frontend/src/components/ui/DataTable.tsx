import { useState, useMemo } from 'react';

interface Column<T> {
  key: keyof T | string;
  label: string;
  sortable?: boolean;
  render?: (item: T) => React.ReactNode;
  className?: string;
}

interface DataTableProps<T> {
  data: T[];
  columns: Column<T>[];
  searchable?: boolean;
  searchKeys?: (keyof T)[];
  pageSize?: number;
  exportable?: boolean;
  exportFilename?: string;
  onRowClick?: (item: T) => void;
  emptyMessage?: string;
  actions?: (item: T) => React.ReactNode;
}

export function DataTable<T extends { id: number | string }>({
  data,
  columns,
  searchable = true,
  searchKeys = [],
  pageSize = 15,
  exportable = true,
  exportFilename = 'datos',
  onRowClick,
  emptyMessage = 'No hay datos',
  actions
}: DataTableProps<T>) {
  const [search, setSearch] = useState('');
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');
  const [page, setPage] = useState(1);

  // Filtrar
  const filtered = useMemo(() => {
    if (!search) return data;
    const s = search.toLowerCase();
    return data.filter(item => {
      if (searchKeys.length > 0) {
        return searchKeys.some(key => 
          String(item[key] || '').toLowerCase().includes(s)
        );
      }
      return Object.values(item).some(val => 
        String(val || '').toLowerCase().includes(s)
      );
    });
  }, [data, search, searchKeys]);

  // Ordenar
  const sorted = useMemo(() => {
    if (!sortKey) return filtered;
    return [...filtered].sort((a, b) => {
      const aVal = (a as any)[sortKey];
      const bVal = (b as any)[sortKey];
      if (aVal === bVal) return 0;
      if (aVal === null || aVal === undefined) return 1;
      if (bVal === null || bVal === undefined) return -1;
      const cmp = aVal < bVal ? -1 : 1;
      return sortDir === 'asc' ? cmp : -cmp;
    });
  }, [filtered, sortKey, sortDir]);

  // Paginar
  const totalPages = Math.ceil(sorted.length / pageSize);
  const paginated = sorted.slice((page - 1) * pageSize, page * pageSize);

  // Handlers
  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
  };

  const handleSearch = (value: string) => {
    setSearch(value);
    setPage(1);
  };

  // Exportar a CSV
  const exportCSV = () => {
    const headers = columns.map(c => c.label).join(',');
    const rows = sorted.map(item => 
      columns.map(col => {
        const val = (item as any)[col.key];
        return `"${String(val || '').replace(/"/g, '""')}"`;
      }).join(',')
    );
    const csv = [headers, ...rows].join('\n');
    const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${exportFilename}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Exportar a Excel (formato simple)
  const exportExcel = () => {
    let html = '<table border="1"><thead><tr>';
    columns.forEach(c => html += `<th>${c.label}</th>`);
    html += '</tr></thead><tbody>';
    sorted.forEach(item => {
      html += '<tr>';
      columns.forEach(col => {
        const val = (item as any)[col.key];
        html += `<td>${val ?? ''}</td>`;
      });
      html += '</tr>';
    });
    html += '</tbody></table>';
    
    const blob = new Blob([html], { type: 'application/vnd.ms-excel' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${exportFilename}.xls`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex flex-col sm:flex-row gap-3 justify-between">
        {searchable && (
          <div className="relative flex-1 max-w-md">
            <input
              type="text"
              placeholder="Buscar..."
              value={search}
              onChange={e => handleSearch(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
            <span className="absolute left-3 top-2.5 text-gray-400">🔍</span>
          </div>
        )}
        
        {exportable && (
          <div className="flex gap-2">
            <button
              onClick={exportCSV}
              className="px-3 py-2 text-sm bg-green-50 text-green-700 border border-green-200 rounded-lg hover:bg-green-100 flex items-center gap-1"
            >
              📄 CSV
            </button>
            <button
              onClick={exportExcel}
              className="px-3 py-2 text-sm bg-emerald-50 text-emerald-700 border border-emerald-200 rounded-lg hover:bg-emerald-100 flex items-center gap-1"
            >
              📊 Excel
            </button>
          </div>
        )}
      </div>

      {/* Info */}
      <div className="text-sm text-gray-500">
        Mostrando {paginated.length} de {sorted.length} registros
        {search && ` (filtrado de ${data.length})`}
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50">
              <tr>
                {columns.map(col => (
                  <th
                    key={String(col.key)}
                    onClick={() => col.sortable !== false && handleSort(String(col.key))}
                    className={`px-4 py-3 text-left text-sm font-medium text-gray-600 ${
                      col.sortable !== false ? 'cursor-pointer hover:bg-gray-100 select-none' : ''
                    } ${col.className || ''}`}
                  >
                    <div className="flex items-center gap-1">
                      {col.label}
                      {col.sortable !== false && sortKey === col.key && (
                        <span className="text-blue-600">
                          {sortDir === 'asc' ? '↑' : '↓'}
                        </span>
                      )}
                    </div>
                  </th>
                ))}
                {actions && <th className="px-4 py-3 text-right text-sm font-medium text-gray-600">Acciones</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {paginated.map(item => (
                <tr
                  key={item.id}
                  onClick={() => onRowClick?.(item)}
                  className={`hover:bg-gray-50 ${onRowClick ? 'cursor-pointer' : ''}`}
                >
                  {columns.map(col => (
                    <td key={String(col.key)} className={`px-4 py-3 ${col.className || ''}`}>
                      {col.render ? col.render(item) : String((item as any)[col.key] ?? '-')}
                    </td>
                  ))}
                  {actions && (
                    <td className="px-4 py-3 text-right">
                      {actions(item)}
                    </td>
                  )}
                </tr>
              ))}
              {paginated.length === 0 && (
                <tr>
                  <td colSpan={columns.length + (actions ? 1 : 0)} className="px-4 py-12 text-center text-gray-500">
                    {emptyMessage}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="text-sm text-gray-500">
            Página {page} de {totalPages}
          </div>
          <div className="flex gap-1">
            <button
              onClick={() => setPage(1)}
              disabled={page === 1}
              className="px-3 py-1 border rounded-lg disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50"
            >
              ««
            </button>
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1}
              className="px-3 py-1 border rounded-lg disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50"
            >
              «
            </button>
            
            {/* Números de página */}
            {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
              let pageNum;
              if (totalPages <= 5) {
                pageNum = i + 1;
              } else if (page <= 3) {
                pageNum = i + 1;
              } else if (page >= totalPages - 2) {
                pageNum = totalPages - 4 + i;
              } else {
                pageNum = page - 2 + i;
              }
              return (
                <button
                  key={pageNum}
                  onClick={() => setPage(pageNum)}
                  className={`px-3 py-1 border rounded-lg ${
                    page === pageNum ? 'bg-blue-600 text-white border-blue-600' : 'hover:bg-gray-50'
                  }`}
                >
                  {pageNum}
                </button>
              );
            })}
            
            <button
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="px-3 py-1 border rounded-lg disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50"
            >
              »
            </button>
            <button
              onClick={() => setPage(totalPages)}
              disabled={page === totalPages}
              className="px-3 py-1 border rounded-lg disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50"
            >
              »»
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default DataTable;
