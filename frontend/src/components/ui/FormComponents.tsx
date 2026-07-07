import { forwardRef } from 'react';

// Input
interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  icon?: React.ReactNode;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, icon, className = '', ...props }, ref) => (
    <div className="w-full">
      {label && (
        <label className="block text-sm font-medium text-gray-700 mb-1">
          {label}
          {props.required && <span className="text-red-500 ml-1">*</span>}
        </label>
      )}
      <div className="relative">
        {icon && (
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">
            {icon}
          </span>
        )}
        <input
          ref={ref}
          className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors
            ${icon ? 'pl-10' : ''} 
            ${error ? 'border-red-500 focus:ring-red-500' : 'border-gray-300'}
            ${props.disabled ? 'bg-gray-100 cursor-not-allowed' : ''}
            ${className}`}
          {...props}
        />
      </div>
      {error && <p className="mt-1 text-sm text-red-500">{error}</p>}
    </div>
  )
);

// Select
interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  error?: string;
  options: { value: string | number; label: string; group?: string }[];
  placeholder?: string;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ label, error, options = [], placeholder, className = '', ...props }, ref) => {
    const hasGroups = options.some(o => o.group);
    const grouped = hasGroups ? options.reduce((acc, opt) => {
      const g = opt.group || '';
      if (!acc[g]) acc[g] = [];
      acc[g].push(opt);
      return acc;
    }, {} as Record<string, typeof options>) : null;

    // Defense-in-depth: si el `value` actual no matchea ningún `option`, el browser
    // mostraría el primer `<option>` como "seleccionado visualmente" pero el state
    // del componente padre queda con el valor original (típicamente 0). Eso causa
    // bugs sutiles donde el usuario "ve" un valor seleccionado pero el form no lo
    // tiene. Para evitarlo, mostramos un placeholder implícito con value="" cuando
    // el value actual no está entre las opciones.
    const currentValue = props.value;
    const valueExists = currentValue !== undefined && currentValue !== null
      && options.some(o => String(o.value) === String(currentValue));
    const needsImplicitPlaceholder = !placeholder && !valueExists;

    return (
      <div className="w-full">
        {label && (
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {label}
            {props.required && <span className="text-red-500 ml-1">*</span>}
          </label>
        )}
        <select
          ref={ref}
          className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors
            ${error ? 'border-red-500' : 'border-gray-300'}
            ${props.disabled ? 'bg-gray-100 cursor-not-allowed' : ''}
            ${className}`}
          {...props}
        >
          {placeholder && <option value="">{placeholder}</option>}
          {needsImplicitPlaceholder && <option value="">-- Seleccionar --</option>}
          {grouped ? Object.entries(grouped).map(([group, opts]) => (
            <optgroup key={group} label={group || 'Otros'}>
              {opts.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </optgroup>
          )) : options.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
        {error && <p className="mt-1 text-sm text-red-500">{error}</p>}
      </div>
    );
  }
);

// Textarea
interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ label, error, className = '', ...props }, ref) => (
    <div className="w-full">
      {label && (
        <label className="block text-sm font-medium text-gray-700 mb-1">
          {label}
          {props.required && <span className="text-red-500 ml-1">*</span>}
        </label>
      )}
      <textarea
        ref={ref}
        className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors resize-none
          ${error ? 'border-red-500' : 'border-gray-300'}
          ${props.disabled ? 'bg-gray-100 cursor-not-allowed' : ''}
          ${className}`}
        rows={4}
        {...props}
      />
      {error && <p className="mt-1 text-sm text-red-500">{error}</p>}
    </div>
  )
);

// Button
interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger' | 'success' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
  loading?: boolean;
  icon?: React.ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = 'primary', size = 'md', loading, icon, children, className = '', disabled, ...props }, ref) => {
    const variants = {
      primary: 'bg-blue-600 text-white hover:bg-blue-700 border-blue-600',
      secondary: 'bg-white text-gray-700 hover:bg-gray-50 border-gray-300',
      danger: 'bg-red-600 text-white hover:bg-red-700 border-red-600',
      success: 'bg-green-600 text-white hover:bg-green-700 border-green-600',
      ghost: 'bg-transparent text-gray-600 hover:bg-gray-100 border-transparent'
    };

    const sizes = {
      sm: 'px-3 py-1.5 text-sm',
      md: 'px-4 py-2',
      lg: 'px-6 py-3 text-lg'
    };

    return (
      <button
        ref={ref}
        disabled={disabled || loading}
        className={`inline-flex items-center justify-center gap-2 font-medium border rounded-lg transition-colors
          ${variants[variant]} ${sizes[size]}
          ${(disabled || loading) ? 'opacity-50 cursor-not-allowed' : ''}
          ${className}`}
        {...props}
      >
        {loading ? (
          <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
          </svg>
        ) : icon}
        {children}
      </button>
    );
  }
);

// Badge
interface BadgeProps {
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'info';
  children: React.ReactNode;
  className?: string;
}

export const Badge = ({ variant = 'default', children, className = '' }: BadgeProps) => {
  const variants = {
    default: 'bg-gray-100 text-gray-800',
    success: 'bg-green-100 text-green-800',
    warning: 'bg-yellow-100 text-yellow-800',
    danger: 'bg-red-100 text-red-800',
    info: 'bg-blue-100 text-blue-800'
  };

  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${variants[variant]} ${className}`}>
      {children}
    </span>
  );
};

