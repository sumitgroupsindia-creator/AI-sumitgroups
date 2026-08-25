import { clearTokens, getAccessToken, getRefreshToken, setTokens } from '@/lib/auth-storage';

export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? '/api/v1';

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public requestId?: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown;
  auth?: boolean;
  raw?: boolean;
}

let refreshPromise: Promise<boolean> | null = null;

async function refreshAccessToken(): Promise<boolean> {
  // Collapse concurrent 401s into a single refresh so a page with several parallel
  // requests doesn't fire a burst of refreshes and invalidate its own tokens.
  if (refreshPromise) return refreshPromise;

  refreshPromise = (async () => {
    const refresh_token = getRefreshToken();
    if (!refresh_token) return false;
    try {
      const res = await fetch(`${API_BASE}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token }),
      });
      if (!res.ok) {
        clearTokens();
        return false;
      }
      const tokens = await res.json();
      setTokens(tokens.access_token, tokens.refresh_token);
      return true;
    } catch {
      clearTokens();
      return false;
    } finally {
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

async function parseError(res: Response): Promise<ApiError> {
  let message = 'Something went wrong. Please try again.';
  let requestId: string | undefined;
  try {
    const data = await res.json();
    if (typeof data?.error === 'string') message = data.error;
    if (Array.isArray(data?.details) && data.details.length > 0) {
      const first = data.details[0];
      if (first?.msg) message = first.msg;
    }
    requestId = data?.request_id;
  } catch {
    // Non-JSON error body (proxy timeout, etc.) — keep the generic message.
  }
  return new ApiError(res.status, message, requestId);
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, auth = true, raw = false, headers, ...rest } = options;

  const send = async (): Promise<Response> => {
    const finalHeaders = new Headers(headers);
    if (body !== undefined && !(body instanceof FormData)) {
      finalHeaders.set('Content-Type', 'application/json');
    }
    if (auth) {
      const token = getAccessToken();
      if (token) finalHeaders.set('Authorization', `Bearer ${token}`);
    }
    return fetch(`${API_BASE}${path}`, {
      ...rest,
      headers: finalHeaders,
      body: body instanceof FormData ? body : body !== undefined ? JSON.stringify(body) : undefined,
    });
  };

  let res = await send();

  if (res.status === 401 && auth) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      res = await send();
    }
  }

  if (!res.ok) throw await parseError(res);
  if (raw || res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

/** Fetches an authenticated binary file and returns an object URL the browser can display. */
export async function fetchAuthedBlobUrl(path: string): Promise<string> {
  const token = getAccessToken();
  const res = await fetch(`${API_BASE}${path.replace(/^\/api\/v1/, '')}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!res.ok) throw await parseError(res);
  return URL.createObjectURL(await res.blob());
}
