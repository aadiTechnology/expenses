import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { CssBaseline, ThemeProvider, createTheme } from '@mui/material'
import App from './App'

const theme = createTheme({
  palette: { primary: { main: '#3949ab' }, secondary: { main: '#00695c' }, background: { default: '#f5f6fa' },
    // darker warning/info so text and chips meet WCAG AA contrast
    warning: { main: '#b45309' }, info: { main: '#0b5cad' } },
  shape: { borderRadius: 10 },
  typography: { fontFamily: '"Segoe UI", Roboto, system-ui, sans-serif', button: { textTransform: 'none', fontWeight: 600 } },
  components: { MuiButton: { defaultProps: { disableElevation: true } }, MuiTextField: { defaultProps: { size: 'small' } } },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ThemeProvider>
  </StrictMode>,
)
