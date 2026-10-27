import { BrainCircuitIcon, ListChecksIcon, SigmaIcon } from "lucide-react"

import { RiskMeter, SeverityBadge } from "@/components/severity"
import { Progress } from "@/components/ui/progress"
import type { RiskScore } from "@/lib/types"

function ScoreBar({ label, value, hint }: { label: string; value: number; hint: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between text-xs">
        <span className="font-semibold tracking-wider uppercase">{label}</span>
        <span className="tabular font-mono">{value.toFixed(1)} / 100</span>
      </div>
      <Progress value={value} aria-label={label} />
      <span className="text-[0.7rem] text-muted-foreground">{hint}</span>
    </div>
  )
}

export function RiskExplanation({ risk }: { risk: RiskScore }) {
  const w = typeof risk.features.rule_weight === "number" ? risk.features.rule_weight : 0.6
  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between gap-3 border bg-muted/40 p-3">
        <div className="flex flex-col gap-1">
          <span className="text-[0.65rem] font-semibold tracking-widest text-muted-foreground uppercase">Final risk</span>
          <RiskMeter score={risk.risk_score} severity={risk.severity} className="[&>div:first-child]:w-28" />
        </div>
        <SeverityBadge severity={risk.severity} />
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <ScoreBar label="Rule score" value={risk.rule_score} hint="Sum of triggered rule points, capped at 100" />
        <ScoreBar
          label="ML score"
          value={risk.ml_score}
          hint={risk.ml_is_anomaly ? "Isolation Forest flagged this event as an outlier" : "Isolation Forest anomaly score (rescaled)"}
        />
      </div>

      <section className="flex flex-col gap-2">
        <h4 className="flex items-center gap-2 text-sm font-semibold">
          <ListChecksIcon className="size-4 text-primary" /> Triggered rules
        </h4>
        {risk.triggered_rules.length === 0 ? (
          <p className="text-sm text-muted-foreground">No rule fired for this event.</p>
        ) : (
          <ul className="flex flex-col divide-y border">
            {risk.triggered_rules.map((r) => (
              <li key={r.code} className="flex items-start justify-between gap-3 p-2.5 text-sm">
                <div className="flex flex-col gap-0.5">
                  <span className="font-medium">
                    <span className="mr-2 font-mono text-xs text-primary">{r.code}</span>
                    {r.name}
                  </span>
                  <span className="text-xs text-muted-foreground">{r.reason}</span>
                </div>
                <span className="tabular shrink-0 font-mono text-xs">+{r.points}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {risk.top_features.length > 0 && (
        <section className="flex flex-col gap-2">
          <h4 className="flex items-center gap-2 text-sm font-semibold">
            <BrainCircuitIcon className="size-4 text-primary" /> Most unusual inputs
          </h4>
          <ul className="flex flex-col gap-1.5 text-sm">
            {risk.top_features.map((f) => (
              <li key={f.feature} className="flex justify-between gap-3">
                <span>{f.label}</span>
                <span className="tabular shrink-0 font-mono text-xs text-muted-foreground">
                  value {f.value} · z {f.z_score}
                </span>
              </li>
            ))}
          </ul>
          <p className="text-[0.7rem] text-muted-foreground">
            Heuristic: features furthest from the dataset average (z-score). This is not a model attribution method.
          </p>
        </section>
      )}

      <section className="flex flex-col gap-2 border-l-2 border-primary bg-accent/40 p-3">
        <h4 className="flex items-center gap-2 text-sm font-semibold">
          <SigmaIcon className="size-4 text-primary" /> How this score was computed
        </h4>
        <p className="font-mono text-xs leading-relaxed">
          risk = {w} × {risk.rule_score.toFixed(1)} + {(1 - w).toFixed(1)} × {risk.ml_score.toFixed(1)}
          {risk.rule_score > 0 && risk.ml_is_anomaly ? " + 10 (rules and ML agree)" : ""} = {risk.risk_score.toFixed(1)}
        </p>
        <p className="text-xs text-muted-foreground">{risk.explanation}</p>
      </section>
    </div>
  )
}
