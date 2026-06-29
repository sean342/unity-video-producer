import { useState, useRef, useEffect } from 'react'

const API_BASE = import.meta.env.VITE_API_URL || ''

// ─── Brand colors ─────────────────────────────────────────────────────────────
// Primary: #C41230 (red), #F5A623 (gold), #1A1A1A (dark), #FFFFFF (white)

const CONTENT_TYPES = [
  { value: 'tip_card',     label: 'Tip Card',      icon: '💡', desc: 'Educational tip or fact' },
  { value: 'before_after', label: 'Before / After', icon: '🏠', desc: 'Project reveal split' },
  { value: 'carousel',     label: 'Carousel',       icon: '📋', desc: 'Multi-slide series' },
  { value: 'testimonial',  label: 'Testimonial',    icon: '⭐', desc: 'Customer quote' },
  { value: 'promotional',  label: 'Promotional',    icon: '📣', desc: 'Offer or announcement' },
]

const SIZE_PRESETS = [
  { ratio: '1:1',  label: 'Square',    sublabel: 'Instagram · Facebook Feed',  icon: '⬛' },
  { ratio: '4:5',  label: 'Portrait',  sublabel: 'Instagram · Facebook Feed',  icon: '📱' },
  { ratio: '9:16', label: 'Vertical',  sublabel: 'Stories · Reels · TikTok',   icon: '📲' },
  { ratio: '16:9', label: 'Landscape', sublabel: 'Facebook · YouTube Cover',   icon: '🖥️' },
]

// ─── Premade templates ────────────────────────────────────────────────────────
// Each template pre-fills content_type, size_ratio, and user_prompt
const PREMADE_TEMPLATES = [
  {
    id: 'westchester_windows',
    label: 'Westchester Windows Tip',
    category: 'Tip Card',
    size: '1:1',
    icon: '🪟',
    color: 'from-blue-900/40 to-gray-900',
    content_type: 'tip_card',
    size_ratio: '1:1',
    prompt: 'Did you know most Westchester homes were built before 1960? Those original windows can account for up to 30% of your heating and cooling loss. New energy-efficient windows pay for themselves.',
  },
  {
    id: 'roofing_promo',
    label: 'Roofing Special Offer',
    category: 'Promotional',
    size: '9:16',
    icon: '🏠',
    color: 'from-red-900/40 to-gray-900',
    content_type: 'promotional',
    size_ratio: '9:16',
    prompt: 'Free roof inspection for homeowners in Westchester, Long Island, and NJ. Limited spots available this month. Call Unified Home Remodeling today.',
  },
  {
    id: 'siding_before_after',
    label: 'Siding Before / After',
    category: 'Before / After',
    size: '1:1',
    icon: '🎨',
    color: 'from-green-900/40 to-gray-900',
    content_type: 'before_after',
    size_ratio: '1:1',
    prompt: 'Old faded vinyl siding on a 1970s colonial home → fresh white James Hardie fiber cement siding with charcoal shutters and new trim. Dramatic curb appeal transformation.',
  },
  {
    id: 'testimonial_westchester',
    label: 'Customer Testimonial',
    category: 'Testimonial',
    size: '4:5',
    icon: '💬',
    color: 'from-yellow-900/40 to-gray-900',
    content_type: 'testimonial',
    size_ratio: '4:5',
    prompt: '"Unified replaced all 14 windows in our White Plains home in a single day. The crew was professional, clean, and the difference in our energy bill was immediate." — The Martinez Family, White Plains NY',
  },
  {
    id: 'windows_carousel_1',
    label: '5 Signs You Need New Windows — Slide 1',
    category: 'Carousel',
    size: '1:1',
    icon: '📋',
    color: 'from-purple-900/40 to-gray-900',
    content_type: 'carousel',
    size_ratio: '1:1',
    prompt: '5 Signs You Need New Windows — Intro slide. Bold title. Teaser: "If your home has any of these warning signs, it\'s time to call Unified."',
    total_slides: 5,
    slide_num: 1,
  },
  {
    id: 'door_tip',
    label: 'Entry Door Value Tip',
    category: 'Tip Card',
    size: '4:5',
    icon: '🚪',
    color: 'from-orange-900/40 to-gray-900',
    content_type: 'tip_card',
    size_ratio: '4:5',
    prompt: 'A new entry door can return over 100% of its cost in home resale value. In Westchester, first impressions matter — and your front door is the first thing buyers see.',
  },
]

