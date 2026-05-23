import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { es } from './es';
import { en } from './en';

type Language = 'es' | 'en';
type Translations = typeof es;

interface LanguageContextType {
  language: Language;
  setLanguage: (lang: Language) => void;
  t: Translations;
}

const translations = { es, en };

const LanguageContext = createContext<LanguageContextType | undefined>(undefined);

export const LanguageProvider = ({ children }: { children: ReactNode }) => {
  const [language, setLanguageState] = useState<Language>(() => {
    const saved = localStorage.getItem('educa-one-language');
    return (saved as Language) || 'es';
  });

  const setLanguage = (lang: Language) => {
    setLanguageState(lang);
    localStorage.setItem('educa-one-language', lang);
  };

  useEffect(() => {
    document.documentElement.lang = language;
  }, [language]);

  const t = translations[language];

  return (
    <LanguageContext.Provider value={{ language, setLanguage, t }}>
      {children}
    </LanguageContext.Provider>
  );
};

export const useLanguage = () => {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error('useLanguage must be used within a LanguageProvider');
  }
  return context;
};

// Componente selector de idioma
export const LanguageSelector = () => {
  const { language, setLanguage } = useLanguage();
  
  return (
    <div className="flex items-center gap-1 bg-gray-100 rounded-lg p-1">
      <button
        onClick={() => setLanguage('es')}
        className={`px-2 py-1 text-xs font-medium rounded transition-colors ${
          language === 'es' 
            ? 'bg-white text-blue-600 shadow-sm' 
            : 'text-gray-500 hover:text-gray-700'
        }`}
        title="Español"
      >
        🇪🇸 ES
      </button>
      <button
        onClick={() => setLanguage('en')}
        className={`px-2 py-1 text-xs font-medium rounded transition-colors ${
          language === 'en' 
            ? 'bg-white text-blue-600 shadow-sm' 
            : 'text-gray-500 hover:text-gray-700'
        }`}
        title="English"
      >
        🇺🇸 EN
      </button>
    </div>
  );
};
