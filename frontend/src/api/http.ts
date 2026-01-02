export async function apiGet<T>(path: string): Promise<T> {
  const r = await fetch(path, { method: 'GET' })
  if (!r.ok) throw new Error(await r.text())
  return (await r.json()) as T
}

export async function apiPut<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error(await r.text())
  return (await r.json()) as T
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error(await r.text())
  return (await r.json()) as T
}

export async function apiDelete(path: string): Promise<void> {
  const r = await fetch(path, { method: 'DELETE' })
  if (!r.ok) throw new Error(await r.text())
}


