import React, { useState, useEffect } from 'react'
import GenerateForm from './components/GenerateForm'
import JobList from './components/JobList'
import JobProgress from './components/JobProgress'

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
  const [view, setView] = useState<'generate' | 'history'>('generate')

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
        <div className="max-w-5xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-2xl">🐾</span>
            <div>
              <h1 className="text-lg font-bold text-white leading-none">Unity Video Producer</h1>
              <p className="text-xs text-gray-400">Unified Home Remodeling</p>
            </div>
          </div>
          <nav className="flex gap-2">
            <button
              onClick={() => setView('generate')}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                view === 'generate'
                  ? 'bg-unified-red text-white'
                  : 'text-gray-400 hover:text-white hover:bg-gray-800'
              }`}
            >
              Generate
            </button>
            <button
              onClick={() => setView('history')}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                view === 'history'
                  ? 'bg-unified-red text-white'
                  : 'text-gray-400 hover:text-white hover:bg-gray-800'
              }`}
            >
              History
              {jobs.filter(j => j.status === 'running').length > 0 && (
                <span className="ml-2 bg-unified-gold text-gray-900 text-xs font-bold px-1.5 py-0.5 rounded-full">
                  {jobs.filter(j => j.status === 'running').length}
                </span>
              )}
            </button>
          </nav>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-5xl mx-auto px-4 py-8">
        {view === 'generate' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            <GenerateForm
              onJobStarted={(jobId) => {
                setActiveJobId(jobId)
                setView('history')
              }}
            />
            <div className="space-y-6">
              <div className="card">
                <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">
                  About Unity
                </h3>
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
                  <p className="text-gray-500 text-xs">
                    Generation takes approximately 4–6 minutes per video.
                  </p>
                </div>
              </div>
              <div className="card">
                <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">
                  Format Guide
                </h3>
                <div className="space-y-3 text-sm">
                  <div>
                    <span className="text-unified-red font-semibold">Myth or Fact</span>
                    <p className="text-gray-400 mt-1">
                      "Myth or fact? [statement]. That's a myth/fact! [explanation]."
                    </p>
                  </div>
                  <div>
                    <span className="text-unified-gold font-semibold">Quick Tip</span>
                    <p className="text-gray-400 mt-1">
                      "Quick tip! [actionable advice about the topic]."
                    </p>
                  </div>
                  <div>
                    <span className="text-green-400 font-semibold">Did You Know</span>
                    <p className="text-gray-400 mt-1">
                      "Did you know? [surprising fact + follow-up tip]."
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {view === 'history' && (
          <JobList
            jobs={jobs}
            activeJobId={activeJobId}
            onSelectJob={setActiveJobId}
          />
        )}
      </main>
    </div>
  )
}
