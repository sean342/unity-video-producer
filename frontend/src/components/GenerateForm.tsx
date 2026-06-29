import React, { useState, useEffect } from 'react'

const API_BASE = import.meta.env.VITE_API_URL || ''

interface Keyframe {
  filename: string
  label: string
  tags: string[]
  url: string
  available: boolean
  is_reference: boolean
}

interface Props {
  onJobStarted: (jobId: string) => void
  preselectedKeyframe?: string | null
  onKeyframeClear?: () => void
}

const FORMAT_OPTIONS = [
  { value: 'myth_or_fact', label: 'Myth or Fact', emoji: '❓' },
  { value: 'quick_tip',    label: 'Quick Tip',    emoji: '💡' },
  { value: 'did_you_know', label: 'Did You Know', emoji: '🤔' },
]

const LENGTH_OPTIONS = [
  { value: '8s',  desc: 'Short & punchy' },
  { value: '15s', desc: 'Standard' },
  { value: '20s', desc: 'Full explanation' },
]

const TOPIC_SUGGESTIONS = [
  'doors', 'windows', 'roofing', 'siding', 'insulation',
  'gutters', 'energy efficiency', 'permits', 'warranties',
]

export default function GenerateForm({ onJobStarted, preselectedKeyframe, onKeyframeClear }: Props) {
  const [topic, setTopic]               = useState('')
  const [format, setFormat]             = useState('myth_or_fact')
  const [length, setLength]             = useState('15s')
  const [customScript, setCustomScript] = useState('')
  const [showCustomScript, setShowCustomScript] = useState(false)

  // Keyframe state
  const [keyframes, setKeyframes]               = useState<Keyframe[]>([])
  const [keyframesLoading, setKeyframesLoading] = useState(true)
  const [selectedKeyframe, setSelectedKeyframe] = useState<string | null>(preselectedKeyframe || null)  // filename or null = auto

  // Sync when Library tab sends a preselected keyframe
  useEffect(() => {
    if (preselectedKeyframe) setSelectedKeyframe(preselectedKeyframe)
  }, [preselectedKeyframe])
  const [showKeyframeLib, setShowKeyframeLib]   = useState(false)
  const [kfFilter, setKfFilter]                 = useState('')

  // On-the-fly keyframe generation
  const [showKfGen, setShowKfGen]         = useState(false)
  const [kfDescription, setKfDescription] = useState('')
  const [kfGenLoading, setKfGenLoading]   = useState(false)
  const [kfGenJobId, setKfGenJobId]       = useState<string | null>(null)
  const [kfGenPreview, setKfGenPreview]   = useState<string | null>(null)   // URL of generated keyframe
  const [kfGenFilename, setKfGenFilename] = useState<string | null>(null)
  const [kfGenError, setKfGenError]       = useState('')
  const [kfMagicLoading, setKfMagicLoading] = useState(false)

  // Keyframe library management
  const [deletingKf, setDeletingKf]     = useState<string | null>(null)

  // Submission
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState('')

  // ── Load keyframe library ──────────────────────────────────────────────────
  const loadKeyframes = async () => {
    setKeyframesLoading(true)
    try {
      const r = await fetch(`${API_BASE}/keyframes-list`)
      const data: Keyframe[] = await r.json()
      setKeyframes(data.filter(k => k.available && !k.is_reference))
    } catch {
      // silently fail
    } finally {
      setKeyframesLoading(false)
    }
  }

  useEffect(() => { loadKeyframes() }, [])

  // ── Filtered keyframes ─────────────────────────────────────────────────────
  const filteredKeyframes = keyframes.filter(k => {
    if (!kfFilter.trim()) return true
    const q = kfFilter.toLowerCase()
    return (
      k.label.toLowerCase().includes(q) ||
      k.tags.some(t => t.toLowerCase().includes(q))
    )
  })

  // ── Prompt Magic ───────────────────────────────────────────────────────────
  const handlePromptMagic = async () => {
    if (!kfDescription.trim()) return
    setKfMagicLoading(true)
    try {
      const r = await fetch(`${API_BASE}/optimize-keyframe-description`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description: kfDescription }),
      })
      if (r.ok) {
        const data = await r.json()
        setKfDescription(data.optimized || kfDescription)
      }
    } catch {
      // silently fail — keep original
    } finally {
      setKfMagicLoading(false)
    }
  }

  // ── On-the-fly keyframe generation ────────────────────────────────────────
  const handleGenerateKeyframe = async () => {
    if (!kfDescription.trim()) return
    setKfGenLoading(true)
    setKfGenError('')
    setKfGenPreview(null)
    setKfGenFilename(null)
    setKfGenJobId(null)
    try {
      const r = await fetch(`${API_BASE}/generate-keyframe`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description: kfDescription }),
      })
      if (!r.ok) throw new Error('Generation failed')
      const data = await r.json()
      // Poll for completion
      const jobId = data.job_id || data.filename
      setKfGenJobId(jobId)
      // If it returns a direct URL (synchronous), show it immediately
      if (data.url) {
        setKfGenPreview(`${API_BASE}${data.url}`)
        setKfGenFilename(data.filename)
        setKfGenLoading(false)
        return
      }
      // Otherwise poll
      const poll = setInterval(async () => {
        try {
          const sr = await fetch(`${API_BASE}/status/${jobId}`)
          const sd = await sr.json()
          if (sd.status === 'complete' || sd.keyframe_url) {
            clearInterval(poll)
            setKfGenPreview(`${API_BASE}${sd.keyframe_url}`)
            setKfGenFilename(sd.keyframe_filename || sd.keyframe_url?.split('/').pop())
            setKfGenLoading(false)
          } else if (sd.status === 'failed') {
            clearInterval(poll)
            setKfGenError(sd.error || 'Generation failed')
            setKfGenLoading(false)
          }
        } catch {}
      }, 3000)
    } catch (err: any) {
      setKfGenError(err.message || 'Failed to generate keyframe')
      setKfGenLoading(false)
    }
  }

  const handleApproveKeyframe = async () => {
    if (!kfGenFilename) return
    // Save the keyframe to the library
    try {
      await fetch(`${API_BASE}/save-keyframe`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: kfGenFilename, label: kfDescription.slice(0, 40) }),
      })
    } catch {}
    setSelectedKeyframe(kfGenFilename)
    setShowKfGen(false)
    setKfDescription('')
    setKfGenPreview(null)
    setKfGenFilename(null)
    await loadKeyframes()
  }

  const handleRejectKeyframe = () => {
    setKfGenPreview(null)
    setKfGenFilename(null)
    setKfGenJobId(null)
  }

  // ── Delete keyframe ────────────────────────────────────────────────────────
  const handleDeleteKeyframe = async (filename: string, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!confirm(`Delete keyframe "${filename}"? This cannot be undone.`)) return
    setDeletingKf(filename)
    try {
      const r = await fetch(`${API_BASE}/keyframes/${filename}`, { method: 'DELETE' })
      if (r.ok) {
        if (selectedKeyframe === filename) setSelectedKeyframe(null)
        await loadKeyframes()
      }
    } catch {}
    setDeletingKf(null)
  }

  // ── Submit video generation ────────────────────────────────────────────────
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!topic.trim()) { setError('Please enter a topic'); return }
    setError('')
    setLoading(true)
    try {
      const r = await fetch(`${API_BASE}/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          topic: topic.trim(),
          format,
          length,
          custom_script: showCustomScript && customScript.trim() ? customScript.trim() : null,
          keyframe_override: selectedKeyframe || null,
        }),
      })
      if (!r.ok) {
        const err = await r.json()
        throw new Error(err.detail || 'Generation failed')
      }
      const data = await r.json()
      onJobStarted(data.job_id)
    } catch (err: any) {
      setError(err.message || 'Something went wrong. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  // ── Selected keyframe display ──────────────────────────────────────────────
  const selectedKfData = keyframes.find(k => k.filename === selectedKeyframe)

  return (
    <div className="card">
      <h2 className="text-xl font-bold text-white mb-6">Generate Unity Video</h2>

      <form onSubmit={handleSubmit} className="space-y-6">

        {/* Topic */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Topic <span className="text-unified-red">*</span>
          </label>
          <input
            type="text"
            value={topic}
            onChange={e => setTopic(e.target.value)}
            placeholder="e.g. double-pane windows, front doors, roof insulation"
            className="input-field"
            disabled={loading}
          />
          <div className="flex flex-wrap gap-2 mt-2">
            {TOPIC_SUGGESTIONS.map(s => (
              <button
                key={s}
                type="button"
                onClick={() => setTopic(s)}
                className="text-xs bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white
                           px-3 py-1 rounded-full transition-colors border border-gray-700"
              >
                {s}
              </button>
            ))}
          </div>
        </div>

        {/* Format */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">Format</label>
          <div className="grid grid-cols-3 gap-3">
            {FORMAT_OPTIONS.map(opt => (
              <button
                key={opt.value}
                type="button"
                onClick={() => setFormat(opt.value)}
                disabled={loading}
                className={`flex flex-col items-center p-3 rounded-xl border-2 transition-all ${
                  format === opt.value
                    ? 'border-unified-red bg-unified-red/10 text-white'
                    : 'border-gray-700 bg-gray-800 text-gray-400 hover:border-gray-600'
                }`}
              >
                <span className="text-xl mb-1">{opt.emoji}</span>
                <span className="text-xs font-medium">{opt.label}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Length */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">Length</label>
          <div className="grid grid-cols-3 gap-3">
            {LENGTH_OPTIONS.map(opt => (
              <button
                key={opt.value}
                type="button"
                onClick={() => setLength(opt.value)}
                disabled={loading}
                className={`flex flex-col items-center p-3 rounded-xl border-2 transition-all ${
                  length === opt.value
                    ? 'border-unified-gold bg-unified-gold/10 text-white'
                    : 'border-gray-700 bg-gray-800 text-gray-400 hover:border-gray-600'
                }`}
              >
                <span className="text-sm font-bold">{opt.value}</span>
                <span className="text-xs text-gray-500 mt-0.5">{opt.desc}</span>
              </button>
            ))}
          </div>
        </div>

        {/* ── Keyframe Library ─────────────────────────────────────────────── */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="text-sm font-medium text-gray-300">
              Keyframe
              <span className="ml-2 text-xs text-gray-500 font-normal">
                {selectedKeyframe ? `— ${selectedKfData?.label || selectedKeyframe}` : '— Auto-select based on topic'}
              </span>
            </label>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => { setShowKfGen(!showKfGen); setShowKeyframeLib(false) }}
                className="text-xs text-unified-gold hover:text-yellow-300 transition-colors flex items-center gap-1"
              >
                ✨ Generate new
              </button>
              <button
                type="button"
                onClick={() => { setShowKeyframeLib(!showKeyframeLib); setShowKfGen(false) }}
                className="text-xs text-gray-400 hover:text-white transition-colors flex items-center gap-1"
              >
                {showKeyframeLib ? '▲ Hide library' : '▼ Browse library'}
              </button>
            </div>
          </div>

          {/* Selected keyframe preview */}
          {selectedKeyframe && selectedKfData && (
            <div className="flex items-center gap-3 p-3 bg-gray-800 border border-unified-gold/40 rounded-xl mb-3">
              <img
                src={`${API_BASE}${selectedKfData.url}`}
                alt={selectedKfData.label}
                className="w-16 h-16 object-cover rounded-lg border border-gray-700"
              />
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-white">{selectedKfData.label}</div>
                <div className="text-xs text-gray-500 mt-0.5">{selectedKfData.tags.slice(0, 4).join(', ')}</div>
              </div>
              <button
                type="button"
                onClick={() => { setSelectedKeyframe(null); onKeyframeClear?.() }}
                className="text-xs text-gray-500 hover:text-red-400 transition-colors px-2 py-1 rounded"
              >
                ✕ Clear
              </button>
            </div>
          )}

          {/* Keyframe library browser */}
          {showKeyframeLib && (
            <div className="border border-gray-700 rounded-xl overflow-hidden">
              <div className="p-3 bg-gray-800/60 border-b border-gray-700">
                <input
                  type="text"
                  value={kfFilter}
                  onChange={e => setKfFilter(e.target.value)}
                  placeholder="Search keyframes (windows, doors, roofing…)"
                  className="input-field text-sm py-2"
                />
              </div>
              {keyframesLoading ? (
                <div className="p-6 text-center text-gray-500 text-sm">Loading keyframes…</div>
              ) : filteredKeyframes.length === 0 ? (
                <div className="p-6 text-center text-gray-500 text-sm">No keyframes match your search.</div>
              ) : (
                <div className="grid grid-cols-3 sm:grid-cols-4 gap-2 p-3 max-h-72 overflow-y-auto">
                  {/* Auto option */}
                  <button
                    type="button"
                    onClick={() => { setSelectedKeyframe(null); setShowKeyframeLib(false) }}
                    className={`relative flex flex-col items-center p-2 rounded-xl border-2 transition-all ${
                      !selectedKeyframe
                        ? 'border-unified-red bg-unified-red/10'
                        : 'border-gray-700 bg-gray-800 hover:border-gray-600'
                    }`}
                  >
                    <div className="w-full aspect-square bg-gray-700 rounded-lg flex items-center justify-center mb-1.5">
                      <span className="text-2xl">🤖</span>
                    </div>
                    <span className="text-xs text-gray-300 text-center leading-tight">Auto</span>
                  </button>

                  {filteredKeyframes.map(kf => (
                    <button
                      key={kf.filename}
                      type="button"
                      onClick={() => { setSelectedKeyframe(kf.filename); setShowKeyframeLib(false) }}
                      className={`relative flex flex-col items-center p-2 rounded-xl border-2 transition-all group ${
                        selectedKeyframe === kf.filename
                          ? 'border-unified-gold bg-unified-gold/10'
                          : 'border-gray-700 bg-gray-800 hover:border-gray-600'
                      }`}
                    >
                      <img
                        src={`${API_BASE}${kf.url}`}
                        alt={kf.label}
                        className="w-full aspect-square object-cover rounded-lg mb-1.5"
                      />
                      <span className="text-xs text-gray-300 text-center leading-tight line-clamp-2">{kf.label}</span>
                      {/* Delete button */}
                      {!kf.is_reference && (
                        <button
                          type="button"
                          onClick={(e) => handleDeleteKeyframe(kf.filename, e)}
                          disabled={deletingKf === kf.filename}
                          className="absolute top-1 right-1 bg-gray-900/80 hover:bg-red-900 text-white rounded-full w-5 h-5
                                     flex items-center justify-center text-xs opacity-0 group-hover:opacity-100 transition-opacity"
                        >
                          {deletingKf === kf.filename ? '…' : '✕'}
                        </button>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* On-the-fly keyframe generator */}
          {showKfGen && (
            <div className="border border-unified-gold/30 rounded-xl overflow-hidden mt-2">
              <div className="p-4 bg-gray-800/60 space-y-3">
                <p className="text-xs text-gray-400">
                  Describe a new scene for Unity. The system will generate a keyframe image for your approval before using it.
                </p>
                <div className="relative">
                  <textarea
                    value={kfDescription}
                    onChange={e => setKfDescription(e.target.value)}
                    placeholder="e.g. Unity standing next to a sunroom addition on the back of a house, pointing at the glass panels"
                    className="input-field h-20 resize-none pr-24"
                    disabled={kfGenLoading}
                  />
                  <button
                    type="button"
                    onClick={handlePromptMagic}
                    disabled={kfMagicLoading || !kfDescription.trim()}
                    title="Optimize description with AI"
                    className="absolute bottom-2 right-2 flex items-center gap-1 text-xs bg-gray-700 hover:bg-unified-gold/20
                               text-gray-300 hover:text-unified-gold px-2 py-1 rounded-lg transition-colors border border-gray-600"
                  >
                    {kfMagicLoading ? '…' : '✨ Magic'}
                  </button>
                </div>

                {kfGenError && (
                  <div className="text-red-400 text-xs">{kfGenError}</div>
                )}

                {/* Preview + approval */}
                {kfGenPreview ? (
                  <div className="space-y-3">
                    <img
                      src={kfGenPreview}
                      alt="Generated keyframe preview"
                      className="w-full rounded-xl border border-gray-700"
                    />
                    <p className="text-xs text-gray-400 text-center">Review the keyframe above. Approve to use it, or reject to regenerate.</p>
                    <div className="grid grid-cols-2 gap-2">
                      <button
                        type="button"
                        onClick={handleApproveKeyframe}
                        className="btn-primary text-sm py-2 flex items-center justify-center gap-1"
                      >
                        ✅ Approve & Use
                      </button>
                      <button
                        type="button"
                        onClick={handleRejectKeyframe}
                        className="btn-secondary text-sm py-2 flex items-center justify-center gap-1"
                      >
                        🔄 Regenerate
                      </button>
                    </div>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={handleGenerateKeyframe}
                    disabled={kfGenLoading || !kfDescription.trim()}
                    className="btn-secondary w-full text-sm flex items-center justify-center gap-2"
                  >
                    {kfGenLoading ? (
                      <>
                        <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                        </svg>
                        Generating keyframe…
                      </>
                    ) : (
                      <><span>🖼️</span> Generate Keyframe</>
                    )}
                  </button>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Custom Script Toggle */}
        <div>
          <button
            type="button"
            onClick={() => setShowCustomScript(!showCustomScript)}
            className="text-sm text-gray-400 hover:text-white transition-colors flex items-center gap-2"
          >
            <span className={`transition-transform ${showCustomScript ? 'rotate-90' : ''}`}>▶</span>
            {showCustomScript ? 'Hide custom script' : 'Use custom script instead of AI-generated'}
          </button>
          {showCustomScript && (
            <textarea
              value={customScript}
              onChange={e => setCustomScript(e.target.value)}
              placeholder="Paste your script here. Unity will speak exactly these words."
              className="input-field mt-3 h-32 resize-none"
              disabled={loading}
            />
          )}
        </div>

        {/* Error */}
        {error && (
          <div className="bg-red-900/30 border border-red-800 rounded-xl p-3 text-red-300 text-sm">
            {error}
          </div>
        )}

        {/* Submit */}
        <button
          type="submit"
          disabled={loading || !topic.trim()}
          className="btn-primary w-full flex items-center justify-center gap-3"
        >
          {loading ? (
            <>
              <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Starting generation…
            </>
          ) : (
            <><span>🎬</span> Generate Unity Video</>
          )}
        </button>
        <p className="text-xs text-gray-500 text-center">
          Generation takes approximately 4–6 minutes. You'll see live progress updates.
        </p>
      </form>
    </div>
  )
}
