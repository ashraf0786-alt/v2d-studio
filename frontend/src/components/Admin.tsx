import { useEffect, useState } from 'react'
import { api } from '../api'
import { Users, Activity, Clock, Loader2 } from 'lucide-react'

export default function Admin() {
  const [users, setUsers] = useState<any[]>([])
  const [stats, setStats] = useState<any>(null)
  const [busy, setBusy] = useState<number | null>(null)

  function load() {
    api.adminUsers().then(setUsers).catch(() => {})
    api.adminStats().then(setStats).catch(() => {})
  }
  useEffect(load, [])

  async function update(id: number, patch: Record<string, any>) {
    setBusy(id)
    try { await api.adminUpdateUser(id, patch); load() } finally { setBusy(null) }
  }

  return (
    <div className="page">
      <header className="page-head">
        <div><h1>Admin</h1><p className="muted">Owner-only controls and platform stats.</p></div>
      </header>

      <div className="stat-grid">
        <div className="stat-card"><Users size={20} /><div><strong>{stats?.users ?? '—'}</strong><span>Users</span></div></div>
        <div className="stat-card"><Activity size={20} /><div><strong>{stats?.jobs ?? '—'}</strong><span>Jobs</span></div></div>
        <div className="stat-card"><Clock size={20} /><div><strong>{stats?.processed_minutes ?? '—'}</strong><span>Minutes processed</span></div></div>
      </div>

      <section className="panel">
        <div className="panel-title">Users</div>
        <div className="table-wrap">
          <table className="user-table">
            <thead><tr><th>Email</th><th>Plan</th><th>Owner</th><th>Active</th><th></th></tr></thead>
            <tbody>
              {users.map(u => (
                <tr key={u.id}>
                  <td>{u.email}</td>
                  <td>
                    <select value={u.plan} disabled={busy === u.id}
                            onChange={e => update(u.id, { plan: e.target.value })}>
                      <option value="free">free</option><option value="pro">pro</option><option value="studio">studio</option>
                    </select>
                  </td>
                  <td><input type="checkbox" checked={u.is_owner} disabled={busy === u.id}
                             onChange={e => update(u.id, { is_owner: e.target.checked })} /></td>
                  <td><input type="checkbox" checked={u.active} disabled={busy === u.id}
                             onChange={e => update(u.id, { is_active: e.target.checked })} /></td>
                  <td>{busy === u.id ? <Loader2 className="spin" size={14} /> : null}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
