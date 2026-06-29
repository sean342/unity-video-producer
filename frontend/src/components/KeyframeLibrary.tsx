import { useState, useEffect } from 'react'

interface Keyframe {
  filename: string
  label: string
  description: string
  available: boolean
  tags: string[]
  is_reference: boolean
  is_alt: boolean
}

interface KeyframeLibraryProps {
  onUseKeyframe?: (filename: string, label: string) => void
}

const API_BASE = import.meta.env.VITE_API_BASE || ''

const TAG_COLORS: Record<string, string> = {
  windows: 'bg-blue-900 text-blue-300',
  doors: 'bg-amber-900 text-amber-300',
  roofing: 'bg-red-900 text-red-300',
  siding: 'bg-green-900 text-green-300',
  gutters: 'bg-cyan-900 text-cyan-300',
  insulation: 'bg-orange-900 text-orange-300',
  bathroom: 'bg-purple-900 text-purple-300',
  sunroom: 'bg-yellow-900 text-yellow-300',
  attic: 'bg-stone-700 text-stone-300',
  energy: 'bg-emerald-900 text-emerald-300',
  financing: 'bg-indigo-900 text-indigo-300',
  reviews: 'bg-pink-900 text-pink-300',
  driving: 'bg-sky-900 text-sky-300',
  teaching: 'bg-violet-900 text-violet-300',
  comedy: 'bg-fuchsia-900 text-fuchsia-300',
  walking: 'bg-teal-900 text-teal-300',
  reference: 'bg-gray-700 text-gray-300',
  exterior: 'bg-lime-900 text-lime-300',
  alt: 'bg-gray-800 text-gray-400',
}

function tagColor(tag: string): string {
  for (const key of Object.keys(TAG_COLORS)) {
    if (tag.toLowerCase().includes(key)) return TAG_COLORS[key]
  }
  return 'bg-gray-800 text-gray-400'
}

