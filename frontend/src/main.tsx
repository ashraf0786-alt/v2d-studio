import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './styles.css'

const adsenseId = import.meta.env.VITE_ADSENSE_ID as string | undefined
if (adsenseId) {
  const script = document.createElement('script')
  script.src = `https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=${adsenseId}`
  script.async = true
  script.crossOrigin = 'anonymous'
  document.head.appendChild(script)
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
