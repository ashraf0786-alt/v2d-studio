import { useState } from 'react'
import { api, setToken } from '../api'
import { Boxes, Sparkles, ArrowRight, Loader2 } from 'lucide-react'

export default function AuthPage({ onAuth }: { onAuth: () => void }) {
  const [mode, setMode] = useState<'login' | 'register'>('register')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      const res = mode === 'register'
        ? await api.register(email, password, name)
        : await api.login(email, password)
      setToken(res.access_token)
      onAuth()
    } catch (err: any) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-hero">
        <div className="brand"><span className="brand-mark"><Boxes size={22} /></span> V2D Studio</div>
        <div className="auth-hero-copy">
          <div className="pill"><Sparkles size={13} /> Video → 3D, in one click</div>
          <h1>Turn ordinary video into<span className="gradient"> dimensional animation.</span></h1>
          <p>Depth-aware parallax, body motion capture, and 3D scene reconstruction — all from a single clip. No GPU required to get started.</p>
          <ul className="hero-list">
            <li><span>01</span> 2.5D parallax from estimated depth &amp; camera motion</li>
            <li><span>02</span> Pose tracking retargeted to a rigged character</li>
            <li><span>03</span> Depth-fused point clouds you can orbit</li>
          </ul>
        </div>
        <div className="auth-foot">Free tier · 10s clips · Upgrade any time</div>
      </div>

      <div className="auth-form-side">
        <form className="auth-card" onSubmit={submit}>
          <h2>{mode === 'register' ? 'Create your account' : 'Welcome back'}</h2>
          <p className="muted">
            {mode === 'register' ? 'Start converting in seconds.' : 'Sign in to continue your projects.'}
          </p>

          {mode === 'register' && (
            <label>Display name
              <input value={name} onChange={e => setName(e.target.value)} placeholder="Your name" />
            </label>
          )}
          <label>Email address
            <input type="email" required value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" />
          </label>
          <label>Password
            <input type="password" required minLength={8} value={password} onChange={e => setPassword(e.target.value)} placeholder="At least 8 characters" />
          </label>

          {error && <div className="alert error">{error}</div>}

          <button className="btn primary full" disabled={busy}>
            {busy ? <Loader2 className="spin" size={16} /> : null}
            {mode === 'register' ? 'Create account' : 'Sign in'}
            {!busy && <ArrowRight size={16} />}
          </button>

          <div className="auth-switch">
            {mode === 'register' ? 'Already have an account?' : 'New here?'}
            <button type="button" onClick={() => { setMode(mode === 'register' ? 'login' : 'register'); setError('') }}>
              {mode === 'register' ? 'Sign in' : 'Create one'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
