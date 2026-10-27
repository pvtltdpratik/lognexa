import type {
  AccessLog,
  AccessLogDetail,
  Alert,
  AlertDetail,
  AnalysisRun,
  DatasetResult,
  Health,
  Methodology,
  Overview,
  Page,
  RiskScoreListItem,
  User,
  UserRisk,
} from "@/lib/types"
import type { AlertUpdateInput, AnalyzeInput, DatasetInput } from "@/lib/schemas"

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

async function request<T>(path: string, init?: RequestInit & { query?: Query }): Promise<T> {
  let res: Response
  try {
    res = await fetch(buildUrl(path, init?.query), {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
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
  overview: () => request<Overview>("/analytics/overview"),
  users: () => request<User[]>("/users"),
  logs: (query: Query) => request<Page<AccessLog>>("/logs", { query }),
  log: (id: number) => request<AccessLogDetail>(`/logs/${id}`),
  alerts: (query: Query) => request<Page<Alert>>("/alerts", { query }),
  alert: (id: number) => request<AlertDetail>(`/alerts/${id}`),
  updateAlert: (id: number, body: AlertUpdateInput) =>
    request<Alert>(`/alerts/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  riskScores: (query: Query) => request<Page<RiskScoreListItem>>("/risk-scores", { query }),
  userRisk: (limit = 10) => request<UserRisk[]>("/risk-scores/users", { query: { limit } }),
  methodology: () => request<Methodology>("/risk-scores/methodology"),
  analyze: (body: AnalyzeInput) => request<AnalysisRun>("/analyze", { method: "POST", body: JSON.stringify(body) }),
  runs: (limit = 10) => request<AnalysisRun[]>("/analyze/runs", { query: { limit } }),
  generateDataset: (body: DatasetInput) =>
    request<DatasetResult>("/dataset/generate", { method: "POST", body: JSON.stringify({ ...body, run_analysis: true }) }),
}
