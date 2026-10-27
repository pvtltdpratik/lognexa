"use client"

import { zodResolver } from "@hookform/resolvers/zod"
import { DatabaseIcon, FlaskConicalIcon, PlayIcon, TriangleAlertIcon } from "lucide-react"
import * as React from "react"
import { Controller, useForm, type Control, type FieldPath, type FieldValues } from "react-hook-form"

import { PageIntro } from "@/components/app-shell"
import { EmptyState, ErrorState, TableSkeleton } from "@/components/states"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { toast } from "@/components/ui/toast"
import { useApi } from "@/hooks/use-api"
import { ApiError, api, errorMessage } from "@/lib/api"
import { formatShort, humanize } from "@/lib/format"
import { analyzeSchema, datasetSchema, type AnalyzeInput, type DatasetInput } from "@/lib/schemas"
import type { AnalysisRun, Prf } from "@/lib/types"

/** Numeric input bound to react-hook-form; empty input becomes NaN so zod reports it. */
function NumberField<T extends FieldValues>({ control, name, label, hint, step = "any" }: {
  control: Control<T>; name: FieldPath<T>; label: string; hint: string; step?: string
}) {
  return (
    <Controller
      control={control}
      name={name}
      render={({ field, fieldState }) => (
        <Field data-invalid={fieldState.invalid}>
          <FieldLabel htmlFor={name}>{label}</FieldLabel>
          <Input
            id={name}
            type="number"
            step={step}
            inputMode="decimal"
            value={Number.isNaN(field.value) ? "" : field.value}
            onChange={(e) => field.onChange(e.target.value === "" ? NaN : e.target.valueAsNumber)}
            onBlur={field.onBlur}
            aria-invalid={fieldState.invalid}
          />
          <FieldDescription>{hint}</FieldDescription>
          <FieldError errors={[fieldState.error]} />
        </Field>
      )}
    />
  )
}

function applyServerErrors<T extends FieldValues>(e: unknown, setError: (n: FieldPath<T>, v: { message: string }) => void, fields: string[]) {
  if (e instanceof ApiError && e.code === "validation_error") {
    for (const d of e.details) if (d.field && fields.includes(d.field)) setError(d.field as FieldPath<T>, { message: d.message })
  }
}

function AnalyzeForm({ onDone }: { onDone: () => void }) {
  const form = useForm<AnalyzeInput>({
    resolver: zodResolver(analyzeSchema),
    defaultValues: { contamination: 0.05, alert_threshold: 40, rule_weight: 0.6 },
    mode: "onChange",
  })
  async function onSubmit(values: AnalyzeInput) {
    try {
      const run = await api.analyze(values)
      toast.add({ title: `Analysis run #${run.id} completed`, description: `${run.logs_analyzed} events scored, ${run.alerts_created} new alerts`, type: "success" })
      onDone()
    } catch (e) {
      applyServerErrors<AnalyzeInput>(e, form.setError, ["contamination", "alert_threshold", "rule_weight"])
      toast.add({ title: "Analysis failed", description: errorMessage(e), type: "error" })
    }
  }
  const busy = form.formState.isSubmitting
  return (
    <Card>
      <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="contents">
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><PlayIcon className="size-4 text-primary" /> Run analysis</CardTitle>
          <CardDescription>Re-score every event. Open alerts are regenerated; acknowledged and resolved alerts are kept.</CardDescription>
        </CardHeader>
        <CardContent>
          <FieldGroup>
            <NumberField control={form.control} name="contamination" label="Isolation Forest contamination" hint="Expected share of outliers, 0.01–0.2" />
            <NumberField control={form.control} name="alert_threshold" label="Alert threshold" hint="Minimum risk score (1–100) that raises an alert" />
            <NumberField control={form.control} name="rule_weight" label="Rule weight (w)" hint="0–1. ML weight is 1 − w" />
          </FieldGroup>
        </CardContent>
        <CardFooter>
          <Button type="submit" disabled={busy || !form.formState.isValid}>
            {busy ? <Spinner data-icon="inline-start" /> : <PlayIcon data-icon="inline-start" />}
            {busy ? "Analysing…" : "Run analysis"}
          </Button>
        </CardFooter>
      </form>
    </Card>
  )
}

