// Response types mirroring server/app/schemas.py

export type Severity = "low" | "medium" | "high" | "critical"
export type AlertStatus = "open" | "acknowledged" | "resolved"

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  pages: number
}

export interface User {
  id: number
  username: string
  full_name: string
  email: string
  department: string
  role: string
  home_country: string
  home_city: string
  shift: string
}

export interface TriggeredRule {
  code: string
  name: string
  category: string
  points: number
  reason: string
}

export interface TopFeature {
  feature: string
  label: string
  value: number
  z_score: number
}

export interface RiskScore {
  id: number
  log_id: number
  run_id: number
  rule_score: number
  ml_score: number
  ml_is_anomaly: boolean
  risk_score: number
  severity: Severity
  triggered_rules: TriggeredRule[]
  features: Record<string, number | string>
  top_features: TopFeature[]
  explanation: string
  created_at: string
}

export interface RiskScoreListItem {
  id: number
  log_id: number
  user_id: number
  username: string
  timestamp: string
  action: string
  resource: string
  rule_score: number
  ml_score: number
  risk_score: number
  severity: Severity
  rule_codes: string[]
}

export interface AccessLog {
  id: number
  user_id: number
  username: string
  timestamp: string
  ip_address: string
  country: string
  city: string
  device: string
  action: string
  resource: string
  resource_sensitivity: string
  status: string
  risk_score: number | null
  severity: Severity | null
  has_alert: boolean
}

export interface AccessLogDetail extends AccessLog {
  injected_anomaly: string | null
  user: User
  risk: RiskScore | null
  alert: { id: number; status: AlertStatus; severity: Severity; title: string } | null
}

export interface Alert {
  id: number
  log_id: number
  user_id: number
  username: string
  severity: Severity
  risk_score: number
  title: string
  description: string
  status: AlertStatus
  resolution_note: string | null
  resolved_by: string | null
  resolved_at: string | null
  created_at: string
  updated_at: string
  timestamp: string
  resource: string
  ip_address: string
}

export interface AlertDetail extends Alert {
  log: AccessLog
  risk: RiskScore | null
}

export interface Prf {
  tp: number
  fp: number
  fn: number
  tn: number
  precision: number
  recall: number
  f1: number
}

export interface RunMetrics {
  labelled_anomalies?: number
  total_events?: number
  combined?: Prf
  rules_only?: Prf
  ml_only?: Prf
  per_type?: Record<string, { injected: number; detected: number; recall: number }>
  caveat?: string
  note?: string
}

export interface AnalysisRun {
  id: number
  started_at: string
  completed_at: string | null
  status: string
  logs_analyzed: number
  alerts_created: number
  parameters: { contamination?: number; alert_threshold?: number; rule_weight?: number; seed?: number }
  metrics: RunMetrics
  error: string | null
}

export interface UserRisk {
  user_id: number
  username: string
  full_name: string
  department: string
  events: number
  avg_risk: number
  max_risk: number
  high_risk_events: number
  open_alerts: number
}

export interface Overview {
  total_logs: number
  total_users: number
  failed_events: number
  open_alerts: number
  acknowledged_alerts: number
  resolved_alerts: number
  avg_risk: number
  severity_counts: Record<Severity, number>
  alert_severity_counts: Record<Severity, number>
  rule_hits: { code: string; name: string; category: string; count: number }[]
  daily: { date: string; events: number; failed: number; alerts: number; avg_risk: number }[]
  hourly: { hour: number; events: number; high_risk: number }[]
  top_users: UserRisk[]
  latest_run: AnalysisRun | null
  period_start: string | null
  period_end: string | null
}

export interface Health {
  status: "ok" | "degraded"
  database: "ok" | "error"
  database_backend: string
  version: string
  counts: Record<string, number> | null
  detail: string | null
}

export interface Methodology {
  formula: string
  default_rule_weight: number
  agreement_bonus: number
  severity_bands: { min: number; severity: Severity }[]
  rules: { code: string; name: string; category: string; points: number }[]
}

export interface DatasetResult {
  users: number
  logs: number
  injected_anomalies: number
  analysis: AnalysisRun | null
}