// Card
interface CardProps {
  title?: string;
  subtitle?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  className?: string;
}

export const Card = ({ title, subtitle, children, footer, className = '' }: CardProps) => (
  <div className={`bg-white rounded-xl shadow-sm border border-gray-200 ${className}`}>
    {(title || subtitle) && (
      <div className="px-6 py-4 border-b border-gray-200">
        {title && <h3 className="text-lg font-semibold text-gray-900">{title}</h3>}
        {subtitle && <p className="text-sm text-gray-500 mt-1">{subtitle}</p>}
      </div>
    )}
    <div className="p-6">{children}</div>
    {footer && (
      <div className="px-6 py-4 border-t border-gray-200 bg-gray-50 rounded-b-xl">
        {footer}
      </div>
    )}
  </div>
);

// Alert
interface AlertProps {
  variant?: 'info' | 'success' | 'warning' | 'error';
  title?: string;
  children: React.ReactNode;
  onClose?: () => void;
  className?: string;
}

export const Alert = ({ variant = 'info', title, children, onClose, className = '' }: AlertProps) => {
  const variants = {
    info: { bg: 'bg-blue-50 border-blue-200', text: 'text-blue-800', icon: 'ℹ️' },
    success: { bg: 'bg-green-50 border-green-200', text: 'text-green-800', icon: '✅' },
    warning: { bg: 'bg-yellow-50 border-yellow-200', text: 'text-yellow-800', icon: '⚠️' },
    error: { bg: 'bg-red-50 border-red-200', text: 'text-red-800', icon: '❌' }
  };

  const v = variants[variant];

  return (
    <div className={`${v.bg} ${v.text} border rounded-lg p-4 ${className}`}>
      <div className="flex">
        <span className="mr-2">{v.icon}</span>
        <div className="flex-1">
          {title && <p className="font-medium">{title}</p>}
          <div className={title ? 'mt-1' : ''}>{children}</div>
        </div>
        {onClose && (
          <button onClick={onClose} className="ml-2 hover:opacity-70">✕</button>
        )}
      </div>
    </div>
  );
};

// Loading Spinner
export const Spinner = ({ size = 'md' }: { size?: 'sm' | 'md' | 'lg' }) => {
  const sizes = { sm: 'h-4 w-4', md: 'h-8 w-8', lg: 'h-12 w-12' };
  return (
    <div className="flex justify-center items-center">
      <div className={`${sizes[size]} animate-spin rounded-full border-2 border-gray-300 border-t-blue-600`} />
    </div>
  );
};

// Empty State
interface EmptyStateProps {
  icon?: string;
  title: string;
  description?: string;
  action?: React.ReactNode;
}

export const EmptyState = ({ icon = '📭', title, description, action }: EmptyStateProps) => (
  <div className="text-center py-12">
    <span className="text-5xl">{icon}</span>
    <h3 className="mt-4 text-lg font-medium text-gray-900">{title}</h3>
    {description && <p className="mt-2 text-gray-500">{description}</p>}
    {action && <div className="mt-4">{action}</div>}
  </div>
);
