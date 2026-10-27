import { Badge } from "@/components/ui/badge"
import { humanize, severityColor, severityLabel } from "@/lib/format"
import type { AlertStatus, Severity } from "@/lib/types"
import { cn } from "@/lib/utils"

export function SeverityBadge({ severity, className }: { severity: Severity | null; className?: string }) {
  if (!severity) return <span className="text-xs text-muted-foreground">Not scored</span>
  const color = severityColor[severity]
  return (
    <Badge
      className={cn("px-2 py-1", className)}
      style={{ color, backgroundColor: `color-mix(in oklch, ${color} 14%, transparent)` }}
    >
      <span className="size-1.5 rounded-full" style={{ backgroundColor: color }} aria-hidden="true" />
      {severityLabel[severity]}
    </Badge>
  )
}

/** Horizontal 0–100 meter coloured by the score's severity band. */
export function RiskMeter({ score, severity, className }: { score: number | null; severity: Severity | null; className?: string }) {
  if (score === null || !severity) return <span className="text-xs text-muted-foreground">–</span>
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className="h-1.5 w-16 bg-muted" role="meter" aria-valuenow={score} aria-valuemin={0} aria-valuemax={100} aria-label="Risk score">
        <div className="h-full" style={{ width: `${score}%`, backgroundColor: severityColor[severity] }} />
      </div>
      <span className="tabular w-8 text-right font-mono text-xs">{score.toFixed(0)}</span>
    </div>
  )
}

const statusStyles: Record<AlertStatus, string> = {
  open: "var(--severity-critical)",
  acknowledged: "var(--severity-medium)",
  resolved: "var(--success)",
}

export function AlertStatusBadge({ status }: { status: AlertStatus }) {
  const color = statusStyles[status]
  return (
    <Badge variant="outline" className="border px-2 py-1" style={{ color, borderColor: `color-mix(in oklch, ${color} 40%, transparent)` }}>
      {humanize(status)}
    </Badge>
  )
}
