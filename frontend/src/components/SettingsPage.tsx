import { useEffect, useRef, useState } from 'react'

const API_BASE = import.meta.env.VITE_API_URL || ''

type CredentialStatus = {
  provider: string
  label: string
  configured: boolean
  storage: string
  updated_at: string | null
}

type MediaAsset = {
  id: string
  name: string
  media_type: 'image' | 'video' | 'audio'
  mime_type: string
  duration_seconds: number | null
  has_audio: boolean
  created_at: string
  url: string
}

type MediaAssignment = {
  slot: 'intro' | 'outro'
  output_ratio: string
  updated_at: string
  scene_asset_id: string
  scene_name: string
  scene_type: 'image' | 'video'
  scene_duration_seconds: number | null
  scene_has_audio: boolean
  audio_asset_id: string | null
  audio_name: string | null
  audio_duration_seconds: number | null
}

const providerHelp: Record<string, string> = {
  openai: 'Used for scripts, Unity images, keyframes, and graphics.',
  elevenlabs: 'Used for Unity voiceover and timestamp alignment.',
  fal: 'Used for fal CDN uploads and Kling Avatar video generation.',
}

const ratioOptions = [
  { value: 'all', label: 'All formats' },
  { value: '1:1', label: 'Square (1:1)' },
  { value: '4:5', label: 'Portrait (4:5)' },
  { value: '9:16', label: 'Vertical (9:16)' },
  { value: '16:9', label: 'Landscape (16:9)' },
]

const formatSeconds = (seconds: number | null) => seconds ? `${seconds.toFixed(seconds >= 10 ? 0 : 1)}s` : '—'

