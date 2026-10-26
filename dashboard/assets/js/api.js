// Fetch wrapper for the FastAPI JSON API (/api/*, api/main.py).

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

/** GET api/<endpoint>?params -> the response's `data`. Throws ApiError with a readable message. */
export async function api(endpoint, params = {}, { signal } = {}) {
  const url = new URL(`api/${endpoint}`, document.baseURI);
  for (const [k, v] of Object.entries(params)) {
    if (v !== null && v !== undefined && v !== '') url.searchParams.set(k, v);
  }
  let response;
  try {
    response = await fetch(url, { headers: { Accept: 'application/json' }, signal });
  } catch (err) {
    if (err.name === 'AbortError') throw err;
    throw new ApiError('Cannot reach the dashboard server. Is it running? (asteroid-watch serve)', 0);
  }
  let body;
  try {
    body = await response.json();
  } catch {
    throw new ApiError(`Unexpected response from ${endpoint} (HTTP ${response.status}).`, response.status);
  }
  if (!response.ok) throw new ApiError(body.error || `HTTP ${response.status}`, response.status);
  return body.data;
}
