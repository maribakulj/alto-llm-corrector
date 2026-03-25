import { useEffect, useRef, useState } from 'react'
import type { JobProgress, JobStatus, LogEntry, LogType, SSEEventData } from '../types'

let _logCounter = 0
function makeLog(type: LogType, message: string): LogEntry {
  return {
    id: String(++_logCounter),
    type,
    message,
    timestamp: new Date(),
  }
}

const INITIAL_PROGRESS: JobProgress = {
  pages_total: 0,
  pages_done: 0,
  lines_total: 0,
  lines_done: 0,
  hyphen_pairs_total: 0,
  hyphen_pairs_reconciled: 0,
}

interface UseJobStreamReturn {
  logs: LogEntry[]
  progress: JobProgress
  status: JobStatus | null
  isRunning: boolean
}

export function useJobStream(jobId: string | null): UseJobStreamReturn {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [progress, setProgress] = useState<JobProgress>(INITIAL_PROGRESS)
  const [status, setStatus] = useState<JobStatus | null>(null)
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!jobId) {
      // Reset all state when job is cleared (e.g. "New correction" clicked)
      setLogs([])
      setProgress(INITIAL_PROGRESS)
      setStatus(null)
      return
    }

    // Reset on new job
    setLogs([])
    setProgress(INITIAL_PROGRESS)
    setStatus('queued')

    const es = new EventSource(`/api/jobs/${jobId}/events`)
    esRef.current = es

    function handleEvent(eventName: string, rawData: string) {
      let data: Record<string, unknown>
      try {
        data = JSON.parse(rawData)
      } catch {
        data = {}
      }

      const ev = { event: eventName, ...data } as SSEEventData

      switch (ev.event) {
        case 'queued':
          setStatus('queued')
          setLogs((l) => [...l, makeLog('info', 'Job queued')])
          break

        case 'started':
          setStatus('started')
          setLogs((l) => [...l, makeLog('info', 'Correction started')])
          break

        case 'document_parsed':
          setStatus('running')
          setProgress((p) => ({
            ...p,
            pages_total: ev.total_pages,
            lines_total: ev.total_lines,
            hyphen_pairs_total: ev.hyphen_pairs,
          }))
          setLogs((l) => [
            ...l,
            makeLog(
              'info',
              `Document parsed — ${ev.total_pages} page(s), ${ev.total_lines} lines, ${ev.hyphen_pairs} hyphen pair(s)`,
            ),
          ])
          break

        case 'page_started':
          setLogs((l) => [
            ...l,
            makeLog('info', `Page ${ev.page_index + 1} started (${ev.line_count} lines)`),
          ])
          break

        case 'chunk_completed':
          setProgress((p) => ({
            ...p,
            lines_done: p.lines_done + ev.line_count,
            hyphen_pairs_reconciled: p.hyphen_pairs_reconciled + ev.hyphen_pairs_reconciled,
          }))
          setLogs((l) => [
            ...l,
            makeLog(
              'info',
              `Chunk done — ${ev.line_count} lines corrected${ev.hyphen_pairs_reconciled ? `, ${ev.hyphen_pairs_reconciled} hyphen pair(s)` : ''}`,
            ),
          ])
          break

        case 'page_completed':
          setProgress((p) => ({ ...p, pages_done: p.pages_done + 1 }))
          setLogs((l) => [
            ...l,
            makeLog(
              'info',
              `Page ${ev.page_index + 1} completed — ${ev.corrections} correction(s)`,
            ),
          ])
          break

        case 'retry':
          setLogs((l) => [
            ...l,
            makeLog('warning', `Retry (attempt ${ev.attempt}) — ${ev.error}`),
          ])
          break

        case 'warning':
          setLogs((l) => [...l, makeLog('warning', ev.message)])
          break

        case 'completed':
          setStatus('completed')
          setProgress((p) => ({
            ...p,
            lines_done: ev.total_lines,
            hyphen_pairs_reconciled: ev.hyphen_pairs_total,
          }))
          setLogs((l) => [
            ...l,
            makeLog(
              'success',
              `Completed — ${ev.lines_modified} line(s) modified, ${ev.hyphen_pairs_total} hyphen pair(s), ${ev.duration_seconds.toFixed(1)}s`,
            ),
          ])
          es.close()
          break

        case 'failed':
          setStatus('failed')
          setLogs((l) => [...l, makeLog('error', `Failed: ${ev.error}`)])
          es.close()
          break

        case 'keepalive':
          break
      }
    }

    const EVENTS = [
      'queued', 'started', 'document_parsed', 'page_started',
      'chunk_planned', 'chunk_started', 'chunk_completed',
      'retry', 'warning', 'page_completed', 'completed', 'failed', 'keepalive',
    ]

    for (const name of EVENTS) {
      es.addEventListener(name, (e: MessageEvent) => handleEvent(name, e.data))
    }

    es.onerror = () => {
      setStatus((s) => (s === 'completed' || s === 'failed' ? s : 'failed'))
      setLogs((l) => [...l, makeLog('error', 'Connection to server lost')])
      es.close()
    }

    return () => {
      es.close()
      esRef.current = null
    }
  }, [jobId])

  const isRunning = status === 'queued' || status === 'started' || status === 'running'

  return { logs, progress, status, isRunning }
}
