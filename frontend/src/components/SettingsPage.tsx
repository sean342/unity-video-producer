import { useEffect, useState } from 'react'

const API_BASE = import.meta.env.VITE_API_URL || ''

type CredentialStatus = {
  provider: string
  label: string
  configured: boolean
  storage: string
  updated_at: string | null
}

const providerHelp: Record<string, string> = {
  openai: 'Used for scripts, Unity images, keyframes, and graphics.',
  elevenlabs: 'Used for Unity voiceover and timestamp alignment.',
  fal: 'Used for fal CDN uploads and Kling Avatar video generation.',
  gemini: 'Legacy provider; retained for compatibility with older workflows.',
}

export default function SettingsPage() {
  const [unlocked, setUnlocked] = useState(false)
  const [password, setPassword] = useState('')
  const [authError, setAuthError] = useState('')
  const [statuses, setStatuses] = useState<CredentialStatus[]>([])
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState<string | null>(null)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const loadStatuses = async () => {
    const response = await fetch(`${API_BASE}/settings/credentials`, { credentials: 'same-origin' })
    if (response.ok) {
      setStatuses(await response.json())
      setUnlocked(true)
    } else if (response.status === 401) {
      setUnlocked(false)
    }
  }

  useEffect(() => { void loadStatuses() }, [])

  const unlock = async (event: React.FormEvent) => {
    event.preventDefault()
    setAuthError('')
    const response = await fetch(`${API_BASE}/settings/session`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    })
    if (!response.ok) {
      setAuthError('That password cannot unlock provider settings.')
      return
    }
    setPassword('')
    await loadStatuses()
  }

  const save = async (provider: string) => {
    const apiKey = (drafts[provider] || '').trim()
    if (!apiKey) {
      setMessage({ type: 'error', text: `Enter the ${provider} key before saving.` })
      return
    }
    setSaving(provider)
    setMessage(null)
    try {
      const response = await fetch(`${API_BASE}/settings/credentials/${provider}`, {
        method: 'PUT',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: apiKey }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data.detail || 'The provider rejected this key.')
      setDrafts(previous => ({ ...previous, [provider]: '' }))
      setMessage({ type: 'success', text: `${data.label} key validated and encrypted.` })
      await loadStatuses()
    } catch (error) {
      setMessage({ type: 'error', text: error instanceof Error ? error.message : 'Could not save this key.' })
    } finally {
      setSaving(null)
    }
  }

  if (!unlocked) {
    return (
      <section className="max-w-xl mx-auto">
        <div className="card border border-unified-gold/30 shadow-[0_0_44px_rgba(250,166,35,0.08)]">
          <p className="text-xs tracking-[0.2em] uppercase text-unified-gold font-semibold mb-3">Protected control</p>
          <h2 className="text-2xl font-bold text-white">Provider settings</h2>
          <p className="text-sm text-gray-400 mt-2">Unlock this panel to rotate server-side provider credentials. Keys are never displayed after they are saved.</p>
          <form onSubmit={unlock} className="mt-6 space-y-4">
            <label className="block text-sm font-medium text-gray-300">Team password
              <input type="password" value={password} onChange={event => setPassword(event.target.value)} className="input-field mt-2" autoFocus />
            </label>
            {authError && <p className="text-sm text-red-400">{authError}</p>}
            <button type="submit" className="btn-primary w-full">Unlock provider settings</button>
          </form>
        </div>
      </section>
    )
  }

  return (
    <section className="max-w-4xl mx-auto space-y-6">
      <header className="card border border-unified-gold/25 bg-gradient-to-br from-gray-900 via-gray-900 to-unified-gold/5">
        <p className="text-xs tracking-[0.2em] uppercase text-unified-gold font-semibold">Provider vault</p>
        <h2 className="text-2xl font-bold text-white mt-2">API credentials</h2>
        <p className="text-sm text-gray-400 mt-2 max-w-2xl">Each key is validated before it is stored, encrypted at rest on the server, and never sent back to this browser. Leave a field blank to keep the current key unchanged.</p>
      </header>

      {message && (
        <div className={`rounded-xl px-4 py-3 text-sm border ${message.type === 'success' ? 'bg-green-950/40 border-green-600/40 text-green-300' : 'bg-red-950/40 border-red-600/40 text-red-300'}`}>
          {message.text}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {statuses.map(status => (
          <article key={status.provider} className="card border border-gray-800 hover:border-gray-700 transition-colors">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="font-semibold text-white">{status.label}</h3>
                <p className="text-xs text-gray-400 mt-1 min-h-8">{providerHelp[status.provider]}</p>
              </div>
              <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${status.configured ? 'bg-green-500/15 text-green-300 border border-green-400/20' : 'bg-gray-700 text-gray-300 border border-gray-600'}`}>
                {status.configured ? 'Configured' : 'Not set'}
              </span>
            </div>
            <label className="block mt-5 text-xs font-medium uppercase tracking-wide text-gray-500">Replace key
              <input
                type="password"
                autoComplete="new-password"
                value={drafts[status.provider] || ''}
                onChange={event => setDrafts(previous => ({ ...previous, [status.provider]: event.target.value }))}
                placeholder="Paste a replacement key"
                className="input-field mt-2 text-sm"
              />
            </label>
            <div className="mt-4 flex items-center justify-between gap-3">
              <p className="text-xs text-gray-500">{status.configured ? `Stored ${status.storage}` : 'No stored key'}</p>
              <button
                onClick={() => void save(status.provider)}
                disabled={saving === status.provider}
                className="px-3 py-2 rounded-lg text-sm font-semibold bg-unified-red hover:bg-red-700 disabled:opacity-50 text-white transition-colors"
              >
                {saving === status.provider ? 'Validating…' : 'Save & validate'}
              </button>
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}
