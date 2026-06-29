import React, { useState } from 'react'
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
  onDeleteJob: (jobId: string) => void
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
export default function JobList({ jobs, activeJobId, onSelectJob, onDeleteJob }: Props) {
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<string | null>(null)

  const handleDeleteClick = (e: React.MouseEvent, jobId: string) => {
    e.stopPropagation()
    setConfirmDeleteId(jobId)
  }

  const handleConfirmDelete = async (e: React.MouseEvent, jobId: string) => {
    e.stopPropagation()
    setDeleting(jobId)
    try {
      const r = await fetch(`/jobs/${jobId}`, { method: 'DELETE' })
      if (r.ok) {
        onDeleteJob(jobId)
      }
    } catch {}
    setDeleting(null)
    setConfirmDeleteId(null)
  }

  const handleCancelDelete = (e: React.MouseEvent) => {
    e.stopPropagation()
    setConfirmDeleteId(null)
  }

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
              <div className="flex items-center gap-3">
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
                {/* Delete button — only for complete or failed jobs */}
                {(job.status === 'complete' || job.status === 'failed') && (
                  confirmDeleteId === job.job_id ? (
                    <span className="flex items-center gap-1.5" onClick={e => e.stopPropagation()}>
                      <span className="text-xs text-gray-300">Delete?</span>
                      <button
                        onClick={e => handleConfirmDelete(e, job.job_id)}
                        disabled={deleting === job.job_id}
                        className="text-xs text-red-400 hover:text-red-300 font-semibold disabled:opacity-50"
                      >
                        {deleting === job.job_id ? '...' : 'Yes'}
                      </button>
                      <button
                        onClick={handleCancelDelete}
                        className="text-xs text-gray-400 hover:text-gray-200"
                      >
                        No
                      </button>
                    </span>
                  ) : (
                    <button
                      onClick={e => handleDeleteClick(e, job.job_id)}
                      className="text-gray-600 hover:text-red-400 transition-colors"
                      title="Delete video"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                        <path fillRule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clipRule="evenodd" />
                      </svg>
                    </button>
                  )
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
