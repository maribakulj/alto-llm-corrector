import { useState } from 'react'
import { createJob } from './api/client'
import { ApiKeyInput } from './components/ApiKeyInput'
import { DownloadButton } from './components/DownloadButton'
import { FileUpload } from './components/FileUpload'
import { JobProgressPanel } from './components/JobProgress'
import { LogPanel } from './components/LogPanel'
import { ModelSelector } from './components/ModelSelector'
import { ProviderSelector } from './components/ProviderSelector'
import { useJobStream } from './hooks/useJobStream'
import { useModels } from './hooks/useModels'
import type { JobStats, Provider } from './types'

export default function App() {
  // Upload state
  const [files, setFiles] = useState<File[]>([])

  // Config state
  const [provider, setProvider] = useState<Provider | null>(null)
  const [apiKey, setApiKey] = useState('')
  const [selectedModel, setSelectedModel] = useState<string | null>(null)

  // Job state
  const [jobId, setJobId] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [finalStats, setFinalStats] = useState<JobStats | null>(null)

  // Models
  const { models, loading: modelsLoading, error: modelsError, loadModels, reset: resetModels } = useModels()

  // SSE stream
  const { logs, progress, status, isRunning } = useJobStream(jobId)

  // Capture completed stats from the SSE logs
  // (we pull them from the last 'success' log message via progress state)
  // Actually we compute stats from progress + last completed event
  const isDone = status === 'completed'
  const isFailed = status === 'failed'

  // Capture stats when completed
  if (isDone && !finalStats && progress.lines_total > 0) {
    setFinalStats({
      lines_modified: 0, // will be set via log parsing below
      hyphen_pairs: progress.hyphen_pairs_reconciled,
      duration_seconds: 0,
    })
  }

  const canPlay =
    files.length > 0 &&
    provider !== null &&
    apiKey.trim().length > 0 &&
    selectedModel !== null &&
    !isRunning &&
    !isDone

  async function handlePlay() {
    if (!canPlay || !provider || !selectedModel) return
    setSubmitting(true)
    setSubmitError(null)
    setFinalStats(null)
    try {
      const res = await createJob(files, provider, apiKey, selectedModel)
      setJobId(res.job_id)
    } catch (err: unknown) {
      setSubmitError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setSubmitting(false)
    }
  }

  function handleReset() {
    setFiles([])
    setJobId(null)
    setSubmitError(null)
    setFinalStats(null)
    resetModels()
    setSelectedModel(null)
  }

  // Extract stats from the success log entry when completed
  const completedLog = logs.find((l) => l.type === 'success' && l.message.startsWith('Completed'))
  const displayStats: JobStats | null = completedLog
    ? (() => {
        const m = completedLog.message.match(/(\d+) line\(s\) modified.*?(\d+) hyphen.*?([\d.]+)s/)
        if (m) {
          return {
            lines_modified: parseInt(m[1]),
            hyphen_pairs: parseInt(m[2]),
            duration_seconds: parseFloat(m[3]),
          }
        }
        return finalStats
      })()
    : finalStats

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100">
      {/* Header */}
      <header className="border-b border-slate-700/50 bg-slate-900/80 backdrop-blur sticky top-0 z-10">
        <div className="max-w-2xl mx-auto px-4 py-4 flex items-center justify-between">
          <div>
            <h1 className="font-serif text-xl font-bold text-slate-100 tracking-tight">
              ALTO LLM Corrector
            </h1>
            <p className="font-mono text-xs text-slate-500 mt-0.5">
              Post-OCR correction via LLM
            </p>
          </div>
          {(isDone || isFailed) && (
            <button
              onClick={handleReset}
              className="font-mono text-xs text-amber-400 border border-amber-500/40
                         hover:bg-amber-500/10 rounded px-3 py-1.5 transition-colors"
            >
              New correction
            </button>
          )}
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-4 py-8 space-y-6">

        {/* 1. File Upload */}
        <section>
          <h2 className="font-serif text-base font-semibold text-slate-300 mb-3 flex items-center gap-2">
            <span className="font-mono text-amber-500 text-xs">01</span>
            Upload ALTO files
          </h2>
          <FileUpload onFilesChange={setFiles} disabled={isRunning || isDone} />
        </section>

        {/* 2. Configuration */}
        <section>
          <h2 className="font-serif text-base font-semibold text-slate-300 mb-3 flex items-center gap-2">
            <span className="font-mono text-amber-500 text-xs">02</span>
            Configuration
          </h2>
          <div className="space-y-3">
            <ProviderSelector
              value={provider}
              onChange={(p) => { setProvider(p); setSelectedModel(null); resetModels() }}
              disabled={isRunning || isDone}
            />
            <ApiKeyInput
              value={apiKey}
              onChange={setApiKey}
              disabled={isRunning || isDone}
            />
            {modelsError && (
              <p className="font-mono text-xs text-red-400 bg-red-900/20 border border-red-800/40 rounded px-3 py-2">
                {modelsError}
              </p>
            )}
            <ModelSelector
              models={models}
              loading={modelsLoading}
              selectedModel={selectedModel}
              onLoad={() => provider && apiKey && loadModels(provider, apiKey)}
              onSelect={setSelectedModel}
              disabled={!provider || !apiKey.trim() || isRunning || isDone}
            />
          </div>
        </section>

        {/* 3. Play button */}
        <section>
          {submitError && (
            <p className="font-mono text-xs text-red-400 bg-red-900/20 border border-red-800/40 rounded px-3 py-2 mb-3">
              {submitError}
            </p>
          )}
          <button
            onClick={handlePlay}
            disabled={!canPlay || submitting}
            className={[
              'w-full flex items-center justify-center gap-3 py-4 rounded-lg font-mono font-bold',
              'text-sm uppercase tracking-widest transition-all',
              canPlay && !submitting
                ? 'bg-amber-500 hover:bg-amber-400 text-slate-900 shadow-lg shadow-amber-500/20'
                : 'bg-slate-700 text-slate-500 cursor-not-allowed',
            ].join(' ')}
          >
            {submitting ? (
              <>
                <span className="w-4 h-4 border-2 border-slate-500 border-t-transparent rounded-full animate-spin" />
                Uploading…
              </>
            ) : (
              <>
                <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM9.555 7.168A1 1 0 008 8v4a1 1 0 001.555.832l3-2a1 1 0 000-1.664l-3-2z" clipRule="evenodd" />
                </svg>
                Start correction
              </>
            )}
          </button>
        </section>

        {/* 4. Progress — shown once job started */}
        {(jobId || isRunning || isDone || isFailed) && (
          <section>
            <h2 className="font-serif text-base font-semibold text-slate-300 mb-3 flex items-center gap-2">
              <span className="font-mono text-amber-500 text-xs">03</span>
              Progress
            </h2>
            <JobProgressPanel progress={progress} status={status} />
          </section>
        )}

        {/* 5. Logs */}
        {logs.length > 0 && (
          <section>
            <h2 className="font-serif text-base font-semibold text-slate-300 mb-3 flex items-center gap-2">
              <span className="font-mono text-amber-500 text-xs">04</span>
              Event log
            </h2>
            <LogPanel logs={logs} />
          </section>
        )}

        {/* 6. Download */}
        {isDone && jobId && (
          <section>
            <h2 className="font-serif text-base font-semibold text-slate-300 mb-3 flex items-center gap-2">
              <span className="font-mono text-amber-500 text-xs">05</span>
              Download
            </h2>
            <DownloadButton jobId={jobId} stats={displayStats} />
          </section>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800 mt-16 py-6">
        <p className="font-mono text-xs text-slate-700 text-center">
          ALTO LLM Corrector — post-OCR correction only, no OCR, no resegmentation
        </p>
      </footer>
    </div>
  )
}