export default function SettingsPage() {
  const [unlocked, setUnlocked] = useState(false)
  const [password, setPassword] = useState('')
  const [authError, setAuthError] = useState('')
  const [statuses, setStatuses] = useState<CredentialStatus[]>([])
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState<string | null>(null)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [assets, setAssets] = useState<MediaAsset[]>([])
  const [assignments, setAssignments] = useState<MediaAssignment[]>([])
  const [uploading, setUploading] = useState(false)
  const [slot, setSlot] = useState<'intro' | 'outro'>('outro')
  const [ratio, setRatio] = useState('all')
  const [sceneAssetId, setSceneAssetId] = useState('')
  const [audioAssetId, setAudioAssetId] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const loadStatuses = async () => {
    const response = await fetch(`${API_BASE}/settings/credentials`, { credentials: 'same-origin' })
    if (response.ok) {
      setStatuses(await response.json())
      setUnlocked(true)
      return true
    }
    if (response.status === 401) setUnlocked(false)
    return false
  }

  const loadMedia = async () => {
    const [assetsResponse, assignmentsResponse] = await Promise.all([
      fetch(`${API_BASE}/settings/media/assets`, { credentials: 'same-origin' }),
      fetch(`${API_BASE}/settings/media/assignments`, { credentials: 'same-origin' }),
    ])
    if (assetsResponse.ok) setAssets(await assetsResponse.json())
    if (assignmentsResponse.ok) setAssignments(await assignmentsResponse.json())
  }

  const loadAll = async () => {
    if (await loadStatuses()) await loadMedia()
  }

  useEffect(() => { void loadAll() }, [])

  const unlock = async (event: React.FormEvent) => {
    event.preventDefault()
    setAuthError('')
    const response = await fetch(`${API_BASE}/settings/session`, {
      method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ password }),
    })
    if (!response.ok) {
      setAuthError('That password cannot unlock Settings.')
      return
    }
    setPassword('')
    await loadAll()
  }

  const saveCredential = async (provider: string) => {
    const apiKey = (drafts[provider] || '').trim()
    if (!apiKey) {
      setMessage({ type: 'error', text: `Enter the ${provider} key before saving.` })
      return
    }
    setSaving(provider)
    setMessage(null)
    try {
      const response = await fetch(`${API_BASE}/settings/credentials/${provider}`, {
        method: 'PUT', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ api_key: apiKey }),
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

  const uploadAsset = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    setUploading(true)
    setMessage(null)
    try {
      const form = new FormData()
      form.append('file', file)
      const response = await fetch(`${API_BASE}/settings/media/assets`, { method: 'POST', credentials: 'same-origin', body: form })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data.detail || 'The upload could not be saved.')
      setMessage({ type: 'success', text: `${data.name} is ready in the media library.` })
      await loadMedia()
    } catch (error) {
      setMessage({ type: 'error', text: error instanceof Error ? error.message : 'The upload failed.' })
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const saveAssignment = async () => {
    if (!sceneAssetId) {
      setMessage({ type: 'error', text: 'Choose an uploaded image or video scene first.' })
      return
    }
    setSaving('assignment')
    try {
      const response = await fetch(`${API_BASE}/settings/media/assignments/${slot}/${ratio}`, {
        method: 'PUT', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scene_asset_id: sceneAssetId, audio_asset_id: audioAssetId || null }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data.detail || 'Could not save this placement.')
      setMessage({ type: 'success', text: `Custom ${slot} saved for ${ratioOptions.find(option => option.value === ratio)?.label.toLowerCase()}.` })
      await loadMedia()
    } catch (error) {
      setMessage({ type: 'error', text: error instanceof Error ? error.message : 'Could not save this placement.' })
    } finally {
      setSaving(null)
    }
  }

  const clearAssignment = async (assignment: MediaAssignment) => {
    if (!window.confirm(`Remove the ${assignment.slot} assigned to ${assignment.output_ratio}?`)) return
    try {
      const response = await fetch(`${API_BASE}/settings/media/assignments/${assignment.slot}/${assignment.output_ratio}`, { method: 'DELETE', credentials: 'same-origin' })
      if (!response.ok) throw new Error('Could not remove this placement.')
      setMessage({ type: 'success', text: 'Custom media placement removed. The standard ending will be used unless another assignment applies.' })
      await loadMedia()
    } catch (error) {
      setMessage({ type: 'error', text: error instanceof Error ? error.message : 'Could not remove this placement.' })
    }
  }

  const deleteAsset = async (asset: MediaAsset) => {
    if (!window.confirm(`Delete “${asset.name}” from the media library? It will also remove any placement that uses it.`)) return
    try {
      const response = await fetch(`${API_BASE}/settings/media/assets/${asset.id}`, { method: 'DELETE', credentials: 'same-origin' })
      if (!response.ok) throw new Error('Could not delete this asset.')
      setMessage({ type: 'success', text: `${asset.name} was removed from the library.` })
      await loadMedia()
    } catch (error) {
      setMessage({ type: 'error', text: error instanceof Error ? error.message : 'Could not delete this asset.' })
    }
  }

  if (!unlocked) {
    return (
      <section className="max-w-xl mx-auto">
        <div className="card border border-unified-gold/30 shadow-[0_0_44px_rgba(250,166,35,0.08)]">
          <p className="text-xs tracking-[0.2em] uppercase text-unified-gold font-semibold mb-3">Protected control</p>
          <h2 className="text-2xl font-bold text-white">Settings</h2>
          <p className="text-sm text-gray-400 mt-2">Unlock this panel to manage provider keys and reusable video intro and outro media. Keys and uploaded media stay server-side.</p>
          <form onSubmit={unlock} className="mt-6 space-y-4">
            <label className="block text-sm font-medium text-gray-300">Team password
              <input type="password" value={password} onChange={event => setPassword(event.target.value)} className="input-field mt-2" autoFocus />
            </label>
            {authError && <p className="text-sm text-red-400">{authError}</p>}
            <button type="submit" className="btn-primary w-full">Unlock Settings</button>
          </form>
        </div>
      </section>
    )
  }

  const sceneAssets = assets.filter(asset => asset.media_type === 'image' || asset.media_type === 'video')
  const audioAssets = assets.filter(asset => asset.media_type === 'audio')

  return (
    <section className="max-w-5xl mx-auto space-y-6">
      <header className="card border border-unified-gold/25 bg-gradient-to-br from-gray-900 via-gray-900 to-unified-gold/5">
        <p className="text-xs tracking-[0.2em] uppercase text-unified-gold font-semibold">Protected control center</p>
        <h2 className="text-2xl font-bold text-white mt-2">Settings</h2>
        <p className="text-sm text-gray-400 mt-2 max-w-3xl">Provider credentials are encrypted at rest. Your media library stores reusable intro, outro, image, and audio assets on the server for future Unity videos.</p>
      </header>

      {message && (
        <div className={`rounded-xl px-4 py-3 text-sm border ${message.type === 'success' ? 'bg-green-950/40 border-green-600/40 text-green-300' : 'bg-red-950/40 border-red-600/40 text-red-300'}`}>{message.text}</div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {statuses.map(status => (
          <article key={status.provider} className="card border border-gray-800 hover:border-gray-700 transition-colors">
            <div className="flex items-start justify-between gap-4">
              <div><h3 className="font-semibold text-white">{status.label}</h3><p className="text-xs text-gray-400 mt-1 min-h-8">{providerHelp[status.provider]}</p></div>
              <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${status.configured ? 'bg-green-500/15 text-green-300 border border-green-400/20' : 'bg-gray-700 text-gray-300 border border-gray-600'}`}>{status.configured ? 'Configured' : 'Not set'}</span>
            </div>
            <label className="block mt-5 text-xs font-medium uppercase tracking-wide text-gray-500">Replace key
              <input type="password" autoComplete="new-password" value={drafts[status.provider] || ''} onChange={event => setDrafts(previous => ({ ...previous, [status.provider]: event.target.value }))} placeholder="Paste a replacement key" className="input-field mt-2 text-sm" />
            </label>
            <div className="mt-4 flex items-center justify-between gap-3"><p className="text-xs text-gray-500">{status.configured ? `Stored ${status.storage}` : 'No stored key'}</p><button onClick={() => void saveCredential(status.provider)} disabled={saving === status.provider} className="px-3 py-2 rounded-lg text-sm font-semibold bg-unified-red hover:bg-red-700 disabled:opacity-50 text-white transition-colors">{saving === status.provider ? 'Validating…' : 'Save & validate'}</button></div>
          </article>
        ))}
      </div>

      <section className="card border border-unified-gold/20 bg-gradient-to-br from-gray-900 to-gray-900/60">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
          <div><p className="text-xs tracking-[0.18em] uppercase text-unified-gold font-semibold">Video bookends</p><h2 className="text-xl font-bold text-white mt-2">Intro & outro media library</h2><p className="text-sm text-gray-400 mt-2 max-w-2xl">Upload a branded video or image scene, then assign it to an intro or outro for a specific social ratio or every format. For image scenes, attached audio sets the scene duration; without audio, the scene runs for five seconds.</p></div>
          <button onClick={() => fileInputRef.current?.click()} disabled={uploading} className="btn-primary shrink-0">{uploading ? 'Uploading…' : 'Upload media'}</button>
          <input ref={fileInputRef} onChange={uploadAsset} type="file" accept=".jpg,.jpeg,.png,.webp,.mp4,.mov,.webm,.mp3,.wav,.m4a,.aac,.ogg" className="hidden" />
        </div>
        <p className="text-xs text-gray-500 mt-4">Accepted: JPG, PNG, WebP, MP4, MOV, WebM, MP3, WAV, M4A, AAC, or OGG. Maximum upload size: 100 MB.</p>
      </section>

      <section className="grid grid-cols-1 lg:grid-cols-[1.1fr_0.9fr] gap-6">
        <div className="card border border-gray-800">
          <p className="text-xs tracking-[0.18em] uppercase text-unified-gold font-semibold">Library</p>
          <h3 className="font-semibold text-white mt-2">Uploaded scenes and audio</h3>
          {assets.length === 0 ? <div className="mt-5 rounded-xl border border-dashed border-gray-700 px-5 py-10 text-center text-sm text-gray-500">Upload a branded video, image, or audio file to start building reusable video bookends.</div> : <div className="mt-5 grid grid-cols-1 sm:grid-cols-2 gap-3 max-h-[610px] overflow-y-auto pr-1">{assets.map(asset => (
            <article key={asset.id} className="rounded-xl border border-gray-800 bg-gray-950/40 p-3">
              <div className="min-h-40 rounded-lg overflow-hidden bg-black/60 flex items-center justify-center p-2">{asset.media_type === 'image' && <img src={`${API_BASE}${asset.url}`} alt={asset.name} className="max-h-64 max-w-full w-auto h-auto object-contain rounded-md" />}{asset.media_type === 'video' && <video src={`${API_BASE}${asset.url}`} className="max-h-64 max-w-full w-auto h-auto object-contain rounded-md" controls muted playsInline />}{asset.media_type === 'audio' && <div className="w-full px-3"><p className="text-3xl text-unified-gold text-center mb-2">♪</p><audio src={`${API_BASE}${asset.url}`} controls className="w-full" /></div>}</div>
              <div className="mt-3 flex gap-2 justify-between"><div className="min-w-0"><p className="text-sm font-medium text-white truncate" title={asset.name}>{asset.name}</p><p className="text-xs text-gray-500 mt-1 capitalize">{asset.media_type} · {formatSeconds(asset.duration_seconds)}{asset.media_type === 'video' && asset.has_audio ? ' · embedded audio' : ''}</p></div><button onClick={() => void deleteAsset(asset)} className="text-xs text-red-300 hover:text-red-200 self-start">Delete</button></div>
            </article>
          ))}</div>}
        </div>

        <div className="card border border-unified-gold/20">
          <p className="text-xs tracking-[0.18em] uppercase text-unified-gold font-semibold">Placement</p>
          <h3 className="font-semibold text-white mt-2">Assign a reusable scene</h3>
          <div className="mt-5 space-y-4">
            <div className="grid grid-cols-2 gap-2">{(['intro', 'outro'] as const).map(value => <button key={value} onClick={() => setSlot(value)} className={`rounded-lg border px-3 py-2 text-sm font-semibold capitalize transition-colors ${slot === value ? 'border-unified-gold bg-unified-gold/10 text-unified-gold' : 'border-gray-700 text-gray-300 hover:border-gray-500'}`}>{value}</button>)}</div>
            <label className="block text-xs font-medium uppercase tracking-wide text-gray-500">Apply to
              <select value={ratio} onChange={event => setRatio(event.target.value)} className="input-field mt-2 text-sm">{ratioOptions.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select>
            </label>
            <label className="block text-xs font-medium uppercase tracking-wide text-gray-500">Image or video scene
              <select value={sceneAssetId} onChange={event => setSceneAssetId(event.target.value)} className="input-field mt-2 text-sm"><option value="">Choose a scene…</option>{sceneAssets.map(asset => <option key={asset.id} value={asset.id}>{asset.name} ({asset.media_type}{asset.duration_seconds ? ` · ${formatSeconds(asset.duration_seconds)}` : ''})</option>)}</select>
            </label>
            <label className="block text-xs font-medium uppercase tracking-wide text-gray-500">Optional background audio
              <select value={audioAssetId} onChange={event => setAudioAssetId(event.target.value)} className="input-field mt-2 text-sm"><option value="">No separate audio</option>{audioAssets.map(asset => <option key={asset.id} value={asset.id}>{asset.name} · {formatSeconds(asset.duration_seconds)}</option>)}</select>
            </label>
            <p className="rounded-lg bg-gray-950/60 border border-gray-800 px-3 py-2 text-xs text-gray-400">An uploaded image plays for the assigned audio duration. If no audio is selected, it runs for five seconds. A video uses its own duration and embedded audio unless you assign replacement audio.</p>
            <button onClick={() => void saveAssignment()} disabled={saving === 'assignment'} className="btn-primary w-full">{saving === 'assignment' ? 'Saving placement…' : `Save ${slot} placement`}</button>
          </div>
          <div className="mt-7 pt-5 border-t border-gray-800"><p className="text-xs tracking-[0.18em] uppercase text-gray-500">Active placements</p>{assignments.length === 0 ? <p className="text-sm text-gray-500 mt-3">No custom scenes assigned. Standard branded endings remain active.</p> : <div className="mt-3 space-y-2">{assignments.map(assignment => <div key={`${assignment.slot}-${assignment.output_ratio}`} className="rounded-lg border border-gray-800 bg-gray-950/40 px-3 py-3"><div className="flex items-start justify-between gap-3"><div><p className="text-sm font-semibold text-white capitalize">{assignment.slot} · {ratioOptions.find(option => option.value === assignment.output_ratio)?.label || assignment.output_ratio}</p><p className="text-xs text-gray-400 mt-1 truncate">{assignment.scene_name}{assignment.audio_name ? ` + ${assignment.audio_name}` : assignment.scene_has_audio ? ' · embedded audio' : ''}</p></div><button onClick={() => void clearAssignment(assignment)} className="text-xs text-red-300 hover:text-red-200">Remove</button></div></div>)}</div>}</div>
        </div>
      </section>
    </section>
  )
}
