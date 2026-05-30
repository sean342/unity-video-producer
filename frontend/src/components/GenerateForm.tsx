import React, { useState } from 'react'

interface Props {
  onJobStarted: (jobId: string) => void
}

const FORMAT_OPTIONS = [
  { value: 'myth_or_fact', label: 'Myth or Fact', emoji: '❓' },
  { value: 'quick_tip', label: 'Quick Tip', emoji: '💡' },
  { value: 'did_you_know', label: 'Did You Know', emoji: '🤔' },
]

const LENGTH_OPTIONS = [
  { value: '8s', label: '~8 seconds', desc: 'Short & punchy' },
  { value: '15s', label: '~15 seconds', desc: 'Standard' },
  { value: '20s', label: '~20 seconds', desc: 'Full explanation' },
]

const TOPIC_SUGGESTIONS = [
  'doors', 'windows', 'roofing', 'siding', 'insulation',
  'gutters', 'energy efficiency', 'permits', 'warranties',
]

export default function GenerateForm({ onJobStarted }: Props) {
  const [topic, setTopic] = useState('')
  const [format, setFormat] = useState('myth_or_fact')
  const [length, setLength] = useState('8s')
  const [customScript, setCustomScript] = useState('')
  const [showCustomScript, setShowCustomScript] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!topic.trim()) {
      setError('Please enter a topic')
      return
    }
    setError('')
    setLoading(true)

    try {
      const r = await fetch('/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          topic: topic.trim(),
          format,
          length,
          custom_script: showCustomScript && customScript.trim() ? customScript.trim() : null,
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

        {/* Custom Script Toggle */}
        <div>
          <button
            type="button"
            onClick={() => setShowCustomScript(!showCustomScript)}
            className="text-sm text-gray-400 hover:text-white transition-colors flex items-center gap-2"
          >
            <span className={`transition-transform ${showCustomScript ? 'rotate-90' : ''}`}>▶</span>
            {showCustomScript ? 'Hide' : 'Use custom script instead of AI-generated'}
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
              Starting generation...
            </>
          ) : (
            <>
              <span>🎬</span>
              Generate Unity Video
            </>
          )}
        </button>

        <p className="text-xs text-gray-500 text-center">
          Generation takes approximately 4–6 minutes. You'll see live progress updates.
        </p>
      </form>
    </div>
  )
}
