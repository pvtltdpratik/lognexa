import type {
  Device,
  DeviceDetail,
  EndpointEvent,
  EndpointEventDetail,
  EndpointOverview,
  EnrollmentToken,
  EnrollmentTokenCreated,
  Alert,
  AlertDetail,
  Health,
  Page,
} from "@/lib/types"
import type { AlertUpdateInput } from "@/lib/schemas"

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "")

export interface FieldIssue {
  field?: string
  message: string
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: FieldIssue[] = []
  ) {
    super(message)
    this.name = "ApiError"
  }
}

type Query = Record<string, string | number | boolean | null | undefined>

function buildUrl(path: string, query?: Query) {
  const url = new URL(API_URL + path)
  for (const [k, v] of Object.entries(query ?? {})) {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v))
  }
  return url.toString()
}

const TOKEN_KEY = "lognexa.token"

/** Analyst/admin bearer token for endpoint-monitoring APIs, kept per browser. */
export const auth = {
  get(): string | null {
    try {
      return localStorage.getItem(TOKEN_KEY)
    } catch {
      return null
    }
  },
  set(token: string | null) {
    try {
      if (token) localStorage.setItem(TOKEN_KEY, token)
      else localStorage.removeItem(TOKEN_KEY)
    } catch {
      /* storage unavailable (private mode) */
    }
    listeners.forEach((l) => l())
  },
  subscribe(fn: () => void) {
    listeners.add(fn)
    return () => {
      listeners.delete(fn)
    }
  },
}
const listeners = new Set<() => void>()

async function request<T>(path: string, init?: RequestInit & { query?: Query }): Promise<T> {
  let res: Response
  const token = auth.get()
  try {
    res = await fetch(buildUrl(path, init?.query), {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...init?.headers,
      },
      cache: "no-store",
    })
  } catch {
    throw new ApiError(0, "network_error", `Cannot reach the Lognexa API at ${API_URL}. Is the backend running?`)
  }
  const body = await res.json().catch(() => null)
  if (!res.ok) {
    const err = body?.error
    throw new ApiError(
      res.status,
      err?.code ?? "http_error",
      err?.message ?? `Request failed with status ${res.status}`,
      Array.isArray(err?.details) ? err.details : []
    )
  }
  return body as T
}

/** Human-readable message including the first field-level issue, if any. */
export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    const first = e.details.find((d) => d.message)
    return first ? `${e.message}: ${first.field ? `${first.field} – ` : ""}${first.message}` : e.message
  }
  return e instanceof Error ? e.message : "Unexpected error"
}

export const api = {
  health: () => request<Health>("/health"),
  alerts: (query: Query) => request<Page<Alert>>("/alerts", { query }),
  alert: (id: number) => request<AlertDetail>(`/alerts/${id}`),
  updateAlert: (id: number, body: AlertUpdateInput) =>
    request<Alert>(`/alerts/${id}`, { method: "PATCH", body: JSON.stringify(body) }),

  // --- endpoint monitoring (require an analyst/admin token) ---
  me: () => request<{ role: "analyst" | "admin" }>("/auth/me"),
  endpointOverview: () => request<EndpointOverview>("/endpoint/overview"),
  devices: (query: Query = {}) => request<Device[]>("/devices", { query }),
  device: (id: number) => request<DeviceDetail>(`/devices/${id}`),
  revokeDevice: (id: number, reason: string) =>
    request<Device>(`/devices/${id}/revoke`, { method: "POST", body: JSON.stringify({ reason }) }),
  rotateDevice: (id: number) => request<Device>(`/devices/${id}/rotate`, { method: "POST" }),
  endpointEvents: (query: Query) => request<Page<EndpointEvent>>("/endpoint-events", { query }),
  endpointEvent: (id: number) => request<EndpointEventDetail>(`/endpoint-events/${id}`),
  enrollmentTokens: () => request<EnrollmentToken[]>("/enrollment-tokens"),
  createEnrollmentToken: (body: { label: string; max_uses: number; expires_in_hours: number }) =>
    request<EnrollmentTokenCreated>("/enrollment-tokens", { method: "POST", body: JSON.stringify(body) }),
  revokeEnrollmentToken: (id: number) =>
    request<EnrollmentToken>(`/enrollment-tokens/${id}/revoke`, { method: "POST" }),
}
