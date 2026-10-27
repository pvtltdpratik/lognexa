"use client"

import { SigmaIcon } from "lucide-react"
import * as React from "react"

import { PageIntro } from "@/components/app-shell"
import { LogDetailSheet } from "@/components/log-detail-sheet"
import { Pager } from "@/components/pager"
import { RiskMeter, SeverityBadge } from "@/components/severity"
import { EmptyState, ErrorState, TableSkeleton } from "@/components/states"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Field, FieldError, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useApi, useDebounced } from "@/hooks/use-api"
import { api } from "@/lib/api"
import { formatShort, humanize, severityColor } from "@/lib/format"
import { severityValues } from "@/lib/schemas"

function Methodology() {
  const { data, error, reload } = useApi(() => api.methodology(), [])
  if (error) return <ErrorState error={error} onRetry={reload} />
  if (!data) return <TableSkeleton rows={4} cols={3} />
  const bands = [...data.severity_bands].reverse()
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><SigmaIcon className="size-4 text-primary" /> Scoring methodology</CardTitle>
        <CardDescription>Every risk score is reproducible from the rules and model output below.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-6 lg:grid-cols-2">
        <div className="flex flex-col gap-4 text-sm">
          <p className="border-l-2 border-primary bg-accent/40 p-3 font-mono text-xs leading-relaxed">{data.formula}</p>
          <p className="text-muted-foreground">
            Default rule weight <b className="text-foreground">w = {data.default_rule_weight}</b>, agreement bonus{" "}
            <b className="text-foreground">+{data.agreement_bonus}</b>. The ML score rescales the Isolation Forest anomaly
            score so the median event is 0 and the most anomalous event is 100.
          </p>
          <div className="flex flex-col gap-1.5">
            <span className="text-xs font-semibold tracking-widest text-muted-foreground uppercase">Severity bands</span>
            <div className="flex h-8 w-full">
              {bands.map((b, i) => {
                const next = bands[i + 1]?.min ?? 100
                return (
                  <div key={b.severity} className="flex items-center justify-center text-[0.65rem] font-semibold tracking-widest text-background uppercase"
                    style={{ width: `${next - b.min}%`, backgroundColor: severityColor[b.severity] }}>
                    {b.severity}
                  </div>
                )
              })}
            </div>
            <div className="flex justify-between font-mono text-[0.65rem] text-muted-foreground"><span>0</span><span>25</span><span>50</span><span>75</span><span>100</span></div>
          </div>
        </div>
        <Table>
          <TableHeader>
            <TableRow><TableHead>Rule</TableHead><TableHead>Category</TableHead><TableHead className="text-right">Points</TableHead></TableRow>
          </TableHeader>
          <TableBody>
            {data.rules.map((r) => (
              <TableRow key={r.code}>
                <TableCell><span className="mr-2 font-mono text-xs text-primary">{r.code}</span>{r.name}</TableCell>
                <TableCell className="text-xs capitalize text-muted-foreground">{humanize(r.category)}</TableCell>
                <TableCell className="tabular text-right font-mono text-xs">+{r.points}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}

export default function RiskPage() {
  const [severity, setSeverity] = React.useState("")
  const [minInput, setMinInput] = React.useState("")
  const [rule, setRule] = React.useState("")
  const [page, setPage] = React.useState(1)
  const [selected, setSelected] = React.useState<number | null>(null)
  const min = useDebounced(minInput, 300)
  const minNum = min === "" ? undefined : Number(min)
  const minError = minInput !== "" && (Number.isNaN(Number(minInput)) || Number(minInput) < 0 || Number(minInput) > 100)
    ? "Enter a number between 0 and 100" : null

  const methodology = useApi(() => api.methodology(), [])
  const { data, error, loading, reload } = useApi(
    () => api.riskScores({ page, page_size: 20, severity, rule_code: rule, min_score: minError ? undefined : minNum }),
    [page, severity, rule, minNum, minError]
  )
  const users = useApi(() => api.userRisk(12), [])

  return (
    <>
      <PageIntro title="Risk scores" description="Per-event risk combining rule points and the Isolation Forest score, plus per-user aggregates." />
      <Methodology />

      <div className="grid gap-4 xl:grid-cols-3">
        <Card size="sm" className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Scored events</CardTitle>
            <CardDescription>Select an event to view its explanation.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
              <Field className="sm:w-40">
                <FieldLabel htmlFor="risk-sev" className="text-xs">Severity</FieldLabel>
                <NativeSelect id="risk-sev" value={severity} onChange={(e) => { setSeverity(e.target.value); setPage(1) }} className="w-full">
                  <NativeSelectOption value="">All</NativeSelectOption>
                  {severityValues.map((s) => <NativeSelectOption key={s} value={s}>{humanize(s)}</NativeSelectOption>)}
                </NativeSelect>
              </Field>
              <Field className="sm:w-64">
                <FieldLabel htmlFor="risk-rule" className="text-xs">Triggered rule</FieldLabel>
                <NativeSelect id="risk-rule" value={rule} onChange={(e) => { setRule(e.target.value); setPage(1) }} className="w-full">
                  <NativeSelectOption value="">Any</NativeSelectOption>
                  {methodology.data?.rules.map((r) => <NativeSelectOption key={r.code} value={r.code}>{r.code} – {r.name}</NativeSelectOption>)}
                </NativeSelect>
              </Field>
              <Field className="sm:w-40" data-invalid={!!minError}>
                <FieldLabel htmlFor="risk-min" className="text-xs">Minimum score</FieldLabel>
                <Input id="risk-min" type="number" inputMode="decimal" min={0} max={100} placeholder="0–100" value={minInput}
                  aria-invalid={!!minError} onChange={(e) => { setMinInput(e.target.value); setPage(1) }} />
                <FieldError>{minError}</FieldError>
              </Field>
            </div>
            {!!error && <ErrorState error={error} onRetry={reload} />}
            {loading && !data ? <TableSkeleton rows={8} cols={5} /> : data && data.total === 0 ? (
              <EmptyState title="No scored events" description="Run an analysis, or relax the filters." />
            ) : data ? (
              <>
                <Table className={loading ? "opacity-60" : ""}>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Event</TableHead><TableHead>User</TableHead>
                      <TableHead className="hidden md:table-cell">Rules</TableHead>
                      <TableHead className="hidden sm:table-cell text-right">Rule / ML</TableHead>
                      <TableHead>Risk</TableHead><TableHead>Severity</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.items.map((r) => (
                      <TableRow key={r.id} className="cursor-pointer" tabIndex={0} onClick={() => setSelected(r.log_id)}
                        onKeyDown={(e) => e.key === "Enter" && setSelected(r.log_id)}>
                        <TableCell>
                          <div className="font-mono text-xs">{formatShort(r.timestamp)}</div>
                          <div className="max-w-48 truncate text-xs text-muted-foreground">{humanize(r.action)} · {r.resource}</div>
                        </TableCell>
                        <TableCell>{r.username}</TableCell>
                        <TableCell className="hidden font-mono text-xs text-primary md:table-cell">{r.rule_codes.join(" ") || "–"}</TableCell>
                        <TableCell className="tabular hidden text-right font-mono text-xs sm:table-cell">{r.rule_score.toFixed(0)} / {r.ml_score.toFixed(0)}</TableCell>
                        <TableCell><RiskMeter score={r.risk_score} severity={r.severity} /></TableCell>
                        <TableCell><SeverityBadge severity={r.severity} /></TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                <Pager page={data.page} pages={data.pages} total={data.total} pageSize={data.page_size} onPage={setPage} />
              </>
            ) : null}
          </CardContent>
        </Card>

        <Card size="sm">
          <CardHeader>
            <CardTitle>User risk ranking</CardTitle>
            <CardDescription>Max and average event risk per user.</CardDescription>
          </CardHeader>
          <CardContent>
            {users.error ? <ErrorState error={users.error} onRetry={users.reload} /> : !users.data ? <TableSkeleton rows={8} cols={2} /> : (
              <ul className="flex flex-col divide-y">
                {users.data.map((u) => (
                  <li key={u.user_id} className="flex items-center justify-between gap-3 py-2 text-sm">
                    <div className="min-w-0">
                      <div className="truncate font-medium">{u.username}</div>
                      <div className="text-xs text-muted-foreground">{u.department} · {u.high_risk_events} high-risk · {u.open_alerts} open</div>
                    </div>
                    <div className="text-right">
                      <div className="tabular font-mono text-sm">{u.max_risk.toFixed(0)}</div>
                      <div className="tabular font-mono text-[0.65rem] text-muted-foreground">avg {u.avg_risk.toFixed(1)}</div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
      <LogDetailSheet logId={selected} onOpenChange={(o) => !o && setSelected(null)} />
    </>
  )
}
