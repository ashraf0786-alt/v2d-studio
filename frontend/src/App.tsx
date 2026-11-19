import { useCallback, useEffect, useState } from 'react'
import { api, clearToken, getToken } from './api'
import type { Job, PlanInfo, User } from './types'
import AuthPage from './components/AuthPage'
import Studio from './components/Studio'
import Billing from './components/Billing'
import Admin from './components/Admin'
import ResultViewer from './components/ResultViewer'
import { Boxes, Clapperboard, Layers, CreditCard, Shield, LogOut, Zap } from 'lucide-react'

type Page = 'studio' | 'library' | 'billing' | 'admin'

export default function App() {
  const [token, setTokenState] = useState(getToken())
  const [user, setUser] = useState<User | null>(null)
  const [plan, setPlan] = useState<PlanInfo | null>(null)
  const [page, setPage] = useState<Page>('studio')
  const [jobs, setJobs] = useState<Job[]>([])
  const [viewing, setViewing] = useState<Job | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    if (!getToken()) return
    try {
      const [me, plans, jobList] = await Promise.all([api.me(), api.plans(), api.jobs()])
      setUser(me)
      setPlan(plans.current)
      setJobs(jobList)
      setError('')
    } catch (e: any) {
      if (e.message.includes('Unauthorized') || e.message.includes('token')) {
        clearToken()
        setTokenState('')
        setUser(null)
      } else {
        setError(e.message)
      }
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { if (token) refresh() }, [token, refresh])

  // Keep the selected job in sync with fresh job data.
  useEffect(() => {
    if (viewing) {
      const fresh = jobs.find(j => j.id === viewing.id)
      if (fresh && fresh.result !== viewing.result) setViewing(fresh)
    }
  }, [jobs])

  function logout() {
    clearToken()
    setTokenState('')
    setUser(null)
    setJobs([])
    setPage('studio')
  }

  function onAuth() {
    setTokenState(getToken())
    setLoading(true)
    refresh()
  }

  if (!token) return <AuthPage onAuth={onAuth} />

  if (loading) {
    return <div className="boot"><div className="spinner" /><p>Loading your studio…</p></div>
  }

  const nav: { id: Page; label: string; icon: typeof Boxes }[] = [
    { id: 'studio', label: 'Studio', icon: Clapperboard },
    { id: 'library', label: 'Library', icon: Layers },
    { id: 'billing', label: 'Plans & Billing', icon: CreditCard },
    ...(user?.is_owner ? [{ id: 'admin' as Page, label: 'Admin', icon: Shield }] : []),
  ]

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark"><Boxes size={20} /></span> V2D Studio</div>
        <nav>
          {nav.map(item => (
            <button key={item.id} className={page === item.id ? 'nav-item active' : 'nav-item'}
                    onClick={() => setPage(item.id)}>
              <item.icon size={17} /> {item.label}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          {plan && (
            <div className="plan-chip">
              <Zap size={14} />
              <span>{plan.label}</span>
              <small>{plan.max_duration_seconds >= 1000 ? 'Unlimited' : `${plan.max_duration_seconds}s max`}</small>
            </div>
          )}
          {user && (
            <div className="user-row">
              <div className="avatar">{user.full_name.slice(0, 1).toUpperCase()}</div>
              <div className="user-meta"><strong>{user.full_name}</strong><small>{user.email}</small></div>
              <button className="icon-btn" title="Sign out" onClick={logout}><LogOut size={16} /></button>
            </div>
          )}
        </div>
      </aside>

      <main className="main">
        {error && <div className="alert error">{error}</div>}
        {page === 'studio' && (
          <Studio user={user} plan={plan} jobs={jobs} onJobsChange={refresh} onView={setViewing} />
        )}
        {page === 'library' && (
          <Library jobs={jobs} onView={setViewing} onRefresh={refresh} />
        )}
        {page === 'billing' && <Billing plan={plan} user={user} onUpdated={refresh} />}
        {page === 'admin' && user?.is_owner && <Admin />}
      </main>

      {viewing && <ResultViewer job={viewing} onClose={() => setViewing(null)} />}
    </div>
  )
}

function Library({ jobs, onView, onRefresh }: {
  jobs: Job[]; onView: (j: Job) => void; onRefresh: () => void
}) {
  return (
    <div className="page">
      <header className="page-head">
        <div><h1>Library</h1><p className="muted">All your conversions in one place.</p></div>
        <button className="btn ghost" onClick={onRefresh}>Refresh</button>
      </header>
      {jobs.length === 0 ? (
        <div className="empty"><Layers size={34} /><h3>Nothing here yet</h3><p className="muted">Head to Studio to create your first conversion.</p></div>
      ) : (
        <div className="card-grid">
          {jobs.map(j => (
            <button key={j.id} className="job-card" onClick={() => onView(j)}>
              <div className={`mode-badge ${j.mode}`}>{j.mode}</div>
              <div className="job-card-title">{j.input_filename}</div>
              <div className="muted small">{new Date(j.created_at).toLocaleString()} · {j.duration_seconds}s</div>
              <div className="job-progress"><span style={{ width: `${j.progress}%` }} /></div>
              <div className="job-card-foot">
                <span className={`status ${j.status}`}>{j.status}</span>
                <span className="muted small">{j.progress}%</span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
