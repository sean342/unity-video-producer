import React from 'react'
import JobProgress from './JobProgress'

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

interface Props {
  jobs: Job[]
  activeJobId: string | null
  onSelectJob: (jobId: string) => void
}

const FORMAT_LABELS: Record<string, string> = {
  myth_or_fact: 'Myth or Fact',
  quick_tip: 'Quick Tip',
  did_you_know: 'Did You Know',
}

const STATUS_COLORS: Record<string, string> = {
  queued: 'bg-gray-700 text-gray-300',
  running: 'bg-yellow-900/50 text-yellow-400 border border-yellow-800/50',
  complete: 'bg-green-900/50 text-green-400 border border-green-800/50',
  failed: 'bg-red-900/50 text-red-400 border border-red-800/50',
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso + 'Z').getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

export default function JobList({ jobs, activeJobId, onSelectJob }: Props) {
  if (jobs.length === 0) {
    return (
      <div className="card text-center py-16">
        <div className="text-5xl mb-4">🎬</div>
        <h3 className="text-xl font-semibold text-white mb-2">No videos yet</h3>
        <p className="text-gray-400">Generate your first Unity video to get started.</p>
      </div>
    )
  }

  const activeJob = activeJobId ? jobs.find(j => j.job_id === activeJobId) : null

  return (
    <div className="space-y-6">
      {/* Active Job Progress */}
      {activeJob && (activeJob.status === 'running' || activeJob.status === 'queued') && (
        <div className="card border-unified-gold/30">
          <h3 className="text-sm font-semibold text-unified-gold uppercase tracking-wider mb-4">
            🔄 Active Generation
          </h3>
          <div className="mb-3">
            <p className="font-semibold text-white capitalize">{activeJob.topic}</p>
            <p className="text-sm text-gray-400">
              {FORMAT_LABELS[activeJob.format] || activeJob.format} · {activeJob.length}
            </p>
          </div>
          <JobProgress jobId={activeJob.job_id} />
        </div>
      )}

      {/* Job Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {jobs.map(job => (
          <div
            key={job.job_id}
            onClick={() => onSelectJob(job.job_id)}
            className={`card cursor-pointer hover:border-gray-600 transition-all ${
              activeJobId === job.job_id ? 'border-unified-red/50' : ''
            }`}
          >
            <div className="flex items-start justify-between mb-3">
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-white capitalize truncate">{job.topic || 'Untitled'}</p>
                <p className="text-sm text-gray-400">
                  {FORMAT_LABELS[job.format] || job.format} · {job.length}
                </p>
              </div>
              <span className={`text-xs px-2 py-1 rounded-full ml-3 flex-shrink-0 ${STATUS_COLORS[job.status] || 'bg-gray-700 text-gray-300'}`}>
                {job.status}
              </span>
            </div>

            {/* Progress bar for running jobs */}
            {(job.status === 'running' || job.status === 'queued') && (
              <div className="mb-3">
                <div className="w-full bg-gray-800 rounded-full h-1.5 overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-unified-red to-unified-gold rounded-full transition-all duration-500"
                    style={{ width: `${job.progress}%` }}
                  />
                </div>
                <p className="text-xs text-gray-500 mt-1">{job.step}</p>
              </div>
            )}

            {/* Video preview for complete jobs */}
            {job.status === 'complete' && job.video_url && (
              <div className="mb-3">
                <video
                  src={job.video_url}
                  className="w-full rounded-lg bg-black"
                  style={{ maxHeight: '200px' }}
                  onClick={e => e.stopPropagation()}
                  controls
                />
              </div>
            )}

            <div className="flex items-center justify-between">
              <span className="text-xs text-gray-500">{timeAgo(job.created_at)}</span>
              {job.status === 'complete' && job.video_url && (
                <a
                  href={`/download/${job.job_id}`}
                  download
                  onClick={e => e.stopPropagation()}
                  className="text-xs text-unified-gold hover:text-yellow-300 transition-colors font-medium"
                >
                  ⬇ Download
                </a>
              )}
              {job.status === 'failed' && (
                <span className="text-xs text-red-400">Generation failed</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