function DatasetForm({ onDone }: { onDone: () => void }) {
  const [confirm, setConfirm] = React.useState<DatasetInput | null>(null)
  const [busy, setBusy] = React.useState(false)
  const form = useForm<DatasetInput>({
    resolver: zodResolver(datasetSchema),
    defaultValues: { seed: 42, n_users: 60, days: 14, n_records: 2200 },
    mode: "onChange",
  })
  async function generate() {
    if (!confirm) return
    setBusy(true)
    try {
      const res = await api.generateDataset(confirm)
      toast.add({ title: "Dataset regenerated", description: `${res.logs} logs for ${res.users} users (${res.injected_anomalies} injected anomalies)`, type: "success" })
      onDone()
    } catch (e) {
      applyServerErrors<DatasetInput>(e, form.setError, ["seed", "n_users", "days", "n_records"])
      toast.add({ title: "Generation failed", description: errorMessage(e), type: "error" })
    } finally {
      setBusy(false)
      setConfirm(null)
    }
  }
  return (
    <Card>
      <form onSubmit={form.handleSubmit((v) => setConfirm(v))} noValidate className="contents">
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><DatabaseIcon className="size-4 text-primary" /> Synthetic dataset</CardTitle>
          <CardDescription>Regenerate reproducible synthetic logs. The same seed always produces the same data.</CardDescription>
        </CardHeader>
        <CardContent>
          <FieldGroup className="grid gap-4 sm:grid-cols-2">
            <NumberField control={form.control} name="seed" label="Random seed" hint="0 – 2,147,483,647" step="1" />
            <NumberField control={form.control} name="n_users" label="Users" hint="6–500" step="1" />
            <NumberField control={form.control} name="days" label="Days of activity" hint="1–90" step="1" />
            <NumberField control={form.control} name="n_records" label="Log records" hint="200–50,000, ≥ 5 × users" step="1" />
          </FieldGroup>
        </CardContent>
        <CardFooter>
          <Button type="submit" variant="outline" disabled={busy || !form.formState.isValid}>
            {busy ? <Spinner data-icon="inline-start" /> : <DatabaseIcon data-icon="inline-start" />}
            {busy ? "Generating…" : "Regenerate dataset"}
          </Button>
        </CardFooter>
      </form>
      <AlertDialog open={confirm !== null} onOpenChange={(o) => !o && !busy && setConfirm(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Replace all data?</AlertDialogTitle>
            <AlertDialogDescription>
              This deletes every user, log, risk score and alert (including resolved alerts) and loads a new synthetic dataset
              of {confirm?.n_records} records. The analysis is re-run automatically.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={generate} disabled={busy}>
              {busy && <Spinner data-icon="inline-start" />} Replace data
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  )
}

function MetricRow({ label, m }: { label: string; m?: Prf }) {
  if (!m) return null
  return (
    <TableRow>
      <TableCell className="font-medium">{label}</TableCell>
      {[m.precision, m.recall, m.f1].map((v, i) => <TableCell key={i} className="tabular text-right font-mono text-xs">{v.toFixed(3)}</TableCell>)}
      <TableCell className="tabular hidden text-right font-mono text-xs sm:table-cell">{m.tp} / {m.fp} / {m.fn}</TableCell>
    </TableRow>
  )
}

function Evaluation({ run }: { run: AnalysisRun }) {
  const m = run.metrics
  if (!m.combined) return <p className="text-sm text-muted-foreground">{m.note ?? "No evaluation available."}</p>
  return (
    <div className="flex flex-col gap-4">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Detector</TableHead><TableHead className="text-right">Precision</TableHead>
            <TableHead className="text-right">Recall</TableHead><TableHead className="text-right">F1</TableHead>
            <TableHead className="hidden text-right sm:table-cell">TP / FP / FN</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <MetricRow label="Combined (risk ≥ threshold)" m={m.combined} />
          <MetricRow label="Rules only (rule score ≥ threshold)" m={m.rules_only} />
          <MetricRow label="Isolation Forest only (flagged)" m={m.ml_only} />
        </TableBody>
      </Table>
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        {Object.entries(m.per_type ?? {}).map(([k, v]) => (
          <div key={k} className="border p-3">
            <div className="text-xs font-semibold tracking-wider capitalize">{humanize(k)}</div>
            <div className="tabular font-heading text-xl font-semibold">{v.detected}/{v.injected}</div>
            <div className="text-xs text-muted-foreground">recall {v.recall.toFixed(2)}</div>
          </div>
        ))}
      </div>
      <p className="flex items-start gap-2 border-l-2 border-severity-medium pl-3 text-xs text-muted-foreground">
        <TriangleAlertIcon className="mt-0.5 size-3.5 shrink-0" /> {m.caveat}
      </p>
    </div>
  )
}

export default function AnalysisPage() {
  const runs = useApi(() => api.runs(10), [])
  const latest = runs.data?.find((r) => r.status === "completed")
  return (
    <>
      <PageIntro title="Analysis & data" description="Tune the detection pipeline, regenerate the synthetic dataset and review evaluation results." />
      <div className="grid gap-4 lg:grid-cols-2">
        <AnalyzeForm onDone={runs.reload} />
        <DatasetForm onDone={runs.reload} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><FlaskConicalIcon className="size-4 text-primary" /> Evaluation on synthetic labels</CardTitle>
          <CardDescription>{latest ? `Run #${latest.id} · threshold ${latest.parameters.alert_threshold} · ${latest.metrics.labelled_anomalies} injected anomalies in ${latest.metrics.total_events} events` : "No completed run yet"}</CardDescription>
        </CardHeader>
        <CardContent>
          {runs.error ? <ErrorState error={runs.error} onRetry={runs.reload} /> : !runs.data ? <TableSkeleton rows={4} cols={4} /> :
            latest ? <Evaluation run={latest} /> : <EmptyState title="Nothing to evaluate" description="Run the analysis to compute metrics." />}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Run history</CardTitle>
          <CardDescription>Most recent analysis runs and their parameters.</CardDescription>
        </CardHeader>
        <CardContent>
          {!runs.data ? <TableSkeleton rows={4} cols={5} /> : runs.data.length === 0 ? (
            <EmptyState title="No runs yet" description="Use the form above to run the first analysis." />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Run</TableHead><TableHead>Started</TableHead><TableHead>Status</TableHead>
                  <TableHead className="hidden md:table-cell">Parameters</TableHead>
                  <TableHead className="text-right">Events</TableHead><TableHead className="text-right">Alerts</TableHead>
                  <TableHead className="hidden text-right sm:table-cell">F1</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {runs.data.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell className="font-mono text-xs">#{r.id}</TableCell>
                    <TableCell className="font-mono text-xs">{formatShort(r.started_at)}</TableCell>
                    <TableCell>
                      <Badge variant={r.status === "failed" ? "destructive" : "secondary"}>{r.status}</Badge>
                      {r.error && <div className="max-w-56 truncate text-xs text-destructive" title={r.error}>{r.error}</div>}
                    </TableCell>
                    <TableCell className="hidden font-mono text-xs text-muted-foreground md:table-cell">
                      c={r.parameters.contamination} · t={r.parameters.alert_threshold} · w={r.parameters.rule_weight}
                    </TableCell>
                    <TableCell className="tabular text-right font-mono text-xs">{r.logs_analyzed}</TableCell>
                    <TableCell className="tabular text-right font-mono text-xs">{r.alerts_created}</TableCell>
                    <TableCell className="tabular hidden text-right font-mono text-xs sm:table-cell">{r.metrics.combined?.f1.toFixed(3) ?? "–"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </>
  )
}