export default function KeyframeLibrary({ onUseKeyframe }: KeyframeLibraryProps) {
  const [keyframes, setKeyframes] = useState<Keyframe[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [filter, setFilter] = useState<'all' | 'scene' | 'reference' | 'alt'>('all')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<Keyframe | null>(null)

  // Delete state
  const [deleteConfirm, setDeleteConfirm] = useState<Keyframe | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState('')

  const loadKeyframes = () => {
    setLoading(true)
    fetch(`${API_BASE}/keyframes-list`)
      .then(r => r.json())
      .then((data: Keyframe[]) => {
        setKeyframes(data.filter(k => k.available))
        setLoading(false)
      })
      .catch(() => {
        setError('Failed to load keyframe library.')
        setLoading(false)
      })
  }

  useEffect(() => { loadKeyframes() }, [])

  const handleDelete = async () => {
    if (!deleteConfirm) return
    setDeleting(true)
    setDeleteError('')
    try {
      const res = await fetch(`${API_BASE}/keyframes/${deleteConfirm.filename}`, { method: 'DELETE' })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Delete failed')
      }
      setDeleteConfirm(null)
      setSelected(null)
      loadKeyframes()
    } catch (e: unknown) {
      setDeleteError(e instanceof Error ? e.message : 'Delete failed')
    } finally {
      setDeleting(false)
    }
  }

  const filtered = keyframes.filter(k => {
    const matchesFilter =
      filter === 'all' ||
      (filter === 'reference' && k.is_reference) ||
      (filter === 'alt' && k.is_alt) ||
      (filter === 'scene' && !k.is_reference && !k.is_alt)
    const matchesSearch =
      !search ||
      k.label.toLowerCase().includes(search.toLowerCase()) ||
      k.description.toLowerCase().includes(search.toLowerCase()) ||
      k.tags.some(t => t.toLowerCase().includes(search.toLowerCase()))
    return matchesFilter && matchesSearch
  })

  const sceneCount = keyframes.filter(k => !k.is_reference && !k.is_alt).length
  const refCount = keyframes.filter(k => k.is_reference).length
  const altCount = keyframes.filter(k => k.is_alt).length

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-unified-red border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          <p className="text-gray-400 text-sm">Loading keyframe library...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="card text-center py-12">
        <p className="text-red-400">{error}</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header + Controls */}
      <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-white">Keyframe Library</h2>
          <p className="text-sm text-gray-400 mt-0.5">
            {keyframes.length} keyframes available — click any to preview, or use it in a video
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          {([
            ['all', `All (${keyframes.length})`],
            ['scene', `Scenes (${sceneCount})`],
            ['reference', `References (${refCount})`],
            ['alt', `Alt Angles (${altCount})`],
          ] as [typeof filter, string][]).map(([val, label]) => (
            <button
              key={val}
              onClick={() => setFilter(val)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                filter === val
                  ? 'bg-unified-red text-white'
                  : 'bg-gray-800 text-gray-400 hover:text-white hover:bg-gray-700'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Search */}
      <div className="relative">
        <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-4.35-4.35M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z" />
        </svg>
        <input
          type="text"
          placeholder="Search by label, description, or tag..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="w-full bg-gray-800 border border-gray-700 rounded-lg pl-9 pr-4 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-unified-red"
        />
        {search && (
          <button onClick={() => setSearch('')} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-white">
            ✕
          </button>
        )}
      </div>

      {/* Grid */}
      {filtered.length === 0 ? (
        <div className="card text-center py-12">
          <p className="text-gray-400">No keyframes match your search.</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
          {filtered.map(kf => (
            <div
              key={kf.filename}
              onClick={() => setSelected(kf)}
              className="group cursor-pointer rounded-xl overflow-hidden bg-gray-900 border border-gray-800 hover:border-unified-red transition-all duration-200 hover:shadow-lg hover:shadow-unified-red/10"
            >
              {/* Image */}
              <div className="relative aspect-[2/3] bg-gray-800 overflow-hidden">
                <img
                  src={`${API_BASE}/keyframes/${kf.filename}`}
                  alt={kf.label}
                  className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                  loading="lazy"
                  onError={e => {
                    (e.target as HTMLImageElement).src = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="100" height="150" viewBox="0 0 100 150"><rect fill="%23374151" width="100" height="150"/><text fill="%236B7280" font-size="10" x="50" y="75" text-anchor="middle">No preview</text></svg>'
                  }}
                />
                {/* Badges */}
                {kf.is_alt && (
                  <span className="absolute top-2 right-2 bg-gray-900/80 text-gray-300 text-xs px-1.5 py-0.5 rounded font-medium">
                    ALT
                  </span>
                )}
                {kf.is_reference && (
                  <span className="absolute top-2 right-2 bg-unified-red/90 text-white text-xs px-1.5 py-0.5 rounded font-medium">
                    REF
                  </span>
                )}
                {/* Hover overlay */}
                <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex flex-col items-center justify-end gap-1.5 p-2">
                  {onUseKeyframe && !kf.is_reference && (
                    <button
                      onClick={e => {
                        e.stopPropagation()
                        onUseKeyframe(kf.filename, kf.label)
                      }}
                      className="w-full bg-unified-red text-white text-xs font-semibold py-1.5 rounded-lg hover:bg-red-600 transition-colors"
                    >
                      Use This
                    </button>
                  )}
                  {/* Delete button — hidden for reference keyframes */}
                  {!kf.is_reference && (
                    <button
                      onClick={e => {
                        e.stopPropagation()
                        setDeleteError('')
                        setDeleteConfirm(kf)
                      }}
                      className="w-full bg-gray-800/90 text-red-400 text-xs font-semibold py-1.5 rounded-lg hover:bg-red-900/60 hover:text-red-300 transition-colors border border-red-900/40"
                    >
                      🗑 Delete
                    </button>
                  )}
                </div>
              </div>
              {/* Label */}
              <div className="p-2">
                <p className="text-xs font-medium text-white truncate">{kf.label}</p>
                {kf.tags.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1">
                    {kf.tags.slice(0, 2).map(tag => (
                      <span key={tag} className={`text-xs px-1.5 py-0.5 rounded ${tagColor(tag)}`}>
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Modal Preview */}
      {selected && (
        <div
          className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4"
          onClick={() => setSelected(null)}
        >
          <div
            className="bg-gray-900 rounded-2xl overflow-hidden max-w-sm w-full shadow-2xl border border-gray-700"
            onClick={e => e.stopPropagation()}
          >
            <div className="relative">
              <img
                src={`${API_BASE}/keyframes/${selected.filename}`}
                alt={selected.label}
                className="w-full object-cover max-h-[60vh]"
              />
              <button
                onClick={() => setSelected(null)}
                className="absolute top-3 right-3 bg-black/60 text-white rounded-full w-8 h-8 flex items-center justify-center hover:bg-black/80 transition-colors"
              >
                ✕
              </button>
            </div>
            <div className="p-4 space-y-3">
              <div>
                <h3 className="text-white font-bold text-lg">{selected.label}</h3>
                <p className="text-gray-400 text-sm mt-1">{selected.description}</p>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {selected.tags.map(tag => (
                  <span key={tag} className={`text-xs px-2 py-1 rounded-full ${tagColor(tag)}`}>
                    {tag}
                  </span>
                ))}
              </div>
              <p className="text-gray-600 text-xs font-mono">{selected.filename}</p>

              {/* Reference keyframes: locked message */}
              {selected.is_reference && (
                <div className="bg-gray-800 rounded-lg px-3 py-2 text-xs text-gray-400 flex items-center gap-2">
                  <span>🔒</span>
                  <span>Reference keyframe — used for AI character consistency. Cannot be deleted.</span>
                </div>
              )}

              <div className="flex gap-2">
                {onUseKeyframe && !selected.is_reference && (
                  <button
                    onClick={() => {
                      onUseKeyframe(selected.filename, selected.label)
                      setSelected(null)
                    }}
                    className="flex-1 bg-unified-red text-white font-semibold py-2.5 rounded-xl hover:bg-red-600 transition-colors text-sm"
                  >
                    Use This Keyframe
                  </button>
                )}
                {!selected.is_reference && (
                  <button
                    onClick={() => {
                      setDeleteError('')
                      setDeleteConfirm(selected)
                      setSelected(null)
                    }}
                    className="px-4 py-2.5 rounded-xl border border-red-900/50 text-red-400 hover:bg-red-900/30 transition-colors text-sm font-medium"
                  >
                    🗑 Delete
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deleteConfirm && (
        <div
          className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4"
          onClick={() => !deleting && setDeleteConfirm(null)}
        >
          <div
            className="bg-gray-900 rounded-2xl max-w-sm w-full shadow-2xl border border-gray-700 p-6"
            onClick={e => e.stopPropagation()}
          >
            <div className="text-center mb-4">
              <div className="text-4xl mb-3">🗑️</div>
              <h3 className="text-white font-bold text-lg">Delete Keyframe?</h3>
              <p className="text-gray-400 text-sm mt-2">
                Are you sure you want to delete <span className="text-white font-medium">"{deleteConfirm.label}"</span>?
                This cannot be undone.
              </p>
            </div>

            {deleteError && (
              <div className="mb-4 p-3 bg-red-900/30 border border-red-700 rounded-lg text-sm text-red-400">
                {deleteError}
              </div>
            )}

            <div className="flex gap-3">
              <button
                onClick={() => setDeleteConfirm(null)}
                disabled={deleting}
                className="flex-1 px-4 py-2.5 border border-gray-700 rounded-xl text-sm text-gray-300 hover:bg-gray-800 transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="flex-1 px-4 py-2.5 bg-red-700 hover:bg-red-600 text-white rounded-xl text-sm font-semibold transition-colors disabled:opacity-50"
              >
                {deleting ? 'Deleting...' : 'Yes, Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
