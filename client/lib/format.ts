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

/**
 * Parse a timestamp from the API. The server stores and returns naive UTC
 * ("2026-10-27T19:23:35"), which date parsers would read as local time, so a
 * value without "Z" or an offset is treated as UTC. Displayed in local time.
 */
export function parseApiDate(iso: string): Date {
  return parseISO(/(Z|[+-]\d{2}:?\d{2})$/i.test(iso) ? iso : `${iso}Z`)
}

export const formatDateTime = (iso: string) => format(parseApiDate(iso), "dd MMM yyyy, HH:mm:ss")
export const formatShort = (iso: string) => format(parseApiDate(iso), "dd MMM, HH:mm")
export const formatPrecise = (iso: string) => format(parseApiDate(iso), "dd MMM, HH:mm:ss")
export const formatDay = (iso: string) => format(parseApiDate(iso), "dd MMM")
export const formatHour = (iso: string) => format(parseApiDate(iso), "HH:mm")
export const humanize = (s: string) => s.replace(/_/g, " ")
export const nf = new Intl.NumberFormat("en-IN")
export const pct = (v: number) => `${(v * 100).toFixed(1)}%`

/** Compact relative time, e.g. "3m ago", "2h ago", "5d ago". */
export function formatRelative(iso: string): string {
  const then = parseApiDate(iso).getTime()
  const secs = Math.round((Date.now() - then) / 1000)
  if (secs < 60) return `${Math.max(0, secs)}s ago`
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`
  return `${Math.floor(secs / 86400)}d ago`
}
