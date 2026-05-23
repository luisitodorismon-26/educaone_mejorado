import { AuthProvider } from './context/AuthContext'
import { LanguageProvider } from './i18n'
import { AppRouter } from './Router'

function App() {
  return (
    <LanguageProvider>
      <AuthProvider>
        <AppRouter />
      </AuthProvider>
    </LanguageProvider>
  )
}

export default App
