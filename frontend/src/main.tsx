import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

// When the page is not visible the browser pauses animation. Show final states instead, so
// nothing important can be left mid-fade (a background tab, a throttled projector machine).
const still = () => document.documentElement.classList.toggle('still', document.visibilityState !== 'visible')
document.addEventListener('visibilitychange', still)
still()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
