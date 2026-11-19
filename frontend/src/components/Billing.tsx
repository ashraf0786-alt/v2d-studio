import { useEffect, useState } from 'react'
import { api } from '../api'
import type { PlanInfo, PlanOption, User } from '../types'
import { Check, Crown, Zap, Loader2, KeyRound, Copy, Trash2 } from 'lucide-react'

export default function Billing({ plan, user, onUpdated }: {
  plan: PlanInfo | null; user: User | null; onUpdated: () => void
}) {
  const [options, setOptions] = useState<PlanOption[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [msg, setMsg] = useState('')
  const [keys, setKeys] = useState<any[]>([])
  const [newKey, setNewKey] = useState('')
  const [keyName, setKeyName] = useState('my-app')

  function loadKeys() { api.apiKeys().then(setKeys).catch(() => setKeys([])) }
  useEffect(() => { api.plans().then(p => setOptions(p.plans)).catch(() => {}) }, [])
  useEffect(() => { if (plan?.api_access) loadKeys() }, [plan?.api_access])

  async function makeKey() {
    setBusy('key')
    try {
      const k = await api.createApiKey(keyName || 'my-app')
      setNewKey(k.key); loadKeys()
    } catch (e: any) { setMsg(e.message) } finally { setBusy(null) }
  }
  async function revokeKey(id: number) {
    await api.revokeApiKey(id); loadKeys()
  }

  async function choose(id: string) {
    setBusy(id); setMsg('')
    try {
      if (!plan?.billing_enabled) {
        await api.devPlan(id)
        setMsg(`Local plan switched to ${id}.`)
      } else {
        const res = await api.checkout(id)
        if (res.url) window.location.href = res.url
        else setMsg(res.message || 'No checkout URL returned.')
      }
      onUpdated()
    } catch (e: any) { setMsg(e.message) } finally { setBusy(null) }
  }

  async function portal() {
    setBusy('portal'); setMsg('')
    try {
      const res = await api.portal()
      window.location.href = res.url
    } catch (e: any) { setMsg(e.message) } finally { setBusy(null) }
  }

  return (
    <div className="page">
      <header className="page-head">
        <div><h1>Plans &amp; Billing</h1><p className="muted">Pick the plan that fits your workflow.</p></div>
      </header>

      {plan && (
        <div className="current-plan">
          <div>
            <span className="muted small">CURRENT PLAN</span>
            <h2>{plan.plan === 'owner' ? <><Crown size={20} className="gold" /> Owner — unlimited, always free</> : plan.label}</h2>
            <p className="muted small">
              {plan.plan === 'owner'
                ? plan.personal_mode
                    ? 'Personal mode — every feature is free and unlocked. No payments, no subscriptions.'
                    : 'All modes, no limits, no charges. Public users pay; you never do.'
                : `${plan.max_duration_seconds}s clips · ${plan.max_resolution}px · ${plan.modes.join(', ')}`}
            </p>
          </div>
          {plan.plan !== 'owner' && plan.billing_enabled && (
            <button className="btn ghost" onClick={portal} disabled={!!busy}>Manage subscription</button>
          )}
        </div>
      )}

      {msg && <div className="alert">{msg}</div>}
      {plan?.personal_mode && (
        <div className="alert info">Personal mode is active. Subscriptions and payments are disabled — everything is free for you.</div>
      )}
      {plan && !plan.billing_enabled && !plan.personal_mode && (
        <div className="alert info">Billing is disabled in this deployment — plan switching is local and free.</div>
      )}

      {!plan?.personal_mode && <div className="pricing-grid">
        {options.map(o => {
          const current = plan?.plan === o.id
          const isOwner = plan?.plan === 'owner'
          return (
            <div key={o.id} className={`price-card ${o.id === 'pro' ? 'featured' : ''}`}>
              {o.id === 'pro' && <div className="featured-tag"><Zap size={12} /> Most popular</div>}
              <h3>{o.label}</h3>
              <div className="price">${o.price_monthly}<small>/mo</small></div>
              <ul>
                <li><Check size={14} /> {o.max_duration_seconds}s max video</li>
                <li><Check size={14} /> {o.max_resolution}px output</li>
                <li><Check size={14} /> {o.modes.includes('scene') ? 'All 3 modes' : 'Parallax mode'}</li>
                <li><Check size={14} /> {o.watermark ? 'Watermarked' : 'No watermark'}</li>
                <li><Check size={14} /> {o.commercial ? 'Commercial license' : 'Personal use'}</li>
                {o.api_access && <li><Check size={14} /> API + batch access</li>}
              </ul>
              <button className={`btn full ${o.id === 'pro' ? 'primary' : 'ghost'}`}
                      disabled={!!busy || current || isOwner}
                      onClick={() => choose(o.id)}>
                {busy === o.id ? <Loader2 className="spin" size={15} /> : null}
                {isOwner ? 'Owner — full access' : current ? 'Current plan' : plan?.billing_enabled ? 'Subscribe' : 'Switch locally'}
              </button>
            </div>
          )
        })}
      </div>}

      {plan?.api_access && (
        <section className="panel api-panel">
          <div className="panel-title"><KeyRound size={17} /> API keys <small className="muted">Studio &amp; Owner</small></div>
          <p className="muted small">Use <code>X-API-Key</code> with <code>/api/v1/jobs</code> to convert videos programmatically.</p>
          <div className="api-key-create">
            <input value={keyName} onChange={e => setKeyName(e.target.value)} placeholder="Key name" />
            <button className="btn ghost small" onClick={makeKey} disabled={!!busy}>
              {busy === 'key' ? <Loader2 className="spin" size={14} /> : <KeyRound size={14} />} Create key
            </button>
          </div>
          {newKey && (
            <div className="alert info new-key">
              <code>{newKey}</code>
              <button className="icon-btn" title="Copy" onClick={() => navigator.clipboard.writeText(newKey)}><Copy size={15} /></button>
              <small>Shown once — copy it now.</small>
            </div>
          )}
          <div className="api-key-list">
            {keys.map(k => (
              <div key={k.id} className="api-key-row">
                <KeyRound size={14} /> <strong>{k.name}</strong>
                <code>{k.prefix}••••••••</code>
                <span className="muted small">created {new Date(k.created_at).toLocaleDateString()}</span>
                <button className="icon-btn" title="Revoke" onClick={() => revokeKey(k.id)}><Trash2 size={14} /></button>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
