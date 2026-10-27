import { MonitorIcon, TerminalIcon } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { humanize } from "@/lib/format"
import type { Connection, OsType } from "@/lib/types"
import { cn } from "@/lib/utils"

export function OsBadge({ os, className }: { os: OsType; className?: string }) {
  const Icon = os === "windows" ? MonitorIcon : TerminalIcon
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-xs", className)}>
      <Icon className="size-3.5 text-muted-foreground" />
      <span className="capitalize">{os}</span>
    </span>
  )
}

const connectionColor: Record<Connection, string> = {
  online: "var(--success)",
  stale: "var(--severity-medium)",
  offline: "var(--muted-foreground)",
  never: "var(--muted-foreground)",
  revoked: "var(--severity-critical)",
}

export function ConnectionBadge({ connection }: { connection: Connection }) {
  const color = connectionColor[connection]
  return (
    <Badge variant="outline" className="gap-1.5 border px-2 py-1" style={{ color, borderColor: `color-mix(in oklch, ${color} 40%, transparent)` }}>
      <span className="size-1.5 rounded-full" style={{ backgroundColor: color }} />
      {humanize(connection)}
    </Badge>
  )
}

const collectorColor: Record<string, string> = {
  ok: "var(--success)",
  disabled: "var(--muted-foreground)",
  unsupported: "var(--muted-foreground)",
  permission_denied: "var(--severity-high)",
  error: "var(--severity-critical)",
}

export function CollectorStatusBadge({ status }: { status: string }) {
  const color = collectorColor[status] ?? "var(--muted-foreground)"
  return (
    <Badge variant="outline" className="border px-1.5 py-0.5 text-[0.65rem]" style={{ color, borderColor: `color-mix(in oklch, ${color} 35%, transparent)` }}>
      {humanize(status)}
    </Badge>
  )
}
