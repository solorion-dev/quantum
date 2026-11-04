import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@dsect/ui/fonts.css'
import '@dsect/ui'
import './app.css'
import App from './App'

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>)