interface GraphicJob {
  job_id: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  step?: string
  progress?: number
  error?: string
  image_url?: string
}

interface Props {
  onJobStarted?: (jobId: string) => void
  portedScene?: string | null          // scene description ported from Images page
  onPortedSceneConsumed?: () => void   // called after the ported scene is applied
}

export default function GraphicsForm({ onJobStarted, portedScene, onPortedSceneConsumed }: Props) {
  const [contentType, setContentType] = useState('tip_card')
  const [sizeRatio, setSizeRatio] = useState('1:1')
  const [userPrompt, setUserPrompt] = useState('')
  const [sceneDescription, setSceneDescription] = useState('')
  const [headline, setHeadline] = useState('')
  const [ctaText, setCtaText] = useState('')
  const [totalSlides, setTotalSlides] = useState(1)
  const [slideNum, setSlideNum] = useState(1)
  const [uploadedFile, setUploadedFile] = useState<File | null>(null)
  const [uploadPreview, setUploadPreview] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [currentJob, setCurrentJob] = useState<GraphicJob | null>(null)
  const [activeTemplate, setActiveTemplate] = useState<string | null>(null)
  const [pollInterval, setPollInterval] = useState<ReturnType<typeof setInterval> | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const formRef = useRef<HTMLDivElement>(null)

  // Apply ported scene from Images page when it arrives
  useEffect(() => {
    if (portedScene) {
      setSceneDescription(portedScene)
      if (onPortedSceneConsumed) onPortedSceneConsumed()
    }
  }, [portedScene])

  const applyTemplate = (tpl: typeof PREMADE_TEMPLATES[0]) => {
    setContentType(tpl.content_type)
    setSizeRatio(tpl.size_ratio)
    setUserPrompt(tpl.prompt)
    if (tpl.content_type === 'carousel') {
      setTotalSlides((tpl as any).total_slides || 5)
      setSlideNum((tpl as any).slide_num || 1)
    }
    setActiveTemplate(tpl.id)
    setCurrentJob(null)
    // Scroll to form
    setTimeout(() => formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100)
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploadedFile(file)
    const reader = new FileReader()
    reader.onload = (ev) => setUploadPreview(ev.target?.result as string)
    reader.readAsDataURL(file)
  }

  const clearUpload = () => {
    setUploadedFile(null)
    setUploadPreview(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const pollStatus = (jobId: string) => {
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/graphic-status/${jobId}`)
        const data: GraphicJob = await res.json()
        setCurrentJob(data)
        if (data.status === 'completed' || data.status === 'failed') {
          clearInterval(interval)
          setPollInterval(null)
          setLoading(false)
        }
      } catch {
        // ignore transient errors
      }
    }, 2000)
    setPollInterval(interval)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!userPrompt.trim()) return
    setLoading(true)
    setError('')
    setCurrentJob(null)

    try {
      // Step 1: Upload photo if one was selected
      let uploadedImagePath: string | undefined = undefined
      if (uploadedFile) {
        const formData = new FormData()
        formData.append('photo', uploadedFile)
        const uploadRes = await fetch(`${API_BASE}/upload-graphic-photo`, {
          method: 'POST',
          body: formData,
        })
        if (!uploadRes.ok) throw new Error(`Photo upload failed: ${uploadRes.status}`)
        const uploadData = await uploadRes.json()
        uploadedImagePath = uploadData.path
      }

      // Step 2: Start graphic generation with optional photo path
      const fullPrompt = sceneDescription.trim()
        ? `${userPrompt.trim()}\n\nScene: ${sceneDescription.trim()}`
        : userPrompt.trim()

      const res = await fetch(`${API_BASE}/generate-graphic`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content_type: contentType,
          size_ratio: sizeRatio,
          user_prompt: fullPrompt,
          headline: headline.trim() || undefined,
          cta_text: ctaText.trim() || undefined,
          total_slides: contentType === 'carousel' ? totalSlides : 1,
          slide_num: contentType === 'carousel' ? slideNum : 1,
          client_id: 'unified',
          uploaded_image_path: uploadedImagePath,
        }),
      })
      if (!res.ok) throw new Error(`Server error ${res.status}`)
      const data = await res.json()
      setCurrentJob({ job_id: data.job_id, status: 'queued' })
      onJobStarted?.(data.job_id)
      pollStatus(data.job_id)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to start generation')
      setLoading(false)
    }
  }

  const handleDownload = () => {
    if (!currentJob?.image_url) return
    const a = document.createElement('a')
    a.href = `${API_BASE}${currentJob.image_url}`
    a.download = `unity_graphic_${currentJob.job_id.slice(0, 8)}.png`
    a.click()
  }

  return (
    <div className="space-y-8">

      {/* ── Premade Templates ─────────────────────────────────────────────── */}
      <div>
        <div className="flex items-center gap-2 mb-4">
          <div className="w-1 h-5 rounded-full bg-unified-red" />
          <h2 className="text-lg font-bold text-white">Quick Start Templates</h2>
        </div>
        <p className="text-sm text-gray-400 mb-4">
          Click any template to pre-fill the form below. Customize the copy, then generate.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {PREMADE_TEMPLATES.map(tpl => (
            <button
              key={tpl.id}
              type="button"
              onClick={() => applyTemplate(tpl)}
              disabled={loading}
              className={`text-left p-4 rounded-xl border-2 transition-all bg-gradient-to-br ${tpl.color} ${
                activeTemplate === tpl.id
                  ? 'border-unified-red ring-1 ring-unified-red/50'
                  : 'border-gray-700 hover:border-gray-500'
              }`}
            >
              <div className="flex items-start gap-3">
                <span className="text-2xl mt-0.5">{tpl.icon}</span>
                <div className="min-w-0">
                  <div className="text-sm font-semibold text-white leading-tight">{tpl.label}</div>
                  <div className="flex items-center gap-2 mt-1.5">
                    <span className="text-xs bg-gray-800 text-gray-400 px-2 py-0.5 rounded-full">{tpl.category}</span>
                    <span className="text-xs bg-gray-800 text-gray-400 px-2 py-0.5 rounded-full">{tpl.size}</span>
                  </div>
                </div>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* ── Custom Form ───────────────────────────────────────────────────── */}
      <div ref={formRef} className="card">
        <div className="flex items-center gap-2 mb-6">
          <div className="w-1 h-5 rounded-full bg-unified-gold" />
          <h2 className="text-lg font-bold text-white">
            {activeTemplate ? 'Customize & Generate' : 'Generate Unity Graphic'}
          </h2>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">

          {/* Content Type */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Content Type</label>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              {CONTENT_TYPES.map(opt => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => { setContentType(opt.value); setActiveTemplate(null) }}
                  disabled={loading}
                  className={`flex flex-col items-center p-3 rounded-xl border-2 transition-all ${
                    contentType === opt.value
                      ? 'border-unified-red bg-unified-red/10 text-white'
                      : 'border-gray-700 bg-gray-800 text-gray-400 hover:border-gray-600'
                  }`}
                >
                  <span className="text-xl mb-1">{opt.icon}</span>
                  <span className="text-xs font-medium">{opt.label}</span>
                  <span className="text-xs text-gray-500 mt-0.5 text-center">{opt.desc}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Carousel slide controls */}
          {contentType === 'carousel' && (
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Total Slides</label>
                <input
                  type="number"
                  min={2}
                  max={10}
                  value={totalSlides}
                  onChange={e => setTotalSlides(parseInt(e.target.value) || 2)}
                  className="input-field"
                  disabled={loading}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">This Slide #</label>
                <input
                  type="number"
                  min={1}
                  max={totalSlides}
                  value={slideNum}
                  onChange={e => setSlideNum(parseInt(e.target.value) || 1)}
                  className="input-field"
                  disabled={loading}
                />
              </div>
            </div>
          )}

          {/* Size / Platform */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Size &amp; Platform</label>
            <div className="grid grid-cols-2 gap-2">
              {SIZE_PRESETS.map(opt => (
                <button
                  key={opt.ratio}
                  type="button"
                  onClick={() => { setSizeRatio(opt.ratio); setActiveTemplate(null) }}
                  disabled={loading}
                  className={`flex items-center gap-3 p-3 rounded-xl border-2 transition-all text-left ${
                    sizeRatio === opt.ratio
                      ? 'border-unified-gold bg-unified-gold/10 text-white'
                      : 'border-gray-700 bg-gray-800 text-gray-400 hover:border-gray-600'
                  }`}
                >
                  <span className="text-xl">{opt.icon}</span>
                  <div>
                    <div className="text-xs font-semibold">{opt.label} ({opt.ratio})</div>
                    <div className="text-xs text-gray-500">{opt.sublabel}</div>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Scene Description — what Unity is doing */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Unity Scene
              <span className="text-gray-500 font-normal ml-1">(optional)</span>
            </label>
            <p className="text-xs text-gray-500 mb-2">
              Describe what Unity is doing and where — this controls the visual the AI generates.
            </p>
            <input
              type="text"
              value={sceneDescription}
              onChange={e => setSceneDescription(e.target.value)}
              placeholder='e.g. "Unity cleaning a window" or "Unity installing a front door in a Westchester neighborhood"'
              className="input-field"
              disabled={loading}
            />
          </div>

          {/* Ad Copy / Context */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Ad Copy / Context <span className="text-unified-red">*</span>
            </label>
            <p className="text-xs text-gray-500 mb-2">
              The message or story behind this graphic. The headline and CTA below are what viewers actually read.
            </p>
            <textarea
              value={userPrompt}
              onChange={e => { setUserPrompt(e.target.value); setActiveTemplate(null) }}
              placeholder={
                contentType === 'tip_card'     ? 'e.g. "Westchester homes built before 1960 lose up to 30% of heating through old windows."' :
                contentType === 'before_after' ? 'e.g. "Old faded vinyl siding on a 1970s colonial \u2192 fresh white James Hardie fiber cement siding"' :
                contentType === 'carousel'     ? 'e.g. "Slide 1: 5 Signs You Need New Windows \u2014 intro"' :
                contentType === 'testimonial'  ? 'e.g. "Unified replaced all 14 windows in our White Plains home in a single day."' :
                'e.g. "Free roof inspection for Westchester homeowners. Limited spots this month."'
              }
              className="input-field h-24 resize-none"
              disabled={loading}
            />
          </div>

          {/* Headline + CTA */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">
                Headline
                <span className="text-gray-500 font-normal ml-1">(2–5 words)</span>
              </label>
              <input
                type="text"
                value={headline}
                onChange={e => setHeadline(e.target.value)}
                placeholder='e.g. "New Door. New Value."'
                className="input-field"
                disabled={loading}
                maxLength={40}
              />
              <p className="text-xs text-gray-600 mt-1">Leave blank for smart default</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">
                CTA Button Text
              </label>
              <input
                type="text"
                value={ctaText}
                onChange={e => setCtaText(e.target.value)}
                placeholder='e.g. "Get a Free Quote"'
                className="input-field"
                disabled={loading}
                maxLength={30}
              />
              <p className="text-xs text-gray-600 mt-1">Leave blank for smart default</p>
            </div>
          </div>

          {/* Image Upload (optional) */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Upload a photo{' '}
              <span className="text-gray-500 font-normal">(optional — for before/after or project photos)</span>
            </label>
            {uploadPreview ? (
              <div className="relative">
                <img src={uploadPreview} alt="Upload preview" className="w-full h-40 object-cover rounded-xl border border-gray-700" />
                <button
                  type="button"
                  onClick={clearUpload}
                  className="absolute top-2 right-2 bg-gray-900/80 hover:bg-red-900 text-white rounded-full w-7 h-7 flex items-center justify-center text-xs transition-colors"
                >
                  ✕
                </button>
                <p className="text-xs text-gray-500 mt-1">{uploadedFile?.name}</p>
              </div>
            ) : (
              <div
                onClick={() => fileInputRef.current?.click()}
                className="border-2 border-dashed border-gray-700 hover:border-gray-500 rounded-xl p-6 text-center cursor-pointer transition-colors"
              >
                <div className="text-2xl mb-2">📷</div>
                <p className="text-sm text-gray-400">Click to upload a photo</p>
                <p className="text-xs text-gray-600 mt-1">PNG, JPG up to 10 MB</p>
              </div>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/png,image/jpeg,image/jpg"
              onChange={handleFileChange}
              className="hidden"
            />
          </div>

          {/* Brand note */}
          <div className="flex items-start gap-2 bg-gray-800/60 border border-gray-700 rounded-xl p-3">
            <span className="text-lg mt-0.5">🎨</span>
            <p className="text-xs text-gray-400">
              Every graphic uses Unified brand colors (red <span className="text-unified-red font-mono">#C41230</span>, gold <span className="text-unified-gold font-mono">#F5A623</span>, charcoal <span className="font-mono text-gray-300">#1A1A1A</span>) and includes the real Unified logo automatically.
            </p>
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
            disabled={loading || !userPrompt.trim()}
            className="btn-primary w-full flex items-center justify-center gap-3"
          >
            {loading ? (
              <>
                <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                {uploadedFile ? "Generating (2-pass)..." : "Generating graphic..."}
              </>
            ) : (
              <>
                <span>🎨</span>
                Generate Unity Graphic
              </>
            )}
          </button>
          <p className="text-xs text-gray-500 text-center">
            {uploadedFile ? "With photo: 2-pass generation takes approximately 90–120 seconds." : "Graphic generation takes approximately 30–60 seconds."}
          </p>
        </form>

        {/* Live Result Preview */}
        {currentJob && (
          <div className="mt-6 border-t border-gray-800 pt-6">
            {currentJob.status === 'queued' || currentJob.status === 'running' ? (
              <div className="space-y-3">
                <div className="flex items-center gap-3">
                  <svg className="animate-spin h-5 w-5 text-unified-red" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  <span className="text-sm text-gray-300">{currentJob.step || 'Generating...'}</span>
                </div>
                {currentJob.progress !== undefined && currentJob.progress > 0 && (
                  <div className="w-full bg-gray-800 rounded-full h-2">
                    <div
                      className="bg-unified-red h-2 rounded-full transition-all duration-500"
                      style={{ width: `${currentJob.progress}%` }}
                    />
                  </div>
                )}
              </div>
            ) : currentJob.status === 'completed' && currentJob.image_url ? (
              <div className="space-y-4">
                <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">Result</h3>
                <img
                  src={`${API_BASE}${currentJob.image_url}`}
                  alt="Generated graphic"
                  className="w-full rounded-xl border border-gray-700 shadow-lg"
                />
                <button
                  onClick={handleDownload}
                  className="btn-secondary w-full flex items-center justify-center gap-2"
                >
                  <span>⬇️</span>
                  Download PNG
                </button>
              </div>
            ) : currentJob.status === 'failed' ? (
              <div className="bg-red-900/30 border border-red-800 rounded-xl p-3 text-red-300 text-sm">
                Generation failed: {currentJob.error || 'Unknown error'}
              </div>
            ) : null}
          </div>
        )}
      </div>
    </div>
  )
}
