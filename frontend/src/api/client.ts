import type { ModelInfo, Provider } from '../types'

// proxied via vite → http://localhost:8000
const BASE = ''

// ---------------------------------------------------------------------------
// listModels
// ---------------------------------------------------------------------------

export async function listModels(provider: Provider, apiKey: string): Promise<ModelInfo[]> {
  const resp = await fetch(`${BASE}/api/providers/models`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider, api_key: apiKey }),
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error(err.detail ?? 'Failed to load models')
  }
  const data = await resp.json()
  return data.models as ModelInfo[]
}

// ---------------------------------------------------------------------------
// createJob
// ---------------------------------------------------------------------------

export async function createJob(
  files: File[],
  provider: Provider,
  apiKey: string,
  model: string,
): Promise<{ job_id: string }> {
  const form = new FormData()
  for (const f of files) {
    form.append('files', f)
  }
  form.append('provider', provider)
  form.append('api_key', apiKey)
  form.append('model', model)

  const resp = await fetch(`${BASE}/api/jobs`, {
    method: 'POST',
    body: form,
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error(err.detail ?? 'Failed to create job')
  }
  return resp.json()
}

// ---------------------------------------------------------------------------
// downloadJob — triggers browser download
// ---------------------------------------------------------------------------

export function downloadJob(jobId: string): void {
  const url = `${BASE}/api/jobs/${jobId}/download`
  const a = document.createElement('a')
  a.href = url
  a.style.display = 'none'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}
