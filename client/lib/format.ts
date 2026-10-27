import { format, parseISO } from "date-fns"

import type { Severity } from "@/lib/types"

export const SEVERITIES: Severity[] = ["critical", "high", "medium", "low"]

export const severityLabel: Record<Severity, string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
  critical: "Critical",
}

/** CSS variable for each severity (defined in app/globals.css). */
export const severityColor: Record<Severity, string> = {
  low: "var(--severity-low)",
  medium: "var(--severity-medium)",
  high: "var(--severity-high)",
  critical: "var(--severity-critical)",
}

export const formatDateTime = (iso: string) => format(parseISO(iso), "dd MMM yyyy, HH:mm:ss")
export const formatShort = (iso: string) => format(parseISO(iso), "dd MMM, HH:mm")
export const formatDay = (iso: string) => format(parseISO(iso), "dd MMM")
export const formatHour = (iso: string) => format(parseISO(iso), "HH:mm")
export const humanize = (s: string) => s.replace(/_/g, " ")
export const nf = new Intl.NumberFormat("en-IN")
export const pct = (v: number) => `${(v * 100).toFixed(1)}%`

/** Compact relative time, e.g. "3m ago", "2h ago", "5d ago". */
export function formatRelative(iso: string): string {
  const then = parseISO(iso).getTime()
  const secs = Math.round((Date.now() - then) / 1000)
  if (secs < 60) return `${Math.max(0, secs)}s ago`
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`
  return `${Math.floor(secs / 86400)}d ago`
}
