import React, { useState, useEffect } from 'react'
import GenerateForm from './components/GenerateForm'
import GraphicsForm from './components/GraphicsForm'
import JobList from './components/JobList'
import KeyframeLibrary from './components/KeyframeLibrary'
import ImagesPage from './components/ImagesPage'
import SettingsPage from './components/SettingsPage'

const APP_PASSWORD = import.meta.env.VITE_APP_PASSWORD || 'unified2024'

interface Job {
  job_id: string
  status: string
  step: string
  progress: number
  topic: string
  format: string
  length: string
  created_at: string
  video_url: string | null
}

export default function App() {
  const [authed, setAuthed] = useState(false)
  const [password, setPassword] = useState('')
  const [authError, setAuthError] = useState('')
  const [activeJobId, setActiveJobId] = useState<string | null>(null)
  const [jobs, setJobs] = useState<Job[]>([])
  const [view, setView] = useState<'generate' | 'library' | 'images' | 'graphics' | 'history' | 'settings'>('generate')

  // Pre-selected keyframe from Library → Generate
  const [selectedKeyframe, setSelectedKeyframe] = useState<{ filename: string; label: string } | null>(null)

  // Pre-filled graphics data ported from Images page
  const [portedGraphicsScene, setPortedGraphicsScene] = useState<string | null>(null)

  // Check session
  useEffect(() => {
    const saved = sessionStorage.getItem('uvp_auth')
    if (saved === 'true') setAuthed(true)
  }, [])

  // Poll jobs list
  useEffect(() => {
    if (!authed) return
    const fetchJobs = async () => {
      try {
        const r = await fetch('/jobs')
        if (r.ok) setJobs(await r.json())
      } catch {}
    }
    fetchJobs()
    const interval = setInterval(fetchJobs, 5000)
    return () => clearInterval(interval)
  }, [authed])

  const handleAuth = (e: React.FormEvent) => {
    e.preventDefault()
    if (password === APP_PASSWORD) {
      setAuthed(true)
      sessionStorage.setItem('uvp_auth', 'true')
    } else {
      setAuthError('Incorrect password. Please try again.')
    }
  }

  const handleUseKeyframe = (filename: string, label: string) => {
    setSelectedKeyframe({ filename, label })
    setView('generate')
  }

  // Called when user ports an image from Images page → Graphics
  const handlePortToGraphics = (_imageUrl: string, sceneDescription: string) => {
    setPortedGraphicsScene(sceneDescription)
    setView('graphics')
  }

  // Called when user ports an image from Images page → Library
  const handlePortToLibrary = (_filename: string, _label: string) => {
    setView('library')
  }
  // Delete a video job from history
  const handleDeleteJob = async (jobId: string) => {
    try {
      const r = await fetch(`/jobs/${jobId}`, { method: 'DELETE' })
      if (r.ok) {
        setJobs(prev => prev.filter(j => j.job_id !== jobId))
        if (activeJobId === jobId) setActiveJobId(null)
      }
    } catch {}
  }

  if (!authed) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-950 px-4">
        <div className="card w-full max-w-md">
          <div className="text-center mb-8">
            <div className="text-5xl mb-4">🐾</div>
            <h1 className="text-2xl font-bold text-white">Unity Video Producer</h1>
            <p className="text-gray-400 mt-2">Unified Home Remodeling — Internal Tool</p>
          </div>
          <form onSubmit={handleAuth} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Team Password
              </label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="Enter team password"
                className="input-field"
                autoFocus
              />
            </div>
            {authError && (
              <p className="text-red-400 text-sm">{authError}</p>
            )}
            <button type="submit" className="btn-primary w-full">
              Sign In
            </button>
          </form>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-950">
      {/* Header */}
      <header className="bg-gray-900 border-b border-gray-800 sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-2xl">🐾</span>
            <div>
              <h1 className="text-lg font-bold text-white leading-none">Unity Video Producer</h1>
              <p className="text-xs text-gray-400">Unified Home Remodeling</p>
            </div>
          </div>
          <nav className="flex gap-1 flex-wrap">
            {(
              [
                { id: 'generate', label: 'Generate', icon: '🎬' },
                { id: 'library',  label: 'Library',  icon: '🖼️' },
                { id: 'images',   label: 'Images',   icon: '🐕' },
                { id: 'graphics', label: 'Graphics', icon: '🎨' },
                { id: 'history',  label: 'Video History',  icon: '📋' },
                { id: 'settings', label: 'Settings', icon: '⚙️' },
              ] as const
            ).map(tab => (
              <button
                key={tab.id}
                onClick={() => setView(tab.id)}
                className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-1.5 ${
                  view === tab.id
                    ? 'bg-unified-red text-white'
                    : 'text-gray-400 hover:text-white hover:bg-gray-800'
                }`}
              >
                {tab.icon && <span className="text-base">{tab.icon}</span>}
                {tab.label}
                {tab.id === 'history' && jobs.filter(j => j.status === 'running').length > 0 && (
                  <span className="bg-unified-gold text-gray-900 text-xs font-bold px-1.5 py-0.5 rounded-full">
                    {jobs.filter(j => j.status === 'running').length}
                  </span>
                )}
                {/* Dot indicator when ported data is waiting */}
                {tab.id === 'graphics' && portedGraphicsScene && view !== 'graphics' && (
                  <span className="w-2 h-2 bg-purple-400 rounded-full" />
                )}
              </button>
            ))}
          </nav>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-6xl mx-auto px-4 py-8">

        {/* ── Generate ── */}
        {view === 'generate' && (
          <>
            {selectedKeyframe && (
              <div className="mb-6 flex items-center gap-3 bg-unified-red/10 border border-unified-red/30 rounded-xl px-4 py-3">
                <img
                  src={`/keyframes/${selectedKeyframe.filename}`}
                  alt={selectedKeyframe.label}
                  className="w-10 h-14 object-cover rounded-lg"
                />
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-gray-400">Keyframe pre-selected from Library</p>
                  <p className="text-sm font-semibold text-white truncate">{selectedKeyframe.label}</p>
                </div>
                <button
                  onClick={() => setSelectedKeyframe(null)}
                  className="text-gray-500 hover:text-white text-sm"
                >
                  ✕ Clear
                </button>
              </div>
            )}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
              <GenerateForm
                onJobStarted={(jobId) => {
                  setActiveJobId(jobId)
                  setView('history')
                }}
                preselectedKeyframe={selectedKeyframe?.filename}
                onKeyframeClear={() => setSelectedKeyframe(null)}
              />
              <div className="space-y-6">
                <div className="card">
                  <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">About Unity</h3>
                  <div className="space-y-3 text-sm text-gray-300">
                    <p>
                      <span className="text-unified-gold font-semibold">Unity</span> is Unified's
                      golden retriever mascot — a friendly pup with a red bandana and tool belt who
                      delivers home improvement tips.
                    </p>
                    <p>
                      Each video is automatically generated using ElevenLabs voice, Kling Avatar v2
                      lip-sync animation, and professional caption overlays.
                    </p>
                    <p className="text-gray-500 text-xs">Generation takes approximately 4–6 minutes per video.</p>
                  </div>
                </div>
                <div className="card">
                  <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">Format Guide</h3>
                  <div className="space-y-3 text-sm">
                    <div>
                      <span className="text-unified-red font-semibold">Myth or Fact</span>
                      <p className="text-gray-400 mt-1">"Myth or fact? [statement]. That's a myth/fact! [explanation]."</p>
                    </div>
                    <div>
                      <span className="text-unified-gold font-semibold">Quick Tip</span>
                      <p className="text-gray-400 mt-1">"Quick tip! [actionable advice about the topic]."</p>
                    </div>
                    <div>
                      <span className="text-green-400 font-semibold">Did You Know</span>
                      <p className="text-gray-400 mt-1">"Did you know? [surprising fact + follow-up tip]."</p>
                    </div>
                  </div>
                </div>
                <div className="card">
                  <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">Quick Actions</h3>
                  <div className="space-y-2">
                    <button
                      onClick={() => setView('library')}
                      className="w-full flex items-center gap-3 bg-gray-800 hover:bg-gray-700 rounded-xl px-4 py-3 transition-colors text-left"
                    >
                      <span className="text-2xl">🖼️</span>
                      <div>
                        <p className="text-sm font-semibold text-white">Browse Keyframe Library</p>
                        <p className="text-xs text-gray-400">Pick a scene for your next video</p>
                      </div>
                    </button>
                    <button
                      onClick={() => setView('images')}
                      className="w-full flex items-center gap-3 bg-gray-800 hover:bg-gray-700 rounded-xl px-4 py-3 transition-colors text-left"
                    >
                      <span className="text-2xl">🐕</span>
                      <div>
                        <p className="text-sm font-semibold text-white">Generate Unity Image</p>
                        <p className="text-xs text-gray-400">Clean image for social media</p>
                      </div>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </>
        )}

        {/* ── Library ── */}
        {view === 'library' && (
          <KeyframeLibrary onUseKeyframe={handleUseKeyframe} />
        )}

        {/* ── Images ── */}
        {view === 'images' && (
          <ImagesPage
            onPortToGraphics={handlePortToGraphics}
            onPortToLibrary={handlePortToLibrary}
          />
        )}

        {/* ── Graphics ── */}
        {view === 'graphics' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            <GraphicsForm
              portedScene={portedGraphicsScene}
              onPortedSceneConsumed={() => setPortedGraphicsScene(null)}
            />
            <div className="space-y-6">
              {portedGraphicsScene && (
                <div className="bg-purple-900/30 border border-purple-500/40 rounded-xl px-4 py-3">
                  <p className="text-xs text-purple-300 font-medium">📥 Scene ported from Images page</p>
                  <p className="text-sm text-white mt-0.5 truncate">"{portedGraphicsScene}"</p>
                  <button
                    onClick={() => setPortedGraphicsScene(null)}
                    className="text-xs text-purple-400 hover:text-purple-200 mt-1"
                  >
                    Clear
                  </button>
                </div>
              )}
              <div className="card">
                <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">Graphic Types</h3>
                <div className="space-y-3 text-sm">
                  <div>
                    <span className="text-unified-red font-semibold">💡 Tip Card</span>
                    <p className="text-gray-400 mt-1">Educational fact or tip with Unity pointing at the content.</p>
                  </div>
                  <div>
                    <span className="text-unified-gold font-semibold">🏠 Before / After</span>
                    <p className="text-gray-400 mt-1">Split layout showing project transformation.</p>
                  </div>
                  <div>
                    <span className="text-green-400 font-semibold">📋 Carousel</span>
                    <p className="text-gray-400 mt-1">Generate each slide individually for a multi-part series.</p>
                  </div>
                  <div>
                    <span className="text-blue-400 font-semibold">⭐ Testimonial</span>
                    <p className="text-gray-400 mt-1">Customer quote with star rating and Unity giving a thumbs up.</p>
                  </div>
                  <div>
                    <span className="text-purple-400 font-semibold">📣 Promotional</span>
                    <p className="text-gray-400 mt-1">Bold offer or seasonal announcement with energetic Unity.</p>
                  </div>
                </div>
              </div>
              <div className="card">
                <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">Platform Sizes</h3>
                <div className="space-y-2 text-sm text-gray-400">
                  <p><span className="text-white font-medium">1:1 Square</span> — Instagram &amp; Facebook Feed</p>
                  <p><span className="text-white font-medium">4:5 Portrait</span> — Instagram &amp; Facebook Feed</p>
                  <p><span className="text-white font-medium">9:16 Vertical</span> — Stories, Reels &amp; TikTok</p>
                  <p><span className="text-white font-medium">16:9 Landscape</span> — Facebook &amp; YouTube Cover</p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ── Settings ── */}
        {view === 'settings' && <SettingsPage />}

        {/* ── History ── */}
        {view === 'history' && (
          <JobList
            jobs={jobs}
            activeJobId={activeJobId}
            onSelectJob={setActiveJobId}
            onDeleteJob={handleDeleteJob}
          />
        )}
      </main>
    </div>
  )
}
