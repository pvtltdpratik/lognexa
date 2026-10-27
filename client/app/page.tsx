"use client"

import {
  AlertTriangleIcon,
  BellRingIcon,
  BrainCircuitIcon,
  DatabaseIcon,
  GaugeIcon,
  ShieldXIcon,
  UsersIcon,
} from "lucide-react"
import Link from "next/link"
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, XAxis, YAxis } from "recharts"

import { PageIntro } from "@/components/app-shell"
import { SeverityBadge } from "@/components/severity"
import { EmptyState, ErrorState } from "@/components/states"
import { buttonVariants } from "@/components/ui/button"
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ChartContainer, ChartLegend, ChartLegendContent, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useApi } from "@/hooks/use-api"
import { api } from "@/lib/api"
import { SEVERITIES, formatDay, formatShort, nf, pct, severityColor, severityLabel } from "@/lib/format"
import type { Overview } from "@/lib/types"

const dailyConfig = {
  events: { label: "Events", color: "var(--chart-4)" },
  alerts: { label: "Alerts", color: "var(--chart-1)" },
} satisfies ChartConfig

const hourlyConfig = {
  events: { label: "Events", color: "var(--chart-4)" },
  high_risk: { label: "High-risk (≥50)", color: "var(--chart-1)" },
} satisfies ChartConfig

const ruleConfig = { count: { label: "Hits", color: "var(--chart-2)" } } satisfies ChartConfig

function Stat({ title, value, hint, icon: Icon, accent }: { title: string; value: string; hint: string; icon: typeof GaugeIcon; accent?: string }) {
  return (
    <Card size="sm">
      <CardHeader>
        <CardDescription className="text-xs font-semibold tracking-widest uppercase">{title}</CardDescription>
        <CardAction>
          <Icon className="size-4" style={{ color: accent ?? "var(--muted-foreground)" }} />
        </CardAction>
        <CardTitle className="tabular font-heading text-3xl font-semibold">{value}</CardTitle>
      </CardHeader>
      <CardContent className="text-xs text-muted-foreground">{hint}</CardContent>
    </Card>
  )
}

