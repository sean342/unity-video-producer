import React, { useState, useEffect } from 'react'

interface Job {
  job_id: string
  status: string
  step: string
  progress: number
  error?: string
  video_url?: string
}

interface Props {
  jobId: string
  onComplete?: (job: Job) => void
}

const STEP_ICONS: Record<string, string> = {
  'Queued': '⏳',
  'Writing script': '✍️',
  'Generating voice': '🎙️',
  'Generating keyframe': '🖼️',
  'Animating Unity': '🎬',
  'Rendering captions': '💬',
  'Assembling final video': '🎞️',
  'Complete': '✅',
  'Failed': '❌',
}

function getStepIcon(step: string): string {
  for (const [key, icon] of Object.entries(STEP_ICONS)) {
    if (step.startsWith(key)) return icon
  }
  return '⚙️'
}

export default function JobProgress({ jobId, onComplete }: Props) {
  const [job, setJob] = useState<Job | null>(null)

  useEffect(() => {
    let interval: ReturnType<typeof setInterval>

    const poll = async () => {
      try {
        const r = await fetch(`/status/${jobId}`)
        if (!r.ok) return
        const data: Job = await r.json()
        setJob(data)
        if (data.status === 'complete' || data.status === 'failed') {
          clearInterval(interval)
          if (data.status === 'complete' && onComplete) onComplete(data)
        }
      } catch {}
    }

    poll()
    interval = setInterval(poll, 3000)
    return () => clearInterval(interval)
  }, [jobId])

  if (!job) {
    return (
      <div className="flex items-center gap-3 text-gray-400 p-4">
        <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        Loading job status...
      </div>
    )
  }

  const isRunning = job.status === 'running' || job.status === 'queued'
  const isComplete = job.status === 'complete'
  const isFailed = job.status === 'failed'

  return (
    <div className="space-y-4">
      {/* Status Header */}
      <div className="flex items-center gap-3">
        <span className="text-2xl">{getStepIcon(job.step)}</span>
        <div className="flex-1">
          <p className="font-semibold text-white">{job.step}</p>
          <p className="text-sm text-gray-400">
            {isRunning && 'Processing...'}
            {isComplete && 'Video ready!'}
            {isFailed && 'Generation failed'}
          </p>
        </div>
        {isRunning && (
          <svg className="animate-spin h-5 w-5 text-unified-gold" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
        )}
      </div>

      {/* Progress Bar */}
      <div className="w-full bg-gray-800 rounded-full h-3 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${
            isFailed
              ? 'bg-red-500'
              : isComplete
              ? 'bg-green-500'
              : 'bg-gradient-to-r from-unified-red to-unified-gold'
          }`}
          style={{ width: `${job.progress}%` }}
        />
      </div>
      <p className="text-xs text-gray-500 text-right">{job.progress}%</p>

      {/* Pipeline Steps */}
      <div className="grid grid-cols-3 gap-2 text-xs">
        {[
          { label: 'Script', threshold: 5 },
          { label: 'Voice', threshold: 15 },
          { label: 'Keyframe', threshold: 28 },
          { label: 'Animation', threshold: 35 },
          { label: 'Captions', threshold: 80 },
          { label: 'Assembly', threshold: 90 },
        ].map(s => (
          <div
            key={s.label}
            className={`flex items-center gap-1.5 px-2 py-1.5 rounded-lg ${
              job.progress >= s.threshold
                ? 'bg-green-900/30 text-green-400 border border-green-800/50'
                : 'bg-gray-800 text-gray-500 border border-gray-700'
            }`}
          >
            <span>{job.progress >= s.threshold ? '✓' : '○'}</span>
            <span>{s.label}</span>
          </div>
        ))}
      </div>

      {/* Error */}
      {isFailed && job.error && (
        <div className="bg-red-900/30 border border-red-800 rounded-xl p-3 text-red-300 text-sm">
          <p className="font-semibold mb-1">Error</p>
          <p className="font-mono text-xs">{job.error}</p>
        </div>
      )}

      {/* Download */}
      {isComplete && job.video_url && (
        <div className="space-y-3">
          <video
            src={job.video_url}
            controls
            className="w-full rounded-xl bg-black"
            style={{ maxHeight: '400px' }}
          />
          <a
            href={`/download/${job.job_id}`}
            download
            className="btn-primary w-full flex items-center justify-center gap-2 no-underline"
          >
            <span>⬇️</span>
            Download MP4
          </a>
        </div>
      )}
    </div>
  )
}
