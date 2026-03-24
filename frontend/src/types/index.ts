// ---------------------------------------------------------------------------
// Enums
// ---------------------------------------------------------------------------

export type Provider = 'openai' | 'anthropic' | 'mistral' | 'google'

export const PROVIDER_LABELS: Record<Provider, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  mistral: 'Mistral',
  google: 'Google Gemini',
}

export type JobStatus = 'queued' | 'started' | 'running' | 'completed' | 'failed'

// ---------------------------------------------------------------------------
// Model info
// ---------------------------------------------------------------------------

export interface ModelInfo {
  id: string
  label: string
  supports_structured_output: boolean
  context_window: number | null
}

// ---------------------------------------------------------------------------
// Logs
// ---------------------------------------------------------------------------

export type LogType = 'info' | 'warning' | 'error' | 'success'

export interface LogEntry {
  id: string
  type: LogType
  message: string
  timestamp: Date
}

// ---------------------------------------------------------------------------
// Job progress
// ---------------------------------------------------------------------------

export interface JobProgress {
  pages_total: number
  pages_done: number
  lines_total: number
  lines_done: number
  hyphen_pairs_total: number
  hyphen_pairs_reconciled: number
}

// ---------------------------------------------------------------------------
// SSE event data (discriminated union on `event`)
// ---------------------------------------------------------------------------

export interface SSEQueued         { event: 'queued';           job_id: string }
export interface SSEStarted        { event: 'started';          job_id: string }
export interface SSEDocumentParsed { event: 'document_parsed';  total_pages: number; total_blocks: number; total_lines: number; hyphen_pairs: number }
export interface SSEPageStarted    { event: 'page_started';     page_id: string; page_index: number; line_count: number; hyphen_pair_count: number }
export interface SSEChunkPlanned   { event: 'chunk_planned';    page_id: string; granularity: string; chunk_count: number }
export interface SSEChunkStarted   { event: 'chunk_started';    chunk_id: string; granularity: string; line_count: number; attempt: number }
export interface SSEChunkCompleted { event: 'chunk_completed';  chunk_id: string; line_count: number; hyphen_pairs_reconciled: number; attempt: number }
export interface SSERetry          { event: 'retry';            chunk_id: string; attempt: number; error: string }
export interface SSEWarning        { event: 'warning';          message: string }
export interface SSEPageCompleted  { event: 'page_completed';   page_id: string; page_index: number; corrections: number }
export interface SSECompleted      { event: 'completed';        total_lines: number; lines_modified: number; hyphen_pairs_total: number; duration_seconds: number }
export interface SSEFailed         { event: 'failed';           error: string }
export interface SSEKeepalive      { event: 'keepalive' }

export type SSEEventData =
  | SSEQueued
  | SSEStarted
  | SSEDocumentParsed
  | SSEPageStarted
  | SSEChunkPlanned
  | SSEChunkStarted
  | SSEChunkCompleted
  | SSERetry
  | SSEWarning
  | SSEPageCompleted
  | SSECompleted
  | SSEFailed
  | SSEKeepalive

// ---------------------------------------------------------------------------
// Final job stats (for DownloadButton)
// ---------------------------------------------------------------------------

export interface JobStats {
  lines_modified: number
  hyphen_pairs: number
  duration_seconds: number
}
