import { useEffect, useRef, useState } from 'react'
import { api, wsUrl } from '../api'
import type { Job, Mode, PlanInfo, User } from '../types'
import { UploadCloud, Play, Loader2, Image as ImageIcon, PersonStanding, Box, CheckCircle2, AlertCircle, Clock, Link2 } from 'lucide-react'
import AdSlot from './AdSlot'

const MODES: { id: Mode; title: string; desc: string; icon: typeof ImageIcon; minPlan: string }[] = [
  { id: 'parallax', title: '2.5D Parallax', desc: 'Depth-aware camera motion', icon: ImageIcon, minPlan: 'free' },
  { id: 'mocap', title: 'Avatar Mocap', desc: 'Track pose onto a character', icon: PersonStanding, minPlan: 'pro' },
  { id: 'scene', title: '3D Scene', desc: 'Depth-fused point cloud', icon: Box, minPlan: 'pro' },
]

export default function Studio({ user, plan, jobs, onJobsChange, onView }: {
  user: User | null; plan: PlanInfo | null; jobs: Job[]
  onJobsChange: () => void; onView: (j: Job) => void
}) {
  const [mode, setMode] = useState<Mode>('parallax')
  const [files, setFiles] = useState<File[]>([])
  const [url, setUrl] = useState('')
  const [demoSeconds, setDemoSeconds] = useState(8)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [active, setActive] = useState<Job | null>(null)
  const [live, setLive] = useState<{ progress: number; message: string; status: string } | null>(null)
  const socketRef = useRef<WebSocket | null>(null)
  const pollRef = useRef<number | null>(null)

  const unlocked = (m: Mode) => !plan || plan.modes.includes(m)

  function watchJob(id: string) {
    socketRef.current?.close()
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
    const ws = new WebSocket(wsUrl(id))
    socketRef.current = ws
    ws.onmessage = (e) => {
      try {
        const ev = JSON.parse(e.data)
        if (ev.error) return
        setLive({ progress: ev.progress, message: ev.message, status: ev.status })
        if (ev.status === 'completed' || ev.status === 'failed') {
          api.job(id).then(j => { setActive(j); onJobsChange(); setBusy(false) }).catch(() => setBusy(false))
          ws.close()
        }
      } catch { /* ignore */ }
    }
    // Polling fallback in case WebSocket is blocked by a proxy.
    const poll = setInterval(async () => {
      try {
        const j = await api.job(id)
        setActive(j)
        if (j.status === 'completed' || j.status === 'failed') {
          clearInterval(poll); pollRef.current = null; onJobsChange(); setBusy(false)
        }
      } catch { /* ignore */ }
    }, 1200)
    pollRef.current = poll
    ws.onclose = () => { /* polling continues */ }
  }

  useEffect(() => () => {
    socketRef.current?.close()
    if (pollRef.current) clearInterval(pollRef.current)
  }, [])

  async function submitUrl() {
    if (!url.trim()) { setError('Enter a video URL first.'); return }
    setError(''); setBusy(true); setLive({ progress: 1, message: 'Fetching URL…', status: 'queued' })
    try {
      const res = await api.importUrl(url.trim(), mode)
      setActive(null)
      watchJob(res.id)
    } catch (e: any) {
      setError(e.message); setBusy(false); setLive(null)
    }
  }

  async function submit(useDemo: boolean) {
    setError(''); setBusy(true); setLive({ progress: 1, message: 'Submitting…', status: 'queued' })
    try {
      const width = plan?.max_resolution || 720
      if (useDemo) {
        const res = await api.demo(mode, demoSeconds)
        setActive(null)
        watchJob(res.id)
        return
      }
      if (files.length > 1) {
        const res = await api.batch(files, mode, width)
        if (res.errors.length) setError(`Skipped ${res.errors.length} file(s): ${res.errors[0].error}`)
        if (res.created.length) {
          setActive(null)
          watchJob(res.created[0].id)
          onJobsChange()
        }
        setBusy(false)
        return
      }
      const res = await api.upload(files[0], mode, width)
      setActive(null)
      watchJob(res.id)
    } catch (e: any) {
      setError(e.message); setBusy(false); setLive(null)
    }
  }

  const maxSeconds = plan && plan.max_duration_seconds < 1000 ? plan.max_duration_seconds : 20

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Studio</h1>
          <p className="muted">Upload a clip, choose a mode, and let the pipeline do the rest.</p>
        </div>
        {plan && <div className="head-plan"><span className={`tag ${plan.plan}`}>{plan.label}</span>
          <span className="muted small"><Clock size={13} /> {maxSeconds >= 1000 ? 'Unlimited' : `${maxSeconds}s max`} · {plan.max_resolution}px</span>
        </div>}
      </header>

      <div className="studio-grid">
        <div className="studio-main">
          <section className="panel">
            <div className="panel-title"><span className="step">1</span> Choose a mode</div>
            <div className="mode-grid">
              {MODES.map(m => {
                const allowed = unlocked(m.id)
                return (
                  <button key={m.id} className={`mode-card ${mode === m.id ? 'selected' : ''} ${!allowed ? 'locked' : ''}`}
                          onClick={() => allowed ? setMode(m.id) : setError(`${m.title} is available on Pro and above.`)}>
                    <m.icon size={20} />
                    <strong>{m.title}</strong>
                    <small>{m.desc}</small>
                    {!allowed && <span className="lock-label">PRO</span>}
                  </button>
                )
              })}
            </div>
          </section>

          <section className="panel">
            <div className="panel-title"><span className="step">2</span> Add your video</div>
            <label className={`dropzone ${files.length ? 'has-file' : ''}`}
                   onDragOver={e => e.preventDefault()}
                   onDrop={e => { e.preventDefault(); setFiles(Array.from(e.dataTransfer.files)) }}>
              <input type="file" accept="video/*" multiple onChange={e => setFiles(Array.from(e.target.files || []))} />
              <UploadCloud size={28} />
              <strong>{files.length ? `${files.length} file${files.length > 1 ? 's' : ''} selected: ${files[0].name}` : 'Drop video(s) here or click to browse'}</strong>
              <small>{files.length
                ? `${(files.reduce((n, f) => n + f.size, 0) / 1024 / 1024).toFixed(1)} MB total · batch mode`
                : `MP4, MOV, WebM · up to ${maxSeconds}s on your plan`}</small>
            </label>

            <div className="url-row">
              <div className="url-input-wrap">
                <Link2 size={16} />
                <input value={url} onChange={e => setUrl(e.target.value)}
                       placeholder="Paste any video URL — direct link, Drive/Dropbox, YouTube, TikTok…"
                       onKeyDown={e => { if (e.key === 'Enter') submitUrl() }} />
              </div>
              <button className="btn ghost small" disabled={busy} onClick={submitUrl}><Link2 size={14} /> Import URL</button>
            </div>
            <p className="hint">Direct files, signed links, cloud shares and video platforms are supported. Large files are fetched with byte-range requests.</p>

            <div className="demo-row">
              <span className="muted small">No video handy?</span>
              <label className="demo-seconds">Demo length
                <input type="number" min={3} max={maxSeconds} value={demoSeconds}
                       onChange={e => setDemoSeconds(Math.max(3, Math.min(maxSeconds, +e.target.value)))} />s
              </label>
              <button className="btn ghost small" disabled={busy} onClick={() => { setFiles([]); submit(true) }}>
                {busy ? <Loader2 className="spin" size={14} /> : <Play size={14} />} {busy ? 'Generating…' : 'Generate sample'}
              </button>
            </div>

            {error && <div className="alert error">{error}</div>}
            <button className="btn primary full" disabled={busy || files.length === 0}
                    onClick={() => submit(false)}>
              {busy ? <Loader2 className="spin" size={16} /> : <UploadCloud size={16} />}
              {busy ? 'Processing…' : files.length > 1 ? `Batch convert ${files.length} videos` : `Convert to ${MODES.find(m => m.id === mode)?.title}`}
            </button>
            <p className="hint">Select multiple files for batch conversion (Studio &amp; Owner). Or use “Generate sample” to try instantly.</p>
          </section>
        </div>

        <aside className="studio-side">
          <section className="panel progress-panel">
            <div className="panel-title">Job progress</div>
            {active || live ? (
              <>
                <div className="progress-ring" style={{ '--p': `${live?.progress ?? active?.progress ?? 0}%` } as React.CSSProperties}>
                  <div><strong>{live?.progress ?? active?.progress ?? 0}%</strong></div>
                </div>
                <div className="progress-status">
                  {(active?.status === 'failed' || live?.status === 'failed')
                    ? <AlertCircle size={16} className="text-red" /> : <CheckCircle2 size={16} className="text-green" />}
                  {active?.error || live?.message || 'Working…'}
                </div>
                {active?.status === 'completed' && (
                  <button className="btn primary full" onClick={() => onView(active)}>Open result</button>
                )}
              </>
            ) : (
              <div className="empty-mini">
                <Play size={26} />
                <p className="muted">Your conversion progress will appear here.</p>
              </div>
            )}
          </section>

          <section className="panel">
            <div className="panel-title">Recent conversions</div>
            {jobs.length === 0 ? <p className="muted small">No jobs yet.</p> : (
              <div className="recent-list">
                {jobs.slice(0, 5).map(j => (
                  <button key={j.id} className="recent-item" onClick={() => onView(j)}>
                    <span className={`status-dot ${j.status}`} />
                    <span className="recent-name">{j.input_filename}</span>
                    <span className="muted small">{j.mode}</span>
                  </button>
                ))}
              </div>
            )}
          </section>

          <AdSlot slot="studio-side" compact />
        </aside>
      </div>
    </div>
  )
}