function Dashboard({ data }: { data: Overview }) {
  const scored = SEVERITIES.reduce((n, s) => n + data.severity_counts[s], 0)
  const run = data.latest_run
  const combined = run?.metrics.combined
  const sevData = SEVERITIES.map((s) => ({ severity: severityLabel[s], key: s, count: data.severity_counts[s] }))

  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat title="Access events" value={nf.format(data.total_logs)} icon={DatabaseIcon}
          hint={data.period_start && data.period_end ? `${formatDay(data.period_start)} – ${formatDay(data.period_end)} · ${data.total_users} users` : "No data"} />
        <Stat title="Open alerts" value={nf.format(data.open_alerts)} icon={BellRingIcon} accent="var(--severity-critical)"
          hint={`${data.alert_severity_counts.critical} critical · ${data.acknowledged_alerts} acknowledged · ${data.resolved_alerts} resolved`} />
        <Stat title="High + critical events" value={nf.format(data.severity_counts.high + data.severity_counts.critical)} icon={AlertTriangleIcon} accent="var(--severity-high)"
          hint={scored ? `${pct((data.severity_counts.high + data.severity_counts.critical) / scored)} of scored events · avg risk ${data.avg_risk}` : "Not analysed yet"} />
        <Stat title="Failed / denied" value={nf.format(data.failed_events)} icon={ShieldXIcon}
          hint={data.total_logs ? `${pct(data.failed_events / data.total_logs)} of all requests` : "–"} />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Activity and alerts per day</CardTitle>
            <CardDescription>Events in the log window, with the alerts raised for each day.</CardDescription>
          </CardHeader>
          <CardContent>
            <ChartContainer config={dailyConfig} className="aspect-auto h-64 w-full">
              <AreaChart data={data.daily} margin={{ left: 0, right: 8 }}>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="date" tickLine={false} axisLine={false} tickFormatter={formatDay} minTickGap={24} />
                <YAxis tickLine={false} axisLine={false} width={32} />
                <ChartTooltip content={<ChartTooltipContent labelFormatter={(v) => formatDay(String(v))} />} />
                <ChartLegend content={<ChartLegendContent />} />
                <Area dataKey="events" type="monotone" fill="var(--color-events)" fillOpacity={0.18} stroke="var(--color-events)" strokeWidth={2} />
                <Area dataKey="alerts" type="monotone" fill="var(--color-alerts)" fillOpacity={0.35} stroke="var(--color-alerts)" strokeWidth={2} />
              </AreaChart>
            </ChartContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Severity distribution</CardTitle>
            <CardDescription>All {nf.format(scored)} scored events.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <ChartContainer config={{ count: { label: "Events" } }} className="aspect-auto h-40 w-full">
              <BarChart data={sevData} layout="vertical" margin={{ left: 8, right: 16 }}>
                <XAxis type="number" hide />
                <YAxis type="category" dataKey="severity" tickLine={false} axisLine={false} width={64} />
                <ChartTooltip cursor={false} content={<ChartTooltipContent hideLabel />} />
                <Bar dataKey="count" radius={0}>
                  {sevData.map((d) => <Cell key={d.key} fill={severityColor[d.key]} />)}
                </Bar>
              </BarChart>
            </ChartContainer>
            <ul className="grid grid-cols-2 gap-2 text-xs">
              {SEVERITIES.map((s) => (
                <li key={s} className="flex items-center justify-between border px-2 py-1.5">
                  <SeverityBadge severity={s} className="px-0 py-0 bg-transparent!" />
                  <span className="tabular font-mono">{nf.format(data.severity_counts[s])}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Activity by hour of day</CardTitle>
            <CardDescription>Night-time spikes in high-risk events point to unusual-hour access.</CardDescription>
          </CardHeader>
          <CardContent>
            <ChartContainer config={hourlyConfig} className="aspect-auto h-56 w-full">
              <BarChart data={data.hourly} margin={{ left: 0, right: 8 }}>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="hour" tickLine={false} axisLine={false} tickFormatter={(h) => `${String(h).padStart(2, "0")}h`} interval={2} />
                <YAxis tickLine={false} axisLine={false} width={32} />
                <ChartTooltip content={<ChartTooltipContent labelFormatter={(h) => `${String(h).padStart(2, "0")}:00`} />} />
                <ChartLegend content={<ChartLegendContent />} />
                <Bar dataKey="events" fill="var(--color-events)" fillOpacity={0.55} />
                <Bar dataKey="high_risk" fill="var(--color-high_risk)" />
              </BarChart>
            </ChartContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Detection rule hits</CardTitle>
            <CardDescription>How often each explainable rule fired in the latest analysis.</CardDescription>
          </CardHeader>
          <CardContent>
            {data.rule_hits.length === 0 ? (
              <EmptyState title="No rule hits" description="Run an analysis to populate rule statistics." />
            ) : (
              <ChartContainer config={ruleConfig} className="aspect-auto h-56 w-full">
                <BarChart data={data.rule_hits.map((r) => ({ ...r, label: `${r.code} ${r.name}` }))} layout="vertical" margin={{ left: 8, right: 16 }}>
                  <XAxis type="number" hide />
                  <YAxis type="category" dataKey="label" tickLine={false} axisLine={false} width={190} tick={{ fontSize: 11 }} />
                  <ChartTooltip cursor={false} content={<ChartTooltipContent hideLabel />} />
                  <Bar dataKey="count" fill="var(--color-count)" />
                </BarChart>
              </ChartContainer>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><UsersIcon className="size-4 text-primary" /> Highest-risk users</CardTitle>
            <CardDescription>Ranked by the maximum event risk, then by average risk.</CardDescription>
            <CardAction>
              <Link href="/risk" className={buttonVariants({ variant: "outline", size: "xs" })}>All risk scores</Link>
            </CardAction>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>User</TableHead>
                  <TableHead className="hidden sm:table-cell">Department</TableHead>
                  <TableHead className="text-right">Events</TableHead>
                  <TableHead className="text-right">Avg</TableHead>
                  <TableHead className="text-right">Max</TableHead>
                  <TableHead className="text-right">Open alerts</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.top_users.map((u) => (
                  <TableRow key={u.user_id}>
                    <TableCell>
                      <Link href={`/logs?user=${u.user_id}`} className="font-medium hover:text-primary">{u.username}</Link>
                      <div className="text-xs text-muted-foreground">{u.full_name}</div>
                    </TableCell>
                    <TableCell className="hidden sm:table-cell">{u.department}</TableCell>
                    <TableCell className="tabular text-right font-mono text-xs">{u.events}</TableCell>
                    <TableCell className="tabular text-right font-mono text-xs">{u.avg_risk.toFixed(1)}</TableCell>
                    <TableCell className="tabular text-right font-mono text-xs">{u.max_risk.toFixed(0)}</TableCell>
                    <TableCell className="tabular text-right font-mono text-xs">{u.open_alerts}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><BrainCircuitIcon className="size-4 text-primary" /> Latest analysis</CardTitle>
            <CardDescription>{run ? `Run #${run.id} · ${formatShort(run.started_at)}` : "No analysis has been run"}</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 text-sm">
            {run && combined ? (
              <>
                <div className="grid grid-cols-3 gap-2 text-center">
                  {(["precision", "recall", "f1"] as const).map((k) => (
                    <div key={k} className="border p-2">
                      <div className="tabular font-heading text-xl font-semibold">{combined[k].toFixed(2)}</div>
                      <div className="text-[0.65rem] tracking-widest text-muted-foreground uppercase">{k}</div>
                    </div>
                  ))}
                </div>
                <p className="text-xs text-muted-foreground">
                  {run.logs_analyzed} events · {run.alerts_created} alerts · threshold {run.parameters.alert_threshold} ·
                  contamination {run.parameters.contamination}
                </p>
                <p className="border-l-2 border-severity-medium pl-2 text-xs text-muted-foreground">{run.metrics.caveat}</p>
              </>
            ) : (
              <p className="text-muted-foreground">Run the analysis pipeline to score events.</p>
            )}
            <Link href="/analysis" className={buttonVariants({ variant: "outline", size: "sm" })}>Open analysis</Link>
          </CardContent>
        </Card>
      </div>
    </>
  )
}

export default function OverviewPage() {
  const { data, error, loading, reload } = useApi(() => api.overview(), [])
  return (
    <>
      <PageIntro
        title="Security overview"
        description="Behavioural risk across all synthetic access events, combining explainable rules with an Isolation Forest model."
      />
      {!!error && <ErrorState error={error} onRetry={reload} />}
      {loading && !data && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className={i < 4 ? "h-32" : "h-64 sm:col-span-2"} />)}
        </div>
      )}
      {data && data.total_logs === 0 && (
        <EmptyState
          icon={DatabaseIcon}
          title="No access logs yet"
          description="Generate the synthetic dataset to start monitoring."
          action={<Link href="/analysis" className={buttonVariants({ size: "sm" })}>Generate dataset</Link>}
        />
      )}
      {data && data.total_logs > 0 && <Dashboard data={data} />}
    </>
  )
}
